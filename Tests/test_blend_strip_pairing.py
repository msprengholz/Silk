"""BlendStrip seam-row pairing + direction (#30, #31) — one build, both
fold regressions.

`test_blend_direction.py` (#31) and `test_blend_pairing.py` (#30) were two
single-test modules that each built `Tests.corner_model.build_corner_pair`
to ask one question about the SAME strip, B12. They are the two halves of
one story — how the extracted seam rows are paired and in which direction
the left row is read — so they live here as one build with both
assertions, rather than two builds of the same fixture. Every assertion is
unchanged; only the redundant build is gone.

#31 direction: `blend_poly_2x4_1x6` needs poles_0 OUTER->SHARED and
poles_1 SHARED->OUTER. The extracted strip row always runs seam-to-outer,
so it is reversed only when the seam sits at parametric 0 (ss=0). B12's
E_s12 is V3 (ss=1) on Patch44 and V0 (ss=0) on Patch001 — the mixed case
the all-ss=0 ground-truth fixture could not see. Pre-fix, the left row was
reversed unconditionally and B3_surface_valid failed (9 flipped normals +
self-intersections).

#30 pairing: B12's seam is identity-aligned (corner 0->0, 3->3). Pre-fix
the middle rows defaulted to ri=3-li, pairing left row v=1 with right row
u=2 — a 180-degree fold (worst-neighbor normal dot -0.998). The fix infers
identity middle-row pairing from the two corner-pair matches. Expected with
identity pairing (right side runs B=(y=0) to C=(y=50)): row 1 right outer
pole p5.y = 16.67, row 2 p5.y = 33.33.
"""

import FreeCAD

import SilkChecks
import Tests.corner_model as cm


def test_seam_strip_pairs_and_directs_without_a_fold(doc):
    """B12 (mixed ss) passes B1-B4 AND its middle rows pair by identity."""
    model = cm.build_corner_pair(doc)
    b12 = model["strip"]
    pa = model["patches"]["Patch44"]
    pb = model["patches"]["Patch001"]

    errors = []
    checks = []

    # #31 — the mixed-ss strip must fill without a fold.
    results = SilkChecks.check_blend(b12, pa, pb)
    for name, ok, detail in results:
        checks.append("%s: %s" % (name, "OK" if ok else "FAIL " + detail))
        if not ok:
            errors.append("%s: %s" % (name, detail))

    # #30 — the middle seam rows pair by identity, not by reversal.
    poles = [FreeCAD.Vector(*v) for v in b12.Poles]
    for li in (1, 2):
        p5 = poles[li * 6 + 5]
        want_y = (li / 3.0) * 50.0
        checks.append("row%d p5.y=%.2f (want %.2f)" % (li, p5.y, want_y))
        if abs(p5.y - want_y) > 0.05:
            errors.append(
                "row %d right outer pole y=%.3f, want %.2f (reversed pairing?)"
                % (li, p5.y, want_y))

    return {"pass": not errors, "errors": errors, "checks": checks}


ALL_TESTS = [test_seam_strip_pairs_and_directs_without_a_fold]
