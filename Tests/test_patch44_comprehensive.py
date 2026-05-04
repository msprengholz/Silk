"""
Comprehensive tests for Patch44 FeaturePython.
All functions take doc, return {"pass": bool, "errors": [...], "checks": [...]}
"""
import FreeCAD
import Part
from FreeCAD import Vector, Gui


def check(cond, msg, errors):
    if not cond:
        errors.append(msg)
    return cond


def _make_edges(doc):
    """Create 4 edeg objects forming a closed rectangle."""
    import SilkPatch44
    edges = []
    for i, poles in enumerate([
        [Vector(0,0,0), Vector(16,0,0), Vector(33,0,0), Vector(50,0,0)],
        [Vector(50,0,0), Vector(50,16,0), Vector(50,33,0), Vector(50,50,0)],
        [Vector(50,50,0), Vector(33,50,0), Vector(16,50,0), Vector(0,50,0)],
        [Vector(0,50,0), Vector(0,33,0), Vector(0,16,0), Vector(0,0,0)]]):
        e = doc.addObject("Part::FeaturePython", f"E{i}")
        e.addProperty("App::PropertyVectorList","Poles","","").Poles = poles
        e.addProperty("App::PropertyFloatList","Weights","","").Weights = [1.0]*4
        legs = [Part.LineSegment(poles[j], poles[j+1]) for j in range(3)]
        e.addProperty("Part::PropertyGeometryList","Legs","","").Legs = legs
        e.Proxy = 0; e.Shape = Part.Shape(legs)
        edges.append(e)
    doc.recompute()
    return edges


def _make_patch(doc, edges):
    import SilkPatch44
    Gui.Selection.clearSelection()
    for e in edges: Gui.Selection.addSelection(e)
    SilkPatch44.CreateSilkPatch44().Activated()
    doc.recompute()
    return [o for o in doc.Objects if o.Name.startswith("Patch44")][0]


def test_basic_creation(doc):
    """Patch44: 16 poles, valid Shape, correct defaults."""
    errors, checks = [], []
    e = _make_edges(doc)
    p = _make_patch(doc, e)
    check(len(p.Poles) == 16, "Expected 16 poles", errors)
    check(p.Shape is not None, "Shape is not None", errors)
    check(p.Proxy._base_surface is not None, "Base surface stored", errors)
    check(len(p.Proxy._subgrids) == 0, "No subgrids by default", errors)
    check(p.ShowSurface == True, "ShowSurface defaults True", errors)
    check(p.ShowGrid == True, "ShowGrid defaults True", errors)
    check(p.ShowSubgrids == False, "ShowSubgrids defaults False", errors)
    checks.append(f"Patch44 OK: {len(p.Poles)} poles")
    return {"pass": len(errors) == 0, "errors": errors, "checks": checks}


def test_usplits(doc):
    """Patch44: USplits creates 2 subgrids."""
    errors, checks = [], []
    e = _make_edges(doc); p = _make_patch(doc, e)
    p.USplits = [0.3]; doc.recompute()
    check(len(p.Proxy._subgrids) == 2, "Expected 2 subgrids", errors)
    check(len(p.Proxy._subsurfaces) == 2, "Expected 2 subsurfaces", errors)
    checks.append(f"USplits=[0.3]: {len(p.Proxy._subgrids)} subgrids")
    return {"pass": len(errors) == 0, "errors": errors, "checks": checks}


def test_vsplits(doc):
    """Patch44: VSplits creates 2 subgrids."""
    errors, checks = [], []
    e = _make_edges(doc); p = _make_patch(doc, e)
    p.VSplits = [0.4]; doc.recompute()
    check(len(p.Proxy._subgrids) == 2, "Expected 2 subgrids", errors)
    return {"pass": len(errors) == 0, "errors": errors, "checks": checks}


def test_uv_splits(doc):
    """Patch44: USplits + VSplits creates 4 subgrids with 16 poles each."""
    errors, checks = [], []
    e = _make_edges(doc); p = _make_patch(doc, e)
    p.USplits = [0.3]; p.VSplits = [0.5]; doc.recompute()
    check(len(p.Proxy._subgrids) == 4, "Expected 4 subgrids", errors)
    check(len(p.Proxy._subsurfaces) == 4, "Expected 4 subsurfaces", errors)
    for i, sg in enumerate(p.Proxy._subgrids):
        check(len(sg) == 16, f"Subgrid {i} expected 16 poles", errors)
    checks.append(f"UV splits: {len(p.Proxy._subgrids)} subgrids")
    return {"pass": len(errors) == 0, "errors": errors, "checks": checks}


def test_multiple_splits(doc):
    """Patch44: Multiple split values create correct count."""
    errors, checks = [], []
    e = _make_edges(doc); p = _make_patch(doc, e)
    p.USplits = [0.2, 0.5, 0.8]; doc.recompute()
    check(len(p.Proxy._subgrids) == 4, "Expected 4 subgrids", errors)
    checks.append(f"USplits=[0.2,0.5,0.8]: {len(p.Proxy._subgrids)} subgrids")
    return {"pass": len(errors) == 0, "errors": errors, "checks": checks}


def test_display_toggles(doc):
    """Patch44: All display toggle combinations produce valid Shape."""
    errors, checks = [], []
    e = _make_edges(doc); p = _make_patch(doc, e)
    p.USplits = [0.3]; doc.recompute()

    p.ShowSubgrids = True; doc.recompute()
    check(p.Shape is not None, "Shape with ShowSubgrids=T", errors)
    p.ShowSubgrids = False; p.ShowSurface = True; p.ShowGrid = True; doc.recompute()
    check(p.Shape is not None, "Shape with ShowSurface+Grid", errors)
    p.ShowSubgrids = False; p.ShowSurface = False; p.ShowGrid = False; doc.recompute()
    check(p.Shape is not None, "Shape with all off", errors)
    p.ShowSubgrids = False; p.ShowSurface = True; p.ShowGrid = False; doc.recompute()
    check(p.Shape is not None, "Shape with ShowSurface only", errors)
    p.ShowSubgrids = False; p.ShowSurface = False; p.ShowGrid = True; doc.recompute()
    check(p.Shape is not None, "Shape with ShowGrid only", errors)
    p.ShowSubgrids = True; p.ShowSurface = False; p.ShowGrid = False; doc.recompute()
    check(p.Shape is not None, "Shape with ShowSubgrids only", errors)

    checks.append("All toggle combinations OK")
    return {"pass": len(errors) == 0, "errors": errors, "checks": checks}


def test_pole_stability(doc):
    """Patch44: Poles remain stable across property changes."""
    errors, checks = [], []
    e = _make_edges(doc); p = _make_patch(doc, e)
    poles_initial = [tuple(v) for v in p.Poles]
    p.USplits = [0.3]; doc.recompute()
    p.ShowSubgrids = True; doc.recompute()
    p.ShowSubgrids = False; doc.recompute()
    poles_final = [tuple(v) for v in p.Poles]
    check(poles_initial == poles_final, "Poles changed after split+display toggles", errors)
    checks.append("Poles stable")
    return {"pass": len(errors) == 0, "errors": errors, "checks": checks}


def test_empty_splits_idempotent(doc):
    """Patch44: Setting empty splits after non-empty resets subgrids."""
    errors, checks = [], []
    e = _make_edges(doc); p = _make_patch(doc, e)
    p.USplits = [0.3]; doc.recompute()
    p.USplits = []; doc.recompute()
    check(len(p.Proxy._subgrids) == 0, "Subgrids reset after empty splits", errors)
    return {"pass": len(errors) == 0, "errors": errors, "checks": checks}


ALL_TESTS = [
    test_basic_creation,
    test_usplits,
    test_vsplits,
    test_uv_splits,
    test_multiple_splits,
    test_display_toggles,
    test_pole_stability,
    test_empty_splits_idempotent,
]
