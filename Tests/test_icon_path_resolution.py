"""Are the icons CWD-INDEPENDENT? Measured, not assumed (#54).

The defect this file was born from: SilkPatch defined TWO icon constants --
an absolute `iconPath` and a RELATIVE `ICON` -- and `PatchViewProvider.getIcon()`
returned the relative one. The toolbar was therefore always right while the
TREE followed the process working directory, which is what "sometimes this
occurs" looked like: whole launches right, whole launches wrong.

The fix is the module idiom every Silk icon path now follows: one absolute
constant, derived from `Silk_dummy.__file__`, used by BOTH `getIcon()` (the
tree) and `GetResources()['Pixmap']` (the button). This measures the two
things that decide it -- what the code returns, and whether Qt can load it
from a foreign working directory (which is what FreeCAD's tree does with
the string: `QPixmap(getIcon())`).

Since the owner's icon round (2026-10-25) the four workflow icons are
`SilkEdge.svg` / `SilkPatch.svg` / `SilkBlend.svg` / `SilkCorner.svg`, and
`Silk_Guide` wears `SilkGuide.svg`. Their DEDICATION is
`Tests/test_icon_dedication.py`'s contract; here only path resolution and
loadability are measured, from two working directories, for every one of
them.

_Findings ride in "errors" because that is what the runner prints.
Run: python3 Tests/run_all.py test_icon_path_resolution
"""

import os

import FreeCAD

# Qt lives under FreeCADGui here, not FreeCAD (ImportError otherwise).
from PySide import QtGui

from Tests.mcp_harness import check


SILK_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OTHER_CWD = "/home/mo"

# (label, module, class holding getIcon()) -- the four object types' tree
# icons, then the five commands' buttons.
TREE_ICONS = (
    ("Edge", "SilkEdge", "EdgeViewProvider"),
    ("Patch", "SilkPatch", "PatchViewProvider"),
    ("Blend", "SilkBlend", "BlendStripViewProvider"),
    ("Corner", "SilkCorner", "CornerBlendViewProvider"),
)
COMMAND_ICONS = (
    ("Silk_CreateEdge", "SilkEdge", "CreateEdge"),
    ("Silk_CreatePatch", "SilkPatch", "CreatePatch"),
    ("Silk_CreateBlend", "SilkBlend", "CreateBlend"),
    ("Silk_CreateCornerBlend", "SilkCorner", "CreateCornerBlend"),
    ("Silk_Guide", "SilkTaskPanel", "CreateGuide"),
)


def test_icon_path_resolution(doc):
    out, errors, checks = [], [], []
    was_cwd = os.getcwd()

    # try/finally, not best-effort: every os.chdir below is global to the
    # whole FreeCAD process, and the harness swallows per-test exceptions
    # (mcp_harness run_tests), so a raise mid-test would otherwise leak
    # the CWD into every subsequent test of the run.
    try:
        # ---- 1. what does each path resolver return? --------------------
        # getIcon does not touch self, so an unbound call is enough and
        # avoids building a throwaway document object.
        icons = []
        for label, module_name, class_name in TREE_ICONS:
            cls = getattr(__import__(module_name), class_name, None)
            if cls is None:
                check(False, "%s view provider class %s is MISSING"
                      % (label, class_name), errors)
                continue
            icon = cls.getIcon(object())
            icons.append(("%s tree" % label, icon))
            out.append("%-18s getIcon()  -> %-52s %s"
                       % (label, icon,
                          "ABSOLUTE" if os.path.isabs(icon) else "*** RELATIVE ***"))
            check(os.path.isabs(icon),
                  "%s getIcon() returns a RELATIVE path: %r" % (label, icon),
                  errors)

        for name, module_name, class_name in COMMAND_ICONS:
            pixmap = getattr(__import__(module_name),
                             class_name)().GetResources().get("Pixmap")
            icons.append(("%s button" % name, pixmap))
            out.append("%-18s Pixmap    -> %-52s %s"
                       % (name, pixmap,
                          "ABSOLUTE" if os.path.isabs(pixmap or "")
                          else "*** RELATIVE ***"))
            check(bool(pixmap) and os.path.isabs(pixmap),
                  "%s Pixmap is not an absolute path: %r" % (name, pixmap),
                  errors)

        # ---- 2. does Qt load every one of them, from each CWD? -----------
        # The invariant: an icon must render no matter where FreeCAD was
        # launched from -- for every type and every button, not just Patch.
        for cwd in (SILK_DIR, OTHER_CWD):
            os.chdir(cwd)
            failed = [label for label, path in icons
                      if not path or QtGui.QPixmap(path).isNull()]
            out.append("cwd=%-40s all %d icons load=%s%s"
                       % (cwd, len(icons), not failed,
                          "" if not failed else "  FAILED: %r" % (failed,)))
            check(not failed,
                  "icons that do not load from cwd=%s: %r" % (cwd, failed),
                  errors)

        os.chdir(OTHER_CWD)
        patch_path = dict(icons).get("Patch tree")
        checks.append("Patch icon resolves to %s and loads from %s: %s"
                      % (patch_path, OTHER_CWD,
                         not QtGui.QPixmap(patch_path).isNull()))
        return {"pass": not errors, "errors": errors, "checks": out + checks}
    finally:
        # restore the process CWD -- guaranteed even if an assertion (or
        # anything else) above raised.
        os.chdir(was_cwd)


ALL_TESTS = [test_icon_path_resolution]
