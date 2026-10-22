#!/usr/bin/env python3
"""Tests/demo_corner_row_diff.py -- THE ROW DIFF: demo junction vs cube corner.

**What it answers.**  The rolling corner is measured fold-free on the
cube-corner fixture (0/0/0 normal-field flips, the tri 7.5..53.5 % of the
corner's extent off the quad) and it FOLDS on the demo model's junction
CB_J1_FrontTopRight (30/56/86 flips, the tri 0.1..2.0 % off the quad, i.e.
inside it).  Both assemblies are the same chain
(`subgrid33_2grid64` x4 -> `control_grid66_4sub`); the placement is the
same two-patch cut.  So the difference is in the INPUT the ring hands the
chain, and this instrument prints it side by side:

  * per patch of the ring -- splits, leader cuts, the INTERVAL list of each
    axis, which intervals are corner cells, and where the patch's own corner
    cell sits;
  * per (seam, patch) -- `band_extent`: the band's along-seam extent, its
    across extent, and the junction end the ring names;
  * the ring as assembled -- each member's 24-pole grid, its bbox, the row
    steps, and `pair_common`'s (i, j) per pair plus the rows each pair
    READS (the ported `SubGrid33_2Grid64` index map);
  * which row order the triangular member is read in
    (`SilkCorner._member_row_order`) and where its collapsed row sits;
  * WHERE THE 6x6 LANDS ON THE MEMBER PATCH: every pole of the assembled
    6x6 inverted onto the member patch's own base net, so the fill's control
    net can be compared with the corner cell's parametric rectangle instead
    of eyeballed;
  * the two readings the fold is counted in -- normal-field flips and the
    tri-interior-to-quad distance, as a fraction of the corner's extent.

**How it runs.**  Inside the owner's running FreeCAD, over XML-RPC, exactly
like `Tests/reference_corner_diff.py --ours` (never spawn a FreeCAD):

    flock /tmp/silk_rpc.lock -c "python3 Tests/demo_corner_row_diff.py"

**What it does NOT do.**  It asserts nothing and it is not a test module: it
is an instrument -- numbers plus names -- and its raw output is the
measurement the ticket is decided on.
"""

import os
import sys

# --- manual tier ------------------------------------------------------
# A measurement script, not a test module (the name is not `test_*`), so the
# suite never collects it and `Tests/test_continuity_instrument.py`'s marker
# rule is honoured by stating it here.
MANUAL = True

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HERE = os.path.dirname(os.path.abspath(__file__))
RPC_HOST = "127.0.0.1"
RPC_PORT = 9875

# The demo junction this instrument reads, and the ring the corner stage
# derives for it (Tests/demo01_fixture_model.CORNERS[0]).
DEMO_CORNER = "CB_J1_FrontTopRight"
DEMO_RING = ("B_FT", "B_FR", "B_TR")


# ---------------------------------------------------------------------------
# The in-FreeCAD half
# ---------------------------------------------------------------------------

def row_diff(cube_leader=0.25):
    """Print the row diff for BOTH fixtures.  RUNS INSIDE FREECAD."""
    import FreeCAD
    import Part
    import SilkChecks
    import SilkCorner as SC
    import SilkMachinery as M
    import SilkWorkflowOps as OPS
    import cube_corner_model as CCM
    import demo01_fixture_model as DEMO
    import reference_corner_diff as R

    out = []

    def emit(line=""):
        out.append(line)

    def make_doc(label):
        for name, d in list(FreeCAD.listDocuments().items()):
            if d.Label == label:
                FreeCAD.closeDocument(name)
        doc = FreeCAD.newDocument(label)
        FreeCAD.setActiveDocument(doc.Name)
        return doc

    # -- the two fixtures -------------------------------------------------
    cube_doc = make_doc("_rowdiff_cube")
    cres = CCM.build_cube_corner_model(cube_doc)
    cube_doc.recompute()
    cube_strips = [cres["strips"][n] for n in ("B_AB", "B_BC", "B_CA")]
    cube_member_patch = cube_doc.getObject("PatchA")

    demo_doc = make_doc("_rowdiff_demo")
    dres = DEMO.build(demo_doc, corners=False)
    demo_doc.recompute()
    demo_strips = [demo_doc.getObject(n) for n in DEMO_RING]

    sides = (
        ("CUBE (Tests/cube_corner_model.py, PatchA carries the member)",
         cube_doc, cube_strips, cube_member_patch, cube_leader),
        ("DEMO %s (Tests/demo01_fixture_model.py, P_Top carries the member)"
         % DEMO_CORNER,
         demo_doc, demo_strips, demo_doc.getObject("P_Top"), 0.25),
    )

    # THE CORNER IS BUILT FIRST, because the rolling cut is WRITTEN by the
    # stage: a reading taken before it sees the pre-cut cells, which is not
    # the input the 6x6 the user gets is assembled from.
    emit("=" * 78)
    emit("THE BUILT CORNER, both sides (rolling construction, default face)")
    emit("=" * 78)
    built = {}
    for label, doc, strips, _hint, _leader in sides:
        built[label.split()[0]] = _build_corner(label.split()[0], doc, strips,
                                                None, OPS, SC, M,
                                                SilkChecks, Part)
    for label, doc, strips, member_patch_candidate, leader in sides:
        emit("=" * 78)
        emit(title_of(label))
        emit("=" * 78)
        _one_side(emit, doc, strips, member_patch_candidate, leader,
                  OPS, SC, M, R, SilkChecks, Part)

    emit("")
    emit("=" * 78)
    emit("THE SHIPPED CONSTRUCTION, both fixtures (the fallback must not "
         "move)")
    emit("=" * 78)
    for label, fixture in (("CUBE", "cube"), ("DEMO", "demo")):
        for line in _shipped_report(label, fixture, OPS, SC, M, SilkChecks,
                                    Part, CCM, DEMO):
            emit(line)

    emit("")
    emit("=" * 78)
    emit("THE TWO READINGS THE FOLD IS COUNTED IN (post-cut, the built ones)")
    emit("=" * 78)
    for key in ("CUBE", "DEMO"):
        for line in built.get(key) or []:
            emit(line)
    return out


def title_of(label):
    return label


def _one_side(emit, doc, strips, member_hint, leader, OPS, SC, M, R,
              SilkChecks, Part):
    """Every reading for ONE ring, printed."""
    ordered, why = M.corner_ring_3(strips)
    emit("")
    emit("RING ORDER  %s  (%s)"
         % (", ".join(s.Name for s in (ordered or [])), why or "a 3-cycle"))

    # -- 1. per patch: the intervals, the corner cells, the corner cell ----
    patches = []
    for s in ordered or []:
        for pth in (s.PatchA, s.PatchB):
            if pth is not None and pth not in patches:
                patches.append(pth)
    emit("")
    emit("1. THE AXES, per ring patch (build_intervals == the subgrid cells)")
    emit("   %-9s %-22s %-22s %-11s %-11s %s"
         % ("patch", "U Split / Leader", "V Split / Leader",
            "U intervals", "V intervals", "corner cells (U / V)"))
    for pth in patches:
        us, vs = M.split_pair(pth, "U"), M.split_pair(pth, "V")
        ul, vl = M.leader_pair(pth, "U"), M.leader_pair(pth, "V")
        uiv, viv = M.build_intervals(*us, *ul), M.build_intervals(*vs, *vl)
        uc = sorted(M.corner_cells(*us, len(uiv), *ul))
        vc = sorted(M.corner_cells(*vs, len(viv), *vl))
        emit("   %-9s %-22s %-22s %-11d %-11d %s / %s"
             % (pth.Name, "%s + %s" % (us, ul), "%s + %s" % (vs, vl),
                len(uiv), len(viv), uc, vc))
        for letter, ivs, pair in (("U", uiv, us), ("V", viv, vs)):
            emit("       %s: %s" % (letter, _ivs_str(ivs)))

    # -- 2. the member patch's own corner cell -----------------------------
    member_patch = member_hint
    cells = {}
    for s in ordered or []:
        for pth in (s.PatchA, s.PatchB):
            if pth is None:
                continue
            cells[pth.Name] = SC.CornerBlend._corner_cell(pth, ordered,
                                                          SC.CORNER_DEFAULT_TOL)
    emit("")
    emit("2. THE PATCH'S CORNER CELL (SilkCorner.CornerBlend._corner_cell)")
    for pth in patches:
        got = cells.get(pth.Name) or (None, None, None, None)
        tag = "  <- MEMBER PATCH" if pth is member_patch else ""
        emit("   %-9s iu_c=%s iv_c=%s   nu=%s nv=%s%s"
             % (pth.Name, got[0], got[1], got[2], got[3], tag))
        if got[0] is not None and got[2] is not None:
            uiv = M.axis_intervals(pth, "U")
            viv = M.axis_intervals(pth, "V")
            emit("             u %s   x   v %s   (the cell's own rectangle)"
                 % (uiv[got[0]], viv[got[1]]))
    emit("   ring_corner_gap per patch: %s"
         % ", ".join("%s=%r" % (p.Name, M.ring_corner_gap(p))
                     for p in patches))

    # -- 3. band_extent per (seam, patch) ---------------------------------
    emit("")
    emit("3. THE BAND PER (SEAM, PATCH) -- band_extent with the ring's end")
    for s in ordered or []:
        for pth in (s.PatchA, s.PatchB):
            e, ss = SC.side_and_end(s, pth, SC.CORNER_DEFAULT_TOL)
            if not e:
                emit("   %-6s %-9s  no shared edge" % (s.Name, pth.Name))
                continue
            end = None
            try:
                end, end_why = OPS.seam_junction_end(s, pth, ordered,
                                                     SC.CORNER_DEFAULT_TOL)
            except Exception as exc:              # noqa: BLE001
                end_why = repr(exc)
            got = M.band_extent(pth, e, ss, end)
            tag = "  <- MEMBER PATCH" if pth is member_patch else ""
            emit("   %-6s %-9s seam %s/%d  end %r %s%s"
                 % (s.Name, pth.Name, e, ss, end, tag,
                    "" if got[0] is not None else "  REFUSED: %s" % (got[1],)))
            if got[0] is not None:
                emit("          along %s   across %s   corner_end %s"
                     % (got[0], got[1], got[2]))

    # -- 4. the ring as assembled -----------------------------------------
    grids, grid_cells, why = SC.corner_inputs(strips)
    emit("")
    emit("4. THE RING AS ASSEMBLED (corner_inputs -> the 4 member grids)")
    if grids is None:
        emit("   REFUSED: %s" % why)
        return
    for k, (poles, _weights) in enumerate(grids):
        name = "member %d" % k
        deg = [v for v in range(4) if R._row_degeneracy(poles, v) >= 5]
        emit("   %s bbox %s  rows 2->3 step %.4f mm  row3 span %.4f mm  "
             "collapsed row(s) %s"
             % (name, _bbox_str(poles), _dist3(poles[18], poles[12]),
                _dist3(poles[18], poles[23]), deg or "none"))
        for v in range(4):
            emit("       row V%d  %s" % (v, _row_str(poles, v)))
    emit("")
    emit("   THE FOUR PAIRS (pair_common's (i, j) and the rows each reads)")
    for k in range(len(grids)):
        a, b = grids[k], grids[(k + 1) % len(grids)]
        common, why = M.pair_common(a[0], b[0], 1e-6)
        if common is None:
            emit("     pair %d: %s" % (k, why))
            continue
        i, j = common
        emit("     pair %d: corners (%d, %d)%s  g0 rows %s  g1 rows %s"
             % (k, i, j, "  [SWAPPED]" if M._pair_needs_swap(common) else "",
                R.READ_ROWS.get(("g0", i), "-"),
                R.READ_ROWS.get(("g1", j), "-")))

    # -- 5. the member's row order ----------------------------------------
    emit("")
    emit("5. THE MEMBER PATCH'S ROW ORDER (SilkCorner._member_row_order)")
    order = SC._member_row_order(member_patch)
    emit("   ring_corner_gap(%s) = %r -> tried %s FIRST"
         % (member_patch.Name, M.ring_corner_gap(member_patch),
            "REAL-ROW-FIRST (%r)" % (order,) if order != SC._MEMBER_ROW_ORDER
            else "AS BUILT (%r)" % (order,)))
    emit("   the member pin the stage resolves: %r"
         % (SC.corner_member_pin(strips)[0],))
    cell_net = SC._corner_cell_net(member_patch,
                                  grid_cells.get(member_patch.Name))
    if cell_net[0]:
        emit("   the member's CELL net (16 poles) bbox %s"
             % _bbox_str(cell_net[0]))

    # -- 6. raw 6x6 and where it lands on the member patch ----------------
    subs = []
    for k in range(len(grids)):
        a, b = grids[k], grids[(k + 1) % len(grids)]
        sp, sw, s_why = M.subgrid33_2grid64(a[0], a[1], b[0], b[1])
        if sp is None:
            emit("")
            emit("6. THE RAW 6x6: subgrid %d refused (%s)" % (k, s_why))
            return
        subs.append((sp, sw))
    praw, _wraw = M.control_grid66_4sub(subs)
    emit("")
    emit("6. THE RAW 6x6 (subgrid33 x4 -> control_grid66_4sub)")
    emit("   coincident pairs %d/630   collapsed side %r   bbox %s"
         % (_coins(praw), M._collapsed_side(praw, 1e-6), _bbox_str(praw)))
    emit("   %-8s %-15s %-15s %-11s %-24s %-24s"
         % ("pair", "g0 (from)", "g1 (from)", "corner(i,j)",
            "g0 reads rows/cols", "g1 reads rows/cols"))
    for k, (sp, _sw) in enumerate(subs):
        a, b = grids[k], grids[(k + 1) % len(grids)]
        common, _why = M.pair_common(a[0], b[0], 1e-6)
        i, j = common
        emit("   %-8d %-15s %-15s %-11s %-24s %-24s"
             % (k, "member %d" % k, "member %d" % ((k + 1) % len(grids)),
                "(%d, %d)" % (i, j),
                "%s / %s" % (R.READ_ROWS[("g0", i)][0],
                             R.READ_ROWS[("g0", i)][1]),
                "%s / %s" % (R.READ_ROWS[("g1", j)][0],
                             R.READ_ROWS[("g1", j)][1])))
        emit("            subgrid bbox %s" % _bbox_str(sp))

    emit("")
    emit("   THE FOLD, LOCATED: normal-field flips inside each 3x3 subgrid "
         "(its own quadratic Bezier, n=9) and in the 6x6's four quadrants")
    for k, (sp, sw) in enumerate(subs):
        flips = _quad_flips(sp)
        emit("     subgrid %d (members %d/%d): %2d flips  %s"
             % (k, k, (k + 1) % len(grids), len(flips),
                ", ".join("(%.2f,%.2f)" % uv for uv in flips[:6])))
    quad = {(False, False): 0, (False, True): 0, (True, False): 0,
            (True, True): 0}
    exact = _net_flips(praw, _wraw)
    for u, v in exact:
        quad[(u > 0.5, v > 0.5)] = quad.get((u > 0.5, v > 0.5), 0) + 1
    emit("     6x6 exact-net flips %d at n=39  by quadrant  ul/bl/ur/lr "
         "(u>0.5, v>0.5): %d %d %d %d"
         % (len(exact), quad[(False, False)], quad[(True, False)],
            quad[(False, True)], quad[(True, True)]))
    emit("       (the quadrants are subgrids 0 / 3 / 1 / 2, per "
         "SilkMachinery._CG66_MAP)")

    emit("")
    emit("   THE STEP (wired into corner_grid): `smooth_folding_interior` -- "
         "a 6x6 with no collapsed side that folds gets the Coons interior")
    emit("     assembled net: fold count %d at n=12, %d at n=24"
         % (M.net_fold_count(praw, _wraw),
            M.net_fold_count(praw, _wraw, n=24)))
    refilled, _rw = M.coons_fill_interior(praw, _wraw)
    moved = max((refilled[i] - praw[i]).Length for i in range(36))
    bnd = [k for k in range(36)
           if k // 6 in (0, 5) or k % 6 in (0, 5)]
    bcheck = max((refilled[i] - praw[i]).Length for i in bnd)
    emit("     coons refill: fold count %d at n=12, %d at n=24 ; interior "
         "poles moved up to %.6f mm, BOUNDARY poles moved %.3e mm"
         % (M.net_fold_count(refilled, _rw),
            M.net_fold_count(refilled, _rw, n=24), moved, bcheck))
    gated_p, _gw = M.smooth_folding_interior(praw, _wraw)
    if gated_p is not praw:
        state = "REFILLED (the refill folds less)"
    elif M.net_fold_count(praw, _wraw):
        state = "UNCHANGED (the refill did not fold less)"
    else:
        state = "UNCHANGED (the net does not fold)"
    emit("     smooth_folding_interior (gated): %s; fold count %d at n=12"
         % (state, M.net_fold_count(gated_p, _gw)))

    base = getattr(getattr(member_patch, "Proxy", None), "_base_surface", None)
    net = _net_of(base) if base is not None else (None, None)
    cell = grid_cells.get(member_patch.Name)
    uiv = M.axis_intervals(member_patch, "U")
    viv = M.axis_intervals(member_patch, "V")
    if cell and cell[0] is not None:
        cell_u, cell_v = uiv[cell[1]], viv[cell[2]]
    else:
        cell_u = cell_v = None
    emit("")
    emit("   THE CORNER CELL on %s is u %s x v %s"
         % (member_patch.Name, cell_u, cell_v))
    emit("   WHERE EACH 6x6 POLE SITS ON THAT PATCH (u, v; '.' = the pole is "
         "not on this patch)")
    if net[0] is None:
        emit("   (no base net read)")
    else:
        npoles, nweights = net
        inside = 0
        umin, umax, vmin, vmax = 9.0, -9.0, 9.0, -9.0
        for i in range(6):
            row = []
            for j in range(6):
                pt = praw[i * 6 + j]
                d, u, v = R.surface_uv(npoles, nweights, (pt.x, pt.y, pt.z))
                if d > 1e-3:
                    row.append("    .    ")
                    continue
                row.append("(%6.3f,%6.3f)" % (u, v))
                umin, umax = min(umin, u), max(umax, u)
                vmin, vmax = min(vmin, v), max(vmax, v)
                if cell_u is not None:
                    if cell_u[0] - 1e-9 <= u <= cell_u[1] + 1e-9 \
                            and cell_v[0] - 1e-9 <= v <= cell_v[1] + 1e-9:
                        inside += 1
            emit("     row %d: %s" % (i, " ".join(row)))
        if cell_u is not None:
            emit("   the 6x6's net spans u %.4f..%.4f  v %.4f..%.4f ; the cell "
                 "is u %.4f..%.4f  v %.4f..%.4f"
                 % (umin, umax, vmin, vmax, cell_u[0], cell_u[1],
                    cell_v[0], cell_v[1]))
            emit("   -> %d of 36 6x6 poles land INSIDE the cell; the net "
                 "exceeds it by u %.4f..%.4f, v %.4f..%.4f"
                 % (inside, umin - cell_u[0], umax - cell_u[1],
                    vmin - cell_v[0], vmax - cell_v[1]))

    # the ring rows themselves, in the member patch's parameters: this is
    # where each SIDE of the 6x6 comes from
    emit("")
    emit("   THE FOUR 6x6 SIDES AND THE RING ROW EACH IS (the strip rows the "
         "assembly copies)")
    for k, (poles, _w) in enumerate(grids):
        for v in (3, 2):
            pts = [poles[v * 6 + u] for u in range(6)]
            emit("     member %d row V%d: %s"
                 % (k, v, _side_uv(pts, net, R)))

    emit("   member patch band cells per ring seam: %s"
         % ", ".join("%s=%r" % (s.Name, M.band_cells(
             member_patch, *(SC.side_and_end(s, member_patch,
                                             SC.CORNER_DEFAULT_TOL))))
             for s in (ordered or [])
             if SC.side_and_end(s, member_patch,
                                SC.CORNER_DEFAULT_TOL)[0]))

    # -- 7. the extents that make the corner big or small -----------------
    emit("")
    emit("7. THE SCALES (mm)")
    emit("   member patch base bbox %s"
         % _bbox_str(_net_poles(net[0])) if net[0] else "   (no net)")
    for s in ordered or []:
        e, ss = SC.side_and_end(s, member_patch, SC.CORNER_DEFAULT_TOL)
        if not e:
            continue
        end = None
        try:
            end, _why = OPS.seam_junction_end(s, member_patch, ordered,
                                              SC.CORNER_DEFAULT_TOL)
        except Exception:                          # noqa: BLE001
            end = None
        got = M.band_extent(member_patch, e, ss, end)
        if got[0] is None:
            continue
        g = member_patch.Proxy.getSubgrid
        (a0, a1), (b0, b1) = got[0], got[1]
        if e[0] == "V":          # band across U, along V
            bp, _bw = g(a0, a1, b0, b1)
        else:
            bp, _bw = g(b0, b1, a0, a1)
        flat = [bp[r][c] for r in range(4) for c in range(4)]
        emit("   %-6s on %s: band cell bbox %s (%.3f mm along the seam axis)"
             % (s.Name, member_patch.Name, _bbox_str(flat),
                _bbox_extent(flat)))


def _shipped_report(label, fixture, OPS, SC, M, SilkChecks, Part, CCM,
                    DEMO):
    """The SHIPPED corner on one fixture: the numbers my step must not move.

    The shipped construction collapses one side of the 6x6 (its member is
    the patch's corner cell read as built), so `smooth_degenerate_cap` owns
    it and `smooth_folding_interior` is gated OFF structurally.  Printed as
    a measurement, not a claim: the coincident pairs, the fold count the gate
    reads, and the flips."""
    import FreeCAD
    for name, d in list(FreeCAD.listDocuments().items()):
        if d.Label == "_rowdiff_shipped_%s" % fixture:
            FreeCAD.closeDocument(name)
    doc = FreeCAD.newDocument("_rowdiff_shipped_%s" % fixture)
    FreeCAD.setActiveDocument(doc.Name)
    try:
        if fixture == "cube":
            res = CCM.build_cube_corner_model(doc)
            strips = [res["strips"][n] for n in ("B_AB", "B_BC", "B_CA")]
        else:
            res = DEMO.build(doc, corners=False)
            strips = [doc.getObject(n) for n in DEMO_RING]
        doc.recompute()
        corner = OPS.create_corner_blend(strips, construction="shipped")
        doc.recompute()
        out = ["%s shipped: %s  construction=%r"
               % (label, getattr(corner, "Name", None),
                  None if corner is None
                  else SC.corner_construction(corner)[0])]
        if corner is None or not corner.Poles:
            out.append("   built NOTHING")
            return out
        poles = list(corner.Poles)
        weights = list(corner.Weights or [1.0] * 36)
        out.append("   poles %d  coincident %d/630  collapsed side %r  "
                   "area %.6f mm^2"
                   % (len(poles), _coins(poles),
                      M._collapsed_side(poles, SC.CORNER_TOL),
                      corner.Shape.Area))
        out.append("   the gate `smooth_folding_interior` reads: collapsed "
                   "side %r -> the step is %s; fold count %d at n=12"
                   % (M._collapsed_side(poles, SC.CORNER_TOL),
                      "GATED OFF" if M._collapsed_side(poles,
                                                       SC.CORNER_TOL)
                      is not None else "reachable",
                      M.net_fold_count(poles, weights)))
        flips = [len(SilkChecks._normal_field_flips(
            corner.Shape.Faces[0].Surface, n=n)[0])
            for n in (39, 81, 150)]
        out.append("   quad normal flips n=39/81/150: %r" % (flips,))
        return out
    finally:
        if doc.Name in FreeCAD.listDocuments():
            FreeCAD.closeDocument(doc.Name)


def render_artifact():
    """Save the demo model with its rolled corner and render it.

    `Resources/Test_files/_inspect/demo_rolled_corner.FCStd` -- the whole
    demo model (12 Edges, 5 Patches, 8 Blends) with CB_J1 rolled -- and
    `demo_rolled_corner.png`, ONE camera on the junction: the corner
    (orange), the triangular member (blue), P_Top (green) and P_Right
    (purple).  RUNS INSIDE THE GUI FREECAD (it needs a 3D view)."""
    import FreeCAD
    import FreeCADGui as Gui
    import demo01_fixture_model as DEMO
    import SilkWorkflowOps as OPS

    out_dir = os.path.join(REPO, "Resources", "Test_files", "_inspect")
    os.makedirs(out_dir, exist_ok=True)
    fcd = os.path.join(out_dir, "demo_rolled_corner.FCStd")
    png = os.path.join(out_dir, "demo_rolled_corner.png")
    label = "_rowdiff_artifact"
    for name, d in list(FreeCAD.listDocuments().items()):
        if d.Label == label:
            FreeCAD.closeDocument(name)
    doc = FreeCAD.newDocument(label)
    FreeCAD.setActiveDocument(doc.Name)
    lines = []
    DEMO.build(doc, corners=False)
    doc.recompute()
    strips = [doc.getObject(n) for n in DEMO_RING]
    corner = OPS.create_corner_blend(strips, construction="rolling",
                                    name=DEMO_CORNER)
    doc.recompute()
    if corner is None:
        lines.append("ARTIFACT: the corner did not build -- nothing saved")
        return lines
    member = None
    for o in doc.Objects:
        if getattr(o, "object_type", None) == "RollingMemberFace":
            member = o
    lines.append("          corner %s construction=%r, tri %s"
                 % (corner.Name, SC_construction(corner),
                    getattr(member, "Name", None)))
    # ONE camera, on the JUNCTION: the corner (orange) and the tri (blue) are
    # framed first -- those two objects ARE the corner, and fitting THEM is
    # what puts the eye on it -- and the two patches are revealed afterwards,
    # WITHOUT re-fitting, so they read as context around the junction instead
    # of shrinking it to a strip.
    view = Gui.getDocument(doc.Name).ActiveView
    focus = [corner.Name]
    if member is not None:
        focus.append(member.Name)
    patches = {"P_Top": (0.25, 0.75, 0.30), "P_Right": (0.60, 0.30, 0.80)}
    colours = {corner.Name: (1.00, 0.67, 0.00)}
    if member is not None:
        colours[member.Name] = (0.20, 0.45, 0.95)
    colours.update(patches)
    for o in doc.Objects:
        if o.ViewObject is None:
            continue
        for prop in ("ShowGrid", "ShowPolygon", "ShowCurve"):
            if getattr(o, prop, None) is not None:
                try:
                    setattr(o, prop, False)
                except Exception:
                    pass
        o.ViewObject.Visibility = (o.Name in focus)
    for name, rgb in colours.items():
        o = doc.getObject(name)
        if o is None or o.ViewObject is None:
            continue
        o.ViewObject.ShapeColor = rgb
        o.ViewObject.Transparency = 0 if name in focus else 45
    doc.recompute()
    view.setCameraType("Orthographic")
    view.viewIsometric()
    view.fitAll()
    # pulled back by a factor, so the junction AND a margin of both patches
    # are in the frame: `fitAll` fits the corner exactly, which puts the
    # patches at the picture's edge
    view.getCameraNode().height.setValue(
        view.getCameraNode().height.getValue() * 1.6)
    for name in patches:
        o = doc.getObject(name)
        if o is not None and o.ViewObject is not None:
            o.ViewObject.Visibility = True
    view.redraw()
    view.saveImage(png, 1600, 1200, "White")
    doc.saveAs(fcd)
    lines.append("ARTIFACT  %s  (%.1f kB, %d objects)"
                 % (fcd, os.path.getsize(fcd) / 1024.0, len(doc.Objects)))
    lines.append("ARTIFACT  %s  (%.1f kB)"
                 % (png, os.path.getsize(png) / 1024.0))
    return lines


def SC_construction(corner):
    """`SilkCorner.corner_construction` without importing it twice."""
    import SilkCorner as SC
    return SC.corner_construction(corner)[0]


def _build_corner(label, doc, strips, pin, OPS, SC, M, SilkChecks, Part):
    """Build the rolling corner in `doc` and print the two fold readings."""
    import FreeCAD
    FreeCAD.setActiveDocument(doc.Name)
    corner = OPS.create_corner_blend(strips, construction="rolling")
    doc.recompute()
    out = ["", "%s: %s  construction=%r" % (label, getattr(corner, "Name",
                                                           None),
                                           None if corner is None
                                           else SC.corner_construction(corner)[0])]
    if corner is None or not corner.Poles:
        out.append("   the corner stage built NOTHING (see the console)")
        return out
    flips = []
    for n in (39, 81, 150):
        flips.append(len(SilkChecks._normal_field_flips(
            corner.Shape.Faces[0].Surface, n=n)[0]))
    out.append("   quad: poles %d  coincident %d/630  collapsed side %r  "
               "area %.6f mm^2" % (len(corner.Poles),
                                   _coins(corner.Poles),
                                   M._collapsed_side(list(corner.Poles),
                                                     1e-6),
                                   corner.Shape.Area))
    bb = corner.Shape.BoundBox
    out.append("   quad extent %.4f mm  bbox (%.4f %.4f %.4f)..(%.4f %.4f "
               "%.4f)" % (_bbox_extent_of_shape(corner.Shape),
                          bb.XMin, bb.YMin, bb.ZMin, bb.XMax, bb.YMax,
                          bb.ZMax))
    out.append("   quad normal flips n=39/81/150: %r" % (flips,))
    gated, gw = M.smooth_folding_interior(list(corner.Poles), list(corner.Weights))
    if gated is not corner.Poles and gated != list(corner.Poles):
        gflips = []
        for n in (39, 81, 150):
            surf = _part_of(gated, gw, Part)
            gflips.append(len(SilkChecks._normal_field_flips(surf, n=n)[0]))
        out.append("   IF `smooth_folding_interior` were applied again: normal "
                   "flips n=39/81/150 %r" % (gflips,))
        out.append("   (the assembled net's own fold count: %d at n=12, "
                   "the refilled one %d)"
                   % (M.net_fold_count(list(corner.Poles),
                                       list(corner.Weights)),
                      M.net_fold_count(gated, gw)))
    for o in doc.Objects:
        if getattr(o, "object_type", None) != "RollingMemberFace":
            continue
        mflips = [len(SilkChecks._normal_field_flips(
            o.Shape.Faces[0].Surface, n=n)[0]) for n in (39, 81, 150)]
        out.append("   tri: %s  area %.6f mm^2  normal flips %r"
                   % (o.Name, o.Shape.Area, mflips))
        try:
            import reference_corner_diff as R
            d = R._reach(o, corner)
        except Exception as exc:                   # noqa: BLE001
            d = None
            out.append("   (tri-to-quad reading failed: %r)" % (exc,))
        if d:
            out.append("   tri interior -> quad: min %.5f max %.5f mm "
                       "(%.2f %%..%.2f %% of the corner extent)"
                       % (d[0], d[1], d[2], d[3]))
    return out


# ---------------------------------------------------------------------------
# small readers
# ---------------------------------------------------------------------------

def _part_of(poles, weights, Part):
    """A `Part.BSplineSurface` from a 6x6 rational net (flips' 2nd reader)."""
    from g2_corner_roll_measure import _part_surface
    return _part_surface(list(poles), list(weights), 6)


def _bez3(pts, n=9):
    """Sample a quadratic Bezier 3x3 net; return (pts_grid, uu, vv)."""
    import FreeCAD
    out = []
    for a in range(n + 1):
        u = a / float(n)
        bu = ((1 - u) ** 2, 2 * u * (1 - u), u * u)
        for b in range(n + 1):
            v = b / float(n)
            bv = ((1 - v) ** 2, 2 * v * (1 - v), v * v)
            x = y = z = 0.0
            for i in range(3):
                for j in range(3):
                    c = bu[i] * bv[j]
                    p = pts[i * 3 + j]
                    x += c * p.x
                    y += c * p.y
                    z += c * p.z
            out.append((a, b, u, v, FreeCAD.Vector(x, y, z)))
    return out


def _quad_flips(pts, n=9):
    """Where a 3x3 quadratic net's normal field reverses, in its own (u, v)."""
    import FreeCAD
    grid = {}
    for a, b, u, v, pt in _bez3(pts, n):
        grid[(a, b)] = pt
    normals = {}
    h = 1.0 / n
    for (a, b), pt in grid.items():
        du = grid.get((a + 1, b), pt) - grid.get((a - 1, b), pt)
        dv = grid.get((a, b + 1), pt) - grid.get((a, b - 1), pt)
        nv = du.cross(dv)
        normals[(a, b)] = None if nv.Length < 1e-12 else nv
    out = []
    for (a, b), nv in normals.items():
        if nv is None:
            continue
        for (da, db) in ((1, 0), (0, 1)):
            nb = normals.get((a + da, b + db))
            if nb is not None and nv.dot(nb) < -1e-6:
                out.append(((a + 0.5 * da) / n, (b + 0.5 * db) / n))
    return out


def _net_flips(poles, weights, n=40):
    """Exact-net normal flips of a 6x6, as (u, v) samples."""
    net = _silk_net(list(poles), list(weights or [1.0] * 36))
    ns = {}
    for i in range(n):
        for j in range(n):
            nrm = net.normal((i + 0.5) / n, (j + 0.5) / n)
            ns[(i, j)] = None if nrm.Length < 1e-12 else nrm
    out = []
    for (i, j), a in ns.items():
        if a is None:
            continue
        for (ii, jj) in ((i - 1, j), (i, j - 1)):
            if ii < 0 or jj < 0:
                continue
            b = ns.get((ii, jj))
            if b is not None and a.dot(b) < -1e-6:
                out.append(((i + 0.5) / n, (j + 0.5) / n))
    return out


def _silk_net(poles, weights):
    import silk_nurbs as SN
    return SN.NurbsSurface.from_flat(poles, weights, 6, 6, SN.KNOTS_6,
                                     SN.KNOTS_6)


def _side_uv(pts, net, R):
    """One strip row, as the member patch's own (u, v) where it inverts."""
    if net[0] is None:
        return "-"
    npoles, nweights = net
    out = []
    for pt in pts:
        d, u, v = R.surface_uv(npoles, nweights, (pt.x, pt.y, pt.z))
        out.append("(%.3f,%.3f)" % (u, v) if d <= 1e-3 else "  .  ")
    return " ".join(out)


def _ivs_str(ivs):
    return " | ".join("[%.4g, %.4g]" % iv for iv in ivs)


def _dist3(a, b):
    d = a - b
    return (d.x ** 2 + d.y ** 2 + d.z ** 2) ** 0.5


def _row_str(poles, v):
    return " ".join("(%.3f %.3f %.3f)" % tuple(poles[v * 6 + u])
                    for u in range(6))


def _bbox_extent(pts):
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    zs = [p[2] for p in pts]
    return max(max(xs) - min(xs), max(ys) - min(ys), max(zs) - min(zs))


def _bbox_str(pts):
    if not pts:
        return "-"
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    zs = [p[2] for p in pts]
    return ("(%.3f %.3f %.3f)..(%.3f %.3f %.3f) extent %.4f"
            % (min(xs), min(ys), min(zs), max(xs), max(ys), max(zs),
               _bbox_extent(pts)))


def _bbox_extent_of_shape(shape):
    bb = shape.BoundBox
    return max(bb.XLength, bb.YLength, bb.ZLength)


def _net_of(base):
    """(poles, weights) as a flat 4x4 [u][v] list from a base surface."""
    try:
        poles = base.getPoles()
        weights = base.getWeights()
    except Exception:                              # noqa: BLE001
        return None, None
    flat = []
    wflat = []
    for u in range(4):
        for v in range(4):
            p = poles[u][v]
            flat.append((p.x, p.y, p.z))
            wflat.append(float(weights[u][v]))
    return flat, wflat


def _net_poles(net):
    return list(net) if net else []


def _coins(poles, tol=1e-7):
    n = 0
    for i in range(len(poles)):
        for j in range(i):
            d = poles[i] - poles[j]
            if d.Length <= tol:
                n += 1
    return n


# ---------------------------------------------------------------------------
# The launcher: send the module's own `row_diff` to the owner's FreeCAD
# ---------------------------------------------------------------------------

BOOT = r'''
import sys
sys.path.insert(0, %(repo)r)
sys.path.insert(0, %(here)r)
for _m in [m for m in list(sys.modules)
           if m.split(".")[0] in ("SilkMachinery", "SilkCorner",
                                  "SilkWorkflowOps", "SilkBlend", "SilkPatch",
                                  "SilkEdge", "SilkChecks", "Silk_dummy",
                                  "cube_corner_model", "demo01_fixture_model",
                                  "reference_corner_diff",
                                  "demo_corner_row_diff", "ArachNURBS")]:
    del sys.modules[_m]
import FreeCAD
import demo_corner_row_diff as D
for _line in D.row_diff():
    print(_line)
for _line in D.render_artifact():
    print(_line)
for _n, _d in list(FreeCAD.listDocuments().items()):
    if _d.Label in ("_rowdiff_cube", "_rowdiff_demo", "_rowdiff_artifact"):
        FreeCAD.closeDocument(_n)
'''


def rpc_execute(code, timeout=900):
    """Send `code` to the owner's running FreeCAD. NEVER spawns one."""
    import xmlrpc.client
    proxy = xmlrpc.client.ServerProxy("http://%s:%d/" % (RPC_HOST, RPC_PORT))
    proxy.ping()
    res = proxy.execute_code(code, timeout)
    if not res.get("success"):
        raise SystemExit("RPC error: %s" % res.get("error"))
    return res.get("message", "")


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    text = rpc_execute(BOOT % {"repo": REPO, "here": HERE})
    print(text)
    dest = os.path.join(REPO, "Resources", "Test_files", "_inspect",
                        "step1_demo_corner_row_diff.txt")
    try:
        with open(dest, "w") as fh:
            fh.write(text if text.endswith("\n") else text + "\n")
        print("[raw output kept: %s]" % dest)
    except OSError as exc:
        print("[could not keep the raw output: %r]" % (exc,))
    return 0


if __name__ == "__main__":
    sys.exit(main())
