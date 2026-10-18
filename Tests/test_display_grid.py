"""
Display grid / compound composition (#108): `Shape` is geometry only, and
the control grid is drawn by the view provider's Coin node.

The owner's report -- "when a compound is created from patches and blends,
only the surface is part of the compound, but not the control grid" --
was exactly backwards from the geometry contract: the grid WAS in `Shape`,
so every compound built from Silk objects came out polluted with loose
grid edges. These tests pin the fix:

  * a Part::Compound assembled from the whole Demo 01 corpus holds
    surfaces and edge curves only -- every edge in it is a face-boundary
    edge or an Edge object's cubic curve, while the corpus still draws
    thousands of grid legs;
  * each object's grid is a Coin node under the view provider, and
    ShowGrid flips the NODE without touching `Shape`;
  * the grid path is a silent no-op headless (no ViewObject / no pivy).

No continuity label is asserted anywhere in this module.
"""

# --- manual tier ------------------------------------------------------
# This module's subject is an end-to-end rebuild / GUI drive /
# measurement sweep, so it is NOT in the default (fast) tier. Run it
# with `python3 Tests/run_all.py --manual` (or by name as a filter);
# Tests/test_manual_tier.py asserts it stays importable. See suite.py.
MANUAL = True

import FreeCAD
import Part

import SilkMachinery
import Tests.demo01_fixture_model as MODEL


def _grid_node(obj):
    """The Coin switch the view provider draws the grid with, or None."""
    vobj = getattr(obj, "ViewObject", None)
    proxy = getattr(vobj, "Proxy", None) if vobj is not None else None
    return getattr(proxy, "_silk_grid_node", None)


def _which_child(obj):
    node = _grid_node(obj)
    return None if node is None else node.whichChild.getValue()


def _grid_point_count(node):
    """How many coordinates the Coin grid node's drawing holds (0 when
    there is no drawing / no pivy)."""
    if node is None:
        return 0
    try:
        from pivy import coin
    except Exception:
        return 0
    total = [0]

    def walk(n):
        if isinstance(n, coin.SoCoordinate3):
            total[0] += n.point.getNum()
        try:
            for i in range(n.getNumChildren()):
                walk(n.getChild(i))
        except Exception:
            pass

    walk(node)
    return total[0]


def _corpus(result):
    return (list(result["edges"].values())
            + list(result["patches"].values())
            + list(result["blends"].values())
            + list(result["corners"].values()))


def test_silk_compound_carries_geometry_only(doc):
    """The whole Demo 01 corpus (12 Edges / 5 Patches / 8 Blends / 4
    corners) in one Part::Compound: every edge in it is a face-boundary
    edge or an Edge object's cubic curve. The control grids -- which the
    corpus really does draw -- are NOT in the compound.

    Pinned against the same surfaces re-composed from `.Faces`, so a face's
    own boundary edges are never mistaken for a leak: a bare
    `len(Shape.Edges)` would not distinguish them."""
    errors, checks = [], []
    result = MODEL.build(doc)
    if result["problems"]:
        errors.append("fixture build refused: %s" % result["problems"])
        return {"pass": False, "errors": errors, "checks": checks}
    objs = _corpus(result)
    shapes = [o.Shape for o in objs if not o.Shape.isNull()]
    comp = Part.makeCompound(shapes)

    face_boundary = sum(len(f.Edges) for f in comp.Faces)
    curve_edges = sum(len(o.Shape.Edges) for o in objs
                      if o.object_type == "Edge")
    grid_legs = sum(len(getattr(o, "Legs", None) or []) for o in objs)
    checks.append("corpus: %d objects, %d faces, %d edges, %d grid legs drawn"
                  % (len(objs), len(comp.Faces), len(comp.Edges), grid_legs))

    if len(objs) != 29:
        errors.append("corpus has %d objects, want 29 (12+5+8+4)" % len(objs))
    if grid_legs <= 0:
        errors.append("fixture draws no grid legs -- the test proves nothing")
    if len(comp.Edges) != face_boundary + curve_edges:
        errors.append(
            "compound carries %d edges, want %d face-boundary + %d edge "
            "curves = %d: loose grid edges are back in Shape"
            % (len(comp.Edges), face_boundary, curve_edges,
               face_boundary + curve_edges))
    else:
        checks.append("compound: %d edges == %d face-boundary + %d curves "
                      "(no loose grid edges)"
                      % (len(comp.Edges), face_boundary, curve_edges))

    # per object: a surface object's Shape is its faces and nothing else
    for o in objs:
        s = o.Shape
        if s is None or s.isNull():
            errors.append("%s %s: empty Shape" % (o.object_type, o.Name))
            continue
        if o.object_type == "Edge":
            if len(s.Faces) or len(s.Edges) != 1:
                errors.append("Edge %s: Shape is %d faces / %d edges, want "
                              "0 / 1 (the cubic curve only)"
                              % (o.Name, len(s.Faces), len(s.Edges)))
            continue
        boundary = sum(len(f.Edges) for f in s.Faces)
        if not s.Faces:
            errors.append("%s %s: Shape has no face" % (o.object_type, o.Name))
        elif len(s.Edges) != boundary:
            errors.append("%s %s: Shape carries %d edges, %d are face "
                          "boundaries (loose grid edges)"
                          % (o.object_type, o.Name, len(s.Edges), boundary))
    return {"pass": not errors, "errors": errors, "checks": checks}


def test_grid_is_a_coin_node_not_geometry(doc):
    """Every corpus object draws its grid with a Coin node under its view
    provider, and each node carries a drawing (the grid the object
    stashes). `Shape` is untouched by ShowGrid: the toggle flips the node
    (whichChild 0 -> -1), never the geometry."""
    from SilkWorkflowOps import create_edge

    errors, checks = [], []
    sk = doc.addObject("Sketcher::SketchObject", "Sk")
    for a, b in (((0, 0, 0), (10, 0, 0)), ((10, 0, 0), (10, 10, 0)),
                 ((10, 10, 0), (0, 10, 0))):
        sk.addGeometry(Part.LineSegment(FreeCAD.Vector(*a), FreeCAD.Vector(*b)))
    doc.recompute()
    edge = create_edge(sk, name="Edge")
    if edge is None:
        errors.append("create_edge returned None")
        return {"pass": False, "errors": errors, "checks": checks}

    node = _grid_node(edge)
    expected_points = 2 * len(edge.Legs or [])
    if node is None:
        errors.append("Edge has no Coin grid node")
    elif _grid_point_count(node) != expected_points:
        errors.append("Edge grid node draws %d coordinates, want 2 x %d legs "
                      "= %d" % (_grid_point_count(node), len(edge.Legs or []),
                                expected_points))
    else:
        checks.append("Edge grid node: switch drawing %d coordinates "
                      "(2 per leg)" % expected_points)
    if _which_child(edge) != 0:
        errors.append("ShowPolygon=True: grid node whichChild=%r, want 0"
                      % _which_child(edge))

    before = (len(edge.Shape.Faces), len(edge.Shape.Edges))
    edge.ShowPolygon = False
    doc.recompute()
    after = (len(edge.Shape.Faces), len(edge.Shape.Edges))
    if after != before:
        errors.append("ShowPolygon changed Shape: %r -> %r" % (before, after))
    elif _which_child(edge) != -1:
        errors.append("ShowPolygon=False: grid node whichChild=%r, want -1"
                      % _which_child(edge))
    else:
        checks.append("ShowPolygon=False: node hidden (%r), Shape unchanged %r"
                      % (_which_child(edge), after))
    return {"pass": not errors, "errors": errors, "checks": checks}


def test_grid_display_is_headless_safe(doc):
    """The grid path is a silent no-op with no ViewObject and no pivy:
    no node, no error. `grid_coin_node` returns None for an empty leg set,
    and `set_grid_display` returns None for a None ViewObject -- the
    headless contract, exercised directly because a real GUI always has a
    ViewObject."""
    errors, checks = [], []

    class _Proxy:
        pass

    if SilkMachinery.grid_coin_node([]) is not None:
        errors.append("grid_coin_node([]) built a node")
    else:
        checks.append("grid_coin_node([]) -> None")

    proxy = _Proxy()
    out = SilkMachinery.set_grid_display(
        proxy, None, [Part.LineSegment(FreeCAD.Vector(0, 0, 0),
                                       FreeCAD.Vector(1, 0, 0))],
        True, (1.0, 0.0, 0.0), 2.0)
    if out is not None:
        errors.append("set_grid_display(vobj=None) returned %r, want None" % out)
    elif getattr(proxy, "_silk_grid_node", None) is not None:
        errors.append("set_grid_display(vobj=None) still stored a node")
    else:
        checks.append("set_grid_display(vobj=None) -> None, no node, no error")

    # the object-level entry point (updateData) must survive a missing
    # ViewObject too: that is the path a document recompute reaches when no
    # GUI is attached
    from SilkPatch import PatchViewProvider
    vp = PatchViewProvider.__new__(PatchViewProvider)
    bare = doc.addObject("App::FeaturePython", "NoView")
    try:
        vp.updateData(bare, "Legs")
    except Exception as e:
        errors.append("PatchViewProvider.updateData without a ViewObject "
                      "raised %r" % (e,))
    else:
        checks.append("PatchViewProvider.updateData without a ViewObject: "
                      "no-op")
    return {"pass": not errors, "errors": errors, "checks": checks}


ALL_TESTS = [
    test_silk_compound_carries_geometry_only,
    test_grid_is_a_coin_node_not_geometry,
    test_grid_display_is_headless_safe,
]
