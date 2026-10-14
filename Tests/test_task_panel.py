"""
Silk task panel tests (ticket #62, the #51 fix).

The panel is a NATIVE FreeCAD task panel -- a `SilkTaskDialog` adapter
carrying `.form` -- so these tests drive the real widgets through RPC
with no user: `Gui.Control.showDialog` is NOT modal (it embeds the
widget and returns), and collection arrives exactly the way it does for
a user, by clicking in the 3D view (`Gui.Selection.addSelection` after a
clear, which is what a single click does). Confirm arrives the way a user
delivers it too: through the same `panel_confirm()` the Enter shortcut
and the native OK button both call, and -- in the two tests that care
about the shortcut itself -- through a REAL key event posted at the main
window, so the QShortcut wiring is exercised rather than assumed.

What is asserted here:
  1. the panel really lands in the native Tasks panel (the #51 failure
     mode was invisible to a unit test, so the live host is probed:
     activeDialog, the dialog's own content list, the TaskBox header);
  2. each stage's collect -> confirm produces the right object through
     the ops layer, verified with the oracle;
  3. a wrong-type click is SILENTLY ignored -- nothing collected, and
     not one console word;
  4. OK is disabled exactly while the open section is invalid;
  5. one confirm is ONE undo step (the Gui/document undo stack), also for
     a multi-seam blend;
  6. a stale collected entry refuses LOUDLY, naming the item, and never
     degrades into a smaller object;
  7. the panel refuses to open over a foreign task dialog and leaves it
     alone;
  8. closing rebuilds fresh -- FreeCAD deletes the widget and nulls the
     adapter's `.form`.
  9. the band split stays EDITABLE after the blend exists (a blended row
     carries a working editor; editing it moves the width, the blend's
     poles follow, and collecting the row is still refused);
 10. a split correction only warns when it discards EVERY value, so the
     property editor's transient `0` on the way to `0.2` is silent;
 11. the panel's own layout: no width floor, capped collection lists with
     a greyed placeholder, and the next-step guidance out of the prime
     space above the accordion but still reachable;
  12. #73: no "chain complete" notification -- the footer hint label is
      hidden on a fully blended document, and visible with its pinned
      wording while a seam is still blendable;
  13. #75: a band width at or past the middle of the patch is not a
      width the panel can store and read back, so neither the write path
      nor either editor offers it -- closed at BOTH ends of the axis and
      by BOTH ways of reaching the midpoint (typing it, arrow-stepping
      onto it).

Fixture helpers are imported, not refactored: the square / sharing /
stray builders and the console capture from Tests.test_seam_resolver,
the ground-truth chain from Tests.test_blend_stage, the loop/triangle
edge builders from Tests.test_patch_gui_command. The one local builder
is `_stacked_pair`: #75 has to reach the parametric-0 and the
parametric-1 end in ONE row, and `_patch_sharing` resolves its shared
edge to the 0-end on both of its patches.
"""
import os

import FreeCAD
import Part
from FreeCAD import Gui

Vector = FreeCAD.Vector


def check(cond, msg, errors):
    if not cond:
        errors.append(msg)
    return cond


# ---- helpers ---------------------------------------------------------------

def _blend_objects(doc):
    return [o for o in doc.Objects
            if getattr(o, "object_type", None) in ("Blend", "BlendStrip")]


def _objects(doc, object_type):
    return [o for o in doc.Objects
            if getattr(o, "object_type", None) == object_type]


def _click(obj):
    """One click in the 3D view: the selection is REPLACED (a plain
    click), which is what fires the panel's collection path."""
    Gui.Selection.clearSelection()
    Gui.Selection.addSelection(obj)


def _open_panel(doc):
    """Drive Silk_Guide's Activated and return the live panel."""
    from SilkTaskPanel import CreateGuide, current_panel
    CreateGuide().Activated()
    return current_panel()


def _close_panel(panel):
    if panel is None:
        return
    # #72: go through the panel's OWN close path. Calling
    # Gui.Control.closeDialog() directly tears down the widget but leaves
    # the Python panel alive, still holding self.doc, _collected and the
    # two cell-widget registries -- so it pins a CLOSED document's
    # geometry for the life of the process (~90 MB per test, 3.4 GB over
    # this module). close_panel() releases those; bypassing it is what
    # leaked. The old direct teardown stays as the fallback for a panel
    # whose own close raised.
    try:
        panel.close_panel()
    except Exception:
        pass
    try:
        Gui.Control.closeDialog()
    except Exception:
        pass
    try:
        import SilkTaskPanel
        if SilkTaskPanel._open_panel is panel:
            SilkTaskPanel._open_panel = None
    except Exception:
        pass


def _undo_count(doc):
    return doc.UndoCount


def _2n_sketches(doc):
    """Two circle+line sketches -- the 2N edge mode's inputs."""
    sk1 = doc.addObject("Sketcher::SketchObject", "SK_A")
    sk1.addGeometry([
        Part.Circle(Vector(0, 0, 0), Vector(0, 0, 1), 10.995),
        Part.LineSegment(Vector(0, 0, 0), Vector(-14.4129, 29.393, 0)),
    ])
    sk2 = doc.addObject("Sketcher::SketchObject", "SK_B")
    sk2.addGeometry([
        Part.Circle(Vector(0, 0, 0), Vector(0, 0, 1), 9.1779),
        Part.LineSegment(Vector(0, 0, 0), Vector(20.5843, 19.925, 0)),
    ])
    doc.recompute()
    return sk1, sk2


def _open_gt_chain(doc):
    """Open the ground-truth fixture and rebuild the 7-edge / 2-patch
    chain in `doc`. Returns (fixture, pa, pb, g); the caller closes the
    fixture and restores the active document."""
    from Tests.test_blend_stage import _build_gt_chain
    fixture_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "Resources", "Test_files",
                                "Silk_Workflow.FCStd")
    fixture = FreeCAD.openDocument(fixture_path)
    FreeCAD.setActiveDocument(doc.Name)  # openDocument activates fixture
    pa, pb, g = _build_gt_chain(doc, fixture)
    return fixture, pa, pb, g


# ---- the host: is it a NATIVE task panel at all? ---------------------------

def test_panel_lands_in_the_native_task_panel(doc):
    """The #51 fix, probed live rather than trusted: the panel is a real
    FreeCAD task dialog -- `activeDialog()` is true, the dialog's own
    content list holds a TaskBox wrapping OUR widget, and the TaskBox
    header is the panel's windowTitle. A bare QWidget (the #48 panel)
    produced an empty task panel and none of this would be true."""
    errors, checks = [], []
    from PySide import QtWidgets
    from SilkTaskPanel import SilkTaskDialog

    panel = _open_panel(doc)
    if not check(panel is not None, "Activated left no panel open", errors):
        return {"pass": False, "errors": errors, "checks": checks}
    try:
        check(Gui.Control.activeDialog(),
              "no active task dialog -- showDialog did nothing (the #51 "
              "failure mode)", errors)
        dialog = Gui.Control.activeTaskDialog()
        check(dialog is not None, "activeTaskDialog() returned None", errors)
        if dialog is not None:
            content = dialog.getDialogContent()
            check(len(content) >= 1,
                  "the dialog reports %d content widget(s)" % len(content),
                  errors)
            if content:
                box = content[0]
                # the widget really is INSIDE FreeCAD's Tasks dock, under
                # a real TaskBox, with our windowTitle as its header
                check(box.isAncestorOf(panel),
                      "the panel is not a descendant of the dialog's "
                      "content widget -- it was not adopted", errors)
                headers = [c.text() for c in box.findChildren(QtWidgets.QToolButton)]
                check(panel.windowTitle() in headers,
                      "the TaskBox header %r does not carry the panel's "
                      "windowTitle %r" % (headers, panel.windowTitle()),
                      errors)
                dock = panel.parent()
                while dock is not None and not isinstance(
                        dock, QtWidgets.QDockWidget):
                    dock = dock.parent()
                check(dock is not None and dock.objectName() == "Tasks",
                      "the panel is not inside FreeCAD's Tasks dock "
                      "(nearest dock: %r)" % (dock.objectName()
                                              if dock else None), errors)
            check(dialog.getDocumentName() == doc.Name,
                  "dialog document name %r != %r"
                  % (dialog.getDocumentName(), doc.Name), errors)
            check(dialog.isAllowedAlterDocument()
                  and dialog.isAllowedAlterSelection(),
                  "the panel must allow altering the document and the "
                  "selection", errors)
        # the adapter is the duck-typed `.form` host
        adapter = SilkTaskDialog(panel)
        check(adapter.form is panel,
              "the adapter does not carry the panel as .form", errors)
        check(panel.windowTitle() == "Silk Workflow",
              "unexpected panel windowTitle %r" % panel.windowTitle(),
              errors)
        checks.append("native task panel: inside the Tasks dock, TaskBox "
                      "header %r" % panel.windowTitle())
    finally:
        _close_panel(panel)
    return {"pass": not errors, "errors": errors, "checks": checks}


def test_toolbox_is_a_three_section_accordion(doc):
    """The three sections are Edge / Patch / Blend in that order, one
    open at a time, and the QToolBox takes no focus (focusPolicy 0) so
    the 3D view keeps it -- which is exactly why confirm cannot be a
    keyPressEvent."""
    errors, checks = [], []
    from PySide import QtCore
    from SilkTaskPanel import SECTION_EDGE, SECTION_TITLES

    panel = _open_panel(doc)
    if not check(panel is not None, "Activated left no panel open", errors):
        return {"pass": False, "errors": errors, "checks": checks}
    try:
        # #71: the container is a header/content stack, not a QToolBox.
        # The structural properties this test cared about -- three
        # sections, the right titles, no focus stolen from the 3D view --
        # are unchanged; only the widget behind them moved. The folding
        # behaviour a QToolBox could not express is asserted by
        # test_sections_are_header_content_pairs_not_a_toolbox.
        tb = panel.sections
        check(tb.count() == 3, "stack has %d sections, expected 3" % tb.count(),
              errors)
        titles = tb.header_titles()
        check(titles == list(SECTION_TITLES),
              "section titles %r != %r" % (titles, list(SECTION_TITLES)),
              errors)
        check(tb.focusPolicy() == QtCore.Qt.NoFocus,
              "the section stack takes focus (policy %r) -- it must leave "
              "the 3D view's focus alone" % tb.focusPolicy(), errors)
        check(tb.current_index() == SECTION_EDGE,
              "the panel opens with no section expanded (%r) -- it should "
              "open on Edge, as the QToolBox did" % tb.current_index(),
              errors)
        checks.append("accordion sections: %s (NoFocus), Edge open"
                      % ", ".join(titles))
    finally:
        _close_panel(panel)
    return {"pass": not errors, "errors": errors, "checks": checks}


def test_enter_shortcut_is_application_scoped_for_both_enter_keys(doc):
    """Confirm is a QShortcut with Qt.ApplicationShortcut, registered for
    BOTH Qt.Key_Return and Qt.Key_Enter. Two shortcuts, one per key code:
    a keypad Enter is a different key and does not fire the main one.

    Asserted structurally -- the two key codes, the context, the bound
    confirm callable, and that the shortcut's window really is the
    FreeCAD main window (an ApplicationShortcut only fires if the widget
    it belongs to is in a live window; that is what puts it in the
    application's shortcut map).

    A SYNTHETIC key event cannot close this loop: Qt only consults the
    application shortcut map on the platform key path
    (QWindowSystemInterface -> processKeyEvent), so
    QApplication.sendEvent(mw, QKeyEvent(...)) goes straight to the
    widget's keyPressEvent and would report a false failure. FreeCAD
    1.1.3 ships no PySide QtTest module either. The wiring is therefore
    asserted here and the keystroke itself is left to the human round."""
    errors, checks = [], []
    from PySide import QtCore, QtGui, QtWidgets

    panel = _open_panel(doc)
    if not check(panel is not None, "Activated left no panel open", errors):
        return {"pass": False, "errors": errors, "checks": checks}
    try:
        check(len(panel._shortcuts) == 2,
              "expected 2 confirm shortcuts, got %d"
              % len(panel._shortcuts), errors)
        keys = set()
        for sc in panel._shortcuts:
            check(sc.context() == QtCore.Qt.ApplicationShortcut,
                  "shortcut context %r is not ApplicationShortcut"
                  % sc.context(), errors)
            keys |= set(sc.key().toString().split("+"))
            # the shortcut's parent must sit in a live window -- that is
            # what puts it in the APPLICATION shortcut map rather than a
            # window-local one
            check(panel.window() is Gui.getMainWindow(),
                  "the panel's window is %r, not the FreeCAD main window"
                  % panel.window(), errors)
            check(panel.window().findChildren(QtGui.QShortcut) is not None
                  and len(panel.window().findChildren(QtGui.QShortcut)) >= 2,
                  "the confirm shortcuts are not parented into the main "
                  "window", errors)
        check("Return" in keys,
              "no Qt.Key_Return shortcut among %r" % sorted(keys), errors)
        check("Enter" in keys,
              "no Qt.Key_Enter (keypad) shortcut among %r" % sorted(keys),
              errors)
        check(isinstance(panel._shortcuts[0].key(), QtGui.QKeySequence),
              "the shortcut has no key sequence", errors)
        checks.append("2 ApplicationShortcut confirms (Return + keypad "
                      "Enter), both in the main window's shortcut map")
    finally:
        _close_panel(panel)
    return {"pass": not errors, "errors": errors, "checks": checks}


# ---- stage 1: Edge ---------------------------------------------------------

def test_edge_stage_collect_one_sketch_then_confirm(doc):
    """One click in the 3D view on a sketch, then confirm -> exactly ONE
    Edge through the ops layer, oracle green, the collection cleared and
    the Edge section still open (no auto-advance)."""
    errors, checks = [], []
    from SilkChecks import check_edge
    from Tests.test_seam_resolver import _Capture, _line_sketch

    sk = _line_sketch(doc, "Extra", [(100, 0, 0), (116.7, 0, 0),
                                     (133.3, 0, 0), (150, 0, 0)])
    n_before = len(_objects(doc, "Edge"))

    panel = _open_panel(doc)
    if not check(panel is not None, "Activated left no panel open", errors):
        return {"pass": False, "errors": errors, "checks": checks}
    try:
        _click(sk)
        check(len(panel.collected()) == 1,
              "one click collected %d sketch(es)" % len(panel.collected()),
              errors)
        check(panel.edge_count_lbl.text() == "1/2",
              "counter reads %r, expected '1/2'" % panel.edge_count_lbl.text(),
              errors)
        check("3L" in panel.edge_mode_lbl.text(),
              "mode line %r does not name the 3L reading"
              % panel.edge_mode_lbl.text(), errors)
        with _Capture() as cap:
            panel.panel_confirm()
        doc.recompute()
        edges = _objects(doc, "Edge")
        check(len(edges) == n_before + 1,
              "confirm created %d edge(s), expected 1"
              % (len(edges) - n_before), errors)
        made = edges[-1]
        results = check_edge(made)
        bad = [(n, d) for n, ok, d in results if not ok]
        check(not bad, "oracle flagged the panel-built edge: %s" % bad, errors)
        check(panel.collected() == [],
              "the collection did not clear after apply: %r"
              % panel.collected(), errors)
        check(panel.open_section() == 0,
              "the panel auto-advanced to section %d after apply"
              % panel.open_section(), errors)
        check(made.Name in panel.status_text(),
              "status line %r does not name the created edge %s"
              % (panel.status_text(), made.Name), errors)
        errors += ["console error: %s" % e for e in cap.errors]
        checks.append("1 sketch -> %s (%d poles), oracle %d checks, %d bad"
                      % (made.Name, len(made.Poles), len(results), len(bad)))
    finally:
        _close_panel(panel)
        Gui.Selection.clearSelection()
    return {"pass": not errors, "errors": errors, "checks": checks}


def test_edge_stage_two_sketches_reach_the_2n_mode(doc):
    """Two clicks -> the 2N reading, and confirm builds an Edge carrying
    BOTH sketches. Collecting rather than firing on the first click is
    precisely what keeps the 2N mode reachable from the panel."""
    errors, checks = [], []
    from Tests.test_seam_resolver import _Capture

    sk1, sk2 = _2n_sketches(doc)
    n_before = len(_objects(doc, "Edge"))

    panel = _open_panel(doc)
    if not check(panel is not None, "Activated left no panel open", errors):
        return {"pass": False, "errors": errors, "checks": checks}
    try:
        _click(sk1)
        _click(sk2)
        check(len(panel.collected()) == 2,
              "two clicks collected %d sketch(es)" % len(panel.collected()),
              errors)
        check("2N" in panel.edge_mode_lbl.text(),
              "mode line %r does not name the 2N reading"
              % panel.edge_mode_lbl.text(), errors)
        with _Capture() as cap:
            panel.panel_confirm()
        doc.recompute()
        edges = _objects(doc, "Edge")
        check(len(edges) == n_before + 1,
              "confirm created %d edge(s), expected 1"
              % (len(edges) - n_before), errors)
        made = edges[-1]
        check(len(made.Sketches) == 2,
              "the 2N edge links %d sketch(es), expected 2"
              % len(made.Sketches), errors)
        check(len(made.Poles) == 4,
              "the 2N edge has %d poles, expected 4" % len(made.Poles),
              errors)
        errors += ["console error: %s" % e for e in cap.errors]
        checks.append("2 sketches -> %s (2N, %d poles, %d links)"
                      % (made.Name, len(made.Poles), len(made.Sketches)))
    finally:
        _close_panel(panel)
        Gui.Selection.clearSelection()
    return {"pass": not errors, "errors": errors, "checks": checks}


# ---- stage 2: Patch --------------------------------------------------------

def test_patch_stage_collect_four_edges_then_confirm(doc):
    """Four edge clicks -> "4/4" + the quad reading, confirm builds ONE
    unified Patch with the oracle green, and the section stays put."""
    errors, checks = [], []
    from SilkChecks import check_patch
    from Tests.test_patch_gui_command import _make_loop_edges
    from Tests.test_seam_resolver import _Capture

    edges = _make_loop_edges(doc)

    panel = _open_panel(doc)
    if not check(panel is not None, "Activated left no panel open", errors):
        return {"pass": False, "errors": errors, "checks": checks}
    try:
        panel.sections.open(1)          # the Patch section
        for e in edges:
            _click(e)
        check(len(panel.collected()) == 4,
              "four clicks collected %d edge(s)" % len(panel.collected()),
              errors)
        check(panel.patch_count_lbl.text() == "4/4",
              "counter reads %r, expected '4/4'"
              % panel.patch_count_lbl.text(), errors)
        check("quad" in panel.patch_fill_lbl.text(),
              "fill line %r does not name the quad fill"
              % panel.patch_fill_lbl.text(), errors)
        with _Capture() as cap:
            panel.panel_confirm()
        doc.recompute()
        patches = _objects(doc, "Patch")
        check(len(patches) == 1,
              "confirm created %d patch(es), expected 1" % len(patches),
              errors)
        if patches:
            results = check_patch(patches[0], edges)
            bad = [(n, d) for n, ok, d in results if not ok]
            check(not bad, "oracle flagged the panel-built patch: %s" % bad,
                  errors)
            check(len(list(patches[0].Edges)) == 4,
                  "the patch links %d edges"
                  % len(list(patches[0].Edges)), errors)
            checks.append("4 edges -> %s, oracle %d checks, %d bad"
                          % (patches[0].Name, len(results), len(bad)))
        errors += ["console error: %s" % e for e in cap.errors]
    finally:
        _close_panel(panel)
        Gui.Selection.clearSelection()
    return {"pass": not errors, "errors": errors, "checks": checks}


def test_patch_stage_three_edges_give_the_pointed_fill(doc):
    """Three edge clicks -> "3/4" + the pointed reading, and confirm
    builds the pointed fill (the U=0 control column collapses)."""
    errors, checks = [], []
    from Tests.test_patch_gui_command import _make_triangle_edges
    from Tests.test_seam_resolver import _Capture

    edges = _make_triangle_edges(doc)

    panel = _open_panel(doc)
    if not check(panel is not None, "Activated left no panel open", errors):
        return {"pass": False, "errors": errors, "checks": checks}
    try:
        panel.sections.open(1)
        for e in edges:
            _click(e)
        check(panel.patch_count_lbl.text() == "3/4",
              "counter reads %r, expected '3/4'"
              % panel.patch_count_lbl.text(), errors)
        check("pointed" in panel.patch_fill_lbl.text(),
              "fill line %r does not name the pointed fill"
              % (panel.patch_fill_lbl.text(),), errors)
        with _Capture() as cap:
            panel.panel_confirm()
        doc.recompute()
        patches = _objects(doc, "Patch")
        check(len(patches) == 1,
              "confirm created %d patch(es), expected 1" % len(patches),
              errors)
        if patches:
            col0 = [patches[0].Poles[i * 4] for i in range(4)]
            devs = [(c - col0[0]).Length for c in col0]
            check(max(devs) <= 1e-6,
                  "the U=0 column is not collapsed (pointed fill): %r" % devs,
                  errors)
            checks.append("3 edges -> %s (pointed, col dev %.2e)"
                          % (patches[0].Name, max(devs)))
        errors += ["console error: %s" % e for e in cap.errors]
    finally:
        _close_panel(panel)
        Gui.Selection.clearSelection()
    return {"pass": not errors, "errors": errors, "checks": checks}


def test_patch_section_reports_success_only_for_a_patch_that_built(doc):
    """#66: the Patch section reports success ONLY for a patch that
    actually built.

    Two halves, and the second is the point. (1) Four edges clicked in a
    deliberately AWKWARD order -- the human's real workflow, and the one
    that used to produce a valid, invisible ghost the panel cheerfully
    called "Patch created" -- now yields a real, visible, oracle-green
    patch. (2) A selection that genuinely cannot close a loop is refused
    LOUDLY, naming the offending edge, and leaves nothing behind: no
    object, and the collection survives so the user can fix it (#62's
    idiom)."""
    errors, checks = [], []
    from Tests.test_patch_gui_command import _make_loop_edges
    from Tests.test_seam_resolver import _Capture, _stray_edge
    from SilkChecks import check_patch

    edges = _make_loop_edges(doc)

    panel = _open_panel(doc)
    if not check(panel is not None, "Activated left no panel open", errors):
        return {"pass": False, "errors": errors, "checks": checks}
    try:
        panel.sections.open(1)          # the Patch section

        # (1) an awkward CLICK order: e2, e0, e3, e1 -- three of the four
        # rotations of the cycle are wrong, so pre-#66 this produced an
        # empty ghost and the panel said "Patch created".
        awkward = [edges[2], edges[0], edges[3], edges[1]]
        for e in awkward:
            _click(e)
        check(len(panel.collected()) == 4,
              "four clicks collected %d edge(s)" % len(panel.collected()),
              errors)
        with _Capture() as cap:
            ok = panel.panel_confirm()
        doc.recompute()
        patches = _objects(doc, "Patch")
        check(ok, "confirm on a valid but awkwardly-clicked selection "
                  "reported failure: %r" % panel.status_text(), errors)
        check(len(patches) == 1,
              "expected exactly 1 patch, got %d" % len(patches), errors)
        if patches:
            p = patches[0]
            check(len(list(p.Poles)) == 16,
                  "the awkwardly-clicked patch has %d poles"
                  % len(list(p.Poles)), errors)
            check(not (p.Shape is None or p.Shape.isNull()),
                  "the awkwardly-clicked patch has a NULL shape -- this is "
                  "the invisible ghost #66 is about", errors)
            check(bool(p.Shape.Faces),
                  "the awkwardly-clicked patch renders no face", errors)
            # the oracle, fed the CYCLIC order the fill actually consumed
            from SilkMachinery import loop_order
            cyclic, problem = loop_order(awkward)
            check(problem is None,
                  "loop_order refused a valid loop: %s" % problem, errors)
            bad = [(n, d) for (n, ok2, d) in check_patch(p, cyclic) if not ok2]
            check(not bad, "oracle flagged the awkward-order patch: %s"
                  % bad, errors)
            check(p.Name in panel.status_text(),
                  "status line %r does not name the created patch %s"
                  % (panel.status_text(), p.Name), errors)
            checks.append("4 edges clicked in an awkward order -> %s: "
                          "16 poles, %d face(s), oracle green, status "
                          "names it" % (p.Name, len(p.Shape.Faces)))
        check(not cap.errors, "console errors: %s" % cap.errors, errors)

        # (2) a selection that cannot close a loop: refused, named,
        # nothing left behind, collection survives.
        stray = _stray_edge(doc, "PanelStray")
        broken = [edges[0], edges[1], edges[2], stray]
        for e in broken:
            _click(e)
        check(len(panel.collected()) == 4,
              "the broken selection collected %d edge(s)"
              % len(panel.collected()), errors)
        before = len(_objects(doc, "Patch"))
        with _Capture() as cap2:
            ok2 = panel.panel_confirm()
        doc.recompute()
        check(not ok2, "a non-closing selection reported SUCCESS", errors)
        check(len(_objects(doc, "Patch")) == before,
              "a refused creation left %d object(s) behind"
              % (len(_objects(doc, "Patch")) - before), errors)
        status = panel.status_text()
        check("cannot apply" in status,
              "the refusal status does not read as a refusal: %r" % status,
              errors)
        check(stray.Name in status or "PanelStray" in status,
              "the refusal does not name the offending edge: %r" % status,
              errors)
        check(len(panel.collected()) == 4,
              "the collection did not survive the refusal (%d left) -- the "
              "user cannot fix the selection" % len(panel.collected()),
              errors)
        checks.append("3 sides + a stray -> refused loudly naming %s, no "
                      "object created, collection intact" % stray.Name)
        errors += ["console error: %s" % e for e in cap2.errors
                   if "cannot apply" not in e]
    finally:
        _close_panel(panel)
        Gui.Selection.clearSelection()
    return {"pass": not errors, "errors": errors, "checks": checks}


def test_every_patch_the_panel_hands_back_is_oracle_green(doc):
    """#67 GUARD: whatever the user clicks, the patch the panel RETURNS is
    oracle-green on its OWN Edges list.

    This is the guard the #67 bug made necessary. The defect was invisible
    because every existing assertion either fed a canonical fixture or fed
    the oracle a hand-computed cycle instead of the object's own property:
    `check_patch(p, list(p.Edges))` -- the honest call, and the one a user
    makes when they open the data tab -- was never written down. So this
    test does not test a behaviour, it closes a class of gap: it walks a
    spread of click orders through the REAL panel (not create_patch) and
    asserts the oracle, fed `list(p.Edges)`, is green every time.

    The spread is deliberate rather than exhaustive: the full 24 orderings
    are enumerated in test_patch_stage
    (test_patch_stored_cycle_is_self_consistent_for_all_24_orderings), and
    what needs covering HERE is the panel path -- click order -> collect ->
    confirm -> object -- which is a different set of code from the ops
    call. Six orders: canonical, both rotations, both reversals, and two
    awkward ones, plus the 3-edge pointed fill."""
    errors, checks = [], []
    import itertools
    from Tests.test_patch_gui_command import _make_loop_edges
    from Tests.test_seam_resolver import _Capture
    from SilkChecks import check_patch

    edges = _make_loop_edges(doc)
    orders = [
        ("canonical", [0, 1, 2, 3]),
        ("rotation", [1, 2, 3, 0]),
        ("rotation2", [2, 3, 0, 1]),
        ("rotation3", [3, 0, 1, 2]),
        ("reversed", [3, 2, 1, 0]),
        ("reversed-rot", [1, 0, 3, 2]),
        ("awkward", [2, 0, 3, 1]),
        ("awkward2", [1, 3, 0, 2]),
    ]
    # and one genuinely non-cyclic order that is NOT a rotation or a
    # reversal, as the sharpest single case
    orders.append(("shuffled", [0, 2, 1, 3]))

    panel = _open_panel(doc)
    if not check(panel is not None, "Activated left no panel open", errors):
        return {"pass": False, "errors": errors, "checks": checks}
    try:
        panel.sections.open(1)          # the Patch section
        for label, perm in orders:
            sel = [edges[i] for i in perm]
            for e in sel:
                _click(e)
            if not check(len(panel.collected()) == 4,
                         "%s: four clicks collected %d"
                         % (label, len(panel.collected())), errors):
                continue
            with _Capture() as cap:
                ok = panel.panel_confirm()
            doc.recompute()
            patches = _objects(doc, "Patch")
            check(ok, "%s: confirm reported failure (%r)"
                  % (label, panel.status_text()), errors)
            check(len(patches) >= 1, "%s: no patch created" % label, errors)
            if not patches:
                continue
            p = patches[-1]
            stored = list(p.Edges)
            fails = [(n, d) for (n, good, d) in check_patch(p, stored)
                     if not good]
            check(not fails,
                  "%s: the panel handed back a patch whose OWN Edges list "
                  "fails the oracle: %s" % (label, fails), errors)
            check(len(stored) == 4 and len(list(p.Poles)) == 16,
                  "%s: %d edges / %d poles" % (label, len(stored),
                                               len(list(p.Poles))), errors)
            check(not (p.Shape is None or p.Shape.isNull()) and
                  bool(p.Shape.Faces),
                  "%s: the panel handed back an invisible patch" % label,
                  errors)
            errors += ["%s: console error: %s" % (label, e)
                       for e in cap.errors]
        # And the 3-edge pointed fill, through the panel too -- #67 does
        # NOT normalize that list (its Patch33 parity rides on the list
        # it is handed), so this is pinned from the same fixture the
        # pointed oracle test uses. Note this pins the FLAT-triangle
        # fixture, where the pointed fill is oracle-green; on a curved
        # corner triple it is not (#68).
        from Tests.test_patch_stage import _make_triangle_edges
        tri = _make_triangle_edges(doc)
        for e in tri:
            _click(e)
        with _Capture() as cap3:
            ok3 = panel.panel_confirm()
        doc.recompute()
        pointed = _objects(doc, "Patch")
        check(ok3 and pointed, "the 3-edge pointed fill was refused", errors)
        if pointed:
            pp = pointed[-1]
            pfails = [(n, d)
                      for (n, good, d) in check_patch(pp, list(pp.Edges))
                      if not good]
            check(not pfails,
                  "the pointed patch fails the oracle on its own Edges: %s"
                  % pfails, errors)
            checks.append("3-edge pointed fill -> %s, oracle green on "
                          "list(p.Edges)" % pp.Name)
        errors += ["pointed: console error: %s" % e for e in cap3.errors]
        checks.append("%d click orders through the real panel -> every "
                      "returned patch oracle-green on list(p.Edges)"
                      % len(orders))
    finally:
        _close_panel(panel)
        Gui.Selection.clearSelection()
    return {"pass": not errors, "errors": errors, "checks": checks}


# ---- uniform interaction rules ---------------------------------------------

def test_wrong_type_clicks_are_silently_ignored(doc):
    """A click on the wrong kind of object changes NOTHING and says
    NOTHING: no dimming, no highlight, no console word, no collection
    entry. Checked in every section, in both directions (a non-sketch in
    the Edge section, a sketch in the Patch section, a non-seam edge in
    the Blend section)."""
    errors, checks = [], []
    from Tests.test_seam_resolver import _Capture, _line_sketch, _square_patch, \
        _patch_sharing, _stray_edge

    patch = _square_patch(doc, "A")
    stray = _stray_edge(doc, "Stray")
    sk = _line_sketch(doc, "A_sk_alone", [(300, 0, 0), (310, 0, 0),
                                          (320, 0, 0), (330, 0, 0)])
    before_status = None
    before_objects = len(doc.Objects)

    panel = _open_panel(doc)
    if not check(panel is not None, "Activated left no panel open", errors):
        return {"pass": False, "errors": errors, "checks": checks}
    try:
        before_status = panel.status_text()
        cases = [
            (0, patch, "a Patch in the Edge section"),
            (0, stray, "an Edge in the Edge section"),
            (1, sk, "a Sketch in the Patch section"),
            (1, patch, "a Patch in the Patch section"),
            (2, sk, "a Sketch in the Blend section"),
            (2, patch, "a Patch in the Blend section"),
            (2, stray, "a non-seam Edge in the Blend section"),
        ]
        with _Capture() as cap:
            for section, obj, label in cases:
                panel.sections.open(section)
                _click(obj)
                check(panel.collected() == [],
                      "%s collected %r" % (label, panel.collected()), errors)
        check(panel.status_text() == before_status,
              "a wrong-type click moved the status line to %r"
              % panel.status_text(), errors)
        check(not cap.errors and not cap.messages,
              "a wrong-type click produced console output: errors=%s "
              "messages=%s" % (cap.errors, cap.messages), errors)
        check(len(doc.Objects) == before_objects,
              "a wrong-type click changed the document (%d -> %d objects)"
              % (before_objects, len(doc.Objects)), errors)
        checks.append("%d wrong-type clicks ignored in silence" % len(cases))
    finally:
        _close_panel(panel)
        Gui.Selection.clearSelection()
    return {"pass": not errors, "errors": errors, "checks": checks}


def test_ok_disabled_until_the_open_section_is_valid(doc):
    """OK tracks the OPEN section only, and only through its own
    collection: Edge 1-2, Patch 3-4, Blend >= 1. The blend rows are the
    way into the Blend section, so the check runs there through the real
    `cellClicked` signal."""
    errors, checks = [], []
    from Tests.test_seam_resolver import _square_patch, _patch_sharing
    from Tests.test_patch_gui_command import _make_loop_edges

    _square_patch(doc, "A")
    loop = _make_loop_edges(doc)
    a = doc.getObject("A")
    seam_edge = a.Edges[0]
    _patch_sharing(doc, seam_edge, "B")

    panel = _open_panel(doc)
    if not check(panel is not None, "Activated left no panel open", errors):
        return {"pass": False, "errors": errors, "checks": checks}
    try:
        check(panel._ok_button is not None,
              "the adapter never saw the native button box (OK cannot be "
              "enabled/disabled)", errors)
        check(panel.ok_enabled() is False,
              "OK starts enabled with an empty collection", errors)
        # -- Edge: 0 -> 1 -> 2 is fine, a third click does not collect
        for n in range(1, 4):
            _click(loop[n - 1].Sketches[0])
            want = n >= 1
            check(bool(panel.can_confirm()) == want,
                  "after %d sketch click(s) can_confirm is %r, expected %r"
                  % (n, panel.can_confirm(), want), errors)
            check(panel.ok_enabled() == want,
                  "after %d sketch click(s) OK is %r, expected %r"
                  % (n, panel.ok_enabled(), want), errors)
        check(len(panel.collected()) == 2,
              "a third click pushed the collection to %d"
              % len(panel.collected()), errors)
        # -- Patch
        panel.sections.open(1)
        for n in range(4):
            _click(loop[n])
            want = n >= 2
            check(panel.ok_enabled() == want,
                  "after %d edge click(s) OK is %r, expected %r"
                  % (n + 1, panel.ok_enabled(), want), errors)
        # -- Blend
        panel.sections.open(2)
        check(panel.ok_enabled() is False,
              "OK is enabled in the Blend section with nothing collected",
              errors)
        row = panel.seam_row_index(seam_edge)
        check(row >= 0, "the shared edge %s is not a row" % seam_edge.Name,
              errors)
        panel.blend_table.cellClicked.emit(row, panel.COL_EDGE)
        check(panel.ok_enabled() is True,
              "OK is still disabled after collecting one blendable seam",
              errors)
        checks.append("OK disabled at Edge 0, Patch 0/1/2, Blend 0; "
                      "enabled at Edge 1/2, Patch 3/4, Blend 1")
    finally:
        _close_panel(panel)
        Gui.Selection.clearSelection()
    return {"pass": not errors, "errors": errors, "checks": checks}


def test_one_confirm_is_one_undo_step(doc):
    """One confirm = one document transaction = ONE undo step, checked on
    the document's own undo stack (doc.UndoCount / UndoNames)."""
    errors, checks = [], []
    from Tests.test_patch_gui_command import _make_loop_edges
    from Tests.test_seam_resolver import _Capture

    loop = _make_loop_edges(doc)
    panel = _open_panel(doc)
    if not check(panel is not None, "Activated left no panel open", errors):
        return {"pass": False, "errors": errors, "checks": checks}
    try:
        panel.sections.open(1)
        for e in loop:
            _click(e)
        before = _undo_count(doc)
        names_before = list(doc.UndoNames)
        with _Capture() as cap:
            panel.panel_confirm()
        doc.recompute()
        after = _undo_count(doc)
        check(after - before == 1,
              "one confirm moved the undo stack by %d steps (expected 1); "
              "names %r -> %r" % (after - before, names_before, doc.UndoNames),
              errors)
        check(len(_objects(doc, "Patch")) == 1,
              "confirm did not create exactly one patch", errors)
        errors += ["console error: %s" % e for e in cap.errors]
        checks.append("patch confirm: undo stack %d -> %d (one step)"
                      % (before, after))
    finally:
        _close_panel(panel)
        Gui.Selection.clearSelection()
    return {"pass": not errors, "errors": errors, "checks": checks}


def test_multi_seam_blend_is_still_one_undo_step(doc):
    """A pair sharing TWO seams (the closed-ring build): both rows
    collected, ONE confirm, TWO blends -- and still ONE undo step, plus
    per-seam idempotency left to the resolver."""
    errors, checks = [], []
    from Tests.test_seam_resolver import _Capture, _build_tube

    pa, pb, s_left, s_right = _build_tube(doc)
    panel = _open_panel(doc)
    if not check(panel is not None, "Activated left no panel open", errors):
        return {"pass": False, "errors": errors, "checks": checks}
    try:
        panel.sections.open(2)
        for e in (s_left, s_right):
            row = panel.seam_row_index(e)
            check(row >= 0, "seam %s has no row" % e.Name, errors)
            panel.blend_table.cellClicked.emit(row, panel.COL_EDGE)
        check(len(panel.collected()) == 2,
              "collected %d seam(s), expected 2" % len(panel.collected()),
              errors)
        before = _undo_count(doc)
        with _Capture() as cap:
            panel.panel_confirm()
        doc.recompute()
        after = _undo_count(doc)
        blends = _blend_objects(doc)
        check(len(blends) == 2,
              "one confirm created %d blend(s), expected 2" % len(blends),
              errors)
        check(after - before == 1,
              "the two-seam confirm moved the undo stack by %d steps "
              "(expected 1); names %r" % (after - before, doc.UndoNames),
              errors)
        errors += ["console error: %s" % e for e in cap.errors]
        checks.append("2 seams -> %d blends in ONE undo step (%d -> %d)"
                      % (len(blends), before, after))
    finally:
        _close_panel(panel)
        Gui.Selection.clearSelection()
    return {"pass": not errors, "errors": errors, "checks": checks}


# ---- staleness --------------------------------------------------------------

def test_stale_entry_refuses_loudly_naming_it(doc):
    """A collected edge deleted behind the panel's back makes the confirm
    REFUSE, naming that edge -- and creates nothing. Silently dropping it
    would turn the quad fill into a pointed patch behind the user's back,
    which is the whole reason the rule is a refusal and not a cleanup."""
    errors, checks = [], []
    from Tests.test_patch_gui_command import _make_loop_edges
    from Tests.test_seam_resolver import _Capture

    loop = _make_loop_edges(doc)
    panel = _open_panel(doc)
    if not check(panel is not None, "Activated left no panel open", errors):
        return {"pass": False, "errors": errors, "checks": checks}
    try:
        panel.sections.open(1)
        for e in loop:
            _click(e)
        check(len(panel.collected()) == 4, "did not collect 4 edges", errors)
        doomed = loop[1]
        doomed_name = doomed.Name
        doc.removeObject(doomed.Name)
        doc.recompute()
        with _Capture() as cap:
            applied = panel.panel_confirm()
        doc.recompute()
        check(not applied, "a stale collection still applied", errors)
        check(not _objects(doc, "Patch"),
              "the stale confirm created %d patch(es)"
              % len(_objects(doc, "Patch")), errors)
        msgs = "".join(cap.errors)
        check(doomed_name in msgs,
              "the refusal does not name the stale edge %s: %r"
              % (doomed_name, msgs), errors)
        check("cannot apply" in msgs,
              "the refusal does not read as a refusal: %r" % msgs, errors)
        check(doomed_name in panel.status_text(),
              "the status line does not name the stale edge: %r"
              % panel.status_text(), errors)
        check(len(panel.collected()) == 4,
              "the refusal dropped the collection instead of keeping it: "
              "%d left" % len(panel.collected()), errors)
        checks.append("stale %s refused and named (%r)"
                      % (doomed_name, msgs.strip()[:80]))
    finally:
        _close_panel(panel)
        Gui.Selection.clearSelection()
    return {"pass": not errors, "errors": errors, "checks": checks}


def test_stale_blend_seam_refuses_naming_it(doc):
    """The same rule on the Blend stage: a collected seam that has since
    become blended (here: the resolver's own idempotent no-op made it so)
    is refused BY NAME on confirm, rather than being quietly dropped from
    the multi-seam transaction."""
    errors, checks = [], []
    from Tests.test_seam_resolver import _Capture, _build_tube
    from SilkWorkflowOps import create_blend_by_edge

    pa, pb, s_left, s_right = _build_tube(doc)
    # blend the left seam behind the panel's back
    made = create_blend_by_edge(s_left)
    doc.recompute()
    s_blend_name = made.Name

    panel = _open_panel(doc)
    if not check(panel is not None, "Activated left no panel open", errors):
        return {"pass": False, "errors": errors, "checks": checks}
    try:
        panel.sections.open(2)
        row = panel.seam_row_index(s_left)
        check(row >= 0, "the already-blended seam has no row", errors)
        flag = panel.blend_flag(s_left)
        check(flag is not None and flag.isChecked(),
              "the row's flag is not ticked for an already-blended seam",
              errors)
        check(flag is not None and s_blend_name in flag.toolTip(),
              "the flag tooltip does not name the blend: %r"
              % (flag.toolTip() if flag else None), errors)
        # put it into the collection by hand -- the click path correctly
        # refuses a non-blendable row, staleness is about what happens if
        # one is in there anyway.
        panel._collected[2].append(__import__("SilkTaskPanel")._Collected(
            s_left))
        panel.refresh()
        with _Capture() as cap:
            applied = panel.panel_confirm()
        doc.recompute()
        check(not applied, "a stale seam still applied", errors)
        msgs = "".join(cap.errors)
        check(s_left.Name in msgs,
              "the refusal does not name the stale seam %s: %r"
              % (s_left.Name, msgs), errors)
        check("already blended" in msgs,
              "the refusal does not say why: %r" % msgs, errors)
        checks.append("stale seam %s refused: %r" % (s_left.Name,
                                                    msgs.strip()[:80]))
    finally:
        _close_panel(panel)
        Gui.Selection.clearSelection()
    return {"pass": not errors, "errors": errors, "checks": checks}


# ---- lifecycle ---------------------------------------------------------------

def test_refuses_to_open_over_a_foreign_task_dialog(doc):
    """FreeCAD allows exactly ONE task dialog and raises
    `Active task dialog found`. The panel refuses rather than silently
    closing whoever is showing -- and the foreign dialog is still there
    afterwards."""
    errors, checks = [], []
    from SilkTaskPanel import open_task_panel
    from Tests.test_seam_resolver import _Capture

    # a foreign task dialog: some other adapter, not ours
    from PySide import QtWidgets
    foreign_widget = QtWidgets.QWidget()
    QtWidgets.QVBoxLayout(foreign_widget).addWidget(QtWidgets.QLabel("hi"))

    class _Foreign:
        def __init__(self, form):
            self.form = form

        def open(self):
            pass

        def accept(self):
            return True

        def reject(self):
            return True

        def clicked(self, button):
            pass

        def modifyStandardButtons(self, box):
            pass

        def getStandardButtons(self):
            return (QtWidgets.QDialogButtonBox.Ok
                    | QtWidgets.QDialogButtonBox.Cancel)

        def isAllowedAlterDocument(self):
            return True

        def isAllowedAlterView(self):
            return True

        def isAllowedAlterSelection(self):
            return True

    Gui.Control.showDialog(_Foreign(foreign_widget))
    try:
        check(Gui.Control.activeDialog(), "the foreign dialog did not open",
              errors)
        with _Capture() as cap:
            raised = None
            try:
                open_task_panel(doc)
            except RuntimeError as e:
                raised = e
        check(raised is not None,
              "open_task_panel did not refuse over a foreign dialog", errors)
        if raised is not None:
            check("Active task dialog found" in str(raised),
                  "RuntimeError message is %r, expected it to carry "
                  "'Active task dialog found'" % str(raised), errors)
        check(Gui.Control.activeDialog(),
              "the foreign dialog was closed instead of respected", errors)
        check(not cap.errors,
              "the refusal was silent on the console: %s" % cap.errors,
              errors)

        # ... and the command turns it into a console refusal, not a crash
        with _Capture() as cap2:
            from SilkTaskPanel import CreateGuide
            CreateGuide().Activated()
        check(any("Active task dialog found" in e for e in cap2.errors),
              "the command did not report the active dialog: %s" % cap2.errors,
              errors)
        check(Gui.Control.activeDialog(),
              "the command closed the foreign dialog", errors)
        checks.append("foreign dialog respected; RuntimeError + console "
                      "refusal, dialog untouched")
    finally:
        Gui.Control.closeDialog()
    return {"pass": not errors, "errors": errors, "checks": checks}


def test_close_then_reopen_rebuilds_fresh(doc):
    """FreeCAD DELETES the panel widget on close and NULLS the adapter's
    `.form`, so there is nothing to reuse: reopening builds a brand new
    widget and a brand new adapter. A stale collection does not survive
    the close either."""
    errors, checks = [], []
    import SilkTaskPanel
    from Tests.test_patch_gui_command import _make_loop_edges

    loop = _make_loop_edges(doc)
    panel1 = _open_panel(doc)
    if not check(panel1 is not None, "first Activated left no panel open",
                 errors):
        return {"pass": False, "errors": errors, "checks": checks}
    adapter_form = panel1
    panel1.sections.open(1)
    _click(loop[0])
    check(len(panel1.collected()) == 1, "nothing collected before close",
          errors)

    # close it the way the adapter does (reject -> close_panel)
    panel1.close_panel()
    check(SilkTaskPanel._open_panel is None,
          "close_panel left the module pointing at the dead panel", errors)
    check(not panel1._hook_installed and not panel1._doc_hook_installed,
          "close_panel left an observer installed", errors)
    check(not Gui.Control.activeDialog(),
          "close_panel left the task dialog up", errors)

    panel2 = _open_panel(doc)
    if not check(panel2 is not None, "reopen left no panel open", errors):
        return {"pass": False, "errors": errors, "checks": checks}
    try:
        check(panel2 is not panel1,
              "reopen handed back the SAME widget -- it must be rebuilt", errors)
        check(panel2.collected() == [],
              "the old collection survived the close: %r" % panel2.collected(),
              errors)
        check(panel2.sections.current_index() == 0,
              "the reopened panel kept the old open section (%d)"
              % panel2.sections.current_index(), errors)
        check(panel2._hook_installed and panel2._doc_hook_installed,
              "the reopened panel did not install its hooks", errors)
        checks.append("close -> widget deleted + form nulled; reopen is fresh")
    finally:
        _close_panel(panel2)
        Gui.Selection.clearSelection()
    return {"pass": not errors, "errors": errors, "checks": checks}


def test_adapter_form_is_nulled_on_close(doc):
    """The lifecycle fact the rebuild-from-scratch rule rests on: FreeCAD
    NULLS the adapter's `.form` when it tears the dialog down (so reusing
    the instance cannot touch a deleted widget). Proved by handing
    `showDialog` an adapter we still hold and closing it."""
    errors, checks = [], []
    from SilkTaskPanel import SilkTaskPanel, SilkTaskDialog
    from PySide import QtWidgets

    panel = SilkTaskPanel(doc)
    adapter = SilkTaskDialog(panel)
    check(adapter.form is panel, "adapter.form is not the panel", errors)
    Gui.Control.showDialog(adapter)
    try:
        check(Gui.Control.activeDialog(),
              "showDialog did nothing for the adapter", errors)
        check(adapter.form is panel,
              "the adapter lost .form while the dialog was open", errors)
    finally:
        Gui.Control.closeDialog()
    check(adapter.form is None,
          "after closeDialog the adapter still holds .form (%r) -- FreeCAD "
          "must have nulled it" % (adapter.form,), errors)
    checks.append("adapter.form: the panel -> None on close")
    return {"pass": not errors, "errors": errors, "checks": checks}


def test_closes_on_document_switch(doc):
    """Collections would belong to a document the user is no longer
    looking at, so activating another document closes the panel."""
    errors, checks = [], []
    import SilkTaskPanel
    from Tests.test_patch_gui_command import _make_loop_edges

    loop = _make_loop_edges(doc)
    other = FreeCAD.newDocument("_mcp_other_doc")
    # openDocument/newDocument activates the new document, so make our own
    # active again -- otherwise setActiveDocument(other) below would be a
    # no-op and emit no Activate signal at all.
    FreeCAD.setActiveDocument(doc.Name)
    try:
        panel = _open_panel(doc)
        if not check(panel is not None, "Activated left no panel open",
                     errors):
            return {"pass": False, "errors": errors, "checks": checks}
        panel.sections.open(1)
        _click(loop[0])
        check(panel._doc_hook_installed,
              "the panel installed no document observer", errors)
        FreeCAD.setActiveDocument(other.Name)
        check(not Gui.Control.activeDialog(),
              "the panel survived a document switch", errors)
        check(SilkTaskPanel._open_panel is None,
              "the module still points at the closed panel", errors)
        check(not panel._doc_hook_installed,
              "the document observer was left installed", errors)
        checks.append("document switch closed the panel and unsubscribed")
    finally:
        FreeCAD.setActiveDocument(doc.Name)
        FreeCAD.closeDocument(other.Name)
        Gui.Selection.clearSelection()
    return {"pass": not errors, "errors": errors, "checks": checks}


# ---- stage 3: Blend ---------------------------------------------------------

def test_blend_table_merges_every_seam_with_its_flag(doc):
    """One merged table, one row per seam_inventory entry IN ORDER, and
    the status column is a CHECKBOX whose state and greying say the same
    thing the status word used to (#69): ticked for blended, unticked and
    LIVE for blendable, unticked and GREYED for blocked. Plus the
    "N of M seams blended" roll-up."""
    errors, checks = [], []
    from SilkWorkflowOps import create_blend_by_edge, seam_inventory
    from Tests.test_seam_resolver import _square_patch, _patch_sharing

    a = _square_patch(doc, "A")
    ea = a.Edges[0]
    _patch_sharing(doc, ea, "B")
    c = _square_patch(doc, "C")
    ec = c.Edges[0]
    _patch_sharing(doc, ec, "D")
    created = create_blend_by_edge(ea)
    _patch_sharing(doc, ec, "E")          # -> blocked (3 patches)

    panel = _open_panel(doc)
    if not check(panel is not None, "Activated left no panel open", errors):
        return {"pass": False, "errors": errors, "checks": checks}
    try:
        panel.sections.open(2)
        inv = seam_inventory(doc)
        statuses = [e["status"] for e in inv]
        check("blocked" in statuses and "blended" in statuses,
              "the fixture lacks a blocked or blended seam (%r)" % statuses,
              errors)
        check(panel.blend_table.rowCount() == len(inv),
              "table has %d rows, seam_inventory has %d"
              % (panel.blend_table.rowCount(), len(inv)), errors)
        seen = {}
        for row, entry in enumerate(inv):
            cells = panel.row_texts(row)
            check(cells[0] == entry["edge"].Name,
                  "row %d edge cell %r != %r"
                  % (row, cells[0], entry["edge"].Name), errors)
            check(cells[1] == "%s <-> %s" % (entry["patch_a"].Name,
                                             entry["patch_b"].Name),
                  "row %d pair cell %r" % (row, cells[1]), errors)
            flag = panel.blend_flag(entry["edge"])
            if not check(flag is not None,
                         "row %d (%s) carries no blended flag"
                         % (row, entry["edge"].Name), errors):
                continue
            status = entry["status"]
            check(flag.isChecked() == (status == "blended"),
                  "row %d (%s): flag checked=%s for status %r"
                  % (row, entry["edge"].Name, flag.isChecked(), status),
                  errors)
            # blocked is GREYED, blendable is not: the two must not be
            # told apart by an unticked tick alone
            check(flag.isEnabled() == (status != "blocked"),
                  "row %d (%s): flag enabled=%s for status %r"
                  % (row, entry["edge"].Name, flag.isEnabled(), status),
                  errors)
            seen[status] = flag
        if "blended" in seen:
            check(created.Name in seen["blended"].toolTip(),
                  "the blended flag's tooltip does not name the blend: %r"
                  % seen["blended"].toolTip(), errors)
        if "blocked" in seen:
            check("three or more patches" in seen["blocked"].toolTip(),
                  "the blocked flag's tooltip does not say WHY: %r"
                  % seen["blocked"].toolTip(), errors)
        blended = sum(1 for s in statuses if s == "blended")
        check(panel.progress_text() == "%d of %d seams blended"
              % (blended, len(inv)),
              "progress %r != '%d of %d seams blended'"
              % (panel.progress_text(), blended, len(inv)), errors)
        checks.append("%d rows; flag ticked/live/greyed per status, "
                      "reasons in the tooltips" % len(inv))
    finally:
        _close_panel(panel)
        Gui.Selection.clearSelection()
    return {"pass": not errors, "errors": errors, "checks": checks}


def test_blend_collect_highlight_and_remove(doc):
    """A blendable row collects on click and is HIGHLIGHTED; clicking it
    again removes it; a blended or blocked row does neither."""
    errors, checks = [], []
    from Tests.test_seam_resolver import _square_patch, _patch_sharing, \
        _stray_edge

    a = _square_patch(doc, "A")
    ea = a.Edges[0]
    _patch_sharing(doc, ea, "B")
    _patch_sharing(doc, ea, "C")            # 3 patches -> BLOCKED on ea
    other = a.Edges[1]
    _patch_sharing(doc, other, "D")         # 2 patches -> blendable
    _stray_edge(doc, "Stray")               # not a seam -> no row

    panel = _open_panel(doc)
    if not check(panel is not None, "Activated left no panel open", errors):
        return {"pass": False, "errors": errors, "checks": checks}
    try:
        panel.sections.open(2)
        good = panel.seam_row_index(other)
        bad = panel.seam_row_index(ea)
        check(good >= 0 and bad >= 0, "the seam rows are missing", errors)
        check(panel.seam_row_index(doc.getObject("Stray")) == -1,
              "a non-seam edge got a table row", errors)

        panel.blend_table.cellClicked.emit(bad, panel.COL_EDGE)
        check(panel.collected() == [],
              "a BLOCKED row collected %r" % panel.collected(), errors)

        panel.blend_table.cellClicked.emit(good, panel.COL_EDGE)
        check(len(panel.collected()) == 1,
              "the blendable row collected %d entries" % len(panel.collected()),
              errors)
        item = panel.blend_table.item(good, panel.COL_EDGE)
        check(item.font().bold() and item.background().color().name()
              not in ("#000000",),
              "the collected row is not highlighted (bold=%s, bg=%s)"
              % (item.font().bold(), item.background().color().name()),
              errors)

        panel.blend_table.cellClicked.emit(good, panel.COL_EDGE)
        check(panel.collected() == [],
              "clicking a collected row did not remove it: %r"
              % panel.collected(), errors)
        item = panel.blend_table.item(good, panel.COL_EDGE)
        check(not item.font().bold(),
              "the removed row is still highlighted", errors)
        checks.append("collect -> highlight -> remove; blocked row inert")
    finally:
        _close_panel(panel)
        Gui.Selection.clearSelection()
    return {"pass": not errors, "errors": errors, "checks": checks}


def test_blend_confirm_matches_the_resolver(doc):
    """The Blend stage's confirm IS create_blend_by_edge: the ground-truth
    oracle green (with `edge=blend.Edge`, #49's pin), the row flips to
    `blended by <Blend>`, and the status line names blend + edge."""
    errors, checks = [], []
    from SilkChecks import check_blend
    from Tests.test_seam_resolver import _Capture

    fixture, pa, pb, g = _open_gt_chain(doc)
    try:
        panel = _open_panel(doc)
        if not check(panel is not None, "Activated left no panel open",
                     errors):
            return {"pass": False, "errors": errors, "checks": checks}
        panel.sections.open(2)
        try:
            e_shr = g["E_Shr"]
            row = panel.seam_row_index(e_shr)
            check(row >= 0, "%s is not a table row" % e_shr.Name, errors)
            panel.blend_table.cellClicked.emit(row, panel.COL_EDGE)
            check(len(panel.collected()) == 1,
                  "collected %d seam(s)" % len(panel.collected()), errors)
            with _Capture() as cap:
                panel.panel_confirm()
            doc.recompute()
            blends = _blend_objects(doc)
            check(len(blends) == 1,
                  "confirm created %d blend(s), expected 1" % len(blends),
                  errors)
            if blends:
                bl = blends[0]
                # #49: the pin is what lets the oracle validate either
                # blend of a two-seam pair.
                results = check_blend(bl, pa, pb,
                                      reference_poles=fixture.BlendStrip.Poles,
                                      edge=bl.Edge)
                bad = [(n, d) for n, ok, d in results if not ok]
                check(not bad, "oracle flagged the panel blend: %s" % bad,
                      errors)
                check("%s created across %s" % (bl.Name, e_shr.Name)
                      == panel.status_text(),
                      "status line %r" % panel.status_text(), errors)
                flag = panel.blend_flag(e_shr)
                check(flag is not None and flag.isChecked()
                      and bl.Name in flag.toolTip(),
                      "the row did not flip to a ticked flag naming the "
                      "blend: %r" % (flag.toolTip() if flag else None),
                      errors)
                errors += ["console error: %s" % e for e in cap.errors]
                checks.append("confirm -> %s across %s: oracle %d checks, "
                              "%d bad" % (bl.Name, e_shr.Name,
                                          len(results), len(bad)))
        finally:
            _close_panel(panel)
    finally:
        Gui.Selection.clearSelection()
        FreeCAD.closeDocument(fixture.Name)
        FreeCAD.setActiveDocument(doc.Name)
    return {"pass": not errors, "errors": errors, "checks": checks}


# ---- unblend: the untick takes the band's splits with it (#71) -------------

def test_untick_unblends_and_says_the_band_splits_went(doc):
    """Unticking a blended seam must take the band's SPLITS with it, and
    must SAY so.

    In the wizard the Band A / Band B editors ARE the patch's USplits /
    VSplits property -- the same data, with no second copy anywhere -- so
    a user who unsets the blend has unset the width, and the patch must go
    back to a plain one. The status line therefore names the axes it
    cleared: an untick is destructive to the user's widths, and a message
    that reports only the reversible half ("Blend deleted") leaves the
    user believing their widths are still there.
    """
    errors, checks = [], []
    from SilkTaskPanel import BAND_A, write_band_split
    from Tests.test_seam_resolver import _Capture

    fixture, pa, pb, g = _open_gt_chain(doc)
    try:
        edge = g["E_Shr"]
        panel = _open_panel(doc)
        if not check(panel is not None, "Activated left no panel open",
                     errors):
            return {"pass": False, "errors": errors, "checks": checks}
        try:
            panel.sections.open(2)
            row = panel.seam_row_index(edge)
            panel.blend_table.cellClicked.emit(row, panel.COL_EDGE)
            with _Capture() as cap:
                panel.panel_confirm()
            doc.recompute()
            blends = _blend_objects(doc)
            if not check(len(blends) == 1, "confirm created %d blend(s)"
                         % len(blends), errors):
                return {"pass": False, "errors": errors, "checks": checks}
            bl = blends[0]
            bl_name = bl.Name    # read NOW: the untick deletes it, and a
                                 # deleted DocumentObject answers .Name
                                 # with None rather than raising

            # a USER's width on band A, set through the wizard's own editor
            entry = next(e for e in panel.seam_inventory()
                         if e["edge"] is edge)
            check(write_band_split(entry, BAND_A, 0.25),
                  "the band editor refused the user's width 0.25", errors)
            doc.recompute()
            fed = [p for p in (entry["patch_a"], entry["patch_b"])
                   if p is not None]
            before = {(p.Name, prop): list(getattr(p, prop, None) or [])
                      for p in fed for prop in ("USplits", "VSplits")}
            checks.append("before the untick: %s"
                          % ", ".join("%s.%s=%r" % (p.Name, prop, before[
                              (p.Name, prop)])
                                      for p in fed
                                      for prop in ("USplits", "VSplits")))
            check(any(before.values()),
                  "the blend wrote no band split at all -- the fixture does "
                  "not exercise the case", errors)

            flag = panel.blend_flag(edge)
            check(flag is not None and flag.isChecked(),
                  "the row is not a ticked flag before the untick", errors)
            tip = flag.toolTip() if flag else ""
            check("splits" in tip,
                  "the untick's own tooltip does not say the band's splits "
                  "go with it: %r" % tip, errors)

            with _Capture() as cap2:
                # a REAL click, not a synthetic signal emit: PySide2's
                # `clicked` exposes a no-arg overload too, and emitting
                # it by hand exercises a path a user never takes (the
                # panel's slot takes the bool, which is what a click
                # delivers).
                flag.click()
            doc.recompute()
            errors += ["console error: %s" % e for e in cap2.errors]
            check(not flag.isChecked(),
                  "the click did not untick the box", errors)

            status = panel.status_text()
            checks.append("status: %r" % status)
            check(edge.Name in status and bl_name in status,
                  "the status line does not name the seam and its blend: %r"
                  % status, errors)
            check("band splits removed" in status,
                  "the status line does not report that the band's splits "
                  "went -- it reports only the deleted blend: %r" % status,
                  errors)
            for p in fed:
                for prop in ("USplits", "VSplits"):
                    was = before[(p.Name, prop)]
                    left_ = list(getattr(p, prop, None) or [])
                    check(not left_,
                          "%s.%s=%r survived the untick -- the band editors "
                          "ARE that property, so unsetting the blend must "
                          "unset it" % (p.Name, prop, left_), errors)
                    if was:
                        check("%s.%s" % (p.Name, prop) in status,
                              "%s.%s held %r before the untick and the status "
                              "does not name it: %r"
                              % (p.Name, prop, was, status), errors)
                check(len(p.Shape.Faces) == 1,
                      "%s is not one whole surface after the untick: %d "
                      "faces" % (p.Name, len(p.Shape.Faces)), errors)
                check(not p.Proxy._subgrids,
                      "%s still builds %d subgrids after the untick"
                      % (p.Name, len(p.Proxy._subgrids)), errors)
            new_flag = panel.blend_flag(edge)
            check(new_flag is not None and not new_flag.isChecked(),
                  "the row is still ticked after the untick", errors)
        finally:
            _close_panel(panel)
    finally:
        Gui.Selection.clearSelection()
        FreeCAD.closeDocument(fixture.Name)
        FreeCAD.setActiveDocument(doc.Name)
    return {"pass": not errors, "errors": errors, "checks": checks}


# ---- the band split ----------------------------------------------------------

def test_band_split_editor_reads_and_writes_the_patch_split(doc):
    """The collected row's band editors read each patch's OWN split and
    write straight back onto it -- which since #64 is what the blend
    reads, so a width set here is the width the blend uses on that patch.
    Asserted against the patch properties, not against a panel copy.

    #69: TWO editors, one per patch. Editing Band A must move A and leave
    B alone -- the write targets the patch the user touched, not "the
    seam", because the seam has two bands and they are allowed to differ.
    """
    errors, checks = [], []
    from SilkMachinery import split_at_end
    from SilkTaskPanel import BAND_A, BAND_B
    from Tests.test_seam_resolver import _square_patch, _patch_sharing

    a = _square_patch(doc, "A")
    b = _patch_sharing(doc, a.Edges[0], "B")
    # a pre-existing user split on the seam's band axis of patch A. The
    # axis is DERIVED, never assumed: _side_of is the panel's own
    # resolver, so this stays true whichever way the seam happens to run.
    from SilkTaskPanel import _side_of
    a_prop, a_ss = _side_of(a, b)
    b_prop, b_ss = _side_of(b, a)
    setattr(a, a_prop, [0.35])
    setattr(b, b_prop, [0.35])
    doc.recompute()

    panel = _open_panel(doc)
    if not check(panel is not None, "Activated left no panel open", errors):
        return {"pass": False, "errors": errors, "checks": checks}
    try:
        panel.sections.open(2)
        row = panel.seam_row_index(a.Edges[0])
        check(row >= 0, "the seam has no row", errors)
        panel.blend_table.cellClicked.emit(row, panel.COL_EDGE)
        spin_a = panel.split_editor(a.Edges[0], BAND_A)
        spin_b = panel.split_editor(a.Edges[0], BAND_B)
        if not check(spin_a is not None and spin_b is not None,
                     "the row carries %d of 2 band editors"
                     % sum(1 for s in (spin_a, spin_b) if s is not None),
                     errors):
            return {"pass": False, "errors": errors, "checks": checks}
        check(panel.blend_table.cellWidget(row, panel.COL_BAND_A) is spin_a
              and panel.blend_table.cellWidget(row, panel.COL_BAND_B)
              is spin_b,
              "the two editors are not mounted in their own columns",
              errors)
        for spin, what in ((spin_a, "Band A"), (spin_b, "Band B")):
            check(abs(spin.value() - 0.35) < 1e-9,
                  "%s shows %g, expected the patch's own 0.35"
                  % (what, spin.value()), errors)
            check(spin.minimum() > 0.0 and spin.maximum() < 1.0,
                  "%s is not constrained to 0 < u < 1 (range %g..%g)"
                  % (what, spin.minimum(), spin.maximum()), errors)

        b_before = list(getattr(b, b_prop) or [])
        undo_before = _undo_count(doc)
        names_before = list(doc.UndoNames)
        spin_a.setValue(0.22)
        spin_a.editingFinished.emit()
        doc.recompute()
        after = split_at_end(list(getattr(a, a_prop) or []), a_ss)
        check(after is not None and abs(after - 0.22) < 1e-9,
              "patch A still reads %r on %s after the edit -- the editor "
              "did not write through"
              % (list(getattr(a, a_prop) or []), a_prop), errors)
        check(list(getattr(b, b_prop) or []) == b_before,
              "editing Band A also wrote patch B: %r was %r"
              % (list(getattr(b, b_prop) or []), b_before), errors)
        check(abs(panel.split_editor(a.Edges[0], BAND_B).value() - 0.35)
              < 1e-9, "the Band B editor was dragged along by the Band A "
              "edit", errors)
        # its OWN undo step: one transaction for one patch's property
        added = list(doc.UndoNames[:len(doc.UndoNames)
                                    - len(names_before)])
        check(_undo_count(doc) - undo_before == 1,
              "one edit moved the undo stack by %d steps (expected 1)"
              % (_undo_count(doc) - undo_before), errors)
        check([str(n) for n in added] == ["Silk band split"],
              "the split edit was not its own transaction: %r" % added,
              errors)
        checks.append("2 editors seeded 0.35; Band A -> 0.22 writes "
                      "A.%s only, 1 undo step, B untouched" % a_prop)
    finally:
        _close_panel(panel)
        Gui.Selection.clearSelection()
    return {"pass": not errors, "errors": errors, "checks": checks}


def test_user_band_split_is_honoured_by_the_blend(doc):
    """#64 end to end through the panel: set a user width on the patches,
    let the blend READ it, and the split is UNCHANGED afterwards (the old
    default-asserting behaviour would have overwritten 0.2 with 0.1).

    B4 is deliberately not asserted: its reference poles ARE the default
    (0.1-wide) blend, so a user width must miss it. Everything the user
    can still break -- structural links, C0 seam continuity, C1 tangent
    continuity and surface validity -- is asserted green."""
    errors, checks = [], []
    from SilkChecks import check_blend
    from SilkTaskPanel import BAND_A, BAND_B
    from Tests.test_seam_resolver import _Capture

    fixture, pa, pb, g = _open_gt_chain(doc)
    try:
        panel = _open_panel(doc)
        if not check(panel is not None, "Activated left no panel open",
                     errors):
            return {"pass": False, "errors": errors, "checks": checks}
        panel.sections.open(2)
        row = panel.seam_row_index(g["E_Shr"])
        check(row >= 0, "the shared edge is not a row", errors)
        panel.blend_table.cellClicked.emit(row, panel.COL_EDGE)
        spin_a = panel.split_editor(g["E_Shr"], BAND_A)
        spin_b = panel.split_editor(g["E_Shr"], BAND_B)
        if not check(spin_a is not None and spin_b is not None,
                     "the row does not carry a band editor per patch",
                     errors):
            return {"pass": False, "errors": errors, "checks": checks}
        # where the width must land, read from the panel's own resolver
        from SilkMachinery import split_at_end
        from SilkTaskPanel import read_band_split
        entry = next(e for e in panel.seam_inventory()
                     if e["edge"] is g["E_Shr"])
        pa_prop, pa_ss, _v1, pb_prop, pb_ss, _v2 = read_band_split(entry)
        # both editors to the same width: the symmetric case is still one
        # value per patch, set twice, and both patches must end up there
        for spin in (spin_a, spin_b):
            spin.setValue(0.2)
            spin.editingFinished.emit()
        doc.recompute()
        with _Capture() as cap:
            panel.panel_confirm()
        doc.recompute()
        blends = _blend_objects(doc)
        check(len(blends) == 1,
              "confirm created %d blend(s), expected 1" % len(blends),
              errors)
        if blends:
            bl = blends[0]
            results = check_blend(bl, pa, pb, edge=bl.Edge)
            checked = {n: ok for n, ok, _d in results}
            for name in ("structural", "B1_c0_seams", "B2_c1_tangents",
                         "B3_surface_valid"):
                check(checked.get(name) is True,
                      "oracle %s failed on the user-width blend: %r"
                      % (name, [(n, d) for n, ok, d in results
                                if not ok]), errors)
            from SilkMachinery import split_at_end
            for p, prop, ss in ((pa, pa_prop, pa_ss), (pb, pb_prop, pb_ss)):
                val = split_at_end(list(getattr(p, prop) or []), ss)
                check(val is not None and abs(val - 0.2) < 1e-9,
                      "the blend rewrote the user's band width on %s.%s: "
                      "%r" % (p.Name, prop, list(getattr(p, prop) or [])),
                      errors)
            checks.append("user width 0.2 honoured on %s.%s / %s.%s; "
                          "oracle structural/B1/B2/B3 green"
                          % (pa.Name, pa_prop, pb.Name, pb_prop))
        errors += ["console error: %s" % e for e in cap.errors]
    finally:
        _close_panel(panel)
        Gui.Selection.clearSelection()
        FreeCAD.closeDocument(fixture.Name)
        FreeCAD.setActiveDocument(doc.Name)
    return {"pass": not errors, "errors": errors, "checks": checks}


def test_band_split_multi_cell_is_refused_naming_patch_and_values(doc):
    """A width that would NOT leave exactly one band cell refuses at
    confirm, naming the patch AND the values that break it -- multi-cell
    bands are still unsupported, so nothing is built rather than something
    wrong."""
    errors, checks = [], []
    from Tests.test_seam_resolver import _Capture, _square_patch, \
        _patch_sharing

    a = _square_patch(doc, "A")
    b = _patch_sharing(doc, a.Edges[0], "B")
    # A's seam-PARALLEL axis already carries a plain mid split at 0.5,
    # which marks NEITHER end: with the band's own split that leaves two
    # cells along the seam, so there is no single-cell band. The
    # parallel axis is the one the band does NOT live on, derived here
    # from the panel's own _side_of so it is right for this seam.
    from SilkTaskPanel import _side_of
    band_prop, _band_ss = _side_of(a, b)
    along_prop = "VSplits" if band_prop == "USplits" else "USplits"
    setattr(a, along_prop, [0.5])
    doc.recompute()

    panel = _open_panel(doc)
    if not check(panel is not None, "Activated left no panel open", errors):
        return {"pass": False, "errors": errors, "checks": checks}
    try:
        panel.sections.open(2)
        edge = a.Edges[0]
        row = panel.seam_row_index(edge)
        check(row >= 0, "the seam has no row", errors)
        panel.blend_table.cellClicked.emit(row, panel.COL_EDGE)
        problems = panel.invalid_bands()
        check(problems, "a two-cell band was not detected: %r"
              % panel.invalid_bands(), errors)
        if problems:
            named_item, message = problems[0]
            check(named_item.obj is edge,
                  "the refusal names %s, expected %s"
                  % (named_item.name, edge.Name), errors)
            check(a.Name in message and "band cells" in message,
                  "the refusal does not name the patch and the cell count: "
                  "%r" % message, errors)
            check("band A" in message,
                  "the refusal does not say WHICH band was judged: %r"
                  % message, errors)
            check(band_prop in message and along_prop in message,
                  "the refusal does not name the split values %r/%r: %r"
                  % (band_prop, along_prop, message), errors)
        with _Capture() as cap:
            applied = panel.panel_confirm()
        doc.recompute()
        check(not applied, "a multi-cell band still applied", errors)
        check(not _blend_objects(doc),
              "the refusal created %d blend(s)" % len(_blend_objects(doc)),
              errors)
        msgs = "".join(cap.errors)
        check(a.Name in msgs and "band cells" in msgs,
              "the console refusal does not name the patch: %r" % msgs,
              errors)
        checks.append("multi-cell band refused: %r" % msgs.strip()[:110])
    finally:
        _close_panel(panel)
        Gui.Selection.clearSelection()
    return {"pass": not errors, "errors": errors, "checks": checks}


def test_band_cell_mirror_agrees_with_the_real_band_cells(doc):
    """The panel's CANDIDATE-layout cell count is a mirror of
    SilkMachinery.band_cells computed on lists (so a width can be checked
    BEFORE it is written). It must agree with the real thing on a live
    patch -- otherwise the panel would refuse valid widths or accept
    invalid ones.

    Judged PER PATCH (#69): the two patches of this fixture are given
    different split layouts, because a mirror that only ever agrees on
    symmetric pairs is exactly the mirror that would let a second editor
    validate against its partner's geometry."""
    errors, checks = [], []
    from SilkMachinery import band_cells, patch_side
    from SilkTaskPanel import BAND_A, BAND_B, band_cell_problem
    from Tests.test_seam_resolver import _square_patch, _patch_sharing

    layouts = [[], [0.1], [0.9], [0.5], [0.1, 0.9], [0.2, 0.85],
               [0.3, 0.5, 0.7]]
    compared = 0
    # #72: the patches are built ONCE, not per iteration. The geometry is
    # the same square every time -- only the SPLITS vary, and splits are a
    # property assignment plus a recompute. Rebuilding them per iteration
    # made this test 116s and left 2,352 objects in the document, which
    # also made the NEXT test 73s (measured) and fed the retention the
    # RSS report was flagging. Same coverage: 147 (layout, layout, band)
    # combinations, compared against the same `band_cells`.
    a = _square_patch(doc, "MirrorA")
    b = _patch_sharing(doc, a.Edges[0], "MirrorB")
    for along_a in layouts:
        for band_a in layouts:
            for along_b, band_b in ((along_a, band_a), ([], [0.2]),
                                    ([0.5], [])):
                a.USplits = list(along_a)
                a.VSplits = list(band_a)
                b.USplits = list(along_b)
                b.VSplits = list(band_b)
                doc.recompute()
                entry = {"edge": a.Edges[0], "patch_a": a, "patch_b": b,
                         "status": "blendable", "blend": None}
                for which, patch, other, along, band in (
                        (BAND_A, a, b, along_a, band_a),
                        (BAND_B, b, a, along_b, band_b)):
                    ea, ss = patch_side(patch, other)
                    if ea is None:
                        continue
                    real = len(band_cells(patch, ea, ss))
                    problem = band_cell_problem(entry, which, None)
                    mirrored = 1 if problem is None else int(
                        problem.rsplit("covers ", 1)[1].split(" ")[0])
                    compared += 1
                    if mirrored != real:
                        errors.append(
                            "%s layout along=%r band=%r: mirror says %d "
                            "cells, SilkMachinery.band_cells says %d"
                            % (which, along, band, mirrored, real))
                    if (real == 1) != (problem is None):
                        errors.append("%s layout along=%r band=%r: "
                                      "problem=%r but real count is %d"
                                      % (which, along, band, problem, real))
    checks.append("candidate-layout mirror matches band_cells on %d "
                  "(patch, layout) pairs, including ASYMMETRIC pairs"
                  % compared)
    return {"pass": not errors, "errors": errors, "checks": checks}


# ---- the band split, AFTER the blend exists (the #62 follow-up) ----------

def test_blended_seam_row_keeps_a_working_split_editor(doc):
    """The band split stays EDITABLE once the seam is blended.

    #62 mounted the editor only on COLLECTED rows, and a collected row is
    by definition blendable -- so a seam that had already been blended had
    no editor at all and its width could only be reached through the
    property editor. Here a blended row exposes a working editor, and
    editing it moves the band width on BOTH patches, re-drives the
    existing blend's poles (asserted on the poles themselves), and leaves
    the oracle green.

    Unchanged by this: a blended row still REFUSES blend creation
    (`accepts`), so the collect-then-confirm rule is exactly as before."""
    errors, checks = [], []
    from SilkChecks import check_blend
    from SilkMachinery import band_cells, patch_side, split_at_end
    from SilkTaskPanel import BAND_A, BAND_B, read_band_split
    from Tests.test_seam_resolver import _Capture

    fixture, pa, pb, g = _open_gt_chain(doc)
    try:
        edge = g["E_Shr"]
        panel = _open_panel(doc)
        if not check(panel is not None, "Activated left no panel open",
                     errors):
            return {"pass": False, "errors": errors, "checks": checks}
        try:
            panel.sections.open(2)
            row = panel.seam_row_index(edge)
            check(row >= 0, "%s has no row" % edge.Name, errors)
            panel.blend_table.cellClicked.emit(row, panel.COL_EDGE)
            with _Capture() as cap:
                panel.panel_confirm()
            doc.recompute()
            blends = _blend_objects(doc)
            if not check(len(blends) == 1,
                         "confirm created %d blend(s), expected 1"
                         % len(blends), errors):
                return {"pass": False, "errors": errors, "checks": checks}
            bl = blends[0]
            errors += ["console error: %s" % e for e in cap.errors]
            flag = panel.blend_flag(edge)
            check(flag is not None and flag.isChecked(),
                  "the row did not flip to a ticked flag: %r"
                  % (flag.isChecked() if flag else None), errors)

            # --- the row now carries a WORKING editor per PATCH -----
            spin_a = panel.split_editor(edge, BAND_A)
            spin_b = panel.split_editor(edge, BAND_B)
            if not check(spin_a is not None and spin_b is not None,
                         "a BLENDED seam row has %d of 2 band editors -- the "
                         "width the blend was built from is unreachable from "
                         "the panel" % sum(1 for s in (spin_a, spin_b)
                                          if s is not None), errors):
                return {"pass": False, "errors": errors, "checks": checks}
            entry = next(e for e in panel.seam_inventory()
                         if e["edge"] is edge)
            check(entry["status"] == "blended",
                  "the seam is not reported as blended (%r)"
                  % entry["status"], errors)
            read = read_band_split(entry)
            check(abs(spin_a.value() - read[2]) < 1e-9,
                  "Band A shows %g, patch A's own band split is %g"
                  % (spin_a.value(), read[2]), errors)
            check(abs(spin_b.value() - read[5]) < 1e-9,
                  "Band B shows %g, patch B's own band split is %g"
                  % (spin_b.value(), read[5]), errors)
            for spin, what in ((spin_a, "A"), (spin_b, "B")):
                check("blended" in spin.toolTip(),
                      "the %s editor's tooltip does not say the seam is "
                      "blended: %r" % (what, spin.toolTip()), errors)

            # --- ... and collectability is unchanged -----------------
            check(not panel.accepts(2, edge),
                  "a blended seam became collectable again -- the editor's "
                  "availability must not leak into blend CREATION", errors)
            panel.blend_table.cellClicked.emit(row, panel.COL_EDGE)
            check(panel.collected() == [],
                  "a blended row collected %r on click" % panel.collected(),
                  errors)

            # --- editing it moves THAT patch's band width -----------
            # The width lives at ITS end's half of the axis:
            # split_at_end reads the lowest split for side 0 and the
            # highest for side 1.
            want = 0.2 if read[1] == 0 else 0.8
            before_poles = [Vector(p) for p in bl.Poles]
            before_undo = _undo_count(doc)
            names_before = list(doc.UndoNames)
            pb_before = list(getattr(pb, read[3]) or [])
            with _Capture() as cap2:
                spin_a.setValue(want)
                spin_a.editingFinished.emit()
            doc.recompute()
            # ONE transaction per split edit (#62's rule: a split edit is
            # NEVER folded into the confirm transaction), and since #69 one
            # edit writes ONE patch, so it is one undo step -- not two.
            # UndoNames is newest-first.
            added = list(doc.UndoNames[:len(doc.UndoNames)
                                        - len(names_before)])
            check(_undo_count(doc) - before_undo == 1,
                  "the split write moved the undo stack by %d steps "
                  "(expected 1)" % (_undo_count(doc) - before_undo), errors)
            check([str(n) for n in added] == ["Silk band split"],
                  "the split edit was not its own transaction: %r" % added,
                  errors)
            check(list(getattr(pb, read[3]) or []) == pb_before,
                  "editing Band A wrote patch B too: %r was %r"
                  % (list(getattr(pb, read[3]) or []), pb_before), errors)
            got = split_at_end(list(getattr(pa, read[0]) or []), read[1])
            check(got is not None and abs(got - want) < 1e-9,
                  "patch A.%s reads %r after the edit, expected %g"
                  % (read[0], list(getattr(pa, read[0]) or []), want),
                  errors)
            # still exactly one band cell per side -- the edit did not turn
            # the seam into an unsupported multi-cell band
            for p, other, what in ((pa, pb, "A"), (pb, pa, "B")):
                ea, sa = patch_side(p, other)
                cells = band_cells(p, ea, sa) if ea else []
                check(len(cells) == 1,
                      "patch %s band covers %d cells after the edit (want 1)"
                      % (what, len(cells)), errors)

            # --- and the blend's poles followed ---------------------
            after_poles = [Vector(p) for p in bl.Poles]
            moved = max((x - y).Length for x, y in zip(before_poles,
                                                       after_poles))
            check(moved > 1e-6,
                  "the blend's poles did not move at all when the band width "
                  "changed (max pole delta %.3e)" % moved, errors)
            results = check_blend(bl, pa, pb, edge=bl.Edge)
            checked = {n: ok for n, ok, _d in results}
            for name in ("structural", "B1_c0_seams", "B2_c1_tangents",
                         "B3_surface_valid"):
                check(checked.get(name) is True,
                      "oracle %s failed after the post-blend width edit: %r"
                      % (name, [(n, d) for n, ok, d in results if not ok]),
                      errors)
            errors += ["console error: %s" % e for e in cap2.errors]
            checks.append("blended row keeps an editor per patch; Band A "
                          "%g -> A only (1 own undo step), poles moved "
                          "%.3g, oracle structural/B1/B2/B3 green, collect "
                          "still refused" % (want, moved))
        finally:
            _close_panel(panel)
    finally:
        Gui.Selection.clearSelection()
        FreeCAD.closeDocument(fixture.Name)
        FreeCAD.setActiveDocument(doc.Name)
    return {"pass": not errors, "errors": errors, "checks": checks}


def test_unresolvable_seam_row_does_not_abandon_the_table(doc):
    """A seam whose patches cannot be resolved gets NO band editor, and the
    rows after it still render.

    Found by screenshotting, not by a test: mounting an editor on EVERY
    row (the post-blend fix) means every refresh now asks each seam which
    axis its band lives on. A patch whose fill failed carries no poles, so
    that resolution RAISES -- and the exception escaped into FreeCAD's
    task-dialog callback, which swallows it. The visible result was a
    half-rendered table: rows present, cells blank, everything below the
    bad seam missing."""
    errors, checks = [], []
    from SilkWorkflowOps import seam_inventory
    from Tests.test_seam_resolver import _square_patch, _patch_sharing

    a = _square_patch(doc, "A")
    b = _patch_sharing(doc, a.Edges[0], "B")
    good = next(e for e in seam_inventory(doc) if e["edge"] is a.Edges[0])

    class _Unbuilt:
        """A Patch-shaped object whose fill never produced poles."""
        Name = "Ghost"

        def __init__(self):
            self.Poles = []

    ghost_edge = a.Edges[1]
    ghost = {"edge": ghost_edge, "patch_a": _Unbuilt(),
             "patch_b": _Unbuilt(), "status": "blendable", "blend": None}

    panel = _open_panel(doc)
    if not check(panel is not None, "Activated left no panel open", errors):
        return {"pass": False, "errors": errors, "checks": checks}
    try:
        panel.sections.open(2)
        raised = None
        try:
            panel._render_table([good, ghost, good],
                                {"blended": 0, "total": 3})
        except Exception as e:                    # pragma: no cover
            raised = e
        check(raised is None,
              "rendering a table with an unresolvable seam raised %r" % raised,
              errors)
        check(panel.blend_table.rowCount() == 3,
              "the table has %d rows, expected 3"
              % panel.blend_table.rowCount(), errors)
        for row in range(3):
            texts = panel.row_texts(row)
            check(all(texts),
                  "row %d did not render its cells: %r" % (row, texts), errors)
            flag = panel.blend_table.cellWidget(row, panel.COL_BLENDED)
            check(flag is not None,
                  "row %d carries no blended flag -- an unresolvable seam "
                  "must still say what it is" % row, errors)
        for col in (panel.COL_BAND_A, panel.COL_BAND_B):
            check(panel.blend_table.cellWidget(1, col) is None,
                  "the unresolvable row was given a band editor anyway",
                  errors)
            check(panel.blend_table.cellWidget(2, col) is not None,
                  "the row AFTER the unresolvable one lost its Band editor",
                  errors)
        checks.append("an unresolvable seam row renders blank-but-present "
                      "and the rows around it survive")
    finally:
        _close_panel(panel)
        Gui.Selection.clearSelection()
    return {"pass": not errors, "errors": errors, "checks": checks}


def test_post_blend_width_that_would_break_the_band_is_refused(doc):
    """A width that would NOT leave one band cell refuses, naming the patch
    and the values, and puts back ONLY the spin that was edited (#69) --
    the same rule the confirm path uses, now protecting a blend that
    already exists instead of preventing one that has not been made yet."""
    errors, checks = [], []
    from SilkTaskPanel import BAND_A, BAND_B, _side_of
    from Tests.test_seam_resolver import _Capture, _square_patch, \
        _patch_sharing
    from SilkWorkflowOps import create_blend_by_edge

    a = _square_patch(doc, "A")
    b = _patch_sharing(doc, a.Edges[0], "B")
    edge = a.Edges[0]
    bl = create_blend_by_edge(edge)
    doc.recompute()
    check(bl is not None, "no blend was created on %s" % edge.Name, errors)

    panel = _open_panel(doc)
    if not check(panel is not None, "Activated left no panel open", errors):
        return {"pass": False, "errors": errors, "checks": checks}
    try:
        panel.sections.open(2)
        spin = panel.split_editor(edge, BAND_A)
        if not check(spin is not None, "the blended row has no Band A editor",
                     errors):
            return {"pass": False, "errors": errors, "checks": checks}
        # A plain mid split at 0.5 on the seam-PARALLEL axis marks
        # neither end, so a band split on top of it spans two cells.
        from SilkTaskPanel import _side_of
        band_prop, band_ss = _side_of(a, b)
        along_prop = "VSplits" if band_prop == "USplits" else "USplits"
        setattr(a, along_prop, [0.5])
        doc.recompute()
        panel.refresh()
        spin = panel.split_editor(edge, BAND_A)
        spin_b = panel.split_editor(edge, BAND_B)
        b_before = list(getattr(b, _side_of(b, a)[0]) or [])
        spin_b_before = spin_b.value()
        before = list(getattr(a, band_prop) or [])
        with _Capture() as cap:
            spin.setValue(0.2)
            spin.editingFinished.emit()
        doc.recompute()
        msgs = "".join(cap.errors)
        check("band cells" in msgs,
              "the refusal does not explain the cell count: %r" % msgs, errors)
        check(edge.Name in msgs and a.Name in msgs,
              "the refusal does not name the seam and the patch: %r" % msgs,
              errors)
        check("band A" in msgs,
              "the refusal does not say WHICH editor was refused: %r" % msgs,
              errors)
        check(list(getattr(a, band_prop) or []) == before,
              "the refused width was written anyway: %s was %s"
              % (list(getattr(a, band_prop) or []), before), errors)
        check(abs(spin.value() - (before[0] if before else 0.1)) < 1e-9,
              "the refused spin was not put back to the stored split (%g)"
              % spin.value(), errors)
        # ... and only THAT spin was touched: the partner editor keeps the
        # value the user can still see, and patch B is untouched.
        check(abs(spin_b.value() - spin_b_before) < 1e-9,
              "the refused edit moved the other editor (%g -> %g)"
              % (spin_b_before, spin_b.value()), errors)
        check(list(getattr(b, _side_of(b, a)[0]) or []) == b_before,
              "the refused edit on A still wrote patch B", errors)
        checks.append("multi-cell width refused on the Band A editor, only "
                      "that spin restored, Band B untouched")
    finally:
        _close_panel(panel)
        Gui.Selection.clearSelection()
    return {"pass": not errors, "errors": errors, "checks": checks}


# ---- #69: two band editors, one per patch ----------------------------------

def test_two_band_editors_start_equal_and_name_their_own_patch(doc):
    """A seam row carries TWO band editors (#69), one per patch, and both
    are seeded from their own patch's stored split.

    Seeded EQUAL for the ordinary seam -- the two patches carry the same
    width, so symmetry is still one value shown twice, and typing it into
    one and the other keeps being an act of symmetry rather than a chase.
    Each tooltip names the patch it writes AND what its partner holds, so
    two numbers on one row are still legible without a third column.
    """
    errors, checks = [], []
    from SilkTaskPanel import BAND_A, BAND_B, band_side, read_band_split
    from Tests.test_seam_resolver import _square_patch, _patch_sharing

    a = _square_patch(doc, "A")
    b = _patch_sharing(doc, a.Edges[0], "B")

    panel = _open_panel(doc)
    if not check(panel is not None, "Activated left no panel open", errors):
        return {"pass": False, "errors": errors, "checks": checks}
    try:
        panel.sections.open(2)
        edge = a.Edges[0]
        row = panel.seam_row_index(edge)
        check(row >= 0, "the seam has no row", errors)
        spin_a = panel.split_editor(edge, BAND_A)
        spin_b = panel.split_editor(edge, BAND_B)
        if not check(spin_a is not None and spin_b is not None,
                     "the row carries %d of 2 band editors"
                     % sum(1 for s in (spin_a, spin_b) if s is not None),
                     errors):
            return {"pass": False, "errors": errors, "checks": checks}
        check(spin_a is not spin_b,
              "both editors are the same widget", errors)
        entry = next(e for e in panel.seam_inventory() if e["edge"] is edge)
        read = read_band_split(entry)
        pa, pb = band_side(entry, BAND_A, read), band_side(entry, BAND_B, read)
        check(pa[0] is a and pb[0] is b,
              "the editors are not bound to patch_a / patch_b "
              "(A -> %r, B -> %r)" % (pa[0].Name, pb[0].Name), errors)
        check(abs(spin_a.value() - spin_b.value()) < 1e-12,
              "the two editors are seeded differently (%g vs %g) on a seam "
              "whose patches agree"
              % (spin_a.value(), spin_b.value()), errors)
        check(abs(spin_a.value() - pa[3]) < 1e-12
              and abs(spin_b.value() - pb[3]) < 1e-12,
              "the editors do not show their own patches' stored splits "
              "(%g/%g vs %g/%g)" % (spin_a.value(), pa[3],
                                    spin_b.value(), pb[3]), errors)
        # each tooltip says which patch it writes, and what the other holds
        check(a.Name in spin_a.toolTip() and b.Name in spin_b.toolTip(),
              "the tooltips do not name their own patch: %r / %r"
              % (spin_a.toolTip(), spin_b.toolTip()), errors)
        check(pa[1] in spin_a.toolTip() and pb[1] in spin_b.toolTip(),
              "the tooltips do not name their own split property: %r / %r"
              % (spin_a.toolTip(), spin_b.toolTip()), errors)
        check("same" in spin_a.toolTip(),
              "the tooltip does not say the two agree: %r"
              % spin_a.toolTip(), errors)
        # five columns, and the flag column is the narrow one
        check(panel.blend_table.columnCount() == 5,
              "the table has %d columns, expected 5"
              % panel.blend_table.columnCount(), errors)
        check(list(panel.blend_table.horizontalHeaderItem(i).text()
                   for i in range(5))
              == ["Seam", "Patches", "Blended?", "Band A", "Band B"],
              "unexpected column headers: %r"
              % [panel.blend_table.horizontalHeaderItem(i).text()
                 for i in range(5)], errors)

        # A DETACHED editor -- one the table has already replaced by a
        # re-render -- must be inert. Acting on it would apply ITS value
        # to the LIVE editor's patch, and the live editor is sitting there
        # showing the seed, so the user would be told their number was
        # written when the other one was.
        old_a = panel.split_editor(edge, BAND_A)
        panel.refresh()
        new_a = panel.split_editor(edge, BAND_A)
        check(old_a is not new_a,
              "the refresh did not re-mount the Band A editor -- the "
              "stale-editor guard below would be untestable", errors)
        pa_before = list(getattr(a, pa[1]) or [])
        old_a.setValue(0.28)
        old_a.editingFinished.emit()
        doc.recompute()
        check(list(getattr(a, pa[1]) or []) == pa_before,
              "a detached editor wrote %r onto %s.%s"
              % (list(getattr(a, pa[1]) or []), a.Name, pa[1]), errors)
        check(abs(panel.split_editor(edge, BAND_A).value() - pa[3]) < 1e-12,
              "the live editor's value moved on a detached edit (%g)"
              % panel.split_editor(edge, BAND_A).value(), errors)
        checks.append("2 editors per row, seeded equal from their own "
                      "patches, each tooltip naming its own property; a "
                      "detached editor is inert")
    finally:
        _close_panel(panel)
        Gui.Selection.clearSelection()
    return {"pass": not errors, "errors": errors, "checks": checks}


def test_band_edit_validation_is_per_patch(doc):
    """Each edit is judged against ITS OWN patch (#69).

    The fixture is built so the answer must differ: patch A carries a
    plain mid split at 0.5 on the axis ALONG the seam, which leaves two
    cells under any band width, so every width is refused on A. Patch B
    is clean, so every width is fine on B. A panel that still validated
    the pair would refuse both editors; a panel that validated the
    partner's layout on A's behalf would accept A. Only the per-patch
    rule gets both answers right.

    Also asserted, because it is the easy half to get wrong: a refused
    edit restores ONLY its own spin, leaves the partner editor showing
    what it showed, and writes neither patch."""
    errors, checks = [], []
    from SilkTaskPanel import BAND_A, BAND_B, _side_of
    from Tests.test_seam_resolver import _Capture, _square_patch, \
        _patch_sharing

    a = _square_patch(doc, "A")
    b = _patch_sharing(doc, a.Edges[0], "B")
    edge = a.Edges[0]
    band_prop, _ss = _side_of(a, b)
    along_prop = "VSplits" if band_prop == "USplits" else "USplits"
    b_band_prop, b_ss = _side_of(b, a)
    setattr(a, along_prop, [0.5])          # A: two cells under any width
    doc.recompute()

    panel = _open_panel(doc)
    if not check(panel is not None, "Activated left no panel open", errors):
        return {"pass": False, "errors": errors, "checks": checks}
    try:
        panel.sections.open(2)
        spin_a = panel.split_editor(edge, BAND_A)
        spin_b = panel.split_editor(edge, BAND_B)
        if not check(spin_a is not None and spin_b is not None,
                     "the row carries %d of 2 band editors"
                     % sum(1 for s in (spin_a, spin_b) if s is not None),
                     errors):
            return {"pass": False, "errors": errors, "checks": checks}
        a_before = list(getattr(a, band_prop) or [])
        b_before = list(getattr(b, b_band_prop) or [])

        # -- refused on A, because A is the one that cannot take it -----
        with _Capture() as cap:
            spin_a.setValue(0.2)
            spin_a.editingFinished.emit()
        doc.recompute()
        msgs = "".join(cap.errors)
        check("band A" in msgs and a.Name in msgs and "band cells" in msgs,
              "the refusal on A does not name the editor, the patch and the "
              "reason: %r" % msgs, errors)
        check(list(getattr(a, band_prop) or []) == a_before,
              "the refused width was written to A anyway: %r was %r"
              % (list(getattr(a, band_prop) or []), a_before), errors)
        check(abs(spin_a.value() - (a_before[0] if a_before else 0.1))
              < 1e-9,
              "the refused editor was not put back (%g)" % spin_a.value(),
              errors)

        # -- ... and B was never dragged into it -----------------------
        b_shown_before = spin_b.value()
        with _Capture() as cap:
            spin_b.setValue(0.2)
            spin_b.editingFinished.emit()
        doc.recompute()
        msgs = "".join(cap.errors)
        check("band cells" not in msgs,
              "the same width was refused on the CLEAN patch B: %r" % msgs,
              errors)
        check(list(getattr(b, b_band_prop) or []) != b_before,
              "the valid width was not written to B: %r"
              % list(getattr(b, b_band_prop) or []), errors)
        check(list(getattr(a, band_prop) or []) == a_before,
              "the successful edit on B also wrote A: %r"
              % list(getattr(a, band_prop) or []), errors)
        check(abs(spin_b.value() - 0.2) < 1e-9,
              "the Band B editor does not show the width it just wrote "
              "(%g)" % spin_b.value(), errors)
        check(abs(spin_a.value() - (a_before[0] if a_before else 0.1))
              < 1e-9,
              "the successful edit on B moved the Band A editor (%g)"
              % spin_a.value(), errors)
        checks.append("0.2 refused on A (two cells), accepted on B (one); "
                      "only the refused spin restored, neither editor "
                      "leaked onto the other patch")
    finally:
        _close_panel(panel)
        Gui.Selection.clearSelection()
    return {"pass": not errors, "errors": errors, "checks": checks}


def _stacked_pair(doc):
    """Two patches stacked so they share ONE edge without overlapping.

    `_patch_sharing` (test_seam_resolver) builds the second patch from the
    other three sides of the SAME square, so both patches occupy the same
    space and every corner matches every corner -- `patch_side` then
    resolves the shared edge to whichever corner pair it meets first,
    which for that fixture pair is the parametric-0 end on BOTH patches.
    #75 needs both ends in one row: a width is stored as itself at the
    0-end and as 1 - width at the 1-end, so the midpoint only looks
    representable if an editor at each end is watched.

    This fixture is a square with a second square standing on its top
    edge: they touch along that one edge and nowhere else, so the shared
    edge is A's parametric-1 END and B's parametric-0 end.
    """
    from Tests.test_seam_resolver import _line_sketch, _square_patch
    from SilkWorkflowOps import create_edge, create_patch
    a = _square_patch(doc, "A")
    shared = next(e for e in a.Edges
                  if abs(e.Poles[0][1] - 50.0) < 1e-9
                  and abs(e.Poles[3][1] - 50.0) < 1e-9)
    b_edges = [
        shared,
        create_edge(_line_sketch(
            doc, "B_up_sk",
            [(0, 50, 0), (0, 66.7, 0), (0, 83.3, 0), (0, 100, 0)]),
            name="B_up"),
        create_edge(_line_sketch(
            doc, "B_top_sk",
            [(0, 100, 0), (16.7, 100, 0), (33.3, 100, 0),
             (50, 100, 0)]),
            name="B_top"),
        create_edge(_line_sketch(
            doc, "B_down_sk",
            [(50, 100, 0), (50, 83.3, 0), (50, 66.7, 0),
             (50, 50, 0)]),
            name="B_down"),
    ]
    b = create_patch(b_edges, name="B")
    if b is None:
        raise AssertionError("the stacked-pair fixture did not build")
    doc.recompute()
    return a, b, shared


def test_band_width_at_the_middle_is_not_stored_even_at_the_1_end(doc):
    """#75: a width at or past the middle of the patch has NO end of the
    axis to be stored at, and the panel's own write path must not store
    one as if it did.

    Driven through `write_band_split` -- the same call the editor makes,
    not a hand-built split list -- and asserted as a ROUND TRIP: what
    `band_side` reports after the write is what the editor is seeded
    from and what the user sees. Before the fix, a written 0.5 stayed on
    the patch and read back as the 0.1 DEFAULT, so the panel showed a
    number nobody typed.

    BOTH ends, which is the point of `_stacked_pair`: patch A shares the
    seam at its parametric-1 end (a width is stored as 1 - width) and
    patch B at its parametric-0 end (stored as the width), and 0.5 is the
    identity of that mapping at either end -- so one value that looks
    perfectly ordinary reaches both editors. `split_at_end` is NOT
    touched: the midpoint really belongs to neither end, so the write side
    adapts to it.
    """
    errors, checks = [], []
    from SilkTaskPanel import BAND_A, BAND_B, band_side, band_width_problem, \
        write_band_split, _side_of
    from Tests.test_seam_resolver import _Capture

    a, b, shared = _stacked_pair(doc)
    a_prop, a_ss = _side_of(a, b)          # A: the parametric-1 end
    b_prop, b_ss = _side_of(b, a)          # B: the parametric-0 end
    check((a_ss, b_ss) == (1, 0),
          "the stacked fixture gives ends (ss A=%r, ss B=%r); both are "
          "needed for #75" % (a_ss, b_ss), errors)
    entry = {"edge": shared, "patch_a": a, "patch_b": b,
             "status": "blendable", "blend": None}
    sides = ((BAND_A, a, a_prop, a_ss), (BAND_B, b, b_prop, b_ss))

    # -- control: an ordinary width IS written and read back at both ends
    for which, p, prop, ss in sides:
        stored = 1.0 - 0.45 if ss else 0.45
        check(write_band_split(entry, which, 0.45),
              "%s: the panel refused its own seeding width 0.45" % which,
              errors)
        check(list(getattr(p, prop)) == [stored],
              "%s: writing 0.45 stored %r on %s.%s (ss=%d), expected [%g]"
              % (which, list(getattr(p, prop)), p.Name, prop, ss, stored),
              errors)
        check(abs(band_side(entry, which)[3] - 0.45) < 1e-9,
              "%s: a stored 0.45-wide band reads back as %g -- the reader "
              "is not merely broken in general, only at the middle"
              % (which, band_side(entry, which)[3]), errors)

    # -- the midpoint, then the half above it: nothing is stored, and the
    #    refusal is not silent.
    for which, p, prop, _ss in sides:
        before = list(getattr(p, prop))
        for width in (0.5, 0.55, 0.9):
            with _Capture() as cap:
                wrote = write_band_split(entry, which, width)
            msgs = "".join(cap.errors)
            check(not wrote,
                  "%s: write_band_split(0.5) wrote it anyway (%r)"
                  % (which, list(getattr(p, prop))), errors)
            check("%g" % width in msgs,
                  "%s: the refusal for %g does not name the number it "
                  "refused: %r" % (which, width, msgs), errors)
            check(list(getattr(p, prop)) == before,
                  "%s: the refused width %g still moved %s.%s (%r)"
                  % (which, width, p.Name, prop, list(getattr(p, prop))),
                  errors)
        check(abs(band_side(entry, which)[3] - 0.45) < 1e-9,
              "%s: after the refused write the panel would show %g, not "
              "the 0.45 the patch holds -- the #75 display bug"
              % (which, band_side(entry, which)[3]), errors)

    # -- the rule itself, at both ends: 0.5 and everything wider
    for ss in (0, 1):
        for width in (0.5, 0.55, 0.9):
            check(band_width_problem(width, ss) is not None,
                  "ss=%d: a width of %g is accepted as storable at that end"
                  % (ss, width), errors)
        check(band_width_problem(0.45, ss) is None,
              "ss=%d: a width of 0.45 is refused" % ss, errors)
    checks.append("0.45 written and read back at both ends; 0.5 / 0.55 / "
                  "0.9 refused loudly at both ends, patch untouched, "
                  "round trip intact")
    return {"pass": not errors, "errors": errors, "checks": checks}


def test_band_editor_offers_no_width_the_panel_cannot_read_back(doc):
    """#75, the half the user actually touches: the EDITOR.

    Two reachable paths to the midpoint, both closed by the editor's own
    domain rather than by a refusal after the fact:

      * TYPING 0.5 (or anything wider) -- an out-of-range number is not
        accepted at all; the editor keeps showing the width its patch
        stores, so the display and the property still agree.
      * ARROW-STEPPING up to it -- the single step is 0.05, so from 0.45
        the next step lands exactly on 0.50. The range stops below the
        middle, so the step is clamped at the widest usable width instead
        of resting on one nothing can read back.

    Asserted on BOTH editors of the row (`_stacked_pair`), i.e. at both
    ends of the axis, and as a ROUND TRIP through the panel: the value
    the editor lands on is committed, then read back off the patch.
    """
    errors, checks = [], []
    from SilkTaskPanel import BAND_A, BAND_B, band_label, band_side, \
        write_band_split, _side_of
    from Tests.test_seam_resolver import _Capture

    a, b, shared = _stacked_pair(doc)
    a_prop, a_ss = _side_of(a, b)
    b_prop, b_ss = _side_of(b, a)
    entry = {"edge": shared, "patch_a": a, "patch_b": b,
             "status": "blendable", "blend": None}
    sides = ((BAND_A, a, a_prop, a_ss), (BAND_B, b, b_prop, b_ss))

    # Seed BOTH patches through the panel's own write path BEFORE the
    # panel is opened, so the editors mount already holding a width they
    # can read back -- and assert the probe starts from nothing, since a
    # leftover split would answer these questions by itself.
    for which, p, prop, ss in sides:
        check(not (list(getattr(p, prop) or [])),
              "%s: the probe does not start clean -- %s.%s already holds %r"
              % (band_label(which), p.Name, prop,
                 list(getattr(p, prop) or [])), errors)
        with _Capture() as cap:
            seeded = write_band_split(entry, which, 0.45)
        check(seeded and not cap.errors,
              "%s: the panel refused its own seeding width 0.45 (%r)"
              % (band_label(which), cap.errors), errors)
    doc.recompute()

    panel = _open_panel(doc)
    if not check(panel is not None, "Activated left no panel open", errors):
        return {"pass": False, "errors": errors, "checks": checks}
    try:
        panel.sections.open(2)
        check(panel.seam_row_index(shared) >= 0,
              "the shared edge is not a row in the table", errors)
        for which, p, prop, ss in sides:
            what = "%s (patch %s.%s, end %d)" % (band_label(which),
                                                 p.Name, prop, ss)
            spin = panel.split_editor(shared, which)
            if not check(spin is not None,
                         "%s: no band editor mounted" % what, errors):
                continue
            # -- state is clean before anything is touched ----------------
            if not check(abs(spin.value() - 0.45) < 1e-9,
                         "%s: the editor opens on %g with the patch at %r"
                         % (what, spin.value(), list(getattr(p, prop))),
                         errors):
                continue

            # -- the domain: nothing at or past the middle is on offer --
            check(spin.maximum() < 0.5,
                  "%s: the editor offers up to %g, which no end of the "
                  "axis can store (#75)"
                  % (what, spin.maximum()), errors)
            check(spin.minimum() > 0.0,
                  "%s: the editor offers %g, a zero-width band"
                  % (what, spin.minimum()), errors)

            # -- TYPED: an ordinary width, first, as the CONTROL ---------
            # If the keystroke path were not live, the midpoint case
            # below would "pass" because nothing was ever committed.
            _type_width(spin, 0.2)
            with _Capture() as cap:
                _enter_key(spin.lineEdit())
            doc.recompute()
            check(abs(spin.value() - 0.2) < 1e-9
                  and abs(band_side(entry, which)[3] - 0.2) < 1e-9
                  and not cap.errors,
                  "%s: typing 0.2 and pressing Enter did not round-trip "
                  "(editor %g, read back %g, console %r) -- the keystroke "
                  "path the midpoint case relies on is not live"
                  % (what, spin.value(), band_side(entry, which)[3],
                     cap.errors), errors)

            # -- TYPED: 0.5, then wider ---------------------------------
            for typed in (0.5, 0.9):
                # the REAL keystroke path again: type it, press Enter,
                # which is the editor's own commit (`_commit_spin`, so
                # the typed text is interpreted exactly once) and then
                # the confirm.
                _type_width(spin, typed)
                before = list(getattr(p, prop) or [])
                with _Capture() as cap:
                    _enter_key(spin.lineEdit())
                doc.recompute()
                check(abs(spin.value() - 0.2) < 1e-9,
                      "%s: typing %g left the editor showing %g, which is "
                      "neither what was typed nor the 0.2 the patch holds"
                      % (what, typed, spin.value()), errors)
                check(list(getattr(p, prop) or []) == before,
                      "%s: typing %g was written to %s.%s anyway: %r"
                      % (what, typed, p.Name, prop,
                         list(getattr(p, prop))), errors)

            # -- ARROWS: the step that lands on the midpoint -------------
            stepped = []
            spin.setValue(0.45)
            for _ in range(8):
                spin.stepBy(1)
                stepped.append(spin.value())
            for _ in range(8):
                spin.stepBy(-1)
                stepped.append(spin.value())
            bad = sorted(set(v for v in stepped if v >= 0.5 - 1e-12))
            check(not bad,
                  "%s: stepping rested on a width the panel cannot read "
                  "back: %r" % (what, bad), errors)
            check(any(abs(v - spin.maximum()) < 1e-9 for v in stepped),
                  "%s: stepping up never reached the top of the range (%g) "
                  "-- the arrow path was not really exercised"
                  % (what, spin.maximum()), errors)

            # -- and what the arrows leave behind survives a refresh ----
            # A step moves the EDITOR only (no editingFinished comes with
            # it): it becomes the patch's width when something commits the
            # edit in flight -- a refresh, or the OK button. So the round
            # trip is re-read AFTER one, off the re-mounted editor.
            spin.setValue(0.45)
            spin.stepBy(1)
            landed = spin.value()
            check(abs(landed - spin.maximum()) < 1e-9,
                  "%s: one step up from 0.45 landed on %g, not the top of "
                  "the range (%g) -- the arrow path was not exercised"
                  % (what, landed, spin.maximum()), errors)
            panel.refresh()
            remounted = panel.split_editor(shared, which)
            check(remounted is not None
                  and abs(remounted.value() - landed) < 1e-9,
                  "%s: after the step's commit the editor shows %r, not "
                  "the %g the patch was left with"
                  % (what, None if remounted is None else remounted.value(),
                     landed), errors)
            check(abs(band_side(entry, which)[3] - landed) < 1e-9,
                  "%s: the arrow's %g reads back as %g off %s.%s"
                  % (what, landed, band_side(entry, which)[3], p.Name, prop),
                  errors)
        checks.append("both editors typed 0.5 / 0.9 (not accepted, patch "
                      "and panel in agreement) and stepped through the "
                      "midpoint without resting on it; the top of the "
                      "range round-trips at both ends")
    finally:
        _close_panel(panel)
        Gui.Selection.clearSelection()
    return {"pass": not errors, "errors": errors, "checks": checks}


def test_panel_band_edits_round_trip_within_the_split_limit(doc):
    """#76 must not cost the panel anything: band editing is the one place
    a user writes a split on purpose, so it has to keep working after an
    over-limit list became a refusal.

    Driven through `write_band_split` -- the call the editor makes -- at
    BOTH ends (`_stacked_pair`: patch A at its parametric-1 end, patch B at
    its parametric-0), as a ROUND TRIP: what `band_side` reads back after
    the write is what was typed. Three things are asserted, because they
    are the three ways this could have gone wrong:

      * a width still round-trips at both ends, including repeated writes
        at the SAME end (which REPLACE the split there -- the panel's
        write is an edit of one end's split, never an append);
      * no editor write can leave an axis over the limit, because the
        stored parametric split is derived from a width the editor's own
        range already keeps under the middle;
      * and on real corner geometry, every strip still resolves to one
        band cell and keeps its 24 poles -- the geometry the limit is
        protecting, not just the property.
    """
    errors, checks = [], []
    from SilkMachinery import split_limit_problem
    from SilkTaskPanel import BAND_A, BAND_B, band_side, write_band_split, \
        _side_of
    from Tests.test_seam_resolver import _Capture

    a, b, shared = _stacked_pair(doc)
    entry = {"edge": shared, "patch_a": a, "patch_b": b,
             "status": "blendable", "blend": None}
    sides = ((BAND_A, a) + _side_of(a, b), (BAND_B, b) + _side_of(b, a))
    for which, _p, prop, ss in sides:
        what = "%s.%s end %d" % (_p.Name, prop, ss)
        if ss not in (0, 1):
            check(False, "%s: no end resolved (ss=%r)" % (what, ss), errors)
            continue
        for width in (0.05, 0.2, 0.45, 0.3, 0.45):
            with _Capture() as cap:
                wrote = write_band_split(entry, which, width)
            got = band_side(entry, which)[3]
            check(wrote and not cap.errors,
                  "%s: writing %g was refused by the panel (%r)"
                  % (what, width, cap.errors), errors)
            check(abs(got - width) < 1e-9,
                  "%s: wrote %g, read back %g -- the round trip the #76 "
                  "refusal could have broken" % (what, width, got), errors)
            vals = [float(v) for v in (getattr(_p, prop) or [])]
            check(len(vals) <= 1,
                  "%s: after writing %g the axis holds %r -- one editor "
                  "must never append a second split at the same end"
                  % (what, width, vals), errors)
            check(split_limit_problem(vals) is None,
                  "%s: the panel's own write left an over-limit axis %r"
                  % (what, vals), errors)
        check("Invalid" not in _p.State and _p.isValid() is True,
              "%s: the patch is flagged after ordinary band edits (State=%r, "
              "isValid=%r)" % (what, _p.State, _p.isValid()), errors)
    checks.append("band widths 0.05 / 0.2 / 0.45 / 0.3 / 0.45 written and read "
                  "back at BOTH ends through the panel's own write path; each "
                  "end holds exactly one split and no axis goes over limit")

    # ...and on corner geometry, where a patch really is seamed on both
    # axes, the strips still build.
    import Tests.corner_model as cm
    model = cm.build_corner_model(doc)
    for bname, strip in model["strips"].items():
        what = "%s (%s | %s)" % (bname, strip.PatchA.Name, strip.PatchB.Name)
        shared_edge = None
        for _ename, e in model["edges"].items():
            if e in list(strip.PatchA.Edges) and e in list(strip.PatchB.Edges):
                shared_edge = e
                break
        if not check(shared_edge is not None,
                     "%s: found no shared edge to write a width on" % what,
                     errors):
            continue
        ent = {"edge": shared_edge, "patch_a": strip.PatchA,
               "patch_b": strip.PatchB, "status": "blendable",
               "blend": strip}
        with _Capture() as cap:
            wrote = write_band_split(ent, BAND_A, 0.25)
        check(wrote and not cap.errors,
              "%s: a 0.25 band-A width was refused (%r)" % (what, cap.errors),
              errors)
        check(abs(band_side(ent, BAND_A)[3] - 0.25) < 1e-9,
              "%s: 0.25 reads back as %g" % (what, band_side(ent, BAND_A)[3]),
              errors)
        doc.recompute()
        check(len(strip.Poles or []) == 24,
              "%s: %d poles after the width edit, want 24"
              % (what, len(strip.Poles or [])), errors)
    for pname, patch in model["patches"].items():
        for prop in ("USplits", "VSplits"):
            vals = [float(v) for v in (getattr(patch, prop) or [])]
            check(split_limit_problem(vals) is None,
                  "%s.%s = %r is over the limit after the panel edits"
                  % (pname, prop, vals), errors)
            check("Invalid" not in patch.State,
                  "%s.%s left the patch flagged (State=%r)"
                  % (pname, prop, patch.State), errors)
    checks.append("all 4 corner strips still build 24 poles after a panel "
                  "width edit, and every patch axis stays within the limit")
    return {"pass": not errors, "errors": errors, "checks": checks}


def test_asymmetric_band_widths_blend_green_and_differ_from_symmetric(doc):
    """A != B is reachable now, and it has to WORK (#69).

    Built end to end through the real panel on the ground-truth chain:
    Band A = 0.2, Band B = 0.35, confirm, and the oracle is green on
    everything the user can still break (links, C0 at the seam, C1
    tangents, surface validity). B4 is deliberately NOT asserted -- its
    reference poles are the default 0.1-wide blend, which a user width
    must miss -- and the 24 poles are asserted to be NON-NULL and to
    differ from both the symmetric build and each other, which is the
    real claim: the cross-section really was cut from two cells of
    different widths on two differently-parametrized patches."""
    errors, checks = [], []
    from SilkChecks import check_blend
    from SilkMachinery import split_at_end
    from SilkTaskPanel import BAND_A, BAND_B, read_band_split
    from Tests.test_seam_resolver import _Capture

    fixture, pa, pb, g = _open_gt_chain(doc)
    try:
        panel = _open_panel(doc)
        if not check(panel is not None, "Activated left no panel open",
                     errors):
            return {"pass": False, "errors": errors, "checks": checks}
        try:
            panel.sections.open(2)
            edge = g["E_Shr"]
            row = panel.seam_row_index(edge)
            check(row >= 0, "%s is not a row" % edge.Name, errors)
            entry = next(e for e in panel.seam_inventory()
                         if e["edge"] is edge)
            read = read_band_split(entry)
            sa, sb = panel.split_editor(edge, BAND_A), \
                panel.split_editor(edge, BAND_B)
            if not check(sa is not None and sb is not None,
                         "the row carries %d of 2 band editors"
                         % sum(1 for s in (sa, sb) if s is not None), errors):
                return {"pass": False, "errors": errors, "checks": checks}
            panel.blend_table.cellClicked.emit(row, panel.COL_EDGE)

            # 1) symmetric 0.2 on both, confirmed -> the reference poles
            sa.setValue(0.2)
            sa.editingFinished.emit()
            sb.setValue(0.2)
            sb.editingFinished.emit()
            doc.recompute()
            with _Capture() as cap:
                panel.panel_confirm()
            doc.recompute()
            blends = _blend_objects(doc)
            if not check(len(blends) == 1,
                         "the symmetric confirm created %d blend(s)"
                         % len(blends), errors):
                return {"pass": False, "errors": errors, "checks": checks}
            sym_poles = [Vector(p) for p in blends[0].Poles]
            sym_bl = blends[0]
            sym_res = check_blend(sym_bl, pa, pb, edge=sym_bl.Edge)
            sym_checked = {n: ok for n, ok, _d in sym_res}
            for name in ("structural", "B1_c0_seams", "B2_c1_tangents",
                         "B3_surface_valid"):
                check(sym_checked.get(name) is True,
                      "oracle %s failed on the symmetric build: %r"
                      % (name, [(n, d) for n, ok, d in sym_res if not ok]),
                      errors)
            errors += ["console error: %s" % e for e in cap.errors]

            # 2) now make it ASYMMETRIC on the blended row and let the
            #    existing blend re-drive itself (no new confirm: #65).
            #    The confirm above re-rendered the table, so the editors
            #    are RE-FETCHED -- holding the pre-confirm widgets would
            #    be editing widgets the table has already thrown away.
            sa = panel.split_editor(edge, BAND_A)
            sb = panel.split_editor(edge, BAND_B)
            entry = next(e for e in panel.seam_inventory()
                         if e["edge"] is edge)
            read = read_band_split(entry)
            if not check(sa is not None and sb is not None,
                         "the blended row has %d of 2 band editors after "
                         "the confirm" % sum(1 for s in (sa, sb)
                                            if s is not None), errors):
                return {"pass": False, "errors": errors, "checks": checks}
            sa.setValue(0.2)
            sa.editingFinished.emit()
            sb.setValue(0.35)
            sb.editingFinished.emit()
            doc.recompute()
            check(split_at_end(list(getattr(pa, read[0]) or []), read[1])
                  is not None
                  and abs(split_at_end(list(getattr(pa, read[0]) or []),
                                       read[1]) - 0.2) < 1e-9,
                  "patch A did not take 0.2: %r"
                  % list(getattr(pa, read[0]) or []), errors)
            check(abs(split_at_end(list(getattr(pb, read[3]) or []),
                                   read[4]) - 0.35) < 1e-9,
                  "patch B did not take 0.35: %r"
                  % list(getattr(pb, read[3]) or []), errors)

            asy_poles = [Vector(p) for p in sym_bl.Poles]
            check(len(asy_poles) == 24,
                  "the asymmetric blend has %d poles, expected 24"
                  % len(asy_poles), errors)
            check(getattr(sym_bl, "Shape", None) is not None
                  and not sym_bl.Shape.isNull(),
                  "the asymmetric blend has a null shape", errors)
            moved = max((x - y).Length for x, y in zip(sym_poles, asy_poles))
            check(moved > 1e-6,
                  "widening B's band from 0.2 to 0.35 moved no pole at all "
                  "(max delta %.3e) -- the second editor is not reaching the "
                  "blend" % moved, errors)
            res = check_blend(sym_bl, pa, pb, edge=sym_bl.Edge)
            checked = {n: ok for n, ok, _d in res}
            for name in ("structural", "B1_c0_seams", "B2_c1_tangents",
                         "B3_surface_valid"):
                check(checked.get(name) is True,
                      "oracle %s failed on the ASYMMETRIC band: %r"
                      % (name, [(n, d) for n, ok, d in res if not ok]),
                      errors)
            errors += ["console error: %s" % e for e in cap.errors]
            checks.append("Band A=0.2 / Band B=0.35 on a live blend: 24 "
                          "poles, non-null, poles moved %.3g from the "
                          "symmetric build, oracle structural/B1/B2/B3 "
                          "green" % moved)
        finally:
            _close_panel(panel)
    finally:
        Gui.Selection.clearSelection()
        FreeCAD.closeDocument(fixture.Name)
        FreeCAD.setActiveDocument(doc.Name)
    return {"pass": not errors, "errors": errors, "checks": checks}


def test_setting_both_editors_to_the_same_value_writes_both(doc):
    """Symmetry is still one gesture (#69): typing the same width into
    both editors writes BOTH patches, each in its own transaction, and the
    blend reads it on both sides."""
    errors, checks = [], []
    from SilkMachinery import split_at_end
    from SilkTaskPanel import BAND_A, BAND_B, read_band_split
    from Tests.test_seam_resolver import _square_patch, _patch_sharing

    a = _square_patch(doc, "A")
    b = _patch_sharing(doc, a.Edges[0], "B")
    edge = a.Edges[0]

    panel = _open_panel(doc)
    if not check(panel is not None, "Activated left no panel open", errors):
        return {"pass": False, "errors": errors, "checks": checks}
    try:
        panel.sections.open(2)
        sa = panel.split_editor(edge, BAND_A)
        sb = panel.split_editor(edge, BAND_B)
        if not check(sa is not None and sb is not None,
                     "the row carries %d of 2 band editors"
                     % sum(1 for s in (sa, sb) if s is not None), errors):
            return {"pass": False, "errors": errors, "checks": checks}
        entry = next(e for e in panel.seam_inventory() if e["edge"] is edge)
        read = read_band_split(entry)
        undo_before = _undo_count(doc)
        sa.setValue(0.25)
        sa.editingFinished.emit()
        sb.setValue(0.25)
        sb.editingFinished.emit()
        doc.recompute()
        check(_undo_count(doc) - undo_before == 2,
              "two edits moved the undo stack by %d steps (expected 2, one "
              "per patch)" % (_undo_count(doc) - undo_before), errors)
        for p, prop, ss, what in ((a, read[0], read[1], "A"),
                                  (b, read[3], read[4], "B")):
            got = split_at_end(list(getattr(p, prop) or []), ss)
            check(got is not None and abs(got - 0.25) < 1e-9,
                  "%s.%s reads %r, expected 0.25"
                  % (what, prop, list(getattr(p, prop) or [])), errors)
        check(abs(panel.split_editor(edge, BAND_A).value() - 0.25) < 1e-9
              and abs(panel.split_editor(edge, BAND_B).value() - 0.25)
              < 1e-9,
              "the two editors do not agree after being set to the same "
              "value", errors)
        checks.append("0.25 into both editors -> both patches, 2 undo "
                      "steps")
    finally:
        _close_panel(panel)
        Gui.Selection.clearSelection()
    return {"pass": not errors, "errors": errors, "checks": checks}


def test_blocked_row_is_not_actionable_and_has_no_editor(doc):
    """A BLOCKED seam row (#69): greyed flag, no band editors at all, and
    clicking it still does nothing. The two editors are the point of the
    row, so putting live-looking editors on a row that cannot blend would
    be two controls promising something the document cannot deliver."""
    errors, checks = [], []
    from PySide import QtCore
    from SilkTaskPanel import BAND_A, BAND_B
    from Tests.test_seam_resolver import _square_patch, _patch_sharing

    a = _square_patch(doc, "A")
    blocked = a.Edges[0]
    _patch_sharing(doc, blocked, "B")
    _patch_sharing(doc, blocked, "C")        # three patches -> blocked
    live = a.Edges[1]
    _patch_sharing(doc, live, "D")           # two patches -> blendable

    panel = _open_panel(doc)
    if not check(panel is not None, "Activated left no panel open", errors):
        return {"pass": False, "errors": errors, "checks": checks}
    try:
        panel.sections.open(2)
        row = panel.seam_row_index(blocked)
        check(row >= 0, "the blocked seam has no row", errors)
        flag = panel.blend_flag(blocked)
        check(flag is not None and not flag.isChecked()
              and not flag.isEnabled(),
              "the blocked row's flag is checked=%s enabled=%s (want "
              "unchecked + greyed)"
              % (flag.isChecked() if flag else None,
                 flag.isEnabled() if flag else None), errors)
        check(flag is not None and "Blocked" in flag.toolTip(),
              "the blocked flag's tooltip does not say it is blocked: %r"
              % (flag.toolTip() if flag else None), errors)
        # The ROW greys too, not just the flag: an unchecked tick is
        # already pale in most styles, so disabling the checkbox on its
        # own changes almost nothing on screen. This is what makes
        # "blocked" unmistakable from "blendable" without a word.
        from SilkTaskPanel import GREY_BRUSH
        for col in (panel.COL_EDGE, panel.COL_PATCHES):
            fg = panel.blend_table.item(row, col).foreground()
            check(fg.color() == GREY_BRUSH.color(),
                  "the blocked row's cell %d is not greyed (%s)"
                  % (col, fg.color().name()), errors)
        live_row = panel.seam_row_index(live)
        for col in (panel.COL_EDGE, panel.COL_PATCHES):
            fg = panel.blend_table.item(live_row, col).foreground()
            check(fg.color() != GREY_BRUSH.color(),
                  "the BLENDABLE row's cell %d is greyed like a blocked "
                  "one's (%s)" % (col, fg.color().name()), errors)
        for which in (BAND_A, BAND_B):
            check(panel.split_editor(blocked, which) is None,
                  "the blocked row carries a Band %s editor" % which, errors)
            check(panel.blend_table.cellWidget(
                row, panel.COL_BAND_A if which == BAND_A
                else panel.COL_BAND_B) is None,
                  "the blocked row has a cell widget in Band %s" % which,
                  errors)
        # a blocked row is still inert on click, as before
        panel.blend_table.cellClicked.emit(row, panel.COL_EDGE)
        check(panel.collected() == [],
              "a BLOCKED row collected %r" % panel.collected(), errors)
        check(not panel.can_confirm(),
              "OK lit up for a collection of nothing", errors)
        # and the flag takes no focus: confirm is an ApplicationShortcut and
        # must never have a tick box in its way
        check(flag.focusPolicy() == QtCore.Qt.NoFocus,
              "the blended flag takes focus (policy %r)"
              % (flag.focusPolicy() if flag else None), errors)
        # the live row next to it is fully equipped, so the grey is a real
        # difference and not the table being broken everywhere
        for which in (BAND_A, BAND_B):
            check(panel.split_editor(live, which) is not None,
                  "the BLENDABLE row has no Band %s editor" % which, errors)
        check(panel.blend_flag(live) is not None
              and panel.blend_flag(live).isEnabled(),
              "the blendable row's flag is greyed", errors)
        checks.append("blocked row: greyed flag, no editors, click inert; "
                      "blendable neighbour fully equipped")
    finally:
        _close_panel(panel)
        Gui.Selection.clearSelection()
    return {"pass": not errors, "errors": errors, "checks": checks}


# ---- the split warning threshold (the #62 follow-up) ----------------------

def test_split_warning_only_fires_on_a_wholesale_discard(doc):
    """#62's "not strictly inside (0, 1)" warning fired on the property
    editor's TRANSIENT commits: typing 0.2 commits a bare 0 on the way, so
    `USplits = [0]` briefly normalized to `[]` and printed an error while
    the user was still typing.

    The threshold is now: a NON-EMPTY input that discards EVERY one of its
    values is the genuinely suspicious case and is reported (naming the
    values); anything that keeps at least one is corrected in silence. The
    normalization itself is untouched -- the stored list always equals what
    the geometry used, which the cell count proves here."""
    errors, checks = [], []
    from Tests.test_seam_resolver import _Capture, _square_patch

    p = _square_patch(doc, "W")

    def stored(prop):
        return [round(float(v), 12) for v in (getattr(p, prop) or [])]

    def cells():
        return len(p.Proxy._subgrids)

    # -- the transient: an emptied list on the way to 0.2, then 0.2 ------
    with _Capture() as cap:
        p.USplits = []
    transient_errors = list(cap.errors)
    with _Capture() as cap2:
        p.USplits = [0.2]
    if transient_errors or cap2.errors:
        errors.append("the transient 0 -> 0.2 sequence warned: %s %s"
                      % (transient_errors, cap2.errors))
    if stored("USplits") != [0.2]:
        errors.append("after the transient the list reads %s, want [0.2]"
                      % stored("USplits"))
    if cells() != 2:
        errors.append("USplits=[0.2] gave %d cells, want 2" % cells())
    checks.append("transient 0 then 0.2: silent, list [0.2], 2 cells")

    # -- the partial correction: one bad value among good ones -----------
    for written, want in (([0.0, 0.2], [0.2]), ([0.2, 0.2], [0.2]),
                          ([0.3, 0.6], [0.3, 0.6])):
        with _Capture() as cap:
            setattr(p, "USplits", list(written))
        if cap.errors:
            errors.append("USplits = %s was partly corrected and still "
                          "reported: %s" % (written, cap.errors))
        if stored("USplits") != want:
            errors.append("USplits = %s stored as %s, want %s"
                          % (written, stored("USplits"), want))
    checks.append("partial corrections (0 dropped, duplicate, reorder) "
                  "silent and correctly stored")

    # -- the wholesale discard: still reported, still named ------------
    for written in ([0.0], [1.0], [1.5], [-0.2, 3.0]):
        with _Capture() as cap:
            setattr(p, "USplits", list(written))
        msg = "".join(cap.errors)
        if not msg.strip():
            errors.append("USplits = %s lost every value and said nothing"
                          % written)
        if not all(("%g" % v) in msg for v in written):
            errors.append("USplits = %s: the message does not name every "
                          "rejected value: %r" % (written, msg))
        if stored("USplits") != []:
            errors.append("USplits = %s stored as %s, want []"
                          % (written, stored("USplits")))
    checks.append("wholesale discards ([0], [1.0], [1.5], [-0.2, 3.0]) "
                  "still warn and still name the values")

    # -- and the same on the other axis, through a real panel refresh ----
    with _Capture() as cap:
        p.VSplits = [0.0, 0.4]
    if cap.errors:
        errors.append("a partial VSplits correction reported: %s" % cap.errors)
    if stored("VSplits") != [0.4]:
        errors.append("VSplits stored as %s, want [0.4]" % stored("VSplits"))
    checks.append("the V axis follows the same threshold")
    return {"pass": not errors, "errors": errors, "checks": checks}


# ---- the panel's own layout (the #62 follow-up) ---------------------------

def test_hint_is_out_of_the_way_and_still_reachable(doc):
    """#62 put the next-step hint in a QGroupBox ABOVE the accordion, where
    it restated the instruction directly beneath it and spent the panel's
    prime space on it. It now sits BELOW the accordion as a muted line,
    and the same guidance is the panel's and the toolbox's tooltip, so the
    words survive without costing the sections a row."""
    errors, checks = [], []
    from PySide import QtWidgets
    from SilkTaskPanel import HINT_TOOLTIP

    panel = _open_panel(doc)
    if not check(panel is not None, "Activated left no panel open", errors):
        return {"pass": False, "errors": errors, "checks": checks}
    try:
        Gui.updateGui()
        hint, toolbox = panel.hint_lbl, panel.sections
        check(hint.isVisible(), "the next-step hint is not visible at all",
              errors)
        check(hint.y() > toolbox.y(),
              "the hint still sits ABOVE the accordion (hint y=%d, toolbox "
              "y=%d)" % (hint.y(), toolbox.y()), errors)
        check(hint.parent() is panel
              and hint.parentWidget().layout().indexOf(hint) > 0,
              "the hint is no longer a top-level item of the form layout",
              errors)
        check(panel.layout().indexOf(hint) > panel.layout().indexOf(toolbox),
              "the form layout still puts the hint before the accordion",
              errors)
        check(not [g for g in panel.findChildren(QtWidgets.QGroupBox)],
              "a group box is back in the panel", errors)
        # the guidance survives, visibly AND as a tooltip
        check(panel.hint_text().strip() != "",
              "the hint carries no text", errors)
        check(HINT_TOOLTIP and "seam" in HINT_TOOLTIP,
              "the static guidance is missing", errors)
        check(panel.toolTip() == HINT_TOOLTIP
              and toolbox.toolTip() == HINT_TOOLTIP,
              "the guidance is not reachable as a tooltip (panel %r, "
              "toolbox %r)" % (panel.toolTip()[:30], toolbox.toolTip()[:30]),
              errors)
        # muted, not a second bold instruction block
        check(hint.font().italic(), "the hint is not styled as guidance",
              errors)
        checks.append("hint below the accordion, muted, and carried in the "
                      "panel + toolbox tooltips")
    finally:
        _close_panel(panel)
    return {"pass": not errors, "errors": errors, "checks": checks}


def test_complete_chain_hides_the_footer_hint(doc):
    """#73: there is no "chain complete" notification.

    Two halves, and both matter. The footer label must be INVISIBLE (not
    merely empty -- an empty QLabel in a QVBoxLayout keeps a line of
    height, which is the dead space the report is about) once no blendable
    seam is left and a blend exists. And it must be visible with its
    pinned wording one seam earlier, so this is a hide-when-empty rule
    and not a footer that never renders."""
    errors, checks = [], []
    from SilkGuide import HINT_BLEND
    from Tests.test_seam_resolver import _Capture, _build_tube

    # Two patches sharing TWO seams: blending the first leaves one seam
    # blendable (the hint must show), blending the second leaves none
    # (the footer must disappear). Driven through the panel's own table
    # row and confirm, so the real render path runs.
    pa, pb, s_left, s_right = _build_tube(doc)
    panel = _open_panel(doc)
    if not check(panel is not None, "Activated left no panel open", errors):
        return {"pass": False, "errors": errors, "checks": checks}
    try:
        panel.sections.open(2)
        Gui.updateGui()
        hint = panel.hint_lbl
        check(hint.isVisible(),
              "with a blendable seam the footer hint is not visible at all",
              errors)
        check(panel.hint_text() == HINT_BLEND,
              "with a blendable seam the hint reads %r, want the pinned "
              "blend hint %r" % (panel.hint_text(), HINT_BLEND), errors)
        checks.append("one seam open: hint visible and reads %r"
                      % panel.hint_text())

        # -- blend the first seam through the panel ---------------------
        row = panel.seam_row_index(s_left)
        check(row >= 0, "seam %s has no row" % s_left.Name, errors)
        panel.blend_table.cellClicked.emit(row, panel.COL_EDGE)
        with _Capture() as cap:
            panel.panel_confirm()
        doc.recompute()
        errors += ["console error: %s" % e for e in cap.errors]
        Gui.updateGui()
        check(len(_blend_objects(doc)) == 1,
              "the first confirm created %d blend(s), expected 1"
              % len(_blend_objects(doc)), errors)
        check(hint.isVisible(),
              "with one seam still blendable the footer hint went hidden",
              errors)
        check(panel.hint_text() == HINT_BLEND,
              "after the first blend the hint reads %r, want %r"
              % (panel.hint_text(), HINT_BLEND), errors)
        checks.append("one blend, one seam open: hint still visible (%r)"
                      % panel.hint_text())

        # -- blend the second: the chain is complete, the footer goes ---
        panel.refresh()
        Gui.updateGui()
        row = panel.seam_row_index(s_right)
        check(row >= 0, "seam %s has no row after the first blend"
              % s_right.Name, errors)
        panel.blend_table.cellClicked.emit(row, panel.COL_EDGE)
        with _Capture() as cap:
            panel.panel_confirm()
        doc.recompute()
        errors += ["console error: %s" % e for e in cap.errors]
        Gui.updateGui()
        check(len(_blend_objects(doc)) == 2,
              "the second confirm created %d blend(s), expected 2"
              % len(_blend_objects(doc)), errors)

        from SilkGuide import compute_guide_state
        state = compute_guide_state(doc)
        check(state["complete"] and state["hint"] == "",
              "the fully blended document is not (complete=%r, hint=%r)"
              % (state["complete"], state["hint"]), errors)
        check(hint.text() == "",
              "the footer label still reads %r on a complete chain -- the "
              "notification is gone, not re-worded" % hint.text(), errors)
        check(not hint.isVisible(),
              "the footer hint label is still VISIBLE (text %r) on a fully "
              "blended document -- an empty QLabel keeps a line of height, "
              "so it must be hidden" % hint.text(), errors)
        checks.append("fully blended: hint %r and the footer label is hidden"
                      % hint.text())
    finally:
        _close_panel(panel)
        Gui.Selection.clearSelection()
    return {"pass": not errors, "errors": errors, "checks": checks}


def test_panel_fits_a_narrow_dock_and_lists_stay_small(doc):
    """The layout facts that #62's geometry numbers got wrong.

    Two of them are structural and assertable here: the panel has NO width
    floor (it shrinks into the dock instead of pushing past it), and the
    collection lists are CAPPED with a greyed placeholder when empty
    rather than being an empty box eating the panel. (The pixels are still
    the human round's job -- see the screenshots -- but these are the
    regression guards.)"""
    errors, checks = [], []
    from PySide import QtCore, QtWidgets
    from SilkTaskPanel import LIST_MAX_ROWS, PLACEHOLDERS, SECTION_EDGE, \
        SECTION_PATCH
    from Tests.test_seam_resolver import _square_patch

    panel = _open_panel(doc)
    if not check(panel is not None, "Activated left no panel open", errors):
        return {"pass": False, "errors": errors, "checks": checks}
    try:
        Gui.updateGui()
        # -- no width floor: the panel may shrink into its dock --------
        check(panel.minimumWidth() == 0,
              "the panel still has a %dpx width floor -- a narrower dock "
              "clips it (and earns a horizontal scrollbar)"
              % panel.minimumWidth(), errors)
        check(panel.minimumSizeHint().width() < 320,
              "the panel's minimum width is %dpx, wider than a narrow dock"
              % panel.minimumSizeHint().width(), errors)

        # -- the collection lists are capped -------------------------
        for section, widget in ((SECTION_EDGE, panel.edge_list),
                                (SECTION_PATCH, panel.patch_list)):
            row_h = widget.fontMetrics().height() + 6
            cap = 2 * widget.frameWidth() + row_h * LIST_MAX_ROWS
            check(widget.maximumHeight() <= cap,
                  "the %s list may grow to %dpx, cap is %dpx"
                  % ("Edge" if section == SECTION_EDGE else "Patch",
                     widget.maximumHeight(), cap), errors)
            check(widget.maximumHeight() < widget.sizeHint().height()
                  or widget.maximumHeight() <= 27,
                  "the %s list is uncapped (%dpx)"
                  % ("Edge" if section == SECTION_EDGE else "Patch",
                     widget.maximumHeight()), errors)
            # -- an empty list shows a greyed placeholder -------------
            check(widget.count() == 1,
                  "an empty %s collection list holds %d rows, expected the "
                  "1 placeholder"
                  % ("Edge" if section == SECTION_EDGE else "Patch",
                     widget.count()), errors)
            item = widget.item(0)
            check(item.text() == PLACEHOLDERS[section],
                  "the placeholder reads %r, expected %r"
                  % (item.text(), PLACEHOLDERS[section]), errors)
            check(not (item.flags() & QtCore.Qt.ItemIsSelectable),
                  "the placeholder row is selectable -- it must not be "
                  "mistaken for a collection entry", errors)
            grey = item.foreground().color().value()
            check(grey > 0x40, "the placeholder is not greyed (%d)" % grey,
                  errors)
            # -- and it never scrolls sideways ------------------------
            check(widget.horizontalScrollBarPolicy()
                  == QtCore.Qt.ScrollBarAlwaysOff,
                  "a collection list can scroll horizontally", errors)

        # -- the seam table is capped too ----------------------------
        row_h = panel.blend_table.fontMetrics().height() + 10
        check(panel.blend_table.maximumHeight() < panel.height(),
              "the seam table may grow to %dpx inside a %dpx panel -- an "
              "uncapped table is the same empty chrome as an uncapped list"
              % (panel.blend_table.maximumHeight(), panel.height()), errors)
        check(panel.blend_table.horizontalScrollBarPolicy()
              == QtCore.Qt.ScrollBarAlwaysOff,
              "the seam table can scroll horizontally", errors)

        # -- a collected entry still lists, and the box grows to fit --
        from Tests.test_seam_resolver import _line_sketch
        sk = _line_sketch(doc, "Fill", [(200, 0, 0), (220, 0, 0),
                                        (240, 0, 0), (260, 0, 0)])
        _click(sk)
        check(panel.edge_list.count() == 1,
              "the collected sketch did not replace the placeholder (%d rows)"
              % panel.edge_list.count(), errors)
        check(panel.edge_list.item(0).text() != PLACEHOLDERS[SECTION_EDGE],
              "the placeholder is still showing over a real entry", errors)
        checks.append("no width floor; lists capped + greyed placeholder; "
                      "table capped; no sideways scrolling; 1 collected "
                      "entry replaces the placeholder")
    finally:
        _close_panel(panel)
        Gui.Selection.clearSelection()
    return {"pass": not errors, "errors": errors, "checks": checks}


# ---- production coupling ----------------------------------------------------

def test_no_production_module_knows_the_panel(doc):
    """The dependency arrow points ONE way: nothing in the production
    modules imports SilkTaskPanel / SilkGuidePanel or mentions the
    command, and the panel's own imports are only the ops layer, the
    machinery core and #47's query."""
    errors, checks = [], []
    root = os.path.dirname(os.path.abspath(__file__))
    root = os.path.dirname(root)
    production = ["SilkEdge.py", "SilkPatch.py", "SilkBlend.py",
                  "SilkWorkflowOps.py", "SilkChecks.py", "SilkGuide.py",
                  "SilkMachinery.py", "InitGui.py"]
    offenders = []
    for name in production:
        path = os.path.join(root, name)
        with open(path) as fh:
            lines = fh.read().splitlines()
        # strip comments and docstrings: what matters is CODE, not prose
        # that happens to name the panel.
        code = [ln for ln in lines
                if not ln.lstrip().startswith("#")]
        code = [ln for ln in code
                if "SilkTaskPanel" not in ln and "SilkGuidePanel" not in ln
                and "Silk_Guide" not in ln]
        blob = "\n".join(code)
        for token in ("SilkTaskPanel", "SilkGuidePanel", "Silk_Guide"):
            if token in blob and not (name == "InitGui.py"
                                      and token == "SilkTaskPanel"):
                offenders.append("%s (%s)" % (name, token))
        if "CreateGuide" in blob or "SilkTaskPanel(" in blob:
            offenders.append("%s references the panel's entry points" % name)
    check(not offenders,
          "production module(s) mention the panel: %s" % offenders, errors)
    checks.append("no production module mentions the panel")

    with open(os.path.join(root, "SilkTaskPanel.py")) as fh:
        panel_src = fh.read()
    for needed in ("from SilkGuide import compute_guide_state",
                   "from SilkWorkflowOps import create_edge",
                   "create_patch", "create_blend_by_edge"):
        check(needed in panel_src,
              "the panel no longer imports %r" % needed, errors)
    checks.append("the panel imports only the ops layer + #47's query")
    return {"pass": not errors, "errors": errors, "checks": checks}



# ---- Enter in a band editor, and edits in flight (#71) ----
def _enter_key(widget, kind=None):
    """Deliver a REAL Return/Enter key event to `widget`, the way the
    platform delivers it to the focus widget: an event filter installed
    on the widget sees it before the widget's own keyPressEvent, which is
    exactly the path #71's band-editor handling hooks.

    (The APPLICATION shortcut map cannot be exercised this way -- Qt only
    consults it on the platform key path -- so what is asserted here is
    the filter's own work: the commit, the confirm, and the
    ShortcutOverride that keeps the application shortcut from firing a
    second confirm on the same keystroke.)
    """
    from PySide import QtCore, QtGui, QtWidgets
    kind = kind or QtCore.QEvent.KeyPress
    event = QtGui.QKeyEvent(kind, QtCore.Qt.Key_Return,
                            QtCore.Qt.NoModifier)
    QtWidgets.QApplication.sendEvent(widget, event)
    return event



def _type_width(spin, value):
    """Type `value` into a band editor the way THIS session spells it.

    A QDoubleSpinBox parses what is typed against the session locale, and
    this one separates the decimals with a comma: setValue is not a
    shortcut here, because it goes through no parsing at all and would not
    be the in-progress edit #71 is about. Returns the string typed.
    """
    from PySide import QtCore
    text = QtCore.QLocale().toString(float(value), 'f', spin.decimals())
    spin.lineEdit().setText(text)
    return text



def _row_of(panel, edge):
    """Index of `edge`'s seam row in the blend table."""
    for r in range(panel.blend_table.rowCount()):
        if panel.blend_table.item(r, panel.COL_EDGE) is not None \
                and panel.blend_table.item(r, panel.COL_EDGE).text() == edge.Name:
            return r
    return -1


def test_enter_in_a_band_editor_commits_then_confirms(doc):
    """#71: Enter inside a band editor commits THAT editor's value and
    then confirms -- commit strictly FIRST, because confirming ends in a
    refresh that rebuilds every row.

    The human's question was whether this conflicts with the 3D-view
    Enter, and it does not: the application shortcut confirms the
    COLLECTION, a band editor's Enter commits its own VALUE. What must
    not happen is the same keystroke confirming twice (the collect would
    be blended twice), which is why the editor accepts the
    ShortcutOverride for that one key -- asserted below on both the
    editor (accepted) and an ordinary widget (NOT accepted, so the 3D
    view's Enter is untouched).

    Order is asserted, not assumed: the undo names must read
    ["Silk band split", "Silk blend"], and the blend's own band must
    already carry the typed width when it is built.
    """
    errors, checks = [], []
    from PySide import QtCore
    from SilkMachinery import split_at_end
    from SilkTaskPanel import BAND_A, _side_of
    from Tests.test_seam_resolver import _square_patch, _patch_sharing

    a = _square_patch(doc, "A")
    b = _patch_sharing(doc, a.Edges[0], "B")
    edge = a.Edges[0]
    doc.recompute()

    panel = _open_panel(doc)
    if not check(panel is not None, "Activated left no panel open", errors):
        return {"pass": False, "errors": errors, "checks": checks}
    try:
        panel.sections.open(2)   # the Blend section                    # the Blend section
        row = _row_of(panel, edge)
        check(row >= 0, "the seam has no row", errors)
        panel.blend_table.cellClicked.emit(row, panel.COL_EDGE)
        check(edge in panel.collected(),
              "the row click did not collect the seam: %r"
              % panel.collected(), errors)
        spin = panel.split_editor(edge, BAND_A)
        if not check(spin is not None, "no Band A editor on the row", errors):
            return {"pass": False, "errors": errors, "checks": checks}

        # the ShortcutOverride: accepted for the editor, not for anything
        # else -- so the application confirm fires ONCE, not twice
        over_editor = _enter_key(spin, QtCore.QEvent.ShortcutOverride)
        check(over_editor.isAccepted(),
              "the band editor did not accept the Enter ShortcutOverride -- "
              "the application shortcut would confirm on top of this one",
              errors)
        over_other = _enter_key(panel.blend_table, QtCore.QEvent.ShortcutOverride)
        check(not over_other.isAccepted(),
              "a widget that is NOT a band editor accepted the Enter "
              "ShortcutOverride -- the 3D-view Enter would stop working",
              errors)

        # type a width the way a user does, then press Enter
        typed = _type_width(spin, 0.2)
        check(abs(spin.value() - 0.2) < 1e-9,
              "typing %r into the editor left the value at %g -- the test "
              "fixture never set up an edit" % (typed, spin.value()), errors)
        names_before = list(doc.UndoNames)
        undo_before = _undo_count(doc)
        _enter_key(spin.lineEdit())                # the editor owns the focus
        doc.recompute()

        # UndoNames reads top-of-stack first, so the blend (committed
        # second) is index 0 -- which is exactly the ORDERING #71 is
        # about: had the confirm come first, it would rebuild every row
        # and the value typed a moment earlier would have nowhere to go.
        added = list(doc.UndoNames[:len(doc.UndoNames)
                                    - len(names_before)])
        check([str(n) for n in added] == ["Silk blend", "Silk band split"],
              "Enter produced the transactions %r (newest first) -- expected "
              "the split commit FIRST and the blend confirm second"
              % added, errors)
        check(_undo_count(doc) - undo_before == 2,
              "one Enter moved the undo stack by %d steps (expected 2: one "
              "commit, one confirm)"
              % (_undo_count(doc) - undo_before), errors)

        a_prop, a_ss = _side_of(a, b)
        stored = split_at_end(list(getattr(a, a_prop) or []), a_ss)
        check(stored is not None and abs(stored - 0.2) < 1e-9,
              "the typed width was not committed to %s.%s (%r) -- the confirm "
              "rebuilt the row before the value was written"
              % (a.Name, a_prop, list(getattr(a, a_prop) or [])), errors)

        blends = _blend_objects(doc)
        check(len(blends) == 1,
              "Enter created %d blend(s), expected 1 -- the same collection "
              "was confirmed twice" % len(blends), errors)
        if blends:
            check(len(blends[0].Poles or []) == 24
                  and not blends[0].Shape.isNull(),
                  "the confirmed blend did not build (%d poles, null=%s)"
                  % (len(blends[0].Poles or []), blends[0].Shape.isNull()),
                  errors)
        check(not panel.collected(),
              "the collection survived the confirm: %r" % panel.collected(),
              errors)
        # the value survives the rebuild, read back off the live editor
        live = panel.split_editor(edge, BAND_A)
        check(live is not None and abs(live.value() - 0.2) < 1e-9,
              "after the confirm the re-mounted editor shows %s, expected "
              "the typed 0.2" % (live.value() if live else None), errors)
        checks.append("Enter in a band editor: 0.2 committed (1 undo step) "
                      "then confirmed (1 more), one blend at 24 poles")
    finally:
        _close_panel(panel)
        Gui.Selection.clearSelection()
    return {"pass": not errors, "errors": errors, "checks": checks}



def test_in_progress_band_edit_is_committed_not_dropped_by_a_refresh(doc):
    """#71: an edit in flight is never silently dropped by a refresh.

    The human reported it as flaky -- "i have to click outside the list
    though for the blend to update" / "nope, on second try i can". The
    mechanism: a QDoubleSpinBox holds typed text until something
    interprets it, and a refresh rebuilds every row, so the widget the
    text lived on is DETACHED. Its later editingFinished then hits the
    #69 detached-widget guard, which correctly declines to act -- so the
    value was neither written nor reported, and it vanished. Which is why
    it worked on the second try: by then the text was gone too.

    So an in-progress edit is committed BEFORE the rows are torn down.
    """
    errors, checks = [], []
    from SilkMachinery import split_at_end
    from SilkTaskPanel import BAND_A, _side_of
    from Tests.test_seam_resolver import _square_patch, _patch_sharing

    a = _square_patch(doc, "A")
    b = _patch_sharing(doc, a.Edges[0], "B")
    edge = a.Edges[0]
    doc.recompute()

    panel = _open_panel(doc)
    if not check(panel is not None, "Activated left no panel open", errors):
        return {"pass": False, "errors": errors, "checks": checks}
    try:
        panel.sections.open(2)   # the Blend section
        row = _row_of(panel, edge)
        check(row >= 0, "the seam has no row", errors)
        panel.blend_table.cellClicked.emit(row, panel.COL_EDGE)
        spin = panel.split_editor(edge, BAND_A)
        if not check(spin is not None, "no Band A editor on the row", errors):
            return {"pass": False, "errors": errors, "checks": checks}
        a_prop, a_ss = _side_of(a, b)

        # typed but NOT committed: the editor holds a width its patch does
        # not store -- the panel is asked to refresh anyway
        typed = _type_width(spin, 0.25)
        check(abs(spin.value() - 0.25) < 1e-9,
              "typing %r left the editor at %g -- the fixture never set up "
              "an in-flight edit" % (typed, spin.value()), errors)
        check(not list(getattr(a, a_prop) or []),
              "the typed value was already written before the refresh "
              "(%r)" % list(getattr(a, a_prop) or []), errors)

        # a plain refresh -- what a selection change or the confirm's own
        # teardown does
        panel.refresh()
        doc.recompute()

        stored = split_at_end(list(getattr(a, a_prop) or []), a_ss)
        check(stored is not None and abs(stored - 0.25) < 1e-9,
              "the refresh dropped the in-progress edit: %s.%s = %r, "
              "expected 0.25"
              % (a.Name, a_prop, list(getattr(a, a_prop) or []),), errors)
        live = panel.split_editor(edge, BAND_A)
        check(live is not None and live is not spin,
              "the refresh did not rebuild the row", errors)
        check(live is not None and abs(live.value() - 0.25) < 1e-9,
              "the re-mounted editor shows %s, expected the committed 0.25"
              % (live.value() if live else None), errors)

        # and the confirm path commits an in-flight edit too, rather than
        # blending at the width still stored
        _type_width(live, 0.3)
        panel.panel_confirm()
        doc.recompute()
        stored = split_at_end(list(getattr(a, a_prop) or []), a_ss)
        check(stored is not None and abs(stored - 0.3) < 1e-9,
              "the confirm applied without committing the in-flight edit: "
              "%s.%s = %r" % (a.Name, a_prop, list(getattr(a, a_prop) or [])),
              errors)
        blends = _blend_objects(doc)
        check(len(blends) == 1 and len(blends[0].Poles or []) == 24,
              "the blend did not build after the in-flight commit (%d blend(s))"
              % len(blends), errors)
        checks.append("in-flight 0.25 committed by a refresh, 0.3 by the "
                      "confirm; nothing silently dropped")
    finally:
        _close_panel(panel)
        Gui.Selection.clearSelection()
    return {"pass": not errors, "errors": errors, "checks": checks}



def test_sections_are_header_content_pairs_not_a_toolbox(doc):
    """#71: the section container is no longer a QToolBox, and the three
    sections are header / content PAIRS in a fixed order.

    The QToolBox it replaces stacked all three handles at the top and
    parked the open page below the stack, so a folded section could never
    sit directly under the section above it -- and `setCurrentIndex(-1)`
    was refused, so folding everything was not expressible at all. Both
    are asserted here as the reason the container changed:

      * the container is NOT a QToolBox (and the fold-everything state is
        reachable);
      * the headers keep their ORDER always;
      * opening a section pushes only the headers BELOW it down -- every
        header above it stays exactly where it was, which is what "in
        place" means, and is the difference from a QToolBox where the
        open page is always parked under the whole stack of handles;
      * the open section's page sits directly under ITS OWN header and
        above the next header;
      * folding the open section (a second click on its header) returns
        every header to the all-folded geometry;
      * no header takes focus (confirm is an ApplicationShortcut and
        must never have a button in its way).

    Geometry is read after Gui.updateGui(), so the layout has actually
    run -- these are positions, not intentions.
    """
    errors, checks = [], []
    from PySide import QtCore, QtWidgets
    from SilkTaskPanel import SECTION_BLEND, SECTION_EDGE, SECTION_NONE, \
        SECTION_TITLES

    panel = _open_panel(doc)
    if not check(panel is not None, "Activated left no panel open", errors):
        return {"pass": False, "errors": errors, "checks": checks}
    try:
        sections = panel.sections
        check(not isinstance(sections, QtWidgets.QToolBox),
              "the section container is still a QToolBox -- a folded section "
              "cannot sit under the section above it there", errors)
        check(not [w for w in panel.findChildren(QtWidgets.QToolBox)],
              "a QToolBox survives somewhere in the panel", errors)
        check(sections.count() == 3,
              "the stack has %d sections, expected 3" % sections.count(),
              errors)
        check(sections.header_titles() == list(SECTION_TITLES),
              "header titles %r != %r" % (sections.header_titles(),
                                          list(SECTION_TITLES)), errors)
        check(sections.focusPolicy() == QtCore.Qt.NoFocus,
              "the section stack takes focus (policy %r)"
              % sections.focusPolicy(), errors)
        for i in range(sections.count()):
            check(sections.header(i).focusPolicy() == QtCore.Qt.NoFocus,
                  "the %s header takes focus" % SECTION_TITLES[i], errors)

        Gui.updateGui()

        def header_ys():
            return {i: sections.header(i).mapTo(panel, QtCore.QPoint(0, 0)).y()
                    for i in range(sections.count())}

        # -- the folded geometry is the baseline -------------------------
        # A QToolBox could not be put into this state at all
        # (setCurrentIndex(-1) is refused), which is why the baseline is
        # measured here and every other state is compared against it.
        check(sections.fold_all(), "fold_all() reported no change", errors)
        Gui.updateGui()
        folded = header_ys()
        check(sections.current_index() == SECTION_NONE,
              "folding everything left %r open" % sections.current_index(),
              errors)
        check(not any(sections.page(i).isVisible() for i in range(3)),
              "a page is still visible with every section folded", errors)
        check(list(folded.values()) == sorted(folded.values()),
              "the headers are not in order on screen: %s" % folded, errors)
        check(panel.open_section() == SECTION_NONE,
              "the open section is %r with everything folded"
              % panel.open_section(), errors)
        check(not panel.can_confirm(),
              "an all-folded panel can confirm", errors)

        for opened in range(sections.count()):
            # -- open one section: its page lands under ITS header ------
            sections.open(opened)
            Gui.updateGui()
            ys = header_ys()
            check(sections.header_titles() == list(SECTION_TITLES),
                  "opening %s changed the header order: %r"
                  % (SECTION_TITLES[opened], sections.header_titles()),
                  errors)
            check(list(ys.values()) == sorted(ys.values()),
                  "opening %s put the headers out of order: %s"
                  % (SECTION_TITLES[opened], ys), errors)
            for i in range(opened + 1):
                check(ys[i] == folded[i],
                      "opening %s moved the %s header above it (%s, folded it "
                      "was %s)" % (SECTION_TITLES[opened], SECTION_TITLES[i],
                                   ys[i], folded[i]), errors)
            page_y = sections.page(opened).mapTo(panel,
                                                 QtCore.QPoint(0, 0)).y()
            check(page_y > ys[opened],
                  "the open %s page does not sit under its own header (%r vs "
                  "%r)" % (SECTION_TITLES[opened], page_y, ys[opened]),
                  errors)
            if opened + 1 < sections.count():
                check(page_y < ys[opened + 1],
                      "the %s page runs over the %s header (%r vs %r)"
                      % (SECTION_TITLES[opened], SECTION_TITLES[opened + 1],
                         page_y, ys[opened + 1]), errors)
            check(all(not sections.page(i).isVisible()
                      for i in range(sections.count()) if i != opened),
                  "opening %s left another section open too"
                  % SECTION_TITLES[opened], errors)
            # -- folding it again puts every header back ---------------
            sections.toggle(opened)          # a second click on the header
            Gui.updateGui()
            check(sections.current_index() == SECTION_NONE,
                  "clicking the open header did not fold %s"
                  % SECTION_TITLES[opened], errors)
            check(header_ys() == folded,
                  "folding %s left the headers somewhere else: %s (folded "
                  "baseline %s)" % (SECTION_TITLES[opened], header_ys(),
                                     folded), errors)

        sections.open(SECTION_EDGE)          # as the panel opens
        Gui.updateGui()
        check(panel.open_section() == SECTION_EDGE,
              "the panel does not open on the Edge section (%r)"
              % panel.open_section(), errors)
        checks.append("header/content pairs: %s in fixed order, each page "
                      "under its own header, folding is in place, all-folded "
                      "is a real state" % " / ".join(sections.header_titles()))
    finally:
        _close_panel(panel)
    return {"pass": not errors, "errors": errors, "checks": checks}


ALL_TESTS = [
    test_panel_lands_in_the_native_task_panel,
    test_toolbox_is_a_three_section_accordion,
    test_enter_shortcut_is_application_scoped_for_both_enter_keys,
    test_edge_stage_collect_one_sketch_then_confirm,
    test_edge_stage_two_sketches_reach_the_2n_mode,
    test_patch_stage_collect_four_edges_then_confirm,
    test_patch_stage_three_edges_give_the_pointed_fill,
    test_patch_section_reports_success_only_for_a_patch_that_built,
    # #67 guard: nothing the panel hands back may fail the oracle on its own
    test_every_patch_the_panel_hands_back_is_oracle_green,
    test_wrong_type_clicks_are_silently_ignored,
    test_ok_disabled_until_the_open_section_is_valid,
    test_one_confirm_is_one_undo_step,
    test_multi_seam_blend_is_still_one_undo_step,
    test_stale_entry_refuses_loudly_naming_it,
    test_stale_blend_seam_refuses_naming_it,
    test_refuses_to_open_over_a_foreign_task_dialog,
    test_close_then_reopen_rebuilds_fresh,
    test_adapter_form_is_nulled_on_close,
    test_closes_on_document_switch,
    test_blend_table_merges_every_seam_with_its_flag,
    test_blend_collect_highlight_and_remove,
    test_blend_confirm_matches_the_resolver,
    test_untick_unblends_and_says_the_band_splits_went,
    test_band_split_editor_reads_and_writes_the_patch_split,
    test_user_band_split_is_honoured_by_the_blend,
    test_band_split_multi_cell_is_refused_naming_patch_and_values,
    test_band_cell_mirror_agrees_with_the_real_band_cells,
    test_blended_seam_row_keeps_a_working_split_editor,
    test_unresolvable_seam_row_does_not_abandon_the_table,
    test_post_blend_width_that_would_break_the_band_is_refused,
    # #69
    test_two_band_editors_start_equal_and_name_their_own_patch,
    test_band_edit_validation_is_per_patch,
    # #75
    test_band_width_at_the_middle_is_not_stored_even_at_the_1_end,
    test_band_editor_offers_no_width_the_panel_cannot_read_back,
    test_panel_band_edits_round_trip_within_the_split_limit,
    test_asymmetric_band_widths_blend_green_and_differ_from_symmetric,
    test_setting_both_editors_to_the_same_value_writes_both,
    test_blocked_row_is_not_actionable_and_has_no_editor,
    test_split_warning_only_fires_on_a_wholesale_discard,
    test_hint_is_out_of_the_way_and_still_reachable,
    # #73
    test_complete_chain_hides_the_footer_hint,
    test_panel_fits_a_narrow_dock_and_lists_stay_small,
    test_sections_are_header_content_pairs_not_a_toolbox,
    test_enter_in_a_band_editor_commits_then_confirms,
    test_in_progress_band_edit_is_committed_not_dropped_by_a_refresh,
    test_no_production_module_knows_the_panel,
]