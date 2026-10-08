"""
#31 BlendStrip row orientation (seam-side ss) — fold regression.

blend_poly_2x4_1x6 requires poles_0 OUTER->SHARED and poles_1
SHARED->OUTER. The extracted strip row always runs seam-to-outer, so it
only needs reversal when the seam sits at parametric 0 (ss=0). The old
code reversed the left row unconditionally: correct for ss=0, but for
ss=1 (seam at parametric 1, edge types U1/V1) it flipped the row into
SHARED->OUTER, producing a 180-degree fold.

B12 in the corner pair is the mixed case: E_s12 is V3 (ss=1) on
Patch44 and V0 (ss=0) on Patch001 — both orientations exercised by one
strip. The ground-truth fixture only has ss=0/ss=0, which is why this
was invisible there.

Pre-fix: B3_surface_valid fails (9 flipped normals + self-intersections).
Post-fix: B1-B4 all green.
"""

import Tests.corner_model as cm
import SilkChecks


def test_mixed_ss_seam_blend_no_fold(doc):
    """A strip with one ss=0 and one ss=1 side must pass B1-B4."""
    model = cm.build_corner_pair(doc)
    b12 = model["strip"]
    pa = model["patches"]["Patch44"]
    pb = model["patches"]["Patch001"]

    results = SilkChecks.check_blend(b12, pa, pb)
    failed = [(n, d) for (n, ok, d) in results if not ok]

    return {
        "pass": not failed,
        "errors": ["%s: %s" % (n, d) for n, d in failed],
        "checks": ["%s: %s" % (n, "OK" if ok else "FAIL " + d)
                   for n, ok, d in results],
    }


ALL_TESTS = [test_mixed_ss_seam_blend_no_fold]
