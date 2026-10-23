"""The runner's OWN module bookkeeping, measured on the live heap.

MANUAL: both tests here answer a question about the whole live interpreter
-- how many orphaned module generations it holds, and whether ONE run of
`ensure_fresh` changes that -- and answering it costs one full sweep of
every object in the process: `gc.collect()` (3-4 s here) plus a pass over
67 million tracked objects (2.4 s with the C-level type filter, 5.7 s
without).  Measured on the owner's long-lived GUI session, the pair took
12.5 s of a 256 s fast tier, for two assertions whose answer is a single
number -- a measurement sweep, not a unit invariant, which is the tier
rule `Tests/test_manual_tier.py` states.

What is LEFT in the fast tier, and is what the guard is for:

  * `Tests/test_module_generation.py::test_every_mod_module_shares_one_
    arachnurbs_generation` -- the #72 single-generation guard itself
    (0.06 s): every Mod module's `AN` is the one object `sys.modules`
    registers;
  * its mutation control (0.07 s), which plants a stale `AN` and requires
    the guard to catch it;
  * the location-purge rules (0.7 s), which is the defect the prefix purge
    caused;
  * `Tests/test_runner_memory.py` and `Tests/test_runner_timeout.py`, the
    cheap half of the runner's own contract.

Run these by name:

    python3 Tests/run_all.py runner_generations      # this module
    python3 Tests/run_all.py --manual                # the whole manual tier

Not deleted, and not weakened: the growth bar is the count
`Tests/silk_reload.py` recorded when the run started, exactly as before.
"""

import sys

from Tests import silk_reload


MANUAL = True


def _ok(checks, errors, passed=None):
    """A test fails when it collected errors, unless it says otherwise."""
    return {
        "pass": (not errors) if passed is None else passed,
        "checks": checks,
        "errors": errors,
    }


def test_unchanged_sources_perform_no_reimport(doc):
    """The runner's own guarantee, checked in the running process.

    ensure_fresh() is called with the fingerprint already recorded, so
    it must not touch sys.modules: same ArachNURBS object afterwards,
    and nothing purged. (If it ever purged mid-suite, every later test
    would run against a generation the collected functions do not
    belong to -- so this is worth asserting, not just hoping.)

    MANUAL because ensure_fresh reports the orphan count, and counting
    orphans is a sweep of the live heap (see the module docstring).
    """
    errors = []
    checks = []
    current = silk_reload.fingerprint()
    silk_reload.save_fingerprint(current)
    before = dict(sys.modules)
    an_before = id(sys.modules.get("ArachNURBS"))
    report = silk_reload.ensure_fresh(verbose=False)
    checks.append("ensure_fresh: reloaded=%s reason=%s"
                  % (report["reloaded"], report["reason"]))
    if report["reloaded"]:
        errors.append("ensure_fresh reloaded the suite mid-run: %s"
                      % report["reason"])
    if id(sys.modules.get("ArachNURBS")) != an_before:
        errors.append("ArachNURBS object changed during a no-op reload check")
    changed = [n for n in before if sys.modules.get(n) is not before[n]]
    if changed:
        errors.append("sys.modules entries changed during a no-op check: %r"
                      % (changed,))
    checks.append("no sys.modules entry changed")
    return _ok(checks, errors)


def test_no_new_orphan_module_generations(doc):
    """A run must not pin module generations of its own.

    An orphan here is a live module object under the Mod directory that
    sys.modules no longer names: a generation something still holds after
    a purge. They are reachable, not garbage, so gc cannot collect them --
    which is why this counts objects.

    The bar is GROWTH WITHIN THIS RUN, measured against the count
    Tests/silk_reload.py recorded when the run started. An absolute zero
    is not reachable from test code: FreeCAD keeps a Python instance per
    command it registers with Gui.addCommand, and ~30 of them belong to
    legacy Control*/Cubic* modules that nothing re-imports after a purge,
    so those generations survive until FreeCAD restarts. What must never
    happen is this run adding one of its own -- which is what a retained
    run_tests frame did (its _patch_dialogs 'saved' list of
    (module, popup.tipsDialog) pairs pinned every module it touched).

    The interpreter's saved traceback is test-owned state and is cleared
    here first: FreeCAD prints exceptions raised inside C++ slots
    (SilkBlend._DeleteWatcher.slotDeletedObject during a document close)
    through the excepthook, and a traceback keeps every frame of the run
    that raised it -- pinning that run's whole generation.
    """
    errors = []
    checks = []
    silk_reload.clear_exception_state()
    # ONE sweep of the live module objects serves both halves of this
    # guard -- the orphan count, and "the registered object is one of the
    # live ones".  Asking `gc.get_objects()` again per watched name swept
    # the whole heap once more each time (4 x 6 s on the owner's session).
    live = silk_reload.live_module_objects()
    orphans = []
    for name, objs in sorted(live.items()):
        registered = sys.modules.get(name)
        for obj in objs:
            if obj is not registered:
                orphans.append((name, id(obj)))
    by_name = {}
    for name, _ in orphans:
        by_name[name] = by_name.get(name, 0) + 1
    baseline = silk_reload.load_state().get("orphans")
    checks.append("%d orphan generation(s) now, %s recorded when this run "
                  "started" % (len(orphans), baseline))
    if baseline is None:
        checks.append("no baseline recorded -- nothing to compare")
    elif len(orphans) > baseline:
        errors.append(
            "this run pinned %d new orphan generation(s) (baseline %d): %s"
            % (len(orphans) - baseline, baseline,
               ", ".join("%s x%d" % (n, by_name[n]) for n in sorted(by_name))))
    else:
        checks.append("no growth during this run")
    if orphans:
        checks.append("retained from earlier runs: %s"
                      % ", ".join("%s x%d" % (n, by_name[n])
                                  for n in sorted(by_name)))
    # The current generation must be registered, not orphaned: a module
    # object in sys.modules that is not the one gc sees is a split
    # identity, which is what a half-applied reload looks like.
    for name in ("ArachNURBS", "Silk_tooltips", "SilkPatch", "SilkMachinery"):
        mods = live.get(name) or []
        if not mods:
            checks.append("%s: not imported in this run" % name)
        elif sys.modules.get(name) not in mods:
            errors.append("%s: registered module object is not among the live "
                          "ones (split identity)" % name)
    return _ok(checks, errors)


ALL_TESTS = [
    test_unchanged_sources_perform_no_reimport,
    test_no_new_orphan_module_generations,
]
