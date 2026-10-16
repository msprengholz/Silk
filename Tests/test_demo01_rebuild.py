"""Demo 01 rebuild attempt (ticket #98): the mapping, measured.

This module drives `Resources/Demo_files/Silk_Demo_01.FCStd`'s stored
inputs through the shop-floor ops layer (`SilkWorkflowOps`: Edge ->
Patch -> Blend -> CornerBlend) and records, honestly, how far the
pipeline reaches. It asserts the steps that succeed and pins the exact
refusals of the steps that do not -- a future capability that makes a
refused step build will turn this module red on purpose.

The mapping (derived from the demo's `Document.xml` link graph; the full
tables are `docs/research/silk-demo-01-inventory.md`): 16 of the demo's
29 sketches feed 12 whole-sketch Edges --

  * 4 outer cross-section edges  (Sketch015/016/017/018)
  * 4 rib curves                 (Sketch020/022/024/026)
  * 4 node-pair (2N) hoop edges  (036+037, 038+039, 042+045, 032+035)

-- and the demo's five ring faces are bounded by those curves. But the
faces use **HALF-ribs**: the demo stores `ControlPoly4_segment` pieces
of u in [0.5, 1] for every rib (e.g. `ControlPoly4_segment001` =
Sketch020 at u in (0.5, 1.0)), and the other half belongs to the model's
mirrored side (the file stores half the shape; `Base_Surface_Mirrors`
mirrors it). A Silk Edge consumes a whole sketch -- it has no trim --
so a rebuilt front/top/bottom/back boundary loop made of full ribs does
not close: each rib's u=0.5 point sits on the symmetry plane (measured:
Sketch020 -> (0,0,0), Sketch022 -> (0,0,50), Sketch024 -> (170,0,0),
Sketch026 -> (185,0,70)), while the outer loop's corners are at the
hoop edges' ends.

The measured outcome, asserted below:

  * all 12 Edges build, match the measured mapping, and are
    **pole-identical to the demo's stored `ControlPoly4` objects**
    (measured max delta 0.0) -- `check_edge` is green except the
    Bottom_Right hoop edge, whose E2 pole-spacing deviation is
    **inherited from the demo's own `ControlPoly4_2N003`** (the same
    inequality holds on the legacy poles; verified in the test);
  * the **Right** face (the end cap -- its four boundary curves ARE the
    whole 2N sketches) rebuilds as one Patch and passes `check_patch`;
  * the other four faces are REFUSED by `create_patch` with the exact
    "do not close a loop" text naming the outer edge that shares no
    corner;
  * no seam can be blended (each hoop edge then has exactly one patch)
    and no junction can be attempted -- `create_corner_blend` refuses
    the empty ring; the front/top/right junction's other two strips
    need the refused patches.

No continuity label is asserted anywhere in this module.
"""

import os

import FreeCAD

import SilkChecks
import SilkWorkflowOps as OPS

_SILK_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEMO01_PATH = os.path.join(_SILK_DIR, "Resources", "Demo_files",
                           "Silk_Demo_01.FCStd")
FIXTURE_PATH = os.path.join(_SILK_DIR, "Resources", "Test_files", "examples",
                            "SketchOnly_Demo01Subset.FCStd")

# (edge name, sketches it consumes, measured u=0 end, measured u=1 end,
#  measured u=0.5 point for ribs -- the symmetry-plane corner the HALF
#  segment ends at -- or None)
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

# (patch name, edge cycle, verdict, the edge named by the refusal)
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

# The demo's stored legacy ControlPoly4 objects the 12 Edges rebuild from.
# Pole parity against these (delta <= _POLE_TOL) is the strong oracle; it
# was measured at exactly 0.0 on every edge.
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

# check_edge's E2 heuristic (step <= 1.05 * skip) is violated by the
# demo's OWN stored Bottom_Right hoop poly (ControlPoly4_2N003):
# p2->p3 = 70.711 > 1.05 * p2->p0 = 63.246. The rebuilt edge is
# pole-identical to that legacy object, so the deviation is inherited from
# the demo's input geometry, not introduced by the rebuild. Accepted for
# exactly this edge and name; verified against the legacy poles below.
KNOWN_E2_EDGE = "E_right_BR"


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
    same name. Constraints are not needed to build an Edge (the ops layer
    and the classifier read Geometry/Placement)."""
    src = source_doc.getObject(name)
    dst = target_doc.addObject("Sketcher::SketchObject", name)
    dst.Placement = src.Placement
    for g in src.Geometry:
        dst.addGeometry(g, False)
    return dst


def _attempt_rebuild(source_doc, doc, legacy=None):
    """Run the whole rebuild attempt from `source_doc`'s sketches into the
    harness scratch `doc`. `legacy` (optional) maps edge name -> the demo's
    stored ControlPoly4 object name for pole parity. Returns
    {pass, errors, checks}."""
    errors, checks = [], []
    FreeCAD.setActiveDocument(doc.Name)
    for _name, sketches, _p0, _p1, _mid in EDGE_MAP:
        for sk in sketches:
            _copy_sketch(doc, source_doc, sk)
    doc.recompute()

    # ---- Edges: all 12 must build, match the measured geometry, and
    # pass check_edge (with the one inherited E2 deviation documented).
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
        checks.append("%d/%d edges build, geometry matches the measured "
                      "demo mapping" % (len(edges), len(EDGE_MAP)))

    # ---- Pole parity against the demo's stored ControlPoly4 objects
    # (only when the caller supplies the mapping).
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

    # ---- Patches: only the Right end cap closes. The four refused loops
    # must name their outer cross-section edge as meeting 0 others.
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


def test_demo01_rebuild_attempt_from_demo_sketches(doc):
    """The whole attempt, driven from the demo's own sketches (the demo is
    opened read-only and never saved). The rebuilt Edges are additionally
    checked pole-for-pole against the demo's stored `ControlPoly4` objects
    -- measured at exactly zero delta on all 12."""
    demo, opened = _open_read_only(DEMO01_PATH)
    try:
        return _attempt_rebuild(demo, doc, legacy=LEGACY_POLYS)
    finally:
        if opened:
            FreeCAD.closeDocument(demo.Name)


def test_demo01_fixture_reproduces_demo_edge_geometry(doc):
    """The durable fixture's sketches must reproduce the demo's measured
    edge geometry, not just its names -- the click-through and rebuild
    rounds rely on it. Runs the same attempt as the demo test; the pole
    parity against the stored legacy objects is asserted there (this test
    never opens the demo file)."""
    fixture, opened = _open_read_only(FIXTURE_PATH)
    try:
        return _attempt_rebuild(fixture, doc)
    finally:
        if opened:
            FreeCAD.closeDocument(fixture.Name)


ALL_TESTS = [
    test_demo01_rebuild_attempt_from_demo_sketches,
    test_demo01_fixture_reproduces_demo_edge_geometry,
]
