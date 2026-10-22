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

**Rolled corner** (also *rolling corner*):
**TWO patches meeting along the rolling leader** -- the **quad** (a `ControlGrid66_4Sub` ->
`CubicSurface_66` built from the four subgrids between consecutive ring members, with the
triangular member **one of the four**, so its interior is the ring hole) and the **tri**
(the member's **own** surface, beside the quad, sharing the leader boundary). Signature
to check against the reference files: **every member is read by THREE consumers** -- its
own `CubicSurface_64` and two `SubGrid33_2Grid64`. A corner where ONE patch wraps the
whole region is **not** this, and curvature numbers do not make it so.
_Avoid_: "it rolls" (a curvature reading, not a construction); "one surface spanning the
corner" (that is the shipped fallback)

**Quad** / **Tri** (in a rolled corner):
the **quad** is the 66 above; the **tri** is the member's own face -- its spiderweb
`CubicSurface_64`, or a FreeCAD fill over the member's **three real boundary curves plus
the apex**. The tri sits **beside** the quad, not inside it: measured on the maintainer's
file the tri interior is **16-62 %** of the corner extent away from the quad, where a
wrapping patch reads **0.1-10 %**.
_Avoid_: using "tri" for a fill drawn over a region the quad already covers

**Preserved piece**:
One CELL of a ring patch's own surface, kept as a separate object beside a rolled corner
-- the surface the corner's two surfaces (the quad and the tri) do **not** cover. A
rolled corner has **FIVE**, measured from the maintainer's file: **three** from the patch
that carries the tri (the cells one step beyond the member's cell in u, in v, and the
diagonal one) and **one** from each of the other two patches (the cell diagonally beyond
its corner cell). Silk builds them as `PreservedPiece` objects, recorded on the corner's
`Pieces` link list; the cell comes from `SilkMachinery.preserved_piece_cells`.
_Avoid_: "patch remnant", "spare surface"; a preserved piece is never a re-fitted copy of
the patch -- it is the patch's own cell, cut on knot lines the patch already carries

**Rolling leader**:
a position on the seam curve, measured from the junction corner, that **must be an
independent cut** -- separate from the band edge (the setback). The maintainer has TWO
cuts per axis end (setback 1/16 and leader 1/4); Silk carries one band edge per axis end
(#82), so the leader exists as `ULeader1/2` / `VLeader1/2`, default unset = byte-identical.
_Avoid_: writing the leader into the band edge (that makes setback and leader one number,
which pinches the corner's 4th side -- the exact defect this vocabulary exists to stop)

**Equal-sided default** (`equal`):
the leader the user has NOT placed. The stage then **equalises** the two cuts that bound the
triangular member -- the same length in mm, at the geometric mean of the sizes the old
parameter default gave them (`SilkWorkflowOps.equal_cut_length` / `equal_cut_legs`) -- which
is the owner's rule and what makes the triangle roughly even-sided. It is the panel's
per-seam default (`CORNER_LEADER_AUTO`: the editor's own 0 shows "equal") and is spelled
`leader=None` / a seam left out of `leaders` in the ops layer.
_Avoid_: calling it a length (it is the ABSENCE of one), and quoting it as a u/v fraction
-- the rule is measured in mm along the seam curve

**Spiderweb**:
the control net of a grid with a **collapsed row** (`ControlGrid64_3_1Grid44`), drawn as a
web of lines to a point. It is a **scaffolding** grid: usable as a ring member, not as a
corner face.
_Avoid_: "the spiderweb" used for any corner surface -- the shipped corner's net is a
perfectly ordinary 6x6

**Rolled-fillet look**:
the maintainer's *design* effect -- one large fillet and one small one that appears to roll
around it, so the eye follows a single continuous break instead of seeing a cross. It is
the **reason** the corner is built with two zones of different size; it is judged by eye
and is **not** the acceptance for the construction. Named *rolling blend* by the author.
_Avoid_: using it as a synonym for the construction (a corner can be built correctly and
still be judged to look wrong, and vice versa)

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
