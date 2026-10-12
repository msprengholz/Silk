"""
Unified Blend (ticket #39): ONE Blend object type, built via create_blend
on the shared edge of two patches and fed only patch subgrid cells.

Valence matrix (user requirement #39.5): pointed <-> pointed (two 3-edge
cone quarters sharing the degenerate profile) and pointed <-> quad (cone
+ hood panel sharing the rim arc), alongside the existing quad <-> quad
case (test_blend_stage.test_create_blend_ground_truth -- the migration
gate, unchanged).

The pointed <-> pointed case is the hard one: the seam touches the cone
apex on BOTH sides, so the corner list [Poles[0], Poles[3], Poles[15],
Poles[12]] carries the apex twice per patch (Poles[0] == Poles[12],
criterion 6). Naive corner matching double-counts the point and finds no
seam; detection must ignore same-patch-coincident corner pairs and pick
an adjacent cyclic matched pair.

Positive: create_blend -> unified object_type "Blend" with 24 poles;
check_blend B1 (C0 seam) / B2 (C1 tangent poles) / B3 (surface valid, no
self-intersection, coherent normal field) green (B4 skipped without a
stored reference); both patches' check_patch still green; both patches'
_HiddenSubgridIdxs hold exactly their seam-adjacent band cell (auto-hide
interop across the unified Patch machinery); no console errors.

Also: an explicit Edge input pins the seam geometrically (same result as
auto-detect); an unshared edge or a Blend fed as a patch refuses
gracefully (empty valid object + console error, never a crash --
"a Blend never eats a Blend"); a patch split mutation recomputes the
blend (poles change, oracle stays green, hidden sets converge -- no
ping-pong); a corrupted pole is flagged by the oracle without raising.
"""

import FreeCAD
import Part

from Tests.test_patch_unified import _make_quarter_cone_edges, _make_stray_edges
from Tests.test_blend_stage import _CaptureConsole

Vector = FreeCAD.Vector


# ---- fixtures -----------------------------------------------------------
# All fixtures use the sketch-Placement mechanism from
# _make_quarter_cone_edges (local x/y + per-sketch Placement), since
# addGeometry silently drops z. Geometry constants are shared with
# Tests.test_patch_unified -- nothing is duplicated silently.

# Ground-truth global 3D poles of the second cone quarter: q1 rotated +90
# deg about Z, in pointed loop order (edge0 point->rim, edge1 rim->rim,
# edge2 rim->point). q2.edge0 is the shared profile -- the exact reverse
# of q1.edge2 -- so the seam touches the apex on both sides.
_CONE2_EDGE_POLES = [
    [(0, 0, 0), (0, 16.667, 0), (0, 33.333, 13.333), (0, 50, 40)],
    [(0, 50, 40), (-27.614, 50, 40), (-50, 27.614, 40), (-50, 0, 40)],
    [(-50, 0, 40), (-33.333, 0, 13.333), (-16.667, 0, 0), (0, 0, 0)],
]

# Ground-truth global 3D poles of the quad "hood" panel, in quad loop
# order (edge0 = row U0, edge1 = col V3, edge2 = row U3, edge3 = col V0).
# quad.edge0 is the shared rim arc -- the SAME poles as q1.edge1 (clean
# seam, no degeneracy).
_HOOD_EDGE_POLES = [
    [(50, 0, 40), (50, 27.614, 40), (27.614, 50, 40), (0, 50, 40)],
    [(0, 50, 40), (0, 55, 50), (0, 60, 60), (0, 65, 70)],
    [(0, 65, 70), (15, 70, 70), (35, 70, 70), (50, 65, 70)],
    [(50, 65, 70), (50, 55, 60), (50, 25, 45), (50, 0, 40)],
]


def _sketch_edge(doc, key, cfg, prefix, i):
    """One 4-pole edge from a (Placement, local-xy points) config entry."""
    from SilkWorkflowOps import create_edge
    pl, loc = cfg[i]
    sk = doc.addObject("Sketcher::SketchObject", "%s%d" % (prefix, i))
    sk.Placement = pl
    for j in range(3):
        sk.addGeometry(Part.LineSegment(
            FreeCAD.Vector(loc[j][0], loc[j][1], 0),
            FreeCAD.Vector(loc[j + 1][0], loc[j + 1][1], 0)))
    doc.recompute()
    return create_edge(sk, name="%s%d" % (key, i))


def _make_cone_quarter2_edges(doc):
    """The second cone quarter (q1 rotated +90 deg about Z), pointed loop
    order e0 point->rim, e1 rim->rim, e2 rim->point. e0 is the shared
    profile (plane x=0)."""
    cfg = [
        # global (0,Y,Z) <-> local (Z,Y); rotY(-90): local (a,b,0) -> (0,b,a)
        (FreeCAD.Placement(FreeCAD.Vector(0, 0, 0),
                           FreeCAD.Rotation(FreeCAD.Vector(0, 1, 0), -90)),
         [(0, 0), (0, 16.667), (13.333, 33.333), (40, 50)]),
        # global (X,Y,40) <-> local (X,Y)
        (FreeCAD.Placement(FreeCAD.Vector(0, 0, 40), FreeCAD.Rotation()),
         [(0, 50), (-27.614, 50), (-50, 27.614), (-50, 0)]),
        # global (X,0,Z) <-> local (X,Z); rotX(90): local (a,b,0) -> (a,0,b)
        (FreeCAD.Placement(FreeCAD.Vector(0, 0, 0),
                           FreeCAD.Rotation(FreeCAD.Vector(1, 0, 0), 90)),
         [(-50, 40), (-33.333, 13.333), (-16.667, 0), (0, 0)]),
    ]
    return [_sketch_edge(doc, "Q2Edge", cfg, "SketchC2", i) for i in range(3)]


def _make_hood_edges(doc):
    """The quad hood panel, quad loop order e0 (shared rim arc, plane
    z=40) -> e1 (plane x=0) -> e2 (plane z=70) -> e3 (plane x=50)."""
    cfg = [
        # global (X,Y,40) <-> local (X,Y)
        (FreeCAD.Placement(FreeCAD.Vector(0, 0, 40), FreeCAD.Rotation()),
         [(50, 0), (50, 27.614), (27.614, 50), (0, 50)]),
        # global (0,Y,Z) <-> local (Z,Y); rotY(-90)
        (FreeCAD.Placement(FreeCAD.Vector(0, 0, 0),
                           FreeCAD.Rotation(FreeCAD.Vector(0, 1, 0), -90)),
         [(40, 50), (50, 55), (60, 60), (70, 65)]),
        # global (X,Y,70) <-> local (X,Y)
        (FreeCAD.Placement(FreeCAD.Vector(0, 0, 70), FreeCAD.Rotation()),
         [(0, 65), (15, 70), (35, 70), (50, 65)]),
        # global (50,Y,Z) <-> local (Z,Y); rotY(-90) lifted to x=50
        (FreeCAD.Placement(FreeCAD.Vector(50, 0, 0),
                           FreeCAD.Rotation(FreeCAD.Vector(0, 1, 0), -90)),
         [(70, 65), (60, 55), (45, 25), (40, 0)]),
    ]
    return [_sketch_edge(doc, "HEdge", cfg, "SketchH", i) for i in range(4)]


def _assert_3d_poles(edges, want_poles, label, errors, checks):
    """Every edge pole on its intended global 3D coordinate (1e-6) --
    catches sketch-plane flattening or wrong Placement math."""
    max_dev = 0.0
    for i, want in enumerate(want_poles):
        for j, w in enumerate(want):
            d = (edges[i].Poles[j] - Vector(*w)).Length
            max_dev = max(max_dev, d)
            if d > 1e-6:
                errors.append("%s edge%d pole %d deviates %.3e from %r"
                              % (label, i, j, d, w))
    checks.append("%s edge poles on intended 3D coordinates "
                  "(max dev %.2e)" % (label, max_dev))


def _build_cone_pair(doc):
    """Two unified pointed cone quarters sharing the profile seam.
    Returns (pa, pb, pa_edges, pb_edges); the shared seam is q1.edge2
    (== reverse of q2.edge0)."""
    from SilkWorkflowOps import create_patch
    qa = _make_quarter_cone_edges(doc)
    qb = _make_cone_quarter2_edges(doc)
    pa = create_patch(qa, name="ConeA")
    pb = create_patch(qb, name="ConeB")
    return pa, pb, qa, qb


def _build_cone_hood(doc):
    """Unified pointed cone + unified quad hood sharing the rim arc.
    Returns (cone, hood, cone_edges, hood_edges); the shared seam is
    cone.edge1 (== hood.edge0)."""
    from SilkWorkflowOps import create_patch
    qc = _make_quarter_cone_edges(doc)
    qh = _make_hood_edges(doc)
    cone = create_patch(qc, name="Cone")
    hood = create_patch(qh, name="Hood")
    return cone, hood, qc, qh


def _check_pair(context, blend, pa, pb, edges_a, edges_b, errors, checks):
    """The shared assertions: check_blend B1/B2/B3 green (B4 skipped),
    both patches' check_patch green, auto-hide hides exactly the band
    cell(s) -- with the expected seam (edge type + side) asserted."""
    from SilkChecks import check_blend, check_patch

    results = check_blend(blend, pa, pb)
    by = {n: (ok, d) for n, ok, d in results}
    for name in ("B1_c0_seams", "B2_c1_tangents", "B3_surface_valid",
                 "B4_pole_match"):
        ok, d = by.get(name, (False, "check missing"))
        checks.append("%s %s: %s (%s)" % (context, name,
                                          "ok" if ok else "FAIL", d))
        if not ok:
            errors.append("%s check_blend %s: %s" % (context, name, d))

    for p, eds, label in ((pa, edges_a, "patchA"), (pb, edges_b, "patchB")):
        bad = [(n, d) for n, ok, d in check_patch(p, eds) if not ok]
        if bad:
            errors.append("%s check_patch %s not green: %s"
                          % (context, label, bad))

    return results


def _check_auto_hide(context, specs, errors, checks):
    """specs: [(patch, edge_type, side, label)]; each patch must hide
    exactly its seam-adjacent band cell (single cell)."""
    from SilkMachinery import band_cells
    summary = []
    for p, etype, ss, label in specs:
        want = sorted(band_cells(p, etype, ss))
        got = list(getattr(p, "_HiddenSubgridIdxs", []) or [])
        summary.append("%s=%r" % (label, got))
        if len(want) != 1:
            errors.append("%s %s: expected a single-cell band, band_cells "
                          "returned %r" % (context, label, want))
        if got != want:
            errors.append("%s %s: _HiddenSubgridIdxs %r, want %r "
                          "(seam-adjacent band cell)"
                          % (context, label, got, want))
    checks.append("%s auto-hide: %s" % (context, ", ".join(summary)))


# ---- tests ---------------------------------------------------------------

def test_blend_pointed_pointed_cone_pair(doc):
    """3+3: two pointed cone quarters sharing the degenerate profile ->
    ONE unified Blend: 24 poles (not empty -- the naive corner detector
    finds no seam here), B1/B2/B3 green, both patches' check_patch green,
    auto-hide hides exactly the band cell on each side, no console
    errors."""
    errors, checks = [], []
    from SilkWorkflowOps import create_blend

    pa, pb, qa, qb = _build_cone_pair(doc)
    _assert_3d_poles(qb, _CONE2_EDGE_POLES, "cone2", errors, checks)

    with _CaptureConsole() as cap:
        blend = create_blend(pa, pb, name="BlendPP")

    if getattr(blend, "object_type", None) != "Blend":
        errors.append("create_blend did not produce the unified Blend "
                      "(object_type=%r)"
                      % getattr(blend, "object_type", None))
    poles = blend.Poles or []
    if len(poles) != 24:
        errors.append("expected 24 blend poles, got %d" % len(poles))
        return {"pass": False, "errors": errors, "checks": checks}
    checks.append("pointed<->pointed: %s built with 24 poles"
                  % blend.Name)

    _check_pair("3+3", blend, pa, pb, qa, qb, errors, checks)
    _check_auto_hide("3+3", [(pa, "U1", 1, "coneA"),
                             (pb, "U0", 0, "coneB")], errors, checks)
    errors += ["console error: %s" % e for e in cap.errors]
    return {"pass": not errors, "errors": errors, "checks": checks}


def test_blend_pointed_quad_cone_hood(doc):
    """3+4: pointed cone + unified quad hood sharing the rim arc ->
    ONE unified Blend: 24 poles, B1/B2/B3 green, both patch types stay
    oracle-green, auto-hide hides exactly the band cell on the cone AND
    on the quad, no console errors."""
    errors, checks = [], []
    from SilkWorkflowOps import create_blend

    cone, hood, qc, qh = _build_cone_hood(doc)
    _assert_3d_poles(qh, _HOOD_EDGE_POLES, "hood", errors, checks)
    # the seam must be the SAME geometry on both sides (same written
    # poles + same lifted placement -> exact match)
    dmax = max((a - b).Length
               for a, b in zip(list(qc[1].Poles), list(qh[0].Poles)))
    if dmax > 1e-6:
        errors.append("hood edge0 does not reproduce the cone rim arc "
                      "(max dev %.3e)" % dmax)

    with _CaptureConsole() as cap:
        blend = create_blend(cone, hood, name="BlendPQ")

    if getattr(blend, "object_type", None) != "Blend":
        errors.append("create_blend did not produce the unified Blend "
                      "(object_type=%r)"
                      % getattr(blend, "object_type", None))
    poles = blend.Poles or []
    if len(poles) != 24:
        errors.append("expected 24 blend poles, got %d" % len(poles))
        return {"pass": False, "errors": errors, "checks": checks}
    checks.append("pointed<->quad: %s built with 24 poles" % blend.Name)

    _check_pair("3+4", blend, cone, hood, qc, qh, errors, checks)
    _check_auto_hide("3+4", [(cone, "V1", 1, "cone"),
                             (hood, "U0", 0, "hood")], errors, checks)
    errors += ["console error: %s" % e for e in cap.errors]
    return {"pass": not errors, "errors": errors, "checks": checks}


def test_blend_explicit_edge_matches_auto_detect(doc):
    """An explicit shared Edge pins the seam geometrically: same result
    as auto-detect (pole parity), the Edge property links, oracle green,
    no console errors."""
    errors, checks = [], []
    from SilkWorkflowOps import create_blend
    from SilkChecks import check_blend

    pa, pb, qa, _ = _build_cone_pair(doc)
    shared_edge = qa[2]  # q1's profile edge = the shared seam
    with _CaptureConsole() as cap:
        b_auto = create_blend(pa, pb, name="BlendAuto")
        b_edge = create_blend(pa, pb, edge=shared_edge, name="BlendEdge")

    for b, label in ((b_auto, "auto"), (b_edge, "explicit")):
        if len(b.Poles or []) != 24:
            errors.append("%s-detect blend has %d poles, want 24"
                          % (label, len(b.Poles or [])))
        bad = [(n, d) for n, ok, d in check_blend(b, pa, pb) if not ok]
        if bad:
            errors.append("%s-detect blend not oracle-green: %s"
                          % (label, bad))
    if b_edge.Edge != shared_edge:
        errors.append("explicit Edge not linked on the blend "
                      "(Edge=%r)" % getattr(b_edge, "Edge", None))

    if len(b_auto.Poles or []) == 24 and len(b_edge.Poles or []) == 24:
        dev = max((p - q).Length
                  for p, q in zip(list(b_edge.Poles), list(b_auto.Poles)))
        if dev > 1e-9:
            errors.append("explicit-edge seam differs from auto-detect by "
                          "%.3e (want identical)" % dev)
        checks.append("explicit edge == auto-detect (max pole dev %.2e)" % dev)
    errors += ["console error: %s" % e for e in cap.errors]
    return {"pass": not errors, "errors": errors, "checks": checks}


def test_blend_rejects_unshared_edge(doc):
    """An edge that is not a shared boundary of BOTH patches -> empty
    valid object + console error, no crash; the oracle flags it and never
    raises."""
    errors, checks = [], []
    from SilkWorkflowOps import create_blend
    from SilkChecks import check_blend

    pa, pb, _, _ = _build_cone_pair(doc)
    stray = _make_stray_edges(doc, 1)[0]
    try:
        with _CaptureConsole() as cap:
            blend = create_blend(pa, pb, edge=stray, name="BlendBad")
    except Exception as e:
        errors.append("create_blend raised on an unshared edge: %r" % e)
        return {"pass": False, "errors": errors, "checks": checks}

    if len(blend.Poles or []) != 0:
        errors.append("unshared edge left %d poles (want empty)"
                      % len(blend.Poles or []))
    if blend.Shape is not None and not blend.Shape.isNull() \
            and blend.Shape.Faces:
        errors.append("unshared edge left a face in the Shape (want empty)")
    if not cap.errors:
        errors.append("unshared edge produced no console error")
    checks.append("unshared edge -> empty valid object + console error")
    try:
        results = check_blend(blend, pa, pb)
    except Exception as e:
        errors.append("check_blend raised on a refused blend: %r" % e)
        return {"pass": False, "errors": errors, "checks": checks}
    if all(ok for _, ok, _ in results):
        errors.append("oracle passed on the refused (empty) blend")
    checks.append("oracle flags the refused blend: %s"
                  % [n for n, ok, _ in results if not ok])
    return {"pass": not errors, "errors": errors, "checks": checks}


def test_blend_refuses_blend_as_patch(doc):
    """A Blend never eats a Blend (criterion 4): feeding a blend object
    as PatchA refuses gracefully -- empty valid object + console error,
    no crash, oracle flags it."""
    errors, checks = [], []
    from SilkWorkflowOps import create_blend
    from SilkChecks import check_blend

    pa, pb, _, _ = _build_cone_pair(doc)
    try:
        with _CaptureConsole() as cap:
            good = create_blend(pa, pb, name="BlendGood")
            bad = create_blend(good, pa, name="BlendCannibal")
    except Exception as e:
        errors.append("create_blend raised on a Blend-as-patch input: %r" % e)
        return {"pass": False, "errors": errors, "checks": checks}

    if len(good.Poles or []) != 24:
        errors.append("the first blend should be intact, got %d poles"
                      % len(good.Poles or []))
    if len(bad.Poles or []) != 0:
        errors.append("blend-as-patch left %d poles (want empty)"
                      % len(bad.Poles or []))
    if bad.Shape is not None and not bad.Shape.isNull() and bad.Shape.Faces:
        errors.append("blend-as-patch left a face in the Shape (want empty)")
    if not cap.errors:
        errors.append("blend-as-patch produced no console error")
    checks.append("blend-as-patch -> empty valid object + console error")
    try:
        results = check_blend(bad, good, pa)
    except Exception as e:
        errors.append("check_blend raised on a blend-as-patch input: %r" % e)
        return {"pass": False, "errors": errors, "checks": checks}
    if all(ok for _, ok, _ in results):
        errors.append("oracle passed on the refused blend-as-patch object")
    checks.append("oracle flags the refused object: %s"
                  % [n for n, ok, _ in results if not ok])
    return {"pass": not errors, "errors": errors, "checks": checks}


def test_blend_pointed_live_update(doc):
    """Mutation/live-update: change a cone's splits -> the blend itself
    recomputes (poles change but stay oracle-green: B1/B2/B3), the
    auto-hide set converges (no ping-pong over repeated recomputes) and
    names the CURRENT band, and both patches stay green."""
    errors, checks = [], []
    from SilkWorkflowOps import create_blend
    from SilkChecks import check_blend, check_patch

    pa, pb, qa, qb = _build_cone_pair(doc)
    with _CaptureConsole() as cap:
        blend = create_blend(pa, pb, name="BlendLive")
    before = [Vector(p) for p in (blend.Poles or [])]
    hidden_before = list(getattr(pa, "_HiddenSubgridIdxs", []) or [])
    if len(before) != 24:
        errors.append("baseline blend has %d poles, want 24" % len(before))
        return {"pass": False, "errors": errors, "checks": checks}

    # A split on cone A PERPENDICULAR to the seam beyond the blend's own
    # 0.9 narrows the band cell -> the blend must recompute off the
    # patch's updated subgrids. #64: this value is now the band's ACTUAL
    # width (the blend reads it) rather than being joined by a re-asserted
    # default, so the band stays the SAME cell at a new width -- the
    # hidden-cell liveness is asserted against band_cells below, not
    # against a cell index that no longer has to move.
    pa.VSplits = [0.95]
    doc.recompute()
    doc.recompute()

    after = [Vector(p) for p in (blend.Poles or [])]
    if len(after) != 24:
        errors.append("blend has %d poles after the mutation, want 24"
                      % len(after))
    else:
        dev = max((p - q).Length for p, q in zip(before, after))
        if dev <= 1e-6:
            errors.append("blend poles did not change after the split "
                          "mutation (dev %.3e) -- blend went stale" % dev)
        checks.append("blend recomputed after split mutation "
                      "(max pole change %.3f)" % dev)

    bad = [(n, d) for n, ok, d in check_blend(blend, pa, pb) if not ok]
    if bad:
        errors.append("blend oracle not green after the mutation: %s" % bad)
    else:
        checks.append("blend oracle green after the mutation")
    for p, eds, label in ((pa, qa, "coneA"), (pb, qb, "coneB")):
        pbad = [(n, d) for n, ok, d in check_patch(p, eds) if not ok]
        if pbad:
            errors.append("check_patch %s not green after the mutation: %s"
                          % (label, pbad))

    hidden1 = list(getattr(pa, "_HiddenSubgridIdxs", []) or [])
    doc.recompute()
    doc.recompute()
    hidden2 = list(getattr(pa, "_HiddenSubgridIdxs", []) or [])
    if hidden1 != hidden2:
        errors.append("hidden-cell set ping-pongs: %r vs %r"
                      % (hidden1, hidden2))
    # The auto-hide set must equal the CURRENT band, re-derived from the
    # patch's splits (#33). Comparing against the live band_cells is what
    # makes this a staleness check: a set recorded before the width moved
    # would no longer name the cell the blend now covers. Before #64 the
    # band cell index happened to change as a side effect of the blend
    # re-asserting its default; #64 makes the index stable and the WIDTH
    # the moving part, so the index comparison no longer proves anything
    # — the band_cells equality does.
    from SilkMachinery import band_cells, patch_side
    e_a, ss_a = patch_side(pa, pb, 0.01)
    live_band = band_cells(pa, e_a, ss_a)
    if hidden1 != live_band:
        errors.append("hidden-cell set %r does not name the current band "
                      "%r (seam %s side %d)" % (hidden1, live_band, e_a, ss_a))
    checks.append("hidden set %r == the live band_cells %r for seam %s "
                  "side %d, converged over repeated recomputes (was %r at "
                  "the default width)"
                  % (hidden1, live_band, e_a, ss_a, hidden_before))
    errors += ["console error: %s" % e for e in cap.errors]
    return {"pass": not errors, "errors": errors, "checks": checks}


def test_blend_oracle_flags_corrupted_pole(doc):
    """Negative: corrupt a blend pole WITHOUT recompute -> check_blend
    flags the break (B1 seam pole here) and never raises."""
    errors, checks = [], []
    from SilkWorkflowOps import create_blend
    from SilkChecks import check_blend

    pa, pb, _, _ = _build_cone_pair(doc)
    blend = create_blend(pa, pb, name="BlendNeg")
    poles = list(blend.Poles or [])
    if len(poles) != 24:
        errors.append("expected 24 poles, got %d" % len(poles))
        return {"pass": False, "errors": errors, "checks": checks}
    poles[0] = poles[0] + Vector(0.5, 0, 0)   # row 0 C0 seam pole
    blend.Poles = poles                        # no recompute

    try:
        results = check_blend(blend, pa, pb)
    except Exception as e:
        errors.append("check_blend raised on a corrupted pole: %r" % e)
        return {"pass": False, "errors": errors, "checks": checks}
    failed = [n for n, ok, _ in results if not ok]
    if not any(n.startswith("B1") or n.startswith("B4") for n in failed):
        errors.append("corrupted pole not flagged; failed: %s" % failed)
    checks.append("corrupted pole flagged: %s" % failed)
    return {"pass": not errors, "errors": errors, "checks": checks}


ALL_TESTS = [
    test_blend_pointed_pointed_cone_pair,
    test_blend_pointed_quad_cone_hood,
    test_blend_explicit_edge_matches_auto_detect,
    test_blend_rejects_unshared_edge,
    test_blend_refuses_blend_as_patch,
    test_blend_pointed_live_update,
    test_blend_oracle_flags_corrupted_pole,
]
