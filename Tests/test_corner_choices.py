"""The corner stage's OWNER CHOICES, measured (#117 / #119 follow-up / #128).

The corner stage used to decide things on the owner's behalf and give him no
way to say otherwise, and the owner's own complaint was: *"why can i
implement a 3 sided corner, but not select to be rolling immediately?"*

  * WHICH CONSTRUCTION it builds -- the rolling one (the 66 over the member
    patch's cut cell plus the small triangular surface beside it, the
    maintainer's two-patch corner) or the shipped one (the 66 with the
    spiderweb member).  Both are reachable from the ops layer
    (`create_corner_blend(construction=...)`) and from the panel's selector,
    the rolling one is the default, and WHICH ONE WAS BUILT is recorded on
    the corner (`Construction`) so a fallback cannot pass for the real thing.
  * WHICH patch of the ring carries the small triangular surface (the
    triangular 4th member). `MemberPatch` / `MemberCorner` exist (#117), but
    they were only written on the SHIPPED construction's corner -- the
    rolling construction handed its resolved pin to the cutting step and
    never wrote it onto the corner it built, so the corner's own `execute()`
    re-derived the member with the automatic search and the 66 and the tri
    could disagree about where the member is.
  * HOW FAR ALONG each seam the band is cut back -- the rolling leader --
    per SEAM. `create_corner_blend(leaders={...})` carries one value per
    seam, and the panel mounts one editor per seam of the ring, so the choice
    reaches every patch of the ring rather than only the one the stage picked.
    The leader is the MEMBER PATCH's own cut (`ULeader1/2`, `VLeader1/2`),
    the band edge staying the setback (#128).

WHAT IS MEASURED HERE, on the cube-corner fixture
(`Tests/cube_corner_model.py`, three exact planar squares meeting at one
corner). Two tables, because the fixture is SYMMETRIC and one table cannot
say both things:

  (A) ONE leader for every seam -- the stage's own default. The tri's area
      follows the leader and nothing else, and the member's PLACEMENT
      follows the patch:

        member on   leader 0.25            leader 0.50            bbox max (l=0.25)
        PatchA[0]     0.020609              0.146550             (0.25, 0.25, 0)
        PatchB[0]     0.020609              0.146550             (0, 0.25, 0.25)
        PatchC[0]     0.020609              0.146550             (0.25, 0, 0.25)

      The area is the cell BETWEEN the 0.1 setback and the leader, so it is
      `(leader - 0.1)^2`-shaped: 0.15^2 = 0.0225 at 0.25 and 0.4^2 = 0.16 at
      0.5, less the bilinear corner cut.  The three areas are EQUAL at one
      leader -- the three cells are the same square on three planes, which is
      the fixture's symmetry, not a pin that failed to move (the placements
      differ, which is what the pin moves).

  (B) ONE LEADER PER SEAM, i.e. an asymmetric roll. Now the three cells are
      three different rectangles, and the area follows the member patch too:

        member on   {B_AB:.5, B_BC:.25, B_CA:.2}   {B_AB:.9, B_BC:.5, B_CA:.3}
        PatchA[0]            0.036637                      0.146550
        PatchB[0]            0.054956                      0.293099
        PatchC[0]            0.013739                      0.073275

      Every cell of (B) differs from its neighbours, so "the owner can choose
      which patch carries the tri" is measured on the geometry, not on a
      property write.

      EVERY LEADER THAT CUTS THE MEMBER PATCH MUST CLEAR THE SETBACK.  The
      cell between the setback and the leader is the member's own cell, on
      BOTH of the patch's axes; a leader resting on the 0.1 band edge is
      inert (`SilkMachinery.axis_cuts`), the cell on that axis stays the
      band's, and the assembly either refuses or comes out with 4 coincident
      pole pairs.  The stage now refuses that BY NAME instead ("the rolling
      leader cannot cut the member's cell: its V axis carries no leader cut
      that clears the setback"), and the fallback is the shipped corner.

Also pinned: the tri's face is a `CubicSurface_64` by DEFAULT (the
construction the maintainer's own files store) and the FreeCAD fill is the
selectable option; an unknown face is refused before anything is built.
"""

# --- manual tier ------------------------------------------------------
# This module's subject is an end-to-end rebuild / measurement sweep, so it
# is NOT in the default (fast) tier. Run it with `python3 Tests/run_all.py
# --manual` (or by name as a filter); `Tests/test_manual_tier.py` asserts it
# stays importable. See suite.py.
MANUAL = True

import FreeCAD

from SilkWorkflowOps import (create_corner_blend, apply_corner_choices,
                             MEMBER_FACE_FILL)

STRIP_NAMES = ("B_AB", "B_BC", "B_CA")
PATCH_NAMES = ("PatchA", "PatchB", "PatchC")
SCRATCH = "_corner_choices"


class _CaptureConsole:
    def __enter__(self):
        self._orig_error = FreeCAD.Console.PrintError
        self._orig_message = FreeCAD.Console.PrintMessage
        self.errors, self.messages = [], []
        FreeCAD.Console.PrintError = lambda m: (self.errors.append(m),
                                                self._orig_error(m))
        FreeCAD.Console.PrintMessage = lambda m: (self.messages.append(m),
                                                  self._orig_message(m))
        return self

    def __exit__(self, *args):
        FreeCAD.Console.PrintError = self._orig_error
        FreeCAD.Console.PrintMessage = self._orig_message


def _member(doc):
    for o in doc.Objects:
        if getattr(o, "object_type", "") == "RollingMemberFace":
            return o
    return None


def _fills(doc):
    return [o for o in doc.Objects
            if getattr(o, "TypeId", "") == "Surface::Filling"]


def _corner_in_scratch(**kw):
    """Build the cube corner + its corner in a SCRATCH document and report.

    A fresh document per build is what makes each row of the measurement a
    corner of its own: the fixture's patches, the cut band edges and the
    member's cell only exist once each, so nothing from a previous row can
    leak into the next one. The scratch document is closed before returning,
    so a failure inside it cannot leave the caller's document dirty.

    Keys: 'corner' (True when one was built, None otherwise), 'errors' (the
    console's), 'member' (the member's NAME -- the document is closed before
    this returns, so no object may escape), 'member_patch', 'member_corner',
    'area', 'faces', 'visible', 'fills'."""
    from Tests.cube_corner_model import build_cube_corner_model
    if SCRATCH in FreeCAD.listDocuments():
        FreeCAD.closeDocument(SCRATCH)
    doc = FreeCAD.newDocument(SCRATCH)
    out = {"corner": None, "errors": [], "member": None, "area": None,
           "member_patch": None, "member_corner": None, "faces": None,
           "visible": None, "fills": [], "bbox_max": None}
    try:
        FreeCAD.setActiveDocument(doc.Name)
        build_cube_corner_model(doc)
        strips = [doc.getObject(n) for n in STRIP_NAMES]
        pin = kw.pop("pin_name", None)
        if pin is not None:
            kw["pin"] = (doc.getObject(pin), kw.get("pin_corner", 0))
        with _CaptureConsole() as cap:
            corner = create_corner_blend(*strips, **kw)
        out["errors"] = list(cap.errors)
        rebuild = doc.getObject("CornerBlend")
        out["corner"] = corner
        if corner is not None:
            out["member_patch"] = getattr(
                (rebuild or corner).MemberPatch, "Name", None)
            out["member_corner"] = int(
                getattr((rebuild or corner), "MemberCorner", 0))
        member = _member(doc)
        if member is not None:
            out["member"] = member.Name
            if member.Shape and member.Shape.Faces:
                out["area"] = member.Shape.Area
                out["faces"] = len(member.Shape.Faces)
                bb = member.Shape.BoundBox
                out["bbox_max"] = (round(bb.XMax, 6), round(bb.YMax, 6),
                                   round(bb.ZMax, 6))
            try:
                out["visible"] = bool(member.ViewObject.Visibility)
            except Exception:
                out["visible"] = None
        out["fills"] = [o.Name for o in _fills(doc)]
        return out
    finally:
        if SCRATCH in FreeCAD.listDocuments():
            FreeCAD.closeDocument(SCRATCH)


def test_the_rolling_corner_honours_the_member_pin(doc):
    """#117 ON THE ROLLING PATH: the pin reaches the corner the rolling
    construction BUILDS, not only the step that cuts the band.

    Measured per patch: the corner's own `MemberPatch` (what the object
    re-derives from), and the built member's face area (the geometry's own
    answer). A pin that only reached the cutting step would leave
    `MemberPatch` naming the patch the automatic search picked."""
    errors, checks = [], []
    corners = {}
    for name in PATCH_NAMES:
        out = _corner_in_scratch(pin_name=name)
        if out["corner"] is None:
            errors.append("%s[0] refused: %r"
                          % (name, "".join(out["errors"]).strip()))
            continue
        corners[name] = out
        checks.append("%s[0]: MemberPatch=%s[%s], tri area %.6f, %s face(s), "
                      "member bbox max %s"
                      % (name, out["member_patch"], out["member_corner"],
                         out["area"] or 0.0, out["faces"], out["bbox_max"]))
        if out["member_patch"] != name:
            errors.append("%s[0]: the corner stores MemberPatch=%r -- the pin "
                          "did not reach the built corner"
                          % (name, out["member_patch"]))
        if out["area"] is None:
            errors.append("%s[0]: the triangular member has no face" % name)
    places = {n: o["bbox_max"] for n, o in corners.items() if o["bbox_max"]}
    if len(places) == len(PATCH_NAMES):
        if len(set(places.values())) != len(PATCH_NAMES):
            errors.append("the member did not MOVE when the pin moved: it "
                          "sits at %s on every patch" % (places,))
        else:
            checks.append("the member sits on a different plane on each "
                          "patch: %s (its area is the same figure three "
                          "times -- the fixture is symmetric)" % (places,))
    return {"pass": not errors, "errors": errors, "checks": checks}


def test_the_leader_and_the_member_patch_set_the_tri_area(doc):
    """THE OWNER'S OWN TABLE, in its two halves (the module docstring carries
    both):

    (A) one leader for the whole ring -- the area follows the LEADER, and the
        member's placement follows the PATCH (the areas coincide because the
        fixture is symmetric; that is reported, not hidden);
    (B) one leader PER SEAM -- the areas then follow the member patch too, and
        every cell differs from its neighbours."""
    errors, checks = [], []
    single = {}
    for name in PATCH_NAMES:
        for leader in (0.25, 0.5):
            out = _corner_in_scratch(pin_name=name, leader=leader)
            single[(name, leader)] = out["area"]
            checks.append("(A) %s[0] leader %.2f: tri area %s, member bbox "
                          "max %s"
                          % (name, leader,
                             "None" if out["area"] is None
                             else "%.6f" % out["area"], out["bbox_max"]))
            if out["corner"] is None:
                errors.append("(A) %s[0] leader %.2f refused: %r"
                              % (name, leader,
                                 "".join(out["errors"]).strip()))
    if any(v is None for v in single.values()):
        return {"pass": False, "errors": errors, "checks": checks}
    for name in PATCH_NAMES:
        a, b = single[(name, 0.25)], single[(name, 0.5)]
        if abs(a - b) <= 1e-9:
            errors.append("(A) %s: the leader did not move the tri's area "
                          "(%.6f at both 0.25 and 0.5)" % (name, a))
    same_leader = [single[(n, 0.25)] for n in PATCH_NAMES]
    spread = max(same_leader) - min(same_leader)
    checks.append("(A) at ONE leader the three patches read %s (spread "
                  "%.3e): %s"
                  % (["%.6f" % v for v in same_leader], spread,
                     "equal -- the fixture is symmetric, so at one leader the "
                     "pin's effect is the member's PLACEMENT above, not the "
                     "area" if spread <= 1e-9 else "they differ"))

    asymmetric = [{"B_AB": 0.5, "B_BC": 0.25, "B_CA": 0.2},
                  {"B_AB": 0.9, "B_BC": 0.5, "B_CA": 0.3}]
    for leaders in asymmetric:
        got = {}
        for name in PATCH_NAMES:
            out = _corner_in_scratch(pin_name=name, leaders=leaders)
            got[name] = out["area"]
            checks.append("(B) %s[0] %s: tri area %s"
                          % (name, leaders,
                             "None" if out["area"] is None
                             else "%.6f" % out["area"]))
            if out["corner"] is None:
                errors.append("(B) %s[0] %s refused: %r"
                              % (name, leaders,
                                 "".join(out["errors"]).strip()))
        values = [v for v in got.values() if v is not None]
        if len(values) == len(PATCH_NAMES):
            if len(set(round(v, 9) for v in values)) != len(PATCH_NAMES):
                errors.append("(B) %s: moving the member patch did not move "
                              "the tri's area (%s)" % (leaders, got))
            else:
                checks.append("(B) %s: every member patch gives a DIFFERENT "
                              "tri area" % (leaders,))
    return {"pass": not errors, "errors": errors, "checks": checks}


def test_the_tri_is_a_cubic_surface_64_by_default(doc):
    """The member's face is its own `CubicSurface_64` over the member net by
    default -- the construction the maintainer's files store
    (`ControlGrid64_3_Grid44 -> CubicSurface_64`) -- and NO FreeCAD fill is
    built, so the tri on screen is that 64 and nothing else."""
    errors, checks = [], []
    out = _corner_in_scratch()
    if out["corner"] is None:
        return {"pass": False,
                "errors": ["refused: %r" % "".join(out["errors"]).strip()],
                "checks": []}
    checks.append("default: member %s, %s face(s), visible %s, %d "
                  "Surface::Filling in the document"
                  % (out["member"], out["faces"],
                     out["visible"], len(out["fills"])))
    if out["faces"] != 1:
        errors.append("the member does not carry exactly one face (%s)"
                      % (out["faces"],))
    if out["fills"]:
        errors.append("the default build put a Surface::Filling in the tree: "
                      "%s" % (out["fills"],))
    if out["visible"] is False:
        errors.append("the 64 face is hidden and no fill replaces it -- the "
                      "tri would not be visible at all")
    return {"pass": not errors, "errors": errors, "checks": checks}


def test_the_fill_is_still_reachable_as_the_option(doc):
    """Both faces must be reachable: `member_face="fill"` builds the owner's
    FreeCAD `Surface::Filling` over the member's three real edges and hides
    the 64 behind it -- the behaviour of before this change, now selected by
    name instead of being the default. An unknown face is refused before
    anything is built, so it can never fall through to the shipped corner."""
    errors, checks = [], []
    out = _corner_in_scratch(member_face=MEMBER_FACE_FILL)
    if out["corner"] is None:
        return {"pass": False,
                "errors": ["the fill option refused: %r"
                           % "".join(out["errors"]).strip()],
                "checks": []}
    checks.append("member_face=%r: %d Surface::Filling (%s), the 64's face "
                  "visible %s" % (MEMBER_FACE_FILL, len(out["fills"]),
                                  out["fills"], out["visible"]))
    if len(out["fills"]) != 1:
        errors.append("expected exactly one fill, got %d" % len(out["fills"]))
    if out["visible"]:
        errors.append("the 64 face and the fill are both visible")
    bad = _corner_in_scratch(member_face="surface66")
    if bad["corner"] is not None:
        errors.append("an unknown member_face built a corner")
    elif not any("member's face must be" in m for m in bad["errors"]):
        errors.append("an unknown member_face was not refused by name: %r"
                      % (bad["errors"],))
    else:
        checks.append("an unknown member_face is refused by name and builds "
                      "nothing")
    return {"pass": not errors, "errors": errors, "checks": checks}


def test_apply_writes_the_choices_onto_an_existing_corner(doc):
    """`apply_corner_choices` (the panel's Apply) moves the member and the
    per-seam leaders of a corner that already exists, and refuses by name
    when the ring has no corner yet -- so it can never become a second
    creation path."""
    from Tests.cube_corner_model import build_cube_corner_model
    errors, checks = [], []
    build_cube_corner_model(doc)
    strips = [doc.getObject(n) for n in STRIP_NAMES]
    base = create_corner_blend(*strips)
    if base is None:
        return {"pass": False, "errors": ["no corner built"], "checks": []}
    before = _member(doc)
    before_area = (before.Shape.Area if before is not None and before.Shape
                   and before.Shape.Faces else None)
    with _CaptureConsole() as cap:
        same, why = apply_corner_choices(
            strips, pin=(doc.getObject("PatchB"), 0),
            leaders={"B_AB": 0.5, "B_BC": 0.25, "B_CA": 0.25})
    if same is None:
        return {"pass": False,
                "errors": ["apply refused: %r"
                           % "".join(cap.errors).strip()],
                "checks": []}
    after = _member(doc)
    after_area = (after.Shape.Area if after is not None and after.Shape
                  and after.Shape.Faces else None)
    checks.append("apply: MemberPatch=%s, tri area %.6f -> %s"
                  % (getattr(same.MemberPatch, "Name", None), before_area or 0.0,
                     "None" if after_area is None else "%.6f" % after_area))
    if getattr(same.MemberPatch, "Name", None) != "PatchB":
        errors.append("apply did not move the member (MemberPatch=%r)"
                      % (getattr(same.MemberPatch, "Name", None),))
    if (before_area is None or after_area is None
            or abs(after_area - before_area) <= 1e-9):
        errors.append("apply did not move the tri's face (%r -> %r)"
                      % (before_area, after_area))
    # a ring with no corner: refused by name, nothing created
    foreign = FreeCAD.newDocument("_apply_refusal")
    try:
        FreeCAD.setActiveDocument(foreign.Name)
        build_cube_corner_model(foreign)
        made, why = apply_corner_choices(
            [foreign.getObject(n) for n in STRIP_NAMES],
            pin=(foreign.getObject("PatchB"), 0))
        if made is not None:
            errors.append("apply built a corner on a ring that had none")
        elif not why or "no corner yet" not in why:
            errors.append("apply refused without naming why: %r" % (why,))
        else:
            checks.append("a ring with no corner is refused by name: %s" % why)
    finally:
        FreeCAD.closeDocument(foreign.Name)
        if doc.Name in FreeCAD.listDocuments():
            FreeCAD.setActiveDocument(doc.Name)

    # a leader that cannot cut the member's cell is refused ATOMICALLY: the
    # rolling corner follows that cut, so Apply must not be a way around the
    # condition the corner stage refuses on
    from SilkMachinery import leader_pair
    before = {n: leader_pair(doc.getObject(n), "U")
              for n in PATCH_NAMES}
    blocked, why = apply_corner_choices(
        strips, leaders={"B_AB": 0.1, "B_BC": 0.25, "B_CA": 0.25})
    after = {n: leader_pair(doc.getObject(n), "U") for n in PATCH_NAMES}
    checks.append("an inert leader on the member patch: %r -> %r; the cuts "
                  "are unchanged: %s"
                  % (blocked, (why or "")[:110], before == after))
    if blocked is not None:
        errors.append("Apply accepted a leader that cannot cut the member's "
                      "cell")
    elif not why or "cannot cut the member's cell" not in why:
        errors.append("the refusal does not reuse the component's wording: %r"
                      % (why,))
    if before != after:
        errors.append("a refused Apply wrote a cut anyway: %s -> %s"
                      % (before, after))
    return {"pass": not errors, "errors": errors, "checks": checks}


def test_the_panel_exposes_the_member_pin_and_a_leader_per_seam(doc):
    """THE OWNER'S REACHABILITY REQUIREMENT, driven through the real panel.

    On the corner page's collected ring the panel must offer
      * the member's PLACEMENT -- a patch combo holding the ring's three
        patches (plus "(automatic)"), and the corner index, and
      * the LEADER OF EVERY SEAM -- one editable row per seam, which is what
        puts the choice on every patch of the ring rather than on one.
    Confirming writes both onto the corner the stage builds, and the Apply
    button writes them onto a corner that already exists. Both are measured
    by the tri's own face area, so "the control moved" is not the claim."""
    from Tests.test_task_panel import _open_panel, _close_panel, _click
    import SilkTaskPanel as TP
    from Tests.cube_corner_model import build_cube_corner_model

    errors, checks = [], []
    build_cube_corner_model(doc)
    strips = [doc.getObject(n) for n in STRIP_NAMES]
    panel = _open_panel(doc)
    try:
        panel.sections.open(TP.SECTION_CORNER)
        for s in strips:
            _click(s)
        collected = panel.collected(TP.SECTION_CORNER)
        entries = [panel.corner_member_patch.itemText(i)
                   for i in range(panel.corner_member_patch.count())]
        rows = panel.corner_leader_table.rowCount()
        spins = dict(panel._corner_leader_spins)
        checks.append("collected %d strips; member combo %s; %d leader row(s) "
                      "for seams %s, seeded %s"
                      % (len(collected), entries, rows,
                         sorted(spins),
                         ["%.3f" % s.value() for s in spins.values()]))
        if len(collected) != 3:
            errors.append("the corner section collected %d of 3 strips"
                          % len(collected))
        if entries[:1] != [TP.CORNER_MEMBER_AUTO] or sorted(entries[1:]) != sorted(
                PATCH_NAMES):
            errors.append("the member combo does not name the ring's patches: "
                          "%s" % (entries,))
        if rows != len(STRIP_NAMES) or sorted(spins) != sorted(STRIP_NAMES):
            errors.append("the leader table has %d row(s) for %d seam(s)"
                          % (rows, len(STRIP_NAMES)))

        # (1) confirm WITH the choices: the member on PatchB, B_AB rolled 0.5
        panel.corner_member_patch.setCurrentIndex(
            panel.corner_member_patch.findText("PatchB"))
        spins["B_AB"].setValue(0.5)
        built = panel.panel_confirm()
        corner = doc.getObject("CornerBlend")
        area_confirmed = None
        where = None
        member = _member(doc)
        if member is not None and member.Shape and member.Shape.Faces:
            area_confirmed = member.Shape.Area
            bb = member.Shape.BoundBox
            where = (round(bb.XMax, 4), round(bb.YMax, 4), round(bb.ZMax, 4))
        checks.append("confirm: built=%s, MemberPatch=%s, tri area %s"
                      % (built, getattr(corner.MemberPatch, "Name", None)
                         if corner is not None else None,
                         "None" if area_confirmed is None
                         else "%.6f" % area_confirmed))
        if corner is None:
            errors.append("confirm built no corner")
        elif getattr(corner.MemberPatch, "Name", None) != "PatchB":
            errors.append("the panel's member choice did not reach the corner "
                          "(MemberPatch=%r)"
                          % (getattr(corner.MemberPatch, "Name", None),))

        # (2) Apply onto the EXISTING corner MOVES the member: the panel's
        # choice must reach the object, and the member's own placement is the
        # evidence (its face area is the same figure on this symmetric
        # fixture, so the area cannot be the instrument here).
        panel.sections.open(TP.SECTION_CORNER)
        for s in strips:
            _click(s)
        panel.corner_member_patch.setCurrentIndex(
            panel.corner_member_patch.findText("PatchC"))
        applied = panel.on_apply_corner_choices()
        corner2 = doc.getObject("CornerBlend")
        member2 = _member(doc)
        where2 = None
        if member2 is not None and member2.Shape and member2.Shape.Faces:
            bb = member2.Shape.BoundBox
            where2 = (round(bb.XMax, 4), round(bb.YMax, 4), round(bb.ZMax, 4))
        checks.append("apply: %s, MemberPatch=%s, member bbox max %s -> %s"
                      % (applied, getattr(corner2.MemberPatch, "Name", None),
                         where, where2))
        if not applied:
            errors.append("Apply did not report success: %r"
                          % panel.status_text())
        if getattr(corner2.MemberPatch, "Name", None) != "PatchC":
            errors.append("Apply did not move the member (MemberPatch=%r)"
                          % (getattr(corner2.MemberPatch, "Name", None),))
        if where is None or where2 is None or where == where2:
            errors.append("the member did not move between the two patches "
                          "(%r -> %r)" % (where, where2))
    finally:
        _close_panel(panel)
        if doc.Name in FreeCAD.listDocuments():
            FreeCAD.setActiveDocument(doc.Name)
    return {"pass": not errors, "errors": errors, "checks": checks}


def test_the_panel_offers_the_construction_and_shows_the_refusal(doc):
    """THE OWNER'S OWN COMPLAINT (#128): *"why can i implement a 3 sided
    corner, but not select to be rolling immediately?"*

    Three things the panel must do, each measured on the real panel:

      * offer the CONSTRUCTION, defaulting to the rolling one, while the ring
        has no corner yet;
      * build what was chosen, and RECORD it on the object (`Construction`);
      * say WHICH construction was built when the chosen one was refused --
        the corner stage falls back to the shipped one, and until #128 that
        fallback lived on the console only, so the panel said "corner
        created" and the user got the other construction.

    The refusal is produced the honest way: a leader that rests on the
    patch's own 0.1 setback cannot cut the member's cell back, so the rolling
    construction refuses by name and the fallback builds.
    """
    from Tests.test_task_panel import _open_panel, _close_panel, _click
    import SilkTaskPanel as TP
    from Tests.cube_corner_model import build_cube_corner_model
    from SilkCorner import corner_construction

    errors, checks = [], []
    build_cube_corner_model(doc)
    strips = [doc.getObject(n) for n in STRIP_NAMES]
    panel = _open_panel(doc)
    try:
        panel.sections.open(TP.SECTION_CORNER)
        for s in strips:
            _click(s)
        combo = panel.corner_construction
        choices = [combo.itemText(i) for i in range(combo.count())]
        checks.append("the construction selector: %s, showing %r, enabled %s"
                      % (choices, combo.currentText(), combo.isEnabled()))
        if sorted(choices) != sorted(["rolling", "shipped"]):
            errors.append("the selector does not offer both constructions: %s"
                          % (choices,))
        if combo.currentText() != TP.CORNER_CONSTRUCTION_DEFAULT:
            errors.append("the selector does not default to the stage's "
                          "default (%r), it shows %r"
                          % (TP.CORNER_CONSTRUCTION_DEFAULT,
                             combo.currentText()))
        if not combo.isEnabled():
            errors.append("the selector is disabled while the ring has no "
                          "corner -- the construction can never be chosen")

        # (1) the default build: rolling, said so on the status line
        built = panel.panel_confirm()
        corner = doc.getObject("CornerBlend")
        construction, _note = (corner_construction(corner)
                               if corner is not None else (None, None))
        checks.append("confirm (default): built=%s, construction=%r, status %r"
                      % (built, construction, panel.status_text()))
        if corner is None:
            errors.append("the default confirm built no corner")
        elif construction != "rolling":
            errors.append("the default confirm built the %r construction"
                          % (construction,))
        if "rolling" not in panel.status_text():
            errors.append("the status line does not name the construction "
                          "that was built: %r" % panel.status_text())
        if combo.isEnabled():
            errors.append("the selector stayed editable after the corner was "
                          "built -- the construction is a build choice")
    finally:
        _close_panel(panel)
        if doc.Name in FreeCAD.listDocuments():
            FreeCAD.setActiveDocument(doc.Name)

    # (2) a REFUSED rolling corner: the panel names the refusal and the
    # construction that was built instead
    sdoc = FreeCAD.newDocument("_corner_refusal")
    panel2 = None
    try:
        FreeCAD.setActiveDocument(sdoc.Name)
        build_cube_corner_model(sdoc)
        sstrips = [sdoc.getObject(n) for n in STRIP_NAMES]
        panel2 = _open_panel(sdoc)
        panel2.sections.open(TP.SECTION_CORNER)
        for s in sstrips:
            _click(s)
        # a leader that rests on the setback cannot cut the member's cell
        for spin in panel2._corner_leader_spins.values():
            spin.setValue(0.1)
        built = panel2.panel_confirm()
        corner = sdoc.getObject("CornerBlend")
        construction, _note = (corner_construction(corner)
                               if corner is not None else (None, None))
        status = panel2.status_text()
        checks.append("a refused rolling corner: built=%s, construction=%r, "
                      "status %r" % (built, construction, status))
        if corner is None:
            errors.append("a refused rolling corner built nothing at all")
        else:
            if construction != "shipped":
                errors.append("the refused rolling corner did not fall back "
                              "to the shipped one (%r)" % (construction,))
            if "shipped" not in status:
                errors.append("the status line does not say which "
                              "construction was built: %r" % status)
            if "refused" not in status:
                errors.append("the status line does not name the refusal: %r"
                              % status)
            word = "the rolling leader cannot cut the member's cell"
            if word not in status:
                errors.append("the status line does not reuse the component's "
                              "own refusal wording (%r missing): %r"
                              % (word, status))
    finally:
        if panel2 is not None:
            _close_panel(panel2)
        if sdoc.Name in FreeCAD.listDocuments():
            FreeCAD.closeDocument(sdoc.Name)
        if doc.Name in FreeCAD.listDocuments():
            FreeCAD.setActiveDocument(doc.Name)
    return {"pass": not errors, "errors": errors, "checks": checks}
