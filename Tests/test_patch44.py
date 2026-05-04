"""
Tests for Patch44 FeaturePython object.
"""
import FreeCAD
import Part
from FreeCAD import Gui
from FreeCAD import Vector


def check(cond, msg, errors):
    if not cond:
        errors.append(msg)
    return cond


def test_patch44_4_sided(doc):
    """Create Patch44 from 4 BoundarySpline edges."""
    errors, checks = [], []

    import ArachNURBS as AN
    import SilkPatch44

    # Create 4 edge polys directly (to avoid sketch dependency)
    edge_data = [
        [Vector(0,0,0), Vector(16,0,0), Vector(33,0,0), Vector(50,0,0)],
        [Vector(50,0,0), Vector(50,16,0), Vector(50,33,0), Vector(50,50,0)],
        [Vector(50,50,0), Vector(33,50,0), Vector(16,50,0), Vector(0,50,0)],
        [Vector(0,50,0), Vector(0,33,0), Vector(0,16,0), Vector(0,0,0)],
    ]
    edges = []
    for i, poles in enumerate(edge_data):
        e = doc.addObject("Part::FeaturePython", f"Edge_{i}")
        e.addProperty("App::PropertyVectorList", "Poles", "", "").Poles = poles
        e.addProperty("App::PropertyFloatList", "Weights", "", "").Weights = [1.0]*4
        e.addProperty("Part::PropertyGeometryList", "Legs", "", "").Legs = [
            Part.LineSegment(poles[j], poles[j+1]) for j in range(3)
        ]
        e.Proxy = 0
        e.Shape = Part.Shape(e.Legs)
        edges.append(e)
    doc.recompute()

    # Create Patch44
    Gui.Selection.clearSelection()
    for e in edges:
        Gui.Selection.addSelection(e)
    Gui.runCommand("Silk_Patch44")

    patches = [o for o in doc.Objects if o.Name.startswith("Patch44") and hasattr(o, "Poles")]
    check(len(patches) == 1, f"Expected 1 Patch44, got {len(patches)}", errors)
    if patches:
        p = patches[0]
        check(len(p.Poles) == 16, f"Expected 16 poles, got {len(p.Poles)}", errors)
        check(p.Shape is not None, "Patch44 has no Shape", errors)
        checks.append(f"Patch44 created with {len(p.Poles)} poles")

    return {"pass": len(errors) == 0, "errors": errors, "checks": checks}


def test_patch44_subdivision(doc):
    """Patch44 with USplits and VSplits — verify subgrids are created (internally)."""
    errors, checks = [], []

    import SilkPatch44

    edge_data = [
        [Vector(0,0,0), Vector(16,0,0), Vector(33,0,0), Vector(50,0,0)],
        [Vector(50,0,0), Vector(50,16,0), Vector(50,33,0), Vector(50,50,0)],
        [Vector(50,50,0), Vector(33,50,0), Vector(16,50,0), Vector(0,50,0)],
        [Vector(0,50,0), Vector(0,33,0), Vector(0,16,0), Vector(0,0,0)],
    ]
    edges = []
    for i, poles in enumerate(edge_data):
        e = doc.addObject("Part::FeaturePython", f"Edge_{i}")
        e.addProperty("App::PropertyVectorList", "Poles", "", "").Poles = poles
        e.addProperty("App::PropertyFloatList", "Weights", "", "").Weights = [1.0]*4
        legs = [Part.LineSegment(poles[j], poles[j+1]) for j in range(3)]
        e.addProperty("Part::PropertyGeometryList", "Legs", "", "").Legs = legs
        e.Proxy = 0; e.Shape = Part.Shape(legs)
        edges.append(e)
    doc.recompute()

    Gui.Selection.clearSelection()
    for e in edges:
        Gui.Selection.addSelection(e)
    Gui.runCommand("Silk_Patch44")

    patches = [o for o in doc.Objects if o.Name.startswith("Patch44") and hasattr(o, "Poles")]
    check(len(patches) == 1, "No Patch44 created", errors)
    if not patches:
        return {"pass": False, "errors": errors, "checks": checks}

    p = patches[0]
    p.USplits = [0.3]
    doc.recompute()
    # Verify subgrid poles exist (internal attribute)
    has_subgrids = hasattr(p.Proxy, "_subgrids") and len(p.Proxy._subgrids) > 0
    check(has_subgrids, "No subgrids after setting USplits=[0.3]", errors)
    if has_subgrids:
        checks.append(f"{len(p.Proxy._subgrids)} subgrids created")

    p.ShowSubgrids = True
    doc.recompute()
    check(p.Shape is not None, "No Shape after enabling ShowSubgrids", errors)
    checks.append("Subgrid display toggled")

    return {"pass": len(errors) == 0, "errors": errors, "checks": checks}
