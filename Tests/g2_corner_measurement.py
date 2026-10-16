"""
Tests/g2_corner_measurement.py -- Phase A measurement for ticket #91.

Feeds the REAL 4-patch subgrid junction (Tests/corner_model.py) to the
Silk-native N-star corner (ArachNURBS.ControlGridNStar66_NSub +
CubicNStarSurface_NStar66) and measures, with Tests/g2_oracle.py, the
continuity across every wedge seam and across the boundary to each
surrounding patch.  Also measures the existing CornerBlend baseline and
probes the N-star's degenerate-centre behaviour.

MEASUREMENT ONLY.  Nothing in this module is a production object; it builds
throwaway carriers in a scratch document and removes them again.

Rerun (live GUI, XML-RPC 127.0.0.1:9875 -- see Tests/run_all.py for the
connection mechanics):

    import sys; sys.path.insert(0, "<Mod>/Silk")
    import Tests.g2_corner_measurement as m
    m.main()

or from a shell inside FreeCAD:

    freecad Tests/g2_corner_measurement.py

The result of the Phase A run is recorded in the ticket #91 report; the
numbers this module prints are the evidence.

--------------------------------------------------------------------------
The N-star feed (why the orientation is what it is)
--------------------------------------------------------------------------
`ControlGridNStar66_NSub` takes a cyclic list of N 6x6 subgrids ("wedges").
Each wedge is a quadrant: local (0,0) is the outer corner, local (1,1) is
the star centre, the u=0 and v=0 edges are the outer boundary, and the
u=1 and v=1 edges are the two radial seams.  Its seam loop pairs
`wedge[i].u1` with `wedge[i+1].v1` (StarRow2_2Sub writes Sub0[17] and
Sub1[32] to the same point), so the feed must be ordered and oriented so
that each wedge's u1 edge is exactly the next wedge's v1 edge.

At the corner model's central junction C the four shared radial edges
(E_s12/E_s13/E_s24/E_s34) are sharp ridges of the raw patch surfaces.  The
adjacency cycle of the four corner cells (by shared radial edge) is
SW-NW-NE-SE; traversing it and assigning each wedge's u1 to the edge it
shares with its successor fixes the star frame:

    wedge      patch       transform on the raw corner cell
    ----       -----       --------------------------------
    0 (SW)     Patch44     transpose
    1 (NW)     Patch002     --
    2 (NE)     Patch003     reverse U, then transpose
    3 (SE)     Patch001     reverse U

("reverse U" puts C at local (1,1); "transpose" swaps the u1/v1 radial
seams so that the seam loop pairs the coincident edges.)  With that feed
the wedge seams are exactly C0 (position gap 0.000); every other ordering
or orientation leaves millimetre-scale position gaps, which is how the
convention is confirmed.
"""

import math

import FreeCAD
import Part
from FreeCAD import Base

from Tests import g2_oracle as G
import Tests.silk_nurbs as SN
import Tests.continuity_analytic as CA

# Manual-only: not discovered by Tests/suite.py (filename is not test_*.py).
# Tests/test_continuity_instrument.py asserts this marker and `main`'s
# reachability, so a rename or a syntax break is caught without running the
# measurement.  See Tests/g2_demo_corner.py for the same convention.
MANUAL = True

# star-frame geometry of the corner-model junction (see module docstring)
CELL = {"Patch44": 3, "Patch002": 3, "Patch003": 1, "Patch001": 1}
TRANSFORMS = {"Patch44": ["T"], "Patch002": [], "Patch003": ["U", "T"],
              "Patch001": ["U"]}
ORDER = ["Patch44", "Patch002", "Patch003", "Patch001"]
# raw corner-cell parameter range in its own patch: (U0, dU, V0, dV)
RAW_RANGE = {"Patch44": (0.9, 0.1, 0.9, 0.1),
             "Patch002": (0.9, 0.1, 0.9, 0.1),
             "Patch003": (0.0, 0.1, 0.9, 0.1),
             "Patch001": (0.0, 0.1, 0.9, 0.1)}


# ---------------------------------------------------------------------------
# small surface builders (all keep the [0,1]x[0,1] domain)
# ---------------------------------------------------------------------------

def _bezier44(poles4):
    s = Part.BSplineSurface()
    s.increaseDegree(3, 3)
    for knot, mult in [(0.0, 4), (1.0, 4)]:
        s.insertUKnot(knot, mult, 1e-7)
        s.insertVKnot(knot, mult, 1e-7)
    for u in range(4):
        for v in range(4):
            s.setPole(u + 1, v + 1, poles4[u][v], 1.0)
    return s


def _surf66(poles6):
    """Build the 6x6 cubic NURBS surface with interior knots 1/3, 2/3
    (identical to ArachNURBS.NURBS_Cubic_66_surf).  poles6 is [u][v]."""
    s = Part.BSplineSurface()
    s.increaseDegree(3, 3)
    for knot, mult in [(0.0, 4), (1.0 / 3, 1), (2.0 / 3, 1), (1.0, 4)]:
        s.insertUKnot(knot, mult, 1e-9)
        s.insertVKnot(knot, mult, 1e-9)
    for v in range(6):
        for u in range(6):
            s.setPole(u + 1, v + 1, poles6[u][v], 1.0)
    return s


def _upsample66(poles4):
    """4x4 bicubic Bezier -> exact 6x6 cubic control net (knots 1/3, 2/3)."""
    s = _bezier44(poles4)
    s.insertUKnot(1.0 / 3.0, 1, 1e-9)
    s.insertUKnot(2.0 / 3.0, 1, 1e-9)
    s.insertVKnot(1.0 / 3.0, 1, 1e-9)
    s.insertVKnot(2.0 / 3.0, 1, 1e-9)
    p = s.getPoles()
    return [[p[u][v] for v in range(6)] for u in range(6)]


def _surf64(poles24):
    s = Part.BSplineSurface()
    s.increaseDegree(3, 3)
    for knot, mult in [(0.0, 4), (1.0 / 3, 1), (2.0 / 3, 1), (1.0, 4)]:
        s.insertUKnot(knot, mult, 1e-9)
    for knot, mult in [(0.0, 4), (1.0, 4)]:
        s.insertVKnot(knot, mult, 1e-9)
    for v in range(4):
        for u in range(6):
            s.setPole(u + 1, v + 1, poles24[v * 6 + u], 1.0)
    return s


def _carrier(doc, name, poles_flat, weights=None):
    obj = doc.addObject("Part::FeaturePython", name)
    obj.addProperty("App::PropertyVectorList", "Poles", "Internal", "p").Poles
    obj.addProperty("App::PropertyFloatList", "Weights", "Internal", "w").Weights
    obj.Poles = poles_flat
    obj.Weights = weights or [1.0] * 36
    return obj


# ---------------------------------------------------------------------------
# corner-cell extraction, oriented into the star frame
# ---------------------------------------------------------------------------

def star_cell_uv(doc, patch_name):
    """The patch's junction corner cell (4x4), oriented to the star frame."""
    patch = doc.getObject(patch_name)
    raw = list(patch.Proxy._subgrids[CELL[patch_name]])
    poles = [[raw[4 * u + v] for v in range(4)] for u in range(4)]
    if "U" in TRANSFORMS[patch_name]:
        poles = [poles[3 - u] for u in range(4)]
    if "T" in TRANSFORMS[patch_name]:
        poles = [[poles[v][u] for v in range(4)] for u in range(4)]
    return poles


def star_to_patch(patch_name, su, sv):
    """Star-frame local (su, sv) -> the patch's own (U, V) parameters."""
    ru, rv = su, sv
    for tr in reversed(TRANSFORMS[patch_name]):
        if tr == "U":
            ru = 1.0 - ru
        elif tr == "T":
            ru, rv = rv, ru
    u0, du, v0, dv = RAW_RANGE[patch_name]
    return (u0 + du * ru, v0 + dv * rv)


def star_flat(poles6):
    """[u][v] -> the star's flat pole order (v*6 + u), as NURBS_Cubic_66_surf reads it."""
    return [poles6[u][v] for v in range(6) for u in range(6)]


# ---------------------------------------------------------------------------
# build + measure
# ---------------------------------------------------------------------------

def build_nstar(doc, prefix="_g2m_", remove_after=True):
    """Build ControlGridNStar66_NSub + CubicNStarSurface_NStar66 from the
    corner model's four junction cells.

    Returns (grid, nsurf, input_surfaces).  When remove_after is True the
    scratch objects are deleted from `doc` before returning.
    """
    import ArachNURBS

    for o in list(doc.Objects):
        if o.Name.startswith(prefix):
            doc.removeObject(o.Name)

    input66 = []
    carriers = []
    for i, name in enumerate(ORDER):
        p6 = _upsample66(star_cell_uv(doc, name))
        input66.append(p6)
        carriers.append(_carrier(doc, prefix + "sub_%d" % i, star_flat(p6)))

    grid = doc.addObject("Part::FeaturePython", prefix + "star")
    ArachNURBS.ControlGridNStar66_NSub(grid, carriers)
    nsurf = doc.addObject("Part::FeaturePython", prefix + "nsurf")
    ArachNURBS.CubicNStarSurface_NStar66(nsurf, grid)
    doc.recompute()

    inputs = [_surf66(p) for p in input66]
    if remove_after:
        for o in list(doc.Objects):
            if o.Name.startswith(prefix):
                doc.removeObject(o.Name)
    return grid, nsurf, inputs


def measure_nstar(doc, n=21):
    """Measure N-star seams + boundary; print and return the report."""
    grid, nsurf, inputs = build_nstar(doc, remove_after=False)
    report = {"seams": [], "boundary": [], "built": False}
    try:
        NS = list(nsurf.NSurf)
        report["built"] = bool(NS)
        print("N-star: N=%s surfaces=%d" % (grid.N, len(NS)))

        labels = ["W radial (44|002)", "N radial (002|003)",
                  "E radial (003|001)", "S radial (001|044)"]
        print("-- wedge seams: input cells vs star output --")
        for i in range(4):
            j = (i + 1) % 4
            sa, aa = (lambda t: (1.0, t)), "u"
            sb, ab = (lambda t: (t, 1.0)), "v"
            rin = G.measure_seam(inputs[i], sa, aa, inputs[j], sb, ab, n=n)
            rst = G.measure_seam(NS[i], sa, aa, NS[j], sb, ab, n=n)
            report["seams"].append((labels[i], rin, rst))
            print("  %-20s INPUT g1=%.2f deg | STAR c0=%.2e g1=%.2f deg "
                  "k_gap=%.3e -> %s"
                  % (labels[i], rin["g1_deg"], rst["c0"], rst["g1_deg"],
                     rst["k_gap"], G.classify(rst)))

        print("-- boundary: star edge vs surrounding patch --")
        for i, name in enumerate(ORDER):
            base = doc.getObject(name).Proxy._base_surface
            for edge, seam_star, acc in (
                    ("u0", lambda t: (0.0, t), "u"),
                    ("v0", lambda t: (t, 0.0), "v")):
                if edge == "u0":
                    sp = (lambda nm: lambda t: star_to_patch(nm, 0.0, t))(name)
                else:
                    sp = (lambda nm: lambda t: star_to_patch(nm, t, 0.0))(name)
                u0, v0 = sp(0.0)
                u1, v1 = sp(1.0)
                ap = "v" if abs(u1 - u0) > abs(v1 - v0) else "u"
                r = G.measure_seam(NS[i], seam_star, acc, base, sp, ap, n=n)
                report["boundary"].append((name, edge, r))
                print("  %s.%-3s c0=%.2e g1=%.4f deg k_gap=%.3e -> %s"
                      % (name, edge, r["c0"], r["g1_deg"], r["k_gap"],
                         G.classify(r)))

        centre = NS[0].value(1.0, 1.0)
        junction = FreeCAD.Vector(50.0, 50.0, 52.0)
        report["centre"] = (centre, (centre - junction).Length)
        print("-- centre -- star centre=%s  |centre - C|=%.4f mm"
              % (tuple(round(c, 4) for c in centre),
                 (centre - junction).Length))
    finally:
        for o in list(doc.Objects):
            if o.Name.startswith("_g2m_"):
                doc.removeObject(o.Name)
    return report


def _analytic_seam(cb_poles, strip_poles, cedge, edge, rev, n=21):
    """Exact control-net reading of one CornerBlend/strip boundary pair.

    The CornerBlend is a 6x6 `NURBS_Cubic_66_surf` and each strip a 6x4
    `NURBS_Cubic_64_surf`; both carry unit weights in this fixture, and the
    analytic layer is the arbiter for the sampled oracle.  The control net
    is the source of truth, so the C0 slot is exact up to rounding.
    """
    cb_surf = SN.NurbsSurface.from_flat(list(cb_poles), [1.0] * 36, 6, 6,
                                        SN.KNOTS_6, SN.KNOTS_6)
    st_surf = SN.NurbsSurface.from_flat(list(strip_poles), [1.0] * 24, 6, 4,
                                        SN.KNOTS_6, SN.KNOTS_4)
    return CA.measure_edges(cb_surf, cedge, rev, st_surf, edge, False, n=n)


def measure_corner_blend(doc, n=21):
    """Continuity of the existing CornerBlend boundary against the ring
    blends it is built from (its neighbours); each strip is itself C0/G1 to
    the patches, so this is the corner's boundary continuity.

    Reports both instruments: the sampled curvature oracle (`g2_oracle`,
    the instrument the yellow map number was attributed to) and the exact
    control-net arbiter (`continuity_analytic`).  c0_net is the
    combinatorial C0 gap -- the control net's own answer, no evaluation.
    """
    cb = doc.getObject("CornerBlend")
    if cb is None:
        print("no CornerBlend in this document")
        return []
    cb_surf = _surf66([[cb.Poles[v * 6 + u] for v in range(6)]
                       for u in range(6)])
    out = []
    print("-- CornerBlend boundary vs ring strips --")
    for s in cb.Strips:
        strip_surf = _surf64(list(s.Poles))
        for li, edge in ((0, "v0"), (3, "v1")):
            srow = [s.Poles[li * 6 + k] for k in range(6)]
            for cedge, idxs in (("u0", [0, 6, 12, 18, 24, 30]),
                                ("u1", [5, 11, 17, 23, 29, 35]),
                                ("v0", [0, 1, 2, 3, 4, 5]),
                                ("v1", [30, 31, 32, 33, 34, 35])):
                cbrow = [cb.Poles[i] for i in idxs]
                # A true boundary pair matches along the WHOLE row, forward
                # or reversed.  Testing only the two endpoints (the old
                # heuristic) matched unrelated edges whose ends happened to
                # be shared, producing eight spurious 10-15 mm "seams".
                rev = None
                for cand in (False, True):
                    ref = list(reversed(srow)) if cand else srow
                    if all((cbrow[k] - ref[k]).Length < 1e-6
                           for k in range(6)):
                        rev = cand
                        break
                if rev is None:
                    continue
                scb, acb = G.edge_seam(cb_surf, cedge, reverse=rev)
                sst, ast = G.edge_seam(strip_surf, edge)
                r = G.measure_seam(cb_surf, scb, acb, strip_surf, sst, ast, n=n)
                an = _analytic_seam(cb.Poles, s.Poles, cedge, edge, rev, n=n)
                out.append((s.Name, cedge, edge, r, an))
                print("  CB.%-3s vs %s.%-2s c0=%.2e g1=%.4f deg k_gap=%.3e "
                      "| net c0=%.2e g1=%.4f deg k_gap=%.3e -> %s"
                      % (cedge, s.Name, edge, r["c0"], r["g1_deg"],
                         r["k_gap"], an["c0"], an["g1_deg"], an["k_gap"],
                         G.classify(r)))
    return out


def degenerate_check(doc):
    """Feed the N-star degenerate wedges and report build/crash behaviour."""
    import ArachNURBS

    def run(tag, cells):
        for o in list(doc.Objects):
            if o.Name.startswith("_g2d_"):
                doc.removeObject(o.Name)
        carriers = [_carrier(doc, "_g2d_sub_%d" % i, star_flat(_upsample66(c)))
                    for i, c in enumerate(cells)]
        grid = doc.addObject("Part::FeaturePython", "_g2d_star")
        ArachNURBS.ControlGridNStar66_NSub(grid, carriers)
        try:
            grid.Proxy.execute(grid)
            state, nsurf = "OK", "-"
            print("[%s] execute OK, N=%s" % (tag, grid.N))
        except Exception as exc:
            state, nsurf = type(exc).__name__, "-"
            print("[%s] execute raised %s: %s" % (tag, type(exc).__name__, exc))
        for o in list(doc.Objects):
            if o.Name.startswith("_g2d_"):
                doc.removeObject(o.Name)
        return state

    real = [star_cell_uv(doc, nm) for nm in ORDER]
    flat = [[[Base.Vector(p.x, p.y, 0.0) for p in row]
             for row in star_cell_uv(doc, nm)] for nm in ORDER]
    same = [star_cell_uv(doc, "Patch44")] * 4
    print("-- degenerate input --")
    run("real (control)", real)
    run("flat but distinct", flat)
    run("four identical wedges", same)


# raw corner-cell local (ru, rv) -> physical position of the junction quadrant
# (used only by the compatible-feed control below)
RAW_PHYSICAL = {
    "Patch44": lambda ru, rv: (45.0 + 5.0 * ru, 45.0 + 5.0 * rv),
    "Patch002": lambda ru, rv: (45.0 + 5.0 * ru, 55.0 - 5.0 * rv),
    "Patch003": lambda ru, rv: (50.0 + 5.0 * ru, 55.0 - 5.0 * rv),
    "Patch001": lambda ru, rv: (50.0 + 5.0 * ru, 45.0 + 5.0 * rv),
}


def _raw_quadrant(patch_name, f):
    """4x4 bicubic Bezier grid of f over the raw corner cell."""
    m = RAW_PHYSICAL[patch_name]
    return [[f(*m(i / 3.0, j / 3.0)) for j in range(4)] for i in range(4)]


def compatible_feed_check(doc, n=21):
    """Control: feed the star geometrically COMPATIBLE wedges (a single
    tilted plane split into four quadrants -> the seams are exactly flat).
    If the star's seams come out G2 here, its seam machinery works and the
    real-junction fold is a property of the raw patch-cell feed, not a
    fundamental inability to join surfaces."""
    import ArachNURBS

    for o in list(doc.Objects):
        if o.Name.startswith("_g2c_"):
            doc.removeObject(o.Name)
    plane = lambda x, y: Base.Vector(x, y, 0.5 * (x - 50.0) + 0.3 * (y - 50.0))
    globals_ = []
    carriers = []
    for i, name in enumerate(ORDER):
        raw = _raw_quadrant(name, plane)
        if "U" in TRANSFORMS[name]:
            raw = [raw[3 - u] for u in range(4)]
        if "T" in TRANSFORMS[name]:
            raw = [[raw[v][u] for v in range(4)] for u in range(4)]
        p6 = _upsample66(raw)
        globals_.append(p6)
        carriers.append(_carrier(doc, "_g2c_sub_%d" % i, star_flat(p6)))
    grid = doc.addObject("Part::FeaturePython", "_g2c_star")
    ArachNURBS.ControlGridNStar66_NSub(grid, carriers)
    nsurf = doc.addObject("Part::FeaturePython", "_g2c_nsurf")
    ArachNURBS.CubicNStarSurface_NStar66(nsurf, grid)
    doc.recompute()
    print("-- compatible feed control (single tilted plane, flat seams) --")
    for i in range(4):
        j = (i + 1) % 4
        r = G.measure_seam(nsurf.NSurf[i], lambda t: (1.0, t), "u",
                           nsurf.NSurf[j], lambda t: (t, 1.0), "v", n=n)
        print("  seam %d|%d  c0=%.2e g1=%.4f deg k_gap=%.3e -> %s"
              % (i, j, r["c0"], r["g1_deg"], r["k_gap"], G.classify(r)))
    for o in list(doc.Objects):
        if o.Name.startswith("_g2c_"):
            doc.removeObject(o.Name)


# ---------------------------------------------------------------------------

def main():
    import Tests.corner_model as corner_model
    name = "_g2_measurement"
    if name in FreeCAD.listDocuments():
        FreeCAD.closeDocument(name)
    doc = FreeCAD.newDocument(name)
    try:
        corner_model.build_corner_model_with_blend(doc)
        measure_nstar(doc)
        measure_corner_blend(doc)
        degenerate_check(doc)
        compatible_feed_check(doc)
    finally:
        FreeCAD.closeDocument(name)


if __name__ == "__main__":
    main()
