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


def _ends_touching(ends, i, j, tol):
    """The ends of edge i that touch edge j: a subset of {0, 1}.

    End-indexed, not point-indexed: the question the closure proof
    (#68) asks is WHICH END of an edge a neighbour arrives at, so a
    set per (i, j) pair is what the cycle check consumes."""
    return {e for e in (0, 1)
            if any(_meets(ends[i][e], ends[j][f], tol) for f in (0, 1))}


def _cycle_joins_corner_to_corner(order, ends, tol):
    """True when every edge of the cycle joins its two neighbours at
    its two DIFFERENT ends (#68).

    Adjacency alone cannot say the loop closes: three edges fanned out
    of ONE point are pairwise-adjacent (every pair meets at that
    point), so for n=3 the "meets exactly 2 of the other 2" check is
    vacuous and any permutation walks as a cycle — while geometrically
    no ordering chains corner to corner. The distinguishing fact is
    per-edge: in a real loop each edge is entered at one end and left
    at the other; in a fan both neighbours arrive at the SAME end and
    the edge's far end plays no part in the loop."""
    n = len(order)
    for k, i in enumerate(order):
        p = _ends_touching(ends, i, order[k - 1], tol)
        s = _ends_touching(ends, i, order[(k + 1) % n], tol)
        if p == s and len(p) == 1:
            return False
    return True


def _walk_cycle(adj, start, ok=None):
    """The edge indices of one closed cycle through `start`, or None.

    Depth-first over the adjacency, candidates tried in INPUT ORDER, so
    the result is the lexicographically smallest cycle through `start` --
    deterministic, and identical to the input whenever the input is
    itself cyclic (the walk's first two indices are then forced by the
    input, so a rotation or a reversal of a good list comes back
    untouched). Backtracking rather than a plain greedy walk so a
    degenerate extra coincidence cannot make a fillable loop look
    unclosable.

    `ok`, when given, filters COMPLETE cycles and the search keeps
    backtracking past one it rejects (#68) — so an extra coincidence
    that pinches the lexicographically-first cycle falls through to a
    later cycle that does not, instead of to a refusal.
    """
    n = len(adj)
    path = [start]
    used = {start}

    def extend():
        if len(path) == n:
            return start in adj[path[-1]] and (
                ok is None or ok(list(path)))
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

    Cyclic means CYCLIC, not merely pairwise-adjacent (#68): the found
    cycle must join corner to corner — every edge entered at one end
    and left at the other. Three edges fanned out of a single point
    are pairwise-adjacent (for n=3 the per-edge "meets exactly 2 of
    the other 2" is vacuously true), yet no ordering of them chains;
    that used to slip through and build a patch disagreeing with its
    own geometry. Now every cycle the walk offers is checked, and a
    selection whose only cycles pinch is refused per edge, named.
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

    # Closure is corner-to-corner, not merely pairwise (#68): the walk
    # offers only cycles where every edge is entered at one end and
    # left at the other. For n=3 the adjacency checks above cannot see
    # the difference -- a fan of three edges out of one point has
    # every edge meeting exactly the other two -- so this is the check
    # that actually refuses it, per edge and named.
    ends = [_edge_ends(e) for e in edges]
    order = _walk_cycle(
        adj, 0, lambda o: _cycle_joins_corner_to_corner(o, ends, tol))
    if order is None or len(order) != n:
        # A cycle exists in the adjacency, but every one of them
        # pinches: some edge joins BOTH of its neighbours at the same
        # end of itself (#68). Say THAT, not "does not close" --
        # the distinction is the whole diagnosis.
        bare = _walk_cycle(adj, 0)
        if bare is not None and len(bare) == n:
            pinched = []
            for k, i in enumerate(bare):
                p = _ends_touching(ends, i, bare[k - 1], tol)
                s = _ends_touching(ends, i, bare[(k + 1) % n], tol)
                if p == s and len(p) == 1:
                    pinched.append(
                        "%s meets both of its loop neighbours at the "
                        "SAME end of itself (its other end plays no "
                        "part in the loop) -- a boundary edge joins "
                        "its two neighbours at its two different ends,"
                        " corner to corner"
                        % _edge_label(edges[i]))
            return None, "; ".join(pinched)
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

    Returns (subgrids, subgrid_weights, subsurfaces, sub_legs):
      - subgrids:        flat 16-pole arrays, one per cell;
                         poles[U][V] == flat[U*4 + V] (FreeCAD convention).
      - subgrid_weights: the matching flat 16-weight arrays (#107). The
                         cell is a RATIONAL net whenever the patch is:
                         an arc edge makes the base surface rational, so
                         a pole-only cell is not the cell — the unit-weight
                         cubic through the same 4 poles is a different
                         curve (0.39 mm out at the middle of a 90 deg arc,
                         R=10), which is exactly what a blend fed `[1.0]*4`
                         drew. Same shape and order as `subgrids`.
      - subsurfaces:     the trimmed sub-shapes (only truthy shapes).
      - sub_legs:        detailed grid lines for the subdivided view.
    With no edges on either axis returns ([], [], [], []).
    """
    subgrids = []
    subgrid_weights = []
    subsurfaces = []
    sub_legs = []
    if not (axis_splits(*u_pair) or axis_splits(*v_pair)):
        return subgrids, subgrid_weights, subsurfaces, sub_legs
    shapes = []
    for u0, u1 in build_intervals(*u_pair):
        for v0, v1 in build_intervals(*v_pair):
            seg = base_surface.copy()
            seg.segment(u0, u1, v0, v1)
            seg_poles = seg.getPoles()
            seg_weights = seg.getWeights()
            flat = []
            flat_weights = []
            for r in range(4):
                for c in range(4):
                    flat.append(seg_poles[r][c])
                    flat_weights.append(float(seg_weights[r][c]))
            subgrids.append(flat)
            subgrid_weights.append(flat_weights)
            sub_shape = seg.toShape()
            if sub_shape:
                shapes.append(sub_shape)
            sub_legs.extend(AN.drawGrid(flat, 4))
    return subgrids, subgrid_weights, shapes, sub_legs


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


def corners_of(p):
    """The four boundary corners of patch `p` in cyclic order --
    Poles[0], Poles[3], Poles[15], Poles[12], i.e. boundary edge k runs
    corner k -> corner k+1. One expression so every reader of "which
    side" starts from the same corners."""
    return [p.Poles[0], p.Poles[3], p.Poles[15], p.Poles[12]]


def _side(ss_label):
    """The 0/1 end a boundary-side label's digit names."""
    return 0 if ss_label == "0" else 1


def patch_side(pa, pb, tol=0.01):
    """Edge type and side of the shared edge as seen from pa (toward pb).

    Returns (edge_type, ss) e.g. ("V1", 1), or (None, None) when the
    patches do not share an edge.

    **From the PAIR alone, so it can only ever name ONE seam (#83).**
    `shared_seam` walks the corners and returns the FIRST adjacent pair
    both patches share, so a pair sharing TWO edges -- a closed ring, the
    tube -- answers ('U0', 0) for both directions and for both of its
    seams. It is the right answer for every caller that genuinely holds
    nothing but a patch pair; a caller that knows WHICH seam it means
    must use `side_of_edge` (or SilkBlend's `_resolve_seam`, which
    prefers the blend's pinned Edge the same way).
    """
    a_c = corners_of(pa)
    b_c = corners_of(pb)
    seam = shared_seam(a_c, b_c, tol)
    if seam is None:
        return None, None
    ea = seam[0]
    return ea, _side(ea[1])


def seam_from_edge(a_c, b_c, ep0, ep1, tol=0.01):
    """Pin the seam to ONE given Edge's endpoint poles (#39 decision C):
    both endpoints must sit (within tol) on a distinct, cyclically
    adjacent corner pair of BOTH patches. Purely geometric -- the Edge
    object identity is irrelevant (patches may share geometry without
    sharing the same Edge object). Returns (ea, eb, pairs) or None.

    Lives here, not in SilkBlend, because `side_of_edge` is the same
    question asked by a reader that has no Blend to carry the pin."""
    a0 = [i for i in range(4) if (a_c[i] - ep0).Length < tol]
    a1 = [i for i in range(4) if (a_c[i] - ep1).Length < tol]
    b0 = [i for i in range(4) if (b_c[i] - ep0).Length < tol]
    b1 = [i for i in range(4) if (b_c[i] - ep1).Length < tol]
    for i0 in a0:
        for i1 in a1:
            if not _cyclic_adjacent(i0, i1):
                continue
            if (a_c[i0] - a_c[i1]).Length < tol:
                continue  # degenerate pair on A (pointed apex)
            for j0 in b0:
                for j1 in b1:
                    if not _cyclic_adjacent(j0, j1):
                        continue
                    if (b_c[j0] - b_c[j1]).Length < tol:
                        continue  # degenerate pair on B
                    ea = _EDGE_OF.get((i0, i1))
                    eb = _EDGE_OF.get((j0, j1))
                    if ea and eb:
                        return ea, eb, [(i0, j0), (i1, j1)]
    return None


def side_of_edge(pa, pb, edge, tol=0.01):
    """(edge_type, ss) of the GIVEN `edge` as seen from pa (toward pb),
    e.g. ("V1", 1); (None, None) when `edge` is None, carries no poles, or
    does not close a corner pair on both patches.

    The edge-aware twin of `patch_side` (#83). `patch_side` throws away
    WHICH shared edge it resolved, so a pair sharing TWO seams gets one
    answer for both of them; carrying the edge through instead is what
    lets a reader that already holds its seam name that seam's side. On
    the tube the two seams land on different sides of each patch, so the
    two answers are different properties, and a reader that re-derived
    the side from the pair edited the wrong band -- and attributed the
    wrong cells to the sibling blend."""
    if edge is None:
        return None, None
    ep = list(getattr(edge, "Poles", []) or [])
    if len(ep) < 4:
        return None, None
    seam = seam_from_edge(corners_of(pa), corners_of(pb), ep[0], ep[3], tol)
    if seam is None:
        return None, None
    ea = seam[0]
    return ea, _side(ea[1])


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


# ---- the rolling corner: splitting a blend ALONG its seam (#119) -------
#
# The maintainer's rolling corner (video episode 51) cuts each edge
# blend along its seam and re-creates the rest of the band, so the
# junction ends up with two zones: a small fillet that rolls into a large
# one.  The cut position is a "rolling leader" -- a position ON THE SEAM
# CURVE, measured from the junction corner.
#
# PARAMETER SPACE (stated once, used everywhere): the leader is a
# fraction of the SEAM CURVE'S OWN parameter, measured from the
# junction corner end.  The patch's base surface is a bicubic Bezier and
# a boundary side of it is a cubic Bezier curve whose parameter IS that
# side's surface coordinate, so "0.25 of the way along the seam curve"
# is the surface coordinate 0.25 (or 0.75, measured from the other end).
# It is NOT the band depth (the setback) and NOT an arc-length fraction:
# the maintainer's own tool places the cut by a curve position, and the
# curve's own parameter is what a Bezier segment carries.

# The two pieces a split blend is cut into.  `CORNER_PIECE` is the piece
# that still reaches the junction corner; `OUTER_PIECE` is the rest.
CORNER_PIECE = "corner"
OUTER_PIECE = "outer"
LEADER_PIECES = (CORNER_PIECE, OUTER_PIECE)


def seam_axis_roles(ea):
    """('U'|'V', 'U'|'V') -- the seam-parallel axis and the band axis.

    A seam along U is crossed by the band, so the band lives on the V
    axis; a seam along V is the other way round."""
    return ("U", "V") if ea[0] == "U" else ("V", "U")


def band_extent(p, ea, ss):
    """((along_lo, along_hi), (band_lo, band_hi), corner_end) or (None, why).

    The band's interval ACROSS the seam, the band's interval ALONG the
    seam, and which parametric end of the seam carries the junction
    corner (0 or 1).

    The band is ONE cell (#82), so the along-seam axis has exactly one
    corner cell at the junction end and the band's own along-seam extent
    is the interval next to it.  An axis with a corner cell at BOTH ends
    (or none) cannot say which end the junction is at -- refused by name
    rather than guessed."""
    along_letter, band_letter = seam_axis_roles(ea)
    along_pair = split_pair(p, along_letter)
    band_pair = split_pair(p, band_letter)
    along_ivs = build_intervals(*along_pair)
    band_ivs = build_intervals(*band_pair)
    corners = corner_cells(*along_pair, len(along_ivs))
    name = getattr(p, "Name", "?")
    if len(corners) != 1:
        return None, ("the band on %s has %d corner cells on its %s axis, "
                      "so it does not reach exactly one junction corner"
                      % (name, len(corners), along_letter))
    idx = next(iter(corners))
    corner_set = set(corners)
    if idx == 0:
        corner_end = 0
    elif idx == len(along_ivs) - 1:
        corner_end = 1
    else:
        return None, ("the band on %s has its corner cell in the middle of "
                      "the %s axis" % (name, along_letter))
    if not band_ivs:
        return None, "the band on %s has no interval" % name
    keep = [i for i in range(len(along_ivs)) if i not in corner_set]
    if len(keep) != 1:
        return None, ("the band on %s covers %d cells along its %s axis "
                      "(exactly 1 is required)"
                      % (name, len(keep), along_letter))
    along_lo, along_hi = along_ivs[keep[0]]
    band_lo, band_hi = band_ivs[0 if ss == 0 else -1]
    return (along_lo, along_hi), (band_lo, band_hi), corner_end


def leader_cut(p, ea, ss, leader):
    """(cut_parameter, corner_end) or (None, why).

    Where the seam curve is cut for a leader `leader` (a fraction of the
    seam curve's own parameter, measured from the junction corner).  The
    cut must fall inside the band's own along-seam extent: a leader
    inside the corner cell would cut where the corner blend's own cell
    lives, and that is refused by name."""
    ext = band_extent(p, ea, ss)
    if ext[0] is None:
        return None, ext[1]
    (along_lo, along_hi), _band, corner_end = ext
    if not 0.0 < float(leader) < 1.0:
        return None, ("the leader %r is not a position inside the seam "
                      "curve (0, 1)" % (leader,))
    cut = float(leader) if corner_end == 0 else 1.0 - float(leader)
    if not (along_lo < cut < along_hi):
        return None, ("the leader %g falls at %g on the seam, outside the "
                      "band's own extent (%g .. %g)"
                      % (float(leader), cut, along_lo, along_hi))
    return cut, corner_end


def split_band_cells(base_surface, p, ea, ss, leader):
    """((corner_poles, corner_weights), (outer_poles, outer_weights), why).

    The band's cell cut at `leader` into the two pieces a split blend is
    made of: the corner-side piece (the band's own along-seam extent up
    to the leader) and the outer piece (the rest).

    The cut is an exact knot line of BOTH nets -- the base surface is
    SEGMENTED (`BSplineSurface.segment`, the same machinery
    `build_subgrids` uses), not re-fitted -- so the two pieces share the
    cut curve exactly and meet with C0 continuity there.

    `base_surface` is the patch's own base surface (a Bezier patch); the
    patch object itself is never modified."""
    cut_info = leader_cut(p, ea, ss, leader)
    if cut_info[0] is None:
        return None, None, cut_info[1]
    cut, corner_end = cut_info
    ext = band_extent(p, ea, ss)
    (along_lo, along_hi), (band_lo, band_hi) = ext[0], ext[1]
    along_letter, _band_letter = seam_axis_roles(ea)
    if corner_end == 0:
        corner_span = (along_lo, cut)
        outer_span = (cut, along_hi)
    else:
        corner_span = (cut, along_hi)
        outer_span = (along_lo, cut)
    if along_letter == "U":
        boxes = ((corner_span[0], corner_span[1], band_lo, band_hi),
                 (outer_span[0], outer_span[1], band_lo, band_hi))
    else:
        boxes = ((band_lo, band_hi, corner_span[0], corner_span[1]),
                 (band_lo, band_hi, outer_span[0], outer_span[1]))
    out = []
    for (u0, u1, v0, v1) in boxes:
        seg = base_surface.copy()
        seg.segment(u0, u1, v0, v1)
        poles = seg.getPoles()
        weights = seg.getWeights()
        flat = []
        flat_w = []
        for u in range(4):
            for v in range(4):
                flat.append(poles[u][v])
                flat_w.append(float(weights[u][v]))
        out.append((flat, flat_w))
    return out[0], out[1], None


# ---- the 4-strip corner ring and its subgrid chain (#91) ----------------
#
# Where four Patches meet at a shared junction, the four ring Blend strips
# enclose the corner cell. Upstream Silk builds that corner from FOUR 3x3
# subgrids -- `SubGrid33_2Grid64` over each consecutive strip pair, then
# `ControlGrid66_4Sub` to assemble the 6x6 -- and the surface comes from
# `CubicSurface_66`. That chain is a genuine C1-ish 4-sided blend, not the
# boundary-only `ControlGrid66_4` fill #28 shipped.
#
# This is a newer, faithful PORT of the two upstream classes' execute()
# bodies into Silk's own machinery. The legacy classes are restore shims
# (#7) and are never called at runtime; they remain the oracle (a test
# feeds both the same grids and requires pole parity).
#
# Grid convention (confirmed, not assumed): each strip stores its blend's
# control net as 4 rows (V, along the seam) x 6 poles (U, across the
# band), flat `V * 6 + U` -- exactly the 6-wide x 4-tall layout
# `SubGrid33_2Grid64` reads, whose four corners are flat 0 / 5 / 18 / 23.
#
# Everything here is pure geometry: no document, no objects, no console.

# The flat corner indices of a 24-pole 4x6 grid, in upstream's corner
# order ([0, 5, 18, 23] = (V0U0, V0U5, V3U0, V3U5)).
CORNER_IDX = (0, 5, 18, 23)

# The parametric ends of the junction seam row after orientation: every
# strip's junction-end row is placed at V = 3 (`_orient_junction_row`),
# and upstream's `SubGrid33_2Grid64` only accepts the shared corner at
# (V3, U5) on the first grid and (V3, U0) on the second. `3` is flat 23,
# `2` is flat 18.
CORNER_COMMON = (3, 2)


def _corner_pts(grid):
    return [grid[k] for k in CORNER_IDX]


def reverse_grid_rows(poles, weights):
    """A 24-pole 4x6 grid with its V (row) order reversed.

    The same strip surface with v -> 1 - v: used to bring a strip's
    junction-end row to V = 3 so the subgrid chain's fixed index
    convention applies to every strip in the ring (#91)."""
    p = [poles[(3 - v) * 6 + u] for v in range(4) for u in range(6)]
    w = [weights[(3 - v) * 6 + u] for v in range(4) for u in range(6)]
    return p, w


def orient_junction_row(poles, weights, junction_row):
    """The 24-pole grid with its junction-end row at V = 3.

    `junction_row` (0 or 3) is the row the ring's corner cell sits
    against, derived by the caller from the patches' band cells. A grid
    already carrying it at row 3 is returned UNCHANGED (same objects), so
    the canonical layout takes the byte-identical path."""
    if junction_row == 3:
        return list(poles), list(weights)
    if junction_row != 0:
        return None, None
    return reverse_grid_rows(poles, weights)


def _collapsed_end_row(slots):
    """True when `slots` is exactly the two corner slots of ONE end row of
    a 24-pole grid: {0, 1} (V0 row) or {2, 3} (V3 row) of CORNER_IDX.

    A degenerate member whose whole junction row collapses onto one point
    presents those two slots at the same place -- that is the only
    duplication the ring chain can read, and telling it apart from two
    genuinely distinct shared corners is what `pair_common` needs."""
    return sorted(slots) in ([0, 1], [2, 3])


def pair_common(grid_0, grid_1, tol):
    """(i, j): the corner of grid_0 that coincides with the corner of
    grid_1, as corner INDICES into CORNER_IDX, at `tol`.

    Returns ((i, j), None) or (None, reason). A single geometric match is
    the ordinary case. The triangular 4th member of a 3-valent corner is
    DEGENERATE at its junction end: its whole end row collapses onto one
    point, so BOTH corner slots of that row sit on the neighbour's shared
    corner and the scan finds two matches. That case is admitted by the
    degeneracy rule below; upstream merely printed a warning and kept the
    last match (then tripped over an unbound local), and a strict refusal
    of it is what kept the 3-valent build red.

    DEGENERACY RULE -- multiple matches are admissible only when

      * every match resolves to ONE and the same point (a genuinely
        ambiguous pair of DISTINCT shared corners still refuses), and
      * exactly one grid presents the duplicated slots, and those slots
        are the two corners of one end ROW (a collapsed end row, the
        member's junction row) -- two grids each holding duplicate slots
        (both collapsed, or an apex repeated across a COLUMN) still
        refuse, and
      * the returned pairing is one the subgrid reader consumes: the
        ring-canonical `CORNER_COMMON` = (3, 2), or its mirror (2, 3) for
        a ring traversed the other way. Anything else is ambiguous and
        refuses.

    The caller (`corner_grid`) decides which ring direction is canonical:
    it tries the (3, 2) reading first and the all-mirrored (2, 3) reading
    second, so a degenerate member works in a ring built either way
    round."""
    c0, c1 = _corner_pts(grid_0), _corner_pts(grid_1)
    matches = [(i, j) for i in range(4) for j in range(4)
               if (c0[i] - c1[j]).Length <= tol]
    if not matches:
        return None, ("the two grids share no corner at tolerance %g" % tol)
    if len(matches) == 1:
        return matches[0], None

    ambiguous = ("the two grids share more than one corner at tolerance "
                 "%g" % tol)
    i_slots = sorted({i for i, _ in matches})
    j_slots = sorted({j for _, j in matches})
    point_0, point_1 = c0[matches[0][0]], c1[matches[0][1]]
    for i, j in matches:
        if (c0[i] - point_0).Length > tol or (c1[j] - point_1).Length > tol:
            return None, ambiguous          # two DISTINCT shared corners
    grid_0_degenerate = len(j_slots) == 1 and _collapsed_end_row(i_slots)
    grid_1_degenerate = len(i_slots) == 1 and _collapsed_end_row(j_slots)
    if grid_0_degenerate == grid_1_degenerate:
        # neither is a collapsed end row, or both are: nothing here picks
        # a pairing, so the overlap is genuine ambiguity.
        return None, ambiguous
    for candidate in (CORNER_COMMON, (CORNER_COMMON[1], CORNER_COMMON[0])):
        if candidate in matches:
            return candidate, None
    return None, ambiguous


def subgrid33_2grid64(poles_0, weights_0, poles_1, weights_1, tol=1e-6):
    """One corner pair -> its 3x3 subgrid (#91).

    Faithful port of `ArachNURBS.SubGrid33_2Grid64.execute` (adjust_0 /
    adjust_1 = 0, reverse = False, which is every use in the corner
    chain): find the shared corner, read the two seam rows that form the
    V at it, extrapolate the two interior rows from tangent ratios and
    average them, and cross-multiply the two boundary weights times the
    shared corner weight.

    Returns (poles9, weights9, None) or (None, None, reason)."""
    g0 = list(poles_0)
    g1 = list(poles_1)
    w0 = list(weights_0)
    w1 = list(weights_1)
    if not (len(g0) == len(w0) == len(g1) == len(w1) == 24):
        return None, None, ("a corner pair needs two 24-pole 4x6 grids "
                            "(got %d/%d)" % (len(g0), len(g1)))

    common, why = pair_common(g0, g1, tol)
    if common is None:
        return None, None, why
    # upstream swaps the two grids when the shared corner sits on the
    # "wrong" pair of corners, then re-finds it. Ported as a swap of the
    # local grids, so no property is ever written.
    if common[0] in (1, 2) and common[1] in (0, 3):
        g0, g1 = g1, g0
        w0, w1 = w1, w0
        common, why = pair_common(g0, g1, tol)
        if common is None:
            return None, None, why

    i, j = common
    if i == 0:
        v_col0 = [g0[0], g0[1], g0[2]]
        v_col0_w = [w0[0], w0[1], w0[2]]
        v_col1 = [g0[6], g0[7], g0[8]]
    elif i == 3:
        v_col0 = [g0[23], g0[22], g0[21]]
        v_col0_w = [w0[23], w0[22], w0[21]]
        v_col1 = [g0[17], g0[16], g0[15]]
    else:
        return None, None, ("a shared corner sits on a cross-seam side "
                            "(corner %d on the first grid); the ring is not "
                            "consistently oriented" % i)

    if j == 1:
        u_row0 = [g1[5], g1[4], g1[3]]
        u_row0_w = [w1[5], w1[4], w1[3]]
        u_row1 = [g1[11], g1[10], g1[9]]
    elif j == 2:
        u_row0 = [g1[18], g1[19], g1[20]]
        u_row0_w = [w1[18], w1[19], w1[20]]
        u_row1 = [g1[12], g1[13], g1[14]]
    else:
        return None, None, ("a shared corner sits on a cross-seam side "
                            "(corner %d on the second grid); the ring is not "
                            "consistently oriented" % j)

    span_v = (v_col1[0] - v_col0[0]).Length
    span_u = (u_row1[0] - u_row0[0]).Length
    if span_v <= 0.0 or span_u <= 0.0:
        return None, None, ("a degenerate seam row feeds this corner (two "
                            "coincident poles)")
    u_tan_ratio = (u_row0[1] - u_row0[0]).Length / span_v
    v_tan_ratio = (v_col0[1] - v_col0[0]).Length / span_u

    p00 = u_row0[0]
    p01 = u_row0[1]
    p02 = u_row0[2]
    p10 = v_col0[1]
    p20 = v_col0[2]
    p11_u = p01 + (u_row0[1] - u_row1[1]) * v_tan_ratio
    p12 = p02 + (u_row0[2] - u_row1[2]) * v_tan_ratio
    p11_v = p10 + (v_col0[1] - v_col1[1]) * u_tan_ratio
    p21 = p20 + (v_col0[2] - v_col1[2]) * u_tan_ratio
    p11 = (p11_u + p11_v) * 0.5
    p22 = ((p12 + (p21 - p11)) + (p21 + (p12 - p11))) * 0.5

    w00 = u_row0_w[0]
    w01 = u_row0_w[1]
    w02 = u_row0_w[2]
    w10 = v_col0_w[1]
    w20 = v_col0_w[2]
    w11 = w01 * w10
    w12 = w02 * w10
    w21 = w01 * w20
    w22 = w02 * w20

    return ([p00, p01, p02, p10, p11, p12, p20, p21, p22],
            [w00, w01, w02, w10, w11, w12, w20, w21, w22], None)


# The 6x6 assembly map of `ControlGrid66_4Sub.execute`: each 3x3 subgrid
# owns one corner of the 6x6, and the two subgrids that share an edge
# contribute half of it (one reads its own rows, the neighbour its
# columns). Entry k is (subgrid index, pole index within that subgrid).
_CG66_MAP = [
    (0, 0), (0, 1), (0, 2), (1, 6), (1, 3), (1, 0),
    (0, 3), (0, 4), (0, 5), (1, 7), (1, 4), (1, 1),
    (0, 6), (0, 7), (0, 8), (1, 8), (1, 5), (1, 2),
    (3, 2), (3, 5), (3, 8), (2, 8), (2, 7), (2, 6),
    (3, 1), (3, 4), (3, 7), (2, 5), (2, 4), (2, 3),
    (3, 0), (3, 3), (3, 6), (2, 2), (2, 1), (2, 0),
]


def control_grid66_4sub(subgrids):
    """Four 3x3 subgrids -> the assembled 6x6 (poles36, weights36).

    Port of `ArachNURBS.ControlGrid66_4Sub.execute`, verbatim index for
    index (`_CG66_MAP` is its pole list read as (subgrid, pole) pairs)."""
    poles, weights = [], []
    for si, k in _CG66_MAP:
        sub_p, sub_w = subgrids[si]
        poles.append(sub_p[k])
        weights.append(sub_w[k])
    return poles, weights


# ---- the degenerate-side cap smoothing (3-valent fold fix) ---------------
#
# A 3-valent corner ring carries a triangular 4th member whose junction row
# COLLAPSES onto the ring's shared corner (`control_grid64_3_1`'s
# p30..p35 = set_poles[15] row). `subgrid33_2grid64` then extrapolates the
# subgrid interiors PAST that collapsed row (`p11_v = p10 + (v_col0[1] -
# v_col1[1]) * u_tan_ratio` and friends) -- correct for a regular pair, but
# past a collapsed end row the extrapolation pushes the corner net's
# member-side rows BEYOND the apex. On the cube-corner fixture that makes
# the cap double over near the apex: the normal field flips (measured, see
# Tests/test_cube_corner_3valent.py).
#
# The fix keeps the collapsed boundary and the three strip-side rows and
# REPLACES the eight interior poles of the two member-side rows with the
# least-squares projection of the TRANSFINITE (Coons) fill of the corner's
# own boundary loop. The Coons fill is fold-free on the fixture (0
# flips at n=39/81 and on the exact net), and the seam OPPOSITE the member
# keeps its exact G1 and curvature because those read the first three
# control rows only -- the fix never touches rows 0..2.
#
# Weights are carried: the solve is the rational least-squares with the
# assembled net's own weights held FIXED (a rational basis function is
# `N_i N_j w_ij / W`), so only the pole positions move and the weight
# channel stays exactly the subgrid chain's. If the solve is not finite
# the input is returned unchanged -- the smoothing must never break a
# build that the upstream construction could complete.

_KNOTS6 = [0.0, 0.0, 0.0, 0.0, 1.0 / 3.0, 2.0 / 3.0, 1.0, 1.0, 1.0, 1.0]


def _bspline_basis(i, p, u, knots):
    """Cox-de Boor basis value N_{i,p}(u) (clamped end: u == 1 allowed)."""
    if p == 0:
        if knots[i] <= u < knots[i + 1]:
            return 1.0
        if u >= knots[-1] and u > knots[i] and knots[i + 1] >= knots[-1]:
            return 1.0
        return 0.0
    left = 0.0
    if knots[i + p] > knots[i]:
        left = ((u - knots[i]) / (knots[i + p] - knots[i])
                * _bspline_basis(i, p - 1, u, knots))
    right = 0.0
    if knots[i + p + 1] > knots[i + 1]:
        right = ((knots[i + p + 1] - u) / (knots[i + p + 1] - knots[i + 1])
                 * _bspline_basis(i + 1, p - 1, u, knots))
    return left + right


def _basis6(u):
    """The six degree-3 basis values at `u` on `_KNOTS6`."""
    return [_bspline_basis(i, 3, u, _KNOTS6) for i in range(6)]


def _collapsed_side(poles36, tol):
    """The name of the 6x6 side whose six poles all coincide ('u0', 'u1',
    'v0', 'v1'), or None. The triangular member's collapsed junction row
    lands on exactly one side of the assembled corner."""
    sides = {
        "u0": [v * 6 + 0 for v in range(6)],
        "u1": [v * 6 + 5 for v in range(6)],
        "v0": [0 * 6 + u for u in range(6)],
        "v1": [5 * 6 + u for u in range(6)],
    }
    for name, idxs in sides.items():
        p0 = poles36[idxs[0]]
        if all((poles36[k] - p0).Length <= tol for k in idxs):
            return name
    return None


def _collapse_frame_index(side, k):
    """Original flat index of frame position `k`, where the frame places
    the collapsed side at V1 (the Coons construction's degenerate side).

    P'[u][v] = P[u][v] for a collapsed v1, P[u][5-v] for v0,
    P[v][u] for u1, P[5-v][u] for u0; flat index = v*6 + u."""
    v, u = divmod(k, 6)
    if side == "v1":
        return v * 6 + u
    if side == "v0":
        return (5 - v) * 6 + u
    if side == "u1":
        return u * 6 + v
    return u * 6 + (5 - v)          # u0


def _coons_target(net_p, net_w, u, v):
    """The transfinite (Coons) fill of the frame net's boundary loop, with
    the v1 side collapsed to a point. Rational boundaries, Cartesian
    result: the same construction on a degenerate quadrilateral."""
    def point(eval_uv):
        num = [0.0, 0.0, 0.0]
        den = 0.0
        for idx, wt in eval_uv:
            num[0] += wt * net_p[idx].x
            num[1] += wt * net_p[idx].y
            num[2] += wt * net_p[idx].z
            den += wt
        if den == 0.0:
            return None
        return (num[0] / den, num[1] / den, num[2] / den)

    bu, bv = _basis6(u), _basis6(v)
    c_v0 = point([(0 * 6 + i, bu[i] * net_w[0 * 6 + i]) for i in range(6)])
    c_v1 = point([(5 * 6 + i, bu[i] * net_w[5 * 6 + i]) for i in range(6)])
    c_u0 = point([(j * 6 + 0, bv[j] * net_w[j * 6 + 0]) for j in range(6)])
    c_u1 = point([(j * 6 + 5, bv[j] * net_w[j * 6 + 5]) for j in range(6)])
    if None in (c_v0, c_v1, c_u0, c_u1):
        return None
    p00 = (net_p[0].x, net_p[0].y, net_p[0].z)
    p01 = c_v1            # the collapsed v1 side is one point
    c00 = tuple((1 - v) * p00[k] + v * p01[k] for k in range(3))
    p10 = tuple(net_p[0 * 6 + 5][k] for k in range(3))
    c10 = tuple((1 - v) * p10[k] + v * p01[k] for k in range(3))
    out = []
    for k in range(3):
        out.append((1 - v) * c_v0[k] + v * c_v1[k]
                   + (1 - u) * (c_u0[k] - c00[k])
                   + u * (c_u1[k] - c10[k]))
    return tuple(out)


def smooth_degenerate_cap(poles36, weights36, tol=1e-6):
    """Fold-free cap smoothing for a corner with a collapsed side.

    Detects a side of the 6x6 whose six poles coincide (the triangular
    4th member's collapsed junction row), re-indexes the net so that side
    is V1, and re-solves the eight interior poles of its two neighbouring
    rows (frame u = 1..4, v = 3,4) as the least-squares projection of the
    transfinite (Coons) fill of the corner's own boundary loop -- with
    the assembled weights held fixed. Everything else (all four boundary
    sides included) is returned untouched, so C0 at every seam and the
    opposite seam's exact G1/curvature are preserved.

    Returns (poles36, weights36): the input lists unchanged when no side
    is collapsed (the ordinary 4-valent ring) or when the solve does not
    produce a finite net.
    """
    side = _collapsed_side(poles36, tol)
    if side is None:
        return poles36, weights36
    perm = [_collapse_frame_index(side, k) for k in range(36)]
    fp = [poles36[k] for k in perm]
    fw = [float(weights36[k]) for k in perm]

    n_samp = 25
    free = [(v * 6 + u) for v in (3, 4) for u in range(1, 5)]
    sites = [((i + 0.5) / n_samp, (j + 0.5) / n_samp)
             for i in range(n_samp) for j in range(n_samp)]
    fixed = [k for k in range(36) if k not in free]

    ncol = len(free)
    A = np.zeros((len(sites), ncol))
    B = np.zeros((len(sites), 3))
    for r, (u, v) in enumerate(sites):
        bu, bv = _basis6(u), _basis6(v)
        field_w = sum(bu[i] * bv[j] * fw[j * 6 + i]
                      for i in range(6) for j in range(6))
        if field_w <= 0.0:
            return poles36, weights36
        tgt = _coons_target(fp, fw, u, v)
        if tgt is None:
            return poles36, weights36
        acc = [0.0, 0.0, 0.0]
        for k in fixed:
            vv, uu = divmod(k, 6)
            rat = bu[uu] * bv[vv] * fw[k] / field_w
            if rat != 0.0:
                acc[0] += rat * fp[k].x
                acc[1] += rat * fp[k].y
                acc[2] += rat * fp[k].z
        for ci, k in enumerate(free):
            vv, uu = divmod(k, 6)
            A[r, ci] = bu[uu] * bv[vv] * fw[k] / field_w
        B[r, 0] = tgt[0] - acc[0]
        B[r, 1] = tgt[1] - acc[1]
        B[r, 2] = tgt[2] - acc[2]

    try:
        sol, _res, _rank, _sv = np.linalg.lstsq(A, B, rcond=None)
    except Exception:
        return poles36, weights36
    if not all(np.isfinite(sol.ravel())):
        return poles36, weights36

    frame_p = list(fp)
    for ci, k in enumerate(free):
        frame_p[k] = _CGV(float(sol[ci, 0]), float(sol[ci, 1]),
                          float(sol[ci, 2]))
    out_p = list(poles36)
    for k in range(36):
        out_p[perm[k]] = frame_p[k]
    return out_p, list(weights36)


def corner_grid(grids, tol=1e-6):
    """Four 24-pole grids (ring order) -> the corner's 6x6.

    `grids` are the strips' control nets with each junction-end row at
    V = 3, given in cyclic order. The ring's rotational direction matters:
    upstream accepts only the shared corner at (V3, U5) on the first grid
    and (V3, U0) on the second, and a ring handed over the other way
    presents every pair MIRRORED -- which assembles into a grid whose
    boundary does not match the ring's own. So a ring whose every pair is
    mirrored is reversed (`grids[1:]` reversed, keeping the first pair's
    orientation); a ring that is not consistently oriented either way is
    refused by name.

    Returns (poles36, weights36, None) or (None, None, reason)."""
    pairs = []
    mirrored = []
    for i in range(4):
        a, b = grids[i], grids[(i + 1) % 4]
        common, why = pair_common(a[0], b[0], tol)
        if common is None:
            return None, None, ("strip %d and strip %d: %s" % (i, (i + 1) % 4,
                                                                why))
        pairs.append(common)
        mirrored.append((common[1], common[0]))
    if all(c == CORNER_COMMON for c in pairs):
        pass
    elif all(c == CORNER_COMMON for c in mirrored):
        grids = [grids[0]] + list(reversed(grids[1:]))
    else:
        return None, None, ("the four strips are not a consistently oriented "
                            "ring (shared corners %r)" % (pairs,))

    subgrids = []
    for i in range(4):
        a, b = grids[i], grids[(i + 1) % 4]
        p, w, why = subgrid33_2grid64(a[0], a[1], b[0], b[1], tol)
        if p is None:
            return None, None, ("strip %d and strip %d: %s"
                                % (i, (i + 1) % 4, why))
        subgrids.append((p, w))
    p36, w36 = control_grid66_4sub(subgrids)
    # A 3-valent ring's triangular member collapses one side of the 6x6;
    # the subgrid extrapolation past that side folds the cap, so the
    # member-side interior rows are re-solved from the boundary (no-op on
    # an ordinary 4-valent ring).
    p36, w36 = smooth_degenerate_cap(p36, w36, tol)
    return p36, w36, None


def _share_patch(a, b):
    pa = [getattr(a, "PatchA", None), getattr(a, "PatchB", None)]
    pb = [getattr(b, "PatchA", None), getattr(b, "PatchB", None)]
    return any(x is not None and x is y for x in pa for y in pb)


def _doc_index(obj):
    doc = getattr(obj, "Document", None)
    if doc is None:
        return 0
    for k, o in enumerate(doc.Objects):
        if o is obj:
            return k
    return 0


def corner_ring(strips):
    """Order 4 Blend strips into their cyclic ring, deterministically.

    Identity-only, like the seam resolver: two strips are adjacent iff
    they share a PATCH object. The four must form one 4-cycle (each
    adjacent to exactly two others) -- that is what "four strips ring one
    junction" means, and it is what a non-corner selection fails.

    The ring direction is fixed by `corner_grid`, so the only choice made
    here is the START: the strip earliest in the document, and the
    neighbour later in document order. That makes the result independent
    of the click order the strips arrived in.

    Returns (ordered, None) or (None, reason)."""
    strips = list(strips)
    if len(strips) != 4:
        return None, ("a corner ring is exactly 4 blends (got %d)"
                      % len(strips))
    seen = {}
    for i, s in enumerate(strips):
        for j in range(i):
            if strips[j] is s:
                return None, ("%s is in the ring twice" % s.Name)
        seen[i] = s
    adj = {i: set() for i in range(4)}
    for i in range(4):
        for j in range(i + 1, 4):
            if _share_patch(strips[i], strips[j]):
                adj[i].add(j)
                adj[j].add(i)
    for i in range(4):
        if len(adj[i]) != 2:
            return None, ("%s shares a patch with %d of the other blends; "
                          "four blends ring a junction only when each one "
                          "meets exactly two of the others"
                          % (strips[i].Name, len(adj[i])))
    start = min(range(4), key=lambda i: _doc_index(strips[i]))
    nxt = min(adj[start], key=lambda i: _doc_index(strips[i]))
    order = [start, nxt]
    while len(order) < 4:
        cur = order[-1]
        step = [k for k in adj[cur] if k not in order]
        if len(step) != 1:
            return None, ("the four blends do not form a single ring "
                          "(the walk from %s is ambiguous)" % strips[start].Name)
        order.append(step[0])
    if order[0] not in adj[order[-1]]:
        return None, ("the four blends do not form a single ring (the walk "
                      "from %s does not close)" % strips[start].Name)
    return [strips[i] for i in order], None


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
    """Compose the patch's display Shape -- the SURFACE only (#108).

    Writes fobj.Shape with the visible surface: the base surface, or the
    non-hidden subgrid surfaces when ShowSubgrids. Honors fobj.ShowSurface
    / ShowSubgrids / AutoHideBlend.

    `Shape` is GEOMETRY ONLY. The control grid used to be appended here as
    loose edges, which is why a Part::Compound built from Silk objects came
    out polluted with grid wires. The grid is a DISPLAY concern: the view
    provider draws it as a Coin node (SilkMachinery.set_grid_display) and
    honours ShowGrid itself. The legs the grid toggle selects are stashed
    on fobj.Proxy._display_legs so the view provider and this rule cannot
    disagree, and they are stashed whether or not ShowGrid is on, so the
    toggle only has to show/hide an already-built node.

    Consequence: the grid is no longer part of Shape -- not exported, not
    selectable, and `Shape` no longer changes on a display toggle.
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
    try:
        fobj.Proxy._display_legs = list(draw_legs or [])
    except Exception:
        pass

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


# ---- control-grid display node (#108) ------------------------------------
#
# `Shape` is geometry only; the control grid is drawn by a Coin node under
# the view provider's own RootNode.
#
# Why RootNode and NOT addDisplayMode: ArchAxis's pattern pairs
# addDisplayMode with a getDisplayModes override, and that REPLACES the
# standard Part modes. Measured on this build (1.1.3): after a proxy calls
# addDisplayMode, `obj.ViewObject.DisplayMode = "Shaded"` raises
# ValueError("'Shaded' is not part of the enumeration"). The ops layer
# writes exactly that from create_blend / create_corner_blend, so the grid
# node is appended as an extra child of RootNode instead: every standard
# mode (and the DisplayMode writes) is untouched.
#
# RootNode's leading SoTransform is the object Placement, and Coin applies
# it to every following sibling, so the node is drawn in LOCAL coordinates
# -- the same coordinates Poles / Legs carry.

def grid_coin_node(legs):
    """A coin.SoSeparator drawing `legs` as line segments, or None when
    there is nothing to draw or pivy is unavailable (the caller then draws
    nothing rather than failing)."""
    if not legs:
        return None
    try:
        from pivy import coin
    except Exception:
        return None
    points, index = [], []
    n = 0
    for leg in legs:
        try:
            edge = leg.toShape()
        except Exception:
            continue
        for v in edge.Vertexes:
            p = v.Point
            points.append((p.x, p.y, p.z))
            index.append(n)
            n += 1
        index.append(-1)
    if not points:
        return None
    sep = coin.SoSeparator()
    coords = coin.SoCoordinate3()
    coords.point.setValues(0, len(points), points)
    lineset = coin.SoType.fromName("SoBrepEdgeSet").createInstance()
    lineset.coordIndex.setValues(0, len(index), index)
    lineset.coordIndex.setNum(len(index))
    sep.addChild(coords)
    sep.addChild(lineset)
    return sep


def set_grid_display(proxy, vobj, legs, visible, color, width):
    """(Re)build the control-grid Coin node on `vobj` and show/hide it.

    `proxy` keeps the node (a coin.SoSwitch) in `proxy._silk_grid_node`
    between calls; `visible=False` hides it (`whichChild = -1`) without
    changing anything else. No ViewObject (headless) or no pivy is a
    silent no-op -- no node, no error. The switch is re-appended to
    RootNode on every call so exactly one grid node ever exists.
    """
    if vobj is None:
        return None
    try:
        from pivy import coin
    except Exception:
        return None
    root = getattr(vobj, "RootNode", None)
    if root is None:
        return None
    switch = getattr(proxy, "_silk_grid_node", None)
    if switch is None:
        switch = coin.SoSwitch()
        proxy._silk_grid_node = switch
    try:
        root.removeChild(switch)
    except Exception:
        pass
    display = coin.SoSeparator()
    if color is not None:
        mat = coin.SoMaterial()
        mat.diffuseColor.setValue(float(color[0]), float(color[1]),
                                  float(color[2]))
        display.addChild(mat)
    if width is not None:
        style = coin.SoDrawStyle()
        style.lineWidth = float(width)
        display.addChild(style)
    node = grid_coin_node(legs)
    if node is not None:
        display.addChild(node)
    try:
        switch.removeAllChildren()
    except Exception:
        pass
    switch.addChild(display)
    switch.whichChild = 0 if visible else -1
    root.addChild(switch)
    return switch


# ---- triangular 4th member (#3-valent hard corner) -----------------------
#
# Port of `ArachNURBS.ControlGrid64_3_1Grid44.execute`: rotate a 4x4 grid
# so the target corner sits at 00, collapse one side into the degenerate
# triangular layout with the "tiny spacing" workaround, and return a
# 6x4 (24-pole) grid that serves as the fourth ring member of a 3-valent
# corner. `corner` in 0..3 is the corner index of the 4x4 to collapse.

import numpy as np
from FreeCAD import Vector as _CGV


def control_grid64_3_1(grid_poles, grid_weights, corner=0):
    if corner not in (0, 1, 2, 3):
        return None, None
    rotate = corner
    lp = list(grid_poles)
    lw = list(grid_weights)
    if len(lp) != 16 or len(lw) != 16:
        return None, None
    Apoles = [list(lp[0:4]), list(lp[4:8]), list(lp[8:12]), list(lp[12:16])]
    Aweights = [list(lw[0:4]), list(lw[4:8]), list(lw[8:12]), list(lw[12:16])]
    uv_poles_temp = np.rot90(Apoles, rotate).tolist()
    uv_weights = np.rot90(Aweights, rotate).tolist()
    uv_poles = [[None]*4 for _ in range(4)]
    for i in range(4):
        for j in range(4):
            v = uv_poles_temp[i][j]
            uv_poles[i][j] = _CGV(v[0], v[1], v[2]) if hasattr(v, "__len__") \
                and not hasattr(v, "x") else v
    set_poles = [uv_poles[i][j] for i in range(4) for j in range(4)]
    set_weights = [uv_weights[i][j] for i in range(4) for j in range(4)]

    def V(p):  # ensure FreeCAD.Vector
        if hasattr(p, "x"):
            return p
        return _CGV(p[0], p[1], p[2])

    p = [V(x) for x in set_poles]
    w = [float(x) for x in set_weights]

    # third strategy mapping, term for term upstream (ticket-foldfix).
    # p12 halves set_poles[5] with p11 = set_poles[9]; p24 starts from
    # p25 = set_poles[11], NOT from set_poles[15] -- the two source-pole
    # slips the member calibration measured. The weight channel below is
    # upstream's LITERAL lines (w12 from input weights 4/10, w13 from
    # 1/10, both averaged with w[10]) even though they read like a
    # copy-paste from a different index map; parity with the stored demo
    # members wins by product decision.
    p00 = p[12]; p01 = p[8]; p02 = p[4]; p03 = p[1]; p04 = p[2]; p05 = p[3]
    p10 = p[13]; p11 = p[9]
    p14 = p[6]; p15 = p[7]
    p20 = p[14]
    p21 = p[14] + (p[10] - p[14]) * 0.5
    p22 = p21 + (p[10] - p21) * 0.5
    p25 = p[11]
    p24 = p25 + (p[10] - p25) * 0.5
    p23 = p24 + (p[10] - p24) * 0.5
    p30 = p[15]; p31 = p[15]; p32 = p[15]; p33 = p[15]; p34 = p[15]; p35 = p[15]
    p12 = (p[5] + p11) * 0.5
    p13 = (p[5] + p14) * 0.5

    out_poles = [p00, p01, p02, p03, p04, p05,
                 p10, p11, p12, p13, p14, p15,
                 p20, p21, p22, p23, p24, p25,
                 p30, p31, p32, p33, p34, p35]

    w00 = w[12]; w01 = w[8]; w02 = w[4]; w03 = w[1]; w04 = w[2]; w05 = w[3]
    w10 = w[13]; w11 = w[9]
    w14 = w[6]; w15 = w[7]
    w20 = w[14]
    w21 = w[10]; w22 = w[10]; w23 = w[10]; w24 = w[10]
    w25 = w[11]
    w30 = w[15]; w31 = w[15]; w32 = w[15]; w33 = w[15]; w34 = w[15]; w35 = w[15]
    w12 = (w02 + w21) * 0.5   # upstream: (set_weights[4] + w[10])/2
    w13 = (w03 + w24) * 0.5   # upstream: (set_weights[1] + w[10])/2

    out_weights = [w00, w01, w02, w03, w04, w05,
                   w10, w11, w12, w13, w14, w15,
                   w20, w21, w22, w23, w24, w25,
                   w30, w31, w32, w33, w34, w35]
    # ensure vectors
    for i in range(len(out_poles)):
        if not hasattr(out_poles[i], "x"):
            v = out_poles[i]
            out_poles[i] = _CGV(v[0], v[1], v[2])
    return out_poles, out_weights


def corner_ring_3(strips):
    strips = list(strips)
    if len(strips) != 3:
        return None, ("a 3-valent ring is exactly 3 blends (got %d)"
                      % len(strips))
    adj = {i: set() for i in range(3)}
    for i in range(3):
        for j in range(i + 1, 3):
            # reuse SilkMachinery? inline share patch
            def _sp(a, b):
                pa = [getattr(a, "PatchA", None), getattr(a, "PatchB", None)]
                pb = [getattr(b, "PatchA", None), getattr(b, "PatchB", None)]
                return any(x is not None and x is y for x in pa for y in pb)
            if _sp(strips[i], strips[j]):
                adj[i].add(j)
                adj[j].add(i)
    for i in range(3):
        if len(adj[i]) != 2:
            return None, ("%s shares a patch with %d of the other blends; "
                          "a 3-valent corner needs a 3-cycle"
                          % (strips[i].Name, len(adj[i])))
    # order
    import FreeCAD
    def _idx(o):
        doc = getattr(o, "Document", None)
        if doc is None:
            return 0
        for k, oo in enumerate(doc.Objects):
            if oo is o:
                return k
        return 0
    start = min(range(3), key=lambda i: _idx(strips[i]))
    nxt = min(adj[start], key=lambda i: _idx(strips[i]))
    third = [k for k in adj[nxt] if k != start][0]
    if third in (start,):
        return None, "not a single 3-cycle"
    if start not in adj[third]:
        return None, "the three blends do not form a single 3-cycle"
    return [strips[start], strips[nxt], strips[third]], None
