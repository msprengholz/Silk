"""
The Blend / CornerBlend control-grid toggle (#95, part A).

Both view providers READ `ShowGrid` through
`bool(getattr(obj, "ShowGrid", True))` (`SilkBlend.py`, `SilkCorner.py`)
but neither ever added the property, so the fallback always won and the
grid could never be hidden -- the owner's "feature parity" report: with
every patch's ShowGrid off, the blends' grids are still drawn and there is
no option to hide them.

The trap this file exists for is the RESTORED document. `__init__` does
not run on restore, so adding the property there alone leaves every Blend
in an already-built document -- the owner's own committed model, 8 blends
-- with no toggle at all. `SilkBlend.ensure_grid_toggle` is the
`ensure_hidden_idxs_property` pattern applied to it: the restore path
GIVES the property to the object, and the first test asserts that on the
owner's own committed model, opened from disk.

#124: the owner's model carries 8 blends and NO corner -- that is the
COMMITTED file's inventory (`Tests/owner_model_fixture.py`
`DOCUMENTED_INVENTORY`, read offline from the file's own Document.xml),
and the owner stopped at the corner stage on purpose (the commit that
added the file says so: the panel required 4 ring blends and a Demo01
junction is 3-valent).  The corner's restore path is covered where it
can be built ON PURPOSE: the second test in this module builds a corner
model, strips the toggle off it and reopens it.  What this module must
not do is assert a corner count that only a DIRTY working tree could
supply -- that is the #67 family again, and it is why the inventory is
stated once and checked by `Tests/test_owner_model_fixture.py`.

The same class of trap, second instance: that model's blends are
`DisplayMode = "Shaded"`, which is why its strip edges cannot be selected
even though #96 shipped Flat Lines for NEW blends -- a Shaded Part face
puts no edge in the pick buffer at all (docs/research/silk-fill-picking.md).
For these two types that is a functional defect, not a preference, so
restore migrates `Shaded` -> `Flat Lines`, narrowly: only Blend /
CornerBlend, only away from Shaded.

No continuity label is asserted anywhere in this module.
"""

# --- manual tier ------------------------------------------------------
# This module's subject is an end-to-end rebuild / GUI drive /
# measurement sweep, so it is NOT in the default (fast) tier. Run it
# with `python3 Tests/run_all.py --manual` (or by name as a filter);
# Tests/test_manual_tier.py asserts it stays importable. See suite.py.
MANUAL = True

import os
import shutil
import tempfile

import FreeCAD

import Tests.demo01_fixture_model as MODEL
# The owner's model: the path, the DOCUMENTED inventory and the readers
# (#124). Imported, not copied, so the state and the tests cannot
# disagree about what the file on disk contains.
import Tests.owner_model_fixture as OWNER
from Tests.mcp_harness import check
# The Coin-node readers live with the #108 tests; imported, not copied, so
# "the toggle hides the node" means the same thing in both places.
from Tests.test_display_grid import _grid_node, _which_child, \
    _grid_point_count

OWNER_PATH = OWNER.OWNER_PATH

GRID_TYPES = ("Blend", "BlendStrip", "CornerBlend")
CORNERS = ("B12", "B24", "B43", "B31")


def _grid_objects(document):
    """Every object that draws a control grid as a Coin node (#95)."""
    return [o for o in document.Objects
            if getattr(o, "object_type", None) in GRID_TYPES]


def _shape_census(obj):
    """(faces, edges) of the object's Shape -- the thing ShowGrid must
    never touch (#108: Shape is geometry only)."""
    shape = getattr(obj, "Shape", None)
    if shape is None or shape.isNull():
        return (0, 0)
    return (len(shape.Faces), len(shape.Edges))


def _toggle_and_read(document, objects, value):
    """Set ShowGrid on every object, recompute, and return
    {name: (whichChild, (faces, edges))}."""
    for o in objects:
        o.ShowGrid = value
    document.recompute()
    return {o.Name: (_which_child(o), _shape_census(o)) for o in objects}


def test_owner_model_restores_with_a_working_grid_toggle(doc):
    """The owner's own committed model (`SketchOnly_Demo01Subset_withPatches
    .FCStd`, 8 Blends) was built BEFORE the property existed, so its
    objects have no `ShowGrid` on disk. Opened from disk they must each
    carry it, the toggle must actually hide the Coin grid node, and the
    restored view mode must be Flat Lines rather than the unpickable
    Shaded.

    The inventory the model is asserted to carry is the DOCUMENTED one
    (#124): 8 blends and 0 corners, read from
    `Tests/owner_model_fixture.DOCUMENTED_INVENTORY`.  A corner count
    that only a dirty working tree could supply is exactly the defect
    this ticket is about, so it is not asserted here."""
    errors, checks = [], []
    source, tmpdir = MODEL.open_fresh(OWNER_PATH)
    try:
        objs = _grid_objects(source)
        blends = [o for o in objs if o.object_type in ("Blend", "BlendStrip")]
        corners = [o for o in objs if o.object_type == "CornerBlend"]
        want_blends = OWNER.DOCUMENTED_INVENTORY["Blend"]
        want_corners = OWNER.DOCUMENTED_INVENTORY["CornerBlend"]
        check(len(blends) == want_blends and len(corners) == want_corners,
              "the owner's model carries %d blends and %d corners, want the "
              "%d + %d it was saved with (the documented inventory, "
              "Tests/owner_model_fixture.DOCUMENTED_INVENTORY) -- the "
              "restore arms below assert nothing otherwise"
              % (len(blends), len(corners), want_blends, want_corners),
              errors)

        missing = [o.Name for o in objs if not hasattr(o, "ShowGrid")]
        check(not missing,
              "restored objects still have no ShowGrid property: %s -- the "
              "toggle can never work on them" % missing, errors)
        shaded = [o.Name for o in objs
                  if getattr(o.ViewObject, "DisplayMode", None) != "Flat Lines"]
        check(not shaded,
              "restored objects are still not Flat Lines: %s -- a Shaded "
              "face has no pickable edge" % shaded, errors)
        checks.append("restored %d blends + %d corner: all carry ShowGrid=%s, "
                      "all Flat Lines"
                      % (len(blends), len(corners),
                         sorted({bool(o.ShowGrid) for o in objs})))

        source.recompute()
        for o in objs:
            node = _grid_node(o)
            legs = len(getattr(o, "Legs", None) or [])
            check(node is not None,
                  "%s draws no Coin grid node at all" % o.Name, errors)
            if node is None:
                continue
            check(_grid_point_count(node) == 2 * legs,
                  "%s grid node draws %d coordinates, want 2 x %d legs"
                  % (o.Name, _grid_point_count(node), legs), errors)
            check(_which_child(o) == 0,
                  "%s ShowGrid=True: node whichChild=%r, want 0"
                  % (o.Name, _which_child(o)), errors)
        checks.append("every restored object draws its grid (2 x Legs "
                      "coordinates) and shows it")

        before = {o.Name: _shape_census(o) for o in objs}
        off = _toggle_and_read(source, objs, False)
        for name, (child, census) in sorted(off.items()):
            check(child == -1,
                  "%s ShowGrid=False: node whichChild=%r, want -1 (hidden) "
                  "-- this is the owner's 'I still can't' case"
                  % (name, child), errors)
            check(census == before[name],
                  "%s ShowGrid=False changed Shape %r -> %r (the grid is a "
                  "display node, not geometry)" % (name, before[name], census),
                  errors)
        checks.append("ShowGrid=False on all %d: every node hidden "
                      "(whichChild=-1), no Shape changed" % len(objs))

        on = _toggle_and_read(source, objs, True)
        for name, (child, _census) in sorted(on.items()):
            check(child == 0,
                  "%s ShowGrid=True again: node whichChild=%r, want 0"
                  % (name, child), errors)
        checks.append("ShowGrid=True again: every node shown")
    finally:
        MODEL.close_fresh(source, tmpdir)
    return {"pass": not errors, "errors": errors, "checks": checks}


def test_an_object_saved_before_the_toggle_gains_it_on_restore(doc):
    """The same restore contract, driven explicitly: build a corner model
    (4 ring strips + 1 CornerBlend), STRIP the toggle off every blend and
    corner and put them back to Shaded -- byte-for-byte the state the
    owner's file is in -- save, reopen, and assert the property, the
    migrated view mode and a working toggle. Without the restore-path
    ensure, the reopened objects have no ShowGrid at all."""
    errors, checks = [], []
    from Tests import corner_model
    from SilkWorkflowOps import create_corner_blend

    scratch = FreeCAD.ActiveDocument
    tmpdir = tempfile.mkdtemp(prefix="silk_gridtoggle_")
    path = os.path.join(tmpdir, "pre_toggle.FCStd")
    fresh = FreeCAD.newDocument("grid_toggle_pre")
    try:
        corner_model.build_corner_model(fresh)
        corner = create_corner_blend(
            *[fresh.getObject(n) for n in CORNERS])
        fresh.recompute()
        if corner is None:
            return {"pass": False, "checks": checks,
                    "errors": ["fixture: the corner blend did not build"]}
        stripped = []
        for o in _grid_objects(fresh):
            o.removeProperty("ShowGrid")          # as saved before #95
            o.ViewObject.DisplayMode = "Shaded"   # as saved before #96
            stripped.append(o.Name)
        fresh.recompute()
        check(len(stripped) == 5,
              "stripped %d objects, want the 4 strips + 1 corner"
              % len(stripped), errors)
        fresh.saveAs(path)
    finally:
        FreeCAD.closeDocument(fresh.Name)

    reopened = FreeCAD.openDocument(path)
    try:
        objs = _grid_objects(reopened)
        check(len(objs) == 5,
              "reopened document carries %d grid objects, want 5"
              % len(objs), errors)
        missing = [o.Name for o in objs if not hasattr(o, "ShowGrid")]
        check(not missing,
              "a blend/corner restored from a pre-#95 file has no ShowGrid: "
              "%s" % missing, errors)
        shaded = [o.Name for o in objs
                  if getattr(o.ViewObject, "DisplayMode", None) != "Flat Lines"]
        check(not shaded,
              "a blend/corner restored from a pre-#96 file is still Shaded: "
              "%s" % shaded, errors)
        checks.append("reopened: %s -> ShowGrid present, Flat Lines"
                      % [o.Name for o in objs])

        reopened.recompute()
        for o in objs:
            check(_grid_node(o) is not None,
                  "%s: no Coin grid node after restore" % o.Name, errors)
        off = _toggle_and_read(reopened, objs, False)
        for name, (child, _census) in sorted(off.items()):
            check(child == -1,
                  "%s: the restored toggle does not hide the node "
                  "(whichChild=%r)" % (name, child), errors)
        on = _toggle_and_read(reopened, objs, True)
        for name, (child, _census) in sorted(on.items()):
            check(child == 0,
                  "%s: the restored toggle does not show the node again "
                  "(whichChild=%r)" % (name, child), errors)
        checks.append("the restored toggle hides and shows every node "
                      "(%d objects)" % len(objs))
    finally:
        FreeCAD.closeDocument(reopened.Name)
        shutil.rmtree(tmpdir, ignore_errors=True)
        if scratch is not None:
            FreeCAD.setActiveDocument(scratch.Name)
    return {"pass": not errors, "errors": errors, "checks": checks}


ALL_TESTS = [
    test_owner_model_restores_with_a_working_grid_toggle,
    test_an_object_saved_before_the_toggle_gains_it_on_restore,
]
