"""
#28 Corner blend object — the 4-subgrid corner fill producing a 6x6 patch.

Where 4 patches meet at the central junction, each contributes its
corner subgrid cell (excluded from the ring blend bands, #33). The corner
blend object takes the 4 ring Blend strips and builds the 6x6 control
grid the way upstream Silk does (#91): four consecutive strip pairs each
make a 3x3 subgrid (`SubGrid33_2Grid64`), the four subgrids assemble into
the 6x6 (`ControlGrid66_4Sub`), and `CubicSurface_66` builds the surface.

The strip corner-end rows form an exact closed loop around the corner
region (adjacent rows share the patches' outer corner poles), so the
boundary is C0 to all 4 strip surfaces by construction.

Acceptance (T4 preview): the completed 2x2 corner tiling — 4 panels,
4 strips, 1 corner blend — without gaps or overlaps.
"""

import FreeCAD

import Tests.corner_model as cm
import SilkChecks
from SilkWorkflowOps import create_corner_blend
from SilkMachinery import corner_grid
from SilkCorner import corner_inputs, CORNER_TOL

STRIP_NAMES = ("B12", "B24", "B43", "B31")

# The 3-valent ring (Tests/cube_corner_model.py): three patches meeting at
# one cube corner, three strips in a directed cycle. Its corner stores the
# THREE strips it was built from -- the triangular 4th member is derived.
STRIP3_NAMES = ("B_AB", "B_BC", "B_CA")

# corner cell index per patch (2x2 grid, cell index = iu*nv + iv)
# Patch44 corner (1,1) -> 3, Patch001 corner (0,1) -> 1,
# Patch002 corner (1,1) -> 3, Patch003 corner (0,1) -> 1
EXPECTED_HIDDEN = {
    "Patch44": [1, 2, 3],
    "Patch001": [0, 1, 3],
    "Patch002": [1, 2, 3],
    "Patch003": [0, 1, 3],
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


def _build(doc):
    model = cm.build_corner_model(doc)
    strips = [doc.getObject(n) for n in STRIP_NAMES]
    cb = create_corner_blend(*strips)
    return model, strips, cb


def _failed(results):
    return [(n, d) for (n, ok, d) in results if not ok]


def _legacy_corner_chain(grids, doc):
    """The ground-truth oracle: instantiate the legacy restore shims
    (`AN.SubGrid33_2Grid64` x4 -> `AN.ControlGrid66_4Sub`) on the SAME
    canonical grids and return the assembled (poles36, weights36). The
    temp objects are removed before returning."""
    import ArachNURBS as AN
    carriers, subs, grid = [], [], None
    try:
        for p, w in grids:
            c = doc.addObject("Part::FeaturePython", "_parity_poly")
            c.addProperty("App::PropertyVectorList", "Poles", "X", "p").Poles
            c.addProperty("App::PropertyFloatList", "Weights", "X", "w").Weights
            c.Poles = list(p)
            c.Weights = list(w)
            carriers.append(c)
        for i in range(4):
            sg = doc.addObject("Part::FeaturePython", "_parity_sub")
            AN.SubGrid33_2Grid64(sg, carriers[i], carriers[(i + 1) % 4])
            sg.recompute()
            subs.append(sg)
        grid = doc.addObject("Part::FeaturePython", "_parity_grid")
        AN.ControlGrid66_4Sub(grid, *subs)
        grid.recompute()
        return list(grid.Poles), list(grid.Weights)
    finally:
        for o in ([grid] if grid is not None else []) + subs + carriers:
            if o is not None and doc.getObject(o.Name) is not None:
                try:
                    doc.removeObject(o.Name)
                except Exception:
                    pass


def test_corner_blend_builds_green(doc):
    """The corner blend passes structural + C0 boundary + fill + B3."""
    _, strips, cb = _build(doc)
    results = SilkChecks.check_corner_blend(cb, *strips)
    failed = _failed(results)

    return {
        "pass": not failed,
        "errors": ["%s: %s" % (n, d) for n, d in failed],
        "checks": ["%s: %s" % (n, "OK" if ok else "FAIL " + d)
                   for n, ok, d in results],
    }


def test_corner_blend_pole_parity_with_legacy_chain(doc):
    """#91 oracle: the corner poles AND weights match the legacy subgrid
    chain (SubGrid33_2Grid64 x4 -> ControlGrid66_4Sub) fed the same
    canonical grids, pole for pole, within 1e-6.

    The legacy classes are the ground truth; our machinery is a port of
    them, so a deviation here means the port drifted.
    """
    model, strips, cb = _build(doc)
    if cb is None:
        return {"pass": False, "errors": ["no corner blend created"],
                "checks": []}
    grids, _cells, why = corner_inputs(strips, 0.01)
    if grids is None:
        return {"pass": False, "errors": ["corner_inputs refused: %s" % why],
                "checks": []}
    lp, lw = _legacy_corner_chain(grids, doc)

    dev = max((a - b).Length for a, b in zip(cb.Poles, lp))
    wdev = max(abs(a - b) for a, b in zip(cb.Weights, lw))
    ok = len(lp) == 36 and dev <= 1e-6 and wdev <= 1e-9
    return {
        "pass": ok,
        "errors": [] if ok else ["legacy pole parity %.3e / weight parity "
                                 "%.3e (want <= 1e-6 / 1e-9)" % (dev, wdev)],
        "checks": ["legacy pole parity %.3e, weight parity %.3e over 36 "
                   "poles" % (dev, wdev)],
    }


def test_corner_machinery_matches_legacy_with_rational_weights(doc):
    """The port CARRIES the weights: with non-unit strip weights the
    assembled 6x6 weights still match the legacy chain, and they are no
    longer all 1.0 (the corner fixture's own strips happen to be unit
    weight, so this is the test that exercises the cross-products)."""
    cm.build_corner_model(doc)
    strips = [doc.getObject(n) for n in STRIP_NAMES]
    grids, _cells, why = corner_inputs(strips, 0.01)
    if grids is None:
        return {"pass": False, "errors": ["corner_inputs refused: %s" % why],
                "checks": []}
    # give every grid a distinct, non-unit weight field
    tweaked = []
    for gi, (p, w) in enumerate(grids):
        nw = [wi * (1.0 + 0.37 * gi + 0.11 * k) for k, wi in enumerate(w)]
        tweaked.append((list(p), nw))
    p36, w36, why = corner_grid(tweaked, CORNER_TOL)
    if p36 is None:
        return {"pass": False, "errors": ["corner_grid refused: %s" % why],
                "checks": []}
    lp, lw = _legacy_corner_chain(tweaked, doc)
    dev = max((a - b).Length for a, b in zip(p36, lp))
    wdev = max(abs(a - b) for a, b in zip(w36, lw))
    varied = max(w36) - min(w36) > 1e-6
    ok = dev <= 1e-6 and wdev <= 1e-9 and varied
    return {
        "pass": ok,
        "errors": [] if ok else ["rational-weight port drifted: pole %.3e "
                                 "weight %.3e varied=%s" % (dev, wdev, varied)],
        "checks": ["with non-unit strip weights: pole parity %.3e, weight "
                   "parity %.3e, weights varied=%s" % (dev, wdev, varied)],
    }


def test_corner_blend_is_idempotent(doc):
    """Asking twice for the corner on one junction returns the SAME object
    -- no second CornerBlend is created, whatever order the strips arrive
    in."""
    model, strips, cb = _build(doc)
    again = create_corner_blend(*[doc.getObject(n)
                                  for n in ("B31", "B12", "B43", "B24")])
    corners = [o for o in doc.Objects
               if getattr(o, "object_type", "") == "CornerBlend"]
    ok = cb is not None and again is cb and len(corners) == 1
    return {
        "pass": bool(ok),
        "errors": [] if ok else ["idempotency failed: cb=%s again=%s corners=%s"
                                 % (cb, again, [c.Name for c in corners])],
        "checks": ["one CornerBlend after two asks; second returned the "
                   "first (%s)" % (cb.Name if cb else None)],
    }


def test_corner_blend_click_order_does_not_change_the_fill(doc):
    """The ring resolver makes the fill independent of the order the 4
    strips were handed over in: a rotation and a reversal of the click
    order both yield the SAME 36 poles as the natural order."""
    cm.build_corner_model(doc)
    s = [doc.getObject(n) for n in STRIP_NAMES]
    base = create_corner_blend(*s)
    if base is None:
        return {"pass": False, "errors": ["no base corner"], "checks": []}
    base_poles = list(base.Poles)
    # remove and re-create from a rotated + a reversed order
    devs = []
    for order in ((s[1], s[2], s[3], s[0]), (s[1], s[0], s[3], s[2])):
        doc.removeObject(base.Name)
        doc.recompute()
        cb = create_corner_blend(*order)
        if cb is None:
            return {"pass": False,
                    "errors": ["corner refused for order %s"
                               % [o.Name for o in order]], "checks": []}
        devs.append(max((a - b).Length for a, b in zip(base_poles, cb.Poles)))
        base = cb
    ok = max(devs) <= 1e-9
    return {
        "pass": ok,
        "errors": [] if ok else ["fill depends on click order: dev %s" % devs],
        "checks": ["rotated/reversed click order: 36-pole deviation %s "
                   "(same fill)" % ["%.3e" % d for d in devs]],
    }


def test_corner_grid_normalizes_the_ring_direction(doc):
    """The subgrid chain only accepts the shared corner at (V3, U5) on the
    first grid and (V3, U0) on the second; a ring traversed the other way
    presents every pair MIRRORED and assembles into a grid whose boundary
    does not match the ring's own. `corner_ring` fixes the ring's start
    but not its direction, so `corner_grid` must normalize a mirrored ring
    to the SAME 6x6 as the canonical one."""
    cm.build_corner_model(doc)
    strips = [doc.getObject(n) for n in STRIP_NAMES]
    grids, _cells, why = corner_inputs(strips, 0.01)
    if grids is None:
        return {"pass": False, "errors": ["corner_inputs refused: %s" % why],
                "checks": []}
    p_can, _w_can, why = corner_grid(grids, CORNER_TOL)
    if p_can is None:
        return {"pass": False, "errors": ["canonical ring refused: %s" % why],
                "checks": []}
    mirrored = [grids[0]] + list(reversed(grids[1:]))
    p_mir, _w_mir, why = corner_grid(mirrored, CORNER_TOL)
    if p_mir is None:
        return {"pass": False,
                "errors": ["mirrored ring refused, not normalized: %s" % why],
                "checks": []}
    dev = max((a - b).Length for a, b in zip(p_can, p_mir))
    ok = dev <= 1e-9
    return {
        "pass": ok,
        "errors": [] if ok else ["mirrored ring fills differently: %.3e"
                                 % dev],
        "checks": ["canonical vs mirrored ring: 36-pole dev %.3e (the "
                   "direction is normalized, not refused)" % dev],
    }


def test_corner_blend_refuses_non_ring_and_leaves_no_object(doc):
    """A selection that is not the ring of 4 blends around one junction is
    refused BY NAME and leaves NO CornerBlend in the tree (#80/#83: never
    park an invalid, up-to-date, unmarked object)."""
    cm.build_corner_model(doc)
    s = [doc.getObject(n) for n in STRIP_NAMES]
    patch = doc.getObject("Patch44")
    cases = [("three strips", (s[0], s[1], s[2])),
             ("a repeated strip", (s[0], s[1], s[2], s[0])),
             ("a patch in the ring", (s[0], s[1], s[2], patch))]
    errors, checks = [], []
    for label, args in cases:
        with _CaptureConsole() as cap:
            made = create_corner_blend(*args)
        corners = [o for o in doc.Objects
                   if getattr(o, "object_type", "") == "CornerBlend"]
        named = bool(cap.errors) and "Silk:" in "".join(cap.errors)
        if made is not None or corners or not named:
            errors.append("%s: made=%s corners=%s msg=%r"
                          % (label, made, [c.Name for c in corners],
                             cap.errors))
        else:
            checks.append("%s refused by name, nothing created: %s"
                          % (label, cap.errors[-1].strip()[:70]))
    return {"pass": not errors, "errors": errors, "checks": checks}


def test_corner_blend_hides_corner_cells(doc):
    """After the corner blend, each patch's hidden set gains the corner
    cell index, so the completed tiling shows only the panel cells."""
    model, strips, cb = _build(doc)
    errors = []
    checks = []
    for name, want in EXPECTED_HIDDEN.items():
        patch = doc.getObject(name)
        got = sorted(int(i) for i in (patch._HiddenSubgridIdxs or []))
        ok = got == want
        checks.append("%s hidden=%s (want %s): %s"
                      % (name, got, want, "OK" if ok else "FAIL"))
        if not ok:
            errors.append("%s hidden cells %s, want %s" % (name, got, want))
        # subgrid display shows only the panel cell (1 face)
        patch.ShowSubgrids = True
        patch.AutoHideBlend = True
        doc.recompute()
        n_faces = len(patch.Shape.Faces)
        ok2 = n_faces == 1
        checks.append("%s subgrid view faces=%d (want 1): %s"
                      % (name, n_faces, "OK" if ok2 else "FAIL"))
        if not ok2:
            errors.append("%s subgrid view shows %d faces, want 1"
                          % (name, n_faces))
        patch.ShowSubgrids = False
        patch.AutoHideBlend = True

    return {"pass": not errors, "errors": errors, "checks": checks}


def test_corner_blend_negative_boundary_pole(doc):
    """A corrupted boundary pole must fail the C0 boundary check."""
    _, strips, cb = _build(doc)
    poles = list(cb.Poles)
    poles[0] = FreeCAD.Vector(poles[0].x + 5.0, poles[0].y, poles[0].z)
    cb.Poles = poles
    results = SilkChecks.check_corner_blend(cb, *strips)
    by_name = {n: ok for (n, ok, d) in results}
    ok = by_name.get("CB1_c0_boundary") is False
    return {
        "pass": ok,
        "errors": [] if ok else ["corrupted boundary pole not flagged: %s"
                                 % by_name],
        "checks": ["CB1_c0_boundary flags corrupted boundary pole: %s"
                   % ("OK" if ok else "FAIL")],
    }


def test_corner_blend_negative_interior_pole(doc):
    """A corrupted interior pole must fail the interior fill check."""
    _, strips, cb = _build(doc)
    poles = list(cb.Poles)
    poles[14] = FreeCAD.Vector(poles[14].x, poles[14].y,
                               poles[14].z + 3.0)   # interior (2,2)
    cb.Poles = poles
    results = SilkChecks.check_corner_blend(cb, *strips)
    by_name = {n: ok for (n, ok, d) in results}
    ok = by_name.get("CB2_interior_fill") is False
    return {
        "pass": ok,
        "errors": [] if ok else ["corrupted interior pole not flagged: %s"
                                 % by_name],
        "checks": ["CB2_interior_fill flags corrupted interior pole: %s"
                   % ("OK" if ok else "FAIL")],
    }


def test_three_strip_ring_is_checkable(doc):
    """The oracle reads a 3-valent hard corner instead of raising on its
    4-argument signature (a 3-strip corner is a shipped object).

    Structural + CB1 + CB3 are asserted as for the 4-valent corner; CB2 is
    reported as NOT APPLICABLE with its measured reason -- the legacy
    subgrid chain cannot assemble the triangular member's collapsed row,
    and the shipped cap re-solves those rows on purpose, so a legacy
    pole-for-pole match there is the wrong assertion, not a missing one.
    """
    import Tests.cube_corner_model as ccm

    model = ccm.build_cube_corner_model(doc)
    strips = [model["strips"][n] for n in STRIP3_NAMES]
    cb = create_corner_blend(*strips)
    if cb is None:
        return {"pass": False, "errors": ["3-valent corner refused"],
                "checks": []}

    try:
        results = SilkChecks.check_corner_blend(cb, *strips)
    except Exception as exc:
        return {"pass": False, "checks": [],
                "errors": ["check_corner_blend raised on a 3-strip ring: %r"
                           % (exc,)]}
    by_name = {n: (ok, d) for (n, ok, d) in results}
    errors, checks = [], []
    for want in ("structural", "CB1_c0_boundary", "CB3_surface_valid"):
        ok, detail = by_name.get(want, (None, "MISSING"))
        if ok is not True:
            errors.append("%s is %r: %s" % (want, ok, detail))
        else:
            checks.append("%s: %s" % (want, detail))
    cb2_ok, cb2_detail = by_name.get("CB2_interior_fill", (None, "MISSING"))
    if cb2_ok is not True or "not applicable" not in cb2_detail:
        errors.append("CB2 on a 3-valent ring should be reported as not "
                      "applicable: %r %s" % (cb2_ok, cb2_detail))
    else:
        checks.append("CB2_interior_fill: %s" % cb2_detail)
    return {"pass": not errors, "errors": errors, "checks": checks}


def test_three_strip_ring_negative_boundary_pole(doc):
    """A corrupted boundary pole of a 3-VALENT corner must fail CB1.

    The 4-valent counterpart is `test_corner_blend_negative_boundary_pole`;
    this is the negative control for the 3-strip reading: CB1 must not go
    green because it only matched three of the corner's four sides.
    """
    import Tests.cube_corner_model as ccm

    model = ccm.build_cube_corner_model(doc)
    strips = [model["strips"][n] for n in STRIP3_NAMES]
    cb = create_corner_blend(*strips)
    if cb is None:
        return {"pass": False, "errors": ["3-valent corner refused"],
                "checks": []}
    poles = list(cb.Poles)
    poles[0] = FreeCAD.Vector(poles[0].x + 5.0, poles[0].y, poles[0].z)
    cb.Poles = poles
    results = SilkChecks.check_corner_blend(cb, *strips)
    by_name = {n: ok for (n, ok, d) in results}
    ok = by_name.get("CB1_c0_boundary") is False
    return {
        "pass": ok,
        "errors": [] if ok else ["corrupted 3-valent boundary pole not "
                                  "flagged: %s" % by_name],
        "checks": ["CB1 flags a corrupted 3-valent boundary pole: %s"
                   % ("OK" if ok else "FAIL")],
    }


def test_check_corner_blend_refuses_wrong_input_shapes_by_name(doc):
    """The oracle NEVER raises on a bad input: 0 / 1 / 2 strips are refused
    as input by count, a non-ring triple is refused with the ring
    resolver's own reason (which names the strip), and a 5-strip list is
    refused by count -- every one a named result, not an exception.

    This is the guard against the worst oracle failure: an empty ring used
    to match no row at all and CB1 returned a 0.0 deviation -- a GREEN for
    having checked nothing.
    """
    cm.build_corner_model(doc)
    ring = [doc.getObject(n) for n in STRIP_NAMES]
    cb = create_corner_blend(*ring)
    errors, checks = [], []
    if cb is None:
        return {"pass": False, "errors": ["the 2x2 corner did not build"],
                "checks": []}

    non_ring = [ring[0], ring[1], ring[3]]        # no 3-cycle: 1-1-2 shares
    cases = (("no strip at all", ()),
             ("one strip", (ring[0],)),
             ("two strips", (ring[0], ring[1])),
             ("a non-ring triple", tuple(non_ring)))
    for label, args in cases:
        try:
            results = SilkChecks.check_corner_blend(cb, *args)
        except Exception as exc:
            errors.append("%s raised %r instead of refusing" % (label, exc))
            continue
        named = all(isinstance(r, tuple) and len(r) == 3 and r[2]
                    for r in results)
        refused = bool(results) and any(not ok for (_n, ok, _d) in results)
        if not (named and refused):
            errors.append("%s: results %r" % (label, results))
            continue
        bad = [(n, d) for (n, ok, d) in results if not ok]
        if len(args) in (0, 1, 2):
            name, detail = bad[0][0], bad[0][1]
            if name != "ring_input" or str(len(args)) not in detail:
                errors.append("%s was refused as %r/%s, want a ring_input "
                              "refusal naming the count"
                              % (label, name, detail))
                continue
        else:
            detail = " | ".join(d for (_n, d) in bad)
            if not any(s.Name in detail for s in non_ring):
                errors.append("the non-ring triple was refused without "
                              "naming a strip: %s" % detail)
                continue
        checks.append("%s -> %s"
                      % (label, " | ".join("%s: %s" % (n, d[:60])
                                           for (n, _ok, d) in results)))

    # a 5-strip ring (the list form is the only shape that can express it)
    try:
        results = SilkChecks.check_corner_blend(list(ring) + [ring[0]])
    except Exception as exc:
        errors.append("a 5-strip ring raised %r instead of refusing" % exc)
    else:
        if results and results[0][0] == "ring_input" \
                and results[0][1] is False:
            checks.append("5 strips -> %s" % results[0][2])
        else:
            errors.append("a 5-strip ring gave %r" % (results,))
    return {"pass": not errors, "errors": errors, "checks": checks}


ALL_TESTS = [
    test_corner_blend_builds_green,
    test_corner_blend_pole_parity_with_legacy_chain,
    test_corner_machinery_matches_legacy_with_rational_weights,
    test_corner_blend_is_idempotent,
    test_corner_blend_click_order_does_not_change_the_fill,
    test_corner_grid_normalizes_the_ring_direction,
    test_corner_blend_refuses_non_ring_and_leaves_no_object,
    test_corner_blend_hides_corner_cells,
    test_corner_blend_negative_boundary_pole,
    test_corner_blend_negative_interior_pole,
    # #103: the 3-valent reading of the same oracle
    test_three_strip_ring_is_checkable,
    test_three_strip_ring_negative_boundary_pole,
    test_check_corner_blend_refuses_wrong_input_shapes_by_name,
]
