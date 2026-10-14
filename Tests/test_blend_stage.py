"""
Blend stage (ticket #20): create_blend op + check_blend oracle (B1-B4).

B1 C0: blend row endpoints sit on the patches' strip-curve endpoints
      (both inner boundaries, all 4 rows, 1e-6)
B2 C1: blend row endpoint tangents match the strip-curve tangents under
      the documented 2x tangent scale (1e-6)
B3:    blend surface valid + no self-intersection + normal field coherent
B4:    full 24-pole match against a provided reference (stored fixture
       blend in the ground-truth test; captured pre-corruption poles in
       the negative test)

Ground-truth test: rebuild the full 7-edge / 2-patch chain from the
fixture's sketches (curved geometry), create the blend, and match the
stored fixture BlendStrip's 24 poles at 1e-6.
"""

import FreeCAD
import os

Vector = FreeCAD.Vector

FIXTURE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..",
                       "Resources", "Test_files", "Silk_Workflow.FCStd")

GT_CHAIN_EDGES = [
    ("E_Top", ["Sketch007", "Sketch008"]),
    ("E_Left", ["Sketch005"]),
    ("E_BtmL", ["Sketch006"]),
    ("E_Shr", ["Sketch"]),
    ("E_BtmR", ["Sketch001"]),
    ("E_CurR", ["Sketch003", "Sketch004"]),
    ("E_TopR", ["Sketch002"]),
]


class _CaptureConsole:
    def __enter__(self):
        import FreeCAD
        self._orig = FreeCAD.Console.PrintError
        self.errors = []
        FreeCAD.Console.PrintError = lambda msg: (
            self.errors.append(msg), self._orig(msg))
        return self

    def __exit__(self, *args):
        FreeCAD.Console.PrintError = self._orig


def _build_gt_chain(doc, fixture_doc):
    """Rebuild all 7 fixture edges + both patches in the test doc.

    Returns (patch_a, patch_b, edges_by_name). `fixture_doc` must be open.
    """
    from Tests.test_patch_stage import _copy_fixture_edge
    from SilkWorkflowOps import create_patch

    edges_by_name = {}
    for edge_name, sketch_names in GT_CHAIN_EDGES:
        e = _copy_fixture_edge(doc, fixture_doc, edge_name, sketch_names)
        edges_by_name.setdefault(edge_name, e)

    g = edges_by_name
    patch_a = create_patch(
        [g["E_Top"], g["E_Left"], g["E_BtmL"], g["E_Shr"]],
        name="PatchA")
    patch_b = create_patch(
        [g["E_Shr"], g["E_BtmR"], g["E_CurR"], g["E_TopR"]],
        name="PatchB")
    return patch_a, patch_b, edges_by_name


def test_create_blend_ground_truth(doc):
    from SilkWorkflowOps import create_blend
    from SilkChecks import check_blend

    fixture = FreeCAD.openDocument(FIXTURE)
    FreeCAD.setActiveDocument(doc.Name)  # openDocument activates the fixture
    try:
        patch_a, patch_b, _ = _build_gt_chain(doc, fixture)
        with _CaptureConsole() as cap:
            blend = create_blend(patch_a, patch_b, name="BlendStrip")

        stored = fixture.BlendStrip.Poles
        if len(stored) != 24:
            errors = [f"fixture blend has {len(stored)} poles, want 24"]
            return {"pass": False, "errors": errors, "checks": []}
        results = check_blend(blend, patch_a, patch_b,
                              reference_poles=stored)
        by = {name: (ok, detail) for name, ok, detail in results}

        errors = []
        errors += [f"console error: {e}" for e in cap.errors]
        if blend.Poles is None or len(blend.Poles) != 24:
            errors.append(f"expected 24 poles, got "
                          f"{0 if blend.Poles is None else len(blend.Poles)}")
        else:
            for name, ok, _ in results:
                if not ok:
                    errors.append(f"check failed: {name} -- {by[name][1]}")
    finally:
        FreeCAD.closeDocument(fixture.Name)
        FreeCAD.setActiveDocument(doc.Name)

    return {"pass": not errors, "errors": errors,
            "checks": [f"{n}: {'ok' if ok else 'FAIL'} ({d})"
                       for n, ok, d in results]}


def test_unblend_restores_the_patches(doc):
    """#70: deleting a FRESHLY created Blend must give both patches their
    band cells back -- and #71 extends it to the band's SPLIT, so an
    unblended patch is a plain patch again.

    The hidden-cell set is re-derived by each blend's execute from the
    blends alive at that moment, but a deleted blend touches nothing and
    recompute() only walks touched objects -- so without a delete hook
    both patches keep the band hole forever.

    **This test exists because the fix shipped green while broken.**
    `Blend` subclasses `BlendStrip` but overrode `__init__` without
    calling super(), so only `BlendStrip.__init__` installed the
    one-shot delete observer. A freshly created blend therefore had NO
    observer and unblend did nothing; a *restored* one did get it via
    the inherited `onDocumentRestored`. Building the blend fresh -- the
    ordinary path, and the one the panel uses -- is precisely what
    exercises the regression.

    #71 reverses #70 on ONE point: #70 kept the band splits so the user's
    width would survive a re-blend, and the human asked for the opposite
    ("unblending does not remove the subgrids, but I think it should do
    so"). The price is stated plainly: the width is discarded, so
    re-blending that seam rebuilds at the DEFAULT (0.1 / 0.9).
    """
    from SilkWorkflowOps import create_blend
    from Tests.test_patch_stage import _copy_fixture_edge  # noqa: F401

    fixture = FreeCAD.openDocument(FIXTURE)
    FreeCAD.setActiveDocument(doc.Name)
    errors, checks = [], []
    try:
        patch_a, patch_b, _ = _build_gt_chain(doc, fixture)
        blend = create_blend(patch_a, patch_b, name="BlendStrip")
        doc.recompute()

        def hidden(p):
            return list(getattr(p, "_HiddenSubgridIdxs", []) or [])

        before_faces = (len(patch_a.Shape.Faces), len(patch_b.Shape.Faces))
        checks.append("blended: hidden=%s faces=%d"
                      % ([hidden(patch_a), hidden(patch_b)], sum(before_faces)))
        if not hidden(patch_a) or not hidden(patch_b):
            errors.append("precondition: a blended patch should have its "
                          "band cells hidden; got %s"
                          % ([hidden(patch_a), hidden(patch_b)],))
        if blend.Proxy._delete_watcher is None:
            errors.append("a FRESHLY created Blend has no delete watcher "
                          "-- unblend cannot work at all")

        doc.removeObject(blend.Name)
        doc.recompute()

        after_faces = (len(patch_a.Shape.Faces), len(patch_b.Shape.Faces))
        checks.append("unblended: hidden=%s faces=%d"
                      % ([hidden(patch_a), hidden(patch_b)], sum(after_faces)))
        if hidden(patch_a) or hidden(patch_b):
            errors.append("after deleting the blend the patches still hide "
                          "their band cells: %s -- a hole is left behind"
                          % ([hidden(patch_a), hidden(patch_b)],))

        # #71: the SEAM's own band split goes with it. #70 deliberately kept
        # it to preserve the user's width; the human asked for the opposite
        # (an unblended patch should look like a plain patch), so the split
        # is removed -- which is why the cell comes back AND the patch goes
        # back to one unsplit surface. The width is the price.
        splits_a = (list(patch_a.USplits), list(patch_a.VSplits))
        splits_b = (list(patch_b.USplits), list(patch_b.VSplits))
        checks.append("splits removed: %s %s" % (splits_a, splits_b))
        if splits_a[0] or splits_a[1] or splits_b[0] or splits_b[1]:
            errors.append("unblend left the band splits behind: %s %s -- the "
                          "patch still renders subdivided"
                          % (splits_a, splits_b))
        cells = (len(patch_a.Proxy._subgrids), len(patch_b.Proxy._subgrids))
        checks.append("subgrids after unblend: %s" % (cells,))
        if cells != (0, 0):
            errors.append("an unblended patch still carries subgrids %s -- it "
                          "renders as a subdivided surface, not a plain one"
                          % (cells,))
        if (len(patch_a.Shape.Faces), len(patch_b.Shape.Faces)) != (1, 1):
            errors.append("an unblended patch is not one whole surface: faces "
                          "%s (a subdivided patch with its band given back "
                          "would show two cells per patch)"
                          % ([len(patch_a.Shape.Faces),
                             len(patch_b.Shape.Faces)],))

        # and re-blending on the same seam must still build -- at the
        # DEFAULT width, because the old one was given back
        again = create_blend(patch_a, patch_b, name="BlendAgain")
        doc.recompute()
        from SilkMachinery import split_at_end
        re_w = (split_at_end(list(patch_a.USplits) or list(patch_a.VSplits), 0),
                split_at_end(list(patch_a.USplits) or list(patch_a.VSplits), 1))
        checks.append("re-blend: poles=%d null=%s splits=%s/%s"
                      % (len(again.Poles or []), again.Shape.isNull(),
                         list(patch_a.USplits), list(patch_a.VSplits)))
        if not list(again.Poles or []) or again.Shape.isNull():
            errors.append("re-blending after an unblend produced nothing")
        if re_w[0] is not None and abs(re_w[0] - 0.1) > 1e-9:
            errors.append("re-blending after an unblend wrote band width %g, "
                          "expected the default 0.1" % re_w[0])
    finally:
        FreeCAD.closeDocument(fixture.Name)
        FreeCAD.setActiveDocument(doc.Name)

    return {"pass": not errors, "errors": errors, "checks": checks}


def test_unblend_removes_only_the_seams_own_split(doc):
    """#71: on a patch carrying SEVERAL splits, unblending one seam removes
    that seam's split and NOTHING else.

    A patch can carry up to four splits (one per side) and meet several
    seams, so "remove the splits" would be wrong -- it would take a
    surviving seam's band boundary with it and leave that blend feeding
    cells that no longer exist. The rule is per (patch, boundary side):
    the dying blend's OWN seam is re-resolved the way run_blend resolved
    it (pinned Edge, else auto-detect), and exactly the split that seam
    owned is dropped.

    The tube fixture is the case that makes the rule necessary: two
    patches sharing TWO edges, so each patch carries two splits from two
    different seams, and the auto-detect alone cannot say which seam a
    blend took (it returns the first matching corner pair for both).
    """
    from SilkWorkflowOps import create_blend_by_edge
    from SilkMachinery import patch_side
    from Tests.test_seam_resolver import _build_tube

    errors, checks = [], []
    pa, pb, s_left, s_right = _build_tube(doc)

    left = create_blend_by_edge(s_left, name="BlendLeft")
    doc.recompute()
    right = create_blend_by_edge(s_right, name="BlendRight")
    doc.recompute()
    if not (list(left.Poles or []) and list(right.Poles or [])):
        return {"pass": False, "checks": checks,
                "errors": ["fixture: the two-seam pair did not blend "
                           "(left %d poles, right %d)"
                           % (len(left.Poles or []), len(right.Poles or []))]}
    before = {p.Name: (list(p.USplits), list(p.VSplits)) for p in (pa, pb)}
    checks.append("blended: %s" % before)
    for p in (pa, pb):
        if len([v for pair in before[p.Name] for v in pair]) != 2:
            errors.append("fixture: %s carries %r, expected one split per "
                          "seam" % (p.Name, before[p.Name]))

    # -- unblend ONE seam: its split goes, the other seam's stays --------
    right_edge = right.Edge.Name
    doc.removeObject(right.Name)
    doc.recompute()
    after = {p.Name: (list(p.USplits), list(p.VSplits)) for p in (pa, pb)}
    checks.append("after unblending %s: %s" % (right_edge, after))
    # the dying seam's band split is the HIGH one on both patches (the
    # right side is the parametric-1 end of that axis), the left seam's
    # is the LOW one -- so "the unblend took the wrong seam's split" is
    # exactly "the wrong one of the two survived"
    for p in (pa, pb):
        kept = [v for pair in after[p.Name] for v in pair]
        if len(kept) != 1:
            errors.append("unblending one seam left %d split(s) on %s (%r), "
                          "expected only the other seam's"
                          % (len(kept), p.Name, after[p.Name]))
        elif abs(kept[0] - 0.1) > 1e-9:
            errors.append("the surviving split on %s is %g, expected the LEFT "
                          "seam's 0.1 -- the unblend took the WRONG seam's "
                          "split (%r)" % (p.Name, kept[0], after[p.Name]))
        # the surviving blend is untouched and still hides its own cells
        hidden = list(getattr(p, "_HiddenSubgridIdxs", []) or [])
        if not hidden:
            errors.append("%s hid no cells after the other seam's blend was "
                          "deleted -- the surviving blend lost its band"
                          % p.Name)
    if not list(left.Poles or []):
        errors.append("the surviving blend lost its poles when the other "
                      "seam's blend was unblended")

    # -- unblend the last one: no splits, no subgrids, whole surfaces -----
    doc.removeObject(left.Name)
    doc.recompute()
    last = {p.Name: (list(p.USplits), list(p.VSplits)) for p in (pa, pb)}
    checks.append("after the last unblend: %s" % last)
    for p in (pa, pb):
        if any(last[p.Name]):
            errors.append("%s still carries splits %r after every blend is "
                          "gone" % (p.Name, last[p.Name]))
        if p.Proxy._subgrids:
            errors.append("%s still builds %d subgrids with no splits"
                          % (p.Name, len(p.Proxy._subgrids)))
        if list(getattr(p, "_HiddenSubgridIdxs", []) or []):
            errors.append("%s still hides cells with no blend alive: %r"
                          % (p.Name, list(p._HiddenSubgridIdxs)))

    # -- and the two-seam pair can be blended again, from the defaults ---
    again_left = create_blend_by_edge(s_left, name="BlendLeft2")
    doc.recompute()
    again_right = create_blend_by_edge(s_right, name="BlendRight2")
    doc.recompute()
    checks.append("re-blended both: %d / %d poles"
                  % (len(again_left.Poles or []), len(again_right.Poles or [])))
    for name, blend in (("left", again_left), ("right", again_right)):
        if not list(blend.Poles or []) or blend.Shape.isNull():
            errors.append("re-blending the %s seam after two unblends built "
                          "nothing" % name)
    return {"pass": not errors, "errors": errors, "checks": checks}


def test_unblend_clears_the_users_own_band_split(doc):
    """#71, second reversal: a split the USER wrote goes with the band.

    #71 first removed only the value the blend had written, filtering by
    value, which left a width the user had set themselves sitting on the
    patch: an unblended patch that still renders subdivided. Measured
    before the change:

        set VSplits=[0.35] by hand -> blend -> unblend
            => VSplits=[0.35] remains, 2 subgrids

    The human's reason is that in the wizard the Band A / Band B editors
    ARE the patch's USplits / VSplits property -- they are equivalent and
    there is no other data the patch can hold -- so unsetting the blend
    must unset them too.

    The axis under test is DERIVED from the seam, not hardcoded, so this
    asserts the rule on whichever axis the seam actually bands (the
    ground-truth chain's seam runs along U, so it bands VSplits -- but the
    test says so because it measured it).

    TWO splits are placed on that axis, and BOTH must go:

      * the USER's own width, AT the seam's end -- the exact shape #71's
        value filter already handled, so it alone would not tell the two
        rules apart;
      * a second split at the OTHER end that no blend reads -- the shape
        that survives #71's filter and leaves the patch still subdivided,
        which is what the human is complaining about. (`band_cells` picks
        the band on the band's OWN axis and drops corner cells on the
        other one, so an extra end on the band axis costs the blend
        nothing -- the fixture still builds.)"""
    from SilkWorkflowOps import create_blend
    from Tests.test_seam_resolver import _Capture

    fixture = FreeCAD.openDocument(FIXTURE)
    FreeCAD.setActiveDocument(doc.Name)
    errors, checks = [], []
    try:
        patch_a, patch_b, _ = _build_gt_chain(doc, fixture)
        doc.recompute()

        # which axis does this seam band, and at which end?
        from SilkMachinery import patch_side
        etype, ss = patch_side(patch_a, patch_b, 0.01)
        if etype is None:
            return {"pass": False, "errors": ["fixture: the chain's seam did "
                                              "not resolve"], "checks": checks}
        prop = "VSplits" if etype[0] == "U" else "USplits"
        width = 0.35 if ss == 0 else 0.65        # the user's own width ...
        spare = 0.65 if ss == 0 else 0.35       # ... and an end nobody reads
        setattr(patch_a, prop, sorted([width, spare]))
        patch_a.recompute()
        doc.recompute()
        checks.append("user splits: %s.%s=%r (seam %s, end %d)"
                      % (patch_a.Name, prop, list(getattr(patch_a, prop)),
                         etype, ss))

        with _Capture() as cap:
            blend = create_blend(patch_a, patch_b, name="BlendUser")
        doc.recompute()
        errors += ["console error: %s" % e for e in cap.errors]
        # the blend READS the user's width (#64) and adds nothing
        if [round(float(v), 9) for v in getattr(patch_a, prop)] \
                != sorted([width, spare]):
            errors.append("the blend moved the user's own splits %s.%s: %r "
                          "(want %r) -- the fixture does not exercise the "
                          "case" % (patch_a.Name, prop,
                                    list(getattr(patch_a, prop)),
                                    sorted([width, spare])))
        if not list(blend.Poles or []):
            return {"pass": False,
                    "errors": errors + ["fixture: the blend built nothing"],
                    "checks": checks}

        doc.removeObject(blend.Name)
        doc.recompute()

        left = list(getattr(patch_a, prop))
        cells = len(patch_a.Proxy._subgrids)
        checks.append("after unblend: %s.%s=%r subgrids=%d faces=%d"
                      % (patch_a.Name, prop, left, cells,
                         len(patch_a.Shape.Faces)))
        if left:
            errors.append("unblending a seam left the USER's own split on %s: "
                          "%s.%s=%r -- it still renders subdivided"
                          % (patch_a.Name, patch_a.Name, prop, left))
        if cells:
            errors.append("%s still builds %d subgrids with %s=%r"
                          % (patch_a.Name, cells, prop, left))
        if len(patch_a.Shape.Faces) != 1:
            errors.append("%s is not one whole surface after the unblend: "
                          "%d faces" % (patch_a.Name,
                                        len(patch_a.Shape.Faces)))
        if list(getattr(patch_a, "_HiddenSubgridIdxs", []) or []):
            errors.append("%s still hides band cells: %r"
                          % (patch_a.Name, list(patch_a._HiddenSubgridIdxs)))

        # and the seam can be blended again, at the DEFAULT width
        again = create_blend(patch_a, patch_b, name="BlendUserAgain")
        doc.recompute()
        checks.append("re-blend: %s.%s=%r poles=%d"
                      % (patch_a.Name, prop, list(getattr(patch_a, prop)),
                         len(again.Poles or [])))
        if not list(again.Poles or []) or again.Shape.isNull():
            errors.append("re-blending after the unblend produced nothing")
        else:
            default = 0.1 if ss == 0 else 0.9
            from SilkMachinery import split_at_end
            got = split_at_end(list(getattr(patch_a, prop)), ss)
            if got is None or abs(got - default) > 1e-9:
                errors.append("re-blending rebuilt the band at %r, expected "
                              "the default %g -- the user's width %g came "
                              "back" % (got, default, width))
    finally:
        FreeCAD.closeDocument(fixture.Name)
        FreeCAD.setActiveDocument(doc.Name)

    return {"pass": not errors, "errors": errors, "checks": checks}


def test_unblend_keeps_the_split_a_surviving_blend_needs(doc):
    """The one thing that survives the axis-wide clear: a split another
    blend is still feeding on.

    A patch can be bounded by TWO seams on the same axis -- the tube's
    TubeA carries one split per seam (both on USplits, one at each end),
    and so does a four-patch corner patch. Unblending ONE of them must not
    strip the split the SURVIVING blend needs, or that blend silently
    loses its band and feeds on cells that no longer exist.

    The kept value is read back from the SURVIVING blend's own seam side
    (through the same `_band_split_of` mapping the writer uses) rather
    than hardcoded to 0.1, so this also pins the case where the surviving
    seam's width is the USER's (see the second half: the survivor's own
    end is set to 0.2 by hand, and 0.2 must be what comes back)."""
    from SilkWorkflowOps import create_blend_by_edge
    from SilkBlend import _band_split_of, _side_on
    from Tests.test_seam_resolver import _build_tube

    errors, checks = [], []
    pa, pb, s_left, s_right = _build_tube(doc)

    left = create_blend_by_edge(s_left, name="BlendLeft")
    doc.recompute()
    right = create_blend_by_edge(s_right, name="BlendRight")
    doc.recompute()
    if not (list(left.Poles or []) and list(right.Poles or [])):
        return {"pass": False, "checks": checks,
                "errors": ["fixture: the two-seam pair did not blend "
                           "(left %d poles, right %d)"
                           % (len(left.Poles or []), len(right.Poles or []))]}

    # the split the SURVIVING blend is built on, read from its own seam
    keep_prop, keep_ss = _band_split_of(_side_on(left, pa))
    dropped_prop, _ = _band_split_of(_side_on(right, pa))
    if keep_prop != dropped_prop:
        return {"pass": False, "checks": checks,
                "errors": ["fixture: the two seams band DIFFERENT axes on "
                           "%s (%s vs %s) -- this test needs them on one"
                           % (pa.Name, keep_prop, dropped_prop)]}
    # a user width on the survivor's own end, so "0.1 came back" cannot
    # pass by accident on the default
    user = 0.2 if keep_ss == 0 else 0.8
    from SilkMachinery import split_at_end
    cur = list(getattr(pa, keep_prop))
    old = split_at_end(cur, keep_ss)
    setattr(pa, keep_prop,
            sorted([v for v in cur if old is None or v != old] + [user]))
    pa.recompute()
    doc.recompute()
    checks.append("two seams on %s.%s: %r (survivor's own width set to %g)"
                  % (pa.Name, keep_prop, list(getattr(pa, keep_prop)), user))

    doc.removeObject(right.Name)
    doc.recompute()

    for p in (pa, pb):
        kept = list(getattr(p, keep_prop))
        checks.append("after unblending the right seam: %s.%s=%r"
                      % (p.Name, keep_prop, kept))
        prop_p, ss_p = _band_split_of(_side_on(left, p))
        if prop_p != keep_prop:
            continue
        want = user if ss_p == keep_ss else None
        if want is None:
            errors.append("%s: the surviving blend's seam resolved to end %r, "
                          "the width was set at end %d" % (p.Name, ss_p,
                                                            keep_ss))
        elif len(kept) != 1 or abs(kept[0] - want) > 1e-9:
            errors.append("%s.%s=%r after unblending the OTHER seam -- the "
                          "surviving blend's band split %g did not survive "
                          "(it must be the one split the surviving blend "
                          "reads)" % (p.Name, keep_prop, kept, want))
        hidden = list(getattr(p, "_HiddenSubgridIdxs", []) or [])
        if not hidden:
            errors.append("%s hides no cells after the other seam's blend "
                          "was deleted -- the surviving blend lost its band"
                          % p.Name)
        if not p.Proxy._subgrids:
            errors.append("%s builds no subgrids at all, so the surviving "
                          "blend has nothing to feed on" % p.Name)

    if not list(left.Poles or []):
        errors.append("the surviving blend lost its poles when the other "
                      "seam's blend was unblended")
    from SilkChecks import check_blend
    bad = [(n, d) for n, ok, d in check_blend(left, pa, pb, edge=left.Edge)
           if not ok]
    if bad:
        errors.append("the oracle flagged the surviving blend after the "
                      "unblend: %s" % bad)

    # the axis is not "cleared" in a way that takes the survivor's split
    # with it a moment later: unblending the survivor too leaves nothing
    doc.removeObject(left.Name)
    doc.recompute()
    last = {p.Name: (list(p.USplits), list(p.VSplits)) for p in (pa, pb)}
    checks.append("after the last unblend: %s" % (last,))
    for p in (pa, pb):
        if any(last[p.Name]):
            errors.append("%s still carries splits %r with no blend alive"
                          % (p.Name, last[p.Name]))
    return {"pass": not errors, "errors": errors, "checks": checks}


def test_unblend_with_no_user_split_leaves_a_plain_patch(doc):
    """The plain case, on a second fixture: the band axis carried ONLY
    what the blend wrote, and unblending empties it completely -- no
    splits, no subgrids, one whole face, no hidden cells -- with the
    patch itself still oracle-green.

    (test_unblend_restores_the_patches asserts this on the curved
    ground-truth chain; this one is straight-edged and adds the oracle,
    so the "plain patch" claim is checked against geometry and not only
    against the split lists.)"""
    from SilkChecks import check_patch
    from SilkWorkflowOps import create_blend
    from Tests.test_seam_resolver import _square_patch, _patch_sharing

    errors, checks = [], []
    a = _square_patch(doc, "PlainA")
    ea = a.Edges[0]
    b = _patch_sharing(doc, ea, "PlainB")
    doc.recompute()

    blend = create_blend(a, b, name="PlainBlend")
    doc.recompute()
    if not list(blend.Poles or []):
        return {"pass": False, "checks": checks,
                "errors": ["fixture: the blend built nothing"]}
    before = {p.Name: (list(p.USplits), list(p.VSplits)) for p in (a, b)}
    checks.append("blended: %s" % before)
    if not any(v for pair in before.values() for v in [pair[0], pair[1]]):
        errors.append("fixture: the blend wrote no band split at all (%r), so "
                      "there is nothing for this test to clear" % before)

    doc.removeObject(blend.Name)
    doc.recompute()

    for p in (a, b):
        after = (list(p.USplits), list(p.VSplits))
        cells = len(p.Proxy._subgrids)
        checks.append("after unblend: %s splits=%r subgrids=%d faces=%d"
                      % (p.Name, after, cells, len(p.Shape.Faces)))
        if any(after[0]) or any(after[1]):
            errors.append("%s still carries splits %r after the unblend"
                          % (p.Name, after))
        if cells:
            errors.append("%s still builds %d subgrids with no splits"
                          % (p.Name, cells))
        if len(p.Shape.Faces) != 1:
            errors.append("%s is not one whole surface: %d faces"
                          % (p.Name, len(p.Shape.Faces)))
        if list(getattr(p, "_HiddenSubgridIdxs", []) or []):
            errors.append("%s still hides band cells: %r"
                          % (p.Name, list(p._HiddenSubgridIdxs)))
        bad = [(n, d) for n, ok, d in check_patch(p, list(p.Edges)) if not ok]
        if bad:
            errors.append("the oracle flagged the unblended %s: %s"
                          % (p.Name, bad))
    return {"pass": not errors, "errors": errors, "checks": checks}


def _blend_corrupted(doc, fixture, pole_idx, delta):
    """Build the GT blend, then corrupt one stored pole by `delta`."""
    from SilkWorkflowOps import create_blend
    patch_a, patch_b, _ = _build_gt_chain(doc, fixture)
    blend = create_blend(patch_a, patch_b, name="BlendStrip")
    poles = list(blend.Poles)
    poles[pole_idx] = poles[pole_idx] + delta
    blend.Poles = poles
    return blend, patch_a, patch_b


def test_oracle_flags_seam_offset(doc):
    """B1 must fail: a row's left endpoint (C0 seam pole) shifted 0.5."""
    from SilkChecks import check_blend

    fixture = FreeCAD.openDocument(FIXTURE)
    FreeCAD.setActiveDocument(doc.Name)  # openDocument activates the fixture
    try:
        blend, pa, pb = _blend_corrupted(doc, fixture, 0, Vector(0.5, 0, 0))
        results = check_blend(blend, pa, pb)
        failed = [n for n, ok, _ in results if not ok]
        if any(n.startswith("B1") for n in failed):
            return {"pass": True, "errors": [],
                    "checks": [f"{n}: {'ok' if ok else 'FAIL'}"
                               for n, ok, _ in results]}
        return {"pass": False,
                "errors": [f"seam offset: expected B1 failure, got {failed}"],
                "checks": [f"{n}: {'ok' if ok else 'FAIL'}"
                           for n, ok, _ in results]}
    finally:
        FreeCAD.closeDocument(fixture.Name)
        FreeCAD.setActiveDocument(doc.Name)


def test_oracle_flags_tangent_break(doc):
    """B2 must fail: a row's first tangent pole shifted 0.5 (B1 stays green)."""
    from SilkChecks import check_blend

    fixture = FreeCAD.openDocument(FIXTURE)
    FreeCAD.setActiveDocument(doc.Name)  # openDocument activates the fixture
    try:
        blend, pa, pb = _blend_corrupted(doc, fixture, 1, Vector(0, 0.5, 0))
        results = check_blend(blend, pa, pb)
        failed = [n for n, ok, _ in results if not ok]
        if any(n.startswith("B2") for n in failed):
            return {"pass": True, "errors": [],
                    "checks": [f"{n}: {'ok' if ok else 'FAIL'}"
                               for n, ok, _ in results]}
        return {"pass": False,
                "errors": [f"tangent break: expected B2 failure, got {failed}"],
                "checks": [f"{n}: {'ok' if ok else 'FAIL'}"
                           for n, ok, _ in results]}
    finally:
        FreeCAD.closeDocument(fixture.Name)
        FreeCAD.setActiveDocument(doc.Name)


def test_oracle_flags_interior_pole(doc):
    """B4 must fail: an interior pole shifted 0.5, reference = clean poles."""
    from SilkChecks import check_blend

    fixture = FreeCAD.openDocument(FIXTURE)
    FreeCAD.setActiveDocument(doc.Name)  # openDocument activates the fixture
    try:
        blend, pa, pb = _blend_corrupted(doc, fixture, 14, Vector(0, 0, 0.5))
        # reference = stored fixture blend poles (plain vectors, cross-doc ok)
        stored = fixture.BlendStrip.Poles
        results = check_blend(blend, pa, pb, reference_poles=stored)
        failed = [n for n, ok, _ in results if not ok]
        if "B4_pole_match" in failed:
            return {"pass": True, "errors": [],
                    "checks": [f"{n}: {'ok' if ok else 'FAIL'}"
                               for n, ok, _ in results]}
        return {"pass": False,
                "errors": [f"interior pole: expected B4 failure, got {failed}"],
                "checks": [f"{n}: {'ok' if ok else 'FAIL'}"
                           for n, ok, _ in results]}
    finally:
        FreeCAD.closeDocument(fixture.Name)
        FreeCAD.setActiveDocument(doc.Name)


ALL_TESTS = [
    test_create_blend_ground_truth,
    test_unblend_restores_the_patches,
    test_unblend_removes_only_the_seams_own_split,
    test_unblend_clears_the_users_own_band_split,
    test_unblend_keeps_the_split_a_surviving_blend_needs,
    test_unblend_with_no_user_split_leaves_a_plain_patch,
    test_oracle_flags_seam_offset,
    test_oracle_flags_tangent_break,
    test_oracle_flags_interior_pole,
]
