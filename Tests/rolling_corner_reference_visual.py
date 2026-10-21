"""
MANUAL VISUAL -- the corner stage's four pictures for the ring-parity ticket.

WHAT IS RENDERED, and what each picture is allowed to say.

  1. OUR corner.  The cube-corner fixture (`Tests/cube_corner_model.py`),
     built through the corner stage with the default construction -- the
     rolling corner -- at leader 0.25.  The 66 and the small triangular
     member beside it, the member's face being its own `CubicSurface_64`.

  2. THE REFERENCE's corner, rebuilt from the nets its own file stores.
     `Tests/prototype_reference_corner.py` proved those nets are reproduced
     pole for pole by our primitives, so drawing them is drawing the
     maintainer's geometry.  The `.FCStd` is read OFFLINE (stdlib only, see
     `Tests/reference_corner_diff.py`), so no reference document is opened in
     the user's GUI and none is needed.

  3. THE TRI AT TWO LEADERS, 0.25 and 0.5, on our fixture: the same corner,
     the member's cell smaller and larger, rendered from the same camera as
     (1).

THE CAMERA.  `Tests/g2_corner_roll_visual.py`'s fixed camera is stated in the
fixture's own coordinates (a 0.1 mm corner at the origin).  The reference's
geometry lives in ITS coordinates, tens of millimetres across and centred
elsewhere, so one literal camera cannot frame both usefully.  What is shared
is the camera RULE: the same direction (1, 1, 1), the same orientation
quaternion and the same relative distance and height, scaled to the subject's
own bounding box.  (2) is therefore the reference seen the way (1) sees ours,
not the reference through our fixture's millimetre window.

MEASUREMENTS PRINTED (they are the reason to keep the pictures honest):
the area, the bounding box and the normal-field flips of each surface.

MANUAL-ONLY: the file name is not `test_*.py`, so `Tests/suite.py` does not
discover it; `Tests/test_continuity_instrument.py` asserts every measurement
script carries `MANUAL = True`.

Run against the owner's running FreeCAD (the only run path -- never spawn a
window):

    flock /tmp/silk_rpc.lock -c \\
        "python3 Tests/rolling_corner_reference_visual.py"
"""

import os

import FreeCAD
import Part

import SilkChecks
from SilkWorkflowOps import create_corner_blend
from Tests import cube_corner_model as ccm
from Tests import reference_corner_diff as R
from Tests.g2_corner_roll_visual import (IMAGE_SIZE, BACKGROUND, set_camera,
                                         _gui_view, _quiesce, _only)

MANUAL = True

OUT_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "Resources", "Test_files", "_inspect")

# The camera RULE: `Tests/g2_corner_roll_visual.py`'s own direction and
# orientation, with the distance and the height scaled to the subject. Its
# fixed numbers frame a 0.1 mm corner at the origin; `CAMERA_SCALE` is the
# ratio they were chosen at (height 0.42 for a 0.1 mm corner), so a subject of
# any extent is framed the same way.
CAMERA_DIRECTION = (1.0, 1.0, 1.0)
CAMERA_ORIENTATION = (0.70710677, -0.70710677, 0.0, 2.186276)
CAMERA_HEIGHT_PER_EXTENT = 4.2
CAMERA_DISTANCE_PER_EXTENT = 9.0

LEADER = 0.25
OTHER_LEADER = 0.5


def _extent(shape):
    bb = shape.BoundBox
    return max(bb.XLength, bb.YLength, bb.ZLength) or 1.0


def _camera_for(view, shape):
    """`set_camera`'s rule, scaled to `shape`'s own extent and centre."""
    from pivy import coin
    bb = shape.BoundBox
    centre = FreeCAD.Vector((bb.XMin + bb.XMax) * 0.5,
                            (bb.YMin + bb.YMax) * 0.5,
                            (bb.ZMin + bb.ZMax) * 0.5)
    d = FreeCAD.Vector(*CAMERA_DIRECTION)
    d.normalize()
    view.setCameraType("Orthographic")
    cam = view.getCameraNode()
    target = centre
    distance = _extent(shape) * CAMERA_DISTANCE_PER_EXTENT
    p = target - d * distance
    cam.position.setValue(coin.SbVec3f(p.x, p.y, p.z))
    cam.orientation.setValue(coin.SbRotation(
        coin.SbVec3f(CAMERA_ORIENTATION[0], CAMERA_ORIENTATION[1],
                     CAMERA_ORIENTATION[2]), CAMERA_ORIENTATION[3]))
    cam.focalDistance.setValue(distance)
    cam.nearDistance.setValue(0.0)
    cam.farDistance.setValue(distance * 4.0)
    cam.height.setValue(_extent(shape) * CAMERA_HEIGHT_PER_EXTENT)
    view.redraw()


def _report(tag, shape):
    """Area, bbox and normal-field flips of one surface."""
    if shape is None or not shape.Faces:
        print("  %-24s (no face)" % tag)
        return
    flips = [len(SilkChecks._normal_field_flips(shape.Faces[0].Surface,
                                                n=n)[0])
             for n in (39, 81, 150)]
    bb = shape.BoundBox
    print("  %-24s area %10.6f  bbox (%8.3f %8.3f %8.3f)..(%8.3f %8.3f "
          "%8.3f)  flips %s"
          % (tag, shape.Area, bb.XMin, bb.YMin, bb.ZMin,
             bb.XMax, bb.YMax, bb.ZMax, flips))


def _save(doc_name, path):
    """One picture of `doc_name`'s 3D view."""
    view = _gui_view(doc_name)
    view.saveImage(path, IMAGE_SIZE[0], IMAGE_SIZE[1], BACKGROUND)
    print("  wrote %s" % path)


def _our_corner(leader, doc_name="_vis_ours", tri_only=False):
    """Build the cube corner + the corner stage's corner in a scratch doc.

    Returns the document name; the corner and the tri are the objects the
    render shows.  `tri_only` hides the 66 so the member's face can be
    judged on its own."""
    if doc_name in FreeCAD.listDocuments():
        FreeCAD.closeDocument(doc_name)
    doc = FreeCAD.newDocument(doc_name)
    FreeCAD.setActiveDocument(doc_name)
    ccm.build_cube_corner_model(doc)
    strips = [doc.getObject(n) for n in ("B_AB", "B_BC", "B_CA")]
    corner = create_corner_blend(*strips, leader=leader)
    doc.recompute()
    if corner is None:
        raise SystemExit("the corner stage refused the fixture")
    _quiesce(doc)
    names = [corner.Name]
    for o in doc.Objects:
        if getattr(o, "object_type", "") == "RollingMemberFace":
            names.append(o.Name)
    if not tri_only:
        _only(doc, *[corner.Name])
    _only(doc, *(names[-1:] if tri_only else [corner.Name]))
    doc.recompute()
    _report("our 66 (leader %g)" % leader, corner.Shape)
    tri = [o for o in doc.Objects
           if getattr(o, "object_type", "") == "RollingMemberFace"]
    if tri:
        _report("our tri (leader %g)" % leader, tri[0].Shape)
    return doc_name


def _reference_corner(doc_name="_vis_ref"):
    """The reference's own corner, drawn from the nets its file stores.

    Read offline, built with `Part` only: the stored 6x6 becomes a degree-3
    Bezier patch (the knot vector `CubicSurface_66` uses), the stored 6x4
    member becomes a `CubicSurface_64` patch.  Nothing of the reference is
    opened in the user's GUI, and nothing is written."""
    archive = R.Archive(R.default_reference("29"))
    corner = None
    for c in archive.corners():
        if c["kind"] == "quad-4sub" and c.get("member_grid"):
            corner = c
            break
    if corner is None:
        raise SystemExit("no reference corner with a triangular member")
    quad_node = archive.get(corner["root"])
    grid_node = archive.get(corner["grid"])
    member_node = archive.get(corner["member_grid"])
    tri_node = archive.get(corner["tri"])

    def net(node):
        return ([FreeCAD.Vector(*p) for p in node.poles],
                list(node.weights or [1.0] * len(node.poles)))

    def patch(poles, weights, nv):
        s = Part.BSplineSurface()
        s.increaseDegree(3, 3)
        for knot, mult in ((0.0, 4), (1.0 / 3.0, 1), (2.0 / 3.0, 1),
                           (1.0, 4)):
            s.insertUKnot(knot, mult, 1e-7)
        for knot, mult in (((0.0, 4), (1.0 / 3.0, 1), (2.0 / 3.0, 1),
                            (1.0, 4)) if nv == 6 else ((0.0, 4), (1.0, 4))):
            s.insertVKnot(knot, mult, 1e-7)
        for v in range(nv):
            for u in range(6):
                s.setPole(u + 1, v + 1, poles[v * 6 + u], weights[v * 6 + u])
        return s.toShape()

    if doc_name in FreeCAD.listDocuments():
        FreeCAD.closeDocument(doc_name)
    doc = FreeCAD.newDocument(doc_name)
    FreeCAD.setActiveDocument(doc_name)
    qp, qw = net(grid_node)
    quad = doc.addObject("Part::Feature", "RefQuad")
    quad.Shape = patch(qp, qw, 6)
    mp, mw = net(member_node)
    tri = doc.addObject("Part::Feature", "RefTri")
    tri.Shape = patch(mp, mw, 4)
    doc.recompute()
    _report("reference 66 (%s)" % quad_node.name, quad.Shape)
    _report("reference tri (%s)" % member_node.name, tri.Shape)
    if tri_node is not None:
        print("  the reference's own tri face object: %s" % tri_node.name)
    return doc_name


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    print("the corner stage's pictures -- the camera RULE of "
          "Tests/g2_corner_roll_visual.py (direction %s, orientation %s), "
          "scaled per subject" % (CAMERA_DIRECTION, CAMERA_ORIENTATION))

    ours = _our_corner(LEADER, "_vis_ours")
    corner = [o for o in FreeCAD.listDocuments()[ours].Objects
              if getattr(o, "object_type", "") == "CornerBlend"][0]
    view = _gui_view(ours)
    _camera_for(view, corner.Shape)
    _save(ours, os.path.join(OUT_DIR, "ringref_1_ours.png"))

    ours50 = _our_corner(OTHER_LEADER, "_vis_ours50")
    corner50 = [o for o in FreeCAD.listDocuments()[ours50].Objects
                if getattr(o, "object_type", "") == "CornerBlend"][0]
    view = _gui_view(ours50)
    _camera_for(view, corner50.Shape)
    _save(ours50, os.path.join(OUT_DIR, "ringref_2_ours_leader050.png"))

    ours_tri = _our_corner(LEADER, "_vis_tri", tri_only=True)
    tri = [o for o in FreeCAD.listDocuments()[ours_tri].Objects
           if getattr(o, "object_type", "") == "RollingMemberFace"][0]
    view = _gui_view(ours_tri)
    _camera_for(view, tri.Shape)
    _save(ours_tri, os.path.join(OUT_DIR, "ringref_3_tri_leader025.png"))

    ours_tri50 = _our_corner(OTHER_LEADER, "_vis_tri50", tri_only=True)
    tri50 = [o for o in FreeCAD.listDocuments()[ours_tri50].Objects
             if getattr(o, "object_type", "") == "RollingMemberFace"][0]
    view = _gui_view(ours_tri50)
    _camera_for(view, tri50.Shape)
    _save(ours_tri50, os.path.join(OUT_DIR, "ringref_4_tri_leader050.png"))

    ref = _reference_corner("_vis_ref")
    quad = FreeCAD.listDocuments()[ref].getObject("RefQuad")
    view = _gui_view(ref)
    _camera_for(view, quad.Shape)
    _save(ref, os.path.join(OUT_DIR, "ringref_5_reference.png"))

    for name in (ours, ours50, ours_tri, ours_tri50, ref):
        try:
            FreeCAD.closeDocument(name)
        except Exception:
            pass
    print("")
    print("the tri at two leaders: 0.25 vs 0.5 -- the member's cell and its "
          "face area are in the lines above; the ringref_3 / ringref_4 "
          "pictures are the two the eye can compare.")


if __name__ == "__main__":
    main()
