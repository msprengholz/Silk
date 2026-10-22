#!/usr/bin/env python3
"""Tests/two_rolled_corners.py -- MORE THAN ONE ROLLED CORNER, measured (#131).

**What it answers.**  The owner's ask (2026-10-22): *"you need to test if the
patch subdivision for a rolling corner works if there is more than one rolling
corner in a document, as one patch might get subdivided multiple times. of
course, this also has to be revertible when the rolling corners get deleted."*

It prints, on the demo model (`Tests/demo01_fixture_model.py`, 12 Edges, 5
Patches, 8 Blends, built through the ops layer):

  1. THE TWO-CORNER TABLE -- J1 and J2 rolled in one document: every patch's
     two band-edge pairs and two leader pairs, the intervals they cut the
     patch into, and the cell each corner reads of each patch.  Then the two
     corners' own numbers: construction, net size, the tri and the quad, their
     areas and the tri's interior as a fraction of the corner's extent, the
     two cut sides in mm, and the five preserved pieces.
  2. THE ONE-SLOT LIMIT -- J1 and J3 both carry the member on P_Top, and both
     need its U axis's 1 end.  Each corner's own leader for that slot, read
     from two SOLO builds, and what the pair then builds.
  3. THE PAIR MATRIX -- every pair of the demo's four junctions, both build
     orders, with the constructions and the state of both corners afterwards.
  4. THE DELETION TABLE -- J1 deleted: what changed and what stayed, field by
     field (J2's net, its pieces, its member, its cuts, the shared patches,
     the deleted corner's own surfaces).  Then J2 deleted: the whole model
     compared with the state it had BEFORE the first corner touched it.
  5. THE ARTIFACT -- `Resources/Test_files/_inspect/demo_two_corners.FCStd`,
     the demo model with BOTH rolling corners, every role named, left OPEN.

**How it runs.**  Inside the owner's running FreeCAD, over XML-RPC (never
spawns one):

    flock /tmp/silk_rpc.lock -c "python3 Tests/two_rolled_corners.py"

The raw output is kept next to the artifact.

**What it does NOT do.**  It asserts nothing: it is an instrument, and its raw
output is the measurement the two-corner work is decided on.  The pins live in
`Tests/test_two_rolled_corners.py`.
"""

import os
import sys

# --- manual tier ------------------------------------------------------
# A measurement script, not a test module (the name is not `test_*`), so the
# suite never collects it -- stated here so the marker rule sees it.
MANUAL = True

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HERE = os.path.dirname(os.path.abspath(__file__))
RPC_HOST = "127.0.0.1"
RPC_PORT = 9875

ARTIFACT = os.path.join(REPO, "Resources", "Test_files", "_inspect",
                        "demo_two_corners.FCStd")

# The demo's four junctions: the ring of blends around each (`DEMO.CORNERS`).
JUNCTIONS = (
    ("J1", "CB_J1_FrontTopRight", ("B_FT", "B_FR", "B_TR")),
    ("J2", "CB_J2_FrontRightBottom", ("B_FB", "B_FR", "B_BR")),
    ("J3", "CB_J3_TopRightBack", ("B_TR", "B_TBk", "B_BkR")),
    ("J4", "CB_J4_RightBottomBack", ("B_BR", "B_BkB", "B_BkR")),
)
NAME = {short: name for short, name, _ring in JUNCTIONS}
RING = {short: ring for short, _name, ring in JUNCTIONS}

# The maintainer's own corner, for the two figures his file gives: the
# tri/quad area ratio and the tri's interior distance from the quad as a
# fraction of the corner's extent (`docs/research/silk-rolling-corner-66.md`).
HIS_AREA_RATIO = 1439.90 / 5187.83          # 0.2776
HIS_TRI_QUAD_PERCENT = (16.0, 62.0)


# ---------------------------------------------------------------------------
# The in-FreeCAD half
# ---------------------------------------------------------------------------

def _helpers():
    """The imports the measurements need (inside FreeCAD only)."""
    import FreeCAD
    import demo01_fixture_model as DEMO
    import SilkCorner as SC
    import SilkMachinery as SM
    import SilkWorkflowOps as OPS
    return FreeCAD, DEMO, SC, SM, OPS


def _make_doc(label, clear=True):
    import FreeCAD
    if clear:
        for name, d in list(FreeCAD.listDocuments().items()):
            if d.Label == label:
                FreeCAD.closeDocument(name)
    doc = FreeCAD.newDocument(label)
    FreeCAD.setActiveDocument(doc.Name)
    return doc


def _model(doc):
    _FreeCAD, DEMO, _SC, _SM, _OPS = _helpers()
    built = DEMO.build(doc, corners=False)
    doc.recompute()
    doc.recompute()
    return built


def _corner(doc, short, **kw):
    _FreeCAD, _DEMO, _SC, _SM, OPS = _helpers()
    strips = [doc.getObject(b) for b in RING[short]]
    corner = OPS.create_corner_blend(strips, name=NAME[short], **kw)
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
    """{(patch, property): value} -- every leader cut in the document."""
    _FreeCAD, DEMO, _SC, SM, _OPS = _helpers()
    out = {}
    for name, _order, _grid in DEMO.PATCHES:
        p = doc.getObject(name)
        if p is None:
            continue
        for letter in ("U", "V"):
            l1, l2 = SM.leader_pair(p, letter)
            for end, value in ((0, l1), (1, l2)):
                if SM.band_edge(value) is not None:
                    out[(name, SM.leader_cut_prop(letter, end))] = value
    return out


def _edges(p):
    _FreeCAD, _DEMO, _SC, SM, _OPS = _helpers()
    parts = []
    for letter in ("U", "V"):
        s1, s2 = SM.split_pair(p, letter)
        l1, l2 = SM.leader_pair(p, letter)
        parts.append("%sSplit1=%g %sSplit2=%g %sLeader1=%g %sLeader2=%g"
                     % (letter, s1, letter, s2, letter, l1, letter, l2))
    return "; ".join(parts)


def _interior_percent(tri_shape, quad_shape, grid=8):
    """The tri's interior samples' distance to the quad, in % of the corner's
    extent (the maintainer's own reading is 16 %..62 %)."""
    import Part
    face = tri_shape.Faces[0]
    b = face.Surface.bounds()
    bb = quad_shape.BoundBox
    extent = max(bb.XLength, bb.YLength, bb.ZLength) or 1.0
    out = []
    for a in range(1, grid):
        for c in range(1, grid):
            pt = face.Surface.value(b[0] + (b[1] - b[0]) * a / float(grid),
                                    b[2] + (b[3] - b[2]) * c / float(grid))
            out.append(Part.Vertex(pt).distToShape(quad_shape)[0])
    if not out:
        return (0.0, 0.0)
    return (min(out) / extent * 100.0, max(out) / extent * 100.0)


# ---- 1. the two-corner table --------------------------------------------

def two_corner_table():
    """J1 + J2 in one document: the per-patch table and each corner's own."""
    FreeCAD, DEMO, SC, SM, OPS = _helpers()
    out = []

    def emit(line=""):
        out.append(line)

    doc = _make_doc("_two_corners_table")
    _model(doc)
    j1 = _corner(doc, "J1")
    j2 = _corner(doc, "J2")
    if j1 is None or j2 is None:
        emit("J1 %r, J2 %r -- a corner refused (see the console)" % (j1, j2))
        FreeCAD.closeDocument(doc.Name)
        return out
    emit("J1 = %s (%r), J2 = %s (%r), in ONE document"
         % (j1.Name, j1.Construction, j2.Name, j2.Construction))
    emit("")
    emit("  THE PATCHES (both corners' cuts live on their own member patch)")
    emit("    %-9s %-8s %-38s %-24s %s"
         % ("patch", "member of", "cuts (band edges and leader cuts)",
            "intervals U", "intervals V"))
    for name, _order, _grid in DEMO.PATCHES:
        p = doc.getObject(name)
        who = [short for short in ("J1", "J2")
               if getattr((j1 if short == "J1" else j2), "MemberPatch", None) is p
               or (SC.corner_member_pin(
                   list((j1 if short == "J1" else j2).Strips))[0][0] is p)]
        emit("    %-9s %-8s %-38s %-24s %s"
             % (name, ",".join(who) or "-", _edges(p),
                str([tuple(round(v, 6) for v in iv)
                     for iv in SM.axis_intervals(p, "U")]),
                str([tuple(round(v, 6) for v in iv)
                     for iv in SM.axis_intervals(p, "V")])))
    emit("")
    emit("  THE CELL EACH CORNER READS OF EACH PATCH "
         "(iu, iv of nu x nv intervals, junction ends (u, v))")
    for name, _order, _grid in DEMO.PATCHES:
        p = doc.getObject(name)
        row = []
        for short, corner in (("J1", j1), ("J2", j2)):
            c = SC.corner_cell_of(p, list(corner.Strips))
            row.append("%s: cell (%r, %r) of %dx%d, ends (%r, %r)"
                       % (short, c[0], c[1], c[2], c[3], c[4], c[5]))
        emit("    %-9s %s" % (name, "; ".join(row)))
    emit("")
    emit("  THE TWO CORNERS")
    for short, corner in (("J1", j1), ("J2", j2)):
        member = _member(doc, corner)
        pin = getattr(corner, "MemberPatch", None)
        if pin is None:
            found = SC.corner_member_pin(list(corner.Strips))
            pin = found[0][0] if found and found[0] else None
        pieces = list(getattr(corner, "Pieces", None) or [])
        emit("    %s: member patch %r, %d poles, %d weights, construction %r"
             % (short, getattr(pin, "Name", None), len(corner.Poles),
                len(corner.Weights), corner.Construction))
        if member is not None:
            lo, hi = _interior_percent(member.Shape, corner.Shape)
            emit("      tri %.6f mm^2, quad %.6f mm^2, ratio %.4f (his %.4f); "
                 "tri interior -> quad %.2f %%..%.2f %% of the extent "
                 "(his %.0f..%.0f %%)"
                 % (member.Shape.Area, corner.Shape.Area,
                    member.Shape.Area / corner.Shape.Area, HIS_AREA_RATIO,
                    lo, hi, HIS_TRI_QUAD_PERCENT[0], HIS_TRI_QUAD_PERCENT[1]))
        for s in corner.Strips:
            if pin not in (getattr(s, "PatchA", None),
                           getattr(s, "PatchB", None)):
                continue
            reach, why = OPS.seam_cut_reach(s, pin, ring=list(corner.Strips))
            leg, lwhy = OPS.seam_cut_length(s, pin, ring=list(corner.Strips))
            if reach is None:
                emit("      seam %-6s REFUSED %s" % (s.Name, why))
                continue
            emit("      seam %-6s along %s, junction at the %d end, "
                 "corner->setback %.6f mm, cut side %s, learned leader %g, "
                 "reachable max %.6f mm"
                 % (s.Name, reach["along"], reach["corner_end"],
                    reach["corner_mm"],
                    ("%.6f mm" % leg) if leg is not None else "REFUSED %s" % lwhy,
                    SM.leader_pair(pin, reach["along"])[reach["corner_end"]],
                    reach["max_mm"]))
        emit("      %d preserved piece(s):" % len(pieces))
        for p in pieces:
            emit("        %-46s %-10s of %-8s cell (%d, %d), u [%.6f, %.6f] "
                 "v [%.6f, %.6f], area %.6f"
                 % (p.Name, p.Role, p.Patch.Name, p.CellU, p.CellV,
                    p.U0, p.U1, p.V0, p.V1, p.Shape.Area))
    emit("")
    emit("  LEADER CUTS IN THE DOCUMENT: %s"
         % sorted("%s.%s=%.9f" % (k + (v,))
                  for k, v in _slots(doc).items()))
    touched = [o.Name for o in doc.Objects if "Touched" in o.State]
    emit("  the document settles: %d Touched, %d objects"
         % (len(touched), len(doc.Objects)))
    FreeCAD.closeDocument(doc.Name)
    return out


# ---- 2. the one-slot limit ---------------------------------------------

def solo_slots(short):
    """The leader cuts one junction writes when it is ALONE, and the slots."""
    FreeCAD, _DEMO, SC, _SM, _OPS = _helpers()
    doc = _make_doc("_solo_" + short)
    try:
        _model(doc)
        corner = _corner(doc, short)
        pin = SC.corner_member_pin(list(corner.Strips))[0][0]
        return (_slots(doc), getattr(corner, "Construction", None),
                pin.Name, doc)
    finally:
        FreeCAD.closeDocument(doc.Name)


def one_slot_limit():
    """J1 and J3: one member patch, one axis end, two leaders."""
    FreeCAD, _DEMO, _SC, _SM, _OPS = _helpers()
    out = []

    def emit(line=""):
        out.append(line)

    wanted = {}
    for short in ("J1", "J3"):
        slots, construction, member_patch, _doc = solo_slots(short)
        wanted[short] = slots
        emit("  %s alone: construction %r, member patch %s, leader cuts %s"
             % (short, construction, member_patch,
                sorted("%s.%s=%.9f" % (k + (v,)) for k, v in slots.items())))
    both = set(wanted["J1"]) & set(wanted["J3"])
    emit("  the slots BOTH want: %s"
         % sorted("%s.%s" % k for k in both))
    for slot in sorted(both):
        emit("    %s.%s: J1 %.9f mm, J3 %.9f mm -- difference %.3e mm, and "
             "the patch has ONE property for it"
             % (slot[0], slot[1], wanted["J1"][slot], wanted["J3"][slot],
                abs(wanted["J1"][slot] - wanted["J3"][slot])))
    doc = _make_doc("_one_slot")
    _model(doc)
    j1 = _corner(doc, "J1")
    j3 = _corner(doc, "J3")
    emit("  built together, J1 then J3: J1 %r (%d poles, %d pieces), J3 %r "
         "(%d poles, %d pieces)"
         % (getattr(j1, "Construction", None), len(getattr(j1, "Poles", [])),
            len(getattr(j1, "Pieces", None) or []),
            getattr(j3, "Construction", None), len(getattr(j3, "Poles", [])),
            len(getattr(j3, "Pieces", None) or [])))
    emit("  leader cuts after both: %s"
         % sorted("%s.%s=%.9f" % (k + (v,)) for k, v in _slots(doc).items()))
    FreeCAD.closeDocument(doc.Name)
    return out


# ---- 3. the pair matrix -------------------------------------------------

def pair_matrix():
    """Every pair of junctions, both build orders."""
    FreeCAD, _DEMO, _SC, _SM, _OPS = _helpers()
    out = []

    def emit(line=""):
        out.append(line)

    def outcome(doc, first, second):
        # delete patch CASCADES its blends (#89), so a name from the list can
        # already be gone by the time it is reached
        for name in [o.Name for o in doc.Objects]:
            try:
                doc.removeObject(name)
            except Exception:
                pass
        doc.recompute()
        _model(doc)
        a = _corner(doc, first)
        b = _corner(doc, second)
        states = []
        for corner in (a, b):
            if corner is None:
                states.append("NO OBJECT")
            elif not (getattr(corner, "Poles", None) or []):
                states.append("%r, EMPTY net" % (corner.Construction,))
            else:
                states.append("%r, %d poles" % (corner.Construction,
                                                len(corner.Poles)))
        return states

    doc = _make_doc("_pair_matrix")
    emit("  %-6s %-6s %-28s %-28s %s"
         % ("first", "then", "first corner after", "second corner after",
            "leader cuts in the document"))
    for first, _name, _ring in JUNCTIONS:
        for second, _n2, _r2 in JUNCTIONS:
            if first == second:
                continue
            states = outcome(doc, first, second)
            emit("  %-6s %-6s %-28s %-28s %s"
                 % (first, second, states[0], states[1],
                    sorted("%s.%s" % k for k in _slots(doc))))
    FreeCAD.closeDocument(doc.Name)
    return out


# ---- 4. the deletion table ---------------------------------------------

def _snapshot(doc):
    FreeCAD, DEMO, _SC, SM, _OPS = _helpers()
    out = {}
    for name, _order, _grid in DEMO.PATCHES:
        p = doc.getObject(name)
        out[name] = {
            "edges": _edges(p),
            "us": [tuple(iv) for iv in SM.axis_intervals(p, "U")],
            "vs": [tuple(iv) for iv in SM.axis_intervals(p, "V")],
            "poles": [tuple(v) for v in p.Poles],
            "weights": [float(w) for w in p.Weights],
            "subgrids": len(getattr(p.Proxy, "_subgrids", None) or []),
            "hidden": sorted(int(i) for i in
                             (getattr(p, "_HiddenSubgridIdxs", None) or [])),
        }
    for name, _pa, _pb, _e in DEMO.BLENDS:
        b = doc.getObject(name)
        out["B:" + name] = {"poles": [tuple(v) for v in b.Poles]}
    return out


def _max_pole(a, b):
    FreeCAD, _DEMO, _SC, _SM, _OPS = _helpers()
    return max([(FreeCAD.Vector(*x) - FreeCAD.Vector(*y)).Length
                for x, y in zip(a, b)] or [0.0])


def _diff_line(before, after):
    """(changed, stayed) -- one clause per patch, one per strip.

    A patch is CHANGED when any of its cuts, interval counts, subgrid count,
    hidden set, 16 poles or 16 weights moved at all; the clause carries the
    number that moved, so "stayed" means 0.00e+00 and not "looks the same".
    """
    changed, stayed = [], []
    for key in sorted(before):
        if key.startswith("B:"):
            d = _max_pole(before[key]["poles"], after[key]["poles"])
            (changed if d > 0.0 else stayed).append(
                "%s: 24 poles, worst %.3e mm" % (key[2:], d))
            continue
        b, a = before[key], after[key]
        dp = _max_pole(b["poles"], a["poles"])
        dw = max([abs(x - y) for x, y in zip(b["weights"], a["weights"])]
                 or [0.0])
        notes = ["poles %.3e mm" % dp, "weights %.3e" % dw]
        for field, label in (("edges", "cuts"), ("us", "U intervals"),
                             ("vs", "V intervals"),
                             ("subgrids", "subgrids"), ("hidden", "hidden")):
            if b[field] != a[field]:
                notes.append("%s %r -> %r" % (label, b[field], a[field]))
            else:
                notes.append("%s %r" % (label, a[field]))
        moved = (dp > 0.0 or dw > 0.0
                 or any(b[f] != a[f] for f in ("edges", "us", "vs",
                                              "subgrids", "hidden")))
        (changed if moved else stayed).append("%s: %s"
                                              % (key, ", ".join(notes)))
    return changed, stayed


def deletion_table():
    """Delete J1, then J2, and read what changed and what stayed."""
    FreeCAD, _DEMO, _SC, _SM, _OPS = _helpers()
    out = []

    def emit(line=""):
        out.append(line)

    doc = _make_doc("_deletion_table")
    _model(doc)
    pre = _snapshot(doc)
    j1 = _corner(doc, "J1")
    j2 = _corner(doc, "J2")
    if j1 is None or j2 is None:
        emit("a corner refused -- see the console")
        FreeCAD.closeDocument(doc.Name)
        return out
    with_both = _snapshot(doc)
    objects_both = len(doc.Objects)
    j2_poles = [tuple(v) for v in j2.Poles]
    j2_pieces = {p.Name: [tuple(v) for v in p.Poles] for p in (j2.Pieces or [])}
    j1_pieces = [p.Name for p in (j1.Pieces or [])]
    j1_member = getattr(_member(doc, j1), "Name", None)
    slots_both = _slots(doc)
    emit("  with both corners: %d objects, leader cuts %s"
         % (len(doc.Objects),
            sorted("%s.%s" % k for k in slots_both)))

    emit("")
    emit("  (1) DELETE J1 -- %r, its member %r, its %d piece(s)"
         % (j1.Name, j1_member, len(j1_pieces)))
    doc.removeObject(j1.Name)
    doc.recompute()
    doc.recompute()
    one = _snapshot(doc)
    names = {o.Name for o in doc.Objects}
    changed, stayed = _diff_line(with_both, one)
    emit("    objects: %d -> %d; roles left: %s"
         % (objects_both, len(doc.Objects),
            sorted(o.Name for o in doc.Objects
                   if getattr(o, "object_type", "")
                   in ("CornerBlend", "RollingMemberFace",
                       "PreservedPiece"))))
    emit("    CHANGED (vs with both corners):")
    for line in changed:
        emit("      %s" % line)
    emit("    STAYED (0.00e+00 / identical): %d field group(s): %s"
         % (len(stayed), ", ".join(line.split()[0] for line in stayed)))
    for name in j1_pieces + ([j1_member] if j1_member else []):
        emit("    the deleted corner's own role %-46s %s"
             % (name, "GONE" if name not in names else "STILL THERE"))
    emit("    J2 (the survivor): construction %r, %d poles, pole delta "
         "%.3e mm; member %r; %d piece(s), worst pole delta %.3e mm"
         % (j2.Construction, len(j2.Poles),
            max([(FreeCAD.Vector(*a) - FreeCAD.Vector(*b)).Length
                 for a, b in zip(j2_poles, j2.Poles)] or [0.0]),
            getattr(_member(doc, j2), "Name", None),
            len(j2.Pieces or []),
            max([(FreeCAD.Vector(*a) - FreeCAD.Vector(*b)).Length
                 for p in (j2.Pieces or [])
                 for a, b in zip(j2_pieces.get(p.Name, []), p.Poles)] or [0.0])))
    slots_one = _slots(doc)
    emit("    leader cuts after the delete: %s"
         % sorted("%s.%s=%.9f" % (k + (v,)) for k, v in slots_one.items()))
    for slot, value in sorted(slots_both.items()):
        state = ("still %.9f" % slots_one[slot]) if slot in slots_one \
            else "GONE (sentinel: the patch is a plain banded patch again)"
        emit("      %s.%s was %.9f -> %s" % (slot[0], slot[1], value, state))

    emit("")
    emit("  (2) DELETE J2 AS WELL -- does the model come back?")
    doc.removeObject(j2.Name)
    doc.recompute()
    doc.recompute()
    post = _snapshot(doc)
    changed, stayed = _diff_line(pre, post)
    emit("    objects: %d (the demo model without corners has 41)"
         % len(doc.Objects))
    emit("    CHANGED vs PRE-CORNER: %s"
         % (", ".join(changed) if changed else "NOTHING -- 0.00e+00 on every "
            "patch's cuts, poles, weights, subgrid count and hidden set, and "
            "on every strip's poles"))
    emit("    compared: %d field group(s) (%d patch(es) x 7 fields + %d "
         "strip(s))" % (len(pre), len([k for k in pre if not k.startswith(
             "B:")]), len([k for k in pre if k.startswith("B:")])))
    touched = [o.Name for o in doc.Objects if "Touched" in o.State]
    emit("    the document settles: %d Touched" % len(touched))
    FreeCAD.closeDocument(doc.Name)
    return out


# ---- 5. the artifact ---------------------------------------------------

def artifact():
    """Save the demo model with BOTH rolling corners and leave it OPEN."""
    FreeCAD, _DEMO, SC, _SM, _OPS = _helpers()
    lines = []
    label = "_demo_two_corners"
    for name, d in list(FreeCAD.listDocuments().items()):
        if d.Label == label or (d.FileName and
                                os.path.abspath(d.FileName)
                                == os.path.abspath(ARTIFACT)):
            FreeCAD.closeDocument(name)
    doc = _make_doc(label, clear=False)
    _model(doc)
    j1 = _corner(doc, "J1")
    j2 = _corner(doc, "J2")
    if j1 is None or j2 is None:
        lines.append("ARTIFACT: a corner refused -- nothing saved")
        return lines
    doc.recompute()
    doc.recompute()
    os.makedirs(os.path.dirname(ARTIFACT), exist_ok=True)
    doc.saveAs(ARTIFACT)
    lines.append("ARTIFACT  %s  (%.1f kB, %d objects) -- LEFT OPEN"
                 % (ARTIFACT, os.path.getsize(ARTIFACT) / 1024.0,
                    len(doc.Objects)))
    lines.append("  corners: %s"
                 % [(o.Name, o.Construction) for o in doc.Objects
                    if getattr(o, "object_type", "") == "CornerBlend"])
    lines.append("  roles: %s"
                 % sorted(o.Name for o in doc.Objects
                          if getattr(o, "object_type", "") in
                          ("CornerBlend", "RollingMemberFace",
                           "PreservedPiece")))
    for short, corner in (("J1", j1), ("J2", j2)):
        pin = getattr(corner, "MemberPatch", None)
        if pin is None:
            found = SC.corner_member_pin(list(corner.Strips))
            pin = found[0][0] if found and found[0] else None
        lines.append("  %s: member patch %s, %d poles, %d pieces"
                     % (short, getattr(pin, "Name", None),
                        len(corner.Poles), len(corner.Pieces or [])))
    return lines


def measure():
    """Print every table above, in order.  RUNS INSIDE FREECAD."""
    out = []
    out.append("=" * 78)
    out.append("1. TWO ROLLED CORNERS IN ONE DOCUMENT (J1 + J2)")
    out.append("=" * 78)
    out.extend(two_corner_table())
    out.append("")
    out.append("=" * 78)
    out.append("2. THE ONE-SLOT LIMIT: J1 AND J3 BOTH NEED P_Top's U AXIS, 1 END")
    out.append("=" * 78)
    out.extend(one_slot_limit())
    out.append("")
    out.append("=" * 78)
    out.append("3. THE PAIR MATRIX (both build orders)")
    out.append("=" * 78)
    out.extend(pair_matrix())
    out.append("")
    out.append("=" * 78)
    out.append("4. THE DELETION TABLE")
    out.append("=" * 78)
    out.extend(deletion_table())
    return out


# ---------------------------------------------------------------------------
# The launcher: send the module's own halves to the owner's FreeCAD
# ---------------------------------------------------------------------------

BOOT = r'''
import sys
sys.path.insert(0, @@REPO@@)
sys.path.insert(0, @@HERE@@)
for _m in [m for m in list(sys.modules)
           if m.split(".")[0] in ("SilkMachinery", "SilkCorner",
                                  "SilkWorkflowOps", "SilkBlend", "SilkPatch",
                                  "SilkEdge", "SilkChecks",
                                  "cube_corner_model", "demo01_fixture_model",
                                  "two_rolled_corners", "ArachNURBS")]:
    del sys.modules[_m]
import two_rolled_corners as T
for _line in T.measure():
    print(_line)
print()
print("=" * 78)
print("5. THE ARTIFACT")
print("=" * 78)
for _line in T.artifact():
    print(_line)
'''


def rpc_execute(code, timeout=1800):
    """Send `code` to the owner's running FreeCAD. NEVER spawns one."""
    import xmlrpc.client
    proxy = xmlrpc.client.ServerProxy("http://%s:%d/" % (RPC_HOST, RPC_PORT))
    proxy.ping()
    res = proxy.execute_code(code, timeout)
    if not res.get("success"):
        raise SystemExit("RPC error: %s" % res.get("error"))
    return res.get("message", "")


def main(argv=None):
    code = BOOT.replace("@@REPO@@", repr(REPO)).replace("@@HERE@@", repr(HERE))
    text = rpc_execute(code)
    print(text)
    dest = os.path.join(os.path.dirname(ARTIFACT), "two_rolled_corners.txt")
    try:
        with open(dest, "w") as fh:
            fh.write(text if text.endswith("\n") else text + "\n")
        print("[raw output kept: %s]" % dest)
    except OSError as exc:
        print("[could not keep the raw output: %r]" % (exc,))
    return 0


if __name__ == "__main__":
    sys.exit(main())
