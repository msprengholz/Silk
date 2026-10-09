"""
Unified Patch (ticket #37): 4-edge quad fill from a variable-length Edges
list, built through the ops layer (create_patch_unified) and validated by
the check_patch oracle.

Positive: 4 loop edges -> create_patch_unified -> check_patch fully green;
pole parity vs the existing Patch44 at 1e-6 (the same ControlGrid44_4
layout, so the unified pipeline reproduces the chain later); mutation of
USplits/VSplits recomputes cleanly and the oracle stays green.

Negative: a boundary pole corrupted WITHOUT recompute must be flagged by
the C-boundary (P2) check -- the oracle returns a failure, never raises.
"""

import FreeCAD
import Part


def _make_loop_edges(doc):
    """Four 4-pole loop edges forming a closed square, cyclic order e0..e3."""
    from SilkWorkflowOps import create_edge
    pts = {
        "edge0": [FreeCAD.Vector(0, 0, 0), FreeCAD.Vector(16.7, 0, 0),
                  FreeCAD.Vector(33.3, 0, 0), FreeCAD.Vector(50, 0, 0)],
        "edge1": [FreeCAD.Vector(50, 0, 0), FreeCAD.Vector(50, 16.7, 0),
                  FreeCAD.Vector(50, 33.3, 0), FreeCAD.Vector(50, 50, 0)],
        "edge2": [FreeCAD.Vector(50, 50, 0), FreeCAD.Vector(33.3, 50, 0),
                  FreeCAD.Vector(16.7, 50, 0), FreeCAD.Vector(0, 50, 0)],
        "edge3": [FreeCAD.Vector(0, 50, 0), FreeCAD.Vector(0, 33.3, 0),
                  FreeCAD.Vector(0, 16.7, 0), FreeCAD.Vector(0, 0, 0)],
    }
    edges = []
    for i in range(4):
        sk = doc.addObject("Sketcher::SketchObject", "Sketch%d" % i)
        for j in range(3):
            sk.addGeometry(Part.LineSegment(pts["edge%d" % i][j],
                                            pts["edge%d" % i][j + 1]))
        doc.recompute()
        edges.append(create_edge(sk, name="Edge%d" % i))
    return edges


def _check_errors(context, results, errors, checks):
    bad = [(n, d) for (n, ok, d) in results if not ok]
    if bad:
        errors.append("%s oracle failures: %s" % (context, bad))
    checks.append("%s: %d checks, %d failed" % (context, len(results), len(bad)))


def test_unified_patch_4_edges(doc):
    """4 loop edges -> create_patch_unified -> check_patch fully green."""
    errors, checks = [], []
    from SilkWorkflowOps import create_patch_unified
    from SilkChecks import check_patch

    edges = _make_loop_edges(doc)
    patch = create_patch_unified(edges, name="PatchU")
    if patch is None or getattr(patch, "object_type", None) != "Patch":
        errors.append("create_patch_unified did not return a unified Patch")
        return {"pass": False, "errors": errors, "checks": checks}
    if len(list(patch.Edges)) != 4:
        errors.append("Edges link list != 4 entries")
    if len(patch.Poles) != 16:
        errors.append("expected 16 poles, got %d" % len(patch.Poles))
    checks.append("create_patch_unified -> %s (%d poles, %d edges)"
                  % (patch.Name, len(patch.Poles), len(list(patch.Edges))))

    results = check_patch(patch, edges)
    _check_errors("check_patch", results, errors, checks)
    return {"pass": not errors, "errors": errors, "checks": checks}


def test_unified_patch_pole_parity(doc):
    """Unified Patch reproduces the SAME 16 poles as Patch44 for identical
    edges in the same order (tolerance 1e-6)."""
    errors, checks = [], []
    from SilkWorkflowOps import create_patch, create_patch_unified

    edges = _make_loop_edges(doc)
    p44 = create_patch(edges[0], edges[1], edges[2], edges[3], name="P44")
    pun = create_patch_unified(edges, name="PUn")

    if len(p44.Poles) != 16 or len(pun.Poles) != 16:
        errors.append("missing poles (Patch44=%d, unified=%d)"
                      % (len(p44.Poles), len(pun.Poles)))
        return {"pass": False, "errors": errors, "checks": checks}

    dmax = max((a - b).Length for a, b in zip(pun.Poles, p44.Poles))
    if dmax > 1e-6:
        errors.append("pole parity deviates by %.3e (tol 1e-6)" % dmax)
    checks.append("uniform->Patch44 max pole deviation %.2e (tol 1e-6)" % dmax)

    wmax = max(abs(a - b) for a, b in zip(pun.Weights, p44.Weights))
    if wmax > 1e-12:
        errors.append("weight parity deviates by %.3e" % wmax)
    checks.append("uniform->Patch44 max weight deviation %.2e" % wmax)
    return {"pass": not errors, "errors": errors, "checks": checks}


def test_unified_oracle_flags_c_boundary(doc):
    """A boundary pole corrupted WITHOUT recompute must be flagged by the
    C-boundary (P2) check -- check_patch never raises."""
    errors, checks = [], []
    from SilkWorkflowOps import create_patch_unified
    from SilkChecks import check_patch

    edges = _make_loop_edges(doc)
    patch = create_patch_unified(edges, name="PatchU")
    poles = list(patch.Poles)
    poles[1] = poles[1] + FreeCAD.Vector(0.5, 0, 0)  # p01 off edge0
    patch.Poles = poles  # no recompute -> oracle reads the stale boundary

    results = check_patch(patch, edges)
    failed = {n: d for (n, ok, d) in results if not ok}
    boundary_fails = [n for n in failed if "boundary" in n]
    if not boundary_fails:
        errors.append("corrupted boundary pole not flagged; failed: %s" % failed)
    else:
        checks.append("C-boundary check flagged: %s" % boundary_fails)
    return {"pass": not errors, "errors": errors, "checks": checks}


def test_unified_mutation_splits(doc):
    """Editing USplits/VSplits on a built unified Patch and recomputing
    stays clean: surface valid, subgrids rebuild, oracle still passes."""
    errors, checks = [], []
    from SilkWorkflowOps import create_patch_unified
    from SilkChecks import check_patch

    edges = _make_loop_edges(doc)
    patch = create_patch_unified(edges, name="PatchU")

    patch.USplits = [0.3]
    patch.VSplits = [0.7]
    doc.recompute()

    if patch.Shape is None or patch.Shape.isNull():
        errors.append("empty Shape after split mutation")
    subgrids = getattr(patch.Proxy, "_subgrids", [])
    if not subgrids:
        errors.append("no subgrids rebuilt after split mutation")
    checks.append("subgrids after mutation: %d cells" % len(subgrids))

    results = check_patch(patch, edges)
    _check_errors("check_patch after mutation", results, errors, checks)

    # restore splits and confirm recompute stays valid
    patch.USplits = []
    patch.VSplits = []
    doc.recompute()
    if patch.Shape is None or patch.Shape.isNull():
        errors.append("empty Shape after clearing splits")
    results2 = check_patch(patch, edges)
    _check_errors("check_patch after clearing splits", results2, errors, checks)
    return {"pass": not errors, "errors": errors, "checks": checks}


ALL_TESTS = [
    test_unified_patch_4_edges,
    test_unified_patch_pole_parity,
    test_unified_oracle_flags_c_boundary,
    test_unified_mutation_splits,
]
