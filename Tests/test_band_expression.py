"""#74 -- a band edge driven by an expression.

The ticket's blocking question was how the wizard tells a WORKING binding
from a silently broken one.  Measured on this FreeCAD build (1.1.3), on an
`App::PropertyFloat`:

  * `setExpression(prop, "0.25")` works, `isValid()` stays True, and a
    direct `prop = 0.55` under the binding reads 0.55 until the next
    recompute, then **reverts to 0.25 with no message at all** -- the
    silent-discard hazard, and the reason a literal write must be refused
    by name rather than attempted;
  * an unresolvable binding (`Nope.A1`) leaves the property HOLDING ITS
    STALE VALUE but the object `Touched, Invalid`, with
    `getStatusString()` naming the binding, and `evalExpression(text)`
    raising -- so detection is possible and the VALUE is the one thing
    that cannot answer it.

These tests pin that behaviour as the panel's contract: `write_band_split`
refuses an expression-owned band (naming patch, property and expression),
`band_binding_problem` tells a working binding from a broken one, the
panel's editor for a driven band is read-only, and an unblend detaches the
binding with the band instead of half-working.

No continuity label is asserted anywhere.
"""

import FreeCAD

from FreeCAD import Gui

from Tests.mcp_harness import check
from Tests.test_seam_resolver import _Capture, _build_tube
from SilkTaskPanel import BAND_A, _side_of, _stored_from_width, \
    band_binding_problem, band_expression, read_band_split, write_band_split


def _fixture(doc):
    """A two-seam tube, both seams blended.  Returns (pa, pb, seams,
    blends, entry) where `entry` is the panel entry for the left seam."""
    from SilkWorkflowOps import create_blend_by_edge
    pa, pb, s_left, s_right = _build_tube(doc)
    blends = [create_blend_by_edge(e) for e in (s_left, s_right)]
    doc.recompute()
    entry = {"edge": s_left, "patch_a": pa, "patch_b": pb,
             "status": "blended", "blend": blends[0]}
    return pa, pb, (s_left, s_right), blends, entry


def test_write_band_split_refuses_an_expression_owned_band(doc):
    """A literal write onto a driven property is refused BY NAME, and the
    stored value never becomes the typed one -- not even transiently
    (a transient change is what a panel would display as the user's)."""
    errors, checks = [], []
    pa, pb, seams, blends, entry = _fixture(doc)
    prop, ss = _side_of(pa, pb, seams[0])
    if not check(prop is not None, "the seam has no band property", errors):
        return {"pass": False, "errors": errors, "checks": checks}

    pa.setExpression(prop, "0.2")
    doc.recompute()
    check(float(getattr(pa, prop)) == 0.2,
          "the binding did not take: %s = %g"
          % (prop, float(getattr(pa, prop))), errors)
    with _Capture() as cap:
        wrote = write_band_split(entry, BAND_A, 0.33)
    doc.recompute()
    msgs = "".join(cap.errors)
    check(wrote is False, "the write onto a driven %s returned %r"
          % (prop, wrote), errors)
    check(pa.Name in msgs and prop in msgs and "0.2" in msgs,
          "the refusal names neither the patch, the property nor the "
          "expression: %r" % msgs, errors)
    check(float(getattr(pa, prop)) == 0.2,
          "the refused write moved %s to %g -- a value the next recompute "
          "would silently revert" % (prop, float(getattr(pa, prop))),
          errors)
    checks.append("driven %s.%s: write refused (%r), value still 0.2 after "
                  "the recompute" % (pa.Name, prop, wrote))

    # detaching it hands the property back: the same write now lands
    pa.setExpression(prop, None)
    doc.recompute()
    check(write_band_split(entry, BAND_A, 0.33),
          "the write was still refused after the expression was detached",
          errors)
    doc.recompute()
    want = _stored_from_width(0.33, ss)
    check(abs(float(getattr(pa, prop)) - want) < 1e-9,
          "after detaching, %s = %g, expected %g"
          % (prop, float(getattr(pa, prop)), want), errors)
    if not errors:
        checks.append("detached %s: the write lands (%.3f)" % (prop, want))
    return {"pass": not errors, "errors": errors, "checks": checks}


def test_a_broken_binding_is_named_not_read_as_a_number(doc):
    """The state is what answers the blocking question, and the panel acts
    on it: a broken binding is reported (tooltip + the refused write), and
    the number on screen is labelled as the stale one it is."""
    errors, checks = [], []
    pa, pb, seams, blends, entry = _fixture(doc)
    prop, ss = _side_of(pa, pb, seams[0])
    if not check(prop is not None, "the seam has no band property", errors):
        return {"pass": False, "errors": errors, "checks": checks}

    stored = float(getattr(pa, prop))
    pa.setExpression(prop, "<<NoSuchSheet>>.s0")
    doc.recompute()
    text = band_expression(pa, prop)
    problem = band_binding_problem(pa, prop, text)
    check(text == "NoSuchSheet.s0", "the binding text reads %r" % text, errors)
    check(bool(problem),
          "a broken binding reported no problem (value %g, isValid %r)"
          % (float(getattr(pa, prop)), pa.isValid()), errors)
    check(float(getattr(pa, prop)) == stored,
          "the broken binding changed the stored value (%g -> %g)"
          % (stored, float(getattr(pa, prop))), errors)
    with _Capture() as cap:
        wrote = write_band_split(entry, BAND_A, 0.33)
    msgs = "".join(cap.errors)
    check(wrote is False, "a write onto a broken binding returned %r"
          % (wrote,), errors)
    check("does not produce a value" in msgs,
          "the refusal does not say the binding is broken: %r" % msgs, errors)
    checks.append("broken binding %r -> problem %r, write refused"
                  % (text, (problem or "")[:60]))

    # the panel's own editor: read-only, and the tooltip names the binding
    from SilkTaskPanel import CreateGuide, SECTION_BLEND, current_panel
    panel = None
    try:
        CreateGuide().Activated()
        panel = current_panel()
        if check(panel is not None, "Activated left no panel open", errors):
            panel.sections.open(SECTION_BLEND)
            spin = panel.split_editor(seams[0], BAND_A)
            if check(spin is not None, "the blended row has no Band A editor",
                     errors):
                check(spin.isReadOnly(),
                      "the editor for a driven band is writable", errors)
                tip = spin.toolTip()
                check("DRIVEN" in tip and "NoSuchSheet.s0" in tip,
                      "the tooltip does not name the binding: %r" % tip, errors)
                check("last value stored" in tip,
                      "the tooltip does not label the shown number as the "
                      "stale one: %r" % tip, errors)
                checks.append("editor read-only; tooltip names the binding "
                              "and the stale number")
    finally:
        if panel is not None:
            try:
                panel.close_panel()
            except Exception:
                pass
        Gui.Control.closeDialog()
        import SilkTaskPanel
        SilkTaskPanel._open_panel = None
        pa.setExpression(prop, None)
        doc.recompute()
    return {"pass": not errors, "errors": errors, "checks": checks}


def test_unblend_detaches_the_binding_with_the_band(doc):
    """`_drop_band_split` is the other writer of the band property: under a
    binding, a sentinel written there is reverted at the next recompute,
    so the unblend would half-work.  It detaches instead, and names what it
    detached -- while an END a surviving seam still needs keeps its own
    binding untouched."""
    errors, checks = [], []
    pa, pb, seams, blends, entry = _fixture(doc)
    from SilkBlend import _band_split_of, _side_on, band_edge_prop
    from SilkMachinery import split_pair

    blend = blends[0]
    etype = _side_on(blend, pa)
    if not check(etype is not None, "the blend resolves no side on %s"
                 % pa.Name, errors):
        return {"pass": False, "errors": errors, "checks": checks}
    letter = _band_split_of(etype)[0][0]
    prop = band_edge_prop(letter, 0)
    pa.setExpression(prop, "0.15")
    doc.recompute()
    check(float(getattr(pa, prop)) == 0.15,
          "the binding on %s did not take" % prop, errors)

    # the unblend itself: deleting the blend is the user's untick, and the
    # delete watcher is what calls `_drop_band_split` for the seam it owned
    with _Capture() as cap:
        doc.removeObject(blend.Name)
        doc.recompute()
    msgs = "".join(cap.messages)
    check(band_expression(pa, prop) is None,
          "%s is still driven after the unblend" % prop, errors)
    check(prop in msgs and "0.15" in msgs,
          "the detachment is not named: %r" % msgs, errors)
    check(band_expression(pa, prop) is None,
          "%s is still driven after the unblend" % prop, errors)
    check(split_pair(pa, letter)[0] == 0.0,
          "the axis did not go back to its sentinel: %r"
          % (split_pair(pa, letter),), errors)
    # the OTHER seam's end keeps its edge (and would keep its binding)
    keep_free = split_pair(pa, letter)[1]
    checks.append("unblend of the seam: binding on %s detached and named; "
                  "axis now %r (end 1 left as %g)"
                  % (prop, split_pair(pa, letter), keep_free))
    return {"pass": not errors, "errors": errors, "checks": checks}
