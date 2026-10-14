"""Is the Patch tree icon CWD-dependent? Measured, not assumed.

SilkPatch defines TWO icon constants:

    iconPath = path_Silk_icons + "/ControlGridPatch.svg"   # absolute, from
                                                           # Silk_dummy.__file__
    ICON     = "Resources/Icons/ControlGridPatch.svg"      # RELATIVE

`PatchViewProvider.getIcon()` returns ICON (relative). SilkEdge, SilkBlend and
SilkCorner all return their absolute `iconPath` instead. The command's Pixmap
uses the absolute one, so the TOOLBAR is always right while the TREE follows
the process working directory -- which is what "sometimes this occurs" would
look like: whole launches right, whole launches wrong.

This measures the two things that decide it:
  1. what getIcon() actually returns for each object type;
  2. whether QtGui.QPixmap -- what FreeCAD's tree builds from that string --
     can load it, from two different working directories.

_Findings ride in "errors" because that is what the runner prints.
Run: python3 Tests/run_all.py test_icon_path_resolution
"""

import os

import FreeCAD

# Qt lives under FreeCADGui here, not FreeCAD (ImportError otherwise).
from PySide import QtGui


SILK_DIR = "/home/mo/.local/share/FreeCAD/v1-1/Mod/Silk"
OTHER_CWD = "/home/mo"


def test_icon_path_resolution(doc):
    out = []
    checks = []
    was_cwd = os.getcwd()

    # ---- 1. what does each getIcon() return? -------------------------
    # try/finally, not best-effort: every os.chdir below is global to the
    # whole FreeCAD process, and the harness swallows per-test exceptions
    # (mcp_harness run_tests), so a raise mid-test would otherwise leak
    # the CWD into every subsequent test of the run.
    try:
        import SilkEdge, SilkPatch, SilkBlend, SilkCorner

        mods = [("Edge", SilkEdge, "EdgeViewProvider"),
                ("Patch", SilkPatch, "PatchViewProvider"),
                ("Blend", SilkBlend, "BlendStripViewProvider"),
                ("Corner", SilkCorner, "CornerBlendViewProvider")]

        icons = {}
        for label, mod, clsname in mods:
            cls = getattr(mod, clsname, None)
            if cls is None:
                out.append("%-7s view provider class %s MISSING" % (label, clsname))
                continue

            # getIcon does not touch self, so an unbound call is enough and
            # avoids building a throwaway document object.
            icon = cls.getIcon(object())
            icons[label] = icon
            out.append("%-7s getIcon -> %-58s %s"
                       % (label, icon,
                          "ABSOLUTE" if os.path.isabs(icon) else "*** RELATIVE ***"))
            checks.append(("%s icon is absolute" % label,
                           os.path.isabs(icon) is True,
                           icon))

        patch_icon = icons.get("Patch")
        if not patch_icon:
            return {"pass": False, "errors": out, "checks": checks}

        # ---- 2. does Qt actually load it, from each CWD? -----------------
        rel = patch_icon
        abspath = SilkPatch.iconPath
        for cwd in (SILK_DIR, OTHER_CWD):
            os.chdir(cwd)
            pm_rel = QtGui.QPixmap(rel)
            pm_abs = QtGui.QPixmap(abspath)
            out.append("cwd=%-44s getIcon() loads=%-5s  iconPath loads=%s"
                       % (cwd, not pm_rel.isNull(), not pm_abs.isNull()))

        # what FreeCAD's tree does is: QPixmap(getIcon()).
        os.chdir(OTHER_CWD)
        rel_ok_foreign = not QtGui.QPixmap(rel).isNull()
        abs_ok_foreign = not QtGui.QPixmap(abspath).isNull()
        os.chdir(SILK_DIR)
        rel_ok_silk = not QtGui.QPixmap(rel).isNull()

        out.append("")
        out.append("getIcon() returns a %s path: %s"
                   % ("RELATIVE" if not os.path.isabs(rel) else "absolute", rel))
        if not os.path.isabs(rel):
            out.append("iconPath (what the TOOLBAR Pixmap uses) is absolute: %s"
                       % abspath)

        # The invariant: the tree icon must render no matter where FreeCAD was
        # launched from. Currently violated for Patch -- this check is RED until
        # getIcon() returns an absolute path.
        checks.append(("Patch tree icon loads regardless of the working directory",
                       rel_ok_foreign is True, rel_ok_foreign))
        checks.append(("Patch icon path loads from the Silk directory",
                       rel_ok_silk is True, rel_ok_silk))
        checks.append(("Patch iconPath (toolbar) loads from a foreign directory",
                       abs_ok_foreign is True, abs_ok_foreign))

        return {"pass": all(c[1] for c in checks), "errors": out, "checks": checks}
    finally:
        # restore the process CWD -- guaranteed even if an assertion (or
        # anything else) above raised.
        os.chdir(was_cwd)


ALL_TESTS = [test_icon_path_resolution]
