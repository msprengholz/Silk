"""
Rational (arc) seam weights through the Blend (ticket #107).

A `Patch` whose boundary edge is an ARC carries non-unit `Edge.Weights` --
the arc's own NURBS weights -- and the patch's base surface is rational.
`SilkMachinery.build_subgrids` returned pole-only cells and
`SilkBlend.run_blend` fed literal `[1.0]*4` weights into
`AN.blend_poly_2x4_1x6`, so the strip's outer boundary curve was a
DIFFERENT curve through the same 4 end poles. B1 compared poles only, so
nothing noticed: the pole match is exact at the ends and the curves
separate in between (~0.39 mm at the middle of a 90 deg arc, R=10).

What is pinned here:

  1. the live C0 measurement: both of the strip's outer boundary curves are
     sampled against the patch surface they have to lie on -- the patch's
     own band-outer edge curve, evaluated from `_base_surface` -- and the
     raw mm gap is reported;
  2. the strengthened B1 CANNOT be satisfied by poles alone: with the
     cells' weights discarded (the pre-#107 reading, mutated in place here
     rather than by editing the fix) B1 goes red with a ~0.39 mm number,
     and back green when they are restored;
  3. the unit-weight path is unchanged: a straight-edge patch pair takes
     the `[1.0]*4` route and the strip's 24 poles AND 24 weights are
     exactly what `AN.blend_poly_2x4_1x6(row, [1.0]*4, row, [1.0]*4, ...)`
     returns for its own cells.

No continuity label is asserted anywhere here: this is C0 by evaluated
curve deviation, nothing more (G2 is parked in #104).

Run: python3 Tests/run_all.py rational_weights
"""
import math

import FreeCAD
import Part
from FreeCAD import Vector

from Tests.mcp_harness import check

# One 90 deg arc of R=10 in the XY plane. Its NURBS weights are the
# non-unit ones the defect is about: a quarter circle's control net is
# rational, so `Edge.Weights` is [1, w, w, 1] with w != 1.
ARC_R = 10.0
P0 = Vector(ARC_R, 0.0, 0.0)     # arc start, 0 deg
P1 = Vector(0.0, ARC_R, 0.0)     # arc end, 90 deg

# The two patches' other corners (the shared edge is the arc for
# `kind="arc"`, its chord for `kind="line"`). Both patches are ordinary
# convex 4-gons: the shared edge is Edges[0] of each, which the quad fill
# lays down as the V0 boundary side (U=0 row).
OUTER = (P1, Vector(0.0, 40.0, 0.0), Vector(40.0, 40.0, 0.0))
INNER = (P1, Vector(-10.0, 10.0, 0.0), Vector(-10.0, 0.0, 0.0))


# ---- fixture ---------------------------------------------------------------

def _arc_sketch(doc, name):
    """One visible arc-of-circle element -> a `FirstElement` Edge with the
    arc's own rational weights."""
    sk = doc.addObject("Sketcher::SketchObject", name)
    sk.addGeometry(Part.ArcOfCircle(
        Part.Circle(Vector(0.0, 0.0, 0.0), Vector(0.0, 0.0, 1.0), ARC_R),
        0.0, math.pi / 2.0), False)
    doc.recompute()
    return sk


def _line_sketch(doc, name, a, b):
    """One visible line segment -> a `FirstElement` Edge: 4 collinear
    poles, unit weights."""
    sk = doc.addObject("Sketcher::SketchObject", name)
    sk.addGeometry(Part.LineSegment(a, b), False)
    doc.recompute()
    return sk


def _loop(doc, tag, corners, shared_sketch):
    """(shared edge, the 4-edge loop) through the ops layer: the shared
    edge first, then the three straight sides that close it."""
    from SilkWorkflowOps import create_edge

    shared = create_edge([shared_sketch], name="%s_shared" % tag)
    edges = [shared]
    for i, (a, b) in enumerate(zip(corners, corners[1:] + (P0,))):
        edges.append(create_edge([_line_sketch(doc, "%s_L%d" % (tag, i), a, b)],
                                 name="%s_L%d" % (tag, i)))
    return shared, edges


def _pair(doc, kind):
    """(shared edge, PatchA, PatchB, Blend) from the ops layer only.

    `kind="arc"` shares a rational arc edge (non-unit weights);
    `kind="line"` shares the same edge as a straight chord (unit weights).
    The two fixtures differ in nothing else, which is what makes the
    unit-weight comparison in `..._unit_weight_path_is_byte_identical` a
    real control for the arc one.
    """
    from SilkWorkflowOps import create_patch, create_blend

    shared_sketch = (_arc_sketch(doc, "Shared") if kind == "arc"
                     else _line_sketch(doc, "Shared", P0, P1))
    shared_a, loop_a = _loop(doc, "A", OUTER, shared_sketch)
    shared_b, loop_b = _loop(doc, "B", INNER, shared_sketch)
    pa = create_patch(loop_a, name="PatchA")
    pb = create_patch(loop_b, name="PatchB")
    blend = create_blend(pa, pb, name="ArcBlend")
    doc.recompute()
    return shared_a, pa, pb, blend


# ---- measurement -----------------------------------------------------------

def _blend_boundary_curve(blend, own):
    """`t -> Vector` for one outer boundary curve of the built strip.

    `own` 0 is the across-index-0 side (the boundary at the surface's U=0
    edge), 5 the other. The blend surface is `NURBS_Cubic_64_surf`'s grid:
    U spans the 6 across poles, V the 4 seam stations, so the across
    boundary curves are the U=0 / U=1 edges of the face. Read from the
    object's own Shape -- the geometry the user sees, not a re-derivation.
    """
    faces = list(blend.Shape.Faces)
    if not faces:
        return None
    surf = max(faces, key=lambda f: f.Area).Surface
    u = 0.0 if own == 0 else 1.0
    return lambda t: surf.value(u, t)


def _patch_band_outer_curve(patch, blend, own):
    """`t -> Vector` for the patch curve the strip's OUTER boundary has
    to lie on: the surface isocurve at the outer edge of the band cell the
    strip covers.

    Derived from `_base_surface` (the patch's own rational base surface),
    not from the blend and not from the cell cache: it is the geometry the
    strip is supposed to meet, and it carries the patch's weights by
    construction. The band cell, its seam end and the seam's direction come
    from the shared machinery (`band_cells` / `split_pair` / `seam_identity`),
    which is not what #107 changed.

    `own` 0 is the across-index-0 side of the strip (the LEFT row, whose
    stations are patch A's own seam indices, so the parameters correspond
    directly); `own` 5 is the right row, where a REVERSED seam names the
    mirrored station (identity False), so its parameter runs the other way.
    """
    from SilkBlend import _resolve_seam, seam_identity
    from SilkMachinery import band_cells, build_intervals, split_pair

    other = blend.PatchB if patch is blend.PatchA else blend.PatchA
    seam = _resolve_seam(blend, patch, other, blend.tolerance)
    if seam is None:
        return None
    ea, eb, pairs = seam
    e = ea if patch is blend.PatchA else eb
    ss = 0 if e[1] == "0" else 1
    idxs = band_cells(patch, e, ss)
    if len(idxs) != 1:
        return None
    band_axis = "V" if e[0] == "U" else "U"
    u_int = build_intervals(*split_pair(patch, "U"))
    v_int = build_intervals(*split_pair(patch, "V"))
    iu, iv = divmod(idxs[0], len(v_int))
    lo, hi = u_int[iu] if band_axis == "U" else v_int[iv]
    outer = hi if ss == 0 else lo          # the far side of the band
    base = patch.Proxy._base_surface
    reverse = (own == 5 and seam_identity(ea, eb, pairs) is False)

    def curve(t):
        if reverse:
            t = 1.0 - t
        if band_axis == "U":
            return base.value(outer, t)
        return base.value(t, outer)

    return curve


SAMPLES = 101


def _c0_gaps(blend):
    """`{side: max mm gap}` between each of the strip's two outer boundary
    curves and the patch curve it must lie on, sampled point-for-point.

    Both curves are cubic Beziers over the same seam span -- the strip's V
    axis is the 4-station cubic, the patch's isocurve is its own cubic in
    the seam-parallel direction -- so the parameters correspond (up to the
    seam's direction, handled above), and the shared endpoint samples read
    ~0 on both sides, which is the on-the-spot control that the
    correspondence is right.
    """
    gaps = {}
    for tag, patch, own in (("A", blend.PatchA, 0), ("B", blend.PatchB, 5)):
        strip_curve = _blend_boundary_curve(blend, own)
        patch_curve = _patch_band_outer_curve(patch, blend, own)
        if strip_curve is None or patch_curve is None:
            gaps[tag] = None
            continue
        dev = 0.0
        for i in range(SAMPLES):
            t = i / (SAMPLES - 1.0)
            dev = max(dev, (strip_curve(t) - patch_curve(t)).Length)
        gaps[tag] = dev
    return gaps


def _oracle_failure(blend, patch_a, patch_b):
    """`{check name: detail}` of everything the blend oracle rejects."""
    from SilkChecks import check_blend

    return {n: d for n, ok, d in check_blend(blend, patch_a, patch_b) if not ok}


def _unit_weight_cells():
    """Make the strip's band cells read weight-less -- the pre-#107 INPUT
    to `run_blend`, where the object code had no weights to hand over. It
    mutates the seam the fix lives in (`SilkBlend._cell_weights`), not the
    fixture's stored state, so a recompute really does rebuild the strip
    with unit weights.

    Returns a restore callable, or None on a REVERTED tree, where there is
    no `_cell_weights` at all: there the object code IS the pre-#107
    reading, and the test's red assertion holds without mutating anything.
    """
    import SilkBlend

    orig = getattr(SilkBlend, "_cell_weights", None)
    if orig is None:
        return None
    SilkBlend._cell_weights = lambda p, idx: [1.0] * 16
    return lambda: setattr(SilkBlend, "_cell_weights", orig)


# ---- 1. the live C0 measurement --------------------------------------------

def test_arc_seam_is_c0_by_evaluated_curve_deviation(doc):
    """A strip across a real arc edge lies ON the patch: both outer
    boundary curves are sampled against the patch's band-outer edge curve
    and the raw mm gap is reported.

    Measured on this fixture, 101 samples each side:

        pre-#107 (cells read weight-less): 3.834204e-01 / 3.409005e-01 mm
        post-#107:                         8.926083e-15 / 6.169484e-15 mm

    (the analytic 1-D estimate for a 90 deg arc at R=10 is 0.390 mm; the
    live 2-D band sits within 2% of it). The assertion is 1e-6 mm -- this
    suite's pole tolerance, `SilkChecks.TOL` -- which is ~5 orders below
    the pre-fix gap and ~8 orders above the float noise the
    same-parameter comparison leaves, so neither end of it is a guess.

    The arc's weights are [1.0, 0.804738, 0.804738, 1.0] -- the issue's
    own quoted value for this arc -- which is why the fixture is the
    measured one.
    """
    errors, checks = [], []
    edge, pa, pb, blend = _pair(doc, "arc")

    weights = list(edge.Weights)
    if not check(len(weights) == 4 and any(abs(w - 1.0) > 1e-9
                                           for w in weights),
                 "the fixture's shared edge carries unit weights %r -- this "
                 "test would prove nothing" % (weights,), errors):
        errors.append("arc edge weights: %r" % (weights,))
    checks.append("arc edge weights (raw): %r" % (weights,))
    checks.append("patch A base surface weights (raw, non-unit): %r"
                  % [round(w, 6) for w in pa.Weights if abs(w - 1.0) > 1e-9])
    checks.append("blend weights (raw): %r" % [round(w, 6) for w in blend.Weights])

    if len(blend.Poles or []) != 24:
        errors.append("the blend built %d poles, want 24 -- no measurement "
                      "to make" % len(blend.Poles or []))
        return {"pass": not errors, "errors": errors, "checks": checks}

    gaps = _c0_gaps(blend)
    checks.append("raw C0 gap, strip boundary curve vs patch band-outer "
                   "edge curve, %d samples: side A %.6e mm, side B %.6e mm"
                   % (SAMPLES, gaps["A"], gaps["B"]))
    for tag in ("A", "B"):
        check(gaps[tag] is not None,
              "could not derive the band-outer curve on side %s" % tag, errors)
        if gaps[tag] is not None:
            check(gaps[tag] <= 1e-6,
                  "the strip is not C0 on side %s: %.6e mm off the patch "
                  "curve (tolerance 1e-6 mm)" % (tag, gaps[tag]), errors)

    fails = _oracle_failure(blend, pa, pb)
    check(not fails, "the blend oracle is red on the rational fixture: %s"
          % fails, errors)
    checks.append("blend oracle green (B1 reports the curve deviation): %s"
                  % _oracle_detail(blend, pa, pb))
    return {"pass": not errors, "errors": errors, "checks": checks}


def _oracle_detail(blend, pa, pb):
    from SilkChecks import check_blend

    return [(n, d) for n, _ok, d in check_blend(blend, pa, pb)
            if n in ("structural", "B1_c0_seams")]


# ---- 2. the oracle cannot be satisfied by poles alone ----------------------

def test_b1_is_red_when_the_cells_lose_their_weights(doc):
    """Mutation check: with the cells read weight-less -- the pre-#107
    input to `run_blend` -- the strengthened B1 must go RED, and the arc
    fixture must come back green when the weights are handed over again.

    On a reverted tree there is nothing to mutate (`_cell_weights` does not
    exist, so the object code is already the pre-#107 reading) and the red
    assertion below is simply run against it -- the same red the suite must
    never ship again.
    """
    errors, checks = [], []
    _, pa, pb, blend = _pair(doc, "arc")

    restore = _unit_weight_cells()
    reverted = restore is None
    if not reverted:
        green = _oracle_failure(blend, pa, pb)
        check(not green, "the fixture is not settled before the mutation: %s"
              % green, errors)
        checks.append("settled: %s" % _oracle_detail(blend, pa, pb))
    else:
        checks.append("no SilkBlend._cell_weights: the object code hands no "
                      "weights over (reverted tree) -- mutating nothing")

    try:
        if not reverted:
            blend.touch()
            doc.recompute()
        red = _oracle_failure(blend, pa, pb)
        checks.append("weight-less cells: %d blend weights, B1 %s"
                      % (len(blend.Weights or []),
                         _b1_detail(blend, pa, pb)))
        check("B1_c0_seams" in red,
              "B1 stayed green with the weights discarded -- the pole-only "
              "blindness is back (red checks: %s)" % (red,), errors)
    finally:
        if restore is not None:
            restore()
            blend.touch()
            doc.recompute()

    if not reverted:
        back = _oracle_failure(blend, pa, pb)
        check(not back, "the fixture did not come back green after restoring "
                        "the weights: %s" % back, errors)
        checks.append("restored: %s" % _oracle_detail(blend, pa, pb))
    return {"pass": not errors, "errors": errors, "checks": checks}


def _b1_detail(blend, pa, pb):
    from SilkChecks import check_blend

    return [(n, d) for n, _ok, d in check_blend(blend, pa, pb)
            if n == "B1_c0_seams"]


# ---- 3. the unit-weight path is unchanged ---------------------------------

def test_unit_weight_path_is_byte_identical(doc):
    """A straight-edge pair (every weight 1.0) takes exactly the pre-#107
    route: the strip's 24 poles and 24 weights are what
    `AN.blend_poly_2x4_1x6(row, [1.0]*4, row, [1.0]*4, 2,2,2,2)` returns,
    row by row, and the weights stay unit.
    """
    import ArachNURBS as AN

    from SilkMachinery import band_cells, build_intervals, split_pair
    from SilkBlend import _resolve_seam

    errors, checks = [], []
    _, pa, pb, blend = _pair(doc, "line")

    for p in (pa, pb):
        check(all(abs(w - 1.0) < 1e-12 for w in p.Weights),
              "%s carries non-unit patch weights %r" % (p.Name, list(p.Weights)),
              errors)

    surf = max(list(blend.Shape.Faces), key=lambda f: f.Area).Surface
    fails = _oracle_failure(blend, pa, pb)
    check(not fails, "the unit-weight strip is not oracle-green: %s" % fails,
          errors)

    # re-derive each of the 4 rows from the patch cells and re-run the
    # pre-#107 call: [1.0]*4 in, poles AND weights out
    rows = []
    for patch, own in ((pa, 0), (pb, 1)):
        other = pb if patch is pa else pa
        e = _resolve_seam(blend, patch, other, blend.tolerance)[own]
        ss = 0 if e[1] == "0" else 1
        idx = band_cells(patch, e, ss)[0]
        u_int = build_intervals(*split_pair(patch, "U"))
        v_int = build_intervals(*split_pair(patch, "V"))
        iu, iv = divmod(idx, len(v_int))
        poles2d, weights2d = patch.Proxy.getSubgrid(u_int[iu][0], u_int[iu][1],
                                                    v_int[iv][0], v_int[iv][1])
        flat = [poles2d[r][c] for r in range(4) for c in range(4)]
        flat_w = [float(weights2d[r][c]) for r in range(4) for c in range(4)]
        va = list(range(4)) if ss == 0 else list(range(3, -1, -1))
        side = []
        for li in range(4):
            cross = ([li * 4 + v for v in va] if e[0] == "U"
                     else [v * 4 + li for v in va])
            if own == 0:
                # left row: outer -> shared (the blend's poles_0 order)
                side.append((list(reversed([flat[i] for i in cross])),
                             list(reversed([flat_w[i] for i in cross]))))
            else:
                # right row: shared -> outer
                side.append(([flat[i] for i in cross],
                             [flat_w[i] for i in cross]))
        rows.append(side)

    ref = []
    for li in range(4):
        left, left_w = rows[0][li]
        right, right_w = rows[1][li]
        ref.append(AN.blend_poly_2x4_1x6(left, left_w, right, right_w,
                                        2.0, 2.0, 2.0, 2.0))

    stored_poles, stored_w = list(blend.Poles), list(blend.Weights)
    max_pole = max((stored_poles[li * 6 + j] - ref[li][0][j]).Length
                   for li in range(4) for j in range(6))
    max_w = max(abs(stored_w[li * 6 + j] - ref[li][1][j])
                for li in range(4) for j in range(6))
    checks.append("unit-weight path: max pole delta %.3e mm, max weight "
                  "delta %.3e over the 24-pole grid; stored weights %r"
                  % (max_pole, max_w,
                     sorted(set(round(w, 12) for w in stored_w))))
    check(max_pole <= 1e-9, "unit-weight poles moved: %.3e mm" % max_pole,
          errors)
    check(max_w <= 1e-12, "unit-weight weights moved: %.3e" % max_w, errors)
    check(all(abs(w - 1.0) < 1e-12 for w in stored_w),
          "the unit-weight strip no longer carries unit weights: %r"
          % (sorted(set(stored_w)),), errors)
    return {"pass": not errors, "errors": errors, "checks": checks}


ALL_TESTS = [
    test_arc_seam_is_c0_by_evaluated_curve_deviation,
    test_b1_is_red_when_the_cells_lose_their_weights,
    test_unit_weight_path_is_byte_identical,
]
