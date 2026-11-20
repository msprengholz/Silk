"""Replaying the Demo 01 corner setup needs OWNED cuts, not raw scalars.

The #130 cut list holds one value per (patch, axis end, owner). Two corners
may claim the same patch end; each must then read its OWN cut. A raw scalar
write makes every ring see the last value and open the ring (#127).
"""

import FreeCAD


def test_two_owners_can_hold_different_cuts_on_one_patch_end(doc):
    """WOULD BE RED IF: the shared slot were written as a bare scalar -- both
    owners would read the same value and the second corner's ring would be
    open on the first corner's cut."""
    import SilkMachinery as SM
    errors, checks = [], []
    from Tests import cube_corner_model as ccm
    ccm.build_cube_corner_model(doc)
    doc.recompute()
    p = doc.getObject("PatchA")
    SM.set_owned_cut(p, "U", 0, 0.20, "CornerA")
    SM.set_owned_cut(p, "U", 0, 0.35, "CornerB")
    a = SM.corner_leader_pair(p, "U", "CornerA")[0]
    b = SM.corner_leader_pair(p, "U", "CornerB")[0]
    entries = [e for e in SM.cut_entries(p) if e[:3] == ("U", 0, "CornerB")]
    checks.append("Cut list: %r; owners read A=%.17g, B=%.17g"
                  % (SM.cut_entries(p), a, b))
    if abs(a - 0.20) > 1e-12 or abs(b - 0.35) > 1e-12:
        errors.append("the two owners read %r / %r instead of their own cuts"
                      % (a, b))
    if len(entries) != 1 or abs(entries[0][3] - 0.35) > 1e-12:
        errors.append("the second cut was not recorded for its owner: %r"
                      % (entries,))
    return {"pass": not errors, "errors": errors, "checks": checks}


def test_one_demo_junction_replays_from_his_setup(doc):
    """J1's values come from the read-only reference instrument; the corner
    is built through the owner-tagged cut list and assembles rolling."""
    import SilkChecks as CK
    import SilkCorner as SC
    import SilkMachinery as SM
    import demo_reference_replay as REPLAY
    import demo_reference_corner_setup as REF
    from Tests import demo01_fixture_model as FM

    errors, checks = [], []
    fixture = FM.build(doc, corners=False)
    if fixture["problems"]:
        return {"pass": False,
                "errors": ["fixture: %r" % fixture["problems"]],
                "checks": checks}
    records = REF.read_setup()[0]
    j1 = [r for r in records if r["name"] == "CB_J1_FrontTopRight"][0]
    result = REPLAY.replay(doc, records=[j1])
    corner = result["corners"].get(j1["name"])
    checks.append("problems=%r" % (result["problems"],))
    if corner is None:
        return {"pass": False, "errors": ["J1 refused: %r" % result["problems"]],
                "checks": checks}
    doc.recompute()
    doc.recompute()
    bad = [x for x in CK.check_corner_blend(corner, *list(corner.Strips))
           if not x[1]]
    checks.append("construction=%r, pin=%r, poles=%d, faces=%d, bad=%r"
                  % (SC.corner_construction(corner)[0],
                     SC.recorded_member_pin(corner)[1], len(corner.Poles),
                     len(corner.Shape.Faces), bad))
    if SC.corner_construction(corner)[0] != "rolling" or bad:
        errors.append("the replayed corner is not a green rolling corner")
    if SC.recorded_member_pin(corner)[0].Name != "P_Right":
        errors.append("the member is not his P_Right")
    owned = [e for e in SM.cut_entries(SC.recorded_member_pin(corner)[0])
             if e[2] == corner.Name]
    checks.append("owned cut entries: %r" % (owned,))
    if len(owned) < 2:
        errors.append("J1's cuts were not recorded under its own name")
    return {"pass": not errors, "errors": errors, "checks": checks}


def test_a_replayed_cut_is_recorded_under_the_corner_name(doc):
    """The replay helper writes the scalar slot AND the owner's cut entry,
    so a corner created afterwards reads its own value (#130/#131)."""
    import SilkMachinery as SM
    errors, checks = [], []
    from Tests import cube_corner_model as ccm
    ccm.build_cube_corner_model(doc)
    doc.recompute()
    p = doc.getObject("PatchA")
    SM.set_owned_cut(p, "V", 1, 0.42, "CB_J1")
    got = SM.corner_leader_pair(p, "V", "CB_J1")[1]
    prop = SM.leader_cut_prop("V", 1)
    checks.append("%s=%.17g, owned read=%.17g"
                  % (prop, float(getattr(p, prop)), got))
    if (abs(float(getattr(p, prop)) - 0.42) > 1e-12
            or abs(got - 0.42) > 1e-12):
        errors.append("the owned cut did not reach the patch's scalar slot")
    return {"pass": not errors, "errors": errors, "checks": checks}
