"""Ticket #106 pins: does the strips' interior freedom move the corner-G2 wall?

MEASUREMENT, not a build.  Pinned calibration records for the offline #106
finding (`docs/research/silk-g2-feasibility.md`); the numpy port lives in
`Tests/g2_feasibility_model.py`.  No continuity label is asserted anywhere in
this module -- it must never call the continuity label function
(`test_continuity_instrument` guards the suite against that).

WHAT IS PINNED (calibration records, not pass/fail thresholds for surface
quality):

  * the port reproduces the #100 numbers on the synthetic compatible ring and
    on the demo's frozen baseline (all eight table entries, plus the
    `CubicSurface_66` v0 calibration seam);
  * the treatment -- each seam strip's second-order row freed jointly with the
    corner's 4 central poles, C0/G1 rows fixed -- takes the four demo
    junctions to the recorded treated `k_gap` values;
  * the motion of every freed row stays at/below the recorded cells, with no
    fold (no normal flip, no non-monotone cross-section), and the four
    triangular members keep their collapsed row.

A failing pin means the maths changed -- update the pin AND
`docs/research/silk-g2-feasibility.md`.

WHY THE SAMPLE COUNTS STAY (#116).  `N_FINAL = 401`, `measure_against`'s
`n=41` and the solve's `n_st=9` / `n_iter=3` are not knobs: every pinned
number below IS the reading taken at those counts, so a smaller `n`
re-pins a WEAKER measurement rather than the same one -- the calibration
record would no longer be the one #100/#106 published.  The measured cost
of the four tests is 49 s (`test_port_calibrates_on_synthetic_compatible_ring`
-- the first of the four to run -- pays the whole `_analysis()`; the
module-level `_CACHE` makes the other three free).  That is the price of
the record, and it is paid once per run.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from g2_feasibility_model import ABS, REL, SEAMS, _analysis  # noqa: E402


# #100 reproduced by the port (synthetic feed, measured at n=41; solved at n=401)
PIN_SYN_TRUTH = 6.678685e-17
PIN_SYN_CURRENT = 4.080250e-4
PIN_SYN_SOLVED = 1.253338e-16
PIN_SYN_POLES_INF = 2.273737e-13

# name, current worst @n=41, frozen solve residual @n_st=9 (the #100 "solved"
# column), frozen measured worst @n=41, treated worst @n=401
PIN_JUNCTIONS = (
    ("CubicSurface_66", 1.306583215e-2, 7.117402677e-3, 7.117402677e-3,
     2.764393824e-4),
    ("CubicSurface_66001", 3.077018021e-2, 4.999001030e-3, 4.999001030e-3,
     4.689266068e-5),
    ("CubicSurface_66002", 1.950185995e-2, 3.375029053e-3, 3.375029053e-3,
     7.636418903e-5),
    ("CubicSurface_66003", 2.107059380e-2, 2.211660799e-4, 2.294450303e-4,
     1.026078204e-5),
)
# per-seam (frozen @n=401, treated @n=401), in SEAMS order
PIN_SEAMS = {
    "CubicSurface_66": (
        (7.117402677e-3, 1.168481766e-4), (2.006140731e-4, 2.559425034e-7),
        (6.007717868e-3, 2.764393824e-4), (2.095482898e-3, 3.446923066e-5)),
    "CubicSurface_66001": (
        (2.643781890e-3, 4.007382023e-5), (3.347145172e-5, 1.576804711e-6),
        (1.545242854e-3, 2.874989402e-5), (4.999001030e-3, 4.689266068e-5)),
    "CubicSurface_66002": (
        (1.618752868e-4, 3.943597562e-6), (3.375029053e-3, 1.453543434e-5),
        (3.272880188e-3, 2.811680774e-5), (9.926839397e-4, 7.636418903e-5)),
    "CubicSurface_66003": (
        (6.681777773e-6, 1.802898202e-17), (3.499548737e-5, 1.026078204e-5),
        (2.302852474e-4, 6.802514361e-6), (1.402658888e-4, 1.499699074e-6)),
}
PIN_MOTION_CELLS_MAX = (0.5157, 0.5183, 0.4714, 0.0257)   # per junction
# the J1 v0 seam of the STORED corner: #100's measure_oblique calibration row
PIN_CAL_SEAM = {"k_gap": 7.117402677e-3, "g1_deg": 0.475746254,
                "twist_gap": 1.230318483e-3}

def _close_pin(value, pin, rel=REL, abs_floor=ABS):
    return abs(value - pin) <= max(rel * abs(pin), abs_floor)


# ---------------------------------------------------------------------------
# tests
# ---------------------------------------------------------------------------

def test_port_calibrates_on_synthetic_compatible_ring(doc):
    """Control (a): the numpy port reproduces #100's known-answer feed --
    truth <= 6.68e-17, averaging 4.080e-4, solve recovers T."""
    a = _analysis()
    checks, errors = [], []
    for label, value, pin in (
            ("truth T vs strips, worst k_gap", a["syn_truth"], PIN_SYN_TRUTH),
            ("two-row averaging, worst k_gap", a["syn_current"],
             PIN_SYN_CURRENT),
            ("G2 solve, worst k_gap", a["syn_solved"], PIN_SYN_SOLVED),
            ("|solved - T|_inf (homogeneous)", a["syn_poles_inf"],
             PIN_SYN_POLES_INF)):
        ok = _close_pin(value, pin)
        checks.append("%s: %.6e (pinned %.3e)" % (label, value, pin))
        if not ok:
            errors.append("%s: %.6e is not the pinned %.3e"
                          % (label, value, pin))
    return {"pass": not errors, "errors": errors, "checks": checks}


def test_demo_frozen_baseline_reproduces_ticket_100(doc):
    """Control (b): on all four demo junctions the port reproduces #100's
    stored-corner worst, frozen-solve residual and frozen measured worst
    (all at the documented station counts), plus the v0 calibration seam."""
    a = _analysis()
    checks, errors = [], []
    for name, cur_pin, resid_pin, base_pin, _t in PIN_JUNCTIONS:
        rec = a["demo"][name]
        cur = max(rec["cur41"][n]["k_gap"] for n, _k, _f, _i in SEAMS)
        base = max(rec["base41"][n]["k_gap"] for n, _k, _f, _i in SEAMS)
        resid = rec["base_residual"]
        checks.append("%s: current worst %.6e (pinned %.4e); frozen solve "
                      "residual %.6e (pinned %.4e); frozen measured worst "
                      "%.6e (pinned %.4e)"
                      % (name, cur, cur_pin, resid, resid_pin, base, base_pin))
        if not _close_pin(cur, cur_pin):
            errors.append("%s: current worst %.6e is not #100's %.4e"
                          % (name, cur, cur_pin))
        if not _close_pin(resid, resid_pin):
            errors.append("%s: frozen solve residual %.6e is not #100's "
                          "%.4e" % (name, resid, resid_pin))
        if not _close_pin(base, base_pin):
            errors.append("%s: frozen measured worst %.6e is not the pinned "
                          "%.4e" % (name, base, base_pin))
    seam = a["demo"]["CubicSurface_66"]["cur41"]["v0"]
    for key, pin in PIN_CAL_SEAM.items():
        checks.append("CubicSurface_66 v0 %s: %.6e (pinned %.4e)"
                      % (key, seam[key], pin))
        if not _close_pin(seam[key], pin):
            errors.append("CubicSurface_66 v0 %s %.6e is not the pinned "
                          "%.4e" % (key, seam[key], pin))
    return {"pass": not errors, "errors": errors, "checks": checks}


def test_strip_interior_freedom_moves_the_wall_with_sane_geometry(doc):
    """The #106 reading: freeing each seam strip's second-order row (plus the
    corner's 4 central poles) takes each junction from its frozen worst to
    the pinned treated worst, with every freed row inside its pinned motion
    and no fold.  Pins are calibration records, not a continuity label."""
    a = _analysis()
    checks, errors = [], []
    for name, _cur_pin, _resid_pin, base_pin, treat_pin in PIN_JUNCTIONS:
        rec = a["demo"][name]
        treated = max(rec["treat"]["report"][n]["k_gap"]
                      for n, _k, _f, _i in SEAMS)
        gain = base_pin / treated
        checks.append("%s: treated worst %.6e /mm (pinned %.4e), frozen "
                      "%.4e -> gain %.1fx; station residual %.2e"
                      % (name, treated, treat_pin, base_pin, gain,
                         rec["treat"]["max_residual"]))
        if not _close_pin(treated, treat_pin):
            errors.append("%s: treated worst %.6e is not the pinned %.4e"
                          % (name, treated, treat_pin))
        for i, (n, _k, _f, _i) in enumerate(SEAMS):
            f_pin, t_pin = PIN_SEAMS[name][i]
            base = rec["base401"][n]["k_gap"]
            tt = rec["treat"]["report"][n]["k_gap"]
            if not _close_pin(base, f_pin) or not _close_pin(tt, t_pin):
                errors.append("%s %s: frozen %.4e treated %.4e are not the "
                              "pinned %.4e / %.4e"
                              % (name, n, base, tt, f_pin, t_pin))
    for j, (name, _c, _r, _b, _t) in enumerate(PIN_JUNCTIONS):
        rec = a["demo"][name]
        mx = max(rec["motions"].values())
        flips = sum(rec["folds"][n][0] for n, _k, _f, _i in SEAMS)
        mono = sum(rec["folds"][n][1] for n, _k, _f, _i in SEAMS)
        checks.append("%s: max motion %.3f cells (pinned <= %.2f), "
                      "normal flips %d, non-monotone steps %d"
                      % (name, mx, PIN_MOTION_CELLS_MAX[j], flips, mono))
        if mx > PIN_MOTION_CELLS_MAX[j] * 1.001:
            errors.append("%s: a freed row moved %.3f cells, beyond the "
                          "pinned %.2f" % (name, mx, PIN_MOTION_CELLS_MAX[j]))
        if flips or mono:
            errors.append("%s: the treated strips fold (flips %d, mono %d)"
                          % (name, flips, mono))
    return {"pass": not errors, "errors": errors, "checks": checks}


def test_triangular_members_keep_their_collapse(doc):
    """All four members carry the collapse in row 3 and the treatment leaves
    it collapsed (the freed row is the member's row 2)."""
    a = _analysis()
    checks, errors = [], []
    count = 0
    for name, _c, _r, _b, _t in PIN_JUNCTIONS:
        rec = a["demo"][name]
        for seam, (spread0, spread1) in rec["members"].items():
            count += 1
            checks.append("%s %s: member row-3 spread stored %.3e mm, "
                          "treated %.3e mm" % (name, seam, spread0, spread1))
            if spread0 > 1e-9 or spread1 > 1e-9:
                errors.append("%s %s: collapse lost (%.3e -> %.3e mm)"
                              % (name, seam, spread0, spread1))
    if count != 4:
        errors.append("expected one triangular member seam per junction, "
                      "found %d" % count)
    return {"pass": not errors, "errors": errors, "checks": checks}


ALL_TESTS = [
    test_port_calibrates_on_synthetic_compatible_ring,
    test_demo_frozen_baseline_reproduces_ticket_100,
    test_strip_interior_freedom_moves_the_wall_with_sane_geometry,
    test_triangular_members_keep_their_collapse,
]


if __name__ == "__main__":
    import time
    t0 = time.time()
    all_ok = True
    for fn in ALL_TESTS:
        r = fn(None)
        print("[%s] %s" % ("pass" if r["pass"] else "FAIL", fn.__name__))
        for c in r["checks"]:
            print("     %s" % c)
        for e in r["errors"]:
            print("     ERROR: %s" % e)
        all_ok = all_ok and r["pass"]
    print("all pass: %s (%.1fs)" % (all_ok, time.time() - t0))
