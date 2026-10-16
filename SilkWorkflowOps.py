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
    obj.ViewObject.DisplayMode = "Shaded"
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
    four blend strips, whatever order they were handed over in."""
    want = {id(s) for s in strips}
    for o in doc.Objects:
        if getattr(o, "object_type", None) != "CornerBlend":
            continue
        have = list(getattr(o, "Strips", []) or [])
        if len(have) == 4 and {id(s) for s in have} == want:
            return o
    return None


def create_corner_blend(*strips, name="CornerBlend"):
    """Create the CornerBlend filling the junction where 4 blend strips
    meet (#28; rebuilt on the subgrid chain in #91).

    `strips` are the 4 ring Blend strips, in any order (or one list).
    The ring resolver orders them; the corner geometry is computed
    BEFORE anything is constructed, so a selection that is not a 4-strip
    ring around one shared junction is refused by name and leaves NO
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
    if len(strips) != 4:
        FreeCAD.Console.PrintError(
            "Silk: cannot create a corner blend from %d blend%s -- a corner "
            "is the ring of exactly 4 blends around one junction. Nothing "
            "was created.\n"
            % (len(strips), "" if len(strips) == 1 else "s"))
        return None
    grids, _cells, why = corner_inputs(strips, CORNER_DEFAULT_TOL)
    if grids is None:
        FreeCAD.Console.PrintError(
            "Silk: cannot create a corner blend from these 4 blends -- %s. "
            "Nothing was created.\n" % why)
        return None
    existing = _existing_corner_blend(doc, strips)
    if existing is not None:
        FreeCAD.Console.PrintMessage(
            "Silk: this junction already has a corner blend (%s) -- no "
            "second one created\n" % existing.Name)
        return existing
    ordered, _why = corner_ring(strips)
    obj = doc.addObject("Part::FeaturePython", name)
    CornerBlend(obj, ordered)
    CornerBlendViewProvider(obj.ViewObject)
    obj.ViewObject.LineWidth = 1.50
    obj.ViewObject.LineColor = (1.00, 0.67, 0.00)
    obj.ViewObject.PointSize = 4.00
    obj.ViewObject.DisplayMode = "Shaded"
    obj.ViewObject.ShapeColor = (1.00, 0.67, 0.00)
    obj.ViewObject.Transparency = 30
    doc.recompute()
    return obj
