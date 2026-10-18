"""Regenerate `Resources/Test_files/examples/SketchOnly_Demo01Subset.FCStd`
(ticket #98).

The fixture is Demo 01's own 29 sketches plus a **documented supplement of
four half-rib sketches**.  The demo stores one symmetric half of the shape:
every rib sketch runs (mirrored hoop) -> symmetry plane (u = 0.5) -> modelled
hoop (u = 1), and the demo's five ring faces consume only the u in [0.5, 1]
half of each rib (a `ControlPoly4_segment` piece).  A Silk Edge consumes a
WHOLE sketch -- it has no trim property -- so with whole ribs the four ring
faces cannot close a loop and the click-through dies at `create_patch`.  The
supplement supplies each half as an ordinary 3-line ControlPoly4 sketch.

Why the half is exact: the [0.5, 1] sub-curve of a cubic Bezier is exactly a
cubic Bezier, with control points given by the blossom (de Casteljau) at
(0.5, 0.5, 1), (0.5, 1, 1), (1, 1, 1):

    R0 = (P0 + 3*P1 + 3*P2 + P3) / 8      = B(0.5)
    R1 = (P1 + 2*P2 + P3) / 4
    R2 = (P2 + P3) / 2
    R3 = P3

computed here from the demo sketch's own three lines (local coordinates,
placement copied unchanged), so no pole is hand-typed.  The result is
checked against the demo's stored `ControlPoly4_segment` pieces in
`Tests/test_demo01_rebuild.py`.

This script LIVES IN Tests/ ON PURPOSE: `Tests/test_module_generation.py`
pins the count of top-level Mod `.py` files at 57, so a generator at the
workbench root would break that guard.

CONSTRAINTS ARE COPIED, NOT REBUILT (#108).  The demo's sketches are not
loose line soup: they are constrained, and 46 of those constraints
(42 `Coincident`, 4 `PointOnObject`) sit on an EXTERNAL edge -- the
neighbouring sketch's hoop line, drawn into this sketch as external
geometry.  `addConstraint` validates a negative geometry index against the
sketch's OWN external-geometry list (`GeoEnum::RefExt = -3`, then -4, -5 for
each further external edge; -1/-2 are the H/V axes and always valid), so
those 46 raised `IndexError: Constraint has invalid indexes` and the old
`except Exception: pass` swallowed every one of them: the fixture shipped
with 347 of the demo's 393 constraints, geometry intact, construction gone.
The copy is therefore three ordered passes -- all sketches' geometry, then
every sketch's external geometry, then the constraints -- and every failure
is RAISED, never swallowed.  (`copyObject(src, True)` also carries
constraints, but it drags the referenced sketches in as extra objects and
would break the 33-sketch set; batching `addConstraint(list(...))` fails
exactly like the one-at-a-time path, because the index validation is the
same.)

Run (no GUI needed -- it only copies sketches, never touches the maths):

    freecadcmd Tests/make_demo01_fixture.py

The demo file is opened read-only and never saved.  `main()` reopens the
written fixture and prints a SHA-256 of every sketch's geometry, so two runs
can be compared content-for-content (the .FCStd container itself is a zip and
its bytes are not guaranteed stable).
"""

import hashlib
import os
import sys

import FreeCAD
import Part
import Sketcher

HERE = os.path.dirname(os.path.abspath(__file__))
SILK_DIR = os.path.dirname(HERE)
DEMO01_PATH = os.path.join(SILK_DIR, "Resources", "Demo_files",
                           "Silk_Demo_01.FCStd")
OUT_PATH = os.path.join(SILK_DIR, "Resources", "Test_files", "examples",
                        "SketchOnly_Demo01Subset.FCStd")
FIXTURE_NAME = "SketchOnly_Demo01Subset"

# The demo's 29 sketches carry 393 constraints (#108); each of the four
# half-rib supplements is a 3-line sketch with the 2 joints between them.
EXPECTED_CONSTRAINTS = 393 + 4 * 2

# (source rib sketch, supplement sketch name) -- the four ring ribs.  The
# supplement sketch is the u in [0.5, 1] half of the source, from the
# symmetry-plane corner to the modelled hoop.
HALF_RIBS = (
    ("Sketch020", "SK_Half_Rib_FB"),
    ("Sketch022", "SK_Half_Rib_FT"),
    ("Sketch024", "SK_Half_Rib_BkB"),
    ("Sketch026", "SK_Half_Rib_TBk"),
)


def rib_control_points(sketch):
    """The 4 local control points of a 3-line rib sketch.

    `ControlPoly4_3L` reads the three visible lines as the cubic's control
    polygon legs, so the poles are the line endpoints in order:
    [l0.start, l0.end, l1.end, l2.end].
    """
    lines = [g for g in sketch.Geometry
             if g.TypeId == "Part::GeomLineSegment"]
    if len(lines) != 3:
        raise RuntimeError("%s: expected 3 lines, found %d"
                           % (sketch.Name, len(lines)))
    return [lines[0].StartPoint, lines[0].EndPoint,
            lines[1].EndPoint, lines[2].EndPoint]


def half_poles(poles):
    """The blossom control points of the u in [0.5, 1] sub-curve."""
    p0, p1, p2, p3 = poles
    return [(p0 + p1 * 3 + p2 * 3 + p3) * 0.125,   # B(0.5)
            (p1 + p2 * 2 + p3) * 0.25,
            (p2 + p3) * 0.5,
            p3]


def add_half_rib(doc, source, name):
    """Create `name` in `doc`: the u in [0.5, 1] half of `source`, as a
    3-line ControlPoly4 sketch with `source`'s placement."""
    poles = half_poles(rib_control_points(source))
    obj = doc.addObject("Sketcher::SketchObject", name)
    obj.Label = name
    obj.Placement = source.Placement
    for a, b in zip(poles[:-1], poles[1:]):
        obj.addGeometry(Part.LineSegment(a, b), False)
    for i in (0, 1):
        obj.addConstraint(Sketcher.Constraint("Coincident", i, 2, i + 1, 1))
    try:
        obj.ViewObject.Visibility = True
    except Exception:
        pass  # headless: no view object
    return obj


def demo_sketch_names(demo):
    return sorted([o.Name for o in demo.Objects
                   if o.TypeId == "Sketcher::SketchObject"],
                  key=lambda s: int(s[6:]))


def copy_external_geometry(src, dst, destinations):
    """Re-attach `dst` to the same external geometry `src` sits on.

    `destinations` maps a demo sketch's name to its copy in the fixture, so
    the links point at the copies and not at the demo's objects.
    `ExternalGeometry` is read-only from Python in FreeCAD 1.1, so each link
    is re-made with `addExternal`, one call per sub-element; `addExternal`
    APPENDS, so the external indices come out in the demo's order --
    external edge `i` is `GeoEnum::RefExt - i` = -3, -4, -5, ... -- exactly
    the indices the demo's own constraints address.  Returns how many links
    were added.
    """
    added = 0
    for obj, subs in src.ExternalGeometry:
        for sub in subs:
            dst.addExternal(destinations[obj.Name].Name, sub)
            added += 1
    return added


def copy_constraints(src, dst):
    """Copy every constraint of `src` onto `dst`; RAISE if one will not go
    on, naming the constraint and the reason.

    #108: this was `try: dst.addConstraint(c) except Exception: pass`.  The
    swallow is what let a fixture with 347 of the demo's 393 constraints
    ship as a valid one, so a failure here is now fatal and says which
    constraint it was.
    """
    failures = []
    for i, c in enumerate(src.Constraints):
        try:
            dst.addConstraint(c)
        except Exception as exc:
            failures.append("%s constraint %d (%s): %s: %s"
                            % (src.Name, i, c.Type, type(exc).__name__, exc))
    if failures:
        raise RuntimeError(
            "%s: %d of %d constraints would not copy:\n  %s"
            % (src.Name, len(failures), len(src.Constraints),
               "\n  ".join(failures)))


def build_fixture(verbose=True):
    """Write the fixture.  Returns (sketch names, geometry digest)."""
    demo = FreeCAD.openDocument(DEMO01_PATH)
    try:
        names = demo_sketch_names(demo)
        if len(names) != 29:
            raise RuntimeError("demo carries %d sketches, expected 29"
                               % len(names))
        doc = FreeCAD.newDocument(FIXTURE_NAME)
        try:
            destinations = {}
            for nm in names:
                src = demo.getObject(nm)
                dst = doc.addObject("Sketcher::SketchObject", nm)
                dst.Label = src.Label
                dst.Placement = src.Placement
                for g in src.Geometry:
                    dst.addGeometry(g, False)
                destinations[nm] = dst
                try:
                    dst.ViewObject.Visibility = True
                except Exception:
                    pass
            # `addExternal` PROJECTS the referenced edge onto this sketch's
            # plane, so the referenced sketch needs a Shape -- a sketch that
            # has never been recomputed has none ("Failed to project
            # external geometry ...: null shape").  No constraint exists
            # yet, so this recompute cannot move a copied geometry.
            doc.recompute()
            external = 0
            for nm in names:
                external += copy_external_geometry(demo.getObject(nm),
                                                   destinations[nm],
                                                   destinations)
            constraints = 0
            for nm in names:
                copy_constraints(demo.getObject(nm), destinations[nm])
                constraints += len(destinations[nm].Constraints)
            for src_name, half_name in HALF_RIBS:
                add_half_rib(doc, demo.getObject(src_name), half_name)
            doc.recompute()
            # The demo's own per-sketch counts, checked before the file is
            # written: a fixture that cannot reproduce the demo's
            # construction must say so here (#108).
            for nm in names:
                want = len(demo.getObject(nm).Constraints)
                got = len(destinations[nm].Constraints)
                if want != got:
                    raise RuntimeError("%s: copied %d of the demo's %d "
                                       "constraints" % (nm, got, want))
            if verbose:
                print("demo: %d sketches, %d constraints, %d external "
                      "geometry links" % (len(names), constraints, external),
                      flush=True)
            doc.saveAs(OUT_PATH)
        finally:
            FreeCAD.closeDocument(doc.Name)
    finally:
        FreeCAD.closeDocument(demo.Name)
    if verbose:
        print("wrote %s" % OUT_PATH, flush=True)
    return verify_fixture(verbose=verbose)


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


def verify_fixture(verbose=True):
    """Reopen the written fixture and report its sketch set + digest."""
    doc = FreeCAD.openDocument(OUT_PATH)
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
    if len(sketches) != 33:
        raise RuntimeError("fixture carries %d sketches, expected 33"
                           % len(sketches))
    if constraints != EXPECTED_CONSTRAINTS:
        raise RuntimeError("fixture carries %d constraints, expected %d "
                           "(the demo's 393 on its 29 sketches + 2 per "
                           "half-rib supplement)"
                           % (constraints, EXPECTED_CONSTRAINTS))
    if verbose:
        print("fixture: %d sketches, %d constraints, 0 non-sketch objects"
              % (len(sketches), constraints), flush=True)
    return sorted(sketches), geometry_digest()


def main():
    sketches, digest = build_fixture()
    print("sketch set: %d" % len(sketches), flush=True)
    print("geometry digest: %s" % digest, flush=True)
    return 0


if __name__ in ("__main__", "make_demo01_fixture"):
    sys.exit(main())
