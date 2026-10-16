"""
The G2 corner solve -- ticket #100, deliverables 3 and 4 (MANUAL).

Question. Silk's 4-patch corner (`SilkMachinery.corner_grid`) reads only the
two rows behind each seam (position + first derivative), then *averages* two
extrapolations.  So it can reach G1 at best, and not exactly.  This module
asks what a corner that is *solved* for G2, rather than averaged, can reach,
and whether the limit is the maths or the neighbours.

It has two feeds:

  synthetic  a 4-strip ring built from ONE known smooth 6x6 Silk surface `T`
             (each strip is the exact outward extension of `T`'s first/last
             control span across the seam).  The exact G2 continuation is
             therefore `T` itself, known by construction -- the known-answer
             calibration: a solve that cannot recover `T` here is broken, not
             a statement about the maths.
  demo       the four ring blends of each junction of the author's reference
             document `Resources/Demo_files/Silk_Demo_01.FCStd`, the same
             neighbours #97 measured the corner against.  Here the neighbours
             are whatever the legacy chain actually produced, so the residual
             linear system measures their MUTUAL COMPATIBILITY (deliverable 3)
             and the solve's k_gap is what our corner COULD reach there
             (deliverable 4).

Measured per seam and per feed:
  current   the shipped construction (averaging `corner_grid`, or the demo's
            own `ControlGrid66_4Sub` output) as it stands;
  solved    the linear least-squares G2 solve of the corner's 36 poles;
  truth     only for the synthetic feed -- `T` itself (must read ~0).

The metric is #97's calibrated instrument: exact control-net c0/g1/k_gap/
twist_gap (`Tests/silk_nurbs.py` + `Tests/continuity_analytic.py`).  `k_gap`
is a single-direction (across-seam) normal-curvature comparison -- necessary,
not sufficient, for full G2; `twist_gap` is reported alongside, with a caveat:
`continuity_analytic.measure_seam` takes its along-tangent from the surface's
natural parameter axis, so on a seam whose correspondence is REVERSED (which
`match_boundaries` freely chooses) the geodesic torsion enters with a sign
flip and `twist_gap` reads ~2|tau| even on a perfectly smooth seam.  `k_gap`
is unaffected (normal curvature does not depend on the along direction).
This module therefore reports `k_gap` as the G2 evidence and prints a
`twist_gap` flag whenever the seam was reversed.

WHY THE RELATIONS ARE THESE.  Let the corner's across-first-span Bezier
control points, walking OUTWARD from the seam, be (b0, b1, b2), and the
neighbour strip's rows, walking outward from the junction, be (V3, V2, V1).
A single smooth cubic through the seam (same parameter scale on both sides)
demands, by Taylor/blossom matching at the junction:

    b0 = V3,   b1 = 2 V3 - V2,   b2 = 4 V3 - 4 V2 + V1.

The shipped `corner_grid` reads only V3 and V2 (position + first derivative),
which is why it reaches G1 and no further; a G2 condition needs V1 too.  With
the corner's B-spline poles this is, per seam station:

    P[boundary]        = V3
    P[one row in]      = 2 V3 - V2
    P[two rows in]     = 6 V3 - 7 V2 + 2 V1

(using b2 = (P[one in] + P[two in]) / 2).  Each seam gives 3 relations x 6
stations = 18 equations; four seams give 72 equations on 36 poles, so the
system is over-determined and generally only least-squares solvable -- exactly
solvable iff the four neighbours agree at the junction.

MANUAL-ONLY (filename is not `test_*.py`).  Never asserts a continuity label;
the numbers are the evidence.  `Tests/test_continuity_instrument.py` asserts
this module imports, exposes `main`, and carries `MANUAL`.

Run (live GUI over XML-RPC, or in a GUI FreeCAD):

    import Tests.g2_corner_solve as m; m.main()
"""

import math
import os

import numpy as np

from FreeCAD import Base

import Tests.silk_nurbs as SN
import Tests.continuity_analytic as CA

MANUAL = True

K6 = SN.KNOTS_6
K4 = SN.KNOTS_4

# --- Bezier extraction of a clamped cubic with KNOTS_6 (verified against
#     OCCT `insertKnot`: rows are the standard span-endpoint blossoms) ------
#
#   first span   b0=P0, b1=P1, b2=(P1+P2)/2, b3=P1/4 + 7P2/12 + P3/6
#   last  span   c0=P2/6+7P3/12+P4/4, c1=(P3+P4)/2, c2=P4, c3=P5
E0 = np.array([[1.0, 0.0, 0.0, 0.0],
               [0.0, 1.0, 0.0, 0.0],
               [0.0, 0.5, 0.5, 0.0],
               [0.0, 0.25, 7.0 / 12, 1.0 / 6]])
E1 = np.array([[1.0 / 6, 7.0 / 12, 0.25, 0.0],
               [0.0, 0.5, 0.5, 0.0],
               [0.0, 0.0, 1.0, 0.0],
               [0.0, 0.0, 0.0, 1.0]])

# Outward extension of a first-span cubic across the seam (blossom):
#   L_k = sum_l EXT[k][l] B_l  (L3 = B0 is the boundary, L0 the far end)
EXT = np.array([[8.0, -12.0, 6.0, -1.0],
                [4.0, -4.0, 1.0, 0.0],
                [2.0, -1.0, 0.0, 0.0],
                [1.0, 0.0, 0.0, 0.0]])

# seam name -> (axis kind, fixed corner index, inner sign)
#   column = v is fixed, the seam runs along u (corner index t = u)
#   row    = u is fixed, the seam runs along v (corner index t = v)
#   v0 -> v=0 (inner +1), u0 -> u=0 (inner +1),
#   u1 -> u=5 (inner -1), v1 -> v=5 (inner -1)
SEAMS = (("v0", "column", 0, +1),
         ("u0", "row", 0, +1),
         ("u1", "row", 5, -1),
         ("v1", "column", 5, -1))

# ring order `SilkMachinery.corner_grid` wants (consecutive strips share the
# junction): u0, v0, u1, v1 -- the order `synthetic_strips` builds.
RING = ("u0", "v0", "u1", "v1")
# from a ring grid's along index U to the corner's along index (rev flags)
RING_REV = {"u0": True, "v0": False, "u1": False, "v1": True}


# ---------------------------------------------------------------------------
# synthetic known-answer feed
# ---------------------------------------------------------------------------

def synthetic_truth():
    """A genuinely curved 6x6 Silk control net `T` (a graph over a square).

    `T[i][j]`, i = u index, j = v index, both `KNOTS_6`.
    """
    xs = [0.0, 0.2, 0.4, 0.6, 0.8, 1.0]
    S = 60.0
    return [[Base.Vector(xs[i] * S, xs[j] * S,
                         0.006 * (xs[i] * S) ** 2
                         + 0.004 * (xs[j] * S) ** 2
                         + 0.003 * (xs[i] * S) * (xs[j] * S) + 2.0)
             for j in range(6)] for i in range(6)]


def _span0_first4(T, axis, idx):
    """First-span Bezier CPs B_0..B_3 of one curve of `T`.

    axis 'v': curve is T[idx][*] (idx = u index), across = v.
    axis 'u': curve is T[*][idx] (idx = v index), across = u.
    """
    B = np.zeros((4, 3))
    for k in range(4):
        for l in range(4):
            P = T[idx][l] if axis == "v" else T[l][idx]
            B[k] += E0[k][l] * np.array([P.x, P.y, P.z])
    return B


def _span1_first4(T, axis, idx):
    """Last-span Bezier CPs B'_0..B'_3 (B'_3 is the u/v=1 boundary)."""
    B = np.zeros((4, 3))
    for k in range(4):
        for l in range(4):
            P = T[idx][2 + l] if axis == "v" else T[2 + l][idx]
            B[k] += E1[k][l] * np.array([P.x, P.y, P.z])
    return B


def _outward_ext(B):
    """Outward Bezier CPs L_0..L_3 of a first-span cubic (L_3 = boundary B_0)."""
    return EXT.dot(B)


def _outward_ext_last(B):
    """Outward Bezier CPs R_0..R_3 of a last-span cubic (R_0 = B'_3)."""
    return EXT.dot(np.array([B[3], B[2], B[1], B[0]]))


def synthetic_strips(T):
    """Four 24-pole grids (ring order u0,v0,u1,v1) as outward extensions.

    Ring/orientation chosen so `corner_grid` accepts them (consecutive
    grids share their junction corner at V3U5 / V3U0).
    """
    grids = [np.zeros((4, 6, 3)) for _ in range(4)]  # [V m][U along][xyz]
    # g0 = u=0 boundary, across = u (outward u<0), along = v (j), reversed
    for j in range(6):
        L = _outward_ext(_span0_first4(T, "u", j))
        for m in range(4):
            grids[0][m][5 - j] = L[m]
    # g1 = v=0 boundary, across = v (outward v<0), along = u (i), direct
    for i in range(6):
        L = _outward_ext(_span0_first4(T, "v", i))
        for m in range(4):
            grids[1][m][i] = L[m]
    # g2 = u=1 boundary, across = u (outward u>1), along = v (j), direct
    for j in range(6):
        R = _outward_ext_last(_span1_first4(T, "u", j))
        for m in range(4):
            grids[2][m][j] = R[m]
    # g3 = v=1 boundary, across = v (outward v>1), along = u (i), reversed
    for i in range(6):
        R = _outward_ext_last(_span1_first4(T, "v", i))
        for m in range(4):
            grids[3][m][5 - i] = R[m]
    return grids


def _grid_flat(grid):
    """(poles24, weights24) in Silk's flat v-major order (index = V*6+U)."""
    poles = []
    for m in range(4):
        for u in range(6):
            p = grid[m][u]
            poles.append(Base.Vector(float(p[0]), float(p[1]), float(p[2])))
    return poles, [1.0] * 24


def _strip_surface_from_grid(grid, weights=None):
    poles_flat, w = _grid_flat(grid)
    if weights is not None:
        w = weights
    return SN.NurbsSurface.from_flat(poles_flat, w, 6, 4, K6, K4)


# ---------------------------------------------------------------------------
# current construction (averaging `corner_grid`) -> 36x4 homogeneous
# ---------------------------------------------------------------------------

def current_corner_h(grids):
    """The shipped averaging construction on four flat grids -> 36x4."""
    import SilkMachinery as M

    flat = [_grid_flat(g)[0] for g in grids]
    p36, w36, why = M.corner_grid([(f, [1.0] * 24) for f in flat], 1e-6)
    if p36 is None:
        raise RuntimeError("corner_grid refused: %s" % why)
    H = np.zeros((36, 4))
    for k in range(36):
        H[k] = [p36[k].x, p36[k].y, p36[k].z, w36[k]]
    return H


# ---------------------------------------------------------------------------
# alignment: ring grids -> the three rows behind each seam, indexed by the
# corner's own along index (so the solve is independent of ring orientation)
# ---------------------------------------------------------------------------

def aligned_rows_from_grids(grids, weights=None, tol=1e-6):
    """{seam: (V3, V2, V1)} from ring-ordered 24-pole grids.

    Each returned row is a (6, 4) homogeneous array indexed by the corner's
    along index (u for a column seam, v for a row seam), so `v3[k]` is the
    junction point at along station k and `v2[k]` / `v1[k]` are the rows one
    and two steps OUTWARD from the junction.

    This reproduces exactly what `corner_grid` sees, but keeps the two extra
    rows a G2 condition needs (the shipped construction drops V1).
    """
    if weights is None:
        weights = [[1.0] * 24 for _ in range(4)]
    gh = {}
    for name, gi in zip(RING, range(4)):
        w = weights[gi]
        rows = np.zeros((4, 6, 4))
        for m in range(4):
            for u in range(6):
                p = grids[gi][m][u]
                iw = w[m * 6 + u]
                rows[m][u] = [p[0] * iw, p[1] * iw, p[2] * iw, iw]
        rev = RING_REV[name]
        V3 = np.array([rows[3][5 - k if rev else k] for k in range(6)])
        V2 = np.array([rows[2][5 - k if rev else k] for k in range(6)])
        V1 = np.array([rows[1][5 - k if rev else k] for k in range(6)])
        gh[name] = (V3, V2, V1)
    return gh


# ---------------------------------------------------------------------------
# the G2 solve
# ---------------------------------------------------------------------------

def _h_rows(H):
    """36 homogeneous poles (flat v*6+u) -> Cartesian positions, 36x3."""
    return H[:, :3] / H[:, 3:4]


def _central_free():
    """Free pole indices after hard C0 (boundary) and hard G1 (one-in ring).

    A 6x6 clamped bicubic corner has 20 boundary poles (row 0) and a 12-pole
    one-in ring (row 1); C0 and G1 fix those, leaving the four central poles
    (2,2),(2,3),(3,2),(3,3) -- the only handles a G2 condition has.
    """
    free = np.ones(36, dtype=bool)
    for _name, kind, fixed, inner in SEAMS:
        for off in (0, 1):
            for t in range(6):
                k = (((fixed + off * inner) * 6 + t) if kind == "column"
                     else (t * 6 + (fixed + off * inner)))
                free[k] = False
    return [k for k in range(36) if free[k]]


def _k_residuals(H, neighbours, n_st=9, tol=1e-5):
    """(residual vector, matches): `k_a - k_b` per seam station (1/mm).

    `neighbours` maps seam name -> the neighbour `NurbsSurface`.  The seam
    correspondence is found by `continuity_analytic.match_boundaries` at every
    call, so the caller needs no orientation bookkeeping.  The residual is
    linear in the free central poles (C0/G1 fixed the boundary and the one-in
    ring, which carry the first derivatives and hence the normal and the
    across-normalisation).
    """
    surf = _h_to_surface(H)
    res, matches = [], []
    for name, _kind, _fixed, _inner in SEAMS:
        nb = neighbours.get(name)
        if nb is None:
            continue
        ms = CA.match_boundaries(surf, nb, tol=tol)
        if not ms:
            continue
        m = ms[0]
        rep = CA.measure_edges(surf, m["edge_a"], m["reverse_a"],
                               nb, m["edge_b"], m["reverse_b"], n=n_st)
        for s in rep["samples"]:
            res.append(s["k_a"] - s["k_b"])
        matches.append((name, m["edge_a"], m["edge_b"], m["reverse_a"]))
    return np.array(res), matches


def solve_corner_h(neighbours, aligned, lambdas=None, current_h=None,
                   n_st=9, n_iter=6):
    """Solve the corner's 36 poles for G2 (across-normal-curvature matching).

    `neighbours` maps seam name -> the neighbour `NurbsSurface` (the surface
    the corner must continue); `aligned` is `{seam: (V3, V2, V1)}` (the
    neighbour's junction row and the two rows behind it, indexed by the
    corner's along index, homogeneous 6x4).  `lambdas` is `{seam: array(6)}`,
    the across-parametrisation ratio `|V2 - V3| / |b1 - b0|` (the G1
    freedom); for the synthetic feed the strips are built with matched
    parametrisation so lambda = 1, for the demo it is read from the corner's
    own G1 rows.  `current_h` is the corner's current 36x4 homogeneous net
    (the starting point -- its central poles are the free handles).

    CONTINUITY TO A NEIGHBOUR is a condition on the corner's pole rows behind
    the seam: row 0 -> C0, row 1 -> G1, row 2 -> G2.  So:

      1. HARD C0: boundary pole row = the neighbour's junction row V3.
      2. HARD G1: one pole in = V3 - (V2 - V3) / lambda  (the across tangent,
         anti-parallel to the neighbour's, at the neighbour's scale).
      3. SOFT G2: least-squares over the four central poles left free,
         minimising the measured across-normal-curvature gap `k_a - k_b` at
         `n_st` stations per seam.  `k_a` is exactly linear in those poles
         (the first derivatives, hence the normal and the normalisation, are
         fixed by steps 1-2), so one Gauss-Newton step is exact and the
         remaining residual is the four neighbours' second-order
         **incompatibility** -- the minimum attainable `k_gap` for this feed.

    The 24 station equations on 4 poles (12 components) are over-determined,
    so exact G2 is possible precisely when the neighbours are mutually
    compatible (`residual` -> 0).  Returns (H36, info).
    """
    H = np.array(current_h, dtype=float) if current_h is not None \
        else np.zeros((36, 4))
    if H.shape != (36, 4):
        H = np.zeros((36, 4))
    for k in range(36):
        if abs(H[k][3]) < 1e-12:
            H[k] = [0.0, 0.0, 0.0, 1.0]

    # 1-2. hard C0 and hard G1 (control level, from the aligned neighbour rows)
    for name, kind, fixed, inner in SEAMS:
        V3, V2, _V1 = aligned[name]
        c3 = V3[:, :3] / V3[:, 3:4]
        c2 = V2[:, :3] / V2[:, 3:4]
        lam = (lambdas or {}).get(name)
        for t in range(6):
            L = float(lam[t]) if lam is not None else 1.0
            k0 = (fixed * 6 + t) if kind == "column" else (t * 6 + fixed)
            k1 = (((fixed + inner) * 6 + t) if kind == "column"
                  else (t * 6 + (fixed + inner)))
            H[k0] = [c3[t][0], c3[t][1], c3[t][2], 1.0]
            b1 = c3[t] - (c2[t] - c3[t]) / L
            H[k1] = [b1[0], b1[1], b1[2], 1.0]

    # 3. soft G2: Gauss-Newton on the four free central poles (exact: linear)
    free = _central_free()
    eps = 1.0
    matches = []
    for _ in range(n_iter):
        r, matches = _k_residuals(H, neighbours, n_st)
        if len(r) == 0 or float(np.max(np.abs(r))) < 1e-12:
            break
        J = np.zeros((len(r), 3 * len(free)))
        for c, k in enumerate(free):
            for d in range(3):
                Hp = H.copy()
                Hp[k, d] += eps
                rp, _ = _k_residuals(Hp, neighbours, n_st)
                J[:, 3 * c + d] = (rp - r) / eps
        delta, *_ = np.linalg.lstsq(J, -r, rcond=None)
        for c, k in enumerate(free):
            H[k, :3] += delta[3 * c:3 * c + 3]
    r, matches = _k_residuals(H, neighbours, n_st)
    resid = float(np.max(np.abs(r))) if len(r) else 0.0
    return H, {"rows": len(r), "n_free": len(free), "residual": resid,
               "soft_residual_mm": resid, "matches": matches,
               "sv": np.zeros(0)}


def _h_to_surface(H):
    """36 homogeneous poles (flat v*6+u) -> a rational `NurbsSurface`."""
    poles = [[Base.Vector(H[v * 6 + u][0] / H[v * 6 + u][3],
                          H[v * 6 + u][1] / H[v * 6 + u][3],
                          H[v * 6 + u][2] / H[v * 6 + u][3])
              for v in range(6)] for u in range(6)]
    weights = [[H[v * 6 + u][3] for v in range(6)] for u in range(6)]
    return SN.NurbsSurface(poles, weights, K6, K6)


# ---------------------------------------------------------------------------
# measurement
# ---------------------------------------------------------------------------

def measure_against(corner, strips, n=41):
    """k_gap/twist_gap/c0/g1 of `corner` against each of four strips.

    `strips` maps seam name -> a `NurbsSurface` on the other side of that
    seam.  The correspondence is found by `match_boundaries`, so the caller
    needs no orientation bookkeeping.
    """
    out = {}
    for name, _kind, _fixed, _inner in SEAMS:
        s = strips.get(name)
        if s is None:
            out[name] = None
            continue
        ms = CA.match_boundaries(corner, s, tol=1e-6)
        if not ms:
            out[name] = None
            continue
        m = ms[0]
        r = CA.measure_edges(corner, m["edge_a"], m["reverse_a"],
                             s, m["edge_b"], m["reverse_b"], n=n)
        r["reverse"] = bool(m["reverse_a"] or m["reverse_b"])
        out[name] = r
    return out


def _fmt_report(title, report):
    print("  %s" % title)
    worst_k = 0.0
    worst_t = 0.0
    for name, _kind, _fixed, _inner in SEAMS:
        r = report.get(name)
        if r is None:
            print("    %-4s no shared boundary" % name)
            continue
        worst_k = max(worst_k, r["k_gap"])
        worst_t = max(worst_t, r["twist_gap"])
        flag = " (rev)" if r.get("reverse") else ""
        print("    %-4s c0=%.2e  g1=%.4f deg  k_gap=%.4e /mm  "
              "twist=%.4e /mm%s"
              % (name, r["c0"], r["g1_deg"], r["k_gap"], r["twist_gap"], flag))
    return worst_k, worst_t


# ---------------------------------------------------------------------------
# feed 1: synthetic known-answer
# ---------------------------------------------------------------------------

def run_synthetic(n=41):
    T = synthetic_truth()
    grids = synthetic_strips(T)
    strips = {name: _strip_surface_from_grid(grids[i])
              for i, name in enumerate(RING)}
    aligned = aligned_rows_from_grids(grids)
    truth = SN.NurbsSurface.from_flat(
        [T[i][j] for j in range(6) for i in range(6)],
        [1.0] * 36, 6, 6, K6, K6)

    print("== synthetic (one known smooth surface T; truth is T) ==")
    t = measure_against(truth, strips, n=n)
    _fmt_report("truth T vs strips (truth = T exactly)", t)

    Hc = current_corner_h(grids)
    cur = _h_to_surface(Hc)
    c = measure_against(cur, strips, n=n)
    ck, _ct = _fmt_report("current averaging construction", c)

    Hs, info = solve_corner_h(strips, aligned, current_h=Hc)
    sol = _h_to_surface(Hs)
    s = measure_against(sol, strips, n=n)
    sk, _st = _fmt_report("G2 solve (least-squares)", s)
    print("    solve: stations=%d free=%d residual_k=%.3e /mm"
          % (info["rows"], info["n_free"], info["soft_residual_mm"]))

    truth_h = np.array([[truth.poles[u][v].x, truth.poles[u][v].y,
                         truth.poles[u][v].z, truth.weights[u][v]]
                        for v in range(6) for u in range(6)])
    poles_inf = float(np.max(np.abs(Hs - truth_h)))
    print("    |solved - T|_inf (homogeneous) = %.3e" % poles_inf)
    return {"truth": t, "current": c, "solved": s, "solve_info": info,
            "current_worst_k": ck, "solved_worst_k": sk,
            "poles_inf": poles_inf}


# ---------------------------------------------------------------------------
# feed 2: the demo's real junctions (deliverables 3 + 4)
# ---------------------------------------------------------------------------

DEMO_NAME = "Silk_Demo_01"


def demo_path():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(root, "Resources", "Demo_files", DEMO_NAME + ".FCStd")


def get_demo_doc():
    import FreeCAD
    if DEMO_NAME in FreeCAD.listDocuments():
        return FreeCAD.getDocument(DEMO_NAME)
    return FreeCAD.openDocument(demo_path())


def _cls(obj):
    proxy = getattr(obj, "Proxy", None)
    return type(proxy).__name__ if proxy is not None else ""


def _corner_objects(doc):
    return [o for o in doc.Objects if _cls(o) == "CubicSurface_66"]


def _blend_lookup(doc):
    """6x4 grid object name -> the CubicSurface_64 that draws it."""
    out = {}
    for o in doc.Objects:
        if _cls(o) == "CubicSurface_64" and getattr(o, "Grid", None) is not None:
            out[o.Grid.Name] = o
    return out


def _grid_rows(poles24):
    return [[poles24[r * 6 + u] for u in range(6)] for r in range(4)]


def _match_boundary_row(boundary, rows, tol=1e-6):
    """(r, rev) such that grid row `r` names `boundary` (forward or reversed).

    A strip's junction row is an END row (0 or 3): the strip runs from the
    junction outward.  `rev` means the strip's U index runs opposite to the
    corner's along index.
    """
    for r in (0, 3):
        for rev in (False, True):
            if all((rows[r][5 - k if rev else k] - boundary[k]).Length < tol
                   for k in range(6)):
                return r, rev
    return None


def _boundary_rows(corner_flat):
    """The corner's four boundary rows in flat v*6+u, indexed by along index."""
    return {
        "u0": [corner_flat[v * 6 + 0] for v in range(6)],
        "u1": [corner_flat[v * 6 + 5] for v in range(6)],
        "v0": [corner_flat[0 * 6 + u] for u in range(6)],
        "v1": [corner_flat[5 * 6 + u] for u in range(6)],
    }


def demo_aligned(corner_obj, doc):
    """{seam: (V3, V2, V1)} for one demo corner, from its neighbouring grids.

    The corner's boundary row is matched (forward or reversed) against each
    neighbouring 6x4 grid's end rows; V3 is that junction row, V2 the row one
    step outward, V1 two steps outward -- all re-indexed to the corner's own
    along index.  Returns (aligned, strips, detail) where `strips` maps seam
    -> the neighbour `NurbsSurface` and `detail` records the match.
    """
    corner_flat = list(corner_obj.Grid.Poles)
    bounds = _boundary_rows(corner_flat)
    # unique neighbour grids around this corner (SubGrid_0..3 name Grid_0/1)
    grids = []
    seen = set()
    for sub in (corner_obj.Grid.SubGrid_0, corner_obj.Grid.SubGrid_1,
                corner_obj.Grid.SubGrid_2, corner_obj.Grid.SubGrid_3):
        for g in (sub.Grid_0, sub.Grid_1):
            if g is not None and g.Name not in seen:
                seen.add(g.Name)
                grids.append(g)
    lookup = _blend_lookup(doc)

    aligned, strips, detail = {}, {}, {}
    for name, kind, fixed, inner in SEAMS:
        b = bounds[name]
        for g in grids:
            rows = _grid_rows(list(g.Poles))
            m = _match_boundary_row(b, rows)
            if m is None:
                continue
            r, rev = m
            gw = list(getattr(g, "Weights", []) or [1.0] * 24)
            grows = [[(rows[rr][u], gw[rr * 6 + u]) for u in range(6)]
                     for rr in range(4)]
            if r == 0:
                R3, R2, R1 = grows[0], grows[1], grows[2]
            else:
                R3, R2, R1 = grows[3], grows[2], grows[1]

            def al(row):
                return [row[5 - k if rev else k] for k in range(6)]

            def hv(row):
                return np.array([_hv(p, w) for (p, w) in row])

            aligned[name] = (hv(al(R3)), hv(al(R2)), hv(al(R1)))
            surf_obj = lookup.get(g.Name)
            strips[name] = (SN.NurbsSurface.from_object(surf_obj)
                            if surf_obj is not None
                            else SN.NurbsSurface.from_flat(
                                list(g.Poles),
                                list(getattr(g, "Weights", []) or [1.0] * 24),
                                6, 4, K6, K4))
            detail[name] = {"grid": g.Name, "row": r, "rev": rev,
                            "surface": surf_obj.Name if surf_obj else None}
            break
    return aligned, strips, detail


def _hv(p, w=1.0):
    """A `Base.Vector` pole and weight -> a homogeneous 4-vector (w*P, w)."""
    return [float(p.x) * w, float(p.y) * w, float(p.z) * w, float(w)]


def demo_current_surface(corner_obj):
    return SN.NurbsSurface.from_object(corner_obj)


def _demo_corner_row(corner_flat, kind, fixed, inner, offset):
    """The corner's row `offset` steps in from the seam (0 = boundary)."""
    if kind == "column":
        base = (fixed + inner * offset) * 6
        return [corner_flat[base + t] for t in range(6)]
    return [corner_flat[t * 6 + (fixed + inner * offset)] for t in range(6)]


def demo_lambdas(corner_obj, aligned):
    """{seam: array(6)} -- the neighbour/corner across-parameter ratio.

    Read from the corner's own G1 rows (the corner is tangent-continuous at
    the control level), so a full 6x6 corner is well-posed even though the
    neighbour blend's across span has a different parametrisation.
    """
    flat = list(corner_obj.Grid.Poles)
    out = {}
    for name, kind, fixed, inner in SEAMS:
        V3, V2, _V1 = aligned[name]
        b0 = _demo_corner_row(flat, kind, fixed, inner, 0)
        b1 = _demo_corner_row(flat, kind, fixed, inner, 1)
        lam = []
        for t in range(6):
            d0 = _vec(V3[t])
            d1 = _vec(V2[t])
            c = (b1[t] - b0[t]).Length
            n = (d1 - d0).Length
            lam.append(n / c if c > 1e-12 else 1.0)
        out[name] = np.array(lam)
    return out


def _vec(h):
    """A homogeneous 4-vector -> its `Base.Vector` position."""
    return Base.Vector(h[0] / h[3], h[1] / h[3], h[2] / h[3])


def run_demo(n=41, verbose=True):
    doc = get_demo_doc()
    out = []
    for corner in _corner_objects(doc):
        aligned, strips, detail = demo_aligned(corner, doc)
        missing = [s for s, _k, _f, _i in SEAMS if s not in aligned]
        if missing:
            out.append({"corner": corner.Name, "error":
                        "no neighbour matched for %s" % missing})
            continue
        cur = demo_current_surface(corner)
        cur_h = np.array([[cur.weights[u][v] * cur.poles[u][v].x,
                           cur.weights[u][v] * cur.poles[u][v].y,
                           cur.weights[u][v] * cur.poles[u][v].z,
                           cur.weights[u][v]]
                          for v in range(6) for u in range(6)])
        lambdas = demo_lambdas(corner, aligned)
        Hs, info = solve_corner_h(strips, aligned, lambdas, current_h=cur_h)
        sol = _h_to_surface(Hs)
        cur_rep = measure_against(cur, strips, n=n)
        sol_rep = measure_against(sol, strips, n=n)
        if verbose:
            print("== demo junction %s ==" % corner.Name)
            for name, _k, _f, _i in SEAMS:
                print("    %-4s neighbour %-20s row=%d rev=%s  lambda=%s"
                      % (name, detail[name]["grid"], detail[name]["row"],
                         detail[name]["rev"],
                         " ".join("%.2f" % x for x in lambdas[name])))
            _fmt_report("current (ControlGrid66_4Sub)", cur_rep)
            ck, ct = _fmt_report("G2 solve (least-squares)", sol_rep)
            print("    solve: stations=%d free=%d residual_k=%.3e /mm "
                  "(neighbour incompatibility)"
                  % (info["rows"], info["n_free"], info["soft_residual_mm"]))
        out.append({"corner": corner.Name, "detail": detail,
                    "solve_info": {k: (float(v) if k == "residual" else v)
                                   for k, v in info.items() if k != "sv"},
                    "current": cur_rep, "solved": sol_rep})
    return out


# ---------------------------------------------------------------------------
# report
# ---------------------------------------------------------------------------

def _summarise(demo):
    worst_cur = 0.0
    worst_sol = 0.0
    res = []
    for r in demo:
        if "error" in r:
            continue
        for name, _k, _f, _i in SEAMS:
            if r["current"].get(name):
                worst_cur = max(worst_cur, r["current"][name]["k_gap"])
            if r["solved"].get(name):
                worst_sol = max(worst_sol, r["solved"][name]["k_gap"])
        res.append(r["solve_info"]["soft_residual_mm"])
    return worst_cur, worst_sol, res


def main(n=41, json_path=None):
    syn = run_synthetic(n=n)
    print()
    demo = run_demo(n=n)
    if demo:
        wc, ws, res = _summarise(demo)
        print()
        print("== summary ==")
        print("  synthetic: current k_gap %.3e  solved k_gap %.3e  "
              "|solved-T| %.3e" % (syn["current_worst_k"], syn["solved_worst_k"],
                                   syn["poles_inf"]))
        print("  demo:      current k_gap %.3e  solved k_gap %.3e  "
              "(worst over junctions; neighbour incompatibility %s mm)"
              % (wc, ws, ["%.2e" % x for x in res]))
    if json_path:
        import json

        def _clean(rep):
            return {k: (None if v is None else
                        {kk: vv for kk, vv in v.items()
                         if kk != "samples"}) for k, v in rep.items()}

        payload = {
            "synthetic": {
                "current_worst_k": syn["current_worst_k"],
                "solved_worst_k": syn["solved_worst_k"],
                "poles_inf": syn["poles_inf"],
                "solve_info": {k: (v.tolist() if k == "sv" else v)
                               for k, v in syn["solve_info"].items()},
                "current": _clean(syn["current"]),
                "solved": _clean(syn["solved"]),
            },
            "demo": [
                {"corner": r.get("corner"), "error": r.get("error"),
                 "detail": r.get("detail"), "solve_info": r.get("solve_info"),
                 "current": _clean(r["current"]) if "current" in r else None,
                 "solved": _clean(r["solved"]) if "solved" in r else None}
                for r in demo
            ],
        }
        with open(json_path, "w") as fh:
            json.dump(payload, fh, indent=1)
        print("  raw output -> %s" % json_path)
    return {"synthetic": syn, "demo": demo}


if __name__ == "__main__":
    main()
