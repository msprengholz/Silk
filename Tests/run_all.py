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
import sys

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

def _silk_run(force_reload, keep_namespace, test_filter, close_docs, save_dir):
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
    import FreeCADGui as Gui
    try:
        Gui.activateWorkbench("Silk")
    except Exception:
        pass
    from Tests import suite
    from Tests.mcp_harness import run_tests
    funcs = suite.collect_tests(test_filter)
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
    rss_after = helper.rss_mb()
    if rss_before is not None and rss_after is not None:
        print("[rss] FreeCAD pid %%d resident memory: before %%.1f MB, "
              "after %%.1f MB (delta %%.1f MB)"
              %% (os.getpid(), rss_before, rss_after, rss_after - rss_before))

_silk_run(%s, %s, %r, %s, %r)
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


def _run_in_process(inspect, save_dir, test_filter):
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
    funcs = suite.collect_tests(test_filter)
    if not funcs:
        print("No tests match %r in %s" % (test_filter, os.path.join(_SILK_DIR, "Tests")))
        print("Available: " + str([f.__name__ for f in suite.collect_tests()]))
        return 1
    print("Running {} Silk tests (in-process runner)".format(len(funcs)))
    summary = run_tests(*funcs, close_docs=not (inspect or save_dir))
    if save_dir:
        _save_inspect_docs(save_dir)
    rss_after = silk_reload.rss_mb()
    if rss_before is not None and rss_after is not None:
        print("[rss] FreeCAD pid %d resident memory: before %.1f MB, after %.1f MB "
              "(delta %.1f MB)" % (os.getpid(), rss_before, rss_after,
                                   rss_after - rss_before))
    return 0 if summary["failed"] == 0 else 1


def _run_via_rpc(port, inspect, save_dir, test_filter, force_reload=False,
                 keep_namespace=False):
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
    res = proxy.execute_code(
        _REMOTE_CODE % (_SILK_DIR, str(bool(force_reload)),
                        str(bool(keep_namespace)), test_filter,
                        str(not (inspect or save_dir)), save_dir),
        _call_timeout,
    )
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
    if inspect or save_dir:
        for line in out.splitlines():
            if "[inspect]" in line or "[saved]" in line or (line.startswith("  - ") and ("_mcp_test_" in line or "_inspect" in line)):
                print(line)
    # #72: module freshness + resident memory, echoed from FreeCAD itself.
    rss_after = None
    for line in out.splitlines():
        # The first captured line carries the RPC server's "Output: " prefix.
        if "[reload]" in line or "[leak]" in line:
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
    rest = sys.argv[1:]
    while rest:
        arg = rest.pop(0)
        if arg in skip:
            rest.pop(0)  # drop the flag's value
            continue
        if arg.startswith("--"):
            continue
        args.append(arg)
    test_filter = args[0] if args else None
    inspect = "--inspect" in sys.argv
    save = "--save" in sys.argv
    force_reload = "--force-reload" in sys.argv
    keep_namespace = "--keep-namespace" in sys.argv
    save_dir = _INSPECT_SAVE_DIR if save else None
    try:
        import FreeCAD  # noqa: F401
        return _run_in_process(inspect, save_dir, test_filter)
    except ImportError:
        port = int(os.environ.get("SILK_RPC_PORT", "9875"))
        return _run_via_rpc(port, inspect, save_dir, test_filter, force_reload,
                            keep_namespace)


# NOTE: called unconditionally -- FreeCAD executes startup scripts with
# __name__ != "__main__", so an if-guard would skip everything.
sys.exit(main())
