"""
The corner fill, from the Silk-side selection (ticket #96).

The owner wants to JUDGE a one-patch corner by eye. The manual Surface
workbench path is blocked by our own `DisplayMode = "Shaded"` (the picker can
only return `Face1` -- docs/research/silk-fill-picking.md), so Silk assembles
the fill instead: the ring strips are selected IN SILK, and
`SilkWorkflowOps.create_corner_fill` builds the `Surface::Filling` over the
hole they close.

What is pinned here:

  1. the fill is built FROM THE COMMAND'S OWN PATH -- `Silk_CornerFill`'s
     `Activated` reads the selection and calls the ops resolver, exactly like
     the corner blend's command -- and the wiring it leaves on the object is
     the measured one: the strips' OWN `EdgeN` junction rows (no throwaway
     carrier), `Face1` supports, one order per edge;
  2. the raw numbers: face count, validity, and the boundary residual
     `distToShape` per edge (0.0 mm for a sound fill);
  3. an unusable selection is REFUSED BY NAME, before anything is
     constructed, leaving no object at all -- the #80/#83 lesson (an invalid
     object parked in the tree reads `State=Up-to-date`);
  4. one undo step per command run, like every other Silk command.

Run: python3 Tests/run_all.py corner_fill
"""
import FreeCAD
from FreeCAD import Gui

from Tests.mcp_harness import check
from Tests.test_seam_resolver import _Capture

STRIPS = ("B12", "B24", "B43", "B31")


def _select(*objs):
    Gui.Selection.clearSelection()
    for o in objs:
        Gui.Selection.addSelection(o)


def _fills(doc):
    return [o for o in doc.Objects if o.TypeId == "Surface::Filling"]


def test_corner_fill_builds_from_the_selected_ring(doc):
    """4 selected ring strips -> ONE Surface::Filling over their junction
    rows, built through the command: face count, validity and the boundary
    residual are reported raw."""
    errors, checks = [], []
    import Tests.corner_model as cm
    from SilkCorner import CreateCornerFill

    cm.build_corner_model(doc)
    strips = [doc.getObject(n) for n in STRIPS]
    _select(*strips)
    with _Capture() as cap:
        CreateCornerFill().Activated()
    doc.recompute()

    fills = _fills(doc)
    check(len(fills) == 1,
          "expected exactly 1 Surface::Filling, got %d (%s)"
          % (len(fills), [o.Name for o in fills]), errors)
    if len(fills) != 1:
        return {"pass": not errors, "checks": checks, "errors": errors}
    fill = fills[0]

    links = [(o.Name, list(s)) for o, s in (fill.BoundaryEdges or [])]
    faces = list(fill.BoundaryFaces or [])
    orders = list(fill.BoundaryOrder or [])
    checks.append("boundary edges (raw): %r" % (links,))
    checks.append("boundary faces (raw): %r" % (faces,))
    checks.append("boundary orders (raw): %r" % (orders,))

    check(len(links) == 4, "expected 4 boundary edges, got %d" % len(links),
          errors)
    check(all(name in STRIPS for name, _sub in links),
          "a boundary edge is not one of the ring strips: %r" % (links,),
          errors)
    check(all(sub and sub[0].startswith("Edge") for _name, sub in links),
          "a boundary edge is not an EdgeN sub-shape: %r" % (links,), errors)
    check(faces == ["Face1"] * 4,
          "expected the strips' own faces as supports, got %r" % (faces,),
          errors)
    check(orders == [1] * 4,
          "expected the default order 1 on every edge, got %r" % (orders,),
          errors)

    # The carriers are the STRIPS THEMSELVES (the probe needed throwaway
    # Part::Feature copies); a linked strip is the whole point of this path.
    check(all(doc.getObject(name) in strips for name, _sub in links),
          "the fill is not linked to the selected strips: %r" % (links,),
          errors)

    shape = fill.Shape
    residual = [round(shape.distToShape(
        doc.getObject(name).Shape.getElement(sub[0]))[0], 9)
        for name, sub in links]
    checks.append("faces: %d" % len(shape.Faces))
    checks.append("valid: %s" % bool(shape.Faces and shape.isValid()))
    checks.append("boundary residual distToShape (mm): %r" % (residual,))
    check(len(shape.Faces) == 1, "expected 1 face, got %d" % len(shape.Faces),
          errors)
    check(shape.isValid(), "the fill is not a valid shape", errors)
    check(max(residual) == 0.0,
          "the fill does not contain its own boundary: %r" % (residual,),
          errors)

    check(any("surface fill" in m for m in cap.messages),
          "the success message does not name the fill: %r" % (cap.messages,),
          errors)
    return {"pass": not errors, "checks": checks, "errors": errors}


def test_corner_fill_is_one_undo_step(doc):
    """The command opens exactly one transaction, like every other Silk
    command: one undo returns the document to no fill at all."""
    errors, checks = [], []
    import Tests.corner_model as cm
    from SilkCorner import CreateCornerFill

    cm.build_corner_model(doc)
    strips = [doc.getObject(n) for n in STRIPS]
    before = set(o.Name for o in doc.Objects)
    _select(*strips)
    with _Capture():
        CreateCornerFill().Activated()
    doc.recompute()
    created = set(o.Name for o in doc.Objects) - before
    checks.append("objects created: %r" % (sorted(created),))
    check(len(created) == 1 and len(_fills(doc)) == 1,
          "expected exactly one new Surface::Filling, got %r" % (created,),
          errors)
    doc.undo()
    doc.recompute()
    check(not _fills(doc),
          "one undo did not remove the fill: %s"
          % [o.Name for o in _fills(doc)], errors)
    return {"pass": not errors, "checks": checks, "errors": errors}


def test_corner_fill_refuses_a_selection_that_is_not_a_ring(doc):
    """A selection that is not the ring -- 2 strips, or 3 that do not ring a
    junction -- is refused BY NAME, and NOTHING is left in the tree: neither
    a fill nor an invalid object reading State=Up-to-date (#80/#83)."""
    errors, checks = [], []
    import Tests.corner_model as cm
    from SilkCorner import CreateCornerFill

    cm.build_corner_model(doc)

    for label, names in (("2 strips", ("B12", "B24")),
                         ("3 strips that do not ring a junction",
                          ("B12", "B24", "B31"))):
        before = set(o.Name for o in doc.Objects)
        _select(*[doc.getObject(n) for n in names])
        with _Capture() as cap:
            CreateCornerFill().Activated()
        doc.recompute()
        created = sorted(set(o.Name for o in doc.Objects) - before)
        checks.append("%s: console: %s"
                      % (label, " | ".join(m.strip() for m in cap.errors)[:200]))
        checks.append("%s: created: %r" % (label, created))
        check(not created,
              "%s: the refused command still created %r" % (label, created),
              errors)
        check(not _fills(doc),
              "%s: a Surface::Filling survived the refusal" % label, errors)
        check(any(m.startswith("Silk:") for m in cap.errors),
              "%s: the refusal is not a named console error: %r"
              % (label, cap.errors), errors)
    return {"pass": not errors, "checks": checks, "errors": errors}


def test_corner_fill_refuses_an_order_it_cannot_build(doc):
    """`BoundaryOrder` is FreeCAD's 0/1/2 and nothing else; an unusable order
    is refused BY NAME before anything is constructed."""
    errors, checks = [], []
    import Tests.corner_model as cm
    from SilkWorkflowOps import create_corner_fill

    cm.build_corner_model(doc)
    strips = [doc.getObject(n) for n in STRIPS]
    before = set(o.Name for o in doc.Objects)
    with _Capture() as cap:
        result = create_corner_fill(strips, order=3)
    doc.recompute()
    created = sorted(set(o.Name for o in doc.Objects) - before)
    checks.append("console: %s" % " | ".join(m.strip() for m in cap.errors)[:200])
    checks.append("created: %r" % (created,))
    check(result is None, "order 3 was accepted: %r" % (result,), errors)
    check(not created, "order 3 created %r" % (created,), errors)
    check(any("order" in m for m in cap.errors),
          "the refusal does not name the order: %r" % (cap.errors,), errors)
    return {"pass": not errors, "checks": checks, "errors": errors}
