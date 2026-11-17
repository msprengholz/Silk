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


ALL_TESTS = [
    test_a_patch_without_a_cut_list_reads_exactly_what_it_always_read,
    test_two_owners_hold_two_different_leaders_on_one_axis_end,
]
