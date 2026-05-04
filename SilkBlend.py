"""
SilkBlend — BlendStrip FeaturePython for joining two Patch44 objects along their shared edge.

Usage:
  1. Select two Patch44 objects
  2. Run Silk_CreateBlend command
  3. Blend auto-updates when patches' USplits/VSplits change
"""

import FreeCAD
import Part
from FreeCAD import Gui
import ArachNURBS as AN
from popup import tipsDialog

import os, Silk_dummy
path_Silk = os.path.dirname(Silk_dummy.__file__)
path_Silk_icons = os.path.join(path_Silk, "Resources", "Icons")
iconPath = path_Silk_icons + "/ControlGrid64_2Grid44.svg"


class BlendStrip:
    """FeaturePython: joins two Patch44 objects at their shared edge."""

    def __init__(self, obj, patch_a, patch_b):
        obj.addProperty("App::PropertyLink", "PatchA", "Inputs", "first patch").PatchA = patch_a
        obj.addProperty("App::PropertyLink", "PatchB", "Inputs", "second patch").PatchB = patch_b
        obj.addProperty("App::PropertyFloat", "tolerance", "Inputs",
                        "corner matching tolerance").tolerance = 0.01
        obj.addProperty("App::PropertyVectorList", "Poles", "Outputs", "blend grid poles").Poles
        obj.addProperty("App::PropertyFloatList", "Weights", "Outputs", "blend grid weights").Weights
        obj.addProperty("Part::PropertyGeometryList", "Legs", "Outputs", "grid segments").Legs
        obj.addProperty("App::PropertyString", "object_type", "", "").object_type = "BlendStrip"
        obj.setEditorMode("object_type", 1)
        obj.Proxy = self
        self._in_execute = False

    def onChanged(self, fp, prop):
        if self._in_execute:
            return
        if prop == "tolerance" or prop.startswith("Patch"):
            if 'Restore' not in fp.State and getattr(fp, "PatchA", None):
                fp.recompute()

    def execute(self, fp):
        if self._in_execute:
            return
        self._in_execute = True
        try:
            self._do_execute(fp)
        finally:
            self._in_execute = False

    def _do_execute(self, fp):
        pa, pb, tol = fp.PatchA, fp.PatchB, fp.tolerance
        if not pa or not pb:
            return

        # Step 1: ensure patches have subdivision
        for p in (pa, pb):
            if not p.Proxy._subgrids:
                p.USplits = [0.1]
                p.recompute()

        # Step 2: find shared corners
        a_c = [pa.Poles[0], pa.Poles[3], pa.Poles[15], pa.Poles[12]]
        b_c = [pb.Poles[0], pb.Poles[3], pb.Poles[15], pb.Poles[12]]
        pairs = []
        for i, ac in enumerate(a_c):
            for j, bc in enumerate(b_c):
                if (ac - bc).Length < tol:
                    pairs.append((i, j))
        if len(pairs) < 2:
            return

        # Step 3: determine edge type (U0/U1/V0/V1)
        edges = {(0, 1): "U0", (1, 2): "V1", (2, 3): "U1", (3, 0): "V0",
                 (1, 0): "U0", (2, 1): "V1", (3, 2): "U1", (0, 3): "V0"}
        ids_a = sorted(p[0] for p in pairs)
        ids_b = sorted(p[1] for p in pairs)
        ea = edges.get((ids_a[0], ids_a[1]))
        eb = edges.get((ids_b[0], ids_b[1]))
        if not ea or not eb:
            return

        # Step 4: set split direction and side
        dir_map = {"U": "V", "V": "U"}
        side_map = {"0": 0, "1": 1}
        sd_a = dir_map[ea[0]]
        sd_b = dir_map[eb[0]]
        ss_a = side_map[ea[1]]
        ss_b = side_map[eb[1]]

        # Ensure splits exist on the shared edge side
        for p, sd, ss in ((pa, sd_a, ss_a), (pb, sd_b, ss_b)):
            attr = f"{sd}Splits"
            current = list(getattr(p, attr))
            if ss == 0:
                if not current or current[0] > 0.1:
                    setattr(p, attr, [0.1])
                    p.recompute()
            else:
                if not current or current[-1] < 0.9:
                    setattr(p, attr, [0.9])
                    p.recompute()

        # Step 5: get subgrid strips
        def get_strip(p, sd, ss):
            sg = p.Proxy._subgrids
            return sg[0] if ss == 0 else sg[-1]

        sga = get_strip(pa, sd_a, ss_a)
        sgb = get_strip(pb, sd_b, ss_b)

        # Step 6: parameter mapping along shared edge
        # Corner index → parameter index (0 or 3)
        param_map = {"U0": {0: 0, 1: 3}, "U1": {2: 3, 3: 0},
                     "V0": {0: 0, 3: 3}, "V1": {1: 0, 2: 3}}
        pmap = {param_map[ea][i]: param_map[eb][j] for i, j in pairs}

        # Step 7: blend each paired row/column
        blend_poles = []
        for li in range(4):
            # Left strip: shared edge → inward, then reverse for outer→shared
            if sd_a == "U":  # shared edge along V, take rows
                l_rev = list(reversed([sga[u * 4 + li] for u in range(4)]))
            else:  # shared edge along U, take columns
                l_rev = list(reversed([sga[li * 4 + v] for v in range(4)]))

            ri = pmap.get(li, 3 - li)

            # Right strip: shared edge → inward (keep direction)
            if sd_b == "U":
                rc = [sgb[u * 4 + ri] for u in range(4)]
            else:
                rc = [sgb[ri * 4 + v] for v in range(4)]

            res = AN.blend_poly_2x4_1x6(l_rev, [1.0] * 4, rc, [1.0] * 4,
                                        2.0, 2.0, 2.0, 2.0)
            blend_poles.append(res[0])

        fp.Poles = [p for row in blend_poles for p in row]
        fp.Weights = [w for row in [res[1] for _ in range(4)] for w in row]
        fp.Legs = AN.drawGrid(fp.Poles, 6)

        # Step 8: build blend surface (6x4 grid → bicubic)
        if len(fp.Poles) != 24:
            return

        surf = Part.BSplineSurface()
        surf.increaseDegree(3, 3)
        for k, m in ((0.0, 4), (1.0 / 3.0, 3), (2.0 / 3.0, 3), (1.0, 4)):
            surf.insertUKnot(k, m, 1e-7)
        for k, m in ((0.0, 4), (1.0, 4)):
            surf.insertVKnot(k, m, 1e-7)
        for r in range(4):
            for c in range(6):
                idx = r * 6 + c
                surf.setPole(c + 1, r + 1, fp.Poles[idx], fp.Weights[idx])

        surf_shape = surf.toShape()
        shapes = [surf_shape]
        for leg in fp.Legs:
            if hasattr(leg, "toShape"):
                shapes.append(leg.toShape())
        try:
            fp.Shape = Part.Compound(shapes)
        except Exception:
            fp.Shape = surf_shape


class CreateBlendStrip:
    """GUI command — select 2 Patch44 objects → BlendStrip."""

    def GetResources(self):
        return {'Pixmap': iconPath, 'MenuText': 'Silk BlendStrip',
                'ToolTip': 'Create a blend strip between two adjacent Patch44 objects.'}

    def Activated(self):
        sel = Gui.Selection.getSelection()
        if len(sel) != 2:
            FreeCAD.Console.PrintError("Silk: BlendStrip requires exactly 2 selected Patch44 objects.\n")
            return
        doc = FreeCAD.ActiveDocument
        obj = doc.addObject("Part::FeaturePython", "BlendStrip")
        BlendStrip(obj, sel[0], sel[1])
        obj.ViewObject.Proxy = 0
        obj.ViewObject.LineWidth = 2.00
        obj.ViewObject.LineColor = (0.00, 1.00, 0.00)
        obj.ViewObject.PointSize = 5.00
        obj.ViewObject.DisplayMode = "Shaded"
        obj.ViewObject.ShapeColor = (0.00, 1.00, 0.00)
        obj.ViewObject.Transparency = 30
        doc.recompute()
        FreeCAD.Console.PrintMessage(f"BlendStrip created: {obj.Name}\n")

    def IsActive(self):
        return Gui is not None


Gui.addCommand("Silk_CreateBlend", CreateBlendStrip())
