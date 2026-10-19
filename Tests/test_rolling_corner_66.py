"""
The rolling corner, path (A): the 66 chain over the CUT cells (ticket #119).

WHAT IS PINNED HERE

  1. THE ROLLING CORNER BUILDS.  `create_rolling_corner_66` moves the
     rolling leader -- the band's CORNER-SIDE CUT -- and builds the
     corner fill (Silk's own 66, over the ring's cut cells), the SMALL
     TRIANGULAR SURFACE beside it (the maintainer's second surface) and
     the FreeCAD filling that replaces it (the owner's spec).

  2. THE LEADER MOVES THE CORNER'S SHAPE.  This is the acceptance
     instrument of the build: the previous build measured the SAME
     curvature spread (1.036938) with and without its leader, because
     its leader was an extra cut INSIDE the band.  The leader that
     moves the corner is the band's own corner-side cut -- the patch's
     named band edge on the seam-parallel axis, which is where the
     maintainer's own file cuts its base surfaces.  Here the spread at
     the junction MUST differ between the shipped corner and the
     rolling one.

  3. THE JUNCTION IS CLOSED.  The corner fill's boundary against each
     blend IS that blend's cut edge, so the C0 residual at the cut is
     zero to the instrument's floor (path (B) left 0.2915 mm there).

  4. THE DEFAULT PATH IS UNCHANGED.  A corner built without the
     rolling construction is the shipped corner, pole for pole.

THE FIXTURE is `Tests/cube_corner_model.py` (three exact planar square
patches meeting like a cube corner), never Demo 01.
"""

import FreeCAD
import Part

from SilkWorkflowOps import (create_corner_blend, create_rolling_corner_66,
                             corner_fill_boundary)
from Tests import cube_corner_model as ccm

TOL = 1e-9          # mm: the cut edge and the corner fill share it


def _fixture(doc):
    ccm.build_cube_corner_model(doc)
    doc.recompute()
    doc.recompute()
    return doc


def _strips(doc):
    return [doc.getObject(n) for n in ("B_AB", "B_BC", "B_CA")]


def _spread(corner):
    """(k_max, k_min, ratio) at the corner's centre, from its own net."""
    from Tests.g2_corner_roll_measure import junction_probe
    import Tests.silk_nurbs as SN
    net = SN.NurbsSurface.from_flat(list(corner.Poles),
                                    list(corner.Weights) or [1.0] * 36,
                                    6, 6, SN.KNOTS_6, SN.KNOTS_6)
    probe = junction_probe(net)
    k_max, k_min, ratio = probe["centre"]
    return k_max, k_min, ratio


def _cut_residual(corner, strips, n=41):
    """The C0 at the cut: every blend's cut edge against the 66."""
    boundary, why = corner_fill_boundary(strips)
    if boundary is None:
        return None, why
    worst = 0.0
    for (obj, sub) in boundary[0]:
        edge = obj.Shape.getElement(sub)
        for i in range(n + 1):
            t = i / float(n)
            p = edge.valueAt(edge.FirstParameter
                              + t * (edge.LastParameter - edge.FirstParameter))
            worst = max(worst, corner.Shape.distToShape(Part.Vertex(p))[0])
    return worst, None


def test_the_rolling_corner_builds_the_66_the_member_and_the_fill(doc):
    """Path (A) builds all three surfaces the maintainer's file carries."""
    errors, checks = [], []
    _fixture(doc)
    strips = _strips(doc)
    patch = doc.getObject("PatchA")
    rolled = [s for s in strips if s.PatchA is patch or s.PatchB is patch]
    res = create_rolling_corner_66(strips, patch, leader=0.25, seams=rolled,
                                   name="Roll")
    if res is None:
        return {"pass": False,
                "errors": ["the rolling corner did not build"],
                "checks": checks}
    corner, member = res["corner"], res["member"]
    checks.append("corner: %d poles, %d face(s)"
                  % (len(corner.Poles), len(corner.Shape.Faces)))
    checks.append("member: %d poles, %d face(s), %d edges"
                  % (len(member.Poles), len(member.Shape.Faces),
                     len(member.Shape.Edges)))
    if len(corner.Poles) != 36:
        errors.append("the corner fill does not carry a 6x6 net")
    if len(corner.Shape.Faces) != 1:
        errors.append("the corner fill is not one face")
    if len(member.Poles) != 24:
        errors.append("the small triangular surface does not carry a 24-pole "
                      "net")
    if len(member.Shape.Faces) != 1:
        errors.append("the small triangular surface is not one face")
    # the member's collapsed row: six poles on the apex
    row = list(member.Poles)[18:24]
    apex = (row[0] - row[-1]).Length
    checks.append("the member's collapsed row: %.3e mm" % apex)
    if apex > 1e-9:
        errors.append("the small triangular surface has no collapsed row")
    # the owner's spec: the FreeCAD replacement of that surface
    if res["member_fill"] is None:
        errors.append("the FreeCAD replacement of the small triangular "
                      "surface did not build")
    else:
        checks.append("the FreeCAD replacement: %s, %d face(s)"
                      % (res["member_fill"].Name,
                         len(res["member_fill"].Shape.Faces)))
    # the leader was written where the cut lives
    checks.append("the cut moved: %s"
                  % ", ".join("%s.%s -> %g" % (w[0], w[1], w[3])
                              for w in res["written"]))
    if not res["written"]:
        errors.append("the rolling leader did not move any cut")
    return {"pass": not errors, "errors": errors, "checks": checks}


def test_the_leader_moves_the_corner_s_shape(doc):
    """THE ACCEPTANCE INSTRUMENT: the leader must change the shape.

    The previous build measured the same spread (1.036938) with and
    without its leader.  Here the leader is the band's own corner-side
    cut, so the corner's spread MUST move."""
    errors, checks = [], []
    _fixture(doc)
    strips = _strips(doc)
    shipped = create_corner_blend(*strips, name="Shipped")
    doc.recompute()
    s_kmax, s_kmin, s_ratio = _spread(shipped)
    checks.append("the shipped corner: k_max %.6g, k_min %.6g, ratio %.6g"
                  % (s_kmax, s_kmin, s_ratio))
    patch = doc.getObject("PatchA")
    rolled = [s for s in strips if s.PatchA is patch or s.PatchB is patch]
    res = create_rolling_corner_66(strips, patch, leader=0.25, seams=rolled,
                                   name="Roll")
    doc.recompute()
    if res is None:
        return {"pass": False,
                "errors": ["the rolling corner did not build"],
                "checks": checks}
    r_kmax, r_kmin, r_ratio = _spread(res["corner"])
    checks.append("the rolling corner: k_max %.6g, k_min %.6g, ratio %.6g"
                  % (r_kmax, r_kmin, r_ratio))
    if abs(r_ratio - s_ratio) < 1e-6:
        errors.append("the leader did not move the corner's shape "
                      "(ratio %.6g both ways)" % s_ratio)
    # and the corner fill's poles are not the shipped ones
    same = all((a - b).Length < 1e-12 for a, b in
               zip(list(shipped.Poles), list(res["corner"].Poles)))
    if same:
        errors.append("the rolling corner is the shipped corner, pole for "
                      "pole")
    return {"pass": not errors, "errors": errors, "checks": checks}


def test_the_junction_at_the_cut_is_closed(doc):
    """The corner fill's boundary IS each blend's cut edge (path (B)
    left 0.2915 mm there)."""
    errors, checks = [], []
    _fixture(doc)
    strips = _strips(doc)
    patch = doc.getObject("PatchA")
    rolled = [s for s in strips if s.PatchA is patch or s.PatchB is patch]
    res = create_rolling_corner_66(strips, patch, leader=0.25, seams=rolled,
                                   name="Roll")
    doc.recompute()
    if res is None:
        return {"pass": False,
                "errors": ["the rolling corner did not build"],
                "checks": checks}
    worst, why = _cut_residual(res["corner"], strips)
    if worst is None:
        return {"pass": False,
                "errors": ["the ring's boundary rows cannot be named: %s"
                           % why],
                "checks": checks}
    checks.append("the C0 at the cut: %.3e mm" % worst)
    if worst > TOL:
        errors.append("the corner fill does not meet the blends' cut edges "
                      "(%.3e mm)" % worst)
    return {"pass": not errors, "errors": errors, "checks": checks}


def test_a_corner_without_the_rolling_construction_is_the_shipped_one(doc):
    """The default path is untouched: no rolling construction, no change."""
    errors, checks = [], []
    _fixture(doc)
    strips = _strips(doc)
    first = create_corner_blend(*strips, name="Shipped1")
    doc.recompute()
    poles = [tuple(v) for v in first.Poles]
    second = create_corner_blend(*strips, name="Shipped2")
    doc.recompute()
    same = all((a - b).Length < 1e-12 for a, b in
               zip(poles, list(second.Poles)))
    checks.append("the shipped corner twice: %s"
                  % ("identical" if same else "DIFFERENT"))
    if not same:
        errors.append("the shipped corner is not reproducible")
    # and the patches' band edges are untouched by a plain corner
    for name in ("PatchA", "PatchB", "PatchC"):
        p = doc.getObject(name)
        if abs(p.USplit1 - 0.1) > 1e-12 or abs(p.VSplit1 - 0.1) > 1e-12:
            errors.append("%s's band edges moved without the rolling "
                          "construction" % name)
    return {"pass": not errors, "errors": errors, "checks": checks}


def test_a_leader_outside_the_seam_is_refused_by_name(doc):
    """A leader outside (0, 1) creates NOTHING."""
    errors, checks = [], []
    _fixture(doc)
    strips = _strips(doc)
    patch = doc.getObject("PatchA")
    before = len(doc.Objects)
    res = create_rolling_corner_66(strips, patch, leader=1.5, name="Bad")
    doc.recompute()
    checks.append("objects before %d, after %d" % (before, len(doc.Objects)))
    if res is not None:
        errors.append("a leader of 1.5 was accepted")
    if len(doc.Objects) != before:
        errors.append("a refused rolling corner left objects in the tree")
    return {"pass": not errors, "errors": errors, "checks": checks}
