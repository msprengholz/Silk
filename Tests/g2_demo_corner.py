"""
MANUAL MEASUREMENT -- the author's reference corner (ticket #97, deliverable 3).

`Resources/Demo_files/Silk_Demo_01.FCStd` is edwardvmills' own best-quality
corner: four `ControlGrid66_4Sub` junctions, each assembled from four
`SubGrid33_2Grid64` corner partial grids, each of which reads two 6x4 blend
grids (`ControlGrid64_2Grid44`) -- and the three-surface hard corner
(`ControlGrid64_3_1Grid44`).  This module measures, for every corner, the
continuity of its `CubicSurface_66` against each neighbouring
`CubicSurface_64` blend it shares a boundary with.

THIS IS THE KNOWN-ANSWER CALIBRATION FOR THE CORNER STAGE: it says what
Silk's corner actually delivers, before the same chain is ported into the
workbench (#91).

MANUAL-ONLY.  The file name does not match `test_*.py`, so `Tests/suite.py`
does not discover it.  Two reasons:
  * it opens (or touches) a 357-object document, and
  * `ArachNURBS.py` imports `FreeCAD.Gui`, so the legacy chain can only be
    evaluated in a GUI process.
It is still reachable from the suite: `Tests/test_continuity_instrument.py`
asserts this module imports and that its `main` is callable, so a rename or
a syntax break is caught even though the measurement itself is not run.

Run (live GUI over XML-RPC, or in a GUI FreeCAD):

    freecad Tests/g2_demo_corner.py

or in a running FreeCAD console:

    import Tests.g2_demo_corner as m; m.main()

The measurement is read-only: it never edits, recomputes or saves the demo
document.  `main(recompute=True)` recomputes the corner chain first, for a
session where the chain's stored shapes are stale.
"""

import math

import FreeCAD

import Tests.silk_nurbs as SN
import Tests.continuity_analytic as CA
from Tests import g2_oracle as G

MANUAL = True

DEMO_NAME = "Silk_Demo_01"


def demo_path():
    import os
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


def corner_objects(doc):
    return [o for o in doc.Objects if _cls(o) == "CubicSurface_66"]


def _blend_lookup(doc):
    """blend-grid name -> the CubicSurface_64 that draws it."""
    out = {}
    for o in doc.Objects:
        if _cls(o) == "CubicSurface_64" and getattr(o, "Grid", None) is not None:
            out[o.Grid.Name] = o
    return out


def neighbour_blends(doc, corner):
    """The CubicSurface_64 blends the corner shares a boundary with.

    Derived from the corner's four SubGrid33_2Grid64 inputs: each names two
    6x4 grid objects, and each such grid drives exactly one CubicSurface_64.
    """
    lookup = _blend_lookup(doc)
    grid = corner.Grid
    names = []
    for sub in (grid.SubGrid_0, grid.SubGrid_1, grid.SubGrid_2, grid.SubGrid_3):
        for g in (sub.Grid_0, sub.Grid_1):
            surf = lookup.get(g.Name)
            if surf is not None and surf.Name not in names:
                names.append(surf.Name)
    return [doc.getObject(n) for n in names]


def measure_pair(corner_obj, blend_obj, n=41):
    """Continuity of one corner boundary against one neighbouring blend.

    Returns a dict with the matched edge/reversal, the exact control-net C0
    gap, and both instruments' c0 / g1_deg / k_gap / twist_gap.
    """
    an_corner = SN.NurbsSurface.from_object(corner_obj)
    an_blend = SN.NurbsSurface.from_object(blend_obj)
    matches = CA.match_boundaries(an_corner, an_blend)
    if not matches:
        return {"corner": corner_obj.Name, "blend": blend_obj.Name,
                "match": None, "error": "no shared boundary found"}
    m = matches[0]
    ea, eb = m["edge_a"], m["edge_b"]
    ra, rb = m["reverse_a"], m["reverse_b"]

    c0_cn, _ = SN.c0_controlnet(an_corner, ea, an_blend, eb, reverse=ra)

    corner_bs = corner_obj.Shape.Faces[0].Surface
    blend_bs = blend_obj.Shape.Faces[0].Surface
    seam_a, across_a = G.edge_seam(corner_bs, ea, reverse=ra)
    seam_b, across_b = G.edge_seam(blend_bs, eb, reverse=rb)
    sampled = G.measure_seam(corner_bs, seam_a, across_a,
                             blend_bs, seam_b, across_b, n=n)
    exact = CA.measure_edges(an_corner, ea, ra, an_blend, eb, rb, n=n)

    return {"corner": corner_obj.Name, "blend": blend_obj.Name,
            "edge_corner": ea, "edge_blend": eb, "reverse": ra,
            "c0_controlnet": c0_cn,
            "sampled": {k: sampled[k] for k in ("c0", "g1_deg", "k_gap",
                                                "twist_gap")},
            "analytic": {k: exact[k] for k in ("c0", "g1_deg", "k_gap",
                                               "twist_gap")}}


def measure_document(doc, n=41, recompute=False):
    """Measure every corner of the demo document.  Read-only by default."""
    if recompute:
        # only the corner chain objects; never a whole-document recompute
        for corner in corner_objects(doc):
            for obj in (corner, corner.Grid):
                try:
                    obj.touch()
                except Exception:
                    pass
        doc.recompute()
    report = []
    for corner in corner_objects(doc):
        for blend in neighbour_blends(doc, corner):
            report.append(measure_pair(corner, blend, n=n))
    return report


def _fmt(x):
    return "n/a" if x is None else "%.3e" % x


def main(n=41, recompute=False, json_path=None):
    doc = get_doc()
    report = measure_document(doc, n=n, recompute=recompute)
    print("Silk_Demo_01 -- corner vs neighbouring CubicSurface_64 blends")
    print("corner           blend             edge       c0_cn      "
          "c0         g1_deg     k_gap       twist")
    for r in report:
        if r.get("match") is None and "error" in r:
            print("  %-16s %-16s %s" % (r["corner"], r["blend"], r["error"]))
            continue
        s = r["sampled"]
        a = r["analytic"]
        print("  %-16s %-16s %-9s %-10s %-10s %6.4f/%-6.4f %-10s %-10s"
              % (r["corner"], r["blend"],
                 "%s%s" % (r["edge_corner"], "(r)" if r["reverse"] else ""),
                 _fmt(r["c0_controlnet"]), _fmt(a["c0"]),
                 a["g1_deg"], s["g1_deg"], _fmt(a["k_gap"]), _fmt(a["twist_gap"])))
    if json_path:
        import json
        with open(json_path, "w") as f:
            json.dump(report, f, indent=1)
    return report


if __name__ == "__main__":
    main()
