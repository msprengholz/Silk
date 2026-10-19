"""
MANUAL VISUAL + MEASUREMENT -- the ROLLING CORNER, path (A) (ticket #119).

WHY THIS EXISTS.  The previous build (#119, path B) put a FreeCAD
`Surface::Filling` beside two split blends and reported a GAP at the
junction: the fill's chord sat 0.2915 mm from the 0.75 piece's
surface, because a triangular fill cannot share a boundary curve with
a band cut across it.

PATH (A) IS THE MAINTAINER'S OWN STRUCTURE, read offline from
`upstream/Resources/Tutorial_Files/Silk CopyPasta/
Silk_CopyPasta_27_First_Corner_Rolled.FCStd`:

  * the corner is a `ControlGrid66_4Sub` over FOUR ring members --
    three blends and one TRIANGULAR MEMBER (`ControlGrid64_3_1Grid44`
    over the corner patch's corner cell);
  * the corner patch's base surface is CUT at the rolling leader: its
    band's cells start there, so the corner fill's boundary against
    each blend is that blend's CUT EDGE -- the junction is closed,
    not gapped;
  * the small triangular surface beside the 66 is the member's own
    face (`CubicSurface_64` over the member's grid) -- the surface the
    owner wants replaced with a FreeCAD surface patch.

So this script builds that: the 66 (Silk's own chain) over the cut
cells, the small triangular surface beside it, and the FreeCAD filling
that replaces it -- and measures it against the shipped corner.

WHAT IS MEASURED, beside the pictures:

  1. the corner's own curvature spread (k_max / k_min) and the fraction
     of saddle cells -- the instrument of #118 -- for the SHIPPED
     corner and for path (A) at two different leaders;
  2. the C0 AT THE CUT: each blend's cut edge against the 66's own
     surface (this is the residual path (B) left at 0.2915 mm);
  3. the C0 where the SMALL TRIANGULAR SURFACE (and its FreeCAD
     replacement) meets the 66;
  4. the seam `k_gap` of every seam, exact and sampled, with the
     instrument's floor beside it.

WHAT IS RENDERED, all from ONE camera (the same fixed camera
`Tests/g2_corner_roll_visual.py` uses, so the pictures are comparable
with that module's and with #119's):

  (a) shaded, the rolling corner ......... rolling66_1_shaded.png
  (b) shaded, the small triangular surface  rolling66_2_member.png
  (c) shaded, the SHIPPED corner (compare) ... rolling66_3_shipped.png
  (d) Gaussian curvature k_max*k_min of the rolling corner
      ....................................... rolling66_4_gauss.png
  (e) the same map of the SHIPPED corner .... rolling66_5_gauss_shipped.png
  plus the shared colour legends.

MANUAL-ONLY: the file name is not `test_*.py`, so `Tests/suite.py` does
not discover it.  `Tests/test_continuity_instrument.py` asserts this
module imports, exposes `main`, and carries `MANUAL`.

Run (live GUI over XML-RPC, or in a GUI FreeCAD):

    import Tests.rolling_corner_66_visual as v; v.main()
"""

import os

import FreeCAD
import Part

import Tests.silk_nurbs as SN
from Tests.g2_corner_roll_measure import (principal_curvatures, per_seam,
                                           junction_probe, _part_surface)
from Tests.g2_corner_roll_visual import (curvature_map, set_camera, _quiesce,
                                          _only, _gui_view, draw_legend,
                                          RATIO_STOPS, GAUSS_STOPS,
                                          _ratio_ticks, _gauss_ticks,
                                          IMAGE_SIZE, BACKGROUND, N_CELLS)
from SilkWorkflowOps import (create_rolling_corner_66, create_corner_blend,
                             corner_fill_boundary)
from Tests import cube_corner_model as ccm

MANUAL = True

OUT_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "Resources", "Test_files", "_inspect")

LEADER = 0.25          # the video's number: 0.25 along the seam
OTHER_LEADER = 0.5     # the second leader the shape is measured at
MEMBER_RGB = (0.20, 0.45, 0.95)
CORNER_RGB = (0.92, 0.55, 0.15)


# ---------------------------------------------------------------------------
# the two corners on the same fixture
# ---------------------------------------------------------------------------

def _fixture(doc_name):
    if doc_name in FreeCAD.listDocuments():
        FreeCAD.closeDocument(doc_name)
    doc = FreeCAD.newDocument(doc_name)
    FreeCAD.setActiveDocument(doc.Name)
    ccm.build_cube_corner_model(doc)
    doc.recompute()
    doc.recompute()
    strips = [doc.getObject(n) for n in ("B_AB", "B_BC", "B_CA")]
    return doc, strips


def build_shipped(doc_name="rolling66_shipped"):
    """The shipped corner on the same fixture -- the reference."""
    doc, strips = _fixture(doc_name)
    corner = create_corner_blend(*strips, name="ShippedCorner")
    doc.recompute()
    return doc, strips, corner


def build_rolling(doc_name="rolling66_roll", leader=LEADER):
    """Path (A): the rolling corner -- the 66 over the cut cells, the
    small triangular surface beside it, and the FreeCAD replacement of
    that surface.  The leader is rolled on the two seams the pinned
    patch carries (rotational), the third seam is left alone."""
    doc, strips = _fixture(doc_name)
    patch = doc.getObject("PatchA")
    rolled = [s for s in strips
              if s.PatchA is patch or s.PatchB is patch]
    res = create_rolling_corner_66(strips, patch, leader=leader,
                                   seams=rolled, name="Roll")
    doc.recompute()
    return doc, strips, res


# ---------------------------------------------------------------------------
# the measurements
# ---------------------------------------------------------------------------

def _corner_net(corner):
    return SN.NurbsSurface.from_flat(list(corner.Poles),
                                     list(corner.Weights) or [1.0] * 36,
                                     6, 6, SN.KNOTS_6, SN.KNOTS_6)


def spread_report(corner):
    """The corner's own curvature spread at and near the junction."""
    net = _corner_net(corner)
    probe = junction_probe(net)
    centre = probe["centre"]
    return {"k_max": centre[0], "k_min": centre[1], "ratio": centre[2],
            "near_ratio_min": probe["near_ratio_min"],
            "near_ratio_max": probe["near_ratio_max"]}


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
                    "corner_edge": m["corner_edge"],
                    "c0_controlnet": m["c0_controlnet"],
                    "k_gap_exact": m["exact"].get("k_gap"),
                    "k_gap_sampled": m["sampled"].get("k_gap"),
                    "g1_exact": m["exact"].get("g1_deg"),
                    "g1_sampled": m["sampled"].get("g1_deg")})
    return out


def _edge_distance(shape, other_shape, n=41):
    """The max distance from a shape's boundary to another shape."""
    worst = 0.0
    for e in shape.Edges:
        for i in range(n + 1):
            t = i / float(n)
            p = e.valueAt(e.FirstParameter
                          + t * (e.LastParameter - e.FirstParameter))
            worst = max(worst, other_shape.distToShape(Part.Vertex(p))[0])
    return worst


def cut_residual(corner, strips):
    """The C0 AT THE CUT: every blend's junction row (its cut edge)
    against the corner fill's own surface.

    This is the residual path (B) left at 0.2915 mm: there the fill's
    third side and the band's cut edge did not share a curve.  Here the
    corner fill's boundary IS the cut edge, so this is the number that
    says whether the junction is closed."""
    out = []
    boundary, why = corner_fill_boundary(strips)
    if boundary is None:
        return [{"strip": "?", "why": why}]
    links, _faces = boundary
    for (obj, sub) in links:
        edge = obj.Shape.getElement(sub)
        worst = 0.0
        for i in range(41):
            t = i / 40.0
            p = edge.valueAt(edge.FirstParameter
                             + t * (edge.LastParameter - edge.FirstParameter))
            worst = max(worst, corner.Shape.distToShape(Part.Vertex(p))[0])
        out.append({"strip": obj.Name, "edge": sub, "c0": worst})
    return out


def member_residual(corner, member):
    """The C0 where the small triangular surface meets the 66 (the
    worst distance over its boundary), and the distance at the apex."""
    if member is None or not member.Shape.Edges:
        return None
    worst = 0.0
    apex = 0.0
    for e in member.Shape.Edges:
        for i in range(21):
            t = i / 20.0
            p = e.valueAt(e.FirstParameter
                          + t * (e.LastParameter - e.FirstParameter))
            d = corner.Shape.distToShape(Part.Vertex(p))[0]
            worst = max(worst, d)
            if e.Length <= 1e-9:
                apex = max(apex, d)
    return {"worst": worst, "apex": apex}


def fill_residual(fill, member, corner):
    """The FreeCAD replacement's own residuals: against the member face
    it replaces, and against the 66."""
    if fill is None or not fill.Shape.Edges:
        return None
    return {"to_member": _edge_distance(fill.Shape, member.Shape),
            "to_corner": _edge_distance(fill.Shape, corner.Shape)}


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


def render(rolling_doc, res, shipped_doc, shipped_corner, rec):
    """Every picture from ONE camera."""
    corner = res["corner"]
    member = res["member"]
    _quiesce(rolling_doc)
    corner.ViewObject.ShapeColor = CORNER_RGB
    corner.ViewObject.Transparency = 0
    if member is not None:
        member.ViewObject.ShapeColor = MEMBER_RGB
        member.ViewObject.Transparency = 0
    view = _gui_view(rolling_doc.Name)
    set_camera(view)
    names = [corner.Name] + ([member.Name] if member is not None else [])
    _shot(rolling_doc, view, "rolling66", "1_shaded", names, rec)
    if member is not None:
        _shot(rolling_doc, view, "rolling66", "2_member", [member.Name], rec)
    # the shipped corner, from the same camera
    _quiesce(shipped_doc)
    shipped_corner.ViewObject.ShapeColor = CORNER_RGB
    sview = _gui_view(shipped_doc.Name)
    set_camera(sview)
    _shot(shipped_doc, sview, "rolling66", "3_shipped",
          [shipped_corner.Name], rec)
    # the curvature maps (the instrument of #118), both corners
    for kind, target, doc_, obj in (("gauss", "4_gauss", rolling_doc, corner),
                                     ("gauss", "5_gauss_shipped", shipped_doc,
                                      shipped_corner)):
        mobj, _values, stats = curvature_map(doc_, obj, kind, N_CELLS)
        rec.setdefault("stats", {})[target] = stats
        _shot(doc_, sview if doc_ is shipped_doc else view, "rolling66",
              target, [mobj.Name], rec)
    rec["legend_ratio"] = draw_legend(
        os.path.join(OUT_DIR, "rolling66_legend_ratio.png"), RATIO_STOPS,
        _ratio_ticks(), "curvature ratio |k_max| / |k_min|  (1 = round)")
    rec["legend_gauss"] = draw_legend(
        os.path.join(OUT_DIR, "rolling66_legend_gauss.png"), GAUSS_STOPS,
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


def print_report(rows, floor=None):
    print("THE ROLLING CORNER, path (A) -- the 66 chain over the cut cells")
    print("fixture: Tests/cube_corner_model.py (three planar squares)")
    print()
    print("THE SHAPE (the acceptance instrument: does the leader move it?)")
    print("    %-26s %-11s %-11s %-10s %s"
          % ("configuration", "k_max", "k_min", "ratio", "saddle cells"))
    for r in rows:
        print("    %-26s %-11.5g %-11.5g %-10.5g %d/%d = %.1f %%"
              % (r["label"], r["k_max"], r["k_min"], r["ratio"],
                 r["saddle_cells"], r["cells"], 100.0 * r["saddle_fraction"]))
    print()
    print("THE JUNCTION (the residual path (B) left at 0.2915 mm)")
    for r in rows:
        if not r.get("cuts"):
            continue
        print("    %s:" % r["label"])
        for c in r["cuts"]:
            print("        %-10s %-8s C0 %s mm"
                  % (c.get("strip"), c.get("edge"), _fmt(c.get("c0"))))
    for r in rows:
        if r.get("member_residual"):
            m = r["member_residual"]
            print("    %s: the small triangular surface against the 66: "
                  "worst %s mm, at the apex %s mm"
                  % (r["label"], _fmt(m["worst"]), _fmt(m["apex"])))
        if r.get("fill_residual"):
            f = r["fill_residual"]
            print("    %s: the FreeCAD replacement against the member face "
                  "%s mm, against the 66 %s mm"
                  % (r["label"], _fmt(f["to_member"]), _fmt(f["to_corner"])))
    print()
    print("SEAM CONTINUITY, the corner against the strips it feeds")
    for r in rows:
        print("    %s:" % r["label"])
        for row in r.get("seams", []):
            if not row.get("matched"):
                print("        %-10s (no matching junction row)" % row["strip"])
                continue
            print("        %-10s %-8s k_gap exact %-12s sampled %-12s"
                  % (row["strip"], row["corner_edge"],
                     _fmt(row.get("k_gap_exact")), _fmt(row.get("k_gap_sampled"))))
    if floor:
        print("    floor (Tests/continuity_calibration): k_gap %s /mm, "
              "c0 %s mm"
              % (_fmt(floor.get("k_gap", {}).get("analytic")),
                 _fmt(floor.get("c0", {}).get("analytic"))))
    print()
    print("IMAGES (one camera for all of them)")
    for key, label in (("1_shaded", "shaded, the rolling corner"),
                       ("2_member", "shaded, the small triangular surface"),
                       ("3_shipped", "shaded, the SHIPPED corner"),
                       ("4_gauss", "Gaussian curvature of the rolling corner"),
                       ("5_gauss_shipped",
                        "Gaussian curvature of the SHIPPED corner")):
        print("    %-46s %s" % (label, rows[0].get("paths", {}).get(key)))


def main(out_dir=None):
    out_dir = out_dir or OUT_DIR
    os.makedirs(out_dir, exist_ok=True)
    sdoc, sstrips, shipped = build_shipped()
    rdoc, rstrips, res = build_rolling("rolling66_roll", LEADER)
    rdoc2, rstrips2, res2 = build_rolling("rolling66_roll50", OTHER_LEADER)

    rows = []
    cases = (("shipped corner", sdoc, sstrips, shipped, None, None),
             ("path (A), leader %.2f" % LEADER, rdoc, rstrips, res["corner"],
              res["member"], res.get("member_fill")),
             ("path (A), leader %.2f" % OTHER_LEADER, rdoc2, rstrips2,
              res2["corner"], res2["member"], res2.get("member_fill")))
    for label, doc_, strips, corner, member, fill in cases:
        s = spread_report(corner)
        _obj, _values, stats = curvature_map(doc_, corner, "gauss", N_CELLS)
        row = {"label": label, "k_max": s["k_max"], "k_min": s["k_min"],
               "ratio": s["ratio"], "saddle_cells": stats["saddle_cells"],
               "cells": stats["cells"],
               "saddle_fraction": stats["saddle_fraction"],
               "near_ratio": (s["near_ratio_min"], s["near_ratio_max"]),
               "cuts": cut_residual(corner, strips),
               "seams": seam_gaps(corner, strips)}
        if member is not None:
            row["member_residual"] = member_residual(corner, member)
            row["fill_residual"] = fill_residual(fill, member, corner)
        rows.append(row)

    rec = render(rdoc, res, sdoc, shipped, {})
    rows[0]["paths"] = rec.get("paths", {})
    rows[1]["paths"] = rec.get("paths", {})
    rows[0]["legend_ratio"] = rec.get("legend_ratio")
    rows[0]["legend_gauss"] = rec.get("legend_gauss")
    rows[1]["stats"] = rec.get("stats", {})

    try:
        from Tests.continuity_calibration import error_floor
        floor = error_floor()
    except Exception:
        floor = None
    print_report(rows, floor)
    for name in ("rolling66_shipped", "rolling66_roll", "rolling66_roll50"):
        if name in FreeCAD.listDocuments():
            FreeCAD.closeDocument(name)
    return {"rows": rows, "out_dir": out_dir}


if __name__ == "__main__":
    main()
