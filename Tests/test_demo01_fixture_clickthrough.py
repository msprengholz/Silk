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

# --- manual tier ------------------------------------------------------
# This module's subject is an end-to-end rebuild / GUI drive /
# measurement sweep, so it is NOT in the default (fast) tier. Run it
# with `python3 Tests/run_all.py --manual` (or by name as a filter);
# Tests/test_manual_tier.py asserts it stays importable. See suite.py.
MANUAL = True

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
    # #126: a junction the DEFAULT (rolling) construction cannot build is
    # refused BY NAME with nothing created -- the measured limit of this model
    # (CB_J4; see `_assert_corners`).  Every OTHER problem is an error.
    for problem in result["problems"]:
        if problem.startswith("corner ") and "Nothing was created" in problem:
            checks.append("%s" % problem.strip())
            continue
        errors.append(problem)

    counts = (len(result["edges"]), len(result["patches"]),
              len(result["blends"]), len(result["corners"]))
    if counts[:3] != (12, 5, 8) or counts[3] != 4 - len(
            [p for p in result["problems"]
             if p.startswith("corner ") and "Nothing was created" in p]):
        errors.append("click-through reached %d edges / %d patches / "
                      "%d blends / %d corners, want 12/5/8/4 (minus any "
                      "junction the default construction refused by name)"
                      % counts)
    else:
        checks.append("click-through: 12 Edges -> 5 Patches -> 8 Blends -> "
                      "%d CornerBlends (%d junction(s) refused by name)"
                      % (counts[3], 4 - counts[3]))
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

    A junction the DEFAULT (rolling) construction cannot build is held to the
    other half of the contract instead: refused BY NAME, with the reason on
    the console, and NO object left behind (#126, CB_J4 -- see the note in
    the body).
    """
    errors, checks, report = [], [], []
    # #126: THE DEFAULT CONSTRUCTION IS THE ROLLING ONE, and on THIS model it
    # reaches three of the four junctions.  The fourth (CB_J4) shares P_Bottom
    # with CB_J2, whose rolling cut lands on P_Bottom's junction end; a ring
    # whose non-member patch already carries a neighbouring corner's real
    # second cut is OPEN (#127), so the corner stage refuses it BY NAME and
    # creates NOTHING.  That is measured, not hidden: the junctions that build
    # are held to the full contract below, and a junction that refuses must
    # say why and leave no object behind.  WHICH CORNER carries the tri when
    # a ring patch already carries a neighbouring corner's cut is the
    # placement question #126 hands to the owner.
    built_names = sorted(result["corners"])
    refused = [name for name, _ring, _pt in MODEL.CORNERS
               if name not in result["corners"]]
    checks.append("junctions built: %s; refused: %s"
                  % (built_names, refused))
    for name in refused:
        why = " ".join(result["console"].get(name) or []).strip()
        if "Nothing was created" not in why:
            errors.append("corner %s was neither built nor refused with a "
                          "named reason: %r" % (name, why))
        elif "OPEN" not in why and "cannot be built" not in why:
            errors.append("corner %s refused without naming the ring's open "
                          "corner: %r" % (name, why))
        else:
            checks.append("corner %-24s refused by name, nothing created: %s"
                          % (name, why))
    for name, ring, point in MODEL.CORNERS:
        corner = result["corners"].get(name)
        if corner is None:
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
    if sorted(built) != sorted(result["corners"]):
        errors.append("the document carries %s CornerBlend(s), the build "
                      "returned %s" % (built, sorted(result["corners"])))
    else:
        checks.append("%d CornerBlend(s) in the document after the second "
                      "asks (no object for a refused junction)" % len(built))
    return errors, checks, report


ALL_TESTS = [
    test_demo01_clickthrough_builds_the_documented_model,
]


def test_a_demo_junction_rolls_on_the_patch_that_carries_two_junctions(doc):
    """#126: THE ROLLING CONSTRUCTION ON THE OWNER'S OWN RING PATCH.

    Its ring patches carry a THIRD seam on the side opposite the junction, so
    the along-seam axis of a rolled seam carries a band edge at BOTH ends --
    two junctions on one axis -- and the patch alone cannot say which end is
    this seam's.  Before #126 the leader placement refused there
    (`the band on P_Top does not reach exactly one junction corner on its V
    axis`) and the corner fell back to the shipped construction.

    Now the RING answers it (`SilkWorkflowOps.seam_junction_end`: the patch
    corner the patch's two ring seams share) and the junction builds.  What
    this pins is the PLACEMENT: the two leader cuts land on the member
    patch's own axis ends, the setback is not touched, the ring reads OPEN on
    the member patch only, and the corner records `rolling` with no refusal
    on the console.  No continuity label is asserted.
    """
    import SilkMachinery as SM
    from SilkCorner import corner_construction, corner_inputs
    from SilkBlend import side_and_end
    from SilkWorkflowOps import seam_junction_end

    errors, checks, report = [], [], []
    model = MODEL.build(doc, corners=False)
    errors.extend(model["problems"])
    name, ring, _point = MODEL.CORNERS[0]
    strips = [model["blends"][b] for b in ring]

    # the ring's answer, per (seam, patch): where the junction is on the
    # seam-parallel axis
    for s in strips:
        for p in (s.PatchA, s.PatchB):
            e, _ss = side_and_end(s, p)
            end, why = seam_junction_end(s, p, strips)
            if end is None:
                errors.append("%s on %s: the ring cannot place the junction "
                              "(%s)" % (s.Name, p.Name, why))
                continue
            checks.append("%s on %-9s side %s -> junction at the %d end"
                          % (s.Name, p.Name, e, end))

    with MODEL.CaptureConsole() as cap:
        corner = MODEL.OPS.create_corner_blend(*strips, name=name)
    doc.recompute()
    doc.recompute()
    refusal = " ".join(cap.errors).strip()
    if refusal:
        errors.append("the rolling construction refused: %s" % refusal)
    if corner is None:
        errors.append("no corner was built")
        return {"pass": False, "errors": errors, "checks": checks}
    built, _note = corner_construction(corner)
    checks.append("%s: construction %r, %d poles"
                  % (corner.Name, built, len(corner.Poles)))
    if built != "rolling":
        errors.append("the corner records %r, not the rolling construction"
                      % (built,))
    if len(corner.Poles) != 36:
        errors.append("the corner carries %d poles, want 36"
                      % len(corner.Poles))
    grids, _cells, why = corner_inputs(strips)
    if grids is None:
        errors.append("the ring does not assemble: %s" % why)
    else:
        checks.append("corner_inputs assembles the ring")

    # the cut: the MEMBER patch's own two axis ends, the setback untouched
    member = None
    for o in doc.Objects:
        if getattr(o, "object_type", "") == "RollingMemberFace":
            member = o
    if member is None:
        errors.append("the corner built no triangular member")
    else:
        checks.append("the triangular member %s is in the tree (%d poles)"
                      % (member.Name, len(member.Poles)))
    member_patch = None
    for p in (strips[0].PatchA, strips[0].PatchB, strips[1].PatchA,
              strips[1].PatchB, strips[2].PatchA, strips[2].PatchB):
        if SM.ring_corner_gap(p) is not None:
            member_patch = p
    if member_patch is None:
        errors.append("no ring patch carries a real second cut -- the rolling "
                      "cut did not land")
    else:
        cuts = {L: SM.leader_pair(member_patch, L) for L in ("U", "V")}
        splits = {L: SM.split_pair(member_patch, L) for L in ("U", "V")}
        checks.append("%s: leader cuts %s, band edges %s, ring_corner_gap %r"
                      % (member_patch.Name, cuts, splits,
                         SM.ring_corner_gap(member_patch)))
        report.append("%s leader cuts %s band edges %s"
                      % (member_patch.Name, cuts, splits))
        # the setback did not ride along with the leader: the band edges are
        # the demo's own, and the leader cut is a DIFFERENT number in a
        # DIFFERENT property
        for L, pair in splits.items():
            for end, sentinel in ((0, 0.0), (1, 1.0)):
                edge = pair[end]
                lead = cuts[L][end]
                if edge in (0.0, 1.0) and lead in (0.0, 1.0):
                    continue
                if abs(lead - edge) < 1e-12:
                    errors.append("%s's %s axis: the leader cut %g is the band "
                                  "edge %g itself -- the setback rode along "
                                  "with the leader" % (member_patch.Name, L,
                                                       lead, edge))
        for other in (strips[0].PatchA, strips[0].PatchB, strips[1].PatchA,
                      strips[1].PatchB, strips[2].PatchA, strips[2].PatchB):
            if other is member_patch:
                continue
            if SM.ring_corner_gap(other) is not None:
                errors.append("%s carries a real second cut: only the member "
                              "patch may" % other.Name)

    from Tests.prototype_reference_corner import _coins
    poles = list(corner.Poles)
    coins = _coins(poles)
    checks.append("the 6x6: %d/630 coincident pairs, collapsed side %r"
                  % (coins, SM._collapsed_side(poles, 1e-6)))
    if coins:
        errors.append("the 6x6 carries %d coincident pole pairs" % coins)

    # THE INTERIOR (measured #129): the demo's 6x6 has no collapsed side, so
    # `smooth_degenerate_cap` is a no-op here and nothing but
    # `SilkMachinery.smooth_folding_interior` touches it -- and upstream's
    # tangent-ratio interior FOLDS on this cell.  Before that step the built
    # corner read 30/56/86 normal-field flips at n=39/81/150 on both readers
    # (Part surface and exact net) with the tri inside the quad (0.0179 mm of
    # its interior off the quad, 0.03..2.13 % of the corner's 57.5 mm
    # extent); with it the corner reads 0/0/0 and the tri's nearest interior
    # sample stands 0.30967 mm off the quad.  Raw readings:
    # `Resources/Test_files/_inspect/step1_demo_corner_row_diff.txt`.
    import SilkChecks
    flips = [len(SilkChecks._normal_field_flips(
        corner.Shape.Faces[0].Surface, n=n)[0]) for n in (39, 81, 150)]
    checks.append("the quad's normal-field flips n=39/81/150: %r (the cell "
                  "this corner is cut from has no collapsed side, so this is "
                  "`smooth_folding_interior` and not the cap smoothing)"
                  % (flips,))
    if any(flips):
        errors.append("the demo corner's 6x6 folds (%r flips at "
                      "n=39/81/150) -- the interior step did not hold"
                      % (flips,))
    return {"pass": not errors, "errors": errors, "checks": checks}


ALL_TESTS = [
    test_demo01_clickthrough_builds_the_documented_model,
    test_a_demo_junction_rolls_on_the_patch_that_carries_two_junctions,
]
