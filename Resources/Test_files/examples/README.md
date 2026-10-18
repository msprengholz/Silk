# Silk example documents — sketch-only click-through fixtures

These are the **durable examples** (ticket #56) for the human-test rounds
and for deciding the most intuitive tools / wizard approach (#48).

Each `.FCStd` in this directory contains **only the input geometry** — the
ControlPoly4 3-line boundary sketches. There are **no Edge, Patch or Blend
objects** in any of them. A human (or an agent) opens one and clicks
through the three commands — **Edge → Patch → Blend** — to rebuild the
whole model by hand, with the "target" line below as the goal.

The file **names** and the **sketch names inside** carry the intent, so
the topology is readable without opening the binary `.FCStd`. The sketch
names are the contract the fixture tests
(`Tests/test_example_documents.py`) assert — and for
`SketchOnly_Demo01Subset.FCStd` that contract is *derived from the source
demo file at test time*, not hand-written (#98 review).

The set is a **progression**, not a single shape:
a simple closed quad → a two-patch chain with a blendable seam → a four
-corner case (plus a bonus cube corner).

---

## SketchOnly_Quad.FCStd — the simplest patch (start here)

- **4 sketches**: `SK_Edge_Bottom`, `SK_Edge_Right`, `SK_Edge_Top`,
  `SK_Edge_Left` — a closed square in the XY plane (`Z=0`), each side a
  single 3-line ControlPoly4 boundary.
- **Which edges go together**: each sketch is one Edge; the four Edges
  close a loop (Bottom→Right→Top→Left).
- **Intended build**: the `Edge -> Patch -> Blend` tutorial case.
  1. Turn each of the 4 sketches into an Edge.
  2. Select all 4 Edges → one Patch.
  3. Nothing to blend (single patch) — this is the clean, unambiguous
     first example, so click-through #1 should end with **1 patch, 0
     blends**.

## SketchOnly_TwoPatches.FCStd — the blend path

- **7 sketches**: one shared seam `SK_Edge_Shared`, plus
  `SK_Edge_A_Bottom/Left/Top` (patch A's other three sides) and
  `SK_Edge_B_Bottom/Right/Top` (patch B's other three sides).
- **Which edges go together** (two patches, one shared edge):
  - **Patch A** = Shared + A_Bottom + A_Left + A_Top
  - **Patch B** = Shared + B_Bottom + B_Right + B_Top
- **Which seams should blend**: the **Shared** edge between Patch A and
  Patch B is the one blendable seam.
- **Intended build**: the blend tutorial case.
  1. Turn each of the 7 sketches into an Edge (the Shared sketch becomes
     the edge both patches use).
  2. Build Patch A from {Shared, A_Bottom, A_Left, A_Top}.
  3. Build Patch B from {Shared, B_Bottom, B_Right, B_Top}.
  4. Blend Patch A and Patch B → the Shared seam is auto-detected as the
     shared edge → **1 blend**. Click-through #2 should end with
     **2 patches, 1 blend**.

## SketchOnly_Corner4.FCStd — the four-corner case

- **12 sketches**: 4 seams `SK_Seam_B/R/T/L` (the edges radiating from
  the corner) + 8 quadrant-boundary sketches `SK_Q<BR/TR/TL/BL>_<A/B>`
  (two per quadrant).
- **Which edges go together** (each sketch is one Edge; the ground-truth
  `SketchOnly_Corner4_withPatches.FCStd` uses them as):
  - **QBR** = Seam_B + QBR_A + QBR_B + Seam_R
  - **QTR** = Seam_R + QTR_A + QTR_B + Seam_T
  - **QTL** = Seam_T + QTL_A + QTL_B + Seam_L
  - **QBL** = Seam_L + QBL_A + QBL_B + Seam_B
- **Which seams should blend**: the four interior seams `Seam_B/R/T/L`,
  each shared by two adjacent quadrant patches.
- **Intended build**: the multi-seam / corner case, for later rounds.
  1. Turn all 12 sketches into Edges.
  2. Build the 4 quadrant patches (each is two seams + the two `_A`/`_B`
     sketches of its quadrant).
  3. Blend the 4 interior seams — the 4-corner junction resolves via the
     corner blend object. Click-through should end with **4 patches, 4
     blendable seams → 4 blends**.

## SketchOnly_CornerCube.FCStd — bonus: the cube corner

- **9 sketches**: 3 seams `SK_Seam_X/Y/Z` + 6 outer edges
  `SK_F<1/2/3>_Outer<A/B>` — three patches meeting at one corner in 3D.
- **Which edges go together** (each sketch is one Edge; the ground-truth
  `SketchOnly_CornerCube_withPatches.FCStd` uses them as):
  - **Face1** = Seam_X + F1_OuterA + F1_OuterB + Seam_Y
  - **Face2** = Seam_X + F2_OuterA + F2_OuterB + Seam_Z
  - **Face3** = Seam_Y + F3_OuterA + F3_OuterB + Seam_Z
- **Which seams should blend**: `Seam_X` (Face1↔Face2), `Seam_Y`
  (Face1↔Face3) and `Seam_Z` (Face2↔Face3).
- **Intended build**: a 3D corner (three quad patches meeting at one
  point), for later rounds. This one is **optional** / advanced; do not
  use it for the first wizard-fit judgement.


## SketchOnly_Demo01Subset.FCStd — Demo 01 sketch-only subset

- **33 sketches**: the demo's own **29** (`Sketch014`..`Sketch045`), copied
  geometry-for-geometry (placements preserved; constraints copied
  best-effort), **plus four documented supplements**: `SK_Half_Rib_FB`,
  `SK_Half_Rib_FT`, `SK_Half_Rib_BkB`, `SK_Half_Rib_TBk`. **Zero** Edge /
  Patch / Blend objects.
- The guard (`Tests/test_example_documents.py`) does **not** trust a
  hand-written list here: it unzips the demo's `Document.xml`, asserts the
  fixture carries the demo's own 29 sketch names, and asserts that every
  *other* sketch is one of the four named supplements (`Tests/
  demo01_fixture_model.HALF_RIB_SUPPLEMENT`) — both directions.
- **Why the supplements exist.** The demo models **half** the shape: each
  rib runs (mirrored hoop) → symmetry plane (u = 0.5) → modelled hoop
  (u = 1), and the four ring faces consume only the **u in [0.5, 1] half**
  of each rib (a stored `ControlPoly4_segment`). A Silk Edge consumes a
  whole sketch — it has no trim — so on the demo's own sketches the four
  rib-bounded faces cannot close a loop. The u in [0.5, 1] sub-curve of a
  cubic Bezier **is** a cubic Bezier, so the fixture adds those four halves
  as ordinary 3-line ControlPoly4 sketches. Each built half-rib Edge is
  pole-identical to the demo's own stored `ControlPoly4_segment` piece
  (max delta 2.8e-14 mm).
- The demo's four **full-rib** sketches (`Sketch020/022/024/026`) stay in
  the file but are **not consumed** by the click-through — they are the
  demo's original inputs, and clicking them gives the refused build
  described under *What a click-through reaches* below.

### The click-through (16 sketches → 12 Edges → 5 Patches → 8 Blends → 4 CornerBlends)

Build **12 Edges** — four whole sketches become one Edge each; the two
hoop edges are one Edge each built from **two** `SK_Edge`-style node
sketches:

| Edge | from sketches |
|---|---|
| `E_front_out` | `Sketch015` |
| `E_top_out` | `Sketch016` |
| `E_back_out` | `Sketch017` |
| `E_bottom_out` | `Sketch018` |
| `E_half_rib_FB` | `SK_Half_Rib_FB` |
| `E_half_rib_FT` | `SK_Half_Rib_FT` |
| `E_half_rib_BkB` | `SK_Half_Rib_BkB` |
| `E_half_rib_TBk` | `SK_Half_Rib_TBk` |
| `E_right_FR` | `Sketch036` + `Sketch037` |
| `E_right_BR` | `Sketch038` + `Sketch039` |
| `E_right_TR` | `Sketch042` + `Sketch045` |
| `E_right_BkR` | `Sketch032` + `Sketch035` |

Build **5 Patches**. The order below is the documented click order (one
entry per boundary side, cyclically):

| Patch | edge click order |
|---|---|
| `P_Front` | `E_half_rib_FB`, `E_right_FR`, `E_half_rib_FT`, `E_front_out` |
| `P_Top` | `E_half_rib_FT`, `E_right_TR`, `E_half_rib_TBk`, `E_top_out` |
| `P_Right` | `E_right_BR`, `E_right_BkR`, `E_right_TR`, `E_right_FR` |
| `P_Bottom` | `E_bottom_out`, `E_half_rib_BkB`, `E_right_BR`, `E_half_rib_FB` |
| `P_Back` | `E_back_out`, `E_half_rib_TBk`, `E_right_BkR`, `E_half_rib_BkB` |

Blend the **8 seams** (each is the shared edge of the pair named):
`B_FB` (Bottom/Front), `B_FT` (Top/Front), `B_FR` (Front/Right),
`B_BR` (Right/Bottom), `B_BkB` (Bottom/Back), `B_TBk` (Top/Back),
`B_TR` (Right/Top), `B_BkR` (Back/Right).

Build **4 CornerBlends**, each from **three** ring blends (this is the
3-valent hard-corner path — a Demo 01 junction is where three faces meet):
`CB_J1_FrontTopRight` = `B_FT`, `B_FR`, `B_TR`; `CB_J2_FrontRightBottom` =
`B_FB`, `B_FR`, `B_BR`; `CB_J3_TopRightBack` = `B_TR`, `B_TBk`, `B_BkR`;
`CB_J4_RightBottomBack` = `B_BR`, `B_BkB`, `B_BkR`.

**Result:** 12 Edges, 5 Patches, 8 Blends, 4 CornerBlends (36 poles each,
valid shapes, each covering its junction point), every object oracle-green.
Every built Patch's 16-pole net **is** the demo's stored `ControlGrid44_4_*`
net up to a named symmetry of the square (Front/Top/Back in the stored
order, delta ≤ 2.9e-14; Right under `rot90`, Bottom under `rot180`, delta ≤
4.0e-13). No continuity label is asserted anywhere.

> **The patch click order and the blend pair order are NOT part of the
> result (#107).** Before #107 building the same five faces in the demo's
> own stored grid order made all four junctions refuse: `"its two patches
> disagree about which end is the junction (twisted input)"`, and blending a
> seam with the two patches handed to the command in the other order could
> leave a ring the corner could not assemble. The corner stage now reads a
> patch that parameterizes a shared seam the other way round, and a blend
> whose `PatchA`/`PatchB` order differs from the ring's direction, so any
> click order fills the same four corners. The order in the table above is
> still the one whose Patch nets are pole-identical to the demo's stored
> `ControlGrid44_4_*` in the RAW order (no transform); `Tests/
> test_demo01_rebuild.py` pins both the pole parity and that the demo's own
> order gives the same corner fill.

### What a click-through reaches on the demo's own 29 sketches (unchanged)

16 of the 29 sketches feed **12 whole-sketch Edges** (4 outer cross-section
edges, 4 **full** rib curves, 4 node-pair hoop edges). The **Right** end cap
(whose four curves really are whole sketches) rebuilds as one Patch; the
other four `create_patch` calls refuse with "do not close a loop" naming the
outer edge that shares no corner, because the faces are bounded by rib
*halves*. No seam can be blended and no junction attempted. The exact
refusal texts are pinned in `Tests/test_demo01_rebuild.py`.

- The full mapping (which sketch feeds which stored curve, per-edge
  tables, raw counts) is `docs/research/silk-demo-01-inventory.md`; the
  junction table is `docs/research/silk-demo-01-junction-table.md`.
- The generator for this file is `Tests/make_demo01_fixture.py`; the
  mapping the tests assert against is `Tests/demo01_fixture_model.py`.


---

## How these fixtures are used

- **Human click-through**: open the file, click **Edge → Patch → Blend**
  to reproduce the target. The point is to test how the *workflow* feels
  (tree clutter, edge claims, panel content) without rebuilding geometry.
- **Agents / automated checks**: `Tests/test_example_documents.py` opens
  every example and asserts the fixture invariant — **zero Silk objects**
  and the **documented sketch set present** — and for
  `SketchOnly_Demo01Subset.FCStd` it also reads the demo's own
  `Document.xml` and asserts each demo sketch carries the **demo's own
  constraints, per type**, and the **same external geometry** (#108: a
  fixture that copies a sketch's geometry but drops its construction is
  still pole-identical, so nothing at the pole level can see it).  These
  files are binary so they cannot be diffed; the sketch names + this
  README are the human- and agent-readable intent.

The `SketchOnly_*` **companion** files with `_withEdges` / `_withPatches`
suffixes at the top level of `Resources/Test_files/` are the *built*
ground-truth versions of these same fixtures (what the click-through
should reproduce). They are kept at the top level, not moved here,
because they contain Silk objects and are not part of this sketch-only
set.
