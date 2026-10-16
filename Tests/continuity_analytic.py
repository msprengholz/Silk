"""
Exact seam-continuity report from control nets (analytic arbiter for #97).

Companion to `Tests/g2_oracle.py`.  Where the oracle SAMPLES a supplied seam
correspondence and takes finite differences, this module evaluates the exact
control-net derivatives (`Tests/silk_nurbs.py`) at the same stations and
computes the same quantities:

  c0        max position gap                                  (mm)
  g1_deg    max angle between the two unit normals            (deg)
  k_gap     max |kappa_a - kappa_b|, normal curvature across  (1/mm)
  twist_gap max |tau_a - tau_b|, geodesic torsion             (1/mm)

`c0` additionally has a purely combinatorial form, `c0_controlnet`, which
compares homogeneous boundary control points and needs no evaluation at all.

WHICH CLAIM EACH NUMBER SUPPORTS.  `g1_deg` is a tangent-plane metric: two
surfaces normal to each other's tangent planes have g1_deg ~ 0 **whether or
not** their curvatures match.  A small `g1_deg` therefore cannot establish
G2.  G2 is the `k_gap` claim, and `k_gap` is only as good as the curvature
formula it comes from -- which is why the instrument carries a calibration
(`Tests/continuity_calibration.py`) with a known curvature jump.

DOMAIN.  Analytic surfaces are [0, 1] x [0, 1].  The four boundary edges
parametrise v (u0/u1) or u (v0/v1); `reverse` walks t -> 1 - t.
"""

import math

from FreeCAD import Base

import Tests.silk_nurbs as SN


def edge_seam(edge, reverse=False):
    """(callable t->(u,v), along_axis, across_axis) for one boundary edge."""
    if edge == "u0":
        return (lambda t: (0.0, 1.0 - t if reverse else t)), "v", "u"
    if edge == "u1":
        return (lambda t: (1.0, 1.0 - t if reverse else t)), "v", "u"
    if edge == "v0":
        return (lambda t: (1.0 - t if reverse else t, 0.0)), "u", "v"
    if edge == "v1":
        return (lambda t: (1.0 - t if reverse else t, 1.0)), "u", "v"
    raise ValueError("edge must be u0/u1/v0/v1, got %r" % (edge,))


def _unit(vec):
    length = vec.Length
    if length < 1e-15:
        return Base.Vector(0, 0, 0)
    return Base.Vector(vec.x / length, vec.y / length, vec.z / length)


def _safe(vec):
    return Base.Vector(vec.x, vec.y, vec.z)


def _dN_ds(ders, across, normal):
    """Exact dN/ds along the seam, N = unit(P_across x P_along)."""
    P, Pu, Pv, Puu, Puv, Pvv = ders
    if across == "u":
        # seam at u = const, v varies: dw/dt = Puv x Pv + Pu x Pvv
        dwdt = Puv.cross(Pv) + Pu.cross(Pvv)
        ta = Pv
    else:
        # seam at v = const, u varies: dw/dt = Puu x Pv + Pu x Puv
        dwdt = Puu.cross(Pv) + Pu.cross(Puv)
        ta = Pu
    w = Pu.cross(Pv)
    wlen = w.Length
    if wlen < 1e-15 or ta.Length < 1e-15:
        return Base.Vector(0, 0, 0)
    dwds = dwdt * (1.0 / ta.Length)
    dNds = (dwds - normal * normal.dot(dwds)) * (1.0 / wlen)
    return dNds


def measure_seam(surf_a, seam_a, across_a, surf_b, seam_b, across_b, n=21):
    """Exact analogue of `g2_oracle.measure_seam` for `NurbsSurface` inputs.

    `seam_a` / `seam_b` map t in [0, 1] to (u, v); the caller supplies the
    correspondence, including any reversal.  `across_a` / `across_b` are the
    parameter axis that leaves the seam.
    """
    out = {"c0": 0.0, "g1_deg": 0.0, "k_gap": 0.0, "twist_gap": 0.0,
           "samples": []}
    if n < 2:
        raise ValueError("n must be >= 2")
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

        na = _unit(da.cross(ta))
        nb = _unit(db.cross(tb))
        if na.dot(nb) < 0.0:
            nb = -1.0 * nb

        c0 = (Pa - Pb).Length
        g1 = math.degrees(math.acos(max(-1.0, min(1.0, na.dot(nb)))))

        da_perp = da - ta_hat * da.dot(ta_hat)
        db_perp = db - tb_hat * db.dot(tb_hat)
        kappa_a = dda.dot(na) / (da_perp.Length ** 2) \
            if da_perp.Length > 1e-12 else 0.0
        kappa_b = ddb.dot(nb) / (db_perp.Length ** 2) \
            if db_perp.Length > 1e-12 else 0.0

        e_across = _unit(da_perp)
        tau_a = -_dN_ds((Pa, Pau, Pav, Pauu, Pauuv, Pavv),
                        across_a, na).dot(e_across)
        tau_b = -_dN_ds((Pb, Pbu, Pbv, Pbuu, Pbuuv, Pbvv),
                        across_b, nb).dot(e_across)

        out["c0"] = max(out["c0"], c0)
        out["g1_deg"] = max(out["g1_deg"], g1)
        out["k_gap"] = max(out["k_gap"], abs(kappa_a - kappa_b))
        out["twist_gap"] = max(out["twist_gap"], abs(tau_a - tau_b))
        out["samples"].append(
            {"t": t, "c0": c0, "g1_deg": g1,
             "k_a": kappa_a, "k_b": kappa_b, "k_gap": abs(kappa_a - kappa_b),
             "twist_gap": abs(tau_a - tau_b)})
    return out


def measure_edges(surf_a, edge_a, reverse_a, surf_b, edge_b, reverse_b, n=21):
    """`measure_seam` for two named boundary edges (orientation by `reverse`).

    `reverse_b` is relative to `edge_b`'s own natural order.  The caller
    chooses the pair so the two edges name the same geometric curve.
    """
    seam_a, _along_a, across_a = edge_seam(edge_a, reverse_a)
    seam_b, _along_b, across_b = edge_seam(edge_b, reverse_b)
    return measure_seam(surf_a, seam_a, across_a, surf_b, seam_b, across_b, n)


# ---------------------------------------------------------------------------
# automated seam pairing from the control nets
# ---------------------------------------------------------------------------

def _close(a, b, tol):
    """True if two homogeneous boundary nets agree componentwise within tol."""
    if len(a) != len(b):
        return False
    return all(max(abs(a[i][k] - b[i][k]) for k in range(4)) < tol
               for i in range(len(a)))


def match_boundaries(surf_a, surf_b, tol=1e-7):
    """Find boundary edges of `surf_a` and `surf_b` that coincide.

    Returns a list of dicts {edge_a, edge_b, reverse_a, reverse_b} such that
    edge_a (walked possibly reversed) names the same rational cubic as
    edge_b.  Compares normalised homogeneous boundary control points, so a
    matching rational parameterisation is recognised regardless of weight
    scale.
    """
    out = []
    for ea in ("u0", "u1", "v0", "v1"):
        for ra in (False, True):
            ha = SN.homogeneous_boundary(surf_a, ea, reverse=ra)
            for eb in ("u0", "u1", "v0", "v1"):
                hb = SN.homogeneous_boundary(surf_b, eb, reverse=False)
                if _close(ha, hb, tol):
                    out.append({"edge_a": ea, "edge_b": eb,
                                "reverse_a": ra, "reverse_b": False})
    return out
