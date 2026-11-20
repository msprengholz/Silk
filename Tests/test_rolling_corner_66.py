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
SM_LEADER = SM_SPLIT_SHIM.leader_pair

from SilkWorkflowOps import (create_corner_blend, create_rolling_corner_66,
                             corner_fill_boundary, MEMBER_FACE_FILL)
from Tests import cube_corner_model as ccm
from Tests.mcp_harness import check

TOL = 1e-9          # mm: the cut edge and the corner fill share it
OPS_FILL_BAR = 1.0  # deg: FILL_NORMAL_GAP_TOL_DEG, the shipped #121 bar


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
        checks.append("the FreeCAD replacement: %s, %d face(s), order %r, "
                      "gap %r deg (bar %.1f deg)"
                      % (res["member_fill"].Name,
                         len(res["member_fill"].Shape.Faces),
                         res.get("member_fill_order"),
                         (res["member_fill_gap"] or {}).get("max_gap_deg"),
                         OPS_FILL_BAR))
        check(res.get("member_fill_order") == 1,
              "order 1 was not reached on the cube: %r"
              % res.get("member_fill_order"), errors)
        gap = (res.get("member_fill_gap") or {}).get("max_gap_deg")
        check(gap is not None and gap <= OPS_FILL_BAR,
              "the G1 fill gap %.3f deg is above the %.1f deg bar"
              % (gap if gap is not None else float("inf"), OPS_FILL_BAR),
              errors)
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
    # THE DERIVED PLACEMENT: each seam's own 0.1 band is the setback and the
    # two cut sides are equalised at 0.1 mm, so on this 1 mm fixture the
    # leaders read 0.2 and the band edges stay 0.1 / 0.9 (no constant is
    # written: the band edges are the user's, #64).
    for letter in ("U", "V"):
        near = [v for v in leader_pair(p, letter) if abs(v - 0.2) <= 1e-9]
        if not near:
            errors.append("the default corner did not derive its %s cut from "
                          "the seam's 0.1 band (leader cuts %r)"
                          % (letter, leader_pair(p, letter)))
    for name in ("PatchA", "PatchB", "PatchC"):
        q = doc.getObject(name)
        if abs(q.USplit1 - 0.1) > 1e-12 \
                or abs(q.VSplit1 - 0.1) > 1e-12:
            errors.append("the rolling construction moved the user's band "
                          "edge on %s (%r / %r)"
                          % (name, split_pair(q, "U"), split_pair(q, "V")))
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



def test_the_default_cut_is_derived_from_the_seams_own_band(doc):
    """With nothing typed the corner consumes each seam's own band width:
    setback 0.1 (unchanged), cut side 0.1 mm, leader 0.2 on this 1 mm cube.

    WOULD BE RED IF: the cut came from the third band again (the G5 rule), a
    global 1/16 / 1/4 constant were written, or widening the third blend
    moved the cut.
    """
    import SilkWorkflowOps as OPS
    errors, checks = [], []
    _fixture(doc)
    strips = _strips(doc)
    corner = create_corner_blend(*strips, name="Derived")
    doc.recompute()
    doc.recompute()
    pin, _why = SC_MEMBER_PIN(strips)
    patch = pin[0] if pin else doc.getObject("PatchA")
    cuts = {L: SM_LEADER(patch, L) for L in ("U", "V")}
    splits = {L: SM_SPLIT(patch, L) for L in ("U", "V")}
    checks.append("member patch %s: leader cuts %r, band edges %r"
                  % (patch.Name, cuts, splits))
    for letter in ("U", "V"):
        values = [v for v in cuts[letter] if 0.0 < v < 1.0]
        check(any(abs(v - 0.2) <= 1e-9 for v in values),
              "the %s cut was not derived from the 0.1 band (%r)"
              % (letter, cuts[letter]), errors)
        check(any(abs(v - 0.1) <= 1e-9 for v in splits[letter]),
              "the %s band edge was rewritten (%r)"
              % (letter, splits[letter]), errors)
    # the third blend's band is NOT the lever any more
    from SilkBlend import side_and_end, band_edge_prop
    third = [s for s in strips
             if patch not in (s.PatchA, s.PatchB)][0]
    for q in (third.PatchA, third.PatchB):
        e, ss = side_and_end(third, q)
        letter = "U" if e[0] == "V" else "V"
        prop = band_edge_prop(letter, ss)
        setattr(q, prop, 0.4 if ss == 0 else 0.6)
    doc.recompute()
    doc.recompute()
    after = {L: SM_LEADER(patch, L) for L in ("U", "V")}
    checks.append("after widening the third blend: leader cuts %r" % (after,))
    for letter in ("U", "V"):
        before_v = [v for v in cuts[letter] if 0.0 < v < 1.0]
        after_v = [v for v in after[letter] if 0.0 < v < 1.0]
        check(len(before_v) == len(after_v)
              and all(abs(a - b) <= 1e-9
                      for a, b in zip(before_v, after_v)),
              "the %s cut followed the third blend's band (%r -> %r) -- "
              "the placement reads this patch's own two seams"
              % (letter, cuts[letter], after[letter]), errors)
    return {"pass": not errors, "errors": errors, "checks": checks}


def test_the_g1_fill_gap_on_the_curved_demo_corner(doc):
    """#128's measured reading: neighbour supports, order 1, curved corner.

    The cube is planar and reads 0 deg at any order, so it cannot prove G1.
    This builds the demo's `CB_J1_FrontTopRight` with `member_face="fill"`,
    reads the tangent-plane gap on all three neighbour supports and pins the
    instrument's floor (`solve_uv`: 4.5e-13 mm of residual) beside the bar.
    """
    import Tests.demo01_fixture_model as DEMO
    import SilkWorkflowOps as OPS
    errors, checks = [], []
    DEMO.build(doc, corners=False)
    doc.recompute()
    doc.recompute()
    strips = [doc.getObject(n) for n in ("B_FT", "B_FR", "B_TR")]
    corner = OPS.create_corner_blend(*strips, name="CurvedFill",
                                     member_face=MEMBER_FACE_FILL)
    doc.recompute()
    doc.recompute()
    fills = [o for o in doc.Objects
             if getattr(o, "TypeId", "") == "Surface::Filling"]
    fill = fills[0] if fills else None
    if corner is None or fill is None:
        return {"pass": False,
                "errors": ["the curved G1 fill was not built"],
                "checks": checks}
    patch = getattr(corner, "MemberPatch", None)
    if patch is None:
        found, _why = SC_MEMBER_PIN(strips)
        patch = found[0] if found else None
    boundary, why = OPS.member_fill_boundary(corner, patch)
    if boundary is None:
        return {"pass": False, "errors": [why], "checks": checks}
    links, supports = boundary
    gap = OPS.fill_normal_gap(fill, links, supports) or {}
    order = int(list(fill.BoundaryOrder or [0])[0])
    checks.append("curved fill: order %r, gap %.6g deg (bar %.1f deg), "
                  "floor 4.5e-13 mm of parameter residual"
                  % (order, gap.get("max_gap_deg", float("inf")),
                     OPS_FILL_BAR))
    for row in gap.get("per_edge", []):
        checks.append("  %s: gap %r deg, residual %.3e mm, reference %.3e mm"
                      % (row.get("label"), row.get("gap_deg"),
                         row.get("residual", 0.0),
                         row.get("ref_residual", 0.0)))
    check(order == 1, "the curved fill reached order %r, not 1" % order,
          errors)
    check(bool(gap.get("measurable")),
          "no gap station was measurable on the curved fill", errors)
    check(gap.get("max_gap_deg", float("inf")) <= OPS_FILL_BAR,
          "the curved fill's gap %.6g deg is above the %.1f deg bar"
          % (gap.get("max_gap_deg", float("inf")), OPS_FILL_BAR), errors)
    return {"pass": not errors, "errors": errors, "checks": checks}

ALL_TESTS = [
    test_the_rolling_corner_builds_the_66_the_member_and_the_fill,
    test_the_default_corner_is_the_rolling_one,
    test_the_default_cut_is_derived_from_the_seams_own_band,
    test_the_g1_fill_gap_on_the_curved_demo_corner,
    test_the_leader_is_measured_from_the_junction_corner,
    test_a_leader_outside_the_seam_is_refused_by_name,
]
