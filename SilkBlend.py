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

        # Ensure patches are up to date and will recompute their Shape with auto-hide
        pa.recompute()
        pb.recompute()

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
        # Split PERPENDICULAR to the shared edge
        sd_a = "V" if ea[0] == "U" else "U"  # VSplits if edge along U, USplits if edge along V
        sd_b = "V" if eb[0] == "U" else "U"
        ss_a = 0 if ea[1] == "0" else 1  # split near 0 or near 1 along the perpendicular direction
        ss_b = 0 if eb[1] == "0" else 1

        # Step 5: get subgrid strips (user must set USplits/VSplits on patches first)
        for p in (pa, pb):
            if not p.Proxy._subgrids:
                return  # no subdivisions — can't blend

        # Tell each patch which subgrid is being blended (for auto-hide)
        hide_a = 0 if ss_a == 0 else len(pa.Proxy._subgrids) - 1
        hide_b = 0 if ss_b == 0 else len(pb.Proxy._subgrids) - 1
        if not hasattr(pa, "_HideSubgridIdx"):
            pa.addProperty("App::PropertyInteger", "_HideSubgridIdx", "Internal",
                           "subgrid index hidden by blend")._HideSubgridIdx = hide_a
            pa.setEditorMode("_HideSubgridIdx", 1)
        else:
            pa._HideSubgridIdx = hide_a
        if not hasattr(pb, "_HideSubgridIdx"):
            pb.addProperty("App::PropertyInteger", "_HideSubgridIdx", "Internal",
                           "subgrid index hidden by blend")._HideSubgridIdx = hide_b
            pb.setEditorMode("_HideSubgridIdx", 1)
        else:
            pb._HideSubgridIdx = hide_b

        # Pick the correct subgrid: 0 if split near 0, -1 if split near 1
        sga = pa.Proxy._subgrids[0 if ss_a == 0 else -1]
        sgb = pb.Proxy._subgrids[0 if ss_b == 0 else -1]

        # Step 6: corner-to-parameter mapping
        cmap = {"U0": {0: 0, 1: 3}, "U1": {2: 3, 3: 0},
                "V0": {0: 0, 3: 3}, "V1": {1: 0, 2: 3}}

        # Step 7: blend each paired row/column
        # Subgraph flat = poles[U][V] = flat[U*4 + V]
        # If shared edge runs ALONG U (row): perpendicular = V → take COLUMNS (const U)
        # If shared edge runs ALONG V (col): perpendicular = U → take ROWS (const V)
        blend_poles = []
        for li in range(4):
            # Left strip: shared edge → inward, then reverse for outer→shared
            if ea[0] == "U":  # shared along U → take COLUMNS
                l_rev = list(reversed([sga[li * 4 + v] for v in range(4)]))
            else:  # shared along V → take ROWS
                l_rev = list(reversed([sga[u * 4 + li] for u in range(4)]))

            # Map left param index to right param index via corner pairs
            cmap = {"U0":{0:0,1:3},"U1":{2:3,3:0},"V0":{0:0,3:3},"V1":{1:0,2:3}}
            ri = 3 - li  # default: reversed
            for lc_idx, rc_idx in pairs:
                if li == cmap[ea][lc_idx]:
                    ri = cmap[eb][rc_idx]
                    break

            # Right strip: shared edge → inward (keep direction)
            if eb[0] == "U":  # shared along U → take COLUMNS
                rc = [sgb[ri * 4 + v] for v in range(4)]
            else:  # shared along V → take ROWS
                rc = [sgb[u * 4 + ri] for u in range(4)]

            res = AN.blend_poly_2x4_1x6(l_rev, [1.0] * 4, rc, [1.0] * 4,
                                        2.0, 2.0, 2.0, 2.0)
            blend_poles.append(res[0])

        fp.Poles = [p for row in blend_poles for p in row]
        fp.Weights = [w for row in [res[1] for _ in range(4)] for w in row]
        fp.Legs = AN.drawGrid(fp.Poles, 6)

        # Step 8: build blend surface using AN.CubicSurface_64
        if len(fp.Poles) != 24:
            return

        doc = fp.Document
        tmp_surf = doc.addObject("Part::FeaturePython", "_blend_surf_tmp")
        AN.CubicSurface_64(tmp_surf, fp)
        tmp_surf.recompute()
        surf_shape = tmp_surf.Shape
        doc.removeObject(tmp_surf.Name)

        if not surf_shape or not hasattr(surf_shape, "Faces") or not surf_shape.Faces:
            # Fallback: just show grid
            shapes = []
        else:
            shapes = [surf_shape]
            for leg in fp.Legs:
                if hasattr(leg, "toShape"):
                    try:
                        shapes.append(leg.toShape())
                    except Exception:
                        pass
        if shapes:
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
