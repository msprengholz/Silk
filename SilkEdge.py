"""
SilkEdge — single FeaturePython group that replaces the old group+children approach.
Sketch(es) in → 4 poles out → cubic curve + grid for display.
Sketches are grouped as children in the tree.
Display toggles: ShowCurve, ShowGrid
"""

import FreeCAD
import Part
from FreeCAD import Gui
import ArachNURBS as AN
from popup import tipsDialog
import Silk_tooltips

tooltip = (Silk_tooltips.ControlPoly4_baseTip + Silk_tooltips.standardTipFooter)
moreInfo = (Silk_tooltips.ControlPoly4_baseTip + Silk_tooltips.ControlPoly4_moreInfo)

import os, Silk_dummy
path_Silk = os.path.dirname(Silk_dummy.__file__)
path_Silk_icons = os.path.join(path_Silk, "Resources", "Icons")
iconPath = path_Silk_icons + "/BoundarySpline.svg"


class Edge:
    def __init__(self, obj):
        """Create an Edge from selected sketch(es).
        Sketches are added as children. Poles computed from first sketch."""
        latest_version = "0.01"

        obj.addProperty("App::PropertyFloat", "tolerance", "C1 - Inputs",
                        "point-to-point connection tolerance").tolerance = AN.default_tol
        obj.addProperty("App::PropertyBool", "reverse", "C1 - Inputs",
                        "reverse the pole sequence").reverse = False
        obj.addProperty("App::PropertyBool", "ShowCurve", "S1 - Display",
                        "show the cubic curve").ShowCurve = True
        obj.addProperty("App::PropertyBool", "ShowPolygon", "S1 - Display",
                        "show the control polygon").ShowPolygon = True
        obj.addProperty("App::PropertyVectorList", "Poles", "C2 - Outputs", "Poles").Poles
        obj.addProperty("App::PropertyFloatList", "Weights", "C2 - Outputs", "Weights").Weights = [1.0, 1.0, 1.0, 1.0]
        obj.addProperty("Part::PropertyGeometryList", "Legs", "C2 - Outputs", "control segments").Legs
        obj.addProperty("Part::PropertyPartShape", "Shape", "C2 - Outputs", "Shape")
        obj.addProperty("App::PropertyString", "object_type", "C3 - Identifiers",
                        "workbench class").object_type = "Edge"
        obj.setEditorMode("object_type", 1)
        obj.addProperty("App::PropertyString", "object_version", "C3 - Identifiers",
                        "class version").object_version = latest_version
        obj.setEditorMode("object_version", 1)
        obj.addProperty("App::PropertyString", "internalName", "C3 - Identifiers",
                        "internal FreeCAD name").internalName = obj.Name
        obj.setEditorMode("internalName", 1)
        obj.Proxy = self

    def onDocumentRestored(self, obj):
        self.execute(obj)

    def onChanged(self, fp, prop):
        if prop in ("ShowCurve", "ShowPolygon", "reverse"):
            if 'Restore' not in fp.State:
                self.execute(fp)

    def execute(self, fp):
        if 'Restore' in fp.State:
            return

        # Read poles from the first sketch child, or keep existing poles
        children = fp.Group
        first_sketch = None
        for child in children:
            if hasattr(child, "TypeId") and child.TypeId == "Sketcher::SketchObject":
                first_sketch = child
                break

        if first_sketch:
            sketch = first_sketch
            geom = sketch.Geometry
            geom_count = len(geom)

            visible_count = 0
            visible_line_count = 0
            for i in range(geom_count):
                if not sketch.getConstruction(i):
                    visible_count += 1
                    if geom[i].TypeId == "Part::GeomLineSegment":
                        visible_line_count += 1

            if visible_line_count == 3 and visible_count == visible_line_count:
                from ArachNURBS import ControlPoly4_3L
                dummy = FreeCAD.ActiveDocument.addObject("Part::FeaturePython", "_edge_tmp")
                ControlPoly4_3L(dummy, sketch)
                dummy.recompute()
                if fp.reverse:
                    fp.Poles = list(reversed(dummy.Poles))
                    fp.Weights = list(reversed(dummy.Weights))
                else:
                    fp.Poles = dummy.Poles
                    fp.Weights = dummy.Weights
                fp.Legs = dummy.Legs
                FreeCAD.ActiveDocument.removeObject(dummy.Name)
            else:
                from ArachNURBS import ControlPoly4_FirstElement
                dummy = FreeCAD.ActiveDocument.addObject("Part::FeaturePython", "_edge_tmp")
                ControlPoly4_FirstElement(dummy, sketch)
                dummy.recompute()
                if fp.reverse:
                    fp.Poles = list(reversed(dummy.Poles))
                    fp.Weights = list(reversed(dummy.Weights))
                else:
                    fp.Poles = dummy.Poles
                    fp.Weights = dummy.Weights
                fp.Legs = dummy.Legs
                FreeCAD.ActiveDocument.removeObject(dummy.Name)

        # Build display shape from toggles
        shapes_to_compound = []
        if fp.ShowCurve and len(fp.Poles) == 4:
            curve = Part.BSplineCurve()
            curve.buildFromPoles(fp.Poles)
            shapes_to_compound.append(curve.toShape())
        if fp.ShowPolygon and fp.Legs:
            for leg in fp.Legs:
                if hasattr(leg, "toShape"):
                    shapes_to_compound.append(leg.toShape())
        if shapes_to_compound:
            try:
                fp.Shape = Part.Compound(shapes_to_compound)
            except Exception:
                if len(shapes_to_compound) == 1:
                    fp.Shape = shapes_to_compound[0]
                else:
                    fp.Shape = Part.Shape()
        else:
            fp.Shape = Part.Shape()


class CreateEdge:
    """GUI command — selected sketch(es) → Edge group."""

    def GetResources(self):
        return {'Pixmap': iconPath, 'MenuText': 'Edge', 'ToolTip': tooltip}

    def Activated(self):
        sel = Gui.Selection.getSelectionEx()
        if len(sel) == 0:
            tipsDialog("Silk: Edge", moreInfo)
            return

        doc = FreeCAD.ActiveDocument
        selected_sketches = []
        for item in sel:
            obj = item.Object
            if obj.TypeId == "Sketcher::SketchObject":
                selected_sketches.append(obj)

        if not selected_sketches:
            FreeCAD.Console.PrintError("Silk: Edge requires at least one Sketch selected.\n")
            return

        # Create Edge as a DocumentObjectGroupPython
        edge = doc.addObject("App::DocumentObjectGroupPython", "Edge")
        proxy = Edge(edge)

        # Add sketches as children
        for sk in selected_sketches:
            edge.addObject(sk)

        edge.ViewObject.Proxy = 0
        proxy.execute(edge)
        doc.recompute()
        FreeCAD.Console.PrintMessage(f"Edge created: {edge.Name}\n")

    def IsActive(self):
        return Gui is not None


Gui.addCommand("Silk_CreateEdge", CreateEdge())
