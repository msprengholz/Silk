"""
Instrument soundness for the azimuth continuity oracle (ticket #97, deliverable 1).

The corner continuity claim is only as good as the instrument that produces
it.  This module calibrates the two instruments -- `Tests/g2_oracle.py`
(sampled, finite-difference) and `Tests/continuity_analytic.py` (exact
control-net) -- against geometry whose answer is known in closed form, and
against an independent cross-check that shares none of their assumptions.

WHAT IS MEASURED
  1. `solve_uv` (from `Tests/g2_corner_fill_probe.py`) on analytic surfaces
     with exact (u, v): residual and parameter recovery.
  2. The error floor of every reported quantity -- c0, g1_deg, k_gap,
     twist_gap -- on a pair of IDENTICAL surfaces, where the true answer is
     0 in every slot.
  3. A known G1 angle: two planes meeting at a dihedral theta.  Both
     instruments must report theta.
  4. A known curvature jump: two parabolic cylinders meeting tangent-plane
     continuous (g1_deg = 0) with normal curvature 2a and 2b.  Both
     instruments must report k_gap = 2|a - b|.  This is also the proof that
     g1_deg CANNOT establish G2 -- g1_deg is ~0 while k_gap is large.
  5. An independent cross-check: the 3D deviation between surface A and
     surface B via OCCT `distToShape`, which knows nothing about either
     instrument's basis or solver.  For a G1 seam the deviation grows like
     delta^2 with the across offset delta; for a C0 seam like delta^1.
  6. `twist_gap`'s frame (#101): ONE C-infinity seam that carries a real
     geodesic torsion, measured with the caller's correspondence matched and
     reversed.  The truth is 0 in both readings, and neither instrument may
     report more -- the defect this pins read 2|tau| (~2 /mm here) on a seam
     whose curvature gap was 1e-16.

The floor from (2) is the smallest number either instrument can honestly
report; nothing below it is a measurement.  The parabolic pair of (2) has
zero torsion along its seam (a cylinder's normal does not turn along the
axis), so the floor of `twist_gap` is NOT evidence about the torsion frame --
(6) is, and it carries the positive control.
"""

import math

import Part
from FreeCAD import Base

import Tests.silk_nurbs as SN
import Tests.continuity_analytic as CA
from Tests import g2_oracle as G


# ---------------------------------------------------------------------------
# analytic surfaces with known continuity
# ---------------------------------------------------------------------------

def _u_coords():
    return [0.0, 1.0 / 3, 2.0 / 3, 1.0]


def parab_surface(a, mirrored=False):
    """z = a*u^2 over (u, v) in [0, 1]^2, as an exact bicubic Bezier patch.

    `mirrored=True` puts it on the -u side: (-u, v, a*u^2), so two such
    patches share the u=0 seam as a real pair.  Normal curvature in the
    across (u) direction at the seam is 2a.
    """
    xs = _u_coords()
    zs = [0.0, 0.0, 1.0 / 3, 1.0]
    poles = []
    for iu in range(4):
        col = []
        for iv in range(4):
            x = -xs[iu] if mirrored else xs[iu]
            col.append(Base.Vector(x, xs[iv], a * zs[iu]))
        poles.append(col)
    return SN.NurbsSurface(poles, [[1.0] * 4 for _ in range(4)],
                           SN.KNOTS_4, SN.KNOTS_4)


def plane_surface(theta, mirrored=False):
    """Plane z = 0 (theta = 0) tilted about the u=0 seam by theta radians."""
    xs = _u_coords()
    c, s = math.cos(theta), math.sin(theta)
    poles = []
    for iu in range(4):
        col = []
        for iv in range(4):
            x = -xs[iu] if mirrored else xs[iu]
            col.append(Base.Vector(-c * x, xs[iv], -s * x))
        poles.append(col)
    return SN.NurbsSurface(poles, [[1.0] * 4 for _ in range(4)],
                           SN.KNOTS_4, SN.KNOTS_4)


def flat_plane():
    xs = _u_coords()
    poles = [[Base.Vector(xs[iu], xs[iv], 0.0) for iv in range(4)]
             for iu in range(4)]
    return SN.NurbsSurface(poles, [[1.0] * 4 for _ in range(4)],
                           SN.KNOTS_4, SN.KNOTS_4)


def _pair_bsplines(sa, sb):
    return sa.to_bspline(), sb.to_bspline()


def hpar_surface(mirrored=False, flip_v=False):
    """z = u*v over (u, v) in [0, 1]^2, as an exact bicubic Bezier patch.

    The hyperbolic paraboloid is a bilinear polynomial, so four control
    points per axis represent it exactly.  `mirrored=True` puts it on the -u
    side: (-u, v, -u*v) -- the same surface continued across u = 0, so a
    mirrored pair meets on a seam that is smooth to all orders.  `flip_v`
    swaps v -> 1 - v, which reverses the patch's NATURAL along-seam axis
    without moving the surface: that is one side of a reversed seam
    correspondence (#101).

    Unlike `parab_surface`, the normal TURNS along the seam: the geodesic
    torsion at the u = 0 seam is ~1 /mm, so a torsion metric that reads 0
    here is blind rather than right.
    """
    xs = _u_coords()
    poles = []
    for iu in range(4):
        col = []
        for iv in range(4):
            x = -xs[iu] if mirrored else xs[iu]
            y = (1.0 - xs[iv]) if flip_v else xs[iv]
            col.append(Base.Vector(x, y, x * y))
        poles.append(col)
    return SN.NurbsSurface(poles, [[1.0] * 4 for _ in range(4)],
                           SN.KNOTS_4, SN.KNOTS_4)


# ---------------------------------------------------------------------------
# (1) solve_uv soundness
# ---------------------------------------------------------------------------

def solve_uv_soundness(surf, prange=(0.0, 1.0, 0.0, 1.0), n=5, grid=30):
    """Solve (u, v) for points taken at known (u, v) on `surf`.

    Returns max position residual (mm) and max parameter error.  For a
    surface that is not injective (a plane) the parameter error is
    meaningless; callers pass a curved surface.
    """
    from Tests.g2_corner_fill_probe import solve_uv

    max_res = 0.0
    max_du = 0.0
    max_dv = 0.0
    for k in range(n):
        t = k / (n - 1.0)
        for m in range(n):
            u = t
            v = m / (n - 1.0)
            p = surf.value(u, v)
            su, sv, res = solve_uv(surf, p, prange, grid=grid)
            max_res = max(max_res, res)
            max_du = max(max_du, abs(su - u))
            max_dv = max(max_dv, abs(sv - v))
    return {"max_residual": max_res, "max_du": max_du, "max_dv": max_dv}


def sample_solve_uv(n=5):
    """solve_uv against (a) an exact bicubic patch and (b) a planar patch."""
    patch = parab_surface(1.0)
    plane = flat_plane()
    out = {"bicubic": solve_uv_soundness(patch.to_bspline(), n=n)}
    # a plane is not injective in (u, v); the residual is still meaningful
    r = solve_uv_soundness(plane.to_bspline(), n=n)
    out["plane"] = {"max_residual": r["max_residual"]}
    return out


# ---------------------------------------------------------------------------
# (2) error floor
# ---------------------------------------------------------------------------

def error_floor(n=41):
    """Both instruments on the C-infinity seam of ONE curved surface.

    `parab_surface(1.0)` and `parab_surface(1.0, mirrored=True)` are the two
    halves of the smooth paraboloid z = u^2: the seam is continuous to all
    orders, so every metric's true value is 0 while each surface is a
    genuinely different control net.  The reported numbers are the floor of
    each quantity -- nothing below them is a measurement.
    """
    a = parab_surface(1.0)
    b = parab_surface(1.0, mirrored=True)
    ba, bb = _pair_bsplines(a, b)
    sampled = G.measure_seam(ba, lambda t: (0.0, t), "u",
                             bb, lambda t: (0.0, t), "u", n=n)
    exact = CA.measure_seam(a, lambda t: (0.0, t), "u",
                            b, lambda t: (0.0, t), "u", n=n)
    out = {}
    for key in ("c0", "g1_deg", "k_gap", "twist_gap"):
        out[key] = {"sampled": sampled[key], "analytic": exact[key]}
    degen = G.measure_seam(ba, lambda t: (0.0, t), "u",
                           ba, lambda t: (0.0, t), "u", n=n)
    out["_degenerate"] = {k: degen[k] for k in ("c0", "g1_deg", "k_gap",
                                                "twist_gap")}
    return out


# ---------------------------------------------------------------------------
# (3) known G1 angle
# ---------------------------------------------------------------------------

def known_g1_angle(theta_deg, n=41):
    """Two planes meeting at a known dihedral angle."""
    theta = math.radians(theta_deg)
    a = flat_plane()
    b = plane_surface(theta, mirrored=True)
    ba, bb = _pair_bsplines(a, b)
    sampled = G.measure_seam(ba, lambda t: (0.0, t), "u",
                             bb, lambda t: (0.0, t), "u", n=n)
    exact = CA.measure_seam(a, lambda t: (0.0, t), "u",
                            b, lambda t: (0.0, t), "u", n=n)
    return {"theta_deg": theta_deg,
            "sampled_g1_deg": sampled["g1_deg"],
            "analytic_g1_deg": exact["g1_deg"],
            "sampled_k_gap": sampled["k_gap"],
            "analytic_k_gap": exact["k_gap"]}


def shipped_normal_gap(theta_deg, t=0.5, grid=30):
    """The SHIPPED fill instrument on the same known dihedral (#121).

    The corner fill's tangent-plane gap is read by the shipped oracle with
    `SilkWorkflowOps.solve_uv` + `normal_gap_deg` -- the OTHER instrument,
    on the SAME pair of planes this function's neighbour uses.  The truth
    is `theta_deg`; the instrument must report it.  This is the
    known-answer calibration the shipped bar rests on.
    """
    from SilkWorkflowOps import solve_uv, normal_gap_deg
    theta = math.radians(theta_deg)
    a = flat_plane()
    b = plane_surface(theta, mirrored=True)
    ba, bb = _pair_bsplines(a, b)
    point = ba.value(0.0, t)
    ua, va, resa = solve_uv(ba, point, (0.0, 1.0, 0.0, 1.0), grid=grid)
    ub, vb, resb = solve_uv(bb, point, (0.0, 1.0, 0.0, 1.0), grid=grid)
    gap = normal_gap_deg(ba, ua, va, bb, ub, vb)
    return {"theta_deg": theta_deg, "gap_deg": gap,
            "residual_a": resa, "residual_b": resb,
            "uv_a": (ua, va), "uv_b": (ub, vb)}


# ---------------------------------------------------------------------------
# (4) known curvature jump (the G2 calibration)
# ---------------------------------------------------------------------------

def known_curvature_jump(a_curv=1.0, b_curv=3.0, n=41):
    """G1 seam with a known normal-curvature jump 2|a - b| (1/mm)."""
    a = parab_surface(a_curv)
    b = parab_surface(b_curv, mirrored=True)
    ba, bb = _pair_bsplines(a, b)
    sampled = G.measure_seam(ba, lambda t: (0.0, t), "u",
                             bb, lambda t: (0.0, t), "u", n=n)
    exact = CA.measure_seam(a, lambda t: (0.0, t), "u",
                            b, lambda t: (0.0, t), "u", n=n)
    return {"truth_k_gap": 2.0 * abs(a_curv - b_curv),
            "sampled_g1_deg": sampled["g1_deg"],
            "analytic_g1_deg": exact["g1_deg"],
            "sampled_k_gap": sampled["k_gap"],
            "analytic_k_gap": exact["k_gap"]}


# ---------------------------------------------------------------------------
# (6) known torsion, measured both ways -- the twist metric's frame (#101)
# ---------------------------------------------------------------------------

def seam_torsion_reversal(n=41):
    """One C-infinity seam carrying a REAL geodesic torsion, measured with the
    caller's correspondence matched and reversed.

    Two halves of z = u*v meet at u = 0 on a seam that is smooth to all
    orders, so the true `twist_gap` is 0.  The seam is not torsion-free: the
    surface's normal turns along it at ~1 /mm, which is the positive control
    -- a metric that reported 0 because it is blind would be caught by the
    reported `tau_a`.

    The reversed reading is the same geometry with B's v axis flipped and the
    correspondence walked backwards, i.e. exactly the layout
    `match_boundaries` produces when it reverses one side.  Both readings must
    land on the same (near-zero) floor; before #101 both read 2|tau| ~ 2 /mm.
    """
    a = hpar_surface()
    out = {"tau_a_max": 0.0, "readings": {}}
    for label, flip_v in (("matched", False), ("reversed", True)):
        b = hpar_surface(mirrored=True, flip_v=flip_v)
        seam_b = (lambda t: (0.0, 1.0 - t)) if flip_v else (lambda t: (0.0, t))
        ba, bb = _pair_bsplines(a, b)
        exact = CA.measure_seam(a, lambda t: (0.0, t), "u", b, seam_b,
                                "u", n=n)
        sampled = G.measure_seam(ba, lambda t: (0.0, t), "u", bb, seam_b,
                                 "u", n=n)
        out["tau_a_max"] = max(out["tau_a_max"],
                               max(abs(s["tau_a"]) for s in exact["samples"]))
        out["readings"][label] = {
            key: {"sampled": sampled[key], "analytic": exact[key]}
            for key in ("c0", "g1_deg", "k_gap", "twist_gap")}
    return out


# ---------------------------------------------------------------------------
# (5) independent cross-check: 3D position profile, no derivative formula
# ---------------------------------------------------------------------------

def _across_step(surf, edge, reverse, t, delta):
    """Point on `surf`, `delta` across the seam from the seam foot at `t`.

    Returns (foot, point, across_unit).  Stepping keeps the along-seam
    station fixed and moves only the across parameter, so no uv solver is
    involved -- the parameter is known.
    """
    seam, along, across = CA.edge_seam(edge, reverse)
    u, v = seam(t)
    foot = surf.value(u, v)
    if across == "u":
        p = surf.value(min(1.0, u + delta), v)
        q = surf.value(min(1.0, u + delta * 0.5), v)
    else:
        p = surf.value(u, min(1.0, v + delta))
        q = surf.value(u, min(1.0, v + delta * 0.5))
    a_dir = _unit(q - foot)
    return foot, p, a_dir


def _unit(vec):
    length = vec.Length
    if length < 1e-15:
        return Base.Vector(0, 0, 0)
    return Base.Vector(vec.x / length, vec.y / length, vec.z / length)


def across_gap_profile(surf_a, edge_a, reverse_a, surf_b, edge_b, reverse_b,
                       deltas, n=11):
    """Max |reflected A point - B point| at matched across offsets.

    Reflects A's across step through the seam's normal plane (so it lands
    on B's side) and compares 3D position only.  The growth exponent is the
    continuity order: ~1 for C0, ~2 for G1, ~3 for G2.  Uses no derivative
    formula, so it shares neither instrument's assumptions.
    """
    prof = []
    for delta in deltas:
        worst = 0.0
        for k in range(n):
            t = k / (n - 1.0)
            foot, pa, a_dir = _across_step(surf_a, edge_a, reverse_a, t, delta)
            _, pb, _ = _across_step(surf_b, edge_b, reverse_b, t, delta)
            # reflect pa across the plane (normal = a_dir) through `foot`
            pa_ref = pa - a_dir * (2.0 * a_dir.dot(pa - foot))
            worst = max(worst, (pa_ref - pb).Length)
        prof.append((delta, worst))
    return prof


def gap_exponent(surf_a, edge_a, reverse_a, surf_b, edge_b, reverse_b,
                 deltas=None, n=11):
    if deltas is None:
        deltas = [0.025, 0.05, 0.1, 0.2]
    prof = [d for d in across_gap_profile(surf_a, edge_a, reverse_a,
                                          surf_b, edge_b, reverse_b,
                                          deltas, n=n) if d[1] > 1e-13]
    if len(prof) < 2:
        return None, prof
    (x0, y0), (x1, y1) = prof[0], prof[-1]
    return math.log(y1 / y0) / math.log(x1 / x0), prof


def seam_c0_distToShape(surf_a, edge_a, reverse_a, shape_b, n=11):
    """Max `distToShape` distance from A's seam points to B's face.

    An independent OCCT check of the C0 claim (the solver-free kind).
    """
    seam, _along, _across = CA.edge_seam(edge_a, reverse_a)
    worst = 0.0
    for k in range(n):
        t = k / (n - 1.0)
        u, v = seam(t)
        d, _, _ = shape_b.distToShape(Part.Vertex(surf_a.value(u, v)))
        worst = max(worst, d)
    return worst


def cross_check(n=11):
    """Known answers: C0 pair -> slope ~1, G1 pair -> slope ~2."""
    # C0 only: two planes at a known dihedral (normals disagree at the seam)
    c0_a = flat_plane()
    c0_b = plane_surface(math.radians(20.0), mirrored=True)
    sl_c0, prof_c0 = gap_exponent(c0_a, "u0", False, c0_b, "u0", False, n=n)

    # G1, curvature jump: parabola pair, tangent planes coincide
    g1_a = parab_surface(1.0)
    g1_b = parab_surface(3.0, mirrored=True)
    sl_g1, prof_g1 = gap_exponent(g1_a, "u0", False, g1_b, "u0", False, n=n)

    c0_seam = seam_c0_distToShape(g1_a, "u0", False,
                                  g1_b.to_bspline().toShape(), n=n)
    return {"c0_slope": sl_c0, "c0_profile": prof_c0,
            "g1_slope": sl_g1, "g1_profile": prof_g1,
            "g1_seam_distToShape": c0_seam}


# ---------------------------------------------------------------------------
# report
# ---------------------------------------------------------------------------

def main():
    print("== solve_uv soundness ==")
    s = sample_solve_uv()
    print("  bicubic max residual = %.3e mm, max |du| = %.3e, max |dv| = %.3e"
          % (s["bicubic"]["max_residual"], s["bicubic"]["max_du"],
             s["bicubic"]["max_dv"]))
    print("  plane   max residual = %.3e mm (params non-unique)"
          % s["plane"]["max_residual"])

    print("== error floor (smooth curved seam, truth = 0) ==")
    fl = error_floor()
    for key in ("c0", "g1_deg", "k_gap", "twist_gap"):
        v = fl[key]
        print("  %-10s sampled %.3e | analytic %.3e"
              % (key, v["sampled"], v["analytic"]))

    print("== known G1 angle ==")
    for th in (5.0, 20.0):
        r = known_g1_angle(th)
        print("  theta=%-5.1f  sampled %.4f deg | analytic %.4f deg"
              % (th, r["sampled_g1_deg"], r["analytic_g1_deg"]))

    print("== known curvature jump (G1, non-zero k_gap) ==")
    r = known_curvature_jump()
    print("  truth k_gap = %.4f /mm" % r["truth_k_gap"])
    print("  sampled  g1=%.4f deg  k_gap=%.4f /mm"
          % (r["sampled_g1_deg"], r["sampled_k_gap"]))
    print("  analytic g1=%.4f deg  k_gap=%.4f /mm"
          % (r["analytic_g1_deg"], r["analytic_k_gap"]))

    print("== independent cross-check (reflected 3D profile slopes) ==")
    cc = cross_check()
    print("  G1 pair slope = %.4f (expect ~2); C0 pair slope = %.4f (expect ~1)"
          % (cc["g1_slope"], cc["c0_slope"]))
    print("  A-seam to B-face distToShape (G1 pair) = %.3e mm"
          % cc["g1_seam_distToShape"])

    print("== twist frame (#101): one torsion-carrying smooth seam, both ways ==")
    tr = seam_torsion_reversal()
    print("  |tau_a| max along the seam = %.4f /mm" % tr["tau_a_max"])
    for label, reading in tr["readings"].items():
        print("  %-8s twist_gap  sampled %.3e | analytic %.3e /mm"
              % (label, reading["twist_gap"]["sampled"],
                 reading["twist_gap"]["analytic"]))
    return {"solve_uv": s, "floor": fl, "cross_check": cc, "torsion": tr}


if __name__ == "__main__":
    main()
