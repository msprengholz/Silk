"""
SilkWorkflowOps — the single construction path for workflow objects.

Thin GUI-free wrappers over the existing FeaturePython constructors
(spec #16 / #14): tests and the future wizard call these functions,
never the constructors or Gui.runCommand. No existing module is modified.

Ticket #18: create_edge. Ticket #19: create_patch. Ticket #20:
create_blend.
"""

import FreeCAD

from SilkEdge import Edge, EdgeViewProvider
from SilkPatch44 import Patch44, Patch44ViewProvider
from SilkBlend import BlendStrip, BlendStripViewProvider


def create_edge(sketches, name="Edge"):
    """Create a SilkEdge from one or two ControlPoly4 sketches.

    addObject -> Edge constructor -> view provider -> recompute -> return
    the created object, so later steps can consume the result in one
    script. No selection, no commands, no dialogs.
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


def create_patch(edge0, edge1, edge2, edge3, name="Patch44"):
    """Create a Patch44 from 4 boundary edges in cyclic loop order.

    addObject -> Patch44 constructor -> view provider -> recompute ->
    return the created object.
    """
    doc = FreeCAD.ActiveDocument
    obj = doc.addObject("Part::FeaturePython", name)
    Patch44(obj, edge0, edge1, edge2, edge3)
    Patch44ViewProvider(obj.ViewObject)
    obj.ViewObject.LineWidth = 1.50
    obj.ViewObject.LineColor = (0.67, 1.00, 1.00)
    obj.ViewObject.PointSize = 4.00
    obj.ViewObject.PointColor = (0.00, 0.33, 1.00)
    doc.recompute()
    return obj


def create_blend(patch_a, patch_b, name="BlendStrip"):
    """Create a BlendStrip joining two adjacent Patch44 objects.

    The shared edge is auto-detected from the patches' corner poles
    (see SilkBlend). addObject -> BlendStrip constructor -> view
    provider -> recompute -> return the created object.
    """
    doc = FreeCAD.ActiveDocument
    obj = doc.addObject("Part::FeaturePython", name)
    BlendStrip(obj, patch_a, patch_b)
    BlendStripViewProvider(obj.ViewObject)
    obj.ViewObject.LineWidth = 2.00
    obj.ViewObject.LineColor = (0.00, 1.00, 0.00)
    obj.ViewObject.PointSize = 5.00
    obj.ViewObject.DisplayMode = "Shaded"
    obj.ViewObject.ShapeColor = (0.00, 1.00, 0.00)
    obj.ViewObject.Transparency = 30
    doc.recompute()
    return obj
