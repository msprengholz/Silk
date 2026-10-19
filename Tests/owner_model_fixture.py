"""The owner's committed Demo 01 model -- ONE place that says what the file
on disk contains, plus an OFFLINE reader for it (ticket #124).

THE FIXTURE.  `Resources/Test_files/SketchOnly_Demo01Subset_withPatches
.FCStd` is the owner's own hand-built Demo 01 model, saved by the owner on
2026-10-17 12:35 (the commit that added it, `685c5a3`, says: "Saved by the
owner while driving the wizard by hand ... Stops at the corner stage: the
panel required exactly 4 ring blends and a Demo01 junction is 3-valent").
It is the ONE artifact in the repo that predates the `ShowGrid` toggle
(#95) and the `Flat Lines` view mode (#96), so the restore-path tests
(`Tests/test_blend_grid_toggle.py`) need it exactly as it is: its blends
carry NO `ShowGrid` on disk and are stored `Shaded`.

WHY THIS MODULE EXISTS (#124).  The manual tier was green on this machine
only because the WORKING TREE carried an uncommitted variant of this file
with one more CornerBlend than the committed one, and
`Tests/test_blend_grid_toggle.py` asserted "8 blends and 1 corner" -- a
number that described the dirty file, not the committed one.  That is the
#67 family again: a green result that depends on state nobody committed.

The durable fix is that the STATE and the TESTS are derived from one
documented constant, and a fast-tier guard checks the file against it:

  * `DOCUMENTED_INVENTORY` is the committed file's inventory -- read
    OFFLINE from its own `Document.xml` (the census technique, no FreeCAD
    needed) on 2026-10-18, and stated here once;
  * `Tests/test_owner_model_fixture.py` asserts the file on disk carries
    exactly that inventory, so a drifted working copy goes RED loudly
    instead of silently supplying an object a test happens to want;
  * both manual modules that open this file assert the LIVE document
    against the same constant.

The corner count is ZERO here, and that is the measured state of the
committed file -- not a preference.  The `1 corner` variant exists only as
an uncommitted working-tree artifact: the same fixture with the objects
hidden and one 3-valent corner added, saved at 2026-10-18 01:48 by a
session whose mechanism the ticket records as unconfirmed.  The commit
that added the file states the deliberate stop at the corner stage, and
the later module that documents this file (`Tests/test_corner_orientation
.py`, #112) describes it as "12 Edges / 5 Patches / 8 Blends / 0 corners".
The corner's RESTORE path is covered where it can be built on purpose:
`Tests/test_blend_grid_toggle.py`'s second test builds a corner model,
strips the toggle off it and reopens it.
"""

import os
import xml.etree.ElementTree as ET
import zipfile

from collections import Counter

_SILK_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OWNER_PATH = os.path.join(_SILK_DIR, "Resources", "Test_files",
                          "SketchOnly_Demo01Subset_withPatches.FCStd")

# The COMMITTED file's inventory, read offline from its own Document.xml
# (the census technique -- zipfile + ElementTree, no FreeCAD) and stated
# here ONCE.  Every test that touches this file compares against this.
#
#   Edge 12  -- the demo's 12 boundary edges
#   Patch 5  -- the five ring faces
#   Blend 8  -- the eight seams
#   CornerBlend 0 -- the owner stopped at the corner stage (see above)
DOCUMENTED_INVENTORY = {
    "Edge": 12,
    "Patch": 5,
    "Blend": 8,
    "CornerBlend": 0,
}

# The Part feature's DisplayMode enumeration, in the order FreeCAD writes
# it: the GuiDocument stores the INDEX, not the name.  The owner's blends
# are stored "Shaded" (index 1), which is the pre-#96 state the restore
# path migrates away from (`SilkBlend.migrate_shaded_display`).
PART_DISPLAY_MODES = ("Flat Lines", "Shaded", "Wireframe", "Points")


def display_mode_name(index):
    """The display-mode NAME of a stored index (None when out of range)."""
    if index is None:
        return None
    if 0 <= index < len(PART_DISPLAY_MODES):
        return PART_DISPLAY_MODES[index]
    return "index %d" % index


def _read(path, member):
    with zipfile.ZipFile(path) as z:
        return z.read(member).decode("utf-8", "replace")


def silk_types(path=None):
    """{object name: its Silk `object_type`} read OFFLINE from the file's
    own `Document.xml`.

    A document lists every object TWICE -- once as a stub under `<Objects>`
    (no properties at all) and once with its data under `<ObjectData>`.
    Only the occurrence that carries the `object_type` PROPERTY is read,
    so the stubs cannot be mistaken for objects (the same trap the #108
    census documents).
    """
    root = ET.fromstring(_read(path or OWNER_PATH, "Document.xml"))
    out = {}
    for obj in root.iter("Object"):
        props = dict((p.get("name"), p)
                     for p in obj.findall("Properties/Property"))
        prop = props.get("object_type")
        if prop is None:
            continue  # a stub, a sketch, or a non-Silk object
        value = prop.find("String")
        out[obj.get("name")] = (value.get("value")
                                if value is not None else None)
    return out


def inventory(path=None):
    """Counter of the Silk object types in the file (offline)."""
    return Counter(silk_types(path).values())


def names_of_type(object_type, path=None):
    """The names of every object of `object_type`, in document order."""
    return [name for name, kind in silk_types(path).items()
            if kind == object_type]


def document_inventory(document):
    """Counter of the Silk object types in an OPEN document.

    The live counterpart of `inventory()`: the manual tests open the file
    and compare the document they actually got against the same
    documented constant.
    """
    return Counter(getattr(o, "object_type", None)
                   for o in document.Objects
                   if getattr(o, "object_type", None))


def stored_show_grid(path=None):
    """{object name: True} for every object that STORES a `ShowGrid`
    property on disk.

    The pre-#95 premise of the restore test: the owner's blends must NOT
    carry the property in the file, or the restore path would have nothing
    to repair.  The five Patches DO carry it -- they have had the toggle
    since before the owner's save -- so the guard is about the BLENDS.
    """
    root = ET.fromstring(_read(path or OWNER_PATH, "Document.xml"))
    out = {}
    for obj in root.iter("Object"):
        for prop in obj.findall("Properties/Property"):
            if prop.get("name") == "ShowGrid":
                out[obj.get("name")] = True
                break
    return out


def stored_display_modes(path=None):
    """{view-provider name: stored DisplayMode index} from `GuiDocument.xml`.

    The pre-#96 premise: the owner's blends are stored "Shaded", so the
    restore path's migration to "Flat Lines" has something to migrate.
    """
    root = ET.fromstring(_read(path or OWNER_PATH, "GuiDocument.xml"))
    out = {}
    for vp in root.iter("ViewProvider"):
        for prop in vp.findall("Properties/Property"):
            if prop.get("name") != "DisplayMode":
                continue
            value = prop.find("Integer")
            if value is not None:
                out[vp.get("name")] = int(value.get("value"))
            break
    return out
