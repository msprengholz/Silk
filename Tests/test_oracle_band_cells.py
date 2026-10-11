"""
#63 — the ORACLE's band-cell copy generalized to match #61.

SilkChecks deliberately re-derives the blend's band-cell selection
independently of SilkMachinery / SilkBlend, so a bug in the object code
cannot satisfy the oracle (the reason the copy exists at all). That copy
was still the pre-#61 form: hard-coded 0.1 / 0.9 literals for the corner
cell exclusion, so a seam-parallel axis carrying a user width (0.2, 0.85,
...) fell through it and the band came out two cells wide. Consequence
(pinned as a known gap in Tests/test_band_generalization.py): a SETTLED,
correct blend on such a patch builds its 24 poles from the single
corner-free cell the object code picked, and check_blend then reports
B1/B2 "no shared edge found" — the oracle disagreeing with correct
geometry, which is worse than no oracle.

This file closes that gap on the ORACLE side only:

  - test_oracle_check_blend_accepts_non_default_band_width: the #61
    finding, turned green. A corner-pair patch whose seam-parallel axis
    carries 0.85 settles Up-to-date and passes the FULL check_blend
    (structural + B1 + B2 + B3), while the verbatim pre-#63 derivation
    still refuses on the very same state — so the fix is what turned it
    green, not the fixture getting easier.

  - test_oracle_band_cells_identical_to_legacy_on_default_splits: the
    generalized rule in SilkChecks is PROVABLY the old rule on every
    split list any current fixture can produce (all subsets of
    {0.1, 0.5, 0.9} on both axes x every seam label x both sides =
    8 * 8 * 4 * 2 = 512 layouts), compared cell-for-cell against a
    verbatim copy of the old oracle body — not against an assertion.
    None of the three fixture values can straddle the 0.5 end
    classification, which is what makes the identity provable.

  - test_oracle_reference_rows_identical_to_legacy_on_default_splits:
    the same claim one level up, on REAL geometry: the reference rows
    _blend_reference_rows hands to B1/B2 are byte-identical (exact
    Vector equality, not a tolerance) between the new derivation and the
    verbatim old one, for every default-reachable split list on BOTH
    patches of the corner pair — including the layouts where both answer
    "no band" (None), which must stay None.

MIRROR, NOT IMPORT — why the rule is written out again in SilkChecks
instead of imported from SilkMachinery.corner_cells. The whole point of
this oracle is that it checks the object code against a derivation it
owns. Importing the function under test would let a bug IN that function
satisfy the oracle trivially — the exact defect class check_blend exists
to catch (#39). The same reasoning is why the new rule is also not
reached through SilkBlend: that module does `from FreeCAD import Gui`,
which would drag GUI dependencies into headless oracle runs.
"""

import itertools

import FreeCAD

import Tests.corner_model as cm


class _StubPatch:
    """Minimal stand-in: the oracle's band-cell selection reads nothing
    but USplits / VSplits, so the selection RULE can be exercised over
    many layouts without building geometry."""

    def __init__(self, u=None, v=None, name="Stub"):
        self.USplits = list(u or [])
        self.VSplits = list(v or [])
        self.Name = name


def _subsets(values):
    """Every subset of `values`, as sorted lists."""
    out = []
    for r in range(len(values) + 1):
        for combo in itertools.combinations(values, r):
            out.append(list(combo))
    return out


def _fmt(vs):
    return "[" + ", ".join("%g" % float(v) for v in vs) + "]"


# ---------------------------------------------------------------------------
# Verbatim copies of the PRE-#63 oracle code.
#
# _legacy_oracle_band_cells is the exact band_cells body that lived
# inside SilkChecks._blend_reference_rows before this ticket (the 0.1 /
# 0.9 literals).
#
# _legacy_blend_reference_rows is the whole pre-#63 _blend_reference_rows,
# renamed and with that closure inlined, so the reference rows it derives
# are provably the ones the oracle produced before. Keep this copy frozen.
# ---------------------------------------------------------------------------

def _legacy_oracle_band_cells(p, etype, ss):
    from SilkMachinery import build_intervals as _build_intervals
    ivs_u = _build_intervals(list(p.USplits or []))
    ivs_v = _build_intervals(list(p.VSplits or []))
    nu, nv = len(ivs_u), len(ivs_v)
    if etype[0] == "U":  # seam along U: band fixes V interval, spans U cells
        b = (nv - 1) if ss else 0
        keep_u = set(range(nu))
        if any(abs(s - 0.1) < 1e-9 for s in (p.USplits or [])):
            keep_u.discard(0)
        if any(abs(s - 0.9) < 1e-9 for s in (p.USplits or [])):
            keep_u.discard(nu - 1)
        return [a * nv + b for a in sorted(keep_u)]
    # seam along V: band fixes U interval, spans V cells
    a = (nu - 1) if ss else 0
    keep_v = set(range(nv))
    if any(abs(s - 0.1) < 1e-9 for s in (p.VSplits or [])):
        keep_v.discard(0)
    if any(abs(s - 0.9) < 1e-9 for s in (p.VSplits or [])):
        keep_v.discard(nv - 1)
    return [a * nv + b for b in sorted(keep_v)]


def _legacy_blend_reference_rows(pa, pb, tol=0.01, edge=None):
    """The pre-#63 SilkChecks._blend_reference_rows, verbatim (with its
    legacy band_cells closure). Do not "improve" this copy."""
    import SilkChecks

    a_c = [pa.Poles[0], pa.Poles[3], pa.Poles[15], pa.Poles[12]]
    b_c = [pb.Poles[0], pb.Poles[3], pb.Poles[15], pb.Poles[12]]
    if edge is not None:
        ep = list(getattr(edge, "Poles", []) or [])
        seam = (SilkChecks._pinned_seam(a_c, b_c, ep[0], ep[3], tol)
                if len(ep) >= 4 else None)
    else:
        seam = SilkChecks._detect_seam(a_c, b_c, tol)
    if seam is None:
        return None
    ea, eb, pairs = seam
    ss_a = 0 if ea[1] == "0" else 1
    ss_b = 0 if eb[1] == "0" else 1

    def band_cells(p, etype, ss):
        return _legacy_oracle_band_cells(p, etype, ss)

    def get_strip(p, etype, ss):
        idxs = band_cells(p, etype, ss)
        if len(idxs) != 1 or not p.Proxy._subgrids:
            return None
        return list(p.Proxy._subgrids[idxs[0]])

    sga = get_strip(pa, ea, ss_a)
    sgb = get_strip(pb, eb, ss_b)
    if sga is None or sgb is None:
        return None

    cmap = {"U0": {0: 0, 1: 3}, "U1": {2: 3, 3: 0},
            "V0": {0: 0, 3: 3}, "V1": {1: 0, 2: 3}}
    identity = None
    for lc_idx, rc_idx in pairs:
        la = cmap[ea].get(lc_idx)
        rb = cmap[eb].get(rc_idx)
        if la is None or rb is None:
            return None
        is_id = (la == rb)
        if identity is None:
            identity = is_id
        elif is_id != identity:
            return None
    if identity is None:
        return None
    va = range(4) if ss_a == 0 else range(3, -1, -1)   # left:  shared->outer
    vb = range(4) if ss_b == 0 else range(3, -1, -1)   # right: shared->outer
    rows = []
    for li in range(4):
        if ea[0] == "U":  # shared along U -> COLUMNS (const U)
            l_rev = list(reversed([sga[li * 4 + v] for v in va]))
        else:  # shared along V -> ROWS (const V)
            l_rev = list(reversed([sga[v * 4 + li] for v in va]))
        for lc_idx, rc_idx in pairs:
            rb = cmap[eb].get(rc_idx)
            if rb is not None and li == cmap[ea].get(lc_idx):
                ri = rb
                break
        else:
            ri = li if identity else 3 - li
        if eb[0] == "U":
            rc = [sgb[ri * 4 + v] for v in vb]
        else:
            rc = [sgb[v * 4 + ri] for v in vb]
        rows.append((l_rev, rc))
    return rows


# ---------------------------------------------------------------------------
# 1. the #61 finding, turned green
# ---------------------------------------------------------------------------

def test_oracle_check_blend_accepts_non_default_band_width(doc):
    """A settled, CORRECT blend on a patch whose seam-parallel axis
    carries a user width now passes the full oracle.

    Fixture: the corner PAIR (Patch44 + Patch001 + strip B12). The shared
    edge E_s12 is seam V1/side 1 for Patch44, so VSplits is Patch44's
    SEAM-PARALLEL axis — and no blend writes it (B12 writes only the
    perpendicular USplits=[0.9]), so a user width there survives the
    document recompute and the state stays settled.

    0.85 > 0.5 marks the parametric-1 end of that axis, so its last
    interval is the corner cell (reserved for the four-cell corner blend
    op, #28) and the band is the single remaining cell. The object code
    (#61) resolves it that way and builds 24 poles; the pre-#63 oracle
    matched neither 0.1 nor 0.9, saw BOTH intervals and reported
    "no shared edge found".

    The legacy derivation is run on the very same, already-settled state
    and must STILL refuse — otherwise this test would pass for the wrong
    reason (an easy fixture) instead of pinning the oracle change."""
    from SilkChecks import check_blend
    from SilkMachinery import band_cells

    model = cm.build_corner_pair(doc)
    p44 = model["patches"]["Patch44"]
    p01 = model["patches"]["Patch001"]
    strip = model["strip"]

    p44.VSplits = [0.85]
    doc.recompute()

    errors, checks = [], []

    stored = sorted(float(v) for v in p44.VSplits)
    if stored != [0.85]:
        errors.append("fixture did not hold: Patch44.VSplits = %s after the "
                      "document recompute, want [0.85] (no blend writes this "
                      "axis for this seam)" % _fmt(stored))
    state = list(getattr(strip, "State", []) or [])
    if "Up-to-date" not in state:
        errors.append("fixture is not settled: strip B12 state is %r"
                      % (state,))
    if len(strip.Poles or []) != 24:
        errors.append("strip B12 built %d poles, want 24 — the blend did "
                      "not resolve a one-cell band, so this fixture does "
                      "not reproduce the finding"
                      % len(strip.Poles or []))
    checks.append("fixture settled: Patch44.VSplits=%s, %d subgrid cells, "
                  "strip B12 state %r with 24 poles"
                  % (_fmt(stored), len(p44.Proxy._subgrids or []), state))

    idxs = band_cells(p44, "V1", 1)
    if idxs != [2]:
        errors.append("object-code band for (V1, side 1) is %r, want the "
                      "single corner-free cell [2]" % (idxs,))
    checks.append("object code: band_cells(Patch44, V1, 1) = %r (the 0.85 "
                  "end-cell [3] is excluded as the corner cell)" % (idxs,))

    results = check_blend(strip, p44, p01)
    for name, ok, detail in results:
        checks.append("%s: %s (%s)" % (name, "ok" if ok else "FAIL", detail))
        if not ok:
            errors.append("check_blend %s not green: %s" % (name, detail))

    # And the pre-#63 derivation still refuses on this exact state: the
    # oracle change is what turned it green.
    legacy = _legacy_blend_reference_rows(p44, p01)
    if legacy is not None:
        errors.append("the pre-#63 oracle derivation now also derives rows "
                      "on VSplits=[0.85] — the regression case no longer "
                      "reproduces")
    checks.append("pre-#63 oracle derivation on the same state: still "
                  "refuses (None) — it saw both V intervals as band cells")
    return {"pass": not errors, "errors": errors, "checks": checks}


# ---------------------------------------------------------------------------
# 2. provable identity of the RULE on default-reachable layouts
# ---------------------------------------------------------------------------

def test_oracle_band_cells_identical_to_legacy_on_default_splits(doc):
    """SilkChecks' own band-cell selection reproduces the pre-#63 oracle
    EXACTLY on every split list the fixtures can produce: all subsets of
    {0.1, 0.5, 0.9} on both axes, every seam label, both sides —
    8 * 8 * 4 * 2 = 512 layouts, compared cell-for-cell against the
    verbatim old body.

    0.1 and 0.9 are the band widths ensure_band_split writes; 0.5 is the
    mid-surface split the mutation sweeps use. None of the three can
    straddle the 0.5 end classification (< 0.5 -> the parametric-0 end,
    > 0.5 -> the parametric-1 end, == 0.5 -> neither), which is what
    makes the identity provable rather than merely checked on the
    fixtures. This is the same argument #61 made for the object code."""
    import SilkChecks

    errors, checks = [], []
    splits_sets = _subsets([0.1, 0.5, 0.9])
    n = 0
    one_cell = 0
    for us, vs in itertools.product(splits_sets, repeat=2):
        p = _StubPatch(us, vs, name="Stub")
        for ea in ("U0", "U1", "V0", "V1"):
            for ss in (0, 1):
                got = SilkChecks._oracle_band_cells(p, ea, ss)
                want = _legacy_oracle_band_cells(p, ea, ss)
                n += 1
                if len(got) == 1:
                    one_cell += 1
                if got != want:
                    errors.append("_oracle_band_cells(%s, %d) = %r, legacy "
                                  "%r for USplits=%s VSplits=%s"
                                  % (ea, ss, got, want, _fmt(us), _fmt(vs)))
    checks.append("%d layouts compared (U in %s x V in %s, 4 seam labels "
                  "x 2 sides): oracle rule == pre-#63 oracle, exactly "
                  "(%d of them resolve to a single band cell)"
                  % (n, len(splits_sets), len(splits_sets), one_cell))

    # The generalization is real, not vacuous: the layouts the fixtures
    # never produce are exactly where it differs, on the 1-end.
    p = _StubPatch([0.9], [0.85], name="UserWidth")
    got = SilkChecks._oracle_band_cells(p, "V1", 1)
    want = [2]
    legacy = _legacy_oracle_band_cells(p, "V1", 1)
    if got != want:
        errors.append("_oracle_band_cells(V1, 1) with VSplits=[0.85] = %r, "
                      "want %r (the 1-end cell is the corner cell)"
                      % (got, want))
    if legacy == got:
        errors.append("the pre-#63 rule now agrees on [0.85] (%r) — the "
                      "generalization is vacuous" % (legacy,))
    checks.append("VSplits=[0.85], USplits=[0.9], seam V1/1: oracle %r vs "
                  "pre-#63 %r (the old rule pulled the corner cell in)"
                  % (got, legacy))

    # And the default layout is untouched by construction.
    d = _StubPatch([0.9], [0.9], name="Default")
    if SilkChecks._oracle_band_cells(d, "V1", 1) != _legacy_oracle_band_cells(d, "V1", 1):
        errors.append("default [0.9] layout no longer matches the old rule")
    checks.append("default VSplits=[0.9]: %r == pre-#63"
                  % (SilkChecks._oracle_band_cells(d, "V1", 1),))
    return {"pass": not errors, "errors": errors, "checks": checks}


# ---------------------------------------------------------------------------
# 3. provable identity of the ROWS on real geometry
# ---------------------------------------------------------------------------

def test_oracle_reference_rows_identical_to_legacy_on_default_splits(doc):
    """One level up from the rule: on REAL geometry, the (l_rev, rc) rows
    SilkChecks._blend_reference_rows derives for B1/B2 are byte-identical
    to the pre-#63 derivation's, for every default-reachable split list
    on both patches of the corner pair.

    Exact Vector equality, not a tolerance: the rows are handed to B1/B2
    as reference geometry, so any difference in the selected cell would
    change the oracle's verdict, not just a reported deviation.

    Layouts where the band spans more than one cell (or there are no
    subgrids at all) must answer None on BOTH sides — that is the state
    the oracle correctly refuses, and generalizing the rule must not
    silently start deriving rows there."""
    import SilkChecks

    errors, checks = [], []
    model = cm.build_corner_pair(doc)
    p44 = model["patches"]["Patch44"]
    p01 = model["patches"]["Patch001"]

    splits_sets = _subsets([0.1, 0.5, 0.9])
    compared = 0
    with_rows = 0
    both_none = 0

    # One axis, one patch at a time; the other patch stays at the
    # fixture default the blend wrote.
    for prop in ("USplits", "VSplits"):
        for values in splits_sets:
            for target in (p44, p01):
                before = (list(p44.USplits or []), list(p44.VSplits or []),
                          list(p01.USplits or []), list(p01.VSplits or []))
                setattr(target, prop, list(values))
                doc.recompute()
                got = SilkChecks._blend_reference_rows(p44, p01)
                want = _legacy_blend_reference_rows(p44, p01)
                compared += 1
                if (got is None) != (want is None):
                    errors.append("%s=%s on %s: new derivation %s, pre-#63 %s"
                                  % (prop, _fmt(values), target.Name,
                                     "rows" if got is not None else "None",
                                     "rows" if want is not None else "None"))
                elif got is None:
                    both_none += 1
                else:
                    with_rows += 1
                    if len(got) != 4:
                        errors.append("%s=%s on %s: %d reference rows, want 4"
                                      % (prop, _fmt(values), target.Name,
                                         len(got)))
                    for i, ((l_new, r_new), (l_old, r_old)) in enumerate(
                            zip(got, want)):
                        if list(l_new) != list(l_old) or list(r_new) != list(r_old):
                            errors.append(
                                "%s=%s on %s: row %d differs from the "
                                "pre-#63 derivation\n  new  L=%r R=%r\n"
                                "  old  L=%r R=%r"
                                % (prop, _fmt(values), target.Name, i,
                                   [tuple(v) for v in l_new],
                                   [tuple(v) for v in r_new],
                                   [tuple(v) for v in l_old],
                                   [tuple(v) for v in r_old]))
                (p44.USplits, p44.VSplits,
                 p01.USplits, p01.VSplits) = before
                doc.recompute()
    checks.append("%d layouts compared on real corner-pair geometry "
                  "(USplits/VSplits, all 8 subsets of {0.1, 0.5, 0.9}, "
                  "each patch in turn): %d derived 4 reference rows, "
                  "byte-identical; %d refused on both sides"
                  % (compared, with_rows, both_none))
    if with_rows == 0:
        errors.append("no layout produced reference rows — the comparison "
                      "proves nothing")
    return {"pass": not errors, "errors": errors, "checks": checks}


ALL_TESTS = [
    test_oracle_check_blend_accepts_non_default_band_width,
    test_oracle_band_cells_identical_to_legacy_on_default_splits,
    test_oracle_reference_rows_identical_to_legacy_on_default_splits,
]
