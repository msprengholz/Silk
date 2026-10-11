"""
SilkBlend — the blend strip between two adjacent patches.

Two object types share ONE implementation (ticket #39):

  BlendStrip  the legacy type (#28/#30/#31/#32/#33 ring strips);
              retained for old-document restore only (ticket
              #42: nothing creates it anymore -- the
              Silk_CreateBlend GUI command and the ops layer
              build the unified Blend).
  Blend       the unified blend (#39): same strip algorithm, plus an
              optional Edge property that pins the seam geometrically,
              object_type "Blend".

The whole strip algorithm lives ONCE in the module-level run_blend(fp);
both classes' execute() delegate to it (guarded against recursion).
A blend is fed ONLY patch subgrid cells -- never another blend (the
input type gate refuses Blend/BlendStrip/CornerBlend inputs with an
empty valid object + console error, never a crash).

Usage:
  1. Select two patches (unified Patch, Patch44 or Patch33) --
     or a single shared Edge (#45: the command resolves its
     adjacent pair via SilkWorkflowOps.create_blend_by_edge)
  2. Run Silk_CreateBlend command (or SilkWorkflowOps.create_blend)
  3. Blend auto-updates when patches' USplits/VSplits change
"""

import FreeCAD
import Part
from FreeCAD import Gui
import ArachNURBS as AN
from popup import tipsDialog

from SilkMachinery import patch_side as _patch_side, band_cells, \
    ensure_hidden_idxs_property, shared_seam, _EDGE_OF, _cyclic_adjacent

import os, Silk_dummy
path_Silk = os.path.dirname(Silk_dummy.__file__)
path_Silk_icons = os.path.join(path_Silk, "Resources", "Icons")
iconPath = path_Silk_icons + "/BlendStrip.svg"


# Every behavioral object_type scan in the workbench accepts BOTH blend
# types (a document may mix the unified Blend with legacy BlendStrips
# during migration, #39 decision E).
BLEND_TYPES = ("Blend", "BlendStrip")

# Patch types a blend may be fed (criterion: a Blend never eats a Blend).
PATCH_TYPES = ("Patch", "Patch44", "Patch33")


# ---- shared plumbing ----------------------------------------------------

def _clear_result(fp):
    """Leave the object empty but valid."""
    fp.Poles = []
    fp.Weights = []
    fp.Legs = []
    fp.Shape = Part.Shape()


def _refuse(fp, msg):
    """Graceful refusal: console error + empty valid object, no crash."""
    FreeCAD.Console.PrintError("Silk: %s\n" % msg)
    _clear_result(fp)


def _seam_from_edge(a_c, b_c, ep0, ep1, tol):
    """Pin the seam from an explicit Edge's endpoint poles (#39 decision
    C): both endpoints must sit (within tol) on a distinct, cyclically
    adjacent corner pair of BOTH patches. Purely geometric -- the Edge
    object identity is irrelevant (patches may share geometry without
    sharing the same Edge object). Returns (ea, eb, pairs) or None.
    """
    a0 = [i for i in range(4) if (a_c[i] - ep0).Length < tol]
    a1 = [i for i in range(4) if (a_c[i] - ep1).Length < tol]
    b0 = [i for i in range(4) if (b_c[i] - ep0).Length < tol]
    b1 = [i for i in range(4) if (b_c[i] - ep1).Length < tol]
    for i0 in a0:
        for i1 in a1:
            if not _cyclic_adjacent(i0, i1):
                continue
            if (a_c[i0] - a_c[i1]).Length < tol:
                continue  # degenerate pair on A (pointed apex)
            for j0 in b0:
                for j1 in b1:
                    if not _cyclic_adjacent(j0, j1):
                        continue
                    if (b_c[j0] - b_c[j1]).Length < tol:
                        continue  # degenerate pair on B
                    ea = _EDGE_OF.get((i0, i1))
                    eb = _EDGE_OF.get((j0, j1))
                    if ea and eb:
                        return ea, eb, [(i0, j0), (i1, j1)]
    return None


# ---- the blend algorithm (single implementation, #39 decision B) --------

def run_blend(fp):
    """Build the 2-patch blend strip on fp (shared by Blend and
    BlendStrip). Silent return leaves the object untouched (missing /
    unfilled inputs); _refuse paths leave it empty/valid.
    """
    pa, pb, tol = fp.PatchA, fp.PatchB, fp.tolerance
    if not pa or not pb:
        return

    # Input gate (#39 criterion 4/G): a blend is fed only patch subgrid
    # cells -- never a Blend/BlendStrip/CornerBlend or other object.
    for p in (pa, pb):
        if getattr(p, "object_type", None) not in PATCH_TYPES:
            _refuse(fp, "blend inputs must be patches, but %s carries "
                        "object_type=%r" % (p.Name,
                                            getattr(p, "object_type", None)))
            return

    # Ensure patches are up to date and will recompute their Shape with auto-hide
    pa.recompute()
    pb.recompute()

    for p in (pa, pb):
        if not getattr(getattr(p, "Proxy", None), "_base_surface", None):
            return

    # Steps 1+2: find the shared seam (edge type U0/U1/V0/V1 per patch +
    # the two matched corner pairs). With an explicit Edge the seam is
    # pinned from its endpoint poles; otherwise it is auto-detected.
    # Both paths are robust against degenerate pointed corners: a
    # pointed patch carries its apex twice in [Poles[0], Poles[3],
    # Poles[15], Poles[12]] (Poles[0] == Poles[12]), which naive
    # corner matching double-counts (#39 criterion 6).
    a_c = [pa.Poles[0], pa.Poles[3], pa.Poles[15], pa.Poles[12]]
    b_c = [pb.Poles[0], pb.Poles[3], pb.Poles[15], pb.Poles[12]]
    edge = getattr(fp, "Edge", None)
    if edge is not None:
        ep = list(getattr(edge, "Poles", []) or [])
        seam = _seam_from_edge(a_c, b_c, ep[0], ep[3], tol) if len(ep) >= 4 \
            else None
        if seam is None:
            _refuse(fp, "edge %s is not a shared boundary of both "
                         "patches (endpoint poles must sit on a corner "
                         "pair of each)" % getattr(edge, "Name", "?"))
            return
    else:
        seam = shared_seam(a_c, b_c, tol)
        if seam is None:
            return
    ea, eb, pairs = seam

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

    # Step 5: the blend band comes from the patch's own subgrid cells —
    # the UV splits already subdivide the surface, so pick the seam-
    # adjacent cell(s) instead of re-segmenting the base surface (see
    # module-level band_cells; #33). The 0.1x0.1 corner cell at a
    # 4-patch junction is not part of the band (reserved for the corner
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
    # Every scan accepts BOTH blend types (legacy + unified mix freely).
    def linked_strips(p):
        for o in fp.Document.Objects:
            if (o is not fp and getattr(o, "object_type", "") in BLEND_TYPES
                    and getattr(o, "PatchA", None) and getattr(o, "PatchB", None)
                    and (o.PatchA is p or o.PatchB is p)):
                yield o

    for p_i in (pa, pb):
        e_i = ea if p_i is pa else eb
        ss_i = ss_a if p_i is pa else ss_b
        idxs = set(band_cells(p_i, e_i, ss_i))
        for st in linked_strips(p_i):
            other = st.PatchB if st.PatchA is p_i else st.PatchA
            if getattr(other, "object_type", None) not in PATCH_TYPES:
                continue
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
        ensure_hidden_idxs_property(p_i)
        p_i._HiddenSubgridIdxs = sorted(idxs)

    # Step 6: corner-to-parameter mapping
    cmap = {"U0": {0: 0, 1: 3}, "U1": {2: 3, 3: 0},
            "V0": {0: 0, 3: 3}, "V1": {1: 0, 2: 3}}

    # Seam alignment (#30): the matched corners fix the two seam ends;
    # the middle rows must follow the same alignment. Both patches can
    # parametrize the shared edge in the same physical direction
    # (identity) or opposite (reversed) — it depends on the geometry,
    # not on the edge type. Inconsistent corner pairs = twisted input.
    # `pairs` holds only the seam's two matched corner pairs; the cmap
    # lookups guard both sides (degenerate pointed corners must never
    # KeyError).
    identity = None
    for lc_idx, rc_idx in pairs:
        la = cmap[ea].get(lc_idx)
        rb = cmap[eb].get(rc_idx)
        if la is None or rb is None:
            return
        is_id = (la == rb)
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
            rb = cmap[eb].get(rc_idx)
            if rb is not None and li == cmap[ea].get(lc_idx):
                ri = rb
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


def _guarded_execute(fp):
    """Recursion guard + shared execute body for both blend types."""
    proxy = fp.Proxy
    if getattr(proxy, "_in_execute", False):
        return
    proxy._in_execute = True
    try:
        run_blend(fp)
    finally:
        proxy._in_execute = False


def _on_changed(fp, prop):
    if prop == "tolerance" or prop == "Edge" or prop.startswith("Patch"):
        if 'Restore' not in fp.State and getattr(fp, "PatchA", None):
            fp.recompute()


# ---- object types --------------------------------------------------------

class BlendStrip:
    """FeaturePython: joins two Patch44 objects at their shared edge
    (legacy type; the unified Blend supersedes it, #39)."""

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
        _on_changed(fp, prop)

    def execute(self, fp):
        _guarded_execute(fp)


class Blend(BlendStrip):
    """FeaturePython (#39): the unified blend — the same 2-patch strip
    algorithm as BlendStrip (shared run_blend), fed only patch subgrid
    cells, plus an optional Edge property pinning the seam."""

    def __init__(self, obj, patch_a, patch_b, edge=None):
        obj.addProperty("App::PropertyLink", "PatchA", "Inputs", "first patch").PatchA = patch_a
        obj.addProperty("App::PropertyLink", "PatchB", "Inputs", "second patch").PatchB = patch_b
        obj.addProperty("App::PropertyLink", "Edge", "Inputs",
                        "shared boundary edge pinning the seam (optional)").Edge = edge
        obj.addProperty("App::PropertyFloat", "tolerance", "Inputs",
                        "corner matching tolerance").tolerance = 0.01
        obj.addProperty("App::PropertyVectorList", "Poles", "Outputs", "blend grid poles").Poles
        obj.addProperty("App::PropertyFloatList", "Weights", "Outputs", "blend grid weights").Weights
        obj.addProperty("Part::PropertyGeometryList", "Legs", "Outputs", "grid segments").Legs
        obj.addProperty("App::PropertyString", "object_type", "", "").object_type = "Blend"
        obj.setEditorMode("object_type", 1)
        obj.Proxy = self
        self._in_execute = False


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


# One blend color/icon per type today (#39 spec: per-fill icon/color
# proliferation is retired).
BlendViewProvider = BlendStripViewProvider


class CreateBlend:
    """GUI command — select either 1 shared Edge or 2 adjacent
    patches -> unified Blend (ticket #42: the legacy BlendStrip
    construction is retired; the command builds the unified Blend,
    the same strip algorithm via the shared run_blend).

    Ticket #45: 1 selected Edge delegates the whole contract to the
    #44 resolver SilkWorkflowOps.create_blend_by_edge (identity-only
    adjacent-pair resolution, per-seam idempotency, graceful refusals,
    the edge as the geometric seam pin) — this class only reads the
    selection and reports. 2 selected patches keep the direct pair
    construction; every other selection shape refuses with a
    "Silk: ..." console error, no side effects."""

    def GetResources(self):
        return {'Pixmap': iconPath, 'MenuText': 'Silk Blend',
                'ToolTip': 'Create a blend from 1 selected Edge or 2 '
                           'selected adjacent patches.'}

    def Activated(self):
        sel = Gui.Selection.getSelection()
        edges = [o for o in sel
                 if getattr(o, "object_type", None) == "Edge"]
        patches = [o for o in sel
                   if getattr(o, "object_type", None) in PATCH_TYPES]

        if len(sel) == 1 and len(edges) == 1:
            # 1 selected Edge (#45): immediate creation through the
            # #44 resolver -- no confirmation dialog (undo is the
            # safety net, a settled decision). The resolver owns every
            # message: its refusals and the idempotent "already
            # blended by X" no-op reach the user unmodified; we only
            # announce a NEW blend on top of that.
            from SilkWorkflowOps import create_blend_by_edge
            doc = FreeCAD.ActiveDocument
            known = {o.Name for o in doc.Objects}
            blend = create_blend_by_edge(edges[0])
            if blend is None:
                return  # resolver already printed its refusal message
            if blend.Name not in known:
                FreeCAD.Console.PrintMessage(
                    f"{blend.Name} created across {edges[0].Name}\n")
            # else: the resolver returned the EXISTING blend (no-op) --
            # its "already blended" message already reached the user;
            # adding a message here would double-report a non-event.
            return

        if len(sel) == 2 and len(patches) == 2:
            doc = FreeCAD.ActiveDocument
            obj = doc.addObject("Part::FeaturePython", "Blend")
            Blend(obj, sel[0], sel[1])
            BlendStripViewProvider(obj.ViewObject)
            obj.ViewObject.LineWidth = 2.00
            obj.ViewObject.LineColor = (0.00, 1.00, 0.00)
            obj.ViewObject.PointSize = 5.00
            obj.ViewObject.DisplayMode = "Shaded"
            obj.ViewObject.ShapeColor = (0.00, 1.00, 0.00)
            obj.ViewObject.Transparency = 30
            doc.recompute()
            FreeCAD.Console.PrintMessage(f"Blend created: {obj.Name}\n")
            return

        FreeCAD.Console.PrintError(
            "Silk: Blend requires either 1 selected Edge or 2 selected "
            "patches (got %d selected: %d Edge, %d patch).\n"
            % (len(sel), len(edges), len(patches)))

    def IsActive(self):
        return Gui is not None


Gui.addCommand("Silk_CreateBlend", CreateBlend())
