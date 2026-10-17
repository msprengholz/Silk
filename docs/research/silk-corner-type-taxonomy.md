# Silk corner types: taxonomy, rationale, and what our workflow uses

Source: read directly from the three demo files' `Document.xml` link graphs (offline, no FreeCAD
GUI) plus upstream's own class help. Each fact below cites the upstream object that states it.
The full four-file census (Demos 01/02/03 + `CadDivision_19`) is `docs/research/silk-demo-blend-census.md`.

## The three concretely observed corner families

| Demo | Junctions | Triangle (valence) | Bulk / seam mechanic | Fill object | Corner classification |
|---|---|---|---|---|---|
| D01 | 4 junctions | 3 surfaces each | 4 setback band strips (3 quad blends + 1 triangular 4th member) | `ControlGrid66_4Sub` → `CubicSurface_66` | 3-surface **hard corner, rolling fillet** |
| D02 | 1 junction | 3 surfaces | 3 soft corner cells (no band setbacks), each spanning 2 surfaces | `ControlGrid3Star66_3Sub` → `CubicNStarSurface_NStar66` | 3-surface **soft corner (star cup)** |
| D03 | (mul.) | up to 6 surfaces (valence up to 6) | star cup, with optional `StarTrim` pinch repair | `ControlGridNStar66_NSub` → `CubicNStarSurface_NStar66` (+ `StarTrim`) | N-surface **star corner** |

## Why Demo 01 is built the way it is (the "one four-sided fill + one triangular strip")

The underlying fill machinery is **fixed to a 4-member ring**. The band around a corner junction is segmented
into pieces, each patch's band piece is turned into a 3×3 sub-grid (`SubGrid33_2Grid64`) along its two
bounding seams, and the fill (`ControlGrid66_4Sub` → `CubicSurface_66`) joins 4 sub-grids into a 6×6 grid
that bridges the gap. So the fill *needs* 4 sub-grids — one per ring member.

- Where **4 surfaces** share a corner (paired seams) there are 4 seam blends → 4 sub-grids → pure
  four-sided fill. (This is the clean case; none of our demos happen to be purely valence-4, but
  D01's tooltip list cites it as the "proven use case".)
- Where **3 surfaces** share a corner there are only 3 seam blends — but the fill machinery still needs
  4. Silk's recipe (from `ControlGrid66_4Sub.py`'s own help):

  > "three surfaces meeting to form a hard corner (like a cube corner). Here more sectioning of the
  > original surfaces is required. You end up with 2 small blends, and one larger blend. use
  > `ControlGrid64_3_1Grid44` opposite the large blend to create the fourth blend. Now you have 4
  > blends across 3 surfaces, and can make the 4 SubGrids. The new grid/surface will produce a
  > 'rolling fillet' corner between the two small blends and the large blend."

So the triangular member (`ControlGrid64_3_1Grid44`, fed one `ControlGrid44_2EdgeSegments` 2-curve
corner cell + a `Corner` index) is **not an alternative to** the four-sided fill — it is the structural
fourth sibling the four-sibling fill demands. Its class comments also flag it as the weakest link:
the degenerate mapping "causes folding", and the "tiny spacing" workaround exists because it
"will break G1 slightly — balance G1 loss versus folding over."

## Why Demo 02 uses the star family instead

Demo 02 has three `ControlGrid44` base patches, three `ControlGrid64_2Grid44` blends, and then builds
the junction as `ControlGrid3Star66_3Sub` → `CubicNStarSurface_NStar66` from three
`SubGrid63_2Surf64` cells (one per 2-surface blend) instead of the 4-ring. The tool-tips say:
"SubGrid63 … Input for ControlGridNStar66 to blend three or more blended edges meeting at a corner,"
"ControlGridNStar66 … creates a ControlGridNStar66 from three to six SubGrid63_2Surf64 … a corner where
three or more CubicSurface_64 meet," and "StarTrim … Useful for eliminating pinch in poor corner
geometry."

So the star family is a different fill construction (`NSub` cups from 3–6 sub-cells) and scales with
valence, with a trim optional step for pinch repair.

## Why "so many options", and the robust answer

The options are not redundant UI knobs; they split on:

1. **Valence** — how many surfaces meet: ≤4 with paired seams → 4-ring; 3–6 → star cup.
2. **Intent** — smooth, low-loss transition (4 strong C¹/C² blends feeding a 4-ring) vs a softer
   rolling fillet for a hard corner (the triangular 4th).
3. **Pinch / surface quality** — star trim (Demo 03 culture) refines star junctions that fold.

So a junction type decides the construction, not the user's tool preference.

## Where our workflow stands (from this grilling)

| Upstream corner | Role | Employed by us? |
|---|---|---|
| `ControlGrid44_4` (4×4 base grid) | base patch | equivalent rôle via `SilkPatch`'s own 16-pole grid |
| `ControlGrid44_2EdgeSegments` (2-curve corner cell) | ring-member input | **employed** — the patch's ring corner cell (extracted with its weights via `Patch.getSubgrid`) feeds the triangular member inside `SilkCorner.corner_inputs`; the old base-net input was one of the two diagnosed refusal causes, now fixed |
| `ControlGrid64_2Grid44` (6×4 2-patch blend) | ring member | equivalent via `SilkBlend` (`blend_poly_2x4_1x6` → `CubicSurface_64`) |
| `ControlGrid64_3_1Grid44` (the triangular 4th member) | ring member @ 3-valent | **employed** (`SilkMachinery.control_grid64_3_1`, hidden inside `CornerBlend`); the positive 3-valent build now succeeds — see "3-valent state" |
| `SubGrid33_2Grid64` | 4-members → 4-sub corner | employed (`SilkMachinery`) |
| `ControlGrid66_4Sub` / `CubicSurface_66` | 4-patch fill | employed |
| `ControlGrid3Star66_3Sub` / `ControlGridNStar66_NSub` | soft N-valent star cup | parked for later (D02/D03 deferral) |
| `CubicNStarSurface_NStar66` (+ `StarTrim`) | star cup output / pinch repair | parked |

Decision recorded:
- Corner stage scoped to **Demo 01** (four 3-valent hard corners). The triangular 4th member is
  built into the corner stage invisibly (per the earlier decision), faithful to upstream; the
  positive 3-valent build now succeeds on the cube-corner fixture — see below.
- The **star family is deferred** to a later subproject with Demos 02/03 (which also carries the
  missing-class finding from the census: Demo 02's stored `ArachNURBS.ControlGrid3Star66_3Sub`
  does not exist in today's `ArachNURBS.py`).
- FreeCAD `Surface::Filling` is **deferred, not rejected** (2026-10-17; #96 reopened, #99 closed; see
  `docs/adr/0005-corner-blending.md` "Reversal"). The fork ships Silk's own maths only: the
  four-ring path fills every corner it can fill, and a user who wants a fill uses FreeCAD's
  Surface workbench by hand, outside the wizard. Consequence: the triangular member, which
  upstream calls a *"stepping stone"* rather than a final surface, is **our final surface**.
- Register + drift-guard added so every ArachNURBS corner type is classified before the suite goes green.

## 3-valent state (built on the cube-corner fixture)

`Tests/cube_corner_model.py` builds three planar patches meeting like a cube corner (oracle-green,
strips resolve as the 3-cycle ring) and `create_corner_blend` now BUILDS on it. Both diagnosed
causes were fixed in the member stage, not the fixture:

1. **Member input**: the search now extracts each patch's ring **corner cell** (the subgrid cell at
   the junction, through `Patch.getSubgrid` so the rational weights come with it) and searches
   corner index + reversal for the member whose collapsed row lands on the ring's shared corner.
   The old input — each patch's full 4x4 base net — has its corners on the patch vertices and can
   never land on the ring; the member is also inserted between the two ring strips that meet at the
   chosen patch, so a ring built the other way round normalizes through `corner_grid`'s mirrored
   path.
2. **Degenerate-corner matching**: the member's collapsed end row puts TWO of its corner slots on
   the neighbour's shared corner. `pair_common` now admits exactly that case — all matches on one
   point, exactly one grid presenting the duplicated slots, and those slots forming one collapsed
   end row — and returns the pairing the subgrid reader consumes ((3,2), or its mirror (2,3) for a
   ring traversed the other way). Two distinct shared corners, duplicates across a column, or two
   facing collapsed rows still refuse.

Measured (`Tests/test_cube_corner_3valent.py::test_3valent_cube_corner_seam_measurement`, n=21,
sampled + exact instruments, floor from `Tests/continuity_calibration.py`):

- Build: 36 poles, 1 face, non-empty Shape, idempotent second ask; `c0_controlnet` 0 on all three
  strip seams (exact c0 ≤ 4.2e-17 mm).
- The corner's fourth side is the member's collapsed row. The two seams terminating there read a
  degenerate-boundary normal at their apex-side stations (g1 = 90 deg there, exactly as
  `Tests/g2_edge_blend_probe.py` records for the demo's hard-corner members); their `k_gap`,
  which upstream's folded net read at 3.5e+2 /mm, is 2.0e-13 /mm exact / 2.4e-3 /mm sampled after
  the fold fix. The seam opposite the member (corner `v0` / strip `B_BC`) is smooth: exact
  `k_gap` 6.9e-15 /mm, sampled 4.6e-3 /mm (finite-difference bias above the calibrated floor).
  `twist_gap` is reported but the B_AB seam is a reversed correspondence (#101), so it is not
  evidence there.
- **The fold is gone (ticket-foldfix).** Upstream's subgrid chain extrapolates subgrid interiors
  PAST the member's collapsed row; on this fixture that pushed the cap's member-side interior
  beyond the apex and doubled it over (19/1521 normal-field flips at n=39 on the parity member;
  the fold was upstream's, not the port's, and independent of the member's tiny-spacing factor —
  a sweep of it never reached 0 flips). `SilkMachinery.smooth_degenerate_cap` re-solves the two
  member-side interior rows of the assembled 6x6 from the transfinite (Coons) fill of the corner's
  own boundary loop (weights held fixed), leaving the collapsed boundary and the three strip-side
  rows untouched. Measured after the fix: **0 flips** at n=39/81/150 on the Part surface and on the
  exact net (the folded net's reversal is continuous, not a discontinuity: it reads 0 at n=300 too,
  so the coarse count is the aliased reading of a tight crease), all samples inside the boundary box
  (the fold had poked 0.0101 mm past it), Shape
  valid, no self-intersections; the opposite seam's exact G1 (0.0000 deg) and `k_gap` are
  preserved because they read the first three control rows only. No continuity label is asserted
  anywhere.

For comparison, the 4-valent corner measured with the same seam-matching code (and untouched by
the smoothing — a collapsed side is what gates it): g1 ≤ 2.0e-4 deg, k_gap ≤ 1.0e-2 /mm (the
strong-link reference of #97/#100), CB2 pole parity with the legacy chain intact.
