"""
SilkEdge — single FeaturePython.
Sketch(es) in → 4 poles out → cubic curve + polygon for display.
Sketches linked via Sketches property (a Part::FeaturePython cannot nest at
object level; the GUI tree groups them under the Edge via EdgeViewProvider.claimChildren, #52).
Display toggles: ShowCurve, ShowPolygon
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
    def __init__(self, obj, sketches):
        latest_version = "0.01"

        obj.addProperty("App::PropertyLinkList", "Sketches", "C1 - Inputs",
                        "source sketches").Sketches = sketches
        obj.addProperty("App::PropertyFloat", "tolerance", "C1 - Inputs",
                        "point-to-point connection tolerance").tolerance = AN.default_tol
        obj.addProperty("App::PropertyBool", "reverse", "C1 - Inputs",
                        "reverse the pole sequence").reverse = False
        obj.addProperty("App::PropertyBool", "ShowCurve", "S1 - Display",
                        "show the cubic curve").ShowCurve = True
        obj.addProperty("App::PropertyBool", "ShowPolygon", "S1 - Display",
                        "show the control polygon").ShowPolygon = True
        obj.addProperty("App::PropertyVectorList", "Poles", "C2 - Outputs", "Poles").Poles
        obj.addProperty("App::PropertyFloatList", "Weights", "C2 - Outputs", "Weights").Weights = [1.0] * 4
        obj.addProperty("Part::PropertyGeometryList", "Legs", "C2 - Outputs", "control segments").Legs
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
        self.execute(obj)

    def onDocumentRestored(self, obj):
        self.execute(obj)

    def onChanged(self, fp, prop):
        if prop in ("ShowCurve", "ShowPolygon", "reverse"):
            if 'Restore' not in fp.State:
                self.execute(fp)

    def execute(self, fp):
        if 'Restore' in fp.State:
            return

        sketches = fp.Sketches
        if not sketches:
            return

        if len(sketches) >= 2:
            # 2N mode — two sketches (each with circle + line)
            from ArachNURBS import ControlPoly4_2N
            dummy = FreeCAD.ActiveDocument.addObject("Part::FeaturePython", "_edge_tmp")
            ControlPoly4_2N(dummy, sketches[0], sketches[1])
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
            sketch = sketches[0]
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


class EdgeViewProvider:
    def __init__(self, vobj):
        vobj.Proxy = self

    def getIcon(self):
        return iconPath

    def attach(self, vobj):
        self.ViewObject = vobj
        self.Object = vobj.Object

    def claimChildren(self):
        """Ticket #52: group this Edge's sketches under it in the tree.

        FreeCAD renders tree parent-child through the view provider's
        claimChildren (DocumentModel/Tree in the 1.x core), not through
        document-level grouping -- the datas-level Sketches link list is
        unchanged, so the Edge/Patch identity model is untouched. Only the
        Edge claims: an edge owns 1-2 sketches, while an edge can serve two
        patches, so a Patch must never claim a sketch here."""
        return list(self.Object.Sketches or [])

    def updateData(self, obj, prop):
        return True

    def __getstate__(self):
        return None

    def __setstate__(self, state):
        return None


class CreateEdge:
    def GetResources(self):
        return {'Pixmap': iconPath, 'MenuText': 'Edge', 'ToolTip': tooltip}

    def Activated(self):
        sel = Gui.Selection.getSelectionEx()
        if len(sel) == 0:
            tipsDialog("Silk: Edge", moreInfo)
            return

        doc = FreeCAD.ActiveDocument
        selected = []
        for item in sel:
            obj = item.Object
            if obj.TypeId == "Sketcher::SketchObject":
                selected.append(obj)

        if not selected:
            FreeCAD.Console.PrintError("Silk: Edge requires at least one Sketch selected.\n")
            return

        edge = doc.addObject("Part::FeaturePython", "Edge")
        Edge(edge, selected)
        EdgeViewProvider(edge.ViewObject)
        edge.ViewObject.LineWidth = 2.00
        edge.ViewObject.LineColor = (0.00, 1.00, 0.00)
        edge.ViewObject.PointSize = 4.00
        edge.ViewObject.PointColor = (0.00, 0.33, 1.00)
        doc.recompute()
        FreeCAD.Console.PrintMessage(f"Edge created: {edge.Name}\n")

    def IsActive(self):
        return Gui is not None


Gui.addCommand("Silk_CreateEdge", CreateEdge())
