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
        # Guard: only recompute if object is fully initialized (has inputs)
        if prop in ("USplits", "VSplits", "ShowSurface", "ShowGrid", "ShowSubgrids", "reverse"):
            if 'Restore' not in fp.State and hasattr(fp, "Poly0") and fp.Poly0:
                fp.recompute()

    def getSubgrid(self, u0, u1, v0, v1):
        if self._base_surface is None:
            return None, None
        seg = self._base_surface.copy()
        seg.segment(u0, u1, v0, v1)
        return seg.getPoles(), seg.getWeights()

    def execute(self, fp):
        if not hasattr(fp, "Poly0") or not fp.Poly0:
            return
        if not hasattr(fp, "Poly1") or not fp.Poly1:
            return
        if not hasattr(fp, "Poly2") or not fp.Poly2:
            return
        if not hasattr(fp, "Poly3") or not fp.Poly3:
            return

        # Build grid poles from edges using ArachNURBS (without temp doc objects)
        p0 = list(fp.Poly0.Poles)
        p1 = list(fp.Poly1.Poles)
        p2 = list(fp.Poly2.Poles)
        p3 = list(fp.Poly3.Poles)
        w0 = list(fp.Poly0.Weights)
        w1 = list(fp.Poly1.Weights)
        w2 = list(fp.Poly2.Weights)
        w3 = list(fp.Poly3.Weights)
        tol = fp.tolerance

        # Replicate ControlGrid44_4.execute logic inline
        quad12 = AN.orient_a_to_b(p0, p1, tol)
        if quad12 == 0:
            fp.Poles = []; fp.Weights = []; fp.Legs = []; return
        quad23 = AN.orient_a_to_b(p1, p2, tol)
        if quad23 == 0:
            fp.Poles = []; fp.Weights = []; fp.Legs = []; return
        quad34 = AN.orient_a_to_b(p2, p3, tol)
        if quad34 == 0:
            fp.Poles = []; fp.Weights = []; fp.Legs = []; return
        quad41 = AN.orient_a_to_b(p3, p0, tol)
        if quad41 == 0:
            fp.Poles = []; fp.Weights = []; fp.Legs = []; return

        if quad12[0] != p0[0] and quad12[0] == p0[-1]:
            w0 = list(reversed(w0))
        if quad23[0] != p1[0] and quad23[0] == p1[-1]:
            w1 = list(reversed(w1))
        if quad34[0] != p2[0] and quad34[0] == p2[-1]:
            w2 = list(reversed(w2))
        if quad41[0] != p3[0] and quad41[0] == p3[-1]:
            w3 = list(reversed(w3))

        p00 = quad12[0]; p01 = quad12[1]; p02 = quad12[2]; p03 = quad12[3]
        p13 = quad23[1]; p23 = quad23[2]; p33 = quad23[3]
        p32 = quad34[1]; p31 = quad34[2]; p30 = quad34[3]
        p20 = quad41[1]; p10 = quad41[2]

        p11 = p00 + (p01 - p00) + (p10 - p00)
        p12 = p03 + (p02 - p03) + (p13 - p03)
        p21 = p30 + (p31 - p30) + (p20 - p30)
        p22 = p33 + (p23 - p33) + (p32 - p33)

        poles = [p00, p01, p02, p03, p10, p11, p12, p13,
                 p20, p21, p22, p23, p30, p31, p32, p33]

        w00 = w0[0]; w01 = w0[1]; w02 = w0[2]; w03 = w0[3]
        w13 = w1[1]; w23 = w1[2]; w33 = w1[3]
        w32 = w2[1]; w31 = w2[2]; w30 = w2[3]
        w20 = w3[1]; w10 = w3[2]
        weights = [w00, w01, w02, w03, w10, w01 * w10, w02 * w13, w13,
                   w20, w20 * w31, w23 * w32, w23, w30, w31, w32, w33]

        fp.Poles = poles
        fp.Weights = weights

        # Build surface from the 16-pole grid
        surf = Part.BSplineSurface()
        poles2d = [[poles[r*4 + c] for c in range(4)] for r in range(4)]
        weights2d = [[weights[r*4 + c] for c in range(4)] for r in range(4)]
        surf.buildFromPolesMultsKnots(poles2d, weights2d,
                                       [4, 4], [4, 4],
                                       [0, 0, 0, 1, 1, 1], [0, 0, 0, 1, 1, 1],
                                       False, False, 3, 3)
        self._base_surface = surf

        # Grid lines
        legs = AN.drawGrid(poles, 4)
        fp.Legs = legs

        # Subdivision
        self._subgrids = []
        self._subsurfaces = []
        u_splits = list(fp.USplits) if fp.USplits else []
        v_splits = list(fp.VSplits) if fp.VSplits else []

        if u_splits or v_splits:
            intervals_u = _build_intervals(u_splits)
            intervals_v = _build_intervals(v_splits)
            shapes = []
            sub_legs = []
            for u0, u1 in intervals_u:
                for v0, v1 in intervals_v:
                    seg = surf.copy()
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
                    sub_legs.extend(AN.drawGrid(flat, 4))
            self._subsurfaces = shapes
            fp.Legs = sub_legs

        # Build display Shape
        shapes_to_compound = []
        if fp.ShowSubgrids and self._subsurfaces:
            shapes_to_compound.extend(self._subsurfaces)
        elif fp.ShowSurface:
            shapes_to_compound.append(surf.toShape())

        if fp.ShowGrid and fp.Legs:
            for leg in fp.Legs:
                if hasattr(leg, "toShape"):
                    shapes_to_compound.append(leg.toShape())

        if shapes_to_compound:
            try:
                fp.Shape = Part.Compound(shapes_to_compound)
            except Exception:
                if len(shapes_to_compound) == 1:
                    fp.Shape = shapes_to_compound[0]
                else:
                    fp.Shape = Part.Shape(shapes_to_compound)
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
