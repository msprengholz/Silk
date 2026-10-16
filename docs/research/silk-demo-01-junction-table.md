# Silk Demo 01 — junction table

| Junction | Patches | Strips (Blend objects) | Continuous? | k_gap (g/m) measured |
|----------|---------|------------------------|-------------|----------------------|
| J1 | QBR,QTR,QTL,QBL | Seam_B, Seam_R, Seam_T, Seam_L | no (4-ring; corner deferred) | see #97 3.1e-2 |
| J2 | (mirrors J1 pattern) | (same seam set) | no | same |
| J3 | (mirrors J1 pattern) | (same seam set) | no | same |
| J4 | (mirrors J1 pattern) | (same seam set) | no | same |

## Notes
- 3 quad + 1 triangular 4th member per junction (#98 family), not built.
- CornerBlend refuses with only 3 strips; gap tracked.
- Twist_gap reported with reversal caveat only.

