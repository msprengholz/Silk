# Silk Workbench — Agent Notes

## Agent skills

### Issue tracker

GitHub Issues on `msprengholz/Silk` (the fork), via the `gh` CLI — always pass `-R msprengholz/Silk` or the `upstream` remote is inferred. See `docs/agents/issue-tracker.md`.

### Triage labels

Default five-role vocabulary (`needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, `wontfix`), plus `wayfinder:*` labels. See `docs/agents/triage-labels.md`.

### Domain docs

Single-context: `GLOSSARY.md` + `docs/adr/` at the repo root. See `docs/agents/domain.md`.

## Core Object Architecture

### Edge (`SilkEdge.py`)
- `Part::FeaturePython` (renders Shape in 3D view)
- Properties: Sketches (PropertyLinkList), Poles (4 vec), Weights, Legs, object_type="Edge"
- Display toggles: ShowCurve, ShowPolygon
- Custom view provider: `EdgeViewProvider` (custom tree icon)
- Sketches are linked via `Sketches` property (not tree children — Part::FeaturePython can't nest)

### Patch44 (`SilkPatch44.py`)
- `Part::FeaturePython` (not group)
- 16 poles + 16 weights (4×4 grid)
- Subgrids stored internally in `_subgrids` and `_subsurfaces` (not in FreeCAD tree)
- Display toggles: ShowSurface, ShowGrid, ShowSubgrids, AutoHideBlend
- Linked BlendStrips auto-hide the blended subgrid strip via `_HideSubgridIdx`
- Custom view provider: `Patch44ViewProvider` (custom tree icon)

### BlendStrip (`SilkBlend.py`)
- `Part::FeaturePython`
- Properties: PatchA, PatchB (PropertyLinks), tolerance, Poles (24), Weights, Legs
- Auto-detects shared edge between two Patch44 objects
- Auto-updates when patches' USplits/VSplits change
- Custom view provider: `BlendStripViewProvider` (custom tree icon)
- Surface built via `AN.CubicSurface_64` (NOT manual knot insertion)

## Full Workflow Pipeline
```
Sketches (9 reference sketches)
  → Edges (7, each linked to 1-2 sketches via Sketches property)
    → Patch44 (2 from 4 Edges each)
      → BlendStrip (1 between the 2 Patch44)
```

## Module Reload Pattern
Each MCP `execute_code` call runs in the same FreeCAD process. Python caches modules:
```python
for m in list(sys.modules.keys()):
    if 'SilkPatch44' in m or 'SilkBlend' in m or 'SilkEdge' in m:
        del sys.modules[m]
import SilkPatch44, SilkBlend, SilkEdge
```

## Shared Edge Detection & Blend Algorithm

### Step 1: Find shared corners
```python
corners = [Poles[0], Poles[3], Poles[15], Poles[12]]
# = [p00, p03, p33, p30] = [U0V0, U1V0, U1V1, U0V1]
```
Compare corner[i] vs corner[j] within tolerance 0.01. Collect matching pairs.

### Step 2: Determine edge type
- (0,1) or (1,0) = U0 (V=0, U varies along row 0)
- (1,2) or (2,1) = V1 (U=1, V varies along col 3)
- (2,3) or (3,2) = U1 (V=1, U varies along row 3)
- (3,0) or (0,3) = V0 (U=0, V varies along col 0)

### Step 3: Subdivide perpendicular to shared edge
| Shared edge | Split direction | Strip location |
|-------------|----------------|----------------|
| U0 (row 0)  | VSplits=[0.1]  | subgrid[0] (V=0→0.1) |
| U1 (row 3)  | VSplits=[0.9]  | subgrid[1] (V=0.9→1.0) |
| V0 (col 0)  | USplits=[0.1]  | subgrid[0] (U=0→0.1) |
| V1 (col 3)  | USplits=[0.9]  | subgrid[1] (U=0.9→1.0) |

### Step 4: Extract rows/columns from strips
Subgrid flat: `poles[U][V]` = `flat[U*4 + V]` (U is first dimension in FreeCAD)

**CRITICAL extraction rule:**
- If shared edge runs ALONG U (row): perpendicular is V → take COLUMNS at const U
- If shared edge runs ALONG V (col): perpendicular is U → take ROWS at const V

Row at V=i: `flat[0+i, 4+i, 8+i, 12+i]` = varying U, constant V
Col at U=j: `flat[4j+0, 4j+1, 4j+2, 4j+3]` = varying V, constant U

### Step 5: Pair rows/columns across patches
Corner matching gives the index mapping. Shared edge direction may be REVERSED.
- Example: left corners[0]=(0,0,40) matches right corners[1]=(0,0,40), left corners[3]=(0,50,0) matches right corners[0]=(0,50,0)
- Then left V=0 ↔ right U=3, left V=3 ↔ right U=0, mapping is left V=i ↔ right U=3-i (reversed)

### Step 6: Blend
For each paired row/col:
1. Reverse the LEFT row so it goes OUTER→SHARED (list(reversed(row)))
2. Keep the RIGHT column as SHARED→OUTER
3. Call `AN.blend_poly_2x4_1x6(l_row_rev, [1.0]*4, r_col, [1.0]*4, 2.0, 2.0, 2.0, 2.0)`
4. Collect 6-pole results

Stack 4 result rows into a 6×4 grid. Create blend surface via `AN.CubicSurface_64`:
```python
tmp = doc.addObject("Part::FeaturePython", "_tmp")
AN.CubicSurface_64(tmp, blend_grid_obj)
tmp.recompute()
surf_shape = tmp.Shape
doc.removeObject(tmp.Name)
```

**NEVER use `buildFromPolesMultsKnots` or manual `insertUKnot` for blend surfaces** — the knot vector is non-trivial. Always use `AN.CubicSurface_64`.

### Key gotchas
- `segment(u0, u1, v0, v1)` — first arg is U range, second is V range
- Surface `getPoles()` returns `poles[U][V]` (U is first dimension)
- `blend_poly_2x4_1x6` expects: poles_0 goes OUTER→SHARED, poles_1 goes SHARED→OUTER

## Auto-Update Chain

When a Patch44's USplits/VSplits change, the BlendStrip auto-updates:

1. `Patch44.onChanged("USplits")` → `fp.touch()` + `fp.recompute()` → `execute()` runs
2. `execute()` searches doc for BlendStrip objects linked to this patch → calls `blend.touch()`
3. Next `doc.recompute()` → BlendStrip is touched → `execute()` reads updated subgrids → blend recomputes

## Display Toggles (Patch44)

- **ShowSurface**: controls surface visibility (base or subdivided)
- **ShowGrid**: controls grid line visibility
- **ShowSubgrids**: when True and splits exist, shows subdivided surfaces instead of smooth surface
- **AutoHideBlend**: when True and a BlendStrip links to this patch, hides the blended subgrid strip (via `_HideSubgridIdx` property set by BlendStrip)

## Surface Creation for Patch44 (bicubic Bezier)
```python
surf = Part.BSplineSurface()
surf.increaseDegree(3, 3)
for knot, mult in [(0.0, 4), (1.0, 4)]:
    surf.insertUKnot(knot, mult, 1e-7)
    surf.insertVKnot(knot, mult, 1e-7)
for r in range(4):
    for c in range(4):
        idx = r * 4 + c
        surf.setPole(c + 1, r + 1, poles[idx], weights[idx])
```

## View Provider Pattern
Each FeaturePython object needs a custom view provider for tree icons:
```python
class MyViewProvider:
    def __init__(self, vobj):
        vobj.Proxy = self
    def getIcon(self):
        return iconPath  # path to SVG
    def attach(self, vobj):
        self.ViewObject = vobj
    def updateData(self, obj, prop):
        return True
    def __getstate__(self):
        return None
    def __setstate__(self, state):
        return None
```
Usage: `MyViewProvider(obj.ViewObject)` (NOT `obj.ViewObject.Proxy = MyViewProvider(obj.ViewObject)`)

## Test Infrastructure

### MCP Harness
- `Tests/mcp_harness.py`: `run_tests(*funcs)`, each func takes doc, returns dict
- `Tests/test_patch44_comprehensive.py`: All Patch44 tests with `CaptureConsole`
- `Tests/test_blend.py`: Blend strip tests

### Console Error Capture
```python
class CaptureConsole:
    def __enter__(self):
        self._orig_error = FreeCAD.Console.PrintError
        FreeCAD.Console.PrintError = lambda msg: (self.errors.append(msg), self._orig_error(msg))
        return self
    def __exit__(self, *args):
        FreeCAD.Console.PrintError = self._orig_error
```

### Test suite (two launchers, one suite)
- `Tests/suite.py` — auto-discovers `Tests/test_*.py` modules (uses `ALL_TESTS` if present, else top-level `test_*` functions)
- `Tests/run_all.py` — **primary launcher**: `python3 Tests/run_all.py` connects via XML-RPC to the user's already-running FreeCAD GUI (127.0.0.1:9875, no restart). Takes an optional substring filter (e.g. `python3 Tests/run_all.py chain`) and `--inspect` to leave test documents open for stage-2 human inspection. Exit codes: 0 = all pass, 1 = failures, 2 = FreeCAD unreachable.
- `freecad Tests/run_all.py` — fallback in-process mode (spawns its own FreeCAD)
- Stage tests: `test_edge_stage.py` (E1–E4 oracle), `test_patch_stage.py` (P1–P4), `test_blend_stage.py` (B1–B4), `test_chain.py` (full 9→7→2→1 rebuild, the acceptance gate — always runs)
- Ops layer: `SilkWorkflowOps.py` (`create_edge`, `create_patch`, `create_blend`) — the only construction path; oracle: `SilkChecks.py` (`check_edge`, `check_patch44`, `check_blend`)
- The harness monkey-patches `popup.tipsDialog` to a console stub so unattended runs never block on modal popups
- RPC runs must `del` all `sys.modules` entries starting with `Silk`/`Tests`/`ArachNURBS` before importing (done in `run_all.py`'s remote code) — otherwise the long-lived RPC process runs stale cached modules

## Reference Files
- `Resources/Test_files/Silk_2Boundaries.FCStd` — 9 sketches only (baseline)
- `Resources/Test_files/Silk_Workflow.FCStd` — full pipeline built on sketches
- `Resources/Test_files/Silk_2BoundariesAndControlGrids.FCStd` — old reference with groups
