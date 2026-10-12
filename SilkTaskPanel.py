#    This file is part of Silk
#    (c) 2025
#
#    NURBS Surface modeling tools focused on low degree and seam continuity (FreeCAD Workbench)
#
#    Silk task panel -- the `Silk_Guide` command + native task panel
#    (ticket #62; supersedes #48's SilkGuidePanel.py and fixes #51).
#
#    HOST. `Gui.Control.showDialog` builds its C++ TaskDialog around a
#    PyObject adapter and looks up `.ui` or `.form` BY NAME. A bare
#    QWidget silently no-ops (that was #51: the #48 panel was one
#    attribute away from working). `SilkTaskDialog` is the duck-typed
#    adapter: handing `showDialog` one of THESE lands the widget in
#    FreeCAD's real Tasks panel, with native chrome, native standard
#    buttons, and `panel.setWindowTitle(...)` as the TaskBox header.
#
#    ORCHESTRATION + DISPLAY ONLY, one way:
#      * no construction logic  -- every create goes through the ops
#        layer (create_edge / create_patch / create_blend_by_edge);
#      * no geometry            -- nothing here builds or touches a shape;
#      * no production coupling -- SilkEdge / SilkPatch / SilkBlend /
#        SilkWorkflowOps / SilkChecks / SilkGuide do not import this
#        module and know nothing about it (settled #16 Q16b). Refresh
#        is PANEL-SIDE: a selection-change observer plus a refresh after
#        each of our own actions, and nothing else in the workbench is
#        subscribed.
#
#    Three collect-then-confirm stages in a QToolBox accordion (Edge /
#    Patch / Blend), one open at a time. `QToolBox` has focusPolicy 0,
#    so the panel never steals focus from the 3D view -- which is why
#    `keyPressEvent` never fires and confirm is a QShortcut with
#    Qt.ApplicationShortcut registered for BOTH Qt.Key_Return and
#    Qt.Key_Enter (the keypad Enter does not fire otherwise).
#
#    One confirm = one document transaction = one undo step, even for a
#    multi-seam blend. Wrong-type clicks are SILENTLY IGNORED. A stale
#    collected entry is REFUSED LOUDLY, naming the item -- never
#    silently dropped (that would turn a quad patch into a pointed one).
#
#    A Patch confirm succeeds for ANY order the edges were clicked in
#    (#66): the fill derives the boundary cycle from the edges' own
#    endpoints, so this panel never reorders anything itself. What it does
#    police is the selection that genuinely cannot become a patch -- one
#    that does not close a loop. That is refused LOUDLY, before anything
#    is constructed, naming the offending edges; the collection survives
#    so the user can fix it, and nothing is left behind. Success is
#    reported only for a patch that actually built poles (#66: the old
#    "Patch created" on an invisible ghost).
#
#    Every seam row, BLENDED ones included, carries its band's split
#    editor: the seam's band is the blend's cross-section, so the width
#    stays tunable once the blend exists (#62 follow-up). Collectability
#    is separate and unchanged -- a blended row still refuses a blend.
#
#    The panel is built for a NARROW dock: no width floor, every label
#    wrapping, the collection lists and the seam table capped to their
#    content with an empty one showing a greyed placeholder, and the next
#    step's guidance below the accordion and in the tooltips rather than
#    in a block above it (#62 follow-up).
#
#    #47's `compute_guide_state` stays the source of truth for the
#    next-step hint and the seam table; its WorkflowGuide container
#    (#47/#19's persisting half) and #48's panel are gone.

import FreeCAD
from FreeCAD import Gui

try:
    from PySide import QtWidgets, QtCore, QtGui
except ImportError:  # pragma: no cover - console-only FreeCAD
    QtWidgets = None
    QtCore = None
    QtGui = None

from SilkGuide import compute_guide_state
from SilkWorkflowOps import create_edge, create_patch, create_blend_by_edge
from SilkMachinery import patch_side, build_intervals, \
    corner_cells, split_at_end, loop_order

import os, Silk_dummy
path_Silk = os.path.dirname(Silk_dummy.__file__)
path_Silk_icons = os.path.join(path_Silk, "Resources", "Icons")
iconPath = path_Silk_icons + "/Silk.svg"


# ---- section indices (the QToolBox pages, in order) -----------------------

SECTION_EDGE, SECTION_PATCH, SECTION_BLEND = 0, 1, 2
SECTION_TITLES = ("Edge", "Patch", "Blend")

# Per-stage collection bounds. Edge: 1 or 2 sketches (1 -> 3L, 2 -> 2N).
# Patch: 3 or 4 edges (3 -> pointed, 4 -> quad). Blend: 1..N seams.
EDGE_MIN, EDGE_MAX = 1, 2
PATCH_MIN, PATCH_MAX = 3, 4
BLEND_MIN = 1

# The default band width SilkBlend.ensure_band_split writes when the
# patch's end of that axis carries no split at all (ss 0 -> 0.1,
# ss 1 -> 0.9). Shown for an UNSET split so the row is editable before
# the blend writes anything.
DEFAULT_BAND = (0.1, 0.9)

# How tall a collection list may grow. The stages collect at most 2
# sketches and 4 edges, so a taller box is pure empty chrome: #62's
# uncapped QListWidget ate ~40% of the panel for zero rows, which is
# what made the panel read as EMPTY rather than ready.
LIST_MAX_ROWS = 4

# How tall the seam table may grow before it scrolls. A document has a
# handful of seams; a table filling the whole panel hides that.
TABLE_MAX_ROWS = 6

# Placeholder shown in an empty collection list, so "nothing yet" reads
# as deliberate rather than as a list that failed to load.
PLACEHOLDERS = {
    SECTION_EDGE: "nothing collected -- click a sketch in the 3D view",
    SECTION_PATCH: "nothing collected -- click edges in the 3D view",
}

# The static guidance, kept as the panel's / sections' tooltip and in the
# adapter's needsFullSpace() explanation. It used to be a permanent
# top-of-panel block duplicating the section instruction directly below.
HINT_TOOLTIP = (
    "Edge: click 1 or 2 sketches (1 reads 3L, 2 read 2N).\n"
    "Patch: click 3 or 4 edges (4 read a quad fill, 3 the pointed one).\n"
    "Blend: click a seam to collect it, click again to remove it; Enter or "
    "OK blends every collected seam in one undo step. A blended seam's band "
    "split stays editable -- it is the width that blend uses.")


# ---- the open panel --------------------------------------------------------

# The panel currently open (None when none is). Survives only within one
# module instance: FreeCAD allows exactly ONE task dialog, and a
# re-imported module has no business claiming a dialog it did not open.
_open_panel = None


def current_panel():
    """The panel currently open, or None."""
    return _open_panel


# ---- console tap -----------------------------------------------------------
# The resolver and the oracle report through the console, which stays
# canonical (every message is forwarded to the real console exactly as
# printed). The tap only ALSO records, so the status line can show the
# resolver's own words instead of a paraphrase.

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


# ---- the duck-typed FreeCAD task-dialog adapter ---------------------------

class SilkTaskDialog:
    """Adapter that makes `Gui.Control.showDialog` build a REAL native
    task panel around `form` (#51).

    FreeCAD's C++ `TaskDialogPython` resolves the panel's content by
    looking up `.ui` or `.form` on this object by name and wrapping the
    widget in a `TaskBox` (its `windowTitle()` becomes the box header).
    Passing a bare QWidget instead leaves the panel EMPTY and silent --
    the #48 failure. Everything below is FreeCAD asking the adapter
    questions it is allowed to leave unanswered; each answer here is
    either the truthful default or the honest one for a wizard that
    alters the document, the view and the selection while it is open.
    """

    def __init__(self, form):
        # FreeCAD NULLS this attribute when it tears the dialog down, so
        # never keep a second reference expecting it to stay valid.
        self.form = form

    def open(self):
        """Called by Gui.Control once the panel is on screen."""
        form = self.form
        if form is not None:
            form.panel_opened()

    def accept(self):
        """OK pressed (or Enter). Return True to keep the panel OPEN --
        applying clears the collection but the section stays put, with no
        auto-advance."""
        form = self.form
        if form is not None:
            form.panel_confirm()
        return False

    def reject(self):
        """Cancel / Esc: close. Collections are simply dropped."""
        form = self.form
        if form is not None:
            form.close_panel()
        return True

    def clicked(self, button):
        # `button` is the QDialogButtonBox.StandardButton. OK already
        # arrived through accept(); Cancel through reject(). Nothing else
        # is offered, so there is nothing left to route.
        return

    def modifyStandardButtons(self, box):
        """FreeCAD hands us the native button box: keep OK's reference so
        the panel can enable/disable it as the open section's collection
        becomes valid or invalid."""
        if QtWidgets is None:
            return
        form = self.form
        if form is None:
            return
        ok = box.button(QtWidgets.QDialogButtonBox.Ok)
        if ok is not None:
            form.set_ok_button(ok)
            form.sync_ok_enabled()

    def getStandardButtons(self):
        return (QtWidgets.QDialogButtonBox.Ok
                | QtWidgets.QDialogButtonBox.Cancel)

    def needsFullSpace(self):
        # No trailing stretch of our own: the toolbox fills the Tasks
        # panel, and each page's OWN trailing stretch keeps a capped list
        # or table from stretching to fill (which is what made #62's panel
        # read as empty). The guidance that used to sit in a group box
        # above the accordion lives here and on the panel's / sections'
        # tooltips -- the primary space belongs to the three sections.
        return True

    def isAllowedAlterDocument(self):
        return True

    def isAllowedAlterView(self):
        return True

    def isAllowedAlterSelection(self):
        return True


# ---- selection-change hook (settled Q16b) ----------------------------------
# FreeCAD 1.1's selection observer callback names. Selection *changes*
# only -- preselection fires continuously while the mouse moves over the
# 3D view and collecting on it would be pure noise.

class _SelectionHook:
    """Forwards selection CHANGES to the panel. Installed when the panel
    opens, removed when it closes -- nothing else in the workbench is
    subscribed."""

    def __init__(self, panel):
        self.panel = panel

    def _added(self, doc_name, obj_name, *_rest):
        # A single click in the 3D view lands here. The panel decides
        # whether the object is something the OPEN section collects;
        # anything else is silently ignored.
        self.panel.on_selection_add(doc_name, obj_name)

    def addSelection(self, docName, objName, subName, pos):
        self._added(docName, objName, subName, pos)

    def removeSelection(self, docName, objName, subName):
        self.panel.refresh()

    def setSelection(self, docName):
        self.panel.refresh()

    def clearSelection(self, docName):
        self.panel.refresh()


# ---- document observer (close on document switch) --------------------------

class _DocumentHook:
    """Closes the panel when the active document changes or the panel's
    own document is deleted.

    Collections belong to a document the user is no longer looking at,
    so the honest thing is to drop them with the panel. The real slot
    names are FreeCAD 1.1's (`slotActivateDocument`,
    `slotDeletedDocument`); the older `slotDocumentActivated` spelling
    is a no-op that would silently never fire.
    """

    def __init__(self, panel):
        self.panel = panel

    def slotActivateDocument(self, doc):
        self.panel.on_document_activated(doc)

    def slotDeletedDocument(self, doc):
        self.panel.on_document_activated(doc)


# ---- one collected entry ----------------------------------------------------

class _Collected:
    """One collected input: the object plus its name captured AT
    COLLECTION TIME.

    The name is the point. A collected object can be deleted behind the
    panel's back, and FreeCAD's deleted DocumentObject proxy raises on
    every attribute access -- so a refusal that has to NAME the stale item
    could not read that name off the corpse. Capturing it early is what
    lets the refusal say "cannot apply -- Edge3 it is no longer in the
    document" instead of dying on the way to the message.
    """

    __slots__ = ("obj", "name")

    def __init__(self, obj):
        self.obj = obj
        self.name = obj.Name

    def __repr__(self):  # pragma: no cover - debugging aid
        return "<collected %s>" % self.name


# ---- the panel -------------------------------------------------------------

class SilkTaskPanel(QtWidgets.QWidget if QtWidgets else object):
    """The `Silk_Guide` task panel: three collect-then-confirm stages in a
    QToolBox accordion.

    Sections, in order:

      Edge   -- collect 1 or 2 SKETCHES. The list shows what is
                collected; the counter reads "N/2" and the mode line names
                the resulting construction (1 -> 3L, 2 -> 2N). OK lights
                up at 1 or 2, never above 2.

      Patch  -- collect 3 or 4 EDGES. "N/4" plus the resulting fill:
                4 -> quad, 3 -> pointed. OK lights up at 3 or 4.

      Blend  -- ONE merged table of every seam in the document, each row
                carrying its own status (blendable / blended by X /
                blocked). Clicking a row collects that seam; a collected
                row is highlighted and clicking it again removes it.
                EVERY row -- blended ones included -- also exposes the
                band's split value, edited straight onto the patch's
                USplits/VSplits: since #64 the blend READS that split, so
                a width set here is the width the blend uses, whether the
                blend already exists or not.

    Confirm (Enter or the native OK button) is one document transaction:
    one undo step, even when several seams blend at once. After applying,
    the collection clears, the section stays open, and nothing advances
    by itself.
    """

    COL_EDGE, COL_PATCHES, COL_STATUS, COL_SPLIT = 0, 1, 2, 3
    COLUMNS = ("Seam", "Patches", "Status", "Band split")

    def __init__(self, doc):
        super().__init__()
        self.doc = doc
        self._ok_button = None
        self._hook = _SelectionHook(self)
        self._hook_installed = False
        self._doc_hook = _DocumentHook(self)
        self._doc_hook_installed = False
        self._shortcuts = []
        # one list of collected objects per section
        self._collected = {SECTION_EDGE: [], SECTION_PATCH: [],
                           SECTION_BLEND: []}
        # seam edge Name -> (QDoubleSpinBox, patch_a, patch_b) for the
        # band-split editors currently mounted in the table.
        self._split_widgets = {}

        self.setWindowTitle("Silk Workflow")
        # The Tasks dock is narrow, and #62 shipped a 320px floor that
        # made the PANEL wider than a narrower dock -- the dock then
        # clipped the right-hand column (and showed its own horizontal
        # scrollbar). No floor: the panel's true minimum is its layout's,
        # and every label in it wraps, so it shrinks with the dock.
        self.setMinimumWidth(0)

        form = QtWidgets.QVBoxLayout(self)
        form.setContentsMargins(4, 4, 4, 4)
        form.setSpacing(4)

        # --- the three-stage accordion -------------------------------
        self.toolbox = QtWidgets.QToolBox(self)
        # focusPolicy 0 (NoFocus): the 3D view keeps focus, which is why
        # confirm cannot be a keyPressEvent.
        self.toolbox.setFocusPolicy(QtCore.Qt.NoFocus)
        self.toolbox.currentChanged.connect(self._on_section_changed)
        form.addWidget(self.toolbox)

        self._build_edge_page()
        self._build_patch_page()
        self._build_blend_page()

        # --- the footer: guidance OUT of the prime top-of-panel space --
        # #62 put the next-step hint in a QGroupBox above the accordion,
        # where it restated the section instruction sitting directly
        # underneath and ate the width the dock actually needed. It now
        # lives BELOW the accordion as one muted line -- guidance stays
        # visible and wrapping -- and is also the panel's and each
        # section's tooltip, so the words are one hover away without
        # costing a row of the reading order.
        self.hint_lbl = QtWidgets.QLabel("")
        self.hint_lbl.setWordWrap(True)
        f = self.hint_lbl.font()
        f.setItalic(True)
        self.hint_lbl.setFont(f)
        self.hint_lbl.setEnabled(False)      # muted: not an input
        self.hint_lbl.setToolTip(HINT_TOOLTIP)
        form.addWidget(self.hint_lbl)
        self.setToolTip(HINT_TOOLTIP)
        self.toolbox.setToolTip(HINT_TOOLTIP)

        # --- the status line: the last action's outcome --------------
        self.status_lbl = QtWidgets.QLabel("")
        self.status_lbl.setWordWrap(True)
        self.status_lbl.setMinimumWidth(0)
        form.addWidget(self.status_lbl)

        self._install_shortcuts()

    # ---- construction of the three pages ---------------------------

    @staticmethod
    def _instruction(text):
        """A wrapping instruction label. Wrapping matters: a Tasks dock is
        narrow, and a non-wrapping label's sizeHint becomes the page's
        minimum width, which clips the whole panel."""
        lbl = QtWidgets.QLabel(text)
        lbl.setWordWrap(True)
        lbl.setToolTip(HINT_TOOLTIP)
        return lbl

    @staticmethod
    def _fit_list(widget, n_rows):
        """Cap a collection list at LIST_MAX_ROWS rows' worth of height.

        An uncapped list expands to fill the page, so on an empty
        collection a QListWidget with nothing in it dominated the panel --
        the layout read as BROKEN rather than ready (#62). The box now
        grows with its content up to the cap and the page's trailing
        stretch takes the slack."""
        row_h = widget.sizeHintForRow(0) or (widget.fontMetrics().height() + 8)
        frame = 2 * widget.frameWidth()
        wanted = frame + row_h * max(1, min(n_rows, LIST_MAX_ROWS))
        widget.setMaximumHeight(wanted)
        widget.setMinimumHeight(min(wanted, frame + row_h))

    @staticmethod
    def _placeholder_item(text):
        """The greyed 'nothing yet' row of an empty collection list. Not
        selectable and not a collection entry: it exists so an empty box
        reads as deliberate."""
        item = QtWidgets.QListWidgetItem(text)
        item.setFlags(QtCore.Qt.NoItemFlags)
        item.setForeground(QtGui.QBrush(QtGui.QColor(0x90, 0x90, 0x90)))
        item.setToolTip("This list fills as you click in the 3D view.")
        return item

    @staticmethod
    def _collection_list(page):
        """A collection list that never scrolls sideways.

        A horizontal scrollbar across a narrow dock is exactly the
        overflow #62 shipped; text elides instead (the collection entry
        is still named in full in the tooltip and by _item_text)."""
        widget = QtWidgets.QListWidget(page)
        widget.setSelectionMode(
            QtWidgets.QAbstractItemView.SingleSelection)
        widget.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        widget.setTextElideMode(QtCore.Qt.ElideRight)
        widget.setWordWrap(False)
        return widget

    def _build_edge_page(self):
        page = QtWidgets.QWidget()
        lay = QtWidgets.QVBoxLayout(page)
        lay.addWidget(self._instruction(
            "Click 1 or 2 sketches in the 3D view. 1 sketch reads 3L, "
            "2 sketches read 2N."))
        self.edge_list = self._collection_list(page)
        self.edge_list.itemSelectionChanged.connect(self._on_collected_changed)
        lay.addWidget(self.edge_list)
        row = QtWidgets.QHBoxLayout()
        self.edge_count_lbl = QtWidgets.QLabel("0/2")
        self.edge_mode_lbl = QtWidgets.QLabel("")
        row.addWidget(self.edge_count_lbl)
        row.addWidget(self.edge_mode_lbl)
        row.addStretch(1)
        self.edge_remove_btn = QtWidgets.QPushButton("Remove")
        self.edge_remove_btn.setToolTip(
            "Remove the selected sketch from this collection")
        self.edge_remove_btn.clicked.connect(self._remove_selected)
        row.addWidget(self.edge_remove_btn)
        lay.addLayout(row)
        # The slack belongs to the PAGE, not to an empty list box.
        lay.addStretch(1)
        self.toolbox.addItem(page, SECTION_TITLES[SECTION_EDGE])

    def _build_patch_page(self):
        page = QtWidgets.QWidget()
        lay = QtWidgets.QVBoxLayout(page)
        lay.addWidget(self._instruction(
            "Click 3 or 4 edges in the 3D view. 4 edges read a quad "
            "patch, 3 edges the pointed fill."))
        self.patch_list = self._collection_list(page)
        self.patch_list.itemSelectionChanged.connect(
            self._on_collected_changed)
        lay.addWidget(self.patch_list)
        row = QtWidgets.QHBoxLayout()
        self.patch_count_lbl = QtWidgets.QLabel("0/4")
        self.patch_fill_lbl = QtWidgets.QLabel("")
        row.addWidget(self.patch_count_lbl)
        row.addWidget(self.patch_fill_lbl)
        row.addStretch(1)
        self.patch_remove_btn = QtWidgets.QPushButton("Remove")
        self.patch_remove_btn.setToolTip(
            "Remove the selected edge from this collection")
        self.patch_remove_btn.clicked.connect(self._remove_selected)
        row.addWidget(self.patch_remove_btn)
        lay.addLayout(row)
        # The slack belongs to the PAGE, not to an empty list box.
        lay.addStretch(1)
        self.toolbox.addItem(page, SECTION_TITLES[SECTION_PATCH])

    def _build_blend_page(self):
        page = QtWidgets.QWidget()
        lay = QtWidgets.QVBoxLayout(page)
        lay.addWidget(self._instruction(
            "Click a seam to collect it, click it again to remove it. "
            "Enter or OK blends every collected seam in one step."))
        self.blend_progress_lbl = QtWidgets.QLabel("")
        lay.addWidget(self.blend_progress_lbl)
        self.blend_table = QtWidgets.QTableWidget(0, len(self.COLUMNS))
        self.blend_table.setHorizontalHeaderLabels(list(self.COLUMNS))
        self.blend_table.setEditTriggers(
            QtWidgets.QAbstractItemView.NoEditTriggers)
        self.blend_table.setSelectionBehavior(
            QtWidgets.QAbstractItemView.SelectRows)
        self.blend_table.setSelectionMode(
            QtWidgets.QAbstractItemView.SingleSelection)
        self.blend_table.verticalHeader().setVisible(False)
        # Stretch every column: the Tasks dock is narrow, and a
        # content-sized table would force a horizontal scrollbar (or a
        # panel wider than its dock). Text elides visually; item.text()
        # still holds the full string.
        self.blend_table.horizontalHeader().setSectionResizeMode(
            QtWidgets.QHeaderView.Stretch)
        # Belt and braces for the same overrun: the columns stretch, so
        # no section may exceed its share. A minimum section size (or a
        # long unbreakable cell) would otherwise push the table's
        # minimum past the dock and earn the dock a horizontal
        # scrollbar.
        self.blend_table.horizontalHeader().setMinimumSectionSize(16)
        self.blend_table.setHorizontalScrollBarPolicy(
            QtCore.Qt.ScrollBarAlwaysOff)
        self.blend_table.setTextElideMode(QtCore.Qt.ElideRight)
        self.blend_table.cellClicked.connect(self._on_blend_row_clicked)
        lay.addWidget(self.blend_table)
        # Same rule as the collection lists: a one-row table stretched to
        # the full panel height is empty chrome. The page's trailing
        # stretch takes the slack instead.
        lay.addStretch(1)
        self.toolbox.addItem(page, SECTION_TITLES[SECTION_BLEND])

    def _install_shortcuts(self):
        """Confirm via Enter, as a QShortcut with Qt.ApplicationShortcut.

        `keyPressEvent` on the panel NEVER fires: the 3D view holds focus
        essentially always. An ApplicationShortcut is matched before the
        focus widget sees the key, which is what makes Enter work at all.
        BOTH Qt.Key_Return and Qt.Key_Enter are registered -- the keypad
        Enter is a different key code and does not fire otherwise.
        """
        for key in (QtCore.Qt.Key_Return, QtCore.Qt.Key_Enter):
            sc = QtGui.QShortcut(QtGui.QKeySequence(key), self,
                                 self.panel_confirm)
            # setContext explicitly: the constructor overload that takes a
            # callable does NOT carry the context through in PySide6, and a
            # WindowShortcut would die with the panel's window rather than
            # fire wherever the focus is.
            sc.setContext(QtCore.Qt.ApplicationShortcut)
            self._shortcuts.append(sc)

    # ---- panel protocol ---------------------------------------------

    def panel_opened(self):
        """The adapter's open(): install hooks and draw once."""
        self.install_hooks()
        self.refresh()

    def set_ok_button(self, ok):
        self._ok_button = ok

    def sync_ok_enabled(self):
        """OK is enabled exactly when the OPEN section's collection is
        valid for a confirm."""
        if self._ok_button is None:
            return
        try:
            self._ok_button.setEnabled(self.can_confirm())
        except RuntimeError:
            pass  # the button outlived the panel

    def install_hooks(self):
        if not self._hook_installed:
            Gui.Selection.addObserver(self._hook)
            self._hook_installed = True
        if not self._doc_hook_installed:
            FreeCAD.addDocumentObserver(self._doc_hook)
            self._doc_hook_installed = True

    def remove_hooks(self):
        if self._hook_installed:
            try:
                Gui.Selection.removeObserver(self._hook)
            except Exception:
                pass
            self._hook_installed = False
        if self._doc_hook_installed:
            try:
                FreeCAD.removeDocumentObserver(self._doc_hook)
            except Exception:
                pass
            self._doc_hook_installed = False

    def close_panel(self):
        """Unsubscribe and close. The widget is DELETED by FreeCAD (and
        the adapter's `.form` nulled), so a reopen always builds fresh."""
        self.remove_hooks()
        global _open_panel
        if _open_panel is self:
            _open_panel = None
        self._release_focus()
        Gui.Control.closeDialog()

    def _release_focus(self):
        """Move focus out of the panel before closing it: a focus pointer
        into a widget that is about to be deleted dangles."""
        try:
            fw = QtWidgets.QApplication.focusWidget()
            if fw is not None and fw is not self:
                fw.clearFocus()
            self.clearFocus()
            mw = Gui.getMainWindow()
            if mw is not None:
                mw.setFocus()
        except Exception:
            pass

    # ---- lifecycle hooks --------------------------------------------

    def on_document_activated(self, doc):
        """Close on document switch: collections would belong to a
        document the user is no longer looking at."""
        if self.doc is None:
            return
        if doc is not None and doc is self.doc:
            return
        self.close_panel()

    def on_selection_add(self, doc_name, obj_name):
        """One click in the 3D view. Offer the object to the OPEN
        section; a wrong-type click is silently ignored (no dimming, no
        message, no change to anything)."""
        if doc_name != self.doc.Name:
            return
        obj = self.doc.getObject(obj_name)
        if obj is None:
            return
        section = self.open_section()
        if not self.accepts(section, obj):
            return
        items = self._collected[section]
        if any(i.obj is obj for i in items):
            return
        if len(items) >= self.section_limit(section):
            return
        items.append(_Collected(obj))
        self.refresh()

    # ---- sections ----------------------------------------------------

    def open_section(self):
        return self.toolbox.currentIndex()

    def section_limit(self, section):
        return {SECTION_EDGE: EDGE_MAX, SECTION_PATCH: PATCH_MAX,
                SECTION_BLEND: len(self.seam_inventory())}[section]

    def accepts(self, section, obj):
        """What the open section collects. A wrong type is IGNORED, never
        refused -- the panel says nothing at all about it."""
        if section == SECTION_EDGE:
            return self.is_sketch(obj)
        if section == SECTION_PATCH:
            return self.object_type(obj) == "Edge"
        # Blend: an Edge object that is a seam right now. An edge with
        # fewer than two patches is not a seam, and a non-manifold one is
        # not blendable -- both are silently ignored here; the table still
        # SHOWS them with their status, which is where a blocked seam is
        # explained. A seam that is ALREADY BLENDED is refused here too:
        # its blend exists, so collecting it would only ever re-run an
        # idempotent no-op. Its band split is still editable in place --
        # that is the editor's availability, not its collectability.
        if self.object_type(obj) != "Edge":
            return False
        return any(e["edge"] is obj and e["status"] == "blendable"
                   for e in self.seam_inventory())

    @staticmethod
    def object_type(obj):
        return getattr(obj, "object_type", None)

    @staticmethod
    def is_sketch(obj):
        # The ops layer's own notion of an edge input: a sketch. Any
        # object carrying Geometry counts (Sketcher::SketchObject,
        # Sketch, a legacy Part sketch), and an Edge is NOT a sketch even
        # though it has Geometry of its own.
        if SilkTaskPanel.object_type(obj) == "Edge":
            return False
        return obj.TypeId.endswith("Sketch") or obj.TypeId.endswith(
            "SketchObject") or hasattr(obj, "Geometry")

    # ---- collection access -------------------------------------------

    def collected(self, section=None):
        """The collected objects of a section (the open one by default)."""
        return [i.obj for i in
                self._collected[self.open_section()
                                if section is None else section]]

    def _on_section_changed(self, _index):
        self.sync_ok_enabled()

    def _on_collected_changed(self):
        self.sync_ok_enabled()

    def _remove_selected(self):
        section = self.open_section()
        widget = (self.edge_list if section == SECTION_EDGE
                  else self.patch_list)
        row = widget.currentRow()
        if row < 0 or row >= len(self._collected[section]):
            return
        del self._collected[section][row]
        self.refresh()

    def _on_blend_row_clicked(self, row, _col):
        """A seam row click TOGGLES collection: a blendable row collects,
        an already-collected row removes, and a blended/blocked row does
        nothing at all (its status is the explanation)."""
        entries = self.seam_inventory()
        if row < 0 or row >= len(entries):
            return
        edge = entries[row]["edge"]
        if edge is None or getattr(edge.Document, "Name", None) != self.doc.Name:
            return
        items = self._collected[SECTION_BLEND]
        for i, entry_item in enumerate(items):
            if entry_item.obj is edge:
                del items[i]
                self.refresh()
                return
        if not self.accepts(SECTION_BLEND, edge):
            return
        items.append(_Collected(edge))
        self.refresh()

    # ---- seams --------------------------------------------------------

    def seam_inventory(self):
        from SilkWorkflowOps import seam_inventory
        if self.doc is None or self.doc.Name not in FreeCAD.listDocuments():
            return []
        return seam_inventory(self.doc)

    # ---- refresh (panel-side only, settled Q16b) -----------------------

    def refresh(self):
        """Re-derive EVERYTHING from the document. The one refresh path:
        nothing here reads a stored stage."""
        if self.doc is None or self.doc.Name not in FreeCAD.listDocuments():
            return
        state = compute_guide_state(self.doc)
        self.hint_lbl.setText(state["hint"])
        self._render_lists()
        self._render_table(state["seams"], state["seam_counts"])
        self.sync_ok_enabled()

    def _render_lists(self):
        for section, widget in ((SECTION_EDGE, self.edge_list),
                                (SECTION_PATCH, self.patch_list)):
            items = self._collected[section]
            widget.clear()
            if items:
                for item in items:
                    widget.addItem(self._item_text(item))
            else:
                # An empty box with nothing in it reads as a failure to
                # load. One greyed, unselectable line reads as "not yet".
                widget.addItem(self._placeholder_item(
                    PLACEHOLDERS[section]))
            self._fit_list(widget, len(items))

        edges = self._collected[SECTION_EDGE]
        self.edge_count_lbl.setText("%d/%d" % (len(edges), EDGE_MAX))
        if len(edges) == 2:
            self.edge_mode_lbl.setText("2N (two sketches)")
        elif len(edges) == 1:
            self.edge_mode_lbl.setText("3L (one sketch)")
        else:
            self.edge_mode_lbl.setText("")

        peds = self._collected[SECTION_PATCH]
        self.patch_count_lbl.setText("%d/%d" % (len(peds), PATCH_MAX))
        if len(peds) == 4:
            self.patch_fill_lbl.setText("quad fill")
        elif len(peds) == 3:
            self.patch_fill_lbl.setText("pointed fill")
        else:
            self.patch_fill_lbl.setText("")

    @staticmethod
    def _item_text(item):
        """The list row for a collected entry. A deleted object still
        shows under the name it had when it was collected -- that is the
        very item a later refusal has to name."""
        try:
            label = getattr(item.obj, "Label", None)
            if label and label != item.name:
                return "%s  (%s)" % (label, item.name)
        except RuntimeError:
            return "%s  (deleted)" % item.name
        return item.name

    def _render_table(self, seams, counts):
        collected = self._collected[SECTION_BLEND]
        self.blend_progress_lbl.setText(
            "%d of %d seams blended" % (counts["blended"], counts["total"]))
        self.blend_table.setRowCount(len(seams))
        # Drop every mounted split editor first; the rows below re-mount
        # the ones that are still needed.
        self._split_widgets = {}
        for row, entry in enumerate(seams):
            texts = (entry["edge"].Name,
                     "%s <-> %s" % (entry["patch_a"].Name,
                                    entry["patch_b"].Name),
                     status_text(entry))
            for col, text in enumerate(texts):
                item = self.blend_table.item(row, col)
                if item is None:
                    item = QtWidgets.QTableWidgetItem(text)
                    self.blend_table.setItem(row, col, item)
                else:
                    item.setText(text)
            taken = any(i.obj is entry["edge"] for i in collected)
            for col in range(len(self.COLUMNS)):
                item = self.blend_table.item(row, col)
                if item is not None:
                    font = item.font()
                    font.setBold(taken)
                    item.setFont(font)
                    if taken:
                        item.setBackground(QtGui.QBrush(
                            QtGui.QColor(0xD8, 0xF0, 0xD8)))
                    else:
                        item.setBackground(QtGui.QBrush())
            self.blend_table.setCellWidget(row, self.COL_SPLIT, None)
            # EVERY seam row carries its band-split editor, blended or
            # not. #62 mounted it only on COLLECTED rows, and a collected
            # row is by definition blendable, so a seam that had already
            # been blended had no editor at all -- the width that blend
            # is actually built from was then only reachable through the
            # property editor, which is the thing #62 exists to replace.
            # Collectability is a separate question and stays where it
            # is (`accepts`), so a blended row still refuses blend
            # CREATION -- only the editor's availability changed.
            if entry["status"] in ("blendable", "blended"):
                self._mount_split_editor(row, entry)
        self._fit_table(len(seams))

    def _fit_table(self, n_rows):
        """Cap the seam table at TABLE_MAX_ROWS rows; it scrolls beyond."""
        vh = self.blend_table.verticalHeader()
        row_h = vh.sectionSize(0) if self.blend_table.rowCount() else 0
        row_h = row_h or (self.blend_table.fontMetrics().height() + 12)
        head_h = self.blend_table.horizontalHeader().height() + 4
        frame = 2 * self.blend_table.frameWidth()
        wanted = frame + head_h + row_h * max(
            1, min(n_rows, TABLE_MAX_ROWS))
        self.blend_table.setMaximumHeight(wanted)

    def _mount_split_editor(self, row, entry):
        """Expose the band's split on EVERY seam row: the value comes
        straight off the patch's USplits/VSplits and writing it goes
        straight back onto that property, which is exactly what #64's
        blend reads.

        Blended rows included (#62 follow-up). The seam's band IS the
        blend's cross-section, so a width set here re-drives an existing
        blend exactly as it would size a new one's -- which is the whole
        reason to be able to edit it after the blend exists. Refusing to
        COLLECT an already-blended row is untouched (`accepts`)."""
        read = read_band_split(entry)
        if read is None:
            return
        pa_prop, pa_ss, pa_val, pb_prop, pb_ss, pb_val = read
        spin = QtWidgets.QDoubleSpinBox()
        spin.setDecimals(3)
        spin.setSingleStep(0.05)
        spin.setRange(0.001, 0.999)     # constrained 0 < u < 1
        spin.setValue(pa_val)
        spin.setToolTip(
            "Band split written on %s.%s (side %d) and %s.%s (side %d).\n"
            "The blend reads these splits -- this is the band width.%s"
            % (pa_prop and entry["patch_a"].Name, pa_prop, pa_ss,
               entry["patch_b"].Name, pb_prop, pb_ss,
               "\nThis seam is blended: editing the width re-drives that "
               "blend." if entry["status"] == "blended" else ""))
        spin.editingFinished.connect(
            lambda e=entry: self._on_split_edited(e))
        self.blend_table.setCellWidget(row, self.COL_SPLIT, spin)
        self._split_widgets[entry["edge"].Name] = spin

    def _on_split_edited(self, entry):
        """One split edit, as its own transaction, written straight onto
        both patches.

        A width that would NOT leave exactly one band cell is REFUSED
        before the write, naming the patch and the values: that write is
        what the blend's cross-section is built from, so committing an
        unusable width would silently break a blend the user can already
        see. A refused edit puts the spin back where it was, so the panel
        and the property never disagree."""
        spin = self._split_widgets.get(entry["edge"].Name)
        if spin is None:
            return False
        value = spin.value()
        problem = band_cell_problem(entry, value)
        if problem:
            before = read_band_split(entry)
            if before is not None:
                spin.setValue(before[2])
            self._refuse("Silk: cannot set the band width on %s -- %s. The "
                         "split was left as it was."
                         % (entry["edge"].Name, problem))
            return False
        if not write_band_split(entry, value):
            return False
        read = read_band_split(entry)
        self.status_lbl.setText(
            "band width %g set on %s.%s and %s.%s%s"
            % (value, entry["patch_a"].Name, read[0],
               entry["patch_b"].Name, read[3],
               " -- the existing blend followed it"
               if entry["status"] == "blended" else ""))
        return True

    # ---- validity ------------------------------------------------------

    def can_confirm(self):
        section = self.open_section()
        n = len(self._collected[section])
        if section == SECTION_EDGE:
            return EDGE_MIN <= n <= EDGE_MAX
        if section == SECTION_PATCH:
            return PATCH_MIN <= n <= PATCH_MAX
        return n >= BLEND_MIN

    def ok_enabled(self):
        """The native OK button's enabled state -- OK is enabled exactly
        when the OPEN section's collection can be confirmed."""
        if self._ok_button is None:
            return None
        try:
            return self._ok_button.isEnabled()
        except RuntimeError:
            return None

    # ---- staleness ------------------------------------------------------

    def stale_items(self):
        """Collected entries that are no longer usable, as
        (object, reason) pairs -- named so a refusal can name them.

        Never silently drop one: dropping an edge from a Patch would turn
        a quad fill into the pointed fill behind the user's back.
        """
        section = self.open_section()
        bad = []
        for item in self._collected[section]:
            obj = item.obj
            if self.doc is None or self.doc.Name not in FreeCAD.listDocuments():
                bad.append((item, "the document is closed"))
                continue
            if self.doc.getObject(item.name) is not obj:
                bad.append((item, "it is no longer in the document"))
                continue
            if section == SECTION_EDGE and not self.is_sketch(obj):
                bad.append((item, "it is no longer a sketch"))
            elif section == SECTION_PATCH and self.object_type(obj) != "Edge":
                bad.append((item, "it is no longer an Edge"))
            elif section == SECTION_BLEND:
                why = self._seam_stale(obj)
                if why:
                    bad.append((item, why))
        return bad

    def _seam_stale(self, edge):
        entry = next((e for e in self.seam_inventory()
                      if e["edge"] is edge), None)
        if entry is None:
            return "it is no longer a seam (fewer than two patches use it)"
        if entry["status"] == "blocked":
            return ("it is blocked (three or more patches reference it, "
                    "which needs the deferred corner fill)")
        if entry["status"] == "blended":
            return "it is already blended by %s" % entry["blend"].Name
        return None

    # ---- band-split validation ------------------------------------------

    def invalid_bands(self):
        """Collected blend rows whose chosen width would NOT leave
        exactly one band cell, as (edge, message) pairs naming the patch
        and the values. Multi-cell bands are still unsupported, so this
        refuses clearly instead of creating something wrong."""
        bad = []
        for item in self._collected[SECTION_BLEND]:
            edge = item.obj
            entry = next((e for e in self.seam_inventory()
                          if e["edge"] is edge), None)
            if entry is None or entry["status"] != "blendable":
                continue
            spin = self._split_widgets.get(item.name)
            value = spin.value() if spin is not None else None
            problem = band_cell_problem(entry, value)
            if problem:
                bad.append((item, problem))
        return bad

    # ---- confirm ---------------------------------------------------------

    def panel_confirm(self):
        """The ONE confirm path, whatever fired it (Enter or OK)."""
        if not self.can_confirm():
            return False
        section = self.open_section()
        if section == SECTION_EDGE:
            return self.confirm_edge()
        if section == SECTION_PATCH:
            return self.confirm_patch()
        return self.confirm_blend()

    def confirm_edge(self):
        sketches = self.collected(SECTION_EDGE)
        stale = self.stale_items()
        if stale:
            return self._refuse_stale(stale)
        doc = self.doc
        doc.openTransaction("Silk edge")
        try:
            with _ConsoleTap() as tap:
                edge = create_edge(sketches)
        finally:
            doc.commitTransaction()
        if edge is None:
            self.status_lbl.setText(tap.errors[-1].strip() if tap.errors
                                    else "no edge created")
            return False
        self._collected[SECTION_EDGE] = []
        self.refresh()
        self.status_lbl.setText(
            "%s created from %d sketch%s"
            % (edge.Name, len(sketches), "" if len(sketches) == 1 else "es"))
        FreeCAD.Console.PrintMessage("Edge created: %s\n" % edge.Name)
        return True

    def confirm_patch(self):
        """Confirm the collected edges into ONE patch, and report success
        only for a patch that ACTUALLY built (#66).

        The fill derives the boundary cycle from the edges' own
        endpoints, so the order the user clicked them in no longer
        decides whether the patch exists -- that landmine is defused in
        SilkMachinery.loop_order, not here. What is left for the panel to
        police is the one case no fill can save: a selection that does not
        close a loop at all. Then no object is created, the console error
        names the offending edges, and the collection survives so the user
        can fix it -- the #62 stale-entry idiom, one transaction, nothing
        left behind.

        #67: the created Patch also KEEPS the resolved cycle in its
        `Edges` property, so entry k is boundary side k whatever the
        click order was. The panel hands back a patch that is
        self-consistent -- its stored edge list is the cycle its geometry
        was built from -- rather than one whose data tab contradicts its
        own surface. Nothing to do here: the normalization lives in the
        Patch, so the data-tab and old-document paths get it too.
        """
        edges = self.collected(SECTION_PATCH)
        stale = self.stale_items()
        if stale:
            return self._refuse_stale(stale)
        _, problem = loop_order(edges)
        if problem:
            self._refuse("Silk: cannot apply -- the %d collected edges do "
                         "not close a loop (%s). Nothing was created; the "
                         "collection is unchanged." % (len(edges), problem))
            return False
        doc = self.doc
        doc.openTransaction("Silk patch")
        try:
            with _ConsoleTap() as tap:
                patch = create_patch(edges)
        finally:
            doc.commitTransaction()
        if patch is None:
            self.status_lbl.setText(tap.errors[-1].strip() if tap.errors
                                    else "no patch created")
            return False
        if not list(getattr(patch, "Poles", None) or []):
            # A patch with no poles is not a patch -- it is the invisible
            # ghost #66 is about. Refuse loudly, and take the empty object
            # back out so a refusal leaves NOTHING behind (#62's idiom).
            name = patch.Name
            doc.openTransaction("Silk patch")
            try:
                doc.removeObject(name)
            finally:
                doc.commitTransaction()
            self._refuse("Silk: cannot apply -- the fill produced no poles, "
                         "so %s would have rendered nothing. Nothing was "
                         "kept; the collection is unchanged." % name)
            return False
        self._collected[SECTION_PATCH] = []
        self.refresh()
        fill = "pointed fill" if len(edges) == 3 else "quad fill"
        self.status_lbl.setText("%s created from %d edges (%s)"
                                % (patch.Name, len(edges), fill))
        FreeCAD.Console.PrintMessage("Patch created: %s\n" % patch.Name)
        return True

    def confirm_blend(self):
        """Every collected seam in ONE transaction, so one Enter is one
        undo step no matter how many blends it made."""
        seams = self.collected(SECTION_BLEND)
        stale = self.stale_items()
        if stale:
            return self._refuse_stale(stale)
        bad = self.invalid_bands()
        if bad:
            item, problem = bad[0]
            self._refuse("Silk: cannot apply the blend on %s -- %s"
                         % (item.name, problem))
            return False

        doc = self.doc
        before = {o.Name for o in doc.Objects}
        doc.openTransaction("Silk blend")
        outcomes = []
        try:
            for edge in seams:
                with _ConsoleTap() as tap:
                    blend = create_blend_by_edge(edge)
                outcomes.append((edge, blend, tap))
        finally:
            doc.commitTransaction()

        self._collected[SECTION_BLEND] = []
        self.refresh()

        made, lines = [], []
        for edge, blend, tap in outcomes:
            if blend is None:
                lines.append(tap.errors[-1].strip() if tap.errors
                             else "no blend created on %s" % edge.Name)
            elif blend.Name in before:
                # Idempotent no-op: the resolver returned the EXISTING
                # blend and already said so, in its own words. Do not
                # double-report it as a creation.
                lines.append(tap.messages[-1].strip() if tap.messages
                             else "no blend created on %s" % edge.Name)
            else:
                made.append(blend.Name)
                lines.append("%s created across %s" % (blend.Name, edge.Name))
                FreeCAD.Console.PrintMessage(
                    "%s created across %s\n" % (blend.Name, edge.Name))
        if len(made) > 1:
            lines.insert(0, "%d blends created in one step" % len(made))
        self.status_lbl.setText("; ".join(lines))
        return bool(made)

    def _refuse_stale(self, stale):
        item, why = stale[0]
        extra = ""
        if len(stale) > 1:
            extra = " (%d collected entries are stale)" % len(stale)
        self._refuse("Silk: cannot apply -- %s %s. Nothing was created; "
                     "the collection is unchanged, remove %s and try "
                     "again.%s" % (item.name, why, item.name, extra))
        return False

    def _refuse(self, message):
        """Refuse LOUDLY, on the console and on the status line. The
        collection survives so the user can fix it."""
        FreeCAD.Console.PrintError(message + "\n")
        self.status_lbl.setText(message)

    # ---- read-only view helpers (tests / assertions) -------------------

    def status_text(self):
        return self.status_lbl.text()

    def hint_text(self):
        """#47's next-step wording. It sits BELOW the accordion as a muted
        line (and in the tooltips), not above it in a box of its own."""
        return self.hint_lbl.text()

    def progress_text(self):
        return self.blend_progress_lbl.text()

    def seam_row_index(self, edge):
        """Row index of `edge`'s seam in the table, or -1."""
        for row, entry in enumerate(self.seam_inventory()):
            if entry["edge"] is edge:
                return row
        return -1

    def row_texts(self, row):
        """The three static cell strings of `row` (the split column is a
        widget, not text)."""
        return [self.blend_table.item(row, col).text()
                for col in (self.COL_EDGE, self.COL_PATCHES, self.COL_STATUS)]

    def split_editor(self, edge):
        """The mounted QDoubleSpinBox for a seam row's band split, or
        None. Mounted on every blendable and every blended row."""
        return self._split_widgets.get(edge.Name)


def status_text(entry):
    """The display string for one seam_inventory entry's status.

    `blendable` / `blended by <Blend.Name>` / `blocked` -- the entry's own
    words, with the blend named so the progress is legible.
    """
    if entry["status"] == "blended" and entry["blend"] is not None:
        return "blended by %s" % entry["blend"].Name
    return entry["status"]


# ---- band split: read / write / validate ----------------------------------

def _side_of(p, other):
    """(property_name, side) of the band p contributes to the seam it
    shares with `other`, or (None, None) when they share no edge.

    Tolerates an unresolved pair: a patch that never built (its fill
    failed, or it is mid-recompute) carries no poles to compare, and seam
    resolution raises on the empty corner list. That is no reason to
    abandon the whole table -- the row simply has no band to size."""
    try:
        etype, ss = patch_side(p, other)
    except Exception:
        return None, None
    if etype is None:
        return None, None
    # A seam along U fixes a V interval, so the band lives in VSplits.
    return ("VSplits" if etype[0] == "U" else "USplits"), ss


def read_band_split(entry):
    """(pa_prop, pa_ss, pa_value, pb_prop, pb_ss, pb_value) for one seam:
    which split property on each patch carves this seam's band, at which
    end, and what the value is now. A value the patch does not carry yet
    reads as the DEFAULT the blend would write (#64 leaves the patch's own
    split alone when there is one). Returns None when the pair shares no
    edge."""
    pa, pb = entry["patch_a"], entry["patch_b"]
    pa_prop, pa_ss = _side_of(pa, pb)
    pb_prop, pb_ss = _side_of(pb, pa)
    if pa_prop is None or pb_prop is None:
        return None
    tol = 0.01

    def value(p, prop, ss):
        v = split_at_end(list(getattr(p, prop) or []), ss)
        return DEFAULT_BAND[ss] if v is None else float(v)
    return (pa_prop, pa_ss, value(pa, pa_prop, pa_ss),
            pb_prop, pb_ss, value(pb, pb_prop, pb_ss))


def write_band_split(entry, value):
    """Write `value` onto BOTH patches' band splits for this seam.

    Since #64 the blend READS the split rather than asserting a default,
    so this is the band width -- the panel's stand-in for a fillet
    radius. Both patches get it because the row is one seam with one
    width; each patch keeps it on its own axis and at its own end, and
    #61 normalizes each list on set. Each write is its own transaction
    (one undo step per edit), kept out of the confirm transaction.
    """
    read = read_band_split(entry)
    if read is None:
        return False
    pa, pb = entry["patch_a"], entry["patch_b"]
    pa_prop, pa_ss = read[0], read[1]
    pb_prop, pb_ss = read[3], read[4]
    doc = entry["edge"].Document
    for p, prop, ss in ((pa, pa_prop, pa_ss), (pb, pb_prop, pb_ss)):
        if prop is None:
            continue
        cur = list(getattr(p, prop) or [])
        old = split_at_end(cur, ss)
        new = [v for v in cur if old is None or v != old]
        new = sorted(set(new + [float(value)]))
        doc.openTransaction("Silk band split")
        try:
            setattr(p, prop, new)
        finally:
            doc.commitTransaction()
    doc.recompute()
    return True


def _band_cell_count(splits_along, splits_band, etype, ss):
    """How many subgrid cells the band covers, from a CANDIDATE split
    layout -- the arithmetic of SilkMachinery.band_cells, expressed on
    lists instead of on a live patch so a width can be checked before it
    is written.

    Only the shared pure helpers are used (build_intervals, corner_cells);
    Tests/test_task_panel.py pins this against the real band_cells on a
    patch after the write, so the two can never drift apart silently.
    """
    n_along = len(build_intervals(splits_along))
    n_band = len(build_intervals(splits_band))
    if etype[0] == "U":     # seam along U: band fixes a V interval
        return n_along - len(corner_cells(splits_along, n_along))
    return n_band - len(corner_cells(splits_band, n_band))


def band_cell_problem(entry, value=None):
    """None when this seam's band is exactly ONE cell, otherwise a
    message naming the patch and the values that break it."""
    pa, pb = entry["patch_a"], entry["patch_b"]
    pa_prop, pa_ss = _side_of(pa, pb)
    pb_prop, pb_ss = _side_of(pb, pa)
    if pa_prop is None or pb_prop is None:
        return ("%s and %s share no edge, so there is no band to size"
                % (pa.Name, pb.Name))
    # A seam along U fixes a V interval, so the band lives in VSplits:
    # the direction follows from the property, no second resolution.
    pa_etype = ("U" if pa_prop == "VSplits" else "V", pa_ss)
    pb_etype = ("U" if pb_prop == "VSplits" else "V", pb_ss)

    def layout(p, prop, ss, along_prop):
        cur = list(getattr(p, prop) or [])
        old = split_at_end(cur, ss)
        band = [v for v in cur if old is None or v != old]
        if value is not None:
            band = sorted(set(band + [float(value)]))
        along = list(getattr(p, along_prop) or [])
        return band, along

    for p, prop, ss, etype, other_prop in (
            (pa, pa_prop, pa_ss, pa_etype,
             "USplits" if pa_prop == "VSplits" else "VSplits"),
            (pb, pb_prop, pb_ss, pb_etype,
             "USplits" if pb_prop == "VSplits" else "VSplits")):
        band, along = layout(p, prop, ss, other_prop)
        n = _band_cell_count(along, band, etype, ss)
        if n != 1:
            return ("patch %s.%s = %s with %s = %s covers %d band cells "
                    "(exactly 1 is required; multi-cell bands are not "
                    "supported yet)"
                    % (p.Name, prop, ["%g" % v for v in band],
                       other_prop, ["%g" % v for v in along], n))
    return None


# ---- open / command --------------------------------------------------------

def open_task_panel(doc=None):
    """Build the panel and show it in the NATIVE task panel. Returns it.

    Refuses to open over a FOREIGN task dialog: FreeCAD allows exactly
    one and raises `Active task dialog found`. We never silently close
    someone else's task -- if the active dialog is OURS we close it
    through our own path (unsubscribing first) and reopen fresh, because
    FreeCAD deletes the widget on close and there is nothing to reuse.
    """
    global _open_panel
    doc = doc if doc is not None else FreeCAD.ActiveDocument
    if doc is None:
        return None
    if Gui.Control.activeDialog():
        if _open_panel is None:
            raise RuntimeError("Active task dialog found")
        _open_panel.close_panel()
    panel = SilkTaskPanel(doc)
    _open_panel = panel
    Gui.Control.showDialog(SilkTaskDialog(panel))
    try:
        dialog = Gui.Control.activeTaskDialog()
        dialog.setDocumentName(doc.Name)
        dialog.setAutoCloseOnDeletedDocument(True)
    except Exception:
        pass
    return panel


class CreateGuide:
    """GUI command `Silk_Guide` -- open the Silk workflow task panel.

    The panel computes live: it adds NOTHING to the document of its own
    accord, and the objects it creates go through the ops layer like any
    other construction path."""

    def GetResources(self):
        return {'Pixmap': iconPath, 'MenuText': 'Silk Guide',
                'ToolTip': 'Open the Silk workflow panel: collect and '
                           'confirm edges, patches and blends, one step '
                           'at a time.'}

    def Activated(self):
        if FreeCAD.ActiveDocument is None:
            FreeCAD.Console.PrintError(
                "Silk: the guide needs an open document\n")
            return
        try:
            open_task_panel(FreeCAD.ActiveDocument)
        except RuntimeError as e:
            FreeCAD.Console.PrintError(
                "Silk: cannot open the guide -- %s (another task panel is "
                "showing; close it first)\n" % e)

    def IsActive(self):
        return Gui is not None


Gui.addCommand("Silk_Guide", CreateGuide())