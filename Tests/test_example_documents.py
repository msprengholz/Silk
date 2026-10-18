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

#108 (fourth quarter): the same guard, one level DOWN.  The name guard
above cannot see a fixture that copies a sketch's geometry but drops its
construction -- and that is exactly what shipped.  `Tests/
make_demo01_fixture.py` wrapped every `dst.addConstraint(c)` in
`except Exception: pass`, so the fixture kept 347 of the demo's 393
constraints: all 46 dropped ones referenced the sketch's EXTERNAL geometry
(`Second = -4`, `-5`, ... in the file; `GeoEnum::RefExt = -3` and below),
which the generator never copied either, so `addConstraint` raised
`IndexError: Constraint has invalid indexes` and the swallow ate it.  The
geometry was copied exactly, which is why every pole-level check stayed
green.  The census below compares the fixture against the demo's own
`Document.xml`, offline (zipfile + ElementTree), the way the name guard
does: per-sketch constraint count, per-type count, and the external
geometry each sketch is attached to.

A test takes one document argument (the harness's fresh scratch doc);
the example files are opened, inspected and closed inside it.

THE 3-VALENT HARD CORNER (the owner's own case).  `SketchOnly_CornerCube
.FCStd` is the fixture for three surfaces meeting at one corner -- the
junction shape the owner's own model has everywhere. It is pinned twice
more than the others:

  * `test_cornercube_fixture_is_reproducible_from_its_generator` compares the
    committed file against `Tests/make_cornercube_fixture.py`'s declared
    placements and boundary lines, so the binary fixture cannot drift from
    the script that produces it;
  * `test_cornercube_fixture_carries_its_documented_constraints` reads the
    fixture's own `Document.xml` and pins the per-sketch constraint COUNT
    (#108: a count, not a name). The hand-made examples carry none -- the
    README says so -- and the count keeps that claim honest.
"""

import FreeCAD
import os
import re
import xml.etree.ElementTree as ET
import zipfile

from collections import Counter

from Tests.demo01_fixture_model import HALF_RIB_SUPPLEMENT, close_fresh, \
    open_fresh
# The "new fixture" generator (#56/#108 retrofit): `SketchOnly_CornerCube
# .FCStd` is the 3-valent hard-corner click-through fixture, and its
# generator declares the sketch placements and boundary lines the committed
# file must carry. Imported, not copied, so the two cannot disagree.
import Tests.make_cornercube_fixture as CORNERCUBE_GENERATOR

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


# The document writer's own constraint-type ordinals (`Sketcher::
# ConstraintType`), the codes that appear as `Type="..."` in a `Constrain`
# element.  Measured, not guessed: one of every type was built, added to a
# sketch and written to a document, and the codes read back (Demo 01 itself
# uses only the six below).  The names are for the FAILURE MESSAGE only --
# the assertion compares the raw codes.
CONSTRAINT_TYPE_NAMES = {
    "1": "Coincident",
    "2": "Horizontal",
    "3": "Vertical",
    "9": "Angle",
    "11": "Radius",
    "13": "PointOnObject",
}


def _type_names(counter):
    """A `Counter` of type codes as `"6 Coincident"`-style text."""
    return " + ".join("%d %s" % (n, CONSTRAINT_TYPE_NAMES.get(code, code))
                      for code, n in sorted(counter.items())) or "none"


# The demo's own constraint total, the census's sanity floor (#108): 393 on
# its 29 sketches, measured offline from `Document.xml` and cross-checked
# live (`sum(len(o.Constraints) for o in demo.Objects if sketch)`).  A
# census that silently read the wrong thing would otherwise compare empty to
# empty and pass.
DEMO01_CONSTRAINTS = 393


def fcstd_sketch_census(path):
    """{sketch name: {"constraints": [type code, ...],
                      "external": [(object name, sub-element), ...]}}

    Read OFFLINE from the document's own `Document.xml` (zipfile +
    ElementTree), like `demo01_sketch_names` -- no FreeCAD, and no
    dependency on what the other side of the comparison happens to
    contain.  A sketch is recognised by carrying the `Constraints`
    property, and ONLY the occurrence that carries the properties is read:
    a document lists every object twice, once as a stub under `<Objects>`
    (no properties at all) and once with its data under `<ObjectData>`.
    Reading the stubs instead would report every sketch as having zero
    constraints on BOTH sides, i.e. compare empty to empty and go green --
    which is why the demo's total is also asserted (see
    `DEMO01_CONSTRAINTS`).  The external-geometry list is flattened to one
    (object, sub-element) pair per link entry, so a multi-sub link in the
    demo and the per-sub links a re-added one is written as compare equal.
    """
    with zipfile.ZipFile(path) as z:
        xml = z.read("Document.xml").decode("utf-8", "replace")
    root = ET.fromstring(xml)
    census = {}
    for obj in root.iter("Object"):
        props = dict((p.get("name"), p)
                     for p in obj.findall("Properties/Property"))
        constr = props.get("Constraints")
        if constr is None:
            continue  # not a sketch, or the `<Objects>` stub of one
        codes = [c.get("Type")
                 for c in constr.findall("ConstraintList/Constrain")]
        ext = props.get("ExternalGeometry")
        links = []
        if ext is not None:
            for link in ext.findall("LinkSubList/Link"):
                for sub in (link.get("sub") or "").split(","):
                    links.append((link.get("obj"), sub))
        census[obj.get("name")] = {"constraints": codes, "external": links}
    return census

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
        "target": "9 sketches -> 9 Edges -> 3 Patches -> 3 Blends -> "
                  "1 CornerBlend (the 3-valent hard corner)",
        "generator": "Tests/make_cornercube_fixture.py",
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


def test_cornercube_fixture_is_reproducible_from_its_generator(doc):
    """`SketchOnly_CornerCube.FCStd` is GENERATED, not hand-saved: every one
    of its nine sketches carries exactly the placement and the three boundary
    lines `Tests/make_cornercube_fixture.py` declares for it (compared in
    WORLD space, so the quaternion's sign does not matter). A fixture edited
    in the Sketcher after generation therefore fails here instead of drifting
    away from the script that claims to produce it.

    This is the CornerCube half of the #108 contract: the Demo 01 guard one
    level up (the demo's own `Document.xml`) pins a fixture whose source is
    another document; this pins a fixture whose source is a data table.
    """
    errors, checks = [], []
    path = os.path.join(EXAMPLES_DIR, "SketchOnly_CornerCube.FCStd")
    if not os.path.exists(path):
        return {"pass": False, "errors": ["missing %s" % path],
                "checks": []}
    generator = CORNERCUBE_GENERATOR
    source, tmpdir = open_fresh(path)
    try:
        names = sorted(o.Name for o in source.Objects
                       if o.TypeId == "Sketcher::SketchObject")
        want = sorted(generator.sketch_names())
        if names != want:
            errors.append("%s carries sketches %s, the generator declares "
                          "%s" % (os.path.basename(path), names, want))
            return {"pass": False, "errors": errors, "checks": checks}
        checks.append("%d sketches == the generator's declared set"
                      % len(names))
        worst = 0.0
        for name in want:
            obj = source.getObject(name)
            place = obj.Placement
            got = [(place.multVec(g.StartPoint), place.multVec(g.EndPoint))
                   for g in obj.Geometry
                   if g.TypeId == "Part::GeomLineSegment"]
            expected = generator.declared_world_segments(name)
            if len(got) != len(expected):
                errors.append("%s: the fixture has %d boundary line(s), the "
                              "generator declares %d"
                              % (name, len(got), len(expected)))
                continue
            for (a, b), (ea, eb) in zip(got, expected):
                for p, q in ((a, ea), (b, eb)):
                    delta = (p - q).Length
                    worst = max(worst, delta)
                    if delta > 1e-6:
                        errors.append(
                            "%s: boundary point %s, the generator declares "
                            "%s (%.3e mm off)" % (name, p, q, delta))
        checks.append("placement + boundary lines match the generator "
                      "(worst %.3e mm)" % worst)
        return {"pass": not errors, "errors": errors, "checks": checks}
    finally:
        close_fresh(source, tmpdir)


def test_cornercube_fixture_carries_its_documented_constraints(doc):
    """The CornerCube fixture's sketch construction, read OFFLINE from its
    own `Document.xml` (`fcstd_sketch_census`) and compared per sketch
    against the documented count, not against a list of names (#108).

    There is nothing here to copy: unlike the Demo 01 subset, whose sketches
    are the demo's own constrained construction, the four hand-made examples
    are three free-standing line segments each and carry ZERO constraints --
    measured on all nine sketches here, not assumed. Pinning the count keeps
    the distinction honest: if a later edit adds a construction (or a
    generator silently drops one), the number changes and this fails rather
    than the README's "no constraints" promise quietly becoming false.
    """
    errors, checks = [], []
    path = os.path.join(EXAMPLES_DIR, "SketchOnly_CornerCube.FCStd")
    if not os.path.exists(path):
        return {"pass": False, "errors": ["missing %s" % path],
                "checks": []}
    census = fcstd_sketch_census(path)
    per = CORNERCUBE_GENERATOR.EXPECTED_CONSTRAINTS_PER_SKETCH
    total = 0
    for name in CORNERCUBE_GENERATOR.sketch_names():
        got = len(census.get(name, {}).get("constraints", []))
        total += got
        if got != per:
            errors.append("%s: fixture carries %d constraints, the "
                          "generator documents %d (the hand-made examples "
                          "carry none)" % (name, got, per))
    checks.append("%d sketches, %d constraints total (documented %d each)"
                  % (len(CORNERCUBE_GENERATOR.sketch_names()), total, per))
    return {"pass": not errors, "errors": errors, "checks": checks}


def test_example_demo01_subset(doc):
    errors, checks = [], []
    _assert_example_sketch_only(errors, checks, "SketchOnly_Demo01Subset.FCStd")
    checks.append("target: "
                  + EXPECTED["SketchOnly_Demo01Subset.FCStd"]["target"])
    return {"pass": not errors, "errors": errors, "checks": checks}


def test_demo01_subset_carries_the_demos_constraints(doc):
    """#108: every demo sketch in the fixture carries the demo's OWN
    constraints -- per-sketch count, per-type count, and the external
    geometry it is attached to, all derived from the demo file at test time
    (`fcstd_sketch_census(DEMO01)`, the name guard's technique).

    What a human sees differently when this is red: the fixture sketches are
    drawn in the right PLACE but are no longer the same CONSTRUCTION.  Their
    geometry is copied vertex-for-vertex, so every rebuilt Edge/Patch is
    still pole-identical and every pole-level check stays green -- but the
    Sketcher now lists no external geometry for them, and the constraints
    that pinned a sketch's points onto the neighbouring sketch's edges are
    gone, so dragging the sketch slides it off the edge it was drawn on.
    That is how the fixture shipped with 347 of the demo's 393 constraints
    (`Sketch015`: 3 of 6, `Sketch032`: 4 of 7) and nothing noticed.
    """
    errors, checks = [], []
    path = os.path.join(EXAMPLES_DIR, "SketchOnly_Demo01Subset.FCStd")
    if not os.path.exists(path):
        return {"pass": False, "errors": ["missing %s" % path],
                "checks": []}
    demo = fcstd_sketch_census(DEMO01)
    fixture = fcstd_sketch_census(path)
    demo_names = demo01_sketch_names()
    demo_total = sum(len(demo[n]["constraints"]) for n in demo_names)
    if demo_total != DEMO01_CONSTRAINTS:
        return {"pass": False, "checks": [],
                "errors": ["the census of %s reads %d constraints, expected "
                           "%d -- the census itself is wrong, so nothing "
                           "below would mean anything"
                           % (DEMO01, demo_total, DEMO01_CONSTRAINTS)]}
    kept_total = sum(len(fixture.get(n, {}).get("constraints", []))
                     for n in demo_names)
    lost_total = 0
    for name in demo_names:
        want = Counter(demo[name]["constraints"])
        got = Counter(fixture.get(name, {}).get("constraints", []))
        if want != got:
            lost = want - got
            lost_total += sum(lost.values())
            errors.append(
                "%s: fixture has %d constraints (%s), the demo has %d (%s) "
                "-- missing %d: %s"
                % (name, sum(got.values()), _type_names(got),
                   sum(want.values()), _type_names(want),
                   sum(lost.values()), _type_names(lost)))
        want_ext = demo[name]["external"]
        got_ext = fixture.get(name, {}).get("external", [])
        if want_ext != got_ext:
            errors.append(
                "%s: fixture external geometry %s, the demo's is %s"
                % (name, got_ext, want_ext))
    # A fixture sketch with no construction at all is the defect itself, in
    # whatever sketch it turns up -- the demo's own sketches all carry
    # constraints, and so do the four half-rib supplements (2 each).
    empty = sorted(n for n, v in fixture.items() if not v["constraints"])
    if empty:
        errors.append("fixture sketches with no constraints at all: %s"
                      % empty)
    checks.append("demo: %d constraints on %d sketches; fixture: %d of them "
                  "kept (%d missing) across %d sketches"
                  % (demo_total, len(demo_names), kept_total, lost_total,
                     len(fixture)))
    return {"pass": not errors, "errors": errors, "checks": checks}


def test_demo01_subset_sketch_lines_are_wired_not_loose(doc):
    """The owner's visible symptom, named (#108): `Sketch015` is three lines
    that form a polyline AND are pinned to the neighbouring sketch's edge.

    The demo's `Sketch015` stores 6 `Coincident` constraints -- the joints
    between its three lines, the pin of its first point to the X axis, and
    the three points that hold its ends on the hoop edge drawn in
    `Sketch014` -- plus one external-geometry link to `Sketch014`'s three
    edges.  The shipped fixture kept 3 of the 6 and NO external geometry:
    a human opening it in the Sketcher saw the three lines joined to each
    other but floating free, with no external edge listed, and dragging
    them slid the whole polyline off the edge instead of holding it on it.
    The four node-pair sketches (`Sketch032` and its three siblings) lost
    `PointOnObject` as well -- the attachment of a line's end onto the
    neighbouring sketch's edge -- so their 2N edge had no drawn connection
    either.
    """
    errors, checks = [], []
    path = os.path.join(EXAMPLES_DIR, "SketchOnly_Demo01Subset.FCStd")
    if not os.path.exists(path):
        return {"pass": False, "errors": ["missing %s" % path],
                "checks": []}
    fixture = fcstd_sketch_census(path)
    # (sketch, the constraint counts the symptom is made of: the joints
    # between its lines, and the attachments onto the neighbour's edge)
    for name, want in (("Sketch015", (("1", 6),)),
                       ("Sketch016", (("1", 6),)),
                       ("Sketch020", (("1", 6),)),
                       ("Sketch031", (("1", 9),)),
                       ("Sketch032", (("1", 4), ("13", 1)))):
        got = Counter(fixture.get(name, {}).get("constraints", []))
        checks.append("%s: %s" % (name, _type_names(got)))
        for code, n in want:
            if got[code] != n:
                errors.append(
                    "%s: fixture has %d %s, expected %d (full: %s)"
                    % (name, got[code], CONSTRAINT_TYPE_NAMES.get(code, code),
                       n, _type_names(got)))
    for name, target, subs in (("Sketch015", "Sketch014",
                                ("Edge12", "Edge11", "Edge10")),
                               ("Sketch032", "Sketch030", ("Edge3",)),
                               ("Sketch032", "Sketch031", ("Edge2",))):
        want = [(target, s) for s in subs]
        got = [pair for pair in fixture.get(name, {}).get("external", [])
               if pair[0] == target]
        checks.append("%s <- %s %s" % (name, target, subs))
        if got != want:
            errors.append("%s: external geometry on %s is %s, expected %s"
                          % (name, target, got, want))
    return {"pass": not errors, "errors": errors, "checks": checks}

ALL_TESTS = [
    test_examples_dir_has_readme_and_docs,
    test_every_example_is_sketch_only,
    test_example_quad,
    test_example_two_patches,
    test_example_corner4,
    test_example_cornercube,
    test_cornercube_fixture_is_reproducible_from_its_generator,
    test_cornercube_fixture_carries_its_documented_constraints,
    test_example_demo01_subset,
    test_demo01_subset_carries_the_demos_constraints,
    test_demo01_subset_sketch_lines_are_wired_not_loose,
]
