"""
MANUAL VISUAL -- the TWO-PATCH corner (#128), beside the maintainer's own.

WHAT IS RENDERED, and what each picture is allowed to say.

  1. OUR corner.  The cube-corner fixture (`Tests/cube_corner_model.py`),
     built through the corner stage's DEFAULT construction: the rolling
     corner, whose leader is the MEMBER PATCH's own cut.  The 66 stops at the
     member's cell, and the small triangular surface (`CubicSurface_64` over
     the member net) sits beside it -- the maintainer's two surfaces.
  2. THE TRI alone, from the same camera, so the cell it covers can be read
     against the quad around it.
  3. THE REFERENCE's corner, rebuilt from the nets its own file stores
     (`Tests/reference_corner_diff.Archive` reads the `.FCStd` offline, stdlib
     only; nothing of the owner's GUI is opened or written).

THE CAMERA.  `Tests/rolling_corner_reference_visual.py`'s rule: the same
direction (1, 1, 1) and the same orientation quaternion as
`Tests/g2_corner_roll_visual.py`'s fixed camera, with the distance and the
height scaled to the subject's own bounding box.  The reference's geometry is
tens of millimetres across and centred elsewhere, so one literal camera cannot
frame both; the rule is what is shared.

MEASUREMENTS PRINTED (they are the reason the pictures are worth trusting):
area, bounding box and normal-field flips of each surface.

MANUAL-ONLY: the file name is not `test_*.py`, so `Tests/suite.py` does not
discover it; `Tests/test_continuity_instrument.py` asserts every measurement
script carries `MANUAL = True` and exposes `main`.

Run against the owner's running FreeCAD (the only run path -- never spawn a
window):

    flock /tmp/silk_rpc.lock -c "python3 Tests/two_patch_corner_visual.py"
"""

import os

import FreeCAD

from SilkWorkflowOps import create_corner_blend
from Tests import cube_corner_model as ccm
from Tests import rolling_corner_reference_visual as ref

MANUAL = True

OUT_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "Resources", "Test_files", "_inspect")

CORNER_RGB = (0.92, 0.55, 0.15)
MEMBER_RGB = (0.20, 0.45, 0.95)

STRIP_NAMES = ("B_AB", "B_BC", "B_CA")


def _ours(doc_name="_vis_twopatch"):
    """The cube corner + the corner stage's default (rolling) corner."""
    if doc_name in FreeCAD.listDocuments():
        FreeCAD.closeDocument(doc_name)
    doc = FreeCAD.newDocument(doc_name)
    FreeCAD.setActiveDocument(doc_name)
    ccm.build_cube_corner_model(doc)
    doc.recompute()
    doc.recompute()
    strips = [doc.getObject(n) for n in STRIP_NAMES]
    corner = create_corner_blend(*strips, name="TwoPatch")
    doc.recompute()
    if corner is None:
        raise SystemExit("the corner stage refused the fixture")
    from Tests.g2_corner_roll_visual import _quiesce
    _quiesce(doc)
    corner.ViewObject.ShapeColor = CORNER_RGB
    corner.ViewObject.Transparency = 0
    member = [o for o in doc.Objects
              if getattr(o, "object_type", "") == "RollingMemberFace"]
    if member:
        member[0].ViewObject.ShapeColor = MEMBER_RGB
        member[0].ViewObject.Transparency = 0
    ref._report("our 66 (rolling)", corner.Shape)
    if member:
        ref._report("our tri (the member)", member[0].Shape)
    return doc_name, corner, (member[0] if member else None)


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    print("the two-patch corner -- the camera RULE of "
          "Tests/g2_corner_roll_visual.py (direction %s, orientation %s), "
          "scaled per subject" % (ref.CAMERA_DIRECTION,
                                  ref.CAMERA_ORIENTATION))
    from Tests.g2_corner_roll_visual import _gui_view, _only

    ours, corner, member = _ours()
    view = _gui_view(ours)
    ref._camera_for(view, corner.Shape)
    _only(FreeCAD.listDocuments()[ours], corner.Name,
          *([member.Name] if member is not None else []))
    view.redraw()
    ref._save(ours, os.path.join(OUT_DIR, "twopatch_1_ours.png"))
    if member is not None:
        _only(FreeCAD.listDocuments()[ours], member.Name)
        view = _gui_view(ours)
        ref._camera_for(view, member.Shape)
        view.redraw()
        ref._save(ours, os.path.join(OUT_DIR, "twopatch_2_tri.png"))

    reference = ref._reference_corner("_vis_twopatch_ref")
    quad = FreeCAD.listDocuments()[reference].getObject("RefQuad")
    rview = _gui_view(reference)
    ref._camera_for(rview, quad.Shape)
    rview.redraw()
    ref._save(reference, os.path.join(OUT_DIR, "twopatch_3_reference.png"))

    for name in (ours, reference):
        try:
            FreeCAD.closeDocument(name)
        except Exception:
            pass
    print("")
    print("the pictures are one camera RULE apart, not one camera: the "
          "reference's geometry lives in its own coordinates (tens of mm "
          "across), ours is the fixture's 0.25 mm corner.")


if __name__ == "__main__":
    main()
