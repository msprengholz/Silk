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
