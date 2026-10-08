"""
Non-chat test runner for the Silk test suite.

Primary -- attach to an already-running FreeCAD GUI (no restart):
    python3 Tests/run_all.py

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
import sys

try:
    sys.stdout.reconfigure(line_buffering=True)
except AttributeError:
    pass

_SILK_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _SILK_DIR not in sys.path:
    sys.path.insert(0, _SILK_DIR)
os.chdir(_SILK_DIR)

# Code sent to the running FreeCAD: activate the workbench (so command
# based tests resolve) and run the shared suite.
_REMOTE_CODE = """
import sys
sys.path.insert(0, %r)
import FreeCADGui as Gui
try:
    Gui.activateWorkbench("Silk")
except Exception:
    pass
from Tests import suite
from Tests.mcp_harness import run_tests
funcs = suite.collect_tests()
if funcs:
    run_tests(*funcs)
else:
    import json
    print("RESULT:" + json.dumps(
        {"total": 0, "passed": 0, "failed": 1, "results": []}))
"""


def _run_in_process():
    """Inside a FreeCAD process (freecad startup-script mode)."""
    try:
        import FreeCADGui as Gui
        Gui.activateWorkbench("Silk")
    except Exception as e:
        print("Warning: could not activate Silk workbench: " + str(e))
    from Tests import suite
    from Tests.mcp_harness import run_tests
    funcs = suite.collect_tests()
    if not funcs:
        print("No tests found in " + os.path.join(_SILK_DIR, "Tests"))
        return 1
    print("Running {} Silk tests (in-process runner)".format(len(funcs)))
    summary = run_tests(*funcs)
    return 0 if summary["failed"] == 0 else 1


def _run_via_rpc(port):
    """Attach to a running FreeCAD GUI through its XML-RPC server."""
    import http.client
    import json
    import xmlrpc.client

    class _Transport(xmlrpc.client.Transport):
        def make_connection(self, host):
            parts = host.split(":")
            return http.client.HTTPConnection(
                parts[0], int(parts[1]) if len(parts) > 1 else 80, timeout=600
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
    res = proxy.execute_code(_REMOTE_CODE % _SILK_DIR, 600)
    if not isinstance(res, dict) or not res.get("success"):
        print("FreeCAD reported an error:\n%s" % res)
        return 2

    out = str(res.get("message", ""))
    idx = out.rfind("RESULT:")
    if idx < 0:
        print("No RESULT line in FreeCAD output:\n%s" % out[-3000:])
        return 2
    summary = json.loads(out[idx + len("RESULT:"):].strip())

    for r in summary["results"]:
        status = "PASS" if r.get("pass") else "FAIL"
        print("  [%s] %s" % (status, r["name"]))
        for err in r.get("errors", []):
            print("    ERROR: " + err)
    print(
        "\n%d/%d passed, %d failed (in running FreeCAD)"
        % (summary["passed"], summary["total"], summary["failed"])
    )
    return 0 if summary["failed"] == 0 else 1


def main():
    try:
        import FreeCAD  # noqa: F401
        return _run_in_process()
    except ImportError:
        port = int(os.environ.get("SILK_RPC_PORT", "9875"))
        return _run_via_rpc(port)


# NOTE: called unconditionally -- FreeCAD executes startup scripts with
# __name__ != "__main__", so an if-guard would skip everything.
sys.exit(main())
