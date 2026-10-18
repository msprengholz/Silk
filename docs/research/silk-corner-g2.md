# What does it take to reach G2 at the 4-patch corner? (ticket #100)

**Question.** #97 established that the reference corner
(`Resources/Demo_files/Silk_Demo_01.FCStd`) is C0-exact and G1 (≤ 0.48°) but
**not G2** (`k_gap` to 3.1e-2 /mm). The owner asked: *is the underlying maths
the limit? check if the FreeCAD surface tool can achieve G2.* Five
deliverables, each measured with the #97 calibrated instrument and its error
floor.

**Answers, one line each.**

1. **FreeCAD `Surface::Filling` at `BoundaryOrder = 2` is not G2** — `k_gap`
   1.665e-1 /mm on the strip feed. Worse: order 2 does **not** beat order 1 in
   `k_gap` (**1.665e-1 vs 8.249e-2**) or in `g1_deg` (**1.10° vs 0.155°**), so
   the order knob is not doing what its name says here.
2. **Silk's edge blend is the strong link** — G1-exact (`g1 = 0.0000°`) with
   `k_gap` ≤ **2.528e-4 /mm** (13 of 14 seams ≤ 1.419e-4, three exactly 0).
   That is ~120× below the corner's 3.1e-2.
3. **The maths is not the limit** — on a synthetic junction whose exact G2
   continuation is known, a control-net **solve** recovers it exactly
   (`k_gap = 5.963e-17`, `|solved − T|_inf = 2.345e-13 mm`). The shipped
   two-row **averaging** reaches G1 exactly but stops at `k_gap = 4.080e-4`.
4. **On the demo's real junction the limit is neighbour incompatibility, not
   the formulation** — the same solve improves the worst `k_gap` from
   **3.077e-2** to **7.117e-3 /mm** (~4×) and cannot close it, because the four
   neighbouring blends' second-order data does not agree at the junction.
5. **Recommendation (shape i, with ii as its prerequisite):** give the corner a
   continuity order backed by a control-net G2 solve instead of the two-row
   average; treat the neighbours' own knobs (`scale_tangent`, `autoG3`) as the
   lever that makes a junction compatible. Do **not** route G2 through
   FreeCAD's order-2 `Surface::Filling`.

---

## Instruments

Two independent instruments (as in #97), plus a new exact-on-oblique-seam
macro:

| instrument | file | method | used for |
|---|---|---|---|
| exact control net | `Tests/silk_nurbs.py` + `Tests/continuity_analytic.py` | Piegl–Tiller basis derivatives on the homogeneous net; `measure_edges` reads the four quantities + combinatorial `c0_controlnet` | deliverable 2; the solve's residual (d3/d4); the calibration cross-check |
| oblique exact | `Tests/g2_corner_fill_continuity.py::measure_oblique` | exact `II(d,d)`, `d = unit(n × seam tangent)`; a trimmed fill's seam is oblique, so a constant-parameter axis is not available | deliverable 1 |
| sampled oracle | `Tests/g2_oracle.py` | finite differences + `surface` evaluation | deliverable 1 cross-check |

`Tests/continuity_calibration.py` is the soundness harness (solve_uv floor
4.5e-13 mm; `g1_deg` shown **blind** to a 4 /mm curvature jump; both a known G1
angle and a known curvature jump). **No test asserts a continuity label for
real geometry** (`test_no_continuity_threshold_in_suite`).

### `measure_oblique` soundness (deliverable 1's instrument)

* **Known-answer cross-check against `continuity_analytic.measure_edges`.**
  The demo's constant-parameter seam `CubicSurface_66` v0 ↔ `CubicSurface_64010`
  v1 (n = 41), both implementations on the same two nets:

  | | c0 (mm) | g1 (°) | k_gap (/mm) | twist (/mm) |
  |---|---|---|---|---|
  | `measure_oblique` | 5.827e-14 | 0.4757 | 7.1174e-03 | 1.2303e-03 |
  | `CA.measure_edges` | 5.827e-14 | 0.4757 | 7.1174e-03 | 1.2303e-03 |

  Raw: `/tmp/opencode/g2_oblique_calibration.txt`, reproduced in-repo with
  `import Tests.g2_corner_fill_continuity as m; m.calibrate(n=41)`.
  The two agree to every printed digit.
* **Error floor.** Fill surface reconstructed from OCCT `BSplineSurface` as a
  `silk_nurbs.NurbsSurface`: max reconstruction error ≤ 8.5e-14 mm. Seam
  parameter solve floor: boundary residual 3.5e-4 mm (orders 0/1), 9.4e-3 mm
  (order 2). `solve_uv`'s own floor: 4.5e-13 mm. So a `k_gap` above ~1e-4 /mm
  is geometry, not solver noise.
* **Independent cross-check on the fill seams.** `g2_oracle.measure_seam` on
  the same seams reproduces `g1_deg` to four decimals and `k_gap` to the same
  order (raw: `/tmp/opencode/g2_fill_crosscheck_report.json`). It fixes a
  constant across axis, so on the oblique fill seam it is the weaker of the
  two; it agrees on the claim (order 2 worse than order 1).

---

## Deliverable 1 — FreeCAD `Surface::Filling` at `BoundaryOrder = 2`

`Tests/g2_corner_fill_continuity.py` (MANUAL) rebuilds the same two feeds as
#91's Phase B probe (`Tests/g2_corner_fill_probe.py`) on the throwaway corner
model (`Tests/corner_model.py`), but reads the **calibrated curvature** metrics
instead of a normal gap. Raw:
`/tmp/opencode/g2_fill_continuity_report.json`. Reproduce:
`import Tests.g2_corner_fill_continuity as m; m.main(n=41, grid=40)`.

| feed | order | valid | boundary residual | `k_gap` (/mm) | `twist_gap` (/mm) | `g1_deg` |
|---|---|---|---|---|---|---|
| raw | 0 | yes | 2.931e-3 mm | — (octagon) | — | — |
| raw | 1 | **NO** | 7.320 mm | — | — | — |
| raw | 2 | **NO** | 7.758 mm | — | — | — |
| strip | 0 | yes | 3.575e-4 mm | 8.116e-2 | 1.006e-1 | 4.3221 |
| strip | 1 | yes | 3.463e-4 mm | 8.249e-2 | 8.603e-2 | 0.1549 |
| strip | 2 | yes | 9.372e-3 mm | **1.665e-1** | 9.834e-2 | 1.1005 |

Convergence (raw `/tmp/opencode/g2_fill_convergence.txt`): `k_gap` is identical
at n = 41 and n = 81 and at grid = 40 and grid = 120 for both orders; only the
peak `g1` moves by 0.015° with more stations. The numbers are converged.

Readings:

* **Order 2 is not G2 and is not better than order 1.** `k_gap` grows from
  8.249e-2 (order 1) to 1.665e-1 (order 2); `g1` grows from 0.155° to 1.10°.
  The second-order boundary condition makes the *tangent-plane* mismatch worse
  and does not reduce the curvature mismatch. The order knob does not deliver
  its name for this feed.
* The strip feed builds a **valid** fill at all three orders. At order 2 it
  trades boundary fit for the second-order condition: the boundary residual
  rises from 3.5e-4 mm to 9.4e-3 mm — the fill no longer passes through its
  own boundary to the order-1 accuracy — and still misses G2.
* The **raw** feed (ADR-0005 Q1=b, the raw patch cells) is over-constrained:
  only order 0 builds (residual 2.9e-3 mm); orders 1 and 2 return an invalid
  face whose surface does not contain its boundary (residual 7.3 / 7.8 mm).
  This reproduces #91's Phase B result, now with an independent instrument.
* These `g1` numbers agree with #91's Phase-B probe (orders 0/1: 4.29° and
  0.155°). Order 2's 1.10° exceeds the probe's recorded 0.483° because the
  probe discarded stations whose boundary residual exceeded 1e-3 mm, dropping
  exactly the stations where the order-2 fill leaves its boundary.

**Deliverable 1 verdict: FreeCAD's order-2 fill does not achieve G2 here, and
order 2 is measurably *worse* than order 1 — the order knob is not the route
to G2.**

---

## Deliverable 2 — Is Silk's edge blend G2?

`Tests/g2_edge_blend_probe.py` (MANUAL) pairs every `CubicSurface_64` blend in
`Silk_Demo_01` with each `CubicSurface_44` patch it shares a boundary with
(`continuity_analytic.match_boundaries`) and reads the exact metrics. Raw:
`/tmp/opencode/g2_edge_blend_report.json`. Reproduce:
`import Tests.g2_edge_blend_probe as m; m.main(n=41)`.

Two kinds of `CubicSurface_64` are reported separately, because they are
different objects:

**Edge blends (`ControlGrid64_2Grid44`) — 14 seams.** g1 max **0.0000°**
(G1-exact); `k_gap` ∈ [0, 2.528e-4] /mm; worst `twist_gap` 5.417e-3 /mm.
Three seams are exactly 0; only one exceeds 1.419e-4 (the 2.528e-4 seam).

**Hard-corner sub-surfaces (`ControlGrid64_3_1Grid44`) — 7 seams.** These are
the three-patch HARD corner surfaces, not edge blends: their matched boundary
degenerates (all six poles coincide → null normal), so `g1_deg` reads 90° by
construction. Reported, not counted: `k_gap` up to 1.323e-2 /mm, `twist_gap` up
to 1.351e-2.

**Deliverable 2 verdict: the edge blend is the strong link.** It is G1-exact
and its `k_gap` is ≤ 2.5e-4 /mm — ~120× below the corner's worst 3.1e-2 /mm.
(Whether 2.5e-4 clears the repo's 5e-5 `k_abs_tol` is a tolerance question; the
number is the evidence. The point that matters: the weak link is the corner,
not the edge blend.)

---

## Deliverable 3 — Are the four neighbours mutually compatible? (synthetic known-answer)

`Tests/g2_corner_solve.py` (MANUAL). A synthetic ring is built from **one**
known smooth 6×6 Silk surface `T`: each strip is the exact outward cubic
extension (`EXT`) of `T`'s first/last control span across its seam, λ = 1. The
exact G2 continuation is therefore `T` itself, known by construction. Raw:
`/tmp/opencode/g2_corner_solve_report.json` (key `synthetic`). Reproduce:
`import Tests.g2_corner_solve as m; m.run_synthetic(n=41)`.

| construction | g1 (°) | `k_gap` (/mm) |
|---|---|---|
| truth `T` vs strips | 0.0000 | ≤ 6.68e-17 |
| current (two-row averaging) | 0.0000 | ≤ **4.080e-4** |
| G2 solve (least-squares) | 0.0000 | **5.963e-17** |

The solve leaves **4 free central poles** (36 → 4, 12 DOF), because C0 and G1
are imposed exactly first (hard C0 = boundary row = neighbour `V3`; hard G1 =
one-in row = `V3 − (V2 − V3)/λ`). `k_a` is exactly linear in those 4 poles (the
first derivatives and the normal are already fixed), so one Gauss-Newton step
is exact: residual 5.963e-17. `|solved − T|_inf = 2.345e-13 mm` — the solve
reconstructs the known continuation.

**Deliverable 3 verdict.** (a) The averaging construction reaches **G1
exactly** on this feed but stops at `k_gap = 4.080e-4` — its averaging is a
formula artefact, not a compatibility limit, because the neighbours here are
pieces of one surface. (b) The G2 solve **recovers the known G2 continuation
exactly**. So **the maths is not the limit**: matching a corner's rows 0,1,2 to
its neighbours' rows 0,1,2 is linear algebra on the control net, and when the
neighbours are mutually compatible it is exactly solvable.

---

## Deliverable 4 — The same solve on the demo's real junction

Same module, `run_demo`; the neighbours are the four ring blends of each
junction of `Silk_Demo_01` (the same neighbours #97 measured against). Raw:
`/tmp/opencode/g2_corner_solve_report.json` (key `demo`). λ is read per seam,
per station, from the corner's own G1 rows (it is not 1 and varies along a
seam, e.g. 0.90 → 2.40 at `CubicSurface_66` v0).

| junction | current worst `k_gap` | solved worst `k_gap` (= solve residual) |
|---|---|---|
| `CubicSurface_66` | 1.307e-2 | **7.117e-3** |
| `CubicSurface_66001` | 3.077e-2 | 4.999e-3 |
| `CubicSurface_66002` | 1.950e-2 | 3.375e-3 |
| `CubicSurface_66003` | 2.107e-2 | 2.212e-4 |
| **worst** | **3.077e-2** | **7.117e-3** |

The solve improves the worst `k_gap` ~4× but **cannot close it**: the
least-squares residual *is* the neighbours' mutual incompatibility. The
attainable gap sits at the seam with the largest G1 error and the most
varying λ (`CubicSurface_66` v0 ↔ `CubicSurface_64010`, g1 0.476°, λ 0.90 →
2.40), i.e. where the neighbours' second-order data disagree most.

**Deliverable 4 verdict.** At the demo's junctions the limit is **neighbour
incompatibility**, not the formulation: the exact solve reaches `k_gap` =
7.1e-3 there, versus 6.0e-17 on the compatible synthetic junction. Replacing
the averaging formula with a solve buys ~4× but does not reach G2 unless the
neighbours themselves are made to agree.

---

## Deliverable 5 — Recommendation

**Shape (i), with (ii) as its prerequisite: the corner gains a continuity
order backed by a control-net solve; the neighbours' own knobs are the lever
that makes a junction compatible.**

* On a junction built from compatible neighbours, a control-net G2 solve is
  exact (deliverable 3). Give `CornerBlend` a continuity order (`G0/G1/G2`)
  that runs the real-valued G2 solve (`Tests/g2_corner_solve.solve_corner_h`,
  ported into `SilkMachinery`) instead of the fixed two-row average. This is
  the same shape every other Silk primitive already has (the edge blend's
  `scale_tangent_*`/`scale_inner_*`/`autoG3`).
* On the **legacy** demo neighbours the solve's bar is 7.1e-3 /mm
  (deliverable 4), because their second-order data does not agree at the
  junction. A UI-level G2 claim therefore needs the neighbours rebuilt or
  knobbed to agree (`ControlGrid64_2Grid44.scale_tangent_*` /
  `scale_inner_*` / `autoG3`). That is the natural follow-on ticket, and it is
  why (i) alone changes the formula but not the number on existing documents.
* **Do not route G2 through FreeCAD's order-2 `Surface::Filling`**: measured on
  the same corner it is not G2 and is worse than order 1 in both metrics
  (deliverable 1). ADR-0005's "users who want an order-2 build" note should not
  be read as a G2 claim.

---

## What could not be established / notes for the ticket owner

* **`twist_gap` is not used as evidence here.** Before #101
  `continuity_analytic.measure_seam` took its along-tangent from the surface's
  natural parameter axis and lost the normal side in alignment, so a seam
  whose correspondence is reversed (which `match_boundaries` freely chooses)
  -- and, as #101 found, any pair whose natural normals oppose -- read ~2|tau|
  even on a smooth seam. #101 measures it in a common frame and pins that with
  a known-answer calibration, so `twist_gap` is now quotable on reversed seams
  as well; the figures in this document were not re-measured with the
  corrected frame. `k_gap` is unaffected and is the G2 evidence throughout.
  (Both `g2_corner_solve` and `g2_edge_blend_probe` print a `(rev)` flag for
  this.)
* **Full G2 (all of the second fundamental form) was not established for any
  real seam.** `k_gap` is the across-seam normal curvature only — necessary,
  not sufficient. The synthetic solve is exact in `k_gap`; twist there is
  carried but not separately solved.
* **The neighbours' knobs were not explored.** Whether setting
  `scale_tangent_*` / `scale_inner_*` / `autoG3` on the legacy
  `ControlGrid64_2Grid44` makes the demo's junctions mutually compatible is
  unmeasured; the finding only shows the *current* neighbours are incompatible
  (the solve residual).
* **The 7 hard-corner sub-surfaces were excluded from deliverable 2 by name,
  not by tolerance** (degenerate boundary → the `g1_deg` 90° is an artefact,
  not a G1 failure). The ticket's deliverable 2 says "`CubicSurface_64`
  blend ↔ patch seams"; four of the twelve `CubicSurface_64` are hard-corner
  surfaces driven by `ControlGrid64_3_1Grid44`, so 12 objects yield 21 seams
  and only 14 are edge-blend seams. The finding separates them.
* **The raw feed cannot be measured at the curvature level** — orders 1 and 2
  do not build a point on the boundary, so `k_gap` there is not a number. The
  order-0 raw fill exists (residual 2.9e-3 mm) but its boundary is an octagon,
  so no per-edge curved match exists to read; it is reported as built, not as
  G2.
* **The ticket's premise checks out.** "The corner is a bicubic 6×6 grid … so
  G2 is algebra on the control net, not an analytic impossibility" — confirmed
  (deliverable 3). "Exact simultaneous C2 to all four neighbours is possible
  precisely when the four neighbours are mutually compatible" — confirmed by
  the synthetic/demo split (deliverable 3 vs 4).

---

## Recommended wording (not applied — `AGENTS.md` and `docs/adr/*` are read-only here)

**`AGENTS.md`, `### Corner Blend`, the "No continuity is asserted." bullet.**
Replace the trailing clause *"#100 is the investigation of what G2 would
take"* with something like:

> …C0 exact, G1 ≤ 0.48°, **not G2**. **#100 measured what G2 would take**
> (`docs/research/silk-corner-g2.md`): the bar is a control-net **solve** of the
> corner's 4 free central poles, not the two-row average. On a known smooth
> junction the solve recovers the exact G2 continuation (`k_gap` 6.0e-17), so
> the maths is not the limit; on the demo's legacy neighbours the attainable
> `k_gap` is 7.1e-3 /mm, set by the neighbours' mutual incompatibility, not the
> formulation. FreeCAD's order-2 `Surface::Filling` is not the route (its
> `k_gap` 1.7e-1 is worse than order 1's 8.2e-2). Silk's **edge blend** is the
> strong link: G1-exact, `k_gap` ≤ 2.5e-4 /mm.

**`AGENTS.md`, "Continuity instrument (corner stage)" manual-script list.**
Add the three new MANUAL scripts, e.g. after the `g2_corner_measurement.py`
mention: *"`Tests/g2_corner_solve.py` (synthetic + demo G2 solve), `Tests/
g2_edge_blend_probe.py` (edge-blend `k_gap`) and `Tests/
g2_corner_fill_continuity.py` (fill `k_gap`; `measure_oblique`) carry
`MANUAL = True` and are asserted reachable."*

**`docs/adr/0005-corner-blending.md`, after "Measurement update (#97)", add a
"Measurement update (#100)" paragraph:**

> #100 measured what G2 would take. The G1 wall is the construction, not the
> maths: the shipped `SubGrid33_2Grid64`/`corner_grid` reads two rows and
> averages, while matching a corner's rows 0,1,2 to its neighbours' is linear
> algebra — on a synthetic junction of compatible neighbours a control-net
> solve recovers the known G2 continuation exactly (`k_gap` 6.0e-17), and the
> current averaging stops at 4.1e-4. On the demo's legacy neighbours the same
> solve reaches only `k_gap` 7.1e-3 /mm, so the real-data limit is neighbour
> incompatibility; the neighbours' own continuity knobs (`scale_tangent_*`,
> `scale_inner_*`, `autoG3`) are the lever, and making a junction compatible is
> its own ticket. FreeCAD `Surface::Filling` at `BoundaryOrder = 2` is not G2
> here and measures *worse* than `= 1` (`k_gap` 1.665e-1 vs 8.249e-2; `g1`
> 1.10° vs 0.155°), so the "order-2 build" opt-in is not a G2 claim. The corner
> stage's target stays the reference bar (G1, ≤ 0.5°); a G2 target is now
> supported by measurement only up to the neighbours' compatibility.

---

## Method / limits

* Live GUI over XML-RPC (localhost:9875); `ArachNURBS` imports `FreeCAD.Gui`,
  so the analytic layer and the throwaway fixtures run on the GUI thread. No
  document is built or removed off the GUI thread.
* All fixtures are built in `Tests/` (`corner_model.py`, `g2_corner_fill_probe
  .py`, `g2_corner_solve.py`); every scratch document is closed again and the
  tree is left clean.
* Manual scripts: `Tests/g2_corner_solve.py` (d3/d4),
  `Tests/g2_edge_blend_probe.py` (d2), `Tests/g2_corner_fill_continuity.py`
  (d1). All carry `MANUAL = True`; the suite asserts they import, expose
  `main`, and stay marked (`Tests/test_continuity_instrument.py::
  test_manual_measurement_scripts_reachable`), and never runs geometry.
* `Silk_Demo_01` (357 objects) is opened read-only and never saved.
* Raw outputs: `/tmp/opencode/g2_fill_continuity_report.json`,
  `/tmp/opencode/g2_fill_crosscheck_report.json`,
  `/tmp/opencode/g2_oblique_calibration.txt`,
  `/tmp/opencode/g2_fill_convergence.txt`,
  `/tmp/opencode/g2_edge_blend_report.json`,
  `/tmp/opencode/g2_corner_solve_report.json`.
