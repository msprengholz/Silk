# Demo blend/corner census — `Silk_Demo_01/02/03.FCStd` + `CadDivision_19.FCStd`

**Scope.** Offline census of the four `.FCStd` files in `Resources/Demo_files/`, extracted from git
commit `2eda11a` (read-only; no FreeCAD, no GUI, no test suite, no measurements of my own).
**Method.** `Document.xml` parsed with `python3` + `zipfile` + `re`; the exact Python class of each
scripted object is read from its stored `Proxy` (`<Python module="ArachNURBS" class="..."/>`), *not*
by trimming digits off object names. That distinction matters: object names like
`ControlGrid64_3_Grid44_000` belong to class `ControlGrid64_3_1Grid44`, and names such as
`ControlGrid66_4Sub002`, `SubGrid33_2Grid64`, `CubicSurface_64002` are `class + instance suffix`.
**Provenance.** sha256 of the extracted inputs (raw parser outputs kept in `/tmp/opencode/demo_census/`:
`parse.py`, `resolve.py`, `final_tables.py`, `graphs.json`, `tables.md`, `tables2.md`):

- `Silk_Demo_01.FCStd` — `675326d0cfa3d4aeeaef0a87dbdc53193bac68c41f2ea9e96a3d0a070d93e142` (FreeCAD 0.21R32552)
- `Silk_Demo_02.FCStd` — `7a065bc5ef106bf2b67479159c3cf8f16840b1a6cff1506c53160d68f6e1aedc` (FreeCAD 0.17R11699)
- `Silk_Demo_03.FCStd` — `d7f2b58b4e798fd97ddaa58fda6ae8f17ddc9d495259396c41de22a82eb48d1f` (FreeCAD 0.17R11699)
- `CadDivision_19.FCStd` — `6d2ca4882ac0f287c2b7379ab5a0120badac609af93cb229ecff5e1c39d6600d` (FreeCAD 0.21R32552)

---

## 1. Counts per object TYPE

Counts are per stored `Proxy` class (one row per class; the task's instance-suffix stripping). See the
role column for the raw-vs-class name discrepancy.

| type (exact stored class) | D01 | D02 | D03 | CadDiv | role |
|---|---:|---:|---:|---:|---|
| `ControlGrid44_2EdgeSegments` | 31 | 9 | 34 | 44 | cell: 2-edge rectangular cut of one `CubicSurface_44` |
| `ControlGrid44_EdgeSegment` | 0 | 0 | 0 | 32 | cell: single strip cut of one `CubicSurface_44` |
| `ControlGrid44_4` | 6 | 3 | 10 | 16 | full-face base grid from 4 `ControlPoly4` |
| `ControlGrid64_2Grid44` | 8 | 3 | 12 | 26 | two-patch blend grid (quad ring member) |
| `ControlGrid64_3_1Grid44` | 4 | 0 | 0 | 4 | triangular 4th ring member; stored objects named `ControlGrid64_3_Grid44*` |
| `ControlGrid64_3_Grid44` | 0 | 0 | 0 | 0 | **no such class at 2eda11a** (requested alias; see row above) |
| `ControlGrid66_4Sub` | 4 | 0 | 0 | 6 | four-subgrid corner fill grid (6×6) |
| `CubicSurface_66` | 4 | 0 | 0 | 6 | 4-ring corner output surface |
| `SubGrid33_2Grid64` | 16 | 0 | 0 | 24 | 3×3 corner cell from 2 `ControlGrid64` |
| `SubGrid63_2Surf64` | 0 | 3 | 14 | 0 | 6×3 star cell from 2 `CubicSurface_64` |
| `ControlGrid3Star66_3Sub` | 0 | 1 | 0 | 0 | legacy N=3 star grid; **class absent from `ArachNURBS.py` @2eda11a** |
| `ControlGridNStar66_NSub` | 0 | 0 | 3 | 0 | N-sub star grid (`N` stored = 3, 5, 6) |
| `ControlGridNStar66_StarTrim` | 0 | 0 | 0 | 0 | star-center refinement (test class) — no demo instance |
| `CubicNStarSurface_NStar66` | 0 | 1 | 3 | 0 | star-cup output surface |
| `StarTrim_CubicNStar` | 0 | 0 | 0 | 0 | pinch-repair trim — no demo instance |
| `CubicSurface_44` | 16 | 6 | 20 | 36 | bicubic Bezier base surface |
| `CubicSurface_64` | 12 | 3 | 12 | 30 | 6×4 blend surface |
| `CubicCurve_4` | 48 | 15 | 43 | 69 | Bezier cubic edge curve |
| `ControlPoly4_segment` | 40 | 6 | 27 | 49 | edge poly from a curve segment |
| `ControlPoly4_FirstElement` | 0 | 0 | 27 | 36 | edge poly from a sketch element |
| `ControlPoly4_2N` | 4 | 7 | 0 | 0 | edge poly from 2 node sketches |
| `ControlPoly4_3L` | 8 | 2 | 0 | 0 | edge poly from a 3-line sketch |
| `Point_onCurve` | 30 | 7 | 29 | 40 | point on a `CubicCurve_4` |

_(No other `ControlGrid44*` / `ControlPoly4*` subclass, no `ControlGrid64_4`, `ControlGrid66_4`,
`ControlGridNStar66_StarTrim` object appears in any of the four files.)_

**Per-demo junction summary**

| demo | junctions | base surfaces (in rings) | corner family | outputs |
|---|---|---|---|---|
| D01 | 4 | 5 (`CubicSurface_44` = Front, `001` Top, `002` Right, `003` Bottom, `004` Back) | 4× valence-3 **hard corner, 4-ring**: 3 quad + 1 triangular member | `CubicSurface_66`, `…66001`, `…66002`, `…66003` |
| D02 | 1 | 3 (`S`, `S001`, `S002`) | 1× valence-3 **star cup** (legacy N=3 class) | `CubicNStarSurface_NStar66` |
| D03 | 3 | 10 (20 exist; 10 grouped-only) | 3× **star cup**, N=3 / 5 / 6 (valences 3 / 5 / 6) | `CubicNStarSurface_NStar66`, `…001`, `…002` |
| CadDiv | 6 | 8 in rings (36 exist; 28 grouped + `Part::Mirroring` display sources) | 4× valence-3 hard corner 4-ring (3 quad + 1 tri) + 2× valence-4 4-ring (4 quad) | `CubicSurface_66_000…005` |

D01 corner groups: `Corner_by_subgrids_Front_Top`, `Corner_by_SubGrid_Front_bottom`,
`Corner_by_subgrids_Back_Top`, `Corner_by_SubGrid_Back_bottom`.
D03 corner groups: `_3Star`, `_5Star`, `_6Star`. D02's star is ungrouped. CadDiv corner groups are
generic (`Group084`/`Group085`).

---

## 2. Junction topology — every corner fill resolved to its base surfaces

Ring order is the stored order (`SubGrid_0…3` / `SubList`); each 4-ring `SubGrid33` cell joins two
**adjacent** ring members. Notation: `S`/`Sxxx` = `CubicSurface_44xxx`, `2G44` =
`ControlGrid64_2Grid44`, `T3` = `ControlGrid64_3_1Grid44` (stored object name `ControlGrid64_3_Grid44*`),
`63` = `SubGrid63_2Surf64`. `[a|b]` = the two base surfaces that member consumes. D01 base labels come
from the group `Group048` "Base_Surfaces".

### D01 — 4 × valence-3 hard corners (4-ring: 3 quad + 1 triangular)

| corner fill (class) | cells in stored order → members → base surfaces | ring | valence |
|---|---|---|---|
| `ControlGrid66_4Sub` → `CubicSurface_66` | S0: `2G44[S|S001]` ∥ `2G44002[S|S002]`<br>S1: `2G44002` ∥ `T3[S002]`<br>S2: `T3[S002]` ∥ `2G44003[S001|S002]`<br>S3: `2G44003` ∥ `2G44[S|S001]` | 4 members: 3×2G44 + 1×T3 | **3**: S(Front), S001(Top), S002(Right) |
| `ControlGrid66_4Sub001` → `CubicSurface_66001` | S0: `2G44001[S|S003]` ∥ `2G44004[S003|S002]`<br>S1: `2G44004` ∥ `T3001[S002]`<br>S2: `T3001[S002]` ∥ `2G44002[S|S002]`<br>S3: `2G44002` ∥ `2G44001[S|S003]` | 3×2G44 + 1×T3 | **3**: S(Front), S002(Right), S003(Bottom) |
| `ControlGrid66_4Sub002` → `CubicSurface_66002` | S0: `2G44003[S001|S002]` ∥ `2G44005[S002|S004]`<br>S1: `2G44005` ∥ `2G44006[S001|S004]`<br>S2: `2G44006` ∥ `T3002[S001]`<br>S3: `T3002[S001]` ∥ `2G44003[S001|S002]` | 3×2G44 + 1×T3 | **3**: S001(Top), S002(Right), S004(Back) |
| `ControlGrid66_4Sub003` → `CubicSurface_66003` | S0: `2G44004[S003|S002]` ∥ `T3003[S003]`<br>S1: `T3003[S003]` ∥ `2G44007[S004|S003]`<br>S2: `2G44007` ∥ `2G44005[S002|S004]`<br>S3: `2G44005` ∥ `2G44004[S003|S002]` | 3×2G44 + 1×T3 | **3**: S002(Right), S003(Bottom), S004(Back) |

### D02 — 1 × valence-3 star cup (3 cells)

| corner fill (class) | cells → two `CubicSurface_64` each → base surfaces | ring | valence |
|---|---|---|---|
| `ControlGrid3Star66_3Sub` → `CubicNStarSurface_NStar66` | cell 1: `CubicSurface_64002[S002|S001]` ∥ `CubicSurface_64[S001|S]`<br>cell 2: `CubicSurface_64[S001|S]` ∥ `CubicSurface_64001[S|S002]`<br>cell 3: `CubicSurface_64001[S|S002]` ∥ `CubicSurface_64002[S002|S001]` | 3 star cells (63) | **3**: S, S001, S002 |

### D03 — 3 star cups; N = 3, 5, 6 (cells = ring members)

| corner fill (class) | cells → two `CubicSurface_64` each → base surfaces | ring | valence |
|---|---|---|---|
| `ControlGridNStar66_NSub` (`_3Star`) → `CubicNStarSurface_NStar66` | c1: `CubicSurface_64006[S010|S004]` ∥ `CubicSurface_64003[S004|S003]`<br>c2: `64003` ∥ `CubicSurface_64005[S010|S003]`<br>c3: `64005` ∥ `64006[S010|S004]` | 3 star cells | **3**: S003, S004, S010 |
| `ControlGridNStar66_NSub001` (`_5Star`) → `…66001` | c1: `64004[S003|S002]` ∥ `64003[S004|S003]`<br>c2: `64003` ∥ `64002[S001|S004]`<br>c3: `64002` ∥ `64001[S|S001]`<br>c4: `64001` ∥ `64[S002|S]`<br>c5: `64` ∥ `64004[S003|S002]` | 5 star cells | **5**: S, S001, S002, S003, S004 |
| `ControlGridNStar66_NSub002` (`_6Star`) → `…66002` | c1: `64011[S015|S014]` ∥ `64010[S013|S014]`<br>c2: `64010` ∥ `64008[S013|S012]`<br>c3: `64008` ∥ `64007[S004|S012]`<br>c4: `64007` ∥ `64006[S010|S004]`<br>c5: `64006` ∥ `64009[S010|S015]`<br>c6: `64009` ∥ `64011[S015|S014]` | 6 star cells | **6**: S004, S010, S012, S013, S014, S015 |

### CadDiv_19 — 6 corners (4× valence-3 hard corner, 2× valence-4)

| corner fill (class) | cells → members → base surfaces | ring | valence |
|---|---|---|---|
| `ControlGrid66_4Sub_000` → `CubicSurface_66_000` | S0: `T3_001[S_012]` ∥ `2G44_021[S_012|S_001]`<br>S1: `021` ∥ `2G44_013[S_004|S_001]`<br>S2: `013` ∥ `2G44_020[S_012|S_004]`<br>S3: `020` ∥ `T3_001` | 3×2G44 + 1×T3 | **3**: S_001, S_004, S_012 |
| `ControlGrid66_4Sub_001` → `CubicSurface_66_001` | S0: `T3_000[S_012]` ∥ `2G44_022[S_012|S_008]`<br>S1: `022` ∥ `2G44_017[S_001|S_008]`<br>S2: `017` ∥ `2G44_021[S_012|S_001]`<br>S3: `021` ∥ `T3_000` | 3×2G44 + 1×T3 | **3**: S_001, S_008, S_012 |
| `ControlGrid66_4Sub_002` → `CubicSurface_66_002` | S0: `2G44_013[S_004|S_001]` ∥ `2G44_015[S_001|S_000]`<br>S1: `015` ∥ `2G44_019[S_000|S_005]`<br>S2: `019` ∥ `2G44_014[S_004|S_005]`<br>S3: `014` ∥ `013` | 4×2G44 | **4**: S_000, S_001, S_004, S_005 |
| `ControlGrid66_4Sub_003` → `CubicSurface_66_003` | S0: `2G44_017[S_001|S_008]` ∥ `2G44_016[S_008|S_009]`<br>S1: `016` ∥ `2G44_018[S_000|S_009]`<br>S2: `018` ∥ `2G44_015[S_001|S_000]`<br>S3: `015` ∥ `017` | 4×2G44 | **4**: S_000, S_001, S_008, S_009 |
| `ControlGrid66_4Sub_004` → `CubicSurface_66_004` | S0: `2G44_018[S_000|S_009]` ∥ `2G44_025[S_013|S_009]`<br>S1: `025` ∥ `T3_003[S_013]`<br>S2: `T3_003` ∥ `2G44_024[S_000|S_013]`<br>S3: `024` ∥ `018` | 3×2G44 + 1×T3 | **3**: S_000, S_009, S_013 |
| `ControlGrid66_4Sub_005` → `CubicSurface_66_005` | S0: `2G44_019[S_000|S_005]` ∥ `2G44_024[S_000|S_013]`<br>S1: `024` ∥ `T3_002[S_013]`<br>S2: `T3_002` ∥ `2G44_023[S_005|S_013]`<br>S3: `023` ∥ `019` | 3×2G44 + 1×T3 | **3**: S_000, S_005, S_013 |

---

## 3. Situation → blend type

| # | Situation (valence / topology) | Type combo (build chain) | Demo evidence (object names) | What the type does (quoted fragment, @2eda11a) |
|---|---|---|---|---|
| 1 | V=4, 4 surfaces with paired seams | 4× `ControlGrid64_2Grid44` → 4× `SubGrid33_2Grid64` → `ControlGrid66_4Sub` → `CubicSurface_66` | CadDiv: `ControlGrid66_4Sub_002`, `_003` | `ControlGrid66_4Sub.py` tip: "four surfaces that share a single corner, and have edges matched bewteen them in pairs (2X2 'square' setup of 4 surfaces)" |
| 2 | V=3 hard corner (cube corner); 2 small + 1 large seam blend, fused by a triangular 4th member | 3× `ControlGrid64_2Grid44` + 1× `ControlGrid64_3_1Grid44` → 4× `SubGrid33_2Grid64` → `ControlGrid66_4Sub` → `CubicSurface_66` | D01: `ControlGrid66_4Sub`/`001`/`002`/`003`; CadDiv: `_000`,`_001`,`_004`,`_005` | `ControlGrid66_4Sub`: "three surfaces meeting to form a hard corner (like a cube corner) … 'rolling fillet' corner between the two small blends and the large blend"; `ControlGrid64_3_1Grid44`: "'triangle' grid that 'flows' to eliminate the selected corner … stepping stone" |
| 3 | V=3 soft cup (star), legacy | 3× `SubGrid63_2Surf64` → `ControlGrid3Star66_3Sub` → `CubicNStarSurface_NStar66` | D02: `ControlGrid3Star66_3Sub` + `CubicNStarSurface_NStar66` (ungrouped) | `SubGrid63_2Surf64.py` tip: "Input for ControlGridNStar66 to blend three or more blended edges meeting at a corner"; `ControlGrid3Star66_3Sub` has no tip at 2eda11a and its ArachNURBS class is gone (§5) |
| 4 | V=3…6 soft cup (scaling star) | N× `SubGrid63_2Surf64` → `ControlGridNStar66_NSub` → `CubicNStarSurface_NStar66` | D03: `_3Star` N=3, `_5Star` N=5, `_6Star` N=6 (stored `N` = 3/5/6) | `ControlGridNStar66.py` tip: "three or more SubGrid63_2Surf64 … corner where three or more CubicSurface_64 meet at a corner"; `CubicNStarSurface_NStar66`: "Used for filling the corner of blended Silk surfaces" |
| 5 | pinch repair of a star cup | `CubicNStarSurface_NStar66` → `StarTrim_CubicNStar` | none in these files (0 instances) — tooltip only | `StarTrim_CubicNStar.py`: "Useful for eliminating pinch in poor corner geometry, and can be patched with a standard Filling Surface" |
| 6 | star-center refinement (alternative cup path) | `StarTrim_CubicNStar` → `ControlGridNStar66_StarTrim` | none in these files (0 instances) | `ArachNURBS.py:9407`: "quick and dirty test for star center refinement … uses a list of subgrids within the single linked StarTrim, instead of a linklist" |
| 7 | single seam between two surfaces (no corner) | 2 cells (`ControlGrid44_EdgeSegment` or `ControlGrid44_2EdgeSegments`) → `ControlGrid64_2Grid44` → `CubicSurface_64` | D01: 8× `ControlGrid64_2Grid44`; D03: 12×; CadDiv: 32× `ControlGrid44_EdgeSegment` + 26× `ControlGrid64_2Grid44` | `ControlGrid64_2Grid44.py`: "Primary use is to blend the edge of two surfaces segmented with ControlGrid44_EdgeSegment … Input for CubicSurface_64" |
| 8 | base face (no blend yet) | 4× `ControlPoly4*` → `ControlGrid44_4` → `CubicSurface_44` | all four files | `Silk_tooltips.py` `CubicSurface_44`: "the basic 'building block' surface that complex models are based on"; `ControlGrid44_2EdgeSegments`: "Used in pairs to create ControlGrid64_2Grid44 to blend edges of CubicSurface_44" |

**Wizard implication (already recorded upstream of this census).** Per `AGENTS.md` and
`docs/research/silk-corner-type-taxonomy.md` @2eda11a: the current corner stage is scoped to the
D01 family (situation #2 — the 4-ring hard corner with the triangular 4th member built in), while the
star family (#3/#4) is deferred to a later subproject with D02/D03. `ControlGridNStar66_NSub` has no
tooltip text at 2eda11a (`GetResources` returns `MenuText` only); its AN property docs are
`SubList` = "Reference Sub Grids", `N` = "N".

---

## 4. `CadDivision_19.FCStd` — is it a Silk demo?

**Yes, but of the upstream ArachNURBS generation — not one of the three numbered `Silk_Demo_*` and not
built with the current Silk object architecture.** Evidence from the file: 418 objects with
`module="ArachNURBS"` (same library as D01–D03), doc label `CadDivision_19`, and Silk-labelled
viewset objects (`Silk_Wb`, `Viewset_Link_Silk_face_Cubicurface_4s`,
`Viewset_Link_Silk_half_blend_*`, `Viewset_Link_Silk_full_blend`). It also contains 165 `App::Link`,
72 `Part::Mirroring` and 148 `Render` `View` objects (display scaffolding). No `Silk*` (v1) object
classes exist in any of the four files — all were saved before the `Edge → Patch → Blend` pipeline
existed (also true of D01–D03).

---

## 5. Anomalies / cannot verify

1. **D02's star corner cannot be rebuilt from the current module as saved.** The stored Proxy is
   `module="ArachNURBS" class="ControlGrid3Star66_3Sub"`, but no `ControlGrid3Star66_3Sub` class
   exists in `ArachNURBS.py` at 2eda11a (only a same-named *command* module that itself calls the
   missing `AN.ControlGrid3Star66_3Sub`, and a test module
   `ControlGridNStar66_NSub_by_inheritance_test.py` where it subclasses `ControlGridNStar66_NSub`).
   The stored property set of the D02 object (`N`=3, `Poles_0..2`, `Weights_0..2`, `SubList`) matches
   that inheritance-test generation, not the current AN class (`StarGrid`, `SquishDiag4`, no
   `Poles_i`/`Weights_i`). What FreeCAD does with an unresolvable Proxy on load is **UNVERIFIED**
   (no GUI run allowed); statically the class is absent.
2. **Requested type name drift**: `ControlGrid64_3_Grid44` is not a class at 2eda11a; the class is
   `ControlGrid64_3_1Grid44`, while D01/CadDiv instances are named `ControlGrid64_3_Grid44*`
   (CadDiv: `…_000` style). Counted above under the class, not the name.
3. **Extra grouped-only surfaces** (not consumed by any grid/blend/corner): D01 has 11 extra
   `CubicSurface_44` inside groups `*_Segment_surfaces` (plus 5 `App::Link` + 5 `Part::Mirroring`
   display copies of the 5 base faces); D02 has 3 in `Group057`
   "CubicSurface44_base_segments_main_sections"; D03 has 10 in `Group013` "main sections";
   CadDiv has 28, each referenced only by a display group and a `Part::Mirroring` copy. These are
   preserved/segment surfaces (tooltip: "re-create the portions of the original surface that are to be
   preserved and not blended"), not junction members — count them as display evidence, not topology.
4. **`StarTrim_CubicNStar` and `ControlGridNStar66_StarTrim` have zero instances in all four files**;
   their behaviour here is documented only (Table 3 rows 5–6). Marked accordingly — no claim about
   whether these demos were ever saved with them.
5. Valences/junction counts above come from resolving stored links (method described in §2, raw output
   kept). No geometry was evaluated, so e.g. a "valence 3" statement means *three distinct
   `CubicSurface_44` leave objects are linked by the ring*, not that the faces geometrically meet.

## 6. Measurement rule

This census contains **no measurements of my own** — no `k_gap`, no `g1_deg`, no error floors. Where
continuity numbers are quoted elsewhere they must carry their owners: the reference corner
(measured on `Resources/Demo_files/Silk_Demo_01.FCStd`) is #97's result (C0 exact, G1 ≤ 0.48°, not G2,
`k_gap` ≤ 3.1e-2 /mm); what G2 would take is #100's (control-net solve: `k_gap` 6.0e-17 on compatible
neighbours, 7.1e-3 /mm attainable on this demo's legacy neighbours; FreeCAD `Surface::Filling` order-2
`k_gap` 1.7e-1 vs order-1 8.2e-2). Quoted here only as attribution, not re-measured.
