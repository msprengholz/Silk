"""Test discovery shared by every launcher (MCP, in-process, non-chat RPC).

A test is a function that takes one argument (a document) and returns a
dict consumed by Tests.mcp_harness.run_tests.

Modules may expose an ALL_TESTS list; otherwise every top-level test_*
function with a single parameter is picked up. Adding a new test file to
Tests/ is all that is needed -- it is discovered automatically.
"""

import glob
import importlib
import inspect
import os

_TESTS_DIR = os.path.dirname(os.path.abspath(__file__))


def collect_tests(test_filter=None):
    """Collect test functions from every test_*.py module in Tests/.

    test_filter: optional substring matched against the test function
    name or its module name (e.g. 'edge_stage' runs only Tests/
    test_edge_stage.py). Lets a developer run one stage at a time.
    """
    funcs = []
    for path in sorted(glob.glob(os.path.join(_TESTS_DIR, "test_*.py"))):
        mod_name = "Tests." + os.path.splitext(os.path.basename(path))[0]
        mod = importlib.import_module(mod_name)
        if hasattr(mod, "ALL_TESTS"):
            funcs.extend(mod.ALL_TESTS)
        else:
            for name, obj in sorted(vars(mod).items()):
                if (
                    name.startswith("test_")
                    and inspect.isfunction(obj)
                    and len(inspect.signature(obj).parameters) == 1
                ):
                    funcs.append(obj)
    if test_filter is not None:
        funcs = [
            f for f in funcs
            if test_filter in f.__name__ or test_filter in (f.__module__ or "")
        ]
    return funcs
