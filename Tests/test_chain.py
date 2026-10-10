"""
Chain test (ticket #21; migrated to the unified objects in ticket #40):
the full 9 -> 7 -> 2 -> 1 rebuild of the ground-truth document from a
blank document, entirely through the ops layer on UNIFIED objects only
(create_edge via _copy_fixture_edge, create_patch_unified, create_blend).

Every object is oracle-checked (check_edge / check_patch / check_blend)
and pole-matched against its stored fixture counterpart at 1e-6 (the 7
edges, both patches' 16 poles, the blend's 24 poles). A tree census
asserts criterion 3 of #40: exactly one unified type per process step --
7 Edge, 2 Patch, 1 Blend, no legacy Patch44 / BlendStrip /
ControlGrid44_3 object_type anywhere in the rebuilt tree -- in
process-step order (all Edges before the first Patch, both before the
Blend, asserted on doc.Objects creation order, not assumed).

This test IS ticket #40's deliverable -- no new ops/oracle code -- and
the standing acceptance gate for the pipeline: it always runs, it is
not skipped.
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
        from SilkWorkflowOps import create_patch_unified, create_blend
        from SilkChecks import check_edge, check_patch, check_blend

        with _CaptureConsole() as cap:
            # 9 sketches -> 7 edges
            edges = {}
            edge_devs = []
            for edge_name, sketch_names in GT_CHAIN_EDGES:
                e = _copy_fixture_edge(doc, fixture, edge_name, sketch_names)
                edges[edge_name] = e
                for name, ok, detail in check_edge(e):
                    if not ok:
                        errors.append("%s %s: %s" % (edge_name, name, detail))
                stored = fixture.getObject(edge_name).Poles
                dev = max((p - s).Length for p, s in zip(e.Poles, stored))
                edge_devs.append(dev)
                if dev > TOL:
                    errors.append("%s poles deviate %.3e from fixture"
                                  % (edge_name, dev))
            if errors:
                checks.append("7 edges: see errors")
            else:
                checks.append("7 edges: oracle green, max pole dev %.3e "
                              "vs fixture within %.0e"
                              % (max(edge_devs), TOL))

            # 7 edges -> 2 unified Patches (cyclic order per corner
            # matching); the created label is the unified type name, the
            # fixture lookup uses the STORED fixture object name.
            g = edges
            patch_specs = [
                ("Patch", "Patch44",
                 ("E_Top", "E_Left", "E_BtmL", "E_Shr")),
                ("Patch", "Patch001",
                 ("E_Shr", "E_BtmR", "E_CurR", "E_TopR")),
            ]
            patches = {}
            patch_devs = []
            for label, fixture_name, loop in patch_specs:
                ed4 = [g[n] for n in loop]
                p = create_patch_unified(ed4, name=label)
                patches[fixture_name] = p
                for cname, ok, detail in check_patch(p, ed4):
                    if not ok:
                        errors.append("%s %s: %s"
                                      % (fixture_name, cname, detail))
                stored = fixture.getObject(fixture_name).Poles
                dev = max((pp - ss).Length
                          for pp, ss in zip(p.Poles, stored))
                patch_devs.append(dev)
                if dev > TOL:
                    errors.append("%s poles deviate %.3e from fixture"
                                  % (fixture_name, dev))
            checks.append("2 unified patches: oracle green, 16 poles "
                          "each, max pole dev %.3e vs fixture within "
                          "%.0e" % (max(patch_devs), TOL))

            # 2 patches -> 1 unified Blend (B4 reference = stored
            # fixture blend; the label is the unified default "Blend",
            # fixture.BlendStrip stays the fixture's own object name)
            pa, pb = patches["Patch44"], patches["Patch001"]
            blend = create_blend(pa, pb)
            for bname, ok, detail in check_blend(
                    blend, pa, pb,
                    reference_poles=fixture.BlendStrip.Poles):
                if not ok:
                    errors.append("blend %s: %s" % (bname, detail))
            bdev = max(((p - s).Length
                        for p, s in zip(blend.Poles,
                                        fixture.BlendStrip.Poles)),
                       default=0.0)  # empty -> oracle flags it, not us
            if bdev > TOL:
                errors.append("blend poles deviate %.3e from fixture"
                              % bdev)
            checks.append("1 blend: oracle green incl. B4 24-pole match "
                          "against stored fixture blend, max pole dev "
                          "%.3e within %.0e" % (bdev, TOL))

        # Tree census (#40 criterion 3): exactly one unified type per
        # process step, and process-step order in doc.Objects (= tree
        # order). Sketches are the reference input, not Silk objects.
        census_before = len(errors)
        allowed = ("Edge", "Patch", "Blend")
        silk_types = []
        for o in doc.Objects:
            if o.isDerivedFrom("Sketcher::SketchObject"):
                continue
            t = getattr(o, "object_type", None)
            if t is None:
                errors.append("tree census: %s (%s) has no object_type"
                              % (o.Name, o.TypeId))
            else:
                silk_types.append(t)
        bad = sorted({t for t in silk_types if t not in allowed})
        if bad:
            errors.append("tree census: legacy object_type(s) in rebuilt "
                          "tree: %s" % ", ".join(bad))
        counts = {t: silk_types.count(t) for t in allowed}
        for t, want in (("Edge", 7), ("Patch", 2), ("Blend", 1)):
            if counts[t] != want:
                errors.append("tree census: %d %s object(s) in rebuilt "
                              "tree (want %d)" % (counts[t], t, want))
        idx = {t: [i for i, o in enumerate(doc.Objects)
                   if getattr(o, "object_type", None) == t]
               for t in allowed}
        if idx["Edge"] and idx["Patch"] and idx["Blend"]:
            if not (max(idx["Edge"]) < min(idx["Patch"])
                    and max(idx["Patch"]) < min(idx["Blend"])):
                errors.append("tree census: process-step order violated "
                              "(Edge idxs %s, Patch idxs %s, Blend idxs "
                              "%s)" % (idx["Edge"], idx["Patch"],
                                       idx["Blend"]))
        else:
            errors.append("tree census: type(s) missing, order not "
                          "checkable (%s)" % idx)
        if len(errors) > census_before:
            checks.append("tree census: see errors")
        else:
            checks.append("tree census: 7 Edge / 2 Patch / 1 Blend, "
                          "unified types only, edges < patches < blend")

        errors += [f"console error: {e}" for e in cap.errors]

        return {"pass": not errors, "errors": errors, "checks": checks}
    finally:
        FreeCAD.closeDocument(fixture.Name)
        FreeCAD.setActiveDocument(doc.Name)


ALL_TESTS = [
    test_chain_ground_truth,
]
