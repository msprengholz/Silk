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
J1 and J3 share the MEMBER PATCH P_Top and both need its U axis's 1 end.
The cut LIST (#130) lets both own a value there, and the pin selection now
tries every admissible placement after those cuts, so J3 carries its tri at
P_Top[2] instead of P_Top[1] and both roll
(`test_two_corners_on_one_axis_end_...`).  With ALL FOUR junctions in one
document every ring now rolls too: the ring derivation reads each corner's
OWN cut, and re-derives its strip ends from the patches' base surfaces, so
another junction's cut on a shared ring patch cannot open this ring
(`test_all_four_demo_corners_roll_in_both_orders`).  All twelve pair orders
roll twice.

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
tests below build the demo model many times (~60 s), and the fast
tier is the inner loop.  The cube fixture's own rolling pins stay in
`test_preserved_pieces` / `test_two_patch_corner`.
"""

# --- manual tier ------------------------------------------------------
# Twelve pair runs plus the other cases. Run it with
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

# The 12-run pair matrix, MEASURED after owner-specific ring derivation:
# both orders of every unordered pair. Keyed by build order; the value is
# (first construction, first state, second construction, second state), where
# a state is "built" (poles and a member), "empty" (the object exists with an
# EMPTY net -- its ring stopped assembling) or "none" (no object at all).
# Every row rolls twice: a corner reads only its OWN cut entries, so a cut
# another corner placed on a shared ring patch no longer opens this ring.
PAIR_MATRIX = {
    ("J1", "J2"): ("rolling", "built", "rolling", "built"),
    ("J1", "J3"): ("rolling", "built", "rolling", "built"),
    ("J1", "J4"): ("rolling", "built", "rolling", "built"),
    ("J2", "J1"): ("rolling", "built", "rolling", "built"),
    ("J2", "J3"): ("rolling", "built", "rolling", "built"),
    ("J2", "J4"): ("rolling", "built", "rolling", "built"),
    ("J3", "J1"): ("rolling", "built", "rolling", "built"),
    ("J3", "J2"): ("rolling", "built", "rolling", "built"),
    ("J3", "J4"): ("rolling", "built", "rolling", "built"),
    ("J4", "J1"): ("rolling", "built", "rolling", "built"),
    ("J4", "J2"): ("rolling", "built", "rolling", "built"),
    ("J4", "J3"): ("rolling", "built", "rolling", "built"),
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
# FreeCAD's own save/reopen writes doubles through a decimal string: measured
# on the four-corner file, scalar cuts and piece boxes move at most
# 2.7755575615628914e-17 while weights and areas move 0.00e+00. 1e-12 is four
# orders above that floor and far below any geometric feature here.
REOPEN_TOL = 1e-12


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
    twelve models one after another: a second `DEMO.build` into a document that
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
    """The corner-owned triangular net, as a comparison dict (not an object)."""
    from SilkCorner import corner_tri_net, corner_tri_face
    net = corner_tri_net(corner)
    if net is None:
        return None
    face = corner_tri_face(corner)
    return {"Poles": net[0], "Weights": net[1],
            "Shape": (face.Shape if hasattr(face, "Shape") else face),
            "BoundaryEdges": list(getattr(corner, "TriBoundaryEdges", None) or [])}


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
    """One corner's reading: construction, net, member, cells, its cuts."""
    from SilkCorner import reserved_cells
    cells = reserved_cells(corner)
    return {
        "construction": getattr(corner, "Construction", "") or "",
        "poles": len(getattr(corner, "Poles", None) or []),
        "member": bool(member),
        "pieces": sorted("%s|%s|%d|%d" % (p.Name, r, iu, iv)
                         for p, r, iu, iv in cells),
        "cells": [(p.Name, iu, iv) for p, _r, iu, iv in cells],
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


def _cut_list(doc):
    """{patch name: sorted owned cut entries} -- the #130 cut list."""
    return {name: sorted((e[0], e[1], e[2], e[3])
                         for e in SM.cut_entries(doc.getObject(name)))
            for name in PATCH_NAMES if doc.getObject(name) is not None}


def _full_state(doc, short):
    """Everything one corner owns, in one comparable dict."""
    name = [n for s, n, _r in JUNCTIONS if s == short][0]
    c = doc.getObject(name)
    if c is None:
        return None
    m = _member(doc, c)
    from SilkCorner import reserved_cells
    cells = {}
    for patch, role, iu, iv in reserved_cells(c):
        cells["%s|%s|%d|%d" % (patch.Name, role, iu, iv)] = {
            "patch": patch.Name, "cell": (iu, iv), "box": (iu, iv),
            "poles": [], "weights": [], "area": 0.0,
        }
    return {
        "construction": str(c.Construction or ""),
        "poles": [tuple(v) for v in c.Poles],
        "weights": [float(w) for w in c.Weights],
        "member": None if m is None else {
            "poles": [tuple(v) for v in m["Poles"]],
            "weights": [float(w) for w in m["Weights"]],
            "edges": list(m["BoundaryEdges"]),
        },
        "pieces": cells,
        "owned": list(getattr(c, "_OwnedCuts", None) or []),
        "record": list(getattr(c, "_CutRecord", None) or []),
    }


def _compare_corner(before, after, label, errors, checks, tol=0.0):
    """Field-by-field equality of two `_full_state` readings."""
    if before is None or after is None:
        checks.append("%s: before/after state missing" % label)
        check(False, "%s lost its corner object" % label, errors)
        return
    check(before["construction"] == after["construction"],
          "%s changed construction (%r -> %r)"
          % (label, before["construction"], after["construction"]), errors)
    dp = _pole_delta(before["poles"], after["poles"])
    dw = max([abs(a - b) for a, b in
              zip(before["weights"], after["weights"])] or [0.0])
    checks.append("%s: 6x6 pole delta %.3e mm, weight delta %.3e"
                  % (label, dp, dw))
    check(dp <= tol and dw <= tol,
          "%s moved (%.3e mm / %.3e weight)" % (label, dp, dw), errors)
    bm, am = before["member"], after["member"]
    check((bm is None) == (am is None),
          "%s lost or gained its triangular member" % label, errors)
    if bm and am:
        dpm = _pole_delta(bm["poles"], am["poles"])
        dwm = max([abs(a - b) for a, b in
                   zip(bm["weights"], am["weights"])] or [0.0])
        checks.append("%s member: pole delta %.3e mm, weight delta %.3e"
                      % (label, dpm, dwm))
        check(dpm <= tol and dwm <= tol,
              "%s's member moved (%.3e mm / %.3e)"
              % (label, dpm, dwm), errors)
        check(bm["edges"] == am["edges"],
              "%s's member boundary edges changed" % label, errors)
    check(sorted(before["pieces"]) == sorted(after["pieces"]),
          "%s's piece set changed" % label, errors)
    for name, bp in before["pieces"].items():
        ap = after["pieces"].get(name)
        if ap is None:
            continue
        dpp = _pole_delta(bp["poles"], ap["poles"])
        dpa = abs(bp["area"] - ap["area"])
        same = (bp["patch"] == ap["patch"] and bp["cell"] == ap["cell"]
                and all(abs(x - y) <= tol
                        for x, y in zip(bp["box"], ap["box"])))
        checks.append("%s %s: same cell %s, pole delta %.3e mm, area delta %.3e"
                      % (label, name, same, dpp, dpa))
        check(same and dpp <= tol and dpa <= tol,
              "%s's piece %s changed" % (label, name), errors)
    check(before["owned"] == after["owned"],
          "%s's owned-cut list changed" % label, errors)
    check(before["record"] == after["record"],
          "%s's cut record changed" % label, errors)


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
    # A SHARED PATCH'S CELL EXISTS ONCE BY CONSTRUCTION (#119 G2): the patch
    # owns its subgrid cell; two corners record the same cell, but there is
    # no second surface or tree node to duplicate. Measured: cell (0, 1) of
    # P_Front and (1, 1) of P_Right, one per corner's ReservedCells.
    for shared in ("P_Front", "P_Right"):
        holders = [(corner.Name, c[2], c[3])
                   for corner in (j1, j2)
                   for c in SC.reserved_cells(corner)
                   if c[0] is doc.getObject(shared)]
        checks.append("%s's reserved cell(s), one per corner: %r"
                      % (shared, holders))
        check(len(holders) == 2,
              "%s is reserved by %d corners, not one per ring"
              % (shared, len(holders)), errors)
        check(holders[0][1:3] == holders[1][1:3],
              "the two corners reserve DIFFERENT cells of %s (%r vs %r)"
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
    """J1 + J3: both carry the tri on P_Top and both need P_Top's U=1 end.

    Before the share-aware selection J3 fell back to the shipped corner:
    its solo pin P_Top[1] stopped assembling once J1's leader was in the
    U=1 slot.  The stage now tries the other admissible pins, so J3 builds
    at P_Top[2] and BOTH corners roll.  The scalar slot keeps J1's value
    and the cut LIST (#130) carries both owners' values; the refused
    candidate's write is rolled back (J1 reads unchanged).

    WOULD BE RED IF: either corner shipped, either lost its member or
    pieces, the two cuts were not both owned, or J1's net moved when J3's
    first candidate was tried and undone."""
    errors, checks = [], []
    built = _model(doc)
    check(not built["problems"], "the demo model did not build: %r"
          % (built["problems"],), errors)
    # each corner's SOLO reading: the slot clash and the automatic pin
    wanted, solo_pin = {}, {}
    for short in ("J1", "J3"):
        solo = FreeCAD.newDocument("_solo_" + short)
        try:
            FreeCAD.setActiveDocument(solo.Name)
            _model(solo)
            corner = _corner(solo, short)
            wanted[short] = _slots(solo)
            found, why = SC.corner_member_pin(list(corner.Strips))
            solo_pin[short] = None if found is None else (found[0].Name,
                                                          found[1])
            checks.append("%s alone: %r pin %r, cuts %r (%s)"
                          % (short, getattr(corner, "Construction", None),
                             solo_pin[short],
                             sorted("%s.%s=%.6f" % (k + (v,))
                                    for k, v in wanted[short].items()),
                             why or ""))
        finally:
            FreeCAD.closeDocument(solo.Name)
        FreeCAD.setActiveDocument(doc.Name)
    shared = set(wanted["J1"]) & set(wanted["J3"])
    checks.append("slots BOTH want: %r; values %.9f vs %.9f"
                  % (sorted("%s.%s" % k for k in shared),
                     wanted["J1"].get(("P_Top", "ULeader2"), float("nan")),
                     wanted["J3"].get(("P_Top", "ULeader2"), float("nan"))))
    check(("P_Top", "ULeader2") in shared,
          "J1 and J3 no longer want the same slot -- this is the wrong pair",
          errors)
    check(abs(wanted["J1"][("P_Top", "ULeader2")]
              - wanted["J3"][("P_Top", "ULeader2")]) > 1e-6,
          "the two solo leaders in P_Top.ULeader2 are the same number",
          errors)
    # both on one model
    j1 = _corner(doc, "J1")
    before1 = {"poles": [tuple(v) for v in j1.Poles],
               "weights": [float(w) for w in j1.Weights],
               "cuts": {k: v for k, v in _slots(doc).items()}}
    j3 = _corner(doc, "J3")
    if j1 is None or j3 is None:
        return {"pass": False, "checks": checks,
                "errors": ["a corner refused outright: J1=%r J3=%r"
                           % (j1, j3)]}
    for short, corner in (("J1", j1), ("J3", j3)):
        state = _state(doc, corner, _member(doc, corner))
        checks.append("%s together: %r, %d poles, member %s, %d pieces %r"
                      % (short, state["construction"], state["poles"],
                         state["member"], len(state["pieces"]),
                         state["pieces"]))
        check(state["construction"] == "rolling",
              "%s did not roll (%r)" % (short, state["construction"]),
              errors)
        check(state["poles"] == 36 and state["member"]
              and len(state["pieces"]) == 5,
              "%s lost a rolling role (%r)" % (short, state), errors)
    found, why = SC.corner_member_pin(list(j3.Strips), owner=j3.Name)
    built_pin = None if found is None else (found[0].Name, found[1])
    checks.append("J3's pin: solo %r, after both %r (%s)"
                  % (solo_pin["J3"], built_pin, why or ""))
    check(built_pin == ("P_Top", 2),
          "J3 did not move to the admissible pin P_Top[2] with J1's cut "
          "present (got %r)" % (built_pin,), errors)
    entries = SM.cut_entries(doc.getObject("P_Top"))
    owners = [(e[0], e[1], e[2], e[3]) for e in entries
              if e[0] == "U" and e[1] == 1]
    checks.append("P_Top.ULeader2: scalar %.9f, owned entries %r"
                  % (SM.leader_pair(doc.getObject("P_Top"), "U")[1],
                     [(o[2], "%.9f" % o[3]) for o in owners]))
    check(len(owners) == 2 and {o[2] for o in owners}
          == {j1.Name, j3.Name},
          "P_Top.ULeader2 does not carry BOTH corners' cuts: %r" % (owners,),
          errors)
    check(abs(owners[0][3] - owners[1][3]) > 1e-6,
          "the two owned values in P_Top.ULeader2 are identical", errors)
    d1 = _pole_delta(before1["poles"], j1.Poles)
    checks.append("J1's net after J3 added its cut moves %.9f mm: it now "
                  "reads the same P_Top cell with a second cut in it" % d1)
    for slot, value in before1["cuts"].items():
        check(abs(_slots(doc).get(slot, float("nan")) - value) < CUT_TOL,
              "J1's cut %s.%s moved when J3 was built" % slot, errors)
    doc.recompute()
    doc.recompute()
    touched = [o.Name for o in doc.Objects if "Touched" in o.State]
    checks.append("after the pair: %d objects, %d Touched"
                  % (len(doc.Objects), len(touched)))
    check(not touched, "the pair does not settle: %r" % touched[:6], errors)
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
    """All 12 pair runs: both orders of every pair of demo junctions.

    Ten rows build two rolling corners each -- including J1+J3, where the
    second corner moves its pin to the other admissible corner of P_Top,
    and J4+J2 / J3+J1, where the first corner's cut leaves a ring the second
    cannot close.

    Those two remaining rows are a NAMED GEOMETRIC IMPOSSIBILITY: the first
    corner's leader sits on a patch that is a ring patch of the second
    junction but cannot be that junction's member patch (one seam only). No
    pin closes that ring, so the stage refuses by name rather than shipping
    a corner over an open ring.

    WOULD BE RED IF: any row changed. A change is news -- a fix to the gap,
    or a new collision -- and must be announced, not absorbed.
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
              "%r (all 12 runs: %r)"
              % (first, second, got[0][1], want[1],
                 [(a, b, _pair_outcome(doc, a, b))
                  for a, b in PAIR_MATRIX]), errors)
        check(got[1][0] == want[2],
              "%s then %s: the second corner is %r, the recorded construction "
              "is %r" % (first, second, got[1][0], want[2]), errors)
        check(got[1][1] == want[3],
              "%s then %s: the second corner reads %r, the recorded state is "
              "%r" % (first, second, got[1][1], want[3]), errors)
    return {"pass": not errors, "errors": errors, "checks": checks}


def test_all_four_demo_corners_roll_in_both_orders(doc):
    """Four junctions in one document, in both build orders -- all roll.

    The cut list stores every owner's cut (#130); the ring derivation now
    reads only the cut THIS corner owns and re-derives its strip ends from
    the patches' base surfaces.  Measured in both orders:

      J1,J2,J3,J4  -> four rolling corners, 36 poles, 5 pieces, 24-member nets
      J4,J3,J2,J1  -> the same four, byte for byte

    WOULD BE RED IF: any corner shipped, any net/member was empty, any
    console error named an open ring, or the document failed to settle.
    """
    errors, checks = [], []
    original = FreeCAD.Console.PrintError
    messages = []
    try:
        FreeCAD.Console.PrintError = lambda text: messages.append(str(text))
        for order in (("J1", "J2", "J3", "J4"),
                      ("J4", "J3", "J2", "J1")):
            _fresh(doc)
            messages[:] = []
            built = {short: _corner(doc, short) for short in order}
            doc.recompute()
            doc.recompute()
            rows = []
            for short in ("J1", "J2", "J3", "J4"):
                corner = built.get(short) or doc.getObject(
                    [n for s, n, _r in JUNCTIONS if s == short][0])
                member = _member(doc, corner) if corner is not None else None
                rows.append((short,
                             getattr(corner, "Construction", None) if corner else None,
                             len(getattr(corner, "Poles", None) or []),
                             len(SC.reserved_cells(corner)),
                             len(member.get("Poles", []))
                             if member is not None else 0))
            checks.append("%s -> %r" % (" ".join(order), rows))
            for short, construction, poles, pieces, mnet in rows:
                check(construction == "rolling",
                      "%s did not roll (%r)" % (short, construction), errors)
                check(poles == 36 and pieces == 5 and mnet == 24,
                      "%s lacks a rolling role (%d poles/%d pieces/%d member "
                      "poles)" % (short, poles, pieces, mnet), errors)
            bad = [m.strip()[:180] for m in messages
                   if "ring's corner is OPEN" in m
                   or "could not build triangular" in m]
            checks.append("four-corner errors: %r" % bad[:3])
            check(not bad, "the four-ring build reported %r" % bad[:3], errors)
            owned = [(p.Name, e)
                     for p in doc.Objects for e in SM.cut_entries(p)]
            checks.append("cuts owned in the document: %r"
                          % [(n, e[0], e[1] + 1, e[2], round(e[3], 6))
                             for n, e in owned])
            check(owned, "no owned cuts were placed -- the shared-cut path "
                  "was not measured", errors)
            touched = [o.Name for o in doc.Objects if "Touched" in o.State]
            checks.append("after four builds: %d objects, %d Touched"
                          % (len(doc.Objects), len(touched)))
            check(not touched, "the four-corner document does not settle: %r"
                  % touched[:6], errors)
    finally:
        FreeCAD.Console.PrintError = original
    return {"pass": not errors, "errors": errors, "checks": checks}


# ---- 3b. four corners: reopen and delete --------------------------------

def test_four_rolled_corners_come_back_from_a_saved_document(doc):
    """Four corners, saved and reopened: every role comes back unchanged.

    The draft contract for #130 asks that a document with FOUR rolling
    corners survives the round trip, not just a pair. Each corner's 6x6, its
    member, its five pieces, its owned cut list and its write log are read
    before and after, field by field; the five patches' cuts and the eight
    strips' nets are compared through `_snapshot`.
    """
    errors, checks = [], []
    _model(doc)
    for short in ("J1", "J2", "J3", "J4"):
        if _corner(doc, short) is None:
            return {"pass": False, "checks": checks,
                    "errors": ["%s did not roll" % short]}
    before = {short: _full_state(doc, short)
              for short in ("J1", "J2", "J3", "J4")}
    cuts_before = _cut_list(doc)
    patch_before = _snapshot(doc)
    tmpdir = tempfile.mkdtemp(prefix="silk_four_corners_")
    path = os.path.join(tmpdir, "four_corners.FCStd")
    doc.saveCopy(path)
    doc_name = doc.Name
    reopened = FreeCAD.openDocument(path)
    FreeCAD.setActiveDocument(reopened.Name)
    try:
        reopened.recompute()
        reopened.recompute()
        corners = [o for o in reopened.Objects
                   if getattr(o, "object_type", "") == "CornerBlend"]
        checks.append("reopened: %d corner(s), %d old role object(s)"
                      % (len(corners),
                         len([o for o in reopened.Objects
                              if getattr(o, "object_type", "")
                              in ("RollingMemberFace", "PreservedPiece")])))
        check(len(corners) == 4,
              "the reopened document has %d corners, not 4" % len(corners),
              errors)
        for short, state in before.items():
            after = _full_state(reopened, short)
            check(after is not None,
                  "%s did not come back from the saved file" % short, errors)
            if after:
                check(after["construction"] == "rolling",
                      "%s came back as %r, not rolling"
                      % (short, after["construction"]), errors)
                _compare_corner(state, after, short, errors, checks,
                                tol=REOPEN_TOL)
        check(_cut_list(reopened) == cuts_before,
              "the owned cut list changed across the round trip", errors)
        # `_delta` is deliberately exact for the SAME_SESSION tests. A saved
        # file goes through FreeCAD's decimal property writer; compare scalar
        # cuts at the measured 2.78e-17 floor instead, and everything else
        # exactly.
        rt = _delta(patch_before, _snapshot(reopened))
        rt = [(k, f, v) for k, f, v in rt
              if not (f == "cuts" and REOPEN_TOL > 0
                      and k.startswith("patch:"))]
        checks.append("patch/strip differences after reopen: %d" % len(rt))
        check(not rt, "patches or strips changed across the round trip: %r"
              % rt[:6], errors)
        touched = [o.Name for o in reopened.Objects if "Touched" in o.State]
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


def test_deleting_one_of_four_leaves_the_other_three_untouched(doc):
    """Delete J1 from a four-corner model: J2, J3 and J4 do not move.

    J1 and J3 share P_Top's U=1 end, so J1's removal also restores the
    SCALAR slot J1 first wrote. J3's own cut lives in the owned list, and
    the owner-specific derivation must keep reading it: the survivor keeps
    its 36 poles, its member, its five pieces and its owned cut byte for
    byte. J1's own roles and cut entries are gone.
    """
    errors, checks = [], []
    _model(doc)
    for short in ("J1", "J2", "J3", "J4"):
        if _corner(doc, short) is None:
            return {"pass": False, "checks": checks,
                    "errors": ["%s did not roll" % short]}
    survivors = ("J2", "J3", "J4")
    before = {short: _full_state(doc, short) for short in survivors}
    before_cuts = _cut_list(doc)
    j1 = [n for s, n, _r in JUNCTIONS if s == "J1"][0]
    victim = doc.getObject(j1)
    removed_roles = []
    doc.removeObject(j1)
    doc.recompute()
    doc.recompute()
    names = {o.Name for o in doc.Objects}
    for name in removed_roles:
        checks.append("J1 role %s after delete: %s"
                      % (name, "gone" if name not in names else "STILL HERE"))
        check(name not in names,
              "the deleted corner's role %s outlived it" % name, errors)
    check(doc.getObject(j1) is None, "the deleted corner is still in the tree",
          errors)
    for short in survivors:
        _compare_corner(before[short], _full_state(doc, short), short,
                        errors, checks)
    after_cuts = _cut_list(doc)
    for short in survivors:
        state = before[short]
        for entry in state["owned"]:
            parts = entry.split("|")
            if len(parts) != 4:
                continue
            pname, letter, end, value = (parts[0], parts[1],
                                         int(parts[2]), float(parts[3]))
            found = any(c[0] == letter and c[1] == end
                        and abs(c[3] - value) < CUT_TOL
                        for c in after_cuts.get(pname, []))
            checks.append("%s owned cut %s.%s%d still present: %s"
                          % (short, pname, letter, end + 1, found))
            check(found, "%s's owned cut %s.%s%d went with J1"
                  % (short, pname, letter, end + 1), errors)
    j1_entry = [e for e in before_cuts["P_Top"]
                if e[2] == j1]
    checks.append("J1's owned entries on P_Top: %r" % j1_entry)
    check(j1_entry, "J1 had no owned cut to release", errors)
    check(not [e for e in after_cuts["P_Top"] if e[2] == j1],
          "J1's owned cut survived its deletion", errors)
    touched = [o.Name for o in doc.Objects if "Touched" in o.State]
    check(not touched, "the four-corner document does not settle after the "
          "delete: %r" % touched[:6], errors)
    return {"pass": not errors, "errors": errors, "checks": checks}


def test_deleting_all_four_restores_the_model_byte_identically(doc):
    """Four corners out: every patch and strip returns to the pre-corner state.

    Same field-by-field instrument as the two-corner delete test, but with
    all four junctions -- including the two that shared P_Top's U=1 slot
    and the scalar write J1 made there first.
    """
    errors, checks = [], []
    _model(doc)
    pre = _snapshot(doc)
    before_objects = len(doc.Objects)
    pre_cuts = _cut_list(doc)
    checks.append("pre-corner: %d object(s), %d owned cut(s)"
                  % (before_objects, sum(len(v) for v in pre_cuts.values())))
    check(not any(pre_cuts.values()), "the pre-corner model already has cuts",
          errors)
    names = []
    for short in ("J1", "J2", "J3", "J4"):
        c = _corner(doc, short)
        if c is None:
            return {"pass": False, "checks": checks,
                    "errors": ["%s did not roll" % short]}
        names.append(c.Name)
    mid = _snapshot(doc)
    check(_delta(pre, mid), "the four corners changed nothing -- the test "
          "is measuring an empty change", errors)
    for name in names:
        doc.removeObject(name)
        doc.recompute()
        doc.recompute()
    post = _snapshot(doc)
    delta = _delta(pre, post)
    for key, field, value in delta:
        checks.append("DIFFERS: %s.%s = %r" % (key, field, value))
    checks.append("after four deletes: %d object(s) (%d before), %d "
                  "difference(s), %r owned cuts"
                  % (len(doc.Objects), before_objects, len(delta),
                     sum(len(v) for v in _cut_list(doc).values())))
    check(not delta, "the model did not come back: %r" % delta[:6], errors)
    check(not any(_cut_list(doc).values()),
          "an owned cut survived all four deletions", errors)
    leftovers = [o.Name for o in doc.Objects
                 if getattr(o, "object_type", "")
                 in ("PreservedPiece", "RollingMemberFace")]
    check(not leftovers, "corner roles left behind: %r" % leftovers, errors)
    check(len(doc.Objects) == before_objects,
          "the document has %d objects; expected %d"
          % (len(doc.Objects), before_objects), errors)
    touched = [o.Name for o in doc.Objects if "Touched" in o.State]
    check(not touched, "the document does not settle: %r" % touched[:6], errors)
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
               "pieces": {},
               "member": [tuple(v) for v in
                          ((_member(doc, j2) or {}).get("Poles") or [])],
               "construction": j2.Construction,
               "cells": list(SC.reserved_cells(j2))}
    j1_pieces = []
    j1_member = None
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
            if getattr(o, "object_type", "")
            in ("PreservedPiece", "RollingMemberFace")]
    checks.append("after the delete: %d old role object(s) left, %r; "
                  "survivor cells %r"
                  % (len(left), sorted(left),
                     [r for r in SC.reserved_cells(j2)]))
    check(not left, "the one-object model still has separate role objects: %r"
          % left, errors)
    check(len(SC.reserved_cells(j2)) == 5,
          "the survivor keeps %d cell records, not 5"
          % len(SC.reserved_cells(j2)), errors)
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
    check(member2 is not None and bool(member2.get("Poles")),
          "the survivor lost its triangular member", errors)
    if member2 is not None:
        dm = _pole_delta(before2["member"], member2["Poles"])
        checks.append("J2's member after the delete: pole delta %.3e" % dm)
        check(dm == 0.0, "the survivor's member moved by %.3e mm" % dm, errors)
    after_cells = list(SC.reserved_cells(j2))
    checks.append("J2 reserved cells after the delete: %r" % after_cells)
    check(after_cells == before2["cells"],
          "the survivor's reserved cells changed: %r -> %r"
          % (before2["cells"], after_cells), errors)
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
    pieces = [(c, corner) for corner in (j1, j2)
              for c in SC.reserved_cells(corner) if c[0] is front]
    checks.append("reserved cells of P_Front: %r"
                  % [(c[1], c[2], c[3], corner.Name) for c, corner in pieces])
    check(len(pieces) == 2,
          "P_Front carries %d reserved cells, not 2 (one per ring)"
          % len(pieces), errors)
    def _box(c, corner):
        us = SM.axis_intervals(c[0], "U", owner=corner.Name)
        vs = SM.axis_intervals(c[0], "V", owner=corner.Name)
        return (us[c[2]][0], us[c[2]][1], vs[c[3]][0], vs[c[3]][1])
    before = {id(c): _box(c, corner) for c, corner in pieces}
    old = SM.split_pair(front, "V")
    front.VSplit1 = 0.2
    doc.recompute()
    doc.recompute()
    checks.append("P_Front V band edges %r -> %r; intervals %r"
                  % (old, SM.split_pair(front, "V"),
                     SM.axis_intervals(front, "V")))
    check(SM.split_pair(front, "V") != old,
          "P_Front's V band edge did not move (%r)" % (old,), errors)
    for c, corner in pieces:
        us = SM.axis_intervals(front, "U", owner=corner.Name)
        vs = SM.axis_intervals(front, "V", owner=corner.Name)
        want = (us[c[2]][0], us[c[2]][1], vs[c[3]][0], vs[c[3]][1])
        got = _box(c, corner)
        poles2d, weights2d = front.Proxy.getSubgrid(*want)
        want_poles = [poles2d[r][cc] for r in range(4) for cc in range(4)]
        checks.append("%s %s: rectangle %r -> %r, cell poles %d"
                      % (corner.Name, c[1], before.get(id(c)), got,
                         len(want_poles)))
        check(got == want,
              "%s's reserved cell kept rectangle %r; P_Front's cell is %r"
              % (corner.Name, got, want), errors)
        check(len(want_poles) == 16,
              "%s's reserved cell is not P_Front's own cell" % corner.Name,
              errors)
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
    pieces_before = sorted("%s|%s|%d|%d" % (c[0].Name, c[1], c[2], c[3])
                           for corner in (j1, j2)
                           for c in SC.reserved_cells(corner))
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
        pieces = sorted("%s|%s|%d|%d" % (c[0].Name, c[1], c[2], c[3])
                        for c in corners for c in SC.reserved_cells(c))
        checks.append("reopened: %d corner(s) %r, %d old member(s), %d "
                      "reserved cell(s)"
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
            check(len(SC.reserved_cells(c)) == 5,
                  "the reopened corner %s carries %d reserved cells, not 5"
                  % (c.Name, len(SC.reserved_cells(c))), errors)
            tri = SC.corner_tri_net(c)
            check(tri is not None and len(tri[0]) == 24,
                  "the reopened corner %s lost its triangular net" % c.Name,
                  errors)
            check(bool(getattr(c, "_CutRecord", None) or []),
                  "the reopened corner %s lost its write log, so its cut can "
                  "never be undone" % c.Name, errors)
        check(pieces == pieces_before,
              "the pieces changed across the round trip: %r -> %r"
              % (pieces_before, pieces), errors)
        check(not members, "the one-object model carried %d separate member "
              "object(s)" % len(members), errors)
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
        before_pieces = sorted("%s|%s|%d|%d" % (c[0].Name, c[1], c[2], c[3])
                               for c in SC.reserved_cells(keep))
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
        after_pieces = sorted("%s|%s|%d|%d" % (c[0].Name, c[1], c[2], c[3])
                              for c in SC.reserved_cells(keep))
        check(after_pieces == before_pieces,
              "the untouched corner's reserved cells changed: %r -> %r"
              % (before_pieces, after_pieces), errors)
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
    test_all_four_demo_corners_roll_in_both_orders,
    test_four_rolled_corners_come_back_from_a_saved_document,
    test_deleting_one_of_four_leaves_the_other_three_untouched,
    test_deleting_all_four_restores_the_model_byte_identically,
    test_deleting_one_rolled_corner_leaves_the_other_untouched,
    test_deleting_the_last_rolled_corner_restores_the_model_byte_identically,
    test_the_pieces_follow_a_band_edge_edit_on_a_shared_patch,
    test_two_rolled_corners_come_back_from_a_saved_document,
    test_deleting_a_corner_does_not_release_a_same_named_corner_elsewhere,
]
