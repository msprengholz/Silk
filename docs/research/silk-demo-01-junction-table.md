# Silk Demo 01 — junction table

The four corner fills of `Resources/Demo_files/Silk_Demo_01.FCStd`
(sha256 `675326d0…`), resolved from the stored link graph. **Instrument and
provenance:** offline parse of the file's `Document.xml` (`zipfile` + `re`,
the census technique), re-derived for this table and in agreement with
`silk-demo-blend-census.md` §2 (raw parser outputs kept in
`/tmp/opencode/demo01_rework/`). These are **graph facts** — three distinct
base `CubicSurface_44` leave objects linked by the ring — not geometric
measurements, and no continuity number was measured on any junction.

Notation: `S`/`S003…` = `CubicSurface_44` instances (Front / Top / Right /
Bottom / Back), `2G44xxxx` = `ControlGrid64_2Grid44` (stored name suffix),
`T3xx` = `ControlGrid64_3_1Grid44` (stored name `ControlGrid64_3_Grid44*`).
Ring order is the stored `SubGrid_0..3` order; `∥` joins the two members of
one `SubGrid33_2Grid64` cell.

| Junction | Faces (valence 3) | Ring (stored order) | Triangular 4th member | Fill → output | Corner group |
|---|---|---|---|---|---|
| **J1** | Front, Top, Right | S0: `2G44[S(Front)‖S001(Top)]` ∥ `2G44002[S(Front)‖S002(Right)]`<br>S1: `2G44002` ∥ `T3_000[S002(Right)]`<br>S2: `T3_000` ∥ `2G44003[S001(Top)‖S002(Right)]`<br>S3: `2G44003` ∥ `2G44[S(Front)‖S001(Top)]` | `ControlGrid64_3_Grid44` (Corner 3; cell `…008` on Right) | `ControlGrid66_4Sub` → `CubicSurface_66` | `Corner_by_subgrids_Front_Top` |
| **J2** | Front, Right, Bottom | S0: `2G44001[S(Front)‖S003(Bottom)]` ∥ `2G44004[S003(Bottom)‖S002(Right)]`<br>S1: `2G44004` ∥ `T3_001[S002(Right)]`<br>S2: `T3_001` ∥ `2G44002[S(Front)‖S002(Right)]`<br>S3: `2G44002` ∥ `2G44001[S(Front)‖S003(Bottom)]` | `ControlGrid64_3_Grid44001` (Corner 0; cell `…016` on Right) | `ControlGrid66_4Sub001` → `CubicSurface_66001` | `Corner_by_SubGrid_Front_bottom` |
| **J3** | Top, Right, Back | S0: `2G44003[S001(Top)‖S002(Right)]` ∥ `2G44005[S002(Right)‖S004(Back)]`<br>S1: `2G44005` ∥ `2G44006[S001(Top)‖S004(Back)]`<br>S2: `2G44006` ∥ `T3_002[S001(Top)]`<br>S3: `T3_002` ∥ `2G44003[S001(Top)‖S002(Right)]` | `ControlGrid64_3_Grid44002` (Corner 1; cell `…023` on Top) | `ControlGrid66_4Sub002` → `CubicSurface_66002` | `Corner_by_subgrids_Back_Top` |
| **J4** | Right, Bottom, Back | S0: `2G44004[S003(Bottom)‖S002(Right)]` ∥ `T3_003[S003(Bottom)]`<br>S1: `T3_003` ∥ `2G44007[S004(Back)‖S003(Bottom)]`<br>S2: `2G44007` ∥ `2G44005[S002(Right)‖S004(Back)]`<br>S3: `2G44005` ∥ `2G44004[S003(Bottom)‖S002(Right)]` | `ControlGrid64_3_Grid44003` (Corner 3; cell `…026` on Bottom) | `ControlGrid66_4Sub003` → `CubicSurface_66003` | `Corner_by_SubGrid_Back_bottom` |

## Continuity — what is measured, on what, and nothing more

- **No per-junction `k_gap` exists.** Nothing in this research measured the
  four stored junctions' seams. The unit is **/mm** (a curvature difference;
  the `g/m` that appeared in the first version of this table was a typo —
  the census and #97 write `/mm`).
- The numbers in circulation are **synthetic/reference-ring** numbers and
  are cited only as such:
  - **#97** (reference corner, `Silk_Demo_01` legacy neighbours as the ring
    reference geometry): C0 exact, G1 ≤ 0.48°, **not G2**, `k_gap` ≤
    3.1e-2 /mm.
  - **#100** (what G2 would take, control-net solve on the same reference
    geometry): exact `k_gap` 6.0e-17 on compatible neighbours; attainable
    7.1e-3 /mm on the demo's legacy neighbours; FreeCAD `Surface::Filling`
    order-2 `k_gap` 1.7e-1 vs order-1 8.2e-2 — **not** a per-junction
    reading of these files.
- **These junctions were not rebuilt**, so no corner object exists to
  measure: a whole-sketch rebuild through `SilkWorkflowOps` refuses the four
  ring faces at `create_patch` (their boundaries are half-ribs; see
  `silk-demo-01-inventory.md` §6 and `Tests/test_demo01_rebuild.py`). Only
  the Right end cap rebuilds, and it is a face, not a junction.
- `twist_gap` is not reversal-invariant (#101): only non-reversed
  correspondences count as evidence. No `twist_gap` is quoted here because
  nothing was measured.
- No continuity label is asserted anywhere (the suite guards this:
  `test_no_continuity_threshold_in_suite`).
