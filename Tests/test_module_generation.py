"""Reload / single-generation guards (ticket #72).

The invariant these assert: **after a reload cycle, every module under
the Mod directory references the same single ArachNURBS object.**

It was silently violated for the life of the old prefix-only purge in
Tests/run_all.py. Roughly 25 of the 57 top-level Mod .py files are
named none of Silk / Tests / ArachNURBS (ControlGrid44, ControlPoly4,
CubicSurface_64, BoundarySpline, Point_onCurve, ...), so they survived
the purge carrying their old bindings while SilkPatch / SilkBlend /
SilkMachinery were re-imported against a fresh ArachNURBS. A 168/168
green suite was validating one generation of the maths against the
surfaces built by another.
"""

import gc
import os
import sys
import tempfile
import types

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from Tests import silk_reload  # noqa: E402

MOD_DIR = silk_reload.MOD_DIR


# ----------------------------------------------------------------------
# helpers
# ----------------------------------------------------------------------

def _find_split_brain(modules=None):
    """Mod-directory modules whose AN is not the live ArachNURBS.

    Returns (offenders, checked) where offenders is a list of
    (module name, its AN id, live ArachNURBS id).
    """
    modules = sys.modules if modules is None else modules
    live_an = modules.get("ArachNURBS")
    offenders = []
    checked = []
    for name in sorted(modules):
        mod = modules[name]
        if not silk_reload.is_mod_module(mod):
            continue
        an = getattr(mod, "AN", None)
        if an is None:
            continue  # a Mod module that does not use ArachNURBS
        checked.append(name)
        if an is not live_an:
            offenders.append((name, id(an), id(live_an)))
    return offenders, checked


def _ok(checks, errors, passed=None):
    """A test fails when it collected errors, unless it says otherwise."""
    return {
        "pass": (not errors) if passed is None else passed,
        "checks": checks,
        "errors": errors,
    }


# ----------------------------------------------------------------------
# THE GUARD
# ----------------------------------------------------------------------

def test_every_mod_module_shares_one_arachnurbs_generation(doc):
    """One ArachNURBS for the whole Mod directory, after reload.

    The assertion whose absence let a split-brain suite report 168/168.
    """
    live_an = sys.modules.get("ArachNURBS")
    errors = []
    checks = []
    if live_an is None:
        return _ok(checks, ["ArachNURBS is not in sys.modules -- nothing to check"])
    offenders, checked = _find_split_brain()
    checks.append("ArachNURBS generation id %d" % id(live_an))
    checks.append("%d Mod-directory module(s) bind AN" % len(checked))
    for name, an_id, live_id in offenders:
        errors.append(
            "split brain: %s (%s) has AN=0x%x but sys.modules['ArachNURBS'] "
            "is 0x%x" % (name, getattr(sys.modules[name], "__file__", "?"),
                         an_id, live_id)
        )
    if not offenders:
        checks.append("all %d AN bindings are the same object" % len(checked))
    return _ok(checks, errors)


def test_the_guard_fails_on_a_planted_stale_binding(doc):
    """Mutation check, permanent: plant one stale AN and the guard must
    catch it. Keeps the guard above honest -- a guard that cannot fail is
    not a guard."""
    live_an = sys.modules["ArachNURBS"]
    victim = None
    for name in ("ControlGrid44", "SilkPatch", "SilkMachinery", "SilkBlend"):
        mod = sys.modules.get(name)
        if mod is not None and hasattr(mod, "AN"):
            victim = mod
            break
    if victim is None:
        return _ok([], ["no Mod module with an AN binding is loaded -- "
                        "cannot plant"])
    original = victim.AN
    errors = []
    checks = []
    try:
        # A module object from a superseded generation: nothing about it
        # is "None-ish", it is simply not the registered ArachNURBS.
        victim.AN = types.ModuleType("ArachNURBS_from_an_older_run")
        offenders, _ = _find_split_brain()
        checks.append("planted a stale AN module on %s" % victim.__name__)
        if not any(name == victim.__name__ for name, _, _ in offenders):
            errors.append(
                "the guard did NOT flag %s's planted stale AN -- "
                "the guard is broken" % victim.__name__
            )
    finally:
        victim.AN = original
    offenders, _ = _find_split_brain()
    if offenders:
        errors.append("planted binding leaked past restore: %r" % (offenders,))
    if not errors:
        checks.append("guard flagged the planted binding and restore was clean")
    return _ok(checks, errors)


# ----------------------------------------------------------------------
# purge rule
# ----------------------------------------------------------------------

def test_prefix_only_purge_would_leave_split_brain(doc):
    """The bug, kept executable.

    Builds the exact split brain the old prefix purge produced -- a
    ControlGrid44 pinned to a superseded ArachNURBS -- and shows that the
    old name-prefix rule leaves it behind while the location rule takes
    it. If someone reintroduces the prefix purge, this is what breaks.
    """
    errors = []
    checks = []
    live_an = sys.modules["ArachNURBS"]

    # A fake sys.modules: the live ArachNURBS, a Silk module, a Tests
    # module, and the helper modules the prefix rule used to miss.
    stale_an = types.ModuleType("ArachNURBS")

    def _fake(name, an):
        m = types.ModuleType(name)
        m.__file__ = os.path.join(MOD_DIR, name.split(".")[-1] + ".py")
        m.AN = an
        return m

    fake = {
        "ArachNURBS": live_an,
        "SilkPatch": _fake("SilkPatch", live_an),
        "Tests.test_chain": _fake("Tests.test_chain", live_an),
    }
    missed_by_prefix = [
        "ControlGrid44", "ControlPoly4", "CubicSurface_64", "BoundarySpline",
        "Point_onCurve", "ControlGrid64", "CubicCurve_4", "CubicSurface_44",
    ]
    for name in missed_by_prefix:
        fake[name] = _fake(name, stale_an)

    def prefix_purge(modules):
        for m in list(modules):
            if m.startswith("Silk") or m.startswith("Tests") or m.startswith("ArachNURBS"):
                del modules[m]

    prefix_purge(dict(fake))
    survivors = [n for n, m in fake.items()
                 if getattr(m, "AN", None) is stale_an]
    checks.append("prefix-only purge leaves %d helper module(s) on the old "
                  "generation: %s" % (len(survivors), ", ".join(survivors)))
    if not survivors:
        errors.append("prefix-only purge unexpectedly cleaned everything -- "
                      "the premise of this test is wrong")
    if len(survivors) != len(missed_by_prefix):
        errors.append("expected %d survivors, got %d"
                      % (len(missed_by_prefix), len(survivors)))

    # The location rule on a fresh copy of the same world.
    location_copy = dict(fake)
    removed = silk_reload.purge_mod_modules(modules=location_copy)
    left = [n for n in location_copy
            if getattr(location_copy[n], "AN", None) is stale_an]
    checks.append("location purge removed %d module(s), %d left"
                  % (len(removed), len(left)))
    if left:
        errors.append("location purge left stale modules behind: %r" % (left,))
    if "ArachNURBS" in location_copy:
        errors.append("location purge left ArachNURBS registered")
    return _ok(checks, errors)


def test_location_purge_covers_every_mod_source_file(doc):
    """All 57 top-level Mod .py files (and the Tests package) are ours."""
    errors = []
    checks = []
    top = [p for p in silk_reload.mod_sources()
           if os.path.dirname(p) == MOD_DIR]
    names = silk_reload.mod_module_names()
    checks.append("%d top-level Mod .py files, %d mod_sources, %d module names"
                  % (len(top), len(silk_reload.mod_sources()), len(names)))
    if len(top) != 57:
        errors.append("expected 57 top-level Mod .py files, found %d"
                      % len(top))
    missing = []
    for path in top:
        name = os.path.splitext(os.path.basename(path))[0]
        if name not in names:
            missing.append(name)
    if missing:
        errors.append("these Mod files are not in mod_module_names(): %r"
                      % (missing,))
    # Every one of them is recognised as ours even with __file__ present.
    not_ours = []
    for name in sorted(names):
        m = types.ModuleType(name)
        m.__file__ = os.path.join(MOD_DIR, name.replace(".", os.sep) + ".py")
        if not silk_reload.is_mod_module(m):
            not_ours.append(name)
    if not_ours:
        errors.append("is_mod_module rejects: %r" % (not_ours,))
    checks.append("every Mod module name recognised by location")
    # ... and with __file__ missing (name derived from disk instead).
    fileless = []
    for name in sorted(names):
        m = types.ModuleType(name)
        m.__file__ = None
        if not silk_reload.is_mod_module(m):
            fileless.append(name)
    if fileless:
        errors.append("is_mod_module rejects (no __file__): %r" % (fileless,))
    checks.append("every Mod module name recognised with __file__ = None")
    # A non-Silk module must NOT be swept up.
    outside = types.ModuleType("json")
    outside.__file__ = os.path.join(os.path.dirname(os.__file__), "json", "__init__.py")
    if silk_reload.is_mod_module(outside):
        errors.append("is_mod_module wrongly claims the stdlib json module")
    checks.append("stdlib modules are left alone")
    return _ok(checks, errors)


# ----------------------------------------------------------------------
# reload only when the sources changed
# ----------------------------------------------------------------------

def test_fingerprint_detects_edits_and_force_reload(doc):
    """No edit -> no reimport; edit -> reimport; --force-reload -> reimport."""
    errors = []
    checks = []
    tmp = tempfile.mkdtemp(prefix="silk_reload_test_")
    try:
        path = os.path.join(tmp, "probe.py")
        with open(path, "w") as fh:
            fh.write("VALUE = 1\n")
        first = silk_reload.fingerprint(tmp)
        again = silk_reload.fingerprint(tmp)
        if first != again:
            errors.append("fingerprint is not stable for unchanged sources")
        checks.append("fingerprint stable across calls (%s...)" % first[:12])

        reload_, reason = silk_reload.needs_reload(first, first)
        if reload_:
            errors.append("unchanged sources asked for a reload: %s" % reason)
        checks.append("unchanged sources -> no reload (%s)" % reason)

        with open(path, "w") as fh:
            fh.write("VALUE = 2\n")  # same length, different content
        edited = silk_reload.fingerprint(tmp)
        reload_, reason = silk_reload.needs_reload(edited, first)
        if not reload_:
            errors.append("an edited file did NOT ask for a reload")
        checks.append("edited file -> reload (%s), hash %s"
                      % (reason, "changed" if edited != first else "UNCHANGED"))

        reload_, reason = silk_reload.needs_reload(first, first, force=True)
        if not reload_:
            errors.append("--force-reload did not force a reload")
        checks.append("--force-reload -> reload (%s)" % reason)
    finally:
        for fn in os.listdir(tmp):
            os.remove(os.path.join(tmp, fn))
        os.rmdir(tmp)
    return _ok(checks, errors)


def test_unchanged_sources_perform_no_reimport(doc):
    """The runner's own guarantee, checked in the running process.

    ensure_fresh() is called with the fingerprint already recorded, so
    it must not touch sys.modules: same ArachNURBS object afterwards,
    and nothing purged. (If it ever purged mid-suite, every later test
    would run against a generation the collected functions do not
    belong to -- so this is worth asserting, not just hoping.)
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


# ----------------------------------------------------------------------
# orphans
# ----------------------------------------------------------------------

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
    orphans = silk_reload.orphan_generations()
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
                      % ", ".join("%s x%d" % (n, by_name[n]) for n in sorted(by_name)))
    # The current generation must be registered, not orphaned: a module
    # object in sys.modules that is not the one gc sees is a split
    # identity, which is what a half-applied reload looks like.
    for name in ("ArachNURBS", "Silk_tooltips", "SilkPatch", "SilkMachinery"):
        live = [o for o in gc.get_objects()
                if isinstance(o, types.ModuleType) and o.__name__ == name]
        if not live:
            checks.append("%s: not imported in this run" % name)
        elif sys.modules.get(name) not in live:
            errors.append("%s: registered module object is not among the live "
                          "ones (split identity)" % name)
    return _ok(checks, errors)


ALL_TESTS = [
    test_every_mod_module_shares_one_arachnurbs_generation,
    test_the_guard_fails_on_a_planted_stale_binding,
    test_prefix_only_purge_would_leave_split_brain,
    test_location_purge_covers_every_mod_source_file,
    test_fingerprint_detects_edits_and_force_reload,
    test_unchanged_sources_perform_no_reimport,
    test_no_new_orphan_module_generations,
]