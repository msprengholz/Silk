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
    three or four blend strips, whatever order they were handed over in."""
    want = {id(s) for s in strips}
    for o in doc.Objects:
        if getattr(o, "object_type", None) != "CornerBlend":
            continue
        have = list(getattr(o, "Strips", []) or [])
        if len(have) == len(strips) and {id(s) for s in have} == want:
            return o
    return None


def create_corner_blend(*strips, name="CornerBlend", pin=None):
    """Create the CornerBlend filling the junction where 3 or 4 blend
    strips meet (#28; rebuilt on the subgrid chain in #91).

    `strips` are the ring Blend strips, in any order (or one list): three
    where three patches meet (the triangular 4th member is built
    invisibly), four where four do.
    `pin` is the optional triangular-member placement (#117):
    `(ring patch, corner index 0..3)`, the corner the member must be
    built at; None leaves the automatic search in charge.
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
    doc.recompute()
    return obj


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

ROLLING_LEADER = 0.25          # the video's number: 0.25 / 0.75


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

    `strips` are the ring's three blend strips, `patch` the PINNED patch
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
            "Silk: the rolling corner needs the ring's 3 blend strips (got "
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


def corner_fill_problem(fill, links):
    """None when `fill` is a sound fill of `links`, else the reason.

    A fill must have a face, be a valid shape, and CONTAIN every boundary
    edge it was given -- the C0 check, and the reason an over-constrained
    boundary can never be left standing.
    """
    shape = fill.Shape
    if not shape.Faces:
        return "it produced no face"
    if not shape.isValid():
        return "the face is not a valid shape"
    for obj, subname in links:
        distance = shape.distToShape(obj.Shape.getElement(subname))[0]
        if distance > FILL_CONTACT_TOL:
            return ("it misses %s.%s by %.4g mm"
                    % (obj.Name, subname, distance))
    return None


def _order_problem(order):
    """The named reason an order cannot be built, or None.

    `BoundaryOrder` is FreeCAD's 0/1/2 and nothing else: >= 3 is refused by
    FreeCAD itself ("BRepFill : The continuity is not G0 G1 or G2"), so the
    honest answer is to refuse it here, before an object exists.
    """
    if order in CORNER_FILL_ORDERS:
        return None
    return ("the corner fill order must be 0 (C0), 1 (G1) or 2 (G2) -- "
            "got %r" % (order,))


def _build_fill(links, faces, order, name):
    """The shared build-and-validate tail of both fill entry points.

    (object, None) or (None, reason). The created object is FreeCAD's own,
    not a Silk one. A fill that produced no face, is invalid, or misses its
    own boundary is REMOVED again before returning, so an invalid fill is
    never parked in the tree reading `State=Up-to-date` (#80/#83).
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
    problem = corner_fill_problem(obj, links)
    if problem is not None:
        doc.removeObject(obj.Name)
        doc.recompute()
        return None, problem
    return obj, None


def create_fill(links, faces=None, order=1, name="Surface"):
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
    is then validated by the C0 boundary residual (`corner_fill_problem`),
    and a fill that misses its own boundary is removed again.

    The corner's own collector is `corner_fill_boundary` (ring strips ->
    this same wiring), used by `create_corner_fill`.
    """
    if links and not isinstance(links[0], (list, tuple)):
        links = [links]     # one bare (object, "EdgeN") link
    links = [(o, s) for o, s in list(links or []) if o is not None and s]
    problem = _order_problem(order)
    if problem is not None:
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
    obj, problem = _build_fill(ordered, faces, order, name)
    if obj is None:
        FreeCAD.Console.PrintError(
            "Silk: the surface fill over %d boundary edges did not build -- "
            "%s. Nothing was left in the tree.\n" % (len(ordered), problem))
        return None
    FreeCAD.Console.PrintMessage(
        "Silk: surface fill %s created over %d boundary edges (order %d)\n"
        % (obj.Name, len(ordered), order))
    return obj


def create_corner_fill(*strips, order=1, name="Surface"):
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
    validated, and a fill that produced no face, is invalid, or misses its
    own boundary is REMOVED again with a named refusal -- an invalid fill
    must never be parked in the tree reading `State=Up-to-date` (#80/#83).

    The created object is FreeCAD's own, not a Silk one: it carries no band
    or split bookkeeping and no Silk view provider. GUI-free -- the command
    and the task panel wrap it in their own transaction.
    """
    if len(strips) == 1 and isinstance(strips[0], (list, tuple)):
        strips = list(strips[0])
    strips = [s for s in (strips or []) if s is not None]
    if len(strips) not in (3, 4):
        FreeCAD.Console.PrintError(
            "Silk: a corner fill needs the ring's 3 or 4 blend strips around "
            "one junction (got %d). Nothing was created.\n" % len(strips))
        return None
    bad_order = _order_problem(order)
    if bad_order is not None:
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
    obj, problem = _build_fill(links, faces, order, name)
    if obj is None:
        FreeCAD.Console.PrintError(
            "Silk: the surface fill over %s did not build -- %s. Nothing was "
            "left in the tree.\n"
            % (", ".join(s.Name for s in strips), problem))
        return None
    FreeCAD.Console.PrintMessage(
        "Silk: surface fill %s created over %s (order %d, %d boundary "
        "edges)\n"
        % (obj.Name, ", ".join(s.Name for s in strips), order, len(links)))
    return obj
