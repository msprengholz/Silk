"""
GUI command tests for the unified Patch (#42).

The retired test_patch44.py / test_patch44_comprehensive.py exercised
the old Silk_Patch44 GUI command through Gui.Selection; these tests
do the same for the replacement Silk_CreatePatch command (selection-
driven, one type per process step), plus the getSubgrid API that
lived in the comprehensive file (ported onto the unified Patch).
"""

# --- manual tier ------------------------------------------------------
# A GUI command drive, the sibling of the already-deferred
# test_blend_gui_command / test_corner_gui_command.
# So this module is NOT in the default (fast) tier. Run it with
# `python3 Tests/run_all.py --manual` (or by name as a filter);
# Tests/test_manual_tier.py asserts it stays importable and keeps tests.
MANUAL = True


import FreeCAD
import Part
from FreeCAD import Gui, Vector
from Tests.mcp_harness import check


class _CaptureConsole:
    """Collect the console errors a command emits (AGENTS.md's
    console-error capture), so a refusal can be asserted on its
    message, not just on the absence of a created object."""

    def __enter__(self):
        self.errors = []
        self._orig = FreeCAD.Console.PrintError
        FreeCAD.Console.PrintError = (
            lambda m: (self.errors.append(str(m)), self._orig(m)))
        return self

    def __exit__(self, *args):
        FreeCAD.Console.PrintError = self._orig


def _make_loop_edges(doc):
    """Four 4-pole loop edges forming a closed square (real Edge
    objects via the ops layer, cyclic order e0..e3)."""
    from SilkWorkflowOps import create_edge
    pts = {
        "edge0": [Vector(0, 0, 0), Vector(16.7, 0, 0),
                  Vector(33.3, 0, 0), Vector(50, 0, 0)],
        "edge1": [Vector(50, 0, 0), Vector(50, 16.7, 0),
                  Vector(50, 33.3, 0), Vector(50, 50, 0)],
        "edge2": [Vector(50, 50, 0), Vector(33.3, 50, 0),
                  Vector(16.7, 50, 0), Vector(0, 50, 0)],
        "edge3": [Vector(0, 50, 0), Vector(0, 33.3, 0),
                  Vector(0, 16.7, 0), Vector(0, 0, 0)],
    }
    edges = []
    for i in range(4):
        sk = doc.addObject("Sketcher::SketchObject", "Sketch%d" % i)
        for j in range(3):
            sk.addGeometry(Part.LineSegment(
                pts["edge%d" % i][j], pts["edge%d" % i][j + 1]))
        doc.recompute()
        edges.append(create_edge(sk, name="Edge%d" % i))
    return edges


def _make_triangle_edges(doc):
    """Three 4-pole loop edges forming a closed triangle, cyclic
    order e0..e2 (the pointed fill's degenerate point sits at the
    corner shared by edges 0+2)."""
    from SilkWorkflowOps import create_edge
    pts = {
        "edge0": [Vector(0, 0, 0), Vector(16.7, 0, 0),
                  Vector(33.3, 0, 0), Vector(50, 0, 0)],
        "edge1": [Vector(50, 0, 0), Vector(25, 33.3, 0),
                  Vector(25, 66.7, 0), Vector(0, 50, 0)],
        "edge2": [Vector(0, 50, 0), Vector(0, 33.3, 0),
                  Vector(0, 16.7, 0), Vector(0, 0, 0)],
    }
    edges = []
    for i in range(3):
        sk = doc.addObject("Sketcher::SketchObject", "SketchT%d" % i)
        for j in range(3):
            sk.addGeometry(Part.LineSegment(
                pts["edge%d" % i][j], pts["edge%d" % i][j + 1]))
        doc.recompute()
        edges.append(create_edge(sk, name="TEdge%d" % i))
    return edges


def _patches(doc):
    return [o for o in doc.Objects
            if getattr(o, "object_type", None) == "Patch"]


def test_create_patch_gui_4_edges(doc):
    """Silk_CreateBlend-style selection flow: select 4 Edge
    objects -> Silk_CreatePatch -> ONE unified Patch (quad fill,
    16 poles), oracle green. Mirrors the retired Patch44 GUI
    command tests on the unified command."""
    errors, checks = [], []
    from SilkPatch import CreatePatch
    from SilkChecks import check_patch

    edges = _make_loop_edges(doc)
    Gui.Selection.clearSelection()
    for e in edges:
        Gui.Selection.addSelection(e)
    CreatePatch().Activated()
    doc.recompute()

    patches = _patches(doc)
    check(len(patches) == 1,
          "expected exactly 1 unified Patch, got %d" % len(patches),
          errors)
    if not patches:
        return {"pass": False, "errors": errors, "checks": checks}
    p = patches[0]
    check(len(p.Poles) == 16,
          "expected 16 poles, got %d" % len(p.Poles), errors)
    check(len(list(p.Edges)) == 4,
          "expected 4 Edges links, got %d" % len(list(p.Edges)),
          errors)
    checks.append("Silk_CreatePatch(4 edges) -> %s (%d poles)"
                  % (p.Name, len(p.Poles)))

    results = check_patch(p, edges)
    bad = [(n, d) for (n, ok, d) in results if not ok]
    if bad:
        errors.append("oracle flagged the GUI-built patch: %s" % bad)
    checks.append("oracle: %d checks, %d failed"
                  % (len(results), len(bad)))
    return {"pass": not errors, "errors": errors, "checks": checks}


def test_create_patch_gui_3_edges(doc):
    """Select 3 Edge objects -> Silk_CreatePatch -> ONE unified
    Patch (pointed fill): the U=0 control column collapses to the
    corner shared by edges 0+2."""
    errors, checks = [], []
    from SilkPatch import CreatePatch

    edges = _make_triangle_edges(doc)
    Gui.Selection.clearSelection()
    for e in edges:
        Gui.Selection.addSelection(e)
    CreatePatch().Activated()
    doc.recompute()

    patches = _patches(doc)
    check(len(patches) == 1,
          "expected exactly 1 unified Patch, got %d" % len(patches),
          errors)
    if not patches:
        return {"pass": False, "errors": errors, "checks": checks}
    p = patches[0]
    check(len(p.Poles) == 16,
          "expected 16 poles, got %d" % len(p.Poles), errors)
    check(len(list(p.Edges)) == 3,
          "expected 3 Edges links, got %d" % len(list(p.Edges)),
          errors)
    col0 = [p.Poles[i * 4] for i in range(4)]
    devs = [(_c - col0[0]).Length for _c in col0]
    check(max(devs) <= 1e-6,
          "U=0 column not collapsed (pointed fill): dev %r" % devs,
          errors)
    checks.append("Silk_CreatePatch(3 edges) -> %s (%d poles, "
                  "pointed, degenerate col dev %.2e)"
                  % (p.Name, len(p.Poles), max(devs)))
    return {"pass": not errors, "errors": errors, "checks": checks}


def test_create_patch_gui_rejects_wrong_counts(doc):
    """The command refuses anything but 3 or 4 selected Edge
    objects (and an empty selection) without creating anything."""
    errors, checks = [], []
    from SilkPatch import CreatePatch

    loop = _make_loop_edges(doc)

    # 0 selection -> dialog stub (harness patches tipsDialog),
    # no object created
    Gui.Selection.clearSelection()
    CreatePatch().Activated()
    doc.recompute()
    check(not _patches(doc), "0 selection: no Patch expected",
          errors)

    # 2 edges -> rejected
    Gui.Selection.clearSelection()
    for e in loop[:2]:
        Gui.Selection.addSelection(e)
    CreatePatch().Activated()
    doc.recompute()
    check(not _patches(doc), "2 edges: no Patch expected", errors)

    # 5 edges -> rejected (a distinct 5th edge: Gui.Selection
    # dedupes repeated objects)
    from SilkWorkflowOps import create_edge
    stray_sk = doc.addObject("Sketcher::SketchObject", "SketchStray")
    stray_pts = [Vector(200, 200, 0), Vector(210, 200, 0),
                 Vector(220, 200, 0), Vector(230, 200, 0)]
    for j in range(3):
        stray_sk.addGeometry(
            Part.LineSegment(stray_pts[j], stray_pts[j + 1]))
    doc.recompute()
    stray = create_edge(stray_sk, name="Stray")
    Gui.Selection.clearSelection()
    for e in loop:
        Gui.Selection.addSelection(e)
    Gui.Selection.addSelection(stray)
    CreatePatch().Activated()
    doc.recompute()
    check(not _patches(doc), "5 edges: no Patch expected", errors)

    checks.append("wrong selection counts (0/2/5) all rejected, "
                  "no Patch objects created")
    return {"pass": not errors, "errors": errors, "checks": checks}


def test_create_patch_gui_refuses_non_edge_in_selection(doc):
    """#58: 3 Edges + 1 Sketch must NOT silently degrade to the pointed
    fill with the sketch dropped. The command refuses, names the
    offending object, and creates nothing."""
    errors, checks = [], []
    from SilkPatch import CreatePatch

    tri = _make_triangle_edges(doc)
    sketch = tri[0].Sketches[0]        # a plain Sketcher::SketchObject
    check(getattr(sketch, "object_type", None) != "Edge",
          "fixture sketch is not a non-Edge object", errors)

    Gui.Selection.clearSelection()
    for e in tri:
        Gui.Selection.addSelection(e)
    Gui.Selection.addSelection(sketch)

    with _CaptureConsole() as cap:
        CreatePatch().Activated()
    doc.recompute()

    check(not _patches(doc),
          "3 edges + 1 sketch: no Patch expected", errors)
    msgs = "".join(cap.errors)
    check(bool(msgs), "3 edges + 1 sketch: expected a refusal message",
          errors)
    check(msgs.startswith("Silk:"),
          "refusal message must start with 'Silk:', got %r" % msgs,
          errors)
    check("non-Edge" in msgs,
          "refusal message must say the selection held non-Edge "
          "objects, got %r" % msgs, errors)
    check(sketch.Label in msgs,
          "refusal message must name the offending object %r, got %r"
          % (sketch.Label, msgs), errors)
    checks.append("3 edges + 1 sketch -> refused, no Patch (%r)"
                  % msgs.strip())
    return {"pass": not errors, "errors": errors, "checks": checks}


def test_create_patch_gui_refuses_patch_and_arbitrary_objects(doc):
    """#58: a non-Edge that IS a Silk object (Patch, Blend) or an
    arbitrary one (Part::Box, no object_type at all) gets the same
    clear refusal -- never a silent drop."""
    errors, checks = [], []
    from SilkPatch import CreatePatch
    from SilkWorkflowOps import create_patch

    loop = _make_loop_edges(doc)
    existing = create_patch(loop, name="PatchAlready")
    box = doc.addObject("Part::Box", "RefuseBox")
    doc.recompute()

    for offender in (existing, box):
        before = len(_patches(doc))
        Gui.Selection.clearSelection()
        for e in loop:
            Gui.Selection.addSelection(e)
        Gui.Selection.addSelection(offender)
        with _CaptureConsole() as cap:
            CreatePatch().Activated()
        doc.recompute()

        check(len(_patches(doc)) == before,
              "%s in selection: no new Patch expected" % offender.Label,
              errors)
        msgs = "".join(cap.errors)
        check(msgs.startswith("Silk:") and "non-Edge" in msgs
              and offender.Label in msgs,
              "%s in selection: expected a 'Silk:' refusal naming it, "
              "got %r" % (offender.Label, msgs), errors)
        checks.append("4 edges + %s -> refused, no Patch"
                      % offender.Label)
    return {"pass": not errors, "errors": errors, "checks": checks}


def test_patch_get_subgrid_api(doc):
    """getSubgrid(u0, u1, v0, v1) returns the segmented patch's
    (poles, weights) as 4x4 grids (ported from the retired
    comprehensive suite onto the unified Patch)."""
    errors, checks = [], []
    from SilkWorkflowOps import create_patch

    edges = _make_loop_edges(doc)
    p = create_patch(edges, name="PatchU")
    p.USplit1 = 0.3
    doc.recompute()

    sub_poles, sub_weights = p.Proxy.getSubgrid(0, 0.5, 0, 1)
    check(sub_poles is not None, "getSubgrid returned None poles",
          errors)
    if sub_poles:
        rows = len(sub_poles)
        cols = len(sub_poles[0]) if rows > 0 else 0
        check(rows == 4 and cols == 4,
              "getSubgrid: expected 4x4, got %dx%d" % (rows, cols),
              errors)
        checks.append("getSubgrid returns %dx%d poles" % (rows, cols))
    return {"pass": not errors, "errors": errors, "checks": checks}


ALL_TESTS = [
    test_create_patch_gui_4_edges,
    test_create_patch_gui_3_edges,
    test_create_patch_gui_rejects_wrong_counts,
    test_create_patch_gui_refuses_non_edge_in_selection,
    test_create_patch_gui_refuses_patch_and_arbitrary_objects,
    test_patch_get_subgrid_api,
]
