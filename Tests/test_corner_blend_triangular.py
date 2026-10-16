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


ALL_TESTS = [test_triangular_member_nonzero_and_no_fold]
