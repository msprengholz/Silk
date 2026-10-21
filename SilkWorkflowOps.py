"""
SilkWorkflowOps — the single construction path for workflow objects.

Thin GUI-free wrappers over the existing FeaturePython constructors
(spec #16 / #14): tests and the future wizard call these functions,
never the constructors or Gui.runCommand. No existing module is modified.

Ticket #18: create_edge. Ticket #19/#20: create_patch / create_blend.
Ticket #42: the ops layer creates ONLY the unified object types
(Edge / Patch / Blend) -- the legacy per-fill builders (Patch44,
Patch33) are gone; the classes survive in their modules as
old-document restore shims only.
Ticket #44: seam resolution + seam inventory + create_blend_by_edge,
all identity-only (adjacency is the shared Edge object, never
geometric coincidence).
"""

import math

import FreeCAD

from SilkEdge import Edge, EdgeViewProvider, classify_sketches
from SilkPatch import Patch, PatchViewProvider
from SilkBlend import Blend, BlendStripViewProvider, BLEND_TYPES, PATCH_TYPES
from SilkMachinery import loop_order, corner_ring, CORNER_PIECE, OUTER_PIECE


def create_edge(sketches, name="Edge"):
    """Create a SilkEdge from one or two ControlPoly4 sketches.

    addObject -> Edge constructor -> view provider -> recompute ->
    return the created object, so later steps can consume the result
    in one script. No selection, no commands, no dialogs.

    #90: the geometry mode is derived from the sketch SHAPES, not from a
    toggle -- 3 visible lines or a single curve element (one sketch), two
    circle+line nodes (2N), or a plan + elevation pair (Sketches[0] is
    the plan, Sketches[1] the elevation; ControlPoly4_2X4P). A selection
    that cannot build any of those is REFUSED here, before anything is
    constructed: a console error naming the offending sketches (or the
    two plane normals) and None. The panel and the toolbar command run
    the same classifier, so they refuse identically.
    """
    doc = FreeCAD.ActiveDocument
    if not isinstance(sketches, (list, tuple)):
        sketches = [sketches]
    sketches = [s for s in sketches if s is not None]
    mode, detail = classify_sketches(sketches)
    if mode is None:
        FreeCAD.Console.PrintError(
            "Silk: cannot create an Edge -- %s\n" % detail)
        return None
    obj = doc.addObject("Part::FeaturePython", name)
    Edge(obj, list(sketches))
    EdgeViewProvider(obj.ViewObject)
    obj.ViewObject.LineWidth = 2.00
    obj.ViewObject.LineColor = (0.00, 1.00, 0.00)
    obj.ViewObject.PointSize = 4.00
    obj.ViewObject.PointColor = (0.00, 0.33, 1.00)
    doc.recompute()
    return obj


def create_patch(edges, name="Patch"):
    """Create the unified Patch (#37/#38/#42) from a variable-length
    Edges list.

    execute() selects the fill from the edge count: 4 edges -> the
    quad fill (#37), 3 edges -> the pointed fill (#38); other counts
    leave the object empty/valid. Mirrors create_edge (addObject ->
    constructor -> view provider -> recompute -> return). Renamed from
    create_patch_unified at the #42 retirement; the legacy per-fill
    create_patch (Patch44) / create_patch33 (Patch33) builders are
    gone -- direct construction of the legacy classes survives only
    for parity evidence and old-document restore.

    #66: a 4-edge selection that does not close a loop is REFUSED here,
    before anything is constructed: a console error naming the offending
    edges, and None. The fill itself reorders a good list into cycle
    order (SilkMachinery.loop_order), so the caller may pass the edges in
    any order -- click order from the panel included. What is left is a
    selection that genuinely cannot become a patch, and the old answer to
    that was a valid, up-to-date, INVISIBLE object plus a cheerful
    "Patch created". The 3-edge pointed fill keeps its documented
    graceful degradation (empty valid object), so the count check below
    stays as it was.

    #67: the returned Patch's `Edges` property is that normalized CYCLE,
    not the order the caller passed -- entry k is boundary side k. So
    `check_patch(p, list(p.Edges))` is the honest oracle call whatever
    order the selection arrived in; there is no second hidden order to
    know about.
    """
    edges = [e for e in list(edges or []) if e is not None]
    if len(edges) == 4:
        order, problem = loop_order(edges)
        if order is None:
            FreeCAD.Console.PrintError(
                "Silk: cannot create a Patch from these 4 edges -- they do "
                "not close a loop (%s). Nothing was created; a patch "
                "boundary is ONE closed loop of 4 edges meeting corner to "
                "corner.\n" % problem)
            return None
    doc = FreeCAD.ActiveDocument
    obj = doc.addObject("Part::FeaturePython", name)
    Patch(obj, edges)
    PatchViewProvider(obj.ViewObject)
    obj.ViewObject.LineWidth = 1.50
    obj.ViewObject.LineColor = (0.67, 1.00, 1.00)
    obj.ViewObject.PointSize = 4.00
    obj.ViewObject.PointColor = (0.00, 0.33, 1.00)
    doc.recompute()
    return obj


def create_blend(patch_a, patch_b, edge=None, name="Blend"):
    """Create the unified Blend (#39) joining two adjacent patches.

    The shared seam is auto-detected from the patches' corner poles
    (robust against degenerate pointed corners), or pinned geometrically
    from `edge`'s endpoint poles when given -- edge OBJECT identity is
    irrelevant, only the endpoint geometry is validated (both endpoints
    must sit on a corner pair of BOTH patches). A non-shared edge or a
    Blend fed as a patch refuses gracefully: empty valid object +
    console error, no crash. Mirrors the other ops (addObject ->
    constructor -> view provider -> recompute -> return).
    """
    doc = FreeCAD.ActiveDocument
    obj = doc.addObject("Part::FeaturePython", name)
    Blend(obj, patch_a, patch_b, edge)
    BlendStripViewProvider(obj.ViewObject)
    obj.ViewObject.LineWidth = 2.00
    obj.ViewObject.LineColor = (0.00, 1.00, 0.00)
    obj.ViewObject.PointSize = 5.00
    # Flat Lines, NOT Shaded: a strip's four boundary edges are what the
    # Surface workbench's Filling panel is meant to pick, and on this build
    # a Shaded face puts no edge in the pick at all -- measured through
    # FreeCAD's own `getObjectInfo` (5 px pick radius, Top view):
    # `B12/Edge4` is absent from a 2601-pixel window around that edge while
    # Shaded, and appears 72 times there at Flat Lines, against a 427-hit
    # control on a Flat-Lines `Patch44` edge
    # (docs/research/silk-fill-picking.md). Transparency 30 keeps the
    # surface readable through the strip.
    obj.ViewObject.DisplayMode = "Flat Lines"
    obj.ViewObject.ShapeColor = (0.00, 1.00, 0.00)
    obj.ViewObject.Transparency = 30
    doc.recompute()
    return obj


# ---- seam resolution + inventory (#44, identity-only) ----------------------
#
# Adjacency is OBJECT IDENTITY ONLY: the two patches adjacent to an Edge
# are exactly those whose `Edges` link list contains it (the glossary's
# "shared edge" vs "coincident boundary"). Coincident-but-unlinked
# patch boundaries are NEVER adjacent -- there is no geometric fallback.
# Every refusal is a console error in the "Silk: ..." refuse-gracefully
# style: never an exception, never a partial side effect (the by-edge
# op refuses BEFORE constructing an object, so no band splits get
# written either).

def _edge_referrers(edge, doc):
    """Patches (document order, identity-deduped) whose Edges link list
    references `edge`. Silent query shared by resolve_seam and
    seam_inventory."""
    refs = []
    for o in doc.Objects:
        if getattr(o, "object_type", None) not in PATCH_TYPES:
            continue
        if any(e is edge for e in (list(getattr(o, "Edges", None) or []))):
            if not any(r is o for r in refs):
                refs.append(o)
    return refs


def resolve_seam(edge):
    """Resolve the seam on `edge` by object identity (#44).

    Returns (patch_a, patch_b): the exactly-two Patches whose Edges link
    list references `edge` (document order). Returns None -- after a
    console error naming the reason -- when 0, 1, or 3+ patches
    reference it. The 3+ (non-manifold) message points at the deferred
    corner-fill track. Pure query: no side effects beyond the message.
    """
    refs = _edge_referrers(edge, FreeCAD.ActiveDocument)
    ename = getattr(edge, "Name", "?")
    if len(refs) == 2:
        return refs[0], refs[1]
    if not refs:
        FreeCAD.Console.PrintError(
            "Silk: edge %s is not used by any patch yet\n" % ename)
    elif len(refs) == 1:
        FreeCAD.Console.PrintError(
            "Silk: edge %s is a boundary of %s only -- a blend needs an "
            "adjacent patch across this edge\n" % (ename, refs[0].Name))
    else:
        FreeCAD.Console.PrintError(
            "Silk: %d patches reference edge %s (%s) -- three patches "
            "reference this edge, not a blendable seam; multi-patch "
            "junctions need a corner fill (deferred)\n"
            % (len(refs), ename, ", ".join(p.Name for p in refs)))
    return None


def _existing_blend(doc, patch_a, patch_b, edge):
    """First blend object between exactly the patch_a/patch_b pair that
    covers `edge`'s band, or None (#44 idempotency).

    Identity-only seam matching: a blend whose Edge link IS `edge`
    covers it; a blend with NO Edge link (auto-detected seam -- and the
    legacy BlendStrip type, which carries no Edge property) conservatively
    covers every shared edge of its pair, since without geometry we
    cannot prove which band it took ("never create a second blend on
    the same band"). A blend pinned to a DIFFERENT shared edge of the
    same pair does not block: a two-seams pair (closed rings) blends
    each seam separately (#44).
    """
    exact = None
    fallback = None
    for o in doc.Objects:
        if getattr(o, "object_type", None) not in BLEND_TYPES:
            continue
        a = getattr(o, "PatchA", None)
        b = getattr(o, "PatchB", None)
        if not ((a is patch_a and b is patch_b)
                or (a is patch_b and b is patch_a)):
            continue
        oe = getattr(o, "Edge", None)
        if oe is edge:
            exact = o
            break
        if oe is None and fallback is None:
            fallback = o
    return exact if exact is not None else fallback


def create_blend_by_edge(edge, name="Blend"):
    """Create the Blend on the seam `edge` occupies (#44).

    resolve_seam (identity-only) -> idempotency check -> create_blend
    with `edge` as the geometric seam pin. Every refuse path (edge
    referenced by 0 / 1 / 3+ patches, or this seam already blended)
    prints a message and returns WITHOUT constructing an object or
    writing band splits. Returns the new Blend on success and the
    EXISTING blend on the idempotent no-op (a message names it); None
    on refusal.
    """
    doc = FreeCAD.ActiveDocument
    pair = resolve_seam(edge)
    if pair is None:
        return None
    patch_a, patch_b = pair
    existing = _existing_blend(doc, patch_a, patch_b, edge)
    if existing is not None:
        FreeCAD.Console.PrintMessage(
            "Silk: %s and %s are already blended by %s -- no second "
            "blend created\n" % (patch_a.Name, patch_b.Name, existing.Name))
        return existing
    return create_blend(patch_a, patch_b, edge=edge, name=name)


def seam_inventory(doc=None):
    """Pure-data inventory of every seam in the document (#44).

    One entry per shared Edge object, in document order:
    {"edge", "patch_a", "patch_b", "status", "blend"} -- the objects
    themselves, no rendering logic (the future panel consumes this).

      blendable  exactly the two patches reference the edge and no
                 blend covers it (blend is None);
      blended    a blend covers this edge's band on the pair (blend
                 names it);
      blocked    3+ patches reference the edge -- non-manifold, not
                 blendable (patch_a/patch_b are the first two refs in
                 document order, blend is None).

    An edge referenced by fewer than two patches is not a seam and gets
    no entry. A pair sharing TWO edges (closed rings) gets one entry --
    and one status -- per seam; blends are matched per seam through
    their Edge link (the #44 two-seam rule), so one blended seam leaves
    the other blendable.
    """
    doc = doc if doc is not None else FreeCAD.ActiveDocument
    entries = []
    for o in doc.Objects:
        if getattr(o, "object_type", None) != "Edge":
            continue
        refs = _edge_referrers(o, doc)
        if len(refs) < 2:
            continue  # not a seam
        entry = {"edge": o, "patch_a": refs[0], "patch_b": refs[1],
                 "status": None, "blend": None}
        if len(refs) > 2:
            entry["status"] = "blocked"
        else:
            blend = _existing_blend(doc, refs[0], refs[1], o)
            entry["status"] = "blended" if blend else "blendable"
            entry["blend"] = blend
        entries.append(entry)
    return entries


def _existing_corner_blend(doc, strips):
    """The CornerBlend already filling exactly this strip SET, or None
    (#28/#91 idempotency). Identity-only: a junction is identified by its
    three or four blends, whatever order they were handed over in."""
    want = {id(s) for s in strips}
    for o in doc.Objects:
        if getattr(o, "object_type", None) != "CornerBlend":
            continue
        have = list(getattr(o, "Strips", []) or [])
        if len(have) == len(strips) and {id(s) for s in have} == want:
            return o
    return None


def existing_corner(strips):
    """The CornerBlend this ring ALREADY has, or None.

    The public reading of `_existing_corner_blend`, for a caller that has to
    know whether its choices are a creation or an edit: the panel's Apply
    writes onto a built corner, and a ring that has none is built by
    `create_corner_blend`, which takes the same choices."""
    doc = FreeCAD.ActiveDocument
    ordered, _why = _ring_of(strips)
    return _existing_corner_blend(doc, ordered or list(strips or []))


# ---- the corner stage's construction (#119) ---------------------------
#
# THE CORNER STAGE BUILDS ONE OF TWO CONSTRUCTIONS, and the owner has
# ruled which one is the default (2026-10-21: *"the rolling corner fill
# should be the default fill!"*).
#
#   "rolling"  THE DEFAULT.  The maintainer's rolling corner: the 66
#               over the ring's CUT cells (the band's corner-side cut
#               IS the rolling leader), plus the small triangular
#               member beside it.
#   "shipped"  THE FALLBACK.  The 66 with the spiderweb member -- the
#               construction this workbench shipped until #119.  It is
#               selected BY NAME and is byte for byte the construction
#               of before: 0.00e+00 on poles and weights.
#
# THE TRIANGULAR MEMBER'S FACE is a `CubicSurface_64` over the member net
# by default -- the construction the maintainer's own files store -- and the
# FreeCAD `Surface::Filling` is the selectable option (`member_face`, #119
# follow-up). Both are reachable from this layer, which is the only
# construction path.
#
# The switch lives HERE, in the ops layer, because the ops layer is the
# only construction path (AGENTS.md): the wizard's corner step and the
# toolbar command both call `create_corner_blend` and therefore both
# build the rolling corner, with NO new button (the visible set stays
# Edge -> Patch -> Blend -> Corner Blend).
#
# The rolling construction is a 3-VALENT thing: its fourth side is the
# triangular member, and a 4-valent ring has no such member.  A 4-valent
# ring therefore keeps the shipped corner, and says so by name.

CORNER_CONSTRUCTION_ROLLING = "rolling"
CORNER_CONSTRUCTION_SHIPPED = "shipped"
CORNER_CONSTRUCTIONS = (CORNER_CONSTRUCTION_ROLLING,
                        CORNER_CONSTRUCTION_SHIPPED)
CORNER_CONSTRUCTION_DEFAULT = CORNER_CONSTRUCTION_ROLLING

# The rolling leader: the fraction of the seam curve's own parameter,
# measured from the junction corner.  The video's number: 0.25 / 0.75.
# (The parameter space is stated once, in the rolling section below.)
ROLLING_LEADER = 0.25

# The TRIANGULAR MEMBER'S FACE (#119 follow-up): the maintainer's corner
# carries a `CubicSurface_64` over the member net beside the 66 (file 27/28/
# 29: `ControlGrid64_3_Grid44_000 -> CubicSurface_64_052`), and that is what
# the corner stage builds by default. The owner's own recommendation is to
# REPLACE that surface with a FreeCAD `Surface::Filling` for quality, so the
# fill stays reachable -- as the option it is -- and never as the implicit
# default.
MEMBER_FACE_CUBICSURFACE64 = "cubicsurface64"
MEMBER_FACE_FILL = "fill"
MEMBER_FACES = (MEMBER_FACE_CUBICSURFACE64, MEMBER_FACE_FILL)
MEMBER_FACE_DEFAULT = MEMBER_FACE_CUBICSURFACE64


def create_corner_blend(*strips, name="CornerBlend", pin=None,
                         construction=None, leader=ROLLING_LEADER,
                         leaders=None, member_face=MEMBER_FACE_DEFAULT):
    """Create the CornerBlend filling the junction where 3 or 4 blend
    strips meet (#28; rebuilt on the subgrid chain in #91).

    `strips` are the ring Blend strips, in any order (or one list): three
    where three patches meet (the triangular 4th member is built
    invisibly), four where four do.
    `pin` is the optional triangular-member placement (#117):
    `(ring patch, corner index 0..3)`, the corner the member must be
    built at; None leaves the automatic search in charge.
    `construction` is the corner stage's CONSTRUCTION (#119): "rolling"
    (the maintainer's rolling corner -- the 66 over the ring's cut cells
    plus the small triangular member whose face is a FreeCAD filling) or
    "shipped" (the 66 with the spiderweb member this workbench shipped
    until #119).  None means the module default, which is "rolling" (the
    owner, 2026-10-21: "the rolling corner fill should be the default
    fill!").  The shipped construction is the FALLBACK: it is selected by
    name and is byte for byte the construction of before (#119) -- 0.00e+00
    on poles and weights.
    `leader` is the rolling leader (the fraction of the seam curve's own
    parameter, measured from the junction corner) the rolling
    construction cuts the ring at; it is ignored by the shipped one.
    `leaders` is the leader PER SEAM (`{blend or its Name: leader}`): a seam
    it names is rolled at its own leader, one it does not at `leader`. The
    ring's seams are the unit the leader is measured on, so a corner can be
    rolled asymmetrically -- which is the one way the leader changes the
    corner's SHAPE rather than its size (#118, measured).
    `member_face` selects the triangular member's surface: "cubicsurface64"
    (the default -- the construction the maintainer's file stores) or
    "fill" (the owner's FreeCAD `Surface::Filling` replacement). It is
    ignored by the shipped construction, which has no separate member.
    The ring resolver orders them; the corner geometry is computed
    BEFORE anything is constructed, so a selection that is not a ring
    around one shared junction -- or a pin no member can be assembled at
    -- is refused by name and leaves NO
    object in the tree (the #80/#83 "invalid + Up-to-date" lesson: never
    park a dead object in the document). A junction that already has a
    corner returns that existing CornerBlend -- an idempotent no-op.

    addObject -> CornerBlend constructor -> view provider -> recompute ->
    return the created object. GUI-free, so the panel and toolbar wrap it
    in their own transaction.
    """
    from SilkCorner import (CornerBlend, CornerBlendViewProvider,
                            corner_inputs, CORNER_DEFAULT_TOL)
    doc = FreeCAD.ActiveDocument
    if len(strips) == 1 and isinstance(strips[0], (list, tuple)):
        strips = list(strips[0])
    strips = [s for s in (strips or []) if s is not None]
    if len(strips) not in (3, 4):
        FreeCAD.Console.PrintError(
            "Silk: cannot create a corner blend from %d blend%s -- a corner "
            "is the ring of 3 (triangular) or 4 blends around one junction. "
            "Nothing was created.\n"
            % (len(strips), "" if len(strips) == 1 else "s"))
        return None
    construction = (CORNER_CONSTRUCTION_DEFAULT if construction is None
                    else str(construction))
    if construction not in CORNER_CONSTRUCTIONS:
        FreeCAD.Console.PrintError(
            "Silk: the corner construction must be %s -- got %r. Nothing was "
            "created.\n"
            % (" or ".join(repr(c) for c in CORNER_CONSTRUCTIONS),
               construction))
        return None
    # `member_face` is checked BEFORE anything is built: an unknown value is a
    # caller's mistake, not a corner that cannot be built, so it must not be
    # swallowed by the shipping fallback below.
    if str(member_face) not in MEMBER_FACES:
        FreeCAD.Console.PrintError(
            "Silk: the triangular member's face must be %s -- got %r. "
            "Nothing was created.\n"
            % (" or ".join(repr(f) for f in MEMBER_FACES), member_face))
        return None
    if construction == CORNER_CONSTRUCTION_ROLLING:
        if len(strips) == 3:
            corner = _create_rolling_corner_blend(strips, name=name, pin=pin,
                                                 leader=leader,
                                                 leaders=leaders,
                                                 member_face=member_face)
            if corner is not None:
                _record_construction(corner, CORNER_CONSTRUCTION_ROLLING)
                return corner
            # The rolling construction REFUSED BY NAME (it has printed
            # the reason).  The shipped construction is the FALLBACK, and
            # the corner stage must still build a corner where the
            # rolling one cannot: the rolling leader is a CUT in the
            # band, and a patch that carries TWO junctions on the
            # seam-parallel axis cannot carry that cut (the band edge is
            # shared by two junctions).  The rolling construction leaves
            # the model untouched when it refuses, so the fallback below
            # is the shipped corner, byte for byte.  WHICH construction
            # was built is recorded on the corner (`Construction`), so a
            # caller -- the panel above all -- can say so instead of
            # reporting a plain "corner created" for a corner that is not
            # the one asked for.
            FreeCAD.Console.PrintMessage(
                "Silk: the rolling corner cannot be built on these %d "
                "blends, so this corner keeps the shipped construction.\n"
                % len(strips))
        else:
            # The rolling corner is a 3-valent construction: its fourth
            # side is the TRIANGULAR MEMBER, and a 4-valent ring has no
            # such member.  A 4-valent ring therefore keeps the shipped
            # corner, and says so.
            FreeCAD.Console.PrintMessage(
                "Silk: the rolling corner is a 3-valent construction (the "
                "triangular member is its fourth side); this ring has 4 "
                "strips, so it keeps the shipped corner.\n")
    grids, _cells, why = corner_inputs(strips, CORNER_DEFAULT_TOL, pin)
    if grids is None:
        FreeCAD.Console.PrintError(
            "Silk: cannot create a corner blend from these %d blends -- %s. "
            "Nothing was created.\n" % (len(strips), why))
        return None
    existing = _existing_corner_blend(doc, strips)
    if existing is not None:
        FreeCAD.Console.PrintMessage(
            "Silk: this junction already has a corner blend (%s) -- no "
            "second one created\n" % existing.Name)
        return existing
    if len(strips) == 3:
        from SilkMachinery import corner_ring_3
        ordered, _why = corner_ring_3(strips)
    else:
        ordered, _why = corner_ring(strips)
    obj = doc.addObject("Part::FeaturePython", name)
    CornerBlend(obj, ordered)
    CornerBlendViewProvider(obj.ViewObject)
    obj.ViewObject.LineWidth = 1.50
    obj.ViewObject.LineColor = (1.00, 0.67, 0.00)
    obj.ViewObject.PointSize = 4.00
    obj.ViewObject.DisplayMode = "Flat Lines"
    obj.ViewObject.ShapeColor = (1.00, 0.67, 0.00)
    obj.ViewObject.Transparency = 30
    if pin is not None:
        # #117: the pin rides the object as the same two properties the
        # data tab edits; setting them recomputes (onChanged), so the
        # last doc.recompute() below is the no-op confirmation.
        obj.MemberPatch = pin[0]
        obj.MemberCorner = int(pin[1])
    # The shipped construction is the one written here (the rolling one
    # records itself at its own return above), so a corner the panel built
    # because the rolling construction refused says WHICH one it is.  This
    # object has not been computed yet, so the record must not clear its
    # touch flag -- the recompute below is what builds it.
    _record_construction(obj, CORNER_CONSTRUCTION_SHIPPED, settle=False)
    doc.recompute()
    return obj


def _member_cell_cut_problem(patch, planned):
    """None when the writes in `planned` cut `patch`'s cell back on BOTH of
    its axes, else the reason as one clause.

    The rolling construction's whole geometry is the cell between the setback
    and the leader: the member's real row is the segment between that cell's
    two mixed corners, and the two strips that share the patch end their ring
    rows on them (`SilkMachinery.ring_corner_gap`).  A leader that does not
    clear its setback is INERT (`SilkMachinery.axis_cuts`), so the cell on
    that axis stays the band's own cell and only ONE of the row's ends is a
    ring corner -- measured on the cube corner, that arrangement builds a 6x6
    with 4 coincident pole pairs (or refuses outright, depending on which
    axis it is).

    Read off the INTERVALS the writes will produce, not off the values: the
    "is it a real cut" question is `axis_cuts`' answer and this must not
    answer it a second way."""
    from SilkMachinery import (build_intervals, split_pair, leader_pair,
                              leader_cut_prop)
    after = {(p, prop): value for p, prop, _cur, value in planned}
    for letter in ("U", "V"):
        s1, s2 = split_pair(patch, letter)
        l1, l2 = leader_pair(patch, letter)
        l1 = after.get((patch, leader_cut_prop(letter, 0)), l1)
        l2 = after.get((patch, leader_cut_prop(letter, 1)), l2)
        plain = len(build_intervals(s1, s2))
        cut = len(build_intervals(s1, s2, l1, l2))
        if cut == plain:
            return ("its %s axis carries no leader cut that clears the "
                    "setback (%s = %g, %s = %g, and a leader at or inside "
                    "the band edge cuts nothing); the cell has to be cut "
                    "back on both axes"
                    % (letter, leader_cut_prop(letter, 0), l1,
                       leader_cut_prop(letter, 1), l2))
    return None


def _record_construction(corner, construction, settle=True):
    """Write which construction `corner` is onto the object.

    The corner stage is the only place that knows, and the panel, the
    toolbar command and `apply_corner_choices` all have to agree with it
    (`SilkCorner.corner_construction` is the reader).

    `settle` clears the touch flag the write raises.  It is True when the
    corner is ALREADY BUILT (the rolling path returns a corner it recomputed
    itself, and a property written after that would leave the document dirty
    for nothing -- #125), and False on a FRESH object, which must reach the
    caller's own `doc.recompute()` still Touched or it is never built at
    all."""
    from SilkCorner import ensure_construction
    ensure_construction(corner)
    if corner.Construction != construction:
        corner.Construction = construction
        if settle:
            try:
                corner.purgeTouched()
            except Exception:
                pass


def _create_rolling_corner_blend(strips, name="CornerBlend", pin=None,
                                  leader=ROLLING_LEADER, leaders=None,
                                  member_face=MEMBER_FACE_DEFAULT):
    """The ROLLING construction of the corner stage (#119) -- the default.

    Returns the CornerBlend (the 66 over the ring's cut cells) -- the
    same kind of object the shipped path returns, so the wizard and the
    toolbar command need no change -- or None when the rolling
    construction refuses by name.

    WHAT IT BUILDS, in the maintainer's order:

      1. the CUT: the rolling leader is written as the member patch's own
         LEADER CUT (its seam-parallel axis, at the junction end), and the
         patch re-cuts its base surface there.  The cut is a knot line of
         the net, so the pieces meet exactly, and the band edge is left
         alone -- the setback and the leader are two numbers, as they are in
         the maintainer's model.  The other patches of the ring are NOT cut:
         the member patch is the only patch whose two ring corners may be two
         different points (`SilkMachinery.ring_corner_gap`).
      2. the 66: the corner fill over the ring's CUT cells -- the member's
         patch contributes the cell BETWEEN its setback and its leader.
      3. the small triangular member BESIDE it, whose FACE is a
         `CubicSurface_64` over the member net by default -- the
         construction the maintainer's own files store -- or, when
         `member_face` asks for it, the owner's FreeCAD
         `Surface::Filling` replacement.  The silk member that carries
         that fill's boundary is kept (hidden) in the fill case, because
         the fill's boundary edges live on it.

    The member's placement is read with `SilkCorner.corner_member_pin`,
    the SAME automatic search the corner's own derivation runs, so the
    cut is always on the seams of the patch that carries the member.
    """
    from SilkCorner import corner_member_pin, CORNER_DEFAULT_TOL
    from SilkMachinery import corner_ring_3
    # 0. the RING contract, before anything is touched: a selection that
    #    is not a 3-cycle ring is refused by name and NOTHING is created
    #    (the patches' band edges are not written either).
    ordered, why = corner_ring_3(strips)
    if ordered is None:
        FreeCAD.Console.PrintError(
            "Silk: cannot create a corner blend from these %d blends -- %s. "
            "Nothing was created.\n" % (len(strips), why))
        return None
    # 1. where the triangular member sits -- the patch whose seams carry
    #    the rolling cut.
    member_pin = None
    if pin is not None:
        from SilkCorner import resolve_member_pin
        patches, _pwhy = corner_ring_patches(ordered)
        member_pin, why = resolve_member_pin(pin, patches or [])
        if member_pin is None:
            FreeCAD.Console.PrintError(
                "Silk: %s. Nothing was created.\n" % why)
            return None
    else:
        member_pin, why = corner_member_pin(strips, CORNER_DEFAULT_TOL)
        if member_pin is None:
            FreeCAD.Console.PrintError(
                "Silk: cannot create a rolling corner blend from these %d "
                "blends -- %s. Nothing was created.\n" % (len(strips), why))
            return None
    # 2. the rolling corner itself: the cut, the 66 over the cut cells,
    #    the member and its fill.
    res = create_rolling_corner_66(strips, patch=member_pin[0],
                                    leader=leader, seams=None, order=1,
                                    name=name, corner_name=name,
                                    member_face=member_face,
                                    member_leaders=leaders,
                                    pin=member_pin)
    if res is None:
        return None
    # THE USER'S PIN RIDES THE CORNER (#117). `member_pin` above is always
    # resolved (the automatic search fills it in when nobody asked), and the
    # property stays UNSET in that case: an unset pin means "the search
    # decides", which is the #117 contract, and the corner and the member
    # then agree because BOTH run that same search on the same ring
    # (`SilkCorner._member_pin_of` reads the property, so a USER's pin
    # reaches the member too). Writing the search's answer back would turn a
    # choice nobody made into a stored one.
    if pin is not None:
        from SilkCorner import ensure_member_pin
        corner = res["corner"]
        ensure_member_pin(corner)
        if (corner.MemberPatch is not member_pin[0]
                or int(corner.MemberCorner) != int(member_pin[1])):
            corner.MemberPatch = member_pin[0]
            corner.MemberCorner = int(member_pin[1])
            FreeCAD.ActiveDocument.recompute()
    return res["corner"]


# ---- the rolling corner (#119) -------------------------------------------
#
# The maintainer's rolling corner (video episode 51) cuts an edge blend
# along its SEAM and re-creates the rest of the band, so the junction
# carries two zones: a small fillet that rolls into a large one.  The
# cut position is a "rolling leader" -- a position ON THE SEAM CURVE,
# measured from the junction corner.
#
# PARAMETER SPACE (one statement, used by every piece): the leader is a
# fraction of the SEAM CURVE'S OWN parameter, measured from the junction
# corner.  A patch's base surface is a bicubic Bezier and one of its
# boundary sides is a cubic Bezier curve whose parameter IS that side's
# surface coordinate, so "0.25 of the way along the seam curve" is the
# surface coordinate 0.25 (0.75 when the corner is at the far end).  It
# is NOT the band depth (the setback) and NOT an arc-length fraction:
# the maintainer's own tool places the cut by a curve position.


def create_split_blend(patch_a, patch_b, edge=None, leader=ROLLING_LEADER,
                       name="Blend"):
    """Create the TWO blends a rolling leader cuts one seam blend into.

    The corner-side piece reaches the junction corner; the outer piece is
    the rest of the seam.  Both are real surfaces, and they meet exactly
    at the cut: the leader is a knot line of both nets (the patch's base
    surface is SEGMENTED there, not re-fitted), so the seam between them
    is C0 by construction.

    The patch is NOT modified -- the leader is a position on the seam
    curve, not one of the patch's two named band edges, so it cannot live
    on the patch.  `Leader` = 0 (the default) is the shipped full-seam
    behaviour, byte for byte.

    Returns (corner_blend, outer_blend); a refusal (the leader does not
    fall inside the band's own extent) creates NOTHING and returns
    (None, None)."""
    from SilkBlend import Blend, BlendStripViewProvider
    doc = FreeCAD.ActiveDocument
    leader = float(leader)
    if leader < 0.0 or leader >= 1.0:
        FreeCAD.Console.PrintError(
            "Silk: the rolling leader %g is not a position inside the seam "
            "curve (0, 1). Nothing was created.\n" % leader)
        return None, None
    made = []
    for piece in (CORNER_PIECE, OUTER_PIECE):
        obj = doc.addObject("Part::FeaturePython", "%s_%s" % (name, piece))
        Blend(obj, patch_a, patch_b, edge)
        BlendStripViewProvider(obj.ViewObject)
        obj.ViewObject.LineWidth = 2.00
        obj.ViewObject.LineColor = (0.00, 1.00, 0.00)
        obj.ViewObject.PointSize = 5.00
        obj.ViewObject.DisplayMode = "Flat Lines"
        obj.ViewObject.ShapeColor = (0.00, 1.00, 0.00)
        obj.ViewObject.Transparency = 30
        obj.Leader = leader
        obj.LeaderPiece = piece
        made.append(obj)
    doc.recompute()
    for obj in made:
        if not obj.Poles:
            FreeCAD.Console.PrintError(
                "Silk: the split blend %s did not build -- the leader %g "
                "does not fall inside the band's own extent. The split "
                "blends were removed again.\n" % (obj.Name, leader))
            for o in made:
                if doc.getObject(o.Name) is not None:
                    doc.removeObject(o.Name)
            doc.recompute()
            return None, None
    return made[0], made[1]


def _seam_side_index(label):
    """The patch boundary-side index (0..3) of a side label U0/V1/U1/V0."""
    return {"U0": 0, "V1": 1, "U1": 2, "V0": 3}[label]


def _curve_segment(curve, u0, u1):
    """The part of `curve` between parameters u0 and u1, as an Edge.

    Exact: the curve is trimmed (or segmented), never re-fitted."""
    c = curve.copy()
    if hasattr(c, "segment"):
        c.segment(u0, u1)
        return c.toShape()
    if hasattr(c, "trim"):
        c.trim(u0, u1)
        return c.toShape()
    raise ValueError("this curve cannot be trimmed")


def create_rolling_triangle(patch, sides, leader=ROLLING_LEADER, order=1,
                            name="RollingTriangle"):
    """Create the small triangular surface at the corner (#119).

    `patch` is the pinned patch -- the one whose corner cell carries the
    triangle.  `sides` are the two boundary sides of that patch the ring
    blends take (labels "U0"/"V1"/"U1"/"V0").

    The boundary is a TRIANGLE:
      * the corner-side piece of the FIRST seam curve -- the seam curve
        from the junction corner to the leader position, and
      * the corner-side piece of the SECOND seam curve, and
      * the CHORD ACROSS THE CORNER: the straight line joining the two
        leader points.

    The third side is the ONE ambiguous piece of this construction and it
    is named here: the chord across the corner.  The alternatives are the
    maintainer's collapsed triangular member (a degenerate surface -- not
    a boundary a fill can take) and the third seam's blend end (which
    closes a different hole).  The chord is what makes the three
    boundary curves MEET.

    The fill is FreeCAD's own `Surface::Filling` (`create_fill`), so it
    carries the same by-name refusals and the same C0 boundary oracle as
    the shipped corner fill.

    Returns the fill object, or None when nothing could be built."""
    import Part
    from SilkMachinery import seam_axis_roles
    doc = FreeCAD.ActiveDocument
    if len(sides) != 2:
        FreeCAD.Console.PrintError(
            "Silk: the rolling triangle needs the two seam sides of the "
            "pinned patch (got %d). Nothing was created.\n" % len(sides))
        return None
    edges = list(getattr(patch, "Edges", None) or [])
    curves = []
    for label in sides:
        idx = _seam_side_index(label)
        if idx >= len(edges) or edges[idx] is None:
            FreeCAD.Console.PrintError(
                "Silk: patch %s has no boundary edge on side %s. Nothing was "
                "created.\n" % (patch.Name, label))
            return None
        curves.append(edges[idx].Shape.Curve)
    if len(curves) != 2:
        FreeCAD.Console.PrintError(
            "Silk: the rolling triangle needs two seam curves. Nothing was "
            "created.\n")
        return None
    # the junction corner: the point the two seam curves share
    vertex = None
    for a in (curves[0].StartPoint, curves[0].EndPoint):
        for b in (curves[1].StartPoint, curves[1].EndPoint):
            if (a - b).Length < 1e-7:
                vertex = a
                break
        if vertex is not None:
            break
    if vertex is None:
        FreeCAD.Console.PrintError(
            "Silk: the two seam curves of %s do not share a corner -- the "
            "rolling triangle has no vertex. Nothing was created.\n"
            % patch.Name)
        return None
    # the leader point on each seam: the curve's own parameter, measured
    # from the corner end
    segs = []
    points = []
    for curve in curves:
        at_start = (curve.StartPoint - vertex).Length < 1e-7
        u_leader = leader if at_start else 1.0 - leader
        u0, u1 = (0.0, u_leader) if at_start else (1.0 - leader, 1.0)
        segs.append(_curve_segment(curve, min(u0, u1), max(u0, u1)))
        points.append(curve.value(u_leader))
    chord = Part.LineSegment(points[0], points[1]).toShape()
    boundary = Part.Compound([segs[0], segs[1], chord])
    carrier = doc.addObject("Part::Feature", name + "_Boundary")
    carrier.Shape = boundary
    doc.recompute()
    links = [(carrier, "Edge%d" % (i + 1)) for i in range(3)]
    # no support face: the three boundary edges live on a carrier object
    # that carries no face of its own, and the chord is on no patch at
    # all. FreeCAD's filling builds the surface over the curves alone.
    obj = create_fill(links, faces=[], order=order, name=name)
    if obj is None and order != 0:
        # A G1/G2 fill over a boundary that cannot carry it (a planar
        # triangle, for instance) is refused by FreeCAD itself; the
        # C0 fill is the honest fallback and still meets the boundary
        # exactly, which is what the C0 oracle checks.
        FreeCAD.Console.PrintMessage(
            "Silk: the rolling triangle's fill would not build at "
            "continuity order %d; falling back to order 0 (C0).\n" % order)
        obj = create_fill(links, faces=[], order=0, name=name)
    if obj is None:
        FreeCAD.Console.PrintError(
            "Silk: the rolling triangle over %s did not build. Nothing was "
            "left in the tree.\n" % patch.Name)
    return obj


def create_rolling_corner(strips, patch, leader=ROLLING_LEADER, order=1,
                          name="Rolling"):
    """Build the rolling corner at a 3-valent junction (#119) -- PATH (B).

    THE OWNER'S SPEC, AND WHAT THIS BUILDS.  The owner's own analysis of
    the maintainer's video: *"fundamentally the corner blend is
    constructed of one quad surface (created with Silk tools, so well
    behaved and low order, blends nicely) and a smaller triangular
    surface ... edward proposes this smaller surface to be replaced with
    a freecad surface patch."*  So the rolling corner is:

      * the BIG QUAD PATCH = the 0.75 piece of each split edge blend
        (a `CubicSurface_64` -- Silk-made, low order, the blend surface
        itself), and
      * the SMALL TRIANGULAR SURFACE = a FreeCAD `Surface::Filling`
        over the corner region's boundary: the two 0.25 pieces (the
        corner-side part of each of the two split seams' curves) and the
        third side.

    **NO `ControlGrid66` AND NO TRIANGULAR MEMBER ARE BUILT.**  The
    maintainer's 66 is a FOUR-member fill; a 3-valent corner has only
    three blends, so the fourth member (the "scaffolding piece" with a
    collapsed row) is what makes a Silk-native 66 possible at all.  The
    owner's spec does not want it: the corner face here is FreeCAD's
    own filling, and the 66 + member would be scaffolding nobody uses.
    The shipped default 3-valent corner (which DOES build the member
    and the 66) is untouched by this path.

    `strips` are the ring's three blends, `patch` the PINNED patch
    -- the one whose corner carries the triangular surface.  The two
    ring strips on that patch's seams are split at the leader (two real
    surfaces each, meeting exactly at the cut).

    Returns a dict:
      {'corner_pieces': {strip name: (corner piece, outer piece)},
       'ring': the two corner-side pieces and the unsplit strip,
       'triangle': the triangular surface (or None),
       'sides': the two boundary sides the triangle was built on}
    or None when the selection is not a 3-valent ring around the pinned
    patch."""
    from SilkBlend import side_and_end
    strips = [s for s in (strips or []) if s is not None]
    if len(strips) != 3:
        FreeCAD.Console.PrintError(
            "Silk: the rolling corner needs the ring's 3 blends (got "
            "%d). Nothing was created.\n" % len(strips))
        return None
    on_patch = [s for s in strips
                if getattr(s, "PatchA", None) is patch
                or getattr(s, "PatchB", None) is patch]
    if len(on_patch) != 2:
        FreeCAD.Console.PrintError(
            "Silk: the pinned patch %s carries %d of the ring's 3 seams (2 "
            "are needed: the triangle's two sides). Nothing was created.\n"
            % (getattr(patch, "Name", "?"), len(on_patch)))
        return None
    corner_pieces = {}
    ring = []
    for s in strips:
        if s in on_patch:
            c, o = create_split_blend(s.PatchA, s.PatchB, edge=s.Edge,
                                      leader=leader, name=s.Name)
            if c is None:
                return None
            corner_pieces[s.Name] = (c, o)
            ring.append(c)
        else:
            ring.append(s)
    sides = []
    for s in on_patch:
        label, _ss = side_and_end(s, patch)
        if label is None:
            FreeCAD.Console.PrintError(
                "Silk: blend %s cannot say which side of %s it takes. "
                "Nothing was created.\n" % (s.Name, patch.Name))
            return None
        sides.append(label)
    triangle = create_rolling_triangle(patch, sides, leader=leader,
                                       order=order,
                                       name="%sTriangle" % name)
    return {"corner_pieces": corner_pieces, "ring": ring,
            "triangle": triangle, "sides": sides,
            "leader": float(leader)}


# ---- the rolling corner, PATH (A): the 66 chain fed with CUT cells -------
#
# WHAT THE MAINTAINER'S OWN FILE SAYS (read offline from
# upstream/Resources/Tutorial_Files/Silk CopyPasta/
# Silk_CopyPasta_27_First_Corner_Rolled.FCStd, its Document.xml and its
# stored nets; see docs/research/silk-rolling-corner-66.md):
#
#   ControlGrid66_4Sub_012 -> 4 x SubGrid33_2Grid64, whose ring members
#   are three blends (ControlGrid64_2Grid44) and one TRIANGULAR MEMBER
#   (ControlGrid64_3_1Grid44 over the corner patch's corner cell).
#
# and, read off the stored cells (their parametric spans against the
# corner patch's own net), the corner patch is cut at TWO positions per
# axis: the SETBACK (the band's width, 1/16) and the LEADER (0.25, where
# the band is cut back from the junction corner).  So:
#
#   * the BAND of a seam starts at the LEADER -- the band's cell is
#     [0, setback] across by [leader, far] along, and the base surface
#     is CUT there (the file's five new ControlGrid44_2EdgeSegments);
#   * the CORNER CELL -- the member's cell -- is the region between the
#     setback and the leader;
#   * so the corner fill's boundary against each blend is the blend's
#     CUT EDGE, i.e. it sits AT THE LEADER.
#
# IN SILK'S OWN CELL STRUCTURE THE LEADER IS A CUT OF THE PATCH: the
# patch's LEADER CUT on the seam-parallel axis, at the junction end
# (`ULeader1` / `VLeader2` -- `SilkMachinery.leader_cut_prop`), which is the
# property #119 added for exactly this separation.  The band edge stays the
# user's SETBACK.  The corner fill then follows the leader because the
# member's cell becomes the region BETWEEN the two cuts, so the two strips
# that share the member's patch end their junction rows at TWO DIFFERENT
# points -- the member's real row runs between them -- and the 66 stops at
# the member's cell instead of sweeping over it (#127).
#
# THE CUT IS ON THE MEMBER PATCH ONLY.  It has to be: the member patch is the
# one patch where two ring pairs meet, so it is the one patch whose two ring
# corners are legitimately two different points (the two ends of the member's
# row).  On any other patch a second cut splits the corner cell's far corner
# in two and the pair no longer meets (`SilkMachinery.ring_corner_gap` names
# the two numbers; the corner stage refuses with that sentence).  The member
# patch is also where the maintainer cuts: his corner patch carries the
# setback AND the leader, and his two blends' cells run out to the leader.
#
# The face of the tri is the member's own `control_grid64_3_1` net -- its
# REAL row on the ring, its collapsed row inside the loop -- and the member
# is read REAL-ROW-FIRST on that patch (`SilkCorner._member_row_order`).

def seam_junction_end(strip, patch, ring, tol=None):
    """`(end, None)` or `(None, why)`: which parametric end of `strip`'s
    SEAM-PARALLEL axis on `patch` carries the junction `ring` rolls.  #126.

    WHY THE PATCH CANNOT ANSWER THIS.  A band's along-seam extent is bounded
    by the corner cell at the junction end, and a patch has always named
    that end by the band edge it carries there -- which works while the
    along-seam axis carries ONE band edge, i.e. while the patch has one
    junction on that axis.  The owner's own ring patches carry a THIRD seam
    on the side opposite the junction, so their along-seam axis carries a
    band edge at BOTH ends and the patch is symmetric between them: nothing
    in `USplit1/2` says which end THIS ring's junction is at.  So the answer
    needs the ring -- and NOT the member's placement: the junction is the
    patch CORNER the patch's two RING seams share, which does not depend on
    which patch carries the triangular member.

    HOW THE RING ANSWERS IT.  Each seam's boundary side names one coordinate
    of that corner: side `U0` / `U1` is the row at V = 0 / V = 1, side `V0`
    / `V1` the column at U = 0 / U = 1 (`SilkBlend.side_and_end`).  Two sides
    of DIFFERENT families therefore meet at exactly one patch corner, and
    this seam's along-axis end is the partner side's own number.

    Refused by name, never guessed:
      * `strip` is not one of `ring`'s seams -- there is no ring to read;
      * `patch` does not carry exactly two of the ring's seams;
      * both of the patch's ring seams run along the SAME axis, so the
        corner is not determined and BOTH ends are candidates -- the reason
        names them."""
    from SilkBlend import side_and_end
    tol = getattr(strip, "tolerance", 0.01) if tol is None else tol
    ring = list(ring or [])
    strip_name = getattr(strip, "Name", "?")
    patch_name = getattr(patch, "Name", "?")
    if not any(s is strip for s in ring):
        return None, ("seam %s is not one of this ring's seams, so the ring "
                      "cannot say which end of its axis its junction is at"
                      % strip_name)
    e, _ss = side_and_end(strip, patch, tol)
    if not e:
        return None, ("blend %s cannot say which side of %s it takes"
                      % (strip_name, patch_name))
    others = []
    for s in ring:
        if s is strip or patch not in (getattr(s, "PatchA", None),
                                       getattr(s, "PatchB", None)):
            continue
        ep, _ssp = side_and_end(s, patch, tol)
        if ep:
            others.append((s, ep))
    if len(others) != 1:
        return None, ("the ring carries %d seams of %s besides %s, and a "
                      "junction is one corner where exactly two meet"
                      % (len(others), patch_name, strip_name))
    partner, ep = others[0]
    if ep[0] == e[0]:
        return None, ("both ring seams of %s (%s on %s, %s on %s) run along "
                      "the same axis, so this seam's junction end is either "
                      "the 0 end or the 1 end of its %s axis and the ring "
                      "cannot say which"
                      % (patch_name, strip_name, e, partner.Name, ep, e[0]))
    return (0 if ep[1] == "0" else 1), None


def _seam_cut_home(strip, patch, leader, prop_of, tol=None, ring=None):
    """(property name, value to write, why) -- where THIS seam's rolling
    leader lives on `patch`, through the property naming `prop_of`.

    One arithmetic for both cuts: the leader is a fraction of the seam
    measured FROM THE JUNCTION CORNER, and a cut value is a position on the
    axis measured from the axis's own 0 end, so a junction at the 1 end
    mirrors the leader (`1 - leader`).  What differs between the two cuts is
    only the PROPERTY: the band edge (`SilkBlend.band_edge_prop`, the shipped
    construction's cut) or the leader cut (`SilkMachinery.leader_cut_prop`,
    the rolling construction's).

    `ring` is the corner's strips.  With it, the junction end is read off the
    ring (`seam_junction_end`) where the patch's own band edges cannot name
    one -- the owner's two-junctions-on-one-axis patches (#126).  Without it
    only the patch is read, which is every patch with one junction on the
    axis and refuses by name on the others.

    `None` (with the reason) when the seam cannot say which end of which
    axis carries it."""
    from SilkBlend import side_and_end
    from SilkMachinery import band_extent, seam_axis_roles
    tol = getattr(strip, "tolerance", 0.01) if tol is None else tol
    e, ss = side_and_end(strip, patch, tol)
    if not e:
        return None, None, ("blend %s cannot say which side of %s it takes"
                            % (strip.Name, patch.Name))
    end = None
    if ring is not None:
        end, why = seam_junction_end(strip, patch, ring, tol)
        if end is None:
            return None, None, why
    along_letter, _band_letter = seam_axis_roles(e)
    ext = band_extent(patch, e, ss, end)
    if ext[0] is None:
        return None, None, ext[1]
    corner_end = ext[2]
    value = float(leader) if corner_end == 0 else 1.0 - float(leader)
    return prop_of(along_letter, corner_end), value, None


def _leader_home(strip, patch, leader, tol=None, ring=None):
    """(property name, value to write, why) -- the patch property that
    carries the ROLLING LEADER of this seam in the SHIPPED construction:
    the BAND EDGE on the seam-PARALLEL axis, at the junction end.

    That is where the construction of before #119 cut, and it is still the
    home `apply_corner_choices` uses on a corner whose construction is
    `"shipped"` -- the leader must go where that construction reads it.
    The rolling construction writes the LEADER CUT instead
    (`_leader_cut_home`), which is the same arithmetic in a different
    property.  `ring` is `_seam_cut_home`'s (#126)."""
    from SilkBlend import band_edge_prop
    return _seam_cut_home(strip, patch, leader, band_edge_prop, tol, ring)


def _leader_cut_home(strip, patch, leader, tol=None, ring=None):
    """(property name, value to write, why) -- where the ROLLING
    construction's leader lives: the patch's LEADER CUT on the seam-parallel
    axis at the junction end (`ULeader1` / `ULeader2`).

    The band edge is left alone, so the SETBACK no longer rides along with
    the leader: the two are separate numbers on separate properties, which is
    the maintainer's own model (setback 1/16, leader 0.25).  `ring` is
    `_seam_cut_home`'s (#126)."""
    from SilkMachinery import leader_cut_prop
    return _seam_cut_home(strip, patch, leader, leader_cut_prop, tol, ring)


def _ring_of(strips):
    """The ring order of 3 or 4 strips, by name of the rule that applies.

    `(ordered, None)` or `(None, reason)`. One place, so a caller that only
    wants the ring's PATCHES cannot pick a different cycle from the one the
    corner builds."""
    from SilkMachinery import corner_ring, corner_ring_3
    strips = list(strips or [])
    if len(strips) == 3:
        return corner_ring_3(strips)
    if len(strips) == 4:
        return corner_ring(strips)
    return None, ("a corner ring is 3 or 4 blends (got %d)" % len(strips))


def corner_ring_patches(strips):
    """The RING's patches, in ring order, each once -- the set a corner's
    choices (the member's placement, the leader of each seam) are about.

    `(patches, None)` or `(None, reason)`."""
    ordered, why = _ring_of(strips)
    if ordered is None:
        return None, why
    patches = []
    for s in ordered:
        for p in (getattr(s, "PatchA", None), getattr(s, "PatchB", None)):
            if p is not None and p not in patches:
                patches.append(p)
    return patches, None


def seam_leader(strip, patch, tol=None, construction=None, ring=None):
    """`(leader, None)` or `(None, why)`: the rolling leader `patch`'s side
    of `strip` is cut at today.

    Read back through the SAME expression the writer uses, so what a panel
    shows is what the corner stage would write, expressed as a fraction of
    the seam measured from the junction corner.  WHICH expression depends on
    the construction, because the two constructions cut in different places:

      * `"rolling"` -- the patch's own LEADER CUT (`_leader_cut_home`), the
        cut the corner follows; a patch that carries none (every patch but
        the member's) reads (None, why), because that seam is not rolled;
      * `"shipped"` -- the BAND EDGE (`_leader_home`), which is where the
        construction of before #119 cut;
      * None (the default) reads whichever cut `patch` actually carries: a
        REAL leader cut when it has one (`ring_corner_gap` says whether the
        cut clears its band edge), else the band edge.  That is the reading
        for a corner whose construction was not recorded, and it cannot
        mistake one for the other: a corner does not carry both.

    `ring` is the corner's strips, handed to the same expression the writer
    uses (#126: a patch with two junctions on its along-seam axis can only be
    read with the ring)."""
    from SilkMachinery import band_edge
    construction = (str(construction) if construction is not None else None)
    if construction == "rolling":
        home = _leader_cut_home
    elif construction == "shipped":
        home = _leader_home
    else:
        home = _leader_cut_home if _has_leader_cut(patch) else _leader_home
    prop, sentinel, why = home(strip, patch, 0.0, tol, ring)
    if prop is None:
        return None, why
    stored = band_edge(getattr(patch, prop, 0.0) or 0.0)
    if stored is None:
        return None, ("%s.%s carries no cut" % (patch.Name, prop))
    # `sentinel` is what the home writes for a leader of 0: 0.0 when the
    # junction sits at the axis's 0 end, 1.0 when it sits at the 1 end
    # (the leader is then mirrored). It is the orientation of the value,
    # and the only thing that has to be undone here.
    return (stored if sentinel == 0.0 else 1.0 - stored), None


def _has_leader_cut(patch):
    """True when `patch` carries a leader cut that CLEARS its band edge --
    the rolling construction's own cut (`SilkMachinery.ring_corner_gap` is
    exactly that predicate, and it is the ring's loop rule besides)."""
    from SilkMachinery import ring_corner_gap
    return ring_corner_gap(patch) is not None


def apply_corner_choices(strips, pin=None, leaders=None):
    """Write the owner's corner CHOICES onto a corner that already exists.

    `pin` is `(ring patch or its Name, corner index 0..3)` -- where the
    triangular member is built (#117); `leaders` is
    `{blend or its Name: leader}`, the rolling leader per seam.

    WHERE A SEAM'S LEADER LANDS is the corner's CONSTRUCTION's answer
    (`SilkCorner.corner_construction`): the rolling construction cuts the
    member patch's own leader cut and CLEARS a cut left on a patch that is no
    longer the member's (a second cut on a patch that carries a ring pair
    splits the pair's shared corner), the shipped construction writes the
    band edge of both patches of the seam.  A seam the member patch does not
    touch has no cut under the rolling construction, and says so.

    The choices are properties of a BUILT corner (the member's placement and
    the ring's cut positions), so this refuses by name when the ring has no
    corner yet: it is the panel's Apply, not a second creation path -- the
    corner is built by `create_corner_blend`, which takes the same two
    choices and applies them itself.

    ATOMIC: every refusal (a patch outside the ring, a corner index outside
    0..3, a leader that is not a position inside its seam) is decided BEFORE
    the first write, so a half-applied corner is not expressible.

    Returns (corner, None) or (None, reason)."""
    doc = FreeCAD.ActiveDocument
    ordered, why = _ring_of(strips)
    if ordered is None:
        return None, why
    corner = _existing_corner_blend(doc, ordered)
    if corner is None:
        return None, ("this ring has no corner yet -- build it first (the "
                      "corner stage takes the member's placement and the "
                      "leaders when it builds)")
    patches, why = corner_ring_patches(ordered)
    if patches is None:
        return None, why
    from SilkCorner import corner_construction
    construction, _cnote = corner_construction(corner)
    plan = []
    target = None
    if pin is not None:
        from SilkCorner import ensure_member_pin, resolve_member_pin
        target, why = resolve_member_pin(pin, patches)
        if target is None:
            return None, why
        ensure_member_pin(corner)
    # WHERE THE LEADERS GO depends on the construction (`seam_leader` reads
    # back through the same two expressions):
    #   rolling -- the member patch's own LEADER CUT, for the seams OF that
    #              patch, and no cut anywhere else (a second cut on a patch
    #              that carries a ring PAIR splits that pair's shared corner
    #              in two, so a cut left behind on a patch that is no longer
    #              the member's is CLEARED here);
    #   shipped -- the BAND EDGE of both patches of the seam, which is where
    #              the construction of before #119 cuts.
    member_patch = None
    if construction == CORNER_CONSTRUCTION_ROLLING:
        member_patch = target[0] if target is not None else None
        if member_patch is None:
            member_patch = getattr(corner, "MemberPatch", None)
        if member_patch is None:
            from SilkCorner import corner_member_pin, CORNER_DEFAULT_TOL
            found, _why = corner_member_pin(ordered, CORNER_DEFAULT_TOL)
            member_patch = found[0] if found is not None else None
        if member_patch is None:
            return None, ("the rolling corner cannot place its leader: no "
                          "patch of this ring carries the triangular "
                          "member")
        from SilkMachinery import NO_LEADER_1, NO_LEADER_2, leader_cut_prop
        for p in patches:
            if p is member_patch:
                continue
            for letter in ("U", "V"):
                for end, sentinel in ((0, NO_LEADER_1), (1, NO_LEADER_2)):
                    prop = leader_cut_prop(letter, end)
                    if abs(float(getattr(p, prop, sentinel) or sentinel)
                           - sentinel) < 1e-12:
                        continue
                    plan.append((p, prop, sentinel))
    seam_writes = []
    for ref, value in (leaders or {}).items():
        name = getattr(ref, "Name", None) or str(ref)
        strip = None
        for s in ordered:
            if s is ref or s.Name == name:
                strip = s
                break
        if strip is None:
            return None, ("the leader names seam %r, which is not part of "
                          "this ring (%s)"
                          % (name, ", ".join(s.Name for s in ordered)))
        try:
            value = float(value)
        except (TypeError, ValueError):
            return None, ("the leader for seam %s is %r, not a number"
                          % (strip.Name, value))
        if not 0.0 < value < 1.0:
            return None, ("the leader %g for seam %s is not a position inside "
                          "the seam curve (0, 1)" % (value, strip.Name))
        if construction == CORNER_CONSTRUCTION_ROLLING:
            if member_patch not in (getattr(strip, "PatchA", None),
                                    getattr(strip, "PatchB", None)):
                FreeCAD.Console.PrintMessage(
                    "Silk: seam %s is not one of %s's seams, so its leader "
                    "is not used (the rolling cut lives on the patch that "
                    "carries the triangular member)\n"
                    % (strip.Name, member_patch.Name))
                continue
            prop, write, why = _leader_cut_home(strip, member_patch, value,
                                               ring=ordered)
            if prop is None:
                return None, ("seam %s: %s" % (strip.Name, why))
            if abs(float(getattr(member_patch, prop, 0.0) or 0.0) - write) \
                    < 1e-12:
                seam_writes.append((strip.Name, value))
                continue
            plan.append((member_patch, prop, write))
            seam_writes.append((strip.Name, value))
            continue
        for p in (getattr(strip, "PatchA", None),
                  getattr(strip, "PatchB", None)):
            if p is None:
                continue
            prop, write, why = _leader_home(strip, p, value, ring=ordered)
            if prop is None:
                return None, ("seam %s: %s" % (strip.Name, why))
            if abs(float(getattr(p, prop, 0.0) or 0.0) - write) < 1e-12:
                continue
            plan.append((p, prop, write))
        seam_writes.append((strip.Name, value))
    if construction == CORNER_CONSTRUCTION_ROLLING:
        # The same condition the corner stage refuses on, decided BEFORE the
        # first write: a leader that does not cut the member's cell back on
        # both axes leaves a 6x6 with coincident poles (or a refusal deeper
        # down), and Apply must not be a way around it.
        why = _member_cell_cut_problem(
            member_patch, [(p, prop, None, write) for p, prop, write in plan])
        if why is not None:
            return None, ("the rolling leader cannot cut the member's cell: "
                          "%s" % why)
    if not plan and target is None:
        return corner, None
    for p, prop, write in plan:
        setattr(p, prop, write)
    if target is not None:
        corner.MemberPatch = target[0]
        corner.MemberCorner = int(target[1])
    doc.recompute()
    doc.recompute()
    for strip_name, value in seam_writes:
        FreeCAD.Console.PrintMessage(
            "Silk: seam %s is rolled at leader %g\n" % (strip_name, value))
    if target is not None:
        FreeCAD.Console.PrintMessage(
            "Silk: the triangular member is pinned to %s[%d]\n"
            % (target[0].Name, target[1]))
    return corner, None


def _existing_rolling_member(doc, strips):
    """The RollingMemberFace already built on exactly this strip SET, or
    None (#119: the rolling corner is idempotent -- a second ask must not
    leave a second member and a second fill in the tree)."""
    want = {id(s) for s in strips}
    for o in doc.Objects:
        if getattr(o, "object_type", None) != "RollingMemberFace":
            continue
        have = list(getattr(o, "Strips", []) or [])
        if len(have) == len(strips) and {id(s) for s in have} == want:
            return o
    return None


def _existing_member_fill(doc, member):
    """The `Surface::Filling` already built over `member`'s boundary
    edges, or None."""
    for o in doc.Objects:
        if getattr(o, "TypeId", "") != "Surface::Filling":
            continue
        for entry in (getattr(o, "BoundaryEdges", None) or []):
            if entry and entry[0] is member:
                return o
    return None


def _face_junction_c0(face_obj, corner, n=41):
    """The C0 residual (mm) where `face_obj`'s boundary meets `corner`'s
    surface: the worst distance from a sampled point of the face's
    boundary to the corner's shape.

    None when either shape is missing.  This is the "do the two surfaces
    still MEET" number of the rolling corner's member face (#119).
    """
    import Part
    shape = getattr(face_obj, "Shape", None)
    other = getattr(corner, "Shape", None)
    if shape is None or other is None or not shape.Edges:
        return None
    worst = 0.0
    for e in shape.Edges:
        for i in range(n + 1):
            t = i / float(n)
            p = e.valueAt(e.FirstParameter
                          + t * (e.LastParameter - e.FirstParameter))
            worst = max(worst, other.distToShape(Part.Vertex(p))[0])
    return worst


def create_rolling_corner_66(strips, patch, leader=ROLLING_LEADER, seams=None,
                              order=1, name="Rolling66",
                              member_face=MEMBER_FACE_DEFAULT,
                              member_leaders=None,
                              pin=None, corner_name=None):
    """PATH (A) -- THE ROLLING CORNER: the corner fill (Silk's own 66)
    whose boundary sits AT THE LEADER, plus the small triangular surface
    the maintainer's file carries beside it.

    `strips` are the ring's three (or four) blends; `patch` the
    pinned patch whose corner carries the member.  `leader` is the
    fraction of the seam curve's own parameter, measured from the
    junction corner -- the SAME parameter space as `create_split_blend`
    and `create_rolling_triangle` use.

    `seams` are the strips whose seam is rolled (default: the two the
    pinned patch carries).  The leader is written into the band edge
    that carries it -- on BOTH patches of the seam, because the seam's
    cut is one curve -- and the patches re-cut their base surfaces
    there.  The ring strips, the corner fill (the 66) and the member
    are then rebuilt from those cut cells.

    The SMALL TRIANGULAR SURFACE is the maintainer's second surface, and
    its face is a `CubicSurface_64` over the member net by DEFAULT -- the
    same construction his file stores (#119 follow-up). `member_face`
    selects it:

      "cubicsurface64"  the member's own `CubicSurface_64` is the tri's
                        face (the default); the member is VISIBLE and no
                        FreeCAD fill is built.
      "fill"            the owner's replacement of that surface: a FreeCAD
                        `Surface::Filling` over the member's three real
                        edges, built through the shipped `create_fill`
                        (#96, with #121's selectable C0 fallback). The silk
                        member that carries the fill's boundary edges is
                        kept, hidden, because the boundary edges live on it
                        -- and so is the 64 face behind it, which is what
                        the fill is measured against.

    `member_leaders` is the leader PER SEAM: a `{blend or its Name: leader}`
    mapping. A seam it does not name is rolled at `leader` when `seams`
    selects it. Both are written through the SAME property
    (`_leader_home`), so a seam's leader is one number however it arrived.

    `pin` is the optional triangular-member placement (#117), handed to
    the corner's own derivation so the 66 and the member cannot disagree
    about where the member is.  `corner_name` names the corner object
    itself (the default is `name + "Corner"`).

    Returns a dict:
      {'corner': the CornerBlend, 'member': the small triangular
       surface, 'member_fill': the FreeCAD filling over it (or None -- and
       None whenever `member_face` is not "fill"),
       'member_fill_gap': the fill's measured tangent-plane gap (or
       None), 'member_junction_c0': the C0 residual where the member's
       face meets the 66 (mm, or None), 'member_face': which face was
       built, 'leader': the leader, 'rolled': the strips whose seam was
       rolled}
    or None when the selection is not a ring around the pinned patch."""
    from SilkCorner import (CornerBlend, CornerBlendViewProvider,
                             RollingMemberFace, RollingMemberFaceViewProvider,
                             corner_inputs, CORNER_DEFAULT_TOL)
    doc = FreeCAD.ActiveDocument
    if len(strips) == 1 and isinstance(strips[0], (list, tuple)):
        strips = list(strips[0])
    strips = [s for s in (strips or []) if s is not None]
    if len(strips) not in (3, 4):
        FreeCAD.Console.PrintError(
            "Silk: the rolling corner needs the ring's 3 or 4 blends "
            "(got %d). Nothing was created.\n" % len(strips))
        return None
    if len(strips) == 4:
        # THE ROLLING CUT LIVES ON THE MEMBER PATCH, and a 4-valent ring has
        # no member: its fourth side is a real blend.  The cut cannot go
        # anywhere else either -- a second cut on a patch that carries a ring
        # PAIR splits that pair's shared corner in two, so the four strips
        # would stop meeting (`SilkMachinery.ring_corner_gap`).  A 4-valent
        # ring therefore takes the shipped construction, and this says so
        # rather than cutting a cell the ring cannot close around.
        FreeCAD.Console.PrintError(
            "Silk: the rolling corner is a 3-valent construction -- its cut "
            "lives on the patch that carries the triangular member -- and "
            "this ring has 4 strips. Nothing was created; a 4-valent corner "
            "takes the shipped construction.\n")
        return None
    if patch is None:
        FreeCAD.Console.PrintError(
            "Silk: the rolling corner needs the pinned patch (the one whose "
            "corner carries the triangular surface). Nothing was created.\n")
        return None
    leader = float(leader)
    if not 0.0 < leader < 1.0:
        FreeCAD.Console.PrintError(
            "Silk: the rolling leader %g is not a position inside the seam "
            "curve (0, 1). Nothing was created.\n" % leader)
        return None
    on_patch = [s for s in strips
                if getattr(s, "PatchA", None) is patch
                or getattr(s, "PatchB", None) is patch]
    roll = [s for s in (seams if seams is not None else on_patch)
            if s in strips]
    if not roll:
        FreeCAD.Console.PrintError(
            "Silk: the rolling corner has no seam to roll (the selection "
            "holds no strip of this ring). Nothing was created.\n")
        return None
    member_face = str(member_face)
    if member_face not in MEMBER_FACES:
        FreeCAD.Console.PrintError(
            "Silk: the triangular member's face must be %s -- got %r. "
            "Nothing was created.\n"
            % (" or ".join(repr(f) for f in MEMBER_FACES), member_face))
        return None
    # the leader PER SEAM: a seam named here is rolled at ITS own leader, a
    # seam named only by `seams` at `leader`. Resolved before anything is
    # written, so a bad value refuses with the model untouched.
    per_seam = {}
    for ref, value in (member_leaders or {}).items():
        name = getattr(ref, "Name", None) or str(ref)
        strip = None
        for s in strips:
            if s is ref or s.Name == name:
                strip = s
                break
        if strip is None:
            FreeCAD.Console.PrintError(
                "Silk: the rolling leader names seam %r, which is not part of "
                "this ring (%s). Nothing was created.\n"
                % (name, ", ".join(s.Name for s in strips)))
            return None
        try:
            per_seam[strip.Name] = float(value)
        except (TypeError, ValueError):
            FreeCAD.Console.PrintError(
                "Silk: the rolling leader for seam %s is %r, not a number. "
                "Nothing was created.\n" % (strip.Name, value))
            return None
        if not 0.0 < per_seam[strip.Name] < 1.0:
            FreeCAD.Console.PrintError(
                "Silk: the rolling leader %g for seam %s is not a position "
                "inside the seam curve (0, 1). Nothing was created.\n"
                % (per_seam[strip.Name], strip.Name))
            return None
    roll = [s for s in strips if s.Name in per_seam] + \
           [s for s in roll if s.Name not in per_seam]
    # A seam the member patch does not touch has no cut to write: the rolling
    # leader is a cut of the MEMBER PATCH's cell, and the other patches keep
    # one cut per axis end (their two strips have to meet at one point).
    # Said out loud rather than dropped, so a caller that named such a seam
    # learns why its leader did not land.
    for s in roll:
        if patch in (getattr(s, "PatchA", None), getattr(s, "PatchB", None)):
            continue
        FreeCAD.Console.PrintMessage(
            "Silk: seam %s is not one of %s's seams, so its rolling leader "
            "is not used (the cut lives on the patch that carries the "
            "triangular member).\n" % (s.Name, getattr(patch, "Name", "?")))
    # the RING contract, BEFORE the cut: a selection that is not a ring
    # around one junction is refused by name, and the patches' band
    # edges are not written either (the cut is a change to the user's
    # model, so it must not happen to a selection that cannot become a
    # corner).
    if len(strips) == 3:
        from SilkMachinery import corner_ring_3
        _ordered, ring_why = corner_ring_3(strips)
    else:
        from SilkMachinery import corner_ring
        _ordered, ring_why = corner_ring(strips)
    if _ordered is None:
        FreeCAD.Console.PrintError(
            "Silk: the rolling corner cannot be built on these %d blends -- "
            "%s. Nothing was created.\n" % (len(strips), ring_why))
        return None

    # 1. the CUT: the member patch's own LEADER CUT, one per seam of that
    #    patch, at the junction end of the seam's axis.  The band edges are
    #    NOT touched -- the setback is the user's, and the leader is its own
    #    number -- and no other patch of the ring is cut (only the member
    #    patch may carry two cuts; a second cut on a patch that carries a
    #    ring PAIR splits that pair's shared corner in two).
    #
    #    ATOMIC: the writes are PLANNED first and only then applied, so
    #    a refusal ("the band on this patch has two corner cells on its
    #    U axis, so it does not reach exactly one junction corner")
    #    leaves the user's model exactly as it was -- the corner stage
    #    falls back to the shipped construction, and that fallback must
    #    be the shipped corner, byte for byte.
    planned = []
    for s in roll:
        if patch not in (getattr(s, "PatchA", None),
                         getattr(s, "PatchB", None)):
            continue
        seam_leader = per_seam.get(s.Name, leader)
        prop, value, why = _leader_cut_home(s, patch, seam_leader,
                                            ring=strips)
        if prop is None:
            FreeCAD.Console.PrintError(
                "Silk: the rolling leader cannot be placed: %s. The "
                "rolling construction was not built.\n" % why)
            return None
        cur = float(getattr(patch, prop, 0.0) or 0.0)
        if abs(cur - value) < 1e-12:
            continue
        planned.append((patch, prop, cur, value))
    # THE CELL MUST BE CUT BACK ON BOTH AXES.  The member's real row runs
    # between the two ring corners, which are that cell's two MIXED corners:
    # `(leader, setback)` and `(setback, leader)`.  With the leader on ONE
    # axis only, the row's two ends are not the ring's two corners, and the
    # assembly either refuses or comes out DEGENERATE -- measured on the cube
    # corner with a leader of 0.1 on one axis only (i.e. resting on the
    # 0.1 setback): 4 coincident pole pairs.  Decided BEFORE the write, so a
    # refused rolling corner leaves the model as it was.
    why = _member_cell_cut_problem(patch, planned)
    if why is not None:
        FreeCAD.Console.PrintError(
            "Silk: the rolling leader cannot cut the member's cell: %s. The "
            "rolling construction was not built.\n" % why)
        return None
    written = []
    for p, prop, cur, value in planned:
        setattr(p, prop, value)
        written.append((p.Name, prop, cur, value))
    if written:
        doc.recompute()
        doc.recompute()
    for pname, prop, old, new in written:
        FreeCAD.Console.PrintMessage(
            "Silk: the rolling leader moved %s.%s from %g to %g (the member "
            "patch's own cut, measured from the junction corner; the band "
            "edge stays the setback)\n"
            % (pname, prop, old, new))

    def _undo_cut():
        """Put the cut back: the rolling corner did not build, so the
        user's model must not keep the leader."""
        for p, prop, cur, _value in planned:
            try:
                setattr(p, prop, cur)
            except Exception:
                pass
        if planned:
            doc.recompute()
            doc.recompute()

    # 2. the corner fill: the 66 chain, fed with the ring's cut cells.
    grids, _cells, why = corner_inputs(strips, CORNER_DEFAULT_TOL, pin)
    if grids is None:
        _undo_cut()
        FreeCAD.Console.PrintError(
            "Silk: the rolling corner cannot be built on these %d blends -- "
            "%s. Nothing was created.\n" % (len(strips), why))
        return None
    existing = _existing_corner_blend(doc, strips)
    if existing is not None:
        corner = existing
    else:
        if len(strips) == 3:
            from SilkMachinery import corner_ring_3
            ordered, _why = corner_ring_3(strips)
        else:
            from SilkMachinery import corner_ring
            ordered, _why = corner_ring(strips)
        corner = doc.addObject("Part::FeaturePython",
                                corner_name or (name + "Corner"))
        CornerBlend(corner, ordered)
        CornerBlendViewProvider(corner.ViewObject)
        corner.ViewObject.LineWidth = 1.50
        corner.ViewObject.LineColor = (1.00, 0.67, 0.00)
        corner.ViewObject.PointSize = 4.00
        corner.ViewObject.DisplayMode = "Flat Lines"
        corner.ViewObject.ShapeColor = (1.00, 0.67, 0.00)
        corner.ViewObject.Transparency = 30
        doc.recompute()


    # 3. the SMALL TRIANGULAR SURFACE beside it (the maintainer's own
    #    second surface), and the owner's FreeCAD replacement of it.
    # A 4-valent ring has FOUR blends and no triangular member -- there
    # is nothing to put beside the 66 -- so the member face is a 3-valent
    # thing only.
    member = None
    if len(strips) == 3:
        member = _existing_rolling_member(doc, strips)
        if member is None:
            member = doc.addObject("Part::FeaturePython", name + "Member")
            RollingMemberFace(member, strips, corner)
            RollingMemberFaceViewProvider(member.ViewObject)
            member.ViewObject.ShapeColor = (0.20, 0.45, 0.95)
            member.ViewObject.Transparency = 0
            doc.recompute()
    member_fill = None
    member_fill_gap = None
    member_junction_c0 = None
    # WHICH SURFACE IS THE TRI (#119 follow-up): its own `CubicSurface_64`
    # (the construction the maintainer's file stores) by default, the
    # FreeCAD fill when asked for. The two are mutually exclusive on screen:
    # exactly one of them is visible, so the corner never shows two faces in
    # one place.
    if member is not None:
        try:
            member.ViewObject.Visibility = (member_face
                                            == MEMBER_FACE_CUBICSURFACE64)
        except Exception:
            pass
    if (member_face == MEMBER_FACE_FILL and member is not None
            and member.Shape and member.Shape.Edges):
        # The member's COLLAPSED row is a DEGENERATE edge (its two ends
        # are the apex), so it is not a boundary curve a fill can take:
        # the fill's boundary is the member's own three REAL edges (the
        # two leader lines and the chord across the corner), which DO
        # close a loop.  The member publishes their sub-shape NAMES
        # (`BoundaryEdges`): they are the names of the compound's own
        # children, and a compound's children are named BY POSITION, so
        # they survive the shape replacement that a band-edge edit
        # causes (see `SilkCorner.RollingMemberFace`).
        names = list(getattr(member, "BoundaryEdges", None) or [])
        if len(names) < 3:
            names = ["Edge%d" % (i + 1) for i, e in
                     enumerate(member.Shape.Edges) if e.Length > 1e-9]
        real = [(member, name) for name in names]
        if len(real) >= 3:
            member_fill = _existing_member_fill(doc, member)
            if member_fill is None:
                # the SHIPPED fill component (#96), with #121's SELECTABLE
                # C0 fallback: a boundary that cannot carry the requested
                # continuity order still gets a C0 fill, which meets the
                # boundary exactly.
                member_fill = create_fill(real, faces=["Face1"] * len(real),
                                          order=order, fallback_order=0,
                                          name=name + "MemberFill")
            if member_fill is not None:
                # THE MEMBER'S FACE IS THE FILL NOW (#119, stage 1): the
                # silk member is kept -- it carries the fill's boundary
                # edges -- but hidden, so the spiderweb is not what the
                # eye sees.
                try:
                    member.ViewObject.Visibility = False
                except Exception:
                    pass
                # the member keeps the fill, so it can re-point the
                # fill's boundary when its own shape is replaced
                # (SilkCorner.RollingMemberFace._refresh_fill).  The
                # member does NOT link to the fill: a link would make
                # the member depend on the fill while the fill depends
                # on the member -- a cycle (see `SilkCorner.fill_of_member`).
                # and the continuity the fill REACHED, measured by the
                # shipped instrument against the face it replaces
                member_fill_gap = fill_normal_gap(member_fill, real,
                                                  ["Face1"] * len(real))
                # and the C0 where the member's face meets the 66
                member_junction_c0 = _face_junction_c0(member_fill, corner)
    elif member is not None:
        # the 64 IS the tri's face: an existing fill for this member (from
        # an earlier "fill" build) is hidden rather than deleted -- the
        # switch must be reversible, and the fill is not ours to destroy.
        stale = _existing_member_fill(doc, member)
        if stale is not None:
            try:
                stale.ViewObject.Visibility = False
            except Exception:
                pass
    return {"corner": corner, "member": member, "member_fill": member_fill,
            "member_fill_gap": member_fill_gap,
            "member_junction_c0": member_junction_c0,
            "member_face": member_face if member is not None else None,
            "leader": leader, "rolled": [s.Name for s in roll],
            "written": written}


# ---- the corner fill (#96) ------------------------------------------------
#
# The owner's ask: fill a whole corner with ONE patch and judge it by eye.
# `Surface::Filling` is a FOREIGN object -- outside Silk's band/split
# machinery and outside its restore and regression coverage -- so it stays
# opt-in and is only built when the user asks for it (ADR-0005, "Reversal,
# and its narrowing").
#
# Measured on this build (docs/research/silk-fill-picking.md): the fill takes
# the ring strips' own `EdgeN` boundary rows DIRECTLY -- no throwaway
# `Part::Feature` carriers, so it stays live-linked to the strips -- and
# returns one valid face at order 0/1/2 with `distToShape` boundary residual
# 0.0 mm. The manual Surface-workbench path now works too: `create_blend`
# draws the strips Flat Lines, so their boundary edges are pickable (the same
# measurement is what made Shaded untenable). This command stays because it is
# the exact path, with the ring contract checked and named BEHIND it.

# `Surface::Filling.BoundaryOrder`: 0 = C0, 1 = G1, 2 = G2. >= 3 is refused by
# FreeCAD ("BRepFill : The continuity is not G0 G1 or G2").
CORNER_FILL_ORDERS = (0, 1, 2)

# How far the fill's own surface may sit from a boundary edge it claims. A
# sound fill CONTAINS its boundary (residual 0.0 mm by construction, measured
# at every order); the over-constrained raw-patch feed measured 0.59-7.3 mm
# AND an invalid face (docs/research/silk-fill-picking.md). This gate is the
# second belt behind the validity check.
FILL_CONTACT_TOL = 1e-3

# The fill's continuity INSTRUMENT: the TANGENT-PLANE GAP ("normal gap")
# between the fill's own surface and the SUPPORT surface it claims along
# the boundary -- the one continuity quantity a fill can be judged by here.
# It is a G1 metric (the two tangent planes agree); it is NOT a G2 one and
# cannot be: `g1_deg` cannot establish G2 (AGENTS.md, #97).
#
# The METHOD is the one the MANUAL probe `Tests/g2_corner_fill_probe.py`
# used, moved here so that there is exactly ONE implementation of it: the
# probe imports these two functions. The algorithm is unchanged, so the
# probe's published readings still stand.
#
# ERROR FLOOR. `solve_uv`'s own floor, published by #97's calibration
# (`Tests/continuity_calibration.py::sample_solve_uv`, at the grid this
# oracle uses): 4.5e-13 mm of position residual. The shipped test also
# reads the ZERO CONTROL -- the fill's surface measured against ITSELF --
# and reports it raw, so the floor is a measurement in the suite and not a
# number quoted from a doc.
#
# MEASURED (FreeCAD 1.1.3 / OCCT 7.9, the `Tests/corner_model.py` fixture
# -- docs/research/freecad-corner-fill-g2-measurement.md), the strip feed:
#     order 0 (C0)   1.86 - 4.29 deg   (C0 by design)
#     order 1 (G1)   0.087 - 0.155 deg
#     order 2        0.164 - 0.483 deg
# The bar below sits ABOVE the measured G1/G2 readings and BELOW the
# measured C0 one, so a fill that came out C0 can never pass a request for
# G1 -- which is the whole point of measuring the order instead of trusting
# the requested one.
FILL_NORMAL_GAP_TOL_DEG = 1.0

# The grid the shipped oracle solves the boundary points with. 30 is the
# grid #97's calibration measured the 4.5e-13 mm floor at.
FILL_NORMAL_GAP_GRID = 30

# The stations per boundary edge the gap is read at. 11 is the probe's own
# sampling (k/10), so the shipped numbers stay comparable with it.
FILL_NORMAL_GAP_STATIONS = 11


def _row_edge_subname(shape, row, tol=1e-6):
    """("EdgeN", None) for the one edge of `shape` a Bezier boundary ROW
    spans, or (None, reason).

    A cubic's end points ARE its end poles, so the junction-end row of a
    strip's 24-pole grid names that strip's own boundary edge by comparing
    endpoints -- the row is usually the row-reversed or column-flipped copy
    `orient_junction_row` / `_orient_ring_columns` produced, so both orders
    are matched. Nothing is assumed about which of the four it is.
    """
    ea, eb = row[0], row[-1]
    hits = []
    for i, e in enumerate(shape.Edges):
        fa = e.valueAt(e.FirstParameter)
        fb = e.valueAt(e.LastParameter)
        if (((fa - ea).Length < tol and (fb - eb).Length < tol)
                or ((fa - eb).Length < tol and (fb - ea).Length < tol)):
            hits.append("Edge%d" % (i + 1))
    if len(hits) == 1:
        return hits[0], None
    if not hits:
        return None, "it has no boundary edge on the junction row"
    return None, "it has %d boundary edges on the junction row" % len(hits)


def corner_fill_boundary(strips, tol=None):
    """((links, faces), None) or (None, reason) -- the hole the RING closes.

    `links` is `[(strip, "EdgeN"), ...]` in ring order and `faces` the
    matching per-edge support faces ("Face1": the strip's own surface) --
    exactly the wiring `Surface::Filling` takes. Pure: no object, no
    document, no console.

    The ring contract is `SilkCorner.corner_inputs`, the SAME one the corner
    blend is built on, so a selection that is not a ring of 3 or 4 strips
    around one junction is refused by NAME here, before anything is built.
    The junction-end rows come from it too: `orient_junction_row` leaves the
    ring's corner row at V = 3, so it is poles 18..23 of each grid.

    A triangular corner's synthetic 4th member is not a strip and carries no
    boundary edge, so a grid that matches no strip is skipped: the ring's own
    three strips bound that hole. A row that matches MORE than one strip, or
    a ring whose rows cannot all be named, is refused.
    """
    from SilkCorner import corner_inputs, CORNER_DEFAULT_TOL
    tol = CORNER_DEFAULT_TOL if tol is None else tol
    if len(strips) == 1 and isinstance(strips[0], (list, tuple)):
        strips = list(strips[0])
    strips = [s for s in (strips or []) if s is not None]
    grids, _cells, why = corner_inputs(strips, tol)
    if grids is None:
        return None, why
    links, faces = [], []
    for grid in grids:
        poles = grid[0] if isinstance(grid, tuple) else grid
        row = list(poles)[18:24]
        matched = []
        for s in strips:
            subname, _why = _row_edge_subname(s.Shape, row)
            if subname is not None:
                matched.append((s, subname))
        if not matched:
            continue        # the 3-valent ring's synthetic member
        if len(matched) > 1:
            return None, ("the corner's junction row cannot be attributed to "
                          "one strip (%s)"
                          % ", ".join(s.Name for s, _n in matched))
        links.append(matched[0])
        faces.append("Face1")
    if len(links) != len(strips):
        return None, ("only %d of the ring's %d strips carry a junction "
                      "boundary edge" % (len(links), len(strips)))
    return (links, faces), None


class _BoundaryLink:
    """One `(object, "EdgeN")` fill boundary link, shaped so
    `SilkMachinery.loop_order` can order it (#66/#68).

    `loop_order` reads a candidate's two endpoints from `Poles`; a fill
    boundary link is a SUB-SHAPE of an object (that is what
    `Surface::Filling.BoundaryEdges` takes), so the two curve endpoints are
    what it gets. One adapter, so the ordering rule and its refusal
    diagnosis are Silk's own, not a second implementation of them.
    """

    def __init__(self, obj, subname):
        self.obj = obj
        self.subname = subname
        self.Name = "%s.%s" % (obj.Name, subname)
        self.Label = self.Name
        edge = obj.Shape.getElement(subname)
        self.Poles = [edge.valueAt(edge.FirstParameter),
                      edge.valueAt(edge.LastParameter)]


def fill_boundary_loop(links, tol=None):
    """((ordered links, None)) or (None, reason) -- `links` as ONE closed
    loop of boundary edges.

    The fill's boundary is ordered BY CONNECTIVITY, never by click order:
    `SilkMachinery.loop_order` owns that rule and the #68 "a loop corner
    meets exactly 2" proof behind it, so a boundary whose edges branch,
    pinch, do not close, or form two loops is refused with the same named
    diagnosis a Patch gives -- and a boundary that is already cyclic comes
    back exactly as it arrived.
    """
    links = list(links or [])
    order, problem = loop_order(
        [_BoundaryLink(o, s) for o, s in links], tol)
    if order is None:
        return None, problem
    return [(link.obj, link.subname) for link in order], None


def solve_uv(surf, point, prange, grid=120):
    """(u, v, residual) for `point` on `surf`, solved over `prange`.

    Coarse grid to bracket the nearest point, then a damped Newton on the
    two parameters.  `residual` is |surf.value(u, v) - point| -- the small
    number the caller wants, and the big number when `point` is not on
    the surface at all (which is exactly the over-constrained-feed
    evidence).

    Moved here from `Tests/g2_corner_fill_probe.py` (#121): the fill's
    continuity is now judged by the SHIPPED oracle, so the instrument
    lives with the code that uses it and the probe imports it -- one
    implementation, one floor.  The algorithm is unchanged.
    """
    u0, u1, v0, v1 = prange
    best = None
    for i in range(grid + 1):
        u = u0 + (u1 - u0) * i / grid
        for j in range(grid + 1):
            v = v0 + (v1 - v0) * j / grid
            d = (surf.value(u, v) - point).Length
            if best is None or d < best[0]:
                best = (d, u, v)
    u, v = best[1], best[2]
    for _ in range(80):
        r = surf.value(u, v) - point
        if r.Length < 1e-11:
            break
        h = 1e-6
        su = (surf.value(u + h, v) - surf.value(u - h, v)) / (2 * h)
        sv = (surf.value(u, v + h) - surf.value(u, v - h)) / (2 * h)
        a, b, c = su.dot(su), su.dot(sv), sv.dot(sv)
        d, e = su.dot(r), sv.dot(r)
        det = a * c - b * b
        if abs(det) < 1e-18:
            break
        u -= (c * d - b * e) / det
        v -= (a * e - b * d) / det
        u = min(u1, max(u0, u))
        v = min(v1, max(v0, v))
    return u, v, (surf.value(u, v) - point).Length


def normal_gap_deg(surf_a, ua, va, surf_b, ub, vb):
    """The angle (deg) between two surfaces' normals at two parameter
    points.

    The second normal is taken on the SAME SIDE (it is flipped when the
    raw dot product is negative), so the figure is the tangent-plane gap
    and never the 180 deg an opposed pair would read.
    """
    na = surf_a.normal(ua, va)
    nb = surf_b.normal(ub, vb)
    if na.Length < 1e-12 or nb.Length < 1e-12:
        return None
    na.normalize()
    nb.normalize()
    if na.dot(nb) < 0.0:
        nb = -1.0 * nb
    return math.degrees(math.acos(max(-1.0, min(1.0, na.dot(nb)))))


def _subname(sub):
    """The sub-shape name as a string ("Edge1"), from a name or a list."""
    if isinstance(sub, (list, tuple)):
        return sub[0] if sub else ""
    return sub


def _support_face(obj, name):
    """The support face of `obj` named `name`, or None.

    The fill's support faces are named on the object that OWNS the
    boundary edge ("Face1"), and that object's shape may be the face
    itself (a Silk strip's Shape is its surface) or a compound holding
    it -- both are resolved here, and a name that does not resolve is
    None rather than an exception.
    """
    shape = getattr(obj, "Shape", None)
    if shape is None or not name:
        return None
    if getattr(shape, "ShapeType", "") == "Face":
        return shape if name in ("Face1", "Face") else None
    try:
        face = shape.getElement(name)
    except Exception:
        face = None
    if face is None:
        faces = getattr(shape, "Faces", None) or []
        if not faces:
            return None
        face = faces[0]
    if getattr(face, "ShapeType", "") != "Face":
        faces = getattr(face, "Faces", None) or []
        if not faces:
            return None
        face = faces[0]
    return face


def fill_normal_gap(fill, links, faces=None, stations=None, grid=None):
    """The fill's TANGENT-PLANE GAP along the boundary it claims (deg).

    For every boundary edge the fill was given, the edge is sampled, each
    sample point is solved on the FILL's surface and on the SUPPORT
    surface, and the two normals at that point are compared -- the
    tangent-plane gap, the G1 metric.  The method is `solve_uv` (the
    probe's, moved here) plus `normal_gap_deg`; the error floor is
    `solve_uv`'s own (4.5e-13 mm, #97's calibration).

    A sample point where the fill does not pass through the boundary is
    SKIPPED, never counted as a zero gap: that is the difference between
    "no gap" and "no measurement".  Whether the fill contains its
    boundary at all is the C0 residual check's business
    (`corner_fill_problem`).

    An edge with NO support face has no surface to measure against: its
    gap is None and the whole measurement reads as not measurable.  That
    is the honest reading for a fill built over bare curves.

    Returns a dict:
      "measurable"   bool -- was there a station to measure at all
      "max_gap_deg"  float or None -- the worst gap over the boundary
      "per_edge"     list of {"label", "gap_deg", "residual",
                              "ref_residual", "stations", "reason"} -- one
                              per boundary edge, raw
      "reason"       None or why nothing could be measured
    """
    stations = FILL_NORMAL_GAP_STATIONS if stations is None else int(stations)
    grid = FILL_NORMAL_GAP_GRID if grid is None else int(grid)
    links = list(links or [])
    faces = list(faces or [])
    shape = getattr(fill, "Shape", None)
    per_edge = []
    if shape is None or not shape.Faces:
        return {"measurable": False, "max_gap_deg": None, "per_edge": [],
                "reason": "the fill produced no face"}
    face = shape.Faces[0]
    surf = face.Surface
    prange = face.ParameterRange
    worst = None
    for i, (obj, subname) in enumerate(links):
        label = "%s.%s" % (getattr(obj, "Name", "?"), _subname(subname))
        entry = {"label": label, "gap_deg": None, "residual": None,
                 "stations": 0, "reason": None}
        fname = faces[i] if i < len(faces) else None
        ref = _support_face(obj, fname)
        if ref is None:
            entry["reason"] = ("no support face was given" if not fname
                               else "the support face %r does not resolve"
                               % (fname,))
            per_edge.append(entry)
            continue
        rsurf = ref.Surface
        rrange = ref.ParameterRange
        edge = obj.Shape.getElement(_subname(subname))
        gap = None
        residual = 0.0
        ref_residual = 0.0
        used = 0
        for k in range(stations):
            t = (edge.FirstParameter
                 + (edge.LastParameter - edge.FirstParameter)
                 * k / float(max(1, stations - 1)))
            point = edge.valueAt(t)
            u, v, res = solve_uv(surf, point, prange, grid=grid)
            residual = max(residual, res)
            if res > FILL_CONTACT_TOL:
                continue      # the fill does not pass through this point
            ur, vr, rres = solve_uv(rsurf, point, rrange, grid=grid)
            ref_residual = max(ref_residual, rres)
            if rres > FILL_CONTACT_TOL:
                continue      # the point is not on the support surface
            g = normal_gap_deg(surf, u, v, rsurf, ur, vr)
            if g is None:
                continue
            gap = g if gap is None else max(gap, g)
            used += 1
        entry["gap_deg"] = gap
        entry["residual"] = residual
        entry["ref_residual"] = ref_residual
        entry["stations"] = used
        if gap is None:
            entry["reason"] = "no station could be measured"
        per_edge.append(entry)
        if gap is not None:
            worst = gap if worst is None else max(worst, gap)
    return {"measurable": worst is not None, "max_gap_deg": worst,
            "per_edge": per_edge,
            "reason": None if worst is not None
            else "no station on any boundary edge could be measured"}


def corner_fill_problem(fill, links, faces=None, order=None):
    """None when `fill` is a sound fill of `links`, else the reason.

    A fill must have a face, be a valid shape, and CONTAIN every boundary
    edge it was given -- the C0 check, and the reason an over-constrained
    boundary can never be left standing.

    With `order` given, the fill must ALSO have REACHED that continuity
    order: the tangent-plane gap along the boundary (`fill_normal_gap`)
    must be within `FILL_NORMAL_GAP_TOL_DEG`.  This is the check the
    requested order alone cannot make: FreeCAD accepts an order and can
    hand back a fill that did not reach it, and a C0 fill passes every
    C0 test (#121).  Order 0 (C0) asks for no tangent-plane continuity,
    so no gap bar applies to it.

    `faces` are the support faces (one per boundary edge).  Without them
    the gap cannot be measured and the order is NOT judged: the fill is
    then accepted on its C0 evidence alone, and the measurement report
    says so.
    """
    shape = fill.Shape
    if not shape.Faces:
        return "it produced no face"
    if not shape.isValid():
        return "the face is not a valid shape"
    for obj, subname in links:
        name = _subname(subname)
        distance = shape.distToShape(obj.Shape.getElement(name))[0]
        if distance > FILL_CONTACT_TOL:
            return ("it misses %s.%s by %.4g mm"
                    % (obj.Name, name, distance))
    if order is not None and int(order) >= 1:
        gap = fill_normal_gap(fill, links, faces)
        if gap["measurable"] and gap["max_gap_deg"] > FILL_NORMAL_GAP_TOL_DEG:
            return ("its tangent-plane gap along the boundary is %.3f deg, "
                    "above the %.1f deg bar for continuity order %d"
                    % (gap["max_gap_deg"], FILL_NORMAL_GAP_TOL_DEG,
                       int(order)))
    return None


def _order_problem(order):
    """The named reason an order cannot be built, or None.

    `BoundaryOrder` is FreeCAD's 0/1/2 and nothing else: >= 3 is refused by
    FreeCAD itself ("BRepFill : The continuity is not G0 G1 or G2"), so the
    honest answer is to refuse it here, before an object exists.

    This is only the FIRST gate, and it is about the VALUE, not about what
    the fill reaches: an order inside 0/1/2 is an order FreeCAD ACCEPTS,
    and FreeCAD may hand back a fill that did not reach it.  Whether the
    fill reached the order asked for is measured, not assumed --
    `corner_fill_problem` reads the tangent-plane gap (#121).
    """
    if order in CORNER_FILL_ORDERS:
        return None
    return ("the corner fill order must be 0 (C0), 1 (G1) or 2 (G2) -- "
            "got %r" % (order,))


def _build_fill(links, faces, order, name):
    """The shared build-and-validate tail of both fill entry points.

    (object, None) or (None, reason). The created object is FreeCAD's own,
    not a Silk one. A fill that produced no face, is invalid, misses its
    own boundary, or did not REACH the order it was asked for is REMOVED
    again before returning, so an invalid fill is never parked in the tree
    reading `State=Up-to-date` (#80/#83).
    """
    doc = FreeCAD.ActiveDocument
    try:
        obj = doc.addObject("Surface::Filling", name)
    except Exception as exc:
        # The Surface module is FreeCAD's, not ours: a build without it can
        # still run every other Silk path, so this refuses by name like any
        # other unusable input rather than raising.
        return None, ("this FreeCAD provides no Surface::Filling object "
                      "type (%s)" % (exc,))
    obj.BoundaryEdges = links
    obj.BoundaryFaces = faces
    obj.BoundaryOrder = [order] * len(links)
    doc.recompute()
    problem = corner_fill_problem(obj, links, faces, order)
    if problem is not None:
        doc.removeObject(obj.Name)
        doc.recompute()
        return None, problem
    return obj, None


def _fill_at_order(links, faces, order, name, fallback_order=None):
    """(object, why, used_order) -- the fill, or nothing.

    `why` is None when the fill built at the order that was asked for;
    otherwise it names the refusal (an order FreeCAD cannot take, or the
    oracle's verdict that the fill did not reach it) or the failure.
    `used_order` is the order the fill was actually built at.

    `fallback_order` is the SELECTABLE C0 fallback (#96: "offer the
    selectable C0 fallback where the requested order is refused"): the
    order to build at when the requested one is refused -- either because
    FreeCAD does not take that order at all, or because the oracle caught
    that the fill did not reach it.  None (the default) means NO
    fallback: the refusal stands and nothing is left in the tree, so a
    caller never gets a C0 fill it did not ask for.
    """
    problem = _order_problem(order)
    if problem is None:
        obj, problem = _build_fill(links, faces, order, name)
        if obj is not None:
            return obj, None, order
    if fallback_order is None:
        return None, problem, order
    bad = _order_problem(fallback_order)
    if bad is not None:
        return None, ("%s; the selected fallback order %r is not usable "
                      "either (%s)" % (problem, fallback_order, bad)), order
    obj, why = _build_fill(links, faces, fallback_order, name)
    if obj is None:
        return None, ("%s; the selected fallback at order %d did not build "
                      "either (%s)" % (problem, fallback_order, why)), order
    return obj, problem, fallback_order


def create_fill(links, faces=None, order=1, name="Surface",
                fallback_order=None):
    """Create ONE `Surface::Filling` over an EXPLICIT hole boundary (#96).

    `links` is the boundary as `[(object, "EdgeN"), ...]` -- the sub-shapes
    `Surface::Filling.BoundaryEdges` takes -- in ANY order: the loop is
    wired by connectivity (`fill_boundary_loop`), never by click order.
    `faces` is the matching per-edge support, defaulting to `Face1` (the
    sub-shape owner's own surface); one face per edge is required. An
    EMPTY list is the opt-in "no support face" (the boundary edges are
    then the whole input -- FreeCAD's filling builds a surface over the
    curves alone); it is what the rolling corner's triangle uses, whose
    three boundary edges live on a carrier object that has no face of
    its own. `order` is the fill's own continuity order (0 = C0, 1 = G1,
    2 = G2).

    Everything that can be checked is checked BEFORE anything is
    constructed: an order outside 0/1/2, or a boundary that is not ONE
    closed loop -- branched, pinched, open, over-constrained with a surplus
    edge -- is refused by name and leaves NO object in the tree. The build
    is then validated by the C0 boundary residual AND, for an order of 1
    or 2, by the TANGENT-PLANE GAP the fill actually reached
    (`corner_fill_problem`): the requested order alone is not evidence,
    because FreeCAD accepts an order it may not reach, and a C0 fill
    passes every C0 test (#121).

    `fallback_order` is the SELECTABLE C0 fallback (#96): the order to
    build at when the requested order is refused -- by FreeCAD's own order
    list, or by the oracle's verdict that the fill did not reach it. The
    default is None: NO fallback, so the refusal stands and nothing is
    left in the tree. When a fallback IS selected, the fallback build is
    reported by name, and the fill's own `BoundaryOrder` carries the order
    it was really built at.

    The corner's own collector is `corner_fill_boundary` (ring strips ->
    this same wiring), used by `create_corner_fill`.
    """
    if links and not isinstance(links[0], (list, tuple)):
        links = [links]     # one bare (object, "EdgeN") link
    links = [(o, s) for o, s in list(links or []) if o is not None and s]
    problem = _order_problem(order)
    if problem is not None and fallback_order is None:
        FreeCAD.Console.PrintError(
            "Silk: %s. Nothing was created.\n" % problem)
        return None
    ordered, problem = fill_boundary_loop(links)
    if ordered is None:
        FreeCAD.Console.PrintError(
            "Silk: cannot build the fill over these %d boundary edges -- "
            "%s. Nothing was created.\n" % (len(links), problem))
        return None
    faces = ["Face1"] * len(ordered) if faces is None else list(faces)
    if faces and len(faces) != len(ordered):
        FreeCAD.Console.PrintError(
            "Silk: the fill needs one support face per boundary edge (%d "
            "edges, %d faces). Nothing was created.\n"
            % (len(ordered), len(faces)))
        return None
    obj, why, used = _fill_at_order(ordered, faces, order, name,
                                    fallback_order)
    if obj is None:
        FreeCAD.Console.PrintError(
            "Silk: the surface fill over %d boundary edges did not build -- "
            "%s. Nothing was left in the tree.\n" % (len(ordered), why))
        return None
    if used != order:
        FreeCAD.Console.PrintMessage(
            "Silk: the fill at continuity order %d was refused (%s); the "
            "selected fallback built it at order %d.\n" % (order, why, used))
    FreeCAD.Console.PrintMessage(
        "Silk: surface fill %s created over %d boundary edges (order %d)\n"
        % (obj.Name, len(ordered), used))
    return obj


def create_corner_fill(*strips, order=1, name="Surface", fallback_order=None):
    """Create ONE `Surface::Filling` over the hole the corner's ring strips
    close (#96).

    `strips` are the ring Blend strips, in any order (or one list): three
    where three patches meet, four where four do -- the same selection
    `create_corner_blend` takes. `order` is the fill's own continuity order
    (0 = C0, 1 = G1, 2 = G2); the default is 1, the bar this workbench's own
    blends reach and the strongest of the three measured for this feed
    (order 2 is NOT G2 here and measures worse: docs/research/
    silk-corner-g2.md).

    Everything that can be checked is checked BEFORE anything is
    constructed: a selection that is not a ring around one junction, a ring
    whose junction rows cannot be named, or an order outside 0/1/2 is
    refused by name and leaves NO object in the tree. The build is then
    validated, and a fill that produced no face, is invalid, misses its own
    boundary, or did not REACH the order it was asked for is REMOVED again
    with a named refusal -- an invalid fill must never be parked in the
    tree reading `State=Up-to-date` (#80/#83).

    `fallback_order` is the SELECTABLE C0 fallback (#96): the order to
    build at when the requested order is refused. The default is None: NO
    fallback, so the refusal stands and nothing is left in the tree.

    The created object is FreeCAD's own, not a Silk one: it carries no band
    or split bookkeeping and no Silk view provider. GUI-free -- the command
    and the task panel wrap it in their own transaction.
    """
    if len(strips) == 1 and isinstance(strips[0], (list, tuple)):
        strips = list(strips[0])
    strips = [s for s in (strips or []) if s is not None]
    if len(strips) not in (3, 4):
        FreeCAD.Console.PrintError(
            "Silk: a corner fill needs the ring's 3 or 4 blends around "
            "one junction (got %d). Nothing was created.\n" % len(strips))
        return None
    bad_order = _order_problem(order)
    if bad_order is not None and fallback_order is None:
        FreeCAD.Console.PrintError(
            "Silk: %s. Nothing was created.\n" % bad_order)
        return None
    boundary, why = corner_fill_boundary(strips)
    if boundary is None:
        FreeCAD.Console.PrintError(
            "Silk: cannot build the corner fill over these %d blends -- %s. "
            "Nothing was created.\n" % (len(strips), why))
        return None
    links, faces = boundary
    obj, why, used = _fill_at_order(links, faces, order, name,
                                    fallback_order)
    if obj is None:
        FreeCAD.Console.PrintError(
            "Silk: the surface fill over %s did not build -- %s. Nothing was "
            "left in the tree.\n"
            % (", ".join(s.Name for s in strips), why))
        return None
    if used != order:
        FreeCAD.Console.PrintMessage(
            "Silk: the corner fill at continuity order %d was refused (%s); "
            "the selected fallback built it at order %d.\n"
            % (order, why, used))
    FreeCAD.Console.PrintMessage(
        "Silk: surface fill %s created over %s (order %d, %d boundary "
        "edges)\n"
        % (obj.Name, ", ".join(s.Name for s in strips), used, len(links)))
    return obj
