"""#88 -- the console-noise audit's two pins.

The audit is `Tests/console_noise_inventory.py` (MANUAL: it prints the
raw lines and the per-action counts).  This file is the part that has to
stay TRUE, so it is a test:

  * `test_inventory_is_reachable_and_instrumented` -- the instrument
    imports, exposes `main`, and carries `MANUAL`, the same contract the
    other manual measurement scripts carry.
  * `test_a_full_build_writes_no_legacy_class_banner` -- building the
    chain through the panel writes no "<Class> class Init" banner.  RED
    before the #88 reduction: the walk measured 44 of its 55 lines as
    `ArachNURBS.__init__` banners (8 on a patch, 12 on a blend, 25 on a
    corner), i.e. 80% of the wizard's volume was legacy scaffolding
    naming a class no user can act on.
  * `test_the_build_still_says_what_it_did` -- and the SIGNAL survives:
    the action lines (the created object's name, the refusal naming
    patch + property) are still written.  Removing noise must not remove
    the observability the headless tests rely on.

No continuity label is asserted anywhere.
"""

# --- manual tier ------------------------------------------------------
# This module's subject is an end-to-end rebuild / GUI drive /
# measurement sweep, so it is NOT in the default (fast) tier. Run it
# with `python3 Tests/run_all.py --manual` (or by name as a filter);
# Tests/test_manual_tier.py asserts it stays importable. See suite.py.
MANUAL = True

import FreeCAD

from FreeCAD import Gui

from Tests.mcp_harness import check
from Tests.test_patch_gui_command import _make_loop_edges
from Tests.test_seam_resolver import _line_sketch
from SilkTaskPanel import CreateGuide, SECTION_BLEND, SECTION_EDGE, \
    SECTION_PATCH, current_panel

_MANUAL_MODULES = ("Tests.console_noise_inventory",)


class _Capture:
    """Capture every Python-side console line, still forwarding it."""

    def __enter__(self):
        self.lines = []
        self._saved = {}
        for attr in ("PrintMessage", "PrintWarning", "PrintError"):
            orig = getattr(FreeCAD.Console, attr)
            self._saved[attr] = orig

            def make(orig=orig):
                def emit(msg):
                    self.lines.append(str(msg))
                    return orig(msg)
                return emit
            setattr(FreeCAD.Console, attr, make())
        return self

    def __exit__(self, *args):
        for attr, orig in self._saved.items():
            setattr(FreeCAD.Console, attr, orig)

    def banners(self):
        return [ln for ln in self.lines if "class Init" in ln]


def test_inventory_is_reachable_and_instrumented(doc):
    """The instrument exists, is importable, is MAIN-callable and is
    marked MANUAL -- so `Tests/suite.py` never collects it and the
    documented run command (`Tests/run_all.py console_noise_inventory`)
    finds it."""
    import importlib
    errors, checks = [], []
    for name in _MANUAL_MODULES:
        mod = importlib.import_module(name)
        check(getattr(mod, "MANUAL", None) is True,
              "%s does not carry MANUAL" % name, errors)
        check(callable(getattr(mod, "main", None)),
              "%s exposes no callable main" % name, errors)
        checks.append("%s: MANUAL + main()" % name)
    return {"pass": not errors, "errors": errors, "checks": checks}


def _panel_walk(doc, errors, sk_name):
    """Drive the wizard's four construction actions through the panel:
    one sketch -> Edge, four loop edges -> Patch, then a two-seam tube's
    blends -> Blend.  Returns (panel, lines) with the panel closed."""
    from Tests.test_seam_resolver import _build_tube

    def click(obj):
        Gui.Selection.clearSelection()
        Gui.Selection.addSelection(obj)

    sk = _line_sketch(doc, sk_name, [(100, 0, 0), (116.7, 0, 0),
                                     (133.3, 0, 0), (150, 0, 0)])
    edges = _make_loop_edges(doc)
    panel = None
    try:
        CreateGuide().Activated()
        panel = current_panel()
        if not check(panel is not None, "Activated left no panel open",
                     errors):
            return None
        panel.sections.open(SECTION_EDGE)
        click(sk)
        panel.panel_confirm()
        panel.sections.open(SECTION_PATCH)
        for e in edges:
            click(e)
        panel.panel_confirm()
        doc.recompute()
        # a real seam needs two patches: the tube shares two edges, so the
        # blend section has a row for each
        _pa, _pb, s_left, s_right = _build_tube(doc)
        panel.sections.open(SECTION_BLEND)
        panel.refresh() if hasattr(panel, "refresh") else None
        for seam in (s_left, s_right):
            row = panel.seam_row_index(seam)
            if row >= 0:
                panel.blend_table.cellClicked.emit(row, panel.COL_EDGE)
        panel.panel_confirm()
        doc.recompute()
        return panel
    finally:
        if panel is not None:
            try:
                panel.close_panel()
            except Exception:
                pass
        Gui.Control.closeDialog()
        import SilkTaskPanel
        SilkTaskPanel._open_panel = None
        Gui.Selection.clearSelection()


def test_a_full_build_writes_no_legacy_class_banner(doc):
    """Edge -> Patch -> Blend through the panel writes no `<Class> class
    Init` banner.  These are the legacy maths classes' `__init__` debug
    prints; the object the user acts on is the Patch / Blend / CornerBlend
    on top of them, so a line naming ControlPoly4_3L is volume with no
    action behind it."""
    errors, checks = [], []
    with _Capture() as cap:
        _panel_walk(doc, errors, "BannerLine")
    banners = cap.banners()
    check(not banners,
          "the build wrote %d legacy class banner(s), first %r"
          % (len(banners), banners[0] if banners else ""), errors)
    if not banners and not errors:
        checks.append("panel Edge+Patch+Blend build: 0 class-Init banners "
                      "among %d console line(s)" % len(cap.lines))
    return {"pass": not errors, "errors": errors, "checks": checks}


def test_the_build_still_says_what_it_did(doc):
    """The signal the noise audit must not take with it: the created
    objects are named on the console, and the blend says which seam it was
    created across -- the lines a headless run reads the action by."""
    errors, checks = [], []
    with _Capture() as cap:
        _panel_walk(doc, errors, "SignalLine")
    lines = "\n".join(cap.lines)
    check("Patch created: " in lines,
          "no line names the created Patch: %r" % lines, errors)
    check("created across" in lines,
          "no line says which seam the Blend was created across: %r"
          % lines, errors)
    if not errors:
        checks.append("action lines survive: 'Patch created: ...', "
                      "'... created across ...'")
    return {"pass": not errors, "errors": errors, "checks": checks}
