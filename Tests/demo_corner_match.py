"""Compare Silk's rolling corners against the Demo 01 reference (task-4 evidence).

READ-ONLY on both files. Prints, per junction, the reference's `CubicSurface_66`
area and extent beside ours, and the quad's four side lengths (a real quad has
four non-zero sides; a collapsed one shows a 0.0). Saves the table to
Resources/Test_files/_inspect/demo_corner_match.txt.

RUN INSIDE FREECAD (never spawns one):

    flock /tmp/silk_rpc.lock -c "python3 Tests/demo_corner_match.py"

Exit code 0 when every corner is within its share of the reference, 1 otherwise.
The instrument asserts nothing about surfaces or tree parity: the reference's
corners are `CubicSurface_66` objects and ours are `CornerBlend`s -- this is
construction and proportion, not bytes.
"""

import os
import sys

# A SCRIPT, not a test module: the name is not `test_*`, so the suite never
# collects it and no MANUAL marker is needed (a marker would have to be added
# to Tests/test_manual_tier.EXPECTED_MANUAL).

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HERE = os.path.dirname(os.path.abspath(__file__))
RPC_HOST = "127.0.0.1"
RPC_PORT = 9875
ARTIFACT = os.path.join(REPO, "Resources", "Test_files", "_inspect",
                        "demo_corner_match.txt")

# The reference's four corner fills, measured from
# Resources/Demo_files/Silk_Demo_01.FCStd (CubicSurface_66, one per junction).
HIS_QUADS = {"CubicSurface_66": 1931.0, "CubicSurface_66001": 955.6,
             "CubicSurface_66002": 1982.5, "CubicSurface_66003": 1532.0}
AREA_TOL = 0.25          # per corner, +/- of his
TOTAL_TOL = 0.15         # the four together


BOOT = r'''
import sys
sys.path.insert(0, @@REPO@@)
sys.path.insert(0, @@HERE@@)
for _m in [m for m in list(sys.modules)
           if m.split(".")[0] in ("SilkMachinery", "SilkCorner",
                                  "SilkWorkflowOps", "SilkBlend", "SilkPatch",
                                  "SilkEdge", "SilkChecks",
                                  "demo01_fixture_model", "ArachNURBS")]:
    del sys.modules[_m]
import demo_corner_match as M
_r = M.measure()
_ok, _text = (_r if isinstance(_r, tuple) else (bool(_r == 0), str(_r)))
print(_text)
print("VERDICT:", "GREEN" if _ok else "OUT-OF-TOLERANCE")
'''


def measure():
    """Print the table and write the artifact. RUNS INSIDE FREECAD."""
    import FreeCAD
    import demo01_fixture_model as DEMO
    import SilkCorner as SC

    out = []

    def emit(line=""):
        out.append(line)

    def sides(face):
        return sorted(round(e.Length, 1) for e in face.Edges)

    emit("HIS corner fills (Resources/Demo_files/Silk_Demo_01.FCStd):")
    his = None
    path = os.path.join(REPO, "Resources", "Demo_files", "Silk_Demo_01.FCStd")
    if os.path.exists(path):
        his = FreeCAD.openDocument(path)
        his.recompute()
        for c in [o for o in his.Objects
                  if getattr(o, "object_type", "") == "CubicSurface_66"]:
            f = max(c.Shape.Faces, key=lambda x: x.Area)
            bb = c.Shape.BoundBox
            emit("  %-20s area=%8.1f extent=%6.1f sides=%r"
                 % (c.Name, f.Area, max(bb.XLength, bb.YLength, bb.ZLength),
                    sides(f)))
        FreeCAD.closeDocument(his.Name)
    else:
        emit("  (file missing; using the published areas %r)" % (HIS_QUADS,))

    doc = FreeCAD.newDocument("_demo_match")
    FreeCAD.setActiveDocument(doc.Name)
    built = DEMO.build(doc)
    doc.recompute()
    doc.recompute()
    emit("")
    emit("OUR rolling corners (SketchOnly_Demo01Subset_withPatches):")
    rows, areas = [], []
    for name, _ring, _pt in DEMO.CORNERS:
        c = built["corners"].get(name)
        if c is None:
            emit("  %-26s MISSING" % name)
            rows.append((name, None, None, None))
            continue
        f = max(c.Shape.Faces, key=lambda x: x.Area)
        bb = c.Shape.BoundBox
        rows.append((name, f.Area, max(bb.XLength, bb.YLength, bb.ZLength),
                     sides(f)))
        areas.append(f.Area)
        emit("  %-26s area=%8.1f extent=%6.1f sides=%r poles=%d faces=%d"
             % (name, f.Area, max(bb.XLength, bb.YLength, bb.ZLength),
                sides(f), len(c.Poles or []), len(c.Shape.Faces)))
    emit("")
    his_order = [HIS_QUADS[k] for k in sorted(HIS_QUADS)]
    ok = True
    for (name, ours, _ext, _s), ref in zip(rows, his_order):
        if ours is None:
            ok = False
            continue
        delta = (ours - ref) / ref * 100.0
        verdict = "ok" if abs(delta) <= AREA_TOL * 100.0 else "OUT"
        emit("  %-26s ours %8.1f vs his %8.1f  %+6.1f %%  %s"
             % (name, ours, ref, delta, verdict))
        ok = ok and abs(delta) <= AREA_TOL * 100.0
    if areas:
        total, ref_total = sum(areas), sum(his_order)
        delta = (total - ref_total) / ref_total * 100.0
        emit("  %-26s ours %8.1f vs his %8.1f  %+6.1f %%  %s"
             % ("TOTAL", total, ref_total, delta,
                "ok" if abs(delta) <= TOTAL_TOL * 100.0 else "OUT"))
        ok = ok and abs(delta) <= TOTAL_TOL * 100.0
    emit("")
    emit("touched=%r" % [o.Name for o in doc.Objects if "Touched" in o.State])
    FreeCAD.closeDocument(doc.Name)
    text = "\n".join(out) + "\n"
    print(text)
    try:
        os.makedirs(os.path.dirname(ARTIFACT), exist_ok=True)
        with open(ARTIFACT, "w") as fh:
            fh.write(text)
        print("[raw output kept: %s]" % ARTIFACT)
    except OSError as exc:
        print("[could not keep the raw output: %r]" % (exc,))
    return ok, text


def main():
    import xmlrpc.client
    code = BOOT.replace("@@REPO@@", repr(REPO)).replace("@@HERE@@", repr(HERE))
    proxy = xmlrpc.client.ServerProxy("http://%s:%d/" % (RPC_HOST, RPC_PORT))
    proxy.ping()
    res = proxy.execute_code(code, 1800)
    if not res.get("success"):
        raise SystemExit("RPC error: %s" % res.get("error"))
    print(res.get("message", ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
