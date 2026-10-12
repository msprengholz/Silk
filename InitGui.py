#    This file is part of Silk
#    (c) Edward Mills 2016-2017
#    edwardvmills@gmail.com
#	
#    NURBS Surface modeling tools focused on low degree and seam continuity (FreeCAD Workbench) 
#
#    Silk is free software: you can redistribute it and/or modify
#    it under the terms of the GNU General Public License as published by
#    the Free Software Foundation, either version 3 of the License, or
#    (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU General Public License for more details.
#
#    You should have received a copy of the GNU General Public License
#    along with this program.  If not, see <http://www.gnu.org/licenses/>.

import FreeCAD
import sys
import os

# Add test directory to Python path for test discovery
import Silk_dummy
path_Silk = os.path.dirname(Silk_dummy.__file__)
test_path = os.path.join(path_Silk, "Tests")
if test_path not in sys.path:
    sys.path.insert(0, test_path)


class Silk (Workbench):
	"""
	# Visible commands (ticket #50)

	These live as CLASS ATTRIBUTES, not module-level globals, and must
	stay that way. FreeCAD loads a workbench's InitGui.py by exec'ing
	it into the __main__ namespace and then STRIPPING the names the
	file defined back out of it -- the registered class's methods keep
	__main__ as their globals, so a module-level constant referenced
	from Initialize() raises NameError at startup (this file crashed
	FreeCAD's workbench load that way). Class attributes travel with
	the class object and survive the strip. Nothing else in this file
	may reference a module-level name from a method.

	Everything below decides only what the user SEES. Every import in
	Initialize() stays, because old documents keep their proxies in the
	legacy modules and those modules must be importable when a document
	is opened:

	  Silk_2Boundaries.FCStd                -> ArachNURBS
	  Silk_2BoundariesAndControlGrids.FCStd -> ArachNURBS + SilkWorkflow
	  Silk_Workflow.FCStd                   -> SilkPatch44 / SilkBlend / SilkEdge
	  Silk_Corner2x2.FCStd                  -> SilkEdge / SilkPatch / SilkBlend / SilkCorner

	Dropping a name from the lists below neither unregisters its
	command nor unloads its module, so documents keep restoring
	exactly as before. Retiring the legacy modules themselves is a
	separate track.
	"""

	# The workflow triad -- one command per process step: Edge -> Patch -> Blend
	WORKFLOW_COMMANDS = ["Silk_CreateEdge", "Silk_CreatePatch", "Silk_CreateBlend"]

	# The task panel
	GUIDE_COMMANDS = ["Silk_Guide"]

	# Development helper (hot reload)
	DEV_COMMANDS = ["Reload_Silk"]

	# Every command the workbench offers the user, in workflow order
	VISIBLE_COMMANDS = WORKFLOW_COMMANDS + GUIDE_COMMANDS + DEV_COMMANDS

	# Silk -> Workflow / Guide / Dev. appendMenu takes a LIST as its
	# first argument, where every entry after the first one is a level
	# of submenu.
	MENU_STRUCTURE = [
		(["Silk", "Workflow"], WORKFLOW_COMMANDS),
		(["Silk", "Guide"], GUIDE_COMMANDS),
		(["Silk", "Dev"], DEV_COMMANDS),
	]

	# One flat toolbar. "Separator" is a valid entry in a toolbar list
	# and renders as a toolbar separator.
	TOOLBAR_NAME = "Silk Commands"
	TOOLBAR_STRUCTURE = (WORKFLOW_COMMANDS + ["Separator"]
	                     + GUIDE_COMMANDS + ["Separator"]
	                     + DEV_COMMANDS)

	def __init__(self):
		self.__class__.Icon = FreeCAD.getUserAppDataDir()+"Mod" + "/Silk/Resources/Icons/Silk.svg"
		self.__class__.MenuText = "Silk"
		self.__class__.ToolTip = "NURBS Surface modeling tools focused on low degree and seam continuity "

	def Initialize(self):
		"This function is executed when FreeCAD starts"
		import ArachNURBS
		import ControlPoly4
		import CubicCurve_4
		import Point_onCurve
		import BoundarySpline
		import SilkEdge
		import ControlPoly4_segment
		import ControlGrid44
		import ControlGrid44_Rotate
		import ControlGrid44_flow
		import CubicSurface_44
		import ControlGrid44_EdgeSegment
		import ControlGrid44_2EdgeSegments
		import ControlPoly6
		import CubicCurve_6
		import ControlGrid66
		import CubicSurface_66
		import ControlGrid64
		import CubicSurface_64
		import ControlGrid64_2Grid44
		import ControlGrid64_3_1Grid44
		import ControlGrid64_normal
		import ControlGrid64_Surf44
		import SubGrid33_2Grid64
		import ControlGrid66_4Sub
		import SubGrid63_2Surf64
		import ControlGridNStar66
		import CubicNStarSurface_NStar66
		import StarTrim_CubicNStar
		import SilkPose
		import SilkPatch
		import SilkBlend
		import SilkWorkflow
		import Reload_Silk
		import SilkTaskPanel

		# Only the five visible commands, in their three groups. All of
		# them are registered by the imports above. Referenced through
		# `self` (class attributes) -- never as module-level globals:
		# see the class docstring for why.
		self.list = list(self.VISIBLE_COMMANDS)

		self.appendToolbar(self.TOOLBAR_NAME, list(self.TOOLBAR_STRUCTURE))
		for menu_path, commands in self.MENU_STRUCTURE:
			self.appendMenu(list(menu_path), list(commands))

	def Activated(self):
		"This function is executed when the workbench is activated"
		return

	def Deactivated(self):
		"This function is executed when the workbench is deactivated"
		return

	def ContextMenu(self, recipient):
		"This is executed whenever the user right-clicks on screen"
		# "recipient" will be either "view" or "tree"
		self.appendContextMenu("My commands",self.list) # add commands to the context menu

	def GetClassName(self): 
		# this function is mandatory if this is a full python workbench
		return "Gui::PythonWorkbench"
       
FreeCAD.Gui.addWorkbench(Silk())




