# Silk corner types: taxonomy, rationale, and what our workflow uses

Source: read directly from the three demo files' `Document.xml` link graphs (offline, no FreeCAD
GUI) plus upstream's own class help. Each fact below cites the upstream object that states it.

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
| `ControlGrid44_2EdgeSegments` (2-curve corner cell) | ring-member input | **not yet** — blocking D01 four-fill member |
| `ControlGrid64_2Grid44` (6×4 2-patch blend) | ring member | equivalent via `SilkBlend` (`blend_poly_2x4_1x6` → `CubicSurface_64`) |
| `ControlGrid64_3_1Grid44` (the triangular 4th member) | ring member @ 3-valent | upcoming build (#100/#97-culture measurement first) |
| `SubGrid33_2Grid64` | 4-members → 4-sub corner | employed (`SilkMachinery`) |
| `ControlGrid66_4Sub` / `CubicSurface_66` | 4-patch fill | employed |
| `ControlGrid3Star66_3Sub` / `ControlGridNStar66_NSub` | soft N-valent star cup | parked for later (D02/D03 deferral) |
| `CubicNStarSurface_NStar66` (+ `StarTrim`) | star cup output / pinch repair | parked |

Decision recorded:
- Corner stage scoped to **Demo 01** (four 3-valent hard corners). The triangular 4th member will be
  built into the corner stage invisibly (per the earlier decision), faithful, then measured in the
  #100/#97 instrument with its G1-loss floor published.
- The **star family is deferred** to a later subproject with Demos 02/03.
- FreeCAD `Surface::Filling` remains a per-hole fallback option (owner: other corner types have
  no stable Silk solution), but is no longer the primary component for any corner the four-ring path
  can fill.
- Register + drift-guard added so every ArachNURBS corner type is classified before the suite goes green.

Pending: #98's subagent rate-limited and errored; its fixtures + junction table still need re-firing.
The topology and recipe above are already extracted offline, so #98's content is narrowed to:
(1) generate the sketch-only example fixture in `Resources/Test_files/examples/`,
(2) assert it stays sketch-only (guard test),
(3) programmatic rebuild of four junctions via `SilkWorkflowOps`,
(4) publish the junction table against measured reference.
