"""
SilkChecks — the correctness oracle for workflow objects.

Each check_* function RETURNS a list of (name, ok, detail) tuples and
never raises: "is this correct?" is a query; deciding what a failure
means is the caller's job (tests assert on it, the future wizard will
display it).

Ticket #18: check_edge (structural + E1-E4). check_patch44 lands with
#19; check_blend with #20.

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
Corner blends (CB1-CB4, #28):
  CB1 C0 boundary: the 6x6 grid's 4 boundary sides match the 4 ring
      strips' corner-end rows, orientation-independent (1e-6)
  CB2 interior fill: all 36 poles match the ControlGrid66_4 fill of the
      independently derived boundary rows (1e-6)
  CB3 corner surface valid + no self-intersection + normal field coherent
  CB4 full 36-pole match against a provided reference (optional)

Tolerances (spec #16): poles 1e-6, weights exact (1.0).
"""

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
        d0 = _dist(poles[0], first)
        d3 = _dist(poles[3], last)
        ok = d0 <= TOL and d3 <= TOL
        results.append((
            "E1_endpoint_anchoring", ok,
            "end deltas vs sketch: %.2e / %.2e (tol %.0e)" % (d0, d3, TOL),
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


def _check_patch44(patch, edges):
    results = []

    # structural
    errs = []
    if getattr(patch, "object_type", None) != "Patch44":
        errs.append("object_type=%r" % getattr(patch, "object_type", None))
    poles = list(patch.Poles)
    if len(poles) != 16:
        errs.append("%d poles (want 16)" % len(poles))
    weights = list(patch.Weights)
    if len(weights) != 16:
        errs.append("%d weights (want 16)" % len(weights))
    elif any(abs(w - 1.0) > 1e-12 for w in weights):
        errs.append("weights not all 1.0")
    if not all(getattr(patch, "Poly%d" % i, None) for i in range(4)):
        errs.append("missing Poly0-3 edge links")
    if patch.Shape.isNull():
        errs.append("empty Shape")
    results.append((
        "structural", not errs,
        "; ".join(errs) if errs else "object_type, 4 edge links, 16 poles/weights, shape",
    ))

    if len(poles) != 16 or len(edges) != 4:
        return results

    e = [list(ed.Poles) for ed in edges]

    # P1: corner poles on shared corners of the edge loop.
    # patch (u,v): (0,0) shared by edges 0+3, (0,3) by 0+1, (3,3) by 1+2,
    # (3,0) by 2+3 -- orientation within an edge is up to orient_a_to_b,
    # so each corner is matched against the two edge endpoints.
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

    # P3: surface normal field consistently oriented (catches folds/flips
    # on the evaluated surface; a raw control-net cross test false-positives
    # on legitimately twisted curved grids)
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


def check_patch33(patch, edges):
    """Check a Patch33 against its 3 driving edges.

    C1_corner_order : the 3 shared loop corners are on the right edges
    C2_boundary_match: row U0 / col V3 / row U3 match their driving edges
    C3_degenerate_pt: the U=0 control column collapses to a single point
    C4_surface_valid: Shape valid + no self-intersection + normal field
    Returns [(name, ok, detail), ...]; never raises.
    """
    try:
        return _check_patch33(patch, list(edges))
    except Exception as e:
        return [("structural", False, "oracle error: %r" % e)]


def _check_patch33(patch, edges):
    results = []
    errs = []
    if getattr(patch, "object_type", None) != "Patch33":
        errs.append("object_type=%r" % getattr(patch, "object_type", None))
    poles = list(patch.Poles)
    if len(poles) != 16:
        errs.append("%d poles (want 16)" % len(poles))
    if len(list(patch.Weights)) != 16:
        errs.append("%d weights (want 16)" % len(list(patch.Weights)))
    if not all(getattr(patch, "Poly%d" % i, None) for i in range(3)):
        errs.append("missing Poly0-2 edge links")
    if patch.Shape.isNull():
        errs.append("empty Shape")
    results.append(("structural", not errs, "; ".join(errs) if errs else
                    "object_type, 3 edge links, 16 poles/weights, shape"))
    if len(poles) != 16 or len(edges) != 3:
        return results

    e = [list(ed.Poles) for ed in edges]
    # C1: corners. (0,0) = point, shared by edges 0+2; (0,3) by 0+1;
    # (3,3) by 1+2. Match each corner against both edge endpoints.
    corner_errs = []
    for (u, v), (a, b) in [((0, 0), (0, 2)), ((0, 3), (0, 1)), ((3, 3), (1, 2))]:
        p = poles[u * 4 + v]
        for ei in (a, b):
            if not any(_dist(p, q) <= TOL for q in (e[ei][0], e[ei][3])):
                corner_errs.append("corner p%d%d not on edge%d" % (u, v, ei))
    results.append(("C1_corner_order", not corner_errs, "; ".join(corner_errs)
                    if corner_errs else "all 3 corners on shared loop corners"))

    # C2: boundary match. row U0=edge0, col V3=edge1, row U3=edge2.
    row_u0 = [poles[0], poles[1], poles[2], poles[3]]
    col_v3 = [poles[3], poles[7], poles[11], poles[15]]
    row_u3 = [poles[12], poles[13], poles[14], poles[15]]
    berrs = []
    for label, row, ep in [("row U0", row_u0, e[0]),
                           ("col V3", col_v3, e[1]),
                           ("row U3", row_u3, e[2])]:
        if not _multiset_match_within(row, ep, TOL):
            berrs.append("%s does not match its edge" % label)
    results.append(("C2_boundary_match", not berrs, "; ".join(berrs)
                    if berrs else "U0/V3/U3 boundaries match their edges"))

    # C3: U=0 control column collapses to a single point (the "point").
    col0 = [poles[i * 4] for i in range(4)]
    devs = [(_c - col0[0]).Length for _c in col0]
    results.append(("C3_degenerate_pt", all(d <= TOL for d in devs),
                    "U=0 column collapsed to a point" if all(d <= TOL for d in devs)
                    else "U=0 column not degenerate: dev %r" % devs))

    # C4: surface valid, no self-intersection, normal field consistent.
    try:
        surf = _build_bicubic(poles, list(patch.Weights))
        flips, any_normal = _normal_field_flips(surf)
        results.append(("C4_normal_field", bool(any_normal) and not flips,
                        "normal flips: %s" % ", ".join(flips) if flips else
                        ("no normal" if not any_normal else "consistent")))
    except Exception as e2:
        results.append(("C4_normal_field", False, "C4 error: %r" % e2))
    try:
        import MeshPart
        faces = patch.Shape.Faces
        if not faces:
            results.append(("C4_surface_valid", False, "no face in Shape"))
        else:
            surf2 = max(faces, key=lambda f: f.Area)
            valid = patch.Shape.isValid()
            mesh = MeshPart.meshFromShape(
                Shape=surf2, LinearDeflection=0.5, AngularDeflection=0.5, Relative=False)
            si = mesh.hasSelfIntersections()
            results.append(("C4_surface_valid", valid and not si,
                            "valid=%s, self-intersections=%s" % (valid, si)))
    except Exception as e2:
        results.append(("C4_surface_valid", False, "C4 error: %r" % e2))
    return results


def check_patch44(patch, edges):
    """Check a Patch44 against its 4 driving edges (explicit arguments --
    ground-truth patches store no links). Returns [(name, ok, detail), ...];
    never raises."""
    try:
        return _check_patch44(patch, list(edges))
    except Exception as e:
        return [("structural", False, "oracle error: %r" % e)]


# The blend strip width used by SilkBlend when it segments the patches'
# base surfaces perpendicular to the shared edge.
BLEND_STRIP_WIDTH = 0.1

# Tangent scale applied by SilkBlend when calling AN.blend_poly_2x4_1x6.
BLEND_TANGENT_SCALE = 2.0


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
    """
    edges = {(0, 1): "U0", (1, 2): "V1", (2, 3): "U1", (3, 0): "V0",
             (1, 0): "U0", (2, 1): "V1", (3, 2): "U1", (0, 3): "V0"}

    def adjacent(i, j):
        return (j - i) % 4 == 1 or (i - j) % 4 == 1

    matches = {i: [j for j in range(4)
                   if (a_c[i] - b_c[j]).Length < tol]
               for i in range(4)}
    for i in range(4):
        i2 = (i + 1) % 4
        if (a_c[i] - a_c[i2]).Length < tol:
            continue  # degenerate pair on the same patch
        for j in matches[i]:
            for j2 in matches[i2]:
                if not adjacent(j, j2):
                    continue
                if (b_c[j] - b_c[j2]).Length < tol:
                    continue  # degenerate pair on the other patch
                ea = edges.get((i, i2))
                eb = edges.get((j, j2))
                if ea and eb:
                    return ea, eb, [(i, j), (i2, j2)]
    return None


def _blend_reference_rows(pa, pb, tol=0.01):
    """Independently re-derive the 4 (l_rev, rc) strip-row pairs that drive
    a blend between two patches.

    Mirrors SilkBlend's blend run (shared seam detection, edge type,
    strip segmentation, corner-pair row mapping) so the oracle checks the
    stored blend poles against geometry it derived itself. Returns
    [(l_rev, rc), ...] (4 rows, each a list of 4 Vectors) or None when
    the patches do not share an edge.
    """
    a_c = [pa.Poles[0], pa.Poles[3], pa.Poles[15], pa.Poles[12]]
    b_c = [pb.Poles[0], pb.Poles[3], pb.Poles[15], pb.Poles[12]]
    seam = _detect_seam(a_c, b_c, tol)
    if seam is None:
        return None
    ea, eb, pairs = seam
    ss_a = 0 if ea[1] == "0" else 1
    ss_b = 0 if eb[1] == "0" else 1

    # #33: the blend band comes from the patch's own subgrid cells
    # (mirrors SilkBlend.run_blend band_cells/get_strip).
    def band_cells(p, etype, ss):
        from SilkPatch44 import _build_intervals
        ivs_u = _build_intervals(list(p.USplits or []))
        ivs_v = _build_intervals(list(p.VSplits or []))
        nu, nv = len(ivs_u), len(ivs_v)
        if etype[0] == "U":  # seam along U: band fixes V interval, spans U cells
            b = (nv - 1) if ss else 0
            keep_u = set(range(nu))
            if any(abs(s - 0.1) < 1e-9 for s in (p.USplits or [])):
                keep_u.discard(0)
            if any(abs(s - 0.9) < 1e-9 for s in (p.USplits or [])):
                keep_u.discard(nu - 1)
            return [a * nv + b for a in sorted(keep_u)]
        # seam along V: band fixes U interval, spans V cells
        a = (nu - 1) if ss else 0
        keep_v = set(range(nv))
        if any(abs(s - 0.1) < 1e-9 for s in (p.VSplits or [])):
            keep_v.discard(0)
        if any(abs(s - 0.9) < 1e-9 for s in (p.VSplits or [])):
            keep_v.discard(nv - 1)
        return [a * nv + b for b in sorted(keep_v)]

    def get_strip(p, etype, ss):
        idxs = band_cells(p, etype, ss)
        if len(idxs) != 1 or not p.Proxy._subgrids:
            return None
        return list(p.Proxy._subgrids[idxs[0]])

    sga = get_strip(pa, ea, ss_a)
    sgb = get_strip(pb, eb, ss_b)
    if sga is None or sgb is None:
        return None

    cmap = {"U0": {0: 0, 1: 3}, "U1": {2: 3, 3: 0},
            "V0": {0: 0, 3: 3}, "V1": {1: 0, 2: 3}}
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
    # shared->outer.
    va = range(4) if ss_a == 0 else range(3, -1, -1)   # left:  shared->outer
    vb = range(4) if ss_b == 0 else range(3, -1, -1)   # right: shared->outer
    rows = []
    for li in range(4):
        if ea[0] == "U":  # shared along U -> COLUMNS (const U)
            l_rev = list(reversed([sga[li * 4 + v] for v in va]))
        else:  # shared along V -> ROWS (const V)
            l_rev = list(reversed([sga[v * 4 + li] for v in va]))
        for lc_idx, rc_idx in pairs:
            rb = cmap[eb].get(rc_idx)
            if rb is not None and li == cmap[ea].get(lc_idx):
                ri = rb
                break
        else:
            ri = li if identity else 3 - li
        if eb[0] == "U":
            rc = [sgb[ri * 4 + v] for v in vb]
        else:
            rc = [sgb[v * 4 + ri] for v in vb]
        rows.append((l_rev, rc))
    return rows


def _check_blend(blend, pa, pb, reference_poles):
    results = []

    # structural (both blend types accepted: the unified "Blend" #39 and
    # the legacy "BlendStrip" that old documents / the GUI command create)
    st = getattr(blend, "object_type", None)
    poles = blend.Poles or []
    weights = blend.Weights or []
    ok = (st in ("Blend", "BlendStrip") and len(poles) == 24
          and len(weights) == 24 and all(abs(w - 1.0) < 1e-12 for w in weights)
          and pa is not None and pb is not None
          and getattr(blend, "Shape", None) is not None
          and not blend.Shape.isNull())
    results.append(("structural", ok,
                    "type=%s poles=%d weights=%d shape=%s" % (
                        st, len(poles), len(weights),
                        "ok" if ok else "bad")))

    rows = _blend_reference_rows(pa, pb, tol=getattr(blend, "tolerance", 0.01))
    if rows is None:
        results.append(("B1_c0_seams", False,
                        "no shared edge found between the patches"))
        results.append(("B2_c1_tangents", False,
                        "no shared edge found between the patches"))
        return results

    # B1: C0 -- each blend row's outer poles sit on the strip-curve
    # endpoints (row layout: [outer_L, t_L, inner_L, inner_R, t_R, outer_R])
    b1_dev = 0.0
    for i, (l_rev, rc) in enumerate(rows):
        row = poles[i * 6:i * 6 + 6]
        b1_dev = max(b1_dev, (row[0] - l_rev[0]).Length,
                     (row[5] - rc[3]).Length)
    results.append(("B1_c0_seams", b1_dev <= TOL,
                    "max endpoint deviation %.3e" % b1_dev))

    # B2: C1 construction -- the tangent poles must match the reference
    # blend of the independently derived strip rows
    import ArachNURBS as AN
    b2_dev = 0.0
    for i, (l_rev, rc) in enumerate(rows):
        ref_row = AN.blend_poly_2x4_1x6(
            l_rev, [1.0] * 4, rc, [1.0] * 4,
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


def _corner_reference_rows(strips, tol=0.01):
    """Independently derive each ring strip's corner-end row — the
    6-pole edge of the strip's blend surface at the corner-cell side.

    Mirrors SilkCorner's derivation from the patches' splits and band
    cells (not from the corner blend itself). Returns (rows,
    corner_cells) or (None, None) on any inconsistency.
    """
    from SilkBlend import band_cells, _patch_side
    from SilkPatch44 import _build_intervals
    rows = []
    corner_cells = {}
    for s in strips:
        pa, pb = s.PatchA, s.PatchB
        if pa is None or pb is None:
            return None, None
        e_a, ss_a = _patch_side(pa, pb, tol)
        e_b, ss_b = _patch_side(pb, pa, tol)
        if not e_a or not e_b:
            return None, None
        bca = band_cells(pa, e_a, ss_a)
        bcb = band_cells(pb, e_b, ss_b)
        if len(bca) != 1 or len(bcb) != 1:
            return None, None
        li_map = {}
        for pth, e, bc in ((pa, e_a, bca), (pb, e_b, bcb)):
            nu = len(_build_intervals(list(pth.USplits or [])))
            nv = len(_build_intervals(list(pth.VSplits or [])))
            iu_c = iv_c = None
            for t in strips:
                other = t.PatchB if t.PatchA is pth else t.PatchA
                if other is None:
                    continue
                te, tss = _patch_side(pth, other, tol)
                if not te:
                    continue
                if te[0] == "U":
                    iv_c = nv - 1 if te[1] == "1" else 0
                else:
                    iu_c = nu - 1 if te[1] == "1" else 0
            if iu_c is None or iv_c is None:
                return None, None
            iu_b, iv_b = divmod(bc[0], nv)
            if e[0] == "U":
                li_map[pth.Name] = 3 if iu_c > iu_b else 0
            else:
                li_map[pth.Name] = 3 if iv_c > iv_b else 0
            corner_cells[pth.Name] = (pth, iu_c, iv_c, nu, nv)
        if li_map[pa.Name] != li_map[pb.Name]:
            return None, None
        poles = s.Poles or []
        if len(poles) != 24:
            return None, None
        li = li_map[pa.Name]
        rows.append(list(poles[li * 6: li * 6 + 6]))
    return rows, corner_cells


def _check_corner_blend(cb, strips, reference_poles):
    results = []

    # structural
    st = getattr(cb, "object_type", None)
    poles = cb.Poles or []
    weights = cb.Weights or []
    ok = (st == "CornerBlend" and len(poles) == 36
          and len(weights) == 36 and all(abs(w - 1.0) < 1e-12 for w in weights)
          and len(list(getattr(cb, "Strips", []) or [])) == 4
          and getattr(cb, "Shape", None) is not None
          and not cb.Shape.isNull())
    results.append(("structural", ok,
                    "type=%s poles=%d weights=%d shape=%s" % (
                        st, len(poles), len(weights),
                        "ok" if ok else "bad")))

    rows, _ = _corner_reference_rows(
        strips, tol=getattr(cb, "tolerance", 0.01))
    if rows is None:
        results.append(("CB1_c0_boundary", False,
                        "could not derive corner-end rows from the strips"))
        results.append(("CB2_interior_fill", False,
                        "could not derive corner-end rows from the strips"))
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

    # CB2: interior fill -- all 36 poles must match the ControlGrid66_4
    # fill of the independently derived boundary rows
    try:
        import ArachNURBS as AN
        doc = cb.Document
        carriers = []
        for i, row in enumerate(rows):
            c = doc.addObject("Part::FeaturePython", "_cb_ref_poly")
            c.addProperty("App::PropertyVectorList", "Poles", "Internal",
                          "p").Poles
            c.addProperty("App::PropertyFloatList", "Weights", "Internal",
                          "w").Weights
            c.Poles = row
            c.Weights = [1.0] * 6
            carriers.append(c)
        grid = doc.addObject("Part::FeaturePython", "_cb_ref_grid")
        AN.ControlGrid66_4(grid, *carriers)
        grid.recompute()
        ref_poles = list(grid.Poles) if hasattr(grid, "Poles") else []
        doc.removeObject(grid.Name)
        for c in carriers:
            doc.removeObject(c.Name)
        if len(ref_poles) != 36:
            results.append(("CB2_interior_fill", False,
                            "reference fill produced %d poles" % len(ref_poles)))
        else:
            cb2_dev = max((p - r).Length for p, r in zip(poles, ref_poles))
            results.append(("CB2_interior_fill", cb2_dev <= TOL,
                            "max deviation from reference fill %.3e" % cb2_dev))
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
    """Corner blend oracle (CB1-CB4). Accepts the 4 ring strips either
    as 4 arguments or (as the only argument) as a list."""
    if isinstance(cb, (list, tuple)):
        strips = list(cb)
    else:
        strips = [strip0, strip1, strip2, strip3]
    return _check_corner_blend(cb, strips, reference_poles)


def check_blend(blend, patch_a, patch_b, reference_poles=None):
    """Check a Blend / legacy BlendStrip against its two patches
    (explicit arguments).

    reference_poles: optional 24-pole reference (e.g. the stored
    ground-truth blend) for the B4 full-pole match.

    Returns [(name, ok, detail), ...]; never raises.
    """
    try:
        return _check_blend(blend, patch_a, patch_b, reference_poles)
    except Exception as e:
        return [("structural", False, "oracle error: %r" % e)]
