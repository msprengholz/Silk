"""
Instrument calibration and reachability tests (ticket #97).

These tests calibrate the CORNER CONTINUITY INSTRUMENT against geometry whose
answer is known in closed form.  They do NOT assert a continuity label for
any real geometry: per ticket #97 (and ADR-0005), no continuity is claimed
until the measurement is calibrated, and an uncalibrated pass/fail threshold
in the suite would be exactly the failure this ticket exists to stop.  The
suite checks that the ruler is honest; it does not read the part with it.

Red-first: before `Tests/continuity_analytic.py` existed, `test_analytic_*`
and `test_normal_curvature_metric_*` fail (no arbiter); before the
calibration module, `test_*_calibration` fail.
"""

import glob
import math
import os

import Tests.continuity_calibration as CAL
import Tests.continuity_analytic as CA
import Tests.silk_nurbs as SN


def _failed(errs):
    return {"pass": not errs, "errors": list(errs),
            "checks": [e for e in errs] or ["ok"]}


def test_solve_uv_calibration(doc):
    """solve_uv on observed (u, v) recovers the exact parameters."""
    s = CAL.sample_solve_uv(n=5)
    b = s["bicubic"]
    errs = []
    if not b["max_residual"] < 1e-6:
        errs.append("bicubic residual %.3e mm >= 1e-6" % b["max_residual"])
    if not b["max_du"] < 1e-6 or not b["max_dv"] < 1e-6:
        errs.append("parameter recovery |du|=%.3e |dv|=%.3e"
                    % (b["max_du"], b["max_dv"]))
    return {"pass": not errs, "errors": errs,
            "checks": ["residual %.3e mm, |du| %.3e, |dv| %.3e"
                       % (b["max_residual"], b["max_du"], b["max_dv"])]}


def test_oracle_known_g1_angle(doc):
    """The sampled g1 metric reports a known dihedral angle."""
    errs = []
    checks = []
    for theta in (5.0, 20.0):
        r = CAL.known_g1_angle(theta)
        d = abs(r["sampled_g1_deg"] - theta)
        checks.append("theta=%.1f -> sampled %.5f deg" % (theta,
                                                          r["sampled_g1_deg"]))
        if d > 0.01:
            errs.append("theta %.1f: sampled %.5f (delta %.4f)"
                        % (theta, r["sampled_g1_deg"], d))
    return {"pass": not errs, "errors": errs, "checks": checks}


def test_oracle_known_curvature_jump(doc):
    """A known normal-curvature jump; and g1 cannot see it.

    Two parabolic cylinders meet tangent-plane continuous (g1 = 0) with
    normal curvatures 2a and 2b.  The curvature metric must report
    2|a - b|; the tangent metric must stay ~0.  This is the calibration for
    any G2 claim.
    """
    r = CAL.known_curvature_jump(a_curv=1.0, b_curv=3.0)
    errs = []
    if abs(r["sampled_k_gap"] - r["truth_k_gap"]) > 0.01:
        errs.append("sampled k_gap %.5f != truth %.5f"
                    % (r["sampled_k_gap"], r["truth_k_gap"]))
    if abs(r["analytic_k_gap"] - r["truth_k_gap"]) > 1e-9:
        errs.append("analytic k_gap %.5f != truth %.5f"
                    % (r["analytic_k_gap"], r["truth_k_gap"]))
    if r["sampled_g1_deg"] > 0.1:
        errs.append("g1 should be ~0 on this seam, got %.5f"
                    % r["sampled_g1_deg"])
    return {"pass": not errs, "errors": errs,
            "checks": ["truth k_gap %.4f, sampled %.4f, analytic %.4f, "
                       "sampled g1 %.5f deg (g1 blind to the G2 jump)"
                       % (r["truth_k_gap"], r["sampled_k_gap"],
                          r["analytic_k_gap"], r["sampled_g1_deg"])]}


def test_analytic_matches_sampled_oracle(doc):
    """The exact arbiter and the sampled instrument agree on known answers."""
    errs = []
    checks = []
    cases = [
        ("g1_20", CAL.known_g1_angle(20.0), ("g1_deg", 1e-3, 1e-2)),
        ("kgap", CAL.known_curvature_jump(1.0, 3.0), ("k_gap", 1e-2, 1e-2)),
    ]
    for name, r, (key, abtol, reltol) in cases:
        sa = r["sampled_" + key]
        an = r["analytic_" + key]
        checks.append("%s sampled %.6f vs analytic %.6f" % (name, sa, an))
        if abs(sa - an) > max(abtol, reltol * max(abs(an), 1e-9)):
            errs.append("%s: sampled %.6f vs analytic %.6f" % (name, sa, an))
    return {"pass": not errs, "errors": errs, "checks": checks}


def test_controlnet_c0_is_exact(doc):
    """C0 read off the control net, combinatorially, with a known gap."""
    a = CAL.parab_surface(1.0)
    b = CAL.parab_surface(1.0)
    errs = []
    checks = []
    gap, _ = SN.c0_controlnet(a, "u0", b, "u0")
    checks.append("identical boundary control nets gap = %.3e" % gap)
    if gap != 0.0:
        errs.append("identical control nets report %.3e" % gap)

    import FreeCAD
    poles = [[FreeCAD.Vector(p.x, p.y, p.z) for p in col] for col in b.poles]
    poles[0][0] = poles[0][0] + FreeCAD.Vector(0.0, 0.0, 0.01)
    b2 = SN.NurbsSurface(poles, b.weights, SN.KNOTS_4, SN.KNOTS_4)
    gap2, _ = SN.c0_controlnet(a, "u0", b2, "u0")
    checks.append("one pole moved 0.01 -> gap = %.6f" % gap2)
    if abs(gap2 - 0.01) > 1e-12:
        errs.append("expected 0.01, got %.6f" % gap2)
    return {"pass": not errs, "errors": errs, "checks": checks}


def test_independent_cross_check_order(doc):
    """A derivative-free 3D profile recovers the continuity order."""
    cc = CAL.cross_check()
    errs = []
    if not (1.85 <= cc["g1_slope"] <= 2.15):
        errs.append("G1 pair slope %.4f not ~2" % cc["g1_slope"])
    if not (0.9 <= cc["c0_slope"] <= 1.1):
        errs.append("C0 pair slope %.4f not ~1" % cc["c0_slope"])
    if not cc["g1_seam_distToShape"] < 1e-6:
        errs.append("G1 seam distToShape %.3e mm" % cc["g1_seam_distToShape"])
    return {"pass": not errs, "errors": errs,
            "checks": ["G1 slope %.4f (expect 2), C0 slope %.4f (expect 1), "
                       "seam distToShape %.3e mm"
                       % (cc["g1_slope"], cc["c0_slope"],
                          cc["g1_seam_distToShape"])]}


def test_error_floor_reported(doc):
    """Report the floor of each quantity; it must sit below any real signal."""
    fl = CAL.error_floor()
    errs = []
    checks = []
    for key in ("c0", "g1_deg", "k_gap", "twist_gap"):
        v = fl[key]["sampled"]
        checks.append("%s floor (sampled) %.3e" % (key, v))
    # the floor is the noise level; a real signal (curvature jump 4.0) must
    # exceed it by orders of magnitude, or no measurement is possible.
    if fl["k_gap"]["sampled"] > 1e-3:
        errs.append("k_gap floor %.3e too large to measure a 4.0 signal"
                    % fl["k_gap"]["sampled"])
    if fl["g1_deg"]["sampled"] > 1e-2:
        errs.append("g1 floor %.3e too large" % fl["g1_deg"]["sampled"])
    return {"pass": not errs, "errors": errs, "checks": checks}


def test_twist_gap_is_reversal_invariant(doc):
    """`twist_gap` reads the same floor for a matched and a reversed seam.

    Known answer (#101): two halves of z = u*v meet on a seam that is smooth
    to all orders, so the true twist_gap is 0 -- while the geodesic torsion
    along it is ~1 /mm, so a metric that read 0 out of blindness is caught by
    `tau_a_max`.  Measured with the caller's correspondence matched and
    reversed; BEFORE #101 both readings returned 2|tau| = 2.000000e+00 /mm on
    both instruments (the natural-axis along-tangent, plus a normal-side sign
    lost after the alignment flip).

    WHAT THE CORRECTED METRIC PERMITS.  `twist_gap` may now be quoted on a
    REVERSED seam correspondence as well as a matched one, so every
    previously quotable non-reversed figure keeps its value and meaning and
    the figures the #100 correction flagged as orientation-suspect become
    re-measurable rather than unusable.  It is still not a continuity label:
    no threshold or `classify()` appears here.
    """
    tr = CAL.seam_torsion_reversal(n=41)
    # 1e-6 /mm: six orders below the 1 /mm torsion the seam carries and six
    # orders above both instruments' measured floor (<= 1.3e-12 sampled,
    # 4.4e-16 exact).  Derived from the floor, not from a continuity claim.
    tol = 1e-6
    errs = []
    checks = ["|tau_a| max along the calibration seam = %.4f /mm"
              % tr["tau_a_max"]]
    if not tr["tau_a_max"] > 0.5:
        errs.append("the calibration seam carries no torsion (|tau_a| max "
                    "%.3e) -- a zero gap would prove nothing"
                    % tr["tau_a_max"])
    for label, reading in sorted(tr["readings"].items()):
        for tag in ("sampled", "analytic"):
            twist = reading["twist_gap"][tag]
            k_gap = reading["k_gap"][tag]
            checks.append("%s %s: twist_gap %.3e /mm, k_gap %.3e /mm"
                          % (label, tag, twist, k_gap))
            if not twist < tol:
                errs.append("%s %s: twist_gap %.3e /mm on a smooth seam "
                            "(the metric carries the frame, not the "
                            "correspondence's orientation)"
                            % (label, tag, twist))
            if not k_gap < 1e-9:
                errs.append("%s %s: k_gap %.3e /mm -- the twist frame must "
                            "not perturb the curvature metric"
                            % (label, tag, k_gap))
    return {"pass": not errs, "errors": errs, "checks": checks}


def test_manual_measurement_scripts_reachable(doc):
    """The manual corner scripts import, expose main, and carry MANUAL.

    A rename, a syntax break, or a lost marker is caught here even though
    neither measurement is run by the suite.
    """
    import Tests.g2_demo_corner as demo
    import Tests.g2_corner_measurement as cm
    import Tests.g2_corner_solve as solve
    import Tests.g2_edge_blend_probe as edge
    import Tests.g2_corner_fill_continuity as fill
    import Tests.g2_corner_roll_measure as roll
    import Tests.g2_corner_roll_visual as visual
    import Tests.rolling_corner_visual as rolling
    # #123: the RSS/baseline instrument is a MANUAL measurement script
    # too, and it is reachable by the same contract.
    import Tests.rss_baseline_measure as rss
    errs = []
    checks = []
    for mod in (demo, cm, solve, edge, fill, roll, visual, rolling, rss):
        ok = callable(getattr(mod, "main", None))
        checks.append("%s.main callable: %s" % (mod.__name__, ok))
        if not ok:
            errs.append("%s has no callable main" % mod.__name__)
        marker = getattr(mod, "MANUAL", None)
        checks.append("%s.MANUAL = %r" % (mod.__name__, marker))
        if not marker:
            errs.append("%s is not marked MANUAL" % mod.__name__)
    return {"pass": not errs, "errors": errs, "checks": checks}


def test_no_continuity_threshold_in_suite(doc):
    """No test module encodes an uncalibrated continuity pass/fail.

    The instrument reports; a label may only be produced by the calibrated
    oracle, never asserted as a suite pass condition.  This scans the
    test_*.py modules for `classify(` -- the label function -- and fails if
    a test ever starts depending on it.
    """
    here = os.path.dirname(os.path.abspath(__file__))
    offenders = []
    for path in sorted(glob.glob(os.path.join(here, "test_*.py"))):
        if os.path.basename(path) == os.path.basename(__file__):
            continue
        with open(path) as fh:
            text = fh.read()
        if "classify(" in text:
            offenders.append(os.path.basename(path))
    errs = []
    if offenders:
        errs.append("test modules using continuity labels: %s"
                    % ", ".join(offenders))
    return {"pass": not errs, "errors": errs,
            "checks": ["no test module calls classify(): %s"
                       % ("yes" if not offenders else offenders)]}


ALL_TESTS = [
    test_solve_uv_calibration,
    test_oracle_known_g1_angle,
    test_oracle_known_curvature_jump,
    test_analytic_matches_sampled_oracle,
    test_controlnet_c0_is_exact,
    test_independent_cross_check_order,
    test_error_floor_reported,
    test_twist_gap_is_reversal_invariant,
    test_manual_measurement_scripts_reachable,
    test_no_continuity_threshold_in_suite,
]
