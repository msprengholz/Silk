"""
The owned cut LIST (#130) — additive, default-off, byte-identical.

The four named scalar properties stay the FIRST cut at each axis end, so an
old document restores without a migration. Extra cuts owned by individual
corners live in a separate list, created only when one is written. Every
reader goes through `axis_cuts` / `build_intervals`, whose `extra` argument
defaults to none — the identity for every existing caller.
"""

import SilkMachinery as SM


class _Patch:
    """The four named cuts and, optionally, an owned list."""

    def __init__(self):
        self.USplit1, self.USplit2 = 0.0, 0.9
        self.VSplit1, self.VSplit2 = 0.1, 0.9
        self.ULeader1, self.ULeader2 = 0.0, 1.0
        self.VLeader1, self.VLeader2 = 0.0, 1.0

    def addProperty(self, kind, name, group, doc):
        setattr(self, name, [])

    def setEditorMode(self, name, mode):
        pass


def test_a_patch_without_a_cut_list_reads_exactly_what_it_always_read(doc):
    errors, checks = [], []
    p = _Patch()
    if hasattr(p, SM.CUT_LIST_PROP):
        errors.append("a fresh patch already carries the cut list")
    checks.append("cut_entries = %r" % (SM.cut_entries(p),))
    if SM.cut_entries(p) != []:
        errors.append("a patch without the property does not read empty")
    plain = SM.axis_intervals(p, "U")
    want = [(0.0, 0.9), (0.9, 1.0)]
    if plain != want:
        errors.append("axis_intervals(U) = %r, want %r" % (plain, want))
    checks.append("axis_intervals(U) = %r" % (plain,))
    SM.add_cut_entry(p, "U", 1, "J1", 0.643019)
    if SM.axis_intervals(p, "U") != plain:
        errors.append("writing an owned cut changed the default reader")
    with_cut = SM.axis_intervals(p, "U", extra=True)
    if len(with_cut) != 3 or abs(with_cut[0][1] - 0.643019) > 1e-12:
        errors.append("axis_intervals(extra=True) = %r" % (with_cut,))
    checks.append("with the owned cut: %r" % (with_cut,))
    gone = SM.remove_cut_entries(p, "J1")
    if len(gone) != 1 or SM.cut_entries(p) != []:
        errors.append("releasing the only owner left an entry behind")
    if SM.axis_intervals(p, "U", extra=True) != plain:
        errors.append("the cut list did not return to the identity")
    return {"pass": not errors, "errors": errors, "checks": checks}


def test_two_owners_hold_two_different_leaders_on_one_axis_end(doc):
    errors, checks = [], []
    p = _Patch()
    SM.add_cut_entry(p, "U", 1, "CB_J1_FrontTopRight", 0.6430193368732177)
    SM.add_cut_entry(p, "U", 1, "CB_J3_TopRightBack", 0.6418435275058045)
    entries = SM.cut_entries(p)
    values = [e[3] for e in entries if e[0] == "U" and e[1] == 1]
    checks.append("U end 1 entries: %r" % (entries,))
    if len(values) != 2 or abs(values[0] - values[1]) < 1e-6:
        errors.append("the two owners do not hold two different leaders")
    ivs = SM.build_intervals(*SM.split_pair(p, "U"),
                             *SM.leader_pair(p, "U"),
                             SM.cut_list_extras(p, "U"))
    checks.append("intervals with both cuts: %r" % (ivs,))
    if len(ivs) != 4 or abs(ivs[1][0] - 0.6418435275058045) > 1e-9 \
            or abs(ivs[2][0] - 0.6430193368732177) > 1e-9:
        errors.append("both cuts did not land as exact knot lines: %r" % ivs)
    # a re-cut by the same owner replaces its own entry, not the other's
    SM.add_cut_entry(p, "U", 1, "CB_J3_TopRightBack", 0.64)
    if len([e for e in SM.cut_entries(p) if e[0] == "U" and e[1] == 1]) != 2:
        errors.append("a re-cut by one owner changed the other owner's entry")
    removed = SM.remove_cut_entries(p, "CB_J1_FrontTopRight")
    left = SM.cut_entries(p)
    checks.append("after releasing J1: %r (removed %r)" % (left, removed))
    if len(removed) != 1 or len(left) != 1 or left[0][2] != "CB_J3_TopRightBack":
        errors.append("releasing one corner removed the other's cut")
    if SM.axis_cuts(*SM.split_pair(p, "U"), *SM.leader_pair(p, "U")) != [0.9]:
        errors.append("the scalar slot was disturbed by the owned entries")
    return {"pass": not errors, "errors": errors, "checks": checks}


def test_two_rolled_corners_own_and_release_only_their_own_cuts(doc):
    """Two demo corners that BOTH roll each own their cut entries (#130)."""
    import FreeCAD
    import demo01_fixture_model as DEMO
    import SilkWorkflowOps as OPS
    errors, checks = [], []
    FreeCAD.setActiveDocument(doc.Name)
    DEMO.build(doc, corners=False)
    doc.recompute()
    doc.recompute()
    for name, ring in (("CB_J1_FrontTopRight", ("B_FT", "B_FR", "B_TR")),
                       ("CB_J2_FrontRightBottom", ("B_FB", "B_FR", "B_BR"))):
        c = OPS.create_corner_blend([doc.getObject(x) for x in ring], name=name)
        checks.append("%s built %r" % (name, getattr(c, "Construction", None)))
        if getattr(c, "Construction", None) != "rolling":
            errors.append("%s did not roll" % name)
        doc.recompute()
        doc.recompute()
    top = [e for e in SM.cut_entries(doc.getObject("P_Top"))
           if e[0] == "U" and e[1] == 1]
    bottom = [e for e in SM.cut_entries(doc.getObject("P_Bottom"))
              if e[0] == "U" and e[1] == 0]
    checks.append("P_Top U end 1: %r; P_Bottom U end 0: %r" % (top, bottom))
    if len(top) != 1 or top[0][2] != "CB_J1_FrontTopRight":
        errors.append("J1's cut is not owned on P_Top")
    if len(bottom) != 1 or bottom[0][2] != "CB_J2_FrontRightBottom":
        errors.append("J2's cut is not owned on P_Bottom")
    doc.removeObject("CB_J1_FrontTopRight")
    doc.recompute()
    doc.recompute()
    top_after = [e for e in SM.cut_entries(doc.getObject("P_Top"))
                 if e[0] == "U" and e[1] == 1]
    bottom_after = [e for e in SM.cut_entries(doc.getObject("P_Bottom"))
                    if e[0] == "U" and e[1] == 0]
    checks.append("after deleting J1: P_Top %r, P_Bottom %r"
                  % (top_after, bottom_after))
    if top_after:
        errors.append("deleting J1 left its owned cut behind")
    if bottom_after != bottom:
        errors.append("deleting J1 changed J2's cut")
    return {"pass": not errors, "errors": errors, "checks": checks}


def test_corners_with_the_default_name_do_not_share_an_owner(doc):
    """Two corners built WITHOUT a name must not answer to one owner string.

    The owner of a cut is a corner identity, so it has to be UNIQUE. When the
    owner was the caller's `name` argument, every unnamed corner answered to
    "CornerBlend": the second corner read the first's cut entries as its own,
    its ring check found a "second cut" on a patch it does not carry, and the
    stage refused with "the ring's corner is OPEN ... (owned cuts: .U1 ...)".
    That is the wizard's own path (the panel does not name corners), and it
    is why three of the owner's four junctions rolled and the fourth refused.

    WOULD BE RED IF: the second unnamed corner is refused, or both corners'
    entries are stored under one owner.
    """
    import FreeCAD
    import demo01_fixture_model as DEMO
    import SilkWorkflowOps as OPS
    errors, checks = [], []
    FreeCAD.setActiveDocument(doc.Name)
    DEMO.build(doc, corners=False)
    doc.recompute()
    doc.recompute()
    made = []
    for ring in (("B_FT", "B_FR", "B_TR"), ("B_TR", "B_TBk", "B_BkR")):
        c = OPS.create_corner_blend([doc.getObject(x) for x in ring])
        doc.recompute()
        doc.recompute()
        made.append(c)
        checks.append("ring %r -> %r" % (list(ring),
                                         None if c is None
                                         else (c.Name, c.Construction,
                                               len(c.Poles or []))))
        if c is None:
            errors.append("an unnamed corner refusal on ring %r" % (list(ring),))
        elif getattr(c, "Construction", None) != "rolling":
            errors.append("an unnamed corner did not roll (%r)"
                          % (getattr(c, "Construction", None),))
        elif len(c.Poles or []) != 36:
            errors.append("an unnamed corner has %d poles"
                          % len(c.Poles or []))
    names = [c.Name for c in made if c is not None]
    if len(set(names)) != len(names):
        errors.append("two corners share one object name: %r" % (names,))
    owners = {}
    for p in [o for o in doc.Objects if getattr(o, "object_type", "") == "Patch"]:
        for e in SM.cut_entries(p):
            owners.setdefault(e[2], set()).add(p.Name)
    checks.append("cut owners in the document: %r" % (owners,))
    if len(owners) != 2:
        errors.append("the two corners stored their cuts under %d owner(s): %r"
                      % (len(owners), sorted(owners)))
    if names and any(n not in owners for n in names):
        errors.append("a corner's own name is not the owner of its cuts: "
                      "names %r, owners %r" % (names, sorted(owners)))
    return {"pass": not errors, "errors": errors, "checks": checks}


ALL_TESTS = [
    test_a_patch_without_a_cut_list_reads_exactly_what_it_always_read,
    test_two_owners_hold_two_different_leaders_on_one_axis_end,
    test_two_rolled_corners_own_and_release_only_their_own_cuts,
    test_corners_with_the_default_name_do_not_share_an_owner,
]
