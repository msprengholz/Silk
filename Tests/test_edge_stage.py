"""
Edge stage (ticket #18): create_edge op + check_edge oracle.

Positive: a real edge built from a ControlPoly4 sketch via create_edge
passes the full oracle (structural + E1-E4) with no console errors.
Negative: deliberately corrupted pole states must be flagged by the
corresponding checks -- the oracle returns failures, it never raises.
"""

import FreeCAD
import Part

Vector = FreeCAD.Vector


def _make_3l_sketch(doc, name, pts):
    """ControlPoly4 sketch: 3 visible line segments through 4 points."""
    sk = doc.addObject("Sketcher::SketchObject", name)
    sk.addGeometry(Part.LineSegment(pts[0], pts[1]))
    sk.addGeometry(Part.LineSegment(pts[1], pts[2]))
    sk.addGeometry(Part.LineSegment(pts[2], pts[3]))
    doc.recompute()
    return sk


def _rect_pts(x=10.0, y=5.0):
    return [Vector(0, 0, 0), Vector(x, 0, 0), Vector(x, y, 0), Vector(0, y, 0)]


class _CaptureConsole:
    def __enter__(self):
        self.errors = []
        self._orig = FreeCAD.Console.PrintError
        FreeCAD.Console.PrintError = lambda m: (self.errors.append(str(m)), self._orig(m))
        return self

    def __exit__(self, *args):
        FreeCAD.Console.PrintError = self._orig


def test_create_edge_3l(doc):
    """create_edge builds a valid Edge from a 3-line sketch; oracle green."""
    errors, checks = [], []
    from SilkWorkflowOps import create_edge
    from SilkChecks import check_edge

    sk = _make_3l_sketch(doc, "Sketch", _rect_pts())
    with _CaptureConsole() as cap:
        edge = create_edge(sk, name="EdgeTest")
    if cap.errors:
        errors.append("console errors during create_edge: %s" % cap.errors)
    if edge is None or getattr(edge, "object_type", None) != "Edge":
        errors.append("create_edge did not return an Edge object")
        return {"pass": False, "errors": errors, "checks": checks}
    checks.append("create_edge returned %s with %d poles" % (edge.Name, len(edge.Poles)))

    results = check_edge(edge)
    bad = [(n, d) for (n, ok, d) in results if not ok]
    if bad:
        errors.append("oracle flagged a valid edge: %s" % bad)
    checks.append("oracle: %d checks, %d failed" % (len(results), len(bad)))
    return {"pass": not errors, "errors": errors, "checks": checks}


def test_oracle_flags_misordered_poles(doc):
    """Swapped middle poles -> the pole-order check (E2) must fail."""
    errors, checks = [], []
    from SilkWorkflowOps import create_edge
    from SilkChecks import check_edge

    sk = _make_3l_sketch(doc, "Sketch", _rect_pts())
    edge = create_edge(sk, name="EdgeTest")
    poles = list(edge.Poles)
    edge.Poles = [poles[0], poles[2], poles[1], poles[3]]

    results = check_edge(edge)
    failed = {n: d for (n, ok, d) in results if not ok}
    order_fails = [n for n in failed if "order" in n]
    if not order_fails:
        errors.append("mis-ordered poles not flagged; failed checks: %s" % failed)
    else:
        checks.append("pole-order check flagged: %s" % order_fails)
    return {"pass": not errors, "errors": errors, "checks": checks}


def test_oracle_flags_selfintersecting_polygon(doc):
    """Bowtie pole layout -> the self-intersection check (E3) must fail."""
    errors, checks = [], []
    from SilkWorkflowOps import create_edge
    from SilkChecks import check_edge

    sk = _make_3l_sketch(doc, "Sketch", _rect_pts())
    edge = create_edge(sk, name="EdgeTest")
    edge.Poles = [Vector(0, 0, 0), Vector(10, 5, 0), Vector(0, 5, 0), Vector(10, 0, 0)]

    results = check_edge(edge)
    failed = {n: d for (n, ok, d) in results if not ok}
    si_fails = [n for n in failed if "intersect" in n]
    if not si_fails:
        errors.append("self-intersecting polygon not flagged; failed checks: %s" % failed)
    else:
        checks.append("self-intersection check flagged: %s" % si_fails)
    return {"pass": not errors, "errors": errors, "checks": checks}


def test_oracle_flags_excessive_arc(doc):
    """Poles far from the chord -> the arc/chord check (E4) must fail."""
    errors, checks = [], []
    from SilkWorkflowOps import create_edge
    from SilkChecks import check_edge

    sk = _make_3l_sketch(doc, "Sketch", _rect_pts())
    edge = create_edge(sk, name="EdgeTest")
    edge.Poles = [Vector(0, 0, 0), Vector(5, 30, 0), Vector(5, 30, 0), Vector(10, 0, 0)]

    results = check_edge(edge)
    failed = {n: d for (n, ok, d) in results if not ok}
    arc_fails = [n for n in failed if "arc" in n]
    if not arc_fails:
        errors.append("excessive arc/chord not flagged; failed checks: %s" % failed)
    else:
        checks.append("arc/chord check flagged: %s" % arc_fails)
    return {"pass": not errors, "errors": errors, "checks": checks}


def test_edge_2n(doc):
    """Edge from 2 sketches (2N mode: circle+line each), built
    through the SilkEdge.CreateEdge GUI command (ported from the
    retired test_patch44_comprehensive.py -- the Edge 2N GUI path
    is otherwise only covered headlessly via the create_edge op)."""
    errors, checks = [], []
    from FreeCAD import Gui
    import SilkEdge

    sk1 = doc.addObject("Sketcher::SketchObject", "SK_A")
    sk1.Placement = FreeCAD.Placement(Vector(88.4507, 0, 9.0377),
                                      FreeCAD.Rotation(-90, 0, 45.5543))
    sk1.addGeometry([
        Part.Circle(Vector(0, 0, 0), Vector(0, 0, 1), 10.995),
        Part.LineSegment(Vector(0, 0, 0), Vector(-14.4129, 29.393, 0)),
    ])
    sk2 = doc.addObject("Sketcher::SketchObject", "SK_B")
    sk2.Placement = FreeCAD.Placement(Vector(138.2692, 50, 0),
                                      FreeCAD.Rotation(-113.309, 0, 90))
    sk2.addGeometry([
        Part.Circle(Vector(0, 0, 0), Vector(0, 0, 1), 9.1779),
        Part.LineSegment(Vector(0, 0, 0), Vector(20.5843, 19.925, 0)),
    ])
    doc.recompute()

    Gui.Selection.clearSelection()
    Gui.Selection.addSelection(sk1)
    Gui.Selection.addSelection(sk2)
    SilkEdge.CreateEdge().Activated()
    doc.recompute()

    edges = [o for o in doc.Objects
             if hasattr(o, "object_type") and o.object_type == "Edge"]
    if not (len(edges) >= 1):
        errors.append("Expected >=1 Edge, got %d" % len(edges))
    if edges:
        e = edges[-1]
        if len(e.Poles) != 4:
            errors.append("Expected 4 poles, got %d" % len(e.Poles))
        if len(e.Sketches) != 2:
            errors.append("Expected 2 sketches, got %d"
                          % len(e.Sketches))
        checks.append("2N Edge: %d poles from %d sketches"
                      % (len(e.Poles), len(e.Sketches)))

    return {"pass": not errors, "errors": errors, "checks": checks}


ALL_TESTS = [
    test_create_edge_3l,
    test_oracle_flags_misordered_poles,
    test_oracle_flags_selfintersecting_polygon,
    test_oracle_flags_excessive_arc,
    test_edge_2n,
]
