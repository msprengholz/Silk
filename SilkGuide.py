#    This file is part of Silk
#    (c) 2025
#
#    NURBS Surface modeling tools focused on low degree and seam continuity (FreeCAD Workbench)
#
#    Guide -- the headless core of the workflow guide (ticket #47).
#
#    TWO parts, both GUI-free (the `Silk_Guide` command + task panel are
#    ticket #48 and consume exactly what lives here):
#
#      1. compute_guide_state(doc) -- a STATELESS pure query. "What is the
#         next action?" is derived from the document on every call; there
#         is deliberately NO Stage enum / no stored stage counter (the
#         retired SilkGuide_prototype.py's `Stage` property is not revived).
#         The user may jump around freely, and the query is a handful of
#         link-list scans (seam_inventory + object_type counts), so it
#         costs the same for 4 patches as for 40.
#
#      2. WorkflowGuide -- a non-geometric Part::FeaturePython container
#         that HOLDS the last computed state so tests and the saved
#         document can inspect it. It is a state SINK, never an owner:
#         nothing in SilkEdge / SilkPatch / SilkBlend / SilkWorkflowOps
#         knows it exists and nothing notifies it (settled #16 Q16b --
#         panel-side refresh, zero wizard coupling in the production
#         modules). Re-deriving on every execute() IS the design.
#
#    The seam list is deliberately NOT stored as object links on the
#    container: seam_inventory (#44) is a cheap pure query, so a stored
#    link list could only ever go stale. The panel re-queries.

import FreeCAD
import Part

from SilkWorkflowOps import seam_inventory
from SilkBlend import PATCH_TYPES, BLEND_TYPES

import os, Silk_dummy
path_Silk = os.path.dirname(Silk_dummy.__file__)
path_Silk_icons = os.path.join(path_Silk, "Resources", "Icons")
iconPath = path_Silk_icons + "/Silk.svg"

ICON = "Resources/Icons/Silk.svg"

# ---- the pinned hints (the panel's copy comes from here, never re-worded) --
HINT_CREATE_EDGE = "select sketches and create edges (Silk_CreateEdge)"
HINT_CREATE_PATCH = "create patches from 3-4 edges (Silk_CreatePatch)"
HINT_BLEND = "select a blendable seam to blend"
HINT_COMPLETE = "chain complete (%d edges, %d patches, %d blends)"


def _count(doc, types):
    """Number of document objects whose `object_type` is in `types`."""
    return sum(1 for o in doc.Objects
               if getattr(o, "object_type", None) in types)


def compute_guide_state(doc=None):
    """Derive the workflow state of `doc` from scratch. PURE.

    Stateless on purpose: nothing is read from a previously stored stage,
    so calling this twice without touching the document returns the same
    answer, and calling it after any edit returns the CURRENT answer.
    `doc` defaults to the active document.

    Returns a plain dict (data + document object references, no logic)::

      {
        "hint":       "<one-line next action>",   # see HINT_* above
        "counts":     {"edges": N, "patches": N, "blends": N},
        "seams":      [ ... #44 seam_inventory entries, unchanged ... ],
        "seam_counts":{"total": N, "blendable": N, "blended": N,
                       "blocked": N},              # derived from "seams"
        "complete":   bool,
      }

    "seams" is the #44 `seam_inventory(doc)` list passed through
    UNCHANGED (same order, same entry dicts, the same object references)
    so the panel renders exactly what the resolver believes -- an edge
    referenced by fewer than two patches is not a seam and therefore has
    no entry at all. "seam_counts" is a convenience roll-up so the panel
    can show "N of M seams blended" without re-walking the list; it
    carries no information the entries do not.

    Hint precedence (most useful next action first -- the pinned four):
      1. no Edges at all                       -> HINT_CREATE_EDGE
      2. at least one `blendable` seam        -> HINT_BLEND
      3. no blendable seam left AND >= 1 blend-> "chain complete (...)"
                                                and complete=True
      4. otherwise                            -> HINT_CREATE_PATCH

    Consequence of that ordering, stated so it is not a surprise: a
    document that already holds blends but has just gained a fresh
    unblended seam reports HINT_BLEND and complete=False (case 2 wins
    over case 3) -- "complete" never hides outstanding work. Case 4 is
    the catch-all: it covers "fewer than two Patches and nothing
    blendable" (the pinned wording) and also the rarer "two or more
    Patches that share no Edge yet", where creating further patches is
    still the only action that can ever produce a seam.

    `complete` means: "no blendable seam is left and at least one blend
    exists". A BLOCKED seam (three or more patches referencing one edge
    -- non-manifold, waiting on the deferred corner fill) does NOT
    prevent completion: it is not blendable, so it is not outstanding
    work, and refusing to call the chain complete would leave the panel
    hinting at an action that has no implementation. Blocked seams stay
    visible through the "seams" pass-through and the seam_counts roll-up,
    so a panel can still surface them.
    """
    doc = doc if doc is not None else FreeCAD.ActiveDocument
    counts = {
        "edges": _count(doc, ("Edge",)),
        "patches": _count(doc, PATCH_TYPES),
        "blends": _count(doc, BLEND_TYPES),
    }
    seams = seam_inventory(doc)
    by_status = {"blendable": 0, "blended": 0, "blocked": 0}
    for entry in seams:
        by_status[entry["status"]] = by_status.get(entry["status"], 0) + 1

    complete = False
    if counts["edges"] == 0:
        hint = HINT_CREATE_EDGE
    elif by_status["blendable"]:
        hint = HINT_BLEND
    elif counts["blends"] >= 1:
        hint = HINT_COMPLETE % (counts["edges"], counts["patches"],
                                counts["blends"])
        complete = True
    else:
        hint = HINT_CREATE_PATCH

    return {
        "hint": hint,
        "counts": counts,
        "seams": seams,
        "seam_counts": dict(total=len(seams), **by_status),
        "complete": complete,
    }


class WorkflowGuide:
    """Non-geometric container holding the last computed guide state.

    A state SINK for `compute_guide_state`: `execute()` re-derives the
    state from the document and writes it into plain (serializable)
    properties. Nothing notifies it and nothing reads it back as truth --
    the panel re-queries `compute_guide_state` directly; these properties
    exist so tests, the property editor and a reloaded document can read
    the last derived state without re-running anything.

    Because it holds no links of its own, it is NOT a second source of
    truth and never can go stale in a harmful way.
    """

    def __init__(self, obj):
        obj.addProperty("App::PropertyString", "NextStepHint", "C1 - Workflow",
                        "the derived next action").NextStepHint = ""
        obj.addProperty("App::PropertyBool", "Complete", "C1 - Workflow",
                        "no blendable seam left and at least one blend "
                        "exists").Complete = False
        obj.addProperty("App::PropertyInteger", "EdgeCount", "C2 - Counts",
                        "edges in the document").EdgeCount = 0
        obj.addProperty("App::PropertyInteger", "PatchCount", "C2 - Counts",
                        "patches in the document").PatchCount = 0
        obj.addProperty("App::PropertyInteger", "BlendCount", "C2 - Counts",
                        "blends in the document").BlendCount = 0
        obj.addProperty("App::PropertyInteger", "SeamCount", "C2 - Counts",
                        "seams in the document").SeamCount = 0
        obj.addProperty("App::PropertyInteger", "BlendableSeams",
                        "C2 - Counts", "seams still waiting for a blend"
                        ).BlendableSeams = 0
        obj.addProperty("App::PropertyInteger", "BlendedSeams", "C2 - Counts",
                        "seams covered by a blend").BlendedSeams = 0
        obj.addProperty("App::PropertyInteger", "BlockedSeams", "C2 - Counts",
                        "non-manifold seams (3+ patches, corner fill "
                        "deferred)").BlockedSeams = 0
        obj.addProperty("App::PropertyString", "object_type", "C3 - Identifiers",
                        "workbench class").object_type = "WorkflowGuide"
        obj.setEditorMode("object_type", 1)
        obj.addProperty("App::PropertyString", "object_version",
                        "C3 - Identifiers", "class version").object_version = "0.01"
        obj.setEditorMode("object_version", 1)
        obj.addProperty("App::PropertyString", "internalName",
                        "C3 - Identifiers",
                        "permanent internal FreeCAD name").internalName = obj.Name
        obj.setEditorMode("internalName", 1)
        obj.Proxy = self
        self.execute(obj)

    def onDocumentRestored(self, obj):
        # Deliberately NO re-derivation on restore: the stored state is
        # what the document was saved with, and a test can prove it
        # round-tripped instead of proving a recompute agrees. The next
        # recompute re-derives anyway.
        return

    def execute(self, fp):
        """Re-derive the state from the document and store it."""
        state = compute_guide_state(fp.Document or FreeCAD.ActiveDocument)
        counts = state["counts"]
        seams = state["seam_counts"]
        fp.NextStepHint = state["hint"]
        fp.Complete = bool(state["complete"])
        fp.EdgeCount = counts["edges"]
        fp.PatchCount = counts["patches"]
        fp.BlendCount = counts["blends"]
        fp.SeamCount = seams["total"]
        fp.BlendableSeams = seams["blendable"]
        fp.BlendedSeams = seams["blended"]
        fp.BlockedSeams = seams["blocked"]
        # non-geometric: keep a valid (empty) shape so the container never
        # renders anything and never goes invalid.
        fp.Shape = Part.Shape()

    def onChanged(self, fp, prop):
        # No-op on purpose: the container owns nothing, so no property of
        # its own warrants a recompute and nothing may couple back into
        # the production modules.
        return


class WorkflowGuideViewProvider:
    def __init__(self, vobj):
        vobj.Proxy = self

    def getIcon(self):
        return ICON

    def attach(self, vobj):
        self.ViewObject = vobj

    def updateData(self, obj, prop):
        return True

    def __getstate__(self):
        return None

    def __setstate__(self, state):
        return None


def create_guide(name="WorkflowGuide", doc=None):
    """Create the guide state container in `doc` (active document by
    default): addObject -> WorkflowGuide -> view provider -> recompute ->
    return the created object. The same shape as the ops layer's
    builders; it lives here because SilkWorkflowOps (#44) is frozen and
    #48 may equally call `WorkflowGuide(obj)` directly.
    """
    doc = doc if doc is not None else FreeCAD.ActiveDocument
    obj = doc.addObject("Part::FeaturePython", name)
    WorkflowGuide(obj)
    WorkflowGuideViewProvider(obj.ViewObject)
    doc.recompute()
    return obj
