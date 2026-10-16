# The Silk corner, measured with a calibrated instrument (ticket #97)

**Question.** The owner says the original Silk corner
(`Resources/Demo_files/Silk_Demo_01.FCStd`) "yields G2 curvature"; upstream's
own code says the G1-ness is unproven (`ArachNURBS.py:7969`). No number for
it survives, and the numbers on the map (`2.08°` / `0.48°` / raw-invalid)
have a provenance defect. This finding calibrates a continuity instrument,
points it at the reference corner, and restates the record.

**Answer.** The reference corner is **C0 exactly** (boundary gap
≤ 5.2e-13 mm) and **tangent-plane continuous to ≤ 0.48°** across the
corner-to-blend seams — G1 by the repo's own 0.5° label, though the normal
gap is a real, non-zero quantity. It is **not G2**: the across-seam normal
curvature gap is up to **3.1e-2 /mm**, i.e. ~600× the repo's `k_abs_tol`
(5e-5). The corner does **not** deliver G2 curvature at its seams to the
surrounding blends. One of the sixteen seams (the `CubicSurface_66003`
v0 ↔ `CubicSurface_64008` v0 hard-corner side) is exactly G2.

## Instruments

Two instruments, deliberately independent:

| | `Tests/g2_oracle.py` (sampled) | `Tests/continuity_analytic.py` + `Tests/silk_nurbs.py` (exact) |
|---|---|---|
| method | samples the seam, finite differences, `solve_uv` correspondence | evaluates the exact control net (Piegl & Tiller A2.4 basis derivatives, A4.4 rational quotient) |
| weights | reads whatever `Part.BSplineSurface` holds | carries the homogeneous net, so rational surfaces are exact |
| C0 | position gap from evaluation | evaluation **plus** `c0_controlnet`: a combinatorial comparison of homogeneous boundary control points, no evaluation at all |
| claims | `c0`, `g1_deg` (tangent plane), `k_gap` (across normal curvature), `twist_gap` (geodesic torsion) | same four, exactly |

`Tests/continuity_calibration.py` is the soundness harness; its raw output is
below. **No test asserts a continuity label for any real geometry**
(`test_no_continuity_threshold_in_suite`); the suite only checks the ruler.

## 1. Instrument soundness (numbers)

Raw output: `Tests/continuity_calibration.main()` in a live FreeCAD GUI 1.1.3
/ OCCT 7.9. Reproduce with
`python3 Tests/run_all.py continuity_instrument` (calibration-only suite) or
`Tests/continuity_calibration.py` in a GUI console.

**`solve_uv` (the sampled instrument's parameter solver).** On an exact
bicubic patch, solving for points taken at known `(u, v)`:

* max position residual **4.460e-13 mm**; max `|du|` 2.776e-17, max `|dv|` 4.460e-13.
* on a plane (non-injective parameters) residual 1.027e-12 mm.
* **Claim supported:** the solver recovers parameters to machine precision on
  these surfaces, so a sampled `c0` above ~1e-12 mm is geometry, not solver noise.

**Error floor of every quantity.** Both instruments on the smooth seam of one
paraboloid split in two (`z = u²`, C∞, truth = 0 in every slot):

| quantity | sampled floor | analytic floor |
|---|---|---|
| `c0` | 0.000e+00 mm | 0.000e+00 mm |
| `g1_deg` | 1.146e-03 ° | 0.000e+00 ° |
| `k_gap` | 0.000e+00 /mm | 0.000e+00 /mm |
| `twist_gap` | 0.000e+00 /mm | 0.000e+00 /mm |

The sampled normal-gap floor is ~1e-3° (finite-difference noise); the analytic
floor is exact. On the demo's own control nets the analytic normal floor rises
to ~1.5e-6° (rational evaluation on rounded poles) — still ~300× below the
smallest signal measured there. **Claim supported:** no number below these is
a measurement.

**Known G1 angle.** Two planes at a dihedral θ: sampled and analytic both
report 5.0000° and 20.0000°. **Claim supported:** `g1_deg` measures the
tangent-plane gap it names.

**Known curvature jump (the G2 calibration).** Two parabolic cylinders meeting
tangent-plane continuous with normal curvatures 2a and 2b:

* truth `k_gap` = 4.0000 /mm; sampled `k_gap` = 4.0000; analytic `k_gap` = 4.0000.
* at the same seam, sampled `g1_deg` = 0.0023°, analytic `g1_deg` = 0.0000°.
* **Claim supported, and the point of the ticket:** `g1_deg` is **blind** to
  the curvature jump — a near-zero `g1_deg` does **not** establish G2. Only
  `k_gap` (and `twist_gap`) can. This is why any G2 claim has to be read off
  the curvature metric, which is what the calibration here validates.

**Independent cross-check (shares neither instrument's basis or solver).**
Reflected 3-D across-seam position profile: for a G1 seam the deviation grows
like δ², for a C0 seam like δ¹.

* G1 pair (parabola, curvature jump): slope **2.0018** (expect 2).
* C0 pair (planes, 20° dihedral): slope **1.0000** (expect 1).
* OCCT `distToShape` from A's seam points to B's face on the G1 pair:
  **1.388e-17 mm**. **Claim supported:** an independent method recovers the
  same continuity order.

## 2. The reference corner (`Silk_Demo_01.FCStd`)

Read-only; the demo document is opened, never recomputed or saved.
`Tests/g2_demo_corner.py` (MANUAL) pairs each `CubicSurface_66` corner with
each neighbouring `CubicSurface_64` blend by matching boundary control nets,
then reports both instruments at n = 41 stations. Raw output:
`/tmp/opencode/demo_corner_report.json` (16 seams). 4 junctions
(`ControlGrid66_4Sub`, each with one `ControlGrid64_3_Grid44` hard-corner
subgrid), 4 seams each.

| corner | blend | edge | rev | c0 net (mm) | c0 exact (mm) | g1 exact (°) | g1 sampled (°) | k_gap exact (/mm) |
|---|---|---|---|---|---|---|---|---|
| CubicSurface_66 | CubicSurface_64 | u0 | | 8.06e-15 | 8.06e-15 | 0.0000 | 0.0003 | 1.568e-03 |
| CubicSurface_66 | CubicSurface_64010 | v0 | | 7.46e-14 | 5.83e-14 | 0.4757 | 0.4755 | 7.117e-03 |
| CubicSurface_66 | CubicSurface_64003 | u1 | y | 2.93e-14 | 4.71e-14 | 0.0000 | 0.0002 | 1.307e-02 |
| CubicSurface_66 | CubicSurface_64011 | v1 | | 4.32e-14 | 5.17e-14 | 0.1808 | 0.1806 | 1.111e-02 |
| CubicSurface_66001 | CubicSurface_64009 | u0 | y | 3.66e-14 | 2.96e-14 | 0.0000 | 0.0003 | 1.407e-03 |
| CubicSurface_66001 | CubicSurface_64012 | v0 | | 6.04e-14 | 6.04e-14 | 0.0723 | 0.0725 | 3.224e-03 |
| CubicSurface_66001 | CubicSurface_64004 | u1 | y | 1.46e-14 | 2.95e-14 | 0.0000 | 0.0001 | 2.782e-03 |
| CubicSurface_66001 | CubicSurface_64010 | v1 | | 3.04e-14 | 3.03e-14 | 0.2041 | 0.2040 | 3.077e-02 |
| CubicSurface_66002 | CubicSurface_64011 | u0 | y | 1.58e-13 | 1.09e-13 | 0.0591 | 0.0590 | 6.242e-03 |
| CubicSurface_66002 | CubicSurface_64013 | v0 | | 5.73e-14 | 6.36e-14 | 0.0000 | 0.0005 | 6.402e-03 |
| CubicSurface_66002 | CubicSurface_64014 | u1 | y | 8.67e-14 | 8.80e-14 | 0.0994 | 0.0996 | 3.273e-03 |
| CubicSurface_66002 | CubicSurface_64007 | v1 | | 5.15e-13 | 5.15e-13 | 0.3515 | 0.3516 | 1.950e-02 |
| CubicSurface_66003 | CubicSurface_64012 | u0 | | 5.05e-14 | 3.55e-14 | 0.0230 | 0.0231 | 1.998e-03 |
| CubicSurface_66003 | CubicSurface_64008 | v0 | y | 5.33e-15 | 5.73e-14 | 0.0000 | 0.0000 | 0.000e+00 |
| CubicSurface_66003 | CubicSurface_64015 | u1 | y | 1.03e-13 | 7.62e-14 | 0.2792 | 0.2790 | 2.905e-03 |
| CubicSurface_66003 | CubicSurface_64013 | v1 | | 2.78e-13 | 2.78e-13 | 0.0000 | 0.0002 | 2.107e-02 |

Readings:

* **C0 — exact.** `c0_controlnet` (no evaluation, homogeneous boundary control
  points) is ≤ 5.15e-13 mm at every seam; the exact evaluator agrees to the
  same order, and the sampled oracle to ~1e-13 mm. The corner and each blend
  share the identical rational boundary curve.
* **G1 — up to 0.476°.** Nine seams are within 0.1°; four are 0.18–0.48°. The
  worst (`CubicSurface_66` ↔ `CubicSurface_64010`) is 0.4757° (exact) vs
  0.4755° (sampled). That is below the repo's 0.5° `g1_deg_tol`, so the repo's
  own `classify` calls these seams **G1**, but the tangent-plane gap is a real,
  non-zero quantity, not zero-to-rounding.
* **G2 — no.** The across-seam normal-curvature gap is 1.4e-3 … 3.1e-2 /mm
  (max at `CubicSurface_66001` ↔ `CubicSurface_64010`), against the repo's
  `k_abs_tol` = 5e-5. Geodesic-torsion gaps reach 4.1e-2 /mm. The lone
  exception is the `CubicSurface_66003` v0 ↔ `CubicSurface_64008` v0 seam,
  where both instruments read exactly 0 (the two surfaces agree there to all
  reported orders).

**Verdict, and on what authority.** Within the calibrated tolerance the
corner is **C0 exact and G1 (≤0.5°), not G2**. Authority: exact control-net
derivatives, in agreement with a finite-difference oracle that was itself
calibrated on closed-form G1 and curvature-jump cases, with an independent
reflected-3D cross-check recovering the same orders. The negative G2 claim
rests on `k_gap`, the one metric shown able to see a known 4.0 /mm curvature
jump; the max gap here is 0.031 /mm, ~600× the tolerance and the same order as
the corner's own curvature at ~50 mm scale.

**What this does not say.** `k_gap` is a single-direction (across-seam) normal
curvature comparison — necessary but not sufficient for full G2 (which needs
the whole second fundamental form, hence also `twist_gap`, to match). Here
both metrics are large, so "not G2" is sound; a small `k_gap` alone would not
have proven G2. The 4-junction interior needs no seam test: each
`CubicSurface_66` is one bicubic B-spline surface, analytic (C∞) inside.

## 3. Correcting the record

* **Yellow `CornerBlend` — `2.1e-14 mm` / `2.08°`: restated, and the
  attribution is wrong.** The number is *reproducible*, but from the **Phase A
  curvature oracle** (`Tests/g2_oracle.measure_seam` via
  `Tests/g2_corner_measurement.measure_corner_blend`), **not** from
  `Tests/g2_corner_fill_probe.py` (which contains no `CornerBlend` code). The
  re-run (n = 41, raw `/tmp/opencode/corner_blend_report.json`) gives, for the
  four true boundary seams:

  | seam | c0 (mm) | g1 sampled (°) | g1 exact (°) | k_gap exact (/mm) |
  |---|---|---|---|---|
  | CB.v0 ↔ B12.v1 | 0.0 | 1.0020 | 1.0021 | 9.318e-04 |
  | CB.u1 ↔ B24.v0 | 0.0 | 1.8068 | 1.8070 | 2.757e-03 |
  | CB.v1 ↔ B43.v1 | 2.66e-14 | 2.0933 | 2.0935 | 3.064e-03 |
  | CB.u0 ↔ B31.v1 | 2.56e-14 | 1.3122 | 1.3123 | 1.925e-03 |

  So the recorded pair is real: residual ~2.6e-14 mm, normal gap up to 2.09°
  (the recorded 2.08° is that number to rounding). **Corrected statement:**
  the `CornerBlend` boundary is **C0 (exact) with a normal gap up to ~2.1°** —
  i.e. **C0, not G1**, by the repo's own `classify` (g1_deg_tol = 0.5). The
  map attributed the pair to the wrong file; the numbers themselves did not
  come from nowhere.

* **Green strip-fed `Surface::Filling` — `0.164–0.483°`: not re-measured
  here.** It is a *different object* (a `Surface::Filling` face on the
  blended feed, Phase B normal-gap probe `Tests/g2_corner_fill_probe.py`), not
  the `CornerBlend` and not the demo corner. It stays attributable and
  reproducible-in-principle. One thing this ticket *does* confirm: the probe
  shares `solve_uv` with the calibration here, whose floor is 4.5e-13 mm, so
  the recorded 4.3e-3 mm boundary residual is a real fill approximation, not
  solver noise.

* **Raw-patch invalid feed: not re-measured here.** Same Phase B probe;
  attributable, reproducible-in-principle.

* **`2.08°` / `2.1e-14` provenance defect: confirmed and now repaired.**
  The strings appear in no doc, source, commit or log (only the map). The
  instrument that can produce them is `Tests/g2_corner_measurement.py`, and a
  raw output is now preserved for them.

## What could not be established

* The green (0.164–0.483°) and raw-invalid Phase B numbers were not
  independently re-run here — the Phase B probe is GUI-only, slow, and builds
  `Surface::Filling` carriers; it is out of this ticket's corner focus. They
  remain attributable but with only the original table as raw output.
* `twist_gap` history: `classify` never reads it (unchanged). No G2 label in
  this finding uses it; it is reported as an extra, un-calibrated-in-label
  quantity.
* The demo was measured at n = 41 stations; a finer sweep could move the
  0.4757° worst-case marginally, but it is bounded by the exact evaluator, not
  by sampling.

## Method / limits

* Instruments: `Tests/silk_nurbs.py` (exact net), `Tests/continuity_analytic.py`
  (seam report), `Tests/continuity_calibration.py` (soundness),
  `Tests/test_continuity_instrument.py` (calibration-only suite tests).
* Manual measurement: `Tests/g2_demo_corner.py` (demo), and the
  `measure_corner_blend` recheck in `Tests/g2_corner_measurement.py`. Both
  carry `MANUAL = True` and are asserted reachable (import + `main`) by the
  suite; neither runs geometry in the suite.
* The demo measurement is read-only. It was taken in the live GUI because
  `ArachNURBS.py` imports `FreeCAD.Gui`; the analytic layer itself is a leaf
  module and runs under `freecadcmd`.
* Ground truth for every claim above is either a closed-form surface or an
  independent OCCT/reflected-3D check — no number here is quoted from a label.
