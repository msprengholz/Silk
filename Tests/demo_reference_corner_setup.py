"""READ-ONLY instrument: the corner setup stored in Silk_Demo_01.FCStd.

For each junction it prints the tri member's patch, the exact (u,v) points of
that member on OUR patch surfaces, the quad's points on the other ring
patches, and every one of those parameters converted into mm along the
patch's own seam curve. Nothing is written to either source document.

INSTRUMENTS AND FLOORS
  * 3D -> (u,v): Part.Face.distToShape(Part.Vertex(p))[0] <= 1e-6 mm, then
    Face.Surface.parameter(p). A point farther than that is on a blend strip,
    not on the base patch, and is printed as such rather than forced.
  * mm along the seam: SilkMachinery.seam_length, 64 stations, 1.7e-6 relative
    floor, measured from the junction corner of that patch's seam curve.
  * duplicated vertices: 1e-5 mm in 3D / 1e-6 in (u,v).

RUN INSIDE FREECAD (never spawns one):

    flock /tmp/silk_rpc.lock -c "python3 Tests/demo_reference_corner_setup.py"
"""

import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HERE = os.path.dirname(os.path.abspath(__file__))
ARTIFACT = os.path.join(REPO, "Resources", "Test_files", "_inspect",
                        "reference_corner_setup.txt")
# The four reference quads and the four triangular members are paired in the
# file's construction order (FrontTopRight, FrontRightBottom, TopRightBack,
# RightBottomBack); demo_corner_match.py pins the quad areas of this order.
QUADS = ("CubicSurface_66", "CubicSurface_66001",
         "CubicSurface_66002", "CubicSurface_66003")
TRIS = ("CubicSurface_64003", "CubicSurface_64004",
        "CubicSurface_64007", "CubicSurface_64008")
ON_PATCH = 1e-6       # mm
XY_FLOOR = 1e-6       # parameter


def _vertices(obj):
    out = []
    for face in obj.Shape.Faces:
        for edge in face.Edges:
            for vertex in edge.Vertexes:
                p = vertex.Point
                if not any((p - q).Length <= 1e-5 for q in out):
                    out.append(p)
    return out


def _project(point, patches):
    best = None
    for patch in patches:
        for face in patch.Shape.Faces:
            d = face.distToShape(Part.Vertex(point))[0]
            try:
                uv = tuple(face.Surface.parameter(point))
            except Exception:
                continue
            if best is None or d < best[0]:
                best = (d, patch, uv)
    return best


def _dedup_uv(rows):
    out = []
    for d, patch, uv in rows:
        if not any(abs(uv[0] - old[0]) <= XY_FLOOR
                   and abs(uv[1] - old[1]) <= XY_FLOOR for old in out):
            out.append(uv)
    return out


def read_setup():
    """`([records], [printed lines])` -- his four corner setups, read-only.

    A record carries the junction name, its three ring strip names, the
    member patch NAME, that member's exact on-patch uv points, each member
    seam's axis/end/setback/cut (parameters and mm), and the quad's exact
    points on the other patches with their seam parameter and mm.
    """
    global Part
    import FreeCAD
    import Part
    import SilkMachinery as SM
    import SilkWorkflowOps as O
    from Tests import demo01_fixture_model as FM

    lines = []
    emit = lines.append
    emit("Demo 01 corner setup, read from Resources/Demo_files/Silk_Demo_01.FCStd")
    emit("instrument: Part.Face.distToShape <= 1e-6 mm then Surface.parameter "
         "for (u,v); SilkMachinery.seam_length (64 stations, 1.7e-6 relative "
         "floor) for mm from the junction corner; vertices deduplicated at "
         "1e-5 mm / 1e-6 in (u,v). READ-ONLY: no geometry is written.")
    emit("fixture for the projection: Tests/demo01_fixture_model.build(corners=False)")
    emit("")
    records = []
    hd = FreeCAD.openDocument(os.path.join(REPO, "Resources", "Demo_files",
                                           "Silk_Demo_01.FCStd"))
    scratch = FreeCAD.newDocument("ReferenceSetup")
    active = FreeCAD.ActiveDocument
    try:
        FreeCAD.setActiveDocument(scratch.Name)
        FM.build(scratch, corners=False)
        patches = [o for o in scratch.Objects
                   if getattr(o, "object_type", "") == "Patch"]
        for (name, ring, _jpt), qname, tname in zip(FM.CORNERS, QUADS, TRIS):
            strips = [scratch.getObject(b) for b in ring]
            tri = hd.getObject(tname)
            quad = hd.getObject(qname)
            emit("== %s (quad %s, tri %s)" % (name, qname, tname))
            tproj = [_project(p, patches) for p in _vertices(tri)]
            exact = [b for b in tproj if b[0] <= ON_PATCH]
            member = None
            if exact:
                names = [b[1].Name for b in exact]
                member = max(set(names), key=lambda n: names.count(n))
            emit("  TRI member patch: %s" % (member or "?"))
            for d, patch, uv in tproj:
                status = "on patch" if d <= ON_PATCH else "ON STRIP (%.3f mm off)" % d
                emit("     %-8s uv=(%.6f, %.6f)  %s"
                     % (patch.Name, uv[0], uv[1], status))
            record = {"name": name, "ring": list(ring), "quad": qname,
                      "tri": tname, "member": member, "member_uv": [],
                      "seams": [], "quad_points": []}
            if member is None:
                emit("  (no exact tri point on any base patch)")
                emit("")
                records.append(record)
                continue
            mpatch = scratch.getObject(member)
            muv = _dedup_uv([b for b in tproj
                             if b[0] <= ON_PATCH and b[1].Name == member])
            record["member_uv"] = [tuple(round(x, 6) for x in uv) for uv in muv]
            for st in strips:
                r, why = O.seam_cut_reach(st, mpatch, ring=strips)
                if r is None:
                    emit("  member seam %s: %s" % (st.Name, why))
                    continue
                axis = r["along"]
                idx = 0 if axis == "U" else 1
                vals = sorted(set(round(uv[idx], 6) for uv in muv))
                near = vals[-1] if r["corner_end"] == 1 else vals[0]
                far = vals[0] if r["corner_end"] == 1 else vals[-1]
                pieces = []
                mms = {}
                for v in vals:
                    mm = SM.seam_length(mpatch, r["side"], r["t_corner"], v)
                    mms[v] = mm
                    pieces.append("u=%.6f -> %.4f mm" % (v, mm)
                                  if axis == "U"
                                  else "v=%.6f -> %.4f mm" % (v, mm))
                emit("  member seam %s: axis=%s end=%d side=%s  %s  "
                     "setback=%.6f cut=%.6f"
                     % (st.Name, axis, r["corner_end"], r["side"],
                        ", ".join(pieces), near, far))
                record["seams"].append({
                    "strip": st.Name, "axis": axis, "end": r["corner_end"],
                    "side": r["side"], "setback": near, "cut": far,
                    "values": vals, "mm": mms,
                    "corner_mm": mms.get(near),
                    "leader_mm": mms.get(far)})
            qproj = [_project(p, patches) for p in _vertices(quad)]
            seen = set()
            for d, patch, uv in qproj:
                key = (patch.Name, round(uv[0], 6), round(uv[1], 6))
                if key in seen:
                    continue
                seen.add(key)
                tag = "on patch" if d <= ON_PATCH else "ON STRIP (%.3f mm off)" % d
                mm_note = ""
                entry = None
                if d <= ON_PATCH and patch.Name != member:
                    for st in strips:
                        if patch not in (st.PatchA, st.PatchB):
                            continue
                        if member not in (getattr(st.PatchA, "Name", None),
                                          getattr(st.PatchB, "Name", None)):
                            continue
                        r, why = O.seam_cut_reach(st, patch, ring=strips)
                        if r is None:
                            continue
                        idx = 0 if r["along"] == "U" else 1
                        mm = SM.seam_length(patch, r["side"], r["t_corner"],
                                            uv[idx])
                        mm_note = ("  seam %s axis=%s end=%d param=%.6f "
                                   "-> %.4f mm"
                                   % (st.Name, r["along"], r["corner_end"],
                                      uv[idx], mm))
                        entry = {"patch": patch.Name, "strip": st.Name,
                                 "axis": r["along"], "end": r["corner_end"],
                                 "param": uv[idx], "mm": mm}
                        break
                emit("  QUAD  %-8s uv=(%.6f, %.6f)  %s%s"
                     % (patch.Name, uv[0], uv[1], tag, mm_note))
                if entry is not None:
                    record["quad_points"].append(entry)
            emit("")
            records.append(record)
    finally:
        FreeCAD.setActiveDocument(active.Name if active else "")
        if scratch.Name in FreeCAD.listDocuments():
            FreeCAD.closeDocument(scratch.Name)
        if hd.Name in FreeCAD.listDocuments():
            FreeCAD.closeDocument(hd.Name)
    return records, lines


def measure():
    records, lines = read_setup()
    text = "\n".join(lines) + "\n"
    print(text)
    path = os.path.abspath(ARTIFACT)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as fh:
        fh.write(text)
    print("[raw output kept: %s]" % path)


if __name__ == "__main__":
    import xmlrpc.client
    code = """import sys
sys.path.insert(0, %r)
sys.path.insert(0, %r)
for m in list(sys.modules.keys()):
    if m.startswith(('Silk','Tests','ArachNURBS','demo01','demo_reference_corner_setup')):
        del sys.modules[m]
import demo_reference_corner_setup as R
R.measure()
""" % (REPO, HERE)
    result = xmlrpc.client.ServerProxy("http://127.0.0.1:9875").execute_code(code)
    print(result.get("output", ""))
    if result.get("error"):
        print("RPC ERROR:", result["error"])
    if result.get("message"):
        print("RPC MESSAGE:", result["message"])
