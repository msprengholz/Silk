"""
The LEADER cut — a second cut per axis end, additive and default-off (#119).

WHAT IS PINNED HERE

  1. A PATCH WITH NO LEADER READS EXACTLY WHAT IT ALWAYS READ.  The four
     leader properties are created at their sentinels, the axis is cut into
     the same intervals, the patch builds the same subgrid cells, and the
     corner cell is the same interval — the identity, cell for cell.

  2. A LEADER CUT SUBDIVIDES THE AXIS.  One more exact knot line, and the
     corner cell becomes the interval BETWEEN the setback and the leader
     (`SilkMachinery.corner_cell_index`), while the BAND still covers exactly
     ONE cell (`band_cells`) — the #82 invariant the leader must not break.

  3. A LEADER INSIDE THE BAND IS INERT AND NAMED.  `axis_cuts` drops it (the
     band edge already cuts further out) and `leader_cut_problem` says so, so
     a caller cannot build a corner cell that is really the band's own cell.

WHY THE TICKET'S TWO-SURFACE CORNER IS NOT BUILT ON IT YET (SUPERSEDED by
#128/#129 -- kept as history): with the
leader-bounded cell the ring assembles with the member's REAL row as its ring
row and the 66 stops at the member's cell (0.0633 mm^2 against the member's
0.0206, no collapsed side) — measured, and rendered in
`Resources/Test_files/_inspect/after_*.png`.  It FOLDS: the member-side
interior rows are extrapolated from the member's own rows and flip the normal
field 25/53/96 times at n = 39/81/150, with the fine mesh self-intersecting.
`SilkMachinery.smooth_degenerate_cap` fixes a COLLAPSED side, and this
arrangement has none there.  **The two-surface corner shipped anyway (#128):**
read REAL-ROW-FIRST, that arrangement measures 0/0/0 flips and needs no
re-solve (`Tests/test_two_patch_corner.py`), and #129 placed the cut by a
length in mm.  The cut, the cell rule and the refusals are what this file
pins.  Numbers: `docs/research/silk-rolling-corner-66.md`, and the corner
itself: `docs/adr/0006-rolled-corner-is-two-patches.md`.
"""

import FreeCAD

import SilkMachinery as SM
from SilkBlend import side_and_end
from Tests import cube_corner_model as ccm


def _cube(doc):
    ccm.build_cube_corner_model(doc)
    doc.recompute()
    doc.recompute()
    return [doc.getObject(n) for n in ("B_AB", "B_BC", "B_CA")]


def test_a_patch_without_a_leader_reads_exactly_what_it_always_read(doc):
    """The identity: sentinels, the same intervals, the same corner cell,
    the same subgrid cells."""
    errors, checks = [], []
    strips = _cube(doc)
    p = strips[0].PatchA
    for letter in ("U", "V"):
        if SM.leader_pair(p, letter) != (SM.NO_LEADER_1, SM.NO_LEADER_2):
            errors.append("%sLeader does not default to its sentinels"
                          % letter)
        s1, s2 = SM.split_pair(p, letter)
        plain = SM.build_intervals(s1, s2)
        with_leader = SM.build_intervals(s1, s2, *SM.leader_pair(p, letter))
        checks.append("%s: %r (both readings), band edge %r"
                      % (letter, plain, (s1, s2)))
        if plain != with_leader:
            errors.append("%s: an unset leader changed the intervals: %r vs %r"
                          % (letter, plain, with_leader))
        idx, n, _end = SM.corner_cell_index(s1, s2, *SM.leader_pair(p, letter))
        if (idx, n) != (0, 2):
            errors.append("%s: the corner cell is (%r, %r), not the end "
                          "interval of this two-interval axis"
                          % (letter, idx, n))
    cells = len(p.Proxy._subgrids)
    checks.append("subgrid cells: %d" % cells)
    if cells != 4:
        errors.append("a patch with no leader should carry 4 cells, got %d"
                      % cells)
    return {"pass": not errors, "errors": errors, "checks": checks}


def test_a_leader_cut_subdivides_the_axis_and_leaves_the_band_one_cell(doc):
    """The new cut: one more cell per axis, the corner cell BETWEEN the two,
    and the band still ONE cell (#82) with the leader in place.

    Both readings are of the same cut on the same patch, so they are one
    test: the fixture build is what either of them cost."""
    errors, checks = [], []
    strips = _cube(doc)
    p = strips[0].PatchA
    before = len(p.Proxy._subgrids)
    SM.ensure_leader_cuts(p)
    for letter in ("U", "V"):
        setattr(p, "%sLeader1" % letter, 0.25)
    doc.recompute()
    after = len(p.Proxy._subgrids)
    checks.append("subgrid cells: %d -> %d" % (before, after))
    if before != 4 or after != 9:
        errors.append("a leader on both axes should cut the patch from 4 "
                      "cells to 9, got %d -> %d" % (before, after))
    for letter in ("U", "V"):
        s1, s2 = SM.split_pair(p, letter)
        l1, l2 = SM.leader_pair(p, letter)
        ivs = SM.build_intervals(s1, s2, l1, l2)
        idx, n, _end = SM.corner_cell_index(s1, s2, l1, l2)
        lo, hi = ivs[idx]
        checks.append("%s: the corner cell is [%g, %g] (index %d of %d)"
                      % (letter, lo, hi, idx, n))
        if abs(lo - 0.1) > 1e-12 or abs(hi - 0.25) > 1e-12:
            errors.append("%s: the corner cell is not the region between the "
                          "setback 0.1 and the leader 0.25" % letter)
        excluded = SM.corner_cells(s1, s2, n, l1, l2)
        if excluded != {0, 1}:
            errors.append("%s: the band exclusion is %r, not the whole corner "
                          "region {0, 1}" % (letter, sorted(excluded)))
    # ... and the band is still ONE cell per seam, leader or no leader
    for s in strips:
        for q in (s.PatchA, s.PatchB):
            e, ss = side_and_end(s, q)
            cells = SM.band_cells(q, e, ss)
            checks.append("%s on %s (%s): band cells %r"
                          % (s.Name, q.Name, e, cells))
            if len(cells) != 1:
                errors.append("%s on %s: the band covers %d cells -- the "
                              "one-cell invariant is broken"
                              % (s.Name, q.Name, len(cells)))
    return {"pass": not errors, "errors": errors, "checks": checks}


def test_a_leader_inside_the_band_is_inert_and_named(doc):
    """Below the band edge there is nothing to cut, and the reason says so."""
    errors, checks = [], []
    strips = _cube(doc)
    p = strips[0].PatchA
    if SM.leader_cut_problem(p) is not None:
        errors.append("a patch with no leader reported a problem")
    SM.ensure_leader_cuts(p)
    p.ULeader1 = 0.0625
    doc.recompute()
    s1, s2 = SM.split_pair(p, "U")
    cuts = SM.axis_cuts(s1, s2, *SM.leader_pair(p, "U"))
    checks.append("U axis cuts with a 1/16 leader under a 0.1 band: %r"
                  % (cuts,))
    if 0.0625 in cuts:
        errors.append("a leader inside the band was admitted as a cut")
    if len(p.Proxy._subgrids) != 4:
        errors.append("an inert leader still subdivided the patch (%d cells)"
                      % len(p.Proxy._subgrids))
    problem = SM.leader_cut_problem(p)
    checks.append("leader_cut_problem: %r" % (problem,))
    if not problem or "does not clear" not in problem:
        errors.append("a leader inside the band was not refused by name")
    p.ULeader1 = 0.25
    doc.recompute()
    if SM.leader_cut_problem(p) is not None:
        errors.append("a leader clear of the band still reported a problem: %s"
                      % SM.leader_cut_problem(p))
    else:
        checks.append("a leader clear of the band is accepted")
    return {"pass": not errors, "errors": errors, "checks": checks}


def test_the_ring_loop_closes_at_one_cut_and_opens_at_two(doc):
    """#127's loop rule, as the one predicate that decides it.

    A ring pair's shared corner is the patch's corner cell FAR corner.
    On the axis across one strip's seam that corner's coordinate is the
    BAND EDGE (where the band ends); on the axis along it, it is the
    along START (the corner cell's far edge). The two strips of a pair
    name the axes the other way round, so the corner is one point exactly
    when the band edge and the along start are the same number at each end
    -- one cut per axis end. A real second cut (the rolling leader) splits
    them, and `ring_corner_gap` names the two numbers.  That is CORRECT on
    the one patch per corner that carries the triangular patch (its two ring
    corners are two different points there, #127), and it is what the corner
    stage refuses on any other patch.
    """
    errors, checks = [], []
    strips = _cube(doc)
    for q in (strips[0].PatchA, strips[0].PatchB, strips[1].PatchB):
        gap = SM.ring_corner_gap(q)
        checks.append("%s, shipped (one cut per axis end): ring_corner_gap %r"
                      % (q.Name, gap))
        if gap is not None:
            errors.append("%s: the shipped ring reports an open corner %r"
                          % (q.Name, gap))
    p = strips[0].PatchA
    SM.ensure_leader_cuts(p)
    p.ULeader1 = 0.25
    p.VLeader1 = 0.25
    doc.recompute()
    gap = SM.ring_corner_gap(p)
    checks.append("%s, leader 0.25 on both axes (two cuts per axis end): "
                  "ring_corner_gap %r" % (p.Name, gap))
    if gap is None:
        errors.append("a real leader cut left the ring reported as CLOSED")
    elif gap != ("U", 0.1, 0.25):
        errors.append("the gap names %r, not the (axis, band edge, leader) "
                      "that split it" % (gap,))
    # THE CARRYING PATCH IS THE ONE PATCH WHERE TWO PAIRS MEET, so its two
    # ring corners are the two ENDS of the member's one row -- two DIFFERENT
    # points are correct there, and #119's arrangement (the cut on that
    # patch alone) assembles.
    import SilkCorner as SC
    _grids, _cells, why = SC.corner_inputs(strips, SC.CORNER_DEFAULT_TOL)
    checks.append("corner_inputs with the cut on the member patch only: %r"
                  % (why,))
    if why is not None:
        errors.append("the member patch's own two ring corners should be the "
                      "member row's two ends, not a refusal: %r" % (why,))
    # ... and a SECOND patch with two cuts (a patch that carries a PAIR, not
    # the member) opens the ring, and the refusal now says why.
    for q in (strips[1].PatchA, strips[1].PatchB, strips[2].PatchB):
        SM.ensure_leader_cuts(q)
        q.ULeader1 = 0.25
        q.VLeader1 = 0.25
    doc.recompute()
    _grids, _cells, why = SC.corner_inputs(strips, SC.CORNER_DEFAULT_TOL)
    checks.append("corner_inputs with two cuts on every patch: %r" % (why,))
    if not why or "the ring's corner is OPEN on" not in why:
        errors.append("the corner refused without naming the open ring "
                      "corner: %r" % (why,))
    # the along start IS the leader only while the leader clears the band
    # edge; an inert one leaves one cut and the ring closed.
    p.ULeader1 = 0.0625
    doc.recompute()
    inert = SM.ring_corner_gap(p)
    checks.append("%s, leader 0.0625 inside the 0.1 band (inert): "
                  "ring_corner_gap %r" % (p.Name, inert))
    if inert is not None and inert[0] == "U":
        errors.append("an INERT leader on the U axis was reported as "
                      "opening the ring: %r" % (inert,))
    return {"pass": not errors, "errors": errors, "checks": checks}


class _TwoJunctionAxis:
    """A patch-shaped stub carrying the demo's OWN layout on one axis (#126).

    `V` holds a band edge at BOTH ends -- 0.1 from the seam that reaches the
    junction and 0.9 from the seam on the OTHER side of the patch, i.e. a
    second junction on the same axis -- and the junction's own LEADER cut at
    the 0 end.  `band_extent` / `band_cells` / `corner_cells` read nothing
    but these names, so the arithmetic can be exercised without geometry."""
    Name = "P_TwoJunction"
    USplit1, USplit2 = 0.0, 0.9
    VSplit1, VSplit2 = 0.1, 0.9
    ULeader1, ULeader2 = 0.0, 0.75
    VLeader1, VLeader2 = 0.25, 1.0


def test_two_junctions_on_one_axis_still_leave_the_band_one_cell(doc):
    """#126: the corner region is read PER END, so a band edge at BOTH ends
    of one axis does not eat the band.

    The owner's own ring patches carry a third seam on the side opposite the
    junction, so the along-seam axis holds two band edges.  Read as ONE end
    (the pre-#126 rule, which has to name one) the leader cut at the junction
    end leaves the band TWO cells; read per end it is the one cell between
    the leader and the far setback -- the cube's answer, on the demo's
    layout.  The setback is untouched and the far end's own cell stays a
    corner cell (it belongs to the other junction)."""
    errors, checks = [], []
    p = _TwoJunctionAxis()

    # the exclusion, per end, with the leader cut at the junction (0) end
    vs = SM.build_intervals(p.VSplit1, p.VSplit2, p.VLeader1, p.VLeader2)
    excluded = SM.corner_cells(p.VSplit1, p.VSplit2, len(vs),
                              p.VLeader1, p.VLeader2)
    checks.append("V intervals %r -> excluded %r"
                  % ([tuple(round(x, 4) for x in iv) for iv in vs],
                     sorted(excluded)))
    if excluded != {0, 1, len(vs) - 1}:
        errors.append("the corner regions are %r: want the junction-side "
                      "region {0, 1} and the FAR end's own cell {%d}"
                      % (sorted(excluded), len(vs) - 1))

    # the band: exactly ONE cell, and it is the one between the leader and
    # the far setback
    cells = SM.band_cells(p, "V1", 1)
    checks.append("band_cells(V1, 1) = %r" % (cells,))
    if len(cells) != 1:
        errors.append("the band covers %d cells -- the one-cell invariant is "
                      "broken by the second junction on the axis"
                      % len(cells))

    # the patch ALONE cannot say which end the junction is at, and the
    # refusal names both candidates
    ext = SM.band_extent(p, "V1", 1)
    checks.append("band_extent(V1, 1) without the ring: %r" % (ext[1],))
    if ext[0] is not None:
        errors.append("the patch named one junction end for an axis with a "
                      "band edge at both ends")
    elif "VSplit1" not in str(ext[1]) or "VSplit2" not in str(ext[1]):
        errors.append("the refusal does not name both candidate ends: %r"
                      % (ext[1],))

    # with the end the RING reads, the band's extent and end come out
    ext = SM.band_extent(p, "V1", 1, 0)
    checks.append("band_extent(V1, 1, end=0) = %r" % (ext,))
    if ext[0] is None:
        errors.append("the ring's end did not place the band: %s" % (ext[1],))
    else:
        (lo, hi), _band, end = ext
        if abs(lo - 0.25) > 1e-12 or abs(hi - 0.9) > 1e-12 or end != 0:
            errors.append("the band reads %r at the %r end, want (0.25, 0.9) "
                          "at the 0 end" % ((lo, hi), end))

    # a caller whose end CONTRADICTS the axis is refused, never guessed
    q = _TwoJunctionAxis()
    q.VSplit1 = 0.0            # one band edge, at the 1 end only
    ext = SM.band_extent(q, "V1", 1, 0)
    checks.append("band_extent on a one-edge axis, told the wrong end: %r"
                  % (ext[1],))
    if ext[0] is not None:
        errors.append("a caller's end contradicted the patch's own band edge "
                      "and was accepted anyway")
    return {"pass": not errors, "errors": errors, "checks": checks}


ALL_TESTS = [
    test_a_patch_without_a_leader_reads_exactly_what_it_always_read,
    test_a_leader_cut_subdivides_the_axis_and_leaves_the_band_one_cell,
    test_a_leader_inside_the_band_is_inert_and_named,
    test_the_ring_loop_closes_at_one_cut_and_opens_at_two,
    test_two_junctions_on_one_axis_still_leave_the_band_one_cell,
]
