#    This file is part of Silk
#    (c) 2025
#
#    NURBS Surface modeling tools focused on low degree and seam continuity (FreeCAD Workbench)
#
#    Patch44 — single FeaturePython combining ControlGrid44 + CubicSurface_44 + subgrids.
#
#    RETAINED FOR OLD-DOCUMENT RESTORE ONLY (ticket #42): nothing
#    creates this type anymore. The ops layer (SilkWorkflowOps.
#    create_patch) and the Silk_CreatePatch GUI command build the
#    unified Patch (SilkPatch), which delegates to the same shared
#    machinery core (SilkMachinery) this class uses. The class +
#    view provider below stay so Silk_Workflow.FCStd and other old
#    documents restore their stored Patch44 objects.

import FreeCAD
import Part
import ArachNURBS as AN

from SilkMachinery import build_intervals, build_subgrids, build_display, \
    split_pair, axis_splits, NO_BAND_1, NO_BAND_2

import os, Silk_dummy
path_Silk = os.path.dirname(Silk_dummy.__file__)
path_Silk_icons = os.path.join(path_Silk, "Resources", "Icons")
iconPath = path_Silk_icons + "/Patch44.svg"

# Canonical implementation lives in the shared machinery core
# (SilkMachinery); re-exported under the legacy name for old
# callers (SilkCorner / SilkChecks import it from SilkMachinery
# directly since #42).
_build_intervals = build_intervals


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
        # #82: the two named band edges per axis, exactly as the unified
        # Patch carries them -- this class shares the whole machinery core
        # (build_subgrids, band_cells, corner_cells), so it speaks the same
        # language or it would not subdivide at all. A Patch44 restored
        # from a pre-#82 file comes back with the four properties at their
        # sentinels, i.e. with no bands: no migration is shipped.
        for letter in ("U", "V"):
            obj.addProperty(
                "App::PropertyFloat", letter + "Split1", "S1 - Subdivision",
                "band edge at the parametric-0 end of the %s axis; 0 = no "
                "band at that end" % letter)
            obj.addProperty(
                "App::PropertyFloat", letter + "Split2", "S1 - Subdivision",
                "band edge at the parametric-1 end of the %s axis; 1 = no "
                "band at that end" % letter)
        obj.USplit1 = NO_BAND_1
        obj.USplit2 = NO_BAND_2
        obj.VSplit1 = NO_BAND_1
        obj.VSplit2 = NO_BAND_2
        obj.addProperty("App::PropertyBool", "ShowSurface", "S2 - Display",
                        "show the surface").ShowSurface = True
        obj.addProperty("App::PropertyBool", "ShowGrid", "S2 - Display",
                        "show the control grid").ShowGrid = True
        obj.addProperty("App::PropertyBool", "ShowSubgrids", "S2 - Display",
                        "show subdivided subgrids instead of base surface").ShowSubgrids = False
        obj.addProperty("App::PropertyBool", "AutoHideBlend", "S2 - Display",
                        "hide subgrids when a BlendStrip uses this patch").AutoHideBlend = True
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
        # #82: an old file's Patch44 arrives with the pre-#82 USplits /
        # VSplits lists and none of the four band edges. No migration is
        # shipped, so they are created at their sentinels: the object comes
        # back with no bands, which is the neutral state, and is editable.
        for letter in ("U", "V"):
            for n, sentinel in ((1, NO_BAND_1), (2, NO_BAND_2)):
                name = "%sSplit%d" % (letter, n)
                if not hasattr(obj, name):
                    obj.addProperty(
                        "App::PropertyFloat", name, "S1 - Subdivision",
                        "band edge at the parametric-%d end of the %s axis; "
                        "%g = no band at that end" % (n - 1, letter, sentinel))
                    setattr(obj, name, sentinel)
        obj.recompute()

    def onChanged(self, fp, prop):
        # Guard: only recompute if object is fully initialized (has inputs)
        if prop in ("USplit1", "USplit2", "VSplit1", "VSplit2",
                    "ShowSurface", "ShowGrid", "ShowSubgrids", "reverse"):
            if 'Restore' not in fp.State and hasattr(fp, "Poly0") and fp.Poly0:
                fp.touch()
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

        # Touch any blend objects linked to this patch (the unified
        # "Blend" #39 plus the legacy "BlendStrip"; old and new blends
        # may mix in one document during migration)
        doc = fp.Document
        if doc:
            for obj in doc.Objects:
                if (hasattr(obj, "object_type")
                        and obj.object_type in ("Blend", "BlendStrip")):
                    if getattr(obj, "PatchA", None) == fp or getattr(obj, "PatchB", None) == fp:
                        obj.touch()

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

        # Build bicubic Bezier surface from the 16-pole grid (matching ArachNURBS pattern)
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

        # Subdivision (shared core), from the two named band edges per axis
        # (#82) rather than the pre-#82 split lists.
        u_pair = split_pair(fp, "U")
        v_pair = split_pair(fp, "V")
        has_subgrids = bool(axis_splits(*u_pair) or axis_splits(*v_pair))
        self._subgrids, self._subsurfaces, sub_legs = build_subgrids(
            surf, u_pair, v_pair)
        if has_subgrids:
            fp.Legs = sub_legs

        # Build display Shape (shared core)
        # ShowSurface: show/hide surface. ShowSubgrids: show subdivided detail. ShowGrid: grid lines.
        # AutoHideBlend: hide the subgrid cells covered by blends
        # (via _HiddenSubgridIdxs; legacy single _HideSubgridIdx also honoured)
        build_display(fp, surf.toShape(), self._subsurfaces, legs, sub_legs,
                      has_subgrids)


class Patch44ViewProvider:
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
