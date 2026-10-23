"""
The rolled corner's TEN ROLES, and its five PRESERVED PIECES (#130).

WHAT IS PINNED HERE

  1. TEN ROLES, as the maintainer's corner stores them.  Measured from
     `Silk_CopyPasta_29`: 3 ring blends + 1 triangular member (the tri) +
     1 corner fill (the quad) + FIVE preserved surfaces, each a
     `CubicSurface_44` over ONE cell of a ring patch -- three from the patch
     that carries the tri, one from each of the other two.  This build
     produced the first five and none of the preserved pieces.

  2. WHAT A PIECE IS: the patch's OWN cell.  `SilkMachinery.
     preserved_piece_cells` places it -- the cell ONE STEP BEYOND the patch's
     inner cell, away from the junction, the inner cell being the member's
     cell on the patch that carries the tri and the corner cell on the other
     two -- and `SilkCorner.PreservedPiece` draws it as a segment of the
     patch's own base surface.  So the pins are the CELL (index and
     parameter rectangle), the NET (pole-for-pole the patch's own cell) and
     the AREA (the cell's, not a re-fit's).

  3. C0 TO ITS NEIGHBOURS -- measured, not eyeballed.  Every edge of every
     piece is sampled (41 stations) and its worst point-to-surface distance
     is taken against the corner's other roles: the quad, the tri, the three
     blends and the other pieces.  An edge that abuts one of them reads ZERO
     to the arithmetic (1e-16 mm on the unit cube, 1e-14 on the demo's
     200 mm model) because a piece is cut on knot lines the patch already
     carries; an edge that abuts nothing is REPORTED as such rather than
     counted as a failure.  Only roles whose BOUNDING BOX reaches the edge
     are measured -- the exact residual is never smaller than that gap, so
     the filter cannot hide contact, and it took the table from 8.8 s to
     2.5 s.

  4. NOTHING ELSE MOVED.  The shipped construction still builds no pieces
     (it has no separate member) and is the 6x6 of before; the 4-valent
     corner is unchanged (it takes the shipped construction and has no
     member, hence no pieces); the pieces are recorded on the corner
     (`CornerBlend.Pieces`) and the document settles after they are built
     (#125).

The fixture is `Tests/cube_corner_model.py` (three exact planar unit
patches), so every area below is exact arithmetic: the member patch is cut
at the 0.1 setback and the 0.25 leader, so its cells are 0.1 x 0.1 (corner),
0.15 x 0.1 (the two mixed cells), 0.15 x 0.15 (the tri), 0.15 x 0.75 and
0.75 x 0.15 (two of the pieces) and 0.75 x 0.75 (the third); the other two
patches carry the setback only, so their cell diagonally beyond the corner
cell is 0.9 x 0.9.

The demo model's own reading (CB_J1_FrontTopRight, 200 mm) is the MANUAL
instrument `Tests/corner_ten_roles.py`, which builds the corner in the GUI,
prints the same table and leaves the document open.
"""

import FreeCAD
import Part

import SilkCorner as SC
import SilkMachinery as SM
from SilkWorkflowOps import create_corner_blend
from Tests import cube_corner_model as ccm

# The five pieces, on the cube fixture: (patch, role, CellU, CellV, area).
# The member patch is cut at the 0.1 setback and the 0.25 leader on both
# axes, so its cell grid is 3x3 and the ring corner is at (u, v) = (0, 0).
CUBE_PIECES = (
    ("PatchA", SM.PRESERVED_BEYOND_U, 2, 1, 0.75 * 0.15),
    ("PatchA", SM.PRESERVED_BEYOND_V, 1, 2, 0.15 * 0.75),
    ("PatchA", SM.PRESERVED_BEYOND_BOTH, 2, 2, 0.75 * 0.75),
    ("PatchB", SM.PRESERVED_BEYOND_BOTH, 1, 1, 0.90 * 0.90),
    ("PatchC", SM.PRESERVED_BEYOND_BOTH, 1, 1, 0.90 * 0.90),
)

# How far a piece edge may sit from the surface it abuts. The pieces are
# segments of their patch's own Bezier, cut on knot lines the patch carries,
# so the residual is the instrument's arithmetic floor (measured: 5.6e-17 ..
# 1.4e-14 mm across both fixtures), never a fudge.
C0_TOL = 1e-9

# The area tolerance: the cell's own area is exact arithmetic.
AREA_TOL = 1e-9


def _corner(doc, **kw):
    ccm.build_cube_corner_model(doc)
    doc.recompute()
    doc.recompute()
    strips = [doc.getObject(n) for n in ("B_AB", "B_BC", "B_CA")]
    corner = create_corner_blend(*strips, name="Ten", **kw)
    doc.recompute()
    doc.recompute()
    return strips, corner


def _member(doc, corner):
    for o in doc.Objects:
        if getattr(o, "object_type", "") == "RollingMemberFace" \
                and getattr(o, "Corner", None) is corner:
            return o
    return None


def _roles(doc, corner):
    """[(role, object)] -- the corner's ten roles, in the naming this
    module and the render both use."""
    out = [("blend:%s" % s.Name, s) for s in corner.Strips]
    member = _member(doc, corner)
    if member is not None:
        out.append(("tri", member))
    out.append(("quad", corner))
    out.extend(("piece:%s" % p.Name, p) for p in (corner.Pieces or []))
    return out


def _edge_residual(edge, shape, stations=21):
    """The worst distance from `edge`'s sampled points to `shape`.

    21 stations, not 41: the reading is the arithmetic floor (5.6e-17 ..
    1.4e-14 mm) and the question the table answers is whether a piece edge
    lies on the surface it abuts -- a piece on the WRONG surface is off by
    the cell's own size (0.15-0.9 mm on this fixture), not by a fraction of
    the sampling step.  Measured: 41 stations cost 3.0 s of the fast tier,
    21 cost 1.6 s, both reading 5.551e-17 mm worst."""
    worst = 0.0
    for i in range(stations):
        t = i / float(stations - 1)
        p = edge.valueAt(edge.FirstParameter
                         + t * (edge.LastParameter - edge.FirstParameter))
        worst = max(worst, shape.distToShape(Part.Vertex(p))[0])
    return worst


def _bbox_gap(bb_a, bb_b):
    """The distance between two bounding boxes (0 when they overlap)."""
    total = 0.0
    for lo_a, hi_a, lo_b, hi_b in (
            (bb_a.XMin, bb_a.XMax, bb_b.XMin, bb_b.XMax),
            (bb_a.YMin, bb_a.YMax, bb_b.YMin, bb_b.YMax),
            (bb_a.ZMin, bb_a.ZMax, bb_b.ZMin, bb_b.ZMax)):
        if hi_a < lo_b:
            total += (lo_b - hi_a) ** 2
        elif hi_b < lo_a:
            total += (lo_a - hi_b) ** 2
    return total ** 0.5


def _nearest_by_edge(piece, roles, tol=1e-6):
    """Per edge of `piece`: (edge, the role it abuts, that role's residual).

    A role is a candidate when it has a surface and is not the piece itself;
    the residual is the worst over the edge's stations, so a reported zero
    means the whole edge lies on that surface and a role further than `tol`
    means the edge abuts nothing among the corner's roles.

    Only roles whose BOUNDING BOX reaches the edge are measured: the exact
    residual is never smaller than that gap, so a role further than `tol`
    cannot abut the edge.  Nine roles x 41 stations x `distToShape` per
    piece edge was 8.8 s; on this fixture 1-3 roles survive the filter.
    When nothing reaches the edge, the bbox-nearest role is measured once
    so the reported "nearest" is still a real distance to a named role."""
    out = []
    for edge in piece.Shape.Edges:
        ebb = edge.BoundBox
        ranked = []
        for name, obj in roles:
            if obj is piece or obj is None:
                continue
            shape = getattr(obj, "Shape", None)
            if not shape or not shape.Faces:
                continue
            ranked.append((_bbox_gap(ebb, shape.BoundBox), name, shape))
        if not ranked:
            continue
        ranked.sort(key=lambda rec: rec[0])
        touching = [rec for rec in ranked if rec[0] <= tol]
        candidates = touching or ranked[:1]
        best = None
        for _gap, name, shape in candidates:
            got = _edge_residual(edge, shape)
            if best is None or got < best[1]:
                best = (name, got)
        out.append((edge, best[0] if best[1] <= tol else None, best[1]))
    return out


def test_the_cube_corner_produces_ten_roles(doc):
    """3 blends + the tri + the quad + FIVE preserved pieces, recorded on
    the corner, and the document settles.

    One build answers both questions (the roles, and that they are on
    `CornerBlend.Pieces` and that nothing stays Touched) -- they were two
    tests on the same fixture, and the fixture build is the cost."""
    errors, checks = [], []
    _strips, corner = _corner(doc)
    if corner is None or not corner.Poles:
        return {"pass": False,
                "errors": ["the corner stage built no corner"], "checks": []}
    roles = _roles(doc, corner)
    pieces = list(corner.Pieces or [])
    checks.append("roles: %s" % ", ".join(n for n, _o in roles))
    if len(roles) != 10:
        errors.append("the corner produced %d roles, not 10: %s"
                      % (len(roles), [n for n, _o in roles]))
    if len(pieces) != 5:
        errors.append("the corner produced %d preserved pieces, not 5"
                      % len(pieces))
    counts = {}
    for p in pieces:
        counts[p.Patch.Name] = counts.get(p.Patch.Name, 0) + 1
    member_patch = corner.MemberPatch
    if member_patch is None:
        member_patch = SC.corner_member_pin(
            list(corner.Strips), SC.CORNER_DEFAULT_TOL)[0][0]
    checks.append("pieces per patch: %s (the tri's patch is %s)"
                  % (counts, member_patch.Name))
    if counts.get(member_patch.Name) != 3:
        errors.append("the patch that carries the tri (%s) yields %d pieces, "
                      "not 3" % (member_patch.Name,
                                 counts.get(member_patch.Name, 0)))
    if sorted(counts.values()) != [1, 1, 3]:
        errors.append("the pieces are not 3 + 1 + 1: %s"
                      % sorted(counts.values()))
    for p in pieces:
        checks.append("%s: %s of %s, cell (%d, %d), u [%g, %g] v [%g, %g], "
                      "area %.6f"
                      % (p.Name, p.Role, p.Patch.Name, p.CellU, p.CellV,
                         p.U0, p.U1, p.V0, p.V1, p.Shape.Area))
    checks.append("corner.Pieces: %s" % [p.Name for p in pieces])
    for p in pieces:
        if getattr(p, "object_type", "") != "PreservedPiece":
            errors.append("%s is a %r, not a PreservedPiece"
                          % (p.Name, getattr(p, "object_type", "")))
        if p.Patch is None:
            errors.append("%s names no patch" % p.Name)
        if not p.Shape.isValid():
            errors.append("%s's shape is invalid" % p.Name)
    doc.recompute()
    doc.recompute()
    touched = [o.Name for o in doc.Objects if "Touched" in o.State]
    checks.append("after two recomputes: %d Touched, %d objects"
                  % (len(touched), len(doc.Objects)))
    if touched:
        errors.append("the document does not settle: %r" % touched[:6])
    # a second ask returns the same corner rather than a second member, a
    # second quad and five more pieces.
    stale = create_corner_blend(*[doc.getObject(n)
                                  for n in ("B_AB", "B_BC", "B_CA")],
                                name="TenAgain")
    checks.append("a second ask returns the same corner: %s; pieces %d"
                  % (stale is corner, len(corner.Pieces or [])))
    if stale is not corner:
        errors.append("a second ask built a second corner (%s)"
                      % getattr(stale, "Name", None))
    if len(corner.Pieces or []) != 5:
        errors.append("the second ask changed the corner's pieces (%d)"
                      % len(corner.Pieces or []))
    return {"pass": not errors, "errors": errors, "checks": checks}


def test_each_piece_is_the_patch_cell_the_rule_places(doc):
    """The cell, the net and the AREA are the patch's own, and the rule
    that chose the cell is the placement: one step BEYOND the inner cell.

    Two readings of one build -- the piece against its patch, and the
    rule against the patches' own arithmetic -- merged because the
    fixture build is what either of them costs."""
    errors, checks = [], []
    strips, corner = _corner(doc)
    got = {}
    for p in (corner.Pieces or []):
        got[(p.Patch.Name, p.Role)] = p
    for patch_name, role, iu, iv, area in CUBE_PIECES:
        p = got.get((patch_name, role))
        if p is None:
            errors.append("no %s piece on %s" % (role, patch_name))
            continue
        patch = p.Patch
        if (p.CellU, p.CellV) != (iu, iv):
            errors.append("%s %s: cell (%d, %d), not (%d, %d)"
                          % (patch_name, role, p.CellU, p.CellV, iu, iv))
        us = SM.axis_intervals(patch, "U")
        vs = SM.axis_intervals(patch, "V")
        if (p.U0, p.U1) != us[p.CellU] or (p.V0, p.V1) != vs[p.CellV]:
            errors.append("%s %s: the stored rectangle [%g, %g] x [%g, %g] is "
                          "not the patch's interval pair %r x %r"
                          % (patch_name, role, p.U0, p.U1, p.V0, p.V1,
                             us[p.CellU], vs[p.CellV]))
        # the NET: pole-for-pole the patch's own cell, weights carried
        poles2d, weights2d = patch.Proxy.getSubgrid(p.U0, p.U1, p.V0, p.V1)
        want_poles = [poles2d[r][c] for r in range(4) for c in range(4)]
        want_weights = [float(weights2d[r][c]) for r in range(4)
                        for c in range(4)]
        worst = max([(a - b).Length for a, b in zip(p.Poles, want_poles)]
                    or [0.0])
        wworst = max([abs(a - b) for a, b in zip(p.Weights, want_weights)]
                     or [0.0])
        checks.append("%s %s: net parity %.3e mm, weight parity %.3e, "
                      "area %.9f (the cell's is %.9f)"
                      % (patch_name, role, worst, wworst, p.Shape.Area, area))
        if worst > 1e-12 or wworst > 1e-12:
            errors.append("%s %s: the piece is not the patch's own cell "
                          "(net %.3e mm, weights %.3e)"
                          % (patch_name, role, worst, wworst))
        if abs(p.Shape.Area - area) > AREA_TOL:
            errors.append("%s %s: its area is %.9f, the cell's is %.9f"
                          % (patch_name, role, p.Shape.Area, area))

    # --- the rule that placed them ---------------------------------------
    if corner is None or not corner.Poles:
        return {"pass": False, "checks": [],
                "errors": ["the corner stage built no corner"]}
    ordered, why = SM.corner_ring_3(strips)
    if ordered is None:
        return {"pass": False, "errors": [why], "checks": []}
    patches = []
    for s in ordered:
        for p in (s.PatchA, s.PatchB):
            if p is not None and p not in patches:
                patches.append(p)
    member_patch = SC.corner_member_pin(list(strips),
                                        SC.CORNER_DEFAULT_TOL)[0][0]
    for p in patches:
        cell = SC.corner_cell_of(p, ordered)
        cells, cell_why = SM.preserved_piece_cells(
            cell, member=(p is member_patch))
        checks.append("%s: corner cell (iu=%r, iv=%r) of %d x %d interval(s), "
                      "junction ends (%r, %r) -> %r"
                      % (p.Name, cell[0], cell[1], cell[2], cell[3],
                         cell[4], cell[5], cells))
        if cells is None:
            errors.append("%s: %s" % (p.Name, cell_why))
            continue
        want = 3 if p is member_patch else 1
        if len(cells) != want:
            errors.append("%s: %d piece cells, not %d"
                          % (p.Name, len(cells), want))
        us = SM.axis_intervals(p, "U")
        vs = SM.axis_intervals(p, "V")
        have = {(q.CellU, q.CellV) for q in (corner.Pieces or [])
                if q.Patch is p}
        for role, iu, iv in cells:
            if not (0 <= iu < len(us) and 0 <= iv < len(vs)):
                errors.append("%s %s: (%d, %d) is not a cell"
                              % (p.Name, role, iu, iv))
            du = 0 if role == SM.PRESERVED_BEYOND_V else 1
            dv = 0 if role == SM.PRESERVED_BEYOND_U else 1
            if abs(iu - cell[0]) != du or abs(iv - cell[1]) != dv:
                errors.append("%s %s: cell (%d, %d) is not one step from the "
                              "inner cell (%d, %d) on the role's own axes"
                              % (p.Name, role, iu, iv, cell[0], cell[1]))
            if (iu, iv) not in have:
                errors.append("%s %s: no piece object for cell (%d, %d)"
                              % (p.Name, role, iu, iv))
    return {"pass": not errors, "errors": errors, "checks": checks}


def test_every_piece_edge_that_abuts_a_role_is_c0_to_it(doc):
    """The C0 table: each piece edge against the role it lies on."""
    errors, checks = [], []
    _strips, corner = _corner(doc)
    roles = _roles(doc, corner)
    pieces = list(corner.Pieces or [])
    if len(pieces) != 5:
        return {"pass": False, "checks": [],
                "errors": ["%d pieces, expected 5" % len(pieces)]}
    floating = []
    worst_abutting = 0.0
    for p in pieces:
        contact = 0
        for edge, name, residual in _nearest_by_edge(p, roles):
            if name is None:
                checks.append("%-34s edge %8.4f mm  abuts nothing among the "
                              "corner's roles (nearest %.3e mm)"
                              % (p.Name, edge.Length, residual))
                continue
            contact += 1
            worst_abutting = max(worst_abutting, residual)
            checks.append("%-34s edge %8.4f mm  abuts %-9s %.3e mm"
                          % (p.Name, edge.Length, name, residual))
            if residual > C0_TOL:
                errors.append("%s: an edge abutting %s sits %.3e mm off it"
                              % (p.Name, name, residual))
        if contact < 2:
            floating.append("%s abuts only %d role(s)" % (p.Name, contact))
    checks.append("worst residual over every abutting piece edge: %.3e mm"
                  % worst_abutting)
    if floating:
        errors.extend(floating)
    return {"pass": not errors, "errors": errors, "checks": checks}


def test_the_shipped_construction_and_the_four_valent_corner_build_no_pieces(doc):
    """The two constructions that have NO separate member: the shipped
    fallback and a 4-valent ring.

    Both take the corner of before #130, so both are read here -- the
    shipped one on the cube fixture of this module (the fixture names its
    objects, and a second corner on the same strips is an idempotent no-op,
    which is why it is asked for by name with `construction="shipped"`), the
    4-valent one on `Tests/corner_model.py`.  The pole-for-pole identity
    with #128's corner is the MANUAL `Tests/test_two_patch_corner.py`'s job;
    here the pins are what these constructions do NOT build.
    """
    errors, checks = [], []
    _strips, shipped = _corner(doc, construction="shipped")
    if shipped is None or not shipped.Poles:
        return {"pass": False, "checks": [],
                "errors": ["the shipped corner stage built nothing"]}
    coins = 0
    for i in range(len(shipped.Poles)):
        for j in range(i):
            if (shipped.Poles[i] - shipped.Poles[j]).Length <= 1e-9:
                coins += 1
    checks.append("shipped corner: %d poles, %d weights, %d coincident "
                  "pair(s), %d piece(s), construction %r"
                  % (len(shipped.Poles), len(shipped.Weights), coins,
                     len(shipped.Pieces or []), shipped.Construction))
    if len(shipped.Poles) != 36 or len(shipped.Weights) != 36:
        errors.append("the shipped corner is not the 6x6 of before (%d poles, "
                      "%d weights)" % (len(shipped.Poles),
                                       len(shipped.Weights)))
    if shipped.Pieces:
        errors.append("the shipped corner built %d preserved pieces"
                      % len(shipped.Pieces))
    if _member(doc, shipped) is not None:
        errors.append("the shipped corner built a triangular member")

    # the 4-valent ring, in a document of its own
    from Tests import corner_model as cm
    fdoc = FreeCAD.newDocument("FourValent")
    try:
        FreeCAD.setActiveDocument(fdoc.Name)
        cm.build_corner_model(fdoc)
        fdoc.recompute()
        fdoc.recompute()
        strips = [fdoc.getObject(n) for n in ("B12", "B24", "B43", "B31")]
        corner = create_corner_blend(*strips, name="Four")
        fdoc.recompute()
        fdoc.recompute()
        if corner is None or not corner.Poles:
            errors.append("the 4-valent corner stage built nothing")
        else:
            coins = 0
            for i in range(len(corner.Poles)):
                for j in range(i):
                    if (corner.Poles[i] - corner.Poles[j]).Length <= 1e-9:
                        coins += 1
            checks.append("4-valent corner: %d poles, %d coincident pair(s), "
                          "construction %r, %d piece(s)"
                          % (len(corner.Poles), coins, corner.Construction,
                             len(corner.Pieces or [])))
            if len(corner.Poles) != 36:
                errors.append("the 4-valent corner has %d poles, not 36"
                              % len(corner.Poles))
            if coins:
                errors.append("the 4-valent corner's 6x6 carries %d "
                              "coincident pairs" % coins)
            if corner.Pieces:
                errors.append("the 4-valent corner built preserved pieces")
            if _member(fdoc, corner) is not None:
                errors.append("the 4-valent corner built a triangular member")
    finally:
        FreeCAD.closeDocument(fdoc.Name)
        FreeCAD.setActiveDocument(doc.Name)
    return {"pass": not errors, "errors": errors, "checks": checks}


ALL_TESTS = [
    test_the_cube_corner_produces_ten_roles,
    test_each_piece_is_the_patch_cell_the_rule_places,
    test_every_piece_edge_that_abuts_a_role_is_c0_to_it,
    test_the_shipped_construction_and_the_four_valent_corner_build_no_pieces,
]
