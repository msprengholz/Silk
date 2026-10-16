"""Unit tests for the triangular 4th member of a 3-valent hard corner.

Covers the member machinery itself -- `control_grid64_3_1` (the 4x4 corner
cell -> 6x4 triangular member) and the degeneracy rule in `pair_common`
that lets the member's collapsed end row match the ring's shared corner.
The end-to-end positive build lives on the cube-corner fixture:
Tests/test_cube_corner_3valent.py (build contract + raw seam measurement).
"""
import math

import FreeCAD

from SilkMachinery import CORNER_IDX, control_grid64_3_1, pair_common


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


# ---------------------------------------------------------------------------
# the degeneracy rule of pair_common
# ---------------------------------------------------------------------------
#
# A synthetic 24-pole grid only has to get its CORNER_IDX poles right for
# pair_common; the rest of the net can be a repeated placeholder.

def _grid(corners):
    """A 24-pole grid carrying `corners` at CORNER_IDX (0, 5, 18, 23)."""
    poles = [FreeCAD.Vector(7.0, 7.0, 7.0) for _ in range(24)]
    for k, idx in enumerate(CORNER_IDX):
        poles[idx] = FreeCAD.Vector(*corners[k])
    return poles


P, Q, R, S, T, U = ((0, 0, 0), (1, 0, 0), (2, 0, 0), (3, 0, 0),
                    (4, 0, 0), (5, 0, 0))
A0, A1, A3 = ((-1, -1, -1), (-2, -2, -2), (-6, -6, -6))


def test_pair_common_collapsed_end_row_rule(doc):
    """The triangular member's collapsed end row presents TWO corner
    slots on one point; `pair_common` admits exactly that and returns the
    pairing the subgrid reader consumes -- (3, 2), or its mirror (2, 3)
    for a ring traversed the other way."""
    checks, errors = [], []

    # (3, 2): the neighbour's slot 3 meets the member's collapsed V3 row.
    a = _grid([P, Q, R, T])
    b = _grid([A0, A1, T, T])
    common, why = pair_common(a, b, 1e-9)
    if common == (3, 2):
        checks.append("collapsed V3 row on grid 1 -> (3, 2)")
    else:
        errors.append("collapsed V3 row on grid 1: got %r (%s)"
                      % (common, why))

    # (2, 3): only the mirror pairing is present (reversed traversal).
    a = _grid([P, Q, T, U])
    b = _grid([A0, A1, T, T])
    common, why = pair_common(a, b, 1e-9)
    if common == (2, 3):
        checks.append("mirror-only overlap -> (2, 3)")
    else:
        errors.append("mirror-only overlap: got %r (%s)" % (common, why))

    # (3, 2) with the collapsed row on grid 0 (the member as grid 0).
    a = _grid([P, Q, T, T])
    b = _grid([A0, A1, T, A3])
    common, why = pair_common(a, b, 1e-9)
    if common == (3, 2):
        checks.append("collapsed V3 row on grid 0 -> (3, 2)")
    else:
        errors.append("collapsed V3 row on grid 0: got %r (%s)"
                      % (common, why))

    # a single match is still returned untouched
    a = _grid([P, Q, R, S])
    b = _grid([A0, A1, R, A3])
    common, why = pair_common(a, b, 1e-9)
    if common == (2, 2):
        checks.append("single match -> (2, 2)")
    else:
        errors.append("single match: got %r (%s)" % (common, why))

    return {"pass": not errors, "errors": errors, "checks": checks}


def test_pair_common_refuses_ambiguous_multi_corner_overlaps(doc):
    """Multiple matches are refused unless they are one collapsed end row
    against one neighbour corner. Non-degenerate grids sharing >1 corner
    still refuse -- including when one of the candidate pairings is the
    ring-canonical (3, 2) -- and so do duplicate slots off a single row
    (an apex repeated across a COLUMN) and two facing collapsed rows."""
    tol = 1e-9
    checks, errors = [], []

    cases = [
        ("two distinct shared corners", _grid([P, Q, R, S]),
         _grid([P, A0, R, A1])),
        ("two distinct corners incl. the (3, 2) candidate",
         _grid([P, Q, R, S]), _grid([A0, A1, S, P])),
        ("identical non-degenerate grids", _grid([P, Q, R, S]),
         _grid([P, Q, R, S])),
        ("duplicate slots across a COLUMN (apex at 0 and 3)",
         _grid([P, Q, R, S]), _grid([P, A0, A1, P])),
        ("two facing collapsed end rows", _grid([P, Q, T, T]),
         _grid([A0, A1, T, T])),
    ]
    for label, a, b in cases:
        common, why = pair_common(a, b, tol)
        if common is None and why:
            checks.append("%s: refused (%s)" % (label, why))
        else:
            errors.append("%s: got %r (expected a named refusal)"
                          % (label, common))

    return {"pass": not errors, "errors": errors, "checks": checks}


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
    fixtures; the genuine 3-patch (cube corner) counterpart lives in
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


ALL_TESTS = [
    test_triangular_member_nonzero_and_no_fold,
    test_pair_common_collapsed_end_row_rule,
    test_pair_common_refuses_ambiguous_multi_corner_overlaps,
    test_3valent_cornerblend_refuses_real_corner_three_subsets,
]
