"""Ticket #54: Patch and Blend each get a DISTINCT, dedicated tree icon.

Before #54 the Patch view provider reused `ControlGridPatch.svg` -- a
ControlGrid-family icon shared with legacy objects -- so a unified Patch was
indistinguishable from the control-grid family in the tree. This test pins the
new contract:

  1. every object type's getIcon() returns an ABSOLUTE path to an EXISTING file;
  2. the Patch icon is NOT one of the ControlGrid-family SVGs;
  3. Patch and Blend resolve to mutually distinct files;
  4. the dedicated icons actually load through QPixmap (how the tree renders
     them) from a foreign working directory.

This is additive to Tests/test_icon_path_resolution.py (CWD independence) --
it does not replace that guard.

Run: python3 Tests/run_all.py test_icon_dedication
"""

import os

import FreeCAD

# Qt lives under FreeCADGui here, not FreeCAD (ImportError otherwise).
from PySide import QtGui


CONTROL_GRID_FAMILY = (
    "ControlGridPatch.svg",
    "ControlGrid44.svg",
    "ControlGrid64.svg",
    "ControlGrid66.svg",
    "ControlGrid3Star66_3Sub.svg",
    "ControlGrid5Star66_5Sub.svg",
    "ControlGrid64_2Grid44.svg",
    "ControlGrid64_3_1Grid44.svg",
    "ControlGrid64_Surf44.svg",
    "ControlGridNStar66.svg",
    "ControlGrid44_EdgeSegment.svg",
    "ControlGrid44_2EdgeSegments.svg",
)

OTHER_CWD = "/home/mo"


def test_icon_dedication(doc):
    out = []
    checks = []
    was_cwd = os.getcwd()

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
                checks.append(("%s view provider class present" % label,
                               False, clsname))
                continue
            icon = cls.getIcon(object())
            icons[label] = icon
            out.append("%-7s getIcon -> %s" % (label, icon))

        # 1. absolute + existing, for every type
        for label in ("Edge", "Patch", "Blend", "Corner"):
            p = icons.get(label)
            checks.append(("%s getIcon returns an absolute path" % label,
                           bool(p) and os.path.isabs(p), p))
            checks.append(("%s icon file exists under Resources/Icons" % label,
                           bool(p) and os.path.isfile(p), p))

        # 2. Patch has a DEDICATED icon, not a ControlGrid-family file
        patch = icons.get("Patch")
        checks.append(("Patch icon is not a ControlGrid-family SVG",
                       bool(patch) and os.path.basename(patch)
                       not in CONTROL_GRID_FAMILY, patch))

        # 3. Patch and Blend are mutually distinct files
        blend = icons.get("Blend")
        checks.append(("Patch and Blend icons are distinct files",
                       bool(patch) and bool(blend)
                       and os.path.basename(patch) != os.path.basename(blend),
                       "%s vs %s" % (patch, blend)))

        # 4. the dedicated icons load via QPixmap from a foreign cwd
        os.chdir(OTHER_CWD)
        for label in ("Edge", "Patch", "Blend"):
            p = icons.get(label)
            if not p:
                continue
            pm = QtGui.QPixmap(p)
            checks.append(("%s icon loads from a foreign cwd via QPixmap"
                           % label, not pm.isNull(), p))
            out.append("%-7s loads from foreign cwd: %s" % (label, not pm.isNull()))

        return {"pass": all(c[1] for c in checks), "errors": out,
                "checks": checks}
    finally:
        os.chdir(was_cwd)


ALL_TESTS = [test_icon_dedication]
