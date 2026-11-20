"""The rolling corner's placement is DERIVED, not a typed parameter.

WHAT IS PINNED

  1. The setback a corner finds on the member patch is the seam's OWN band
     width. The stage does not rewrite it (a width the user set is his, #64),
     and there is no global 1/16 anywhere on the automatic path.
  2. The two cut sides are EQUALISED in mm from those two band widths
     (#129's `equal_cut_length`, geometric mean), so a seam twice as long
     does not hand its triangle twice the side.
  3. Both hold on the demo's four structurally different junctions, whose
     seams carry different widths in mm.

INSTRUMENT: `SilkWorkflowOps.seam_cut_reach` reads the band width in mm on the
patch's own seam curve (64 stations, relative floor 1.7e-6); `seam_cut_length`
reads the cut side on the same curve, with `owner` so a shared axis end reads
this corner's cut (#130). Both are printed mm values, not parameters.
"""

import math

import FreeCAD

from Tests.mcp_harness import check

BAND_FLOOR = 1e-9       # mm: equality of a written band edge with its seed
CUT_FLOOR = 1e-6        # mm: the seam-length instrument's relative floor


def _cube(doc, band=None):
    from Tests import cube_corner_model as ccm
    ccm.build_cube_corner_model(doc)
    doc.recompute()
    if band is not None:
        for name in ("PatchA", "PatchB", "PatchC"):
            p = doc.getObject(name)
            p.USplit1 = band
            p.VSplit1 = band
        doc.recompute()
    doc.recompute()
    strips = [doc.getObject(n) for n in ("B_AB", "B_BC", "B_CA")]
    return strips, None


def _demo(doc):
    from Tests import demo01_fixture_model as FM
    result = FM.build(doc, corners=False)
    if result["problems"]:
        raise RuntimeError("demo fixture: %r" % (result["problems"],))
    strips = {name: [doc.getObject(b) for b in ring]
              for name, ring, _pt in FM.CORNERS}
    return None, strips


def _legs(strips, corner, patch):
    import SilkWorkflowOps as OPS
    rows = []
    for s in corner.Strips:
        reach, why = OPS.seam_cut_reach(s, patch, ring=strips)
        if reach is None:
            continue
        leg, lwhy = OPS.seam_cut_length(s, patch, ring=strips,
                                        owner=corner.Name)
        rows.append((s.Name, reach["corner_mm"], leg, lwhy))
    return rows


def _member(corner):
    from SilkCorner import recorded_member_pin
    pin = recorded_member_pin(corner)
    return pin[0] if pin else None


def test_the_seams_band_width_is_left_alone_and_feeds_the_cut(doc):
    """A corner with nothing typed consumes the band edges it finds (0.1 on
    this fixture), and places both cut sides at that same length in mm.

    WOULD BE RED IF: the automatic path still writes the 1/16 setback (it did
    in #133), or the cut still sits at 0.25 of the parameter (11.26/41.70 mm
    on the demo's J1 instead of equal 6.92 mm sides).
    """
    import SilkWorkflowOps as OPS
    errors, checks = [], []
    strips, _ = _cube(doc)
    patches = [doc.getObject(n) for n in ("PatchA", "PatchB", "PatchC")]
    before = {(p.Name, prop): float(getattr(p, prop))
              for p in patches for prop in ("USplit1", "VSplit1")}
    corner = OPS.create_corner_blend(strips, name="Derived")
    doc.recompute()
    doc.recompute()
    if corner is None:
        return {"pass": False, "errors": ["the corner was not built"],
                "checks": checks}
    patch = _member(corner)
    for p in patches:
        for prop in ("USplit1", "VSplit1"):
            now = float(getattr(p, prop))
            checks.append("%s.%s %.17g -> %.17g"
                          % (p.Name, prop, before[(p.Name, prop)], now))
            check(abs(now - before[(p.Name, prop)]) <= BAND_FLOOR,
                  "%s.%s: the corner rewrote the seam's band width %g -> %g"
                  % (p.Name, prop, before[(p.Name, prop)], now), errors)
    rows = _legs(strips, corner, patch)
    checks.append("cut sides: %r" % [(n, round(w, 6), round(l, 6))
                                      for n, w, l, _ in rows])
    check(len(rows) == 2, "the member patch reports %d cut sides" % len(rows),
          errors)
    if len(rows) == 2:
        check(all(abs(l - w) <= CUT_FLOOR for _n, w, l, why in rows),
              "the cut side is not the seam's own band width: %r" % rows,
              errors)
    return {"pass": not errors, "errors": errors, "checks": checks}


def test_a_user_band_width_moves_the_derived_placement(doc):
    """A width the USER wrote (0.2, not Silk's 0.1 blend default) is kept,
    and the cut is re-derived from it. Under the retired 1/16 + 0.25 rule
    this same build left the band at 0.2 and the cut side at 0.05 mm.
    """
    import SilkWorkflowOps as OPS
    errors, checks = [], []
    strips, _ = _cube(doc, band=0.2)
    corner = OPS.create_corner_blend(strips, name="UserBand")
    doc.recompute()
    doc.recompute()
    patch = _member(corner)
    rows = _legs(strips, corner, patch)
    checks.append("user band 0.2: %r"
                  % [(n, round(w, 6), round(l, 6)) for n, w, l, _ in rows])
    for p in (doc.getObject("PatchA"),):
        check(abs(p.USplit1 - 0.2) <= BAND_FLOOR
              and abs(p.VSplit1 - 0.2) <= BAND_FLOOR,
              "the user's 0.2 band was overwritten: %r / %r"
              % (p.USplit1, p.VSplit1), errors)
    check(len(rows) == 2 and all(abs(l - 0.2) <= CUT_FLOOR
                                 for _n, w, l, why in rows),
          "the cut was not derived from the user's band: %r" % rows, errors)
    return {"pass": not errors, "errors": errors, "checks": checks}


def test_all_four_demo_junctions_derive_from_their_own_seams(doc):
    """The demo's four junctions have structurally different seams: their
    band widths in mm must differ corner by corner and both cut sides must
    still be equal there. A single global setback cannot produce this table.
    """
    import SilkWorkflowOps as OPS
    errors, checks = [], []
    _, rings = _demo(doc)
    seen = []
    for name, strips in rings.items():
        corner = OPS.create_corner_blend(strips, name=name)
        doc.recompute()
        doc.recompute()
        if corner is None:
            errors.append("%s was not built" % name)
            continue
        patch = _member(corner)
        rows = _legs(strips, corner, patch)
        widths = [w for _n, w, _l, _why in rows]
        legs = [l for _n, _w, l, _why in rows]
        checks.append("%s: bands %r mm, cut sides %r mm"
                      % (name, [round(w, 4) for w in widths],
                         [round(l, 4) for l in legs]))
        check(len(rows) == 2, "%s: %d cut sides" % (name, len(rows)), errors)
        if len(rows) != 2:
            continue
        target = math.sqrt(widths[0] * widths[1])
        check(abs(legs[0] - legs[1]) <= CUT_FLOOR,
              "%s: cut sides are unequal %.6f / %.6f mm"
              % (name, legs[0], legs[1]), errors)
        check(abs(legs[0] - target) <= CUT_FLOOR * max(1.0, target),
              "%s: cut side %.6f mm is not the band widths' geometric mean "
              "%.6f mm" % (name, legs[0], target), errors)
        seen.append(tuple(round(w, 3) for w in widths))
    check(len(set(seen)) >= 2,
          "the four demo junctions all read the same band widths %r -- "
          "a global setback, not a derived one" % (seen,), errors)
    return {"pass": not errors, "errors": errors, "checks": checks}
