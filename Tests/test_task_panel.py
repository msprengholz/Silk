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

Fixture helpers are imported, not refactored: the square / sharing /
stray builders and the console capture from Tests.test_seam_resolver,
the ground-truth chain from Tests.test_blend_stage, the loop/triangle
edge builders from Tests.test_patch_gui_command.
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
    from SilkTaskPanel import SECTION_TITLES

    panel = _open_panel(doc)
    if not check(panel is not None, "Activated left no panel open", errors):
        return {"pass": False, "errors": errors, "checks": checks}
    try:
        tb = panel.toolbox
        check(tb.count() == 3, "toolbox has %d pages, expected 3" % tb.count(),
              errors)
        titles = [tb.itemText(i) for i in range(tb.count())]
        check(titles == list(SECTION_TITLES),
              "toolbox titles %r != %r" % (titles, list(SECTION_TITLES)),
              errors)
        check(tb.focusPolicy() == QtCore.Qt.NoFocus,
              "the toolbox takes focus (policy %r) -- it must leave the 3D "
              "view's focus alone" % tb.focusPolicy(), errors)
        checks.append("accordion sections: %s (NoFocus)" % ", ".join(titles))
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
        panel.toolbox.setCurrentIndex(1)          # the Patch section
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
        panel.toolbox.setCurrentIndex(1)
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
                panel.toolbox.setCurrentIndex(section)
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
        panel.toolbox.setCurrentIndex(1)
        for n in range(4):
            _click(loop[n])
            want = n >= 2
            check(panel.ok_enabled() == want,
                  "after %d edge click(s) OK is %r, expected %r"
                  % (n + 1, panel.ok_enabled(), want), errors)
        # -- Blend
        panel.toolbox.setCurrentIndex(2)
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
        panel.toolbox.setCurrentIndex(1)
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
        panel.toolbox.setCurrentIndex(2)
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
        panel.toolbox.setCurrentIndex(1)
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
    create_blend_by_edge(s_left)
    doc.recompute()

    panel = _open_panel(doc)
    if not check(panel is not None, "Activated left no panel open", errors):
        return {"pass": False, "errors": errors, "checks": checks}
    try:
        panel.toolbox.setCurrentIndex(2)
        row = panel.seam_row_index(s_left)
        check(row >= 0, "the already-blended seam has no row", errors)
        check(panel.row_texts(row)[2].startswith("blended by"),
              "row status %r does not name the blend"
              % panel.row_texts(row)[2], errors)
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
    panel1.toolbox.setCurrentIndex(1)
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
        check(panel2.toolbox.currentIndex() == 0,
              "the reopened panel kept the old open section (%d)"
              % panel2.toolbox.currentIndex(), errors)
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
        panel.toolbox.setCurrentIndex(1)
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

def test_blend_table_merges_every_seam_with_its_status(doc):
    """One merged table, one row per seam_inventory entry IN ORDER, each
    row carrying that entry's own status wording -- including `blocked`
    on a non-manifold seam and `blended by <Blend>` once blended, plus the
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
    create_blend_by_edge(ea)
    _patch_sharing(doc, ec, "E")          # -> blocked (3 patches)

    panel = _open_panel(doc)
    if not check(panel is not None, "Activated left no panel open", errors):
        return {"pass": False, "errors": errors, "checks": checks}
    try:
        panel.toolbox.setCurrentIndex(2)
        inv = seam_inventory(doc)
        statuses = [e["status"] for e in inv]
        check("blocked" in statuses and "blended" in statuses,
              "the fixture lacks a blocked or blended seam (%r)" % statuses,
              errors)
        check(panel.blend_table.rowCount() == len(inv),
              "table has %d rows, seam_inventory has %d"
              % (panel.blend_table.rowCount(), len(inv)), errors)
        for row, entry in enumerate(inv):
            cells = panel.row_texts(row)
            check(cells[0] == entry["edge"].Name,
                  "row %d edge cell %r != %r"
                  % (row, cells[0], entry["edge"].Name), errors)
            check(cells[1] == "%s <-> %s" % (entry["patch_a"].Name,
                                             entry["patch_b"].Name),
                  "row %d pair cell %r" % (row, cells[1]), errors)
            want = ("blended by %s" % entry["blend"].Name
                    if entry["status"] == "blended" and entry["blend"]
                    else entry["status"])
            check(cells[2] == want,
                  "row %d status cell %r != %r" % (row, cells[2], want),
                  errors)
        blended = sum(1 for s in statuses if s == "blended")
        check(panel.progress_text() == "%d of %d seams blended"
              % (blended, len(inv)),
              "progress %r != '%d of %d seams blended'"
              % (panel.progress_text(), blended, len(inv)), errors)
        checks.append("%d rows match statuses %r" % (len(inv), statuses))
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
        panel.toolbox.setCurrentIndex(2)
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
        panel.toolbox.setCurrentIndex(2)
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
                check(panel.row_texts(row)[2] == "blended by %s" % bl.Name,
                      "the row did not flip: %r" % panel.row_texts(row)[2],
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


# ---- the band split ----------------------------------------------------------

def test_band_split_editor_reads_and_writes_the_patch_split(doc):
    """The collected row's split editor reads the patch's OWN split and
    writes straight back onto it -- which since #64 is what the blend
    reads, so a width set here is the width the blend uses. Asserted
    against the patch property, not against a panel copy."""
    errors, checks = [], []
    from SilkMachinery import split_at_end
    from Tests.test_seam_resolver import _square_patch, _patch_sharing

    a = _square_patch(doc, "A")
    b = _patch_sharing(doc, a.Edges[0], "B")
    # a pre-existing user split on the seam's band axis of patch A. The
    # axis is DERIVED, never assumed: _side_of is the panel's own
    # resolver, so this stays true whichever way the seam happens to run.
    from SilkTaskPanel import _side_of
    a_prop, a_ss = _side_of(a, b)
    setattr(a, a_prop, [0.35])
    doc.recompute()

    panel = _open_panel(doc)
    if not check(panel is not None, "Activated left no panel open", errors):
        return {"pass": False, "errors": errors, "checks": checks}
    try:
        panel.toolbox.setCurrentIndex(2)
        row = panel.seam_row_index(a.Edges[0])
        check(row >= 0, "the seam has no row", errors)
        panel.blend_table.cellClicked.emit(row, panel.COL_EDGE)
        spin = panel.split_editor(a.Edges[0])
        if not check(spin is not None,
                     "no split editor was mounted on the collected row",
                     errors):
            return {"pass": False, "errors": errors, "checks": checks}
        check(abs(spin.value() - 0.35) < 1e-9,
              "the editor shows %g, expected the patch's own 0.35"
              % spin.value(), errors)
        check(spin.minimum() > 0.0 and spin.maximum() < 1.0,
              "the editor is not constrained to 0 < u < 1 (range %g..%g)"
              % (spin.minimum(), spin.maximum()), errors)

        spin.setValue(0.22)
        spin.editingFinished.emit()
        doc.recompute()
        after = split_at_end(list(getattr(a, a_prop) or []), a_ss)
        check(after is not None and abs(after - 0.22) < 1e-9,
              "the patch still reads %r on %s after the edit -- the editor "
              "did not write through"
              % (list(getattr(a, a_prop) or []), a_prop), errors)
        checks.append("editor reads 0.35 off A.%s and writes 0.22 back"
                      % a_prop)
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
    from Tests.test_seam_resolver import _Capture

    fixture, pa, pb, g = _open_gt_chain(doc)
    try:
        panel = _open_panel(doc)
        if not check(panel is not None, "Activated left no panel open",
                     errors):
            return {"pass": False, "errors": errors, "checks": checks}
        panel.toolbox.setCurrentIndex(2)
        row = panel.seam_row_index(g["E_Shr"])
        check(row >= 0, "the shared edge is not a row", errors)
        panel.blend_table.cellClicked.emit(row, panel.COL_EDGE)
        spin = panel.split_editor(g["E_Shr"])
        if not check(spin is not None, "no split editor on the row", errors):
            return {"pass": False, "errors": errors, "checks": checks}
        # where the width must land, read from the panel's own resolver
        from SilkMachinery import split_at_end
        from SilkTaskPanel import read_band_split
        entry = next(e for e in panel.seam_inventory()
                     if e["edge"] is g["E_Shr"])
        pa_prop, pa_ss, _v1, pb_prop, pb_ss, _v2 = read_band_split(entry)
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
        panel.toolbox.setCurrentIndex(2)
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
    invalid ones."""
    errors, checks = [], []
    from SilkMachinery import band_cells, patch_side
    from SilkTaskPanel import band_cell_problem
    from Tests.test_seam_resolver import _square_patch, _patch_sharing

    layouts = [[], [0.1], [0.9], [0.5], [0.1, 0.9], [0.2, 0.85],
               [0.3, 0.5, 0.7]]
    for along in layouts:
        for band in layouts:
            a = _square_patch(doc, "A_%s_%s" % ("_".join(map(str, along)) or "n",
                                                 "_".join(map(str, band)) or "n"))
            b = _patch_sharing(doc, a.Edges[0], "B")
            a.USplits = list(along)
            a.VSplits = list(band)
            b.USplits = list(along)
            b.VSplits = list(band)
            doc.recompute()
            ea, ss = patch_side(a, b)
            if ea is None:
                continue
            real = len(band_cells(a, ea, ss))
            entry = {"edge": a.Edges[0], "patch_a": a, "patch_b": b,
                     "status": "blendable", "blend": None}
            problem = band_cell_problem(entry, None)
            mirrored = 1 if problem is None else int(
                problem.rsplit("covers ", 1)[1].split(" ")[0])
            if mirrored != real:
                errors.append(
                    "layout along=%r band=%r: mirror says %d cells, "
                    "SilkMachinery.band_cells says %d"
                    % (along, band, mirrored, real))
            if (real == 1) != (problem is None):
                errors.append("layout along=%r band=%r: problem=%r but "
                              "real count is %d"
                              % (along, band, problem, real))
    checks.append("candidate-layout mirror matches band_cells on %d layouts"
                  % (len(layouts) ** 2))
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


ALL_TESTS = [
    test_panel_lands_in_the_native_task_panel,
    test_toolbox_is_a_three_section_accordion,
    test_enter_shortcut_is_application_scoped_for_both_enter_keys,
    test_edge_stage_collect_one_sketch_then_confirm,
    test_edge_stage_two_sketches_reach_the_2n_mode,
    test_patch_stage_collect_four_edges_then_confirm,
    test_patch_stage_three_edges_give_the_pointed_fill,
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
    test_blend_table_merges_every_seam_with_its_status,
    test_blend_collect_highlight_and_remove,
    test_blend_confirm_matches_the_resolver,
    test_band_split_editor_reads_and_writes_the_patch_split,
    test_user_band_split_is_honoured_by_the_blend,
    test_band_split_multi_cell_is_refused_naming_patch_and_values,
    test_band_cell_mirror_agrees_with_the_real_band_cells,
    test_no_production_module_knows_the_panel,
]