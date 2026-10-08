"""
Tests/corner_model.py — 2x2 corner model: data + headless builder.

The 2x2 corner fixture (ticket #25): four Patch44s meeting at a central
junction C, 12 edges (8 outer boundary + 4 shared radial), 4 BlendStrips
forming a ring. Every edge is a 2N edge (two node sketches: circle =
endpoint pole, line far end = interior pole), giving full 3D Bezier
freedom without coplanarity constraints.

Junction points (world coords) form a doubly-curved dome: the outer
boundary sags/bulges, the radial ridges S-bend up to the central peak.

build_corner_model(doc) creates 24 node sketches + 12 edges + 4 patches
+ 4 strips in `doc` via SilkWorkflowOps only, and returns the object
map. The same module regenerates the reference fixture
Resources/Test_files/Silk_Corner2x2.FCStd (see save_fixture).
"""

import os

import FreeCAD
import Part

import SilkWorkflowOps as ops

# ---------------------------------------------------------------------------
# Geometry data
# ---------------------------------------------------------------------------

# 9 junction points: 4 outer corners, 4 side midpoints, 1 center peak.
JUNCTIONS = {
    "BL": (0.0, 0.0, 0.0),
    "BR": (100.0, 0.0, 6.0),
    "TL": (0.0, 100.0, 18.0),
    "TR": (100.0, 100.0, 48.0),
    "B":  (50.0, 0.0, 4.0),
    "R":  (100.0, 50.0, 27.0),
    "T":  (50.0, 100.0, 35.0),
    "L":  (0.0, 50.0, 9.0),
    "C":  (50.0, 50.0, 52.0),
}

# 12 edges: (name, start_junction, interior_pole_1, interior_pole_2, end).
# Poles are in cyclic edge order: start -> p1 -> p2 -> end.
EDGES = [
    # outer boundary (clockwise from BL)
    ("E_b1", "BL", (16.67, 0.0, -1.67), (33.33, 0.0, -0.33), "B"),
    ("E_b2", "B",  (66.67, 0.0, 1.67),  (83.33, 0.0, 2.33),  "BR"),
    ("E_r2", "BR", (103.0, 16.67, 13.0), (103.0, 33.33, 20.0), "R"),
    ("E_r4", "R",  (103.0, 66.67, 34.0), (103.0, 83.33, 41.0), "TR"),
    ("E_t4", "TR", (83.33, 103.0, 43.67), (66.67, 103.0, 39.33), "T"),
    ("E_t3", "T",  (33.33, 103.0, 29.33), (16.67, 103.0, 23.67), "TL"),
    ("E_l3", "TL", (-3.0, 83.33, 15.0),  (-3.0, 66.67, 12.0), "L"),
    ("E_l1", "L",  (-3.0, 33.33, 6.0),   (-3.0, 16.67, 3.0),  "BL"),
    # shared radial edges (each shared by two patches, all meeting at C)
    ("E_s12", "B", (50.0, 16.67, 15.0), (50.0, 33.33, 31.0), "C"),
    ("E_s24", "R", (83.33, 50.0, 31.0), (66.67, 50.0, 39.67), "C"),
    ("E_s34", "T", (50.0, 83.33, 36.67), (50.0, 66.67, 42.33), "C"),
    ("E_s13", "L", (16.67, 50.0, 19.67), (33.33, 50.0, 33.33), "C"),
]

# 4 patches: (name, edge0, edge1, edge2, edge3) in cyclic walk order.
#   Patch44  (bottom-left):    BL -> B -> C -> L -> BL
#   Patch001 (bottom-right):   B  -> BR -> R -> C -> B
#   Patch002 (top-left):       TL -> T -> C -> L -> TL
#   Patch003 (top-right):      T  -> TR -> R -> C -> T
PATCHES = [
    ("Patch44",  "E_b1", "E_s12", "E_s13", "E_l1"),
    ("Patch001", "E_b2", "E_r2", "E_s24", "E_s12"),
    ("Patch002", "E_t3", "E_s34", "E_s13", "E_l3"),
    ("Patch003", "E_t4", "E_r4", "E_s24", "E_s34"),
]

# 4 blend strips (ring): (name, patch_a, patch_b) — shared edge is
# auto-detected from corner poles.
STRIPS = [
    ("B12", "Patch44", "Patch001"),
    ("B24", "Patch001", "Patch003"),
    ("B43", "Patch003", "Patch002"),
    ("B31", "Patch002", "Patch44"),
]


# ---------------------------------------------------------------------------
# Sketch builder
# ---------------------------------------------------------------------------

def node_sketch(doc, name, base_key, pole):
    """Create one 2N node sketch at junction `base_key`.

    Local geometry: circle at (0,0) r=1 (center -> endpoint pole) plus a
    line from (0,0) to (d,0) (far end -> interior pole `pole` in world).
    The sketch plane is oriented with X along the base->pole direction.
    Circle radius is irrelevant to ControlPoly4_2N (center only).
    """
    b = FreeCAD.Vector(*JUNCTIONS[base_key])
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


# ---------------------------------------------------------------------------
# Model builder
# ---------------------------------------------------------------------------

def build_corner_model(doc):
    """Build the full 2x2 corner model in `doc` via the ops layer only.

    Returns dict: {'sketches': {edge: (sk_a, sk_b)}, 'edges': {name: obj},
                   'patches': {name: obj}, 'strips': {name: obj}}
    """
    active = FreeCAD.ActiveDocument
    FreeCAD.setActiveDocument(doc.Name)
    try:
        sketches = {}
        edges = {}
        for (ename, skey, p1, p2, ekey) in EDGES:
            sk_a = node_sketch(doc, "NS_%s_a" % ename, skey, p1)
            sk_b = node_sketch(doc, "NS_%s_b" % ename, ekey, p2)
            sketches[ename] = (sk_a, sk_b)
            edges[ename] = ops.create_edge([sk_a, sk_b], name=ename)

        patches = {}
        for (pname, e0, e1, e2, e3) in PATCHES:
            patches[pname] = ops.create_patch(
                edges[e0], edges[e1], edges[e2], edges[e3], name=pname)

        strips = {}
        for (bname, pa, pb) in STRIPS:
            strips[bname] = ops.create_blend(patches[pa], patches[pb], name=bname)

        return {"sketches": sketches, "edges": edges,
                "patches": patches, "strips": strips}
    finally:
        FreeCAD.setActiveDocument(active.Name)


def build_corner_pair(doc):
    """Build the 2-patch B12 probe: Patch44 (BL) + Patch001 (BR) + strip B12.

    The shared edge E_s12 is V3 (ss=1) for Patch44 and V0 (ss=0) for
    Patch001, so the strip exercises both seam sides at once. Used by the
    #30 pairing and #31 direction regression tests.
    """
    active = FreeCAD.ActiveDocument
    FreeCAD.setActiveDocument(doc.Name)
    try:
        etab = {e[0]: e for e in EDGES}
        edges = {}
        for ename in ("E_b1", "E_l1", "E_s13", "E_b2", "E_r2", "E_s24", "E_s12"):
            (_, skey, p1, p2, ekey) = etab[ename]
            sk_a = node_sketch(doc, "NS_%s_a" % ename, skey, p1)
            sk_b = node_sketch(doc, "NS_%s_b" % ename, ekey, p2)
            edges[ename] = ops.create_edge([sk_a, sk_b], name=ename)
        patches = {
            "Patch44": ops.create_patch(edges["E_b1"], edges["E_s12"],
                                        edges["E_s13"], edges["E_l1"],
                                        name="Patch44"),
            "Patch001": ops.create_patch(edges["E_b2"], edges["E_r2"],
                                         edges["E_s24"], edges["E_s12"],
                                         name="Patch001"),
        }
        strip = ops.create_blend(patches["Patch44"], patches["Patch001"], name="B12")
        return {"edges": edges, "patches": patches, "strip": strip}
    finally:
        FreeCAD.setActiveDocument(active.Name)


def fixture_path():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(root, "Resources", "Test_files", "Silk_Corner2x2.FCStd")


def save_fixture():
    """Regenerate the 2x2 corner reference fixture headlessly."""
    for d in FreeCAD.listDocuments().values():
        if d.Name == "CornerFixture":
            FreeCAD.closeDocument("CornerFixture")
    doc = FreeCAD.newDocument("CornerFixture")
    model = build_corner_model(doc)
    path = fixture_path()
    doc.saveAs(path)
    return doc, model, path
