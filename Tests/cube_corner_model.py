"""
Tests/cube_corner_model.py — 3-patch hard-corner (cube corner) fixture: data + builder.

The 3-valent counterpart of Tests/corner_model.py: three planar square
patches meeting like the corner of a unit cube at the shared origin, each
pairwise sharing exactly one edge — the three coordinate-axis edges through
the origin:

    PatchA: plane z = 0, (x, y) in [0, 1]^2   (bottom face)
    PatchB: plane x = 0, (y, z) in [0, 1]^2   (left face)
    PatchC: plane y = 0, (x, z) in [0, 1]^2   (front face)

Shared seams (one Edge object each, referenced by both patches):
    E_AB: origin -> (0, 1, 0)   (the y axis; PatchA | PatchB)
    E_AC: origin -> (1, 0, 0)   (the x axis; PatchA | PatchC)
    E_BC: origin -> (0, 0, 1)   (the z axis; PatchB | PatchC)

plus six outer edges (E_A1/E_A2, E_B1/E_B2, E_C1/E_C2). Three Blend strips
(B_AB, B_BC, B_CA) round the three seams; the 3-valent CornerBlend then
rings the shared origin vertex, with the triangular patch's net
auto-built by `SilkCorner.corner_inputs` (no fourth strip exists).

Every edge is a straight cubic (2N node sketches, interior poles at the
thirds of the segment), so all three base surfaces are exact planar
squares and the fixture carries no curvature of its own. Band splits are
the Blend defaults (0.1 at each seam's own end) — no width is overridden.

build_cube_corner_model(doc) creates 18 node sketches + 9 edges + 3 patches
+ 3 strips in `doc` via SilkWorkflowOps only, and returns the object map.

MEASURED STATE (ticket-3valent-fix): the fixture is oracle-green (3 patches
pass `check_patch` on their own stored `Edges`, 3 strips pass `check_blend`),
the three strips resolve as the 3-cycle ring, and the corner now BUILDS on
it: `SilkCorner.corner_inputs` no longer feeds the member the patch's
full 4x4 base net -- it extracts the patch's ring CORNER CELL (the subgrid
cell at the junction, with its weights) and searches corner index +
reversal for the member whose collapsed row lands on the ring's shared
corner; `SilkMachinery.pair_common` then admits that row's two coincident
corner slots by the degeneracy rule (one collapsed end row against one
neighbour corner). The built CornerBlend has 36 poles, one face, a
non-empty Shape and an idempotent second ask. See
Tests/test_cube_corner_3valent.py for the executed record and the raw seam
measurement.
"""

import FreeCAD
import Part

import SilkWorkflowOps as ops

# ---------------------------------------------------------------------------
# Geometry data
# ---------------------------------------------------------------------------

# 7 junction points: the shared origin (the cube corner), the three far
# ends of the shared axes, and the three outer corners of the faces.
JUNCTIONS = {
    "O":  (0.0, 0.0, 0.0),   # the corner itself (all 3 patches meet here)
    "PX": (1.0, 0.0, 0.0),   # x-axis end    (PatchA | PatchC)
    "PY": (0.0, 1.0, 0.0),   # y-axis end    (PatchA | PatchB)
    "PZ": (0.0, 0.0, 1.0),   # z-axis end    (PatchB | PatchC)
    "Q":  (1.0, 1.0, 0.0),   # PatchA outer corner
    "S":  (0.0, 1.0, 1.0),   # PatchB outer corner
    "U":  (1.0, 0.0, 1.0),   # PatchC outer corner
}

# 9 edges: (name, start_junction, end_junction). Interior poles are placed
# at the thirds of the straight segment, so every edge is a straight cubic
# Bezier and the quad fills are exact planar squares.
EDGES = [
    # shared axis edges (each referenced by two patches)
    ("E_AB", "O", "PY"),   # y axis
    ("E_AC", "O", "PX"),   # x axis
    ("E_BC", "O", "PZ"),   # z axis
    # outer boundary of PatchA (z = 0)
    ("E_A1", "PX", "Q"),   # (1,0,0) -> (1,1,0)
    ("E_A2", "Q", "PY"),   # (1,1,0) -> (0,1,0)
    # outer boundary of PatchB (x = 0)
    ("E_B1", "PY", "S"),   # (0,1,0) -> (0,1,1)
    ("E_B2", "S", "PZ"),   # (0,1,1) -> (0,0,1)
    # outer boundary of PatchC (y = 0)
    ("E_C1", "PX", "U"),   # (1,0,0) -> (1,0,1)
    ("E_C2", "U", "PZ"),   # (1,0,1) -> (0,0,1)
]

# 3 patches: (name, edge0, edge1, edge2, edge3) in cyclic walk order.
#   PatchA: O -> PY -> Q -> PX -> O
#   PatchB: O -> PY -> S -> PZ -> O
#   PatchC: O -> PX -> U -> PZ -> O
PATCHES = [
    ("PatchA", "E_AB", "E_A2", "E_A1", "E_AC"),
    ("PatchB", "E_AB", "E_B1", "E_B2", "E_BC"),
    ("PatchC", "E_AC", "E_C1", "E_C2", "E_BC"),
]

# 3 blend strips (ring): (name, patch_a, patch_b) — the shared seam is
# auto-detected from the patches' corner poles. The (patch_a, patch_b)
# order is also the strip's U direction (patch_a at U0, patch_b at U5),
# and the ring's orientation chain requires each strip's patch_b to be
# the next strip's patch_a, so the three strips are built as the
# directed cycle A -> B -> C -> A (names B_AB, B_BC, B_CA).
STRIPS = [
    ("B_AB", "PatchA", "PatchB"),
    ("B_BC", "PatchB", "PatchC"),
    ("B_CA", "PatchC", "PatchA"),
]


# ---------------------------------------------------------------------------
# Sketch builder
# ---------------------------------------------------------------------------

def node_sketch(doc, name, base_key, pole):
    """Create one 2N node sketch at junction `base_key`.

    Local geometry: circle at (0,0) r=1 (center -> endpoint pole) plus a
    line from (0,0) to (d,0) (far end -> interior pole `pole` in world).
    Same convention as Tests/corner_model.node_sketch; the circle radius is
    irrelevant to ControlPoly4_2N (center only).
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
    sk.addGeometry(Part.Circle(FreeCAD.Vector(0, 0, 0),
                               FreeCAD.Vector(0, 0, 1), 1.0), False)
    sk.addGeometry(Part.LineSegment(FreeCAD.Vector(0, 0, 0),
                                    FreeCAD.Vector(ln, 0, 0)), False)
    return sk


def edge_poles(start_key, end_key):
    """(p1, p2): the straight-cubic interior poles at the segment thirds."""
    a = FreeCAD.Vector(*JUNCTIONS[start_key])
    b = FreeCAD.Vector(*JUNCTIONS[end_key])
    return (a + (b - a) * (1.0 / 3.0), a + (b - a) * (2.0 / 3.0))


# ---------------------------------------------------------------------------
# Model builder
# ---------------------------------------------------------------------------

def build_cube_corner_model(doc):
    """Build the 3-patch cube-corner model in `doc` via the ops layer only.

    Returns dict: {'sketches': {edge: (sk_a, sk_b)}, 'edges': {name: obj},
                   'patches': {name: obj}, 'strips': {name: obj}}
    """
    active = FreeCAD.ActiveDocument
    FreeCAD.setActiveDocument(doc.Name)
    try:
        sketches = {}
        edges = {}
        for (ename, skey, ekey) in EDGES:
            p1, p2 = edge_poles(skey, ekey)
            sk_a = node_sketch(doc, "NS_%s_a" % ename, skey, p1)
            sk_b = node_sketch(doc, "NS_%s_b" % ename, ekey, p2)
            sketches[ename] = (sk_a, sk_b)
            edges[ename] = ops.create_edge([sk_a, sk_b], name=ename)

        patches = {}
        for (pname, e0, e1, e2, e3) in PATCHES:
            patches[pname] = ops.create_patch(
                [edges[e0], edges[e1], edges[e2], edges[e3]],
                name=pname)

        strips = {}
        for (bname, pa, pb) in STRIPS:
            strips[bname] = ops.create_blend(patches[pa], patches[pb],
                                             name=bname)

        return {"sketches": sketches, "edges": edges,
                "patches": patches, "strips": strips}
    finally:
        FreeCAD.setActiveDocument(active.Name)
