"""The TWO-PATCH corner, measured (#128).

WHAT THIS PINS, AND WHY IT IS A MEASUREMENT MODULE

The rolled corner is two surfaces: the big **quad** (the 66 over the ring's
four members) and, beside it, the **tri** (the triangular patch), plus the
five preserved pieces -- stated once in
`docs/adr/0006-rolled-corner-is-two-patches.md`.  This module measures that
arrangement, and it measures it as built:

  * the patch that carries the tri is cut at TWO positions per axis, the
    SETBACK and the LEADER (`SilkPatch.ULeader1/2`, `VLeader1/2`), so the
    tri's cell is the region BETWEEN them and the TWO strips that share that
    patch end their junction rows at TWO DIFFERENT points -- the member's real
    row runs between them (`SilkMachinery.ring_corner_gap` states the rule);
  * every other patch of the ring keeps ONE cut per axis end, so its own two
    strips still meet at one point, and the third blend is not cut at all;
  * the member's row is read as the ring row (not its collapsed row), which
    is `SilkCorner._member_row_order` answering REAL-ROW-FIRST for a patch
    that carries a real second cut.

Before #128 the corner stage wrote the leader INTO THE BAND EDGE on both
patches of each rolled seam, so the setback rode along with it, the member's
cell WAS the corner cell, and the 66 pinched at the junction.  That corner is
still reachable -- `construction="shipped"` -- and it is byte-identical
(0.00e+00 on poles and weights), which the fallback test below re-measures.

THE INSTRUMENT AND ITS CONTROLS.  Every number here is read off the BUILT
corner (the nets the objects store and the shapes they hold), never off a
parameter:

  * coincident pole pairs -- the census that says whether a side of the 6x6
    has collapsed;
  * normal-field flips at n = 39/81/150, on the Part surface AND on the exact
    control net (two readers of the same field), WITHOUT
    `smooth_degenerate_cap` -- the two-patch corner has no collapsed side, so
    the smoothing is a no-op and cannot be doing the work;
  * the CALIBRATION for that reading is in the same test: the SHIPPED corner's
    raw assembly (upstream's own extrapolation) FOLDS, and its built
    (smoothed) net does not -- a known-fold and a known-good control at the
    same resolution;
  * the tri-interior-to-quad distance, as a fraction of the corner's own
    extent, beside the maintainer's own reading (16 %..62 %) -- REPORTED, not
    used as a pass line (see row (d): its minimum is below his floor);
  * the property that actually separates the two surfaces: **no common area**
    and an interior strictly outside the quad, with a known-answer control
    (the quad against itself) that proves the instrument can see an overlap;
  * the seam `k_gap`, exact and sampled, with the published floor beside it
    (`Tests/continuity_calibration.error_floor`), and the C0 at the cut;
  * the settling count and the per-pass cost (#125).

MEASURED (this build, cube-corner fixture, leader 0.25, setback 0.1)

    (a) ring closes             ring_corner_gap: PatchA ('U', 0.1, 0.25) --
                                THE MEMBER PATCH, where two different ring
                                corners are correct (#127); PatchB/PatchC None.
                                corner_inputs assembles.
    (b) coincident pairs        6x6 0/630, member 15/276 (the member keeps its
                                own collapsed row, inside the loop)
    (c) normal-field flips      0/0/0 without the smoothing; no collapsed side
    (d) tri interior -> quad    0.0187 .. 0.1337 mm = 7.5 %..53.5 % of the
                                0.25 mm extent (his: 16..62 %; the minimum is
                                BELOW his floor and is reported as such).
                                THE BAR: no common area (0.000000 mm^2, against
                                the quad-against-itself control's 0.046713)
                                and an interior strictly outside the quad
    (e) seam k_gap              exact 7.8e-15 .. 1.6e-14 /mm, sampled
                                0.0067 .. 0.0093 /mm; the cut's C0
                                1.4e-17 .. 3.2e-17 mm
    (f) settles                 touched [], three passes 0.0001 s each, the
                                poles move 0.000e+00 mm

SECOND FIXTURE (the 2x2 corner, `Tests/corner_model.py`): a FOUR-valent
junction, so the rolling construction refuses it BY NAME (it needs a third,
uncut seam and a triangular remainder, and a 4-valent ring has neither), the
corner stage builds the shipped construction and says so, and the 4-valent
corner is otherwise exactly what it was: 36 poles, 0 coincident pairs, no
member.
"""

# --- manual tier ------------------------------------------------------
# This module is a measurement sweep over end-to-end builds, so it is NOT in
# the default (fast) tier.  `Tests/test_manual_tier.py` asserts it stays
# importable and named.
MANUAL = True

import FreeCAD

import SilkChecks
import SilkCorner as SC
import SilkMachinery as SM
import Tests.silk_nurbs as SN
from SilkWorkflowOps import create_corner_blend
from Tests import cube_corner_model as ccm
from Tests.g2_corner_roll_measure import _part_surface
from Tests.prototype_reference_corner import _coins, _interior_distances
from Tests.rolling_corner_66_visual import cut_residual, seam_gaps

STRIP_NAMES = ("B_AB", "B_BC", "B_CA")
PATCH_NAMES = ("PatchA", "PatchB", "PatchC")
LEADER = 0.25
SETBACK = 0.1

# The maintainer's own reading of the tri-to-quad distance, as a fraction of
# the corner's extent (`docs/research/silk-rolling-corner-66.md`, measured on
# his finished corner: 8.0..31.0 mm of a 50 mm diagonal).
HIS_TRI_QUAD_PERCENT = (16.0, 62.0)


def _fixture(doc):
    ccm.build_cube_corner_model(doc)
    doc.recompute()
    doc.recompute()
    return [doc.getObject(n) for n in STRIP_NAMES]


def _member_of(doc):
    for o in doc.Objects:
        if getattr(o, "object_type", "") == "RollingMemberFace":
            return o
    return None


def _two_patch(doc, **kw):
    """The cube corner + the corner stage's DEFAULT construction (#128)."""
    strips = _fixture(doc)
    corner = create_corner_blend(*strips, name="TwoPatch", **kw)
    doc.recompute()
    return strips, corner, _member_of(doc)


def _exact_flips(poles, weights, n):
    """Normal-field flips of the EXACT control net (the second reader)."""
    net = SN.NurbsSurface.from_flat(list(poles), list(weights or [1.0] * 36),
                                    6, 6, SN.KNOTS_6, SN.KNOTS_6)
    ns = []
    for i in range(n):
        for j in range(n):
            nrm = net.normal((i + 0.5) / n, (j + 0.5) / n)
            ns.append(None if nrm.Length < 1e-12 else nrm)
    out = []
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
                    out.append((round((i + 0.5) / n, 4),
                                round((j + 0.5) / n, 4)))
        # the sweep is reported as a count, never as a label
    return out


def _flip_readings(poles, weights):
    part = _part_surface(list(poles), list(weights or [1.0] * 36), 6)
    out = {}
    for n in (39, 81, 150):
        part_flips, any_normal = SilkChecks._normal_field_flips(part, n=n)
        out[n] = (len(part_flips), len(_exact_flips(poles, weights, n)),
                  any_normal)
    return out


def test_the_ring_closes_with_the_cut_on_the_member_patch_only(doc):
    """(a) THE RING LOOP, read per patch, and the assembly that follows it.

    `ring_corner_gap` states the rule: a ring pair's shared corner is ONE
    point only when the band edge and the along start (the leader cut) are
    the same number at each end -- so a patch carrying two cuts reads OPEN.
    That reading is CORRECT on the member patch and nothing else: it is the
    one patch where two ring pairs meet, and its two ring corners are the
    two ends of the member's own row (#127).  What has to hold is that the
    ring ASSEMBLES, which is `corner_inputs`' answer.
    """
    errors, checks = [], []
    strips, corner, member = _two_patch(doc)
    if corner is None or not corner.Poles:
        return {"pass": False,
                "errors": ["the default (rolling) corner did not build"],
                "checks": checks}
    built, _note = SC.corner_construction(corner)
    checks.append("the corner the stage built: %s (%s construction)"
                  % (corner.Name, built))
    if built != "rolling":
        errors.append("the default construction is %r, not the rolling one"
                      % (built,))
    gaps = {}
    for name in PATCH_NAMES:
        p = doc.getObject(name)
        gaps[name] = SM.ring_corner_gap(p)
        checks.append("%s: ring_corner_gap %r" % (name, gaps[name]))
    if gaps["PatchA"] is None:
        errors.append("the member patch reads CLOSED -- it is the one patch "
                      "that must carry two ring corners")
    for name in ("PatchB", "PatchC"):
        if gaps[name] is not None:
            errors.append("%s carries a real second cut (%r): only the member "
                          "patch may, or its ring pair stops meeting"
                          % (name, (gaps[name],)))
    grids, cells, why = SC.corner_inputs(strips)
    checks.append("corner_inputs assembles: %r (%s grids, member at %r)"
                  % (why is None, len(grids or []), _member_pin(strips)))
    if grids is None:
        errors.append("the ring does not assemble: %s" % why)
    # the corner the object built is the SAME net the derivation gives
    if grids is not None:
        p36, _w36, why_g = SM.corner_grid(grids, SC.CORNER_TOL)
        if p36 is None:
            errors.append("corner_grid refused the ring: %s" % why_g)
        else:
            dev = max((a - b).Length for a, b in zip(p36, list(corner.Poles)))
            checks.append("the built corner vs the derivation: %.3e mm" % dev)
            if dev > 1e-9:
                errors.append("the built 6x6 is not the derivation's net "
                              "(%.3e mm)" % dev)
    # the member's own row is a REAL row: its collapsed row is not on the loop
    if member is not None:
        rows = [list(member.Poles)[r * 6:(r + 1) * 6] for r in range(4)]
        collapsed = [r for r, row in enumerate(rows)
                     if all((row[k] - row[0]).Length <= 1e-9
                            for k in range(1, 6))]
        checks.append("the member's collapsed row(s): %r of 4 (its ring row "
                      "is the other one)" % (collapsed,))
        if collapsed == []:
            errors.append("the member has no collapsed row at all -- it is "
                          "not the triangular member")
    return {"pass": not errors, "errors": errors, "checks": checks}


def _member_pin(strips):
    try:
        pin, _why = SC.corner_member_pin(strips)
    except Exception:
        return None
    return None if pin is None else (pin[0].Name, pin[1])


def test_the_two_patch_corner_has_no_coincident_poles(doc):
    """(b) THE DEGENERACY CENSUS: 0 of 630 pairs on the 6x6.

    The shipped corner collapses one whole side of the 6x6 (six poles on one
    point, 15 coincident pairs on a net whose poles are otherwise exact).
    The two-patch corner does not: its 6x6 has 36 DISTINCT poles, and the
    member -- the triangular net -- keeps its own 15, inside the loop.
    """
    errors, checks = [], []
    strips, corner, member = _two_patch(doc)
    if corner is None or not corner.Poles:
        return {"pass": False, "errors": ["no corner built"], "checks": checks}
    quad_coins = _coins(list(corner.Poles))
    checks.append("the 6x6: %d poles, %d/630 coincident pairs, collapsed side "
                  "%r" % (len(corner.Poles), quad_coins,
                          SM._collapsed_side(list(corner.Poles),
                                             SC.CORNER_TOL)))
    if quad_coins:
        errors.append("the 6x6 carries %d coincident pole pairs -- a side of "
                      "the corner has collapsed" % quad_coins)
    if SM._collapsed_side(list(corner.Poles), SC.CORNER_TOL) is not None:
        errors.append("the 6x6 still has a collapsed side")
    if member is None:
        errors.append("the corner built no triangular member")
    else:
        member_coins = _coins(list(member.Poles))
        checks.append("the member: %d poles, %d/276 coincident pairs (its own "
                      "collapsed row)" % (len(member.Poles), member_coins))
        if member_coins != 15:
            errors.append("the member does not keep exactly its 15 collapsed "
                          "pairs (%d)" % member_coins)
    return {"pass": not errors, "errors": errors, "checks": checks}


def test_the_two_patch_corner_is_fold_free_without_the_smoothing(doc):
    """(c) THE FLIP READING, with the calibration that makes it readable.

    The two-patch 6x6 has no collapsed side, so
    `SilkMachinery.smooth_degenerate_cap` returns it unchanged -- the reading
    below is the RAW assembly, which is the only way it can say anything.

    The controls, in the same test at the same resolutions:
      * a KNOWN-FOLD -- the shipped corner's raw assembly, upstream's own
        extrapolation past the collapsed side;
      * a KNOWN-GOOD -- the shipped corner as BUILT, where the smoothing
        re-solves the two member-side interior rows.
    """
    errors, checks = [], []
    strips, corner, member = _two_patch(doc)
    if corner is None or not corner.Poles:
        return {"pass": False, "errors": ["no corner built"], "checks": checks}
    raw_p = list(corner.Poles)
    raw_w = list(corner.Weights) or [1.0] * 36
    smoothed, _sm_w = SM.smooth_degenerate_cap(raw_p, raw_w, SC.CORNER_TOL)
    moved = max((a - b).Length for a, b in zip(raw_p, smoothed))
    checks.append("smooth_degenerate_cap on the two-patch 6x6 moves the poles "
                  "%.3e mm (a no-op: there is no collapsed side)" % moved)
    if moved != 0.0:
        errors.append("the smoothing is not a no-op on this corner (%.3e mm) "
                      "-- the reading below would not be the raw assembly"
                      % moved)
    readings = _flip_readings(raw_p, raw_w)
    for n, (part_flips, net_flips, any_normal) in readings.items():
        checks.append("n=%d: Part-surface flips %d, exact-net flips %d (a "
                      "valid normal exists: %s)"
                      % (n, part_flips, net_flips, any_normal))
        if not any_normal:
            errors.append("n=%d: no valid normal on the corner surface" % n)
    if any(pf or nf for pf, nf, _a in readings.values()):
        errors.append("the two-patch corner folds: %s"
                      % {n: (pf, nf) for n, (pf, nf, _a) in readings.items()})

    # the CALIBRATION: the shipped corner, raw (fold) and built (smoothed)
    sdoc = FreeCAD.newDocument("TwoPatchCalibration")
    try:
        FreeCAD.setActiveDocument(sdoc.Name)
        sstrips = _fixture(sdoc)
        shipped = create_corner_blend(*sstrips, name="Shipped",
                                     construction="shipped")
        sdoc.recompute()
        sgrids, _cells, why = SC.corner_inputs(sstrips)
        if sgrids is None:
            errors.append("the shipped ring does not assemble: %s" % why)
        else:
            pairs = [SM.pair_common(sgrids[i][0], sgrids[(i + 1) % 4][0],
                                    SC.CORNER_TOL)[0] for i in range(4)]
            subs = [SM.subgrid33_2grid64(sgrids[i][0], sgrids[i][1],
                                         sgrids[(i + 1) % 4][0],
                                         sgrids[(i + 1) % 4][1],
                                         SC.CORNER_TOL)[:2] for i in range(4)]
            raw66, raw66_w = SM.control_grid66_4sub(subs)
            known_fold = _flip_readings(raw66, raw66_w)
            known_good = _flip_readings(list(shipped.Poles),
                                        list(shipped.Weights))
            checks.append("calibration, shipped RAW (upstream's "
                          "extrapolation, collapse %r): %s"
                          % (SM._collapsed_side(raw66, SC.CORNER_TOL),
                             {n: (pf, nf)
                              for n, (pf, nf, _a) in known_fold.items()}))
            checks.append("calibration, shipped BUILT (smoothed): %s"
                          % {n: (pf, nf)
                             for n, (pf, nf, _a) in known_good.items()})
            if not any(pf or nf for pf, nf, _a in known_fold.values()):
                errors.append("the KNOWN-FOLD control does not fold -- the "
                              "instrument is not reading this construction")
            if any(pf or nf for pf, nf, _a in known_good.values()):
                errors.append("the KNOWN-GOOD control folds -- the instrument "
                              "or the smoothing is broken")
            checks.append("shipped raw pair patterns: %r" % (pairs,))
    finally:
        FreeCAD.closeDocument(sdoc.Name)
        FreeCAD.setActiveDocument(doc.Name)
    return {"pass": not errors, "errors": errors, "checks": checks}


def test_the_tri_is_beside_the_quad_not_inside_it(doc):
    """(d) THE TWO SURFACES ARE ADJACENT, NOT OVERLAPPING -- the property
    that makes them two patches, with a known-answer control.

    THE BAR IS NON-OVERLAP, and it is two-sided: the two faces must have no
    common area, and the tri's interior must lie strictly OUTSIDE the quad.
    A positive control runs in the same test -- the quad against ITSELF, whose
    common area is the quad's whole face -- so the reading is not a zero that
    an instrument that cannot see an overlap would also give.

    THE PERCENTAGE IS A READING, NOT THE BAR.  The maintainer's file reads
    8.0..31.0 mm on a 50 mm diagonal (16 %..62 %); the shipped fallback reads
    0.1 %..10 % because its 66 sweeps over the member's cell.  This corner
    reads 7.5 %..53.5 %, i.e. its MINIMUM is BELOW his floor -- so the
    percentage cannot be the pass line (an earlier version of this row
    compared only the maximum, and passed while reading 7.5 %).  What it
    cannot be used for is hidden: it is printed with the floor beside it.
    """
    errors, checks = [], []
    strips, corner, member = _two_patch(doc)
    if corner is None or not corner.Poles or member is None \
            or not member.Shape.Faces:
        return {"pass": False,
                "errors": ["the two-patch corner or its tri did not build"],
                "checks": checks}
    ds = _interior_distances(member.Shape, corner.Shape, grid=8)
    bb = corner.Shape.BoundBox
    extent = max(bb.XLength, bb.YLength, bb.ZLength) or 1.0
    lo, hi = min(ds) / extent * 100.0, max(ds) / extent * 100.0
    checks.append("tri interior -> quad: %.5f .. %.5f mm = %.1f %%..%.1f %% of "
                  "the corner's %.4f mm extent (his: %.0f..%.0f %%; our "
                  "minimum is %s his floor -- a reading, not the bar)"
                  % (min(ds), max(ds), lo, hi, extent,
                     HIS_TRI_QUAD_PERCENT[0], HIS_TRI_QUAD_PERCENT[1],
                     "BELOW" if lo < HIS_TRI_QUAD_PERCENT[0] else "inside"))
    checks.append("areas: quad %.6f mm^2, tri %.6f mm^2"
                  % (corner.Shape.Area, member.Shape.Area))
    # THE BAR (1): the two surfaces share no area.  The control is the quad
    # against ITSELF: same code, same tolerance, an overlap that must show.
    try:
        shared = _shared_area(corner.Shape, member.Shape)
        control = _shared_area(corner.Shape, corner.Shape)
    except Exception as exc:            # a boolean that will not run is not
        return {"pass": False,             # a pass
                "errors": ["the overlap instrument did not run: %r" % (exc,)],
                "checks": checks}
    checks.append("common area: quad & tri %.6f mm^2, control quad & quad "
                  "%.6f mm^2 (the bar: the first is 0, the second is the "
                  "quad's own area)"
                  % (shared, control))
    if control <= 0.5 * (corner.Shape.Area or 0.0):
        errors.append("the overlap instrument cannot see an overlap (the "
                      "quad against itself reads %.6f mm^2 of %.6f) -- the "
                      "reading below is vacuous"
                      % (control, corner.Shape.Area))
    if shared > 1e-9:
        errors.append("the quad and the tri share %.6f mm^2 -- the 66 sweeps "
                      "over the tri's cell" % shared)
    # THE BAR (2): the tri's interior is strictly outside the quad
    if min(ds) <= 1e-9:
        errors.append("the tri's interior lies ON the quad (%.3e mm)"
                      % min(ds))
    return {"pass": not errors, "errors": errors, "checks": checks}


def _shared_area(a, b):
    """The area `a` and `b` have in common, in mm^2."""
    common = a.common(b)
    if common is None:
        return 0.0
    return sum(f.Area for f in common.Faces)


def test_the_cut_is_c0_and_the_seams_read_a_k_gap(doc):
    """(e) THE SEAM NUMBERS, with the floor beside them.

    The cut is where the corner fill's boundary meets the blends' cut edges
    (C0, mm); the `k_gap` is the corner against the strip it feeds, EXACT from
    the control nets carrying the weights and SAMPLED on the Part surfaces.
    """
    errors, checks = [], []
    strips, corner, member = _two_patch(doc)
    if corner is None or not corner.Poles:
        return {"pass": False, "errors": ["no corner built"], "checks": checks}
    cuts = cut_residual(corner, strips)
    checks.append("the C0 at the cut: %s"
                  % ", ".join("%s %s %.3e mm"
                              % (c.get("strip"), c.get("edge"), c.get("c0", 0))
                              for c in cuts))
    for c in cuts:
        if c.get("c0") is None or c["c0"] > 1e-9:
            errors.append("the corner fill does not meet %s's cut edge "
                          "(%r mm)" % (c.get("strip"), c.get("c0")))
    rows = seam_gaps(corner, strips)
    for r in rows:
        checks.append("%s: k_gap exact %s /mm, sampled %s /mm (g1 exact %s, "
                      "sampled %s deg)"
                      % (r.get("strip"), _fmt(r.get("k_gap_exact")),
                         _fmt(r.get("k_gap_sampled")), _fmt(r.get("g1_exact")),
                         _fmt(r.get("g1_sampled"))))
    try:
        from Tests.continuity_calibration import error_floor
        floor = error_floor()
        checks.append("floor (Tests/continuity_calibration): k_gap %s /mm, "
                      "c0 %s mm"
                      % (_fmt(floor.get("k_gap", {}).get("analytic")),
                         _fmt(floor.get("c0", {}).get("analytic"))))
    except Exception as exc:
        checks.append("floor not read: %r" % (exc,))
    return {"pass": not errors, "errors": errors, "checks": checks}


def _fmt(x):
    if x is None:
        return "n/a"
    if isinstance(x, float):
        return "%.4g" % x
    return str(x)


def test_the_two_patch_corner_settles(doc):
    """(f) A SETTLED DOCUMENT STAYS SETTLED (#125), with the numbers.

    Nothing Touched after the build, three recompute passes that touch
    nothing, the per-pass cost, and the net's own movement across a pass.
    """
    import time
    errors, checks = [], []
    strips, corner, member = _two_patch(doc)
    if corner is None or not corner.Poles:
        return {"pass": False, "errors": ["no corner built"], "checks": checks}
    doc.recompute()
    left = [o.Name for o in doc.Objects if "Touched" in o.State]
    checks.append("after the build: %d Touched object(s) %r"
                  % (len(left), left))
    if left:
        errors.append("the document is dirty after the build: %s" % (left,))
    times = []
    poles = [tuple(p) for p in corner.Poles]
    for i in range(3):
        t0 = time.time()
        doc.recompute()
        times.append(time.time() - t0)
        left = [o.Name for o in doc.Objects if "Touched" in o.State]
        if left:
            errors.append("pass #%d re-dirtied the document: %s"
                          % (i, (left,)))
    moved = max((FreeCAD.Vector(*a) - FreeCAD.Vector(*b)).Length
                for a, b in zip(poles, [tuple(p) for p in corner.Poles]))
    checks.append("three settled passes: %s; the 6x6 poles moved %.3e mm"
                  % (", ".join("%.4f s" % t for t in times), moved))
    if moved != 0.0:
        errors.append("a settled pass MOVED the corner's poles (%.3e mm)"
                      % moved)
    return {"pass": not errors, "errors": errors, "checks": checks}


def test_the_shipped_fallback_is_still_byte_identical(doc):
    """The fallback is untouched by #128: `construction="shipped"` builds the
    66 with the spiderweb member, 0.00e+00 against the same build, and the
    patches' band edges and leader cuts are exactly what the fixture had.

    The 4-valent corner is unchanged too: it takes the shipped construction
    and says so (a rolled corner needs a third, uncut seam and a triangular
    remainder, and a 4-valent ring has neither).
    """
    errors, checks = [], []
    strips = _fixture(doc)
    first = create_corner_blend(*strips, name="Fallback1",
                               construction="shipped")
    doc.recompute()
    poles = [FreeCAD.Vector(v) for v in first.Poles]
    second = create_corner_blend(*strips, name="Fallback2",
                                construction="shipped")
    doc.recompute()
    dev = max((a - b).Length for a, b in zip(poles, list(second.Poles)))
    checks.append("the shipped corner twice: max pole deviation %.3e mm"
                  % dev)
    if dev != 0.0:
        errors.append("the shipped corner is not reproducible (%.3e mm)" % dev)
    built, _note = SC.corner_construction(first)
    checks.append("its recorded construction: %r" % (built,))
    if built != "shipped":
        errors.append("the shipped corner recorded %r" % (built,))
    for name in PATCH_NAMES:
        p = doc.getObject(name)
        if abs(p.USplit1 - SETBACK) > 1e-12 or abs(p.VSplit1 - SETBACK) > 1e-12:
            errors.append("the shipped corner moved %s's band edge" % name)
        for letter in ("U", "V"):
            if SM.leader_pair(p, letter) != (SM.NO_LEADER_1,
                                             SM.NO_LEADER_2):
                errors.append("the shipped corner wrote %s's %s leader cut"
                              % (name, letter))
    checks.append("the shipped corner wrote no band edge and no leader cut")
    return {"pass": not errors, "errors": errors, "checks": checks}


def test_the_2x2_corner_takes_the_shipped_construction_and_says_so(doc):
    """THE SECOND FIXTURE: the 2x2 corner model (`Tests/corner_model.py`).

    It is a FOUR-valent junction, and the rolling construction is 3-valent:
    it needs a third, uncut seam and a triangular remainder, and a 4-valent
    ring has neither.  Cutting any other patch is not an option either
    -- a second cut on a patch that carries a ring PAIR splits that pair's
    shared corner.  So the 2x2 corner takes the shipped construction, the
    corner stage says so, and nothing about it moved (#128 leaves the
    4-valent corner exactly as it was).
    """
    from SilkWorkflowOps import create_rolling_corner_66
    from Tests import corner_model as cm

    class _Messages:
        """Both console channels: the corner stage's NOTE on the status path
        is a message, its refusals are errors, and the check needs each."""

        def __enter__(self):
            self.messages, self.errors = [], []
            self._om = FreeCAD.Console.PrintMessage
            self._oe = FreeCAD.Console.PrintError
            FreeCAD.Console.PrintMessage = lambda m: (
                self.messages.append(str(m)), self._om(m))
            FreeCAD.Console.PrintError = lambda m: (
                self.errors.append(str(m)), self._oe(m))
            return self

        def __exit__(self, *a):
            FreeCAD.Console.PrintMessage = self._om
            FreeCAD.Console.PrintError = self._oe

    errors, checks = [], []
    _CaptureConsole = _Messages
    cm.build_corner_model(doc)
    doc.recompute()
    doc.recompute()
    strips = [doc.getObject(n) for n in ("B12", "B24", "B43", "B31")]
    with _CaptureConsole() as cap:
        corner = create_corner_blend(*strips, name="Quad4")
    doc.recompute()
    if corner is None or not corner.Poles:
        return {"pass": False,
                "errors": ["the 4-valent corner did not build: %r"
                           % ("".join(cap.errors).strip(),)],
                "checks": checks}
    built, _note = SC.corner_construction(corner)
    coins = _coins(list(corner.Poles))
    checks.append("the 2x2 corner: %s, construction %r, %d poles, %d "
                  "coincident pair(s), %d face(s); messages %r"
                  % (corner.Name, built, len(corner.Poles), coins,
                     len(corner.Shape.Faces),
                     [m.strip()[:90] for m in cap.messages]))
    if built != "shipped":
        errors.append("the 4-valent corner built the %r construction" % built)
    if coins:
        errors.append("the 4-valent corner's 6x6 carries %d coincident pairs"
                      % coins)
    if not any("3-valent construction" in m for m in cap.messages):
        errors.append("the corner stage did not say why the rolling one was "
                      "skipped: %r" % (cap.messages,))
    if _member_of(doc) is not None:
        errors.append("a 4-valent corner built a triangular member")
    with _CaptureConsole() as cap2:
        refused = create_rolling_corner_66(strips, doc.getObject("Patch44"),
                                           leader=LEADER, name="Nope")
    checks.append("create_rolling_corner_66 on the 4-valent ring: %r -- %r"
                  % (refused, "".join(cap2.errors).strip()[:150]))
    if refused is not None:
        errors.append("the rolling construction built on a 4-valent ring")
    elif "3-valent construction" not in "".join(cap2.errors):
        errors.append("the rolling corner refused a 4-valent ring without "
                      "naming the reason")
    return {"pass": not errors, "errors": errors, "checks": checks}


ALL_TESTS = [
    test_the_ring_closes_with_the_cut_on_the_member_patch_only,
    test_the_two_patch_corner_has_no_coincident_poles,
    test_the_two_patch_corner_is_fold_free_without_the_smoothing,
    test_the_tri_is_beside_the_quad_not_inside_it,
    test_the_cut_is_c0_and_the_seams_read_a_k_gap,
    test_the_two_patch_corner_settles,
    test_the_shipped_fallback_is_still_byte_identical,
    test_the_2x2_corner_takes_the_shipped_construction_and_says_so,
]
