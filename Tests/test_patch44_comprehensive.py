"""
Comprehensive Patch44 test suite.
Includes: flat/3D geometry, splits, display toggles, serialization, console error capture,
getSubgrid API, edge cases.

All tests: func(doc) → {"pass": bool, "errors": [...], "checks": [...]}
"""
import FreeCAD
import Part
from FreeCAD import Vector, Gui


class CaptureConsole:
    """Captures FreeCAD PrintError/PrintWarning during test execution."""
    def __init__(self):
        self.errors = []
        self.warnings = []
        self._orig_error = None
        self._orig_warn = None

    def __enter__(self):
        self._orig_error = FreeCAD.Console.PrintError
        self._orig_warn = FreeCAD.Console.PrintWarning
        FreeCAD.Console.PrintError = lambda msg: (self.errors.append(msg), self._orig_error(msg) if self._orig_error else None)
        FreeCAD.Console.PrintWarning = lambda msg: (self.warnings.append(msg), self._orig_warn(msg) if self._orig_warn else None)
        return self

    def __exit__(self, *args):
        FreeCAD.Console.PrintError = self._orig_error
        FreeCAD.Console.PrintWarning = self._orig_warn


def check(cond, msg, errors):
    if not cond:
        errors.append(msg)
    return cond


def _make_edges(doc, edge_data):
    edges = []
    for i, poles in enumerate(edge_data):
        e = doc.addObject("Part::FeaturePython", f"E{i}")
        e.addProperty("App::PropertyVectorList", "Poles", "", "").Poles = poles
        e.addProperty("App::PropertyFloatList", "Weights", "", "").Weights = [1.0] * 4
        legs = [Part.LineSegment(poles[j], poles[j + 1]) for j in range(3)]
        e.addProperty("Part::PropertyGeometryList", "Legs", "", "").Legs = legs
        e.Proxy = 0
        e.Shape = Part.Shape(legs)
        edges.append(e)
    doc.recompute()
    return edges


def _make_patch(doc, edges):
    import SilkPatch44
    Gui.Selection.clearSelection()
    for e in edges:
        Gui.Selection.addSelection(e)
    SilkPatch44.CreateSilkPatch44().Activated()
    doc.recompute()
    return [o for o in doc.Objects if o.Name.startswith("Patch44")][0]


FLAT_SQUARE = [
    [Vector(0,0,0), Vector(16,0,0), Vector(33,0,0), Vector(50,0,0)],
    [Vector(50,0,0), Vector(50,16,0), Vector(50,33,0), Vector(50,50,0)],
    [Vector(50,50,0), Vector(33,50,0), Vector(16,50,0), Vector(0,50,0)],
    [Vector(0,50,0), Vector(0,33,0), Vector(0,16,0), Vector(0,0,0)],
]

LOFTED_3D = [
    [Vector(0,0,0), Vector(16,0,3), Vector(33,0,8), Vector(50,0,15)],
    [Vector(50,0,15), Vector(50,16,20), Vector(50,33,25), Vector(50,50,35)],
    [Vector(50,50,35), Vector(33,50,25), Vector(16,50,15), Vector(0,50,20)],
    [Vector(0,50,20), Vector(0,33,10), Vector(0,16,5), Vector(0,0,0)],
]


def _run_with_capture(doc, test_fn):
    """Run a test while capturing console errors."""
    cap = CaptureConsole()
    with cap:
        result = test_fn(doc)
    pass
    result["console_errors"] = cap.errors
    result["console_warnings"] = cap.warnings
    # Fail test if any console errors
    if cap.errors:
        result["pass"] = False
        result.setdefault("errors", []).extend([f"ConsoleError: {e.strip()}" for e in cap.errors])
    return result


# ──────────────────────────────────────────────
# INDIVIDUAL TEST IMPLEMENTATIONS
# ──────────────────────────────────────────────

def _basic_creation(doc):
    err, chk = [], []
    e = _make_edges(doc, FLAT_SQUARE)
    p = _make_patch(doc, e)
    check(len(p.Poles) == 16, "Expected 16 poles", err)
    check(p.Shape is not None, "Shape is not None", err)
    check(p.Proxy._base_surface is not None, "Base surface stored", err)
    check(len(p.Proxy._subgrids) == 0, "No subgrids by default", err)
    check(p.ShowSurface == True, "ShowSurface defaults True", err)
    check(p.ShowGrid == True, "ShowGrid defaults True", err)
    check(p.ShowSubgrids == False, "ShowSubgrids defaults False", err)
    chk.append(f"Basic creation: {len(p.Poles)} poles")
    return {"pass": len(err) == 0, "errors": err, "checks": chk}


def _subgrid_counts(doc):
    err, chk = [], []
    e = _make_edges(doc, FLAT_SQUARE)
    p = _make_patch(doc, e)
    
    # U split only
    p.USplits = [0.3]; doc.recompute()
    check(len(p.Proxy._subgrids) == 2, "U split: expected 2 subgrids", err)
    check(len(p.Proxy._subsurfaces) == 2, "U split: expected 2 subsurfaces", err)
    
    # V split only
    p.USplits = []; p.VSplits = [0.4]; doc.recompute()
    check(len(p.Proxy._subgrids) == 2, "V split: expected 2 subgrids", err)
    
    # UV split
    p.USplits = [0.3]; p.VSplits = [0.5]; doc.recompute()
    check(len(p.Proxy._subgrids) == 4, "UV split: expected 4 subgrids", err)
    check(len(p.Proxy._subsurfaces) == 4, "UV split: expected 4 subsurfaces", err)
    for i, sg in enumerate(p.Proxy._subgrids):
        check(len(sg) == 16, f"Subgrid {i}: expected 16 poles", err)
    
    # Multiple splits
    p.USplits = [0.2, 0.5, 0.8]; p.VSplits = []; doc.recompute()
    check(len(p.Proxy._subgrids) == 4, "Multi split: expected 4 subgrids", err)
    
    # Empty splits clear subgrids
    p.USplits = []; p.VSplits = []; doc.recompute()
    check(len(p.Proxy._subgrids) == 0, "Empty splits: expected 0 subgrids", err)
    
    chk.append("All split combinations OK")
    return {"pass": len(err) == 0, "errors": err, "checks": chk}


def _display_toggles(doc):
    err, chk = [], []
    e = _make_edges(doc, FLAT_SQUARE)
    p = _make_patch(doc, e)
    p.USplits = [0.3]; doc.recompute()
    
    cases = [
        (True, True, True, "Subgrids+Surf+Grid"),
        (True, False, False, "Subgrids only"),
        (False, True, True, "Base+Grid"),
        (False, True, False, "Surface only"),
        (False, False, True, "Grid only"),
        (False, False, False, "All off"),
    ]
    for sg, sf, gr, label in cases:
        p.ShowSubgrids = sg; p.ShowSurface = sf; p.ShowGrid = gr
        doc.recompute()
        check(p.Shape is not None, f"Shape with {label}", err)
    chk.append(f"{len(cases)} toggle combinations OK")
    return {"pass": len(err) == 0, "errors": err, "checks": chk}


def _pole_stability(doc):
    err, chk = [], []
    e = _make_edges(doc, FLAT_SQUARE)
    p = _make_patch(doc, e)
    poles_init = [tuple(v) for v in p.Poles]
    p.USplits = [0.3]; doc.recompute()
    p.ShowSubgrids = True; doc.recompute()
    p.ShowSubgrids = False; doc.recompute()
    p.VSplits = [0.5]; doc.recompute()
    poles_final = [tuple(v) for v in p.Poles]
    check(poles_init == poles_final, "Poles changed after property toggles", err)
    chk.append("Poles stable across property changes")
    return {"pass": len(err) == 0, "errors": err, "checks": chk}


def _3d_lofted(doc):
    err, chk = [], []
    e = _make_edges(doc, LOFTED_3D)
    p = _make_patch(doc, e)
    check(len(p.Poles) == 16, "Expected 16 poles for lofted", err)
    check(p.Proxy._base_surface is not None, "Base surface for lofted", err)
    p.USplits = [0.3]; doc.recompute()
    check(len(p.Proxy._subgrids) == 2, "Lofted U split: 2 subgrids", err)
    p.VSplits = [0.5]; doc.recompute()
    check(len(p.Proxy._subgrids) == 4, "Lofted UV split: 4 subgrids", err)
    chk.append("3D lofted patch OK")
    return {"pass": len(err) == 0, "errors": err, "checks": chk}


def _serialization(doc):
    err, chk = [], []
    import os
    e = _make_edges(doc, LOFTED_3D)
    p = _make_patch(doc, e)
    p.USplits = [0.3]; doc.recompute()
    poles_before = [tuple(v) for v in p.Poles]
    sg_before = len(p.Proxy._subgrids)
    
    save_path = "/tmp/_test_patch44_serialize.FCStd"
    doc.saveAs(save_path)
    FreeCAD.closeDocument(doc.Name)
    
    doc2 = FreeCAD.openDocument(save_path)
    p2 = [o for o in doc2.Objects if o.Name.startswith("Patch44")][0]
    check(len(p2.Poles) == 16, "Reload: expected 16 poles", err)
    poles_after = [tuple(v) for v in p2.Poles]
    check(poles_before == poles_after, "Reload: poles changed", err)
    p2.USplits = [0.3]; doc2.recompute()
    check(len(p2.Proxy._subgrids) == sg_before, f"Reload: expected {sg_before} subgrids", err)
    os.remove(save_path)
    FreeCAD.closeDocument(doc2.Name)
    chk.append("Save/reload cycle OK")
    return {"pass": len(err) == 0, "errors": err, "checks": chk}


def _get_subgrid_api(doc):
    err, chk = [], []
    e = _make_edges(doc, FLAT_SQUARE)
    p = _make_patch(doc, e)
    p.USplits = [0.3]; doc.recompute()
    
    # getSubgrid returns (poles, weights) or (None, None)
    sub_poles, sub_weights = p.Proxy.getSubgrid(0, 0.5, 0, 1)
    check(sub_poles is not None, "getSubgrid returned None poles", err)
    if sub_poles:
        rows = len(sub_poles)
        cols = len(sub_poles[0]) if rows > 0 else 0
        check(rows == 4 and cols == 4, f"getSubgrid: expected 4x4, got {rows}x{cols}", err)
        chk.append(f"getSubgrid returns 4x4 poles")
    return {"pass": len(err) == 0, "errors": err, "checks": chk}


# ──────────────────────────────────────────────
# EXPORTED TEST WRAPPERS (with console capture)
# ──────────────────────────────────────────────

def test_basic_creation(doc):
    return _run_with_capture(doc, _basic_creation)

def test_subgrid_counts(doc):
    return _run_with_capture(doc, _subgrid_counts)

def test_display_toggles(doc):
    return _run_with_capture(doc, _display_toggles)

def test_pole_stability(doc):
    return _run_with_capture(doc, _pole_stability)

def test_3d_lofted(doc):
    return _run_with_capture(doc, _3d_lofted)

def test_serialization(doc):
    return _run_with_capture(doc, _serialization)

def test_get_subgrid_api(doc):
    return _run_with_capture(doc, _get_subgrid_api)


ALL_TESTS = [
    test_basic_creation,
    test_subgrid_counts,
    test_display_toggles,
    test_pole_stability,
    test_3d_lofted,
    test_serialization,
    test_get_subgrid_api,
]
