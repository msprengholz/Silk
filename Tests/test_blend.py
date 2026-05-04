"""
Blend test: two adjacent patches with a blend strip between them.
"""
import FreeCAD
import Part
from FreeCAD import Vector, Gui
from Tests.test_patch44_comprehensive import CaptureConsole, check


def _run_with_capture(doc, test_fn):
    cap = CaptureConsole()
    with cap:
        result = test_fn(doc)
    if cap.errors:
        result["pass"] = False
        result.setdefault("errors", []).extend([f"ConsoleError: {e.strip()}" for e in cap.errors])
    return result


def _get_patches(doc):
    import SilkPatch44
    return [o for o in doc.Objects if hasattr(o, "object_type") and o.object_type == "Patch44"]


def _make_patch(doc, edge_data):
    import SilkPatch44
    edges = []
    for i, poles in enumerate(edge_data):
        e = doc.addObject("Part::FeaturePython", f"E{i}")
        e.addProperty("App::PropertyVectorList","Poles","","").Poles = poles
        e.addProperty("App::PropertyFloatList","Weights","","").Weights = [1.0]*4
        legs = [Part.LineSegment(poles[j], poles[j+1]) for j in range(3)]
        e.addProperty("Part::PropertyGeometryList","Legs","","").Legs = legs
        e.Proxy = 0; e.Shape = Part.Shape(legs)
        edges.append(e)
    doc.recompute()
    Gui.Selection.clearSelection()
    for e in edges: Gui.Selection.addSelection(e)
    SilkPatch44.CreateSilkPatch44().Activated()
    doc.recompute()
    return _get_patches(doc)[-1]


def _flat_blend_strip(doc):
    import ArachNURBS as AN
    err, chk = [], []

    left = _make_patch(doc, [
        [Vector(0,0,0), Vector(16,0,0), Vector(33,0,0), Vector(50,0,0)],
        [Vector(50,0,0), Vector(50,16,0), Vector(50,33,0), Vector(50,50,0)],
        [Vector(50,50,0), Vector(33,50,0), Vector(16,50,0), Vector(0,50,0)],
        [Vector(0,50,0), Vector(0,33,0), Vector(0,16,0), Vector(0,0,0)],
    ])
    right = _make_patch(doc, [
        [Vector(50,0,0), Vector(66,0,0), Vector(83,0,0), Vector(100,0,0)],
        [Vector(100,0,0), Vector(100,16,0), Vector(100,33,0), Vector(100,50,0)],
        [Vector(100,50,0), Vector(83,50,0), Vector(66,50,0), Vector(50,50,0)],
        [Vector(50,50,0), Vector(50,33,0), Vector(50,16,0), Vector(50,0,0)],
    ])

    check(len(left.Poles) == 16, "Left patch 16 poles", err)
    check(len(right.Poles) == 16, "Right patch 16 poles", err)

    # Subdivide at shared edge
    left.USplits = [0.9]; right.USplits = [0.1]
    doc.recompute()

    l_sg = left.Proxy._subgrids[1]   # U=0.9→1.0
    r_sg = right.Proxy._subgrids[0]  # U=0→0.1
    check(len(l_sg) == 16, "Left strip 16 poles", err)
    check(len(r_sg) == 16, "Right strip 16 poles", err)

    # Blend row pairs (flat[u*4 + v] = U=u, V=v)
    blend_poles = []
    for i in range(4):
        l_row = [l_sg[u*4 + i] for u in range(4)]
        r_row = [r_sg[u*4 + i] for u in range(4)]
        result = AN.blend_poly_2x4_1x6(l_row, [1.0]*4, r_row, [1.0]*4, 2.0, 2.0, 2.0, 2.0)
        blend_poles.append(result[0])

    flat_poles = [p for row in blend_poles for p in row]
    check(len(flat_poles) == 24, "Blend 24 poles (6×4)", err)

    # Verify blend spans from left outer to right outer
    v0 = blend_poles[0]
    check(abs(v0[0].x - 44.9) < 0.5, "Blend starts at left strip", err)
    check(abs(v0[5].x - 54.8) < 0.5, "Blend ends at right strip", err)

    chk.append(f"Blend strip spans ({v0[0].x:.1f}) → ({v0[5].x:.1f})")
    return {"pass": len(err) == 0, "errors": err, "checks": chk}


def test_flat_blend(doc):
    return _run_with_capture(doc, _flat_blend_strip)


ALL_TESTS = [test_flat_blend]
