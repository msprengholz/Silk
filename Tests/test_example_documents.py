"""
Example documents (ticket #56): the durable sketch-only click-through
fixtures under Resources/Test_files/examples/.

Each example document contains ONLY the input ControlPoly4 boundary
sketches -- zero Edge / Patch / Blend objects. A human (or an agent)
opens one and clicks through the three commands (Edge -> Patch -> Blend)
to reproduce the documented target in the examples/ README.

These tests assert the fixture invariant the whole point relies on:
"opens with zero Silk objects" and "contains the documented sketch set",
so a broken or accidentally-populated example fails here rather than
corrupting a human-test round.

#98 review: `SketchOnly_Demo01Subset.FCStd` shipped with 91 sketches
(Demo 01's 29 plus 62 from Demos 02/03) while the guard stayed green,
because its expectation was the hand-written list of what had been
saved. The Demo 01 subset expectation is therefore DERIVED at test time
from the demo file itself -- `Resources/Demo_files/Silk_Demo_01.FCStd`
is unzipped and its `Document.xml` parsed for the stored Sketch object
names (zipfile + regex, the census technique, no FreeCAD needed). A
fixture carrying other demos' or stale sketches cannot ship green again:
the guard compares against the demo's own set, both directions.

#98 (second half): the fixture also carries a DOCUMENTED SUPPLEMENT --
four half-rib sketches (`Tests/demo01_fixture_model.HALF_RIB_SUPPLEMENT`)
that the demo does not have and the click-through needs, because the
demo stores one symmetric half of the shape and a Silk Edge consumes
whole sketches only. So the Demo 01 guard asserts BOTH directions
against `demo sketches | supplement`: every demo sketch present, every
sketch in the fixture either a demo sketch or a named supplement.

A test takes one document argument (the harness's fresh scratch doc);
the example files are opened, inspected and closed inside it.
"""

import FreeCAD
import os
import re
import zipfile

from Tests.demo01_fixture_model import HALF_RIB_SUPPLEMENT, close_fresh, \
    open_fresh

# Thread-safety is irrelevant: RPC runs on the GUI thread. The examples
# directory is on the well-known path shared by every launcher.
EXAMPLES_DIR = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..",
    "Resources", "Test_files", "examples")

# The source demo the subset fixture must mirror exactly (#98).
DEMO01 = os.path.normpath(os.path.join(
    EXAMPLES_DIR, "..", "..", "Demo_files", "Silk_Demo_01.FCStd"))

SILK_OBJECT_TYPES = ("Edge", "Patch", "Blend")


def demo01_sketch_names():
    """The Demo 01 sketch set, read OFFLINE from the demo's own
    `Document.xml` (zipfile + regex -- the census technique, no FreeCAD,
    no dependency on what the fixture happens to contain).

    This is the expectation the subset guard compares against; deriving
    it from the demo is what makes a wrong fixture (the 91-sketch first
    attempt) impossible to ship green.
    """
    with zipfile.ZipFile(DEMO01) as z:
        xml = z.read("Document.xml").decode("utf-8", "replace")
    names = re.findall(r'<Object name="(Sketch\d+)"', xml)
    if not names:
        raise RuntimeError("no Sketch objects found in %s" % DEMO01)
    return sorted(names, key=lambda s: int(s[6:]))

# Documented build targets -- kept in lock-step with the examples/ README.
EXPECTED = {
    "SketchOnly_Quad.FCStd": {
        "sketches": [
            "SK_Edge_Bottom", "SK_Edge_Right", "SK_Edge_Top", "SK_Edge_Left"],
        "target": "4 sketches -> 4 Edges -> 1 Patch (closed quad)",
    },
    "SketchOnly_TwoPatches.FCStd": {
        "sketches": [
            "SK_Edge_Shared", "SK_Edge_A_Bottom", "SK_Edge_A_Left",
            "SK_Edge_A_Top", "SK_Edge_B_Bottom", "SK_Edge_B_Right",
            "SK_Edge_B_Top"],
        "target": "7 sketches -> 7 Edges -> 2 Patches -> 1 Blend (seam)",
    },
    "SketchOnly_Corner4.FCStd": {
        "sketches": [
            "SK_Seam_B", "SK_Seam_R", "SK_Seam_T", "SK_Seam_L",
            "SK_QBR_A", "SK_QBR_B", "SK_QTR_A", "SK_QTR_B",
            "SK_QTL_A", "SK_QTL_B", "SK_QBL_A", "SK_QBL_B"],
        "target": "12 sketches -> 12 Edges -> 4 quadrant Patches, "
                  "4 blendable interior seams (B/R/T/L)",
    },
    "SketchOnly_CornerCube.FCStd": {
        "sketches": [
            "SK_Seam_X", "SK_Seam_Y", "SK_Seam_Z",
            "SK_F1_OuterA", "SK_F1_OuterB", "SK_F2_OuterA", "SK_F2_OuterB",
            "SK_F3_OuterA", "SK_F3_OuterB"],
        "target": "9 sketches -> 9 Edges -> 3 corner Patches, "
                  "3 blendable seams (X/Y/Z)",
    },
    "SketchOnly_Demo01Subset.FCStd": {
        # #98 review: NOT hand-written -- derived from the demo itself at
        # test time (`demo01_sketch_names()`), so the guard cannot go
        # green while the fixture carries the wrong sketch set.
        "sketches": None,
        "expected_from_demo": "Silk_Demo_01.FCStd",
        "supplement": HALF_RIB_SUPPLEMENT,
        "target": "Demo 01 sketch-only subset (the demo's own 29 "
                  "sketches, Sketch014..Sketch045, plus the 4 documented "
                  "half-rib supplements) -> 12 Edges, 5 Patches, 8 Blends, "
                  "4 CornerBlends",
    },

}

def _inspect(fname):
    """Open an example and return (sketch_names, silk_object_names, others)
    without leaving the document open.

    The file is opened from a PRIVATE COPY (`Tests.demo01_fixture_model.
    open_fresh`): `FreeCAD.openDocument` hands back an already-open document
    whose path matches (measured: opening a file that had been rewritten on
    disk returned the stale in-memory document), so a fixture regenerated
    while an older copy is open would be validated in its stale form.
    """
    path = os.path.join(EXAMPLES_DIR, fname)
    if not os.path.exists(path):
        return None
    doc, tmpdir = open_fresh(path)
    try:
        sketches = [o.Name for o in doc.Objects
                    if o.TypeId == "Sketcher::SketchObject"]
        silk = [o.Name for o in doc.Objects
                if getattr(o, "object_type", None) in SILK_OBJECT_TYPES]
        others = [o.Name for o in doc.Objects
                  if o.TypeId != "Sketcher::SketchObject"
                  and getattr(o, "object_type", None) not in SILK_OBJECT_TYPES]
        return sketches, silk, others
    finally:
        close_fresh(doc, tmpdir)


def _expected_sketches(fname, errors, checks):
    """(documented sketches, documented supplement) for `fname`; for the
    Demo 01 subset the sketch set is DERIVED from the demo file (see
    `demo01_sketch_names`), never from what the fixture happens to contain,
    and the supplement is the named `HALF_RIB_SUPPLEMENT`."""
    entry = EXPECTED[fname]
    supplement = tuple(entry.get("supplement", ()))
    if entry.get("expected_from_demo"):
        try:
            names = demo01_sketch_names()
        except Exception as exc:
            errors.append("%s: cannot derive the expected sketch set from "
                          "the demo (%s): %r"
                          % (fname, entry["expected_from_demo"], exc))
            return None, supplement
        checks.append("%s: expectation derived from %s (%d sketches) + "
                      "%d documented supplement sketch(es)"
                      % (fname, entry["expected_from_demo"], len(names),
                         len(supplement)))
        return names, supplement
    return entry["sketches"], supplement


def _assert_example_sketch_only(errors, checks, fname):
    info = _inspect(fname)
    if info is None:
        errors.append("missing example file %r under examples/" % fname)
        return
    sketches, silk, others = info
    checks.append("%s: %d sketches, %d silk objects"
                  % (fname, len(sketches), len(silk)))
    expected, supplement = _expected_sketches(fname, errors, checks)
    if silk:
        errors.append("%s must open with ZERO Silk objects, found %s"
                      % (fname, silk))
    if others:
        errors.append("%s contains non-sketch objects %s"
                      % (fname, others))
    if expected is None:
        return
    documented = list(expected) + [s for s in supplement
                                   if s not in expected]
    missing = [name for name in documented if name not in sketches]
    extra = [name for name in sketches if name not in documented]
    if missing:
        errors.append("%s missing documented sketch(es) %s (have %s)"
                      % (fname, missing, sketches))
    if extra:
        errors.append("%s carries sketches that are neither in the demo's "
                      "set nor in the documented supplement %s: %s"
                      % (fname, list(supplement), extra))
    if len(sketches) != len(documented):
        errors.append("%s expected %d sketches (%d demo + %d supplement), "
                      "found %d" % (fname, len(documented), len(expected),
                                    len(documented) - len(expected),
                                    len(sketches)))


def test_examples_dir_has_readme_and_docs(doc):
    errors, checks = [], []
    if not os.path.isdir(EXAMPLES_DIR):
        errors.append("examples/ directory does not exist: %s" % EXAMPLES_DIR)
    else:
        checks.append("examples/ present")
    if not os.path.isfile(os.path.join(EXAMPLES_DIR, "README.md")):
        errors.append("examples/README.md is required")
    else:
        checks.append("examples/README.md present")
    fcd = [f for f in os.listdir(EXAMPLES_DIR) if f.endswith(".FCStd")]
    if len(fcd) < 3:
        errors.append("need at least 3 example docs, found %d (%s)"
                      % (len(fcd), fcd))
    else:
        checks.append("%d example docs" % len(fcd))
    return {"pass": not errors, "errors": errors, "checks": checks}


def test_every_example_is_sketch_only(doc):
    errors, checks = [], []
    if not os.path.isdir(EXAMPLES_DIR):
        return {"pass": False,
                "errors": ["examples/ directory missing"], "checks": []}
    for fname in sorted(os.listdir(EXAMPLES_DIR)):
        if fname.endswith(".FCStd"):
            _assert_example_sketch_only(errors, checks, fname)
    return {"pass": not errors, "errors": errors, "checks": checks}


def test_example_quad(doc):
    errors, checks = [], []
    _assert_example_sketch_only(errors, checks, "SketchOnly_Quad.FCStd")
    checks.append("target: " + EXPECTED["SketchOnly_Quad.FCStd"]["target"])
    return {"pass": not errors, "errors": errors, "checks": checks}


def test_example_two_patches(doc):
    errors, checks = [], []
    _assert_example_sketch_only(errors, checks, "SketchOnly_TwoPatches.FCStd")
    checks.append("target: "
                  + EXPECTED["SketchOnly_TwoPatches.FCStd"]["target"])
    return {"pass": not errors, "errors": errors, "checks": checks}


def test_example_corner4(doc):
    errors, checks = [], []
    _assert_example_sketch_only(errors, checks, "SketchOnly_Corner4.FCStd")
    checks.append("target: " + EXPECTED["SketchOnly_Corner4.FCStd"]["target"])
    return {"pass": not errors, "errors": errors, "checks": checks}


def test_example_cornercube(doc):
    errors, checks = [], []
    _assert_example_sketch_only(errors, checks, "SketchOnly_CornerCube.FCStd")
    checks.append("target: "
                  + EXPECTED["SketchOnly_CornerCube.FCStd"]["target"])
    return {"pass": not errors, "errors": errors, "checks": checks}



def test_example_demo01_subset(doc):
    errors, checks = [], []
    _assert_example_sketch_only(errors, checks, "SketchOnly_Demo01Subset.FCStd")
    checks.append("target: "
                  + EXPECTED["SketchOnly_Demo01Subset.FCStd"]["target"])
    return {"pass": not errors, "errors": errors, "checks": checks}

ALL_TESTS = [
    test_examples_dir_has_readme_and_docs,
    test_every_example_is_sketch_only,
    test_example_quad,
    test_example_two_patches,
    test_example_corner4,
    test_example_cornercube,
    test_example_demo01_subset,
]
