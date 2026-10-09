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
iconPath = path_Silk_icons + "/BlendStrip.svg"


def _patch_side(pa, pb, tol=0.01):
    """Edge type and side of the shared edge as seen from pa (toward pb).

    Returns (edge_type, ss) e.g. ("V1", 1), or (None, None) when the
    patches do not share an edge.
    """
    a_c = [pa.Poles[0], pa.Poles[3], pa.Poles[15], pa.Poles[12]]
    b_c = [pb.Poles[0], pb.Poles[3], pb.Poles[15], pb.Poles[12]]
    pairs = [(i, j) for i, ac in enumerate(a_c)
             for j, bc in enumerate(b_c) if (ac - bc).Length < tol]
    if len(pairs) < 2:
        return None, None
    edges = {(0, 1): "U0", (1, 2): "V1", (2, 3): "U1", (3, 0): "V0",
             (1, 0): "U0", (2, 1): "V1", (3, 2): "U1", (0, 3): "V0"}
    ids_a = sorted(x[0] for x in pairs)
    ids_b = sorted(x[1] for x in pairs)
    ea = edges.get((ids_a[0], ids_a[1]))
    if not ea:
        return None, None
    return ea, (0 if ea[1] == "0" else 1)


def band_cells(p, ea, ss):
    """Subgrid cell indices covered by a strip's band on patch p.

    The band runs along the seam in the band interval (0 or last, per
    ss). A cell at a seam end with a seam-axis split is a corner cell —
    excluded from the band (reserved for the four-cell corner blend
    op, #28).
    """
    from SilkPatch44 import _build_intervals
    ivs_u = _build_intervals(list(p.USplits or []))
    ivs_v = _build_intervals(list(p.VSplits or []))
    nu, nv = len(ivs_u), len(ivs_v)
    if ea[0] == "U":  # seam along U: band fixes V interval, spans U cells
        b = (nv - 1) if ss else 0
        keep_u = set(range(nu))
        if any(abs(s - 0.1) < 1e-9 for s in (p.USplits or [])):
            keep_u.discard(0)
        if any(abs(s - 0.9) < 1e-9 for s in (p.USplits or [])):
            keep_u.discard(nu - 1)
        return [a * nv + b for a in sorted(keep_u)]
    # seam along V: band fixes U interval, spans V cells
    a = (nu - 1) if ss else 0
    keep_v = set(range(nv))
    if any(abs(s - 0.1) < 1e-9 for s in (p.VSplits or [])):
        keep_v.discard(0)
    if any(abs(s - 0.9) < 1e-9 for s in (p.VSplits or [])):
        keep_v.discard(nv - 1)
    return [a * nv + b for b in sorted(keep_v)]


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

        for p in (pa, pb):
            if not p.Proxy._base_surface:
                return

        # Step 1: find shared corners
        a_c = [pa.Poles[0], pa.Poles[3], pa.Poles[15], pa.Poles[12]]
        b_c = [pb.Poles[0], pb.Poles[3], pb.Poles[15], pb.Poles[12]]
        pairs = []
        for i, ac in enumerate(a_c):
            for j, bc in enumerate(b_c):
                if (ac - bc).Length < tol:
                    pairs.append((i, j))
        if len(pairs) < 2:
            return

        # Step 2: determine edge type (U0/U1/V0/V1)
        edges = {(0, 1): "U0", (1, 2): "V1", (2, 3): "U1", (3, 0): "V0",
                 (1, 0): "U0", (2, 1): "V1", (3, 2): "U1", (0, 3): "V0"}
        ids_a = sorted(p[0] for p in pairs)
        ids_b = sorted(p[1] for p in pairs)
        ea = edges.get((ids_a[0], ids_a[1]))
        eb = edges.get((ids_b[0], ids_b[1]))
        if not ea or not eb:
            return

        # Step 3: set split direction and side
        # Split PERPENDICULAR to the shared edge
        sd_a = "V" if ea[0] == "U" else "U"  # VSplits if edge along U, USplits if edge along V
        sd_b = "V" if eb[0] == "U" else "U"
        ss_a = 0 if ea[1] == "0" else 1  # split near 0 or near 1 along the perpendicular direction
        ss_b = 0 if eb[1] == "0" else 1

        # Step 4: ensure each patch has the split that isolates its 0.1 band at
        # the shared edge (perpendicular to the seam, on the seam's side). A
        # corner patch meets two strips, so both USplits and VSplits get set.
        def ensure_band_split(p, sd, ss):
            prop = "VSplits" if sd == "V" else "USplits"
            val = 0.9 if ss else 0.1
            cur = list(getattr(p, prop) or [])
            if all(abs(v - val) > 1e-9 for v in cur):
                setattr(p, prop, sorted(cur + [val]))
                p.recompute()

        ensure_band_split(pa, sd_a, ss_a)
        ensure_band_split(pb, sd_b, ss_b)

        # Step 5: extract edge strips directly from base surface
        # (bypasses pre-computed subgrids which may not cover the full shared edge)
        # For shared edge along U (row): need strip with full U range, narrow V range
        # For shared edge along V (col): need strip with full V range, narrow U range

        # #33: the blend band comes from the patch's own subgrid cells —
        # the UV splits already subdivide the surface, so pick the seam-
        # adjacent cell(s) instead of re-segmenting the base surface (see
        # module-level band_cells). The 0.1x0.1 corner cell at a 4-patch
        # junction is not part of the band (reserved for the corner
        # blend op, #28).
        def get_strip(p, ea, ss):
            """Extract the band cell's flat 16-pole array poles[U][V] = flat[U*4+V]
            from the patch's pre-computed subgrids.
            """
            idxs = band_cells(p, ea, ss)
            if len(idxs) != 1 or not p.Proxy._subgrids:
                FreeCAD.Console.PrintError(
                    f"Silk: blend band on {p.Name} covers {len(idxs)} subgrid "
                    "cells; exactly 1 is required (multi-cell bands not "
                    "supported yet).\n")
                return None
            return list(p.Proxy._subgrids[idxs[0]])

        sga = get_strip(pa, ea, ss_a)
        sgb = get_strip(pb, eb, ss_b)
        if sga is None or sgb is None:
            return

        # Auto-hide: re-derive the FULL hidden set for each patch from ALL
        # blend bands on it, using the current splits. Cell indices shift
        # whenever a later strip adds a split and re-subdivides the patch,
        # so per-strip sets recorded earlier would go stale (#33). The
        # corner cell at a 4-patch junction is never part of a band.
        def linked_strips(p):
            for o in fp.Document.Objects:
                if (o is not fp and getattr(o, "object_type", "") == "BlendStrip"
                        and getattr(o, "PatchA", None) and getattr(o, "PatchB", None)
                        and (o.PatchA is p or o.PatchB is p)):
                    yield o

        for p_i in (pa, pb):
            e_i = ea if p_i is pa else eb
            ss_i = ss_a if p_i is pa else ss_b
            idxs = set(band_cells(p_i, e_i, ss_i))
            for st in linked_strips(p_i):
                other = st.PatchB if st.PatchA is p_i else st.PatchA
                e_j, ss_j = _patch_side(p_i, other, fp.tolerance)
                if e_j:
                    idxs |= set(band_cells(p_i, e_j, ss_j))
            # corner cells owned by corner blends on this patch (#28): the
            # strip must not wipe them, else the display ping-pongs between
            # the strip writing its band cells and the corner blend
            # re-unioning the corner cell on the next recompute pass.
            try:
                from SilkCorner import CornerBlend as _CB
                for ob in fp.Document.Objects:
                    if getattr(ob, "object_type", "") != "CornerBlend":
                        continue
                    for so in list(getattr(ob, "Strips", []) or []):
                        if so.PatchA is p_i or so.PatchB is p_i:
                            cc = _CB._corner_cell(
                                p_i, list(ob.Strips), fp.tolerance)
                            if cc[0] is not None and cc[1] is not None:
                                iu_c, iv_c, nu, nv = cc
                                idxs.add(iu_c * nv + iv_c)
                            break
            except ImportError:
                pass
            try:
                p_i.removeProperty("_HideSubgridIdx")  # superseded by the list
            except Exception:
                pass
            if not hasattr(p_i, "_HiddenSubgridIdxs"):
                p_i.addProperty("App::PropertyIntegerList", "_HiddenSubgridIdxs", "Internal",
                                "subgrid cell indices hidden by blends")
                p_i.setEditorMode("_HiddenSubgridIdxs", 1)
            p_i._HiddenSubgridIdxs = sorted(idxs)

        # Step 6: corner-to-parameter mapping
        cmap = {"U0": {0: 0, 1: 3}, "U1": {2: 3, 3: 0},
                "V0": {0: 0, 3: 3}, "V1": {1: 0, 2: 3}}

        # Seam alignment (#30): the matched corners fix the two seam ends;
        # the middle rows must follow the same alignment. Both patches can
        # parametrize the shared edge in the same physical direction
        # (identity) or opposite (reversed) — it depends on the geometry,
        # not on the edge type. Inconsistent corner pairs = twisted input.
        identity = None
        for lc_idx, rc_idx in pairs:
            la = cmap[ea].get(lc_idx)
            if la is None:
                continue
            is_id = (la == cmap[eb][rc_idx])
            if identity is None:
                identity = is_id
            elif is_id != identity:
                return
        if identity is None:
            return

        # Step 7: blend each paired row/column
        # Subgraph flat = poles[U][V] = flat[U*4 + V]
        # If shared edge runs ALONG U (row): perpendicular = V → take COLUMNS (const U)
        # If shared edge runs ALONG V (col): perpendicular = U → take ROWS (const V)
        blend_poles = []
        # #31: strip index 0 sits at param 0 of the strip window. For ss=0 the
        # shared edge is at index 0; for ss=1 it is at index 3. Build each row
        # in shared→outer order, then orient: blend_poly_2x4_1x6 needs
        # poles_0 outer→shared and poles_1 shared→outer.
        va = range(4) if ss_a == 0 else range(3, -1, -1)   # left:  shared→outer
        vb = range(4) if ss_b == 0 else range(3, -1, -1)   # right: shared→outer
        for li in range(4):
            # Left strip: shared edge → outward, then reverse for outer→shared
            if ea[0] == "U":  # shared along U → take COLUMNS
                l_rev = list(reversed([sga[li * 4 + v] for v in va]))
            else:  # shared along V → take ROWS
                l_rev = list(reversed([sga[v * 4 + li] for v in va]))

            # Map left param index to right param index: corner pairs fix
            # the seam ends, the inferred alignment governs the middle.
            for lc_idx, rc_idx in pairs:
                if li == cmap[ea].get(lc_idx):
                    ri = cmap[eb][rc_idx]
                    break
            else:
                ri = li if identity else 3 - li

            # Right strip: shared edge → outward (keep shared→outer direction)
            if eb[0] == "U":  # shared along U → take COLUMNS
                rc = [sgb[ri * 4 + v] for v in vb]
            else:  # shared along V → take ROWS
                rc = [sgb[v * 4 + ri] for v in vb]

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
            fp.Shape = Part.Compound(shapes) if shapes else Part.Shape()
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

        # Auto-update chain (#28): touch corner blends fed by this strip.
        # Next doc.recompute() runs them against the updated strip poles.
        for o in fp.Document.Objects:
            if (getattr(o, "object_type", "") == "CornerBlend"
                    and fp in list(getattr(o, "Strips", []) or [])):
                o.touch()


class BlendStripViewProvider:
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
        BlendStripViewProvider(obj.ViewObject)
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
