"""Demo 01 rebuild (ticket #98): the mapping, measured -- and the fixture
that makes it reachable.

The demo's own sketches (`Resources/Demo_files/Silk_Demo_01.FCStd`, opened
read-only and never saved) are HALF the shape: the rib curves run (mirrored
hoop) -> symmetry plane (u = 0.5) -> modelled hoop (u = 1), and the five ring
faces consume only the u in [0.5, 1] half of each rib (a stored
`ControlPoly4_segment` piece).  A Silk `Edge` consumes a WHOLE sketch -- it
has no trim property -- so on the demo's own sketches the twelve whole-sketch
Edges build but the four rib-bounded faces cannot close a loop: that is
pinned here, unchanged, with the exact refusal text.

`Resources/Test_files/examples/SketchOnly_Demo01Subset.FCStd` adds the four
missing half-ribs as ordinary 3-line ControlPoly4 sketches (the u in [0.5, 1]
sub-curve of a cubic Bezier is exactly a cubic Bezier).  The fixture rebuild
then reaches the demo's own topology -- 12 Edges -> 5 Patches -> 8 Blends ->
4 CornerBlends, all oracle-green -- and the measurements below say how
exactly it reproduces the demo's stored legacy objects:

  * every built Edge is pole-identical to the demo's stored `ControlPoly4`
    it stands for (the four half-ribs against the stored
    `ControlPoly4_segment` pieces: max delta 2.8e-14 mm, float association,
    not geometry);
  * every built Patch's 16-pole net IS the demo's stored `ControlGrid44_4_*`
    net, up to a named symmetry of the square: Front/Top/Back in the stored
    order (delta <= 2.9e-14), Right under `rot90` and Bottom under `rot180`
    (delta <= 4.0e-13) (see `Tests/demo01_fixture_model.py`).

The click order is NOT part of the result (#107), and the third test
measures that: in the demo's own stored order all five faces are
pole-identical in the RAW order and all four junctions fill, with the SAME
36 poles the documented order produces (delta <= 4e-13). Before #107 the
demo's own order made every junction refuse; the corner stage read a patch
that parameterizes a seam the other way round, and a blend whose
`PatchA`/`PatchB` order differs from the ring's direction, as errors.

No continuity label is asserted anywhere in this module.
"""

import os

import FreeCAD

import SilkChecks
import SilkWorkflowOps as OPS
import Tests.demo01_fixture_model as MODEL

_SILK_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEMO01_PATH = MODEL.DEMO01_PATH
FIXTURE_PATH = MODEL.FIXTURE_PATH

# The demo's 29 sketches are the WHOLE-rib inputs: 16 of them feed 12
# whole-sketch Edges, and the four rib-bounded faces cannot close on them.
# (edge name, sketches, measured u=0 end, measured u=1 end, measured u=0.5
#  point for ribs -- the symmetry-plane corner the face would have to start
#  from -- or None)
EDGE_MAP = [
    ("E_front_out", ("Sketch015",), (0.0, 0.0, 0.0), (0.0, 0.0, 50.0), None),
    ("E_top_out", ("Sketch016",), (0.0, 0.0, 50.0), (185.0, 0.0, 70.0), None),
    ("E_back_out", ("Sketch017",), (185.0, 0.0, 70.0), (170.0, 0.0, 0.0), None),
    ("E_bottom_out", ("Sketch018",), (0.0, 0.0, 0.0), (170.0, 0.0, 0.0), None),
    ("E_rib_FB", ("Sketch020",), (20.0, 75.0, 0.0), (20.0, -75.0, 0.0),
     (0.0, 0.0, 0.0)),
    ("E_rib_FT", ("Sketch022",), (20.0, 85.0, 50.0), (20.0, -85.0, 50.0),
     (0.0, 0.0, 50.0)),
    ("E_rib_BkB", ("Sketch024",), (150.0, 45.0, 0.0), (150.0, -45.0, 0.0),
     (170.0, 0.0, 0.0)),
    ("E_rib_TBk", ("Sketch026",), (185.0, 50.0, 60.0), (185.0, -50.0, 60.0),
     (185.0, 0.0, 70.0)),
    ("E_right_FR", ("Sketch036", "Sketch037"), (20.0, -85.0, 50.0),
     (20.0, -75.0, 0.0), None),
    ("E_right_BR", ("Sketch038", "Sketch039"), (20.0, -75.0, 0.0),
     (150.0, -45.0, 0.0), None),
    ("E_right_TR", ("Sketch042", "Sketch045"), (20.0, -85.0, 50.0),
     (185.0, -50.0, 60.0), None),
    ("E_right_BkR", ("Sketch032", "Sketch035"), (185.0, -50.0, 60.0),
     (150.0, -45.0, 0.0), None),
]

# (patch name, whole-sketch edge cycle, verdict, the edge named by a refusal)
PATCH_MAP = [
    ("P_Front", ("E_front_out", "E_right_FR", "E_rib_FT", "E_rib_FB"),
     "refused", "E_front_out"),
    ("P_Top", ("E_rib_FT", "E_right_TR", "E_rib_TBk", "E_top_out"),
     "refused", "E_top_out"),
    ("P_Right", ("E_right_FR", "E_right_BR", "E_right_BkR", "E_right_TR"),
     "built", None),
    ("P_Bottom", ("E_right_BR", "E_rib_FB", "E_bottom_out", "E_rib_BkB"),
     "refused", "E_bottom_out"),
    ("P_Back", ("E_rib_BkB", "E_right_BkR", "E_rib_TBk", "E_back_out"),
     "refused", "E_back_out"),
]

_ENDPOINT_TOL = 1e-6
_POLE_TOL = 1e-9

# The demo's stored legacy ControlPoly4 objects the 12 whole-sketch Edges
# rebuild from (pole parity measured at exactly 0.0 on every edge).
LEGACY_POLYS = {
    "E_front_out": "ControlPoly4_3L",
    "E_top_out": "ControlPoly4_3L003",
    "E_back_out": "ControlPoly4_3L002",
    "E_bottom_out": "ControlPoly4_3L001",
    "E_rib_FB": "ControlPoly4_3L004",
    "E_rib_FT": "ControlPoly4_3L005",
    "E_rib_BkB": "ControlPoly4_3L006",
    "E_rib_TBk": "ControlPoly4_3L007",
    "E_right_FR": "ControlPoly4_2N001",
    "E_right_BR": "ControlPoly4_2N003",
    "E_right_TR": "ControlPoly4_2N004",
    "E_right_BkR": "ControlPoly4_2N",
}

# check_edge's E2 heuristic (step <= 1.05 * skip) is violated by the demo's
# OWN stored Bottom_Right hoop poly (ControlPoly4_2N003): p2->p3 = 70.711 >
# 1.05 * p2->p0 = 63.246.  The rebuilt edge is pole-identical to that legacy
# object, so the deviation is inherited from the demo's input geometry.
KNOWN_E2_EDGE = MODEL.KNOWN_E2_EDGE


class _CaptureConsole:
    """Capture PrintError output for one block (the refusal texts)."""

    def __enter__(self):
        self._orig = FreeCAD.Console.PrintError
        self.errors = []
        FreeCAD.Console.PrintError = lambda msg: (
            self.errors.append(msg), self._orig(msg))
        return self

    def __exit__(self, *args):
        FreeCAD.Console.PrintError = self._orig


def _failed(results):
    return [(n, d) for (n, ok, d) in results if not ok]


def _close(point, expected, tol=_ENDPOINT_TOL):
    return (point - FreeCAD.Vector(*expected)).Length <= tol


def _curve(edge):
    return edge.Shape.Edges[0]


def _open_read_only(path):
    """Open `path`, or reuse the document if it is already open.
    Returns (doc, we_opened) so the caller closes only what it opened."""
    name = os.path.splitext(os.path.basename(path))[0]
    docs = FreeCAD.listDocuments()
    if name in docs:
        return docs[name], False
    return FreeCAD.openDocument(path), True


def _copy_sketch(target_doc, source_doc, name):
    """Copy one sketch's geometry + placement into `target_doc` under the
    same name. Constraints are not needed to build an Edge."""
    src = source_doc.getObject(name)
    dst = target_doc.addObject("Sketcher::SketchObject", name)
    dst.Placement = src.Placement
    for g in src.Geometry:
        dst.addGeometry(g, False)
    return dst


def _report(lines):
    """Emit the raw numbers this ticket has to report, so they reach the
    suite tail (the harness prints errors, not `checks`)."""
    for line in lines:
        print("[demo01] %s" % line)


# ---------------------------------------------------------------------------
# 1. the demo's own whole-rib sketches: what still refuses, pinned
# ---------------------------------------------------------------------------

def _whole_sketch_attempt(source_doc, doc, legacy=None):
    """Run the whole-sketch rebuild attempt from `source_doc`'s sketches into
    the harness scratch `doc`. `legacy` (optional) maps edge name -> the
    demo's stored ControlPoly4 name for pole parity. Returns
    {pass, errors, checks}."""
    errors, checks = [], []
    FreeCAD.setActiveDocument(doc.Name)
    for _name, sketches, _p0, _p1, _mid in EDGE_MAP:
        for sk in sketches:
            _copy_sketch(doc, source_doc, sk)
    doc.recompute()

    # ---- Edges: all 12 build, match the measured geometry, and pass
    # check_edge (with the one inherited E2 deviation documented).
    edges = {}
    edge_errors = []
    for name, sketches, p0, p1, mid in EDGE_MAP:
        edge = OPS.create_edge([doc.getObject(s) for s in sketches], name=name)
        if edge is None:
            edge_errors.append("edge %s refused to build" % name)
            continue
        edges[name] = edge
        e = _curve(edge)
        a = e.valueAt(e.FirstParameter)
        b = e.valueAt(e.LastParameter)
        if not (_close(a, p0) and _close(b, p1)):
            edge_errors.append(
                "edge %s runs (%s -> %s), measured (%s -> %s)"
                % (name, tuple(a), tuple(b), p0, p1))
        if mid is not None:
            m = e.valueAt((e.FirstParameter + e.LastParameter) / 2.0)
            if not _close(m, mid):
                edge_errors.append(
                    "rib %s u=0.5 at %s, measured symmetry-plane corner %s"
                    % (name, tuple(m), mid))
        bad = _failed(SilkChecks.check_edge(edge))
        if bad:
            if (name == KNOWN_E2_EDGE and len(bad) == 1
                    and bad[0][0] == "E2_pole_order"):
                checks.append("check_edge %s: E2 pole-order deviation "
                              "inherited from the demo's own 2N poly (%s)"
                              % (name, bad[0][1]))
            else:
                edge_errors.append("check_edge %s: %s" % (name, bad))
    errors.extend(edge_errors)
    if not edge_errors:
        checks.append("%d/%d whole-sketch edges build, geometry matches the "
                      "measured demo mapping" % (len(edges), len(EDGE_MAP)))

    # ---- Pole parity against the demo's stored ControlPoly4 objects.
    if legacy is not None:
        parity_errors = []
        for name, lname in legacy.items():
            e = edges.get(name)
            lp = source_doc.getObject(lname).Poles
            if e is None:
                parity_errors.append("%s missing for parity" % name)
                continue
            ep = list(e.Poles)
            delta = max((ep[i] - lp[i]).Length for i in range(4))
            if delta > _POLE_TOL:
                parity_errors.append("%s vs %s: max pole delta %.3e"
                                     % (name, lname, delta))
            if name == KNOWN_E2_EDGE:
                # the E2 acceptance above must be INHERITED: the same
                # inequality on the legacy poles
                factor = SilkChecks.ORDER_FACTOR
                step_new = (ep[2] - ep[3]).Length
                skip_new = (ep[2] - ep[0]).Length
                step_old = (lp[2] - lp[3]).Length
                skip_old = (lp[2] - lp[0]).Length
                if not (step_new > factor * skip_new
                        and step_old > factor * skip_old):
                    parity_errors.append(
                        "E2 inheritance not reproduced: legacy %.3f/%.3f, "
                        "rebuilt %.3f/%.3f, factor %.2f"
                        % (step_old, skip_old, step_new, skip_new, factor))
        errors.extend(parity_errors)
        if not parity_errors:
            checks.append("%d/%d poles identical to the demo's stored "
                          "ControlPoly4 objects (max delta 0)"
                          % (len(legacy), len(legacy)))

    # ---- Patches: only the Right end cap closes; the four rib-bounded
    # faces must be refused, naming their outer cross-section edge.
    patches = {}
    skipped_patch = False
    with _CaptureConsole() as cap:
        for name, keys, verdict, outer in PATCH_MAP:
            if any(k not in edges for k in keys):
                errors.append("%s skipped: its edges did not build" % name)
                skipped_patch = True
                continue
            before = len(cap.errors)
            patch = OPS.create_patch([edges[k] for k in keys], name=name)
            msgs = cap.errors[before:]
            if verdict == "built":
                if patch is None:
                    errors.append("%s refused (%s)" % (name, msgs))
                    continue
                patches[name] = patch
                bad = _failed(SilkChecks.check_patch(patch, list(patch.Edges)))
                if bad:
                    errors.append("check_patch %s: %s" % (name, bad))
                else:
                    checks.append("%s builds and check_patch GREEN "
                                  "(the end cap's 4 curves are whole "
                                  "sketches)" % name)
            else:
                if patch is not None:
                    errors.append(
                        "%s now BUILDS -- the half-rib limitation changed; "
                        "update the #98 report/tests" % name)
                    continue
                text = " ".join(msgs)
                if "do not close a loop" not in text:
                    errors.append("%s refusal text lacks 'do not close a "
                                  "loop': %s" % (name, msgs))
                elif ("%s meets only 0 of the other 3 edges" % outer) not in text:
                    errors.append("%s refusal does not name %s as sharing "
                                  "no corner: %s" % (name, outer, msgs))
    if not skipped_patch:
        checks.append("patch attempt: 1 built (Right), 4 refused -- the "
                      "refusals name the outer edge that meets only 0 of "
                      "the other 3")

    # ---- Blends / corner: unreachable from one patch. Record the exact
    # dead end instead of forcing it.
    inventory = OPS.seam_inventory(doc)
    if inventory:
        errors.append("seam_inventory found %d seam(s) from one patch: %s"
                      % (len(inventory), [e["edge"].Name for e in inventory]))
    else:
        checks.append("seam inventory empty: one patch, no shared edge")
    with _CaptureConsole() as cap:
        blend = OPS.create_blend_by_edge(edges.get("E_right_FR"),
                                         name="B_Right_FR")
        msgs = cap.errors
        if blend is not None:
            errors.append("a blend built on E_right_FR: %s" % blend.Name)
        elif not any("is a boundary of" in m and "P_Right" in m for m in msgs):
            errors.append("blend refusal text unexpected: %s" % msgs)
    with _CaptureConsole() as cap:
        corner = OPS.create_corner_blend([], name="CB_dead_end")
        msgs = cap.errors
        if corner is not None:
            errors.append("a corner built from an empty ring: %s" % corner.Name)
        elif not any("cannot create a corner blend from 0 blends" in m
                     for m in msgs):
            errors.append("corner refusal text unexpected: %s" % msgs)
        else:
            checks.append("corner attempt refused: %s"
                          % msgs[0].strip().split("\n")[0])
    return {"pass": not errors, "errors": errors, "checks": checks}


def test_demo01_whole_sketch_edges_cannot_bound_the_ring_faces(doc):
    """The demo's OWN sketches (opened read-only, never saved): 12 Edges
    build and are pole-identical to the stored `ControlPoly4` objects, the
    Right end cap builds as one Patch, and the four rib-bounded faces are
    REFUSED with the exact "do not close a loop" text naming the outer
    cross-section edge that shares no corner.  No seam, no blend, no
    junction is reachable from whole sketches -- the limitation the fixture's
    half-rib supplement exists to remove."""
    demo, opened = _open_read_only(DEMO01_PATH)
    try:
        outcome = _whole_sketch_attempt(demo, doc, legacy=LEGACY_POLYS)
        _report(["demo's own 29 sketches: 12 whole-sketch Edges, 1 of 5 "
                 "faces reachable, 0 seams"])
        return outcome
    finally:
        if opened:
            FreeCAD.closeDocument(demo.Name)


# ---------------------------------------------------------------------------
# 2. the fixture rebuild: the achieved outcome, pole-for-pole
# ---------------------------------------------------------------------------

def test_demo01_fixture_rebuild_reaches_the_demo_topology(doc):
    """The fixture's click-through, driven by the ops layer: 12 Edges ->
    5 Patches -> 8 Blends -> 4 CornerBlends, every object oracle-green (the
    one inherited E2 deviation aside), every Edge pole-identical to the
    demo's stored curve and every Patch's net the demo's stored
    `ControlGrid44_4_*` net up to a named square symmetry."""
    errors, checks, report = [], [], []
    result = MODEL.build(doc)
    errors.extend(result["problems"])

    counts = (len(result["edges"]), len(result["patches"]),
              len(result["blends"]), len(result["corners"]))
    if counts != (12, 5, 8, 4):
        errors.append("fixture rebuild reached %d edges / %d patches / "
                      "%d blends / %d corners, want 12/5/8/4" % counts)
    else:
        checks.append("click-through: 12 Edges -> 5 Patches -> 8 Blends -> "
                      "4 CornerBlends")
    report.append("counts: %d edges, %d patches, %d blends, %d corners"
                  % counts)

    # ---- oracle green, per object
    for name, bad in sorted(result["edge_checks"].items()):
        if not bad:
            continue
        if (name == KNOWN_E2_EDGE and len(bad) == 1
                and bad[0][0] == "E2_pole_order"):
            checks.append("check_edge %s: E2 pole-order deviation %s "
                          "inherited from the demo's own 2N poly"
                          % (name, bad[0][1]))
        else:
            errors.append("check_edge %s: %s" % (name, bad))
    green_edges = sorted(n for n, bad in result["edge_checks"].items()
                         if not bad)
    checks.append("check_edge GREEN on %d/%d edges (%s)"
                  % (len(green_edges), len(result["edges"]),
                     ", ".join(green_edges)))
    report.append("check_edge GREEN on %d/12; %s carries the inherited E2 "
                  "%s" % (len(green_edges), KNOWN_E2_EDGE,
                          result["edge_checks"].get(KNOWN_E2_EDGE)))

    for name, bad in sorted(result["patch_checks"].items()):
        if bad:
            errors.append("check_patch %s: %s" % (name, bad))
    for name, bad in sorted(result["blend_checks"].items()):
        if bad:
            errors.append("check_blend %s: %s" % (name, bad))
    if not any("check_patch" in e for e in errors):
        checks.append("check_patch GREEN on all %d patches (own Edges cycle)"
                      % len(result["patches"]))
    if not any("check_blend" in e for e in errors):
        checks.append("check_blend GREEN on all %d blends" % len(result["blends"]))

    for name, corner in sorted(result["corners"].items()):
        problems = []
        if len(corner.Poles or []) != 36:
            problems.append("%d poles" % len(corner.Poles or []))
        if not corner.Shape or corner.Shape.isNull() or not corner.Shape.Faces:
            problems.append("empty Shape")
        elif not corner.Shape.isValid():
            problems.append("invalid Shape")
        if problems:
            errors.append("corner %s: %s" % (name, problems))
    if not any(e.startswith("corner ") for e in errors):
        checks.append("all %d corners: 36 poles, valid non-empty Shape"
                      % len(result["corners"]))
        for name, corner in sorted(result["corners"].items()):
            report.append("corner %-24s %d poles, %d face(s), valid=%s"
                          % (name, len(corner.Poles),
                             len(corner.Shape.Faces),
                             corner.Shape.isValid()))

    # ---- seam inventory: 8 seams, all blended
    blended = [n for n, status in result["seam_inventory"]
               if status == "blended"]
    if len(result["seam_inventory"]) != 8 or len(blended) != 8:
        errors.append("seam inventory is %s, want 8 seams all 'blended'"
                      % (result["seam_inventory"],))
    else:
        checks.append("seam inventory: 8 seams, all 'blended'")

    # ---- pole parity against the demo's stored legacy objects
    demo, opened = _open_read_only(DEMO01_PATH)
    try:
        for name, sketches, legacy_name in MODEL.EDGES:
            edge = result["edges"].get(name)
            if edge is None:
                continue
            reference = demo.getObject(legacy_name).Poles
            delta = MODEL.straight_pole_delta(list(edge.Poles), reference)
            report.append("edge %-16s vs %-24s delta %.3e"
                          % (name, legacy_name, delta))
            if delta > _POLE_TOL:
                errors.append("edge %s vs %s: max pole delta %.3e"
                              % (name, legacy_name, delta))
        for name, order, grid in MODEL.PATCHES:
            patch = result["patches"].get(name)
            if patch is None:
                continue
            reference = demo.getObject(grid).Poles
            raw = MODEL.straight_pole_delta(list(patch.Poles), reference)
            transform, delta = MODEL.pole_parity(list(patch.Poles), reference)
            report.append("patch %-9s vs %-22s %-16s delta %.3e "
                          "(raw-order delta %.3e)"
                          % (name, grid, transform, delta, raw))
            if delta > _POLE_TOL:
                errors.append("patch %s vs %s: best dihedral image %s still "
                              "differs by %.3e" % (name, grid, transform,
                                                   delta))
        checks.append("every Edge is pole-identical to the demo's stored "
                      "ControlPoly4 (max delta <= %.0e)" % _POLE_TOL)
        checks.append("every Patch net IS the demo's stored "
                      "ControlGrid44_4_* net up to a named square symmetry "
                      "(max delta <= %.0e)" % _POLE_TOL)
    finally:
        if opened:
            FreeCAD.closeDocument(demo.Name)

    _report(report)
    return {"pass": not errors, "errors": errors, "checks": checks}


# ---------------------------------------------------------------------------
# 3. the click order is NOT part of the result: the demo's own order fills too
# ---------------------------------------------------------------------------

def test_demo01_demo_order_patches_fill_their_corners(doc):
    """The demo's own stored grid order (its `Poly0..Poly3` links) is the
    order in which every face compares pole-for-pole with NO transform, and
    it now fills every junction too (#107).

    Until #107 this was the order in which no junction could be filled:
    each corner refused with "its two patches disagree about which end is
    the junction (twisted input)", because the corner stage treated a patch
    that parameterizes the shared seam the other way round -- and a blend
    whose `PatchA`/`PatchB` order differs from the ring's direction -- as
    errors. The nets are the same under either order; the order was a
    parameterization constraint of the corner stage, and that constraint is
    gone: the demo's order yields the SAME 36 poles the documented order
    does.
    """
    errors, checks, report = [], [], []
    result = MODEL.build_demo_order_patches(doc)
    counts = (len(result.get("edges", {})), len(result.get("patches", {})),
              len(result.get("blends", {})))
    if counts != (12, 5, 8):
        errors.append("demo-order build reached %d/%d/%d, want 12/5/8"
                      % counts)
    else:
        checks.append("demo-order build: 12 Edges -> 5 Patches -> 8 Blends")

    # every face pole-identical in the RAW order under this order
    demo, opened = _open_read_only(DEMO01_PATH)
    try:
        for name, order, grid in MODEL.PATCHES:
            patch = result["patches"].get(name)
            if patch is None:
                continue
            reference = demo.getObject(grid).Poles
            raw = MODEL.straight_pole_delta(list(patch.Poles), reference)
            report.append("demo-order patch %-9s vs %-22s raw delta %.3e"
                          % (name, grid, raw))
            if raw > _POLE_TOL:
                errors.append("demo-order patch %s vs %s: raw pole delta "
                              "%.3e" % (name, grid, raw))
    finally:
        if opened:
            FreeCAD.closeDocument(demo.Name)

    # all four junctions fill, 36 poles / one valid face each
    corners = result.get("corners", {})
    want = {name for name, _ring, _pt in MODEL.CORNERS}
    if set(corners) != want:
        errors.append("demo-order build filled %s, want all four %s"
                      % (sorted(corners), sorted(want)))
    else:
        checks.append("demo-order build fills all 4 junctions")
        for name, corner in sorted(corners.items()):
            problems = []
            if len(corner.Poles or []) != 36:
                problems.append("%d poles" % len(corner.Poles or []))
            if not corner.Shape or corner.Shape.isNull() \
                    or not corner.Shape.Faces:
                problems.append("empty Shape")
            elif not corner.Shape.isValid():
                problems.append("invalid Shape")
            if problems:
                errors.append("demo-order corner %s: %s"
                              % (name, "; ".join(problems)))
            else:
                report.append("demo-order corner %-24s %d poles, %d face(s), "
                              "valid=%s"
                              % (name, len(corner.Poles),
                                 len(corner.Shape.Faces),
                                 corner.Shape.isValid()))
    if not any(e.startswith("demo-order corner") for e in errors) \
            and result.get("corners"):
        checks.append("all 4 demo-order corners: 36 poles, valid Shape")

    # ...and they are the SAME fill the documented order produced: the
    # corner no longer depends on the click order (#107).  The reference
    # runs in its own document -- the same `doc` already holds this build.
    ref_doc = FreeCAD.newDocument("_demo01_doc_order_ref")
    try:
        doc_order = MODEL.build(ref_doc)
        ref_poles = {n: list(c.Poles)
                     for n, c in doc_order.get("corners", {}).items()}
    finally:
        FreeCAD.closeDocument(ref_doc.Name)
        FreeCAD.setActiveDocument(doc.Name)
    for name, _ring, _pt in MODEL.CORNERS:
        a = result.get("corners", {}).get(name)
        b = ref_poles.get(name)
        if a is None or b is None:
            continue
        dev = max((x - y).Length for x, y in zip(a.Poles, b))
        report.append("corner %-24s demo-order vs documented-order dev %.3e"
                      % (name, dev))
        if dev > 1e-9:
            errors.append("corner %s: the demo's own order gives a different "
                          "fill (max pole dev %.3e)" % (name, dev))
    if not any("gives a different fill" in e for e in errors) \
            and result.get("corners"):
        checks.append("demo-order fill = documented-order fill "
                      "(max pole dev <= 1e-9): the click order no longer "
                      "changes the corner")
    _report(report)
    return {"pass": not errors, "errors": errors, "checks": checks}


ALL_TESTS = [
    test_demo01_whole_sketch_edges_cannot_bound_the_ring_faces,
    test_demo01_fixture_rebuild_reaches_the_demo_topology,
    test_demo01_demo_order_patches_fill_their_corners,
]
