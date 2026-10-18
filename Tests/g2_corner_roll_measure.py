"""
MANUAL MEASUREMENT -- does the shipped 3-valent corner ROLL? (ticket #118).

Part of #1 (map). Owner, 2026-10-18: *"d2: yes"*. The video's author makes a
*rolling* fillet by setting the setbacks ASYMMETRICALLY (0.25 in one
direction, 0.125 in the other). The claim this module tests, stated so it can
fail:

    Silk's 3-valent corner's fillet character changes when the band widths
    are set asymmetrically -- one direction large, one small -- rather than
    averaging into one uniform round.

If our corner is a compromise, the asymmetry will not reach the geometry and
the spread will not move.

WHAT IS MEASURED, per config (see CONFIGS)

  1. per-seam `k_gap` -- the built corner vs each neighbouring strip, on the
     exact control net (`Tests/continuity_analytic`), with the calibrated
     floor beside it.  Two of the three strip seams terminate in the
     triangular member's COLLAPSED row (all six poles at the ring's shared
     corner), so their boundary normal is degenerate at the apex-side
     station: `g1_deg` reads 90 deg there by construction (the same reading
     `Tests/g2_edge_blend_probe.py` records for the demo's hard-corner
     members) and only their `k_gap` is a continuity number.  The third seam
     does not touch the collapse and reads a genuine g1 ~ 0.
  2. the corner surface's OWN curvature spread at and near the junction: a
     directional normal-curvature sample on the stored 6x6 net, reported as
     `k_max`, `k_min` and their ratio.  A rolling corner has a large spread;
     a mushed one a small spread.

FLOOR.  Every number is reported next to the calibrated floor from
`Tests/continuity_calibration.error_floor`.  `k_gap` (and the curvature
formula behind it) is geometry only above that floor, so a spread difference
below it proves nothing.

THE FIXTURE is `Tests/cube_corner_model.py` -- three exact planar square
patches meeting like a cube corner, no curvature of its own -- never Demo 01.

CONFIGS.  The setback is the band width Silk reads off each patch's own band
edge; a seam's two setbacks are the two patches it joins (the panel's
`Band A` / `Band B` editors).  `symmetric` leaves the fixture's own defaults
(0.1 / 0.1 on every seam).  `asymmetric` sets one patch of every seam to 0.25
and the other to 0.125 -- the video's two numbers -- in the rotational sense
(each ring patch carries one 0.25 and one 0.125).  `asymmetric_axis` is the
other reading of "one direction large, one small" (every patch U = 0.25,
V = 0.125), kept as a robustness variant.

MANUAL-ONLY: the file name is not `test_*.py`, so `Tests/suite.py` does not
discover it.  `Tests/test_continuity_instrument.py` asserts this module
imports, exposes `main`, and carries `MANUAL`; nothing else in the suite runs
it.  Nothing here is a production object or a fix.

Run (live GUI over XML-RPC, or in a GUI FreeCAD):

    import Tests.g2_corner_roll_measure as m; m.main()
"""

import math

import FreeCAD
import Part
from FreeCAD import Base

import Tests.cube_corner_model as ccm
import Tests.continuity_analytic as CA
import Tests.continuity_calibration as CAL
import Tests.g2_oracle as G
import Tests.silk_nurbs as SN
import SilkBlend
import SilkCorner
import SilkMachinery as SM
from SilkWorkflowOps import create_corner_blend

MANUAL = True

STRIP_NAMES = ("B_AB", "B_BC", "B_CA")

# The four boundary sides of the corner's 6x6 grid, as flat pole indices
# (the same sides `Tests/test_cube_corner_3valent.py` CB_SIDES reads).
CB_SIDES = {
    "u0": [0, 6, 12, 18, 24, 30],
    "u1": [5, 11, 17, 23, 29, 35],
    "v0": [0, 1, 2, 3, 4, 5],
    "v1": [30, 31, 32, 33, 34, 35],
}

# The video's two setback values.  LARGE is the wide band, SMALL the narrow
# one; the ratio 2:1 is the asymmetry under test.
LARGE, SMALL = 0.25, 0.125

# config name -> {patch name: (USplit1, VSplit1)}.  Only the origin-end
# (Split1) band edges are touched; Split2 stays the "no band" sentinel 1.0.
CONFIGS = {
    # the fixture's own defaults: every seam's two bands equal at 0.1
    "symmetric": {"PatchA": (0.1, 0.1),
                  "PatchB": (0.1, 0.1),
                  "PatchC": (0.1, 0.1)},
    # the video's numbers, rotational: every seam is LARGE/SMALL and every
    # ring patch carries one LARGE and one SMALL
    "asymmetric": {"PatchA": (SMALL, LARGE),
                   "PatchB": (LARGE, SMALL),
                   "PatchC": (SMALL, LARGE)},
    # the other reading of "one direction large, one small": one param axis
    # LARGE, the other SMALL, on every patch
    "asymmetric_axis": {"PatchA": (LARGE, SMALL),
                        "PatchB": (LARGE, SMALL),
                        "PatchC": (LARGE, SMALL)},
}

# direction samples per junction point (2 deg resolution over [0, pi))
N_DIR = 90


# ---------------------------------------------------------------------------
# exact control-net curvature
# ---------------------------------------------------------------------------

def _unit(vec):
    length = vec.Length
    if length < 1e-15:
        return Base.Vector(0, 0, 0)
    return Base.Vector(vec.x / length, vec.y / length, vec.z / length)


def normal_curvature(net, u, v, direction):
    """Exact normal curvature of `net` at (u, v) in unit 3D direction `d`.

    II(d, d) with the second fundamental form read from the exact control net
    (the same formula `Tests/g2_corner_fill_continuity._kappa_oblique` uses):
    d = a*Pu + b*Pv, kappa = e a^2 + 2 f a b + g b^2 with e/f/g the second
    fundamental form coefficients.  Rational surfaces are handled because the
    net carries the weights.
    """
    _P, Pu, Pv, Puu, Puv, Pvv = net.ders(u, v, order=2)
    n = _unit(Pu.cross(Pv))
    E, G, F = Pu.dot(Pu), Pv.dot(Pv), Pu.dot(Pv)
    det = E * G - F * F
    if abs(det) < 1e-18:
        return 0.0
    du, dv = direction.dot(Pu), direction.dot(Pv)
    a = (du * G - dv * F) / det
    b = (E * dv - F * du) / det
    e, f, g = Puu.dot(n), Puv.dot(n), Pvv.dot(n)
    return e * a * a + 2.0 * f * a * b + g * b * b


def principal_curvatures(net, u, v):
    """(k_max, k_min) of `net` at (u, v) from the shape operator, exact.

    The two roots of the normal-curvature quadratic; the directional sample
    in `spread` must reproduce them.
    """
    _P, Pu, Pv, Puu, Puv, Pvv = net.ders(u, v, order=2)
    n = _unit(Pu.cross(Pv))
    E, G, F = Pu.dot(Pu), Pv.dot(Pv), Pu.dot(Pv)
    det = E * G - F * F
    if abs(det) < 1e-18:
        return 0.0, 0.0
    L, M, N2 = Puu.dot(n), Puv.dot(n), Pvv.dot(n)
    mean = (E * N2 - 2.0 * F * M + G * L) / (2.0 * det)
    gauss = (L * N2 - M * M) / det
    disc = mean * mean - gauss
    root = math.sqrt(disc) if disc > 0.0 else 0.0
    return mean + root, mean - root


def spread(net, u, v, n_dir=N_DIR):
    """Directional normal-curvature sample: (k_max, k_min, ratio).

    Walks `n_dir` directions of the tangent plane at (u, v), reads the exact
    normal curvature in each, and returns the extremes and their ratio.  The
    extremes are the view of the principal curvatures the issue asks for
    ("many directions from the same point").
    """
    P, Pu, Pv, *_ = net.ders(u, v, order=1)
    ks = []
    for i in range(n_dir):
        theta = math.pi * i / n_dir
        d = _unit(Pu * math.cos(theta) + Pv * math.sin(theta))
        ks.append(normal_curvature(net, u, v, d))
    kmax, kmin = max(ks), min(ks)
    ratio = abs(kmax) / abs(kmin) if abs(kmin) > 1e-12 else float("inf")
    return kmax, kmin, ratio


# ---------------------------------------------------------------------------
# fixture + corner build
# ---------------------------------------------------------------------------

def _part_surface(flat, weights, nv):
    """A `Part.BSplineSurface` from a flat v-major net (index = v*6 + u)."""
    s = Part.BSplineSurface()
    s.increaseDegree(3, 3)
    for knot, mult in ((0.0, 4), (1.0 / 3.0, 1), (2.0 / 3.0, 1), (1.0, 4)):
        s.insertUKnot(knot, mult, 1e-7)
    v_knots = ((0.0, 4), (1.0 / 3.0, 1), (2.0 / 3.0, 1), (1.0, 4)) \
        if nv == 6 else ((0.0, 4), (1.0, 4))
    for knot, mult in v_knots:
        s.insertVKnot(knot, mult, 1e-7)
    for v in range(nv):
        for u in range(6):
            s.setPole(u + 1, v + 1, flat[v * 6 + u], weights[v * 6 + u])
    return s


def build_config(doc, splits):
    """Build the cube-corner fixture in `doc` with `splits`, then the corner.

    The splits are written on the patches FIRST, the document recomputes
    (patches -> auto-updated strips), and the corner is built from the strips
    as rebuilt -- so the corner it assembles is the one the widths describe.
    Returns (strips, corner).
    """
    ccm.build_cube_corner_model(doc)
    for patch_name, (usplit1, vsplit1) in splits.items():
        p = doc.getObject(patch_name)
        p.USplit1 = usplit1
        p.VSplit1 = vsplit1
    doc.recompute()
    strips = [doc.getObject(n) for n in STRIP_NAMES]
    corner = create_corner_blend(*strips)
    return strips, corner


def seam_bands(strip):
    """The two band widths of `strip`'s seam, as (patch, property, value)."""
    out = []
    for p in (strip.PatchA, strip.PatchB):
        side = SilkBlend._side_on(strip, p)
        prop, _end = SilkBlend._band_split_of(side)
        out.append((p.Name, prop, getattr(p, prop)))
    return out


def match_side(cb_poles, strip_poles):
    """(cedge, row, rev) naming the corner side that is `strip`'s junction
    row, matched along the WHOLE row (either direction), or None."""
    for row in (0, 3):
        srow = [strip_poles[row * 6 + k] for k in range(6)]
        for cedge, idxs in CB_SIDES.items():
            cbrow = [cb_poles[i] for i in idxs]
            for rev in (False, True):
                ref = list(reversed(srow)) if rev else srow
                if all((cbrow[k] - ref[k]).Length < 1e-6 for k in range(6)):
                    return cedge, row, rev
    return None


def per_seam(cb_part, cb_net, strip, n=41):
    """Corner vs one strip: sampled + exact continuity on the matched side."""
    m = match_side(_flat(cb_net), list(strip.Poles))
    if m is None:
        return None
    cedge, row, rev = m
    edge_st = "v0" if row == 0 else "v1"
    s_flat = list(strip.Poles)
    s_w = list(strip.Weights) or [1.0] * 24
    st_net = SN.NurbsSurface.from_flat(s_flat, s_w, 6, 4,
                                       SN.KNOTS_6, SN.KNOTS_4)
    st_part = _part_surface(s_flat, s_w, 4)
    exact = CA.measure_edges(cb_net, cedge, rev, st_net, edge_st, False, n=n)
    scb, acb = G.edge_seam(cb_part, cedge, reverse=rev)
    sst, ast = G.edge_seam(st_part, edge_st)
    sampled = G.measure_seam(cb_part, scb, acb, st_part, sst, ast, n=n)
    c0_net, _ = SN.c0_controlnet(cb_net, cedge, st_net, edge_st, reverse=rev)
    return {"strip": strip.Name, "corner_edge": cedge, "row": row,
            "reversed": rev, "edge_strip": edge_st,
            "c0_controlnet": c0_net,
            "exact": exact, "sampled": sampled}


def _flat(net):
    """Re-flatten a `NurbsSurface`'s poles to the 36-pole v-major order."""
    return [net.poles[u][v] for v in range(net.nv) for u in range(net.nu)]


def junction_probe(net):
    """Spread at the cap centre and over a small neighbourhood of it, plus
    the point closest to the cube vertex (the junction foot)."""
    # the foot: the corner sample nearest the shared origin (0, 0, 0)
    foot = (1e18, 0.5, 0.5)
    for i in range(81):
        for j in range(81):
            u, v = i / 80.0, j / 80.0
            d = net.value(u, v).Length
            if d < foot[0]:
                foot = (d, u, v)
    centre = spread(net, 0.5, 0.5)
    # near-junction range: the 5x5 uv grid over [0.4, 0.6]
    ratios = []
    for i in range(5):
        for j in range(5):
            r = spread(net, 0.4 + 0.05 * i, 0.4 + 0.05 * j)[2]
            ratios.append(r)
    return {"centre": centre, "centre_k1k2": principal_curvatures(net, 0.5, 0.5),
            "foot": (foot[0], foot[1], foot[2], spread(net, foot[1], foot[2])),
            "near_ratio_min": min(ratios), "near_ratio_max": max(ratios)}


def measure_config(name, splits):
    """Build one config in its own scratch document and measure it."""
    doc_name = "roll_" + name
    if doc_name in FreeCAD.listDocuments():
        FreeCAD.closeDocument(doc_name)      # only our own scratch doc
    doc = FreeCAD.newDocument(doc_name)
    strips, corner = build_config(doc, splits)
    out = {"name": name, "splits": splits, "bands": [], "seams": [],
           "collapsed_side": None, "junction": None, "corner": corner}
    if corner is None:
        return out
    for s in strips:
        out["bands"].append((s.Name, seam_bands(s)))
    flat = list(corner.Poles)
    weights = list(corner.Weights) or [1.0] * 36
    out["collapsed_side"] = SM._collapsed_side(flat, SilkCorner.CORNER_TOL)
    cb_part = _part_surface(flat, weights, 6)
    cb_net = SN.NurbsSurface.from_flat(flat, weights, 6, 6,
                                       SN.KNOTS_6, SN.KNOTS_6)
    for s in strips:
        r = per_seam(cb_part, cb_net, s)
        if r is not None:
            out["seams"].append(r)
    out["junction"] = junction_probe(cb_net)
    return out


# ---------------------------------------------------------------------------
# report
# ---------------------------------------------------------------------------

def _fmt(x):
    return "n/a" if x is None else "%.6e" % x


def floor_report(n=41):
    fl = CAL.error_floor(n=n)
    return {k: {"sampled": fl[k]["sampled"], "analytic": fl[k]["analytic"]}
            for k in ("c0", "g1_deg", "k_gap", "twist_gap")}


def print_floor(floor):
    print("CALIBRATED FLOOR (Tests/continuity_calibration.error_floor, n=41)")
    print("  the smallest number either instrument can honestly report on a")
    print("  smooth curved seam whose truth is 0 (nothing below it is a")
    print("  measurement):")
    for k in ("c0", "g1_deg", "k_gap", "twist_gap"):
        print("    %-10s sampled %s | analytic %s /mm" %
              (k, _fmt(floor[k]["sampled"]), _fmt(floor[k]["analytic"])))
    print()


def print_config(res, floor):
    print("=== %s ===" % res["name"])
    print("  splits (USplit1, VSplit1): %s" % res["splits"])
    if res["corner"] is None:
        print("  CORNER BUILD REFUSED -- nothing to measure")
        print()
        return
    print("  seam bands (patch, property, width):")
    for strip_name, bands in res["bands"]:
        print("    %-5s %s" % (strip_name, bands))
    print("  corner 6x6: 36 poles, collapsed side %s" % res["collapsed_side"])
    print()
    print("  per-seam k_gap (corner vs each neighbouring strip):")
    print("    %-5s %-8s %-4s %-10s %-12s %-12s" %
          ("strip", "c-edge", "rev", "c0_control", "exact k_gap",
           "sampled k_gap"))
    for r in res["seams"]:
        print("    %-5s %-8s %-4s %-10s %-12s %-12s   (exact g1 %.4f deg)"
              % (r["strip"], r["corner_edge"], "y" if r["reversed"] else "n",
                 _fmt(r["c0_controlnet"]), _fmt(r["exact"]["k_gap"]),
                 _fmt(r["sampled"]["k_gap"]), r["exact"]["g1_deg"]))
    print("    (the 4th side is the triangular member's COLLAPSED row -- no")
    print("     strip sits on it; its boundary normal is degenerate.)")
    print()
    j = res["junction"]
    kmax, kmin, ratio = j["centre"]
    k1, k2 = j["centre_k1k2"]
    print("  corner's own curvature spread, directional sample on the 6x6 net:")
    print("    at the junction (uv = 0.50, 0.50): k_max %.4f, k_min %.4f, "
          "ratio %.3f /mm" % (kmax, kmin, ratio))
    print("      (shape-operator cross-check: k1 %.4f, k2 %.4f, ratio %.3f)"
          % (k1, k2, abs(k1) / abs(k2) if abs(k2) > 1e-12 else float("inf")))
    fdist, fu, fv, fspread = j["foot"]
    print("    at the junction foot (closest to the cube vertex, %.4f mm "
          "away, uv %.2f/%.2f): k_max %.4f, k_min %.4f, ratio %.3f"
          % (fdist, fu, fv, fspread[0], fspread[1], fspread[2]))
    print("    near the junction (5x5 uv grid over [0.4, 0.6]): ratio "
          "%.3f .. %.3f" % (j["near_ratio_min"], j["near_ratio_max"]))
    print()
    print("  FLOOR beside these: k_gap floor sampled %s / analytic %s /mm;"
          % (_fmt(floor["k_gap"]["sampled"]), _fmt(floor["k_gap"]["analytic"])))
    print("  the curvature values above are ~1 /mm, orders of magnitude "
          "above it.")
    print()


def main(n=41):
    floor = floor_report(n)
    print_floor(floor)
    results = []
    for name, splits in CONFIGS.items():
        results.append(measure_config(name, splits))
    for res in results:
        print_config(res, floor)

    print("READING")
    sym = next(r for r in results if r["name"] == "symmetric")
    asym = next(r for r in results if r["name"] == "asymmetric")
    if sym["junction"] and asym["junction"]:
        rs = sym["junction"]["centre"][2]
        ra = asym["junction"]["centre"][2]
        print("  symmetric ratio %.3f -> asymmetric ratio %.3f (x%.2f)"
              % (rs, ra, ra / rs if rs else float("inf")))
        print("  a spread that MOVES with the asymmetry means the corner "
              "expresses it (it rolls); one that stays put would mean it "
              "mushes.  Compare both against the floor above.")
    for d in list(FreeCAD.listDocuments()):
        if d.startswith("roll_"):
            FreeCAD.closeDocument(d)     # our own scratch documents only
    return {"floor": floor, "configs": results}


if __name__ == "__main__":
    main()
