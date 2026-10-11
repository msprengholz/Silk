"""
GUI command tests for Silk_CreateBlend (ticket #45).

The command accepts EITHER 1 selected Edge or 2 selected patches:

  1 Edge   -> delegates the whole contract to the #44 resolver
              SilkWorkflowOps.create_blend_by_edge (identity-only
              adjacent pair, per-seam idempotency, graceful 0/1/3+
              refusals, the edge as geometric seam pin). Creation is
              immediate -- no confirmation dialog -- and only a NEW
              blend gets a "created across" message on top of the
              resolver's own messaging (its idempotent no-op message
              reaches the user unmodified, not double-reported).
  2 Patches -> the unchanged direct pair construction (Blend(obj,
              sel[0], sel[1]), no Edge link, styling as today).
  anything else -> the command's own "Silk: ..." console refusal,
              zero side effects.

Style follows Tests/test_patch_gui_command.py: build docs via the ops
layer, drive the command via Gui.Selection + the command class, assert
with the oracle + console capture. Fixture helpers are reused from
Tests.test_seam_resolver (square / sharing / stray builders, splits,
message capture) and Tests.test_blend_stage (ground-truth chain) --
imported, not refactored.
"""
import FreeCAD
from FreeCAD import Gui


def check(cond, msg, errors):
    if not cond:
        errors.append(msg)
    return cond


def _select(*objs):
    Gui.Selection.clearSelection()
    for o in objs:
        Gui.Selection.addSelection(o)


def _blend_objects(doc):
    return [o for o in doc.Objects
            if getattr(o, "object_type", None) in ("Blend", "BlendStrip")]


def _open_gt_chain(doc):
    """Open the ground-truth fixture and rebuild the 7-edge / 2-patch
    chain in `doc`. Returns (fixture, pa, pb, edges_by_name); the
    caller must close the fixture and restore the active document
    (mirrors Tests.test_seam_resolver's fixture usage)."""
    import os
    from Tests.test_blend_stage import _build_gt_chain

    fixture_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "Resources", "Test_files",
                                "Silk_Workflow.FCStd")
    fixture = FreeCAD.openDocument(fixture_path)
    FreeCAD.setActiveDocument(doc.Name)  # openDocument activates fixture
    pa, pb, g = _build_gt_chain(doc, fixture)
    return fixture, pa, pb, g


def test_create_blend_gui_edge_selected(doc):
    """Select the shared Edge -> Silk_CreateBlend builds ONE unified
    Blend through the #44 resolver: full check_blend oracle green
    (incl. B4 against the stored ground-truth strip), the Edge
    property links the selected edge, and the success message names
    the blend + edge."""
    errors, checks = [], []
    from SilkBlend import CreateBlend
    from SilkChecks import check_blend
    from Tests.test_seam_resolver import _Capture

    fixture, pa, pb, g = _open_gt_chain(doc)
    try:
        _select(g["E_Shr"])
        with _Capture() as cap:
            CreateBlend().Activated()
        doc.recompute()

        blends = _blend_objects(doc)
        check(len(blends) == 1,
              "expected exactly 1 blend from 1 selected Edge, got %d"
              % len(blends), errors)
        if blends:
            b = blends[0]
            check(getattr(b, "object_type", None) == "Blend",
                  "expected a unified Blend, got %r"
                  % getattr(b, "object_type", None), errors)
            check(getattr(b, "Edge", None) is g["E_Shr"],
                  "Edge property does not link the selected edge "
                  "(Edge=%r)" % getattr(b, "Edge", None), errors)
            named = [m for m in cap.messages
                     if b.Name in m and "created across" in m]
            check(named,
                  "no success message naming %s across %s; got: %s"
                  % (b.Name, g["E_Shr"].Name, cap.messages), errors)
            results = check_blend(b, pa, pb,
                                  reference_poles=fixture.BlendStrip.Poles)
            bad = [(n, d) for n, ok, d in results if not ok]
            check(not bad,
                  "oracle flagged the GUI-built blend: %s" % bad, errors)
            checks.append("%s created across %s: oracle %d checks, "
                          "%d failed" % (b.Name, g["E_Shr"].Name,
                                         len(results), len(bad)))
        errors += ["console error: %s" % e for e in cap.errors]
    finally:
        FreeCAD.closeDocument(fixture.Name)
        FreeCAD.setActiveDocument(doc.Name)
    return {"pass": not errors, "errors": errors, "checks": checks}


def test_create_blend_gui_edge_idempotent(doc):
    """1 Edge already blended -> a second command run creates NO
    second blend: the resolver's 'already blended by <name>' message
    reaches the console unmodified, and the command adds no
    'created across' message of its own (the no-op is surfaced as the
    resolver words it, not re-reported as an error or a creation)."""
    errors, checks = [], []
    from SilkBlend import CreateBlend
    from Tests.test_seam_resolver import _Capture, _square_patch, \
        _patch_sharing

    a = _square_patch(doc, "A")
    e0 = a.Edges[0]
    _patch_sharing(doc, e0, "B")

    _select(e0)
    with _Capture() as cap1:
        CreateBlend().Activated()
    doc.recompute()
    errors += ["console error: %s" % e for e in cap1.errors]
    blends = _blend_objects(doc)
    if not check(len(blends) == 1,
                 "first run: expected 1 blend, got %d" % len(blends),
                 errors):
        return {"pass": False, "errors": errors, "checks": checks}
    first = blends[0]
    check(any(first.Name in m and "created across" in m
              for m in cap1.messages),
          "first run did not announce the creation; got: %s"
          % cap1.messages, errors)

    _select(e0)
    with _Capture() as cap2:
        CreateBlend().Activated()
    doc.recompute()
    blends2 = _blend_objects(doc)
    check(len(blends2) == 1,
          "second run created another blend (%d blend objects total)"
          % len(blends2), errors)
    named = [m for m in cap2.messages
             if "already blended" in m and first.Name in m]
    check(named,
          "resolver's idempotent no-op message naming %s did not reach "
          "the console; got: %s" % (first.Name, cap2.messages), errors)
    check(not any("created across" in m for m in cap2.messages),
          "command double-reported the no-op as a creation: %s"
          % cap2.messages, errors)
    errors += ["console error: %s" % e for e in cap2.errors]
    checks.append("2nd run: 1 blend kept, no-op message naming %s "
                  "reaches the console, no creation message"
                  % first.Name)
    return {"pass": not errors, "errors": errors, "checks": checks}


def test_create_blend_gui_edge_refusals(doc):
    """0 / 1 / 3+ referencing patches: the command routes to the #44
    resolver's refusals -- each message reaches the console, and the
    document is untouched: no Blend object, no USplits/VSplits
    written on any patch."""
    errors, checks = [], []
    from SilkBlend import CreateBlend
    from Tests.test_seam_resolver import _Capture, _square_patch, \
        _patch_sharing, _stray_edge, _splits

    a = _square_patch(doc, "A")
    e0 = a.Edges[0]
    _patch_sharing(doc, e0, "B")
    _patch_sharing(doc, e0, "C")
    stray = _stray_edge(doc)

    with _Capture() as cap:
        _select(stray)          # referenced by 0 patches
        CreateBlend().Activated()
        _select(a.Edges[1])     # referenced by A only
        CreateBlend().Activated()
        _select(e0)             # referenced by A, B, C (non-manifold)
        CreateBlend().Activated()
    doc.recompute()

    n = len(_blend_objects(doc))
    check(n == 0,
          "refusing selections created %d blend object(s)" % n, errors)
    for pname in ("A", "B", "C"):
        u, v = _splits(doc.getObject(pname))
        check(not u and not v,
              "refusal wrote splits on %s (U=%s V=%s)" % (pname, u, v),
              errors)
    expected = ("not used by any patch", "adjacent patch",
                "not a blendable seam")
    for want in expected:
        check(any(want in e for e in cap.errors),
              "missing refusal message %r; got: %s" % (want, cap.errors),
              errors)
    unexpected = [e for e in cap.errors
                  if not any(w in e for w in expected)]
    check(not unexpected,
          "unexpected console errors: %s" % unexpected, errors)
    check(not any("created across" in m for m in cap.messages),
          "refusals announced a creation: %s" % cap.messages, errors)
    checks.append("0/1/3+ refusals emitted, no blend objects, no "
                  "splits on A/B/C")
    return {"pass": not errors, "errors": errors, "checks": checks}


def test_create_blend_gui_two_patches(doc):
    """Select 2 patches -> the unchanged direct path: ONE unified
    Blend between them with NO Edge link (auto-detected seam), the
    'Blend created: <name>' message as before, and the full oracle
    green against the stored ground-truth strip."""
    errors, checks = [], []
    from SilkBlend import CreateBlend
    from SilkChecks import check_blend
    from Tests.test_seam_resolver import _Capture

    fixture, pa, pb, _ = _open_gt_chain(doc)
    try:
        _select(pa, pb)
        with _Capture() as cap:
            CreateBlend().Activated()
        doc.recompute()

        blends = _blend_objects(doc)
        check(len(blends) == 1,
              "expected exactly 1 blend from 2 selected patches, got %d"
              % len(blends), errors)
        if blends:
            b = blends[0]
            check(getattr(b, "object_type", None) == "Blend",
                  "expected a unified Blend, got %r"
                  % getattr(b, "object_type", None), errors)
            check(getattr(b, "PatchA", None) is pa
                  and getattr(b, "PatchB", None) is pb,
                  "PatchA/PatchB do not link the selected patches "
                  "(%r, %r)" % (getattr(b, "PatchA", None),
                                getattr(b, "PatchB", None)), errors)
            check(getattr(b, "Edge", None) is None,
                  "2-patch path must keep the no-Edge-link "
                  "(auto-detect) construction; Edge=%r"
                  % getattr(b, "Edge", None), errors)
            check(any(("Blend created: %s" % b.Name) in m
                      for m in cap.messages),
                  "no 'Blend created: %s' message; got: %s"
                  % (b.Name, cap.messages), errors)
            results = check_blend(b, pa, pb,
                                  reference_poles=fixture.BlendStrip.Poles)
            bad = [(n, d) for n, ok, d in results if not ok]
            check(not bad,
                  "oracle flagged the GUI-built blend: %s" % bad, errors)
            checks.append("%s built from 2 patches (no Edge link): "
                          "oracle %d checks, %d failed"
                          % (b.Name, len(results), len(bad)))
        errors += ["console error: %s" % e for e in cap.errors]
    finally:
        FreeCAD.closeDocument(fixture.Name)
        FreeCAD.setActiveDocument(doc.Name)
    return {"pass": not errors, "errors": errors, "checks": checks}


def test_create_blend_gui_rejects_mixed_selection(doc):
    """Every other selection shape (0 selected, 1 patch, 2 edges,
    1 edge + 1 patch, 3 mixed objects) is refused with the command's
    own 'Silk: ...' message: nothing created, no success messages."""
    errors, checks = [], []
    from SilkBlend import CreateBlend
    from Tests.test_seam_resolver import _Capture, _square_patch

    a = _square_patch(doc, "A")
    e0, e1 = a.Edges[0], a.Edges[1]

    cases = [
        ("0 selected", ()),
        ("1 patch", (a,)),
        ("2 edges", (e0, e1)),
        ("1 edge + 1 patch", (e0, a)),
        ("3 mixed objects", (e0, e1, a)),
    ]
    with _Capture() as cap:
        for _label, objs in cases:
            _select(*objs)
            CreateBlend().Activated()
    doc.recompute()

    refusals = [e for e in cap.errors if "Blend requires" in e]
    check(len(refusals) == len(cases),
          "expected %d refusals, got %d: %s"
          % (len(cases), len(refusals), cap.errors), errors)
    n = len(_blend_objects(doc))
    check(n == 0,
          "refused selections created %d blend object(s)" % n, errors)
    check(not any("created" in m for m in cap.messages),
          "refused selections announced a creation: %s"
          % cap.messages, errors)
    checks.append("%d selection shapes refused with the 'Silk: ...' "
                  "message; no blends created" % len(cases))
    return {"pass": not errors, "errors": errors, "checks": checks}


ALL_TESTS = [
    test_create_blend_gui_edge_selected,
    test_create_blend_gui_edge_idempotent,
    test_create_blend_gui_edge_refusals,
    test_create_blend_gui_two_patches,
    test_create_blend_gui_rejects_mixed_selection,
]
