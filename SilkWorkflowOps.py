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

from SilkEdge import Edge, EdgeViewProvider
from SilkPatch import Patch, PatchViewProvider
from SilkBlend import Blend, BlendStripViewProvider, BLEND_TYPES, PATCH_TYPES


def create_edge(sketches, name="Edge"):
    """Create a SilkEdge from one or two ControlPoly4 sketches.

    addObject -> Edge constructor -> view provider -> recompute ->
    return the created object, so later steps can consume the result
    in one script. No selection, no commands, no dialogs.
    """
    doc = FreeCAD.ActiveDocument
    if not isinstance(sketches, (list, tuple)):
        sketches = [sketches]
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
    """
    doc = FreeCAD.ActiveDocument
    obj = doc.addObject("Part::FeaturePython", name)
    Patch(obj, list(edges))
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


def create_corner_blend(strip0, strip1, strip2, strip3, name="CornerBlend"):
    """Create a CornerBlend filling the central region where 4 patches
    meet (#28). Takes the 4 ring BlendStrips in cyclic order; each
    strip's corner-end row feeds AN.ControlGrid66_4 + AN.CubicSurface_66.

    addObject -> CornerBlend constructor -> view provider -> recompute ->
    return the created object.
    """
    from SilkCorner import CornerBlend, CornerBlendViewProvider
    doc = FreeCAD.ActiveDocument
    obj = doc.addObject("Part::FeaturePython", name)
    CornerBlend(obj, strip0, strip1, strip2, strip3)
    CornerBlendViewProvider(obj.ViewObject)
    obj.ViewObject.LineWidth = 1.50
    obj.ViewObject.LineColor = (1.00, 0.67, 0.00)
    obj.ViewObject.PointSize = 4.00
    obj.ViewObject.DisplayMode = "Shaded"
    obj.ViewObject.ShapeColor = (1.00, 0.67, 0.00)
    obj.ViewObject.Transparency = 30
    doc.recompute()
    return obj
