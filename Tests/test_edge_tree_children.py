"""
Edge tree children (ticket #52): a Sketch an Edge owns via its
`Sketches` property appears GROUPED under that Edge in the FreeCAD tree.

Mechanism: FreeCAD's tree renders a child-under-parent through the
parent's VIEWPROVIDER `claimChildren()` (DocumentModel::claimChildren /
Tree.cpp in the 1.x core) -- NOT through document-level grouping, which a
Part::FeaturePython cannot express ("FeaturePython doesn't nest" in
AGENTS.md is about the object/datas level, not the GUI tree). The Edge
view provider reports its sketches as tree children; the datas-level
Sketches link list is unchanged, so no Edge/Patch identity invariant
moves.

Only Edge claims sketches -- an Edge owns 1-2 of them. Patch does NOT
claim: an edge can serve two patches, so there is no unique owning
sketch at the patch level. A sketch not yet used by any Edge stays at
top level (claimed by no Edge).
"""

import FreeCAD
import Part

Vector = FreeCAD.Vector


def _line_sketch(doc, name, pts):
    sk = doc.addObject("Sketcher::SketchObject", name)
    for a, b in zip(pts, pts[1:]):
        sk.addGeometry(Part.LineSegment(Vector(*a), Vector(*b)))
    doc.recompute()
    return sk


def _claims(edge):
    """The tree children the Edge's view provider reports."""
    return list(edge.ViewObject.Proxy.claimChildren())


def _rect_pts():
    return [(0, 0, 0), (16.7, 0, 0), (33.3, 0, 0), (50, 0, 0)]


def test_edge_groups_its_sketches(doc):
    """A sketch an Edge points at appears under the Edge in the tree:
    the Edge's view provider claims exactly that sketch."""
    errors, checks = [], []
    from SilkWorkflowOps import create_edge

    sk = _line_sketch(doc, "Sketch", _rect_pts())
    edge = create_edge(sk, name="Edge")

    if edge is None:
        errors.append("create_edge returned None")
        return {"pass": False, "errors": errors, "checks": checks}
    children = _claims(edge)
    if children != [sk]:
        errors.append("Edge claims %s, want [%s]"
                      % ([o.Name for o in children], sk.Name))
    else:
        checks.append("Edge tree children == [%s]" % sk.Name)
    return {"pass": not errors, "errors": errors, "checks": checks}


def test_unused_sketch_stays_top_level(doc):
    """A sketch not referenced by any Edge is claimed by no Edge -- it
    stays at top level in the tree."""
    errors, checks = [], []
    from SilkWorkflowOps import create_edge

    used = _line_sketch(doc, "Used", _rect_pts())
    unused = doc.addObject("Sketcher::SketchObject", "Unused")
    doc.recompute()
    edge = create_edge(used, name="Edge")

    children = _claims(edge)
    if unused in children:
        errors.append("an Edge claims the unused sketch %s" % unused.Name)
    if len(children) != 1 or children[0] is not used:
        errors.append("Edge claims %s, want only the used sketch"
                      % [o.Name for o in children])
    else:
        checks.append("unused sketch %s claimed by no Edge (top level)"
                      % unused.Name)
    return {"pass": not errors, "errors": errors, "checks": checks}


def test_multiple_edges_claim_their_own_sketches(doc):
    """N edges, N sketches: each Edge claims only its OWN sketch."""
    errors, checks = [], []
    from SilkWorkflowOps import create_edge

    sk1 = _line_sketch(doc, "S1", [(0, 0, 0), (10, 0, 0), (20, 0, 0), (30, 0, 0)])
    sk2 = _line_sketch(doc, "S2", [(0, 0, 0), (10, 0, 0), (20, 0, 0), (30, 0, 0)])
    e1 = create_edge(sk1, name="E1")
    e2 = create_edge(sk2, name="E2")

    if _claims(e1) != [sk1]:
        errors.append("E1 claims %s, want [S1]" % [o.Name for o in _claims(e1)])
    if _claims(e2) != [sk2]:
        errors.append("E2 claims %s, want [S2]" % [o.Name for o in _claims(e2)])
    if not errors:
        checks.append("each Edge claims exactly its own sketch")
    return {"pass": not errors, "errors": errors, "checks": checks}


def test_patch_does_not_claim_edge_sketches(doc):
    """A Patch must NOT claim its edges' sketches: an edge can serve two
    patches, so there is no unique owning sketch at the patch level.
    The edges still each claim their own sketch."""
    errors, checks = [], []
    from Tests.test_seam_resolver import _square_patch

    patch = _square_patch(doc, "A")

    patch_vp = patch.ViewObject.Proxy
    if hasattr(patch_vp, "claimChildren"):
        patch_children = list(patch_vp.claimChildren())
        errors.append("Patch view provider claims tree children: %s"
                      % [o.Name for o in patch_children])
    else:
        checks.append("Patch view provider has no claimChildren (claims nothing)")

    # each of the patch's edges still owns exactly its own sketch
    for edge in patch.Edges:
        sk = edge.Sketches[0]
        if _claims(edge) != [sk]:
            errors.append("edge %s fails to claim its own sketch %s"
                          % (edge.Name, sk.Name))
    checks.append("each edge of the patch still claims its own sketch")
    return {"pass": not errors, "errors": errors, "checks": checks}


ALL_TESTS = [
    test_edge_groups_its_sketches,
    test_unused_sketch_stays_top_level,
    test_multiple_edges_claim_their_own_sketches,
    test_patch_does_not_claim_edge_sketches,
]
