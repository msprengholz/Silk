"""
Tests/test_patch_touched.py -- ticket #59: a settled model must not be
left dirty, and the Patch display defaults must let the blend band
auto-hide.

Part 1 (the defect): Blend.execute -> run_blend -> ensure_band_split
writes the band split on both covered Patches. That write fires
Patch.onChanged's USplits/VSplits branch (`fp.touch(); fp.recompute()`),
and run_blend additionally recomputes both feeds up front. Because
FreeCAD's DocumentObject.recompute() touches the object it recomputes,
and Patch.execute itself touches every linked Blend, Patch <-> Blend
forms a compute cycle: after create_blend_by_edge + doc.recompute() the
two covered Patches stayed ['Touched'] forever (the Blend was
Up-to-date), so the document never settled -- spurious save prompts,
recompute-loop hazard.

The fix is in SilkPatch.execute: the Patch now purges its own Touched
flag once its geometry is rebuilt. Nested/forced recomputes from a Blend
therefore settle, while the #41 live-update chain is untouched: a user
USplits/VSplits edit still triggers onChanged's touch + recompute (which
IS this execute), and execute still touches the linked blends so they
refresh on the next doc.recompute().

Part 2 (the human's simplification): a new Patch defaults
ShowSubgrids = True. With it off, build_display fell back to the base
surface and the blend's band cell visibly overlaid it -- the auto-hide
had no effect. On by default, the patch draws its non-hidden subgrid
cells and the band the blend covers is simply absent.

Fixtures are built in memory from the ops layer (create_edge /
create_patch / create_blend_by_edge) -- no document is ever opened from
Resources/Test_files, so the user's open example docs are untouched.
"""

import FreeCAD
import Part

Vector = FreeCAD.Vector


# ---- fixtures -----------------------------------------------------------

def _edge(doc, key, pts):
    """One 4-pole Edge from 4 points, through the ops layer."""
    from SilkWorkflowOps import create_edge
    sk = doc.addObject("Sketcher::SketchObject", key)
    for j in range(3):
        sk.addGeometry(Part.LineSegment(Vector(*pts[j]), Vector(*pts[j + 1])))
    doc.recompute()
    return create_edge(sk, name=key)


def _build_two_patch_pair(doc):
    """Two quad Patches sharing ONE Edge object (the seam), so
    create_blend_by_edge's identity-only seam resolution succeeds.

    Both panels are y-banded: PA covers y in [-50, 0], PB covers
    y in [0, 50], and the shared seam SA2 runs along x at y = 0 with a
    gently rising z -- a clean, non-degenerate shared boundary.
    Returns (pa, pb, shared_edge).
    """
    from SilkWorkflowOps import create_patch
    sa0 = _edge(doc, "SA0", [(0, -50, 0), (16.7, -50, 0),
                             (33.3, -50, 0), (50, -50, 0)])
    sa1 = _edge(doc, "SA1", [(50, -50, 0), (50, -33.3, 3.3),
                             (50, -16.7, 6.7), (50, 0, 10)])
    sa2 = _edge(doc, "SA2", [(50, 0, 10), (33.3, 0, 9),
                             (16.7, 0, 8), (0, 0, 10)])
    sa3 = _edge(doc, "SA3", [(0, 0, 10), (0, -16.7, 6.7),
                             (0, -33.3, 3.3), (0, -50, 0)])
    sb1 = _edge(doc, "SB1", [(50, 0, 10), (50, 16.7, 13.3),
                             (50, 33.3, 16.7), (50, 50, 20)])
    sb2 = _edge(doc, "SB2", [(50, 50, 20), (33.3, 50, 20),
                             (16.7, 50, 20), (0, 50, 20)])
    sb3 = _edge(doc, "SB3", [(0, 50, 20), (0, 33.3, 20),
                             (0, 16.7, 20), (0, 0, 10)])
    pa = create_patch([sa0, sa1, sa2, sa3], name="PA")
    pb = create_patch([sa2, sb1, sb2, sb3], name="PB")
    return pa, pb, sa2


def _silk_objects(doc):
    """Every Patch / Blend in the document."""
    return [o for o in doc.Objects
            if getattr(o, "object_type", "") in ("Patch", "Blend")]


def _touched(doc):
    return [(o.Name, list(o.State)) for o in _silk_objects(doc)
            if "Touched" in o.State]


# ---- test 1: a settled document has no Touched object -------------------

def test_blend_leaves_no_touched_patch(doc):
    """After create_blend_by_edge + doc.recompute() neither covered Patch
    nor the Blend is left Touched, and a second recompute changes
    nothing. This is the #59 regression test: before the fix PA/PB were
    ['Touched'] forever while the Blend was Up-to-date."""
    errors, checks = [], []
    from SilkWorkflowOps import create_blend_by_edge
    pa, pb, seam = _build_two_patch_pair(doc)
    if _touched(doc):
        errors.append("patches already dirty before the blend: %s"
                      % _touched(doc))
    blend = create_blend_by_edge(seam)
    if blend is None:
        return {"pass": False, "errors": ["create_blend_by_edge refused"],
                "checks": checks}
    doc.recompute()
    left = _touched(doc)
    if left:
        errors.append("after create_blend_by_edge + recompute, still "
                      "Touched: %s" % left)
    else:
        checks.append("after create_blend_by_edge + doc.recompute(): "
                      "%d Patch/Blend objects, none Touched"
                      % len(_silk_objects(doc)))
    settled = sorted((o.Name, tuple(o.State)) for o in _silk_objects(doc))
    for _ in range(3):
        doc.recompute()
        again = _touched(doc)
        if again:
            errors.append("re-recomputing re-dirtied: %s" % again)
        states = sorted((o.Name, tuple(o.State)) for o in _silk_objects(doc))
        if settled != states:
            errors.append("state drift over repeated recomputes: %s -> %s"
                          % (settled, states))
        settled = states
    checks.append("3 further recomputes: stable, no re-dirtying")
    return {"pass": not errors, "errors": errors, "checks": checks}


# ---- test 2: the #41 live-update chain survives the fix -----------------

def test_user_split_edit_still_refreshes_blend(doc):
    """The fix must NOT disable the #41 live-update chain: a user-style
    split assignment (what the property editor does) still recomputes
    the Patch immediately AND still refreshes the linked Blend.

    The perpendicular axis of PA is swept: changing PA.USplits moves
    PA's band-cell indexing, so the blend's 24 poles must change and
    the oracle stay green. `obj.X = [...]` + recompute is the headless
    equivalent of the property-editor round trip."""
    errors, checks = [], []
    from SilkWorkflowOps import create_blend_by_edge
    from SilkChecks import check_blend, check_patch
    pa, pb, seam = _build_two_patch_pair(doc)
    blend = create_blend_by_edge(seam)
    doc.recompute()

    base_poles = [tuple(p) for p in blend.Poles]
    base_area = blend.Shape.Area
    if len(base_poles) != 24:
        return {"pass": False,
                "errors": ["blend has %d poles (expect 24)"
                           % len(base_poles)], "checks": checks}

    # a user edit on the axis PARALLEL to the seam. PA's seam runs along
    # U (the blend wrote its band split onto VSplits), so USplits is the
    # seam-parallel axis and controls the band's cell COUNT -- per #33
    # only the corner-exclusion values 0.1/0.9 keep it a single cell
    # (see Tests.test_mutation_unified.SEAM_AXIS_SAFE).
    n_before = len(pa.Proxy._subgrids)
    pa.USplits = [0.9]
    doc.recompute()

    n_cells = len(pa.Proxy._subgrids)
    if n_cells != 2 * n_before:
        errors.append("pa.USplits=[0.9] produced %d subgrids, expected "
                      "%d (one more U interval)" % (n_cells, 2 * n_before))
    new_poles = [tuple(p) for p in blend.Poles]
    if new_poles == base_poles:
        errors.append("blend poles did NOT change after the user's "
                      "split edit -- the live-update chain is broken")
    else:
        dev = max((Vector(*a) - Vector(*b)).Length
                  for a, b in zip(base_poles, new_poles))
        checks.append("pa.USplits=[0.9] refreshed the blend: 24 poles "
                      "moved, max dev %.4f mm" % dev)
    if abs(blend.Shape.Area - base_area) > 1e-6:
        checks.append("blend Shape rebuilt: area %.3f -> %.3f"
                      % (base_area, blend.Shape.Area))
    else:
        errors.append("blend Shape did not change after the split edit")

    for obj, edges, tag in ((pa, list(pa.Edges), "pa"), (pb, list(pb.Edges),
                                                          "pb")):
        bad = [(n, d) for n, ok, d in check_patch(obj, edges) if not ok]
        if bad:
            errors.append("after split edit, %s oracle not green: %s"
                          % (tag, bad))
    bad = [(n, d) for n, ok, d in check_blend(blend, pa, pb) if not ok]
    if bad:
        errors.append("after split edit, blend oracle not green: %s" % bad)
    else:
        checks.append("check_patch + check_blend green after the edit")

    # the document still settles after a user edit (the fix is not just
    # "purge everything at any cost")
    if _touched(doc):
        errors.append("document dirty after the user split edit: %s"
                      % _touched(doc))
    else:
        checks.append("document settles after the user split edit")
    return {"pass": not errors, "errors": errors, "checks": checks}


# ---- test 3: the touch guard does not block the onChanged recompute ----

def test_headless_property_edit_recomputes_immediately(doc):
    """onChanged must still recompute the Patch on a user split write,
    WITHOUT a follow-up doc.recompute() -- that immediate rebuild is
    what the property editor relies on. The guard added for #59 must not
    turn the immediate recompute into a no-op."""
    errors, checks = [], []
    from Tests.test_patch_unified import _make_loop_edges
    from SilkWorkflowOps import create_patch
    edges = _make_loop_edges(doc)
    p = create_patch(edges, name="P1")
    doc.recompute()
    n0 = len(p.Proxy._subgrids)
    legs0 = len(p.Legs)

    p.USplits = [0.5]        # onChanged -> touch + recompute, no doc.recompute
    n1 = len(p.Proxy._subgrids)
    if n1 != 2:
        errors.append("USplits write did not recompute: %d subgrids "
                      "(expected 2), no doc.recompute() called"
                      % n1)
    elif n1 == n0:
        errors.append("subgrid count unchanged")
    else:
        checks.append("USplits write recomputed the patch immediately: "
                      "%d -> %d subgrids, legs %d -> %d"
                      % (n0, n1, legs0, len(p.Legs)))

    # and the object settles on the next doc.recompute (a bare property
    # write always leaves the generic Touched bit set -- that is
    # FreeCAD's property machinery, not Silk's)
    doc.recompute()
    if "Touched" in p.State:
        errors.append("patch left Touched after the settle recompute: %s"
                      % list(p.State))
    else:
        checks.append("patch settles on the next doc.recompute")

    p.VSplits = [0.25, 0.75]
    if len(p.Proxy._subgrids) != 6:
        errors.append("VSplits write did not recompute: %d subgrids "
                      "(expect 6)" % len(p.Proxy._subgrids))
    else:
        checks.append("VSplits write recomputed immediately: 6 subgrids")
    return {"pass": not errors, "errors": errors, "checks": checks}


# ---- test 4: ShowSubgrids defaults on, and the band really auto-hides --

def test_showsubgrids_default_and_band_autohide(doc):
    """Part 2: a freshly created Patch has ShowSubgrids == True (the
    human's simplification -- subgrids always on by default), and
    turning it OFF is still honoured (the default, not a lock).

    Then the visual claim: with the default on, the patch's display
    Shape carries one face per NON-hidden subgrid cell, so the cell the
    blend's band covers is simply absent -- the strip no longer overlays
    the base surface. With ShowSubgrids off, build_display falls back to
    the single base-surface face and the strip DOES overlay it (the old,
    visually broken behaviour), which is exactly why the default flipped.
    """
    errors, checks = [], []
    from SilkWorkflowOps import create_blend_by_edge
    pa, pb, seam = _build_two_patch_pair(doc)
    if not pa.ShowSubgrids:
        errors.append("new Patch defaults ShowSubgrids=%r, expect True"
                      % pa.ShowSubgrids)
    else:
        checks.append("fresh Patch defaults ShowSubgrids=True")
    if not pb.ShowSubgrids:
        errors.append("new Patch PB defaults ShowSubgrids=%r, expect True"
                      % pb.ShowSubgrids)

    blend = create_blend_by_edge(seam)
    doc.recompute()

    for tag, p in (("PA", pa), ("PB", pb)):
        hidden = list(getattr(p, "_HiddenSubgridIdxs", []) or [])
        n_cells = len(p.Proxy._subsurfaces)
        n_faces = sum(1 for s in p.Shape.Solids) or len(p.Shape.Faces)
        if not hidden:
            errors.append("%s: blend did not register a hidden band cell"
                          % tag)
            continue
        # surface faces only (the grid legs add wire edges, not faces)
        n_sub_faces = n_cells - len(hidden)
        if n_sub_faces != n_faces:
            errors.append("%s: %d subgrid cells - %d hidden = %d "
                          "expected visible faces, Shape carries %d"
                          % (tag, n_cells, len(hidden), n_sub_faces,
                             n_faces))
        else:
            checks.append("%s: %d subgrid cells, %d hidden by the blend, "
                          "%d faces drawn -- the band is absent from the "
                          "patch display"
                          % (tag, n_cells, len(hidden), n_faces))

    # toggling the default OFF is still the user's call
    pa.ShowSubgrids = False
    doc.recompute()
    if len(pa.Shape.Faces) != 1:
        errors.append("ShowSubgrids=False should fall back to the single "
                      "base-surface face, got %d" % len(pa.Shape.Faces))
    else:
        checks.append("ShowSubgrids=False honoured: 1 base-surface face "
                      "(the pre-#59 overlay behaviour, now opt-in)")
    return {"pass": not errors, "errors": errors, "checks": checks}


ALL_TESTS = [
    test_blend_leaves_no_touched_patch,
    test_user_split_edit_still_refreshes_blend,
    test_headless_property_edit_recomputes_immediately,
    test_showsubgrids_default_and_band_autohide,
]
