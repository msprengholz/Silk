"""
The rolling corner, path (A): the quad over the ring's four members
(ticket #119).

WHAT IS PINNED HERE

  1. THE ROLLING CORNER BUILDS.  `create_rolling_corner_66` places the
     rolling leader -- the patch's own LEADER CUT, placed by a length
     in mm (#129) -- and builds the quad (Silk's own 66, over the ring's
     four members), the TRIANGULAR PATCH beside it (the maintainer's second
     surface) and the FreeCAD filling that replaces that face (the owner's
     spec).  The construction is stated once, in
     `docs/adr/0006-rolled-corner-is-two-patches.md`.

  2. THE LEADER MOVES THE CORNER'S SHAPE (a supporting reading, not the
     acceptance -- the acceptance is the construction diff plus no overlap,
     `docs/adr/0006-rolled-corner-is-two-patches.md`).  The previous
     build measured the SAME
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
import SilkCorner as SC_MEMBER_PIN_SHIM
import SilkMachinery as SM_SPLIT_SHIM

SC_MEMBER_PIN = SC_MEMBER_PIN_SHIM.corner_member_pin
SM_SPLIT = SM_SPLIT_SHIM.split_pair

from SilkWorkflowOps import (create_corner_blend, create_rolling_corner_66,
                             corner_fill_boundary, MEMBER_FACE_FILL)
from Tests import cube_corner_model as ccm
from Tests.mcp_harness import check

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
    """Path (A) builds all three surfaces the maintainer's file carries:
    the 66, the small triangular member, and -- AS THE OPTION -- its FreeCAD
    `Surface::Filling` replacement; and the junction that cut leaves is
    CLOSED.

    The default is the member's own `CubicSurface_64` (the construction the
    maintainer's files store), so the fill is built here by asking for it BY
    NAME. `Tests/test_corner_choices.py` pins the default and the pair of
    reachable faces.

    One build answers three questions that used to be three tests on the
    same fixture (the surfaces, the C0 at the cut, and where the cut sits
    relative to the junction): the fixture build is what either of them
    cost, and none of the readings changed."""
    errors, checks = [], []
    from SilkBlend import side_and_end
    from SilkMachinery import band_extent, leader_pair, split_pair

    _fixture(doc)
    strips = _strips(doc)
    patch = doc.getObject("PatchA")
    rolled = [s for s in strips if s.PatchA is patch or s.PatchB is patch]
    res = create_rolling_corner_66(strips, patch, leader=0.25, seams=rolled,
                                   name="Roll",
                                   member_face=MEMBER_FACE_FILL)
    if res is None:
        return {"pass": False,
                "errors": ["the rolling corner did not build"],
                "checks": checks}
    doc.recompute()
    corner = res["corner"]
    from SilkCorner import corner_tri_face, corner_tri_net
    tri_face = corner_tri_face(corner)
    tri_net = corner_tri_net(corner)
    checks.append("corner: %d poles, %d face(s); corner-owned tri: %s poles"
                  % (len(corner.Poles), len(corner.Shape.Faces),
                     len(tri_net[0]) if tri_net else 0))
    checks.append("compound edges: %d; tri boundary: %r"
                  % (len(corner.Shape.Edges),
                     list(getattr(corner, "TriBoundaryEdges", None) or [])))
    if len(corner.Poles) != 36:
        errors.append("the corner fill does not carry a 6x6 net")
    if len(corner.Shape.Faces) != 2 or tri_face is None:
        errors.append("the corner Shape is not a compound of quad and tri")
    if tri_net is None:
        errors.append("the corner does not carry a 24-pole triangular net")
    if tri_face is None or len(tri_face.Faces) != 1:
        errors.append("the corner's triangular face is not one face")
    # the member's collapsed row: six poles on the apex
    row = list(tri_net[0])[18:24]
    apex = (row[0] - row[-1]).Length
    checks.append("the member's collapsed row: %.3e mm" % apex)
    if apex > 1e-9:
        errors.append("the small triangular surface has no collapsed row")
    # the owner's spec: the FreeCAD replacement of that surface, when asked
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

    # THE JUNCTION AT THE CUT IS CLOSED: the corner fill's boundary IS each
    # blend's cut edge (path (B) left 0.2915 mm there).
    worst, why = _cut_residual(corner, strips)
    if worst is None:
        errors.append("the ring's boundary rows cannot be named: %s" % why)
    else:
        checks.append("the C0 at the cut: %.3e mm" % worst)
        if worst > TOL:
            errors.append("the corner fill does not meet the blends' cut "
                          "edges (%.3e mm)" % worst)

    # THE CUT IS THE LEADER'S DISTANCE FROM THE JUNCTION, read off the
    # patch's own intervals (not off the property name), and the band edge
    # it leaves behind is the setback (#128).
    for s in rolled:
        e2, ss2 = side_and_end(s, patch)
        ext = band_extent(patch, e2, ss2)
        if ext[0] is None:
            errors.append("%s: the band's extent cannot be read" % patch.Name)
            continue
        (lo, hi), _band, corner_end = ext
        away = lo if corner_end == 0 else 1.0 - hi
        checks.append("%s on %s: the junction at the %d end, the band's cut "
                      "starts %.4g from it (band edges %r %r, leader cuts "
                      "%r %r)"
                      % (s.Name, patch.Name, corner_end, away,
                         split_pair(patch, "U"), split_pair(patch, "V"),
                         leader_pair(patch, "U"), leader_pair(patch, "V")))
        if abs(away - 0.25) > 1e-9:
            errors.append("%s: the band's cut starts %.4g from the junction, "
                          "not the leader 0.25" % (s.Name, away))
        if 0.1 not in split_pair(patch, "U") and 0.1 not in split_pair(
                patch, "V"):
            errors.append("%s: the setback is gone from the member patch's "
                          "band edges" % patch.Name)
    return {"pass": not errors, "errors": errors, "checks": checks}


def test_the_default_corner_is_the_rolling_one(doc):
    """THE DEFAULT SWITCH (#119): a 3-valent corner builds the ROLLING
    construction, and the shipped one is the selectable fallback.

    The default (no `construction` argument) must:
      * cut the rolling leader -- as the member patch's own LEADER CUT, its
        band edge staying the setback (#128),
      * build the small triangular member, whose FACE is its own
        `CubicSurface_64` -- the construction the maintainer's files store
        (#119 follow-up; the FreeCAD filling is the selectable option and is
        pinned in `Tests/test_corner_choices.py`),
      * and differ from the fallback, pole for pole.

    The fallback (`construction="shipped"`) must leave the patches'
    band edges alone, must be reproducible, and must be the corner of
    before #119: its byte-identity is pinned by the legacy-chain parity test
    (`Tests/test_corner_blend.py::test_corner_blend_pole_parity_with_
    legacy_chain`) and by the member calibration
    (`Tests/test_triangular_member_calibration.py`).

    THE LEADER MOVES THE CORNER'S SHAPE -- a supporting reading, not the
    acceptance (a curvature spread does not make a rolled corner, ADR
    0006); it only says the cut is doing something to the surface.  It is
    read on the same two corners, because the rolling build REUSES the
    corner object of the ring it rolls: the shipped corner is built in its
    OWN document, so the comparison is between two different corners.
    (Measured: shipped 1.03694, rolling 1.8272.)

    One fixture and one second document for all of it: the design switch,
    the fallback's reproducibility, the band edges and the two shapes are
    the same question asked of two corners."""
    errors, checks = [], []
    _fixture(doc)
    strips = _strips(doc)
    patch = doc.getObject("PatchA")
    rolled = [s for s in strips if s.PatchA is patch or s.PatchB is patch]

    # the FALLBACK, in its own document: the shipped corner, untouched,
    # built twice
    sdoc = FreeCAD.newDocument("FallbackDoc")
    try:
        ccm.build_cube_corner_model(sdoc)
        sdoc.recompute()
        sdoc.recompute()
        sstrips = [sdoc.getObject(n) for n in ("B_AB", "B_BC", "B_CA")]
        shipped = create_corner_blend(*sstrips, name="Fallback",
                                      construction="shipped")
        sdoc.recompute()
        s_poles = [FreeCAD.Vector(v) for v in shipped.Poles]
        s_kmax, s_kmin, s_ratio = _spread(shipped)
        again = create_corner_blend(*sstrips, name="Fallback2",
                                    construction="shipped")
        sdoc.recompute()
        same_twice = all((a - b).Length < 1e-12 for a, b in
                         zip(s_poles, list(again.Poles)))
        checks.append("the shipped corner twice: %s"
                      % ("identical" if same_twice else "DIFFERENT"))
        if not same_twice:
            errors.append("the shipped corner is not reproducible")
        checks.append("the shipped corner: k_max %.6g, k_min %.6g, ratio %.6g"
                      % (s_kmax, s_kmin, s_ratio))
        for name in ("PatchA", "PatchB", "PatchC"):
            p = sdoc.getObject(name)
            if abs(p.USplit1 - 0.1) > 1e-12 or abs(p.VSplit1 - 0.1) > 1e-12:
                errors.append("the fallback moved %s's band edges" % name)
        checks.append("the fallback: the band edges are untouched")
    finally:
        FreeCAD.closeDocument(sdoc.Name)

    # the DEFAULT: the rolling construction
    FreeCAD.setActiveDocument(doc.Name)
    corner = create_corner_blend(*strips, name="Default")
    doc.recompute()
    if corner is None:
        return {"pass": False,
                "errors": ["the default corner did not build"],
                "checks": checks}
    from SilkCorner import corner_tri_face, corner_tri_net
    tri_face = corner_tri_face(corner)
    tri_net = corner_tri_net(corner)
    fill = doc.getObject("DefaultMemberFill")
    checks.append("the default corner: %d poles, %d face(s); corner-owned "
                  "tri: %d poles, %d face(s); a FreeCAD member filling: %s"
                  % (len(corner.Poles), len(corner.Shape.Faces),
                     len(tri_net[0]) if tri_net else 0,
                     len(tri_face.Faces) if tri_face is not None else 0,
                     getattr(fill, "Name", None)))
    if tri_net is None or tri_face is None:
        errors.append("the default corner carries no triangular member")
    if fill is not None:
        errors.append("the default corner built a FreeCAD member filling "
                      "(%s): the 64 is the default face" % fill.Name)
    # the leader moved the CUT, and the BAND EDGE is still the setback
    p = doc.getObject("PatchA")
    from SilkMachinery import leader_pair, split_pair
    checks.append("the cut: PatchA band edges %r %r, leader cuts %r %r"
                  % (split_pair(p, "U"), split_pair(p, "V"),
                     leader_pair(p, "U"), leader_pair(p, "V")))
    # #129/G5: the parameter is SOLVED from a length, and the default length
    # is the third, uncut seam's band width. On this fixture it is 0.10 mm,
    # so the leader is the 0.10 setback plus that leg: 0.20.
    for letter in ("U", "V"):
        near = [v for v in leader_pair(p, letter) if abs(v - 0.20) <= 1e-9]
        if not near:
            errors.append("the default corner did not cut the member patch's "
                          "%s leader (leader cuts %r)"
                          % (letter, leader_pair(p, letter)))
    for name in ("PatchA", "PatchB", "PatchC"):
        q = doc.getObject(name)
        if abs(q.USplit1 - 0.1) > 1e-12 or abs(q.VSplit1 - 0.1) > 1e-12:
            errors.append("the rolling construction moved %s's band edge -- "
                          "the setback must not ride along with the leader"
                          % name)
    # and it is NOT the shipped corner
    same = all((a - b).Length < 1e-12 for a, b in
               zip(s_poles, list(corner.Poles)))
    checks.append("the default corner is the shipped one: %s"
                  % ("yes" if same else "no"))
    if same:
        errors.append("the default corner is the shipped corner, pole for "
                      "pole")
    # ... and the leader moves the corner's SHAPE
    r_kmax, r_kmin, r_ratio = _spread(corner)
    checks.append("the rolling corner: k_max %.6g, k_min %.6g, ratio %.6g"
                  % (r_kmax, r_kmin, r_ratio))
    if abs(r_ratio - s_ratio) < 1e-6:
        errors.append("the leader did not move the corner's shape "
                      "(ratio %.6g both ways)" % s_ratio)
    return {"pass": not errors, "errors": errors, "checks": checks}


def test_the_leader_is_measured_from_the_junction_corner(doc):
    """The leader is a DISTANCE FROM THE JUNCTION, so a junction at the
    1 end of an axis mirrors the cut value (`1 - leader`).

    The GEOMETRY half -- the cut the stage writes lies the leader's distance
    from the junction on the member patch, the band edge it leaves behind is
    the setback -- is measured in
    `test_the_rolling_corner_builds_the_66_the_member_and_the_fill`, on the
    build it already makes.

    What is left here is the MIRROR, on the 2x2 model
    (`Tests/corner_model.py`), whose patches carry the junction at the 1 end
    of an axis: the arithmetic is the same expression the stage writes with
    (`_leader_cut_home`), called directly, because a 4-valent ring cannot
    build a rolling corner at all (#128: it has no third, uncut seam and no
    triangular remainder)."""
    errors, checks = [], []
    from SilkMachinery import band_extent
    from SilkBlend import side_and_end

    # (2) the mirror, on the 2x2 model's junction at the 1 end
    from SilkWorkflowOps import (_leader_cut_home, seam_default_leader,
                                 seam_leader)
    from Tests import corner_model as cm
    sdoc = FreeCAD.newDocument("MirrorDoc")
    try:
        FreeCAD.setActiveDocument(sdoc.Name)
        cm.build_corner_model(sdoc)
        sdoc.recompute()
        sdoc.recompute()
        mstrips = [sdoc.getObject(n) for n in ("B12", "B24", "B43", "B31")]
        target = None
        for s in mstrips:
            for p in (s.PatchA, s.PatchB):
                e, ss = side_and_end(s, p)
                ext = band_extent(p, e, ss)
                if ext[0] is not None and ext[2] == 1:
                    target = (s, p, e)
                    break
            if target is not None:
                break
        if target is None:
            errors.append("the 2x2 fixture carries no junction at the 1 end "
                          "of an axis")
        else:
            s, p, e = target
            prop, value, why = _leader_cut_home(s, p, 0.25)
            checks.append("the seam %s on %s carries the junction at the 1 "
                          "end: the cut goes to %s = %g (1 - leader)"
                          % (s.Name, p.Name, prop, value))
            if prop is None:
                errors.append("the cut's home cannot be named: %s" % why)
            elif abs(value - 0.75) > 1e-12:
                errors.append("a junction at the 1 end did not mirror the "
                              "leader: %s = %g, not 0.75" % (prop, value))
            if prop is not None:
                setattr(p, prop, value)
                sdoc.recompute()
                # #129: `seam_leader` reads the cut back as a LENGTH IN MM
                # along the seam (the panel's unit), so the fraction 0.25
                # written above reads back as the arc from the junction
                # corner to it -- which is what the same cut is asked for in
                # the stage's own unit.
                back, _why = seam_leader(s, p, construction="rolling")
                want, _w = seam_default_leader(s, p)
                checks.append("  read back through `seam_leader`: %r mm (the "
                              "same cut by the stage's own default, %r mm)"
                              % (back, want))
                if back is None or abs(back - want) > 1e-9:
                    errors.append("the cut reads back as %r mm, not the %r mm "
                                  "the same cut is worth along the seam"
                                  % (back, want))
    finally:
        FreeCAD.closeDocument(sdoc.Name)
        FreeCAD.setActiveDocument(doc.Name)
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



def test_the_default_cut_is_the_third_blend_band_width(doc):
    """G5: a fresh corner with no typed length takes the third seam's width.

    The third seam is the one NOT touching the triangular member's patch.
    Its band is measured on both of its patches, in mm, on the exact base
    surfaces; the geometric mean is the ONE target and both cut sides are
    placed at it (capped by reach). A setback is not written. The cube's
    third seam is 0.1 mm wide on both sides, so both cut sides are 0.1 mm.
    """
    import SilkWorkflowOps as OPS
    errors, checks = [], []
    _fixture(doc)
    strips = _strips(doc)
    pin, _why = SC_MEMBER_PIN(strips)
    patch = pin[0] if pin else doc.getObject("PatchA")
    info, why = OPS.third_band_widths(strips, patch)
    if info is None:
        return {"pass": False, "errors": [why], "checks": checks}
    before = {p.Name: (SM_SPLIT(p, "U"), SM_SPLIT(p, "V"))
              for p in (doc.getObject(n) for n in ("PatchA", "PatchB",
                                                  "PatchC"))}
    corner = create_corner_blend(*strips, name="ThirdBand")
    doc.recompute()
    legs = []
    for st in strips:
        if patch in (st.PatchA, st.PatchB):
            leg, _w = OPS.seam_cut_length(st, patch, ring=strips)
            legs.append(leg)
    after = {p.Name: (SM_SPLIT(p, "U"), SM_SPLIT(p, "V"))
             for p in (doc.getObject(n) for n in ("PatchA", "PatchB",
                                                  "PatchC"))}
    checks.append("third seam %s: widths %.9f / %.9f mm, target %.9f mm"
                  % (info["seam"].Name, info["widths"][0],
                     info["widths"][1], info["target"]))
    checks.append("cut sides %s mm; splits unchanged %s"
                  % (", ".join("%.9f" % v for v in legs), before == after))
    check(len(legs) == 2, "the member patch has %d rolled seams" % len(legs),
          errors)
    if len(legs) == 2:
        check(abs(legs[0] - legs[1]) <= 1e-9,
              "the cut sides differ by %.3e mm" % abs(legs[0] - legs[1]),
              errors)
        check(abs(legs[0] - info["target"]) <= 1e-9,
              "the default cut %.9f mm is not the third band %.9f mm"
              % (legs[0], info["target"]), errors)
    check(before == after, "a setback moved: %r -> %r" % (before, after),
          errors)
    return {"pass": not errors, "errors": errors, "checks": checks}

ALL_TESTS = [
    test_the_rolling_corner_builds_the_66_the_member_and_the_fill,
    test_the_default_corner_is_the_rolling_one,
    test_the_default_cut_is_the_third_blend_band_width,
    test_the_leader_is_measured_from_the_junction_corner,
    test_a_leader_outside_the_seam_is_refused_by_name,
]
