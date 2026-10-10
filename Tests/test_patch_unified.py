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

Display contract (#38 round 2): the six display/subdivision properties
exist and are editable, and the ShowSurface/ShowGrid/ShowSubgrids x
USplits/VSplits toggle matrix produces concrete, asserted face/edge
counts -- on the flat triangle fixture AND on the curved quarter-cone
fixture (built through sketch Placements, since bare sketches silently
drop z and would flatten any 3D control polygon).
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


# Ground-truth global 3D poles of the quarter-cone fixture (see
# _make_quarter_cone_edges): a quarter of the paraboloid of revolution
# z = 0.004*r^2, R = 50, rim z = 10. The profile edges (0, 2) are the
# EXACT degree-elevated quadratic Bezier of the parabola: uniform
# x-poles (0, 50/3, 100/3, 50) with z-poles (0, 0, 10/3, 10), written
# with 3-decimal roundings below.
_CONE_EDGE_POLES = [
    [(0, 0, 0), (16.667, 0, 0), (33.333, 0, 3.333), (50, 0, 10)],
    [(50, 0, 10), (50, 27.614, 10), (27.614, 50, 10), (0, 50, 10)],
    [(0, 50, 10), (0, 33.333, 3.333), (0, 16.667, 0), (0, 0, 0)],
]


def _make_quarter_cone_edges(doc):
    """Three 4-pole edges forming a closed loop: a quarter of the
    paraboloid of revolution z = 0.004*r^2 (R = 50, rim z = 10).

      edge0  profile parabola in the global XZ plane, origin -> rim --
             EXACT degree-elevated quadratic Bezier of z = 0.004*x^2:
             uniform x-poles (0, 50/3, 100/3, 50) with z-poles
             (0, 0, 10/3, 10), so z(t) = 10*t^2 = 0.004*x(t)^2
      edge1  rim quarter arc at z=10, rim -> rim (circular-arc cubic,
             k = 4/3*tan(pi/8)*50 ~ 27.614)
      edge2  the profile rotated 90 deg about Z, reversed, rim -> origin

    The degenerate point sits at the origin, shared by edges 0+2 --
    matching the pointed-fill corner layout (C1: (0,0) shared by 0+2,
    (0,3) by 0+1, (3,3) by 1+2). Loop closes exactly:
    e0.end == e1.start == (50,0,10), e1.end == e2.start == (0,50,10),
    e2.end == e0.start == (0,0,0). Coordinates are written with
    3-decimal roundings (3.333 ~ 10/3, residual ~1.25e-4 at t=0.5).

    Sketcher geometry lives in the sketch plane: addGeometry takes LOCAL
    x/y coordinates and silently drops z, so a bare XY sketch would
    flatten this 3D control polygon to z=0. Each sketch therefore
    carries a Placement lifting its local polygon into the intended
    global plane (local<->global mappings in the cfg comments).
    """
    from SilkWorkflowOps import create_edge
    cfg = {
        # global (X,0,Z) <-> local (X,Z); rotX(90): local (x,y,0) -> (x,0,y)
        "edge0": (FreeCAD.Placement(FreeCAD.Vector(0, 0, 0),
                                    FreeCAD.Rotation(FreeCAD.Vector(1, 0, 0), 90)),
                  [(0, 0), (16.667, 0), (33.333, 3.333), (50, 10)]),
        # global (X,Y,10) <-> local (X,Y); plane lifted by the position
        "edge1": (FreeCAD.Placement(FreeCAD.Vector(0, 0, 10),
                                    FreeCAD.Rotation()),
                  [(50, 0), (50, 27.614), (27.614, 50), (0, 50)]),
        # global (0,Y,Z) <-> local (-Z,Y); rotY(90): local (x,y,0) -> (0,y,-x)
        "edge2": (FreeCAD.Placement(FreeCAD.Vector(0, 0, 0),
                                    FreeCAD.Rotation(FreeCAD.Vector(0, 1, 0), 90)),
                  [(-10, 50), (-3.333, 33.333), (0, 16.667), (0, 0)]),
    }
    edges = []
    for i in range(3):
        pl, loc = cfg["edge%d" % i]
        sk = doc.addObject("Sketcher::SketchObject", "SketchQ%d" % i)
        sk.Placement = pl
        for j in range(3):
            sk.addGeometry(Part.LineSegment(
                FreeCAD.Vector(loc[j][0], loc[j][1], 0),
                FreeCAD.Vector(loc[j + 1][0], loc[j + 1][1], 0)))
        doc.recompute()
        edges.append(create_edge(sk, name="QEdge%d" % i))
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


# Concrete display-contract counts for a unified pointed patch with
# USplits=[0.3] / VSplits=[0.7] (4 subgrid cells). Face counts are pure
# topology (4 cell faces vs 1 base face). The ShowGrid=False edge counts
# are exactly the face-boundary edges (4 per face) because every grid-leg
# edge disappears with the toggle. The grid-ON totals (106 edges with
# subgrids shown, 24 with the base grid = face boundaries + the 20
# non-degenerate control-grid leg segments) depend on drawGrid's segment
# layout and are therefore only asserted as strictly larger than their
# grid-OFF counterparts.
def _assert_pointed_display_contract(doc, patch, edges, errors, checks,
                                     context):
    """Assert the full display toggle contract on a unified pointed
    patch (sets USplits=[0.3] / VSplits=[0.7] itself). check_patch must
    be green in every surface-visible state; the ShowSurface=False
    states are asserted to fail EXACTLY the display-driven checks (P4
    needs a face to mesh; the empty-all-off shape also fails
    structural) -- the surface is hidden, not missing."""
    from SilkChecks import check_patch

    def recompute():
        doc.recompute()

    def oracle_bad():
        return [n for (n, ok, d) in check_patch(patch, edges) if not ok]

    def expect(cond, msg):
        if not cond:
            errors.append("%s: %s" % (context, msg))

    # 1. splits set, base surface mode (ShowSubgrids default False)
    patch.ShowSubgrids = False
    patch.ShowSurface = True
    patch.ShowGrid = True
    patch.USplits = [0.3]
    patch.VSplits = [0.7]
    recompute()
    subgrids = getattr(patch.Proxy, "_subgrids", [])
    expect(len(subgrids) == 4 and all(len(sg) == 16 for sg in subgrids),
           "expected 4 subgrid cells of 16 poles, got %r"
           % [len(sg) for sg in subgrids])
    expect(len(patch.Shape.Faces) == 1,
           "ShowSubgrids=False: expected 1 base face, got %d"
           % len(patch.Shape.Faces))
    expect(not oracle_bad(), "oracle not green on base surface")

    # 2. ShowSubgrids=True -> one face per cell
    patch.ShowSubgrids = True
    recompute()
    expect(len(patch.Shape.Faces) == 4 == len(subgrids),
           "ShowSubgrids=True: expected 4 cell faces, got %d"
           % len(patch.Shape.Faces))
    expect(not oracle_bad(), "oracle not green with ShowSubgrids")
    edges_grid_on_subgrids = len(patch.Shape.Edges)

    # 3. ShowSurface=False -> zero faces in EITHER subgrids mode; the
    #    oracle's only failure is the display-driven P4.
    patch.ShowSurface = False
    recompute()
    expect(len(patch.Shape.Faces) == 0,
           "surface off + subgrids on: expected 0 faces, got %d"
           % len(patch.Shape.Faces))
    expect(oracle_bad() == ["P4_surface_valid"],
           "surface off + subgrids on: expected only the P4 failure, "
           "got %r" % oracle_bad())
    patch.ShowSubgrids = False
    recompute()
    expect(len(patch.Shape.Faces) == 0,
           "surface off + subgrids off: expected 0 faces, got %d"
           % len(patch.Shape.Faces))
    expect(oracle_bad() == ["P4_surface_valid"],
           "surface off + subgrids off: expected only the P4 failure, "
           "got %r" % oracle_bad())

    # 4. ShowGrid=False -> only face-boundary edges remain (no leg edges)
    patch.ShowSurface = True
    patch.ShowGrid = False
    patch.ShowSubgrids = False
    recompute()
    edges_base_grid_off = len(patch.Shape.Edges)
    expect(edges_base_grid_off == 4,
           "grid off + base: expected 4 face-boundary edges, got %d"
           % edges_base_grid_off)
    expect(not oracle_bad(), "oracle not green (grid off, base)")
    patch.ShowSubgrids = True
    recompute()
    expect(len(patch.Shape.Edges) == 4 * len(patch.Shape.Faces) == 16,
           "grid off + subgrids: expected 16 face-boundary edges "
           "(4 faces x 4), got %d" % len(patch.Shape.Edges))
    expect(not oracle_bad(), "oracle not green (grid off, subgrids)")
    expect(edges_grid_on_subgrids > len(patch.Shape.Edges),
           "grid on (%d edges) should exceed grid off (%d edges)"
           % (edges_grid_on_subgrids, len(patch.Shape.Edges)))

    # 5. everything off -> empty shape; oracle fails exactly
    #    structural + P4
    patch.ShowSurface = False
    recompute()
    expect(len(patch.Shape.Faces) == 0 and len(patch.Shape.Edges) == 0,
           "all toggles off: expected an empty shape, got %d faces / "
           "%d edges" % (len(patch.Shape.Faces), len(patch.Shape.Edges)))
    expect(sorted(oracle_bad()) == ["P4_surface_valid", "structural"],
           "all toggles off: expected exactly structural+P4 failures, "
           "got %r" % oracle_bad())

    # 6. restore toggles and clear the splits -> clean base state
    patch.ShowSurface = True
    patch.ShowGrid = True
    patch.ShowSubgrids = False
    patch.USplits = []
    patch.VSplits = []
    recompute()
    expect(not getattr(patch.Proxy, "_subgrids", []),
           "subgrids not cleared after clearing splits")
    expect(len(patch.Shape.Faces) == 1,
           "cleared splits: expected 1 base face, got %d"
           % len(patch.Shape.Faces))
    expect(len(patch.Shape.Edges) == 24,
           "cleared splits: expected 24 base edges (1 face + 20 grid-leg "
           "segments), got %d" % len(patch.Shape.Edges))
    expect(not oracle_bad(), "oracle not green after clearing splits")
    checks.append("%s display contract: 4/1/0 faces, 16/4 grid-off "
                  "edges, base 24 edges" % context)


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


def test_unified_pointed_display_contract(doc):
    """The 3-edge fill exposes the full display contract: the six
    display/subdivision properties exist and are editable (not
    read-only), and the ShowSurface/ShowGrid/ShowSubgrids x
    USplits/VSplits toggle matrix produces the concrete, asserted
    face/edge counts at every state, with check_patch green in every
    surface-visible state."""
    errors, checks = [], []
    from SilkWorkflowOps import create_patch_unified

    edges = _make_triangle_edges(doc)
    patch = create_patch_unified(edges, name="PatchU3")

    # 1. display/subdivision properties exist and are editable
    for prop in ("ShowSurface", "ShowGrid", "ShowSubgrids",
                 "AutoHideBlend", "USplits", "VSplits"):
        if not hasattr(patch, prop):
            errors.append("missing display/subdivision property %s" % prop)
        elif tuple(patch.getEditorMode(prop)):
            errors.append("%s is not editable: editor mode %r"
                          % (prop, list(patch.getEditorMode(prop))))
    checks.append("6 display/subdivision properties present and editable")

    # 2./3. the toggle matrix with concrete counts + oracle states
    _assert_pointed_display_contract(doc, patch, edges, errors, checks,
                                     "pointed triangle")
    return {"pass": not errors, "errors": errors, "checks": checks}


def test_unified_pointed_cone_build(doc):
    """Quarter-cone edges -> create_patch_unified -> pointed fill builds
    on the shared Patch type with the full oracle green (object_type,
    16 poles, C1-C3 incl. the degenerate column, P3/P4)."""
    errors, checks = [], []
    from SilkWorkflowOps import create_patch_unified
    from SilkChecks import check_patch

    edges = _make_quarter_cone_edges(doc)
    patch = create_patch_unified(edges, name="PatchCone")
    if patch is None or getattr(patch, "object_type", None) != "Patch":
        errors.append("create_patch_unified did not return a unified Patch")
        return {"pass": False, "errors": errors, "checks": checks}
    if len(list(patch.Edges)) != 3:
        errors.append("Edges link list != 3 entries")
    if len(patch.Poles) != 16:
        errors.append("expected 16 poles, got %d" % len(patch.Poles))
    checks.append("cone edges -> %s (%d poles, %d edges)"
                  % (patch.Name, len(patch.Poles), len(list(patch.Edges))))

    results = check_patch(patch, edges)
    _check_errors("check_patch cone", results, errors, checks)
    return {"pass": not errors, "errors": errors, "checks": checks}


def test_unified_pointed_cone_curved(doc):
    """The quarter-cone fixture is genuinely 3D and doubly curved --
    NOT the flattened sketch-plane case: every Edge pole sits on the
    intended global 3D coordinate (z != 0, tol 1e-6; a bare XY sketch
    silently drops z and deviates by up to 10), the 16 fill poles are
    not coplanar (max deviation from the corner plane > 2.0, empirical
    ~8.52), the
    profile edges trace the EXACT parabola z = 0.004*r^2 (Bezier
    midpoint at t=0.5 on the parabola within 5e-4; the degree-elevated
    quadratic has z-poles (0,0,10/3,10), so z(0.5)=2.5 -- a smoothstep
    fixture would give 5.0), and the rim arc bulges > 5.0 off its
    chord."""
    errors, checks = [], []
    from SilkWorkflowOps import create_patch_unified

    edges = _make_quarter_cone_edges(doc)

    # 1. edge poles on the intended 3D coordinates -- catches the silent
    #    sketch-plane flattening
    max_dev = 0.0
    for i, want in enumerate(_CONE_EDGE_POLES):
        for j, w in enumerate(want):
            d = (edges[i].Poles[j] - FreeCAD.Vector(*w)).Length
            max_dev = max(max_dev, d)
            if d > 1e-6:
                errors.append("edge%d pole %d deviates %.3e from %r"
                              % (i, j, d, w))
    checks.append("cone edge poles on intended 3D coordinates "
                  "(max dev %.2e, tol 1e-6)" % max_dev)

    patch = create_patch_unified(edges, name="PatchCone")

    # 2. the fill poles are not coplanar (doubly curved)
    poles = list(patch.Poles)
    n = (poles[3] - poles[0]).cross(poles[15] - poles[0])
    n.normalize()
    devs = [abs((q - poles[0]).dot(n)) for q in poles]
    if max(devs) <= 2.0:
        errors.append("fill poles (nearly) coplanar: max dev %.3f"
                      % max(devs))
    checks.append("fill poles not coplanar (max dev %.3f > 2.0)"
                  % max(devs))

    # 3. the profile edges trace the EXACT parabola z = 0.004*r^2: the
    #    Bezier midpoint (Bernstein at t=0.5) lies on the parabola.
    #    Exact value: (25, ., 2.5); the old smoothstep poles
    #    (0,0,10,10) gave z=5.0 and would fail this. Tolerance 5e-4
    #    covers the 3-decimal pole rounding (3.333 ~ 10/3 -> 1.25e-4).
    for ei in (0, 2):
        ep = [edges[ei].Poles[i] for i in range(4)]
        pmid = (ep[0] + 3 * ep[1] + 3 * ep[2] + ep[3]) * 0.125
        r2 = pmid.x ** 2 + pmid.y ** 2
        if abs(pmid.z - 0.004 * r2) > 5e-4:
            errors.append("edge%d midpoint off the parabola: "
                          "(%.4f, %.4f, %.6f) vs z=0.004*r^2=%.6f"
                          % (ei, pmid.x, pmid.y, pmid.z, 0.004 * r2))
    checks.append("profile midpoints on z=0.004*r^2 (tol 5e-4)")

    # 4. the rim arc bulges off its chord
    e1 = [edges[1].Poles[i] for i in range(4)]
    mid = (e1[0] + 3 * e1[1] + 3 * e1[2] + e1[3]) * 0.125
    bulge = (mid - (e1[0] + e1[3]) * 0.5).Length
    if bulge <= 5.0:
        errors.append("rim arc bulge %.3f <= 5.0" % bulge)
    checks.append("rim arc bulge %.3f > 5.0" % bulge)
    return {"pass": not errors, "errors": errors, "checks": checks}


def test_unified_pointed_cone_display(doc):
    """The subgrid machinery + display contract also holds on the curved
    quarter-cone fixture: 4 cells of 16 poles, the concrete face/edge
    toggle counts, oracle green, and a clean clear."""
    errors, checks = [], []
    from SilkWorkflowOps import create_patch_unified

    edges = _make_quarter_cone_edges(doc)
    patch = create_patch_unified(edges, name="PatchCone")
    _assert_pointed_display_contract(doc, patch, edges, errors, checks,
                                     "quarter cone")
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
    test_unified_pointed_display_contract,
    test_unified_pointed_cone_build,
    test_unified_pointed_cone_curved,
    test_unified_pointed_cone_display,
]
