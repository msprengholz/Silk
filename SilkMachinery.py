"""
SilkMachinery — shared machinery core for Silk surface objects.

One reusable implementation of the machinery every patch fill shares:
subdivision (USplits/VSplits -> subgrid pole arrays + trimmed surfaces),
blend-band selection, hidden-cell bookkeeping, and compound display.

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


# ---- subdivision -------------------------------------------------------

def normalize_splits(values):
    return sorted(set(v for v in values if 0.0 < v < 1.0))


def build_intervals(values):
    splits = normalize_splits(list(values))
    if not splits:
        return [(0.0, 1.0)]
    return list(zip([0.0] + splits, splits + [1.0]))


def normalize_splits_report(values):
    """(kept, out_of_range, repeated) for one axis.

    The stored list is normalized ON SET by the Patch (#61), so this is
    the same rule the Patch applies at write time — the values kept
    (sorted, deduped, strictly inside (0, 1)) plus, for the console
    message, what was rejected and WHY: a value outside (0, 1), and a
    value the input repeated. Both lists are empty for an already-
    normalized input."""
    raw = list(values)
    kept = normalize_splits(raw)
    kept_set = set(kept)
    out_of_range = []
    repeated = []
    for v in raw:
        if not 0.0 < v < 1.0:
            if v not in out_of_range:
                out_of_range.append(v)
        elif v in kept_set and raw.count(v) > 1 and v not in repeated:
            repeated.append(v)
    return kept, out_of_range, repeated


def build_subgrids(base_surface, u_splits, v_splits):
    """Subdivide base_surface by the U/V splits.

    Returns (subgrids, subsurfaces, sub_legs):
      - subgrids:    flat 16-pole arrays, one per cell;
                     poles[U][V] == flat[U*4 + V] (FreeCAD convention).
      - subsurfaces: the trimmed sub-shapes (only truthy shapes).
      - sub_legs:    detailed grid lines for the subdivided view.
    With no splits returns ([], [], []).
    """
    subgrids = []
    subsurfaces = []
    sub_legs = []
    u_splits = list(u_splits) if u_splits else []
    v_splits = list(v_splits) if v_splits else []
    if not (u_splits or v_splits):
        return subgrids, subsurfaces, sub_legs
    shapes = []
    for u0, u1 in build_intervals(u_splits):
        for v0, v1 in build_intervals(v_splits):
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


def split_end(value):
    """Which END of its axis ONE split belongs to: 0 (parametric-0), 1
    (parametric-1), or None when it marks NEITHER -- which is what the
    exact midpoint 0.5 does. #64, #76.

    This is the classification itself, factored out of `split_at_end` so
    that every question about a split's end asks THIS function: which
    split is an end's band boundary (#64), which intervals are corner
    cells (#61), which panel width can be stored (#75), and how many
    splits an axis may carry (#76). Two notions of "which end" is how a
    band comes to measure itself against a cell that was excluded for a
    different reason.
    """
    v = float(value)
    if v < 0.5:
        return 0
    if v > 0.5:
        return 1
    return None


def split_at_end(splits, ss):
    """The split that carves the band at ONE END of an axis, or None.

    A split is not a width marker at a magic number, it is the FAR EDGE
    of a band at one end of its axis: the lowest split carves [0, s] at
    the parametric-0 end, the highest carves [s, 1] at the parametric-1
    end, and a split exactly at 0.5 marks NEITHER end (a plain
    mid-surface subdivision with no band attached to it). Returns that
    split's value for the requested end, or None when the end carries
    none. #64.

    This is the SINGLE end-classification rule, shared on purpose: a
    band and the corner-cell exclusion that trims it must never disagree
    about which of a patch's splits is which end's, or the band would
    measure itself against a cell that was excluded for a different
    reason (corner_cells drops exactly the interval its end's split
    carved; SilkBlend reads exactly that split as the band's width).

    With TWO splits on one axis ([0.1, 0.9]) each end gets its own —
    end 0 takes the lowest, end 1 the highest. That is what lets a
    four-patch corner carry one split per seam side on the same axis.
    The membership test is `split_end` (#76), the same one the
    per-axis limit counts with; only the ORDER within an end is local
    here, and it is the whole point of this function. An end's band is
    the interval that reaches from that end: [0, s] at the 0 end, so s
    is the LOWEST split there, and [s, 1] at the 1 end, so s is the
    HIGHEST. Any further split at the same end is the middle one, and it
    is to exactly that middle one that the geometry goes quietly wrong
    (see split_limit_problem).
    """
    s = normalize_splits(list(splits or []))
    mine = [v for v in s if split_end(v) == ss]
    if not mine:
        return None
    return mine[0] if ss == 0 else mine[-1]


def split_limit_problem(values):
    """Why `values` may not be STORED as one axis' splits, or None. #76.

    THE RULE: at most TWO splits on one axis.

    It was first written FINER -- one below 0.5 and one above -- and the
    human hit it within minutes, because it refused `[0.2, 0.4]`, two
    ordinary subdivision values they were simply trying to store. There
    was no principle behind that refusal. A split list is ordered surface
    subdivisions, `0 < u1 < u2 < 1`, and `normalize_splits` already
    enforces range, order and duplicates. `[0.2, 0.4]` is legal, and a
    regression that rejects ordinary input is worse than the silent case
    it was meant to prevent.

    Why there is a limit at all: past two, results are invisible rather
    than wrong. An extra split on the band axis is absorbed without a word
    and `SilkCorner._corner_cell` quietly starts picking a different
    subgrid cell; on the seam-parallel axis it makes the band span cells
    the blend refuses, and that refusal leaves the Blend's Poles
    byte-identical while the Patch reports itself Up-to-date and Valid --
    no tree marker, no stale flag. Hence a REFUSAL (SilkPatch puts the
    axis back and flags the object) rather than a truncation: with three
    values there is no principled one to drop, and silently dropping one
    changes the geometry while saying nothing.

    KNOWN GAP -- a full axis cannot gain a band split. `ensure_band_split`
    writes only where `split_at_end` returns None, and `split_at_end`
    classifies by VALUE (below 0.5 -> end 0, above -> end 1, exactly 0.5
    -> neither). So on `[0.2, 0.4]` it reports NO band at the 1 end, even
    though 0.4 is plainly the far edge of the [0.4, 1.0] band, and the
    blend then tries to write a third split -- which this rule refuses, and
    the patch goes Invalid. Tracked as #81: the fix is to make
    `split_at_end` POSITIONAL for two splits (lower is the 0 end's, upper
    is the 1 end's, which is what the human's own reading is), but that
    changes band geometry for every layout containing 0.5 and needs its
    own review rather than a drive-by fix here.
    """
    s = normalize_splits(list(values))
    if len(s) <= 2:
        return None
    return ("%s -- an axis carries at most two splits (0 < u1 < u2 < 1). "
            "Past two the result is invisible rather than wrong: the corner "
            "blend picks a different subgrid cell, or the band spans cells "
            "the blend refuses while this patch still reports itself "
            "Up-to-date and Valid. With three values there is no principled "
            "one to drop, so the list was not stored and the axis keeps "
            "what it had."
            % ("[%s]" % ", ".join("%g" % v for v in s)))
def corner_cells(splits, n_intervals):
    """Interval indices along one axis that are CORNER cells — reserved
    for the four-cell corner blend op (#28) and excluded from a band.

    #61: this is the generalized form of the old hard-coded test
    ("is there a 0.1? drop the first cell / a 0.9? drop the last").
    A split is not a width marker at a magic number, it is the far edge
    of a band at one END of its axis: s < 0.5 isolates the band [0, s] at
    the parametric-0 end, s > 0.5 the band [s, 1] at the parametric-1
    end (SilkBlend.ensure_band_split writes 0.1 / 0.9 by default, but
    the width is the user's). So:
      - the split NEAREST the 0 end (the lowest) carved out the interval
        [0, s]: that interval is the corner cell -> drop it;
      - the split NEAREST the 1 end (the highest) carved out [s, 1]:
        drop it;
      - a split exactly at 0.5 marks neither end (a plain mid-surface
        subdivision, no band attached to either end).

    A single split marks the one end it is nearest to: [0.1] drops the
    first cell only and [0.9] the last cell only — which is exactly what
    the old literal rule did for the two values it knew, and what keeps
    a 2-interval layout ([0, s], [s, 1]) from collapsing to no band at
    all. For a split list drawn from {0.1, 0.5, 0.9} — every value the
    fixtures use — this is provably identical to the old rule; only a
    user width like 0.2 / 0.85 used to fall through it silently (#61).
    """
    s = normalize_splits(list(splits))
    if not s:
        return set()
    out = set()
    if split_at_end(s, 0) is not None:
        out.add(0)
    if split_at_end(s, 1) is not None:
        out.add(n_intervals - 1)
    return out


def band_cells(p, ea, ss):
    """Subgrid cell indices covered by a strip's band on patch p.

    The band runs along the seam in the band interval (0 or last, per
    ss). A cell at a seam end with a seam-axis split is a corner cell —
    excluded from the band (reserved for the four-cell corner blend op,
    #28). Which cells those are follows the axis splits, not a magic
    0.1/0.9 (see corner_cells, #61).
    """
    us, vs = list(p.USplits or []), list(p.VSplits or [])
    nu = len(build_intervals(us))
    nv = len(build_intervals(vs))
    if ea[0] == "U":  # seam along U: band fixes V interval, spans U cells
        b = (nv - 1) if ss else 0
        keep_u = set(range(nu)) - corner_cells(us, nu)
        return [a * nv + b for a in sorted(keep_u)]
    # seam along V: band fixes U interval, spans V cells
    a = (nu - 1) if ss else 0
    keep_v = set(range(nv)) - corner_cells(vs, nv)
    return [a * nv + b for b in sorted(keep_v)]


def _splits_str(values):
    """`[0.1, 0.9]` — the split list the way a user reads it in the
    property editor (never Python float noise like [0.100000001490116])."""
    return "[" + ", ".join("%g" % float(v) for v in values) + "]"


def band_diagnosis(p, ea, ss):
    """Actionable, fact-by-fact diagnosis of patch p's band at seam
    ea/ss — the axis roles, the split values in play, how many intervals
    they make, which cells the corner exclusion drops, and what single
    split value WOULD leave a one-cell band. Pure data -> string, no
    console output; SilkBlend owns the message that carries it (#61).
    """
    name = getattr(p, "Name", "?")
    us, vs = list(p.USplits or []), list(p.VSplits or [])
    nu, nv = len(build_intervals(us)), len(build_intervals(vs))
    if ea[0] == "U":  # seam along U: band fixes a V interval, spans U
        band_prop, along_prop, along, n_along = "VSplits", "USplits", us, nu
        band_ivs = build_intervals(vs)
    else:             # seam along V: band fixes a U interval, spans V
        band_prop, along_prop, n_along = "USplits", "VSplits", nv
        along, band_ivs = vs, build_intervals(us)
    # the band is the first (side 0) or the last (side 1) interval
    band_iv = band_ivs[0] if ss == 0 else band_ivs[-1]
    width = band_iv[1] - band_iv[0]
    excluded = sorted(corner_cells(along, n_along))
    along_set = normalize_splits(along)
    pick = (along_set[0] if ss == 0 else along_set[-1]) if along_set else None
    return (
        "seam %s (band at parametric %d): band axis %s = %s -> %d "
        "interval(s), width %g.\n"
        "      seam-parallel axis %s = %s -> %d interval(s); corner "
        "cell(s) %s excluded, %d left in the band.\n"
        "      A one-cell band needs at most one split below 0.5 and one "
        "above 0.5 on the seam-parallel axis: %s.%s = %s gives a single "
        "band cell of width %g."
        % (ea, ss, band_prop, _splits_str(getattr(p, band_prop) or []),
           len(band_ivs), width,
           along_prop, _splits_str(along), n_along, excluded,
           n_along - len(excluded),
           name, along_prop,
           "[]" if pick is None else "[%g]" % pick, width))


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
