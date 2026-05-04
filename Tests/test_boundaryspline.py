"""
Tests for new BoundarySpline FeaturePython object.
Each test takes a FreeCAD doc and returns {"pass": bool, "errors": [str, ...], "checks": [...]}
"""
import FreeCAD
import Part
from FreeCAD import Gui


def check(cond, msg, errors):
    if not cond:
        errors.append(msg)
    return cond


def test_boundaryspline_3l(doc):
    """Create BoundarySpline from sketch with 3 visible line segments."""
    errors, checks = [], []

    # Ensure the module is loaded
    import BoundarySpline
    from FreeCAD import Gui

    # Create a 3-line sketch
    sk = doc.addObject("Sketcher::SketchObject", "Sketch")
    sk.Placement = FreeCAD.Placement(FreeCAD.Vector(0,0,0), FreeCAD.Rotation(0,0,0))
    sk.addGeometry([
        Part.LineSegment(FreeCAD.Vector(0,0,0), FreeCAD.Vector(16,0,0)),
        Part.LineSegment(FreeCAD.Vector(16,0,0), FreeCAD.Vector(33,0,0)),
        Part.LineSegment(FreeCAD.Vector(33,0,0), FreeCAD.Vector(50,0,0)),
    ])
    doc.recompute()

    # Call command directly (in-session Gui.addCommand doesn't replace cached registration)
    Gui.Selection.clearSelection()
    Gui.Selection.addSelection(sk)
    cmd = BoundarySpline.CreateBoundarySpline()
    cmd.Activated()

    # Should find exactly one BoundarySpline with 4 poles
    bs_list = [o for o in doc.Objects if o.Name.startswith("BoundarySpline") and hasattr(o, "Poles")]
    check(len(bs_list) == 1, f"Expected 1 BoundarySpline, got {len(bs_list)}", errors)
    if bs_list:
        bs = bs_list[0]
        check(len(bs.Poles) == 4, f"Expected 4 poles, got {len(bs.Poles)}", errors)
        check(bs.Shape is not None, "BoundarySpline has no Shape", errors)
        checks.append(f"BoundarySpline created with {len(bs.Poles)} poles")

    return {"pass": len(errors) == 0, "errors": errors, "checks": checks}
