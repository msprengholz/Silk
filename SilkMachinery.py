"""
SilkMachinery — shared machinery core for Silk surface objects.

One reusable implementation of the machinery every patch fill shares:
subdivision (USplits/VSplits -> subgrid pole arrays + trimmed surfaces),
blend-band selection, hidden-cell bookkeeping, and compound display.

Patch44 (the quad fill) consumes this core for all four; BlendStrip
resolves its seam-adjacent subgrid cell through band_cells here. Future
fills (the 3-edge patch, the unified Patch/Blend) delegate to the same
implementation instead of reimplementing it.

Only behavior shared verbatim across consumers lives here — no object
type or geometry logic is introduced.
"""

import Part
import ArachNURBS as AN


# ---- subdivision -------------------------------------------------------

def normalize_splits(values):
    return sorted(set(v for v in values if 0.0 < v < 1.0))


def build_intervals(values):
    splits = normalize_splits(list(values))
    if not splits:
        return [(0.0, 1.0)]
    return list(zip([0.0] + splits, splits + [1.0]))


def build_subgrids(base_surface, u_splits, v_splits):
    """Subdivide base_surface by the U/V splits.

    Returns (subgrids, subsurfaces, sub_legs):
      - subgrids:    flat 16-pole arrays, one per cell;
                     poles[U][V] == flat[U*4 + V] (FreeCAD convention).
      - subsurfaces: the trimmed sub-shapes (only truthy shapes).
      - sub_legs:    detailed grid lines for the subdivided view.
    With no splits returns ([], [], []).
    """
    subgrids = []
    subsurfaces = []
    sub_legs = []
    u_splits = list(u_splits) if u_splits else []
    v_splits = list(v_splits) if v_splits else []
    if not (u_splits or v_splits):
        return subgrids, subsurfaces, sub_legs
    shapes = []
    for u0, u1 in build_intervals(u_splits):
        for v0, v1 in build_intervals(v_splits):
            seg = base_surface.copy()
            seg.segment(u0, u1, v0, v1)
            seg_poles = seg.getPoles()
            flat = []
            for r in range(4):
                for c in range(4):
                    flat.append(seg_poles[r][c])
            subgrids.append(flat)
            sub_shape = seg.toShape()
            if sub_shape:
                shapes.append(sub_shape)
            sub_legs.extend(AN.drawGrid(flat, 4))
    return subgrids, shapes, sub_legs


# ---- blend band / shared-edge selection --------------------------------

def patch_side(pa, pb, tol=0.01):
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
    excluded from the band (reserved for the four-cell corner blend op,
    #28).
    """
    ivs_u = build_intervals(list(p.USplits or []))
    ivs_v = build_intervals(list(p.VSplits or []))
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


# ---- hidden-cell bookkeeping ------------------------------------------

def ensure_hidden_idxs_property(p):
    """Ensure patch p carries the _HiddenSubgridIdxs property.

    The superseded single-index _HideSubgridIdx is removed first. Used by
    BlendStrip (and, later, every fill) when it hides the subgrid cells
    it covers.
    """
    try:
        p.removeProperty("_HideSubgridIdx")
    except Exception:
        pass
    if not hasattr(p, "_HiddenSubgridIdxs"):
        p.addProperty("App::PropertyIntegerList", "_HiddenSubgridIdxs", "Internal",
                      "subgrid cell indices hidden by blends")
        p.setEditorMode("_HiddenSubgridIdxs", 1)


# ---- compound display --------------------------------------------------

def build_display(fobj, base_shape, sub_shapes, base_legs, sub_legs,
                  has_subgrids):
    """Compose the patch display Shape from the surface/grid toggles.

    Writes fobj.Shape with the compound of the visible surface (the base
    surface, or the non-hidden subgrid surfaces when ShowSubgrids) plus
    the chosen grid lines. Honors fobj.ShowSurface / ShowSubgrids /
    ShowGrid / AutoHideBlend the way Patch44 always has.
    """
    hide_idxs = set(list(getattr(fobj, "_HiddenSubgridIdxs", []) or []))
    if not getattr(fobj, "AutoHideBlend", True):
        hide_idxs = set()
    else:
        legacy = getattr(fobj, "_HideSubgridIdx", -1)
        if isinstance(legacy, int) and legacy >= 0:
            hide_idxs.add(legacy)

    shapes = []
    if getattr(fobj, "ShowSurface", True):
        if getattr(fobj, "ShowSubgrids", False) and sub_shapes:
            for i, sub in enumerate(sub_shapes):
                if i not in hide_idxs:
                    shapes.append(sub)
        else:
            shapes.append(base_shape)

    draw_legs = sub_legs if has_subgrids and getattr(fobj, "ShowSubgrids", False) \
        else base_legs
    if getattr(fobj, "ShowGrid", True) and draw_legs:
        for leg in draw_legs:
            if hasattr(leg, "toShape"):
                shapes.append(leg.toShape())

    if shapes:
        try:
            fobj.Shape = Part.Compound(shapes)
        except Exception:
            if len(shapes) == 1:
                fobj.Shape = shapes[0]
            else:
                fobj.Shape = Part.Shape(shapes)
    else:
        fobj.Shape = Part.Shape()
