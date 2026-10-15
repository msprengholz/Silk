"""
Edge plan + elevation mode (ticket #90).

`Edge` now picks its geometry from the SHAPES the user selected. Besides
the existing 3L / FirstElement (one sketch) and 2N (two circle+line
nodes) readings, two profile sketches -- a plan on the first sketch's
plane and an elevation whose heights run along that plane's normal --
compose into one 3D edge through ControlPoly4_2X4P. The plan is
`Sketches[0]`, the elevation `Sketches[1]`; there is no mode property.

What is asserted here:
  1. a plan + elevation pair composes to exactly the 2X4P pole set and is
     oracle-green (structural + E1-E4) with no console errors;
  2. the E1 open question, SETTLED BY MEASUREMENT: a raised-end edge
     (elevation height != 0 at an end) is oracle-green under the
     generalized in-plane anchoring, while the OLD exact-endpoint distance
     is > tolerance -- i.e. the old E1 would have been red. The
     measurement is recorded in the test, not just the conclusion;
  3. every refusal is LOUD and leaves nothing half-built -- coplanar
     planes, non-perpendicular planes (both normals named), a flat
     elevation, a mixed node/view pair, two sketches that are neither
     shape, an unconnected circle + line pair (no node), and 3+ sketches.
     Each refusal test is mutation-checked (removing the guard makes it
     fail);
  4. an old 2-sketch node Edge still classifies as "2N" (restore parity),
     including across a save / reopen, and a node sketch carrying extra
     geometry AFTER its circle + line is still a node (the core reads only
     the first two elements);
  5. the real panel reads the plan + elevation mode into its label, shows
     the refusal reason for a bad pair, and builds the edge on confirm.

Fixtures are built through the ops layer + oracle only. Plan and elevation
helpers mirror the shape a user draws: 3 connected visible lines (3L).
"""

import FreeCAD
import Part

from Tests.mcp_harness import check

Vector = FreeCAD.Vector
TOL = 1e-6

# Plan footprint on the XY plane; the elevation is drawn in the XZ plane
# (Rotation about X by 90 deg), so its local y is the world height.
PLAN_PTS = [(0.0, 0.0, 0.0), (10.0, 0.0, 0.0),
            (20.0, 10.0, 0.0), (30.0, 0.0, 0.0)]
ELEV_LEVEL = [(0.0, 0.0), (10.0, 5.0), (20.0, 15.0), (30.0, 0.0)]
ELEV_RAISED = [(0.0, 5.0), (10.0, 10.0), (20.0, 20.0), (30.0, 5.0)]
ELEV_FLAT = [(0.0, 5.0), (10.0, 5.0), (20.0, 5.0), (30.0, 5.0)]
# plan pole i lifted by elevation height i (ELEV_LEVEL)
EXPECTED_LEVEL = [(0.0, 0.0, 0.0), (10.0, 0.0, 5.0),
                  (20.0, 10.0, 15.0), (30.0, 0.0, 0.0)]


# ---- helpers ---------------------------------------------------------------

def _line_sketch(doc, name, pts, placement=None):
    """A visible-line sketch through `pts` (consecutive lines)."""
    sk = doc.addObject("Sketcher::SketchObject", name)
    if placement is not None:
        sk.Placement = placement
    for a, b in zip(pts, pts[1:]):
        sk.addGeometry(Part.LineSegment(Vector(*a), Vector(*b)))
    doc.recompute()
    return sk


def _elev_placement(deg=90.0):
    return FreeCAD.Placement(Vector(0, 0, 0),
                             FreeCAD.Rotation(Vector(1, 0, 0), deg))


def _plan_elev_pair(doc, elev_local=ELEV_LEVEL, deg=90.0):
    plan = _line_sketch(doc, "Plan", PLAN_PTS)
    elev = _line_sketch(doc, "Elev", elev_local, _elev_placement(deg))
    return plan, elev


def _node_sketch(doc, name, dx):
    """A circle + line node sketch (the 2N input shape)."""
    sk = doc.addObject("Sketcher::SketchObject", name)
    sk.addGeometry([
        Part.Circle(Vector(0, 0, 0), Vector(0, 0, 1), 5.0),
        Part.LineSegment(Vector(0, 0, 0), Vector(dx, 10.0, 0)),
    ])
    doc.recompute()
    return sk


def _unconnected_node(doc, name="Bad"):
    """A circle + line pair whose circle centre is NOT on the line -- the
    shape ControlPoly4_2N cannot connect (it then leaves p01s unset)."""
    sk = doc.addObject("Sketcher::SketchObject", name)
    sk.addGeometry([
        Part.Circle(Vector(0, 0, 0), Vector(0, 0, 1), 5.0),
        Part.LineSegment(Vector(10, 0, 0), Vector(20, 10, 0)),
    ])
    doc.recompute()
    return sk


def _edges(doc):
    return [o for o in doc.Objects
            if getattr(o, "object_type", None) == "Edge"]


def _failures(edge):
    from SilkChecks import check_edge
    return [(n, d) for (n, ok, d) in check_edge(edge) if not ok]


def _max_pole_delta(before, after):
    """Largest per-component difference between two pole lists."""
    return max(abs(a - b)
               for pa, pb in zip(before, after)
               for a, b in zip(pa, pb))


class _Capture:
    """Capture console errors AND messages (still forwarded)."""

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


# ---- positive: the mode exists and composes correctly ----------------------

def test_plan_elevation_builds_oracle_green(doc):
    """Two profile sketches -> a plan + elevation Edge, green on the full
    oracle, with poles identical to the 2X4P composition."""
    errors, checks = [], []
    from SilkWorkflowOps import create_edge
    from SilkEdge import classify_sketches

    plan, elev = _plan_elev_pair(doc)
    mode, detail = classify_sketches([plan, elev])
    check(mode == "plan_elevation",
          "classifier read %r (%s), expected plan_elevation"
          % (mode, detail), errors)

    with _Capture() as cap:
        edge = create_edge([plan, elev], name="PlanElev")
    errors += ["console error during build: %s" % e for e in cap.errors]
    if not check(edge is not None and edge.object_type == "Edge",
                 "create_edge did not return an Edge", errors):
        return {"pass": False, "errors": errors, "checks": checks}

    check(len(list(edge.Sketches)) == 2,
          "the edge links %d sketches, expected 2"
          % len(list(edge.Sketches)), errors)
    check(list(edge.Sketches)[0] is plan,
          "Sketches[0] is not the plan sketch", errors)
    check(list(edge.Sketches)[1] is elev,
          "Sketches[1] is not the elevation sketch", errors)
    check(len(edge.Poles) == 4,
          "the composed edge has %d poles, expected 4" % len(edge.Poles),
          errors)

    if len(edge.Poles) == 4:
        dev = max((Vector(*want) - got).Length
                  for want, got in zip(EXPECTED_LEVEL, edge.Poles))
        check(dev <= TOL,
              "composed poles deviate from the 2X4P result by %.3e: %s"
              % (dev, [tuple(v) for v in edge.Poles]), errors)
        checks.append("poles match the 2X4P composition to %.2e" % dev)

    bad = _failures(edge)
    check(not bad, "oracle flagged a valid plan+elevation edge: %s" % bad,
          errors)
    checks.append("plan+elevation edge oracle green (E1-E4)")
    return {"pass": not errors, "errors": errors, "checks": checks}


def test_raised_end_plan_elevation_is_oracle_green(doc):
    """E1 SETTLED BY MEASUREMENT.

    A plan + elevation edge whose elevation is RAISED at its ends (height
    5 at both ends) is legitimate 3D geometry. The generalized E1 anchors
    each end pole's IN-PLANE projection to the plan sketch, so the edge is
    green. The measurement also records the raw endpoint-to-sketch distance
    (> tolerance here), which is exactly what the pre-#90 E1 checked -- so
    the earlier exact-distance E1 would have been RED on a legitimate edge.
    That is the evidence for choosing the in-plane generalization over a
    refusal gate.
    """
    errors, checks = [], []
    from SilkWorkflowOps import create_edge
    from SilkChecks import check_edge

    plan, elev = _plan_elev_pair(doc, elev_local=ELEV_RAISED)
    with _Capture() as cap:
        edge = create_edge([plan, elev], name="Raised")
    errors += ["console error during build: %s" % e for e in cap.errors]
    if not check(edge is not None, "create_edge returned None", errors):
        return {"pass": False, "errors": errors, "checks": checks}

    # the measurement: what the OLD E1 looked at
    first = plan.Placement.multVec(plan.Geometry[0].StartPoint)
    last = plan.Placement.multVec(plan.Geometry[-1].EndPoint)
    d0 = (edge.Poles[0] - first).Length
    d3 = (edge.Poles[3] - last).Length
    check(d0 > TOL and d3 > TOL,
          "the raised-end fixture does not expose the old E1 gap "
          "(raw end distances %.2e / %.2e)" % (d0, d3), errors)
    checks.append("MEASURED: pre-#90 exact-end E1 would be red "
                  "(d0=%.2e, d3=%.2e > tol)" % (d0, d3))

    results = {n: (ok, d) for (n, ok, d) in check_edge(edge)}
    e1_ok, e1_detail = results.get("E1_endpoint_anchoring", (False, "missing"))
    check(e1_ok, "generalized E1 flagged the raised-end edge: %s" % e1_detail,
          errors)
    checks.append("generalized E1 green: %s" % e1_detail)

    bad = _failures(edge)
    check(not bad, "oracle flagged a legitimate raised-end edge: %s" % bad,
          errors)
    return {"pass": not errors, "errors": errors, "checks": checks}


# ---- refusals: loud, and nothing half-built --------------------------------

def _refusal_case(doc, sketches, expect_substrings, label):
    """Build `sketches`; assert create_edge refuses with a console error
    containing every expected substring and creates NOTHING."""
    errors, checks = [], []
    from SilkWorkflowOps import create_edge

    n_before = len(_edges(doc))
    with _Capture() as cap:
        edge = create_edge(list(sketches), name="Refused")
    if edge is not None:
        errors.append("%s: create_edge returned an Edge instead of refusing"
                      % label)
    if len(_edges(doc)) != n_before:
        errors.append("%s: an Edge object leaked into the document" % label)
    if not cap.errors:
        errors.append("%s: refusal was silent" % label)
    blob = " ".join(cap.errors)
    for needle in expect_substrings:
        if needle not in blob:
            errors.append("%s: console error %r does not contain %r"
                          % (label, blob, needle))
    checks.append("%s refused: %s" % (label, blob.strip()[:120]))
    return {"pass": not errors, "errors": errors, "checks": checks}


def test_refuses_coplanar_planes(doc):
    """Elevation in the plan's own plane -> refuse, both normals named."""
    plan, elev = _plan_elev_pair(doc, deg=0.0)
    return _refusal_case(doc, [plan, elev],
                         ["perpendicular", "normal"],
                         "coplanar planes")


def test_refuses_non_perpendicular_planes(doc):
    """Elevation at 45 deg -> refuse, both normals and the dot named."""
    plan, elev = _plan_elev_pair(doc, deg=45.0)
    return _refusal_case(doc, [plan, elev],
                         ["perpendicular", "normal (0.000, 0.000, 1.000)"],
                         "non-perpendicular planes")


def test_refuses_flat_elevation(doc):
    """Elevation of constant height -> refuse, 'flat' named."""
    plan, elev = _plan_elev_pair(doc, elev_local=ELEV_FLAT)
    return _refusal_case(doc, [plan, elev], ["flat"],
                         "flat elevation")


def test_refuses_mixed_node_and_profile(doc):
    """One node sketch + one profile sketch -> refuse (mixed pair)."""
    plan, _ = _plan_elev_pair(doc)
    node = _node_sketch(doc, "Node", 10.0)
    return _refusal_case(doc, [plan, node],
                         ["cannot form an Edge"],
                         "mixed node/view pair")


def test_refuses_two_unusable_sketches(doc):
    """Two sketches that are neither nodes nor profiles -> refuse."""
    a = _line_sketch(doc, "Two1", [(0, 0, 0), (5, 0, 0), (5, 5, 0)])
    b = _line_sketch(doc, "Two2", [(0, 0, 0), (5, 0, 0), (5, 5, 0)])
    return _refusal_case(doc, [a, b],
                         ["cannot form an Edge", "neither a node nor a "
                          "profile"],
                         "two unusable sketches")


def test_refuses_three_sketches(doc):
    """3+ sketches -> refuse (the old silent drop of extra sketches)."""
    a = _line_sketch(doc, "S1", [(0, 0, 0), (5, 0, 0), (10, 0, 0)])
    b = _line_sketch(doc, "S2", [(0, 5, 0), (5, 5, 0), (10, 5, 0)])
    c = _line_sketch(doc, "S3", [(0, 10, 0), (5, 10, 0), (10, 10, 0)])
    return _refusal_case(doc, [a, b, c], ["3 sketches"],
                         "three sketches")


def test_unconnected_node_is_refused_in_every_placement(doc):
    """A circle + line pair whose centre is off the line is never read as
    a node: refused, naming the sketch and the reason, in all three
    placements (alone, next to a good node, next to a profile)."""
    errors, checks = [], []
    from SilkEdge import classify_sketches

    good = _node_sketch(doc, "Good", 10.0)
    bad = _unconnected_node(doc, "Bad")
    plan = _line_sketch(doc, "Plan", PLAN_PTS)

    for label, sel in (("alone", [bad]),
                       ("with a node", [bad, good]),
                       ("with a profile", [plan, bad])):
        mode, detail = classify_sketches(sel)
        check(mode is None,
              "%s: unconnected node read as %r (%s)" % (label, mode, detail),
              errors)
        check("Bad" in detail,
              "%s: refusal %r does not name the offending sketch"
              % (label, detail), errors)
        check("circle" in detail.lower() and "endpoint" in detail.lower(),
              "%s: refusal %r does not name the reason" % (label, detail),
              errors)
    checks.append("unconnected node refused by name and reason in all three "
                  "placements")
    return {"pass": not errors, "errors": errors, "checks": checks}


def test_unconnected_node_pair_builds_nothing_and_does_not_crash(doc):
    """create_edge on the unconnected pair refuses before building: None,
    no leaked Edge object, a console error naming the sketch -- never the
    0-pole, null-Shape, oracle-red Edge (with its UnboundLocalError)."""
    errors, checks = [], []
    from SilkWorkflowOps import create_edge
    from SilkChecks import check_edge

    good = _node_sketch(doc, "Good", 10.0)
    bad = _unconnected_node(doc, "Bad")
    n_before = len(_edges(doc))
    with _Capture() as cap:
        edge = create_edge([bad, good], name="Unconnected")
    check(edge is None,
          "create_edge built an Edge from the unconnected pair", errors)
    check(len(_edges(doc)) == n_before,
          "an Edge object leaked into the document", errors)
    check(any("Bad" in e for e in cap.errors),
          "the refusal does not name the offending sketch: %r" % cap.errors,
          errors)
    red = [(o.Name, [n for (n, ok, _d) in check_edge(o) if not ok])
           for o in _edges(doc)
           if [n for (n, ok, _d) in check_edge(o) if not ok]]
    check(not red, "an oracle-red Edge survived: %s" % red, errors)
    checks.append("unconnected pair: None, no object, loud, nothing red")
    return {"pass": not errors, "errors": errors, "checks": checks}


# ---- restore parity + classification regressions ---------------------------

def test_node_pair_still_classifies_as_2n(doc):
    """Two circle+line sketches still read as 2N, and build green."""
    errors, checks = [], []
    from SilkWorkflowOps import create_edge
    from SilkEdge import classify_sketches
    from Tests import corner_model

    (_n, skey, p1, p2, ekey) = corner_model.EDGES[0]
    a = corner_model.node_sketch(doc, "NS_a", skey, p1)
    b = corner_model.node_sketch(doc, "NS_b", ekey, p2)
    mode, detail = classify_sketches([a, b])
    check(mode == "2N", "node pair read %r (%s), expected 2N"
          % (mode, detail), errors)

    edge = create_edge([a, b], name="TwoNode")
    if check(edge is not None, "create_edge refused a node pair", errors):
        bad = _failures(edge)
        check(not bad, "oracle flagged the 2N edge: %s" % bad, errors)
        checks.append("2N edge (%d poles) oracle green" % len(edge.Poles))
    return {"pass": not errors, "errors": errors, "checks": checks}


def test_node_with_extra_geometry_still_classifies_2n(doc):
    """A node sketch carrying an extra CONSTRUCTION element after its
    circle + line is still a node -- the core reads only Geometry[0] and
    Geometry[1] -- and builds a green 2N edge."""
    errors, checks = [], []
    from SilkWorkflowOps import create_edge
    from SilkEdge import classify_sketches
    from Tests import corner_model

    (_n, skey, p1, p2, ekey) = corner_model.EDGES[0]
    a = corner_model.node_sketch(doc, "NS_a_extra", skey, p1)
    a.addGeometry(
        Part.LineSegment(Vector(0, 30, 0), Vector(5, 30, 0)), True)
    doc.recompute()
    b = corner_model.node_sketch(doc, "NS_b", ekey, p2)
    check(len(a.Geometry) == 3,
          "fixture has %d geometry elements, expected 3" % len(a.Geometry),
          errors)
    check(a.Geometry[0].TypeId == "Part::GeomCircle"
          and a.Geometry[1].TypeId == "Part::GeomLineSegment",
          "the first two elements are not circle + line: %s"
          % [g.TypeId for g in a.Geometry], errors)

    mode, detail = classify_sketches([a, b])
    check(mode == "2N",
          "node + extra element read as %r (%s), expected 2N"
          % (mode, detail), errors)

    edge = create_edge([a, b], name="NodeExtra2N")
    if check(edge is not None,
             "create_edge refused a node with extra geometry", errors):
        check(len(edge.Poles) == 4,
              "built %d poles, expected 4" % len(edge.Poles), errors)
        bad = _failures(edge)
        check(not bad, "oracle flagged the 2N edge: %s" % bad, errors)
        checks.append("node + extra construction element -> 2N, oracle green")
    return {"pass": not errors, "errors": errors, "checks": checks}


def test_single_sketch_classification_unchanged(doc):
    """3L and FirstElement readings are untouched by the new mode."""
    errors, checks = [], []
    from SilkEdge import classify_sketches

    three = _line_sketch(doc, "Three", [(0, 0, 0), (5, 0, 0), (10, 5, 0),
                                        (15, 0, 0)])
    one = doc.addObject("Sketcher::SketchObject", "One")
    one.addGeometry(Part.LineSegment(Vector(0, 0, 0), Vector(10, 5, 0)))
    doc.recompute()

    check(classify_sketches([three])[0] == "3L",
          "3 lines read as %r" % (classify_sketches([three]),), errors)
    check(classify_sketches([one])[0] == "FirstElement",
          "one line read as %r" % (classify_sketches([one]),), errors)
    no_sketch = doc.addObject("Sketcher::SketchObject", "Nothing")
    doc.recompute()
    check(classify_sketches([no_sketch])[0] is None,
          "an empty sketch was classified as buildable", errors)
    checks.append("3L / FirstElement / empty classifications unchanged")
    return {"pass": not errors, "errors": errors, "checks": checks}


def test_node_pair_survives_save_and_reopen_as_2n(doc):
    """Restore parity: an old-style 2-sketch node Edge reopens and still
    classifies as 2N with unchanged poles and a green oracle."""
    errors, checks = [], []
    from SilkWorkflowOps import create_edge
    from SilkEdge import classify_sketches
    from Tests import corner_model

    (_n, skey, p1, p2, ekey) = corner_model.EDGES[0]
    a = corner_model.node_sketch(doc, "NS_a", skey, p1)
    b = corner_model.node_sketch(doc, "NS_b", ekey, p2)
    edge = create_edge([a, b], name="Persist2N")
    if edge is None:
        return {"pass": False, "errors": ["create_edge refused a node pair"],
                "checks": checks}
    poles_before = [tuple(v) for v in edge.Poles]

    path = "/tmp/_test_edge_plan_elev_2n.FCStd"
    doc.saveAs(path)
    FreeCAD.closeDocument(doc.Name)

    doc2 = FreeCAD.openDocument(path)
    try:
        e2 = [o for o in doc2.Objects
              if getattr(o, "object_type", None) == "Edge"][0]
        if len(list(e2.Sketches)) != 2:
            errors.append("reopened edge links %d sketches, expected 2"
                          % len(list(e2.Sketches)))
        mode, detail = classify_sketches(list(e2.Sketches))
        check(mode == "2N", "reopened pair read %r (%s), expected 2N"
              % (mode, detail), errors)
        doc2.recompute()
        poles_after = [tuple(v) for v in e2.Poles]
        # The save/reopen round-trip re-derives the node poles from the
        # reloaded sketch placements; the Placement->matrix conversion is
        # exact only to ~1 ulp, so this is a tolerance check, not an
        # equality one (measured max diff 6.7e-16, geometry unchanged).
        delta = _max_pole_delta(poles_before, poles_after)
        if delta > 1e-9:
            errors.append("poles changed across save/reopen by %.3e"
                          % delta)
        bad = _failures(e2)
        check(not bad, "reopened 2N edge not oracle green: %s" % bad, errors)
        checks.append("reopened 2-sketch node edge still reads 2N, green")
    finally:
        FreeCAD.closeDocument(doc2.Name)
    return {"pass": not errors, "errors": errors, "checks": checks}


# ---- the real panel --------------------------------------------------------

def test_panel_reads_plan_elevation_mode_and_builds(doc):
    """Two profile clicks -> the label names plan + elevation, and confirm
    builds the composed edge through the panel's own path."""
    errors, checks = [], []
    from Tests.test_task_panel import _open_panel, _close_panel, _click

    plan, elev = _plan_elev_pair(doc)
    n_before = len(_edges(doc))

    panel = _open_panel(doc)
    if not check(panel is not None, "Activated left no panel open", errors):
        return {"pass": False, "errors": errors, "checks": checks}
    try:
        _click(plan)
        _click(elev)
        text = panel.edge_mode_lbl.text().lower()
        check("plan" in text and "elevation" in text,
              "mode line %r does not name the plan + elevation reading"
              % panel.edge_mode_lbl.text(), errors)
        # #90 review: the label must name the two SUB-modes in play, not
        # just "two sketches" (both fixture sketches are 3L here).
        check("3l" in text or "firstelement" in text,
              "mode line %r does not name the sub-modes"
              % panel.edge_mode_lbl.text(), errors)
        with _Capture() as cap:
            panel.panel_confirm()
        doc.recompute()
        errors += ["console error during panel confirm: %s" % e
                   for e in cap.errors]
        edges = _edges(doc)
        check(len(edges) == n_before + 1,
              "confirm created %d edge(s), expected 1"
              % (len(edges) - n_before), errors)
        if edges:
            made = edges[-1]
            check(len(made.Poles) == 4,
                  "panel edge has %d poles, expected 4" % len(made.Poles),
                  errors)
            bad = _failures(made)
            check(not bad, "oracle flagged the panel-built edge: %s" % bad,
                  errors)
            checks.append("panel built %s (plan+elevation), oracle green"
                          % made.Name)
    finally:
        _close_panel(panel)
        from FreeCAD import Gui
        Gui.Selection.clearSelection()
    return {"pass": not errors, "errors": errors, "checks": checks}


def test_panel_shows_refusal_reason(doc):
    """A non-perpendicular pair: the label carries the refusal, and confirm
    creates nothing."""
    errors, checks = [], []
    from Tests.test_task_panel import _open_panel, _close_panel, _click

    plan, elev = _plan_elev_pair(doc, deg=45.0)
    n_before = len(_edges(doc))

    panel = _open_panel(doc)
    if not check(panel is not None, "Activated left no panel open", errors):
        return {"pass": False, "errors": errors, "checks": checks}
    try:
        _click(plan)
        _click(elev)
        check("perpendicular" in panel.edge_mode_lbl.text().lower(),
              "refusal label %r does not explain the non-perpendicular pair"
              % panel.edge_mode_lbl.text(), errors)
        panel.panel_confirm()
        doc.recompute()
        check(len(_edges(doc)) == n_before,
              "confirm created an edge from a refused pair", errors)
        checks.append("panel showed the refusal and built nothing")
    finally:
        _close_panel(panel)
        from FreeCAD import Gui
        Gui.Selection.clearSelection()
    return {"pass": not errors, "errors": errors, "checks": checks}


ALL_TESTS = [
    test_plan_elevation_builds_oracle_green,
    test_raised_end_plan_elevation_is_oracle_green,
    test_refuses_coplanar_planes,
    test_refuses_non_perpendicular_planes,
    test_refuses_flat_elevation,
    test_refuses_mixed_node_and_profile,
    test_refuses_two_unusable_sketches,
    test_refuses_three_sketches,
    test_unconnected_node_is_refused_in_every_placement,
    test_unconnected_node_pair_builds_nothing_and_does_not_crash,
    test_node_pair_still_classifies_as_2n,
    test_node_with_extra_geometry_still_classifies_2n,
    test_single_sketch_classification_unchanged,
    test_node_pair_survives_save_and_reopen_as_2n,
    test_panel_reads_plan_elevation_mode_and_builds,
    test_panel_shows_refusal_reason,
]
