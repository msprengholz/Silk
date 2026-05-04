#    This file is part of Silk
#    (c) 2025
#
#    NURBS Surface modeling tools focused on low degree and seam continuity (FreeCAD Workbench)
#
#    Patch44 — single FeaturePython combining ControlGrid44 + CubicSurface_44 + subgrids.

import FreeCAD
import Part
from FreeCAD import Gui
import ArachNURBS as AN
from popup import tipsDialog

import os, Silk_dummy
path_Silk = os.path.dirname(Silk_dummy.__file__)
path_Silk_icons = os.path.join(path_Silk, "Resources", "Icons")
iconPath = path_Silk_icons + "/ControlGrid44.svg"


def _normalize_splits(values):
    return sorted(set(v for v in values if 0.0 < v < 1.0))


def _build_intervals(values):
    splits = _normalize_splits(list(values))
    if not splits:
        return [(0.0, 1.0)]
    return list(zip([0.0] + splits, splits + [1.0]))


class Patch44:
    def __init__(self, obj, poly0, poly1, poly2, poly3):
        latest_version = "0.01"
        obj.addProperty("App::PropertyLink", "Poly0", "C1 - Inputs", "first boundary edge").Poly0 = poly0
        obj.addProperty("App::PropertyLink", "Poly1", "C1 - Inputs", "second boundary edge").Poly1 = poly1
        obj.addProperty("App::PropertyLink", "Poly2", "C1 - Inputs", "third boundary edge").Poly2 = poly2
        obj.addProperty("App::PropertyLink", "Poly3", "C1 - Inputs", "fourth boundary edge").Poly3 = poly3
        obj.addProperty("App::PropertyFloat", "tolerance", "C1 - Inputs",
                        "endpoint matching tolerance").tolerance = AN.default_tol
        obj.addProperty("App::PropertyBool", "reverse", "C1 - Inputs",
                        "reverse the grid parameter direction").reverse = False
        obj.addProperty("App::PropertyFloatList", "USplits", "S1 - Subdivision",
                        "U split parameters (0-1)").USplits = []
        obj.addProperty("App::PropertyFloatList", "VSplits", "S1 - Subdivision",
                        "V split parameters (0-1)").VSplits = []
        obj.addProperty("App::PropertyBool", "ShowSurface", "S2 - Display",
                        "show the surface").ShowSurface = True
        obj.addProperty("App::PropertyBool", "ShowGrid", "S2 - Display",
                        "show the control grid").ShowGrid = True
        obj.addProperty("App::PropertyBool", "ShowSubgrids", "S2 - Display",
                        "show subdivided subgrids instead of base surface").ShowSubgrids = False
        obj.addProperty("App::PropertyVectorList", "Poles", "C2 - Outputs", "Poles").Poles
        obj.addProperty("App::PropertyFloatList", "Weights", "C2 - Outputs", "Weights").Weights
        obj.addProperty("Part::PropertyGeometryList", "Legs", "C2 - Outputs", "grid segments").Legs
        obj.addProperty("App::PropertyString", "object_type", "C3 - Identifiers",
                        "workbench class").object_type = "Patch44"
        obj.setEditorMode("object_type", 1)
        obj.addProperty("App::PropertyString", "object_version", "C3 - Identifiers",
                        "class version").object_version = latest_version
        obj.setEditorMode("object_version", 1)
        obj.addProperty("App::PropertyString", "internalName", "C3 - Identifiers",
                        "permanent internal FreeCAD name").internalName = obj.Name
        obj.setEditorMode("internalName", 1)
        obj.Proxy = self
        self._subgrids = []
        self._subsurfaces = []
        self._base_surface = None

    def onDocumentRestored(self, obj):
        obj.recompute()

    def onChanged(self, fp, prop):
        if prop in ("USplits", "VSplits", "ShowSurface", "ShowGrid", "ShowSubgrids", "reverse"):
            if 'Restore' not in fp.State:
                fp.recompute()

    def getSubgrid(self, u0, u1, v0, v1):
        if self._base_surface is None:
            return None, None
        seg = self._base_surface.copy()
        seg.segment(u0, u1, v0, v1)
        return seg.getPoles(), seg.getWeights()

    def execute(self, fp):
        if 'Restore' in fp.State:
            return

        dummy_grid = FreeCAD.ActiveDocument.addObject("Part::FeaturePython", "_patch_tmp")
        AN.ControlGrid44_4(dummy_grid, fp.Poly0, fp.Poly1, fp.Poly2, fp.Poly3)
        dummy_grid.recompute()
        poles = dummy_grid.Poles
        weights = dummy_grid.Weights
        legs = dummy_grid.Legs
        FreeCAD.ActiveDocument.removeObject(dummy_grid.Name)

        if not poles or len(poles) != 16:
            fp.Poles = []
            fp.Weights = []
            fp.Legs = []
            return

        fp.Poles = poles
        fp.Weights = weights

        dummy_surf = FreeCAD.ActiveDocument.addObject("Part::FeaturePython", "_patch_surf_tmp")
        AN.CubicSurface_44(dummy_surf, fp)
        dummy_surf.recompute()
        if dummy_surf.Shape and dummy_surf.Shape.Faces:
            self._base_surface = dummy_surf.Shape.Faces[0].Surface.copy()
        FreeCAD.ActiveDocument.removeObject(dummy_surf.Name)

        self._subgrids = []
        self._subsurfaces = []
        u_splits = list(fp.USplits) if fp.USplits else []
        v_splits = list(fp.VSplits) if fp.VSplits else []

        if u_splits or v_splits:
            intervals_u = _build_intervals(u_splits)
            intervals_v = _build_intervals(v_splits)
            if self._base_surface:
                shapes = []
                grid_shapes_list = []
                for u0, u1 in intervals_u:
                    for v0, v1 in intervals_v:
                        seg = self._base_surface.copy()
                        seg.segment(u0, u1, v0, v1)
                        seg_poles = seg.getPoles()
                        flat = []
                        for r in range(4):
                            for c in range(4):
                                flat.append(seg_poles[r][c])
                        self._subgrids.append(flat)
                        sub_shape = seg.toShape()
                        if sub_shape:
                            shapes.append(sub_shape)
                        grid_shapes_list.extend(AN.drawGrid(flat, 4))
                self._subsurfaces = shapes
                fp.Legs = grid_shapes_list
        else:
            fp.Legs = legs

        shapes_to_compound = []
        if fp.ShowSubgrids and self._subsurfaces:
            shapes_to_compound.extend(self._subsurfaces)
        elif fp.ShowSurface:
            dummy_surf2 = FreeCAD.ActiveDocument.addObject("Part::FeaturePython", "_patch_surf2_tmp")
            AN.CubicSurface_44(dummy_surf2, fp)
            dummy_surf2.recompute()
            if dummy_surf2.Shape:
                shapes_to_compound.append(dummy_surf2.Shape)
            FreeCAD.ActiveDocument.removeObject(dummy_surf2.Name)

        if fp.ShowGrid and fp.Legs:
            for leg in fp.Legs:
                if hasattr(leg, "toShape"):
                    shapes_to_compound.append(leg.toShape())

        if shapes_to_compound:
            fp.Shape = Part.Compound(shapes_to_compound)
        else:
            fp.Shape = Part.Shape()


class CreateSilkPatch44:
    def GetResources(self):
        return {'Pixmap': iconPath, 'MenuText': 'Silk Patch44',
                'ToolTip': 'Create a 44 patch from 4 boundary edges.'}

    def Activated(self):
        sel = Gui.Selection.getSelection()
        if len(sel) == 0:
            tipsDialog("Silk: Patch44", "Select exactly 4 boundary edges (with 4 Poles each).")
            return
        if len(sel) != 4:
            FreeCAD.Console.PrintError("Silk: Patch44 requires exactly 4 selected edges.\n")
            return

        doc = FreeCAD.ActiveDocument
        obj = doc.addObject("Part::FeaturePython", "Patch44")
        Patch44(obj, sel[0], sel[1], sel[2], sel[3])
        obj.ViewObject.Proxy = 0
        obj.ViewObject.LineWidth = 1.50
        obj.ViewObject.LineColor = (0.67, 1.00, 1.00)
        obj.ViewObject.PointSize = 4.00
        obj.ViewObject.PointColor = (0.00, 0.33, 1.00)
        doc.recompute()
        FreeCAD.Console.PrintMessage(f"Patch44 created: {obj.Name}\n")

    def IsActive(self):
        return Gui is not None


Gui.addCommand("Silk_Patch44", CreateSilkPatch44())
