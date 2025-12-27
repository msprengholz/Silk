Nice, this “minimal but useful” step is very sensible. Let’s treat this as a concrete design + implementation plan you could actually start coding.

I’ll structure it like this:

1. Overall architecture (what new objects/commands we add)
2. BoundarySpline object + command
3. ControlGridPatch (44/33) object + command
4. Subdivision (subgrids) inside ControlGridPatch
5. UI integration (toolbar, buttons)
6. Notes on future-proofing for blending

---

## 1. Architecture overview

We add **two new feature types** and **two new GUI commands**:

### New feature types

1. **BoundarySpline**

   * Concept: combined “ControlPoly4 + CubicCurve4” object.
   * Input: one or more Sketches (or edges), grouped under it.
   * Data:

     * References to the defining sketches
     * A 4-point control poly (ControlPoly4)
     * A derived cubic curve (CubicCurve4) for display
   * Display:

     * Show the cubic curve **by default**
     * Optionally show control polygon

2. **ControlGridPatch**

   * Concept: grid-based patch, either 4×4 (quad) or 3×3 (triangle), plus **optional surface**.
   * Input: 3 or 4 BoundarySpline objects.
   * Data:

     * Link list of boundarysplines
     * Stored 4×4 (or 3×3) poles
     * Properties for U/V subdivision
   * Display:

     * Control net (grid)
     * Optional surface (toggle)
     * If subdivided: show only **latest subgrids**, not the original full patch

### New GUI commands

* `Silk_CreateBoundarySpline`  → “Create boundary spline”
* `Silk_CreateControlGridPatch` → “Create control grid”

These will be added to the Silk workbench toolbar/panel.

---

## 2. BoundarySpline: design & implementation

### 2.1. Object type

Create a new FeaturePython class, something like:

```python
class BoundarySpline:
    Type = "Silk::BoundarySpline"
```

It should behave as a **group-like GeoFeature** so that its child sketches can be nested under it.

Implementation choices (you can pick one):

* Inherit from `App.DocumentObjectGroupPython` (or group-capable base) and add geometry properties.
* Or: use a plain `Part::FeaturePython` + a `Group` property to hold child sketches.

I’d recommend:

* **App::DocumentObjectGroupPython**
  → keeps the tree tidy and grouping is “natural” (sketches underneath).

### 2.2. Properties

Add these properties in `__init__` of the feature:

* **Input / definition**

  * `PropertyLinkList`  `BaseSketches`
    List of Sketches (or other geometry) that define the boundary.
* **Geometry**

  * `PropertyVectorList` `ControlPoints` (4 vectors)
    The 4 control points of the ControlPoly4.
* **Display / options**

  * `PropertyBool` `ShowCurve` (default: `True`)
  * `PropertyBool` `ShowControlPoly` (default: `False`)
  * (Optional) `PropertyFloat` parameters for how to build the control poly from sketches – not strictly needed now.

### 2.3. Execute logic

`onChanged` or `execute(obj)` should:

1. Read the linked `BaseSketches`.

2. Extract the relevant edges or points from those sketches. For a first implementation, keep it simple:

   * Assume the user draws a single 3-segment polyline sketch representing control poly directly, OR
   * A single sketch with two endpoints + tangent handles (depends how Silk currently does ControlPoly4).

3. Convert this to a **4-point ControlPoly4**:

   Examples of mapping:

   * If using a “3-line control poly” style: just take the four corner vertices.
   * If using “endpoints + tangents”: compute inner control points via endpoint + tangent length.

4. Store those four control points in `obj.ControlPoints`.

5. Build a **cubic curve** representation for display:

   * Either create a `Part.BSplineCurve` of degree 3 from the 4 poles.
   * Or reuse existing Silk helper that turns a ControlPoly4 into a CubicCurve4.

6. Assign the curve to `obj.Shape` (if you want BoundarySpline to itself carry the visible curve).

   * When `ShowCurve` is `True`, set `Shape` to the BSpline curve.
   * If `ShowControlPoly` is `True`, you can also build a small wire/compound showing the control polygon (or add Coin nodes in the ViewProvider).

### 2.4. Grouping sketches under BoundarySpline

In the BoundarySpline creation command (GUI command), after creating the feature:

* For each selected sketch `sk`:

  * Assign it to the group’s `Group` property:

    ```python
    obj.addObject(sk)
    ```
* Optionally set the sketches’ visibility to False, letting the boundary spline dominate the view.

This yields a tree like:

```
BoundarySpline001
  ├─ Sketch001
  └─ Sketch002
```

Nice and tidy.

### 2.5. GUI command: CreateBoundarySpline

Create a new command class in `InitGui.py` (or wherever Silk defines its commands):

```python
class _BoundarySplineCmd:
    def GetResources(self):
        return {
            'MenuText': 'Create BoundarySpline',
            'ToolTip': 'Create a boundary spline (ControlPoly4 + CubicCurve4) from one or more Sketches',
            'Pixmap': 'path/to/icon_boundaryspline.svg',
        }

    def IsActive(self):
        # Active if at least one Sketch is selected
        import FreeCADGui
        sel = FreeCADGui.Selection.getSelection()
        return any(obj.TypeId.startswith('Sketcher::Sketch') for obj in sel)

    def Activated(self):
        import FreeCAD, FreeCADGui
        doc = FreeCAD.ActiveDocument
        sel = FreeCADGui.Selection.getSelection()

        sketches = [obj for obj in sel if obj.TypeId.startswith('Sketcher::Sketch')]
        if not sketches:
            FreeCAD.Console.PrintError('Select one or more sketches to create a BoundarySpline.\n')
            return

        bs = doc.addObject('App::DocumentObjectGroupPython', 'BoundarySpline')
        BoundarySpline(bs)            # attach proxy
        ViewProviderBoundarySpline(bs.ViewObject)

        bs.BaseSketches = sketches
        # group the sketches
        for sk in sketches:
            bs.addObject(sk)

        bs.ShowCurve = True
        bs.ShowControlPoly = False

        doc.recompute()
```

Then register this command and add it to Silk’s toolbar.

---

## 3. ControlGridPatch (44/33) object

### 3.1. Object type

New FeaturePython class:

```python
class ControlGridPatch:
    Type = "Silk::ControlGridPatch"
```

Represents either:

* 4×4 grid (quad 44), or
* 3×3 grid (tri 33)

### 3.2. Properties

In `__init__`:

* **Inputs**

  * `PropertyLinkList` `Boundaries`
    List of 3 or 4 `BoundarySpline` objects.
* **Type**

  * `PropertyEnumeration` `PatchType`
    Values: `["Quad44", "Tri33"]`
* **Geometry**

  * `PropertyVectorList` `ControlPoints`
    Store the 16 (or 9) control points in a flat list (or separate 2D indexing inside proxy).
* **Display**

  * `PropertyBool` `ShowSurface` (default `False`)
  * `PropertyBool` `ShowControlNet` (default `True`)
* **Subdivision**

  * `PropertyFloatList` `USplits` (default empty)
  * `PropertyFloatList` `VSplits` (default empty)

  OR, if you want fixed two splits:

  * `PropertyFloat` `USplit1`, `USplit2` (default 0.0 and 1.0)
  * `PropertyFloat` `VSplit1`, `VSplit2`

But I’d go with `USplits` and `VSplits` as lists of floats between 0 and 1. For this first version, you can restrict UI to allow at most 2 splits by convention.

### 3.3. Execute logic: building base grid

In `execute(obj)`:

1. Read the `Boundaries` list:

   * If 4 boundaries → `PatchType = Quad44`
   * If 3 boundaries → `PatchType = Tri33`

2. Extract the cubic curves (BSplines) from each BoundarySpline (using their `ControlPoints` and/or `Shape`).

3. Call a grid-construction routine:

   * For 4 boundaries: a Coons-like routine that builds a 4×4 grid from 4 cubic edges (existing Silk code does this for `ControlGrid44`).
   * For 3 boundaries: degenerate 3×3/4×4 with one collapsed side (again, existing Silk methods).

   The result: `poles[i][j]` for i,j in range(4) (or 3).

4. Flatten and store as `obj.ControlPoints`.

5. **Display control net:**

   * Create a series of edges between control points (u- and v-lines) and assign them to a `Part.Compound` for `obj.Shape` if `ShowControlNet` is True and `ShowSurface` is False.
   * Or, have the ViewProvider draw the control net using Coin.

6. If **ShowSurface is True** and there are no splits:

   * Build a `Part.BSplineSurface` from `obj.ControlPoints` and assign to `obj.Shape`.
   * (If you want both net and surface, you can build a Compound of the face + net, or draw net in VP only.)

We’ll refine this in the next section when subdivision is in play.

### 3.4. GUI command: CreateControlGridPatch

Command class:

```python
class _ControlGridPatchCmd:
    def GetResources(self):
        return {
            'MenuText': 'Create ControlGridPatch',
            'ToolTip': 'Create a 4x4 or 3x3 control grid from 3–4 BoundarySplines',
            'Pixmap': 'path/to/icon_controlgrid.svg',
        }

    def IsActive(self):
        import FreeCADGui
        sel = FreeCADGui.Selection.getSelection()
        return all(obj.TypeId == 'App::DocumentObjectGroupPython' and getattr(obj.Proxy, 'Type', '') == 'Silk::BoundarySpline'
                   for obj in sel) and (3 <= len(sel) <= 4)

    def Activated(self):
        import FreeCAD, FreeCADGui
        doc = FreeCAD.ActiveDocument
        sel = FreeCADGui.Selection.getSelection()

        boundaries = [obj for obj in sel
                      if getattr(getattr(obj, 'Proxy', None), 'Type', '') == 'Silk::BoundarySpline']

        if len(boundaries) not in (3, 4):
            FreeCAD.Console.PrintError('Select 3 or 4 BoundarySplines.\n')
            return

        grid = doc.addObject('Part::FeaturePython', 'ControlGridPatch')
        ControlGridPatch(grid)
        ViewProviderControlGridPatch(grid.ViewObject)

        grid.Boundaries = boundaries
        grid.PatchType = 'Quad44' if len(boundaries) == 4 else 'Tri33'
        grid.ShowControlNet = True
        grid.ShowSurface = False

        doc.recompute()
```

This gives you the “Create controlgrid object” button.

---

## 4. Subdivision inside ControlGridPatch

This is your step 3: “make the object containing the controlgrid also have settings in the data grid to define its subdivisions… Make sure to only display the latest subgrids and not the original surface.”

We’ll do this purely *internal* to the ControlGridPatch.

### 4.1. Data interpretation

Assume:

* `USplits`: list of float parameters t in (0,1)
* `VSplits`: same

In `execute(obj)`:

1. Build the **base grid** poles from boundaries (as above).

2. Determine segmentation intervals:

   * Sort `USplits` and filter values (0 < t < 1).
   * Build interval list in U: `[0, u1, u2, ..., 1]`.
   * Same for V.

3. If there are **no splits** in U/V:

   * Just one patch: use full 0–1 range → show original grid (and surface if ShowSurface).

4. If splits exist:

   * For each interval `u_i..u_{i+1}` and `v_j..v_{j+1}`:

     * Compute sub-grid poles for that param rectangle.
     * Store each as a local 4×4 (or 3×3) patch.

   * Collect all resulting sub-patches into a list.

### 4.2. Geometry: subdividing the grid

There are two options:

* **Use Silk’s grid subdivision utilities** if they exist (they likely do, since you can already create 44 from 44 segments).
* Or implement direct Bezier subdivision along U and V (De Casteljau).

Conceptually:

* For 4×4 one patch, subdivide along U at `u = t` to get two 4×4 patches. Then subdivide each along V at each `v` split, etc.
* So in code, implement a helper:

  ```python
  def subdivide_patch(poles_4x4, u_intervals, v_intervals) -> list_of_poles_4x4
  ```

  that returns a list of 4×4 grids corresponding to each rectangle.

For first iteration, you can restrict to **at most one split per direction** (so 2×2 = 4 patches). That’s enough to test concept and already useful.

### 4.3. Display logic for subgrids

We obey your “only display latest subgrids and not the original surface” rule:

* If no splits → show base patch as before.
* If splits exist:

  * The **ControlGridPatch** still remains a single document object.
  * Its `Shape` becomes a **compound** of:

    * control nets for each subgrid, or
    * surfaces for each subgrid, depending on `ShowSurface` and `ShowControlNet`.
  * The original base grid is **not** shown anymore (except that it implicitly underlies the subgrids).

This means from the user POV:

* They still see one object `ControlGridPatch001`.
* As they fill in `USplits` / `VSplits`, the patch visually breaks into several smaller patches.
* There are no extra objects in the tree.

Later, when blending is implemented, those sub-patches can be conceptually addressed by parameter ranges (e.g. “blend along U segment 1”); for now the user simply gets the segmented visuals.

---

## 5. UI Integration

In `InitGui.py` (or Silk’s GUI module):

1. **Register commands**:

   ```python
   FreeCADGui.addCommand('Silk_CreateBoundarySpline', _BoundarySplineCmd())
   FreeCADGui.addCommand('Silk_CreateControlGridPatch', _ControlGridPatchCmd())
   ```

2. **Add toolbar buttons**:

   ```python
   class SilkWorkbench(Workbench):
       def Initialize(self):
           self.appendToolbar(
               "Silk Surface Tools",
               ['Silk_CreateBoundarySpline',
                'Silk_CreateControlGridPatch']
           )
   ```

3. Add icons (`.svg`) for both commands.

4. Add brief tooltips / ‘What’s this?’ help:

   * “Create BoundarySpline: Turn selected sketch(es) into a reusable boundary spline (ControlPoly4 + cubic curve).”
   * “Create ControlGridPatch: Turn 3–4 BoundarySplines into a 4×4 or 3×3 control grid, optionally with a surface.”

---

## 6. Future-proofing for blending (without implementing it yet)

You’re explicitly *not* asking for blending implementation here, but let’s make sure this design doesn’t paint us into a corner.

* **BoundarySpline** is a single, reusable object that can serve as:

  * Edge input to ControlGridPatch,
  * And later, to blend creation commands (which will need access to the cubic curve and its parameterization).
* **ControlGridPatch**:

  * Knows its U/V parameters and segments.
  * Stores the full base grid + split information.
  * Can later be asked: “Give me the subgrid corresponding to U in [0.3, 0.6] and whole V” – exactly what a blend feature will need.
* **Subgrids**:

  * Are currently internal to one object’s Shape.
  * For blending, we can either:

    * Expose a lightweight API (e.g. method `getSegment(u0,u1,v0,v1)` returning a 4×4 pole array).
    * Or, later, promote certain segments to named “segments” that blend tools can use.

No dependency problems are introduced yet: segmentation is controlled entirely by properties; no extra objects depend on them. When blending is added, we’ll attach the segmentation state to blend features (as discussed before), but the current design is fully compatible with that.

---

If you like, next step I can turn this into a more code-level skeleton (actual class stubs) you can drop into Silk and iterate on.
