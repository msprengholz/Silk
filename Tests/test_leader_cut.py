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

WHY THE TICKET'S TWO-SURFACE CORNER IS NOT BUILT ON IT YET: with the
leader-bounded cell the ring assembles with the member's REAL row as its ring
row and the 66 stops at the member's cell (0.0633 mm^2 against the member's
0.0206, no collapsed side) — measured, and rendered in
`Resources/Test_files/_inspect/after_*.png`.  It FOLDS: the member-side
interior rows are extrapolated from the member's own rows and flip the normal
field 25/53/96 times at n = 39/81/150, with the fine mesh self-intersecting.
`SilkMachinery.smooth_degenerate_cap` fixes a COLLAPSED side, and this
arrangement has none there.  So the corner stage keeps the cut it has always
used (the band edge) until the member side has a re-solve; the cut, the cell
rule and the refusals are what this file pins in the meantime.  Numbers:
`docs/research/silk-rolling-corner-66.md`.
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


def test_a_leader_cut_subdivides_the_axis_and_between_is_the_corner_cell(doc):
    """The new cut: one more cell, and the corner cell is BETWEEN the two."""
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
    return {"pass": not errors, "errors": errors, "checks": checks}


def test_the_band_stays_one_cell_under_a_leader_cut(doc):
    """The #82 invariant: ONE cell per band, leader or no leader."""
    errors, checks = [], []
    strips = _cube(doc)
    p = strips[0].PatchA
    SM.ensure_leader_cuts(p)
    for letter in ("U", "V"):
        setattr(p, "%sLeader1" % letter, 0.25)
    doc.recompute()
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


ALL_TESTS = [
    test_a_patch_without_a_leader_reads_exactly_what_it_always_read,
    test_a_leader_cut_subdivides_the_axis_and_between_is_the_corner_cell,
    test_the_band_stays_one_cell_under_a_leader_cut,
    test_a_leader_inside_the_band_is_inert_and_named,
]
