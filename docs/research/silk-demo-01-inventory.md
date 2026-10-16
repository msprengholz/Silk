# Silk Demo 01 — inventory (stored object graph)

Source: `Resources/Demo_files/Silk_Demo_01.FCStd`, sha256
`675326d0cfa3d4aeeaef0a87dbdc53193bac68c41f2ea9e96a3d0a070d93e142`
(FreeCAD 0.21R32552). The file is opened **read-only** for cross-checks and
never re-saved.

**This is Demo 01's own graph** — *(correction, #98 review: the first version
of this file inventoried `Resources/Test_files/Silk_Workflow.FCStd` — 9
sketches, 7 Edges, 2 Patches, 1 Blend — which is a different document. Nothing
below is carried over from it.)*

Method. The class/link graph is parsed offline from the file's `Document.xml`
(`zipfile` + `re`; the census technique — no FreeCAD needed). Raw parser
outputs are kept in `/tmp/opencode/demo01_rework/` (`graph2.json`,
`analysis.txt`, `analysis2.txt`). Geometry claims (endpoints, u=0.5 points)
are live measurements: the demo was opened read-only in FreeCAD 1.1 and the
Silk Edges were built from copies of its sketches
(`/tmp/opencode/demo01_rework/probe_gui5.py`, `probe_gui6.py`; the rebuild
test reproduces the same numbers). Every number below carries which
instrument produced it; anything not measured is marked **UNVERIFIED**.

Associated research: the four-file census (`silk-demo-blend-census.md`), the
corner taxonomy (`silk-corner-type-taxonomy.md`), the junction table
(`silk-demo-01-junction-table.md`).

---

## 1. Raw counts (stored `Proxy` classes)

| class | count | role |
|---:|---|---|
| `Sketch` (`Sketcher::SketchObject`) | 29 | inputs, `Sketch014`..`Sketch045` |
| `ControlPoly4_3L` | 8 | edge poly from one 3-line sketch |
| `ControlPoly4_2N` | 4 | edge poly from two node sketches (circle+line each) |
| `ControlPoly4_segment` | 40 | edge poly = a sub-interval of another curve |
| `CubicCurve_4` | 48 | 12 physical curves + 36 sub-curves (see §3) |
| `Point_onCurve` | 30 | parameters on those curves |
| `ControlGrid44_4` | 6 | full-face base grids: 5 ring faces + 1 duplicate |
| `ControlGrid44_2EdgeSegments` | 31 | 3x3 corner cells cut from a base surface by 2 curves |
| `ControlGrid64_2Grid44` | 8 | two-cell seam blends (quad ring members) |
| `ControlGrid64_3_1Grid44` | 4 | triangular 4th ring members (stored names `ControlGrid64_3_Grid44*`) |
| `SubGrid33_2Grid64` | 16 | 3x3 cell joining two `ControlGrid64` objects |
| `ControlGrid66_4Sub` | 4 | 6x6 corner fill grids |
| `CubicSurface_44` | 16 | 5 ring base surfaces + 11 single-cell "segment surfaces" |
| `CubicSurface_64` | 12 | 8 seam-blend outputs + 4 triangular-member outputs |
| `CubicSurface_66` | 4 | 4-ring corner outputs |

Plus display scaffolding: 87 `App::DocumentObjectGroup`, 5 `App::Link`,
5 `Part::Mirroring` (the modelled half is mirrored through the symmetry
plane), and no `Silk*` (v1) classes at all — this file predates the
`Edge → Patch → Blend` pipeline.

## 2. The chain

```
29 sketches
  → 8× ControlPoly4_3L + 4× ControlPoly4_2N          (edge polys)
    → 48× CubicCurve_4                                (12 physical + 36 sub-curves
       → 40× ControlPoly4_segment                       cut by ControlPoly4_segment)
    → 6× ControlGrid44_4                              (base grids: 5 ring faces + 1 dup)
      → 31× ControlGrid44_2EdgeSegments               (corner cells)
        → 8× ControlGrid64_2Grid44 + 4× ControlGrid64_3_1Grid44   (seam members + tri members)
          → 16× SubGrid33_2Grid64
            → 4× ControlGrid66_4Sub
              → 4× CubicSurface_66                     (the four corner fills)
```

`ControlGrid44_4004_Back` is stored but **no surface consumes it** (only the
`Base_Grids` display group): it is a reordered duplicate of the modelled Back
grid `ControlGrid44_4006_Back` (which builds `CubicSurface_44004`). The ring
uses `_4006` — verified by following `CubicSurface_44004.Grid` in the link
sweep.

### The modelled half and the symmetry plane

The demo models **half** the shape: the rib curves run from one hoop edge
(mirrored side), through the symmetry plane at **u = 0.5**, to the modelled
hoop edge at **u = 1**; the five base surfaces use only the **`u ∈ [0.5, 1]`
half** of every rib (one `ControlPoly4_segment` piece, shared by the two
faces it sits between) and the mirror supplies the other half. Live
measurement of the whole-sketch Silk Edges built from copies (probe 5):

| rib sketch | u=0 | u=0.5 (= symmetry-plane corner) | u=1 |
|---|---|---|---|
| `Sketch020` Front_Bottom_Rib | (20, 75, 0) | **(0, 0, 0)** | (20, −75, 0) |
| `Sketch022` Front_Top_Rib | (20, 85, 50) | **(0, 0, 50)** | (20, −85, 50) |
| `Sketch024` Back_Bottom_Rib | (150, 45, 0) | **(170, 0, 0)** | (150, −45, 0) |
| `Sketch026` Back_Top_Rib | (185, 50, 60) | **(185, 0, 70)** | (185, −50, 60) |

The u=0.5 points are exactly the cross-section loop's corners
(`Sketch015/016/017/018` endpoints). This is what makes the demo's half-rib
faces close while whole-sketch ribs do not (§6).

## 3. Sketch → ControlPoly4 → CubicCurve

Physical curves are the 12 `CubicCurve_4` objects whose `Poly` is a
`ControlPoly4_3L`/`_2N`; the other 36 are **sub-curves** whose `Poly` is a
`ControlPoly4_segment` cutting a physical curve (or another sub-curve). The
u-interval of a sub-curve is composed through the segment's two
`Point_onCurve` parameters (one is expression-linked to another,
`Point_onCurve029 → Point_onCurve019.u`).

### 3.1 The 16 sketches that feed physical curves

| sketch | feeds | physical curve | interval |
|---|---|---|---|
| `Sketch015` | `ControlPoly4_3L` | `CubicCurve_4` Front cross-section (0,0,0)→(0,0,50) | full |
| `Sketch016` | `ControlPoly4_3L003` | `CubicCurve_4003` Top cross-section (0,0,50)→(185,0,70) | full |
| `Sketch017` | `ControlPoly4_3L002` | `CubicCurve_4002` Back cross-section (185,0,70)→(170,0,0) | full |
| `Sketch018` | `ControlPoly4_3L001` | `CubicCurve_4001` Bottom cross-section (0,0,0)→(170,0,0) | full |
| `Sketch020` | `ControlPoly4_3L004` | `CubicCurve_4004` Front_Bottom_Rib | full (faces use [0.5,1]) |
| `Sketch022` | `ControlPoly4_3L005` | `CubicCurve_4005` Front_Top_Rib | full (faces use [0.5,1]) |
| `Sketch024` | `ControlPoly4_3L006` | `CubicCurve_4006` Back_Bottom_Rib | full (faces use [0.5,1]) |
| `Sketch026` | `ControlPoly4_3L007` | `CubicCurve_4007` Back_Top_Rib | full (faces use [0.5,1]) |
| `Sketch036`+`Sketch037` | `ControlPoly4_2N001` | `CubicCurve_4009` Front_Right hoop edge | full |
| `Sketch038`+`Sketch039` | `ControlPoly4_2N003` | `CubicCurve_4011` Bottom_Right hoop edge | full |
| `Sketch042`+`Sketch045` | `ControlPoly4_2N004` | `CubicCurve_4012` Top_Right hoop edge | full |
| `Sketch032`+`Sketch035` | `ControlPoly4_2N` | `CubicCurve_4008` Back_Right hoop edge | full |

### 3.2 The six base grids (`ControlGrid44_4`) — boundary polys

Each row is one face's boundary cycle, stored order `Poly0..Poly3`. A cell
reads `class sketch(es) [stored interval] → curve`: `seg` = a
`ControlPoly4_segment` cut **from** that `CubicCurve_4` (its `NL_Curve`); a
`3L`/`2N` poly **is** the `Poly` link of that `CubicCurve_4`. Intervals are
the segment's own `Point_onCurve` parameters; `full` means the whole curve.

| grid (face) | Poly0 | Poly1 | Poly2 | Poly3 |
|---|---|---|---|---|
| `ControlGrid44_4_Front` | seg 020 [0.5,1] → `CubicCurve_4004` | 2N 036+037 → `4009` | seg 022 [0.5,1] → `4005` | 3L 015 → `CubicCurve_4` |
| `ControlGrid44_4001_Top` | seg 022 [0.5,1] → `4005` | 2N 042+045 → `4012` | seg 026 [0.5,1] → `4007` | 3L 016 → `4003` |
| `ControlGrid44_4002_Right` | 2N 036+037 → `4009` | 2N 038+039 → `4011` | 2N 032+035 → `4008` | 2N 042+045 → `4012` |
| `ControlGrid44_4005_Bottom` | 2N 038+039 → `4011` | seg 020 [0.5,1] → `4004` | 3L 018 → `4001` | seg 024 [0.5,1] → `4006` |
| `ControlGrid44_4006_Back` (ring) | 3L 017 → `4002` | seg 026 [0.5,1] → `4007` | 2N 032+035 → `4008` | seg 024 [0.5,1] → `4006` |
| `ControlGrid44_4004_Back` (unused dup) | seg 024 [0.5,1] → `4006` | 2N 032+035 → `4008` | seg 026 [0.5,1] → `4007` | 3L 017 → `4002` |

The 6th row is the unused duplicate from §2. So the five modelled faces are
bounded by **12 distinct curves = 12 whole-sketch-equivalent inputs** (4
cross-section edges + 4 ribs + 4 hoop edges) — but the ribs enter each face
as a **half** (§2).

### 3.3 The 13 sketches that feed no `ControlPoly4`

`Sketch014` (symmetry-plane profile — other sketches reference its edges as
`ExternalGeometry`; measured link sweep) and 12 sketches that sit only in
display groups: `Sketch019/021/023/025` (grouped beside the used rib
`Sketch020/022/024/026` — labelled `*_De_Casteljau_Sketch`, role
**UNVERIFIED**), and `Sketch030/031`, `Sketch033/034`, `Sketch040/041`,
`Sketch043/044` (the `*_3DN` node triples beside the used 2N nodes
`Sketch032`, `Sketch035`, `Sketch042`, `Sketch045`; the unused members' role
is **UNVERIFIED**).

## 4. The shared seams (`ControlGrid64_2Grid44`, 8)

Each seam member joins two corner cells (`ControlGrid44_2EdgeSegments`), one
per face; the cell pair's common curve is the seam-cut curve, a sub-interval
of a physical curve. `seam` column = measured common curve and its composed
interval; `cell curves` = the two curves bounding that cell, each written as
`<sketch(es)> [interval]` on the physical curve (2N sketches cited together;
all values composed through the segment/point chain).

| seam member | faces | seam curve (sketch, interval) | cell of face A (a / b) | cell of face B (a / b) |
|---|---|---|---|---|
| `ControlGrid64_2Grid44` | Front\|Top | `Sketch022` [0.5, 0.75] | `…001`: 022 [0.5–0.75] / 036+037 [0.5–1.0] | `…004`: 022 [0.5–0.75] / 042+045 [0.1–1.0] |
| `ControlGrid64_2Grid44001` | Front\|Bottom | `Sketch020` [0.5, 0.75] | `…013`: 020 [0.5–0.75] / 036+037 [0.8–1.0] | `…018`: 020 [0.5–0.75] / 038+039 [0.1–1.0] |
| `ControlGrid64_2Grid44002` | Front\|Right | `Sketch036+037` [0.5, 0.8] | `…002`: 022 [0.75–1.0] / 036+037 [0.5–0.8] | `…012`: 042+045 [0.075–1.0] / 036+037 [0.5–0.8] |
| `ControlGrid64_2Grid44003` | Top\|Right | `Sketch042+045` [0.1, 0.8] | `…005`: 022 [0.75–1.0] / 042+045 [0.1–0.8] | `…007`: 042+045 [0.1–0.8] / 036+037 [0.375–1.0] |
| `ControlGrid64_2Grid44004` | Bottom\|Right | *(no common cell curve)* | `…019`: 020 [0.75–1.0] / 038+039 [0.1–0.8] | `…015`: 036+037 [0.85–1.0] / 042+045 [0.1–0.8] |
| `ControlGrid64_2Grid44005` | Right\|Back | `Sketch032+035` [0.375, 0.85] | `…027`: 032+035 [0.375–0.85] / 042+045 [0.8–1.0] | `…031`: 032+035 [0.375–0.85] / 026 [0.62–1.0] |
| `ControlGrid64_2Grid44006` | Top\|Back | `Sketch026` [0.5, 0.62] | `…022`: 042+045 [0.95–1.0] / 026 [0.5–0.62] | `…029`: 026 [0.5–0.62] / 032+035 [0.375–1.0] |
| `ControlGrid64_2Grid44007` | Back\|Bottom | `Sketch024` [0.5, 0.62] | `…030`: 032+035 [0.85–1.0] / 024 [0.5–0.62] | `…025`: 024 [0.5–0.62] / 038+039 [0.95–1.0] |

`ControlGrid64_2Grid44004` shares no whole cell curve: its two cells are cut
by *different* sub-curves (Bottom's `…019.a` = 020[0.75,1] and Right's
`…015.a` = 036+037[0.85,1]); the blend pairing there is geometric, and which
curves correspond is **UNVERIFIED** offline. All interval values are composed
through the segment/point chain by the offline parser; 2N sketches are cited
together as `036+037` etc.

## 5. The triangular 4th members (`ControlGrid64_3_1Grid44`, 4)

| member | `Corner` | cell (face) | cell's curves | consumer ring |
|---|---|---|---|---|
| `ControlGrid64_3_Grid44` | 3 | `…008` (Right) | 042+045 [0.075–0.1] / 036+037 [0.375–0.5] | J1 (Front/Top/Right) |
| `ControlGrid64_3_Grid44001` | 0 | `…016` (Right) | 036+037 [0.8–0.85] / 042+045 [0.075–0.1] | J2 (Front/Right/Bottom) |
| `ControlGrid64_3_Grid44002` | 1 | `…023` (Top) | 042+045 [0.8–0.95] / 026 [0.62–0.75] | J3 (Top/Right/Back) |
| `ControlGrid64_3_Grid44003` | 3 | `…026` (Bottom) | 038+039 [0.8–0.95] / 024 [0.62–0.75] | J4 (Right/Bottom/Back) |

## 6. Edge-equivalent mapping — what a Silk rebuild would need

A rebuild through `SilkWorkflowOps` (spec: whole sketches only — `3L`, `2N`,
plan+elevation) maps the 12 distinct curves onto 12 Edges; the demo's own
boundary pieces are **not** all reproducible, because four of them are
half-ribs:

| Edge (rebuild name) | sketches consumed | demo role | measured endpoints (u=0 → u=1) |
|---|---|---|---|
| `E_front_out` | `Sketch015` | Front cross-section | (0,0,0) → (0,0,50) |
| `E_top_out` | `Sketch016` | Top cross-section | (0,0,50) → (185,0,70) |
| `E_back_out` | `Sketch017` | Back cross-section | (185,0,70) → (170,0,0) |
| `E_bottom_out` | `Sketch018` | Bottom cross-section | (0,0,0) → (170,0,0) |
| `E_rib_FB` | `Sketch020` | Front↔Bottom rib, faces use [0.5,1] | (20,75,0) → (20,−75,0), mid (0,0,0) |
| `E_rib_FT` | `Sketch022` | Front↔Top rib, faces use [0.5,1] | (20,85,50) → (20,−85,50), mid (0,0,50) |
| `E_rib_BkB` | `Sketch024` | Bottom↔Back rib, faces use [0.5,1] | (150,45,0) → (150,−45,0), mid (170,0,0) |
| `E_rib_TBk` | `Sketch026` | Top↔Back rib, faces use [0.5,1] | (185,50,60) → (185,−50,60), mid (185,0,70) |
| `E_right_FR` | `Sketch036`+`Sketch037` | Front↔Right hoop edge | (20,−85,50) → (20,−75,0) |
| `E_right_BR` | `Sketch038`+`Sketch039` | Bottom↔Right hoop edge | (20,−75,0) → (150,−45,0) |
| `E_right_TR` | `Sketch042`+`Sketch045` | Top↔Right hoop edge | (20,−85,50) → (185,−50,60) |
| `E_right_BkR` | `Sketch032`+`Sketch035` | Back↔Right hoop edge | (185,−50,60) → (150,−45,0) |

**Measured rebuild outcome** (`Tests/test_demo01_rebuild.py`; the refusal
texts are pinned there):

- all **12 Edges build**, match the measured mapping, and are
  **pole-identical to the demo's stored `ControlPoly4` objects** (max delta
  `0.0`, asserted in the test). `check_edge` is green except the
  Bottom_Right hoop edge, whose E2 pole-spacing deviation (`p2->p3` 70.711
  > 1.05 × `p2->p0` 63.246) is **inherited from the demo's own legacy
  `ControlPoly4_2N003`** — the same inequality holds on the stored poles,
  which the test verifies;
- the **Right** face (end cap — its four boundary curves really are whole
  sketches) rebuilds as one Patch and passes `check_patch`;
- the four other `create_patch` calls are **refused**: “do not close a loop
  (… meets only 0 of the other 3 edges …)” — the outer cross-section edge
  shares no corner with the whole-rib edges, because the demo's faces are
  bounded by rib **halves**. Reproducing them needs an Edge that can be
  trimmed to a sketch sub-interval (`u ∈ [0.5, 1]`), which the current Edge
  vocabulary has no property for;
- with one patch there are **no seams** (`seam_inventory` empty), no blend
  can be created (`create_blend_by_edge` refuses: “is a boundary of … only”),
  and no junction can be attempted (`create_corner_blend` refuses the empty
  ring). The corner stage is unreachable from whole sketches on this demo.

## 7. UNVERIFIED / caveats

1. The role of `Sketch014`'s profile and of the 12 multi-member groups'
   unused sketches (`019/021/023/025`, `030/031`, `033/034`, `040/041`,
   `043/044`) is not established — labels only (`*_De_Casteljau_Sketch`,
   `*_3DN`). No rule was invented for them.
2. The `ControlGrid64_2Grid44004` blend pairing (no shared cell curve) is
   **UNVERIFIED** (geometric pairing not evaluated).
3. The stored `Shape` properties of the legacy objects read back as control
   **polygon legs** when sampled naively (e.g. `ControlPoly4_3L_Front.Shape`
   ends at a leg point, not the curve end). All endpoint measurements in this
   file come from freshly built Silk Edges, not from stored `Shape`.
4. No geometry was evaluated for the census-style link tables — “face”,
   “seam” etc. are the stored graph's own vocabulary.
5. No continuity number is produced here. Where quoted elsewhere they belong
   to #97/#100 and describe synthetic/reference rings, not this demo's four
   junctions — see `silk-demo-01-junction-table.md` for the labelled
   citations.
