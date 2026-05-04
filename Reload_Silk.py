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
