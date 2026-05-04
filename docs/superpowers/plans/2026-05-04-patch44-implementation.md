# Patch44 + Simplified BoundarySpline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the multi-object workflow (BoundarySpline group + ControlGrid44 + CubicSurface_44 + ControlGridPatch group) with two single FeaturePython objects.

**Architecture:** Two new FeaturePython classes following existing ArachNURBS patterns. BoundarySpline aggregates 4 poles from a sketch. Patch44 reads 4 BoundarySpline edges, computes a 16-pole grid and surface internally, supports U/V subdivision stored as internal arrays. No changes to ArachNURBS. TDD: write failing test, implement, verify pass.

**Tech Stack:** FreeCAD v1.1 Python API, ArachNURBS (for ControlGrid44_4, CubicSurface_44), FreeCAD MCP server.

---

## File Map

| Action | Path | Responsibility |
|--------|------|----------------|
| CREATE | `BoundarySpline.py` | Single FeaturePython — 4-pole edge from sketch |
| CREATE | `SilkPatch44.py` | Combined Patch44 FeaturePython — grid+surface+subgrids |
| MODIFY | `InitGui.py` | Add BoundarySpline and Silk_Patch44 to toolbar |
| CREATE | `Tests/test_boundaryspline.py` | TDD tests for BoundarySpline |
| CREATE | `Tests/test_patch44.py` | TDD tests for Patch44 |

---

### Task 1: Test — BoundarySpline creation from a 3L sketch

**Files:**
- Create: `Tests/test_boundaryspline.py`

- [ ] **Step 1: Write the failing test**

```python
"""
Tests for new BoundarySpline FeaturePython object.
Each test takes a FreeCAD doc and returns {"pass": bool, "errors": [str, ...], "checks": [...]}
"""
import FreeCAD
import Part
from FreeCAD import Gui


def check(cond, msg, errors):
    if not cond:
        errors.append(msg)
    return cond


def test_boundaryspline_3l(doc):
    """Create BoundarySpline from sketch with 3 visible line segments."""
    errors, checks = [], []

    # Ensure the module is loaded
    import BoundarySpline
    from FreeCAD import Gui

    # Create a 3-line sketch
    sk = doc.addObject("Sketcher::SketchObject", "Sketch")
    sk.Placement = FreeCAD.Placement(FreeCAD.Vector(0,0,0), FreeCAD.Rotation(0,0,0))
    sk.addGeometry([
        Part.LineSegment(FreeCAD.Vector(0,0,0), FreeCAD.Vector(16,0,0)),
        Part.LineSegment(FreeCAD.Vector(16,0,0), FreeCAD.Vector(33,0,0)),
        Part.LineSegment(FreeCAD.Vector(33,0,0), FreeCAD.Vector(50,0,0)),
    ])
    doc.recompute()

    Gui.Selection.clearSelection()
    Gui.Selection.addSelection(sk)
    Gui.runCommand("BoundarySpline")

    # Should find exactly one BoundarySpline with 4 poles
    bs_list = [o for o in doc.Objects if o.Name.startswith("BoundarySpline") and hasattr(o, "Poles")]
    check(len(bs_list) == 1, f"Expected 1 BoundarySpline, got {len(bs_list)}", errors)
    if bs_list:
        bs = bs_list[0]
        check(len(bs.Poles) == 4, f"Expected 4 poles, got {len(bs.Poles)}", errors)
        check(bs.Shape is not None, "BoundarySpline has no Shape", errors)
        checks.append(f"BoundarySpline created with {len(bs.Poles)} poles")

    return {"pass": len(errors) == 0, "errors": errors, "checks": checks}
```

- [ ] **Step 2: Run the failing test via MCP**

Send via `FreeCAD_execute_code`:
```python
import sys
sys.path.insert(0, "/home/mo/.local/share/FreeCAD/v1-1/Mod/Silk")
from Tests.mcp_harness import run_tests
from Tests.test_boundaryspline import test_boundaryspline_3l
run_tests(test_boundaryspline_3l)
```

Expected: FAIL or "No such command 'BoundarySpline'" because the module doesn't exist yet.

---

### Task 2: Implement BoundarySpline FeaturePython

**Files:**
- Create: `BoundarySpline.py`

- [ ] **Step 1: Write the BoundarySpline module**

```python
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

    def onDocumentRestored(self, obj):
        # Version migration — for now just recompute
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

        # Count visible line segments to determine mode
        visible_count = 0
        visible_line_count = 0
        for i in range(geom_count):
            if not sketch.getConstruction(i):
                visible_count += 1
                if geom[i].TypeId == "Part::GeomLineSegment":
                    visible_line_count += 1

        if visible_line_count == 3 and visible_count == visible_line_count:
            # 3L mode — delegate to ArachNURBS
            from ArachNURBS import ControlPoly4_3L
            dummy = FreeCAD.ActiveDocument.addObject("Part::FeaturePython", "_bs_tmp")
            ControlPoly4_3L(dummy, sketch)
            if fp.reverse:
                fp.Poles = list(reversed(dummy.Poles))
                fp.Weights = list(reversed(dummy.Weights))
            else:
                fp.Poles = dummy.Poles
                fp.Weights = dummy.Weights
            fp.Legs = dummy.Legs
            FreeCAD.ActiveDocument.removeObject(dummy.Name)
        else:
            # FirstElement mode
            from ArachNURBS import ControlPoly4_FirstElement
            dummy = FreeCAD.ActiveDocument.addObject("Part::FeaturePython", "_bs_tmp")
            ControlPoly4_FirstElement(dummy, sketch)
            if fp.reverse:
                fp.Poles = list(reversed(dummy.Poles))
                fp.Weights = list(reversed(dummy.Weights))
            else:
                fp.Poles = dummy.Poles
                fp.Weights = dummy.Weights
            fp.Legs = dummy.Legs
            FreeCAD.ActiveDocument.removeObject(dummy.Name)

        # Build the cubic curve for display
        if len(fp.Poles) == 4:
            curve = Part.BSplineCurve()
            curve.buildFromPoles(fp.Poles)
            fp.Shape = curve.toShape()
        else:
            fp.Shape = Part.Shape(fp.Legs)


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
                bs.ViewObject.Proxy = 0
                bs.ViewObject.LineWidth = 2.00
                bs.ViewObject.LineColor = (0.00, 1.00, 0.00)
                bs.ViewObject.PointSize = 4.00
                bs.ViewObject.PointColor = (0.00, 0.33, 1.00)
                doc.recompute()

    def IsActive(self):
        return Gui is not None


Gui.addCommand("BoundarySpline", CreateBoundarySpline())
```

- [ ] **Step 2: Run the test to verify it passes**

Send via `FreeCAD_execute_code`:
```python
import sys
sys.path.insert(0, "/home/mo/.local/share/FreeCAD/v1-1/Mod/Silk")
import BoundarySpline  # register the command
from Tests.mcp_harness import run_tests
from Tests.test_boundaryspline import test_boundaryspline_3l
run_tests(test_boundaryspline_3l)
```

Expected: PASS — BoundarySpline created with 4 poles, valid Shape.

- [ ] **Step 3: Commit**

```bash
git add BoundarySpline.py Tests/test_boundaryspline.py
git commit -m "feat: add BoundarySpline single FeaturePython (TDD)"
```

---

### Task 3: Test — Patch44 creation from 4 BoundarySplines

**Files:**
- Create: `Tests/test_patch44.py`

- [ ] **Step 1: Write the failing test**

```python
"""
Tests for Patch44 FeaturePython object.
"""
import FreeCAD
import Part
from FreeCAD import Gui
from FreeCAD import Vector


def check(cond, msg, errors):
    if not cond:
        errors.append(msg)
    return cond


def test_patch44_4_sided(doc):
    """Create Patch44 from 4 BoundarySpline edges."""
    errors, checks = [], []

    import ArachNURBS as AN
    import SilkPatch44

    # Create 4 edge polys directly (to avoid sketch dependency)
    edge_data = [
        [Vector(0,0,0), Vector(16,0,0), Vector(33,0,0), Vector(50,0,0)],
        [Vector(50,0,0), Vector(50,16,0), Vector(50,33,0), Vector(50,50,0)],
        [Vector(50,50,0), Vector(33,50,0), Vector(16,50,0), Vector(0,50,0)],
        [Vector(0,50,0), Vector(0,33,0), Vector(0,16,0), Vector(0,0,0)],
    ]
    edges = []
    for i, poles in enumerate(edge_data):
        e = doc.addObject("Part::FeaturePython", f"Edge_{i}")
        e.addProperty("App::PropertyVectorList", "Poles", "", "").Poles = poles
        e.addProperty("App::PropertyFloatList", "Weights", "", "").Weights = [1.0]*4
        e.addProperty("Part::PropertyGeometryList", "Legs", "", "").Legs = [
            Part.LineSegment(poles[j], poles[j+1]) for j in range(3)
        ]
        e.Proxy = 0
        e.Shape = Part.Shape(e.Legs)
        edges.append(e)
    doc.recompute()

    # Create Patch44
    Gui.Selection.clearSelection()
    for e in edges:
        Gui.Selection.addSelection(e)
    Gui.runCommand("Silk_Patch44")

    patches = [o for o in doc.Objects if o.Name.startswith("Patch44") and hasattr(o, "Poles")]
    check(len(patches) == 1, f"Expected 1 Patch44, got {len(patches)}", errors)
    if patches:
        p = patches[0]
        check(len(p.Poles) == 16, f"Expected 16 poles, got {len(p.Poles)}", errors)
        check(p.Shape is not None, "Patch44 has no Shape", errors)
        checks.append(f"Patch44 created with {len(p.Poles)} poles")

    return {"pass": len(errors) == 0, "errors": errors, "checks": checks}


def test_patch44_subdivision(doc):
    """Patch44 with USplits and VSplits — verify subgrids are created (internally)."""
    errors, checks = [], []

    import SilkPatch44

    edge_data = [
        [Vector(0,0,0), Vector(16,0,0), Vector(33,0,0), Vector(50,0,0)],
        [Vector(50,0,0), Vector(50,16,0), Vector(50,33,0), Vector(50,50,0)],
        [Vector(50,50,0), Vector(33,50,0), Vector(16,50,0), Vector(0,50,0)],
        [Vector(0,50,0), Vector(0,33,0), Vector(0,16,0), Vector(0,0,0)],
    ]
    edges = []
    for i, poles in enumerate(edge_data):
        e = doc.addObject("Part::FeaturePython", f"Edge_{i}")
        e.addProperty("App::PropertyVectorList", "Poles", "", "").Poles = poles
        e.addProperty("App::PropertyFloatList", "Weights", "", "").Weights = [1.0]*4
        legs = [Part.LineSegment(poles[j], poles[j+1]) for j in range(3)]
        e.addProperty("Part::PropertyGeometryList", "Legs", "", "").Legs = legs
        e.Proxy = 0; e.Shape = Part.Shape(legs)
        edges.append(e)
    doc.recompute()

    Gui.Selection.clearSelection()
    for e in edges:
        Gui.Selection.addSelection(e)
    Gui.runCommand("Silk_Patch44")

    patches = [o for o in doc.Objects if o.Name.startswith("Patch44") and hasattr(o, "Poles")]
    check(len(patches) == 1, "No Patch44 created", errors)
    if not patches:
        return {"pass": False, "errors": errors, "checks": checks}

    p = patches[0]
    p.USplits = [0.3]
    doc.recompute()
    # Verify subgrid poles exist (internal attribute)
    has_subgrids = hasattr(p.Proxy, "_subgrids") and len(p.Proxy._subgrids) > 0
    check(has_subgrids, "No subgrids after setting USplits=[0.3]", errors)
    if has_subgrids:
        checks.append(f"{len(p.Proxy._subgrids)} subgrids created")

    p.ShowSubgrids = True
    doc.recompute()
    check(p.Shape is not None, "No Shape after enabling ShowSubgrids", errors)
    checks.append("Subgrid display toggled")

    return {"pass": len(errors) == 0, "errors": errors, "checks": checks}
```

- [ ] **Step 2: Run the failing test via MCP**

Send via `FreeCAD_execute_code`:
```python
import sys
sys.path.insert(0, "/home/mo/.local/share/FreeCAD/v1-1/Mod/Silk")
from Tests.mcp_harness import run_tests
from Tests.test_patch44 import test_patch44_4_sided
run_tests(test_patch44_4_sided)
```

Expected: FAIL — "No such command 'Silk_Patch44'"

---

### Task 4: Implement Patch44 FeaturePython

**Files:**
- Create: `SilkPatch44.py`

- [ ] **Step 1: Write the Patch44 module**

```python
#    This file is part of Silk
#    (c) 2025
#
#    NURBS Surface modeling tools focused on low degree and seam continuity (FreeCAD Workbench)
#
#    Patch44 — single FeaturePython combining ControlGrid44 + CubicSurface_44 + subgrids.
#    Takes 4 boundary edges (anything with 4 Poles), creates grid+surface, supports subdivision.

import FreeCAD
import Part
from FreeCAD import Gui
import ArachNURBS as AN
from popup import tipsDialog
import Silk_tooltips

tooltip = "Create a 44 patch from 4 boundary edges. Select 4 boundary objects (with 4 Poles each)."
moreInfo = tooltip

import os, Silk_dummy
path_Silk = os.path.dirname(Silk_dummy.__file__)
path_Silk_icons = os.path.join(path_Silk, "Resources", "Icons")
iconPath = path_Silk_icons + "/ControlGrid44.svg"


def _normalize_splits(values):
    """Sort and filter split values to (0,1)."""
    return sorted(set(v for v in values if 0.0 < v < 1.0))


def _build_intervals(values):
    """Convert split positions to interval list."""
    splits = _normalize_splits(list(values))
    if not splits:
        return [(0.0, 1.0)]
    return list(zip([0.0] + splits, splits + [1.0]))


class Patch44:
    def __init__(self, obj, poly0, poly1, poly2, poly3):
        latest_version = "0.01"

        obj.addProperty("App::PropertyLink", "Poly0", "C1 - Inputs", "first boundary edge").Poly0 = poly0
        obj.addProperty("App::PropertyLink", "Poly1", "C1 - Inputs", "second boundary edge").Poly1 = poly1
        obj.addProperty("App::PropertyLink", "Poly2", "C1 - Inputs", "third boundary edge").Poly2 = poly2
        obj.addProperty("App::PropertyLink", "Poly3", "C1 - Inputs", "fourth boundary edge").Poly3 = poly3
        obj.addProperty("App::PropertyFloat", "tolerance", "C1 - Inputs",
                        "endpoint matching tolerance").tolerance = AN.default_tol
        obj.addProperty("App::PropertyBool", "reverse", "C1 - Inputs",
                        "reverse the grid parameter direction").reverse = False
        obj.addProperty("App::PropertyFloatList", "USplits", "S1 - Subdivision",
                        "U split parameters (0-1)").USplits = []
        obj.addProperty("App::PropertyFloatList", "VSplits", "S1 - Subdivision",
                        "V split parameters (0-1)").VSplits = []
        obj.addProperty("App::PropertyBool", "ShowSurface", "S2 - Display",
                        "show the surface").ShowSurface = True
        obj.addProperty("App::PropertyBool", "ShowGrid", "S2 - Display",
                        "show the control grid").ShowGrid = True
        obj.addProperty("App::PropertyBool", "ShowSubgrids", "S2 - Display",
                        "show subdivided subgrids instead of base surface").ShowSubgrids = False
        obj.addProperty("App::PropertyVectorList", "Poles", "C2 - Outputs", "Poles").Poles
        obj.addProperty("App::PropertyFloatList", "Weights", "C2 - Outputs", "Weights").Weights
        obj.addProperty("Part::PropertyGeometryList", "Legs", "C2 - Outputs", "grid segments").Legs
        obj.addProperty("App::PropertyString", "object_type", "C3 - Identifiers",
                        "workbench class").object_type = "Patch44"
        obj.setEditorMode("object_type", 1)
        obj.addProperty("App::PropertyString", "object_version", "C3 - Identifiers",
                        "class version").object_version = latest_version
        obj.setEditorMode("object_version", 1)
        obj.addProperty("App::PropertyString", "internalName", "C3 - Identifiers",
                        "permanent internal FreeCAD name").internalName = obj.Name
        obj.setEditorMode("internalName", 1)
        obj.Proxy = self

        # Internal subgrid storage (not serialized)
        self._subgrids = []
        self._subsurfaces = []

    def onDocumentRestored(self, obj):
        latest_version = "0.01"
        if not hasattr(obj, "object_version") or obj.object_version != latest_version:
            # version migration — will recompute in execute()
            pass
        obj.recompute()

    def onChanged(self, fp, prop):
        if prop in ("USplits", "VSplits", "ShowSurface", "ShowGrid", "ShowSubgrids", "reverse"):
            if 'Restore' not in fp.State:
                fp.recompute()

    def getSubgrid(self, u0, u1, v0, v1):
        """Return (poles, weights) for a parameter range on the base surface.
        Used by future blend tools."""
        if not hasattr(self, "_base_surface") or self._base_surface is None:
            return None, None
        seg = self._base_surface.copy()
        seg.segment(u0, u1, v0, v1)
        return seg.getPoles(), seg.getWeights()

    def execute(self, fp):
        if 'Restore' in fp.State:
            return

        # 1. Build 16-pole grid from 4 edges
        dummy_grid = FreeCAD.ActiveDocument.addObject("Part::FeaturePython", "_patch_tmp")
        AN.ControlGrid44_4(dummy_grid, fp.Poly0, fp.Poly1, fp.Poly2, fp.Poly3)
        poles = dummy_grid.Poles
        weights = dummy_grid.Weights
        legs = dummy_grid.Legs
        FreeCAD.ActiveDocument.removeObject(dummy_grid.Name)

        # Check if grid was created (endpoints may have been mismatched)
        if not poles or len(poles) != 16:
            fp.Poles = []
            fp.Weights = []
            fp.Legs = []
            return

        fp.Poles = poles
        fp.Weights = weights

        # 2. Build surface
        surf = FreeCAD.ActiveDocument.addObject("Part::FeaturePython", "_patch_surf_tmp")
        AN.CubicSurface_44(surf, fp)
        self._base_surface = surf.Shape.Faces[0].Surface.copy() if surf.Shape and surf.Shape.Faces else None
        FreeCAD.ActiveDocument.removeObject(surf.Name)

        # 3. Compute subgrids
        self._subgrids = []
        self._subsurfaces = []
        u_splits = list(fp.USplits) if fp.USplits else []
        v_splits = list(fp.VSplits) if fp.VSplits else []

        if u_splits or v_splits:
            intervals_u = _build_intervals(u_splits)
            intervals_v = _build_intervals(v_splits)
            if self._base_surface:
                shapes = []
                grid_shapes = []
                for u0, u1 in intervals_u:
                    uv_grids = []
                    for v0, v1 in intervals_v:
                        seg = self._base_surface.copy()
                        seg.segment(u0, u1, v0, v1)
                        sub_poles = [[seg.getPoles()[r][c]
                                      for c in range(4)]
                                     for r in range(4)]
                        # Flatten to 16-element list
                        flat = []
                        for r in range(4):
                            for c in range(4):
                                flat.append(sub_poles[r][c])
                        self._subgrids.append(flat)
                        # Create sub-surface shape
                        sub_surf = seg.toShape()
                        if sub_surf:
                            shapes.append(sub_surf)
                        # Create sub-grid lines
                        grid_shapes.append(AN.drawGrid(flat, 4))
                self._subsurfaces = shapes
                fp.Legs = grid_shapes
        else:
            fp.Legs = legs

        # 4. Set display Shape based on toggles
        shapes_to_compound = []
        if fp.ShowSubgrids and self._subsurfaces:
            shapes_to_compound.extend(self._subsurfaces)
        elif fp.ShowSurface and self._base_surface:
            # Rebuild surface from stored poles
            surf2 = FreeCAD.ActiveDocument.addObject("Part::FeaturePython", "_patch_surf2_tmp")
            AN.CubicSurface_44(surf2, fp)
            if surf2.Shape:
                shapes_to_compound.append(surf2.Shape)
            FreeCAD.ActiveDocument.removeObject(surf2.Name)

        if fp.ShowGrid and fp.Legs:
            for leg in fp.Legs:
                if hasattr(leg, "toShape"):
                    shapes_to_compound.append(leg.toShape())

        if shapes_to_compound:
            fp.Shape = Part.Compound(shapes_to_compound)
        else:
            fp.Shape = Part.Shape()


class CreateSilkPatch44:
    """GUI command — select 4 boundary edges → Patch44."""

    def GetResources(self):
        return {'Pixmap': iconPath, 'MenuText': 'Silk Patch44', 'ToolTip': tooltip}

    def Activated(self):
        sel = Gui.Selection.getSelection()
        if len(sel) == 0:
            tipsDialog("Silk: Patch44", moreInfo)
            return
        if len(sel) != 4:
            FreeCAD.Console.PrintError("Silk: Patch44 requires exactly 4 selected edges.\n")
            return

        doc = FreeCAD.ActiveDocument
        obj = doc.addObject("Part::FeaturePython", "Patch44")
        Patch44(obj, sel[0], sel[1], sel[2], sel[3])
        obj.ViewObject.Proxy = 0
        obj.ViewObject.LineWidth = 1.50
        obj.ViewObject.LineColor = (0.67, 1.00, 1.00)
        obj.ViewObject.PointSize = 4.00
        obj.ViewObject.PointColor = (0.00, 0.33, 1.00)
        doc.recompute()
        FreeCAD.Console.PrintMessage(f"Patch44 created: {obj.Name}\n")

    def IsActive(self):
        return Gui is not None


Gui.addCommand("Silk_Patch44", CreateSilkPatch44())
```

- [ ] **Step 2: Run tests to verify passes**

Send via `FreeCAD_execute_code`:
```python
import sys
sys.path.insert(0, "/home/mo/.local/share/FreeCAD/v1-1/Mod/Silk")
import SilkPatch44
from Tests.mcp_harness import run_tests
from Tests.test_patch44 import test_patch44_4_sided, test_patch44_subdivision
run_tests(test_patch44_4_sided, test_patch44_subdivision)
```

Expected: BOTH PASS — 16 poles, surface Shape, subgrids populated.

- [ ] **Step 3: Commit**

```bash
git add SilkPatch44.py Tests/test_patch44.py
git commit -m "feat: add Patch44 combined FeaturePython with subgrid support (TDD)"
```

---

### Task 5: Merge InitGui.py and full verification

**Files:**
- Modify: `InitGui.py`

- [ ] **Step 1: Add imports to InitGui.py**

In `InitGui.py`, add after the existing imports:

```python
        import BoundarySpline
        import SilkPatch44
```

And add commands to the toolbar list:

```python
            "BoundarySpline",
            "Silk_Patch44",
```

(Place them after `"Point_onCurve"` and before `"ControlPoly4_segment"` respectively.)

- [ ] **Step 2: Run full test suite**

Send via `FreeCAD_execute_code`:
```python
import sys
sys.path.insert(0, "/home/mo/.local/share/FreeCAD/v1-1/Mod/Silk")
import BoundarySpline, SilkPatch44
from Tests.mcp_harness import run_tests
from Tests.test_boundaryspline import test_boundaryspline_3l
from Tests.test_patch44 import test_patch44_4_sided, test_patch44_subdivision
run_tests(test_boundaryspline_3l, test_patch44_4_sided, test_patch44_subdivision)
```

Expected: ALL 3 PASS.

- [ ] **Step 3: Commit**

```bash
git add InitGui.py
git commit -m "feat: add BoundarySpline and Silk_Patch44 commands to toolbar"
```

- [ ] **Step 4: Show git log**

```bash
git log --oneline -5
```
