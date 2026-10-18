# Corner blending

What Silk builds where three or four surfaces meet, what the maintainer's
rolling-blend video does differently, and which parts are measured, which are
judgement, and which are not claimed. Evidence lives in `docs/research/` (each
number below names its file) and `docs/adr/0005-corner-blending.md`.

## Vocabulary

Two people using *rolling* for different things is how a demo slide becomes a
lie, so the terms first. The words marked **(author)** are his; the rest are ours.

| term | meaning |
|---|---|
| **seam** | the shared boundary between two adjacent patches |
| **band** | the row of subgrid cells on a patch adjacent to its seam — what a blend consumes |
| **setback** / **band width** | how far back from the seam the blend reaches. The same thing: the panel's per-patch `Band A` / `Band B` editors (`USplit1/2`, `VSplit1/2`). The user owns the value |
| **corner cell** | the subgrid cell where two bands meet at a patch corner; reserved for the corner, never part of a band |
| **corner blend** | a `CornerBlend` object: the surface closing the junction of 3 or 4 patches |
| **corner fill** | FreeCAD's `Surface::Filling` over a boundary wire — the `Silk_CornerFill` command. A different object from a corner blend |
| **triangular member** | `ControlGrid64_3_1Grid44`: the degenerate 6×4 grid with a *collapsed row* that fakes a fourth blend at a 3-valent corner. **(author)** calls it a *"scaffolding piece"* with a *"spiderweb"* grid. `docs/research/silk-corner-type-taxonomy.md` |
| **rolling** **(author)** | *"the separation of the blending into two zones with different sizes — a large fillet in one direction and a small fillet in another"*, where *"this small fillet rolls around this big one"*. **Two convex fillets of different radii.** An effect you judge by eye |
| **mushing** **(author)** | his opposite: blending that averages into *"one thing"*, i.e. one uniform round |
| **anisotropy** | a measured property: the corner's curvature differs by direction (`k_max / k_min` away from 1) |
| **saddle** | a measured property: negative Gaussian curvature — the surface bends opposite ways in the two directions |

**Rolling is reserved for the author's two-zone effect.** Our measured result is
*anisotropy* (and past a threshold a *saddle*); see the honest answer below.

## Supported valences

| valence | what Silk ships | how | measured continuity |
|---|---|---|---|
| **3** (hard corner) | one `CornerBlend` | 3 strip blends + the invisible triangular member → 4 subgrids → one 6×6 surface | C0 exact, **G1 ≤ 0.48°**, not G2 (`k_gap` ≤ 3.1e-2 /mm on the demo). The member's collapsed row gives a *degenerate-boundary* normal on the two seams that reach it |
| **4** | one `CornerBlend` | 4 strip blends → 4 subgrids → one 6×6 surface | G1 ≤ 2.0e-4°, `k_gap` ≤ 1.0e-2 /mm |
| **5 or more** | **nothing** | `CornerBlend` refuses by name and creates nothing | — |

**For five or more surfaces, use FreeCAD's `Surface::Filling` directly** — the
`Silk_CornerFill` command — even where it is not pretty. Upstream's own answer is
the N-star family, whose author measures it as barely usable; Silk does not
expose it (`docs/research/silk-corner-type-taxonomy.md`).

## The video, step by step, against what we ship

| the video does | Silk today |
|---|---|
| sets the two setbacks **asymmetrically** (its own numbers: 0.25 and 0.125) so one fillet is large and the other small | the setback is already the user's, per patch and per end, in the panel. Asymmetry **reaches the corner's shape**: curvature spread 1.04 → 2.29 |
| the small fillet **rolls around** the large one | **not claimed** — see below |
| **segments** each blend along its seam, backfills the rest with the original surface, **trims** the 66 back, and **inserts a separate fill** | one 6×6 surface spans the whole corner. The segmented recipe is **opt-in, not built**: #119, staged, and limited to tools Silk or FreeCAD already provide |

## Is our corner a rolling fillet? The honest answer

Measured on the cube-corner fixture with the video's own asymmetric setbacks
(`Tests/g2_corner_roll_measure.py`, `docs/research/silk-corner-roll.md`):

- the corner's own curvature spread moves **1.04 → 2.29** (`k_max/k_min`),
  `k_min` dropping 8.58 → 2.42 /mm — ≥ 4 orders above the instrument floor;
- near the junction it goes **saddle** (`k1 = +1.70`, `k2 = −2.46 /mm`, negative
  Gaussian curvature), which the symmetric corner does not;
- **every seam stays at the exact `k_gap` floor** (≤ 6.8e-13 /mm).

So the asymmetry is absorbed into the corner's shape instead of averaging out —
which is *necessary* for a rolling look. It is **not sufficient to claim one**:
the author's rolling corner is **two convex fillets**, and a saddle is a twist,
not two fillets. **Nobody has looked at it.** Whether the screen shows two zones
or a twisted corner is a visual judgement on the demo shape (zebra + curvature
view, setbacks 0.25 / 0.125) — until that is done, the presentation says:

> the corner **responds directionally** to asymmetric setbacks — measured, seam
> continuity untouched — and the **two-zone look needs the segmented recipe**.

## The Y-split

An alternative for the 3-valent junction: build it as **three four-sided patches
meeting at a computed apex** instead of one 6×6 with a degenerate member. Upstream
has exactly this code — the star family at N=3 (`ControlGridNStar66_NSub` →
`CubicNStarSurface_NStar66`) — and the author's own verdict on the star family is
negative. **We have never measured it, and it is not planned** (map #1; #92
closed, #104 closed with its findings kept).

## Not in this page

G2 at a corner — the control-net solve, the weight tuning, the feasibility wall.
Measured, documented (`docs/research/silk-corner-g2.md`,
`silk-g2-feasibility.md`, `silk-g2-math-overview.md`) and **deliberately not
built**: it is maths neither FreeCAD nor Silk already provides.
