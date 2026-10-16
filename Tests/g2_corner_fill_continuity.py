"""
MANUAL MEASUREMENT -- is FreeCAD `Surface::Filling` at `BoundaryOrder = 2` G2?
(ticket #100, deliverable 1.)

#91's Phase B probe (`Tests/g2_corner_fill_probe.py`) measured the built-in
`Surface::Filling` over the corner model at `BoundaryOrder` 0/1/2, but only
read a **normal gap** (0.164-0.483 deg at order 2).  A normal gap cannot
establish G2: the calibration (`Tests/continuity_calibration.py`) shows
`g1_deg` is blind to a 4 /mm curvature jump.  This module re-runs the SAME
fill feeds and reads the calibrated curvature metrics instead -- `k_gap` and
`twist_gap`, via the exact control-net instrument (the fill's OCCT
`BSplineSurface` reconstructed as a `silk_nurbs.NurbsSurface`).

The whole point of the order knob is the second-order boundary condition, so
the comparison of interest is order 1 vs order 2 in `k_gap`.  If order 2 does
not beat order 1 in `k_gap`, the knob is not doing what its name says.

MEASUREMENT ONLY, on the throwaway corner model (`Tests/corner_model.py`) in a
scratch document that is closed again.  MANUAL-ONLY (not `test_*.py`); the
suite asserts this file imports, exposes `main`, and carries `MANUAL`.

Run (live GUI over XML-RPC, or in a GUI FreeCAD):

    import Tests.g2_corner_fill_continuity as m; m.main()
    import Tests.g2_corner_fill_continuity as m; m.cross_check()   # oracle cross-check
    import Tests.g2_corner_fill_continuity as m; m.calibrate()     # vs measure_edges
"""

import math

import FreeCAD
import Part
from FreeCAD import Base

from Tests import corner_model
from Tests import g2_corner_fill_probe as P
import Tests.silk_nurbs as SN
import Tests.continuity_analytic as CA
import Tests.g2_oracle as G

MANUAL = True

FEEDS = ("strip", "raw")
ORDERS = (0, 1, 2)

# a boundary point is "on" the fill when the parameter solve lands within this
# (the probe's own sound-fill boundary residual is <= 9e-3 mm)
ON_FILL_TOL = 1e-2


def nurbs_from_bspline(bs):
    """A `silk_nurbs.NurbsSurface` carrying the exact OCCT BSpline net."""
    nu, nv = bs.NbUPoles, bs.NbVPoles
    poles = [[bs.getPole(i + 1, j + 1) for j in range(nv)] for i in range(nu)]
    weights = [[bs.getWeight(i + 1, j + 1) for j in range(nv)] for i in range(nu)]
    return SN.NurbsSurface(poles, weights, list(bs.UKnotSequence),
                           list(bs.VKnotSequence), bs.UDegree, bs.VDegree)


def _newton_uv(surf, point, u, v, prange, iters=80):
    """Damped Newton for `point` on `surf`, seeded at (u, v)."""
    u0, u1, v0, v1 = prange
    for _ in range(iters):
        r = surf.value(u, v) - point
        if r.Length < 1e-11:
            break
        h = 1e-6
        su = (surf.value(u + h, v) - surf.value(u - h, v)) / (2 * h)
        sv = (surf.value(u, v + h) - surf.value(u, v - h)) / (2 * h)
        a, b, c = su.dot(su), su.dot(sv), sv.dot(sv)
        d, e = su.dot(r), sv.dot(r)
        det = a * c - b * b
        if abs(det) < 1e-18:
            break
        u -= (c * d - b * e) / det
        v -= (a * e - b * d) / det
        u = min(u1, max(u0, u))
        v = min(v1, max(v0, v))
    return u, v, (surf.value(u, v) - point).Length


def _solve_seam(surf_bs, curve, n, grid=40):
    """(seam callable t->(u,v), residuals) for `curve` lying on `surf_bs`.

    Each station is seeded from the previous one, so the (u, v) correspondence
    follows the boundary curve instead of jumping between parameter branches
    (a coarse global grid solve can land on a different branch as t varies,
    which corrupts the seam derivatives).
    """
    prange = G.domain(surf_bs)
    u, v, _ = P.solve_uv(surf_bs, curve.value(0.0), prange, grid=grid)
    sols = []
    for k in range(n):
        t = k / (n - 1.0)
        u, v, res = _newton_uv(surf_bs, curve.value(t), u, v, prange)
        sols.append((t, u, v, res))

    def f(t):
        # seed the solve for arbitrary t from the nearest stored station
        _t, u0, v0, _res = min(sols, key=lambda s: abs(s[0] - t))
        uu, vv, _r = _newton_uv(surf_bs, curve.value(t), u0, v0, prange)
        return uu, vv

    return f, [s[3] for s in sols]


def _unit(v):
    L = v.Length
    if L < 1e-15:
        return Base.Vector(0.0, 0.0, 0.0)
    return Base.Vector(v.x / L, v.y / L, v.z / L)


def _normal(surf, u, v):
    _P, Pu, Pv, *_ = surf.ders(u, v, order=1)
    return _unit(Pu.cross(Pv))


def _kappa_oblique(surf, u, v, d):
    """Exact normal curvature of `surf` at (u, v) in unit direction `d`.

    II(d, d) with the second fundamental form read from the exact control net:
    d = a*Pu + b*Pv, then kappa = e a^2 + 2 f a b + g b^2 (e=Puu.n, f=Puv.n,
    g=Pvv.n).  Works for an oblique seam, which a trimmed fill has.
    """
    _P, Pu, Pv, Puu, Puv, Pvv = surf.ders(u, v, order=2)
    n = _unit(Pu.cross(Pv))
    puu, pvv, puv = Pu.dot(Pu), Pv.dot(Pv), Pu.dot(Pv)
    det = puu * pvv - puv * puv
    if abs(det) < 1e-18:
        return 0.0
    du = d.dot(Pu)
    dv = d.dot(Pv)
    a = (du * pvv - dv * puv) / det
    b = (puu * dv - puv * du) / det
    e = Puu.dot(n)
    f = Puv.dot(n)
    g = Pvv.dot(n)
    return e * a * a + 2.0 * f * a * b + g * b * b


def measure_oblique(surf_a, seam_a, surf_b, seam_b, curve, n=41):
    """Exact c0 / g1_deg / k_gap / twist_gap across an oblique seam.

    `curve` is the boundary cubic (the shared seam), so its tangent gives the
    along direction even when the seam is not a constant-parameter line.
    """
    out = {"c0": 0.0, "g1_deg": 0.0, "k_gap": 0.0, "twist_gap": 0.0,
           "samples": []}
    dt = 1e-4
    for k in range(n):
        t = k / (n - 1.0)
        ua, va = seam_a(t)
        ub, vb = seam_b(t)
        t0t, t1t = max(0.0, t - 1e-6), min(1.0, t + 1e-6)
        tanvec = curve.value(t1t) - curve.value(t0t)
        speed = tanvec.Length / (t1t - t0t) if t1t > t0t else 0.0
        ta = _unit(tanvec)
        na = _normal(surf_a, ua, va)
        nb = _normal(surf_b, ub, vb)
        if na.dot(nb) < 0.0:
            nb = -1.0 * nb
        pa = surf_a.ders(ua, va, order=0)[0]
        pb = surf_b.ders(ub, vb, order=0)[0]
        d = _unit(na.cross(ta))
        ka = _kappa_oblique(surf_a, ua, va, d)
        kb = _kappa_oblique(surf_b, ub, vb, d)
        # dN/ds along the seam (finite difference on the analytic normals);
        # the b-side normals are carried on the a-side's orientation.
        t0, t1 = max(0.0, t - dt), min(1.0, t + dt)
        ua0, va0 = seam_a(t0)
        ua1, va1 = seam_a(t1)
        ub0, vb0 = seam_b(t0)
        ub1, vb1 = seam_b(t1)
        sign = 1.0 if na.dot(nb) >= 0.0 else -1.0
        n0a = _normal(surf_a, ua0, va0)
        n1a = _normal(surf_a, ua1, va1)
        n0b = _normal(surf_b, ub0, vb0) * sign
        n1b = _normal(surf_b, ub1, vb1) * sign
        if n0a.dot(n1a) < 0.0:
            n1a = -1.0 * n1a
        if n0b.dot(n1b) < 0.0:
            n1b = -1.0 * n1b
        dtm = (t1 - t0)
        dna = (n1a - n0a) / dtm if dtm > 0 else Base.Vector(0, 0, 0)
        dnb_ = (n1b - n0b) / dtm if dtm > 0 else Base.Vector(0, 0, 0)
        tau_a = -dna.dot(d) / speed if speed > 1e-12 else 0.0
        tau_b = -dnb_.dot(d) / speed if speed > 1e-12 else 0.0

        c0 = (pa - pb).Length
        g1 = math.degrees(math.acos(max(-1.0, min(1.0, na.dot(nb)))))
        out["c0"] = max(out["c0"], c0)
        out["g1_deg"] = max(out["g1_deg"], g1)
        out["k_gap"] = max(out["k_gap"], abs(ka - kb))
        out["twist_gap"] = max(out["twist_gap"], abs(tau_a - tau_b))
        out["samples"].append({"t": t, "c0": c0, "g1_deg": g1,
                               "k_a": ka, "k_b": kb,
                               "k_gap": abs(ka - kb),
                               "twist_gap": abs(tau_a - tau_b)})
    return out


def measure_fill(fill, rows, ref_surfaces, n=41, grid=40):
    """Continuity of a built fill against each strip's reference surface.

    `rows` are the boundary cubic pole rows; `ref_surfaces` the OCCT surfaces
    the fill is supposed to continue.  Returns per-edge reports.
    """
    shape = fill.Shape
    report = {"valid": bool(shape.Faces) and shape.isValid(),
              "boundary_residual": None, "per_edge": [], "k_gap": 0.0,
              "twist_gap": 0.0}
    if not shape.Faces:
        return report
    fill_bs = shape.Faces[0].Surface
    try:
        fill_nurbs = nurbs_from_bspline(fill_bs)
    except Exception as exc:                      # not a reconstructible BSpline
        report["error"] = "fill surface not a BSpline net: %r" % (exc,)
        return report

    worst_res = 0.0
    for row, ref_bs in zip(rows, ref_surfaces):
        curve = Part.BSplineCurve()
        curve.buildFromPoles(row)
        seam_fill, res_f = _solve_seam(fill_bs, curve, n, grid=grid)
        seam_ref, res_r = _solve_seam(ref_bs, curve, n, grid=grid)
        edge_res = max(max(res_f), max(res_r))
        worst_res = max(worst_res, edge_res)
        entry = {"boundary_residual": edge_res, "c0": edge_res}
        if edge_res > ON_FILL_TOL:
            entry["k_gap"] = None
            entry["twist_gap"] = None
            entry["note"] = "fill does not reach this boundary"
            report["per_edge"].append(entry)
            continue
        ref_nurbs = nurbs_from_bspline(ref_bs)
        m = measure_oblique(ref_nurbs, seam_ref, fill_nurbs, seam_fill,
                            curve, n=n)
        entry.update({"k_gap": m["k_gap"], "twist_gap": m["twist_gap"],
                      "g1_deg": m["g1_deg"], "c0": m["c0"]})
        report["k_gap"] = max(report["k_gap"], m["k_gap"])
        report["twist_gap"] = max(report["twist_gap"], m["twist_gap"])
        report["per_edge"].append(entry)
    report["boundary_residual"] = worst_res
    return report


def run(doc, feed, order, n=21, grid=40):
    if feed == "strip":
        data = P.build_strip_fill(doc, order)
        rep = measure_fill(data["fill"], data["row"], data["surface"],
                           n=n, grid=grid)
    else:
        data = P.build_raw_patch_fill(doc, order)
        rows, refs = [], []
        for i, e in enumerate(data["edge"]):
            pts = [e.valueAt(e.FirstParameter
                             + (e.LastParameter - e.FirstParameter) * k / 10.0)
                   for k in range(11)]
            rows.append(pts)
            refs.append(doc.getObject(data["patch"][i]).Proxy._base_surface)
        rep = _measure_fill_curves(data["fill"], rows, refs, n=n, grid=grid)
    rep["feed"] = feed
    rep["order"] = order
    return rep


def _measure_fill_curves(fill, point_lists, ref_surfaces, n=21, grid=40):
    """Like `measure_fill` but the seam is supplied as sampled points (raw)."""
    shape = fill.Shape
    report = {"valid": bool(shape.Faces) and shape.isValid(),
              "boundary_residual": None, "per_edge": [], "k_gap": None,
              "twist_gap": None}
    if not shape.Faces:
        return report
    fill_bs = shape.Faces[0].Surface
    worst_res = 0.0
    for pts, ref_bs in zip(point_lists, ref_surfaces):
        prange = G.domain(fill_bs)
        sol = [P.solve_uv(fill_bs, p, prange, grid=grid) for p in pts]
        edge_res = max(s[2] for s in sol)
        worst_res = max(worst_res, edge_res)
        entry = {"boundary_residual": edge_res}
        if edge_res > ON_FILL_TOL:
            entry["k_gap"] = None
            entry["twist_gap"] = None
            entry["note"] = "fill does not reach this boundary"
            report["per_edge"].append(entry)
            continue
        entry["k_gap"] = None
        entry["twist_gap"] = None
        entry["note"] = ("raw feed: octagon boundary, curvature not measured "
                         "per edge")
        report["per_edge"].append(entry)
    report["boundary_residual"] = worst_res
    return report


def _across_axis(nurbs, seam):
    """The parameter direction ('u'/'v') that leaves the seam, at t = 0.5."""
    u, v = seam(0.5)
    _P, Pu, Pv, *_ = nurbs.ders(u, v, order=1)
    t0, t1 = 0.5 - 1e-4, 0.5 + 1e-4
    u0, v0 = seam(t0)
    u1, v1 = seam(t1)
    ta = _unit(nurbs.ders(u1, v1, order=0)[0] - nurbs.ders(u0, v0, order=0)[0])
    pu = Pu - ta * Pu.dot(ta)
    pv = Pv - ta * Pv.dot(ta)
    return "u" if pu.Length >= pv.Length else "v"


def cross_check(n=41, grid=40):
    """`measure_oblique` vs the sampled `g2_oracle` on the strip-fill seams.

    Two independent instruments on the SAME seams: the exact control-net
    second fundamental form (`measure_oblique`) and the finite-difference
    sampled oracle (`g2_oracle.measure_seam`).  `measure_oblique` is the
    instrument used for the order 1 vs order 2 claim; this is its
    independent cross-check.  (It is exact on a constant-parameter seam --
    `tests`/`Tests/continuity_analytic.measure_edges` agrees to all printed
    digits there -- and the sampled oracle fixes a constant across axis, so
    the two are expected to agree on `g1_deg` and on the `k_gap` scale.)
    """
    doc = _scratch_document()
    out = []
    try:
        for order in ORDERS:
            before = set(o.Name for o in doc.Objects)
            try:
                data = P.build_strip_fill(doc, order)
                fill_bs = data["fill"].Shape.Faces[0].Surface
                fill_n = nurbs_from_bspline(fill_bs)
                for row, ref_bs in zip(data["row"], data["surface"]):
                    curve = Part.BSplineCurve()
                    curve.buildFromPoles(row)
                    ref_n = nurbs_from_bspline(ref_bs)
                    sf, rf = _solve_seam(fill_bs, curve, n, grid=grid)
                    sr, rr = _solve_seam(ref_bs, curve, n, grid=grid)
                    obl = measure_oblique(ref_n, sr, fill_n, sf, curve, n=n)
                    smp = G.measure_seam(ref_bs, sr, _across_axis(ref_n, sr),
                                         fill_bs, sf, _across_axis(fill_n, sf),
                                         n=n)
                    out.append({
                        "order": order,
                        "boundary_residual": max(max(rf), max(rr)),
                        "oblique": {k: obl[k] for k in
                                    ("c0", "g1_deg", "k_gap", "twist_gap")},
                        "sampled": {k: smp[k] for k in
                                    ("c0", "g1_deg", "k_gap", "twist_gap")}})
            finally:
                for o in list(doc.Objects):
                    if o.Name not in before:
                        try:
                            doc.removeObject(o.Name)
                        except Exception:
                            pass
                doc.recompute()
    finally:
        FreeCAD.closeDocument(doc.Name)
    return out


def calibrate(n=41):
    """`measure_oblique` vs `continuity_analytic.measure_edges` on a demo seam.

    The demo's constant-parameter corner <-> blend seam (`CubicSurface_66`
    v0 <-> `CubicSurface_64010` v1) is a known-answer cross-check: the oblique
    macro must reproduce the exact control-net evaluator to all printed
    digits there.  The demo is opened read-only and never saved.
    """
    import Tests.g2_edge_blend_probe as EBP
    doc = EBP.get_doc()
    an_c = SN.NurbsSurface.from_object(doc.getObject("CubicSurface_66"))
    an_b = SN.NurbsSurface.from_object(doc.getObject("CubicSurface_64010"))
    m = CA.match_boundaries(an_c, an_b)[0]
    bnd = an_c.boundary(m["edge_a"])
    if m["reverse_a"]:
        bnd = list(reversed(bnd))
    curve = Part.BSplineCurve()
    curve.buildFromPoles([p for p, _w in bnd])
    sa, _la, _aa = CA.edge_seam(m["edge_a"], m["reverse_a"])
    sb, _lb, _ab = CA.edge_seam(m["edge_b"], m["reverse_b"])
    obl = measure_oblique(an_c, sa, an_b, sb, curve, n=n)
    ca = CA.measure_edges(an_c, m["edge_a"], m["reverse_a"],
                          an_b, m["edge_b"], m["reverse_b"], n=n)
    keys = ("c0", "g1_deg", "k_gap", "twist_gap")
    return {"edge_a": m["edge_a"], "edge_b": m["edge_b"],
            "oblique": {k: obl[k] for k in keys},
            "analytic": {k: ca[k] for k in keys}}


def _scratch_document():
    name = "_g2_corner_fill_continuity"
    if name in FreeCAD.listDocuments():
        FreeCAD.closeDocument(name)
    doc = FreeCAD.newDocument(name)
    corner_model.build_corner_model_with_blend(doc)
    return doc


def _probe(doc, feed, order, n, grid):
    before = set(o.Name for o in doc.Objects)
    try:
        return run(doc, feed, order, n=n, grid=grid)
    finally:
        for o in list(doc.Objects):
            if o.Name not in before:
                try:
                    doc.removeObject(o.Name)
                except Exception:
                    pass
        doc.recompute()


def main(n=21, grid=40, json_path=None):
    doc = _scratch_document()
    results = []
    try:
        for feed in FEEDS:
            for order in ORDERS:
                try:
                    results.append(_probe(doc, feed, order, n, grid))
                except Exception as exc:
                    results.append({"feed": feed, "order": order,
                                    "error": repr(exc)})
    finally:
        FreeCAD.closeDocument(doc.Name)
    print("feed   order  valid  boundary_residual  k_gap      twist_gap  g1_deg")
    for r in results:
        if "error" in r:
            print("%-6s %-6d  ERROR  %s" % (r["feed"], r["order"], r["error"]))
            continue
        kg = r.get("k_gap")
        tg = r.get("twist_gap")
        g1 = max((e.get("g1_deg", 0.0) or 0.0 for e in r["per_edge"]),
                 default=0.0)
        print("%-6s %-6d  %-5s  %-17s  %-9s  %-9s  %6.4f"
              % (r["feed"], r["order"], r["valid"],
                 ("%.3e mm" % r["boundary_residual"]
                  if r["boundary_residual"] is not None else "-"),
                 ("%.3e" % kg) if kg is not None else "-",
                 ("%.3e" % tg) if tg is not None else "-", g1))
    if json_path:
        import json
        with open(json_path, "w") as f:
            json.dump(results, f, indent=1, default=str)
        print("raw output -> %s" % json_path)
    return results


if __name__ == "__main__":
    main()

