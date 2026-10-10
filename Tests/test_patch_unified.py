"""
Unified Patch (tickets #37/#38): fills from a variable-length Edges list,
built through the ops layer (create_patch_unified) and validated by the
check_patch oracle. The edge count picks the fill: 4 edges -> quad fill
(#37), 3 edges -> pointed fill (#38).

Positive: 4 loop edges -> quad fill -> check_patch fully green; 3 loop
edges -> pointed fill -> check_patch fully green including the degenerate
U=0 column; pole parity vs the legacy Patch44/Patch33 at 1e-6 (the same
ControlGrid44_4/_3 layouts, so the unified pipeline reproduces the chain
later); mutation of USplits/VSplits recomputes cleanly on BOTH fills and
the oracle stays green (the 3-edge fill gets the full subgrid machinery
the legacy Patch33 lacked).

Negative: a boundary pole corrupted WITHOUT recompute must be flagged by
the boundary check (P2/C2) -- the oracle returns a failure, never raises.
Malformed input (non-connecting loops, wrong edge counts) leaves a valid
empty object without crashing.
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


def _make_triangle_edges(doc):
    """Three 4-pole loop edges forming a closed, doubly-curved triangle,
    cyclic order e0..e2 (A->B->C->A with curved, non-planar interiors)."""
    from SilkWorkflowOps import create_edge
    pts = {
        "edge0": [FreeCAD.Vector(0, 0, 0), FreeCAD.Vector(33.3, 0, 3),
                  FreeCAD.Vector(66.7, 0, 6), FreeCAD.Vector(100, 0, 10)],
        "edge1": [FreeCAD.Vector(100, 0, 10), FreeCAD.Vector(90, 33, 20),
                  FreeCAD.Vector(70, 66, 35), FreeCAD.Vector(50, 100, 40)],
        "edge2": [FreeCAD.Vector(50, 100, 40), FreeCAD.Vector(30, 66, 38),
                  FreeCAD.Vector(10, 33, 20), FreeCAD.Vector(0, 0, 0)],
    }
    edges = []
    for i in range(3):
        sk = doc.addObject("Sketcher::SketchObject", "SketchT%d" % i)
        for j in range(3):
            sk.addGeometry(Part.LineSegment(pts["edge%d" % i][j],
                                            pts["edge%d" % i][j + 1]))
        doc.recompute()
        edges.append(create_edge(sk, name="TEdge%d" % i))
    return edges


def _make_stray_edges(doc, n=3):
    """n straight 4-pole edges, mutually disjoint and disjoint from the
    loop helpers (far away in +Y), so no two of them connect."""
    from SilkWorkflowOps import create_edge
    edges = []
    for i in range(n):
        y = 200.0 + 20.0 * i
        pts = [FreeCAD.Vector(0, y, 0), FreeCAD.Vector(10, y, 0),
               FreeCAD.Vector(20, y, 0), FreeCAD.Vector(30, y, 0)]
        sk = doc.addObject("Sketcher::SketchObject", "SketchS%d" % i)
        for j in range(3):
            sk.addGeometry(Part.LineSegment(pts[j], pts[j + 1]))
        doc.recompute()
        edges.append(create_edge(sk, name="Stray%d" % i))
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


def test_unified_patch_3_edges(doc):
    """3 loop edges -> create_patch_unified -> pointed fill on the shared
    Patch type, check_patch fully green (including degenerate column)."""
    errors, checks = [], []
    from SilkWorkflowOps import create_patch_unified
    from SilkChecks import check_patch

    edges = _make_triangle_edges(doc)
    patch = create_patch_unified(edges, name="PatchU3")
    if patch is None or getattr(patch, "object_type", None) != "Patch":
        errors.append("create_patch_unified did not return a unified Patch")
        return {"pass": False, "errors": errors, "checks": checks}
    if len(list(patch.Edges)) != 3:
        errors.append("Edges link list != 3 entries")
    if len(patch.Poles) != 16:
        errors.append("expected 16 poles, got %d" % len(patch.Poles))
    checks.append("create_patch_unified -> %s (%d poles, %d edges)"
                  % (patch.Name, len(patch.Poles), len(list(patch.Edges))))

    results = check_patch(patch, edges)
    _check_errors("check_patch 3-edge", results, errors, checks)
    return {"pass": not errors, "errors": errors, "checks": checks}


def test_unified_pointed_pole_parity(doc):
    """Unified 3-edge fill reproduces the SAME 16 poles/weights as the
    legacy Patch33 for identical edges in the same order (tol 1e-6)."""
    errors, checks = [], []
    from SilkWorkflowOps import create_patch33, create_patch_unified

    edges = _make_triangle_edges(doc)
    p33 = create_patch33(edges[0], edges[1], edges[2], name="P33")
    pun = create_patch_unified(edges, name="PUn3")

    if len(p33.Poles) != 16 or len(pun.Poles) != 16:
        errors.append("missing poles (Patch33=%d, unified=%d)"
                      % (len(p33.Poles), len(pun.Poles)))
        return {"pass": False, "errors": errors, "checks": checks}

    dmax = max((a - b).Length for a, b in zip(pun.Poles, p33.Poles))
    if dmax > 1e-6:
        errors.append("pole parity deviates by %.3e (tol 1e-6)" % dmax)
    checks.append("unified->Patch33 max pole deviation %.2e (tol 1e-6)" % dmax)

    wmax = max(abs(a - b) for a, b in zip(pun.Weights, p33.Weights))
    if wmax > 1e-12:
        errors.append("weight parity deviates by %.3e" % wmax)
    checks.append("unified->Patch33 max weight deviation %.2e" % wmax)
    return {"pass": not errors, "errors": errors, "checks": checks}


def test_unified_pointed_degenerate_column(doc):
    """The pointed fill's U=0 control column collapses to a single point
    sitting on the corner shared by edges 0 and 2 (explicit assert, the
    oracle checks it too)."""
    errors, checks = [], []
    from SilkWorkflowOps import create_patch_unified
    from SilkChecks import TOL

    edges = _make_triangle_edges(doc)
    patch = create_patch_unified(edges, name="PatchU3")
    poles = list(patch.Poles)
    if len(poles) != 16:
        errors.append("expected 16 poles, got %d" % len(poles))
        return {"pass": False, "errors": errors, "checks": checks}

    col0 = [poles[i * 4] for i in range(4)]  # U=0 column
    devs = [(c - col0[0]).Length for c in col0]
    if max(devs) > TOL:
        errors.append("U=0 column not collapsed: dev %r" % devs)
    checks.append("U=0 column collapsed (max dev %.2e)" % max(devs))

    for ei in (0, 2):  # the point is the corner shared by edges 0+2
        d = min((col0[0] - q).Length
                for q in (list(edges[ei].Poles)[0], list(edges[ei].Poles)[3]))
        if d > TOL:
            errors.append("degenerate point not on edge%d endpoints "
                          "(dev %.2e)" % (ei, d))
    checks.append("degenerate point on edge0+edge2 shared corner")
    return {"pass": not errors, "errors": errors, "checks": checks}


def test_unified_pointed_subgrid_machinery(doc):
    """The 3-edge fill has the full subgrid machinery via the shared core:
    USplits/VSplits recompute rebuilds the subgrids and a valid display,
    the oracle stays green, and clearing the splits recomputes clean."""
    errors, checks = [], []
    from SilkWorkflowOps import create_patch_unified
    from SilkChecks import check_patch

    edges = _make_triangle_edges(doc)
    patch = create_patch_unified(edges, name="PatchU3")

    patch.USplits = [0.3]
    patch.VSplits = [0.7]
    doc.recompute()

    if patch.Shape is None or patch.Shape.isNull():
        errors.append("empty Shape after split mutation")
    subgrids = getattr(patch.Proxy, "_subgrids", [])
    if len(subgrids) != 4:
        errors.append("expected 4 subgrid cells, got %d" % len(subgrids))
    elif any(len(sg) != 16 for sg in subgrids):
        errors.append("subgrid cells without 16 poles")
    checks.append("subgrids after mutation: %d cells" % len(subgrids))

    patch.ShowSubgrids = True  # compound display of the sub-shapes
    doc.recompute()
    if patch.Shape is None or patch.Shape.isNull():
        errors.append("empty Shape with ShowSubgrids")
    results = check_patch(patch, edges)
    _check_errors("check_patch with subgrids", results, errors, checks)

    # restore splits and confirm recompute stays valid
    patch.ShowSubgrids = False
    patch.USplits = []
    patch.VSplits = []
    doc.recompute()
    if getattr(patch.Proxy, "_subgrids", []):
        errors.append("subgrids not cleared after clearing splits")
    if patch.Shape is None or patch.Shape.isNull():
        errors.append("empty Shape after clearing splits")
    results2 = check_patch(patch, edges)
    _check_errors("check_patch after clearing splits", results2, errors, checks)
    return {"pass": not errors, "errors": errors, "checks": checks}


def test_unified_pointed_graceful_degradation(doc):
    """Malformed 3-edge input degrades gracefully: non-connecting edges
    leave a valid empty object, and check_patch returns failures without
    raising. Wrong edge counts (2, 5) still hit the empty branch."""
    errors, checks = [], []
    from SilkWorkflowOps import create_patch_unified
    from SilkChecks import check_patch

    # (a) 3 edges whose loop does not connect
    strays = _make_stray_edges(doc, 3)
    try:
        bad3 = create_patch_unified(strays, name="PatchBad3")
    except Exception as e:
        errors.append("create_patch_unified raised on non-connecting "
                      "3 edges: %r" % e)
        return {"pass": False, "errors": errors, "checks": checks}
    if len(bad3.Poles) != 0:
        errors.append("expected empty fill for non-connecting loop, got "
                      "%d poles" % len(bad3.Poles))
    if (bad3.Shape is not None and not bad3.Shape.isNull()
            and bad3.Shape.Faces):
        errors.append("expected empty Shape for non-connecting loop")
    try:
        results = check_patch(bad3, strays)
    except Exception as e:
        errors.append("check_patch raised on non-connecting input: %r" % e)
        return {"pass": False, "errors": errors, "checks": checks}
    failed = [(n, d) for (n, ok, d) in results if not ok]
    if not failed:
        errors.append("oracle passed on empty non-connecting fill")
    checks.append("non-connecting 3-edge input flagged: %s"
                  % [n for n, _ in failed])

    # (b) wrong edge counts still hit the empty branch without crashing
    loop = _make_loop_edges(doc)
    edges5 = list(loop) + [strays[0]]
    try:
        p2 = create_patch_unified(loop[:2], name="PatchU2")
        p5 = create_patch_unified(edges5, name="PatchU5")
    except Exception as e:
        errors.append("create_patch_unified raised on wrong edge count: %r" % e)
        return {"pass": False, "errors": errors, "checks": checks}
    for p, eds, want in ((p2, loop[:2], 2), (p5, edges5, 5)):
        if len(p.Poles) != 0:
            errors.append("%d-edge input left %d poles (want empty)"
                          % (want, len(p.Poles)))
        try:
            res = check_patch(p, eds)
        except Exception as e:
            errors.append("check_patch raised on %d-edge input: %r"
                          % (want, e))
            continue
        if not [n for (n, ok, d) in res if not ok]:
            errors.append("oracle passed on empty %d-edge input" % want)
    checks.append("wrong edge counts (2, 5) -> empty valid objects")
    return {"pass": not errors, "errors": errors, "checks": checks}


def test_unified_oracle_flags_pointed_boundary(doc):
    """A boundary pole of the 3-edge fill corrupted WITHOUT recompute must
    be flagged by the C2 boundary check -- check_patch never raises."""
    errors, checks = [], []
    from SilkWorkflowOps import create_patch_unified
    from SilkChecks import check_patch

    edges = _make_triangle_edges(doc)
    patch = create_patch_unified(edges, name="PatchU3")
    poles = list(patch.Poles)
    poles[1] = poles[1] + FreeCAD.Vector(0.5, 0, 0)  # p01 off edge0
    patch.Poles = poles  # no recompute -> oracle reads the stale boundary

    results = check_patch(patch, edges)
    failed = {n: d for (n, ok, d) in results if not ok}
    boundary_fails = [n for n in failed if "boundary" in n]
    if not boundary_fails:
        errors.append("corrupted boundary pole not flagged; failed: %s" % failed)
    else:
        checks.append("boundary check flagged: %s" % boundary_fails)
    return {"pass": not errors, "errors": errors, "checks": checks}


ALL_TESTS = [
    test_unified_patch_4_edges,
    test_unified_patch_pole_parity,
    test_unified_oracle_flags_c_boundary,
    test_unified_mutation_splits,
    test_unified_patch_3_edges,
    test_unified_pointed_pole_parity,
    test_unified_pointed_degenerate_column,
    test_unified_pointed_subgrid_machinery,
    test_unified_pointed_graceful_degradation,
    test_unified_oracle_flags_pointed_boundary,
]
