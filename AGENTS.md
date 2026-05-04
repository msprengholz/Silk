# Silk Workbench — Agent Notes

## Shared Edge Detection & Blend Algorithm

### Problem
Two Patch44 objects share an edge. Need to determine WHICH edge (Poly0..Poly3) they share, what UV direction it runs in each grid, and how to pair rows/columns for blending.

### Step 1: Find shared corners

Each Patch44 has 4 corners extracted from the 16-pole grid:
```python
corners = [Poles[0], Poles[3], Poles[15], Poles[12]]
# = [p00, p03, p33, p30] = [U0V0, U1V0, U1V1, U0V1]
```

Compare corner[i] of patch A vs corner[j] of patch B within tolerance (0.01). Collect matching pairs.

### Step 2: Determine edge type

Corners adjacency (edges of the quadrilateral):
- (0,1) or (1,0) = U0 (V=0, U varies along row 0)
- (1,2) or (2,1) = V1 (U=1, V varies along col 3)
- (2,3) or (3,2) = U1 (V=1, U varies along row 3)
- (3,0) or (0,3) = V0 (U=0, V varies along col 0)

Two shared corners define the shared edge. Look up which edge those indices correspond to.

### Step 3: Subdivide perpendicular to shared edge

| Shared edge | Split direction | Strip location |
|-------------|----------------|----------------|
| U0 (row 0)  | VSplits=[0.1]  | subgrid[0] (V=0→0.1) |
| U1 (row 3)  | VSplits=[0.9]  | subgrid[1] (V=0.9→1.0) |
| V0 (col 0)  | USplits=[0.1]  | subgrid[0] (U=0→0.1) |
| V1 (col 3)  | USplits=[0.9]  | subgrid[1] (U=0.9→1.0) |

### Step 4: Extract rows/columns from strips

Subgrid flat array: `poles[u][v]` = `flat[u*4 + v]`

If shared edge is along V (col): rows at constant V = `flat[u*4 + v] for u in 0..3`
If shared edge is along U (row): cols at constant U = `flat[u*4 + v] for v in 0..3`

### Step 5: Subdivide perpendicular to shared edge

| Shared edge | Split on patch | Split direction | Strip location |
|-------------|---------------|----------------|----------------|
| U0 (row 0)  | Patch          | VSplits=[0.1]  | subgrid[0] (V=0→0.1) |
| U1 (row 3)  | Patch          | VSplits=[0.9]  | subgrid[1] (V=0.9→1.0) |
| V0 (col 0)  | Patch          | USplits=[0.1]  | subgrid[0] (U=0→0.1) |
| V1 (col 3)  | Patch          | USplits=[0.9]  | subgrid[1] (U=0.9→1.0) |

### Step 6: Extract rows/columns from strips

Subgrid flat array: `poles[u][v]` = `flat[u*4 + v]`

If shared edge is along V (col): rows at constant V = `flat[u*4 + v] for u in 0..3`
If shared edge is along U (row): cols at constant U = `flat[u*4 + v] for v in 0..3`

### Step 7: Pair rows/columns across patches

Corner matching gives the index mapping. The shared edge runs in possibly reversed direction:
- Corner A ↔ corner B means: the V (or U) index at corner A on patch A corresponds to the U (or V) index at corner B on patch B
- This defines the pairing for intermediate indices
- Example: if left corners[0]=(0,0,40) matches right corners[1]=(0,0,40), and left corners[3]=(0,50,0) matches right corners[0]=(0,50,0), then left V=0 ↔ right U=1, left V=3 ↔ right U=0, meaning the mapping is left V=i ↔ right U=n−1−i (reversed)

### Step 8: Blend

For each paired row/col:
1. Reverse the LEFT row so it goes OUTER→SHARED (list(reversed(row)))
2. Keep the RIGHT column as SHARED→OUTER
3. Call `AN.blend_poly_2x4_1x6(l_row_rev, [1.0]*4, r_col, [1.0]*4, 2.0, 2.0, 2.0, 2.0)`
4. Collect 6-pole results

Stack 4 result rows into a 6×4 grid (24 poles). Create blend surface:
```python
surf = Part.BSplineSurface()
surf.increaseDegree(3, 3)
surf.insertUKnot(0.0, 4, 1e-7)
surf.insertUKnot(1.0/3.0, 3, 1e-7)
surf.insertUKnot(2.0/3.0, 3, 1e-7)
surf.insertUKnot(1.0, 4, 1e-7)
surf.insertVKnot(0.0, 4, 1e-7)
surf.insertVKnot(1.0, 4, 1e-7)
for r in range(4):
    for c in range(6):
        surf.setPole(c+1, r+1, poles_24[r*6+c], weights_24[r*6+c])
```

### Key gotchas
- `flat[u*4 + v]` = U=u, V=v (first dim = U in FreeCAD's BSplineSurface)
- `segment(u0, u1, v0, v1)` — first arg is U range, second is V range
- Surface `getPoles()` returns `poles[U][V]` = `flat[U*4 + V]` (U is first dimension)
- Row at V=i: `flat[0+i, 4+i, 8+i, 12+i]` = varying U, constant V
- Col at U=j: `flat[4j+0, 4j+1, 4j+2, 4j+3]` = varying V, constant U
- Shared edge direction is REVERSED between patches — use corner matching to determine pairing
- `blend_poly_2x4_1x6` expects: poles_0 goes OUTER→SHARED, poles_1 goes SHARED→OUTER  
  So reverse the left row but NOT the right column

## Patch44 Implementation Notes

### Architecture
- Single FeaturePython object (not group)
- 16 poles + 16 weights (4×4 grid)
- Subgrids stored internally in `_subgrids` and `_subsurfaces` (not in FreeCAD tree)
- Display toggles: ShowSurface, ShowGrid, ShowSubgrids

### Key properties
- Poly0..Poly3: PropertyLink to 4 edge objects (must have .Poles, .Weights)
- USplits, VSplits: PropertyFloatList for subdivision
- `getSubgrid(u0,u1,v0,v1)`: API for blend tool to query pole data

### Surface creation
- Use `increaseDegree(3,3)` + `insertUKnot`/`insertVKnot` + `setPole` pattern
- NOT `buildFromPolesMultsKnots` (signature is non-standard)
- `getPoles()` from surface returns `poles[u][v]`

### Module reload
- Each MCP `execute_code` call runs in the same FreeCAD process
- Python caches modules — must `del sys.modules[key]` before re-import
- Template: `for m in list(sys.modules.keys()): if 'SilkPatch44' in m: del sys.modules[m]; import SilkPatch44`

## Test Infrastructure

### MCP Harness
- `Tests/mcp_harness.py`: `run_tests(*funcs)`, each func takes doc, returns dict
- `Tests/test_patch44_comprehensive.py`: All tests with `CaptureConsole` for error capture
- `Tests/test_blend.py`: Blend strip tests

### Running tests via MCP
```python
import sys
sys.path.insert(0, "/home/mo/.local/share/FreeCAD/v1-1/Mod/Silk")
for m in list(sys.modules.keys()):
    if 'SilkPatch44' in m or 'test_patch44' in m or 'test_blend' in m or 'mcp_harness' in m:
        del sys.modules[m]
import SilkPatch44
from Tests.mcp_harness import run_tests
from Tests.test_patch44_comprehensive import ALL_TESTS as tests
from Tests.test_blend import ALL_TESTS as blend_tests
run_tests(*(tests + blend_tests))
```

### Console error capture
```python
class CaptureConsole:
    def __enter__(self):
        self._orig_error = FreeCAD.Console.PrintError
        FreeCAD.Console.PrintError = lambda msg: (self.errors.append(msg), ...)
```
