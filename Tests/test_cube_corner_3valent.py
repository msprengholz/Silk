"""3-valent hard-corner fixture (cube corner): build contract + measurement.

`Tests/cube_corner_model.py` builds three planar patches meeting at the
shared origin exactly like a cube corner, joined by three Blend strips
built as the directed cycle A -> B -> C -> A. This module drives the
3-valent CornerBlend ops path (`create_corner_blend` with THREE strips)
on that fixture, and measures the built corner's seams.

MEASURED STATE (ticket-3valent-fix): the fixture is oracle-green (3
patches pass `check_patch` on their own `Edges`, 3 strips pass
`check_blend`), the three strips resolve as the 3-cycle ring
`corner_ring_3` requires, and the corner now BUILDS:

  * the triangular 4th ring member is fed the patch's ring CORNER CELL
    (the subgrid cell at the junction, extracted with its weights via
    `Patch.getSubgrid`), not the patch's full 4x4 base net -- the base
    net's corners are the patch vertices, never the point the ring
    actually needs;
  * the member's collapsed end row puts two of its corner slots on the
    ring's shared corner, and the degeneracy rule in `pair_common`
    admits exactly that (one collapsed end row against one neighbour
    corner), choosing the ring-canonical pairing.

The built corner has 36 poles, one face, a non-empty Shape and an
idempotent second ask. `test_3valent_cube_corner_seam_measurement`
records the raw seam numbers; no continuity label is asserted anywhere
in this module.
"""

import FreeCAD
import Part

import SilkChecks
import Tests.cube_corner_model as ccm
import Tests.continuity_analytic as CA
import Tests.continuity_calibration as CAL
import Tests.g2_oracle as G
import Tests.silk_nurbs as SN
from SilkMachinery import corner_ring_3
from SilkWorkflowOps import create_corner_blend

STRIP_NAMES = ("B_AB", "B_BC", "B_CA")

# The four boundary sides of the corner's 6x6 grid, as flat pole indices
# (the same sides `SilkChecks` CB1 reads).
CB_SIDES = {
    "u0": [0, 6, 12, 18, 24, 30],
    "u1": [5, 11, 17, 23, 29, 35],
    "v0": [0, 1, 2, 3, 4, 5],
    "v1": [30, 31, 32, 33, 34, 35],
}


class _CaptureConsole:
    def __enter__(self):
        self._orig = FreeCAD.Console.PrintError
        self.errors = []
        FreeCAD.Console.PrintError = lambda msg: (
            self.errors.append(msg), self._orig(msg))
        return self

    def __exit__(self, *args):
        FreeCAD.Console.PrintError = self._orig


def _corner_names(doc):
    return [o.Name for o in doc.Objects
            if getattr(o, "object_type", "") == "CornerBlend"]


def _failed(results):
    return [(n, d) for (n, ok, d) in results if not ok]


def test_cube_corner_fixture_is_oracle_green(doc):
    """The fixture itself is sound: every patch passes `check_patch` on its
    OWN stored `Edges` cycle, every strip passes `check_blend`, the three
    strips resolve as the 3-cycle ring the corner op needs, and the three
    patches share the origin corner of the cube. A corner refusal would
    therefore be attributable to the corner machinery, not to a bad
    fixture."""
    model = ccm.build_cube_corner_model(doc)
    errors, checks = [], []

    for name, p in model["patches"].items():
        bad = _failed(SilkChecks.check_patch(p, list(p.Edges)))
        if bad:
            errors.append("check_patch %s: %s" % (name, bad))
        else:
            checks.append("check_patch %s: GREEN (16 poles, own Edges "
                          "cycle)" % name)

    for name, s in model["strips"].items():
        bad = _failed(SilkChecks.check_blend(s, s.PatchA, s.PatchB))
        if bad:
            errors.append("check_blend %s: %s" % (name, bad))
        else:
            checks.append("check_blend %s: GREEN (24 poles, seam %s|%s)"
                          % (name, s.PatchA.Name, s.PatchB.Name))

    strips = [doc.getObject(n) for n in STRIP_NAMES]
    ordered, why = corner_ring_3(strips)
    if ordered is None:
        errors.append("the three strips do not resolve as a 3-cycle: %s"
                      % why)
    else:
        checks.append("corner_ring_3 orders the fixture: %s"
                      % [s.Name for s in ordered])

    for name, p in model["patches"].items():
        corners = [p.Poles[i] for i in (0, 3, 15, 12)]
        at_origin = min((c - FreeCAD.Vector(0, 0, 0)).Length for c in corners)
        if at_origin > 1e-9:
            errors.append("%s has no corner at the shared origin "
                          "(closest %.3e mm)" % (name, at_origin))
        else:
            checks.append("%s has a corner at the shared origin" % name)

    return {"pass": not errors, "errors": errors, "checks": checks}


def test_3valent_cube_corner_builds_green(doc):
    """`create_corner_blend(B_AB, B_BC, B_CA)` on the cube corner.

    CONTRACT (the pre-written positive one, now live): a CornerBlend with
    36 poles, 1+ faces, a non-empty Shape, and an idempotent second ask
    (reversed order) returning the SAME object -- one CornerBlend in the
    document, no second one. This is the 3-valent counterpart of
    `Tests/test_corner_blend.py::test_corner_blend_builds_green`; the
    surface-quality seam numbers live in the measurement test below and
    no continuity label is asserted here or anywhere in this suite.
    """
    model = ccm.build_cube_corner_model(doc)
    strips = [doc.getObject(n) for n in STRIP_NAMES]
    errors, checks = [], []

    ok_fixture = (all(len(p.Poles or []) == 16
                      for p in model["patches"].values())
                  and all(len(s.Poles or []) == 24
                          for s in model["strips"].values()))
    if not ok_fixture:
        errors.append("fixture is not 3 x 16-pole patches + 3 x 24-pole "
                      "strips")
    else:
        checks.append("fixture via ops only: 3 patches x 16 poles, "
                      "3 strips x 24 poles")

    before = _corner_names(doc)
    with _CaptureConsole() as cap:
        cb = create_corner_blend(*strips)  # exactly B_AB, B_BC, B_CA
    after = _corner_names(doc)
    msg = "".join(cap.errors).strip()

    if cb is None:
        errors.append("corner build refused: %r" % msg)
        return {"pass": False, "errors": errors, "checks": checks}

    checks.append("corner built: %s" % cb.Name)
    if len(cb.Poles or []) != 36:
        errors.append("built corner has %d poles, want 36"
                      % len(cb.Poles or []))
    else:
        checks.append("36 poles")
    if not cb.Shape or cb.Shape.isNull() or not cb.Shape.Faces:
        errors.append("corner Shape is empty (null=%s faces=%d)"
                      % (not cb.Shape or cb.Shape.isNull(),
                         len(cb.Shape.Faces) if cb.Shape else 0))
    else:
        checks.append("Shape non-empty: %d face(s)" % len(cb.Shape.Faces))
    if len(after) != len(before) + 1:
        errors.append("expected exactly one new CornerBlend, got %s -> %s"
                      % (before, after))

    # second ask, reversed order: the positive idempotency contract
    with _CaptureConsole() as cap2:
        cb2 = create_corner_blend(*list(reversed(strips)))
    if cb2 is not cb or _corner_names(doc) != after:
        errors.append("second ask was not an idempotent no-op: cb2=%r "
                      "corner objects %s" % (cb2, _corner_names(doc)))
    else:
        checks.append("second ask (reversed order) returned the same %s; "
                      "still one CornerBlend" % cb.Name)

    return {"pass": not errors, "errors": errors, "checks": checks}


def _part_surface(flat, weights, nv):
    """A `Part.BSplineSurface` from a flat v-major net (index = v*6 + u):
    the 6x6 `CubicSurface_66` layout when nv == 6, the 6x4
    `CubicSurface_64` layout when nv == 4 (u knots 1/3, 2/3; v clamped)."""
    s = Part.BSplineSurface()
    s.increaseDegree(3, 3)
    for knot, mult in ((0.0, 4), (1.0 / 3.0, 1), (2.0 / 3.0, 1), (1.0, 4)):
        s.insertUKnot(knot, mult, 1e-7)
    v_knots = ((0.0, 4), (1.0 / 3.0, 1), (2.0 / 3.0, 1), (1.0, 4)) \
        if nv == 6 else ((0.0, 4), (1.0, 4))
    for knot, mult in v_knots:
        s.insertVKnot(knot, mult, 1e-7)
    for v in range(nv):
        for u in range(6):
            s.setPole(u + 1, v + 1, flat[v * 6 + u], weights[v * 6 + u])
    return s


def _match_side(cb_poles, strip_poles):
    """(cedge, row, rev) naming the 6x6 side of the corner that is the
    strip's junction row, matched along the WHOLE row (forward or
    reversed), or None. The caller supplies the row the strip's junction
    sits on: both stored layouts (V0 and V3) are tried."""
    for row in (0, 3):
        srow = [strip_poles[row * 6 + k] for k in range(6)]
        for cedge, idxs in CB_SIDES.items():
            cbrow = [cb_poles[i] for i in idxs]
            for rev in (False, True):
                ref = list(reversed(srow)) if rev else srow
                if all((cbrow[k] - ref[k]).Length < 1e-6
                       for k in range(6)):
                    return cedge, row, rev
    return None


def test_3valent_cube_corner_seam_measurement(doc):
    """Raw seam numbers of the built 3-valent corner (measurement only).

    Every ring strip's junction row is a side of the corner's 6x6, so each
    strip/corner pair is measured with BOTH instruments:

      * sampled -- `Tests/g2_oracle.measure_seam` on Part surfaces;
      * exact   -- `Tests/continuity_analytic.measure_edges` on the stored
        control nets carrying the weights;

    plus the combinatorial `c0_controlnet`, and the calibrated floor
    (`Tests/continuity_calibration.error_floor`) each number must clear to
    mean anything. The values are reported in the check strings; nothing
    here is labelled or thresholded.

    CAVEATS, named so the numbers are not over-read:

      * the corner's fourth side is the triangular member's COLLAPSED row
        (all six poles at the ring's shared corner), so the two seams
        that terminate there read a degenerate-boundary normal at their
        apex-side stations -- `g1_deg` reaches 90 deg by construction
        exactly as `Tests/g2_edge_blend_probe.py` records for the demo's
        hard-corner members;
      * `twist_gap` depends on the caller's seam correspondence: on a
        REVERSED seam the geodesic torsion enters with a sign flip, so it
        can read ~2|tau| even where the surface is smooth (#101). Only
        non-reversed values count as evidence.
    """
    ccm.build_cube_corner_model(doc)
    strips = [doc.getObject(n) for n in STRIP_NAMES]
    cb = create_corner_blend(*strips)
    if cb is None:
        return {"pass": False,
                "errors": ["corner build refused -- nothing to measure"],
                "checks": []}
    if len(cb.Poles or []) != 36:
        return {"pass": False,
                "errors": ["corner has %d poles, want 36"
                           % len(cb.Poles or [])],
                "checks": []}

    errors, checks = [], []
    cb_flat = list(cb.Poles)
    cb_weights = list(cb.Weights) or [1.0] * 36
    cb_part = _part_surface(cb_flat, cb_weights, 6)
    cb_net = SN.NurbsSurface.from_flat(cb_flat, cb_weights, 6, 6,
                                       SN.KNOTS_6, SN.KNOTS_6)

    matched = 0
    for s in strips:
        m = _match_side(cb_flat, list(s.Poles))
        if m is None:
            errors.append("%s: none of the corner's sides is this strip's "
                          "junction row" % s.Name)
            continue
        cedge, row, rev = m
        matched += 1
        edge_st = "v0" if row == 0 else "v1"
        s_flat = list(s.Poles)
        s_weights = list(s.Weights) or [1.0] * 24
        st_part = _part_surface(s_flat, s_weights, 4)
        st_net = SN.NurbsSurface.from_flat(s_flat, s_weights, 6, 4,
                                           SN.KNOTS_6, SN.KNOTS_4)

        scb, acb = G.edge_seam(cb_part, cedge, reverse=rev)
        sst, ast = G.edge_seam(st_part, edge_st)
        sampled = G.measure_seam(cb_part, scb, acb, st_part, sst, ast, n=21)
        exact = CA.measure_edges(cb_net, cedge, rev, st_net, edge_st, False,
                                 n=21)
        c0_net, _n = SN.c0_controlnet(cb_net, cedge, st_net, edge_st,
                                      reverse=rev)

        checks.append(
            "%s = corner %s vs strip %s (row %d, reversed=%s): "
            "sampled c0=%.3e g1=%.6f deg k_gap=%.3e /mm twist_gap=%.3e /mm "
            "| exact c0=%.3e g1=%.6f deg k_gap=%.3e /mm twist_gap=%.3e /mm "
            "| c0_controlnet=%.3e"
            % (s.Name, cedge, edge_st, row, rev,
               sampled["c0"], sampled["g1_deg"], sampled["k_gap"],
               sampled["twist_gap"],
               exact["c0"], exact["g1_deg"], exact["k_gap"],
               exact["twist_gap"], c0_net))
        for tag, report in (("sampled", sampled), ("exact", exact)):
            for key in ("c0", "g1_deg", "k_gap", "twist_gap"):
                v = report[key]
                if not isinstance(v, float) or v != v or v == float("inf"):
                    errors.append("%s %s: %s not finite (%r)"
                                  % (s.Name, tag, key, v))

    if matched != len(strips):
        errors.append("matched %d of %d strips by junction row"
                      % (matched, len(strips)))

    floor = CAL.error_floor(n=21)
    for key in ("c0", "g1_deg", "k_gap", "twist_gap"):
        entry = floor.get(key) or {}
        if "sampled" not in entry or "analytic" not in entry:
            errors.append("no floor reported for %s" % key)
            continue
        checks.append("instrument floor %s: sampled %.3e / analytic %.3e"
                      % (key, entry["sampled"], entry["analytic"]))

    return {"pass": not errors, "errors": errors, "checks": checks}


def test_3valent_cube_corner_builds_in_a_reversed_ring(doc):
    """The ring direction follows DOCUMENT ORDER (`corner_ring_3` picks the
    start, then the earliest neighbour), so a user who creates the three
    strips the other way round gets the mirrored ring. The triangular
    member is placed between the two strips that meet at its patch and
    `corner_grid`'s mirrored normalization must build the SAME 36 poles as
    the canonical order -- the direction is normalized, not refused."""
    STRIPS_REVERSED = [("B_AB", "PatchA", "PatchB"),
                       ("B_CA", "PatchC", "PatchA"),
                       ("B_BC", "PatchB", "PatchC")]
    errors, checks = [], []

    ref_name = "_3valent_reversed_ref"
    if ref_name in FreeCAD.listDocuments():
        FreeCAD.closeDocument(ref_name)
    ref_doc = FreeCAD.newDocument(ref_name)
    try:
        ccm.build_cube_corner_model(ref_doc)
        FreeCAD.setActiveDocument(ref_doc.Name)
        ref = create_corner_blend(*[ref_doc.getObject(n)
                                    for n in STRIP_NAMES])
        ref_poles = list(ref.Poles) if ref is not None else None

        orig = list(ccm.STRIPS)
        ccm.STRIPS = STRIPS_REVERSED
        try:
            ccm.build_cube_corner_model(doc)
        finally:
            ccm.STRIPS = orig
        strips = [doc.getObject(n) for n in STRIP_NAMES]
        ordered, why = corner_ring_3(strips)
        order = [s.Name for s in ordered] if ordered else None
        if order != ["B_AB", "B_CA", "B_BC"]:
            errors.append("fixture did not produce the reversed ring order "
                          "(got %r: %s)" % (order, why))
        FreeCAD.setActiveDocument(doc.Name)
        with _CaptureConsole() as cap:
            cb = create_corner_blend(*strips)
        if cb is None:
            errors.append("reversed-ring build refused: %r"
                          % "".join(cap.errors).strip())
        else:
            checks.append("reversed ring %s built: %d poles, %d face(s)"
                          % (order, len(cb.Poles), len(cb.Shape.Faces)))
            if len(cb.Poles) != 36 or not cb.Shape or not cb.Shape.Faces:
                errors.append("reversed-ring corner is not 36 poles / "
                              "1+ faces")
            if ref_poles is None:
                errors.append("canonical reference build failed")
            else:
                dev = max((a - b).Length for a, b in zip(cb.Poles,
                                                         ref_poles))
                if dev > 1e-9:
                    errors.append("reversed ring fill differs from the "
                                  "canonical one: max pole dev %.3e" % dev)
                else:
                    checks.append("reversed ring fill = canonical fill "
                                  "(36-pole dev %.3e)" % dev)
    finally:
        FreeCAD.closeDocument(ref_doc.Name)
        if doc.Name in FreeCAD.listDocuments():
            FreeCAD.setActiveDocument(doc.Name)
    return {"pass": not errors, "errors": errors, "checks": checks}


def test_3valent_cube_corner_non_ring_refused(doc):
    """A 3-selection that is not a 3-cycle of strips is refused BY NAME and
    leaves no CornerBlend behind (#80/#83: never park a dead object). Two
    shapes of non-ring input: a Patch in the ring, and the same strip
    handed over twice. The existing contract -- refusal by name, nothing
    created -- must survive whatever happens to the triangular member."""
    ccm.build_cube_corner_model(doc)
    strips = [doc.getObject(n) for n in STRIP_NAMES]
    patch_a = doc.getObject("PatchA")
    cases = [("a patch in place of a strip",
              (strips[0], strips[1], patch_a), "3-cycle"),
             ("the same strip twice",
              (strips[0], strips[1], strips[0]), None)]
    errors, checks = [], []
    for label, args, must_contain in cases:
        before = _corner_names(doc)
        with _CaptureConsole() as cap:
            made = create_corner_blend(*args)
        after = _corner_names(doc)
        msg = "".join(cap.errors).strip()
        named = bool(msg) and "Silk:" in msg
        if made is not None or after != before or not named:
            errors.append("%s: made=%s corners %s->%s msg=%r"
                          % (label, made, before, after, cap.errors))
            continue
        if must_contain and must_contain not in msg:
            errors.append("%s: refused, but not by the ring contract "
                          "(missing %r): %r" % (label, must_contain, msg))
            continue
        checks.append("%s: refused by name, nothing created: %s"
                      % (label, msg))
    return {"pass": not errors, "errors": errors, "checks": checks}


ALL_TESTS = [
    test_cube_corner_fixture_is_oracle_green,
    test_3valent_cube_corner_builds_green,
    test_3valent_cube_corner_builds_in_a_reversed_ring,
    test_3valent_cube_corner_seam_measurement,
    test_3valent_cube_corner_non_ring_refused,
]
