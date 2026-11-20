"""Replay the corner setup read from Silk_Demo_01.FCStd into our workflow.

READ-ONLY on the reference file. Writes happen only in a fresh scratch
document built from the sketch-only fixture. Band edges are per patch and
shared; LEADER cuts are written by the corner stage with its owner name, so
two corners may claim different ends of one patch without opening each
other's ring (#130/#131).

A seam on which his file carries only the setback value (J1/J2 on P_Right's
U axis, J3 on P_Top's V, J4 on P_Bottom's U) has no measured cut side: that
missing side is EQUALISED to the measured side on the member's other seam,
in mm on the patch's own curve. The choice is printed, never hidden.
"""

import os
import traceback

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HERE = os.path.dirname(os.path.abspath(__file__))
ARTIFACT = os.path.join(REPO, "Resources", "Test_files", "_inspect",
                        "reference_replay.txt")


def _pin_index(seams):
    """Patch corner index where the member's two ring seams meet.

    Patch corners are (U0,V0)=0, (U0,V1)=1, (U1,V1)=2, (U1,V0)=3.
    """
    u = [s for s in seams if s["axis"] == "U"]
    v = [s for s in seams if s["axis"] == "V"]
    if len(u) != 1 or len(v) != 1:
        return None
    eu, ev = u[0]["end"], v[0]["end"]
    if eu == 0:
        return 0 if ev == 0 else 1
    return 3 if ev == 0 else 2


def replay(doc, records=None, names=None, verbose=True):
    """Build the requested corners from his setup in `doc`.

    `doc` must already carry the fixture's sketches/edges/patches/blends;
    pass `corners=False` to Tests.demo01_fixture_model.build. Returns a dict
    with 'corners', 'writes', 'leaders', 'problems' and 'lines'.
    """
    import FreeCAD
    import SilkWorkflowOps as O
    import SilkMachinery as SM
    import SilkCorner as SC
    from SilkBlend import band_edge_prop
    from Tests import demo01_fixture_model as FM
    import demo_reference_corner_setup as REF

    records = records if records is not None else REF.read_setup()[0]
    if names is not None:
        records = [r for r in records if r["name"] in names]
    lines, writes, leaders, problems, corners = [], [], {}, [], {}

    def emit(text=""):
        lines.append(text)
        if verbose:
            print(text)

    # 1. band edges: one value per (patch, axis end). Conflicts are named.
    plan = {}
    for rec in records:
        member = rec["member"]
        for seam in rec["seams"]:
            plan[(member, seam["axis"], seam["end"])] = (
                seam["setback"], "%s member seam %s" % (rec["name"], seam["strip"]))
        for point in rec["quad_points"]:
            key = (point["patch"], point["axis"], point["end"])
            value = point["param"]
            if key in plan and abs(plan[key][0] - value) > 1e-8:
                problems.append("band conflict %r: %r vs %r"
                                % (key, plan[key], value))
            plan[key] = (value, "%s quad point" % rec["name"])
    for (patch_name, axis, end), (value, why) in sorted(plan.items()):
        patch = doc.getObject(patch_name)
        prop = band_edge_prop(axis, end)
        before = float(getattr(patch, prop))
        if abs(before - value) > 1e-12:
            setattr(patch, prop, value)
        writes.append((patch_name, prop, before, value, why))
        emit("BAND %s.%s %.6f -> %.6f  (%s)"
             % (patch_name, prop, before, value, why))
    doc.recompute()
    doc.recompute()

    # 2. each corner: pin from its two member seams, leaders in mm.
    for rec in records:
        name = rec["name"]
        strips = [doc.getObject(b) for b in rec["ring"]]
        member = doc.getObject(rec["member"])
        idx = _pin_index(rec["seams"])
        if member is None or idx is None:
            problems.append("%s: no member or pin (%r)" % (name, idx))
            continue
        measured = {}
        sides = {}
        fallback = []
        for seam in rec["seams"]:
            vals = seam.get("values") or []
            if len(vals) < 2:
                fallback.append(seam)
            else:
                measured[seam["strip"]] = seam["leader_mm"]
                sides[seam["strip"]] = (seam["leader_mm"]
                                        - seam["mm"][seam["setback"]])
        if fallback:
            # equalise the missing side to the measured side on the other axis
            if not measured:
                problems.append("%s: no measured cut side to equalise" % name)
                continue
            leg = min(sides.values())
            for seam in fallback:
                prop, param, why = O.seam_cut_at_leg(
                    doc.getObject(seam["strip"]), member, leg, ring=strips)
                if prop is None:
                    problems.append("%s: %s" % (name, why))
                    continue
                r, rwhy = O.seam_cut_reach(doc.getObject(seam["strip"]),
                                           member, ring=strips)
                if r is None:
                    problems.append("%s: %s" % (name, rwhy))
                    continue
                mm = SM.seam_length(member, r["side"], r["t_corner"], param)
                measured[seam["strip"]] = mm
                emit("EQUALISE %s: his file gives only setback %.6f on %s; "
                     "cut side %.4f mm -> leader %.4f mm"
                     % (name, seam["setback"], seam["strip"], leg, mm))
        leaders[name] = measured
        with FM.CaptureConsole() as cap:
            corner = O.create_corner_blend(strips, name=name,
                                           pin=(member, idx), leaders=measured)
        doc.recompute()
        doc.recompute()
        emit("BUILD %s pin=%s[%d] leaders=%r -> %s %r"
             % (name, member.Name, idx,
                {k: round(v, 4) for k, v in measured.items()},
                getattr(corner, "Name", None), list(cap.errors)[:1]))
        if corner is None:
            problems.append("%s refused: %s"
                            % (name, " ".join(cap.errors).strip()))
        else:
            corners[name] = corner
    return {"corners": corners, "writes": writes, "leaders": leaders,
            "problems": problems, "lines": lines}


def replay_in_new_document(corners=True):
    """`([records], result, doc)` -- replay into a fresh full click-through."""
    import FreeCAD
    import demo_reference_corner_setup as REF
    from Tests import demo01_fixture_model as FM
    records = REF.read_setup()[0]
    source, source_dir = FM.open_fresh(FM.FIXTURE_PATH)
    sketch_names = [o.Name for o in source.Objects
                    if o.TypeId == "Sketcher::SketchObject"]
    original = FM.used_sketch_names
    doc = FreeCAD.newDocument("Demo01_Replayed")
    try:
        FM.used_sketch_names = lambda: list(sketch_names)
        FreeCAD.setActiveDocument(doc.Name)
        result = FM.build(doc, source=source, corners=False)
    finally:
        FM.used_sketch_names = original
        FM.close_fresh(source, source_dir)
    if result["problems"]:
        raise RuntimeError("fixture: %r" % result["problems"])
    names = None if corners else [records[0]["name"]]
    result = replay(doc, records=records, names=names)
    return records, result, doc


if __name__ == "__main__":
    import xmlrpc.client
    code = """import sys, traceback
sys.path.insert(0, __REPO__)
sys.path.insert(0, __HERE__)
for m in list(sys.modules.keys()):
    if m.startswith(('Silk','Tests','ArachNURBS','demo01','demo_reference_corner_setup','demo_reference_replay')):
        del sys.modules[m]
import demo_reference_replay as R
try:
    records, result, doc = R.replay_in_new_document()
    import FreeCAD, SilkChecks as CK, SilkCorner as SC
    for c in [o for o in doc.Objects if getattr(o,'object_type','')=='CornerBlend']:
        bad = [x for x in CK.check_corner_blend(c,*list(c.Strips)) if not x[1]]
        print('CHECK', c.Name, SC.corner_construction(c)[0], len(c.Poles),
              len(c.Shape.Faces), len(getattr(c,'ReservedCells',[]) or []),
              'area %.1f' % max(f.Area for f in c.Shape.Faces), 'bad', bad)
    print('Touched', [o.Name for o in doc.Objects if 'Touched' in o.State])
    open(__ARTIFACT__,'w').write('\\n'.join(result['lines'])+'\\n')
except Exception:
    print(traceback.format_exc())
""".replace('__REPO__', repr(REPO)).replace('__HERE__', repr(HERE)).replace('__ARTIFACT__', repr(ARTIFACT))
    response = xmlrpc.client.ServerProxy("http://127.0.0.1:9875").execute_code(code)
    print(response.get("output", ""))
    if response.get("error"):
        print("RPC ERROR:", response["error"])
