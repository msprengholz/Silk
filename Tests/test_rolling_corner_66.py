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

from SilkWorkflowOps import (create_corner_blend, create_rolling_corner_66,
                             corner_fill_boundary, MEMBER_FACE_FILL)
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
    """Path (A) builds all three surfaces the maintainer's file carries:
    the 66, the small triangular member, and -- AS THE OPTION -- its FreeCAD
    `Surface::Filling` replacement.

    The default is the member's own `CubicSurface_64` (the construction the
    maintainer's files store), so the fill is built here by asking for it BY
    NAME. `Tests/test_corner_choices.py` pins the default and the pair of
    reachable faces."""
    errors, checks = [], []
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
    return {"pass": not errors, "errors": errors, "checks": checks}


def test_the_leader_moves_the_corner_s_shape(doc):
    """(A SUPPORTING READING, not the acceptance) The leader must change the
    corner's shape, however the construction is judged.

    The previous build measured the same spread (1.036938) with and
    without its leader.  Here the leader is the band's own corner-side
    cut, so the corner's spread MUST move.  A curvature spread does not
    make a rolled corner (ADR 0006); it only says the cut is doing
    something to the surface.

    THE TWO CORNERS ARE TWO OBJECTS.  The rolling build REUSES the
    corner object of the ring it rolls -- the corner follows the
    leader -- so the shipped corner is built in its OWN document and
    the comparison is between two different corners, never a corner
    against itself."""
    errors, checks = [], []
    _fixture(doc)
    strips = _strips(doc)
    # the shipped corner, in its own document
    sdoc = FreeCAD.newDocument("ShippedCornerDoc")
    try:
        ccm.build_cube_corner_model(sdoc)
        sdoc.recompute()
        sdoc.recompute()
        sstrips = [sdoc.getObject(n) for n in ("B_AB", "B_BC", "B_CA")]
        shipped = create_corner_blend(*sstrips, name="Shipped",
                                      construction="shipped")
        sdoc.recompute()
        s_kmax, s_kmin, s_ratio = _spread(shipped)
        s_poles = [FreeCAD.Vector(v) for v in shipped.Poles]
        checks.append("the shipped corner: k_max %.6g, k_min %.6g, ratio %.6g"
                      % (s_kmax, s_kmin, s_ratio))
        patch = doc.getObject("PatchA")
        rolled = [s for s in strips
                  if s.PatchA is patch or s.PatchB is patch]
        # the ops layer builds into the ACTIVE document
        FreeCAD.setActiveDocument(doc.Name)
        res = create_rolling_corner_66(strips, patch, leader=0.25,
                                       seams=rolled, name="Roll")
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
                   zip(s_poles, list(res["corner"].Poles)))
        checks.append("the poles are the shipped ones: %s"
                      % ("yes" if same else "no"))
        if same:
            errors.append("the rolling corner is the shipped corner, pole "
                          "for pole")
        return {"pass": not errors, "errors": errors, "checks": checks}
    finally:
        FreeCAD.closeDocument(sdoc.Name)


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
    """The FALLBACK path is untouched: no rolling construction, no change.

    Since #119 the corner stage's DEFAULT is the rolling construction,
    so the shipped 66-with-the-spiderweb-member is selected BY NAME
    (`construction="shipped"`).  This test pins that path: it is
    reproducible, and it does not touch the patches' band edges."""
    errors, checks = [], []
    _fixture(doc)
    strips = _strips(doc)
    first = create_corner_blend(*strips, name="Shipped1",
                               construction="shipped")
    doc.recompute()
    poles = [FreeCAD.Vector(v) for v in first.Poles]
    second = create_corner_blend(*strips, name="Shipped2",
                                construction="shipped")
    doc.recompute()
    same = all((a - b).Length < 1e-12 for a, b in
               zip(poles, list(second.Poles)))
    checks.append("the shipped corner twice: %s"
                  % ("identical" if same else "DIFFERENT"))
    if not same:
        errors.append("the shipped corner is not reproducible")
    # and the patches' band edges are untouched by the shipped corner
    for name in ("PatchA", "PatchB", "PatchC"):
        p = doc.getObject(name)
        if abs(p.USplit1 - 0.1) > 1e-12 or abs(p.VSplit1 - 0.1) > 1e-12:
            errors.append("%s's band edges moved without the rolling "
                          "construction" % name)
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
    band edges alone: it is the construction of before #119, and its
    byte-identity is pinned by the legacy-chain parity test
    (`Tests/test_corner_blend.py::test_corner_blend_pole_parity_with_
    legacy_chain`) and by the member calibration
    (`Tests/test_triangular_member_calibration.py`)."""
    errors, checks = [], []
    _fixture(doc)
    strips = _strips(doc)
    patch = doc.getObject("PatchA")
    rolled = [s for s in strips if s.PatchA is patch or s.PatchB is patch]

    # the FALLBACK, in its own document: the shipped corner, untouched
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
    member = doc.getObject("DefaultMember")
    fill = doc.getObject("DefaultMemberFill")
    checks.append("the default corner: %d poles, %d face(s); the member: %s "
                  "(%d face(s)); a FreeCAD member filling: %s"
                  % (len(corner.Poles), len(corner.Shape.Faces),
                     getattr(member, "Name", None),
                     len(member.Shape.Faces) if member is not None
                     and member.Shape else 0,
                     getattr(fill, "Name", None)))
    if member is None:
        errors.append("the default corner built no triangular member")
    elif not member.Shape or len(member.Shape.Faces) != 1:
        errors.append("the default corner's triangular member is not one "
                      "face -- its `CubicSurface_64` is the tri")
    if fill is not None:
        errors.append("the default corner built a FreeCAD member filling "
                      "(%s): the 64 is the default face" % fill.Name)
    # the leader moved the CUT, and the BAND EDGE is still the setback
    p = doc.getObject("PatchA")
    from SilkMachinery import leader_pair, split_pair
    checks.append("the cut: PatchA band edges %r %r, leader cuts %r %r"
                  % (split_pair(p, "U"), split_pair(p, "V"),
                     leader_pair(p, "U"), leader_pair(p, "V")))
    # #129: the parameter is now SOLVED from a length, so it is compared to
    # its value, not to its float.  On this fixture (1 mm axes) the cut side
    # the equalising rule makes is 0.15 mm, which lands on 0.25 -- the same
    # corner the parameter default always built, to the last bit.
    for letter in ("U", "V"):
        near = [v for v in leader_pair(p, letter) if abs(v - 0.25) <= 1e-9]
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
    return {"pass": not errors, "errors": errors, "checks": checks}


def test_the_leader_is_measured_from_the_junction_corner(doc):
    """The leader is a DISTANCE FROM THE JUNCTION, so a junction at the
    1 end of an axis mirrors the cut value (`1 - leader`).

    Two halves, because one fixture cannot carry both:

      * the GEOMETRY, on the cube corner: the cut the stage writes lies the
        leader's distance from the junction on the member patch, and the
        band edge it leaves behind is the setback -- read off the patch's own
        intervals, not off the property name;
      * the MIRROR, on the 2x2 model (`Tests/corner_model.py`), whose
        patches carry the junction at the 1 end of an axis: the arithmetic
        is the same expression the stage writes with (`_leader_cut_home`),
        called directly, because a 4-valent ring cannot build a rolling
        corner at all (#128: it has no third, uncut seam and no
        triangular remainder).
    """
    errors, checks = [], []
    from SilkBlend import side_and_end
    from SilkMachinery import band_extent, leader_pair, split_pair

    # (1) the geometry, on the cube corner
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
    for s in rolled:
        e2, ss2 = side_and_end(s, patch)
        ext = band_extent(patch, e2, ss2)
        if ext[0] is None:
            errors.append("%s: the band's extent cannot be read" % patch.Name)
            continue
        (lo, hi), (band_lo, band_hi), corner_end = ext
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
