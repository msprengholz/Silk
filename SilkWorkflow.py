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
        before = _snapshot_objects(doc)
        group = doc.addObject("App::DocumentObjectGroupPython", "ControlGridPatch")
        group.ViewObject.Proxy = ControlGridPatchViewProvider()
        # ControlGrid44 consumes selected ControlPolys.
        try:
            Gui.Selection.clearSelection()
            for controlpoly in controlpolys:
                Gui.Selection.addSelection(controlpoly)
        except Exception:
            pass
        ok = Gui.runCommand("ControlGrid44")
        if ok is False:
            FreeCAD.Console.PrintError("SilkWorkflow: ControlGrid44 command failed.\n")
            return
        created_after_grid = _new_objects(doc, before)
        grid = _find_controlgrid(created_after_grid)
        if grid is None:
            FreeCAD.Console.PrintError(
                "SilkWorkflow: could not find ControlGrid output.\n"
            )
            return
        # CubicSurface_44 expects the ControlGrid selected.
        try:
            Gui.Selection.clearSelection()
            Gui.Selection.addSelection(grid)
        except Exception:
            pass
        ok = Gui.runCommand("CubicSurface_44")
        if ok is False:
            FreeCAD.Console.PrintError(
                "SilkWorkflow: CubicSurface_44 command failed.\n"
            )
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


# Add a custom icon to the ControlGridPatch group
class ControlGridPatchViewProvider:
    def getIcon(self):
        return gridIconPath


# Register the commands with FreeCAD GUI
if Gui:
    Gui.addCommand("Silk_CreateBoundarySpline", CreateBoundarySplineCommand())
    Gui.addCommand("Silk_CreateControlGridPatch", CreateControlGridPatchCommand())
