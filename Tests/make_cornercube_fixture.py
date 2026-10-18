"""Regenerate `Resources/Test_files/examples/SketchOnly_CornerCube.FCStd`
(ticket #56): the sketch-only click-through fixture for the **3-valent hard
corner** -- the owner's own case, three surfaces meeting at a cube-like
corner.

The fixture is nine ordinary 3-line ControlPoly4 boundary sketches, no Edge /
Patch / Blend / CornerBlend objects. Clicking
Edge -> Patch -> Blend -> Corner Blend on it reproduces the README's target:

    9 sketches -> 9 Edges -> 3 Patches -> 3 Blends -> 1 CornerBlend

The nine sketches are HARD-CODED here (each sketch's placement plus the three
line endpoints in its local coordinates) because the fixture was drawn by hand
in the Sketcher and the `.FCStd` is a binary: without this table the geometry
lives nowhere a human or an agent can read it. `Tests/
test_example_documents.test_cornercube_fixture_is_reproducible_from_its_generator`
compares the committed file against this table, so the two cannot drift.

CONSTRAINTS, AND THE #108 LESSON.  #108 was a fixture **generator** that
wrapped every `addConstraint` in `except Exception: pass`, so 46 constraints
referencing external geometry were silently dropped and the fixture shipped
with 347 of the demo's 393.  The demo-copying generator (`Tests/
make_demo01_fixture.py`) is where that could bite, and it now refuses to
swallow.  THIS fixture has nothing to copy: the four hand-made examples
(`Quad`, `TwoPatches`, `Corner4`, `CornerCube`) carry **zero** constraints on
every sketch -- measured from their own `Document.xml`, not assumed -- because
each boundary is three free-standing line segments, not a constrained
construction.  So there is nothing here for a swallow to eat; what this module
does instead is ASSERT the documented count (0 per sketch, 0 in total) after
building, so a later edit that adds or loses constraints without saying so
fails loudly rather than being written out.

This script LIVES IN Tests/ for the reason the demo generator does: it is not
a workbench module, and `Tests/test_module_generation.py` pins the top-level
Mod `.py` file count at 57.

Run (no GUI needed -- it only creates sketches, it never touches the maths):

    freecadcmd Tests/make_cornercube_fixture.py

`main()` reopens the written fixture and prints the object counts and a
SHA-256 of every sketch's geometry, so two runs can be compared
content-for-content (the .FCStd container is a zip; its bytes are not
guaranteed stable).
"""

import hashlib
import os
import sys

import FreeCAD
import Part

HERE = os.path.dirname(os.path.abspath(__file__))
SILK_DIR = os.path.dirname(HERE)
OUT_PATH = os.path.join(SILK_DIR, "Resources", "Test_files", "examples",
                        "SketchOnly_CornerCube.FCStd")
FIXTURE_NAME = "SketchOnly_CornerCube"

# The fixture carries no sketch constraints, and must not grow any silently
# (#108's lesson applied to the fixture that HAS no construction to copy).
EXPECTED_CONSTRAINTS_PER_SKETCH = 0

# name -> (placement base, placement rotation as a quaternion, the three
#         boundary lines' endpoints in sketch-local coordinates)
#
# The three seam sketches are the SAME local polyline; only their placement
# differs, which is why they share one entry via SEAM_LINES below.  The six
# outer sketches are the panels' far boundaries.
SEAM_LINES = (
    ((0.0, 0.0, 0.0), (23.0, 12.0, 0.0)),
    ((23.0, 12.0, 0.0), (47.0, 12.0, 0.0)),
    ((47.0, 12.0, 0.0), (70.0, 0.0, 0.0)),
)

SKETCH_DATA = {
    # --- the three seams radiating from the shared corner -----------------
    "SK_Seam_X": (
        (0.0, 0.0, 0.0),
        (0.7071067811865475, 0.0, 0.0, 0.7071067811865476),
        SEAM_LINES),
    "SK_Seam_Y": (
        (0.0, 0.0, 0.0),
        (0.5, 0.5, 0.5, 0.4999999999999999),
        SEAM_LINES),
    "SK_Seam_Z": (
        (0.0, 0.0, 0.0),
        (0.5, 0.5, 0.5, -0.5000000000000002),
        SEAM_LINES),
    # --- Face1's far boundary (Seam_X -> Face1 -> Seam_Y) ------------------
    "SK_F1_OuterA": (
        (70.0, 0.0, 0.0),
        (0.7063976158089917, 0.6948204440771386, 0.13124233498550786,
         0.03166083352301412),
        (((0.0, 0.0, 0.0), (23.33452377915607, 3.0822070014844907, 0.0)),
         ((23.33452377915607, 3.082207001484491, 0.0),
          (47.51757569573601, 2.984874148806057, 0.0)),
         ((47.51757569573601, 2.984874148806057, 0.0),
          (70.71067811865477, 0.0, 0.0)))),
    "SK_F1_OuterB": (
        (70.0, 70.0, 10.0),
        (-0.003330664841021936, 0.9963826192075238, 0.046866010836615964,
         0.0708107325278698),
        (((0.0, 0.0, 0.0), (23.193102422918756, 3.0133038346638727, 0.0)),
         ((23.193102422918756, 3.0133038346638727, 0.0),
          (47.376154339498676, 3.0531272333598736, 0.0)),
         ((47.376154339498676, 3.0531272333598736, 0.0),
          (70.71067811865474, 0.0, 0.0)))),
    # --- Face2's far boundary (Seam_X -> Face2 -> Seam_Z) ------------------
    "SK_F2_OuterA": (
        (70.0, 0.0, 0.0),
        (-0.47711095427040595, -0.584114592761002, -0.39850990266698383,
         0.5218861344346892),
        (((0.0, 0.0, 0.0), (23.33452377915607, 3.0822070014844907, 0.0)),
         ((23.33452377915607, 3.082207001484491, 0.0),
          (47.517575695736, 2.9848741488060426, 0.0)),
         ((47.517575695736, 2.9848741488060426, 0.0),
          (70.71067811865476, 0.0, 0.0)))),
    "SK_F2_OuterB": (
        (70.0, 10.0, 70.0),
        (-0.05242588484618981, 0.7376881807677872, 0.6714096326283203,
         -0.04771561345629734),
        (((0.0, 0.0, 0.0), (23.193102422918756, 3.0133038346638585, 0.0)),
         ((23.193102422918756, 3.0133038346638585, 0.0),
          (47.376154339498676, 3.0531272333598594, 0.0)),
         ((47.376154339498676, 3.0531272333598594, 0.0),
          (70.71067811865474, -4.440892098500626e-16, 0.0)))),
    # --- Face3's far boundary (Seam_Y -> Face3 -> Seam_Z) ------------------
    "SK_F3_OuterA": (
        (0.0, 70.0, 0.0),
        (-0.08724017012018777, -0.6508182792118182, -0.07566299838833428,
         0.750399780674312),
        (((0.0, 0.0, 0.0), (23.334523779156072, 3.082207001484477, 0.0)),
         ((23.334523779156072, 3.082207001484477, 0.0),
          (47.517575695736, 2.9848741488060284, 0.0)),
         ((47.517575695736, 2.9848741488060284, 0.0),
          (70.71067811865476, 0.0, 0.0)))),
    "SK_F3_OuterB": (
        (10.0, 70.0, 70.0),
        (-0.44101827034203006, 0.5084983380288778, 0.5586950137065158,
         -0.48455361633762417),
        (((0.0, 0.0, 0.0), (23.193102422918763, 3.0133038346638585, 0.0)),
         ((23.193102422918763, 3.0133038346638585, 0.0),
          (47.37615433949868, 3.0531272333598594, 0.0)),
         ((47.37615433949868, 3.0531272333598594, 0.0),
          (70.71067811865476, 0.0, 0.0)))),
}


def sketch_names():
    """The fixture's documented sketch set, in creation order."""
    return list(SKETCH_DATA)


def placement_for(name):
    """The sketch's declared `FreeCAD.Placement`."""
    base, quat, _lines = SKETCH_DATA[name]
    return FreeCAD.Placement(FreeCAD.Vector(*base),
                             FreeCAD.Rotation(*quat))


def declared_world_segments(name):
    """The sketch's three boundary lines as world-space ((x, y, z), ...)
    endpoint pairs -- placement applied, so a comparison against a sketch
    read back from disk does not care about the quaternion's sign."""
    place = placement_for(name)
    world = []
    for a, b in SKETCH_DATA[name][2]:
        world.append((tuple(place.multVec(FreeCAD.Vector(*a))),
                      tuple(place.multVec(FreeCAD.Vector(*b)))))
    return world


def add_boundary_sketch(doc, name):
    """Create `name` in `doc` from SKETCH_DATA: three free-standing line
    segments at the declared placement."""
    obj = doc.addObject("Sketcher::SketchObject", name)
    obj.Label = name
    obj.Placement = placement_for(name)
    for a, b in SKETCH_DATA[name][2]:
        obj.addGeometry(Part.LineSegment(FreeCAD.Vector(*a),
                                         FreeCAD.Vector(*b)), False)
    return obj


def build_fixture(path=None, verbose=True):
    """Write the fixture.  Returns (sketch names, geometry digest)."""
    out = path or OUT_PATH
    doc = FreeCAD.newDocument(FIXTURE_NAME)
    try:
        for name in sketch_names():
            add_boundary_sketch(doc, name)
        doc.recompute()
        # The #108 lesson as a count, not a name: the fixture's sketches must
        # carry exactly the documented number of constraints.  A silent
        # swallow (or an undocumented addition) fails here, before writing.
        for name in sketch_names():
            got = len(doc.getObject(name).Constraints)
            if got != EXPECTED_CONSTRAINTS_PER_SKETCH:
                raise RuntimeError(
                    "%s: built %d constraints, the fixture documents %d"
                    % (name, got, EXPECTED_CONSTRAINTS_PER_SKETCH))
        doc.saveAs(out)
    finally:
        FreeCAD.closeDocument(doc.Name)
    if verbose:
        print("wrote %s" % out, flush=True)
    return verify_fixture(path=out, verbose=verbose)


def geometry_digest(path=None):
    """SHA-256 over every sketch's name, placement and element geometry."""
    digest = hashlib.sha256()
    doc = FreeCAD.openDocument(path or OUT_PATH)
    try:
        for o in sorted(doc.Objects, key=lambda o: o.Name):
            digest.update(("%s|%s|" % (o.Name, o.Placement)).encode())
            for g in o.Geometry:
                digest.update(("%s|%s|" % (g.TypeId, repr(g))).encode())
    finally:
        FreeCAD.closeDocument(doc.Name)
    return digest.hexdigest()


def verify_fixture(path=None, verbose=True):
    """Reopen the written fixture and report its object counts + digest."""
    doc = FreeCAD.openDocument(path or OUT_PATH)
    try:
        sketches = [o.Name for o in doc.Objects
                    if o.TypeId == "Sketcher::SketchObject"]
        others = [o.Name for o in doc.Objects
                  if o.TypeId != "Sketcher::SketchObject"]
        silk = [o.Name for o in doc.Objects
                if getattr(o, "object_type", None)
                in ("Edge", "Patch", "Blend", "CornerBlend")]
        constraints = sum(len(o.Constraints) for o in doc.Objects
                          if o.TypeId == "Sketcher::SketchObject")
    finally:
        FreeCAD.closeDocument(doc.Name)
    if others:
        raise RuntimeError("fixture carries non-sketch objects: %s" % others)
    if silk:
        raise RuntimeError("fixture carries Silk objects: %s" % silk)
    if sorted(sketches) != sorted(sketch_names()):
        raise RuntimeError("fixture carries sketches %s, expected %s"
                           % (sorted(sketches), sorted(sketch_names())))
    if constraints != EXPECTED_CONSTRAINTS_PER_SKETCH * len(sketch_names()):
        raise RuntimeError(
            "fixture carries %d constraints, expected %d (%d per sketch -- "
            "the hand-made examples carry none)"
            % (constraints,
               EXPECTED_CONSTRAINTS_PER_SKETCH * len(sketch_names()),
               EXPECTED_CONSTRAINTS_PER_SKETCH))
    if verbose:
        print("fixture: %d sketches, %d constraints, 0 Silk objects"
              % (len(sketches), constraints), flush=True)
    return sorted(sketches), geometry_digest(path=path)


def main():
    sketches, digest = build_fixture()
    print("sketch set: %d" % len(sketches), flush=True)
    print("geometry digest: %s" % digest, flush=True)
    return 0


if __name__ in ("__main__", "make_cornercube_fixture"):
    sys.exit(main())
