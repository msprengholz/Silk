# Silk upstream corner-type register

Upstream ArachNURBS corner/blend classes relevant to Silk's corner
implementation, classified by how our workflow uses them. Status values:
employed, parked-with-decision, not-used. Reason is one line.

## Register

| Type | Role | Employed by our workflow (location) | Status | Reasoning |
|---|---|---|---|---|
| ControlGrid44_4 | 4x4 base patch grid | SilkPatch equivalent | employed | We build the base patch grid directly rather than via ControlGrid44_4. |
| ControlGrid44_2EdgeSegments | 2-curve corner cell | SilkCorner.corner_inputs (member input) | employed | Feeds the triangular 4th member from the patch's ring corner cell (extracted with its weights via Patch.getSubgrid); the 3-valent hard-corner build succeeds (see silk-corner-type-taxonomy.md). |
| ControlGrid64_2Grid44 | 6x4 two-patch blend grid | SilkBlend | employed | Equivalent blend via AN blend helper + CubicSurface_64. |
| ControlGrid64_3_1Grid44 | triangular 4th member | SilkMachinery.control_grid64_3_1 (hidden in CornerBlend) | employed | Ported faithfully and unit-tested; builds the 3-valent hard corner (its collapsed end row is admitted by pair_common's degeneracy rule). |
| ControlGrid66_4Sub | four-subgrid corner fill | SilkMachinery/SilkCorner | employed | Four-ring fill from four sub cells. |
| SubGrid33_2Grid64 | 3x3 sub-cell | SilkMachinery | employed | Employed sub-cell conversion. |
| CubicSurface_44 | bicubic base surface | not employed | not-used | Patches create BSpline directly. |
| CubicSurface_64 | 6x4 blend surface | SilkBlend | employed | Created via AN.CubicSurface_64. |
| CubicSurface_66 | 6x6 corner fill | SilkMachinery/SilkCorner | employed | Corner fill surface. |
| CubicCurve_4 | curve geometry | SilkEdge | employed | Edge curves. |
| ControlPoly4_* | edge control polygons | SilkEdge | employed | Boundary edges. |
| ControlGrid3Star66_3Sub | 3-surface soft cup | parked | parked-with-decision | Deferred Demo 02/03. |
| ControlGridNStar66_NSub | N-surface star cup | parked | parked-with-decision | Deferred Demo 02/03. |
| ControlGridNStar66_StarTrim | star center refinement | parked | parked-with-decision | Deferred. |
| CubicNStarSurface_NStar66 | star cup output | parked | parked-with-decision | Deferred. |
| StarTrim_CubicNStar | pinch repair trim | parked | parked-with-decision | Deferred. |
| SubGrid63_2Surf64 | star cell | parked | parked-with-decision | Deferred. |
| ControlPoly6_* | 6-pole edge geometry | parked | parked-with-decision | Deferred. |

## Notes

No continuity claims.

| ControlGrid44_EdgeSegment | single edge-segment cell | not employed | not-used | Single-segment helper not used by unified workflow. |
| Point_onCurve | point-on-curve helper | not employed | not-used | Edge construction does not consume point-on-curve objects. |
