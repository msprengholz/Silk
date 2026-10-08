"""
#30 BlendStrip seam-row pairing — identity-alignment regression.

B12's seam is identity-aligned (corner 0->0, 3->3). Pre-fix, the
middle rows defaulted to ri=3-li, pairing left row v=1 with right row
u=2 — a 180-degree fold (worst-neighbor normal dot -0.998).

The #30 fix infers alignment from the two corner-pair matches: identity
endpoints (0->0, 3->3) imply identity middle-row pairing (1->1, 2->2).

Expected with identity pairing (right side runs B=(y=0) to C=(y=50)):
    row 1 right outer pole p5.y = 16.67
    row 2 right outer pole p5.y = 33.33
"""

import FreeCAD

import Tests.corner_model as cm


def test_identity_seam_middle_row_pairing(doc):
    """Middle seam rows must pair by identity, not by reversal."""
    model = cm.build_corner_pair(doc)
    b12 = model["strip"]
    poles = [FreeCAD.Vector(*v) for v in b12.Poles]

    errors = []
    for li in (1, 2):
        p5 = poles[li * 6 + 5]
        want_y = (li / 3.0) * 50.0
        if abs(p5.y - want_y) > 0.05:
            errors.append(
                "row %d right outer pole y=%.3f, want %.2f (reversed pairing?)"
                % (li, p5.y, want_y))

    return {
        "pass": not errors,
        "errors": errors,
        "checks": [
            "row1 p5.y=%.2f (want 16.67)" % poles[7].y,
            "row2 p5.y=%.2f (want 33.33)" % poles[13].y,
        ],
    }


ALL_TESTS = [test_identity_seam_middle_row_pairing]
