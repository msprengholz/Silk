"""The two-tier suite contract.

The default run (`python3 Tests/run_all.py`) is the FAST tier: the guards,
the ops/oracle stage tests, the acceptance gate and the cheap unit tests.
The end-to-end rebuilds, GUI click-throughs, panel drives and measurement
sweeps carry `MANUAL = True` and are excluded -- they took the old default
run to ~11 minutes, which is what made the suite unusable as an inner loop.

This module is the counterweight that makes the split safe. It asserts:

  * the manual tier is exactly the set named here, so a module cannot be
    quietly deferred (or quietly pulled back) by editing its marker alone;
  * every manual module still IMPORTS and still carries at least one
    collected test, so "deferred" never silently becomes "lost";
  * the DEFAULT collection still contains the named load-bearing tests --
    the chain gate, the #67 stored-cycle guard, the #72 single-generation
    guard, and the continuity-calibration soundness checks -- so a future
    tier edit cannot drop one of them out of the fast tier by accident;
  * a MANUAL module named explicitly (as `--changed` and a by-name filter
    do) is still collected, so the manual tier is reachable on demand.

It is fast: it imports modules and calls the collector, it runs nothing
from the manual tier.
"""

import os

from Tests import suite
from Tests.mcp_harness import check

_TESTS_DIR = os.path.dirname(os.path.abspath(__file__))


# The manual tier, by module basename. Keep in step with the `MANUAL = True`
# marker each module carries; `suite.manual_module_basenames()` reads the
# markers, so a mismatch is a failure, not a silent divergence.
EXPECTED_MANUAL = {
    "test_band_expression",
    "test_band_generalization",
    "test_blend_corner_splits",
    "test_blend_gui_command",
    "test_blend_grid_toggle",
    "test_console_noise",
    "test_corner_blend",
    "test_corner_fill",
    "test_corner_gui_command",
    "test_corner_orientation",
    "test_cube_corner_3valent",
    "test_demo01_fixture_clickthrough",
    "test_demo01_rebuild",
    "test_display_grid",
    "test_g2_feasibility",
    "test_junction_corner_hidden",
    "test_mutation_backfill",
    "test_mutation_unified",
    "test_oracle_band_cells",
    "test_parametric_rebuild",
    "test_restore_contract",
    "test_runner_watchdog",
    "test_seam_resolver",
    "test_seam_side",
    "test_silkguide",
    "test_task_panel",
}


# Guards that must NOT be deferred, though they are tests of the runner: a
# module whose subject is the machinery the tier split itself uses cannot
# live in the tier that machinery creates. test_runner_timeout.py was
# deferred by the by-module rule ("the runner's tests are runner tests") and
# costs ~1.3 s -- it was never deferred for being slow. It then stayed green
# over the #122 commit that added `include_manual` as the seventh `_silk_run`
# argument -- the very signature change the split introduced -- and the break
# only surfaced in a ~12 minute `--manual` run. The tier gate protects the
# fast run, so the gate's own signature (and run_all/watchdog around it) must
# be checked BY the fast run. Do not move it back.
NOT_DEFERRABLE_FAST = (
    "test_runner_timeout",
)


# Tests that must NEVER leave the default (fast) tier. AGENTS.md names each
# one; losing any of them is the failure the tiering must not introduce.
LOAD_BEARING_FAST = (
    # the acceptance gate (ticket #26: it always runs, and always last)
    "test_chain_ground_truth",
    "test_chain_corner_ground_truth",
    # the #67 patch stored-cycle self-consistency guard
    "test_patch_stored_cycle_is_self_consistent_for_all_24_orderings",
    # the #72 single-generation guard
    "test_every_mod_module_shares_one_arachnurbs_generation",
    # the continuity-calibration soundness harness + its label guard
    "test_solve_uv_calibration",
    "test_oracle_known_g1_angle",
    "test_oracle_known_curvature_jump",
    "test_no_continuity_threshold_in_suite",
    # the ops/oracle stage tests
    "test_create_edge_3l",
    "test_create_patch_ground_truth",
    "test_create_blend_ground_truth",
)


def test_manual_tier_is_exactly_the_expected_set(doc):
    """The `MANUAL = True` markers and this list agree, both directions."""
    found = set(suite.manual_module_basenames())
    errors = []
    checks = ["manual modules found: %d" % len(found)]
    for name in sorted(EXPECTED_MANUAL - found):
        errors.append("%s is expected MANUAL but its marker is gone "
                      "(did it silently rejoin the fast tier?)" % name)
    for name in sorted(found - EXPECTED_MANUAL):
        errors.append("%s carries MANUAL but is not in EXPECTED_MANUAL "
                      "(a deferral nobody recorded?)" % name)
    for name in NOT_DEFERRABLE_FAST:
        if name in found or name in EXPECTED_MANUAL:
            errors.append("%s is deferred, but its subject is the runner/tier "
                          "machinery the fast run depends on -- see the "
                          "comment on NOT_DEFERRABLE_FAST" % name)
        else:
            checks.append("%s is in the fast tier" % name)
    return {"pass": not errors, "errors": errors, "checks": checks}


def test_every_manual_module_still_imports_and_has_tests(doc):
    """Deferred is not deleted: each manual module imports and has tests."""
    errors = []
    checks = []
    default_names = {f.__name__ for f in suite.collect_tests()}
    manual_funcs = suite.collect_tests(include_manual=True)
    for name in sorted(EXPECTED_MANUAL):
        path = os.path.join(_TESTS_DIR, name + ".py")
        if not os.path.exists(path):
            errors.append("%s is missing from Tests/" % name)
            continue
        import importlib
        try:
            mod = importlib.import_module("Tests." + name)
        except Exception as exc:  # noqa: BLE001 - report, do not crash
            errors.append("%s does not import: %s: %s"
                          % (name, type(exc).__name__, exc))
            continue
        if not getattr(mod, "MANUAL", False):
            errors.append("%s lost its MANUAL marker" % name)
        own = [f.__name__ for f in manual_funcs
               if (f.__module__ or "").split(".")[-1] == name]
        if not own:
            errors.append("%s collects no test functions in the manual tier"
                          % name)
        if any(n in default_names for n in own):
            leaked = [n for n in own if n in default_names]
            errors.append("%s tests leaked into the default tier: %s"
                          % (name, leaked))
        checks.append("%s: %d test(s)" % (name, len(own)))
    return {"pass": not errors, "errors": errors, "checks": checks}


def test_default_tier_keeps_the_load_bearing_tests(doc):
    """No tier edit may drop a named guard out of the default run."""
    default_names = {f.__name__ for f in suite.collect_tests()}
    errors = []
    checks = ["default tier: %d tests" % len(default_names)]
    for name in LOAD_BEARING_FAST:
        if name not in default_names:
            errors.append("%s is NOT in the default (fast) tier" % name)
    if not errors:
        checks.append("all %d load-bearing tests are in the default tier"
                      % len(LOAD_BEARING_FAST))
    return {"pass": not errors, "errors": errors, "checks": checks}


def test_a_named_manual_module_is_still_reachable(doc):
    """The manual tier runs on demand: naming a module selects it."""
    name = sorted(EXPECTED_MANUAL)[0]
    by_module = suite.collect_tests(test_modules=[name])
    by_filter = suite.collect_tests(test_filter=name)
    errors = []
    checks = []
    if not by_module:
        errors.append("test_modules=[%r] selected nothing" % name)
    else:
        checks.append("test_modules=[%r] -> %d test(s)" % (name, len(by_module)))
    if not by_filter:
        errors.append("filter %r selected nothing from the manual tier" % name)
    else:
        checks.append("filter %r -> %d test(s)" % (name, len(by_filter)))
    for fn in by_module + by_filter:
        mod = (fn.__module__ or "").split(".")[-1]
        check(mod == name, "%s came from %s, not %s" % (fn.__name__, mod, name),
              errors)
    return {"pass": not errors, "errors": errors, "checks": checks}


ALL_TESTS = [
    test_manual_tier_is_exactly_the_expected_set,
    test_every_manual_module_still_imports_and_has_tests,
    test_default_tier_keeps_the_load_bearing_tests,
    test_a_named_manual_module_is_still_reachable,
]
