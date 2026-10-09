"""
#28 Corner blend object — the 4-subgrid corner fill producing a 6x6 patch.

Where 4 patches meet at the central junction, each patch contributes its
0.1x0.1 corner subgrid cell (excluded from the ring blend bands, #33).
The corner blend object takes the 4 ring BlendStrips, extracts each
strip's corner-end row (the 6-pole edge of the strip's blend surface at
the corner-cell side), and builds a 6x6 control grid via
AN.ControlGrid66_4 + AN.CubicSurface_66 — the 4-sided corner blend.

The strip corner-end rows form an exact closed loop around the corner
region (adjacent rows share the patches' outer corner poles), so the
boundary is C0 to all 4 strip surfaces by construction.

Acceptance (T4 preview): the completed 2x2 corner tiling — 4 panels,
4 strips, 1 corner blend — without gaps or overlaps.
"""

import Tests.corner_model as cm
import SilkChecks
from SilkWorkflowOps import create_corner_blend

STRIP_NAMES = ("B12", "B24", "B43", "B31")

# corner cell index per patch (2x2 grid, cell index = iu*nv + iv)
# Patch44 corner (1,1) -> 3, Patch001 corner (0,1) -> 1,
# Patch002 corner (1,1) -> 3, Patch003 corner (0,1) -> 1
EXPECTED_HIDDEN = {
    "Patch44": [1, 2, 3],
    "Patch001": [0, 1, 3],
    "Patch002": [1, 2, 3],
    "Patch003": [0, 1, 3],
}


def _build(doc):
    model = cm.build_corner_model(doc)
    strips = [doc.getObject(n) for n in STRIP_NAMES]
    cb = create_corner_blend(*strips)
    return model, strips, cb


def _failed(results):
    return [(n, d) for (n, ok, d) in results if not ok]


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
    import FreeCAD
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
    import FreeCAD
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


ALL_TESTS = [
    test_corner_blend_builds_green,
    test_corner_blend_hides_corner_cells,
    test_corner_blend_negative_boundary_pole,
    test_corner_blend_negative_interior_pole,
]
