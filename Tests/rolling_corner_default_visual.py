"""
MANUAL VISUAL + MEASUREMENT -- the ROLLING CORNER AS THE DEFAULT (#119).

WHAT THIS IS.  The rolling corner is the corner stage's DEFAULT
construction since #119 (the owner, 2026-10-21: *"the rolling corner
fill should be the default fill!"*), and the shipped 66-with-the-
spiderweb-member is the selectable fallback.  This script measures the
DEFAULT as it stands and renders it, with the shipped corner from the
SAME camera for comparison.

THE MEASUREMENTS (all with the shipped instruments, and with the
instrument's floor beside every figure):

  1. the corner's own curvature spread (k_max / k_min) and the fraction
     of saddle cells -- the instrument of #118 -- for the shipped
     corner, for the rolling corner at the maintainer's 0.25, and for
     the rolling corner at a second leader (0.5);
  2. the seam `k_gap` of every seam, exact (from the control net) and
     sampled (along the seam), with the instrument's floor;
  3. the C0 AT THE CUT: every blend's cut edge against the corner
     fill's own surface;
  4. the C0 where the MEMBER'S FACE (the FreeCAD filling) meets the 66,
     and the fill's own TANGENT-PLANE GAP against the silk face it
     replaces -- the shipped instrument (`fill_normal_gap`), with the
     instrument's floor (4.5e-13 mm) and the shipped bar (1.0 deg);
  5. the FALLBACK path's byte-identity: the shipped corner built twice,
     pole for pole and weight for weight.

THE RENDERS, all from ONE camera (the fixed camera
`Tests/g2_corner_roll_visual.py` uses, so the pictures are comparable
with that module's and with #119's):

  (a) shaded, the rolling corner ............. rollingdef_1_shaded.png
  (b) shaded, the member's face (the fill) .... rollingdef_2_member.png
  (c) shaded, the SHIPPED corner (compare) .... rollingdef_3_shipped.png
  (d) Gaussian curvature k_max*k_min of the rolling corner
      ......................................... rollingdef_4_gauss.png
  (e) the same map of the SHIPPED corner ....... rollingdef_5_gauss_shipped.png
  plus the shared colour legends.

MANUAL-ONLY: the file name is not `test_*.py`, so `Tests/suite.py` does
not discover it.  `Tests/test_continuity_instrument.py` asserts that every
measurement script carries `MANUAL = True`.

Run (live GUI over XML-RPC, or in a GUI FreeCAD):

    import Tests.rolling_corner_default_visual as v; v.main()
"""

import os

import FreeCAD
import Part

import Tests.silk_nurbs as SN
from Tests.g2_corner_roll_measure import (per_seam, junction_probe,
                                           _part_surface)
from Tests.g2_corner_roll_visual import (curvature_map, set_camera, _quiesce,
                                          _only, _gui_view, draw_legend,
                                          RATIO_STOPS, GAUSS_STOPS,
                                          _ratio_ticks, _gauss_ticks,
                                          IMAGE_SIZE, BACKGROUND, N_CELLS)
from SilkWorkflowOps import (create_corner_blend, create_fill,
                             fill_normal_gap, corner_fill_boundary)
from Tests import cube_corner_model as ccm

MANUAL = True

OUT_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "Resources", "Test_files", "_inspect")

LEADER = 0.25          # the video's number: 0.25 along the seam
OTHER_LEADER = 0.5     # the second leader the shape is measured at
MEMBER_RGB = (0.20, 0.45, 0.95)
CORNER_RGB = (0.92, 0.55, 0.15)
FILL_RGB = (0.30, 0.70, 0.95)


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


def build_shipped(doc_name="rollingdef_shipped"):
    """The SHIPPED corner -- the fallback -- on the same fixture."""
    doc, strips = _fixture(doc_name)
    corner = create_corner_blend(*strips, name="ShippedCorner",
                                 construction="shipped")
    doc.recompute()
    return doc, strips, corner


def build_rolling(doc_name="rollingdef_roll", leader=LEADER):
    """The DEFAULT: the rolling corner -- the 66 over the cut cells, the
    small triangular member, and its FreeCAD filling (the member's
    face)."""
    doc, strips = _fixture(doc_name)
    corner = create_corner_blend(*strips, name="Roll", leader=leader)
    doc.recompute()
    return doc, strips, corner


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
    against the corner fill's own surface."""
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


def member_report(corner, member, fill):
    """THE MEMBER'S FACE (STAGE 1): the FreeCAD filling that replaces the
    spiderweb -- its continuity against the silk face it replaces, and
    the C0 where it meets the 66.

    Also the ANSWER to "can the fill take the member boundary as it
    is?": the member's collapsed row is a DEGENERATE edge (its two
    ends are the apex), so it is not a curve a fill can take -- the
    fill takes the member's three REAL edges."""
    out = {"member": None, "fill": None, "gap": None, "junction_c0": None}
    if member is None:
        return out
    out["member"] = {
        "faces": len(member.Shape.Faces),
        "edges": len(member.Shape.Edges),
        "degenerate_edges": sum(1 for e in member.Shape.Edges
                                if e.Length <= 1e-9),
        "boundary_edges": list(getattr(member, "BoundaryEdges", None) or []),
    }
    if fill is None:
        return out
    out["fill"] = {
        "name": fill.Name,
        "type": getattr(fill, "TypeId", "?"),
        "faces": len(fill.Shape.Faces),
        "order": list(fill.BoundaryOrder),
        "boundary": [(o.Name, list(s)) for o, s in fill.BoundaryEdges],
    }
    links = [(member, name) for name in
             (getattr(member, "BoundaryEdges", None) or [])]
    faces = ["Face1"] * len(links)
    gap = fill_normal_gap(fill, links, faces)
    out["gap"] = {"max_gap_deg": gap["max_gap_deg"],
                  "measurable": gap["measurable"],
                  "per_edge": gap["per_edge"]}
    out["junction_c0"] = _edge_distance(fill.Shape, corner.Shape)
    out["to_member"] = _edge_distance(fill.Shape, member.Shape)
    return out


def fallback_identity(doc_name="rollingdef_fallback"):
    """The FALLBACK path's byte-identity: the shipped corner built twice,
    in two documents, pole for pole and weight for weight."""
    d1, s1, c1 = build_shipped(doc_name + "1")
    d2, s2, c2 = build_shipped(doc_name + "2")
    try:
        p1 = [FreeCAD.Vector(v) for v in c1.Poles]
        p2 = [FreeCAD.Vector(v) for v in c2.Poles]
        pole = max((a - b).Length for a, b in zip(p1, p2)) if p1 else None
        w1 = list(c1.Weights or [])
        w2 = list(c2.Weights or [])
        weight = max(abs(a - b) for a, b in zip(w1, w2)) if w1 else None
        return {"pole": pole, "weight": weight}
    finally:
        for d in (d1, d2):
            if d.Name in FreeCAD.listDocuments():
                FreeCAD.closeDocument(d.Name)


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


def render(rolling_doc, corner, member, fill, shipped_doc, shipped_corner,
           rec):
    """Every picture from ONE camera."""
    _quiesce(rolling_doc)
    corner.ViewObject.ShapeColor = CORNER_RGB
    corner.ViewObject.Transparency = 0
    if member is not None:
        member.ViewObject.ShapeColor = MEMBER_RGB
        member.ViewObject.Transparency = 0
    if fill is not None:
        try:
            fill.ViewObject.ShapeColor = FILL_RGB
            fill.ViewObject.Transparency = 0
        except Exception:
            pass
    view = _gui_view(rolling_doc.Name)
    set_camera(view)
    # what the eye sees: the corner and the member's FACE -- the FreeCAD
    # filling.  The silk member behind it is hidden (the fill IS the
    # member's face since #119), so it is not in the shot.
    face_names = []
    if fill is not None:
        face_names.append(fill.Name)
    elif member is not None:
        face_names.append(member.Name)
    names = [corner.Name] + face_names
    _shot(rolling_doc, view, "rollingdef", "1_shaded", names, rec)
    if face_names:
        _shot(rolling_doc, view, "rollingdef", "2_member", face_names, rec)
    # the shipped corner, from the same camera
    _quiesce(shipped_doc)
    shipped_corner.ViewObject.ShapeColor = CORNER_RGB
    sview = _gui_view(shipped_doc.Name)
    set_camera(sview)
    _shot(shipped_doc, sview, "rollingdef", "3_shipped",
          [shipped_corner.Name], rec)
    # the curvature maps (the instrument of #118), both corners
    for kind, target, doc_, obj in (("gauss", "4_gauss", rolling_doc, corner),
                                     ("gauss", "5_gauss_shipped", shipped_doc,
                                      shipped_corner)):
        mobj, _values, stats = curvature_map(doc_, obj, kind, N_CELLS)
        rec.setdefault("stats", {})[target] = stats
        _shot(doc_, sview if doc_ is shipped_doc else view, "rollingdef",
              target, [mobj.Name], rec)
    rec["legend_ratio"] = draw_legend(
        os.path.join(OUT_DIR, "rollingdef_legend_ratio.png"), RATIO_STOPS,
        _ratio_ticks(), "curvature ratio |k_max| / |k_min|  (1 = round)")
    rec["legend_gauss"] = draw_legend(
        os.path.join(OUT_DIR, "rollingdef_legend_gauss.png"), GAUSS_STOPS,
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


def print_report(rows, floor=None, fallback=None):
    print("THE ROLLING CORNER AS THE DEFAULT (#119)")
    print("fixture: Tests/cube_corner_model.py (three planar squares)")
    print()
    print("THE SHAPE (the acceptance instrument: does the leader move it?)")
    print("    %-26s %-11s %-11s %-10s %s"
          % ("configuration", "k_max", "k_min", "ratio", "saddle cells"))
    for r in rows:
        print("    %-26s %-11.5g %-11.5g %-10.5g %d/%d = %.1f %%"
              % (r["label"], r["k_max"], r["k_min"], r["ratio"],
                 r["saddle_cells"], r["cells"],
                 100.0 * r["saddle_fraction"]))
    print()
    print("THE JUNCTION (the residual path (B) left at 0.2915 mm)")
    for r in rows:
        if not r.get("cuts"):
            continue
        print("    %s:" % r["label"])
        for c in r["cuts"]:
            print("        %-10s %-8s C0 %s mm"
                  % (c.get("strip"), c.get("edge"), _fmt(c.get("c0"))))
    print()
    print("THE MEMBER'S FACE (the FreeCAD filling that replaces the "
          "spiderweb)")
    for r in rows:
        m = r.get("member")
        if not m or not m.get("member"):
            continue
        print("    %s:" % r["label"])
        print("        the silk member: %d face(s), %d edge(s) (%d "
              "degenerate), the fill's boundary: %s"
              % (m["member"]["faces"], m["member"]["edges"],
                 m["member"]["degenerate_edges"],
                 m["member"]["boundary_edges"]))
        if m.get("fill"):
            print("        the fill: %s (%s), %d face(s), built at order %s"
                  % (m["fill"]["name"], m["fill"]["type"], m["fill"]["faces"],
                     m["fill"]["order"]))
        if m.get("gap"):
            print("        the tangent-plane gap against the silk face: %s "
                  "deg (measurable: %s)"
                  % (_fmt(m["gap"]["max_gap_deg"]), m["gap"]["measurable"]))
            for e in m["gap"]["per_edge"]:
                print("            %-28s gap %-10s residual %-10s stations %d"
                      % (e["label"], _fmt(e["gap_deg"]),
                         _fmt(e["residual"]), e["stations"]))
        print("        the fill against the 66: C0 %s mm; against the silk "
              "member: %s mm"
              % (_fmt(m.get("junction_c0")), _fmt(m.get("to_member"))))
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
    if fallback:
        print()
        print("THE FALLBACK PATH (construction='shipped'), built twice: "
              "max pole deviation %s mm, max weight deviation %s"
              % (_fmt(fallback.get("pole")), _fmt(fallback.get("weight"))))
    print()
    print("IMAGES (one camera for all of them)")
    for key, label in (("1_shaded", "shaded, the rolling corner"),
                       ("2_member", "shaded, the member's face (the fill)"),
                       ("3_shipped", "shaded, the SHIPPED corner"),
                       ("4_gauss", "Gaussian curvature of the rolling corner"),
                       ("5_gauss_shipped",
                        "Gaussian curvature of the SHIPPED corner")):
        print("    %-46s %s" % (label, rows[0].get("paths", {}).get(key)))


def main(out_dir=None):
    out_dir = out_dir or OUT_DIR
    os.makedirs(out_dir, exist_ok=True)
    sdoc, sstrips, shipped = build_shipped()
    rdoc, rstrips, corner = build_rolling("rollingdef_roll", LEADER)
    rdoc2, rstrips2, corner2 = build_rolling("rollingdef_roll50", OTHER_LEADER)

    def members_of(doc, prefix):
        member = doc.getObject(prefix + "Member")
        fill = doc.getObject(prefix + "MemberFill")
        return member, fill

    rows = []
    cases = (("shipped corner (fallback)", sdoc, sstrips, shipped),
             ("default (rolling), leader %.2f" % LEADER, rdoc, rstrips, corner),
             ("default (rolling), leader %.2f" % OTHER_LEADER, rdoc2, rstrips2,
              corner2))
    for label, doc_, strips, c in cases:
        s = spread_report(c)
        _obj, _values, stats = curvature_map(doc_, c, "gauss", N_CELLS)
        member, fill = members_of(doc_, "Roll" if "rolling" in label
                                   else "Shipped")
        row = {"label": label, "k_max": s["k_max"], "k_min": s["k_min"],
               "ratio": s["ratio"], "saddle_cells": stats["saddle_cells"],
               "cells": stats["cells"],
               "saddle_fraction": stats["saddle_fraction"],
               "near_ratio": (s["near_ratio_min"], s["near_ratio_max"]),
               "cuts": cut_residual(c, strips),
               "seams": seam_gaps(c, strips),
               "member": member_report(c, member, fill)}
        rows.append(row)

    rec = render(rdoc, corner, *members_of(rdoc, "Roll"),
                 sdoc, shipped, {})
    for r in rows:
        r["paths"] = rec.get("paths", {})
    rows[0]["stats"] = rec.get("stats", {})

    try:
        from Tests.continuity_calibration import error_floor
        floor = error_floor()
    except Exception:
        floor = None
    fallback = fallback_identity()
    print_report(rows, floor, fallback)
    for name in ("rollingdef_shipped", "rollingdef_roll", "rollingdef_roll50",
                 "rollingdef_fallback1", "rollingdef_fallback2"):
        if name in FreeCAD.listDocuments():
            FreeCAD.closeDocument(name)
    return {"rows": rows, "out_dir": out_dir}


if __name__ == "__main__":
    main()
