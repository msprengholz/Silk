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
from SilkMachinery import loop_order, corner_ring


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


def create_corner_blend(*strips, name="CornerBlend"):
    """Create the CornerBlend filling the junction where 3 or 4 blend
    strips meet (#28; rebuilt on the subgrid chain in #91).

    `strips` are the ring Blend strips, in any order (or one list): three
    where three patches meet (the triangular 4th member is built
    invisibly), four where four do.
    The ring resolver orders them; the corner geometry is computed
    BEFORE anything is constructed, so a selection that is not a ring
    around one shared junction is refused by name and leaves NO
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
    grids, _cells, why = corner_inputs(strips, CORNER_DEFAULT_TOL)
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
    doc.recompute()
    return obj


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
    doc = FreeCAD.ActiveDocument
    if len(strips) == 1 and isinstance(strips[0], (list, tuple)):
        strips = list(strips[0])
    strips = [s for s in (strips or []) if s is not None]
    if len(strips) not in (3, 4):
        FreeCAD.Console.PrintError(
            "Silk: a corner fill needs the ring's 3 or 4 blend strips around "
            "one junction (got %d). Nothing was created.\n" % len(strips))
        return None
    if order not in CORNER_FILL_ORDERS:
        FreeCAD.Console.PrintError(
            "Silk: the corner fill order must be 0 (C0), 1 (G1) or 2 (G2) -- "
            "got %r. Nothing was created.\n" % (order,))
        return None
    boundary, why = corner_fill_boundary(strips)
    if boundary is None:
        FreeCAD.Console.PrintError(
            "Silk: cannot build the corner fill over these %d blends -- %s. "
            "Nothing was created.\n" % (len(strips), why))
        return None
    links, faces = boundary
    try:
        obj = doc.addObject("Surface::Filling", name)
    except Exception as exc:
        # The Surface module is FreeCAD's, not ours: a build without it can
        # still run every other Silk path, so this refuses by name like any
        # other unusable input rather than raising.
        FreeCAD.Console.PrintError(
            "Silk: this FreeCAD provides no Surface::Filling object type "
            "(%s). Nothing was created.\n" % (exc,))
        return None
    obj.BoundaryEdges = links
    obj.BoundaryFaces = faces
    obj.BoundaryOrder = [order] * len(links)
    doc.recompute()
    problem = corner_fill_problem(obj, links)
    if problem is not None:
        doc.removeObject(obj.Name)
        doc.recompute()
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
