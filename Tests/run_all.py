"""
Non-chat test runner for the Silk test suite.

Primary -- attach to an already-running FreeCAD GUI (no restart):
    python3 Tests/run_all.py

Stage 2 (visual inspection) -- leave the test documents open in the GUI
so you can look at the geometry afterwards:
    python3 Tests/run_all.py --inspect

Persist the resulting geometry to disk (Resources/Test_files/_inspect/)
so each test document can be reopened even after the run ended / FreeCAD
was closed. Implies --inspect (docs are left open so they can be saved):
    python3 Tests/run_all.py --save

Both can be combined with a filter:
    python3 Tests/run_all.py mutation_backfill --save

Run one stage at a time (substring matched against test or module name):
    python3 Tests/run_all.py edge_stage
    python3 Tests/run_all.py edge_stage --inspect

Reload control (#72):
    python3 Tests/run_all.py --force-reload     reload even if no file changed
    python3 Tests/run_all.py --keep-namespace   do not clear stale bindings
                                               in the RPC execute_code namespace
    python3 Tests/run_all.py --rss-warn 1024    RSS warning threshold in MB
                                               (default 2048)

Silk modules are reimported only when a .py under the Mod directory has
actually changed (mtime + size + sha256, per process). A re-run with no
edits reimports nothing, so it creates no new generation of the ~86
modules and no new generation of ArachNURBS.

Uses the MCP RPC server (XML-RPC on 127.0.0.1:9875) that auto-starts
inside any FreeCAD GUI. FreeCAD must be open; override the port with
SILK_RPC_PORT.

Fallback -- standalone instance (e.g. CI):
    freecad Tests/run_all.py

Both modes run exactly the same test functions through
Tests.mcp_harness.run_tests -- the MCP chat path uses the same functions.
Exit codes: 0 = all passed, 1 = test failures, 2 = could not reach FreeCAD.
"""

import os
import re
import json
import os
import sys
import threading
import time

try:
    sys.stdout.reconfigure(line_buffering=True)
except AttributeError:
    pass

_SILK_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _SILK_DIR not in sys.path:
    sys.path.insert(0, _SILK_DIR)
os.chdir(_SILK_DIR)

# Where --save persists the leftover test geometry documents. Kept out of
# git (scratch inspection artifacts, not reference fixtures).
_INSPECT_SAVE_DIR = os.path.join(_SILK_DIR, "Resources", "Test_files", "_inspect")

# Resident-memory warning threshold in MB (#72); --rss-warn overrides.
_rss_warn_mb = 2048.0

# Code sent to the running FreeCAD: activate the workbench (so command
# based tests resolve), run the shared suite, then (optionally) persist the
# leftover inspection documents to disk.
#
# #72: module freshness lives in Tests/silk_reload.py. It purges by FILE
# LOCATION (every .py under the Mod directory -- all 57 of them, whatever
# they are called), not by the old "Silk*/Tests*/ArachNURBS" name prefix
# which left ~25 helper modules on an older generation of ArachNURBS. It
# also reimports only when the sources changed, clears stale bindings in
# the persistent execute_code namespace, and reports RSS before/after.
_REMOTE_CODE = """
import sys, os, importlib
sys.path.insert(0, %r)

def _silk_run(force_reload, keep_namespace, test_filter, close_docs, save_dir,
              test_modules=None):
    \"\"\"Everything in one function, so nothing this run binds survives it.

    The execute_code namespace is persistent by design, and a name left
    in it pins the module generation it was bound to -- which is how
    orphaned Silk_tooltips / ControlGrid44 objects outlived a purge that
    had removed them from sys.modules (#72). Locals die with the call.
    \"\"\"
    import Tests.silk_reload as helper
    importlib.reload(helper)  # our own source may have changed
    rss_before = helper.rss_mb()
    helper.ensure_fresh(force=force_reload, namespace=globals(),
                        keep_namespace=keep_namespace)
    # #79: cap the Report View BEFORE the suite prints into it. Its
    # QTextDocument is uncapped (maximumBlockCount 0), so a long-lived GUI
    # keeps every message ever printed -- ~20 MB per run, measured, no
    # plateau. Only on this path: this is the launcher that leaves a
    # FreeCAD running afterwards. The in-process launcher exits at the end
    # of the run, so there the cap would cost the user their report
    # history and buy nothing.
    for _line in helper.describe_memory(
            report_view=helper.cap_report_view()):
        print(_line)
    import FreeCADGui as Gui
    try:
        Gui.activateWorkbench("Silk")
    except Exception:
        pass
    from Tests import suite
    from Tests.mcp_harness import run_tests
    funcs = suite.collect_tests(test_filter, test_modules)
    if funcs:
        run_tests(*funcs, close_docs=close_docs)
    else:
        import json
        print("No tests match. Available: " + str(
            [f.__name__ for f in suite.collect_tests()]))
        print("RESULT:" + json.dumps(
            {"total": 0, "passed": 0, "failed": 1, "results": []}))
    # --save: persist any leftover _mcp_test_* docs so the geometry can be
    # reopened even after this FreeCAD session ends (stage-2 inspection).
    if save_dir and funcs:
        os.makedirs(save_dir, exist_ok=True)
        saved = []
        for name in sorted(FreeCAD.listDocuments()):
            if name.startswith("_mcp_test_"):
                path = os.path.join(save_dir, name + ".FCStd")
                try:
                    FreeCAD.getDocument(name).saveAs(path)
                    saved.append(path)
                    print("[saved] " + path)
                except Exception as exc:
                    print("[save-failed] %%s: %%r" %% (name, exc))
        if saved:
            print("[inspect] geometry saved to disk (open these to inspect):")
            for path in saved:
                print("  - " + path)
    # #72: leave no reference to this run behind, and report memory.
    helper.clear_runner_namespace(globals())
    helper.clear_exception_state()
    # #79: trim AFTER the release. glibc keeps freed memory in its arena,
    # so a trim only returns what is already free: run before the release
    # it reclaimed 6 MB, run after it, 162 MB. The two changes are one
    # fix -- the cap gives the trim something to return.
    for _line in helper.describe_memory(trim=helper.malloc_trim()):
        print(_line)
    rss_after = helper.rss_mb()
    if rss_before is not None and rss_after is not None:
        print("[rss] FreeCAD pid %%d resident memory: before %%.1f MB, "
              "after %%.1f MB (delta %%.1f MB)"
              %% (os.getpid(), rss_before, rss_after, rss_after - rss_before))

_silk_run(%s, %s, %r, %s, %r, %r)
"""


def _save_inspect_docs(save_dir):
    """Persist leftover _mcp_test_* documents to disk for later inspection.
    Returns the list of paths saved."""
    if not save_dir:
        return []
    import FreeCAD
    os.makedirs(save_dir, exist_ok=True)
    saved = []
    for n in sorted(FreeCAD.listDocuments()):
        if n.startswith("_mcp_test_"):
            p = os.path.join(save_dir, n + ".FCStd")
            try:
                FreeCAD.getDocument(n).saveAs(p)
                saved.append(p)
                print("[saved] " + p)
            except Exception as e:
                print("[save-failed] %s: %r" % (n, e))
    return saved


def _run_in_process(inspect, save_dir, test_filter, test_modules=None):
    """Inside a FreeCAD process (freecad startup-script mode)."""
    import Tests.silk_reload as silk_reload
    rss_before = silk_reload.rss_mb()
    try:
        import FreeCADGui as Gui
        Gui.activateWorkbench("Silk")
    except Exception as e:
        print("Warning: could not activate Silk workbench: " + str(e))
    from Tests import suite
    from Tests.mcp_harness import run_tests
    funcs = suite.collect_tests(test_filter, test_modules)
    if not funcs:
        print("No tests match %r / %r in %s"
              % (test_filter, test_modules, os.path.join(_SILK_DIR, "Tests")))
        print("Available: " + str([f.__name__ for f in suite.collect_tests()]))
        return 1
    print("Running {} Silk tests (in-process runner)".format(len(funcs)))
    summary = run_tests(*funcs, close_docs=not (inspect or save_dir))
    if save_dir:
        _save_inspect_docs(save_dir)
    # #79: deliberately NOT capping the Report View on this path. This
    # FreeCAD exits when the run does, so an unbounded buffer costs
    # nothing, and truncating the only copy of the user's report history
    # would cost something. The cap belongs to the launcher that leaves a
    # long-lived GUI behind. The trim is still worth doing (it reports
    # what this run freed, and this FreeCAD may be kept open by --inspect).
    print("[report] Report View left uncapped here (in-process run: this "
          "FreeCAD exits when the run does)")
    for line in silk_reload.describe_memory(trim=silk_reload.malloc_trim()):
        print(line)
    rss_after = silk_reload.rss_mb()
    if rss_before is not None and rss_after is not None:
        print("[rss] FreeCAD pid %d resident memory: before %.1f MB, after %.1f MB "
              "(delta %.1f MB)" % (os.getpid(), rss_before, rss_after,
                                   rss_after - rss_before))
    return 0 if summary["failed"] == 0 else 1


# The stall watchdog lives in its own module on purpose -- see its docstring.
# run_all.py itself cannot be imported inside FreeCAD (it runs main()
# unconditionally, which re-enters the RPC server and segfaults the GUI
# thread), so anything testable about the watchdog has to live elsewhere.
from Tests.watchdog import (  # noqa: E402
    PROGRESS_FILE, STALL_SECONDS, _Watchdog,
)

def _run_via_rpc(port, inspect, save_dir, test_filter, force_reload=False,
                 keep_namespace=False, test_modules=None):
    """Attach to a running FreeCAD GUI through its XML-RPC server."""
    import http.client
    import json
    import xmlrpc.client

    # The full suite takes ~11 minutes in a busy FreeCAD, so wait as long
    # as the RPC server is willing to (its own cap, 1800s). At the old
    # 600s the client hung up while the suite was still running, and the
    # run's output was lost with it.
    _call_timeout = 1800

    class _Transport(xmlrpc.client.Transport):
        def make_connection(self, host):
            parts = host.split(":")
            return http.client.HTTPConnection(
                parts[0], int(parts[1]) if len(parts) > 1 else 80, timeout=_call_timeout
            )

    try:
        proxy = xmlrpc.client.ServerProxy(
            "http://127.0.0.1:%d/" % port, _Transport()
        )
        proxy.ping()
    except Exception as e:
        print("No running FreeCAD reachable at 127.0.0.1:%d (%s)" % (port, e))
        print("Open FreeCAD first -- its MCP RPC server is the test target.")
        return 2

    try:
        os.remove(PROGRESS_FILE)      # never trust a previous run's record
    except OSError:
        pass
    print("Running Silk tests in the running FreeCAD (port %d)..." % port)
    if inspect:
        print("--inspect: test documents will be left open for inspection.")
    if save_dir:
        print("--save: test geometry will be persisted to %s" % save_dir)
    if test_filter:
        print("filter: %s" % test_filter)
    if force_reload:
        print("--force-reload: reimporting Silk modules even if unchanged.")
    if keep_namespace:
        print("--keep-namespace: leaving stale RPC namespace bindings alone.")
    _wd = _Watchdog()
    _wd.start()
    try:
        res = proxy.execute_code(
        # Order must match _silk_run's signature inside _REMOTE_CODE:
        # (force, keep_ns, test_filter, close_docs, save_dir, test_modules).
        # Getting this wrong passes test_modules in save_dir's slot, which
        # does not crash -- it just runs the whole suite, which is the
        # worst possible failure for a speed flag.
            _REMOTE_CODE % (_SILK_DIR, str(bool(force_reload)),
                            str(bool(keep_namespace)), test_filter,
                            str(not (inspect or save_dir)), save_dir,
                            list(test_modules) if test_modules else None),
            _call_timeout,
        )
    except Exception:
        raise
    finally:
        # The watchdog is a daemon and dies with the process; this only
        # makes the lifetime explicit.
        _wd.interval = 1e9
    if _wd.stalled:
        return 3
    if not isinstance(res, dict) or not res.get("success"):
        print("FreeCAD reported an error:\n%s" % res)
        return 2

    out = str(res.get("message", ""))
    idx = out.rfind("RESULT:")
    if idx < 0:
        print("No RESULT line in FreeCAD output:\n%s" % out[-3000:])
        return 2
    # The RESULT line is a single JSON object; any [saved]/[inspect] lines
    # printed afterwards by --save must not be swallowed into the JSON.
    summary = json.loads(out[idx + len("RESULT:"):].splitlines()[0].strip())

    for r in summary["results"]:
        status = "PASS" if r.get("pass") else "FAIL"
        print("  [%s] %s" % (status, r["name"]))
        for err in r.get("errors", []):
            print("    ERROR: " + err)
    print(
        "\n%d/%d passed, %d failed (in running FreeCAD)"
        % (summary["passed"], summary["total"], summary["failed"])
    )
    # Slowest tests, from the summary (#72). FreeCAD's own console output
    # for this never reached stdout, so it is recomputed here from the
    # timings the harness now records. This is what turned "the suite is
    # slow" into two named tests -- and disproved the module-level guess
    # everyone agreed on.
    timings = summary.get("timings") or []
    if timings and sum(t["seconds"] for t in timings) >= 5.0:
        ranked = sorted(timings, key=lambda t: -t["seconds"])
        total_s = sum(t["seconds"] for t in timings)
        top = [t for t in ranked[:8] if t["seconds"] >= 0.2]
        if top:
            print("[slowest] %.1fs total across %d tests" % (total_s, len(timings)))
            for t in top:
                print("   %6.2fs  %s" % (t["seconds"], t["name"]))
            print("   -> these %d are %.0f%% of the run"
                  % (len(top), sum(t["seconds"] for t in top) / total_s * 100))
    if inspect or save_dir:
        for line in out.splitlines():
            if "[inspect]" in line or "[saved]" in line or (line.startswith("  - ") and ("_mcp_test_" in line or "_inspect" in line)):
                print(line)
    # #72: module freshness + resident memory, echoed from FreeCAD itself.
    rss_after = None
    for line in out.splitlines():
        # The first captured line carries the RPC server's "Output: " prefix.
        if "[reload]" in line or "[leak]" in line or "[report]" in line:
            print(line)
        elif line.startswith("[rss]"):
            print(line)
            m = re.search(r"after ([0-9.]+) MB", line)
            if m:
                rss_after = float(m.group(1))
    if rss_after is not None and rss_after > _rss_warn_mb:
        print("WARNING: FreeCAD resident memory %.1f MB is above the %.0f MB "
              "threshold -- leaked generations? (--rss-warn to change)"
              % (rss_after, _rss_warn_mb))
    return 0 if summary["failed"] == 0 else 1


def main():
    global _rss_warn_mb
    if "--rss-warn" in sys.argv:
        value = sys.argv[sys.argv.index("--rss-warn") + 1]
        _rss_warn_mb = float(value)
        print("RSS warning threshold: %.0f MB" % _rss_warn_mb)
    # Positional args are test filters; a flag's value is not one.
    skip = {"--rss-warn"}
    args = []
    # --changed's ref is OPTIONAL. It has to be consumed explicitly: a
    # bare `--changed` is skipped by the startswith("--") rule below, but
    # its VALUE is not, so `run_all.py --changed HEAD~1` passed "HEAD~1"
    # through as a test filter, matched no test, and reported 0/0 without
    # ever saying anything had gone wrong.
    rest = sys.argv[1:]
    while rest:
        arg = rest.pop(0)
        if arg == "--changed":
            if rest and not rest[0].startswith("--"):
                rest.pop(0)
            continue
        if arg in skip:
            rest.pop(0)  # drop the flag's value
            continue
        if arg.startswith("--"):
            continue
        args.append(arg)
    # FreeCADCmd hands the STARTUP SCRIPT ITSELF to sys.argv, so under a
    # headless run the first "positional" is this file's own path. It
    # became a test filter, matched nothing, and the run reported 0/0
    # with no hint that the filter was nonsense.
    try:
        _self = os.path.realpath(__file__)
        args = [a for a in args if os.path.realpath(a) != _self]
    except OSError:
        pass
    test_filter = args[0] if args else None
    inspect = "--inspect" in sys.argv
    save = "--save" in sys.argv
    force_reload = "--force-reload" in sys.argv
    keep_namespace = "--keep-namespace" in sys.argv
    save_dir = _INSPECT_SAVE_DIR if save else None

    # --changed [ref]: run only the test modules a changed file can break
    # (#72). The full suite is ~6.5 minutes and most edits cannot touch
    # most of it; a SilkPatch.py change needs 10 seconds. Falls back to
    # the whole suite whenever the mapping is not confident, because a
    # partial run that is wrong in the direction of running TOO LITTLE is
    # how a break ships, while running too much only costs time.
    test_modules = None
    if "--changed" in sys.argv:
        rest = sys.argv[sys.argv.index("--changed"):]
        ref = None
        if len(rest) > 1 and not rest[1].startswith("--"):
            ref = rest[1]
        from Tests import deps
        paths = deps.changed_files(ref)
        if paths is None:
            print("--changed: git unavailable or not a repo; running everything")
        else:
            mods, reason = deps.modules_for_paths(paths)
            if mods:
                test_modules = mods
                print("--changed: %s" % reason)
                print("           %s" % ", ".join(mods))
            else:
                print("--changed: %s -> running everything" % reason)

    try:
        # ONLY the import decides which mode we are in. The try block used
        # to wrap _run_in_process() as well, so an ImportError raised
        # anywhere INSIDE a headless run silently fell through to the RPC
        # path -- and the run then quietly executed in the human's GUI
        # process instead. That is how a "headless, 102 MB" measurement
        # turned out to be a 4.7 GB run against the live GUI: the launcher
        # printed the fallback's output and nobody could tell.
        import FreeCAD  # noqa: F401
    except ImportError:
        pass
    else:
        return _run_in_process(inspect, save_dir, test_filter, test_modules)
    port = int(os.environ.get("SILK_RPC_PORT", "9875"))
    return _run_via_rpc(port, inspect, save_dir, test_filter, force_reload,
                        keep_namespace, test_modules)


# NOTE: called unconditionally -- FreeCAD executes startup scripts with
# __name__ != "__main__", so an if-guard would skip everything.
sys.exit(main())
