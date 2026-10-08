"""
SilkChecks — the correctness oracle for workflow objects.

Each check_* function RETURNS a list of (name, ok, detail) tuples and
never raises: "is this correct?" is a query; deciding what a failure
means is the caller's job (tests assert on it, the future wizard will
display it).

Ticket #18: check_edge (structural + E1-E4). check_patch44 / check_blend
land with #19 / #20.

Check menu (locked in #14):
  E1  endpoints anchored to the driving sketch
  E2  pole order without jumps (a pole stays near its neighbors)
  E3  control polygon does not self-intersect
  E4  curve arc length bounded relative to chord + curve is valid

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
