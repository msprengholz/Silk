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

**Triangular member** (the tri's net):
The 6×4 net with one collapsed row (`ControlGrid64_3_1Grid44`) that the triangular patch
carries. In a rolled corner it is **one of the quad's four ring members** AND the tri's own
face, read REAL-ROW-FIRST; only the shipped fallback uses it as a fake fourth ring member
(`docs/adr/0006-rolled-corner-is-two-patches.md`).
_Avoid_: calling it a filler that exists to reach four subgrids, fake blend, fourth strip

**Rolled corner** (also *rolling corner*):
**TWO patches meeting along one curve**, plus the cells the division leaves: the **quad**
(a `ControlGrid66_4Sub` -> `CubicSurface_66` over four ring members, the triangular
member's net being one of them), the **tri** (a patch of its own, adjacent to the quad,
sharing one curve with it, covering no area the quad covers), and **five preserved
pieces**. The cut is a LENGTH in mm per seam, equalised by default. Stated once in
`docs/adr/0006-rolled-corner-is-two-patches.md` -- that file is the definition; this entry
is the pointer. A corner where ONE patch wraps the whole region is **not** this, and
curvature numbers do not make it so.
_Avoid_: "it rolls" (a curvature reading, not a construction); "one surface spanning the
corner" (that is the shipped fallback)

**Quad** / **Tri** (in a rolled corner):
the **quad** is the 66 above; the **tri** is the patch beside it, whose **face** is its own
net's `CubicSurface_64` (the construction the maintainer's files store) or a FreeCAD fill
over its **three real boundary curves**. It sits **beside** the quad: the two share one
curve and cover **no common area**, which is the property to measure. The interior-distance
percentage the maintainer's file gives (16-62 % of the corner extent) is a **reading**;
Silk's own corner reads 3.51-37.08 % on the demo, and below his floor is not green.
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
a LENGTH in mm along the seam curve, measured from the junction corner, that **must be an
independent cut** -- separate from the band edge (the setback). The maintainer has TWO
cuts per axis end (setback 1/16 and leader 1/4); Silk carries one band edge per axis end
(#82), so the leader exists as `ULeader1/2` / `VLeader1/2`, default unset = byte-identical,
written on the patch that carries the tri (#129: mm, never a u/v fraction).
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
web of lines to a point. It is the **tri's net** in a rolled corner, and the fake fourth
ring member in the shipped fallback.
_Avoid_: "the spiderweb" used for any corner surface -- the quad is a perfectly ordinary 6x6

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
