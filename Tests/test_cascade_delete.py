"""
Cascade-delete (#89): deleting a Patch from under a live 2-patch edge
blend must cascade-delete that blend with full-unblend on the survivor.

The reported failure the ticket exists for: `doc.removeObject(patchA)`
removes the patch but leaves the blend behind as an ORPHAN -- its
PatchA link nullified by Document::_removeObject, so it can no longer
unblend, and the surviving patch keeps its band hole (hidden cell) and
stale split and renders subdivided forever. This test fails exactly on
that. The fix is ONE central app-level document observer (object model,
not InitGui) that catches the patch delete in the same
before-links-nullified window _DeleteWatcher relies on, runs the shared
_on_delete unblend on the linked blend, then removes the orphan.
"""

import FreeCAD
import os

FIXTURE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..",
                       "Resources", "Test_files", "Silk_Workflow.FCStd")


class _CaptureMessage:
    """Capture FreeCAD.Console.PrintMessage (the silent cascade line)."""

    def __enter__(self):
        import FreeCAD
        self._orig = FreeCAD.Console.PrintMessage
        self.messages = []
        FreeCAD.Console.PrintMessage = lambda msg: self.messages.append(msg)
        return self

    def __exit__(self, *args):
        FreeCAD.Console.PrintMessage = self._orig


def _hidden(p):
    return list(getattr(p, "_HiddenSubgridIdxs", []) or [])


def test_deleted_patch_cascades_its_blend(doc):
    """#89: delete a patch from under a live (ops-created) blend -> the
    orphan blend is gone and the surviving patch is a plain patch again
    (no band hole, no stale split, cells restored)."""
    from SilkWorkflowOps import create_blend
    from Tests.test_blend_stage import _build_gt_chain, _edges, _carries_band

    fixture = FreeCAD.openDocument(FIXTURE)
    FreeCAD.setActiveDocument(doc.Name)
    errors, checks = [], []
    try:
        pa, pb, _ = _build_gt_chain(doc, fixture)
        blend = create_blend(pa, pb, name="Blend")
        doc.recompute()

        blend_name, pa_name, pb_name = blend.Name, pa.Name, pb.Name

        # precondition: the blend is live and both patches carry their band
        if not list(blend.Poles or []):
            return {"pass": False, "checks": checks,
                    "errors": ["precondition: blend did not build"]}
        checks.append("blended: hidden=%s" % ([_hidden(pa), _hidden(pb)],))
        if not (_hidden(pa) and _hidden(pb)):
            return {"pass": False, "checks": checks,
                    "errors": ["precondition: blended patches should hide "
                               "their band cell; got %s"
                               % ([_hidden(pa), _hidden(pb)],)]}

        # --- delete one patch from under the live blend --------------
        with _CaptureMessage() as cap:
            doc.removeObject(pa.Name)
            doc.recompute()

        # cascade: the blend is gone
        blends_after = [o.Name for o in doc.Objects
                        if getattr(o, "object_type", "")
                        in ("Blend", "BlendStrip")]
        checks.append("blends after patch delete: %s" % blends_after)
        if any(o.Name == blend_name for o in doc.Objects):
            errors.append("the blend %s survived the patch delete as an "
                          "orphan" % blend_name)

        # the survivor is a plain patch again
        if not any(o.Name == pb_name for o in doc.Objects):
            errors.append("the surviving patch %s was removed too" % pb_name)
        h_b, e_b = _hidden(pb), _edges(pb)
        cells = len(pb.Proxy._subgrids)
        faces = len(pb.Shape.Faces)
        checks.append("survivor %s: hidden=%s edges=%s subgrids=%d faces=%d"
                      % (pb_name, h_b, e_b, cells, faces))
        if h_b:
            errors.append("survivor %s still hides band cell %s -- a band "
                          "hole is left behind" % (pb_name, h_b))
        if _carries_band(pb):
            errors.append("survivor %s still carries a band edge %s -- not "
                          "a plain patch" % (pb_name, e_b))
        if cells != 0:
            errors.append("survivor %s still carries %d subgrids -- not a "
                          "plain patch" % (pb_name, cells))
        if faces != 1:
            errors.append("survivor %s is not one whole surface: %d faces"
                          % (pb_name, faces))

        # silent notice: exactly one console line naming blend + patch
        cascade_lines = [m for m in cap.messages
                         if "cascad" in m.lower() and blend_name in m]
        checks.append("cascade console lines: %s" % cascade_lines)
        if len(cascade_lines) != 1:
            errors.append("expected exactly one cascade console line naming "
                          "%s, got %r" % (blend_name, cascade_lines))
        elif pa_name not in cascade_lines[0]:
            errors.append("cascade console line does not name the deleted "
                          "patch %s: %r" % (pa_name, cascade_lines[0]))
    finally:
        FreeCAD.closeDocument(fixture.Name)
        FreeCAD.setActiveDocument(doc.Name)

    return {"pass": not errors, "errors": errors, "checks": checks}


ALL_TESTS = [
    test_deleted_patch_cascades_its_blend,
]
