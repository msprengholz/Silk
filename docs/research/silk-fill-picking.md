# Why the Surface workbench cannot pick a blend strip's edges (#96), and what the fill does accept

Ticket #96 was reopened as *interactive usability*: the owner wants to fill a
whole corner with one patch **and judge it by eye**, and reported that the
Surface workbench's `Surface::Filling` panel would not let them select the
blend strips' edges — the recorded symptom being *open → select an edge →
cancel → FreeCAD died*.

This note is the diagnosis. It names its instrument, keeps the raw output,
publishes the error floor and carries a known-answer calibration, because the
result decides a product choice (leave the picker alone and assemble the fill
in Silk, or change what Silk draws).

## Instrument

* Fixture: `Tests/corner_model.py::build_corner_model_with_blend` — 4 patches,
  4 ring `Blend` strips (`B12`, `B24`, `B43`, `B31`), 1 `CornerBlend`, built
  through `SilkWorkflowOps` only. Live FreeCAD 1.1.3 (OCCT 7.9) over the MCP
  `execute_code` path (the GUI thread), scratch document `_fill_diag`, removed
  afterwards.
* **Pick**: `Gui.ActiveDocument.ActiveView.getObjectInfo((x, y))` — the same
  Coin ray-pick the mouse drives, through FreeCAD's own
  `View3DInventorPy::getObjectInfo`. Camera set with `viewTop()` + `fitAll()`;
  3D → pixel via `View3DInventorPy.getPointOnScreen`. FreeCAD's own pick radius
  on this build is **5.0 px** (`viewer.getPickRadius()`), viewport 1156×657.
* **Scan**: 9 stations along the sub-shape under test, each scored over a
  17×17 px window (2601 `getObjectInfo` calls per station set). A component is
  reported only when a pixel actually hits it.
* **Object path**: `Surface::Filling` built in the same document with our
  `Blend` objects as the `BoundaryEdges` carriers, `BoundaryFaces =
  ["Face1"] * 4`, `BoundaryOrder` 0/1/2; residual = `Shape.distToShape(edge)`.

## Raw output

### 1. Topology, `Selectable`, `SelectionStyle` — nothing is missing here

| object | TypeId | `Shape.ShapeType` | faces/edges/verts | `Selectable` | `SelectionStyle` | `DisplayMode` |
|---|---|---|---|---|---|---|
| `B12` | `Part::FeaturePython` | `Face` | 1 / 4 / 4 | True | Shape | **Shaded** |
| `B24` | `Part::FeaturePython` | `Face` | 1 / 4 / 4 | True | Shape | **Shaded** |
| `B43` | `Part::FeaturePython` | `Face` | 1 / 4 / 4 | True | Shape | **Shaded** |
| `B31` | `Part::FeaturePython` | `Face` | 1 / 4 / 4 | True | Shape | **Shaded** |
| `CornerBlend` | `Part::FeaturePython` | `Face` | 1 / 4 / 4 | True | Shape | **Shaded** |
| `Patch44` | `Part::FeaturePython` | `Compound` | 1 / 4 / 4 | True | Shape | Flat Lines |

`SelectionStyle` enumerates `["Shape", "BoundBox"]`; `DisplayMode` enumerates
`["Flat Lines", "Shaded", "Wireframe", "Points"]`. Every strip's `Shape` is
non-null and its four boundary edges resolve by name: `B12.Shape.getElement
("Edge4")` is the strip's junction-end row. `RootNode` holds the standard Part
display subtree (`SoFCTransform`, `PickStyle`, `Coordinate3`, `Switch` ×2)
plus Silk's grid `SoSwitch` (#108/#110) — the strips have a selectable Part
node, they are not "geometry-less".

### 2. What the picker reports, per display mode

Distinct `Object/Component` over the 17×17 px window around `B12`'s
junction-end row (`Shape.Edges[3]`, `"Edge4"`), Top view:

| target | `DisplayMode` | reported components (hits) |
|---|---|---|
| `B12.Edge4` | Shaded (**current**) | `E_s12/Edge1` 252, `Patch44/Edge72` 109, `Patch001/Edge22` 104, `Patch44/Edge83` 100, `Patch44/Edge57` 87, `Patch44/Edge80` 84, … — **`B12/Edge4` never appears** |
| `B12` face centroid | Shaded | `B12/Face1` 119, `E_s12/Edge1` 170 |
| `B12.Edge4` | Flat Lines | `E_s12/Edge1` 252, `Patch44/Edge72` 105, `Patch001/Edge22` 104, … **`B12/Edge4` 72** |
| `B12` face centroid | Flat Lines | `B12/Face1` 119, `E_s12/Edge1` 170 (unchanged) |
| `Patch44.Edge4` | **Flat Lines** (calibration) | **`Patch44/Edge4` 427**, `B31/Face1` 458, `Patch44/Face1` 376, … |

Reading:

* **The cause is Silk's own display choice.** In `Shaded` the wireframe node of
  the Part subtree is switched off, so there is nothing to ray-pick on the
  boundary: the strip can only ever yield `Face1`. Switching the *same* object
  to `Flat Lines` makes `Edge4` pickable (72 hits). The three sites that write
  it are `SilkWorkflowOps.create_blend` (`DisplayMode = "Shaded"`),
  `SilkBlend.CreateBlend.Activated` (same) and `SilkWorkflowOps.
  create_corner_blend` (same), each paired with `Transparency = 30`.
* **The known-answer calibration is green.** `Patch44` is a Silk object of the
  *same* C++ type, drawn `Flat Lines`, and its `Edge4` is pickuped 427 times —
  so the instrument, the `Part::FeaturePython` selection node and our sub-shape
  names are all sound. Nothing about *our* objects as such is unpickable.
* **Error floor.** The reported value is a whole sub-element name from
  FreeCAD's own pick, at FreeCAD's 5 px pick radius. "`B12/Edge4` cannot be
  picked in Shaded" rests on 2601 sampled pixels around nine stations on that
  very edge, and is not a sampling artefact; "it can be picked in Flat Lines"
  is a positive hit on the same pixels. The residual ambiguity is a shared
  pixel: where the radial `Edge` object `E_s12` crosses the row, `E_s12/Edge1`
  wins the depth test, so the *ends* of a strip's row are the reliably
  clickable part of it (this is the same overlap the owner would meet by hand).
* **The one-line Silk-side fix** is `DisplayMode = "Flat Lines"` at those three
  sites (or "Wireframe"). It is **not applied in this ticket**: it changes what
  every blend in every document looks like, which is the owner's call, not the
  implementer's. The picker question is settled by the measurement above.

### 3. The Surface panel accepts our objects — it only ever sees `Face1`

The panel's own selection gate was read out of `SurfaceGui.so`
(`SurfaceGui::FillingPanel::ShapeSelection::allow` / `allowEdge`): it requires
a `Part::Feature`-derived object and a non-empty `Edge*` subname, and refuses
an edge already in `BoundaryEdges`. `Part::FeaturePython` is derived from
`Part::Feature`, so our strips pass the gate — nothing in the panel rejects
Silk objects by type.

Driven programmatically in a **throwaway offscreen GUI instance**
(`QT_QPA_PLATFORM=offscreen freecad -u <tmp cfg> -s <tmp cfg>`, isolated from
the live session) with the same corner fixture:

```
workbenches: ['SurfaceWorkbench']          -> activateWorkbench("SurfaceWorkbench")
filling-ish commands: ['Surface_Filling']  -> runCommand
list widgets: [('listBoundary', 0), ('listUnbound', 0), ('listFreeVertex', 0)]
buttons: buttonEdgeAdd(Add Edge), buttonEdgeRemove, buttonAccept, buttonIgnore, ...
Gui.Selection.addSelection(B12, "Edge4")
  after add listBoundary -> ['B12.Edge4']
  fill BoundaryEdges now: [('B12', ['Edge4'])]
  fill BoundaryFaces now: ['']
```

So **the panel takes `(Blend, "EdgeN")` as a boundary edge** — the failure the
owner hit is upstream of the panel, in the picker (section 2).

Two honest limits of that sandbox run:

* `accept()` could not be completed: with no GL context the offscreen platform
  floods `No valid GL context found!` and the accept never returned. The
  panel's *own* build step is therefore **not** verified here; what is verified
  is the wiring it writes onto the object, and that wiring is exactly what
  section 4 measures on the object path.
* The recorded crash (open → select edge → cancel) was **not reproduced** —
  the sandbox never reached a clean reject. It is not contradicted either. It
  is a FreeCAD-side hazard we cannot test from a script; hand the click test
  below to the owner. A task panel must be closed (`dialog.reject()`) before
  anything else, or it blocks the GUI.

### 4. `Surface::Filling` accepts our strips directly (the Silk-side path)

Junction-end row → sub-shape name, derived through `SilkCorner.corner_inputs`
(the same derivation the corner blend uses): `B12 → Edge4`, `B24 → Edge2`,
`B43 → Edge4`, `B31 → Edge4`.

| `BoundaryOrder` | faces | `isValid()` | `distToShape(fill, boundary edge)` per strip (mm) |
|---|---|---|---|
| 0 | 1 | True | 0.0 / 0.0 / 0.0 / 0.0 |
| 1 | 1 | True | 0.0 / 0.0 / 0.0 / 0.0 |
| 2 | 1 | True | 0.0 / 0.0 / 0.0 / 0.0 |

with `BoundaryEdges = [(B12, "Edge4"), (B24, "Edge2"), (B43, "Edge4"),
(B31, "Edge4")]` and `BoundaryFaces = ["Face1"] * 4` — **no throwaway carrier
objects** (what `Tests/g2_corner_fill_probe.py` needed), so the fill stays
live-linked to the strips. The residual floor is `0.0` mm by construction: a
sound fill *contains* its boundary edges. That makes a boundary-contact check a
free, exact refusal gate; the probe's `~1e-4` figures were its parameter-solve
floor, not the fill's.

Continuity numbers for this feed stay where the probe measured them
(`strip`, order 1: `<= 2.2e-4` mm boundary residual, `0.087–0.155 deg` normal
gap); nothing here re-opens them, and no continuity label is asserted.

## Conclusion

* Category **1** of the ticket holds, with a sharpened mechanism: the strips
  expose *unpickable* sub-shapes — not missing ones. `Shape` is correct,
  `Selectable` is True, `EdgeN` names are stable and `Surface::Filling` accepts
  them; Silk draws the strips `Shaded`, so the picker can only return `Face1`.
* Category **2** does not hold: the Surface panel's gate accepts our objects and
  the panel records `(Blend, "EdgeN")` correctly.
* Category **3** is neither reproduced nor refuted (offscreen Qt has no GL
  context; the crash path needs a real click).
* Therefore #96 ships the Silk-side assembly path — select the ring strips in
  Silk and let Silk build the `Surface::Filling` — and the picker stays as the
  owner prefers it. The owner still judges the surface by eye; they just do not
  fight the picker.

## Click test for the owner (manual, still unverified)

1. Open a model with a `CornerBlend` (or the corner fixture). Click one `Blend`
   strip; in the *View* tab set `DisplayMode` to `Flat Lines`.
2. Move the mouse along a short end of the strip's junction-side boundary edge
   and watch the highlight: an edge highlight means the picker can see it.
3. Keep the strip selected and run **Surface → Filling**. The panel's
   `listBoundary` should list `BlendName.EdgeN` ("1 adjacent face").
4. Add the other three strips' junction-side edges the same way, set
   `Continuity` to `C0` first, and press OK — the corner is filled with one
   patch.
5. If FreeCAD dies on **Cancel** (the recorded symptom), note the exact click
   order; that is a FreeCAD-side crash, not a Silk one.
