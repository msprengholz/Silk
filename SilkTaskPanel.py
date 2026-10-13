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
#    editors: the seam's band is the blend's cross-section, so the width
#    stays tunable once the blend exists (#62 follow-up). Collectability
#    is separate and unchanged -- a blended row still refuses a blend.
#
#    The seam's status is a CHECKBOX, not a word (#69). "blended" is the
#    one state worth a glance at a glance, so it is the one that gets the
#    tick; "blocked" -- an edge three or more patches reference, which is
#    not a seam anyone can blend -- is greyed out rather than merely left
#    unticked, because unticked-and-live is exactly what "blendable" looks
#    like, and the two must not be mistaken for each other. The reason is
#    in the checkbox's tooltip: it costs no column width, and the column
#    it saved is what pays for the two editors below.
#
#    Those editors are TWO, one per patch (#69), because a seam is
#    bounded by one split on EACH patch and those two are already free to
#    disagree -- measured on the human's own file, one patch carries
#    USplits=[0.3] and VSplits=[0.1] for two different seams. Each spin is
#    seeded from its OWN patch's split, so the ordinary symmetric seam
#    still shows the same number twice (symmetry stays one gesture) while
#    a seam that already diverges shows its divergence instead of a
#    flattering lie about it. One edit validates against its own patch
#    only and writes its own patch only: a width that leaves one band cell
#    on A may leave two on B, and refusing B's edit would refuse A's
#    because they sat next to each other.
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

# How wide the blended-flag column is, at least (#69). A QCheckBox needs
# its indicator plus the cell's own margins and nothing else -- but the
# column is also carrying the word "Blended?", and a header that elides
# into "lended" is worse than a column that is a few pixels too wide. So
# the width actually used is the HEADER's, measured from the font at
# build time rather than guessed. Everything beyond that -- and the header
# is the whole of it -- goes to the two band editors, which are the point
# of the row.
FLAG_MIN_WIDTH = 44

# The grey a BLOCKED seam row's own text is drawn in (#69). Module level
# so the panel and its tests name one brush.
GREY_BRUSH = QtGui.QBrush(QtGui.QColor(0x90, 0x90, 0x90))


def flag_column_width(table):
    """The width the `Blended?` column needs so its own label fits.

    The header text plus the header's own left+right padding, and never
    less than FLAG_MIN_WIDTH (which is also QHeaderView's own default
    floor -- ask for less and it is silently clamped back, so a too-small
    request is a lie about what got drawn)."""
    header = table.horizontalHeader()
    label = table.horizontalHeaderItem(SilkTaskPanel.COL_BLENDED)
    text = label.text() if label is not None else "Blended?"
    fm = header.fontMetrics()
    try:
        padding = 2 * header.style().pixelMetric(
            QtWidgets.QStyle.PM_HeaderMargin)
    except Exception:
        padding = 12          # a style with no such metric: guess
    return max(FLAG_MIN_WIDTH, fm.horizontalAdvance(text) + padding + 4)


# Which patch of a seam's pair a band editor is about (#69). `patch_a` is
# the pair's first referrer in document order, `patch_b` the second --
# the same pairing seam_inventory reports, so an editor and a patch are
# never matched by name-matching or by position guessing. Module level
# because the read / write / validate helpers all key off it, and the
# helpers are module level.
BAND_A, BAND_B = "A", "B"

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
    "OK blends every collected seam in one undo step. A seam is bounded by "
    "one band split on EACH of its two patches, so a blended row has an "
    "editor per patch (Band A / Band B) -- they start equal, and setting "
    "them apart is deliberate.")


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


class _BandEditorFilter(QtCore.QObject if QtCore else object):
    """Enter typed in ONE band editor means "commit that editor, then
    confirm" (#71).

    The human asked whether this conflicts with the 3D-view Enter, and it
    does not: the application shortcut confirms the COLLECTION, while a
    band editor's Enter commits its own VALUE. Two different subjects, so
    both can happen -- but exactly once each, and in that order.

    Two events, two jobs:

      * KeyPress Return/Enter -> the panel commits THIS editor and then
        confirms, and the event is CONSUMED. Consumed, because a
        QDoubleSpinBox's own Enter handling emits a second
        editingFinished, and because confirming rebuilds every row -- a
        commit arriving after that would be writing to a detached widget.

      * ShortcutOverride for the same key -> ACCEPTED. That is what stops
        the ApplicationShortcut confirm from ALSO firing on one
        keystroke: Qt skips shortcut processing when the override is
        accepted. Without it, one Enter would confirm twice and try to
        blend the same collected seams twice. Nothing else is
        intercepted, so Enter everywhere else in FreeCAD -- including the
        3D view -- still reaches the confirm shortcut untouched.
    """

    def __init__(self, panel, entry, which, spin):
        try:
            super().__init__(spin)
        except TypeError:      # Qt-less console build
            pass
        self.panel = panel
        self.entry = entry
        self.which = which
        self.spin = spin

    @staticmethod
    def _is_enter(event):
        return event.key() in (QtCore.Qt.Key_Return, QtCore.Qt.Key_Enter)

    def eventFilter(self, obj, event):
        kind = event.type()
        if kind == QtCore.QEvent.ShortcutOverride and self._is_enter(event):
            event.accept()          # no second confirm on one keystroke
            return True
        if kind == QtCore.QEvent.KeyPress and self._is_enter(event):
            self.panel.band_editor_enter(self.entry, self.which, self.spin)
            return True
        return False


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

      Blend  -- ONE merged table of every seam in the document. Each
                row is ticked in the `Blended?` column when its seam is
                already blended; an unticked LIVE row is blendable, and
                an unticked GREYED row is blocked (three or more patches
                reference the edge) with the reason in the tooltip.
                Clicking a blendable row collects that seam; a collected
                row is highlighted and clicking it again removes it.
                EVERY live row -- blended ones included -- also exposes
                the band's width, one editor PER PATCH (`Band A` /
                `Band B`, #69): since #64 the blend READS each patch's
                split, so a width set here is the width that blend uses
                on that patch, whether the blend already exists or not.
                The two are seeded equal, but a seam's two bands are
                independently sized and may diverge.

    Confirm (Enter or the native OK button) is one document transaction:
    one undo step, even when several seams blend at once. After applying,
    the collection clears, the section stays open, and nothing advances
    by itself.
    """

    # #69: the status WORD is gone -- it became a checkbox, so the width
    # it occupied pays for a SECOND band editor (one per patch). Five
    # columns now, and the row's whole content is: which seam, which two
    # patches, has it been blended, and how wide is its band on each of
    # them.
    COL_EDGE, COL_PATCHES, COL_BLENDED, COL_BAND_A, COL_BAND_B = 0, 1, 2, 3, 4
    COLUMNS = ("Seam", "Patches", "Blended?", "Band A", "Band B")

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
        # seam edge Name -> {BAND_A: QDoubleSpinBox, BAND_B: ...} for the
        # band-split editors currently mounted in the table. Two per row
        # since #69: one per patch, each writing only its own.
        self._split_widgets = {}
        # seam edge Name -> QCheckBox for the row's blended flag.
        self._flag_widgets = {}
        # seam edge Name -> {BAND_A: entry, BAND_B: entry}: which seam
        # each mounted editor belongs to (#71). _split_widgets says what
        # is on screen; this says what it is FOR, which is what lets a
        # refresh tell a held edit from a written one.
        self._split_meta = {}
        # the event filters installed on those editors, kept alive here:
        # a Qt parent owns the filter, but holding it costs nothing and
        # makes 'the filters are cleared with the rows' obvious.
        self._split_filters = []
        # the row brush for a row that is NOT blocked; see _live_brush
        self._live_foreground = None

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
        #
        # #69: five columns now -- the status WORD became a checkbox and
        # its width bought a second band editor -- so the checkbox column
        # is sized to what it actually needs (its label, see
        # flag_column_width) instead of taking a fifth of the table like
        # the four columns that share the slack. Every pixel it does not
        # take is a pixel the two band editors keep, and they are the
        # point of the row.
        header = self.blend_table.horizontalHeader()
        header.setSectionResizeMode(QtWidgets.QHeaderView.Stretch)
        header.setSectionResizeMode(self.COL_BLENDED,
                                    QtWidgets.QHeaderView.Fixed)
        header.resizeSection(self.COL_BLENDED,
                             flag_column_width(self.blend_table))
        # Belt and braces for the same overrun: the columns stretch, so
        # no section may exceed its share. A minimum section size (or a
        # long unbreakable cell) would otherwise push the table's
        # minimum past the dock and earn the dock a horizontal
        # scrollbar.
        header.setMinimumSectionSize(16)
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
        self._release_document_refs()
        Gui.Control.closeDialog()

    def _release_document_refs(self):
        """Drop every reference this panel holds into the document (#72).

        Closing the widget is NOT enough to let the panel die. It keeps
        `_collected`, the two cell-widget registries, and `self.doc` --
        and a closed FreeCAD Document's Python object still owns its
        Objects and their shapes. So a panel that outlives its document
        pins that whole document's geometry for the life of the process.

        Measured: the panel tests leaked one such panel per test, ~90 MB
        each, 3.4 GB across 38 tests -- with the module still reporting
        "0 orphaned module generations", because nothing here is a
        module leak at all. It is a plain reference cycle through a
        deleted Document.

        Called from close_panel, so it covers every exit: manual close,
        the document-switch hook, and the caller-closed path."""
        self._collected = {SECTION_EDGE: [], SECTION_PATCH: [],
                           SECTION_BLEND: []}
        self._split_widgets = {}
        self._split_meta = {}
        self._split_filters = []
        self._flag_widgets = {}
        try:
            self.doc = None
        except Exception:
            pass

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
        # SHOWS them, with the blocked one GREYED in the flag column
        # (#69), which is where a blocked seam is explained. A seam that
        # is ALREADY BLENDED is refused here too: its blend exists, so
        # collecting it would only ever re-run an idempotent no-op. Its
        # band editors are still live -- that is the editors'
        # availability, not its collectability.
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
        # #71: a refresh re-mounts every row, so an editor still holding
        # an unwritten width is about to be detached. Commit it first, or
        # the value the user typed is lost without a word -- which is what
        # made it look like the edit "worked on the second try".
        self._commit_in_flight_edits()
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
        # Drop every mounted editor first; the rows below re-mount the
        # ones that are still needed.
        self._split_widgets = {}
        self._split_meta = {}
        self._split_filters = []
        self._flag_widgets = {}
        for row, entry in enumerate(seams):
            texts = (entry["edge"].Name,
                     "%s <-> %s" % (entry["patch_a"].Name,
                                    entry["patch_b"].Name))
            for col, text in zip((self.COL_EDGE, self.COL_PATCHES), texts):
                item = self.blend_table.item(row, col)
                if item is None:
                    item = QtWidgets.QTableWidgetItem(text)
                    self.blend_table.setItem(row, col, item)
                else:
                    item.setText(text)
                # Five columns in a 380px dock means the seam name and
                # the patch pair can be elided to nothing (#69). Their
                # full text is one hover away, which is what the split
                # column did before it became a widget column.
                item.setToolTip(text)
            taken = any(i.obj is entry["edge"] for i in collected)
            blocked = entry["status"] == "blocked"
            # The collection highlight is over the TEXT cells only. The
            # blended flag and the two band editors are cell widgets now,
            # and a cell widget paints over its cell: there is nothing
            # for a background brush to reach there, and reaching past
            # them is how a "highlighted" row ends up looking half done.
            for col in (self.COL_EDGE, self.COL_PATCHES):
                item = self.blend_table.item(row, col)
                if item is None:
                    continue
                font = item.font()
                font.setBold(taken)
                item.setFont(font)
                if taken:
                    item.setBackground(QtGui.QBrush(
                        QtGui.QColor(0xD8, 0xF0, 0xD8)))
                else:
                    item.setBackground(QtGui.QBrush())
                # A BLOCKED row greys its own TEXT too, and this is not
                # decoration. `setEnabled(False)` on the flag is what the
                # ticket asks for, but in most styles an UNCHECKED tick
                # is already drawn in a pale grey -- so greying it changes
                # almost nothing on screen, and the one thing that has to
                # be unmistakable (blocked is not blendable) is the one
                # thing the pixels do not say. A greyed row is the idiom
                # every disabled control in Qt already speaks, and the
                # seam name and the patch pair going grey is what makes it
                # read at a glance. The name is still selectable, still in
                # the tooltip and still in item.text().
                item.setForeground(
                    GREY_BRUSH if blocked else self._live_brush())
            for col in (self.COL_BLENDED, self.COL_BAND_A, self.COL_BAND_B):
                self.blend_table.setCellWidget(row, col, None)
            self._mount_blended_flag(row, entry)
            # EVERY seam row carries its band-split editors, blended or
            # not. #62 mounted the (single) one only on COLLECTED rows,
            # and a collected row is by definition blendable, so a seam
            # that had already been blended had no editor at all -- the
            # width that blend is actually built from was then only
            # reachable through the property editor, which is the thing
            # #62 exists to replace. Collectability is a separate
            # question and stays where it is (`accepts`), so a blended row
            # still refuses blend CREATION -- only the editors'
            # availability changed.
            #
            # A BLOCKED seam gets neither editor: it is not blendable, so
            # there is no band for a width to size, and a live-looking
            # editor on a row that cannot act is a control that lies
            # about being one.
            if entry["status"] in ("blendable", "blended"):
                self._mount_split_editors(row, entry)
        self._fit_table(len(seams))

    def _live_brush(self):
        """The row brush for a row that is NOT blocked (#69).

        Captured once, from a cell that has never been greyed. A blocked
        row that later stops being blocked (drop a patch and the seam
        becomes a seam again) must go back to the palette's own text
        colour, and `item.foreground()` on a cell we just greyed would
        hand back the grey -- so the live one is remembered rather than
        read back."""
        if self._live_foreground is None:
            self._live_foreground = self.blend_table.palette().brush(
                QtGui.QPalette.Text)
        return self._live_foreground

    def _mount_blended_flag(self, row, entry):
        """The row's status as a checkbox (#69) -- and the checkbox IS the
        click (#70).

        Ticked = blended, the one state worth a glance at a glance.
        Unticked and LIVE = blendable, the ordinary not-yet case.
        Unticked and GREYED = blocked: an edge three or more patches
        reference, which is not a seam anyone can blend.

        The grey is the whole reason this is a widget and not a word. A
        column of text can say `blocked`; a column of ticks can say
        nothing except ticked / not, and an unticked-but-clickable row
        reads as "ready" to anyone who glances. Disabling it draws the
        difference without spending a character on it, and the reason --
        which IS words, and which used to be the status text -- moves to
        the tooltip, where it costs no column width at all.

        #70: a LIVE tick is now an INPUT, not a readout. Unticking a
        blended seam UNBLENDS it (deletes the Blend, one undo step);
        ticking a blendable seam blends it. The outcomes are reported in
        the status line, naming the seam -- a checkbox carries no text,
        so the words have to come from the panel. A BLOCKED row's tick
        stays disabled and therefore inert BOTH ways: not tappable (a
        disabled widget ignores the mouse) and not untickable (it is
        already unchecked). A greyed tick that still responds is worse
        than no tick.

        It still takes no focus (confirm is an Application-scoped
        shortcut and must never have a tick box to fight), and clicking
        the ROW still collects/removes the seam for the multi-seam
        confirm -- the flag drives THIS seam at once."""
        status = entry["status"]
        flag = QtWidgets.QCheckBox()
        flag.setFocusPolicy(QtCore.Qt.NoFocus)
        flag.setToolTip(status_reason(entry))
        flag.setChecked(status == "blended")
        if status == "blocked":
            # Greyed, the way any disabled control renders -- so the row
            # reads as inert with no new vocabulary to learn. A disabled
            # checkbox emits no click, so blocked is inert both ways.
            flag.setEnabled(False)
        else:
            # The checkbox IS the click (#70): untick unblends, tick
            # blends. Clicking the ROW still collects the seam for the
            # multi-seam confirm; the flag drives THIS seam at once.
            flag.clicked.connect(
                lambda checked, e=entry, f=flag:
                self._on_flag_toggled(e, f, checked))
        self.blend_table.setCellWidget(row, self.COL_BLENDED, flag)
        self._flag_widgets[entry["edge"].Name] = flag

    def _on_flag_toggled(self, entry, flag, checked):
        """One tick/untick on a seam's flag (#70).

        Unticking a blended seam unblends it (deletes the Blend, one
        undo step); ticking a blendable seam blends it. A blocked row
        never reaches here -- its flag is disabled and emits no click.

        The guard is the render-time no-op: a setChecked from a refresh
        must not be mistaken for a user action, so a check state that
        ALREADY matches the row's status is ignored. The status is
        re-read from a FRESH seam_inventory (the row can have changed
        behind the panel's back), and every outcome -- success or
        refusal -- is reported in the status line NAMING the seam,
        because a checkbox carries no text and the user is left guessing
        otherwise. A refusal puts the tick back."""
        edge = entry["edge"]
        cur = next((e for e in self.seam_inventory()
                    if e["edge"] is edge), None)
        if cur is None:
            flag.setChecked(False)
            self._refuse("Silk: cannot act on %s -- it is no longer a seam. "
                         "Nothing was changed." % edge.Name)
            return False
        status = cur["status"]
        if checked == (status == "blended"):
            return False      # a render-time set, not a user action
        if checked:
            return self._blend_seam_now(cur, flag)
        return self._unblend_seam_now(cur, flag)

    def _blend_seam_now(self, entry, flag):
        """Tick: blend this one seam now, as its own transaction (one undo
        step) -- the same path the confirm uses, driven by the flag."""
        edge = entry["edge"]
        doc = self.doc
        before = {o.Name for o in doc.Objects}
        doc.openTransaction("Silk blend")
        try:
            with _ConsoleTap() as tap:
                blend = create_blend_by_edge(edge)
        finally:
            doc.commitTransaction()
        self.refresh()
        if blend is None:
            why = tap.errors[-1].strip() if tap.errors \
                else "no blend was created"
            flag.setChecked(False)
            self._refuse("Silk: cannot blend %s -- %s. Nothing was changed."
                         % (edge.Name, why))
            return False
        if blend.Name in before:
            # Idempotent no-op: a blend already covered this seam behind
            # the panel's back; the refresh shows it ticked.
            self.status_lbl.setText(
                "%s is already blended by %s -- nothing to do"
                % (edge.Name, blend.Name))
            return False
        self.status_lbl.setText("%s created across %s" % (blend.Name, edge.Name))
        FreeCAD.Console.PrintMessage(
            "%s created across %s\n" % (blend.Name, edge.Name))
        return True

    def _unblend_seam_now(self, entry, flag):
        """Untick: delete the Blend on this seam, as its own transaction
        (one undo step).

        The band splits the blend wrote SURVIVE the unblend (#70): they
        are the user's chosen width (#64) and re-blending reads them
        back, so deleting them would silently discard the user's widths."""
        edge = entry["edge"]
        blend = entry["blend"]
        doc = self.doc
        if blend is None or doc.getObject(blend.Name) is None:
            # The blend is already gone behind the panel's back; the
            # guard's fresh status said blended, so this is a race -- say
            # so rather than leaving the tick pulled.
            flag.setChecked(True)
            self._refuse("Silk: cannot unblend %s -- its blend %s is no "
                         "longer in the document. Nothing was changed."
                         % (edge.Name, getattr(blend, "Name", "?")))
            return False
        blend_name = blend.Name
        doc.openTransaction("Silk unblend")
        try:
            doc.removeObject(blend_name)
        finally:
            doc.commitTransaction()
        self.refresh()
        self.status_lbl.setText(
            "unblended %s (%s deleted)" % (edge.Name, blend_name))
        FreeCAD.Console.PrintMessage(
            "unblended %s (%s deleted)\n" % (edge.Name, blend_name))
        return True

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

    def _mount_split_editors(self, row, entry):
        """Expose the band's split on EVERY seam row -- and there are TWO
        of them now (#69), because a seam is bounded by one split on EACH
        patch.

        Each value comes straight off its OWN patch's USplits/VSplits and
        each write goes straight back onto that property, which is exactly
        what #64's blend reads. So an editor is a width, a width is a
        band, and a band is a cross-section -- there is no panel-side copy
        to drift.

        Blended rows included (#62 follow-up): the seam's band IS the
        blend's cross-section, so a width set here re-drives an existing
        blend exactly as it would size a new one -- which is the whole
        reason to be able to edit it after the blend exists. Refusing to
        COLLECT an already-blended row is untouched (`accepts`).

        Both editors are seeded from their own patch, so the ordinary
        symmetric seam shows the same number twice and symmetry is still
        one gesture, while a seam whose two patches already disagree shows
        that disagreement rather than one of the two numbers pretending to
        speak for both. The tooltip names which patch this editor writes
        and what the OTHER one currently holds, so the pair is legible
        without a third column."""
        read = read_band_split(entry)
        if read is None:
            return
        col = {BAND_A: self.COL_BAND_A, BAND_B: self.COL_BAND_B}
        spins = {}
        for which in (BAND_A, BAND_B):
            patch, prop, ss, value = band_side(entry, which, read)
            spin = QtWidgets.QDoubleSpinBox()
            spin.setDecimals(3)
            spin.setSingleStep(0.05)
            spin.setRange(0.001, 0.999)     # constrained 0 < u < 1
            # No up/down buttons (#69): two editors must fit a 380px dock
            # side by side, and the steppers are ~30px of chrome on each
            # -- wider than the digits they surround. The keyboard and the
            # wheel still step, and the value is what the user is really
            # editing.
            spin.setButtonSymbols(
                QtWidgets.QAbstractSpinBox.ButtonSymbols.NoButtons)
            spin.setValue(value)
            spin.setToolTip(self._band_tooltip(entry, which, read))
            spin.editingFinished.connect(
                lambda e=entry, w=which, s=spin:
                self._on_split_edited(e, w, s))
            self.blend_table.setCellWidget(row, col[which], spin)
            spins[which] = spin
        self._split_widgets[entry["edge"].Name] = spins
        # #71: remember which seam each mounted editor belongs to, so a
        # refresh can tell an edit that is merely HELD from one that is
        # already written. The registry is keyed by edge name exactly like
        # _split_widgets, and both are cleared together on re-render.
        meta = self._split_meta.setdefault(entry["edge"].Name, {})
        for which2 in (BAND_A, BAND_B):
            spin2 = spins.get(which2)
            if spin2 is None:
                continue
            meta[which2] = entry
            # Enter in an editor commits it and then confirms (#71).
            filt = _BandEditorFilter(self, entry, which2, spin2)
            self._split_filters.append(filt)   # keep it alive
            spin2.installEventFilter(filt)

    @staticmethod
    def _band_tooltip(entry, which, read):
        """What one band editor writes, and what its partner holds.

        The per-patch wording (#69) is the point: an editor says WHICH
        patch's property it moves, because after this there are two and
        "the band split" alone would not say which of them a number is
        about."""
        patch, prop, ss, value = band_side(entry, which, read)
        other = BAND_B if which == BAND_A else BAND_A
        o_patch, o_prop, o_ss, o_value = band_side(entry, other, read)
        same = abs(o_value - value) < 1e-12
        return (
            "Band width on %s.%s (this seam's %s end).\n"
            "The blend reads this split, so this is the width the band is "
            "cut at on that patch.\n"
            "The number shown is the WIDTH from the seam; %s stores the "
            "parametric split (%g at this end), which is what the "
            "property editor shows -- the two never disagree about what "
            "is stored."
            % (patch.Name, prop, "parametric-0" if ss == 0
               else "parametric-1", prop,
               _stored_from_width(value, ss))
            + ("\n%s.%s currently holds %g -- the two patches' bands "
               "differ, which is allowed." % (o_patch.Name, o_prop, o_value)
               if not same else
               "\n%s.%s holds the same %g, so this seam's band is "
               "symmetric." % (o_patch.Name, o_prop, o_value))
            + ("\nThis seam is blended: editing the width re-drives that "
               "blend." if entry["status"] == "blended" else ""))

    def _on_split_edited(self, entry, which=BAND_A, edited=None):
        """One split edit: validate against ITS OWN patch, then write
        ITS OWN patch, as its own transaction.

        Per-PATCH is the substance of #69. A width is refused when it
        would not leave exactly one band cell on the patch it is being
        written to -- that write is what the blend's cross-section is
        built from, so committing an unusable one would silently break a
        blend the user can already see. What the check must NOT do is
        consult the OTHER patch: with one shared spin that was free, and
        with two editors it is a trap, because the two bands are
        independently sized and a layout that leaves one cell on A can
        leave two on B. So a width refused on A neither rolls B back nor
        stops B being edited; each editor owns its own verdict.

        Only the refused spin is put back, and from its own patch's
        stored split, so the panel and the property never disagree and
        the partner editor is not yanked to a value the user never typed.
        """
        spins = self._split_widgets.get(entry["edge"].Name) or {}
        spin = spins.get(which)
        if spin is None:
            return False
        if edited is not None and edited is not spin:
            # The table re-rendered under this editor (a refresh, or the
            # confirm that re-mounts every row) and `edited` is no longer
            # the one mounted. Acting anyway would apply the DETACHED
            # widget's value to the LIVE one -- which is 0.1, the seed --
            # and report the user's own number as having been written. Say
            # nothing and change nothing instead: the live editor is still
            # on screen with the right value.
            return False
        value = spin.value()
        problem = band_cell_problem(entry, which, value)
        if problem:
            before = read_band_split(entry)
            if before is not None:
                spin.setValue(band_side(entry, which, before)[3])
            self._refuse("Silk: cannot set the band width on %s for %s -- "
                         "%s. That split was left as it was."
                         % (entry["edge"].Name, band_label(which), problem))
            return False
        if not write_band_split(entry, which, value):
            return False
        read = read_band_split(entry)
        patch, prop = band_side(entry, which, read)[:2]
        self.status_lbl.setText(
            "band width %g set on %s.%s%s"
            % (value, patch.Name, prop,
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
        refuses clearly instead of creating something wrong.

        Per-PATCH (#69): each editor is judged against its own patch
        alone. Two bands that are independently sized can each be fine
        and the pair still be right -- checking them as one number was
        only ever possible because there was one spin to check."""
        bad = []
        for item in self._collected[SECTION_BLEND]:
            edge = item.obj
            entry = next((e for e in self.seam_inventory()
                          if e["edge"] is edge), None)
            if entry is None or entry["status"] != "blendable":
                continue
            spins = self._split_widgets.get(item.name) or {}
            for which in (BAND_A, BAND_B):
                spin = spins.get(which)
                value = spin.value() if spin is not None else None
                problem = band_cell_problem(entry, which, value)
                if problem:
                    bad.append((item, "%s: %s" % (band_label(which), problem)))
                    break
        return bad

    # ---- confirm ---------------------------------------------------------

    def panel_confirm(self):
        """The ONE confirm path, whatever fired it (Enter, the band
        editors' Enter, or the native OK button)."""
        # #71: an Enter typed into a band editor reaches here through
        # band_editor_enter, which has ALREADY committed that editor. Any
        # OTHER editor still holding an unwritten width is committed here,
        # before the confirm rebuilds the rows and detaches it.
        self._commit_in_flight_edits()
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
        """The two static cell strings of `row`: the seam and the patch
        pair. Since #69 the other three columns are widgets -- the
        blended flag and one band editor per patch -- so their content is
        read off the widgets themselves (blend_flag / split_editor), not
        off items."""
        return [self.blend_table.item(row, col).text()
                for col in (self.COL_EDGE, self.COL_PATCHES)]

    def blend_flag(self, edge):
        """The row's mounted blended-flag QCheckBox, or None. Mounted on
        every seam row, blocked ones included (that is where the grey
        lives)."""
        return self._flag_widgets.get(edge.Name)

    # ---- Enter, and edits in flight (#71) -------------------------------

    def _commit_spin(self, spin, entry, which):
        """Turn the editor's typed text into its value and write it ONCE.

        `interpretText()` is what a QDoubleSpinBox does on Enter -- and it
        emits `editingFinished` when the value moved, which is the
        ordinary commit path. It is muted here so the commit goes through
        `_on_split_edited` exactly once: two commits would be two
        transactions and two undo steps for one keystroke. Clicking away
        from the editor still takes the ordinary path -- same writer, one
        call.
        """
        blocked = spin.blockSignals(True)
        try:
            spin.interpretText()
        finally:
            spin.blockSignals(blocked)
        return self._on_split_edited(entry, which, spin)

    def band_editor_enter(self, entry, which, spin):
        """Enter in a band editor: COMMIT this editor's value, THEN
        confirm the open section.

        The order is the whole subtlety and it is not cosmetic. Confirming
        ends in `refresh()`, which tears down every row and re-mounts its
        editors; a commit arriving after that would be writing to a
        DETACHED widget, and the #69 guard would rightly drop it -- so the
        number just typed would silently never be written. Commit first,
        confirm second, and the value is on the patch before the blend is
        built.

        A REFUSED commit does not confirm. The refusal says why (the width
        would not leave one band cell on its own patch) and puts the editor
        back; confirming on top would blend the OLD width while the user
        is looking at a refused edit, which is the surprise the refusals
        exist to prevent.
        """
        if self.split_editor(entry["edge"], which) is not spin:
            return False      # detached by a refresh; the live editor stands
        if not self._commit_spin(spin, entry, which):
            return False
        return self.panel_confirm()

    def _editor_is_pending(self, entry, which, spin):
        """True when this editor holds a value its patch does NOT store.

        That is the honest reading of "an edit is in flight", and it is
        deliberately NOT a reading of the line edit's TEXT: a
        QDoubleSpinBox parses as you type, so a valid width is already in
        `value()` while the SPLIT is still unwritten -- and it is the
        split the blend is built from. So the test is panel-versus-patch:
        an editor disagreeing with its own patch is an edit nobody has
        written yet.
        """
        read = read_band_split(entry)
        if read is None:
            return False
        stored = band_side(entry, which, read)[3]
        if stored is None:
            return True
        return abs(float(spin.value()) - float(stored)) > 1e-12

    def _commit_in_flight_edits(self):
        """Commit every band edit that is typed but not yet committed.

        A refresh rebuilds every row, so an editor holding an unsaved
        value is about to be detached -- and a detached editor's later
        editingFinished hits the #69 guard, which correctly declines to act
        on it. That is how a typed width used to vanish without a message,
        and why the human saw it work "on the second try": by then the
        text was gone too and the editor held the stored value.

        Called from `refresh()` (before the rows are dropped) and from
        `panel_confirm()` (before anything is applied), so an in-progress
        edit is either committed or refused in its own words, never
        silently dropped. Each commit is its own transaction, so an
        unrelated refresh never merges somebody's width into its own undo
        step; and an editor that was merely refused has already been put
        back to the stored value, so it is not pending a second time.
        """
        committed = False
        for name, spins in list(self._split_widgets.items()):
            meta = self._split_meta.get(name) or {}
            for which, spin in list(spins.items()):
                entry = meta.get(which)
                if entry is None:
                    continue
                try:
                    pending = self._editor_is_pending(entry, which, spin)
                except RuntimeError:
                    continue        # the widget is already gone
                if pending and self._commit_spin(spin, entry, which):
                    committed = True
        return committed

    def split_editor(self, edge, which=BAND_A):
        """The mounted QDoubleSpinBox for ONE patch of a seam row's band,
        or None. Two per row since #69; `which` is BAND_A or BAND_B and
        selects the patch. Mounted on every blendable and every blended
        row, never on a blocked one."""
        spins = self._split_widgets.get(edge.Name) or {}
        return spins.get(which)


def status_reason(entry):
    """Why one seam_inventory entry is in the state it is -- the words
    the flag column used to spell out (#69).

    A checkbox says ticked / not and the grey says live / inert, which is
    all a glance needs. But "greyed, why?" is a hover away, and the
    tooltip is the one place the full explanation costs nothing at all:
      blendable  ready; say what a click would do;
      blended    name the blend, since that is the thing a user hunting
                 for "why is this not collecting?" needs;
      blocked    the reason it cannot act -- three or more patches share
                 the edge, which needs the deferred corner fill.
    """
    status = entry["status"]
    if status == "blended":
        made = ("%s" % entry["blend"].Name if entry["blend"] is not None
                else "another blend")
        return ("Blended by %s.\nUntick to unblend it (deletes %s, one "
                "undo step). Its band editors still work -- a width set "
                "here re-drives that blend." % (made, made))
    if status == "blocked":
        return ("Blocked: three or more patches reference this edge, so it "
                "is not a seam you can blend (it needs the deferred corner "
                "fill). The greyed tick is inert -- it neither ticks nor "
                "unticks.")
    return ("Not blended yet -- blendable.\nTick to blend it now, or click "
            "the row to collect it and blend several seams in one step.")


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


def _width_from_stored(value, ss):
    """The band WIDTH as the user reads it: the distance from the seam.

    The stored split is a PARAMETRIC position -- 0.1 at the parametric-0
    end, 0.9 at the parametric-1 end -- so the 1-end reads upside down
    (a stored 0.9 is a band 0.1 wide). The panel shows the width; the
    property keeps the parametric split (#70). Module level because the
    read / write / validate helpers all convert through it."""
    return value if ss == 0 else 1.0 - value


def _stored_from_width(width, ss):
    """The parametric split a band WIDTH of `width` means at end `ss`:
    `width` at the 0-end, 1 - width at the 1-end. The exact inverse of
    _width_from_stored, so display -> typed -> stored -> display is a
    round-trip at both ends."""
    return width if ss == 0 else 1.0 - width


def read_band_split(entry):
    """BOTH patches' band splits for one seam, as
    (pa_prop, pa_ss, pa_value, pb_prop, pb_ss, pb_value): which split
    property on each patch carves this seam's band, at which end, and what
    the value is now. A value the patch does not carry yet reads as the
    DEFAULT the blend would write (#64 leaves the patch's own split alone
    when there is one). Returns None when the pair shares no edge.

    The values are WIDTHS (distance from the seam, #70), not the raw
    parametric splits: a stored 0.9 at the parametric-1 end reads as the
    0.1-wide band it actually is. The stored USplits/VSplits keep their
    parametric meaning -- only the panel's display converts.

    Both were always here -- what #69 changes is not the read but what is
    DONE with it: the two halves were being collapsed into one spin box
    and one write, which quietly asserted that a seam has a single width.
    It does not; see band_side."""
    pa, pb = entry["patch_a"], entry["patch_b"]
    pa_prop, pa_ss = _side_of(pa, pb)
    pb_prop, pb_ss = _side_of(pb, pa)
    if pa_prop is None or pb_prop is None:
        return None

    def value(p, prop, ss):
        v = split_at_end(list(getattr(p, prop) or []), ss)
        v = DEFAULT_BAND[ss] if v is None else float(v)
        return _width_from_stored(v, ss)
    return (pa_prop, pa_ss, value(pa, pa_prop, pa_ss),
            pb_prop, pb_ss, value(pb, pb_prop, pb_ss))


def band_side(entry, which, read=None):
    """(patch, prop, ss, value) for ONE patch of the seam's band, or
    (None, None, None, None) when the pair shares no edge.

    `which` is BAND_A / BAND_B. Every read, write and validation goes
    through here, so "which patch is this editor about" is answered in
    exactly one place -- there is no second derivation to drift from the
    first, and no path that can validate a width against the patch the
    user did not edit."""
    if read is None:
        read = read_band_split(entry)
    if read is None:
        return None, None, None, None
    if which == BAND_A:
        return entry["patch_a"], read[0], read[1], read[2]
    if which == BAND_B:
        return entry["patch_b"], read[3], read[4], read[5]
    return None, None, None, None


def band_label(which):
    """How a band side is NAMED in a message. "patch A" would collide with
    a patch literally called A; "band A" and "band B" name the column."""
    return "band %s" % which


def write_band_split(entry, which, value):
    """Write `value` onto ONE patch's band split for this seam.

    Since #64 the blend READS the split rather than asserting a default,
    so this is the band width -- the panel's stand-in for a fillet
    radius. The patch keeps it on its own axis and at its own end, and
    #61 normalizes each list on set.

    ONE patch, and it is named (`which`) rather than implied: since #69 a
    seam carries two independently sized bands, so "write the width" no
    longer has a single object to mean. Touching only the target is what
    makes a refused edit on A leave B exactly as the user left it.

    One transaction -- one undo step per edit -- and it stays OUT of the
    confirm transaction, so a width edit is always undoable on its own."""
    p, prop, ss = band_side(entry, which)[:3]
    if p is None or prop is None:
        return False
    cur = list(getattr(p, prop) or [])
    old = split_at_end(cur, ss)
    new = [v for v in cur if old is None or v != old]
    # `value` is the width the user typed; the property stores the
    # parametric split at this end (#70).
    new = sorted(set(new + [_stored_from_width(float(value), ss)]))
    doc = entry["edge"].Document
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


def band_cell_problem(entry, which, value=None):
    """None when ONE patch's band for `value` is exactly ONE cell,
    otherwise a message naming that patch and the values that break it.

    Per-PATCH since #69. The count is a property of a single patch's
    split layout -- `along` intervals minus the corner cells, on that
    patch's own two axes -- so checking it against the pair was never
    more than checking each patch with a shared candidate. With one spin
    that was harmless. With two, applying one candidate to both would
    refuse a width that is perfectly good on the patch it was typed into
    because the OTHER patch happens to subdivide differently. So `which`
    is not a convenience: it is the only honest question to ask."""
    pa, pb = entry["patch_a"], entry["patch_b"]
    pa_prop, pa_ss = _side_of(pa, pb)
    pb_prop, pb_ss = _side_of(pb, pa)
    if pa_prop is None or pb_prop is None:
        return ("%s and %s share no edge, so there is no band to size"
                % (pa.Name, pb.Name))
    p, prop, ss = band_side(entry, which, (pa_prop, pa_ss, 0.0,
                                           pb_prop, pb_ss, 0.0))[:3]
    if p is None:
        return ("unknown band side %r" % (which,))
    # A seam along U fixes a V interval, so the band lives in VSplits:
    # the direction follows from the property, no second resolution.
    etype = ("U" if prop == "VSplits" else "V", ss)
    along_prop = "USplits" if prop == "VSplits" else "VSplits"

    cur = list(getattr(p, prop) or [])
    old = split_at_end(cur, ss)
    band = [v for v in cur if old is None or v != old]
    if value is not None:
        # `value` is a width; the layout is judged in parametric terms
        # (#70).
        band = sorted(set(band + [_stored_from_width(float(value), ss)]))
    along = list(getattr(p, along_prop) or [])
    n = _band_cell_count(along, band, etype, ss)
    if n != 1:
        return ("patch %s.%s = %s with %s = %s covers %d band cells "
                "(exactly 1 is required; multi-cell bands are not "
                "supported yet)"
                % (p.Name, prop, ["%g" % v for v in band],
                   along_prop, ["%g" % v for v in along], n))
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