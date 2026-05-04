# Silk WorkflowManual Migration to v1-1 — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Port BoundarySpline + ControlGridPatch workflows, reload infrastructure, test fixtures, and MCP-based test framework from `Mod/Silk` to `v1-1/Mod/Silk`.

**Architecture:** Bottom-up validation first — prove v1-1 APIs still work via MCP scripts, then copy files incrementally, testing each step. Nothing modifies existing Silk class behavior; all additions are in new files or targeted insertions. Agent self-tests via MCP `execute_code` → JSON results loop.

**Tech Stack:** FreeCAD v1.1 Python API, Silk workbench (ArachNURBS, ControlPoly4, ControlGrid44, CubicCurve_4, CubicSurface_44), FreeCAD MCP server (`execute_code` tool), Python 3.

---

## File Map

| Action | Path | Responsibility |
|--------|------|----------------|
| CREATE | `Tests/__init__.py` | Package marker |
| CREATE | `Tests/mcp_harness.py` | Test runner for agent via MCP |
| CREATE | `Tests/test_api_smoke.py` | Phase 1 API validation tests |
| CREATE | `Tests/test_workflow.py` | BoundarySpline + ControlGridPatch E2E tests |
| CREATE | `SilkWorkflow.py` | BoundarySpline + ControlGridPatch commands (copied from old, verified) |
| CREATE | `SilkReloadManager.py` | Full hot-reload manager (copied from old) |
| CREATE | `Resources/Test_files/Silk_2Boundaries.FCStd` | Reference test fixture (copied from old) |
| CREATE | `Resources/Test_files/Silk_2BoundariesAndControlGrids.FCStd` | Reference test fixture (copied from old) |
| CREATE | `Resources/Icons/BoundarySpline.svg` | Icon (copied from old) |
| CREATE | `Resources/Icons/ControlGridPatch.svg` | Icon (copied from old) |
| REPLACE | `Reload_Silk.py` | Rewire to SilkReloadManager |
| MODIFY | `InitGui.py` | Add SilkWorkflow import + 2 commands + test path |

---

### Task 1: Create test directory and harness

**Files:**
- Create: `Tests/__init__.py`
- Create: `Tests/mcp_harness.py`

- [ ] **Step 1: Create `Tests/__init__.py`**

```python
"""Silk Workbench MCP test suite."""
```

- [ ] **Step 2: Create `Tests/mcp_harness.py`**

```python
"""
Test harness for agent-driven testing via FreeCAD MCP.

The agent sends test functions via MCP execute_code.
Each test returns a dict {"pass": bool, "errors": [str, ...], "checks": [...]}.
The harness collects results and prints a JSON summary line the agent can parse.
"""

import FreeCAD
import json


def run_tests(*test_funcs, verbose=True):
    """Run test functions, return JSON summary.

    Each test_func must accept a document and return a dict:
        {"pass": bool, "errors": [str, ...], "checks": [...]}

    Prints a single JSON line "RESULT:<json>" at the end for agent parsing.
    """
    results = []
    for func in test_funcs:
        doc = None
        try:
            doc_name = "_mcp_test_" + func.__name__
            doc = FreeCAD.newDocument(doc_name)
            outcome = func(doc)
            if not isinstance(outcome, dict):
                outcome = {"pass": False, "errors": ["Test returned non-dict: " + str(type(outcome))], "checks": []}
            else:
                outcome.setdefault("checks", [])
                outcome.setdefault("errors", [])
            outcome["name"] = func.__name__
            results.append(outcome)
        except Exception as e:
            import traceback
            results.append({
                "name": func.__name__,
                "pass": False,
                "errors": [str(e)],
                "checks": [],
                "traceback": traceback.format_exc()
            })
        finally:
            if doc is not None:
                try:
                    FreeCAD.closeDocument(doc.Name)
                except Exception:
                    pass

    passed = sum(1 for r in results if r.get("pass"))
    failed = len(results) - passed

    summary = {
        "total": len(results),
        "passed": passed,
        "failed": failed,
        "results": results
    }

    if verbose:
        for r in results:
            status = "PASS" if r.get("pass") else "FAIL"
            print(f"  [{status}] {r['name']}")
            for err in r.get("errors", []):
                print(f"    ERROR: {err}")

        print(f"\n{passed}/{len(results)} passed, {failed} failed")

    # Machine-parseable line
    print("RESULT:" + json.dumps(summary))
    return summary
```

---

### Task 2: API validation tests (Phase 1)

**Files:**
- Create: `Tests/test_api_smoke.py`

- [ ] **Step 1: Create `Tests/test_api_smoke.py`**

```python
"""
API validation tests for v1-1 Silk workbench.
Each function takes a FreeCAD document and returns {"pass": bool, "errors": [...], ...}.

Run via: from Tests.mcp_harness import run_tests; run_tests(test_1, test_2, ...)
"""

import FreeCAD
import Part
from FreeCAD import Gui


def check(condition, msg, errors):
    """Append msg to errors if condition is False."""
    if not condition:
        errors.append(msg)
    return condition


def test_controlpoly4_3_lines(doc):
    """ControlPoly4 from sketch with exactly 3 visible line segments."""
    errors = []
    checks = []

    sketch = doc.addObject("Sketcher::SketchObject", "Sketch")
    sketch.Placement = FreeCAD.Placement(
        FreeCAD.Vector(0, 0, 0),
        FreeCAD.Rotation(90, 0, 90)
    )
    geo = [
        Part.LineSegment(FreeCAD.Vector(0, 40, 0), FreeCAD.Vector(25, 40, 0)),
        Part.LineSegment(FreeCAD.Vector(25, 40, 0), FreeCAD.Vector(50, 15, 0)),
        Part.LineSegment(FreeCAD.Vector(50, 15, 0), FreeCAD.Vector(50, 0, 0))
    ]
    sketch.addGeometry(geo)
    doc.recompute()

    Gui.Selection.clearSelection()
    Gui.Selection.addSelection(sketch)
    ok = Gui.runCommand("ControlPoly4")
    check(ok is not False, "ControlPoly4 command failed", errors)

    polys = [obj for obj in doc.Objects
             if obj.Name.startswith("ControlPoly4") and hasattr(obj, "Poles")]
    check(len(polys) >= 1, f"Expected >=1 ControlPoly4, got {len(polys)}", errors)
    if polys:
        checks.append(f"Created {polys[0].Name} with {len(polys[0].Poles)} poles")
        check(len(polys[0].Poles) == 4, f"Expected 4 poles, got {len(polys[0].Poles)}", errors)

    return {"pass": len(errors) == 0, "errors": errors, "checks": checks}


def test_controlpoly4_first_element(doc):
    """ControlPoly4 in FirstElement mode (sketch with !=3 visible lines)."""
    errors = []
    checks = []

    sketch = doc.addObject("Sketcher::SketchObject", "Sketch")
    sketch.Placement = FreeCAD.Placement(
        FreeCAD.Vector(0, 0, 0),
        FreeCAD.Rotation(90, 0, 90)
    )
    # One line only — triggers FirstElement mode
    geo = [
        Part.LineSegment(FreeCAD.Vector(0, 40, 0), FreeCAD.Vector(50, 0, 0))
    ]
    sketch.addGeometry(geo)
    doc.recompute()

    Gui.Selection.clearSelection()
    Gui.Selection.addSelection(sketch)
    ok = Gui.runCommand("ControlPoly4")
    check(ok is not False, "ControlPoly4 FirstElement command failed", errors)

    polys = [obj for obj in doc.Objects
             if obj.Name.startswith("ControlPoly4") and hasattr(obj, "Poles")]
    check(len(polys) >= 1, f"Expected >=1 ControlPoly4, got {len(polys)}", errors)

    return {"pass": len(errors) == 0, "errors": errors, "checks": checks}


def test_cubic_curve_4(doc):
    """CubicCurve_4 from a ControlPoly4."""
    errors = []
    checks = []

    sketch = doc.addObject("Sketcher::SketchObject", "Sketch")
    sketch.Placement = FreeCAD.Placement(
        FreeCAD.Vector(0, 0, 0),
        FreeCAD.Rotation(90, 0, 90)
    )
    geo = [
        Part.LineSegment(FreeCAD.Vector(0, 40, 0), FreeCAD.Vector(25, 40, 0)),
        Part.LineSegment(FreeCAD.Vector(25, 40, 0), FreeCAD.Vector(50, 15, 0)),
        Part.LineSegment(FreeCAD.Vector(50, 15, 0), FreeCAD.Vector(50, 0, 0))
    ]
    sketch.addGeometry(geo)
    doc.recompute()

    Gui.Selection.clearSelection()
    Gui.Selection.addSelection(sketch)
    Gui.runCommand("ControlPoly4")

    polys = [obj for obj in doc.Objects
             if obj.Name.startswith("ControlPoly4") and hasattr(obj, "Poles")]
    check(len(polys) >= 1, "No ControlPoly4 created", errors)
    if not polys:
        return {"pass": False, "errors": errors, "checks": checks}

    Gui.Selection.clearSelection()
    Gui.Selection.addSelection(polys[0])
    Gui.runCommand("CubicCurve_4")

    curves = [obj for obj in doc.Objects
              if obj.Name.startswith("CubicCurve") and hasattr(obj, "Shape")]
    check(len(curves) >= 1, f"Expected >=1 CubicCurve, got {len(curves)}", errors)
    if curves:
        check(curves[0].Shape is not None, "CubicCurve has no Shape", errors)
        checks.append(f"Curve {curves[0].Name} has valid Shape")

    return {"pass": len(errors) == 0, "errors": errors, "checks": checks}


def test_controlgrid44_4(doc):
    """ControlGrid44_4 from 4 ControlPoly4 objects."""
    errors = []
    checks = []

    # Create 4 sketches with 3 lines each
    placements = [
        (FreeCAD.Vector(0, 0, 0), FreeCAD.Rotation(90, 0, 90)),
        (FreeCAD.Vector(0, 0, 40), FreeCAD.Rotation(0, 0, 90)),
        (FreeCAD.Vector(0, 50, 0), FreeCAD.Rotation(0, 0, 0)),
        (FreeCAD.Vector(50, 50, 0), FreeCAD.Rotation(-90, 0, 0)),
    ]
    polys = []
    for i, (pos, rot) in enumerate(placements):
        sk = doc.addObject("Sketcher::SketchObject", f"Sketch_{i}")
        sk.Placement = FreeCAD.Placement(pos, rot)
        geo = [
            Part.LineSegment(FreeCAD.Vector(0, 40, 0), FreeCAD.Vector(25, 40, 0)),
            Part.LineSegment(FreeCAD.Vector(25, 40, 0), FreeCAD.Vector(50, 15, 0)),
            Part.LineSegment(FreeCAD.Vector(50, 15, 0), FreeCAD.Vector(50, 0, 0))
        ]
        sk.addGeometry(geo)
        doc.recompute()
        Gui.Selection.clearSelection()
        Gui.Selection.addSelection(sk)
        Gui.runCommand("ControlPoly4")
        p = [obj for obj in doc.Objects if obj.Name.startswith("ControlPoly4") and hasattr(obj, "Poles")]
        if p:
            polys.append(p[-1])

    check(len(polys) == 4, f"Expected 4 ControlPoly4, got {len(polys)}", errors)
    if len(polys) != 4:
        return {"pass": False, "errors": errors, "checks": checks}

    Gui.Selection.clearSelection()
    for p in polys:
        Gui.Selection.addSelection(p)
    Gui.runCommand("ControlGrid44")

    grids = [obj for obj in doc.Objects
             if obj.Name.startswith("ControlGrid44") and hasattr(obj, "Poles")
             and len(obj.Poles) == 16]
    check(len(grids) >= 1, f"Expected >=1 ControlGrid44 with 16 poles, got {len(grids)}", errors)
    if grids:
        checks.append(f"Grid {grids[0].Name}: {len(grids[0].Poles)} poles")

    return {"pass": len(errors) == 0, "errors": errors, "checks": checks}


def test_cubic_surface_44(doc):
    """CubicSurface_44 from ControlGrid44."""
    errors = []
    checks = []

    placements = [
        (FreeCAD.Vector(0, 0, 0), FreeCAD.Rotation(90, 0, 90)),
        (FreeCAD.Vector(0, 0, 40), FreeCAD.Rotation(0, 0, 90)),
        (FreeCAD.Vector(0, 50, 0), FreeCAD.Rotation(0, 0, 0)),
        (FreeCAD.Vector(50, 50, 0), FreeCAD.Rotation(-90, 0, 0)),
    ]
    polys = []
    for i, (pos, rot) in enumerate(placements):
        sk = doc.addObject("Sketcher::SketchObject", f"Sketch_{i}")
        sk.Placement = FreeCAD.Placement(pos, rot)
        geo = [
            Part.LineSegment(FreeCAD.Vector(0, 40, 0), FreeCAD.Vector(25, 40, 0)),
            Part.LineSegment(FreeCAD.Vector(25, 40, 0), FreeCAD.Vector(50, 15, 0)),
            Part.LineSegment(FreeCAD.Vector(50, 15, 0), FreeCAD.Vector(50, 0, 0))
        ]
        sk.addGeometry(geo)
        doc.recompute()
        Gui.Selection.clearSelection()
        Gui.Selection.addSelection(sk)
        Gui.runCommand("ControlPoly4")
        p = [obj for obj in doc.Objects if obj.Name.startswith("ControlPoly4") and hasattr(obj, "Poles")]
        if p:
            polys.append(p[-1])

    Gui.Selection.clearSelection()
    for p in polys:
        Gui.Selection.addSelection(p)
    Gui.runCommand("ControlGrid44")
    grids = [obj for obj in doc.Objects
             if obj.Name.startswith("ControlGrid44") and hasattr(obj, "Poles")
             and len(obj.Poles) == 16]
    check(len(grids) >= 1, "No ControlGrid44", errors)
    if not grids:
        return {"pass": False, "errors": errors, "checks": checks}

    Gui.Selection.clearSelection()
    Gui.Selection.addSelection(grids[0])
    Gui.runCommand("CubicSurface_44")
    surfaces = [obj for obj in doc.Objects
                if obj.Name.startswith("CubicSurface") and hasattr(obj, "Shape")]
    check(len(surfaces) >= 1, f"Expected >=1 CubicSurface, got {len(surfaces)}", errors)
    if surfaces:
        check(surfaces[0].Shape is not None, "Surface has no Shape", errors)
        check(hasattr(surfaces[0].Shape, "Faces"), "Surface Shape has no Faces", errors)
        checks.append(f"Surface {surfaces[0].Name} created")

    return {"pass": len(errors) == 0, "errors": errors, "checks": checks}


def test_controlgrid44_3(doc):
    """ControlGrid44_3 from 3 ControlPoly4 objects (triangular grid)."""
    errors = []
    checks = []

    placements = [
        (FreeCAD.Vector(0, 0, 0), FreeCAD.Rotation(90, 0, 90)),
        (FreeCAD.Vector(0, 0, 40), FreeCAD.Rotation(0, 0, 90)),
        (FreeCAD.Vector(0, 50, 0), FreeCAD.Rotation(0, 0, 0)),
    ]
    polys = []
    for i, (pos, rot) in enumerate(placements):
        sk = doc.addObject("Sketcher::SketchObject", f"Sketch_{i}")
        sk.Placement = FreeCAD.Placement(pos, rot)
        geo = [
            Part.LineSegment(FreeCAD.Vector(0, 40, 0), FreeCAD.Vector(25, 40, 0)),
            Part.LineSegment(FreeCAD.Vector(25, 40, 0), FreeCAD.Vector(50, 15, 0)),
            Part.LineSegment(FreeCAD.Vector(50, 15, 0), FreeCAD.Vector(50, 0, 0))
        ]
        sk.addGeometry(geo)
        doc.recompute()
        Gui.Selection.clearSelection()
        Gui.Selection.addSelection(sk)
        Gui.runCommand("ControlPoly4")
        p = [obj for obj in doc.Objects if obj.Name.startswith("ControlPoly4") and hasattr(obj, "Poles")]
        if p:
            polys.append(p[-1])

    check(len(polys) == 3, f"Expected 3 ControlPoly4, got {len(polys)}", errors)
    if len(polys) != 3:
        return {"pass": False, "errors": errors, "checks": checks}

    Gui.Selection.clearSelection()
    for p in polys:
        Gui.Selection.addSelection(p)
    Gui.runCommand("ControlGrid44_3_1Grid44")

    tri = [obj for obj in doc.Objects
           if obj.Name.startswith("ControlGrid44_3") and hasattr(obj, "Poles")]

    if tri:
        checks.append(f"Tri-grid {tri[0].Name}: {len(tri[0].Poles)} poles")
        check(len(tri[0].Poles) == 16, f"Expected 16 poles, got {len(tri[0].Poles)}", errors)
    else:
        errors.append("No ControlGrid44_3 found")

    return {"pass": len(errors) == 0, "errors": errors, "checks": checks}


ALL_TESTS = [
    test_controlpoly4_3_lines,
    test_controlpoly4_first_element,
    test_cubic_curve_4,
    test_controlgrid44_4,
    test_cubic_surface_44,
    test_controlgrid44_3,
]
```

- [ ] **Step 2: Run API validation via MCP**

Send to FreeCAD via MCP `execute_code`:
```python
import sys
sys.path.insert(0, "/home/mo/.local/share/FreeCAD/v1-1/Mod/Silk")
from Tests.mcp_harness import run_tests
from Tests.test_api_smoke import ALL_TESTS
run_tests(*ALL_TESTS)
```

Expected: All 6 pass. If any fail, read the error and fix before proceeding.

- [ ] **Step 3: Verify and commit**

```bash
cd /home/mo/.local/share/FreeCAD/v1-1/Mod/Silk
git add Tests/
git commit -m "test: add MCP test harness and API validation tests"
```

---

### Task 3: Copy test fixture FCStd files and icons

**Files:**
- Create: `Resources/Test_files/Silk_2Boundaries.FCStd`
- Create: `Resources/Test_files/Silk_2BoundariesAndControlGrids.FCStd`
- Create: `Resources/Icons/BoundarySpline.svg`
- Create: `Resources/Icons/ControlGridPatch.svg`

- [ ] **Step 1: Copy fixture files**

```bash
mkdir -p /home/mo/.local/share/FreeCAD/v1-1/Mod/Silk/Resources/Test_files
cp /home/mo/.local/share/FreeCAD/Mod/Silk/Resources/Test_files/Silk_2Boundaries.FCStd \
   /home/mo/.local/share/FreeCAD/v1-1/Mod/Silk/Resources/Test_files/
cp /home/mo/.local/share/FreeCAD/Mod/Silk/Resources/Test_files/Silk_2BoundariesAndControlGrids.FCStd \
   /home/mo/.local/share/FreeCAD/v1-1/Mod/Silk/Resources/Test_files/
```

- [ ] **Step 2: Copy icons**

```bash
cp /home/mo/.local/share/FreeCAD/Mod/Silk/Resources/Icons/BoundarySpline.svg \
   /home/mo/.local/share/FreeCAD/v1-1/Mod/Silk/Resources/Icons/
cp /home/mo/.local/share/FreeCAD/Mod/Silk/Resources/Icons/ControlGridPatch.svg \
   /home/mo/.local/share/FreeCAD/v1-1/Mod/Silk/Resources/Icons/
```

- [ ] **Step 3: Commit**

```bash
git add Resources/Test_files/ Resources/Icons/BoundarySpline.svg Resources/Icons/ControlGridPatch.svg
git commit -m "feat: add test fixture files and workflow icons"
```

---

### Task 4: Port SilkWorkflow.py

**Files:**
- Create: `SilkWorkflow.py`

- [ ] **Step 1: Copy SilkWorkflow.py from old to new**

```bash
cp /home/mo/.local/share/FreeCAD/Mod/Silk/SilkWorkflow.py \
   /home/mo/.local/share/FreeCAD/v1-1/Mod/Silk/SilkWorkflow.py
```

- [ ] **Step 2: Verify SilkWorkflow imports via MCP**

Send to FreeCAD via MCP `execute_code`:
```python
import sys
sys.path.insert(0, "/home/mo/.local/share/FreeCAD/v1-1/Mod/Silk")
from SilkWorkflow import CreateBoundarySplineCommand, CreateControlGridPatchCommand
print("CreateBoundarySplineCommand:", CreateBoundarySplineCommand)
print("CreateControlGridPatchCommand:", CreateControlGridPatchCommand)
print("OK")
```

Expected: prints "OK" with no import errors.

- [ ] **Step 3: Test BoundarySpline via MCP**

Send to FreeCAD via MCP `execute_code`:
```python
import sys, FreeCAD, Part, json
sys.path.insert(0, "/home/mo/.local/share/FreeCAD/v1-1/Mod/Silk")
from SilkWorkflow import CreateBoundarySplineCommand
from FreeCAD import Gui

doc = FreeCAD.newDocument("_mcp_bs_test")
sketch = doc.addObject("Sketcher::SketchObject", "Sketch")
sketch.Placement = FreeCAD.Placement(FreeCAD.Vector(0,0,0), FreeCAD.Rotation(90,0,90))
geo = [
    Part.LineSegment(FreeCAD.Vector(0,40,0), FreeCAD.Vector(25,40,0)),
    Part.LineSegment(FreeCAD.Vector(25,40,0), FreeCAD.Vector(50,15,0)),
    Part.LineSegment(FreeCAD.Vector(50,15,0), FreeCAD.Vector(50,0,0))
]
sketch.addGeometry(geo)
doc.recompute()

Gui.Selection.clearSelection()
Gui.Selection.addSelection(sketch)
cmd = CreateBoundarySplineCommand()
cmd.Activated()

boundaries = [obj for obj in doc.Objects
             if "BoundarySpline" in obj.Name
             and obj.TypeId == "App::DocumentObjectGroupPython"]
result = {"pass": len(boundaries) == 1, "bs_count": len(boundaries)}
if boundaries:
    result["group_contents"] = [o.Name for o in boundaries[0].Group]
print("RESULT:" + json.dumps(result))
FreeCAD.closeDocument(doc.Name)
```

Expected: `{"pass": true, "bs_count": 1, "group_contents": ["ControlPoly4...", "CubicCurve_4..."]}`

- [ ] **Step 4: Test ControlGridPatch via MCP**

Send to FreeCAD via MCP `execute_code`:
```python
import sys, FreeCAD, Part, json
sys.path.insert(0, "/home/mo/.local/share/FreeCAD/v1-1/Mod/Silk")
from SilkWorkflow import CreateBoundarySplineCommand, CreateControlGridPatchCommand
from FreeCAD import Gui

doc = FreeCAD.newDocument("_mcp_cgp_test")

# Create 4 boundaries
placements = [
    (FreeCAD.Vector(0,0,0), FreeCAD.Rotation(90,0,90)),
    (FreeCAD.Vector(0,0,40), FreeCAD.Rotation(0,0,90)),
    (FreeCAD.Vector(0,50,0), FreeCAD.Rotation(0,0,0)),
    (FreeCAD.Vector(50,50,0), FreeCAD.Rotation(-90,0,0)),
]
boundaries = []
for i, (pos, rot) in enumerate(placements):
    sk = doc.addObject("Sketcher::SketchObject", f"Sketch_{i}")
    sk.Placement = FreeCAD.Placement(pos, rot)
    geo = [
        Part.LineSegment(FreeCAD.Vector(0,40,0), FreeCAD.Vector(25,40,0)),
        Part.LineSegment(FreeCAD.Vector(25,40,0), FreeCAD.Vector(50,15,0)),
        Part.LineSegment(FreeCAD.Vector(50,15,0), FreeCAD.Vector(50,0,0))
    ]
    sk.addGeometry(geo)
    doc.recompute()
    Gui.Selection.clearSelection()
    Gui.Selection.addSelection(sk)
    CreateBoundarySplineCommand().Activated()
    bs = [obj for obj in doc.Objects if obj.Name.startswith("BoundarySpline")]
    if bs:
        boundaries.append(bs[-1])

# Select all 4 boundaries
Gui.Selection.clearSelection()
for bs in boundaries:
    Gui.Selection.addSelection(bs)
CreateControlGridPatchCommand().Activated()

patches = [obj for obj in doc.Objects
           if obj.Name.startswith("ControlGridPatch")
           and obj.TypeId == "App::DocumentObjectGroupPython"]
result = {
    "pass": len(patches) == 1 and len(boundaries) == 4,
    "patch_count": len(patches),
    "boundary_count": len(boundaries)
}
if patches:
    result["group_contents"] = [o.Name for o in patches[0].Group]
print("RESULT:" + json.dumps(result))
FreeCAD.closeDocument(doc.Name)
```

Expected: `{"pass": true, "patch_count": 1, "boundary_count": 4}` with grid + surface in group_contents.

- [ ] **Step 5: Commit**

```bash
git add SilkWorkflow.py
git commit -m "feat: port SilkWorkflow (BoundarySpline + ControlGridPatch commands)"
```

---

### Task 5: Port SilkReloadManager and update Reload_Silk

**Files:**
- Create: `SilkReloadManager.py`
- Replace: `Reload_Silk.py`

- [ ] **Step 1: Copy SilkReloadManager.py**

```bash
cp /home/mo/.local/share/FreeCAD/Mod/Silk/SilkReloadManager.py \
   /home/mo/.local/share/FreeCAD/v1-1/Mod/Silk/SilkReloadManager.py
```

- [ ] **Step 2: Replace Reload_Silk.py**

Replace the entire content of `Reload_Silk.py` with the following:

```python
#    This file is part of Silk
#    (c) 2025
#
#    NURBS Surface modeling tools focused on low degree and seam continuity (FreeCAD Workbench)
#
#    Hot reload command for the Silk workbench

import os
import traceback

import FreeCAD
from FreeCAD import Gui

import Silk_dummy

path_Silk = os.path.dirname(Silk_dummy.__file__)
path_Silk_icons = os.path.join(path_Silk, "Resources", "Icons")


class Reload_Silk:
    def Activated(self):
        """Execute hot reload of Silk modules."""
        from SilkReloadManager import SimpleSilkReloadManager

        manager = SimpleSilkReloadManager()
        try:
            manager.reload_all()
            FreeCAD.Console.PrintMessage(
                "Silk: Module reload successful! Code changes are now active.\n"
            )
        except Exception as exc:
            FreeCAD.Console.PrintError(
                f"Reload_Silk: Reload failed: {exc}\n"
            )
            traceback.print_exc()

    def GetResources(self):
        return {
            "Pixmap": path_Silk_icons + "/WIP.svg",
            "MenuText": "Reload Silk Workbench",
            "ToolTip": (
                "Hot reload the entire Silk workbench without restarting FreeCAD.\n"
                "Reloads ArachNURBS, all commands, observers, and GUI elements.\n"
                "Use during development to see code changes immediately."
            ),
        }


Gui.addCommand("Reload_Silk", Reload_Silk())
```

- [ ] **Step 3: Verify reload works via MCP**

Send to FreeCAD via MCP `execute_code`:
```python
from SilkReloadManager import SimpleSilkReloadManager
mgr = SimpleSilkReloadManager()
mgr.reload_all()
print("RELOAD_OK")
```

Expected: prints "RELOAD_OK" with success messages, no errors.

- [ ] **Step 4: Commit**

```bash
git add SilkReloadManager.py Reload_Silk.py
git commit -m "feat: port full hot-reload manager"
```

---

### Task 6: Merge InitGui.py

**Files:**
- Modify: `InitGui.py`

- [ ] **Step 1: Read the current v1-1 InitGui.py to understand its structure**

- [ ] **Step 2: Add test path injection after the license header**

Insert after the license block and before `class Silk(Workbench):`:

```python
import sys
import os

# Add test directory to Python path for test discovery
path_Silk = os.path.dirname(__file__)
test_path = os.path.join(path_Silk, "Tests")
if test_path not in sys.path:
    sys.path.insert(0, test_path)
```

Note: v1-1's InitGui already imports `FreeCAD` and `os` — do not duplicate those.

- [ ] **Step 3: Add SilkWorkflow import in Initialize()**

In the `Initialize()` method import block, add after the `import SilkPose` line:

```python
        import SilkWorkflow
```

- [ ] **Step 4: Add commands to self.list**

In the `self.list` assignment, add before the closing `]`:

```python
            "Silk_CreateBoundarySpline",
            "Silk_CreateControlGridPatch",
```

- [ ] **Step 5: Verify commands are registered via MCP**

Send to FreeCAD via MCP `execute_code`:
```python
from FreeCAD import Gui
cmds = ["Silk_CreateBoundarySpline", "Silk_CreateControlGridPatch"]
for c in cmds:
    try:
        info = Gui.Commands.get(c)
        print(f"  {c}: registered")
    except:
        print(f"  {c}: MISSING")
```

Expected: both commands reported as registered.

- [ ] **Step 6: Commit**

```bash
git add InitGui.py
git commit -m "feat: add SilkWorkflow commands and test path to InitGui"
```

---

### Task 7: End-to-end workflow tests

**Files:**
- Create: `Tests/test_workflow.py`

- [ ] **Step 1: Create `Tests/test_workflow.py`**

```python
"""
End-to-end workflow tests for BoundarySpline and ControlGridPatch.
Each function takes a FreeCAD document and returns {"pass": bool, "errors": [...], ...}.

Run via: from Tests.mcp_harness import run_tests; run_tests(test_1, test_2, ...)
"""

import FreeCAD
import Part
from FreeCAD import Gui


def check(condition, msg, errors):
    if not condition:
        errors.append(msg)
    return condition


def _make_line_sketch(doc, name, pos, rot):
    sk = doc.addObject("Sketcher::SketchObject", name)
    sk.Placement = FreeCAD.Placement(pos, rot)
    geo = [
        Part.LineSegment(FreeCAD.Vector(0, 40, 0), FreeCAD.Vector(25, 40, 0)),
        Part.LineSegment(FreeCAD.Vector(25, 40, 0), FreeCAD.Vector(50, 15, 0)),
        Part.LineSegment(FreeCAD.Vector(50, 15, 0), FreeCAD.Vector(50, 0, 0))
    ]
    sk.addGeometry(geo)
    doc.recompute()
    return sk


def test_boundaryspline_single_sketch(doc):
    """Create a single BoundarySpline from one sketch."""
    errors, checks = [], []

    from SilkWorkflow import CreateBoundarySplineCommand
    sk = _make_line_sketch(doc, "Sketch",
        FreeCAD.Vector(0, 0, 0), FreeCAD.Rotation(90, 0, 90))

    Gui.Selection.clearSelection()
    Gui.Selection.addSelection(sk)
    CreateBoundarySplineCommand().Activated()

    bs_list = [obj for obj in doc.Objects
               if obj.Name.startswith("BoundarySpline")
               and obj.TypeId == "App::DocumentObjectGroupPython"]
    check(len(bs_list) == 1, f"Expected 1 BoundarySpline, got {len(bs_list)}", errors)
    if bs_list:
        bs = bs_list[0]
        check(len(bs.Group) == 2, f"Expected 2 children, got {len(bs.Group)}", errors)
        has_poly = any("ControlPoly4" in o.Name for o in bs.Group)
        has_curve = any("CubicCurve" in o.Name for o in bs.Group)
        check(has_poly, "Missing ControlPoly4 child", errors)
        check(has_curve, "Missing CubicCurve child", errors)
        checks.append(f"BoundarySpline {bs.Name}: poly={has_poly}, curve={has_curve}")

    return {"pass": len(errors) == 0, "errors": errors, "checks": checks}


def test_controlgridpatch_4(doc):
    """Create a ControlGridPatch from 4 BoundarySplines."""
    errors, checks = [], []

    from SilkWorkflow import CreateBoundarySplineCommand, CreateControlGridPatchCommand

    placements = [
        (FreeCAD.Vector(0, 0, 0), FreeCAD.Rotation(90, 0, 90)),
        (FreeCAD.Vector(0, 0, 40), FreeCAD.Rotation(0, 0, 90)),
        (FreeCAD.Vector(0, 50, 0), FreeCAD.Rotation(0, 0, 0)),
        (FreeCAD.Vector(50, 50, 0), FreeCAD.Rotation(-90, 0, 0)),
    ]
    boundaries = []
    for i, (pos, rot) in enumerate(placements):
        sk = _make_line_sketch(doc, f"Sketch_{i}", pos, rot)
        Gui.Selection.clearSelection()
        Gui.Selection.addSelection(sk)
        CreateBoundarySplineCommand().Activated()
        bs = [obj for obj in doc.Objects if obj.Name.startswith("BoundarySpline")]
        if bs:
            boundaries.append(bs[-1])

    check(len(boundaries) == 4, f"Expected 4 BoundarySplines, got {len(boundaries)}", errors)
    if len(boundaries) != 4:
        return {"pass": False, "errors": errors, "checks": checks}

    Gui.Selection.clearSelection()
    for bs in boundaries:
        Gui.Selection.addSelection(bs)
    CreateControlGridPatchCommand().Activated()

    patches = [obj for obj in doc.Objects
               if obj.Name.startswith("ControlGridPatch")
               and obj.TypeId == "App::DocumentObjectGroupPython"]
    check(len(patches) == 1, f"Expected 1 ControlGridPatch, got {len(patches)}", errors)
    if patches:
        patch = patches[0]
        group_names = [o.Name for o in patch.Group]
        checks.append(f"Patch {patch.Name}: {group_names}")
        has_grid = any("ControlGrid44" in n for n in group_names)
        has_surf = any("CubicSurface" in n for n in group_names)
        check(has_grid, "Missing ControlGrid44 child", errors)
        check(has_surf, "Missing CubicSurface child", errors)

    return {"pass": len(errors) == 0, "errors": errors, "checks": checks}


def test_controlgridpatch_3(doc):
    """Create a ControlGridPatch from 3 BoundarySplines."""
    errors, checks = [], []

    from SilkWorkflow import CreateBoundarySplineCommand, CreateControlGridPatchCommand

    placements = [
        (FreeCAD.Vector(0, 0, 0), FreeCAD.Rotation(90, 0, 90)),
        (FreeCAD.Vector(0, 0, 40), FreeCAD.Rotation(0, 0, 90)),
        (FreeCAD.Vector(0, 50, 0), FreeCAD.Rotation(0, 0, 0)),
    ]
    boundaries = []
    for i, (pos, rot) in enumerate(placements):
        sk = _make_line_sketch(doc, f"Sketch_{i}", pos, rot)
        Gui.Selection.clearSelection()
        Gui.Selection.addSelection(sk)
        CreateBoundarySplineCommand().Activated()
        bs = [obj for obj in doc.Objects if obj.Name.startswith("BoundarySpline")]
        if bs:
            boundaries.append(bs[-1])

    check(len(boundaries) == 3, f"Expected 3 BoundarySplines, got {len(boundaries)}", errors)
    if len(boundaries) != 3:
        return {"pass": False, "errors": errors, "checks": checks}

    Gui.Selection.clearSelection()
    for bs in boundaries:
        Gui.Selection.addSelection(bs)
    CreateControlGridPatchCommand().Activated()

    patches = [obj for obj in doc.Objects
               if obj.Name.startswith("ControlGridPatch")
               and obj.TypeId == "App::DocumentObjectGroupPython"]
    check(len(patches) == 1, f"Expected 1 ControlGridPatch, got {len(patches)}", errors)
    if patches:
        checks.append(f"3-sided patch {patches[0].Name} created")

    return {"pass": len(errors) == 0, "errors": errors, "checks": checks}


ALL_TESTS = [
    test_boundaryspline_single_sketch,
    test_controlgridpatch_4,
    test_controlgridpatch_3,
]
```

- [ ] **Step 2: Run workflow tests via MCP**

Send to FreeCAD via MCP `execute_code`:
```python
import sys
sys.path.insert(0, "/home/mo/.local/share/FreeCAD/v1-1/Mod/Silk")
from Tests.mcp_harness import run_tests
from Tests.test_workflow import ALL_TESTS
run_tests(*ALL_TESTS)
```

Expected: All 3 pass.

- [ ] **Step 3: Commit**

```bash
git add Tests/test_workflow.py
git commit -m "test: add end-to-end workflow tests"
```

---

### Task 8: Final verification — full test suite

- [ ] **Step 1: Run all tests together via MCP**

Send to FreeCAD via MCP `execute_code`:
```python
import sys
sys.path.insert(0, "/home/mo/.local/share/FreeCAD/v1-1/Mod/Silk")
from Tests.mcp_harness import run_tests
from Tests.test_api_smoke import ALL_TESTS as API_TESTS
from Tests.test_workflow import ALL_TESTS as WF_TESTS
run_tests(*(API_TESTS + WF_TESTS))
```

Expected: All 9 tests pass (6 API + 3 workflow).

- [ ] **Step 2: Commit final verification result**

```bash
git status
```
