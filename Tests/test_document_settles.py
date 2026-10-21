"""
Tests/test_document_settles.py -- ticket #125: the document never settles.

THE DEFECT (measured on the cube-corner fixture, before the fix):

    doc.recompute() #0: 0.826 s | still touched: ['B_AB', 'B_BC']
    doc.recompute() #1: 0.820 s | still touched: ['B_AB', 'B_BC']
    doc.recompute() #2: 0.815 s | still touched: ['B_AB', 'B_BC']

Two blends stayed Touched FOREVER, so every document recompute rebuilt
the whole chain (an edge 4 ms, a patch 22 ms, a blend 78 ms, a corner
178 ms).

THE TOUCHER -- named by measurement, not by guess:

  * A patch's execute touches every blend that reads it (the #41
    live-update chain, SilkPatch.Patch._execute).
  * SilkBlend.run_blend FORCED the rebuild of both patches it reads
    (`pa.recompute(); pb.recompute()`), and FreeCAD's single-object
    recompute FORCES the execute even on a clean object -- measured on
    a live object: `obj.recompute()` on an up-to-date object ran its
    execute again and left it Touched.

So every blend re-ran both patches' executes a SECOND time inside the
same document pass, and that second rebuild re-armed the blends that
had ALREADY been rebuilt in that pass. The last blend to run left the
earlier ones Touched, so the pass never settled. (Traced: the patch
execute is what fires the touch, and the touch happens AFTER the
blend's own execute has returned -- which is why purging the flag from
inside the blend's execute could not help.)

THE FIX: the forced rebuild is now conditional
(SilkBlend._patch_needs_rebuild): a DIRTY patch (the user edited a band
edge, an input changed) is rebuilt before the strip reads it, a CLEAN
one is not. The #41 / #109 chain is untouched -- a dirty patch still
touches the blends that read it, and the document pass rebuilds a patch
BEFORE the blends that read it (a blend links to its patches, so the
framework's topological order puts the patch first).

THE GUARD: this module.
  * test_settled_document_recomputes_to_nothing fails when the fix is
    reverted -- the two blends stay Touched and every pass rebuilds.
  * test_band_edit_still_reaches_blend_and_corner fails when the
    settling is bought by breaking the live-update chain.
"""

import time

import FreeCAD

# --- fast tier -----------------------------------------------------------
# This module's subject is an invariant, not an end-to-end rebuild or a
# measurement sweep, so it belongs in the default tier: it is the guard
# against #125 coming back.  See suite.py.
MANUAL = False


def _cube_corner(doc):
    """The 3-patch cube corner with its ring of three blends and the
    3-valent corner blend -- the fixture #125 was measured on."""
    import Tests.cube_corner_model as ccm
    from SilkWorkflowOps import create_corner_blend
    model = ccm.build_cube_corner_model(doc)
    strips = [model["strips"][n] for n in ("B_AB", "B_BC", "B_CA")]
    corner = create_corner_blend(strips)
    doc.recompute()
    return model, corner


def _touched(doc):
    """[(name, state)] of every Touched object in the document."""
    return [(o.Name, list(o.State)) for o in doc.Objects
            if "Touched" in o.State]


def _poles(o):
    return [tuple(p) for p in o.Poles]


def test_a_restored_blend_gets_a_grid_free_shape(doc):
    """A restored blend's Shape must be the SURFACE alone (#108: the
    control grid is a display node, not geometry) -- even when the file
    still carries a pre-#108 Shape with the grid legs in it.

    #125: the framework does NOT necessarily mark a restored blend dirty
    (in the owner's own model seven of the eight came back dirty and
    were rebuilt, and one came back clean), so the stale Shape survived
    the restore -- and then a DISPLAY toggle CHANGED the Shape, which is
    exactly what the grid-is-display-not-geometry contract forbids. The
    restore path now rebuilds the surface from the stored poles.
    """
    errors, checks = [], []
    import os
    import shutil
    import tempfile

    import Part
    from Tests.test_patch_touched import _build_two_patch_pair
    from SilkWorkflowOps import create_blend_by_edge

    scratch = FreeCAD.newDocument("t125_restore")
    active = FreeCAD.ActiveDocument
    FreeCAD.setActiveDocument(scratch.Name)
    tmp = tempfile.mkdtemp(prefix="silk_restore_")
    path = os.path.join(tmp, "restore.FCStd")
    try:
        pa, pb, seam = _build_two_patch_pair(scratch)
        blend = create_blend_by_edge(seam)
        scratch.recompute()
        if blend is None:
            errors.append("the blend was refused")
            return {"pass": False, "errors": errors, "checks": checks}
        legs = list(getattr(blend, "Legs", None) or [])
        if not legs:
            errors.append("the blend carries no Legs, so the pre-#108 "
                          "Shape cannot be fabricated")
            return {"pass": False, "errors": errors, "checks": checks}
        # fabricate the pre-#108 Shape: the surface AND the grid legs
        pieces = [blend.Shape]
        for leg in legs[:4]:
            try:
                pieces.append(Part.LineSegment(leg.StartPoint,
                                               leg.EndPoint).toShape())
            except Exception:
                pass
        blend.Shape = Part.Compound(pieces)
        before = len(blend.Shape.Edges)
        if before <= 4:
            errors.append("the fabricated pre-#108 Shape carries %d edges, "
                          "want more than the surface's 4" % before)
            return {"pass": False, "errors": errors, "checks": checks}
        scratch.saveAs(path)
        FreeCAD.closeDocument(scratch.Name)
        reopened = FreeCAD.openDocument(path)
    except Exception as exc:
        errors.append("the restore path raised: %r" % (exc,))
        return {"pass": False, "errors": errors, "checks": checks}
    finally:
        try:
            if active is not None:
                FreeCAD.setActiveDocument(active.Name)
        except Exception:
            pass
    try:
        objs = [o for o in reopened.Objects
                if getattr(o, "object_type", "") == "Blend"]
        if len(objs) != 1:
            errors.append("the reopened document carries %d blends, want 1"
                          % len(objs))
        for o in objs:
            n_edges = len(o.Shape.Edges) if not o.Shape.isNull() else 0
            if n_edges != 4:
                errors.append("the restored blend carries a %d-edge Shape, "
                              "want the surface's 4 (the grid legs are a "
                              "display node, #108)" % n_edges)
            else:
                checks.append("restored blend: Shape carries %d edges (the "
                              "surface alone), the %d grid legs are still "
                              "in the Legs property"
                              % (n_edges, len(list(o.Legs or []))))
    finally:
        FreeCAD.closeDocument(reopened.Name)
        shutil.rmtree(tmp, ignore_errors=True)
    return {"pass": not errors, "errors": errors, "checks": checks}


def test_settled_document_recomputes_to_nothing(doc):
    """A SETTLED document must recompute to nothing: three consecutive
    document passes, each leaving NOTHING Touched.

    Before the fix the cube corner left two blends Touched after every
    pass, so each pass rebuilt the whole chain (0.83 s).  The structural
    invariant (nothing left Touched) is the assertion; the elapsed time
    is recorded next to it, with a generous ceiling that the pre-fix
    behaviour (3 x 0.8 s) blows through.
    """
    errors, checks = [], []
    model, corner = _cube_corner(doc)

    left = _touched(doc)
    if left:
        errors.append("the freshly built document is already dirty: %s"
                      % left)
    else:
        checks.append("cube corner built clean (3 patches, 3 blends, "
                      "1 corner)")

    times = []
    for i in range(3):
        t0 = time.time()
        doc.recompute()
        dt = time.time() - t0
        times.append(dt)
        left = _touched(doc)
        if left:
            errors.append("pass #%d left %s Touched -- the document does "
                          "not settle" % (i, left))
    if not errors:
        checks.append("3 consecutive passes: %s -- nothing left Touched"
                      % ", ".join("%.3f s" % t for t in times))
        total = sum(times)
        if total > 1.5:
            errors.append("3 settled passes took %.3f s (ceiling 1.5 s) -- "
                          "the chain is being rebuilt for nothing"
                          % total)
        else:
            checks.append("3 settled passes took %.3f s in total"
                          % total)
    return {"pass": not errors, "errors": errors, "checks": checks}


def test_band_edit_still_reaches_blend_and_corner(doc):
    """The #109 live-update chain must survive the settling fix: a
    band-edge edit on a patch must still reach the blends that read it
    AND the corner built from them, and the document must settle right
    after.

    The corner is the proof that the chain is intact end to end: it is
    built from the ring's strips, so it can only move when the strips
    moved.

    WHICH STRIPS READ AN EDGE IS THE CONSTRUCTION'S ANSWER (#128).  The edit
    is made on a patch that carries ONE cut per axis end (`PatchB`), where
    the band edge is still the blend's own setback -- so both of its strips
    must follow.  On the MEMBER patch the rolling construction cut a second
    edge (the leader), and the band's cells start AT the leader, so its
    setback moves the member's cell and the corner and no strip: that is
    measured in the second half rather than asserted away.
    """
    errors, checks = [], []
    model, corner = _cube_corner(doc)
    pB = model["patches"]["PatchB"]
    bAB = model["strips"]["B_AB"]
    bBC = model["strips"]["B_BC"]

    before = {n: _poles(s) for n, s in (("B_AB", bAB), ("B_BC", bBC),
                                        ("Corner", corner))}
    area_before = corner.Shape.Area

    # a user-style band-edge edit on the patch that two ring strips read
    pB.VSplit1 = 0.2
    doc.recompute()

    for name, s in (("B_AB", bAB), ("B_BC", bBC), ("Corner", corner)):
        after = _poles(s)
        moved = sum(1 for a, b in zip(before[name], after) if a != b)
        if not moved:
            errors.append("%s did NOT refresh after the band-edge edit -- "
                          "the live-update chain is broken" % name)
        else:
            checks.append("%s refreshed: %d/%d poles moved"
                          % (name, moved, len(after)))
    if abs(corner.Shape.Area - area_before) < 1e-9:
        errors.append("the corner surface did not change after the edit")
    else:
        checks.append("corner surface rebuilt: area %.6f -> %.6f"
                      % (area_before, corner.Shape.Area))

    left = _touched(doc)
    if left:
        errors.append("document dirty after the edit pass: %s" % left)
    else:
        checks.append("document settles right after the edit")

    # the MEMBER patch's setback reaches the corner the same way (its band's
    # cells start at the leader, so no strip follows it -- reported, not
    # hidden)
    pA = model["patches"]["PatchA"]
    corner_before = _poles(corner)
    area_before = corner.Shape.Area
    strips_before = {n: _poles(s) for n, s in (("B_AB", bAB), ("B_CA",
                                                              model["strips"]["B_CA"]))}
    pA.VSplit1 = 0.15
    doc.recompute()
    corner_moved = sum(1 for a, b in zip(corner_before, _poles(corner))
                       if a != b)
    checks.append("the member patch's setback: the corner moved %d/36 poles, "
                  "area %.6f -> %.6f; the strips' poles moved %s"
                  % (corner_moved, area_before, corner.Shape.Area,
                     {n: sum(1 for a, b in zip(strips_before[n], _poles(s))
                             if a != b)
                      for n, s in (("B_AB", bAB),
                                   ("B_CA", model["strips"]["B_CA"]))}))
    if not corner_moved or abs(corner.Shape.Area - area_before) < 1e-9:
        errors.append("the member patch's own setback did not reach the "
                      "corner -- the member's cell is not being rebuilt")

    # and it stays settled
    for i in range(2):
        doc.recompute()
        left = _touched(doc)
        if left:
            errors.append("pass #%d after the edit re-dirtied: %s"
                          % (i, left))
    if not any("after the edit" in e for e in errors):
        checks.append("document still settled 2 passes after the edit")
    return {"pass": not errors, "errors": errors, "checks": checks}


ALL_TESTS = [
    test_settled_document_recomputes_to_nothing,
    test_band_edit_still_reaches_blend_and_corner,
    test_a_restored_blend_gets_a_grid_free_shape,
]
