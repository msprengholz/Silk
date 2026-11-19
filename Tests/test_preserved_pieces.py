"""The rolled corner's TEN GEOMETRIC ROLES IN ONE OBJECT (#119 G1-G3).

WHAT IS PINNED HERE

  1. The maintainer's corner has ten roles: 3 ring blends, the triangular
     member, the quad, and FIVE preserved surfaces -- cells of the ring
     patches. Silk's new build has the same ten GEOMETRIC roles but ONE tree
     node: the CornerBlend's Shape is a compound of the quad and the tri,
     and the five cells are `ReservedCells` bookkeeping on the corner. No
     `PreservedPiece` or `RollingMemberFace` object is created.

  2. WHAT A CELL IS: the patch's OWN cell. `preserved_piece_cells` places it
     one step beyond the patch's inner cell, away from the junction, and
     the patch already computes and draws it. The corner records its
     identity (patch, role, cell indices); the surface is the patch's own,
     re-derived from `getSubgrid` for the C0 and area readings below.

  3. C0 TO ITS NEIGHBOURS -- measured, not eyeballed. Every edge of every
     reserved cell is sampled (21 stations) and its worst point-to-surface
     distance is taken against the corner's other roles: the quad, the tri,
     the three blends and the other cells. An edge that abuts one reads
     ZERO to the arithmetic (5.6e-17 .. 1.4e-14 mm across both fixtures).
     An edge that abuts nothing is REPORTED, not counted.

  4. NOTHING ELSE MOVED. The shipped construction still builds no tri and
     no cells; the 4-valent corner is unchanged; the document settles.

The fixture is `Tests/cube_corner_model.py` (three exact planar unit
patches). The demo model's own reading is the MANUAL instrument
`Tests/corner_ten_roles.py`.
"""

import FreeCAD
import Part

import SilkCorner as SC
import SilkMachinery as SM
from SilkWorkflowOps import create_corner_blend
from Tests import cube_corner_model as ccm
from Tests.mcp_harness import check

CUBE_CELLS = (
    ("PatchA", SM.PRESERVED_BEYOND_U, 2, 1, 0.80 * 0.10),
    ("PatchA", SM.PRESERVED_BEYOND_V, 1, 2, 0.10 * 0.80),
    ("PatchA", SM.PRESERVED_BEYOND_BOTH, 2, 2, 0.80 * 0.80),
    ("PatchB", SM.PRESERVED_BEYOND_BOTH, 1, 1, 0.90 * 0.90),
    ("PatchC", SM.PRESERVED_BEYOND_BOTH, 1, 1, 0.90 * 0.90),
)

C0_TOL = 1e-9
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


def _cell_shape(corner, patch, iu, iv):
    """The patch's own cell as a Face, exactly as the patch builds it."""
    us = SM.axis_intervals(patch, "U", owner=corner.Name)
    vs = SM.axis_intervals(patch, "V", owner=corner.Name)
    if not (0 <= iu < len(us) and 0 <= iv < len(vs)):
        return None
    u0, u1 = us[iu]
    v0, v1 = vs[iv]
    poles2d, weights2d = patch.Proxy.getSubgrid(u0, u1, v0, v1)
    if not poles2d or not weights2d:
        return None
    surf = Part.BSplineSurface()
    surf.increaseDegree(3, 3)
    for knot, mult in ((0.0, 4), (1.0, 4)):
        surf.insertUKnot(knot, mult, 1e-7)
        surf.insertVKnot(knot, mult, 1e-7)
    for r in range(4):
        for c in range(4):
            surf.setPole(c + 1, r + 1, poles2d[r][c],
                         float(weights2d[r][c]))
    return surf.toShape()


def _edge_residual(edge, shape, stations=21):
    worst = 0.0
    for i in range(stations):
        t = i / float(stations - 1)
        p = edge.valueAt(edge.FirstParameter
                         + t * (edge.LastParameter - edge.FirstParameter))
        worst = max(worst, shape.distToShape(Part.Vertex(p))[0])
    return worst


def _bbox_gap(bb_a, bb_b):
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


def test_the_cube_corner_produces_ten_roles_in_one_object(doc):
    errors, checks = [], []
    strips, corner = _corner(doc)
    if corner is None or not corner.Poles:
        return {"pass": False,
                "errors": ["the corner stage built no corner"], "checks": checks}
    tri = SC.corner_tri_face(corner)
    net = SC.corner_tri_net(corner)
    cells = SC.reserved_cells(corner)
    checks.append("tree roles: %s"
                  % ", ".join("%s:%s" % (o.Name, getattr(o, "object_type", ""))
                              for o in doc.Objects
                              if getattr(o, "object_type", "")
                              in ("CornerBlend", "RollingMemberFace",
                                  "PreservedPiece")))
    check(not [o for o in doc.Objects
               if getattr(o, "object_type", "")
               in ("RollingMemberFace", "PreservedPiece")],
          "old separate roles were created for the one-object model", errors)
    check(len(corner.Shape.Faces) == 2 and tri is not None,
          "the corner Shape is not a compound of quad and tri (%d faces)"
          % len(corner.Shape.Faces), errors)
    check(net is not None, "the corner carries no 24-pole triangular net",
          errors)
    check(len(cells) == 5, "the corner records %d cells, not 5" % len(cells),
          errors)
    counts = {}
    for patch, _role, _iu, _iv in cells:
        counts[patch.Name] = counts.get(patch.Name, 0) + 1
    member_patch = corner.MemberPatch
    if member_patch is None:
        member_patch = SC.corner_member_pin(
            list(corner.Strips), SC.CORNER_DEFAULT_TOL)[0][0]
    checks.append("reserved cells per patch: %s (the tri's patch is %s)"
                  % (counts, member_patch.Name))
    check(counts.get(member_patch.Name) == 3 and sorted(counts.values()) == [1, 1, 3],
          "the cells are not 3 + 1 + 1 around the tri's patch: %s" % counts,
          errors)
    for patch, role, iu, iv in cells:
        shape = _cell_shape(corner, patch, iu, iv)
        checks.append("%s: %s cell (%d, %d), area %.6f"
                      % (patch.Name, role, iu, iv,
                         max(f.Area for f in shape.Faces) if shape else 0.0))
        check(shape is not None and shape.isValid(),
              "%s's reserved cell (%d, %d) has no valid patch surface"
              % (patch.Name, iu, iv), errors)
    touched = [o.Name for o in doc.Objects if "Touched" in o.State]
    checks.append("after two recomputes: %d Touched, %d objects"
                  % (len(touched), len(doc.Objects)))
    check(not touched, "the document does not settle: %r" % touched[:6], errors)
    return {"pass": not errors, "errors": errors, "checks": checks}


def test_each_cell_is_the_patch_cell_the_rule_places(doc):
    errors, checks = [], []
    _strips, corner = _corner(doc)
    cells = SC.reserved_cells(corner)
    got = sorted((p.Name, r, iu, iv) for p, r, iu, iv in cells)
    want = sorted(c[:4] for c in CUBE_CELLS)
    checks.append("reserved: %r" % (got,))
    check(got == want, "the reserved cells are %r, want %r" % (got, want), errors)
    for patch_name, role, iu, iv, area in CUBE_CELLS:
        patch = doc.getObject(patch_name)
        shape = _cell_shape(corner, patch, iu, iv)
        face = max(shape.Faces, key=lambda f: f.Area) if shape else None
        if face is None:
            errors.append("%s cell (%d, %d) has no face" % (patch_name, iu, iv))
            continue
        d = abs(face.Area - area)
        checks.append("%s %s: area %.9f, want %.9f (delta %.3e)"
                      % (patch_name, role, face.Area, area, d))
        check(d <= AREA_TOL, "%s's cell area moved by %.3e" % (patch_name, d),
              errors)
    return {"pass": not errors, "errors": errors, "checks": checks}


def test_every_cell_edge_that_abuts_a_role_is_c0_to_it(doc):
    errors, checks = [], []
    strips, corner = _corner(doc)
    tri = SC.corner_tri_face(corner)
    cells = SC.reserved_cells(corner)
    roles = [("blend:%s" % s.Name, s.Shape) for s in strips]
    roles.append(("tri", tri.Shape if hasattr(tri, "Shape") else tri))
    roles.append(("quad", corner.Shape))
    for patch, role, iu, iv in cells:
        roles.append(("cell:%s:%s" % (patch.Name, role),
                      _cell_shape(corner, patch, iu, iv)))
    worst = 0.0
    for patch, role, iu, iv in cells:
        shape = _cell_shape(corner, patch, iu, iv)
        if shape is None:
            continue
        for edge in shape.Edges:
            ebb = edge.BoundBox
            ranked = []
            for name, other in roles:
                if other is shape or other is None or not other.Faces:
                    continue
                ranked.append((_bbox_gap(ebb, other.BoundBox), name, other))
            ranked.sort(key=lambda rec: rec[0])
            touching = [rec for rec in ranked if rec[0] <= 1e-6]
            if not touching:
                continue
            best = None
            for _gap, name, other in touching:
                got = _edge_residual(edge, other)
                if best is None or got < best[1]:
                    best = (name, got)
            if best is None or best[1] > C0_TOL:
                continue
            name, got = best
            worst = max(worst, got)
            checks.append("cell %s %s (%d,%d) edge abuts %s: %.3e mm"
                          % (patch.Name, role, iu, iv, name, got))
    checks.append("worst residual over every abutting cell edge: %.3e mm" % worst)
    check(worst <= C0_TOL, "a reserved cell edge is %.3e mm off its neighbour"
          % worst, errors)
    return {"pass": not errors, "errors": errors, "checks": checks}


def test_the_corner_hides_its_whole_junction_end_block(doc):
    """The corner hides the JUNCTION-END BLOCK, not one cell.

    A rolling corner cuts its member patch twice per axis, so the square the
    corner sits on is split into strips by those cuts. Covering only the
    leader-bounded cell leaves the rest of the square -- and the strips the
    cuts created -- drawn as stray subpatches under the corner. That is the
    report: "the sub patches that are created to allow the rolled corner are
    not hidden correctly".

    Contract: on every ring patch, every cell inside the block between the
    corner cell and the patch edge on BOTH axes is hidden, and every
    preserved piece (the cell one step AWAY from the junction) stays visible.
    """
    errors, checks = [], []
    _strips, corner = _corner(doc)
    if corner is None or not corner.Poles:
        return {"pass": False, "errors": ["the corner did not build"],
                "checks": checks}
    pieces = {(p.Name, iu, iv) for p, _r, iu, iv in SC.reserved_cells(corner)}
    for patch in [doc.getObject(n) for n in ("PatchA", "PatchB", "PatchC")]:
        cell = SC.corner_cell_of(patch, list(corner.Strips),
                                 SC.CORNER_DEFAULT_TOL, corner.Name)
        iu, iv, nu, nv, u_end, v_end = cell
        us = list(range(iu, nu)) if u_end == 1 else list(range(0, iu + 1))
        vs = list(range(iv, nv)) if v_end == 1 else list(range(0, iv + 1))
        block = {(i, j) for i in us for j in vs}
        hidden = {divmod(int(k), nv) for k in
                  (getattr(patch, "_HiddenSubgridIdxs", None) or [])}
        missing = sorted(block - hidden)
        pieces_visible = {c for c in pieces if c[0] == patch.Name}
        hidden_pieces = sorted(pieces_visible & hidden)
        checks.append("%s: corner cell (%d,%d) of %dx%d, block %r, hidden %r"
                      % (patch.Name, iu, iv, nu, nv, sorted(block),
                         sorted(hidden)))
        check(not missing,
              "%s leaves %d cell(s) of the junction-end block VISIBLE: %r -- "
              "the corner's own square is drawn as stray subpatches"
              % (patch.Name, len(missing), missing), errors)
        check(not hidden_pieces,
              "%s HIDES its preserved piece cell(s) %r -- the exposed original "
              "surface must stay visible" % (patch.Name, hidden_pieces),
              errors)
    return {"pass": not errors, "errors": errors, "checks": checks}


ALL_TESTS = [
    test_the_cube_corner_produces_ten_roles_in_one_object,
    test_each_cell_is_the_patch_cell_the_rule_places,
    test_every_cell_edge_that_abuts_a_role_is_c0_to_it,
    test_the_corner_hides_its_whole_junction_end_block,
]
