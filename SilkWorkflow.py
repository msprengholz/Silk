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
* a ControlGrid/Silk patch edge (preselect a vertex or edge)

The resulting BoundarySpline remains driven by the original sketches, exposes
Silk specific metadata, and stores an optional visualization BSpline."""

PATCH_TIP = """Create a ControlGrid object from three or four BoundarySplines.
All selected inputs must share endpoints just like the classic ControlGrid tools."""


def _is_boundary(obj):
	return hasattr(obj, "SilkRole") and obj.SilkRole == "SilkBoundarySpline"


def _make_boundary_label(mode):
	return "BoundarySpline_{}".format(mode)


def _create_boundary_feature(mode, payload):
	doc = FreeCAD.ActiveDocument
	obj = doc.addObject("Part::FeaturePython", _make_boundary_label(mode))
	SilkBoundarySpline(obj, mode, payload)
	SilkBoundaryViewProvider(obj.ViewObject)
	obj.ViewObject.DisplayMode = "Flat Lines"
	obj.ViewObject.Visibility = True
	obj.ViewObject.LineColor = obj.PolyColor
	return obj


def _clamp_01(value):
	try:
		val = float(value)
	except (TypeError, ValueError):
		val = 0.0
	return max(0.0, min(1.0, val))


# index helpers for ControlGrid44 style pole ordering
EDGE_INTERIOR_INDICES = {
	0: [1, 2],    # top edge
	1: [7, 11],   # right edge
	2: [13, 14],  # bottom edge
	3: [4, 8],    # left edge
}

EDGE_POLE_SEQUENCE = {
	0: [0, 1, 2, 3],
	1: [3, 7, 11, 15],
	2: [15, 14, 13, 12],
	3: [12, 8, 4, 0],
}


def _grid_edge_from_selection(sel_ex):
	obj = sel_ex.Object
	if obj is None:
		return None
	poles = getattr(obj, "Poles", None)
	if poles is None or len(poles) != 16:
		return None
	if not sel_ex.SubObjects:
		return None
	sub = sel_ex.SubObjects[0]
	points = []
	if sub.ShapeType == 'Vertex':
		points.append(sub.Point)
	elif sub.ShapeType == 'Edge':
		points.append(sub.firstVertex().Point)
		points.append(sub.lastVertex().Point)
	else:
		return None
	for pt in points:
		match = AN.VectorIndex(poles, pt)
		if match == 'noIndex':
			continue
		for edge_idx, interior_ids in EDGE_INTERIOR_INDICES.items():
			if match in interior_ids:
				return (obj, edge_idx)
	return None


def _compound_shapes(shapes):
	valid = [s for s in shapes if s and not s.isNull()]
	if not valid:
		return Part.Shape()
	if len(valid) == 1:
		return valid[0]
	return Part.Compound(valid)


def _grid_shape_from_surface(surface):
	try:
		poles = surface.getPoles()
	except Exception:
		return Part.Shape()
	if not poles:
		return Part.Shape()
	edges = []
	u_count = len(poles)
	v_count = len(poles[0])
	for row in poles:
		for start, end in zip(row, row[1:]):
			edges.append(Part.LineSegment(start, end).toShape())
	for col in range(v_count):
		points = [poles[i][col] for i in range(u_count)]
		for start, end in zip(points, points[1:]):
			edges.append(Part.LineSegment(start, end).toShape())
	return _compound_shapes(edges)


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
						"ShowControlPoly",
						"B2 - Preview",
						"Display the control polyline").ShowControlPoly = False
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
		elif self.boundary_mode == 'GridEdge':
			obj.addProperty("App::PropertyLink",
							"Grid",
							"C1 - Inputs",
							"Reference grid or surface patch").Grid = payload['Grid']
			obj.addProperty("App::PropertyInteger",
							"EdgeIndex",
							"C1 - Inputs",
							"Grid edge index (0-3)").EdgeIndex = payload['EdgeIndex']
			obj.addProperty("App::PropertyFloatList",
							"Weights",
							"C1 - Inputs",
							"Weights").Weights = [1.0, 1.0, 1.0, 1.0]
			obj.addProperty("App::PropertyVectorList",
							"Poles",
							"C2 - Outputs",
							"Poles").Poles
			obj.addProperty("Part::PropertyGeometryList",
							"Legs",
							"C2 - Outputs",
							"control segments").Legs
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
		elif self.boundary_mode == 'GridEdge':
			if prop in ("Grid", "EdgeIndex"):
				obj.recompute()
		if prop in ("ShowControlPoly", "ShowPreviewCurve"):
			self._update_display_shape(obj)

	def _update_display_shape(self, obj):
		shapes = []
		if obj.ShowControlPoly:
			poly_shape = Part.Shape(obj.Legs)
			obj.PolyShape = poly_shape
			shapes.append(poly_shape)
		else:
			obj.PolyShape = Part.Shape()
		if obj.ShowPreviewCurve:
			weighted = [[obj.Poles[i], obj.Weights[i]] for i in range(len(obj.Poles))]
			curve = AN.Bezier_Cubic_curve(weighted).toShape()
			obj.CurveShape = curve
			shapes.append(curve)
		else:
			obj.CurveShape = Part.Shape()
		if shapes:
			obj.Shape = Part.Compound(shapes) if len(shapes) > 1 else shapes[0]
		else:
			obj.Shape = Part.Shape()

	def execute(self, obj):
		if self.boundary_mode == '3L':
			AN.ControlPoly4_3L.execute(self, obj)
		elif self.boundary_mode == 'FirstElement':
			AN.ControlPoly4_FirstElement.execute(self, obj)
		elif self.boundary_mode == '2N':
			AN.ControlPoly4_2N.execute(self, obj)
		elif self.boundary_mode == '2P':
			AN.ControlPoly4_2P.execute(self, obj)
		elif self.boundary_mode == 'GridEdge':
			self._execute_grid_edge(obj)
		self._update_display_shape(obj)

	def _execute_grid_edge(self, obj):
		grid = obj.Grid
		if grid is None or not hasattr(grid, "Poles"):
			return
		poles = getattr(grid, "Poles", [])
		weights = getattr(grid, "Weights", [1.0] * len(poles))
		if len(poles) != 16:
			return
		edge = max(0, min(3, obj.EdgeIndex))
		index_sequence = EDGE_POLE_SEQUENCE.get(edge, [])
		if not index_sequence:
			return
		poly_pts = [poles[i] for i in index_sequence]
		poly_w = [weights[i] for i in index_sequence]
		obj.Poles = poly_pts
		obj.Weights = poly_w
		obj.Legs = [
			Part.LineSegment(poly_pts[0], poly_pts[1]),
			Part.LineSegment(poly_pts[1], poly_pts[2]),
			Part.LineSegment(poly_pts[2], poly_pts[3]),
		]


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

	def canDropObject(self, x):
		return False

	def getDefaultRepresentation(self):
		return 'Shaded'


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
			grid_edge = _grid_edge_from_selection(sel[0])
			if grid_edge:
				grid_obj, edge_idx = grid_edge
				return ('GridEdge', {'Grid': grid_obj, 'EdgeIndex': edge_idx})
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
		_create_boundary_feature(mode, payload)
		FreeCAD.ActiveDocument.recompute()


class SilkControlGrid(AN.ControlGrid44_4, AN.ControlGrid44_3):
	PATCH_OPTIONS = ['Quad4', 'Quad3']

	def __init__(self, obj, boundaries, patch_type='Quad4'):
		self._topology_lock = False
		init_type = patch_type if patch_type in self.PATCH_OPTIONS else 'Quad4'
		self.patch_topology = init_type
		self._init_patch(obj, init_type, boundaries)
		self._setup_common_properties(obj, boundaries, init_type)
		obj.Proxy = self

	def _poly_names_for(self, patch_type=None):
		current = patch_type or self.patch_topology
		if current == 'Quad3':
			return ["Poly0", "Poly1", "Poly2"]
		return ["Poly0", "Poly1", "Poly2", "Poly3"]

	def _init_patch(self, obj, patch_type, boundaries, settings=None):
		settings = settings or {}
		required = 4 if patch_type == 'Quad4' else 3
		if len(boundaries) < required:
			raise ValueError("Not enough boundaries supplied for {}".format(patch_type))
		selected = boundaries[:required]
		if patch_type == 'Quad3':
			AN.ControlGrid44_3.__init__(self, obj, *selected)
		else:
			AN.ControlGrid44_4.__init__(self, obj, *selected)
		self.patch_topology = patch_type
		if 'tolerance' in settings and hasattr(obj, "tolerance"):
			obj.tolerance = settings['tolerance']
		if 'reverse' in settings and hasattr(obj, "reverse"):
			obj.reverse = settings['reverse']
		if 'TweakWeight11' in settings and hasattr(obj, "TweakWeight11"):
			obj.TweakWeight11 = settings['TweakWeight11']

	def _setup_common_properties(self, obj, boundaries, patch_type, update_topology=True):
		if not hasattr(obj, "SilkRole"):
			obj.addProperty("App::PropertyString",
							"SilkRole",
							"P1 - Patch",
							"Silk workflow identifier").SilkRole = "SilkControlGrid"
		if not hasattr(obj, "PatchTopology"):
			obj.addProperty("App::PropertyEnumeration",
							"PatchTopology",
							"P1 - Patch",
							"Surface patch topology").PatchTopology = self.PATCH_OPTIONS
		if update_topology:
			self._topology_lock = True
			obj.PatchTopology = patch_type
			self._topology_lock = False
		if not hasattr(obj, "Boundaries"):
			obj.addProperty("App::PropertyLinkList",
							"Boundaries",
							"P1 - Patch",
							"Ordered boundary references").Boundaries = boundaries[:]
			obj.setEditorMode("Boundaries", 1)
		else:
			obj.Boundaries = boundaries[:]
		if not hasattr(obj, "ShowSurface"):
			obj.addProperty("App::PropertyBool",
							"ShowSurface",
							"P2 - Display",
							"Display the underlying cubic surface").ShowSurface = True
		if not hasattr(obj, "ShowGrid"):
			obj.addProperty("App::PropertyBool",
							"ShowGrid",
							"P2 - Display",
							"Display the control grid").ShowGrid = True
		if not hasattr(obj, "USplits"):
			obj.addProperty("App::PropertyFloatList",
							"USplits",
							"P2 - Display",
							"Subdivision parameters along U").USplits = []
		if not hasattr(obj, "VSplits"):
			obj.addProperty("App::PropertyFloatList",
							"VSplits",
							"P2 - Display",
							"Subdivision parameters along V").VSplits = []
		if not hasattr(obj, "ReverseNormal"):
			obj.addProperty("App::PropertyBool",
							"ReverseNormal",
							"P2 - Display",
							"Flip the generated surface normal").ReverseNormal = False
		if not hasattr(obj, "GridShape"):
			obj.addProperty("Part::PropertyPartShape",
							"GridShape",
							"P3 - Cache",
							"Cached control grid shape").GridShape = Part.Shape()
		if not hasattr(obj, "SurfaceShape"):
			obj.addProperty("Part::PropertyPartShape",
							"SurfaceShape",
							"P3 - Cache",
							"Cached cubic surface shape").SurfaceShape = Part.Shape()

	def _capture_patch_settings(self, obj):
		settings = {}
		if hasattr(obj, "tolerance"):
			settings['tolerance'] = obj.tolerance
		if hasattr(obj, "reverse"):
			settings['reverse'] = obj.reverse
		if hasattr(obj, "TweakWeight11"):
			settings['TweakWeight11'] = obj.TweakWeight11
		return settings

	def _clear_patch_specific_properties(self, obj):
		to_remove = ["Poly0", "Poly1", "Poly2", "Poly3",
					 "tolerance", "reverse", "TweakWeight11",
					 "Poles", "Weights", "Legs",
					 "object_type", "object_version", "internalName"]
		for name in to_remove:
			if hasattr(obj, name):
				obj.removeProperty(name)

	def _current_builder(self):
		return AN.ControlGrid44_3 if self.patch_topology == 'Quad3' else AN.ControlGrid44_4

	def _boundary_inputs_for(self, obj, patch_type=None):
		target = patch_type or self.patch_topology
		required = 4 if target == 'Quad4' else 3
		source = list(getattr(obj, "Boundaries", []))
		if len(source) >= required:
			return source[:required]
		names = self._poly_names_for(target)
		collected = []
		for name in names:
			if hasattr(obj, name):
				collected.append(getattr(obj, name))
		return collected[:required]

	def _sync_boundaries(self, obj):
		if not hasattr(obj, "Boundaries"):
			return
		names = self._poly_names_for()
		obj.Boundaries = [getattr(obj, name) for name in names if hasattr(obj, name)]
	def _switch_topology(self, obj, new_type):
		bounds = self._boundary_inputs_for(obj, new_type)
		required = 4 if new_type == 'Quad4' else 3
		if len(bounds) < required:
			FreeCAD.Console.PrintMessage("\nSilkControlGrid: not enough boundaries for {}\n".format(new_type))
			self._topology_lock = True
			obj.PatchTopology = self.patch_topology
			self._topology_lock = False
			return
		settings = self._capture_patch_settings(obj)
		self._clear_patch_specific_properties(obj)
		self._init_patch(obj, new_type, bounds, settings)
		self._setup_common_properties(obj, bounds, new_type, update_topology=False)
		self._sync_boundaries(obj)
		self._topology_lock = True
		obj.PatchTopology = new_type
		self._topology_lock = False
		self._update_shape(obj)

	def _base_surface(self, obj):
		weights = obj.Weights
		poles = obj.Poles
		if len(poles) != 16:
			return None
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
		return AN.Bezier_Bicubic_surf(reordered)

	def _build_surface_shape(self, obj):
		base = self._base_surface(obj)
		return base.toShape() if base else Part.Shape()

	def _intervals(self, values):
		valid = sorted(set(_clamp_01(v) for v in values if 0 < v < 1))
		points = [0.0] + valid + [1.0]
		return [(points[i], points[i + 1]) for i in range(len(points) - 1)]

	def _generate_segments(self, surface, intervals_u, intervals_v):
		segments = []
		if surface is None:
			return segments
		for u0, u1 in intervals_u:
			for v0, v1 in intervals_v:
				sub = surface.copy()
				try:
					sub.segment(u0, u1, v0, v1)
				except Exception:
					continue
				segments.append(sub)
		return segments

	def _update_shape(self, obj):
		base_surface = self._base_surface(obj)
		if base_surface is None:
			obj.GridShape = Part.Shape()
			obj.SurfaceShape = Part.Shape()
			obj.Shape = Part.Shape()
			return
		u_intervals = self._intervals(getattr(obj, "USplits", []))
		v_intervals = self._intervals(getattr(obj, "VSplits", []))
		has_subdiv = len(u_intervals) > 1 or len(v_intervals) > 1
		if not has_subdiv:
			grid_shape = Part.Shape(obj.Legs)
			surface_shape = base_surface.toShape()
			obj.GridShape = grid_shape if obj.ShowGrid else Part.Shape()
			obj.SurfaceShape = surface_shape if obj.ShowSurface else Part.Shape()
			obj.Shape = _compound_shapes(
				[
					obj.GridShape if obj.ShowGrid else None,
					obj.SurfaceShape if obj.ShowSurface else None,
				]
			)
			return
		sub_surfaces = self._generate_segments(base_surface, u_intervals, v_intervals)
		grid_shapes = [_grid_shape_from_surface(s) for s in sub_surfaces]
		surface_shapes = [s.toShape() for s in sub_surfaces]
		obj.GridShape = _compound_shapes(grid_shapes) if obj.ShowGrid else Part.Shape()
		obj.SurfaceShape = (
			_compound_shapes(surface_shapes) if obj.ShowSurface else Part.Shape()
		)
		obj.Shape = _compound_shapes(
			[
				obj.GridShape if obj.ShowGrid else None,
				obj.SurfaceShape if obj.ShowSurface else None,
			]
		)

	def onChanged(self, obj, prop):
		if prop == "PatchTopology":
			if self._topology_lock:
				return
			if obj.PatchTopology != self.patch_topology:
				self._switch_topology(obj, obj.PatchTopology)
			return
		if prop in self._poly_names_for():
			self._sync_boundaries(obj)
			return
		if prop == "reverse":
			builder = self._current_builder()
			builder.onChanged(self, obj, prop)
		if prop in ("ShowGrid", "ShowSurface", "ReverseNormal"):
			self._update_shape(obj)

	def execute(self, obj):
		builder = self._current_builder()
		try:
			builder.execute(self, obj)
		except NameError as err:
			if getattr(err, "name", "") == "please_read_message_above":
				FreeCAD.Console.PrintError("SilkControlGrid: boundary endpoints do not match. Check boundary ordering and tolerances.\n")
				return
			raise
		self._sync_boundaries(obj)
		self._update_shape(obj)

	def onDocumentRestored(self, obj):
		topo = getattr(obj, "PatchTopology", None)
		if topo not in self.PATCH_OPTIONS:
			topo = 'Quad4'
		self.patch_topology = topo
		builder = self._current_builder()
		if hasattr(builder, "onDocumentRestored"):
			builder.onDocumentRestored(self, obj)
		bounds = self._boundary_inputs_for(obj, topo)
		self._setup_common_properties(obj, bounds, topo)
		self._sync_boundaries(obj)
		self._update_shape(obj)


class SilkControlGridViewProvider:
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


class CreateControlGridCommand:
	def GetResources(self):
		return {'Pixmap': '',
				'MenuText': 'Silk ControlGrid',
				'ToolTip': PATCH_TIP}

	def _collect_boundaries(self):
		bounds = []
		created = []
		selection = Gui.Selection.getSelectionEx()
		if not selection:
			selection = [type('Sel', (object,), {'Object': o, 'SubObjects': []}) for o in Gui.Selection.getSelection()]
		for sel in selection:
			obj = sel.Object
			if obj is None:
				continue
			if _is_boundary(obj):
				bounds.append(obj)
				continue
			if hasattr(obj, "object_type") and isinstance(obj.object_type, str):
				if obj.object_type.startswith("ControlPoly4"):
					bounds.append(obj)
					continue
			if obj.TypeId == 'Sketcher::SketchObject':
				if obj.GeometryCount == 3:
					mode = '3L'
					payload = {'Sketch': obj}
				else:
					mode = 'FirstElement'
					payload = {'Sketch': obj}
				new_boundary = _create_boundary_feature(mode, payload)
				created.append(new_boundary)
				bounds.append(new_boundary)
				continue
			grid_edge = _grid_edge_from_selection(sel)
			if grid_edge:
				grid_obj, edge_idx = grid_edge
				new_boundary = _create_boundary_feature('GridEdge', {'Grid': grid_obj, 'EdgeIndex': edge_idx})
				created.append(new_boundary)
				bounds.append(new_boundary)
		if created:
			FreeCAD.ActiveDocument.recompute()
		return bounds

	def Activated(self):
		bounds = self._collect_boundaries()
		if len(bounds) not in (3, 4):
			tipsDialog("Silk: ControlGrid", PATCH_TIP)
			return
		doc = FreeCAD.ActiveDocument
		patch_type = 'Quad3' if len(bounds) == 3 else 'Quad4'
		label = "ControlGrid{}".format(patch_type)
		obj = doc.addObject("Part::FeaturePython", label)
		SilkControlGrid(obj, bounds, patch_type)
		SilkControlGridViewProvider(obj.ViewObject)
		obj.ViewObject.DisplayMode = u"Flat Lines"
		doc.recompute()


Gui.addCommand('Silk_CreateBoundarySpline', CreateBoundarySplineCommand())
Gui.addCommand('Silk_CreateControlGrid', CreateControlGridCommand())
