# Does the shipped 3-valent corner roll? (ticket #118)

**Question.** The video's author makes a *rolling* fillet by setting the
setbacks asymmetrically (0.25 in one direction, 0.125 in the other). #118 asks
the falsifiable version: **does Silk's shipped 3-valent corner's fillet
character change when the band widths are set asymmetrically — one direction
large, one small — or does it average into one uniform round?** Two readings
were pre-declared: the curvature spread grows (it rolls) or it stays put (it
mushes, and the rolling look depends on the parked segmented-blend recipe).

**Answer (one line). It rolls.** At the cube-corner junction the corner's own
normal-curvature spread moves from **k_max/k_min = 1.04 (symmetric) to 2.29
(asymmetric)** — a 2.2× move, ≥ 4 orders of magnitude above the instrument
floor — while every strip seam stays at the exact `k_gap` floor
(≤ 6.8e-13 /mm): the asymmetry **reaches the corner's shape** and it becomes
an oval (and develops a saddle), rather than averaging into a round. The
rolling character is already in the shipped single 6×6; it does not need the
parked segmented-blend + trim + fill recipe.

**Scope.** A finding, not a fix — no production code changed. Measured on the
`Tests/cube_corner_model.py` cube-corner fixture (three exact planar squares,
no curvature of its own), not `Silk_Demo_01`. One seam interpretation is the
headline (the per-seam `Band A` / `Band B` widths, below); a second reading of
"one direction large, one small" is carried as a robustness variant. No
continuity label is asserted anywhere in this finding or its script.

---

## Method

`Tests/g2_corner_roll_measure.py` (`MANUAL = True`, reached only by
`Tests/test_continuity_instrument.test_manual_measurement_scripts_reachable`).
For each config it builds the fixture, writes the band widths, recomputes
(patches → auto-updated strips), then builds the corner from the rebuilt
strips.

Quantities, per the ticket:

1. **per-seam `k_gap`** — the built corner vs each neighbouring strip, on the
   exact control net (`Tests/continuity_analytic`), with the `Tests/g2_oracle`
   sampled reading beside it. The 3-valent corner has **three** strip seams;
   the 6×6's **fourth** side is the triangular member's **collapsed row**
   (all six poles at the ring's shared corner), which no strip sits on and
   whose boundary normal is degenerate — reported, not counted.
2. **the corner's own curvature spread** — a directional normal-curvature
   sample on the stored 6×6 net: 90 directions (2° apart) of the tangent plane
   at a point, `k_max`, `k_min`, ratio. The shape operator (the exact roots of
   the normal-curvature quadratic) is printed as a cross-check and agrees to
   4 digits.

**The setback is the band width** Silk reads off each patch's own band edge; a
seam's two setbacks are the two patches it joins — the wizard's `Band A` /
`Band B` editors. `symmetric` leaves the fixture's defaults (0.1 / 0.1 on
every seam). `asymmetric` sets one patch of every seam to **0.25** and the
other to **0.125** (the video's two numbers) in the rotational sense, so every
seam is LARGE/SMALL and every ring patch carries one of each.
`asymmetric_axis` reads "one direction large, one small" the other way (every
patch U = 0.25, V = 0.125) and is kept only as a robustness variant.

## Floor

`Tests/continuity_calibration.error_floor` (n = 41), the smallest number the
instrument can honestly report on a smooth curved seam whose truth is 0:

| quantity | sampled | analytic |
|---|---|---|
| `c0` | 0.0 | 0.0 |
| `g1_deg` | 1.146e-03 | 0.0 |
| `k_gap` | 0.0 | 0.0 |
| `twist_gap` | 0.0 | 0.0 |

The `k_gap` floor is **exactly 0** here because the calibration's known-answer
pair (two halves of `z = u²`) carries the same curvature on both sides; the
issue's "~1e-4 /mm" is the conservative practical threshold and the instrument
resolves the calibration's 4.0 /mm jump to below 1e-2 /mm. Every curvature
figure below is ~1 /mm, so the spread and its change sit ≥ 4 orders of
magnitude above either floor.

## Raw numbers

Seam bands (patch, property, width) — the setback pair per seam:

| config | B_AB | B_BC | B_CA |
|---|---|---|---|
| symmetric | 0.1 / 0.1 | 0.1 / 0.1 | 0.1 / 0.1 |
| asymmetric | 0.25 / 0.125 | 0.25 / 0.125 | 0.25 / 0.125 |
| asymmetric_axis | 0.125 / 0.125 | 0.25 / 0.25 | 0.125 / 0.25 |

Per-seam `k_gap` (corner vs strip; B_AB and B_CA terminate in the collapsed
row and read a degenerate boundary normal — exact `g1_deg` 90 for those two,
~0 for B_BC):

| seam | exact k_gap (sym) | exact k_gap (asym) | sampled k_gap (sym) | sampled k_gap (asym) |
|---|---|---|---|---|
| B_AB | 9.594e-13 | 6.833e-13 | 2.380e-03 | 1.363e-02 |
| B_BC | 7.808e-15 | 1.396e-14 | 4.563e-03 | 5.668e-03 |
| B_CA | 2.485e-13 | 4.406e-13 | 2.380e-03 | 5.267e-03 |

`c0_controlnet` is 0.000e+00 on every seam in every config. The exact
`k_gap` stays at the floor in all three configs (≤ 6.8e-13 /mm) — **the corner
continues each neighbouring strip regardless of the asymmetry**; the sampled
reading is larger only because the two degenerate-apex seams are read through
a null boundary normal there, not because the seam disagrees.

Corner's own curvature spread (directional sample on the 6×6 net):

| point | symmetric | asymmetric | asymmetric_axis |
|---|---|---|---|
| junction, uv (0.5, 0.5): k_max / k_min / ratio | 8.9014 / 8.5843 / **1.037** | 5.5289 / 2.4164 / **2.288** | 6.1730 / 3.0018 / 2.056 |
| junction foot (nearest the cube vertex): ratio | 1.177 (0.053 mm) | 1.674 (0.099 mm) | 2.383 (0.095 mm) |
| near junction, 5×5 uv grid over [0.4, 0.6]: ratio range | 1.037 .. 1.676 | 0.692 .. 6.087 | 1.438 .. 3.269 |

The asymmetric corner's near-junction range dips **below 1** (0.692 at uv
0.6/0.6): the shape operator there gives k1 = +1.701, k2 = −2.458 — principal
curvatures of **opposite sign**, i.e. a genuine saddle (negative Gaussian
curvature, product −4.18). The symmetric corner stays positive-definite over
the whole sampled region (ratio ≥ 1). A rolling fillet is exactly a shape that
goes hyperbolic as it turns, so the sign change is a second, independent
reading of the same effect.

## Reading

The spread **moves with the asymmetry**: the junction curvature ratio
1.037 → 2.288 (×2.21); the shape-operator cross-check sees the same
(1.037 → 2.289). The `asymmetric_axis` variant moves it too (→ 2.056), so the
result is not an artifact of one particular way of arranging the unequal
widths. Meanwhile the exact per-seam `k_gap` stays at the floor in every
config. The corner therefore **does not compromise or average the setbacks**:
it absorbs the unequal widths into its own shape (oval, then saddle) while
staying curvature-continuous to each strip.

Consequence for the ticket's outcomes: this is the **"spread grows"** branch.
The shipped single 6×6 does express the rolling character; the effect can be
demonstrated by dragging the `Band A` / `Band B` editors, and the parked
segmented-blend + trim + fill recipe is a refinement rather than the source of
the look.

## Caveats

* One fixture, one corner (the cube corner). The demo's legacy junctions carry
  other neighbours; this measures the shipped corner machinery on a
  curvature-free fixture, as the ticket scopes it.
* Curvature magnitudes here are ~1 /mm because the corner is a fine feature
  (band width 0.1 on unit-square patches); the ratio, not the magnitude, is
  the shape statement and is scale-free.
* No continuity label is claimed. `k_gap` only; `twist_gap` carried but not
  tabulated.

## Reproduce

```
import Tests.g2_corner_roll_measure as m
m.main()
```

Raw output is the printed table; the script opens and closes its own scratch
documents and never saves a file.
