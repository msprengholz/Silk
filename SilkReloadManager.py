#    This file is part of Silk
#    (c) 2025
#
#    NURBS Surface modeling tools focused on low degree and seam continuity (FreeCAD Workbench)
#
#    Simple hot reload manager - reloads modules without touching GUI commands

import sys
from importlib import reload
import traceback

import FreeCAD
from FreeCAD import Gui


# =============================================================================
# Simple Reload Manager - Reload modules in-place
# =============================================================================

class SimpleSilkReloadManager:
    """Simple reload manager that only reloads module code, not GUI registrations."""

    def __init__(self):
        pass

    def reload_all(self):
        """Execute reload of core modules only."""
        FreeCAD.Console.PrintMessage("\n" + "="*60 + "\n")
        FreeCAD.Console.PrintMessage("Silk: Starting hot reload (modules only)...\n")
        FreeCAD.Console.PrintMessage("="*60 + "\n")

        # Reload order: dependencies first, then dependents
        RELOAD_ORDER = [
            'ArachNURBS',
            'ControlPoly4',
            'ControlPoly4_segment',
            'ControlPoly6',
            'CubicCurve_4',
            'CubicCurve_6',
            'Point_onCurve',
            'ControlGrid44',
            'ControlGrid44_Rotate',
            'ControlGrid44_flow',
            'ControlGrid44_EdgeSegment',
            'ControlGrid44_2EdgeSegments',
            'ControlGrid66',
            'ControlGrid64',
            'ControlGrid64_normal',
            'ControlGrid64_2Grid44',
            'ControlGrid64_3_1Grid44',
            'ControlGrid64_Surf44',
            'ControlGrid66_4Sub',
            'ControlGridNStar66',
            'CubicSurface_44',
            'CubicSurface_64',
            'CubicSurface_66',
            'CubicNStarSurface_NStar66',
            'StarTrim_CubicNStar',
            'SubGrid33_2Grid64',
            'SubGrid63_2Surf64',
            'SilkPose',
            'SilkWorkflow',
        ]

        succeeded = []
        failed = []

        FreeCAD.Console.PrintMessage("Silk: Reloading modules...\n")

        for module_name in RELOAD_ORDER:
            if module_name in sys.modules:
                try:
                    module = sys.modules[module_name]
                    reload(module)
                    succeeded.append(module_name)
                    FreeCAD.Console.PrintMessage(f"  ✓ {module_name}\n")
                except Exception as e:
                    failed.append((module_name, e))
                    FreeCAD.Console.PrintError(f"  ✗ {module_name}: {e}\n")
            else:
                FreeCAD.Console.PrintWarning(f"  ? {module_name} (not loaded yet)\n")

        # Summary
        FreeCAD.Console.PrintMessage("="*60 + "\n")
        FreeCAD.Console.PrintMessage(f"Silk: Reload complete!\n")
        FreeCAD.Console.PrintMessage(f"  Succeeded: {len(succeeded)} modules\n")
        if failed:
            FreeCAD.Console.PrintError(f"  Failed: {len(failed)} modules\n")
        FreeCAD.Console.PrintMessage("="*60 + "\n\n")
        FreeCAD.Console.PrintMessage(
            "NOTE: Changes to command classes (Activated, GetResources)\n"
            "       require switching workbenches to take effect.\n"
            "       Changes to ArachNURBS and other functions work immediately.\n"
        )


def reload_for_testing():
    """
    Entry point for external test scripts.

    Usage in test file:
        from SilkReloadManager import reload_for_testing
        reload_for_testing()

    Returns:
        SimpleSilkReloadManager instance for inspection
    """
    manager = SimpleSilkReloadManager()
    manager.reload_all()
    return manager
