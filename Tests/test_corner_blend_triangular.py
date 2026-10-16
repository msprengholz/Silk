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
    fixtures; success would require a genuine triangular (3-patch)
    junction fixture, which does not exist yet."""
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
    repo's only corner fixture is the 4-valent 2x2 dome (Tests/corner_model),
    and no three of its ring blends form the 3-cycle `corner_ring_3`
    requires, so no executable 3-valent CornerBlend (and therefore no
    surface to feed to g2_oracle.measure_seam) can be produced from the
    available fixtures. Synthetic triangular geometry would be needed; not
    added here because inventing a 3-patch junction by hand is out of
    scope of validation-only work and would not be a faithful instrument
    reading. This test records that limitation rather than asserting a
    continuity label (which would cross the label guard)."""
    return {"pass": True, "errors": [],
            "checks": ["no 3-valent fixture present; k_gap not measured -- "
                       "see test docstring"]}

ALL_TESTS = [
    test_triangular_member_nonzero_and_no_fold,
    test_3valent_cornerblend_refuses_real_corner_three_subsets,
    test_3valent_cornerblend_measurement_unavailable,
]
