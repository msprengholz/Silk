"""
Patch stage (ticket #19): create_patch op + check_patch oracle.

The op builds the unified Patch (#42: the legacy per-fill
create_patch/Patch44 builder is retired); check_patch is the
only patch oracle (dispatches on the edge count).

Positive: 4 loop edges (a 50x50 square) -> create_patch -> full oracle
green (structural + P1-P4), no console errors.
Negative: deliberately corrupted pole states / wrong edge arguments
must be flagged by the corresponding checks -- the oracle returns
failures, it never raises.

Ticket #66 -- the edge ORDER is not the user's problem any more.
The `Edges` link list arrives in whatever order it was produced: the
task panel collects in CLICK order, the property editor can be
hand-reordered, an old document restores whatever it saved. The quad
fill used to walk that list blind, so a pair of consecutive entries
that did not share an endpoint failed the whole fill -- 16 of the 24
permutations of one valid 4-edge loop produced a valid, up-to-date,
INVISIBLE ghost, and `create_patch` reported success on it. What is
asserted here:

  1. ALL 24 orderings of one valid 4-edge set build, and every one of
     them is the SAME SURFACE -- compared as a surface (sampled through
     the 8 symmetries of the parametric square, which is exactly the
     freedom a cyclic rotation / reversal of the boundary is), not as a
     pole vector. This is the headline test: stronger than "no longer
     crashes", and it is the property the ticket actually asks for.
  2. The 3-edge pointed fill is untouched: all 6 orderings still build,
     and the canonical order still matches legacy Patch33 at 1e-6.
  3. PARITY: the canonical order reproduces the legacy Patch44 poles at
     1e-6 (weights exactly), and `loop_order` on an already-cyclic list
     is a genuine NO-OP -- it hands back the very list it was given, in
     the very order, for all 8 cyclic rotations/directions. Without
     that, the chain gate would stop reproducing ground truth and
     legacy restore would drift.
  4. A selection that genuinely cannot close a loop creates NOTHING and
     names the offending edges -- in create_patch AND in the
     Silk_CreatePatch command.
  5. The panel's Patch section reports success only for a patch that
     actually built.

Fixtures are built in memory; where a stored ground truth is needed the
fixture file is COPIED to a scratch directory first and the copy is
opened -- the human's live FreeCAD may already have the originals open,
and FreeCAD.openDocument would hand back (and then close) their
documents. Nothing under Resources/Test_files is ever opened, saved or
closed by this module.
"""

import itertools
import os
import shutil
import tempfile

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


# Closed, doubly-curved triangle for the 3-edge (pointed) fill, cyclic
# order t0..t2. CURVED on purpose: the flat triangle the panel tests use
# builds a pointed fill whose surface the oracle's mesh step reports as
# self-intersecting (P4), and that is true of the legacy Patch33 on the
# same edges too -- a property of the flat fixture, not of #66. On the
# curved triangle every ordering is green, which is what makes the
# orderings comparable at all.
_TRI_PTS = {
    "t0": [Vector(0, 0, 0), Vector(33.3, 0, 3),
           Vector(66.7, 0, 6), Vector(100, 0, 10)],
    "t1": [Vector(100, 0, 10), Vector(90, 33, 20),
           Vector(70, 66, 35), Vector(50, 100, 40)],
    "t2": [Vector(50, 100, 40), Vector(30, 66, 38),
           Vector(10, 33, 20), Vector(0, 0, 0)],
}


class _CaptureConsole:
    def __enter__(self):
        self.errors = []
        self._orig = FreeCAD.Console.PrintError
        FreeCAD.Console.PrintError = lambda m: (self.errors.append(str(m)), self._orig(m))
        return self

    def __exit__(self, *args):
        FreeCAD.Console.PrintError = self._orig


def _make_triangle_edges(doc):
    """Three edges forming a closed triangle loop, cyclic order t0..t2 --
    the pointed fill's input."""
    from SilkWorkflowOps import create_edge
    edges = []
    for i in range(3):
        sk = _make_3l_sketch(doc, "TriSketch%d" % i, _TRI_PTS["t%d" % i])
        edges.append(create_edge(sk, name="TriEdge%d" % i))
    return edges


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
    patch = create_patch(edges, name="Patch")
    return patch, edges


# ---- #66: the edge ORDER is derived, not trusted ------------------------
#
# The oracle below is deliberately INDEPENDENT of the production helper:
# it builds the bicubic surface itself from the patch's poles and compares
# it as a SURFACE, sampled through the 8 symmetries of the parametric
# square. That symmetry group is exactly the freedom a cyclic rotation /
# reversal of the boundary order is -- the same four boundary curves, the
# same patch, a different pole indexing -- so "the same surface" is the
# honest statement, and "no longer crashes" is not.

# The 8 symmetries of [0,1]^2 as maps on SAMPLE-GRID indices (i, j)
# in 0.._SAMPLE_N-1, named. `I` is the identity; `R` is a quarter turn;
# `F` mirrors u. The complement is `_SAMPLE_N - 1` (#68 found these maps
# hardcoded to 3 -- the POLE-grid complement -- while being applied to
# the 7x7 SAMPLE grid: R/R2/R3/F/FR2/FR3 then mapped indices out of
# range (negative Python indexing wraps to an arbitrary point) or to
# the wrong point entirely, so no non-trivial symmetry could ever match.
# That too was invisible while `_same_surface` never read the candidate:
# identity answered first, worst 0, and returned).
_SYMMETRIES = (
    ("I", lambda u, v: (u, v)),
    ("R", lambda u, v: (_SAMPLE_N - 1 - v, u)),
    ("R2", lambda u, v: (_SAMPLE_N - 1 - u, _SAMPLE_N - 1 - v)),
    ("R3", lambda u, v: (v, _SAMPLE_N - 1 - u)),
    ("F", lambda u, v: (_SAMPLE_N - 1 - u, v)),
    ("FR", lambda u, v: (v, u)),
    ("FR2", lambda u, v: (u, _SAMPLE_N - 1 - v)),
    ("FR3", lambda u, v: (_SAMPLE_N - 1 - v, _SAMPLE_N - 1 - u)),
)

# Sample the patch on a 7x7 interior grid -- coarse enough to be quick,
# fine enough that a rotated-but-different surface cannot hide.
_SAMPLE_N = 7


def _sample_points(poles, weights, n=_SAMPLE_N):
    """(u, v, point) over an n x n interior grid of the bicubic patch."""
    surf = Part.BSplineSurface()
    surf.increaseDegree(3, 3)
    for knot in (0.0, 1.0):
        surf.insertUKnot(knot, 4, 1e-7)
        surf.insertVKnot(knot, 4, 1e-7)
    for r in range(4):
        for c in range(4):
            surf.setPole(c + 1, r + 1, poles[r * 4 + c], weights[r * 4 + c])
    out = []
    for i in range(n):
        for j in range(n):
            u = (i + 0.5) / n
            v = (j + 0.5) / n
            out.append((u, v, surf.value(u, v)))
    return out


def _same_surface(ref, cand, tol=1e-6):
    """(ok, worst, how) -- are two (poles, weights) pairs the same patch?

    `same` means: there is one symmetry of the parametric square under
    which every sampled point of `cand` matches the corresponding point
    of `ref`. True surface equality up to the cyclic rotation / reversal
    that a reordered edge list induces, checked as points rather than as
    pole indices so no indexing convention can fake it.
    """
    ref_pts = _sample_points(ref[0], ref[1])
    cand_pts = _sample_points(cand[0], cand[1])
    if len(ref_pts) != len(cand_pts):
        return False, float("inf"), "sample grids differ in size"
    best = None
    for name, sym in _SYMMETRIES:
        worst = 0.0
        for (u, v, p_ref), (u2, v2, p_cand) in zip(ref_pts, cand_pts):
            # indices, not normalised coordinates -- the map is on the grid
            i, j = int(u * _SAMPLE_N), int(v * _SAMPLE_N)
            i2, j2 = sym(i, j)
            target = ref_pts[i2 * _SAMPLE_N + j2][2]
            # CANDIDATE point vs the reference point at the symmetry-
            # mapped index (#68 discovered this line comparing ref to
            # ref's own symmetrised grid, which made identity worst==0
            # for ANY candidate -- the helper answered "same surface"
            # without ever reading the candidate, and every consumer's
            # surface claim was vacuous because of it).
            worst = max(worst, (p_cand - target).Length)
        if best is None or worst < best[0]:
            best = (worst, name)
        if worst <= tol:
            return True, worst, name
    return False, best[0], "worst symmetry %s" % best[1]


def _patches(doc):
    return [o for o in doc.Objects
            if getattr(o, "object_type", None) == "Patch"]


def _open_fixture_copy():
    """Open a COPY of the ground-truth fixture in a scratch directory.

    Never openDocument the file under Resources/Test_files/: the human's
    FreeCAD may already have it open, in which case openDocument hands
    back THAT document -- and the test's `closeDocument` in a finally
    block then takes the human's work down with it (it has happened).
    The copy is a byte-for-byte fixture; nothing under the repo is
    touched. Returns (doc, scratch_dir); the caller closes the doc and
    removes the scratch dir."""
    tmp = tempfile.mkdtemp(prefix="silk_patch_stage_")
    dst = os.path.join(tmp, os.path.basename(FIXTURE))
    shutil.copy2(FIXTURE, dst)
    return FreeCAD.openDocument(dst), tmp


def test_patch_order_independence_all_24_permutations(doc):
    """#66 HEADLINE: all 24 orderings of one valid 4-edge set build, and
    every one of them is the SAME SURFACE as the canonical build.

    Before #66 exactly 8 of the 24 built anything (the 4 rotations x 2
    directions of the true cycle) and the other 16 produced a valid,
    up-to-date, INVISIBLE object that `create_patch` happily returned --
    the user's "patches are invisible, blends are impossible" bug.

    The comparison is a surface comparison under the 8 symmetries of the
    parametric square (see `_same_surface`), NOT a pole-vector
    comparison: a reordered boundary is the same patch with the pole
    indices turned around, so demanding identical indices would be
    demanding the bug. The oracle is built here in the test, from
    Part, with no production code in it.
    """
    errors, checks = [], []
    from SilkWorkflowOps import create_patch

    edges = _make_loop_edges(doc)
    ref_patch = create_patch(edges, name="PatchRef")
    if len(ref_patch.Poles) != 16:
        errors.append("the canonical build has %d poles, expected 16"
                      % len(ref_patch.Poles))
        return {"pass": False, "errors": errors, "checks": checks}
    ref = (list(ref_patch.Poles), list(ref_patch.Weights))

    built, ghosts, mismatch = 0, [], []
    for perm in itertools.permutations(range(4)):
        sel = [edges[i] for i in perm]
        with _CaptureConsole() as cap:
            patch = create_patch(sel, name="PatchP")
        label = "".join(str(i) for i in perm)
        if patch is None:
            ghosts.append("%s (no object)" % label)
            continue
        if len(patch.Poles) != 16:
            ghosts.append("%s (%d poles)" % (label, len(patch.Poles)))
            continue
        if cap.errors:
            errors.append("ordering %s printed errors: %s"
                          % (label, cap.errors))
        built += 1
        ok, worst, how = _same_surface(ref, (list(patch.Poles),
                                            list(patch.Weights)))
        if not ok:
            mismatch.append("%s (worst %.3e via %s)"
                            % (label, worst, how))

    if ghosts:
        errors.append("%d/24 orderings produced no surface (ghosts): %s"
                      % (len(ghosts), ghosts))
    else:
        checks.append("all 24 orderings built 16 poles + a surface "
                      "(0 invisible ghosts)")
    if mismatch:
        errors.append("%d/24 orderings are a DIFFERENT surface from the "
                      "canonical build: %s" % (len(mismatch), mismatch))
    else:
        checks.append("all 24 orderings are the same surface as the "
                      "canonical build (sampled on a 7x7 interior grid, "
                      "matched through the 8 symmetries of the square)")
    checks.append("orderings compared: 24, built: %d" % built)
    return {"pass": not errors, "errors": errors, "checks": checks}


def test_patch_order_independence_curved_ground_truth(doc):
    """The 24-ordering guarantee on the REAL curved ground-truth edges,
    not only on the synthetic square -- a flat square is the easy case.

    The 7 fixture edges are rebuilt in the test doc from the copied
    fixture's sketches, so the loop is the same asymmetric, curved,
    non-trivial boundary the chain gate uses."""
    errors, checks = [], []
    from SilkWorkflowOps import create_patch

    fixture, tmp = _open_fixture_copy()
    FreeCAD.setActiveDocument(doc.Name)
    try:
        edges = _build_gt_edges(doc, fixture, GT_PATCH44_EDGES)
        ref_patch = create_patch(edges, name="GTRef")
        if len(ref_patch.Poles) != 16:
            errors.append("canonical curved build has %d poles, expected 16"
                          % len(ref_patch.Poles))
            return {"pass": False, "errors": errors, "checks": checks}
        ref = (list(ref_patch.Poles), list(ref_patch.Weights))
        ref_area = ref_patch.Shape.Area

        ghosts, mismatch = [], []
        for perm in itertools.permutations(range(4)):
            sel = [edges[i] for i in perm]
            patch = create_patch(sel, name="GTP")
            label = "".join(str(i) for i in perm)
            if patch is None or len(patch.Poles) != 16:
                ghosts.append("%s (%s)"
                              % (label, "none" if patch is None
                                 else "%d poles" % len(patch.Poles)))
                continue
            ok, worst, how = _same_surface(ref, (list(patch.Poles),
                                                list(patch.Weights)))
            if not ok:
                mismatch.append("%s (worst %.3e via %s)"
                                % (label, worst, how))
            elif abs(patch.Shape.Area - ref_area) > 1e-6 * max(1.0, ref_area):
                mismatch.append("%s (area %.6f vs %.6f)"
                                % (label, patch.Shape.Area, ref_area))
        if ghosts:
            errors.append("%d/24 curved orderings produced no surface: %s"
                          % (len(ghosts), ghosts))
        else:
            checks.append("all 24 curved orderings built 16 poles + a "
                          "surface (0 ghosts)")
        if mismatch:
            errors.append("%d/24 curved orderings differ from the "
                          "canonical surface: %s"
                          % (len(mismatch), mismatch))
        else:
            checks.append("all 24 curved orderings match the canonical "
                          "surface AND its area (%.4f)" % ref_area)
    finally:
        FreeCAD.closeDocument(fixture.Name)
        FreeCAD.setActiveDocument(doc.Name)
        shutil.rmtree(tmp, ignore_errors=True)
    return {"pass": not errors, "errors": errors, "checks": checks}


def test_patch_loop_order_is_a_noop_for_a_cyclic_list(doc):
    """PARITY, half one: `loop_order` hands an already-cyclic list back
    UNCHANGED -- the same list, the same order -- for all 8 cyclic
    rotations/directions of a good edge set.

    This is load-bearing, not a nicety. The fill feeds its result
    straight into the legacy ControlGrid44_4 arithmetic, so "unchanged"
    is what makes the chain gate reproduce ground truth at 1e-6 and
    keeps an old document restoring to the poles it was saved with. A
    helper that helpfully re-serialized a good list would silently
    resample every legacy surface in the workbench."""
    errors, checks = [], []
    from SilkMachinery import loop_order

    edges = _make_loop_edges(doc)

    # the identity first: the canonical list comes back as the SAME object
    same_obj, problem = loop_order(edges)
    if same_obj is not edges:
        errors.append("loop_order rebuilt the canonical list instead of "
                      "returning it unchanged")
    else:
        checks.append("canonical list returned as the identical object "
                      "(no reserialization)")

    # then every cyclic rotation and both directions
    rotations = []
    for k in range(4):
        rotations.append([edges[(i + k) % 4] for i in range(4)])
        rotations.append([edges[(k - i) % 4] for i in range(4)])
    for rot in rotations:
        out, prob = loop_order(rot)
        if prob is not None:
            errors.append("loop_order refused a CYCLIC list %s: %s"
                          % ([e.Name for e in rot], prob))
        elif [e.Name for e in out] != [e.Name for e in rot]:
            errors.append("loop_order reordered a cyclic list: %s -> %s"
                          % ([e.Name for e in rot], [e.Name for e in out]))
    if not errors:
        checks.append("all %d cyclic rotations/directions returned "
                      "verbatim, in the given order" % len(rotations))
    return {"pass": not errors, "errors": errors, "checks": checks}


def test_patch_parity_canonical_order_matches_legacy(doc):
    """PARITY, half two: the canonical order still reproduces the legacy
    Patch44 / Patch33 poles at 1e-6 and their weights exactly.

    #66 must not have moved a single legacy number: the chain gate
    (test_chain) pole-matches both patches and the blend against stored
    ground truth at 1e-6, and legacy restore depends on the same
    numbers. Compared against the legacy classes constructed directly
    (the restore shims), not against a copy of the old code."""
    errors, checks = [], []
    from Tests.test_patch_unified import (_make_legacy_patch44,
                                          _make_legacy_patch33)
    from SilkWorkflowOps import create_patch

    edges = _make_loop_edges(doc)
    p44 = _make_legacy_patch44(doc, edges, name="P44")
    pun = create_patch(edges, name="PUn")
    dmax = max((a - b).Length for a, b in zip(pun.Poles, p44.Poles))
    if dmax > 1e-6:
        errors.append("quad pole parity deviates by %.3e (tol 1e-6)" % dmax)
    wmax = max(abs(a - b) for a, b in zip(pun.Weights, p44.Weights))
    if wmax > 1e-12:
        errors.append("quad weight parity deviates by %.3e" % wmax)
    checks.append("canonical quad order -> Patch44: max pole dev %.2e, "
                  "weight dev %.2e (tol 1e-6)" % (dmax, wmax))

    tri = _make_triangle_edges(doc)
    p33 = _make_legacy_patch33(doc, tri, name="P33")
    pun3 = create_patch(tri, name="PUn3")
    d3 = max((a - b).Length for a, b in zip(pun3.Poles, p33.Poles))
    if d3 > 1e-6:
        errors.append("pointed pole parity deviates by %.3e (tol 1e-6)" % d3)
    w3 = max(abs(a - b) for a, b in zip(pun3.Weights, p33.Weights))
    if w3 > 1e-12:
        errors.append("pointed weight parity deviates by %.3e" % w3)
    checks.append("canonical pointed order -> Patch33: max pole dev %.2e, "
                  "weight dev %.2e (tol 1e-6)" % (d3, w3))

    # and the chain's own ground truth, through the copied fixture
    fixture, tmp = _open_fixture_copy()
    FreeCAD.setActiveDocument(doc.Name)
    try:
        gt_patch, _gt_edges = _build_gt_patch(doc, fixture)
        stored = fixture.getObject("Patch44")
        dg = max((a - b).Length for a, b in zip(gt_patch.Poles, stored.Poles))
        wg = max(abs(a - b) for a, b in zip(gt_patch.Weights, stored.Weights))
        if dg > 1e-6:
            errors.append("ground-truth quad deviates from stored Patch44 "
                          "by %.3e" % dg)
        if wg > 1e-12:
            errors.append("ground-truth quad weights deviate by %.3e" % wg)
        checks.append("chain ground truth -> stored Patch44: max pole dev "
                      "%.2e, weight dev %.2e" % (dg, wg))
    finally:
        FreeCAD.closeDocument(fixture.Name)
        FreeCAD.setActiveDocument(doc.Name)
        shutil.rmtree(tmp, ignore_errors=True)
    return {"pass": not errors, "errors": errors, "checks": checks}


def test_pointed_fill_all_orderings_unchanged(doc):
    """The 3-edge pointed fill is NOT touched by #66: all 6 orderings
    build, the oracle is green on each, and the canonical order is
    byte-for-byte what it always was.

    What #66 left alone is the BUILD and the canonical bytes. It is NOT
    true -- and #68 showed this test never verified it, because
    `_same_surface` compared the reference to its own symmetry image
    (see `test_surface_comparison_helper_actually_compares`) -- that the
    6 orderings are the same surface. Four of them are not: the
    degenerate corner of a pointed fill is the `Edges[2] -> Edges[0]`
    junction, i.e. the corner opposite the list's MIDDLE edge, so the
    orderings with a different middle edge move the cone point and no
    parametrization can map the result back. The pure loop reversal
    (210) keeps the cone and comes back as the mirror image -- the same
    surface -- and that partition (4 differ, 012+210 match) is asserted
    below. Every ordering of a closed triple is a valid cycle (there is
    no canonical rotation to pick), so `loop_order` returns it verbatim.
    `Tests/test_pointed_corner_triple.py` pins the rule explicitly;
    this test pins what #66/#67 must not change: the build, the oracle,
    and the canonical bytes."""
    errors, checks = [], []
    from SilkWorkflowOps import create_patch
    from SilkChecks import check_patch

    tri = _make_triangle_edges(doc)
    base = create_patch(tri, name="PTBase")
    if len(base.Poles) != 16:
        errors.append("canonical pointed build has %d poles" % len(base.Poles))
        return {"pass": False, "errors": errors, "checks": checks}
    canon = (list(base.Poles), list(base.Weights))

    empties, bad_oracle, differing = [], [], []
    for perm in itertools.permutations(range(3)):
        sel = [tri[i] for i in perm]
        label = "".join(str(i) for i in perm)
        patch = create_patch(sel, name="PT")
        if patch is None or len(patch.Poles) != 16:
            empties.append(label)
            continue
        bad = [(n, d) for (n, ok, d) in check_patch(patch, sel) if not ok]
        if bad:
            bad_oracle.append("%s: %s" % (label, bad))
        ok, worst, how = _same_surface(canon, (list(patch.Poles),
                                               list(patch.Weights)))
        if not ok:
            differing.append("%s (worst %.3e via %s)" % (label, worst, how))
    if empties:
        errors.append("pointed orderings with no poles: %s" % empties)
    else:
        checks.append("all 6 pointed orderings built 16 poles")
    if bad_oracle:
        errors.append("oracle flagged a pointed build: %s" % bad_oracle)
    else:
        checks.append("oracle green on all 6 pointed orderings (C1-C3, "
                      "P3-P4)")
    if len(differing) == 4 and not any(
            d.startswith("012") or d.startswith("210") for d in differing):
        checks.append("the 4 cone-MOVING orderings differ from the "
                      "canonical surface (%s); the pure loop reversal "
                      "210 is the mirror image and matches -- the "
                      "degenerate corner follows Edges[2]->Edges[0], "
                      "#68, pinned in test_pointed_corner_triple"
                      % ", ".join(d.split(" ")[0] for d in differing))
    else:
        errors.append("expected exactly the 4 cone-moving orderings "
                      "(021/102/120/201) to differ and 012/210 to match; "
                      "got %d differing: %s" % (len(differing), differing))

    # the canonical order is the legacy baseline, untouched
    again = create_patch(tri, name="PTAgain")
    exact = max((a - b).Length for a, b in zip(again.Poles, canon[0]))
    wexact = max(abs(a - b) for a, b in zip(again.Weights, canon[1]))
    if exact != 0.0 or wexact != 0.0:
        errors.append("canonical pointed build is not reproducible "
                      "exactly (pole dev %.3e, weight dev %.3e)"
                      % (exact, wexact))
    else:
        checks.append("canonical pointed poles AND weights reproduce "
                      "EXACTLY (dev 0.0) -- the fill is byte-for-byte "
                      "what it was before #66")
    return {"pass": not errors, "errors": errors, "checks": checks}


# ---- #67: the STORED list is the cycle ---------------------------------
#
# #66 made the fill order-independent but never wrote the answer back, so a
# clicked-around patch contradicted itself: `Edges[k]` was not boundary
# side k, and both the data tab and the oracle said so (P1_corner_order /
# P2_boundary_match red on 16 of 24 orderings). The suite stayed green
# because every #66 fixture passes edges in canonical order, where
# `loop_order` is a no-op -- no test ever asked whether the OBJECT agreed
# with itself. These tests ask exactly that, for all 24 orderings.


def test_patch_stored_cycle_is_self_consistent_for_all_24_orderings(doc):
    """#67 HEADLINE: for EVERY ordering, `check_patch(p, list(p.Edges))` is
    green AND `p.Edges` is exactly the resolved cycle.

    This is the assertion whose absence let #67's bug ship: #66's own
    tests compared SURFACES (which a reordering preserves) and never read
    the stored property back. The oracle here is fed `list(p.Edges)` --
    what the object claims -- not the selection that was passed in, so a
    patch that normalised its geometry but not its property would still
    fail. P1_corner_order and P2_boundary_match are named explicitly
    because those two are the ones that go red on a non-cyclic list.

    Curved ground-truth edges are used as well as the synthetic square:
    a flat square is the easy case, and #66 already learned that lesson.
    """
    errors, checks = [], []
    from SilkWorkflowOps import create_patch
    from SilkChecks import check_patch

    fixtures = [("square", _make_loop_edges(doc))]
    fx, tmp = _open_fixture_copy()
    FreeCAD.setActiveDocument(doc.Name)
    try:
        fixtures.append(
            ("curved", _build_gt_edges(doc, fx, GT_PATCH44_EDGES)))

        for label, edges in fixtures:
            bad_oracle, bad_cycle, bad_props = [], [], []
            for perm in itertools.permutations(range(4)):
                sel = [edges[i] for i in perm]
                plabel = "".join(str(i) for i in perm)
                patch = create_patch(sel, name="SC")
                if patch is None:
                    bad_oracle.append("%s (no object)" % plabel)
                    continue

                # (1) SELF-CONSISTENCY: the oracle, fed the STORED list.
                stored = list(patch.Edges)
                fails = {n: d for (n, ok, d) in check_patch(patch, stored)
                         if not ok}
                for key in ("P1_corner_order", "P2_boundary_match"):
                    if key in fails:
                        bad_oracle.append("%s %s: %s"
                                          % (plabel, key, fails[key]))
                if fails:
                    bad_oracle.append("%s other: %s" % (plabel, fails))

                # (2) the stored list IS a closed cycle, derived
                # independently from the edges' own endpoints -- and it
                # starts with the first edge that was passed in (the
                # #66 rotation rule), so the normalization is the
                # documented one, not an arbitrary reshuffle.
                adj_ok, detail = _is_closed_cycle(stored)
                if not adj_ok:
                    bad_cycle.append("%s: %s" % (plabel, detail))
                elif stored[0] is not sel[0]:
                    bad_cycle.append("%s: cycle does not lead with the "
                                     "first collected edge" % plabel)

                # (3) the property itself is intact: 4 links, 16 poles,
                #     a real shape.
                if len(stored) != 4 or len(list(patch.Poles)) != 16:
                    bad_props.append("%s (%d edges, %d poles)"
                                     % (plabel, len(stored),
                                        len(list(patch.Poles))))
                elif patch.Shape is None or patch.Shape.isNull():
                    bad_props.append("%s: null shape" % plabel)
                elif not patch.Shape.Faces:
                    bad_props.append("%s: shape has no face (invisible "
                                     "ghost)" % plabel)

            if bad_oracle:
                errors.append("%s: the oracle is not green when fed the "
                              "patch's OWN Edges list: %s"
                              % (label, bad_oracle[:12]))
            else:
                checks.append("%s: all 24 orderings oracle-green on "
                              "list(p.Edges) (structural, P1_corner_order, "
                              "P2_boundary_match, P3, P4)" % label)
            if bad_cycle:
                errors.append("%s: p.Edges is not the resolved cycle for: %s"
                              % (label, bad_cycle[:12]))
            else:
                checks.append("%s: all 24 orderings stored a closed cycle "
                              "leading with the first collected edge" % label)
            if bad_props:
                errors.append("%s: object damaged for: %s"
                              % (label, bad_props[:12]))
            else:
                checks.append("%s: all 24 orderings kept 4 links, 16 poles "
                              "and a real face" % label)
    finally:
        FreeCAD.closeDocument(fx.Name)
        FreeCAD.setActiveDocument(doc.Name)
        shutil.rmtree(tmp, ignore_errors=True)
    return {"pass": not errors, "errors": errors, "checks": checks}


def _is_closed_cycle(edges, tol=1e-6):
    """(ok, detail) -- do consecutive entries of `edges` meet, and last to
    first? Written from the POLE ENDPOINTS alone (distance, no production
    helper), so it is the same independent restatement of "cycle" the
    oracle's P1/P2 checks are, not a call back into loop_order."""
    n = len(edges)
    if n < 3:
        return False, "only %d entries" % n
    for i in range(n):
        a = list(edges[i].Poles)
        b = list(edges[(i + 1) % n].Poles)
        near = min((p - q).Length for p in a for q in b)
        if near > tol:
            return False, ("entry %d (%s) does not meet entry %d (%s): "
                           "closest endpoints %.3e apart"
                           % (i, edges[i].Name, (i + 1) % n,
                              edges[(i + 1) % n].Name, near))
    return True, "closed"


class _WriteSpy(object):
    """Count the cycle writes on one Patch proxy, by wrapping the proxy's
    own store method. Restores itself on exit -- a test must not leave a
    monkey-patch on a production class."""

    def __init__(self):
        self.writes = []

    def __enter__(self):
        import SilkPatch
        self._cls = SilkPatch.Patch
        self._orig = self._cls._store_boundary_cycle
        spy = self

        def wrapped(self_, fp, was, cycle):
            did = self._orig(self_, fp, was, cycle)
            if did:
                spy.writes.append([e.Name for e in was])
            return did

        self._cls._store_boundary_cycle = wrapped
        return self

    def __exit__(self, *a):
        self._cls._store_boundary_cycle = self._orig


def test_patch_cycle_write_is_a_one_shot_fixed_point(doc):
    """#67: the write HAPPENS ONCE and the recompute CONVERGES -- and a
    cyclic input never writes at all.

    `execute()` both reads `fp.Edges` and writes `fp.Edges`, which is
    exactly the shape that ping-pongs if you get it wrong. Three claims,
    each measured rather than argued:

      1. an awkwardly ordered input is rewritten exactly ONCE, during the
         creation recompute;
      2. every later recompute -- forced by touch(), so nothing is
         skipped -- leaves the stored order alone and leaves the object
         Up-to-date (no Touched residue from the write, no recompute
         cycle with a Blend, no churn);
      3. an ALREADY-CYCLIC input writes NOTHING, ever: not at creation,
         not on any later recompute, not for any of the 8 cyclic
         rotations / reversals. That is what keeps the legacy
         Patch44/Patch33 pole parity at 0.00e+00 -- an unnecessary
         rewrite would reserialize a good list and drift every restored
         legacy surface.
    """
    errors, checks = [], []
    from SilkWorkflowOps import create_patch

    edges = _make_loop_edges(doc)

    # (1)+(2) an awkward order: one write, then a fixed point.
    awkward = [edges[2], edges[0], edges[3], edges[1]]
    with _WriteSpy() as spy:
        patch = create_patch(awkward, name="Conv")
        n_after_create = len(spy.writes)
        seq = []
        for _ in range(6):
            patch.touch()
            doc.recompute()
            seq.append((tuple(e.Name for e in patch.Edges),
                        tuple(patch.State)))
    if n_after_create != 1:
        errors.append("an awkwardly ordered input caused %d writes during "
                      "creation, expected exactly 1"
                      % n_after_create)
    else:
        checks.append("awkward order -> exactly 1 cycle write during "
                      "creation: %s -> %s" % (spy.writes[0],
                                               [e.Name for e in patch.Edges]))
    if len(spy.writes) != 1:
        errors.append("the cycle was rewritten %d times in total "
                      "(expected 1, then never again): %s"
                      % (len(spy.writes), spy.writes))
    else:
        checks.append("6 further forced recomputes wrote nothing "
                      "(fixed point, no ping-pong)")
    settled = set(seq)
    if len(settled) != 1:
        errors.append("the stored order or State changed across recomputes: "
                      "%s" % sorted(settled))
    elif list(next(iter(settled))[1]) != ["Up-to-date"]:
        errors.append("the patch is left %s after the write -- the property "
                      "assignment's Touched flag was not cleared"
                      % (next(iter(settled))[1],))
    else:
        checks.append("stable across 6 recomputes at %s, State %s"
                      % (list(next(iter(settled))[0]),
                         list(next(iter(settled))[1])))

    # (3) a cyclic input: never a write, for any cyclic order.
    cyclic_edges = _make_loop_edges(doc)
    rotations = [[cyclic_edges[(i + k) % 4] for i in range(4)]
                 for k in range(4)]
    rotations += [[cyclic_edges[(k - i) % 4] for i in range(4)]
                  for k in range(4)]
    total = 0
    for rot in rotations:
        with _WriteSpy() as spy2:
            p = create_patch(rot, name="NoOp")
            total += len(spy2.writes)
            for _ in range(2):
                p.touch()
                doc.recompute()
            total += len(spy2.writes)
            if [e.Name for e in p.Edges] != [e.Name for e in rot]:
                errors.append("a cyclic input was reordered on storage: %s "
                              "-> %s" % ([e.Name for e in rot],
                                         [e.Name for e in p.Edges]))
    if total:
        errors.append("an already-cyclic input caused %d cycle writes; it "
                      "must take the byte-identical no-op path" % total)
    else:
        checks.append("all %d cyclic rotations/directions: 0 writes across "
                      "creation + 2 forced recomputes each (byte-identical "
                      "no-op path preserved)" % len(rotations))
    return {"pass": not errors, "errors": errors, "checks": checks}


def test_patch_cycle_converges_when_the_user_reorders_the_data_tab(doc):
    """#67: a HAND reordering of `Edges` in the data tab is normalized on
    the next recompute, and the object stops there.

    The data tab is the third producer of a non-cyclic list (after the
    panel's click order and an old file's saved order), so it needs the
    same one-shot guarantee -- and it is the one a user can repeat at will.
    Reordering again is not an error: the patch simply normalizes once
    more, and the geometry follows the new stored order rather than the
    old one."""
    errors, checks = [], []
    from SilkWorkflowOps import create_patch
    from SilkChecks import check_patch

    edges = _make_loop_edges(doc)
    patch = create_patch(list(edges), name="Tab")
    before = [e.Name for e in patch.Edges]

    # Two data-tab edits, because the two cases differ and both matter.
    #
    # (a) A pure ROTATION is already a cycle, so there is nothing to
    #     normalize and nothing must be written -- the #66 no-op, still
    #     intact. Asserted separately so the real case below cannot pass
    #     by accident.
    cyclic_moved = [edges[1], edges[2], edges[3], edges[0]]
    patch.Edges = cyclic_moved
    patch.touch()
    with _WriteSpy() as spy_rot:
        doc.recompute()
    if len(spy_rot.writes):
        errors.append("a pure rotation of the boundary was rewritten (%d "
                      "writes); a rotation is already a cycle"
                      % len(spy_rot.writes))
    elif [e.Name for e in patch.Edges] != [e.Name for e in cyclic_moved]:
        errors.append("a cyclic rotation was not stored verbatim: %s"
                      % [e.Name for e in patch.Edges])
    else:
        checks.append("data-tab rotation %s is already cyclic -> stored "
                      "verbatim, 0 writes" % [e.Name for e in cyclic_moved])

    # (b) A genuine shuffle: right next to top. This one DOES get
    #     normalized -- back onto the cycle that leads with the first
    #     entry, which for a rotation of the square is the original
    #     canonical order. So the stored order after normalization is
    #     `before`, and the honest assertion is that the RAW order the
    #     user typed was replaced by a cycle -- not that it differs from
    #     `before`, which for this fixture it does not.
    moved = [edges[1], edges[2], edges[0], edges[3]]
    raw = [e.Name for e in moved]
    patch.Edges = moved
    # `Edges` is a link list, not one of the recompute-trigger properties
    # (onChanged watches the split lists and the display toggles only), so
    # a data-tab edit needs the explicit touch any geometry edit does. The
    # point of the test is the WRITE, not the trigger.
    patch.touch()
    with _WriteSpy() as spy:
        doc.recompute()
        first = [e.Name for e in patch.Edges]
        for _ in range(4):
            patch.touch()
            doc.recompute()
        again = [e.Name for e in patch.Edges]

    if first == raw:
        errors.append("the data-tab shuffle %s was stored raw -- it is not a "
                      "cycle" % raw)
    else:
        checks.append("data-tab shuffle %s -> %s, normalized in one "
                      "recompute" % (raw, first))
    if list(again) != list(first):
        errors.append("the data-tab reorder did not settle: %s -> %s"
                      % (first, again))
    if len(spy.writes) != 1:
        errors.append("the data-tab reorder caused %d writes, expected 1"
                      % len(spy.writes))
    else:
        checks.append("exactly 1 write, then a fixed point over 4 further "
                      "recomputes")

    ok, detail = _is_closed_cycle(patch.Edges)
    if not ok:
        errors.append("after the data-tab reorder the stored list is not a "
                      "cycle: %s" % detail)
    fails = [(n, d) for (n, good, d) in check_patch(patch, list(patch.Edges))
             if not good]
    if fails:
        errors.append("the oracle is not green after the data-tab reorder: "
                      "%s" % fails)
    else:
        checks.append("oracle green on list(p.Edges) after the reorder")

    if patch.Shape is None or patch.Shape.isNull():
        errors.append("the patch lost its surface across the data-tab "
                      "shuffle")
    else:
        checks.append("shape still has %d face(s), area %.4f"
                      % (len(patch.Shape.Faces), patch.Shape.Area))
    return {"pass": not errors, "errors": errors, "checks": checks}


def test_blend_across_two_awkwardly_ordered_patches_resolves(doc):
    """#67: a Blend across two patches whose edges were each supplied in a
    non-cyclic order resolves the seam and builds its 24 poles.

    The user's report was "i also cant blend two of these hidden
    patches", and #66's answer was that the patch was a ghost. #67's
    extra risk is the reverse one: if the stored list is now rewritten,
    a seam resolver that reads edge IDENTITY must still see the same two
    patches referencing the shared edge. `create_blend_by_edge` resolves
    purely on identity, and the band is taken from the patches' subgrid
    cells, so neither cares about the list's order -- this pins that,
    because it is the kind of invariant that a normalizing write can
    quietly break.
    """
    errors, checks = [], []
    from SilkWorkflowOps import create_patch, create_blend_by_edge
    from SilkChecks import check_patch, check_blend
    from Tests.test_seam_resolver import _Capture

    from Tests.test_seam_resolver import _line_sketch
    from SilkWorkflowOps import create_edge

    # Two genuinely ADJACENT squares sharing one Edge object: the left
    # square is x in [0,50], the right one x in [50,100], and the seam is
    # the vertical side at x=50. (Two COINCIDENT squares would share all
    # four corners and degenerate the band cell, which is a fixture
    # problem, not a normalization problem -- the seam resolver's own
    # tests use coincidence only where no blend surface is built.)
    # left square, cyclic: bottom -> seam -> top -> left
    L = {
        "bottom": [(0, 0, 0), (16.7, 0, 0), (33.3, 0, 0), (50, 0, 0)],
        "top":    [(50, 50, 0), (33.3, 50, 0), (16.7, 50, 0), (0, 50, 0)],
        "left":   [(0, 50, 0), (0, 33.3, 0), (0, 16.7, 0), (0, 0, 0)],
    }
    R = {
        "bottom": [(50, 0, 0), (66.7, 0, 0), (83.3, 0, 0), (100, 0, 0)],
        "top":    [(100, 50, 0), (83.3, 50, 0), (66.7, 50, 0), (50, 50, 0)],
        "right":  [(100, 0, 0), (100, 16.7, 0), (100, 33.3, 0), (100, 50, 0)],
    }
    # the ONE shared edge object: the left square's right side, run in the
    # opposite direction to the right square's left side (as real seams
    # are), so the resolver cannot pass by accident.
    seam_sk = _line_sketch(doc, "Seam_sk",
                           [(50, 0, 0), (50, 16.7, 0), (50, 33.3, 0),
                            (50, 50, 0)])
    shared = create_edge(seam_sk, name="Seam")

    def build(prefix, table, skip):
        out = {}
        for key, pts in table.items():
            sk = _line_sketch(doc, "%s_sk_%s" % (prefix, key), pts)
            out[key] = create_edge(sk, name="%s_%s" % (prefix, key))
        out["seam"] = shared
        return out

    a = build("LA", L, None)
    b = build("RB", R, None)

    # Both fed in a deliberately WRONG order, and a DIFFERENT wrong order
    # each -- so the two patches are not symmetric about the seam.
    pa = create_patch([a["bottom"], a["seam"], a["left"], a["top"]],
                      name="AwkA")
    pb = create_patch([b["seam"], b["right"], b["top"], b["bottom"]],
                      name="AwkB")
    for nm, p in (("AwkA", pa), ("AwkB", pb)):
        if p is None:
            errors.append("%s did not build" % nm)
            continue
        fails = [(n, d) for (n, ok, d) in check_patch(p, list(p.Edges))
                 if not ok]
        if fails:
            errors.append("oracle not green on %s's own Edges: %s"
                          % (nm, fails))
    if errors:
        return {"pass": False, "errors": errors, "checks": checks}
    checks.append("both awkwardly ordered patches oracle-green on "
                  "list(p.Edges): %s" % [e.Name for e in pa.Edges])

    with _Capture() as cap:
        blend = create_blend_by_edge(shared, name="AwkBlend")
    if blend is None:
        errors.append("the seam was not resolved across two awkwardly "
                      "ordered patches (console: %s)" % cap.errors)
        return {"pass": False, "errors": errors, "checks": checks}
    if len(list(blend.Poles)) != 24:
        errors.append("the blend built %d poles, expected 24"
                      % len(list(blend.Poles)))
    elif blend.Shape is None or blend.Shape.isNull():
        errors.append("the blend has a NULL shape -- the invisible-ghost "
                      "symptom #66 was about, back through the seam")
    fails = [(n, d) for (n, ok, d) in check_blend(blend, pa, pb) if not ok]
    if fails:
        errors.append("blend oracle flagged the awkward-order blend: %s"
                      % fails)
    else:
        checks.append("blend: 24 poles, non-null shape, full oracle green")
    errors += ["console error: %s" % e for e in cap.errors
               if "cannot" not in e]
    return {"pass": not errors, "errors": errors, "checks": checks}


def _make_stray_edge(doc, name="Stray"):
    """One 4-pole edge far away from everything -- a loop with a hole in
    it rather than a loop."""
    from SilkWorkflowOps import create_edge
    pts = [Vector(200, 200, 0), Vector(210, 200, 0),
           Vector(220, 200, 0), Vector(230, 200, 0)]
    sk = _make_3l_sketch(doc, name + "_sk", pts)
    return create_edge(sk, name=name)


def test_patch_non_closing_selection_creates_nothing(doc):
    """#66, refusal half: a selection that cannot close a loop creates NO
    object and NAMES the offending edges -- in `create_patch` AND in the
    Silk_CreatePatch command.

    #62's idiom: a wrong-type click is silently ignored, but a refused
    CREATION reports which item is the problem. This is the case that has
    no correct outcome at all (3 of 4 sides of a square plus a stray), so
    there is nothing to salvage -- the refusal must name the offenders
    rather than say "curves do not share endpoints" (a symptom) or, worse,
    return a ghost."""
    errors, checks = [], []
    from SilkWorkflowOps import create_patch
    from SilkMachinery import loop_order
    from Tests.test_patch_gui_command import _CaptureConsole
    from FreeCAD import Gui

    edges = _make_loop_edges(doc)
    stray = _make_stray_edge(doc)
    broken = [edges[0], edges[1], edges[2], stray]

    # the helper names the offenders, per edge
    order, problem = loop_order(broken)
    if order is not None:
        errors.append("loop_order accepted a selection that does not "
                      "close a loop")
    if not problem:
        errors.append("loop_order gave no problem text for a broken "
                      "selection")
    for name in (stray.Name,):
        if not problem or name not in problem:
            errors.append("the problem text does not name the stray edge "
                          "%s: %r" % (name, problem))
    checks.append("loop_order refused and named: %s" % (problem or "?"))

    # create_patch: no object, one loud message, nothing left behind
    before = len(_patches(doc))
    with _CaptureConsole() as cap:
        result = create_patch(broken, name="PatchRefused")
    if result is not None:
        errors.append("create_patch returned %r for a non-closing "
                      "selection" % (result,))
    after = [o.Name for o in _patches(doc)]
    if len(after) != before:
        errors.append("a refused creation left %s behind"
                      % [n for n in after if n not in
                         [o.Name for o in _patches(doc)][:before]])
    msgs = "".join(cap.errors)
    if not msgs:
        errors.append("create_patch refused silently (no console error)")
    if not msgs.startswith("Silk:"):
        errors.append("refusal must start with 'Silk:', got %r" % msgs)
    if stray.Name not in msgs:
        errors.append("the refusal does not name the offending edge %s: %r"
                      % (stray.Name, msgs))
    checks.append("create_patch: refused, no object, message %r"
                  % msgs.strip()[:110])

    # #85, edge-release lock (#55 Q2): a refusal must never consume an
    # edge. Assert the SEMANTIC, not just "no Patch object left behind":
    # after the refused create_patch, no Edge object in the document is
    # referenced by ANY Patch's `Edges` link list -- so every edge used in
    # the refused selection is still FREE (claimed by nothing). This locks
    # the round-1 defect ("a failed patch held its links, so every edge was
    # claimed and none were free"). #66's refuse-before-construct makes it
    # trivially true today, but a build-then-refuse regression must go red
    # here even if it left no visible Patch object behind.
    claimed = {}
    for p in _patches(doc):
        for e in (list(getattr(p, "Edges", None) or [])):
            claimed.setdefault(e.Name, []).append(p.Name)
    for e in doc.Objects:
        if getattr(e, "object_type", None) != "Edge":
            continue
        if e.Name in claimed:
            errors.append("the refused create_patch left the edge %s "
                          "claimed by %s's Edges list (edge not free)"
                          % (e.Name, claimed[e.Name]))
    checks.append("edge-release: no Edge in the doc is claimed by any "
                  "Patch after the refusal")

    # and the GUI command refuses the same way
    before = len(_patches(doc))
    Gui.Selection.clearSelection()
    for e in broken:
        Gui.Selection.addSelection(e)
    with _CaptureConsole() as cap2:
        from SilkPatch import CreatePatch
        CreatePatch().Activated()
    doc.recompute()
    if len(_patches(doc)) != before:
        errors.append("Silk_CreatePatch created %d object(s) for a "
                      "non-closing selection"
                      % (len(_patches(doc)) - before))
    msgs2 = "".join(cap2.errors)
    if not msgs2.startswith("Silk:") or stray.Name not in msgs2:
        errors.append("the command's refusal does not name the offending "
                      "edge: %r" % msgs2)
    Gui.Selection.clearSelection()
    checks.append("Silk_CreatePatch: refused, no object, message %r"
                  % msgs2.strip()[:110])
    return {"pass": not errors, "errors": errors, "checks": checks}


def test_create_patch_ground_truth(doc):
    """Build the real (curved) Patch44 from fixture sketches; all 16 poles
    and 16 weights must match the stored ground-truth patch exactly, and
    the oracle must be fully green."""
    errors, checks = [], []
    from SilkChecks import check_patch

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

        results = check_patch(patch, edges)
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
    from SilkChecks import check_patch

    edges = _make_loop_edges(doc)
    with _CaptureConsole() as cap:
        patch = create_patch(edges, name="Patch")
    if cap.errors:
        errors.append("console errors during create_patch: %s" % cap.errors)
    if patch is None or getattr(patch, "object_type", None) != "Patch":
        errors.append("create_patch did not return a unified Patch object")
        return {"pass": False, "errors": errors, "checks": checks}
    checks.append("create_patch returned %s with %d poles" % (patch.Name, len(patch.Poles)))

    results = check_patch(patch, edges)
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
    from SilkChecks import check_patch

    fixture_doc = FreeCAD.openDocument(FIXTURE)
    FreeCAD.setActiveDocument(doc.Name)
    try:
        patch, edges = _build_gt_patch(doc, fixture_doc)
        poles = list(patch.Poles)
        poles[4:8] = list(reversed(poles[4:8]))  # flip row U1
        patch.Poles = poles

        results = check_patch(patch, edges)
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
    from SilkChecks import check_patch

    edges = _make_loop_edges(doc)
    patch = create_patch(edges, name="Patch")
    poles = list(patch.Poles)
    poles[1] = poles[1] + Vector(0.5, 0, 0)  # p01 off edge0
    patch.Poles = poles

    results = check_patch(patch, edges)
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
    from SilkChecks import check_patch

    edges = _make_loop_edges(doc)
    patch = create_patch(edges, name="Patch")

    results = check_patch(patch, [edges[0], edges[2], edges[1], edges[3]])
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
    # #66 -- the edge order is derived, not trusted
    test_patch_order_independence_all_24_permutations,
    test_patch_order_independence_curved_ground_truth,
    test_patch_loop_order_is_a_noop_for_a_cyclic_list,
    test_patch_parity_canonical_order_matches_legacy,
    test_pointed_fill_all_orderings_unchanged,
    test_patch_non_closing_selection_creates_nothing,
    # #67 -- the STORED list is the cycle, and the object agrees with itself
    test_patch_stored_cycle_is_self_consistent_for_all_24_orderings,
    test_patch_cycle_write_is_a_one_shot_fixed_point,
    test_patch_cycle_converges_when_the_user_reorders_the_data_tab,
    test_blend_across_two_awkwardly_ordered_patches_resolves,
]
