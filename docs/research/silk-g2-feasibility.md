# What the strips' interior freedom does to the corner-G2 wall (ticket #106)

**Question.** #100 measured what G2 at the 4-patch corner would take: on a
synthetic junction of compatible neighbours the control-net solve recovers the
exact continuation (`k_gap` 5.963e-17), but on `Silk_Demo_01`'s legacy
junctions it stops at **7.117e-3 /mm** (worst of four; frozen-neighbour
baseline 3.077e-2). #100 named the limit the neighbours' mutual
incompatibility and left the neighbours' knobs unmeasured. #106 asks the next
question: **is that wall caused by the strips' hardcoded recipe (the stitch +
`scale 2.0` build), i.e. does freeing the strips' interior remove it?**

**Answer (one line).** The wall moves but does not vanish: freeing each seam
strip's second-order control row and re-solving it jointly with the corner's 4
free central poles takes all four demo junctions from (7.117e-3, 4.999e-3,
3.375e-3, 2.303e-4) down to (**2.764e-4, 4.689e-5, 7.636e-5, 1.026e-5 /mm**)
with every freed pole moving ≤ 0.52 of a control-cell edge and no fold — three
of four junctions land at or below the edge blend's own 2.528e-4 reference —
but the residual cannot be driven to the station-level zero without motions of
5–90 cells that fold the strips. So the binding constraint at the demo is the
**strip's shape authority** (one 6-pole row cannot match the seam pointwise),
not the patches' second-order disagreement alone.

**Caveat up front.** `k_gap` only (across-seam normal curvature); no full-G2
claim. No continuity label is asserted anywhere in this finding or its test.
`twist_gap` is carried but not solved (and #101's reversal caveat applies).

---

## Method

Offline, no FreeCAD, read-only: `Silk_Demo_01.FCStd` parsed straight from its
zip (`Document.xml` + `Poles*` / `Weights*` blobs; the technique of
`Tests/test_triangular_member_calibration.py`). The instrument
(`Tests/silk_nurbs.py` + `Tests/continuity_analytic.py`: exact control-net
evaluation, `match_boundaries`, `measure_edges`) and the #100 solve
(`Tests/g2_corner_solve.py`: hard C0/G1 from the neighbour rows, least-squares
on the `k_a - k_b` residual) are ported to pure numpy (`g2lib.py` in
`/tmp/opencode/g2_feasibility/`; raw JSONs beside it).

Three feeds, all at the same code:

1. **synthetic** — #100's compatible ring (four strips that are exact outward
   extensions of one smooth 6×6 net `T`). Known answer: the solve must recover
   `T`.
2. **demo frozen** — the four stored `ControlGrid66_4Sub` junctions, the same
   feed and solve as #100 (control).
3. **demo treated** — the corner's 4 central poles **plus each seam strip's
   second-order row** (the row two steps behind its junction row), jointly
   least-squares in the seam `k` residuals. The strips' junction rows and
   one-behind rows stay fixed, so C0, G1 and the seam positions are untouched
   by construction; only the curvature side is free.

Scales: `motion` is reported in mm and in **cells** (mm divided by the strip's
own mean adjacent-pole distance, 0.99–26.4 mm across these eight strips).

## Controls

* **(a) synthetic ring.** Port reproduces the documented numbers: truth vs
  strips ≤ 6.679e-17 (`#100`: ≤ 6.68e-17); two-row averaging 4.080e-4
  (`#100`: 4.080e-4); solve station residual 3.773e-17 (`#100`: 5.963e-17);
  `|solved − T|_inf` 2.274e-13 mm (`#100`: 2.345e-13).
* **(b) demo frozen.** All eight #100 table numbers reproduced within print
  precision — worst `k_gap` per junction, current → solved:
  1.3066e-2 → 7.1174e-3; 3.0770e-2 → 4.9990e-3; 1.9502e-2 → 3.3750e-3;
  2.1071e-2 → 2.2117e-4 (doc: 1.307e-2 → 7.117e-3; 3.077e-2 → 4.999e-3;
  1.950e-2 → 3.375e-3; 2.107e-2 → 2.212e-4). The calibration seam
  (`CubicSurface_66` v0): `k_gap` 7.1174e-03, `g1` 0.4757°, `twist`
  1.2303e-03 — digit-for-digit the #100 `measure_oblique` table.

## Raw numbers (`results.md` has the full per-seam table, n=401)

| junction | frozen worst | treated worst | gain | max motion | folds |
|---|---|---|---|---|---|
| CubicSurface_66 | 7.117e-3 | **2.764e-4** | 26× | 0.52 cells (0.80 mm) | 0 |
| CubicSurface_66001 | 4.999e-3 | **4.689e-5** | 107× | 0.52 cells | 0 |
| CubicSurface_66002 | 3.375e-3 | **7.636e-5** | 44× | 0.47 cells | 0 |
| CubicSurface_66003 | 2.303e-4 | **1.026e-5** | 22× | 0.03 cells | 0 |

The joint solve drives its own station residual (36 equations, 9 stations per
seam) to 2.6e-15…4.9e-16 /mm — exact for the linear system. The numbers above
are the **converged measurement at n=401 stations** (stable to 4 digits from
n=41 on), i.e. what the fitted geometry actually reads between the fitted
stations.

Pushing the sample count up makes things worse, not better: solving at
n_st=21/41 reaches 1e-8-level readings only by moving poles 5–90 cells
(`pareto.py`), 35–99 normal-field flips where fold-checked (J1/J2 at
n_st=41, `checks.py`) — the 6-pole curvature row cannot reproduce the
required between-station detail. Ridge-regularised refits at n_st=41 do not
recover a small-motion point below ~1e-4 for the two worst junctions.

**Member freedom (secondary).** All four triangular members carry their
collapse in row 3 (spread 0.0 mm) with the junction row at row 0. Freeing the
member's own second-order row (row 2 — the primary treatment above) is what
lets the member-side seams close. Two variants were measured and are recorded
as such: (A) member fully frozen — the min-norm fit compensates by moving the
corner's central poles by 1.3e2–1.5e2 mm and the n=41 reading is *worse* than
the frozen baseline; (C) member rows 1+2 free with the corner's G1 row
following — **not expressible in this model**: the member's G1 row maps onto
the corner's u=4 column, whose endpoints are simultaneously the v0/v1 boundary
rows pinned by the other seams' C0 conditions. A faithful member-G1 run needs
a weighted joint re-solve with soft-coupled C0/G1, which is not this finding.

## Verdict

1. **The hypothesis is half right, and the half that is wrong is the
   interesting half.** The strips' second-order row is a real lever: with it
   free, no junction needs more than half a cell of motion to fall to
   1e-5–3e-4 /mm, i.e. the strip recipe (the fixed `scale 2.0` value of that
   row), not the patches, is what #100 measured as "neighbour
   incompatibility".
2. **But the freedom does not close the wall.** The strip's curvature across a
   seam is controlled by one 6-pole row; that row's shape space cannot match
   the corner's curvature *pointwise*, so beyond ~1e-4 /mm the solve pays in
   pole motion and folds. The residual floor is a resolution limit of the
   4-row strip parametrisation — the exact-at-stations solution is real but
   not a usable surface.
3. **Three of four junctions reach the edge blend's own bar** (2.528e-4 /mm);
   `CubicSurface_66`'s member-side seam (2.764e-4) sits just above it. So a
   G2-target build is plausible only with (i) the strip's interior row as a
   solved quantity and (ii) an explicit regularization/motion budget — and it
   would be *near*-G2, not exact.

## What was NOT established

* **Not full G2.** `k_gap` is the across-seam normal curvature only; the
  second fundamental form's other component (`twist_gap`) was carried, not
  solved, and #101's reversal caveat applies to it.
* **Not a global build.** The demo shares strips between junctions
  (`ControlGrid64_2Grid44002` appears at junctions 1 and 2, etc.), and the
  freed row also changes the strip's **far end** (normal changes of 0–10.9°
  measured at the far edge, `results.md`). The per-junction numbers are
  single-junction attainability, not a consistent whole-model solution. A
  global build needs one joint solve over all junctions and/or the far-end
  boundary conditions as constraints.
* **Not the minimum motion.** The reported motions are the minimum-norm
  solution of an under-determined system (a convention); the Pareto between
  motion and residual was only sampled (`pareto.py`), not optimised. The
  1e-5–3e-4 readings are therefore *attainable points* at ≤0.52-cell motion,
  not a proven floor: variant A shows a badly chosen exact fit can carry much
  larger between-station ripples at a larger corner-pole motion.
* **Not the patches' interior.** Only the strips' junction-side second-order
  row and the corner's 4 central poles were freed; the patches' band cells
  and the strips' outer rows were not.
* **Not the member's G1 row** — structurally out of model (above).

## Provenance

* Scripts + raw JSONs: `/tmp/opencode/g2_feasibility/` (`g2lib.py`, `run.py`,
  `checks.py`, `pareto.py`, `member_variant.py`, `final_numbers.py`,
  `g2_feasibility_report.json`, `g2_feasibility_checks.json`,
  `g2_feasibility_pareto.json`, `g2_feasibility_final.json`, `convergence.json`,
  `results.md`).
* Landed test + port: `Tests/test_g2_feasibility.py` (4 pinned calibration
  records) and `Tests/g2_feasibility_model.py` (the numpy port; runs in ~60 s).
* Repo geometry untouched; `Silk_Demo_01.FCStd` never opened, only zip-read.

## Status

Status: G2 parked in #104; corners stay G1 fold-free after #foldfix (#97,
#100, #102, #106).
