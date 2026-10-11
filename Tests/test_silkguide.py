"""
SilkGuide headless core (ticket #47): stateless hint query + container.

compute_guide_state(doc) is PURE -- "what's next" is derived from the
document on every call (no Stage enum, no stored stage counter), so the
guide scales with the document instead of replaying a linear script.
WorkflowGuide is a state SINK that mirrors the last derived state into
serializable properties.

Pinned hint semantics (all four asserted verbatim below):
  no edges                 -> "select sketches and create edges ..."
  edges, nothing blendable -> "create patches from 3-4 edges ..."
  a blendable seam exists  -> "select a blendable seam to blend"
  none left + a blend      -> "chain complete (N edges, M patches, K blends)"

Documented decisions pinned by tests here:
  * a document with blends but a FRESH unblended seam is NOT complete
    (the blend hint outranks the complete hint);
  * a BLOCKED (non-manifold) seam does NOT prevent `complete`: it is not
    blendable, so it is not outstanding blend work, and no action exists
    for it until the deferred corner fill lands;
  * the seam pass-through equals seam_inventory(doc) entry-for-entry;
  * the container round-trips through save/reload.

Fixtures are imported from Tests/test_seam_resolver.py (#45 precedent);
no shared test module was refactored.
"""

import FreeCAD

from Tests.test_seam_resolver import (
    _Capture, _square_patch, _patch_sharing, _stray_edge,
)

from SilkGuide import (
    compute_guide_state, create_guide, HINT_CREATE_EDGE,
    HINT_CREATE_PATCH, HINT_BLEND, HINT_COMPLETE,
)


def _chain_of_three(doc):
    """A -> B -> C: three square patches, each linked to the next by ONE
    shared Edge (2 blendable seams, 10 edges, 3 patches). Built through
    the ops layer only (create_edge / create_patch)."""
    from SilkWorkflowOps import create_blend_by_edge

    a = _square_patch(doc, "A")
    b = _patch_sharing(doc, a.Edges[0], "B")
    c = _patch_sharing(doc, b.Edges[1], "C")
    return a, b, c, [a.Edges[0], b.Edges[1]], create_blend_by_edge


def test_guide_state_empty_document(doc):
    """Empty document -> the create-edges hint, zero counts, no seams,
    complete=False."""
    errors, checks = [], []
    state = compute_guide_state(doc)

    if state["hint"] != HINT_CREATE_EDGE:
        errors.append("empty doc hint is %r, want %r"
                      % (state["hint"], HINT_CREATE_EDGE))
    checks.append("hint: %r" % state["hint"])
    if state["counts"] != {"edges": 0, "patches": 0, "blends": 0}:
        errors.append("empty doc counts are %r" % (state["counts"],))
    checks.append("counts: %r" % (state["counts"],))
    if state["seams"]:
        errors.append("empty doc reports %d seam(s)" % len(state["seams"]))
    if state["complete"]:
        errors.append("empty doc reports complete=True")
    if state["seam_counts"]["total"] != 0:
        errors.append("empty doc seam_counts total is %r"
                      % state["seam_counts"]["total"])
    checks.append("complete=%s seam_counts=%r"
                  % (state["complete"], state["seam_counts"]))
    return {"pass": not errors, "errors": errors, "checks": checks}


def test_guide_state_edges_only(doc):
    """Edges but no patches (and a stray unreferenced edge, which is not
    a seam) -> the create-patches hint; counts count the stray edge."""
    errors, checks = [], []
    from Tests.test_seam_resolver import _square_edges

    edges = _square_edges(doc, "Solo")
    _stray_edge(doc, "Stray")

    state = compute_guide_state(doc)
    if state["hint"] != HINT_CREATE_PATCH:
        errors.append("edges-only hint is %r, want %r"
                      % (state["hint"], HINT_CREATE_PATCH))
    checks.append("hint: %r (%d edges, %d patches)"
                  % (state["hint"], state["counts"]["edges"],
                     state["counts"]["patches"]))
    if state["counts"] != {"edges": 5, "patches": 0, "blends": 0}:
        errors.append("edges-only counts are %r, want 5 edges (4 + stray)"
                      % (state["counts"],))
    if state["seams"]:
        errors.append("an unreferenced edge produced %d seam entr(y/ies)"
                      % len(state["seams"]))
    checks.append("%d edges counted, %d seams (0/1-patch edges are not "
                  "seams)" % (state["counts"]["edges"], len(state["seams"])))
    if state["complete"]:
        errors.append("edges-only reports complete=True")
    checks.append("complete=%s" % state["complete"])
    return {"pass": not errors, "errors": errors, "checks": checks}


def test_guide_state_single_patch_no_seam(doc):
    """One patch, four edges, no seam: < 2 patches and nothing blendable
    -> the create-patches hint (the < 2 patches half of case 2)."""
    errors, checks = [], []
    _square_patch(doc, "A")
    state = compute_guide_state(doc)
    if state["hint"] != HINT_CREATE_PATCH:
        errors.append("single-patch hint is %r, want %r"
                      % (state["hint"], HINT_CREATE_PATCH))
    checks.append("hint: %r" % state["hint"])
    if state["seam_counts"]["blendable"]:
        errors.append("a lone patch produced blendable seams")
    checks.append("counts=%r seams=%r" % (state["counts"],
                                          state["seam_counts"]))
    return {"pass": not errors, "errors": errors, "checks": checks}


def test_guide_state_blendable_seam(doc):
    """Two patches sharing one edge -> the blend hint, one blendable
    seam, complete=False."""
    errors, checks = [], []
    a = _square_patch(doc, "A")
    b = _patch_sharing(doc, a.Edges[0], "B")

    state = compute_guide_state(doc)
    if state["hint"] != HINT_BLEND:
        errors.append("blendable-seam hint is %r, want %r"
                      % (state["hint"], HINT_BLEND))
    checks.append("hint: %r" % state["hint"])
    if state["seam_counts"] != {"total": 1, "blendable": 1, "blended": 0,
                                "blocked": 0}:
        errors.append("seam_counts is %r, want one blendable seam"
                      % (state["seam_counts"],))
    checks.append("seam_counts: %r" % (state["seam_counts"],))
    if state["complete"]:
        errors.append("a document with a blendable seam reports complete=True")
    if state["counts"] != {"edges": 7, "patches": 2, "blends": 0}:
        errors.append("counts are %r, want 7 edges / 2 patches / 0 blends"
                      % (state["counts"],))
    checks.append("counts: %r" % (state["counts"],))
    return {"pass": not errors, "errors": errors, "checks": checks}


def test_guide_state_chain_complete(doc):
    """Blend the one seam -> no blendable seam left and a blend exists ->
    the complete hint with the real counts, complete=True."""
    errors, checks = [], []
    import SilkWorkflowOps as ops

    a = _square_patch(doc, "A")
    _patch_sharing(doc, a.Edges[0], "B")

    with _Capture() as cap:
        blend = ops.create_blend_by_edge(a.Edges[0], name="BlendSeam")
    errors += ["console error: %s" % e for e in cap.errors]
    if blend is None:
        errors.append("by-edge blend creation failed on the fixture")
        return {"pass": False, "errors": errors, "checks": checks}

    state = compute_guide_state(doc)
    want = HINT_COMPLETE % (state["counts"]["edges"],
                           state["counts"]["patches"],
                           state["counts"]["blends"])
    if state["hint"] != want:
        errors.append("complete hint is %r, want %r"
                      % (state["hint"], want))
    checks.append("hint: %r" % state["hint"])
    if not state["complete"]:
        errors.append("fully blended document reports complete=False")
    if state["seam_counts"] != {"total": 1, "blendable": 0, "blended": 1,
                                "blocked": 0}:
        errors.append("seam_counts after blending is %r"
                      % (state["seam_counts"],))
    checks.append("complete=%s seam_counts=%r"
                  % (state["complete"], state["seam_counts"]))
    return {"pass": not errors, "errors": errors, "checks": checks}


def test_guide_state_scales_to_many_patches(doc):
    """The 'scales' claim: a 3-patch chain with two seams -- counts are
    fresh on every call (never stale, never double counted), the blend
    hint survives while ANY seam is unblended, and only the second blend
    completes the chain."""
    errors, checks = [], []
    a, b, c, seams, create_by_edge = _chain_of_three(doc)

    state = compute_guide_state(doc)
    if state["counts"] != {"edges": 10, "patches": 3, "blends": 0}:
        errors.append("chain counts are %r, want 10 edges / 3 patches / 0 "
                      "blends" % (state["counts"],))
    checks.append("before: counts=%r" % (state["counts"],))
    if state["seam_counts"] != {"total": 2, "blendable": 2, "blended": 0,
                                "blocked": 0}:
        errors.append("chain seam_counts is %r, want 2 blendable seams"
                      % (state["seam_counts"],))
    if state["hint"] != HINT_BLEND:
        errors.append("3-patch chain hint is %r, want the blend hint"
                      % state["hint"])
    checks.append("before: hint=%r seams=%r" % (state["hint"],
                                                state["seam_counts"]))

    with _Capture() as cap:
        blend = create_by_edge(seams[0], name="BlendAB")
    errors += ["console error: %s" % e for e in cap.errors]
    if blend is None:
        errors.append("first by-edge blend creation failed")
        return {"pass": False, "errors": errors, "checks": checks}

    # A blend exists but one seam is still open -> NOT complete, and the
    # blend hint must not be overtaken by the complete hint.
    state = compute_guide_state(doc)
    if state["complete"]:
        errors.append("document with blends AND a fresh unblended seam "
                      "reports complete=True")
    if state["hint"] != HINT_BLEND:
        errors.append("hint after the first blend is %r, want the blend hint"
                      % state["hint"])
    if state["counts"] != {"edges": 10, "patches": 3, "blends": 1}:
        errors.append("counts after first blend are %r, want 10/3/1"
                      % (state["counts"],))
    if state["seam_counts"] != {"total": 2, "blendable": 1, "blended": 1,
                                "blocked": 0}:
        errors.append("seam_counts after first blend is %r, want 1/1/0"
                      % (state["seam_counts"],))
    checks.append("after blend 1: hint=%r complete=%s counts=%r seams=%r"
                  % (state["hint"], state["complete"], state["counts"],
                     state["seam_counts"]))

    with _Capture() as cap:
        blend2 = create_by_edge(seams[1], name="BlendBC")
    errors += ["console error: %s" % e for e in cap.errors]
    if blend2 is None or blend2 is blend:
        errors.append("second by-edge blend failed / returned the first "
                      "blend (%r)" % (blend2,))
        return {"pass": False, "errors": errors, "checks": checks}

    state = compute_guide_state(doc)
    want = HINT_COMPLETE % (10, 3, 2)
    if state["hint"] != want:
        errors.append("completed chain hint is %r, want %r"
                      % (state["hint"], want))
    if not state["complete"]:
        errors.append("fully blended 3-patch chain reports complete=False")
    if state["counts"] != {"edges": 10, "patches": 3, "blends": 2}:
        errors.append("final counts are %r, want 10/3/2" % (state["counts"],))
    if state["seam_counts"] != {"total": 2, "blendable": 0, "blended": 2,
                                "blocked": 0}:
        errors.append("final seam_counts is %r" % (state["seam_counts"],))
    checks.append("after blend 2: hint=%r complete=%s counts=%r seams=%r"
                  % (state["hint"], state["complete"], state["counts"],
                     state["seam_counts"]))

    # Statelessness: the same document yields the same answer twice, and
    # adding one more patch is picked up immediately.
    again = compute_guide_state(doc)
    if again["hint"] != state["hint"] or again["counts"] != state["counts"]:
        errors.append("compute_guide_state is not deterministic on an "
                      "unchanged document")
    _patch_sharing(doc, c.Edges[1], "D")
    grown = compute_guide_state(doc)
    if grown["counts"]["patches"] != 4:
        errors.append("adding a 4th patch did not update the counts (%r)"
                      % (grown["counts"],))
    if grown["hint"] != HINT_BLEND:
        errors.append("after adding a 4th patch the hint is %r, want the "
                      "blend hint" % grown["hint"])
    checks.append("re-query after adding a 4th patch: hint=%r counts=%r "
                  "seams=%r" % (grown["hint"], grown["counts"],
                                grown["seam_counts"]))
    return {"pass": not errors, "errors": errors, "checks": checks}


def test_guide_state_blocked_seam_does_not_block_completion(doc):
    """DECISION (pinned): a BLOCKED (non-manifold) seam is not outstanding
    blend work, so it does not prevent `complete`.

    Fixture: patch A shares its bottom edge with B AND C (3 patches ->
    blocked), and shares its right edge with D (a normal blendable seam).
    After blending the A/D seam the only seam left is blocked, one blend
    exists -> complete=True, and the blocked seam stays visible in the
    pass-through and the seam_counts roll-up."""
    errors, checks = [], []
    import SilkWorkflowOps as ops

    a = _square_patch(doc, "A")
    _patch_sharing(doc, a.Edges[0], "B")
    _patch_sharing(doc, a.Edges[0], "C")   # -> blocked on a.Edges[0]
    _patch_sharing(doc, a.Edges[1], "D")   # -> blendable on a.Edges[1]

    state = compute_guide_state(doc)
    if state["seam_counts"] != {"total": 2, "blendable": 1, "blended": 0,
                                "blocked": 1}:
        errors.append("pre-blend seam_counts is %r, want 1 blendable + 1 "
                      "blocked" % (state["seam_counts"],))
    if state["hint"] != HINT_BLEND:
        errors.append("with a blendable seam present the hint is %r, want "
                      "the blend hint" % state["hint"])
    checks.append("pre-blend: %r complete=%s" % (state["seam_counts"],
                                                  state["complete"]))

    with _Capture() as cap:
        blend = ops.create_blend_by_edge(a.Edges[1], name="BlendAD")
    errors += ["console error: %s" % e for e in cap.errors]
    if blend is None:
        errors.append("by-edge blend creation failed")
        return {"pass": False, "errors": errors, "checks": checks}

    state = compute_guide_state(doc)
    if not state["complete"]:
        errors.append("a document whose only remaining seam is BLOCKED "
                      "reports complete=False -- blocked seams must not "
                      "prevent completion (documented decision)")
    if state["hint"] != HINT_COMPLETE % (state["counts"]["edges"],
                                         state["counts"]["patches"],
                                         state["counts"]["blends"]):
        errors.append("blocked-only hint is %r, want the complete hint"
                      % state["hint"])
    if state["seam_counts"]["blocked"] != 1:
        errors.append("the blocked seam disappeared from the roll-up: %r"
                      % (state["seam_counts"],))
    blocked = [e for e in state["seams"] if e["status"] == "blocked"]
    if len(blocked) != 1 or blocked[0]["edge"] is not a.Edges[0]:
        errors.append("the blocked seam is not passed through: %r"
                      % [e["status"] for e in state["seams"]])
    checks.append("blocked-only: hint=%r complete=%s seams=%r (the blocked "
                  "seam stays listed)"
                  % (state["hint"], state["complete"], state["seam_counts"]))

    # ...and a blendable seam ALWAYS outranks completion, blocked or not.
    patch_b = doc.getObject("B")
    _patch_sharing(doc, patch_b.Edges[1], "E")
    state = compute_guide_state(doc)
    if state["complete"] or state["hint"] != HINT_BLEND:
        errors.append("a blocked seam plus a new blendable seam reports "
                      "complete=%r hint=%r -- a blendable seam must always "
                      "win" % (state["complete"], state["hint"]))
    checks.append("blocked + fresh blendable seam: hint=%r complete=%s"
                  % (state["hint"], state["complete"]))
    return {"pass": not errors, "errors": errors, "checks": checks}


def test_guide_state_seams_match_seam_inventory(doc):
    """The 'seams' entry is the #44 seam_inventory list passed through
    UNCHANGED: same length, same order, same status/blend and the same
    object identities -- in a document holding blendable, blended and
    blocked seams at once."""
    errors, checks = [], []
    import SilkWorkflowOps as ops
    from SilkWorkflowOps import seam_inventory

    a = _square_patch(doc, "A")
    _patch_sharing(doc, a.Edges[0], "B")
    _patch_sharing(doc, a.Edges[0], "C")   # blocked (3 patches)
    _patch_sharing(doc, a.Edges[1], "D")   # blendable, then blended below
    _patch_sharing(doc, a.Edges[2], "F")   # left blendable
    with _Capture() as cap:
        ops.create_blend_by_edge(a.Edges[1], name="BlendAD")
    errors += ["console error: %s" % e for e in cap.errors]

    state = compute_guide_state(doc)
    inv = seam_inventory(doc)
    if len(state["seams"]) != len(inv):
        errors.append("guide reports %d seams, seam_inventory reports %d"
                      % (len(state["seams"]), len(inv)))
    else:
        for i, (got, want) in enumerate(zip(state["seams"], inv)):
            if got is want:
                continue
            if (got["edge"] is want["edge"]
                    and got["patch_a"] is want["patch_a"]
                    and got["patch_b"] is want["patch_b"]
                    and got["status"] == want["status"]
                    and got["blend"] is want["blend"]):
                continue
            errors.append("seam %d differs from seam_inventory: %r vs %r"
                          % (i, {k: getattr(v, "Name", v)
                                 for k, v in got.items()},
                             {k: getattr(v, "Name", v)
                              for k, v in want.items()}))
    statuses = [e["status"] for e in state["seams"]]
    if sorted(statuses) != ["blendable", "blended", "blocked"]:
        errors.append("expected one blendable / blended / blocked seam, got %r"
                      % statuses)
    checks.append("seam pass-through identical to seam_inventory (%d seams: "
                  "%s)" % (len(state["seams"]), statuses))
    return {"pass": not errors, "errors": errors, "checks": checks}


def test_guide_container_execute_populates_properties(doc):
    """create_guide -> execute() mirrors compute_guide_state into the
    container's properties.

    Also pins the SINK contract: a plain `doc.recompute()` must NOT
    refresh the container (nothing in SilkEdge/SilkPatch/SilkBlend/
    SilkWorkflowOps knows it exists -- settled #16 Q16b), and an explicit
    recompute of the container re-derives from the document."""
    errors, checks = [], []
    a = _square_patch(doc, "A")
    _patch_sharing(doc, a.Edges[0], "B")

    guide = create_guide(name="Guide")
    if getattr(guide, "object_type", None) != "WorkflowGuide":
        errors.append("container object_type is %r, want 'WorkflowGuide'"
                      % getattr(guide, "object_type", None))
    checks.append("container: %s (%s)"
                  % (guide.Name, getattr(guide, "object_type", None)))

    state = compute_guide_state(doc)
    if guide.NextStepHint != state["hint"]:
        errors.append("container NextStepHint %r != compute_guide_state %r"
                      % (guide.NextStepHint, state["hint"]))
    checks.append("NextStepHint: %r" % guide.NextStepHint)
    if (guide.EdgeCount, guide.PatchCount, guide.BlendCount) != (
            state["counts"]["edges"], state["counts"]["patches"],
            state["counts"]["blends"]):
        errors.append("container counts (%d/%d/%d) != state %r"
                      % (guide.EdgeCount, guide.PatchCount, guide.BlendCount,
                         state["counts"]))
    checks.append("counts: %d edges / %d patches / %d blends"
                  % (guide.EdgeCount, guide.PatchCount, guide.BlendCount))
    if (guide.SeamCount, guide.BlendableSeams, guide.BlendedSeams,
            guide.BlockedSeams) != (
            state["seam_counts"]["total"], state["seam_counts"]["blendable"],
            state["seam_counts"]["blended"],
            state["seam_counts"]["blocked"]):
        errors.append("container seam counts (%d/%d/%d/%d) != state %r"
                      % (guide.SeamCount, guide.BlendableSeams,
                         guide.BlendedSeams, guide.BlockedSeams,
                         state["seam_counts"]))
    checks.append("seams: %d total / %d blendable / %d blended / %d blocked"
                  % (guide.SeamCount, guide.BlendableSeams,
                     guide.BlendedSeams, guide.BlockedSeams))
    if bool(guide.Complete) != bool(state["complete"]):
        errors.append("container Complete=%r != state %r"
                      % (guide.Complete, state["complete"]))
    checks.append("Complete: %r" % guide.Complete)

    # The container is non-geometric: it must never add geometry.
    if len(guide.Shape.Faces) or len(guide.Shape.Edges):
        errors.append("container has geometry (%d faces, %d edges) -- it "
                      "must stay non-geometric"
                      % (len(guide.Shape.Faces), len(guide.Shape.Edges)))
    checks.append("container shape is empty (non-geometric)")

    # Blend the seam. The container is a SINK, not an owner: nothing in
    # the production modules notifies it, so `doc.recompute()` alone
    # leaves the stored state untouched -- refreshing it is the panel's
    # job (#48), and that is the settled #16 Q16b design.
    import SilkWorkflowOps as ops
    with _Capture() as cap:
        ops.create_blend_by_edge(a.Edges[0], name="BlendSeam")
    errors += ["console error: %s" % e for e in cap.errors]
    doc.recompute()
    if guide.NextStepHint != state["hint"]:
        errors.append("the container refreshed itself without being asked "
                      "(hint changed to %r) -- it must stay a passive sink"
                      % guide.NextStepHint)
    checks.append("plain doc.recompute() does NOT refresh the sink "
                  "(no production-module coupling)")

    # Refreshing the sink re-derives the state from the document.
    guide.recompute()
    doc.recompute()
    state2 = compute_guide_state(doc)
    if guide.NextStepHint != state2["hint"]:
        errors.append("after blending, container NextStepHint %r != state %r"
                      % (guide.NextStepHint, state2["hint"]))
    if not guide.Complete or guide.BlendedSeams != 1:
        errors.append("after blending, container reports Complete=%r "
                      "BlendedSeams=%d, want True/1"
                      % (guide.Complete, guide.BlendedSeams))
    checks.append("after blending + explicit refresh: hint=%r Complete=%r"
                  % (guide.NextStepHint, guide.Complete))
    return {"pass": not errors, "errors": errors, "checks": checks}


def test_guide_container_serialization_round_trip(doc):
    """Save / close / reopen: the stored state properties survive the
    round trip (not merely re-derivable) -- the container's onDocument
    Restored deliberately does not re-derive."""
    import os
    errors, checks = [], []
    import SilkWorkflowOps as ops

    a = _square_patch(doc, "A")
    _patch_sharing(doc, a.Edges[0], "B")
    with _Capture() as cap:
        ops.create_blend_by_edge(a.Edges[0], name="BlendSeam")
    errors += ["console error: %s" % e for e in cap.errors]
    guide = create_guide(name="Guide")

    before = (guide.NextStepHint, guide.Complete, guide.EdgeCount,
              guide.PatchCount, guide.BlendCount, guide.SeamCount,
              guide.BlendableSeams, guide.BlendedSeams, guide.BlockedSeams)

    save_path = "/tmp/_test_silkguide_serialize.FCStd"
    doc.saveAs(save_path)
    FreeCAD.closeDocument(doc.Name)

    doc2 = FreeCAD.openDocument(save_path)
    try:
        g2 = [o for o in doc2.Objects
              if getattr(o, "object_type", None) == "WorkflowGuide"]
        if len(g2) != 1:
            errors.append("reload: expected exactly one WorkflowGuide "
                          "container, got %d" % len(g2))
            return {"pass": False, "errors": errors, "checks": checks}
        g2 = g2[0]
        after = (g2.NextStepHint, g2.Complete, g2.EdgeCount, g2.PatchCount,
                 g2.BlendCount, g2.SeamCount, g2.BlendableSeams,
                 g2.BlendedSeams, g2.BlockedSeams)
        if before != after:
            errors.append("reload: state changed %r -> %r" % (before, after))
        checks.append("round trip: hint=%r complete=%s counts=%d/%d/%d "
                      "seams=%d/%d/%d/%d" % after)
        # And the sink still agrees with a fresh query on the reloaded doc.
        state2 = compute_guide_state(doc2)
        if g2.NextStepHint != state2["hint"]:
            errors.append("reload: stored hint %r != fresh query %r"
                          % (g2.NextStepHint, state2["hint"]))
        checks.append("stored hint agrees with a fresh query on reload")
    finally:
        os.remove(save_path)
        FreeCAD.closeDocument(doc2.Name)
    return {"pass": not errors, "errors": errors, "checks": checks}


ALL_TESTS = [
    test_guide_state_empty_document,
    test_guide_state_edges_only,
    test_guide_state_single_patch_no_seam,
    test_guide_state_blendable_seam,
    test_guide_state_chain_complete,
    test_guide_state_scales_to_many_patches,
    test_guide_state_blocked_seam_does_not_block_completion,
    test_guide_state_seams_match_seam_inventory,
    test_guide_container_execute_populates_properties,
    test_guide_container_serialization_round_trip,
]
