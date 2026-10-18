"""
SilkGuide headless core (ticket #47): the stateless hint query.

compute_guide_state(doc) is PURE -- "what's next" is derived from the
document on every call (no Stage enum, no stored stage counter), so the
guide scales with the document instead of replaying a linear script.

#62 removed the module's second half: the WorkflowGuide container that
mirrored the last derived state into serializable properties. The #62
task panel computes live and publishes nothing to the property editor,
so the container was a snapshot nothing ever read back. What survives
here is the query, and the tests that pin it.

Pinned hint semantics (all four asserted verbatim below):
  no edges                 -> "select sketches and create edges ..."
  edges, nothing blendable -> "create patches from 3-4 edges ..."
  a blendable seam exists  -> "select a blendable seam to blend"
  none left + a blend      -> "" (no hint at all -- see below)

#73 removed the fourth string, "chain complete (N edges, M patches, K
blends)". It was the only one of the four that was not an ACTION: it
announced a terminal state, which implies every seam ought to be blended.
It is not -- blending is optional per seam, so a user who deliberately
leaves a seam open should never be told they are "done". Case 3 now
returns an EMPTY hint and the panel hides the footer line when the hint
is empty. `complete` STAYS a flag on the returned dict: the hint went, the
fact stayed. The other three hints are untouched -- pinned wording, they
name an action, and they were not reported.

Documented decisions pinned by tests here:
  * a document with blends but a FRESH unblended seam is NOT complete
    (the blend hint outranks the empty hint);
  * a BLOCKED (non-manifold) seam does NOT prevent `complete`: it is not
    blendable, so it is not outstanding blend work, and no action exists
    for it until the deferred corner fill lands;
  * the seam pass-through equals seam_inventory(doc) entry-for-entry;
  * #62's removal is total: the module exposes no container, no
    create_guide, and nothing writes guide state into a document.

Fixtures are imported from Tests/test_seam_resolver.py (#45 precedent);
no shared test module was refactored.
"""

# --- manual tier ------------------------------------------------------
# This module's subject is an end-to-end rebuild / GUI drive /
# measurement sweep, so it is NOT in the default (fast) tier. Run it
# with `python3 Tests/run_all.py --manual` (or by name as a filter);
# Tests/test_manual_tier.py asserts it stays importable. See suite.py.
MANUAL = True

import FreeCAD

from Tests.test_seam_resolver import (
    _Capture, _square_patch, _patch_sharing, _stray_edge,
)

import SilkGuide
from SilkGuide import (
    compute_guide_state, HINT_CREATE_EDGE,
    HINT_CREATE_PATCH, HINT_BLEND,
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


def test_guide_state_no_document(doc):
    """No active document -> the same zero-count state as an empty
    document, no AttributeError.

    compute_guide_state() resolves doc=None to FreeCAD.ActiveDocument;
    when that is None the query must not walk doc.Objects. The stub
    replaces SilkGuide.FreeCAD (the module's own binding) so the
    no-document path is forced deterministically even though the test
    run itself has an active document."""
    errors, checks = [], []

    class _NoDocFreeCAD(object):
        ActiveDocument = None

    orig = SilkGuide.FreeCAD
    SilkGuide.FreeCAD = _NoDocFreeCAD
    try:
        state = compute_guide_state()
    finally:
        SilkGuide.FreeCAD = orig

    if state["hint"] != HINT_CREATE_EDGE:
        errors.append("no-document hint is %r, want %r"
                      % (state["hint"], HINT_CREATE_EDGE))
    if state["counts"] != {"edges": 0, "patches": 0, "blends": 0}:
        errors.append("no-document counts are %r" % (state["counts"],))
    if state["seams"]:
        errors.append("no-document reports %d seam(s)" % len(state["seams"]))
    if state["complete"]:
        errors.append("no-document reports complete=True")
    if state["seam_counts"] != {"total": 0, "blendable": 0, "blended": 0,
                                "blocked": 0}:
        errors.append("no-document seam_counts are %r"
                      % (state["seam_counts"],))
    checks.append("no active document -> zero-count state, no crash")
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
    NO hint at all (#73) and complete=True.

    The hint goes, the fact stays: `complete` is data and is asserted
    here, while the hint is the empty string the panel must render as no
    footer line. The old "chain complete (N edges, M patches, K blends)"
    is pinned dead -- it is the only one of the four that was not an
    action, and it told the user they were done when blending every seam
    is their choice, not the workflow's goal."""
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
    if state["hint"] != "":
        errors.append("a fully blended document still hints %r -- #73: the "
                      "chain-complete case announces a terminal state and "
                      "the user may never wish to blend every seam, so the "
                      "hint must be empty"
                      % (state["hint"],))
    checks.append("hint: %r (empty, #73)" % state["hint"])
    if not state["complete"]:
        errors.append("fully blended document reports complete=False")
    if state["seam_counts"] != {"total": 1, "blendable": 0, "blended": 1,
                                "blocked": 0}:
        errors.append("seam_counts after blending is %r"
                      % (state["seam_counts"],))
    # The word is gone from the module, not just from this fixture: no
    # constant, and no fallback nag behind the empty hint.
    if hasattr(SilkGuide, "HINT_COMPLETE"):
        errors.append("SilkGuide still exports HINT_COMPLETE=%r -- #73 "
                      "deleted it with the string"
                      % SilkGuide.HINT_COMPLETE)
    checks.append("HINT_COMPLETE is gone; the hint is the empty string")
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
    if state["hint"] != "":
        errors.append("completed chain hint is %r, want the empty hint "
                      "(#73)" % (state["hint"],))
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
    if state["hint"] != "":
        errors.append("blocked-only hint is %r, want the empty hint (#73)"
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


def test_guide_container_removed(doc):
    """#62: the WorkflowGuide container and create_guide are GONE from
    SilkGuide -- the task panel computes live and publishes no state to
    the property editor, so a snapshot object had nothing to serve.

    Asserted on the module itself (not by constructing anything), because
    the point is that the constructor is no longer reachable at all.
    """
    import SilkGuide

    errors, checks = [], []
    for name in ("WorkflowGuide", "WorkflowGuideViewProvider",
                 "create_guide"):
        if hasattr(SilkGuide, name):
            errors.append("SilkGuide still exposes %s" % name)
    checks.append("no container class, no create_guide on SilkGuide")

    # And no SILK-GUIDE-typed object can appear in a document any more.
    a = _square_patch(doc, "A")
    _patch_sharing(doc, a.Edges[0], "B")
    doc.recompute()
    guides = [o for o in doc.Objects
              if getattr(o, "object_type", None) == "WorkflowGuide"]
    if guides:
        errors.append("document holds %d WorkflowGuide object(s): %s"
                      % (len(guides), [o.Name for o in guides]))
    checks.append("no WorkflowGuide object can reach a document")

    # The query itself is untouched and still pure.
    state = compute_guide_state(doc)
    if state["hint"] != HINT_BLEND:
        errors.append("hint %r != %r after the container removal"
                      % (state["hint"], HINT_BLEND))
    checks.append("compute_guide_state still returns hint=%r"
                  % state["hint"])
    return {"pass": not errors, "errors": errors, "checks": checks}


ALL_TESTS = [
    test_guide_state_empty_document,
    test_guide_state_no_document,
    test_guide_state_edges_only,
    test_guide_state_single_patch_no_seam,
    test_guide_state_blendable_seam,
    test_guide_state_chain_complete,
    test_guide_state_scales_to_many_patches,
    test_guide_state_blocked_seam_does_not_block_completion,
    test_guide_state_seams_match_seam_inventory,
    test_guide_container_removed,
]
