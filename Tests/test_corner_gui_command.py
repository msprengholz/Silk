"""
GUI command tests for Silk_CreateCornerBlend (ticket #91).

The command turns 4 selected Blend strips into ONE CornerBlend where they
ring a shared junction. The whole contract -- adjudicating the ring,
refusing a non-junction / repeated strip set BY NAME with nothing left in
the tree (#80/#83), and the idempotent "already has a corner" no-op --
lives in SilkWorkflowOps.create_corner_blend. The command only reads the
selection, opens the undo transaction the task panel's own path also
opens, and reports.

Style follows Tests/test_blend_gui_command.py: build the 2x2 corner model
via the ops layer, drive the command through Gui.Selection + the command
class, assert with the oracle + console capture, and check the document's
own undo stack for the one-transaction contract.
"""

# --- manual tier ------------------------------------------------------
# This module's subject is an end-to-end rebuild / GUI drive /
# measurement sweep, so it is NOT in the default (fast) tier. Run it
# with `python3 Tests/run_all.py --manual` (or by name as a filter);
# Tests/test_manual_tier.py asserts it stays importable. See suite.py.
MANUAL = True
import FreeCAD
from FreeCAD import Gui
from Tests.mcp_harness import check

STRIPS = ("B12", "B24", "B43", "B31")


def _select(*objs):
    Gui.Selection.clearSelection()
    for o in objs:
        Gui.Selection.addSelection(o)


def _corners(doc):
    return [o for o in doc.Objects
            if getattr(o, "object_type", None) == "CornerBlend"]


def test_create_corner_gui_four_strips(doc):
    """Select the 4 ring strips -> Silk_CreateCornerBlend builds ONE
    CornerBlend through the ops resolver: full CB1-CB4 oracle green, and
    the success message names it."""
    errors, checks = [], []
    import Tests.corner_model as cm
    from SilkCorner import CreateCornerBlend
    from SilkChecks import check_corner_blend
    from Tests.test_seam_resolver import _Capture

    cm.build_corner_model(doc)
    strips = [doc.getObject(n) for n in STRIPS]
    _select(*strips)
    with _Capture() as cap:
        CreateCornerBlend().Activated()
    doc.recompute()

    corners = _corners(doc)
    check(len(corners) == 1,
          "expected exactly 1 corner blend from 4 selected strips, got %d"
          % len(corners), errors)
    if len(corners) == 1:
        c = corners[0]
        results = check_corner_blend(c, *strips)
        bad = [(n, d) for n, ok, d in results if not ok]
        check(not bad, "oracle flagged the GUI-built corner: %s" % bad, errors)
        check(any(("Corner blend created: %s" % c.Name) in m
                  for m in cap.messages),
              "no 'Corner blend created: %s' message; got: %s"
              % (c.Name, cap.messages), errors)
        checks.append("%s built from 4 selected strips: oracle %d checks, "
                      "%d failed" % (c.Name, len(results), len(bad)))
    errors += ["console error: %s" % e for e in cap.errors]
    return {"pass": not errors, "errors": errors, "checks": checks}


def test_create_corner_gui_is_one_undo_step(doc):
    """One command run is ONE document transaction = ONE undo step,
    checked on the document's own undo stack (doc.UndoCount)."""
    errors, checks = [], []
    import Tests.corner_model as cm
    from SilkCorner import CreateCornerBlend

    cm.build_corner_model(doc)
    strips = [doc.getObject(n) for n in STRIPS]
    before = doc.UndoCount
    _select(*strips)
    CreateCornerBlend().Activated()
    doc.recompute()
    after = doc.UndoCount

    check(len(_corners(doc)) == 1, "no corner blend was created", errors)
    check(after - before == 1,
          "one command moved the undo stack by %d steps (expected 1); "
          "UndoNames=%r" % (after - before, list(doc.UndoNames)), errors)
    checks.append("one command -> one undo step (%d -> %d)" % (before, after))
    return {"pass": not errors, "errors": errors, "checks": checks}


def test_create_corner_gui_refuses_non_ring(doc):
    """A selection that is not the ring of 4 blends around one junction is
    refused BY NAME and leaves NO CornerBlend in the tree: 3 strips, a
    repeated strip, and a 3-strips-plus-a-patch selection (the patch is
    not a blend, so it is ignored and the strip count is 3)."""
    errors, checks = [], []
    import Tests.corner_model as cm
    from SilkCorner import CreateCornerBlend
    from Tests.test_seam_resolver import _Capture

    cm.build_corner_model(doc)
    strips = [doc.getObject(n) for n in STRIPS]
    patch = doc.getObject("Patch44")
    cases = [("three strips", strips[:3]),
             ("a repeated strip",
              [strips[0], strips[1], strips[2], strips[0]]),
             ("a patch in the ring",
              [strips[0], strips[1], strips[2], patch])]
    with _Capture() as cap:
        for _label, objs in cases:
            _select(*objs)
            CreateCornerBlend().Activated()
    doc.recompute()

    n = len(_corners(doc))
    check(n == 0,
          "refused selections created %d corner blend(s)" % n, errors)
    refusals = [e for e in cap.errors if "Silk:" in e]
    check(len(refusals) >= len(cases),
          "expected a refusal per case, got %d: %s"
          % (len(refusals), cap.errors), errors)
    check(not any("Corner blend created" in m for m in cap.messages),
          "a refused selection announced a creation: %s" % cap.messages,
          errors)
    checks.append("%d non-ring selections refused by name, no corner "
                  "created" % len(cases))
    return {"pass": not errors, "errors": errors, "checks": checks}


ALL_TESTS = [
    test_create_corner_gui_four_strips,
    test_create_corner_gui_is_one_undo_step,
    test_create_corner_gui_refuses_non_ring,
]
