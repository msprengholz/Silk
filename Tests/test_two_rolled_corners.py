"""
MORE THAN ONE ROLLED CORNER, AND WHAT DELETING ONE GIVES BACK (#131).

The owner's ask (2026-10-22): *"you need to test if the patch subdivision for
a rolling corner works if there is more than one rolling corner in a document,
as one patch might get subdivided multiple times. of course, this also has to
be revertible when the rolling corners get deleted."*

WHY THIS IS A PRESSURE POINT.  A rolled corner cuts its MEMBER PATCH: the
leader cut it places is one of that patch's four properties (`ULeader1/2`,
`VLeader1/2` -- one slot per AXIS END).  Two corners on one document therefore
write into one namespace, and the demo's four junctions share patches:

    junction                    ring                   member patch  reads
    CB_J1_FrontTopRight         B_FT B_FR B_TR         P_Top         (u1,v0)
    CB_J2_FrontRightBottom      B_FB B_FR B_BR         P_Bottom      (u0,v1)
    CB_J3_TopRightBack          B_TR B_TBk B_BkR       P_Top         (u1,v1)
    CB_J4_RightBottomBack       B_BR B_BkB B_BkR       P_Right       (u1,v0)

J1 and J2 share P_Front and P_Right through B_FR and neither cuts them, so
they coexist and each reads its OWN cells (`test_two_rolled_corners_...`).
J1 and J3 share the MEMBER PATCH P_Top and both need its U axis's 1 end --
one slot, two leaders (`test_two_corners_on_one_axis_end_...`).  That is the
limit the one-cut-per-axis-end model has, and it is NOT worked around here:
the measurement is what the owner decides on (`two_rolled_corners.py`, the
MANUAL instrument, prints the same tables plus the demo's own numbers).

WHAT THE DELETION PINS.  A corner that is deleted must leave the model as it
found it (`SilkCorner.release_corner`, the `_CutRecord` write log): the
member patch's cut goes back to the value it carried, the corner's own
surfaces (the triangular member, its fill, the five preserved pieces) go, and
the patches, the ring strips and the OTHER corner are untouched.  Deleting
the last corner returns every patch, every weight, every subgrid count and
every strip pole to the PRE-CORNER state, byte for byte (0.00e+00).

The fixture is the demo model (`Tests/demo01_fixture_model.py`: 12 Edges, 5
Patches, 8 Blends, built through the ops layer) with `corners=False`, so the
corner stage itself is what this module drives.

The demo is the only fixture with more than one junction (the cube-corner
fixture has one, the 4-patch fixture one), which is why this module is in the
MANUAL tier beside `test_corner_choices` and `test_two_patch_corner`: the
seven tests below build the demo model thirteen times (~40 s), and the fast
tier is the inner loop.  The cube fixture's own rolling pins stay in
`test_preserved_pieces` / `test_two_patch_corner`.
"""

# --- manual tier ------------------------------------------------------
# The demo model, thirteen times.  Run it with
#   python3 Tests/run_all.py --manual two_rolled_corners
MANUAL = True

import os
import tempfile

import FreeCAD

import demo01_fixture_model as DEMO
import SilkCorner as SC
import SilkMachinery as SM
import SilkWorkflowOps as OPS
from Tests.mcp_harness import check

# (short name, corner name, the 3 ring blends) -- `DEMO.CORNERS`, shortened.
JUNCTIONS = (
    ("J1", "CB_J1_FrontTopRight", ("B_FT", "B_FR", "B_TR")),
    ("J2", "CB_J2_FrontRightBottom", ("B_FB", "B_FR", "B_BR")),
    ("J3", "CB_J3_TopRightBack", ("B_TR", "B_TBk", "B_BkR")),
    ("J4", "CB_J4_RightBottomBack", ("B_BR", "B_BkB", "B_BkR")),
)
SHORT = {name: short for short, name, _ring in JUNCTIONS}
RING = {short: ring for short, _name, ring in JUNCTIONS}

# The demo's five patches, in the fixture's own order.
PATCH_NAMES = [name for name, _order, _grid in DEMO.PATCHES]

# The pair matrix, MEASURED (`Tests/two_rolled_corners.py` prints the raw
# table).  Keyed by the two short names in JUNCTIONS order; the value is
# (first construction, first state, second construction, second state), where
# a state is "built" (poles and a member), "empty" (the object exists with an
# EMPTY net -- its ring stopped assembling) or "none" (no object at all).
#
# The row that ends "rolling/empty" is a DEFECT this table records rather
# than hides: the second corner rolls and the FIRST one's ring stops
# assembling, because the second corner cut the axis end the first one reads.
# It turns red the day that is fixed, which is the point -- the fix is the
# owner's decision (a LIST of cuts per axis instead of one).
PAIR_MATRIX = {
    ("J1", "J2"): ("rolling", "built", "rolling", "built"),
    ("J1", "J3"): ("rolling", "built", "shipped", "built"),
    ("J1", "J4"): ("rolling", "built", "rolling", "built"),
    ("J2", "J3"): ("rolling", "built", "rolling", "built"),
    ("J2", "J4"): ("rolling", "built", None, "none"),
    ("J3", "J4"): ("rolling", "empty", "rolling", "built"),
}

# The slots each corner writes when it is the only one in the document:
# (patch, property).  Read by the clash test below, so "one slot, two
# leaders" is a named fact and not a number buried in a message.
SOLO_CUTS = {
    "J1": (("P_Top", "ULeader2"), ("P_Top", "VLeader1")),
    "J2": (("P_Bottom", "ULeader1"), ("P_Bottom", "VLeader2")),
    "J3": (("P_Top", "ULeader2"), ("P_Top", "VLeader2")),
    "J4": (("P_Right", "ULeader2"), ("P_Right", "VLeader1")),
}

# The values the two corners of the clashing pair place in the SAME slot on a
# fresh model, in mm from the junction corner (measured; the equalising rule
# moves them by a hair, which is why the test compares the PATTERN and not
# these digits).
CUT_TOL = 1e-9


# ---- reading the model ---------------------------------------------------

def _model(doc):
    """The demo model with its blends and NO corners."""
    built = DEMO.build(doc, corners=False)
    doc.recompute()
    doc.recompute()
    return built


def _fresh(doc):
    """Empty the document and build the demo model in it.

    The harness hands one document to a whole test, and a pair matrix builds
    six models one after another: a second `DEMO.build` into a document that
    still holds the first pair's objects is a DIFFERENT model (the names are
    taken), so the document is emptied first.  Deleting a patch CASCADES its
    blends (#89), so the name list goes stale while it is walked: every
    removal is allowed to find its object already gone.  A corner removed
    here releases itself, which is the path under test elsewhere in this
    module."""
    for name in [o.Name for o in doc.Objects]:
        try:
            doc.removeObject(name)
        except Exception:
            pass
    doc.recompute()
    return _model(doc)


def _corner(doc, short):
    """Build (or fetch) one junction's corner through the ops layer."""
    strips = [doc.getObject(b) for b in RING[short]]
    name = [n for s, n, _r in JUNCTIONS if s == short][0]
    corner = OPS.create_corner_blend(strips, name=name)
    doc.recompute()
    doc.recompute()
    return corner


def _member(doc, corner):
    for o in doc.Objects:
        if (getattr(o, "object_type", "") == "RollingMemberFace"
                and getattr(o, "Corner", None) is corner):
            return o
    return None


def _slots(doc):
    """{(patch name, property): value} -- every LEADER CUT in the document."""
    out = {}
    for name in PATCH_NAMES:
        p = doc.getObject(name)
        if p is None:
            continue
        for letter in ("U", "V"):
            l1, l2 = SM.leader_pair(p, letter)
            for end, value in ((0, l1), (1, l2)):
                if SM.band_edge(value) is not None:
                    out[(name, SM.leader_cut_prop(letter, end))] = value
    return out


def _state(doc, corner, member):
    """One corner's reading: construction, net, member, pieces, its cuts."""
    pieces = list(getattr(corner, "Pieces", None) or [])
    return {
        "construction": getattr(corner, "Construction", "") or "",
        "poles": len(getattr(corner, "Poles", None) or []),
        "member": (member is not None
                   and bool(getattr(member, "Poles", None) or [])),
        "pieces": sorted(p.Name for p in pieces),
        "cells": [(p.Patch.Name, p.CellU, p.CellV) for p in pieces],
    }


def _snapshot(doc):
    """Everything a corner must leave alone: each patch's cuts, net, subgrid
    count and hidden cells, and each strip's net."""
    out = {}
    for name in PATCH_NAMES:
        p = doc.getObject(name)
        out["patch:" + name] = {
            "cuts": (SM.split_pair(p, "U") + SM.leader_pair(p, "U")
                     + SM.split_pair(p, "V") + SM.leader_pair(p, "V")),
            "poles": [tuple(v) for v in p.Poles],
            "weights": [float(w) for w in p.Weights],
            "subgrids": len(getattr(p.Proxy, "_subgrids", None) or []),
            "hidden": sorted(int(i) for i in
                             (getattr(p, "_HiddenSubgridIdxs", None) or [])),
        }
    for name, _pa, _pb, _e in DEMO.BLENDS:
        b = doc.getObject(name)
        out["strip:" + name] = {
            "poles": [tuple(v) for v in b.Poles],
            "weights": [float(w) for w in b.Weights],
        }
    return out


def _delta(before, after):
    """[(key, field, the number)] -- every difference, with its magnitude."""
    out = []
    for key in sorted(before):
        if key not in after:
            out.append((key, "object", float("inf")))
            continue
        for field in before[key]:
            a = before[key][field]
            b = after[key][field]
            if isinstance(a, list) and isinstance(b, list):
                if len(a) != len(b):
                    out.append((key, field, float("inf")))
                elif a and isinstance(a[0], tuple):
                    d = max((FreeCAD.Vector(*x) - FreeCAD.Vector(*y)).Length
                            for x, y in zip(a, b))
                    if d > 0.0:
                        out.append((key, field, d))
                elif a:
                    d = max(abs(x - y) for x, y in zip(a, b))
                    if d > 0.0:
                        out.append((key, field, d))
            elif a != b:
                out.append((key, field, float("inf")))
    for key in sorted(after):
        if key not in before:
            out.append((key, "object", float("inf")))
    return out


def _pole_delta(a, b):
    return max([(FreeCAD.Vector(*x) - FreeCAD.Vector(*y)).Length
                for x, y in zip(a, b)] or [0.0])


# ---- 1. two corners that coexist ----------------------------------------

def test_two_rolled_corners_share_patches_and_each_reads_its_own_cells(doc):
    """J1 + J2: both roll, both own their cells, and NEITHER cuts a shared
    patch.

    Both corners record `Construction = "rolling"`, carry the 36-pole 66, a
    triangular member and five preserved pieces; they read two DIFFERENT
    member patches (P_Top / P_Bottom) at two different corners; the patches
    they share (P_Front, P_Right) carry no leader cut at all, which is what
    lets them meet at one band edge each.

    WOULD BE RED IF: either corner fell back to the shipped construction, a
    corner's member or pieces were missing, a shared patch carried a cut, or
    the two corners read the same cell of one patch (the second corner would
    then be covering the first's surface)."""
    errors, checks = [], []
    built = _model(doc)
    check(not built["problems"], "the demo model did not build: %r"
          % (built["problems"],), errors)
    j1 = _corner(doc, "J1")
    j2 = _corner(doc, "J2")
    if j1 is None or j2 is None:
        return {"pass": False, "checks": checks,
                "errors": ["a corner refused: J1=%r J2=%r"
                           % (j1, j2)]}
    m1, m2 = _member(doc, j1), _member(doc, j2)
    s1, s2 = _state(doc, j1, m1), _state(doc, j2, m2)
    for short, corner, state in (("J1", j1, s1), ("J2", j2, s2)):
        checks.append(
            "%s: construction %r, %d poles, member %s, %d pieces %r"
            % (short, state["construction"], state["poles"],
               "built" if state["member"] else "MISSING",
               len(state["pieces"]), state["pieces"]))
        check(state["construction"] == "rolling",
              "%s is not a rolling corner (%r)"
              % (short, state["construction"]), errors)
        check(state["poles"] == 36, "%s has %d poles, not 36"
              % (short, state["poles"]), errors)
        check(state["member"], "%s has no triangular member" % short, errors)
        check(len(state["pieces"]) == 5, "%s keeps %d pieces, not 5"
              % (short, len(state["pieces"])), errors)
    slots = _slots(doc)
    checks.append("leader cuts in the document: %s"
                  % sorted("%s.%s" % k for k in slots))
    for short, want in (("J1", SOLO_CUTS["J1"]), ("J2", SOLO_CUTS["J2"])):
        check(set(want) <= set(slots),
              "%s's own cuts are not in the document: %r"
              % (short, sorted(set(want) - set(slots))), errors)
    check(set(slots) == set(SOLO_CUTS["J1"]) | set(SOLO_CUTS["J2"]),
          "the two corners cut more than their own member patches: %r"
          % sorted(set(slots) - (set(SOLO_CUTS["J1"])
                                 | set(SOLO_CUTS["J2"]))), errors)
    for shared in ("P_Front", "P_Right"):
        cut = [k for k in slots if k[0] == shared]
        checks.append("%s (shared by both rings) carries %d leader cut(s)%s"
                      % (shared, len(cut), " %r" % (sorted(cut),) if cut else ""))
        check(not cut, "the shared patch %s carries a leader cut %r -- a "
              "second cut on a ring patch splits the ring pair's shared "
              "corner" % (shared, sorted(cut)), errors)
    # each corner reads its own cells: different patches, different cells
    m1_patch, m2_patch = j1.MemberPatch, j2.MemberPatch
    if m1_patch is None:
        m1_patch = SC.corner_member_pin(list(j1.Strips))[0][0]
    if m2_patch is None:
        m2_patch = SC.corner_member_pin(list(j2.Strips))[0][0]
    cell1 = SC.corner_cell_of(m1_patch, list(j1.Strips))
    cell2 = SC.corner_cell_of(m2_patch, list(j2.Strips))
    checks.append("J1 reads %s cell (u %r, v %r) of %dx%d intervals, "
                  "junction ends (%r, %r)"
                  % (m1_patch.Name, cell1[0], cell1[1], cell1[2], cell1[3],
                     cell1[4], cell1[5]))
    checks.append("J2 reads %s cell (u %r, v %r) of %dx%d intervals, "
                  "junction ends (%r, %r)"
                  % (m2_patch.Name, cell2[0], cell2[1], cell2[2], cell2[3],
                     cell2[4], cell2[5]))
    check(m1_patch is not m2_patch,
          "both corners read the member patch %s -- they would have to share "
          "one leader slot" % m1_patch.Name, errors)
    # the cell each corner reads is the patch's OWN cell, on its own axes
    for corner, patch, cell in ((j1, m1_patch, cell1), (j2, m2_patch, cell2)):
        us, vs = SM.axis_intervals(patch, "U"), SM.axis_intervals(patch, "V")
        got = SM.leader_pair(patch, "U"), SM.leader_pair(patch, "V")
        checks.append("%s's member patch %s: U %s; V %s; cell U%s V%s"
                      % (corner.Name, patch.Name,
                         SM._edges_str(patch, "U"), SM._edges_str(patch, "V"),
                         list(us[cell[0]]), list(vs[cell[1]])))
        # the cell that ends at the leader must be cut back on both axes
        check(SM.ring_corner_gap(patch) is not None,
              "%s's member patch %s carries no real second cut, so its cell "
              "is not the member's region" % (corner.Name, patch.Name), errors)
    # the corners read DIFFERENT cells of the shared patches
    for shared in ("P_Front", "P_Right"):
        p = doc.getObject(shared)
        c1 = SC.corner_cell_of(p, list(j1.Strips))
        c2 = SC.corner_cell_of(p, list(j2.Strips))
        checks.append("%s: J1 reads cell (u %r, v %r) ends (%r, %r); J2 reads "
                      "(u %r, v %r) ends (%r, %r)"
                      % (shared, c1[0], c1[1], c1[4], c1[5],
                         c2[0], c2[1], c2[4], c2[5]))
        check((c1[0], c1[1]) != (c2[0], c2[1]),
              "both corners read %s's cell (%r, %r) -- one surface is covering "
              "the other's" % (shared, c1[0], c1[1]), errors)
    # THE SHARED PATCH'S PIECE IS KEPT TWICE: each corner owns one cell of
    # P_Front and of P_Right, and on a shared patch both come out the SAME
    # cell -- the two objects are the same surface, one per corner.  RECORDED,
    # not endorsed: the number is here because a shared patch is the case a
    # dedupe would change, and a dedupe must announce itself.  (Measured: cell
    # (0, 1) of P_Front at 3368.106687 mm^2 twice, cell (1, 1) of P_Right at
    # 6692.122665 mm^2 twice.)
    for shared in ("P_Front", "P_Right"):
        holders = [(corner.Name, piece.CellU, piece.CellV, piece.Shape.Area)
                   for corner in (j1, j2)
                   for piece in (corner.Pieces or [])
                   if piece.Patch is doc.getObject(shared)]
        checks.append("%s's preserved piece(s), one per corner: %r"
                      % (shared, holders))
        check(len(holders) == 2,
              "%s is held by %d corner piece(s), not one per ring"
              % (shared, len(holders)), errors)
        check(holders[0][1:3] == holders[1][1:3],
              "the two corners keep DIFFERENT cells of %s (%r vs %r) -- the "
              "shared-patch duplication this module records is gone"
              % (shared, holders[0][1:3], holders[1][1:3]), errors)
    doc.recompute()
    doc.recompute()
    touched = [o.Name for o in doc.Objects if "Touched" in o.State]
    checks.append("after two recomputes: %d Touched, %d objects"
                  % (len(touched), len(doc.Objects)))
    check(not touched, "the document does not settle: %r" % touched[:6], errors)
    return {"pass": not errors, "errors": errors, "checks": checks}


# ---- 2. the limit: one leader per axis end -----------------------------

def test_two_corners_on_one_axis_end_cannot_both_hold_a_leader(doc):
    """J1 + J3: both members are P_Top and both need P_Top's U axis at the
    SAME end -- one slot, two leaders.

    Measured: the second corner refuses the rolling construction and falls
    back to the shipped one (J3, `Construction = "shipped"`, no member, no
    pieces), while the first keeps the slot with ITS value.  Both leader
    values are read here, from two SOLO builds, so the clash is two numbers
    in one slot and not a guess.

    WOULD BE RED IF: the second corner rolled anyway (the slot would then
    hold one corner's number while the other corner's cell claims it -- the
    corners would be silently inconsistent), or if the two corners did not
    want the same slot (this pair is then the wrong pair to pin)."""
    errors, checks = [], []
    built = _model(doc)
    check(not built["problems"], "the demo model did not build: %r"
          % (built["problems"],), errors)
    # what each corner wants, alone
    wanted = {}
    for short in ("J1", "J3"):
        solo = FreeCAD.newDocument("_solo_" + short)
        try:
            FreeCAD.setActiveDocument(solo.Name)
            _model(solo)
            corner = _corner(solo, short)
            wanted[short] = _slots(solo)
            checks.append("%s alone: %r, cuts %r"
                          % (short, getattr(corner, "Construction", None),
                             sorted("%s.%s=%.6f" % (k + (v,))
                                    for k, v in wanted[short].items())))
        finally:
            FreeCAD.closeDocument(solo.Name)
        FreeCAD.setActiveDocument(doc.Name)
    left, right = set(wanted["J1"]), set(wanted["J3"])
    checks.append("J1 wants %r; J3 wants %r; the slots BOTH want: %r"
                  % (sorted("%s.%s" % k for k in left),
                     sorted("%s.%s" % k for k in right),
                     sorted("%s.%s" % k for k in (left & right))))
    check(left & right, "J1 and J3 do not want a common leader slot -- this "
          "pair no longer pins the one-leader-per-axis-end limit", errors)
    for slot in left & right:
        a = wanted["J1"][slot]
        b = wanted["J3"][slot]
        checks.append("the clashing slot %s.%s: J1 %.9f, J3 %.9f -- "
                      "difference %.3e"
                      % (slot[0], slot[1], a, b, abs(a - b)))
        check(abs(a - b) > 1e-6,
              "%s.%s is the same number for both corners (%.9f) -- there is "
              "no clash left to express" % (slot[0], slot[1], a), errors)
    # both on one model
    j1 = _corner(doc, "J1")
    j3 = _corner(doc, "J3")
    if j1 is None or j3 is None:
        return {"pass": False, "checks": checks,
                "errors": ["a corner refused outright: J1=%r J3=%r"
                           % (j1, j3)]}
    checks.append("built together: J1 %r (%d poles, %d pieces), J3 %r "
                  "(%d poles, %d pieces)"
                  % (j1.Construction, len(j1.Poles), len(j1.Pieces or []),
                     j3.Construction, len(j3.Poles), len(j3.Pieces or [])))
    check(j1.Construction == "rolling",
          "the FIRST corner is no longer rolling (%r)" % j1.Construction,
          errors)
    check(j3.Construction == "shipped",
          "the second corner did not fall back to the shipped construction "
          "(%r) -- two different leaders in one slot are not expressible, so "
          "this build must say so" % j3.Construction, errors)
    check(not (j3.Pieces or []),
          "the shipped fallback kept %d preserved pieces"
          % len(j3.Pieces or []), errors)
    slots = _slots(doc)
    for slot, value in wanted["J1"].items():
        checks.append("after both: %s.%s = %.9f (J1's own %.9f)"
                      % (slot[0], slot[1], slots.get(slot, float("nan")),
                         value))
        check(slot in slots and abs(slots[slot] - value) < 1e-9,
              "J1's cut %s.%s did not survive the second corner"
              % (slot[0], slot[1]), errors)
    return {"pass": not errors, "errors": errors, "checks": checks}


# ---- 3. the pair matrix ------------------------------------------------

def _pair_outcome(doc, first, second):
    """Build both corners of one pair, in that order, and read what is left.

    ("none" when the stage created nothing, "empty" when the object exists
    with no net -- its ring stopped assembling -- else "built")."""
    _fresh(doc)
    a = _corner(doc, first)
    b = _corner(doc, second)
    out = []
    for corner in (a, b):
        if corner is None:
            out.append((None, "none"))
        elif not (getattr(corner, "Poles", None) or []):
            out.append((getattr(corner, "Construction", "") or None, "empty"))
        else:
            out.append((getattr(corner, "Construction", "") or None, "built"))
    return out


def test_the_pair_matrix_on_the_demo(doc):
    """Every pair of the demo's junctions, in the ring order J1..J4.

    The table (`PAIR_MATRIX`) is the measurement, and it reads:

      J1+J2, J1+J4, J2+J3  two rolling corners, both built -- the pairs whose
                           member patches (and the axis ends they cut) do not
                           collide;
      J1+J3                J3 falls back to the shipped corner: same member
                           patch, same axis end;
      J2+J4                J4 builds NOTHING: J2's cut sits on an axis end
                           J4's ring reads;
      J3+J4                J4 rolls and J3's ring stops assembling -- the
                           FIRST corner is the casualty.

    WOULD BE RED IF: any row changed.  A row changing is news -- a fix for the
    one-slot limit, or a new collision -- and must be announced, not absorbed.
    """
    errors, checks = [], []
    for first, second in PAIR_MATRIX:
        got = _pair_outcome(doc, first, second)
        want = PAIR_MATRIX[(first, second)]
        checks.append("%s then %s -> %r/%s then %r/%s (recorded %r/%s then "
                      "%r/%s)"
                      % (first, second, got[0][0], got[0][1],
                         got[1][0], got[1][1], want[0], want[1],
                         want[2], want[3]))
        check(got[0][0] == want[0],
              "%s then %s: the first corner is %r, the recorded construction "
              "is %r" % (first, second, got[0][0], want[0]), errors)
        check(got[0][1] == want[1],
              "%s then %s: the first corner reads %r, the recorded state is "
              "%r" % (first, second, got[0][1], want[1]), errors)
        check(got[1][0] == want[2],
              "%s then %s: the second corner is %r, the recorded construction "
              "is %r" % (first, second, got[1][0], want[2]), errors)
        check(got[1][1] == want[3],
              "%s then %s: the second corner reads %r, the recorded state is "
              "%r" % (first, second, got[1][1], want[3]), errors)
    return {"pass": not errors, "errors": errors, "checks": checks}


# ---- 4. deleting one corner -------------------------------------------

def test_deleting_one_rolled_corner_leaves_the_other_untouched(doc):
    """J1 + J2, then J1 is deleted.

    (a) the survivor J2 is untouched -- its 36 poles, its weights, its five
        pieces' nets and its 6x6 are byte-identical (0.00e+00);
    (b) the survivor's cuts are still on its own member patch, with the same
        values;
    (c) the shared patches (P_Front, P_Right) keep exactly what they had --
        no cut at all;
    (d) the deleted corner's own surfaces are GONE: no preserved piece and no
        triangular member of J1's are left in the document;
    and the deleted corner's cut is undone on P_Top (a sentinel), so its
    patch is a plain banded patch again.

    WOULD BE RED IF: a J1 piece survived, J2's net moved by any amount, J2's
    cut disappeared, or P_Top kept J1's leader."""
    errors, checks = [], []
    _model(doc)
    j1 = _corner(doc, "J1")
    j2 = _corner(doc, "J2")
    if j1 is None or j2 is None:
        return {"pass": False, "checks": checks,
                "errors": ["a corner refused: %r / %r" % (j1, j2)]}
    before2 = {"poles": [tuple(v) for v in j2.Poles],
               "weights": [float(w) for w in j2.Weights],
               "pieces": {p.Name: [tuple(v) for v in p.Poles]
                          for p in (j2.Pieces or [])},
               "member": [tuple(v) for v in
                          (getattr(_member(doc, j2), "Poles", None) or [])],
               "construction": j2.Construction}
    j1_pieces = [p.Name for p in (j1.Pieces or [])]
    j1_member = getattr(_member(doc, j1), "Name", None)
    j1_cuts = {k: v for k, v in _slots(doc).items()
               if k in set(SOLO_CUTS["J1"])}
    survivor_cuts = {k: v for k, v in _slots(doc).items()
                     if k in set(SOLO_CUTS["J2"])}
    shared_before = {name: _snapshot(doc)["patch:" + name]
                     for name in ("P_Front", "P_Right")}
    checks.append("before the delete: J1 cuts %r, J2 cuts %r, J1 pieces %r"
                  % (sorted("%s.%s" % k for k in j1_cuts),
                     sorted("%s.%s" % k for k in survivor_cuts),
                     j1_pieces))

    doc.removeObject(j1.Name)
    doc.recompute()
    doc.recompute()

    names = {o.Name for o in doc.Objects}
    for name in j1_pieces:
        check(name not in names,
              "the deleted corner's preserved piece %s outlived it" % name,
              errors)
    if j1_member is not None:
        check(j1_member not in names,
              "the deleted corner's triangular member %s outlived it"
              % j1_member, errors)
    left = [o.Name for o in doc.Objects
            if getattr(o, "object_type", "") == "PreservedPiece"]
    checks.append("after the delete: %d preserved piece(s) left, %r"
                  % (len(left), sorted(left)))
    check(len(left) == 5, "the survivor keeps %d pieces, not 5" % len(left),
          errors)
    # (a) the survivor is untouched
    d = _pole_delta(before2["poles"], j2.Poles)
    w = max([abs(a - b) for a, b in zip(before2["weights"], j2.Weights)]
            or [0.0])
    checks.append("J2's 6x6 after the delete: pole delta %.3e, weight delta "
                  "%.3e, construction %r"
                  % (d, w, j2.Construction))
    check(d == 0.0, "the survivor's corner net moved by %.3e mm" % d, errors)
    check(w == 0.0, "the survivor's weights moved by %.3e" % w, errors)
    check(j2.Construction == "rolling",
          "the survivor is no longer rolling (%r)" % j2.Construction, errors)
    member2 = _member(doc, j2)
    check(member2 is not None and bool(member2.Poles),
          "the survivor lost its triangular member", errors)
    if member2 is not None:
        dm = _pole_delta(before2["member"], member2.Poles)
        checks.append("J2's member after the delete: pole delta %.3e" % dm)
        check(dm == 0.0, "the survivor's member moved by %.3e mm" % dm, errors)
    for piece in (j2.Pieces or []):
        want = before2["pieces"].get(piece.Name)
        if want is None:
            checks.append("%s is a NEW piece (the cell set moved)" % piece.Name)
            check(False, "the survivor gained the piece %s" % piece.Name,
                  errors)
            continue
        dp = _pole_delta(want, piece.Poles)
        checks.append("%s: pole delta %.3e" % (piece.Name, dp))
        check(dp == 0.0, "the survivor's piece %s moved by %.3e mm"
              % (piece.Name, dp), errors)
    # (b) the survivor's cuts, unchanged
    slots = _slots(doc)
    for slot, value in survivor_cuts.items():
        checks.append("survivor cut %s.%s = %r (was %.9f)"
                      % (slot[0], slot[1], slots.get(slot), value))
        check(slot in slots and abs(slots[slot] - value) < CUT_TOL,
              "the survivor's cut %s.%s went with the other corner"
              % (slot[0], slot[1]), errors)
    # the deleted corner's cut is undone
    for slot in j1_cuts:
        check(slot not in slots,
              "the deleted corner's cut %s.%s is still on the patch"
              % (slot[0], slot[1]), errors)
    # (c) the shared patches keep exactly what they had
    for name, want in shared_before.items():
        got = _snapshot(doc)["patch:" + name]
        d2 = [x for x in _delta({"patch:" + name: want},
                                {"patch:" + name: got})]
        checks.append("%s after the delete: %s"
                      % (name, "unchanged" if not d2
                         else "; ".join("%s %r" % (f, v) for _k, f, v in d2)))
        check(not d2, "the shared patch %s changed when the other corner was "
              "deleted: %r" % (name, d2), errors)
    doc.recompute()
    doc.recompute()
    touched = [o.Name for o in doc.Objects if "Touched" in o.State]
    checks.append("after the delete: %d objects, %d Touched"
                  % (len(doc.Objects), len(touched)))
    check(not touched, "the document does not settle after the delete: %r"
          % touched[:6], errors)
    return {"pass": not errors, "errors": errors, "checks": checks}


# ---- 5. deleting both: the pre-corner state, byte for byte --------------

def test_deleting_the_last_rolled_corner_restores_the_model_byte_identically(doc):
    """Two corners out and back in again: every patch and every strip reads
    exactly what it read BEFORE the corner stage touched it.

    The snapshot is taken after the model's blends are built and before the
    first corner: each patch's two band-edge pairs, its two leader pairs, its
    16 poles, its 16 weights, its subgrid count and its hidden cells, and each
    of the 8 strips' 24 poles and weights.  After both corners are deleted the
    same snapshot is compared FIELD BY FIELD, so the answer is a maximum
    difference per field, not a "looks the same".

    WOULD BE RED IF: any field differs -- a leader left behind, a subgrid
    count still 12 instead of 6, a hidden cell still hidden, a strip still
    built from a cut cell."""
    errors, checks = [], []
    _model(doc)
    pre = _snapshot(doc)
    objects_before = len(doc.Objects)
    checks.append("pre-corner: %d object(s), %d patch field(s) and %d strip "
                  "field(s) to compare"
                  % (objects_before,
                     sum(len(v) for k, v in pre.items()
                         if k.startswith("patch:")),
                     sum(len(v) for k, v in pre.items()
                         if k.startswith("strip:"))))
    j1 = _corner(doc, "J1")
    j2 = _corner(doc, "J2")
    if j1 is None or j2 is None:
        return {"pass": False, "checks": checks,
                "errors": ["a corner refused: %r / %r" % (j1, j2)]}
    mid = _snapshot(doc)
    checks.append("with both corners: %d object(s), %d patch field(s) and %d "
                  "strip field(s) differ from the pre-corner state"
                  % (len(doc.Objects),
                     len([1 for k, f, _v in _delta(pre, mid)
                          if k.startswith("patch:")]),
                     len([1 for k, f, _v in _delta(pre, mid)
                          if k.startswith("strip:")])))
    check(_delta(pre, mid), "the two corners changed NOTHING -- the test is "
          "measuring an empty change", errors)
    doc.removeObject(j1.Name)
    doc.recompute()
    doc.recompute()
    doc.removeObject(j2.Name)
    doc.recompute()
    doc.recompute()
    post = _snapshot(doc)
    delta = _delta(pre, post)
    for key, field, value in delta:
        checks.append("DIFFERS: %s.%s = %r" % (key, field, value))
    checks.append("after both deletes: %d object(s) (%d before the corners), "
                  "%d difference(s) from the pre-corner state"
                  % (len(doc.Objects), objects_before, len(delta)))
    check(not delta, "the model did not come back: %r" % (delta[:6],), errors)
    leftovers = [o.Name for o in doc.Objects
                 if getattr(o, "object_type", "")
                 in ("PreservedPiece", "RollingMemberFace")]
    checks.append("corner roles left in the tree: %r" % leftovers)
    check(not leftovers, "the deleted corners left %r behind" % leftovers,
          errors)
    check(len(doc.Objects) == objects_before,
          "the document has %d objects; the demo model without corners has "
          "%d" % (len(doc.Objects), objects_before), errors)
    touched = [o.Name for o in doc.Objects if "Touched" in o.State]
    check(not touched, "the document does not settle: %r" % touched[:6], errors)
    return {"pass": not errors, "errors": errors, "checks": checks}


# ---- 6. the pieces follow a band-edge edit on a shared patch -----------

def test_the_pieces_follow_a_band_edge_edit_on_a_shared_patch(doc):
    """J1 + J2, then P_Front's V band edge is moved.

    P_Front is the patch both rings share and neither cuts, and each corner
    keeps one piece of it (`..._P_Front_beyond_both`).  A piece is the
    patch's OWN cell (`Patch.getSubgrid`), so moving the band edge must move
    the piece: its parameter rectangle becomes the patch's interval pair and
    its net the patch's cell net -- for BOTH corners' pieces at once, since
    they are cells of the same patch.

    WOULD BE RED IF: a piece kept the old rectangle, or its net stopped being
    the patch's cell (a stale rectangle is the failure mode a cached piece
    would have)."""
    errors, checks = [], []
    _model(doc)
    j1 = _corner(doc, "J1")
    j2 = _corner(doc, "J2")
    front = doc.getObject("P_Front")
    if j1 is None or j2 is None or front is None:
        return {"pass": False, "checks": checks,
                "errors": ["a corner refused: %r / %r / %r"
                           % (j1, j2, front)]}
    pieces = [p for p in list(j1.Pieces or []) + list(j2.Pieces or [])
              if p.Patch is front]
    checks.append("pieces of P_Front: %r"
                  % [(p.Name, p.CellU, p.CellV, p.U0, p.U1, p.V0, p.V1)
                     for p in pieces])
    check(len(pieces) == 2, "P_Front carries %d pieces, not 2 (one per ring)"
          % len(pieces), errors)
    before = {p.Name: (p.U0, p.U1, p.V0, p.V1) for p in pieces}
    old = SM.split_pair(front, "V")
    front.VSplit1 = 0.2
    doc.recompute()
    doc.recompute()
    checks.append("P_Front V band edges %r -> %r; intervals %r"
                  % (old, SM.split_pair(front, "V"),
                     SM.axis_intervals(front, "V")))
    check(SM.split_pair(front, "V") != old,
          "P_Front's V band edge did not move (%r)" % (old,), errors)
    for p in pieces:
        us = SM.axis_intervals(p.Patch, "U")
        vs = SM.axis_intervals(p.Patch, "V")
        want = (us[p.CellU][0], us[p.CellU][1], vs[p.CellV][0],
                vs[p.CellV][1])
        got = (p.U0, p.U1, p.V0, p.V1)
        poles2d, weights2d = front.Proxy.getSubgrid(want[0], want[1],
                                                    want[2], want[3])
        want_poles = [poles2d[r][c] for r in range(4) for c in range(4)]
        dp = _pole_delta(want_poles, list(p.Poles))
        checks.append("%s: rectangle %r -> %r, net parity %.3e mm, area %.6f"
                      % (p.Name, before.get(p.Name), got, dp, p.Shape.Area))
        check(got == want, "%s kept the rectangle %r; P_Front's cell is %r"
              % (p.Name, got, want), errors)
        check(dp <= 1e-12, "%s is not P_Front's own cell any more (%.3e mm)"
              % (p.Name, dp), errors)
    for corner in (j1, j2):
        checks.append("%s after the edit: %r, %d poles, %d pieces"
                      % (corner.Name, corner.Construction,
                         len(corner.Poles or []), len(corner.Pieces or [])))
        check(corner.Construction == "rolling",
              "%s is no longer rolling after a band-edge edit on a shared "
              "patch (%r)" % (corner.Name, corner.Construction), errors)
        check(len(corner.Poles or []) == 36,
              "%s's net is %d poles after the edit, not 36"
              % (corner.Name, len(corner.Poles or [])), errors)
    doc.recompute()
    doc.recompute()
    touched = [o.Name for o in doc.Objects if "Touched" in o.State]
    check(not touched, "the document does not settle after the edit: %r"
          % touched[:6], errors)
    return {"pass": not errors, "errors": errors, "checks": checks}


# ---- 7. save and reopen ------------------------------------------------

def test_two_rolled_corners_come_back_from_a_saved_document(doc):
    """Save the two-corner model, reopen it, and delete one corner THERE.

    Everything the corner owns must survive the round trip: both corners with
    `Construction = "rolling"`, both members, all ten preserved pieces with
    their cells, and the two write logs (`_CutRecord`).  And the delete path
    must work on the REOPENED document -- `onDocumentRestored` installs the
    release watcher, so a corner that is reopened can still give its patch
    back.  That is the difference between a revert that works in the session
    that built the corner and one that works on the owner's saved file.

    WOULD BE RED IF: a piece or a member failed to come back, a construction
    came back empty, or the reopened corner's deletion left its cut on the
    patch."""
    errors, checks = [], []
    _model(doc)
    j1 = _corner(doc, "J1")
    j2 = _corner(doc, "J2")
    if j1 is None or j2 is None:
        return {"pass": False, "checks": checks,
                "errors": ["a corner refused: %r / %r" % (j1, j2)]}
    cut_before = _slots(doc)
    pieces_before = sorted(p.Name for p in list(j1.Pieces or [])
                           + list(j2.Pieces or []))
    j1_name, j2_name = j1.Name, j2.Name
    tmpdir = tempfile.mkdtemp(prefix="silk_two_corners_")
    path = os.path.join(tmpdir, "two_corners.FCStd")
    # saveCopy, not saveAs: the harness document must stay usable after this
    # test (saveAs renames it to the file's own label), and the question here
    # is what a SAVED file carries, not what the live document is called.
    doc.saveCopy(path)
    doc_name = doc.Name
    reopened = FreeCAD.openDocument(path)
    FreeCAD.setActiveDocument(reopened.Name)
    try:
        reopened.recompute()
        reopened.recompute()
        corners = [o for o in reopened.Objects
                   if getattr(o, "object_type", "") == "CornerBlend"]
        members = [o for o in reopened.Objects
                   if getattr(o, "object_type", "") == "RollingMemberFace"]
        pieces = sorted(o.Name for o in reopened.Objects
                        if getattr(o, "object_type", "") == "PreservedPiece")
        checks.append("reopened: %d corner(s) %r, %d member(s), %d piece(s)"
                      % (len(corners), sorted(c.Name for c in corners),
                         len(members), len(pieces)))
        check(len(corners) == 2, "the reopened document has %d corners, not 2"
              % len(corners), errors)
        for c in corners:
            checks.append("%s: construction %r, %d poles, record %r"
                          % (c.Name, c.Construction, len(c.Poles or []),
                             list(getattr(c, "_CutRecord", None) or [])))
            check(c.Construction == "rolling",
                  "the reopened corner %s reads %r, not rolling"
                  % (c.Name, c.Construction), errors)
            check(len(c.Poles or []) == 36,
                  "the reopened corner %s has %d poles, not 36"
                  % (c.Name, len(c.Poles or [])), errors)
            check(len(getattr(c, "Pieces", None) or []) == 5,
                  "the reopened corner %s carries %d pieces, not 5"
                  % (c.Name, len(getattr(c, "Pieces", None) or [])), errors)
            check(bool(getattr(c, "_CutRecord", None) or []),
                  "the reopened corner %s lost its write log, so its cut can "
                  "never be undone" % c.Name, errors)
        check(pieces == pieces_before,
              "the pieces changed across the round trip: %r -> %r"
              % (pieces_before, pieces), errors)
        check(len(members) == 2, "%d triangular member(s) came back, not 2"
              % len(members), errors)
        # and the delete path still works on a REOPENED corner
        victim = reopened.getObject(j1_name)
        survivor = reopened.getObject(j2_name)
        if victim is None or survivor is None:
            checks.append("the corners came back under other names: %r"
                          % [c.Name for c in corners])
        else:
            survivor_poles = [tuple(v) for v in survivor.Poles]
            victim_cuts = {k: v for k, v in cut_before.items()
                           if k in set(SOLO_CUTS["J1"])}
            victim_name = victim.Name
            reopened.removeObject(victim_name)
            reopened.recompute()
            reopened.recompute()
            slots = _slots(reopened)
            checks.append("after deleting the reopened %s: survivor %d poles, "
                          "cuts %r" % (victim_name,
                                       len(survivor.Poles or []),
                                       sorted("%s.%s" % k for k in slots)))
            check(_pole_delta(survivor_poles, survivor.Poles) == 0.0,
                  "the survivor moved when the reopened corner was deleted",
                  errors)
            for slot in victim_cuts:
                check(slot not in slots,
                      "the reopened corner's cut %s.%s survived its deletion"
                      % (slot[0], slot[1]), errors)
            for slot, value in cut_before.items():
                if slot in victim_cuts:
                    continue
                check(slot in slots and abs(slots[slot] - value) < CUT_TOL,
                      "the reopened survivor's cut %s.%s went missing"
                      % (slot[0], slot[1]), errors)
            touched = [o.Name for o in reopened.Objects
                       if "Touched" in o.State]
            check(not touched, "the reopened document does not settle: %r"
                  % touched[:6], errors)
    finally:
        FreeCAD.closeDocument(reopened.Name)
        try:
            os.remove(path)
            os.rmdir(tmpdir)
        except OSError:
            pass
        FreeCAD.setActiveDocument(doc_name)
    return {"pass": not errors, "errors": errors, "checks": checks}


# ---- 8. two documents, the same names ----------------------------------

def test_deleting_a_corner_does_not_release_a_same_named_corner_elsewhere(doc):
    """Two documents, one corner each, under the SAME names: deleting the
    corner in one must not touch the corner in the other.

    An observer is registered per APPLICATION and sees every document's
    deletions, so a release that matches on the object's NAME alone fires for
    a same-named corner in another document -- and it would strip a LIVE
    corner's pieces and cuts in a document nobody asked about.  Measured
    before the guard: deleting `CB_J1_FrontTopRight` in a test document left
    the open artifact's two corners with 12 objects missing (both members,
    all ten pieces, both cut records) while both corners were still in the
    tree.

    WOULD BE RED IF: the untouched document's corner lost its member, its
    pieces or its cut, or its patches came back uncut."""
    errors, checks = [], []
    first = doc
    _model(first)
    keep = _corner(first, "J1")
    second = FreeCAD.newDocument("_two_corners_second")
    try:
        FreeCAD.setActiveDocument(second.Name)
        _model(second)
        doomed = _corner(second, "J1")
        if keep is None or doomed is None:
            return {"pass": False, "checks": checks,
                    "errors": ["a corner refused: %r / %r" % (keep, doomed)]}
        check(keep.Name == doomed.Name,
              "the two corners are not the same name (%r vs %r), so this "
              "test is not measuring a name collision"
              % (keep.Name, doomed.Name), errors)
        before_poles = [tuple(v) for v in keep.Poles]
        before_pieces = sorted(p.Name for p in (keep.Pieces or []))
        before_record = list(getattr(keep, "_CutRecord", None) or [])
        before_slots = _slots(first)
        checks.append("the document that must NOT change: %s %r, %d poles, "
                      "%d pieces, record %r, cuts %r"
                      % (keep.Name, keep.Construction, len(before_poles),
                         len(before_pieces), before_record,
                         sorted("%s.%s" % k for k in before_slots)))
        doomed_name = doomed.Name
        FreeCAD.setActiveDocument(second.Name)
        second.removeObject(doomed_name)
        second.recompute()
        second.recompute()
        check(second.getObject(doomed_name) is None,
              "the corner deleted in its own document is still there", errors)
        # the OTHER document
        FreeCAD.setActiveDocument(first.Name)
        first.recompute()
        first.recompute()
        names = {o.Name for o in first.Objects}
        checks.append("the untouched document after the other one deleted its "
                      "corner: %d objects, %d piece(s), %d cut(s) (%r)"
                      % (len(first.Objects),
                         len([o for o in first.Objects
                              if getattr(o, "object_type", "")
                              == "PreservedPiece"]),
                         len(_slots(first)),
                         sorted("%s.%s" % k for k in _slots(first))))
        check(len(keep.Poles or []) == 36,
              "the untouched corner reads %d poles, not 36"
              % len(keep.Poles or []), errors)
        check(_pole_delta(before_poles, keep.Poles) == 0.0,
              "the untouched corner's net moved", errors)
        for name in before_pieces:
            check(name in names,
                  "the untouched corner's piece %s was released by the OTHER "
                  "document's delete" % name, errors)
        check(sorted(p.Name for p in (keep.Pieces or [])) == before_pieces,
              "the untouched corner's piece list changed: %r"
              % sorted(p.Name for p in (keep.Pieces or [])), errors)
        check(list(getattr(keep, "_CutRecord", None) or []) == before_record,
              "the untouched corner lost its write log", errors)
        check(_slots(first) == before_slots,
              "the untouched document's cuts changed: %r"
              % sorted("%s.%s" % k for k in _slots(first)), errors)
        check(_member(first, keep) is not None,
              "the untouched corner lost its triangular member", errors)
    finally:
        FreeCAD.closeDocument(second.Name)
        FreeCAD.setActiveDocument(doc.Name)
    return {"pass": not errors, "errors": errors, "checks": checks}


ALL_TESTS = [
    test_two_rolled_corners_share_patches_and_each_reads_its_own_cells,
    test_two_corners_on_one_axis_end_cannot_both_hold_a_leader,
    test_the_pair_matrix_on_the_demo,
    test_deleting_one_rolled_corner_leaves_the_other_untouched,
    test_deleting_the_last_rolled_corner_restores_the_model_byte_identically,
    test_the_pieces_follow_a_band_edge_edit_on_a_shared_patch,
    test_two_rolled_corners_come_back_from_a_saved_document,
    test_deleting_a_corner_does_not_release_a_same_named_corner_elsewhere,
]
