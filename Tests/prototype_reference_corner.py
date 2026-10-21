#!/usr/bin/env python3
"""Tests/prototype_reference_corner.py -- THROWAWAY PROTOTYPE.

**Not a feature, not a test, not production code.** It exists to answer ONE
question with numbers and is expected to be deleted once the answer is
recorded:

    Can OUR primitives reproduce the maintainer's rolling corner at all?

The maintainer's corner (episodes 28/29 of the copy-pasta tutorial) is built
from a chain we also have -- `SubGrid33_2Grid64`, `ControlGrid66_4Sub`,
`ControlGrid64_3_1Grid44`, `CubicSurface_66`, `CubicSurface_64`. So the
question is not "can we build a corner" but "is the gap in the CORNER STAGE
(our choices: which cells, which cuts, which orientation) or in the
PRIMITIVES (what our cells and cuts can express at all)".

The way to separate them is to REMOVE our stage from the comparison: take the
ring grids the reference itself stores, feed them to our PRIMITIVES, and
compare the result pole by pole with the net the reference stores. If that
agrees, the primitives are not the limit -- whatever else differs is a choice
made above them.

Run it against the owner's running FreeCAD (the only run path -- never spawn a
window):

    flock /tmp/silk_rpc.lock -c \\
        "python3 Tests/prototype_reference_corner.py"

It (1) reads the reference offline, (2) sends the rebuild to the GUI, (3)
prints the parity, the degenerate-row census of every step, and the surfaces
built from OUR nets measured the same way the reference's stored shapes are
(area, bbox, normal-field flips at n = 39/81/150, tri-interior-to-quad
distance). Nothing is written to disk and nothing is saved; the scratch
document is closed at the end.

`--all` runs the census first: one line of parity per corner in the file.

**MEASURED (2026-10, FreeCAD 1.1.3 / OCCT 7.9, the tracked episode 29, and
episode 28 for the census).** The answer is YES, to the last bit:

    episode 29, 8 rolled corners    member net 0.000e+00, quad 0.000e+00
    episode 28, 20 quad corners      member net 0.000e+00, quad 0.000e+00
                                    (8 N-star corners not attempted: a
                                     three-member assembly with no port)

and the surfaces built from OUR nets are the reference's own shapes: 6x6
area 5059.082 mm^2 vs 5059.082, 6x4 tri area 1396.025 vs 1396.025, identical
bboxes, 0 normal-field flips at n = 39/81/150, and the same
tri-interior-to-quad distances (4.639 .. 35.521 mm, 7 %..56 % of the corner's
own 63.2 mm extent). The primitives are NOT the gap.

What the census also showed, on every one of those 20 rings, was that
`corner_grid` -- our corner stage's RING NORMALIZER -- REFUSED them while the
pair function underneath reproduced them exactly. THAT has since been fixed
(#119 follow-up): the normalizer now accepts the pairings the algebra
produces, all 40 rings of episodes 28 and 29 come through it at 0.000e+00, and
`Tests/test_corner_ring_parity.py` is the permanent instrument for it. The
rest of this docstring is the state the question was asked in. `corner_grid` accepts only rings whose
every adjacent pair shares the corner slots `CORNER_COMMON = (3, 2)` (or all
its mirror); the reference's rings share (0, 1) and (0, 2) as well, which
upstream's `SubGrid33_2Grid64` takes one pair at a time. That is the first
step that diverges, and it is a CORNER-STAGE choice, not a primitive limit.
"""

import argparse
import os
import sys

MANUAL = True

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
for _p in (REPO, HERE):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from Tests import reference_corner_diff as R          # noqa: E402


# ---------------------------------------------------------------------------
# Inside FreeCAD: the hand rebuild
# ---------------------------------------------------------------------------

REBUILD_CODE = r'''
import sys
sys.path.insert(0, %(repo)r)
sys.path.insert(0, %(here)r)
for _m in [m for m in list(sys.modules)
           if m.split(".")[0] in ("SilkMachinery", "SilkCorner",
                                  "SilkWorkflowOps", "SilkBlend", "SilkPatch",
                                  "SilkEdge", "SilkChecks",
                                  "prototype_reference_corner",
                                  "reference_corner_diff", "ArachNURBS")]:
    del sys.modules[_m]
import prototype_reference_corner as P
P.rebuild_and_report(%(ref)r, %(root)r, %(tri)r, %(doc)r, census=%(census)r)
'''


def _net(archive, name):
    """(poles, weights) of a stored grid, as FreeCAD Vectors."""
    from FreeCAD import Vector as V
    node = archive.get(name)
    poles = [V(*p) for p in (node.poles or [])]
    weights = list(node.weights or [1.0] * len(poles))
    return poles, weights


def _coins(poles, tol=1e-7):
    """Coincident pole PAIRS -- the degenerate-row census of a net."""
    n = 0
    for i in range(len(poles)):
        for j in range(i):
            if (poles[i] - poles[j]).Length <= tol:
                n += 1
    return n


def _surface_66(poles, weights):
    """A `CubicSurface_66` shape over `poles`, exactly as the class builds it."""
    import FreeCAD
    import ArachNURBS as AN
    doc = FreeCAD.ActiveDocument
    grid = doc.addObject("App::FeaturePython", "_proto_grid")
    grid.addProperty("App::PropertyVectorList", "Poles", "", "")
    grid.addProperty("App::PropertyFloatList", "Weights", "", "")
    grid.Poles = list(poles)
    grid.Weights = list(weights)
    surf = doc.addObject("Part::FeaturePython", "_proto_surf")
    AN.CubicSurface_66(surf, grid)
    surf.recompute()
    shape = surf.Shape
    doc.removeObject(surf.Name)
    doc.removeObject(grid.Name)
    return shape


def _surface_64(poles, weights):
    """A `CubicSurface_64` shape over a 6x4 net."""
    import FreeCAD
    import ArachNURBS as AN
    doc = FreeCAD.ActiveDocument
    grid = doc.addObject("App::FeaturePython", "_proto_grid64")
    grid.addProperty("App::PropertyVectorList", "Poles", "", "")
    grid.addProperty("App::PropertyFloatList", "Weights", "", "")
    grid.Poles = list(poles)
    grid.Weights = list(weights)
    surf = doc.addObject("Part::FeaturePython", "_proto_surf64")
    AN.CubicSurface_64(surf, grid)
    surf.recompute()
    shape = surf.Shape
    doc.removeObject(surf.Name)
    doc.removeObject(grid.Name)
    return shape


def rebuild_and_report(ref_path, root_name, tri_name, doc_label, census=False):
    """THE HAND REBUILD. Runs inside FreeCAD; prints; returns nothing.

    Step 1  the member grid: OUR `control_grid64_3_1` over the reference's own
            `ControlGrid44_2EdgeSegments` net, against the stored member grid.
    Step 2  the quad: OUR `subgrid33_2grid64` (pair by pair) and
            `control_grid66_4sub` over the reference's own ring, against the
            stored 6x6 -- and the same through `corner_grid`, our ring
            normalizer, to see whether the stage path accepts the ring at all.
    Step 3  the surfaces: build `CubicSurface_66` / `CubicSurface_64` from OUR
            nets and measure them the same way the reference's stored shapes
            are measured.
    """
    import FreeCAD
    import Part
    import SilkChecks
    import SilkMachinery as M

    if census:
        parity_table(ref_path)
        print("")

    archive = R.Archive(ref_path)
    corners = archive.corners()
    corner = None
    for c in corners:
        if c["root"] == root_name:
            corner = c
            break
    if corner is None:
        print("no corner rooted at %s" % root_name)
        return
    quad = archive.get(corner["root"])
    grid66 = archive.get(corner["grid"])
    member_name = corner["member_grid"]
    members = list(corner["members"])

    print("=" * 78)
    print("HAND REBUILD of %s (%s)" % (corner["root"], doc_label))
    print("  reference: %s" % os.path.basename(ref_path))
    print("  ring (assembly order): %s"
          % ", ".join("%s%s" % (m, " <- MEMBER" if m == member_name else "")
                      for m in members))
    print("=" * 78)

    # -- step 1 ---------------------------------------------------------
    print("")
    print("STEP 1  the triangular member's grid")
    g44 = (archive.get(member_name).links.get("ControlGrid44") or [None])[0]
    corner_index = int(archive.get(member_name).scalars.get("Corner", 0))
    p44 = [tuple(x) for x in archive.get(g44).poles]
    w44 = list(archive.get(g44).weights or [1.0] * 16)
    ref_member, ref_member_w = _net(archive, member_name)
    ours_member, ours_member_w = M.control_grid64_3_1(p44, w44, corner_index)
    d1 = max((ours_member[i] - ref_member[i]).Length
             for i in range(len(ref_member)))
    dw1 = max(abs(ours_member_w[i] - ref_member_w[i])
              for i in range(len(ref_member_w)))
    print("  input   %s  (Corner=%d, %d poles)"
          % (g44, corner_index, len(p44)))
    print("  ours    control_grid64_3_1(44 net, corner)  24 poles")
    print("  parity  max pole deviation %.3e mm, max weight deviation %.3e"
          % (d1, dw1))
    print("  census  reference member coincident pairs %d/276, ours %d/276"
          % (_coins(ref_member), _coins(ours_member)))

    # -- step 2 ---------------------------------------------------------
    print("")
    print("STEP 2  the quad (the 6x6 over the four ring pairs)")
    ring = [_net(archive, m) for m in members]
    subs = []
    pair_patterns = []
    refusal = None
    for i in range(len(ring)):
        a, b = ring[i], ring[(i + 1) % len(ring)]
        sp, sw, why = M.subgrid33_2grid64(a[0], a[1], b[0], b[1])
        if sp is None:
            refusal = "pair %d->%d refused: %s" % (i, (i + 1) % len(ring),
                                                   why)
            break
        subs.append((sp, sw))
        common, _why = M.pair_common(a[0], b[0], 1e-6)
        pair_patterns.append(common)
    if refusal:
        print("  RAW PAIR PATH: %s" % refusal)
        return
    praw, wraw = M.control_grid66_4sub(subs)
    ref66, ref66_w = _net(archive, quad.links["Grid"][0])
    d2 = max((praw[i] - ref66[i]).Length for i in range(len(ref66)))
    dw2 = max(abs(wraw[i] - ref66_w[i]) for i in range(len(ref66_w)))
    print("  pair patterns (our `pair_common` corner slots, ring order): %s"
          % (pair_patterns,))
    print("  ours    subgrid33_2grid64 x%d -> control_grid66_4sub  36 poles"
          % len(subs))
    print("  parity  max pole deviation %.3e mm, max weight deviation %.3e"
          % (d2, dw2))
    print("  census  reference 6x6 coincident pairs %d/630, ours %d/630"
          % (_coins(ref66), _coins(praw)))

    print("")
    print("  the SAME ring, through the corner stage's ring normalizer:")
    p_cg, w_cg, why = M.corner_grid(ring, 1e-6)
    if p_cg is None:
        print("    corner_grid REFUSED this ring: %s" % why)
        print("    (the pair path above accepts it, pole for pole -- so the "
              "refusal is the ring normalizer's, not the subgrid's)")
    else:
        d3 = max((p_cg[i] - ref66[i]).Length for i in range(len(ref66)))
        print("    corner_grid accepted it, max pole deviation %.3e mm" % d3)
        moved = max((p_cg[i] - praw[i]).Length for i in range(len(praw)))
        print("    the stage's own step (smooth_degenerate_cap) moved the "
              "poles by up to %.3e mm" % moved)

    # -- step 3 ---------------------------------------------------------
    print("")
    print("STEP 3  the surfaces, measured the same way as the reference's "
          "stored shapes")
    FreeCAD.newDocument(doc_label)
    FreeCAD.setActiveDocument(doc_label)
    our_quad = _surface_66(praw, wraw)
    our_tri = _surface_64(ours_member, ours_member_w)
    ref_quad = quad_shape_in(ref_path, corner["root"])
    ref_tri = quad_shape_in(ref_path, tri_name) if tri_name else None

    def row(tag, shape):
        if shape is None:
            print("  %-18s (not readable)" % tag)
            return
        flips = [len(SilkChecks._normal_field_flips(shape.Faces[0].Surface,
                                                    n=n)[0])
                 for n in (39, 81, 150)]
        bb = shape.BoundBox
        print("  %-18s area %10.3f  bbox (%8.3f %8.3f %8.3f)..(%8.3f %8.3f "
              "%8.3f)  flips %s"
              % (tag, shape.Area, bb.XMin, bb.YMin, bb.ZMin, bb.XMax,
                 bb.YMax, bb.ZMax, flips))

    row("reference quad", ref_quad)
    row("OUR quad", our_quad)
    row("reference tri", ref_tri)
    row("OUR tri", our_tri)

    if ref_quad is not None and ref_tri is not None:
        print("")
        print("  tri interior -> quad (sampled on the tri's own parameter "
              "rectangle, 8x8):")
        for tag, tri, qd in (("reference", ref_tri, ref_quad),
                             ("OURS", our_tri, our_quad)):
            ds = _interior_distances(tri, qd)
            ext = max(qd.BoundBox.XLength, qd.BoundBox.YLength,
                      qd.BoundBox.ZLength) or 1.0
            if ds:
                print("    %-10s min %8.3f  max %8.3f mm   (%.0f%%..%.0f%% of "
                      "the corner's own extent %.1f mm)"
                      % (tag, min(ds), max(ds), 100.0 * min(ds) / ext,
                         100.0 * max(ds) / ext, ext))

    print("")
    print("ANSWER  parity on the quad: %.3e mm;  on the member: %.3e mm."
          % (d2, d1))
    FreeCAD.closeDocument(FreeCAD.ActiveDocument.Name)


def parity_table(ref_path):
    """ONE LINE PER CORNER: does OUR chain reproduce it from HIS ring?

    The single-corner report above is a case study; this is the census. It
    runs the same two steps for every corner in the file that carries a
    triangular member, so "our primitives reproduce his construction" is a
    claim with n = the number of his corners, not with n = 1.
    """
    import SilkMachinery as M

    archive = R.Archive(ref_path)
    print("%-28s %-10s %-10s %-10s %-2s %s"
          % ("quad", "member dev", "quad dev", "corner_grid", "cp",
             "ring pair patterns"))
    rows = []
    skipped = []
    refusal_reasons = set()
    for corner in archive.corners():
        if corner["kind"] != "quad-4sub":
            # The N-STAR corners (three members, `ControlGridNStar66_NSub`
            # over `SubGrid63_2Surf64` pairs) are a DIFFERENT assembly, and
            # SilkMachinery has no port of it -- so they are outside this
            # question and are counted, not silently dropped.
            skipped.append(corner["root"])
            continue
        d1 = None
        if corner["member_grid"]:
            member = archive.get(corner["member_grid"])
            g44 = (member.links.get("ControlGrid44") or [None])[0]
            if g44 is None:
                continue
            p44 = [tuple(x) for x in archive.get(g44).poles]
            w44 = list(archive.get(g44).weights or [1.0] * 16)
            cidx = int(member.scalars.get("Corner", 0))
            ref_member, _rw = _net(archive, corner["member_grid"])
            ours_member, _wm = M.control_grid64_3_1(p44, w44, cidx)
            d1 = max((ours_member[i] - ref_member[i]).Length
                     for i in range(len(ref_member)))

        ring = [_net(archive, m) for m in corner["members"]]
        subs = []
        patterns = []
        ok = True
        for i in range(len(ring)):
            a, b = ring[i], ring[(i + 1) % len(ring)]
            sp, sw, _why = M.subgrid33_2grid64(a[0], a[1], b[0], b[1])
            if sp is None:
                ok = False
                break
            subs.append((sp, sw))
            patterns.append(M.pair_common(a[0], b[0], 1e-6)[0])
        if not ok:
            print("%-28s  pair path refused" % corner["root"])
            continue
        praw, _wraw = M.control_grid66_4sub(subs)
        ref66, _r66w = _net(archive, corner["grid"])
        if len(ref66) != len(praw):
            print("%-28s  no stored 6x6 net in this file (the grid is a "
                  "computed object); parity not readable offline"
                  % corner["root"])
            continue
        d2 = max((praw[i] - ref66[i]).Length for i in range(len(ref66)))
        verdict = "ACCEPT"
        p_cg, _w_cg, why = M.corner_grid(ring, 1e-6)
        if p_cg is None:
            verdict = "refuse"
            if why and why not in refusal_reasons:
                refusal_reasons.add(why)
        rows.append((corner["root"], d1, d2, verdict, patterns))
        print("%-28s %-10s %-10.3e %-10s %-2d %s"
              % (corner["root"],
                 "-" if d1 is None else "%.3e" % d1,
                 d2, verdict, _coins(ref66), patterns))
    worst = max([max([x for x in r[1:3] if x is not None] or [0.0])
                 for r in rows] or [0.0])
    refused = [r[0] for r in rows if r[3] == "refuse"]
    print("")
    if skipped:
        print("%d N-star corners not attempted (three-member assembly; no "
              "port in SilkMachinery): %s"
              % (len(skipped), ", ".join(skipped)))
    print("%d corners reproduced from HIS OWN ring grids; worst deviation "
          "%.3e mm ('member dev' is '-' where the corner has no triangular "
          "member)." % (len(rows), worst))
    print("%d of %d rings are REFUSED by our ring normalizer `corner_grid` -- "
          "the pair path reproduces them pole for pole, so the refusal is the "
          "stage's normalization, not the primitives."
          % (len(refused), len(rows)))
    for why in sorted(refusal_reasons):
        print("  corner_grid says: %s" % why)
    print("  `corner_grid` accepts ONLY rings whose every adjacent pair shares "
          "the corner slots CORNER_COMMON = (%d, %d) or all their mirror; the "
          "reference's rings share (%s) and (%s) too, which upstream's "
          "`SubGrid33_2Grid64` takes one pair at a time."
          % (M.CORNER_COMMON[0], M.CORNER_COMMON[1], "0, 1", "0, 2"))
    return rows


def quad_shape_in(ref_path, name):
    """The STORED shape of `name` in the reference, if it is open in the GUI."""
    import FreeCAD
    doc = _open_doc(ref_path, name)
    if doc is None:
        return None
    obj = doc.getObject(name)
    if obj is None or not hasattr(obj, "Shape") or obj.Shape.isNull():
        return None
    return obj.Shape


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


def _open_doc(ref_path, object_name=None):
    """The reference document if the GUI has it open, else None.

    A reference file is READ, never written. Matching is by FILE NAME FIRST:
    every copy-pasta episode names its objects the same way, so an
    object-name match alone silently reads the wrong episode (it did: 66_014
    in file 28 is a plain corner 13.9e3 mm^2, in file 29 a rolled one 5.1e3
    mm^2). The object name is only the fallback, for a document saved under
    another path. If nothing matches this returns None rather than opening --
    and later closing -- a document that might be the owner's; the XML reader
    carries the same facts.
    """
    import FreeCAD
    want = os.path.basename(ref_path)
    docs = list(FreeCAD.listDocuments().items())
    for _n, d in docs:
        if d.FileName and os.path.basename(d.FileName) == want:
            return d
    for _n, d in docs:
        if object_name is not None and d.getObject(object_name) is not None:
            return d
    return None


# ---------------------------------------------------------------------------
# Local driver
# ---------------------------------------------------------------------------

def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Rebuild the maintainer's rolling corner from OUR "
                    "primitives and compare, pole for pole.")
    ap.add_argument("--ref", default=R.default_reference("29"),
                    help="the reference .FCStd (default: the tracked copy of "
                         "episode 29)")
    ap.add_argument("--corner", default="auto",
                    help="'auto' (smallest tri area) or a root name")
    ap.add_argument("--all", action="store_true",
                    help="the census: one line of parity per corner in the "
                         "file, then the single-corner case study")
    ap.add_argument("--no-rpc", action="store_true",
                    help="offline only: print what would be sent")
    args = ap.parse_args(argv)

    if not os.path.exists(args.ref):
        raise SystemExit("%s does not exist -- see the docstring of "
                         "Tests/reference_corner_diff.py (--fetch)" % args.ref)
    archive = R.Archive(args.ref)
    corner, why = R.pick_corner(archive, args.corner)
    print("PICK  %s" % why)

    boot = REBUILD_CODE % {"repo": REPO, "here": HERE,
                           "ref": os.path.abspath(args.ref),
                           "root": corner["root"],
                           "tri": corner["tri"],
                           "doc": "_proto_refcorner",
                           "census": bool(args.all)}
    if args.no_rpc:
        print(boot)
        return 0
    print(R.rpc_execute(boot, timeout=1800))
    return 0


if __name__ == "__main__":
    sys.exit(main())
