"""
G2 continuity oracle for two adjacent NURBS surfaces sharing a boundary curve.

MEASUREMENT ONLY -- no production geometry is modified. Ticket #91 Phase A.

Given two surfaces that are supposed to meet along a common seam, sample the
seam at N stations and quantify, per station:

  C0  -- position gap        |pA - pB|                              (mm)
  G1  -- tangent-plane gap   angle between the two unit normals      (deg)
  G2  -- curvature gap       |kappaA - kappaB| where kappa is the normal
                             curvature in the direction PERPENDICULAR to
                             the seam, plus the geodesic-torsion gap.

`kappa` is II(e, e), the normal curvature with e the unit tangent-plane
direction that crosses the seam, taken geometrically from surface A, so a
matching pair reports ~0 and a curvature discontinuity reports the real
difference. Domain-aware: seam callables use each surface's own (possibly
non-[0,1]) parameter domain, which `Part.BSplineSurface.segment` produces.

Nothing here is labelled by intent -- the numbers are the evidence.
"""

import math

from FreeCAD import Base

_H_FIRST = 1e-5
_H_SECOND = 1e-4


# ---------------------------------------------------------------------------
# numerical derivatives (one-sided at the domain edge)
# ---------------------------------------------------------------------------

def domain(surf):
    """(umin, umax, vmin, vmax) of a Part.BSplineSurface."""
    uk = surf.UKnotSequence
    vk = surf.VKnotSequence
    return (uk[0], uk[-1], vk[0], vk[-1])


def _pd(surf, u, v, axis, h=_H_FIRST):
    """First derivative in `axis` ('u' or 'v') at (u, v)."""
    p = surf.value
    umin, umax, vmin, vmax = domain(surf)
    if axis == "u":
        if u <= umin + h:
            return (p(u + h, v) - p(u, v)) / h
        if u >= umax - h:
            return (p(u, v) - p(u - h, v)) / h
        return (p(u + h, v) - p(u - h, v)) / (2.0 * h)
    if v <= vmin + h:
        return (p(u, v + h) - p(u, v)) / h
    if v >= vmax - h:
        return (p(u, v) - p(u, v - h)) / h
    return (p(u, v + h) - p(u, v - h)) / (2.0 * h)


def _p2d(surf, u, v, axis, h=_H_SECOND):
    """Second derivative in `axis` at (u, v)."""
    p = surf.value
    umin, umax, vmin, vmax = domain(surf)
    if axis == "u":
        if u <= umin + 2 * h:
            return (p(u + 2 * h, v) - 2.0 * p(u + h, v) + p(u, v)) / (h * h)
        if u >= umax - 2 * h:
            return (p(u, v) - 2.0 * p(u - h, v) + p(u - 2 * h, v)) / (h * h)
        return (p(u + h, v) - 2.0 * p(u, v) + p(u - h, v)) / (h * h)
    if v <= vmin + 2 * h:
        return (p(u, v + 2 * h) - 2.0 * p(u, v + h) + p(u, v)) / (h * h)
    if v >= vmax - 2 * h:
        return (p(u, v) - 2.0 * p(u, v - h) + p(u, v - 2 * h)) / (h * h)
    return (p(u, v + h) - 2.0 * p(u, v) + p(u, v - h)) / (h * h)


def _unit(vec):
    length = vec.Length
    if length < 1e-15:
        return Base.Vector(0, 0, 0)
    return Base.Vector(vec.x / length, vec.y / length, vec.z / length)


def _safe(v):
    return Base.Vector(v.x, v.y, v.z)


# ---------------------------------------------------------------------------
# seam callables for the four boundary edges of a surface
# ---------------------------------------------------------------------------

def edge_seam(surf, edge, reverse=False):
    """Return (seam_callable, across_axis) for one boundary edge.

    edge is 'u0', 'u1', 'v0' or 'v1'. The callable maps t in [0, 1] onto the
    edge within the surface's own parameter domain; `reverse` walks it
    t -> 1 - t so a caller can match the opposite surface's direction.
    """
    umin, umax, vmin, vmax = domain(surf)

    def f(t):
        s = 1.0 - t if reverse else t
        if edge == "u0":
            return (umin, vmin + s * (vmax - vmin))
        if edge == "u1":
            return (umax, vmin + s * (vmax - vmin))
        if edge == "v0":
            return (umin + s * (umax - umin), vmin)
        if edge == "v1":
            return (umin + s * (umax - umin), vmax)
        raise ValueError("edge must be u0/u1/v0/v1, got %r" % (edge,))
    return f, ("u" if edge.startswith("u") else "v")


# ---------------------------------------------------------------------------
# the oracle
# ---------------------------------------------------------------------------

def measure_seam(surf_a, seam_a, across_a, surf_b, seam_b, across_b, n=21):
    """Quantify continuity between two surfaces along a shared seam.

    `seam_a` / `seam_b` are callables t in [0, 1] -> (u, v) naming the SAME
    geometric seam point on each surface (the caller supplies the
    correspondence, including any reversal).
    `across_a` / `across_b` are 'u' or 'v': the surface parameter direction
    that leaves the seam.

    Returns maxima and the per-station samples:
      c0            max position gap (mm)
      g1_deg        max angle between the two unit normals (deg)
      k_gap         max |kappa_a - kappa_b| (1/mm)  -- cross normal curvature
      twist_gap     max |tau_a - tau_b| (1/mm)      -- geodesic torsion gap
    """
    out = {"c0": 0.0, "g1_deg": 0.0, "k_gap": 0.0, "twist_gap": 0.0,
           "samples": []}
    dt = 1e-5
    for k in range(n):
        t = k / (n - 1.0)
        ua, va = seam_a(t)
        ub, vb = seam_b(t)

        pa = surf_a.value(ua, va)
        pb = surf_b.value(ub, vb)

        t0 = max(0.0, t - dt)
        t1 = min(1.0, t + dt)

        ua0, va0 = seam_a(t0)
        ua1, va1 = seam_a(t1)
        ta = _safe(surf_a.value(ua1, va1) - surf_a.value(ua0, va0))
        ub0, vb0 = seam_b(t0)
        ub1, vb1 = seam_b(t1)
        tb = _safe(surf_b.value(ub1, vb1) - surf_b.value(ub0, vb0))

        da = _safe(_pd(surf_a, ua, va, across_a))
        dda = _safe(_p2d(surf_a, ua, va, across_a))
        db = _safe(_pd(surf_b, ub, vb, across_b))
        ddb = _safe(_p2d(surf_b, ub, vb, across_b))

        ta_hat = _unit(ta)
        tb_hat = _unit(tb)

        na = _unit(da.cross(ta))
        nb = _unit(db.cross(tb))
        if na.dot(nb) < 0.0:          # orient both normals to the same side
            nb = -1.0 * nb

        g1 = math.degrees(math.acos(max(-1.0, min(1.0, na.dot(nb)))))
        c0 = (pa - pb).Length

        # across direction perpendicular to the seam in the tangent plane
        da_perp = da - ta_hat * da.dot(ta_hat)
        db_perp = db - tb_hat * db.dot(tb_hat)

        kappa_a = dda.dot(na) / (da_perp.Length ** 2) \
            if da_perp.Length > 1e-12 else 0.0
        kappa_b = ddb.dot(nb) / (db_perp.Length ** 2) \
            if db_perp.Length > 1e-12 else 0.0

        # geodesic torsion: -(dN/ds_along) . e_across, arc-length normalised.
        # N(t) is the unit normal field along the seam; e_across is the
        # geometric across direction (taken from A, the same for both sides).
        e_across = _unit(da_perp)
        sign_b = 1.0 if na.dot(nb) > 0 else -1.0
        dt2 = 1e-4
        ta_ = max(0.0, t - dt2)
        tb_ = min(1.0, t + dt2)
        dtm = tb_ - ta_

        def _normal_and_dNdt(surf, seam, across, sign):
            ua_, va_ = seam(ta_)
            ub_, vb_ = seam(tb_)
            ttan = _safe(surf.value(ub_, vb_) - surf.value(ua_, va_))
            du0 = _safe(_pd(surf, ua_, va_, across))
            du1 = _safe(_pd(surf, ub_, vb_, across))
            n0 = _unit(du0.cross(ttan)) * sign
            n1 = _unit(du1.cross(ttan)) * sign
            if n0.dot(n1) < 0.0:
                n1 = -1.0 * n1
            return (n1 - n0) / dtm

        dna = _normal_and_dNdt(surf_a, seam_a, across_a, 1.0)
        dnb = _normal_and_dNdt(surf_b, seam_b, across_b, sign_b)
        speed = ta.Length / (t1 - t0) if (t1 - t0) > 0 else 0.0
        tau_a = -dna.dot(e_across) / speed if speed > 1e-12 else 0.0
        tau_b = -dnb.dot(e_across) / speed if speed > 1e-12 else 0.0

        out["c0"] = max(out["c0"], c0)
        out["g1_deg"] = max(out["g1_deg"], g1)
        out["k_gap"] = max(out["k_gap"], abs(kappa_a - kappa_b))
        out["twist_gap"] = max(out["twist_gap"], abs(tau_a - tau_b))
        out["samples"].append(
            {"t": t, "c0": c0, "g1_deg": g1,
             "k_a": kappa_a, "k_b": kappa_b, "k_gap": abs(kappa_a - kappa_b),
             "twist_gap": abs(tau_a - tau_b)})
    return out


def classify(report, c0_tol=1e-4, g1_deg_tol=0.5, k_abs_tol=5e-5, k_rel_tol=0.05):
    """Turn a `measure_seam` report into a continuity label.

    Thresholds are explicit and are printed alongside the label. Curvature is
    compared on an absolute scale (1/mm): the corner patches here are ~100 mm
    features, so k_abs_tol = 5e-5 /mm is well below any real curvature.
    """
    if report["c0"] > c0_tol:
        return "C-1 (gap)"
    if report["g1_deg"] > g1_deg_tol:
        return "C0"
    kmax = max((abs(s["k_a"]) for s in report["samples"]), default=0.0)
    scale = max(k_abs_tol, k_rel_tol * kmax)
    if report["k_gap"] > scale:
        return "G1"
    return "G2+"
