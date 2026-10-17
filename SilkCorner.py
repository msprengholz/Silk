"""
SilkCorner — CornerBlend FeaturePython for the 4-subgrid corner fill (#28, #91).

Where 4 Patch objects meet at a central junction, each contributes its
corner subgrid cell (excluded from the ring blend bands by #33). The
CornerBlend takes the ring's 3 or 4 Blend strips (DAG: patch -> strip ->
corner blend) and builds Silk's real corner: the four consecutive strip
pairs each make a 3x3 subgrid (`SubGrid33_2Grid64`), the four subgrids
assemble into a 6x6 (`ControlGrid66_4Sub`), and the surface comes from
`CubicSurface_66` (never `buildFromPolesMultsKnots`).

#91: the geometry machinery is a PURE port of the two upstream classes
into Silk's own code -- `SilkMachinery` holds the ring resolver and the
subgrid chain (`corner_ring`, `corner_grid`, `subgrid33_2grid64`,
`control_grid66_4sub`, `orient_junction_row`), and this module holds the
strip-to-grid derivation shared by the object and the ops validator
(`corner_inputs`, `corner_from_strips`). Those upstream classes are
restore shims (#7) and are never called at runtime; they remain the
pole-for-pole oracle the tests compare against. The old #28 fill
(`ControlGrid66_4`, a boundary-curve constructor whose interior was
difference propagation) is gone. Ticket-foldfix adds the one deliberate
deviation from the port: `SilkMachinery.smooth_degenerate_cap` re-solves
the member-side interior rows of a ring that carries a collapsed side,
because upstream's subgrid extrapolation past that side folds the cap on
the cube-corner fixture; on the ordinary 4-valent ring it is a
byte-identical no-op.

Usage:
  1. Build the 3 or 4 ring Blend strips
  2. Run create_corner_blend(*ring_blends)
  3. The corner blend auto-updates when any linked strip recomputes
"""

import FreeCAD
from FreeCAD import Gui
import Part
import ArachNURBS as AN

from SilkBlend import band_cells, side_and_end, seam_direction, BLEND_TYPES
from SilkMachinery import (build_intervals, split_pair, corner_ring,
    corner_grid, orient_junction_row, corner_ring_3,
    control_grid64_3_1, reverse_grid_rows, set_grid_display)

import os, Silk_dummy
path_Silk = os.path.dirname(Silk_dummy.__file__)
path_Silk_icons = os.path.join(path_Silk, "Resources", "Icons")
iconPath = path_Silk_icons + "/ControlGrid66_4Sub.svg"

# The corner blend's own default tolerance for the strip-side / corner-cell
# derivation (matches the object's `tolerance` property default).
CORNER_DEFAULT_TOL = 0.01

# The shared-corner match tolerance of the subgrid chain. Upstream's
# `SubGrid33_2Grid64` uses `default_tol` = 1e-6; the corner poles are
# exact, so a tight tolerance is right and cannot match two corners.
CORNER_TOL = 1e-6


# ---- the pure corner derivation (#91) ------------------------------------
#
# Both the object's `execute()` and the ops-layer validator run these, so
# there is exactly ONE definition of "what corner does this strip set
# make". No document, no object, no console here.

def _corner_cell_net(p, cell):
    """Patch p's ring-corner subgrid cell as (flat poles, flat weights) in
    the row-major 4x4 order `control_grid64_3_1` reads, or (None, None).

    `cell` is the patch's entry from `corner_inputs`' `corner_cells`
    (`(pth, iu_c, iv_c, nu, nv)`). The cell is extracted through the
    patch's own `getSubgrid`, so the RATIONAL weights of the segmented
    cell come with the poles -- the same net the patch's `_subgrids`
    holds, plus its weights. This is the ring's corner cell: the region
    the band setbacks leave for the corner fill, whose outer corner is
    the point the ring's boundary loop passes through.
    """
    if cell is None:
        return None, None
    pth, iu_c, iv_c, _nu, nv = cell
    if pth is not p:
        return None, None
    us = build_intervals(*split_pair(p, "U"))
    vs = build_intervals(*split_pair(p, "V"))
    if not (0 <= iu_c < len(us) and 0 <= iv_c < len(vs)):
        return None, None
    getter = getattr(getattr(p, "Proxy", None), "getSubgrid", None)
    if getter is None:
        return None, None
    u0, u1 = us[iu_c]
    v0, v1 = vs[iv_c]
    poles2d, weights2d = getter(u0, u1, v0, v1)
    if not poles2d or not weights2d:
        return None, None
    try:
        poles = [poles2d[r][c] for r in range(4) for c in range(4)]
        weights = [float(weights2d[r][c]) for r in range(4)
                   for c in range(4)]
    except (IndexError, TypeError):
        return None, None
    if len(poles) != 16 or len(weights) != 16:
        return None, None
    return poles, weights


def _shared_patch(a, b):
    """The one patch two ring strips both touch, or None when they touch
    none or two (an ambiguous pair -- the corner cannot name a side then)."""
    common = []
    for x in (getattr(a, "PatchA", None), getattr(a, "PatchB", None)):
        if x is not None and x in (getattr(b, "PatchA", None),
                                   getattr(b, "PatchB", None)):
            common.append(x)
    return common[0] if len(common) == 1 else None


def _orient_ring_columns(grids, ordered):
    """Flip each strip's 6 columns so the ring's shared patch lies on the
    SAME side of every strip.

    A strip's 6-pole axis runs PatchA's outer -> shared seam -> PatchB's
    outer, so which of the two patches lands at column 0 is whichever the
    user handed `create_blend` FIRST -- arbitrary, and a blend is the same
    surface either way round. The corner chain instead reads the shared
    corner from a fixed column (grid_i's col 5 against grid_(i+1)'s col 0),
    so a ring whose blends do not run as a directed cycle (PatchB of one
    strip IS PatchA of the next) cannot assemble. Flipping the columns of
    the strips that run the other way -- column c -> 5 - c, a
    reparameterization of the across-seam axis, not a geometry change --
    turns any ring into that cycle. On a ring already directed this way it
    changes nothing. It is applied only when the ring does not assemble as
    stored (see `_assemble_square_ring` / `_tri_ring_member`), so the
    documented rings keep their exact poles."""
    n = len(grids)
    out = []
    for i, (poles, weights) in enumerate(grids):
        nxt = _shared_patch(ordered[i], ordered[(i + 1) % n])
        if nxt is not None and getattr(ordered[i], "PatchA", None) is nxt:
            poles = [poles[r * 6 + (5 - c)]
                     for r in range(4) for c in range(6)]
            weights = [weights[r * 6 + (5 - c)]
                       for r in range(4) for c in range(6)]
        out.append((poles, weights))
    return out


def _member_ring(base_grids, ordered, patch, member):
    """The 4-grid ring with `member` at `patch`'s corner.

    The triangular 4th member stands in for the blend the missing fourth
    surface would have contributed, so it sits between the TWO ring
    strips that meet at `patch` -- not blindly appended, because
    `corner_ring_3`'s direction follows document order and a ring built
    the other way round needs the member at the mirrored position. The
    ring's first grid (and so the canonical start both `corner_grid` and
    the object's own derivation use) is preserved."""
    touching = [i for i, s in enumerate(ordered)
                if getattr(s, "PatchA", None) is patch
                or getattr(s, "PatchB", None) is patch]
    for i in touching:
        j = (i + 1) % len(ordered)
        if j != i and j in touching:
            return base_grids[:i + 1] + [member] + base_grids[i + 1:]
    return base_grids + [member]


def _assemble_square_ring(base, ordered):
    """(grids, None) for a 4-valent corner: `base` when it already
    assembles, else the ring with the columns normalized (`base` is tried
    first so a ring that already works keeps its exact poles), else
    (None, corner_grid's own refusal for the stored orientation)."""
    p36, _w, why = corner_grid(base, CORNER_TOL)
    if p36 is not None:
        return base, None
    flipped = _orient_ring_columns(base, ordered)
    p36, _w, _why = corner_grid(flipped, CORNER_TOL)
    if p36 is not None:
        return flipped, None
    return None, why


def _tri_ring_member(base_grids, ordered, patches, corner_cells):
    """The first 4-grid ring `corner_grid` accepts for a 3-valent corner:
    `base_grids` (the three strips) plus the triangular 4th member built
    from a patch's ring corner CELL -- never the full 4x4 base net, whose
    corners are the patch vertices -- across every corner index and
    reversal. Returns the 4-grid ring or None."""
    for pth in patches:
        poles_c, weights_c = _corner_cell_net(pth, corner_cells.get(pth.Name))
        if poles_c is None:
            continue
        for corner in range(4):
            for rev in (False, True):
                mp, mw = control_grid64_3_1(poles_c, weights_c, corner)
                if mp is None:
                    continue
                if rev:
                    mp, mw = reverse_grid_rows(mp, mw)
                member = (list(mp), list(mw))
                cand = _member_ring(base_grids, ordered, pth, member)
                p36, _w, _why = corner_grid(cand, CORNER_TOL)
                if p36 is not None:
                    return cand
    return None


def corner_inputs(strips, tol=CORNER_DEFAULT_TOL):
    """The four strips' 24-pole grids in ring order, each with its
    junction-end row at V = 3, plus the corner cell of each patch.

    Returns (grids, corner_cells, None) or (None, None, reason). Every
    refusal names the strip (or patch) that caused it.
    """
    strips = list(strips)
    is_tri = (len(strips) == 3)
    if is_tri:
        ordered, why = corner_ring_3(strips)
    else:
        ordered, why = corner_ring(strips)
    if ordered is None:
        return None, None, why
    grids = []
    corner_cells = {}
    for s in ordered:
        pa = getattr(s, "PatchA", None)
        pb = getattr(s, "PatchB", None)
        if pa is None or pb is None:
            return None, None, "blend %s has no patches" % s.Name
        e_a, ss_a = side_and_end(s, pa, tol)
        e_b, ss_b = side_and_end(s, pb, tol)
        if not e_a or not e_b:
            return None, None, ("blend %s: no shared edge between %s and %s"
                                % (s.Name, pa.Name, pb.Name))
        # The two patches can parameterize their shared seam in the same
        # direction (identity) or opposite (reversed) -- it depends on
        # the geometry and on each patch's stored cycle, not on the edge
        # type. A reversed seam names the SAME junction at the mirrored
        # row of the patch's seam-parallel axis, so the two patches'
        # junction-end rows are compared ACROSS that reflection.
        # Comparing the raw indices is what reports a legitimately
        # reversed seam as a twisted input.
        identity = seam_direction(s, tol)
        bca = band_cells(pa, e_a, ss_a)
        bcb = band_cells(pb, e_b, ss_b)
        if len(bca) != 1 or len(bcb) != 1:
            return None, None, ("blend %s: its band must cover exactly 1 cell "
                                "per side (got %d/%d)"
                                % (s.Name, len(bca), len(bcb)))
        li_map = {}
        for pth, e, bc in ((pa, e_a, bca), (pb, e_b, bcb)):
            iu_c, iv_c, nu, nv = CornerBlend._corner_cell(pth, ordered, tol)
            if iu_c is None or iv_c is None:
                return None, None, ("patch %s: corner cell at the 4-patch "
                                    "junction not found" % pth.Name)
            iu_b, iv_b = divmod(bc[0], nv)
            # corner-end row: 3 if the corner cell sits above the band
            # cell along the band axis, else 0
            if e[0] == "U":
                li_map[pth.Name] = 3 if iu_c > iu_b else 0
            else:
                li_map[pth.Name] = 3 if iv_c > iv_b else 0
            corner_cells[pth.Name] = (pth, iu_c, iv_c, nu, nv)
        if li_map[pa.Name] != (3 - li_map[pb.Name] if identity is False
                               else li_map[pb.Name]):
            return None, None, ("blend %s: its two patches disagree about "
                                "which end is the junction (twisted input)"
                                % s.Name)
        poles = list(getattr(s, "Poles", None) or [])
        weights = list(getattr(s, "Weights", None) or [])
        if len(poles) != 24 or len(weights) != 24:
            return None, None, ("blend %s: expected a 24-pole grid, got %d "
                                "poles / %d weights"
                                % (s.Name, len(poles), len(weights)))
        grids.append(orient_junction_row(poles, weights, li_map[pa.Name]))
    if is_tri:
        patches = []
        for s in ordered:
            for pth in (getattr(s, "PatchA", None), getattr(s, "PatchB", None)):
                if pth is not None and pth not in patches:
                    patches.append(pth)
        # The stored column orientation of a strip is arbitrary (which
        # patch the user handed create_blend first), so the member search
        # runs once as stored -- the documented rings assemble there --
        # and, only if that cannot, once with the ring's columns
        # normalized.
        ring = None
        for base_grids in (list(grids),
                           _orient_ring_columns(grids, ordered)):
            ring = _tri_ring_member(base_grids, ordered, patches,
                                    corner_cells)
            if ring is not None:
                break
        if ring is None:
            return None, None, "could not build triangular 4th member"
        grids = ring
    else:
        grids, why = _assemble_square_ring(grids, ordered)
        if grids is None:
            return None, None, why
    return grids, corner_cells, None


def corner_from_strips(strips, tol=CORNER_DEFAULT_TOL):
    """The full corner: four strips -> (poles36, weights36, corner_cells).

    Returns (p36, w36, corner_cells, None) or (None, None, None, reason).
    """
    grids, corner_cells, why = corner_inputs(strips, tol)
    if grids is None:
        return None, None, None, why
    p36, w36, why = corner_grid(grids, CORNER_TOL)
    if p36 is None:
        return None, None, None, why
    return p36, w36, corner_cells, None


class CornerBlend:
    """FeaturePython: fills the central region where 4 patches meet."""

    def __init__(self, obj, strips):
        obj.addProperty("App::PropertyLinkList", "Strips", "Inputs",
                        "ring blend strips in cyclic order"
                        ).Strips = list(strips)
        obj.addProperty("App::PropertyFloat", "tolerance", "Inputs",
                        "corner matching tolerance").tolerance = CORNER_DEFAULT_TOL
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
            # #83: read the strip's side off the STRIP (which carries the
            # pinned Edge of a unified Blend), not off the patch pair. A
            # patch pair sharing two seams names the same side twice, so a
            # corner cell derived through `patch_side` can be taken on the
            # wrong seam's band.
            e, ss = side_and_end(s, p, tol)
            if not e:
                continue
            if e[0] == "U":
                iv_c = nv - 1 if e[1] == "1" else 0
            else:
                iu_c = nu - 1 if e[1] == "1" else 0
        return iu_c, iv_c, nu, nv

    def _refuse(self, fp, why):
        """Refuse loudly and leave the object EMPTY rather than stale: a
        corner that can no longer be built shows nothing and says why."""
        fp.Poles = []
        fp.Weights = []
        fp.Legs = []
        fp.Shape = Part.Shape()
        FreeCAD.Console.PrintError(
            "Silk: corner blend %s: %s\n" % (fp.Name, why))

    # ---- execution --------------------------------------------------

    def _do_execute(self, fp):
        p36, w36, corner_cells, why = corner_from_strips(
            list(fp.Strips), fp.tolerance)
        if p36 is None:
            self._refuse(fp, why)
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

        fp.Poles = p36
        fp.Weights = w36
        fp.Legs = AN.drawGrid(fp.Poles, 6)

        # corner surface via AN.CubicSurface_66 (never
        # buildFromPolesMultsKnots) -- it reads Grid.Poles / Grid.Weights,
        # so the cross-multiplied rational weights are carried into it.
        doc = fp.Document
        surf_shape = None
        tmp_surf = None
        try:
            tmp_surf = doc.addObject("Part::FeaturePython", "_cb_surf_tmp")
            AN.CubicSurface_66(tmp_surf, fp)
            tmp_surf.recompute()
            surf_shape = tmp_surf.Shape
        finally:
            # the temp carrier must not survive a failed build
            if tmp_surf is not None and doc.getObject(tmp_surf.Name) is not None:
                try:
                    doc.removeObject(tmp_surf.Name)
                except Exception:
                    pass

        if not surf_shape or not hasattr(surf_shape, "Faces") \
                or not surf_shape.Faces:
            fp.Shape = Part.Shape()  # no surface to show; the grid is a view node
            return

        # Shape is GEOMETRY ONLY (#108): the corner surface. The control
        # grid is a DISPLAY concern -- the view provider draws it as a Coin
        # node (SilkMachinery.set_grid_display reads fp.Legs), so it is not
        # part of Shape, not exported, and not selectable.
        fp.Shape = surf_shape


class CornerBlendViewProvider:
    def __init__(self, vobj):
        vobj.Proxy = self

    def getIcon(self):
        return iconPath

    def attach(self, vobj):
        self.ViewObject = vobj
        self.Object = vobj.Object
        self._refresh_grid(self.Object, vobj)

    def _refresh_grid(self, obj, vobj):
        """Draw the corner's control grid as a Coin node (#108).

        The grid is no longer part of Shape (execute keeps only the
        surface); the view provider draws it from the stored `Legs`, in the
        corner's own LineColor / LineWidth. A CornerBlend has no grid
        toggle, so the grid stays drawn -- exactly the visibility it had
        inside Shape. Headless (no ViewObject) is a silent no-op."""
        if obj is None or vobj is None:
            return
        set_grid_display(self, vobj, list(getattr(obj, "Legs", None) or []),
                         bool(getattr(obj, "ShowGrid", True)),
                         getattr(vobj, "LineColor", None),
                         getattr(vobj, "LineWidth", None))

    def updateData(self, obj, prop):
        if prop in ("Legs", "Shape"):
            self._refresh_grid(obj, getattr(self, "ViewObject", None))
        return True

    def onChanged(self, vobj, prop):
        if prop in ("LineColor", "LineWidth"):
            self._refresh_grid(getattr(vobj, "Object", None), vobj)

    def __getstate__(self):
        return None

    def __setstate__(self, state):
        return None


class CreateCornerBlend:
    """GUI command — select the 3 or 4 blend strips that ring a shared
    junction -> CornerBlend (ticket #91).

    The whole contract (adjudicating the ring, refusing a non-junction or
    repeated strip set by name, the idempotent "already has a corner"
    no-op) lives in SilkWorkflowOps.create_corner_blend. This class only
    reads the selection, opens the undo transaction the toolbar triad did
    not (#91), and reports."""

    def GetResources(self):
        return {'Pixmap': iconPath, 'MenuText': 'Silk Corner Blend',
                'ToolTip': 'Create the corner blend where three or four '
                           'blends ring one shared junction.'}

    def Activated(self):
        sel = Gui.Selection.getSelection()
        strips = [o for o in sel
                  if getattr(o, "object_type", None) in BLEND_TYPES]
        from SilkWorkflowOps import create_corner_blend
        doc = FreeCAD.ActiveDocument
        if doc is None:
            return  # nothing to put a transaction on; nothing is created
        known = {o.Name for o in doc.Objects}
        doc.openTransaction("Silk corner blend")
        try:
            corner = create_corner_blend(*strips)
        finally:
            doc.commitTransaction()
        if corner is None:
            return  # the resolver already printed its refusal
        if corner.Name not in known:
            FreeCAD.Console.PrintMessage(
                "Corner blend created: %s\n" % corner.Name)
        # else: the resolver returned the EXISTING corner (no-op) -- its
        # own message already reached the user; do not double-report.

    def IsActive(self):
        return Gui is not None


Gui.addCommand("Silk_CreateCornerBlend", CreateCornerBlend())
