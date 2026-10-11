"""
Silk_Guide command + task panel tests (ticket #48).

The panel is ORCHESTRATION + DISPLAY ONLY, so these tests assert exactly
the three things that can be wrong about such a panel:

  1. It renders what the #47 headless query says -- the hint VERBATIM,
     and one table row per seam_inventory entry with that entry's own
     status wording (blendable / blended by <Blend> / blocked), plus the
     "N of M seams blended" roll-up.
  2. Its seam-row action IS create_blend_by_edge -- same created object,
     same already-blended no-op, same refusal message (the resolver owns
     the words; the panel must not re-word or re-implement them).
  3. It is side-effect-free outside the one container: opening and
     reopening binds exactly ONE WorkflowGuide and disturbs nothing else.

Headless-vs-modal boundary (the panel IS a real Qt dialog):
  FreeCAD's `Gui.Control.showDialog` is NOT modal -- it embeds the widget
  in the task panel and returns immediately (verified), so the tests can
  drive the real command and the real widgets through RPC with no user.
  Nothing here needs a synthetic click: `cellClicked` is wired to
  `_on_row_clicked` -> `activate_seam_row(row)`, and the tests call that
  very method, so they exercise the same call path a row click takes.
  Only the two convenience buttons (which call Gui.runCommand) are not
  driven here -- running a real command needs a live command manager, and
  they add nothing but a delegation (asserted structurally instead).

Fixture helpers are imported, not refactored: the square / sharing /
stray builders and the console capture from Tests.test_seam_resolver,
and the ground-truth chain from Tests.test_blend_stage.
"""
import sys

import FreeCAD
from FreeCAD import Gui


def check(cond, msg, errors):
    if not cond:
        errors.append(msg)
    return cond


def _blend_objects(doc):
    return [o for o in doc.Objects
            if getattr(o, "object_type", None) in ("Blend", "BlendStrip")]


def _guide_objects(doc):
    return [o for o in doc.Objects
            if getattr(o, "object_type", None) == "WorkflowGuide"]


def _open_panel(doc):
    """Drive Silk_Guide's Activated (which binds the container and shows
    the panel) and return the live panel. Silently skips the assertion
    target if Qt is unavailable so a console-only FreeCAD fails with a
    readable error rather than an import crash."""
    from SilkGuidePanel import CreateGuide, current_panel
    CreateGuide().Activated()
    panel = current_panel()
    if panel is None:
        FreeCAD.closeDocument(FreeCAD.ActiveDocument.Name)
    return panel


def _close_panel(panel):
    if panel is not None:
        try:
            panel.close_panel()
        except Exception:
            pass


def test_guide_command_opens_panel_with_container(doc):
    """Silk_Guide.Activated binds exactly ONE WorkflowGuide container
    (via SilkGuide.create_guide) and shows the task panel; the hint
    label renders compute_guide_state(doc)["hint"] VERBATIM -- same
    string object content, no re-wording, no prefix."""
    errors, checks = [], []
    from SilkGuide import compute_guide_state

    panel = _open_panel(doc)
    if not check(panel is not None,
                 "Activated did not leave a panel open", errors):
        return {"pass": False, "errors": errors, "checks": checks}
    try:
        guides = _guide_objects(doc)
        check(len(guides) == 1,
              "expected exactly 1 WorkflowGuide container, got %d"
              % len(guides), errors)
        state = compute_guide_state(doc)
        shown = panel.hint_text()
        check(shown == state["hint"],
              "hint label %r != compute_guide_state hint %r"
              % (shown, state["hint"]), errors)
        check(panel.guide is guides[0] if guides else False,
              "the panel is not bound to the document's container", errors)
        checks.append("container bound, hint rendered verbatim: %r" % shown)
    finally:
        _close_panel(panel)
    return {"pass": not errors, "errors": errors, "checks": checks}


def test_guide_panel_seam_rows_match_seam_inventory(doc):
    """The table has ONE row per seam_inventory entry, in order, and each
    row shows that entry's edge name, its patch pair, and ITS OWN status
    wording -- including `blocked` on a non-manifold seam and
    `blended by <Blend>` once blended. The progress label carries the
    seam_counts roll-up."""
    errors, checks = [], []
    from SilkWorkflowOps import create_blend_by_edge, seam_inventory
    from Tests.test_seam_resolver import _square_patch, _patch_sharing

    # two blendable seams (two disjoint square pairs)
    a = _square_patch(doc, "A")
    ea = a.Edges[0]
    b = _patch_sharing(doc, ea, "B")
    c = _square_patch(doc, "C")
    ec = c.Edges[0]
    d = _patch_sharing(doc, ec, "D")
    # blend one of them so a "blended by" row exists
    blend = create_blend_by_edge(ea)
    check(blend is not None,
          "setup: create_blend_by_edge on the first seam failed", errors)
    # a third patch on ec -> non-manifold, blocked
    _patch_sharing(doc, ec, "E")

    panel = _open_panel(doc)
    if not check(panel is not None,
                 "Activated did not leave a panel open", errors):
        return {"pass": False, "errors": errors, "checks": checks}
    try:
        inv = seam_inventory(doc)
        check(panel.seam_table.rowCount() == len(inv),
              "table has %d rows, seam_inventory has %d"
              % (panel.seam_table.rowCount(), len(inv)), errors)
        for row, entry in enumerate(inv):
            cells = panel.row_texts(row)
            check(cells[0] == entry["edge"].Name,
                  "row %d edge cell %r != %r"
                  % (row, cells[0], entry["edge"].Name), errors)
            check(cells[1] == "%s <-> %s" % (entry["patch_a"].Name,
                                             entry["patch_b"].Name),
                  "row %d pair cell %r != %s <-> %s"
                  % (row, cells[1], entry["patch_a"].Name,
                     entry["patch_b"].Name), errors)
            want = ("blended by %s" % entry["blend"].Name
                    if entry["status"] == "blended" and entry["blend"]
                    else entry["status"])
            check(cells[2] == want,
                  "row %d status cell %r != %r" % (row, cells[2], want),
                  errors)
        # the blocked seam is actually present (guards against the test
        # passing on an all-blendable fixture)
        statuses = [e["status"] for e in inv]
        check("blocked" in statuses and "blended" in statuses,
              "fixture lacks a blocked or blended seam (got %r)" % statuses,
              errors)
        total = len(inv)
        blended = sum(1 for s in statuses if s == "blended")
        check(panel.progress_text() == "%d of %d seams blended"
              % (blended, total),
              "progress label %r != %d of %d seams blended"
              % (panel.progress_text(), blended, total), errors)
        checks.append("%d rows match seam_inventory statuses %r"
                      % (len(inv), statuses))
    finally:
        _close_panel(panel)
    return {"pass": not errors, "errors": errors, "checks": checks}


def test_guide_panel_seam_row_click_matches_resolver(doc):
    """A seam-row click IS create_blend_by_edge: clicking a `blendable`
    row creates exactly ONE blend (full check_blend oracle green on the
    ground-truth chain), the row flips to `blended by <Blend>`, and the
    status line names the blend + edge. Clicking the same row again is
    the idempotent no-op -- no second blend, and the RESOLVER's
    'already blended by' message (unmodified) on the status line."""
    errors, checks = [], []
    import os
    from SilkChecks import check_blend
    from Tests.test_blend_stage import _build_gt_chain
    from Tests.test_seam_resolver import _Capture

    fixture_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "Resources", "Test_files",
                                "Silk_Workflow.FCStd")
    fixture = FreeCAD.openDocument(fixture_path)
    FreeCAD.setActiveDocument(doc.Name)  # openDocument activates fixture
    pa, pb, g = _build_gt_chain(doc, fixture)
    e_shr = g["E_Shr"]

    panel = _open_panel(doc)
    if not check(panel is not None,
                 "Activated did not leave a panel open", errors):
        FreeCAD.closeDocument(fixture.Name)
        return {"pass": False, "errors": errors, "checks": checks}
    try:
        row = panel.seam_row_index(e_shr)
        check(row >= 0,
              "the shared edge %s is not a row in the panel" % e_shr.Name,
              errors)
        if row < 0:
            return {"pass": False, "errors": errors, "checks": checks}

        # click row 1: creates the blend. Emitting the REAL Qt signal
        # proves the whole wiring (cellClicked -> _on_row_clicked ->
        # activate_seam_row), not just the method underneath it.
        with _Capture() as cap1:
            panel.seam_table.cellClicked.emit(row, panel.COL_EDGE)
        doc.recompute()
        blends = _blend_objects(doc)
        check(len(blends) == 1,
              "row click created %d blend objects, expected 1"
              % len(blends), errors)
        if blends:
            bl = blends[0]
            check(panel.status_text() == "%s created across %s"
                  % (bl.Name, e_shr.Name),
                  "status line %r != '%s created across %s'"
                  % (panel.status_text(), bl.Name, e_shr.Name), errors)
            check(any(bl.Name in m for m in cap1.messages),
                  "no console message naming the created blend %s; got %s"
                  % (bl.Name, cap1.messages), errors)
            results = check_blend(bl, pa, pb,
                                  reference_poles=fixture.BlendStrip.Poles)
            bad = [(n, d) for n, ok, d in results if not ok]
            check(not bad,
                  "oracle flagged the panel-built blend: %s" % bad, errors)
            checks.append("row click -> %s across %s: oracle %d checks, "
                          "%d failed" % (bl.Name, e_shr.Name, len(results),
                                         len(bad)))
        # the row now reads "blended by <blend>"
        check(panel.seam_table.rowCount() == 1
              and panel.row_texts(0)[2] == "blended by %s" % blends[0].Name
              if blends else False,
              "row did not flip to 'blended by %s'" % blends[0].Name
              if blends else "no blend to check", errors)

        # click again: idempotent no-op, resolver's message on status
        with _Capture() as cap2:
            panel.activate_seam_row(panel.seam_row_index(e_shr))
        doc.recompute()
        check(len(_blend_objects(doc)) == 1,
              "second row click created a second blend (%d total)"
              % len(_blend_objects(doc)), errors)
        check("already blended" in panel.status_text(),
              "second click status %r lacks the resolver's "
              "'already blended' no-op message" % panel.status_text(), errors)
        check(any("already blended" in m and blends[0].Name in m
                  for m in cap2.messages),
              "resolver's 'already blended by %s' message did not reach "
              "the console; got %s" % (blends[0].Name, cap2.messages),
              errors)
        checks.append("2nd click: no 2nd blend, resolver no-op on status")
    finally:
        _close_panel(panel)
        FreeCAD.closeDocument(fixture.Name)
        FreeCAD.setActiveDocument(doc.Name)
    return {"pass": not errors, "errors": errors, "checks": checks}


def test_guide_panel_blocked_row_refuses(doc):
    """A `blocked` (non-manifold) row refuses: NO blend object is created
    and the RESOLVER's own 'not a blendable seam' message (unmodified,
    only whitespace-trimmed for the label) reaches the status line."""
    errors, checks = [], []
    from Tests.test_seam_resolver import _square_patch, _patch_sharing, \
        _splits, _Capture

    a = _square_patch(doc, "A")
    e0 = a.Edges[0]
    _patch_sharing(doc, e0, "B")
    _patch_sharing(doc, e0, "C")  # 3 patches -> non-manifold, blocked

    panel = _open_panel(doc)
    if not check(panel is not None,
                 "Activated did not leave a panel open", errors):
        return {"pass": False, "errors": errors, "checks": checks}
    try:
        row = panel.seam_row_index(e0)
        check(row >= 0, "blocked seam %s has no row" % e0.Name, errors)
        check(panel.row_texts(row)[2] == "blocked",
              "row status %r != 'blocked'" % panel.row_texts(row)[2],
              errors)
        with _Capture() as cap:
            panel.activate_seam_row(row)
        doc.recompute()
        check(not _blend_objects(doc),
              "a blocked row created %d blend object(s)"
              % len(_blend_objects(doc)), errors)
        for pname in ("A", "B", "C"):
            u, v = _splits(doc.getObject(pname))
            check(not u and not v,
                  "the refusal wrote splits on %s (U=%s V=%s)"
                  % (pname, u, v), errors)
        check("not a blendable seam" in panel.status_text(),
              "status line %r lacks the resolver's non-manifold refusal"
              % panel.status_text(), errors)
        check(any("not a blendable seam" in e for e in cap.errors),
              "resolver's non-manifold console error missing; got %s"
              % cap.errors, errors)
        checks.append("blocked row refused, no blend, no splits, "
                      "resolver message on the status line")
    finally:
        _close_panel(panel)
    return {"pass": not errors, "errors": errors, "checks": checks}


def test_guide_panel_refresh_on_selection_change(doc):
    """Panel-side refresh (settled Q16b): the panel subscribes FreeCAD's
    selection-change observer while open, and a selection change makes it
    re-query compute_guide_state and push the derived state into the
    container. Closing the panel unsubscribes and leaves the container
    intact."""
    errors, checks = [], []
    from SilkGuide import compute_guide_state
    from Tests.test_seam_resolver import _square_patch, _patch_sharing

    a = _square_patch(doc, "A")
    ea = a.Edges[0]
    _patch_sharing(doc, ea, "B")

    panel = _open_panel(doc)
    if not check(panel is not None,
                 "Activated did not leave a panel open", errors):
        return {"pass": False, "errors": errors, "checks": checks}
    try:
        check(panel._hook_installed,
              "the panel did not install its selection observer", errors)
        guide = panel.guide
        # add a second seam so the state's numbers actually move
        from SilkWorkflowOps import create_blend_by_edge
        c = _square_patch(doc, "C")
        ec = c.Edges[0]
        _patch_sharing(doc, ec, "D")
        # make a selection change; the observer fires refresh() which
        # re-derives and syncs the container.
        Gui.Selection.clearSelection()
        Gui.Selection.addSelection(a)
        state = compute_guide_state(doc)
        check(guide.NextStepHint == state["hint"],
              "container NextStepHint %r != fresh state hint %r"
              % (guide.NextStepHint, state["hint"]), errors)
        check(guide.PatchCount == state["counts"]["patches"]
              and guide.SeamCount == state["seam_counts"]["total"],
              "container counts not synced after selection change "
              "(PatchCount=%s SeamCount=%s, want %s/%s)"
              % (guide.PatchCount, guide.SeamCount,
                 state["counts"]["patches"], state["seam_counts"]["total"]),
              errors)
        checks.append("selection change re-derived and synced the container")

        # closing leaves the container intact and unsubscribes
        panel.close_panel()
        check(not panel._hook_installed,
              "close_panel did not remove the selection observer", errors)
        check(guide.Document is doc,
              "close_panel disturbed the guide container's document link",
              errors)
        checks.append("close_panel unsubscribed; container left intact")
        Gui.Selection.clearSelection()
    finally:
        _close_panel(panel)
    return {"pass": not errors, "errors": errors, "checks": checks}


def test_guide_reopen_does_not_duplicate_container(doc):
    """Reopening the panel is idempotent: a second Silk_Guide activation
    on a document that already has a container binds the SAME container
    (still exactly one), shows a live panel again, and leaves every
    pre-existing object undisturbed (counts unchanged)."""
    errors, checks = [], []
    from Tests.test_seam_resolver import _square_patch, _patch_sharing

    a = _square_patch(doc, "A")
    ea = a.Edges[0]
    _patch_sharing(doc, ea, "B")
    before = {o.Name for o in doc.Objects}

    from SilkGuidePanel import current_panel
    panel1 = _open_panel(doc)
    if not check(panel1 is not None,
                 "first Activated did not leave a panel open", errors):
        return {"pass": False, "errors": errors, "checks": checks}
    guide1 = panel1.guide
    # reopen without closing first (the command closes any live panel
    # itself; here we close explicitly then reopen to model the user
    # pressing the menu item twice)
    _close_panel(panel1)
    panel2 = _open_panel(doc)
    if not check(panel2 is not None,
                 "second Activated did not leave a panel open", errors):
        return {"pass": False, "errors": errors, "checks": checks}
    try:
        guides = _guide_objects(doc)
        check(len(guides) == 1,
              "reopening duplicated the container: %d WorkflowGuide objects"
              % len(guides), errors)
        check(panel2.guide is guide1,
              "reopen bound a different container than the first open",
              errors)
        # no pre-existing object was disturbed, and exactly the one
        # container was added on the first open (nothing added now)
        check({o.Name for o in doc.Objects} == before | {guide1.Name},
              "reopen disturbed pre-existing objects; docs objects = %r"
              % sorted(o.Name for o in doc.Objects), errors)
        checks.append("reopen reused the container, disturbed nothing")
    finally:
        _close_panel(panel2)
    return {"pass": not errors, "errors": errors, "checks": checks}


def test_guide_convenience_buttons_only_delegate(doc):
    """The two convenience buttons do nothing but run the existing
    commands -- asserted structurally (they call Gui.runCommand with the
    existing command names and nothing else), so no live command is
    invoked from the test."""
    errors, checks = [], []
    from SilkGuidePanel import GuideTaskPanel, CreateGuide

    panel = _open_panel(doc)
    if not check(panel is not None,
                 "Activated did not leave a panel open", errors):
        return {"pass": False, "errors": errors, "checks": checks}
    try:
        ran = []
        orig = Gui.runCommand
        Gui.runCommand = lambda name, idx=0: ran.append(name)
        try:
            panel.run_create_edge()
            panel.run_create_patch()
        finally:
            Gui.runCommand = orig
        check(ran == ["Silk_CreateEdge", "Silk_CreatePatch"],
              "convenience buttons invoked %r, expected exactly "
              "['Silk_CreateEdge', 'Silk_CreatePatch']" % ran, errors)
        # the buttons are wired to those same methods
        check(panel.edge_btn.text() == "Create Edge"
              and panel.patch_btn.text() == "Create Patch",
              "unexpected button labels: %r / %r"
              % (panel.edge_btn.text(), panel.patch_btn.text()), errors)
        # the command is registered
        check(getattr(CreateGuide, "GetResources")(
            CreateGuide())["MenuText"] == "Silk Guide",
            "CreateGuide is not the Silk Guide command", errors)
        checks.append("buttons delegate to the two existing commands only")
    finally:
        _close_panel(panel)
    return {"pass": not errors, "errors": errors, "checks": checks}


def test_guide_reopen_after_module_reload_replaces_stale_dialog(doc):
    """FreeCAD allows exactly ONE task dialog and raises on a second one.
    Our own `_open_panel` bookkeeping can disagree with reality after a
    module reload (the RPC runner deletes every `Silk*` module between
    runs): the reload resets `_open_panel` to None while the previous
    panel's dialog is still on screen. Reopening must still succeed --
    `open_guide_panel` has to notice the live dialog and replace it."""
    errors, checks = [], []
    import importlib
    from SilkGuidePanel import current_panel

    panel1 = _open_panel(doc)
    if not check(panel1 is not None,
                 "first Activated did not leave a panel open", errors):
        return {"pass": False, "errors": errors, "checks": checks}
    try:
        # simulate the module reload: a FRESH module instance that knows
        # nothing about the panel whose dialog is still showing.
        for m in list(sys.modules):
            if m == "SilkGuidePanel":
                del sys.modules[m]
        fresh = importlib.import_module("SilkGuidePanel")
        check(fresh.current_panel() is None,
              "the reloaded module should not remember the open panel",
              errors)
        check(Gui.Control.activeDialog(),
              "expected the stale dialog to still be showing", errors)
        try:
            panel2 = fresh.open_guide_panel(doc)
        except Exception as e:
            errors.append("open_guide_panel raised with a stale dialog "
                          "showing: %s: %s" % (type(e).__name__, e))
            panel2 = None
        if panel2 is not None:
            check(len(_guide_objects(doc)) == 1,
                  "reopen after reload made %d containers"
                  % len(_guide_objects(doc)), errors)
            checks.append("reopen after a module reload replaced the "
                          "stale dialog instead of raising")
            _close_panel(panel2)
    finally:
        _close_panel(panel1)
    return {"pass": not errors, "errors": errors, "checks": checks}


ALL_TESTS = [
    test_guide_command_opens_panel_with_container,
    test_guide_panel_seam_rows_match_seam_inventory,
    test_guide_panel_seam_row_click_matches_resolver,
    test_guide_panel_blocked_row_refuses,
    test_guide_panel_refresh_on_selection_change,
    test_guide_reopen_does_not_duplicate_container,
    test_guide_convenience_buttons_only_delegate,
    test_guide_reopen_after_module_reload_replaces_stale_dialog,
]
