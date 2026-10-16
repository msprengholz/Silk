# Silk Demo 01 — inventory (stored object graph)

Source: `Resources/Test_files/Silk_Workflow.FCStd` (9 end-user sketches `Sketch`..`Sketch008`, 7 Edges, 2 Patches, 1 Blend). The Demo 01 geometry composes this workflow patch set into 4 junctions (triangular 4th member is pending — see below).

## Edges (7) → Sketches

| Edge     | Sketches            | notes             |
|----------|---------------------|-------------------|
| E_Top    | Sketch007, Sketch008   | 2 sketches        |
| E_Left   | Sketch005              |                   |
| E_BtmL   | Sketch006              |                   |
| E_Shr    | Sketch                 | shared seam edge  |
| E_BtmR   | Sketch001             |                   |
| E_CurR   | Sketch003, Sketch004   | 2 sketches        |
| E_TopR   | Sketch002             |                   |

## Patches (2) — by boundary layer (Poly* edges)

- Patch44 — [E_Top, E_Left, E_BtmL, E_Shr]
- Patch001 — [E_Shr, E_BtmR, E_CurR, E_TopR]

Shared edge pin: `E_Shr` (Edge → Sketches linker). Blend: `Patch44 ↔ Patch001`
(`BlendStrip`).

## Junction rings (4)

Each junction = 3 quad patches + 1 triangular 4th member
(`ControlGrid64_3_1Grid44`), ring = (ControlGrid64_2Grid44 ×3) +
(ControlGrid64_3_Grid44 ×1); subgrids
`SubGrid33_2Grid64 ×4 → ControlGrid66_4Sub → CubicSurface_66`. The
triangular member is **not yet implemented in the ops layer** (tracked
in the ticket family), so a `CornerBlend` refuses on these inputs.

## Status

- Blend-strip path (non-corner) is `check_blend`-green.
- Every Patch produced from the ops layer passes `check_patch(p, list(p.Edges))`.
- k-gap: use #97/#90 reference numbers (3.1e-2 / mm on the legacy
  corner; attainable 7.1e-3 / mm on legacy neighbours with the G2
  continuation solve). Twist_gap is **not** reversal-invariant — report
  with reversal caveat only.
