"""
Restore contract (#93): an old document opens, restores every proxy, and
stays EDITABLE -- deleting a restored blend unblends its patches exactly
as deleting a freshly created one does.

The defect this pins. FreeCAD restores a proxy WITHOUT running __init__:
it rebuilds the proxy from the saved (empty) state, then calls
onDocumentRestored -- which is where the blend installs its #70
delete-watcher. SilkBlend.BlendStrip._install_delete_watcher read
`self._delete_watcher`, an attribute only __init__ ever created, so every
restored blend raised

    AttributeError: 'Blend' object has no attribute '_delete_watcher'

and died unwatched. Measured on Silk_Corner2x2.FCStd: all four unified
Blends (B12/B24/B43/B31) restored with no watcher, so deleting B12 left
Patch44 at U(0.0, 0.9) and Patch001 at U(0.1, 1.0) -- #70's unblend never
ran and both stayed subdivided ("an unblended patch that still renders
subdivided does not look unblended"). A freshly created blend unblends
correctly, so the bug is restore-specific.

Two things the oracle must respect:

  * the hidden CELLS are re-derived by the surviving blends and so are
    already correct even in the bug arm; assert the SPLITS, not the
    hidden set, and
  * the AttributeError is raised inside a C++ callback, so
    CaptureConsole (a Python monkeypatch of FreeCAD.Console.PrintError)
    never sees it -- "no console error" is not an assertion here.

The last two tests walk EVERY reference .FCStd: each object that declared
a proxy (module + class in Document.xml) must restore with a live proxy
of that class, and every restored blend must carry its delete watcher.
Objects whose saved Proxy is JSON `null` declare no proxy to restore --
that is a property of the FILE, recorded in the checks and reported, not
a restore-code defect (#10 family).
"""

import os
import tempfile
import zipfile
import xml.etree.ElementTree as ET

import FreeCAD

from Tests.mcp_harness import check

_HERE = os.path.dirname(os.path.abspath(__file__))
FIXTURE_DIR = os.path.join(_HERE, "..", "Resources", "Test_files")

BLEND_TYPES = ("Blend", "BlendStrip")

# The corner fixture's B12 seam joins these two patches; deleting it must
# drop the band split it owns on each (#70/#71).
_BLEND = "B12"
_PATCHES = ("Patch44", "Patch001")


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _band_edges(p):
    """((USplit1, USplit2), (VSplit1, VSplit2)) rounded -- the band splits.

    The band EDGES, not the hidden cells: the hidden set is re-derived by
    the surviving blends and is right even when the unblend never ran, so
    asserting it would let a dead blend pass (see the module docstring).
    """
    def pair(letter):
        return (round(float(getattr(p, letter + "Split1")), 12),
                round(float(getattr(p, letter + "Split2")), 12))
    return pair("U"), pair("V")


def _splits(document, patches=_PATCHES):
    return {name: _band_edges(document.getObject(name))
            for name in patches if document.getObject(name) is not None}


def _watchers(document):
    """name -> bool: does each blend's proxy carry a live delete watcher?"""
    return {o.Name: getattr(o.Proxy, "_delete_watcher", None) is not None
            for o in document.Objects
            if getattr(o, "object_type", None) in BLEND_TYPES}


def _fresh_document(name):
    for d in list(FreeCAD.listDocuments().values()):
        if d.Name == name:
            FreeCAD.closeDocument(name)
    return FreeCAD.newDocument(name)


def _fixture_files():
    """Every reference .FCStd under Resources/Test_files.

    examples/ is included; `_inspect/` is NOT -- it is gitignored scratch
    that earlier runs leave behind, not a reference fixture, and asserting
    on stale artifacts would make this oracle depend on run history.
    """
    out = []
    for base, dirs, names in os.walk(FIXTURE_DIR):
        dirs[:] = [d for d in dirs if d != "_inspect"]
        for n in sorted(names):
            if n.endswith(".FCStd"):
                out.append(os.path.join(base, n))
    return sorted(out)


def _declared_proxies(path):
    """object name -> (module, class) for every Proxy the .FCStd declares.

    Only a `<Python module="..." class="..."/>` is a proxy FreeCAD can
    rebuild. A saved Proxy that is JSON `null` (or a bare scalar) declares
    none -- there is no class to instantiate, so it is absent here; that
    is a FILE property, recorded rather than failed on.
    """
    with zipfile.ZipFile(path) as zf:
        root = ET.fromstring(zf.read("Document.xml"))
    out = {}
    for obj in root.iter("Object"):
        for prop in obj.iter("Property"):
            if prop.get("name") != "Proxy":
                continue
            py = prop.find("Python")
            if py is not None and py.get("module"):
                out[obj.get("name")] = (py.get("module"), py.get("class"))
            break
    return out


def _null_proxy_names(path):
    """Objects whose saved Proxy is JSON null -- nothing to restore."""
    with zipfile.ZipFile(path) as zf:
        root = ET.fromstring(zf.read("Document.xml"))
    out = []
    for obj in root.iter("Object"):
        for prop in obj.iter("Property"):
            if prop.get("name") != "Proxy":
                continue
            py = prop.find("Python")
            if py is not None and not py.get("module"):
                import base64
                try:
                    value = base64.b64decode(py.get("value", "")).decode()
                except Exception:
                    value = py.get("value")
                if value in ("null", ""):
                    out.append(obj.get("name"))
            break
    return out


# ---------------------------------------------------------------------------
# the oracle: fresh vs restored unblend
# ---------------------------------------------------------------------------

def test_a_restored_blend_unblends_like_a_fresh_one(doc):
    """Delete B12 twice -- once fresh, once restored -- same patch state.

    Control arm: build the corner model (__init__ runs, the watcher is
    installed), save it, then delete B12. Bug arm: reopen the saved
    document (__init__ never runs) and delete B12. The two RESULTS must be
    identical, and the fresh delete must actually change something (or the
    arms would agree by both doing nothing).
    """
    errors, checks = [], []
    from Tests import corner_model

    tmp = tempfile.mkdtemp(prefix="silk_restore_")
    path = os.path.join(tmp, "corner.FCStd")
    scratch = FreeCAD.ActiveDocument

    # ---- control arm: fresh, then save + delete -------------------------
    fresh = _fresh_document("restore_fresh")
    try:
        corner_model.build_corner_model(fresh)
        fresh.recompute()
        before_fresh = _splits(fresh)
        fresh_watchers = _watchers(fresh)
        fresh.saveAs(path)
        fresh.removeObject(_BLEND)
        fresh.recompute()
        after_fresh = _splits(fresh)
    finally:
        FreeCAD.closeDocument(fresh.Name)

    # ---- the bug arm: REOPEN the saved document, then delete ------------
    reopened = FreeCAD.openDocument(path)
    try:
        before_restored = _splits(reopened)
        restored_watchers = _watchers(reopened)
        reopened.removeObject(_BLEND)
        reopened.recompute()
        after_restored = _splits(reopened)
    finally:
        FreeCAD.closeDocument(reopened.Name)
        if scratch is not None:
            FreeCAD.setActiveDocument(scratch.Name)

    checks.append("fresh watchers: %s" % fresh_watchers)
    checks.append("restored watchers: %s" % restored_watchers)
    checks.append("before (fresh) = %s" % before_fresh)
    checks.append("after  (fresh) = %s" % after_fresh)
    checks.append("after  (restored) = %s" % after_restored)

    # precondition on the control: a fresh blend is watched
    check(all(fresh_watchers.values()),
          "a FRESH blend was created without a delete watcher: %s"
          % fresh_watchers, errors)

    # the restore-path defect, asserted directly
    dead = sorted(n for n, ok in restored_watchers.items() if not ok)
    check(not dead,
          "restored blend(s) %s have no delete watcher -- a reopened blend "
          "can never unblend (#93)" % dead, errors)

    # the two arms must agree (the bug arm is RED here today)
    check(before_fresh == before_restored,
          "the saved/reopened document is not in the same state as the "
          "fresh one: fresh=%s restored=%s"
          % (before_fresh, before_restored), errors)
    check(after_fresh != before_fresh,
          "the control delete did not unblend anything (fresh delete was a "
          "no-op) -- the oracle would pass for the wrong reason", errors)
    check(after_restored == after_fresh,
          "deleting a RESTORED blend did not unblend like deleting a fresh "
          "one: fresh delete -> %s, restored delete -> %s"
          % (after_fresh, after_restored), errors)

    return {"pass": not errors, "errors": errors, "checks": checks}


# ---------------------------------------------------------------------------
# every reference document restores its proxies
# ---------------------------------------------------------------------------

def test_every_reference_document_restores_its_declared_proxies(doc):
    """Every object that declared a proxy restores with a live one.

    An object whose .FCStd Proxy is `null` declared no proxy, so it cannot
    be asserted -- those are recorded (checks) as a found property of the
    fixtures, not failed on.
    """
    errors, checks = [], []
    files = _fixture_files()
    check(files, "no .FCStd fixtures found under %s" % FIXTURE_DIR, errors)

    total = 0
    null_notes = []
    for path in files:
        fname = os.path.relpath(path, FIXTURE_DIR)
        declared = _declared_proxies(path)
        nulls = _null_proxy_names(path)
        if nulls:
            null_notes.append("%s: %d object(s) save Proxy=null (%s)"
                              % (fname, len(nulls), ", ".join(nulls[:4])
                                 + ("..." if len(nulls) > 4 else "")))
        d = FreeCAD.openDocument(path)
        try:
            for name, (module, cls) in sorted(declared.items()):
                o = d.getObject(name)
                if o is None:
                    errors.append("%s declares a %s.%s proxy for object %r "
                                  "that is not in the reopened document"
                                  % (fname, module, cls, name))
                    continue
                total += 1
                if o.Proxy is None:
                    errors.append("%s: %s declares proxy %s.%s but restored "
                                  "Proxy is None" % (fname, name, module, cls))
                    continue
                got_cls = type(o.Proxy).__name__
                if got_cls != cls:
                    errors.append("%s: %s restored a %s proxy, declared %s.%s"
                                  % (fname, name, got_cls, module, cls))
        finally:
            FreeCAD.closeDocument(d.Name)

    checks.append("checked %d declared proxies in %d fixtures"
                  % (total, len(files)))
    for note in null_notes:
        checks.append("Proxy=null (nothing to restore): " + note)
    return {"pass": not errors, "errors": errors, "checks": checks}


def test_every_restored_blend_has_its_delete_watcher(doc):
    """Every blend in every reference .FCStd restored with a live watcher."""
    errors, checks = [], []
    seen = 0
    per_file = []
    for path in _fixture_files():
        fname = os.path.relpath(path, FIXTURE_DIR)
        d = FreeCAD.openDocument(path)
        try:
            for o in d.Objects:
                if getattr(o, "object_type", None) not in BLEND_TYPES:
                    continue
                seen += 1
                per_file.append("%s/%s" % (fname, o.Name))
                proxy = getattr(o, "Proxy", None)
                if proxy is None:
                    errors.append("%s: blend %s restored with no proxy at all"
                                  % (fname, o.Name))
                elif getattr(proxy, "_delete_watcher", None) is None:
                    errors.append("%s: restored blend %s has no delete "
                                  "watcher -- it can never unblend (#93)"
                                  % (fname, o.Name))
        finally:
            FreeCAD.closeDocument(d.Name)

    check(seen, "no restored blend objects found in any reference document",
          errors)
    checks.append("%d restored blends: %s" % (seen, ", ".join(per_file)))
    return {"pass": not errors, "errors": errors, "checks": checks}


ALL_TESTS = [
    test_a_restored_blend_unblends_like_a_fresh_one,
    test_every_reference_document_restores_its_declared_proxies,
    test_every_restored_blend_has_its_delete_watcher,
]
