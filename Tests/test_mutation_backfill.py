"""
Tests/test_mutation_backfill.py — mutation backfill (issue #43).

Demonstrates every mutation operator from Tests.mutation_ops.py on the
current stable objects: a single Edge (via SilkWorkflowOps.create_edge)
and the existing 2-patch Patch44/BlendStrip pipeline (the corner_pair
fixture from Tests.corner_model), including a shared-edge mutation that
makes both patches + the blend rebuild and revalidate with the seam still
clean. Also confirms the ground-truth chain recomputes stably at 1e-6.

Coverage:
  Edge                    : move_boundary_pole (1), reverse_edge (3),
                            toggle_display (4), recompute_convergence (5)
  Patch44/Blend pipeline  : move_boundary_pole (1) on the shared edge,
                            change_splits (2), reverse_edge (3),
                            toggle_display (4), recompute_convergence (5)
  Chain gate              : recompute_convergence keeps the stored
                            ground-truth blend at 1e-6 (#43 op 5)

Everything uses the ops layer + oracles only; no private internals.
"""

import functools

import FreeCAD

from Tests import corner_model
from Tests import mutation_ops as mo

Vector = FreeCAD.Vector

CHAIN_GT_TOL = 1e-6


# ---- builders ----------------------------------------------------------

def _build_single_edge(doc):
    """One 2N edge (two node sketches) via SilkWorkflowOps.create_edge."""
    from SilkWorkflowOps import create_edge
    (name, skey, p1, p2, ekey) = corner_model.EDGES[0]  # E_b1
    sk_a = corner_model.node_sketch(doc, "NS_a", skey, p1)
    sk_b = corner_model.node_sketch(doc, "NS_b", ekey, p2)
    edge = create_edge([sk_a, sk_b], name="Edge")
    return {"doc": doc, "edges": {"E": edge}}


def _build_corner_pair_model(doc):
    """The existing 2-patch + blend (B12) probe via Tests.corner_model."""
    m = corner_model.build_corner_pair(doc)
    m["doc"] = doc
    m["patch_edges"] = {
        "Patch44": [m["edges"]["E_b1"], m["edges"]["E_s12"],
                    m["edges"]["E_s13"], m["edges"]["E_l1"]],
        "Patch001": [m["edges"]["E_b2"], m["edges"]["E_r2"],
                     m["edges"]["E_s24"], m["edges"]["E_s12"]],
    }
    return m


# ---- oracles -----------------------------------------------------------

def _oracle_edge(model):
    from SilkChecks import check_edge
    return check_edge(model["edges"]["E"])


def _oracle_corner_pair(model):
    """Full correctness check for the pipeline: both patches + the blend."""
    from SilkChecks import check_patch44, check_blend
    res = []
    for name, p in model["patches"].items():
        res += [("patch:%s:%s" % (name, n), ok, d)
                for n, ok, d in check_patch44(p, model["patch_edges"][name])]
    res += [("blend:%s" % n, ok, d)
            for n, ok, d in check_blend(
                model["strip"], model["patches"]["Patch44"],
                model["patches"]["Patch001"])]
    return res


# ---- Edge (ops 1, 3, 4, 5) ---------------------------------------------

def test_mutation_edge_move_boundary_pole(doc):
    errors, checks = mo.run_mutations(
        doc, lambda: _build_single_edge(doc), _oracle_edge,
        [functools.partial(mo.move_boundary_pole, edge="E", pole_index=1,
                           delta=Vector(4.0, 3.0, 2.0))])
    return {"pass": not errors, "errors": errors, "checks": checks}


def test_mutation_edge_reverse(doc):
    errors, checks = mo.run_mutations(
        doc, lambda: _build_single_edge(doc), _oracle_edge,
        [functools.partial(mo.reverse_edge, edge="E")])
    return {"pass": not errors, "errors": errors, "checks": checks}


def test_mutation_edge_toggle_display(doc):
    errors, checks = mo.run_mutations(
        doc, lambda: _build_single_edge(doc), _oracle_edge,
        [functools.partial(mo.toggle_display)])
    return {"pass": not errors, "errors": errors, "checks": checks}


def test_mutation_edge_recompute_convergence(doc):
    errors, checks = mo.run_mutations(
        doc, lambda: _build_single_edge(doc), _oracle_edge,
        [functools.partial(mo.recompute_convergence, iterations=5)])
    return {"pass": not errors, "errors": errors, "checks": checks}


# ---- Pipeline (ops 1, 2, 3, 4, 5) --------------------------------------

def test_mutation_pipeline_shared_edge(doc):
    """Move a pole on the shared edge E_s12 -> both patches + the blend
    rebuild and revalidate with the seam still clean (op 1)."""
    errors, checks = mo.run_mutations(
        doc, lambda: _build_corner_pair_model(doc), _oracle_corner_pair,
        [functools.partial(mo.move_boundary_pole, edge="E_s12", pole_index=1,
                           delta=Vector(3.0, 2.0, 1.0))])
    return {"pass": not errors, "errors": errors, "checks": checks}


def test_mutation_pipeline_change_splits(doc):
    """Set / remove / sweep USplits on both patches; subgrid cells rebuild
    and the blend band stays the correct seam-adjacent cell (op 2)."""
    errors, checks = mo.run_mutations(
        doc, lambda: _build_corner_pair_model(doc), _oracle_corner_pair,
        [functools.partial(mo.change_splits, patch="Patch44"),
         functools.partial(mo.change_splits, patch="Patch001")])
    return {"pass": not errors, "errors": errors, "checks": checks}


def test_mutation_pipeline_reverse_edge(doc):
    """Reverse the shared edge E_s12; orient_a_to_b re-orients both patches
    and the blend stays fold-free (op 3)."""
    errors, checks = mo.run_mutations(
        doc, lambda: _build_corner_pair_model(doc), _oracle_corner_pair,
        [functools.partial(mo.reverse_edge, edge="E_s12"),
         functools.partial(mo.reverse_edge, edge="E_s12")])
    return {"pass": not errors, "errors": errors, "checks": checks}


def test_mutation_pipeline_toggle_display(doc):
    """Flip ShowSubgrids/ShowGrid/AutoHideBlend; the patch Shape never
    becomes invalid or wrongly empty (op 4)."""
    errors, checks = mo.run_mutations(
        doc, lambda: _build_corner_pair_model(doc), _oracle_corner_pair,
        [functools.partial(mo.toggle_display,
                           obj=lambda m: m["patches"]["Patch44"])])
    return {"pass": not errors, "errors": errors, "checks": checks}


def test_mutation_pipeline_recompute_convergence(doc):
    """Recompute repeatedly over the whole pipeline; every object's oracle
    stays green and no pole set drifts (no ping-pong) (op 5)."""
    errors, checks = mo.run_mutations(
        doc, lambda: _build_corner_pair_model(doc), _oracle_corner_pair,
        [functools.partial(mo.recompute_convergence, iterations=5)])
    return {"pass": not errors, "errors": errors, "checks": checks}


# ---- Chain gate (op 5: chain GT stays at 1e-6) -------------------------

def test_mutation_chain_recompute_convergence(doc):
    """Rebuild the ground-truth 7-edge / 2-patch chain, then recompute
    repeatedly; the blend (and both patches) keep matching the stored
    fixture at 1e-6."""
    import os
    from Tests.test_blend_stage import _build_gt_chain, FIXTURE
    from SilkChecks import check_blend, check_patch44

    errors, checks = [], []
    fixture = FreeCAD.openDocument(FIXTURE)
    FreeCAD.setActiveDocument(doc.Name)
    try:
        pa, pb, _ = _build_gt_chain(doc, fixture)
        blend = doc.addObject("Part::FeaturePython", "BlendStrip")
        # rebuild through the ops layer for a faithful copy
        from SilkWorkflowOps import create_blend
        blend = create_blend(pa, pb, name="BlendStrip")
        stored_blend = fixture.BlendStrip.Poles
        stored_pa = fixture.Patch44.Poles
        stored_pb = fixture.Patch001.Poles
        for i in range(5):
            doc.recompute()
            bdev = max((p - s).Length for p, s in zip(blend.Poles, stored_blend))
            padev = max((p - s).Length for p, s in zip(pa.Poles, stored_pa))
            pbdev = max((p - s).Length for p, s in zip(pb.Poles, stored_pb))
            bad = [(n, d) for n, ok, d in
                   check_blend(blend, pa, pb, reference_poles=stored_blend)
                   if not ok]
            bad += [(n, d) for n, ok, d in check_patch44(pa, [pa.Poly0, pa.Poly1,
                                                              pa.Poly2, pa.Poly3])
                    if not ok]
            bad += [(n, d) for n, ok, d in check_patch44(pb, [pb.Poly0, pb.Poly1,
                                                              pb.Poly2, pb.Poly3])
                    if not ok]
            if bad:
                errors.append("chain iter %d: oracle not green: %s" % (i, bad))
            if max(bdev, padev, pbdev) > CHAIN_GT_TOL:
                errors.append("chain iter %d: GT deviation %.3e > %.0e"
                              % (i, max(bdev, padev, pbdev), CHAIN_GT_TOL))
        if not errors:
            checks.append("chain recomputed 5x; oracle green, blend+patches "
                          "match fixture within %.0e" % CHAIN_GT_TOL)
    finally:
        FreeCAD.closeDocument(fixture.Name)
        FreeCAD.setActiveDocument(doc.Name)
    return {"pass": not errors, "errors": errors, "checks": checks}


ALL_TESTS = [
    test_mutation_edge_move_boundary_pole,
    test_mutation_edge_reverse,
    test_mutation_edge_toggle_display,
    test_mutation_edge_recompute_convergence,
    test_mutation_pipeline_shared_edge,
    test_mutation_pipeline_change_splits,
    test_mutation_pipeline_reverse_edge,
    test_mutation_pipeline_toggle_display,
    test_mutation_pipeline_recompute_convergence,
    test_mutation_chain_recompute_convergence,
]
