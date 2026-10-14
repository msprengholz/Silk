"""
#61 — generalized band-split corner-cell exclusion, an actionable
one-cell refusal, and split normalization on set.

Three problems, three groups of tests:

1. band_cells' corner-cell exclusion was hard-coded to the LITERAL
   values 0.1 / 0.9 ("a split sits near this end of the axis -> that
   end's cell is a corner cell, drop it"). A user-chosen width (0.2,
   0.85) fell through it silently, so a corner cell could be pulled
   into a band.
   - test_band_cells_identical_to_legacy_on_default_splits: the new
     rule is PROVABLY identical to the old one for every split list
     the fixtures can produce ({0.1, 0.5, 0.9}, every subset, both
     axes, every seam label and side);
   - test_band_cells_generalizes_user_widths: at 0.2 / 0.85 (and
     0.3 / 0.7) the corner cell is still excluded — and provably is
     NOT what the old literal rule returned;
   - test_corner_model_bands_follow_non_default_widths: real 2x2 corner
     model geometry, every band width moved off 0.1 / 0.9 — every band
     still resolves to the same single corner-free cell;

1b. #64 — the band width is the USER'S. The blend reads the two split
   values the patch already carries at the seam-perpendicular axis's
   ends instead of asserting its own default beside them (no new Blend
   property; the patch owns its splits, the blend consumes them).
   - test_split_at_end_picks_the_splits_own_end: the end-classification
     rule (lowest split -> the 0 end, highest -> the 1 end, 0.5 -> both
     neither), including two splits on ONE axis;
   - test_blend_reads_the_user_band_width: a user width survives the
     recompute with no duplicate added, is the band's ACTUAL parameter
     extent (checked against the base surface, not a cell index), and
     the blend's poles move onto it;
   - test_band_widths_of_both_sides_are_independent: setting one side's
     width leaves the other side's split list alone, in both directions;
   - test_corner_patch_band_widths_stay_per_seam: the four-patch corner
     keeps both splits per patch and one band cell per strip; a width on
     one seam does not disturb the other seam's band axis;
   - test_default_band_split_decision_is_unchanged: over every split list
     the fixtures can produce, the new rule writes the default EXACTLY
     when the pre-#64 one did — the no-user-choice path is unchanged.

2. The multi-cell refusal named a cell count and nothing else.
   - test_multi_cell_band_refusal_names_patch_and_values: the message
     names the patch, the seam, both axis split lists, how many cells
     they make, the excluded corner cells, and the single split value
     that would leave a one-cell band.

3. #53 display residue: a rejected split stayed in the stored
   USplits / VSplits while the geometry silently dropped it.
   - test_splits_normalized_on_set: 0 < u1 < u2 < 1 is pinned — 0.0,
     1.0, negative, >1, duplicates and unsorted input never persist,
     the stored list equals what the geometry used, and the console
     says what was rejected and why.

4. #76: the one-split-per-end limit was a SENTENCE in a refusal message.
   - test_over_limit_splits_are_refused_on_the_property: at most one
     split below 0.5 and one above, per axis, enforced on the property
     path — [0.2, 0.8] and [0.1, 0.5, 0.9] pass, [0.2, 0.45, 0.9],
     [0.2, 0.3] and [0.85, 0.95] are refused, and a refusal leaves the
     axis exactly as it was;
   - test_over_limit_refusal_is_visible_on_the_object: the refusal shows
     up in the object's own state (Invalid / isValid() / status string),
     with a control and a recovery, because the failure it prevents is a
     blend that silently keeps stale poles;
   - test_band_writes_can_never_go_over_the_limit: neither writer of a
     split in the codebase (ensure_band_split, the panel's band editor)
     can produce an over-limit axis, so the rule permits every layout
     the workbench itself builds.

NOTE on the oracle — the gap noted here was CLOSED by #63.
SilkChecks re-derives band_cells independently, on purpose ("the oracle
re-derives the object code's tables instead of importing them, so a bug
in the object code cannot hide itself"), and that copy still hard-coded
0.1 / 0.9 when this ticket was written. Consequence, demonstrated: a
SETTLED, correct blend whose seam-parallel axis carries a user width
(e.g. Patch44.VSplits=[0.85] on the corner pair, where no blend writes
that axis) builds its 24 poles from the correct single corner-free cell,
yet check_blend derived a two-cell band, failed to produce reference
rows and reported "no shared edge found" on B1/B2 — the oracle
disagreeing with correct geometry.

#63 generalized that independent copy with the same end-classification
rule (again MIRRORED, not imported — see Tests/test_oracle_band_cells.py,
which also PROVES the new rule byte-identical to the old one on all 512
default-reachable layouts). The oracle no longer has a gap here, so the
tests in this file may now be complemented by a check_blend assertion on
a non-default width; that one lives with the rest of the oracle work.
"""

import itertools

import FreeCAD

import Tests.corner_model as cm

Vector = FreeCAD.Vector


class _Capture:
    """Capture BOTH console errors and messages (still forwarded)."""

    def __enter__(self):
        self.errors = []
        self.messages = []
        self._oe = FreeCAD.Console.PrintError
        self._om = FreeCAD.Console.PrintMessage
        FreeCAD.Console.PrintError = lambda m: (
            self.errors.append(str(m)), self._oe(m))
        FreeCAD.Console.PrintMessage = lambda m: (
            self.messages.append(str(m)), self._om(m))
        return self

    def __exit__(self, *args):
        FreeCAD.Console.PrintError = self._oe
        FreeCAD.Console.PrintMessage = self._om


class _StubPatch:
    """Minimal stand-in: band_cells reads nothing but USplits / VSplits
    (and band_diagnosis the Name), so the split-selection RULE can be
    exercised over many layouts without building geometry."""

    def __init__(self, u=None, v=None, name="Stub"):
        self.USplits = list(u or [])
        self.VSplits = list(v or [])
        self.Name = name


def _legacy_band_cells(p, ea, ss):
    """The pre-#61 rule, verbatim — the 0.1 / 0.9 literals."""
    from SilkMachinery import build_intervals
    ivs_u = build_intervals(list(p.USplits or []))
    ivs_v = build_intervals(list(p.VSplits or []))
    nu, nv = len(ivs_u), len(ivs_v)
    if ea[0] == "U":
        b = (nv - 1) if ss else 0
        keep_u = set(range(nu))
        if any(abs(s - 0.1) < 1e-9 for s in (p.USplits or [])):
            keep_u.discard(0)
        if any(abs(s - 0.9) < 1e-9 for s in (p.USplits or [])):
            keep_u.discard(nu - 1)
        return [a * nv + b for a in sorted(keep_u)]
    a = (nu - 1) if ss else 0
    keep_v = set(range(nv))
    if any(abs(s - 0.1) < 1e-9 for s in (p.VSplits or [])):
        keep_v.discard(0)
    if any(abs(s - 0.9) < 1e-9 for s in (p.VSplits or [])):
        keep_v.discard(nv - 1)
    return [a * nv + b for b in sorted(keep_v)]


def _subsets(values):
    """Every subset of `values`, as sorted lists."""
    out = []
    for r in range(len(values) + 1):
        for combo in itertools.combinations(values, r):
            out.append(list(combo))
    return out


def _fmt(vs):
    return "[" + ", ".join("%g" % float(v) for v in vs) + "]"


# ---- 1a: provable equivalence on the fixture values ----------------------

def test_band_cells_identical_to_legacy_on_default_splits(doc):
    """The generalized rule reproduces the old 0.1/0.9 rule EXACTLY for
    every split list the fixtures can produce: all subsets of
    {0.1, 0.5, 0.9} on both axes, every seam label, both sides — 8 * 8
    * 4 * 2 = 512 layouts, compared cell-for-cell.

    0.1 and 0.9 are the band widths ensure_band_split writes; 0.5 is the
    mid-surface split the mutation sweeps use. None of the three can
    straddle the 0.5 end classification, which is what makes the
    identity provable rather than merely checked on the fixtures."""
    from SilkMachinery import band_cells

    errors, checks = [], []
    splits_sets = _subsets([0.1, 0.5, 0.9])
    n = 0
    for us, vs in itertools.product(splits_sets, repeat=2):
        p = _StubPatch(us, vs, name="Stub")
        for ea in ("U0", "U1", "V0", "V1"):
            for ss in (0, 1):
                got = band_cells(p, ea, ss)
                want = _legacy_band_cells(p, ea, ss)
                n += 1
                if got != want:
                    errors.append("band_cells(%s, %s, %d) = %r, legacy %r "
                                  "for USplits=%s VSplits=%s"
                                  % (p.Name, ea, ss, got, want,
                                     _fmt(us), _fmt(vs)))
    checks.append("%d layouts compared (U in %s x V in %s, 4 seam labels "
                  "x 2 sides): generalized rule == legacy rule"
                  % (n, len(splits_sets), len(splits_sets)))
    return {"pass": not errors, "errors": errors, "checks": checks}


# ---- 1b: it really is generalized ----------------------------------------

def test_band_cells_generalizes_user_widths(doc):
    """A user width is treated like the default one: the split nearest
    each end of the axis marks that end's cell as the corner cell.

    [0.2, 0.85] on the seam-parallel axis of a patch whose other axis
    is [0.9] gives 2 x 3 cells; seam V1 / side 1 fixes U interval 1 and
    the band is the single middle V cell — the two END cells are corner
    cells. The old literal rule matched neither 0.2 nor 0.85 and
    returned all three V cells: the corner cell silently entered the
    band (the #61 bug)."""
    from SilkMachinery import band_cells, corner_cells

    errors, checks = [], []

    # (splits, intervals, expected excluded interval indices)
    cases = [
        ([0.2, 0.85], 3, {0, 2}),     # both ends marked -> drop first+last
        ([0.85], 2, {1}),             # one width at the 1-end
        ([0.2], 2, {0}),              # one width at the 0-end
        ([0.5], 2, set()),            # mid-surface split marks no end
        ([], 1, set()),               # no split, no corner cell
        ([0.15, 0.3, 0.8], 4, {0, 3}),  # crowded: the extremes still rule
    ]
    for splits, n, want in cases:
        got = corner_cells(splits, n)
        if got != want:
            errors.append("corner_cells(%s, %d) = %r, want %r"
                          % (_fmt(splits), n, sorted(got), sorted(want)))
    checks.append("corner_cells over %d layouts: %s"
                  % (len(cases), ", ".join(
                      "%s/%d->%s" % (_fmt(s), n,
                                     sorted(corner_cells(s, n)))
                      for s, n, _ in cases)))

    # The reported bug, on the real selection function.
    p = _StubPatch([0.9], [0.2, 0.85], name="Wide")
    got = band_cells(p, "V1", 1)
    want = [1 * 3 + 1]            # U interval 1, V interval 1
    if got != want:
        errors.append("band_cells(V1, 1) with VSplits=[0.2, 0.85] = %r, want "
                      "%r (the corner cells at both ends must be excluded)"
                      % (got, want))
    legacy = _legacy_band_cells(p, "V1", 1)
    if legacy == got:
        errors.append("the legacy rule now agrees on [0.2, 0.85] (%r) — the "
                      "regression case no longer reproduces" % (legacy,))
    checks.append("VSplits=[0.2, 0.85], USplits=[0.9], seam V1/1: "
                  "band_cells=%r (legacy rule said %r — it had pulled the "
                  "corner cells in)" % (got, legacy))

    # And the default layout still resolves to exactly the same single
    # cell as it always did, only the width differs.
    d = _StubPatch([0.9], [0.9], name="Default")
    if band_cells(d, "V1", 1) != _legacy_band_cells(d, "V1", 1):
        errors.append("default [0.9] layout no longer matches legacy")
    checks.append("default VSplits=[0.9]: band_cells=%r == legacy"
                  % (band_cells(d, "V1", 1),))
    return {"pass": not errors, "errors": errors, "checks": checks}


# ---- 1c: real geometry, a band width off the defaults -------------------

def test_corner_model_bands_follow_non_default_widths(doc):
    """Real 2x2 corner model, real patches, real subdivision: with every
    band width moved off the default 0.1 / 0.9 (0.1 -> 0.2, 0.9 -> 0.85)
    each band still resolves to exactly the corner-free cell it resolved
    to at the defaults — the cell INDEX set is unchanged, only the width
    of the cell is.

    Under the old literal rule the 0.85 end-cells were no longer
    recognized as corner cells, so the corner cell at the 4-patch
    junction would have been pulled into the band (two cells per band).

    The bands are read straight after a per-PATCH recompute, on purpose:
    a blend re-asserts its own default width on the next document
    recompute (pinned separately in
    test_blend_reasserts_its_default_band_width), so this is the only
    state in which a user width survives long enough to be examined."""
    from SilkMachinery import band_cells, patch_side

    errors, checks = [], []

    def band_sides(model):
        """[(strip name, patch, edge_label, side)] for every ring strip."""
        out = []
        for bname in ("B12", "B24", "B43", "B31"):
            st = model["strips"][bname]
            for p in (st.PatchA, st.PatchB):
                e, ss = patch_side(
                    p, st.PatchB if st.PatchA is p else st.PatchA, 0.01)
                out.append((bname, p, e, ss))
        return out

    model = cm.build_corner_model_with_blend(doc)
    before = {}
    for bname, p, e, ss in band_sides(model):
        before[(p.Name, e, ss)] = sorted(band_cells(p, e, ss))
    for k, v in sorted(before.items()):
        if len(v) != 1:
            errors.append("fixture band %r spans %r, want 1 cell"
                          % (k, v))
    checks.append("default widths: %d bands, all single-cell (%s)"
                  % (len(before),
                     ", ".join("%s:seam %s/side %d -> %s"
                               % (k[0], k[1], k[2], v)
                               for k, v in sorted(before.items()))))

    REMAP = {0.1: 0.2, 0.9: 0.85}
    for name, p in model["patches"].items():
        for prop in ("USplits", "VSplits"):
            cur = [float(v) for v in (getattr(p, prop) or [])]
            new = [REMAP.get(round(v, 9), v) for v in cur]
            if new != cur:
                setattr(p, prop, new)
        p.recompute()   # patch only: no blend re-asserts its default here
    moved = {n: (list(p.USplits or []), list(p.VSplits or []))
             for n, p in model["patches"].items()}
    checks.append("widths moved: %s"
                  % ", ".join("%s U=%s V=%s"
                              % (n, _fmt(u), _fmt(v))
                              for n, (u, v) in sorted(moved.items())))

    for bname, p, e, ss in band_sides(model):
        got = sorted(band_cells(p, e, ss))
        want = before[(p.Name, e, ss)]
        if got != want:
            errors.append("%s on %s: band_cells(%s, %d) = %r, want the "
                          "default-width cell set %r"
                          % (bname, p.Name, e, ss, got, want))
        if len(got) != 1:
            errors.append("%s on %s: band spans %d cells, want 1"
                          % (bname, p.Name, len(got)))
    checks.append("every band still exactly 1 cell, same cell index as at "
                  "the default widths")

    # The corner cell itself must still be excluded: at width 0.85 on a
    # 2-interval axis it is interval 1, and the band must be interval 0.
    p44 = model["patches"]["Patch44"]
    if sorted(band_cells(p44, "V1", 1)) != [2]:
        errors.append("Patch44 V1 band = %r, want the single cell [2] "
                      "(U interval 1, V interval 0 — the 1-end cell is the "
                      "corner cell)"
                      % (band_cells(p44, "V1", 1),))
    checks.append("Patch44 seam V1/1 -> cell [2] (the 0.85 corner cell at "
                  "the junction stays out of the band)")
    return {"pass": not errors, "errors": errors, "checks": checks}


def _band_axis(p, other, tol=0.01):
    """(seam label, side, band-axis property, side-0/1) of p's band for
    the seam it shares with `other`.

    Independently re-derived from the documented rule (AGENTS.md step 3):
    the band axis is PERPENDICULAR to the seam, and the band sits at the
    seam's own parametric end. Nothing here imports band_cells or the
    blend's own seam helper, so the assertions below do not lean on the
    code under test to decide what the band *should* be."""
    from SilkMachinery import patch_side

    e, ss = patch_side(p, other, tol)
    if e is None:
        return None, None, None, None
    return e, ss, ("VSplits" if e[0] == "U" else "USplits"), ss


def _intervals(splits):
    """[(lo, hi)] from split values, written out here so the width
    assertions do not borrow the object code's interval builder."""
    s = sorted(set(float(v) for v in (splits or []) if 0.0 < v < 1.0))
    return list(zip([0.0] + s, s + [1.0]))


def _band_interval(p, prop, ss):
    ivs = _intervals(getattr(p, prop) or [])
    return ivs[0] if ss == 0 else ivs[-1]


def _band_box(p, ea, ss):
    """(u-interval, v-interval) of p's band cell for seam ea / side ss,
    derived here from the split lists so it never borrows band_cells.

    The band axis is PERPENDICULAR to the seam (seam along U -> V band)
    and sits at the seam's own parametric end; the seam-PARALLEL extent
    is the whole axis here because these fixtures put no extra split on
    it. `None` on an axis means "derive it from the cell index"."""
    us, vs = _intervals(p.USplits), _intervals(p.VSplits)
    if ea[0] == "U":
        return None, (vs[0] if ss == 0 else vs[-1])
    return (us[0] if ss == 0 else us[-1]), None


def _band_corners_on_surface(p, idx, want_u, want_v):
    """Worst deviation of subgrid cell `idx`'s four corner poles from the
    patch's base surface evaluated at the corners of the parameter box
    (want_u, want_v).

    This is the geometric proof that the band's ACTUAL extent is that box
    -- not a bookkeeping claim about a cell index."""
    nv = len(_intervals(p.VSplits))
    iu, ivc = divmod(idx, nv)
    us, vs = _intervals(p.USplits), _intervals(p.VSplits)
    box_u = want_u if want_u is not None else us[iu]
    box_v = want_v if want_v is not None else vs[ivc]
    flat = list(p.Proxy._subgrids[idx])
    base = p.Proxy._base_surface
    # flat[U * 4 + V]; the cell's corners in its own local (0..3) grid
    worst = 0.0
    for u_i, v_i in ((0, 0), (0, 3), (3, 0), (3, 3)):
        u = box_u[0] if u_i == 0 else box_u[1]
        v = box_v[0] if v_i == 0 else box_v[1]
        worst = max(worst, (flat[u_i * 4 + v_i] - base.value(u, v)).Length)
    return worst


def test_split_at_end_picks_the_splits_own_end(doc):
    """The end-classification rule #64 reads the band boundary through:
    the LOWEST split belongs to the parametric-0 end, the HIGHEST to the
    parametric-1 end, and one exactly at 0.5 to NEITHER.

    With two splits on ONE axis ([0.1, 0.9]) each end gets its own — the
    rule is per (axis, end), never a single global value. That is what
    lets a four-patch corner carry one split per seam side on the same
    axis and still have each strip read the right one.

    #76 folds the classification into `split_end` — below 0.5 is the
    0-end, above 0.5 the 1-end, exactly 0.5 neither — and `split_at_end`
    is now the per-value classification plus the ORDER within an end
    (lowest for the band that reaches from 0, highest for the one that
    reaches from 1). The second half of this test pins the two together,
    because a second notion of "which end" is exactly how a band comes to
    measure itself against a cell excluded for a different reason."""
    from SilkMachinery import split_at_end

    errors, checks = [], []
    cases = [
        # (splits, ss, expected)
        ([], 0, None), ([], 1, None),
        ([0.1], 0, 0.1), ([0.1], 1, None),
        ([0.9], 0, None), ([0.9], 1, 0.9),
        ([0.1, 0.9], 0, 0.1), ([0.1, 0.9], 1, 0.9),   # both ends, one axis
        ([0.25], 0, 0.25), ([0.75], 1, 0.75),          # user widths
        ([0.25, 0.75], 0, 0.25), ([0.25, 0.75], 1, 0.75),
        ([0.5], 0, None), ([0.5], 1, None),            # neither end
        ([0.15, 0.3, 0.8], 0, 0.15), ([0.15, 0.3, 0.8], 1, 0.8),
        ([0.3, 0.5], 0, 0.3), ([0.3, 0.5], 1, None),
    ]
    for splits, ss, want in cases:
        got = split_at_end(splits, ss)
        ok = (got is None and want is None) or \
             (got is not None and want is not None and abs(got - want) < 1e-12)
        if not ok:
            errors.append("split_at_end(%s, %d) = %r, want %r"
                          % (_fmt(splits), ss, got, want))
    checks.append("%d (splits, end) layouts: the lowest split is the 0-end's, "
                  "the highest the 1-end's, 0.5 is neither" % len(cases))

    # #76: the per-axis limit counts with `split_end`, so this rule has to
    # BE that classification -- an end "has a split" exactly when some
    # split classifies to it. If the two ever drifted, the limit would be
    # counting a different notion of "which end" than the one that reads
    # the band.
    from SilkMachinery import split_end
    n = 0
    for splits in _subsets([0.1, 0.3, 0.5, 0.7, 0.9]):
        for ss in (0, 1):
            n += 1
            classified = any(split_end(v) == ss for v in splits)
            got = split_at_end(splits, ss)
            if classified != (got is not None):
                errors.append("split_at_end(%s, %d) = %r, but split_end says "
                              "this end %s a split"
                              % (_fmt(splits), ss, got,
                                 "has" if classified else "has no"))
            if got is not None and split_end(got) != ss:
                errors.append("split_at_end(%s, %d) = %g, which split_end "
                              "puts at end %r" % (_fmt(splits), ss, got,
                                                 split_end(got)))
    checks.append("%d (splits, end) layouts: split_at_end and split_end "
                  "classify the same end for every one of them -- the limit "
                  "counts with the same rule that reads the band" % n)
    return {"pass": not errors, "errors": errors, "checks": checks}


def test_blend_reads_the_user_band_width(doc):
    """#64, the defect: the blend used to ASSERT its default 0.1 / 0.9
    instead of READING the patch's split, so a user width never took
    effect — it accumulated beside the default ([0.1] + user 0.2 ->
    [0.1, 0.2], band still 0.1 wide, and on a patch that already had a
    split at that end the band grew a second cell and refused).

    Now the patch owns its splits and the blend consumes them: a user
    width survives the recompute with NO duplicate value added, it
    becomes the band's actual width (verified against the base surface,
    not just a cell index), and the blend's poles move onto it."""
    from SilkMachinery import band_cells
    from SilkWorkflowOps import create_blend_by_edge
    from Tests.test_patch_touched import _build_two_patch_pair

    pa, pb, seam = _build_two_patch_pair(doc)
    blend = create_blend_by_edge(seam)
    doc.recompute()
    errors, checks = [], []

    ea, ss_a, prop_a, _ = _band_axis(pa, pb)
    eb, ss_b, prop_b, _ = _band_axis(pb, pa)
    if ea is None or eb is None:
        return {"pass": False,
                "errors": ["fixture: no shared seam resolved"],
                "checks": checks}

    default_poles = [tuple(q) for q in (blend.Poles or [])]
    if len(default_poles) != 24:
        return {"pass": False,
                "errors": ["default blend has %d poles, want 24"
                           % len(default_poles)], "checks": checks}
    default_a = sorted(float(v) for v in (getattr(pa, prop_a) or []))
    checks.append("default: %s seam %s/side %d -> %s = %s"
                  % (pa.Name, ea, ss_a, prop_a, _fmt(default_a)))

    # the user moves ONE side's band width (0.1 default -> 0.3)
    user = 0.3 if ss_a == 0 else 0.7
    with _Capture() as cap:
        setattr(pa, prop_a, [user])
        doc.recompute()

    stored = sorted(float(v) for v in (getattr(pa, prop_a) or []))
    checks.append("after setting %s.%s = %s and recomputing: %s = %s"
                  % (pa.Name, prop_a, _fmt([user]), prop_a, _fmt(stored)))
    if stored != [user]:
        errors.append("%s.%s = %s after recompute, want exactly %s — the "
                      "blend re-asserted its default beside the user's "
                      "width" % (pa.Name, prop_a, _fmt(stored), _fmt([user])))
    errors += ["console error: %s" % e for e in cap.errors]

    # the width is the band's ACTUAL parameter extent ...
    iv = _band_interval(pa, prop_a, ss_a)
    width = iv[1] - iv[0]
    if abs(width - abs(user - (0.0 if ss_a == 0 else 1.0))) > 1e-9:
        errors.append("band interval on %s is %r, want width %g"
                      % (pa.Name, iv, abs(user - (0.0 if ss_a == 0 else 1.0))))
    idxs = band_cells(pa, ea, ss_a)
    if len(idxs) != 1:
        errors.append("%s band now covers %r cells, want exactly 1"
                      % (pa.Name, idxs))
    else:
        dev = _band_corners_on_surface(pa, idxs[0], *_band_box(pa, ea, ss_a))
        if dev > 1e-9:
            errors.append("band cell corners deviate %.3e from the base "
                          "surface over interval %r" % (dev, iv))
        checks.append("band on %s = cell %r over %r (width %g), corners on "
                      "the base surface to %.1e" % (pa.Name, idxs, iv, width,
                                                    dev))

    # ... and the blend's poles moved onto it.
    new_poles = [tuple(q) for q in (blend.Poles or [])]
    if len(new_poles) != 24:
        errors.append("blend has %d poles after the width change, want 24"
                      % len(new_poles))
    elif new_poles == default_poles:
        errors.append("blend poles did NOT move after the user set the band "
                      "width — the blend is still reading its default")
    else:
        dev = max((Vector(*a) - Vector(*b)).Length
                  for a, b in zip(default_poles, new_poles))
        if dev <= 1e-6:
            errors.append("blend poles moved only %.3e — not onto the new band"
                          % dev)
        checks.append("blend rebuilt on the new band: 24 poles, max move "
                      "%.3f mm" % dev)
    return {"pass": not errors, "errors": errors, "checks": checks}


def test_band_widths_of_both_sides_are_independent(doc):
    """Each side of the seam is read on its own patch, so a width set on
    one leaves the other side's split list exactly as the blend wrote
    it — in both directions, and each patch keeps its own user width."""
    from SilkWorkflowOps import create_blend_by_edge
    from Tests.test_patch_touched import _build_two_patch_pair

    pa, pb, seam = _build_two_patch_pair(doc)
    blend = create_blend_by_edge(seam)
    doc.recompute()
    errors, checks = [], []

    _, ss_a, prop_a, _ = _band_axis(pa, pb)
    _, ss_b, prop_b, _ = _band_axis(pb, pa)
    def va(v):
        return v if ss_a == 0 else 1.0 - v
    def vb(v):
        return v if ss_b == 0 else 1.0 - v

    base_b = sorted(float(v) for v in (getattr(pb, prop_b) or []))
    checks.append("defaults: %s.%s = %s, %s.%s = %s"
                  % (pa.Name, prop_a, _fmt(getattr(pa, prop_a)), pb.Name,
                     prop_b, _fmt(getattr(pb, prop_b))))

    # A only
    setattr(pa, prop_a, [va(0.25)])
    doc.recompute()
    doc.recompute()
    if sorted(float(v) for v in (getattr(pa, prop_a) or [])) != [va(0.25)]:
        errors.append("A's width did not stick: %s.%s = %s"
                      % (pa.Name, prop_a, _fmt(getattr(pa, prop_a))))
    if sorted(float(v) for v in (getattr(pb, prop_b) or [])) != base_b:
        errors.append("setting A's width disturbed B: %s.%s = %s, want %s"
                      % (pb.Name, prop_b, _fmt(getattr(pb, prop_b)),
                         _fmt(base_b)))
    if len(blend.Poles or []) != 24:
        errors.append("blend lost poles after A's width change (%d)"
                      % len(blend.Poles or []))
    checks.append("A width %g: A reads it, B still %s, blend has 24 poles"
                  % (0.25, _fmt(base_b)))

    # now B too, with a different width — A must not be re-asserted
    setattr(pb, prop_b, [vb(0.4)])
    doc.recompute()
    doc.recompute()
    if sorted(float(v) for v in (getattr(pa, prop_a) or [])) != [va(0.25)]:
        errors.append("setting B's width disturbed A: %s.%s = %s"
                      % (pa.Name, prop_a, _fmt(getattr(pa, prop_a))))
    if sorted(float(v) for v in (getattr(pb, prop_b) or [])) != [vb(0.4)]:
        errors.append("B's width did not stick: %s.%s = %s"
                      % (pb.Name, prop_b, _fmt(getattr(pb, prop_b))))
    if len(blend.Poles or []) != 24:
        errors.append("blend lost poles after both widths changed (%d)"
                      % len(blend.Poles or []))
    # and each side's band really is the width that side asked for
    for p, other, prop, ss, want_w in ((pa, pb, prop_a, ss_a, 0.25),
                                       (pb, pa, prop_b, ss_b, 0.4)):
        iv = _band_interval(p, prop, ss)
        if abs((iv[1] - iv[0]) - want_w) > 1e-9:
            errors.append("%s band interval %r, want width %g"
                          % (p.Name, iv, want_w))
    checks.append("both widths set independently: A=%g B=%g, blend still 24 "
                  "poles" % (0.25, 0.4))
    return {"pass": not errors, "errors": errors, "checks": checks}


def test_corner_patch_band_widths_stay_per_seam(doc):
    """The four-patch corner must not regress: each patch legitimately
    carries TWO splits, one per seam side (on its two axes), and every
    strip still resolves to exactly ONE band cell. A non-default width
    on ONE seam of a corner patch leaves that seam's split list alone —
    the OTHER seam's band axis is a different list and is not touched."""
    from SilkMachinery import band_cells, patch_side
    from Tests.test_blend_corner_splits import EXPECTED_SPLITS

    model = cm.build_corner_model(doc)
    p44 = model["patches"]["Patch44"]
    errors, checks = [], []

    for name, want_u, want_v in EXPECTED_SPLITS:
        p = model["patches"][name]
        got = (sorted(float(v) for v in (p.USplits or [])),
               sorted(float(v) for v in (p.VSplits or [])))
        if got != (sorted(want_u), sorted(want_v)):
            errors.append("fixture: %s splits %s, want %s"
                          % (name, got, (want_u, want_v)))
    checks.append("default ring: all 4 corner patches carry both splits "
                  "(%s)" % "; ".join(
                      "%s U=%s V=%s" % (n, u, v) for n, u, v in EXPECTED_SPLITS))

    # the two seams meeting at Patch44, as the strips see them
    sides = []
    for bname, st in model["strips"].items():
        if st.PatchA is not p44 and st.PatchB is not p44:
            continue
        other = st.PatchB if st.PatchA is p44 else st.PatchA
        e, ss = patch_side(p44, other, 0.01)
        sides.append((bname, other, e, ss))
    if len(sides) != 2:
        return {"pass": False,
                "errors": ["fixture: Patch44 meets %d strips, want 2"
                           % len(sides)], "checks": checks}
    axes = {("VSplits" if e[0] == "U" else "USplits") for _, _, e, _ in sides}
    if len(axes) != 2:
        return {"pass": False,
                "errors": ["fixture: both seams of Patch44 use the same band "
                           "axis %s" % axes], "checks": checks}

    b_target, other_t, e_t, ss_t = sides[0]
    b_other, other_o, e_o, ss_o = sides[1]
    prop_t = "VSplits" if e_t[0] == "U" else "USplits"
    prop_o = "VSplits" if e_o[0] == "U" else "USplits"
    before_o = sorted(float(v) for v in (getattr(p44, prop_o) or []))
    cells_before = {bn: band_cells(p44, e, ss) for bn, _, e, ss in sides}
    strips_before = {bn: [tuple(q) for q in model["strips"][bn].Poles or []]
                     for bn in model["strips"]}
    checks.append("Patch44 seams: %s -> %s (side %d), %s -> %s (side %d); "
                  "band axes %s / %s" % (b_target, e_t, ss_t, b_other, e_o,
                                         ss_o, prop_t, prop_o))

    user = 0.3 if ss_t == 0 else 0.7
    with _Capture() as cap:
        setattr(p44, prop_t, [user])
        doc.recompute()
    errors += ["console error: %s" % e for e in cap.errors]

    stored = sorted(float(v) for v in (getattr(p44, prop_t) or []))
    checks.append("Patch44.%s set to %s and recomputed -> %s"
                  % (prop_t, _fmt([user]), _fmt(stored)))
    if stored != [user]:
        errors.append("Patch44.%s = %s after the width change, want %s "
                      "(the blend re-asserted its default)"
                      % (prop_t, _fmt(stored), _fmt([user])))

    # the OTHER seam is untouched, on its own axis
    if sorted(float(v) for v in (getattr(p44, prop_o) or [])) != before_o:
        errors.append("Patch44.%s = %s, want %s — the other seam's band axis "
                      "was disturbed" % (prop_o,
                                          _fmt(getattr(p44, prop_o)),
                                          _fmt(before_o)))

    # every strip still resolves to exactly one band cell
    for bn, other, e, ss in sides:
        got = band_cells(p44, e, ss)
        if len(got) != 1:
            errors.append("%s band on Patch44 covers %r cells, want 1"
                          % (bn, got))
        elif got != cells_before[bn]:
            checks.append("%s band cell %r -> %r (same cell, new width)"
                          % (bn, cells_before[bn], got))
    # and the whole ring is still built
    for bn, st in model["strips"].items():
        if len(st.Poles or []) != 24:
            errors.append("%s has %d poles after the width change, want 24"
                          % (bn, len(st.Poles or [])))
    checks.append("all 4 ring strips still carry 24 poles (one band cell "
                  "each on Patch44)")
    return {"pass": not errors, "errors": errors, "checks": checks}


def test_default_band_split_decision_is_unchanged(doc):
    """With no user choice, #64 changes nothing: for every split list the
    fixtures can produce ({0.1, 0.5, 0.9}, every subset, both axes, both
    ends) the new end-classification rule writes the default EXACTLY when
    the old `no split within 1e-9 of 0.1 / 0.9` test did. The default
    path is therefore byte-identical, and a fresh ring still materializes
    the documented 0.1 / 0.9 layout."""
    from SilkMachinery import split_at_end

    errors, checks = [], []
    subsets = _subsets([0.1, 0.5, 0.9])
    n = 0
    for splits in subsets:
        for ss in (0, 1):
            default = 0.9 if ss else 0.1
            new_writes = split_at_end(splits, ss) is None
            old_writes = all(abs(float(v) - default) > 1e-9 for v in splits)
            n += 1
            if new_writes != old_writes:
                errors.append("splits %s side %d: new rule writes=%r, old "
                              "rule writes=%r" % (_fmt(splits), ss,
                                                  new_writes, old_writes))
    checks.append("%d (splits, end) layouts over every subset of "
                  "{0.1, 0.5, 0.9}: write-the-default decision identical to "
                  "the pre-#64 rule" % n)

    # ... and on real geometry, a fresh ring still lands on 0.1 / 0.9.
    from Tests.test_blend_corner_splits import EXPECTED_SPLITS
    model = cm.build_corner_model(doc)
    for name, want_u, want_v in EXPECTED_SPLITS:
        p = model["patches"][name]
        got = (sorted(float(v) for v in (p.USplits or [])),
               sorted(float(v) for v in (p.VSplits or [])))
        if got != (sorted(want_u), sorted(want_v)):
            errors.append("default ring: %s splits %s, want %s"
                          % (name, got, (want_u, want_v)))
    for bname, st in model["strips"].items():
        if len(st.Poles or []) != 24:
            errors.append("default ring: %s has %d poles, want 24"
                          % (bname, len(st.Poles or [])))
    checks.append("fresh 2x2 ring still materializes the documented "
                  "0.1 / 0.9 layout on all 4 patches, 24 poles per strip")
    return {"pass": not errors, "errors": errors, "checks": checks}


# ---- 2: the refusal is actionable ---------------------------------------

def test_multi_cell_band_refusal_names_patch_and_values(doc):
    """A band that spans more than one subgrid cell still refuses (the
    blend supports single-cell bands only) — but the message now carries
    what a user needs to fix it: the patch, the seam and its side, both
    axis split lists, how many cells each makes, which are corner cells,
    and the single split value that leaves a one-cell band.

    Fixture: the corner PAIR (two patches, one strip). Patch44's
    seam-parallel axis (V, the axis running ALONG the shared seam) gets
    [0.5, 0.8]: three intervals, the 1-end one is a corner cell, two
    cells left in the band. #76 turned the old [0.85, 0.95] fixture into
    an illegal write (two splits above 0.5, which is now refused), and
    the substitution is better than a renaming: the extra cell here comes
    from a plain MID-SURFACE split, which the limit permits -- so this is
    a band the rule still cannot make single-cell, and it says so."""
    from Tests.corner_model import build_corner_pair
    from SilkMachinery import band_cells

    model = build_corner_pair(doc)
    p44 = model["patches"]["Patch44"]
    strip = model["strip"]

    errors, checks = [], []

    with _Capture() as cap:
        p44.VSplits = [0.5, 0.8]
        doc.recompute()

    idxs = band_cells(p44, "V1", 1)
    checks.append("band_cells(Patch44, V1, 1) with VSplits=[0.5, 0.8] "
                  "= %r (2 cells)" % (idxs,))
    if len(idxs) != 2:
        errors.append("fixture did not produce a multi-cell band: %r" % idxs)

    msg = "\n".join(cap.errors)
    want_fragments = [
        ("patch name", "Patch44"),
        ("cell count", "covers 2 subgrid cells"),
        ("seam + side", "seam V1 (band at parametric 1)"),
        ("band axis value", "band axis USplits = [0.9]"),
        ("offending axis values", "seam-parallel axis VSplits = [0.5, 0.8]"),
        ("interval count", "3 interval(s)"),
        ("corner cells excluded", "corner cell(s) [2] excluded"),
        ("cells left", "2 left in the band"),
        ("valid fix", "Patch44.VSplits = [0.8]"),
    ]
    for label, frag in want_fragments:
        if frag not in msg:
            errors.append("refusal message does not name the %s (%r); got:\n%s"
                          % (label, frag, msg))
    checks.append("refusal message names %d facts (patch, seam, both "
                  "split lists, interval count, corner cells, the fix)"
                  % len(want_fragments))

    # The refusal is still a refusal: no crash, and the object survives.
    if getattr(strip, "object_type", None) not in ("Blend", "BlendStrip"):
        errors.append("strip lost its type after the refusal (%r)"
                      % getattr(strip, "object_type", None))
    checks.append("no crash; strip still a %s" % getattr(strip, "object_type",
                                                         None))

    # And the suggested fix actually works.
    with _Capture() as cap2:
        p44.VSplits = [0.8]
        doc.recompute()
    if cap2.errors:
        errors.append("the suggested fix still errors: %s" % cap2.errors)
    fixed = band_cells(p44, "V1", 1)
    if len(fixed) != 1:
        errors.append("with VSplits=[0.8] the band is %r, want 1 cell"
                      % (fixed,))
    if len(strip.Poles or []) != 24:
        errors.append("after the suggested fix the strip has %d poles, "
                      "want 24" % len(strip.Poles or []))
    checks.append("applying the suggested fix (VSplits=[0.8]) rebuilds the "
                  "strip: 24 poles, one band cell %r, no errors" % (fixed,))
    return {"pass": not errors, "errors": errors, "checks": checks}


# ---- 3: splits normalized on set ---------------------------------------

def test_splits_normalized_on_set(doc):
    """`0 < u1 < u2 < 1` (same for v) is pinned ON THE STORED PROPERTY:
    whatever goes in, what comes back out is exactly what the geometry
    used, and the console says what was rejected and why (#53 display
    residue — before this the property editor kept showing 0.0 / 1.0 /
    duplicates that the geometry had already dropped).

    The console word has a THRESHOLD (#62 follow-up): a write that loses
    EVERY value ([0], [1.5]) is the suspicious case and is reported, but
    a PARTIAL correction — a reorder, a duplicate, one mistyped value
    among good ones — is corrected silently. The property editor commits
    a bare `0` while `0.2` is still being typed, so warning on every
    discarded value scolded input the editor never meant to send."""
    from Tests.test_seam_resolver import _square_patch

    p = _square_patch(doc, "Norm")
    errors, checks = [], []

    def cells():
        return len(p.Proxy._subgrids)

    def stored(prop):
        return [round(float(v), 12) for v in (getattr(p, prop) or [])]

    cases = [
        # (written, expected stored, expected cell count with VSplits [])
        ([0.7, 0.0, 0.2, 1.0, -0.5, 2.0, 0.2], [0.2, 0.7], 3),
        ([0.5, 0.5], [0.5], 2),
        ([0.9, 0.2, 0.5], [0.2, 0.5, 0.9], 4),   # unsorted in; 3 is legal (#76)
        ([0.0, 1.0], [], 0),                     # nothing survives -> loud
        ([0.0, 0.25, 1.0], [0.25], 2),           # a partial fix -> silent
        ([0.5], [0.5], 2),                       # a legal write: no-op
    ]
    for written, want, n_cells in cases:
        with _Capture() as cap:
            p.USplits = list(written)
        got = stored("USplits")
        if got != want:
            errors.append("USplits = %s stored as %s, want %s"
                          % (_fmt(written), _fmt(got), _fmt(want)))
        if cells() != n_cells:
            errors.append("USplits = %s produced %d cells, want %d"
                          % (_fmt(written), cells(), n_cells))
        if want and any(not 0.0 < v < 1.0 for v in got):
            errors.append("stored USplits %s escapes (0, 1)" % _fmt(got))
        if len(set(got)) != len(got) or got != sorted(got):
            errors.append("stored USplits %s is not strictly increasing"
                          % _fmt(got))
        msg = "\n".join(cap.errors)
        # The threshold: a NON-EMPTY input that discards every one of its
        # values is reported, naming the values; anything else is
        # corrected in silence.
        if written and not want:
            rejected = [v for v in written if not 0.0 < v < 1.0]
            if not msg.strip():
                errors.append("USplits = %s lost every value and said "
                              "nothing" % _fmt(written))
            elif not all(("%g" % v) in msg for v in rejected):
                errors.append("USplits = %s: rejected values %s not all "
                              "named in the console message:\n%s"
                              % (_fmt(written), rejected, msg))
        elif msg.strip():
            errors.append("USplits = %s was corrected to %s and reported "
                          "anyway (only a wholesale discard warns):\n%s"
                          % (_fmt(written), _fmt(want), msg))
    checks.append("%d USplits writes: stored list always sorted, deduped, "
                  "strictly inside (0, 1); cell count always matches it; "
                  "only a wholesale discard is reported" % len(cases))

    # The V axis is normalized the same way, independently -- and the
    # same threshold holds there.
    with _Capture() as cap:
        p.VSplits = [0.0, 0.25, 1.0, 0.75]
    if stored("VSplits") != [0.25, 0.75]:
        errors.append("VSplits stored as %s, want [0.25, 0.75]"
                      % _fmt(stored("VSplits")))
    if cap.errors:
        errors.append("a PARTLY corrected VSplits reported: %s" % cap.errors)
    with _Capture() as cap:
        p.VSplits = [1.0, 1.5]
    if stored("VSplits") != []:
        errors.append("VSplits stored as %s, want []"
                      % _fmt(stored("VSplits")))
    if not any("VSplits" in e for e in cap.errors):
        errors.append("a WHOLLY discarded VSplits said nothing: %s"
                      % cap.errors)
    want_cells = (len(stored("USplits")) + 1) * (len(stored("VSplits")) + 1)
    if cells() != want_cells:
        errors.append("USplits=%s x VSplits=%s gives %d cells, want %d"
                      % (_fmt(stored("USplits")), _fmt(stored("VSplits")),
                         cells(), want_cells))
    checks.append("VSplits normalized independently and SILENTLY when only "
                  "partly corrected, loudly when wholly discarded; "
                  "%dx%d = %d cells matches the stored lists"
                  % (len(stored("USplits")) + 1,
                     len(stored("VSplits")) + 1, cells()))

    # Geometry agrees with the stored list: every interval is a cell and
    # the object is valid + non-null.
    if p.Shape.isNull() or not p.Shape.isValid():
        errors.append("patch shape invalid after normalization")
    checks.append("patch shape valid, non-null after the writes")

    # A blend writing its own 0.1 / 0.9 band split is a no-op (already
    # normalized) and must not report anything.
    from Tests.corner_model import build_corner_pair
    pair = build_corner_pair(doc)
    with _Capture() as cap:
        pair["strip"].touch()
        doc.recompute()
    p44 = pair["patches"]["Patch44"]
    if sorted(float(v) for v in p44.USplits) != [0.9]:
        errors.append("blend band split drifted to %s"
                      % _fmt(p44.USplits))
    if cap.errors:
        errors.append("the blend's own band-split write reported: %s"
                      % cap.errors)
    checks.append("the blend's own band split (USplits=[0.9]) passes "
                  "through normalization untouched, silently")
    return {"pass": not errors, "errors": errors, "checks": checks}


# ---- 4: #76 — the one-split-per-end limit, in code ----------------------

def test_over_limit_splits_are_refused_on_the_property(doc):
    """#76: "at most one split below 0.5 and at most one above 0.5, per
    axis" was a SENTENCE in a refusal message. Here it is a rule the
    property path enforces.

    The rule is finer than "at most two", because that is what the
    geometry can hold: a split is the FAR EDGE of one band's interval and
    an axis has one interval per end, so `[0.2, 0.8]` is two bands (one per
    end, legal) while `[0.2, 0.3]` is two bands that both want to be at the
    SAME end. 0.5 marks neither end, so `[0.1, 0.5, 0.9]` — three splits,
    and what `ensure_band_split` writes onto an axis that already carried a
    plain mid-surface subdivision — is LEGAL and stays legal.

    A refusal is a REFUSAL, not a silent correction: which of two
    same-side splits to keep is a semantic guess (it decides the band
    width), so the axis keeps the list it last accepted, unchanged, and the
    geometry does not move at all."""
    from SilkMachinery import split_limit_problem
    from Tests.test_seam_resolver import _square_patch

    errors, checks = [], []

    # -- the rule itself, as data ---------------------------------------
    legal = [[], [0.5], [0.2], [0.8], [0.2, 0.8], [0.05, 0.95],
             [0.1, 0.5, 0.9], [0.2, 0.5], [0.5, 0.9]]
    illegal = [[0.2, 0.3], [0.2, 0.45, 0.9], [0.2, 0.3, 0.4],
               [0.85, 0.95], [0.1, 0.85, 0.95], [0.2, 0.3, 0.9, 0.8]]
    for splits in legal:
        problem = split_limit_problem(splits)
        if problem is not None:
            errors.append("%s is legal (one below 0.5, one above, 0.5 to "
                          "neither) but the rule refuses it: %s"
                          % (_fmt(splits), problem))
    for splits in illegal:
        if split_limit_problem(splits) is None:
            errors.append("%s is over the limit (more than one split at the "
                          "same end of the axis) and nothing says so"
                          % _fmt(splits))
    checks.append("%d legal and %d over-limit lists classified by the one "
                  "rule, including 0.5 counting for neither end"
                  % (len(legal), len(illegal)))

    # the message names the values it refuses — a refusal the user cannot
    # act on is half a refusal
    msg = split_limit_problem([0.2, 0.45, 0.9])
    if msg is None:
        errors.append("split_limit_problem([0.2, 0.45, 0.9]) said nothing")
    else:
        for v in (0.2, 0.45, 0.9):
            if "%g" % v not in msg:
                errors.append("the refusal for [0.2, 0.45, 0.9] does not "
                              "name %g: %s" % (v, msg))
    checks.append("the refusal message names every value on the axis")

    # -- and the same rule through the PROPERTY path --------------------
    p = _square_patch(doc, "Limit")

    def stored():
        return [round(float(v), 12) for v in (p.USplits or [])]

    def cells():
        return len(p.Proxy._subgrids)

    cases = [
        # (written, stored after, accepted?)
        ([0.2, 0.8], [0.2, 0.8], True),        # one per end: the 2-split band
        ([0.1, 0.5, 0.9], [0.1, 0.5, 0.9], True),  # THREE, legal: 0.5 is neither
        ([0.5], [0.5], True),
        # ...and each of these puts the axis back to that [0.5]: a refusal
        # is not a correction, it is a refusal.
        ([0.2, 0.45, 0.9], [0.5], False),      # two below
        ([0.3, 0.45, 0.9], [0.5], False),      # two below, again
        ([0.85, 0.95], [0.5], False),          # two above
        ([0.2, 0.3], [0.5], False),            # two below, straddling nothing
        ([0.3, 0.6], [0.3, 0.6], True),
        # ...and a refusal from an EMPTY axis leaves it empty, so the
        # over-limit list never becomes the "before" of the next one.
        ([], [], True),
        ([0.2, 0.45, 0.9], [], False),
        ([0.2, 0.8], [0.2, 0.8], True),
    ]
    for written, want, accepted in cases:
        with _Capture() as cap:
            p.USplits = list(written)
        got = stored()
        if got != want:
            errors.append("USplits = %s stored as %s, want %s"
                          % (_fmt(written), _fmt(got), _fmt(want)))
        # geometry follows the stored list and NOTHING ELSE: a refusal
        # moves no cell, so nothing downstream can be left stale. (No
        # splits at all is no subgrids at all, not one cell.)
        n_splits = len(got) + len(p.VSplits or [])
        want_cells = (len(got) + 1) * (len(p.VSplits) + 1) if n_splits else 0
        if cells() != want_cells:
            errors.append("USplits = %s left %d cells, want %d (the stored "
                          "list is %s)" % (_fmt(written), cells(),
                                           want_cells, _fmt(got)))
        said = "\n".join(cap.errors)
        if accepted and said.strip():
            errors.append("USplits = %s is legal and was reported anyway: %s"
                          % (_fmt(written), said))
        if not accepted:
            if not said.strip():
                errors.append("USplits = %s was refused in silence"
                              % _fmt(written))
            elif not all(("%g" % v) in said for v in written):
                errors.append("the refusal for %s does not name every value "
                              "it refused:\n%s" % (_fmt(written), said))
    checks.append("%d USplits writes through the property: legal lists "
                  "stored and silent, over-limit lists refused with the "
                  "axis left exactly as it was and the cells unmoved"
                  % len(cases))
    return {"pass": not errors, "errors": errors, "checks": checks}


def test_over_limit_refusal_is_visible_on_the_object(doc):
    """The refusal has to be VISIBLE. The failure #76 exists to prevent is
    not a crash: the blend refuses a band it cannot build, leaves its
    Poles byte-identical to the previous run, and the Patch reports
    `State ['Up-to-date']`, `isValid() True`, `getStatusString() 'Valid'`
    — no tree marker, no stale flag, and a surface on screen that no
    longer belongs to the inputs.

    So the refusal is surfaced the way FreeCAD surfaces a property error:
    the object is left INVALID, carrying the message. Asserted on the
    state the tree reads, not on a printed line — plus the control (a
    patch nobody refused is valid) so the flag cannot pass by being
    always-on, and the recovery (a legal write clears it), so it cannot
    pass by being permanent."""
    from Tests.test_seam_resolver import _square_patch

    errors, checks = [], []
    p = _square_patch(doc, "Visible")

    # control: an ordinary object is up to date and valid
    if "Invalid" in p.State:
        errors.append("a freshly built patch is already Invalid (%r)"
                      % (p.State,))
    if p.isValid() is not True:
        errors.append("a freshly built patch reports isValid()=%r, want True"
                      % (p.isValid(),))
    if p.getStatusString() != "Valid":
        errors.append("a freshly built patch reports status %r, want 'Valid'"
                      % p.getStatusString())
    checks.append("control: the untouched patch is Up-to-date / valid / "
                  "'Valid' -- so the flag below is not simply always-on")

    p.USplits = [0.2, 0.8]
    doc.recompute()
    p.USplits = [0.2, 0.45, 0.9]       # two splits below 0.5: refused
    doc.recompute()                    # ...and still refused on the next pass

    for label, probe in (("State", lambda: "Invalid" in p.State),
                         ("isValid()", lambda: p.isValid() is False),
                         ("getStatusString()",
                          lambda: ("USplits" in p.getStatusString()
                                   and "0.45" in p.getStatusString()))):
        if not probe():
            errors.append("after a refused USplits write the patch's %s "
                          "does not show the refusal (State=%r, isValid=%r, "
                          "status=%r)" % (label, p.State, p.isValid(),
                                          p.getStatusString()))
    if "Up-to-date" in p.State:
        errors.append("the refused patch still claims to be Up-to-date "
                      "(State=%r) -- that is exactly the #76 failure mode"
                      % (p.State,))
    checks.append("after the refused write: State %r, isValid()=%r, status "
                  "'%s' -- and it survives a further doc.recompute(), so it "
                  "is not a transient Touched flag"
                  % (p.State, p.isValid(), p.getStatusString()))

    # The refusal must not cost the user their geometry: the splits did not
    # change, so the surface on screen is still the right one.
    if p.Shape.isNull() or not p.Shape.isValid():
        errors.append("the refused write destroyed the patch shape")
    checks.append("the refused write leaves the patch shape intact -- the "
                  "geometry is unchanged because the splits are")

    # ...and a legal write clears the flag: the object recovers.
    p.USplits = [0.2, 0.8]
    doc.recompute()
    if "Invalid" in p.State or p.isValid() is not True:
        errors.append("a legal USplits write did not clear the refusal "
                      "(State=%r, isValid=%r)" % (p.State, p.isValid()))
    if "Up-to-date" not in p.State:
        errors.append("after the fix the patch is not Up-to-date (%r)"
                      % (p.State,))
    checks.append("a legal write after the refusal clears it: State %r, "
                  "isValid()=%r" % (p.State, p.isValid()))
    return {"pass": not errors, "errors": errors, "checks": checks}


def test_band_writes_can_never_go_over_the_limit(doc):
    """The rule must permit what the CODE writes, or #76 breaks the
    workbench. Two writers of a split exist: `ensure_band_split` (0.1 /
    0.9) and the panel's band editor (a user width, stored as the width at
    the 0-end and 1 - width at the 1-end). Both write only when the end
    carries no split at all, which is precisely when the write cannot be
    the second split at that end — so neither can trip the rule, and
    `[0.1, 0.5, 0.9]` (a plain mid-surface split plus a band at each end)
    is a layout the blend legitimately produces."""
    from SilkMachinery import split_at_end, split_limit_problem

    errors, checks = [], []
    subsets = _subsets([0.1, 0.5, 0.9])

    def write(cur, ss, width):
        """SilkBlend.ensure_band_split's write / the panel's, in shape: the
        caller means a band WIDTH, the property keeps the parametric split
        at this end (the width at the 0 end, 1 - width at the 1 end, #70),
        and the write only happens when the end carries no split at all."""
        cur = list(cur)
        if split_at_end(cur, ss) is not None:
            return cur
        stored = width if ss == 0 else 1.0 - width
        return sorted(cur + [stored])

    n = 0
    for splits in subsets:
        for ss in (0, 1):
            # the blend's own default, then user widths at each end
            for width in (0.1, 0.45, 0.05, 0.2, 0.49):
                after = write(splits, ss, width)
                n += 1
                problem = split_limit_problem(after)
                if problem is not None:
                    errors.append("writing a %g-wide band at end %d of %s "
                                  "leaves %s, which the rule refuses: %s"
                                  % (width, ss, _fmt(splits), _fmt(after),
                                     problem))
    checks.append("%d (start, end, width) writes from every subset of "
                  "{0.1, 0.5, 0.9}: none of them can produce an over-limit "
                  "axis" % n)

    # and on real geometry: a four-patch corner ring, where each patch
    # carries a band at BOTH ends of BOTH axes -- the layout the rule has
    # to survive.
    model = cm.build_corner_model(doc)
    worst = 0
    for name, patch in model["patches"].items():
        for prop in ("USplits", "VSplits"):
            vals = [float(v) for v in (getattr(patch, prop) or [])]
            worst = max(worst, len(vals))
            problem = split_limit_problem(vals)
            if problem is not None:
                errors.append("%s.%s = %s is over the limit: %s"
                              % (name, prop, _fmt(vals), problem))
    checks.append("the 4-patch corner ring: every axis of every patch is "
                  "within the limit (widest axis holds %d splits)" % worst)
    return {"pass": not errors, "errors": errors, "checks": checks}


ALL_TESTS = [
    test_band_cells_identical_to_legacy_on_default_splits,
    test_band_cells_generalizes_user_widths,
    test_corner_model_bands_follow_non_default_widths,
    test_split_at_end_picks_the_splits_own_end,
    test_blend_reads_the_user_band_width,
    test_band_widths_of_both_sides_are_independent,
    test_corner_patch_band_widths_stay_per_seam,
    test_default_band_split_decision_is_unchanged,
    test_multi_cell_band_refusal_names_patch_and_values,
    test_splits_normalized_on_set,
    test_over_limit_splits_are_refused_on_the_property,
    test_over_limit_refusal_is_visible_on_the_object,
    test_band_writes_can_never_go_over_the_limit,
]
