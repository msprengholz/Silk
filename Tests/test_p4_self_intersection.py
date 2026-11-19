"""Known-answer calibration for P4's exact-surface self-intersection test.

MeshPart's boolean depends on tessellation: 0.5 mm false-positives on valid
pointed patches, 0.1/0.01 do so on others, and 0.5 misses a real crossed
net. P4 now samples the EXACT Part surface. The 12 valid flat/corner triple
orderings are the known-good controls; a crossed 4x4 net is the known-bad
control. Raw matrix: Resources/Test_files/_inspect/cut_list_attempts/
09_p4_mesh_matrix.txt. No continuity label is asserted.
"""

import itertools

import FreeCAD
import Part

import SilkChecks as C
import SilkWorkflowOps as O
import test_patch_stage as PS
import test_pointed_corner_triple as CT

BAD_POLES = (
    (0.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 2.0, 0.0), (0.0, 3.0, 0.0),
    (1.0, 0.0, 0.0), (-1.403, -2.865, -0.416), (-2.295, -3.268, -0.394),
    (1.0, 3.0, 0.0),
    (2.0, 0.0, 0.0), (6.098, 4.805, 1.061), (-1.559, 1.903, -0.893),
    (2.0, 3.0, 0.0),
    (3.0, 0.0, 0.0), (3.0, 1.0, 0.0), (3.0, 2.0, 0.0), (3.0, 3.0, 0.0),
)


def _bad_face():
    surf = Part.BSplineSurface()
    surf.increaseDegree(3, 3)
    for knot, mult in ((0.0, 4), (1.0, 4)):
        surf.insertUKnot(knot, mult, 1e-7)
        surf.insertVKnot(knot, mult, 1e-7)
    for r in range(4):
        for c in range(4):
            surf.setPole(c + 1, r + 1, FreeCAD.Vector(*BAD_POLES[r * 4 + c]))
    return max(surf.toShape().Faces, key=lambda f: f.Area)


def test_p4_self_intersection_known_answers(doc):
    from Tests.mcp_harness import check
    errors, checks = [], []
    d = FreeCAD.newDocument("_p4_calibration")
    try:
        readings = []
        for label, edges in (("flat", PS._make_triangle_edges(d)),
                             ("corner", CT._make_corner_triple_edges(d))):
            for perm in itertools.permutations(range(3)):
                code = "".join(str(i) for i in perm)
                patch = O.create_patch([edges[i] for i in perm],
                                       name="P4_" + label + code)
                d.recompute()
                face = max(patch.Shape.Faces, key=lambda f: f.Area)
                hits, eps, closest = C.sampled_self_intersections(face)
                readings.append((label + code, hits, closest, eps))
                checks.append("%s: hits %d, closest %.6g mm, bar %.6g mm"
                              % (label + code, hits, closest, eps))
                check(hits == 0,
                      "valid %s ordering reported %d self-intersections"
                      % (label + code, hits), errors)
        bad_hits, bad_eps, bad_closest = C.sampled_self_intersections(
            _bad_face())
        checks.append("known-bad crossed net: hits %d, closest %.6g mm, "
                      "bar %.6g mm" % (bad_hits, bad_closest, bad_eps))
        check(bad_hits > 0,
              "the known-bad crossed net was not detected at the calibrated "
              "sampling bar", errors)
        check(len(readings) == 12,
              "the valid control set has %d readings, not 12" % len(readings),
              errors)
    finally:
        FreeCAD.closeDocument(d.Name)
    return {"pass": not errors, "errors": errors, "checks": checks}


ALL_TESTS = [test_p4_self_intersection_known_answers]
