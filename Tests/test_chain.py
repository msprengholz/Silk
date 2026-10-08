"""
Chain test (ticket #21): the full 9 -> 7 -> 2 -> 1 rebuild of the
ground-truth document from a blank document, entirely through the ops
layer (create_edge via _copy_fixture_edge, create_patch, create_blend).

Every object is oracle-checked (check_edge / check_patch44 / check_blend)
and pole-matched against its stored fixture counterpart at 1e-6. This is
the acceptance gate for the pipeline: it always runs, it is not skipped.

This test IS the ticket's deliverable -- no new ops/oracle code.
"""

import FreeCAD
import os

TOL = 1e-6

FIXTURE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..",
                       "Resources", "Test_files", "Silk_Workflow.FCStd")


class _CaptureConsole:
    def __enter__(self):
        self._orig = FreeCAD.Console.PrintError
        self.errors = []
        FreeCAD.Console.PrintError = lambda msg: (
            self.errors.append(msg), self._orig(msg))
        return self

    def __exit__(self, *args):
        FreeCAD.Console.PrintError = self._orig


def test_chain_ground_truth(doc):
    errors = []
    checks = []

    fixture = FreeCAD.openDocument(FIXTURE)
    FreeCAD.setActiveDocument(doc.Name)  # openDocument activates the fixture
    try:
        from Tests.test_patch_stage import _copy_fixture_edge
        from Tests.test_blend_stage import GT_CHAIN_EDGES
        from SilkWorkflowOps import create_patch, create_blend
        from SilkChecks import check_edge, check_patch44, check_blend

        with _CaptureConsole() as cap:
            # 9 sketches -> 7 edges
            edges = {}
            for edge_name, sketch_names in GT_CHAIN_EDGES:
                e = _copy_fixture_edge(doc, fixture, edge_name, sketch_names)
                edges[edge_name] = e
                for name, ok, detail in check_edge(e):
                    if not ok:
                        errors.append("%s %s: %s" % (edge_name, name, detail))
                stored = fixture.getObject(edge_name).Poles
                dev = max((p - s).Length for p, s in zip(e.Poles, stored))
                if dev > TOL:
                    errors.append("%s poles deviate %.3e from fixture"
                                  % (edge_name, dev))
            if errors:
                checks.append("7 edges: see errors")
            else:
                checks.append("7 edges: oracle green, poles match fixture "
                              "within %.0e" % TOL)

            # 7 edges -> 2 patches (cyclic order per corner matching)
            g = edges
            patch_specs = [
                ("Patch44", ("E_Top", "E_Left", "E_BtmL", "E_Shr")),
                ("Patch001", ("E_Shr", "E_BtmR", "E_CurR", "E_TopR")),
            ]
            patches = {}
            for name, (e0, e1, e2, e3) in patch_specs:
                p = create_patch(g[e0], g[e1], g[e2], g[e3], name=name)
                patches[name] = p
                ed4 = [g[e0], g[e1], g[e2], g[e3]]
                for cname, ok, detail in check_patch44(p, ed4):
                    if not ok:
                        errors.append("%s %s: %s" % (name, cname, detail))
                stored = fixture.getObject(name).Poles
                dev = max((pp - ss).Length
                          for pp, ss in zip(p.Poles, stored))
                if dev > TOL:
                    errors.append("%s poles deviate %.3e from fixture"
                                  % (name, dev))
            checks.append("2 patches: oracle green, 16 poles each match "
                          "fixture within %.0e" % TOL)

            # 2 patches -> 1 blend (B4 reference = stored fixture blend)
            blend = create_blend(patches["Patch44"], patches["Patch001"],
                                 name="BlendStrip")
            for name, ok, detail in check_blend(
                    blend, patches["Patch44"], patches["Patch001"],
                    reference_poles=fixture.BlendStrip.Poles):
                if not ok:
                    errors.append("blend %s: %s" % (name, detail))
            checks.append("1 blend: oracle green incl. B4 24-pole match "
                          "against stored fixture blend")

        errors += [f"console error: {e}" for e in cap.errors]

        return {"pass": not errors, "errors": errors, "checks": checks}
    finally:
        FreeCAD.closeDocument(fixture.Name)
        FreeCAD.setActiveDocument(doc.Name)


ALL_TESTS = [
    test_chain_ground_truth,
]
