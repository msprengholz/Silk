# Silk's blend machinery and how G2 could in theory be achieved

**Orientation memo. Provenance:** all source quotes pinned at commit `2eda11a`
(2026-10-16). Citations are `from code <path:line>` for code facts and `from doc
<path>` for numbers already published in the repo's research notes. Items I
derive here are marked `derived`; uncertain bibliographic detail is marked
UNCERTAIN. No new measurements were made (this memo cannot run FreeCAD).

Notation: a bicubic Bezier patch has poles `P_{i,j}` (i across the seam,
j along it), a rational one has weights `w_{i,j}`. `k_n` = normal curvature
across the seam, `tau_g` = geodesic torsion. The cross-seam parameter scale is
`lambda_j` (`lambda` = neighbour step / strip step).

---

## 1 What Silk builds

**Patches and edges.** `Patch` is a degree-3x3 Bezier surface from a 4x4 control
grid, knots `[0,0,0,0,1,1,1,1]` on both axes; edges are degree-3 rational Bezier
curves with 4 poles + 4 weights (AGENTS.md, "Surface Creation for Patch").
Weights are carried by every object (`Poles` + `Weights` properties).

**The edge blend strip (6x4).** `run_blend` (`from code SilkBlend.py:337-580`)
takes one band cell per patch (the cell between the seam and the patch's _split_
edge, default width 0.1/0.9), one 4-pole cross-band curve per along-seam
station (4 stations of the patch boundary), and builds the strip as 4 calls

```python
res = AN.blend_poly_2x4_1x6(l_rev, [1.0]*4, rc, [1.0]*4, 2.0, 2.0, 2.0, 2.0)
```
(`from code SilkBlend.py:530-536`). Each `res[0]` is a 6-pole cubic spline with
knots `[0,0,0,0,1/3,2/3,1,1,1,1]` (3 Bezier spans); the 4 results stack into the
6x4 net and `AN.CubicSurface_64` builds the surface (U = 6 across the seam,
V = 4 along it; `from code SilkBlend.py:539-555`, `ArachNURBS.py:471`).
**The shared seam is interior to the strip**: the cross-spline runs
split(A) -> seam -> split(B), so the patch-to-patch seam is replaced by one
smooth surface. Only the two strip ends (the split curves) are geometrically
tied to the patches, and only in C0 (the end poles `p0`, `p5` are the input
poles, copied unchanged).

**`blend_poly_2x4_1x6`, the actual algorithm** (`from code ArachNURBS.py:505-673`):
1. Each 4-pole input Bezier (`curve_0` = the left band, outer->shared;
   `curve_1` = the right band, shared->outer) is knot-inserted at 1/3 and 2/3
   into a 6-pole representation of the *same cubic*
   (`ArachNURBS.py:512-513, 520-521`).
2. The output poles are three from each side: `p0,p1,p2 = curve_0[0..2]`,
   `p3,p4,p5 = curve_1[3..5]` (`ArachNURBS.py:591-596`). **There is no
   averaging here**; the two half-curves are stitched.
3. The four interior poles are *rescaled*, not solved
   (`ArachNURBS.py:601-646`): with start scales `s0,s1`,
   `p1' = p0 + s0(P1-P0)`; writing `P2-P1 = l1 + h1` with `l1` along the start
   tangent and `h1` orthogonal, `p2' = p1' + s0^2 h1 + s1 (p1'-p0)`; mirrored at
   the end with `s3,s2`. The shipped call uses `(s0..s3) = (2,2,2,2)`: tangent
   legs x2, orthogonal heights x4.
4. Weights are passed through from the knot-inserted curves
   (`ArachNURBS.py:665`), but the shaping formulas use Cartesian poles only
   ("the curvature formulas above do not incorporate weights yet",
   `ArachNURBS.py:661-663`); the caller feeds `[1.0]*4`
   (`SilkBlend.py:530`), so **the shipped strip is polynomial / unit weight**.
   Rationality (arc) handling is a repair heuristic: if knot insertion loses
   rationality, endpoint weights are duplicated to restore G0 at the cost of
   tangency to the arc (`ArachNURBS.py:556-570`).

**The corner ring chain.** `CornerBlend` takes the four ring strips in any
order; `corner_inputs` canonicalizes each 24-pole grid (junction-end row moved
to V=3) (`from code SilkCorner.py:60-160`), then
`corner_grid = 4 x subgrid33_2grid64 -> control_grid66_4sub`
(`from code SilkMachinery.py:785, 892, 905`):

- `subgrid33_2grid64` takes two adjacent strips' 3-pole runs at the shared
  corner (the junction row V3 and the row one behind it, V2), extrapolates
  interior points from tangent ratios and **averages the two extrapolations**
  `p11 = (p11_u + p11_v)/2`; `p12/p21` one-sided, `p22` a parallelogram average
  (`from code SilkMachinery.py:820-890`; `ArachNURBS.py:8035-8052`). It reads
  only rows V3 and V2 - positions plus first derivative - so it can reach G1 at
  best, and not exactly. Weights cross-multiply the boundary weights:
  `w11 = w01*w10`, `w12 = w02*w10`, `w21 = w01*w20`, `w22 = w02*w20`
  (`from code ArachNURBS.py:8062-8070`) - i.e. the rational Bezier weight of a
  product patch is the product of the boundary weights.
- `control_grid66_4sub` assembles the 36 poles/weights from the four 3x3
  subgrids (`ArachNURBS.py:8077-8195`); `CubicSurface_66` builds a degree-3x3
  surface with knots `[0,0,0,0,1/3,2/3,1,1,1,1]` on **both** axes
  (`ArachNURBS.py:6299-6464`, `446-470`), set via `AN.CubicSurface_66`
  (`SilkCorner.py:283-291`).

**The star family** (`ControlGridNStar66_NSub`, `CubicNStarSurface_NStar66`,
`ArachNURBS.py:8970-9330`) generalizes the corner to N strips by progressively
extrapolated/averaged rows, a "squish" projection of the row-3 diagonal points
onto a best-fit plane, N-dependent scale heuristics (0.75 / 1 / 1.25 / 1.5 for
N = 3..6, `ArachNURBS.py:9148-9155`) and a center pole = average of all row-4
poles (`StarCenter`, `ArachNURBS.py:9258`). Continuity is unverified anywhere
(from doc `docs/research/arachnurbs-fill-type-review.md`, sec. 3.4).

---

## 2 Continuity across a seam in control-net terms

Let A have the seam at `u = 0`, B at `w = 0`, with the same curve
`P_{0,j} = Q_{0,j} = C_j` and the same along-parameterization (`v`). Cross
tangents anti-parallel with ratio `lambda(v) > 0`: `dA/du = -lambda dB/dw`.

**C0.** Boundary control row equal: `Q_{0,j} = P_{0,j}` for all j.

**G1.** The tangent plane is common iff the two cross derivatives lie in the
same plane as the seam tangent; per station (rows along the seam),
`derived`:

```
Q_{1,j} = P_{0,j} + alpha_j (P_{1,j} - P_{0,j})        alpha_j = 1/lambda_j > 0
```

i.e. the two straddling interior poles are collinear with the boundary pole
(`P_{1,j}, P_{0,j}, Q_{1,j}`), with the ratio `alpha_j` free along the seam.
In the general (sheared) case a term parallel to the seam tangent is allowed:
`Q_{1,j} = P_{0,j} + alpha_j(P_{1,j}-P_{0,j}) + beta_j * (seam tangent)_j`.
The corner solve uses exactly the first form: with the neighbour strip's rows
V3 (junction), V2 (one out), the hard G1 row is
`P_in1 = V3 - (V2 - V3)/lambda` (`from code Tests/g2_corner_solve.py:351, 333-390`).

**G2.** The second fundamental form must match at every seam point: `derived`
(the standard result; cf. Farin, sec. 6)

```
k_n^A(s) = k_n^B(s)   and   tau_g^A(s) = tau_g^B(s)     for all seam stations s
```

i.e. a **function-level match, not one scalar**. In row form, with `alpha_j` the
G1 scale, the second cross-difference must agree up to a tangential shear
`beta_j` (the shear is what the twist/geodesic-torsion condition pins down):

```
(Q_{2,j} - 2Q_{1,j} + Q_{0,j}) - alpha_j^2 (P_{2,j} - 2P_{1,j} + P_{0,j})
        = beta_j * (seam tangent at j)
```

When both sides are low-degree splines in the same parameterization, a finite
set of stations is enough to pin the whole function. The concrete Silk form
(known-answer case, `from code Tests/g2_corner_solve.py:44-66`): let the
neighbour strip's three rows walking outward from the junction be `(V3,V2,V1)`
and the corner's outward first-span Bezier poles `(b0,b1,b2)`; then

```
b0 = V3,   b1 = 2V3 - V2,   b2 = 4V3 - 4V2 + V1
```

i.e. C0 fixes `b0`, G1 fixes `b1` from two rows, and **G2 reads the third row**.
In the corner's own 6-pole B-spline form, using `b2 = (P_in1 + P_in2)/2`
(the first-span Bezier extraction E0, `from code Tests/g2_corner_solve.py:94-108`):

```
P_in1 = 2V3 - V2,     P_in2 = 6V3 - 7V2 + 2V1
```

The shipped `SubGrid33_2Grid64` reads only V3 and V2, so it structurally cannot
be G2; and because it *averages* two sides it is not even exact G1 (measured
`k_gap <= 4.080e-4` where a compatible continuation exists, from doc
`silk-corner-g2.md`, deliverable 3).

**What the instrument measures** (`from code Tests/continuity_analytic.py:115-130`):
`k_gap = |k_a - k_b|` with `k = d2P_across . n / |dP_across,perp|^2`, and
`twist_gap` from `-dN/ds . e_across`; `g1_deg` is the angle between unit
normals. The calibration is explicit: `g1_deg` is **blind** to a 4.0/mm
curvature jump, so only `k_gap` (and `twist_gap`) can establish G2 (from doc
`silk-corner-continuity-measurement.md`, sec. 1).

---

## 3 Free parameters vs constraints

**The strip.** 24 poles (72 scalars) + 24 weights (up to one global scale).
If we require C0 to the two patch split curves, the two ends of the 6-wide
direction - control columns `{P_{0,j}}` and `{P_{5,j}}` ("rows 0 and 5" of the
6x4 net) - are fixed (8 poles); the 16 interior poles
(48 scalars) are free, and today the shipped construction *fixes* all of them
via the stitch-and-scale recipe and leaves only the four `scale_*` knobs
(2.0 hardcoded in `SilkBlend.py:530`; the legacy
`ControlGrid64_2Grid44` exposed `scale_tangent_0/1`, `scale_inner_0/1`,
`autoG3`, `from code ArachNURBS.py:7271-7277`).

**The corner.** 36 poles; hard C0 (boundary rows) and hard G1 (one-in rows)
leave exactly the 4 central poles (2,2),(2,3),(3,2),(3,3) =
12 scalar DOF (`from code Tests/g2_corner_solve.py:288-303, 333-390`). The
docstring counts 3 relations x 6 stations x 4 seams = 72 relations on 36 poles
(generically over-determined); the solver samples `n_st = 9` stations per seam
by default, so the soft step is a least-squares fit (`_k_residuals`,
`from code :305-330`).

**Why a solve works.** Once C0/G1 are hard-fixed, the first derivatives (hence
the normal and the curvature normalization) are fixed, so `k_a` is exactly
linear in the 4 free poles: one Gauss-Newton step is exact
(`from code :333-395`). On a synthetic junction whose four strips are the exact
outward extensions of one smooth surface, the exact G2 continuation is known by
construction and the solve recovers it: `k_gap = 5.963e-17`, `|solved-T|_inf =
2.345e-13 mm`, versus `4.080e-4` for the shipped two-row average (from doc
`silk-corner-g2.md`, deliverable 3).

**Why compatibility is the limit.** The least-squares residual *is* the
neighbours' mutual second-order disagreement. On the demo's legacy junctions the
same solve improves the worst `k_gap` from `3.077e-2` to `7.117e-3 /mm` and
cannot close it, because the four neighbouring blends' second-order data does
not agree at the junction (from doc `silk-corner-g2.md`, deliverable 4; also
AGENTS.md, #102). Exact simultaneous G2 to all four neighbours is possible
precisely when the four neighbours are mutually compatible. For orientation:
the edge blend itself is the strong link (G1-exact, `k_gap <= 2.528e-4 /mm`),
the corner is the weak one (up to `3.1e-2 /mm` on the reference document) (from
docs `silk-corner-g2.md` deliverable 2, `silk-corner-continuity-measurement.md`
sec. 2).

---

## 4 The weights ("low weight") angle

**Two different "weights".** Silk's tagline "low weight surface modeling" means
*light-weight* models: low degree, few control points (`from code README.md:2`,
"Low Degree" section). This section is about the other weight: the rational
NURBS weight `w_{i,j}`.

**What the code does today.** Weights are *carried* by the corner chain (the
cross-products above) and by the exact instrument (`from code
Tests/silk_nurbs.py:20-24`: the net is stored in homogeneous form `(wP, w)`),
but the edge blend's shaping path is Cartesian-only and the caller passes unit
weights, so the shipped 6x4 strip has `w = 1` everywhere.

**Why weights are a curvature lever.** For a degree-n rational Bezier curve,
`derived` (quotient rule on the homogeneous form; standard):

```
kappa(0) = ((n-1)/n) * (w0 w2 / w1^2) * (h / v^2)
```

with `v = |P1-P0|` and `h` the distance of `P2` from the line `P0P1`. For a
cubic: `kappa(0) = (2/3)(w0 w2 / w1^2)(h/v^2)`. So the endpoint curvature is
scaled by `w0 w2 / w1^2`: lowering an inner weight **increases** the local
curvature (pulls the curve), raising it flattens/spreads it. Rational quadratics
(and their cubic elevations) represent conics exactly - e.g. a quarter circle
needs a middle weight `cos(45 deg) = sqrt(2)/2` in the standard rational
quadratic form `(1, sqrt(2)/2, 1)`; the code's own arc example is a non-unit
cubic weight vector `[1.0, 0.779... , 0.779... , 1.0]`
(`ArachNURBS.py:557-558`).

**DOF and nonlinearity.** A rational strip adds 24 weights (one global scale is
a gauge). With weights free, the C0/G1/curvature relations become rational
(quotient-rule) equations, i.e. **nonlinear in (poles x weights)**, unlike the
pole-only linear solve where C0/G1 make `k_a` linear. Each seam station can be
given a weight-ratio condition (`w0 w2 / w1^2` for the endpoint curvature of a
cross-curve), but changing a weight changes the whole span's shape and the
parameter speed (`|p'| ~ w1/w0`), so weight tuning is a small nonlinear problem
with fold/cusp risk as a weight approaches 0.

**Practical schemes (orientation, not measured).**

- (a) **Pole-only least squares with a curvature-matching functional** - the
  #100 solve: hard C0/G1, soft `k_gap` residual on the 12 free corner DOF;
  linear, exact on compatible neighbours, limited by their incompatibility
  otherwise. Weights stay 1.
- (b) **Weight-per-row tuning, then pole solve** - use the
  `w0 w2 / w1^2` lever to reshape the attainable curvature profile of the two
  rows behind each seam (a few ratio DOF per row), then re-run (a) with the
  weights frozen. Cheap, keeps the exact linear core, but the weight search
  itself is nonlinear and its usefulness is bounded by neighbour compatibility.
- (c) **Full nonlinear G2 solve** over poles + weights (Gauss-Newton on the
  exact rational net). Finds a genuinely rational G2 fit *when one exists*;
  cannot manufacture compatibility the neighbours lack; needs weight gauges,
  monotone parameter-speed bounds to avoid folds, and has slower/local support
  behaviour for weights than for poles.

---

## 5 What the neighbours must provide for G2 to be attainable

For full G2 across a seam the two sides must agree along the whole seam on:
C0 (the identical curve), G1 (the common tangent plane), and the second
fundamental form - equal normal curvature `k_n(s)` **and** equal geodesic
torsion `tau_g(s)` (the twist term `d2P/dudv` included). If they disagree, the
attainable limit is the least-squares residual of the row conditions; on
Silk's own demo the compatible synthetic case reads `6.0e-17 /mm` and the
legacy junction `7.1e-3 /mm` (from doc `silk-corner-g2.md`). The neighbours'
own knobs (`scale_tangent_*`, `scale_inner_*`, `autoG3` on the legacy
`ControlGrid64_2Grid44`) are the lever that could make a junction compatible,
but that was not measured (from doc `silk-corner-g2.md`, deliverable 5).

Measurement caveats to carry with any G2 claim: no test asserts a continuity
label (`test_no_continuity_threshold_in_suite`, AGENTS.md); `k_gap` is
across-normal curvature only - necessary, not sufficient, for full G2;
`twist_gap` is orientation-suspect on reversed seams (the geodesic torsion
enters with a sign flip, so a smooth seam can read `twist_gap ~ 2|tau|`; a seam
with `k_gap 2.1e-6` reads `twist_gap 5.3e-3`) - only non-reversed values count
until the metric is made reversal-invariant (#101, AGENTS.md and
`silk-corner-g2.md` "What could not be established"). FreeCAD's
`Surface::Filling` at `BoundaryOrder = 2` is **not** the route: `k_gap
1.665e-1` versus order 1's `8.249e-2` on the same feed (from doc
`silk-corner-g2.md`, deliverable 1).

---

## 6 References

- G. Farin, *Curves and Surfaces for CAGD: A Practical Guide* - G0/G1/G2
  conditions for Bezier curves and patches, alpha/beta constraints. (Standard;
  exact edition/pages UNCERTAIN.)
- L. Piegl & W. Tiller, *The NURBS Book* - knot insertion, rational evaluation,
  basis derivatives; the repo's exact instrument follows its A2.3/A2.4/A4.4
  (from code `Tests/silk_nurbs.py:44-56`). (Standard; page numbers UNCERTAIN.)
- W. Degen - explicit G1/G2 continuity conditions and blending for adjacent
  Bezier patches. (Author/topic standard; exact title/venue/year UNCERTAIN.)
- J. Hoschek & D. Lasser, *Fundamentals of Computer Aided Geometric Design* -
  geometric continuity and rational form. (UNCERTAIN on specifics.)

*Memo scope: orientation only. The memo deliberately does not attempt the full
nonlinear rational G2 derivation; the repo's own measured evidence for what a
solve can and cannot reach is `docs/research/silk-corner-g2.md`.*
