#    This file is part of Silk
#    (c) Edward Mills 2016-2024
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

from __future__ import division
import FreeCAD
import FreeCADGui as Gui
import Part

from popup import tipsDialog
import Silk_tooltips
import ArachNURBS as AN


BOUNDARY_TIP = """Create a BoundarySpline object by selecting either:
* one sketch (first element or 3 connected edges)
* two node sketches
* two Point_onCurve objects

The resulting BoundarySpline remains driven by the original sketches, exposes
Silk specific metadata, and stores an optional visualization BSpline."""

PATCH_TIP = """Create a SurfacePatch object from three or four BoundarySplines.
All selected inputs must share endpoints just like the classic ControlGrid tools."""


def _is_boundary(obj):
	return hasattr(obj, "SilkRole") and obj.SilkRole == "SilkBoundarySpline"


def _make_boundary_label(mode):
	return "BoundarySpline_{}".format(mode)


class SilkBoundarySpline(AN.ControlPoly4_3L,
						AN.ControlPoly4_FirstElement,
						AN.ControlPoly4_2N,
						AN.ControlPoly4_2P):
	def __init__(self, obj, mode, payload):
		self.boundary_mode = mode
		self._init_inputs(obj, payload)
		obj.addProperty("App::PropertyString",
						"SilkRole",
						"B1 - Boundary",
						"Silk workflow identifier").SilkRole = "SilkBoundarySpline"
		obj.addProperty("App::PropertyString",
						"BoundaryMode",
						"B1 - Boundary",
						"Input interpretation mode").BoundaryMode = mode
		obj.addProperty("App::PropertyBool",
						"ShowPreviewCurve",
						"B2 - Preview",
						"Overlay a cubic curve preview").ShowPreviewCurve = True
		obj.addProperty("Part::PropertyPartShape",
						"PolyShape",
						"B3 - Cache",
						"Stored polyline shape").PolyShape = Part.Shape()
		obj.addProperty("Part::PropertyPartShape",
						"CurveShape",
						"B3 - Cache",
						"Stored cubic curve preview").CurveShape = Part.Shape()
		obj.addProperty("App::PropertyColor",
						"CurveColor",
						"B2 - Preview",
						"Preview curve display color").CurveColor = (1.0, 0.67, 0.0)
		obj.addProperty("App::PropertyColor",
						"PolyColor",
						"B2 - Preview",
						"Polyline display color").PolyColor = (0.0, 1.0, 1.0)
		obj.addProperty("App::PropertyString",
						"CreatorNote",
						"B1 - Boundary",
						"Free form comment about this boundary").CreatorNote = ""
		obj.Proxy = self

	def _init_inputs(self, obj, payload):
		if self.boundary_mode == '3L':
			AN.ControlPoly4_3L.__init__(self, obj, payload['Sketch'])
		elif self.boundary_mode == 'FirstElement':
			AN.ControlPoly4_FirstElement.__init__(self, obj, payload['Sketch'])
		elif self.boundary_mode == '2N':
			AN.ControlPoly4_2N.__init__(self, obj, payload['Sketch0'], payload['Sketch1'])
		elif self.boundary_mode == '2P':
			AN.ControlPoly4_2P.__init__(self, obj, payload['Point0'], payload['Point1'])
		else:
			raise ValueError("Unsupported BoundarySpline mode {}".format(self.boundary_mode))

	def onChanged(self, obj, prop):
		if self.boundary_mode == '3L':
			AN.ControlPoly4_3L.onChanged(self, obj, prop)
		elif self.boundary_mode == 'FirstElement':
			AN.ControlPoly4_FirstElement.onChanged(self, obj, prop)
		elif self.boundary_mode == '2N':
			AN.ControlPoly4_2N.onChanged(self, obj, prop)
		elif self.boundary_mode == '2P':
			AN.ControlPoly4_2P.onChanged(self, obj, prop)

	def _update_display_shape(self, obj):
		poly_shape = Part.Shape(obj.Legs)
		obj.PolyShape = poly_shape
		if obj.ShowPreviewCurve:
			weighted = [[obj.Poles[i], obj.Weights[i]] for i in range(len(obj.Poles))]
			curve = AN.Bezier_Cubic_curve(weighted).toShape()
			obj.CurveShape = curve
			comp = Part.Compound([poly_shape, curve])
			obj.Shape = comp
		else:
			obj.CurveShape = Part.Shape()
			obj.Shape = poly_shape

	def execute(self, obj):
		if self.boundary_mode == '3L':
			AN.ControlPoly4_3L.execute(self, obj)
		elif self.boundary_mode == 'FirstElement':
			AN.ControlPoly4_FirstElement.execute(self, obj)
		elif self.boundary_mode == '2N':
			AN.ControlPoly4_2N.execute(self, obj)
		elif self.boundary_mode == '2P':
			AN.ControlPoly4_2P.execute(self, obj)
		self._update_display_shape(obj)


class SilkBoundaryViewProvider:
	def __init__(self, obj):
		obj.Proxy = self

	def attach(self, vobj):
		self.Object = vobj.Object

	def updateData(self, fp, prop):
		return

	def getDisplayModes(self, obj):
		return ["Default"]

	def getDefaultDisplayMode(self):
		return "Default"

	def setDisplayMode(self, mode):
		return mode

	def onDelete(self, feature, subelements):
		return True


class CreateBoundarySplineCommand:
	def GetResources(self):
		return {'Pixmap': '',
				'MenuText': 'Silk BoundarySpline',
				'ToolTip': BOUNDARY_TIP}

	def _interpret_selection(self):
		sel = Gui.Selection.getSelectionEx()
		if len(sel) == 0:
			return None

		if len(sel) == 1:
			obj = sel[0].Object
			if obj.TypeId == 'Sketcher::SketchObject':
				if obj.GeometryCount == 3:
					return ('3L', {'Sketch': obj})
				else:
					return ('FirstElement', {'Sketch': obj})
		if len(sel) == 2:
			if sel[0].Object.TypeId == 'Sketcher::SketchObject' and sel[1].Object.TypeId == 'Sketcher::SketchObject':
				return ('2N', {'Sketch0': sel[0].Object, 'Sketch1': sel[1].Object})
			try:
				if sel[0].Object.object_type == 'Point_onCurve' and sel[1].Object.object_type == 'Point_onCurve':
					return ('2P', {'Point0': sel[0].Object, 'Point1': sel[1].Object})
			except AttributeError:
				pass
		return None

	def Activated(self):
		data = self._interpret_selection()
		if not data:
			tipsDialog("Silk: BoundarySpline", BOUNDARY_TIP)
			return
		mode, payload = data
		doc = FreeCAD.ActiveDocument
		obj = doc.addObject("Part::FeaturePython", _make_boundary_label(mode))
		SilkBoundarySpline(obj, mode, payload)
		SilkBoundaryViewProvider(obj.ViewObject)
		obj.ViewObject.LineColor = obj.PolyColor
		doc.recompute()


class SilkSurfacePatch(AN.ControlGrid44_4):
	def __init__(self, obj, boundaries):
		self.boundaries = boundaries
		AN.ControlGrid44_4.__init__(self,
									obj,
									boundaries[0],
									boundaries[1],
									boundaries[2],
									boundaries[3])
		obj.addProperty("App::PropertyString",
						"SilkRole",
						"P1 - Patch",
						"Silk workflow identifier").SilkRole = "SilkSurfacePatch"
		obj.addProperty("App::PropertyBool",
						"ShowSurface",
						"P2 - Display",
						"Display the underlying cubic surface").ShowSurface = True
		obj.addProperty("App::PropertyBool",
						"ShowGrid",
						"P2 - Display",
						"Display the control grid").ShowGrid = True
		obj.addProperty("App::PropertyBool",
						"ReverseNormal",
						"P1 - Patch",
						"Flip the generated surface normal").ReverseNormal = False
		obj.addProperty("Part::PropertyPartShape",
						"GridShape",
						"P3 - Cache",
						"Cached control grid shape").GridShape = Part.Shape()
		obj.addProperty("Part::PropertyPartShape",
						"SurfaceShape",
						"P3 - Cache",
						"Cached cubic surface shape").SurfaceShape = Part.Shape()
		obj.Proxy = self

	def _build_surface_shape(self, obj):
		weights = obj.Weights
		poles = obj.Poles
		if len(poles) != 16:
			return Part.Shape()
		if obj.ReverseNormal:
			reordered = [
				[poles[3], weights[3]],
				[poles[2], weights[2]],
				[poles[1], weights[1]],
				[poles[0], weights[0]],
				[poles[7], weights[7]],
				[poles[6], weights[6]],
				[poles[5], weights[5]],
				[poles[4], weights[4]],
				[poles[11], weights[11]],
				[poles[10], weights[10]],
				[poles[9], weights[9]],
				[poles[8], weights[8]],
				[poles[15], weights[15]],
				[poles[14], weights[14]],
				[poles[13], weights[13]],
				[poles[12], weights[12]],
			]
		else:
			reordered = [[poles[i], weights[i]] for i in range(16)]
		return AN.Bezier_Bicubic_surf(reordered).toShape()

	def _update_shape(self, obj):
		grid_shape = Part.Shape(obj.Legs)
		obj.GridShape = grid_shape
		if obj.ShowSurface:
			obj.SurfaceShape = self._build_surface_shape(obj)
		else:
			obj.SurfaceShape = Part.Shape()
		shapes = []
		if obj.ShowGrid:
			shapes.append(grid_shape)
		if obj.ShowSurface and not obj.SurfaceShape.isNull():
			shapes.append(obj.SurfaceShape)
		if shapes:
			obj.Shape = Part.Compound(shapes) if len(shapes) > 1 else shapes[0]
		else:
			obj.Shape = Part.Shape()

	def onChanged(self, obj, prop):
		if prop == "reverse":
			AN.ControlGrid44_4.onChanged(self, obj, prop)
		if prop in ("ShowGrid", "ShowSurface", "ReverseNormal"):
			self._update_shape(obj)

	def execute(self, obj):
		AN.ControlGrid44_4.execute(self, obj)
		self._update_shape(obj)


class SilkPatchViewProvider:
	def __init__(self, obj):
		obj.Proxy = self

	def attach(self, vobj):
		self.Object = vobj.Object

	def updateData(self, fp, prop):
		return

	def getDisplayModes(self, obj):
		return ["Default"]

	def getDefaultDisplayMode(self):
		return "Default"

	def setDisplayMode(self, mode):
		return mode

	def onDelete(self, feature, subelements):
		return True


class CreateSurfacePatchCommand:
	def GetResources(self):
		return {'Pixmap': '',
				'MenuText': 'Silk SurfacePatch',
				'ToolTip': PATCH_TIP}

	def _collect_boundaries(self):
		bounds = []
		for obj in Gui.Selection.getSelection():
			if _is_boundary(obj):
				bounds.append(obj)
		return bounds

	def Activated(self):
		bounds = self._collect_boundaries()
		if len(bounds) not in (4,):
			tipsDialog("Silk: SurfacePatch", PATCH_TIP)
			return
		doc = FreeCAD.ActiveDocument
		obj = doc.addObject("Part::FeaturePython", "SurfacePatch44")
		SilkSurfacePatch(obj, bounds)
		SilkPatchViewProvider(obj.ViewObject)
		obj.ViewObject.DisplayMode = u"Flat Lines"
		doc.recompute()


Gui.addCommand('Silk_CreateBoundarySpline', CreateBoundarySplineCommand())
Gui.addCommand('Silk_CreateSurfacePatch', CreateSurfacePatchCommand())
