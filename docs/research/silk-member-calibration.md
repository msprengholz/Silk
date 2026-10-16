# Is our ported triangular member faithful to upstream's stored member? (member calibration)

**Question.** Is `SilkMachinery.control_grid64_3_1` (the triangular 4th ring
member of the 3-valent hard corner) faithful to upstream's
`ArachNURBS.ControlGrid64_3_1Grid44` **as actually stored** in
`Resources/Demo_files/Silk_Demo_01.FCStd`?

**Answers, one line each.**

1. **No.** On the demo's four stored members our port deviates from the
   stored 24-pole net by up to **7.6036 mm** (`ControlGrid64_3_Grid44003`,
   corner 3) — a whole input cell edge, not a rounding difference — confined
   to **three flat poles slots: 8 (p12), 15 (p23), 16 (p24)**.
2. **The demo is a valid known-answer oracle.** Upstream's own class,
   re-executed on the demo's stored 4x4 input grids, reproduces all four
   stored members with max |dPole| = max |dWeight| = **0.0** (bit-exact).
3. **The cause is two wrong source poles**, not rotation, not a tiny-spacing
   rescale, not an input-cell ordering change: our `p12` averages
   `set_poles[5]` with `set_poles[11]` where upstream averages it with
   `set_poles[9]`; our `p24` starts from `set_poles[15]` where upstream
   starts from `p25 = set_poles[11]` (so `p23`, built from `p24`, inherits the
   error at exactly half weight — the measured slot-16/slot-15 ratio is
   `2.000000000` on all four objects). Everything else is index-for-index
   upstream.
4. **The weight channel differs too**, at flat slots 8 and 9 (w12, w13), by
   up to **1.875** on a non-unit-weight input; the demo cannot show it
   because every stored input weight is `1.0`. Upstream builds `w12`/`w13`
   from input weights 4/10 and 1/10; our port builds them from 5/11 and 5/6.
5. **No mapping was needed** and none was applied: signature, corner
   convention, row-major 4x6 ordering, units and the row-3 collapse onto
   `set_poles[15]` all match. The two implementations were compared on the
   same flat indices; nothing was permuted to force a match.
6. **Consequence for the cube-corner apex pinch:** on the cube-corner
   fixture the divergence is small in absolute terms (**3.333e-2 mm**, one
   corner-cell pole step of `1/30` mm) but real: the 36-pole corner net moves
   by **5.556e-3 mm** at slots 25, 26 when upstream's member is substituted.
   The **collapsed apex row is byte-identical** between the two members
   (slots 18–23, max |dPole| 0.0), so the degenerate boundary normal that
   `Tests/test_cube_corner_3valent.py` reads at apex-side stations is **not**
   an artefact of the port. The shipped weld's seam numbers were nevertheless
   measured on the divergent member and must be re-read if the port is fixed.

---

## Instruments

| instrument | file | method |
|---|---|---|
| stored known answer | `Resources/Demo_files/Silk_Demo_01.FCStd` | read read-only: `Document.xml` for the objects, the binary `Poles*`/`Weights*` blobs (`uint32` count + `float64` payload) for the numbers. Nothing was opened, recomputed or saved. |
| live upstream reference | `ArachNURBS.ControlGrid64_3_1Grid44` | instantiated on a carrier object in the test document and recomputed — the parity-oracle pattern of `Tests/test_corner_blend.py::_legacy_corner_chain` |
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

`Corner` is an `App::PropertyFloat` holding an integral value 0–3; both sides
name the same corner index (upstream's `if corner == 0: rotate = 0` chain) and
both flatten the rotated 4x4 grid row-major before building the 24-pole
output, so no index mapping is needed.

### Known-answer calibration — upstream's class re-run vs the stored 24

| member | max \|dPole\| (mm) | max \|dWeight\| | poles differing |
|---|---|---|---|
| `ControlGrid64_3_Grid44` | 0.000e+00 | 0.0 | — |
| `ControlGrid64_3_Grid44001` | 0.000e+00 | 0.0 | — |
| `ControlGrid64_3_Grid44002` | 0.000e+00 | 0.0 | — |
| `ControlGrid64_3_Grid44003` | 0.000e+00 | 0.0 | — |

The stored member **is** upstream's own output, so any deviation below is ours.

### Our port vs the stored 24 (raw)

| member | corner | max \|dPole\| (mm) | net diagonal (mm) | rel | mean input cell edge (mm) | dev / edge | pole slots | max \|dWeight\| |
|---|---|---|---|---|---|---|---|---|
| `ControlGrid64_3_Grid44` | 3 | 2.3823927790370045 | 9.957 | 2.39e-1 | 2.008 | 1.186 | 8, 15, 16 | 0.0 |
| `ControlGrid64_3_Grid44001` | 0 | 1.2720659601562707 | 5.425 | 2.34e-1 | 1.204 | 1.057 | 8, 15, 16 | 0.0 |
| `ControlGrid64_3_Grid44002` | 1 | 6.3309534363346289 | 31.775 | 1.99e-1 | 6.742 | 0.939 | 8, 15, 16 | 0.0 |
| `ControlGrid64_3_Grid44003` | 3 | 7.6035673075488015 | 33.885 | 2.24e-1 | 6.603 | 1.152 | 8, 15, 16 | 0.0 |

Flat slot index = `row*6 + col`; slot 8 = p12/w12, slot 9 = w13, slot 15 =
p23, slot 16 = p24. Every other one of the 24 slots is bit-exact on every
object. `slot 16 / slot 15 = 2.000000000` on all four (the halving-chain
signature: `p23 = p24 + (sp[10] − p24)/2` halves the error that `p24` carries).

## 2. Where the two implementations part company (source, term by term)

Both sides: `np.rot90` of the row-major 4x4 by `Corner`, flatten, then the
third strategy. Identical: `p00=sp[12]`, `p01=sp[8]`, `p02=sp[4]`, `p03=sp[1]`,
`p04=sp[2]`, `p05=sp[3]`, `p10=sp[13]`, `p11=sp[9]`, `p13=(sp[5]+sp[6])/2`,
`p14=sp[6]`, `p15=sp[7]`, `p20=sp[14]`, `p21=p20+(sp[10]−p20)/2`,
`p22=p21+(sp[10]−p21)/2`, `p25=sp[11]`, `p30..p35=sp[15]` (the collapsed row),
`w21..w24=sw[10]`, `w30..w35=sw[15]`, and the whole `p0*`/`p1*`/`w0*`/`w1*`
block outside the four lines below.

| output slot | upstream `ArachNURBS.py` | our port `SilkMachinery.py` | on the demo |
|---|---|---|---|
| p12 (flat 8) | `(set_poles[5] + p11)/2`, `p11 = set_poles[9]` | `(p[5] + p[11])*0.5` | differs |
| p24 (flat 16) | `p25 + (set_poles[10] − p25)/2`, `p25 = set_poles[11]` | `p[15] + (p[10] − p[15])*0.5` | differs |
| p23 (flat 15) | `p24 + (set_poles[10] − p24)/2` | same expression, but fed the wrong `p24` | differs (= ½ slot 16) |
| w12 (flat 8) | `(w02 + w21)/2 = (sw[4] + sw[10])/2` | `(w[5] + w[11])*0.5` | invisible (unit weights) |
| w13 (flat 9) | `(w03 + w24)/2 = (sw[1] + sw[10])/2` | `(w[5] + w[6])*0.5` | invisible (unit weights) |

Two notes for whoever fixes this, deliberately left as observations rather
than a verdict:

* upstream's **weight** lines look like a copy-paste from a different index
  map (`w12` from input weights 4/10 is the average of the poles that feed
  `p22`, not `p12`), while our port's `w12` uses its own `p12` poles. Our
  weight expressions are the *mathematically consistent* ones; upstream's are
  the ones the demo's legacy surfaces were actually built with. Since all
  shipped weights are 1.0, nothing on disk distinguishes them.
* the port's `p12` line carries a vestigial
  `if hasattr(p[5]+p[11], "multiply")` guard left over from the transcription.

## 3. The weight channel, measured (synthetic non-unit input)

The demo has unit weights everywhere, so it carries no weight information.
Feeding both sides a synthetic 4x4 net (poles at 10 mm spacing plus a bow,
weights in `[0.25, 5.0]`):

| corner | our w12 (slot 8) | upstream w12 | our w13 (slot 9) | upstream w13 |
|---|---|---|---|---|
| 0 | 0.750000 | 2.000000 | 1.875000 | 2.500000 |
| 1 | 3.750000 | 1.875000 | 3.000000 | 2.875000 |
| 2 | 2.000000 | 0.750000 | 2.625000 | 1.175000 |
| 3 | 1.875000 | 3.750000 | 1.500000 | 1.625000 |

max |dWeight| = **1.875**, weight slots differing: **8, 9**; pole slots
differing: 8, 15, 16 (same signature as the demo), max |dPole| = 10.07 mm.
This is a source-level difference demonstrated on a synthetic input, **not**
demo evidence.

## 4. What it means for the cube-corner apex pinch

`Tests/test_cube_corner_3valent.py` measures the shipped 3-valent corner on
`Tests/cube_corner_model.py`'s unit-cube fixture (three planar patches
meeting at the origin, band splits 0.1, so the ring corner cell spans 0.1 mm
with poles at steps of `1/30` mm). That corner is built from our member.
Substituting upstream's member on the fixture's own member input (patch
`PatchA`, corner 0, not reversed — identified by value against the ring
`SilkCorner.corner_inputs` builds):

| quantity | measurement |
|---|---|
| member input identified | 1 candidate match, patch `PatchA`, corner 0, reversed=False |
| our member vs upstream member | max \|dPole\| **3.333333e-2 mm** = **1.000** corner-cell pole step (`1/30` mm); slots 8, 15, 16 |
| collapsed apex row (slots 18–23) | max \|dPole\| **0.000e+00** — both collapse onto the same cell pole |
| 36-pole corner net, ours vs upstream's member substituted | max \|dPole\| **5.555556e-3 mm** at slots 25, 26 |

Reading:

* the apex pinch **stays** either way. The degenerate boundary normal at the
  apex-side stations is produced by the fully collapsed V3 row, and that row
  is identical in both members (measured 0.0). The port slips are in the
  "tiny spacing" interior points (`p12`, `p23`, `p24`) — upstream's own
  comment calls that spacing the device that "will break G1 slightly. The
  goal is to balance G1 loss versus folding over" — so the fold/pinch
  behaviour is upstream's design decision, not a transcription accident;
* the magnitudes are small **on this fixture only** because its corner cell
  is tiny (0.1 mm on a unit cube). On the demo the same slips move interior
  poles by up to 7.6 mm;
* the seam numbers in `Tests/test_cube_corner_3valent.py` (the non-reversed
  seam `k_gap` 6.132e-03 sampled / 6.888e-15 exact, the degenerate normals,
  the 16/1521 fold) were measured on the **divergent** member. If the port is
  fixed, they must be re-run; this memo gives the bound on how much the
  36-pole net can move (5.6e-3 mm at slots 25/26 on this fixture).

## 5. What this memo does not claim

* **No continuity label.** Nothing here asserts G1/G2 anywhere, and no test
  does either (`test_no_continuity_threshold_in_suite`).
* **Not a verdict on which variant is "correct" for the product.** Upstream is
  the reference *because we are porting it*; whether a future fix should
  reproduce upstream's weights literally or keep the more consistent w12/w13
  is a product decision. Either way the pins in
  `Tests/test_triangular_member_calibration.py` must be updated with the maths.
* **Not a re-measurement of the corner's seam quality.** Only the pole-level
  consequence of the substitution was measured, not its `k_gap`/`g1_deg`.
