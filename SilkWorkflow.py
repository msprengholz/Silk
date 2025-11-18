#    This file is part of Silk
#    (c) Edward Mills 2016-2024
#    Refactored by Gemini
#
#    NURBS Surface modeling tools focused on low degree and seam continuity (FreeCAD Workbench)

import os
import FreeCAD
import FreeCADGui as Gui
import Part

from popup import tipsDialog
import Silk_tooltips
import ArachNURBS as AN
import Silk_dummy

BOUNDARY_TIP = """Create a BoundarySpline object by selecting either:
* one sketch (first element or 3 connected edges)
* two node sketches
* two Point_onCurve objects
* a ControlGrid/Silk patch edge (preselect a vertex or edge)

The resulting BoundarySpline remains driven by the original sketches, exposes
Silk specific metadata, and stores an optional visualization BSpline."""

PATCH_TIP = """Create a ControlGrid object from three or four BoundarySplines.
All selected inputs must share endpoints just like the classic ControlGrid tools."""

PATH_SILK = os.path.dirname(Silk_dummy.__file__)
BOUNDARY_ICON = os.path.join(PATH_SILK, 'Resources', 'Icons', 'BoundarySpline.svg')
CONTROLGRID_ICON = os.path.join(PATH_SILK, 'Resources', 'Icons', 'ControlGridPatch.svg')


# --- Helper Functions ---

def _ensure_property(obj, prop_type, prop_name, group, tooltip, default_val=None):
    """Safely adds a property to an object if it doesn't exist."""
    if not hasattr(obj, prop_name):
        obj.addProperty(prop_type, prop_name, group, tooltip)
    
    # Initialize value if provided and safe to do so
    if default_val is not None:
        current_val = getattr(obj, prop_name)
        # Only set if necessary to avoid marking object touched unnecessarily
        if current_val != default_val:
            setattr(obj, prop_name, default_val)
    return getattr(obj, prop_name)

def _clamp_01(value):
    try:
        val = float(value)
    except (TypeError, ValueError):
        val = 0.0
    return max(0.0, min(1.0, val))

def _compound_shapes(shapes):
    valid = [s for s in shapes if s and not s.isNull()]
    if not valid:
        return Part.Shape()
    if len(valid) == 1:
        return valid[0]
    return Part.Compound(valid)

# --- Grid/Edge Logic ---

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
    
    # Add U lines
    for row in poles:
        for start, end in zip(row, row[1:]):
            edges.append(Part.LineSegment(start, end).toShape())
    
    # Add V lines
    for col in range(v_count):
        points = [poles[i][col] for i in range(u_count)]
        for start, end in zip(points, points[1:]):
            edges.append(Part.LineSegment(start, end).toShape())
            
    return _compound_shapes(edges)


# --- Silk Boundary Spline ---

class SilkBoundarySpline:
    def __init__(self, obj, mode, payload):
        # Init Properties
        _ensure_property(obj, "App::PropertyString", "SilkRole", "B1 - Boundary", "Silk workflow identifier", "SilkBoundarySpline")
        _ensure_property(obj, "App::PropertyString", "BoundaryMode", "B1 - Boundary", "Input interpretation mode", mode)
        _ensure_property(obj, "App::PropertyBool", "ShowControlPoly", "B2 - Preview", "Display the control polyline", False)
        _ensure_property(obj, "App::PropertyBool", "ShowPreviewCurve", "B2 - Preview", "Overlay a cubic curve preview", True)
        _ensure_property(obj, "Part::PropertyPartShape", "PolyShape", "B3 - Cache", "Stored polyline shape")
        _ensure_property(obj, "Part::PropertyPartShape", "CurveShape", "B3 - Cache", "Stored cubic curve preview")
        _ensure_property(obj, "App::PropertyColor", "CurveColor", "B2 - Preview", "Preview curve display color", (1.0, 0.67, 0.0))
        _ensure_property(obj, "App::PropertyColor", "PolyColor", "B2 - Preview", "Polyline display color", (0.0, 1.0, 1.0))
        _ensure_property(obj, "App::PropertyString", "CreatorNote", "B1 - Boundary", "Free form comment about this boundary", "")
        
        self._init_worker(obj, mode, payload)
        obj.Proxy = self

    def __getstate__(self):
        state = self.__dict__.copy()
        if 'worker' in state: del state['worker']
        return state

    def __setstate__(self, state):
        self.__dict__.update(state)
        self.worker = None

    def _init_worker(self, obj, mode, payload):
        try:
            if mode == '3L':
                self.worker = AN.ControlPoly4_3L(obj, payload.get('Sketch'))
            elif mode == 'FirstElement':
                self.worker = AN.ControlPoly4_FirstElement(obj, payload.get('Sketch'))
            elif mode == '2N':
                self.worker = AN.ControlPoly4_2N(obj, payload.get('Sketch0'), payload.get('Sketch1'))
            elif mode == '2P':
                self.worker = AN.ControlPoly4_2P(obj, payload.get('Point0'), payload.get('Point1'))
            elif mode == 'GridEdge':
                self.worker = None
                if payload: # Only set props if payload exists (creation time)
                    _ensure_property(obj, "App::PropertyLink", "Grid", "C1 - Inputs", "Reference grid or surface patch", payload['Grid'])
                    _ensure_property(obj, "App::PropertyInteger", "EdgeIndex", "C1 - Inputs", "Grid edge index (0-3)", payload['EdgeIndex'])
                    _ensure_property(obj, "App::PropertyFloatList", "Weights", "C1 - Inputs", "Weights", [1.0, 1.0, 1.0, 1.0])
                    _ensure_property(obj, "App::PropertyVectorList", "Poles", "C2 - Outputs", "Poles")
                    _ensure_property(obj, "Part::PropertyGeometryList", "Legs", "C2 - Outputs", "control segments")
        except Exception as e:
            FreeCAD.Console.PrintWarning(f"SilkBoundary init warning: {e}\n")
            self.worker = None

    def onDocumentRestored(self, obj):
        """Rebuilds the worker by finding existing inputs on the object."""
        mode = getattr(obj, "BoundaryMode", "")
        payload = {}
        
        # Attempt to recover inputs from properties that AN likely created
        if mode in ['3L', 'FirstElement']:
            if hasattr(obj, "Sketch"): payload['Sketch'] = obj.Sketch
        elif mode == '2N':
            if hasattr(obj, "Node0"): payload['Sketch0'] = obj.Node0
            if hasattr(obj, "Node1"): payload['Sketch1'] = obj.Node1
        
        self._init_worker(obj, mode, payload)
        obj.Proxy = self # Re-assert proxy ownership

    def onChanged(self, obj, prop):
        # Use obj.BoundaryMode instead of self.boundary_mode to be safe during load
        mode = getattr(obj, "BoundaryMode", None)
        
        if mode == 'GridEdge':
            if prop in ("Grid", "EdgeIndex"):
                obj.recompute()
        elif self.worker:
            self.worker.onChanged(obj, prop)
            
        if prop in ("ShowControlPoly", "ShowPreviewCurve"):
            self._update_display_shape(obj)

    def execute(self, obj):
        try:
            mode = getattr(obj, "BoundaryMode", None)
            if mode == 'GridEdge':
                self._execute_grid_edge(obj)
            elif self.worker:
                self.worker.execute(obj)
            self._update_display_shape(obj)
        except Exception as e:
            FreeCAD.Console.PrintError(f"SilkBoundary error: {e}\n")

    def _execute_grid_edge(self, obj):
        grid = obj.Grid
        if grid is None or not hasattr(grid, "Poles"): return
        poles = getattr(grid, "Poles", [])
        weights = getattr(grid, "Weights", [1.0] * len(poles))
        if len(poles) != 16: return
        edge = max(0, min(3, obj.EdgeIndex))
        index_sequence = EDGE_POLE_SEQUENCE.get(edge, [])
        if not index_sequence: return
        poly_pts = [poles[i] for i in index_sequence]
        poly_w = [weights[i] for i in index_sequence]
        obj.Poles = poly_pts
        obj.Weights = poly_w
        obj.Legs = [
            Part.LineSegment(poly_pts[0], poly_pts[1]),
            Part.LineSegment(poly_pts[1], poly_pts[2]),
            Part.LineSegment(poly_pts[2], poly_pts[3]),
        ]

    def _update_display_shape(self, obj):
        shapes = []
        if obj.ShowControlPoly and hasattr(obj, "Legs"):
            obj.PolyShape = Part.Shape(obj.Legs)
            shapes.append(obj.PolyShape)
        else:
            obj.PolyShape = Part.Shape()

        if obj.ShowPreviewCurve and hasattr(obj, "Poles") and hasattr(obj, "Weights"):
            try:
                weighted = [[obj.Poles[i], obj.Weights[i]] for i in range(len(obj.Poles))]
                curve = AN.Bezier_Cubic_curve(weighted).toShape()
                obj.CurveShape = curve
                shapes.append(curve)
            except Exception:
                obj.CurveShape = Part.Shape()
        else:
            obj.CurveShape = Part.Shape()
        obj.Shape = _compound_shapes(shapes)

class SilkBoundaryViewProvider:
    def __init__(self, obj):
        obj.Proxy = self

    def __getstate__(self):
        """Don't save the FreeCAD Object reference."""
        state = self.__dict__.copy()
        if 'Object' in state:
            del state['Object']
        return state

    def __setstate__(self, state):
        self.__dict__.update(state)
        self.Object = None

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

    def getIcon(self):
        return BOUNDARY_ICON

    def onDelete(self, feature, subelements):
        return True

    def canDropObject(self, x):
        return False

    def getDefaultRepresentation(self):
        return 'Shaded'


# --- Silk Control Grid (Patch) ---

class SilkControlGrid:
    PATCH_OPTIONS = ['Quad4', 'Quad3']

    def __init__(self, obj, boundaries, patch_type='Quad4'):
        self._topology_lock = False
        self.worker = None
        init_type = patch_type if patch_type in self.PATCH_OPTIONS else 'Quad4'
        self.patch_topology = init_type # fallback
        self._init_worker(obj, init_type, boundaries)
        self._setup_common_properties(obj, boundaries, init_type)
        obj.Proxy = self

    def __getstate__(self):
        state = self.__dict__.copy()
        if 'worker' in state: del state['worker']
        return state

    def __setstate__(self, state):
        self.__dict__.update(state)
        self.worker = None

    def _init_worker(self, obj, patch_type, boundaries, settings=None):
        settings = settings or {}
        required = 4 if patch_type == 'Quad4' else 3
        if len(boundaries) < required: required = len(boundaries)
        selected = boundaries[:required]
        
        try:
            if patch_type == 'Quad3':
                self.worker = AN.ControlGrid44_3(obj, *selected)
            else:
                self.worker = AN.ControlGrid44_4(obj, *selected)
        except Exception as e:
             FreeCAD.Console.PrintWarning(f"SilkGrid init warning: {e}\n")

        if 'tolerance' in settings and hasattr(obj, "tolerance"): obj.tolerance = settings['tolerance']
        if 'reverse' in settings and hasattr(obj, "reverse"): obj.reverse = settings['reverse']
        if 'TweakWeight11' in settings and hasattr(obj, "TweakWeight11"): obj.TweakWeight11 = settings['TweakWeight11']

    def _setup_common_properties(self, obj, boundaries, patch_type, update_topology=True):
        _ensure_property(obj, "App::PropertyString", "SilkRole", "P1 - Patch", "Silk workflow identifier", "SilkControlGrid")
        _ensure_property(obj, "App::PropertyEnumeration", "PatchTopology", "P1 - Patch", "Surface patch topology", self.PATCH_OPTIONS)
        if update_topology:
            self._topology_lock = True
            obj.PatchTopology = patch_type
            self._topology_lock = False
        _ensure_property(obj, "App::PropertyLinkList", "Boundaries", "P1 - Patch", "Ordered boundary references", boundaries[:])
        obj.setEditorMode("Boundaries", 1)
        obj.Boundaries = boundaries[:]
        _ensure_property(obj, "App::PropertyBool", "ShowSurface", "P2 - Display", "Display the underlying cubic surface", True)
        _ensure_property(obj, "App::PropertyBool", "ShowGrid", "P2 - Display", "Display the control grid", True)
        _ensure_property(obj, "App::PropertyFloatList", "USplits", "P2 - Display", "Subdivision parameters along U", [])
        _ensure_property(obj, "App::PropertyFloatList", "VSplits", "P2 - Display", "Subdivision parameters along V", [])
        _ensure_property(obj, "App::PropertyBool", "ReverseNormal", "P2 - Display", "Flip the generated surface normal", False)
        _ensure_property(obj, "Part::PropertyPartShape", "GridShape", "P3 - Cache", "Cached control grid shape")
        _ensure_property(obj, "Part::PropertyPartShape", "SurfaceShape", "P3 - Cache", "Cached cubic surface shape")

    def _poly_names_for(self, obj=None, patch_type=None):
        """Safely determine poly names using Obj property if available."""
        if patch_type:
            current = patch_type
        elif obj and hasattr(obj, "PatchTopology"):
            current = obj.PatchTopology
        else:
            # Default safe fallback during load if property isn't ready
            return ["Poly0", "Poly1", "Poly2", "Poly3"]
            
        if current == 'Quad3':
            return ["Poly0", "Poly1", "Poly2"]
        return ["Poly0", "Poly1", "Poly2", "Poly3"]

    def _boundary_inputs_for(self, obj, patch_type=None):
        target = patch_type or getattr(obj, "PatchTopology", "Quad4")
        required = 4 if target == 'Quad4' else 3
        source = list(getattr(obj, "Boundaries", []))
        if len(source) >= required:
            return source[:required]
        names = self._poly_names_for(obj, target)
        collected = []
        for name in names:
            if hasattr(obj, name): collected.append(getattr(obj, name))
        return collected[:required]

    def _sync_boundaries(self, obj):
        if not hasattr(obj, "Boundaries"): return
        names = self._poly_names_for(obj)
        obj.Boundaries = [getattr(obj, name) for name in names if hasattr(obj, name)]

    def _capture_patch_settings(self, obj):
        settings = {}
        for attr in ["tolerance", "reverse", "TweakWeight11"]:
            if hasattr(obj, attr): settings[attr] = getattr(obj, attr)
        return settings

    def _clear_patch_specific_properties(self, obj):
        to_remove = ["Poly0", "Poly1", "Poly2", "Poly3", "tolerance", "reverse", "TweakWeight11", "Poles", "Weights", "Legs"]
        for name in to_remove:
            if hasattr(obj, name): obj.removeProperty(name)

    def _switch_topology(self, obj, new_type):
        bounds = self._boundary_inputs_for(obj, new_type)
        settings = self._capture_patch_settings(obj)
        self._clear_patch_specific_properties(obj)
        self._init_worker(obj, new_type, bounds, settings)
        self._setup_common_properties(obj, bounds, new_type, update_topology=False)
        self._sync_boundaries(obj)
        self._topology_lock = True
        obj.PatchTopology = new_type
        self._topology_lock = False
        self._update_shape(obj)

    def _update_shape(self, obj):
        if not hasattr(obj, "Poles") or len(obj.Poles) != 16:
            obj.Shape = Part.Shape()
            return
        
        # --- Base Surface Generation ---
        weights = obj.Weights
        poles = obj.Poles
        if obj.ReverseNormal:
             reordered = [
                [poles[3], weights[3]], [poles[2], weights[2]], [poles[1], weights[1]], [poles[0], weights[0]],
                [poles[7], weights[7]], [poles[6], weights[6]], [poles[5], weights[5]], [poles[4], weights[4]],
                [poles[11], weights[11]], [poles[10], weights[10]], [poles[9], weights[9]], [poles[8], weights[8]],
                [poles[15], weights[15]], [poles[14], weights[14]], [poles[13], weights[13]], [poles[12], weights[12]],
            ]
        else:
            reordered = [[poles[i], weights[i]] for i in range(16)]
        base_surface = AN.Bezier_Bicubic_surf(reordered)

        # --- Subdivision Logic ---
        u_intervals = self._intervals(getattr(obj, "USplits", []))
        v_intervals = self._intervals(getattr(obj, "VSplits", []))
        has_subdiv = len(u_intervals) > 1 or len(v_intervals) > 1

        if not has_subdiv:
            obj.GridShape = Part.Shape(obj.Legs) if obj.ShowGrid else Part.Shape()
            obj.SurfaceShape = base_surface.toShape() if obj.ShowSurface else Part.Shape()
        else:
            sub_surfaces = self._generate_segments(base_surface, u_intervals, v_intervals)
            grid_shapes = [_grid_shape_from_surface(s) for s in sub_surfaces]
            surface_shapes = [s.toShape() for s in sub_surfaces]
            obj.GridShape = _compound_shapes(grid_shapes) if obj.ShowGrid else Part.Shape()
            obj.SurfaceShape = _compound_shapes(surface_shapes) if obj.ShowSurface else Part.Shape()

        obj.Shape = _compound_shapes([obj.GridShape if obj.ShowGrid else None, obj.SurfaceShape if obj.ShowSurface else None])

    def _intervals(self, values):
        valid = sorted(set(_clamp_01(v) for v in values if 0 < v < 1))
        points = [0.0] + valid + [1.0]
        return [(points[i], points[i + 1]) for i in range(len(points) - 1)]

    def _generate_segments(self, surface, intervals_u, intervals_v):
        segments = []
        if surface is None: return segments
        for u0, u1 in intervals_u:
            for v0, v1 in intervals_v:
                try:
                    sub = surface.copy()
                    sub.segment(u0, u1, v0, v1)
                    segments.append(sub)
                except Exception: continue
        return segments

    def onChanged(self, obj, prop):
        if prop == "PatchTopology":
            curr_topo = getattr(obj, "PatchTopology", "Quad4")
            if not self._topology_lock and curr_topo != getattr(self, "patch_topology", ""):
                self.patch_topology = curr_topo
                self._switch_topology(obj, curr_topo)
            return
            
        if prop in self._poly_names_for(obj):
            self._sync_boundaries(obj)
            return
            
        if prop == "reverse" and self.worker:
            self.worker.onChanged(obj, prop)
            
        if prop in ("ShowGrid", "ShowSurface", "ReverseNormal", "USplits", "VSplits"):
            self._update_shape(obj)

    def execute(self, obj):
        try:
            if self.worker:
                self.worker.execute(obj)
            self._sync_boundaries(obj)
            self._update_shape(obj)
        except Exception as e:
            FreeCAD.Console.PrintError(f"SilkGrid Execute Error: {e}\n")

    def onDocumentRestored(self, obj):
        topo = getattr(obj, "PatchTopology", "Quad4")
        self.patch_topology = topo
        bounds = self._boundary_inputs_for(obj, topo)
        self._init_worker(obj, topo, bounds)
        
        if hasattr(self.worker, "onDocumentRestored"):
            self.worker.onDocumentRestored(obj)
            
        self._sync_boundaries(obj)
        self._update_shape(obj)

class SilkControlGridViewProvider:
    def __init__(self, obj):
        obj.Proxy = self

    def __getstate__(self):
        state = self.__dict__.copy()
        if 'Object' in state:
            del state['Object']
        return state

    def __setstate__(self, state):
        self.__dict__.update(state)
        self.Object = None

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

    def getIcon(self):
        return CONTROLGRID_ICON

    def onDelete(self, feature, subelements):
        return True


# --- Commands ---

def _create_boundary_feature(mode, payload):
    doc = FreeCAD.ActiveDocument
    name = f"BoundarySpline_{mode}"
    obj = doc.addObject("Part::FeaturePython", name)
    SilkBoundarySpline(obj, mode, payload)
    SilkBoundaryViewProvider(obj.ViewObject)
    obj.ViewObject.DisplayMode = "Flat Lines"
    obj.ViewObject.Visibility = True
    obj.ViewObject.LineColor = obj.PolyColor
    return obj

class CreateBoundarySplineCommand:
    def GetResources(self):
        return {'Pixmap': BOUNDARY_ICON,
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
            obj0 = sel[0].Object
            obj1 = sel[1].Object
            
            if obj0.TypeId == 'Sketcher::SketchObject' and obj1.TypeId == 'Sketcher::SketchObject':
                return ('2N', {'Sketch0': obj0, 'Sketch1': obj1})
            
            # Duck typing for Point_onCurve
            if hasattr(obj0, 'object_type') and hasattr(obj1, 'object_type'):
                if obj0.object_type == 'Point_onCurve' and obj1.object_type == 'Point_onCurve':
                     return ('2P', {'Point0': obj0, 'Point1': obj1})
        return None

    def Activated(self):
        data = self._interpret_selection()
        if not data:
            tipsDialog("Silk: BoundarySpline", BOUNDARY_TIP)
            return
        mode, payload = data
        _create_boundary_feature(mode, payload)
        FreeCAD.ActiveDocument.recompute()


class CreateControlGridCommand:
    def GetResources(self):
        return {'Pixmap': CONTROLGRID_ICON,
                'MenuText': 'Silk ControlGrid',
                'ToolTip': PATCH_TIP}

    def _collect_boundaries(self):
        bounds = []
        created = []
        selection = Gui.Selection.getSelectionEx()
        
        # Fallback to simple selection if getSelectionEx is empty but getSelection has items
        if not selection:
            raw_sel = Gui.Selection.getSelection()
            if raw_sel:
                selection = [type('Sel', (object,), {'Object': o, 'SubObjects': []}) for o in raw_sel]

        for sel in selection:
            obj = sel.Object
            if obj is None:
                continue
                
            # Case 1: Existing Silk Boundary
            if hasattr(obj, "SilkRole") and obj.SilkRole == "SilkBoundarySpline":
                bounds.append(obj)
                continue
                
            # Case 2: Legacy/Raw AN Curve
            if hasattr(obj, "object_type") and isinstance(obj.object_type, str):
                if obj.object_type.startswith("ControlPoly4"):
                    bounds.append(obj)
                    continue
            
            # Case 3: Auto-convert Sketches
            if obj.TypeId == 'Sketcher::SketchObject':
                mode = '3L' if obj.GeometryCount == 3 else 'FirstElement'
                payload = {'Sketch': obj}
                new_boundary = _create_boundary_feature(mode, payload)
                created.append(new_boundary)
                bounds.append(new_boundary)
                continue
            
            # Case 4: Auto-convert Grid Edges
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
        label = f"ControlGrid{patch_type}"
        obj = doc.addObject("Part::FeaturePython", label)
        
        SilkControlGrid(obj, bounds, patch_type)
        SilkControlGridViewProvider(obj.ViewObject)
        obj.ViewObject.DisplayMode = "Flat Lines"
        doc.recompute()


Gui.addCommand('Silk_CreateBoundarySpline', CreateBoundarySplineCommand())
Gui.addCommand('Silk_CreateControlGrid', CreateControlGridCommand())