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
    band_diagnosis, ensure_hidden_idxs_property, shared_seam, \
    split_at_end, _EDGE_OF, _cyclic_adjacent

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


# ---- the seam this blend took, and the band split it owns -----------------

def _resolve_seam(fp, pa, pb, tol):
    """(ea, eb, pairs) for the seam THIS blend takes, or None.

    Pinned by `fp.Edge`'s endpoint poles when it has one, auto-detected
    from the two patches' corner poles otherwise -- exactly the two
    paths run_blend uses, extracted so the delete path can ask the same
    question and get the same answer.

    That matters because a pair sharing TWO edges (a closed ring) is
    auto-detected as only ONE of them: SilkMachinery.patch_side returns
    the first matching corner pair for both patches, so two blends on one
    pair answer the same question with the same side. A band split
    removed "by patch_side" would then be the wrong seam's.

    Both paths stay robust against degenerate pointed corners: a pointed
    patch carries its apex twice in [Poles[0], Poles[3], Poles[15],
    Poles[12]] (Poles[0] == Poles[12]), which naive corner matching
    double-counts (#39 criterion 6).
    """
    a_c = [pa.Poles[0], pa.Poles[3], pa.Poles[15], pa.Poles[12]]
    b_c = [pb.Poles[0], pb.Poles[3], pb.Poles[15], pb.Poles[12]]
    edge = getattr(fp, "Edge", None)
    if edge is not None:
        ep = list(getattr(edge, "Poles", []) or [])
        return _seam_from_edge(a_c, b_c, ep[0], ep[3], tol) if len(ep) >= 4 \
            else None
    return shared_seam(a_c, b_c, tol)


def _band_split_of(etype):
    """(property_name, end) of the split that carves the band of
    boundary side `etype` on its own patch: a seam along U fixes a V
    interval, so the band lives in VSplits (and vice versa), and the
    side's 0/1 is the end of that axis. The same two lines
    run_blend.ensure_band_split uses to write it -- derived once here so
    the writer and the remover can never disagree about which split is
    which end's."""
    return ("VSplits" if etype[0] == "U" else "USplits",
            0 if etype[1] == "0" else 1)


def _side_on(o, p):
    """The boundary side blend `o` takes on patch `p`, or None when `o`
    cannot say -- re-resolved through the SAME `_resolve_seam` run_blend
    used, so the reader and the writer of a band split can never disagree
    about which seam is whose (the two-shared-edges case: auto-detect
    alone returns the same side for both blends of a pair)."""
    seam = _resolve_seam(o, o.PatchA, o.PatchB,
                         getattr(o, "tolerance", 0.01))
    if seam is None:
        return None
    return seam[0] if o.PatchA is p else seam[1]


def _survivor_needs(doc, dying, p, prop):
    """The splits on axis `prop` of `p` that a blend OTHER than `dying`
    still needs -- one per surviving blend, read at that blend's OWN
    seam end through `_band_split_of`.

    The rule is per (patch, axis, end), which is what makes clearing a
    whole band axis safe on a patch that carries several: a patch's
    sides are U0 / U1 / V0 / V1, and two SEAMS can land on the SAME axis
    at opposite ends -- the tube's TubeA.USplits [0.1, 0.9] is exactly
    that, and so is a four-patch corner. So the values are READ OFF the
    surviving blends, never assumed to be the 0.1 / 0.9 defaults: a user
    width on the surviving seam's end is what comes back.

    A blend that cannot resolve its seam contributes nothing -- it has no
    band to keep, and inventing one would pin a split that belongs to
    nobody.
    """
    cur = list(getattr(p, prop) or [])
    keep = []
    for o in doc.Objects:
        if (o is dying
                or getattr(o, "object_type", "") not in BLEND_TYPES
                or getattr(getattr(o, "Proxy", None), "_dying", False)
                or not getattr(o, "PatchA", None)
                or not getattr(o, "PatchB", None)
                or not (o.PatchA is p or o.PatchB is p)):
            continue
        side = _side_on(o, p)
        if side is None:
            continue
        prop_o, ss_o = _band_split_of(side)
        if prop_o != prop:
            continue
        need = split_at_end(cur, ss_o)
        if need is not None and need not in keep:
            keep.append(need)
    return keep


def _corner_blend_feeds(doc, dying):
    """True when a CornerBlend still feeds off `dying`'s band (#28): its
    cells are still in use, so the axis under it must stay as it is."""
    for ob in doc.Objects:
        if getattr(ob, "object_type", "") != "CornerBlend":
            continue
        if any(s is dying for s in list(getattr(ob, "Strips", []) or [])):
            return True        # the corner blend still feeds off this band
    return False


def _drop_band_split(doc, dying, p, etype):
    """Give the band axis of patch `p` back on unblend (#71).

    #70 kept every split; #71 removed only the ONE this seam owned, by
    value. The human reversed that once more, and the reason is that in
    the wizard the Band A / Band B editors ARE the patch's USplits /
    VSplits property -- there is no other place a width can live, so
    unsetting the blend has to unset them too:

        "if i unset the blend in the wizard, then also remove the
         corresponding u or v splits value!"

    So the WHOLE band axis goes, the user's own split included, and the
    axis name comes from `_band_split_of(etype)` -- the same two lines
    run_blend.ensure_band_split writes through.

    Two things are kept, and only these two:

      * a split a SURVIVING blend still needs (`_survivor_needs`) --
        unblending one of two seams on one axis must not strip the other
        one's band;
      * the whole axis, untouched, when a CornerBlend still feeds off
        this blend (#28).

    The width is the price: re-blending a seam whose axis was cleared
    rebuilds at the default (0.1 / 0.9).
    """
    prop = _band_split_of(etype)[0]
    cur = list(getattr(p, prop) or [])
    if not cur:
        return False            # the axis carried no split: nothing to do
    if _corner_blend_feeds(doc, dying):
        return False
    # what is left is ONLY what a surviving blend still reads -- read in
    # `cur`'s own order, so the stored list stays sorted.
    left = [v for v in cur if v in _survivor_needs(doc, dying, p, prop)]
    if left == cur:
        return False            # every split on the axis is still needed
    setattr(p, prop, left)
    return True


# ---- the blend algorithm (single implementation, #39 decision B) --------

def _linked_band_cells(fp, p):
    """Band cells hidden on patch `p` by every blend linked to it EXCEPT
    `fp` itself, plus the corner cells owned by corner blends on `p`
    (#28).

    The shared derivation behind BOTH writers of _HiddenSubgridIdxs:
    run_blend (which seeds the set with fp's own band on top of this) and
    BlendStrip.onDelete (which drops fp's band entirely -- a dying blend
    owns no band, so it is skipped here and the surviving strips
    re-derive the set without it). Skipping by `_dying` is what lets a
    recompute that still reaches the dying object (it is linked until
    removeObject finishes) leave the restored set alone.
    """
    doc = fp.Document
    idxs = set()
    for o in doc.Objects:
        if (o is fp
                or getattr(o, "object_type", "") not in BLEND_TYPES
                or getattr(getattr(o, "Proxy", None), "_dying", False)
                or not getattr(o, "PatchA", None)
                or not getattr(o, "PatchB", None)
                or not (o.PatchA is p or o.PatchB is p)):
            continue
        other = o.PatchB if o.PatchA is p else o.PatchA
        if getattr(other, "object_type", None) not in PATCH_TYPES:
            continue
        e_j, ss_j = _patch_side(p, other, fp.tolerance)
        if e_j:
            idxs |= set(band_cells(p, e_j, ss_j))
    # corner cells owned by corner blends on this patch (#28): the
    # strip must not wipe them, else the display ping-pongs between
    # the strip writing its band cells and the corner blend
    # re-unioning the corner cell on the next recompute pass.
    try:
        from SilkCorner import CornerBlend as _CB
        for ob in doc.Objects:
            if getattr(ob, "object_type", "") != "CornerBlend":
                continue
            for so in list(getattr(ob, "Strips", []) or []):
                if so.PatchA is p or so.PatchB is p:
                    cc = _CB._corner_cell(
                        p, list(ob.Strips), fp.tolerance)
                    if cc[0] is not None and cc[1] is not None:
                        iu_c, iv_c, nu, nv = cc
                        idxs.add(iu_c * nv + iv_c)
                    break
    except ImportError:
        pass
    return idxs


def run_blend(fp):
    """Build the 2-patch blend strip on fp (shared by Blend and
    BlendStrip). Silent return leaves the object untouched (missing /
    unfilled inputs); _refuse paths leave it empty/valid.
    """
    # A dying blend owns no band: if a recompute still reaches it before
    # removeObject finishes unlinking it, it must not re-hide the band
    # onDelete just restored (see BlendStrip.onDelete).
    if getattr(getattr(fp, "Proxy", None), "_dying", False):
        return
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
    # the two matched corner pairs). Resolved by the shared _resolve_seam
    # -- the Edge property pins it, otherwise it is auto-detected -- so
    # the delete path can identify the SAME seam later (#71).
    seam = _resolve_seam(fp, pa, pb, tol)
    if seam is None:
        if getattr(fp, "Edge", None) is not None:
            _refuse(fp, "edge %s is not a shared boundary of both "
                        "patches (endpoint poles must sit on a corner "
                        "pair of each)" % getattr(fp.Edge, "Name", "?"))
        return
    ea, eb, pairs = seam

    # Step 3: set split direction and side
    # Split PERPENDICULAR to the shared edge
    sd_a = "V" if ea[0] == "U" else "U"  # VSplits if edge along U, USplits if edge along V
    sd_b = "V" if eb[0] == "U" else "U"
    ss_a = 0 if ea[1] == "0" else 1  # split near 0 or near 1 along the perpendicular direction
    ss_b = 0 if eb[1] == "0" else 1

    # Step 4: each patch carries the split that isolates its band at the
    # shared edge (perpendicular to the seam, on the seam's side). A
    # corner patch meets two strips, so both USplits and VSplits get set.
    #
    # #64: the blend READS that boundary, it does not assert it. The
    # patch owns its splits; the blend consumes them. If the patch
    # already carries a split at THIS seam's end of THIS axis, that split
    # IS the band's far edge — use it and add nothing. Only when the end
    # carries no split at all does the blend write the default width
    # (0.1 / 0.9) as before.
    #
    # "At this end" is SilkMachinery.split_at_end's classification — the
    # same rule corner_cells uses to decide which interval is a corner
    # cell, so the band and its corner exclusion can never disagree
    # about which split is which end's. It is per (patch, axis, side),
    # never a single global value: a four-patch corner carries one split
    # per seam side on each axis, and each strip reads its own.
    def ensure_band_split(p, sd, ss):
        prop = "VSplits" if sd == "V" else "USplits"
        cur = list(getattr(p, prop) or [])
        if split_at_end(cur, ss) is not None:
            return          # the patch's own split defines this band
        val = 0.9 if ss else 0.1
        setattr(p, prop, sorted(cur + [val]))
        p.recompute()

    ensure_band_split(pa, sd_a, ss_a)
    ensure_band_split(pb, sd_b, ss_b)

    # Step 5: the blend band comes from the patch's own subgrid cells —
    # the UV splits already subdivide the surface, so pick the seam-
    # adjacent cell(s) instead of re-segmenting the base surface (see
    # module-level band_cells; #33). The corner cell at a 4-patch
    # junction is not part of the band (reserved for the corner blend
    # op, #28).
    def get_strip(p, ea, ss):
        """Extract the band cell's flat 16-pole array poles[U][V] = flat[U*4+V]
        from the patch's pre-computed subgrids.

        #61: the refusal stays, but it now says WHAT is wrong and what
        would fix it — the patch, the seam, both axis split lists, how
        many cells each makes, which are corner cells, and the single
        split value that would leave a one-cell band. The old text named
        the cell count and nothing else, so the only way to act on it was
        to go and re-derive the whole split layout by hand.
        """
        idxs = band_cells(p, ea, ss)
        if len(idxs) != 1:
            FreeCAD.Console.PrintError(
                "Silk: blend band on %s covers %d subgrid cells; exactly 1 "
                "is required (multi-cell bands not supported yet).\n"
                "      %s\n" % (p.Name, len(idxs),
                              band_diagnosis(p, ea, ss)))
            return None
        if not p.Proxy._subgrids:
            FreeCAD.Console.PrintError(
                "Silk: blend band on %s: the patch has no subgrid cells at "
                "all (USplits=%s, VSplits=%s) — the seam %s band needs at "
                "least the split that isolates it.\n"
                % (p.Name, list(p.USplits or []), list(p.VSplits or []), ea))
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
    for p_i in (pa, pb):
        e_i = ea if p_i is pa else eb
        ss_i = ss_a if p_i is pa else ss_b
        idxs = set(band_cells(p_i, e_i, ss_i)) | _linked_band_cells(fp, p_i)
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


def _on_delete(fp):
    """Unblend: a dying blend gives its band back on both patches.

    Two things are given back, and the ORDER matters:

      1. the band's SPLITS -- the WHOLE axis on each patch (#71). #70
         deliberately kept them, to preserve the user's width (#64); the
         human reversed that, because an unblended patch that still
         renders subdivided does not LOOK unblended -- and, in the
         wizard, because the Band A / Band B editors ARE that property,
         so there is nowhere else a width could live. The axis is the one
         `_band_split_of` names for the side this blend took, and it goes
         WHOLE, the user's own split included. Two things stay: a split a
         SURVIVING blend still needs (a patch can carry two seams on one
         axis -- the tube's TubeA.USplits [0.1, 0.9] -- and unblending
         one must not strip the other's band), and the whole axis when a
         CornerBlend still feeds off this blend (#28). The width is the
         price: re-blending a cleared seam rebuilds at the default.
      2. the band CELLS -- the hidden-cell set is re-derived by each
         blend's execute from the strips alive at that moment, but a
         DELETED blend touches nothing and recompute() only walks touched
         objects, so without this both patches would keep the band hole
         forever. The tree-delete path has the same defect; this is a
         document hook, not a panel path, so it covers every delete with
         or without the panel open.

    Splits FIRST: band_cells is computed from the split lists, so the
    surviving blends' cell indices are only right once the layout is the
    one the patches will actually render.

    Each fed patch's set is then re-derived from the blends that REMAIN
    linked (the shared _linked_band_cells derivation, which skips the
    dying blend), the write fires Patch.onChanged's display rebuild, and
    the patches are touched so the surviving strips re-derive against
    them on the next recompute.
    """
    proxy = fp.Proxy
    if getattr(proxy, "_dying", False):
        return False
    proxy._dying = True
    try:
        doc = getattr(fp, "Document", None)
        if doc is None or "Restore" in getattr(fp, "State", []):
            return False
        pa, pb = getattr(fp, "PatchA", None), getattr(fp, "PatchB", None)
        # (1) this seam's own split, on each patch it feeds
        if pa is not None and pb is not None and pa is not pb:
            seam = _resolve_seam(fp, pa, pb, getattr(fp, "tolerance", 0.01))
            for p, etype in ((pa, seam[0]), (pb, seam[1])) if seam else ():
                if getattr(p, "object_type", None) in PATCH_TYPES:
                    try:
                        _drop_band_split(doc, fp, p, etype)
                    except Exception:
                        pass
        # (2) the band cells, from the blends that remain
        seen = []
        for role in ("PatchA", "PatchB"):
            p = getattr(fp, role, None)
            if (p is None
                    or getattr(p, "object_type", None) not in PATCH_TYPES
                    or any(q is p for q in seen)):
                continue
            seen.append(p)
            try:
                ensure_hidden_idxs_property(p)
                # every surviving strip's band, minus this one
                p._HiddenSubgridIdxs = sorted(_linked_band_cells(fp, p))
            except Exception:
                pass
            try:
                p.touch()
            except Exception:
                pass
        try:
            doc.recompute()
        except Exception:
            pass
    finally:
        proxy._dying = False
    return False


# ---- object types --------------------------------------------------------

class _DeleteWatcher:
    """One-shot document observer that fires the unblend when its blend
    is deleted (#70).

    WHY AN OBSERVER AND NOT onDelete: FreeCAD 1.1.3 has NO
    DocumentObjectPy::onDelete -- the method does not exist on the type
    (verified: `hasattr(obj, 'onDelete')` is False on a live
    FeaturePython) and no core code calls it, so BlendStrip.onDelete
    alone would never run. This observer is the live trigger:
    Document::_removeObject emits signalDeletedObject BEFORE it
    nullifies the links, so PatchA/PatchB are still readable when the
    slot fires -- which is exactly what makes the restoration possible.
    The slot removes the observer after firing (one shot per blend), so
    nothing accumulates.
    """

    def __init__(self, fp):
        self._fp = fp
        self._fired = False

    def _spend(self):
        """Retire this watcher for good: mark it fired AND unregister it.

        Both, together, and only from a path that cannot raise before
        completing -- an observer left registered is the spin (#80), and a
        slot that can raise before setting the flag is the spin's cause.
        """
        self._fired = True
        try:
            FreeCAD.removeDocumentObserver(self)
        except Exception:
            pass

    def slotDeletedObject(self, obj):
        # #80: `getattr(x, "Name", None)` does NOT swallow ReferenceError --
        # the default only covers AttributeError. Once the document is
        # tearing down, `self._fp` is a DELETED object and reading `.Name`
        # raises. The old code let that escape before setting `_fired` and
        # before unregistering, so the slot re-entered on every later
        # deletion: measured at 959,399 tracebacks in one session, each
        # printed in full because it was raised inside a C++ slot. A
        # dangling document observer also outlives the object it wraps,
        # and FreeCAD then died with SIGSEGV in
        # View3DInventorViewer::aboutToDestroyGLContext.
        #
        # So the flag is no longer set blindly-first. Setting it before
        # the comparison was a REGRESSION I introduced in ef7054b and
        # caught in review: the slot fires for EVERY deleted object in the
        # document, so spending it on the first unrelated one meant the
        # watcher had already retired itself by the time *our* blend was
        # deleted -- and unblend silently stopped working
        # (test_unblend_restores_the_patches,
        # test_unblend_removes_only_the_seams_own_split). Two tests caught
        # what the mutation checks and the crash-count fix could not.
        #
        # The rule that is actually correct: retire on the two cases where
        # retirement is safe -- our blend is gone (do the unblend), or our
        # own object is already deleted so we can never match again. On a
        # name mismatch, KEEP WAITING.
        if self._fired:
            return
        try:
            mine = getattr(self._fp, "Name", None)
        except ReferenceError:
            self._spend()      # can never match again; stop being called
            return
        try:
            theirs = getattr(obj, "Name", None)
        except ReferenceError:
            return             # a half-deleted `obj`; not ours, not yet
        if theirs != mine:
            return             # some other object went: stay armed
        self._spend()
        _on_delete(obj)

    def slotDeletedDocument(self, doc):
        pass


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
        # set by the delete path: a dying blend owns no band, so it is
        # skipped by _linked_band_cells and run_blend alike.
        self._dying = False
        self._delete_watcher = None
        self._install_delete_watcher(obj)

    def _install_delete_watcher(self, fp):
        """Install the one-shot observer that fires the unblend (#70).

        Idempotent: a blend carries at most one watcher. Called from
        __init__ (the object is in the document by the time the proxy
        constructor runs) and from onDocumentRestored (a restored blend
        never runs __init__, so without this it would die unwatched).
        """
        if self._delete_watcher is not None:
            return
        try:
            if fp.Document is None:
                return
            self._delete_watcher = _DeleteWatcher(fp)
            FreeCAD.addDocumentObserver(self._delete_watcher)
        except Exception:
            self._delete_watcher = None

    def onChanged(self, fp, prop):
        _on_changed(fp, prop)

    def onDocumentRestored(self, obj):
        self._install_delete_watcher(obj)

    def onDelete(self, fp):
        # FreeCAD 1.1.3 never calls this (no DocumentObjectPy::onDelete);
        # the _DeleteWatcher observer is the live trigger. Kept so the
        # restoration has a home on the class and so a future FreeCAD
        # that does invoke onDelete is covered too.
        return _on_delete(fp)

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
        self._dying = False
        # #70: Blend overrides __init__ without calling super(), so the
        # delete watcher installed by BlendStrip.__init__ never runs for
        # a FRESHLY created blend -- only a restored one got it, via the
        # inherited onDocumentRestored. That left every unblend with the
        # panel-created blends inert, and the patches kept their band
        # hole. Install it here too.
        self._delete_watcher = None
        self._install_delete_watcher(obj)

    def onDelete(self, fp):
        """The unblend. Delegates to the shared _on_delete -- the one
        place that knows the whole rule (#71: the band CELLS come back
        AND the band's SPLITS go, the whole axis bar what a surviving
        blend still needs, so an unblended patch is a plain patch again).

        Like BlendStrip.onDelete this is never actually called -- FreeCAD
        1.1.3 has no DocumentObjectPy::onDelete, and the _DeleteWatcher
        observer is the live trigger (#70). It is kept so the rule has a
        home on the class and so a future FreeCAD that does invoke
        onDelete gets the SAME rule rather than a second, weaker copy."""
        return _on_delete(fp)


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
