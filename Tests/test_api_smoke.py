"""
API validation tests for v1-1 Silk workbench.
Each function takes a FreeCAD document and returns {"pass": bool, "errors": [...], ...}.

Run via: from Tests.mcp_harness import run_tests; run_tests(test_1, test_2, ...)
"""

import FreeCAD
import Part
from FreeCAD import Gui


def check(condition, msg, errors):
    """Append msg to errors if condition is False."""
    if not condition:
        errors.append(msg)
    return condition


def test_controlpoly4_3_lines(doc):
    """ControlPoly4 from sketch with exactly 3 visible line segments."""
    errors = []
    checks = []

    sketch = doc.addObject("Sketcher::SketchObject", "Sketch")
    sketch.Placement = FreeCAD.Placement(
        FreeCAD.Vector(0, 0, 0),
        FreeCAD.Rotation(90, 0, 90)
    )
    geo = [
        Part.LineSegment(FreeCAD.Vector(0, 40, 0), FreeCAD.Vector(25, 40, 0)),
        Part.LineSegment(FreeCAD.Vector(25, 40, 0), FreeCAD.Vector(50, 15, 0)),
        Part.LineSegment(FreeCAD.Vector(50, 15, 0), FreeCAD.Vector(50, 0, 0))
    ]
    sketch.addGeometry(geo)
    doc.recompute()

    Gui.Selection.clearSelection()
    Gui.Selection.addSelection(sketch)
    ok = Gui.runCommand("ControlPoly4")
    check(ok is not False, "ControlPoly4 command failed", errors)

    polys = [obj for obj in doc.Objects
             if obj.Name.startswith("ControlPoly4") and hasattr(obj, "Poles")]
    check(len(polys) >= 1, f"Expected >=1 ControlPoly4, got {len(polys)}", errors)
    if polys:
        checks.append(f"Created {polys[0].Name} with {len(polys[0].Poles)} poles")
        check(len(polys[0].Poles) == 4, f"Expected 4 poles, got {len(polys[0].Poles)}", errors)

    return {"pass": len(errors) == 0, "errors": errors, "checks": checks}


def test_controlpoly4_first_element(doc):
    """ControlPoly4 in FirstElement mode (sketch with !=3 visible lines)."""
    errors = []
    checks = []

    sketch = doc.addObject("Sketcher::SketchObject", "Sketch")
    sketch.Placement = FreeCAD.Placement(
        FreeCAD.Vector(0, 0, 0),
        FreeCAD.Rotation(90, 0, 90)
    )
    # One line only — triggers FirstElement mode
    geo = [
        Part.LineSegment(FreeCAD.Vector(0, 40, 0), FreeCAD.Vector(50, 0, 0))
    ]
    sketch.addGeometry(geo)
    doc.recompute()

    Gui.Selection.clearSelection()
    Gui.Selection.addSelection(sketch)
    ok = Gui.runCommand("ControlPoly4")
    check(ok is not False, "ControlPoly4 FirstElement command failed", errors)

    polys = [obj for obj in doc.Objects
             if obj.Name.startswith("ControlPoly4") and hasattr(obj, "Poles")]
    check(len(polys) >= 1, f"Expected >=1 ControlPoly4, got {len(polys)}", errors)

    return {"pass": len(errors) == 0, "errors": errors, "checks": checks}


def test_cubic_curve_4(doc):
    """CubicCurve_4 from a ControlPoly4."""
    errors = []
    checks = []

    sketch = doc.addObject("Sketcher::SketchObject", "Sketch")
    sketch.Placement = FreeCAD.Placement(
        FreeCAD.Vector(0, 0, 0),
        FreeCAD.Rotation(90, 0, 90)
    )
    geo = [
        Part.LineSegment(FreeCAD.Vector(0, 40, 0), FreeCAD.Vector(25, 40, 0)),
        Part.LineSegment(FreeCAD.Vector(25, 40, 0), FreeCAD.Vector(50, 15, 0)),
        Part.LineSegment(FreeCAD.Vector(50, 15, 0), FreeCAD.Vector(50, 0, 0))
    ]
    sketch.addGeometry(geo)
    doc.recompute()

    Gui.Selection.clearSelection()
    Gui.Selection.addSelection(sketch)
    Gui.runCommand("ControlPoly4")

    polys = [obj for obj in doc.Objects
             if obj.Name.startswith("ControlPoly4") and hasattr(obj, "Poles")]
    check(len(polys) >= 1, "No ControlPoly4 created", errors)
    if not polys:
        return {"pass": False, "errors": errors, "checks": checks}

    Gui.Selection.clearSelection()
    Gui.Selection.addSelection(polys[0])
    Gui.runCommand("CubicCurve_4")

    curves = [obj for obj in doc.Objects
              if obj.Name.startswith("CubicCurve") and hasattr(obj, "Shape")]
    check(len(curves) >= 1, f"Expected >=1 CubicCurve, got {len(curves)}", errors)
    if curves:
        check(curves[0].Shape is not None, "CubicCurve has no Shape", errors)
        checks.append(f"Curve {curves[0].Name} has valid Shape")

    return {"pass": len(errors) == 0, "errors": errors, "checks": checks}


def test_controlgrid44_4(doc):
    """ControlGrid44_4 from 4 ControlPoly4 objects (direct API)."""
    errors = []
    checks = []

    import ArachNURBS as AN

    # Create 4 manual ControlPoly4 objects forming a closed rectangle
    # Each poly has 4 poles; adjacent polys share endpoints exactly
    edge_data = [
        [FreeCAD.Vector(0,0,0), FreeCAD.Vector(16,0,0), FreeCAD.Vector(33,0,0), FreeCAD.Vector(50,0,0)],
        [FreeCAD.Vector(50,0,0), FreeCAD.Vector(50,16,0), FreeCAD.Vector(50,33,0), FreeCAD.Vector(50,50,0)],
        [FreeCAD.Vector(50,50,0), FreeCAD.Vector(33,50,0), FreeCAD.Vector(16,50,0), FreeCAD.Vector(0,50,0)],
        [FreeCAD.Vector(0,50,0), FreeCAD.Vector(0,33,0), FreeCAD.Vector(0,16,0), FreeCAD.Vector(0,0,0)],
    ]
    polys = []
    for i, poles in enumerate(edge_data):
        p = doc.addObject("Part::FeaturePython", f"Poly_{i}")
        p.addProperty("App::PropertyVectorList", "Poles", "", "").Poles = poles
        p.addProperty("App::PropertyFloatList", "Weights", "", "").Weights = [1.0]*4
        p.Proxy = 0
        polys.append(p)

    grid = doc.addObject("Part::FeaturePython", "ControlGrid44_Test")
    AN.ControlGrid44_4(grid, polys[0], polys[1], polys[2], polys[3])
    grid.ViewObject.Proxy = 0
    doc.recompute()

    check(len(grid.Poles) == 16, f"Expected 16 poles, got {len(grid.Poles)}", errors)
    checks.append(f"Grid created with {len(grid.Poles)} poles, {len(grid.Weights)} weights")

    return {"pass": len(errors) == 0, "errors": errors, "checks": checks}


def test_cubic_surface_44(doc):
    """CubicSurface_44 from ControlGrid44 (direct API)."""
    errors = []
    checks = []

    import ArachNURBS as AN

    edge_data = [
        [FreeCAD.Vector(0,0,0), FreeCAD.Vector(16,0,0), FreeCAD.Vector(33,0,0), FreeCAD.Vector(50,0,0)],
        [FreeCAD.Vector(50,0,0), FreeCAD.Vector(50,16,0), FreeCAD.Vector(50,33,0), FreeCAD.Vector(50,50,0)],
        [FreeCAD.Vector(50,50,0), FreeCAD.Vector(33,50,0), FreeCAD.Vector(16,50,0), FreeCAD.Vector(0,50,0)],
        [FreeCAD.Vector(0,50,0), FreeCAD.Vector(0,33,0), FreeCAD.Vector(0,16,0), FreeCAD.Vector(0,0,0)],
    ]
    polys = []
    for i, poles in enumerate(edge_data):
        p = doc.addObject("Part::FeaturePython", f"Poly_{i}")
        p.addProperty("App::PropertyVectorList", "Poles", "", "").Poles = poles
        p.addProperty("App::PropertyFloatList", "Weights", "", "").Weights = [1.0]*4
        p.Proxy = 0
        polys.append(p)

    grid = doc.addObject("Part::FeaturePython", "ControlGrid44_Test")
    AN.ControlGrid44_4(grid, polys[0], polys[1], polys[2], polys[3])
    grid.ViewObject.Proxy = 0
    doc.recompute()

    check(len(grid.Poles) == 16, "ControlGrid44 has no poles", errors)
    if len(grid.Poles) != 16:
        return {"pass": False, "errors": errors, "checks": checks}

    surf = doc.addObject("Part::FeaturePython", "CubicSurface_Test")
    AN.CubicSurface_44(surf, grid)
    surf.ViewObject.Proxy = 0
    doc.recompute()

    check(surf.Shape is not None, "Surface has no Shape", errors)
    check(hasattr(surf.Shape, "Faces"), "Surface Shape has no Faces", errors)
    if surf.Shape and hasattr(surf.Shape, "Faces"):
        checks.append(f"Surface created with {len(surf.Shape.Faces)} face(s)")

    return {"pass": len(errors) == 0, "errors": errors, "checks": checks}


def test_controlgrid44_3(doc):
    """ControlGrid44_3 from 3 ControlPoly4 objects (direct API)."""
    errors = []
    checks = []

    import ArachNURBS as AN

    # 3 polys forming a closed triangle; adjacent polys share endpoints
    tri_data = [
        [FreeCAD.Vector(0,0,0), FreeCAD.Vector(16,0,0), FreeCAD.Vector(33,0,0), FreeCAD.Vector(50,0,0)],
        [FreeCAD.Vector(50,0,0), FreeCAD.Vector(40,16,0), FreeCAD.Vector(25,33,0), FreeCAD.Vector(0,50,0)],
        [FreeCAD.Vector(0,50,0), FreeCAD.Vector(0,33,0), FreeCAD.Vector(0,16,0), FreeCAD.Vector(0,0,0)],
    ]
    polys = []
    for i, poles in enumerate(tri_data):
        p = doc.addObject("Part::FeaturePython", f"Poly_{i}")
        p.addProperty("App::PropertyVectorList", "Poles", "", "").Poles = poles
        p.addProperty("App::PropertyFloatList", "Weights", "", "").Weights = [1.0]*4
        p.Proxy = 0
        polys.append(p)

    grid = doc.addObject("Part::FeaturePython", "ControlGrid44_3_Test")
    AN.ControlGrid44_3(grid, polys[0], polys[1], polys[2])
    grid.ViewObject.Proxy = 0
    doc.recompute()

    check(len(grid.Poles) == 16, f"Expected 16 poles, got {len(grid.Poles)}", errors)
    if len(grid.Poles) == 16:
        checks.append(f"Tri-grid created with {len(grid.Poles)} poles")

    return {"pass": len(errors) == 0, "errors": errors, "checks": checks}


ALL_TESTS = [
    test_controlpoly4_3_lines,
    test_controlpoly4_first_element,
    test_cubic_curve_4,
    test_controlgrid44_4,
    test_cubic_surface_44,
    test_controlgrid44_3,
]
