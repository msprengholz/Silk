"""
MANUAL MEASUREMENT -- is Silk's EDGE BLEND G2? (ticket #100, deliverable 2).

#97 measured the 4-patch corner and found the reference corner C0-exact, G1
(<= 0.48 deg), not G2 (`k_gap` to 3.1e-2 /mm).  It explicitly did **not**
measure Silk's edge blend.  This module does: for every `CubicSurface_64`
blend in `Silk_Demo_01`, it pairs the blend with each `CubicSurface_44` patch
it shares a boundary with (boundary control nets matched by
`continuity_analytic.match_boundaries`) and reports the calibrated continuity
numbers, `k_gap` and `twist_gap` included.

TWO KINDS OF `CubicSurface_64`.  Eight are driven by a `ControlGrid64_2Grid44`
(a genuine two-patch edge blend).  Four are driven by a
`ControlGrid64_3_1Grid44` (the three-patch HARD corner): their surface
degenerates along one edge (all six poles coincide) and the matched boundary's
surface normal is null, so the seam read there is not a smooth edge-blend seam
(the vacuum normal makes `g1_deg` read 90 deg by construction).  The two kinds
are therefore reported separately; the edge-blend answer is the first kind.

WHY IT MATTERS.  Upstream's `ControlGrid64_2Grid44` carries a continuity knob
(`scale_tangent_0/1`, `scale_inner_0/1`, `autoG3`), so the edge blend was
*designed* to be tunable up to G3.  If the blend is G2/G3 at its patch seams,
the corner is the only weak link in the chain and a fix is localised there.

MANUAL-ONLY: the file name is not `test_*.py`, so `Tests/suite.py` does not
discover it (it opens a 357-object document).  `Tests/test_continuity_instrument.py`
asserts this module imports, exposes `main`, and carries `MANUAL`.  The demo is
opened read-only and never saved.

Run (live GUI over XML-RPC, or in a GUI FreeCAD):

    import Tests.g2_edge_blend_probe as m; m.main()
"""

import os

import FreeCAD

import Tests.silk_nurbs as SN
import Tests.continuity_analytic as CA

MANUAL = True

DEMO_NAME = "Silk_Demo_01"

# blend-grid proxy class -> the kind of `CubicSurface_64` it drives
GRID_KIND = {"ControlGrid64_2Grid44": "edge",
             "ControlGrid64_3_1Grid44": "hard-corner"}


def demo_path():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(root, "Resources", "Demo_files", DEMO_NAME + ".FCStd")


def get_doc():
    """The open demo document, or a freshly opened copy.  Never recomputed."""
    if DEMO_NAME in FreeCAD.listDocuments():
        return FreeCAD.getDocument(DEMO_NAME)
    return FreeCAD.openDocument(demo_path())


def _cls(obj):
    proxy = getattr(obj, "Proxy", None)
    return type(proxy).__name__ if proxy is not None else ""


def blend_objects(doc):
    return [o for o in doc.Objects if _cls(o) == "CubicSurface_64"]


def patch_objects(doc):
    return [o for o in doc.Objects if _cls(o) == "CubicSurface_44"]


def blend_kind(blend_obj):
    grid = getattr(blend_obj, "Grid", None)
    return GRID_KIND.get(_cls(grid), "other") if grid is not None else "other"


def measure_blend(blend_obj, patches, n=41):
    """Every patch seam of one blend: exact c0 / g1_deg / k_gap / twist_gap."""
    an_b = SN.NurbsSurface.from_object(blend_obj)
    kind = blend_kind(blend_obj)
    seams = []
    for p in patches:
        an_p = SN.NurbsSurface.from_object(p)
        matches = CA.match_boundaries(an_b, an_p)
        if not matches:
            continue
        m = matches[0]
        c0_cn, _ = SN.c0_controlnet(an_b, m["edge_a"], an_p, m["edge_b"],
                                    reverse=m["reverse_a"])
        r = CA.measure_edges(an_b, m["edge_a"], m["reverse_a"],
                             an_p, m["edge_b"], m["reverse_b"], n=n)
        seams.append({"blend": blend_obj.Name, "kind": kind, "patch": p.Name,
                      "edge_blend": m["edge_a"], "edge_patch": m["edge_b"],
                      "reverse": bool(m["reverse_a"] or m["reverse_b"]),
                      "c0_controlnet": c0_cn,
                      "c0": r["c0"], "g1_deg": r["g1_deg"],
                      "k_gap": r["k_gap"], "twist_gap": r["twist_gap"]})
    return seams


def measure_document(doc, n=41):
    patches = patch_objects(doc)
    out = []
    for b in blend_objects(doc):
        out.extend(measure_blend(b, patches, n=n))
    return out


def _fmt(x):
    return "n/a" if x is None else "%.3e" % x


def _worst(seams):
    if not seams:
        return 0.0, 0.0
    return (max(s["k_gap"] for s in seams),
            max(s["twist_gap"] for s in seams))


def main(n=41, json_path=None):
    doc = get_doc()
    report = measure_document(doc, n=n)
    edge = [s for s in report if s["kind"] == "edge"]
    hard = [s for s in report if s["kind"] != "edge"]

    print("Silk_Demo_01 -- CubicSurface_64 (edge blend) vs CubicSurface_44 (patch)")
    print("blend             kind         patch             edge  rev  c0_cn      "
          "g1_deg   k_gap      twist")
    for r in report:
        print("  %-16s %-12s %-16s %-5s %-4s %-10s %6.4f   %-10s %-10s"
              % (r["blend"], r["kind"], r["patch"], r["edge_blend"],
                 "y" if r["reverse"] else "", _fmt(r["c0_controlnet"]),
                 r["g1_deg"], _fmt(r["k_gap"]), _fmt(r["twist_gap"])))
    wk, wt = _worst(edge)
    print()
    print("edge blends (ControlGrid64_2Grid44): %d seams, g1 max %.4f deg, "
          "worst k_gap %.3e /mm, worst twist %.3e /mm"
          % (len(edge), max((s["g1_deg"] for s in edge), default=0.0), wk, wt))
    if hard:
        hk, ht = _worst(hard)
        print("hard corners (ControlGrid64_3_1Grid44): %d seams, degenerate "
              "boundary normal (g1 reads 90 deg) -- reported, not counted"
              % len(hard))
        print("    their k_gap up to %.3e /mm, twist up to %.3e /mm" % (hk, ht))
    if json_path:
        import json
        with open(json_path, "w") as f:
            json.dump({"n": n, "seams": report,
                       "edge_worst_k_gap": wk, "edge_worst_twist_gap": wt},
                      f, indent=1)
        print("raw output -> %s" % json_path)
    return report


if __name__ == "__main__":
    main()
