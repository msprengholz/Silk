"""
#113: a junction's corner cell is hidden as soon as its RING of blends
exists, not only once a corner blend is created.

The owner, after building the corner with edge blends: "when doing the edge
blends, the subgrids that remain in the corner should be automatically
hidden as well. this makes it easier to later perform manual surface
filling. it does not add anything useful when i see that subpatch."

The subtlety is why this is not a one-liner: a single Blend cannot identify
a corner. A corner cell is pinned by a seam on EACH axis, and one blend
knows only its own seam -- so the trigger is a PAIR of blends meeting at the
same corner on one patch. `SilkBlend._junction_corner_cells` reuses
`CornerBlend._corner_cell` for the cell itself, so the ring path and the
corner path cannot disagree about which cell a junction owns.

These tests derive the expectation INDEPENDENTLY of that helper -- the band
is the seam-adjacent cell the corner exclusion leaves (SilkMachinery
.band_cells), and the junction corner is the cell the two axes' seams pin --
and then assert the object's hidden set equals that union exactly. A stale
index (the "hole" a wrong unblend leaves) shows up as a hidden cell in
neither set; a missing one shows up as a visible cell that should be gone.

No continuity label is asserted anywhere in this module.
"""

# --- manual tier ------------------------------------------------------
# This module's subject is an end-to-end rebuild / GUI drive /
# measurement sweep, so it is NOT in the default (fast) tier. Run it
# with `python3 Tests/run_all.py --manual` (or by name as a filter);
# Tests/test_manual_tier.py asserts it stays importable. See suite.py.
MANUAL = True

import FreeCAD

import Tests.demo01_fixture_model as MODEL
from Tests.mcp_harness import check


def _blended_seams(document):
    """Every seam a live blend covers (SilkWorkflowOps.seam_inventory)."""
    import SilkWorkflowOps as OPS
    return [e for e in OPS.seam_inventory(document) if e["blend"] is not None]


def _derivation(patch, entries, tol=0.01):
    """(band cells, junction corner cells, cell count) for `patch`.

    The documented rules, written out again rather than imported:

      * a band is the seam-adjacent cell the corner exclusion leaves on the
        seam-PERPENDICULAR axis (`SilkMachinery.band_cells`);
      * a junction corner cell is pinned by a seam on each axis -- the
        U-direction seam fixes the V side, the V-direction seam the U side
        -- so it exists only where TWO seams meet on DIFFERENT axes and
        lead to two DIFFERENT neighbours (a junction is 3+ patches).

    `side_and_end` is the one seam-side reader the whole workbench shares;
    the corner-cell mapping above is this test's own.
    """
    from SilkBlend import side_and_end
    from SilkMachinery import band_cells, build_intervals, split_pair

    nu = len(build_intervals(*split_pair(patch, "U")))
    nv = len(build_intervals(*split_pair(patch, "V")))
    bands = set()
    by_axis = {"U": [], "V": []}
    for entry in entries:
        blend = entry["blend"]
        if not (entry["patch_a"] is patch or entry["patch_b"] is patch):
            continue
        etype, ss = side_and_end(blend, patch, tol)
        if not etype:
            continue
        bands |= set(band_cells(patch, etype, ss))
        other = blend.PatchB if blend.PatchA is patch else blend.PatchA
        by_axis[etype[0]].append((etype, other))
    junctions = set()
    for etype_u, other_u in by_axis["U"]:
        for etype_v, other_v in by_axis["V"]:
            if other_u is other_v:
                continue
            iv_c = nv - 1 if etype_u[1] == "1" else 0
            iu_c = nu - 1 if etype_v[1] == "1" else 0
            junctions.add(iu_c * nv + iv_c)
    return bands, junctions, nu * nv


def _hidden(patch):
    return set(int(i) for i in (getattr(patch, "_HiddenSubgridIdxs", None) or []))


def _visible_faces(patch):
    """How many subgrid cells the patch actually DRAWS -- one face per
    non-hidden cell in subgrid view. This is the end-to-end check that the
    bookkeeping and the display agree (a stale index would leave a hole)."""
    patch.ShowSubgrids = True
    patch.AutoHideBlend = True
    patch.recompute()
    n = len(patch.Shape.Faces)
    patch.ShowSubgrids = False
    patch.recompute()
    return n


def _check_patch(patch, entries, errors, checks, context):
    bands, junctions, n_cells = _derivation(patch, entries)
    hidden = _hidden(patch)
    check(not (bands & junctions),
          "%s %s: cell(s) %s are BOTH a band and a junction corner -- a "
          "corner cell is excluded from every band"
          % (context, patch.Name, sorted(bands & junctions)), errors)
    check(hidden == bands | junctions,
          "%s %s: hidden cells %s, want the bands %s union the junction "
          "corners %s"
          % (context, patch.Name, sorted(hidden), sorted(bands),
             sorted(junctions)), errors)
    n_faces = _visible_faces(patch)
    check(n_faces == n_cells - len(hidden),
          "%s %s: %d of %d cells drawn, want %d (a stale hidden index leaves "
          "a hole, a missing one leaves a subpatch in it)"
          % (context, patch.Name, n_faces, n_cells, n_cells - len(hidden)),
          errors)
    checks.append("%s %s: %d cells, bands %s + junctions %s hidden, %d drawn"
                  % (context, patch.Name, n_cells, sorted(bands),
                     sorted(junctions), n_faces))
    return bands, junctions, n_cells


def _build_without_corners(doc, result_problems):
    result = MODEL.build(doc, corners=False)
    result_problems.extend(result["problems"])
    return result


def test_demo01_ring_hides_every_junction_corner_cell(doc):
    """The owner's Demo 01 model built WITHOUT the corner blends: every ring
    patch hides its junction corner cell(s), and nothing else is hidden --
    the non-junction corners are either a band cell (hidden by their own
    blend, unchanged) or drawn.

    Then the four corner blends are created: the hidden sets must be
    IDENTICAL, because the corner fill's own write is the same derivation.
    The two paths agree rather than fight."""
    errors, checks = [], []
    problems = []
    result = _build_without_corners(doc, problems)
    if problems:
        return {"pass": False, "checks": checks,
                "errors": ["fixture build refused: %s" % problems]}
    entries = _blended_seams(doc)
    patches = list(result["patches"].values())
    total = 0
    for patch in patches:
        _bands, junctions, _n = _check_patch(patch, entries, errors, checks,
                                             "ring only:")
        total += len(junctions)
    check(total == 12,
          "%d junction corner cells over the 5 patches, want 12 (four "
          "3-valent junctions, each pinning a corner on three patches)"
          % total, errors)

    before = {p.Name: sorted(_hidden(p)) for p in patches}
    from SilkWorkflowOps import create_corner_blend
    for name, ring, _point in MODEL.CORNERS:
        corner = create_corner_blend([result["blends"][b] for b in ring],
                                     name=name)
        check(corner is not None,
              "the corner blend %s refused on the ring the test just built"
              % name, errors)
    doc.recompute()
    after = {p.Name: sorted(_hidden(p)) for p in patches}
    check(after == before,
          "creating the corner blends CHANGED the hidden sets: %s -> %s -- "
          "the ring path and the corner path must agree"
          % (before, after), errors)
    checks.append("after the four corner blends: hidden sets byte-identical "
                  "(%s)" % after)
    return {"pass": not errors, "errors": errors, "checks": checks}


def test_a_patchs_non_junction_corner_cell_stays_visible(doc):
    """The cube-corner fixture (3 planar patches, each 2x2 cells, ONE shared
    junction): each patch hides its two bands and its junction corner cell,
    and the cell at the patch's FAR corner -- a corner of the patch that is
    not a junction -- is still drawn. Hiding a patch's other corners is the
    failure mode this pins."""
    errors, checks = [], []
    from Tests import cube_corner_model

    cube_corner_model.build_cube_corner_model(doc)
    doc.recompute()
    entries = _blended_seams(doc)
    patches = [o for o in doc.Objects
               if getattr(o, "object_type", None) == "Patch"]
    check(len(patches) == 3, "fixture: %d patches, want 3" % len(patches),
          errors)
    for patch in patches:
        bands, junctions, n_cells = _check_patch(patch, entries, errors, checks,
                                                 "cube corner:")
        check(len(junctions) == 1,
              "%s: %d junction corners, want exactly 1 (the cube corner)"
              % (patch.Name, len(junctions)), errors)
        visible = set(range(n_cells)) - bands - junctions
        check(len(visible) == 1,
              "%s: %d cells are neither a band nor the junction corner, want "
              "the single far corner cell (%s)"
              % (patch.Name, len(visible), sorted(visible)), errors)
        cell = sorted(visible)[0]
        # the far corner of a 2x2 grid is cell 3; it is a CORNER cell of the
        # patch, and it is NOT the junction -- so it must stay visible
        check(cell == n_cells - 1,
              "%s: the surviving cell is %d, want the far corner %d"
              % (patch.Name, cell, n_cells - 1), errors)
        check(cell not in junctions,
              "%s: the far corner cell %d is treated as a junction"
              % (patch.Name, cell), errors)
    return {"pass": not errors, "errors": errors, "checks": checks}


def test_unblending_a_ring_gives_the_junction_cell_back(doc):
    """Unblend one ring strip and the cell comes back: the hidden set is
    re-derived (the existing unblend rule), so no stale index survives and
    no hole is left. The junctions that strip pinned -- two on each of its
    patches -- are gone; every other junction is untouched."""
    errors, checks = [], []
    problems = []
    result = _build_without_corners(doc, problems)
    if problems:
        return {"pass": False, "checks": checks,
                "errors": ["fixture build refused: %s" % problems]}
    entries = _blended_seams(doc)
    victim = result["blends"]["B_FR"]
    victim_name = victim.Name
    fed = [victim.PatchA, victim.PatchB]
    before = {p.Name: _derivation(p, entries) for p in fed}
    for p in fed:
        check(len(before[p.Name][1]) > 0,
              "precondition: %s had no junction corner before the unblend"
              % p.Name, errors)

    doc.removeObject(victim_name)
    doc.recompute()
    entries = _blended_seams(doc)
    for p in fed:
        _bands, junctions, _n = _check_patch(p, entries, errors, checks,
                                             "unblended:")
        lost = len(before[p.Name][1]) - len(junctions)
        check(lost == 2,
              "%s: %d junction corners went with %s, want the 2 it pinned"
              % (p.Name, lost, victim_name), errors)
    return {"pass": not errors, "errors": errors, "checks": checks}


ALL_TESTS = [
    test_demo01_ring_hides_every_junction_corner_cell,
    test_a_patchs_non_junction_corner_cell_stays_visible,
    test_unblending_a_ring_gives_the_junction_cell_back,
]
