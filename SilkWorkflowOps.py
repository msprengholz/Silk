"""
SilkWorkflowOps — the single construction path for workflow objects.

Thin GUI-free wrappers over the existing FeaturePython constructors
(spec #16 / #14): tests and the future wizard call these functions,
never the constructors or Gui.runCommand. No existing module is modified.

Ticket #18: create_edge. Ticket #19/#20: create_patch / create_blend.
Ticket #42: the ops layer creates ONLY the unified object types
(Edge / Patch / Blend) -- the legacy per-fill builders (Patch44,
Patch33) are gone; the classes survive in their modules as
old-document restore shims only.
"""

import FreeCAD

from SilkEdge import Edge, EdgeViewProvider
from SilkPatch import Patch, PatchViewProvider
from SilkBlend import Blend, BlendStripViewProvider


def create_edge(sketches, name="Edge"):
    """Create a SilkEdge from one or two ControlPoly4 sketches.

    addObject -> Edge constructor -> view provider -> recompute ->
    return the created object, so later steps can consume the result
    in one script. No selection, no commands, no dialogs.
    """
    doc = FreeCAD.ActiveDocument
    if not isinstance(sketches, (list, tuple)):
        sketches = [sketches]
    obj = doc.addObject("Part::FeaturePython", name)
    Edge(obj, list(sketches))
    EdgeViewProvider(obj.ViewObject)
    obj.ViewObject.LineWidth = 2.00
    obj.ViewObject.LineColor = (0.00, 1.00, 0.00)
    obj.ViewObject.PointSize = 4.00
    obj.ViewObject.PointColor = (0.00, 0.33, 1.00)
    doc.recompute()
    return obj


def create_patch(edges, name="Patch"):
    """Create the unified Patch (#37/#38/#42) from a variable-length
    Edges list.

    execute() selects the fill from the edge count: 4 edges -> the
    quad fill (#37), 3 edges -> the pointed fill (#38); other counts
    leave the object empty/valid. Mirrors create_edge (addObject ->
    constructor -> view provider -> recompute -> return). Renamed from
    create_patch_unified at the #42 retirement; the legacy per-fill
    create_patch (Patch44) / create_patch33 (Patch33) builders are
    gone -- direct construction of the legacy classes survives only
    for parity evidence and old-document restore.
    """
    doc = FreeCAD.ActiveDocument
    obj = doc.addObject("Part::FeaturePython", name)
    Patch(obj, list(edges))
    PatchViewProvider(obj.ViewObject)
    obj.ViewObject.LineWidth = 1.50
    obj.ViewObject.LineColor = (0.67, 1.00, 1.00)
    obj.ViewObject.PointSize = 4.00
    obj.ViewObject.PointColor = (0.00, 0.33, 1.00)
    doc.recompute()
    return obj


def create_blend(patch_a, patch_b, edge=None, name="Blend"):
    """Create the unified Blend (#39) joining two adjacent patches.

    The shared seam is auto-detected from the patches' corner poles
    (robust against degenerate pointed corners), or pinned geometrically
    from `edge`'s endpoint poles when given -- edge OBJECT identity is
    irrelevant, only the endpoint geometry is validated (both endpoints
    must sit on a corner pair of BOTH patches). A non-shared edge or a
    Blend fed as a patch refuses gracefully: empty valid object +
    console error, no crash. Mirrors the other ops (addObject ->
    constructor -> view provider -> recompute -> return).
    """
    doc = FreeCAD.ActiveDocument
    obj = doc.addObject("Part::FeaturePython", name)
    Blend(obj, patch_a, patch_b, edge)
    BlendStripViewProvider(obj.ViewObject)
    obj.ViewObject.LineWidth = 2.00
    obj.ViewObject.LineColor = (0.00, 1.00, 0.00)
    obj.ViewObject.PointSize = 5.00
    obj.ViewObject.DisplayMode = "Shaded"
    obj.ViewObject.ShapeColor = (0.00, 1.00, 0.00)
    obj.ViewObject.Transparency = 30
    doc.recompute()
    return obj


def create_corner_blend(strip0, strip1, strip2, strip3, name="CornerBlend"):
    """Create a CornerBlend filling the central region where 4 patches
    meet (#28). Takes the 4 ring BlendStrips in cyclic order; each
    strip's corner-end row feeds AN.ControlGrid66_4 + AN.CubicSurface_66.

    addObject -> CornerBlend constructor -> view provider -> recompute ->
    return the created object.
    """
    from SilkCorner import CornerBlend, CornerBlendViewProvider
    doc = FreeCAD.ActiveDocument
    obj = doc.addObject("Part::FeaturePython", name)
    CornerBlend(obj, strip0, strip1, strip2, strip3)
    CornerBlendViewProvider(obj.ViewObject)
    obj.ViewObject.LineWidth = 1.50
    obj.ViewObject.LineColor = (1.00, 0.67, 0.00)
    obj.ViewObject.PointSize = 4.00
    obj.ViewObject.DisplayMode = "Shaded"
    obj.ViewObject.ShapeColor = (1.00, 0.67, 0.00)
    obj.ViewObject.Transparency = 30
    doc.recompute()
    return obj
