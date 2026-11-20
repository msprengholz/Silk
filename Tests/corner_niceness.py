"""READING, not a pass/fail: how nice each rolling corner actually is.

Printed per junction (raw output kept under Resources/Test_files/_inspect/):
each seam's own band width in mm (the setback), the two equalised cut sides,
the quad's four sides, the tri's two free sides, their spread, the tri/quad
area ratio, both areas with the maintainer's quad beside ours, fold counts,
coincident poles, normal-field flips and the corner oracle.

INSTRUMENTS: SilkWorkflowOps.seam_cut_reach / seam_cut_length (64-station arc
on the patch's own seam curve, 1.7e-6 relative floor); Part edge lengths;
SilkMachinery.net_fold_count on the exact net; SilkChecks._normal_field_flips
at n=39/81/150; SilkChecks.check_corner_blend. His quad areas are read from
Resources/Demo_files/Silk_Demo_01.FCStd and are a READING, not a bar (#134).
"""

import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HERE = os.path.dirname(os.path.abspath(__file__))

ARTIFACT = os.path.join(REPO, "Resources", "Test_files", "_inspect",
                        "corner_niceness.txt")
HIS_QUAD = {"CB_J1_FrontTopRight": 1931.0, "CB_J2_FrontRightBottom": 955.6,
            "CB_J3_TopRightBack": 1982.5, "CB_J4_RightBottomBack": 1532.0}
HIS_TRI_OVER_QUAD = 0.2776
TOL = 1e-6


def _faces(corner):
    quad = tri = None
    for f in corner.Shape.Faces:
        lengths = [e.Length for e in f.Edges]
        if any(v <= TOL for v in lengths):
            tri = f
        else:
            quad = f
    return quad, tri


def measure():
    import FreeCAD
    for m in list(sys.modules.keys()):
        if m.split(".")[0] in ("SilkMachinery", "SilkCorner",
                               "SilkWorkflowOps", "SilkBlend", "SilkPatch",
                               "SilkEdge", "SilkChecks",
                               "demo01_fixture_model", "ArachNURBS"):
            del sys.modules[m]
    import SilkWorkflowOps as OPS
    import SilkMachinery as SM
    import SilkChecks as CK
    import SilkCorner as SC
    from Tests import demo01_fixture_model as FM

    out = []
    emit = out.append
    doc = FreeCAD.newDocument("Niceness")
    FreeCAD.setActiveDocument(doc.Name)
    FM.build(doc)
    doc.recompute()
    doc.recompute()
    emit("rolling corner niceness -- READINGS, no pass/fail")
    emit("instrument: seam_cut_reach/seam_cut_length (64 stations, 1.7e-6 "
         "relative floor), Part edge lengths, net_fold_count on the exact "
         "net, _normal_field_flips n=39/81/150, check_corner_blend")
    emit("fixture: Tests/demo01_fixture_model.build(doc) "
         "(SketchOnly_Demo01Subset_withPatches)")
    emit("")
    for c in [o for o in doc.Objects
              if getattr(o, "object_type", "") == "CornerBlend"]:
        pin = SC.recorded_member_pin(c)
        patch = pin[0] if pin else None
        strips = list(c.Strips)
        bands, legs = [], []
        for s in strips:
            r, why = OPS.seam_cut_reach(s, patch, ring=strips)
            if r is None:
                continue
            leg, lwhy = OPS.seam_cut_length(s, patch, ring=strips,
                                            owner=c.Name)
            bands.append(r["corner_mm"])
            legs.append(leg)
        quad, tri = _faces(c)
        q_sides = [e.Length for e in quad.Edges]

        def _key(edge):
            return tuple(sorted(tuple(round(v, 4) for v in vt.Point)
                                for vt in edge.Vertexes if vt is not None))

        shared = {_key(e) for e in quad.Edges}
        t_edges = [e for e in tri.Edges
                   if e.Length > TOL and _key(e) not in shared]
        t_sides = [e.Length for e in t_edges]
        all_sides = q_sides + t_sides
        coins = sum(1 for i in range(len(c.Poles))
                    for j in range(i + 1, len(c.Poles))
                    if (c.Poles[i] - c.Poles[j]).Length <= 1e-6)
        flips = [len(CK._normal_field_flips(quad.Surface, n=n)[0])
                 for n in (39, 81, 150)]
        folds = SM.net_fold_count(list(c.Poles), list(c.Weights))
        checks = CK.check_corner_blend(c, *strips)
        bad = [x for x in checks if not x[1]]
        emit("== %s member=%s construction=%r pieces=%d"
             % (c.Name, patch.Name, SC.corner_construction(c)[0],
                len(getattr(c, "ReservedCells", []) or [])))
        emit("  band widths (setback, mm)      %r"
             % [round(v, 6) for v in bands])
        emit("  cut sides (equalised, mm)      %r  |diff| %.3e"
             % ([round(v, 6) for v in legs],
                abs(legs[0] - legs[1]) if len(legs) == 2 else float('nan')))
        emit("  quad four sides (mm)           %r"
             % [round(v, 4) for v in q_sides])
        emit("  tri free sides (mm, shared excluded) %r"
             % [round(v, 4) for v in t_sides])
        emit("  side spread (six, mm)          %.6f .. %.6f = %.6f"
             % (min(all_sides), max(all_sides),
                max(all_sides) - min(all_sides)))
        emit("  quad / tri areas (mm^2)        %.4f / %.4f  ratio %.6f"
             % (quad.Area, tri.Area, tri.Area / quad.Area))
        emit("  reference quad / tri/quad      %.1f / %.4f  (delta %+.1f %%)"
             % (HIS_QUAD[c.Name], HIS_TRI_OVER_QUAD,
                (quad.Area - HIS_QUAD[c.Name]) / HIS_QUAD[c.Name] * 100.0))
        emit("  folds / coincident / flips     %d / %d of 630 / %r"
             % (folds, coins, flips))
        emit("  corner oracle                  %d checks, failures %r"
             % (len(checks), bad))
        emit("")
    touched = [o.Name for o in doc.Objects if "Touched" in o.State]
    emit("touched=%r" % (touched,))
    text = "\n".join(out) + "\n"
    print(text)
    path = os.path.abspath(ARTIFACT)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as fh:
        fh.write(text)
    print("[raw output kept: %s]" % path)
    return text


if __name__ == "__main__":
    import xmlrpc.client
    code = """import sys
sys.path.insert(0, %r)
sys.path.insert(0, %r)
for m in list(sys.modules.keys()):
    if m.startswith(('Silk','Tests','ArachNURBS','demo01','corner_niceness')): del sys.modules[m]
import corner_niceness as N
N.measure()
""" % (REPO, HERE)
    print(xmlrpc.client.ServerProxy("http://127.0.0.1:9875")
          .execute_code(code).get("output", ""))
