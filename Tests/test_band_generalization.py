"""
#61 — generalized band-edge corner-cell exclusion, an actionable band
refusal, and band-edge normalization on set. Restated for #82's two
named edges per axis.

Four groups of tests:

1. band_cells' corner-cell exclusion was hard-coded to the LITERAL
   values 0.1 / 0.9 ("a split sits near this end of the axis -> that
   end's cell is a corner cell, drop it"). A user-chosen width (0.2,
   0.85) fell through it silently, so a corner cell could be pulled
   into a band.
   - test_corner_cells_follow_the_end_that_carries_an_edge: an end's
     cell is a corner cell exactly when that END carries an edge, at
     any width, and nothing else is;
   - test_band_cells_generalizes_user_widths: at 0.2 / 0.85 (and
     0.3 / 0.7) the corner cell is still excluded — and provably is
     NOT what the old literal rule returned;
   - test_corner_model_bands_follow_non_default_widths: real 2x2 corner
     model geometry, every band width moved off 0.1 / 0.9 — every band
     still resolves to the same single corner-free cell;

1b. #64 — the band width is the USER'S. The blend reads the edge the
    patch already carries at the seam-perpendicular axis's end instead
    of asserting its own default beside it (no new Blend property; the
    patch owns its edges, the blend consumes them).
    - test_band_edge_is_named_for_its_own_end: #82's replacement for
      the end-classification rule -- `Split1` IS the 0 end's edge,
      `Split2` the 1 end's, with no threshold anywhere, and
      `band_cells`/`corner_cells` reading the same names;
    - test_blend_reads_the_user_band_width: a user width survives the
      recompute with no default re-asserted, is the band's ACTUAL
      parameter extent (checked against the base surface, not a cell
      index), and the blend's poles move onto it;
    - test_band_widths_of_both_sides_are_independent: setting one side's
      width leaves the other side's edge alone, in both directions;
    - test_corner_patch_band_widths_stay_per_seam: the four-patch corner
      keeps an edge per end per axis and one band cell per strip; a width
      on one seam does not disturb the other seam's band axis;
    - test_default_band_edge_decision_is_unchanged: the blend writes the
      default EXACTLY when the end carries no edge — the no-user-choice
      path is unchanged.

2. The band refusal names the patch, the seam, both named edges on each
   axis and what single edit would leave a one-cell band.
   - test_zero_cell_band_refusal_names_patch_and_values

3. #53 display residue: a mistyped edge stayed in the stored property
   while the geometry silently dropped it.
   - test_band_edges_normalized_on_set

4. #76 — the two-split cap is now a TYPE, not a check.
   - test_third_split_on_an_axis_is_not_expressible: there are two
     properties and each names its own end, so no write -- list or
     property -- can put a third split on an axis, and the two
     degenerate writes that ARE possible (out of range, inverted) are
     corrected and reported rather than left for the band to refuse.
   - test_a_band_is_one_cell_by_construction: the arithmetic that made
     a multi-cell band possible is gone -- each edge cuts one corner
     cell off the axis it is on, so exactly one cell is left.

NOTE on the oracle — the gap noted here was CLOSED by #63.
SilkChecks re-derives band_cells independently, on purpose ("the oracle
re-derives the object code's tables instead of importing them, so a bug
in the object code cannot hide itself"), and that copy still hard-coded
0.1 / 0.9 when this ticket was written. Consequence, demonstrated: a
SETTLED, correct blend whose seam-parallel axis carries a user width
(e.g. Patch44.VSplit2 = 0.85 on the corner pair, where no blend writes
that axis) builds its 24 poles from the correct single corner-free cell,
yet check_blend derived a two-cell band, failed to produce reference
rows and reported "no shared edge found" on B1/B2 — the oracle
disagreeing with correct geometry.

#63 generalized that independent copy with the same end rule, and #82
gave both copies the named edges to read.
"""

# --- manual tier ------------------------------------------------------
# This module's subject is an end-to-end rebuild / GUI drive /
# measurement sweep, so it is NOT in the default (fast) tier. Run it
# with `python3 Tests/run_all.py --manual` (or by name as a filter);
# Tests/test_manual_tier.py asserts it stays importable. See suite.py.
MANUAL = True

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
    """Minimal stand-in: band_cells reads nothing but the four named band
    edges (and band_diagnosis the Name), so the corner-cell RULE can be
    exercised over many layouts without building geometry.

    `u` / `v` are `(Split1, Split2)` pairs; the default is the neutral
    pair, "no band at either end"."""

    def __init__(self, u=(0.0, 1.0), v=(0.0, 1.0), name="Stub"):
        self.USplit1, self.USplit2 = u
        self.VSplit1, self.VSplit2 = v
        self.Name = name


# Sentinels: "no band at that end" is the property's OWN endpoint.
NO_BAND_1, NO_BAND_2 = 0.0, 1.0


def _legacy_band_cells(p, ea, ss):
    """The pre-#61 rule, verbatim — the 0.1 / 0.9 literals, driven by the
    two edges the layout would have written as a list.

    Kept only as the CONTROL the generalization is compared against: it
    is what a rule keyed to the two literal values would say about the
    same pair of ends. An end with no edge is the empty list."""
    us = [v for v in (p.USplit1, p.USplit2) if 0.0 < v < 1.0]
    vs = [v for v in (p.VSplit1, p.VSplit2) if 0.0 < v < 1.0]

    def ivs(ss_):
        s = sorted(set(ss_))
        return [(0.0, 1.0)] if not s else list(zip([0.0] + s, s + [1.0]))
    ivs_u, ivs_v = ivs(us), ivs(vs)
    nu, nv = len(ivs_u), len(ivs_v)
    if ea[0] == "U":
        b = (nv - 1) if ss else 0
        keep_u = set(range(nu))
        if any(abs(s - 0.1) < 1e-9 for s in us):
            keep_u.discard(0)
        if any(abs(s - 0.9) < 1e-9 for s in us):
            keep_u.discard(nu - 1)
        return [a * nv + b for a in sorted(keep_u)]
    a = (nu - 1) if ss else 0
    keep_v = set(range(nv))
    if any(abs(s - 0.1) < 1e-9 for s in vs):
        keep_v.discard(0)
    if any(abs(s - 0.9) < 1e-9 for s in vs):
        keep_v.discard(nv - 1)
    return [a * nv + b for b in sorted(keep_v)]


def _fmt_pair(pair):
    return "(%g, %g)" % tuple(pair)


# ---- 1a: the exclusion follows the named end ------------------------------

def test_corner_cells_follow_the_end_that_carries_an_edge(doc):
    """An interval is a corner cell exactly when the END it reaches from
    carries a band edge — first interval for `Split1`, last for `Split2`,
    and neither when that property holds its own endpoint (0.0 / 1.0).

    No value threshold anywhere: 0.5 is an ordinary edge for both ends
    now (it was "neither end's" under the pre-#82 classification, which
    is what made a 0.5 width unstorable and sent `[0.2, 0.4]` down the
    #81 path). The widths the workbench itself writes (0.1 / 0.9) and
    the user widths (0.2 / 0.85 / 0.45 / 0.05) are all just values."""
    from SilkMachinery import corner_cells, build_intervals

    errors, checks = [], []

    cases = [
        # ((Split1, Split2), intervals, expected excluded indices)
        ((0.2, 0.85), 3, {0, 2}),      # both ends marked -> first + last
        ((0.85, NO_BAND_2), 2, {0}),    # one edge, and it is the 0 END's --
        ((NO_BAND_1, 0.85), 2, {1}),    # ...the 0.85 in the other slot is
        ((0.2, NO_BAND_2), 2, {0}),     # the 1 end's. The NAME decides; a
        ((NO_BAND_1, 0.15), 2, {1}),    # value never has to be compared with
        ((0.5, NO_BAND_2), 2, {0}),     # the middle of the axis (#81).
        ((NO_BAND_1, 0.5), 2, {1}),     # the midpoint is an ORDINARY edge
        ((NO_BAND_1, NO_BAND_2), 1, set()),   # no edge, no corner cell
        ((NO_BAND_1, 0.9), 2, {1}),     # Split1 AT its sentinel: only 1 end
        ((0.1, NO_BAND_2), 2, {0}),     # Split2 AT its sentinel: only 0 end
    ]
    for pair, n, want in cases:
        got = corner_cells(pair[0], pair[1], n)
        if got != want:
            errors.append("corner_cells(%s, %d) = %r, want %r"
                          % (_fmt_pair(pair), n, sorted(got), sorted(want)))
        # the declared interval count must be the one the pair really
        # makes, or the case above would be asserting against a fiction
        if len(build_intervals(*pair)) != n:
            errors.append("corner_cells case %s claims %d intervals, the "
                          "pair really makes %d"
                          % (_fmt_pair(pair), n, len(build_intervals(*pair))))
    checks.append("corner_cells over %d named-edge layouts: the first cell "
                  "whenever Split1 carries an edge, the last whenever "
                  "Split2 does, and the 0.5 midpoint counted like any "
                  "other" % len(cases))

    # The 0.1 / 0.9 defaults -- the only widths the workbench writes --
    # still behave exactly as the literal rule they replaced.
    from SilkMachinery import band_cells
    n = 0
    for u, v in (((0.1, NO_BAND_2), (NO_BAND_1, 0.9)),
                 ((0.1, 0.9), (NO_BAND_1, 0.9))):
        p = _StubPatch(u, v, name="Default")
        for ea in ("U0", "U1", "V0", "V1"):
            for ss in (0, 1):
                got = band_cells(p, ea, ss)
                want = _legacy_band_cells(p, ea, ss)
                n += 1
                if got != want:
                    errors.append("band_cells(%s, %s, %d) = %r, legacy %r "
                                  "for U=%s V=%s"
                                  % (p.Name, ea, ss, got, want,
                                     _fmt_pair(u), _fmt_pair(v)))
    checks.append("%d default-width layouts (4 seam labels x 2 sides x 2 "
                  "axis states): the named-edge rule == the old literal "
                  "rule, exactly -- for the layouts the old model could "
                  "hold, i.e. each end carrying its OWN default" % n)
    return {"pass": not errors, "errors": errors, "checks": checks}


# ---- 1b: it really is generalized ----------------------------------------

def test_band_cells_generalizes_user_widths(doc):
    """A user width is treated like the default one: the end that carries
    an edge has its cell marked as the corner cell.

    (Split1, Split2) = (0.2, 0.85) on the seam-parallel axis of a patch
    whose other axis carries 0.9 at its 1 end gives 2 x 3 cells; seam V1 /
    side 1 fixes U interval 1 and the band is the single middle V cell —
    the two END cells are corner cells. The old literal rule matched
    neither 0.2 nor 0.85 and returned all three V cells: the corner cell
    silently entered the band (the #61 bug)."""
    from SilkMachinery import band_cells, corner_cells

    errors, checks = [], []

    # (pair, intervals, expected excluded interval indices). The NAME of
    # the property says the end, so 0.85 in Split1 is the 0 end's edge and
    # 0.85 in Split2 is the 1 end's -- a value never has to be compared
    # with the middle of the axis to be filed (#81).
    cases = [
        ((0.2, 0.85), 3, {0, 2}),     # both ends marked -> drop first+last
        ((NO_BAND_1, 0.85), 2, {1}),  # one width at the 1-end
        ((0.85, NO_BAND_2), 2, {0}),  # one width at the 0-end
        ((NO_BAND_1, NO_BAND_2), 1, set()),   # no edge, no corner cell
    ]
    for pair, n, want in cases:
        got = corner_cells(pair[0], pair[1], n)
        if got != want:
            errors.append("corner_cells(%s, %d) = %r, want %r"
                          % (_fmt_pair(pair), n, sorted(got), sorted(want)))
    checks.append("corner_cells over %d layouts: %s"
                  % (len(cases), ", ".join(
                      "%s/%d->%s" % (_fmt_pair(p), n,
                                     sorted(corner_cells(p[0], p[1], n)))
                      for p, n, _ in cases)))

    # The reported bug, on the real selection function.
    p = _StubPatch((NO_BAND_1, 0.9), (0.2, 0.85), name="Wide")
    got = band_cells(p, "V1", 1)
    want = [1 * 3 + 1]            # U interval 1, V interval 1
    if got != want:
        errors.append("band_cells(V1, 1) with V edges (0.2, 0.85) = %r, "
                      "want %r (the corner cells at both ends must be "
                      "excluded)" % (got, want))
    legacy = _legacy_band_cells(p, "V1", 1)
    if legacy == got:
        errors.append("the legacy rule now agrees on (0.2, 0.85) (%r) — the "
                      "regression case no longer reproduces" % (legacy,))
    checks.append("V edges (0.2, 0.85), U edges (0, 0.9), seam V1/1: "
                  "band_cells=%r (legacy rule said %r — it had pulled the "
                  "corner cells in)" % (got, legacy))

    # And the default layout still resolves to exactly the same single
    # cell as it always did, only the width differs.
    d = _StubPatch((NO_BAND_1, 0.9), (NO_BAND_1, 0.9), name="Default")
    if band_cells(d, "V1", 1) != _legacy_band_cells(d, "V1", 1):
        errors.append("default (0, 0.9) layout no longer matches legacy")
    checks.append("default V edges (0, 0.9): band_cells=%r == legacy"
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
        for letter in ("U", "V"):
            for n_ in (1, 2):
                prop = "%sSplit%d" % (letter, n_)
                cur = float(getattr(p, prop))
                new = REMAP.get(round(cur, 9), cur)
                if new != cur:
                    setattr(p, prop, new)
        p.recompute()   # patch only: no blend re-asserts its default here
    moved = {n: (_edges(p, "U"), _edges(p, "V"))
             for n, p in model["patches"].items()}
    checks.append("widths moved: %s"
                  % ", ".join("%s U=%s V=%s"
                              % (n, _fmt_pair(u), _fmt_pair(v))
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


def _edges(p, letter):
    """`(Split1, Split2)` of one axis, as plain floats."""
    return (round(float(getattr(p, letter + "Split1")), 12),
            round(float(getattr(p, letter + "Split2")), 12))


def _band_axis(p, other, tol=0.01):
    """(seam label, side, band-edge property, side-0/1) of p's band for
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
    letter = "V" if e[0] == "U" else "U"
    return e, ss, "%sSplit%d" % (letter, ss + 1), ss


def _intervals(pair):
    """[(lo, hi)] from a pair of named edges, written out here so the
    width assertions do not borrow the object code's interval builder."""
    s = sorted(set(float(v) for v in pair if 0.0 < v < 1.0))
    return list(zip([0.0] + s, s + [1.0]))


def _band_interval(p, prop, ss):
    ivs = _intervals(_edges(p, prop[0]))
    return ivs[0] if ss == 0 else ivs[-1]


def _band_box(p, ea, ss):
    """(u-interval, v-interval) of p's band cell for seam ea / side ss,
    derived here from the named edges so it never borrows band_cells.

    The band axis is PERPENDICULAR to the seam (seam along U -> V band)
    and sits at the seam's own parametric end; the seam-PARALLEL extent
    is the whole axis here because these fixtures put no extra edge on
    it. `None` on an axis means "derive it from the cell index"."""
    us, vs = _intervals(_edges(p, "U")), _intervals(_edges(p, "V"))
    if ea[0] == "U":
        return None, (vs[0] if ss == 0 else vs[-1])
    return (us[0] if ss == 0 else us[-1]), None


def _band_corners_on_surface(p, idx, want_u, want_v):
    """Worst deviation of subgrid cell `idx`'s four corner poles from the
    patch's base surface evaluated at the corners of the parameter box
    (want_u, want_v).

    This is the geometric proof that the band's ACTUAL extent is that box
    -- not a bookkeeping claim about a cell index."""
    nv = len(_intervals(_edges(p, "V")))
    iu, ivc = divmod(idx, nv)
    us, vs = _intervals(_edges(p, "U")), _intervals(_edges(p, "V"))
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


def test_band_edge_is_named_for_its_own_end(doc):
    """#82 replaces the end-classification rule, and this pins what took
    its place: `Split1` IS the parametric-0 end's band edge and `Split2`
    IS the parametric-1 end's, with no threshold and no ordering.

    The pre-#82 rule (`split_at_end`) read a LIST and guessed: the
    lowest split belongs to the 0 end, the highest to the 1 end, and one
    exactly at 0.5 to NEITHER. That guess is #81 — on `[0.2, 0.4]` it
    reported no band at the 1 end, so the blend wrote a third split that
    the two-entry cap then refused and the patch went Invalid. With the
    edge's NAME saying, there is nothing to guess, and the two cases the
    old rule could not express are ordinary:
      * the midpoint, 0.5, is an edge at BOTH ends now;
      * a wide 0-end edge (0.9 on Split1) is a 0.9-wide band at the 0
        end, never a band that migrates to the other end.

    Also pinned: every consumer reads the same names -- band_cells and
    corner_cells agree with `band_at_end` about which end carries what,
    because they all read the same two properties (a second notion of
    "which end" is how a band comes to measure itself against a cell
    excluded for a different reason)."""
    from SilkMachinery import band_at_end, build_intervals, corner_cells

    errors, checks = [], []

    cases = [
        # ((Split1, Split2), ss, expected edge or None)
        ((NO_BAND_1, NO_BAND_2), 0, None),
        ((NO_BAND_1, NO_BAND_2), 1, None),
        ((0.1, NO_BAND_2), 0, 0.1),      # one edge at the 0 end
        ((NO_BAND_1, 0.9), 1, 0.9),      # one edge at the 1 end
        ((0.1, 0.9), 0, 0.1),            # both ends, one axis
        ((0.1, 0.9), 1, 0.9),
        ((0.25, NO_BAND_2), 0, 0.25),    # user widths
        ((NO_BAND_1, 0.75), 1, 0.75),
        ((0.5, NO_BAND_2), 0, 0.5),      # the midpoint IS an edge now
        ((NO_BAND_1, 0.5), 1, 0.5),
        ((0.2, 0.4), 0, 0.2),            # #81's own case: both edges read
        ((0.2, 0.4), 1, 0.4),
        ((0.9, NO_BAND_2), 0, 0.9),      # a wide 0-end edge stays at the 0 end
    ]
    for pair, ss, want in cases:
        got = band_at_end(pair[0], pair[1], ss)
        ok = (got is None and want is None) or \
             (got is not None and want is not None and abs(got - want) < 1e-12)
        if not ok:
            errors.append("band_at_end(%s, %d) = %r, want %r"
                          % (_fmt_pair(pair), ss, got, want))
    checks.append("%d (pair, end) layouts: Split1 is the 0 end's edge, "
                  "Split2 the 1 end's, 0.5 included, no threshold"
                  % len(cases))

    # The interval arithmetic and the corner-cell exclusion agree with it
    # on every layout, because they read the same properties.
    from SilkMachinery import axis_splits
    candidates = [NO_BAND_1, NO_BAND_1, 0.2, 0.4, 0.5, 0.9, NO_BAND_2]
    n = 0
    for s1 in candidates:
        for s2 in candidates:
            n_iv = len(build_intervals(s1, s2))
            corners = corner_cells(s1, s2, n_iv)
            for ss in (0, 1):
                has = band_at_end(s1, s2, ss) is not None
                dropped = (0 in corners) if ss == 0 \
                    else (n_iv - 1 in corners)
                n += 1
                if has != dropped:
                    errors.append("end %d of (Split1=%g, Split2=%g): "
                                  "band_at_end says it %s an edge, "
                                  "corner_cells %s that end's cell"
                                  % (ss, s1, s2,
                                     "has" if has else "has no",
                                     "dropped" if dropped else "kept"))
            if axis_splits(s1, s2) and n_iv != 1 + len(axis_splits(s1, s2)):
                errors.append("(%g, %g) makes %d intervals, which is not "
                              "one more than the %d edges it carries"
                              % (s1, s2, n_iv, len(axis_splits(s1, s2))))
    checks.append("%d (pair, end) layouts over {sentinel, 0.2, 0.4, 0.5, "
                  "0.9}: band_at_end, corner_cells and the interval count "
                  "all agree -- one rule, read by name" % n)
    return {"pass": not errors, "errors": errors, "checks": checks}


def test_blend_reads_the_user_band_width(doc):
    """#64, the defect: the blend used to ASSERT its default 0.1 / 0.9
    instead of READING the patch's band edge, so a user width never took
    effect.

    Now the patch owns its edges and the blend consumes them: a user
    width survives the recompute with NO default written beside it, it
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
    default_a = _edges(pa, prop_a[0])
    checks.append("default: %s seam %s/side %d -> %s = %s"
                  % (pa.Name, ea, ss_a, prop_a, _fmt_pair(default_a)))

    # the user moves ONE side's band width (0.1 default -> 0.3)
    user = 0.3 if ss_a == 0 else 0.7
    with _Capture() as cap:
        setattr(pa, prop_a, user)
        doc.recompute()

    stored = _edges(pa, prop_a[0])
    checks.append("after setting %s.%s = %g and recomputing: %s = %s"
                  % (pa.Name, prop_a, user, prop_a, _fmt_pair(stored)))
    want_pair = list(default_a)
    want_pair[int(prop_a[-1]) - 1] = user
    if stored != (round(want_pair[0], 12), round(want_pair[1], 12)):
        errors.append("%s.%s = %s after recompute, want %s — the blend "
                      "re-asserted its default beside the user's width"
                      % (pa.Name, prop_a, _fmt_pair(stored),
                         _fmt_pair((want_pair[0], want_pair[1]))))
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
    Vector = FreeCAD.Vector
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
    one leaves the other side's band edge exactly as the blend wrote
    it — in both directions, and each patch keeps its own user width."""
    from SilkWorkflowOps import create_blend_by_edge
    from Tests.test_patch_touched import _build_two_patch_pair

    pa, pb, seam = _build_two_patch_pair(doc)
    blend = create_blend_by_edge(seam)
    doc.recompute()
    errors, checks = [], []

    _, ss_a, prop_a, _ = _band_axis(pa, pb)
    _, ss_b, prop_b, _ = _band_axis(pb, pa)

    base_b = _edges(pb, prop_b[0])
    checks.append("defaults: %s.%s = %s, %s.%s = %s"
                  % (pa.Name, prop_a, _fmt_pair(_edges(pa, prop_a[0])),
                     pb.Name, prop_b, _fmt_pair(base_b)))

    def set_edge(p, prop, width, ss):
        pair = list(_edges(p, prop[0]))
        pair[int(prop[-1]) - 1] = width if ss == 0 else 1.0 - width
        setattr(p, prop, pair[int(prop[-1]) - 1])

    # A only
    set_edge(pa, prop_a, 0.25, ss_a)
    doc.recompute()
    doc.recompute()
    if _edges(pa, prop_a[0]) != _edges(pa, prop_a[0]) or \
            abs(_band_interval(pa, prop_a, ss_a)[1]
                - _band_interval(pa, prop_a, ss_a)[0] - 0.25) > 1e-9:
        errors.append("A's width did not stick: %s.%s = %s over %r"
                      % (pa.Name, prop_a, _fmt_pair(_edges(pa, prop_a[0])),
                         _band_interval(pa, prop_a, ss_a)))
    if _edges(pb, prop_b[0]) != base_b:
        errors.append("setting A's width disturbed B: %s.%s = %s, want %s"
                      % (pb.Name, prop_b, _fmt_pair(_edges(pb, prop_b[0])),
                         _fmt_pair(base_b)))
    if len(blend.Poles or []) != 24:
        errors.append("blend lost poles after A's width change (%d)"
                      % len(blend.Poles or []))
    checks.append("A width 0.25: A reads it, B still %s, blend has 24 poles"
                  % (_fmt_pair(base_b),))

    # now B too, with a different width — A must not be re-asserted
    set_edge(pb, prop_b, 0.4, ss_b)
    doc.recompute()
    doc.recompute()
    if abs(_band_interval(pa, prop_a, ss_a)[1]
           - _band_interval(pa, prop_a, ss_a)[0] - 0.25) > 1e-9:
        errors.append("setting B's width disturbed A: %s.%s = %s over %r"
                      % (pa.Name, prop_a, _fmt_pair(_edges(pa, prop_a[0])),
                         _band_interval(pa, prop_a, ss_a)))
    if abs(_band_interval(pb, prop_b, ss_b)[1]
           - _band_interval(pb, prop_b, ss_b)[0] - 0.4) > 1e-9:
        errors.append("B's width did not stick: %s.%s = %s over %r"
                      % (pb.Name, prop_b, _fmt_pair(_edges(pb, prop_b[0])),
                         _band_interval(pb, prop_b, ss_b)))
    if len(blend.Poles or []) != 24:
        errors.append("blend lost poles after both widths changed (%d)"
                      % len(blend.Poles or []))
    checks.append("both widths set independently: A=0.25 B=0.4, blend still "
                  "24 poles")
    return {"pass": not errors, "errors": errors, "checks": checks}


def test_corner_patch_band_widths_stay_per_seam(doc):
    """The four-patch corner must not regress: each patch legitimately
    carries a band edge per END on its two axes, and every strip still
    resolves to exactly ONE band cell. A non-default width on ONE seam of
    a corner patch leaves that seam's OTHER end on the same axis alone —
    the OTHER seam's band axis is a different property pair and is not
    touched."""
    from SilkMachinery import band_cells, patch_side
    from Tests.test_blend_corner_splits import EXPECTED_SPLITS

    model = cm.build_corner_model(doc)
    p44 = model["patches"]["Patch44"]
    errors, checks = [], []

    for name, want_u, want_v in EXPECTED_SPLITS:
        p = model["patches"][name]
        got = (_edges(p, "U"), _edges(p, "V"))
        if got != (tuple(want_u), tuple(want_v)):
            errors.append("fixture: %s edges U=%s V=%s, want U=%s V=%s"
                          % (name, _fmt_pair(got[0]), _fmt_pair(got[1]),
                             _fmt_pair(want_u), _fmt_pair(want_v)))
    checks.append("default ring: all 4 corner patches carry an edge on "
                  "both of the ends their seams ask for (%s)"
                  % "; ".join("%s U=%s V=%s" % (n, _fmt_pair(u),
                                                _fmt_pair(v))
                              for n, u, v in EXPECTED_SPLITS))

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
    axes = {("V" if e[0] == "U" else "U") for _, _, e, _ in sides}
    if len(axes) != 2:
        return {"pass": False,
                "errors": ["fixture: both seams of Patch44 use the same band "
                           "axis %s" % axes], "checks": checks}

    b_target, other_t, e_t, ss_t = sides[0]
    b_other, other_o, e_o, ss_o = sides[1]
    prop_t = "%sSplit%d" % ("V" if e_t[0] == "U" else "U", ss_t + 1)
    letter_o = "V" if e_o[0] == "U" else "U"
    before_o = _edges(p44, letter_o)
    cells_before = {bn: band_cells(p44, e, ss) for bn, _, e, ss in sides}
    checks.append("Patch44 seams: %s -> %s (side %d) via %s, %s -> %s "
                  "(side %d) via the %s axis"
                  % (b_target, e_t, ss_t, prop_t, b_other, e_o, ss_o,
                     letter_o))

    user = 0.3 if ss_t == 0 else 0.7
    with _Capture() as cap:
        setattr(p44, prop_t, user)
        doc.recompute()
    errors += ["console error: %s" % e for e in cap.errors]

    pair_t = _edges(p44, prop_t[0])
    checks.append("Patch44.%s set to %g and recomputed -> %s"
                  % (prop_t, user, _fmt_pair(pair_t)))
    if pair_t[ss_t] != user:
        errors.append("Patch44.%s = %s after the width change, want %g at "
                      "that end (the blend re-asserted its default)"
                      % (prop_t, _fmt_pair(pair_t), user))

    # the OTHER seam is untouched, on its own axis
    if _edges(p44, letter_o) != before_o:
        errors.append("Patch44's %s axis = %s, want %s — the other seam's "
                      "band axis was disturbed"
                      % (letter_o, _fmt_pair(_edges(p44, letter_o)),
                         _fmt_pair(before_o)))

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


def test_default_band_edge_decision_is_unchanged(doc):
    """With no user choice, #64 changes nothing: the blend writes the
    default EXACTLY when the end carries no edge.

    Compared against the pre-#82 rule that decision was "the end has no
    split", classified by VALUE (below 0.5 -> end 0, above -> end 1, 0.5
    -> neither). On every layout the fixtures can produce — each end
    holding its own default, or nothing — the two agree, which is the
    claim: the default path is unchanged and a fresh ring still
    materializes the documented 0.1 / 0.9 layout.

    Where they DIFFER is #81, and that is the point rather than a
    regression: with both ends carrying an edge on their own side of the
    middle — say Split1 = 0.2 and Split2 = 0.4 — the pre-#82 rule reported
    NO band at the 1 end, so the blend tried to write a third split that
    the two-entry cap refused and the patch went Invalid. Both ends now
    carry an edge, both bands exist, and nothing is written."""
    from SilkMachinery import band_edge

    errors, checks = [], []

    # (pair, {end: "the pre-#82 rule reports an edge here?"}). Each pair
    # is the named-edge form of a split list the fixtures produce.
    layouts = [
        ((NO_BAND_1, NO_BAND_2), {0: False, 1: False}),      # []
        ((0.1, NO_BAND_2), {0: True, 1: False}),              # [0.1]
        ((NO_BAND_1, 0.9), {0: False, 1: True}),              # [0.9]
        ((0.1, 0.9), {0: True, 1: True}),                    # [0.1, 0.9]
    ]
    for pair, legacy in layouts:
        for ss in (0, 1):
            edge = band_edge(pair[ss])
            writes = edge is None
            if writes == legacy[ss]:
                errors.append("edges %s, end %d: the blend %s write the "
                              "default, the pre-#82 rule said this end %s an "
                              "edge"
                              % (_fmt_pair(pair), ss,
                                 "would not" if writes else "would",
                                 "has" if legacy[ss] else "has no"))
    checks.append("%d (pair, end) layouts the fixtures can produce: "
                  "write-the-default decision identical to the pre-#82 "
                  "rule" % (2 * len(layouts)))

    # ... and on real geometry, a fresh ring still lands on 0.1 / 0.9.
    from Tests.test_blend_corner_splits import EXPECTED_SPLITS
    model = cm.build_corner_model(doc)
    for name, want_u, want_v in EXPECTED_SPLITS:
        p = model["patches"][name]
        got = (_edges(p, "U"), _edges(p, "V"))
        if got != (tuple(want_u), tuple(want_v)):
            errors.append("default ring: %s edges U=%s V=%s, want U=%s V=%s"
                          % (name, _fmt_pair(got[0]), _fmt_pair(got[1]),
                             _fmt_pair(want_u), _fmt_pair(want_v)))
    for bname, st in model["strips"].items():
        if len(st.Poles or []) != 24:
            errors.append("default ring: %s has %d poles, want 24"
                          % (bname, len(st.Poles or [])))
    checks.append("fresh 2x2 ring still materializes the documented "
                  "0.1 / 0.9 layout on all 4 patches, 24 poles per strip")

    # #81 itself: the layout the old rule could not handle.
    from SilkMachinery import band_at_end, band_cells
    p = _StubPatch((NO_BAND_1, 0.4), (0.2, NO_BAND_2), name="EightyOne")
    if band_at_end(0.2, 0.4, 0) is None or band_at_end(0.2, 0.4, 1) is None:
        errors.append("the 1 end of (0.2, 0.4) reports no band -- #81 is "
                      "not gone")
    if len(band_cells(p, "V1", 1)) != 1:
        errors.append("#81's (0.2, 0.4) layout gives band_cells(V1, 1) = %r, "
                      "want one cell" % (band_cells(p, "V1", 1),))
    checks.append("#81's (0.2, 0.4): both ends report a band and the band "
                  "is one cell -- the layout the pre-#82 classification "
                  "refused now works")
    return {"pass": not errors, "errors": errors, "checks": checks}


# ---- 2: the refusal is actionable ---------------------------------------

def test_zero_cell_band_refusal_names_patch_and_values(doc):
    """A band that covers no subgrid cell at all still refuses (the blend
    supports single-cell bands only) — and the message carries what a
    user needs to fix it: the patch, the seam and its side, both named
    edges on each axis, how many intervals they make, which are corner
    cells, and the single edit that leaves a one-cell band.

    Fixture: the corner PAIR (two patches, one strip). Patch44's
    seam-parallel axis (V, the axis running ALONG the shared seam) gets
    the SAME edge at both ends, 0.8 / 0.8: one split, so both of the
    axis' end cells are corner cells and the band has none left. That is
    the one degenerate layout #82's named edges still admit — the two
    ends agree on a value, which a list could not even express — and the
    refusal is what says so."""
    from Tests.corner_model import build_corner_pair
    from SilkMachinery import band_cells

    model = build_corner_pair(doc)
    p44 = model["patches"]["Patch44"]
    strip = model["strip"]

    errors, checks = [], []

    with _Capture() as cap:
        p44.VSplit1 = 0.8
        p44.VSplit2 = 0.8
        doc.recompute()

    idxs = band_cells(p44, "V1", 1)
    checks.append("band_cells(Patch44, V1, 1) with V edges (0.8, 0.8) "
                  "= %r (0 cells)" % (idxs,))
    if len(idxs) != 0:
        errors.append("fixture did not produce a zero-cell band: %r" % idxs)

    msg = "\n".join(cap.errors)
    want_fragments = [
        ("patch name", "Patch44"),
        ("cell count", "covers 0 subgrid cells"),
        ("seam + side", "seam V1 (band at parametric 1)"),
        ("band axis edges", "band axis USplit1 = 0, USplit2 = 0.9"),
        ("offending axis edges", "seam-parallel axis VSplit1 = 0.8, "
                                 "VSplit2 = 0.8"),
        ("interval count", "2 interval(s)"),
        ("corner cells excluded", "corner cell(s) [0, 1] excluded"),
        ("cells left", "0 left in the band"),
        ("valid fix", "set Patch44.VSplit2 = 1"),
    ]
    for label, frag in want_fragments:
        if frag not in msg:
            errors.append("refusal message does not name the %s (%r); got:\n%s"
                          % (label, frag, msg))
    checks.append("refusal message names %d facts (patch, seam, both named "
                  "edge pairs, interval count, corner cells, the fix)"
                  % len(want_fragments))

    # The refusal is still a refusal: no crash, and the object survives.
    if getattr(strip, "object_type", None) not in ("Blend", "BlendStrip"):
        errors.append("strip lost its type after the refusal (%r)"
                      % getattr(strip, "object_type", None))
    checks.append("no crash; strip still a %s" % getattr(strip, "object_type",
                                                         None))

    # And the suggested fix actually works.
    with _Capture() as cap2:
        p44.VSplit2 = 1.0
        doc.recompute()
    if cap2.errors:
        errors.append("the suggested fix still errors: %s" % cap2.errors)
    fixed = band_cells(p44, "V1", 1)
    if len(fixed) != 1:
        errors.append("with V edges (0.8, no band) the band is %r, want 1 "
                      "cell" % (fixed,))
    if len(strip.Poles or []) != 24:
        errors.append("after the suggested fix the strip has %d poles, "
                      "want 24" % len(strip.Poles or []))
    checks.append("applying the suggested fix (VSplit2 = 1) rebuilds the "
                  "strip: 24 poles, one band cell %r, no errors" % (fixed,))
    return {"pass": not errors, "errors": errors, "checks": checks}


# ---- 3: band edges normalized on set -------------------------------------

def test_band_edges_normalized_on_set(doc):
    """Whatever goes into the two properties, what comes back out is
    exactly what the geometry used (#53 display residue: before this, a
    rejected value stayed visible in the property editor while the
    geometry had already dropped it).

    The rule is narrow now (#82): a value outside [0, 1] becomes its own
    slot's SENTINEL ("this end carries no band"), and a pair whose two
    edges are out of order is swapped so `Split1 <= Split2` as the
    interval arithmetic reads them. Both are corrections, and both are
    REPORTED — a mistyped width that silently became "no band here" is
    the residue the ticket is about.

    Two cases are deliberately NOT corrected, because a correction there
    would be a guess rather than a fix:
      * a WIDE edge at one end (Split1 = 0.9 with no 1-end edge) is a
        legitimate 0.9-wide band at the 0 end, so it is stored as typed;
      * both ends at the SAME value is stored as typed too -- the two
        ends then agree, which is degenerate for a band and is refused by
        the band, not silently rewritten here."""
    from Tests.test_seam_resolver import _square_patch

    p = _square_patch(doc, "Norm")
    errors, checks = [], []

    def cells():
        return len(p.Proxy._subgrids)

    # the V axis carries one edge throughout, so every cell count below is
    # (U edges + 1) * 2 -- a correction that really drops an edge is then
    # visible in the geometry, not only in the property.
    p.VSplit2 = 0.4
    doc.recompute()
    cases = [
        # (prop, written, expected stored, expected cell count)
        ("USplit1", 0.7, 0.7, 4),
        ("USplit2", 0.2, 0.2, 4),
        ("USplit2", 1.5, 1.0, 2),     # outside [0,1] -> its own sentinel
        ("USplit2", -0.5, 1.0, 2),
        ("USplit1", 0.0, 0.0, 2),     # the sentinel is a legal value
        ("USplit1", 1.0, 1.0, 2),     # ...even in the other slot
        ("USplit2", 0.0, 0.0, 2),     # ...and here
    ]
    for prop, written, want, n_cells in cases:
        with _Capture() as cap:
            # start each case from the other end's sentinel, so the cell
            # count is about the value under test and nothing else
            setattr(p, "USplit2" if prop == "USplit1" else "USplit1",
                    NO_BAND_2 if prop == "USplit1" else NO_BAND_1)
            setattr(p, prop, written)
        got = round(float(getattr(p, prop)), 12)
        if got != want:
            errors.append("%s = %g stored as %g, want %g"
                          % (prop, written, got, want))
        if cells() != n_cells:
            errors.append("%s = %g produced %d cells, want %d"
                          % (prop, written, cells(), n_cells))
        if not 0.0 <= got <= 1.0:
            errors.append("stored %s = %g escapes [0, 1]" % (prop, got))
        msg = "\n".join(cap.errors)
        # The threshold: a correction is REPORTED, always -- the input was
        # not what the geometry used.
        if abs(written - want) > 1e-12:
            if ("%g" % written) not in msg or prop not in msg:
                errors.append("%s = %g was corrected to %g without naming "
                              "the value in the console:\n%s"
                              % (prop, written, want, msg))
        elif msg.strip():
            errors.append("%s = %g was already canonical and reported "
                          "anyway:\n%s" % (prop, written, msg))
    checks.append("%d band-edge writes with one V edge held constant: an "
                  "out-of-range value corrected to its own sentinel AND "
                  "reported (4 cells -> 2), a legal value stored and "
                  "silent, the cell count always following the stored pair"
                  % len(cases))

    # The V axis is normalized the same way, independently -- starting
    # from its neutral pair so the swap below is the only thing at play.
    p.VSplit1 = NO_BAND_1
    p.VSplit2 = NO_BAND_2
    doc.recompute()
    with _Capture() as cap:
        p.VSplit1 = 0.9
        p.VSplit2 = 0.25
    if (_edges(p, "V")) != (0.25, 0.9):
        errors.append("V edges = %s after writing 0.9 then 0.25, want "
                      "(0.25, 0.9) -- the inverted pair was not swapped"
                      % (_fmt_pair(_edges(p, "V")),))
    if not cap.errors:
        errors.append("the swap of an inverted pair was silent: %s"
                      % (cap.errors,))
    elif "swapped" not in "\n".join(cap.errors):
        errors.append("the swap did not say it swapped: %s" % cap.errors)
    checks.append("an inverted pair (VSplit1 = 0.9, VSplit2 = 0.25) is "
                  "swapped to (0.25, 0.9) and says so")

    # ...and the geometry agrees with what is stored.
    if p.Shape.isNull() or not p.Shape.isValid():
        errors.append("patch shape invalid after normalization")
    checks.append("patch shape valid, non-null after the writes")

    # A blend writing its own 0.1 / 0.9 band edge is a no-op (already
    # canonical) and must not report anything.
    from Tests.corner_model import build_corner_pair
    pair = build_corner_pair(doc)
    with _Capture() as cap:
        pair["strip"].touch()
        doc.recompute()
    p44 = pair["patches"]["Patch44"]
    if _edges(p44, "U") != (0.0, 0.9):
        errors.append("the blend's band edge drifted to %s"
                      % (_fmt_pair(_edges(p44, "U")),))
    if cap.errors:
        errors.append("the blend's own band-edge write reported: %s"
                      % cap.errors)
    checks.append("the blend's own band edge (USplit2 = 0.9) passes "
                  "through normalization untouched, silently")
    return {"pass": not errors, "errors": errors, "checks": checks}


# ---- 4: #76's cap, now a type --------------------------------------------

def test_third_split_on_an_axis_is_not_expressible(doc):
    """#76's "at most two splits per axis" is no longer a rule anything
    enforces -- it is a TYPE. There are two properties, each named for one
    end, so a third split on an axis cannot be written at all: the axis
    has no list to append to, and `Split3` is not a property.

    So what is asserted here is the shape, and the fact that the two
    writers of a band edge in the codebase can only ever move ONE of the
    two: the blend's ensure_band_split and the panel's band editor. Both
    are pinned below by exercising them -- a third value is not refused,
    it is inexpressible, and every write lands on the end it names."""
    from Tests.test_seam_resolver import _square_patch

    errors, checks = [], []
    p = _square_patch(doc, "Type")

    # The properties themselves: four scalars, no lists anywhere.
    for prop in ("USplit1", "USplit2", "VSplit1", "VSplit2"):
        if not hasattr(p, prop):
            errors.append("a Patch has no %s property" % prop)
            continue
        kind = p.getTypeIdOfProperty(prop)
        if kind != "App::PropertyFloat":
            errors.append("%s is a %s, want App::PropertyFloat"
                          % (prop, kind))
    for old in ("USplits", "VSplits"):
        if hasattr(p, old):
            errors.append("the pre-#82 %s property is still there -- the "
                          "cap is not a type while a list survives" % old)
    checks.append("a Patch carries exactly four App::PropertyFloat band "
                  "edges and no split list")

    # Writing the two ends in any order gives one interval per edge, so
    # an axis can hold at most THREE intervals -- two bands and a middle.
    for s1, s2 in ((0.1, 0.9), (0.2, 0.4), (0.0, 0.9), (0.3, 1.0)):
        p.USplit1 = s1
        p.USplit2 = s2
        doc.recompute()
        n = len(p.Proxy._subgrids)
        if n > 3:
            errors.append("U edges (%g, %g) produced %d cells -- an axis "
                          "can hold at most three" % (s1, s2, n))
    checks.append("every pair of U edges yields at most 3 cells (2 bands "
                  "plus the middle), and #81's (0.2, 0.4) is an ordinary "
                  "pair now, not a refused one")

    # The blend's own writer: it can only ever write the ONE end it is
    # asked about, and it leaves the other end alone.
    from Tests.corner_model import build_corner_model
    model = build_corner_model(doc)
    for pname, patch in model["patches"].items():
        u, v = _edges(patch, "U"), _edges(patch, "V")
        n_u = len([x for x in u if 0.0 < x < 1.0])
        n_v = len([x for x in v if 0.0 < x < 1.0])
        if n_u > 2 or n_v > 2:
            errors.append("%s carries %d U and %d V edges; a ring writes "
                          "at most one per end" % (pname, n_u, n_v))
    checks.append("after the full ring every patch carries at most one edge "
                  "per end per axis, written by the blend alone")
    return {"pass": not errors, "errors": errors, "checks": checks}


def test_a_band_is_one_cell_by_construction(doc):
    """#82 removed a failure mode, so this pins WHY rather than a symptom.

    Each named edge cuts exactly one interval off the axis it belongs to
    -- `Split1` the first, `Split2` the last -- so an axis with `n` edges
    makes `n + 1` intervals and loses `n` of them to the corner-cell
    exclusion: exactly one cell is left for the band. That is why #61's
    multi-cell band refusal can no longer be reached, and it is asserted
    over every layout the properties can express (and over the one
    degenerate pair, which yields none)."""
    from SilkMachinery import band_cells, build_intervals, corner_cells

    errors, checks = [], []
    candidates = [0.0, 0.1, 0.2, 0.5, 0.8, 0.9, 1.0]
    n = 0
    degenerate = 0
    for u1 in candidates:
        for u2 in candidates:
            for v1 in candidates:
                for v2 in candidates:
                    p = _StubPatch((u1, u2), (v1, v2), name="Stub")
                    for ea in ("U0", "U1", "V0", "V1"):
                        for ss in (0, 1):
                            got = band_cells(p, ea, ss)
                            n += 1
                            if len(got) > 1:
                                errors.append("band_cells(%s, %s, %d) = %r "
                                              "-- a multi-cell band is not "
                                              "expressible any more"
                                              % (p.Name, ea, ss, got))
                            if not got:
                                degenerate += 1
                    # the arithmetic, stated directly
                    for letter, (s1, s2) in (("U", (u1, u2)),
                                              ("V", (v1, v2))):
                        n_iv = len(build_intervals(s1, s2))
                        edges = n_iv - 1
                        dropped = len(corner_cells(s1, s2, n_iv))
                        same = (0.0 < s1 < 1.0 and s1 == s2)
                        if edges and not same and n_iv - dropped != 1:
                            errors.append("%s edges (%g, %g): %d intervals "
                                          "minus %d corner cells is not 1"
                                          % (letter, s1, s2, n_iv, dropped))
                        if edges and same and n_iv - dropped != 0:
                            errors.append("%s edges (%g, %g): the degenerate "
                                          "same-edge pair left %d cells, want "
                                          "none" % (letter, s1, s2,
                                                    n_iv - dropped))
    checks.append("%d (layout, seam, side) combinations over every pair of "
                  "properties from %s: never more than one band cell "
                  "(%d of them are the degenerate same-edge pair, which has "
                  "none)" % (n, candidates, degenerate))
    if degenerate == 0:
        errors.append("no layout produced the degenerate zero-cell band -- "
                      "the arithmetic being pinned is not reachable")
    return {"pass": not errors, "errors": errors, "checks": checks}


ALL_TESTS = [
    test_corner_cells_follow_the_end_that_carries_an_edge,
    test_band_cells_generalizes_user_widths,
    test_corner_model_bands_follow_non_default_widths,
    test_band_edge_is_named_for_its_own_end,
    test_blend_reads_the_user_band_width,
    test_band_widths_of_both_sides_are_independent,
    test_corner_patch_band_widths_stay_per_seam,
    test_default_band_edge_decision_is_unchanged,
    test_zero_cell_band_refusal_names_patch_and_values,
    test_band_edges_normalized_on_set,
    test_third_split_on_an_axis_is_not_expressible,
    test_a_band_is_one_cell_by_construction,
]