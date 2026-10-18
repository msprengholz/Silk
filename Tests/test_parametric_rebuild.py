"""
#109 — a band-width write must leave the WHOLE chain consistent.

The defect the owner reported: editing an edge-blend band width leaves every
`CornerBlend` fed by that patch holding poles assembled from the PRE-edit
strips — no error, no tree marker, wrong geometry. The chain is meant to be
automatic (patch -> blend -> corner), but every link only TOUCHES its
dependent, and a touch is not a recompute:

  * `SilkPatch.onChanged` (a `USplit1/2` `VSplit1/2` write) did a
    single-object `fp.recompute()` — the patch rebuilt, the blend was
    touched, and nothing ran the blend;
  * `SilkPatch.execute` touches every linked blend;
  * `SilkBlend.run_blend`'s tail touches every `CornerBlend` that has the
    strip in `Strips`.

So the chain settled only through a *caller's* `doc.recompute()`. The panel's
own `write_band_split` happens to make that call (which is why the panel path
measured green even before the fix); a bare property write — the data tab,
an expression, a script, the ops layer — has no such caller and left the
strip and the corner byte-identical to their pre-edit state.

These tests pin the OBJECT as parametric: the write itself, with no
document recompute added by the test, must settle patch -> blend -> corner.
Both writers the panel/user has are exercised:

  * `test_band_property_write_is_parametric` — the bare property write that
    `SilkPatch.onChanged` owns (the panel's `write_band_split` is exactly
    this write plus a trailing `doc.recompute()`, so this is the object
    half of the owner's path). RED before the fix.
  * `test_panel_band_edit_rebuilds_corners_with_no_extra_recompute` — the
    panel's own `write_band_split`, the owner's path. Green before and
    after; it guards the end-to-end behaviour the fix must not break.

No continuity label is asserted anywhere.
"""

# --- manual tier ------------------------------------------------------
# This module's subject is an end-to-end rebuild / GUI drive /
# measurement sweep, so it is NOT in the default (fast) tier. Run it
# with `python3 Tests/run_all.py --manual` (or by name as a filter);
# Tests/test_manual_tier.py asserts it stays importable. See suite.py.
MANUAL = True

import FreeCAD

import Tests.corner_model as cm
from Tests.mcp_harness import check
from SilkTaskPanel import BAND_A, BAND_B, _side_of, _stored_from_width, \
    write_band_split
from SilkCorner import corner_from_strips


STRIP_NAMES = ("B12", "B24", "B43", "B31")


class _CaptureConsole:
    """Capture FreeCAD.Console.PrintError for one block."""

    def __enter__(self):
        self._orig = FreeCAD.Console.PrintError
        self.errors = []
        FreeCAD.Console.PrintError = lambda msg: (
            self.errors.append(msg), self._orig(msg))
        return self

    def __exit__(self, *args):
        FreeCAD.Console.PrintError = self._orig


def _delta(a, b):
    """Max pole-for-pole distance between two equal-length pole lists."""
    return max((FreeCAD.Vector(a[i]) - FreeCAD.Vector(b[i])).Length
               for i in range(len(a)))


def _snapshot(corner):
    return [FreeCAD.Vector(p) for p in corner.Poles]


def _fresh(corner):
    """A corner built right now from the strips' current stored poles."""
    poles, _weights, _cells, why = corner_from_strips(list(corner.Strips))
    return poles, why


def _assert_corner_matches_its_strips(corner, before, what, errors,
                                      expect_moved=True):
    """The contract: the corner is a function of its strips' CURRENT poles.
    `expect_moved` is for the writers that change the geometry; a display
    toggle or a hidden-cell write must leave the poles alone but still
    consistent. Raw numbers into `checks` via the caller."""
    fresh, why = _fresh(corner)
    if not fresh:
        errors.append("%s: a fresh corner from the same strips refused (%s)"
                      % (what, why))
        return None
    moved = _delta(before, _snapshot(corner))
    consistent = _delta(_snapshot(corner), fresh)
    if expect_moved and not moved > 1e-6:
        errors.append("%s: the corner did not move at all (max pole delta "
                      "%g) -- it still holds the pre-edit poles"
                      % (what, moved))
    if not consistent < 1e-6:
        errors.append("%s: the corner disagrees with a fresh build from the "
                      "same strips by %g -- stale poles" % (what, consistent))
    if "Invalid" in corner.State or corner.isValid() is not True:
        errors.append("%s: the corner is flagged after the write (State=%r, "
                      "isValid=%r)" % (what, corner.State, corner.isValid()))
    return moved, consistent


def _seam_entry(strip):
    """The panel entry for a strip's owned seam, plus the (patch_a, prop,
    end) the BAND_A editor would write."""
    pa, pb = strip.PatchA, strip.PatchB
    shared = next(e for e in pa.Edges if e in list(pb.Edges))
    prop, ss = _side_of(pa, pb, shared)
    entry = {"edge": shared, "patch_a": pa, "patch_b": pb,
             "status": "blended", "blend": strip}
    return entry, prop, ss


def _build(doc):
    model = cm.build_corner_model_with_blend(doc)
    strip = model["strips"]["B12"]
    return model, strip, model["corner_blend"]


def test_band_property_write_is_parametric(doc):
    """The write `SilkPatch.onChanged` owns settles the chain on its own.

    This is the object half of the panel's `write_band_split`: the panel
    performs this exact property assignment and then a `doc.recompute()`.
    A bare property write (data tab / expression / script / ops) has no
    trailing document pass, so the object must settle itself. RED before
    the fix: the patch rebuilt, but the strip and the corner stayed
    byte-identical to their pre-edit poles."""
    errors, checks = [], []
    _model, strip, corner = _build(doc)

    entry, prop, ss = _seam_entry(strip)
    patch = entry["patch_a"]
    before_corner = _snapshot(corner)
    before_strip = [FreeCAD.Vector(p) for p in strip.Poles]

    stored = _stored_from_width(0.2, ss)
    with _CaptureConsole() as cap:
        setattr(patch, prop, stored)      # no doc.recompute() by the test
    if cap.errors:
        errors.append("the bare property write printed errors: %r"
                      % cap.errors)
    checks.append("bare write: %s.%s = %g (a 0.2 band at end %d)"
                  % (patch.Name, prop, stored, ss))

    strip_moved = _delta(before_strip, [FreeCAD.Vector(p)
                                        for p in strip.Poles])
    if not strip_moved > 1e-6:
        errors.append("strip %s did not recompute against the new band "
                      "(max pole delta %g) -- it still reads the pre-edit "
                      "subgrids" % (strip.Name, strip_moved))
    checks.append("strip %s moved by %g after the bare write"
                  % (strip.Name, strip_moved))

    numbers = _assert_corner_matches_its_strips(
        corner, before_corner, "bare write", errors)
    if numbers:
        checks.append("corner %s moved %g from its pre-edit poles and "
                      "matches a fresh build from the same strips to %g"
                      % (corner.Name, numbers[0], numbers[1]))
    return {"pass": not errors, "errors": errors, "checks": checks}


def test_panel_band_edit_rebuilds_corners_with_no_extra_recompute(doc):
    """The owner's path: the panel's own `write_band_split`.

    `write_band_split` performs the property write and then one
    `doc.recompute()`, so this path already settles before the fix; it is
    here so the fix cannot regress the end-to-end behaviour, and it drives
    BOTH band editors on EVERY strip of the ring — each write must leave
    the corner equal to a fresh build from the same strips and moved from
    the pre-edit poles."""
    errors, checks = [], []
    model, _strip, corner = _build(doc)
    strips = [doc.getObject(n) for n in STRIP_NAMES]

    for which in (BAND_A, BAND_B):
        for strip in strips:
            entry, prop, ss = _seam_entry(strip)
            patch = entry["patch_a"] if which == BAND_A else entry["patch_b"]
            before = _snapshot(corner)
            with _CaptureConsole() as cap:
                wrote = write_band_split(entry, which, 0.2)
            if not wrote or cap.errors:
                errors.append("panel %s write on %s.%s was refused (%r)"
                              % (which, patch.Name, prop, cap.errors))
                continue
            numbers = _assert_corner_matches_its_strips(
                corner, before,
                "panel %s on %s.%s" % (which, patch.Name, prop), errors)
            if numbers:
                checks.append("panel %s on %s.%s: corner moved %g, matches "
                              "fresh to %g"
                              % (which, patch.Name, prop,
                                 numbers[0], numbers[1]))

    # one roll-up of the raw numbers for the equation the issue asks for
    fresh, _why = _fresh(corner)
    if fresh:
        checks.append("final corner vs fresh-from-strips max pole delta: %g"
                      % _delta(_snapshot(corner), fresh))
    return {"pass": not errors, "errors": errors, "checks": checks}


def test_neighbouring_patch_writes_keep_the_corner_consistent(doc):
    """The other writers that touch a patch AFTER a blend has executed.

    The issue names three and asks whether they are the same bug wearing a
    hat: the display toggles (`ShowSubgrids`), the blend's own auto-hide
    bookkeeping (`_HiddenSubgridIdxs`), and the band split `run_blend`
    writes through `ensure_band_split`. None may leave the corner
    disagreeing with its strips, and none may leave the patch flagged."""
    errors, checks = [], []
    model, strip, corner = _build(doc)
    patch = model["patches"]["Patch44"]

    # --- ShowSubgrids: a display toggle through onChanged
    before = _snapshot(corner)
    with _CaptureConsole() as cap:
        patch.ShowSubgrids = not bool(patch.ShowSubgrids)
    if cap.errors:
        errors.append("ShowSubgrids write printed errors: %r" % cap.errors)
    numbers = _assert_corner_matches_its_strips(corner, before,
                                                "ShowSubgrids", errors,
                                                expect_moved=False)
    if numbers:
        checks.append("ShowSubgrids: corner still matches fresh (delta %g)"
                      % numbers[1])

    # --- _HiddenSubgridIdxs: the blend's auto-hide bookkeeping write
    before = _snapshot(corner)
    current = sorted(set(int(i) for i in (patch._HiddenSubgridIdxs or [])))
    with _CaptureConsole() as cap:
        patch._HiddenSubgridIdxs = current   # the value run_blend would set
    if cap.errors:
        errors.append("_HiddenSubgridIdxs write printed errors: %r"
                      % cap.errors)
    numbers = _assert_corner_matches_its_strips(corner, before,
                                                "_HiddenSubgridIdxs", errors,
                                                expect_moved=False)
    if numbers:
        checks.append("_HiddenSubgridIdxs: corner still matches fresh "
                      "(delta %g)" % numbers[1])
    if "Invalid" in patch.State:
        errors.append("the hidden-cell write left the patch flagged (%r)"
                      % (patch.State,))

    # --- ensure_band_split: drop this end's band edge, and let the
    #     blend's own run_blend restore it. No recompute from the test:
    #     the sentinel write's onChanged must run the pass that re-drives
    #     the blend, ensure_band_split writes the default back, and the
    #     corner rebuilds in that same pass.
    from SilkMachinery import band_edge
    entry, prop, ss = _seam_entry(strip)
    check(write_band_split(entry, BAND_A, 0.25),
          "setting a non-default band before the ensure_band_split case",
          errors)
    sentinel = 0.0 if prop.endswith("1") else 1.0
    before = _snapshot(corner)
    with _CaptureConsole() as cap:
        setattr(patch, prop, sentinel)      # drop this end's band
    if cap.errors:
        errors.append("the ensure_band_split write printed errors: %r"
                      % cap.errors)
    if band_edge(getattr(patch, prop)) is None:
        errors.append("ensure_band_split did not restore a band edge on "
                      "%s.%s after it was dropped" % (patch.Name, prop))
    numbers = _assert_corner_matches_its_strips(corner, before,
                                                "ensure_band_split", errors)
    if numbers:
        checks.append("ensure_band_split: corner moved %g and matches fresh "
                      "to %g" % numbers)
    return {"pass": not errors, "errors": errors, "checks": checks}


def test_unblend_then_reblend_leaves_the_corner_honest(doc):
    """#71: unblend/re-blend a ring strip with a corner present.

    Unblending a ring strip breaks the ring, so the corner must REFUSE
    cleanly (empty poles, never the pre-edit ones). Re-blending the seam
    and re-linking the ring must rebuild the corner from the new strip,
    with no stale object left behind."""
    errors, checks = [], []
    model, strip, corner = _build(doc)
    from SilkWorkflowOps import create_blend

    doc.removeObject(strip.Name)          # unblend one ring member
    doc.recompute()
    if corner.Poles:
        # a broken ring is not a corner; if it kept anything it must at
        # least be a consistent build of what it still has (it is not)
        fresh, why = _fresh(corner)
        if not fresh or _delta(_snapshot(corner), fresh) > 1e-6:
            errors.append("unblend left the corner holding stale poles (%s)"
                          % why)
    checks.append("unblend: ring broken, corner poles=%d State=%s"
                  % (len(corner.Poles or []), list(corner.State)))

    again = create_blend(model["patches"]["Patch44"],
                         model["patches"]["Patch001"], name="B12again")
    doc.recompute()
    rest = [doc.getObject(n) for n in ("B24", "B43", "B31")]
    corner.Strips = [again] + rest        # re-link the ring: corner onChanged
    fresh, why = _fresh(corner)
    if not fresh:
        errors.append("re-blend/re-link refused to build the corner: %s"
                      % why)
    else:
        delta = _delta(_snapshot(corner), fresh)
        if not (len(corner.Poles) == 36 and delta < 1e-6
                and corner.isValid() is True):
            errors.append("re-blend/re-link left the corner stale or invalid "
                          "(%d poles, delta %g, isValid=%r)"
                          % (len(corner.Poles), delta, corner.isValid()))
        checks.append("re-blend/re-link: %d poles, matches fresh to %g"
                      % (len(corner.Poles), delta))
    return {"pass": not errors, "errors": errors, "checks": checks}


def test_panel_write_edge_cases_leave_the_document_as_it_was(doc):
    """The holes a caller-side `doc.recompute()` used to paper over.

    Removing the panel's `doc.recompute()` makes `Patch.onChanged` the only
    trigger for a band write. Four cases where that trigger may not fire,
    asserted explicitly rather than assumed:

      1. the SAME value written twice -- FreeCAD may not fire `onChanged`
         when the stored value does not change, so the second write must
         still leave the corner consistent with its strips;
      2. a REFUSED width -- nothing is written, so nothing may move, and
         the undo stack must not grow;
      3. an EXPRESSION-owned property -- FreeCAD discards the assignment
         silently; the write is a no-op and the document is UNCHANGED (not
         stale), which is the recorded #74 hazard and worth stating. This
         build refuses `setExpression` on an `App::PropertyFloat`, so the
         case is asserted only where the engine can own the property and
         otherwise recorded as untestable;
      4. the transaction boundary -- the document recompute now runs from
         inside the panel's open transaction; one edit must still be ONE
         undo step and print no error.
    """
    errors, checks = [], []
    model, strip, corner = _build(doc)
    entry, prop, ss = _seam_entry(strip)
    patch = entry["patch_a"]

    def consistent(what):
        fresh, why = _fresh(corner)
        if not fresh:
            errors.append("%s: a fresh corner from the same strips refused "
                          "(%s)" % (what, why))
            return None
        delta = _delta(_snapshot(corner), fresh)
        if delta > 1e-6:
            errors.append("%s: the corner disagrees with a fresh build by %g"
                          % (what, delta))
        return delta

    # ---- 1. the same value written twice
    with _CaptureConsole() as cap:
        first = write_band_split(entry, BAND_A, 0.2)
        second = write_band_split(entry, BAND_A, 0.2)
    errors += ["same-value write printed an error: %s" % e for e in cap.errors]
    if not (first and second):
        errors.append("a legal width was refused (first=%r second=%r)"
                      % (first, second))
    delta = consistent("same-value second write")
    if delta is not None:
        checks.append("same value written twice: corner still matches fresh "
                      "(delta %g), stored %g"
                      % (delta, float(getattr(patch, prop))))

    # ---- 2. a refused width: nothing written, nothing moves
    before_poles = _snapshot(corner)
    before_value = float(getattr(patch, prop))
    before_undo = doc.UndoCount
    for bad in (0.0, 1.0, -0.3, 1.7):
        with _CaptureConsole() as cap:
            wrote = write_band_split(entry, BAND_A, bad)
        if wrote:
            errors.append("a width of %g was not refused" % bad)
        if not cap.errors:
            errors.append("the refusal of %g said nothing on the console"
                          % bad)
    if float(getattr(patch, prop)) != before_value:
        errors.append("a refused width moved %s.%s (%g -> %g)"
                      % (patch.Name, prop, before_value,
                         float(getattr(patch, prop))))
    if doc.UndoCount != before_undo:
        errors.append("refused writes moved the undo stack by %d"
                      % (doc.UndoCount - before_undo))
    if _delta(before_poles, _snapshot(corner)) > 1e-9:
        errors.append("a refused width still moved the corner")
    checks.append("refused widths 0.0 / 1.0 / -0.3 / 1.7: value, undo stack "
                  "and corner all unchanged")

    # ---- 3. an EXPRESSION-owned property: FreeCAD discards the write
    #
    # The recorded #74 hazard is that an expression-owned property silently
    # swallows the assignment. With the caller's recompute gone there is no
    # recompute here either -- but nothing was stored, so the document is
    # UNCHANGED (not stale). This FreeCAD build refuses setExpression on an
    # App::PropertyFloat ("Expression can not evaluate to a value"), so the
    # case is asserted only where the engine can actually own the property.
    cur = float(getattr(patch, prop))
    installed = False
    try:
        patch.setExpression(prop, repr(cur))
        installed = any(n == prop for n, _e in patch.ExpressionEngine)
    except Exception as exc:
        checks.append("expression-owned property not testable on this "
                      "FreeCAD build: setExpression(%s) raised %s -- the "
                      "discarded write leaves the document unchanged"
                      % (prop, exc))
    if installed:
        doc.recompute()
        before_poles = _snapshot(corner)
        with _CaptureConsole() as cap:
            wrote = write_band_split(entry, BAND_A, 0.33)
        if float(getattr(patch, prop)) != cur:
            errors.append("an expression-owned property changed value "
                          "(%g -> %g)" % (cur, float(getattr(patch, prop))))
        if _delta(before_poles, _snapshot(corner)) > 1e-9:
            errors.append("the discarded expression write moved the corner")
        consistent("expression-owned write")
        checks.append("expression-owned %s: write_band_split returned %r "
                      "but FreeCAD discarded it -- stored %g unchanged, "
                      "corner unchanged and consistent (the #74 hazard)"
                      % (prop, wrote, float(getattr(patch, prop))))
        patch.setExpression(prop, None)
        doc.recompute()
    patch.setExpression(prop, None)
    doc.recompute()

    # ---- 4. the transaction boundary: one edit is ONE undo step
    before_undo = doc.UndoCount
    before_names = list(doc.UndoNames)
    with _CaptureConsole() as cap:
        write_band_split(entry, BAND_A, 0.28)
    errors += ["a normal write printed an error: %s" % e for e in cap.errors]
    added = [str(n) for n in doc.UndoNames[:len(doc.UndoNames)
                                           - len(before_names)]]
    if doc.UndoCount - before_undo != 1:
        errors.append("one panel edit moved the undo stack by %d steps "
                      "(expected 1); names added %r"
                      % (doc.UndoCount - before_undo, added))
    if added != ["Silk band split"]:
        errors.append("the edit's undo step is %r, expected ['Silk band "
                      "split']" % (added,))
    delta = consistent("one-undo-step edit")
    if delta is not None:
        checks.append("one panel edit: undo stack +1 ('Silk band split'), "
                      "no console error, corner matches fresh (delta %g)"
                      % delta)
    return {"pass": not errors, "errors": errors, "checks": checks}
