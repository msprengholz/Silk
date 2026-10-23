"""
MANUAL MEASUREMENT -- is the runner's memory growing per RUN, or is the
BASELINE drifting? (ticket #123)

THE QUESTION, AS #123 PUTS IT
    A fresh FreeCAD measured RSS 582.7 MB before the first run, then
    582.7 -> 756.1 (+173.4) and 792.5 -> 821.8 (+29.3), with
    "[leak] 3 orphaned generations".  So: does the BASELINE drift across
    runs in one process (the number before run N+1 is higher than the
    number after run N), or is that steady-state churn?  And what are the
    orphans?

WHAT THIS INSTRUMENT MEASURES
    One process, N runs of the fast tier, and for every run:

      * rss_before / rss_after -- the runner's own reading (the same
        numbers the "[rss]" line prints), so the measurement is the one
        the owner already sees;
      * the INTER-RUN GAP -- rss_before(run N+1) - rss_after(run N).
        This is the quantity the runner's own delta CANNOT see: the
        runner measures a window that starts at the top of a run and ends
        at the bottom of the same run, so everything that happens between
        two runs (the RPC round trip, the Report View, FreeCAD's own
        caches) is invisible to it.  The gap is where a drifting baseline
        has to show up.
      * the orphan count the runner printed ("[leak] N orphaned ...");
      * whether the run RELOADED the Mod sources (the "[reload]" line) --
        without this the orphan series cannot be read, because the count
        is a function of reloads, not of runs (see below);
      * a client-side RSS sample of the FreeCAD process at the same
        moments, from a DIFFERENT reader than the runner's, as an
        independent cross-check of the in-process reading.

    After the series, ONE census runs inside FreeCAD: the orphan module
    objects that are alive but no longer in sys.modules, and WHO holds
    them (the referrers, named).

THE ORPHAN COUNT, AND WHY IT IS NOT A PER-RUN COUNT
    `Tests/silk_reload.orphan_generations()` counts live module objects
    that (a) are Mod modules by FILE LOCATION, (b) are alive, and (c) are
    not the object sys.modules registers under that name.  A module
    object can only become such an orphan when a PURGE removed it from
    sys.modules while something still referenced it -- and a purge
    happens only when the Mod sources CHANGED (or --force-reload).  So
    the number counts ORPHANED GENERATIONS, and generations are minted by
    reloads: the count is a function of the number of RELOADS, not of the
    number of runs.  A session that edits files between runs grows the
    count; a session that does not edit files keeps it constant.  The
    series below separates the two, because the reload flag is recorded
    next to the count.

    The census names the orphans and their holders.  The static reading
    of the sources says what to expect: about forty Mod modules do
    `import ArachNURBS as AN` and `import Silk_dummy` at MODULE level
    (and fifteen also `import Silk_tooltips`), so every surviving
    generation's module dict holds those three module OBJECTS.  When the
    next generation is imported, the old three are no longer registered
    and become orphans -- three per reload.  That is a HYPOTHESIS from
    reading the code, and the census is what settles it: the instrument
    prints the names and the holders, not the hypothesis.

FLOOR AND CROSS-CHECK
    The RSS reading's own noise is measured, not assumed: the instrument
    reads the same counter many times over and publishes the spread, and
    it compares the runner's in-process reading with its own
    out-of-process reading of the same process at the same moment.  A
    drift smaller than that disagreement is not a measurement.

HOW TO RUN IT (the owner runs this -- the gate has not)
    The measurement needs a live FreeCAD with its RPC server (the one the
    normal runner uses).  ONE command does everything:

        python3 Tests/rss_baseline_measure.py --runs 5

    That runs `python3 Tests/run_all.py` (the real runner) five times
    against the SAME running FreeCAD, samples the process between the
    runs, takes the orphan census at the end, and writes the raw output
    and the readings to a timestamped directory under /tmp.  The path is
    printed at the end; keep it -- the raw output is the measurement.

    Options:
        --runs N        how many runs (default 5)
        --port P        RPC port (default 9875, or $SILK_RPC_PORT)
        --filter F      a test filter for the runner (the control run:
                        a cheap filter separates the RUNNER's own cost
                        from the SUITE's cost)
        --out-dir D     where the raw output goes (default /tmp/...)
        --in-process    run the N runs inside THIS FreeCAD process
                        instead of driving the runner as a subprocess
                        (for `freecad -c "import Tests.rss_baseline_measure
                        as m; m.main(['--in-process','--runs','5'])"`)

MANUAL-ONLY: the file name is not `test_*.py`, so `Tests/suite.py` does
not discover it.  `Tests/test_continuity_instrument.py` asserts this
module imports, exposes `main`, and carries `MANUAL`; nothing else in the
suite runs it.  Nothing here is a production object or a fix.
"""

import ast
import contextlib
import io
import json
import os
import re
import subprocess
import sys
import tempfile
import time

MANUAL = True

# .../Mod/Silk -- the FreeCAD Mod directory holding every Silk module.
MOD_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if MOD_DIR not in sys.path:
    sys.path.insert(0, MOD_DIR)

DEFAULT_RUNS = 5
DEFAULT_PORT = 9875
PROBE_MARKER = "RSSBASELINE:"
OUT_ROOT = os.path.join(tempfile.gettempdir(), "silk_rss_baseline")

# The smallest growth over a whole series this instrument will call a
# drift, in MB.  The floor below is MEASURED (the spread of repeated
# readings, and the spread of the two readers' disagreement), and on a
# quiet process it can be 0 -- the kernel counter is exact.  A 0.02 MB
# wobble is a bookkeeping artefact, not a drift, so this floor exists
# to keep the verdict from being trigger-happy.  It is stated, not
# fitted: the numbers behind it are printed beside it.
MIN_DRIFT_MB = 1.0

# The modules whose generation identity is worth watching: the three that
# ~40 Mod modules import at module level (so every surviving generation
# pins them), plus the runner's own helpers.
WATCHED_MODULES = (
    "ArachNURBS", "Silk_dummy", "Silk_tooltips", "SilkMachinery",
    "SilkPatch", "SilkBlend", "Tests.suite", "Tests.mcp_harness",
    "Tests.silk_reload",
)


# ---------------------------------------------------------------------------
# the shared helper (imported lazily, never at module level)
# ---------------------------------------------------------------------------
#
# This module IS a Mod module.  A module-level `from Tests import
# silk_reload` would put the silk_reload MODULE OBJECT into this
# module's dict -- and a surviving module dict is exactly what the
# orphan count is made of.  The instrument must not change what it
# measures, so every Mod import here is function-local.

def _helper():
    """Tests.silk_reload -- the runner's own reload/memory helper."""
    from Tests import silk_reload
    return silk_reload


# ---------------------------------------------------------------------------
# pure analysis (no FreeCAD, no filesystem: unit-testable)
# ---------------------------------------------------------------------------

def least_squares_slope(series):
    """The slope of the least-squares line through *series*.

    x is the run index 0..n-1, y the value.  Pure arithmetic: no numpy,
    so the instrument has no dependency the measurement does not need.
    """
    n = len(series)
    if n < 2:
        return 0.0
    mean_x = (n - 1) / 2.0
    mean_y = sum(series) / float(n)
    num = sum((i - mean_x) * (y - mean_y) for i, y in enumerate(series))
    den = sum((i - mean_x) ** 2 for i in range(n))
    if not den:
        return 0.0
    return num / den


def classify_baseline(baseline, floor_mb, factor=3.0):
    """'drift' or 'steady' -- is the baseline growing beyond the floor?

    *baseline* is the RSS at the START of each run.  A growth that does
    not exceed *factor* x *floor_mb* over the whole series is not a
    measurement, so it is called 'steady'.  The floor is the instrument's
    own noise (the spread of repeated readings, cross-checked against a
    second reader), never a number picked to make the answer come out.
    """
    n = len(baseline)
    slope = least_squares_slope(baseline)
    span = (baseline[-1] - baseline[0]) if n >= 2 else 0.0
    growth = abs(slope) * max(n - 1, 0)
    limit = max(factor * max(float(floor_mb), 0.0), MIN_DRIFT_MB)
    return {
        "slope_mb_per_run": slope,
        "span_mb": span,
        "growth_mb": growth,
        "floor_mb": float(floor_mb),
        "limit_mb": limit,
        "runs": n,
        "verdict": "drift" if growth > limit else "steady",
    }


def parse_run_output(text):
    """The readings ONE runner invocation printed.

    Only the runner's own lines are read -- the same lines the owner
    already sees -- so the instrument measures the real runner and not a
    re-implementation of it.
    """
    out = {
        "rss_before_mb": None, "rss_after_mb": None, "runner_delta_mb": None,
        "pid": None, "orphans": None, "reloaded": None, "reload_reason": None,
        "passed": None, "total": None, "failed": None,
    }
    m = re.search(
        r"\[rss\] FreeCAD pid (\d+) resident memory: before ([0-9.]+) MB, "
        r"after ([0-9.]+) MB \(delta (-?[0-9.]+) MB\)", text)
    if m:
        out["pid"] = int(m.group(1))
        out["rss_before_mb"] = float(m.group(2))
        out["rss_after_mb"] = float(m.group(3))
        out["runner_delta_mb"] = float(m.group(4))
    m = re.search(r"\[leak\] (\d+) orphaned Mod module generation", text)
    if m:
        out["orphans"] = int(m.group(1))
    m = re.search(r"\[reload\] RELOADING: (.*?) -- purged", text)
    if m:
        out["reloaded"] = True
        out["reload_reason"] = m.group(1).strip()
    m = re.search(r"\[reload\] reusing modules: (.*?) \(no reimport", text)
    if m:
        out["reloaded"] = False
        out["reload_reason"] = m.group(1).strip()
    m = re.search(r"(\d+)/(\d+) passed, (\d+) failed", text)
    if m:
        out["passed"] = int(m.group(1))
        out["total"] = int(m.group(2))
        out["failed"] = int(m.group(3))
    return out


def orphan_count_tracks_reloads(records):
    """(tracks_reloads, runs_where_it_changed_without_one).

    True when the orphan count only ever changes on a reloading run.
    That is the signature of a RELOAD counter rather than a per-run
    counter: a count that grows on every run is a different animal from a
    count that grows exactly when a new generation was minted.
    """
    changed_without_reload = []
    prev = None
    for rec in records:
        count = rec.get("orphans")
        if count is None:
            continue
        if prev is not None and count != prev and not rec.get("reloaded"):
            changed_without_reload.append(rec.get("run"))
        prev = count
    return (not changed_without_reload), changed_without_reload


def verdict(records, analysis, floors):
    """The plain reading of a series, as a dict of statements.

    Three questions, kept apart on purpose:
      * is there a PER-RUN leak (the cost of a run growing run over run)?
      * is the BASELINE drifting (the start-of-run RSS growing)?
      * is the orphan count a REPORTING ARTEFACT (a reload counter)?

    The answer is a set of statements with the evidence attached, not a
    single label: the ticket asks for a measurement, and a measurement
    that answers "it depends" is allowed to say so.
    """
    notes = []
    deltas = [r["runner_delta_mb"] for r in records
              if r.get("runner_delta_mb") is not None]
    gaps = [r["inter_run_gap_mb"] for r in records
            if r.get("inter_run_gap_mb") is not None]
    per_run_slope = least_squares_slope(deltas) if len(deltas) >= 2 else 0.0
    gap_slope = least_squares_slope(gaps) if len(gaps) >= 2 else 0.0
    floor = max(float(floors.get("floor_mb", 0.0)), 1e-9)
    steps = max(len(deltas) - 1, 0)
    # A leak means the cost of a run GROWS.  A shrinking cost is the
    # opposite -- it is a warm-up (the first run pays for what the later
    # ones reuse), and it is not a leak.
    per_run_leak = (per_run_slope * steps) > 3.0 * floor
    per_run_warmup = (per_run_slope * steps) < -3.0 * floor
    baseline_drift = analysis.get("verdict") == "drift"
    tracks, changed = orphan_count_tracks_reloads(records)
    if per_run_leak:
        notes.append("the cost of a run GROWS across the series (%.1f MB/run "
                     "of slope, floor %.2f MB) -- a per-run leak"
                     % (per_run_slope, floor))
    elif per_run_warmup:
        notes.append("the cost of a run SHRINKS across the series (%.1f "
                     "MB/run of slope) -- that is a warm-up, not a leak"
                     % per_run_slope)
    else:
        notes.append("the cost of a run does not grow across the series "
                     "(slope %.1f MB/run, floor %.2f MB) -- no per-run leak"
                     % (per_run_slope, floor))
    if baseline_drift:
        notes.append("the BASELINE drifts: the RSS at the start of each run "
                     "grows %.1f MB/run (%.1f MB over the series) -- the "
                     "growth is NOT inside the run window"
                     % (analysis.get("slope_mb_per_run", 0.0),
                        analysis.get("span_mb", 0.0)))
    else:
        notes.append("the BASELINE does not drift beyond the floor (%.2f MB "
                     "over the series, floor %.2f MB) -- steady state"
                     % (analysis.get("span_mb", 0.0), floor))
    if tracks:
        notes.append("the orphan count changes ONLY on runs that reloaded the "
                     "Mod sources -- it counts ORPHANED GENERATIONS, so it "
                     "is a function of the number of reloads, not of the "
                     "number of runs")
    else:
        notes.append("the orphan count changed on runs that did NOT reload "
                     "(runs %s) -- it is not purely a reload counter"
                     % (changed,))
    return {
        "per_run_leak": bool(per_run_leak),
        "per_run_warmup": bool(per_run_warmup),
        "baseline_drift": bool(baseline_drift),
        "orphan_count_is_a_reload_counter": bool(tracks),
        "per_run_slope_mb": per_run_slope,
        "gap_slope_mb": gap_slope,
        "notes": notes,
    }


# ---------------------------------------------------------------------------
# the in-process census: what is pinned outside sys.modules, and by whom
# ---------------------------------------------------------------------------

def _module_dict_owners(objects=None):
    """{id(module.__dict__): module name} for every live module object.

    A module dict is the usual holder of another module OBJECT (a
    module-level `import X as Y` puts X into the importing module's
    dict), so naming the dict's owner names the pinner.  *objects* is the
    list to scan (default None = the whole live heap); the census's
    calibration hands in a synthetic pair instead of sweeping 67 million
    objects.
    """
    import gc
    import types
    is_module = types.ModuleType.__instancecheck__
    owners = {}
    for obj in filter(is_module, gc.get_objects() if objects is None
                      else objects):
        try:
            owners[id(obj.__dict__)] = obj.__name__
        except Exception:
            continue
    return owners


def describe_referrer(ref, dict_owners=None):
    """A short, human-readable name for a thing that holds a reference."""
    import types
    if isinstance(ref, types.ModuleType):
        return "module %s" % ref.__name__
    if isinstance(ref, dict):
        owner = (dict_owners or {}).get(id(ref))
        if owner:
            return "dict of module '%s'" % owner
        if "__qualname__" in ref and "__module__" in ref:
            return "class dict %s.%s" % (ref.get("__module__"),
                                         ref.get("__qualname__"))
        if "__name__" in ref:
            return "namespace dict of %r" % (ref.get("__name__"),)
        return "dict (%d keys)" % len(ref)
    if isinstance(ref, type):
        return "class %s.%s" % (getattr(ref, "__module__", "?"),
                                getattr(ref, "__name__", "?"))
    if isinstance(ref, types.FunctionType):
        return "function %s (defined in %s)" % (getattr(ref, "__name__", "?"),
                                                getattr(ref, "__module__", "?"))
    if isinstance(ref, types.MethodType):
        return "bound method %s" % (getattr(ref, "__qualname__", "?"),)
    if isinstance(ref, (list, tuple, set, frozenset)):
        return "%s (%d items)" % (type(ref).__name__, len(ref))
    if isinstance(ref, types.FrameType):
        return "frame %s:%d" % (os.path.basename(ref.f_code.co_filename),
                                ref.f_lineno)
    return type(ref).__name__


def collect_orphans(mod_dir=None, deep=False, objects=None):
    """The orphan module objects, and who holds them.

    Mirrors `Tests/silk_reload.orphan_generations` (the runner's own
    count) but keeps the OBJECTS, so each one can be asked who refers
    to it.  A full gc.collect() runs first, so the list means "still
    pinned" and not "not collected yet".

    *deep* adds a rough "how much is pinned behind this" size estimate.
    It walks the object graph, which costs time, so the measurement
    leaves it off by default.

    *objects* replaces the live heap as the census's input (None, the
    default, is `gc.get_objects()` and keeps the gc.collect()).  The
    instrument's calibration in `Tests/test_rss_baseline_measure.py`
    hands in a synthetic orphan pair instead: on a real session's heap
    the census costs 123 s, because it asks `gc.get_referrers` once per
    orphan and each of those is a full heap scan.  The instrument itself
    still runs the live sweep; a fast-tier test must not.
    """
    import gc
    import sys
    import types
    helper = _helper()
    names = helper.mod_module_names(mod_dir)
    if objects is None:
        gc.collect()
        objects = gc.get_objects()
    else:
        objects = list(objects)
    is_module = types.ModuleType.__instancecheck__
    live = {}
    for obj in filter(is_module, objects):
        name = getattr(obj, "__name__", None)
        if name in names:
            live.setdefault(name, []).append(obj)
    # The containers this function builds hold the very objects we are
    # about to ask about, so they would show up as "owners".  They are
    # excluded by identity -- and so are this file's own frames, which
    # hold the objects as locals.
    mine = {id(live), id(objects)}
    for objs in live.values():
        mine.add(id(objs))
    dict_owners = _module_dict_owners(objects)
    out = []
    for name, objs in sorted(live.items()):
        registered = sys.modules.get(name)
        for obj in objs:
            if obj is registered:
                continue
            owners = []
            try:
                referrers = gc.get_referrers(obj)
            except Exception:
                referrers = []
            mine.add(id(referrers))
            for ref in referrers:
                if id(ref) in mine:
                    continue
                if isinstance(ref, types.FrameType) and \
                        ref.f_code.co_filename == __file__:
                    continue
                try:
                    owners.append(describe_referrer(ref, dict_owners))
                except Exception:
                    continue
            entry = {
                "name": name,
                "id": id(obj),
                "registered_id": id(registered) if registered is not None else None,
                "owners": sorted(set(owners)),
            }
            if deep:
                entry["retained_bytes_estimate"] = retained_size(obj)
            out.append(entry)
    return {
        "count": len(out),
        "orphans": out,
        "mod_module_count": len(names),
    }


def retained_size(obj, max_objects=20000, max_depth=5):
    """A rough size for what is pinned behind *obj* (bytes).

    A BOUNDED walk -- it is an estimate, not an accounting: it stops at
    *max_objects* visited objects and *max_depth* levels, and it never
    visits the same object twice.  Code objects and function globals are
    followed, because a function's own size does not include its code.
    """
    import sys
    import types
    seen = set()
    total = 0
    stack = [(obj, 0)]
    while stack and len(seen) < max_objects:
        item, depth = stack.pop()
        key = id(item)
        if key in seen:
            continue
        seen.add(key)
        try:
            total += sys.getsizeof(item, 0)
        except Exception:
            pass
        if depth >= max_depth:
            continue
        if isinstance(item, types.FunctionType):
            children = [item.__code__, item.__globals__, item.__defaults__]
        elif isinstance(item, types.CodeType):
            children = list(item.co_consts)
        elif isinstance(item, type):
            children = [item.__dict__, item.__mro__]
        elif isinstance(item, dict):
            children = list(item.values())[:2000]
        elif isinstance(item, (list, tuple, set, frozenset)):
            children = list(item)[:2000]
        elif hasattr(item, "__dict__"):
            children = [v for v in vars(item).values()][:500]
        else:
            children = []
        for child in children:
            if id(child) not in seen:
                stack.append((child, depth + 1))
    return total


def generation_ids(names=WATCHED_MODULES):
    """{module name: id(module)} -- the generation identity, per run.

    Two runs with the same ids ran the SAME generation; a changed id
    means a new generation was minted (a reload happened).
    """
    out = {}
    for name in names:
        mod = sys.modules.get(name)
        if mod is not None:
            out[name] = id(mod)
    return out


def probe_payload(mod_dir=None, deep=False):
    """The census, as a JSON-serialisable dict.  Runs INSIDE FreeCAD."""
    helper = _helper()
    census = collect_orphans(mod_dir, deep=deep)
    return {
        "pid": os.getpid(),
        "rss_mb": helper.rss_mb(),
        "orphans": census["count"],
        "orphan_detail": census["orphans"],
        "mod_module_count": census["mod_module_count"],
        "generation_ids": generation_ids(),
    }


# ---------------------------------------------------------------------------
# the client: drive the real runner against a running FreeCAD
# ---------------------------------------------------------------------------

_PROBE_CODE = """
import json
import sys
sys.path.insert(0, %r)


def _silk_rss_probe():
    import Tests.rss_baseline_measure as M
    return M.probe_payload(deep=%s)


print(%r + json.dumps(_silk_rss_probe()))
"""


def _rpc_execute(port, code, timeout):
    """One execute_code call against the running FreeCAD.

    The same transport run_all.py uses: the socket timeout sits behind
    the caller's own deadline, and the server's answer is returned as
    text (the console output of the executed code).
    """
    import http.client
    import xmlrpc.client

    class _Transport(xmlrpc.client.Transport):
        def make_connection(self, host):
            parts = host.split(":")
            return http.client.HTTPConnection(
                parts[0], int(parts[1]) if len(parts) > 1 else 80,
                timeout=timeout)

    proxy = xmlrpc.client.ServerProxy("http://127.0.0.1:%d/" % port,
                                      _Transport())
    res = proxy.execute_code(code)
    if not isinstance(res, dict) or not res.get("success"):
        raise RuntimeError("FreeCAD reported an error: %r" % (res,))
    return str(res.get("message", ""))


def probe_freecad(port=DEFAULT_PORT, timeout=300, deep=False):
    """Ask the running FreeCAD for its pid, its RSS and its orphan census."""
    code = _PROBE_CODE % (MOD_DIR, "True" if deep else "False", PROBE_MARKER)
    message = _rpc_execute(port, code, timeout)
    idx = message.rfind(PROBE_MARKER)
    if idx < 0:
        raise RuntimeError("no %s line in the FreeCAD answer:\n%s"
                           % (PROBE_MARKER, message[-2000:]))
    line = message[idx + len(PROBE_MARKER):].splitlines()[0]
    return json.loads(line)


def sample_rss(pid):
    """The RSS of *pid* in MB, read by THIS process (not the runner's)."""
    return _helper().rss_mb(pid)


def reading_floor(pid, samples=20, pause=0.05):
    """The instrument's own noise: the spread of repeated readings.

    The RSS counter is a kernel number, so this is small -- but it is
    MEASURED, not assumed, and it is published beside the drift.
    """
    values = []
    for _ in range(max(int(samples), 2)):
        value = sample_rss(pid)
        if value is not None:
            values.append(value)
        time.sleep(pause)
    if not values:
        return {"samples": 0, "min_mb": None, "max_mb": None, "spread_mb": None}
    return {
        "samples": len(values),
        "min_mb": min(values),
        "max_mb": max(values),
        "spread_mb": max(values) - min(values),
    }


def runner_command(test_filter=None):
    """The command that runs the REAL runner once."""
    cmd = [sys.executable, os.path.join(MOD_DIR, "Tests", "run_all.py")]
    if test_filter:
        cmd.append(test_filter)
    return cmd


def run_suite_once(test_filter=None, port=DEFAULT_PORT, timeout=3600,
                   cwd=None):
    """Run the real runner once, as a subprocess.  Returns (rc, text)."""
    env = dict(os.environ)
    env["SILK_RPC_PORT"] = str(port)
    proc = subprocess.run(
        runner_command(test_filter),
        cwd=cwd or MOD_DIR, env=env, timeout=timeout,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        universal_newlines=True)
    return proc.returncode, proc.stdout or ""


# ---------------------------------------------------------------------------
# the in-process mode: the N runs inside THIS FreeCAD
# ---------------------------------------------------------------------------

def runner_remote_code():
    """run_all.py's _REMOTE_CODE block, extracted with ast.

    Importing run_all.py would RUN the suite (it calls sys.exit(main())
    at module level), so the block is read out of the source instead.
    That way the in-process mode measures the runner's own remote path,
    not a re-implementation of it.
    """
    path = os.path.join(MOD_DIR, "Tests", "run_all.py")
    with open(path) as fh:
        source = fh.read()
    for node in ast.parse(source).body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if getattr(target, "id", None) == "_REMOTE_CODE":
                    return ast.literal_eval(node.value)
    raise RuntimeError("run_all.py has no _REMOTE_CODE block")


def format_remote_code(test_filter=None, progress_file=None):
    """The remote code, formatted exactly as run_all.py formats it."""
    code = runner_remote_code()
    progress = progress_file or os.path.join(
        tempfile.gettempdir(), "silk_progress_%d.json" % os.getpid())
    args = (
        MOD_DIR,                    # sys.path.insert(0, %r)
        progress,                   # os.environ["SILK_PROGRESS_FILE"] = %r
        "False",                    # force_reload
        "False",                    # keep_namespace
        test_filter if test_filter else None,   # test_filter
        "True",                     # close_docs
        None,                       # save_dir
        None,                       # test_modules
        "False",                    # include_manual
    )
    return code % args


# ---------------------------------------------------------------------------
# the series
# ---------------------------------------------------------------------------

def _record_from(parsed, index, seconds, returncode=None,
                 client_before=None, client_after=None):
    record = {
        "run": index,
        "seconds": seconds,
        "returncode": returncode,
        "rss_before_mb": parsed.get("rss_before_mb"),
        "rss_after_mb": parsed.get("rss_after_mb"),
        "runner_delta_mb": parsed.get("runner_delta_mb"),
        "orphans": parsed.get("orphans"),
        "reloaded": parsed.get("reloaded"),
        "reload_reason": parsed.get("reload_reason"),
        "passed": parsed.get("passed"),
        "total": parsed.get("total"),
        "failed": parsed.get("failed"),
        "client_rss_before_mb": client_before,
        "client_rss_after_mb": client_after,
        "inter_run_gap_mb": None,
        "client_inter_run_gap_mb": None,
        "client_run_delta_mb": None,
        "crosscheck_delta_mb": None,
    }
    if client_before is not None and client_after is not None:
        record["client_run_delta_mb"] = client_after - client_before
    # The cross-check: the runner's reading of the process, from INSIDE
    # it, against the client's reading of the same process, from OUTSIDE
    # it, at the same moment.
    if client_after is not None and parsed.get("rss_after_mb") is not None:
        record["crosscheck_delta_mb"] = client_after - parsed["rss_after_mb"]
    return record


def _fill_gaps(records):
    """The inter-run gap: rss_before(run N+1) - rss_after(run N).

    This is the quantity the runner's own delta cannot see.  It is
    filled from the runner's numbers (available in both modes) and, when
    the client sampled the process, from the client's numbers too.
    """
    for i in range(len(records) - 1):
        prev, cur = records[i], records[i + 1]
        if prev.get("rss_after_mb") is not None and \
                cur.get("rss_before_mb") is not None:
            cur["inter_run_gap_mb"] = cur["rss_before_mb"] - prev["rss_after_mb"]
        if prev.get("client_rss_after_mb") is not None and \
                cur.get("client_rss_before_mb") is not None:
            cur["client_inter_run_gap_mb"] = (cur["client_rss_before_mb"]
                                              - prev["client_rss_after_mb"])
    return records


def _progress_line(record, runs):
    return ("[measure] run %d/%d: %.1f MB -> %.1f MB (delta %+.1f), "
            "orphans %s, reloaded %s, %.0f s"
            % (record["run"], runs,
               record.get("rss_before_mb") or -1.0,
               record.get("rss_after_mb") or -1.0,
               record.get("runner_delta_mb") or 0.0,
               record.get("orphans"), record.get("reloaded"),
               record.get("seconds") or 0.0))


def measure_series_client(runs=DEFAULT_RUNS, port=DEFAULT_PORT,
                          test_filter=None, out_dir=None, timeout=3600):
    """Drive the real runner N times against ONE running FreeCAD.

    The client samples the FreeCAD process before and after every run --
    from OUTSIDE the process, with a different reader than the runner's
    -- which is the independent cross-check of the in-process reading.
    """
    out_dir = out_dir or _new_out_dir()
    os.makedirs(out_dir, exist_ok=True)
    start = probe_freecad(port)
    pid = start["pid"]
    floor = reading_floor(pid)
    records = []
    for i in range(1, int(runs) + 1):
        before = sample_rss(pid)
        t0 = time.time()
        try:
            rc, text = run_suite_once(test_filter, port, timeout)
        except subprocess.TimeoutExpired:
            rc, text = -1, "TIMEOUT after %s s\n" % timeout
        seconds = time.time() - t0
        after = sample_rss(pid)
        raw = os.path.join(out_dir, "run_%02d.txt" % i)
        with open(raw, "w") as fh:
            fh.write(text)
        parsed = parse_run_output(text)
        record = _record_from(parsed, i, seconds, rc, before, after)
        record["raw_output"] = raw
        records.append(record)
        print(_progress_line(record, runs), flush=True)
    end = probe_freecad(port, deep=True)
    return {"records": _fill_gaps(records), "start_probe": start,
            "end_probe": end, "floor": floor, "out_dir": out_dir,
            "mode": "client (the real runner, N times, one FreeCAD)"}


def measure_series_in_process(runs=DEFAULT_RUNS, test_filter=None,
                              out_dir=None):
    """Run the fast tier N times inside THIS FreeCAD process.

    The runner's own remote block is executed N times in ONE persistent
    namespace -- the same shape as N execute_code calls, because the
    RPC namespace is persistent by design.
    """
    out_dir = out_dir or _new_out_dir()
    os.makedirs(out_dir, exist_ok=True)
    code = format_remote_code(test_filter)
    namespace = {}
    floor = reading_floor(os.getpid())
    records = []
    for i in range(1, int(runs) + 1):
        buf = io.StringIO()
        t0 = time.time()
        with contextlib.redirect_stdout(buf):
            exec(code, namespace)
        seconds = time.time() - t0
        text = buf.getvalue()
        raw = os.path.join(out_dir, "run_%02d.txt" % i)
        with open(raw, "w") as fh:
            fh.write(text)
        parsed = parse_run_output(text)
        record = _record_from(parsed, i, seconds, 0)
        record["raw_output"] = raw
        records.append(record)
        print(_progress_line(record, runs), flush=True)
    census = collect_orphans(deep=True)
    end = {"pid": os.getpid(), "rss_mb": _helper().rss_mb(),
           "orphans": census["count"], "orphan_detail": census["orphans"],
           "mod_module_count": census["mod_module_count"],
           "generation_ids": generation_ids()}
    return {"records": _fill_gaps(records), "start_probe": None,
            "end_probe": end,
            "floor": floor,
            "out_dir": out_dir,
            "mode": "in-process (the runner's remote block, N times, one "
                    "FreeCAD)"}


# ---------------------------------------------------------------------------
# the report
# ---------------------------------------------------------------------------

def _new_out_dir():
    stamp = time.strftime("%Y%m%d-%H%M%S", time.localtime())
    return os.path.join(OUT_ROOT, stamp)


def analyze(series):
    """The analysis of a measured series: the numbers and the reading."""
    records = series["records"]
    baseline = [r["rss_before_mb"] for r in records
                if r.get("rss_before_mb") is not None]
    floor = series.get("floor") or {}
    spread = floor.get("spread_mb") or 0.0
    # The cross-check: the runner's reading of the process, from INSIDE
    # it, against the client's reading of the same process, from OUTSIDE
    # it, at the same moment.  The client's sample is taken LATER (after
    # the answer came back), so the difference carries a systematic
    # offset -- that offset is reported, but the NOISE is the spread of
    # the differences, and the spread is what the floor uses.
    deltas = [r["crosscheck_delta_mb"] for r in records
              if r.get("crosscheck_delta_mb") is not None]
    deltas.sort()
    if deltas:
        offset = deltas[len(deltas) // 2]
        cross_spread = (deltas[-1] - deltas[0]) if len(deltas) > 1 else 0.0
    else:
        offset = 0.0
        cross_spread = 0.0
    floor_mb = max(float(spread or 0.0), float(cross_spread or 0.0))
    analysis = classify_baseline(baseline, floor_mb)
    floors = {"reading_spread_mb": spread, "crosscheck_offset_mb": offset,
              "crosscheck_spread_mb": cross_spread, "floor_mb": floor_mb}
    # A series that lost a run cannot be read: the verdict below would
    # be about the runs that happened, not about the runner.
    complete = (len(baseline) == len(records) and len(records) >= 2
                and all(r.get("runner_delta_mb") is not None for r in records))
    return {"baseline": baseline, "analysis": analysis, "floors": floors,
            "complete": complete,
            "verdict": verdict(records, analysis, floors)}


def print_report(series, result, out_dir):
    records = series["records"]
    analysis = result["analysis"]
    floors = result["floors"]
    reading = result["verdict"]
    print("")
    print("=== #123 baseline measurement ===")
    print("mode: %s" % series["mode"])
    print("raw output: %s" % out_dir)
    print("")
    print("%-4s %-9s %-9s %-28s %-24s %-10s"
          % ("run", "reloaded", "orphans", "runner RSS before->after",
             "client RSS before->after", "gap"))
    for rec in records:
        gap = rec.get("inter_run_gap_mb")
        reloaded = rec.get("reloaded")
        client = ("%.1f -> %.1f" % (rec.get("client_rss_before_mb"),
                                    rec.get("client_rss_after_mb"))
                  if rec.get("client_rss_before_mb") is not None else "-")
        print("%-4d %-9s %-9s %-28s %-24s %-10s"
              % (rec["run"],
                 ("yes" if reloaded else "no") if reloaded is not None else "?",
                 rec.get("orphans"),
                 "%.1f -> %.1f (%+.1f)" % (rec.get("rss_before_mb") or 0.0,
                                           rec.get("rss_after_mb") or 0.0,
                                           rec.get("runner_delta_mb") or 0.0),
                 client,
                 ("%+.1f" % gap) if gap is not None else "-"))
    print("")
    print("the gap is rss_before(run N+1) - rss_after(run N): what happens")
    print("BETWEEN two runs, which the runner's own delta cannot see.")
    print("")
    print("FLOOR (the instrument's own noise, measured):")
    print("  repeated readings of the idle process: spread %.3f MB over %s "
          "readings" % (floors["reading_spread_mb"] or 0.0,
                        (series.get("floor") or {}).get("samples")))
    print("  runner reading vs the client's reading of the same process: "
          "offset %+.2f MB (the client reads later), spread %.2f MB"
          % (floors["crosscheck_offset_mb"], floors["crosscheck_spread_mb"]))
    print("  floor used for the verdict: %.2f MB" % floors["floor_mb"])
    print("")
    print("BASELINE (the RSS at the START of each run): %s"
          % ", ".join("%.1f" % v for v in result["baseline"]))
    print("  slope %.2f MB/run, span %.1f MB over %d runs -> %s"
          % (analysis["slope_mb_per_run"], analysis["span_mb"],
             analysis["runs"], analysis["verdict"].upper()))
    print("")
    print("READING")
    if not result.get("complete", True):
        print("  - THE SERIES IS INCOMPLETE: at least one run did not "
              "report its RSS (see the raw output). The reading below "
              "covers the runs that happened, not the runner.")
    for note in reading["notes"]:
        print("  - %s" % note)
    print("")
    end = series.get("end_probe") or {}
    orphans = end.get("orphan_detail") or []
    if orphans:
        print("ORPHAN GENERATIONS (alive, outside sys.modules), and who "
              "holds them:")
        for entry in orphans:
            print("  %-24s id %s  held by: %s"
                  % (entry["name"], entry["id"],
                     ", ".join(entry.get("owners") or ["<none found>"])))
        total = sum(e.get("retained_bytes_estimate") or 0 for e in orphans)
        if total:
            print("  rough size pinned behind them: %.2f MB"
                  % (total / (1024.0 * 1024.0)))
    else:
        print("ORPHAN GENERATIONS: none.")
    print("")
    print("KEEP the raw output directory; the numbers above are a reading "
          "of it, not a substitute for it.")


def main(argv=None):
    """The instrument's entry point.  Returns a process exit code."""
    argv = list(sys.argv[1:] if argv is None else argv)
    runs = DEFAULT_RUNS
    port = int(os.environ.get("SILK_RPC_PORT", DEFAULT_PORT))
    test_filter = None
    out_dir = None
    in_process = False
    i = 0
    while i < len(argv):
        arg = argv[i]
        if arg == "--runs" and i + 1 < len(argv):
            runs = int(argv[i + 1]); i += 2; continue
        if arg == "--port" and i + 1 < len(argv):
            port = int(argv[i + 1]); i += 2; continue
        if arg == "--filter" and i + 1 < len(argv):
            test_filter = argv[i + 1]; i += 2; continue
        if arg == "--out-dir" and i + 1 < len(argv):
            out_dir = argv[i + 1]; i += 2; continue
        if arg == "--in-process":
            in_process = True; i += 1; continue
        if arg in ("-h", "--help"):
            print(__doc__)
            return 0
        print("unknown argument: %s (try --help)" % arg)
        return 2
    try:
        if in_process:
            series = measure_series_in_process(runs, test_filter, out_dir)
        else:
            series = measure_series_client(runs, port, test_filter, out_dir)
    except Exception as exc:
        print("measurement failed: %s: %s" % (type(exc).__name__, exc))
        if not in_process:
            print("(is a FreeCAD running with its RPC server on port %d?)"
                  % port)
        return 2
    result = analyze(series)
    out_dir = series["out_dir"]
    with open(os.path.join(out_dir, "measurements.json"), "w") as fh:
        json.dump({"series": series, "result": result}, fh, indent=2,
                  default=str)
    print_report(series, result, out_dir)
    return 0


if __name__ == "__main__":
    sys.exit(main())
