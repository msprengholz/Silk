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

Also here: resident-memory reading (/proc/<pid>/status VmRSS) and a
report of orphaned module generations (module objects that are alive
but no longer in sys.modules -- the fingerprint of a pinner).

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
    """
    if isinstance(value, types.ModuleType):
        return value.__name__ if value.__name__ in names else None
    for cand in (value, type(value)):
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
    """True when *value* demonstrably belongs to a superseded generation.

    Positive evidence only -- anything we cannot prove stale is left
    alone. A value is stale when the module that defines it is still
    registered but is a different object than the one that defined it:

    * a module object that sys.modules no longer names,
    * a function/class the live module does not bind (identically),
    * an instance whose class is not the live module's class.

    Containers (list/tuple/set) are stale when any element is, which is
    how the namespace's old `edges` / `funcs` / `panels` bindings go.
    """
    if depth > 3:
        return False
    if isinstance(value, (str, bytes, bytearray, int, float, bool, complex,
                          type(None))):
        return False
    if isinstance(value, dict):
        return False
    if isinstance(value, (list, tuple, set, frozenset)):
        try:
            items = list(value)[:20000]
        except Exception:
            return False
        return any(_is_stale(item, names, depth + 1) for item in items)
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
        if any(key.startswith(p) for p in extra_prefixes) or _is_stale(
            namespace.get(key), names
        ):
            del namespace[key]
            dropped.append(key)
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
        cleared = clear_stale_namespace(namespace, mod_dir)
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