"""
patch33 (#34): 3-edge pointed patch via AN.ControlGrid44_3.

A curved, non-planar triangle (full double curvature) with a degenerate
U=0 control column at the point where two edges meet. Built headlessly
through the ops layer only (create_edge -> create_patch33), mirroring the
#18/#19/#20 bottom-up unit pattern.
"""

import FreeCAD
import Part

import SilkWorkflowOps as ops
import SilkChecks

# 3 junction points of the curved triangle. A is the "point" (degenerate
# U=0 column); the loop is A->B->C->A.
TRI = {
    "A": (0.0, 0.0, 0.0),
    "B": (100.0, 0.0, 10.0),
    "C": (50.0, 100.0, 40.0),
}

# 3 edges: (name, start_key, interior_pol1, interior_pol2, end_key).
# Non-planar interior poles give genuine double curvature.
TRI_EDGES = [
    ("E_a", "A", (33.33, 0.0, 3.0), (66.67, 0.0, 6.0), "B"),
    ("E_b", "B", (90.0, 33.0, 20.0), (70.0, 66.0, 35.0), "C"),
    ("E_c", "C", (30.0, 66.0, 38.0), (10.0, 33.0, 20.0), "A"),
]


def node_sketch(doc, name, base_key, pole):
    """One 2N node sketch at junction `base_key` (circle = endpoint pole,
    line far end = interior pole in world). Mirrors corner_model."""
    b = FreeCAD.Vector(*TRI[base_key])
    p = FreeCAD.Vector(*pole)
    d = p.sub(b)
    ln = d.Length
    x = FreeCAD.Vector(d.x, d.y, d.z).normalize()
    up = FreeCAD.Vector(0, 0, 1)
    if d.cross(up).Length < 1e-6:
        up = FreeCAD.Vector(0, 1, 0)
    z = FreeCAD.Vector(d.cross(up)).normalize()
    y = FreeCAD.Vector(z.cross(x)).normalize()
    rot = FreeCAD.Rotation(x, y, z)
    sk = doc.addObject("Sketcher::SketchObject", name)
    sk.Placement = FreeCAD.Placement(b, rot)
    sk.addGeometry(Part.Circle(FreeCAD.Vector(0, 0, 0), FreeCAD.Vector(0, 0, 1), 1.0), False)
    sk.addGeometry(Part.LineSegment(FreeCAD.Vector(0, 0, 0), FreeCAD.Vector(ln, 0, 0)), False)
    return sk


def build_triangle(doc):
    """Build 3 edges + one Patch33 in `doc` via the ops layer.

    Returns {'sketches': {edge: (sk_a, sk_b)}, 'edges': {name: obj},
             'patch': obj}.
    """
    active = FreeCAD.ActiveDocument
    FreeCAD.setActiveDocument(doc.Name)
    try:
        sketches = {}
        edges = {}
        for (ename, skey, p1, p2, ekey) in TRI_EDGES:
            sk_a = node_sketch(doc, "NS_%s_a" % ename, skey, p1)
            sk_b = node_sketch(doc, "NS_%s_b" % ename, ekey, p2)
            sketches[ename] = (sk_a, sk_b)
            edges[ename] = ops.create_edge([sk_a, sk_b], name=ename)
        patch = ops.create_patch33(
            edges["E_a"], edges["E_b"], edges["E_c"], name="Patch33")
        return {"sketches": sketches, "edges": edges, "patch": patch}
    finally:
        FreeCAD.setActiveDocument(active.Name)


def _summary(results, ok_names):
    failed = [(n, d) for n, ok, d in results if not ok]
    return {
        "pass": not failed,
        "errors": ["%s: %s" % (n, d) for n, d in failed],
        "checks": ["%s: %s" % (n, "OK" if ok else "FAIL " + d)
                   for n, ok, d in results],
    }


def test_patch33_builds_green(doc):
    m = build_triangle(doc)
    edges = [m["edges"][e] for e in ("E_a", "E_b", "E_c")]
    return _summary(SilkChecks.check_patch33(m["patch"], edges), [])


def test_patch33_degenerate_column(doc):
    m = build_triangle(doc)
    p = m["patch"]
    poles = list(p.Poles)
    col0 = [poles[i * 4] for i in range(4)]  # U=0 column
    TOL = SilkChecks.TOL
    devs = [(_c - col0[0]).Length for _c in col0]
    collapsed = all(d <= TOL for d in devs)
    errs = []
    if not collapsed:
        errs.append("U=0 column not collapsed: dev %r" % devs)
    a = FreeCAD.Vector(*TRI["A"])
    if SilkChecks._dist(col0[0], a) > TOL:
        errs.append("degenerate column not at the point junction A")
    return {"pass": not errs, "errors": errs,
            "checks": ["C3: collapsed=%s" % collapsed, "C3: at A"] if not errs else
            [er for er in errs]}


def test_patch33_negative_boundary_pole(doc):
    m = build_triangle(doc)
    patch = m["patch"]
    e1 = m["edges"]["E_b"]
    orig = list(e1.Poles)
    e1.Poles = [orig[0], orig[1],
                FreeCAD.Vector(orig[2].x + 5, orig[2].y, orig[2].z), orig[3]]
    res = SilkChecks.check_patch33(patch, [m["edges"][e] for e in ("E_a", "E_b", "E_c")])
    names = [r[0] for r in res if not r[1]]
    return {
        "pass": "C2_boundary_match" in names,
        "errors": ["corrupted boundary pole not flagged: %r" % names],
        "checks": ["C2 flagged" if "C2_boundary_match" in names else "C2 NOT flagged"],
    }


ALL_TESTS = [test_patch33_builds_green,
             test_patch33_degenerate_column,
             test_patch33_negative_boundary_pole]
