"""
BoundarySpline tree children (ticket #11): the spline PARENTS the sketch that
drives it, so the tree reads top-down, spline -> sketch.

Mechanism: the `EdgeViewProvider.claimChildren` idiom (#52), reused -- FreeCAD
renders tree nesting through the parent's VIEWPROVIDER, not through
document-level grouping (a FeaturePython cannot nest), and `BoundarySpline`
is a `Part::FeaturePython` with a single `Sketch` link. The datas-level
`Sketch` link is untouched, so no identity invariant moves, and a sketch no
spline points at stays at top level.

One spline, one sketch: unlike an Edge (1-2 sketches, shared by up to two
patches), a BoundarySpline has exactly one input, so `claimChildren` is the
link list of one -- and the claim follows the link, which is why it also
holds on a reloaded document.
"""

import os
import tempfile

import FreeCAD
import Part
from FreeCAD import Base

from Tests.mcp_harness import check


def _triangle_sketch(doc, name="Sketch"):
    sk = doc.addObject("Sketcher::SketchObject", name)
    sk.addGeometry(Part.LineSegment(Base.Vector(0, 0, 0),
                                    Base.Vector(10, 0, 0)), False)
    sk.addGeometry(Part.LineSegment(Base.Vector(10, 0, 0),
                                    Base.Vector(10, 10, 0)), False)
    sk.addGeometry(Part.LineSegment(Base.Vector(10, 10, 0),
                                    Base.Vector(0, 5, 0)), False)
    doc.recompute()
    return sk


def _claims(spline):
    """The tree children the spline's view provider reports."""
    return list(spline.ViewObject.Proxy.claimChildren())


def _boundary_spline(doc, sketch, name="BoundarySpline"):
    from BoundarySpline import BoundarySpline

    bs = doc.addObject("Part::FeaturePython", name)
    BoundarySpline(bs, sketch)
    doc.recompute()
    return bs


def test_boundaryspline_claims_its_driving_sketch(doc):
    """The sketch the spline is built from appears under the spline."""
    errors, checks = [], []
    sketch = _triangle_sketch(doc)
    spline = _boundary_spline(doc, sketch)

    children = _claims(spline)
    checks.append("BoundarySpline tree children: %s"
                  % [o.Name for o in children])
    check(children == [sketch],
          "BoundarySpline claims %s, want [%s]"
          % ([o.Name for o in children], sketch.Name), errors)
    return {"pass": not errors, "errors": errors, "checks": checks}


def test_a_sketch_no_spline_drives_stays_top_level(doc):
    """A sketch referenced by no spline is claimed by none -- top level."""
    errors, checks = [], []
    used = _triangle_sketch(doc, "Used")
    unused = _triangle_sketch(doc, "Unused")
    spline = _boundary_spline(doc, used)

    children = _claims(spline)
    check(unused not in children,
          "the spline claims the sketch it does not drive: %s"
          % [o.Name for o in children], errors)
    check(children == [used],
          "BoundarySpline claims %s, want only [%s]"
          % ([o.Name for o in children], used.Name), errors)
    checks.append("unused sketch %s claimed by no spline (top level)"
                  % unused.Name)
    return {"pass": not errors, "errors": errors, "checks": checks}


def test_the_claim_survives_save_and_reopen(doc):
    """The parent/child relation is a view provider, so it must come back
    with the view provider on a reloaded document -- the same object, its
    link and its tree child."""
    errors, checks = [], []
    sketch = _triangle_sketch(doc)
    spline = _boundary_spline(doc, sketch)
    sketch_name = sketch.Name

    path = os.path.join(tempfile.mkdtemp(prefix="silk_bs_tree_"),
                        "bs_tree.FCStd")
    doc.saveAs(path)
    FreeCAD.closeDocument(doc.Name)
    reopened = FreeCAD.openDocument(path)
    try:
        restored = reopened.getObject("BoundarySpline")
        if restored is None:
            errors.append("BoundarySpline gone from the reopened document")
        else:
            proxy = restored.ViewObject.Proxy
            checks.append("restored view provider: %s"
                          % type(proxy).__name__)
            children = [o.Name for o in _claims(restored)]
            checks.append("restored tree children: %s" % children)
            check(children == [sketch_name],
                  "after reopen the spline claims %s, want [%s]"
                  % (children, sketch_name), errors)
    finally:
        try:
            FreeCAD.closeDocument(reopened.Name)
        except Exception:
            pass
        try:
            os.remove(path)
        except OSError:
            pass
    return {"pass": not errors, "errors": errors, "checks": checks}


ALL_TESTS = [
    test_boundaryspline_claims_its_driving_sketch,
    test_a_sketch_no_spline_drives_stays_top_level,
    test_the_claim_survives_save_and_reopen,
]
