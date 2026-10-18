"""Module freshness for the Silk test runners (ticket #72).

Two jobs, both of them test infrastructure:

1. **Purge by file location, not by name prefix.** The Mod directory holds
   57 top-level .py files and roughly 25 of them are named none of
   Silk / Tests / ArachNURBS (ControlGrid44, ControlPoly4,
   CubicSurface_64, BoundarySpline, Point_onCurve, ...). The old
   prefix-only purge in Tests/run_all.py left those behind carrying
   their old bindings, so after a reload cycle two generations of
   ArachNURBS were live at once and the suite validated Silk's maths
   against one generation while the helpers that build the surfaces
   still ran the other. Here "is this module ours?" is answered by
   *where its file is*, so all 57 are caught whatever they are called
   and split-brain becomes structurally impossible.

2. **Only reload when the sources actually changed.** The human edits
   .py files while FreeCAD stays open, so the reload itself must stay
   -- but a re-run with no edits should not create a new generation of
   every module (each generation is retained by the things FreeCAD
   registers, so gratuitous reloads are the memory growth). The Mod
   directory is fingerprinted (mtime + size + sha256 per .py) and the
   fingerprint is kept in a small per-process file under the temp dir,
   because the FreeCAD process -- not this runner -- outlives the run,
   so a module global in run_all.py would not survive.

Also here: resident-memory reading (/proc/<pid>/status VmRSS), a report
of orphaned module generations (module objects that are alive but no
longer in sys.modules -- the fingerprint of a pinner), and the two
run-hygiene calls the long-lived GUI needs (ticket #79): capping the
uncapped Report View, and glibc malloc_trim at the end of a run.

Nothing in this module imports FreeCAD, so it is safe to import from
anywhere, including before the purge.
"""

import gc
import hashlib
import json
import os
import sys
import tempfile
import types

# .../Mod/Silk -- the FreeCAD Mod directory holding every Silk module.
MOD_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Subtrees that never hold importable Silk sources.
_SKIP_DIRS = {"__pycache__", "Resources", ".git", ".mypy_cache", ".pytest_cache"}

# Default RSS warning threshold for the runner (MB).
DEFAULT_RSS_WARN_MB = 2048.0


# ----------------------------------------------------------------------
# "is this module under the Mod directory?"
# ----------------------------------------------------------------------

def _norm(path):
    return os.path.normcase(os.path.realpath(path))


def is_under_mod(path, mod_dir=None):
    """True when *path* (a file or directory) lives inside the Mod dir.

    realpath on both sides so symlinked temp dirs (macOS /tmp) and
    relative __file__ values cannot smuggle a module past the check.
    Compares with a trailing separator so /Mod/SilkOther is not
    counted as inside /Mod/Silk.
    """
    if not path:
        return False
    root = _norm(mod_dir or MOD_DIR)
    try:
        target = _norm(path)
    except (TypeError, ValueError):
        return False
    return target == root or target.startswith(root + os.sep)


def mod_sources(mod_dir=None):
    """Every .py file under the Mod directory, as a sorted list of paths."""
    root = mod_dir or MOD_DIR
    out = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [
            d for d in dirnames if d not in _SKIP_DIRS and not d.startswith(".")
        ]
        for fn in filenames:
            if fn.endswith(".py"):
                out.append(os.path.join(dirpath, fn))
    return sorted(out)


def mod_module_names(mod_dir=None):
    """Module names derived from the files on disk under the Mod dir.

    'SilkPatch.py' -> 'SilkPatch', 'Tests/test_chain.py' ->
    'Tests.test_chain'. Used as a backstop for the location rule: a
    module whose __file__ is missing/None is still ours if a file of
    that name is sitting in the Mod directory.
    """
    root = os.path.realpath(mod_dir or MOD_DIR)
    names = set()
    for path in mod_sources(mod_dir):
        rel = os.path.relpath(os.path.realpath(path), root)
        parts = rel[: -len(".py")].split(os.sep)
        names.add(".".join(parts))
        names.add(parts[0])
    return names


def is_mod_module(mod, names=None, mod_dir=None):
    """True when *mod* is a Silk module: its file is under the Mod dir,
    or its name matches a source file there (covers __file__ == None)."""
    if mod is None:
        return False
    if is_under_mod(getattr(mod, "__file__", None), mod_dir):
        return True
    if names is None:
        names = mod_module_names(mod_dir)
    return getattr(mod, "__name__", None) in names


def purge_mod_modules(mod_dir=None, modules=None):
    """Delete every Silk module from sys.modules and return the names.

    The purge is by file location (see module docstring). Any module
    currently executing from those files keeps working -- Python
    functions hold their own globals -- so this is safe to call from
    inside a module that lives in the Mod directory.
    """
    modules = sys.modules if modules is None else modules
    names = mod_module_names(mod_dir)
    me = modules.get(__name__) if modules is sys.modules else None
    removed = []
    for name in list(modules.keys()):
        if name == __name__:
            continue
        mod = modules.get(name)
        if is_mod_module(mod, names, mod_dir):
            del modules[name]
            removed.append(name)
    if me is not None:
        # Keep exactly one object for this helper even though it is a
        # Mod-directory module and was purged like the rest.
        modules[__name__] = me
    return sorted(removed)


# ----------------------------------------------------------------------
# fingerprint: has anything on disk changed since the last run?
# ----------------------------------------------------------------------

def fingerprint(mod_dir=None):
    """A stable hash of every .py under the Mod dir.

    mtime_ns + size + sha256: the hash catches an edit that preserves
    size, the mtime catches a touch (so --force-reload style freshness
    checks stay conservative), and neither misses an actual change.
    ~1.4 MB of sources, so hashing every run is negligible.
    """
    digest = hashlib.sha256()
    root = os.path.realpath(mod_dir or MOD_DIR)
    for path in mod_sources(mod_dir):
        rel = os.path.relpath(os.path.realpath(path), root)
        try:
            st = os.stat(path)
            mtime, size = st.st_mtime_ns, st.st_size
            with open(path, "rb") as fh:
                content = fh.read()
        except OSError:
            mtime, size, content = -1, -1, b""
        digest.update(("%s|%d|%d|" % (rel, mtime, size)).encode())
        digest.update(hashlib.sha256(content).digest())
    return digest.hexdigest()


def fingerprint_path(pid=None):
    """Where the last-run fingerprint is kept.

    Per FreeCAD *process* (the pid is in the name): the process is what
    holds imported modules, so a restarted FreeCAD needs no reload and
    a still-running one does. A temp-dir file is the one store that
    outlives an XML-RPC call without touching FreeCAD's own config.
    """
    pid = os.getpid() if pid is None else pid
    return os.path.join(tempfile.gettempdir(), "silk_reload_fingerprint_%d.json" % pid)


def load_fingerprint(pid=None):
    path = fingerprint_path(pid)
    try:
        with open(path) as fh:
            return json.load(fh).get("fingerprint")
    except (OSError, ValueError):
        return None


def load_state(pid=None):
    """Everything the last run recorded: fingerprint plus diagnostics."""
    path = fingerprint_path(pid)
    try:
        with open(path) as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return {}


def save_fingerprint(fp, pid=None, mod_dir=None, **extra):
    path = fingerprint_path(pid)
    record = {"fingerprint": fp, "pid": os.getpid() if pid is None else pid,
              "mod_dir": os.path.realpath(mod_dir or MOD_DIR)}
    record.update(extra)
    try:
        with open(path, "w") as fh:
            json.dump(record, fh)
    except OSError:
        return None
    _sweep_stale_fingerprints(path)
    return path


def clear_exception_state():
    """Drop the interpreter's saved traceback.

    FreeCAD prints Python exceptions raised inside C++ slots (e.g.
    SilkBlend._DeleteWatcher.slotDeletedObject during a document close)
    through the normal excepthook, which leaves them in sys.last_traceback.
    A traceback keeps every frame of the run that raised it, and those
    frames reference the module generation they were executing -- so one
    such traceback pins a whole generation that no purge can free. Test
    infrastructure owns this state, so it is cleared at the end of a run.
    Returns the names actually cleared.
    """
    cleared = []
    for attr in ("last_traceback", "last_exc", "last_value", "last_type"):
        if getattr(sys, attr, None) is not None:
            try:
                setattr(sys, attr, None)
                cleared.append(attr)
            except (AttributeError, TypeError):
                pass
    return cleared


def _sweep_stale_fingerprints(keep_path):
    """Delete fingerprint files whose FreeCAD process is gone."""
    import glob as _glob
    for path in _glob.glob(os.path.join(tempfile.gettempdir(), "silk_reload_fingerprint_*.json")):
        if os.path.abspath(path) == os.path.abspath(keep_path):
            continue
        base = os.path.basename(path)
        try:
            pid = int(base.rsplit("_", 1)[1].split(".")[0])
        except (ValueError, IndexError):
            continue
        try:
            os.kill(pid, 0)
        except OSError:
            try:
                os.remove(path)
            except OSError:
                pass


def needs_reload(current, previous, force=False):
    """(bool, reason) -- is a reimport needed?"""
    if force:
        return True, "--force-reload"
    if previous is None:
        return True, "no fingerprint for this FreeCAD process (first run)"
    if previous != current:
        return True, "sources changed since the last run"
    return False, "sources unchanged since the last run"


# ----------------------------------------------------------------------
# the persistent execute_code namespace (ticket #72 part 3)
# ----------------------------------------------------------------------

def _silk_owner(value, names):
    """The Mod module that owns *value*, or None.

    An object belongs to a module if the module object is it, if it is a
    function/class/instance defined there, or -- for a bound method --
    if its owner is. Instances matter: a SilkEdge.Edge proxy carries no
    __module__ of its own, and those proxies are what kept whole old
    generations of SilkEdge alive.

    #78 + #105: the probes are ordered so the one that cannot raise comes
    first. `type(value).__module__` is an attribute of a type object;
    `value.__module__` is an attribute access on the value ITSELF, and an
    object of a CLOSED document refuses exactly that -- `ReferenceError:
    Cannot access attribute '__module__' of deleted object` under 1.1.3,
    `RuntimeError: Cannot access attribute '__class__' of deleted object`
    in the build that filed #105, where the `isinstance` above raised
    because its fallback asks the value for `__class__`. Those bindings
    accumulate because the RPC namespace is persistent by design, and one
    of them made every `run_all.py` invocation report "FreeCAD reported an
    error" -- 0 tests run, no diagnosis. Same mistake as the SilkBlend
    delete-watcher (#80); three occurrences, three places.

    Nothing is swallowed here: an access that raises is proof the value is
    dead, and _is_stale turns that proof into "drop it".
    """
    if isinstance(value, types.ModuleType):
        return value.__name__ if value.__name__ in names else None
    for cand in (type(value), value):
        name = getattr(cand, "__module__", None)
        if name in names:
            return name
    owner = getattr(value, "__self__", None)
    if owner is not None:
        name = type(owner).__module__
        if name in names:
            return name
    return None


def _is_stale(value, names, depth=0):
    """True when *value* must go: it belongs to a superseded generation, or
    it cannot be inspected at all.

    Evidence, not guesswork, is what removes a binding an agent set
    deliberately. A value is stale when the module that defines it is
    still registered but is a different object than the one that defined
    it:

    * a module object that sys.modules no longer names,
    * a function/class the live module does not bind (identically),
    * an instance whose class is not the live module's class.

    Containers (list/tuple/set) are stale when any element is, which is
    how the namespace's old `edges` / `funcs` / `panels` bindings go.

    The one case that is not evidence is an INSPECTION FAILURE -- and
    #105 is that experience. `isinstance` and `getattr` are what a sweep
    is made of, and an object of a CLOSED document answers both with an
    exception whose class is a FreeCAD detail (ReferenceError in 1.1.3,
    RuntimeError in the build that filed #105). Such a value cannot be a
    live Silk binding, so it is stale by definition; and converting the
    failure here, rather than enumerating the classes that may be raised,
    is what keeps the sweep -- and with it the reload -- unable to die on
    a value it exists to remove.
    """
    if depth > 3:
        return False
    try:
        return _proven_stale(value, names, depth)
    except Exception:
        return True


def _proven_stale(value, names, depth):
    """_is_stale's evidence: may raise while inspecting *value*."""
    if isinstance(value, (str, bytes, bytearray, int, float, bool, complex,
                          type(None))):
        return False
    if isinstance(value, dict):
        return False
    if isinstance(value, (list, tuple, set, frozenset)):
        # Iteration can refuse too (a closed document's own Objects list):
        # the raise reaches _is_stale's guard and the binding goes.
        return any(_is_stale(item, names, depth + 1)
                   for item in list(value)[:20000])
    name = _silk_owner(value, names)
    if name is None:
        return False
    live = sys.modules.get(name)
    if live is None:
        return False
    if isinstance(value, types.ModuleType):
        return live is not value
    if type(value).__module__ == name and not isinstance(
        value, (types.FunctionType, type)
    ):
        # An instance / bound method: stale iff its own class was replaced.
        return live is not type(value)
    attr = getattr(value, "__name__", None)
    if attr and getattr(live, attr, None) is value:
        return False
    return True


_PROTECTED_NAMES = ("FreeCAD", "App", "FreeCADGui", "Gui", "__builtins__",
                     "__name__", "__file__", "__doc__")


def clear_stale_namespace(namespace, mod_dir=None, extra_prefixes=()):
    """Drop namespace bindings that pin a superseded module generation.

    The MCP/RPC execute_code namespace is deliberately persistent
    ("sharing module-level variables between successive calls"), which
    is exactly why orphaned Silk_tooltips / ControlGrid44 / ... objects
    survived a purge that removed them from sys.modules: something
    outside sys.modules still referenced the old module, and the
    namespace is the usual something.

    Only names with positive evidence of staleness are removed, so a
    live binding an agent set deliberately survives. Returns the sorted
    names dropped.
    """
    names = mod_module_names(mod_dir)
    dropped = []
    for key in list(namespace.keys()):
        if key in _PROTECTED_NAMES:
            continue
        try:
            hit = any(key.startswith(p) for p in extra_prefixes) or _is_stale(
                namespace.get(key), names
            )
        except Exception:
            # The binding cannot be inspected (an object of a closed
            # document, whose exception class is a FreeCAD detail -- #78
            # caught ReferenceError, #105 met RuntimeError from the same
            # access). We cannot prove what it was, but we can prove it is
            # useless: a deleted object can never be a live Silk module.
            # Drop it rather than fail the run, whatever it raised.
            hit = True
        if hit:
            del namespace[key]
            dropped.append(key)
    if dropped:
        # #78: visible, because a silent namespace clear is how this hid
        # for so long -- 21 dead bindings accumulated with nothing to say
        # so, until one of them failed every run in the session.
        print("[leak] cleared %d stale RPC namespace binding(s): %s"
              % (len(dropped), ", ".join(sorted(dropped)[:12])
                 + (" ..." if len(dropped) > 12 else "")))
    return sorted(dropped)


_RUNNER_NAMES = ("suite", "run_tests", "funcs", "summary", "save_dir", "saved",
                 "_save_dir", "_saved", "_p", "_n", "_e", "_m")


def clear_runner_namespace(namespace):
    """Remove the names a previous run_all remote run left behind.

    Called at the end of a run so the runner leaves no reference to the
    generation it just ran (it must not pin what it purges next time).
    The current remote code binds nothing at module level any more (it
    runs inside a function), so this only sweeps older runners' leftovers.
    """
    dropped = []
    for key in list(namespace.keys()):
        if key == "_silk_run":
            continue  # the function currently executing this run
        if key in _RUNNER_NAMES:
            del namespace[key]
            dropped.append(key)
    return sorted(dropped)


# ----------------------------------------------------------------------
# entry point used by the runners
# ----------------------------------------------------------------------

def ensure_fresh(force=False, namespace=None, mod_dir=None, pid=None,
                 keep_namespace=False, verbose=True):
    """Make sure this FreeCAD process runs current Silk sources.

    Returns a report dict: {"reloaded", "reason", "removed",
    "namespace_cleared", "orphans", "fingerprint", "previous"}.

    * reimports only when the Mod sources changed (or --force-reload),
    * purges by file location when it does,
    * clears stale bindings in *namespace* (the RPC execute_code
      namespace) either way, since those pin old generations even when
      no reload happens,
    * records the orphan-generation count as the baseline the next run
      is measured against.
    """
    mod_dir = mod_dir or MOD_DIR
    current = fingerprint(mod_dir)
    previous = load_fingerprint(pid)
    reload_, reason = needs_reload(current, previous, force)
    cleared = []
    if namespace is not None and not keep_namespace:
        try:
            cleared = clear_stale_namespace(namespace, mod_dir)
        except Exception as exc:
            # #105's rule at the call site: the sweep can never fail the
            # reload. The reload is how one recovers from the state that
            # broke the sweep, so a failure escaping here takes the
            # recovery with it -- and run_all.py reports that as 0 tests
            # run, with no diagnosis.
            print("[leak] stale-binding sweep failed (%s: %s) -- continuing"
                  % (type(exc).__name__, exc))
    removed = []
    if reload_:
        removed = purge_mod_modules(mod_dir)
    orphans = len(orphan_generations(mod_dir))
    save_fingerprint(current, pid, mod_dir, orphans=orphans)
    report = {
        "reloaded": reload_,
        "reason": reason,
        "removed": removed,
        "removed_count": len(removed),
        "namespace_cleared": cleared,
        "orphans": orphans,
        "fingerprint": current,
        "previous": previous,
        "mod_dir": os.path.realpath(mod_dir),
        "fingerprint_path": fingerprint_path(pid),
    }
    if verbose:
        for line in describe(report):
            print(line)
    return report


def describe(report):
    """Human-readable [reload] / [leak] lines for the runner to echo."""
    lines = []
    if report["reloaded"]:
        lines.append(
            "[reload] RELOADING: %s -- purged %d module(s) from the Mod directory"
            % (report["reason"], report["removed_count"])
        )
    else:
        lines.append("[reload] reusing modules: %s (no reimport, no new generation)"
                     % report["reason"])
    if report["namespace_cleared"]:
        lines.append("[reload] dropped %d stale namespace binding(s): %s"
                     % (len(report["namespace_cleared"]),
                        ", ".join(report["namespace_cleared"][:20])))
    lines.append("[leak] %d orphaned Mod module generation(s) pinned outside "
                 "sys.modules" % report["orphans"])
    return lines


# ----------------------------------------------------------------------
# memory / diagnostics
# ----------------------------------------------------------------------

def rss_mb(pid=None):
    """Resident set size in MB from /proc/<pid>/status, or None."""
    pid = os.getpid() if pid is None else pid
    try:
        with open("/proc/%d/status" % pid) as fh:
            for line in fh:
                if line.startswith("VmRSS:"):
                    return int(line.split()[1]) / 1024.0
    except OSError:
        return None
    return None


def orphan_generations(mod_dir=None, modules=None, collect=True):
    """Live module objects that are NOT in sys.modules -- i.e. pinned.

    Returns [(name, id), ...] sorted by name. Anything here is a
    retention leak: a module the purge dropped while something outside
    sys.modules still referenced it. gc cannot collect them -- they are
    reachable, not garbage -- which is why this counts objects.

    collect=True runs a full collection first so the count means
    "still pinned" rather than "not collected yet": an uncollected
    traceback cycle from the run that just finished would otherwise be
    counted as a leak and make the number swing by a few per run.
    """
    names = mod_module_names(mod_dir)
    if collect:
        gc.collect()
    live = {}
    for obj in gc.get_objects():
        if isinstance(obj, types.ModuleType):
            name = getattr(obj, "__name__", None)
            if name in names:
                live.setdefault(name, []).append(obj)
    modules = sys.modules if modules is None else modules
    out = []
    for name, objs in live.items():
        registered = modules.get(name)
        extra = [o for o in objs if o is not registered]
        for o in extra:
            out.append((name, id(o)))
    return sorted(out)


# ----------------------------------------------------------------------
# the Report View (#79)
# ----------------------------------------------------------------------
#
# FreeCAD's Report View is a QTextEdit whose objectName is "Report view",
# and its QTextDocument has maximumBlockCount() == 0 -- UNCAPPED. That
# means it retains every console message the process has ever printed, for
# the life of the process. Measured in #79: after five runs of one test
# module it held 2,293,056 characters across 30,789 blocks, and RSS grew
# ~20 MB per run, linearly, with no plateau. That is the leak.
#
# It was nearly missed twice over. Clearing the Report View on its own
# moved RSS by 0 MB -- glibc keeps the freed memory in its arena, so the
# honest measurement is a malloc_trim(0) AFTER the release, which
# returned 162 MB. And the trim alone, run while the buffer was still
# full, reclaimed 6 MB and looked like a dead end.
#
# 2000 is the value verified by hand in #79: with the cap in place, four
# further runs of the same module went 593 -> 621 -> 638 -> 641 -> 643 MB
# (+28, +17, +3, +2) -- growth stops after three runs.
#
# This is a DELIBERATE, VISIBLE compromise. A long run will scroll the
# Report View's history off the top: the oldest messages are dropped and
# cannot be recovered. That is the price of not adding ~20 MB per run to
# the user's own long-lived GUI. Do NOT "restore" the cap to 0 thinking it
# looks more polite -- uncapped is the bug, and it is the single largest
# thing this runner was growing.
REPORT_VIEW_BLOCK_CAP = 2000

# "No opinion" sentinel, distinct from an explicit None. cap_report_view
# has to be able to say "there is no Gui at all" (None) as well as "go
# and look one up" (unset).
_UNSET = object()


def cap_report_view(block_cap=REPORT_VIEW_BLOCK_CAP, gui=_UNSET,
                    main_window=_UNSET):
    """Cap the Report View's buffer. Returns a status dict, never raises.

    The Report View is the biggest thing a big suite grows in a long-lived
    GUI (#79), and its document is uncapped by default. This sets
    maximumBlockCount to *block_cap* so old blocks are dropped instead of
    retained for the life of the process.

    Deliberately total: no main window, no Gui (a console FreeCAD), no
    Report view, several of them, or a widget whose C++ half has already
    been deleted all produce a status and a return. A memory-hygiene fix
    that can abort a test run is worse than the leak it prevents.

    *gui* / *main_window* exist so the test can exercise every one of
    those paths without a GUI; leave them unset to use the real ones.

    Returns {"status", "cap", "changed", "kept", "detail"} where status is
    one of: capped, already-capped, no-gui, no-main-window, no-qt,
    not-found, error. "capped" means at least one widget was changed;
    "already-capped" means every Report view found was already capped at
    or below *block_cap*.
    """
    report = {"status": "error", "cap": block_cap, "changed": [], "kept": [],
              "detail": ""}

    if gui is _UNSET:
        try:
            import FreeCADGui as gui  # noqa: F811 -- deliberate rebinding
        except Exception:
            gui = None
    if gui is None:
        report["status"] = "no-gui"
        return report
    try:
        window = gui.getMainWindow() if main_window is _UNSET else main_window
    except Exception as exc:
        report["status"] = "error"
        report["detail"] = "getMainWindow: %r" % (exc,)
        return report
    if window is None:
        report["status"] = "no-main-window"
        return report

    try:
        from PySide import QtWidgets
    except Exception:
        try:
            from PySide2 import QtWidgets  # FreeCAD < 0.21
        except Exception as exc:
            report["status"] = "no-qt"
            report["detail"] = repr(exc)
            return report

    try:
        edits = list(window.findChildren(QtWidgets.QTextEdit))
    except Exception as exc:
        report["status"] = "error"
        report["detail"] = "findChildren: %r" % (exc,)
        return report

    problems = []
    for widget in edits:
        try:
            if widget.objectName() != "Report view":
                continue
        except Exception as exc:
            # A C++ object deleted since findChildren ran.
            problems.append("objectName: %r" % (exc,))
            continue
        try:
            document = widget.document()
            current = document.maximumBlockCount()
            if 0 < current <= block_cap:
                # Already capped at least this tightly. A cap somebody
                # chose is not ours to loosen.
                report["kept"].append(current)
                continue
            document.setMaximumBlockCount(block_cap)
            report["changed"].append(block_cap)
        except Exception as exc:
            problems.append("setMaximumBlockCount: %r" % (exc,))

    if problems:
        report["status"] = "error"
        report["detail"] = "; ".join(problems)
        return report
    report["status"] = "capped" if report["changed"] else (
        "already-capped" if report["kept"] else "not-found")
    return report


# ----------------------------------------------------------------------
# malloc_trim (#79)
# ----------------------------------------------------------------------

def malloc_trim(loader=None, platform=None):
    """Ask glibc to return free heap memory to the OS. Never raises.

    ORDER MATTERS, and this is the whole trick (#79). glibc holds freed
    memory in its arena rather than giving it back, so a trim only
    reclaims what is actually free: trimming while the Report View is
    still holding its buffer returned 6 MB, and trimming right after
    that buffer was released returned 162 MB. The trim is the second
    half of cap_report_view, not a substitute for it -- it has nothing
    to return unless something was released first.

    *loader* and *platform* are injection points for the test. Guarded on
    every path: not glibc, no ctypes, no libc, no symbol, or a raising
    call all return {"trimmed": False, "reason": ...}.
    """
    if not str(sys.platform if platform is None else platform).startswith("linux"):
        return {"trimmed": False, "reason": "not glibc (%s)"
                % (platform if platform is not None else sys.platform,)}
    try:
        import ctypes
    except ImportError as exc:
        return {"trimmed": False, "reason": "no ctypes: %r" % (exc,)}
    try:
        libc = (loader or (lambda: ctypes.CDLL("libc.so.6")))()
        trim = libc.malloc_trim
    except Exception as exc:
        return {"trimmed": False, "reason": "no libc malloc_trim: %r" % (exc,)}
    rss_before = rss_mb()
    try:
        rc = trim(0)
    except Exception as exc:
        return {"trimmed": False, "reason": "malloc_trim raised: %r" % (exc,),
                "rss_before": rss_before}
    rss_after = rss_mb()
    out = {"trimmed": True, "reason": "", "rc": rc,
           "rss_before": rss_before, "rss_after": rss_after}
    if rss_before is not None and rss_after is not None:
        out["reclaimed_mb"] = rss_before - rss_after
    return out


# ----------------------------------------------------------------------
# reporting
# ----------------------------------------------------------------------

_CAP_NOTE = ("maximumBlockCount 0 means KEEP EVERY MESSAGE EVER PRINTED "
             "-- see silk_reload.REPORT_VIEW_BLOCK_CAP")


def describe_memory(report_view=None, trim=None):
    """[report] lines: what was capped, and what the trim gave back.

    Separate from describe(), which reports on module generations: a
    future session has to be able to see this fix working from the run
    output rather than re-derive the measurement from scratch.
    """
    lines = []
    if report_view:
        status = report_view.get("status")
        cap = report_view.get("cap")
        detail = report_view.get("detail") or ""
        if status == "capped":
            lines.append(
                "[report] capped the Report View at %d blocks -- %s (%d widget(s))"
                % (cap, _CAP_NOTE, len(report_view.get("changed") or [])))
        elif status == "already-capped":
            lines.append("[report] Report View already capped at %s (at or below "
                         "%d), left alone" % (report_view.get("kept"), cap))
        else:
            lines.append("[report] no Report View to cap: %s%s"
                         % (status, " (%s)" % detail if detail else ""))
    if trim is not None:
        if not trim.get("trimmed"):
            lines.append("[report] malloc_trim(0) skipped: %s"
                         % (trim.get("reason") or "unknown reason",))
        else:
            before = trim.get("rss_before")
            after = trim.get("rss_after")
            gave = trim.get("reclaimed_mb")
            if gave is None:
                lines.append("[report] malloc_trim(0) ran (rss unavailable)")
            elif gave > 0:
                lines.append("[report] malloc_trim(0) ran: rss %.1f -> %.1f MB "
                             "(%.1f MB back to the OS)" % (before, after, gave))
            else:
                # Honest, not omitted: a trim that returns nothing is the
                # normal case when the run freed little.
                lines.append("[report] malloc_trim(0) ran: rss %.1f -> %.1f MB "
                             "(nothing new returned)" % (before, after))
    return lines