"""
End-to-end workflow tests for BoundarySpline and ControlGridPatch.
Each function takes a FreeCAD document and returns {"pass": bool, "errors": [...], ...}.

Run via: from Tests.mcp_harness import run_tests; run_tests(test_1, test_2, ...)
"""

import FreeCAD
import Part
from FreeCAD import Gui


def check(condition, msg, errors):
    if not condition:
        errors.append(msg)
    return condition


def _make_line_sketch(doc, name, pos, rot):
    sk = doc.addObject("Sketcher::SketchObject", name)
    sk.Placement = FreeCAD.Placement(pos, rot)
    geo = [
        Part.LineSegment(FreeCAD.Vector(0, 40, 0), FreeCAD.Vector(25, 40, 0)),
        Part.LineSegment(FreeCAD.Vector(25, 40, 0), FreeCAD.Vector(50, 15, 0)),
        Part.LineSegment(FreeCAD.Vector(50, 15, 0), FreeCAD.Vector(50, 0, 0))
    ]
    sk.addGeometry(geo)
    doc.recompute()
    return sk


def test_boundaryspline_single_sketch(doc):
    """Create a single BoundarySpline from one sketch."""
    errors, checks = [], []

    from SilkWorkflow import CreateBoundarySplineCommand
    sk = _make_line_sketch(doc, "Sketch",
        FreeCAD.Vector(0, 0, 0), FreeCAD.Rotation(90, 0, 90))

    Gui.Selection.clearSelection()
    Gui.Selection.addSelection(sk)
    CreateBoundarySplineCommand().Activated()

    bs_list = [obj for obj in doc.Objects
               if obj.Name.startswith("BoundarySpline")
               and obj.TypeId == "App::DocumentObjectGroupPython"]
    check(len(bs_list) == 1, f"Expected 1 BoundarySpline, got {len(bs_list)}", errors)
    if bs_list:
        bs = bs_list[0]
        check(len(bs.Group) == 2, f"Expected 2 children, got {len(bs.Group)}", errors)
        has_poly = any("ControlPoly4" in o.Name for o in bs.Group)
        has_curve = any("CubicCurve" in o.Name for o in bs.Group)
        check(has_poly, "Missing ControlPoly4 child", errors)
        check(has_curve, "Missing CubicCurve child", errors)
        checks.append(f"BoundarySpline {bs.Name}: poly={has_poly}, curve={has_curve}")

    return {"pass": len(errors) == 0, "errors": errors, "checks": checks}


def test_controlgridpatch_4(doc):
    """Create a ControlGridPatch from 4 BoundarySplines."""
    errors, checks = [], []

    from SilkWorkflow import CreateBoundarySplineCommand, CreateControlGridPatchCommand

    placements = [
        (FreeCAD.Vector(0, 0, 0), FreeCAD.Rotation(90, 0, 90)),
        (FreeCAD.Vector(0, 0, 40), FreeCAD.Rotation(0, 0, 90)),
        (FreeCAD.Vector(0, 50, 0), FreeCAD.Rotation(0, 0, 0)),
        (FreeCAD.Vector(50, 50, 0), FreeCAD.Rotation(-90, 0, 0)),
    ]
    boundaries = []
    for i, (pos, rot) in enumerate(placements):
        sk = _make_line_sketch(doc, f"Sketch_{i}", pos, rot)
        Gui.Selection.clearSelection()
        Gui.Selection.addSelection(sk)
        CreateBoundarySplineCommand().Activated()
        bs = [obj for obj in doc.Objects if obj.Name.startswith("BoundarySpline")]
        if bs:
            boundaries.append(bs[-1])

    check(len(boundaries) == 4, f"Expected 4 BoundarySplines, got {len(boundaries)}", errors)
    if len(boundaries) != 4:
        return {"pass": False, "errors": errors, "checks": checks}

    Gui.Selection.clearSelection()
    for bs in boundaries:
        Gui.Selection.addSelection(bs)
    CreateControlGridPatchCommand().Activated()

    patches = [obj for obj in doc.Objects
               if obj.Name.startswith("ControlGridPatch")
               and obj.TypeId == "App::DocumentObjectGroupPython"]
    check(len(patches) == 1, f"Expected 1 ControlGridPatch, got {len(patches)}", errors)
    if patches:
        patch = patches[0]
        group_names = [o.Name for o in patch.Group]
        checks.append(f"Patch {patch.Name}: {group_names}")
        has_grid = any("ControlGrid44" in n for n in group_names)
        has_surf = any("CubicSurface" in n for n in group_names)
        check(has_grid, "Missing ControlGrid44 child", errors)
        check(has_surf, "Missing CubicSurface child", errors)

    return {"pass": len(errors) == 0, "errors": errors, "checks": checks}


def test_controlgridpatch_3(doc):
    """Create a ControlGridPatch from 3 BoundarySplines."""
    errors, checks = [], []

    from SilkWorkflow import CreateBoundarySplineCommand, CreateControlGridPatchCommand

    placements = [
        (FreeCAD.Vector(0, 0, 0), FreeCAD.Rotation(90, 0, 90)),
        (FreeCAD.Vector(0, 0, 40), FreeCAD.Rotation(0, 0, 90)),
        (FreeCAD.Vector(0, 50, 0), FreeCAD.Rotation(0, 0, 0)),
    ]
    boundaries = []
    for i, (pos, rot) in enumerate(placements):
        sk = _make_line_sketch(doc, f"Sketch_{i}", pos, rot)
        Gui.Selection.clearSelection()
        Gui.Selection.addSelection(sk)
        CreateBoundarySplineCommand().Activated()
        bs = [obj for obj in doc.Objects if obj.Name.startswith("BoundarySpline")]
        if bs:
            boundaries.append(bs[-1])

    check(len(boundaries) == 3, f"Expected 3 BoundarySplines, got {len(boundaries)}", errors)
    if len(boundaries) != 3:
        return {"pass": False, "errors": errors, "checks": checks}

    Gui.Selection.clearSelection()
    for bs in boundaries:
        Gui.Selection.addSelection(bs)
    CreateControlGridPatchCommand().Activated()

    patches = [obj for obj in doc.Objects
               if obj.Name.startswith("ControlGridPatch")
               and obj.TypeId == "App::DocumentObjectGroupPython"]
    check(len(patches) == 1, f"Expected 1 ControlGridPatch, got {len(patches)}", errors)
    if patches:
        checks.append(f"3-sided patch {patches[0].Name} created")

    return {"pass": len(errors) == 0, "errors": errors, "checks": checks}


ALL_TESTS = [
    test_boundaryspline_single_sketch,
    test_controlgridpatch_4,
    test_controlgridpatch_3,
]
