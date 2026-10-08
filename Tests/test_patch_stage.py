"""
Patch stage (ticket #19): create_patch op + check_patch44 oracle.

Positive: 4 loop edges (a 50x50 square) -> create_patch -> full oracle
green (structural + P1-P4), no console errors.
Negative: deliberately corrupted pole states / wrong edge arguments
must be flagged by the corresponding checks -- the oracle returns
failures, it never raises.
"""

import FreeCAD
import Part

Vector = FreeCAD.Vector

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
    """Reversed interior row U1 -> the fold/flip check (P3) must fail."""
    errors, checks = [], []
    from SilkWorkflowOps import create_patch
    from SilkChecks import check_patch44

    edges = _make_loop_edges(doc)
    patch = create_patch(edges[0], edges[1], edges[2], edges[3], name="PatchTest")
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
    test_create_patch_4_edges,
    test_oracle_flags_flipped_row,
    test_oracle_flags_seam_offset,
    test_oracle_flags_misassigned_edge,
]
