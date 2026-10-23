#!/usr/bin/env python3
"""Tests/corner_follows_inputs.py -- the rolled corner FOLLOWING its inputs
(#132), measured on the owner's own junction.

**What it answers.**  The owner (2026-10-22): *"to make the rolling corner look
nice, i need control of the initial blends.  can i already update these and
rolling corner will follow?  ideally, the patch setback would also recalculate
(make it optional though) to make the triangle patch again."*

The corner already REBUILDS when a ring patch's band edge moves (the #109
chain), but its CUT stayed where the corner stage stored it.  On the demo's
`CB_J1_FrontTopRight` the two sides that bound the triangular member are
17.435446 / 17.435446 mm at the 0.1 setback -- and 17.435446 / 5.965472 mm once
`P_Top.VSplit1` is 0.15, because the band moved out from under the cut.

This instrument prints the HAND-BACK TABLE for that edit, under both modes
(`CornerBlend.LeaderMode`, `CornerBlend.SetbackMode`):

    LeaderMode   "auto"  the cut is re-derived from the band edges the way a
                         fresh build places it (the equalising rule, #129);
                 "fixed" the stored cut is kept -- the behaviour of before.
    SetbackMode  "fixed" the band edges are never written (the default: a band
                         edge is the user's own width, #64);
                 "auto"  the carrying patch's setback and the triangle's own
                         cut side are the corner's, and both are put back
                         where the corner PLACED them (`_CutReference`): the
                         band edge as a parameter (the triangle's share of
                         the patch), the cut as a length (its size).

and, for each row, the readings the change must not move: the corner's and the
member's areas, the cut sides in mm, the corner's 6x6 pole motion, the normal
field at n = 39/81/150, the coincident pole pairs, and the settling bar of
#125 (3 x `doc.recompute()`, nothing Touched, poles 0.000e+00).

It also drives the REAL PANEL -- flipping each selector on the demo junction
and editing a setback -- so the same numbers are reproducible from the UI, and
it leaves the model OPEN as
`Resources/Test_files/_inspect/demo_corner_reactive.FCStd` with every role
named.

**How it runs.**  Inside the owner's running FreeCAD, over XML-RPC (never
spawns one):

    flock /tmp/silk_rpc.lock -c "python3 Tests/corner_follows_inputs.py"

**What it does NOT do.**  It asserts nothing: it is an instrument, and its raw
output is the measurement the change is decided on.  The pins are in
`Tests/test_corner_follows_inputs.py` (fast tier, cube fixture) and
`Tests/test_corner_follow_demo.py` (manual tier, this junction).
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
                        "demo_corner_reactive.FCStd")

# The demo junction and its ring (`Tests/demo01_fixture_model.CORNERS[0]`).
DEMO_CORNER = "CB_J1_FrontTopRight"
DEMO_RING = ("B_FT", "B_FR", "B_TR")
DEMO_MEMBER_PATCH = "P_Top"
# The band edge the owner's edit moves, and the two values: the state the
# corner is built in, and the state the "before" measurement was taken at.
EDITED_EDGE = "VSplit1"
EDITED_FROM = 0.100
EDITED_TO = 0.150

# The mode pairs the table runs, in the order the owner would try them.
MODES = (("auto", "fixed"), ("fixed", "fixed"), ("auto", "auto"),
         ("fixed", "auto"))


# ---------------------------------------------------------------------------
# The in-FreeCAD half
# ---------------------------------------------------------------------------

def measure():
    """Print the hand-back table for the demo junction.  RUNS INSIDE FREECAD."""
    import time

    import FreeCAD

    import demo01_fixture_model as DEMO
    import SilkChecks
    import SilkCorner as SC
    import SilkMachinery as SM
    import SilkWorkflowOps as OPS

    out = []

    def emit(line=""):
        out.append(line)
        print(line)

    def fresh(label):
        for name, d in list(FreeCAD.listDocuments().items()):
            if d.Label == label or d.Name == label:
                FreeCAD.closeDocument(name)
        doc = FreeCAD.newDocument(label)
        FreeCAD.setActiveDocument(doc.Name)
        DEMO.build(doc, corners=False)
        doc.recompute()
        return doc

    def ring(doc):
        return [doc.getObject(n) for n in DEMO_RING]

    def corner_of(doc):
        for o in doc.Objects:
            if getattr(o, "object_type", "") == "CornerBlend":
                return o
        return None

    def member_of(doc):
        for o in doc.Objects:
            if getattr(o, "object_type", "") == "RollingMemberFace":
                return o
        return None

    def sides(doc):
        c = corner_of(doc)
        strips = list(c.Strips)
        patch = c.MemberPatch or doc.getObject(DEMO_MEMBER_PATCH)
        got = {}
        for s in strips:
            if patch not in (s.PatchA, s.PatchB):
                continue
            length, _why = OPS.seam_cut_length(s, patch, ring=strips)
            got[s.Name] = length
        return got

    def areas(doc):
        c = corner_of(doc)
        m = member_of(doc)
        return (c.Shape.Area if c.Shape and c.Shape.Faces else None,
                m.Shape.Area if m is not None and m.Shape and m.Shape.Faces
                else None)

    def coins(poles):
        return sum(1 for i in range(len(poles))
                   for j in range(i + 1, len(poles))
                   if (poles[i] - poles[j]).Length <= 1e-9)

    def flips(doc):
        c = corner_of(doc)
        if not c.Shape or not c.Shape.Faces:
            return None
        return [len(SilkChecks._normal_field_flips(
            c.Shape.Faces[0].Surface, n=n)[0]) for n in (39, 81, 150)]

    def pole_move(a, b):
        return max((FreeCAD.Vector(*x) - FreeCAD.Vector(*y)).Length
                   for x, y in zip(a, b))

    def settle(doc, label):
        times = []
        for _ in range(3):
            started = time.time()
            doc.recompute()
            times.append(time.time() - started)
        left = [o.Name for o in doc.Objects if "Touched" in o.State]
        emit("      %s: recompute #0/#1/#2 %.4f / %.4f / %.4f s -- still "
             "touched %s" % (label, times[0], times[1], times[2],
                             left or "NOTHING"))
        return times, left

    emit("=" * 78)
    emit("THE HAND-BACK TABLE -- the demo junction %s, ring %s, tri on %s"
         % (DEMO_CORNER, DEMO_RING, DEMO_MEMBER_PATCH))
    emit("the edit: %s.%s %.3f -> %.3f (the corner's own setback)"
         % (DEMO_MEMBER_PATCH, EDITED_EDGE, EDITED_FROM, EDITED_TO))
    emit("=" * 78)
    for leader_mode, setback_mode in MODES:
        doc = fresh("_follow_%s_%s" % (leader_mode, setback_mode))
        strips = ring(doc)
        corner = OPS.create_corner_blend(strips)
        doc.recompute()
        patch = corner.MemberPatch or doc.getObject(DEMO_MEMBER_PATCH)
        OPS.set_follow_modes(corner, leader=leader_mode, setback=setback_mode)
        doc.recompute()
        build_sides = sides(doc)
        quad0, tri0 = areas(doc)
        poles0 = [tuple(p) for p in corner.Poles]
        edge0 = float(getattr(patch, EDITED_EDGE))
        emit("")
        emit("LeaderMode=%r SetbackMode=%r" % (leader_mode, setback_mode))
        emit("  built : corner %.6f mm^2, tri %.6f mm^2, sides %s"
             % (quad0, tri0,
                " / ".join("%.6f" % v for v in build_sides.values())))
        setattr(patch, EDITED_EDGE, EDITED_TO)
        doc.recompute()
        after_sides = sides(doc)
        quad1, tri1 = areas(doc)
        edge1 = float(getattr(patch, EDITED_EDGE))
        emit("  after : corner %.6f mm^2, tri %.6f mm^2, sides %s"
             % (quad1, tri1,
                " / ".join("%.6f" % v for v in after_sides.values())))
        values = [v for v in after_sides.values() if v is not None]
        emit("  %-30s %s = %.17g  (the edit wrote %.3f; %+.3e)"
             % ("the setback reads", EDITED_EDGE, edge1, EDITED_TO,
                edge1 - EDITED_TO))
        emit("  %-30s unequal = %.3e mm"
             % ("the two tri sides", max(values) - min(values)
                if len(values) == 2 else float("nan")))
        report = getattr(corner.Proxy, "_follow_report", None) or {}
        emit("  %-30s branch %r, note %r"
             % ("the follow reports", report.get("branch"), report.get("note")))
        moved = pole_move(poles0, [tuple(p) for p in corner.Poles])
        emit("  %-30s %.3e mm (36 poles)" % ("poles vs the build", moved))
        emit("  %-30s %d/630" % ("coincident pole pairs", coins(list(corner.Poles))))
        emit("  %-30s %r" % ("normal-field flips n=39/81/150", flips(doc)))
        settle(doc, "settles")
        emit("  %-30s %s" % ("%s.%s mode" % ("CornerBlend", "LeaderMode"),
                             corner.LeaderMode))
        emit("  %-30s %s (%d objects)"
             % ("recorded cut, (mm, band edge)",
                {k: (round(a, 6), round(b, 6))
                 for k, (a, b) in SC.cut_reference(corner).items()},
                len(doc.Objects)))
        FreeCAD.closeDocument(doc.Name)

    # ---- the FRESH-BUILD cross-check -----------------------------------
    emit("")
    emit("-" * 78)
    emit("THE CROSS-CHECK: is \"follows its inputs\" the same corner a FRESH "
         "build places?")
    emit("-" * 78)
    doc = fresh("_follow_fresh")
    strips = ring(doc)
    patch = doc.getObject(DEMO_MEMBER_PATCH)
    setattr(patch, EDITED_EDGE, EDITED_TO)
    doc.recompute()
    fresh_corner = OPS.create_corner_blend(strips)
    doc.recompute()
    fresh_patch = fresh_corner.MemberPatch or doc.getObject(DEMO_MEMBER_PATCH)
    fresh_sides = sides(doc)
    quad_f, tri_f = areas(doc)
    emit("  a fresh build AT %.3f: corner %.6f mm^2, tri %.6f mm^2, sides %s"
         % (EDITED_TO, quad_f, tri_f,
            " / ".join("%.6f" % v for v in fresh_sides.values())))
    emit("  its cut: %s" % ({k: round(float(getattr(fresh_patch, k)), 9)
                             for k in ("ULeader2", "VLeader1")},))
    FreeCAD.closeDocument(doc.Name)

    # ---- the panel ------------------------------------------------------
    emit("")
    emit("-" * 78)
    emit("THE PANEL: the two selectors on the demo junction, flipped, and the "
         "setback edited under each")
    emit("-" * 78)
    from Tests.test_task_panel import _open_panel, _close_panel, _click
    # the panel's OWN band-edge editor: a property written behind the panel's
    # back is committed back to the editor's value by `refresh()` (#71), so
    # the setback is typed where a user types it -- one helper, shared with
    # the pin in `Tests/test_corner_follows_inputs.py`
    from Tests.test_corner_follows_inputs import _panel_band_editor
    import SilkTaskPanel as TP
    doc = fresh("demo_corner_reactive")
    strips = ring(doc)
    corner = OPS.create_corner_blend(strips)
    doc.recompute()
    panel = _open_panel(doc)
    try:
        panel.sections.open(TP.SECTION_CORNER)
        for s in strips:
            _click(s)
        emit("  the page offers cut %s / setback %s; in force: %r"
             % ([panel.corner_leader_mode.itemText(i) for i in
                 range(panel.corner_leader_mode.count())],
                [panel.corner_setback_mode.itemText(i) for i in
                 range(panel.corner_setback_mode.count())],
                panel.corner_follow_choices()))
        emit("  the page says: %r" % (panel.corner_follow_lbl.text(),))
        patch = corner.MemberPatch or doc.getObject(DEMO_MEMBER_PATCH)
        edge0 = float(getattr(patch, EDITED_EDGE))
        build_poles = [tuple(p) for p in corner.Poles]
        emit("  built (through the panel's ring): sides %s"
             % " / ".join("%.6f" % v for v in sides(doc).values()))

        # (1) Cut: fixed -- the edit moves the band and not the cut.  The
        # setback is typed into the PANEL's editor for that patch's band edge.
        panel.corner_leader_mode.setCurrentIndex(
            panel.corner_leader_mode.findText("fixed"))
        spin, seeded = _panel_band_editor(panel, patch, EDITED_EDGE)
        emit("  the panel's editor for %s.%s: seeds %.6f" %
             (patch.Name, EDITED_EDGE, seeded))
        spin.setValue(EDITED_TO)
        panel.refresh()          # commits the typed width (its own path)
        doc.recompute()
        emit("  Cut: fixed  + %s %.3f -> %.3f (typed in the panel): %s reads "
             "%.6f, sides %s"
             % (EDITED_EDGE, EDITED_FROM, EDITED_TO, EDITED_EDGE,
                float(getattr(patch, EDITED_EDGE)),
                " / ".join("%.6f" % v for v in sides(doc).values())))

        # (2) Cut: auto on the SAME edit -- the cut is re-derived
        panel.corner_leader_mode.setCurrentIndex(
            panel.corner_leader_mode.findText("auto"))
        emit("  Cut: auto   + the same edit: %s reads %.6f, sides %s, "
             "corner %.6f mm^2"
             % (EDITED_EDGE, float(getattr(patch, EDITED_EDGE)),
                " / ".join("%.6f" % v for v in sides(doc).values()),
                corner.Shape.Area))

        # (3) Setback: auto -- the band edge goes back to the built triangle
        panel.corner_setback_mode.setCurrentIndex(
            panel.corner_setback_mode.findText("auto"))
        emit("  Setback: auto: %s reads %.17g (built at %.3f, the edit wrote "
             "%.3f), sides %s, poles vs the build %.3e mm"
             % (EDITED_EDGE, float(getattr(patch, EDITED_EDGE)), edge0,
                EDITED_TO,
                " / ".join("%.6f" % v for v in sides(doc).values()),
                pole_move(build_poles, [tuple(p) for p in corner.Poles])))
        emit("  the page now says: %r" % (panel.corner_follow_lbl.text(),))
        settle(doc, "settles")
        # leave the model OPEN as the artifact, every role named
        corner.Label = DEMO_CORNER
        member = member_of(doc)
        if member is not None:
            member.Label = "%s tri (the triangular patch)" % DEMO_CORNER
        os.makedirs(os.path.dirname(ARTIFACT), exist_ok=True)
        doc.saveAs(ARTIFACT)
        emit("  the artifact: %s (%d objects: %s)"
             % (ARTIFACT, len(doc.Objects),
                ", ".join(sorted("%s=%s" % (getattr(o, "object_type", ""),
                                            o.Name) for o in doc.Objects))))
    finally:
        _close_panel(panel)
    emit("")
    emit("THE MODEL IS LEFT OPEN as %s -- nothing is rendered."
         % ARTIFACT)
    return "\n".join(out)


# ---------------------------------------------------------------------------
# The RPC client half (never spawns a FreeCAD)
# ---------------------------------------------------------------------------

def _transport(timeout=3600):
    import http.client
    import xmlrpc.client

    class _T(xmlrpc.client.Transport):
        def make_connection(self, host):
            parts = host.split(":")
            return http.client.HTTPConnection(
                parts[0], int(parts[1]) if len(parts) > 1 else 80,
                timeout=timeout)
    return xmlrpc.client.ServerProxy("http://%s:%d/" % (RPC_HOST, RPC_PORT),
                                     _T())


_REMOTE = """
import sys
sys.path.insert(0, %r)
import Tests.silk_reload as helper
helper.ensure_fresh(force=False, namespace=globals())
import Tests.corner_follows_inputs as instrument
print("MEASURE-START")
instrument.measure()
print("MEASURE-END")
"""


def main():
    _, _, host = (RPC_HOST, RPC_PORT, RPC_HOST)
    proxy = _transport()
    res = proxy.execute_code(_REMOTE % (REPO,))
    if not isinstance(res, dict) or not res.get("success"):
        print("FreeCAD reported an error: %r" % (res,))
        return 1
    text = str(res.get("message", ""))
    start = text.find("MEASURE-START")
    end = text.find("MEASURE-END")
    if start < 0 or end < 0:
        print(text)
        print("(no MEASURE markers -- the instrument did not run)")
        return 1
    body = text[start + len("MEASURE-START"):end].strip("\n")
    print(body)
    print("\nMEASURED (this output is the measurement; nothing is asserted "
          "here).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
