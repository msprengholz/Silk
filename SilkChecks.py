"""
SilkChecks — the correctness oracle for workflow objects.

Each check_* function RETURNS a list of (name, ok, detail) tuples and
never raises: "is this correct?" is a query; deciding what a failure
means is the caller's job (tests assert on it, the future wizard will
display it).

Ticket #18: check_edge (structural + E1-E4). check_patch (the
unified patch oracle, dispatching on the edge count) is the only
patch oracle since #42 (the legacy check_patch44 / check_patch33
are gone with the per-fill types); check_blend with #20.

Check menu (locked in #14):
  E1  endpoints anchored to the driving sketch
  E2  pole order without jumps (a pole stays near its neighbors)
  E3  control polygon does not self-intersect
  E4  curve arc length bounded relative to chord + curve is valid
Patches (P1-P4):
  P1  corner poles sit on the shared corners of the 4-edge loop
  P2  boundary row/col pole sets match their driving edges
  P3  the built surface's normal field is consistently oriented
      (a folded or flipped net shows up as a normal flip on the
      evaluated surface -- robust on curved grids, unlike a raw
      control-net cross test which false-positives on twists)
  P4  surface is valid and free of self-intersection
Blends (B1-B4):
  B1  C0 at both inner boundaries: each blend row's outer poles sit on
      the patches' strip-curve endpoints (1e-6)
  B2  C1 construction at both inner boundaries: each row's first/last
      tangent poles match the strip-curve tangents under the documented
      2x tangent scale (1e-6)
  B3  blend surface valid + no self-intersection + normal field coherent
  B4  full 24-pole match against a provided reference (optional)
check_blend takes an optional `edge=` seam pin (#49): with it, B1/B2
derive their reference rows from that Edge's endpoint poles (the seam
the blend used) instead of auto-detecting the first matching corner
pair -- which is what makes a SECOND seam on a pair sharing two edges
(closed-ring builds) checkable. Without it, behaviour is unchanged.
Corner blends (CB1-CB4, #28; the fill is the subgrid chain since #91):
  CB1 C0 boundary: the 6x6 grid's boundary sides match the ring
      strips' corner-end rows, orientation-independent (1e-6); a
      3-valent corner has three ring strips and covers three sides
      (the fourth is the derived triangular member's)
  CB2 interior fill: all 36 poles match the legacy subgrid chain
      (SubGrid33_2Grid64 x4 -> ControlGrid66_4Sub) fed canonical grids
      the oracle canonicalizes ITSELF (#120) -- the ring order, the
      junction-end rows and the across-seam columns are the oracle's own
      mirror, so a wrong canonical grid moves one side only (1e-6)
  CB3 corner surface valid + no self-intersection + normal field coherent
  CB4 full 36-pole match against a provided reference (optional)

Tolerances (spec #16): poles 1e-6. Weights are carried, not assumed:
`blend_poly_2x4_1x6` can emit rational weights, so the corner's own
weights are only required to be positive.

MIRROR, DO NOT IMPORT: several helpers here deliberately re-derive the
object code's tables (_detect_seam, _pinned_seam, _oracle_band_cells,
_oracle_side_and_end, _oracle_corner_cells, _oracle_corner_ring,
_oracle_shared_corner, _oracle_orient_ring_columns) instead of importing
them. An oracle that calls the function under test proves nothing — a
bug in that function would satisfy the check. Every mirror says so where
it is defined, and #120 closed the last two places that broke the rule
(CB1's refusal message and CB2's canonical grids).
"""

import FreeCAD
import Part

TOL = 1e-6

# A sane boundary edge follows its chord; a looped/mangled one does not.
# A legitimate 3-corner U-edge (two 90-degree turns) measures 3.36, so the
# limit must stay above that; looped cubics run an order of magnitude higher.
ARC_CHORD_LIMIT = 4.0

# A pole may be at most this factor farther from its neighbor than from
# its diagonal skip -- beyond that, the order jumped.
ORDER_FACTOR = 1.05


def _dist(a, b):
    return (a - b).Length


def _bezier4_point(poles, weights, t):
    """The rational cubic Bezier through `poles` / `weights` at `t`.

    Bernstein basis in homogeneous coordinates, divided through -- i.e. the
    curve the 4 (pole, weight) pairs actually describe, which is NOT the
    curve through the poles alone whenever the weights differ from 1
    (#107). Used by B1 to compare boundary CURVES, not pole lists.
    """
    b = ((1.0 - t) ** 3, 3.0 * t * (1.0 - t) ** 2,
         3.0 * t * t * (1.0 - t), t ** 3)
    num = FreeCAD.Vector(0.0, 0.0, 0.0)
    den = 0.0
    for i in range(4):
        w = float(weights[i]) * b[i]
        num += poles[i] * w
        den += w
    return num * (1.0 / den)


def _seg_cross(a, b, c, d, tol=1e-7):
    """Do segments ab and cd cross, touch, or overlap? (3D-safe distance test.)"""
    try:
        dist, _, _ = Part.makeLine(a, b).distToShape(Part.makeLine(c, d))
    except Exception:
        return False
    return dist <= tol


def _sketch_endpoints(sketch):
    """(first, last) point of the visible geometry, or None if not a
    pure line-segment sketch (the 3L case is what E1 anchors against).
    Points are returned in document coordinates (sketch Placement
    applied) to match the edge's pole coordinates."""
    lines = [
        geom for i, geom in enumerate(sketch.Geometry)
        if not sketch.getConstruction(i)
    ]
    if not lines or any(g.TypeId != "Part::GeomLineSegment" for g in lines):
        return None
    pl = sketch.Placement
    return pl.multVec(lines[0].StartPoint), pl.multVec(lines[-1].EndPoint)


def _sketch_plane_normal(sketch):
    """World-space unit normal of a sketch plane. Mirrors the object
    code's own normal (SilkEdge._plane_normal) but is re-derived HERE on
    purpose -- like the other helpers this file mirrors, the oracle must
    not call the function under test (see the MIRROR note above)."""
    try:
        n = sketch.Placement.Rotation.multVec(FreeCAD.Vector(0, 0, 1))
    except Exception:
        return None
    if n.Length <= 0:
        return None
    n.normalize()
    return n


def _in_plane_dist(p, q, n):
    """Distance from p to q after dropping both points' component along
    the plane normal n."""
    d = p - q
    return (d - n * d.dot(n)).Length


def _check_edge(edge):
    results = []

    # structural
    errs = []
    if getattr(edge, "object_type", None) != "Edge":
        errs.append("object_type=%r" % getattr(edge, "object_type", None))
    poles = list(edge.Poles)
    if len(poles) != 4:
        errs.append("%d poles (want 4)" % len(poles))
    weights = list(edge.Weights)
    if len(weights) != 4:
        errs.append("%d weights (want 4)" % len(weights))
    elif any(abs(w - 1.0) > 1e-12 for w in weights):
        errs.append("weights not all 1.0: %s" % weights)
    if not edge.Sketches:
        errs.append("no linked sketches")
    if not edge.Legs:
        errs.append("no control legs")
    if edge.Shape.isNull():
        errs.append("empty Shape")
    results.append((
        "structural", not errs,
        "; ".join(errs) if errs else "object_type, links, 4 poles/weights, legs, shape",
    ))

    if len(poles) != 4:
        return results

    # E1: endpoints anchored to the driving sketch
    endpoints = _sketch_endpoints(edge.Sketches[0]) if edge.Sketches else None
    if endpoints is None:
        results.append(("E1_endpoint_anchoring", True,
                        "sketch not pure 3L lines; anchoring not checked"))
    else:
        first, last = endpoints
        # #90: a plan + elevation Edge lifts each plan pole off the plan
        # plane by the elevation height, so a pole is anchored when its
        # IN-PLANE projection meets the plan sketch's endpoint. A
        # legitimate raised end (nonzero elevation height at an end) must
        # not be red -- the height belongs to the elevation. The plan is
        # Sketches[0]; a 2N edge's first sketch is a circle + line, whose
        # endpoints read None above, so this path stays single-profile.
        n = None
        if len(list(edge.Sketches)) == 2:
            n = _sketch_plane_normal(edge.Sketches[0])
        if n is not None:
            d0 = _in_plane_dist(poles[0], first, n)
            d3 = _in_plane_dist(poles[3], last, n)
            basis = "in-plane end"
        else:
            d0 = _dist(poles[0], first)
            d3 = _dist(poles[3], last)
            basis = "end"
        ok = d0 <= TOL and d3 <= TOL
        results.append((
            "E1_endpoint_anchoring", ok,
            "%s deltas vs sketch: %.2e / %.2e (tol %.0e)" % (basis, d0, d3, TOL),
        ))

    # E2: pole order without jumps. Edges are open curves (sketch start
    # to sketch end), so only the 3 consecutive pairs are continuity
    # constraints -- the p3->p0 wrap is not (it is the closing chord of
    # an open edge and can legitimately be long).
    bad = []
    for i in range(3):
        step = _dist(poles[i], poles[i + 1])
        skip = _dist(poles[i], poles[i + 2] if i < 2 else poles[0])
        if step > ORDER_FACTOR * max(skip, TOL):
            bad.append("p%d->p%d=%.3f > %.2fx p%d->p%d=%.3f"
                       % (i, i + 1, step, ORDER_FACTOR, i, i + 2, skip))
    results.append((
        "E2_pole_order", not bad,
        "; ".join(bad) if bad else "consecutive steps stay shorter than diagonal skips",
    ))

    # E3: control polygon does not self-intersect. The control polygon of
    # an open edge is the 3 legs p0p1, p1p2, p2p3 -- the only
    # non-adjacent pair is (p0p1, p2p3). The p3p0 closing chord is not a
    # leg and must not be tested (it false-positives on tight U-edges).
    crossings = []
    if _seg_cross(poles[0], poles[1], poles[2], poles[3]):
        crossings.append("p0p1 x p2p3")
    results.append((
        "E3_polygon_self_intersection", not crossings,
        "crossings: " + ", ".join(crossings) if crossings else "no crossings",
    ))

    # E4: arc length bounded relative to chord + valid curve
    try:
        curve = Part.BSplineCurve()
        curve.buildFromPoles(poles)
        shape = curve.toShape()
        valid = shape.isValid()
        length = shape.Length
    except Exception as e:
        valid, length = False, float("nan")
    chord = _dist(poles[0], poles[3])
    if chord <= TOL:
        ok, detail = False, "degenerate chord %.2e" % chord
    else:
        ratio = length / chord
        ok = valid and ratio <= ARC_CHORD_LIMIT
        detail = "length/chord = %.2f (limit %.1f), curve valid=%s" % (
            ratio, ARC_CHORD_LIMIT, valid)
    results.append(("E4_arc_chord_and_valid", ok, detail))

    return results


def check_edge(edge):
    """Check a SilkEdge object. Returns [(name, ok, detail), ...]; never raises."""
    try:
        return _check_edge(edge)
    except Exception as e:
        return [("structural", False, "oracle error: %r" % e)]


def _multiset_match_within(poles, targets, tol):
    """Every pole in `poles` matched to a distinct target within tol."""
    pool = list(targets)
    for p in poles:
        best_i, best_d = -1, None
        for i, q in enumerate(pool):
            d = _dist(p, q)
            if best_d is None or d < best_d:
                best_i, best_d = i, d
        if best_d is None or best_d > tol:
            return False
        del pool[best_i]
    return True


def _build_bicubic(poles, weights):
    """Bicubic Bezier surface from a 4x4 pole grid (mirrors Patch44).
    Used by P3 to evaluate the surface its control net defines."""
    surf = Part.BSplineSurface()
    surf.increaseDegree(3, 3)
    for knot, mult in [(0.0, 4), (1.0, 4)]:
        surf.insertUKnot(knot, mult, 1e-7)
        surf.insertVKnot(knot, mult, 1e-7)
    for r in range(4):
        for c in range(4):
            surf.setPole(c + 1, r + 1, poles[r * 4 + c], weights[r * 4 + c])
    return surf


def _normal_field_flips(surf, n=9):
    """Neighbour-consistency check on a surface's normal field.

    Samples surf.normal(u, v) on an n x n parametric grid (cell centres
    in knot space [0,1]^2) and compares each sample with its left and
    upper neighbours. A genuine fold/flip appears as a sign flip between
    adjacent samples; a legitimate large normal rotation (long curved
    strips, curved patches) does not, so this is robust where a
    fixed-reference dot test false-positives.

    Returns (flips, any_normal): flips is a list of "u=..,v=.." strings
    (empty = consistent), any_normal is False when every sample was
    degenerate (degenerate surface).
    """
    ns = []
    for i in range(n):
        for j in range(n):
            nrm = surf.normal((i + 0.5) / n, (j + 0.5) / n)
            if nrm.Length < 1e-9:
                ns.append(None)
            else:
                nrm.normalize()
                ns.append(nrm)
    flips = []
    for i in range(n):
        for j in range(n):
            a = ns[i * n + j]
            if a is None:
                continue
            for (ii, jj) in ((i - 1, j), (i, j - 1)):
                if ii < 0 or jj < 0:
                    continue
                b = ns[ii * n + jj]
                if b is not None and a.dot(b) < -1e-6:
                    flips.append("u=%.2f,v=%.2f" % ((i + 0.5) / n, (j + 0.5) / n))
    return flips, any(v is not None for v in ns)


def check_patch(patch, edges):
    """Check the unified Patch (#37 quad / #38 pointed) against its
    boundary Edges list.

    Dispatches on the edge count: 4 edges -> the quad layout, 3 edges ->
    the pointed layout. Quad (P1-P4):
      P1  patch corners sit on the shared corners of the 4-edge loop
      P2  boundary row/col pole sets match their driving edges
      P3  the built surface's normal field is consistently oriented
      P4  surface is valid and free of self-intersection
    Pointed (mirrors the legacy Patch33 oracle under the unified shell):
      C1  corner order: (0,0) is the point shared by edges 0+2, (0,3) by
          0+1, (3,3) by 1+2
      C2  boundary match: row U0=edge0, col V3=edge1, row U3=edge2
      C3  degenerate U=0 control column collapses to a single point
      P3/P4 as above
    Returns [(name, ok, detail), ...]; never raises.
    """
    try:
        return _check_patch(patch, list(edges))
    except Exception as e:
        return [("structural", False, "oracle error: %r" % e)]


def _check_patch(patch, edges):
    """Internal oracle body dispatcher: the edge count picks the fill
    (#37 quad, #38 pointed). Other counts fall through to the quad body,
    which flags the count mismatch structurally."""
    if len(edges) == 3:
        return _check_patch_pointed(patch, edges)
    return _check_patch_quad(patch, edges)


def _check_patch_quad(patch, edges):
    """Internal oracle body for the unified 4-edge quad fill (#37).
    Mirrors the Patch44 quad checks but asserts object_type=='Patch' and
    the Edges link list, and reads the fill off the free-standing Edges
    list."""
    results = []

    # structural
    errs = []
    if getattr(patch, "object_type", None) != "Patch":
        errs.append("object_type=%r" % getattr(patch, "object_type", None))
    poles = list(patch.Poles)
    if len(poles) != 16:
        errs.append("%d poles (want 16)" % len(poles))
    weights = list(patch.Weights)
    if len(weights) != 16:
        errs.append("%d weights (want 16)" % len(weights))
    elif any(abs(w - 1.0) > 1e-12 for w in weights):
        errs.append("weights not all 1.0")
    if len(list(getattr(patch, "Edges", None) or [])) != 4:
        errs.append("Edges link list != 4 entries")
    if patch.Shape is None or patch.Shape.isNull():
        errs.append("empty Shape")
    results.append((
        "structural", not errs,
        "; ".join(errs) if errs else "object_type, 4 Edges links, 16 poles/weights, shape",
    ))

    if len(poles) != 16 or len(edges) != 4:
        return results

    e = [list(ed.Poles) for ed in edges]

    # P1: corner poles on shared corners of the edge loop.
    # Same layout as Patch44: (0,0) shared by edges 0+3, (0,3) by 0+1,
    # (3,3) by 1+2, (3,0) by 2+3; orientation within an edge is up to
    # orient_a_to_b, so each corner is matched against both endpoints.
    corner_errs = []
    for (u, v), (a, b) in [((0, 0), (0, 3)), ((0, 3), (0, 1)),
                           ((3, 3), (1, 2)), ((3, 0), (2, 3))]:
        p = poles[u * 4 + v]
        for ei in (a, b):
            if not any(_dist(p, q) <= TOL for q in (e[ei][0], e[ei][3])):
                corner_errs.append("corner p%d%d not on edge%d" % (u, v, ei))
    results.append((
        "P1_corner_order", not corner_errs,
        "; ".join(corner_errs) if corner_errs else "all 4 corners on shared loop corners",
    ))

    # P2: boundary row/col pole sets match their driving edges
    row_u0 = [poles[0], poles[1], poles[2], poles[3]]
    col_v3 = [poles[3], poles[7], poles[11], poles[15]]
    row_u3 = [poles[12], poles[13], poles[14], poles[15]]
    col_v0 = [poles[0], poles[4], poles[8], poles[12]]
    berrs = []
    for label, row, ep in [("row U0", row_u0, e[0]), ("col V3", col_v3, e[1]),
                           ("row U3", row_u3, e[2]), ("col V0", col_v0, e[3])]:
        if not _multiset_match_within(row, ep, TOL):
            berrs.append("%s does not match its edge" % label)
    results.append((
        "P2_boundary_match", not berrs,
        "; ".join(berrs) if berrs else "all 4 boundary rows/cols match their edges",
    ))

    # P3: surface normal field consistently oriented
    try:
        surf = _build_bicubic(poles, weights)
        flips, any_normal = _normal_field_flips(surf)
        if not any_normal:
            results.append(("P3_no_fold_flip", False, "surface degenerate: no normal"))
        else:
            results.append((
                "P3_no_fold_flip", not flips,
                "normal flips: " + ", ".join(flips) if flips else "normal field consistent",
            ))
    except Exception as e2:
        results.append(("P3_no_fold_flip", False, "P3 check error: %r" % e2))

    # P4: surface valid + no self-intersection
    try:
        import MeshPart
        faces = patch.Shape.Faces
        if not faces:
            results.append(("P4_surface_valid", False, "no face in Shape"))
        else:
            surf = max(faces, key=lambda f: f.Area)
            valid = patch.Shape.isValid()
            mesh = MeshPart.meshFromShape(
                Shape=surf, LinearDeflection=0.5, AngularDeflection=0.5, Relative=False)
            si = mesh.hasSelfIntersections()
            results.append((
                "P4_surface_valid", valid and not si,
                "valid=%s, self-intersections=%s" % (valid, si),
            ))
    except Exception as e2:
        results.append(("P4_surface_valid", False, "P4 check error: %r" % e2))

    return results


def _check_patch_pointed(patch, edges):
    """Internal oracle body for the unified 3-edge pointed fill (#38).
    Mirrors the legacy _check_patch33 under the unified shell:
    object_type=='Patch' with the Edges link list, the C1-C3 pointed
    checks (corner order, boundary match, degenerate U=0 column), plus
    the P3/P4 surface checks shared with the quad body."""
    results = []

    # structural
    errs = []
    if getattr(patch, "object_type", None) != "Patch":
        errs.append("object_type=%r" % getattr(patch, "object_type", None))
    poles = list(patch.Poles)
    if len(poles) != 16:
        errs.append("%d poles (want 16)" % len(poles))
    weights = list(patch.Weights)
    if len(weights) != 16:
        errs.append("%d weights (want 16)" % len(weights))
    if len(list(getattr(patch, "Edges", None) or [])) != 3:
        errs.append("Edges link list != 3 entries")
    if patch.Shape is None or patch.Shape.isNull():
        errs.append("empty Shape")
    results.append((
        "structural", not errs,
        "; ".join(errs) if errs else "object_type, 3 Edges links, 16 poles/weights, shape",
    ))

    if len(poles) != 16 or len(edges) != 3:
        return results

    e = [list(ed.Poles) for ed in edges]

    # C1: corner poles on shared corners of the edge loop.
    # (0,0) = the point, shared by edges 0+2; (0,3) by 0+1; (3,3) by
    # 1+2 -- orientation within an edge is up to orient_a_to_b, so each
    # corner is matched against both endpoints.
    corner_errs = []
    for (u, v), (a, b) in [((0, 0), (0, 2)), ((0, 3), (0, 1)),
                           ((3, 3), (1, 2))]:
        p = poles[u * 4 + v]
        for ei in (a, b):
            if not any(_dist(p, q) <= TOL for q in (e[ei][0], e[ei][3])):
                corner_errs.append("corner p%d%d not on edge%d" % (u, v, ei))
    results.append((
        "C1_corner_order", not corner_errs,
        "; ".join(corner_errs) if corner_errs else "all 3 corners on shared loop corners",
    ))

    # C2: boundary row/col pole sets match their driving edges
    row_u0 = [poles[0], poles[1], poles[2], poles[3]]
    col_v3 = [poles[3], poles[7], poles[11], poles[15]]
    row_u3 = [poles[12], poles[13], poles[14], poles[15]]
    berrs = []
    for label, row, ep in [("row U0", row_u0, e[0]), ("col V3", col_v3, e[1]),
                           ("row U3", row_u3, e[2])]:
        if not _multiset_match_within(row, ep, TOL):
            berrs.append("%s does not match its edge" % label)
    results.append((
        "C2_boundary_match", not berrs,
        "; ".join(berrs) if berrs else "U0/V3/U3 boundaries match their edges",
    ))

    # C3: the U=0 control column collapses to a single point (the
    # "point" of the pointed shape).
    col0 = [poles[i * 4] for i in range(4)]
    devs = [(_c - col0[0]).Length for _c in col0]
    collapsed = all(d <= TOL for d in devs)
    results.append((
        "C3_degenerate_pt", collapsed,
        "U=0 column collapsed to a point" if collapsed
        else "U=0 column not degenerate: dev %r" % devs,
    ))

    # P3: surface normal field consistently oriented
    try:
        surf = _build_bicubic(poles, weights)
        flips, any_normal = _normal_field_flips(surf)
        if not any_normal:
            results.append(("P3_no_fold_flip", False, "surface degenerate: no normal"))
        else:
            results.append((
                "P3_no_fold_flip", not flips,
                "normal flips: " + ", ".join(flips) if flips else "normal field consistent",
            ))
    except Exception as e2:
        results.append(("P3_no_fold_flip", False, "P3 check error: %r" % e2))

    # P4: surface valid + no self-intersection
    try:
        import MeshPart
        faces = patch.Shape.Faces
        if not faces:
            results.append(("P4_surface_valid", False, "no face in Shape"))
        else:
            surf = max(faces, key=lambda f: f.Area)
            valid = patch.Shape.isValid()
            mesh = MeshPart.meshFromShape(
                Shape=surf, LinearDeflection=0.5, AngularDeflection=0.5, Relative=False)
            si = mesh.hasSelfIntersections()
            results.append((
                "P4_surface_valid", valid and not si,
                "valid=%s, self-intersections=%s" % (valid, si),
            ))
    except Exception as e2:
        results.append(("P4_surface_valid", False, "P4 check error: %r" % e2))

    return results


# Tangent scale applied by SilkBlend when calling AN.blend_poly_2x4_1x6.
BLEND_TANGENT_SCALE = 2.0


# Boundary-edge label per adjacent corner pair (corner i of a patch is
# Poles[0], Poles[3], Poles[15], Poles[12] in cyclic order, so boundary
# edge k runs corner k -> corner k+1). The label fixes the band-split
# direction (perpendicular to the seam) and side. Kept local to the
# oracle (#39: the oracle re-derives the object code's tables instead of
# importing them, so a bug in the object code cannot hide itself).
_EDGE_LABELS = {(0, 1): "U0", (1, 2): "V1", (2, 3): "U1", (3, 0): "V0",
                (1, 0): "U0", (2, 1): "V1", (3, 2): "U1", (0, 3): "V0"}


def _adjacent(i, j):
    """Corner indices i, j adjacent on the 4-corner cycle."""
    return (j - i) % 4 == 1 or (i - j) % 4 == 1


def _detect_seam(a_c, b_c, tol):
    """Mirror of SilkMachinery.shared_seam (#39): the oracle re-derives
    the seam detection itself instead of trusting the object code.

    Robust against degenerate corners (#39 criterion 6): a pointed patch
    carries its apex twice in [Poles[0], Poles[3], Poles[15], Poles[12]]
    (Poles[0] == Poles[12]), so naive matched-pair collection
    double-counts the point. Picks an adjacent cyclic pair of corners on
    A whose matches form an adjacent cyclic pair on B, both pairs
    non-degenerate (endpoints distinct). Returns (ea, eb, pairs) or
    None.

    NOTE (#49): with two seams between the SAME patch pair (closed-ring
    builds) this returns the FIRST match -- possibly a phantom
    coincident-corner pair -- not the seam the blend actually used. Pass
    an `edge` pin where that matters; see _pinned_seam.
    """
    matches = {i: [j for j in range(4)
                   if (a_c[i] - b_c[j]).Length < tol]
               for i in range(4)}
    for i in range(4):
        i2 = (i + 1) % 4
        if (a_c[i] - a_c[i2]).Length < tol:
            continue  # degenerate pair on the same patch
        for j in matches[i]:
            for j2 in matches[i2]:
                if not _adjacent(j, j2):
                    continue
                if (b_c[j] - b_c[j2]).Length < tol:
                    continue  # degenerate pair on the other patch
                ea = _EDGE_LABELS.get((i, i2))
                eb = _EDGE_LABELS.get((j, j2))
                if ea and eb:
                    return ea, eb, [(i, j), (i2, j2)]
    return None


def _pinned_seam(a_c, b_c, ep0, ep1, tol):
    """Mirror of SilkBlend._seam_from_edge (#49), re-derived here for the
    same reason _detect_seam is: the oracle checks the blend against its
    OWN seam derivation, not the object code's.

    Pin the seam from an explicit Edge's endpoint poles -- both must sit
    (within tol) on a distinct, cyclically adjacent corner pair of BOTH
    patches. Purely geometric: the Edge object identity is irrelevant
    (patches may share geometry without sharing the same Edge object).
    This is what makes the oracle able to validate a SECOND seam on a
    pair that shares two edges, where _detect_seam cannot know which of
    the two the blend used. Returns (ea, eb, pairs) or None.
    """
    a0 = [i for i in range(4) if (a_c[i] - ep0).Length < tol]
    a1 = [i for i in range(4) if (a_c[i] - ep1).Length < tol]
    b0 = [i for i in range(4) if (b_c[i] - ep0).Length < tol]
    b1 = [i for i in range(4) if (b_c[i] - ep1).Length < tol]
    for i0 in a0:
        for i1 in a1:
            if not _adjacent(i0, i1):
                continue
            if (a_c[i0] - a_c[i1]).Length < tol:
                continue  # degenerate pair on A (pointed apex)
            for j0 in b0:
                for j1 in b1:
                    if not _adjacent(j0, j1):
                        continue
                    if (b_c[j0] - b_c[j1]).Length < tol:
                        continue  # degenerate pair on B
                    ea = _EDGE_LABELS.get((i0, i1))
                    eb = _EDGE_LABELS.get((j0, j1))
                    if ea and eb:
                        return ea, eb, [(i0, j0), (i1, j1)]
    return None


def _oracle_corner_cells(s1, s2, n_intervals, l1=0.0, l2=1.0):
    """Interval indices along one axis that are CORNER cells — reserved
    for the four-cell corner blend op (#28) and excluded from a band.

    Mirror of SilkMachinery.corner_cells, written out again HERE on
    purpose: this oracle re-derives the object code's tables instead of
    importing them, so a bug in the object code cannot satisfy the oracle
    (the reason the whole copy exists, since #39). Importing
    corner_cells would make that guarantee void — the function under test
    would be the oracle. It is equally deliberately NOT reached through
    SilkBlend, which does `from FreeCAD import Gui` and would drag GUI
    dependencies into headless oracle runs.

    The rule (#82): each axis carries TWO NAMED band edges, `Split1` for
    the parametric-0 end and `Split2` for the parametric-1 end, and each
    end's property holds its own endpoint as the "no band here" sentinel
    (0.0 on Split1, 1.0 on Split2). An end with an edge carved out the
    interval that reaches from that end — [0, s] for the 0 end, [s, 1]
    for the 1 end — and that interval is the corner cell, so drop the
    first one for Split1 and the last one for Split2. An end holding its
    sentinel has no band attached, and its end cell is not a corner cell.

    Written against the NAMES, not against a value threshold, which is
    what removes the pre-#82 guess that made a user's 0.2 or 0.85 fall
    through (#61) and made `[0.2, 0.4]` claim the 1 end had no band (#81).

    #119 / #126, mirrored here the same way: a LEADER cut at an end makes
    the corner region there the intervals from that end up to and including
    the one that ends at the leader (the cell between the setback and the
    leader), and the two ENDS are read INDEPENDENTLY — so a patch carrying a
    band edge at BOTH ends of one axis (two junctions on it, the owner's own
    ring patches) keeps the band ONE cell.  Without a leader the reading is
    the pre-#119 set, cell for cell.
    """
    def has_edge(value):
        v = float(value)
        return 0.0 < v < 1.0

    def index_at_end(end):
        """The FAR interval of the corner region at `end` — the one ending
        at the leader cut when that end carries a real one, else the end
        interval itself.  Mirror of `SilkMachinery.corner_cell_index`."""
        raw = l1 if end == 0 else l2
        cuts = _oracle_cuts(s1, s2, l1, l2)
        if not has_edge(raw) or float(raw) not in cuts:
            return 0 if end == 0 else n_intervals - 1
        pos = cuts.index(float(raw))
        return pos if end == 0 else pos + 1

    out = set()
    for end in (0, 1):
        if not has_edge(s1 if end == 0 else s2):
            continue
        idx = index_at_end(end)
        if end == 0:
            out |= set(range(0, idx + 1))
        else:
            out |= set(range(idx, n_intervals))
    return out


def _oracle_axis(p, letter):
    """`(Split1, Split2)` of axis `letter` of `p`, read by name.

    Mirrors SilkMachinery.split_pair rather than importing it (same
    reason as _oracle_corner_cells), and reads an object that has neither
    property — a pre-#82 file, where the split lists are gone — as the
    neutral "no band at either end"."""
    if letter == "U":
        return (float(getattr(p, "USplit1", 0.0)),
                float(getattr(p, "USplit2", 1.0)))
    return (float(getattr(p, "VSplit1", 0.0)),
            float(getattr(p, "VSplit2", 1.0)))


def _oracle_leader_axis(p, letter):
    """`(Leader1, Leader2)` of axis `letter` of `p` — the SECOND cut per
    axis end (#119), mirrored from `SilkMachinery.leader_pair`.

    An object that has neither property (a pre-#119 patch, a legacy
    `Patch44`, a test stub) reads as "no leader cut at either end", which
    is the identity: the axis is then cut by its two band edges alone.
    Read by NAME, like `_oracle_axis`."""
    if letter == "U":
        return (float(getattr(p, "ULeader1", 0.0)),
                float(getattr(p, "ULeader2", 1.0)))
    return (float(getattr(p, "VLeader1", 0.0)),
            float(getattr(p, "VLeader2", 1.0)))


def _oracle_cuts(s1, s2, l1, l2):
    """Every cut position one axis carries, ascending — mirror of
    `SilkMachinery.axis_cuts`: the two band edges plus a leader cut at an
    end where it CLEARS that end's band edge (a leader inside the band has
    nothing to cut and is INERT, the identity)."""
    def edge(value):
        v = float(value)
        return v if 0.0 < v < 1.0 else None
    b1, b2 = edge(s1), edge(s2)
    led1, led2 = edge(l1), edge(l2)
    cuts = [v for v in (b1, b2) if v is not None]
    if led1 is not None and (b1 is None or led1 > b1):
        cuts.append(led1)
    if led2 is not None and (b2 is None or led2 < b2):
        cuts.append(led2)
    return sorted(set(cuts))


def _oracle_intervals(s1, s2, l1=0.0, l2=1.0):
    """The intervals one axis is cut into by its two named band edges AND,
    when they are set, its two leader cuts (#119).

    Mirrors SilkMachinery.build_intervals rather than importing it (same
    reason as _oracle_corner_cells).  A patch with no leader reads exactly
    the intervals it always read."""
    s = _oracle_cuts(s1, s2, l1, l2)
    if not s:
        return [(0.0, 1.0)]
    return list(zip([0.0] + s, s + [1.0]))


def _oracle_band_cells(p, etype, ss):
    """The oracle's own re-derivation of the subgrid cells a blend's band
    covers on patch p — the #33 "band = pre-computed subgrid cells" rule,
    with the corner-cell exclusion (see _oracle_corner_cells).

    The band runs along the seam in the band interval (0 or last, per ss),
    spanning the seam-PARALLEL axis' cells; a cell at a seam end whose end
    carries a band edge is a corner cell and stays out.
    """
    us = _oracle_axis(p, "U")   # the two named band edges per axis (#82)
    vs = _oracle_axis(p, "V")
    ul = _oracle_leader_axis(p, "U")   # the second cut per end (#119)
    vl = _oracle_leader_axis(p, "V")
    nu = len(_oracle_intervals(*us, *ul))
    nv = len(_oracle_intervals(*vs, *vl))
    if etype[0] == "U":  # seam along U: band fixes V interval, spans U cells
        b = (nv - 1) if ss else 0
        keep_u = set(range(nu)) - _oracle_corner_cells(us[0], us[1], nu,
                                                      *ul)
        return [a * nv + b for a in sorted(keep_u)]
    # seam along V: band fixes U interval, spans V cells
    a = (nu - 1) if ss else 0
    keep_v = set(range(nv)) - _oracle_corner_cells(vs[0], vs[1], nv, *vl)
    return [a * nv + b for b in sorted(keep_v)]


def _oracle_cell_net(p, idx):
    """`(flat poles, flat weights)` of subgrid cell `idx` of patch `p`.

    #107: the WEIGHTS come with the poles here. A pole-only reference is
    what let a blend built with unit weights pass B1 on a rational (arc)
    patch: the strip's outer boundary curve is a different curve through
    the same 4 end poles, so the pole comparison stays exact while the
    geometry is 0.39 mm out at the middle of a 90 deg arc.

    The net is re-derived from the patch's own base surface -- the
    segmented cell -- through `Proxy.getSubgrid`, which is the patch's raw
    reader, not the cell cache the blend consumes (`_subgrids` /
    `_subgrid_weights`, the #107 seam itself). A proxy whose `getSubgrid`
    cannot answer (the legacy Patch44 shim before its base surface is
    built, a test stub) falls back to that cache, with
    unit weights when the patch stores none -- the pre-#107 reading, so
    those objects keep the verdict they always had.

    #120: that fallback is a RECORDED exception to the spec's principle 1
    ("never inspect private internals") -- see docs/specs/
    test-structure-and-mutation.md, "Recorded exception to principle 1:
    the oracle's legacy cell reader". It stays because closing it would
    turn a legacy patch's VERDICT into a refusal, and #120 changes no
    behaviour.

    Returns (None, None) when `idx` is outside the patch's cells.
    """
    proxy = getattr(p, "Proxy", None)
    us = _oracle_intervals(*_oracle_axis(p, "U"),
                           *_oracle_leader_axis(p, "U"))
    vs = _oracle_intervals(*_oracle_axis(p, "V"),
                           *_oracle_leader_axis(p, "V"))
    iu, iv = divmod(int(idx), len(vs))
    getter = getattr(proxy, "getSubgrid", None)
    if getter is not None and iu < len(us) and iv < len(vs):
        try:
            poles2d, weights2d = getter(us[iu][0], us[iu][1],
                                        vs[iv][0], vs[iv][1])
            flat_p = [poles2d[r][c] for r in range(4) for c in range(4)]
            flat_w = [float(weights2d[r][c]) for r in range(4)
                      for c in range(4)]
            if len(flat_p) == 16 and len(flat_w) == 16:
                return flat_p, flat_w
        except Exception:
            pass
    cells = list(getattr(proxy, "_subgrids", None) or [])
    if not 0 <= idx < len(cells):
        return None, None
    stored = list(getattr(proxy, "_subgrid_weights", None) or [])
    flat_w = list(stored[idx]) if len(stored) == len(cells) else [1.0] * 16
    return list(cells[idx]), flat_w


def _oracle_side_and_end(o, p, tol):
    """`(etype, ss)` -- the boundary side AND the end it names -- of the
    seam blend-shaped `o` takes on patch `p`, or (None, None) when `o`
    cannot say.

    Mirror of SilkBlend.side_and_end, re-derived HERE for the same
    reason _detect_seam is (#39): the corner oracle must resolve the
    strip's side itself, not call the production reader whose answer it
    checks -- a shared bug in side_and_end would otherwise be
    oracle-green by construction. Uses the oracle's own seam mirrors,
    exactly the two paths SilkBlend._resolve_seam takes: _pinned_seam
    when `o` pins an Edge (a unified Blend), _detect_seam otherwise (a
    legacy BlendStrip) -- and the pinned path does NOT fall back to
    auto-detect. (None, None) when `p` is not one of `o`'s two patches,
    matching the production refusal the corner-cell walk relies on to
    skip foreign strips.
    """
    if not (o.PatchA is p or o.PatchB is p):
        return None, None
    a_c = [o.PatchA.Poles[0], o.PatchA.Poles[3],
           o.PatchA.Poles[15], o.PatchA.Poles[12]]
    b_c = [o.PatchB.Poles[0], o.PatchB.Poles[3],
           o.PatchB.Poles[15], o.PatchB.Poles[12]]
    seam = None
    edge = getattr(o, "Edge", None)
    if edge is not None:
        ep = list(getattr(edge, "Poles", []) or [])
        seam = (_pinned_seam(a_c, b_c, ep[0], ep[3], tol)
                if len(ep) >= 4 else None)
    if seam is None and edge is None:
        seam = _detect_seam(a_c, b_c, tol)
    if seam is None:
        return None, None
    e = seam[0] if o.PatchA is p else seam[1]
    return e, (0 if e[1] == "0" else 1)


# The oracle's own copy of the seam-direction map (MIRROR, DO NOT IMPORT --
# see the module docstring); `_blend_reference_rows` and
# `_corner_reference_rows` both read it.
_ORACLE_SEAM_CMAP = {"U0": {0: 0, 1: 3}, "U1": {2: 3, 3: 0},
                     "V0": {0: 0, 3: 3}, "V1": {1: 0, 2: 3}}


def _oracle_seam_identity(o, tol):
    """True when `o`'s two patches parameterize their shared seam in the
    SAME direction, False when opposite, None when the matched corner pairs
    cannot say.

    Mirror of SilkBlend.seam_identity, re-derived HERE for the same reason
    `_oracle_side_and_end` is (see the module docstring): the corner oracle
    must know the seam's direction itself, because a patch that
    parameterizes the seam the other way round names the SAME junction at
    the MIRRORED row of its seam-parallel axis.
    """
    a_c = [o.PatchA.Poles[0], o.PatchA.Poles[3],
           o.PatchA.Poles[15], o.PatchA.Poles[12]]
    b_c = [o.PatchB.Poles[0], o.PatchB.Poles[3],
           o.PatchB.Poles[15], o.PatchB.Poles[12]]
    edge = getattr(o, "Edge", None)
    if edge is not None:
        ep = list(getattr(edge, "Poles", []) or [])
        seam = (_pinned_seam(a_c, b_c, ep[0], ep[3], tol)
                if len(ep) >= 4 else None)
    else:
        seam = _detect_seam(a_c, b_c, tol)
    if seam is None:
        return None
    ea, eb, pairs = seam
    identity = None
    for lc_idx, rc_idx in pairs:
        la = _ORACLE_SEAM_CMAP[ea].get(lc_idx)
        rb = _ORACLE_SEAM_CMAP[eb].get(rc_idx)
        if la is None or rb is None:
            return None
        is_id = (la == rb)
        if identity is None:
            identity = is_id
        elif is_id != identity:
            return None
    return identity


def _blend_reference_rows(pa, pb, tol=0.01, edge=None):
    """Independently re-derive the 4 (l_rev, l_w, rc, r_w) strip-row pairs
    that drive a blend between two patches.

    Mirrors SilkBlend's blend run (shared seam detection, edge type,
    strip segmentation, corner-pair row mapping) so the oracle checks the
    stored blend poles against geometry it derived itself. Returns
    [(l_rev, l_w, rc, r_w), ...] (4 rows; each side's poles are a list of 4
    Vectors and its weights the matching 4 floats, #107) or None when the
    patches do not share an edge.

    edge (#49): optional seam PIN, an Edge object, mirroring
    create_blend's edge= contract -- the seam is then derived from that
    Edge's endpoint poles (_pinned_seam) instead of auto-detected
    (_detect_seam). Required to check a blend on a pair that shares TWO
    edges, where the auto-detect would re-derive the first (or a phantom
    coincident-corner) seam and flag a correct second-seam blend. With
    edge=None the behaviour is exactly as before.
    """
    a_c = [pa.Poles[0], pa.Poles[3], pa.Poles[15], pa.Poles[12]]
    b_c = [pb.Poles[0], pb.Poles[3], pb.Poles[15], pb.Poles[12]]
    if edge is not None:
        ep = list(getattr(edge, "Poles", []) or [])
        seam = (_pinned_seam(a_c, b_c, ep[0], ep[3], tol)
                if len(ep) >= 4 else None)
    else:
        seam = _detect_seam(a_c, b_c, tol)
    if seam is None:
        return None
    ea, eb, pairs = seam
    ss_a = 0 if ea[1] == "0" else 1
    ss_b = 0 if eb[1] == "0" else 1

    # #33: the blend band comes from the patch's own subgrid cells
    # (mirrors SilkBlend.run_blend band_cells/get_strip; the selection
    # RULE is the oracle's own — see _oracle_band_cells, #63).
    def band_cells(p, etype, ss):
        return _oracle_band_cells(p, etype, ss)

    def get_strip(p, etype, ss):
        idxs = band_cells(p, etype, ss)
        if len(idxs) != 1 or not p.Proxy._subgrids:
            return None
        return _oracle_cell_net(p, idxs[0])

    sga = get_strip(pa, ea, ss_a)
    sgb = get_strip(pb, eb, ss_b)
    if sga is None or sgb is None:
        return None
    sga_p, sga_w = sga
    sgb_p, sgb_w = sgb

    cmap = _ORACLE_SEAM_CMAP
    # Seam alignment (#30): middle rows follow the corner-pair alignment
    # (identity or reversed), not an assumed reversal. `pairs` holds only
    # the seam's two matched corner pairs; the cmap lookups guard both
    # sides (degenerate pointed corners must never KeyError).
    identity = None
    for lc_idx, rc_idx in pairs:
        la = cmap[ea].get(lc_idx)
        rb = cmap[eb].get(rc_idx)
        if la is None or rb is None:
            return None
        is_id = (la == rb)
        if identity is None:
            identity = is_id
        elif is_id != identity:
            return None
    if identity is None:
        return None
    # #31: strip index 0 sits at param 0 of the strip window, so the shared
    # edge is at index 0 for ss=0 and index 3 for ss=1. Build each row in
    # shared->outer order, then orient: poles_0 outer->shared, poles_1
    # shared->outer. #107: the WEIGHTS are read with the same indices as the
    # poles -- a row is (poles, weights) in both orientations, so
    # `rows[i][1][k]` is the weight of `rows[i][0][k]`.
    va = range(4) if ss_a == 0 else range(3, -1, -1)   # left:  shared->outer
    vb = range(4) if ss_b == 0 else range(3, -1, -1)   # right: shared->outer
    rows = []
    for li in range(4):
        if ea[0] == "U":  # shared along U -> COLUMNS (const U)
            l_idx = [li * 4 + v for v in va]
        else:  # shared along V -> ROWS (const V)
            l_idx = [v * 4 + li for v in va]
        l_rev = list(reversed([sga_p[i] for i in l_idx]))
        l_rev_w = list(reversed([sga_w[i] for i in l_idx]))
        for lc_idx, rc_idx in pairs:
            rb = cmap[eb].get(rc_idx)
            if rb is not None and li == cmap[ea].get(lc_idx):
                ri = rb
                break
        else:
            ri = li if identity else 3 - li
        if eb[0] == "U":
            r_idx = [ri * 4 + v for v in vb]
        else:
            r_idx = [v * 4 + ri for v in vb]
        rc = [sgb_p[i] for i in r_idx]
        rc_w = [sgb_w[i] for i in r_idx]
        rows.append((l_rev, l_rev_w, rc, rc_w))
    return rows


def _check_blend(blend, pa, pb, reference_poles, edge=None):
    results = []

    # structural (both blend types accepted: the unified "Blend" #39 and
    # the legacy "BlendStrip" that old documents / the GUI command create)
    st = getattr(blend, "object_type", None)
    poles = blend.Poles or []
    weights = blend.Weights or []
    # #107: the weights are no longer asserted to be 1. A strip across a
    # rational (arc) patch edge carries that edge's weights, which is the
    # whole point of the fix; what a blend must never carry is a
    # non-positive or missing weight. The unit-weight path is separately
    # pinned in the tests (and the demo/legacy fixtures are unit-weight,
    # so this reads "unit" there).
    unit_weights = (len(weights) == 24
                    and all(abs(w - 1.0) < 1e-12 for w in weights))
    ok = (st in ("Blend", "BlendStrip") and len(poles) == 24
          and len(weights) == 24 and all(w > 1e-12 for w in weights)
          and pa is not None and pb is not None
          and getattr(blend, "Shape", None) is not None
          and not blend.Shape.isNull())
    results.append(("structural", ok,
                    "type=%s poles=%d weights=%d (%s) shape=%s" % (
                        st, len(poles), len(weights),
                        "unit" if unit_weights else "rational",
                        "ok" if ok else "bad")))

    rows = _blend_reference_rows(pa, pb,
                                 tol=getattr(blend, "tolerance", 0.01),
                                 edge=edge)
    if rows is None:
        no_seam = ("the pinned edge is not a shared boundary of both patches"
                   if edge is not None
                   else "no shared edge found between the patches")
        results.append(("B1_c0_seams", False, no_seam))
        results.append(("B2_c1_tangents", False, no_seam))
        return results

    # B1: C0 -- each blend row's outer poles sit on the strip-curve
    # endpoints (row layout: [outer_L, t_L, inner_L, inner_R, t_R, outer_R])
    # AND the two outer boundary CURVES coincide with the patch cells'
    # outer edge curves, weights included (#107).
    #
    # The pole comparison alone is structurally blind: the strip's outer
    # boundary curve is the cubic Bezier through the 4 outer poles WITH
    # their 4 weights, and the unit-weight curve through the same 4 poles is
    # a different curve whenever the patch is rational (an arc edge). It
    # stays exact at the poles -- which is precisely why this check shipped
    # green on geometry that is 0.39 mm out at the middle of a 90 deg arc,
    # R=10. Forgotten weights are the #67 trap in a new place, so the
    # comparison is now on the evaluated curve.
    b1_pole_dev = 0.0
    b1_weight_dev = 0.0
    b1_curve_dev = 0.0
    _ts = [i / 32.0 for i in range(33)]
    for i, (l_rev, l_w, rc, r_w) in enumerate(rows):
        row = poles[i * 6:i * 6 + 6]
        row_w = weights[i * 6:i * 6 + 6]
        b1_pole_dev = max(b1_pole_dev, (row[0] - l_rev[0]).Length,
                          (row[5] - rc[3]).Length)
        b1_weight_dev = max(b1_weight_dev, abs(row_w[0] - l_w[0]),
                            abs(row_w[5] - r_w[3]))
    # the two boundary curves: the 4 rows' outer poles/weights (the blend's
    # own outer rows) against the reference cells' outer edge curves, both
    # cubic Beziers over the same 4 seam stations, sampled point-for-point.
    for ref_p, ref_w, own in (
            ([r[0][0] for r in rows], [r[1][0] for r in rows], 0),
            ([r[2][3] for r in rows], [r[3][3] for r in rows], 5)):
        own_p = [poles[i * 6 + own] for i in range(4)]
        own_w = [weights[i * 6 + own] for i in range(4)]
        for t in _ts:
            b1_curve_dev = max(b1_curve_dev,
                               (_bezier4_point(own_p, own_w, t)
                                - _bezier4_point(ref_p, ref_w, t)).Length)
    results.append(("B1_c0_seams",
                    b1_pole_dev <= TOL and b1_curve_dev <= TOL,
                    "max boundary-curve deviation %.3e mm (outer poles "
                    "%.3e, boundary weights %.3e)"
                    % (b1_curve_dev, b1_pole_dev, b1_weight_dev)))

    # B2: C1 construction -- the tangent poles must match the reference
    # blend of the independently derived strip rows
    import ArachNURBS as AN
    b2_dev = 0.0
    for i, (l_rev, l_w, rc, r_w) in enumerate(rows):
        ref_row = AN.blend_poly_2x4_1x6(
            l_rev, l_w, rc, r_w,
            BLEND_TANGENT_SCALE, BLEND_TANGENT_SCALE,
            BLEND_TANGENT_SCALE, BLEND_TANGENT_SCALE)[0]
        row = poles[i * 6:i * 6 + 6]
        b2_dev = max(b2_dev, (row[1] - ref_row[1]).Length,
                     (row[4] - ref_row[4]).Length)
    results.append(("B2_c1_tangents", b2_dev <= TOL,
                    "max tangent-pole deviation %.3e" % b2_dev))

    # B3: surface valid + no self-intersection + normal field coherent
    try:
        import MeshPart
        faces = blend.Shape.Faces
        if not faces:
            results.append(("B3_surface_valid", False, "no face in Shape"))
        else:
            surf = max(faces, key=lambda f: f.Area)
            valid = blend.Shape.isValid()
            mesh = MeshPart.meshFromShape(
                Shape=surf, LinearDeflection=0.5, AngularDeflection=0.5,
                Relative=False)
            si = mesh.hasSelfIntersections()
            # local normal consistency over a 9x9 parametric grid
            # (neighbour-based -- see _normal_field_flips)
            bad_normals, any_normal = _normal_field_flips(surf.Surface)
            ok_b3 = valid and not si and not bad_normals and any_normal
            results.append(("B3_surface_valid", ok_b3,
                            "valid=%s, self-intersections=%s, "
                            "flipped normals=%d" % (valid, si, len(bad_normals))))
    except Exception as e2:
        results.append(("B3_surface_valid", False, "B3 check error: %r" % e2))

    # B4: full 24-pole match against a provided reference
    if reference_poles is None:
        results.append(("B4_pole_match", True,
                        "no reference given (skipped)"))
    else:
        if len(reference_poles) != 24:
            results.append(("B4_pole_match", False,
                            "reference has %d poles, want 24" %
                            len(reference_poles)))
        else:
            b4_dev = max((p - r).Length for p, r in zip(poles,
                                                        reference_poles))
            results.append(("B4_pole_match", b4_dev <= TOL,
                            "max deviation from reference %.3e" % b4_dev))

    return results


def _oracle_share_patch(a, b):
    """True when two strips touch one and the same Patch object.

    Mirror of SilkMachinery._share_patch, re-derived HERE (see the module
    docstring): adjacency in a corner ring is patch-object IDENTITY, and
    the oracle must not read the code under test's answer to build the
    ring it checks that code's output against."""
    return any(x is not None and (x is getattr(b, "PatchA", None)
                                  or x is getattr(b, "PatchB", None))
               for x in (getattr(a, "PatchA", None),
                         getattr(a, "PatchB", None)))


def _oracle_shared_patch(a, b):
    """The ONE Patch object two ring strips both touch, or None when they
    touch none or two (an ambiguous pair). Mirror of
    SilkCorner._shared_patch, for the reason _oracle_share_patch is."""
    common = [x for x in (getattr(a, "PatchA", None),
                          getattr(a, "PatchB", None))
              if x is not None and (x is getattr(b, "PatchA", None)
                                    or x is getattr(b, "PatchB", None))]
    return common[0] if len(common) == 1 else None


def _oracle_doc_index(o):
    """The object's own position in its document's object list, else 0.

    Mirror of SilkMachinery._doc_index: the ring's START is the strip
    earliest in the document, so the oracle has to know the same order to
    derive the same canonical ring (`_oracle_corner_ring`)."""
    doc = getattr(o, "Document", None)
    if doc is None:
        return 0
    for k, oo in enumerate(list(doc.Objects)):
        if oo is o:
            return k
    return 0


def _oracle_corner_ring(strips):
    """The four ring strips in the cyclic order the corner chain is fed
    them: `ordered[k]` and `ordered[k+1]` share a patch.

    Mirror of SilkMachinery.corner_ring, re-derived HERE (see the module
    docstring): the ring ORDER is part of the canonical feed CB2's
    reference chain is built from, so reading it from the code under test
    would let a wrong start move both sides together and cancel out.
    Written from the documented ring instead -- two strips are neighbours
    when they both touch one patch object, the start is the strip earliest
    in the document and its neighbour later in document order, and the
    four must form one cycle in which every strip has exactly two
    neighbours.

    Returns (ordered, None) or (None, reason)."""
    strips = list(strips)
    if len(strips) != 4:
        return None, ("a corner ring is exactly 4 blends (got %d)"
                      % len(strips))
    for i, s in enumerate(strips):
        if any(s is t for t in strips[:i]):
            return None, ("%s is in the ring twice"
                          % (getattr(s, "Name", None) or s))
    adj = {i: set() for i in range(4)}
    for i in range(4):
        for j in range(i + 1, 4):
            if _oracle_share_patch(strips[i], strips[j]):
                adj[i].add(j)
                adj[j].add(i)
    for i in range(4):
        if len(adj[i]) != 2:
            return None, ("%s shares a patch with %d of the other blends; "
                          "four blends ring a junction only when each one "
                          "meets exactly two of the others"
                          % (getattr(strips[i], "Name", None) or i,
                             len(adj[i])))
    start = min(range(4), key=lambda i: _oracle_doc_index(strips[i]))
    nxt = min(adj[start], key=lambda i: _oracle_doc_index(strips[i]))
    order = [start, nxt]
    while len(order) < 4:
        step = [k for k in adj[order[-1]] if k not in order]
        if len(step) != 1:
            return None, "the four blends do not form a single ring"
        order.append(step[0])
    if order[0] not in adj[order[-1]]:
        return None, "the four blends do not form a single ring"
    return [strips[i] for i in order], None


# The flat corner slots of a 24-pole 4x6 grid, in the chain's corner order
# ([0, 5, 18, 23] = (V0U0, V0U5, V3U0, V3U5)) -- the oracle's own copy of
# SilkMachinery.CORNER_IDX (MIRROR, DO NOT IMPORT; module docstring).
_ORACLE_GRID_CORNERS = (0, 5, 18, 23)

# The pairing the subgrid chain reads at a shared corner: slot 3 of one
# grid (V3,U5) against slot 2 of the next (V3,U0) -- the oracle's own copy
# of SilkMachinery.CORNER_COMMON (MIRROR, DO NOT IMPORT).
_ORACLE_RING_PAIRING = (3, 2)

# The chain matches its shared corner at 1e-6 (upstream SubGrid33_2Grid64's
# default tolerance, CORNER_TOL in SilkCorner), tighter than the strip-side
# tolerance the junction rows are derived at. The oracle tests its ring feed
# at the chain's OWN tolerance, so it cannot refuse a feed the chain accepts.
_ORACLE_GRID_TOL = 1e-6


def _oracle_shared_corner(grid_0, grid_1, tol=_ORACLE_GRID_TOL):
    """(a, b): the corner slot (0..3 of `_ORACLE_GRID_CORNERS`) that two
    adjacent ring grids share, or (None, reason).

    Mirror of SilkMachinery.pair_common for a ring of FOUR: two strips of
    a 4-patch ring meet at exactly ONE junction corner, so the rules that
    let `pair_common` admit the triangular member's collapsed end row do
    not apply here -- anything but a single coincidence is an
    inconsistency, not a pairing."""
    c0 = [grid_0[k] for k in _ORACLE_GRID_CORNERS]
    c1 = [grid_1[k] for k in _ORACLE_GRID_CORNERS]
    matches = [(a, b) for a in range(4) for b in range(4)
               if (c0[a] - c1[b]).Length <= tol]
    if len(matches) != 1:
        return None, ("the two grids share %d corners at tolerance %g"
                      % (len(matches), tol))
    return matches[0], None


def _oracle_ring_reading(grids, tol=_ORACLE_GRID_TOL):
    """('canonical' | 'mirrored', None) or (None, reason) for a 4-grid ring.

    Mirror of the orientation test SilkMachinery.corner_grid applies before
    it assembles a ring: every consecutive pair must present its shared
    corner at the chain's pairing (slot 3 of the first, slot 2 of the
    second), or at the mirror of it for a ring whose stored strip order
    runs the other way round. Anything else is not a consistently oriented
    ring and the chain cannot consume it."""
    pairs = []
    for i in range(4):
        pr, why = _oracle_shared_corner(grids[i][0], grids[(i + 1) % 4][0],
                                        tol)
        if pr is None:
            return None, ("strip %d and strip %d: %s"
                          % (i, (i + 1) % 4, why))
        pairs.append(pr)
    if all(pr == _ORACLE_RING_PAIRING for pr in pairs):
        return "canonical", None
    if all(pr == tuple(reversed(_ORACLE_RING_PAIRING)) for pr in pairs):
        return "mirrored", None
    return None, ("the four strips are not a consistently oriented ring "
                  "(shared corners %r)" % (pairs,))


def _oracle_orient_ring_columns(grids, ordered):
    """Mirror of SilkCorner._orient_ring_columns: reverse the 6 columns
    (U -> 5 - U) of every strip that owns the ring's shared patch as its
    PatchA.

    The 6-pole axis of a strip runs from its PatchA side to its PatchB
    side, so which patch lands at column 0 is whichever the user handed
    `create_blend` FIRST -- arbitrary, and the same surface either way
    round. A ring whose strips are not a directed cycle therefore cannot
    present its shared corners at one fixed slot pair until those columns
    are flipped; the flip is a reparameterization of the across-seam axis,
    not a geometry change."""
    n = len(grids)
    out = []
    for i, (poles, weights) in enumerate(grids):
        nxt = _oracle_shared_patch(ordered[i], ordered[(i + 1) % n])
        if nxt is not None and getattr(ordered[i], "PatchA", None) is nxt:
            poles = [poles[r * 6 + (5 - c)]
                     for r in range(4) for c in range(6)]
            weights = [weights[r * 6 + (5 - c)]
                       for r in range(4) for c in range(6)]
        out.append((poles, weights))
    return out


def _oracle_strip_junction_row(s, strips, tol):
    """(li, why): the row (0 or 3) of strip `s`'s flat `V*6+U` blend grid
    that sits at the ring's junction, or (None, reason).

    Mirror of SilkCorner.corner_inputs' per-strip derivation (#120), and
    the strip's side is read off the STRIP (#83), the way
    `_oracle_side_and_end` already does: a unified Blend pins its Edge, so
    a patch pair sharing two seams cannot collapse to one side. The
    junction row is the row the patch's corner CELL sits against -- the
    corner cell is the signed end of the axis the OTHER seam runs along,
    and the band cell is the seam's own, so the row is 3 when the corner
    cell lies above the band cell. The two patches must agree (mirrored
    when the seam is reversed): that is the twisted-input refusal."""
    pa = getattr(s, "PatchA", None)
    pb = getattr(s, "PatchB", None)
    if pa is None or pb is None:
        return None, ("blend %s has no patches"
                      % (getattr(s, "Name", None) or s))
    e_a, ss_a = _oracle_side_and_end(s, pa, tol)
    e_b, ss_b = _oracle_side_and_end(s, pb, tol)
    if not e_a or not e_b:
        return None, ("blend %s: no shared edge between %s and %s"
                      % (getattr(s, "Name", None) or s, pa.Name, pb.Name))
    # The two patches can parameterize the shared seam in the same
    # direction (identity) or opposite (reversed); a reversed seam names
    # the SAME junction at the MIRRORED row of the patch's seam-parallel
    # axis, so the two are compared ACROSS that reflection.
    identity = _oracle_seam_identity(s, tol)
    bca = _oracle_band_cells(pa, e_a, ss_a)
    bcb = _oracle_band_cells(pb, e_b, ss_b)
    if len(bca) != 1 or len(bcb) != 1:
        return None, ("blend %s: its band must cover exactly 1 cell per side "
                      "(got %d/%d)"
                      % (getattr(s, "Name", None) or s, len(bca), len(bcb)))
    li_map = {}
    for pth, e, bc in ((pa, e_a, bca), (pb, e_b, bcb)):
        nu = len(_oracle_intervals(*_oracle_axis(pth, "U"),
                                   *_oracle_leader_axis(pth, "U")))
        nv = len(_oracle_intervals(*_oracle_axis(pth, "V"),
                                   *_oracle_leader_axis(pth, "V")))
        iu_c = iv_c = None
        for t in strips:
            te, tss = _oracle_side_and_end(t, pth, tol)
            if not te:
                continue
            if te[0] == "U":
                iv_c = nv - 1 if te[1] == "1" else 0
            else:
                iu_c = nu - 1 if te[1] == "1" else 0
        if iu_c is None or iv_c is None:
            return None, ("blend %s: patch %s: no corner cell at the "
                          "junction (the strips on it do not close one)"
                          % (getattr(s, "Name", None) or s, pth.Name))
        iu_b, iv_b = divmod(bc[0], nv)
        if e[0] == "U":
            li_map[pth.Name] = 3 if iu_c > iu_b else 0
        else:
            li_map[pth.Name] = 3 if iv_c > iv_b else 0
    if li_map[pa.Name] != (3 - li_map[pb.Name] if identity is False
                           else li_map[pb.Name]):
        return None, ("blend %s: its two patches disagree about which end "
                      "is the junction (twisted input)"
                      % (getattr(s, "Name", None) or s))
    return li_map[pa.Name], None


def _oracle_canonical_corner_grids(strips, tol=0.01):
    """The ring's four 24-pole grids in the exact form the subgrid chain
    consumes them: ring order, every strip's junction-end row at V = 3,
    and the across-seam columns normalized so the ring presents each
    shared corner at the pairing the chain reads.

    MIRROR of SilkCorner.corner_inputs, re-derived HERE (#120), for the
    reason the module docstring gives: CB2 builds its reference chain
    from these grids, and asking `corner_inputs` for them meant the same
    derivation had just fed the object under test. Both sides then moved
    together, so a wrong canonical grid -- a wrong ring start, a wrong
    junction row, a wrong column direction -- was invisible: the
    reference reproduced the defect instead of exposing it. (`SilkChecks`
    already mirrors `band_cells` for exactly this reason; this is that
    rule applied to the corner's canonical feed.)

    Returns (grids, None) or (None, reason): `grids` is a list of
    (poles24, weights24) in ring order."""
    ordered, why = _oracle_corner_ring(strips)
    if ordered is None:
        return None, why
    base = []
    for s in ordered:
        li, why = _oracle_strip_junction_row(s, list(strips), tol)
        if li is None:
            return None, why
        poles = list(getattr(s, "Poles", None) or [])
        weights = list(getattr(s, "Weights", None) or [])
        if len(poles) != 24 or len(weights) != 24:
            return None, ("blend %s: expected a 24-pole grid, got %d poles "
                          "/ %d weights"
                          % (getattr(s, "Name", None) or s, len(poles),
                             len(weights)))
        if li != 3:
            # The chain's fixed index convention: junction-end row at V = 3.
            poles = [poles[(3 - v) * 6 + u]
                     for v in range(4) for u in range(6)]
            weights = [weights[(3 - v) * 6 + u]
                       for v in range(4) for u in range(6)]
        base.append((poles, weights))
    # The ring as stored, then with its columns normalized -- `corner_grid`
    # tries the stored orientation first so a ring that already assembles
    # keeps its exact poles, and the oracle tries the same two candidates in
    # the same order for the same reason.
    why = None
    for cand in (base, _oracle_orient_ring_columns(base, ordered)):
        reading, why = _oracle_ring_reading(cand)
        if reading is not None:
            return cand, None
    return None, why


def _corner_reference_rows(strips, tol=0.01):
    """Independently derive each ring strip's corner-end row — the
    6-pole edge of the strip's blend surface at the corner-cell side.

    Works for a 3-strip ring as well as a 4-strip one: the corner index
    comes from the STRIPS that touch a patch, and a 3-valent patch is
    touched by exactly two of them.

    Mirrors SilkCorner's derivation from the patches' splits and band
    cells (not from the corner blend itself). Returns (rows, None) or
    (None, reason) -- the reason names the strip that broke the ring, so
    CB1 can say WHY (#120; the ring resolver is no longer asked).
    """
    rows = []
    for s in strips:
        li, why = _oracle_strip_junction_row(s, list(strips), tol)
        if li is None:
            return None, why
        poles = list(getattr(s, "Poles", None) or [])
        if len(poles) != 24:
            return None, ("blend %s: expected a 24-pole grid, got %d"
                          % (getattr(s, "Name", None) or s, len(poles)))
        rows.append(poles[li * 6: li * 6 + 6])
    return rows, None


def _check_corner_blend(cb, strips, reference_poles):
    results = []

    # structural
    st = getattr(cb, "object_type", None)
    poles = cb.Poles or []
    weights = cb.Weights or []
    # A 3-valent hard corner stores the THREE ring strips it was built
    # from (the triangular 4th member is derived, never an object); a
    # 4-valent one stores all four. Both are 36-pole corners.
    ok = (st == "CornerBlend" and len(poles) == 36
          and len(weights) == 36 and all(w > 0.0 for w in weights)
          and len(list(getattr(cb, "Strips", []) or [])) in (3, 4)
          and getattr(cb, "Shape", None) is not None
          and not cb.Shape.isNull())
    results.append(("structural", ok,
                    "type=%s poles=%d weights=%d shape=%s" % (
                        st, len(poles), len(weights),
                        "ok" if ok else "bad")))

    rows, why = _corner_reference_rows(
        strips, tol=getattr(cb, "tolerance", 0.01))
    if rows is None:
        # The refusal NAMES the strip (or patch) that broke the ring --
        # the oracle's OWN reason, not the ring resolver's (#120: the
        # resolver is the code under test, and asking it to explain a
        # verdict the oracle has already reached proves nothing).
        why = why or "could not derive corner-end rows from the strips"
        results.append(("CB1_c0_boundary", False,
                        "could not derive corner-end rows: %s" % why))
        results.append(("CB2_interior_fill", False, why))
        return results

    # CB1: C0 boundary -- each reference row appears among the 4
    # boundary sides of the 6x6 grid (orientation-independent), each
    # side used exactly once
    sides = [list(poles[0:6]), list(poles[30:36]),
             list(poles[0::6]), list(poles[5::6])]
    if any(len(side) != 6 for side in sides):
        results.append(("CB1_c0_boundary", False,
                        "grid does not hold 36 poles"))
    else:
        import math
        used = set()
        cb1_dev = 0.0
        for row in rows:
            best, bi = math.inf, None
            for k, side in enumerate(sides):
                if k in used:
                    continue
                d = min(max((a - b).Length for a, b in zip(row, side)),
                        max((a - b).Length
                            for a, b in zip(row, list(reversed(side)))))
                if d < best:
                    best, bi = d, k
            if bi is None:
                cb1_dev = math.inf
                break
            used.add(bi)
            cb1_dev = max(cb1_dev, best)
        results.append(("CB1_c0_boundary", cb1_dev <= TOL,
                        "max boundary deviation %.3e" % cb1_dev))

    # CB2: interior fill -- all 36 poles must match the legacy subgrid
    # chain (SubGrid33_2Grid64 x4 -> ControlGrid66_4Sub) fed the SAME
    # canonical grids (#91). The legacy classes are the ground-truth
    # oracle; our machinery is required to match them pole for pole. The
    # grids themselves are the oracle's OWN mirror of the canonicalization
    # (`_oracle_canonical_corner_grids`, #120): were they read back from
    # `corner_inputs`, a wrong ring order / junction row / column
    # direction would move both sides together and this check could not
    # see it.
    try:
        import ArachNURBS as AN
        doc = cb.Document
        if len(strips) == 3:
            # A 3-valent ring has NO legacy reference to match: the legacy
            # SubGrid33_2Grid64 cannot assemble it (the triangular member's
            # collapsed row presents two coincident corners, and it refuses
            # with "multiple common corners found at the current tolerance",
            # 0 poles, Invalid -- measured), and the shipped surface
            # deliberately re-solves the member-side interior rows from the
            # boundary (SilkMachinery.smooth_degenerate_cap) where that chain
            # extrapolates past the collapsed row and folds the cap. So this
            # is reported, not asserted either way -- the same convention as
            # CB4's "no reference given (skipped)".
            results.append(("CB2_interior_fill", True,
                            "not applicable to a 3-valent ring: the legacy "
                            "subgrid chain cannot assemble its collapsed "
                            "member (multiple coincident corners), and the "
                            "shipped cap re-solves those rows on purpose"))
        else:
            grids, why = _oracle_canonical_corner_grids(
                list(strips), getattr(cb, "tolerance", 0.01))
            if grids is None:
                results.append(("CB2_interior_fill", False,
                                "could not derive corner grids: %s" % why))
            else:
                carriers, subs, grid = [], [], None
                ref_poles = []
                try:
                    for p, w in grids:
                        c = doc.addObject("Part::FeaturePython",
                                          "_cb_ref_poly")
                        c.addProperty("App::PropertyVectorList", "Poles",
                                      "Internal", "p").Poles
                        c.addProperty("App::PropertyFloatList", "Weights",
                                      "Internal", "w").Weights
                        c.Poles = p
                        c.Weights = w
                        carriers.append(c)
                    for i in range(4):
                        sg = doc.addObject("Part::FeaturePython",
                                           "_cb_ref_sub")
                        AN.SubGrid33_2Grid64(sg, carriers[i],
                                             carriers[(i + 1) % 4])
                        sg.recompute()
                        subs.append(sg)
                    grid = doc.addObject("Part::FeaturePython",
                                         "_cb_ref_grid")
                    AN.ControlGrid66_4Sub(grid, *subs)
                    grid.recompute()
                    ref_poles = (list(grid.Poles)
                                 if hasattr(grid, "Poles") else [])
                finally:
                    # temp reference objects must not survive a failed
                    # build; cleanup runs before the error result below
                    for o in (([grid] if grid is not None else [])
                              + subs + carriers):
                        if o is not None and doc.getObject(o.Name) is not None:
                            try:
                                doc.removeObject(o.Name)
                            except Exception:
                                pass
                if len(ref_poles) != 36:
                    results.append(("CB2_interior_fill", False,
                                    "reference chain produced %d poles"
                                    % len(ref_poles)))
                else:
                    cb2_dev = max((p - r).Length
                                  for p, r in zip(poles, ref_poles))
                    results.append(("CB2_interior_fill", cb2_dev <= TOL,
                                    "max deviation from reference chain "
                                    "%.3e" % cb2_dev))
    except Exception as e2:
        results.append(("CB2_interior_fill", False,
                        "CB2 check error: %r" % e2))

    # CB3: surface valid + no self-intersection + normal field coherent
    try:
        import MeshPart
        faces = cb.Shape.Faces
        if not faces:
            results.append(("CB3_surface_valid", False, "no face in Shape"))
        else:
            surf = max(faces, key=lambda f: f.Area)
            valid = cb.Shape.isValid()
            mesh = MeshPart.meshFromShape(
                Shape=surf, LinearDeflection=0.5, AngularDeflection=0.5,
                Relative=False)
            si = mesh.hasSelfIntersections()
            bad_normals, any_normal = _normal_field_flips(surf.Surface)
            ok_b3 = valid and not si and not bad_normals and any_normal
            results.append(("CB3_surface_valid", ok_b3,
                            "valid=%s, self-intersections=%s, "
                            "flipped normals=%d" % (valid, si,
                                                    len(bad_normals))))
    except Exception as e2:
        results.append(("CB3_surface_valid", False, "CB3 check error: %r" % e2))

    # CB4: full 36-pole match against a provided reference
    if reference_poles is None:
        results.append(("CB4_pole_match", True,
                        "no reference given (skipped)"))
    else:
        if len(reference_poles) != 36:
            results.append(("CB4_pole_match", False,
                            "reference has %d poles, want 36" %
                            len(reference_poles)))
        else:
            cb4_dev = max((p - r).Length for p, r in zip(poles,
                                                         reference_poles))
            results.append(("CB4_pole_match", cb4_dev <= TOL,
                            "max deviation from reference %.3e" % cb4_dev))

    return results


def check_corner_blend(cb, strip0=None, strip1=None, strip2=None,
                       strip3=None, reference_poles=None):
    """Corner blend oracle (CB1-CB4). Accepts the ring's strips either as
    separate arguments or (as the only argument) as a list.

    Three strips is a 3-valent hard corner -- the corner OBJECT derives
    its triangular 4th member, and CB2 has no legacy reference for such a
    ring, so it says so rather than going green or red (see CB2);
    the 4-valent ring is the case CB2's reference chain runs on. CB1
    then matches the ring strips' junction rows, which are three of the
    corner's four boundary sides (the fourth is the member's).

    A ring of anything other than 3 or 4 strips is refused as INPUT, by
    count: with an empty strip list no row needs matching, so CB1 used to
    compute a 0.0 deviation -- a GREEN for having checked nothing.
    """
    if isinstance(cb, (list, tuple)):
        strips = list(cb)
    else:
        strips = [s for s in (strip0, strip1, strip2, strip3)
                  if s is not None]
    if len(strips) not in (3, 4):
        return [("ring_input", False,
                 "a corner ring is 3 or 4 blends (got %d)"
                 % len(strips))]
    return _check_corner_blend(cb, strips, reference_poles)


def check_blend(blend, patch_a, patch_b, reference_poles=None, edge=None):
    """Check a Blend / legacy BlendStrip against its two patches
    (explicit arguments).

    reference_poles: optional 24-pole reference (e.g. the stored
    ground-truth blend) for the B4 full-pole match.

    edge (#49): optional seam PIN, an Edge object, mirroring
    create_blend's edge= contract. The B1/B2 reference rows are then
    derived from that Edge's endpoint poles rather than auto-detected,
    so a blend on a pair sharing TWO edges (closed-ring builds) is
    checked against the seam it actually used. Omit it (default) and
    the reference is auto-detected, exactly as before -- pass
    blend.Edge for a blend that carries one.

    Returns [(name, ok, detail), ...]; never raises.
    """
    try:
        return _check_blend(blend, patch_a, patch_b, reference_poles, edge)
    except Exception as e:
        return [("structural", False, "oracle error: %r" % e)]
