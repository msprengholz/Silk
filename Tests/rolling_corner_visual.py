"""
MANUAL VISUAL + MEASUREMENT -- the ROLLING CORNER, path (B) (ticket #119).

WHY THIS EXISTS.  The owner looked at the shipped corner and ruled
(2026-10-21): *"the patch has weirdly rounded edges. I would not consider
this to be a rolling corner like described by the silk maintainer. ...
I only see one surface, but it should be two!"*  #119 builds the owner's
construction:

  * the BIG QUAD PATCH = the 0.75 piece of each split edge blend (the
    blend surface itself -- a `CubicSurface_64`, Silk-made, low order),
  * the SMALL TRIANGULAR SURFACE = a FreeCAD `Surface::Filling` over
    the corner region's boundary (the two 0.25 pieces and the third
    side).

**NO `ControlGrid66` AND NO TRIANGULAR MEMBER ARE BUILT HERE.**  The
maintainer's 66 is a four-member fill, and a 3-valent corner has only
three blends: the fourth member (the "scaffolding piece" with a
collapsed row) is what makes a Silk-native 66 possible at all.  The
owner's spec does not want it -- the corner face is FreeCAD's own
filling, and a 66 plus a member would be scaffolding nobody uses.  The
shipped default 3-valent corner (which DOES build both) is untouched
and is measured here as the reference.

WHAT IS RENDERED, all from ONE camera (the same one
`Tests/g2_corner_roll_visual.py` uses, so the two sets of images are
comparable):

  (a) shaded, the rolling corner (the triangle + the split blends)
      ................................ rolling_1_shaded.png
  (b) shaded, the triangular surface alone .... rolling_2_triangle.png
  (c) shaded, the SHIPPED corner (the reference) ... shipped_shaded.png
  (d) curvature ratio k_max/k_min of the shipped corner
      ............................................. rolling_3_ratio.png
  (e) Gaussian curvature k_max*k_min of the shipped corner
      ............................................. rolling_4_gauss.png
  plus the two shared colour legends.

WHAT IS MEASURED, beside the pictures:

  1. the TRIANGULAR SURFACE's own curvature spread (k_max / k_min) on
     the fill's own surface, with the shipped corner's spread beside it;
  2. how many cells of the shipped corner's surface are saddle
     (k1*k2 < 0) -- the same instrument as #118;
  3. the JUNCTION residual: how far the triangular fill's boundary is
     from the split blends' cut edges (the place the owner's "part of
     the edge blend needs to be replaced" comes in) and the residual
     against the shipped corner's surface;
  4. the seam `k_gap` of the split blends against the corner they feed,
     with the calibrated floor beside it.

NOTHING HERE IS A CLAIM.  No continuity label, no verdict on whether
the result rolls: the images and the numbers are the evidence and the
judgement is the owner's.

MANUAL-ONLY: the file name is not `test_*.py`, so `Tests/suite.py` does
not discover it.  `Tests/test_continuity_instrument.py` asserts this
module imports, exposes `main`, and carries `MANUAL`; nothing else in the
suite runs it.

Run (live GUI over XML-RPC, or in a GUI FreeCAD):

    import Tests.rolling_corner_visual as v; v.main()
"""

import os

import FreeCAD
import Part

import Tests.silk_nurbs as SN
import Tests.g2_oracle as G
from Tests.g2_corner_roll_measure import (principal_curvatures, spread,
                                           per_seam, junction_probe, _flat,
                                           _part_surface)
from Tests.g2_corner_roll_visual import (curvature_map, set_camera, _quiesce,
                                          _only, _gui_view, draw_legend,
                                          RATIO_STOPS, GAUSS_STOPS,
                                          _ratio_ticks, _gauss_ticks,
                                          IMAGE_SIZE, BACKGROUND, N_CELLS)
from SilkWorkflowOps import create_rolling_corner, create_corner_blend
from Tests import cube_corner_model as ccm

MANUAL = True

OUT_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "Resources", "Test_files", "_inspect")

LEADER = 0.25          # the video's number: 0.25 / 0.75 along the seam
TRIANGLE_RGB = (0.20, 0.45, 0.95)   # the triangle gets a colour of its own


# ---------------------------------------------------------------------------
# the two corners on the same fixture
# ---------------------------------------------------------------------------

def build_rolling(doc_name):
    """The rolling corner (path B): the fixture, the two split blends, the
    triangular fill.  NO ControlGrid66, NO triangular member."""
    if doc_name in FreeCAD.listDocuments():
        FreeCAD.closeDocument(doc_name)
    doc = FreeCAD.newDocument(doc_name)
    FreeCAD.setActiveDocument(doc.Name)
    ccm.build_cube_corner_model(doc)
    doc.recompute()
    doc.recompute()
    strips = [doc.getObject(n) for n in ("B_AB", "B_BC", "B_CA")]
    res = create_rolling_corner(strips, doc.getObject("PatchA"),
                                 leader=LEADER, name="Roll")
    doc.recompute()
    return doc, res


def build_shipped(doc_name):
    """The shipped corner on the same fixture: the ring of the three
    full-seam strips, no leader.  This is the DEFAULT path -- the
    reference the rolling corner is measured against."""
    if doc_name in FreeCAD.listDocuments():
        FreeCAD.closeDocument(doc_name)
    doc = FreeCAD.newDocument(doc_name)
    FreeCAD.setActiveDocument(doc.Name)
    ccm.build_cube_corner_model(doc)
    doc.recompute()
    doc.recompute()
    strips = [doc.getObject(n) for n in ("B_AB", "B_BC", "B_CA")]
    corner = create_corner_blend(*strips, name="ShippedCorner")
    doc.recompute()
    return doc, strips, corner


# ---------------------------------------------------------------------------
# the measurements
# ---------------------------------------------------------------------------

def _corner_net(corner):
    """The corner's stored 6x6 as an exact net (weights carried)."""
    return SN.NurbsSurface.from_flat(list(corner.Poles),
                                     list(corner.Weights) or [1.0] * 36,
                                     6, 6, SN.KNOTS_6, SN.KNOTS_6)


def _surface_net(shape):
    """A `NurbsSurface` from a Part shape's own B-spline surface.

    The fill's own poles, weights and knot sequences -- the same
    instrument (`Tests/silk_nurbs.py`) the shipped corner is read with,
    applied to the fill's surface.  Nothing is re-fitted."""
    surf = shape.Face1.Surface
    nu, nv = surf.NbUPoles, surf.NbVPoles
    poles = surf.getPoles()
    weights = surf.getWeights()
    flat = []
    flat_w = []
    for v in range(nv):
        for u in range(nu):
            flat.append(poles[u][v])
            flat_w.append(float(weights[u][v]))
    return SN.NurbsSurface.from_flat(flat, flat_w, nu, nv,
                                     list(surf.UKnotSequence),
                                     list(surf.VKnotSequence))


def spread_report(corner):
    """The shipped corner's own curvature spread at and near the junction."""
    net = _corner_net(corner)
    probe = junction_probe(net)
    centre = probe["centre"]
    return {"k_max": centre[0], "k_min": centre[1], "ratio": centre[2],
            "centre_k1k2": probe["centre_k1k2"],
            "near_ratio_min": probe["near_ratio_min"],
            "near_ratio_max": probe["near_ratio_max"],
            "foot": probe["foot"]}


def triangle_spread(triangle, n=21):
    """The triangular fill's own curvature spread, on ITS OWN surface.

    The same instrument as the shipped corner (`principal_curvatures` on
    a `NurbsSurface`), read on the fill's own B-spline surface."""
    if triangle is None:
        return None
    net = _surface_net(triangle.Shape)
    values = []
    for i in range(n):
        for j in range(n):
            u = (i + 0.5) / n
            v = (j + 0.5) / n
            k1, k2 = principal_curvatures(net, u, v)
            values.append((k1, k2))
    kmax = max(k[0] for k in values)
    kmin = min(k[1] for k in values)
    ratio = abs(kmax) / abs(kmin) if abs(kmin) > 1e-12 else float("inf")
    saddle = sum(1 for k in values if k[0] * k[1] < 0.0)
    return {"k_max": kmax, "k_min": kmin, "ratio": ratio,
            "samples": len(values), "saddle": saddle,
            "centre": principal_curvatures(net, 0.5, 0.5)}


def junction_residual(triangle, corner, n=41):
    """The C0 residual at the triangle/corner junction.

    The triangle's boundary against the corner's own surface: the max
    distance from a point on the triangle's boundary to the corner's
    surface, sampled along the three boundary edges."""
    if triangle is None or corner is None:
        return None
    shape = corner.Shape
    worst = 0.0
    for e in triangle.Shape.Edges:
        for i in range(n + 1):
            t = i / float(n)
            p = e.valueAt(e.FirstParameter
                          + t * (e.LastParameter - e.FirstParameter))
            worst = max(worst, shape.distToShape(Part.Vertex(p))[0])
    return worst


def cut_gap(triangle, blends, n=41):
    """The gap between the triangular fill and the 0.75 pieces.

    The triangle's THIRD SIDE (the chord across the corner) against the
    0.75 piece's own surface: the max distance from a point on the chord
    to the piece's surface.  This is the place where the owner's "part
    of the edge blend needs to be replaced with a (patch66? type)
    surface" comes in -- the two surfaces do not share a boundary curve
    there.  Reported, not judged."""
    if triangle is None:
        return None
    chord = None
    for e in triangle.Shape.Edges:
        mid = e.valueAt((e.FirstParameter + e.LastParameter) / 2.0)
        if chord is None or mid.Length > chord[1].Length:
            chord = (e, mid)
    worst = 0.0
    for b in blends:
        for i in range(n + 1):
            t = i / float(n)
            p = chord[0].valueAt(chord[0].FirstParameter
                                 + t * (chord[0].LastParameter
                                        - chord[0].FirstParameter))
            worst = max(worst, b.Shape.distToShape(Part.Vertex(p))[0])
    return worst


def seam_gaps(corner, strips):
    """The seam continuity between the corner and each strip it feeds."""
    net = _corner_net(corner)
    part = _part_surface(list(corner.Poles),
                         list(corner.Weights) or [1.0] * 36, 6)
    out = []
    for s in strips:
        m = per_seam(part, net, s)
        if m is None:
            out.append({"strip": s.Name, "matched": False})
            continue
        out.append({"strip": s.Name, "matched": True,
                    "corner_edge": m["corner_edge"], "row": m["row"],
                    "c0_controlnet": m["c0_controlnet"],
                    "k_gap_exact": m["exact"].get("k_gap"),
                    "k_gap_sampled": m["sampled"].get("k_gap"),
                    "g1_exact": m["exact"].get("g1_deg"),
                    "g1_sampled": m["sampled"].get("g1_deg")})
    return out


# ---------------------------------------------------------------------------
# the rendering
# ---------------------------------------------------------------------------

def _shot(doc, view, key, target, names, rec):
    _only(doc, *names)
    view.redraw()
    path = os.path.join(OUT_DIR, "%s_%s.png" % (key, target))
    view.saveImage(path, IMAGE_SIZE[0], IMAGE_SIZE[1], BACKGROUND)
    rec.setdefault("paths", {})[target] = path
    return path


def render_rolling(doc, res, shipped_corner=None):
    """The rolling corner's pictures.  ONE camera for every image."""
    triangle = res["triangle"]
    pieces = []
    for (c, o) in res["corner_pieces"].values():
        pieces.extend([c, o])
    rec = {"paths": {}}
    _quiesce(doc)
    for p in pieces:
        p.ViewObject.ShapeColor = (0.00, 0.75, 0.25)
        p.ViewObject.Transparency = 25
    if triangle is not None:
        triangle.ViewObject.ShapeColor = TRIANGLE_RGB
        triangle.ViewObject.Transparency = 0
    view = _gui_view(doc.Name)
    set_camera(view)
    _shot(doc, view, "rolling", "1_shaded",
          [p.Name for p in pieces] + ([triangle.Name] if triangle else []),
          rec)
    if triangle is not None:
        _shot(doc, view, "rolling", "2_triangle", [triangle.Name], rec)
    # the shipped corner on the same fixture, for the eye to compare
    if shipped_corner is not None:
        sdoc = shipped_corner[0]
        _quiesce(sdoc)
        shipped_corner[1].ViewObject.ShapeColor = (0.92, 0.55, 0.15)
        sview = _gui_view(sdoc.Name)
        set_camera(sview)
        _shot(sdoc, sview, "shipped", "shaded", [shipped_corner[1].Name], rec)
        # the curvature maps of the shipped corner (the instrument of #118)
        for kind, target in (("ratio", "3_ratio"), ("gauss", "4_gauss")):
            obj, _values, stats = curvature_map(sdoc, shipped_corner[1],
                                                kind, N_CELLS)
            rec.setdefault("stats", {})[kind] = stats
            _shot(sdoc, sview, "rolling", target, [obj.Name], rec)
    rec["legend_ratio"] = draw_legend(
        os.path.join(OUT_DIR, "rolling_legend_ratio.png"), RATIO_STOPS,
        _ratio_ticks(), "curvature ratio |k_max| / |k_min|  (1 = round)")
    rec["legend_gauss"] = draw_legend(
        os.path.join(OUT_DIR, "rolling_legend_gauss.png"), GAUSS_STOPS,
        _gauss_ticks(), "Gaussian curvature k_max * k_min  (/mm^2)")
    return rec


# ---------------------------------------------------------------------------
# the report
# ---------------------------------------------------------------------------

def _fmt(x):
    if x is None:
        return "n/a"
    if isinstance(x, float):
        return "%.4g" % x
    return str(x)


def print_report(rolling, shipped, floor=None):
    print("THE ROLLING CORNER (path B) -- the video's numbers (leader %.2f "
          "on two of the three seams, rotational)" % LEADER)
    print("fixture: Tests/cube_corner_model.py (three planar squares), "
          "never Demo 01")
    print("no ControlGrid66 and no triangular member are built on this path: "
          "the corner face is FreeCAD's own filling")
    print()
    print("IMAGES (one camera for all of them; the same camera "
          "Tests/g2_corner_roll_visual.py uses)")
    for key, label in (("1_shaded", "a  shaded, the rolling corner (the "
                        "triangle + the split blends)"),
                       ("2_triangle", "a  shaded, the triangular surface "
                        "alone"),
                       ("3_ratio", "b  curvature ratio k_max/k_min (the "
                        "SHIPPED corner)"),
                       ("4_gauss", "b  Gaussian curvature k_max*k_min (the "
                        "SHIPPED corner)")):
        print("    %-36s %s" % (label, rolling.get("paths", {}).get(key)))
    print("    %-36s %s" % ("a  shaded, the SHIPPED corner (compare)",
                            rolling.get("paths", {}).get("shaded")))
    print("    %-36s %s" % ("   colour legend (ratio)",
                            rolling.get("legend_ratio")))
    print("    %-36s %s" % ("   colour legend (gaussian)",
                            rolling.get("legend_gauss")))
    print()
    print("THE CURVATURE SPREAD (the exact nets)")
    t = rolling.get("triangle_spread")
    if t:
        print("    %-34s k_max %10.4f  k_min %10.4f  ratio %8.3f"
              % ("the triangular surface (the fill)", t["k_max"], t["k_min"],
                 t["ratio"]))
        print("    %-34s k_max %10.4f  k_min %10.4f  ratio %8.3f"
              % ("  its centre sample", t["centre"][0], t["centre"][1],
                 abs(t["centre"][0]) / abs(t["centre"][1])
                 if abs(t["centre"][1]) > 1e-12 else float("inf")))
        print("    %-34s %d of %d samples are saddle (k1*k2 < 0)"
              % ("  its saddle samples", t["saddle"], t["samples"]))
    s = shipped.get("spread")
    print("    %-34s k_max %10.4f  k_min %10.4f  ratio %8.3f"
          % ("the SHIPPED corner (the 6x6)", s["k_max"], s["k_min"],
             s["ratio"]))
    print("    near-junction ratio range (shipped): %.3f .. %.3f"
          % (s["near_ratio_min"], s["near_ratio_max"]))
    g = shipped.get("stats", {}).get("gauss")
    if g:
        print("    saddle cells on the shipped corner: %d of %d = %.1f %% of "
              "the surface" % (g["saddle_cells"], g["cells"],
                              100.0 * g["saddle_fraction"]))
    print()
    print("THE TRIANGLE / QUAD JUNCTION")
    print("    C0 residual (the triangle's boundary against the shipped "
          "corner's surface): %s mm" % _fmt(rolling.get("junction_residual")))
    print("    gap between the triangle and the split blends' cut edges: "
          "%s mm" % _fmt(rolling.get("cut_gap")))
    print()
    print("SEAM CONTINUITY, the shipped corner against the strips it feeds")
    print("    %-10s %-8s %-14s %-14s %-12s"
          % ("strip", "edge", "k_gap exact", "k_gap sampled", "g1 sampled"))
    for row in rolling.get("seams", []):
        if not row.get("matched"):
            print("    %-10s (no matching junction row)" % row["strip"])
            continue
        print("    %-10s %-8s %-14s %-14s %-12s"
              % (row["strip"], row["corner_edge"],
                 _fmt(row.get("k_gap_exact")), _fmt(row.get("k_gap_sampled")),
                 _fmt(row.get("g1_sampled"))))
    if floor:
        print("    floor (Tests/continuity_calibration): k_gap %s /mm, "
              "c0 %s mm"
              % (_fmt(floor.get("k_gap", {}).get("analytic")),
                 _fmt(floor.get("c0", {}).get("analytic"))))
    print()


def main(out_dir=None):
    """Build, render and measure the rolling corner; print where it all is."""
    out_dir = out_dir or OUT_DIR
    os.makedirs(out_dir, exist_ok=True)
    doc, res = build_rolling("rolling_corner")
    sdoc, sstrips, shipped_corner = build_shipped("shipped_corner")

    rolling = {}
    rolling["triangle_spread"] = triangle_spread(res["triangle"])
    rolling["junction_residual"] = junction_residual(res["triangle"],
                                                      shipped_corner)
    rolling["cut_gap"] = cut_gap(res["triangle"],
                                 [o for (_c, o) in res["corner_pieces"].values()])
    corner_pieces = [c for (c, _o) in res["corner_pieces"].values()]
    rolling["seams"] = seam_gaps(shipped_corner, sstrips)
    shipped = {"spread": spread_report(shipped_corner)}
    shipped["seams"] = seam_gaps(shipped_corner, sstrips)

    rec = render_rolling(doc, res, shipped_corner=(sdoc, shipped_corner))
    rolling.update(rec)

    shipped["stats"] = rec.get("stats", {})

    try:
        from Tests.continuity_calibration import error_floor
        floor = error_floor()
    except Exception:
        floor = None
    print_report(rolling, shipped, floor)
    for name in ("rolling_corner", "shipped_corner"):
        if name in FreeCAD.listDocuments():
            FreeCAD.closeDocument(name)
    return {"rolling": rolling, "shipped": shipped, "out_dir": out_dir}


if __name__ == "__main__":
    main()
