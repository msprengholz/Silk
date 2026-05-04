# Silk Workbench — Patch44 + Simplified BoundarySpline Design

**Date:** 2026-05-04  
**Author:** AI agent (OpenCode)  
**Status:** Draft

## Overview

Replace the multi-object workflow (BoundarySpline group + ControlPoly4 + CubicCurve_4 + ControlGrid44 + CubicSurface_44 + ControlGridPatch group) with two single FeaturePython objects: a streamlined `BoundarySpline` and a combined `Patch44`. The old commands remain in the toolbar for low-level access.

## Architecture

### Object Model

```
BoundarySpline (FeaturePython, 1 object)
├─ Properties: Sketch (link), Poles (4 vec), Weights (4 float), Legs, object_type, object_version
├─ execute(): compute poles from Sketch geometry, set Shape
├─ Auto-serializes via standard FreeCAD properties
└─ onDocumentRestored(): version migration

Patch44 (FeaturePython, 1 object)
├─ Properties: Boundary0..3 (links), Poles (16 vec), Weights (16 float),
│             USplits, VSplits, ShowSubgrids, ShowSurface, ShowGrid
├─ execute(): compute grid + surface from 4 BoundarySpline edges,
│             optionally subdivide, set Shape per display toggles
├─ Subgrids: stored internally, recomputed from USplits/VSplits on each execute()
├─ getSubgrid(u0,u1,v0,v1) → poles, weights   (API for blend tool)
└─ onDocumentRestored(): version migration
```

### File Changes

| File | Action | Purpose |
|------|--------|---------|
| `BoundarySpline.py` | **Create** | Single FeaturePython BoundarySpline class + GUI command |
| `SilkPatch44.py` | **Create** | Patch44 FeaturePython + GUI command + subdivision logic |
| `ArachNURBS.py` | **Edit** | Add `snap_endpoints` flag to `ControlGrid44_4.execute()` |
| `InitGui.py` | **Edit** | Add `BoundarySpline` and `Silk_Patch44` commands to toolbar |
| `Tests/` | **Add** | Smoke tests for new objects |

### What stays unchanged

- `ControlPoly4.py`, `CubicCurve_4.py` — low-level building blocks, still on toolbar
- `ControlGrid44.py`, `CubicSurface_44.py` — low-level, still on toolbar
- `ControlGrid64_2Grid44.py`, `CubicSurface_64.py` — blend building blocks for future
- `SilkReloadManager.py`, `Reload_Silk.py` — development flow
- All other existing commands

### What is deprecated (not removed)

- `SilkWorkflow.py` — old CreateBoundarySplineCommand and CreateControlGridPatchCommand remain for backward compat but are superseded

## Data Flow

```
Sketch (3L mode: 3 line segments)
  → BoundarySpline.Activated() reads sketch → AN.ControlPoly4_3L → 4 poles
  → Shape = cubic curve from poles

4× BoundarySpline
  → Patch44.Activated() reads 4 boundary poles → AN.ControlGrid44_4() → 16-pole grid
  → AN.CubicSurface_44() → BSpline surface
  → If USplits/VSplits: surface.segment() → subgrid pole arrays (internal)
  → Shape selection logic:
      ShowSurface=Y, ShowSubgrids=N, ShowGrid=N → base surface
      ShowSurface=Y, ShowSubgrids=Y, ShowGrid=N → sub-surfaces (compound)
      ShowSurface=N, ShowSubgrids=N, ShowGrid=Y → grid lines
      ShowSurface=Y, ShowSubgrids=N, ShowGrid=Y → base surface + grid lines
```

## Serialization

- Standard `addProperty("App::PropertyVectorList", "Poles", ...)` → auto-saved by FreeCAD
- Subgrids are NOT stored — recomputed from USplits/VSplits on restore
- Version migration via `object_version` string + `onDocumentRestored()` (existing ArachNURBS pattern)
- `onDocumentRestored` calls `execute()` which handles Shape recomputation

### Version Migration Pattern

```python
def onDocumentRestored(self, obj):
    latest_version = "0.01"
    if not hasattr(obj, "object_version") or obj.object_version != latest_version:
        # capture old props, remove them, re-add in new format
        ...
        obj.recompute()
```

## GUI Commands

| Command | Class | Toolbar Label |
|---------|-------|---------------|
| `BoundarySpline` | `BoundarySpline` (new) | "Boundary Spline" |
| `Silk_Patch44` | `SilkPatch44` (new) | "44 Patch" |

### Toolbar Layout (proposed)

```
[ControlPoly4] [CubicCurve_4] [BoundarySpline] [Silk_Patch44] [Reload]
   (old)          (old)           (NEW!)           (NEW!)        (keep)
```

Plus all existing low-level commands that were already on the toolbar.

## Subgrid Architecture (internal to Patch44)

```
execute():
  1. Read Poles/Weights from 4 BoundarySpline children
  2. Call AN.ControlGrid44_4(grid, poly0, poly1, poly2, poly3)
     — grid.Poles, grid.Weights populated
  3. Call AN.CubicSurface_44(surf, grid) — surf.Shape = BSpline surface
  4. If USplits or VSplits:
       intervals_u = build_intervals(USplits)
       intervals_v = build_intervals(VSplits)
       for (u0,u1) in intervals_u:
         for (v0,v1) in intervals_v:
           seg = surface.copy(); seg.segment(u0,u1,v0,v1)
           subgrid = seg.getPoles()  → store in self._subgrids
           subsurf = seg → store in self._subsurfaces
  5. Set obj.Shape based on display toggles:
       ShowSurface → base/sub surfaces
       ShowGrid → grid lines
       ShowSubgrids → subgrid lines instead of base grid
```

## Boundaries

Not covered in this design:
- Auto-blend (Phase 2) — will consume Patch44 objects via getSubgrid()
- Corner blend (Phase 3) — fills 4-sided holes between 2-edge blends
- The BoundarySpline edge object is designed to be reusable across multiple Patch44 objects

## Testing

- `Tests/test_boundaryspline.py` — create BoundarySpline from sketch, verify 4 poles, verify Shape
- `Tests/test_patch44.py` — create 4 BoundarySplines → Patch44, verify 16 poles, verify surface Shape
- `Tests/test_patch44_subdivision.py` — set USplits/VSplits, verify subgrid arrays populated
- All tests runnable via MCP `run_tests()` harness
