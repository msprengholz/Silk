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
(`Tests/test_example_documents.py`) assert.

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

---

## How these fixtures are used

- **Human click-through**: open the file, click **Edge → Patch → Blend**
  to reproduce the target. The point is to test how the *workflow* feels
  (tree clutter, edge claims, panel content) without rebuilding geometry.
- **Agents / automated checks**: `Tests/test_example_documents.py` opens
  every example and asserts the fixture invariant — **zero Silk objects**
  and the **documented sketch set present**. These files are binary so
  they cannot be diffed; the sketch names + this README are the
  human- and agent-readable intent.

The `SketchOnly_*` **companion** files with `_withEdges` / `_withPatches`
suffixes at the top level of `Resources/Test_files/` are the *built*
ground-truth versions of these same fixtures (what the click-through
should reproduce). They are kept at the top level, not moved here,
because they contain Silk objects and are not part of this sketch-only
set.
