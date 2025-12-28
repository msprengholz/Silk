#    This file is part of Silk
#    (c) 2025
#
#    NURBS Surface modeling tools focused on low degree and seam continuity (FreeCAD Workbench)
#
#    Workflow scaffolding that bundles existing Silk commands without modifying
#    the core library.

import os

import FreeCAD
import Part
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


def _find_boundary_controlpoly(boundary):
    for obj in getattr(boundary, "Group", []):
        obj_type = getattr(obj, "object_type", "")
        if obj_type.startswith("ControlPoly4"):
            return obj
        if hasattr(obj, "Poles"):
            return obj
    return None


def _normalize_splits(values):
    return sorted(set([v for v in values if 0.0 < v < 1.0]))


def _build_intervals(values):
    splits = _normalize_splits(values)
    if not splits:
        return [(0.0, 1.0)]
    return list(zip([0.0] + splits, splits + [1.0]))


def _make_subgrid_from_surface(doc, surface, u0, u1, v0, v1, name):
    seg = surface.copy()
    seg.segment(u0, u1, v0, v1)
    poles = seg.getPoles()
    weights = seg.getWeights()
    flat_poles = [
        poles[3][0],
        poles[3][1],
        poles[3][2],
        poles[3][3],
        poles[2][0],
        poles[2][1],
        poles[2][2],
        poles[2][3],
        poles[1][0],
        poles[1][1],
        poles[1][2],
        poles[1][3],
        poles[0][0],
        poles[0][1],
        poles[0][2],
        poles[0][3],
    ]
    flat_weights = [
        weights[3][0],
        weights[3][1],
        weights[3][2],
        weights[3][3],
        weights[2][0],
        weights[2][1],
        weights[2][2],
        weights[2][3],
        weights[1][0],
        weights[1][1],
        weights[1][2],
        weights[1][3],
        weights[0][0],
        weights[0][1],
        weights[0][2],
        weights[0][3],
    ]
    sub = doc.addObject("Part::FeaturePython", name)
    sub.addProperty(
        "App::PropertyVectorList", "Poles", "C2 - Outputs", "Poles"
    ).Poles = flat_poles
    sub.addProperty(
        "App::PropertyFloatList", "Weights", "C2 - Outputs", "Weights"
    ).Weights = flat_weights
    sub.addProperty(
        "Part::PropertyGeometryList", "Legs", "C2 - Outputs", "control segments"
    ).Legs
    sub.Proxy = 0
    sub.Shape = Part.Shape(AN.drawGrid(flat_poles, 4))
    return sub


def _next_grid_id(doc):
    used = set()
    for obj in doc.Objects:
        if hasattr(obj, "GridId"):
            try:
                used.add(int(obj.GridId))
            except Exception:
                pass
    grid_id = 0
    while grid_id in used:
        grid_id += 1
    return grid_id


def _group_id_tag(obj):
    grid_id = getattr(obj, "GridId", None)
    if grid_id is None:
        return ""
    return str(int(grid_id))


def _name_with_suffix(base, group_tag, extra=None):
    parts = [base]
    if group_tag:
        parts.append(group_tag)
    if extra:
        parts.append(extra)
    return "_".join(parts)


def _segment_label(dim, index, count):
    # Generate consistent segment labels based on the number of u and v splits.
    if count == 1:
        return ""
    if count == 2:
        return dim + ("1" if index == 0 else "2")
    if count == 3:
        if index == 1:
            return dim
        return dim + ("1" if index == 0 else "2")
    return dim + str(index + 1)


def _subgrid_suffix(u_index, u_count, v_index, v_count):
    # Generate consistent subgrid suffix based on u and v segment indices and counts.
    u_label = _segment_label("u", u_index, u_count)
    v_label = _segment_label("v", v_index, v_count)
    return u_label + v_label


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


class ControlGridPatchProxy:
    def __init__(self, obj):
        obj.Proxy = self
        obj.addProperty(
            "App::PropertyBool", "Rebuilding", "Internal", ""
        ).Rebuilding = False

    def onChanged(self, obj, prop):
        if prop in ("USplits", "VSplits"):
            # Avoid rebuilding while the document is restoring.
            if "Restore" in obj.State:
                return
            self.execute(obj)

    def execute(self, obj):
        if obj.Rebuilding:
            return
        obj.Rebuilding = True
        try:
            self._rebuild(obj)
        finally:
            obj.Rebuilding = False

    def _rebuild(self, obj):
        doc = obj.Document
        base_grid = getattr(obj, "BaseGrid", None)
        base_surface = getattr(obj, "BaseSurface", None)
        if base_grid is None or base_surface is None:
            return
        # On restore, the shape can be incomplete; guard before accessing faces.
        if not hasattr(base_surface, "Shape") or base_surface.Shape is None:
            return
        shape = base_surface.Shape
        # Access the surface via faces because Shape.Surface may not exist.
        if not hasattr(shape, "Faces") or not shape.Faces:
            return
        splits_u = _normalize_splits(list(obj.USplits))
        splits_v = _normalize_splits(list(obj.VSplits))
        if splits_u or splits_v:
            grid_type = getattr(base_grid, "object_type", "")
            if grid_type.startswith("ControlGrid44_3"):
                FreeCAD.Console.PrintError(
                    "SilkWorkflow: splits not supported for 3-sided grids.\n"
                )
                return
        for child in list(obj.Group):
            if child in (base_grid, base_surface):
                continue
            if child.Name.startswith("ControlGrid44_Sub") or child.Name.startswith(
                "CubicSurface_44_Sub"
            ):
                doc.removeObject(child.Name)

        if not splits_u and not splits_v:
            base_grid.ViewObject.Visibility = True
            base_surface.ViewObject.Visibility = True
            return
        base_grid.ViewObject.Visibility = False
        base_surface.ViewObject.Visibility = False
        intervals_u = _build_intervals(list(obj.USplits))
        intervals_v = _build_intervals(list(obj.VSplits))
        surface = shape.Faces[0].Surface
        group_tag = _group_id_tag(obj)
        for iu, (u0, u1) in enumerate(intervals_u):
            for iv, (v0, v1) in enumerate(intervals_v):
                suffix = _subgrid_suffix(iu, len(intervals_u), iv, len(intervals_v))
                sub_name = _name_with_suffix("ControlGrid44_Sub", group_tag, suffix)
                sub = _make_subgrid_from_surface(doc, surface, u0, u1, v0, v1, sub_name)
                sub.ViewObject.Proxy = 0
                sub.ViewObject.LineWidth = 1.00
                sub.ViewObject.LineColor = (0.67, 1.00, 1.00)
                sub.ViewObject.PointSize = 4.00
                sub.ViewObject.PointColor = (0.00, 0.33, 1.00)
                surf_name = _name_with_suffix("CubicSurface_44_Sub", group_tag, suffix)
                surf = doc.addObject("Part::FeaturePython", surf_name)
                AN.CubicSurface_44(surf, sub)
                surf.ViewObject.Proxy = 0
                surf.ViewObject.DisplayMode = "Shaded"
                surf.ViewObject.ShapeColor = (0.33, 0.67, 1.00)
                obj.addObject(sub)
                obj.addObject(surf)
        doc.recompute()


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
        group.addProperty(
            "App::PropertyFloatList", "USplits", "Splits", "U split params"
        )
        group.addProperty(
            "App::PropertyFloatList", "VSplits", "Splits", "V split params"
        )
        group.addProperty("App::PropertyLink", "BaseGrid", "Internal", "base grid")
        group.addProperty(
            "App::PropertyLink", "BaseSurface", "Internal", "base surface"
        )
        ControlGridPatchProxy(group)
        group.addProperty(
            "App::PropertyInteger", "GridId", "Internal", "unique grid id"
        )
        group.GridId = _next_grid_id(doc)
        group_tag = _group_id_tag(group)
        if len(controlpolys) == 4:
            grid = doc.addObject(
                "Part::FeaturePython",
                _name_with_suffix("ControlGrid44_4", group_tag),
            )
            AN.ControlGrid44_4(
                grid,
                controlpolys[0],
                controlpolys[1],
                controlpolys[2],
                controlpolys[3],
            )
        else:
            grid = doc.addObject(
                "Part::FeaturePython",
                _name_with_suffix("ControlGrid44_3", group_tag),
            )
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
        surf = doc.addObject(
            "Part::FeaturePython",
            _name_with_suffix("CubicSurface_44", group_tag),
        )
        # Create CubicSurface_44 from ControlGrid44 (TODO: could also be done via GUI command)
        AN.CubicSurface_44(surf, grid)
        surf.ViewObject.Proxy = 0
        surf.ViewObject.DisplayMode = "Shaded"
        surf.ViewObject.ShapeColor = (0.33, 0.67, 1.00)
        group.addObject(grid)
        group.addObject(surf)
        group.BaseGrid = grid
        group.BaseSurface = surf
        group.Proxy.execute(group)
        doc.recompute()


# Add a custom icon to the ControlGridPatch group
class ControlGridPatchViewProvider:
    def getIcon(self):
        return gridIconPath


# Register the commands with FreeCAD GUI
if Gui:
    Gui.addCommand("Silk_CreateBoundarySpline", CreateBoundarySplineCommand())
    Gui.addCommand("Silk_CreateControlGridPatch", CreateControlGridPatchCommand())
