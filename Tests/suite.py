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


def collect_tests(test_filter=None, test_modules=None):
    """Collect test functions from every test_*.py module in Tests/.

    test_filter: optional substring matched against the test function
    name or its module name (e.g. 'edge_stage' runs only Tests/
    test_edge_stage.py). Lets a developer run one stage at a time.

    test_modules: optional iterable of test module BASENAMES ('test_chain')
    to run, selecting whole modules rather than a substring. This is what
    `run_all.py --changed` uses: one source edit maps to SEVERAL modules
    at once, which a single substring cannot express (#72). Intersected
    with test_filter when both are given.
    """
    funcs = []
    # Ticket #26: the chain gate is the acceptance gate and always runs
    # LAST -- collect every other module alphabetically, then append
    # test_chain.py's tests so it is literally the final test executed.
    _paths = sorted(glob.glob(os.path.join(_TESTS_DIR, "test_*.py")))
    _chain = [p for p in _paths if os.path.basename(p) == "test_chain.py"]
    _paths = [p for p in _paths if os.path.basename(p) != "test_chain.py"]
    for path in _paths + _chain:
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
    if test_modules is not None:
        # A bare string would iterate CHARACTERS ('test_chain' -> {'t',
        # 'e', 's', ...}) and silently select nothing. Guard it.
        if isinstance(test_modules, str):
            test_modules = [test_modules]
        wanted = set(test_modules)
        funcs = [
            f for f in funcs
            if (f.__module__ or "").split(".")[-1] in wanted
        ]
    if test_filter is not None:
        funcs = [
            f for f in funcs
            if test_filter in f.__name__ or test_filter in (f.__module__ or "")
        ]
    return funcs
