# Is our ported triangular member faithful to upstream's stored member? (member calibration)

**Question.** Is `SilkMachinery.control_grid64_3_1` (the triangular 4th ring
member of the 3-valent hard corner) faithful to upstream's
`ArachNURBS.ControlGrid64_3_1Grid44` **as actually stored** in
`Resources/Demo_files/Silk_Demo_01.FCStd`?

**Answers, one line each.**

1. **Yes -- exact parity (ticket-foldfix).** On the demo's four stored
   members our port reproduces the stored 24-pole net and weight channel
   with max |dPole| = max |dWeight| = **0.0**, no slot differing, on all
   four objects (`Tests/test_triangular_member_calibration.py` pins it).
   The original finding -- three flat slots (8/p12, 15/p23, 16/p24)
   deviating by up to **7.6036 mm** -- was fixed by making the port
   term-for-term upstream: `p12 = (set_poles[5] + p11)/2` with
   `p11 = set_poles[9]`, and `p24 = p25 + (set_poles[10] - p25)/2` with
   `p25 = set_poles[11]`; `p23` then inherits the corrected `p24`.
2. **The weight channel follows upstream's literal lines too.** `w12 =
   (w02 + w21)/2`, `w13 = (w03 + w24)/2` -- the lines that look like a
   copy-paste from a different index map (`w12` averages the input weights
   that feed `p22`, not `p12`). This is deliberate: parity with the stored
   members is the product decision, and the demo cannot distinguish
   because every stored input weight is `1.0`. The synthetic non-unit
   input now pins parity there too (max |dWeight| **0.0** at every corner;
   the pre-fix divergence was 1.875 in slots 8/9). **Rational-weight
   check:** the fixture/demo feeds are unit-weight; the change moves the
   weight channel *toward* what upstream actually built, and no test
   measures a rational 3-valent input, so any rational-case consequence is
   unmeasured -- flagged here deliberately rather than implied.
3. **The demo is a valid known-answer oracle.** Upstream's own class,
   re-executed on the demo's stored 4x4 input grids, reproduces all four
   stored members with max |dPole| = max |dWeight| = **0.0** (bit-exact).
4. **No mapping was needed** and none was applied: signature, corner
   convention, row-major 4x6 ordering, units and the row-3 collapse onto
   `set_poles[15]` all match. The two implementations were compared on the
   same flat indices; nothing was permuted to force a match.
5. **Parity did NOT remove the cube-corner fold -- the fold is upstream's.**
   On the cube-corner fixture the folded member and the parity member both
   fold: normal-field flips at n=39 were **17 of 1521** pre-parity and
   **19 of 1521** post-parity (n=81: 23 either way; the difference is
   sampling, not geometry), and the collapsed apex row is byte-identical
   between them. A sweep of the member's third-strategy spacing factor
   t = 0.0..1.0 (upstream 0.5) never reached 0 flips (15-27 at n=39). The
   fold comes from `subgrid33_2grid64`'s extrapolation of the subgrid
   interiors PAST the collapsed row. **Fixed at the assembly**
   (`SilkMachinery.smooth_degenerate_cap`, section 5): after it, 0 flips
   at n=39/81 on the Part surface and the exact net, cap samples inside
   the boundary box (the folded net poked 0.0101 mm past it), the opposite
   seam's exact G1 (0.0000 deg) and `k_gap` 6.888e-15 /mm preserved, and
   the degenerate seams' `k_gap` down from 3.514e+02 /mm to ~2e-13 /mm
   exact / 2.380e-03 /mm sampled.

---

## Instruments

| instrument | file | method |
|---|---|---|
| stored known answer | `Resources/Demo_files/Silk_Demo_01.FCStd` | read read-only: `Document.xml` for the objects, the binary `Poles*`/`Weights*` blobs (`uint32` count + `float64` payload) for the numbers. Nothing was opened, recomputed or saved. |
| live upstream reference | `ArachNURBS.ControlGrid64_3_1Grid44` | instantiated on a carrier object in the test document and recomputed -- the parity-oracle pattern of `Tests/test_corner_blend.py::_legacy_corner_chain` |
| our port | `SilkMachinery.control_grid64_3_1` | called directly |
| criterion | `Tests/test_triangular_member_calibration.py` | max Euclidean pole distance in mm (the repo's convention); exact = `<= 1e-9` |

The suite test pins every number below: `python3 Tests/run_all.py
member_calibration`.

## 1. The demo's four stored members

Identified from `Document.xml` by `module="ArachNURBS" class="ControlGrid64_3_1Grid44"`:

| stored member | input (`ControlGrid44` link) | `Corner` | stored | policy |
|---|---|---|---|---|
| `ControlGrid64_3_Grid44` | `ControlGrid44_2EdgeSegments008` | 3.0 | 24 poles / 24 weights, weights all 1.0 | input 16/16, weights all 1.0 |
| `ControlGrid64_3_Grid44001` | `ControlGrid44_2EdgeSegments016` | 0.0 | 24/24, weights all 1.0 | 16/16, 1.0 |
| `ControlGrid64_3_Grid44002` | `ControlGrid44_2EdgeSegments023` | 1.0 | 24/24, weights all 1.0 | 16/16, 1.0 |
| `ControlGrid64_3_Grid44003` | `ControlGrid44_2EdgeSegments026` | 3.0 | 24/24, weights all 1.0 | 16/16, 1.0 |

`Corner` is an `App::PropertyFloat` holding an integral value 0-3; both sides
name the same corner index (upstream's `if corner == 0: rotate = 0` chain) and
both flatten the rotated 4x4 grid row-major before building the 24-pole
output, so no index mapping is needed.

### Known-answer calibration -- upstream's class re-run vs the stored 24

| member | max \|dPole\| (mm) | max \|dWeight\| | poles differing |
|---|---|---|---|
| `ControlGrid64_3_Grid44` | 0.000e+00 | 0.0 | -- |
| `ControlGrid64_3_Grid44001` | 0.000e+00 | 0.0 | -- |
| `ControlGrid64_3_Grid44002` | 0.000e+00 | 0.0 | -- |
| `ControlGrid64_3_Grid44003` | 0.000e+00 | 0.0 | -- |

The stored member **is** upstream's own output, so any deviation is ours.

### Our port vs the stored 24

After ticket-foldfix (pinned):

| member | corner | max \|dPole\| (mm) | max \|dWeight\| | pole slots differing |
|---|---|---|---|---|
| `ControlGrid64_3_Grid44` | 3 | 0.000e+00 | 0.0 | -- |
| `ControlGrid64_3_Grid44001` | 0 | 0.000e+00 | 0.0 | -- |
| `ControlGrid64_3_Grid44002` | 1 | 0.000e+00 | 0.0 | -- |
| `ControlGrid64_3_Grid44003` | 3 | 0.000e+00 | 0.0 | -- |

Historical record (the pre-foldfix state the original calibration measured;
kept so the finding is auditable): max |dPole| 2.3823927790370045 mm
(`...44`), 1.2720659601562707 (`...001`), 6.3309534363346289 (`...002`),
7.6035673075488015 (`...003`), all of the order of one whole input cell edge
(0.94-1.19 x the mean cell edge), confined to flat slots 8, 15, 16, with
`slot 16 / slot 15 = 2.000000000` on all four (the halving-chain signature).

## 2. Where the two implementations part company (source, term by term)

Both sides: `np.rot90` of the row-major 4x4 by `Corner`, flatten, then the
third strategy. Identical: `p00=sp[12]`, `p01=sp[8]`, `p02=sp[4]`, `p03=sp[1]`,
`p04=sp[2]`, `p05=sp[3]`, `p10=sp[13]`, `p11=sp[9]`, `p21=p20+(sp[10]-p20)/2`,
`p22=p21+(sp[10]-p21)/2`, `p13=(sp[5]+p14)/2`, `p25=sp[11]`,
`p30..p35=sp[15]` (the collapsed row), `w21..w24=sw[10]`, `w30..w35=sw[15]`,
and the whole `p0*`/`p1*`/`w0*`/`w1*` block outside the lines below.

| output slot | upstream `ArachNURBS.py` | our port (now) | pre-foldfix port |
|---|---|---|---|
| p12 (flat 8) | `(set_poles[5] + p11)/2`, `p11 = set_poles[9]` | `(p[5] + p11)*0.5` | `(p[5] + p[11])*0.5` (wrong source pole) |
| p24 (flat 16) | `p25 + (set_poles[10] - p25)/2`, `p25 = set_poles[11]` | `p25 + (p[10] - p25)*0.5` | `p[15] + (p[10] - p[15])*0.5` (wrong start) |
| p23 (flat 15) | `p24 + (set_poles[10] - p24)/2` | same expression, corrected `p24` | same expression, wrong `p24` |
| w12 (flat 8) | `(w02 + w21)/2 = (sw[4] + sw[10])/2` | `(w02 + w21)*0.5` | `(w[5] + w[11])*0.5` |
| w13 (flat 9) | `(w03 + w24)/2 = (sw[1] + sw[10])/2` | `(w03 + w24)*0.5` | `(w[5] + w[6])*0.5` |

The port's pre-fix `p12` line also carried a vestigial
`if hasattr(...)` guard from the transcription; it is gone.

## 3. The weight channel, measured (synthetic non-unit input)

The demo has unit weights everywhere, so it carries no weight information.
Feeding both sides the same synthetic 4x4 net (poles at 10 mm spacing plus a
bow, weights in `[0.25, 5.0]`): after the fix, max |dPole| = max |dWeight| =
**0.0** at corners 0-3, no slot differing. Pre-fix the same input measured
max |dWeight| **1.875** at weight slots 8/9 (w12/w13), with the pole
signature above.

## 4. What the port divergence meant for the cube-corner apex pinch

`Tests/test_cube_corner_3valent.py` measures the shipped 3-valent corner on
`Tests/cube_corner_model.py`'s unit-cube fixture (three planar patches
meeting at the origin, band splits 0.1, so the ring corner cell spans 0.1 mm
with poles at steps of `1/30` mm). Pre-fix, substituting upstream's member on
the fixture's own member input (patch `PatchA`, corner 0, not reversed)
moved the 36-pole corner net by 5.556e-3 mm at slots 25/26 while the
collapsed apex row was byte-identical -- i.e. the degenerate-boundary normal
at the apex was **not** the port's doing. Post-fix, our member IS upstream's
member on the fixture (max |dPole| 0.0, all 24 slots; pinned in the fourth
test).

## 5. The fold (ticket-foldfix): found, diagnosed, fixed

Parity alone did not remove the fold (answer 5 above), so the fix moved to
the assembly:

* **Diagnosis.** With the member at ring index 3, the corner's member-side
  interior rows come from `subgrid33_2grid64` pairs involving the member.
  That routine extrapolates each subgrid's interior *past* the shared
  corner (`p11_v = p10 + (v_col0[1] - v_col1[1]) * u_tan_ratio`, etc.) --
  right for a regular pair, but past a COLLAPSED end row it places poles
  beyond the apex (on the fixture: subgrid 3's `p21 = A + (A - member[15])
  * 2/3`, row v4 of the corner ends up at (0.11667, 0.12222) against an apex
  A = (0.1, 0.1)). The cap's planar projection then reverses orientation
  near the apex: the normal field flips 19 times at n=39.
* **Fix.** `SilkMachinery.smooth_degenerate_cap(p36, w36, tol)`:
  detect a collapsed 6x6 side (all six poles coincident), re-index the net
  to the Coons frame (collapse at V1), and re-solve the **eight interior
  poles of the two member-side rows** (frame u = 1..4, v = 3,4) as the
  least-squares projection of the transfinite (Coons) fill of the corner's
  own boundary loop. Weights are held fixed (the rational basis function is
  `N_i N_j w_ij / W`), so only pole positions move; a non-finite solve
  returns the input unchanged. Called from `corner_grid`, so it is a
  byte-identical no-op whenever no side is collapsed (every 4-valent ring --
  CB2 pole parity with the legacy chain stays intact).
* **Why those eight poles.** In the frame, the strip-side rows/columns are
  untouched, and the seam OPPOSITE the member reads only the first three
  control rows for its G1 and curvature -- measured: exact G1 0.0000 deg and
  `k_gap` 6.888e-15 /mm preserved. Freeing row v2 as well broke that
  `k_gap` (12.9 /mm): the opposite seam's curvature needs row 2 as well.
* **Measured after the fix** (built corner on the fixture; raw output kept
  with the ticket):
  * normal-field flips: **0** at n=39, 81 and 150, on the `Part` surface
    (`SilkChecks._normal_field_flips`) and on the exact control net
    (was 19/23 at n=39/81). The folded net's reversal is continuous, not a
    discontinuity: at n=300 the folded net reads 0 flips too (a one-off
    fine check at n=300/600 on the FIXED net also reads 0), so the coarse
    count is the aliased reading of a tight crease -- the box overshoot
    below is the resolution-independent defect;
  * overshoot: all exact-net samples inside the boundary rows' box
    `[2.0e-17, 0] x [0, 0] x [0, 0] .. (0.1, 0.1, 0.1)`; worst excursion
    **0.000e+00 mm** (the folded net poked 0.0101 mm = 10 % of the corner
    cell past it);
  * `Shape.isValid()` true; a 1e-3 mm mesh of the face (320 facets) has no
    self-intersections;
  * seam numbers (n=21, exact / sampled `k_gap`): the non-reversed seam
    `B_BC` 6.888e-15 / 4.563e-03 (its exact G1 0.0000 deg); the two
    degenerate-apex seams `B_AB`/`B_CA` 9.446e-13 / 2.380e-03 and
    2.029e-13 / 2.380e-03 (was 3.514e+02 / 3.512e+02), with their
    apex-side `g1` still reading 90 deg -- the collapsed row's boundary
    normal is genuinely degenerate upstream's construct, reported
    separately and not a cap-quality number;
  * side-agnostic: the same raw assembly smoothed with the collapse placed
    on each of v1/v0/u1/u0 gives the identical net (max |dPole| 0.0) and 0
    flips (`test_3valent_cap_smoothing_is_side_agnostic`).

## 6. What this memo does not claim

* **No continuity label.** Nothing here asserts G1/G2 anywhere, and no test
  does either (`test_no_continuity_threshold_in_suite`).
* **Not a verdict on upstream's design.** The fold fix departs from
  upstream's assembly deliberately: the owner acceptance is "no visible
  fold", not parity for its own sake. The member itself stays a faithful,
  term-for-term port.
* **The rational 3-valent case is unmeasured.** All shipped feeds are
  unit-weight (the demo's stored inputs included); the smoothing keeps
  whatever weights the subgrid chain produced and solves only poles, but no
  test exercises a rational 3-valent input, and none is claimed.
