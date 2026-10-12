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
#    point rather than a ping-pong. The 3-edge pointed fill is NOT touched
#    -- its Patch33 parity rides on the list it is handed. (Not because it
#    is already order-independent: see the note at the normalization
#    site and #68.)

import FreeCAD
import Part
from FreeCAD import Gui

import ArachNURBS as AN
from popup import tipsDialog

from SilkMachinery import build_subgrids, build_display, \
    normalize_splits_report, loop_order

import os, Silk_dummy
path_Silk = os.path.dirname(Silk_dummy.__file__)
path_Silk_icons = os.path.join(path_Silk, "Resources", "Icons")
iconPath = path_Silk_icons + "/ControlGridPatch.svg"

ICON = "Resources/Icons/ControlGridPatch.svg"

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
        obj.addProperty("App::PropertyFloatList", "USplits", "S1 - Subdivision",
                        "U split parameters (0-1)").USplits = []
        obj.addProperty("App::PropertyFloatList", "VSplits", "S1 - Subdivision",
                        "V split parameters (0-1)").VSplits = []
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
        self._subsurfaces = []
        self._sub_legs = []
        self._base_surface = None
        # #67: re-entrancy guard for the Edges-cycle write. See
        # _store_boundary_cycle.
        self._normalizing_edges = False

    def onDocumentRestored(self, obj):
        obj.recompute()

    def onChanged(self, fp, prop):
        # #61: normalize the split lists ON SET, so the stored value is
        # always the one the geometry actually used. Before this, a
        # rejected entry (0.0, 1.0, a negative, >1, a repeat) stayed
        # visible in the property editor while build_subgrids silently
        # dropped it — property and geometry disagreed, and nothing in
        # the UI said so (#53 display residue).
        #
        # Both halves, deliberately:
        #   - rewrite the property with what is actually used, so the
        #     stored list can never show a value that would be
        #     discarded;
        #   - say what was dropped, so a mistyped width is not silently
        #     swallowed. Normalizing alone would hide the mistake;
        #     messaging alone would leave the residue the ticket is
        #     about.
        #
        # ...but only when the write lost EVERYTHING. Typing 0.2 into the
        # property editor commits a bare 0 on the way (the line edit fires
        # before the text is finished), so `USplits = [0]` normalizes to
        # `[]` and used to print an error while the user was still typing
        # -- a warning for input the editor never meant to send. Warning on
        # the genuinely suspicious case only, a non-empty input that
        # discards every one of its values ([0], [1.5], [-0.1, 2.0]), keeps
        # the mistyped-width report and drops the noise. The normalization
        # itself is untouched: the stored list still always equals what the
        # geometry used.
        #
        # The rule is unchanged (SilkMachinery.normalize_splits):
        # strictly inside (0, 1), strictly increasing, no repeats. It is
        # idempotent, and the write is guarded, so onChanged cannot
        # re-enter: the second pass sees an already-normalized list and
        # writes nothing.
        if prop in ("USplits", "VSplits"):
            try:
                self._normalize_splits_on_set(fp, prop)
            except Exception:
                pass   # never let housekeeping break the object
        # Guard: only recompute if object is fully initialized (has inputs)
        if prop in ("USplits", "VSplits", "ShowSurface", "ShowGrid",
                    "ShowSubgrids", "reverse"):
            if 'Restore' not in fp.State and hasattr(fp, "Edges") and fp.Edges:
                fp.touch()
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
        """Rewrite `fp.<prop>` as its normalized form (see onChanged).

        Writes only when the incoming value is not already normalized, so
        the common path (a blend's 0.1 / 0.9 band split, a user's 0.3)
        costs nothing and the guard makes the re-entrant onChanged that
        the write triggers a no-op. Nothing writes a split during a
        recompute, so this corrective write cannot open the Patch <-> Blend
        cycle #59 closed -- it only ever accompanies a user/ops write that
        already recomputes the patch.

        On a document restore the residue is fixed silently: an old file
        carrying a 0.0 split should not greet the user with a complaint
        every time it opens. The next real edit reports again.

        The same silence covers a PARTIAL correction -- a reorder, a
        duplicate, one mistyped value among good ones. Those are corrected
        and the stored list is right, so there is nothing for the user to
        act on; only a write that loses every value is worth a word (see
        onChanged for why the property editor's transient `0` must not
        raise one).
        """
        current = list(getattr(fp, prop, None) or [])
        kept, out_of_range, repeated = normalize_splits_report(current)
        if list(kept) == [float(v) for v in current]:
            return
        setattr(fp, prop, list(kept))
        if 'Restore' in fp.State:
            return
        if not current or kept:
            return      # a partial correction: correct it, do not scold
        why = []
        if out_of_range:
            why.append("outside (0, 1): %s"
                       % ", ".join("%g" % v for v in out_of_range))
        if repeated:
            why.append("repeated: %s"
                       % ", ".join("%g" % v for v in repeated))
        FreeCAD.Console.PrintError(
            "Silk: Patch '%s': %s = %s has no value strictly inside (0, 1) "
            "(%s) -- every entry was discarded, so no split is set. Enter "
            "a width between 0 and 1 if that was meant.\n"
            % (fp.Name, prop, ", ".join("%g" % v for v in current),
               "; ".join(why)))

    def _rebuild_display(self, fp):
        """Recompose the display Shape from the cached base surface,
        sub-surfaces and grid legs (build_display), leaving Poles /
        Weights / Legs / the subgrid arrays alone. Used when only the
        display inputs changed (#59: a Blend writing the hidden-cell
        set)."""
        if self._base_surface is None:
            return
        has_subgrids = bool(fp.USplits or fp.VSplits)
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

    def _pointed_fill(self, fp):
        """Replicate Patch33's ControlGrid44_3 fill from Edges[0..2].

        Produces the SAME 16 poles/weights/layout as Patch33 for the
        identical 3 edges in the same order (pole parity at 1e-6): the
        U=0 control column collapses to the point shared by edges 0 and
        2. Patch33's TweakWeight11 defaults to 1.0 and is a legacy-fill
        detail only -- the unified fill uses that default; no such
        property is added to the unified Patch.
        """
        p0 = list(fp.Edges[0].Poles)
        p1 = list(fp.Edges[1].Poles)
        p2 = list(fp.Edges[2].Poles)
        w0 = list(fp.Edges[0].Weights)
        w1 = list(fp.Edges[1].Weights)
        w2 = list(fp.Edges[2].Weights)
        tol = fp.tolerance

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
        # The #41 live-update chain is untouched: a user's USplits/
        # VSplits edit still runs onChanged's touch + recompute (that IS
        # this execute), and a blend that is not mid-execute is still
        # touched below so it refreshes on the next doc.recompute().
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
            self._subgrids = []; self._subsurfaces = []; self._base_surface = None
            self._sub_legs = []
            build_display(fp, Part.Shape(), [], [], [], False)
            return

        # #67: normalize the STORED boundary list before the fill reads
        # it, so the fill consumes exactly what the property says.
        # `Edges` is a cycle; it may arrive in any order (panel click
        # order, hand-order in the data tab, an old file's saved order).
        # `loop_order` derives the cycle from the edges' own endpoints,
        # the write below persists it, and the fill then runs on the
        # stored cycle -- which is what makes `Edges[k]` boundary side k
        # for ANY input order, not just for a canonical fixture.
        #
        # Only the quad (4-edge) fill is normalized. The 3-edge pointed
        # fill is left alone: its parity with Patch33 rides on the list it
        # is given. Do NOT read that as "the pointed fill is fine" -- it
        # builds poles for every ordering (6/6) but its OUTPUT is
        # order-dependent, and it does not satisfy the Edges[k]-is-side-k
        # invariant this method exists to establish: on a curved corner
        # triple it is oracle-red on 6/6. Pre-existing, tracked in #68.
        # A list that does not close is NOT written -- _quad_fill refuses
        # it with the per-edge message, and a refusal leaves the stored
        # list exactly as the user had it, which is what they can fix.
        fill_inputs = inputs
        if len(inputs) == 4:
            cycle, _problem = loop_order(inputs, fp.tolerance)
            if cycle is not None:
                self._store_boundary_cycle(fp, inputs, cycle)
                fill_inputs = cycle

        filled = (self._pointed_fill(fp) if len(inputs) == 3
                  else self._quad_fill(fp, fill_inputs))
        if filled is None:
            # degenerate / non-connecting loop: leave the object empty/valid
            fp.Poles = []; fp.Weights = []; fp.Legs = []
            self._subgrids = []; self._subsurfaces = []; self._base_surface = None
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

        # Subdivision (shared machinery core)
        self._subgrids, self._subsurfaces, sub_legs = build_subgrids(
            surf, fp.USplits, fp.VSplits)
        self._sub_legs = sub_legs   # cached for _rebuild_display (#59)
        if fp.USplits or fp.VSplits:
            fp.Legs = sub_legs

        # Compound display (shared machinery core)
        build_display(fp, surf.toShape(), self._subsurfaces, legs, sub_legs,
                      bool(fp.USplits or fp.VSplits))


class PatchViewProvider:
    def __init__(self, vobj):
        vobj.Proxy = self

    def getIcon(self):
        return ICON

    def attach(self, vobj):
        self.ViewObject = vobj

    def updateData(self, obj, prop):
        return True

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
