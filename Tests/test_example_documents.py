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

A test takes one document argument (the harness's fresh scratch doc);
the example files are opened, inspected and closed inside it.
"""

import FreeCAD
import os

# Thread-safety is irrelevant: RPC runs on the GUI thread. The examples
# directory is on the well-known path shared by every launcher.
EXAMPLES_DIR = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..",
    "Resources", "Test_files", "examples")

SILK_OBJECT_TYPES = ("Edge", "Patch", "Blend")

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
}


def _inspect(fname):
    """Open an example and return (sketch_names, silk_object_names, others)
    without leaving the document open."""
    path = os.path.join(EXAMPLES_DIR, fname)
    if not os.path.exists(path):
        return None
    doc = FreeCAD.openDocument(path)
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
        FreeCAD.closeDocument(doc.Name)


def _assert_example_sketch_only(errors, checks, fname):
    info = _inspect(fname)
    if info is None:
        errors.append("missing example file %r under examples/" % fname)
        return
    sketches, silk, others = info
    checks.append("%s: %d sketches, %d silk objects"
                  % (fname, len(sketches), len(silk)))
    expected = EXPECTED[fname]["sketches"]
    if silk:
        errors.append("%s must open with ZERO Silk objects, found %s"
                      % (fname, silk))
    if others:
        errors.append("%s contains non-sketch objects %s"
                      % (fname, others))
    for name in expected:
        if name not in sketches:
            errors.append("%s missing documented sketch %r (have %s)"
                          % (fname, name, sketches))
    if len(sketches) != len(expected):
        errors.append("%s expected %d sketches, found %d"
                      % (fname, len(expected), len(sketches)))


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


ALL_TESTS = [
    test_examples_dir_has_readme_and_docs,
    test_every_example_is_sketch_only,
    test_example_quad,
    test_example_two_patches,
    test_example_corner4,
    test_example_cornercube,
]
