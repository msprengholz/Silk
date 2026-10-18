"""
Corner band edges (ticket #32, restated by #82): each corner patch needs a
band edge in BOTH directions.

A 2x2 corner patch meets two blend strips (one per shared radial edge),
one seam perpendicular to U, one perpendicular to V. Each strip must
ensure the edge that isolates its 0.1 band — on the correct axis and on
the seam's own END (0.9 for a seam at parametric 1). Only then does the
0.1x0.1 corner cell at the central junction exist.

#113 (in the second test): the corner cell is HIDDEN as soon as its ring
exists, not only when a corner blend is created — so the hole a manual
fill is about to cover reads as empty. The cell is still excluded from
every band (#33); what changed is who hides it.

Pre-#82, SilkBlend wrote a split value into a per-axis LIST once per
patch (whenever the patch had no subgrids at all), regardless of seam
axis/side, and the second strip on the same patch never added the
perpendicular split. Now it writes ONE property, named for the end it
belongs to, and the two strips on one patch write two different
properties.

Expected end state after the full ring (the band edge each axis carries,
as `(Split1, Split2)`):

    patch      USplit1/USplit2   VSplit1/VSplit2
    Patch44    0.0  / 0.9        0.0  / 0.9
    Patch001   0.1  / (none)     0.0  / 0.9
    Patch002   0.0  / 0.9        0.0  / 0.9
    Patch003   0.1  / (none)     0.0  / 0.9

Patch002's two seams both sit at the parametric-1 end of their axes,
which is why its U axis carries the 1 end's edge too.

(the pre-#82 table read as `USplits=[0.9]`, `[0.1]`, `[]`, `[0.1]` with
`VSplits=[0.9]` throughout -- the same information, with each value filed
under the end that names it)
"""

# --- manual tier ------------------------------------------------------
# This module's subject is an end-to-end rebuild / GUI drive /
# measurement sweep, so it is NOT in the default (fast) tier. Run it
# with `python3 Tests/run_all.py --manual` (or by name as a filter);
# Tests/test_manual_tier.py asserts it stays importable. See suite.py.
MANUAL = True

import FreeCAD

# (name, expected (USplit1, USplit2), expected (VSplit1, VSplit2))
EXPECTED_SPLITS = [
    ("Patch44", (0.0, 0.9), (0.0, 0.9)),
    ("Patch001", (0.1, 1.0), (0.0, 0.9)),
    ("Patch002", (0.0, 0.9), (0.0, 0.9)),
    ("Patch003", (0.1, 1.0), (0.0, 0.9)),
]


def _edges(p, letter):
    """`(Split1, Split2)` of one axis, as plain floats."""
    return (round(float(getattr(p, letter + "Split1")), 12),
            round(float(getattr(p, letter + "Split2")), 12))


def _fmt(pair):
    return "%g / %g" % pair


def test_corner_patches_have_both_band_splits(doc):
    """After the full ring, every patch has an edge on both of the ends
    its two seams ask for (2x2 subgrid).

    The assertion is per PROPERTY, not per axis: #82's whole point is
    that the name says which end the edge belongs to, so a corner patch
    holding 0.9 on U's parametric-1 end and 0.1 on V's parametric-0 end
    is a different thing from one holding 0.1 and 0.9 the other way
    round — and it is the pair of PROPERTIES that tells them apart.
    """
    from Tests.corner_model import build_corner_model

    model = build_corner_model(doc)
    errors = []
    checks = []
    for name, want_u, want_v in EXPECTED_SPLITS:
        p = model["patches"][name]
        got_u = _edges(p, "U")
        got_v = _edges(p, "V")
        if got_u != want_u:
            errors.append(f"{name}: USplit1/USplit2={got_u}, want {want_u}")
        if got_v != want_v:
            errors.append(f"{name}: VSplit1/VSplit2={got_v}, want {want_v}")
        n = len(p.Proxy._subgrids)
        if n != 4:
            errors.append(f"{name}: {n} subgrid cells, want 4 (2x2)")
        checks.append(f"{name}: U={_fmt(got_u)} V={_fmt(got_v)} cells={n}")
    return {"pass": not errors, "errors": errors, "checks": checks}


def test_corner_patch_hidden_cells_cover_both_bands(doc):
    """Both trimmed strip bands are recorded, and the junction corner cell
    is hidden with them (#113).

    Cell index = iu * nv + iv (row-major over the 2x2 subgrid).
    With the #33 trim, each band stops at the corner-cell boundary, so the
    0.1x0.1 corner cell at C is covered by no strip band -- and since #113
    it is HIDDEN as soon as the ring exists, rather than staying drawn as a
    placeholder face until a corner blend is created (the owner's "why do I
    see that subpatch in the hole I am about to fill by hand").
    Patch44 (BL): B12 band (U, ss=1, trimmed) -> cells [2];
                  B31 band (V, ss=1, trimmed) -> cells [1];
                  junction corner cell (1,1)   -> cell 3;
                  union [1, 2, 3], visible cell = 0 (the panel).
    """
    from Tests.corner_model import build_corner_model

    model = build_corner_model(doc)
    p44 = model["patches"]["Patch44"]
    errors = []
    checks = []

    hidden = sorted(p44._HiddenSubgridIdxs)
    if hidden != [1, 2, 3]:
        errors.append(f"Patch44 _HiddenSubgridIdxs={hidden}, want [1, 2, 3] "
                      f"(both bands + the junction corner cell, #113)")
    checks.append(f"Patch44 hidden={hidden}")

    # In subgrid view the patch must show exactly ONE face: the outer panel
    # cell (0). The corner cell (3) is hidden as soon as its ring exists.
    p44.ShowSurface = True
    p44.ShowSubgrids = True
    p44.AutoHideBlend = True
    p44.recompute()
    faces = [s for s in p44.Shape.SubShapes if s.ShapeType == "Face"]
    if len(faces) != 1:
        errors.append(f"Patch44 subgrid view shows {len(faces)} faces, want 1 "
                      f"(the panel cell only -- the corner cell is hidden)")
    checks.append(f"subgrid view faces={len(faces)} (want 1: panel only)")

    return {"pass": not errors, "errors": errors, "checks": checks}


ALL_TESTS = [
    test_corner_patches_have_both_band_splits,
    test_corner_patch_hidden_cells_cover_both_bands,
]