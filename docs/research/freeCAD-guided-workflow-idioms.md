# FreeCAD GUI idioms for a guided multi-step workflow

Research ticket: [msprengholz/Silk#2](https://github.com/msprengholz/Silk/issues/2)
Date: 2026-10-08 · FreeCAD 1.1 branch: `releases/FreeCAD-1-1` (all FreeCAD source paths below point at that branch unless noted)

## Question

Which FreeCAD GUI idiom fits a guided multi-step workflow over Silk's existing
pipeline (sketches → boundary splines → `SilkEdge` → `Patch44` → `BlendStrip`)?
Options:

- **(a)** PartDesign-style task panel
- **(b)** container object + property-driven state (additive, recompute-driven)
- **(c)** toolbar command chains with selection
- **(d)** hybrid

Constraints: Silk is mostly custom `Part::FeaturePython` objects
(`SilkEdge`, `SilkPatch44`, `SilkBlend`), distributed via AddonManager, targets
FreeCAD 1.1, and the fork must stay PR-clean against `edwardvmills/Silk`
(see `docs/adr/0001-upstream-first-fork-strategy.md`: new code must be purely
additive).

## What Silk's GUI already is

From the fork's own sources (baseline for any idiom choice):

- `InitGui.py` — a classic `Workbench` with a flat command list,
  `appendToolbar`/`appendMenu` (idiom **c** scaffolding only).
- `SilkPatch44.py`, `SilkBlend.py` — `Part::FeaturePython` objects whose proxy
  implements `addProperty` + `onChanged` (→ `fp.touch()`/`fp.recompute()`) +
  `execute()`. `Patch44.execute()` even touches linked BlendStrips when
  USplits/VSplits change. This is idiom **b** — it is already Silk's
  parametric backbone.
- `SilkWorkflow.py` — a command that *chains other commands* via
  `Gui.runCommand("ControlPoly4")` then `Gui.runCommand("CubicCurve_4")`,
  snapshotting objects before/after each step, clearing/re-aiming
  `Gui.Selection` in between, and collects outputs into an
  `App::DocumentObjectGroupPython` with a `SilkType` marker property and a
  selection observer that expands the group on click. This is idiom **c**
  today, and its fragility (pre/post snapshots, forced selection hand-offs)
  is the pain the guided workflow is meant to remove.

## The four idioms against FreeCAD 1.1 reality

### (a) PartDesign-style task panel

What the task panel actually is in 1.1:

- The panel is a docked "Tasks" view; C++ content classes
  `TaskContent`/`TaskGroup`/`TaskBox`/`TaskPanel` live in
  `src/Gui/TaskView/TaskView.h`
  (https://github.com/FreeCAD/FreeCAD/blob/releases/FreeCAD-1-1/src/Gui/TaskView/TaskView.h).
  `TaskDialog` (`src/Gui/TaskView/TaskDialog.h`) holds the boxes plus
  auto-managed OK/Close buttons.
- **PartDesign's panels are C++**: every `src/Mod/PartDesign/Gui/Task*` class
  (e.g. `TaskPrimitiveParameters.cpp`, `TaskBooleanParameters.cpp`,
  `TaskFeaturePick.cpp`) subclasses `Gui::TaskView::TaskBox` and is injected
  by its `ViewProvider` while the feature is *in edit*. There is no PartDesign
  panel to imitate from Python — PartDesign's "guidedness" (in-edit feature,
  body container, DAG) is a C++/App module architecture an AddonManager workbench
  cannot use.
- **The Python-side reality** is a plain protocol, not a PartDesign clone:
  `Gui.Control.showDialog(panel)` / `Gui.Control.closeDialog()` /
  `Gui.Control.addTaskWatcher([...])`, bound in
  `src/Gui/TaskView/TaskDialogPython.h/.cpp` (`ControlPy` methods:
  `showDialog`, `activeDialog`, `activeTaskDialog`, `closeDialog`,
  `addTaskWatcher`, `clearTaskWatcher`, `isAllowedAlterDocument/View/Selection`,
  `showTaskView`, `showModelView`). The Python panel object may define any of
  `ui`, `form`, `setupUi()`, `open()`, `clicked(id)`, `accept()`, `reject()`,
  `changed(widget)`, `helpRequested()`, `getStandardButtons()`,
  `modifyStandardButtons()`, `isAllowedAlter*()`, `needsFullSpace()`,
  `autoClosedOnTransactionChange` — each looked up with `hasAttr` in
  `TaskDialogPython.cpp`, i.e. all optional. Watcher objects: `title`, `icon`,
  `commands`, `widgets`, `filter`, `shouldShow` (same file).
- Canonical in-tree Python example: the official workbench template
  `src/Mod/TemplatePyMod/TaskPanel.py` (task panel + `TaskWatcher` +
  `Gui.Control.addTaskWatcher`/`showDialog`). Draft does the same from
  `src/Mod/Draft/DraftGui.py` (`_show_dialog` →
  `FreeCADGui.Control.showDialog(panel)`, then
  `task.setDocumentName(...)`, `task.setAutoCloseOnDeletedDocument(True)`).
- User-facing docs: "Task Panel"
  (https://wiki.freecad.org/Task_panel) and "Creating interface tools"
  (https://wiki.freecad.org/Manual:Creating_interface_tools — the
  `BoxTaskPanel` recipe: `self.form = FreeCADGui.PySideUic.loadUi(...)`,
  `accept()` writes geometry, `FreeCADGui.Control.closeDialog()`).

Assessment: a task panel is an excellent **UI for a guided flow**, but it is
stateless by design — `accept()` is where you materialize results into
document objects. It cannot *be* the workflow state; it can only drive it.
Cost to Silk: one new file, pure additive, works from AddonManager. This is
the strongest UI primitive available to a Python workbench.

### (b) Container object + property-driven state

FreeCAD's native parametric idiom, and the one Silk already uses:

- `doc.addObject("Part::FeaturePython")` + proxy `execute()`/`onChanged()`,
  `obj.touch()`, `doc.recompute()` — Silk's `SilkPatch44.py`/`SilkBlend.py`
  are live in-repo examples; dependency propagation via
  `App::PropertyLink(List)` is exactly what recompute ordering gives for free.
- `App::DocumentObjectGroupPython` is available for tree containers
  (Silk already uses it for the BoundarySpline group in `SilkWorkflow.py`).
- In-tree 1.1 precedent for a *Python* container with property-driven state
  and a recompute proxy: the Assembly workbench's joint objects —
  `src/Mod/Assembly/JointObject.py`: `class Joint` (line 174) adds ~20 typed
  properties (`App::PropertyEnumeration` for joint type, `App::PropertyLink`
  refs, offset/rotation vectors) and drives behaviour from `onChanged()`
  (line 765) and `execute()` (line 816); a `GroundedJoint` proxy (line 1215)
  does the same. All workflow state is inspectable in the property editor,
  survives document save/reload, and is undoable — none of which a task panel
  or a command chain provides.

Assessment: this is the correct **source of truth** for the workflow. As a
*standalone UX* it is weak: a property editor is not a wizard; the user must
know which step to fill next.

### (c) Toolbar command chains with selection

The primitives, from 1.1 source:

- Commands: `Gui::Command` (`src/Gui/Command.h`) with `GetResources`/
  `IsActive`/`Activated`/`Execute` from Python (`src/Gui/PythonWorkbenchPyImp.cpp`
  binds `appendMenu`/`appendToolbar`; Silk's `InitGui.py` uses this today).
- Selection API: `Gui.Selection` module (registered in `src/Gui/Application.cpp`,
  methods table at `src/Gui/Selection/Selection.cpp:2221`): `addSelection`,
  `updateSelection`, `removeSelection`, `clearSelection`, `isSelected`,
  `setPreselection`/`getPreselection`, `getSelection`,
  `countObjectsOfType`; plus `addSelectionGate` (`src/Gui/Selection/Selection.h:420`)
  and observer registration; `Gui.runCommand` is bound at
  `src/Gui/ApplicationPy.cpp:244`.
- Silk's `SilkWorkflow.CreateBoundarySplineCommand` is the in-repo example and
  demonstrates the failure mode: it must `Gui.runCommand` two upstream
  commands in sequence, snapshot `doc` objects before/after to guess which
  output belongs to it, and hand the selection to the second command by
  force. Any user interruption, rename, or extra object breaks the chain;
  nothing is persistent; undo leaves a half-built chain.

Assessment: commands + selection are the right **picking/activation**
mechanism (they are the only way to get the user to point at geometry), but a
command chain is a bad **state machine**: transient, non-inspectable, fragile
under user freedom, and it re-runs upstream code paths rather than driving
Silk's own objects.

### (d) Hybrid — and the strongest in-tree precedent

FreeCAD 1.1's own Assembly workbench (new in 1.x, core, Python-heavy) is
exactly this hybrid for a guided multi-step flow:

- **State = property-driven container objects** (`Joint`/`GroundedJoint` in
  `src/Mod/Assembly/JointObject.py`, see (b)).
- **Activation = commands + task watchers** (`src/Mod/Assembly/InitGui.py`:
  `AssemblyCreateWatcher`, `AssemblyJointsWatcher`, etc., each with
  `commands`/`widgets`/`shouldShow`).
- **Interaction = task panel + selection gate + selection observer**, all in
  `JointObject.py`:
  - `ViewProviderJoint` context menu builds
    `TaskAssemblyCreateJoint(...)` and opens it with
    `Gui.Control.showDialog(panel)`, then
    `dialog.setAutoCloseOnTransactionChange(True)` /
    `setAutoCloseOnDeletedDocument(True)` / `setDocumentName(...)`
    (line 1200).
  - `MakeJointSelGate` (line 1422) implements `allow(doc, obj, sub)` so only
    valid joint candidate elements are selectable — registered via
    `Gui.Selection.addSelectionGate(gate, Gui.Selection.ResolveMode.NoResolve)`
    (line 1599).
  - The task panel registers itself as a selection observer
    (`Gui.Selection.addObserver(self, ...)`, `setSelectionStyle(GreedySelection)`)
    and a 3D-view mouse callback (`view.addEventCallback("SoLocation2Event", ...)`)
    to drive live preview while the user picks the second element.
- The panel is a *form over the object being created*: it writes the two
  picked references back to selection and to the joint's link properties;
  the joint's `execute()` does the actual constraint solve. Panel closed, the
  object and its state remain fully editable in the property editor.

## Comparison

| | (a) task panel | (b) property-driven container | (c) command chain + selection | (d) hybrid (Assembly pattern) |
|---|---|---|---|---|
| State persistence | ✗ (transient until `accept()`) | ✓ document object, saved, undoable | ✗ | ✓ (via (b)) |
| Inspectable/editable after creation | ✗ | ✓ property editor | ✗ | ✓ |
| Guided step-by-step UX | ✓ (best-in-class widget space) | ✗ | ~ (sequential prompts) | ✓ |
| Geometry picking | via selection, manual | ✗ | ✓ (native) | ✓ + selection **gate** |
| Python-only from an addon | ✓ (`Gui.Control.showDialog`) | ✓ (`addProperty`/`execute`/`touch`) | ✓ | ✓ |
| Fits Silk's existing objects | drives them | **is** them | re-runs upstream commands (fragile) | drives them |
| PR-clean/additive for fork | ✓ new file | ✓ new file | already exists, fragile | ✓ new files only |
| Precedent in 1.1 | TemplatePyMod, Draft | Assembly joints, Silk itself | Silk `SilkWorkflow.py` (painful) | **Assembly workbench** |

## Recommendation

**(d) Hybrid: (b) as the backbone, (a) as the wizard UI, (c) reduced to
picking.**

1. **State machine = one new container `Part::FeaturePython`** ("Silk
   Workflow" object) with an `App::PropertyEnumeration` `Stage`
   (`Sketches` → `Edges` → `Patches` → `Blends`) and `PropertyLinkList`
   properties for each layer. Its `execute()` validates stage invariants
   (e.g. "4 boundary edges present ⇒ can create a patch"). This reuses Silk's
   existing recompute machinery (idiom b), is purely additive, and keeps the
   workflow inspectable/undoable/serializable — the three things idioms (a)
   and (c) cannot do alone.
2. **Wizard UI = one Python task panel** opened with
   `Gui.Control.showDialog(panel)` from a single "Silk Workflow" command. The
   panel is a *form over the container object*: it shows current stage,
   what is needed next, and "Create next step" buttons that call the
   **existing** `SilkPatch44`/`SilkBlend`/`SilkEdge` create functions and
   assign results to the container's link properties. The panel never owns
   state; closing it (Esc) leaves the document fully valid. Copy the exact
   1.1 idiom: `dialog.setAutoCloseOnTransactionChange(True)` +
   `setAutoCloseOnDeletedDocument(True)` + `setDocumentName(doc.Name)`.
3. **Selection only for picking**, upgraded from Silk's current raw
   selection hand-offs: register a selection gate
   (`Gui.Selection.addSelectionGate` with an `allow(doc, obj, sub)` that
   accepts only stage-valid objects, e.g. unblended patches) and an observer,
   Assembly-style, while the panel is open.
4. **Explicit non-goals**: do not attempt PartDesign's in-edit-feature model
   (C++ only), and do not extend `SilkWorkflow.py`'s
   `Gui.runCommand`-chaining pattern — the new container drives creation
   directly instead of re-running upstream commands.

## Concrete stub design for the prototype ticket

Throwaway, single-file, additive (no edits to upstream files, no edits to
existing Silk proxies):

- **`SilkGuide.py`** (new):
  - `class WorkflowProxy` for a `Part::FeaturePython` "SilkWorkflow" object:
    - `Stage` (`App::PropertyEnumeration`, default `"Sketches"`),
    - `BoundaryEdges`, `Patches`, `BlendStrips` (`App::PropertyLinkList`),
    - `execute(fp)`: recompute a `StageOk`-style status — e.g. count edges
      per boundary and expose a read-only `App::PropertyString`
      `NextStepHint` ("4/4 edges — create Patch44").
  - `class WorkflowTaskPanel`: builds `self.form` in code (a `QVBoxLayout`
    with stage label, hint label, and one `QPushButton` per valid next
    action — no `.ui` file needed for a stub). Methods: `open()` (read the
    container, enable valid buttons), `changed(widget)` (if a "pick" button,
    register gate+observer and let the 3D pick fill a
    `QListWidget`), `accept()`/`reject()` → `Gui.Control.closeDialog()`.
    The create buttons call the existing create functions and append the
    returned objects to the container's link lists + `doc.recompute()`.
  - `class CreateWorkflowCommand` (`GetResources`/`IsActive`/`Activated`):
    creates the container object if absent, opens the panel via
    `Gui.Control.showDialog(panel)` with the three `dialog` setup calls
    above.
  - One-line addition to `InitGui.py` command list is the *only* touch to an
    existing file — mark it for the spec ticket to decide whether the stub
    keeps it.
- **Acceptance for the stub**: open `Silk_Workflow.FCStd`, run the command,
  and step one full chain (edge set → patch → blend) from the panel; close
  the panel mid-flow, change a property by hand, re-open, and the panel must
  resume from the stored `Stage`. This proves state lives in the object, not
  the panel.
- Do **not** build: task watchers, selection-gate subclasses, or per-stage
  panels in the stub — the follow-up spec decides how far "guided" goes.

## Sources

FreeCAD 1.1 (`releases/FreeCAD-1-1`) source:

- Task panel/box classes: https://github.com/FreeCAD/FreeCAD/blob/releases/FreeCAD-1-1/src/Gui/TaskView/TaskView.h ; dialog: https://github.com/FreeCAD/FreeCAD/blob/releases/FreeCAD-1-1/src/Gui/TaskView/TaskDialog.h
- Python task-panel protocol & `Gui.Control` bindings: https://github.com/FreeCAD/FreeCAD/blob/releases/FreeCAD-1-1/src/Gui/TaskView/TaskDialogPython.cpp (and `.h`)
- Template workbench task panel: https://github.com/FreeCAD/FreeCAD/blob/releases/FreeCAD-1-1/src/Mod/TemplatePyMod/TaskPanel.py
- PartDesign C++ task boxes: https://github.com/FreeCAD/FreeCAD/blob/releases/FreeCAD-1-1/src/Mod/PartDesign/Gui/TaskFeaturePick.cpp (pattern repeats across `Task*`)
- Selection API: https://github.com/FreeCAD/FreeCAD/blob/releases/FreeCAD-1-1/src/Gui/Selection/Selection.cpp (PyMethodDef table, line 2221), `Selection.h` (`addSelectionGate`), `src/Gui/FreeCADGuiInit.py` (`SelectionStyle`), `src/Gui/Application.cpp` (module registration)
- `Gui.runCommand` binding: https://github.com/FreeCAD/FreeCAD/blob/releases/FreeCAD-1-1/src/Gui/ApplicationPy.cpp
- Assembly hybrid precedent: https://github.com/FreeCAD/FreeCAD/blob/releases/FreeCAD-1-1/src/Mod/Assembly/JointObject.py (Joint proxy, `MakeJointSelGate`, `TaskAssemblyCreateJoint`, `Gui.Control.showDialog`) and https://github.com/FreeCAD/FreeCAD/blob/releases/FreeCAD-1-1/src/Mod/Assembly/InitGui.py (task watchers)
- Draft task panel: https://github.com/FreeCAD/FreeCAD/blob/releases/FreeCAD-1-1/src/Mod/Draft/DraftGui.py (`_show_dialog`, `DraftTaskPanel`)

Wiki:

- Task Panel (user): https://wiki.freecad.org/Task_panel
- Creating interface tools (developer recipe for Python task panels): https://wiki.freecad.org/Manual:Creating_interface_tools

Silk (this fork): `AGENTS.md`, `InitGui.py`, `SilkWorkflow.py`,
`SilkPatch44.py`, `SilkBlend.py`, `docs/adr/0001-upstream-first-fork-strategy.md`.
