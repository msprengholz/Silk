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
    """ControlGrid44_4 from 4 ControlPoly4 objects."""
    errors = []
    checks = []

    # Create 4 sketches with 3 lines each
    placements = [
        (FreeCAD.Vector(0, 0, 0), FreeCAD.Rotation(90, 0, 90)),
        (FreeCAD.Vector(0, 0, 40), FreeCAD.Rotation(0, 0, 90)),
        (FreeCAD.Vector(0, 50, 0), FreeCAD.Rotation(0, 0, 0)),
        (FreeCAD.Vector(50, 50, 0), FreeCAD.Rotation(-90, 0, 0)),
    ]
    polys = []
    for i, (pos, rot) in enumerate(placements):
        sk = doc.addObject("Sketcher::SketchObject", f"Sketch_{i}")
        sk.Placement = FreeCAD.Placement(pos, rot)
        geo = [
            Part.LineSegment(FreeCAD.Vector(0, 40, 0), FreeCAD.Vector(25, 40, 0)),
            Part.LineSegment(FreeCAD.Vector(25, 40, 0), FreeCAD.Vector(50, 15, 0)),
            Part.LineSegment(FreeCAD.Vector(50, 15, 0), FreeCAD.Vector(50, 0, 0))
        ]
        sk.addGeometry(geo)
        doc.recompute()
        Gui.Selection.clearSelection()
        Gui.Selection.addSelection(sk)
        Gui.runCommand("ControlPoly4")
        p = [obj for obj in doc.Objects if obj.Name.startswith("ControlPoly4") and hasattr(obj, "Poles")]
        if p:
            polys.append(p[-1])

    check(len(polys) == 4, f"Expected 4 ControlPoly4, got {len(polys)}", errors)
    if len(polys) != 4:
        return {"pass": False, "errors": errors, "checks": checks}

    Gui.Selection.clearSelection()
    for p in polys:
        Gui.Selection.addSelection(p)
    Gui.runCommand("ControlGrid44")

    grids = [obj for obj in doc.Objects
             if obj.Name.startswith("ControlGrid44") and hasattr(obj, "Poles")
             and len(obj.Poles) == 16]
    check(len(grids) >= 1, f"Expected >=1 ControlGrid44 with 16 poles, got {len(grids)}", errors)
    if grids:
        checks.append(f"Grid {grids[0].Name}: {len(grids[0].Poles)} poles")

    return {"pass": len(errors) == 0, "errors": errors, "checks": checks}


def test_cubic_surface_44(doc):
    """CubicSurface_44 from ControlGrid44."""
    errors = []
    checks = []

    placements = [
        (FreeCAD.Vector(0, 0, 0), FreeCAD.Rotation(90, 0, 90)),
        (FreeCAD.Vector(0, 0, 40), FreeCAD.Rotation(0, 0, 90)),
        (FreeCAD.Vector(0, 50, 0), FreeCAD.Rotation(0, 0, 0)),
        (FreeCAD.Vector(50, 50, 0), FreeCAD.Rotation(-90, 0, 0)),
    ]
    polys = []
    for i, (pos, rot) in enumerate(placements):
        sk = doc.addObject("Sketcher::SketchObject", f"Sketch_{i}")
        sk.Placement = FreeCAD.Placement(pos, rot)
        geo = [
            Part.LineSegment(FreeCAD.Vector(0, 40, 0), FreeCAD.Vector(25, 40, 0)),
            Part.LineSegment(FreeCAD.Vector(25, 40, 0), FreeCAD.Vector(50, 15, 0)),
            Part.LineSegment(FreeCAD.Vector(50, 15, 0), FreeCAD.Vector(50, 0, 0))
        ]
        sk.addGeometry(geo)
        doc.recompute()
        Gui.Selection.clearSelection()
        Gui.Selection.addSelection(sk)
        Gui.runCommand("ControlPoly4")
        p = [obj for obj in doc.Objects if obj.Name.startswith("ControlPoly4") and hasattr(obj, "Poles")]
        if p:
            polys.append(p[-1])

    Gui.Selection.clearSelection()
    for p in polys:
        Gui.Selection.addSelection(p)
    Gui.runCommand("ControlGrid44")
    grids = [obj for obj in doc.Objects
             if obj.Name.startswith("ControlGrid44") and hasattr(obj, "Poles")
             and len(obj.Poles) == 16]
    check(len(grids) >= 1, "No ControlGrid44", errors)
    if not grids:
        return {"pass": False, "errors": errors, "checks": checks}

    Gui.Selection.clearSelection()
    Gui.Selection.addSelection(grids[0])
    Gui.runCommand("CubicSurface_44")
    surfaces = [obj for obj in doc.Objects
                if obj.Name.startswith("CubicSurface") and hasattr(obj, "Shape")]
    check(len(surfaces) >= 1, f"Expected >=1 CubicSurface, got {len(surfaces)}", errors)
    if surfaces:
        check(surfaces[0].Shape is not None, "Surface has no Shape", errors)
        check(hasattr(surfaces[0].Shape, "Faces"), "Surface Shape has no Faces", errors)
        checks.append(f"Surface {surfaces[0].Name} created")

    return {"pass": len(errors) == 0, "errors": errors, "checks": checks}


def test_controlgrid44_3(doc):
    """ControlGrid44_3 from 3 ControlPoly4 objects (triangular grid)."""
    errors = []
    checks = []

    placements = [
        (FreeCAD.Vector(0, 0, 0), FreeCAD.Rotation(90, 0, 90)),
        (FreeCAD.Vector(0, 0, 40), FreeCAD.Rotation(0, 0, 90)),
        (FreeCAD.Vector(0, 50, 0), FreeCAD.Rotation(0, 0, 0)),
    ]
    polys = []
    for i, (pos, rot) in enumerate(placements):
        sk = doc.addObject("Sketcher::SketchObject", f"Sketch_{i}")
        sk.Placement = FreeCAD.Placement(pos, rot)
        geo = [
            Part.LineSegment(FreeCAD.Vector(0, 40, 0), FreeCAD.Vector(25, 40, 0)),
            Part.LineSegment(FreeCAD.Vector(25, 40, 0), FreeCAD.Vector(50, 15, 0)),
            Part.LineSegment(FreeCAD.Vector(50, 15, 0), FreeCAD.Vector(50, 0, 0))
        ]
        sk.addGeometry(geo)
        doc.recompute()
        Gui.Selection.clearSelection()
        Gui.Selection.addSelection(sk)
        Gui.runCommand("ControlPoly4")
        p = [obj for obj in doc.Objects if obj.Name.startswith("ControlPoly4") and hasattr(obj, "Poles")]
        if p:
            polys.append(p[-1])

    check(len(polys) == 3, f"Expected 3 ControlPoly4, got {len(polys)}", errors)
    if len(polys) != 3:
        return {"pass": False, "errors": errors, "checks": checks}

    Gui.Selection.clearSelection()
    for p in polys:
        Gui.Selection.addSelection(p)
    Gui.runCommand("ControlGrid44_3_1Grid44")

    tri = [obj for obj in doc.Objects
           if obj.Name.startswith("ControlGrid44_3") and hasattr(obj, "Poles")]

    if tri:
        checks.append(f"Tri-grid {tri[0].Name}: {len(tri[0].Poles)} poles")
        check(len(tri[0].Poles) == 16, f"Expected 16 poles, got {len(tri[0].Poles)}", errors)
    else:
        errors.append("No ControlGrid44_3 found")

    return {"pass": len(errors) == 0, "errors": errors, "checks": checks}


ALL_TESTS = [
    test_controlpoly4_3_lines,
    test_controlpoly4_first_element,
    test_cubic_curve_4,
    test_controlgrid44_4,
    test_cubic_surface_44,
    test_controlgrid44_3,
]
