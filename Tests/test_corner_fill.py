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
  4. one undo step per command run, like every other Silk command;
  5. the component behind the command takes an EXPLICIT hole boundary as
     well as the ring strips (`create_fill`), orders that boundary by
     connectivity -- never by click order -- and refuses a boundary that is
     not ONE closed loop before anything is constructed;
  6. the command is REGISTERED with FreeCAD's command manager and is a
     member of the workbench's visible set (#96, owner decision D3) -- the
     button beside the Silk corner -- and its bad-selection refusals are the
     COMPONENT's own wording, not a second spelling of it;
  7. #121: the shipped oracle measures the fill's TANGENT-PLANE GAP along
     the boundary -- the instrument the MANUAL probe used, now in the code
     that judges the fill -- with its ZERO CONTROL read in the same run, so
     the error floor is a measurement in the suite;
  8. #121: the requested order is not evidence.  The same boundary built at
     order 0 (C0) is a SOUND fill that contains its own boundary and passes
     every C0 test; only the measured gap tells the two orders apart, so
     the oracle accepts the order-1 fill and refuses the order-0 one;
  9. #121: the SELECTABLE C0 fallback -- with no fallback selected the
     refusal stands and nothing is left in the tree; with it selected the
     fill is built at order 0 and the console says so by name.

Run: python3 Tests/run_all.py corner_fill
"""

# --- manual tier ------------------------------------------------------
# This module's subject is an end-to-end rebuild / GUI drive /
# measurement sweep, so it is NOT in the default (fast) tier. Run it
# with `python3 Tests/run_all.py --manual` (or by name as a filter);
# Tests/test_manual_tier.py asserts it stays importable. See suite.py.
MANUAL = True
import os

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


def _fill_links(fill):
    """The fill's boundary wiring as [(object, "EdgeN"), ...] -- the shape
    FreeCAD hands back (`BoundaryEdges` carries a LIST of sub-names)."""
    out = []
    for obj, subs in (fill.BoundaryEdges or []):
        sub = list(subs)[0] if isinstance(subs, (list, tuple)) else subs
        out.append((obj, sub))
    return out


def _fill_faces(fill):
    """The fill's support faces, one per boundary edge."""
    return list(fill.BoundaryFaces or [])


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


def _boundary_names(fill):
    """The fill's boundary wiring as [(obj name, "EdgeN"), ...]."""
    return [(o.Name, list(s)[0]) for o, s in (fill.BoundaryEdges or [])]


def _same_cyclic_order(a, b):
    """True when `a` and `b` are the same closed loop: equal up to a
    rotation, in either direction."""
    n = len(a)
    if n != len(b):
        return False
    for r in range(n):
        rolled = a[r:] + a[:r]
        if rolled == b or list(reversed(rolled)) == b:
            return True
    return False


def test_fill_from_an_explicit_boundary_is_ordered_by_connectivity(doc):
    """`create_fill` takes the hole boundary DIRECTLY -- `[(object,
    "EdgeN"), ...]`, the wiring `Surface::Filling` wants -- in any order,
    and wires the loop by connectivity: two scrambled inputs build the SAME
    cyclic wire, and the wire is genuinely cyclic (each edge shares a corner
    with the next)."""
    errors, checks = [], []
    import Tests.corner_model as cm
    import SilkWorkflowOps as OPS

    cm.build_corner_model(doc)
    strips = [doc.getObject(n) for n in STRIPS]
    boundary, why = OPS.corner_fill_boundary(strips)
    check(boundary is not None,
          "the ring's boundary did not resolve: %s" % why, errors)
    if boundary is None:
        return {"pass": not errors, "checks": checks, "errors": errors}
    links, _faces = boundary

    scrambled = [[links[2], links[0], links[3], links[1]],
                 [links[3], links[2], links[1], links[0]]]
    fills = []
    for order_in in scrambled:
        fill = OPS.create_fill(order_in)
        check(fill is not None,
              "create_fill refused the boundary in click order %r"
              % ([s for _o, s in order_in],), errors)
        if fill is None:
            continue
        fills.append(fill)
        residual = [round(fill.Shape.distToShape(
            o.Shape.getElement(list(s)[0]))[0], 9)
            for o, s in fill.BoundaryEdges]
        checks.append("faces: %d, valid: %s, residual: %r"
                      % (len(fill.Shape.Faces), bool(fill.Shape.isValid()),
                         residual))
        check(len(fill.Shape.Faces) == 1 and fill.Shape.isValid(),
              "the explicit-boundary fill is not one valid face", errors)
        check(max(residual) == 0.0,
              "the fill does not contain its own boundary: %r" % (residual,),
              errors)

    if len(fills) == 2:
        first, second = _boundary_names(fills[0]), _boundary_names(fills[1])
        checks.append("click order A wired %r" % (first,))
        checks.append("click order B wired %r" % (second,))
        check(_same_cyclic_order(first, second),
              "the wire is not the same cyclic order for both click orders: "
              "%r vs %r" % (first, second), errors)
        # ...and it really is a loop: consecutive links share a corner.
        ends = []
        for o, s in fills[0].BoundaryEdges:
            e = o.Shape.getElement(list(s)[0])
            ends.append((e.valueAt(e.FirstParameter),
                         e.valueAt(e.LastParameter)))
        closed = all(
            min((ends[k][1] - ends[(k + 1) % len(ends)][0]).Length,
                (ends[k][1] - ends[(k + 1) % len(ends)][1]).Length) < 1e-6
            for k in range(len(ends)))
        check(closed, "the wired boundary does not chain corner to corner: %r"
              % (ends,), errors)
    return {"pass": not errors, "checks": checks, "errors": errors}


def test_fill_refuses_a_boundary_that_is_not_one_closed_loop(doc):
    """An explicit boundary that is not ONE closed loop -- an open chain, or
    the ring plus a surplus edge (over-constrained) -- is refused BY NAME
    before anything is constructed, and no object is left in the tree."""
    errors, checks = [], []
    import Tests.corner_model as cm
    import SilkWorkflowOps as OPS

    cm.build_corner_model(doc)
    strips = [doc.getObject(n) for n in STRIPS]
    links, _faces = OPS.corner_fill_boundary(strips)[0]
    b12 = doc.getObject("B12")
    junction = [s for o, s in links if o is b12][0]
    surplus = None
    for i in range(1, len(b12.Shape.Edges) + 1):
        cand = "Edge%d" % i
        if cand != junction:
            surplus = (b12, cand)
            break
    check(surplus is not None, "no surplus edge on B12 to over-constrain with",
          errors)

    for label, boundary in (("an open chain (3 of the ring's 4 edges)",
                             links[:3]),
                            ("the ring plus a surplus edge",
                             list(links) + [surplus])):
        before = set(o.Name for o in doc.Objects)
        with _Capture() as cap:
            result = OPS.create_fill(boundary)
        doc.recompute()
        created = sorted(set(o.Name for o in doc.Objects) - before)
        checks.append("%s: console: %s"
                      % (label, " | ".join(m.strip() for m in cap.errors)[:200]))
        checks.append("%s: created: %r" % (label, created))
        check(result is None, "%s was accepted: %r" % (label, result), errors)
        check(not created, "%s created %r" % (label, created), errors)
        check(not _fills(doc),
              "%s left a Surface::Filling behind" % label, errors)
        check(any(m.startswith("Silk:") for m in cap.errors),
              "%s: the refusal is not a named console error: %r"
              % (label, cap.errors), errors)
    return {"pass": not errors, "checks": checks, "errors": errors}


def test_fill_works_on_a_general_hole_not_just_a_corner(doc):
    """The component is not corner-shaped: the SAME entry point fills a
    plain rectangular hole -- one Patch's own four boundary edges, each
    supported by the patch's own face -- from a scrambled edge list.  The
    probe's raw-patch feed was over-constrained and invalid (#91/#96); a
    whole boundary loop is the general case that is not."""
    errors, checks = [], []
    import Tests.corner_model as cm
    import SilkWorkflowOps as OPS

    model = cm.build_corner_model(doc)
    patch = model["patches"]["Patch001"]
    names = ["Edge%d" % i for i in range(1, len(patch.Shape.Edges) + 1)]
    checks.append("patch boundary edges: %r" % (names,))
    check(len(names) == 4, "expected a 4-edge patch boundary, got %r"
          % (names,), errors)
    if len(names) != 4:
        return {"pass": not errors, "checks": checks, "errors": errors}

    boundary = [(patch, n) for n in (names[2], names[0], names[3], names[1])]
    fill = OPS.create_fill(boundary)
    check(fill is not None, "create_fill refused a plain patch boundary",
          errors)
    if fill is None:
        return {"pass": not errors, "checks": checks, "errors": errors}

    residual = [round(fill.Shape.distToShape(
        patch.Shape.getElement(list(s)[0]))[0], 9)
        for _o, s in fill.BoundaryEdges]
    checks.append("faces: %d, valid: %s, residual: %r"
                  % (len(fill.Shape.Faces), bool(fill.Shape.isValid()),
                     residual))
    check(len(fill.Shape.Faces) == 1,
          "expected 1 face, got %d" % len(fill.Shape.Faces), errors)
    check(fill.Shape.isValid(), "the general-hole fill is not a valid shape",
          errors)
    check(max(residual) == 0.0,
          "the fill does not contain its own boundary: %r" % (residual,),
          errors)
    check(all(o is patch for o, _s in fill.BoundaryEdges),
          "the fill is not linked to the patch that owns the boundary: %r"
          % ([(o.Name, s) for o, s in fill.BoundaryEdges],), errors)
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


def test_corner_fill_command_is_registered_and_refuses_a_bad_selection(doc):
    """#96 (D3): `Silk_CornerFill` is a real registered Gui command --
    `Gui.listCommands()` holds it and FreeCAD builds a QAction for it, the
    public check `test_initgui_commands` makes for the whole visible set --
    and the handler REFUSES a selection that is not a corner-fill boundary
    BY NAME, in the COMPONENT's own wording, leaving nothing in the tree.

    Deliberately silent on WHERE the button sits: menu/toolbar layout is
    `test_initgui_commands`' contract. What is pinned here is that the command
    exists for FreeCAD and that a bad selection is refused cleanly.
    """
    errors, checks = [], []
    import Tests.corner_model as cm
    from SilkCorner import CreateCornerFill

    # 1. registered: what the command manager holds, and the button FreeCAD
    #    would build for it. `getAction()` does NOT build on demand (measured;
    #    see test_initgui_commands), so a session whose workbench toolbar
    #    predates this command has no action to read yet -- the session-
    #    independent proof is the command's own resources.
    check("Silk_CornerFill" in set(Gui.listCommands()),
          "Silk_CornerFill is not in Gui.listCommands() -- not registered",
          errors)
    command = Gui.Command.get("Silk_CornerFill")
    check(command is not None,
          "Gui.Command.get('Silk_CornerFill') is None", errors)
    resources = CreateCornerFill().GetResources()
    check(str(resources.get("MenuText", "")).strip() != "",
          "Silk_CornerFill has no MenuText to label a button with: %r"
          % (resources,), errors)
    pixmap = resources.get("Pixmap")
    check(bool(pixmap) and os.path.isabs(pixmap) and os.path.isfile(pixmap),
          "Silk_CornerFill's Pixmap is not an existing absolute icon: %r"
          % (pixmap,), errors)
    actions = (command.getAction() or []) if command is not None else []
    if actions:
        names = [a.objectName() for a in actions]
        check(all(n == "Silk_CornerFill" for n in names),
              "the QAction(s) carry %r" % (names,), errors)
        check(actions[0].text().strip() != "",
              "the Silk_CornerFill QAction has an empty label", errors)
        checks.append("Silk_CornerFill registered; QAction label %r"
                      % actions[0].text())
    else:
        checks.append("Silk_CornerFill registered; no QAction in this "
                      "session (its toolbar predates the name), button "
                      "resources %r" % (resources.get("MenuText"),))

    # 2. every unusable selection is refused by name, nothing is created
    cm.build_corner_model(doc)
    patch = doc.getObject("Patch44")
    strips = [doc.getObject(n) for n in STRIPS]
    counted = "needs the ring's 3 or 4 blend strips"
    cases = [("no selection", (), counted),
             ("a patch instead of the strips", (patch,), counted),
             ("one strip", (strips[0],), counted),
             ("two strips", (strips[0], strips[1]), counted),
             ("three strips that do not ring a junction",
              (strips[0], strips[1], strips[3]),
              "cannot build the corner fill over these 3 blends")]
    for label, objs, wording in cases:
        before = set(o.Name for o in doc.Objects)
        _select(*objs)
        with _Capture() as cap:
            CreateCornerFill().Activated()
        doc.recompute()
        created = sorted(set(o.Name for o in doc.Objects) - before)
        named = [m for m in cap.errors if wording in m]
        checks.append("%s: %s"
                      % (label, " | ".join(m.strip()
                                           for m in cap.errors)[:200]))
        check(named,
              "%s: no refusal carrying the component's own wording %r; got %r"
              % (label, wording, cap.errors), errors)
        check(all(m.startswith("Silk:") for m in named),
              "%s: the refusal is not a named console error: %r"
              % (label, named), errors)
        check(not created,
              "%s: the refused command still created %r" % (label, created),
              errors)
        check(not _fills(doc),
              "%s: a Surface::Filling survived the refusal" % label, errors)
    return {"pass": not errors, "checks": checks, "errors": errors}


# ---------------------------------------------------------------------------
# #121 -- the shipped oracle's CONTINUITY MEASUREMENT, the ORDER it
# actually reached, and the SELECTABLE C0 fallback.
# ---------------------------------------------------------------------------

def test_the_shipped_oracle_measures_the_boundary_normal_gap(doc):
    """#121: the SHIPPED oracle measures the fill's TANGENT-PLANE GAP along
    the boundary -- the instrument the MANUAL probe (`Tests/
    g2_corner_fill_probe.py`) used, now living in the code that judges the
    fill, so there is ONE implementation and ONE error floor.

    The ZERO CONTROL is read in the same run: the fill's own surface
    measured against ITSELF, through the same instrument.  That is the
    floor, as a measurement in the suite and not a number quoted from a
    doc.  The raw per-edge readings are reported either way.
    """
    errors, checks = [], []
    import Tests.corner_model as cm
    import SilkWorkflowOps as OPS

    cm.build_corner_model(doc)
    strips = [doc.getObject(n) for n in STRIPS]
    fill = OPS.create_corner_fill(strips, order=1)
    check(fill is not None, "the corner fill did not build", errors)
    if fill is None:
        return {"pass": not errors, "checks": checks, "errors": errors}

    links = _fill_links(fill)
    faces = _fill_faces(fill)
    report = OPS.fill_normal_gap(fill, links, faces)
    checks.append("boundary normal gap per edge (deg): %r"
                  % ([(e["label"], e["gap_deg"], e["stations"])
                      for e in report["per_edge"]],))
    checks.append("max boundary normal gap: %r deg" % (report["max_gap_deg"],))
    checks.append("the shipped bar: %.1f deg" % OPS.FILL_NORMAL_GAP_TOL_DEG)

    check(report["measurable"],
          "the tangent-plane gap could not be measured at all: %r"
          % (report["reason"],), errors)
    check(all(e["stations"] > 0 for e in report["per_edge"]),
          "a boundary edge carried no measurable station: %r"
          % (report["per_edge"],), errors)
    check(report["max_gap_deg"] is not None,
          "no max gap was reported", errors)

    # The ZERO CONTROL: the fill's own surface, measured against itself.
    edges = fill.Shape.Edges
    self_links = [(fill, "Edge%d" % (i + 1)) for i in range(len(edges))]
    zero = OPS.fill_normal_gap(fill, self_links, ["Face1"] * len(edges))
    checks.append("zero control (the fill against itself): %r deg"
                  % (zero["max_gap_deg"],))
    check(zero["measurable"],
          "the zero control could not be measured: %r" % (zero["reason"],),
          errors)
    check(zero["max_gap_deg"] is not None and zero["max_gap_deg"] <= 1e-5,
          "the instrument does not read 0 on an identical pair: %r"
          % (zero["max_gap_deg"],), errors)
    return {"pass": not errors, "checks": checks, "errors": errors}


def test_the_oracle_judges_the_order_the_fill_reached(doc):
    """#121: the REQUESTED order is not evidence.

    The same boundary built at order 0 (C0) is a SOUND fill: it has a
    face, it is valid, and it contains its own boundary -- it passes every
    C0 test, which is all the shipped oracle used to ask.  Only the
    measured tangent-plane gap tells the two orders apart.

    So the shipped oracle, asked for order 1, ACCEPTS the order-1 fill and
    REFUSES the order-0 one by name -- the order FreeCAD accepted and did
    not reach.
    """
    errors, checks = [], []
    import Tests.corner_model as cm
    import SilkWorkflowOps as OPS

    cm.build_corner_model(doc)
    strips = [doc.getObject(n) for n in STRIPS]

    fill1 = OPS.create_corner_fill(strips, order=1, name="OrderOne")
    check(fill1 is not None, "the order-1 corner fill did not build", errors)
    fill0 = OPS.create_corner_fill(strips, order=0, name="OrderZero")
    check(fill0 is not None, "the order-0 corner fill did not build", errors)
    if fill1 is None or fill0 is None:
        return {"pass": not errors, "checks": checks, "errors": errors}

    links1, faces1 = _fill_links(fill1), _fill_faces(fill1)
    links0, faces0 = _fill_links(fill0), _fill_faces(fill0)
    gap1 = OPS.fill_normal_gap(fill1, links1, faces1)["max_gap_deg"]
    gap0 = OPS.fill_normal_gap(fill0, links0, faces0)["max_gap_deg"]
    checks.append("order 1 gap: %r deg; order 0 gap: %r deg" % (gap1, gap0))

    problem1 = OPS.corner_fill_problem(fill1, links1, faces1, order=1)
    check(problem1 is None,
          "the shipped oracle refused the order-1 fill: %r" % (problem1,),
          errors)

    # The order-0 fill, judged as order 1: the order FreeCAD ACCEPTED but
    # did not reach.
    problem0 = OPS.corner_fill_problem(fill0, links0, faces0, order=1)
    checks.append("the order-0 fill judged as order 1: %r" % (problem0,))
    check(problem0 is not None,
          "the shipped oracle accepted a C0 fill as an order-1 fill", errors)
    check(problem0 is not None and "tangent-plane gap" in problem0,
          "the refusal does not name the measured gap: %r" % (problem0,),
          errors)

    # ...and the same fill judged as the C0 it is: accepted.
    check(OPS.corner_fill_problem(fill0, links0, faces0, order=0) is None,
          "the shipped oracle refused the C0 fill it was asked for", errors)

    # The instrument DISCRIMINATES: the two orders read differently.
    check(gap1 is not None and gap0 is not None and gap1 < gap0,
          "the instrument does not tell the two orders apart: %r vs %r"
          % (gap1, gap0), errors)
    return {"pass": not errors, "checks": checks, "errors": errors}


def test_the_c0_fallback_is_selectable(doc):
    """#96's third acceptance item, and #121: a SELECTABLE C0 fallback
    where the requested order is refused.

    With NO fallback selected the refusal stands and nothing is left in the
    tree (the #80/#83 lesson).  With the fallback selected the fill is
    built at order 0 and the console says so BY NAME -- a caller is never
    handed a C0 fill it did not ask for, silently.
    """
    errors, checks = [], []
    import Tests.corner_model as cm
    import SilkWorkflowOps as OPS

    cm.build_corner_model(doc)
    strips = [doc.getObject(n) for n in STRIPS]
    links, _faces = OPS.corner_fill_boundary(strips)
    check(bool(links), "the ring's boundary did not resolve", errors)
    if not links:
        return {"pass": not errors, "checks": checks, "errors": errors}

    # 1. no fallback selected: refused, nothing created.
    before = set(o.Name for o in doc.Objects)
    with _Capture() as cap:
        refused = OPS.create_fill(links, order=3)
    doc.recompute()
    created = sorted(set(o.Name for o in doc.Objects) - before)
    checks.append("no fallback: console %s"
                  % " | ".join(m.strip() for m in cap.errors)[:200])
    check(refused is None,
          "order 3 was accepted without a fallback: %r" % (refused,), errors)
    check(not created, "the refused fill created %r" % (created,), errors)

    # 2. the fallback selected: built at order 0, and said so by name.
    before = set(o.Name for o in doc.Objects)
    with _Capture() as cap:
        fallback = OPS.create_fill(links, order=3, fallback_order=0)
    doc.recompute()
    created = sorted(set(o.Name for o in doc.Objects) - before)
    checks.append("with the fallback: console %s"
                  % " | ".join(m.strip() for m in cap.messages)[:300])
    check(fallback is not None, "the selected C0 fallback did not build",
          errors)
    if fallback is None:
        return {"pass": not errors, "checks": checks, "errors": errors}
    check(len(created) == 1, "the fallback created %r" % (created,), errors)
    check(list(fallback.BoundaryOrder or []) == [0] * len(links),
          "the fallback fill is not at order 0: %r"
          % (list(fallback.BoundaryOrder or []),), errors)
    check(bool(fallback.Shape.Faces) and fallback.Shape.isValid(),
          "the fallback fill is not a valid shape", errors)
    check(any("fallback" in m for m in cap.messages),
          "the fallback was not reported by name: %r" % (cap.messages,), errors)
    return {"pass": not errors, "checks": checks, "errors": errors}
