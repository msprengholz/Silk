"""
SilkMachinery — shared machinery core for Silk surface objects.

One reusable implementation of the machinery every patch fill shares:
subdivision (the two named band edges per axis -> subgrid pole arrays +
trimmed surfaces), blend-band selection, hidden-cell bookkeeping, and
compound display.

Patch44 (the quad fill) consumes this core for all four; BlendStrip and
the unified Blend resolve their seam (shared_seam) and seam-adjacent
subgrid cell (band_cells) through here. The unified Patch's fills (the
#37 quad and the #38 pointed fill) delegate to the same implementation
instead of reimplementing it.

Only behavior shared verbatim across consumers lives here — no object
type or geometry logic is introduced.
"""

import Part
import ArachNURBS as AN


# ---- closed-loop ordering of boundary edges (#66) ------------------------
#
# A Patch's `Edges` link list is a CYCLE, but the list itself arrives in
# whatever order the user produced it -- the task panel collects edges in
# CLICK order, the property editor lets a hand rewire them, and an old
# document restores whatever it saved. The fills walk the list as a cycle
# (edge k meets edge k+1 at a corner) and AN.orient_a_to_b can reverse an
# EDGE, but it cannot reorder the LIST. So a list whose consecutive pairs
# do not meet simply failed the fill, and the result was a valid,
# up-to-date, INVISIBLE object -- 16 of the 24 permutations of one valid
# 4-edge loop built exactly that ghost.
#
# So the cycle is DERIVED from the edges' own endpoints, here, in the
# shared core -- the one place every construction path already goes
# through (the fill), so the panel, the ops layer, the data tab and an
# old-document restore are all fixed at once.
#
# Pure geometry: no document, no objects, no console. `tol` defaults to
# the endpoint-matching tolerance a fresh Patch carries, and the caller
# decides what a None means (the fill leaves the object empty/valid and
# says why; the ops layer refuses the creation and leaves nothing
# behind).

def _edge_label(edge):
    """How a refusal names one edge: its Label, with the internal Name in
    parentheses when they differ (the #58 convention)."""
    name = getattr(edge, "Name", None) or repr(edge)
    label = getattr(edge, "Label", None)
    if label and label != name:
        return "%s (%s)" % (label, name)
    return name


def _edge_ends(edge):
    """(start, end) poles of one boundary edge, or (None, None) when it
    carries no usable poles."""
    poles = list(getattr(edge, "Poles", None) or [])
    if len(poles) < 2:
        return None, None
    return poles[0], poles[-1]


def _meets(p, q, tol):
    """Endpoint coincidence at `tol` -- AN.equalVectors' rule verbatim
    (<= tol), so this agrees with orient_a_to_b about what 'shares an
    endpoint' means."""
    return p is not None and q is not None and (q - p).Length <= tol


def _endpoint_adjacency(edges, tol):
    """adjacency[i] = the indices of the edges sharing an endpoint with
    edge i. Pure coincidence -- no document, no identity assumption."""
    ends = [_edge_ends(e) for e in edges]
    adj = [set() for _ in edges]
    for i in range(len(edges)):
        for j in range(i + 1, len(edges)):
            (a0, a1), (b0, b1) = ends[i], ends[j]
            if (_meets(a0, b0, tol) or _meets(a0, b1, tol)
                    or _meets(a1, b0, tol) or _meets(a1, b1, tol)):
                adj[i].add(j)
                adj[j].add(i)
    return adj


def _walk_cycle(adj, start):
    """The edge indices of one closed cycle through `start`, or None.

    Depth-first over the adjacency, candidates tried in INPUT ORDER, so
    the result is the lexicographically smallest cycle through `start` --
    deterministic, and identical to the input whenever the input is
    itself cyclic (the walk's first two indices are then forced by the
    input, so a rotation or a reversal of a good list comes back
    untouched). Backtracking rather than a plain greedy walk so a
    degenerate extra coincidence cannot make a fillable loop look
    unclosable.
    """
    n = len(adj)
    path = [start]
    used = {start}

    def extend():
        if len(path) == n:
            return start in adj[path[-1]]
        for j in sorted(adj[path[-1]]):
            if j in used:
                continue
            path.append(j)
            used.add(j)
            if extend():
                return True
            used.discard(j)
            path.pop()
        return False

    return list(path) if extend() else None


def loop_order(edges, tol=None):
    """(order, problem) for a boundary edge list (#66).

    `order` is the list of edges in closed-loop order with the FIRST
    collected edge leading -- or None when the edges do not close a loop,
    in which case `problem` is a ready-to-print clause naming the
    offending edges.

    The rotation rule: the walk starts at the first collected edge and
    takes the neighbours in the order they were collected. Two
    consequences fall out of that one rule, both required:
      * an ALREADY-CYCLIC list is returned as it stands, so feeding a
        good list is a genuine no-op (that is what keeps the legacy
        Patch44/Patch33 pole parity, and it is not a reserialization);
      * a clicked-around list still starts from what the user picked
        first, and otherwise follows their click order as closely as the
        geometry allows. Which way round the loop is walked is the only
        other freedom, and it does not matter: AN.orient_a_to_b reverses
        each edge, so both directions build the same surface with the
        pole indices turned around.
    """
    # Keep the caller's list object: when the input turns out to be
    # already cyclic, THAT list is what comes back, not a copy of it.
    # The no-op is structural, not a promise.
    original = edges
    edges = list(edges or [])
    if tol is None:
        tol = AN.default_tol        # what a fresh Patch starts with
    n = len(edges)
    if n < 3:
        return None, ("a closed loop needs at least 3 boundary edges, "
                      "got %d" % n)

    adj = _endpoint_adjacency(edges, tol)

    # A corner of a closed loop meets exactly two of the other edges.
    # Anything else is the actual problem, and it is per-edge, so it can
    # be named -- which is the whole point of refusing loudly.
    problems = []
    for i, edge in enumerate(edges):
        k = len(adj[i])
        if k < 2:
            problems.append(
                "%s meets only %d of the other %d edges (%s) -- the loop "
                "does not close here"
                % (_edge_label(edge), k, n - 1,
                   ", ".join(_edge_label(edges[j]) for j in sorted(adj[i]))
                   or "none"))
        elif k > 2:
            problems.append(
                "%s meets %d of the other %d edges (%s) -- a loop corner "
                "meets exactly 2, so these edges branch instead of "
                "closing"
                % (_edge_label(edge), k, n - 1,
                   ", ".join(_edge_label(edges[j]) for j in sorted(adj[i]))))
    if problems:
        return None, "; ".join(problems)

    order = _walk_cycle(adj, 0)
    if order is None or len(order) != n:
        # every edge meets exactly two, yet there is no single cycle
        # through them: two separate closed loops handed over at once.
        left = [i for i in range(n) if not order or i not in order]
        return None, ("%s close a loop of their own and do not join the "
                      "loop through %s -- a patch boundary is ONE loop"
                      % (", ".join(_edge_label(edges[i]) for i in left),
                         _edge_label(edges[0])))

    if order == list(range(n)):
        return original, None    # already in this exact cyclic order
    return [edges[i] for i in order], None


# ---- subdivision: TWO NAMED BAND EDGES per axis (#82) -------------------
#
# An axis no longer carries a LIST of split parameters. It carries two
# scalars, named for the END each one belongs to:
#
#     <Axis>Split1   this axis's band edge at its parametric-0 end
#     <Axis>Split2   this axis's band edge at its parametric-1 end
#
# A band edge is the FAR edge of the band at that end, so 0.0 on Split1
# and 1.0 on Split2 are the sentinels for "no band at this end" -- and
# they ARE the axis endpoints, which is the whole point of naming them:
# `Split1 = 0, Split2 = 1` reads as "no split on this axis" rather than
# as a magic number every reader has to interpret.
#
# WHY NAMED (#81, and #76's cap along with it). With a list, every reader
# had to CLASSIFY each value into an end, and the classification was by
# VALUE: below 0.5 is the parametric-0 end's, above it the
# parametric-1 end's, exactly 0.5 NEITHER's. That guess is the #81 bug —
# on [0.2, 0.4] it reports no band at the 1 end, even though 0.4 is
# plainly the far edge of the [0.4, 1.0] band, so the blend writes a
# third split which #76's two-entry cap then refuses and the patch goes
# Invalid. Here there is nothing left to classify: `Split1` IS the 0
# end's edge by name. #76's cap becomes a TYPE instead of a check --
# there are two properties, so a third value cannot be written at all --
# and #75's "a stored width the panel cannot read back" has no failure
# mode left either, because the property's NAME is what reads it.

# The sentinels, per slot: "this end carries no band edge". Exposed so no
# caller has to remember which endpoint belongs to which property.
NO_BAND_1 = 0.0
NO_BAND_2 = 1.0


def band_edge(value):
    """`value` as a band edge, or None when this end carries none.

    A band edge is a parametric position STRICTLY INSIDE (0, 1); the
    slot's own endpoint (0.0 on Split1, 1.0 on Split2) is the sentinel,
    and so is anything else outside the open interval -- a value that is
    not a position on this axis cannot mark an edge on it."""
    v = float(value)
    return v if 0.0 < v < 1.0 else None


def axis_splits(s1, s2):
    """The split values one axis carries, ascending — the DERIVED view of
    its two named edges, for the interval arithmetic and for messages.

    Deliberately a view and not storage: nothing writes this back as a
    list, which is what stops a list from creeping in and with it the
    classify-by-value step #81 was about. An axis whose two ends hold the
    SAME edge carries one split (the ends are indistinguishable then) --
    legal to store, degenerate for a band, and the band refusal says so."""
    edges = [v for v in (band_edge(s1), band_edge(s2)) if v is not None]
    return sorted(set(edges))


def build_intervals(s1, s2):
    """The intervals one axis is cut into by its two named edges."""
    splits = axis_splits(s1, s2)
    if not splits:
        return [(0.0, 1.0)]
    return list(zip([0.0] + splits, splits + [1.0]))


def split_pair(p, letter):
    """`(Split1, Split2)` of axis `letter` ("U" / "V") of object `p`.

    Read by NAME, so a reader cannot attach an edge to the wrong end. An
    object that has neither property -- one restored from a pre-#82 file,
    where the USplits / VSplits lists are gone and no migration is
    shipped (#82: an old document comes back with no splits, which is the
    correct neutral state), or a test stub -- reads as "no band at
    either end"."""
    return (float(getattr(p, letter + "Split1", NO_BAND_1)),
            float(getattr(p, letter + "Split2", NO_BAND_2)))


def normalize_edge_pair(s1, s2):
    """`(s1, s2, why)` — the canonical form of two named edges.

    `why` is None when the pair was already canonical, else a clause
    naming what was corrected. Two rules, both lossless:

      * a value outside [0, 1] becomes its OWN slot's sentinel, so a
        mistyped edge reads as "no band at this end" instead of
        silently becoming a position on the other end;
      * two edges that are both real and out of order are SWAPPED, so
        Split1 <= Split2 as the interval arithmetic reads them.

    The swap is only applied when BOTH ends carry a real edge: with one
    end empty, Split1 = 0.9 is a legitimate wide band at the 0 end, and
    swapping it would hand that band to the 1 end — a silent reassignment
    of the user's intent rather than a correction of its spelling.
    Geometry is identical either way (build_intervals sorts), so this is
    about which end the stored names claim."""
    v1, v2 = float(s1), float(s2)
    why = None
    if not 0.0 <= v1 <= 1.0:
        why = "%g is outside [0, 1], so this end carries no band edge" % v1
        v1 = NO_BAND_1
    elif not 0.0 <= v2 <= 1.0:
        why = "%g is outside [0, 1], so this end carries no band edge" % v2
        v2 = NO_BAND_2
    elif band_edge(v1) is not None and band_edge(v2) is not None \
            and v1 > v2:
        v1, v2 = v2, v1
        why = ("the 0 end's edge (%g) was above the 1 end's (%g); the two "
               "were swapped, which is the same geometry under the two "
               "names" % (v2, v1))
    return v1, v2, why


def band_at_end(s1, s2, ss):
    """The band edge at ONE END of an axis, or None when that end carries
    none. ss 0 -> Split1, ss 1 -> Split2.

    This is the whole of #64's "which split is this end's band" and of
    #81's positional reading, in three lines: the PROPERTY NAME says. It
    replaces `split_at_end`, whose value-threshold guess was the bug."""
    return band_edge(s1) if ss == 0 else band_edge(s2)


def build_subgrids(base_surface, u_pair, v_pair):
    """Subdivide base_surface by the two named edges on each axis.

    `u_pair` / `v_pair` are `(Split1, Split2)` — see `split_pair`.

    Returns (subgrids, subsurfaces, sub_legs):
      - subgrids:    flat 16-pole arrays, one per cell;
                     poles[U][V] == flat[U*4 + V] (FreeCAD convention).
      - subsurfaces: the trimmed sub-shapes (only truthy shapes).
      - sub_legs:    detailed grid lines for the subdivided view.
    With no edges on either axis returns ([], [], []).
    """
    subgrids = []
    subsurfaces = []
    sub_legs = []
    if not (axis_splits(*u_pair) or axis_splits(*v_pair)):
        return subgrids, subsurfaces, sub_legs
    shapes = []
    for u0, u1 in build_intervals(*u_pair):
        for v0, v1 in build_intervals(*v_pair):
            seg = base_surface.copy()
            seg.segment(u0, u1, v0, v1)
            seg_poles = seg.getPoles()
            flat = []
            for r in range(4):
                for c in range(4):
                    flat.append(seg_poles[r][c])
            subgrids.append(flat)
            sub_shape = seg.toShape()
            if sub_shape:
                shapes.append(sub_shape)
            sub_legs.extend(AN.drawGrid(flat, 4))
    return subgrids, shapes, sub_legs


# ---- blend band / shared-edge selection --------------------------------

# Boundary-edge label per adjacent corner pair. Corner i of a patch is
# Poles[0], Poles[3], Poles[15], Poles[12] in cyclic order, so boundary
# edge k runs corner k -> corner k+1; the label fixes the band split
# direction (perpendicular to the seam) and side.
_EDGE_OF = {(0, 1): "U0", (1, 2): "V1", (2, 3): "U1", (3, 0): "V0",
            (1, 0): "U0", (2, 1): "V1", (3, 2): "U1", (0, 3): "V0"}


def _cyclic_adjacent(i, j):
    """Corner indices i, j adjacent on the 4-corner cycle."""
    return (j - i) % 4 == 1 or (i - j) % 4 == 1


def shared_seam(a_c, b_c, tol=0.01):
    """Detect the shared seam between two patches from their corner poles.

    Returns (ea, eb, pairs): the boundary-edge labels on patch A and B
    plus the two matched corner pairs ([(i, j), (i2, j2)] with i~j,
    i2~j2), or None when no seam is found.

    Robust against degenerate corners (#39, criterion 6): a pointed
    patch carries its apex twice in the corner list (Poles[0] ==
    Poles[12]), so naive matched-pair collection double-counts the point
    and the sorted-ids edge lookup used to find no seam at all. This
    instead picks an adjacent cyclic pair of corners on A whose matches
    form an adjacent cyclic pair on B, requiring both pairs to be
    non-degenerate (endpoints distinct -- same-patch-coincident corners,
    i.e. the apex duplicates, are ignored as pair members).
    """
    matches = {i: [j for j in range(4)
                   if (a_c[i] - b_c[j]).Length < tol]
               for i in range(4)}
    for i in range(4):
        i2 = (i + 1) % 4
        if (a_c[i] - a_c[i2]).Length < tol:
            continue  # degenerate pair on the same patch (pointed apex)
        for j in matches[i]:
            for j2 in matches[i2]:
                if not _cyclic_adjacent(j, j2):
                    continue
                if (b_c[j] - b_c[j2]).Length < tol:
                    continue  # degenerate pair on the other patch
                ea = _EDGE_OF.get((i, i2))
                eb = _EDGE_OF.get((j, j2))
                if ea and eb:
                    return ea, eb, [(i, j), (i2, j2)]
    return None


def patch_side(pa, pb, tol=0.01):
    """Edge type and side of the shared edge as seen from pa (toward pb).

    Returns (edge_type, ss) e.g. ("V1", 1), or (None, None) when the
    patches do not share an edge.
    """
    a_c = [pa.Poles[0], pa.Poles[3], pa.Poles[15], pa.Poles[12]]
    b_c = [pb.Poles[0], pb.Poles[3], pb.Poles[15], pb.Poles[12]]
    seam = shared_seam(a_c, b_c, tol)
    if seam is None:
        return None, None
    ea = seam[0]
    return ea, (0 if ea[1] == "0" else 1)


# #76's cap, restated as a TYPE rather than a check (#82).
#
# It used to live here as `split_limit_problem`, refusing a three-entry
# list, because a list could hold three values. There is nothing left to
# refuse: an axis has two properties, one per end, and a third value
# cannot be written at all. The reasons the rule existed are now
# structural rather than enforced -- past two ends there are only two
# ends -- and the failure it used to prevent (an extra split absorbed in
# silence, so the corner blend picks a different subgrid cell, or the
# band spans cells the blend refuses while the patch reports itself
# Up-to-date and Valid) is no longer expressible. The one degenerate
# layout that remains, both ends holding the SAME edge, is not a third
# split: it collapses to one split whose two end cells are both corner
# cells, and the band refusal names it (see band_diagnosis).


def corner_cells(s1, s2, n_intervals):
    """Interval indices along one axis that are CORNER cells — reserved
    for the four-cell corner blend op (#28) and excluded from a band.

    The exclusion follows the two NAMED edges, one per end:

      - `Split1` carries the far edge of the band that reaches from the
        parametric-0 end, so it carved out interval [0, s] and that
        interval is the corner cell -> drop the FIRST one;
      - `Split2` carries the far edge of the band that reaches from the
        parametric-1 end, so it carved out [s, 1] -> drop the LAST one;
      - an end whose property holds its sentinel (0.0 on Split1, 1.0 on
        Split2) has no band attached to it, so its end cell is not a
        corner cell.

    This is what #61 generalized ("is there a 0.1? drop the first cell /
    a 0.9? drop the last"), with the values read from the ends they
    belong to rather than compared against the middle of the axis, so a
    user width like 0.2 or 0.85 needs no special case and #81's [0.2,
    0.4] is just two ends with two edges."""
    out = set()
    if band_edge(s1) is not None:
        out.add(0)
    if band_edge(s2) is not None:
        out.add(n_intervals - 1)
    return out


def band_cells(p, ea, ss):
    """Subgrid cell indices covered by a strip's band on patch p.

    The band runs along the seam in the band interval (0 or last, per
    ss). A cell at a seam end whose axis carries that end's band edge is a
    corner cell — excluded from the band (reserved for the four-cell
    corner blend op, #28).

    With two named edges per axis this is exactly ONE cell whenever the
    two ends hold DIFFERENT edges, and that is now structural rather
    than enforced: the seam-parallel axis is cut into (edges + 1)
    intervals and drops exactly one interval per edge, so one cell is
    all that is left. (Before #82 that was the multi-cell refusal #61
    wrote a message for; the arithmetic no longer produces the case.)
    """
    us = split_pair(p, "U")
    vs = split_pair(p, "V")
    nu = len(build_intervals(*us))
    nv = len(build_intervals(*vs))
    if ea[0] == "U":  # seam along U: band fixes V interval, spans U cells
        b = (nv - 1) if ss else 0
        keep_u = set(range(nu)) - corner_cells(us[0], us[1], nu)
        return [a * nv + b for a in sorted(keep_u)]
    # seam along V: band fixes U interval, spans V cells
    a = (nu - 1) if ss else 0
    keep_v = set(range(nv)) - corner_cells(vs[0], vs[1], nv)
    return [a * nv + b for b in sorted(keep_v)]


def _edges_str(p, letter):
    """`USplit1 = 0.1, USplit2 = 0.9` — one axis as the data tab shows it."""
    s1, s2 = split_pair(p, letter)
    return "%s = %g, %s = %g" % (letter + "Split1", s1,
                                 letter + "Split2", s2)


def band_diagnosis(p, ea, ss):
    """Actionable, fact-by-fact diagnosis of patch p's band at seam
    ea/ss — the axis roles, both named edges on each, how many intervals
    they make, which cells the corner exclusion drops, and what single
    edit would leave a one-cell band. Pure data -> string, no console
    output; SilkBlend owns the message that carries it (#61)."""
    name = getattr(p, "Name", "?")
    us = split_pair(p, "U")
    vs = split_pair(p, "V")
    nu, nv = len(build_intervals(*us)), len(build_intervals(*vs))
    if ea[0] == "U":  # seam along U: band fixes a V interval, spans U
        band_letter, along_letter, n_along = "V", "U", nu
        along = us
        band_ivs = build_intervals(*vs)
    else:             # seam along V: band fixes a U interval, spans V
        band_letter, along_letter, n_along = "U", "V", nv
        along = vs
        band_ivs = build_intervals(*us)
    # the band is the first (side 0) or the last (side 1) interval
    band_iv = band_ivs[0] if ss == 0 else band_ivs[-1]
    width = band_iv[1] - band_iv[0]
    excluded = sorted(corner_cells(along[0], along[1], n_along))
    left = n_along - len(excluded)
    if band_at_end(*split_pair(p, band_letter), ss) is None:
        fix = ("the band axis has no edge at this end, so its band cell is "
               "the whole surface -- set %s.%sSplit%d to %g to give this "
               "end a band of its own."
               % (name, band_letter, ss + 1, 0.9 if ss else 0.1))
    elif band_edge(along[0]) is not None \
            and band_edge(along[0]) == band_edge(along[1]):
        fix = ("both ends of the seam-parallel axis hold the same edge %g, "
               "so the axis carries ONE split and both of its end cells are "
               "corner cells -- set %s.%sSplit2 = %g (its default, no band "
               "at that end) to leave the other end's cell in the band."
               % (band_edge(along[0]), name, along_letter, NO_BAND_2))
    else:
        fix = ("a one-cell band needs the two ends of the seam-parallel "
               "axis to carry DIFFERENT edges (%s.%sSplit1 = %g and "
               "%s.%sSplit2 = %g is such a pair); with them the band is "
               "exactly the cell of width %g."
               % (name, along_letter, band_edge(along[0]) or NO_BAND_1,
                  along_letter, along_letter,
                  band_edge(along[1]) or NO_BAND_2, width))
    return (
        "seam %s (band at parametric %d): band axis %s -> %d "
        "interval(s), width %g.\n"
        "      seam-parallel axis %s -> %d interval(s); corner "
        "cell(s) %s excluded, %d left in the band.\n"
        "      %s"
        % (ea, ss, _edges_str(p, band_letter), len(band_ivs), width,
           _edges_str(p, along_letter), n_along, excluded, left, fix))


# ---- hidden-cell bookkeeping ------------------------------------------

def ensure_hidden_idxs_property(p):
    """Ensure patch p carries the _HiddenSubgridIdxs property.

    The superseded single-index _HideSubgridIdx is removed first. Used by
    BlendStrip (and, later, every fill) when it hides the subgrid cells
    it covers.
    """
    try:
        p.removeProperty("_HideSubgridIdx")
    except Exception:
        pass
    if not hasattr(p, "_HiddenSubgridIdxs"):
        p.addProperty("App::PropertyIntegerList", "_HiddenSubgridIdxs", "Internal",
                      "subgrid cell indices hidden by blends")
        p.setEditorMode("_HiddenSubgridIdxs", 1)


# ---- compound display --------------------------------------------------

def build_display(fobj, base_shape, sub_shapes, base_legs, sub_legs,
                  has_subgrids):
    """Compose the patch display Shape from the surface/grid toggles.

    Writes fobj.Shape with the compound of the visible surface (the base
    surface, or the non-hidden subgrid surfaces when ShowSubgrids) plus
    the chosen grid lines. Honors fobj.ShowSurface / ShowSubgrids /
    ShowGrid / AutoHideBlend the way Patch44 always has.
    """
    hide_idxs = set(list(getattr(fobj, "_HiddenSubgridIdxs", []) or []))
    if not getattr(fobj, "AutoHideBlend", True):
        hide_idxs = set()
    else:
        legacy = getattr(fobj, "_HideSubgridIdx", -1)
        if isinstance(legacy, int) and legacy >= 0:
            hide_idxs.add(legacy)

    shapes = []
    if getattr(fobj, "ShowSurface", True):
        if getattr(fobj, "ShowSubgrids", False) and sub_shapes:
            for i, sub in enumerate(sub_shapes):
                if i not in hide_idxs:
                    shapes.append(sub)
        else:
            shapes.append(base_shape)

    draw_legs = sub_legs if has_subgrids and getattr(fobj, "ShowSubgrids", False) \
        else base_legs
    if getattr(fobj, "ShowGrid", True) and draw_legs:
        for leg in draw_legs:
            if hasattr(leg, "toShape"):
                shapes.append(leg.toShape())

    if shapes:
        try:
            fobj.Shape = Part.Compound(shapes)
        except Exception:
            if len(shapes) == 1:
                fobj.Shape = shapes[0]
            else:
                fobj.Shape = Part.Shape(shapes)
    else:
        fobj.Shape = Part.Shape()
