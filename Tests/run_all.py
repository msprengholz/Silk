"""
Non-chat test runner for the Silk test suite.

Run from anywhere:
    freecad Tests/run_all.py        (or: freecad /path/to/Silk/Tests/run_all.py)

Discovers every test in Tests/test_*.py and runs it through the same
run_tests() harness the MCP (agent) path uses, so both launchers exercise
exactly the same test functions. Prints a per-test pass/fail summary and
exits 0 when everything passes, 1 otherwise.

Adding a test: put a test_*.py module in Tests/. It is picked up
automatically -- use an ALL_TESTS list, or plain test_* functions that
take a document.
"""

import glob
import importlib
import inspect
import os
import sys

# Line-buffer stdout so progress is visible in the terminal even if the
# process is killed mid-run (FreeCAD startup scripts otherwise buffer).
try:
    sys.stdout.reconfigure(line_buffering=True)
except AttributeError:
    pass

_SILK_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_TESTS_DIR = os.path.dirname(os.path.abspath(__file__))

# Make the workbench root importable (ArachNURBS, SilkEdge, ... live there)
# and give the tests a predictable cwd for any relative file references.
if _SILK_DIR not in sys.path:
    sys.path.insert(0, _SILK_DIR)
os.chdir(_SILK_DIR)

import FreeCAD  # noqa: E402
from Tests.mcp_harness import run_tests  # noqa: E402


def _collect_tests():
    """Collect test functions from every test_*.py module in this directory."""
    funcs = []
    for path in sorted(glob.glob(os.path.join(_TESTS_DIR, "test_*.py"))):
        mod_name = "Tests." + os.path.splitext(os.path.basename(path))[0]
        mod = importlib.import_module(mod_name)
        if hasattr(mod, "ALL_TESTS"):
            funcs.extend(mod.ALL_TESTS)
        else:
            # Fallback: any top-level test_* function taking a document.
            for name, obj in sorted(vars(mod).items()):
                if (
                    name.startswith("test_")
                    and inspect.isfunction(obj)
                    and len(inspect.signature(obj).parameters) == 1
                ):
                    funcs.append(obj)
    return funcs


def main():
    # The MCP path runs with the Silk workbench active (commands like
    # 'ControlPoly4' only resolve in that context) -- replicate it here.
    try:
        import FreeCADGui as Gui
        Gui.activateWorkbench("Silk")
    except Exception as e:
        print("Warning: could not activate Silk workbench: " + str(e))

    funcs = _collect_tests()
    if not funcs:
        print("No tests found in " + _TESTS_DIR)
        return 1
    print("Running {} Silk tests via freecad (non-chat runner)".format(len(funcs)))
    summary = run_tests(*funcs)
    return 0 if summary["failed"] == 0 else 1


# NOTE: called unconditionally -- FreeCAD executes startup scripts with
# __name__ != "__main__", so an if-guard would skip everything.
sys.exit(main())

