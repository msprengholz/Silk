"""
MANUAL VISUAL + MEASUREMENT -- the ROLLING CORNER at the video's numbers
(ticket #119, part of #1 the map).

WHY THIS EXISTS.  The owner looked at the shipped corner and ruled
(2026-10-21): *"the patch has weirdly rounded edges. I would not consider
this to be a rolling corner like described by the silk maintainer. ...
I only see one surface, but it should be two!"*  #119 is the build: cut
the edge blends along their seams at a "rolling leader" (a position ON
the seam curve, measured from the junction corner), and give the corner
a small triangular surface of its own.

WHAT IS RENDERED, all from ONE camera (the same one
`Tests/g2_corner_roll_visual.py` uses, so the two sets of images are
comparable):

  (a) shaded, the rolling corner alone .......... rolling_1_shaded.png
  (b) shaded, the rolling corner + the triangle .. rolling_2_shaded_triangle.png
  (c) shaded, the SHIPPED corner alone (the same
      junction, no leader) for comparison ....... shipped_1_shaded.png
  (d) curvature ratio k_max/k_min ................ rolling_3_ratio.png
  (e) Gaussian curvature k_max*k_min ............ rolling_4_gauss.png
  plus the two shared colour legends.

WHAT IS MEASURED, beside the pictures:

  1. the corner's OWN curvature spread (k_max / k_min) at the junction,
     on the stored 6x6 net -- the rolling corner against the shipped
     corner on the SAME fixture, so the difference is the leader and
     nothing else;
  2. how many cells of the corner's own surface are saddle (k1*k2 < 0);
  3. the C0 residual at the new triangle/quad junction: the distance
     between the triangle's boundary and the corner's own surface;
  4. the seam `k_gap` of the split blends against the corner they feed,
     with the calibrated floor beside it.

NOTHING HERE IS A CLAIM.  No continuity label, no verdict on whether the
result rolls: the images and the numbers are the evidence and the
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
    """The rolling corner: the fixture, the two split blends, the triangle,
    the corner built from the ring of the corner-side pieces."""
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
    full-seam strips, no leader."""
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


def spread_report(corner):
    """The corner's own curvature spread at and near the junction."""
    net = _corner_net(corner)
    probe = junction_probe(net)
    centre = probe["centre"]
    return {"k_max": centre[0], "k_min": centre[1], "ratio": centre[2],
            "centre_k1k2": probe["centre_k1k2"],
            "near_ratio_min": probe["near_ratio_min"],
            "near_ratio_max": probe["near_ratio_max"],
            "foot": probe["foot"]}


def triangle_junction_residual(triangle, corner, n=41):
    """The C0 residual at the triangle/quad junction.

    The triangle's boundary against the corner's own surface: the max
    distance from a point on the triangle's boundary to the corner's
    surface, sampled along the three boundary edges.  It is the number
    that says how well the two surfaces meet where they meet."""
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


def triangle_reach(triangle, corner):
    """How far the triangle's own VERTICES reach from the corner's surface.

    The corner's surface and the triangle can CROSS (the triangle is built
    over the corner-side region, the corner's own surface bulges over it).
    This is the max distance from a vertex of the triangle to the corner's
    own surface -- how far the two surfaces are apart at their corners.
    Reported, not judged."""
    if triangle is None or corner is None:
        return None
    worst = 0.0
    for v in triangle.Shape.Vertexes:
        worst = max(worst, corner.Shape.distToShape(v)[0])
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
    corner = res["corner_blend"]
    triangle = res["triangle"]
    rec = {"paths": {}}
    _quiesce(doc)
    corner.ViewObject.ShapeColor = (0.92, 0.55, 0.15)
    if triangle is not None:
        triangle.ViewObject.ShapeColor = TRIANGLE_RGB
        triangle.ViewObject.Transparency = 20
    view = _gui_view(doc.Name)
    set_camera(view)
    _shot(doc, view, "rolling", "1_shaded", [corner.Name], rec)
    if triangle is not None:
        _shot(doc, view, "rolling", "2_shaded_triangle",
              [corner.Name, triangle.Name], rec)
    # the curvature maps of the corner's own surface
    for kind, target in (("ratio", "3_ratio"), ("gauss", "4_gauss")):
        obj, _values, stats = curvature_map(doc, corner, kind, N_CELLS)
        rec.setdefault("stats", {})[kind] = stats
        _shot(doc, view, "rolling", target, [obj.Name], rec)
    # the shipped corner on the same fixture, for the eye to compare
    if shipped_corner is not None:
        sdoc = shipped_corner[0]
        _quiesce(sdoc)
        shipped_corner[1].ViewObject.ShapeColor = (0.92, 0.55, 0.15)
        sview = _gui_view(sdoc.Name)
        set_camera(sview)
        _shot(sdoc, sview, "shipped", "shaded",
              [shipped_corner[1].Name], rec)
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
    print("THE ROLLING CORNER -- the video's numbers (leader %.2f on two of "
          "the three seams, rotational)" % LEADER)
    print("fixture: Tests/cube_corner_model.py (three planar squares), "
          "never Demo 01")
    print()
    print("IMAGES (one camera for all of them; the same camera "
          "Tests/g2_corner_roll_visual.py uses)")
    for key, label in (("1_shaded", "a  shaded, the rolling corner alone"),
                       ("2_shaded_triangle", "a  shaded, the corner + the "
                        "triangle"),
                       ("3_ratio", "b  curvature ratio k_max/k_min"),
                       ("4_gauss", "b  Gaussian curvature k_max*k_min")):
        print("    %-36s %s" % (label, rolling.get("paths", {}).get(key)))
    print("    %-36s %s" % ("a  shaded, the SHIPPED corner (compare)",
                            rolling.get("paths", {}).get("shaded")))
    print("    %-36s %s" % ("   colour legend (ratio)",
                            rolling.get("legend_ratio")))
    print("    %-36s %s" % ("   colour legend (gaussian)",
                            rolling.get("legend_gauss")))
    print()
    print("THE CORNER'S OWN CURVATURE SPREAD (the exact 6x6 net)")
    print("    %-22s %12s %12s %10s" % ("", "k_max", "k_min", "k_max/k_min"))
    for label, rep in (("rolling (leader 0.25)", rolling["spread"]),
                       ("shipped (no leader)", shipped["spread"])):
        print("    %-22s %12.4f %12.4f %10.3f"
              % (label, rep["k_max"], rep["k_min"], rep["ratio"]))
    print("    near-junction ratio range: rolling %.3f .. %.3f, shipped "
          "%.3f .. %.3f"
          % (rolling["spread"]["near_ratio_min"],
             rolling["spread"]["near_ratio_max"],
             shipped["spread"]["near_ratio_min"],
             shipped["spread"]["near_ratio_max"]))
    dev = rolling.get("pole_deviation_vs_shipped")
    if dev is not None:
        print("    the two corners' 36-pole grids differ by at most %.3e mm "
              "(the ring's own start differs between the two builds, so this "
              "is not a shape difference)" % dev)
    g = rolling.get("stats", {}).get("gauss")
    if g:
        print("    saddle cells (k1*k2 < 0) on the rolling corner: %d of %d "
              "= %.1f %% of the surface"
              % (g["saddle_cells"], g["cells"], 100.0 * g["saddle_fraction"]))
    gs = shipped.get("stats", {}).get("gauss")
    if gs:
        print("    saddle cells on the shipped corner:              %d of %d "
              "= %.1f %% of the surface"
              % (gs["saddle_cells"], gs["cells"], 100.0 * gs["saddle_fraction"]))
    print()
    print("THE TRIANGLE / QUAD JUNCTION")
    print("    C0 residual (the triangle's boundary against the corner's "
          "own surface): %s mm"
          % _fmt(rolling.get("junction_residual")))
    print("    the triangle's own vertices reach %s mm from the corner's "
          "surface" % _fmt(rolling.get("reach")))
    print()
    print("SEAM CONTINUITY, the corner against the strips it feeds")
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

    rolling = {"spread": spread_report(res["corner_blend"])}
    rolling["junction_residual"] = triangle_junction_residual(
        res["triangle"], res["corner_blend"])
    rolling["reach"] = triangle_reach(res["triangle"],
                                      res["corner_blend"])
    rolling["pole_deviation_vs_shipped"] = max(
        (a - b).Length
        for a, b in zip(res["corner_blend"].Poles, shipped_corner.Poles))
    corner_pieces = [c for (c, _o) in res["corner_pieces"].values()]
    rolling["seams"] = seam_gaps(res["corner_blend"], corner_pieces)
    shipped = {"spread": spread_report(shipped_corner)}
    shipped["seams"] = seam_gaps(shipped_corner, sstrips)

    rec = render_rolling(doc, res, shipped_corner=(sdoc, shipped_corner))
    rolling.update(rec)

    # the shipped corner's curvature map, for the numbers only
    _quiesce(sdoc)
    _obj, _v, stats = curvature_map(sdoc, shipped_corner, "gauss", N_CELLS)
    shipped["stats"] = {"gauss": stats}

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
