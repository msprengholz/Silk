"""The #123 baseline instrument: the analyser is calibrated (ticket #123).

`Tests/rss_baseline_measure.py` is a MEASUREMENT, not a fix: it runs the
fast tier N times in one FreeCAD and asks whether the runner's memory
grows per RUN or whether the BASELINE drifts between runs.  The suite
cannot run it (it needs a live FreeCAD and it is a MANUAL script), so
what the suite does here is check the parts of it that can be checked
without one:

  * the instrument is reachable -- it imports, exposes `main`, and
    carries MANUAL (the same contract the other measurement scripts
    carry; `Tests/test_continuity_instrument.py` asserts the same thing
    for the continuity instruments);
  * the instrument is NOT in the fast tier -- a measurement script that
    the fast tier started running would measure the measurement;
  * the analyser recovers a KNOWN slope (the calibration: a synthetic
    series with a known drift must be reported as drifting, and a flat
    one must not);
  * the analyser reads the runner's OWN output lines, so a change to
    those lines is caught here rather than silently producing an empty
    measurement;
  * the orphan census finds an orphan that is put in front of it -- with
    a SYNTHETIC module object, so the test never touches sys.modules and
    never leaves a generation behind for the next run to count.

The instrument is imported INSIDE the tests, not at module level: this
test module is itself a Mod module, and a module-level import would put
a Mod module object into its dict.  A surviving module dict is what the
orphan count is made of, and the instrument must not change what it
measures.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def _instrument():
    """The measurement instrument, imported lazily (see the module docstring)."""
    from Tests import rss_baseline_measure
    return rss_baseline_measure


def _ok(checks, errors, passed=None):
    return {
        "pass": (not errors) if passed is None else passed,
        "checks": checks,
        "errors": errors,
    }


# ----------------------------------------------------------------------
# reachability and tier
# ----------------------------------------------------------------------

def test_the_instrument_is_reachable_and_manual(doc):
    """It imports, exposes main(), and carries MANUAL."""
    M = _instrument()
    errors = []
    checks = []
    ok = callable(getattr(M, "main", None))
    checks.append("rss_baseline_measure.main callable: %s" % ok)
    if not ok:
        errors.append("Tests.rss_baseline_measure has no callable main")
    marker = getattr(M, "MANUAL", None)
    checks.append("MANUAL = %r" % (marker,))
    if not marker:
        errors.append("Tests.rss_baseline_measure is not marked MANUAL")
    return _ok(checks, errors)


def test_the_instrument_is_not_in_the_fast_tier(doc):
    """The fast tier must not run the measurement (it needs a live GUI)."""
    from Tests import suite
    errors = []
    checks = []
    funcs = suite.collect_tests()
    mine = [f.__name__ for f in funcs
            if (f.__module__ or "") == "Tests.rss_baseline_measure"]
    checks.append("%d fast-tier test function(s) from the instrument: %s"
                  % (len(mine), mine))
    if mine:
        errors.append("the measurement script is in the fast tier: %s" % mine)
    return _ok(checks, errors)


# ----------------------------------------------------------------------
# the analyser, against known answers
# ----------------------------------------------------------------------

def test_the_analyser_recovers_a_known_slope(doc):
    """A synthetic series with a known drift must be read as drifting.

    This is the calibration of the instrument: the drift verdict is only
    as good as the slope it is computed from, so the slope is checked
    against a series whose slope is known exactly.
    """
    M = _instrument()
    errors = []
    checks = []
    for slope in (2.0, -1.5, 0.0):
        series = [600.0 + slope * i for i in range(5)]
        got = M.least_squares_slope(series)
        checks.append("known slope %+.1f -> measured %+.4f MB/run"
                      % (slope, got))
        if abs(got - slope) > 1e-9:
            errors.append("known slope %+.1f measured %+.4f" % (slope, got))
        # The floor is 1 MB here, so a 2 MB/run drift over 4 runs (8 MB)
        # is a drift and a 0 MB/run slope is not.
        verdict = M.classify_baseline(series, 1.0)
        checks.append("  -> %s (span %.1f MB)" % (verdict["verdict"],
                                                  verdict["span_mb"]))
        if (slope != 0.0) and verdict["verdict"] != "drift":
            errors.append("a %.1f MB/run drift was called %r"
                          % (slope, verdict["verdict"]))
        if slope == 0.0 and verdict["verdict"] != "steady":
            errors.append("a flat series was called %r" % verdict["verdict"])
    return _ok(checks, errors)


def test_a_drift_below_the_floor_is_not_called_a_drift(doc):
    """A growth inside the floor is 'steady' -- the instrument must not
    turn noise into a finding."""
    M = _instrument()
    errors = []
    checks = []
    floor = 2.0
    series = [600.0, 600.4, 600.8, 601.2, 601.6]     # 0.4 MB/run
    verdict = M.classify_baseline(series, floor)
    checks.append("0.4 MB/run with a %.1f MB floor -> %s (span %.1f MB)"
                  % (floor, verdict["verdict"], verdict["span_mb"]))
    if verdict["verdict"] != "steady":
        errors.append("a sub-floor growth was called %r" % verdict["verdict"])
    series = [600.0, 610.0, 620.0, 630.0, 640.0]     # 10 MB/run
    verdict = M.classify_baseline(series, floor)
    checks.append("10 MB/run with a %.1f MB floor -> %s" % (floor,
                                                            verdict["verdict"]))
    if verdict["verdict"] != "drift":
        errors.append("a 10 MB/run drift was called %r" % verdict["verdict"])
    return _ok(checks, errors)


def test_the_runner_lines_are_read(doc):
    """The readings come from the runner's OWN output lines.

    If those lines change, the measurement would silently come out
    empty -- so the format is pinned here.
    """
    M = _instrument()
    errors = []
    checks = []
    sample = (
        "[reload] RELOADING: sources changed since the last run -- purged "
        "57 module(s) from the Mod directory\n"
        "[leak] 3 orphaned Mod module generation(s) pinned outside "
        "sys.modules\n"
        "[rss] FreeCAD pid 12345 resident memory: before 582.7 MB, after "
        "756.1 MB (delta 173.4 MB)\n"
        "\n200/200 passed, 0 failed (in running FreeCAD)\n")
    parsed = M.parse_run_output(sample)
    checks.append("parsed: %r" % (parsed,))
    for key, want in (("rss_before_mb", 582.7), ("rss_after_mb", 756.1),
                       ("runner_delta_mb", 173.4), ("orphans", 3),
                       ("pid", 12345), ("total", 200), ("failed", 0)):
        if parsed.get(key) != want:
            errors.append("%s: read %r, expected %r"
                          % (key, parsed.get(key), want))
    if parsed.get("reloaded") is not True:
        errors.append("a RELOADING line was not read as a reload: %r"
                      % parsed.get("reloaded"))
    quiet = sample.replace(
        "[reload] RELOADING: sources changed since the last run -- purged "
        "57 module(s) from the Mod directory",
        "[reload] reusing modules: sources unchanged since the last run "
        "(no reimport, no new generation)")
    parsed = M.parse_run_output(quiet)
    checks.append("quiet run reloaded=%r reason=%r"
                  % (parsed.get("reloaded"), parsed.get("reload_reason")))
    if parsed.get("reloaded") is not False:
        errors.append("a 'reusing modules' line was not read as no reload")
    return _ok(checks, errors)


def test_the_orphan_count_is_read_as_a_reload_counter(doc):
    """A count that only moves on a reloading run is a reload counter.

    That distinction is the whole answer to the "221 orphans" question:
    the count is a function of the number of RELOADS, not of the number
    of runs.
    """
    M = _instrument()
    errors = []
    checks = []
    records = [
        {"run": 1, "orphans": 3, "reloaded": True},
        {"run": 2, "orphans": 6, "reloaded": True},
        {"run": 3, "orphans": 6, "reloaded": False},
        {"run": 4, "orphans": 6, "reloaded": False},
    ]
    tracks, changed = M.orphan_count_tracks_reloads(records)
    checks.append("reloads only -> tracks=%s changed=%s" % (tracks, changed))
    if not tracks:
        errors.append("a count that moved only on reloads was not tracked")
    records = [
        {"run": 1, "orphans": 3, "reloaded": True},
        {"run": 2, "orphans": 6, "reloaded": False},
    ]
    tracks, changed = M.orphan_count_tracks_reloads(records)
    checks.append("moved without a reload -> tracks=%s changed=%s"
                  % (tracks, changed))
    if tracks:
        errors.append("a count that moved without a reload was tracked")
    return _ok(checks, errors)


# ----------------------------------------------------------------------
# the census, on a synthetic orphan
# ----------------------------------------------------------------------

def test_the_census_finds_an_orphan_and_names_its_holder(doc):
    """The census finds an orphan that is put in front of it.

    The orphan is a SYNTHETIC module object -- it is never registered in
    sys.modules and it is named after a Mod module, so the census treats
    it exactly as it treats a real orphaned generation.  Nothing is
    touched in sys.modules, so the test cannot leave a generation behind
    for the next run to count.
    """
    import types
    M = _instrument()
    errors = []
    checks = []
    fake = types.ModuleType("ArachNURBS")
    fake.__file__ = os.path.join(M.MOD_DIR, "ArachNURBS.py")
    fake.marker = "synthetic orphan for the #123 census test"
    # The holder is a module DICT, because that is how a real orphan is
    # held: a module-level `import X as Y` puts the module OBJECT into
    # the importing module's dict, and the dict outlives the purge.
    holder = types.ModuleType("synthetic_holder_123")
    holder.kept = fake
    census = M.collect_orphans()
    entries = [e for e in census["orphans"] if e["id"] == id(fake)]
    checks.append("census: %d orphan(s) among %d Mod module name(s); "
                  "the synthetic one is in the list: %s"
                  % (census["count"], census["mod_module_count"],
                     bool(entries)))
    if not entries:
        errors.append("the census did not find the synthetic orphan")
        return _ok(checks, errors)
    entry = entries[0]
    checks.append("entry: name=%s id=%s owners=%s"
                  % (entry["name"], entry["id"], entry["owners"]))
    if entry["name"] != "ArachNURBS":
        errors.append("the synthetic orphan was reported as %r"
                      % entry["name"])
    if not entry["owners"]:
        errors.append("the census named no holder for the synthetic orphan")
    elif not any("holder_123" in o for o in entry["owners"]):
        errors.append("the census did not name the holder module: %s"
                      % entry["owners"])
    return _ok(checks, errors)


ALL_TESTS = [
    test_the_instrument_is_reachable_and_manual,
    test_the_instrument_is_not_in_the_fast_tier,
    test_the_analyser_recovers_a_known_slope,
    test_a_drift_below_the_floor_is_not_called_a_drift,
    test_the_runner_lines_are_read,
    test_the_orphan_count_is_read_as_a_reload_counter,
    test_the_census_finds_an_orphan_and_names_its_holder,
]
