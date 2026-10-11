"""
Seam resolver + seam inventory (ticket #44): identity-only ops layer.

Adjacency is OBJECT IDENTITY ONLY: the two patches adjacent to an Edge
are exactly those whose Edges link list contains it (the glossary's
"shared edge" vs "coincident boundary"). Coincident-but-unlinked
boundaries are never adjacent; 0 / 1 / 3+ referencing patches refuse
gracefully (console error, no exception, zero side effects).

Covered here:
  - resolve_seam: the correct pair on a 2-patch / 1-shared-edge build;
    the three refuse paths (unreferenced, single-patch, non-manifold);
    and the no-geometric-fallback rule (a coincident unlinked patch
    does NOT make an edge shared).
  - create_blend_by_edge: full check_blend oracle (incl. B4) on the
    ground-truth chain; idempotency (second call is a no-op naming the
    first blend, no second object); refuse paths create no blend and
    write no USplits/VSplits.
  - seam_inventory: blendable before / blended (named) after / blocked
    on the non-manifold edge; one entry per shared edge, so a pair
    sharing two edges gets one status per seam.
  - The #44 centerpiece -- two seams between the SAME patch pair
    (closed-ring/cylinder builds): run_blend derives the seam from the
    pinned Edge's ENDPOINT POLES (_seam_from_edge), not from the
    first-matching shared_seam auto-detect, so the pin picks the pinned
    seam. Verified: blending the second seam writes only that seam's
    band split, its 24 poles match an independently derived,
    seam-pinned reference at 1e-6, and -- since #49 gave check_blend an
    optional `edge=` seam pin mirroring create_blend's edge= contract --
    it passes the FULL oracle (structural + B1/B2/B3 + a B4 24-pole
    match) when invoked with that pin. Without the pin the oracle
    auto-detects the seam, so B1/B2 still flag the second-seam blend;
    that unpinned behaviour is unchanged and reported, not asserted on.
"""

import FreeCAD
import Part

Vector = FreeCAD.Vector

# 50x50 square in the z=0 plane, one straight 3-line sketch per side,
# cyclic direction (bottom -> right -> top -> left).
_SQUARE = {
    "bottom": [(0, 0, 0), (16.7, 0, 0), (33.3, 0, 0), (50, 0, 0)],
    "right": [(50, 0, 0), (50, 16.7, 0), (50, 33.3, 0), (50, 50, 0)],
    "top": [(50, 50, 0), (33.3, 50, 0), (16.7, 50, 0), (0, 50, 0)],
    "left": [(0, 50, 0), (0, 33.3, 0), (0, 16.7, 0), (0, 0, 0)],
}


class _Capture:
    """Capture BOTH console errors and messages (still forwarded)."""

    def __enter__(self):
        self.errors = []
        self.messages = []
        self._oe = FreeCAD.Console.PrintError
        self._om = FreeCAD.Console.PrintMessage
        FreeCAD.Console.PrintError = lambda m: (
            self.errors.append(str(m)), self._oe(m))
        FreeCAD.Console.PrintMessage = lambda m: (
            self.messages.append(str(m)), self._om(m))
        return self

    def __exit__(self, *args):
        FreeCAD.Console.PrintError = self._oe
        FreeCAD.Console.PrintMessage = self._om


# ---- fixture helpers (ops layer only) ------------------------------------

def _line_sketch(doc, name, pts):
    sk = doc.addObject("Sketcher::SketchObject", name)
    for a, b in zip(pts, pts[1:]):
        sk.addGeometry(Part.LineSegment(Vector(*a), Vector(*b)))
    doc.recompute()
    return sk


def _square_edges(doc, prefix):
    """Four straight 3L edges forming the closed square loop, cyclic."""
    from SilkWorkflowOps import create_edge
    edges = []
    for i, key in enumerate(("bottom", "right", "top", "left")):
        sk = _line_sketch(doc, "%s_sk%d" % (prefix, i), _SQUARE[key])
        edges.append(create_edge(sk, name="%s_%s" % (prefix, key)))
    return edges


def _square_patch(doc, name):
    from SilkWorkflowOps import create_patch
    return create_patch(_square_edges(doc, name), name=name)


def _patch_sharing(doc, shared_edge, name):
    """A fresh patch using `shared_edge` as its bottom side plus fresh
    coincident copies of the other three sides. Geometric overlap with
    the original patch is intentional -- adjacency is identity-only."""
    from SilkWorkflowOps import create_edge, create_patch
    rest = []
    for i, key in enumerate(("right", "top", "left")):
        sk = _line_sketch(doc, "%s_sk%d" % (name, i), _SQUARE[key])
        rest.append(create_edge(sk, name="%s_%s" % (name, key)))
    return create_patch([shared_edge] + rest, name=name)


def _stray_edge(doc, name="Stray"):
    from SilkWorkflowOps import create_edge
    sk = _line_sketch(doc, name + "_sk",
                      [(200, 0, 0), (216.7, 0, 0), (233.3, 0, 0), (250, 0, 0)])
    return create_edge(sk, name=name)


def _blend_objects(doc):
    return [o for o in doc.Objects
            if getattr(o, "object_type", None) in ("Blend", "BlendStrip")]


def _splits(p):
    return (sorted(float(v) for v in (list(getattr(p, "USplits", None) or []))),
            sorted(float(v) for v in (list(getattr(p, "VSplits", None) or []))))


# ---- the two-seams (closed-ring) fixture ----------------------------------

def _arch_sketch(doc, name, pos_y, local_pts):
    """A bulging 3L edge in the vertical plane y=pos_y: local (a,b,0)
    maps to global (a, pos_y, b) via rotX(90) sketch Placement."""
    sk = doc.addObject("Sketcher::SketchObject", name)
    sk.Placement = FreeCAD.Placement(
        Vector(0, pos_y, 0), FreeCAD.Rotation(Vector(1, 0, 0), 90))
    for (a, b), (c, d) in zip(local_pts, local_pts[1:]):
        sk.addGeometry(Part.LineSegment(Vector(a, b, 0), Vector(c, d, 0)))
    doc.recompute()
    return sk


def _build_tube(doc):
    """Two patches sharing TWO Edge objects (the #44 two-seams risk
    case): TubeA = the flat square panel; TubeB = an arched panel over
    the same footprint, sharing TubeA's left and right side edges.

    Returns (pa, pb, s_left, s_right). Seam labels (derived from the
    corner walks): s_right is "V1" on A and "U1" on B; s_left is "V0"
    on A and "U0" on B; the matched corner pairs are [(1,2),(2,3)] and
    [(3,0),(0,1)] respectively."""
    from SilkWorkflowOps import create_edge, create_patch
    a_edges = _square_edges(doc, "TubeA")
    s_right, s_left = a_edges[1], a_edges[3]
    arch_bottom = create_edge(_arch_sketch(
        doc, "ArchB", 0.0, [(0, 0), (16.7, 20), (33.3, 20), (50, 0)]),
        name="ArchBottom")
    arch_top = create_edge(_arch_sketch(
        doc, "ArchT", 50.0, [(50, 0), (33.3, 20), (16.7, 20), (0, 0)]),
        name="ArchTop")
    pa = create_patch(a_edges, name="TubeA")
    pb = create_patch([s_left, arch_bottom, s_right, arch_top], name="TubeB")
    return pa, pb, s_left, s_right


def _pinned_reference_rows(pa, pb, ea, eb, pairs):
    """Independently derive the 4 (l_rev, rc) blend-row pairs for a
    SEAM-PINNED (ea, eb, pairs) seam -- the same derivation shape as
    SilkChecks._blend_reference_rows, but with the seam fixed instead of
    auto-detected (the auto-detect re-derives the FIRST matching corner
    pair, which matters for the two-shared-edges case)."""
    from SilkMachinery import band_cells
    ss_a = 0 if ea[1] == "0" else 1
    ss_b = 0 if eb[1] == "0" else 1

    def strip(p, et, ss):
        idxs = band_cells(p, et, ss)
        assert len(idxs) == 1, "band %s/%s covers %r" % (et, ss, idxs)
        return list(p.Proxy._subgrids[idxs[0]])

    sga = strip(pa, ea, ss_a)
    sgb = strip(pb, eb, ss_b)
    cmap = {"U0": {0: 0, 1: 3}, "U1": {2: 3, 3: 0},
            "V0": {0: 0, 3: 3}, "V1": {1: 0, 2: 3}}
    va = range(4) if ss_a == 0 else range(3, -1, -1)
    vb = range(4) if ss_b == 0 else range(3, -1, -1)
    rows = []
    for li in range(4):
        if ea[0] == "U":
            l_rev = list(reversed([sga[li * 4 + v] for v in va]))
        else:
            l_rev = list(reversed([sga[v * 4 + li] for v in va]))
        for lc_idx, rc_idx in pairs:
            rb = cmap[eb].get(rc_idx)
            if rb is not None and li == cmap[ea].get(lc_idx):
                ri = rb
                break
        else:
            ri = 3 - li
        if eb[0] == "U":
            rc = [sgb[ri * 4 + v] for v in vb]
        else:
            rc = [sgb[v * 4 + ri] for v in vb]
        rows.append((l_rev, rc))
    return rows


def _pinned_reference_poles(rows):
    """The 24-pole blend grid implied by _pinned_reference_rows -- the
    reference handed to check_blend's B4, derived here independently of
    the oracle."""
    import ArachNURBS as AN
    poles = []
    for l_rev, rc in rows:
        poles.extend(AN.blend_poly_2x4_1x6(
            l_rev, [1.0] * 4, rc, [1.0] * 4, 2.0, 2.0, 2.0, 2.0)[0])
    return poles


def _matches_pinned_reference(blend, rows):
    import ArachNURBS as AN
    poles = list(blend.Poles or [])
    if len(poles) != 24:
        return None
    dev = 0.0
    for i, (l_rev, rc) in enumerate(rows):
        ref = AN.blend_poly_2x4_1x6(
            l_rev, [1.0] * 4, rc, [1.0] * 4, 2.0, 2.0, 2.0, 2.0)[0]
        for j in range(6):
            dev = max(dev, (poles[i * 6 + j] - ref[j]).Length)
    return dev


# ---- resolve_seam ----------------------------------------------------------

def test_resolve_seam_two_patch_pair(doc):
    """2 patches / 1 shared edge -> resolve_seam returns exactly that
    pair in document order, with no console errors."""
    from Tests.corner_model import build_corner_pair
    from SilkWorkflowOps import resolve_seam

    model = build_corner_pair(doc)
    with _Capture() as cap:
        pair = resolve_seam(model["edges"]["E_s12"])

    errors = []
    checks = []
    if pair is None:
        errors.append("resolve_seam returned None on a valid shared edge")
    else:
        pa, pb = pair
        ok = (pa is model["patches"]["Patch44"]
              and pb is model["patches"]["Patch001"])
        checks.append("pair = (%s, %s): %s" % (pa.Name, pb.Name,
                                               "OK" if ok else "FAIL"))
        if not ok:
            errors.append("resolve_seam returned (%s, %s), want "
                          "(Patch44, Patch001)" % (pa.Name, pb.Name))
    errors += ["console error: %s" % e for e in cap.errors]
    return {"pass": not errors, "errors": errors, "checks": checks}


def test_resolve_seam_identity_only_no_geometric_fallback(doc):
    """A fully coincident but UNLINKED second patch is not adjacent:
    resolve_seam refuses each edge with the 1-patch message (the
    glossary's coincident boundary is never a seam)."""
    from SilkWorkflowOps import resolve_seam

    a = _square_patch(doc, "A")
    d = _square_patch(doc, "D")  # same geometry, distinct Edge objects

    errors, checks = [], []
    with _Capture() as cap:
        pair_a = resolve_seam(a.Edges[0])
        pair_d = resolve_seam(d.Edges[0])
    if pair_a is not None or pair_d is not None:
        errors.append("coincident unlinked patch treated as adjacent "
                      "(%r, %r)" % (pair_a, pair_d))
    checks.append("coincident-but-unlinked patches refused on both sides")
    if not any("adjacent patch" in e for e in cap.errors):
        errors.append("expected the 1-patch refusal message, got: %s"
                      % cap.errors)
    checks.append("refusal messages: %s" % [e.strip() for e in cap.errors])
    return {"pass": not errors, "errors": errors, "checks": checks}


def test_resolve_seam_refuses_unreferenced_edge(doc):
    """An edge no patch references -> None + 'not used by any patch'."""
    from SilkWorkflowOps import resolve_seam

    stray = _stray_edge(doc)
    errors, checks = [], []
    with _Capture() as cap:
        pair = resolve_seam(stray)
    if pair is not None:
        errors.append("resolve_seam returned %r on an unreferenced edge" % (pair,))
    if not any("not used by any patch" in e for e in cap.errors):
        errors.append("expected the 0-patch refusal message, got: %s"
                      % cap.errors)
    checks.append("unreferenced edge -> None + console error")
    return {"pass": not errors, "errors": errors, "checks": checks}


def test_resolve_seam_refuses_single_patch_edge(doc):
    """An edge referenced by exactly one patch -> None + 'needs an
    adjacent patch'."""
    from SilkWorkflowOps import resolve_seam

    a = _square_patch(doc, "A")
    errors, checks = [], []
    with _Capture() as cap:
        pair = resolve_seam(a.Edges[1])
    if pair is not None:
        errors.append("resolve_seam returned %r on a 1-patch edge" % (pair,))
    if not any("adjacent patch" in e for e in cap.errors):
        errors.append("expected the 1-patch refusal message, got: %s"
                      % cap.errors)
    checks.append("1-patch edge -> None + console error")
    return {"pass": not errors, "errors": errors, "checks": checks}


def test_resolve_seam_refuses_nonmanifold_edge(doc):
    """An edge referenced by 3 patches -> None + the non-manifold
    message pointing at the corner-fill track."""
    from SilkWorkflowOps import resolve_seam

    a = _square_patch(doc, "A")
    e0 = a.Edges[0]
    _patch_sharing(doc, e0, "B")
    _patch_sharing(doc, e0, "C")

    errors, checks = [], []
    with _Capture() as cap:
        pair = resolve_seam(e0)
    if pair is not None:
        errors.append("resolve_seam returned %r on a 3-patch edge" % (pair,))
    if not any("not a blendable seam" in e for e in cap.errors):
        errors.append("expected the non-manifold refusal message, got: %s"
                      % cap.errors)
    if not any("corner" in e for e in cap.errors):
        errors.append("non-manifold message does not point at the corner "
                      "track; got: %s" % cap.errors)
    checks.append("3-patch edge -> None + non-manifold console error")
    return {"pass": not errors, "errors": errors, "checks": checks}


# ---- create_blend_by_edge --------------------------------------------------

def test_create_blend_by_edge_full_oracle(doc):
    """by-edge create on the ground-truth chain's shared edge: the
    created Blend passes the FULL check_blend oracle including the B4
    24-pole match against the stored fixture blend, no console errors."""
    import os
    import SilkWorkflowOps as ops
    from SilkChecks import check_blend

    fixture_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "Resources", "Test_files",
                                "Silk_Workflow.FCStd")
    fixture = FreeCAD.openDocument(fixture_path)
    FreeCAD.setActiveDocument(doc.Name)
    try:
        from Tests.test_blend_stage import _build_gt_chain
        pa, pb, g = _build_gt_chain(doc, fixture)
        with _Capture() as cap:
            blend = ops.create_blend_by_edge(g["E_Shr"], name="BlendSeam")

        errors, checks = [], []
        if getattr(blend, "object_type", None) != "Blend":
            errors.append("by-edge create did not produce a unified Blend "
                          "(%r)" % getattr(blend, "object_type", None))
        if blend is not None and getattr(blend, "Edge", None) is not g["E_Shr"]:
            errors.append("created blend does not link the pinned edge "
                          "(Edge=%r)" % getattr(blend, "Edge", None))
        results = check_blend(blend, pa, pb,
                              reference_poles=fixture.BlendStrip.Poles)
        for name, ok, detail in results:
            checks.append("%s: %s (%s)" % (name, "ok" if ok else "FAIL",
                                           detail))
            if not ok:
                errors.append("check_blend %s: %s" % (name, detail))
        errors += ["console error: %s" % e for e in cap.errors]
    finally:
        FreeCAD.closeDocument(fixture.Name)
        FreeCAD.setActiveDocument(doc.Name)
    return {"pass": not errors, "errors": errors, "checks": checks}


def test_create_blend_by_edge_idempotent(doc):
    """Calling by-edge create twice on the same edge is a no-op: the
    second call returns the FIRST blend, prints a message naming it,
    and creates no second blend object."""
    import os
    import SilkWorkflowOps as ops

    fixture_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "Resources", "Test_files",
                                "Silk_Workflow.FCStd")
    fixture = FreeCAD.openDocument(fixture_path)
    FreeCAD.setActiveDocument(doc.Name)
    try:
        from Tests.test_blend_stage import _build_gt_chain
        _, _, g = _build_gt_chain(doc, fixture)
        with _Capture() as cap1:
            first = ops.create_blend_by_edge(g["E_Shr"], name="BlendSeam")
        with _Capture() as cap2:
            second = ops.create_blend_by_edge(g["E_Shr"], name="BlendAgain")

        errors, checks = [], []
        if second is not first:
            errors.append("second by-edge call returned %r, want the first "
                          "blend %r (no-op)" % (second, first))
        n_blends = len(_blend_objects(doc))
        if n_blends != 1:
            errors.append("document holds %d blend objects after the "
                          "idempotent second call, want 1" % n_blends)
        checks.append("second call returned the first blend; %d blend "
                      "object(s) in doc" % n_blends)
        named = [m for m in cap2.messages if first.Name in m]
        if not named:
            errors.append("no message naming the existing blend %s; "
                          "got: %s" % (first.Name, cap2.messages))
        checks.append("no-op message names %s: %r" % (first.Name,
                                                      named[:1]))
        errors += ["console error: %s" % e for e in cap1.errors + cap2.errors]
    finally:
        FreeCAD.closeDocument(fixture.Name)
        FreeCAD.setActiveDocument(doc.Name)
    return {"pass": not errors, "errors": errors, "checks": checks}


def test_create_blend_by_edge_refusals_leave_no_side_effects(doc):
    """Every refuse path (0 / 1 / 3+ referencing patches) returns None
    with a console error and leaves the document untouched: no blend
    object, no USplits/VSplits written on any patch."""
    import SilkWorkflowOps as ops

    a = _square_patch(doc, "A")
    e0 = a.Edges[0]
    _patch_sharing(doc, e0, "B")
    _patch_sharing(doc, e0, "C")
    stray = _stray_edge(doc)

    errors, checks = [], []
    with _Capture() as cap:
        r0 = ops.create_blend_by_edge(stray, name="Blend0")
        r1 = ops.create_blend_by_edge(a.Edges[1], name="Blend1")
        r3 = ops.create_blend_by_edge(e0, name="Blend3")
    for label, r in (("0-patch", r0), ("1-patch", r1), ("3-patch", r3)):
        if r is not None:
            errors.append("%s refusal returned %r, want None" % (label, r))
    checks.append("all three refusals returned None")
    n_blends = len(_blend_objects(doc))
    if n_blends:
        errors.append("refusals created %d blend object(s)" % n_blends)
    for pname in ("A", "B", "C"):
        p = doc.getObject(pname)
        u, v = _splits(p)
        if u or v:
            errors.append("refusals wrote splits on %s (U=%s V=%s)"
                          % (pname, u, v))
    checks.append("no blend objects, no splits on A/B/C")
    for want in ("not used by any patch", "adjacent patch",
                 "not a blendable seam"):
        if not any(want in e for e in cap.errors):
            errors.append("missing refusal message %r; got: %s"
                          % (want, cap.errors))
    checks.append("all three refusal messages emitted")
    return {"pass": not errors, "errors": errors, "checks": checks}


# ---- seam_inventory --------------------------------------------------------

def test_seam_inventory_statuses(doc):
    """blendable before a blend exists, blended (naming it) after; one
    entry per shared edge, non-shared edges get no entry."""
    import SilkWorkflowOps as ops

    a = _square_patch(doc, "A")
    e0 = a.Edges[0]
    b = _patch_sharing(doc, e0, "B")  # shares ONLY e0 with A

    errors, checks = [], []

    inv = ops.seam_inventory()
    if len(inv) != 1:
        errors.append("inventory has %d entries, want 1 (only e0 is "
                      "shared)" % len(inv))
        return {"pass": False, "errors": errors, "checks": checks}
    e = inv[0]
    ok = (e["edge"] is e0
          and e["patch_a"] is a and e["patch_b"] is b
          and e["status"] == "blendable" and e["blend"] is None)
    checks.append("before: %s status=%s blend=%s: %s"
                  % (e["edge"].Name, e["status"], e["blend"],
                     "OK" if ok else "FAIL"))
    if not ok:
        errors.append("unexpected pre-blend entry: %r" % {k: e[k] for k in e})

    with _Capture() as cap:
        blend = ops.create_blend_by_edge(e0)
    errors += ["console error during blend create: %s" % x
               for x in cap.errors]

    inv = ops.seam_inventory()
    if len(inv) != 1:
        errors.append("inventory has %d entries after blending, want 1"
                      % len(inv))
        return {"pass": False, "errors": errors, "checks": checks}
    e = inv[0]
    ok = (e["status"] == "blended" and e["blend"] is blend)
    checks.append("after: status=%s blend=%s: %s"
                  % (e["status"], getattr(e["blend"], "Name", None),
                     "OK" if ok else "FAIL"))
    if not ok:
        errors.append("unexpected post-blend entry: status=%r blend=%r"
                      % (e["status"], e["blend"]))
    return {"pass": not errors, "errors": errors, "checks": checks}


def test_seam_inventory_blocked_nonmanifold(doc):
    """An edge referenced by 3+ patches is one 'blocked' entry (with the
    first two refs as the pair) -- and nothing else in the document
    produces an entry."""
    import SilkWorkflowOps as ops

    a = _square_patch(doc, "A")
    e0 = a.Edges[0]
    b = _patch_sharing(doc, e0, "B")
    _patch_sharing(doc, e0, "C")

    errors, checks = [], []
    inv = ops.seam_inventory()
    if len(inv) != 1:
        errors.append("inventory has %d entries, want 1 (only e0 is "
                      "shared)" % len(inv))
        return {"pass": False, "errors": errors, "checks": checks}
    e = inv[0]
    ok = (e["edge"] is e0 and e["status"] == "blocked"
          and e["blend"] is None
          and e["patch_a"] is a and e["patch_b"] is b)
    checks.append("non-manifold edge: status=%s pair=(%s, %s): %s"
                  % (e["status"], e["patch_a"].Name, e["patch_b"].Name,
                     "OK" if ok else "FAIL"))
    if not ok:
        errors.append("unexpected blocked entry: %r" % {k: e[k] for k in e})
    return {"pass": not errors, "errors": errors, "checks": checks}


# ---- the two-shared-edges centerpiece --------------------------------------

def test_two_shared_edges_pin_picks_the_pinned_seam(doc):
    """#44 risk verification: two patches sharing TWO Edge objects.
    run_blend derives the seam from the pinned Edge's endpoint poles
    (_seam_from_edge), so by-edge blending the SECOND seam:
      - writes only that seam's band split (A.USplits == [0.9], NOT the
        [0.1] that re-detecting the first seam or the phantom
        coincident-corner seam would write),
      - lands its 24 poles on that seam's bands (1e-6 match against an
        independently derived, seam-pinned reference),
      - coexists with a first-seam blend (distinct objects, distinct
        bands), and per-seam idempotency holds (third call returns the
        second-seam blend).
    check_blend's structural + B3 must be green; its B1/B2 flag here
    because the oracle's reference derivation auto-detects the seam and
    has no pin -- documented, not asserted green."""
    import SilkWorkflowOps as ops
    from SilkChecks import check_blend

    pa, pb, s_left, s_right = _build_tube(doc)
    errors, checks = [], []

    with _Capture() as cap:
        b_right = ops.create_blend_by_edge(s_right, name="BlendRight")
    errors += ["console error: %s" % e for e in cap.errors]

    if getattr(b_right, "object_type", None) != "Blend":
        errors.append("by-edge create did not produce a Blend (%r)"
                      % getattr(b_right, "object_type", None))
        return {"pass": False, "errors": errors, "checks": checks}
    if getattr(b_right, "Edge", None) is not s_right:
        errors.append("blend does not link the pinned second seam "
                      "(Edge=%r)" % getattr(b_right, "Edge", None))
    if len(b_right.Poles or []) != 24:
        errors.append("second-seam blend has %d poles, want 24"
                      % len(b_right.Poles or []))
        return {"pass": False, "errors": errors, "checks": checks}

    # Which side: the second seam is A's "V1" (band at USplits 0.9).
    # Re-detecting the first seam ("V0") would write USplits [0.1]; the
    # phantom coincident-corner front seam ("U0") would write VSplits.
    u_a, v_a = _splits(pa)
    u_b, v_b = _splits(pb)
    if u_a != [0.9] or v_a or u_b or v_b != [0.9]:
        errors.append("second-seam splits A(U=%s,V=%s) B(U=%s,V=%s), "
                      "want A U=[0.9], B V=[0.9]" % (u_a, v_a, u_b, v_b))
    checks.append("band split written on the pinned seam's side: "
                  "A(U=%s,V=%s) B(U=%s,V=%s)" % (u_a, v_a, u_b, v_b))

    rows = _pinned_reference_rows(pa, pb, "V1", "U1", [(1, 2), (2, 3)])
    dev = _matches_pinned_reference(b_right, rows)
    if dev is None or dev > 1e-6:
        errors.append("second-seam blend poles deviate %s from the pinned "
                      "seam-2 reference (want <= 1e-6)" % dev)
    checks.append("24 poles match the seam-pinned reference (max dev "
                  "%.2e)" % dev)

    # The pinned seam is also the FULL ORACLE's seam: since #49,
    # check_blend takes an optional `edge=` pin mirroring
    # create_blend's edge= contract, so the whole oracle (structural,
    # B1, B2, B3, B4) goes green on the second-seam blend instead of
    # flagging a correct blend because it re-derived the first seam.
    res = {n: (ok, d) for n, ok, d in check_blend(
        b_right, pa, pb, reference_poles=_pinned_reference_poles(rows),
        edge=s_right)}
    for n in ("structural", "B1_c0_seams", "B2_c1_tangents",
              "B3_surface_valid", "B4_pole_match"):
        if not res.get(n, (False,))[0]:
            errors.append("pinned check_blend %s not green: %s"
                          % (n, res.get(n, (False, "missing"))))
    checks.append("pinned check_blend green on all of %s"
                  % ", ".join("%s (%s)" % (n, res[n][1]) for n in
                              ("structural", "B1_c0_seams",
                               "B2_c1_tangents", "B3_surface_valid",
                               "B4_pole_match") if n in res))

    # Unpinned the oracle still auto-detects the seam (unchanged #49
    # behaviour) and therefore still flags the second-seam blend. That
    # is the pin's raison d'etre; reported, not asserted.
    unpinned = {n: ok for n, ok, _ in check_blend(b_right, pa, pb)}
    checks.append("unpinned check_blend (no pin, auto-detect): %s"
                  % ", ".join("%s=%s" % (n, "ok" if ok else "flag")
                              for n, ok in unpinned.items()))

    # Both seams individually blendable: a first-seam blend coexists.
    with _Capture() as cap:
        b_left = ops.create_blend_by_edge(s_left, name="BlendLeft")
    errors += ["console error: %s" % e for e in cap.errors]
    if b_left is b_right or b_left is None:
        errors.append("first-seam by-edge did not create a distinct "
                      "blend (%r)" % b_left)
        return {"pass": False, "errors": errors, "checks": checks}
    if len(b_left.Poles or []) != 24:
        errors.append("first-seam blend has %d poles, want 24"
                      % len(b_left.Poles or []))
    u_a, v_a = _splits(pa)
    if u_a != [0.1, 0.9] or v_a:
        errors.append("after both seams A(U=%s,V=%s), want U=[0.1,0.9]"
                      % (u_a, v_a))
    checks.append("both seams blended: A(U=%s,V=%s), distinct blends "
                  "%s + %s" % (u_a, v_a, b_left.Name, b_right.Name))

    rows = _pinned_reference_rows(pa, pb, "V0", "U0", [(3, 0), (0, 1)])
    dev = _matches_pinned_reference(b_left, rows)
    if dev is None or dev > 1e-6:
        errors.append("first-seam blend poles deviate %s from the pinned "
                      "seam-1 reference (want <= 1e-6)" % dev)
    checks.append("first-seam poles match the seam-pinned reference "
                  "(max dev %.2e)" % dev)

    # The first seam is fully oracle-checkable too, pinned (this is the
    # seam the unpinned auto-detect happens to pick, so pin and
    # auto-detect must agree).
    res_l = {n: (ok, d) for n, ok, d in check_blend(
        b_left, pa, pb, reference_poles=_pinned_reference_poles(rows),
        edge=s_left)}
    for n in ("structural", "B1_c0_seams", "B2_c1_tangents",
              "B3_surface_valid", "B4_pole_match"):
        if not res_l.get(n, (False,))[0]:
            errors.append("pinned check_blend (first seam) %s not green: %s"
                          % (n, res_l.get(n, (False, "missing"))))
    checks.append("pinned check_blend green on the first-seam blend too")

    # The two blends sit on different bands: their poles must differ.
    dmax = max((p - q).Length for p, q in zip(b_left.Poles, b_right.Poles))
    if dmax <= 1e-6:
        errors.append("the two same-pair blends have identical poles "
                      "(dev %.3e) -- the second landed on the first "
                      "seam" % dmax)
    checks.append("same-pair blends occupy different bands (max pole "
                  "diff %.3f)" % dmax)

    # Per-seam idempotency: re-calling either seam returns its own blend.
    with _Capture() as cap:
        again_right = ops.create_blend_by_edge(s_right, name="AgainR")
        again_left = ops.create_blend_by_edge(s_left, name="AgainL")
    errors += ["console error: %s" % e for e in cap.errors]
    if again_right is not b_right or again_left is not b_left:
        errors.append("per-seam idempotency broken: (%r, %r)"
                      % (again_right, again_left))
    n_blends = len(_blend_objects(doc))
    if n_blends != 2:
        errors.append("%d blend objects after the idempotent calls, "
                      "want 2" % n_blends)
    checks.append("per-seam idempotency: %d blend objects kept" % n_blends)

    # Inventory: one entry per shared edge, each naming its own blend.
    inv = {e["edge"].Name: e for e in ops.seam_inventory()}
    for ename, want in (("TubeA_right", b_right), ("TubeA_left", b_left)):
        e = inv.get(ename)
        if e is None or e["status"] != "blended" or e["blend"] is not want:
            errors.append("inventory entry for %s wrong: %r"
                          % (ename, None if e is None else
                             (e["status"], getattr(e["blend"], "Name", None))))
    checks.append("inventory: both seams 'blended', each naming its own "
                  "blend")
    return {"pass": not errors, "errors": errors, "checks": checks}


ALL_TESTS = [
    test_resolve_seam_two_patch_pair,
    test_resolve_seam_identity_only_no_geometric_fallback,
    test_resolve_seam_refuses_unreferenced_edge,
    test_resolve_seam_refuses_single_patch_edge,
    test_resolve_seam_refuses_nonmanifold_edge,
    test_create_blend_by_edge_full_oracle,
    test_create_blend_by_edge_idempotent,
    test_create_blend_by_edge_refusals_leave_no_side_effects,
    test_seam_inventory_statuses,
    test_seam_inventory_blocked_nonmanifold,
    test_two_shared_edges_pin_picks_the_pinned_seam,
]
