#    This file is part of Silk
#    (c) 2025
#
#    NURBS Surface modeling tools focused on low degree and seam continuity (FreeCAD Workbench)
#
#    Guide -- the headless core of the workflow guide (ticket #47).
#
#    ONE part, GUI-free: compute_guide_state(doc), a STATELESS pure
#    query. "What is the next action?" is derived from the document on
#    every call; there is deliberately NO Stage enum / no stored stage
#    counter (the retired SilkGuide_prototype.py's `Stage` property is
#    not revived). The user may jump around freely, and the query is a
#    handful of link-list scans (seam_inventory + object_type counts),
#    so it costs the same for 4 patches as for 40.
#
#    #62 REMOVED the second half: the WorkflowGuide container that held
#    the last computed state. The panel computes live and publishes
#    nothing to the property editor, so the container could only ever
#    store a snapshot the panel never read back -- a second place to go
#    stale. compute_guide_state and its tests stay; the task panel
#    (SilkTaskPanel.py) re-queries on every refresh.
#
#    The seam list is passed through UNCHANGED from seam_inventory (#44),
#    a cheap pure query, so nothing here could go stale even if a caller
#    did hold on to it.

import FreeCAD

from SilkWorkflowOps import seam_inventory
from SilkBlend import PATCH_TYPES, BLEND_TYPES

# ---- the pinned hints (the panel's copy comes from here, never re-worded) --
HINT_CREATE_EDGE = "select sketches and create edges (Silk_CreateEdge)"
HINT_CREATE_PATCH = "create patches from 3-4 edges (Silk_CreatePatch)"
HINT_BLEND = "select a blendable seam to blend"
#    #73 DELETED a fourth constant, HINT_COMPLETE ("chain complete (N
#    edges, M patches, K blends)"). It was the only one of these that was
#    not an ACTION: it named a property of the document, announced a
#    terminal state, and so implied that every seam ought to be blended.
#    That is not true -- blending is the user's choice per seam, and a
#    corner box legitimately has seams they intend to leave alone -- so
#    the report asked for no notification at all. Case 3 therefore
#    returns the EMPTY hint and the panel hides its footer line. Nothing
#    replaced it: falling through to HINT_CREATE_PATCH would be a
#    different nag, not the absence of one. The `complete` FLAG survives
#    the string -- it is data, and "no blendable seam left" is a real
#    distinction the tests read.


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
                     #   or "" when there is nothing to ask for (#73)
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

    Hint precedence (most useful next action first -- the pinned three,
    plus the empty case):
      1. no Edges at all                       -> HINT_CREATE_EDGE
      2. at least one `blendable` seam        -> HINT_BLEND
      3. no blendable seam left AND >= 1 blend-> "" (nothing to ask for)
                                                and complete=True
      4. otherwise                            -> HINT_CREATE_PATCH

    Case 3 returns the EMPTY string, not a fourth pinned hint (#73). The
    footer used to announce "chain complete (N edges, M patches, K
    blends)" here, and that was the only one of the four that was not an
    ACTION: it named a property of the document and announced a terminal
    state, implying the chain is supposed to end there. It is not --
    blending is optional per seam, so a user who deliberately leaves a
    seam open is not "incomplete" and must not be told they are done.
    Hence no notification, and specifically NOT a fall-through to
    HINT_CREATE_PATCH either: the human asked for silence, not a
    different nag (a document of 3 patches and 2 blends needs no further
    patch). A caller rendering `hint` must treat "" as "show nothing" --
    an empty QLabel in a layout still occupies a line of height.

    Consequence of that ordering, stated so it is not a surprise: a
    document that already holds blends but has just gained a fresh
    unblended seam reports HINT_BLEND and complete=False (case 2 wins
    over case 3) -- "complete" never hides outstanding work. Case 4 is
    the catch-all: it covers "fewer than two Patches and nothing
    blendable" (the pinned wording) and also the rarer "two or more
    Patches that share no Edge yet", where creating further patches is
    still the only action that can ever produce a seam.

    `complete` means: "no blendable seam is left and at least one blend
    exists". #73 kept this flag and deleted only the string: the fact is
    data and the wording was a judgement call. A BLOCKED seam (three or
    more patches referencing one edge -- non-manifold, waiting on the
    deferred corner fill) does NOT prevent completion: it is not
    blendable, so it is not outstanding work, and refusing to call the
    chain complete would leave the panel hinting at an action that has
    no implementation. Blocked seams stay visible through the "seams"
    pass-through and the seam_counts roll-up, so a panel can still
    surface them.
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
        # #73: nothing left to ask for. The empty hint, NOT the pinned
        # "chain complete (...)" and NOT a fall-through to
        # HINT_CREATE_PATCH -- the user may never wish to blend every
        # seam, so a terminal state is not a thing to announce.
        hint = ""
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
