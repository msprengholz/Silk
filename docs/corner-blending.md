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
| sets the two setbacks **asymmetrically** (its own numbers: 0.25 and 0.125) so one fillet is large and the other small | the setback is already the user's, per patch and per end, in the panel. Asymmetry **reaches the corner's shape**: curvature spread 1.04 → 2.29 — but see the ruling below: that is **not** the two-zone look |
| the small fillet **rolls around** the large one | **not achieved** — the owner's own look at the render (2026-10-21) is the ruling: *"the patch has weirdly rounded edges. I would not consider this to be a rolling corner"* |
| **sections** each blend along its seam, backfills the rest with the original surface, **trims** the 66 back, and **inserts a separate fill** | one 6×6 surface spans the whole corner, and the band it consumes is **not** re-created. The segmented recipe is **opt-in, not built**: #119, staged, and limited to tools Silk or FreeCAD already provide |

## Is our corner a rolling fillet? The **ruled** answer: **no**

**The owner's ruling (2026-10-21), on the rendered corner:** *"the patch has weirdly
rounded edges. I would not consider this to be a rolling corner like described by
the silk maintainner. … I only see one surface, but it should be two!"*

That is the ground truth for this question, and it **overturns the reading #118
gave**. What #118 measured is real and still stands — the corner's curvature
spread moves **1.04 → 2.29** and it develops a **saddle** (`k1 = +1.70`,
`k2 = −2.46 /mm`) while every seam stays at the exact `k_gap` floor. But the
*interpretation* was wrong: a saddle is a **twist**, and the author's rolling
corner is **two convex fillets of different size**. The measurement says the
asymmetry is absorbed; it does **not** say the result is a rolling fillet, and
the rendered surface says it is not.

**Why ours is one surface and his is two — the step comparison.** The maintainer's
own class help (`ControlGrid66_4Sub.py`, quoted in
`docs/research/silk-corner-type-taxonomy.md`) is explicit:

> "three surfaces meeting to form a hard corner (like a cube corner). **Here more
> sectioning of the original surfaces is required.** You end up with **2 small
> blends, and one larger blend.** use `ControlGrid64_3_1Grid44` opposite the large
> blend to create the fourth blend. Now you have 4 blends across 3 surfaces, and
> can make the 4 SubGrids."

| step | the maintainer | Silk today | same? |
|---|---|---|---|
| 1. cut the base surface | the base `CubicSurface_44` is **sectioned** into cells (`ControlGrid44_2EdgeSegments` = a *2-edge rectangular cut*; `ControlGrid44_EdgeSegment` = a *single strip cut*) | the patch is divided into subgrid cells and the **band** is the cut — but the **whole band** is consumed | partly |
| 2. **preserve what is not blended** | the un-blended remainder is **re-created as its own surface** — the demo's `*_Segment_surfaces` groups hold 11 extra `CubicSurface_44` whose tooltip is *"re-create the portions of the original surface that are to be preserved and not blended"* | **nothing is preserved.** The band is consumed and the patch's own surface is hidden under it (auto-hide), never re-created | **no** |
| 3. "2 small blends, and one larger blend" | the three ring members differ in **how far they run along the seam** — small = near the corner, large = continuing past it | the three ring members differ in **band depth** (the setback) | **no — the wrong parameter** |
| 4. the triangular 4th member | `ControlGrid64_3_1Grid44` opposite the large blend | ported, faithful (pole parity 0.000e+00) | yes |
| 5. 4 subgrids → one surface | `ControlGrid66_4Sub` → `CubicSurface_66` | the same chain, our 6×6 | yes |

**The two divergences are the whole answer.** Step 2 is missing, so the corner's
neighbours are the blends themselves and the 66's outline is the **band edge** —
one closed loop at a roughly constant distance from the junction, which is
exactly the "weirdly rounded edges": a rounded triangle with rounded corners, a
**blob**, not a fillet. Step 3's "small" and "large" are about **extent along the
seam**, and we varied **depth** instead — the same numbers, a different
parameter. So the video's 0.25 / 0.125 are read as *where the segment ends along
the seam*, not as *how deep the band is*.

**Consequence.** #119 is **not** a refinement of the look — it **is** the look.
Its first stage (section each blend along its seam and re-create the preserved
remainder) is what produces the second surface and the seam where the small
fillet rolls into the large one. Until that is built, the honest sentence is:

> the corner **responds directionally** to asymmetric setbacks — measured, seam
> continuity untouched — and it is **one surface with a rounded outline**, not the
> maintainer's two-zone rolling fillet. The two-zone look needs the segmented
> recipe (#119).

## The rolling corner, built (opt-in) — #119

The segmented recipe is **built** as an opt-in
(`SilkWorkflowOps.create_split_blend` /
`create_rolling_triangle` / `create_rolling_corner`; the full write-up
and the measurements are `docs/research/silk-rolling-corner.md`):

* a blend can be **split at a rolling leader** — a position on the
  **seam curve**, measured from the junction corner — into two real
  surfaces that meet exactly at the cut (the base surface is *segmented*
  there, so the cut is a knot line of both nets: 5.6e-17 mm measured);
* the corner can carry a small **triangular surface** of its own, built
  by FreeCAD's own `Surface::Filling` over the two corner-side seam
  pieces and the chord across the corner;
* the default path is **byte-identical** when the opt-in is not used
  (`Leader` = 0 → the same 24 poles, deviation 0.00e+00).

**What the measurement says.** On the cube-corner fixture the leader
does **not** change the corner's own shape: the junction's curvature
spread is 1.037 with the leader and 1.037 without it (identical to
thirteen digits). The reason is in the shipped corner chain and is
written down in the research note: the subgrid extrapolation is
**scale-invariant along the seam** (the along-seam step cancels against
the ratio that scales it), and the corner's boundary — the member's
junction row — sits at the band's own corner end, which the split does
not move. So the rolling has to come from the **boundary** (the
maintainer's ring members are cuts of the base surfaces, so their
junction rows sit at the cut), which is the step this build does not
yet close.

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
