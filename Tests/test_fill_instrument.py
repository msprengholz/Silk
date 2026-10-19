"""
The SHIPPED fill instrument's soundness (ticket #121).

The corner fill's continuity is judged by the SHIPPED oracle
(`SilkWorkflowOps.corner_fill_problem`), which measures the fill's
TANGENT-PLANE GAP along the boundary it claims: the angle between the
fill's normal and its support surface's normal, read with `solve_uv` (the
MANUAL probe's solver, moved into the shipped code) and `normal_gap_deg`.

That number decides a product choice -- it is the bar the shipped oracle
refuses a fill against -- so per the standing measurement rule it has to
name its instrument, keep its raw output, publish its error floor and
carry a known-answer calibration or an independent cross-check.  This
module is that calibration:

  * a KNOWN G1 ANGLE: two planes meeting at a known dihedral theta must
    read theta through the shipped instrument -- the same known answer
    #97's calibration demands of the sampled oracle, on the same pair of
    planes (`Tests/continuity_calibration.py`), read by the OTHER
    instrument;
  * the ZERO CONTROL: a surface measured against itself must read 0 --
    the floor of the angle;
  * the SOLVER'S FLOOR: `solve_uv` must recover a point whose parameters
    are known exactly, to the 4.5e-13 mm #97's calibration published.

It asserts nothing about any real geometry: the instrument is the ruler,
and the ruler is what is checked here.  The corner fill's own readings
live in `Tests/test_corner_fill.py` (the manual tier).

Fast: two exact patches and a handful of solves.
"""

import Tests.continuity_calibration as CAL

import SilkWorkflowOps as OPS


def _failed(errs, checks):
    return {"pass": not errs, "errors": list(errs),
            "checks": list(checks) or ["ok"]}


def test_the_shipped_fill_instrument_reads_a_known_angle(doc):
    """Two planes at a known dihedral must read that dihedral through the
    SHIPPED instrument (`solve_uv` + `normal_gap_deg`)."""
    errs = []
    checks = []
    for theta in (5.0, 20.0):
        r = CAL.shipped_normal_gap(theta)
        checks.append("theta=%.1f -> shipped instrument %.6f deg "
                      "(residuals %.3e / %.3e mm)"
                      % (theta, r["gap_deg"], r["residual_a"],
                         r["residual_b"]))
        if r["gap_deg"] is None:
            errs.append("theta %.1f: the instrument read nothing" % theta)
            continue
        if abs(r["gap_deg"] - theta) > 0.01:
            errs.append("theta %.1f: the shipped instrument read %.6f"
                        % (theta, r["gap_deg"]))
    return _failed(errs, checks)


def test_the_shipped_fill_instrument_reads_zero_on_an_identical_pair(doc):
    """The ZERO CONTROL: a surface measured against itself reads 0.

    That is the floor of the angle -- and it is the control that says the
    instrument reports a difference when there IS one, rather than
    reporting a constant.
    """
    errs = []
    checks = []
    a = CAL.flat_plane().to_bspline()
    point = a.value(0.0, 0.5)
    u, v, res = OPS.solve_uv(a, point, (0.0, 1.0, 0.0, 1.0), grid=30)
    gap = OPS.normal_gap_deg(a, u, v, a, u, v)
    checks.append("identical pair: %.3e deg (solve residual %.3e mm)"
                  % (gap, res))
    if gap is None:
        errs.append("the instrument read nothing on an identical pair")
    elif gap > 1e-5:
        errs.append("the instrument reads %.3e deg on an identical pair"
                    % gap)
    return _failed(errs, checks)


def test_the_shipped_solver_recovers_a_known_parameter(doc):
    """`solve_uv` -- the solver the shipped fill oracle reads its points
    with -- must recover the parameters of a point whose (u, v) is known
    exactly, to the floor #97's calibration published (4.5e-13 mm).

    The stations are INTERIOR on purpose: the Newton differentiates across
    the point it solved, so a station on the patch's parametric edge would
    ask the surface for a value outside its domain."""
    errs = []
    checks = []
    a = CAL.flat_plane().to_bspline()
    for t in (0.25, 0.5, 0.75):
        point = a.value(0.37, t)
        u, v, res = OPS.solve_uv(a, point, (0.0, 1.0, 0.0, 1.0), grid=30)
        checks.append("point (0.37, %.2f) -> solved (%.9f, %.9f), "
                      "residual %.3e mm" % (t, u, v, res))
        if res > 1e-9:
            errs.append("residual %.3e mm at t=%.2f" % (res, t))
        if abs(u - 0.37) > 1e-6 or abs(v - t) > 1e-6:
            errs.append("parameter recovery at t=%.2f: (%.9f, %.9f)"
                        % (t, u, v))
    return _failed(errs, checks)


ALL_TESTS = [
    test_the_shipped_fill_instrument_reads_a_known_angle,
    test_the_shipped_fill_instrument_reads_zero_on_an_identical_pair,
    test_the_shipped_solver_recovers_a_known_parameter,
]
