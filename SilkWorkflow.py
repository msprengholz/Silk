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

import Silk_dummy

path_Silk = os.path.dirname(Silk_dummy.__file__)
path_Silk_icons = os.path.join(path_Silk, "Resources", "Icons")
iconPath = os.path.join(path_Silk_icons, "BoundarySpline.svg")


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


def _create_boundaryspline_group(doc):
	group = doc.addObject("App::DocumentObjectGroupPython", "BoundarySpline")
	try:
		group.ViewObject.Proxy = BoundarySplineViewProvider()
	except Exception:
		pass
	return group


class CreateBoundarySplineCommand:
	def GetResources(self):
		return {
			"Pixmap": iconPath,
			"MenuText": "Silk BoundarySpline",
			"ToolTip": "Create a BoundarySpline from sketches (scaffold).",
		}

	def IsActive(self):
		return Gui is not None

	def Activated(self):
		doc = FreeCAD.ActiveDocument
		if doc is None:
			FreeCAD.Console.PrintError("SilkWorkflow: no active document.\n")
			return
		before = _snapshot_objects(doc)
		group = _create_boundaryspline_group(doc)
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
		return iconPath


# Register the commands with FreeCAD GUI
if Gui:
	Gui.addCommand("Silk_CreateBoundarySpline", CreateBoundarySplineCommand())
