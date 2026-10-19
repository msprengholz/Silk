# Silk

Geometry-modeling language of the Silk workbench: the boundary-curve →
surface → transition pipeline and the objects it produces.

## Language

**Edge**:
A boundary curve object built from one or two sketches; the atomic input of a patch.
_Avoid_: curve, wire, BoundarySpline

**Patch**:
A bicubic surface bounded by three edges (pointed fill) or four edges (quad fill).
_Avoid_: control grid, ControlGridPatch, surface patch

**Blend**:
A transition strip joining the bands of two adjacent patches along their shared boundary.
_Avoid_: blend strip, BlendStrip

**Subgrid**:
One cell of a patch's surface subdivision.
_Avoid_: subpatch, segment

**Band**:
The row of subgrid cells on a patch adjacent to its seam, consumed by the patch's blend.
Its **band width** (the `USplit`/`VSplit` scalar at that seam's end of that axis) is the
maintainer's video's *setback* -- the same property, and both words are in use.
_Avoid_: strip, blend band

**Seam**:
The boundary line where two adjacent patches meet, occupied by their shared edge.
_Avoid_: common edge line

**Free edge**:
An Edge not yet referenced by any Patch; the pool a new patch is built from.
_Avoid_: unused edge, unclaimed edge, available edge

**Shared edge**:
The single Edge object referenced by both of two adjacent patches' boundaries; the only admissible evidence that two patches are adjacent.
_Avoid_: coincident edge, geometric adjacency

**Coincident boundary**:
Patch boundaries that meet geometrically without sharing a shared edge; not a valid basis for blending.
_Avoid_: implicit seam, loose adjacency

**Corner cell**:
The subgrid cell where the bands of two seams meet at a patch corner; reserved for corner fills, never part of a band.
_Avoid_: corner subgrid

**Corner fill**:
The surface that closes the gap where four bands meet at a four-patch corner. FreeCAD's
`Surface::Filling` over a boundary wire (`Silk_CornerFill`), **not** a `CornerBlend`.
_Avoid_: corner blend, corner patch

**Corner blend**:
A `CornerBlend`: the single 6x6 surface closing the junction of three or four patches,
built from the ring of strip blends (four subgrids). Three- and four-patch junctions only;
five or more is refused by name -- use a corner fill there.
_Avoid_: corner surface, corner patch, corner subgrid

**Triangular member**:
The degenerate grid with a collapsed row (`ControlGrid64_3_1Grid44`) a three-patch corner
needs to reach the four subgrids its fill machinery demands. Upstream calls it a
*scaffolding piece*; the collapsed row gives a degenerate-boundary normal on the two seams
that touch it.
_Avoid_: triangular patch, fake blend, fourth strip

**Rolling fillet**:
The maintainer's name for a corner showing **two zones of different fillet size** -- one
large fillet in one direction, a small one that appears to roll around it. **The author's
effect, judged by eye**, and **we do not have it**: our 3-valent corner is ONE 6x6 whose
outline is the band edge -- a rounded triangle with rounded corners -- and the owner's
look at the render (2026-10-21) ruled that this is not a rolling corner. What is measured
is *anisotropy* (asymmetric setbacks move its curvature spread 1.04 -> 2.29) and, past a
threshold, a *saddle* -- and a saddle is a twist, not two fillets. The two-zone look
needs the **sectioned** recipe: cut each blend along its seam and re-create the preserved
remainder as its own surface (`docs/corner-blending.md`, #119).
_Avoid_: our corner is a rolling fillet (overclaim)

**Restore shim**:
A class + view provider kept in a module only so an old document that saved
objects of that class can rebuild their proxies when it opens; nothing creates
one any more (`Patch44`, `Patch33`, `BlendStrip`).
The **restore contract** it carries: FreeCAD rebuilds a restored proxy from the
saved (empty) state and then calls `onDocumentRestored` -- **it never runs
`__init__`** -- so every registration a fresh object gets in `__init__` (the
blend's delete-watcher) must be re-established on the restore path too, through
a guard that does not depend on `__init__` having run. A restored object is a
live, editable one: deleting a restored blend must unblend its patches exactly
as deleting a freshly created one does.
_Avoid_: restore hook, migration class
