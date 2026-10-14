"""
Which side of a patch a SEAM is on, when the pair shares TWO seams (#83).

`SilkMachinery.patch_side(pa, pb)` answers "which side does pa present to
pb" from the patch PAIR alone, and on a pair sharing two edges it returns
the FIRST matching corner pair every time -- the same answer for both
seams. Every reader that re-derived a side from the pair therefore got
one seam's answer while the blend's writer (`ensure_band_split`, through
`_resolve_seam`, which honours the pinned Edge) put the band somewhere
else. Three symptoms, one cause:

  1. the panel's band editor targets the wrong property (#83's report:
     "when I set Band A, vsplit1 is also changed along with usplit1");
  2. `SilkBlend._linked_band_cells` computes a SIBLING blend's band from
     the wrong side, so the auto-hide full set loses the first blend's
     cell ("cell 0 LOST");
  3. one patch is reduced to a single visible cell, which with
     ShowSubgrids reads as "the curved patch disappeared, showing only
     its control grid".

The fixture is the two-seam tube (`Tests.test_seam_resolver._build_tube`):
a flat square panel (TubeA) and an arched panel (TubeB) over the same
footprint sharing TubeA's LEFT and RIGHT edges. Its two seams land on
DIFFERENT sides of each patch, which is what makes the ambiguity
visible: `patch_side(TubeA, TubeB)` and `patch_side(TubeB, TubeA)` both
return ('U0', 0), and that side is neither seam.

Every assertion here is anchored on ground truth that does not come from
the resolver under test: what the blend WROTE is read back off the
patch's four band-edge properties, and what is visible is read off the
patch OBJECT's `_HiddenSubgridIdxs` (which lives on the object, not on
the proxy -- reading `Proxy._HiddenSubgridIdxs` silently returns
nothing and looks like "auto-hide never runs").
"""

import FreeCAD

from Tests.test_seam_resolver import _build_tube, _splits, _fmt_splits, \
    _Capture, NO_BAND


def _entries(doc):
    """seam_inventory keyed by edge name."""
    from SilkWorkflowOps import seam_inventory
    return {e["edge"].Name: e for e in seam_inventory(doc)}


def _band_props(p):
    """The names of the band-edge properties this patch really carries --
    i.e. the ones holding a position strictly inside (0, 1), which is
    exactly the set the blend's writer touched."""
    from SilkMachinery import band_edge
    out = set()
    for letter in ("U", "V"):
        for end, sentinel in ((1, 0.0), (2, 1.0)):
            name = "%sSplit%d" % (letter, end)
            if band_edge(getattr(p, name, sentinel)) is not None:
                out.add(name)
    return out


def _hidden(p):
    """The auto-hidden subgrid cell indices, read off the OBJECT (see the
    module docstring -- this is the measurement trap)."""
    return set(getattr(p, "_HiddenSubgridIdxs", []) or [])


def _visible(p):
    n = len(getattr(p.Proxy, "_subgrids", []) or [])
    return n - len(_hidden(p))


# ---- the panel's band editor must name the seam's own property -----------

def test_two_seam_band_editor_names_each_seams_own_property(doc):
    """The four (seam, patch) combinations each name the property the
    blend ACTUALLY wrote.

    Blended RIGHT first (its band edges are the only non-sentinel ones
    right after, so the ground truth is unambiguous), then LEFT. Each
    seam's read_band_split must name the property holding the seam's own
    band edge, on BOTH patches -- never the other seam's, and never a
    sentinel. Reading the RIGHT seam again after the LEFT blend exists
    pins that adding a second seam does not move the first one's editor.
    """
    from SilkTaskPanel import read_band_split, BAND_A, BAND_B

    pa, pb, s_left, s_right = _build_tube(doc)
    errors, checks = [], []

    # ---- seam RIGHT, alone ------------------------------------------
    from SilkWorkflowOps import create_blend_by_edge
    with _Capture() as cap:
        create_blend_by_edge(s_right, name="BlendRight")
    errors += ["console error: %s" % e for e in cap.errors]

    want_right_a = _band_props(pa)
    want_right_b = _band_props(pb)
    # The blend wrote exactly one end on each patch; assert that so the
    # rest of the test cannot pass on an empty ground truth.
    if len(want_right_a) != 1 or len(want_right_b) != 1:
        errors.append("right-seam blend did not write exactly one band "
                      "edge per patch: A=%s B=%s"
                      % (sorted(want_right_a), sorted(want_right_b)))
        return {"pass": False, "errors": errors, "checks": checks}

    ent = _entries(doc)[s_right.Name]
    read = read_band_split(ent)
    if read is None:
        errors.append("read_band_split returned None on the right seam")
        return {"pass": False, "errors": errors, "checks": checks}
    pa_prop, pa_ss, pa_w = read[0], read[1], read[2]
    pb_prop, pb_ss, pb_w = read[3], read[4], read[5]
    if pa_prop != next(iter(want_right_a)):
        errors.append("right seam: band A editor targets %s, but the blend "
                      "wrote %s" % (pa_prop, sorted(want_right_a)))
    if pb_prop != next(iter(want_right_b)):
        errors.append("right seam: band B editor targets %s, but the blend "
                      "wrote %s" % (pb_prop, sorted(want_right_b)))
    checks.append("right seam (alone): editor -> A.%s B.%s, blend wrote "
                  "A.%s B.%s"
                  % (pa_prop, pb_prop, sorted(want_right_a),
                     sorted(want_right_b)))
    # The right seam is V1 on A / U1 on B, so its bands live on A's U axis
    # at the parametric-1 end and B's V axis at the parametric-1 end.
    if (pa_prop, pa_ss, pb_prop, pb_ss) != ("USplit2", 1, "VSplit2", 1):
        errors.append("right seam: (A%s/%s, B%s/%s), want "
                      "(USplit2/1, VSplit2/1) -- the seam runs along V on "
                      "A and along U on B, so both bands are on the "
                      "parametric-1 end"
                      % (pa_prop, pa_ss, pb_prop, pb_ss))
    checks.append("right seam: A.%s end %d / B.%s end %d"
                  % (pa_prop, pa_ss, pb_prop, pb_ss))

    # ---- seam LEFT, on top of it -----------------------------------
    with _Capture() as cap:
        create_blend_by_edge(s_left, name="BlendLeft")
    errors += ["console error: %s" % e for e in cap.errors]

    ent_left = _entries(doc)[s_left.Name]
    read_l = read_band_split(ent_left)
    if read_l is None:
        errors.append("read_band_split returned None on the left seam")
        return {"pass": False, "errors": errors, "checks": checks}
    la_prop, la_ss, la_w = read_l[0], read_l[1], read_l[2]
    lb_prop, lb_ss, lb_w = read_l[3], read_l[4], read_l[5]
    # The left seam is V0 on A / U0 on B -> A.USplit1 / B.VSplit1.
    if (la_prop, la_ss, lb_prop, lb_ss) != ("USplit1", 0, "VSplit1", 0):
        errors.append("left seam: (A%s/%s, B%s/%s), want "
                      "(USplit1/0, VSplit1/0)"
                      % (la_prop, la_ss, lb_prop, lb_ss))
    checks.append("left seam: A.%s end %d / B.%s end %d"
                  % (la_prop, la_ss, lb_prop, lb_ss))

    # Both seams' editors must now name two DIFFERENT properties per patch,
    # and together cover both edges the blend wrote.
    if la_prop == pa_prop or lb_prop == pb_prop:
        errors.append("the two seams name the same property on a patch "
                      "(A: %s/%s, B: %s/%s)"
                      % (la_prop, pa_prop, lb_prop, pb_prop))
    both_a, both_b = _band_props(pa), _band_props(pb)
    if {la_prop, pa_prop} != both_a or {lb_prop, pb_prop} != both_b:
        errors.append("the two seams' editors cover %s/%s but the patches "
                      "carry %s/%s"
                      % (sorted({la_prop, pa_prop}), sorted({lb_prop, pb_prop}),
                         sorted(both_a), sorted(both_b)))
    checks.append("both seams together cover every band edge written: "
                  "A=%s B=%s" % (sorted(both_a), sorted(both_b)))

    # Adding the second seam did not move the first seam's editor.
    read_r2 = read_band_split(_entries(doc)[s_right.Name])
    if read_r2[0] != pa_prop or read_r2[3] != pb_prop:
        errors.append("after the left blend the RIGHT seam's editor moved "
                      "from A.%s/B.%s to A.%s/B.%s"
                      % (pa_prop, pb_prop, read_r2[0], read_r2[3]))
    checks.append("right seam's editor unchanged after the left blend "
                  "(A.%s B.%s)" % (read_r2[0], read_r2[3]))

    # Each editor reads its own band's real width, not a default.
    if abs(pa_w - 0.1) > 1e-9 or abs(pb_w - 0.1) > 1e-9:
        errors.append("right seam widths read %g/%g, want 0.1/0.1 (the "
                      "defaults the blend wrote)" % (pa_w, pb_w))
    if abs(la_w - 0.1) > 1e-9 or abs(lb_w - 0.1) > 1e-9:
        errors.append("left seam widths read %g/%g, want 0.1/0.1" % (la_w,
                                                                      lb_w))
    checks.append("all four editors read the real 0.1 width")
    return {"pass": not errors, "errors": errors, "checks": checks}


def test_two_seam_band_write_touches_only_its_own_property(doc):
    """A width typed on one seam lands on that seam's own band edge and
    disturbs nothing else -- the human's "when I set Band A, usplit1 is
    also changed along with vsplit1".

    Typing on the LEFT seam's Band A must move A.USplit1 only; the right
    seam's band (A.USplit2) and every edge on B must be bit-identical
    afterwards. This is checked on the raw property values, not through
    the panel's own read, so a reader that lies cannot hide a bad write.
    """
    from SilkWorkflowOps import create_blend_by_edge
    from SilkTaskPanel import write_band_split, BAND_A, _stored_from_width

    pa, pb, s_left, s_right = _build_tube(doc)
    errors, checks = [], []
    with _Capture() as cap:
        create_blend_by_edge(s_right, name="BlendRight")
        create_blend_by_edge(s_left, name="BlendLeft")
    errors += ["console error: %s" % e for e in cap.errors]

    before = {n: float(getattr(pa, n)) for n in
              ("USplit1", "USplit2", "VSplit1", "VSplit2")}
    before_b = {n: float(getattr(pb, n)) for n in
                ("USplit1", "USplit2", "VSplit1", "VSplit2")}

    ent = _entries(doc)[s_left.Name]
    ok = write_band_split(ent, BAND_A, 0.25)
    errors += ["console error: %s" % e for e in cap.errors]
    if not ok:
        errors.append("write_band_split refused a legal width on the left "
                      "seam's band A")

    after = {n: float(getattr(pa, n)) for n in before}
    after_b = {n: float(getattr(pb, n)) for n in before_b}
    want = 0.25                      # the 0-end stores the width as-is
    if abs(after["USplit1"] - want) > 1e-9:
        errors.append("typing 0.25 on the left seam's band A left "
                      "TubeA.USplit1 at %g, want %g -- it was written to %r"
                      % (after["USplit1"], want,
                         [k for k, v in after.items()
                          if abs(v - want) < 1e-9
                          and abs(before[k] - want) >= 1e-9]))
    for n in ("USplit2", "VSplit1", "VSplit2"):
        if abs(after[n] - before[n]) > 1e-9:
            errors.append("typing on the left seam's band A moved "
                          "TubeA.%s from %g to %g" % (n, before[n], after[n]))
    for n in before_b:
        if abs(after_b[n] - before_b[n]) > 1e-9:
            errors.append("typing on the left seam's band A moved "
                          "TubeB.%s from %g to %g" % (n, before_b[n],
                                                       after_b[n]))
    checks.append("width 0.25 on the left seam's band A: TubeA %s (was %s), "
                  "TubeB untouched"
                  % ("/".join("%g" % after[n] for n in
                              ("USplit1", "USplit2", "VSplit1", "VSplit2")),
                     "/".join("%g" % before[n] for n in
                              ("USplit1", "USplit2", "VSplit1", "VSplit2"))))

    # And the 1-end converts the width the other way round (#70), still on
    # its own property only.
    ent_r = _entries(doc)[s_right.Name]
    ok = write_band_split(ent_r, BAND_A, 0.3)
    errors += ["console error: %s" % e for e in cap.errors]
    if not ok:
        errors.append("write_band_split refused a legal width on the right "
                      "seam's band A")
    got = float(getattr(pa, "USplit2"))
    if abs(got - 0.7) > 1e-9:
        errors.append("a width of 0.3 typed at the 1-end stored %g on "
                      "TubeA.USplit2, want 1 - 0.3 = 0.7" % got)
    checks.append("width 0.3 on the right seam's band A -> TubeA.USplit2 = %g"
                  % got)
    if abs(float(getattr(pa, "USplit1")) - want) > 1e-9:
        errors.append("writing the right seam's band moved TubeA.USplit1")
    return {"pass": not errors, "errors": errors, "checks": checks}


# ---- the auto-hide "full set" must not lose a sibling blend's cell -------

def test_two_seam_auto_hide_keeps_both_band_cells(doc):
    """Creating the SECOND blend must not un-hide the FIRST one's band
    cell, and after both blends each patch's visible cell is the
    INTERIOR one, not a sliver at one seam.

    `_linked_band_cells` re-derives the auto-hide set for a patch from
    every OTHER blend linked to it. Deriving a sibling's band from the
    patch PAIR (`patch_side`) returns the same side for both seams, so
    the sibling contributed one (wrong) cell and the union came out
    {own cell, middle cell} -- the FIRST blend's own cell never reappeared
    and the patch was left showing a thin end sliver instead of its
    body. That is the human's "the curved patch disappears, showing only
    its control grid".

    Cell arithmetic on this fixture (the only honest reading, since the
    two seams sit at OPPOSITE ends of the same axis on each patch): the
    band's axis carries one edge per end -> 3 intervals, and the
    seam-parallel axis carries none -> 1. So a patch has 3 cells and the
    two seams' bands are the first and the last of them, leaving exactly
    ONE visible cell -- the interior one, [0.1, 0.9], which is the body
    of the panel and of the arch. A "more than one visible cell"
    expectation cannot hold here and is NOT asserted; what must hold is
    that the visible cell is the interior one and that it is visible at
    all (see the report).
    """
    from SilkWorkflowOps import create_blend_by_edge

    pa, pb, s_left, s_right = _build_tube(doc)
    errors, checks = [], []

    with _Capture() as cap:
        create_blend_by_edge(s_right, name="BlendRight")
    errors += ["console error: %s" % e for e in cap.errors]

    # Right seam ALONE: one band edge, at the parametric-1 end, so the
    # band's axis has 2 intervals and the band is the last cell.
    for p in (pa, pb):
        n = len(getattr(p.Proxy, "_subgrids", []) or [])
        if n != 2 or _hidden(p) != {1} or _visible(p) != 1:
            errors.append("after the RIGHT seam alone %s has %d cells, "
                          "hidden %s, %d visible -- want 2 cells, hidden "
                          "{1} (the last interval of its U axis)"
                          % (p.Name, n, sorted(_hidden(p)), _visible(p)))
        checks.append("after RIGHT only: %s %d cells, hidden=%s, %d visible"
                      % (p.Name, n, sorted(_hidden(p)), _visible(p)))

    with _Capture() as cap:
        create_blend_by_edge(s_left, name="BlendLeft")
    errors += ["console error: %s" % e for e in cap.errors]

    for tag, p in (("after BOTH", pa), ("after BOTH", pb)):
        n_cells = len(getattr(p.Proxy, "_subgrids", []) or [])
        hid, vis = _hidden(p), _visible(p)
        checks.append("%s: %s %d cells, hidden=%s, %d visible"
                      % (tag, p.Name, n_cells, sorted(hid), vis))
        if n_cells != 3:
            errors.append("%s %s has %d subgrid cells, want 3 (one band "
                          "edge per end of its U/V axis)"
                          % (tag, p.Name, n_cells))
        if len(hid) != 2:
            errors.append("%s %s hides %s (%d cells), want exactly the TWO "
                          "band cells {0, 2} -- a union of the two seams' "
                          "own bands" % (tag, p.Name, sorted(hid), len(hid)))
        if hid != {0, 2}:
            errors.append("%s %s hides %s, want {0, 2}" % (tag, p.Name,
                                                          sorted(hid)))
        if vis != 1:
            errors.append("%s %s has %d visible cells, want exactly the 1 "
                          "interior one (the patch body)"
                          % (tag, p.Name, vis))
        if len(hid) > n_cells:
            errors.append("%s %s hides %d cells of %d"
                          % (tag, p.Name, len(hid), n_cells))

    # The regression itself: the FIRST blend's cell is still hidden after
    # the second exists. Under the bug the union was {1, 2}, i.e. cell 0
    # (the left seam's band) left VISIBLE and the middle cell hidden.
    for p in (pa, pb):
        if 0 not in _hidden(p):
            errors.append("%s: cell 0 (the left seam's own band) is visible "
                          "again after the right blend -- LOST" % p.Name)
        if 1 in _hidden(p):
            errors.append("%s: the interior cell 1 is hidden -- the sibling "
                          "band was computed from the wrong seam, so the "
                          "union held the middle instead of the first "
                          "blend's band" % p.Name)
    checks.append("both patches: first blend's cell 0 still hidden, "
                  "interior cell 1 visible")
    return {"pass": not errors, "errors": errors, "checks": checks}


def test_two_seam_sibling_band_comes_from_the_siblings_own_seam(doc):
    """The mechanism behind the auto-hide: for each blend, the band cells
    it attributes to the OTHER blend linked to the same patch are the ones
    that OTHER blend's own pinned seam names.

    This is asserted on `_linked_band_cells` directly (the object-level
    union is checked above), so the fix cannot pass by making the union
    accidentally right.
    """
    from SilkWorkflowOps import create_blend_by_edge
    from SilkBlend import _linked_band_cells
    from SilkMachinery import band_cells

    pa, pb, s_left, s_right = _build_tube(doc)
    errors, checks = [], []
    with _Capture() as cap:
        create_blend_by_edge(s_right, name="BlendRight")
    with _Capture() as cap:
        create_blend_by_edge(s_left, name="BlendLeft")
    errors += ["console error: %s" % e for e in cap.errors]

    blends = {o.Name: o for o in doc.Objects
              if getattr(o, "object_type", None) == "Blend"}
    if len(blends) != 2:
        errors.append("expected 2 Blend objects, got %d" % len(blends))
        return {"pass": False, "errors": errors, "checks": checks}

    # Each blend's own seam, per the fixture's own derivation: the LEFT
    # edge is A's V0 / B's U0, the RIGHT edge is A's V1 / B's U1.
    want_by_edge = {s_left.Name: ("V0", "U0"), s_right.Name: ("V1", "U1")}

    for bname, b in sorted(blends.items()):
        own = want_by_edge[b.Edge.Name]
        for p, own_side in ((pa, own[0]), (pb, own[1])):
            other = _linked_band_cells(b, p)
            sibling = b.PatchB if b.PatchA is p else b.PatchA
            for other_blend in blends.values():
                if other_blend is b:
                    continue
                if other_blend.PatchA is not sibling \
                        and other_blend.PatchB is not sibling:
                    continue
                e = want_by_edge[other_blend.Edge.Name][
                    0 if other_blend.PatchA is p else 1]
                ss = 0 if e[1] == "0" else 1
                want = set(band_cells(p, e, ss))
                if not want.issubset(other):
                    errors.append("%s attributes %s to the sibling blend of "
                                  "seam %s, whose own side %s on %s names %s"
                                  % (bname, sorted(other), other_blend.Name,
                                     e, p.Name, sorted(want)))
            checks.append("%s on %s: sibling band cells %s (own seam %s)"
                          % (bname, p.Name, sorted(other), own_side))
    return {"pass": not errors, "errors": errors, "checks": checks}


def test_an_edge_that_resolves_to_nothing_gets_no_band_editor(doc):
    """Given an edge that does NOT resolve against the pair, `_side_of`
    must say "no band" -- never fall back to the pair's first matching
    seam.

    This is the no-fallback rule stated in `_side_of`'s docstring, and it
    is load-bearing: falling back is exactly the wrong answer #83
    removes. A `Stray` edge 200 units away shares no corner with either
    tube patch, so `side_of_edge` has nothing to classify -- and the pair
    alone would happily have answered ('U0', 0).

    Also pins what the geometric pin DOES accept, which is unchanged
    behaviour and easy to mistake for a fallback: TubeB's arched bottom
    edge is not a shared Edge object, yet its endpoint poles sit on the
    panel's two bottom corners, so the pin resolves it to the panel's
    U0. #39 decision C made the pin purely geometric on purpose ("edge
    OBJECT identity is irrelevant"); this test records that the fix did
    not quietly narrow it.
    """
    from SilkTaskPanel import read_band_split, _side_of
    from Tests.test_seam_resolver import _stray_edge

    pa, pb, s_left, s_right = _build_tube(doc)
    errors, checks = [], []

    # The real seams DO resolve, through the edge.
    for e, want in ((s_left, "USplit1"), (s_right, "USplit2")):
        prop, ss = _side_of(pa, pb, e)
        if prop != want:
            errors.append("_side_of(pa, pb, %s) = %r, want %r"
                          % (e.Name, prop, want))
        checks.append("real seam %s -> %s/%s" % (e.Name, prop, ss))

    # An edge that shares nothing must be REFUSED, not answered.
    stray = _stray_edge(doc)
    got = _side_of(pa, pb, stray)
    if got != (None, None):
        errors.append("_side_of(pa, pb, %s) = %r -- %s resolves to no "
                      "corner pair on this pair, so there is no side; "
                      "falling back to the pair's first match is the #83 "
                      "bug" % (stray.Name, got, stray.Name))
    checks.append("non-resolving edge %s -> %r (refused)" % (stray.Name, got))

    # Through the panel entry: no editors, not a mis-targeted pair.
    entry = {"edge": stray, "patch_a": pa, "patch_b": pb,
             "status": "blendable", "blend": None}
    r = read_band_split(entry)
    if r is not None:
        errors.append("read_band_split on a non-resolving entry returned "
                      "%r, want None" % (r,))
    checks.append("read_band_split on a non-resolving entry -> None")

    # The geometric pin's own scope, unchanged: an unshared Edge whose
    # ENDPOINTS sit on the pair's corners still resolves.
    arch = [x for x in pb.Edges if x not in (s_left, s_right)][0]
    prop, ss = _side_of(pa, pb, arch)
    if prop != "VSplit1" or ss != 0:
        errors.append("_side_of(pa, pb, %s) = (%r, %r), want ('VSplit1', 0) "
                      "-- the pin is geometric by design (#39 decision C): "
                      "the arch edge is not a shared Edge object but its "
                      "endpoint poles sit on the panel's bottom corners"
                      % (arch.Name, prop, ss))
    checks.append("geometric pin still accepts %s by its endpoints -> "
                  "%s/%s" % (arch.Name, prop, ss))
    return {"pass": not errors, "errors": errors, "checks": checks}


def test_patch_side_alone_still_names_the_single_seam(doc):
    """`patch_side` keeps working for callers that genuinely have only a
    patch pair -- the single-seam case, which is every band/blend/corner
    test in the suite. Refused to answer when the pair shares MORE than
    one edge is a second question; see module docstring of SilkMachinery.
    """
    from SilkMachinery import patch_side
    from Tests.corner_model import build_corner_pair

    errors, checks = [], []
    model = build_corner_pair(doc)
    pa = model["patches"]["Patch44"]
    pb = model["patches"]["Patch001"]
    et, ss = patch_side(pa, pb)
    if et is None:
        errors.append("patch_side returned None on the single-seam corner "
                      "pair (%s, %s)" % (pa.Name, pb.Name))
    else:
        checks.append("single-seam corner pair -> (%s, %s)" % (et, ss))
    return {"pass": not errors, "errors": errors, "checks": checks}


ALL_TESTS = [
    test_two_seam_band_editor_names_each_seams_own_property,
    test_two_seam_band_write_touches_only_its_own_property,
    test_two_seam_auto_hide_keeps_both_band_cells,
    test_two_seam_sibling_band_comes_from_the_siblings_own_seam,
    test_an_edge_that_resolves_to_nothing_gets_no_band_editor,
    test_patch_side_alone_still_names_the_single_seam,
]