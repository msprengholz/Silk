"""The four workflow commands wear the OWNER'S icons, and no two buttons twin.

`Resources/Icons/new/` (the owner's own SVGs, 2026-10-25) is now THE workflow
set, and the legacy pile the wizard used to borrow from is gone. The mapping
is pinned here, in process order:

    Silk_CreateEdge        -> Resources/Icons/SilkEdge.svg
    Silk_CreatePatch       -> Resources/Icons/SilkPatch.svg   (his SinglePatch)
    Silk_CreateBlend       -> Resources/Icons/SilkBlend.svg   (his edgeblend)
    Silk_CreateCornerBlend -> Resources/Icons/SilkCorner.svg  (his cornerblend)
    Silk_Guide             -> Resources/Icons/SilkGuide.svg  (its own wand)

This test is the contract for that, and it keeps the #54/#94/#96 habit: two
toolbar entries wearing the same picture is the defect. So it asserts

  1. every workflow command's Pixmap is an absolute path to an existing file
     under Resources/Icons, and it is THE file named above -- the four are
     four distinct icons, one per step;
  2. `Silk_Guide` is its own file and specifically NOT the workbench's
     `Silk.svg`;
  3. NO VISIBLE command (`InitGui.Silk.VISIBLE_COMMANDS`: the four workflow
     names, `Silk_Guide` and the dev `Reload_Silk`, spelled out here
     independently) shares another's Pixmap, and `Silk_CornerFill` -- the
     extra registered command that stands beside the corner blend -- is
     distinct from the corner blend's too;
  4. the four object types' TREE icons are that same set (a Patch is not a
     Blend, a corner is not a control grid), absolute and existing;
  5. each of those icons loads through QPixmap from a foreign working
     directory (how the tree and the toolbar actually render it), and each
     has its `.png` preview beside it (128 px, the size the #54 family's
     previews are, `rsvg-convert -w 128 -h 128`);
  6. the distinctness check is not vacuous: handed two commands wearing one
     icon, the same helper that passes above names the twin.

Mutation (measured, not asserted in-line): pointing `SilkPatch.iconPath` at
`SilkCorner.svg` turns this test RED on the pinned mapping AND on the twin
check; reverting it turns it green again.

This is additive to Tests/test_icon_path_resolution.py (CWD independence) --
it does not replace that guard.

Run: python3 Tests/run_all.py test_icon_dedication
"""

import os

import FreeCAD

# Qt lives under FreeCADGui here, not FreeCAD (ImportError otherwise).
from PySide import QtGui

from Tests.mcp_harness import check


OTHER_CWD = "/home/mo"

# (command, module, command class, expected icon file). Spelled out
# independently of the modules' own constants, so a typo in a module cannot
# make this test agree with itself.
WORKFLOW_COMMANDS = (
    ("Silk_CreateEdge", "SilkEdge", "CreateEdge", "SilkEdge.svg"),
    ("Silk_CreatePatch", "SilkPatch", "CreatePatch", "SilkPatch.svg"),
    ("Silk_CreateBlend", "SilkBlend", "CreateBlend", "SilkBlend.svg"),
    ("Silk_CreateCornerBlend", "SilkCorner", "CreateCornerBlend",
     "SilkCorner.svg"),
)
GUIDE_COMMAND = ("Silk_Guide", "SilkTaskPanel", "CreateGuide", "SilkGuide.svg")
# The dev command is visible too, so it takes part in the twin check; its
# icon is NOT part of this ticket, so only its distinctness is asserted.
DEV_COMMAND = ("Reload_Silk", "Reload_Silk", "Reload_Silk", None)

# The four object types' tree icons (#54): the same files the commands wear.
VIEW_PROVIDERS = (
    ("Edge", "SilkEdge", "EdgeViewProvider", "SilkEdge.svg"),
    ("Patch", "SilkPatch", "PatchViewProvider", "SilkPatch.svg"),
    ("Blend", "SilkBlend", "BlendStripViewProvider", "SilkBlend.svg"),
    ("Corner", "SilkCorner", "CornerBlendViewProvider", "SilkCorner.svg"),
)

# `Silk_CornerFill` is registered but NOT visible (#96 D3, revoked
# 2026-10-21); it still stands beside the corner blend whenever a script
# reaches for it, so it must not wear the same picture (#96).
FILL_COMMAND = ("Silk_CornerFill", "SilkCorner", "CreateCornerFill")


def _twins(rows):
    """The basenames worn by more than one entry: [] means all dedicated.

    `rows` is [(label, pixmap), ...]. Empty pixmaps are skipped by the
    callers' own absolute/existing checks -- a missing icon is not a twin.
    """
    seen, twins = {}, []
    for label, pixmap in rows:
        base = os.path.basename(pixmap) if pixmap else ""
        if not base:
            continue
        if base in seen:
            twins.append((seen[base], label, base))
        else:
            seen[base] = label
    return twins


def _resources(module_name, class_name):
    """A command's GetResources(), through its own class."""
    mod = __import__(module_name)
    return getattr(mod, class_name)().GetResources()


def test_icon_dedication(doc):
    out, errors, checks = [], [], []
    was_cwd = os.getcwd()

    try:
        # ---- 1. the four workflow commands, pinned to their own icons ----
        command_icons = []
        for name, module_name, class_name, expected in WORKFLOW_COMMANDS:
            resources = _resources(module_name, class_name)
            pixmap = resources.get("Pixmap")
            command_icons.append((name, pixmap))
            out.append("%-24s -> %s" % (name, pixmap))
            check(bool(pixmap) and os.path.isabs(pixmap),
                  "%s Pixmap is not an absolute path: %r" % (name, pixmap),
                  errors)
            check(bool(pixmap) and os.path.isfile(pixmap),
                  "%s icon file does not exist: %r" % (name, pixmap), errors)
            check(os.path.basename(pixmap or "") == expected,
                  "%s wears %r, expected %r" % (name,
                                                os.path.basename(pixmap or ""),
                                                expected), errors)
            check(bool(pixmap)
                  and os.path.basename(os.path.dirname(pixmap) or "")
                  == "Icons",
                  "%s icon is not under Resources/Icons: %r" % (name, pixmap),
                  errors)

        # ---- 2. the guide button: its own file, not the workbench's ----
        guide_resources = _resources(GUIDE_COMMAND[1], GUIDE_COMMAND[2])
        guide = guide_resources.get("Pixmap")
        command_icons.append((GUIDE_COMMAND[0], guide))
        out.append("%-24s -> %s" % (GUIDE_COMMAND[0], guide))
        check(bool(guide) and os.path.isabs(guide),
              "Silk_Guide Pixmap is not an absolute path: %r" % (guide,),
              errors)
        check(bool(guide) and os.path.isfile(guide),
              "Silk_Guide icon file does not exist: %r" % (guide,), errors)
        check(os.path.basename(guide or "") == GUIDE_COMMAND[3],
              "Silk_Guide wears %r, expected %r"
              % (os.path.basename(guide or ""), GUIDE_COMMAND[3]), errors)
        check(os.path.basename(guide or "") != "Silk.svg",
              "Silk_Guide borrows the workbench icon Silk.svg: %r" % (guide,),
              errors)

        # ---- 3. no visible command twins another -------------------------
        dev_resources = _resources(DEV_COMMAND[1], DEV_COMMAND[2])
        dev = dev_resources.get("Pixmap")
        command_icons.append((DEV_COMMAND[0], dev))
        out.append("%-24s -> %s" % (DEV_COMMAND[0], dev))
        check(bool(dev) and os.path.isabs(dev) and os.path.isfile(dev),
              "Reload_Silk Pixmap is not an existing absolute icon: %r"
              % (dev,), errors)

        twins = _twins(command_icons)
        out.append("distinct Pixmaps over the %d visible commands: %s"
                   % (len(command_icons), not twins))
        check(not twins, "visible commands share a Pixmap: %r" % (twins,),
              errors)

        fill_resources = _resources(FILL_COMMAND[1], FILL_COMMAND[2])
        fill = fill_resources.get("Pixmap")
        out.append("%-24s -> %s" % (FILL_COMMAND[0], fill))
        check(bool(fill) and os.path.isabs(fill) and os.path.isfile(fill),
              "Silk_CornerFill Pixmap is not an existing absolute icon: %r"
              % (fill,), errors)
        fill_twins = _twins(command_icons + [(FILL_COMMAND[0], fill)])
        check(not fill_twins,
              "Silk_CornerFill shares a Pixmap with a visible command: %r"
              % (fill_twins,), errors)

        # ---- 4. the tree icons are that same dedicated set (#54) ---------
        tree_icons = []
        for label, module_name, class_name, expected in VIEW_PROVIDERS:
            cls = getattr(__import__(module_name), class_name, None)
            if cls is None:
                check(False, "%s view provider class %s is MISSING"
                      % (label, class_name), errors)
                continue
            icon = cls.getIcon(object())
            tree_icons.append((label, icon))
            out.append("%-7s tree icon    -> %s" % (label, icon))
            check(bool(icon) and os.path.isabs(icon),
                  "%s getIcon() returns a relative path: %r" % (label, icon),
                  errors)
            check(bool(icon) and os.path.isfile(icon),
                  "%s tree icon does not exist: %r" % (label, icon), errors)
            check(os.path.basename(icon or "") == expected,
                  "%s tree icon is %r, expected %r"
                  % (label, os.path.basename(icon or ""), expected), errors)
        tree_twins = _twins(tree_icons)
        check(not tree_twins,
              "two object types share a tree icon: %r" % (tree_twins,), errors)

        # ---- 5. they load from a foreign cwd, and carry their previews ---
        previews = []
        os.chdir(OTHER_CWD)
        for label, pixmap in command_icons + [(FILL_COMMAND[0], fill)]:
            if not pixmap:
                continue
            loaded = not QtGui.QPixmap(pixmap).isNull()
            check(loaded, "%s icon does not load from a foreign cwd: %r"
                  % (label, pixmap), errors)
            preview = os.path.splitext(pixmap)[0] + ".png"
            preview_ok = (os.path.isfile(preview)
                          and not QtGui.QPixmap(preview).isNull())
            check(preview_ok, "%s has no loadable .png preview: %r"
                  % (label, preview), errors)
            if preview_ok:
                size = QtGui.QPixmap(preview).size()
                previews.append("%s %dx%d" % (os.path.basename(preview),
                                              size.width(), size.height()))
        out.append("previews: %s" % ", ".join(previews))
        out.append("every icon loads from cwd=%s: yes" % OTHER_CWD)

        # ---- 6. the twin check is not vacuous ----------------------------
        # Two commands wearing ONE icon -- exactly the defect above -- must be
        # named by the same helper that just passed. A distinctness check that
        # cannot fail is not evidence (the #54/#94 lesson).
        planted = _twins([(WORKFLOW_COMMANDS[0][0], command_icons[1][1]),
                          (WORKFLOW_COMMANDS[1][0], command_icons[1][1])])
        if planted:
            out.append("MUTATION CONTROL: the identical icon now reports %r"
                       % (planted,))
        check(bool(planted),
              "the twin check does not report two commands wearing one icon "
              "-- it cannot fail, so the green above is not evidence",
              errors)

        checks.append("workflow icons: %s"
                      % ", ".join("%s=%s" % (n, os.path.basename(p or ""))
                                  for n, p in command_icons))
        return {"pass": not errors, "errors": errors, "checks": out + checks}
    finally:
        os.chdir(was_cwd)


ALL_TESTS = [test_icon_dedication]
