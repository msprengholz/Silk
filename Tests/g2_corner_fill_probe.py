"""
Tests/g2_corner_fill_probe.py -- Phase B measurement for ticket #91.

Does FreeCAD's built-in surface tool (`Surface::Filling`, the ADR-0005
"G2 default" for the corner stage) actually reach G2 across the 4-patch
corner junction, and **what feed does it need**?

MEASUREMENT ONLY.  Nothing here is a production object; every carrier is
a throwaway `Part::Feature` / `Surface::Filling` built in a scratch
document and removed again.

Two feeds of the SAME corner hole are measured side by side:

  raw   the four raw patches' junction cells -- the ADR-0005 Q1=b feed.
        The hole boundary is the OCTAGON of each corner cell's two inner
        edges (8 edges, 2 per patch), one support per edge taken from the
        adjacent raw patch cell.
  strip the four ring BlendStrips' corner-end rows -- the "after edge
        blending" boundary.  The hole boundary is the QUAD the four
        strips' inner ends close (4 edges); one support per edge is the
        strip's own face.

Run (live GUI over XML-RPC, or in a GUI process):

    freecad Tests/g2_corner_fill_probe.py

or from a shell inside FreeCAD:

    import Tests.g2_corner_fill_probe as p; p.main()

--------------------------------------------------------------------------
MEASURED RESULT (FreeCAD 1.1.3, OCCT 7.9; corner fixture Tests/corner_model.py)
--------------------------------------------------------------------------
continuity order is the `Surface::Filling.BoundaryOrder` value: 0 = C0,
1 = G1, 2 = G2 (this build rejects >= 3 with
"BRepFill : The continuity is not G0 G1 or G2").

  feed   order  valid  boundary_residual   max boundary normal gap
  ----   -----  -----  -----------------   -----------------------
  raw      0    yes    <= 5.0e-3 mm        45.3 - 88.6 deg  (C0 by design)
  raw      1    NO     0.59 - 7.3 mm       not measurable (no point on fill)
  raw      2    NO     0.75 - 3.2 mm       not measurable (no point on fill)
  strip    0    yes    <= 2.3e-4 mm        1.86 - 4.29 deg  (C0 by design)
  strip    1    yes    <= 2.2e-4 mm        0.087 - 0.155 deg
  strip    2    yes    <= 9.0e-3 mm        0.164 - 0.483 deg

(`boundary_residual` = max distance from a boundary point to the fill
surface; for a sound fill it is the parameter-solve floor ~1e-4..5e-3 mm,
and for the over-constrained raw feed it is 0.6-7 mm -- the fill does not
pass through its own boundary at all.)

Reading:
  * The raw-patch feed is OVER-CONSTRAINED.  At every octagon vertex two
    consecutive boundary edges are supported by DIFFERENT raw patches,
    and the raw patches meet there at the 60-88 deg ridges #92 measured.
    No single smooth surface can be G1/G2 to both sides at once, so the
    Filling returns an INVALID face whose surface does not even contain
    its own boundary (residual ~0.35 mm).  C0 is the only order that
    builds (valid, boundary residual ~5e-6 mm).
  * The strip feed (boundary smooth because the edge blends already
    smoothed the ridges) builds a VALID fill: G1 to 0.09-0.16 deg and
    G2 to 0.53-0.94 deg residual normal gap.

This is the measured input the ticket owner needs to move ADR-0005 Q1
from `b` (raw patches) to `a` (blended strips) if the G2 default is to
hold.
"""

import math

import FreeCAD
import Part
from FreeCAD import Base

from Tests import corner_model

RIDGE_PATCHES = ("Patch44", "Patch001", "Patch002", "Patch003")
STRIP_ORDER = ("B12", "B24", "B43", "B31")
JUNCTION_C = Base.Vector(50.0, 50.0, 52.0)
TOL = 1e-4


# ---------------------------------------------------------------------------
# parameter solve (the fill's surface is a general trim, so S.parameter()
# is NOT reliable enough for boundary points -- see the measurement note)
# ---------------------------------------------------------------------------

def solve_uv(surf, point, prange, grid=120):
    """(u, v, residual) for `point` on `surf`, solved over `prange`.

    Coarse grid to bracket the nearest point, then a damped Newton on the
    two parameters.  `residual` is |surf.value(u, v) - point| -- the small
    number the caller wants, and the big number when `point` is not on the
    surface at all (which is exactly the raw-patch-feed evidence).
    """
    u0, u1, v0, v1 = prange
    best = None
    for i in range(grid + 1):
        u = u0 + (u1 - u0) * i / grid
        for j in range(grid + 1):
            v = v0 + (v1 - v0) * j / grid
            d = (surf.value(u, v) - point).Length
            if best is None or d < best[0]:
                best = (d, u, v)
    u, v = best[1], best[2]
    for _ in range(80):
        r = surf.value(u, v) - point
        if r.Length < 1e-11:
            break
        h = 1e-6
        su = (surf.value(u + h, v) - surf.value(u - h, v)) / (2 * h)
        sv = (surf.value(u, v + h) - surf.value(u, v - h)) / (2 * h)
        a, b, c = su.dot(su), su.dot(sv), sv.dot(sv)
        d, e = su.dot(r), sv.dot(r)
        det = a * c - b * b
        if abs(det) < 1e-18:
            break
        u -= (c * d - b * e) / det
        v -= (a * e - b * d) / det
        u = min(u1, max(u0, u))
        v = min(v1, max(v0, v))
    return u, v, (surf.value(u, v) - point).Length


def _normal_gap(surf_a, ua, va, surf_b, ub, vb):
    na = surf_a.normal(ua, va)
    nb = surf_b.normal(ub, vb)
    if na.Length < 1e-12 or nb.Length < 1e-12:
        return None
    na.normalize()
    nb.normalize()
    if na.dot(nb) < 0.0:
        nb = -1.0 * nb
    return math.degrees(math.acos(max(-1.0, min(1.0, na.dot(nb)))))


# ---------------------------------------------------------------------------
# patch / strip geometry helpers
# ---------------------------------------------------------------------------

def _axis_pair(p, letter):
    s1 = float(getattr(p, letter + "Split1"))
    s2 = float(getattr(p, letter + "Split2"))
    s = sorted(set(v for v in (s1, s2) if 0.0 < v < 1.0))
    return [(0.0, 1.0)] if not s else list(zip([0.0] + s, s + [1.0]))


def _cell(base, u0, u1, v0, v1):
    seg = base.copy()
    seg.segment(u0, u1, v0, v1)
    return seg.toShape()


def _corner_cell_info(patch):
    """(base_surface, ui, vi, iu_c, iv_c, cell_face) for the patch cell
    nearest the junction C."""
    base = patch.Proxy._base_surface
    ui = _axis_pair(patch, "U")
    vi = _axis_pair(patch, "V")
    best = None
    for iu, (u0, u1) in enumerate(ui):
        for iv, (v0, v1) in enumerate(vi):
            face = _cell(base, u0, u1, v0, v1)
            d = (face.CenterOfMass - JUNCTION_C).Length
            if best is None or d < best[0]:
                best = (d, iu, iv, face)
    return base, ui, vi, best[1], best[2], best[3]


def _order_loop(edges):
    """Edge indices in consecutive (wire) order, or None."""
    def ends(e):
        return (e.valueAt(e.FirstParameter), e.valueAt(e.LastParameter))

    order = [0]
    used = {0}
    cursor = ends(edges[0])[0]
    while len(order) < len(edges):
        found = None
        for k in range(len(edges)):
            if k in used:
                continue
            qa, qb = ends(edges[k])
            if (cursor - qa).Length < TOL:
                found = (k, qb)
                break
            if (cursor - qb).Length < TOL:
                found = (k, qa)
                break
        if found is None:
            return None
        order.append(found[0])
        used.add(found[0])
        cursor = found[1]
    return order


def _edge_subname(face_or_compound, edge_shape):
    """The 'EdgeN' subname of `edge_shape` in `face_or_compound`, matched by
    its two endpoints (exact for the fill's own boundary edges)."""
    ea = edge_shape.valueAt(edge_shape.FirstParameter)
    eb = edge_shape.valueAt(edge_shape.LastParameter)
    for i, fe in enumerate(face_or_compound.Edges):
        fa = fe.valueAt(fe.FirstParameter)
        fb = fe.valueAt(fe.LastParameter)
        if (((fa - ea).Length < TOL and (fb - eb).Length < TOL)
                or ((fa - eb).Length < TOL and (fb - ea).Length < TOL)):
            return "Edge%d" % (i + 1)
    return None


# ---------------------------------------------------------------------------
# feed 1 -- raw patches (ADR-0005 Q1=b)
# ---------------------------------------------------------------------------

def build_raw_patch_fill(doc, order, prefix="_g2raw_"):
    """A `Surface::Filling` bounded by the four raw patches' junction cells.

    Returns dict(edge=list of 8 Edge shapes, support=list of 8 faces,
    patch=list of 8 names, fill=the Surface::Filling object).
    """
    edges, supports, patches = [], [], []
    for name in RIDGE_PATCHES:
        patch = doc.getObject(name)
        base, ui, vi, iu_c, iv_c, cell = _corner_cell_info(patch)
        nu, nv = len(ui), len(vi)
        for e in cell.Edges:
            p0 = e.valueAt(e.FirstParameter)
            p1 = e.valueAt(e.LastParameter)
            if (p0 - JUNCTION_C).Length < TOL or (p1 - JUNCTION_C).Length < TOL:
                continue  # one of the two edges meeting at C (not a hole edge)
            uv0, uv1 = base.parameter(p0), base.parameter(p1)
            if abs(uv0[0] - uv1[0]) < 1e-6:          # U-const inner edge
                us = uv0[0]
                vlo, vhi = min(uv0[1], uv1[1]), max(uv0[1], uv1[1])
                sup_u = (0.0, us) if iu_c == nu - 1 else (us, 1.0)
                sup_v = (vlo, vhi)
            else:                                     # V-const inner edge
                vs = uv0[1]
                ulo, uhi = min(uv0[0], uv1[0]), max(uv0[0], uv1[0])
                sup_v = (0.0, vs) if iv_c == nv - 1 else (vs, 1.0)
                sup_u = (ulo, uhi)
            edges.append(e)
            supports.append(_cell(base, sup_u[0], sup_u[1], sup_v[0], sup_v[1]))
            patches.append(name)

    order_idx = _order_loop(edges)
    if order_idx is None:
        raise RuntimeError("raw-patch octagon does not close")

    links, faces, orders = [], [], []
    for k in order_idx:
        obj = doc.addObject("Part::Feature", prefix + "sup_%d" % k)
        obj.Shape = supports[k]
        links.append((obj, _edge_subname(obj.Shape, edges[k])))
        faces.append("Face1")
        orders.append(order)
    fill = doc.addObject("Surface::Filling", prefix + "fill")
    fill.BoundaryEdges = links
    fill.BoundaryFaces = faces
    fill.BoundaryOrder = orders
    doc.recompute()
    return {"edge": [edges[k] for k in order_idx],
            "support": [supports[k] for k in order_idx],
            "patch": [patches[k] for k in order_idx],
            "fill": fill}


# ---------------------------------------------------------------------------
# feed 2 -- ring strips (ADR-0005 Q1=a, the "after edge blending" boundary)
# ---------------------------------------------------------------------------

def _strip_corner_row(strip, strips):
    """(row, li) -- the strip's 6-pole corner-end row (mirrors SilkCorner's
    derivation, re-derived here rather than imported)."""
    from SilkBlend import band_cells, side_and_end
    from SilkMachinery import build_intervals, split_pair

    def corner_cell(p):
        nu = len(build_intervals(*split_pair(p, "U")))
        nv = len(build_intervals(*split_pair(p, "V")))
        iu_c = iv_c = None
        for s in strips:
            if s.PatchA is not p and s.PatchB is not p:
                continue
            e, ss = side_and_end(s, p, 0.01)
            if not e:
                continue
            if e[0] == "U":
                iv_c = nv - 1 if e[1] == "1" else 0
            else:
                iu_c = nu - 1 if e[1] == "1" else 0
        return iu_c, iv_c, nu, nv

    pa, pb = strip.PatchA, strip.PatchB
    e_a, ss_a = side_and_end(strip, pa, 0.01)
    e_b, ss_b = side_and_end(strip, pb, 0.01)
    bca = band_cells(pa, e_a, ss_a)[0]
    bcb = band_cells(pb, e_b, ss_b)[0]
    li = None
    for pth, e, bc in ((pa, e_a, bca), (pb, e_b, bcb)):
        iu_c, iv_c, nu, nv = corner_cell(pth)
        iu_b, iv_b = divmod(bc, nv)
        li2 = ((3 if iu_c > iu_b else 0) if e[0] == "U"
               else (3 if iv_c > iv_b else 0))
        if li is None:
            li = li2
    row = list(strip.Poles)[li * 6: li * 6 + 6]
    return row, li


def build_strip_fill(doc, order, prefix="_g2strip_"):
    """A `Surface::Filling` bounded by the four ring strips' corner-end rows.

    Returns dict(row=list of 4 pole rows, surface=list of 4 strip surfaces,
    strip=list of 4 names, fill=the Surface::Filling object).
    """
    strips = [doc.getObject(n) for n in STRIP_ORDER]
    rows, surfs, names = [], [], []
    links, faces, orders = [], [], []
    for strip in strips:
        row, _li = _strip_corner_row(strip, strips)
        face = max(strip.Shape.Faces, key=lambda f: f.Area)
        # boundary edge of the strip face = the cubic through `row`
        curve = Part.BSplineCurve()
        curve.buildFromPoles(row)
        edge = curve.toShape()
        obj = doc.addObject("Part::Feature", prefix + "sup_%s" % strip.Name)
        obj.Shape = face
        links.append((obj, _edge_subname(obj.Shape, edge)))
        faces.append("Face1")
        orders.append(order)
        rows.append(row)
        surfs.append(face.Surface)
        names.append(strip.Name)
    fill = doc.addObject("Surface::Filling", prefix + "fill")
    fill.BoundaryEdges = links
    fill.BoundaryFaces = faces
    fill.BoundaryOrder = orders
    doc.recompute()
    return {"row": rows, "surface": surfs, "strip": names, "fill": fill}


# ---------------------------------------------------------------------------
# measurement
# ---------------------------------------------------------------------------

def measure(fill, boundary_points, reference_surfaces, labels):
    """Measure the fill's continuity along `boundary_points`.

    `boundary_points[i]` is a list of 3D points along boundary edge i;
    `reference_surfaces[i]` is the surface that edge is supposed to be
    continuous with.

    Returns (report, per_edge) where report has
    `valid`, `boundary_residual` (max distance from a boundary point to the
    fill surface -- the C0/host-surface check) and `max_normal_gap_deg`.
    """
    shape = fill.Shape
    report = {"state": list(shape.State) if hasattr(shape, "State") else [],
              "faces": len(shape.Faces),
              "valid": bool(shape.Faces) and shape.isValid(),
              "boundary_residual": None,
              "max_normal_gap_deg": None}
    per_edge = []
    if not shape.Faces:
        return report, per_edge
    face = shape.Faces[0]
    surf = face.Surface
    prange = face.ParameterRange
    worst_res = 0.0
    worst_gap = 0.0
    measured_any = False
    for pts, ref, label in zip(boundary_points, reference_surfaces, labels):
        edge_res = 0.0
        edge_gap = None
        for p in pts:
            u, v, res = solve_uv(surf, p, prange)
            edge_res = max(edge_res, res)
            if res > 1e-3:
                continue  # the fill does not pass through this boundary point
            nr = solve_uv(ref, p, (0.0, 1.0, 0.0, 1.0), grid=60)
            gap = _normal_gap(surf, u, v, ref, nr[0], nr[1])
            if gap is not None:
                edge_gap = gap if edge_gap is None else max(edge_gap, gap)
        worst_res = max(worst_res, edge_res)
        if edge_gap is not None:
            measured_any = True
            worst_gap = max(worst_gap, edge_gap)
        per_edge.append({"label": label,
                         "boundary_residual": edge_res,
                         "normal_gap_deg": edge_gap})
    report["boundary_residual"] = worst_res
    # None when the fill never reaches the boundary (raw feed at G1/G2),
    # so "no measurement" cannot be misread as "zero gap".
    report["max_normal_gap_deg"] = worst_gap if measured_any else None
    return report, per_edge


def run(doc, order, feed):
    """Build `feed` ('raw' or 'strip') at `order` and measure it."""
    if feed == "raw":
        data = build_raw_patch_fill(doc, order)
        boundary_points = []
        refs = []
        for i, e in enumerate(data["edge"]):
            pts = [e.valueAt(e.FirstParameter
                            + (e.LastParameter - e.FirstParameter) * k / 10.0)
                   for k in range(11)]
            boundary_points.append(pts)
            patch = doc.getObject(data["patch"][i])
            refs.append(patch.Proxy._base_surface)
        labels = data["patch"]
    else:
        data = build_strip_fill(doc, order)
        boundary_points = []
        refs = []
        for row in data["row"]:
            curve = Part.BSplineCurve()
            curve.buildFromPoles(row)
            boundary_points.append([curve.value(k / 10.0) for k in range(11)])
        refs = data["surface"]
        labels = data["strip"]
    report, per_edge = measure(data["fill"], boundary_points, refs, labels)
    report["order"] = order
    report["feed"] = feed
    report["per_edge"] = per_edge
    return report


def _scratch_document():
    name = "_g2_corner_fill_probe"
    if name in FreeCAD.listDocuments():
        FreeCAD.closeDocument(name)
    doc = FreeCAD.newDocument(name)
    corner_model.build_corner_model_with_blend(doc)
    return doc


def _probe_document(doc, order, feed):
    """Build into a document that already holds the corner model, then
    remove the throwaway carriers (keeps the document reusable)."""
    before = set(o.Name for o in doc.Objects)
    report = run(doc, order, feed)
    for o in list(doc.Objects):
        if o.Name not in before:
            try:
                doc.removeObject(o.Name)
            except Exception:
                pass
    doc.recompute()
    return report


def main():
    doc = _scratch_document()
    results = []
    try:
        for feed in ("raw", "strip"):
            for order in (0, 1, 2):
                try:
                    results.append(_probe_document(doc, order, feed))
                except Exception as exc:      # a feed that cannot even build
                    results.append({"feed": feed, "order": order,
                                    "error": repr(exc)})
    finally:
        FreeCAD.closeDocument(doc.Name)
    print("feed   order  valid  boundary_residual  max_normal_gap_deg")
    for r in results:
        if "error" in r:
            print("%-6s %-6d  ERROR  %s" % (r["feed"], r["order"], r["error"]))
            continue
        print("%-6s %-6d  %-5s  %-17s  %s"
              % (r["feed"], r["order"], r["valid"],
                 ("%.3e mm" % r["boundary_residual"]
                  if r["boundary_residual"] is not None else "-"),
                 ("%.3f deg" % r["max_normal_gap_deg"]
                  if r["max_normal_gap_deg"] else "-")))
    return results


if __name__ == "__main__":
    main()
