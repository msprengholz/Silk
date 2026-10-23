"""The rolled corner FOLLOWS its inputs (#132) -- fast tier, cube fixture.

THE OWNER'S ASK (2026-10-22): *"to make the rolling corner look nice, i need
control of the initial blends.  can i already update these and rolling corner
will follow?  ideally, the patch setback would also recalculate (make it
optional though) to make the triangle patch again."*

The corner already REBUILDS when a ring patch's band edge moves (the #109
chain), but its CUT stayed where the corner stage stored it -- so the band
moved out from under the cut and the triangular member stopped being the
triangle it was placed as.  Measured on the demo's `CB_J1_FrontTopRight`
(`Tests/corner_follows_inputs.py`, the instrument): the two sides are
17.435446 / 17.435446 mm at the 0.1 setback and 17.435446 / 5.965472 mm once
`P_Top.VSplit1` is 0.15.

TWO MODES, and the pair is what these tests measure:

    LeaderMode   "auto" (default) -- the cut is RE-DERIVED from the band edges
                                     by the stage's own rule (the equalising
                                     rule), so the triangle's two sides are
                                     equal again at the NEW geometry;
                 "fixed"          -- the stored cut is kept (the behaviour of
                                     before this ticket; a length somebody
                                     typed sets this, and keeps it).
    SetbackMode  "fixed" (default) -- the band edges are NEVER written (a band
                                     edge is the user's own width, #64);
                 "auto"           -- the carrying patch's setback AND the
                                     triangle's cut side are the corner's, and
                                     both are put back where the corner PLACED
                                     them (`SilkCorner._CutReference`): the
                                     band edge as a parameter (the triangle's
                                     share of the patch), the cut side in mm
                                     (its size).

WHY IT CANNOT LOOP, measured rather than argued: each derivation's answer does
not depend on the value it is about to write (the leader rule seeds from
`ROLLING_LEADER`'s own parameter, never from the stored cut; the setback rule
is a restore of two constants).  So the second pass of a document recompute
finds nothing to write -- `test_a_following_corner_settles` is that bar
(#125): 3 x `doc.recompute()`, nothing Touched, and none of the corner's 36
poles moving afterwards.

The cube fixture is the fast tier's: 1 mm seams, a 0.1 setback, exact planar
squares, so a millimetre and the axis parameter are the same number there and
every reading below can be checked by hand.
"""

# --- fast tier -----------------------------------------------------------
# The subject is one invariant per test (does the cut follow? does the
# setback stay? does the document settle?), measured on the small fixture, so
# this module belongs in the default tier.  The DEMO junction's own hand-back
# table is the MANUAL instrument `Tests/corner_follows_inputs.py`.
MANUAL = False

import time

import FreeCAD

from SilkCorner import (LEADER_MODE_AUTO, LEADER_MODE_FIXED, SETBACK_MODE_AUTO,
                        SETBACK_MODE_FIXED, corner_construction, follow_modes)
from SilkWorkflowOps import (create_corner_blend, seam_cut_length,
                             seam_cut_reach, set_follow_modes,
                             CORNER_CONSTRUCTION_SHIPPED, CUT_LENGTH_TOL)

STRIP_NAMES = ("B_AB", "B_BC", "B_CA")
PATCH_NAMES = ("PatchA", "PatchB", "PatchC")
SCRATCH = "_follow_scratch"

# `test_document_settles`'s bar, per recompute, on this fixture: a settled
# corner's document pass is milliseconds (#125 measured 0.0004 s).
SETTLE_SECONDS = 0.05

# A pole that moved by less than this is the same pole: the corner's own
# `CubicSurface_66` chain is exact, so a re-derivation that lands on the same
# cut lands on the same 36 poles (measured: 1.2e-13 mm on the demo, from the
# length instrument's own 1e-16 parameter residual).
POLE_TOL = 1e-9


# ---------------------------------------------------------------------------
# Reading the fixture
# ---------------------------------------------------------------------------

def _build(doc, construction=None, setback_edit=None):
    """The cube-corner ring and its corner, built in `doc`."""
    from Tests.cube_corner_model import build_cube_corner_model
    build_cube_corner_model(doc)
    strips = [doc.getObject(n) for n in STRIP_NAMES]
    if setback_edit is not None and construction is None:
        patch = _member_patch(None, strips)
        prop, _cur, value = _setback_write(patch, strips)
        setattr(patch, prop, value)
        doc.recompute()
    kw = {} if construction is None else {"construction": construction}
    corner = create_corner_blend(strips, **kw)
    doc.recompute()
    doc.recompute()
    return strips, corner


def _member_patch(corner, strips):
    """The ring patch that carries the triangular member: the corner's own
    recorded placement, else the stage's search (an unset pin means "the
    search decides", #117)."""
    from SilkCorner import corner_member_pin, CORNER_DEFAULT_TOL
    patch = getattr(corner, "MemberPatch", None) if corner is not None else None
    if patch is None:
        found, _why = corner_member_pin(strips, CORNER_DEFAULT_TOL)
        patch = found[0] if found is not None else None
    return patch


def _setback_write(patch, strips):
    """`(property, current, moved)` for the carrying patch's own setback
    moved 0.05 mm IN from the junction corner -- the initial-blend edit the
    owner is talking about.  The cube's seams are 1 mm long, so 0.05 mm is
    the axis parameter 0.05."""
    from SilkBlend import band_edge_prop
    for s in strips:
        if patch not in (getattr(s, "PatchA", None),
                         getattr(s, "PatchB", None)):
            continue
        reach, why = seam_cut_reach(s, patch, ring=strips)
        if reach is None:
            raise RuntimeError("no reach on %s: %s" % (s.Name, why))
        prop = band_edge_prop(reach["along"], reach["corner_end"])
        cur = float(getattr(patch, prop))
        moved = cur + 0.05 if reach["corner_end"] == 0 else cur - 0.05
        return prop, cur, moved
    raise RuntimeError("%s carries no ring seam" % patch.Name)


def _sides(strips, patch):
    """`{seam: mm}` -- the cut side that bounds the triangular member, per
    rolled seam (`seam_cut_length`, the stage's own instrument)."""
    out = {}
    for s in strips:
        if patch not in (getattr(s, "PatchA", None),
                         getattr(s, "PatchB", None)):
            continue
        length, _why = seam_cut_length(s, patch, ring=strips)
        out[s.Name] = length
    return out


def _cuts(patch):
    """The patch's eight cut values: the two band edges and the two leader
    cuts of each axis."""
    from SilkMachinery import leader_pair, split_pair
    return {"U": split_pair(patch, "U") + leader_pair(patch, "U"),
            "V": split_pair(patch, "V") + leader_pair(patch, "V")}


def _cut_delta(before, after):
    """The largest change between two `_cuts` readings, mm/parameter."""
    out = 0.0
    for letter in ("U", "V"):
        for a, b in zip(before[letter], after[letter]):
            out = max(out, abs(float(a) - float(b)))
    return out


def _leader_params(patch):
    """`{property: value}` of the patch's four leader cuts."""
    from SilkMachinery import is_leader_cut_prop, leader_cut_prop
    return {leader_cut_prop(letter, end):
            float(getattr(patch, leader_cut_prop(letter, end)))
            for letter in ("U", "V") for end in (0, 1)
            if is_leader_cut_prop(leader_cut_prop(letter, end))}


def _pole_move(a, b):
    """The largest distance any pole moved between two 36-pole readings."""
    return max((FreeCAD.Vector(*x) - FreeCAD.Vector(*y)).Length
               for x, y in zip(a, b))


def _coins(poles, tol=1e-9):
    """Coincident pole pairs in a 6x6 net -- a collapsed side shows up here
    as 15 pairs on one row/column, which is a DEGENERATE corner, not a fold."""
    return sum(1 for i in range(len(poles)) for j in range(i + 1, len(poles))
               if (poles[i] - poles[j]).Length <= tol)


# ---------------------------------------------------------------------------
# 1. auto: the cut is re-derived, and equals what a fresh build places
# ---------------------------------------------------------------------------

def test_the_cut_follows_the_band_edges_in_auto_mode(doc):
    """`LeaderMode = "auto"`, the default: moving the carrying patch's setback
    re-derives the cut by the equalising rule, so the two sides that bound the
    triangle are equal again -- and they are the numbers a FRESH build at that
    setback places, which is what "the way a fresh build would" means."""
    errors, checks = [], []
    strips, corner = _build(doc)
    patch = _member_patch(corner, strips)
    leader_mode, setback_mode = follow_modes(corner)
    checks.append("built: leader %s, setback %s, sides %s"
                  % (leader_mode, setback_mode,
                     {k: round(v, 9) for k, v in _sides(strips, patch).items()}))
    if (leader_mode, setback_mode) != (LEADER_MODE_AUTO, SETBACK_MODE_FIXED):
        errors.append("a corner this stage built reads (%r, %r), not the "
                      "default (%r, %r)"
                      % (leader_mode, setback_mode, LEADER_MODE_AUTO,
                         SETBACK_MODE_FIXED))
    built_sides = _sides(strips, patch)
    prop, cur, moved = _setback_write(patch, strips)
    leaders_before = _leader_params(patch)
    setattr(patch, prop, moved)
    doc.recompute()
    after = _sides(strips, patch)
    leaders_after = _leader_params(patch)
    checks.append("edit %s.%s %g -> %g: sides %s (were %s)"
                  % (patch.Name, prop, cur, moved,
                     {k: round(v, 9) for k, v in after.items()},
                     {k: round(v, 9) for k, v in built_sides.items()}))
    if len(after) != 2 or any(v is None for v in after.values()):
        return {"pass": False,
                "errors": ["the carrying patch reports %d cut side(s) after "
                           "the edit: %s" % (len(after), after)],
                "checks": checks}
    lo, hi = min(after.values()), max(after.values())
    checks.append("the two sides are equal to %.3e mm (tolerance %.1e)"
                  % (hi - lo, CUT_LENGTH_TOL))
    if hi - lo > CUT_LENGTH_TOL:
        errors.append("auto mode left the triangle UNEQUAL: %s"
                      % ({k: round(v, 9) for k, v in after.items()},))
    moved_leaders = {k: (leaders_before[k], v) for k, v in leaders_after.items()
                     if abs(leaders_before[k] - v) > 0.0}
    checks.append("the cut was re-derived: leader cuts %s"
                  % {k: (round(a, 9), round(b, 9))
                     for k, (a, b) in moved_leaders.items()})
    if not moved_leaders:
        errors.append("the cut did not move at all -- the band edge moved "
                      "under it and the triangle kept the old sides")

    # THE FRESH-BUILD CROSS-CHECK: the same edit made BEFORE the corner is
    # built has to give the same sides, or "follows its inputs" means
    # something other than "what the stage would place".
    if SCRATCH in FreeCAD.listDocuments():
        FreeCAD.closeDocument(SCRATCH)
    sdoc = FreeCAD.newDocument(SCRATCH)
    try:
        FreeCAD.setActiveDocument(sdoc.Name)
        _strips, fresh = _build(sdoc, setback_edit=True)
        fresh_patch = _member_patch(fresh, _strips)
        fresh_sides = _sides(_strips, fresh_patch)
        checks.append("a FRESH build at the moved setback: sides %s"
                      % {k: round(v, 9) for k, v in fresh_sides.items()})
        worst = max(abs(after[k] - fresh_sides[k]) for k in fresh_sides)
        checks.append("|followed - fresh| %.3e mm" % worst)
        if worst > 1e-6:
            errors.append("the followed corner is not what a fresh build "
                          "places: %s vs %s"
                          % ({k: round(v, 9) for k, v in after.items()},
                             {k: round(v, 9) for k, v in fresh_sides.items()}))
    finally:
        if SCRATCH in FreeCAD.listDocuments():
            FreeCAD.closeDocument(SCRATCH)
        if doc.Name in FreeCAD.listDocuments():
            FreeCAD.setActiveDocument(doc.Name)
    return {"pass": not errors, "errors": errors, "checks": checks}


# ---------------------------------------------------------------------------
# 2. fixed: the stored cut is kept -- the behaviour of before this ticket
# ---------------------------------------------------------------------------

def test_fixed_mode_keeps_the_stored_cut(doc):
    """`LeaderMode = "fixed"`: today's behaviour, byte for byte.  The band
    edge moves, the corner rebuilds around it, and the CUT does not move --
    which is exactly the defect #132 was filed for, kept on purpose for a
    length somebody typed."""
    errors, checks = [], []
    strips, corner = _build(doc)
    patch = _member_patch(corner, strips)
    set_follow_modes(corner, leader=LEADER_MODE_FIXED, setback=SETBACK_MODE_FIXED)
    doc.recompute()
    built_sides = _sides(strips, patch)
    leaders_before = _leader_params(patch)
    poles_before = [tuple(p) for p in corner.Poles]
    prop, cur, moved = _setback_write(patch, strips)
    setattr(patch, prop, moved)
    doc.recompute()
    after = _sides(strips, patch)
    checks.append("fixed mode, %s.%s %g -> %g: sides %s"
                  % (patch.Name, prop, cur, moved,
                     {k: round(v, 9) for k, v in after.items()}))
    cut_move = max(abs(leaders_before[k] - v)
                   for k, v in _leader_params(patch).items())
    checks.append("the stored cut moved by %.3e (leader parameters)"
                  % cut_move)
    if cut_move != 0.0:
        errors.append("fixed mode MOVED the stored cut by %g" % cut_move)
    if abs(after[list(after)[0]] - built_sides[list(built_sides)[0]]) <= 1e-9:
        errors.append("fixed mode shifted the triangle's own side -- the cut "
                      "was expected to stay and the band to move under it")
    values = [v for v in after.values() if v is not None]
    if len(values) == 2 and abs(values[0] - values[1]) <= CUT_LENGTH_TOL:
        errors.append("fixed mode left the triangle EQUAL -- the band edge "
                      "did not move the cut at all, so this measures nothing")
    # the corner itself did rebuild (the #109 chain), so the cut really was
    # left behind rather than the whole object going stale
    body = _pole_move(poles_before, [tuple(p) for p in corner.Poles])
    checks.append("the corner rebuilt around the moved band: %.3e mm of pole "
                  "motion" % body)
    if body <= 1e-9:
        errors.append("the corner did not rebuild after the band-edge edit -- "
                      "the #109 chain is broken")
    return {"pass": not errors, "errors": errors, "checks": checks}


# ---------------------------------------------------------------------------
# 3. setback auto: the corner puts the patch's setback back where it placed it
# ---------------------------------------------------------------------------

def test_setback_auto_puts_the_band_edge_back(doc):
    """`SetbackMode = "auto"`: the carrying patch's setback is the corner's,
    and it is put back where the corner PLACED the triangle's cut
    (`SilkCorner._CutReference`), together with the cut side itself.

    The rule, stated once: the recorded pair -- the band edge as a parameter
    and the cut side in mm -- is a CONSTANT, so this is a restore and not a
    search: it lands on the built corner from any state, and it cannot chase
    the leader rule.  That is what makes the edit reversible: the user's 0.05
    in is undone exactly, and the corner's 36 poles come back to 0.000e+00."""
    errors, checks = [], []
    strips, corner = _build(doc)
    patch = _member_patch(corner, strips)
    built_sides = _sides(strips, patch)
    poles_before = [tuple(p) for p in corner.Poles]
    progress = _cuts(patch)
    set_follow_modes(corner, leader=LEADER_MODE_AUTO, setback=SETBACK_MODE_AUTO)
    doc.recompute()
    prop, cur, moved = _setback_write(patch, strips)
    setattr(patch, prop, moved)
    doc.recompute()
    after = _sides(strips, patch)
    checks.append("setback auto, %s.%s: the user wrote %g, the corner placed "
                  "%.17g (difference %.3e)"
                  % (patch.Name, prop, moved, float(getattr(patch, prop)),
                     float(getattr(patch, prop)) - cur))
    if abs(float(getattr(patch, prop)) - cur) > 1e-9:
        errors.append("the setback was not put back where the corner placed "
                      "it: it reads %.17g, and the corner placed %g"
                      % (float(getattr(patch, prop)), cur))
    worst = max(abs(after[k] - built_sides[k]) for k in built_sides)
    checks.append("the triangle's sides after the edit: %s (|d| %.3e mm "
                  "against the build)"
                  % ({k: round(v, 9) for k, v in after.items()}, worst))
    if worst > 1e-6:
        errors.append("setback auto did not put the triangle back: %s vs "
                      "the built %s"
                      % ({k: round(v, 9) for k, v in after.items()},
                         {k: round(v, 9) for k, v in built_sides.items()}))
    body = _pole_move(poles_before, [tuple(p) for p in corner.Poles])
    checks.append("the corner came back to its built geometry: %.3e mm of "
                  "pole motion, cuts moved by %.3e"
                  % (body, _cut_delta(progress, _cuts(patch))))
    if body > POLE_TOL:
        errors.append("the corner did not come back to the geometry it was "
                      "built at (%.3e mm)" % body)
    return {"pass": not errors, "errors": errors, "checks": checks}


# ---------------------------------------------------------------------------
# 4. setback fixed: a band edge is NEVER written -- 0.00e+00
# ---------------------------------------------------------------------------

def test_fixed_setback_mode_never_writes_a_band_edge(doc):
    """The default, and the one #64 paid for: a band edge is the user's own
    width.  With `SetbackMode = "fixed"` the corner writes NO band edge --
    on the carrying patch, on the other ring patches, or after the cut
    follows.  Every cut property on every ring patch is compared before and
    after two edits; the only band edges that move are the ones the test
    itself typed."""
    errors, checks = [], []
    strips, corner = _build(doc)
    patch = _member_patch(corner, strips)
    patches = [doc.getObject(n) for n in PATCH_NAMES]
    before = {p.Name: _cuts(p) for p in patches}
    typed = []
    prop, cur, moved = _setback_write(patch, strips)
    typed.append((patch.Name, prop, moved))
    setattr(patch, prop, moved)
    doc.recompute()
    # a SECOND edit, on a patch that does not carry the triangle: the whole
    # ring moves, so a corner that wrote band edges would show it here
    other = [p for p in patches if p.Name != patch.Name][0]
    oprop, _ocur, omoved = _setback_write(other, strips)
    typed.append((other.Name, oprop, omoved))
    setattr(other, oprop, omoved)
    doc.recompute()
    after = {p.Name: _cuts(p) for p in patches}
    written = []
    for name, cuts_after in after.items():
        for letter in ("U", "V"):
            for i, (a, b) in enumerate(zip(before[name][letter],
                                          cuts_after[letter])):
                if abs(float(a) - float(b)) <= 0.0:
                    continue
                if i < 2:
                    prop_name = "%s.%sSplit%d" % (name, letter, i + 1)
                else:
                    prop_name = "%s.%sLeader%d" % (name, letter, i - 1)
                written.append((prop_name, float(a), float(b)))
    checks.append("SetbackMode fixed: two edits made, %d cut propert(ies) "
                  "moved on the ring: %s"
                  % (len(written),
                     [(n, round(a, 9), round(b, 9)) for n, a, b in written]))
    allowed = {("%s.%s" % (name, p)): value for name, p, value in typed}
    for prop_name, was, now in written:
        if not prop_name.endswith(("USplit1", "USplit2", "VSplit1",
                                   "VSplit2")):
            continue                     # leader cuts are the CUT's business
        if prop_name not in allowed or abs(now - allowed[prop_name]) > 1e-12:
            errors.append("SetbackMode fixed WROTE a band edge: %s %g -> %g"
                          % (prop_name, was, now))
    leaders = _leader_params(patch)
    checks.append("the cut followed instead (leader cuts %s), so the corner is "
                  "not simply inert" %
                  {k: round(v, 6) for k, v in leaders.items()})
    if all(abs(v - 0.0) < 1e-12 or abs(v - 1.0) < 1e-12
           for v in leaders.values()):
        errors.append("no leader cut was placed at all: %s" % (leaders,))
    return {"pass": not errors, "errors": errors, "checks": checks}


# ---------------------------------------------------------------------------
# 5. no feedback loop: a settled document stays settled, in every mode
# ---------------------------------------------------------------------------

def test_a_following_corner_settles(doc):
    """The #125 bar, in both mode pairs that WRITE (the pair that writes
    nothing is `test_fixed_mode_keeps_the_stored_cut`'s subject) and AFTER an
    edit: three `doc.recompute()` passes cost ~0 s each, nothing is left
    Touched, and the corner's 36 poles do not move across them (0.000e+00).

    That is the proof that re-deriving a cut, which WRITES a patch property
    from inside the corner's own execute, is a fixed point rather than a
    loop: the second pass finds the value the first one wrote, writes
    nothing, and the framework's own iteration stops."""
    errors, checks = [], []
    for leader, setback in ((LEADER_MODE_AUTO, SETBACK_MODE_FIXED),
                            (LEADER_MODE_AUTO, SETBACK_MODE_AUTO)):
        strips, corner = _build(doc)
        patch = _member_patch(corner, strips)
        set_follow_modes(corner, leader=leader, setback=setback)
        doc.recompute()
        prop, _cur, moved = _setback_write(patch, strips)
        setattr(patch, prop, moved)
        doc.recompute()
        poles = [tuple(p) for p in corner.Poles]
        times = []
        for _ in range(3):
            started = time.time()
            doc.recompute()
            times.append(time.time() - started)
        left = [o.Name for o in doc.Objects if "Touched" in o.State]
        moved_mm = _pole_move(poles, [tuple(p) for p in corner.Poles])
        checks.append("leader %s / setback %s: recomputes %.4f/%.4f/%.4f s, "
                      "still touched %s, poles moved %.3e mm"
                      % (leader, setback, times[0], times[1], times[2],
                         left or "none", moved_mm))
        if left:
            errors.append("leader %s / setback %s: the document never settles "
                          "-- %s stay(s) Touched"
                          % (leader, setback, left))
        if max(times) > SETTLE_SECONDS:
            errors.append("leader %s / setback %s: a settled recompute cost "
                          "%.4f s (bar %.2f s)"
                          % (leader, setback, max(times), SETTLE_SECONDS))
        if moved_mm != 0.0:
            errors.append("leader %s / setback %s: the corner still moves on "
                          "a settled document (%.3e mm) -- a feedback loop"
                          % (leader, setback, moved_mm))
        members = [o for o in doc.Objects
                   if getattr(o, "object_type", "") == "RollingMemberFace"]
        if not members or not members[0].Shape or not members[0].Shape.Faces:
            errors.append("leader %s / setback %s: the triangular member has "
                          "no face after the settle" % (leader, setback))
        # each pair is its own build
        for name in [o.Name for o in doc.Objects]:
            try:
                doc.removeObject(name)
            except Exception:
                pass
        doc.recompute()
    return {"pass": not errors, "errors": errors, "checks": checks}


# ---------------------------------------------------------------------------
# 6. the shipped construction is never rewritten
# ---------------------------------------------------------------------------

def test_the_shipped_construction_is_never_followed(doc):
    """`Construction = "shipped"` has no triangular member and cuts with the
    BAND EDGE, so "following" there would mean rewriting the user's setback.
    The follower must not touch it: the four leader cuts stay at their
    sentinels, the band edges only move where the test typed, and the reason
    is reported rather than silent."""
    errors, checks = [], []
    strips, corner = _build(doc, construction=CORNER_CONSTRUCTION_SHIPPED)
    built, _note = corner_construction(corner)
    checks.append("built construction %r" % (built,))
    if built != CORNER_CONSTRUCTION_SHIPPED:
        return {"pass": False,
                "errors": ["the shipped construction was not built (%r)"
                           % (built,)],
                "checks": checks}
    patches = [doc.getObject(n) for n in PATCH_NAMES]
    before = {p.Name: _cuts(p) for p in patches}
    leaders_before = {p.Name: _leader_params(p) for p in patches}
    for p in patches:
        prop, _cur, moved = _setback_write(p, strips)
        setattr(p, prop, moved)
        doc.recompute()
    after = {p.Name: _cuts(p) for p in patches}
    leaders_after = {p.Name: _leader_params(p) for p in patches}
    leader_move = max(abs(leaders_before[n][k] - leaders_after[n][k])
                      for n in leaders_before for k in leaders_before[n])
    checks.append("shipped corner after three band-edge edits: leader cuts "
                  "moved by %.3e, reported %r"
                  % (leader_move, corner.Proxy._follow_report))
    if leader_move != 0.0:
        errors.append("the follower wrote a leader cut on a SHIPPED corner "
                      "(%.3e)" % leader_move)
    report = getattr(corner.Proxy, "_follow_report", None) or {}
    note = report.get("note") or ""
    if "shipped" not in note:
        errors.append("the shipped corner does not report why it does not "
                      "follow: %r" % (note,))
    band_moves = 0
    for name in before:
        band_moves += sum(1 for letter in ("U", "V")
                          for a, b in zip(before[name][letter][:2],
                                          after[name][letter][:2])
                          if abs(float(a) - float(b)) > 0.0)
    checks.append("band edges moved: %d (one per edit on the patch typed on)"
                  % band_moves)
    if band_moves != 3:
        errors.append("the band edges moved %d times, and the test typed on "
                      "three patches once each" % band_moves)
    return {"pass": not errors, "errors": errors, "checks": checks}


# ---------------------------------------------------------------------------
# 7. no fold, no coincident poles -- the change cannot hide a regression
# ---------------------------------------------------------------------------

def test_the_followed_corner_is_still_fold_free(doc):
    """The readings the corner is already pinned on, re-taken AFTER the cut
    has been re-derived: 0 coincident pole pairs on the 6x6, 0/0/0 normal-field
    flips at n = 39/81/150 across the fold, and a triangular member with one
    face.  A change that made the cut follow must not quietly fold the cap."""
    import SilkChecks
    errors, checks = [], []
    strips, corner = _build(doc)
    patch = _member_patch(corner, strips)
    prop, _cur, moved = _setback_write(patch, strips)
    setattr(patch, prop, moved)
    doc.recompute()
    poles = list(corner.Poles)
    coins = _coins(poles)
    flips = [len(SilkChecks._normal_field_flips(
        corner.Shape.Faces[0].Surface, n=n)[0]) for n in (39, 81, 150)]
    members = [o for o in doc.Objects
               if getattr(o, "object_type", "") == "RollingMemberFace"]
    tri_faces = len(members[0].Shape.Faces) if members and members[0].Shape \
        else 0
    checks.append("after the follow: %d/630 coincident pole pairs, "
                  "normal-field flips n=39/81/150 %r, %d pole(s), tri %d "
                  "face(s)" % (coins, flips, len(poles), tri_faces))
    if len(poles) != 36:
        errors.append("the followed corner is not a 6x6: %d poles" % len(poles))
    if coins:
        errors.append("%d coincident pole pairs after the follow" % coins)
    if any(flips):
        errors.append("the followed corner folds: %r flips at n=39/81/150"
                      % (flips,))
    if tri_faces < 1:
        errors.append("the triangular member has no face after the follow")
    return {"pass": not errors, "errors": errors, "checks": checks}


# ---------------------------------------------------------------------------
# 8. the panel: both selectors, driven, and the corner obeys
# ---------------------------------------------------------------------------

def _panel_band_editor(panel, patch, prop):
    """`(spin, value)` for the panel's OWN band-edge editor of `patch.prop`.

    The setback is edited through the panel here, not by writing the property:
    `refresh()` commits an editor whose value DISAGREES with its patch
    (`_commit_in_flight_edits`, #71), so a property written behind the panel's
    back is put back to the value the editor still holds.  That is the panel
    being right -- a typed width is not silently dropped -- and it is why this
    test types where a user types.
    """
    from SilkTaskPanel import BAND_A, BAND_B, band_side, read_band_split
    for edge_name, spins in (panel._split_widgets or {}).items():
        meta = (panel._split_meta or {}).get(edge_name) or {}
        for which in (BAND_A, BAND_B):
            entry = meta.get(which)
            if entry is None or spins.get(which) is None:
                continue
            read = read_band_split(entry)
            if read is None:
                continue
            seen_patch, seen_prop, _ss, value = band_side(entry, which, read)
            if seen_patch is patch and seen_prop == prop:
                return spins[which], value
    return None, None


def test_the_panel_flips_each_mode_and_the_corner_obeys(doc):
    """The real panel, not the properties: the corner page's two selectors are
    mounted on a BUILT corner, they show the modes in force, and flipping them
    makes the corner obey AT ONCE -- the numbers, not the widgets:

      * `Cut: fixed` -- a band-edge edit moves the band and NOT the cut;
      * `Cut: auto`  -- the same edit, and the cut is re-derived, the two
                        sides equal;
      * `Setback: auto` -- the band edge is placed back where the triangle is
                        the size it was built at."""
    from Tests.test_task_panel import _open_panel, _close_panel, _click
    import SilkTaskPanel as TP

    errors, checks = [], []
    strips, corner = _build(doc)
    patch = _member_patch(corner, strips)
    built_sides = _sides(strips, patch)
    poles_at_build = [tuple(p) for p in corner.Poles]
    panel = _open_panel(doc)
    try:
        panel.sections.open(TP.SECTION_CORNER)
        for s in strips:
            _click(s)
        offers = [panel.corner_leader_mode.itemText(i) for i in
                  range(panel.corner_leader_mode.count())]
        sets = [panel.corner_setback_mode.itemText(i) for i in
                range(panel.corner_setback_mode.count())]
        checks.append("the page offers cut %s / setback %s and reads %r"
                      % (offers, sets, panel.corner_follow_choices()))
        if offers != list(("auto", "fixed")) or sets != ["fixed", "auto"]:
            errors.append("the selectors do not offer both modes each: %s / %s"
                          % (offers, sets))
        if panel.corner_follow_choices() != (LEADER_MODE_AUTO,
                                            SETBACK_MODE_FIXED):
            errors.append("an untouched page does not read the modes the "
                          "corner carries: %r"
                          % (panel.corner_follow_choices(),))
        say = panel.corner_follow_lbl.text()
        checks.append("the page says which mode is in force: %r" % (say,))
        if LEADER_MODE_AUTO not in say or SETBACK_MODE_FIXED not in say:
            errors.append("the page does not say which mode is in force: %r"
                          % (say,))

        # (1) cut: fixed -- the stored cut is kept across a band-edge edit
        # made in the panel's OWN setback editor (see `_panel_band_editor`)
        panel.corner_leader_mode.setCurrentIndex(
            panel.corner_leader_mode.findText(LEADER_MODE_FIXED))
        prop, cur, moved = _setback_write(patch, strips)
        spin, seeded = _panel_band_editor(panel, patch, prop)
        checks.append("the panel's own editor for %s.%s is %r and seeds %r"
                      % (patch.Name, prop, spin is not None, seeded))
        if spin is None:
            return {"pass": False,
                    "errors": ["the panel mounts no band-edge editor for "
                               "%s.%s -- the setback cannot be edited where "
                               "a user edits it" % (patch.Name, prop)],
                    "checks": checks}
        spin.setValue(moved)
        panel.refresh()             # commits the typed width (its own path)
        doc.recompute()
        fixed_sides = _sides(strips, patch)
        checks.append("Cut: fixed, %s.%s %g -> %g: sides %s"
                      % (patch.Name, prop, cur, moved,
                         {k: round(v, 9) for k, v in fixed_sides.items()}))
        if abs(fixed_sides[list(fixed_sides)[0]]
               - built_sides[list(built_sides)[0]]) <= 1e-9:
            errors.append("with Cut: fixed the triangle still moved its own "
                          "side -- the mode was not obeyed")

        # (2) cut: auto -- the same edit re-derives the cut, equal sides
        panel.corner_leader_mode.setCurrentIndex(
            panel.corner_leader_mode.findText(LEADER_MODE_AUTO))
        auto_sides = _sides(strips, patch)
        values = [v for v in auto_sides.values() if v is not None]
        checks.append("Cut: auto (flipped on the same edit): sides %s"
                      % {k: round(v, 9) for k, v in auto_sides.items()})
        if len(values) != 2 or abs(values[0] - values[1]) > CUT_LENGTH_TOL:
            errors.append("with Cut: auto the triangle is not equal-sided: %s"
                          % (auto_sides,))

        # (3) setback: auto -- the band edge and the cut side are put back
        # where the corner placed them
        panel.corner_setback_mode.setCurrentIndex(
            panel.corner_setback_mode.findText(SETBACK_MODE_AUTO))
        placed = float(getattr(patch, prop))
        checks.append("Setback: auto: %s.%s reads %.17g (the user wrote %g, "
                      "the build had %g); sides %s"
                      % (patch.Name, prop, placed, moved, cur,
                         {k: round(v, 9)
                          for k, v in _sides(strips, patch).items()}))
        if abs(placed - cur) > 1e-9:
            errors.append("Setback: auto did not place the band edge back: %g "
                          "vs the build's %g" % (placed, cur))
        back = _pole_move(poles_at_build, [tuple(p) for p in corner.Poles])
        checks.append("the corner is back at its built geometry to %.3e mm"
                      % back)
        if back > POLE_TOL:
            errors.append("Setback: auto left the corner %.3e mm away from "
                          "its built geometry" % back)
        if "auto" not in panel.corner_follow_lbl.text():
            errors.append("the page does not say the setback mode is in "
                          "force: %r" % (panel.corner_follow_lbl.text(),))
    finally:
        _close_panel(panel)
    return {"pass": not errors, "errors": errors, "checks": checks}
