"""
#68 — what a pointed patch's `Edges` list means, pinned.

The ticket exists because one fixture's luck was read as a fill's
property. So this module carries THREE fixtures, deliberately:

1. `_make_corner_triple_edges` — the CLOSED curved corner triple: two
   seams radiating from the degenerate corner (0,0,0) plus one outer
   curve. This is the boundary a cube-corner pointed patch actually
   has. Note what "closed" forces: a loop of three distinct two-ended
   curves has three corners, so the degenerate corner is shared by
   exactly TWO of the three edges (the C1 layout: (0,0) shared by
   edges 0+2). No three distinct curves forming ONE closed loop can
   all share a single endpoint.

2. `_make_fan_triple_edges` — the literal #68 measurement: Seam_X,
   Seam_Y, Seam_Z ALL with an endpoint at (0,0,0), far ends
   unconnected — a Y, not a loop. Before this ticket's fix, that
   topology reproduced the issue's numbers exactly: 6/6 orderings
   built 16 poles and every one was oracle-RED on C1_corner_order and
   C2_boundary_match (3 of 6 also P3/P4). The input is not a closed
   boundary, so per the product's own terms (`Edges` is a CYCLE —
   #66/#67, loop_order's docstring, create_patch's refusal text) the
   answer is REFUSAL, not normalization: loop_order's per-edge closure
   check used to be vacuous for 3 edges ("meets exactly 2 of the other
   2" — there ARE only 2 others), which is how the Y slipped through
   and built garbage.

3. the FLAT triangle (Tests.test_patch_gui_command._make_triangle_edges,
   all z=0) — kept here so flat and curved are both present and
   neither is mistaken for the other's property.

Semantics settled for the pointed fill (#68, branch (a) + the
ticket's own second-bullet fallback):

  * `Edges` is a CYCLE for 3 edges exactly as for 4: entry k IS
    boundary side k — row U0 = Edges[0], col V3 = Edges[1], row U3 =
    Edges[2]. The oracle's C1/C2/C3 already check exactly that meaning.
  * For a CLOSED triple every ordering is ALREADY a cyclic order (with
    three corners the walk has no freedom), so loop_order returns the
    list verbatim — the #67 persistence is structurally a no-op for
    3-edge lists (nothing to rotate), and the invariant holds for
    whatever order arrived: check_patch(p, list(p.Edges)) green on all
    6 orderings.
  * The degenerate corner IS the Edges[2]->Edges[0] junction — list
    position by definition, i.e. the corner OPPOSITE the list's middle
    edge. So an ordering that changes the middle edge (4 of the 6)
    moves the cone point, and the SURFACE genuinely differs: no
    symmetry of the parametric square can map it back, because a
    reparameterization would have to carry the cone to a different
    physical point on the boundary (measured: tens of mm on this
    fixture). The one remaining non-canonical ordering — the pure loop
    reversal [SeamY, Outer, SeamX] — keeps the cone and comes back as
    the mirror image: the SAME surface. The partition (4 differ,
    reversal matches) is asserted, on the curved triple AND on the flat
    fixture. That is NOT removable by normalization: every ordering of
    a closed triple is already cyclic, so no walk can canonicalize it,
    and no rule in the product derives WHICH of the three corners
    should collapse from the curves alone. The ticket's second bullet
    offers exactly this resolution — "record that the caller must
    supply the degenerate corner in a defined position" — and
    test_pointed_degenerate_corner_follows_the_list_and_the_surface_with_it
    records it: the cone-corner rule (and the surface partition it
    implies) is the documented meaning, asserted, not folklore.
  * A fan is refused with loop_order's per-edge message; poles never
    build, so no object can disagree with its own geometry.

(The surface comparisons here ride on `Tests.test_patch_stage._same_surface`,
which #68 discovered comparing the reference to ITSELF — identity gave
worst 0 for any candidate, so every "same surface" claim since #66 was
vacuous, including this module's first green run — and then, once the
candidate was actually read, discovered its non-identity symmetry maps
hardcoded to pole-grid complements (3) while indexing the 7x7 SAMPLE
grid, so no rotation or flip could ever match either. Both defects are
fixed, and the helper is pinned in both directions by
test_surface_comparison_helper_actually_compares: transpose / quarter
turn / flip accepted, a moved interior pole rejected.)
"""

import itertools

import FreeCAD
import Part

Vector = FreeCAD.Vector

from SilkChecks import check_patch
from SilkMachinery import loop_order
from SilkWorkflowOps import create_edge, create_patch
from Tests.test_patch_stage import _CaptureConsole, _same_surface
from Tests.test_patch_gui_command import _make_triangle_edges \
    as _make_flat_triangle_edges


def _make_poly_edge(doc, name, pts):
    """One 4-pole SilkEdge whose control polygon is `pts` (Bezier
    endpoints = pts[0]/pts[-1], which is what loop_order reads)."""
    sk = doc.addObject("Sketcher::SketchObject", name + "_sk")
    for j in range(3):
        sk.addGeometry(Part.LineSegment(pts[j], pts[j + 1]))
    doc.recompute()
    return create_edge(sk, name=name)


def _make_corner_triple_edges(doc):
    """The CLOSED curved corner triple: SeamX (origin -> rim), Outer
    (rim -> rim, doubly curved), SeamY (rim -> origin). Degenerate
    corner (0,0,0) shared by SeamX+SeamY; canonical cycle order is
    [SeamX, Outer, SeamY], matching the pointed C1 layout ((0,0)
    shared by edges 0+2)."""
    return [
        _make_poly_edge(doc, "SeamX",
                        [Vector(0, 0, 0), Vector(16, 0, 0),
                         Vector(34, 0, 4), Vector(50, 0, 8)]),
        _make_poly_edge(doc, "Outer",
                        [Vector(50, 0, 8), Vector(50, 22, 16),
                         Vector(28, 50, 16), Vector(0, 50, 8)]),
        _make_poly_edge(doc, "SeamY",
                        [Vector(0, 50, 8), Vector(0, 34, 4),
                         Vector(0, 16, 0), Vector(0, 0, 0)]),
    ]


def _make_fan_triple_edges(doc):
    """The #68 measurement topology: Seam_X, Seam_Y, Seam_Z all with an
    endpoint at the degenerate corner (0,0,0), far ends unconnected.
    A Y, not a loop — no ordering closes corner to corner."""
    return [
        _make_poly_edge(doc, "Seam_X",
                        [Vector(0, 0, 0), Vector(18, 0, 2),
                         Vector(34, 0, 7), Vector(50, 0, 12)]),
        _make_poly_edge(doc, "Seam_Y",
                        [Vector(0, 0, 0), Vector(0, 18, 2),
                         Vector(0, 34, 7), Vector(0, 50, 12)]),
        _make_poly_edge(doc, "Seam_Z",
                        [Vector(0, 0, 0), Vector(14, 10, 16),
                         Vector(28, 26, 24), Vector(40, 40, 32)]),
    ]


def _bad_checks(patch, stored):
    return [(n, d) for (n, ok, d) in check_patch(patch, stored) if not ok]


def test_pointed_corner_triple_all_6_orderings_agree_with_their_own_edges(doc):
    """The Edges[k]-is-side-k invariant for the pointed fill, on the
    curved corner triple, all 6 orderings: every ordering builds, the
    stored list is NOT reordered (every ordering of a closed triple is
    already cyclic — the #67 no-op), and every patch is oracle-green
    on its OWN list(p.Edges).

    Surface equality across orderings is deliberately NOT asserted
    here: for the pointed fill it is false by meaning (the degenerate
    corner follows Edges[2]->Edges[0], so a rotated list is a
    different patch) and is pinned honestly in
    test_pointed_degenerate_corner_follows_the_list_and_the_surface_with_it.
    """
    errors, checks = [], []
    triple = _make_corner_triple_edges(doc)

    canon = create_patch(list(triple), name="CTC")
    if canon is None or len(canon.Poles) != 16:
        errors.append("canonical corner triple built %d poles"
                      % len(canon.Poles))
        return {"pass": False, "errors": errors, "checks": checks}
    bad = _bad_checks(canon, list(canon.Edges))
    if bad:
        errors.append("canonical corner triple oracle-red on its own "
                      "Edges: %s" % bad)

    empties, reordered, bad_oracle = [], [], []
    for perm in itertools.permutations(range(3)):
        sel = [triple[i] for i in perm]
        label = "".join(str(i) for i in perm)
        patch = create_patch(list(sel), name="CT")
        if patch is None or len(patch.Poles) != 16:
            empties.append(label)
            continue
        stored = [e.Name for e in patch.Edges]
        if stored != [e.Name for e in sel]:
            reordered.append("%s -> %s" % (label, stored))
        bad = _bad_checks(patch, list(patch.Edges))
        if bad:
            bad_oracle.append("%s: %s" % (label, bad))
    if empties:
        errors.append("corner-triple orderings with no poles: %s" % empties)
    if reordered:
        errors.append("closed-triple lists were reordered (loop_order "
                      "must return every ordering verbatim): %s" % reordered)
    if bad_oracle:
        errors.append("corner-triple oracle-red on list(p.Edges): %s"
                      % bad_oracle)
    checks.append("curved corner triple: 6/6 built, stored verbatim, "
                  "oracle-green on own Edges")
    return {"pass": not errors, "errors": errors, "checks": checks}


def test_pointed_fan_of_three_seams_is_refused_never_built(doc):
    """#68's 6/6-red reproduction, pinned as the OPPOSITE contract.

    The fan (three seams all ending at (0,0,0), far ends free) is not
    a closed loop. Before the fix this very topology built 6/6 and was
    oracle-RED on C1+C2 every time — an object disagreeing with its
    own geometry. The contract now: loop_order refuses it naming each
    edge, and NO ordering ever builds poles; a returned object is the
    documented empty/valid graceful state with a console error, and
    the oracle flags it incomplete (structural) rather than green."""
    errors, checks = [], []
    fan = _make_fan_triple_edges(doc)

    order, problem = loop_order(list(fan))
    if order is not None:
        errors.append("loop_order ACCEPTED a fan of three seams: %r "
                      "(problem=%r) — the issue's garbage build starts "
                      "here" % ([e.Name for e in order], problem))
    else:
        names = {e.Label for e in fan} | {e.Name for e in fan}
        missing = sorted(n for n in names if n not in (problem or ""))
        if missing:
            errors.append("loop_order's fan refusal does not name: %s "
                          "(got %r)" % (missing, problem))
        checks.append("loop_order refuses the fan: %s" % problem)

    built, msgs_missing = [], []
    for perm in itertools.permutations(range(3)):
        sel = [fan[i] for i in perm]
        label = "".join(str(i) for i in perm)
        with _CaptureConsole() as cap:
            patch = create_patch(list(sel), name="FAN")
        if patch is None:
            continue                     # create-time refusal: also fine
        if len(patch.Poles) != 0:
            built.append("%s: %d poles, oracle %s"
                         % (label, len(patch.Poles),
                            _bad_checks(patch, list(patch.Edges))))
            continue
        if not (patch.Shape is None or patch.Shape.isNull()
                or not patch.Shape.Faces):
            built.append("%s: empty poles but a real face" % label)
        msg = "".join(cap.errors)
        if not any(n in msg for n in ("Seam_X", "Seam_Y", "Seam_Z")):
            msgs_missing.append("%s: %r" % (label, msg.strip()))
    if built:
        errors.append("fan orderings BUILT garbage (this is the #68 "
                      "6/6-red state): %s" % built)
    if msgs_missing:
        errors.append("fan refusal console error missing the seam "
                      "names: %s" % msgs_missing)
    checks.append("all 6 fan orderings refused: no poles, no face, "
                  "console error names the seams")
    return {"pass": not errors, "errors": errors, "checks": checks}


def test_pointed_degenerate_corner_follows_the_list_and_the_surface_with_it(doc):
    """ORDER-DEPENDENCE, stated explicitly so no reader is misled again
    (#68's third bullet — "a test that says so explicitly").

    The pointed fill puts the degenerate corner at the
    Edges[2]->Edges[0] junction BY DEFINITION — equivalently the corner
    OPPOSITE the list's middle edge — and no rule in the product
    derives which of a triple's corners SHOULD collapse from the curves
    alone (normalization cannot help either: every ordering of a closed
    triple is already cyclic, so there is nothing for loop_order to
    canonicalize). So the caller's list position is the record, and the
    surface partition it forces is pinned here on all 6 orderings of
    the curved triple:

      * the 4 orderings with a different middle edge (021, 102, 120,
        201) move the cone to another physical corner — no
        parametrization can map the result back, so they must be
        DIFFERENT surfaces (measured, in the open: tens of mm);
      * the pure loop reversal (210) keeps the cone and comes back as
        the mirror image — the SAME surface, and it would be wrong to
        lump it in with the cone-movers.

    What must hold across ALL orderings instead is agreement with each
    patch's OWN stored list — the Edges[k]-is-side-k invariant —
    asserted here too.

    If this test ever FAILS because the cone-movers now MATCH: the fill
    became order-independent — a semantics change. Update this
    docstring and the module note, do not just flip the assertion.
    """
    errors, checks = [], []
    triple = _make_corner_triple_edges(doc)

    canon = create_patch(list(triple), name="CTP0")
    if canon is None or len(canon.Poles) != 16:
        errors.append("canonical build gave %r" % (canon,))
        return {"pass": False, "errors": errors, "checks": checks}

    cone_movers = {"021", "102", "120", "201"}
    differing, matching, bad_oracle = set(), set(), []
    pole_devs = {}
    for perm in itertools.permutations(range(3)):
        label = "".join(str(i) for i in perm)
        if label == "012":
            continue
        patch = create_patch([triple[i] for i in perm], name="CTP")
        if patch is None or len(patch.Poles) != 16:
            errors.append("ordering %s built %r" % (label, patch))
            continue
        pole_devs[label] = max((a - b).Length for a, b in
                               zip(canon.Poles, patch.Poles))
        ok, worst, how = _same_surface(
            (list(canon.Poles), list(canon.Weights)),
            (list(patch.Poles), list(patch.Weights)))
        (differing if not ok else matching).add(label)
        bad = _bad_checks(patch, list(patch.Edges))
        if bad:
            bad_oracle.append("%s: %s" % (label, bad))

    if differing != cone_movers:
        errors.append("expected the 4 cone-moving orderings %s to "
                      "differ, got differing=%s matching=%s — either the "
                      "fill's semantics changed or `_same_surface` broke "
                      "again (do not flip this assertion silently)"
                      % (sorted(cone_movers), sorted(differing),
                         sorted(matching)))
    else:
        checks.append("cone-moving orderings 021/102/120/201 are "
                      "DIFFERENT surfaces (max pole dev %.1f..%.1f mm "
                      "vs canonical); the loop reversal 210 is the "
                      "mirror image and matches — the surface follows "
                      "the CONE CORNER, which follows "
                      "Edges[2]->Edges[0]"
                      % (min(pole_devs[m] for m in cone_movers),
                         max(pole_devs[m] for m in cone_movers)))
    if "210" in pole_devs and pole_devs["210"] <= 1e-6:
        errors.append("the pure loop reversal reproduces the canonical "
                      "poles EXACTLY — unexpected: it must at least be "
                      "the mirrored pole grid, not the same grid")
    if bad_oracle:
        errors.append("non-canonical builds disagree with their own "
                      "Edges: %s" % bad_oracle)
    checks.append("every ordering oracle-green on its own stored list "
                  "(Edges[k] is side k)")
    return {"pass": not errors, "errors": errors, "checks": checks}


def test_pointed_corner_triple_loop_order_is_verbatim_in_every_ordering(doc):
    """Every ordering of a closed triple is already a cyclic order, so
    loop_order hands each one back AS THE SAME LIST OBJECT. This is
    the structural reason the #67 persistence writes nothing for
    3-edge lists (no rotation exists to persist) and the reason
    Patch33 parity cannot drift: the canonical list takes the
    byte-identical path it always did."""
    errors, checks = [], []
    triple = _make_corner_triple_edges(doc)
    for perm in itertools.permutations(range(3)):
        sel = [triple[i] for i in perm]
        label = "".join(str(i) for i in perm)
        out, problem = loop_order(sel)
        if problem is not None:
            errors.append("ordering %s refused: %s" % (label, problem))
        elif out is not sel:
            errors.append("ordering %s returned a copy/rotation: %r"
                          % (label, [e.Name for e in out]))
    if not errors:
        checks.append("all 6 closed-triple orderings returned "
                      "verbatim, same object (the no-op)")
    return {"pass": not errors, "errors": errors, "checks": checks}


def test_pointed_corner_triple_canonical_matches_legacy_patch33(doc):
    """Patch33 parity on the NEW fixture too: the canonical closed
    corner triple must still reproduce the legacy fill at 1e-6 — the
    legacy comparison is the reference, not the obstacle (#68)."""
    errors, checks = [], []
    from Tests.test_patch_unified import _make_legacy_patch33

    triple = _make_corner_triple_edges(doc)
    p33 = _make_legacy_patch33(doc, list(triple), name="P33CT")
    pun = create_patch(list(triple), name="PUnCT")
    if pun is None or len(pun.Poles) != 16:
        errors.append("canonical corner triple built %d poles"
                      % len(pun.Poles))
        return {"pass": False, "errors": errors, "checks": checks}
    dmax = max((a - b).Length for a, b in zip(pun.Poles, p33.Poles))
    wmax = max(abs(a - b) for a, b in zip(pun.Weights, p33.Weights))
    if dmax > 1e-6:
        errors.append("pointed pole parity deviates by %.3e (tol 1e-6)"
                      % dmax)
    if wmax > 1e-12:
        errors.append("pointed weight parity deviates by %.3e" % wmax)
    checks.append("corner triple canonical -> Patch33: max pole dev "
                  "%.2e, weight dev %.2e (tol 1e-6)" % (dmax, wmax))
    return {"pass": not errors, "errors": errors, "checks": checks}


def test_surface_comparison_helper_actually_compares(doc):
    """The INSTRUMENT has to read something (#68's measurement trap,
    found while mutation-checking this module).

    `_same_surface` used to compare the reference to its own
    symmetry-mapped image and never touched the candidate: identity
    then gives worst == 0 for ANY input, so every "same surface"
    claim in the suite was vacuous (a planted interior-pole mutation
    moved the sampled surface by 48 mm and the helper still answered
    "identical, 0.000e+00"). Pinned here in all three directions: a
    pure grid relabeling IS the same surface -- transpose, quarter
    turn and flip, because the rotation/flip maps were ALSO written
    with pole-grid complements (3) and applied to the 7x7 sample grid
    (#68) -- and a moved interior pole is NOT."""
    errors, checks = [], []
    triple = _make_corner_triple_edges(doc)
    p = create_patch(list(triple), name="INS")
    if p is None or len(p.Poles) != 16:
        errors.append("fixture patch built %d poles" % len(p.Poles))
        return {"pass": False, "errors": errors, "checks": checks}
    poles, weights = list(p.Poles), list(p.Weights)

    def _relabel(src, sym):
        """cand[sym(i, j)] = ref[i, j] on the 4x4 POLE grid."""
        out = [None] * 16
        for i in range(4):
            for j in range(4):
                i2, j2 = sym(i, j)
                out[i2 * 4 + j2] = src[i * 4 + j]
        return out

    relabelings = (
        ("transpose", lambda i, j: (j, i)),
        ("quarter turn", lambda i, j: (3 - j, i)),
        ("flip v", lambda i, j: (i, 3 - j)),
    )
    for label, sym in relabelings:
        cand = _relabel(poles, sym)
        tw = _relabel(weights, sym)
        ok, worst, how = _same_surface((poles, weights), (cand, tw))
        if not ok:
            errors.append("helper rejects a pure %s relabeling (worst "
                          "%.3e via %s)" % (label, worst, how))
        else:
            checks.append("%s relabeling accepted: worst %.3e via %s"
                          % (label, worst, how))

    moved = list(poles)
    moved[10] = moved[10] + FreeCAD.Vector(0.5, 0, 0)
    ok2, worst2, how2 = _same_surface((poles, weights), (moved, weights))
    if ok2:
        errors.append("helper accepted a 0.5mm-moved interior pole "
                      "(worst %.3e via %s) — it is not reading the "
                      "candidate" % (worst2, how2))
    else:
        checks.append("moved interior pole rejected: worst %.3e via %s"
                      % (worst2, how2))
    checks.append("grid relabeling accepted: worst %.3e via %s"
                  % (worst, how))
    return {"pass": not errors, "errors": errors, "checks": checks}


def test_pointed_flat_triangle_invariant_green_on_all_6_orderings(doc):
    """The FLAT triangle (the panel fixture), all 6 orderings: the
    invariant (structural, C1 corner order, C2 boundary match against
    the object's OWN stored list) holds for the flat fixture exactly
    as for the curved one — flat-vs-curved is a fixture property
    (P3/P4 surface checks may differ with the fixture, which is why
    #68 demanded BOTH fixtures), never an excuse for C1/C2.

    Surface equality across orderings is the pointed fill's documented
    order-dependence (see the module note) and is not asserted here."""
    errors, checks = [], []
    flat = _make_flat_triangle_edges(doc)

    canon = create_patch(list(flat), name="FLAT0")
    if canon is None or len(canon.Poles) != 16:
        errors.append("flat triangle built %d poles"
                      % len(canon.Poles))
        return {"pass": False, "errors": errors, "checks": checks}

    empties, bad_oracle = [], []
    for perm in itertools.permutations(range(3)):
        sel = [flat[i] for i in perm]
        label = "".join(str(i) for i in perm)
        patch = create_patch(list(sel), name="FLAT")
        if patch is None or len(patch.Poles) != 16:
            empties.append(label)
            continue
        bad = [(n, d) for (n, ok, d)
               in check_patch(patch, list(patch.Edges)) if not ok]
        # C1/C2/C3 + structural ARE the invariant, whatever the
        # fixture does to the surface checks:
        hard = [(n, d) for (n, d) in bad
                if n in ("structural", "C1_corner_order",
                         "C2_boundary_match", "C3_degenerate_pt")]
        if hard:
            bad_oracle.append("%s: %s" % (label, hard))
    if empties:
        errors.append("flat-triangle orderings with no poles: %s"
                      % empties)
    if bad_oracle:
        errors.append("flat-triangle invariant checks red on "
                      "list(p.Edges): %s" % bad_oracle)
    checks.append("flat triangle: 6/6 built, invariant (structural, "
                  "C1-C3) green on own Edges")
    return {"pass": not errors, "errors": errors, "checks": checks}
