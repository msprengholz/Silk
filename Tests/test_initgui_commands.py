"""
Visible-command contract for InitGui.py (ticket #50).

The ticket shrinks the workbench's VISIBLE surface to five commands --
the workflow triad (Edge -> Patch -> Blend), the guide, and the dev hot
reload -- and groups them. The thing that can silently go wrong is the
other direction: a name that is no longer visible but is still needed to
RESTORE an old document, or a grouped structure that names something the
user can no longer reach (or that does not exist at all).

So these tests assert three things:

  1. The visible set is EXACTLY those five, in workflow order, and no
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

try:
    from FreeCAD import Gui
except ImportError:          # console-only FreeCAD
    Gui = None

INITGUI = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                       "..", "InitGui.py")
FIXTURE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           "..", "Resources", "Test_files")

# The five, spelled out independently of InitGui.py's own constants so a
# typo in the file cannot make the test agree with itself.
EXPECTED_VISIBLE = ["Silk_CreateEdge", "Silk_CreatePatch", "Silk_CreateBlend",
                    "Silk_Guide", "Reload_Silk"]
EXPECTED_WORKFLOW = ["Silk_CreateEdge", "Silk_CreatePatch", "Silk_CreateBlend"]
EXPECTED_GROUPS = ["Workflow", "Guide", "Dev"]

# Modules a legacy document's proxy needs at open time (ticket #50).
RESTORE_CRITICAL = ["ArachNURBS", "SilkWorkflow", "SilkPatch44", "SilkEdge",
                    "SilkPatch", "SilkBlend", "SilkCorner"]

# ...and the subset Initialize() is expected to import up front. SilkPatch44
# and SilkCorner are reached lazily (SilkBlend imports SilkCorner; FreeCAD's
# restore imports SilkPatch44 on demand), so they are asserted importable
# rather than asserted to be in the import block.
IMPORTED_UP_FRONT = ["ArachNURBS", "SilkWorkflow", "SilkEdge", "SilkPatch",
                     "SilkBlend"]

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


def check(cond, msg, errors):
    if not cond:
        errors.append(msg)
    return cond


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


def test_visible_commands_are_exactly_the_five(doc):
    """VISIBLE_COMMANDS is exactly the five, in workflow order, and none of
    the thirty legacy command names survives in ANY visible structure."""
    errors, checks = [], []
    mod, _tree = load_initgui()

    workflow = list(mod.WORKFLOW_COMMANDS)
    guide = list(mod.GUIDE_COMMANDS)
    dev = list(mod.DEV_COMMANDS)
    visible = list(mod.VISIBLE_COMMANDS)

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
        "TOOLBAR_STRUCTURE": list(mod.TOOLBAR_STRUCTURE),
        "MENU_STRUCTURE": [c for _p, cmds in mod.MENU_STRUCTURE for c in cmds],
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
    check(probe.toolbars == [(mod.TOOLBAR_NAME,
                              EXPECTED_WORKFLOW + ["Separator",
                                                   "Silk_Guide",
                                                   "Separator",
                                                   "Reload_Silk"])],
          "Initialize() appendToolbar calls are %r" % (probe.toolbars,), errors)

    # the toolbar structure is flat (no nesting) and separators are exact
    tb = list(mod.TOOLBAR_STRUCTURE)
    check(tb.count("Separator") == 2,
          "TOOLBAR_STRUCTURE has %d Separator entries, expected 2"
          % tb.count("Separator"), errors)
    check("Separator" not in tb[0] and "Separator" not in tb[-1],
          "TOOLBAR_STRUCTURE starts or ends with a separator: %r" % tb, errors)
    check([n for n in tb if n != "Separator"] == EXPECTED_VISIBLE,
          "TOOLBAR_STRUCTURE minus separators is %r, expected %r"
          % ([n for n in tb if n != "Separator"], EXPECTED_VISIBLE), errors)

    # nothing is dropped between the flat list and the grouped menus
    in_menus = [c for _p, cmds in mod.MENU_STRUCTURE for c in cmds]
    check(sorted(in_menus) == sorted(mod.VISIBLE_COMMANDS),
          "MENU_STRUCTURE covers %r but VISIBLE_COMMANDS is %r"
          % (in_menus, mod.VISIBLE_COMMANDS), errors)
    check(list(mod.VISIBLE_COMMANDS) == [n for n in tb if n != "Separator"],
          "the toolbar and VISIBLE_COMMANDS disagree about what is visible",
          errors)

    # self.list (the context menu source) is the same five, nothing legacy
    check(list(probe.list) == EXPECTED_VISIBLE,
          "self.list is %r, expected %r" % (probe.list, EXPECTED_VISIBLE),
          errors)
    checks.append("Silk -> Workflow[3] / Guide[1] / Dev[1]; toolbar "
                  "Edge,Patch,Blend | Guide | Reload")
    return {"pass": not errors, "errors": errors, "checks": checks}


def test_every_visible_command_is_registered(doc):
    """Each of the five was really handed to Gui.addCommand.

    Verified through public API only: Gui.listCommands() lists what the
    command manager holds, and the QAction it built carries the command
    name as its objectName with a non-empty label. A name that is listed
    but never registered is absent from listCommands() and fails here."""
    errors, checks = [], []
    if Gui is None:
        errors.append("no Gui: Gui.listCommands() unavailable, cannot "
                      "verify command registration")
        return {"pass": False, "errors": errors, "checks": checks}

    mod, _tree = load_initgui()
    # run the real import block so registration happens even in a session
    # where the Silk workbench has not been activated
    init = initialize_node(_tree)
    for name in imported_modules(init):
        importlib.import_module(name)

    registered = set(Gui.listCommands())
    missing = [n for n in mod.VISIBLE_COMMANDS if n not in registered]
    check(not missing,
          "listed but NOT registered with FreeCAD: %r" % missing, errors)

    # the command manager built a real action for each one
    try:
        from PySide6 import QtGui
        QAction = QtGui.QAction
    except ImportError:
        from PySide import QtGui
        QAction = QtGui.QAction
    mw = Gui.getMainWindow()
    acted, labelled = [], []
    for name in mod.VISIBLE_COMMANDS:
        action = mw.findChild(QAction, name)
        if action is None:
            errors.append("no QAction named %s -- the command exists but "
                          "FreeCAD built no action for it" % name)
            continue
        acted.append(name)
        if not action.text().strip():
            errors.append("QAction %s has an empty label" % name)
        elif name in labelled:
            errors.append("QAction %s duplicates %s" % (name, labelled[-1]))
        labelled.append(name)

    checks.append("Gui.listCommands() holds all %d: %s"
                  % (len(acted), ", ".join(acted)))
    return {"pass": not errors, "errors": errors, "checks": checks}


def test_initialize_keeps_the_legacy_import_block(doc):
    """Restore safety (#50): Initialize() still imports the whole legacy
    block, so every proxy module a reference document names stays
    importable at open time, and no import was traded away for the
    visible-list cleanup."""
    errors, checks = [], []
    mod, tree = load_initgui()
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


ALL_TESTS = [
    test_visible_commands_are_exactly_the_five,
    test_grouped_structures_reference_only_visible_commands,
    test_every_visible_command_is_registered,
    test_initialize_keeps_the_legacy_import_block,
]
