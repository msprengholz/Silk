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
   - test_blend_reasserts_its_default_band_width: what actually happens
     when a user moves a band width today (the blend puts its default
     back), pinned so the next ticket has a baseline to change.

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

NOTE on the oracle — a known gap, deliberately NOT closed here.
SilkChecks re-derives band_cells independently, on purpose ("the oracle
re-derives the object code's tables instead of importing them, so a bug
in the object code cannot hide itself"), and that copy still hard-codes
0.1 / 0.9. Consequence, demonstrated: a SETTLED, correct blend whose
seam-parallel axis carries a user width (e.g. Patch44.VSplits=[0.85] on
the corner pair, where no blend writes that axis) builds its 24 poles
from the correct single corner-free cell, yet check_blend derives a
two-cell band, fails to produce reference rows and reports "no shared
edge found" on B1/B2. Generalizing that independent copy is a
SilkChecks change, which this ticket scopes out — so it needs its own
ticket before any non-default band width can be oracle-checked. The
tests here therefore assert on band_cells, the strip's poles and the
hidden-cell sets, never on check_blend for a non-default width.
"""

import itertools

import FreeCAD

import Tests.corner_model as cm


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


def test_blend_reasserts_its_default_band_width(doc):
    """The band width is NOT a Blend property (#61 background): each
    seam's band split is written by the blend itself, at the fixed
    default width (0.1 / 0.9), additively. So a user-moved band width
    does not survive a document recompute — the blend puts its default
    back. When the second default lands on the SAME end of the
    seam-parallel axis as the user's width (Patch44 of the 2x2 corner
    model meets two seams, one writing each axis), the band then spans
    two cells and refuses.

    Pinned here as the current contract, together with what that refusal
    now reports: the patch, the seam, both split lists (the user's width
    AND the blend's default re-added), and the value that would fix it.
    Making the band width the user's is a design question for #62; until
    then it is simply not the user's to move."""
    from SilkMachinery import band_cells

    model = cm.build_corner_model(doc)
    p44 = model["patches"]["Patch44"]
    errors, checks = [], []

    if sorted(float(v) for v in p44.VSplits) != [0.9]:
        errors.append("fixture: Patch44.VSplits = %s, want [0.9]"
                      % _fmt(p44.VSplits))

    with _Capture() as cap:
        p44.VSplits = [0.85]
        doc.recompute()
    stored = sorted(float(v) for v in p44.VSplits)
    checks.append("after moving Patch44's V band width to 0.85 and "
                  "recomputing, Patch44.VSplits = %s" % _fmt(stored))
    if stored != [0.85, 0.9]:
        errors.append("expected the blend to re-assert its 0.9 default, got "
                      "%s" % _fmt(stored))

    idxs = band_cells(p44, "V1", 1)
    if len(idxs) != 2:
        errors.append("fixture did not produce a multi-cell band: %r" % idxs)
    msg = "\n".join(cap.errors)
    for label, frag in (("cell count", "covers 2 subgrid cells"),
                        ("seam", "seam V1 (band at parametric 1)"),
                        ("re-added default",
                         "seam-parallel axis VSplits = [0.85, 0.9]"),
                        ("corner cells", "corner cell(s) [2] excluded"),
                        ("fix (the split nearest the band's own side, so "
                         "the user's extra 0.85 is what goes)",
                         "Patch44.VSplits = [0.9]")):
        if frag not in msg:
            errors.append("refusal does not name the %s (%r); got:\n%s"
                          % (label, frag, msg))
    checks.append("refusal names the count, the seam, the re-added default, "
                  "the corner cells and the fix")

    # Graceful, as ever: every ring strip survives with its type.
    for bname, st in model["strips"].items():
        if getattr(st, "object_type", None) not in ("Blend", "BlendStrip"):
            errors.append("strip %s lost its type after the refusal (%r)"
                          % (bname, getattr(st, "object_type", None)))
    checks.append("refusal is graceful: all 4 ring strips survive")
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
    [0.85, 0.95]: three intervals, the 1-end one is a corner cell, two
    cells left in the band."""
    from Tests.corner_model import build_corner_pair
    from SilkMachinery import band_cells

    model = build_corner_pair(doc)
    p44 = model["patches"]["Patch44"]
    strip = model["strip"]

    errors, checks = [], []

    with _Capture() as cap:
        p44.VSplits = [0.85, 0.95]
        doc.recompute()

    idxs = band_cells(p44, "V1", 1)
    checks.append("band_cells(Patch44, V1, 1) with VSplits=[0.85, 0.95] "
                  "= %r (2 cells)" % (idxs,))
    if len(idxs) != 2:
        errors.append("fixture did not produce a multi-cell band: %r" % idxs)

    msg = "\n".join(cap.errors)
    want_fragments = [
        ("patch name", "Patch44"),
        ("cell count", "covers 2 subgrid cells"),
        ("seam + side", "seam V1 (band at parametric 1)"),
        ("band axis value", "band axis USplits = [0.9]"),
        ("offending axis values", "seam-parallel axis VSplits = [0.85, 0.95]"),
        ("interval count", "3 interval(s)"),
        ("corner cells excluded", "corner cell(s) [2] excluded"),
        ("cells left", "2 left in the band"),
        ("valid fix", "Patch44.VSplits = [0.95]"),
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
        p44.VSplits = [0.95]
        doc.recompute()
    if cap2.errors:
        errors.append("the suggested fix still errors: %s" % cap2.errors)
    fixed = band_cells(p44, "V1", 1)
    if len(fixed) != 1:
        errors.append("with VSplits=[0.95] the band is %r, want 1 cell"
                      % (fixed,))
    if len(strip.Poles or []) != 24:
        errors.append("after the suggested fix the strip has %d poles, "
                      "want 24" % len(strip.Poles or []))
    checks.append("applying the suggested fix (VSplits=[0.95]) rebuilds the "
                  "strip: 24 poles, one band cell %r, no errors" % (fixed,))
    return {"pass": not errors, "errors": errors, "checks": checks}


# ---- 3: splits normalized on set ---------------------------------------

def test_splits_normalized_on_set(doc):
    """`0 < u1 < u2 < 1` (same for v) is pinned ON THE STORED PROPERTY:
    whatever goes in, what comes back out is exactly what the geometry
    used, and the console says what was rejected and why (#53 display
    residue — before this the property editor kept showing 0.0 / 1.0 /
    duplicates that the geometry had already dropped)."""
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
        ([0.9, 0.3, 0.6], [0.3, 0.6, 0.9], 4),   # unsorted in
        ([0.0, 1.0], [], 0),                     # nothing survives
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
        rejected = [v for v in written if not 0.0 < v < 1.0]
        if rejected and not all(("%g" % v) in msg for v in rejected):
            errors.append("USplits = %s: rejected values %s not all named "
                          "in the console message:\n%s"
                          % (_fmt(written), rejected, msg))
        if len(written) != len(set(written)) and "repeated" not in msg:
            errors.append("USplits = %s: repeated values not reported:\n%s"
                          % (_fmt(written), msg))
        if not rejected and len(written) == len(set(written)) \
                and list(written) == sorted(written) and msg.strip():
            errors.append("USplits = %s is already legal but produced a "
                          "message:\n%s" % (_fmt(written), msg))
    checks.append("%d USplits writes: stored list always sorted, deduped, "
                  "strictly inside (0, 1); cell count always matches it"
                  % len(cases))

    # The V axis is normalized the same way, independently.
    with _Capture() as cap:
        p.VSplits = [0.0, 0.25, 1.0, 0.75]
    if stored("VSplits") != [0.25, 0.75]:
        errors.append("VSplits stored as %s, want [0.25, 0.75]"
                      % _fmt(stored("VSplits")))
    want_cells = (len(stored("USplits")) + 1) * (len(stored("VSplits")) + 1)
    if cells() != want_cells:
        errors.append("USplits=%s x VSplits=%s gives %d cells, want %d"
                      % (_fmt(stored("USplits")), _fmt(stored("VSplits")),
                         cells(), want_cells))
    checks.append("VSplits normalized independently: %s; %dx%d = %d cells "
                  "matches the stored lists"
                  % (_fmt(stored("VSplits")), len(stored("USplits")) + 1,
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


ALL_TESTS = [
    test_band_cells_identical_to_legacy_on_default_splits,
    test_band_cells_generalizes_user_widths,
    test_corner_model_bands_follow_non_default_widths,
    test_blend_reasserts_its_default_band_width,
    test_multi_cell_band_refusal_names_patch_and_values,
    test_splits_normalized_on_set,
]
