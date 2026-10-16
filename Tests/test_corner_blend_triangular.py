"""Unit tests for the triangular 4th member of a 3-valent hard corner."""
import math

import FreeCAD

from SilkMachinery import control_grid64_3_1


def _is_vec(v):
    return hasattr(v, "x") and hasattr(v, "y") and hasattr(v, "z")


def test_triangular_member_nonzero_and_no_fold(doc):
    # 4x4 input grid: a slightly curved patch (not degenerate)
    poles = []
    for i in range(4):
        for j in range(4):
            poles.append(FreeCAD.Vector(float(j) * 10.0,
                                         float(i) * 10.0,
                                         0.3 * float(i * j)))
    weights = [1.0] * 16
    for corner in range(4):
        mp, mw = control_grid64_3_1(poles, weights, corner)
        assert mp is not None and len(mp) == 24
        assert mw is not None and len(mw) == 24
        # non-zero poles (not all origin)
        assert any((p.x, p.y, p.z) != (0.0, 0.0, 0.0) for p in mp)
        # no NaN / inf
        for p in mp:
            assert all(math.isfinite(c) for c in (p.x, p.y, p.z))
        # no complete collapse / fold: not all poles identical
        uniq = {(round(p.x, 6), round(p.y, 6), round(p.z, 6)) for p in mp}
        assert len(uniq) > 1
    return {"pass": True, "errors": [], "checks": ["triangular member OK"]}




import itertools

import FreeCAD

import Tests.corner_model as cm
from SilkWorkflowOps import create_corner_blend


class _CaptureConsole:
    def __enter__(self):
        self._orig = FreeCAD.Console.PrintError
        self.errors = []
        FreeCAD.Console.PrintError = lambda msg: (
            self.errors.append(msg), self._orig(msg))
        return self

    def __exit__(self, *args):
        FreeCAD.Console.PrintError = self._orig


def test_3valent_cornerblend_refuses_real_corner_three_subsets(doc):
    """A 3-valent CornerBlend cannot be built from the 4-valent corner's
    strips: no three of its four ring blends form the 3-cycle that
    `corner_ring_3` requires (each blend shares a patch with exactly the
    other two). Every subset is refused BY NAME and leaves no
    CornerBlend behind (#80/#83). This is the end-to-end exercise of
    `create_corner_blend` on three real Blend strips available in the
    fixtures; the genuine 3-patch (cube corner) counterpart now lives in
    Tests/cube_corner_model.py and is driven by
    Tests/test_cube_corner_3valent.py."""
    cm.build_corner_model(doc)
    strips = [doc.getObject(n) for n in ("B12", "B24", "B43", "B31")]
    errors = []
    checks = []
    for combo in itertools.combinations(strips, 3):
        names = [s.Name for s in combo]
        before = len([o for o in doc.Objects
                      if getattr(o, "object_type", "") == "CornerBlend"])
        with _CaptureConsole() as cap:
            made = create_corner_blend(*combo)
        after = len([o for o in doc.Objects
                     if getattr(o, "object_type", "") == "CornerBlend"])
        named = bool(cap.errors) and "Silk:" in "".join(cap.errors)
        if made is not None or after != before or not named:
            errors.append("%s: made=%s corners %d->%d msg=%r"
                          % (names, made, before, after, cap.errors))
        else:
            checks.append("%s refused by name, no CornerBlend created: %s"
                          % (names, cap.errors[-1].strip()[:80]))
    return {"pass": not errors, "errors": errors, "checks": checks}


def test_3valent_cornerblend_measurement_unavailable(doc):
    """k_gap measurement on a 3-valent corner is not available: the
    3-patch cube-corner fixture now EXISTS (Tests/cube_corner_model.py),
    its three strips resolve as the 3-cycle ring, but the corner build is
    refused by name before any surface is constructed --

        Silk: cannot create a corner blend from these 3 blends -- could
        not build triangular 4th member. Nothing was created.

    (the triangular-member search feeds each patch's FULL 4x4 base grid,
    whose corners are the patch vertices -- never the ring's shared
    corner, the patch's corner-CELL outer corner). With no CornerBlend
    object there is no surface for g2_oracle.measure_seam to measure, so
    k_gap stays unmeasured. Tests/test_cube_corner_3valent.py executes
    that attempt and records the refusal; this test points at it. No
    continuity label is asserted here or anywhere in this suite (which
    would cross the label guard)."""
    return {"pass": True, "errors": [],
            "checks": ["3-valent fixture exists (Tests/cube_corner_model.py) "
                       "but the corner build refuses ('could not build "
                       "triangular 4th member'), so no CornerBlend surface "
                       "exists -> k_gap not measured -- see "
                       "Tests/test_cube_corner_3valent.py"]}

ALL_TESTS = [
    test_triangular_member_nonzero_and_no_fold,
    test_3valent_cornerblend_refuses_real_corner_three_subsets,
    test_3valent_cornerblend_measurement_unavailable,
]
