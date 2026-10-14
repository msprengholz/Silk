"""
Tests/test_mutation_unified.py — mutation matrix over the UNIFIED
objects (issue #41): quad Patch (4-edge fill), pointed Patch (3-edge
fill) and the unified Blend. Build, then change, then verify — the
recompute/live-update chain must stay stable under mutation, not just
at build time (spec "Testing Decisions", first-class mutation safety).

Driven through the shared operators in Tests.mutation_ops (extended by
#41: the unified Patch oracle case, the axis-selectable change_splits,
and hidden-cell-set convergence tracking) + the full oracle
(check_edge / check_patch / check_blend — B1 C0, B2 C1, B3 surface
valid + no self-intersection + coherent normal field).

Scenario coverage (criterion 5):
  Edge         : tests 1/4 (GT chain E_Shr), test 2 (cone profile A2),
                 test 3 (hood edge H2)
  Patch quad   : test 1 (GT chain), test 3 (hood), test 4 (worst case)
  Patch pointed: test 2 (cone pair), test 3 (cone side)
  Blend        : every test (all four pipeline models carry one)
  Patch44 legacy: Tests/test_mutation_backfill.py (unchanged, #43)

Builders reuse existing fixtures, nothing duplicated silently:
  - GT chain: Tests.test_blend_stage.GT_CHAIN_EDGES +
    Tests.test_patch_stage._copy_fixture_edge + create_patch +
    create_blend + the Silk_Workflow.FCStd fixture for pole comparison.
    The chain builder lives HERE rather than factored out of
    Tests/test_chain.py because that gate's inline build is entangled
    with its per-step assertion stream and tree census; factoring would
    risk the byte-equivalent acceptance gate for no reuse (the mutation
    model dict has a different shape than the gate's error/check
    stream). Same ingredients, same ops layer — the parity is
    re-proven by test 4's 0.0 baseline deviation anyway.
  - Pointed fixtures: Tests.test_blend_unified._build_cone_pair (3+3,
    seam touches the degenerate apex on both sides) and
    _build_cone_hood (3+4, seam on the clean rim arc).

Split-sweep safety (documented per model, see SEAM_AXIS_SAFE below):
the blend band (#33) is the seam-adjacent subgrid cell; its cell COUNT
depends only on the axis PARALLEL to the shared seam. Since #82 that
axis carries two NAMED band edges, one per end, and each edge drops
exactly one corner cell -- so a seam-parallel sweep keeps a single band
cell whenever the two ends hold DIFFERENT values, which SEAM_AXIS_SAFE
enforces. Perpendicular sweeps may take any values. Chosen per model and
asserted empirically green:
  GT quad   pa seam V0 -> V axis seam-parallel, U axis perpendicular
            pb seam U0 -> U axis seam-parallel, V axis perpendicular
  cone pair pa seam U1 / pb seam U0 -> U axis seam-parallel both
  cone+hood cone seam V1 -> V axis seam-parallel (U perp),
            hood seam U0 -> U axis seam-parallel (V perp)

Known latent bug found & fixed while deriving these (#41 report):
ArachNURBS.blend_poly_2x4_1x6's end-point degeneracy guard inspected
the FIRST curve while the tangent comes from the SECOND, so a blend row
pairing a non-degenerate row with a degenerate one (coneA USplit1=0.1
vs coneB's apex column) crashed "Cannot normalize null vector". Fixed
with a both-curves guard (strictly crash-only change); the (0.1, no band)
cone-pair sweep below is the red->green regression for it.
"""

import functools
import os

import FreeCAD

from Tests import mutation_ops as mo

Vector = FreeCAD.Vector

TOL = 1e-6

FIXTURE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..",
                       "Resources", "Test_files", "Silk_Workflow.FCStd")

# Sweep values that keep the blend band a single seam-adjacent cell on
# the axis PARALLEL to the seam (see module docstring), as `(Split1,
# Split2)` pairs: (0, 1) -> no edge at either end, one interval; (0, 0.9)
# and (0.1, 1) -> one end's edge, which drops that end's cell as the
# corner cell (#33 band_cells) and leaves exactly one band cell. Every
# pair holds DIFFERENT values at the two ends, which is what keeps the
# band non-degenerate: two ends holding the same edge would collapse the
# axis to a single split whose BOTH cells are corner cells. The final
# value also proves the corner-exclusion path; on the PERPENDICULAR axis
# the operator's default sweep ((0.5, 1), (0.25, 0.75), (0, 1), (0.1, 1),
# (0, 0.9)) is safe at every step and is used unchanged.
SEAM_AXIS_SAFE = ((0.0, 0.9), (0.0, 1.0), (0.1, 1.0))


# ---- builders ----------------------------------------------------------

def _build_unified_gt_chain(doc, fixture):
    """The ground-truth chain rebuilt on UNIFIED objects through the ops
    layer: 7 edges -> 2 unified Patches -> 1 unified Blend. `fixture`
    must be open. Returns the mutation model dict."""
    from Tests.test_patch_stage import _copy_fixture_edge
    from Tests.test_blend_stage import GT_CHAIN_EDGES
    from SilkWorkflowOps import create_patch, create_blend

    edges = {}
    for edge_name, sketch_names in GT_CHAIN_EDGES:
        edges[edge_name] = _copy_fixture_edge(doc, fixture, edge_name,
                                              sketch_names)
    loops = {"pa": ("E_Top", "E_Left", "E_BtmL", "E_Shr"),
             "pb": ("E_Shr", "E_BtmR", "E_CurR", "E_TopR")}
    patches, patch_edges = {}, {}
    for key, loop in loops.items():
        eds = [edges[n] for n in loop]
        patches[key] = create_patch(eds, name="Patch_%s" % key)
        patch_edges[key] = eds
    blend = create_blend(patches["pa"], patches["pb"], name="Blend")
    return {"doc": doc, "edges": edges, "patches": patches,
            "patch_edges": patch_edges, "blend": blend}


def _build_pointed_pair_model(doc):
    """Two unified 3-edge cone quarters sharing the degenerate profile
    (seam touches the apex on both sides) + the unified Blend."""
    from Tests.test_blend_unified import _build_cone_pair
    from SilkWorkflowOps import create_blend

    pa, pb, qa, qb = _build_cone_pair(doc)
    blend = create_blend(pa, pb, name="BlendPP")
    edges = {}
    for i, e in enumerate(qa):
        edges["A%d" % i] = e
    for i, e in enumerate(qb):
        edges["B%d" % i] = e
    return {"doc": doc, "edges": edges, "patches": {"pa": pa, "pb": pb},
            "patch_edges": {"pa": list(qa), "pb": list(qb)},
            "blend": blend}


def _build_pointed_quad_model(doc):
    """Unified 3-edge pointed cone + unified 4-edge quad hood sharing
    the rim arc + the unified Blend."""
    from Tests.test_blend_unified import _build_cone_hood
    from SilkWorkflowOps import create_blend

    cone, hood, qc, qh = _build_cone_hood(doc)
    blend = create_blend(cone, hood, name="BlendPQ")
    edges = {}
    for i, e in enumerate(qc):
        edges["C%d" % i] = e
    for i, e in enumerate(qh):
        edges["H%d" % i] = e
    return {"doc": doc, "edges": edges, "patches": {"pa": cone, "pb": hood},
            "patch_edges": {"pa": list(qc), "pb": list(qh)},
            "blend": blend}


# ---- oracle ------------------------------------------------------------

def _oracle_edge_patch_blend(model):
    """Full correctness check for a 2-patch + blend model: every edge
    (check_edge), every patch (check_patch — quad or pointed,
    dispatched on the Edges count) and the blend (check_blend B1/B2/B3;
    B4 skipped without a stored reference)."""
    from SilkChecks import check_edge, check_patch, check_blend
    res = []
    for n, e in sorted(model["edges"].items()):
        res += [("edge:%s:%s" % (n, cn), ok, d)
                for cn, ok, d in check_edge(e)]
    for k in sorted(model["patches"]):
        res += [("patch:%s:%s" % (k, cn), ok, d)
                for cn, ok, d in check_patch(model["patches"][k],
                                             model["patch_edges"][k])]
    b = model.get("blend")
    if b is not None:
        res += [("blend:%s" % cn, ok, d)
                for cn, ok, d in check_blend(
                    b, model["patches"]["pa"], model["patches"]["pb"])]
    return res


# ---- test 1: GT quad pipeline ------------------------------------------

def test_mutation_unified_quad_pipeline(doc):
    """Unified quad pipeline (GT chain: 2 unified Patches + 1 unified
    Blend) under the full mutation matrix:
      - move a pole on the SHARED boundary edge E_Shr -> both patches
        AND the blend rebuild (acceptance 1);
      - change_splits on BOTH axes of BOTH patches (acceptance 2):
        perpendicular axes take the default sweep, seam-parallel axes
        (pa's V axis for the V0 seam, pb's U axis for the U0 seam) take
        SEAM_AXIS_SAFE so the band stays a single cell at every step;
      - display toggles;
      - recompute convergence incl. hidden-cell-set assertions
        (acceptance 3). The full oracle (check_edge + check_patch +
        check_blend B1/B2/B3) must stay green after every operator."""
    errors, checks = [], []
    fixture = FreeCAD.openDocument(FIXTURE)
    FreeCAD.setActiveDocument(doc.Name)
    try:
        errs, chks = mo.run_mutations(
            doc, lambda: _build_unified_gt_chain(doc, fixture),
            _oracle_edge_patch_blend,
            [functools.partial(mo.move_boundary_pole, edge="E_Shr",
                               pole_index=1, delta=Vector(3.0, 2.0, 1.0)),
             functools.partial(mo.change_splits, patch="pa",
                               splits_axis="U"),
             functools.partial(mo.change_splits, patch="pa",
                               splits_axis="V",
                               splits_sweep=SEAM_AXIS_SAFE),
             functools.partial(mo.change_splits, patch="pb",
                               splits_axis="U",
                               splits_sweep=SEAM_AXIS_SAFE),
             functools.partial(mo.change_splits, patch="pb",
                               splits_axis="V"),
             functools.partial(mo.toggle_display, obj="pa"),
             functools.partial(mo.recompute_convergence, iterations=5)])
        errors += errs
        checks += chks
    finally:
        FreeCAD.closeDocument(fixture.Name)
        FreeCAD.setActiveDocument(doc.Name)
    return {"pass": not errors, "errors": errors, "checks": checks}


# ---- test 2: pointed pair (3+3) ----------------------------------------

def test_mutation_unified_pointed_pair(doc):
    """Pointed <-> pointed (two 3-edge cone quarters sharing the
    degenerate profile, seam apex on both sides): boundary-pole move on
    the shared profile (its endpoints are the seam corners, so the
    corner-based seam detection stays valid while both patches' nets
    change), splits sweep on BOTH axes of both patches (seam-parallel
    U axes take SEAM_AXIS_SAFE — including (0.1, no band), the value that
    regresses the blend_poly degenerate-second-curve fix — perpendicular
    V axes take the default sweep), and recompute
    convergence with hidden-cell-set assertions. The full oracle must
    stay green after every operator."""
    errors, checks = [], []
    errs, chks = mo.run_mutations(
        doc, lambda: _build_pointed_pair_model(doc),
        _oracle_edge_patch_blend,
        [functools.partial(mo.move_boundary_pole, edge="A2",
                           pole_index=1, delta=Vector(2.0, 1.0, 1.0)),
         functools.partial(mo.change_splits, patch="pa",
                           splits_axis="U",
                           splits_sweep=SEAM_AXIS_SAFE),
         functools.partial(mo.change_splits, patch="pa",
                           splits_axis="V"),
         functools.partial(mo.change_splits, patch="pb",
                           splits_axis="U",
                           splits_sweep=SEAM_AXIS_SAFE),
         functools.partial(mo.change_splits, patch="pb",
                           splits_axis="V"),
         functools.partial(mo.recompute_convergence, iterations=5)])
    errors += errs
    checks += chks
    return {"pass": not errors, "errors": errors, "checks": checks}


# ---- test 3: pointed <-> quad (3+4) ------------------------------------

def test_mutation_unified_pointed_quad(doc):
    """Pointed <-> quad (3-edge cone + 4-edge hood sharing the rim
    arc): both fill types mutate cleanly — a boundary-pole move on the
    hood's NON-shared edge H2 (rebuilds the quad patch, the blend band
    follows), splits sweeps on both axes of both patches (cone seam V1:
    V axis seam-parallel safe / U axis perpendicular default; hood
    seam U0: U axis seam-parallel safe / V axis perpendicular
    default), and recompute convergence with hidden-cell-set
    assertions. The full oracle must stay green after every operator."""
    errors, checks = [], []
    errs, chks = mo.run_mutations(
        doc, lambda: _build_pointed_quad_model(doc),
        _oracle_edge_patch_blend,
        [functools.partial(mo.move_boundary_pole, edge="H2",
                           pole_index=1, delta=Vector(0.0, -3.0, -2.0)),
         functools.partial(mo.change_splits, patch="pa",
                           splits_axis="V",
                           splits_sweep=SEAM_AXIS_SAFE),
         functools.partial(mo.change_splits, patch="pa",
                           splits_axis="U"),
         functools.partial(mo.change_splits, patch="pb",
                           splits_axis="U",
                           splits_sweep=SEAM_AXIS_SAFE),
         functools.partial(mo.change_splits, patch="pb",
                           splits_axis="V"),
         functools.partial(mo.recompute_convergence, iterations=5)])
    errors += errs
    checks += chks
    return {"pass": not errors, "errors": errors, "checks": checks}


# ---- test 4: worst-case mutation, revert, 1e-6 ground truth -----------

def test_mutation_chain_worst_case_restores_1e6(doc):
    """Acceptance 4 (bespoke flow — needs revert, not run_mutations):
    build the unified GT chain fresh, capture the baseline pole
    deviation vs the stored fixture (expect 0.0: same ops-layer build
    path), then apply the worst-case mutation sequence — shared-boundary
    pole move + band-edge changes on BOTH patches + >=5
    recomputes — asserting the full oracle is green at EVERY step, then
    revert every mutation to its EXACT original value, recompute, and
    assert the stored ground truth (edges + both patches + blend) holds
    at <=1e-6. The actual deviation numbers are reported in the checks.
    """
    errors, checks = [], []

    def _dev(obj, stored):
        return max((p - s).Length
                   for p, s in zip(list(obj.Poles), stored))

    fixture = FreeCAD.openDocument(FIXTURE)
    FreeCAD.setActiveDocument(doc.Name)
    try:
        m = _build_unified_gt_chain(doc, fixture)
        pa, pb, blend = m["patches"]["pa"], m["patches"]["pb"], m["blend"]

        def oracle_green(step):
            bad = [(n, d) for n, ok, d
                   in _oracle_edge_patch_blend(m) if not ok]
            if bad:
                errors.append("%s: oracle not green: %s" % (step, bad))
            return not bad

        # baseline vs the stored fixture (expect exact: identical build path)
        base = {n: _dev(e, fixture.getObject(n).Poles)
                for n, e in m["edges"].items()}
        base["pa"] = _dev(pa, fixture.Patch44.Poles)
        base["pb"] = _dev(pb, fixture.Patch001.Poles)
        base["blend"] = _dev(blend, fixture.BlendStrip.Poles)
        worst = max(base.values())
        if worst > TOL:
            errors.append("baseline deviates from fixture by %.3e "
                          "(expect 0.0 at build time)" % worst)
        else:
            checks.append("baseline: max pole dev vs fixture %.3e "
                          "(expect 0.0)" % worst)

        # ---- worst-case mutation sequence, oracle green at every step
        orig_poles = {n: list(e.Poles) for n, e in m["edges"].items()}
        from SilkMachinery import split_pair
        props = ("USplit1", "USplit2", "VSplit1", "VSplit2")
        orig_splits = tuple(float(getattr(p, q))
                            for p in (pa, pb) for q in props)
        shr = m["edges"]["E_Shr"]
        poles = list(shr.Poles)
        poles[1] = poles[1] + Vector(3.0, 2.0, 1.0)   # shared boundary pole
        shr.Poles = poles
        doc.recompute()
        oracle_green("after shared-edge pole move")
        pa.USplit1 = 0.5       # pa seam V0: perpendicular axis
        doc.recompute()
        oracle_green("after pa.USplit1=0.5")
        pa.VSplit2 = 0.9       # pa seam-parallel axis: band cell v0 only
        doc.recompute()
        oracle_green("after pa.VSplit2=0.9")
        pb.USplit2 = 0.9       # pb seam U0, seam-parallel: band cell u0
        doc.recompute()
        oracle_green("after pb.USplit2=0.9")
        pb.VSplit1 = 0.5       # pb perpendicular axis
        doc.recompute()
        oracle_green("after pb.VSplit1=0.5")
        for i in range(5):
            doc.recompute()
            oracle_green("mutated recompute %d" % i)

        # ---- revert every mutation to its exact original value
        for n, e in m["edges"].items():
            e.Poles = orig_poles[n]
        for patch_, off in ((pa, 0), (pb, 4)):
            for k, q in enumerate(props):
                setattr(patch_, q, orig_splits[off + k])
        for i in range(5):
            doc.recompute()
        if not oracle_green("after full revert"):
            return {"pass": False, "errors": errors, "checks": checks}

        devs = {n: _dev(e, fixture.getObject(n).Poles)
                for n, e in m["edges"].items()}
        devs["pa"] = _dev(pa, fixture.Patch44.Poles)
        devs["pb"] = _dev(pb, fixture.Patch001.Poles)
        devs["blend"] = _dev(blend, fixture.BlendStrip.Poles)
        for n in sorted(devs):
            if devs[n] > TOL:
                errors.append("post-revert %s deviates %.3e (> %.0e)"
                              % (n, devs[n], TOL))
        checks.append("worst-case reverted: max pole dev vs fixture "
                      "edges=%.3e pa=%.3e pb=%.3e blend=%.3e (tol %.0e)"
                      % (max(devs[n] for n in m["edges"]),
                         devs["pa"], devs["pb"], devs["blend"], TOL))
    finally:
        FreeCAD.closeDocument(fixture.Name)
        FreeCAD.setActiveDocument(doc.Name)
    return {"pass": not errors, "errors": errors, "checks": checks}


ALL_TESTS = [
    test_mutation_unified_quad_pipeline,
    test_mutation_unified_pointed_pair,
    test_mutation_unified_pointed_quad,
    test_mutation_chain_worst_case_restores_1e6,
]
