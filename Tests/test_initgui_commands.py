"""
Visible-command contract for InitGui.py (ticket #50).

The ticket shrinks the workbench's VISIBLE surface to seven commands --
the workflow pentad (Edge -> Patch -> Blend -> Corner Blend, plus the
FreeCAD corner fill of #96), the guide, and the dev hot reload -- and
groups them. The thing that can silently go wrong is the other direction:
a name that is no longer visible but is
still needed to RESTORE an old document, or a grouped structure that
names something the user can no longer reach (or that does not exist at
all).

So these tests assert three things:

  1. The visible set is EXACTLY those seven, in workflow order, and no
     legacy name survives anywhere in the visible structures.
  2. Every visible name is really registered -- checked through a public
     API (Gui.listCommands(), plus the QAction FreeCAD's command manager
     actually built for it). No monkeypatching: a name that is listed but
     was never passed to Gui.addCommand fails here.
  3. The grouped menu/toolbar structures reference only visible names.

Plus the restore-safety guard (#50's constraint): Initialize() keeps the
whole legacy import block, so every proxy module named by a reference
document's Document.xml stays importable at open time.

Why InitGui.py is loaded rather than imported: the file's last line is
`FreeCAD.Gui.addWorkbench(Silk())`, and FreeCAD raises KeyError when the
workbench name is already taken (it always is, in a session where Silk
has run). The module is therefore executed with exactly that one call
stripped from its AST -- every declaration under test is above it, and
`Workbench` is injected exactly as FreeCAD injects it. Nothing else is
altered: the constants, the class, and Initialize() all come from the
real file.
"""
import ast
import importlib
import os
import re
import types
import zipfile

import FreeCAD
from Tests.mcp_harness import check

try:
    from FreeCAD import Gui
except ImportError:          # console-only FreeCAD
    Gui = None

INITGUI = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                       "..", "InitGui.py")
FIXTURE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           "..", "Resources", "Test_files")

# The visible set, spelled out independently of InitGui.py's own
# constants so a typo in the file cannot make the test agree with itself.
# `Silk_CornerFill` is #96's owner decision D3: the fill button stands
# beside the Silk corner blend.
EXPECTED_VISIBLE = ["Silk_CreateEdge", "Silk_CreatePatch", "Silk_CreateBlend",
                    "Silk_CreateCornerBlend", "Silk_CornerFill", "Silk_Guide",
                    "Reload_Silk"]
EXPECTED_WORKFLOW = ["Silk_CreateEdge", "Silk_CreatePatch", "Silk_CreateBlend",
                     "Silk_CreateCornerBlend", "Silk_CornerFill"]
EXPECTED_GROUPS = ["Workflow", "Guide", "Dev"]

# Modules a legacy document's proxy needs at open time (ticket #50).
RESTORE_CRITICAL = ["ArachNURBS", "SilkWorkflow", "SilkPatch44", "SilkEdge",
                    "SilkPatch", "SilkBlend", "SilkCorner"]

# ...and the subset Initialize() is expected to import up front. SilkCorner
# is reached lazily (SilkBlend imports it), so it is asserted importable
# rather than asserted to be in the import block. SilkPatch44 IS in the
# import block: the docstring's old-document-restore story names it
# (Silk_Workflow.FCStd -> SilkPatch44 / SilkBlend / SilkEdge), and a
# restore shim with no command registration costs nothing up front.
IMPORTED_UP_FRONT = ["ArachNURBS", "SilkWorkflow", "SilkEdge", "SilkPatch",
                     "SilkPatch44", "SilkBlend"]

# Every legacy command name that used to be visible. None may reappear.
LEGACY_NAMES = [
    "ControlPoly4", "CubicCurve_4", "Point_onCurve", "BoundarySpline",
    "ControlPoly4_segment", "ControlGrid44", "ControlGrid44_Rotate",
    "ControlGrid44_flow", "CubicSurface_44", "ControlGrid44_EdgeSegment",
    "ControlGrid44_2EdgeSegments", "ControlPoly6", "CubicCurve_6",
    "ControlGrid66", "CubicSurface_66", "ControlGrid64", "CubicSurface_64",
    "ControlGrid64_2Grid44", "ControlGrid64_3_1Grid44", "ControlGrid64_normal",
    "ControlGrid64_Surf44", "SubGrid33_2Grid64", "ControlGrid66_4Sub",
    "SubGrid63_2Surf64", "ControlGridNStar66", "CubicNStarSurface_NStar66",
    "StarTrim_CubicNStar", "SilkPose", "Silk_CreateBoundarySpline",
    "Silk_CreateControlGridPatch",
]


def _is_addworkbench_call(node):
    """True for the module-level `FreeCAD.Gui.addWorkbench(Silk())`."""
    return (isinstance(node, ast.Expr)
            and isinstance(node.value, ast.Call)
            and isinstance(node.value.func, ast.Attribute)
            and node.value.func.attr == "addWorkbench")


def load_initgui(workbench_base=None):
    """Execute the real InitGui.py minus its workbench registration.

    Returns (module, tree): the executed module (so the module-level
    constants can be read as FreeCAD would see them) and its AST (so
    Initialize()'s body can be inspected without running it -- running it
    would append to the live workbench's menus and toolbars).

    workbench_base: what `Workbench` resolves to inside the exec'd file.
    Defaults to the real Gui.Workbench; pass a recorder to capture what
    Initialize() hands FreeCAD without touching the live workbench.
    """
    path = os.path.abspath(INITGUI)
    with open(path) as fh:
        src = fh.read()
    tree = ast.parse(src, path)
    body = [n for n in tree.body if not _is_addworkbench_call(n)]
    stripped = len(tree.body) - len(body)
    if stripped != 1:
        raise AssertionError(
            "expected exactly one addWorkbench call in InitGui.py, found %d"
            % stripped)
    if workbench_base is None:
        workbench_base = Gui.Workbench if Gui is not None else object
    mod = types.ModuleType("SilkInitGuiUnderTest")
    mod.__dict__["__file__"] = path
    # FreeCAD injects this name into InitGui.py's namespace before exec;
    # `class Silk(Workbench)` needs it.
    mod.__dict__["Workbench"] = workbench_base
    exec(compile(ast.Module(body=body, type_ignores=[]), path, "exec"),
         mod.__dict__)
    return mod, tree


def initialize_node(tree):
    """The FunctionDef for Silk.Initialize."""
    cls = [n for n in tree.body if isinstance(n, ast.ClassDef)]
    if len(cls) != 1:
        raise AssertionError("expected exactly one class in InitGui.py")
    fns = [n for n in cls[0].body
           if isinstance(n, ast.FunctionDef) and n.name == "Initialize"]
    if len(fns) != 1:
        raise AssertionError("expected exactly one Initialize method")
    return fns[0]


def imported_modules(init_node):
    return [a.name for n in init_node.body if isinstance(n, ast.Import)
            for a in n.names]


def document_modules(path):
    """Every `module="..."` proxy module named in a .FCStd's Document.xml."""
    with zipfile.ZipFile(path) as zf:
        xml = zf.read("Document.xml").decode("utf-8", "replace")
    mods = set(re.findall(r'module="([^"]+)"', xml))
    return sorted(m for m in mods if m and "." not in m)


def test_visible_commands_are_exactly_the_expected_set(doc):
    """VISIBLE_COMMANDS is exactly the expected set, in workflow order, and
    none of the thirty legacy command names survives in ANY visible
    structure."""
    errors, checks = [], []
    mod, _tree = load_initgui()
    silk = mod.Silk

    workflow = list(silk.WORKFLOW_COMMANDS)
    guide = list(silk.GUIDE_COMMANDS)
    dev = list(silk.DEV_COMMANDS)
    visible = list(silk.VISIBLE_COMMANDS)

    check(workflow == EXPECTED_WORKFLOW,
          "WORKFLOW_COMMANDS is %r, expected %r" % (workflow, EXPECTED_WORKFLOW),
          errors)
    check(guide == ["Silk_Guide"],
          "GUIDE_COMMANDS is %r, expected ['Silk_Guide']" % (guide,), errors)
    check(dev == ["Reload_Silk"],
          "DEV_COMMANDS is %r, expected ['Reload_Silk']" % (dev,), errors)
    check(visible == EXPECTED_VISIBLE,
          "VISIBLE_COMMANDS is %r, expected exactly %r"
          % (visible, EXPECTED_VISIBLE), errors)
    check(sorted(visible) == sorted(set(visible)),
          "VISIBLE_COMMANDS contains a duplicate: %r" % visible, errors)

    # every name reachable from the user sits in one of the three groups
    grouped = [n for group in (workflow, guide, dev) for n in group]
    check(sorted(grouped) == sorted(visible),
          "the three groups cover %r but VISIBLE_COMMANDS is %r"
          % (grouped, visible), errors)

    # and no legacy name is still visible anywhere
    structures = {
        "WORKFLOW_COMMANDS": workflow,
        "GUIDE_COMMANDS": guide,
        "DEV_COMMANDS": dev,
        "VISIBLE_COMMANDS": visible,
        "TOOLBAR_STRUCTURE": list(silk.TOOLBAR_STRUCTURE),
        "MENU_STRUCTURE": [c for _p, cmds in silk.MENU_STRUCTURE for c in cmds],
    }
    for label, names in structures.items():
        stale = [n for n in names if n in LEGACY_NAMES]
        check(not stale, "%s still lists legacy command(s) %r" % (label, stale),
              errors)
        unknown = [n for n in names if n not in EXPECTED_VISIBLE
                   and n != "Separator"]
        check(not unknown, "%s names non-visible command(s) %r" % (label, unknown),
              errors)
    checks.append("visible set is exactly %r; 0 of %d legacy names remain"
                  % (visible, len(LEGACY_NAMES)))
    return {"pass": not errors, "errors": errors, "checks": checks}


def test_grouped_structures_reference_only_visible_commands(doc):
    """MENU_STRUCTURE is three Silk submenus (Workflow / Guide / Dev) fed
    their group's commands, and TOOLBAR_STRUCTURE is the flat list with
    exactly two Separator entries in the right places. Both together name
    every visible command exactly once and nothing else."""
    errors, checks = [], []

    class _SilentWorkbench(object):
        """Captures what Initialize() would hand FreeCAD, without
        touching the live workbench's menus and toolbars.

        Silk.__init__ does not chain to the base __init__, so the
        capture lists are class-level and reset per probe below.
        """
        menus = []
        toolbars = []

        def appendMenu(self, menu, items):
            self.menus.append((list(menu), list(items)))

        def appendToolbar(self, bar, items):
            self.toolbars.append((bar, list(items)))

        def appendContextMenu(self, menu, items):
            pass

        def GetClassName(self):
            return "Gui::PythonWorkbench"

    mod, _tree = load_initgui(workbench_base=_SilentWorkbench)
    silk = mod.Silk
    probe = mod.Silk()
    probe.menus = []
    probe.toolbars = []
    probe.Initialize()      # the real Initialize(), real import block

    check(probe.menus == [(["Silk", "Workflow"], EXPECTED_WORKFLOW),
                          (["Silk", "Guide"], ["Silk_Guide"]),
                          (["Silk", "Dev"], ["Reload_Silk"])],
          "Initialize() appendMenu calls are %r, expected Silk -> "
          "Workflow/Guide/Dev" % (probe.menus,), errors)
    groups = [path[-1] for path, _items in probe.menus]
    check(groups == EXPECTED_GROUPS,
          "submenu names are %r, expected %r" % (groups, EXPECTED_GROUPS),
          errors)
    check(probe.toolbars == [(silk.TOOLBAR_NAME,
                              EXPECTED_WORKFLOW + ["Separator",
                                                   "Silk_Guide",
                                                   "Separator",
                                                   "Reload_Silk"])],
          "Initialize() appendToolbar calls are %r" % (probe.toolbars,), errors)

    # the toolbar structure is flat (no nesting) and separators are exact
    tb = list(silk.TOOLBAR_STRUCTURE)
    check(tb.count("Separator") == 2,
          "TOOLBAR_STRUCTURE has %d Separator entries, expected 2"
          % tb.count("Separator"), errors)
    check("Separator" not in tb[0] and "Separator" not in tb[-1],
          "TOOLBAR_STRUCTURE starts or ends with a separator: %r" % tb, errors)
    check([n for n in tb if n != "Separator"] == EXPECTED_VISIBLE,
          "TOOLBAR_STRUCTURE minus separators is %r, expected %r"
          % ([n for n in tb if n != "Separator"], EXPECTED_VISIBLE), errors)

    # nothing is dropped between the flat list and the grouped menus
    in_menus = [c for _p, cmds in silk.MENU_STRUCTURE for c in cmds]
    check(sorted(in_menus) == sorted(silk.VISIBLE_COMMANDS),
          "MENU_STRUCTURE covers %r but VISIBLE_COMMANDS is %r"
          % (in_menus, silk.VISIBLE_COMMANDS), errors)
    check(list(silk.VISIBLE_COMMANDS) == [n for n in tb if n != "Separator"],
          "the toolbar and VISIBLE_COMMANDS disagree about what is visible",
          errors)

    # self.list (the context menu source) is the same seven, nothing legacy
    check(list(probe.list) == EXPECTED_VISIBLE,
          "self.list is %r, expected %r" % (probe.list, EXPECTED_VISIBLE),
          errors)
    checks.append("Silk -> Workflow[5] / Guide[1] / Dev[1]; toolbar "
                  "Edge,Patch,Blend,Corner,Fill | Guide | Reload")
    return {"pass": not errors, "errors": errors, "checks": checks}


def test_every_visible_command_is_registered(doc):
    """Each visible command was really handed to Gui.addCommand.

    Verified through public API only: Gui.listCommands() lists what the
    command manager holds, and Gui.Command.get(name).getAction() returns
    the real QAction the command manager builds for it, carrying the
    command name as its objectName and a non-empty label. A name that is
    listed but never registered is absent from listCommands() and
    Gui.Command.get returns None.

    Why getAction() and not MainWindow.findChild(QAction, name): FreeCAD
    builds a command's QAction when the command first lands in a toolbar
    or menu. A long-running dev session therefore has actions only for the
    commands its toolbar was built with, so findChild would silently test
    the session's startup generation, not the code under test.

    MEASURED, and the reason the action is checked where it EXISTS (#96):
    `getAction()` does NOT build the action on demand. In a session that has
    been up since before a name joined the visible set, that name's action
    list is empty while every name the running toolbar was built with keeps
    its action across a hot reload (probe, this session: Silk_CornerFill 0
    actions, Silk_CreateEdge/Patch/Blend/CornerBlend/Guide/Reload_Silk 1).
    So a name the session's toolbar predates is REPORTED, not failed -- what
    is asserted for every visible name is registration (listCommands() and
    Command.get()) plus the structures handed to appendToolbar/appendMenu,
    which is what builds the action on the next activation.
    """
    errors, checks = [], []
    if Gui is None:
        errors.append("no Gui: Gui.listCommands() unavailable, cannot "
                      "verify command registration")
        return {"pass": False, "errors": errors, "checks": checks}

    mod, _tree = load_initgui()
    silk = mod.Silk
    # run the real import block so registration happens even in a session
    # where the Silk workbench has not been activated
    init = initialize_node(_tree)
    for name in imported_modules(init):
        importlib.import_module(name)

    registered = set(Gui.listCommands())
    missing = [n for n in silk.VISIBLE_COMMANDS if n not in registered]
    check(not missing,
          "listed but NOT registered with FreeCAD: %r" % missing, errors)

    # the command manager built a real action for each one -- where this
    # session has one (see the docstring: getAction() does not build on
    # demand, so a name that joined the visible set after this FreeCAD
    # started has none until the workbench is activated again).
    acted, unbuilt = [], []
    for name in silk.VISIBLE_COMMANDS:
        command = Gui.Command.get(name)
        if command is None:
            errors.append("no command named %s -- absent from FreeCAD's "
                          "command manager" % name)
            continue
        actions = command.getAction() or []
        if not actions:
            unbuilt.append(name)
            continue
        acted.append(name)
        wrong = [a for a in actions if a.objectName() != name]
        if wrong:
            errors.append("QAction(s) of %s carry the wrong objectName: %r"
                          % (name, [a.objectName() for a in wrong]))
        if not actions[0].text().strip():
            errors.append("QAction %s has an empty label" % name)

    # a name the running session's toolbar predates must be in the structures
    # Initialize() hands FreeCAD, or nothing would ever build its button
    handed_over = (set(silk.TOOLBAR_STRUCTURE)
                   | {c for _p, cmds in silk.MENU_STRUCTURE for c in cmds})
    stale = [n for n in unbuilt if n not in handed_over]
    check(not stale,
          "visible name(s) %r build no action AND are not in the toolbar "
          "structure" % stale, errors)
    checks.append("Gui.listCommands() holds all %d: %s"
                  % (len(acted), ", ".join(acted)))
    if unbuilt:
        checks.append("session's toolbar predates %r -- no QAction yet, "
                      "registration asserted, structures pinned by the "
                      "sibling test" % unbuilt)
    return {"pass": not errors, "errors": errors, "checks": checks}


def test_initialize_keeps_the_legacy_import_block(doc):
    """Restore safety (#50): Initialize() still imports the whole legacy
    block, so every proxy module a reference document names stays
    importable at open time, and no import was traded away for the
    visible-list cleanup."""
    errors, checks = [], []
    mod, tree = load_initgui()
    silk = mod.Silk
    init = initialize_node(tree)
    imports = imported_modules(init)

    absent = [m for m in IMPORTED_UP_FRONT if m not in imports]
    check(not absent,
          "Initialize() no longer imports restore-critical module(s) %r"
          % absent, errors)
    check(len(imports) >= len(IMPORTED_UP_FRONT),
          "Initialize() imports only %d modules (%r) -- the legacy block "
          "looks truncated" % (len(imports), imports), errors)

    # every proxy module the reference documents name must be importable
    referenced = set()
    fixtures = sorted(f for f in os.listdir(FIXTURE_DIR)
                      if f.endswith(".FCStd"))
    check(fixtures, "no .FCStd fixtures found in %s" % FIXTURE_DIR, errors)
    for fname in fixtures:
        try:
            mods = document_modules(os.path.join(FIXTURE_DIR, fname))
        except Exception as e:
            errors.append("could not read %s: %s: %s"
                          % (fname, type(e).__name__, e))
            continue
        referenced.update(mods)
    for m in sorted(referenced):
        try:
            importlib.import_module(m)
        except Exception as e:
            errors.append("proxy module %s (named by a reference document) "
                          "is not importable: %s: %s"
                          % (m, type(e).__name__, e))
    missing_critical = [m for m in RESTORE_CRITICAL if m not in referenced]
    check(not missing_critical,
          "the reference documents no longer name %r -- this spot-check's "
          "coverage has gone stale" % missing_critical, errors)

    checks.append("%d Initialize() imports kept; all %d referenced proxy "
                  "modules importable (%s)"
                  % (len(imports), len(referenced),
                     ", ".join(sorted(referenced))))
    return {"pass": not errors, "errors": errors, "checks": checks}


def test_initialize_survives_freecad_namespace_strip(doc):
    """Regression (#50 follow-up, found in the real GUI): FreeCAD loads a
    workbench's InitGui.py by exec'ing it into __main__ and then STRIPPING
    the names the file defined back out of that namespace -- the registered
    class's methods keep __main__ as their globals, so a module-level
    constant referenced from Initialize() raises NameError and the
    workbench fails to load ("name 'VISIBLE_COMMANDS' is not defined").

    Executing the file in a plain namespace hides this, because nothing is
    stripped there. So this test reproduces the real path: exec the file,
    then delete every name the file itself defined (keeping the injected
    builtins FreeCAD provides), then run the real Initialize(). The visible
    commands must still be there -- which they only are because they are
    CLASS ATTRIBUTES, not module globals.
    """
    errors, checks = [], []

    class _SilentWorkbench(object):
        menus = []
        toolbars = []

        def appendMenu(self, menu, items):
            self.menus.append((list(menu), list(items)))

        def appendToolbar(self, bar, items):
            self.toolbars.append((bar, list(items)))

        def appendContextMenu(self, menu, items):
            pass

        def GetClassName(self):
            return "Gui::PythonWorkbench"

    path = os.path.abspath(INITGUI)
    with open(path) as fh:
        src = fh.read()
    tree = ast.parse(src, path)
    body = [n for n in tree.body if not _is_addworkbench_call(n)]
    mod = types.ModuleType("SilkInitGuiStripped")
    mod.__dict__["__file__"] = path
    mod.__dict__["Workbench"] = _SilentWorkbench
    exec(compile(ast.Module(body=body, type_ignores=[]), path, "exec"),
         mod.__dict__)

    # Reproduce FreeCAD: keep only what FreeCAD itself injected, drop
    # every name the file defined at module level. (FreeCAD strips the
    # class name too; the registered workbench instance holds the class
    # alive regardless, so we keep our own reference first.)
    silk_cls = mod.Silk
    file_defined = set()
    for node in body:
        if isinstance(node, ast.Assign):
            file_defined.update(t.id for t in node.targets
                                if isinstance(t, ast.Name))
        elif isinstance(node, ast.ClassDef):
            file_defined.add(node.name)
        elif isinstance(node, (ast.FunctionDef, ast.Import, ast.ImportFrom)):
            name = getattr(node, "name", None) or getattr(node, "module", None)
            if name:
                file_defined.add(name.split(".")[0])
    for name in file_defined:
        mod.__dict__.pop(name, None)
    checks.append("stripped %d module-level names the way FreeCAD does"
                  % len(file_defined))

    probe = silk_cls()
    probe.menus = []
    probe.toolbars = []
    try:
        probe.Initialize()          # the real Initialize(), stripped ns
    except NameError as e:
        errors.append("Initialize() raised NameError after FreeCAD's "
                      "namespace strip: %s -- the visible-command lists "
                      "must be class attributes, not module globals" % e)
        return {"pass": False, "errors": errors, "checks": checks}
    except Exception as e:
        errors.append("Initialize() raised %s after the namespace strip: %s"
                      % (type(e).__name__, e))
        return {"pass": False, "errors": errors, "checks": checks}

    check(probe.list == list(silk_cls.VISIBLE_COMMANDS),
          "after the strip, self.list is %r, expected %r"
          % (probe.list, list(silk_cls.VISIBLE_COMMANDS)), errors)
    check([c for _p, cmds in probe.menus for c in cmds]
          == list(silk_cls.VISIBLE_COMMANDS),
          "after the strip, the menus name %r, expected %r"
          % ([c for _p, cmds in probe.menus for c in cmds],
             list(silk_cls.VISIBLE_COMMANDS)), errors)
    checks.append("Initialize() survived the strip: self.list = %r, %d "
                  "menus, %d toolbar"
                  % (probe.list, len(probe.menus), len(probe.toolbars)))

    # And the guard itself: Initialize() must not reach for the old bare
    # module globals -- assert from its AST that every load of the list
    # names is an attribute access (self.X), not a bare Name.
    cls_node = [n for n in body if isinstance(n, ast.ClassDef)][0]
    init_node = [n for n in cls_node.body
                 if isinstance(n, ast.FunctionDef) and n.name == "Initialize"][0]
    bare = sorted({n.id for n in ast.walk(init_node)
                   if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load)
                   and n.id in ("VISIBLE_COMMANDS", "TOOLBAR_STRUCTURE",
                                 "MENU_STRUCTURE", "TOOLBAR_NAME")})
    check(not bare,
          "Initialize() still reads the bare module global(s) %r; they must "
          "be read through self.<name> (class attributes)" % (bare,), errors)
    checks.append("Initialize() reads the lists through self.*, not bare "
                  "module globals")
    return {"pass": not errors, "errors": errors, "checks": checks}


ALL_TESTS = [
    test_visible_commands_are_exactly_the_expected_set,
    test_grouped_structures_reference_only_visible_commands,
    test_every_visible_command_is_registered,
    test_initialize_keeps_the_legacy_import_block,
    test_initialize_survives_freecad_namespace_strip,
]
