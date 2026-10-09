#    This file is part of Silk
#    (c) 2025
#
#    NURBS Surface modeling tools focused on low degree and seam continuity (FreeCAD Workbench)
#
#    Patch — the unified Patch object (ticket #37).
#
#    One variable-length `Edges` link list (PropertyLinkList) is the single
#    boundary input; execute() selects the fill from the edge count. For
#    #37 only the 4-edge quad fill is implemented, reproducing the SAME 16
#    poles as Patch44 for the identical 4 edges in the same order (the
#    3-edge pointed fill is #38, the unified Blend #39 — out of scope).
#
#    Subdivision / band / hidden-cell bookkeeping / compound display all
#    delegate to the shared machinery core (SilkMachinery) — nothing is
#    reimplemented here.

import FreeCAD
import Part

import ArachNURBS as AN

from SilkMachinery import build_subgrids, build_display

ICON = "Resources/Icons/ControlGridPatch.svg"


class Patch:
    """Unified Patch proxy (object_type='Patch')."""

    def __init__(self, obj, edges):
        obj.addProperty("App::PropertyLinkList", "Edges", "C1 - Inputs",
                        "boundary edges (4 for the quad fill)").Edges = list(edges)
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
        obj.addProperty("App::PropertyBool", "AutoHideBlend", "S2 - Display",
                        "hide subgrids covered by a blend").AutoHideBlend = True
        obj.addProperty("App::PropertyVectorList", "Poles", "C2 - Outputs", "Poles").Poles
        obj.addProperty("App::PropertyFloatList", "Weights", "C2 - Outputs", "Weights").Weights
        obj.addProperty("Part::PropertyGeometryList", "Legs", "C2 - Outputs",
                        "grid segments").Legs
        obj.addProperty("App::PropertyString", "object_type", "C3 - Identifiers",
                        "workbench class").object_type = "Patch"
        obj.setEditorMode("object_type", 1)
        obj.addProperty("App::PropertyString", "object_version", "C3 - Identifiers",
                        "class version").object_version = "0.01"
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
        if prop in ("USplits", "VSplits", "ShowSurface", "ShowGrid",
                    "ShowSubgrids", "reverse"):
            if 'Restore' not in fp.State and hasattr(fp, "Edges") and fp.Edges:
                fp.touch()
                fp.recompute()

    def getSubgrid(self, u0, u1, v0, v1):
        if self._base_surface is None:
            return None, None
        seg = self._base_surface.copy()
        seg.segment(u0, u1, v0, v1)
        return seg.getPoles(), seg.getWeights()

    # ---- fill selection --------------------------------------------------

    def _quad_fill(self, fp):
        """Replicate Patch44's ControlGrid44_4 fill from Edges[0..3].

        Produces the SAME 16 poles/weights/layout as Patch44 for the
        identical 4 edges in the same order (pole parity at 1e-6 is what
        later lets the unified pipeline reproduce the chain — #40).
        """
        p0 = list(fp.Edges[0].Poles)
        p1 = list(fp.Edges[1].Poles)
        p2 = list(fp.Edges[2].Poles)
        p3 = list(fp.Edges[3].Poles)
        w0 = list(fp.Edges[0].Weights)
        w1 = list(fp.Edges[1].Weights)
        w2 = list(fp.Edges[2].Weights)
        w3 = list(fp.Edges[3].Weights)
        tol = fp.tolerance

        quad12 = AN.orient_a_to_b(p0, p1, tol)
        if quad12 == 0:
            return None
        quad23 = AN.orient_a_to_b(p1, p2, tol)
        if quad23 == 0:
            return None
        quad34 = AN.orient_a_to_b(p2, p3, tol)
        if quad34 == 0:
            return None
        quad41 = AN.orient_a_to_b(p3, p0, tol)
        if quad41 == 0:
            return None

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

        return poles, weights

    # ---- execute ---------------------------------------------------------

    def execute(self, fp):
        inputs = [e for e in getattr(fp, "Edges", []) or [] if e is not None]
        if len(inputs) != 4:
            # #37 implements only the 4-edge quad fill; other counts are
            # deferred (#38 pointed fill). Leave the object empty/valid.
            fp.Poles = []; fp.Weights = []; fp.Legs = []
            self._subgrids = []; self._subsurfaces = []; self._base_surface = None
            build_display(fp, Part.Shape(), [], [], [], False)
            return

        filled = self._quad_fill(fp)
        if filled is None:
            fp.Poles = []; fp.Weights = []; fp.Legs = []; fp.Shape = Part.Shape(); return
        poles, weights = filled

        fp.Poles = poles
        fp.Weights = weights

        # Build bicubic Bezier surface from the 16-pole grid (matching Patch44)
        surf = Part.BSplineSurface()
        surf.increaseDegree(3, 3)
        for knot, mult in [(0.0, 4), (1.0, 4)]:
            surf.insertUKnot(knot, mult, 1e-7)
            surf.insertVKnot(knot, mult, 1e-7)
        for r in range(4):
            for c in range(4):
                idx = r * 4 + c
                surf.setPole(c + 1, r + 1, poles[idx], weights[idx])
        self._base_surface = surf

        # Grid lines
        legs = AN.drawGrid(poles, 4)
        fp.Legs = legs

        # Subdivision (shared machinery core)
        self._subgrids, self._subsurfaces, sub_legs = build_subgrids(
            surf, fp.USplits, fp.VSplits)
        if fp.USplits or fp.VSplits:
            fp.Legs = sub_legs

        # Compound display (shared machinery core)
        build_display(fp, surf.toShape(), self._subsurfaces, legs, sub_legs,
                      bool(fp.USplits or fp.VSplits))


class PatchViewProvider:
    def __init__(self, vobj):
        vobj.Proxy = self

    def getIcon(self):
        return ICON

    def attach(self, vobj):
        self.ViewObject = vobj

    def updateData(self, obj, prop):
        return True

    def __getstate__(self):
        return None

    def __setstate__(self, state):
        return None
