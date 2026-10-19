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
        if getattr(obj, "ViewObject", None) is not None:
            BoundarySplineViewProvider(obj.ViewObject)

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


class BoundarySplineViewProvider:
    """Tree provider for the BoundarySpline object.

    Ticket #11: the spline PARENTS the sketch that drives it, so the model
    tree reads spline -> sketch. The idiom is `EdgeViewProvider.claimChildren`
    (#52), reused rather than re-invented: FreeCAD renders tree nesting
    through the view provider, the datas-level `Sketch` link is untouched,
    and a sketch no spline points at stays at top level.

    `claimChildren` reads the live link, so it survives a reload with the
    rest of the view provider (`__getstate__` / `__setstate__` are what let
    FreeCAD rebuild it).

    #121 -- WHICH READING OF #11 WAS ASKED.  The ask was: *"the
    BoundarySpline object should own/parent the sketches that drive it
    (sketches in its group), so the model tree reads top-down: spline ->
    sketches"*.  Two readings hide in it -- an OWNERSHIP one (the object
    holds the sketch in its DATA) and a PARENTING one (the tree shows the
    sketch inside the spline) -- and the ask's own purpose clause names
    the second: the deliverable is that the MODEL TREE READS TOP-DOWN.
    The owner accepted that reading when the ticket was closed: *"Done
    and merged: `BoundarySpline` parents the sketch that drives it,
    reusing the existing claim-children idiom (#52) rather than a second
    grouping mechanism"* (#11).

    The ownership half is not absent either: `obj.Sketch` is an
    `App::PropertyLink`, so the spline DOES own its sketch in the data.
    What a `Part::FeaturePython` cannot do is hold children in the DATA
    TREE -- FreeCAD renders a feature's children through the view
    provider's `claimChildren` (the #52 idiom the Edge already uses), and
    a second grouping mechanism would be a second way of saying the same
    thing.  So the tree-level reading is the one that was asked, and it
    is the one that ships.
    """

    def __init__(self, vobj):
        vobj.Proxy = self

    def getIcon(self):
        return iconPath

    def attach(self, vobj):
        self.ViewObject = vobj
        self.Object = vobj.Object

    def claimChildren(self):
        sketch = getattr(self.Object, "Sketch", None)
        return [sketch] if sketch is not None else []

    def updateData(self, obj, prop):
        return True

    def __getstate__(self):
        return None

    def __setstate__(self, state):
        return None


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
                bs.ViewObject.LineWidth = 2.00
                bs.ViewObject.LineColor = (0.00, 1.00, 0.00)
                bs.ViewObject.PointSize = 4.00
                bs.ViewObject.PointColor = (0.00, 0.33, 1.00)
                doc.recompute()

    def IsActive(self):
        return Gui is not None


# #72: the `Gui.addCommand(...)` this module used to run at IMPORT time
# is gone. FreeCAD keeps one Python instance per registered command, and
# that instance pins this module's globals -- which pin ArachNURBS -- for
# the life of the process. Re-importing on every reload therefore minted a
# fresh ArachNURBS per run that could never be freed (~600 MB per run,
# measured). The command is retired (#50: LEGACY_NAMES 'none may reappear');
# old documents restore from the CLASS below, which is untouched.
