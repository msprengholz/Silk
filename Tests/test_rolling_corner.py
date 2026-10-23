"""
The rolling corner's split, triangle and junction (ticket #119).

WHAT IS PINNED HERE

  1. THE SPLIT.  One edge blend cut at a "rolling leader" -- a position
     ON THE SEAM CURVE, measured from the junction corner -- into two
     pieces that are still the same curve: the corner-side piece and the
     outer piece.  Both are real surfaces, and they meet exactly at the
     cut (the cut is a knot line of both nets: the patch's base surface
     is SEGMENTED there, not re-fitted).  The proof is by EVALUATED
     CURVE DEVIATION, not by comparing poles.

  2. THE DEFAULT PATH IS UNCHANGED.  A blend with `Leader` = 0 (the
     default) is the shipped blend, pole for pole: the same 24 poles,
     the same weights, deviation 0.00e+00.

  3. THE TRIANGLE.  The small triangular surface at the corner: a
     FreeCAD `Surface::Filling` over a boundary of three curves -- the
     corner-side piece of each of the two split seams' curves, and the
     CHORD ACROSS THE CORNER joining their far ends.  The chord is the
     one ambiguous piece of this construction and it is named here (the
     alternatives are the maintainer's collapsed triangular member --
     a degenerate surface, not a boundary a fill can take -- and the
     third seam's blend end, which closes a different hole).

  4. THE JUNCTION.  The corner's own surface is built from the ring of
     the two CORNER-SIDE pieces and the third, unsplit strip: the short
     members are what squeeze the corner's interior in those two
     directions, which is the rolling.

  5. REFUSALS BY NAME.  A leader that does not fall inside the band's
     own extent creates NOTHING.

THE FIXTURE is `Tests/cube_corner_model.py` (three exact planar square
patches meeting like a cube corner), never Demo 01.
"""

# --- manual tier ------------------------------------------------------
# #119's path (B) split/triangle drive, marked SUPERSEDED by ADR 0006
# (the corner is two patches, and the tri is a patch of its own). Each
# test builds the corner end to end, so it is an end-to-end rebuild.
# So this module is NOT in the default (fast) tier. Run it with
# `python3 Tests/run_all.py --manual` (or by name as a filter);
# Tests/test_manual_tier.py asserts it stays importable and keeps tests.
MANUAL = True


import FreeCAD
import Part

from SilkWorkflowOps import create_split_blend, create_rolling_corner
from SilkMachinery import leader_cut
from Tests import cube_corner_model as ccm

TOL = 1e-9          # mm: the split's cut is a shared knot line


def _edge_deviation(e1, e2, n=33):
    """The max distance between two edges, sampled point for point."""
    worst = 0.0
    for i in range(n + 1):
        t = i / float(n)
        p1 = e1.valueAt(e1.FirstParameter
                        + t * (e1.LastParameter - e1.FirstParameter))
        p2 = e2.valueAt(e2.FirstParameter
                        + t * (e2.LastParameter - e2.FirstParameter))
        worst = max(worst, (p1 - p2).Length)
    return worst


def _closest_edge_pair(a, b):
    """(deviation, edge index in a, edge index in b) -- the closest pair."""
    best = None
    for i, e1 in enumerate(a.Shape.Edges):
        for j, e2 in enumerate(b.Shape.Edges):
            d = _edge_deviation(e1, e2)
            if best is None or d < best[0]:
                best = (d, i, j)
    return best


def _fixture(doc):
    """The cube-corner fixture in `doc`, fully recomputed."""
    ccm.build_cube_corner_model(doc)
    doc.recompute()
    doc.recompute()
    return doc


def _strips(doc):
    return [doc.getObject(n) for n in ("B_AB", "B_BC", "B_CA")]


def test_the_split_gives_two_real_surfaces_that_meet_exactly(doc):
    """The leader cuts the blend into two surfaces; the cut is exact."""
    errors, checks = [], []
    _fixture(doc)
    pa, pb = doc.getObject("PatchA"), doc.getObject("PatchB")
    corner, outer = create_split_blend(pa, pb, leader=0.25, name="Split")
    if corner is None or outer is None:
        return {"pass": False,
                "errors": ["the split at 0.25 did not build"],
                "checks": checks}
    for obj, label in ((corner, "corner piece"), (outer, "outer piece")):
        checks.append("%s: %d poles, %d weights, shape %s, %d face(s)"
                      % (label, len(obj.Poles), len(obj.Weights),
                         "ok" if obj.Shape and not obj.Shape.isNull()
                         else "empty",
                         len(obj.Shape.Faces) if obj.Shape else 0))
        if len(obj.Poles) != 24 or len(obj.Weights) != 24:
            errors.append("%s does not carry a 24-pole net" % label)
        if not obj.Shape or obj.Shape.isNull():
            errors.append("%s has no surface" % label)
    dev, _i, _j = _closest_edge_pair(corner, outer)
    checks.append("the two pieces' closest boundary edges: %.3e mm" % dev)
    if dev > TOL:
        errors.append("the two split pieces do not meet exactly at the cut "
                      "(%.3e mm)" % dev)
    # the split really is a split: the corner piece stops at the leader
    yb = corner.Shape.BoundBox
    yl = outer.Shape.BoundBox
    checks.append("corner piece spans y [%.4f, %.4f], outer piece y "
                  "[%.4f, %.4f]" % (yb.YMin, yb.YMax, yl.YMin, yl.YMax))
    if abs(yb.YMax - 0.25) > 1e-9:
        errors.append("the corner piece does not stop at the leader 0.25")
    if abs(yl.YMin - 0.25) > 1e-9:
        errors.append("the outer piece does not start at the leader 0.25")
    return {"pass": not errors, "errors": errors, "checks": checks}


def test_a_blend_without_the_leader_is_byte_identical_to_the_shipped_one(doc):
    """`Leader` = 0 is the shipped path: the same poles, the same weights."""
    errors, checks = [], []
    _fixture(doc)
    pa, pb = doc.getObject("PatchA"), doc.getObject("PatchB")
    shipped = doc.getObject("B_AB")
    plain = create_split_blend(pa, pb, leader=0.0, name="Plain")
    if plain[0] is None or plain[1] is None:
        return {"pass": False,
                "errors": ["a split with no leader did not build"],
                "checks": checks}
    for obj, label in ((plain[0], "corner piece"), (plain[1], "outer piece")):
        dp = max((a - b).Length for a, b in zip(obj.Poles, shipped.Poles))
        dw = max(abs(a - b) for a, b in zip(obj.Weights, shipped.Weights))
        checks.append("%s vs the shipped blend: max pole deviation %.2e mm, "
                      "max weight deviation %.2e" % (label, dp, dw))
        if dp != 0.0 or dw != 0.0:
            errors.append("%s is not the shipped blend (poles %.2e, "
                          "weights %.2e)" % (label, dp, dw))
    return {"pass": not errors, "errors": errors, "checks": checks}


def test_a_leader_outside_the_band_is_refused_by_name(doc):
    """A leader inside the corner cell is refused; nothing is created."""
    errors, checks = [], []
    _fixture(doc)
    pa, pb = doc.getObject("PatchA"), doc.getObject("PatchB")
    before = len(doc.Objects)
    corner, outer = create_split_blend(pa, pb, leader=0.05, name="Bad")
    checks.append("leader 0.05 -> (%r, %r); objects before %d, after %d"
                  % (corner, outer, before, len(doc.Objects)))
    if corner is not None or outer is not None:
        errors.append("a leader inside the corner cell was accepted")
    if len(doc.Objects) != before:
        errors.append("the refused split left objects behind")
    cut, why = leader_cut(pa, "U0", 0, 0.05)
    checks.append("leader_cut names the reason: %s" % why)
    if cut is not None or not why:
        errors.append("the refusal is not named")
    return {"pass": not errors, "errors": errors, "checks": checks}


def test_the_rolling_corner_builds_a_triangle_and_a_corner(doc):
    """The opt-in rolling corner: the split blends, the triangle, the quad."""
    errors, checks = [], []
    _fixture(doc)
    strips = _strips(doc)
    patch = doc.getObject("PatchA")
    res = create_rolling_corner(strips, patch, leader=0.25, name="Roll")
    if res is None:
        return {"pass": False,
                "errors": ["the rolling corner did not build"],
                "checks": checks}
    for strip_name, (c, o) in res["corner_pieces"].items():
        checks.append("%s split into %s (%d poles) and %s (%d poles)"
                      % (strip_name, c.Name, len(c.Poles), o.Name,
                         len(o.Poles)))
        if len(c.Poles) != 24 or len(o.Poles) != 24:
            errors.append("%s did not split into two 24-pole surfaces"
                          % strip_name)
    # path (B): NO ControlGrid66 and NO triangular member on this path.
    corners = [o for o in doc.Objects
               if getattr(o, "object_type", "") == "CornerBlend"]
    checks.append("CornerBlend objects on the rolling path: %d (path B "
                  "builds none)" % len(corners))
    if corners:
        errors.append("the rolling path built a ControlGrid66")
    tri = res["triangle"]
    if tri is None:
        errors.append("the rolling triangle did not build")
        return {"pass": not errors, "errors": errors, "checks": checks}
    checks.append("the triangle: %d face(s), bounding box %s"
                  % (len(tri.Shape.Faces), tri.Shape.BoundBox))
    if len(tri.Shape.Faces) != 1:
        errors.append("the triangle is not a single face")
    # the triangle's boundary is the two leader pieces and the chord: its
    # edges must reach the junction corner and the two leader points
    pts = []
    for e in tri.Shape.Edges:
        pts.extend([e.Vertexes[0].Point, e.Vertexes[-1].Point])
    for want, label in ((FreeCAD.Vector(0, 0, 0), "the junction corner"),
                        (FreeCAD.Vector(0, 0.25, 0), "the first leader "
                         "point"),
                        (FreeCAD.Vector(0.25, 0, 0), "the second leader "
                         "point")):
        d = min((p - want).Length for p in pts)
        checks.append("the triangle's boundary reaches %s: %.2e mm"
                      % (label, d))
        if d > 1e-7:
            errors.append("the triangle's boundary does not reach %s" % label)
    return {"pass": not errors, "errors": errors, "checks": checks}


def test_the_triangle_is_a_freecad_fill_over_a_triangular_boundary(doc):
    """The triangle is FreeCAD's own Surface::Filling, over three edges."""
    errors, checks = [], []
    _fixture(doc)
    patch = doc.getObject("PatchA")
    from SilkWorkflowOps import create_rolling_triangle
    tri = create_rolling_triangle(patch, ("U0", "V0"), leader=0.25,
                                   name="Tri")
    if tri is None:
        return {"pass": False,
                "errors": ["the rolling triangle did not build"],
                "checks": checks}
    checks.append("the triangle is a %s" % tri.TypeId)
    checks.append("faces: %d, edges: %d" % (len(tri.Shape.Faces),
                                            len(tri.Shape.Edges)))
    if tri.TypeId != "Surface::Filling":
        errors.append("the triangle is not a Surface::Filling")
    if len(tri.Shape.Faces) != 1:
        errors.append("the triangle is not a single face")
    return {"pass": not errors, "errors": errors, "checks": checks}
