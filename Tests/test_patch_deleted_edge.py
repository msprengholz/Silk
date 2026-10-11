"""
Tests/test_patch_deleted_edge.py -- ticket #46: a precise console error
when a Patch's referenced Edge is deleted on the script path.

The problem. Deleting a Silk Edge out from under a Patch is otherwise
SILENT. Std_Delete already warns for us -- it walks the InList and pops
"Object Dependencies - might break", because our view providers keep the
default canDelete=False (invariant: never override canDelete to True).
On the GUI path that warning is the whole story.

But the SCRIPT path (doc.removeObject / Scripts menu / the future
wizard) has no such dialog, and FreeCAD's own cleanup is invisible: the
dead link is cleanly removed from `Edges` -- no None left in the list, no
exception, no event. The count check cannot save us either, because a
4-edge quad shrinking to 3 is a LEGAL pointed fill (#38). The only
symptom is that the surviving 3 edges no longer close, so the fill dies
with ArachNURBS's cryptic "curves do not share endpoints" -- which names
a symptom, not the cause. The user is told to go look at three edges
that are each perfectly fine, and never told that a fourth was deleted.

The fix. The Patch remembers the boundary edge IDENTITIES (FreeCAD
internal Names) it was last successfully built from, and identity-diffs
them against the current `Edges` on every execute. A name that went
missing is named, along with the patch and the fact that the boundary is
now short:

    Silk: Patch 'Patch001': boundary edge 'E_Shr' was deleted — patch
    is incomplete (needs 3 or 4 edges).

The baseline is deliberately NOT advanced while an edge is missing, so
the check is stateless: every subsequent execute re-detects and
re-reports. No once-flag to go stale, no state to leak.

Fixtures are built in memory from the ops layer (create_edge /
create_patch); no document under Resources/Test_files is ever opened, so
the user's open example docs are untouched.
"""

import FreeCAD

from Tests.test_patch_stage import _CaptureConsole


# ---- fixtures -----------------------------------------------------------

def _quad_patch(doc, name="P1"):
    """A healthy 4-edge (quad) patch on the standard square loop.

    Returns (patch, edges). Baseline is recorded by the create_patch
    recompute, so the patch is "last known good" before anything is
    deleted.
    """
    from Tests.test_patch_unified import _make_loop_edges
    from SilkWorkflowOps import create_patch
    edges = _make_loop_edges(doc)
    p = create_patch(edges, name=name)
    doc.recompute()
    return p, edges


def _pointed_patch(doc, name="PT"):
    """A healthy 3-edge (pointed) patch on the closed triangle loop.

    The false-positive guard: a legitimate 3-edge pointed patch has the
    same edge COUNT as a quad that lost one, and must never be reported.
    """
    from Tests.test_patch_unified import _make_triangle_edges
    from SilkWorkflowOps import create_patch
    edges = _make_triangle_edges(doc)
    p = create_patch(edges, name=name)
    doc.recompute()
    return p, edges


def _deleted_errors(cap):
    """Only the #46 messages from a capture (other modules may speak up)."""
    return [e for e in cap.errors if "was deleted" in e]


# ---- test 1: the message names the missing edge AND the patch ------------

def test_deleted_edge_names_edge_and_patch(doc):
    """Delete one of a quad patch's four edges on the script path and
    recompute: no crash, and a precise console error naming BOTH the
    missing edge and the patch that lost it.

    Also pins the mechanics that make the detection possible: FreeCAD
    removes the dead link SILENTLY (4 -> 3 entries, no None, no
    exception), so nothing but an identity diff can see it -- and the
    patch's last-known baseline really did hold the deleted edge's name.
    """
    errors, checks = [], []
    p, edges = _quad_patch(doc, name="P1")
    gone_name = edges[2].Name   # the Python wrapper dies with the object
    patch_name = p.Name

    if len(p.Edges) != 4:
        errors.append("fixture patch does not start with 4 edges: %d"
                      % len(p.Edges))
        return {"pass": False, "errors": errors, "checks": checks}

    with _CaptureConsole() as cap:
        doc.removeObject(gone_name)
    if cap.errors:
        errors.append("doc.removeObject itself printed errors: %s"
                      % cap.errors)
    checks.append("removeObject('%s') was silent (no exception, no "
                  "console output)" % gone_name)

    # the silent shrink: this is why a count check is not enough
    if len(p.Edges) != 3:
        errors.append("after deleting one edge the link list is %d "
                      "entries, expected the silent shrink to 3"
                      % len(p.Edges))
    if any(e is None for e in p.Edges):
        errors.append("a None survived in Edges after deletion")
    checks.append("FreeCAD silently shrank Edges 4 -> %d (a legal pointed "
                  "count, no None, no event)" % len(p.Edges))

    # the baseline still remembers the deleted edge
    baseline = list(getattr(p, "_LastEdgeNames", []) or [])
    if gone_name not in baseline:
        errors.append("last-known identities %r do not include the edge "
                      "about to be deleted %r" % (baseline, gone_name))
    else:
        checks.append("last-known identities recorded all 4 edge names, "
                      "including '%s'" % gone_name)

    # now the recompute the user would run
    with _CaptureConsole() as cap:
        doc.recompute()
    msgs = _deleted_errors(cap)
    if not msgs:
        errors.append("no 'was deleted' console error after removing a "
                      "boundary edge; captured instead: %s" % cap.errors)
        return {"pass": False, "errors": errors, "checks": checks}

    hit = [m for m in msgs if gone_name in m and patch_name in m]
    if not hit:
        errors.append("the message does not name both the edge %r and the "
                      "patch %r: %r" % (gone_name, patch_name, msgs))
        return {"pass": False, "errors": errors, "checks": checks}
    checks.append("error names edge '%s' and patch '%s': %s"
                  % (gone_name, patch_name, hit[0].strip()))

    msg = hit[0]
    for frag in ("was deleted", "incomplete", "3 or 4 edges"):
        if frag not in msg:
            errors.append("message missing %r: %r" % (frag, msg))
    if "curves do not share endpoints" in msg:
        errors.append("message is the cryptic ArachNURBS symptom, not the "
                      "cause: %r" % msg)

    # no crash: the patch object survives and is still computable
    if doc.getObject(patch_name) is not p:
        errors.append("the patch object disappeared after the broken "
                      "recompute")
    checks.append("patch '%s' survived the broken recompute (no crash)"
                  % patch_name)
    return {"pass": not errors, "errors": errors, "checks": checks}


# ---- test 2: stateless re-fire on every execute -------------------------

def test_error_refires_on_every_execute(doc):
    """The message is NOT once-only: it re-fires on every execute for as
    long as the patch stays broken.

    This is what the frozen baseline buys -- no once-flag that can go
    stale after the first notice, so a user who scrolls past the message
    (or fixes a different patch first) still sees it on the next
    recompute.
    """
    errors, checks = [], []
    p, edges = _quad_patch(doc, name="P1")
    gone_name = edges[2].Name
    doc.removeObject(gone_name)

    rounds = []
    for i in range(3):
        p.touch()                      # force a fresh execute each round
        with _CaptureConsole() as cap:
            doc.recompute()
        hits = [m for m in _deleted_errors(cap) if gone_name in m]
        rounds.append(len(hits))
        if not hits:
            errors.append("execute #%d printed no deleted-edge error "
                          "(captured: %s)" % (i + 1, cap.errors))
        else:
            checks.append("execute #%d re-fired: %s"
                          % (i + 1, hits[0].strip()))

    if rounds != [1, 1, 1]:
        errors.append("expected exactly one message per execute, got %r"
                      % rounds)
    else:
        checks.append("3 consecutive executes, 3 messages -- stateless "
                      "re-fire, no once-flag")

    # and the baseline is genuinely frozen, not re-captured to the broken
    # set (that is the mechanism, and it is what keeps re-firing possible)
    baseline = list(getattr(p, "_LastEdgeNames", []) or [])
    if gone_name not in baseline:
        errors.append("baseline advanced past the broken state %r -- it "
                      "must stay pinned to the last known good set"
                      % baseline)
    else:
        checks.append("baseline stayed pinned to the last known good set "
                      "%r" % baseline)
    return {"pass": not errors, "errors": errors, "checks": checks}


# ---- test 3: healthy patches stay silent --------------------------------

def test_healthy_patch_prints_nothing(doc):
    """A patch that has not lost an edge must print NOTHING -- including
    across repeated recomputes and a user-style split edit.

    Two false-positive guards live here:
      * the 3-edge POINTED patch, which has the same edge count as a
        quad that lost one and must never be reported;
      * repeated recomputes of a healthy patch, whose baseline is
        rewritten on every execute without ever going missing.
    """
    errors, checks = [], []
    p, edges = _quad_patch(doc, name="P1")

    with _CaptureConsole() as cap:
        for _ in range(3):
            doc.recompute()
            p.touch()
            doc.recompute()
        p.USplits = [0.5]          # a user-style edit -> live recompute
        doc.recompute()
    if cap.errors:
        errors.append("a healthy patch printed errors: %s" % cap.errors)
    else:
        checks.append("healthy quad patch: 6 recomputes + a split edit, "
                      "console completely silent")

    q, _ = _pointed_patch(doc, name="PT")
    with _CaptureConsole() as cap:
        for _ in range(3):
            doc.recompute()
            q.touch()
            doc.recompute()
    if cap.errors:
        errors.append("a healthy POINTED (3-edge) patch printed errors: %s"
                      % cap.errors)
    else:
        checks.append("healthy pointed 3-edge patch: 6 recomputes, silent "
                      "(no false 'deleted' on a legal 3-edge fill)")

    # both are genuinely intact
    from SilkChecks import check_patch
    for tag, obj, eds in (("quad", p, list(p.Edges)),
                          ("pointed", q, list(q.Edges))):
        bad = [(n, d) for n, ok, d in check_patch(obj, eds) if not ok]
        if bad:
            errors.append("healthy %s patch oracle not green: %s"
                          % (tag, bad))
        else:
            checks.append("healthy %s patch: oracle green (%d edges)"
                          % (tag, len(eds)))
    return {"pass": not errors, "errors": errors, "checks": checks}


# ---- test 4: the #59 settle invariant survives the new bookkeeping ------

def test_deleted_edge_does_not_rediary_document(doc):
    """The #46 bookkeeping write must not re-touch the object -- or it
    would undo #59 (a settled document must not be left dirty) and every
    save would prompt.

    _LastEdgeNames is marked Output, exactly like #59's
    _HiddenSubgridIdxs, so the per-execute write leaves no Touched bit
    behind even while the patch is reporting an error every recompute.
    The untouched sibling patch is the control: its geometry, display
    and oracle must be bit-identical across the whole episode.
    """
    errors, checks = [], []
    from Tests.test_patch_touched import _build_two_patch_pair
    from SilkChecks import check_patch

    pa, pb, _seam = _build_two_patch_pair(doc)
    doc.recompute()
    base_poles = [tuple(v) for v in pb.Poles]
    base_faces = len(pb.Shape.Faces)
    base_area = pb.Shape.Area

    gone_name = list(pa.Edges)[1].Name
    doc.removeObject(gone_name)

    with _CaptureConsole() as cap:
        for _ in range(3):
            doc.recompute()
            for o in (pa, pb):
                o.touch()
            doc.recompute()

    msgs = [m for m in _deleted_errors(cap) if gone_name in m and pa.Name in m]
    if not msgs:
        errors.append("pa did not report the deleted edge %r (captured: %s)"
                      % (gone_name, cap.errors))
    else:
        checks.append("pa reported '%s' on %d recomputes"
                      % (gone_name, 6))

    # the #59 invariant: nothing left dirty, however many recomputes
    dirty = [(o.Name, list(o.State)) for o in doc.Objects
             if getattr(o, "object_type", "") in ("Patch", "Blend")
             and "Touched" in o.State]
    if dirty:
        errors.append("document left dirty by the #46 bookkeeping write "
                      "(#59 settle invariant broken): %s" % dirty)
    else:
        checks.append("6 recomputes while broken: document still settles, "
                      "no Patch/Blend left Touched")

    # the sibling patch is bit-identical throughout
    if [tuple(v) for v in pb.Poles] != base_poles:
        errors.append("the untouched sibling pb changed poles")
    if len(pb.Shape.Faces) != base_faces:
        errors.append("the untouched sibling pb changed its display "
                      "(%d -> %d faces)" % (base_faces, len(pb.Shape.Faces)))
    if abs(pb.Shape.Area - base_area) > 1e-9:
        errors.append("the untouched sibling pb changed area")
    bad = [(n, d) for n, ok, d in check_patch(pb, list(pb.Edges)) if not ok]
    if bad:
        errors.append("sibling pb oracle not green: %s" % bad)
    else:
        checks.append("sibling pb untouched: same poles, same %d display "
                      "faces, same area, oracle green" % base_faces)
    return {"pass": not errors, "errors": errors, "checks": checks}


# ---- test 5: a deliberate re-wire is not mistaken for a deletion --------

def test_deliberate_rewire_is_not_reported(doc):
    """The check reports a pure SHRINK only.

    Re-wiring the link list through the property editor (drop one edge,
    add another) also removes a name from the set -- but nothing was
    deleted, the user meant it, and nagging about it on every recompute
    would be worse than the silence #46 is fixing. Adding an edge makes
    the episode a re-wire, not a deletion, so the message stays quiet
    and the new baseline is adopted normally.
    """
    errors, checks = [], []
    from Tests.test_patch_unified import _make_loop_edges, _make_triangle_edges
    from SilkWorkflowOps import create_patch

    edges = _make_loop_edges(doc)
    spare = _make_triangle_edges(doc)     # unrelated geometry to wire in
    p = create_patch(edges, name="P1")
    doc.recompute()
    before = list(getattr(p, "_LastEdgeNames", []) or [])

    # user-style edit: swap the third edge for an unrelated one
    p.Edges = [edges[0], edges[1], spare[0], edges[3]]
    with _CaptureConsole() as cap:
        for _ in range(3):
            doc.recompute()
            p.touch()
            doc.recompute()
    msgs = _deleted_errors(cap)
    if msgs:
        errors.append("a deliberate re-wire was reported as a deletion: %s"
                      % msgs)
    else:
        checks.append("re-wiring 4 edges (one replaced) reported nothing "
                      "across 6 recomputes")

    after = list(getattr(p, "_LastEdgeNames", []) or [])
    if after == before:
        errors.append("baseline was not adopted for the rewired set "
                      "(still %r)" % after)
    else:
        checks.append("baseline adopted the rewired set %r" % after)

    # the patch is still computable and still consistent with what it is
    # now linked to -- i.e. we did not freeze it into a false report
    if len(p.Edges) != 4:
        errors.append("rewire did not take, Edges = %d" % len(p.Edges))
    return {"pass": not errors, "errors": errors, "checks": checks}


ALL_TESTS = [
    test_deleted_edge_names_edge_and_patch,
    test_error_refires_on_every_execute,
    test_healthy_patch_prints_nothing,
    test_deleted_edge_does_not_rediary_document,
    test_deliberate_rewire_is_not_reported,
]
