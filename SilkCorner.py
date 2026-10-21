"""
SilkCorner — CornerBlend FeaturePython for the 4-subgrid corner fill (#28, #91).

Where 4 Patch objects meet at a central junction, each contributes its
corner subgrid cell (excluded from the ring blend bands by #33). The
CornerBlend takes the ring's 3 or 4 blends (DAG: patch -> blend ->
corner blend) and builds Silk's real corner: the four consecutive strip
pairs each make a 3x3 subgrid (`SubGrid33_2Grid64`), the four subgrids
assemble into a 6x6 (`ControlGrid66_4Sub`), and the surface comes from
`CubicSurface_66` (never `buildFromPolesMultsKnots`).

#91: the geometry machinery is a PURE port of the two upstream classes
into Silk's own code -- `SilkMachinery` holds the ring resolver and the
subgrid chain (`corner_ring`, `corner_grid`, `subgrid33_2grid64`,
`control_grid66_4sub`, `orient_junction_row`), and this module holds the
strip-to-grid derivation shared by the object and the ops validator
(`corner_inputs`, `corner_from_strips`). Those upstream classes are
restore shims (#7) and are never called at runtime; they remain the
pole-for-pole oracle the tests compare against. The old #28 fill
(`ControlGrid66_4`, a boundary-curve constructor whose interior was
difference propagation) is gone. Ticket-foldfix adds the one deliberate
deviation from the port: `SilkMachinery.smooth_degenerate_cap` re-solves
the member-side interior rows of a ring that carries a collapsed side,
because upstream's subgrid extrapolation past that side folds the cap on
the cube-corner fixture; on the ordinary 4-valent ring it is a
byte-identical no-op.

Usage:
  1. Build the 3 or 4 ring blends
  2. Run create_corner_blend(*ring_blends)
  3. The corner blend auto-updates when any linked strip recomputes
"""

import FreeCAD
from FreeCAD import Gui
import Part
import ArachNURBS as AN

from SilkBlend import band_cells, side_and_end, seam_direction, BLEND_TYPES, \
    ensure_grid_toggle, migrate_shaded_display
from SilkMachinery import (build_intervals, axis_intervals, split_pair,
    leader_pair, band_edge, corner_cell_index, corner_ring,
    corner_grid, orient_junction_row, corner_ring_3,
    control_grid64_3_1, reverse_grid_rows, set_grid_display,
    ring_corner_gap)

import os, Silk_dummy
path_Silk = os.path.dirname(Silk_dummy.__file__)
path_Silk_icons = os.path.join(path_Silk, "Resources", "Icons")
iconPath = path_Silk_icons + "/ControlGrid66_4Sub.svg"
# The `Silk_CornerFill` command's own Pixmap (#96, owner decision D3: the
# command joined the visible set, so it now stands BESIDE the corner blend in
# the toolbar). Its own file, not the corner blend's `ControlGrid66_4Sub.svg`:
# two adjacent buttons must not wear the same picture (#54/#94, the defect
# `test_icon_dedication` exists to prevent). Absolute and `Silk_dummy.__file__`
# derived, like every other Silk icon path (#54).
corner_fill_icon_path = path_Silk_icons + "/SilkCornerFill.svg"

# The corner blend's own default tolerance for the strip-side / corner-cell
# derivation (matches the object's `tolerance` property default).
CORNER_DEFAULT_TOL = 0.01

# The shared-corner match tolerance of the subgrid chain. Upstream's
# `SubGrid33_2Grid64` uses `default_tol` = 1e-6; the corner poles are
# exact, so a tight tolerance is right and cannot match two corners.
CORNER_TOL = 1e-6

# The order the triangular member's two row orientations are tried in
# (#119).  `control_grid64_3_1` collapses row 3 -- upstream's own layout,
# where row 3 IS the selected corner -- so the member's REAL row (the curve
# that flows round the corner, the one the ring's other members meet) sits on
# row 0 in the net as built.  The ring convention puts every member's
# junction-end row at V = 3 (`orient_junction_row` does it for the strips),
# so the member is tried REVERSED first: that is the orientation in which the
# ring reads its real row.  Read as-built, a ring hands its collapsed row to
# the 6x6, one whole side of the corner fill becomes a point, and the fill
# sweeps over the member's own cell instead of sitting beside it (measured
# #119: the member's face lies 0.0002-0.017 mm off the corner fill, i.e.
# inside it).
#
# AS-BUILT IS THE ORDER FOR EVERY CORNER WITHOUT A LEADER CUT, and that is
# what keeps every pre-#119 corner pole-identical -- measured, not assumed:
# the cube corner's shipped cap relies on the collapsed row sitting at V = 3,
# where `smooth_degenerate_cap` re-solves the interior rows (25/53/96
# normal-field flips and a self-intersecting cap when the order is forced the
# other way).  The reversed order is used exactly where the leader cut makes
# the member's real row its ring row, i.e. on a patch that carries one.
_MEMBER_ROW_ORDER_LEADER = (True, False)
_MEMBER_ROW_ORDER = (False, True)


def _member_row_order(pth):
    """The order the member's row orientations are tried in: AS BUILT.

    #119 tried the other order on a patch that carries a leader cut, so the
    member's REAL row (which the leader-bounded cell puts on the cell's
    mixed corners) would be the ring row at V = 3 like every strip's.  That
    arrangement DOES produce the owner's two-patch corner -- the 66 stops at
    the member's cell instead of sweeping over it -- and it was measured and
    rendered: the 66 comes out at 0.0633 mm2 against the member's 0.0206,
    with no collapsed side.  IT IS NOT SHIPPED, because it FOLDS: the
    member-side interior rows, extrapolated from the member's own rows, flip
    the normal field 25/53/96 times at n = 39/81/150 and the fine mesh
    self-intersects -- `smooth_degenerate_cap` fixes the COLLAPSED side, and
    this arrangement has none there.  The two-surface corner therefore waits
    on a member-side re-solve, and until it has one the as-built order (the
    collapsed row at V = 3, the cap smoothing's own case) is what builds.
    #119's research note carries the numbers.
    """
    return _MEMBER_ROW_ORDER


# ---- the pure corner derivation (#91) ------------------------------------
#
# Both the object's `execute()` and the ops-layer validator run these, so
# there is exactly ONE definition of "what corner does this strip set
# make". No document, no object, no console here.

def _corner_cell_net(p, cell):
    """Patch p's ring-corner subgrid cell as (flat poles, flat weights) in
    the row-major 4x4 order `control_grid64_3_1` reads, or (None, None).

    `cell` is the patch's entry from `corner_inputs`' `corner_cells`
    (`(pth, iu_c, iv_c, nu, nv)`). The cell is extracted through the
    patch's own `getSubgrid`, so the RATIONAL weights of the segmented
    cell come with the poles -- the same net the patch's `_subgrids`
    holds, plus its weights. This is the ring's corner cell: the region
    the band setbacks leave for the corner fill, whose outer corner is
    the point the ring's boundary loop passes through.
    """
    if cell is None:
        return None, None
    pth, iu_c, iv_c, _nu, nv = cell
    if pth is not p:
        return None, None
    us = axis_intervals(p, "U")
    vs = axis_intervals(p, "V")
    if not (0 <= iu_c < len(us) and 0 <= iv_c < len(vs)):
        return None, None
    getter = getattr(getattr(p, "Proxy", None), "getSubgrid", None)
    if getter is None:
        return None, None
    u0, u1 = us[iu_c]
    v0, v1 = vs[iv_c]
    poles2d, weights2d = getter(u0, u1, v0, v1)
    if not poles2d or not weights2d:
        return None, None
    try:
        poles = [poles2d[r][c] for r in range(4) for c in range(4)]
        weights = [float(weights2d[r][c]) for r in range(4)
                   for c in range(4)]
    except (IndexError, TypeError):
        return None, None
    if len(poles) != 16 or len(weights) != 16:
        return None, None
    return poles, weights


def _shared_patch(a, b):
    """The one patch two ring strips both touch, or None when they touch
    none or two (an ambiguous pair -- the corner cannot name a side then)."""
    common = []
    for x in (getattr(a, "PatchA", None), getattr(a, "PatchB", None)):
        if x is not None and x in (getattr(b, "PatchA", None),
                                   getattr(b, "PatchB", None)):
            common.append(x)
    return common[0] if len(common) == 1 else None


def _orient_ring_columns(grids, ordered):
    """Flip each strip's 6 columns so the ring's shared patch lies on the
    SAME side of every strip.

    A strip's 6-pole axis runs PatchA's outer -> shared seam -> PatchB's
    outer, so which of the two patches lands at column 0 is whichever the
    user handed `create_blend` FIRST -- arbitrary, and a blend is the same
    surface either way round. The corner chain instead reads the shared
    corner from a fixed column (grid_i's col 5 against grid_(i+1)'s col 0),
    so a ring whose blends do not run as a directed cycle (PatchB of one
    strip IS PatchA of the next) cannot assemble. Flipping the columns of
    the strips that run the other way -- column c -> 5 - c, a
    reparameterization of the across-seam axis, not a geometry change --
    turns any ring into that cycle. On a ring already directed this way it
    changes nothing. It is applied only when the ring does not assemble as
    stored (see `_assemble_square_ring` / `_tri_ring_member`), so the
    documented rings keep their exact poles."""
    n = len(grids)
    out = []
    for i, (poles, weights) in enumerate(grids):
        nxt = _shared_patch(ordered[i], ordered[(i + 1) % n])
        if nxt is not None and getattr(ordered[i], "PatchA", None) is nxt:
            poles = [poles[r * 6 + (5 - c)]
                     for r in range(4) for c in range(6)]
            weights = [weights[r * 6 + (5 - c)]
                       for r in range(4) for c in range(6)]
        out.append((poles, weights))
    return out


def _member_ring(base_grids, ordered, patch, member):
    """The 4-grid ring with `member` at `patch`'s corner.

    The triangular 4th member stands in for the blend the missing fourth
    surface would have contributed, so it sits between the TWO ring
    strips that meet at `patch` -- not blindly appended, because
    `corner_ring_3`'s direction follows document order and a ring built
    the other way round needs the member at the mirrored position. The
    ring's first grid (and so the canonical start both `corner_grid` and
    the object's own derivation use) is preserved."""
    touching = [i for i, s in enumerate(ordered)
                if getattr(s, "PatchA", None) is patch
                or getattr(s, "PatchB", None) is patch]
    for i in touching:
        j = (i + 1) % len(ordered)
        if j != i and j in touching:
            return base_grids[:i + 1] + [member] + base_grids[i + 1:]
    return base_grids + [member]


def _assemble_square_ring(base, ordered):
    """(grids, None) for a 4-valent corner: `base` when it already
    assembles, else the ring with the columns normalized (`base` is tried
    first so a ring that already works keeps its exact poles), else
    (None, corner_grid's own refusal for the stored orientation)."""
    p36, _w, why = corner_grid(base, CORNER_TOL)
    if p36 is not None:
        return base, None
    flipped = _orient_ring_columns(base, ordered)
    p36, _w, _why = corner_grid(flipped, CORNER_TOL)
    if p36 is not None:
        return flipped, None
    return None, why


def resolve_member_pin(pin, patches):
    """(patch, corner) for a triangular-member pin, or (None, reason).

    `pin` is `(patch or its Name, corner index)` -- which ring patch's
    grid corner the triangular 4th member must be built at (#117). Both
    halves are validated here so the refusal can name what it could not
    honour: a pin that names a patch outside THIS ring, or a corner
    outside 0..3, is refused before any candidate is tried."""
    ref, corner = pin
    name = getattr(ref, "Name", None) or str(ref)
    target = None
    for p in patches:
        if p is ref or p.Name == name:
            target = p
            break
    if target is None:
        return None, ("the member pin names patch %s, which is not part of "
                      "this ring (%s)"
                      % (name, ", ".join(p.Name for p in patches)))
    try:
        corner = int(corner)
    except (TypeError, ValueError):
        return None, ("the member pin's corner index %r is not an integer"
                      % (corner,))
    if not 0 <= corner <= 3:
        return None, ("the member pin's corner index %d is outside 0..3"
                      % corner)
    return (target, corner), None


def _tri_ring_member(base_grids, ordered, patches, corner_cells,
                     pinned=None):
    """The first 4-grid ring `corner_grid` accepts for a 3-valent corner:
    `base_grids` (the three strips) plus the triangular 4th member built
    from a patch's ring corner CELL -- never the full 4x4 base net, whose
    corners are the patch vertices -- across every corner index and
    reversal. Returns the 4-grid ring or None.

    `pinned` is a resolved `(patch, corner)` from `resolve_member_pin`:
    when set, ONLY that candidate is tried (both reversal states, as the
    search does) and no other patch or corner is considered, so the
    member lands exactly where the user asked or the caller refuses. When
    None the automatic search above runs unchanged.

    Returns `(ring, pin)` -- the ring (or None) and the `(patch, corner)`
    the member was built at (or None).  The pin is what the rolling
    construction needs (#119): the leader is cut on the seams of the
    patch that CARRIES the member, so the two cannot disagree about
    which patch that is."""
    if pinned is not None:
        pth, corner = pinned
        poles_c, weights_c = _corner_cell_net(pth, corner_cells.get(pth.Name))
        if poles_c is None:
            return None, None
        for rev in _member_row_order(pth):
            mp, mw = control_grid64_3_1(poles_c, weights_c, corner)
            if mp is None:
                continue
            if rev:
                mp, mw = reverse_grid_rows(mp, mw)
            member = (list(mp), list(mw))
            cand = _member_ring(base_grids, ordered, pth, member)
            p36, _w, _why = corner_grid(cand, CORNER_TOL)
            if p36 is not None:
                return cand, (pth, corner)
        return None, None
    for pth in patches:
        poles_c, weights_c = _corner_cell_net(pth, corner_cells.get(pth.Name))
        if poles_c is None:
            continue
        for corner in range(4):
            for rev in _member_row_order(pth):
                mp, mw = control_grid64_3_1(poles_c, weights_c, corner)
                if mp is None:
                    continue
                if rev:
                    mp, mw = reverse_grid_rows(mp, mw)
                member = (list(mp), list(mw))
                cand = _member_ring(base_grids, ordered, pth, member)
                p36, _w, _why = corner_grid(cand, CORNER_TOL)
                if p36 is not None:
                    return cand, (pth, corner)
    return None, None


def corner_inputs(strips, tol=CORNER_DEFAULT_TOL, pin=None):
    """The four strips' 24-pole grids in ring order, each with its
    junction-end row at V = 3, plus the corner cell of each patch.

    Returns (grids, corner_cells, None) or (None, None, reason). Every
    refusal names the strip (or patch) that caused it.

    `pin` is an optional `(patch or its Name, corner index)` naming which
    ring patch's grid corner the TRIANGULAR 4th member is built at -- the
    placement upstream's `ControlGrid64_3_1Grid44` recipe leaves to the
    user (#117). None (the default) runs the automatic search unchanged,
    so a corner nobody has pinned is byte-identical. When set, the search
    may only use that candidate and refuses by name otherwise, and a pin
    on a 4-valent ring (which has no triangular member) is refused too.

    The member's own placement is read by `corner_member_pin`, which runs
    the SAME search -- there is one definition of where the member is."""
    grids, cells, _pin, why = _corner_inputs(strips, tol, pin)
    return grids, cells, why


def corner_member_pin(strips, tol=CORNER_DEFAULT_TOL, pin=None):
    """(patch, corner) or (None, reason) -- where the TRIANGULAR 4th
    member of a 3-valent ring is built.

    The same automatic search `corner_inputs` runs, so the answer cannot
    disagree with the member the corner actually builds.  The rolling
    construction (#119) needs it: the rolling leader is cut on the seams
    of the patch that CARRIES the member, so the cut and the member are
    always about the same patch."""
    _grids, _cells, member_pin, why = _corner_inputs(strips, tol, pin)
    if why is not None:
        return None, why
    if member_pin is None:
        return None, ("this ring carries no triangular member (a "
                      "3-valent ring does)")
    return member_pin, None


def _ring_gap_reason(patches):
    """`""` when every ring patch's corner closes, else the clause naming
    the two numbers that keep it open (#127).

    `SilkMachinery.ring_corner_gap` states the loop rule: a ring pair's
    shared corner is the patch's corner cell FAR corner, which is ONE point
    only when the band edge and the along start (the leader cut, when there
    is one) are the same number at each end of the patch's two axes.  The
    shipped construction writes ONE cut per axis end and therefore passes;
    a patch carrying a REAL leader cut does not, and the ring's pairs then
    report "the two grids share no corner" without saying why.  This puts
    the why into that refusal.
    """
    for pth in patches:
        gap = ring_corner_gap(pth)
        if gap is not None:
            letter, across, along = gap
            return ("; the ring's corner is OPEN on %s: its %s axis carries a "
                    "band edge of %g and a leader cut of %g, and a ring "
                    "pair's shared corner needs those two to be one number "
                    "(#127)" % (pth.Name, letter, across, along))
    return ""


def _corner_inputs(strips, tol=CORNER_DEFAULT_TOL, pin=None):
    """`corner_inputs` plus the member's own placement.

    Returns (grids, corner_cells, member_pin, None) or
    (None, None, None, reason).  `member_pin` is the `(patch, corner)`
    the triangular 4th member was built at (None on a 4-valent ring)."""
    strips = list(strips)
    is_tri = (len(strips) == 3)
    if is_tri:
        ordered, why = corner_ring_3(strips)
    else:
        ordered, why = corner_ring(strips)
    if ordered is None:
        return None, None, None, why
    grids = []
    corner_cells = {}
    member_pin = None
    for s in ordered:
        pa = getattr(s, "PatchA", None)
        pb = getattr(s, "PatchB", None)
        if pa is None or pb is None:
            return None, None, None, "blend %s has no patches" % s.Name
        e_a, ss_a = side_and_end(s, pa, tol)
        e_b, ss_b = side_and_end(s, pb, tol)
        if not e_a or not e_b:
            return None, None, None, ("blend %s: no shared edge between %s "
                                      "and %s" % (s.Name, pa.Name, pb.Name))
        # The two patches can parameterize their shared seam in the same
        # direction (identity) or opposite (reversed) -- it depends on
        # the geometry and on each patch's stored cycle, not on the edge
        # type. A reversed seam names the SAME junction at the mirrored
        # row of the patch's seam-parallel axis, so the two patches'
        # junction-end rows are compared ACROSS that reflection.
        # Comparing the raw indices is what reports a legitimately
        # reversed seam as a twisted input.
        identity = seam_direction(s, tol)
        bca = band_cells(pa, e_a, ss_a)
        bcb = band_cells(pb, e_b, ss_b)
        if len(bca) != 1 or len(bcb) != 1:
            return None, None, None, ("blend %s: its band must cover exactly "
                                      "1 cell per side (got %d/%d)"
                                      % (s.Name, len(bca), len(bcb)))
        li_map = {}
        for pth, e, bc in ((pa, e_a, bca), (pb, e_b, bcb)):
            iu_c, iv_c, nu, nv = CornerBlend._corner_cell(pth, ordered, tol)
            if iu_c is None or iv_c is None:
                return None, None, None, ("patch %s: corner cell at the "
                                          "4-patch junction not found"
                                          % pth.Name)
            iu_b, iv_b = divmod(bc[0], nv)
            # corner-end row: 3 if the corner cell sits above the band
            # cell along the band axis, else 0
            if e[0] == "U":
                li_map[pth.Name] = 3 if iu_c > iu_b else 0
            else:
                li_map[pth.Name] = 3 if iv_c > iv_b else 0
            corner_cells[pth.Name] = (pth, iu_c, iv_c, nu, nv)
        if li_map[pa.Name] != (3 - li_map[pb.Name] if identity is False
                               else li_map[pb.Name]):
            return None, None, None, ("blend %s: its two patches disagree "
                                      "about which end is the junction "
                                      "(twisted input)" % s.Name)
        poles = list(getattr(s, "Poles", None) or [])
        weights = list(getattr(s, "Weights", None) or [])
        if len(poles) != 24 or len(weights) != 24:
            return None, None, None, ("blend %s: expected a 24-pole grid, "
                                      "got %d poles / %d weights"
                                      % (s.Name, len(poles), len(weights)))
        grids.append(orient_junction_row(poles, weights, li_map[pa.Name]))
    if is_tri:
        patches = []
        for s in ordered:
            for pth in (getattr(s, "PatchA", None), getattr(s, "PatchB", None)):
                if pth is not None and pth not in patches:
                    patches.append(pth)
        # The stored column orientation of a strip is arbitrary (which
        # patch the user handed create_blend first), so the member search
        # runs once as stored -- the documented rings assemble there --
        # and, only if that cannot, once with the ring's columns
        # normalized.  The ring's DIRECTION is tried the same way (#119):
        # which of the two strips touching the member's patch comes first is
        # not a free choice a caller makes, it is what the ring order gave,
        # and the member's two real ring corners are read (V3, U0) and
        # (V3, U5) -- so a ring traversed the other way can present them
        # swapped.  Stored order FIRST, so a corner that already assembles
        # keeps its exact poles.
        pinned, pin_why = ((None, None) if pin is None
                           else resolve_member_pin(pin, patches))
        if pin is not None and pinned is None:
            return None, None, None, pin_why
        ring = None
        stored = list(grids)
        flipped = _orient_ring_columns(grids, ordered)
        reversed_order = list(reversed(ordered))
        for base_grids, ord_ in ((stored, ordered),
                                 (flipped, ordered),
                                 (list(reversed(stored)), reversed_order),
                                 (list(reversed(flipped)), reversed_order)):
            ring, member_pin = _tri_ring_member(base_grids, ord_, patches,
                                                corner_cells, pinned)
            if ring is not None:
                break
        if ring is None:
            if pinned is not None:
                return None, None, None, ("could not build the triangular 4th "
                                          "member at the pinned corner %s[%d]"
                                          "%s"
                                          % (pinned[0].Name, pinned[1],
                                             _ring_gap_reason(patches)))
            return None, None, None, ("could not build triangular 4th "
                                      "member%s"
                                      % _ring_gap_reason(patches))
        grids = ring
    else:
        if pin is not None:
            return None, None, None, ("the triangular-member pin applies "
                                      "only to a 3-valent corner; this ring "
                                      "has 4 strips")
        grids, why = _assemble_square_ring(grids, ordered)
        if grids is None:
            return None, None, None, why + _ring_gap_reason(ordered)
    return grids, corner_cells, member_pin, None


def corner_from_strips(strips, tol=CORNER_DEFAULT_TOL, pin=None):
    """The full corner: four strips -> (poles36, weights36, corner_cells).

    `pin` is `corner_inputs`' optional triangular-member placement (#117);
    None runs the automatic search.

    Returns (p36, w36, corner_cells, None) or (None, None, None, reason).
    """
    grids, corner_cells, why = corner_inputs(strips, tol, pin)
    if grids is None:
        return None, None, None, why
    p36, w36, why = corner_grid(grids, CORNER_TOL)
    if p36 is None:
        return None, None, None, why
    return p36, w36, corner_cells, None


def ensure_member_pin(obj):
    """#117: the triangular-member placement properties, added once.

    `MemberPatch` names the ring patch whose grid corner the triangular
    4th member is pinned to (empty = the automatic search) and
    `MemberCorner` its grid corner index 0..3. An empty pin IS the old
    behaviour, so a corner saved before #117 -- which has neither
    property (`__init__` does not run on restore) -- keeps building
    exactly as before the moment this runs, and its placement becomes
    selectable without a rebuild."""
    if not hasattr(obj, "MemberPatch"):
        obj.addProperty("App::PropertyLink", "MemberPatch", "Inputs",
                        "ring patch whose grid corner the triangular 4th "
                        "member is pinned to (3-valent corners only; empty "
                        "= automatic search)")
    if not hasattr(obj, "MemberCorner"):
        obj.addProperty("App::PropertyInteger", "MemberCorner", "Inputs",
                        "grid corner index (0..3) of the pinned triangular "
                        "4th member").MemberCorner = 0


def fill_of_member(doc, member):
    """The `Surface::Filling` whose boundary is this member's shape, or
    None.

    THE MEMBER DOES NOT LINK TO THE FILL.  A link would make the member
    DEPEND on the fill, while the fill depends on the member (its
    boundary edges) -- a cycle, and FreeCAD's recompute order inside a
    cycle is arbitrary: measured, the member then ends up touched after
    every pass and the document never settles (#125).  So the fill is
    FOUND by its boundary instead, which is the same direction the
    dependency already runs."""
    for o in doc.Objects:
        if getattr(o, "TypeId", "") != "Surface::Filling":
            continue
        for entry in (getattr(o, "BoundaryEdges", None) or []):
            if entry and entry[0] is member:
                return o
    return None


class CornerBlend:
    """FeaturePython: fills the central region where 4 patches meet."""

    def __init__(self, obj, strips):
        obj.addProperty("App::PropertyLinkList", "Strips", "Inputs",
                        "ring blends in cyclic order"
                        ).Strips = list(strips)
        obj.addProperty("App::PropertyFloat", "tolerance", "Inputs",
                        "corner matching tolerance").tolerance = CORNER_DEFAULT_TOL
        # #117: the triangular 4th member's placement. The search picks
        # the first patch/corner that assembles; MemberPatch names the
        # ring patch whose grid corner the member is PINNED to (empty =
        # today's automatic search) and MemberCorner its grid corner index
        # 0..3. Both are inert until MemberPatch is set.
        ensure_member_pin(obj)
        obj.addProperty("App::PropertyVectorList", "Poles", "Outputs",
                        "corner grid poles (6x6)").Poles
        obj.addProperty("App::PropertyFloatList", "Weights", "Outputs",
                        "corner grid weights").Weights
        obj.addProperty("Part::PropertyGeometryList", "Legs", "Outputs",
                        "grid segments").Legs
        ensure_grid_toggle(obj)
        obj.addProperty("App::PropertyString", "object_type", "",
                        "").object_type = "CornerBlend"
        obj.setEditorMode("object_type", 1)
        obj.Proxy = self
        self._in_execute = False

    def onDocumentRestored(self, obj):
        # #95: same two restore fixes as a Blend, for the same reasons --
        # a corner saved before the grid toggle existed has no ShowGrid
        # (__init__ does not run on restore), and `Shaded` leaves the
        # corner's boundary edges unpickable, which is a defect on a
        # surface the Filling panel is meant to consume, not a
        # preference.
        ensure_grid_toggle(obj)
        migrate_shaded_display(obj)
        ensure_member_pin(obj)

    def onChanged(self, fp, prop):
        if prop in ("Strips", "tolerance", "MemberPatch", "MemberCorner"):
            if 'Restore' not in fp.State and list(getattr(fp, "Strips", []) or []):
                fp.touch()
                fp.recompute()
        elif prop in ("ShowGrid", "ShowSurface"):
            # A DISPLAY toggle must not leave the object dirty. FreeCAD
            # sets the Touched flag on every property write -- after
            # onChanged returns -- so the next document recompute pass
            # rebuilt the whole corner chain (the member, the four 33
            # subgrids, the 66 and its surface) for a change that only
            # decides what is DRAWN. Measured: 857 ms per toggle on the
            # cube corner, against 4 ms for the write itself.
            try:
                fp.purgeTouched()
            except Exception:
                pass

    def execute(self, fp):
        if 'Restore' in fp.State:
            return  # preserve stored poles across save/restore
        # #95: the toggle is structural -- every execute path guarantees
        # it, so a corner restored from an older file is editable the
        # moment it recomputes rather than only after a reopen.
        ensure_grid_toggle(fp)
        if not list(getattr(fp, "Strips", []) or []):
            return
        if getattr(self, "_in_execute", False):
            return
        self._in_execute = True
        try:
            self._do_execute(fp)
        finally:
            self._in_execute = False

    # ---- derivation -------------------------------------------------

    @staticmethod
    def _corner_cell(p, strips, tol):
        """(iu_c, iv_c, nu, nv) of the corner cell at the 4-patch junction
        of patch p. The U-direction seam gives the V side of the corner,
        the V-direction seam gives the U side.

        `nu` / `nv` are the interval counts of the two named band edges
        plus the leader cuts (#82 / #119) -- `len(splits) + 1` used to say
        "how many splits does this axis carry", and what an axis carries is
        now, per end, the question "does this end have an edge, and a leader
        cut beyond it?".

        THE CORNER CELL (#119): when the junction end carries a LEADER cut,
        the corner cell is the interval that ENDS at that cut -- the region
        between the setback and the leader -- because that is the region the
        corner fill leaves over once the band is cut back. Without a leader
        it is the end interval, exactly as before."""
        nu, nv = len(axis_intervals(p, "U")), len(axis_intervals(p, "V"))
        iu_c = iv_c = None
        for s in strips:
            other = s.PatchB if s.PatchA is p else s.PatchA
            if other is None:
                continue
            # #83: read the strip's side off the STRIP (which carries the
            # pinned Edge of a unified Blend), not off the patch pair. A
            # patch pair sharing two seams names the same side twice, so a
            # corner cell derived through `patch_side` can be taken on the
            # wrong seam's band.
            e, ss = side_and_end(s, p, tol)
            if not e:
                continue
            letter = "V" if e[0] == "U" else "U"
            s1, s2 = split_pair(p, letter)
            l1, l2 = leader_pair(p, letter)
            idx, _n, _end = corner_cell_index(s1, s2, l1, l2,
                                              int(e[1]))
            if e[0] == "U":
                iv_c = idx
            else:
                iu_c = idx
        return iu_c, iv_c, nu, nv

    def _refuse(self, fp, why):
        """Refuse loudly and leave the object EMPTY rather than stale: a
        corner that can no longer be built shows nothing and says why."""
        fp.Poles = []
        fp.Weights = []
        fp.Legs = []
        fp.Shape = Part.Shape()
        FreeCAD.Console.PrintError(
            "Silk: corner blend %s: %s\n" % (fp.Name, why))

    # ---- execution --------------------------------------------------

    def _do_execute(self, fp):
        member_patch = getattr(fp, "MemberPatch", None)
        pin = (None if member_patch is None
               else (member_patch, int(getattr(fp, "MemberCorner", 0))))
        p36, w36, corner_cells, why = corner_from_strips(
            list(fp.Strips), fp.tolerance, pin)
        if p36 is None:
            self._refuse(fp, why)
            return

        # hide the corner cells (the region this blend covers)
        for name, (pth, iu_c, iv_c, nu, nv) in corner_cells.items():
            idx = iu_c * nv + iv_c
            try:
                pth.removeProperty("_HideSubgridIdx")  # superseded
            except Exception:
                pass
            if not hasattr(pth, "_HiddenSubgridIdxs"):
                pth.addProperty("App::PropertyIntegerList",
                                "_HiddenSubgridIdxs", "Internal",
                                "subgrid cell indices hidden by blends")
                pth.setEditorMode("_HiddenSubgridIdxs", 1)
            cur = set(int(i) for i in (pth._HiddenSubgridIdxs or []))
            cur.add(idx)
            pth._HiddenSubgridIdxs = sorted(cur)

        fp.Poles = p36
        fp.Weights = w36
        fp.Legs = AN.drawGrid(fp.Poles, 6)

        # corner surface via AN.CubicSurface_66 (never
        # buildFromPolesMultsKnots) -- it reads Grid.Poles / Grid.Weights,
        # so the cross-multiplied rational weights are carried into it.
        doc = fp.Document
        surf_shape = None
        tmp_surf = None
        try:
            tmp_surf = doc.addObject("Part::FeaturePython", "_cb_surf_tmp")
            AN.CubicSurface_66(tmp_surf, fp)
            tmp_surf.recompute()
            surf_shape = tmp_surf.Shape
        finally:
            # the temp carrier must not survive a failed build
            if tmp_surf is not None and doc.getObject(tmp_surf.Name) is not None:
                try:
                    doc.removeObject(tmp_surf.Name)
                except Exception:
                    pass

        if not surf_shape or not hasattr(surf_shape, "Faces") \
                or not surf_shape.Faces:
            fp.Shape = Part.Shape()  # no surface to show; the grid is a view node
            return

        # Shape is GEOMETRY ONLY (#108): the corner surface. The control
        # grid is a DISPLAY concern -- the view provider draws it as a Coin
        # node (SilkMachinery.set_grid_display reads fp.Legs), so it is not
        # part of Shape, not exported, and not selectable.
        fp.Shape = surf_shape


class RollingMemberFace:
    """The SMALL TRIANGULAR SURFACE beside the rolling corner (#119, A).

    The maintainer's rolling corner is TWO surfaces: one big quad (Silk's
    own 66) and, beside it, a SMALLER TRIANGULAR surface -- in his file
    the `CubicSurface_64` over the ring's triangular member (the corner
    patch's corner cell, with one row collapsed onto the apex).  The
    owner's spec: this smaller surface is the one to be replaced with a
    FreeCAD surface patch.

    This object is that smaller surface.  It re-derives the member from
    the ring on every execute -- the SAME derivation the corner fill
    uses (`corner_inputs`, the one place that defines "what corner does
    this strip set make") -- so the two surfaces cannot disagree about
    where the member is, and the face follows the corner when it moves.

    Its surface is built from the member's own 24-pole grid through
    `AN.CubicSurface_64` (never `buildFromPolesMultsKnots`), exactly the
    way the maintainer's own `CubicSurface_64` over that grid is built.
    """

    def __init__(self, obj, strips, corner=None):
        obj.addProperty("App::PropertyLinkList", "Strips", "Inputs",
                        "the ring's blends").Strips = list(strips)
        obj.addProperty("App::PropertyLink", "Corner", "Inputs",
                        "the corner fill this face belongs to").Corner = corner
        obj.addProperty("App::PropertyStringList", "BoundaryEdges",
                        "Outputs",
                        "the sub-shapes the member's face fill takes: the "
                        "member's three REAL boundary curves").BoundaryEdges
        obj.addProperty("App::PropertyVectorList", "Poles", "Outputs",
                        "the triangular member's 24 poles").Poles
        obj.addProperty("App::PropertyFloatList", "Weights", "Outputs",
                        "the triangular member's 24 weights").Weights
        obj.addProperty("Part::PropertyGeometryList", "Legs", "Outputs",
                        "grid segments").Legs
        obj.addProperty("App::PropertyString", "object_type", "",
                        "").object_type = "RollingMemberFace"
        obj.setEditorMode("object_type", 1)
        obj.Proxy = self
        self._in_execute = False

    def onChanged(self, fp, prop):
        if prop in ("Strips", "Corner"):
            if 'Restore' not in fp.State and list(getattr(fp, "Strips", []) or []):
                fp.touch()
                fp.recompute()

    def _refresh_fill(self, fp):
        """Re-point the FILL's boundary at this object's own edges (#119).

        WHY THIS IS NEEDED.  The fill's boundary edges live on THIS
        object's shape -- the member's own three real edges -- and a
        REPLACED shape breaks their sub-names: FreeCAD re-resolves a
        link's sub-elements against the new shape, the old names do not
        resolve ("?Edge1"), and the fill is left Touched+Invalid, so the
        document never settles again after a band-edge edit.  (The
        shipped corner fill, which is opt-in, has the same latent defect:
        its boundary lives on the ring strips.)

        So the fill is re-pointed here, right after the new shape is in
        place: the fill is then rebuilt in the same recompute pass (it
        depends on this object, so it comes after it).

        The re-pointing is done ONLY when the links are actually broken.
        A property write on the fill TOUCHES it, and a touched fill is
        rebuilt -- and left dirty again -- for nothing, so a member that
        recomputes several times in one pass (it does: the ring's cells
        change more than once) must not touch the fill more than once.

        The member's COLLAPSED row is a degenerate edge -- its two ends
        are the apex -- and a degenerate edge is not a curve a fill can
        take, so the fill's boundary is the member's three REAL edges.
        """
        fill = fill_of_member(fp.Document, fp)
        if fill is None:
            return
        real = list(getattr(fp, "BoundaryEdges", None) or [])
        if len(real) < 3:
            return
        current = []
        try:
            current = list(getattr(fill, "BoundaryEdges", None) or [])
        except Exception:
            current = []
        if (len(current) == 1 and current[0][0] is fp
                and list(current[0][1]) == real):
            # already pointing at these edges -- but the fill may still
            # be dirty from the rebuild it just did, and the document
            # must settle, so it is purged here.
            try:
                fill.purgeTouched()
            except Exception:
                pass
            return
        try:
            fill.BoundaryEdges = [(fp, name) for name in real]
            fill.BoundaryFaces = ["Face1"] * len(real)
            # and rebuild it NOW: the fill depends on this object, and
            # while this object is still executing the dependency is not
            # up to date, so the document's own pass would skip it -- the
            # fill would stay dirty (and its surface stale) and the
            # document would never settle.
            fill.touch()
            fill.recompute(True)
            fill.purgeTouched()
        except Exception as exc:
            FreeCAD.Console.PrintError(
                "Silk: the member face's fill could not be re-pointed at "
                "%s: %s\n" % (fp.Name, exc))

    def execute(self, fp):
        if 'Restore' in fp.State:
            return
        if getattr(self, "_in_execute", False):
            return
        self._in_execute = True
        try:
            self._do_execute(fp)
        finally:
            self._in_execute = False

    def _do_execute(self, fp):
        grids, _cells, why = corner_inputs(list(fp.Strips),
                                          pin=_member_pin_of(fp))
        member = member_grid(grids) if grids is not None else None
        if member is None:
            FreeCAD.Console.PrintError(
                "Silk: the rolling member face %s: %s\n"
                % (fp.Name, why if grids is None else
                   "this ring carries no triangular member"))
            fp.Poles = []
            fp.Weights = []
            fp.Legs = []
            fp.Shape = Part.Shape()
            return
        poles, weights = member
        old_poles = list(getattr(fp, "Poles", None) or [])
        fp.Poles = poles
        fp.Weights = weights
        fp.Legs = AN.drawGrid(fp.Poles, 6)
        doc = fp.Document
        tmp = None
        try:
            tmp = doc.addObject("Part::FeaturePython", "_rmf_surf_tmp")
            AN.CubicSurface_64(tmp, fp)
            tmp.recompute()
            shape = tmp.Shape
        finally:
            if tmp is not None and doc.getObject(tmp.Name) is not None:
                try:
                    doc.removeObject(tmp.Name)
                except Exception:
                    pass
        if not shape or not hasattr(shape, "Faces") or not shape.Faces:
            fp.Shape = Part.Shape()
            return
        # A REPLACED shape breaks the fill's sub-names (see
        # `_refresh_fill`), and this object is recomputed several times
        # in one pass -- so the shape is only replaced when the member's
        # NET actually changed.  An unchanged net means an unchanged
        # surface, and the fill's links stay good.
        same_net = (len(old_poles) == len(poles) and old_poles
                    and all((a - b).Length <= 1e-12
                            for a, b in zip(old_poles, poles)))
        if same_net and getattr(fp, "Shape", None) is not None \
                and fp.Shape.Faces:
            self._purge(fp)
            return
        # THE SHAPE IS A COMPOUND: the silk face AND the member's three
        # REAL boundary curves.  The compound is not decoration -- it is
        # what makes the FILL's boundary stable.  A fill's boundary is a
        # LINK to a sub-shape, and a FACE's sub-names are resolved
        # through the shape's element map: a replaced face breaks them
        # ("?Edge1"), the fill cannot resolve its own boundary and goes
        # Invalid for good.  A COMPOUND's children are named BY POSITION
        # ("Edge1", "Edge2", ...), so the names survive the replacement
        # -- measured: the fill stays Up-to-date across a band-edge edit
        # that replaces the shape under it.
        #
        # THE NAMES ARE POSITIONS IN `shape.Edges`, NOT IN `real` (#119).
        # "EdgeN" on a compound resolves to the N-th EDGE OF THE SHAPE, so
        # a run that keeps only the non-degenerate edges and numbers them
        # 1..n names the wrong curve whenever the collapsed edge is not the
        # last one: measured on the leader-cut cell, the fill was handed the
        # collapsed edge as its second side and refused by name ("Edge1
        # meets both of its loop neighbours at the SAME end of itself").
        real = [(i, e) for i, e in enumerate(shape.Edges) if e.Length > 1e-9]
        if len(real) >= 3:
            fp.Shape = Part.Compound([shape] + [e for _i, e in real])
            fp.BoundaryEdges = ["Edge%d" % (i + 1) for i, _e in real]
        else:
            fp.Shape = shape
            fp.BoundaryEdges = []
        # the fill's boundary lives on the shape just replaced: re-point
        # it, or it breaks (see `_refresh_fill`).
        self._refresh_fill(fp)
        # A rebuilt member must not leave the document dirty: the shape,
        # the poles and the boundary names written above touch it again.
        self._purge(fp)

    @staticmethod
    def _purge(fp):
        """Clear the touch flag this execute raised.

        The properties written above (the poles, the weights, the legs,
        the shape, the boundary names) touch the object again, and a
        document that stays dirty is a document that never settles
        (#125).  The CornerBlend does the same."""
        try:
            fp.purgeTouched()
        except Exception:
            pass


def _member_pin_of(face):
    """The `(patch, corner)` the corner fill this face belongs to is PINNED
    to, or None.

    THE MEMBER AND THE 66 MUST AGREE ABOUT WHERE THE MEMBER IS (#117).  The
    corner object carries the placement (`MemberPatch` / `MemberCorner`) and
    derives its 6x6 from it; this face re-derives the SAME member from the
    SAME ring, so it has to read the same pin rather than run the automatic
    search again.  Measured on the cube-corner fixture with the member pinned
    to PatchB: without this, the face kept showing the member the search
    picks (its face area did not move when PatchB's cut moved, while the
    corner's own derivation did) -- i.e. the two surfaces disagreed, which is
    exactly the defect #117 was filed for, on the rolling construction."""
    corner = getattr(face, "Corner", None)
    patch = getattr(corner, "MemberPatch", None) if corner is not None else None
    if patch is None:
        return None
    return (patch, int(getattr(corner, "MemberCorner", 0) or 0))


def member_grid(grids):
    """(poles, weights) of the ring's TRIANGULAR MEMBER, or None.

    The member is the one ring grid with a COLLAPSED end row: six poles
    on one point (the apex the corner fill pinches at).  That is the
    only structural difference between it and the three blends, so it is
    what identifies it -- the same rule `pair_common` reads the
    degeneracy from."""
    for grid in (grids or []):
        poles = grid[0] if isinstance(grid, tuple) else grid
        weights = grid[1] if isinstance(grid, tuple) else None
        if not poles or len(poles) != 24:
            continue
        for row in range(4):
            base = poles[row * 6]
            if all((poles[row * 6 + j] - base).Length <= 1e-9
                   for j in range(1, 6)):
                return list(poles), list(weights or [])
    return None


class RollingMemberFaceViewProvider:
    """The small triangular surface's view provider (no icon of its own:
    it is a piece of the corner, not a new kind of object)."""

    def __init__(self, vobj):
        vobj.Proxy = self

    def attach(self, vobj):
        self.ViewObject = vobj
        self.Object = vobj.Object

    def updateData(self, obj, prop):
        return True

    def __getstate__(self):
        return None

    def __setstate__(self, state):
        return None


class CornerBlendViewProvider:
    def __init__(self, vobj):
        vobj.Proxy = self

    def getIcon(self):
        return iconPath

    def attach(self, vobj):
        self.ViewObject = vobj
        self.Object = vobj.Object
        self._refresh_grid(self.Object, vobj)

    def _refresh_grid(self, obj, vobj):
        """Draw the corner's control grid as a Coin node (#108).

        The grid is no longer part of Shape (execute keeps only the
        surface); the view provider draws it from the stored `Legs`, in the
        corner's own LineColor / LineWidth, and ShowGrid shows/hides the
        node (#95 -- the toggle a CornerBlend carries now, so the grid can
        be hidden exactly as a patch's can). Headless (no ViewObject) is a
        silent no-op."""
        if obj is None or vobj is None:
            return
        set_grid_display(self, vobj, list(getattr(obj, "Legs", None) or []),
                         bool(getattr(obj, "ShowGrid", True)),
                         getattr(vobj, "LineColor", None),
                         getattr(vobj, "LineWidth", None))

    def updateData(self, obj, prop):
        if prop in ("Legs", "Shape", "ShowGrid"):
            self._refresh_grid(obj, getattr(self, "ViewObject", None))
        return True

    def onChanged(self, vobj, prop):
        if prop in ("LineColor", "LineWidth"):
            self._refresh_grid(getattr(vobj, "Object", None), vobj)

    def __getstate__(self):
        return None

    def __setstate__(self, state):
        return None


class CreateCornerFill:
    """GUI command — the ring's 3 or 4 blends -> ONE FreeCAD
    `Surface::Filling` over the corner's hole (#96).

    The owner's ask is to JUDGE a one-patch corner by eye. That judgement
    needs no picker: this command takes the same selection the corner blend
    takes and lets Silk assemble the fill (measured wiring: the strips' own
    `EdgeN` boundary rows, order 1 -- see
    docs/research/silk-fill-picking.md). The whole contract (the ring, the
    boundary derivation, the named refusals, the post-build validation)
    lives in SilkWorkflowOps.create_corner_fill; this class only reads the
    selection, opens the undo transaction, and reports.

    The created object is FreeCAD's own, foreign object: it carries no Silk
    band/split bookkeeping and no Silk view provider, which is why the fill
    stays an OPT-IN next to the Silk corner rather than becoming the corner
    default. It is nevertheless part of the workbench's visible command set
    (#96, owner decision D3): the button sits beside `Silk_CreateCornerBlend`
    in Silk -> Workflow and the toolbar, so FreeCAD's `Surface::Filling` can
    be demonstrated and judged next to the Silk corner. The record of the
    earlier decision (registered but deliberately not visible) is superseded
    by this one.
    """

    def GetResources(self):
        return {'Pixmap': corner_fill_icon_path, 'MenuText': 'Silk Corner Fill',
                'ToolTip': 'Fill the corner hole with one FreeCAD '
                           'Surface::Filling over the selected ring blends, '
                           'so the surface can be judged by eye.'}

    def Activated(self):
        sel = Gui.Selection.getSelection()
        strips = [o for o in sel
                  if getattr(o, "object_type", None) in BLEND_TYPES]
        from SilkWorkflowOps import create_corner_fill
        doc = FreeCAD.ActiveDocument
        if doc is None:
            return  # nothing to put a transaction on; nothing is created
        doc.openTransaction("Silk corner fill")
        try:
            create_corner_fill(strips)
        finally:
            doc.commitTransaction()
        # create_corner_fill owns every message: its refusals name the
        # reason and leave nothing behind, its success names the fill.

    def IsActive(self):
        return Gui is not None


class CreateCornerBlend:
    """GUI command — select the 3 or 4 blends that ring a shared
    junction -> CornerBlend (ticket #91).

    The whole contract (adjudicating the ring, refusing a non-junction or
    repeated strip set by name, the idempotent "already has a corner"
    no-op) lives in SilkWorkflowOps.create_corner_blend. This class only
    reads the selection, opens the undo transaction the toolbar triad did
    not (#91), and reports."""

    def GetResources(self):
        return {'Pixmap': iconPath, 'MenuText': 'Silk Corner Blend',
                'ToolTip': 'Create the corner blend where three or four '
                           'blends ring one shared junction.'}

    def Activated(self):
        sel = Gui.Selection.getSelection()
        strips = [o for o in sel
                  if getattr(o, "object_type", None) in BLEND_TYPES]
        from SilkWorkflowOps import create_corner_blend
        doc = FreeCAD.ActiveDocument
        if doc is None:
            return  # nothing to put a transaction on; nothing is created
        known = {o.Name for o in doc.Objects}
        doc.openTransaction("Silk corner blend")
        try:
            corner = create_corner_blend(*strips)
        finally:
            doc.commitTransaction()
        if corner is None:
            return  # the resolver already printed its refusal
        if corner.Name not in known:
            FreeCAD.Console.PrintMessage(
                "Corner blend created: %s\n" % corner.Name)
        # else: the resolver returned the EXISTING corner (no-op) -- its
        # own message already reached the user; do not double-report.

    def IsActive(self):
        return Gui is not None


Gui.addCommand("Silk_CreateCornerBlend", CreateCornerBlend())
Gui.addCommand("Silk_CornerFill", CreateCornerFill())
