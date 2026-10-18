"""Pure-numpy port of the #106 G2-feasibility measurement (ticket #106).

MEASUREMENT, not a build.  This is the offline machinery behind
`Tests/test_g2_feasibility.py`: a numpy port of the #97/#100 instrument
(`Tests/silk_nurbs.py` + `Tests/continuity_analytic.py`) and of the #100
corner solve (`Tests/g2_corner_solve.py`), fed from
`Resources/Demo_files/Silk_Demo_01.FCStd` read straight from its zip
(`Document.xml` + `Poles*` / `Weights*` blobs; the technique of
`Tests/test_triangular_member_calibration.py`).  No surface is evaluated
through FreeCAD.

The four pinned tests live in `Tests/test_g2_feasibility.py` and import
`_analysis` and `SEAMS` from here.  Nothing here asserts a continuity label
or calls the continuity label function.  Finding:
`docs/research/silk-g2-feasibility.md`;
raw JSONs/scripts: `/tmp/opencode/g2_feasibility/`.

NOTE FOR INTEGRATION: this module carries the numpy port while the solve
lives only in `Tests/g2_corner_solve.py` (MANUAL).  When the solve moves into
`SilkMachinery`, the test should call that instead of the local port.

PRE-#101 TWIST FRAME: `measure_seam` here still carries the old torsion frame
(the surface's natural along axis; the normal side lost after alignment), so
its `twist_gap` reads ~2|tau| on any seam whose natural normals oppose.  Its
`k_gap` -- the quantity every pin in `Tests/test_g2_feasibility.py` is about
-- is unaffected.  The corrected frame lives in `Tests/continuity_analytic.py`
and `Tests/g2_oracle.py` (#101); do not quote this port's `twist_gap`.
"""

import math
import os
import re
import struct
import sys
import zipfile

import numpy as np

try:
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import silk_reload  # noqa: E402
    MOD_DIR = silk_reload.MOD_DIR
except Exception:  # standalone draft run (outside the harness)
    MOD_DIR = os.environ.get(
        "SILK_MOD_DIR",
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DEMO = os.path.join(MOD_DIR, "Resources", "Demo_files", "Silk_Demo_01.FCStd")

REL = 1e-6          # relative pin tolerance for the measured k_gap numbers
ABS = 1e-16         # absolute floor for near-zero readings
N_FINAL = 401       # converged measurement station count

K6 = [0.0, 0.0, 0.0, 0.0, 1.0 / 3, 2.0 / 3, 1.0, 1.0, 1.0, 1.0]
K4 = [0.0, 0.0, 0.0, 0.0, 1.0, 1.0, 1.0, 1.0]


# ---------------------------------------------------------------------------
# numpy port of the instrument (Tests/silk_nurbs.py / continuity_analytic.py)
# ---------------------------------------------------------------------------

def _find_span(n, p, u, knots):
    if u >= knots[n + 1]:
        return n
    if u <= knots[p]:
        return p
    lo, hi = p, n + 1
    mid = (lo + hi) // 2
    while u < knots[mid] or u >= knots[mid + 1]:
        if u < knots[mid]:
            hi = mid
        else:
            lo = mid
        mid = (lo + hi) // 2
    return mid


def _basis_derivatives(span, u, p, knots, order=2):
    ndu = [[0.0] * (p + 1) for _ in range(p + 1)]
    ndu[0][0] = 1.0
    left = [0.0] * (p + 1)
    right = [0.0] * (p + 1)
    for j in range(1, p + 1):
        left[j] = u - knots[span + 1 - j]
        right[j] = knots[span + j] - u
        saved = 0.0
        for r in range(j):
            ndu[j][r] = right[r + 1] + left[j - r]
            temp = ndu[r][j - 1] / ndu[j][r]
            ndu[r][j] = saved + right[r + 1] * temp
            saved = left[j - r] * temp
        ndu[j][j] = saved
    ders = [[0.0] * (p + 1) for _ in range(order + 1)]
    for j in range(p + 1):
        ders[0][j] = ndu[j][p]
    a = [[0.0] * (p + 1) for _ in range(2)]
    for r in range(p + 1):
        s1, s2 = 0, 1
        a[0][0] = 1.0
        for k in range(1, order + 1):
            d = 0.0
            rk = r - k
            pk = p - k
            if r >= k:
                a[s2][0] = a[s1][0] / ndu[pk + 1][rk]
                d = a[s2][0] * ndu[rk][pk]
            j1 = 1 if rk >= -1 else -rk
            j2 = k - 1 if (r - 1) <= pk else p - r
            for j in range(j1, j2 + 1):
                a[s2][j] = (a[s1][j] - a[s1][j - 1]) / ndu[pk + 1][rk + j]
                d += a[s2][j] * ndu[rk + j][pk]
            if r <= pk:
                a[s2][k] = -a[s1][k - 1] / ndu[pk + 1][r]
                d += a[s2][k] * ndu[r][pk]
            ders[k][r] = d
            s1, s2 = s2, s1
    fac = 1.0
    for k in range(1, order + 1):
        fac *= (p - k + 1)
        for j in range(p + 1):
            ders[k][j] *= fac
    return ders


def _binom(n, k):
    return math.factorial(n) // (math.factorial(k) * math.factorial(n - k))


class NS:
    def __init__(self, poles, weights, knots_u=K6, knots_v=K6,
                 degree_u=3, degree_v=3):
        self.poles = [[np.asarray(p, dtype=float) for p in col]
                      for col in poles]
        self.weights = [[float(w) for w in col] for col in weights]
        self.knots_u = list(knots_u)
        self.knots_v = list(knots_v)
        self.degree_u = degree_u
        self.degree_v = degree_v
        self.nu = len(poles)
        self.nv = len(poles[0])
        self.hom = [[np.array([self.weights[u][v] * self.poles[u][v][0],
                               self.weights[u][v] * self.poles[u][v][1],
                               self.weights[u][v] * self.poles[u][v][2],
                               self.weights[u][v]])
                     for v in range(self.nv)] for u in range(self.nu)]

    @classmethod
    def from_flat(cls, poles_flat, weights_flat, nu, nv,
                  knots_u=K6, knots_v=K6, degree_u=3, degree_v=3):
        poles = [[poles_flat[v * nu + u] for v in range(nv)]
                 for u in range(nu)]
        weights = [[weights_flat[v * nu + u] for v in range(nv)]
                   for u in range(nu)]
        return cls(poles, weights, knots_u, knots_v, degree_u, degree_v)

    def ders(self, u, v, order=2):
        pu, pv = self.degree_u, self.degree_v
        su = _find_span(self.nu - 1, pu, u, self.knots_u)
        sv = _find_span(self.nv - 1, pv, v, self.knots_v)
        du = _basis_derivatives(su, u, pu, self.knots_u, order)
        dv = _basis_derivatives(sv, v, pv, self.knots_v, order)
        SKL = [[np.zeros(4) for _ in range(order + 1)]
               for _ in range(order + 1)]
        for k in range(order + 1):
            for l in range(order + 1):
                acc = np.zeros(4)
                for i in range(pu + 1):
                    di = du[k][i]
                    if di == 0.0:
                        continue
                    iu = su - pu + i
                    for j in range(pv + 1):
                        dj = dv[l][j]
                        if dj == 0.0:
                            continue
                        jv = sv - pv + j
                        acc = acc + (di * dj) * self.hom[iu][jv]
                SKL[k][l] = acc
        w00 = SKL[0][0][3]
        S = [[np.zeros(3) for _ in range(order + 1)]
             for _ in range(order + 1)]
        for k in range(order + 1):
            for l in range(order + 1):
                acc = SKL[k][l][:3].copy()
                for j in range(1, l + 1):
                    acc = acc - S[k][l - j] * (_binom(l, j) * SKL[0][j][3])
                for i in range(1, k + 1):
                    acc = acc - S[k - i][l] * (_binom(k, i) * SKL[i][0][3])
                    for j in range(1, l + 1):
                        acc = acc - S[k - i][l - j] * (
                            _binom(k, i) * _binom(l, j) * SKL[i][j][3])
                S[k][l] = acc * (1.0 / w00)
        zero = np.zeros(3)
        return (S[0][0],
                S[1][0] if order >= 1 else zero,
                S[0][1] if order >= 1 else zero,
                S[2][0] if order >= 2 else zero,
                S[1][1] if order >= 2 else zero,
                S[0][2] if order >= 2 else zero)

    def boundary(self, edge):
        if edge == "u0":
            return [(self.poles[0][v], self.weights[0][v])
                    for v in range(self.nv)]
        if edge == "u1":
            return [(self.poles[self.nu - 1][v],
                     self.weights[self.nu - 1][v]) for v in range(self.nv)]
        if edge == "v0":
            return [(self.poles[u][0], self.weights[u][0])
                    for u in range(self.nu)]
        if edge == "v1":
            return [(self.poles[u][self.nv - 1],
                     self.weights[u][self.nv - 1]) for u in range(self.nu)]
        raise ValueError("edge must be u0/u1/v0/v1, got %r" % (edge,))


def _unit(vec):
    length = float(np.linalg.norm(vec))
    return np.zeros(3) if length < 1e-15 else vec / length


def _dN_ds(ders, across, normal):
    P, Pu, Pv, Puu, Puv, Pvv = ders
    if across == "u":
        dwdt = np.cross(Puv, Pv) + np.cross(Pu, Pvv)
        ta = Pv
    else:
        dwdt = np.cross(Puu, Pv) + np.cross(Pu, Puv)
        ta = Pu
    w = np.cross(Pu, Pv)
    wlen = float(np.linalg.norm(w))
    tal = float(np.linalg.norm(ta))
    if wlen < 1e-15 or tal < 1e-15:
        return np.zeros(3)
    dwds = dwdt * (1.0 / tal)
    return (dwds - normal * float(np.dot(normal, dwds))) * (1.0 / wlen)


def measure_seam(surf_a, seam_a, across_a, surf_b, seam_b, across_b, n=21):
    out = {"c0": 0.0, "g1_deg": 0.0, "k_gap": 0.0, "twist_gap": 0.0,
           "samples": []}
    for k in range(n):
        t = k / (n - 1.0)
        ua, va = seam_a(t)
        ub, vb = seam_b(t)
        Pa, Pau, Pav, Pauu, Pauuv, Pavv = surf_a.ders(ua, va, order=2)
        Pb, Pbu, Pbv, Pbuu, Pbuuv, Pbvv = surf_b.ders(ub, vb, order=2)
        if across_a == "u":
            da, dda, ta = Pau, Pauu, Pav
        else:
            da, dda, ta = Pav, Pavv, Pau
        if across_b == "u":
            db, ddb, tb = Pbu, Pbuu, Pbv
        else:
            db, ddb, tb = Pbv, Pbvv, Pbu
        ta_hat = _unit(ta)
        tb_hat = _unit(tb)
        na = _unit(np.cross(da, ta))
        nb = _unit(np.cross(db, tb))
        if float(np.dot(na, nb)) < 0.0:
            nb = -nb
        c0 = float(np.linalg.norm(Pa - Pb))
        g1 = math.degrees(math.acos(max(-1.0, min(1.0,
                                                   float(np.dot(na, nb))))))
        da_perp = da - ta_hat * float(np.dot(da, ta_hat))
        db_perp = db - tb_hat * float(np.dot(db, tb_hat))
        kappa_a = (float(np.dot(dda, na)) / (float(np.dot(da_perp, da_perp)))
                   if float(np.linalg.norm(da_perp)) > 1e-12 else 0.0)
        kappa_b = (float(np.dot(ddb, nb)) / (float(np.dot(db_perp, db_perp)))
                   if float(np.linalg.norm(db_perp)) > 1e-12 else 0.0)
        e_across = _unit(da_perp)
        tau_a = -float(np.dot(_dN_ds((Pa, Pau, Pav, Pauu, Pauuv, Pavv),
                                     across_a, na), e_across))
        tau_b = -float(np.dot(_dN_ds((Pb, Pbu, Pbv, Pbuu, Pbuuv, Pbvv),
                                     across_b, nb), e_across))
        out["c0"] = max(out["c0"], c0)
        out["g1_deg"] = max(out["g1_deg"], g1)
        out["k_gap"] = max(out["k_gap"], abs(kappa_a - kappa_b))
        out["twist_gap"] = max(out["twist_gap"], abs(tau_a - tau_b))
        out["samples"].append({"t": t, "c0": c0, "k_a": kappa_a,
                               "k_b": kappa_b,
                               "k_gap": abs(kappa_a - kappa_b)})
    return out


def _edge_seam(edge, reverse=False):
    if edge == "u0":
        return (lambda t: (0.0, 1.0 - t if reverse else t)), "v", "u"
    if edge == "u1":
        return (lambda t: (1.0, 1.0 - t if reverse else t)), "v", "u"
    if edge == "v0":
        return (lambda t: (1.0 - t if reverse else t, 0.0)), "u", "v"
    if edge == "v1":
        return (lambda t: (1.0 - t if reverse else t, 1.0)), "u", "v"
    raise ValueError("edge must be u0/u1/v0/v1, got %r" % (edge,))


def measure_edges(surf_a, edge_a, reverse_a, surf_b, edge_b, reverse_b, n=21):
    seam_a, _al, across_a = _edge_seam(edge_a, reverse_a)
    seam_b, _al2, across_b = _edge_seam(edge_b, reverse_b)
    return measure_seam(surf_a, seam_a, across_a, surf_b, seam_b, across_b, n)


def homogeneous_boundary(surface, edge, reverse=False):
    b = surface.boundary(edge)
    if reverse:
        b = list(reversed(b))
    if not b:
        return []
    wref = b[0][1]
    return [(w * p[0] / wref, w * p[1] / wref, w * p[2] / wref, w / wref)
            for p, w in b]


def _close(a, b, tol):
    if len(a) != len(b):
        return False
    return all(max(abs(a[i][k] - b[i][k]) for k in range(4)) < tol
               for i in range(len(a)))


def match_boundaries(surf_a, surf_b, tol=1e-7):
    out = []
    for ea in ("u0", "u1", "v0", "v1"):
        for ra in (False, True):
            ha = homogeneous_boundary(surf_a, ea, reverse=ra)
            for eb in ("u0", "u1", "v0", "v1"):
                hb = homogeneous_boundary(surf_b, eb, reverse=False)
                if _close(ha, hb, tol):
                    out.append({"edge_a": ea, "edge_b": eb,
                                "reverse_a": ra, "reverse_b": False})
    return out


# ---------------------------------------------------------------------------
# seam frame, synthetic feed, corner solve (Tests/g2_corner_solve.py port)
# ---------------------------------------------------------------------------

SEAMS = (("v0", "column", 0, +1),
         ("u0", "row", 0, +1),
         ("u1", "row", 5, -1),
         ("v1", "column", 5, -1))
RING = ("u0", "v0", "u1", "v1")
RING_REV = {"u0": True, "v0": False, "u1": False, "v1": True}

E0 = np.array([[1.0, 0.0, 0.0, 0.0],
               [0.0, 1.0, 0.0, 0.0],
               [0.0, 0.5, 0.5, 0.0],
               [0.0, 0.25, 7.0 / 12, 1.0 / 6]])
E1 = np.array([[1.0 / 6, 7.0 / 12, 0.25, 0.0],
               [0.0, 0.5, 0.5, 0.0],
               [0.0, 0.0, 1.0, 0.0],
               [0.0, 0.0, 0.0, 1.0]])
EXT = np.array([[8.0, -12.0, 6.0, -1.0],
                [4.0, -4.0, 1.0, 0.0],
                [2.0, -1.0, 0.0, 0.0],
                [1.0, 0.0, 0.0, 0.0]])


def synthetic_truth():
    xs = [0.0, 0.2, 0.4, 0.6, 0.8, 1.0]
    S = 60.0
    return [[np.array([xs[i] * S, xs[j] * S,
                       0.006 * (xs[i] * S) ** 2
                       + 0.004 * (xs[j] * S) ** 2
                       + 0.003 * (xs[i] * S) * (xs[j] * S) + 2.0])
             for j in range(6)] for i in range(6)]


def _span0_first4(T, axis, idx):
    B = np.zeros((4, 3))
    for k in range(4):
        for l in range(4):
            P = T[idx][l] if axis == "v" else T[l][idx]
            B[k] += E0[k][l] * P
    return B


def _span1_first4(T, axis, idx):
    B = np.zeros((4, 3))
    for k in range(4):
        for l in range(4):
            P = T[idx][2 + l] if axis == "v" else T[2 + l][idx]
            B[k] += E1[k][l] * P
    return B


def _outward_ext(B):
    return EXT.dot(B)


def _outward_ext_last(B):
    return EXT.dot(np.array([B[3], B[2], B[1], B[0]]))


def synthetic_strips(T):
    grids = [np.zeros((4, 6, 3)) for _ in range(4)]
    for j in range(6):
        L = _outward_ext(_span0_first4(T, "u", j))
        for m in range(4):
            grids[0][m][5 - j] = L[m]
    for i in range(6):
        L = _outward_ext(_span0_first4(T, "v", i))
        for m in range(4):
            grids[1][m][i] = L[m]
    for j in range(6):
        R = _outward_ext_last(_span1_first4(T, "u", j))
        for m in range(4):
            grids[2][m][j] = R[m]
    for i in range(6):
        R = _outward_ext_last(_span1_first4(T, "v", i))
        for m in range(4):
            grids[3][m][5 - i] = R[m]
    return grids


def _grid_flat(grid):
    poles = []
    for m in range(4):
        for u in range(6):
            p = grid[m][u]
            poles.append(np.array([float(p[0]), float(p[1]), float(p[2])]))
    return poles, [1.0] * 24


def _strip_surface_from_grid(grid):
    poles_flat, w = _grid_flat(grid)
    return NS.from_flat(poles_flat, w, 6, 4, K6, K4)


def aligned_rows_from_grids(grids, weights=None):
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
        gh[name] = tuple(
            np.array([rows[3 - off][5 - k if rev else k]
                      for k in range(6)]) for off in (0, 1, 2))
    return gh


def _central_free():
    free = np.ones(36, dtype=bool)
    for _name, kind, fixed, inner in SEAMS:
        for off in (0, 1):
            for t in range(6):
                k = (((fixed + off * inner) * 6 + t) if kind == "column"
                     else (t * 6 + (fixed + off * inner)))
                free[k] = False
    return [k for k in range(36) if free[k]]


def _h_to_surface(H):
    poles = [[np.array([H[v * 6 + u][0] / H[v * 6 + u][3],
                        H[v * 6 + u][1] / H[v * 6 + u][3],
                        H[v * 6 + u][2] / H[v * 6 + u][3]])
              for v in range(6)] for u in range(6)]
    weights = [[H[v * 6 + u][3] for v in range(6)] for u in range(6)]
    return NS(poles, weights, K6, K6)


def _k_residuals(H, neighbours, n_st=9, tol=1e-5):
    surf = _h_to_surface(H)
    res = []
    for name, _kind, _fixed, _inner in SEAMS:
        nb = neighbours.get(name)
        if nb is None:
            continue
        ms = match_boundaries(surf, nb, tol=tol)
        if not ms:
            continue
        m = ms[0]
        rep = measure_edges(surf, m["edge_a"], m["reverse_a"],
                            nb, m["edge_b"], m["reverse_b"], n=n_st)
        res.extend(s["k_a"] - s["k_b"] for s in rep["samples"])
    return np.array(res)


def solve_corner_h(neighbours, aligned, lambdas=None, current_h=None,
                   n_st=9, n_iter=6):
    H = np.array(current_h, dtype=float) if current_h is not None \
        else np.zeros((36, 4))
    if H.shape != (36, 4):
        H = np.zeros((36, 4))
    for k in range(36):
        if abs(H[k][3]) < 1e-12:
            H[k] = [0.0, 0.0, 0.0, 1.0]
    for name, kind, fixed, inner in SEAMS:
        V3, V2, _V1 = aligned[name]
        c3 = V3[:, :3] / V3[:, 3:4]
        c2 = V2[:, :3] / V2[:, 3:4]
        lam = (lambdas or {}).get(name)
        for t in range(6):
            Ld = float(lam[t]) if lam is not None else 1.0
            k0 = (fixed * 6 + t) if kind == "column" else (t * 6 + fixed)
            k1 = (((fixed + inner) * 6 + t) if kind == "column"
                  else (t * 6 + (fixed + inner)))
            H[k0] = [c3[t][0], c3[t][1], c3[t][2], 1.0]
            b1 = c3[t] - (c2[t] - c3[t]) / Ld
            H[k1] = [b1[0], b1[1], b1[2], 1.0]
    free = _central_free()
    for _ in range(n_iter):
        r = _k_residuals(H, neighbours, n_st)
        if len(r) == 0 or float(np.max(np.abs(r))) < 1e-12:
            break
        J = np.zeros((len(r), 3 * len(free)))
        for c, k in enumerate(free):
            for d in range(3):
                Hp = H.copy()
                Hp[k, d] += 1.0
                rp = _k_residuals(Hp, neighbours, n_st)
                J[:, 3 * c + d] = rp - r
        delta, *_ = np.linalg.lstsq(J, -r, rcond=None)
        for c, k in enumerate(free):
            H[k, :3] += delta[3 * c:3 * c + 3]
    r = _k_residuals(H, neighbours, n_st)
    return H, {"residual": float(np.max(np.abs(r))) if len(r) else 0.0,
               "n_free": len(free)}


def measure_against(corner, strips, n=41):
    out = {}
    for name, _kind, _fixed, _inner in SEAMS:
        s = strips.get(name)
        if s is None:
            out[name] = None
            continue
        ms = match_boundaries(corner, s, tol=1e-6)
        if not ms:
            out[name] = None
            continue
        m = ms[0]
        r = measure_edges(corner, m["edge_a"], m["reverse_a"],
                          s, m["edge_b"], m["reverse_b"], n=n)
        r["reverse"] = bool(m["reverse_a"] or m["reverse_b"])
        out[name] = r
    return out


# ---------------------------------------------------------------------------
# SilkMachinery.corner_grid port (synthetic two-row-averaging control)
# ---------------------------------------------------------------------------

_CORNER_IDX = (0, 5, 18, 23)
_CORNER_COMMON = (3, 2)


def _corner_pts(grid):
    return [grid[k] for k in _CORNER_IDX]


def _pair_common(g0, g1, tol):
    c0, c1 = _corner_pts(g0), _corner_pts(g1)
    matches = [(i, j) for i in range(4) for j in range(4)
               if float(np.linalg.norm(c0[i] - c1[j])) <= tol]
    if not matches:
        return None
    if len(matches) == 1:
        return matches[0]
    for candidate in (_CORNER_COMMON, (_CORNER_COMMON[1], _CORNER_COMMON[0])):
        if candidate in matches:
            return candidate
    return None


def _subgrid33(poles_0, poles_1, tol=1e-6):
    g0, g1 = list(poles_0), list(poles_1)
    common = _pair_common(g0, g1, tol)
    if common is None:
        return None
    if common[0] in (1, 2) and common[1] in (0, 3):
        g0, g1 = g1, g0
        common = _pair_common(g0, g1, tol)
        if common is None:
            return None
    i, j = common
    if i == 0:
        v_col0 = [g0[0], g0[1], g0[2]]
        v_col1 = [g0[6], g0[7], g0[8]]
    elif i == 3:
        v_col0 = [g0[23], g0[22], g0[21]]
        v_col1 = [g0[17], g0[16], g0[15]]
    else:
        return None
    if j == 1:
        u_row0 = [g1[5], g1[4], g1[3]]
        u_row1 = [g1[11], g1[10], g1[9]]
    elif j == 2:
        u_row0 = [g1[18], g1[19], g1[20]]
        u_row1 = [g1[12], g1[13], g1[14]]
    else:
        return None
    span_v = float(np.linalg.norm(v_col1[0] - v_col0[0]))
    span_u = float(np.linalg.norm(u_row1[0] - u_row0[0]))
    if span_v <= 0.0 or span_u <= 0.0:
        return None
    u_tr = float(np.linalg.norm(u_row0[1] - u_row0[0])) / span_v
    v_tr = float(np.linalg.norm(v_col0[1] - v_col0[0])) / span_u
    p00, p01, p02 = u_row0[0], u_row0[1], u_row0[2]
    p10, p20 = v_col0[1], v_col0[2]
    p11_u = p01 + (u_row0[1] - u_row1[1]) * v_tr
    p12 = p02 + (u_row0[2] - u_row1[2]) * v_tr
    p11_v = p10 + (v_col0[1] - v_col1[1]) * u_tr
    p21 = p20 + (v_col0[2] - v_col1[2]) * u_tr
    p11 = (p11_u + p11_v) * 0.5
    p22 = ((p12 + (p21 - p11)) + (p21 + (p12 - p11))) * 0.5
    return [p00, p01, p02, p10, p11, p12, p20, p21, p22]


_CG66_MAP = [
    (0, 0), (0, 1), (0, 2), (1, 6), (1, 3), (1, 0),
    (0, 3), (0, 4), (0, 5), (1, 7), (1, 4), (1, 1),
    (0, 6), (0, 7), (0, 8), (1, 8), (1, 5), (1, 2),
    (3, 2), (3, 5), (3, 8), (2, 8), (2, 7), (2, 6),
    (3, 1), (3, 4), (3, 7), (2, 5), (2, 4), (2, 3),
    (3, 0), (3, 3), (3, 6), (2, 2), (2, 1), (2, 0),
]


def corner_grid(grids, tol=1e-6):
    pairs, mirrored = [], []
    for i in range(4):
        a, b = grids[i], grids[(i + 1) % 4]
        common = _pair_common(a[0], b[0], tol)
        if common is None:
            return None
        pairs.append(common)
        mirrored.append((common[1], common[0]))
    if all(c == _CORNER_COMMON for c in pairs):
        pass
    elif all(c == _CORNER_COMMON for c in mirrored):
        grids = [grids[0]] + list(reversed(grids[1:]))
    else:
        return None
    subgrids = []
    for i in range(4):
        s = _subgrid33(grids[i][0], grids[(i + 1) % 4][0], tol)
        if s is None:
            return None
        subgrids.append(s)
    poles, weights = [], []
    for si, k in _CG66_MAP:
        poles.append(subgrids[si][k])
        weights.append(1.0)
    return poles, weights


def current_corner_h(grids):
    flat = [_grid_flat(g)[0] for g in grids]
    p36, w36 = corner_grid([(f, [1.0] * 24) for f in flat])
    H = np.zeros((36, 4))
    for k in range(36):
        H[k] = [p36[k][0], p36[k][1], p36[k][2], 1.0]
    return H


# ---------------------------------------------------------------------------
# demo extraction (zipfile technique of test_triangular_member_calibration)
# ---------------------------------------------------------------------------

def _vec_list(z, fname):
    raw = z.read(fname)
    n = struct.unpack("<I", raw[:4])[0]
    flat = struct.unpack("<%dd" % (n * 3), raw[4:])
    return [np.array([flat[3 * i], flat[3 * i + 1], flat[3 * i + 2]])
            for i in range(n)]


def _float_list(z, fname):
    raw = z.read(fname)
    n = struct.unpack("<I", raw[:4])[0]
    return list(struct.unpack("<%dd" % n, raw[4:]))


def _prop(body, name):
    m = re.search(r'<Property name="%s"[^>]*>\s*<[A-Za-z:]+ '
                  r'(?:value|file)="([^"]*)"' % name, body)
    return m.group(1) if m else None


def _parse_objects(doc):
    out = {}
    for chunk in doc.split('<Object name="')[1:]:
        name, _, body = chunk.partition('"')
        out[name] = body.split("</Object>")[0]
    return out


class _Grid:
    def __init__(self, name, cls, poles, weights):
        self.name = name
        self.cls = cls
        self.poles = poles
        self.weights = weights


class _Corner:
    def __init__(self, name, poles, weights, grids):
        self.name = name
        self.poles = poles
        self.weights = weights
        self.grids = grids

    def current_surface(self):
        return NS.from_flat(self.poles, self.weights, 6, 6, K6, K6)


def load_demo():
    z = zipfile.ZipFile(DEMO)
    try:
        objs = _parse_objects(z.read("Document.xml").decode("utf-8",
                                                            "replace"))
        cls_of, grid_cache, cl_objs = {}, {}, {}
        for n, b in objs.items():
            m = re.search(r'module="ArachNURBS" class="([^"]+)"', b)
            cls_of[n] = m.group(1) if m else None
            cl_objs[n] = b

        def grid_by_name(n):
            if n not in grid_cache:
                b = cl_objs[n]
                grid_cache[n] = _Grid(n, cls_of[n],
                                      _vec_list(z, _prop(b, "Poles")),
                                      _float_list(z, _prop(b, "Weights")))
            return grid_cache[n]

        corners = []
        for n, b in objs.items():
            if cls_of[n] != "CubicSurface_66":
                continue
            gb = cl_objs[_prop(b, "Grid")]
            grids, seen = [], set()
            for i in range(4):
                sub = cl_objs[_prop(gb, "SubGrid_%d" % i)]
                for key in ("Grid_0", "Grid_1"):
                    g = grid_by_name(_prop(sub, key))
                    if g.name not in seen:
                        seen.add(g.name)
                        grids.append(g)
            corners.append(_Corner(n, _vec_list(z, _prop(gb, "Poles")),
                                   _float_list(z, _prop(gb, "Weights")),
                                   grids))
        return corners
    finally:
        z.close()


def _grid_rows(poles24):
    return [[poles24[r * 6 + u] for u in range(6)] for r in range(4)]


def _match_boundary_row(boundary, rows, tol=1e-6):
    for r in (0, 3):
        for rev in (False, True):
            if all(float(np.linalg.norm(rows[r][5 - k if rev else k]
                                        - boundary[k])) < tol
                   for k in range(6)):
                return r, rev
    return None


def _boundary_rows(corner_flat):
    return {"u0": [corner_flat[v * 6 + 0] for v in range(6)],
            "u1": [corner_flat[v * 6 + 5] for v in range(6)],
            "v0": [corner_flat[0 * 6 + u] for u in range(6)],
            "v1": [corner_flat[5 * 6 + u] for u in range(6)]}


def _hv(p, w):
    return np.array([float(p[0]) * w, float(p[1]) * w, float(p[2]) * w,
                     float(w)])


def _vec(h):
    return np.array([h[0] / h[3], h[1] / h[3], h[2] / h[3]])


def demo_aligned(corner):
    corner_flat = list(corner.poles)
    bounds = _boundary_rows(corner_flat)
    aligned, strips, detail, grid_by_seam = {}, {}, {}, {}
    for name, kind, fixed, inner in SEAMS:
        b = bounds[name]
        for g in corner.grids:
            rows = _grid_rows(list(g.poles))
            m = _match_boundary_row(b, rows)
            if m is None:
                continue
            r, rev = m
            gw = list(g.weights)
            grows = [[(rows[rr][u], gw[rr * 6 + u]) for u in range(6)]
                     for rr in range(4)]
            R3, R2, R1 = ((grows[0], grows[1], grows[2]) if r == 0
                          else (grows[3], grows[2], grows[1]))

            def al(row):
                return [row[5 - k if rev else k] for k in range(6)]

            aligned[name] = tuple(
                np.array([_hv(p, w) for (p, w) in al(R)]) for R in (R3, R2, R1))
            strips[name] = NS.from_flat(g.poles, g.weights, 6, 4, K6, K4)
            grid_by_seam[name] = g
            detail[name] = {"grid": g.name, "row": r, "rev": rev}
            break
    return aligned, strips, detail, grid_by_seam


def _demo_corner_row(corner_flat, kind, fixed, inner, offset):
    if kind == "column":
        base = (fixed + inner * offset) * 6
        return [corner_flat[base + t] for t in range(6)]
    return [corner_flat[t * 6 + (fixed + inner * offset)] for t in range(6)]


def demo_lambdas(corner, aligned):
    flat = list(corner.poles)
    out = {}
    for name, kind, fixed, inner in SEAMS:
        V3, V2, _V1 = aligned[name]
        b0 = _demo_corner_row(flat, kind, fixed, inner, 0)
        b1 = _demo_corner_row(flat, kind, fixed, inner, 1)
        lam = []
        for t in range(6):
            c = float(np.linalg.norm(b1[t] - b0[t]))
            n = float(np.linalg.norm(_vec(V2[t]) - _vec(V3[t])))
            lam.append(n / c if c > 1e-12 else 1.0)
        out[name] = np.array(lam)
    return out


# ---------------------------------------------------------------------------
# joint treatment: corner's 4 central poles + strip second-order rows
# ---------------------------------------------------------------------------

def joint_solve(corner, aligned, lambdas, strips_frozen, free_rows,
                n_st=9, n_iter=3):
    free_corner = _central_free()
    strip_vars = []
    for name, _k, _f, _i in SEAMS:
        g = strips_frozen.get(name)
        if g is None:
            continue
        for row in sorted(free_rows.get(g.name, ())):
            for u in range(6):
                for d in range(3):
                    var = (g.name, row, u, d)
                    if var not in strip_vars:
                        strip_vars.append(var)
    base_grids = {}
    for name, _k, _f, _i in SEAMS:
        g = strips_frozen.get(name)
        if g is not None:
            base_grids[g.name] = (g.poles, g.weights)

    def apply(x):
        gridp = {gn: ([np.array(p, dtype=float) for p in poles],
                      list(weights))
                 for gn, (poles, weights) in base_grids.items()}
        for i, (gn, row, u, d) in enumerate(strip_vars):
            gridp[gn][0][row * 6 + u][d] += x[12 + i]
        H = np.zeros((36, 4))
        H[:, 3] = 1.0
        for name, kind, fixed, inner in SEAMS:
            V3, V2, _V1 = aligned[name]
            c3 = V3[:, :3] / V3[:, 3:4]
            c2 = V2[:, :3] / V2[:, 3:4]
            lam = lambdas[name]
            for t in range(6):
                Ld = float(lam[t])
                k0 = (fixed * 6 + t) if kind == "column" else \
                    (t * 6 + fixed)
                k1 = (((fixed + inner) * 6 + t) if kind == "column"
                      else (t * 6 + (fixed + inner)))
                H[k0] = [c3[t][0], c3[t][1], c3[t][2], 1.0]
                b1 = c3[t] - (c2[t] - c3[t]) / Ld
                H[k1] = [b1[0], b1[1], b1[2], 1.0]
        for c, k in enumerate(free_corner):
            H[k, 0] = x[3 * c]
            H[k, 1] = x[3 * c + 1]
            H[k, 2] = x[3 * c + 2]
        surf = _h_to_surface(H)
        neighbours = {}
        for name, _k, _f, _i in SEAMS:
            g = strips_frozen.get(name)
            if g is None:
                continue
            pp, ww = gridp[g.name]
            neighbours[name] = NS.from_flat(pp, ww, 6, 4, K6, K4)
        return H, gridp, surf, neighbours

    def residual(x):
        _H, _g, surf, neighbours = apply(x)
        res = []
        for name, _kind, _fixed, _inner in SEAMS:
            nb = neighbours.get(name)
            if nb is None:
                continue
            ms = match_boundaries(surf, nb, tol=1e-5)
            if not ms:
                continue
            m = ms[0]
            rep = measure_edges(surf, m["edge_a"], m["reverse_a"],
                                nb, m["edge_b"], m["reverse_b"], n=n_st)
            res.extend(s["k_a"] - s["k_b"] for s in rep["samples"])
        return np.array(res)

    x = np.zeros(12 + len(strip_vars))
    for c, k in enumerate(free_corner):
        x[3 * c] = corner.poles[k][0]
        x[3 * c + 1] = corner.poles[k][1]
        x[3 * c + 2] = corner.poles[k][2]
    hist = []
    for _ in range(n_iter):
        r = residual(x)
        rmax = float(np.max(np.abs(r))) if len(r) else 0.0
        hist.append(rmax)
        if rmax < 1e-12:
            break
        J = np.zeros((len(r), len(x)))
        for j in range(len(x)):
            xp = x.copy()
            xp[j] += 1.0
            J[:, j] = residual(xp) - r
        delta, *_ = np.linalg.lstsq(J, -r, rcond=None)
        x = x + delta
    r = residual(x)
    rmax = float(np.max(np.abs(r))) if len(r) else 0.0
    H, gridp, surf, strips_after = apply(x)
    rep = measure_against(surf, strips_after, n=N_FINAL)
    return {"x": x, "max_residual": rmax, "report": rep,
            "grids_after": gridp, "base_grids": base_grids,
            "strip_vars": strip_vars}


def _mean_cell_edge(poles24):
    edges = []
    for r in range(4):
        for u in range(6):
            k = r * 6 + u
            if u < 5:
                edges.append(float(np.linalg.norm(poles24[k]
                                                  - poles24[k + 1])))
            if r < 3:
                edges.append(float(np.linalg.norm(poles24[k]
                                                  - poles24[k + 6])))
    return float(np.mean(edges))


def _fold_counts(poles0, w0, poles1, w1, seam_row, ns=21, nv=13):
    """(normal flips vs the stored surface, monotone violations)."""
    a = NS.from_flat(poles0, w0, 6, 4, K6, K4)
    b = NS.from_flat(poles1, w1, 6, 4, K6, K4)
    flips = 0
    for i in range(ns):
        u = i / (ns - 1.0)
        for j in range(nv):
            v = j / (nv - 1.0)
            _, Pau, Pav, _, _, _ = a.ders(u, v, order=1)
            wa = np.cross(Pau, Pav)
            _, Pbu, Pbv, _, _, _ = b.ders(u, v, order=1)
            wb = np.cross(Pbu, Pbv)
            if float(np.linalg.norm(wa)) < 1e-12 or \
                    float(np.linalg.norm(wb)) < 1e-12:
                continue
            if float(np.dot(wa, wb)) < 0.0:
                flips += 1
    bad = 0
    order = [0, 1, 2, 3] if seam_row == 0 else [3, 2, 1, 0]
    for u in range(6):
        pts = [poles1[r * 6 + u] for r in order]
        d = pts[3] - pts[0]
        nd = float(np.linalg.norm(d))
        if nd < 1e-12:
            continue
        d = d / nd
        ts = [float(np.dot(p - pts[0], d)) for p in pts]
        bad += sum(1 for i in range(3) if ts[i + 1] - ts[i] <= 0.0)
    return flips, bad




_CACHE = {}


def _analysis():
    """Everything, once: synthetic control + the four demo junctions."""
    if _CACHE:
        return _CACHE
    out = {}

    # synthetic compatible ring (control a)
    T = synthetic_truth()
    grids = synthetic_strips(T)
    strips = {name: _strip_surface_from_grid(grids[i])
              for i, name in enumerate(RING)}
    aligned = aligned_rows_from_grids(grids)
    truth = NS.from_flat([T[i][j] for j in range(6) for i in range(6)],
                         [1.0] * 36, 6, 6, K6, K6)
    out["syn_truth"] = max(measure_against(truth, strips, n=41)[n]["k_gap"]
                           for n, _k, _f, _i in SEAMS)
    out["syn_current"] = max(
        measure_against(_h_to_surface(current_corner_h(grids)), strips,
                        n=41)[n]["k_gap"] for n, _k, _f, _i in SEAMS)
    Hs, _info = solve_corner_h(strips, aligned,
                               current_h=current_corner_h(grids))
    out["syn_solved"] = max(
        measure_against(_h_to_surface(Hs), strips, n=N_FINAL)[n]["k_gap"]
        for n, _k, _f, _i in SEAMS)
    T_h = np.array([[T[i][j][0], T[i][j][1], T[i][j][2], 1.0]
                    for j in range(6) for i in range(6)])
    out["syn_poles_inf"] = float(np.max(np.abs(Hs - T_h)))

    # demo junctions
    res = {}
    for corner in load_demo():
        aligned, strips, detail, grid_by_seam = demo_aligned(corner)
        lambdas = demo_lambdas(corner, aligned)
        cur = corner.current_surface()
        cur41 = measure_against(cur, strips, n=41)
        cur_h = np.array([[w * p[0], w * p[1], w * p[2], w]
                          for p, w in zip(corner.poles, corner.weights)])
        Hs, info = solve_corner_h(strips, aligned, lambdas,
                                  current_h=cur_h)
        base_surf = _h_to_surface(Hs)
        base41 = measure_against(base_surf, strips, n=41)
        base401 = measure_against(base_surf, strips, n=N_FINAL)
        free_rows = {}
        for name, _k, _f, _i in SEAMS:
            g = detail[name]["grid"]
            r = detail[name]["row"]
            free_rows.setdefault(g, set()).add(2 if r == 0 else 1)
        treat = joint_solve(corner, aligned, lambdas, grid_by_seam,
                            free_rows, n_st=9, n_iter=3)
        rec = {"detail": detail, "cur41": cur41,
               "base41": base41, "base401": base401, "treat": treat,
               "base_residual": info["residual"],
               "motions": {}, "folds": {}, "members": {}}
        for name, _k, _f, _i in SEAMS:
            g = grid_by_seam[name]
            p1 = treat["grids_after"][g.name][0]
            motion = max(float(np.linalg.norm(a - b))
                         for a, b in zip(g.poles, p1))
            rec["motions"][name] = motion / _mean_cell_edge(g.poles)
            rec["folds"][name] = _fold_counts(g.poles, g.weights, p1,
                                              g.weights, detail[name]["row"])
            if g.cls == "ControlGrid64_3_1Grid44":
                spread0 = max(float(np.linalg.norm(g.poles[18 + j]
                                                   - g.poles[18]))
                              for j in range(6))
                spread1 = max(float(np.linalg.norm(p1[18 + j] - p1[18]))
                              for j in range(6))
                rec["members"][name] = (spread0, spread1)
        res[corner.name] = rec
    out["demo"] = res
    _CACHE.update(out)
    return _CACHE
