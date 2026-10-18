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


def collect_tests(test_filter=None, test_modules=None, include_manual=False):
    """Collect test functions from every test_*.py module in Tests/.

    test_filter: optional substring matched against the test function
    name or its module name (e.g. 'edge_stage' runs only Tests/
    test_edge_stage.py). Lets a developer run one stage at a time.

    test_modules: optional iterable of test module BASENAMES ('test_chain')
    to run, selecting whole modules rather than a substring. This is what
    `run_all.py --changed` uses: one source edit maps to SEVERAL modules
    at once, which a single substring cannot express (#72). Intersected
    with test_filter when both are given.

    include_manual: the DEFAULT run is the FAST tier. A test_*.py module
    that carries `MANUAL = True` -- the same marker the g2_* measurement
    scripts use -- is excluded from it, because its subject is an
    end-to-end rebuild, a GUI click-through or a measurement sweep rather
    than a unit invariant (the cost the owner reported as "out of hand").
    The manual tier is NOT dropped: `run_all.py --manual`
    (include_manual=True) runs it on demand, and a module selected by a
    by-name `test_filter` or listed in `test_modules` (`--changed`) always
    runs -- an explicit request outranks the tier gate. Tests/
    test_manual_tier.py asserts every marked module still imports and still
    carries tests. Without that test the fast tier would silently lose
    coverage instead of splitting it.
    """
    funcs = []
    # Ticket #26: the chain gate is the acceptance gate and always runs
    # LAST -- collect every other module alphabetically, then append
    # test_chain.py's tests so it is literally the final test executed.
    _paths = sorted(glob.glob(os.path.join(_TESTS_DIR, "test_*.py")))
    _chain = [p for p in _paths if os.path.basename(p) == "test_chain.py"]
    _paths = [p for p in _paths if os.path.basename(p) != "test_chain.py"]
    # Normalise once: a bare string would iterate CHARACTERS ('test_chain'
    # -> {'t', 'e', 's', ...}).
    if isinstance(test_modules, str):
        test_modules = [test_modules]
    named_modules = set(test_modules) if test_modules is not None else set()
    for path in _paths + _chain:
        basename = os.path.splitext(os.path.basename(path))[0]
        mod_name = "Tests." + basename
        mod = importlib.import_module(mod_name)
        # The fast tier is the default; a MANUAL module runs only when the
        # run asks for the manual tier, or when this run selects it
        # explicitly (a by-name filter, or a named module via --changed).
        if (getattr(mod, "MANUAL", False) and not include_manual
                and test_filter is None
                and basename not in named_modules):
            continue
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
        funcs = [
            f for f in funcs
            if (f.__module__ or "").split(".")[-1] in named_modules
        ]
    if test_filter is not None:
        funcs = [
            f for f in funcs
            if test_filter in f.__name__ or test_filter in (f.__module__ or "")
        ]
    return funcs


def manual_module_basenames():
    """The test_*.py modules in the manual tier, by basename.

    Imports every test module to read its marker -- the same price the
    default run pays anyway -- so a module moved between tiers is seen by
    Tests/test_manual_tier.py without a hand-kept list here.
    """
    names = []
    for path in sorted(glob.glob(os.path.join(_TESTS_DIR, "test_*.py"))):
        basename = os.path.splitext(os.path.basename(path))[0]
        mod = importlib.import_module("Tests." + basename)
        if getattr(mod, "MANUAL", False):
            names.append(basename)
    return names
