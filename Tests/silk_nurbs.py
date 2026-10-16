"""
Exact NURBS control-net evaluation for the Silk corner continuity instrument.

Ticket #97, deliverable 2 ("analytic-first").  Silk's surfaces are bicubic
with explicit control nets and a fixed knot layout, so the geometry at and
across a seam is a **control-net condition**.  This module evaluates a
Silk-style surface directly from its control net -- no `solve_uv`, no finite
differences -- and hands back exact positions and derivatives.  Continuity
across a seam is then read off those derivatives (`Tests/continuity_analytic.py`),
and the C0 condition is read off the control net itself, combinatorially.

WHY THIS EXISTS.  `Tests/g2_oracle.py` measures continuity by sampling a
supplied seam correspondence and taking finite differences.  That is a sound
*instrument* but it is not self-evidently correct: it has a step size, a
solver-free parameter correspondence the caller must supply, and a curvature
formula.  This module is the arbiter -- it computes the same quantities from
the control net, exactly, so the sampled instrument can be checked against it
on a known answer.

WEIGHTS ARE CARRIED.  The control net is stored in homogeneous form
`(w*P, w)`; rational evaluation is the quotient rule on those homogeneous
sums, so a rational surface (which `ArachNURBS.blend_poly_2x4_1x6` can emit)
is handled exactly.  An unweighted check of a rational surface is not exact.

PARAMETER DOMAIN.  `Part.BSplineSurface` produced by Silk's
`NURBS_Cubic_*_surf` helpers always has the domain [0, 1] x [0, 1] (the knot
vectors are 0..1).  This module assumes that, like `Tests/g2_oracle.py`
reads each surface's own domain.

NO FreeCAD GUI, no `ArachNURBS` import -- this file is a leaf, so it reloads
cleanly and can run under `freecadcmd`.
"""

import math

from FreeCAD import Base

# The knot layout Silk's `NURBS_Cubic_66_surf` / `NURBS_Cubic_64_surf` use
# along the 6-control-point direction (uniform cubic B-spline, 3 Bezier
# spans).  The 4-control-point direction is a plain cubic Bezier.
KNOTS_6 = [0.0, 0.0, 0.0, 0.0, 1.0 / 3, 2.0 / 3, 1.0, 1.0, 1.0, 1.0]
KNOTS_4 = [0.0, 0.0, 0.0, 0.0, 1.0, 1.0, 1.0, 1.0]

# Span boundaries of KNOTS_6 (used to report the seam station grid).
SPANS_6 = ((0.0, 1.0 / 3), (1.0 / 3, 2.0 / 3), (2.0 / 3, 1.0))


# ---------------------------------------------------------------------------
# basis functions (Piegl & Tiller, The NURBS Book, A2.3 / A2.4)
# ---------------------------------------------------------------------------

def find_span(n, p, u, knots):
    """Index i such that knots[i] <= u < knots[i+1] (u inside the domain).

    `n` is the last control-point index (len(poles) - 1), `p` the degree.
    """
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


def basis_derivatives(span, u, p, knots, order=2):
    """ders[k][j] = d^k/du^k of the j-th local basis over `span`, k <= order."""
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
    # multiply by p!/(p-k)!
    fac = 1.0
    for k in range(1, order + 1):
        fac *= (p - k + 1)
        for j in range(p + 1):
            ders[k][j] *= fac
    return ders


def _binomial(n, k):
    return math.factorial(n) // (math.factorial(k) * math.factorial(n - k))


# ---------------------------------------------------------------------------
# the surface
# ---------------------------------------------------------------------------

class NurbsSurface:
    """A rational tensor-product NURBS surface held as a control net.

    `poles` is [u][v] of `Base.Vector`; `weights` is [u][v] of float;
    `knots_u` / `knots_v` are the (non-decreasing) knot vectors; the degree
    is len of the clamped ends minus one, but is passed explicitly because
    Silk's knots are always clamped cubic.
    """

    def __init__(self, poles, weights, knots_u=KNOTS_6, knots_v=KNOTS_6,
                 degree_u=3, degree_v=3):
        self.poles = [[Base.Vector(p.x, p.y, p.z) for p in col]
                      for col in poles]
        self.weights = [list(w) for w in weights]
        self.knots_u = list(knots_u)
        self.knots_v = list(knots_v)
        self.degree_u = degree_u
        self.degree_v = degree_v
        self.nu = len(poles)
        self.nv = len(poles[0])
        # homogeneous control net: (w*P, w)
        self.hom = [[[self.weights[u][v] * self.poles[u][v].x,
                      self.weights[u][v] * self.poles[u][v].y,
                      self.weights[u][v] * self.poles[u][v].z,
                      self.weights[u][v]]
                     for v in range(self.nv)] for u in range(self.nu)]

    # -- builders -----------------------------------------------------------

    @classmethod
    def from_flat(cls, poles_flat, weights_flat, nu, nv,
                  knots_u=KNOTS_6, knots_v=KNOTS_6, degree_u=3, degree_v=3):
        """Build from Silk's flat v-major list: index = v*nu + u.

        This is the order `NURBS_Cubic_66_surf` / `NURBS_Cubic_64_surf`
        read (`for v: for u: setPole(u+1, v+1, ...)`).
        """
        poles = [[poles_flat[v * nu + u] for v in range(nv)]
                 for u in range(nu)]
        weights = [[weights_flat[v * nu + u] for v in range(nv)]
                   for u in range(nu)]
        return cls(poles, weights, knots_u, knots_v, degree_u, degree_v)

    @classmethod
    def from_object(cls, obj):
        """Build from a `CubicSurface_*` object's stored control grid.

        Reads `obj.Grid.Poles` / `.Weights` (Silk's flat v-major control
        net) with the knot layout implied by the object's own `Shape`
        surface when available.  Keeps the weights, unlike reading the
        generated OCCT surface's poles.
        """
        grid = obj.Grid
        flat = list(grid.Poles)
        weights = list(grid.Weights) if getattr(grid, "Weights", None) else \
            [1.0] * len(flat)
        surf = obj.Shape.Faces[0].Surface
        nu = surf.NbUPoles
        nv = surf.NbVPoles
        ku = list(surf.UKnotSequence)
        kv = list(surf.VKnotSequence)
        return cls.from_flat(flat, weights, nu, nv, ku, kv)

    def to_bspline(self):
        """A `Part.BSplineSurface` with the same poles, weights and knots.

        Built the way Silk's `NURBS_Cubic_*_surf` helpers build theirs
        (`increaseDegree(3, 3)` then insert every knot once), so the result
        is directly comparable to a `CubicSurface_*`'s `Shape.Surface`.
        """
        import Part

        s = Part.BSplineSurface()
        s.increaseDegree(self.degree_u, self.degree_v)
        for kn in self.knots_u:
            s.insertUKnot(kn, 1, 1e-9)
        for kn in self.knots_v:
            s.insertVKnot(kn, 1, 1e-9)
        for u in range(self.nu):
            for v in range(self.nv):
                s.setPole(u + 1, v + 1, self.poles[u][v], self.weights[u][v])
        return s

    # -- exact evaluation ---------------------------------------------------

    def value(self, u, v):
        p, _, _, _, _, _ = self.ders(u, v, order=0)
        return p

    def ders(self, u, v, order=2):
        """Exact derivatives: (P, Pu, Pv, Puu, Puv, Pvv).

        `order` controls how many derivative orders are computed; the tuple
        always has the six slots, missing ones being zero vectors.
        """
        pu, pv = self.degree_u, self.degree_v
        su = find_span(self.nu - 1, pu, u, self.knots_u)
        sv = find_span(self.nv - 1, pv, v, self.knots_v)
        du = basis_derivatives(su, u, pu, self.knots_u, order)
        dv = basis_derivatives(sv, v, pv, self.knots_v, order)

        # homogeneous surface derivatives SKL[k][l] (4-vectors)
        SKL = [[[0.0, 0.0, 0.0, 0.0] for _ in range(order + 1)]
               for _ in range(order + 1)]
        for k in range(order + 1):
            for l in range(order + 1):
                acc = [0.0, 0.0, 0.0, 0.0]
                for i in range(pu + 1):
                    di = du[k][i] if k <= order else 0.0
                    if di == 0.0:
                        continue
                    iu = su - pu + i
                    for j in range(pv + 1):
                        dj = dv[l][j] if l <= order else 0.0
                        if dj == 0.0:
                            continue
                        jv = sv - pv + j
                        h = self.hom[iu][jv]
                        w = di * dj
                        acc[0] += w * h[0]
                        acc[1] += w * h[1]
                        acc[2] += w * h[2]
                        acc[3] += w * h[3]
                SKL[k][l] = acc

        w00 = SKL[0][0][3]
        # rational surface derivatives, Piegl & Tiller A4.4 (A3.6 + quotient)
        S = [[Base.Vector(0, 0, 0) for _ in range(order + 1)]
             for _ in range(order + 1)]
        for k in range(order + 1):
            for l in range(order + 1):
                acc = Base.Vector(SKL[k][l][0], SKL[k][l][1], SKL[k][l][2])
                for j in range(1, l + 1):
                    acc = acc - S[k][l - j] * (_binomial(l, j) * SKL[0][j][3])
                for i in range(1, k + 1):
                    acc = acc - S[k - i][l] * (_binomial(k, i) * SKL[i][0][3])
                    for j in range(1, l + 1):
                        acc = acc - S[k - i][l - j] * (
                            _binomial(k, i) * _binomial(l, j) * SKL[i][j][3])
                S[k][l] = acc * (1.0 / w00)

        P = S[0][0]
        Pu = S[1][0] if order >= 1 else Base.Vector(0, 0, 0)
        Pv = S[0][1] if order >= 1 else Base.Vector(0, 0, 0)
        Puu = S[2][0] if order >= 2 else Base.Vector(0, 0, 0)
        Puv = S[1][1] if order >= 2 else Base.Vector(0, 0, 0)
        Pvv = S[0][2] if order >= 2 else Base.Vector(0, 0, 0)
        return P, Pu, Pv, Puu, Puv, Pvv

    def normal(self, u, v):
        _, Pu, Pv, _, _, _ = self.ders(u, v, order=1)
        n = Pu.cross(Pv)
        length = n.Length
        if length < 1e-15:
            return Base.Vector(0, 0, 0)
        return Base.Vector(n.x / length, n.y / length, n.z / length)

    # -- boundary control net ----------------------------------------------

    def boundary(self, edge):
        """The boundary control points as a list of (P, w) along the edge."""
        if edge == "u0":
            return [(self.poles[0][v], self.weights[0][v])
                    for v in range(self.nv)]
        if edge == "u1":
            return [(self.poles[self.nu - 1][v], self.weights[self.nu - 1][v])
                    for v in range(self.nv)]
        if edge == "v0":
            return [(self.poles[u][0], self.weights[u][0])
                    for u in range(self.nu)]
        if edge == "v1":
            return [(self.poles[u][self.nv - 1], self.weights[u][self.nv - 1])
                    for u in range(self.nu)]
        raise ValueError("edge must be u0/u1/v0/v1, got %r" % (edge,))

    def opposite(self, edge):
        return {"u0": "u1", "u1": "u0", "v0": "v1", "v1": "v0"}[edge]


# ---------------------------------------------------------------------------
# combinatorial C0 across a seam
# ---------------------------------------------------------------------------

def homogeneous_boundary(surface, edge, reverse=False):
    """Boundary control points in homogeneous form, normalised per point.

    Each entry is (w*P / w_ref, w / w_ref) with `w_ref` the edge's first
    weight, so two parameterisations of the SAME rational curve compare
    equal regardless of a common scale factor.  Returns a list of 4-tuples.
    """
    b = surface.boundary(edge)
    if reverse:
        b = list(reversed(b))
    if not b:
        return []
    wref = b[0][1]
    out = []
    for p, w in b:
        out.append((w * p.x / wref, w * p.y / wref, w * p.z / wref, w / wref))
    return out


def c0_controlnet(surface_a, edge_a, surface_b, edge_b, reverse=False):
    """Max heterogeneous distance between two matching boundary control nets.

    A sufficient (and, for equal knots and a matched parameterisation,
    necessary) C0 condition: if the normalised homogeneous boundary control
    points coincide exactly, the two boundary curves are the same rational
    curve.  No sampling, no solver -- this is the control-net statement.

    Returns (max_gap_mm, per_point_gaps).
    """
    ha = homogeneous_boundary(surface_a, edge_a, reverse=False)
    hb = homogeneous_boundary(surface_b, edge_b, reverse=reverse)
    if len(ha) != len(hb):
        raise ValueError("boundary control nets differ in length: %d vs %d"
                         % (len(ha), len(hb)))
    gaps = []
    for a, b in zip(ha, hb):
        d = math.sqrt(sum((a[i] - b[i]) ** 2 for i in range(4)))
        gaps.append(d)
    return (max(gaps) if gaps else 0.0), gaps
