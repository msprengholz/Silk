"""The owner's committed Demo 01 model must carry the inventory the tests
assert (ticket #124).

THE DEFECT THIS PINS.  `Resources/Test_files/SketchOnly_Demo01Subset
_withPatches.FCStd` is the owner's hand-built Demo 01 model, and it is the
one artifact that predates the `ShowGrid` toggle (#95) and the `Flat Lines`
view mode (#96) -- so the restore-path test
(`Tests/test_blend_grid_toggle.py`) needs it exactly as it is.  But the
manual tier was green on one machine only because the WORKING TREE carried
an uncommitted variant of the file with one more CornerBlend than the
committed one, and the test asserted "8 blends and 1 corner": a number
that described the dirty file, not the committed one.  A dirty tree
supplied the missing object, and nothing said so.

THE CONTRACT.  The committed file's inventory is stated ONCE, in
`Tests/owner_model_fixture.DOCUMENTED_INVENTORY` (read offline from the
file's own `Document.xml`): 12 Edges, 5 Patches, 8 Blends and 0
CornerBlends.  This module asserts the file on disk carries exactly that,
so a drifted working copy goes RED loudly instead of silently feeding a
test.  The two manual modules that open the file assert the LIVE document
against the same constant, so the state and the tests cannot disagree
about what the file is.

It also pins the two PREMISES the restore test rests on, because they are
properties of the FILE and are otherwise invisible:

  * the blends store NO `ShowGrid` on disk (the property arrived in #95 --
    a blend that carried it in the file would leave the restore path
    nothing to repair), and
  * the blends are stored `Shaded` (the pre-#96 state that
    `SilkBlend.migrate_shaded_display` migrates to `Flat Lines`).

This is a FAST-tier module: it reads the file as a zip and needs no
document, no FreeCAD geometry and no rebuild -- which is exactly why it
can be the guard that does not depend on the state it guards.
"""

import os

from Tests import owner_model_fixture as OWNER
from Tests.mcp_harness import check


def _blend_premises(path=None):
    """(the blend names, the blends that store ShowGrid, the blends that
    are not stored Shaded) -- the two pre-#95 / pre-#96 premises."""
    blends = OWNER.names_of_type("Blend", path)
    with_grid = OWNER.stored_show_grid(path)
    modes = OWNER.stored_display_modes(path)
    shaded = [n for n in blends
              if OWNER.display_mode_name(modes.get(n)) == "Shaded"]
    return blends, [n for n in blends if n in with_grid], shaded


def test_owner_model_fixture_carries_its_documented_inventory(doc):
    """The file on disk carries exactly the documented inventory.

    Read OFFLINE (zipfile + ElementTree), so the guard measures the FILE
    and not whatever a document happens to hold in memory.
    """
    errors, checks = [], []
    if not os.path.exists(OWNER.OWNER_PATH):
        return {"pass": False, "checks": [],
                "errors": ["missing %s" % OWNER.OWNER_PATH]}
    got = OWNER.inventory()
    want = OWNER.DOCUMENTED_INVENTORY
    for kind in sorted(want):
        check(got.get(kind, 0) == want[kind],
              "%s carries %d %s object(s), the documented inventory says "
              "%d -- the file and the tests must agree (restore it with "
              "`git checkout -- Resources/Test_files/%s`, or regenerate it "
              "deliberately and update "
              "Tests/owner_model_fixture.DOCUMENTED_INVENTORY)"
              % (os.path.basename(OWNER.OWNER_PATH), got.get(kind, 0), kind,
                 want[kind],
                 os.path.basename(OWNER.OWNER_PATH)), errors)
    extra = sorted(k for k in got if k not in want)
    check(not extra,
          "%s carries object type(s) %s the documented inventory does not "
          "mention" % (os.path.basename(OWNER.OWNER_PATH), extra), errors)
    checks.append("inventory: %s"
                  % ", ".join("%d %s" % (got.get(k, 0), k)
                              for k in sorted(want)))
    return {"pass": not errors, "errors": errors, "checks": checks}


def test_owner_model_fixture_predates_the_grid_toggle(doc):
    """The owner's blends carry no `ShowGrid` on disk and are stored
    `Shaded` -- the two premises the restore-path test needs.

    Without them the restore test would assert nothing: a blend that
    already had the property in the file would not be repaired by the
    restore path, and a blend already stored `Flat Lines` would not be
    migrated.
    """
    errors, checks = [], []
    if not os.path.exists(OWNER.OWNER_PATH):
        return {"pass": False, "checks": [],
                "errors": ["missing %s" % OWNER.OWNER_PATH]}
    blends, with_grid, shaded = _blend_premises()
    check(len(blends) == OWNER.DOCUMENTED_INVENTORY["Blend"],
          "the file carries %d blend(s), the documented inventory says %d"
          % (len(blends), OWNER.DOCUMENTED_INVENTORY["Blend"]), errors)
    check(not with_grid,
          "these blends already store a ShowGrid property in the file: %s "
          "-- they no longer predate the toggle, so the restore path has "
          "nothing to repair and the restore test asserts nothing"
          % with_grid, errors)
    check(len(shaded) == len(blends),
          "%d of %d blends are stored Shaded (%s not stored Shaded) -- the "
          "restore path's migration to Flat Lines has nothing to migrate"
          % (len(shaded), len(blends),
             sorted(set(blends) - set(shaded))), errors)
    checks.append("%d blends: none stores ShowGrid, all stored Shaded"
                  % len(blends))
    return {"pass": not errors, "errors": errors, "checks": checks}


ALL_TESTS = [
    test_owner_model_fixture_carries_its_documented_inventory,
    test_owner_model_fixture_predates_the_grid_toggle,
]
