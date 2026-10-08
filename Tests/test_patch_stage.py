"""
Patch stage (ticket #19): create_patch op + check_patch44 oracle.

Positive: 4 loop edges (a 50x50 square) -> create_patch -> full oracle
green (structural + P1-P4), no console errors.
Negative: deliberately corrupted pole states / wrong edge arguments
must be flagged by the corresponding checks -- the oracle returns
failures, it never raises.
"""

import FreeCAD
import os
import Part

Vector = FreeCAD.Vector

FIXTURE = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                       "..", "Resources", "Test_files", "Silk_Workflow.FCStd")

# Which 4 edges drive each stored ground-truth patch (cyclic order), and
# which fixture sketches drive each edge. Extracted by corner matching
# (ticket #19); the chain test (#21) owns the full 7-edge table as data.
GT_PATCH44_EDGES = [
    ("E_Top", ["Sketch007", "Sketch008"]),
    ("E_Left", ["Sketch005"]),
    ("E_BtmL", ["Sketch006"]),
    ("E_Shr", ["Sketch"]),
]

GT_PATCH001_EDGES = [
    ("E_Shr", ["Sketch"]),
    ("E_BtmR", ["Sketch001"]),
    ("E_CurR", ["Sketch003", "Sketch004"]),
    ("E_TopR", ["Sketch002"]),
]

# 50x50 square, one straight 3-line sketch per side, cyclic direction.
_SIDE_PTS = {
    "edge0": [Vector(0, 0, 0), Vector(16.7, 0, 0), Vector(33.3, 0, 0), Vector(50, 0, 0)],
    "edge1": [Vector(50, 0, 0), Vector(50, 16.7, 0), Vector(50, 33.3, 0), Vector(50, 50, 0)],
    "edge2": [Vector(50, 50, 0), Vector(33.3, 50, 0), Vector(16.7, 50, 0), Vector(0, 50, 0)],
    "edge3": [Vector(0, 50, 0), Vector(0, 33.3, 0), Vector(0, 16.7, 0), Vector(0, 0, 0)],
}


def _make_3l_sketch(doc, name, pts):
    sk = doc.addObject("Sketcher::SketchObject", name)
    sk.addGeometry(Part.LineSegment(pts[0], pts[1]))
    sk.addGeometry(Part.LineSegment(pts[1], pts[2]))
    sk.addGeometry(Part.LineSegment(pts[2], pts[3]))
    doc.recompute()
    return sk


def _make_loop_edges(doc):
    """Four edges forming a closed square loop, cyclic order e0..e3."""
    from SilkWorkflowOps import create_edge
    edges = []
    for i in range(4):
        sk = _make_3l_sketch(doc, "Sketch%d" % i, _SIDE_PTS["edge%d" % i])
        edges.append(create_edge(sk, name="Edge%d" % i))
    return edges


class _CaptureConsole:
    def __enter__(self):
        self.errors = []
        self._orig = FreeCAD.Console.PrintError
        FreeCAD.Console.PrintError = lambda m: (self.errors.append(str(m)), self._orig(m))
        return self

    def __exit__(self, *args):
        FreeCAD.Console.PrintError = self._orig


def _copy_fixture_edge(doc, fixture_doc, edge_name, sketch_names):
    """Recreate one fixture edge in the test doc from its sketch geometry."""
    from SilkWorkflowOps import create_edge
    sks = []
    for sn in sketch_names:
        src = fixture_doc.getObject(sn)
        sk = doc.addObject("Sketcher::SketchObject", sn + "_c")
        sk.Placement = src.Placement
        for i in range(src.GeometryCount):
            sk.addGeometry(src.Geometry[i], src.getConstruction(i))
        sks.append(sk)
    doc.recompute()
    if len(sks) == 1:
        return create_edge(sks[0], name=edge_name + "_n")
    return create_edge(sks, name=edge_name + "_n")


def _build_gt_edges(doc, fixture_doc, edge_table):
    """Recreate the fixture edges from a (edge_name, [sketch names]) table
    in the test doc. `fixture_doc` must already be open."""
    edges = []
    for edge_name, sketch_names in edge_table:
        edges.append(_copy_fixture_edge(doc, fixture_doc, edge_name, sketch_names))
    return edges


def _build_gt_patch(doc, fixture_doc):
    """Build the ground-truth Patch44 (curved) in the test doc from the
    fixture's sketches. `fixture_doc` must already be open."""
    from SilkWorkflowOps import create_patch
    edges = _build_gt_edges(doc, fixture_doc, GT_PATCH44_EDGES)
    patch = create_patch(edges[0], edges[1], edges[2], edges[3], name="Patch44")
    return patch, edges


def test_create_patch_ground_truth(doc):
    """Build the real (curved) Patch44 from fixture sketches; all 16 poles
    and 16 weights must match the stored ground-truth patch exactly, and
    the oracle must be fully green."""
    errors, checks = [], []
    from SilkChecks import check_patch44

    fixture_doc = FreeCAD.openDocument(FIXTURE)
    FreeCAD.setActiveDocument(doc.Name)  # openDocument activates the fixture
    try:
        with _CaptureConsole() as cap:
            patch, edges = _build_gt_patch(doc, fixture_doc)
        if cap.errors:
            errors.append("console errors during create_patch: %s" % cap.errors)

        for (edge_name, _), e in zip(GT_PATCH44_EDGES, edges):
            stored = fixture_doc.getObject(edge_name)
            dmax = max((a - b).Length for a, b in zip(e.Poles, stored.Poles))
            if dmax > 1e-6:
                errors.append("edge %s deviates from stored by %.3e" % (edge_name, dmax))
            checks.append("edge %s: max pole deviation %.2e" % (edge_name, dmax))

        gt = fixture_doc.getObject("Patch44")
        dmax = max((a - b).Length for a, b in zip(patch.Poles, gt.Poles))
        if dmax > 1e-6:
            errors.append("patch deviates from stored Patch44 by %.3e" % dmax)
        checks.append("patch: max pole deviation %.2e (tol 1e-6)" % dmax)
        wmax = max(abs(a - b) for a, b in zip(patch.Weights, gt.Weights))
        if wmax > 1e-12:
            errors.append("weights deviate from stored by %.3e" % wmax)
        checks.append("patch: max weight deviation %.2e" % wmax)

        results = check_patch44(patch, edges)
        bad = [(n, d) for (n, ok, d) in results if not ok]
        if bad:
            errors.append("oracle flagged the ground-truth patch: %s" % bad)
        checks.append("oracle: %d checks, %d failed" % (len(results), len(bad)))
    finally:
        FreeCAD.closeDocument(fixture_doc.Name)
    return {"pass": not errors, "errors": errors, "checks": checks}


def test_create_patch_4_edges(doc):
    """4 loop edges -> create_patch -> oracle fully green."""
    errors, checks = [], []
    from SilkWorkflowOps import create_patch
    from SilkChecks import check_patch44

    edges = _make_loop_edges(doc)
    with _CaptureConsole() as cap:
        patch = create_patch(edges[0], edges[1], edges[2], edges[3], name="PatchTest")
    if cap.errors:
        errors.append("console errors during create_patch: %s" % cap.errors)
    if patch is None or getattr(patch, "object_type", None) != "Patch44":
        errors.append("create_patch did not return a Patch44 object")
        return {"pass": False, "errors": errors, "checks": checks}
    checks.append("create_patch returned %s with %d poles" % (patch.Name, len(patch.Poles)))

    results = check_patch44(patch, edges)
    bad = [(n, d) for (n, ok, d) in results if not ok]
    if bad:
        errors.append("oracle flagged a valid patch: %s" % bad)
    checks.append("oracle: %d checks, %d failed" % (len(results), len(bad)))
    return {"pass": not errors, "errors": errors, "checks": checks}


def test_oracle_flags_flipped_row(doc):
    """Reversed interior row U1 on the curved ground-truth patch -> the
    fold/flip check (P3) must fail. (A flat square would stay planar
    under a row flip, so the GT patch is used.)"""
    errors, checks = [], []
    from SilkChecks import check_patch44

    fixture_doc = FreeCAD.openDocument(FIXTURE)
    FreeCAD.setActiveDocument(doc.Name)
    try:
        patch, edges = _build_gt_patch(doc, fixture_doc)
        poles = list(patch.Poles)
        poles[4:8] = list(reversed(poles[4:8]))  # flip row U1
        patch.Poles = poles

        results = check_patch44(patch, edges)
        failed = {n: d for (n, ok, d) in results if not ok}
        flip_fails = [n for n in failed if "flip" in n or "fold" in n]
        if not flip_fails:
            errors.append("flipped row not flagged; failed checks: %s" % failed)
        else:
            checks.append("fold/flip check flagged: %s" % flip_fails)
    finally:
        FreeCAD.closeDocument(fixture_doc.Name)
    return {"pass": not errors, "errors": errors, "checks": checks}


def test_oracle_flags_seam_offset(doc):
    """Boundary pole shifted off its edge -> P2 must fail."""
    errors, checks = [], []
    from SilkWorkflowOps import create_patch
    from SilkChecks import check_patch44

    edges = _make_loop_edges(doc)
    patch = create_patch(edges[0], edges[1], edges[2], edges[3], name="PatchTest")
    poles = list(patch.Poles)
    poles[1] = poles[1] + Vector(0.5, 0, 0)  # p01 off edge0
    patch.Poles = poles

    results = check_patch44(patch, edges)
    failed = {n: d for (n, ok, d) in results if not ok}
    seam_fails = [n for n in failed if "boundary" in n]
    if not seam_fails:
        errors.append("seam offset not flagged; failed checks: %s" % failed)
    else:
        checks.append("boundary check flagged: %s" % seam_fails)
    return {"pass": not errors, "errors": errors, "checks": checks}


def test_oracle_flags_misassigned_edge(doc):
    """Wrong edge->patch correspondence in the arguments -> P1 must fail."""
    errors, checks = [], []
    from SilkWorkflowOps import create_patch
    from SilkChecks import check_patch44

    edges = _make_loop_edges(doc)
    patch = create_patch(edges[0], edges[1], edges[2], edges[3], name="PatchTest")

    results = check_patch44(patch, [edges[0], edges[2], edges[1], edges[3]])
    failed = {n: d for (n, ok, d) in results if not ok}
    corner_fails = [n for n in failed if "corner" in n]
    if not corner_fails:
        errors.append("misassigned edges not flagged; failed checks: %s" % failed)
    else:
        checks.append("corner check flagged: %s" % corner_fails)
    return {"pass": not errors, "errors": errors, "checks": checks}


ALL_TESTS = [
    test_create_patch_ground_truth,
    test_create_patch_4_edges,
    test_oracle_flags_flipped_row,
    test_oracle_flags_seam_offset,
    test_oracle_flags_misassigned_edge,
]
