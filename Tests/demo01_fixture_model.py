"""Demo 01 fixture model (ticket #98): the documented
sketch -> Edge -> Patch -> Blend -> CornerBlend mapping for
`Resources/Test_files/examples/SketchOnly_Demo01Subset.FCStd`, and the
ops-layer driver that reproduces Demo 01's topology from it.

WHY THE FIXTURE CARRIES A SUPPLEMENT.  Demo 01 stores HALF the shape: its rib
curves run (mirrored hoop) -> symmetry plane (u = 0.5) -> modelled hoop
(u = 1), and its five ring faces consume only the u in [0.5, 1] half of each
rib (a legacy `ControlPoly4_segment` piece).  A Silk `Edge` consumes WHOLE
sketches -- it has no trim property -- so with the demo's whole ribs the four
ring faces cannot close a loop and the click-through dies at `create_patch`
(`Tests/test_demo01_rebuild.py` pins that, on the demo's own sketches).  The
fixture therefore adds FOUR half-rib sketches (`HALF_RIB_SUPPLEMENT`), each
the u in [0.5, 1] sub-curve of a demo rib as an ordinary 3-line ControlPoly4
sketch (the sub-curve of a cubic Bezier is exactly a cubic Bezier; the poles
are computed by `Tests/make_demo01_fixture.py`, never hand-typed).

THE TWO ORDERING CONTRACTS (both measured, both pinned in the tests):

1. PATCH EDGE ORDER.  `create_patch` normalizes the boundary CYCLE but keeps
   the caller's first edge and direction, so the click order fixes each
   face's parameterization.  The corner stage requires the four ring faces to
   agree about which parametric end of a seam the junction is at
   (`SilkCorner.corner_inputs`' `li_map`); with the demo's own stored grid
   order they disagree at EVERY junction and each corner refuses with
   "its two patches disagree about which end is the junction (twisted
   input)".  The order below is a measured consistent one: Front/Top/Back
   keep the demo's stored order (so their nets compare pole-for-pole with no
   transform at all), Right is rotated one edge and Bottom two.
2. BLEND DIRECTION.  A strip runs PatchA (U0) -> PatchB (U5), and
   `SilkMachinery.corner_grid` assembles a ring only from strips whose
   PatchB is the next strip's PatchA.  So the three blends around a 3-valent
   junction must form a directed 3-cycle.  `SilkWorkflowOps.create_blend`
   takes that pair order from the caller (the toolbar's 2-patch selection
   order); `create_blend_by_edge`/the panel's seam tick derives it from
   document order, which can never close a 3-cycle.  `BLENDS` below is one of
   the two directed assignments of this ring (its mirror is the other).

No continuity label is asserted anywhere in this model or its tests.
"""

import os
import shutil
import tempfile

import FreeCAD

import SilkChecks
import SilkWorkflowOps as OPS

_SILK_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIXTURE_PATH = os.path.join(_SILK_DIR, "Resources", "Test_files", "examples",
                            "SketchOnly_Demo01Subset.FCStd")
DEMO01_PATH = os.path.join(_SILK_DIR, "Resources", "Demo_files",
                           "Silk_Demo_01.FCStd")

# The documented supplement (see the module docstring).  The fixture guard in
# `Tests/test_example_documents.py` asserts the fixture carries the demo's 29
# sketches AND that every other sketch is one of these four.
HALF_RIB_SUPPLEMENT = ("SK_Half_Rib_FB", "SK_Half_Rib_FT",
                       "SK_Half_Rib_BkB", "SK_Half_Rib_TBk")

# (edge name, sketches it consumes, the demo's stored ControlPoly4 the built
#  Edge must be pole-identical to).  The half-rib edges are compared against
#  the demo's stored `ControlPoly4_segment` pieces -- that is the measurement
#  that says the half is the RIGHT half.
EDGES = (
    ("E_front_out", ("Sketch015",), "ControlPoly4_3L"),
    ("E_top_out", ("Sketch016",), "ControlPoly4_3L003"),
    ("E_back_out", ("Sketch017",), "ControlPoly4_3L002"),
    ("E_bottom_out", ("Sketch018",), "ControlPoly4_3L001"),
    ("E_half_rib_FB", ("SK_Half_Rib_FB",), "ControlPoly4_segment001"),
    ("E_half_rib_FT", ("SK_Half_Rib_FT",), "ControlPoly4_segment"),
    ("E_half_rib_BkB", ("SK_Half_Rib_BkB",), "ControlPoly4_segment002"),
    ("E_half_rib_TBk", ("SK_Half_Rib_TBk",), "ControlPoly4_segment003"),
    ("E_right_FR", ("Sketch036", "Sketch037"), "ControlPoly4_2N001"),
    ("E_right_BR", ("Sketch038", "Sketch039"), "ControlPoly4_2N003"),
    ("E_right_TR", ("Sketch042", "Sketch045"), "ControlPoly4_2N004"),
    ("E_right_BkR", ("Sketch032", "Sketch035"), "ControlPoly4_2N"),
)

# check_edge's E2 heuristic is violated by the demo's OWN stored
# Bottom_Right hoop poly: p2->p3 70.711 > 1.05 x p2->p0 63.246.  The rebuilt
# edge is pole-identical to that legacy object, so the deviation is inherited
# from the demo's input geometry, not introduced by the rebuild (the same
# acceptance `Tests/test_demo01_rebuild.py` has always carried).
KNOWN_E2_EDGE = "E_right_BR"

# (patch name, the edge click order -- entry k is boundary side k -- and the
#  demo's stored base grid the built 16 poles must reproduce, up to the
#  named dihedral image of a 4x4 net).
PATCHES = (
    ("P_Front",
     ("E_half_rib_FB", "E_right_FR", "E_half_rib_FT", "E_front_out"),
     "ControlGrid44_4"),
    ("P_Top",
     ("E_half_rib_FT", "E_right_TR", "E_half_rib_TBk", "E_top_out"),
     "ControlGrid44_4001"),
    ("P_Right",
     ("E_right_BR", "E_right_BkR", "E_right_TR", "E_right_FR"),
     "ControlGrid44_4002"),
    ("P_Bottom",
     ("E_bottom_out", "E_half_rib_BkB", "E_right_BR", "E_half_rib_FB"),
     "ControlGrid44_4005"),
    ("P_Back",
     ("E_back_out", "E_half_rib_TBk", "E_right_BkR", "E_half_rib_BkB"),
     "ControlGrid44_4006"),
)

# The same five faces in the demo's OWN stored grid order (its `Poly0..Poly3`
# links) -- the pole-parity order.  Used by the tests that pin what that order
# cannot do (the four corners refuse).
DEMO_ORDER_PATCHES = (
    ("P_Front",
     ("E_half_rib_FB", "E_right_FR", "E_half_rib_FT", "E_front_out")),
    ("P_Top",
     ("E_half_rib_FT", "E_right_TR", "E_half_rib_TBk", "E_top_out")),
    ("P_Right",
     ("E_right_FR", "E_right_BR", "E_right_BkR", "E_right_TR")),
    ("P_Bottom",
     ("E_right_BR", "E_half_rib_FB", "E_bottom_out", "E_half_rib_BkB")),
    ("P_Back",
     ("E_back_out", "E_half_rib_TBk", "E_right_BkR", "E_half_rib_BkB")),
)

# (blend name, patch A, patch B, the seam edge) -- the directed cycles around
# the four junctions (see the module docstring, contract 2).
BLENDS = (
    ("B_FB", "P_Bottom", "P_Front", "E_half_rib_FB"),
    ("B_FT", "P_Top", "P_Front", "E_half_rib_FT"),
    ("B_FR", "P_Front", "P_Right", "E_right_FR"),
    ("B_BR", "P_Right", "P_Bottom", "E_right_BR"),
    ("B_BkB", "P_Bottom", "P_Back", "E_half_rib_BkB"),
    ("B_TBk", "P_Top", "P_Back", "E_half_rib_TBk"),
    ("B_TR", "P_Right", "P_Top", "E_right_TR"),
    ("B_BkR", "P_Back", "P_Right", "E_right_BkR"),
)

# (corner name, the 3 ring blends, the junction point the fill must cover)
CORNERS = (
    ("CB_J1_FrontTopRight", ("B_FT", "B_FR", "B_TR"), (20.0, -85.0, 50.0)),
    ("CB_J2_FrontRightBottom", ("B_FB", "B_FR", "B_BR"), (20.0, -75.0, 0.0)),
    ("CB_J3_TopRightBack", ("B_TR", "B_TBk", "B_BkR"),
     (185.0, -50.0, 60.0)),
    ("CB_J4_RightBottomBack", ("B_BR", "B_BkB", "B_BkR"),
     (150.0, -45.0, 0.0)),
)


def used_sketch_names():
    """The 16 sketches the click-through consumes (12 of the demo's 29 + the
    4 supplement halves).  The demo's four FULL-rib sketches are not among
    them: they are the demo's original inputs, not the rebuild's."""
    names = []
    for _name, sketches, _legacy in EDGES:
        for sk in sketches:
            if sk not in names:
                names.append(sk)
    return names


# ---- opening a fixture without a stale in-memory copy ---------------------
#
# `FreeCAD.openDocument(path)` hands back an ALREADY-OPEN document whose file
# path matches (measured on the running GUI: opening a file that had been
# rewritten on disk returned the stale in-memory document, 33 vs 4 objects).
# A fixture that was regenerated while an older copy is open would therefore
# be validated in its stale form, so the fixture tests open a private copy
# under a name no other document can hold.

_SEQ = [0]


def open_fresh(path):
    """Open `path` from a private copy.  Returns (doc, tmpdir)."""
    _SEQ[0] += 1
    stem = os.path.splitext(os.path.basename(path))[0]
    tmpdir = tempfile.mkdtemp(prefix="silk_fixture_")
    copy = os.path.join(tmpdir, "%s__open%d.FCStd" % (stem, _SEQ[0]))
    shutil.copyfile(path, copy)
    doc = FreeCAD.openDocument(copy)
    return doc, tmpdir


def close_fresh(doc, tmpdir):
    """Close a document `open_fresh` produced and drop its temp copy."""
    try:
        FreeCAD.closeDocument(doc.Name)
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


# ---- pole parity ---------------------------------------------------------

def _net(poles):
    return [[poles[r * 4 + c] for c in range(4)] for r in range(4)]


def _flat(net):
    return [net[r][c] for r in range(4) for c in range(4)]


def _rot90(net):
    return [[net[3 - c][r] for c in range(4)] for r in range(4)]


def dihedral_images(poles):
    """The 8 dihedral images of a 16-pole net, keyed by how they are built.

    A patch's parameterization is its boundary cycle order, so a differently
    ordered build returns the SAME control net under a symmetry of the square
    (D4).  Naming the symmetry is what turns "the poles differ" into "the
    poles are the same net, parameterized differently".
    """
    out = {}
    base = _net(poles)
    net = base
    for k in range(4):
        out["rot%d" % (90 * k)] = _flat(net)
        net = _rot90(net)
    net = [[base[c][r] for c in range(4)] for r in range(4)]
    for k in range(4):
        out["transpose_rot%d" % (90 * k)] = _flat(net)
        net = _rot90(net)
    return out


def pole_parity(poles, reference_poles):
    """(transform name, max delta) of the best dihedral image of `poles`
    against `reference_poles` -- 16 poles each (4x4)."""
    best = None
    for name, image in dihedral_images(poles).items():
        delta = max((image[i] - reference_poles[i]).Length
                    for i in range(16))
        if best is None or delta < best[1]:
            best = (name, delta)
    return best


def straight_pole_delta(poles, reference_poles):
    """Max delta pole-for-pole, in the stored order (no transform)."""
    return max((poles[i] - reference_poles[i]).Length
               for i in range(len(reference_poles)))


# ---- the build -----------------------------------------------------------

class CaptureConsole:
    """Capture FreeCAD.Console.PrintError for one block (refusal texts)."""

    def __enter__(self):
        self._orig = FreeCAD.Console.PrintError
        self.errors = []
        FreeCAD.Console.PrintError = lambda msg: (
            self.errors.append(msg), self._orig(msg))
        return self

    def __exit__(self, *args):
        FreeCAD.Console.PrintError = self._orig


def _copy_sketch(target_doc, source_doc, name):
    """Copy one sketch's geometry + placement into `target_doc` under the
    same name (constraints are not needed to build an Edge)."""
    src = source_doc.getObject(name)
    dst = target_doc.addObject("Sketcher::SketchObject", name)
    dst.Placement = src.Placement
    for g in src.Geometry:
        dst.addGeometry(g, False)
    return dst


def _failed(results):
    return [(n, d) for (n, ok, d) in results if not ok]


def build(doc, source=None, corners=True):
    """Drive the documented click-through in `doc`.

    `corners=False` stops after the blends, leaving the four 3-valent
    junctions unfilled -- the input a panel test needs to drive the corner
    section itself (a junction that already has a corner is an idempotent
    no-op, so a pre-built corner could never be confirmed anew).

    Copies the 16 sketches it needs from `source` (an open fixture; opened
    fresh when omitted) and creates 12 Edges, 5 Patches, 8 Blends and 4
    CornerBlends through the ops layer.  Returns a result dict:
    sketches/edges/patches/blends/corners, the seam inventory, per-object
    oracle failures, per-corner console output, and `problems` -- one string
    per refused step, so a test can turn them straight into errors.
    """
    result = {"edges": {}, "patches": {}, "blends": {}, "corners": {},
              "problems": [], "edge_checks": {}, "patch_checks": {},
              "blend_checks": {}, "console": {}, "seam_inventory": []}
    active = FreeCAD.ActiveDocument
    opened = opened_dir = None
    if source is None:
        source, opened_dir = open_fresh(FIXTURE_PATH)
        opened = source
    try:
        FreeCAD.setActiveDocument(doc.Name)
        for name in used_sketch_names():
            _copy_sketch(doc, source, name)
        doc.recompute()

        for name, sketches, _legacy in EDGES:
            with CaptureConsole() as cap:
                edge = OPS.create_edge([doc.getObject(s) for s in sketches],
                                       name=name)
            if edge is None:
                result["problems"].append("edge %s refused: %s"
                                          % (name, cap.errors))
                continue
            result["edges"][name] = edge
            result["edge_checks"][name] = _failed(SilkChecks.check_edge(edge))

        for name, order, _grid in PATCHES:
            if any(k not in result["edges"] for k in order):
                result["problems"].append("patch %s: an edge did not build"
                                          % name)
                continue
            with CaptureConsole() as cap:
                patch = OPS.create_patch([result["edges"][k] for k in order],
                                         name=name)
            if patch is None:
                result["problems"].append("patch %s refused: %s"
                                          % (name, cap.errors))
                continue
            result["patches"][name] = patch
            result["patch_checks"][name] = _failed(
                SilkChecks.check_patch(patch, list(patch.Edges)))

        # Blends: the seam is auto-detected (the toolbar's two-patch path,
        # no Edge pin); the PAIR ORDER is the documented direction.
        for name, pa, pb, _edge in BLENDS:
            if pa not in result["patches"] or pb not in result["patches"]:
                result["problems"].append("blend %s: a patch did not build"
                                          % name)
                continue
            with CaptureConsole() as cap:
                blend = OPS.create_blend(result["patches"][pa],
                                         result["patches"][pb], name=name)
            result["blends"][name] = blend
            result["console"][name] = list(cap.errors)
            result["blend_checks"][name] = _failed(
                SilkChecks.check_blend(blend, blend.PatchA, blend.PatchB))
        result["seam_inventory"] = [
            (e["edge"].Name, e["status"]) for e in OPS.seam_inventory(doc)]

        for name, ring, _point in (CORNERS if corners else ()):
            if any(b not in result["blends"] for b in ring):
                result["problems"].append("corner %s: a blend did not build"
                                          % name)
                continue
            with CaptureConsole() as cap:
                corner = OPS.create_corner_blend(
                    [result["blends"][b] for b in ring], name=name)
            result["console"][name] = list(cap.errors)
            if corner is None:
                result["problems"].append("corner %s refused: %s"
                                          % (name, " ".join(cap.errors).strip()))
                continue
            result["corners"][name] = corner
    finally:
        FreeCAD.setActiveDocument(active.Name if active else "")
        if opened is not None:
            close_fresh(opened, opened_dir)
    return result


def build_demo_order_patches(doc, source=None):
    """The same 12 Edges and 8 Blends, but with each face built in the demo's
    OWN stored grid order (`DEMO_ORDER_PATCHES`).  Returns the build result;
    the corner stage is expected to refuse -- the tests pin that text."""
    result = {"edges": {}, "patches": {}, "blends": {}, "corners": {},
              "problems": [], "console": {}}
    active = FreeCAD.ActiveDocument
    opened = opened_dir = None
    if source is None:
        source, opened_dir = open_fresh(FIXTURE_PATH)
        opened = source
    try:
        FreeCAD.setActiveDocument(doc.Name)
        for name in used_sketch_names():
            _copy_sketch(doc, source, name)
        doc.recompute()
        edges = {}
        for name, sketches, _legacy in EDGES:
            edges[name] = OPS.create_edge([doc.getObject(s) for s in sketches],
                                          name=name)
        patches = {}
        for name, order in DEMO_ORDER_PATCHES:
            patches[name] = OPS.create_patch([edges[k] for k in order],
                                             name=name)
        blends = {}
        for name, pa, pb, _edge in BLENDS:
            blends[name] = OPS.create_blend(patches[pa], patches[pb],
                                            name=name)
        result["edges"], result["patches"] = edges, patches
        result["blends"] = blends
        for name, ring, _point in CORNERS:
            with CaptureConsole() as cap:
                corner = OPS.create_corner_blend(
                    [blends[b] for b in ring], name=name)
            result["console"][name] = list(cap.errors)
            if corner is None:
                result["problems"].append(" ".join(cap.errors).strip())
            else:
                result["corners"][name] = corner
    finally:
        FreeCAD.setActiveDocument(active.Name if active else "")
        if opened is not None:
            close_fresh(opened, opened_dir)
    return result
