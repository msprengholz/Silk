#    This file is part of Silk
#    (c) 2025
#
#    NURBS Surface modeling tools focused on low degree and seam continuity (FreeCAD Workbench)
#
#    BoundarySpline — single FeaturePython that replaces the old group+children approach.
#    One sketch in → 4 poles out → cubic curve for display.

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


class BoundarySpline:
    def __init__(self, obj, sketch):
        """Create a BoundarySpline from a sketch (3L or FirstElement)."""
        latest_version = "0.01"

        obj.addProperty("App::PropertyLink", "Sketch", "C1 - Inputs", "source sketch").Sketch = sketch
        obj.addProperty("App::PropertyFloat", "tolerance", "C1 - Inputs",
                        "point-to-point connection tolerance").tolerance = AN.default_tol
        obj.addProperty("App::PropertyBool", "reverse", "C1 - Inputs",
                        "reverse the pole sequence").reverse = False
        obj.addProperty("App::PropertyVectorList", "Poles", "C2 - Outputs", "Poles").Poles
        obj.addProperty("App::PropertyFloatList", "Weights", "C2 - Outputs", "Weights").Weights = [1.0, 1.0, 1.0, 1.0]
        obj.addProperty("Part::PropertyGeometryList", "Legs", "C2 - Outputs", "control segments").Legs
        obj.addProperty("App::PropertyString", "object_type", "C3 - Identifiers",
                        "the workbench class used to create this object").object_type = "BoundarySpline"
        obj.setEditorMode("object_type", 1)
        obj.addProperty("App::PropertyString", "object_version", "C3 - Identifiers",
                        "the class version of this object").object_version = latest_version
        obj.setEditorMode("object_version", 1)
        obj.addProperty("App::PropertyString", "internalName", "C3 - Identifiers",
                        "the permanent internal FreeCAD name for this object").internalName = obj.Name
        obj.setEditorMode("internalName", 1)
        obj.Proxy = self

    def onDocumentRestored(self, obj):
        obj.recompute()

    def onChanged(self, fp, prop):
        if prop == "reverse":
            fp.recompute()

    def execute(self, fp):
        if 'Restore' in fp.State:
            return

        sketch = fp.Sketch
        geom = sketch.Geometry
        geom_count = geom.__len__()

        visible_count = 0
        visible_line_count = 0
        for i in range(geom_count):
            if not sketch.getConstruction(i):
                visible_count += 1
                if geom[i].TypeId == "Part::GeomLineSegment":
                    visible_line_count += 1

        if visible_line_count == 3 and visible_count == visible_line_count:
            from ArachNURBS import ControlPoly4_3L
            dummy = FreeCAD.ActiveDocument.addObject("Part::FeaturePython", "_bs_tmp")
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
            dummy = FreeCAD.ActiveDocument.addObject("Part::FeaturePython", "_bs_tmp")
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

        if len(fp.Poles) == 4:
            curve = Part.BSplineCurve()
            curve.buildFromPoles(fp.Poles)
            fp.Shape = curve.toShape()
        else:
            fp.Shape = Part.Shape(fp.Legs)


class CreateBoundarySpline:
    """GUI command — selected sketch → BoundarySpline."""

    def GetResources(self):
        return {'Pixmap': iconPath, 'MenuText': 'BoundarySpline', 'ToolTip': tooltip}

    def Activated(self):
        sel = Gui.Selection.getSelectionEx()
        if len(sel) == 0:
            tipsDialog("Silk: BoundarySpline", moreInfo)
            return

        doc = FreeCAD.ActiveDocument
        for item in sel:
            obj = item.Object
            if obj.TypeId == "Sketcher::SketchObject":
                bs = doc.addObject("Part::FeaturePython", "BoundarySpline")
                BoundarySpline(bs, obj)
                bs.ViewObject.Proxy = 0
                bs.ViewObject.LineWidth = 2.00
                bs.ViewObject.LineColor = (0.00, 1.00, 0.00)
                bs.ViewObject.PointSize = 4.00
                bs.ViewObject.PointColor = (0.00, 0.33, 1.00)
                doc.recompute()

    def IsActive(self):
        return Gui is not None


Gui.addCommand("BoundarySpline", CreateBoundarySpline())
