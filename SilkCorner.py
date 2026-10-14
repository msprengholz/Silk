"""
SilkCorner — CornerBlend FeaturePython for the 4-subgrid corner fill (#28).

Where 4 Patch44 objects meet at a central junction, each contributes its
0.1x0.1 corner subgrid cell (excluded from the ring blend bands by #33).
The CornerBlend takes the 4 ring BlendStrips (DAG: patch -> strip ->
corner blend), extracts each strip's corner-end row — the 6-pole edge of
the strip's blend surface at the corner-cell side — and builds a 6x6
control grid with AN.ControlGrid66_4 + AN.CubicSurface_66 (the existing
4-sided corner blend primitive).

Strip corner-end row derivation: for each strip side (patch), the
corner cell at the junction is the subgrid cell where the patch's two
shared (seam) edges meet; the corner-end row is the blend row adjacent
to that corner cell along the strip's band axis (row 3 if the corner
cell sits above the band cell, row 0 if below).

Usage:
  1. Build the 4 ring BlendStrips (in cyclic order)
  2. Run create_corner_blend(strip0, strip1, strip2, strip3)
  3. The corner blend auto-updates when any linked strip recomputes
"""

import FreeCAD
import Part
import ArachNURBS as AN

from SilkBlend import _patch_side, band_cells
from SilkMachinery import build_intervals, split_pair

import os, Silk_dummy
path_Silk = os.path.dirname(Silk_dummy.__file__)
path_Silk_icons = os.path.join(path_Silk, "Resources", "Icons")
iconPath = path_Silk_icons + "/ControlGrid66_4Sub.svg"


class CornerBlend:
    """FeaturePython: fills the central region where 4 patches meet."""

    def __init__(self, obj, strip0, strip1, strip2, strip3):
        obj.addProperty("App::PropertyLinkList", "Strips", "Inputs",
                        "ring blend strips in cyclic order"
                        ).Strips = [strip0, strip1, strip2, strip3]
        obj.addProperty("App::PropertyFloat", "tolerance", "Inputs",
                        "corner matching tolerance").tolerance = 0.01
        obj.addProperty("App::PropertyVectorList", "Poles", "Outputs",
                        "corner grid poles (6x6)").Poles
        obj.addProperty("App::PropertyFloatList", "Weights", "Outputs",
                        "corner grid weights").Weights
        obj.addProperty("Part::PropertyGeometryList", "Legs", "Outputs",
                        "grid segments").Legs
        obj.addProperty("App::PropertyString", "object_type", "",
                        "").object_type = "CornerBlend"
        obj.setEditorMode("object_type", 1)
        obj.Proxy = self
        self._in_execute = False

    def onChanged(self, fp, prop):
        if prop in ("Strips", "tolerance"):
            if 'Restore' not in fp.State and list(getattr(fp, "Strips", []) or []):
                fp.touch()
                fp.recompute()

    def execute(self, fp):
        if 'Restore' in fp.State:
            return  # preserve stored poles across save/restore
        if not list(getattr(fp, "Strips", []) or []):
            return
        if getattr(self, "_in_execute", False):
            return
        self._in_execute = True
        try:
            self._do_execute(fp)
        finally:
            self._in_execute = False

    # ---- derivation -------------------------------------------------

    @staticmethod
    def _corner_cell(p, strips, tol):
        """(iu_c, iv_c, nu, nv) of the corner cell at the 4-patch junction
        of patch p. The U-direction seam gives the V side of the corner,
        the V-direction seam gives the U side.

        `nu` / `nv` are the interval counts of the two named band edges
        each (#82) -- `len(splits) + 1` used to say "how many splits does
        this axis carry", and what an axis carries is now, per end, the
        question "does this end have an edge?". So the count is the
        number of EDGES on the axis plus one, read off the two properties
        by name."""
        nu = len(build_intervals(*split_pair(p, "U")))
        nv = len(build_intervals(*split_pair(p, "V")))
        iu_c = iv_c = None
        for s in strips:
            other = s.PatchB if s.PatchA is p else s.PatchA
            if other is None:
                continue
            e, ss = _patch_side(p, other, tol)
            if not e:
                continue
            if e[0] == "U":
                iv_c = nv - 1 if e[1] == "1" else 0
            else:
                iu_c = nu - 1 if e[1] == "1" else 0
        return iu_c, iv_c, nu, nv

    def _derive_rows(self, fp, strips):
        """Corner-end row per strip + corner cell per patch.

        Returns (rows, corner_cells) or (None, None) on any
        inconsistency. rows are in the given strip order (need not be
        ring order — _order_loop fixes that).
        """
        tol = fp.tolerance
        rows = []
        corner_cells = {}
        for s in strips:
            pa, pb = s.PatchA, s.PatchB
            if pa is None or pb is None:
                FreeCAD.Console.PrintError(
                    "Silk: corner blend strip %s has no patches.\n" % s.Name)
                return None, None
            e_a, ss_a = _patch_side(pa, pb, tol)
            e_b, ss_b = _patch_side(pb, pa, tol)
            if not e_a or not e_b:
                FreeCAD.Console.PrintError(
                    "Silk: corner blend strip %s: no shared edge found "
                    "between %s and %s.\n" % (s.Name, pa.Name, pb.Name))
                return None, None
            bca = band_cells(pa, e_a, ss_a)
            bcb = band_cells(pb, e_b, ss_b)
            if len(bca) != 1 or len(bcb) != 1:
                FreeCAD.Console.PrintError(
                    "Silk: corner blend strip %s: band must cover exactly "
                    "1 cell per side (got %d/%d).\n"
                    % (s.Name, len(bca), len(bcb)))
                return None, None
            li_map = {}
            for pth, e, bc in ((pa, e_a, bca), (pb, e_b, bcb)):
                iu_c, iv_c, nu, nv = self._corner_cell(pth, strips, tol)
                if iu_c is None or iv_c is None:
                    FreeCAD.Console.PrintError(
                        "Silk: patch %s: corner cell at the 4-patch "
                        "junction not found.\n" % pth.Name)
                    return None, None
                iu_b, iv_b = divmod(bc[0], nv)
                # corner-end blend row: 3 if the corner cell sits above
                # the band cell along the band axis, else 0
                if e[0] == "U":
                    li_map[pth.Name] = 3 if iu_c > iu_b else 0
                else:
                    li_map[pth.Name] = 3 if iv_c > iv_b else 0
                corner_cells[pth.Name] = (pth, iu_c, iv_c, nu, nv)
            if li_map[pa.Name] != li_map[pb.Name]:
                FreeCAD.Console.PrintError(
                    "Silk: corner blend strip %s: inconsistent corner-end "
                    "row between sides (%s vs %s) — twisted input.\n"
                    % (s.Name, li_map[pa.Name], li_map[pb.Name]))
                return None, None
            li = li_map[pa.Name]
            poles = s.Poles or []
            if len(poles) != 24:
                FreeCAD.Console.PrintError(
                    "Silk: corner blend strip %s: expected 24 poles, got "
                    "%d.\n" % (s.Name, len(poles)))
                return None, None
            rows.append(list(poles[li * 6: li * 6 + 6]))
        return rows, corner_cells

    @staticmethod
    def _order_loop(rows, tol):
        """Reorder the 4 boundary rows into a closed loop: each next row
        shares an endpoint with the previous one, and the last shares
        one with the first. Returns the ordered rows or None."""
        remaining = list(rows[1:])
        ordered = [rows[0]]
        while remaining:
            last = ordered[-1]
            for i, r in enumerate(remaining):
                d = min((last[a] - r[b]).Length
                        for a in (0, 5) for b in (0, 5))
                if d <= tol:
                    ordered.append(remaining.pop(i))
                    break
            else:
                return None
        d = min((ordered[-1][a] - ordered[0][b]).Length
                for a in (0, 5) for b in (0, 5))
        return ordered if d <= tol else None

    # ---- execution --------------------------------------------------

    def _do_execute(self, fp):
        strips = list(fp.Strips)
        rows, corner_cells = self._derive_rows(fp, strips)
        if rows is None:
            return

        ordered = self._order_loop(rows, fp.tolerance)
        if ordered is None:
            FreeCAD.Console.PrintError(
                "Silk: corner blend %s: strip corner-end rows do not form "
                "a closed loop.\n" % fp.Name)
            return

        # hide the corner cells (the region this blend covers)
        for name, (pth, iu_c, iv_c, nu, nv) in corner_cells.items():
            idx = iu_c * nv + iv_c
            try:
                pth.removeProperty("_HideSubgridIdx")  # superseded
            except Exception:
                pass
            if not hasattr(pth, "_HiddenSubgridIdxs"):
                pth.addProperty("App::PropertyIntegerList",
                                "_HiddenSubgridIdxs", "Internal",
                                "subgrid cell indices hidden by blends")
                pth.setEditorMode("_HiddenSubgridIdxs", 1)
            cur = set(int(i) for i in (pth._HiddenSubgridIdxs or []))
            cur.add(idx)
            pth._HiddenSubgridIdxs = sorted(cur)

        # 6x6 control grid from the 4 boundary rows (ControlGrid66_4
        # needs pole-carrying objects, so build throwaway carriers)
        doc = fp.Document
        carriers = []
        for i, row in enumerate(ordered):
            c = doc.addObject("Part::FeaturePython", "_cb_poly_tmp")
            c.addProperty("App::PropertyVectorList", "Poles", "Internal",
                          "boundary row poles").Poles
            c.addProperty("App::PropertyFloatList", "Weights", "Internal",
                          "boundary row weights").Weights
            c.Poles = row
            c.Weights = [1.0] * 6
            carriers.append(c)
        grid = doc.addObject("Part::FeaturePython", "_cb_grid_tmp")
        AN.ControlGrid66_4(grid, *carriers)
        grid.recompute()
        poles36 = list(grid.Poles) if hasattr(grid, "Poles") else []
        weights36 = list(grid.Weights) if hasattr(grid, "Weights") else []
        doc.removeObject(grid.Name)
        for c in carriers:
            doc.removeObject(c.Name)

        if len(poles36) != 36 or len(weights36) != 36:
            FreeCAD.Console.PrintError(
                "Silk: corner blend %s: ControlGrid66_4 produced %d/%d "
                "poles/weights (want 36).\n"
                % (fp.Name, len(poles36), len(weights36)))
            return

        fp.Poles = poles36
        fp.Weights = weights36
        fp.Legs = AN.drawGrid(fp.Poles, 6)

        # corner surface via AN.CubicSurface_66 (never buildFromPolesMultsKnots)
        tmp_surf = doc.addObject("Part::FeaturePython", "_cb_surf_tmp")
        AN.CubicSurface_66(tmp_surf, fp)
        tmp_surf.recompute()
        surf_shape = tmp_surf.Shape
        doc.removeObject(tmp_surf.Name)

        if not surf_shape or not hasattr(surf_shape, "Faces") \
                or not surf_shape.Faces:
            fp.Shape = Part.Shape()  # fallback: just show the grid
            return

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


class CornerBlendViewProvider:
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
