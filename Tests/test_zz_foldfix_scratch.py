"""SCRATCH (ticket-foldfix): raw fold/seam measurement dump.

NOT a permanent test. This module collects raw numbers into
/tmp/opencode/foldfix/measure.json for the ticket report:
  * normal-field flip count on the built corner surface, via
    SilkChecks._normal_field_flips (the project's neighbour-consistency
    instrument) and via the exact control net;
  * the three strip seams (sampled + exact) as
    Tests/test_cube_corner_3valent.py measures them;
  * cap sample ranges / half-space violations on the cube fixture;
  * the same readings on the corner built with the PRE-parity member
    substituted, for the honesty of "was the fold the port's?".

Delete before handoff.
"""

import json
import math
import os

import FreeCAD
import numpy as np

import SilkChecks
import SilkCorner
import SilkMachinery
import Tests.cube_corner_model as ccm
import Tests.continuity_analytic as CA
import Tests.g2_oracle as G
import Tests.silk_nurbs as SN
from SilkMachinery import corner_grid, control_grid64_3_1, reverse_grid_rows
from SilkWorkflowOps import create_corner_blend
from Tests.test_cube_corner_3valent import _part_surface, _match_side

OUT_DIR = "/tmp/opencode/foldfix"
OUT = os.path.join(OUT_DIR, "measure.json")
STRIP_NAMES = ("B_AB", "B_BC", "B_CA")


def _prefix_member(grid_poles, grid_weights, corner):
    """The pre-ticket-foldfix `control_grid64_3_1` (git b308164), for the
    before/after fold reading only."""
    if corner not in (0, 1, 2, 3):
        return None, None
    rotate = corner
    lp = list(grid_poles)
    lw = list(grid_weights)
    if len(lp) != 16 or len(lw) != 16:
        return None, None
    Apoles = [list(lp[0:4]), list(lp[4:8]), list(lp[8:12]), list(lp[12:16])]
    Aweights = [list(lw[0:4]), list(lw[4:8]), list(lw[8:12]),
                list(lw[12:16])]
    uv_poles_temp = np.rot90(Apoles, rotate).tolist()
    uv_weights = np.rot90(Aweights, rotate).tolist()
    uv_poles = [[None] * 4 for _ in range(4)]
    for i in range(4):
        for j in range(4):
            v = uv_poles_temp[i][j]
            uv_poles[i][j] = FreeCAD.Vector(v[0], v[1], v[2])
    set_poles = [uv_poles[i][j] for i in range(4) for j in range(4)]
    set_weights = [uv_weights[i][j] for i in range(4) for j in range(4)]
    p = [FreeCAD.Vector(x) for x in set_poles]
    w = [float(x) for x in set_weights]
    p00 = p[12]; p01 = p[8]; p02 = p[4]; p03 = p[1]; p04 = p[2]; p05 = p[3]
    p10 = p[13]; p11 = p[9]
    p14 = p[6]; p15 = p[7]
    p20 = p[14]
    p21 = p[14] + (p[10] - p[14]) * 0.5
    p22 = p21 + (p[10] - p21) * 0.5
    p24 = p[15] + (p[10] - p[15]) * 0.5
    p23 = p24 + (p[10] - p24) * 0.5
    p25 = p[11]
    p30 = p[15]; p31 = p[15]; p32 = p[15]; p33 = p[15]; p34 = p[15]; p35 = p[15]
    p12 = (p[5] + p[11]) * 0.5
    p13 = (p[5] + p[6]) * 0.5
    out_poles = [p00, p01, p02, p03, p04, p05,
                 p10, p11, p12, p13, p14, p15,
                 p20, p21, p22, p23, p24, p25,
                 p30, p31, p32, p33, p34, p35]
    w00 = w[12]; w01 = w[8]; w02 = w[4]; w03 = w[1]; w04 = w[2]; w05 = w[3]
    w10 = w[13]; w11 = w[9]
    w14 = w[6]; w15 = w[7]
    w20 = w[14]
    w21 = w[10]; w22 = w[10]; w23 = w[10]; w24 = w[10]
    w25 = w[11]
    w30 = w[15]; w31 = w[15]; w32 = w[15]; w33 = w[15]; w34 = w[15]; w35 = w[15]
    w12 = (w[5] + w[11]) * 0.5
    w13 = (w[5] + w[6]) * 0.5
    out_weights = [w00, w01, w02, w03, w04, w05,
                   w10, w11, w12, w13, w14, w15,
                   w20, w21, w22, w23, w24, w25,
                   w30, w31, w32, w33, w34, w35]
    return out_poles, out_weights


def _flips_exact(net, n):
    """Neighbour-consistency flips read off the exact net (the same rule
    as SilkChecks._normal_field_flips: sample cell centres, compare each
    with its left and upper neighbour, flip = dot < -1e-6)."""
    ns = []
    for i in range(n):
        for j in range(n):
            nrm = net.normal((i + 0.5) / n, (j + 0.5) / n)
            ns.append(None if nrm.Length < 1e-12 else nrm)
    flips = []
    for i in range(n):
        for j in range(n):
            a = ns[i * n + j]
            if a is None:
                continue
            for (ii, jj) in ((i - 1, j), (i, j - 1)):
                if ii < 0 or jj < 0:
                    continue
                b = ns[ii * n + jj]
                if b is not None and a.dot(b) < -1e-6:
                    flips.append([round((i + 0.5) / n, 4),
                                  round((j + 0.5) / n, 4)])
    return flips


def _seams(cb_flat, cb_weights, strips):
    cb_part = _part_surface(cb_flat, cb_weights, 6)
    cb_net = SN.NurbsSurface.from_flat(cb_flat, cb_weights, 6, 6,
                                       SN.KNOTS_6, SN.KNOTS_6)
    out = []
    for s in strips:
        m = _match_side(cb_flat, list(s.Poles))
        if m is None:
            out.append({"strip": s.Name, "matched": False})
            continue
        cedge, row, rev = m
        edge_st = "v0" if row == 0 else "v1"
        s_flat = list(s.Poles)
        s_weights = list(s.Weights) or [1.0] * 24
        st_part = _part_surface(s_flat, s_weights, 4)
        st_net = SN.NurbsSurface.from_flat(s_flat, s_weights, 6, 4,
                                           SN.KNOTS_6, SN.KNOTS_4)
        scb, acb = G.edge_seam(cb_part, cedge, reverse=rev)
        sst, ast = G.edge_seam(st_part, edge_st)
        sampled = G.measure_seam(cb_part, scb, acb, st_part, sst, ast,
                                 n=21)
        exact = CA.measure_edges(cb_net, cedge, rev, st_net, edge_st,
                                 False, n=21)
        c0_net, _n = SN.c0_controlnet(cb_net, cedge, st_net, edge_st,
                                      reverse=rev)
        out.append({
            "strip": s.Name, "matched": True, "cedge": cedge, "row": row,
            "reversed": rev,
            "sampled": {k: sampled[k] for k in
                        ("c0", "g1_deg", "k_gap", "twist_gap")},
            "exact": {k: exact[k] for k in
                      ("c0", "g1_deg", "k_gap", "twist_gap")},
            "c0_controlnet": c0_net,
        })
    return out


def _cap_report(cb_flat, cb_weights):
    part = _part_surface(cb_flat, cb_weights, 6)
    net = SN.NurbsSurface.from_flat(cb_flat, cb_weights, 6, 6,
                                    SN.KNOTS_6, SN.KNOTS_6)
    rep = {}
    flips39, any39 = SilkChecks._normal_field_flips(part, n=39)
    flips81, any81 = SilkChecks._normal_field_flips(part, n=81)
    rep["flips_part_n39"] = {"count": len(flips39), "any": any39,
                             "first": flips39[:24]}
    rep["flips_part_n81"] = {"count": len(flips81), "any": any81,
                             "first": flips81[:24]}
    fe39 = _flips_exact(net, 39)
    fe81 = _flips_exact(net, 81)
    rep["flips_exact_n39"] = {"count": len(fe39), "first": fe39[:24]}
    rep["flips_exact_n81"] = {"count": len(fe81), "first": fe81[:24]}
    # sample ranges + half-space violations on the unit-cube fixture
    xs, ys, zs = [], [], []
    minv = [0.0, 0.0, 0.0]
    for i in range(41):
        for j in range(41):
            pt = net.value(i / 40.0, j / 40.0)
            xs.append(pt.x); ys.append(pt.y); zs.append(pt.z)
            minv[0] = min(minv[0], pt.x)
            minv[1] = min(minv[1], pt.y)
            minv[2] = min(minv[2], pt.z)
    rep["samples"] = {"x": [min(xs), max(xs)], "y": [min(ys), max(ys)],
                      "z": [min(zs), max(zs)]}
    rep["halfspace_min"] = minv
    rep["shape_valid"] = bool(part is not None)
    return rep


def _member_t(poles_c, weights_c, corner, t):
    """The parity `control_grid64_3_1` with the third strategy's factor `t`
    (upstream: 0.5) on p21/p22/p24/p23."""
    if corner not in (0, 1, 2, 3):
        return None, None
    lp = list(poles_c)
    lw = list(weights_c)
    Apoles = [list(lp[0:4]), list(lp[4:8]), list(lp[8:12]), list(lp[12:16])]
    Aweights = [list(lw[0:4]), list(lw[4:8]), list(lw[8:12]),
                list(lw[12:16])]
    uv_poles_temp = np.rot90(Apoles, corner).tolist()
    uv_weights = np.rot90(Aweights, corner).tolist()
    uv_poles = [[None] * 4 for _ in range(4)]
    for i in range(4):
        for j in range(4):
            v = uv_poles_temp[i][j]
            uv_poles[i][j] = v if hasattr(v, "x") else \
                FreeCAD.Vector(v[0], v[1], v[2])
    p = [uv_poles[i][j] for i in range(4) for j in range(4)]
    w = [float(uv_weights[i][j]) for i in range(4) for j in range(4)]
    p00 = p[12]; p01 = p[8]; p02 = p[4]; p03 = p[1]; p04 = p[2]; p05 = p[3]
    p10 = p[13]; p11 = p[9]
    p14 = p[6]; p15 = p[7]
    p20 = p[14]
    p21 = p[14] + (p[10] - p[14]) * t
    p22 = p21 + (p[10] - p21) * t
    p25 = p[11]
    p24 = p25 + (p[10] - p25) * t
    p23 = p24 + (p[10] - p24) * t
    p30 = p[15]; p31 = p[15]; p32 = p[15]; p33 = p[15]; p34 = p[15]; p35 = p[15]
    p12 = (p[5] + p11) * 0.5
    p13 = (p[5] + p14) * 0.5
    out_poles = [p00, p01, p02, p03, p04, p05,
                 p10, p11, p12, p13, p14, p15,
                 p20, p21, p22, p23, p24, p25,
                 p30, p31, p32, p33, p34, p35]
    w00 = w[12]; w01 = w[8]; w02 = w[4]; w03 = w[1]; w04 = w[2]; w05 = w[3]
    w10 = w[13]; w11 = w[9]
    w14 = w[6]; w15 = w[7]
    w20 = w[14]
    w21 = w[10]; w22 = w[10]; w23 = w[10]; w24 = w[10]
    w25 = w[11]
    w30 = w[15]; w31 = w[15]; w32 = w[15]; w33 = w[15]; w34 = w[15]; w35 = w[15]
    w12 = (w02 + w21) * 0.5
    w13 = (w03 + w24) * 0.5
    out_weights = [w00, w01, w02, w03, w04, w05,
                   w10, w11, w12, w13, w14, w15,
                   w20, w21, w22, w23, w24, w25,
                   w30, w31, w32, w33, w34, w35]
    return out_poles, out_weights


def _find_member(grids, corner_cells, patches):
    """(idx, patch, corner, rev, input poles/weights) of the ring member."""
    for i, g in enumerate(grids):
        for pth in patches:
            cell = corner_cells.get(pth.Name)
            poles_c, weights_c = SilkCorner._corner_cell_net(pth, cell)
            if poles_c is None:
                continue
            for corner in range(4):
                mp, mw = control_grid64_3_1(poles_c, weights_c, corner)
                if mp is None:
                    continue
                for rev in (False, True):
                    cand = reverse_grid_rows(mp, mw) if rev else (list(mp),
                                                                  list(mw))
                    if max((a - b).Length for a, b in zip(cand[0], g[0])) \
                            <= 1e-9:
                        return i, pth.Name, corner, rev, poles_c, weights_c
    return None, None, None, None, None, None


def test_foldfix_sweep(doc):
    """Sweep the member's third-strategy factor t (upstream 0.5) and read
    the corner net's flip count / overshoot / seam k_gap for each."""
    os.makedirs(OUT_DIR, exist_ok=True)
    model = ccm.build_cube_corner_model(doc)
    strips = [doc.getObject(n) for n in STRIP_NAMES]
    grids, corner_cells, why = SilkCorner.corner_inputs(strips)
    if grids is None:
        return {"pass": False, "errors": ["corner_inputs: %s" % why],
                "checks": []}
    idx, pth, corner, rev, poles_c, weights_c = _find_member(
        grids, corner_cells, model["patches"].values())

    rep = {"member_index": idx, "patch": pth, "corner": corner,
           "reversed": rev, "ring_rows_v3": [], "rows": [],
           "sweep": []}
    for g in grids:
        rep["ring_rows_v3"].append(
            [[round(q.x, 6), round(q.y, 6), round(q.z, 6)]
             for q in g[0][18:24]])
    for t in (0.0, 0.02, 0.05, 0.1, 0.15, 0.2, 0.25, 0.33, 0.4, 0.5,
              0.6, 0.75, 0.9, 1.0):
        mp, mw = _member_t(poles_c, weights_c, corner, t)
        if rev:
            mp, mw = reverse_grid_rows(mp, mw)
        ring = list(grids)
        ring[idx] = (mp, mw)
        p36, w36, why2 = corner_grid(ring, SilkCorner.CORNER_TOL)
        if p36 is None:
            rep["sweep"].append({"t": t, "error": why2})
            continue
        part = _part_surface(p36, w36, 6)
        net = SN.NurbsSurface.from_flat(p36, w36, 6, 6, SN.KNOTS_6,
                                        SN.KNOTS_6)
        fl39, _ = SilkChecks._normal_field_flips(part, n=39)
        fl81, _ = SilkChecks._normal_field_flips(part, n=81)
        fe39 = _flips_exact(net, 39)
        # member's own surface flips
        mpart = _part_surface(mp, mw, 4)
        mfl39, _ = SilkChecks._normal_field_flips(mpart, n=39)
        # overshoot: max coordinate of the corner net samples
        mcoord = [0.0, 0.0, 0.0]
        for i in range(21):
            for j in range(21):
                pt = net.value(i / 20.0, j / 20.0)
                for a in range(3):
                    mcoord[a] = max(mcoord[a], (pt.x, pt.y, pt.z)[a])
        # the degenerate seam B_AB k_gap (exact)
        cb_net = net
        cb_part = part
        s = doc.getObject("B_AB")
        m = _match_side(p36, list(s.Poles))
        k_gap = None
        if m:
            cedge, row, rv = m
            st_net = SN.NurbsSurface.from_flat(
                list(s.Poles), list(s.Weights) or [1.0] * 24, 6, 4,
                SN.KNOTS_6, SN.KNOTS_4)
            ex = CA.measure_edges(cb_net, cedge, rv, st_net,
                                  "v0" if row == 0 else "v1", False, n=21)
            k_gap = ex["k_gap"]
        rep["sweep"].append({
            "t": t, "flips_part_n39": len(fl39), "flips_part_n81": len(fl81),
            "flips_exact_n39": len(fe39), "member_flips_n39": len(mfl39),
            "max_coord": mcoord, "B_AB_exact_k_gap": k_gap,
            "first_flips": fe39[:6],
        })
        rep["rows"].append({
            "t": t,
            "row_v2": [[round(q.x, 6), round(q.y, 6), round(q.z, 6)]
                       for q in mp[12:18]] if idx is not None else None,
        })
    with open(os.path.join(OUT_DIR, "sweep.json"), "w") as fh:
        json.dump(rep, fh, indent=1)
    return {"pass": True, "errors": [], "checks": ["raw -> sweep.json"]}


def _row_collapsed(g, end, tol=1e-9):
    base = end * 6
    return all((g[base + k] - g[base]).Length <= tol for k in range(6))


def _subgrid_fixed(poles_0, weights_0, poles_1, weights_1, tol=1e-6):
    """`SilkMachinery.subgrid33_2grid64` with one change: when the shared
    seam row of one grid is COLLAPSED (all six poles one point), the
    interior extrapolation past that row is replaced by an interpolation
    back toward the grid's next row. Extrapolating past a collapsed end
    row overshoots the apex and folds; this keeps the interior inside.
    The regular case is byte-identical."""
    from SilkMachinery import pair_common, CORNER_COMMON
    g0 = list(poles_0)
    g1 = list(poles_1)
    w0 = list(weights_0)
    w1 = list(weights_1)
    if not (len(g0) == len(w0) == len(g1) == len(w1) == 24):
        return None, None, "not two 24-pole grids"
    common, why = pair_common(g0, g1, tol)
    if common is None:
        return None, None, why
    swapped = False
    if common[0] in (1, 2) and common[1] in (0, 3):
        g0, g1 = g1, g0
        w0, w1 = w1, w0
        swapped = True
        common, why = pair_common(g0, g1, tol)
        if common is None:
            return None, None, why
    i, j = common
    if i == 0:
        base0 = 0
        v_col0 = [g0[0], g0[1], g0[2]]
        v_col0_w = [w0[0], w0[1], w0[2]]
        v_col1 = [g0[6], g0[7], g0[8]]
    elif i == 3:
        base0 = 18
        v_col0 = [g0[23], g0[22], g0[21]]
        v_col0_w = [w0[23], w0[22], w0[21]]
        v_col1 = [g0[17], g0[16], g0[15]]
    else:
        return None, None, "cross-seam side on grid1"
    if j == 1:
        base1 = 0
        u_row0 = [g1[5], g1[4], g1[3]]
        u_row0_w = [w1[5], w1[4], w1[3]]
        u_row1 = [g1[11], g1[10], g1[9]]
    elif j == 2:
        base1 = 18
        u_row0 = [g1[18], g1[19], g1[20]]
        u_row0_w = [w1[18], w1[19], w1[20]]
        u_row1 = [g1[12], g1[13], g1[14]]
    else:
        return None, None, "cross-seam side on grid2"

    span_v = (v_col1[0] - v_col0[0]).Length
    span_u = (u_row1[0] - u_row0[0]).Length
    if span_v <= 0.0 or span_u <= 0.0:
        return None, None, "degenerate seam row"
    u_tan_ratio = (u_row0[1] - u_row0[0]).Length / span_v
    v_tan_ratio = (v_col0[1] - v_col0[0]).Length / span_u
    deg0 = _row_collapsed(g0, base0 // 6)
    deg1 = _row_collapsed(g1, base1 // 6)

    p00 = u_row0[0]
    p01 = u_row0[1]
    p02 = u_row0[2]
    p10 = v_col0[1]
    p20 = v_col0[2]
    if deg1:
        p11_u = u_row0[1] + (u_row1[1] - u_row0[1]) * v_tan_ratio
        p12 = u_row0[2] + (u_row1[2] - u_row0[2]) * v_tan_ratio
    else:
        p11_u = p01 + (u_row0[1] - u_row1[1]) * v_tan_ratio
        p12 = p02 + (u_row0[2] - u_row1[2]) * v_tan_ratio
    if deg0:
        p11_v = v_col0[1] + (v_col1[1] - v_col0[1]) * u_tan_ratio
        p21 = v_col0[2] + (v_col1[2] - v_col0[2]) * u_tan_ratio
    else:
        p11_v = p10 + (v_col0[1] - v_col1[1]) * u_tan_ratio
        p21 = p20 + (v_col0[2] - v_col1[2]) * u_tan_ratio
    p11 = (p11_u + p11_v) * 0.5
    p22 = ((p12 + (p21 - p11)) + (p21 + (p12 - p11))) * 0.5

    w00 = u_row0_w[0]
    w01 = u_row0_w[1]
    w02 = u_row0_w[2]
    w10 = v_col0_w[1]
    w20 = v_col0_w[2]
    w11 = w01 * w10
    w12 = w02 * w10
    w21 = w01 * w20
    w22 = w02 * w20
    return ([p00, p01, p02, p10, p11, p12, p20, p21, p22],
            [w00, w01, w02, w10, w11, w12, w20, w21, w22], None)


def _corner_grid_fixed(grids, tol=1e-6):
    from SilkMachinery import (pair_common, CORNER_COMMON,
                               control_grid66_4sub)
    pairs, mirrored = [], []
    for i in range(4):
        a, b = grids[i], grids[(i + 1) % 4]
        common, why = pair_common(a[0], b[0], tol)
        if common is None:
            return None, None, why
        pairs.append(common)
        mirrored.append((common[1], common[0]))
    if all(c == CORNER_COMMON for c in pairs):
        pass
    elif all(c == CORNER_COMMON for c in mirrored):
        grids = [grids[0]] + list(reversed(grids[1:]))
    else:
        return None, None, "not a consistently oriented ring"
    subs = []
    for i in range(4):
        a, b = grids[i], grids[(i + 1) % 4]
        p, w, why = _subgrid_fixed(a[0], a[1], b[0], b[1], tol)
        if p is None:
            return None, None, why
        subs.append((p, w))
    p36, w36 = control_grid66_4sub(subs)
    return p36, w36, None


def test_foldfix_fix(doc):
    """Candidate: degeneracy-gated interpolation in the subgrid interior."""
    os.makedirs(OUT_DIR, exist_ok=True)
    model = ccm.build_cube_corner_model(doc)
    strips = [doc.getObject(n) for n in STRIP_NAMES]
    cb = create_corner_blend(*strips)
    grids, corner_cells, why = SilkCorner.corner_inputs(strips)
    rep = {"candidate": "degeneracy-gated subgrid interpolation"}
    if grids is None or cb is None:
        return {"pass": False, "errors": ["build refused: %s" % why],
                "checks": []}
    p36, w36, why2 = _corner_grid_fixed(grids, SilkCorner.CORNER_TOL)
    if p36 is None:
        return {"pass": False, "errors": ["fixed corner refused: %s" % why2],
                "checks": []}
    dev = max((a - b).Length for a, b in zip(p36, list(cb.Poles)))
    rep["net_dev_vs_shipped"] = dev
    rep["cap"] = _cap_report(p36, w36)
    rep["seams"] = _seams(p36, w36, strips)
    rep["poles"] = [[round(p.x, 9), round(p.y, 9), round(p.z, 9)]
                    for p in p36]
    with open(os.path.join(OUT_DIR, "fix.json"), "w") as fh:
        json.dump(rep, fh, indent=1)
    return {"pass": True, "errors": [], "checks": ["raw -> fix.json"]}


def _band_probe(net, us, vs):
    out = []
    for v in vs:
        row = []
        for u in us:
            p = net.value(u, v)
            nrm = net.normal(u, v)
            row.append({"u": round(u, 4), "v": round(v, 6),
                        "p": [round(p.x, 8), round(p.y, 8),
                              round(p.z, 8)],
                        "n": [round(nrm.x, 8), round(nrm.y, 8),
                              round(nrm.z, 8)]})
        out.append(row)
    return out


def _flip_diag(net, n=39, limit=8):
    ns = {}
    for i in range(n):
        for j in range(n):
            u, v = (i + 0.5) / n, (j + 0.5) / n
            ns[(i, j)] = (u, v, net.normal(u, v))
    out = []
    for (i, j), (u, v, a) in ns.items():
        for (ii, jj) in ((i - 1, j), (i, j - 1)):
            if ii < 0 or jj < 0:
                continue
            b = ns[(ii, jj)][2]
            if a.Length > 1e-12 and b.Length > 1e-12 and a.dot(b) < -1e-6:
                uu, vv, _ = ns[(ii, jj)]
                _p, pu, pv, *_ = net.ders(u, v, order=1)
                _p2, pu2, pv2, *_ = net.ders(uu, vv, order=1)
                out.append({
                    "u": round(u, 4), "v": round(v, 4),
                    "n": [round(a.x, 8), round(a.y, 8), round(a.z, 8)],
                    "n_neighbour": [round(b.x, 8), round(b.y, 8),
                                    round(b.z, 8)],
                    "dot": round(a.dot(b), 8),
                    "|Su|": round(pu.Length, 10),
                    "|Sv|": round(pv.Length, 10),
                    "|Su|_n": round(pu2.Length, 10),
                    "|Sv|_n": round(pv2.Length, 10),
                })
                if len(out) >= limit:
                    return out
    return out


def _scan_u(net, v, u0, u1, steps=71):
    out = []
    for k in range(steps):
        u = u0 + (u1 - u0) * k / (steps - 1.0)
        p = net.value(u, v)
        nn = net.normal(u, v)
        out.append([round(u, 5), round(p.x, 8), round(p.y, 8),
                    round(p.z, 8), round(nn.x, 6), round(nn.y, 6),
                    round(nn.z, 6)])
    return out


def test_foldfix_foldnature(doc):
    """Is the shipped +z normal reversal a genuine fold or aliasing at a
    degenerate parameterization? Dump the flip neighbourhoods and a fine
    u-scan through them."""
    os.makedirs(OUT_DIR, exist_ok=True)
    ccm.build_cube_corner_model(doc)
    strips = [doc.getObject(n) for n in STRIP_NAMES]
    cb = create_corner_blend(*strips)
    flat = list(cb.Poles)
    w = list(cb.Weights) or [1.0] * 36
    net = SN.NurbsSurface.from_flat(flat, w, 6, 6, SN.KNOTS_6, SN.KNOTS_6)
    rep = {"flip_diag": _flip_diag(net, 39, 12)}
    rep["scan_v088"] = _scan_u(net, 0.88, 0.15, 0.6)
    rep["scan_v09"] = _scan_u(net, 0.90, 0.15, 0.6)
    rep["scan_v095"] = _scan_u(net, 0.95, 0.15, 0.6)
    with open(os.path.join(OUT_DIR, "foldnature.json"), "w") as fh:
        json.dump(rep, fh, indent=1)
    return {"pass": True, "errors": [], "checks": ["raw -> foldnature.json"]}


def test_foldfix_probe(doc):
    """Fine probe of the collapse band on the shipped and the candidate
    nets, to tell a true fold from a fast-rotating degenerate fan."""
    os.makedirs(OUT_DIR, exist_ok=True)
    model = ccm.build_cube_corner_model(doc)
    strips = [doc.getObject(n) for n in STRIP_NAMES]
    cb = create_corner_blend(*strips)
    grids, _cc, why = SilkCorner.corner_inputs(strips)
    rep = {}
    vs = [0.95, 0.98, 0.99, 0.995, 0.999, 1.0]
    us = [0.30, 0.35, 0.40, 0.45, 0.50, 0.55, 0.60]

    def probe(tag, flat, w):
        net = SN.NurbsSurface.from_flat(flat, w, 6, 6, SN.KNOTS_6,
                                        SN.KNOTS_6)
        part = _part_surface(flat, w, 6)
        fl, _ = SilkChecks._normal_field_flips(part, n=39)
        fl81, _ = SilkChecks._normal_field_flips(part, n=81)
        fl300, _ = SilkChecks._normal_field_flips(part, n=300)
        # max neighbour dot at a very fine sampling in the band
        dmin = 1.0
        for v in [0.95, 0.98, 0.99, 0.995, 0.999]:
            for k in range(0, 40):
                u0 = 0.25 + 0.5 * k / 40.0
                u1 = 0.25 + 0.5 * (k + 1) / 40.0
                n0 = net.normal(u0, v)
                n1 = net.normal(u1, v)
                if n0.Length > 1e-12 and n1.Length > 1e-12:
                    dmin = min(dmin, n0.dot(n1))
        rep[tag] = {
            "flips_n39": len(fl), "flips_n81": len(fl81),
            "flips_n300": len(fl300),
            "min_adjacent_dot_band": dmin,
            "shape_check": bool(part.toShape().isValid()),
            "band": _band_probe(
                SN.NurbsSurface.from_flat(flat, w, 6, 6, SN.KNOTS_6,
                                          SN.KNOTS_6), us, vs),
        }

    probe("shipped", list(cb.Poles), list(cb.Weights) or [1.0] * 36)
    if grids is not None:
        p36, w36, _why2 = _corner_grid_fixed(grids, SilkCorner.CORNER_TOL)
        if p36 is not None:
            probe("candidate", p36, w36)
    with open(os.path.join(OUT_DIR, "probe.json"), "w") as fh:
        json.dump(rep, fh, indent=1)
    return {"pass": True, "errors": [], "checks": ["raw -> probe.json"]}


def test_foldfix_measure(doc):
    os.makedirs(OUT_DIR, exist_ok=True)
    model = ccm.build_cube_corner_model(doc)
    strips = [doc.getObject(n) for n in STRIP_NAMES]
    cb = create_corner_blend(*strips)
    if cb is None:
        return {"pass": False, "errors": ["corner build refused"],
                "checks": []}
    cb_flat = list(cb.Poles)
    cb_weights = list(cb.Weights) or [1.0] * 36
    rep = {"build": {"poles": len(cb_flat),
                     "faces": len(cb.Shape.Faces) if cb.Shape else 0,
                     "shape_valid": bool(cb.Shape.isValid())
                     if cb.Shape else False}}

    # ---- current (parity) corner ----
    rep["parity"] = _cap_report(cb_flat, cb_weights)
    rep["parity"]["seams"] = _seams(cb_flat, cb_weights, strips)
    rep["parity"]["poles"] = [[round(p.x, 9), round(p.y, 9),
                               round(p.z, 9)] for p in cb_flat]

    # ---- pre-parity member substituted into the same ring ----
    grids, corner_cells, why = SilkCorner.corner_inputs(strips)
    idx = None
    cand_info = None
    for i, g in enumerate(grids):
        for pth in model["patches"].values():
            cell = corner_cells.get(pth.Name)
            poles_c, weights_c = SilkCorner._corner_cell_net(pth, cell)
            if poles_c is None:
                continue
            for corner in range(4):
                mp, mw = control_grid64_3_1(poles_c, weights_c, corner)
                if mp is None:
                    continue
                for rev in (False, True):
                    cand = reverse_grid_rows(mp, mw) if rev else (list(mp),
                                                                  list(mw))
                    if max((a - b).Length for a, b in zip(cand[0], g[0])) \
                            <= 1e-9:
                        idx = i
                        cand_info = (pth.Name, corner, rev, poles_c,
                                     weights_c)
    if idx is None:
        rep["prefix"] = {"error": "member not identified in the ring"}
    else:
        pth, corner, rev, poles_c, weights_c = cand_info
        omp, omw = _prefix_member(poles_c, weights_c, corner)
        if rev:
            omp, omw = reverse_grid_rows(omp, omw)
        old_ring = list(grids)
        old_ring[idx] = (omp, omw)
        p36_old, w36_old, why_old = corner_grid(old_ring, SilkCorner.CORNER_TOL)
        if p36_old is None:
            rep["prefix"] = {"error": "old member ring refused: %s" % why_old}
        else:
            dev = max((a - b).Length for a, b in zip(p36_old, cb_flat))
            rep["prefix"] = _cap_report(p36_old, w36_old)
            rep["prefix"]["seams"] = _seams(p36_old, w36_old, strips)
            rep["prefix"]["net_dev_vs_parity"] = dev
            rep["prefix"]["identified"] = [pth, corner, rev]

    # ---- subgrid structure (which poles feed the fold region) ----
    grids2, _cc, _w = SilkCorner.corner_inputs(strips)
    pairs = []
    for i in range(4):
        pr, _why = SilkMachinery.pair_common(grids2[i][0],
                                             grids2[(i + 1) % 4][0], 1e-6)
        pairs.append(pr)
    from SilkMachinery import subgrid33_2grid64, CORNER_COMMON
    if all(p == CORNER_COMMON for p in pairs):
        pass
    elif all(p == (CORNER_COMMON[1], CORNER_COMMON[0]) for p in pairs):
        grids2 = [grids2[0]] + list(reversed(grids2[1:]))
    subs = []
    for i in range(4):
        a, b = grids2[i], grids2[(i + 1) % 4]
        p9, w9, _why = subgrid33_2grid64(a[0], a[1], b[0], b[1], 1e-6)
        subs.append(None if p9 is None else
                    [[round(q.x, 6), round(q.y, 6), round(q.z, 6)]
                     for q in p9])
    rep["subgrids"] = subs
    rep["pairs"] = pairs

    with open(OUT, "w") as fh:
        json.dump(rep, fh, indent=1)
    return {"pass": True, "errors": [], "checks": ["raw -> " + OUT]}
