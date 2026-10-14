"""
SilkPatch33.py -- Patch33: a 3-edge pointed patch.

A self-contained Part::FeaturePython object driven by three boundary
edges (4-pole ControlPoly4 objects) forming a closed, doubly-curved loop
with three corners. The fill replicates AN.ControlGrid44_3: a 4x4 control
grid whose U=0 column collapses to a single point (the "point" of the
pointed shape). The surface is a bicubic BSplineSurface over that grid.

Inputs:  Poly0/1/2 (three boundary edges), tolerance, reverse.
Outputs: Poles (16), Weights (16), Legs (grid), Shape (bicubic surface).
"""

import FreeCAD
import Part

import ArachNURBS as AN

try:
    from . import SilkPatch44 as _P  # for icon/helpers if needed
except Exception:
    pass

import os, Silk_dummy
path_Silk = os.path.dirname(Silk_dummy.__file__)
path_Silk_icons = os.path.join(path_Silk, "Resources", "Icons")
iconPath = path_Silk_icons + "/ControlGrid44_Rotate.svg"


class Patch33:
    """Patch33 proxy (object_type='Patch33')."""

    def __init__(self, obj, poly0, poly1, poly2):
        obj.addProperty("App::PropertyLink", "Poly0", "C1 - Inputs",
                        "first boundary edge").Poly0 = poly0
        obj.addProperty("App::PropertyLink", "Poly1", "C1 - Inputs",
                        "second boundary edge").Poly1 = poly1
        obj.addProperty("App::PropertyLink", "Poly2", "C1 - Inputs",
                        "third boundary edge").Poly2 = poly2
        obj.addProperty("App::PropertyFloat", "tolerance", "C1 - Inputs",
                        "point-to-point connection tolerance").tolerance = AN.default_tol
        obj.addProperty("App::PropertyBool", "reverse", "C1 - Inputs",
                        "reverse the parameter direction").reverse = False
        obj.addProperty("App::PropertyFloat", "TweakWeight11", "C1 - Inputs",
                        "scale factor for inner control point near the point").TweakWeight11 = 1.0
        obj.addProperty("App::PropertyVectorList", "Poles", "C2 - Outputs",
                        "Poles").Poles
        obj.addProperty("App::PropertyFloatList", "Weights", "C2 - Outputs",
                        "Weights").Weights
        obj.addProperty("Part::PropertyGeometryList", "Legs", "C2 - Outputs",
                        "grid segments").Legs
        obj.addProperty("App::PropertyString", "object_type", "C3 - Identifiers",
                        "workbench class").object_type = "Patch33"
        obj.setEditorMode("object_type", 1)
        obj.addProperty("App::PropertyString", "object_version", "C3 - Identifiers",
                        "class version").object_version = "0.01"
        obj.setEditorMode("object_version", 1)
        obj.addProperty("App::PropertyString", "internalName", "C3 - Identifiers",
                        "permanent internal FreeCAD name").internalName = obj.Name
        obj.setEditorMode("internalName", 1)
        obj.Proxy = self
        self._base_surface = None

    def execute(self, fp):
        if not all(getattr(fp, "Poly%d" % i, None) for i in range(3)):
            return

        p0 = list(fp.Poly0.Poles)
        p1 = list(fp.Poly1.Poles)
        p2 = list(fp.Poly2.Poles)
        w0 = list(fp.Poly0.Weights)
        w1 = list(fp.Poly1.Weights)
        w2 = list(fp.Poly2.Weights)
        tol = fp.tolerance

        # Replicate ControlGrid44_3.execute inline.
        quad12 = AN.orient_a_to_b(p0, p1, tol)
        if quad12 == 0:
            fp.Poles = []; fp.Weights = []; fp.Legs = []; fp.Shape = Part.Shape(); return
        quad23 = AN.orient_a_to_b(p1, p2, tol)
        if quad23 == 0:
            fp.Poles = []; fp.Weights = []; fp.Legs = []; fp.Shape = Part.Shape(); return
        quad31 = AN.orient_a_to_b(p2, p0, tol)
        if quad31 == 0:
            fp.Poles = []; fp.Weights = []; fp.Legs = []; fp.Shape = Part.Shape(); return

        if quad12[0] != p0[0] and quad12[0] == p0[-1]:
            w0 = list(reversed(w0))
        if quad23[0] != p1[0] and quad23[0] == p1[-1]:
            w1 = list(reversed(w1))
        if quad31[0] != p2[0] and quad31[0] == p2[-1]:
            w2 = list(reversed(w2))

        p00 = quad12[0]; p01 = quad12[1]; p02 = quad12[2]; p03 = quad12[3]
        p13 = quad23[1]; p23 = quad23[2]; p33 = quad23[3]
        p32 = quad31[1]; p31 = quad31[2]; p30 = p00

        # degenerate U=0 column collapses to the point p00
        p20 = p00
        p10 = p00

        p11 = p01 + p31 - p30
        p12 = p02 + p13 - p03
        p21 = p11
        p22 = p23 + p32 - p33

        fp.Poles = [p00, p01, p02, p03,
                    p10, p11, p12, p13,
                    p20, p21, p22, p23,
                    p30, p31, p32, p33]

        # Weights mirror ControlGrid44_3 (interior degenerate weights tie to
        # the outer boundary weights; TweakWeight11 scales the degenerate
        # corner's draw).
        tweak = fp.TweakWeight11 if hasattr(fp, "TweakWeight11") else 1.0
        w00 = w0[0]; w01 = w0[1]; w02 = w0[2]; w03 = w0[3]
        w13 = w1[1]; w23 = w1[2]; w33 = w1[3]
        w32 = w2[1]; w31 = w2[2]; w30 = w2[3]
        w10 = tweak
        w20 = tweak
        fp.Weights = [w00, w01, w02, w03,
                      w10, w01 * w10, w02 * w13, w13,
                      w20, w31 * w20, w23 * w32, w23,
                      w30, w31, w32, w33]

        fp.Legs = AN.drawGrid(fp.Poles, 4)

        # Bicubic Bezier surface over the 16-pole grid (degenerate U=0 column).
        surf = Part.BSplineSurface()
        surf.increaseDegree(3, 3)
        for knot, mult in [(0.0, 4), (1.0, 4)]:
            surf.insertUKnot(knot, mult, 1e-7)
            surf.insertVKnot(knot, mult, 1e-7)
        poles = list(fp.Poles)
        weights = list(fp.Weights)
        for r in range(4):
            for c in range(4):
                idx = r * 4 + c
                surf.setPole(c + 1, r + 1, poles[idx], weights[idx])
        self._base_surface = surf

        try:
            fp.Shape = surf.toShape()
        except Exception:
            fp.Shape = Part.Shape()


class Patch33ViewProvider:
    def __init__(self, vobj):
        vobj.Proxy = self

    def getIcon(self):
        return iconPath

    def attach(self, vobj):
        self.ViewObject = vobj

    def updateData(self, obj, prop):
        return True

    def __getstate__(self):
        return None

    def __setstate__(self, state):
        return None
