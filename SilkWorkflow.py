#    This file is part of Silk
#    (c) 2025
#
#    NURBS Surface modeling tools focused on low degree and seam continuity (FreeCAD Workbench)
#
#    Workflow scaffolding that bundles existing Silk commands without modifying
#    the core library.

import os

import FreeCAD
from FreeCAD import Gui

import ArachNURBS as AN

# get icons
import Silk_dummy

path_Silk = os.path.dirname(Silk_dummy.__file__)
path_Silk_icons = os.path.join(path_Silk, "Resources", "Icons")
splineIconPath = os.path.join(path_Silk_icons, "BoundarySpline.svg")
gridIconPath = os.path.join(path_Silk_icons, "ControlGridPatch.svg")


def _snapshot_objects(doc):
    # runCommand does not return created objects; snapshot to diff later.
    return set(doc.Objects) if doc else set()


def _new_objects(doc, before):
    after = set(doc.Objects) if doc else set()
    return [obj for obj in after if obj not in before]


def _find_controlpoly(objs):
    # Find ControlPoly output so CubicCurve_4 gets the right input.
    for obj in objs:
        obj_type = getattr(obj, "object_type", "")
        if obj_type.startswith("ControlPoly4"):
            return obj
        if hasattr(obj, "Poles"):
            return obj
    return None


def _find_controlgrid(objs):
    # Find ControlGrid output so CubicSurface_44 gets the right input.
    for obj in objs:
        obj_type = getattr(obj, "object_type", "")
        if obj_type.startswith("ControlGrid44"):
            return obj
        if hasattr(obj, "Poles"):
            return obj
    return None


def _find_boundary_controlpoly(boundary):
    for obj in getattr(boundary, "Group", []):
        obj_type = getattr(obj, "object_type", "")
        if obj_type.startswith("ControlPoly4"):
            return obj
        if hasattr(obj, "Poles"):
            return obj
    return None


class CreateBoundarySplineCommand:
    def GetResources(self):
        return {
            "Pixmap": splineIconPath,
            "MenuText": "Silk BoundarySpline",
            "ToolTip": "Create a BoundarySpline from sketches.",
        }

    def IsActive(self):
        return Gui is not None

    def Activated(self):
        doc = FreeCAD.ActiveDocument
        if doc is None:
            FreeCAD.Console.PrintError("SilkWorkflow: no active document.\n")
            return
        before = _snapshot_objects(doc)
        # create BoundarySpline group to hold outputs
        group = doc.addObject("App::DocumentObjectGroupPython", "BoundarySpline")
        group.ViewObject.Proxy = BoundarySplineViewProvider()  # assign custom icon
        ok = Gui.runCommand("ControlPoly4")
        if ok is False:
            FreeCAD.Console.PrintError("SilkWorkflow: ControlPoly4 command failed.\n")
            return
        created_after_cp = _new_objects(doc, before)
        controlpoly = _find_controlpoly(created_after_cp)
        if controlpoly is None:
            FreeCAD.Console.PrintError(
                "SilkWorkflow: could not find ControlPoly4 output.\n"
            )
            return
        # CubicCurve_4 uses selection; override to ensure correct input.
        try:
            Gui.Selection.clearSelection()
            Gui.Selection.addSelection(controlpoly)
        except Exception:
            pass
        ok = Gui.runCommand("CubicCurve_4")
        if ok is False:
            FreeCAD.Console.PrintError("SilkWorkflow: CubicCurve_4 command failed.\n")
            return
        created = _new_objects(doc, before)
        for obj in created:
            if obj is group:
                continue
            try:
                group.addObject(obj)
            except Exception:
                pass
        doc.recompute()


# Add a custom icon to the BoundarySpline group
class BoundarySplineViewProvider:
    def getIcon(self):
        return splineIconPath


class CreateControlGridPatchCommand:
    def GetResources(self):
        return {
            "Pixmap": gridIconPath,
            "MenuText": "Silk ControlGridPatch",
            "ToolTip": "Create a ControlGrid patch from 3-4 BoundarySplines.",
        }

    def IsActive(self):
        return Gui is not None

    def Activated(self):
        doc = FreeCAD.ActiveDocument
        if doc is None:
            FreeCAD.Console.PrintError("SilkWorkflow: no active document.\n")
            return
        selection = Gui.Selection.getSelection()
        if len(selection) not in (3, 4):
            FreeCAD.Console.PrintError("SilkWorkflow: select 3 or 4 BoundarySplines.\n")
            return
        # Resolve BoundarySpline groups to their ControlPoly children.
        controlpolys = []
        for boundary in selection:
            controlpoly = _find_boundary_controlpoly(boundary)
            if controlpoly is None:
                FreeCAD.Console.PrintError(
                    "SilkWorkflow: BoundarySpline missing ControlPoly4 output.\n"
                )
                return
            controlpolys.append(controlpoly)
        group = doc.addObject("App::DocumentObjectGroupPython", "ControlGridPatch")
        group.ViewObject.Proxy = ControlGridPatchViewProvider()
        if len(controlpolys) == 4:
            grid = doc.addObject("Part::FeaturePython", "ControlGrid44_4")
            AN.ControlGrid44_4(
                grid,
                controlpolys[0],
                controlpolys[1],
                controlpolys[2],
                controlpolys[3],
            )
        else:
            grid = doc.addObject("Part::FeaturePython", "ControlGrid44_3")
            AN.ControlGrid44_3(
                grid,
                controlpolys[0],
                controlpolys[1],
                controlpolys[2],
            )
        # Set visual properties for grid and surface as done in the GUI commands.
        grid.ViewObject.Proxy = 0
        grid.ViewObject.LineWidth = 1.00
        grid.ViewObject.LineColor = (0.67, 1.00, 1.00)
        grid.ViewObject.PointSize = 4.00
        grid.ViewObject.PointColor = (0.00, 0.33, 1.00)
        surf = doc.addObject("Part::FeaturePython", "CubicSurface_44")
        # Create CubicSurface_44 from ControlGrid44 (TODO: could also be done via GUI command)
        AN.CubicSurface_44(surf, grid)
        surf.ViewObject.Proxy = 0
        surf.ViewObject.DisplayMode = "Shaded"
        surf.ViewObject.ShapeColor = (0.33, 0.67, 1.00)
        group.addObject(grid)
        group.addObject(surf)
        doc.recompute()


# Add a custom icon to the ControlGridPatch group
class ControlGridPatchViewProvider:
    def getIcon(self):
        return gridIconPath


# Register the commands with FreeCAD GUI
if Gui:
    Gui.addCommand("Silk_CreateBoundarySpline", CreateBoundarySplineCommand())
    Gui.addCommand("Silk_CreateControlGridPatch", CreateControlGridPatchCommand())
