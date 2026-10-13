"""Which test modules a source change can possibly break (#72).

The suite takes ~6.5 minutes, and a two-line edit to `SilkPatch.py` does
not need it. This maps a set of changed files to the test modules worth
running, so the inner loop is seconds instead of minutes.

**The map is derived from imports, not hand-written.** A hand-kept
module-to-module table rots the moment someone adds an import, and a
table that has quietly gone stale is worse than none: it makes a partial
run look like a full one. Parsing the actual imports cannot rot -- add
`import SilkMachinery` to a test and it is covered automatically.

The rule is deliberately CONSERVATIVE. A changed file whose dependents
cannot be determined -- a brand-new production module, a test helper, a
resource -- yields "run everything". A partial run that is wrong in the
direction of running too little is how you ship a break; one that runs
too much only costs time, which is the cheap failure.
"""

import ast
import os
import subprocess

_TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
MOD_DIR = os.path.dirname(_TESTS_DIR)


_PROD_CACHE = []
_IMPORTS_CACHE = {}


def production_modules():
    """Top-level Mod .py files, by module name (the legacy Control*/Cubic*
    helpers included -- they are importable and therefore dependency
    bearing). Cached: this is called once per closure expansion."""
    if not _PROD_CACHE:
        for fn in os.listdir(MOD_DIR):
            if fn.endswith(".py"):
                _PROD_CACHE.append(fn[:-3])
    return set(_PROD_CACHE)


def imports_of(path):
    """Top-level module names imported by `path`, from its AST.

    Cached by path: without this the dependency map parses
    `ArachNURBS.py` (3,500 lines) thousands of times and takes longer than
    the test run it is meant to shorten -- measured as a >120s timeout.

    Unparseable files (or ones importing inside functions, which AST
    still sees) yield what they can rather than raising: this is a
    best-effort speed aid, never a correctness gate."""
    hit = _IMPORTS_CACHE.get(path)
    if hit is not None:
        return hit
    try:
        tree = ast.parse(open(path, encoding="utf-8").read(), path)
    except (OSError, SyntaxError, UnicodeDecodeError):
        names = set()
    else:
        names = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for a in node.names:
                    names.add(a.name.split(".")[0])
            elif isinstance(node, ast.ImportFrom):
                if node.module and node.level == 0:   # 0 == absolute only
                    names.add(node.module.split(".")[0])
    _IMPORTS_CACHE[path] = names
    return names


def _production_closure(root):
    """Transitive production imports of `root`, restricted to files that
    actually exist under Mod.

    Transitive because `SilkPatch` imports `SilkMachinery`: changing the
    machinery can break the patch, and a direct-imports-only map would
    miss it.

    NOTE: the set of production modules is fetched here, inside the
    function. An earlier version took the set as a parameter and shadowed
    it with the root's name, so `dep in prod` tested membership in a
    STRING and the closure silently collapsed to the module itself -- a
    map that looked derived and quietly was not."""
    prod = production_modules()
    seen, stack = set(), [root]
    while stack:
        cur = stack.pop()
        if cur in seen:
            continue
        seen.add(cur)
        path = os.path.join(MOD_DIR, cur + ".py")
        if not os.path.exists(path):
            continue
        for dep in imports_of(path):
            if dep in prod and dep not in seen:
                stack.append(dep)
    return seen


def test_module_dependencies():
    """{test module basename: set of production modules it can be broken
    by}, including transitive production imports of its production ones.

    Tests import each other too (fixtures: `test_seam_resolver` is used
    widely), so a change to a test module selects the modules that
    IMPORT it."""
    import glob
    prod = production_modules()
    tests = {}
    for path in sorted(glob.glob(os.path.join(_TESTS_DIR, "test_*.py"))):
        name = os.path.splitext(os.path.basename(path))[0]
        direct = imports_of(path) & prod
        closure = set()
        for d in direct:
            closure |= _production_closure(d)
        tests[name] = closure
    # a test module that another test module imports is itself a dependency
    names = {os.path.splitext(os.path.basename(p))[0]
             for p in glob.glob(os.path.join(_TESTS_DIR, "test_*.py"))}
    for path in sorted(glob.glob(os.path.join(_TESTS_DIR, "test_*.py"))):
        name = os.path.splitext(os.path.basename(path))[0]
        for dep in imports_of(path) & names:
            if dep != name:
                tests[name] |= tests.get(dep, set())
    return tests


def changed_files(ref=None):
    """Files changed relative to `ref` (default: the working tree vs HEAD).

    Staged, unstaged and brand-new-untracked all count, because all three
    can break a test."""
    try:
        out = subprocess.run(["git", "diff", "--name-only", ref or "HEAD"],
                             cwd=MOD_DIR, capture_output=True, text=True,
                             timeout=30).stdout.split()
        out += subprocess.run(["git", "diff", "--name-only", "--cached"],
                              cwd=MOD_DIR, capture_output=True, text=True,
                              timeout=30).stdout.split()
        out += subprocess.run(["git", "ls-files", "--others",
                               "--exclude-standard"],
                              cwd=MOD_DIR, capture_output=True, text=True,
                              timeout=30).stdout.split()
    except (OSError, subprocess.SubprocessError):
        return None
    return sorted(set(out))


# Files whose damage an import graph cannot express. InitGui.py is
# exec'd by FreeCAD, never imported, so no test imports it and AST sees
# nothing -- yet test_initgui_commands exists precisely for it. The test
# infrastructure is not imported by production at all, so changing it can
# break anything: those run everything.
_EXPLICIT = {
    "InitGui.py": {"test_initgui_commands"},
    "Init.py": {"test_initgui_commands"},
    "popup.py": {"test_initgui_commands"},
    "Reload_Silk.py": {"test_initgui_commands"},
}
_INFRA = ("run_all.py", "silk_reload.py", "mcp_harness.py", "suite.py",
          "deps.py", "conftest.py")


def modules_for_paths(paths):
    """Test modules to run for these changed paths.

    Returns (module_names, reason). `module_names` empty means "run
    everything" -- so the caller never silently skips work."""
    if not paths:
        return [], "no changes"
    deps = test_module_dependencies()
    wanted, unknown = set(), []
    for p in paths:
        rel = os.path.relpath(os.path.abspath(os.path.join(MOD_DIR, p)),
                              MOD_DIR)
        base, ext = os.path.splitext(rel)
        if ext != ".py":
            # a resource, fixture or doc: not something imports track
            unknown.append(p)
            continue
        if base.startswith("Tests" + os.sep) or base.startswith("Tests."):
            leaf = base.split(os.sep)[-1].split(".")[-1]
            if leaf in _INFRA:
                return [], "test infrastructure changed (%s)" % leaf
            hit = {n for n, d in deps.items() if leaf in d or n == leaf}
            if not hit:
                unknown.append(p)
            wanted |= hit
            continue
        leaf = base.split(os.sep)[-1]
        if leaf + ext in _EXPLICIT:
            wanted |= _EXPLICIT[leaf + ext]
            continue
        hit = {n for n, d in deps.items() if base in d or leaf in d}
        if hit:
            wanted |= hit
        else:
            # a production module nothing imports from a test: rather than
            # silently run nothing, run the tests that touch the area
            unknown.append(p)
    if unknown:
        return [], "unmapped change(s): %s" % ", ".join(unknown[:6])
    return sorted(wanted), "derived from %d changed file(s)" % len(paths)