# Silk Workbench - Agent Notes

## Overview
Silk is a FreeCAD workbench that provides low-degree NURBS curve and surface tools,
focused on seam continuity and small control nets. The repo is primarily Python
modules that define FreeCAD commands and FeaturePython objects.

## Entry Points
- `Init.py` - console-mode entry point (currently empty).
- `InitGui.py` - workbench registration, command imports, toolbar/menu wiring.

## Core Modules
- `ArachNURBS.py` - core geometry/utility routines used by most commands.
- `SilkWorkflow.py` - newer workflow objects/commands (BoundarySpline,
  SurfacePatch, Blend, debug helpers).
- `ControlPoly*.py`, `CubicCurve_*.py` - curve/control polygon commands.
- `ControlGrid*.py`, `CubicSurface_*.py`, `SubGrid*.py` - grid and surface
  commands, subdivisions, and transformations.
- `SilkPose.py` - placement/pose helper command for sketches.
- `Silk_tooltips.py` - tooltip strings and help text.
- `Reload_Silk.py` - reload helper for development.

## FreeCAD Object Patterns
- Commands are typically registered via `Gui.addCommand(...)` inside each module.
- FeaturePython objects are created with `Part::FeaturePython` or group objects
  with `App::DocumentObjectGroupPython`.
- Geometry output is usually stored on `obj.Shape` and recomputed via
  `doc.recompute()`.

## Resources
- `Resources/Icons` - command icons.
- `Resources/Demo_files` - demo images and example files referenced in README.

## Docs
- `README.md` - project overview and goals.
- `implementation_guide.md` - design notes for newer workflow objects.

## Development Notes
- There are no automated tests; validation is typically manual in FreeCAD.
- Most modules are standalone and imported in `InitGui.py` to register commands.
