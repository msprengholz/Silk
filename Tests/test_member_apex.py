"""The triangular member's apex is the cell's LEADER/LEADER corner.

HIS RULE.  The maintainer's rolling corner (`Silk_CopyPasta_29`, corner
`CubicSurface_66_013`) cuts its corner patch at the setback and the leader and
builds the triangular member over the region BETWEEN them; the member's
collapsed row -- the apex -- sits at `(0.25, 0.25)`, the corner where the two
LEADERS meet, and the junction square is preserved original surface that
belongs to neither surface
(`docs/research/silk-rolling-corner-66.md` sections 1.2 and 1.3).

WHY IT IS PINNED.  `SilkCorner._tri_ring_member` walks the four cell corners
until the ring assembles, and more than one corner assembles on a lopsided
ring.  Measured on the demo's `CB_J1_FrontTopRight`, the first assembling
corner (index 1) put the apex on the SETBACK/SETBACK corner -- the junction
side -- so the 66, whose fourth side is the member's real row, closed its loop
AROUND the member: the tri's interior read 0.35..1.47 mm off the quad
(0.6..2.6 % of the corner's extent, i.e. the two surfaces described one area).
`SilkCorner.member_apex_corner` derives the corner from the cell's own two
boundary values instead, and the tri then reads 0.89..8.37 mm
(1.6..14.6 %) -- beside the 66, not inside it.

The stubs below are Patches only in the sense the arithmetic needs: the four
named band edges, the four named leader cuts, and the cell rectangle the ring
reports for that patch.  No document is touched; the harness passes `doc` to
every test function and these do not use it.
"""

import FreeCAD

import SilkCorner


class _CellPatch:
    """A patch-shaped stub: the cuts the cell arithmetic reads, nothing else."""

    def __init__(self, u_split, v_split, u_leader, v_leader, name="Stub"):
        self.Name = name
        self.USplit1, self.USplit2 = u_split
        self.VSplit1, self.VSplit2 = v_split
        self.ULeader1, self.ULeader2 = u_leader
        self.VLeader1, self.VLeader2 = v_leader


def _cell(iu, iv):
    return (None, iu, iv, 2, 2)


def test_the_apex_takes_the_corner_at_the_two_leaders(doc):
    """Junction at the 0 ends (the cube corner): setback 0.1, leader 0.25 --
    the cell's interval 0 is the setback, interval 1 the leader, so the apex
    is the (3, 3) corner, which `control_grid64_3_1` collapses at index 0.
    The cell is the ring's own rectangle, `corner_cell_index`'s interval 1
    (the region between the setback 0.1 and the leader 0.25)."""
    patch = _CellPatch((0.1, 1.0), (0.1, 1.0), (0.25, 1.0), (0.25, 1.0))
    apex = SilkCorner.member_apex_corner(patch, _cell(1, 1))
    errors = []
    if apex != 0:
        errors.append("the apex corner is %r, want 0 (the leader/leader "
                      "corner of an axis whose junction is at the 0 ends)"
                      % (apex,))
    order = SilkCorner._apex_corner_order(patch, _cell(1, 1))
    if order != [0, 1, 2, 3]:
        errors.append("the search order is %r, want the apex corner first"
                      % (order,))
    return {"pass": not errors, "errors": errors,
            "checks": ["apex corner %r, search order %r" % (apex, order)]}


def test_the_apex_follows_the_junction_to_the_other_ends(doc):
    """The demo's shape: U's junction at the 1 end (setback 0.9, leader 0.75)
    and V's at the 0 end (setback 0.1, leader 0.25).  The leader/leader corner
    is then the cell's (0, 3) one -- index 3 -- and NOT the setback/setback
    corner (index 1) the corner search reaches first."""
    patch = _CellPatch((0.0, 0.9), (0.1, 0.9), (0.0, 0.75), (0.25, 1.0))
    apex = SilkCorner.member_apex_corner(patch, _cell(1, 1))
    errors = []
    if apex != 3:
        errors.append("the apex corner is %r, want 3" % (apex,))
    order = SilkCorner._apex_corner_order(patch, _cell(1, 1))
    if order != [3, 0, 1, 2]:
        errors.append("the search order is %r, want the apex corner first"
                      % (order,))
    return {"pass": not errors, "errors": errors,
            "checks": ["apex corner %r, search order %r" % (apex, order)]}


def test_a_cell_without_a_leader_keeps_the_old_search_order(doc):
    """No leader cut on an axis means no leader/leader corner: the order stays
    0..3, which is the shipped corner's behaviour (byte-identical)."""
    errors, checks = [], []
    patch = _CellPatch((0.1, 1.0), (0.1, 1.0), (0.0, 1.0), (0.0, 1.0))
    apex = SilkCorner.member_apex_corner(patch, _cell(0, 0))
    order = SilkCorner._apex_corner_order(patch, _cell(0, 0))
    checks.append("a leader-free cell: apex corner %r, search order %r"
                  % (apex, order))
    if apex is not None:
        errors.append("a cell with no leader named an apex corner (%r)"
                      % (apex,))
    if order != [0, 1, 2, 3]:
        errors.append("the search order changed for a leader-free cell: %r"
                      % (order,))
    # an INERT leader (inside the band) is not a cut either (`axis_cuts`)
    patch = _CellPatch((0.1, 1.0), (0.1, 1.0), (0.05, 1.0), (0.05, 1.0))
    if SilkCorner.member_apex_corner(patch, _cell(0, 0)) is not None:
        errors.append("a leader INSIDE the band was read as a real cut")
    checks.append("a leader inside its band (0.05 under a 0.1 setback) names "
                  "no apex corner")
    return {"pass": not errors, "errors": errors, "checks": checks}


ALL_TESTS = [
    test_the_apex_takes_the_corner_at_the_two_leaders,
    test_the_apex_follows_the_junction_to_the_other_ends,
    test_a_cell_without_a_leader_keeps_the_old_search_order,
]
