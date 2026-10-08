"""
Corner band splits (ticket #32): each corner patch needs a band split in
BOTH directions.

A 2x2 corner patch meets two blend strips (one per shared radial edge),
one seam perpendicular to U, one perpendicular to V. Each strip must
ensure the split that isolates its 0.1 band — on the correct axis and on
the seam's side (0.9 for a seam at parametric 1). Only then does the
0.1x0.1 corner cell at the central junction exist.

Pre-fix, SilkBlend wrote USplits=[0.1] once per patch (whenever the patch
had no subgrids at all), regardless of seam axis/side, and the second
strip on the same patch never added the perpendicular split.

Expected end state after the full ring:

    patch      USplits   VSplits
    Patch44    [0.9]     [0.9]
    Patch001   [0.1]     [0.9]
    Patch002   [0.9]     [0.9]
    Patch003   [0.1]     [0.9]
"""

import FreeCAD

# (name, expected USplits, expected VSplits)
EXPECTED_SPLITS = [
    ("Patch44", [0.9], [0.9]),
    ("Patch001", [0.1], [0.9]),
    ("Patch002", [0.9], [0.9]),
    ("Patch003", [0.1], [0.9]),
]


def _sorted_vals(p, prop):
    return sorted(float(v) for v in (getattr(p, prop) or []))


def test_corner_patches_have_both_band_splits(doc):
    """After the full ring, every patch has both splits (2x2 subgrid)."""
    from Tests.corner_model import build_corner_model

    model = build_corner_model(doc)
    errors = []
    checks = []
    for name, want_u, want_v in EXPECTED_SPLITS:
        p = model["patches"][name]
        got_u = _sorted_vals(p, "USplits")
        got_v = _sorted_vals(p, "VSplits")
        if got_u != want_u:
            errors.append(f"{name}: USplits={got_u}, want {want_u}")
        if got_v != want_v:
            errors.append(f"{name}: VSplits={got_v}, want {want_v}")
        n = len(p.Proxy._subgrids)
        if n != 4:
            errors.append(f"{name}: {n} subgrid cells, want 4 (2x2)")
        checks.append(f"{name}: U={got_u} V={got_v} cells={n}")
    return {"pass": not errors, "errors": errors, "checks": checks}


def test_corner_patch_hidden_cells_cover_both_bands(doc):
    """Both strip bands are recorded; only the far corner cell stays visible.

    Cell index = iu * nv + iv (row-major over the 2x2 subgrid).
    Patch44 (BL): B12 band (U, ss=1) -> cells [2, 3];
                  B31 band (V, ss=1) -> cells [1, 3];
                  union [1, 2, 3], visible cell = 0.
    """
    from Tests.corner_model import build_corner_model

    model = build_corner_model(doc)
    p44 = model["patches"]["Patch44"]
    errors = []
    checks = []

    hidden = sorted(p44._HiddenSubgridIdxs)
    if hidden != [1, 2, 3]:
        errors.append(f"Patch44 _HiddenSubgridIdxs={hidden}, want [1, 2, 3]")
    checks.append(f"Patch44 hidden={hidden}")

    # In subgrid view the patch must show exactly one face (cell 0).
    p44.ShowSurface = True
    p44.ShowSubgrids = True
    p44.AutoHideBlend = True
    p44.recompute()
    faces = [s for s in p44.Shape.SubShapes if s.ShapeType == "Face"]
    if len(faces) != 1:
        errors.append(f"Patch44 subgrid view shows {len(faces)} faces, want 1")
    checks.append(f"subgrid view faces={len(faces)} (want 1)")

    return {"pass": not errors, "errors": errors, "checks": checks}


ALL_TESTS = [
    test_corner_patches_have_both_band_splits,
    test_corner_patch_hidden_cells_cover_both_bands,
]
