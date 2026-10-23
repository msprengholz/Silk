#    This file is part of Silk
#    (c) 2025
#
#    NURBS Surface modeling tools focused on low degree and seam continuity (FreeCAD Workbench)
#
#    Patch — the unified Patch object (tickets #37/#38).
#
#    One variable-length `Edges` link list (PropertyLinkList) is the single
#    boundary input; execute() selects the fill from the edge count: 4
#    edges -> the quad fill (#37, SAME 16 poles as Patch44), 3 edges ->
#    the pointed fill (#38, SAME 16 poles as Patch33) for the identical
#    edges in the same order (pole parity at 1e-6 is what later lets the
#    unified pipeline reproduce the chain — #40; the unified Blend is
#    #39). Other counts leave the object empty/valid.
#
#    Subdivision / band / hidden-cell bookkeeping / compound display all
#    delegate to the shared machinery core (SilkMachinery) — nothing is
#    reimplemented here. That is the whole point of the unification: the
#    pointed fill gets the subgrid machinery the legacy Patch33 lacked.
#
#    #66: the quad fill does not trust the ORDER of the `Edges` list. The
#    list arrives in click order (the panel), or hand-reordered (the data
#    tab), or restored from an old file, and a cycle walked blind failed
#    for 16 of the 24 permutations of one valid loop — silently, leaving
#    an invisible ghost. `SilkMachinery.loop_order` derives the cycle from
#    the edges' own endpoints (at `tolerance`) inside the fill, so every
#    path that can produce a patch is fixed at once; an already-cyclic
#    list comes back untouched, which is what preserves the legacy
#    Patch44/Patch33 pole parity.
#
#    #67: ...and then it KEEPS the answer. #66 resolved the cycle for the
#    fill but left the stored list in the order it arrived, so for a
#    clicked-around selection the object contradicted itself: `Edges[k]`
#    was not boundary side k, and both the data tab and the oracle said so
#    (P1_corner_order / P2_boundary_match fail on a non-cyclic list).
#    execute() now writes the resolved cycle back onto `Edges` — only when
#    it differs, so a cyclic list takes the byte-identical path it always
#    did (the legacy pole parity and the chain ground truth ride on that).
#    `Edges[k]` IS boundary side k by construction, for any input order,
#    and one recompute later the list is cyclic, so the write is a fixed
#    point rather than a ping-pong.
#
#    #68: the pointed fill now means the same thing. `Edges` is a cycle
#    for 3 edges exactly as for 4 — row U0/col V3/row U3 = Edges[0]/[1]/[2],
#    the degenerate corner IS the Edges[2]->Edges[0] junction — both
#    counts run through the normalization gate, and _pointed_fill
#    re-checks the loop itself so it refuses a non-loop instead of
#    building 16 poles that disagree with their own geometry. For a
#    CLOSED triple nothing is rewritten (every ordering of three corners
#    is already cyclic — the write is structurally a no-op, which is
#    what keeps Patch33 parity at 0.00e+00); what the check catches is
#    the three-seams-from-one-point fan, which is not a loop at all and
#    used to slip through because for n=3 the per-edge adjacency test is
#    vacuous. See SilkMachinery.loop_order and
#    Tests/test_pointed_corner_triple.py.

import FreeCAD
import Part
from FreeCAD import Gui

import ArachNURBS as AN
from popup import tipsDialog

from SilkMachinery import build_subgrids, build_display, \
    normalize_edge_pair, normalize_leader_on_set, ensure_leader_cuts, \
    split_pair, axis_splits, axis_cuts, axis_has_cuts, leader_pair, \
    NO_BAND_1, NO_BAND_2, NO_LEADER_1, NO_LEADER_2, \
    loop_order, set_grid_display

import os, Silk_dummy
path_Silk = os.path.dirname(Silk_dummy.__file__)
path_Silk_icons = os.path.join(path_Silk, "Resources", "Icons")
iconPath = path_Silk_icons + "/SilkPatch.svg"

PATCH_TOOLTIP = ('Create a unified Patch from 3 or 4 selected '
                 'Silk Edge objects. The edge count picks the '
                 'fill: 3 edges -> pointed, 4 edges -> quad.')


class Patch:
    """Unified Patch proxy (object_type='Patch')."""

    def __init__(self, obj, edges):
        # #67: the Edges list is a CYCLE and is stored AS the cycle. You
        # may hand it any order (click order from the panel, hand-order in
        # the data tab, whatever an old file restored) and execute() writes
        # back the resolved boundary cycle whenever it differs, so entry k
        # is boundary side k: row U0 / col V3 / row U3 / col V0 for the
        # quad fill, and the 3 pointed edges for the pointed fill. An
        # already-cyclic list is left exactly as it is, byte for byte.
        # This is visible in the data tab -- the Edges row shows the
        # normalized cycle, not the click order -- and that is the point:
        # the stored value describes the geometry it produced.
        obj.addProperty("App::PropertyLinkList", "Edges", "C1 - Inputs",
                        "boundary edges as the closed loop (3 for the "
                        "pointed fill, 4 for the quad fill); entry k is "
                        "boundary side k -- execute() normalizes any input "
                        "order into this cycle").Edges = list(edges)
        obj.addProperty("App::PropertyFloat", "tolerance", "C1 - Inputs",
                        "endpoint matching tolerance").tolerance = AN.default_tol
        obj.addProperty("App::PropertyBool", "reverse", "C1 - Inputs",
                        "reverse the grid parameter direction").reverse = False
        # #82: subdivision is TWO NAMED BAND EDGES per axis, not a list of
        # split parameters. `Split1` is the far edge of the band at the
        # parametric-0 end, `Split2` the far edge at the parametric-1
        # end, and each property's OWN ENDPOINT is its "no band here"
        # sentinel: Split1 = 0 and Split2 = 1 means the axis carries no
        # split at all. That is why the DEFAULTS are the sentinels and
        # not 0.1 / 0.9 -- a patch nobody has blended must stay in one
        # piece (0 subgrid cells, 1 face). 0.1 / 0.9 are the widths
        # SilkBlend.ensure_band_split writes into the ONE end that needs
        # them, which is a different thing and has always been.
        for letter, axis in (("U", "U"), ("V", "V")):
            obj.addProperty(
                "App::PropertyFloat", letter + "Split1", "S1 - Subdivision",
                "band edge at the parametric-0 end of the %s axis; 0 = no "
                "band at that end" % axis)
            obj.addProperty(
                "App::PropertyFloat", letter + "Split2", "S1 - Subdivision",
                "band edge at the parametric-1 end of the %s axis; 1 = no "
                "band at that end" % axis)
        obj.USplit1 = NO_BAND_1
        obj.USplit2 = NO_BAND_2
        obj.VSplit1 = NO_BAND_1
        obj.VSplit2 = NO_BAND_2
        # #119: the LEADER cut, one more cut per axis end and a different
        # thing from the band edge -- the band edge is the user's SETBACK
        # (how wide the blend is), the leader is how far the band is cut
        # back from the junction corner. The rolled corner needs both: the
        # two cuts bound the cell the triangular patch occupies, on the one
        # patch that carries it. ADDITIVE and
        # default-off: a patch that never carries one reads exactly the two
        # band edges it always read, so every existing document builds
        # byte-identically. Same sentinel rule (each property's OWN
        # endpoint), so `band_edge()` reads a leader too.
        ensure_leader_cuts(obj)
        obj.addProperty("App::PropertyBool", "ShowSurface", "S2 - Display",
                        "show the surface").ShowSurface = True
        obj.addProperty("App::PropertyBool", "ShowGrid", "S2 - Display",
                        "show the control grid").ShowGrid = True
        obj.addProperty("App::PropertyBool", "ShowSubgrids", "S2 - Display",
                        "show subdivided subgrids instead of base surface").ShowSubgrids = True
        obj.addProperty("App::PropertyBool", "AutoHideBlend", "S2 - Display",
                        "hide subgrids covered by a blend").AutoHideBlend = True
        obj.addProperty("App::PropertyVectorList", "Poles", "C2 - Outputs", "Poles").Poles
        obj.addProperty("App::PropertyFloatList", "Weights", "C2 - Outputs", "Weights").Weights
        obj.addProperty("Part::PropertyGeometryList", "Legs", "C2 - Outputs",
                        "grid segments").Legs
        obj.addProperty("App::PropertyString", "object_type", "C3 - Identifiers",
                        "workbench class").object_type = "Patch"
        obj.setEditorMode("object_type", 1)
        # #46: last-known boundary edge identities. The edge COUNT alone
        # cannot detect a deleted edge (4 -> 3 is a legal pointed fill),
        # so the Patch remembers the NAMES it was last successfully built
        # from and identity-diffs them on every execute. Internal + Output
        # (the #59 _HiddenSubgridIdxs technique): the bookkeeping write in
        # _record_last_edge_names must not re-touch the object, or it
        # would break the Blend <-> Patch settle invariant #59 established.
        obj.addProperty("App::PropertyStringList", "_LastEdgeNames", "Internal",
                        "last-known boundary edge identities")._LastEdgeNames = []
        obj.setEditorMode("_LastEdgeNames", 1)
        try:
            obj.setPropertyStatus("_LastEdgeNames", "Output")
        except Exception:
            pass
        obj.addProperty("App::PropertyString", "object_version", "C3 - Identifiers",
                        "class version").object_version = "0.01"
        obj.setEditorMode("object_version", 1)
        obj.addProperty("App::PropertyString", "internalName", "C3 - Identifiers",
                        "permanent internal FreeCAD name").internalName = obj.Name
        obj.setEditorMode("internalName", 1)
        obj.Proxy = self
        self._subgrids = []
        self._subgrid_weights = []      # #107: one flat 16-weight net per cell
        self._subsurfaces = []
        self._sub_legs = []
        self._base_surface = None
        # #89: ensure the app-level cascade observer is installed on
        # first Patch create too (idempotent -- module-flag dedupe).
        try:
            from SilkBlend import ensure_cascade_observer
            ensure_cascade_observer()
        except Exception:
            pass
        # #67: re-entrancy guard for the Edges-cycle write. See
        # _store_boundary_cycle.
        self._normalizing_edges = False
        # #82: re-entrancy guard for the split-normalization write below.
        # Writing the canonical value re-enters onChanged, which is a
        # no-op the second time round (the pair is already canonical), but
        # the flag makes that structural instead of incidental.
        self._normalizing_splits = False

    def onDocumentRestored(self, obj):
        # #89: a restored (legacy) patch+blend must also get the cascade
        # observer, so a patch deleted from under a restored blend still
        # cascades it. Idempotent -- module-flag dedupe.
        try:
            from SilkBlend import ensure_cascade_observer
            ensure_cascade_observer()
        except Exception:
            pass
        # #82: a Patch saved before the band edges existed comes back
        # without any of the four properties -- __init__ does not run on
        # restore, and no migration is shipped, so the old USplits /
        # VSplits lists stay behind as inert dynamic properties and this
        # object has to be given the four properties to be editable at
        # all. They are created at their SENTINELS, so such a document
        # comes back with no bands: the neutral state, exactly what the
        # human asked for ("no backwards compatibility is needed").
        self._ensure_split_properties(obj)
        ensure_leader_cuts(obj)
        obj.recompute()

    @staticmethod
    def _ensure_split_properties(fp):
        """Give `fp` the four named band edges if it has none (#82).

        Same shape as `_ensure_last_edge_names` (#46): the property has to
        exist before anything can read or write it, and the case that
        needs this is a document saved before #82, whose Patch arrives
        with the old split lists and none of these."""
        for letter in ("U", "V"):
            for n, sentinel in ((1, NO_BAND_1), (2, NO_BAND_2)):
                name = "%sSplit%d" % (letter, n)
                if not hasattr(fp, name):
                    fp.addProperty(
                        "App::PropertyFloat", name, "S1 - Subdivision",
                        "band edge at the parametric-%d end of the %s axis; "
                        "%g = no band at that end"
                        % (n - 1, letter, sentinel))
                    setattr(fp, name, sentinel)

    def onChanged(self, fp, prop):
        # #61/#82: normalize the band edges ON SET, so the stored value is
        # always the one the geometry actually used. Before this, a
        # rejected entry (0.0, 1.0, a negative, >1, a repeat) stayed
        # visible in the property editor while the geometry silently
        # dropped it — property and geometry disagreed, and nothing in
        # the UI said so (#53 display residue).
        #
        # Both halves, deliberately:
        #   - rewrite the property with what is actually used, so the
        #     stored value can never show a position the geometry would
        #     discard;
        #   - say what was corrected, so a mistyped width is not silently
        #     swallowed. Normalizing alone would hide the mistake;
        #     messaging alone would leave the residue the ticket is
        #     about.
        #
        # With #82 the correction is much narrower than the list rule it
        # replaces: a scalar outside [0, 1] becomes its slot's sentinel
        # ("no band at this end"), and a pair whose two edges are out of
        # order is swapped. Both are lossless, both are what the geometry
        # used, and #76's over-limit refusal is GONE rather than moved --
        # a third split cannot be written, so there is nothing to refuse
        # (see the note at SilkMachinery.corner_cells).
        if prop in ("USplit1", "USplit2", "VSplit1", "VSplit2"):
            try:
                self._normalize_splits_on_set(fp, prop)
            except Exception:
                pass   # never let housekeeping break the object
        if prop in ("ULeader1", "ULeader2", "VLeader1", "VLeader2"):
            try:
                normalize_leader_on_set(fp, prop)
            except Exception:
                pass   # never let housekeeping break the object
        if prop == "ShowGrid":
            # A DISPLAY toggle must not leave the object dirty: FreeCAD
            # sets the Touched flag on every property write, so the next
            # document recompute pass rebuilt the patch for a change that
            # only decides what is DRAWN (the control grid is a view node).
            # Same fix as the blend's and the corner's.
            try:
                fp.purgeTouched()
            except Exception:
                pass
            return
        # Guard: only recompute if object is fully initialized (has inputs)
        #
        # `ShowGrid` is NOT in this list, and that is the fix for a display
        # toggle costing seconds. The control grid is a VIEW node (the view
        # provider draws it from the stored Legs), so showing or hiding it
        # changes nothing about the geometry: the view provider's
        # `updateData` already refreshes the node. Recomputing the patch for
        # it rebuilt the fill, the subgrids and the surface for nothing, and
        # the panel's "hide grids" button writes the property on every
        # object, so the whole document paid for it. `ShowSurface` and
        # `ShowSubgrids` DO stay: they decide what `build_display` puts in
        # the shape, so they need the build.
        if prop in ("USplit1", "USplit2", "VSplit1", "VSplit2",
                    "ULeader1", "ULeader2", "VLeader1", "VLeader2",
                    "ShowSurface", "ShowSubgrids", "reverse"):
            if getattr(self, "_normalizing_splits", False):
                # This onChanged IS the corrective write _normalize_splits_on_set
                # just made (a clamp or a swap); the user's outer write is
                # still in flight above and will settle the axis once. Doing
                # it here too would run the whole chain twice per edit.
                return
            from SilkMachinery import is_refollowing
            if is_refollowing():
                # #132: a corner is re-deriving its own cut from this patch's
                # band edges, and it is doing so from inside its OWN execute.
                # The patch must still be rebuilt -- the framework marks it
                # Touched after this write and re-runs it, then the corner, in
                # the next pass of the same document recompute -- but a NESTED
                # doc.recompute() from inside an execute is exactly the
                # re-entrancy #125 removed, so only that is skipped.
                fp.touch()
                return
            if 'Restore' not in fp.State and hasattr(fp, "Edges") and fp.Edges:
                fp.touch()
                # #109: a band-edge write is the one property that feeds the
                # whole downstream chain (patch -> blend -> corner), and every
                # link of that chain only TOUCHES its dependent -- a touch is
                # not a recompute. A single-object fp.recompute() therefore
                # rebuilt the patch and left the blend (and, through it, the
                # corner) reading the pre-edit subgrids until some caller ran
                # a document pass, which a bare property write (data tab,
                # expression, script, ops) never does. Band edges settle the
                # DAG with a DOCUMENT recompute; the display toggles only
                # change what this patch draws, so they keep the single-object
                # recompute. `fp.touch()` first is deliberate -- FreeCAD sets
                # this object's Touched flag only AFTER onChanged returns, so
                # without it the pass below would skip the patch itself.
                doc = fp.Document
                if (prop in ("USplit1", "USplit2", "VSplit1", "VSplit2",
                             "ULeader1", "ULeader2", "VLeader1",
                             "VLeader2")
                        and doc):
                    doc.recompute()
                else:
                    fp.recompute()
        elif prop == "_HiddenSubgridIdxs":
            # A Blend writes this (run_blend's auto-hide bookkeeping)
            # AFTER it last recomputed this patch, so the display has to
            # be refreshed here or the patch keeps drawing the band cell
            # the blend just claimed -- the overlay #59 part 2 removes.
            #
            # It is a DISPLAY-ONLY property, so two things keep it from
            # re-arming the patch (#59 part 1):
            #   1. mark it Output, so FreeCAD does not flag the object
            #      Touched when the blend assigns to it (the flag is set
            #      AFTER onChanged returns, so a purge in here cannot
            #      beat it -- Output is the only thing that works);
            #   2. rebuild the display shape in place instead of going
            #      through touch + recompute. The blend's execute is
            #      running right now and is holding this patch's
            #      sub-surfaces; a full recompute here would touch the
            #      blend (this execute touches it back) and close a
            #      Patch <-> Blend cycle a settled doc.recompute() cannot
            #      close -- the patches stayed Touched forever.
            try:
                fp.setPropertyStatus("_HiddenSubgridIdxs", "Output")
            except Exception:
                pass
            self._rebuild_display(fp)
            fp.purgeTouched()

    def _normalize_splits_on_set(self, fp, prop):
        """Put `fp`'s axis into canonical form after a write to `prop`
        (see onChanged).

        One axis is ONE property and its partner, so this normalizes the
        PAIR: `SilkMachinery.normalize_edge_pair` clamps anything outside
        [0, 1] to that slot's own sentinel and swaps two real edges that
        were written the wrong way round. Writes only when the pair is not
        already canonical, so the common path (a blend's 0.1 / 0.9, a
        user's 0.3) costs nothing, and the guard makes the re-entrant
        onChanged that the write triggers a no-op. Nothing writes a band
        edge during a recompute, so this corrective write cannot open the
        Patch <-> Blend cycle #59 closed -- it only ever accompanies a
        user/ops write that already recomputes the patch.

        A correction is reported, because a mistyped width that silently
        became "no band here" is the #53 residue all over again -- except
        on a document restore, where it is fixed quietly: an old file
        should not greet the user with a complaint every time it opens.
        The next real edit reports again.
        """
        letter = prop[0]                      # "USplit1" -> "U"
        slot = int(prop[-1]) - 1              # "USplit1" -> 0
        before = split_pair(fp, letter)
        after = normalize_edge_pair(before[0], before[1])
        kept, why = (after[0], after[1])[slot], after[2]
        if before == (after[0], after[1]):
            return                            # already canonical
        if self._normalizing_splits:
            return
        self._normalizing_splits = True
        try:
            setattr(fp, prop, kept)
            # a swap moves BOTH names, so the partner is rewritten too; a
            # clamp is this property's business alone.
            if after[1 - slot] != before[1 - slot]:
                setattr(fp, "%sSplit%d" % (letter, 2 - slot),
                        after[1 - slot])
        finally:
            self._normalizing_splits = False
        if why and 'Restore' not in fp.State:
            FreeCAD.Console.PrintError(
                "Silk: Patch '%s': %s = %g -- %s, so the axis now stores "
                "%s = %g and %s = %g.\n"
                % (fp.Name, prop, before[slot], why, prop, after[0],
                   letter + "Split2", after[1]))

    def _rebuild_display(self, fp):
        """Recompose the display Shape from the cached base surface,
        sub-surfaces and grid legs (build_display), leaving Poles /
        Weights / Legs / the subgrid arrays alone. Used when only the
        display inputs changed (#59: a Blend writing the hidden-cell
        set)."""
        if self._base_surface is None:
            return
        has_subgrids = bool(axis_has_cuts(fp, "U") or axis_has_cuts(fp, "V"))
        base_legs = AN.drawGrid(list(fp.Poles), 4) if fp.Poles else []
        sub_legs = self._sub_legs if has_subgrids else []
        build_display(fp, self._base_surface.toShape(), self._subsurfaces,
                      base_legs, sub_legs, has_subgrids)

    # ---- #46: deleted-edge identity diff --------------------------------
    #
    # Deleting a boundary Edge behind the Patch's back is otherwise
    # SILENT. Std_Delete already warns for us -- it walks the InList and
    # pops "Object Dependencies - might break", because our view
    # providers keep the default canDelete=False (invariant: never
    # override canDelete to True) -- and then it cleanly removes the
    # dead link from `Edges`: no None left in the list, no exception, no
    # event. A 4-edge quad quietly shrinking to 3 is not an error at the
    # COUNT level either, because 3 edges is a legal POINTED fill (#38);
    # the loop only fails later with the cryptic "curves do not share
    # endpoints", which names a symptom and not the cause.
    #
    # So the Patch remembers the edge identities it was last built from
    # and identity-diffs them on every execute. The GUI warning covers
    # the interactive delete; this covers the script path
    # (doc.removeObject / Scripts / the future wizard), where nothing
    # else speaks up.

    def _ensure_last_edge_names(self, fp):
        """Lazy-create the hidden _LastEdgeNames property.

        __init__ does not run when an old document is restored, so a
        Patch saved before #46 arrives without the property; ensure it
        here too. Same shape as
        SilkMachinery.ensure_hidden_idxs_property (#59)."""
        if hasattr(fp, "_LastEdgeNames"):
            return
        fp.addProperty("App::PropertyStringList", "_LastEdgeNames",
                       "Internal", "last-known boundary edge identities")
        fp.setEditorMode("_LastEdgeNames", 1)
        try:
            fp.setPropertyStatus("_LastEdgeNames", "Output")
        except Exception:
            pass

    def _record_last_edge_names(self, fp, names):
        """Remember the boundary edge identities this patch is currently
        built from.

        Written on every execute that is NOT broken. The property is
        marked Output (the #59 _HiddenSubgridIdxs technique), so this
        bookkeeping write does not flag the object Touched -- the
        touched bit is set after onChanged returns, so a purge in there
        cannot beat it. execute()'s finally-purgeTouched is the backstop;
        between the two, the #59 settle invariant still holds."""
        self._ensure_last_edge_names(fp)
        fp._LastEdgeNames = list(names)

    def _check_deleted_edges(self, fp):
        """Name the boundary edge that was deleted out from under this
        patch (#46). Returns nothing; pure bookkeeping + reporting.

        Stateless by construction: while an edge is missing the baseline
        is deliberately NOT advanced, so the next execute diffs against
        the same last-known-good identities and reports again. There is
        no once-flag to leak or to go stale, and the message re-fires on
        every execute for as long as the patch stays broken.

        Only a pure SHRINK is reported (a known identity gone AND nothing
        new in its place). Deliberately re-wiring the link list through
        the property editor -- drop one edge, add another -- also removes
        a name, but that is a user edit, not a deletion, and crying
        "was deleted" at it on every recompute would be worse than
        silence."""
        edges = [e for e in (getattr(fp, "Edges", None) or []) if e is not None]
        current = [e.Name for e in edges]
        last = list(getattr(fp, "_LastEdgeNames", None) or [])

        missing = [n for n in last if n not in current]
        added = [n for n in current if n not in last]
        if last and missing and not added:
            for name in missing:
                FreeCAD.Console.PrintError(
                    "Silk: Patch '%s': boundary edge '%s' was deleted \u2014 "
                    "patch is incomplete (needs 3 or 4 edges).\n"
                    % (fp.Name, name))
            return          # baseline frozen -> re-fires next execute

        self._record_last_edge_names(fp, current)

    def getSubgrid(self, u0, u1, v0, v1):
        if self._base_surface is None:
            return None, None
        seg = self._base_surface.copy()
        seg.segment(u0, u1, v0, v1)
        return seg.getPoles(), seg.getWeights()

    # ---- fill selection --------------------------------------------------

    def _quad_fill(self, fp, inputs=None):
        """Replicate Patch44's ControlGrid44_4 fill from Edges[0..3].

        Produces the SAME 16 poles/weights/layout as Patch44 for the
        identical 4 edges in the same order (pole parity at 1e-6 is what
        later lets the unified pipeline reproduce the chain — #40).

        #66: the cycle is DERIVED from the edges' own endpoints, so the
        # list's own order no longer decides whether the patch builds.
        # The `Edges` property arrives in whatever order the user
        # produced — the panel collects in click order, the data tab can
        # be hand-reordered, an old document restores whatever it saved —
        # and walking it blind meant 16 of the 24 permutations of one
        # valid 4-edge loop produced a valid, up-to-date, INVISIBLE
        # ghost.
        #
        # #67: execute() has ALREADY normalized the stored list and
        # hands the cycle in through `inputs`, so the call below is the
        # structural no-op -- it returns that very list -- and this fill
        # reads the list the property shows. It stays (and keeps its
        # refusal path) because the fill must be callable standalone, and
        # because an in-order list must take the byte-identical path it
        # always did: that is the legacy pole parity, and the chain
        # ground truth rides on it.
        """
        inputs = list(inputs if inputs is not None else fp.Edges)
        tol = fp.tolerance
        edges, problem = loop_order(inputs, tol)
        if edges is None:
            FreeCAD.Console.PrintError(
                "Silk: Patch '%s': its %d boundary edges do not close a "
                "loop -- %s. No surface was built.\n"
                % (fp.Name, len(inputs), problem))
            return None

        p0 = list(edges[0].Poles)
        p1 = list(edges[1].Poles)
        p2 = list(edges[2].Poles)
        p3 = list(edges[3].Poles)
        w0 = list(edges[0].Weights)
        w1 = list(edges[1].Weights)
        w2 = list(edges[2].Weights)
        w3 = list(edges[3].Weights)

        quad12 = AN.orient_a_to_b(p0, p1, tol)
        if quad12 == 0:
            return None
        quad23 = AN.orient_a_to_b(p1, p2, tol)
        if quad23 == 0:
            return None
        quad34 = AN.orient_a_to_b(p2, p3, tol)
        if quad34 == 0:
            return None
        quad41 = AN.orient_a_to_b(p3, p0, tol)
        if quad41 == 0:
            return None

        if quad12[0] != p0[0] and quad12[0] == p0[-1]:
            w0 = list(reversed(w0))
        if quad23[0] != p1[0] and quad23[0] == p1[-1]:
            w1 = list(reversed(w1))
        if quad34[0] != p2[0] and quad34[0] == p2[-1]:
            w2 = list(reversed(w2))
        if quad41[0] != p3[0] and quad41[0] == p3[-1]:
            w3 = list(reversed(w3))

        p00 = quad12[0]; p01 = quad12[1]; p02 = quad12[2]; p03 = quad12[3]
        p13 = quad23[1]; p23 = quad23[2]; p33 = quad23[3]
        p32 = quad34[1]; p31 = quad34[2]; p30 = quad34[3]
        p20 = quad41[1]; p10 = quad41[2]

        p11 = p00 + (p01 - p00) + (p10 - p00)
        p12 = p03 + (p02 - p03) + (p13 - p03)
        p21 = p30 + (p31 - p30) + (p20 - p30)
        p22 = p33 + (p23 - p33) + (p32 - p33)

        poles = [p00, p01, p02, p03, p10, p11, p12, p13,
                 p20, p21, p22, p23, p30, p31, p32, p33]

        w00 = w0[0]; w01 = w0[1]; w02 = w0[2]; w03 = w0[3]
        w13 = w1[1]; w23 = w1[2]; w33 = w1[3]
        w32 = w2[1]; w31 = w2[2]; w30 = w2[3]
        w20 = w3[1]; w10 = w3[2]
        weights = [w00, w01, w02, w03, w10, w01 * w10, w02 * w13, w13,
                   w20, w20 * w31, w23 * w32, w23, w30, w31, w32, w33]

        return poles, weights

    def _pointed_fill(self, fp, inputs=None):
        """Replicate Patch33's ControlGrid44_3 fill from Edges[0..2].

        Produces the SAME 16 poles/weights/layout as Patch33 for the
        identical 3 edges in the same order (pole parity at 1e-6): the
        U=0 control column collapses to the point shared by edges 0 and
        2. Patch33's TweakWeight11 defaults to 1.0 and is a legacy-fill
        detail only -- the unified fill uses that default; no such
        property is added to the unified Patch.

        #68: `Edges` is a CYCLE here exactly as in the quad fill --
        row U0 = Edges[0], col V3 = Edges[1], row U3 = Edges[2], and
        the degenerate corner IS the Edges[2]->Edges[0] junction (the
        C1 layout). execute() hands the resolved cycle in through
        `inputs` (for a closed triple that is the caller's own list --
        every ordering of three corners is already cyclic, so this
        stays byte-identical to the legacy path); the fill re-runs
        loop_order on its own so it is safe standalone AND so a
        selection that is not a loop -- three edges fanned out of one
        point -- is REFUSED with the per-edge message instead of
        chained into corners that do not exist. That refusal is what
        keeps a pointed patch from disagreeing with its own geometry:
        the oracle checks Edges[k] is side k, so the honest object for
        a non-loop input is the empty/valid one, never 16 poles and a
        red C1/C2.
        """
        inputs = list(inputs if inputs is not None else fp.Edges)
        tol = fp.tolerance
        edges, problem = loop_order(inputs, tol)
        if edges is None:
            FreeCAD.Console.PrintError(
                "Silk: Patch '%s': its %d boundary edges do not close a "
                "loop -- %s. No surface was built.\n"
                % (fp.Name, len(inputs), problem))
            return None

        p0 = list(edges[0].Poles)
        p1 = list(edges[1].Poles)
        p2 = list(edges[2].Poles)
        w0 = list(edges[0].Weights)
        w1 = list(edges[1].Weights)
        w2 = list(edges[2].Weights)

        quad12 = AN.orient_a_to_b(p0, p1, tol)
        if quad12 == 0:
            return None
        quad23 = AN.orient_a_to_b(p1, p2, tol)
        if quad23 == 0:
            return None
        quad31 = AN.orient_a_to_b(p2, p0, tol)
        if quad31 == 0:
            return None

        if quad12[0] != p0[0] and quad12[0] == p0[-1]:
            w0 = list(reversed(w0))
        if quad23[0] != p1[0] and quad23[0] == p1[-1]:
            w1 = list(reversed(w1))
        if quad31[0] != p2[0] and quad31[0] == p2[-1]:
            w2 = list(reversed(w2))

        p00 = quad12[0]; p01 = quad12[1]; p02 = quad12[2]; p03 = quad12[3]
        p13 = quad23[1]; p23 = quad23[2]; p33 = quad23[3]
        p32 = quad31[1]; p31 = quad31[2]; p30 = p00

        # degenerate U=0 column collapses to the point p00
        p20 = p00
        p10 = p00

        p11 = p01 + p31 - p30
        p12 = p02 + p13 - p03
        p21 = p11
        p22 = p23 + p32 - p33

        poles = [p00, p01, p02, p03,
                 p10, p11, p12, p13,
                 p20, p21, p22, p23,
                 p30, p31, p32, p33]

        # Weights mirror ControlGrid44_3 (interior degenerate weights tie
        # to the outer boundary weights; TweakWeight11 at its legacy
        # default 1.0 scales the degenerate corner's draw).
        tweak = 1.0
        w00 = w0[0]; w01 = w0[1]; w02 = w0[2]; w03 = w0[3]
        w13 = w1[1]; w23 = w1[2]; w33 = w1[3]
        w32 = w2[1]; w31 = w2[2]; w30 = w2[3]
        w10 = tweak
        w20 = tweak
        weights = [w00, w01, w02, w03,
                   w10, w01 * w10, w02 * w13, w13,
                   w20, w31 * w20, w23 * w32, w23,
                   w30, w31, w32, w33]

        return poles, weights

    # ---- boundary cycle normalization (#67) ------------------------------

    def _store_boundary_cycle(self, fp, was, cycle):
        """Persist the resolved boundary cycle onto `fp.Edges` (#67).

        `was` is the list the fill was handed, `cycle` the loop
        `SilkMachinery.loop_order` derived from it. Returns True when the
        property was written.

        Three rules, and each one is load-bearing:

        1. WRITE ONLY WHEN IT DIFFERS. An already-cyclic list takes the
           path it has always taken -- that is the legacy Patch44/Patch33
           pole parity (0.00e+00) and the chain ground truth, so no write,
           no reserialization, no document churn. "Differs" is compared
           ELEMENT BY ELEMENT BY IDENTITY, not by list identity: the
           question we actually care about is "are the same edge objects
           in the same slots", and comparing that way does not lean on
           loop_order's internal trick of handing the caller's own list
           object back. A helper that helpfully rebuilt an equal list
           would still be recognized as unchanged.

        2. GUARDED AGAINST RE-ENTRANCY. The assignment fires onChanged,
           and execute() is already running. `Edges` is not in the
           recompute-trigger list (it is a link list, not a geometry
           knob), and the assignment's Touched flag is cleared by the
           purgeTouched() in execute()'s finally -- but a flag makes the
           invariant explicit rather than incidental: at most one write
           per execute, whatever FreeCAD decides to call in between.

        3. IDEMPOTENT, therefore CONVERGENT. After the write the stored
           list IS the cycle, so the next execute()'s loop_order returns
           it unchanged (rule 1) and writes nothing. Fixed point, no
           ping-pong -- asserted by the tests, not hoped for.
        """
        if len(was) != len(cycle):
            return False
        if all(a is b for a, b in zip(was, cycle)):
            return False                      # already the cycle
        if self._normalizing_edges:
            return False                      # rule 2
        self._normalizing_edges = True
        try:
            fp.Edges = list(cycle)
        except Exception:
            return False
        finally:
            self._normalizing_edges = False
        return True

    # ---- execute ---------------------------------------------------------

    def execute(self, fp):
        # #59, part 1 -- the Patch half of the Blend <-> Patch recompute
        # cycle. A settled document.recompute() used to leave the two
        # covered Patches of a freshly blended pair ['Touched'] forever
        # while the Blend read Up-to-date.
        #
        # The cycle, measured by tracing the execute/onChanged sequence:
        #   run_blend writes the band split -> Patch.onChanged touch +
        #   recompute -> run_blend writes _HiddenSubgridIdxs (blend's
        #   auto-hide bookkeeping) -> the patch is dirty, and its own
        #   execute then touches the blend -> the blend recomputes ->
        #   run_blend writes the hidden set AGAIN -> dirty again ...
        # A compute cycle FreeCAD cannot settle, so it stops and hands
        # back a permanently dirty patch.
        #
        # Two halves break it, both here in the Patch (no Blend change):
        #   (a) purgeTouched() on the way out -- this patch's geometry IS
        #       current when execute returns, so the flag means nothing;
        #   (b) the `_HiddenSubgridIdxs` branch in onChanged rebuilds the
        #       display in place instead of going through touch +
        #       recompute, so the blend's bookkeeping write no longer
        #       re-arms the patch.
        # (b) is also what makes the auto-hide actually VISIBLE: without
        # it the patch kept drawing the band cell the blend had just
        # claimed (the #59 part-2 overlay), because the blend writes the
        # hidden set after it last recomputed the patch.
        #
        # The #41 live-update chain is untouched: a user's band-edge edit
        # still runs onChanged's touch + recompute (that IS this execute),
        # and a blend that is not mid-execute is still touched below so it
        # refreshes on the next doc.recompute().
        #
        # #82 removed the #76 refusal that used to raise out of here: a
        # third split on an axis is no longer expressible, so there is no
        # input that can leave the patch holding something the geometry
        # will not use.
        try:
            self._execute(fp)
        finally:
            fp.purgeTouched()

    def _execute(self, fp):
        # Auto-update chain (#39 decision F): touch every blend that reads
        # this patch, so it recomputes against the updated subgrids --
        # the mirror of Patch44.execute's legacy strip touch (both blend
        # types scan; a document may mix unified Blends and legacy
        # BlendStrips during migration). Touch first, so the dependent
        # blend is covered even when this execute leaves early.
        #
        # #59: skip a blend that is mid-execute. It is reading this
        # patch's subgrids right now and will pick up what just
        # changed, so touching it only re-arms a blend that is already
        # running and re-opens the cycle above. A blend at rest (the user
        # -edit case) is touched as before, so #41 still holds.
        doc = fp.Document
        if doc:
            for obj in doc.Objects:
                if getattr(obj, "object_type", "") in ("Blend", "BlendStrip"):
                    if (getattr(obj, "PatchA", None) == fp
                            or getattr(obj, "PatchB", None) == fp):
                        if getattr(getattr(obj, "Proxy", None),
                                   "_in_execute", False):
                            continue
                        obj.touch()

        # #46: identity-diff the boundary edges BEFORE anything reads
        # them, so the precise "boundary edge was deleted" message fires
        # independently of whatever the fill then does with the
        # surviving (now non-closing) loop -- and whatever it does, the
        # patch keeps its last-known-good baseline and re-reports on the
        # next execute.
        self._check_deleted_edges(fp)

        inputs = [e for e in getattr(fp, "Edges", []) or [] if e is not None]
        if len(inputs) not in (3, 4):
            # Fills are picked from the edge count (#37 quad, #38
            # pointed); other counts leave the object empty/valid.
            fp.Poles = []; fp.Weights = []; fp.Legs = []
            self._subgrids = []; self._subgrid_weights = []
            self._subsurfaces = []; self._base_surface = None
            self._sub_legs = []
            build_display(fp, Part.Shape(), [], [], [], False)
            return

        # #67/#68: normalize the STORED boundary list before the fill
        # reads it, so the fill consumes exactly what the property
        # says. `Edges` is a cycle; it may arrive in any order (panel
        # click order, hand-order in the data tab, an old file's saved
        # order). `loop_order` derives the cycle from the edges' own
        # endpoints, the write below persists it, and the fill then
        # runs on the stored cycle -- which is what makes `Edges[k]`
        # boundary side k for ANY input order, not just for a
        # canonical fixture. Both counts go through the same gate now
        # (#68): the pointed fill's Edges means exactly what the quad
        # fill's does, row U0/col V3/row U3 = Edges[0]/[1]/[2] with
        # the degenerate corner at the Edges[2]->Edges[0] junction.
        #
        # For a closed 3-edge triple the write never fires, and that is
        # structural, not hopeful: with three corners every ordering is
        # already cyclic, so loop_order hands back the caller's own
        # list (pinned by test_pointed_corner_triple_loop_order_is_verbatim_in_every_ordering)
        # and the fill chains byte-identically to the legacy path --
        # Patch33 parity stays 0.00e+00. What the gate DOES change for
        # 3 edges: a selection that is not a loop -- three edges fanned
        # out of one point, which the per-edge adjacency check cannot
        # see for n=3 because there it is vacuous -- never reaches the
        # fill as buildable input; _pointed_fill re-runs loop_order
        # and refuses with the per-edge message. A list that does not
        # close is NOT written, for either count: a refusal leaves the
        # stored list exactly as the user had it, which is what they
        # can fix.
        fill_inputs = inputs
        if len(inputs) in (3, 4):
            cycle, _problem = loop_order(inputs, fp.tolerance)
            if cycle is not None:
                self._store_boundary_cycle(fp, inputs, cycle)
                fill_inputs = cycle

        filled = (self._pointed_fill(fp, fill_inputs) if len(inputs) == 3
                  else self._quad_fill(fp, fill_inputs))
        if filled is None:
            # degenerate / non-connecting loop: leave the object empty/valid
            fp.Poles = []; fp.Weights = []; fp.Legs = []
            self._subgrids = []; self._subgrid_weights = []
            self._subsurfaces = []; self._base_surface = None
            self._sub_legs = []
            fp.Shape = Part.Shape()
            return
        poles, weights = filled

        fp.Poles = poles
        fp.Weights = weights

        # Build bicubic Bezier surface from the 16-pole grid (matching Patch44)
        surf = Part.BSplineSurface()
        surf.increaseDegree(3, 3)
        for knot, mult in [(0.0, 4), (1.0, 4)]:
            surf.insertUKnot(knot, mult, 1e-7)
            surf.insertVKnot(knot, mult, 1e-7)
        for r in range(4):
            for c in range(4):
                idx = r * 4 + c
                surf.setPole(c + 1, r + 1, poles[idx], weights[idx])
        self._base_surface = surf

        # Grid lines
        legs = AN.drawGrid(poles, 4)
        fp.Legs = legs

        # Subdivision (shared machinery core). The axis pair is read by
        # NAME (#82): each edge belongs to the end that names it.
        u_pair = split_pair(fp, "U")
        v_pair = split_pair(fp, "V")
        u_leader = leader_pair(fp, "U")
        v_leader = leader_pair(fp, "V")
        has_subgrids = bool(axis_cuts(*u_pair, *u_leader)
                            or axis_cuts(*v_pair, *v_leader))
        self._subgrids, self._subgrid_weights, self._subsurfaces, sub_legs = \
            build_subgrids(surf, u_pair, v_pair, u_leader, v_leader)
        self._sub_legs = sub_legs   # cached for _rebuild_display (#59)
        if has_subgrids:
            fp.Legs = sub_legs

        # Compound display (shared machinery core)
        build_display(fp, surf.toShape(), self._subsurfaces, legs, sub_legs,
                      has_subgrids)


class PatchViewProvider:
    def __init__(self, vobj):
        vobj.Proxy = self

    def getIcon(self):
        return iconPath

    def attach(self, vobj):
        self.ViewObject = vobj
        self.Object = vobj.Object
        self._refresh_grid(self.Object, vobj)

    def _refresh_grid(self, obj, vobj):
        """Draw the patch's control grid as a Coin node (#108).

        The grid is no longer part of Shape (build_display keeps only the
        surface), so the view provider draws it: the legs build_display
        stashed (`obj.Proxy._display_legs`, already the base or the
        sub-grid set the toggles pick) and ShowGrid shows/hides the node.
        Headless (no ViewObject) is a silent no-op."""
        if obj is None or vobj is None:
            return
        proxy = getattr(obj, "Proxy", None)
        legs = list(getattr(proxy, "_display_legs", None) or [])
        set_grid_display(self, vobj, legs,
                         bool(getattr(obj, "ShowGrid", True)),
                         getattr(vobj, "LineColor", None),
                         getattr(vobj, "LineWidth", None))

    def updateData(self, obj, prop):
        if prop in ("Legs", "Shape", "ShowGrid", "ShowSubgrids",
                    "ShowSurface", "AutoHideBlend"):
            self._refresh_grid(obj, getattr(self, "ViewObject", None))
        return True

    def onChanged(self, vobj, prop):
        if prop in ("LineColor", "LineWidth"):
            self._refresh_grid(getattr(vobj, "Object", None), vobj)

    def __getstate__(self):
        return None

    def __setstate__(self, state):
        return None


class CreatePatch:
    """GUI command — select 3 or 4 Edge objects -> unified Patch.

    The edge count picks the fill (3 -> pointed, 4 -> quad);
    there is no fill-type knob. Mirrors SilkEdge.CreateEdge's
    selection-driven pattern (read Gui.Selection, build via the
    ops-layer constructor sequence, apply the patch color)."""

    def GetResources(self):
        return {'Pixmap': iconPath, 'MenuText': 'Patch',
                'ToolTip': PATCH_TOOLTIP}

    def Activated(self):
        sel = Gui.Selection.getSelection()
        if len(sel) == 0:
            tipsDialog("Silk: Patch",
                       "Select 3 or 4 boundary Edges (Silk Edge "
                       "objects).")
            return

        edges = [o for o in sel
                 if getattr(o, "object_type", None) == "Edge"]
        # #58: never silently drop a non-Edge from the selection. The
        # edge COUNT picks the fill, so a stray object quietly changes
        # the geometry: 4 edges + a Sketch used to be refused only as a
        # count error, but 3 edges + a Sketch passed the count check and
        # became a POINTED fill with the sketch discarded -- and if the
        # loop did not close the user got "curves do not share
        # endpoints" instead of the real mistake. Refuse, and name the
        # offenders so the fix is obvious.
        others = [o for o in sel
                  if getattr(o, "object_type", None) != "Edge"]
        if others:
            names = ", ".join(getattr(o, "Label", None) or o.Name
                              for o in others)
            FreeCAD.Console.PrintError(
                "Silk: Patch selection contains %d non-Edge object(s) "
                "(%s). Select 3 or 4 Edge objects only.\n"
                % (len(others), names))
            return

        if len(edges) not in (3, 4):
            FreeCAD.Console.PrintError(
                "Silk: Patch requires exactly 3 or 4 selected Edge "
                "objects (got %d Edge objects among %d selected).\n"
                % (len(edges), len(sel)))
            return

        # #66: the selection arrives in CLICK order, which is not the
        # order the fill walks. Refuse BEFORE constructing anything when
        # the edges do not close a loop, naming the offenders -- never
        # leave a valid, up-to-date, invisible object behind (#58's
        # idiom).
        order, problem = loop_order(edges, AN.default_tol)
        if order is None:
            FreeCAD.Console.PrintError(
                "Silk: the %d selected edges do not close a loop -- %s. "
                "A patch boundary is ONE closed loop of 3 or 4 edges "
                "meeting corner to corner. Nothing was created.\n"
                % (len(edges), problem))
            return

        doc = FreeCAD.ActiveDocument
        obj = doc.addObject("Part::FeaturePython", "Patch")
        Patch(obj, edges)
        PatchViewProvider(obj.ViewObject)
        obj.ViewObject.LineWidth = 1.50
        obj.ViewObject.LineColor = (0.67, 1.00, 1.00)
        obj.ViewObject.PointSize = 4.00
        obj.ViewObject.PointColor = (0.00, 0.33, 1.00)
        doc.recompute()
        FreeCAD.Console.PrintMessage(f"Patch created: {obj.Name}\n")

    def IsActive(self):
        return Gui is not None


Gui.addCommand("Silk_CreatePatch", CreatePatch())
