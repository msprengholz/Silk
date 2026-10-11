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
_Avoid_: strip, blend band

**Seam**:
The boundary line where two adjacent patches meet, occupied by their shared edge.
_Avoid_: common edge line

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
The surface that closes the gap where four bands meet at a four-patch corner.
_Avoid_: corner blend, corner patch
