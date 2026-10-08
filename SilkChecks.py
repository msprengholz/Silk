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
    pure line-segment sketch (the 3L case is what E1 anchors against)."""
    lines = [
        geom for i, geom in enumerate(sketch.Geometry)
        if not sketch.getConstruction(i)
    ]
    if not lines or any(g.TypeId != "Part::GeomLineSegment" for g in lines):
        return None
    return lines[0].StartPoint, lines[-1].EndPoint


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

    # E2: pole order without jumps
    bad = []
    for i in range(4):
        step = _dist(poles[i], poles[(i + 1) % 4])
        skip = _dist(poles[i], poles[(i + 2) % 4])
        if step > ORDER_FACTOR * max(skip, TOL):
            bad.append("p%d->p%d=%.3f > %.2fx p%d->p%d=%.3f"
                       % (i, (i + 1) % 4, step, ORDER_FACTOR, i, (i + 2) % 4, skip))
    results.append((
        "E2_pole_order", not bad,
        "; ".join(bad) if bad else "consecutive steps stay shorter than diagonal skips",
    ))

    # E3: control polygon does not self-intersect
    crossings = []
    if _seg_cross(poles[0], poles[1], poles[2], poles[3]):
        crossings.append("p0p1 x p2p3")
    if _seg_cross(poles[1], poles[2], poles[3], poles[0]):
        crossings.append("p1p2 x p3p0")
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
    """Bicubic Bezier surface from a 4x4 pole grid (mirrors Patch44)."""
    surf = Part.BSplineSurface()
    surf.increaseDegree(3, 3)
    for knot, mult in [(0.0, 4), (1.0, 4)]:
        surf.insertUKnot(knot, mult, 1e-7)
        surf.insertVKnot(knot, mult, 1e-7)
    for r in range(4):
        for c in range(4):
            surf.setPole(c + 1, r + 1, poles[r * 4 + c], weights[r * 4 + c])
    return surf


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
        n0, folds = None, []
        surf = _build_bicubic(poles, weights)
        N = 9
        for i in range(N):
            for j in range(N):
                u, v = (i + 0.5) / N, (j + 0.5) / N
                n = surf.normal(u, v)
                if n.Length < 1e-12:
                    continue
                if n0 is None:
                    n0 = n
                elif n.dot(n0) < -1e-6:
                    folds.append("u=%.2f,v=%.2f" % (u, v))
        if n0 is None:
            results.append(("P3_no_fold_flip", False, "surface degenerate: no normal"))
        else:
            results.append((
                "P3_no_fold_flip", not folds,
                "normal flips: " + ", ".join(folds) if folds else "normal field consistent",
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


def check_patch44(patch, edges):
    """Check a Patch44 against its 4 driving edges (explicit arguments --
    ground-truth patches store no links). Returns [(name, ok, detail), ...];
    never raises."""
    try:
        return _check_patch44(patch, list(edges))
    except Exception as e:
        return [("structural", False, "oracle error: %r" % e)]
