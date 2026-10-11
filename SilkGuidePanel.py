#    This file is part of Silk
#    (c) 2025
#
#    NURBS Surface modeling tools focused on low degree and seam continuity (FreeCAD Workbench)
#
#    Guide panel -- the `Silk_Guide` command + task panel (ticket #48).
#
#    This module is ORCHESTRATION + DISPLAY ONLY. It contains:
#
#      * no construction logic   -- every action delegates to an existing
#        seam: blendable rows go through SilkWorkflowOps.create_blend_by_edge
#        (the #44 resolver), the convenience buttons go through
#        Gui.runCommand for the existing Silk_CreateEdge / Silk_CreatePatch.
#      * no geometry             -- nothing here builds or touches a shape.
#      * no production coupling  -- SilkEdge / SilkPatch / SilkBlend /
#        SilkWorkflowOps / SilkGuide do not import this module and know
#        nothing about it. The dependency arrow points ONE way.
#
#    The state lives in the #47 headless core:
#      compute_guide_state(doc)  -- the stateless query (source of truth)
#      create_guide(doc)         -- the WorkflowGuide container (state sink)
#    and this panel is only a VIEW over that query plus a thin action
#    surface. It re-queries on FreeCAD's selection-change signal and
#    after each of its own actions (settled Q16b: panel-side refresh),
#    then writes the derived hint into the container so the property
#    editor reflects it. Closing the panel leaves the container intact;
#    nothing auto-opens on document load.
#
#    The resolver OWNS the words: refusals ("... is not a blendable
#    seam ...") and the idempotent no-op ("... are already blended by
#    X ...") are captured verbatim off the console and shown on the
#    status line. Nothing here re-implements or re-words them.

import FreeCAD
from FreeCAD import Gui

try:
    from PySide import QtWidgets, QtCore
except ImportError:  # pragma: no cover - console-only FreeCAD
    QtWidgets = None
    QtCore = None

from SilkGuide import compute_guide_state, create_guide

import os, Silk_dummy
path_Silk = os.path.dirname(Silk_dummy.__file__)
path_Silk_icons = os.path.join(path_Silk, "Resources", "Icons")
iconPath = path_Silk_icons + "/Silk.svg"


# The container's object_type, as written by SilkGuide.WorkflowGuide.
# Used to find an existing container so reopening never duplicates it.
GUIDE_TYPE = "WorkflowGuide"

# The currently open panel (None when no panel is open). Kept so tests and
# the command can reach the live panel without re-opening a dialog, and so
# a second activation can replace the first panel cleanly.
_open_panel = None


# ---- console tap -----------------------------------------------------------
# The resolver reports through the console, which stays canonical (every
# message is forwarded to the real console exactly as printed). The tap
# only ALSO records, so the status line can show the resolver's own words
# instead of a paraphrase. Nothing is swallowed and nothing is re-worded.

class _ConsoleTap:
    """Record console messages/errors raised inside the `with` block,
    while still forwarding every one of them to the real console."""

    def __enter__(self):
        self.messages = []
        self.errors = []
        self._om = FreeCAD.Console.PrintMessage
        self._oe = FreeCAD.Console.PrintError
        FreeCAD.Console.PrintMessage = self._record(self.messages, self._om)
        FreeCAD.Console.PrintError = self._record(self.errors, self._oe)
        return self

    def __exit__(self, *args):
        FreeCAD.Console.PrintMessage = self._om
        FreeCAD.Console.PrintError = self._oe
        return False

    @staticmethod
    def _record(bucket, forward):
        def _log(msg):
            bucket.append(str(msg))
            forward(msg)
        return _log


# ---- selection-change hook (settled Q16b) ----------------------------------
# FreeCAD 1.1's selection observer callback names. Selection *changes*
# only -- preselection fires continuously while the mouse moves over the
# 3D view and refreshing on it would be pure noise.

class _SelectionRefreshHook:
    """Selection observer that forwards selection CHANGES to the panel's
    refresh(). Installed when the panel opens, removed when it closes --
    nothing else in the workbench is subscribed."""

    def __init__(self, panel):
        self.panel = panel

    def _changed(self, *_args):
        self.panel.refresh()

    # the four selection-change callbacks FreeCAD 1.1 dispatches
    def addSelection(self, docName, objName, subName, pos):
        self._changed(docName, objName, subName, pos)

    def removeSelection(self, docName, objName, subName):
        self._changed(docName, objName, subName)

    def setSelection(self, docName):
        self._changed(docName)

    def clearSelection(self, docName):
        self._changed(docName)


# ---- the task panel --------------------------------------------------------

class GuideTaskPanel(QtWidgets.QWidget if QtWidgets else object):
    """The `Silk_Guide` task panel: hint, seam table, status line.

    Contents, and nothing else:
      * `hint_lbl`     -- compute_guide_state(doc)["hint"], rendered
                          VERBATIM (never re-worded, never re-formatted).
      * `progress_lbl` -- "N of M seams blended" from the state's
                          seam_counts roll-up.
      * `seam_table`   -- one row per state["seams"] entry: the edge name,
                          the patch pair (A <-> B), and the status
                          (blendable / blended by <Blend> / blocked).
                          A row click IS "select that edge in 3D": it runs
                          the #44 resolver on that edge, immediately, with
                          no confirmation dialog.
      * `status_lbl`   -- the last action's outcome, one line.
      * two convenience buttons that ONLY invoke the existing commands.

    Owns no document state of its own: `refresh()` re-derives everything
    from `compute_guide_state` on every call.
    """

    COL_EDGE, COL_PATCHES, COL_STATUS = 0, 1, 2
    COLUMNS = ("Edge", "Patches", "Status")

    def __init__(self, guide, doc=None):
        super().__init__()
        self.guide = guide
        self.doc = doc if doc is not None else guide.Document
        # seam_inventory entries, index-parallel with the table's rows
        self._rows = []
        self._hook = _SelectionRefreshHook(self)
        self._hook_installed = False

        form = QtWidgets.QVBoxLayout(self)

        # --- hint -------------------------------------------------------
        hint_box = QtWidgets.QGroupBox("Next step")
        hint_layout = QtWidgets.QVBoxLayout(hint_box)
        self.hint_lbl = QtWidgets.QLabel("")
        font = self.hint_lbl.font()
        font.setBold(True)
        self.hint_lbl.setFont(font)
        self.hint_lbl.setWordWrap(True)
        hint_layout.addWidget(self.hint_lbl)
        form.addWidget(hint_box)

        # --- seam table + progress --------------------------------------
        self.progress_lbl = QtWidgets.QLabel("")
        form.addWidget(self.progress_lbl)

        self.seam_table = QtWidgets.QTableWidget(0, len(self.COLUMNS))
        self.seam_table.setHorizontalHeaderLabels(list(self.COLUMNS))
        self.seam_table.setEditTriggers(
            QtWidgets.QAbstractItemView.NoEditTriggers)
        self.seam_table.setSelectionBehavior(
            QtWidgets.QAbstractItemView.SelectRows)
        self.seam_table.setSelectionMode(
            QtWidgets.QAbstractItemView.SingleSelection)
        self.seam_table.verticalHeader().setVisible(False)
        self.seam_table.horizontalHeader().setStretchLastSection(True)
        self.seam_table.cellClicked.connect(self._on_row_clicked)
        form.addWidget(self.seam_table)

        # --- status line -------------------------------------------------
        self.status_lbl = QtWidgets.QLabel("")
        self.status_lbl.setWordWrap(True)
        form.addWidget(self.status_lbl)

        # --- convenience: run the EXISTING commands, nothing else --------
        buttons = QtWidgets.QHBoxLayout()
        self.edge_btn = QtWidgets.QPushButton("Create Edge")
        self.edge_btn.setToolTip(
            "Run the Silk_CreateEdge command (from the current selection)")
        self.edge_btn.clicked.connect(self.run_create_edge)
        self.patch_btn = QtWidgets.QPushButton("Create Patch")
        self.patch_btn.setToolTip(
            "Run the Silk_CreatePatch command (from the current selection)")
        self.patch_btn.clicked.connect(self.run_create_patch)
        buttons.addWidget(self.edge_btn)
        buttons.addWidget(self.patch_btn)
        buttons.addStretch(1)
        form.addLayout(buttons)

    # ---- panel protocol (FreeCAD task panel) ---------------------------

    def open(self):
        """Called by Gui.Control when the dialog is shown."""
        self.install_hook()
        self.refresh()

    def accept(self):
        self.close_panel()

    def reject(self):
        self.close_panel()

    def close_panel(self):
        """Unsubscribe and close. The guide container stays in the
        document, fully valid (it is a state sink, not a view)."""
        self.remove_hook()
        global _open_panel
        if _open_panel is self:
            _open_panel = None
        Gui.Control.closeDialog()

    # ---- selection-change wiring (settled Q16b) ------------------------

    def install_hook(self):
        if not self._hook_installed:
            Gui.Selection.addObserver(self._hook)
            self._hook_installed = True

    def remove_hook(self):
        if self._hook_installed:
            Gui.Selection.removeObserver(self._hook)
            self._hook_installed = False

    # ---- refresh --------------------------------------------------------

    def refresh(self):
        """Re-derive the whole panel from compute_guide_state(doc) and
        write the hint into the container. THE ONLY refresh path: the
        panel never reads a stored stage."""
        doc = self.doc
        if doc is None or doc.Name not in FreeCAD.listDocuments():
            return  # the document went away under us
        state = compute_guide_state(doc)

        # The hint is rendered exactly as the query formatted it.
        self.hint_lbl.setText(state["hint"])
        counts = state["seam_counts"]
        self.progress_lbl.setText(
            "%d of %d seams blended" % (counts["blended"], counts["total"]))

        current = self.seam_table.currentRow()
        self.seam_table.setRowCount(len(state["seams"]))
        self._rows = list(state["seams"])
        for row, entry in enumerate(self._rows):
            texts = (entry["edge"].Name,
                     "%s <-> %s" % (entry["patch_a"].Name,
                                    entry["patch_b"].Name),
                     status_text(entry))
            for col, text in enumerate(texts):
                item = self.seam_table.item(row, col)
                if item is None:
                    item = QtWidgets.QTableWidgetItem(text)
                    self.seam_table.setItem(row, col, item)
                else:
                    item.setText(text)

        # Keep the focus on the table after an in-place update (no
        # auto-advance to the next row).
        if self.seam_table.rowCount():
            self.seam_table.setCurrentCell(
                min(max(current, 0), self.seam_table.rowCount() - 1),
                self.COL_EDGE)
            self.seam_table.setFocus()

        self.sync_container()

    def sync_container(self):
        """Push the derived state into the WorkflowGuide container so the
        property editor shows the same numbers the panel does. The
        container's own execute() does the deriving; nothing is set here."""
        if self.guide is not None and self.guide.Document is not None:
            self.guide.recompute()

    # ---- seam table access ----------------------------------------------

    def seam_row_index(self, edge):
        """Row index of `edge`'s seam, or -1 when it is not a seam."""
        for row, entry in enumerate(self._rows):
            if entry["edge"] is edge:
                return row
        return -1

    def row_texts(self, row):
        """The three cell strings of `row` (for tests / assertions)."""
        return [self.seam_table.item(row, col).text()
                for col in range(len(self.COLUMNS))]

    def status_text(self):
        return self.status_lbl.text()

    def hint_text(self):
        return self.hint_lbl.text()

    def progress_text(self):
        return self.progress_lbl.text()

    # ---- actions ---------------------------------------------------------

    def _on_row_clicked(self, row, _col):
        self.activate_seam_row(row)

    def activate_seam_row(self, row):
        """The seam-row action -- the single call path behind a row click.
        Runs the #44 resolver on that seam's edge, immediately: no
        confirmation dialog, no auto-advance to the next row."""
        if row < 0 or row >= len(self._rows):
            return None
        return self.blend_seam(self._rows[row]["edge"])

    def blend_seam(self, edge):
        """Delegate the whole blend contract to the #44 resolver. The
        panel NEVER re-implements adjacency, idempotency or the refusal
        rules, and NEVER re-words their messages: it captures what the
        resolver printed and shows that on the status line."""
        doc = self.doc if self.doc is not None else FreeCAD.ActiveDocument
        known = {o.Name for o in doc.Objects}
        with _ConsoleTap() as tap:
            from SilkWorkflowOps import create_blend_by_edge
            blend = create_blend_by_edge(edge)

        if blend is None:
            # Refusal: the resolver already printed the reason (console
            # stays canonical). Show its own words, not a paraphrase.
            self.status_lbl.setText(
                tap.errors[-1].strip() if tap.errors
                else "refused: no blend created on %s" % edge.Name)
        elif blend.Name in known:
            # Idempotent no-op: the resolver returned the EXISTING blend
            # and already said so. Don't double-report it as a creation.
            self.status_lbl.setText(
                tap.messages[-1].strip() if tap.messages
                else "no blend created on %s" % edge.Name)
        else:
            # A new blend: the resolver is silent on creation, so the
            # panel names it (blend + edge) and says so on the console
            # too, matching the Silk_CreateBlend wording.
            self.status_lbl.setText("%s created across %s"
                                    % (blend.Name, edge.Name))
            FreeCAD.Console.PrintMessage(
                "%s created across %s\n" % (blend.Name, edge.Name))

        self.refresh()
        return blend

    def run_create_edge(self):
        """Convenience only: run the existing Silk_CreateEdge command.
        It reads the live selection itself; this adds nothing."""
        Gui.runCommand("Silk_CreateEdge", 0)

    def run_create_patch(self):
        """Convenience only: run the existing Silk_CreatePatch command."""
        Gui.runCommand("Silk_CreatePatch", 0)


def status_text(entry):
    """The display string for one seam_inventory entry's status.

    `blendable` / `blended by <Blend.Name>` / `blocked` -- the entry's own
    words, with the blend named so the progress is legible."""
    if entry["status"] == "blended" and entry["blend"] is not None:
        return "blended by %s" % entry["blend"].Name
    return entry["status"]


# ---- container binding + command -------------------------------------------

def find_guide(doc=None):
    """The document's WorkflowGuide container, or None if it has none."""
    doc = doc if doc is not None else FreeCAD.ActiveDocument
    if doc is None:
        return None
    for o in doc.Objects:
        if getattr(o, "object_type", None) == GUIDE_TYPE:
            return o
    return None


def bind_guide(doc=None):
    """Return the document's guide container, creating it if absent.
    Idempotent: opening/reopening the panel never duplicates it."""
    doc = doc if doc is not None else FreeCAD.ActiveDocument
    guide = find_guide(doc)
    if guide is None:
        guide = create_guide(doc=doc)
    return guide


def current_panel():
    """The panel currently open (None when none is)."""
    return _open_panel


def open_guide_panel(doc=None):
    """Bind the container, build the panel and show it. Returns the panel.

    Any task dialog already showing is closed first. FreeCAD allows
    exactly ONE task dialog and raises `Active task dialog found` on a
    second one, so re-activating the command has to make room.

    The close is driven off `Gui.Control.activeDialog()` rather than only
    off our own `_open_panel` bookkeeping, because the two can disagree:
    a module reload (the RPC test runner deletes every `Silk*` module
    between runs) resets `_open_panel` to None while the previous panel's
    dialog is still on screen. Trusting the bookkeeping alone then raises
    instead of reopening. Our own panel is closed through its own
    `close_panel` so its selection observer is unsubscribed first."""
    global _open_panel
    doc = doc if doc is not None else FreeCAD.ActiveDocument
    if doc is None:
        return None
    if _open_panel is not None:
        _open_panel.close_panel()
    elif Gui.Control.activeDialog():
        Gui.Control.closeDialog()
    guide = bind_guide(doc)
    panel = GuideTaskPanel(guide, doc)
    _open_panel = panel
    Gui.Control.showDialog(panel)
    try:
        panel.setDocumentName(doc.Name)
        panel.setAutoCloseOnDeletedDocument(True)
    except Exception:
        pass
    panel.open()
    return panel


class CreateGuide:
    """GUI command `Silk_Guide` -- open the workflow guide task panel.

    The only thing it does is bind the #47 container (creating it when the
    document has none) and show the panel. Beyond that single container
    object, Activated changes nothing in the document."""

    def GetResources(self):
        return {'Pixmap': iconPath, 'MenuText': 'Silk Guide',
                'ToolTip': 'Open the Silk workflow guide: next step, seam '
                           'table and one-click blending.'}

    def Activated(self):
        if FreeCAD.ActiveDocument is None:
            FreeCAD.Console.PrintError(
                "Silk: the guide needs an open document\n")
            return
        open_guide_panel(FreeCAD.ActiveDocument)

    def IsActive(self):
        return Gui is not None


Gui.addCommand("Silk_Guide", CreateGuide())
