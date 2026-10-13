"""
Blend stage (ticket #20): create_blend op + check_blend oracle (B1-B4).

B1 C0: blend row endpoints sit on the patches' strip-curve endpoints
      (both inner boundaries, all 4 rows, 1e-6)
B2 C1: blend row endpoint tangents match the strip-curve tangents under
      the documented 2x tangent scale (1e-6)
B3:    blend surface valid + no self-intersection + normal field coherent
B4:    full 24-pole match against a provided reference (stored fixture
       blend in the ground-truth test; captured pre-corruption poles in
       the negative test)

Ground-truth test: rebuild the full 7-edge / 2-patch chain from the
fixture's sketches (curved geometry), create the blend, and match the
stored fixture BlendStrip's 24 poles at 1e-6.
"""

import FreeCAD
import os

Vector = FreeCAD.Vector

FIXTURE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..",
                       "Resources", "Test_files", "Silk_Workflow.FCStd")

GT_CHAIN_EDGES = [
    ("E_Top", ["Sketch007", "Sketch008"]),
    ("E_Left", ["Sketch005"]),
    ("E_BtmL", ["Sketch006"]),
    ("E_Shr", ["Sketch"]),
    ("E_BtmR", ["Sketch001"]),
    ("E_CurR", ["Sketch003", "Sketch004"]),
    ("E_TopR", ["Sketch002"]),
]


class _CaptureConsole:
    def __enter__(self):
        import FreeCAD
        self._orig = FreeCAD.Console.PrintError
        self.errors = []
        FreeCAD.Console.PrintError = lambda msg: (
            self.errors.append(msg), self._orig(msg))
        return self

    def __exit__(self, *args):
        FreeCAD.Console.PrintError = self._orig


def _build_gt_chain(doc, fixture_doc):
    """Rebuild all 7 fixture edges + both patches in the test doc.

    Returns (patch_a, patch_b, edges_by_name). `fixture_doc` must be open.
    """
    from Tests.test_patch_stage import _copy_fixture_edge
    from SilkWorkflowOps import create_patch

    edges_by_name = {}
    for edge_name, sketch_names in GT_CHAIN_EDGES:
        e = _copy_fixture_edge(doc, fixture_doc, edge_name, sketch_names)
        edges_by_name.setdefault(edge_name, e)

    g = edges_by_name
    patch_a = create_patch(
        [g["E_Top"], g["E_Left"], g["E_BtmL"], g["E_Shr"]],
        name="PatchA")
    patch_b = create_patch(
        [g["E_Shr"], g["E_BtmR"], g["E_CurR"], g["E_TopR"]],
        name="PatchB")
    return patch_a, patch_b, edges_by_name


def test_create_blend_ground_truth(doc):
    from SilkWorkflowOps import create_blend
    from SilkChecks import check_blend

    fixture = FreeCAD.openDocument(FIXTURE)
    FreeCAD.setActiveDocument(doc.Name)  # openDocument activates the fixture
    try:
        patch_a, patch_b, _ = _build_gt_chain(doc, fixture)
        with _CaptureConsole() as cap:
            blend = create_blend(patch_a, patch_b, name="BlendStrip")

        stored = fixture.BlendStrip.Poles
        if len(stored) != 24:
            errors = [f"fixture blend has {len(stored)} poles, want 24"]
            return {"pass": False, "errors": errors, "checks": []}
        results = check_blend(blend, patch_a, patch_b,
                              reference_poles=stored)
        by = {name: (ok, detail) for name, ok, detail in results}

        errors = []
        errors += [f"console error: {e}" for e in cap.errors]
        if blend.Poles is None or len(blend.Poles) != 24:
            errors.append(f"expected 24 poles, got "
                          f"{0 if blend.Poles is None else len(blend.Poles)}")
        else:
            for name, ok, _ in results:
                if not ok:
                    errors.append(f"check failed: {name} -- {by[name][1]}")
    finally:
        FreeCAD.closeDocument(fixture.Name)
        FreeCAD.setActiveDocument(doc.Name)

    return {"pass": not errors, "errors": errors,
            "checks": [f"{n}: {'ok' if ok else 'FAIL'} ({d})"
                       for n, ok, d in results]}


def test_unblend_restores_the_patches(doc):
    """#70: deleting a FRESHLY created Blend must give both patches their
    band cells back.

    The hidden-cell set is re-derived by each blend's execute from the
    blends alive at that moment, but a deleted blend touches nothing and
    recompute() only walks touched objects -- so without a delete hook
    both patches keep the band hole forever.

    **This test exists because the fix shipped green while broken.**
    `Blend` subclasses `BlendStrip` but overrode `__init__` without
    calling super(), so only `BlendStrip.__init__` installed the
    one-shot delete observer. A freshly created blend therefore had NO
    observer and unblend did nothing; a *restored* one did get it via
    the inherited `onDocumentRestored`. Building the blend fresh -- the
    ordinary path, and the one the panel uses -- is precisely what
    exercises the regression.
    """
    from SilkWorkflowOps import create_blend
    from Tests.test_patch_stage import _copy_fixture_edge  # noqa: F401

    fixture = FreeCAD.openDocument(FIXTURE)
    FreeCAD.setActiveDocument(doc.Name)
    errors, checks = [], []
    try:
        patch_a, patch_b, _ = _build_gt_chain(doc, fixture)
        blend = create_blend(patch_a, patch_b, name="BlendStrip")
        doc.recompute()

        def hidden(p):
            return list(getattr(p, "_HiddenSubgridIdxs", []) or [])

        before_faces = (len(patch_a.Shape.Faces), len(patch_b.Shape.Faces))
        checks.append("blended: hidden=%s faces=%d"
                      % ([hidden(patch_a), hidden(patch_b)], sum(before_faces)))
        if not hidden(patch_a) or not hidden(patch_b):
            errors.append("precondition: a blended patch should have its "
                          "band cells hidden; got %s"
                          % ([hidden(patch_a), hidden(patch_b)],))
        if blend.Proxy._delete_watcher is None:
            errors.append("a FRESHLY created Blend has no delete watcher "
                          "-- unblend cannot work at all")

        doc.removeObject(blend.Name)
        doc.recompute()

        after_faces = (len(patch_a.Shape.Faces), len(patch_b.Shape.Faces))
        checks.append("unblended: hidden=%s faces=%d"
                      % ([hidden(patch_a), hidden(patch_b)], sum(after_faces)))
        if hidden(patch_a) or hidden(patch_b):
            errors.append("after deleting the blend the patches still hide "
                          "their band cells: %s -- a hole is left behind"
                          % ([hidden(patch_a), hidden(patch_b)],))
        if sum(after_faces) <= sum(before_faces):
            errors.append("the band cell did not come back: faces %d -> %d"
                          % (sum(before_faces), sum(after_faces)))

        # the user's width must survive the unblend (it is the patch's own
        # split, #64) -- only the *cells* are given back
        splits_a = (list(patch_a.USplits), list(patch_a.VSplits))
        splits_b = (list(patch_b.USplits), list(patch_b.VSplits))
        checks.append("splits survive: %s %s" % (splits_a, splits_b))
        if not (splits_a[0] or splits_a[1] or splits_b[0] or splits_b[1]):
            errors.append("unblend discarded the band splits -- the user's "
                          "chosen width would be lost")

        # and re-blending on the same seam must still build
        again = create_blend(patch_a, patch_b, name="BlendAgain")
        doc.recompute()
        checks.append("re-blend: poles=%d null=%s"
                      % (len(again.Poles or []), again.Shape.isNull()))
        if not list(again.Poles or []) or again.Shape.isNull():
            errors.append("re-blending after an unblend produced nothing")
    finally:
        FreeCAD.closeDocument(fixture.Name)
        FreeCAD.setActiveDocument(doc.Name)

    return {"pass": not errors, "errors": errors, "checks": checks}


def _blend_corrupted(doc, fixture, pole_idx, delta):
    """Build the GT blend, then corrupt one stored pole by `delta`."""
    from SilkWorkflowOps import create_blend
    patch_a, patch_b, _ = _build_gt_chain(doc, fixture)
    blend = create_blend(patch_a, patch_b, name="BlendStrip")
    poles = list(blend.Poles)
    poles[pole_idx] = poles[pole_idx] + delta
    blend.Poles = poles
    return blend, patch_a, patch_b


def test_oracle_flags_seam_offset(doc):
    """B1 must fail: a row's left endpoint (C0 seam pole) shifted 0.5."""
    from SilkChecks import check_blend

    fixture = FreeCAD.openDocument(FIXTURE)
    FreeCAD.setActiveDocument(doc.Name)  # openDocument activates the fixture
    try:
        blend, pa, pb = _blend_corrupted(doc, fixture, 0, Vector(0.5, 0, 0))
        results = check_blend(blend, pa, pb)
        failed = [n for n, ok, _ in results if not ok]
        if any(n.startswith("B1") for n in failed):
            return {"pass": True, "errors": [],
                    "checks": [f"{n}: {'ok' if ok else 'FAIL'}"
                               for n, ok, _ in results]}
        return {"pass": False,
                "errors": [f"seam offset: expected B1 failure, got {failed}"],
                "checks": [f"{n}: {'ok' if ok else 'FAIL'}"
                           for n, ok, _ in results]}
    finally:
        FreeCAD.closeDocument(fixture.Name)
        FreeCAD.setActiveDocument(doc.Name)


def test_oracle_flags_tangent_break(doc):
    """B2 must fail: a row's first tangent pole shifted 0.5 (B1 stays green)."""
    from SilkChecks import check_blend

    fixture = FreeCAD.openDocument(FIXTURE)
    FreeCAD.setActiveDocument(doc.Name)  # openDocument activates the fixture
    try:
        blend, pa, pb = _blend_corrupted(doc, fixture, 1, Vector(0, 0.5, 0))
        results = check_blend(blend, pa, pb)
        failed = [n for n, ok, _ in results if not ok]
        if any(n.startswith("B2") for n in failed):
            return {"pass": True, "errors": [],
                    "checks": [f"{n}: {'ok' if ok else 'FAIL'}"
                               for n, ok, _ in results]}
        return {"pass": False,
                "errors": [f"tangent break: expected B2 failure, got {failed}"],
                "checks": [f"{n}: {'ok' if ok else 'FAIL'}"
                           for n, ok, _ in results]}
    finally:
        FreeCAD.closeDocument(fixture.Name)
        FreeCAD.setActiveDocument(doc.Name)


def test_oracle_flags_interior_pole(doc):
    """B4 must fail: an interior pole shifted 0.5, reference = clean poles."""
    from SilkChecks import check_blend

    fixture = FreeCAD.openDocument(FIXTURE)
    FreeCAD.setActiveDocument(doc.Name)  # openDocument activates the fixture
    try:
        blend, pa, pb = _blend_corrupted(doc, fixture, 14, Vector(0, 0, 0.5))
        # reference = stored fixture blend poles (plain vectors, cross-doc ok)
        stored = fixture.BlendStrip.Poles
        results = check_blend(blend, pa, pb, reference_poles=stored)
        failed = [n for n, ok, _ in results if not ok]
        if "B4_pole_match" in failed:
            return {"pass": True, "errors": [],
                    "checks": [f"{n}: {'ok' if ok else 'FAIL'}"
                               for n, ok, _ in results]}
        return {"pass": False,
                "errors": [f"interior pole: expected B4 failure, got {failed}"],
                "checks": [f"{n}: {'ok' if ok else 'FAIL'}"
                           for n, ok, _ in results]}
    finally:
        FreeCAD.closeDocument(fixture.Name)
        FreeCAD.setActiveDocument(doc.Name)


ALL_TESTS = [
    test_create_blend_ground_truth,
    test_unblend_restores_the_patches,
    test_oracle_flags_seam_offset,
    test_oracle_flags_tangent_break,
    test_oracle_flags_interior_pole,
]
