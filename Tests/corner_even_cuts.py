#!/usr/bin/env python3
"""Tests/corner_even_cuts.py -- the corner's cuts measured in MILLIMETRES (#129).

**What it answers.**  The corner stage used to place its rolling cut as a
FRACTION of each seam curve's own parameter, and a fraction is not a length:
on the demo's `CB_J1_FrontTopRight` the same 0.25 cuts 14.3 mm of one seam
and 57.6 mm of the other, so the triangular member came out a 9 mm x 35 mm
sliver where the maintainer's is a near-even triangle.  The owner's rule
(2026-10-22): *"ideally both segment lengths should be close to the same
absolute length (not u or v values between 0 and 1, but the actual length in
eg. mm). this ensures a neat, closer to even sided triangle, and with that a
nicer surface for both the tri and quad patch."*

This instrument reads, on BOTH fixtures and for BOTH placements:

  * the two cut lengths in mm -- the tri's own sides, the arc from each
    seam's SETBACK to its cut (`SilkWorkflowOps.seam_cut_length`), beside the
    corner distance and the parameter that lengths lands on;
  * the tri and the quad areas and their ratio (the maintainer's own corner
    reads 0.28: 1439.90 / 5187.83 mm^2);
  * the tri's interior, measured to the quad, as a fraction of the corner's
    extent (his: 16 %..62 %);
  * the quad's STRETCH: its bounding box, and the mean / worst adjacent pole
    pitch of the 6x6 net in each direction;
  * the fold readings the corner is already pinned on -- normal-field flips
    at n = 39/81/150 on the Part surface, coincident pole pairs -- so the
    change cannot hide a regression behind a nicer triangle;
  * the length instrument's own ERROR FLOOR: the same seam measured at 64,
    256 and 1024 stations, and the residual left after equalising.

**How it runs.**  Inside the owner's running FreeCAD, over XML-RPC (never
spawns one):

    flock /tmp/silk_rpc.lock -c "python3 Tests/corner_even_cuts.py"

and it leaves the demo model with its equalised corner OPEN as
`Resources/Test_files/_inspect/demo_corner_even.FCStd` -- every role the
corner builds named, nothing rendered.

**What it does NOT do.**  It asserts nothing: it is an instrument, and its
raw output is the measurement the change is decided on.
"""

import os
import sys

# --- manual tier ------------------------------------------------------
# A measurement script, not a test module (the name is not `test_*`), so the
# suite never collects it -- stated here so the marker rule sees it.
MANUAL = True

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HERE = os.path.dirname(os.path.abspath(__file__))
RPC_HOST = "127.0.0.1"
RPC_PORT = 9875

ARTIFACT = os.path.join(REPO, "Resources", "Test_files", "_inspect",
                        "demo_corner_even.FCStd")

# The demo junction and its ring (Tests/demo01_fixture_model.CORNERS[0]).
DEMO_CORNER = "CB_J1_FrontTopRight"
DEMO_RING = ("B_FT", "B_FR", "B_TR")
DEMO_MEMBER_PATCH = "P_Top"

# The maintainer's own corner, for the two figures his file gives
# (`docs/research/silk-rolling-corner-66.md`): tri/quad area ratio, and the
# tri's interior distance from the quad as a fraction of the corner's extent.
HIS_AREA_RATIO = 1439.90 / 5187.83          # 0.2776
HIS_TRI_QUAD_PERCENT = (16.0, 62.0)

# The station counts the length instrument's floor is read at: the corner
# stage's own (`SilkMachinery.SEAM_LENGTH_STATIONS`) and two refinements.
STATION_SWEEP = (64, 256, 1024)


# ---------------------------------------------------------------------------
# The in-FreeCAD half
# ---------------------------------------------------------------------------

def measure():
    """Print the millimetre table for both fixtures, both placements.
    RUNS INSIDE FREECAD."""
    import FreeCAD
    import demo01_fixture_model as DEMO
    import cube_corner_model as CCM
    import SilkCorner as SC
    import SilkMachinery as SM
    import SilkWorkflowOps as OPS

    out = []

    def emit(line=""):
        out.append(line)

    def make_doc(label):
        for name, d in list(FreeCAD.listDocuments().items()):
            if d.Label == label:
                FreeCAD.closeDocument(name)
        doc = FreeCAD.newDocument(label)
        FreeCAD.setActiveDocument(doc.Name)
        return doc

    emit("=" * 78)
    emit("THE LENGTH INSTRUMENT'S FLOOR (`SilkMachinery.seam_length`)")
    emit("=" * 78)
    floor_doc = make_doc("_even_floor")
    DEMO.build(floor_doc, corners=False)
    floor_doc.recompute()
    patch = floor_doc.getObject(DEMO_MEMBER_PATCH)
    strips = [floor_doc.getObject(n) for n in DEMO_RING]
    reach, _why = OPS.seam_cut_reach(strips[0], patch, ring=strips)
    # the interval under discussion: the demo's equalised cut, placed once,
    # then measured at three station counts -- the spread IS the floor
    param, _why = SM.seam_parameter_at_length(
        patch, reach["side"], reach["setback"], reach["t_far"], 17.435446)
    emit("  the interval under discussion: %.6f mm of the %s seam on %s, "
         "placed at parameter %.9f"
         % (17.435446, strips[0].Name, patch.Name, param))
    readings = []
    for stations in STATION_SWEEP:
        total = SM.seam_length(patch, reach["side"], 0.0, 1.0,
                               stations=stations)
        cut = SM.seam_length(patch, reach["side"], reach["setback"], param,
                             stations=stations)
        readings.append((stations, total, cut))
        emit("  %-5d stations: whole seam %.9f mm, the cut side %.9f mm"
             % (stations, total, cut))
    emit("  -> the floor on a cut side: %.3e mm (64 vs 1024 stations, %.1e "
         "relative); on the whole seam %.3e mm"
         % (abs(readings[0][2] - readings[-1][2]),
            abs(readings[0][2] - readings[-1][2]) / readings[-1][2],
            abs(readings[0][1] - readings[-1][1])))
    _close(FreeCAD, floor_doc)

    emit("")
    emit("=" * 78)
    emit("THE CUBE, BIT FOR BIT: explicit `leader=0.25` vs the equalising "
         "default")
    emit("=" * 78)
    for line in _cube_identity(make_doc, FreeCAD, CCM, SC, OPS):
        emit(line)

    emit("")
    emit("=" * 78)
    emit("THE RULE, SCANNED: the demo's corner at every candidate equal "
         "length")
    emit("=" * 78)
    for line in _rule_scan(make_doc, FreeCAD, DEMO, SC, SM, OPS):
        emit(line)

    for label, kind in (("CUBE  Tests/cube_corner_model.py", "cube"),
                        ("DEMO  %s (member patch %s)"
                         % (DEMO_CORNER, DEMO_MEMBER_PATCH), "demo")):
        for mode in ("before", "after"):
            emit("")
            emit("=" * 78)
            emit("%s -- %s" % (label, MODE_TITLE[mode]))
            emit("=" * 78)
            for line in _one(kind, mode, make_doc, FreeCAD, DEMO, CCM, SC,
                             SM, OPS):
                emit(line)
    return out


MODE_TITLE = {
    "before": "the PARAMETER placement (`ROLLING_LEADER` = 0.25 of each "
              "seam's parameter, placed by length)",
    "after": "the EQUALISED placement (the default: both cut sides the same "
             "mm)",
}


def _one(kind, mode, make_doc, FreeCAD, DEMO, CCM, SC, SM, OPS):
    out = []

    def emit(line=""):
        out.append(line)

    doc = make_doc("_even_%s_%s" % (kind, mode))
    if kind == "cube":
        CCM.build_cube_corner_model(doc)
        doc.recompute()
        doc.recompute()
        strips = [doc.getObject(n) for n in ("B_AB", "B_BC", "B_CA")]
        member_patch_hint = doc.getObject("PatchA")
    else:
        DEMO.build(doc, corners=False)
        doc.recompute()
        doc.recompute()
        strips = [doc.getObject(n) for n in DEMO_RING]
        member_patch_hint = doc.getObject(DEMO_MEMBER_PATCH)

    # BEFORE is the parameter default, expressed in the stage's own unit: the
    # length `ROLLING_LEADER` lands at on each seam.  So the "before" corner is
    # built through the SAME length path -- it is the same geometry the old
    # fraction produced, not a second implementation of it.
    pin, _why = SC.corner_member_pin(strips)
    patch = pin[0] if pin is not None else member_patch_hint
    kw = {}
    if mode == "before":
        leaders = {}
        for s in strips:
            if patch not in (getattr(s, "PatchA", None),
                             getattr(s, "PatchB", None)):
                continue
            length, _w = OPS.seam_default_leader(s, patch, ring=strips)
            leaders[s.Name] = length
        kw["leaders"] = leaders
        emit("the parameter 0.25, as lengths: %s"
             % ", ".join("%s %.6f mm" % kv for kv in sorted(leaders.items())))
    corner = OPS.create_corner_blend(*strips, name="Even", **kw)
    doc.recompute()
    doc.recompute()
    if corner is None or not corner.Poles:
        emit("  the corner stage built NOTHING (see the console)")
        _close(FreeCAD, doc)
        return out

    member = None
    for o in doc.Objects:
        if getattr(o, "object_type", "") == "RollingMemberFace" \
                and getattr(o, "Corner", None) is corner:
            member = o
    if member is None:
        emit("  no triangular member on this corner")
        _close(FreeCAD, doc)
        return out

    # -- the two cut lengths -------------------------------------------
    emit("")
    emit("  THE TWO CUTS (the tri's own sides: setback -> cut, mm)")
    emit("    %-7s %-3s %-8s %-9s %-9s %-9s %-13s %s"
         % ("seam", "ax", "junction", "corner->sb", "cut side", "setback",
            "leader param", "reachable max"))
    legs = []
    for s in strips:
        if patch not in (getattr(s, "PatchA", None),
                         getattr(s, "PatchB", None)):
            continue
        reach, why = OPS.seam_cut_reach(s, patch, ring=strips)
        if reach is None:
            emit("    %-7s REFUSED: %s" % (s.Name, why))
            continue
        leg, _w = OPS.seam_cut_length(s, patch, ring=strips)
        legs.append(leg)
        emit("    %-7s %-3s end %-5d %9.6f %9.6f %9.6f %-13.9f %9.6f"
             % (s.Name, reach["along"], reach["corner_end"],
                reach["corner_mm"], leg, reach["setback"],
                _leader_param(patch, reach), reach["max_mm"]))
    if len(legs) == 2:
        emit("    the two cut sides: %.6f and %.6f mm -- difference %.3e mm "
             "(%.1f %% of the shorter)"
             % (legs[0], legs[1], abs(legs[0] - legs[1]),
                abs(legs[0] - legs[1]) / min(legs) * 100.0))

    # -- areas ---------------------------------------------------------
    bb = corner.Shape.BoundBox
    extent = max(bb.XLength, bb.YLength, bb.ZLength) or 1.0
    ratio = member.Shape.Area / corner.Shape.Area if corner.Shape.Area else 0.0
    emit("")
    emit("  AREAS: quad %.6f mm^2, tri %.6f mm^2, tri/quad %.4f "
         "(his %.4f)" % (corner.Shape.Area, member.Shape.Area, ratio,
                         HIS_AREA_RATIO))
    ds = _interior_distances(member.Shape, corner.Shape)
    emit("  TRI INTERIOR -> QUAD: %.6f .. %.6f mm = %.2f %%..%.2f %% of the "
         "corner's %.4f mm extent (his %.0f..%.0f %%)"
         % (min(ds), max(ds), min(ds) / extent * 100.0,
            max(ds) / extent * 100.0, extent,
            HIS_TRI_QUAD_PERCENT[0], HIS_TRI_QUAD_PERCENT[1]))

    # -- the quad's stretch -------------------------------------------
    pitch_u, pitch_v = _pole_pitches(list(corner.Poles))
    emit("  QUAD STRETCH: bbox %.4f x %.4f x %.4f mm; adjacent pole pitch "
         "along U %.6f..%.6f mm, along V %.6f..%.6f mm; worst/best pitch "
         "%.2f (two directions), %.2f (one)"
         % (bb.XLength, bb.YLength, bb.ZLength, pitch_u[0], pitch_u[1],
            pitch_v[0], pitch_v[1],
            max(pitch_u[1], pitch_v[1]) / min(pitch_u[0], pitch_v[0]),
            max(pitch_u[1] / pitch_u[0], pitch_v[1] / pitch_v[0])))
    emit("  TRI SIDES: %s mm, chord %.6f mm"
         % (", ".join("%.6f" % e.Length for e in member.Shape.Edges
                      if e.Length > 1e-9), _chord(member.Shape)))

    # -- the readings the change must not move -------------------------
    import SilkChecks
    flips = [len(SilkChecks._normal_field_flips(
        corner.Shape.Faces[0].Surface, n=n)[0]) for n in (39, 81, 150)]
    emit("  FOLDS: quad normal-field flips n=39/81/150 %r; the 6x6's "
         "coincident pole pairs %d/630; collapsed side %r"
         % (flips, _coins(list(corner.Poles)),
            SM._collapsed_side(list(corner.Poles), 1e-6)))
    emit("  construction %r, %d objects in the tree"
         % (SC.corner_construction(corner)[0], len(doc.Objects)))
    _close(FreeCAD, doc)
    return out


def _leader_param(patch, reach):
    """The LEADER CUT parameter `patch` carries on this seam's axis, or 0."""
    import SilkMachinery as SM
    l1, l2 = SM.leader_pair(patch, reach["along"])
    return l1 if reach["corner_end"] == 0 else l2


def _cube_identity(make_doc, FreeCAD, CCM, SC, OPS):
    """The cube corner built twice: once at `leader=0.25` (what every pinned
    number in the suite passes) and once at the equalising default.  The
    poles, the weights and the tri's poles are compared element by element."""
    out = []
    built = {}
    for mode in ("before", "after"):
        doc = make_doc("_even_identity_%s" % mode)
        CCM.build_cube_corner_model(doc)
        doc.recompute()
        doc.recompute()
        strips = [doc.getObject(n) for n in ("B_AB", "B_BC", "B_CA")]
        if mode == "before":
            kw = {"leader": 0.25}
        else:
            kw = {}
        corner = OPS.create_corner_blend(*strips, name="Id", **kw)
        doc.recompute()
        doc.recompute()
        member = [o for o in doc.Objects
                  if getattr(o, "object_type", "") == "RollingMemberFace"][0]
        built[mode] = ([tuple(p) for p in corner.Poles],
                       [float(w) for w in corner.Weights],
                       [tuple(p) for p in member.Poles],
                       [float(w) for w in member.Weights])
        _close(FreeCAD, doc)
    a, b = built["before"], built["after"]
    for k, name in enumerate(("quad poles", "quad weights", "tri poles",
                              "tri weights")):
        if k in (0, 2):
            delta = max((FreeCAD.Vector(*x) - FreeCAD.Vector(*y)).Length
                        for x, y in zip(a[k], b[k]))
        else:
            delta = max(abs(x - y) for x, y in zip(a[k], b[k]))
        out.append("  %-12s %3d entries, worst |before - after| = %.3e"
                   % (name, len(a[k]), delta))
    out.append("  (the unit cube makes 0.25 mm the parameter 0.25, and the two "
               "cuts are already equal at 0.15 mm each -- so the default does "
               "not move the cube)")
    return out


def _rule_scan(make_doc, FreeCAD, DEMO, SC, SM, OPS):
    """The demo's corner at every candidate EQUAL length, so the rule is a
    measurement and not a preference.

    The seeds are the two cuts the stage's parameter default makes (9.302915
    and 32.677217 mm); `min` shrinks the longer to the shorter, `max` grows
    the shorter to the longer, `geomean` keeps the triangle's AREA, and `mean`
    is the midpoint of the two."""
    import SilkChecks
    import corner_even_cuts as E
    out = []
    seeds = None
    rows = []
    for label, T in (("min (shrink to the shorter)", "min"),
                     ("13.0 mm", 13.0),
                     ("GEOMEAN (the rule)", "geomean"),
                     ("arithmetic mean", "mean"),
                     ("26.0 mm", 26.0),
                     ("max (grow to the longer)", "max")):
        doc = make_doc("_even_scan")
        DEMO.build(doc, corners=False)
        doc.recompute()
        doc.recompute()
        strips = [doc.getObject(n) for n in DEMO_RING]
        pin, _why = SC.corner_member_pin(strips)
        patch = pin[0]
        if seeds is None:
            seeds = []
            for st in strips:
                if patch in (getattr(st, "PatchA", None),
                             getattr(st, "PatchB", None)):
                    seeds.append(OPS.seam_default_leader(st, patch,
                                                         ring=strips)[0])
        old = OPS.equal_cut_length
        if T == "min":
            OPS.equal_cut_length = lambda cuts: min(cuts)
        elif T == "max":
            OPS.equal_cut_length = lambda cuts: max(cuts)
        elif T == "mean":
            OPS.equal_cut_length = lambda cuts: sum(cuts) / float(len(cuts))
        elif T == "geomean":
            OPS.equal_cut_length = old
        else:
            OPS.equal_cut_length = lambda cuts, _t=float(T): _t
        try:
            corner = OPS.create_corner_blend(*strips, name="Scan")
        finally:
            OPS.equal_cut_length = old
        doc.recompute()
        doc.recompute()
        member = [o for o in doc.Objects
                  if getattr(o, "object_type", "") == "RollingMemberFace"][0]
        bb = corner.Shape.BoundBox
        extent = max(bb.XLength, bb.YLength, bb.ZLength)
        ds = _interior_distances(member.Shape, corner.Shape)
        pu, pv = _pole_pitches(list(corner.Poles))
        flips = [len(SilkChecks._normal_field_flips(
            corner.Shape.Faces[0].Surface, n=n)[0]) for n in (39, 81, 150)]
        legs = [OPS.seam_cut_length(st, patch, ring=strips)[0]
                for st in strips
                if patch in (getattr(st, "PatchA", None),
                             getattr(st, "PatchB", None))]
        rows.append((label, min(legs), member.Shape.Area, corner.Shape.Area,
                     member.Shape.Area / corner.Shape.Area,
                     min(ds) / extent * 100.0, max(ds) / extent * 100.0,
                     max(pu[1], pv[1]) / min(pu[0], pv[0]), flips,
                     _coins(list(corner.Poles))))
        _close(FreeCAD, doc)
    out.append("  the corner distances the parameter default makes: %s mm "
               "(their cut sides are the table's min and max rows)"
               % ", ".join("%.6f" % v for v in seeds))
    out.append("  %-28s %9s %10s %10s %7s %14s %8s %s"
               % ("rule", "cut mm", "tri mm^2", "quad mm^2", "ratio",
                  "tri% of extent", "stretch", "flips/coins"))
    for (label, leg, tri, quad, ratio, lo, hi, stretch, flips,
         coins) in rows:
        out.append("  %-28s %9.4f %10.4f %10.4f %7.4f %6.2f..%6.2f %8.2f "
                   "%r/%d"
                   % (label, leg, tri, quad, ratio, lo, hi, stretch, flips,
                      coins))
    out.append("  his corner: ratio %.4f, tri %.0f..%.0f %% of the extent"
               % (HIS_AREA_RATIO, HIS_TRI_QUAD_PERCENT[0],
                  HIS_TRI_QUAD_PERCENT[1]))
    return out


def _interior_distances(tri_shape, quad_shape, grid=8):
    """Every interior sample of the tri's face, to the quad shape."""
    import Part
    face = tri_shape.Faces[0]
    b = face.Surface.bounds()
    umin, umax, vmin, vmax = b[0], b[1], b[2], b[3]
    out = []
    for a in range(1, grid):
        for c in range(1, grid):
            pt = face.Surface.value(umin + (umax - umin) * a / float(grid),
                                    vmin + (vmax - vmin) * c / float(grid))
            out.append(Part.Vertex(pt).distToShape(quad_shape)[0])
    return out


def _pole_pitches(poles):
    """(min, max) adjacent-pole distance along U and along V of a 6x6 net.

    The 6x6 is flat `V*6 + U` (`SilkMachinery.control_grid66_4sub`), so a row
    step is one U pitch and a column step one V pitch."""
    def steps(along_u):
        vals = []
        for i in range(6):
            for j in range(6):
                a = poles[i * 6 + j]
                b = (poles[i * 6 + j + 1] if along_u and j < 5
                     else poles[(i + 1) * 6 + j] if not along_u and i < 5
                     else None)
                if b is not None:
                    vals.append((a - b).Length)
        return (min(vals), max(vals)) if vals else (0.0, 0.0)
    return steps(True), steps(False)


def _chord(shape):
    """The tri's longest edge -- the chord across the corner."""
    return max((e.Length for e in shape.Edges), default=0.0)


def _coins(poles, tol=1e-7):
    n = 0
    for i in range(len(poles)):
        for j in range(i):
            if (poles[i] - poles[j]).Length <= tol:
                n += 1
    return n


def _close(FreeCAD, doc):
    if doc.Name in FreeCAD.listDocuments():
        FreeCAD.closeDocument(doc.Name)


# ---------------------------------------------------------------------------
# The artifact: the demo model with its equalised corner, LEFT OPEN
# ---------------------------------------------------------------------------

def artifact():
    """Build the demo model's corner with the equalising placement and SAVE
    it, leaving the document OPEN for the owner.

    `Resources/Test_files/_inspect/demo_corner_even.FCStd` -- the whole demo
    model (12 Edges, 5 Patches, 8 Blends) with `CB_J1_FrontTopRight` rolled
    at the default (equalised) placement, and every role the corner builds
    named: the three ring blends, the quad (`CornerBlend`), the tri
    (`RollingMemberFace`), and the five preserved pieces.  No render, no
    colour, nothing to look at but the tree and the shapes."""
    import FreeCAD
    import demo01_fixture_model as DEMO
    import SilkCorner as SC
    import SilkWorkflowOps as OPS

    lines = []
    label = "_demo_corner_even"
    for name, d in list(FreeCAD.listDocuments().items()):
        if d.Label == label:
            FreeCAD.closeDocument(name)
    doc = FreeCAD.newDocument(label)
    FreeCAD.setActiveDocument(doc.Name)
    DEMO.build(doc, corners=False)
    doc.recompute()
    doc.recompute()
    strips = [doc.getObject(n) for n in DEMO_RING]
    pin, _why = SC.corner_member_pin(strips)
    patch = pin[0]
    corner = OPS.create_corner_blend(*strips, name=DEMO_CORNER)
    doc.recompute()
    doc.recompute()
    if corner is None:
        lines.append("ARTIFACT: the corner did not build -- nothing saved")
        return lines
    os.makedirs(os.path.dirname(ARTIFACT), exist_ok=True)
    doc.saveAs(ARTIFACT)
    lines.append("ARTIFACT  %s  (%.1f kB, %d objects) -- LEFT OPEN"
                 % (ARTIFACT, os.path.getsize(ARTIFACT) / 1024.0,
                    len(doc.Objects)))
    lines.append("  roles: %s"
                 % ", ".join(sorted(o.Name for o in doc.Objects
                                    if getattr(o, "object_type", "") in
                                    ("Blend", "CornerBlend",
                                     "RollingMemberFace", "PreservedPiece"))))
    for s in strips:
        if patch not in (getattr(s, "PatchA", None),
                        getattr(s, "PatchB", None)):
            continue
        length, _w = OPS.seam_cut_length(s, patch, ring=strips)
        lines.append("  %-6s cut side %s mm"
                     % (s.Name, "REFUSED" if length is None
                        else "%.9f" % length))
    return lines


# ---------------------------------------------------------------------------
# The launcher: send the module's own halves to the owner's FreeCAD
# ---------------------------------------------------------------------------

BOOT = r'''
import sys
sys.path.insert(0, @@REPO@@)
sys.path.insert(0, @@HERE@@)
for _m in [m for m in list(sys.modules)
           if m.split(".")[0] in ("SilkMachinery", "SilkCorner",
                                  "SilkWorkflowOps", "SilkBlend", "SilkPatch",
                                  "SilkEdge", "SilkChecks",
                                  "cube_corner_model", "demo01_fixture_model",
                                  "prototype_reference_corner",
                                  "corner_even_cuts", "ArachNURBS")]:
    del sys.modules[_m]
import corner_even_cuts as E
for _line in E.measure():
    print(_line)
for _line in E.artifact():
    print(_line)
'''


def rpc_execute(code, timeout=1800):
    """Send `code` to the owner's running FreeCAD. NEVER spawns one."""
    import xmlrpc.client
    proxy = xmlrpc.client.ServerProxy("http://%s:%d/" % (RPC_HOST, RPC_PORT))
    proxy.ping()
    res = proxy.execute_code(code, timeout)
    if not res.get("success"):
        raise SystemExit("RPC error: %s" % res.get("error"))
    return res.get("message", "")


def main(argv=None):
    code = BOOT.replace("@@REPO@@", repr(REPO)).replace("@@HERE@@", repr(HERE))
    text = rpc_execute(code)
    print(text)
    dest = os.path.join(os.path.dirname(ARTIFACT), "corner_even_cuts.txt")
    try:
        with open(dest, "w") as fh:
            fh.write(text if text.endswith("\n") else text + "\n")
        print("[raw output kept: %s]" % dest)
    except OSError as exc:
        print("[could not keep the raw output: %r]" % (exc,))
    return 0


if __name__ == "__main__":
    sys.exit(main())
