"""Regenerate `Resources/Test_files/Silk_CornerCube_Rolling.FCStd`.

**What it is.** A file the owner can OPEN and SEE the rolling corner working:
the cube-corner fixture's three surfaces, their three blends, and the corner
built with the **rolling** construction -- the cut-cell 66 plus the triangular
member whose face is a FreeCAD `Surface::Filling` (the maintainer's own last
step, `Silk_CopyPasta_27_First_Corner_Rolled.FCStd`).

**Why it exists.** The rolling construction is the DEFAULT for a 3-valent
corner since #119, but on the owner's own model it is **refused** (the band on
one patch carries two corner cells, so the leader has no single junction corner
to sit on) and the corner falls back to the shipped construction. So the
default is not visible on that model, and the owner asked for a file where it
demonstrably works. This is that file: the same construction, on the fixture
where it builds.

**The control grids are OFF** on every object, so what you see is the SHAPE,
not the net -- and it exercises the display path (a grid toggle must not
rebuild the geometry, and the document must settle).

Run (it builds real geometry, so it needs FreeCAD):

    freecadcmd Tests/make_rolling_corner_fixture.py

or, against the running GUI:

    import Tests.make_rolling_corner_fixture as m; m.main()
"""

import os

import FreeCAD

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
OUT = os.path.join(REPO, "Resources", "Test_files",
                    "Silk_CornerCube_Rolling.FCStd")

# The leader the maintainer uses (0.25 of the way along the seam curve).
LEADER = 0.25


def _hide_grids(doc):
    """Turn the control grids off everywhere, and the control polygons too.

    The grid is a VIEW node (#108), so this is a display-only change -- and it
    must not rebuild anything (the whole point of #125).
    """
    for obj in doc.Objects:
        for prop in ("ShowGrid", "ShowSurface"):
            if hasattr(obj, prop):
                try:
                    setattr(obj, prop, False)
                except Exception:
                    pass
        if hasattr(obj, "ShowPolygon"):
            try:
                obj.ShowPolygon = False
            except Exception:
                pass
    doc.recompute()


def build_fixture(path=OUT, verbose=True):
    """Build the cube corner with the ROLLING construction and save it."""
    from Tests import cube_corner_model as ccm
    from SilkWorkflowOps import create_corner_blend

    doc = FreeCAD.newDocument("Silk_CornerCube_Rolling")
    try:
        ccm.build_cube_corner_model(doc)
        doc.recompute()
        doc.recompute()
        strips = [doc.getObject(n) for n in ("B_AB", "B_BC", "B_CA")]
        strips = [s for s in strips if s is not None]
        if len(strips) != 3:
            raise RuntimeError("the cube corner did not build its 3 blends "
                               "(got %r)" % (strips,))
        corner = create_corner_blend(*strips, name="RollingCorner",
                                     leader=LEADER)
        if corner is None:
            raise RuntimeError("the rolling corner was not built")
        doc.recompute()
        _hide_grids(doc)
        doc.recompute()
        if path:
            doc.saveAs(path)
        if verbose:
            print("wrote %s" % path)
            print("  objects: %s" % ", ".join(
                "%s(%s)" % (o.Name, getattr(o, "object_type", o.TypeId))
                for o in doc.Objects if getattr(o, "object_type", "")))
            print("  corner: %s, %d poles" % (corner.Name, len(corner.Poles)))
        return doc
    finally:
        try:
            FreeCAD.closeDocument(doc.Name)
        except Exception:
            pass


def verify_fixture(path=OUT, verbose=True):
    """Re-open the saved file and report what it carries."""
    doc = FreeCAD.openDocument(path)
    try:
        counts = {}
        for obj in doc.Objects:
            kind = getattr(obj, "object_type", None)
            if kind:
                counts[kind] = counts.get(kind, 0) + 1
        if verbose:
            print("%s carries %s" % (os.path.basename(path), counts))
        return counts
    finally:
        try:
            FreeCAD.closeDocument(doc.Name)
        except Exception:
            pass


def main():
    build_fixture()
    verify_fixture()


if __name__ == "__main__":
    main()
