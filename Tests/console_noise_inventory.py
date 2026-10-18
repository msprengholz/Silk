"""#88 -- console-noise inventory across the workbench actions (MANUAL).

An INVENTORY instrument, not a test.  It taps the three Python-side
console writers -- `FreeCAD.Console.PrintMessage` / `PrintWarning` /
`PrintError` -- and attributes every line to the ACTION that was running
and to the writer that emitted it, then drives a scripted walk through
the wizard (the same panel calls `Tests/test_task_panel.py` drives) and
prints the raw lines plus two groupings: per action, and per writer.

Scope of the instrument, deliberately: this captures the PYTHON writers
only.  A message emitted inside C++ (the Report View path the expression
engine uses, #74) never reaches these attributes.  The inventory is
therefore "every line Silk writes", which is exactly the noise question;
it is not "every line the Report View shows".

MANUAL-ONLY: the file name is not `test_*.py`, so `Tests/suite.py` does
not collect it.  `Tests/test_console_noise.py` asserts this module
imports, exposes `main`, and carries `MANUAL`.

Run:
    python3 Tests/run_all.py console_noise_inventory
"""

import sys

import FreeCAD

MANUAL = True

_THIS = __name__


class _Tap:
    """Record every Python-side console line as (action, level, writer,
    text).  `writer` is the first Silk frame outside this file, i.e. the
    function that actually decided to print."""

    _LEVELS = (("PrintMessage", "message"), ("PrintWarning", "warning"),
               ("PrintError", "error"))

    def __init__(self):
        self.records = []
        self.action = "startup"

    def act(self, name):
        self.action = name
        return self

    def _writer(self):
        frame = sys._getframe(2)
        while frame is not None and frame.f_globals.get("__name__") == _THIS:
            frame = frame.f_back
        if frame is None:
            return "?"
        return "%s.%s" % (frame.f_globals.get("__name__", "?"),
                          frame.f_code.co_name)

    def _record(self, level, orig):
        def emit(msg):
            self.records.append((self.action, level, self._writer(), msg))
            return orig(msg)
        return emit

    def __enter__(self):
        self._orig = {}
        for attr, level in self._LEVELS:
            orig = getattr(FreeCAD.Console, attr)
            self._orig[attr] = orig
            setattr(FreeCAD.Console, attr, self._record(level, orig))
        return self

    def __exit__(self, *args):
        for attr, _level in self._LEVELS:
            setattr(FreeCAD.Console, attr, self._orig[attr])

    # ---- the two groupings -------------------------------------------

    def by_action(self):
        out = {}
        for action, level, _writer, text in self.records:
            row = out.setdefault(action, {"message": 0, "warning": 0,
                                          "error": 0})
            row[level] += 1
        return out

    def by_writer(self):
        out = {}
        for _action, level, writer, _text in self.records:
            out.setdefault(writer, {"message": 0, "warning": 0,
                                    "error": 0})[level] += 1
        return out


def _script(doc):
    """Drive the walk and return (tap, facts).  Split from `main` so the
    steps are readable and the measurement is one call."""
    from FreeCAD import Gui
    from SilkTaskPanel import (BAND_A, BAND_B, CreateGuide, current_panel,
                               SECTION_BLEND, SECTION_CORNER, SECTION_EDGE,
                               SECTION_PATCH, band_side, write_band_split)
    import Tests.corner_model as cm
    from Tests.test_patch_gui_command import _make_loop_edges
    from Tests.test_seam_resolver import _build_tube, _line_sketch

    facts = {}
    tap = _Tap()

    def click(obj):
        Gui.Selection.clearSelection()
        Gui.Selection.addSelection(obj)

    def close(panel):
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

    with tap:
        # ---- 1. panel open (the wizard itself) ---------------------
        tap.act("panel open")
        CreateGuide().Activated()
        panel = current_panel()
        facts["panel"] = panel is not None

        # ---- 2. Edge confirm ---------------------------------------
        tap.act("edge confirm")
        sk = _line_sketch(doc, "NoiseLine", [(100, 0, 0), (116.7, 0, 0),
                                             (133.3, 0, 0), (150, 0, 0)])
        panel.sections.open(SECTION_EDGE)
        click(sk)
        made_edge = panel.panel_confirm()
        facts["edge"] = bool(made_edge)

        # ---- 3. Patch confirm --------------------------------------
        tap.act("patch confirm")
        loop = _make_loop_edges(doc)
        panel.sections.open(SECTION_PATCH)
        for e in loop:
            click(e)
        made_patch = panel.panel_confirm()
        doc.recompute()
        facts["patch"] = bool(made_patch)
        close(panel)

        # ---- 4. Blend confirm (a two-seam tube: 2 blends, one step)
        tap.act("blend confirm")
        pa, pb, s_left, s_right = _build_tube(doc)
        panel = current_panel()
        if panel is None:
            CreateGuide().Activated()
            panel = current_panel()
        panel.sections.open(SECTION_BLEND)
        for e in (s_left, s_right):
            row = panel.seam_row_index(e)
            panel.blend_table.cellClicked.emit(row, panel.COL_EDGE)
        panel.panel_confirm()
        doc.recompute()
        blends = [o for o in doc.Objects
                  if getattr(o, "object_type", "") == "Blend"]
        facts["blends"] = len(blends)

        # ---- 5. band edit (both bands, a legal width each) ---------
        tap.act("band edit")
        for e in (s_left, s_right):
            for which in (BAND_A, BAND_B):
                spin = panel.split_editor(e, which)
                if spin is not None:
                    spin.setValue(0.25)
                    spin.editingFinished.emit()
        doc.recompute()
        facts["band_edits"] = "2 seams x 2 bands at 0.25"

        # ---- 6. refused band width (outside (0, 1)) ----------------
        tap.act("band edit refused")
        victim_blend = next((b for b in blends
                             if getattr(b, "Edge", None) is s_left), None)
        entry = {"edge": s_left, "patch_a": pa, "patch_b": pb,
                 "status": "blended", "blend": victim_blend}
        for which in (BAND_A, BAND_B):
            write_band_split(entry, which, 1.0)
        facts["band_refusal"] = "width 1.0 on both bands"
        close(panel)

        # ---- 7. corner confirm (the 4-ring fixture) ----------------
        tap.act("corner confirm")
        cm.build_corner_model(doc)
        strips = [doc.getObject(n) for n in ("B12", "B24", "B43", "B31")]
        CreateGuide().Activated()
        panel = current_panel()
        panel.sections.open(SECTION_CORNER)
        for s in strips:
            click(s)
        panel.panel_confirm()
        doc.recompute()
        facts["corners"] = len([o for o in doc.Objects
                                if getattr(o, "object_type", "")
                                == "CornerBlend"])
        close(panel)

        # ---- 8. delete cascade (a patch goes, the blend cascades) --
        tap.act("delete cascade")
        victim = doc.getObject("TubeA")
        if victim is not None:
            doc.removeObject(victim.Name)
            doc.recompute()
        facts["cascade"] = True

    return tap, facts


def main(doc=None):
    """Build a scratch document, run the walk, print the inventory."""
    own = doc is None
    if own:
        doc = FreeCAD.newDocument("ConsoleNoiseInventory")
    Gui = getattr(FreeCAD, "Gui", None)
    if Gui is None:
        raise RuntimeError("the panel walk needs the FreeCAD GUI")
    try:
        tap, facts = _script(doc)
    finally:
        try:
            import SilkTaskPanel
            SilkTaskPanel._open_panel = None
        except Exception:
            pass
        if own:
            FreeCAD.closeDocument(doc.Name)

    print("=" * 72)
    print("#88 console-noise inventory -- scripted wizard walk")
    print("=" * 72)
    print("facts: %r" % (facts,))
    print("total lines: %d (message %d, warning %d, error %d)"
          % (len(tap.records),
             sum(1 for r in tap.records if r[1] == "message"),
             sum(1 for r in tap.records if r[1] == "warning"),
             sum(1 for r in tap.records if r[1] == "error")))
    print("")
    print("-- per action " + "-" * 58)
    for action, row in tap.by_action().items():
        print("%-24s message %3d  warning %3d  error %3d  (total %3d)"
              % (action, row["message"], row["warning"], row["error"],
                 sum(row.values())))
    print("")
    print("-- per writer " + "-" * 58)
    for writer, row in sorted(tap.by_writer().items()):
        print("%-44s message %3d  warning %3d  error %3d"
              % (writer, row["message"], row["warning"], row["error"]))
    print("")
    print("-- raw lines " + "-" * 58)
    for i, (action, level, writer, text) in enumerate(tap.records, 1):
        print("%3d [%-20s] %-6s %-34s %s"
              % (i, action, level, writer,
                 text.replace("\n", " ")[:110]))
    return {"pass": True, "errors": [], "checks": [
        "%d console lines over %d actions" % (len(tap.records),
                                              len(tap.by_action())),
        "facts: %r" % (facts,)]}
