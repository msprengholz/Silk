"""Demo 01 fixture click-through (ticket #98): the documented
Edge -> Patch -> Blend -> CornerBlend sequence, driven through the ops layer
from `Resources/Test_files/examples/SketchOnly_Demo01Subset.FCStd`.

The fixture is the human-test artifact: a person opens it, clicks each
sketch into an Edge, four Edges into a Patch, two Patches into a Blend and
three ring Blends into a CornerBlend, and should end with Demo 01's own
topology -- 12 Edges, 5 Patches (Front/Top/Right/Bottom/Back), 8 seams
blended and 4 three-valent hard corners.  The mapping (which sketches, which
click order, which pair order) is `Tests/demo01_fixture_model.py`, and this
module asserts it end to end and against the objects that came out:

  * the 12 Edges consume exactly the documented sketches, and the demo's four
    FULL-rib sketches are not among them;
  * each Patch's stored `Edges` list is the documented cycle (entry k is
    boundary side k);
  * each Blend's `PatchA`/`PatchB` is the documented direction, its seam is
    auto-detected (no Edge pin -- the toolbar's two-patch path) and the seam
    inventory shows all 8 seams blended;
  * each CornerBlend fills its junction: 36 poles, one valid face, the
    junction point inside the fill's box, and an idempotent second ask in
    either strip order.

No continuity label is asserted anywhere.
"""

import FreeCAD

import SilkChecks
import Tests.demo01_fixture_model as MODEL

PANEL_SKETCH_TOL = 1e-6


def _failed(results):
    return [(n, d) for (n, ok, d) in results if not ok]


def _report(lines):
    """Emit the raw numbers (the harness prints errors, not `checks`)."""
    for line in lines:
        print("[demo01] %s" % line)


def test_demo01_clickthrough_builds_the_documented_model(doc):
    """The documented click order, end to end, through the ops layer: the
    built model AND the corners it reaches.

    One build carries both halves.  `MODEL.build` is this module's entire cost
    (measured ~19 s: 12 Edges -> 5 Patches -> 8 Blends -> 4 CornerBlends, a
    full-document recompute per created object), and the two halves assert
    complementary contracts on exactly that one build, so building it twice
    bought nothing but wall clock.  Every assertion the former
    `test_demo01_clickthrough_corners_fill_their_junctions` carried is below,
    unchanged.
    """
    errors, checks, report = [], [], []
    result = MODEL.build(doc)
    errors.extend(result["problems"])

    counts = (len(result["edges"]), len(result["patches"]),
              len(result["blends"]), len(result["corners"]))
    if counts != (12, 5, 8, 4):
        errors.append("click-through reached %d edges / %d patches / "
                      "%d blends / %d corners, want 12/5/8/4" % counts)
    else:
        checks.append("click-through: 12 Edges -> 5 Patches -> 8 Blends -> "
                      "4 CornerBlends")
    report.append("counts: %d edges, %d patches, %d blends, %d corners"
                  % counts)

    # ---- the Edges consume exactly the documented sketches
    used = set(MODEL.used_sketch_names())
    if len(used) != 16:
        errors.append("the model claims %d sketches, want 16" % len(used))
    for name, sketches, _legacy in MODEL.EDGES:
        edge = result["edges"].get(name)
        if edge is None:
            continue
        linked = [s.Name for s in edge.Sketches]
        if linked != list(sketches):
            errors.append("edge %s links %s, documented %s"
                          % (name, linked, list(sketches)))
    checks.append("12 Edges over 16 sketches: 4 cross-sections, 4 half-ribs, "
                  "4 node-pair hoop edges")
    full_ribs = [s for s in ("Sketch020", "Sketch022", "Sketch024",
                             "Sketch026") if s in used]
    if full_ribs:
        errors.append("the rebuild consumes the demo's FULL-rib sketches "
                      "%s -- the faces need the [0.5, 1] halves" % full_ribs)
    else:
        checks.append("the demo's four full-rib sketches are NOT consumed "
                      "(the four SK_Half_Rib_* halves are)")

    # ---- every patch's stored Edges list IS the documented cycle
    for name, order, _grid in MODEL.PATCHES:
        patch = result["patches"].get(name)
        if patch is None:
            continue
        stored = [e.Name for e in patch.Edges]
        if stored != list(order):
            errors.append("patch %s stores the cycle %s, documented %s"
                          % (name, stored, list(order)))
        bad = _failed(SilkChecks.check_patch(patch, list(patch.Edges)))
        if bad:
            errors.append("check_patch %s: %s" % (name, bad))
        else:
            checks.append("patch %-9s check_patch GREEN on its own stored "
                          "Edges cycle (%s)" % (name, ", ".join(stored)))

    # ---- every blend: documented direction, auto-detected seam, green
    for name, pa, pb, seam in MODEL.BLENDS:
        blend = result["blends"].get(name)
        if blend is None:
            continue
        if blend.PatchA is not result["patches"].get(pa) \
                or blend.PatchB is not result["patches"].get(pb):
            errors.append("blend %s is directed %s->%s, documented %s->%s"
                          % (name, blend.PatchA.Name, blend.PatchB.Name,
                             pa, pb))
        if getattr(blend, "Edge", None) is not None:
            errors.append("blend %s carries an Edge pin (%s); the documented "
                          "path has the seam auto-detected"
                          % (name, blend.Edge.Name))
        bad = _failed(SilkChecks.check_blend(blend, blend.PatchA,
                                             blend.PatchB))
        if bad:
            errors.append("check_blend %s: %s" % (name, bad))
        else:
            checks.append("blend %-6s %s->%s over %-16s check_blend GREEN "
                          "(%d poles)" % (name, pa, pb, seam,
                                          len(blend.Poles)))
    blended = [n for n, status in result["seam_inventory"]
               if status == "blended"]
    if len(result["seam_inventory"]) != 8 or len(blended) != 8:
        errors.append("seam inventory is %s, want 8 seams all 'blended'"
                      % (result["seam_inventory"],))
    else:
        checks.append("seam inventory: 8 seams, all 'blended' (%s)"
                      % ", ".join(name for name, _s in result["seam_inventory"]))
    report.append("seams: %s" % result["seam_inventory"])

    _report(report)

    # ---- the second half: the four 3-valent corners of the SAME build
    corner_errors, corner_checks, corner_report = _assert_corners(result, doc)
    errors.extend(corner_errors)
    checks.extend(corner_checks)
    _report(corner_report)
    return {"pass": not errors, "errors": errors, "checks": checks}


def _assert_corners(result, doc):
    """Each of the four 3-valent corners, from its three ring blends.

    Contract: 36 poles, exactly one face, a valid Shape, the junction point
    inside the fill's bounding box, and an idempotent second ask (the same
    object, in the documented order and reversed).  The corner fills carry no
    Edge link of their own; `Strips` is the ring the ops layer ordered.
    """
    errors, checks, report = [], [], []
    if len(result["corners"]) != 4:
        errors.append("expected 4 corners, built %d" % len(result["corners"]))
        return errors, checks, report
    for name, ring, point in MODEL.CORNERS:
        corner = result["corners"].get(name)
        if corner is None:
            errors.append("corner %s was not built" % name)
            continue
        problems = []
        if len(corner.Poles or []) != 36:
            problems.append("%d poles, want 36" % len(corner.Poles or []))
        if not corner.Shape or corner.Shape.isNull():
            problems.append("null Shape")
        else:
            if len(corner.Shape.Faces) != 1:
                problems.append("%d faces, want 1" % len(corner.Shape.Faces))
            if not corner.Shape.isValid():
                problems.append("Shape is not valid")
        strips = [s.Name for s in corner.Strips]
        if sorted(strips) != sorted(ring):
            problems.append("Strips %s, documented ring %s"
                            % (strips, list(ring)))
        if problems:
            errors.append("corner %s: %s" % (name, "; ".join(problems)))
            continue

        bb = corner.Shape.BoundBox
        junction = FreeCAD.Vector(*point)
        inside = (bb.XMin - PANEL_SKETCH_TOL <= junction.x
                  <= bb.XMax + PANEL_SKETCH_TOL
                  and bb.YMin - PANEL_SKETCH_TOL <= junction.y
                  <= bb.YMax + PANEL_SKETCH_TOL
                  and bb.ZMin - PANEL_SKETCH_TOL <= junction.z
                  <= bb.ZMax + PANEL_SKETCH_TOL)
        if not inside:
            errors.append("corner %s does not cover its junction %s: box "
                          "(%.3f..%.3f, %.3f..%.3f, %.3f..%.3f)"
                          % ((name, point) + (bb.XMin, bb.XMax, bb.YMin,
                                              bb.YMax, bb.ZMin, bb.ZMax)))
        checks.append("corner %-24s 36 poles, 1 face, valid=%s, junction %s "
                      "inside box (%.2f..%.2f, %.2f..%.2f, %.2f..%.2f)"
                      % (name, corner.Shape.isValid(),
                         "(%.0f, %.0f, %.0f)" % point,
                         bb.XMin, bb.XMax, bb.YMin, bb.YMax, bb.ZMin,
                         bb.ZMax))
        report.append("corner %-24s 36 poles, %d face, valid=%s, box "
                      "(%.2f..%.2f, %.2f..%.2f, %.2f..%.2f)"
                      % (name, len(corner.Shape.Faces),
                         corner.Shape.isValid(), bb.XMin, bb.XMax, bb.YMin,
                         bb.YMax, bb.ZMin, bb.ZMax))

        # idempotent second ask: same object, documented order and reversed
        strips = [result["blends"][b] for b in ring]
        for label, order in (("documented", strips),
                             ("reversed", list(reversed(strips)))):
            with MODEL.CaptureConsole() as cap:
                again = MODEL.OPS.create_corner_blend(order,
                                                      name=name + "_ask2")
            if again is not corner:
                errors.append("corner %s: the %s-order second ask returned "
                              "%r instead of the existing corner (%s)"
                              % (name, label,
                                 getattr(again, "Name", again),
                                 " ".join(cap.errors).strip()))
    built = [o.Name for o in doc.Objects
             if getattr(o, "object_type", "") == "CornerBlend"]
    if len(built) != 4:
        errors.append("expected exactly 4 CornerBlends in the document, "
                      "found %d (%s)" % (len(built), built))
    else:
        checks.append("exactly 4 CornerBlends in the document after the "
                      "second asks")
    return errors, checks, report


ALL_TESTS = [
    test_demo01_clickthrough_builds_the_documented_model,
]
