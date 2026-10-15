# Review: ArachNURBS fill/feature types — which exist, are they stable, do they fit the workflow?

Research for issue [#87](https://github.com/msprengholz/Silk/issues/87) (part of map #1,
round-seven backlog item (ii)). **No production code was changed.** The only repository
artifact this issue adds is this document.

> Human question, verbatim: *"i am still not sure when to use the flow patch, if it is
> stable / has G2 cont. and if it would be compatible with our developed workflow. These I
> need answered for all these types. There are also new sketch -> controlgrid features. I
> think we need a review of the codebase as its own task that answers these questions."*

---

## 0. Method, and how to read the evidence

Three evidence levels are used and are **not** interchangeable:

- **MEASURED** — I ran it. A separate **headless** `freecadcmd` process (FreeCAD 1.1.3) was
  used with throwaway probe scripts (scratch files, not part of the record). The live GUI
  (issue #86) and its RPC port 9875 were **not** touched: no GUI document was created,
  modified, or closed. `ArachNURBS.py` imports `from FreeCAD import Gui`
  (`ArachNURBS.py:28`), so the headless probes stub `FreeCAD.Gui` — that is the whole
  difference from an in-GUI import. Every measured input and result is inlined in the
  Appendix, so this document stands alone.
- **READ** — I read the source. A docstring/comment claiming a property is **not**
  evidence of that property (the #68 lesson); such claims are tagged as *claimed*.
- **INFERRED** — a conclusion drawn from MEASURED/READ facts but not itself executed.

Standing probes were run with a **non-degenerate** input *and*, where a failure appeared, a
**degenerate** one too, so that "it built" and "it crashed" are both statements the
instrument could have contradicted. Where a probe result was surprising, the unmodified
baseline (`blend_poly_2x4_1x6`) was re-run in the same process as a control.

**What the workflow actually requires of a fill** (the correctness bar a new type must
clear), all READ from `SilkChecks.py`:

| object | stored contract | oracle |
|---|---|---|
| `Edge` | **4 poles + 4 weights (all 1.0)** in `Poles`/`Weights`, `object_type=="Edge"`, `Sketches`, `Legs`, valid `Shape` | `check_edge` → E1 endpoint anchoring to the driving sketch, E2 pole order, E3 control-polygon non-self-intersection, E4 arc/chord bound + valid (`SilkChecks.py:100-191`) — the structural gate at `:108` hard-requires **exactly 4 poles** |
| `Patch` (4 edges) | 16 poles + 16 weights in `Poles`/`Weights`, `object_type=="Patch"`, `Edges` link list, valid `Shape` | `check_patch` → P1 corner order, P2 boundary match, P3 no fold/flip, P4 valid+non-self-intersecting (`SilkChecks.py:302-399`) |
| `Patch` (3 edges) | same 16 poles; U=0 column collapses to the point | `check_patch` → C1 corner order, C2 boundary match, C3 degenerate point, + P3/P4 (`SilkChecks.py:402-508`) |
| `Blend` | 24 poles + weights, fed **only** patch subgrid cells | `check_blend` → B1 C0 seams (1e-6), B2 C1 tangent poles vs `blend_poly_2x4_1x6` at the 2× scale (1e-6), B3 valid, B4 optional pole match (`SilkChecks.py:820-912`) |
| `CornerBlend` | 36 poles, 4 ring strips in | `check_corner_blend` → CB1 C0 boundary, CB2 36-pole fill vs `ControlGrid66_4`, CB3 valid, CB4 optional (`SilkChecks.py:974-1109`) |

A fill that cannot express itself as one of those shapes has **no oracle**, and #68
warns exactly against asserting its properties without one.

---

## 1. Provenance verdict — were the three `*_test.py` modules conclusions or experiments?

**Verdict: they are prior *experiments / scratch scripts*, not conclusions, and not
evidence of anything.**

The three modules the ticket names are:

- `CubicNStarSurface_NStar66_test.py`
- `ControlGridNStar66_NSub_test.py`
- `ControlGridNStar66_NSub_by_inheritance_test.py`

Evidence (all READ):

1. **They are top-level scripts with import-time side effects.** Importing any of them
   immediately reads the GUI selection and mutates the active document:
   `sel=Gui.Selection.getSelection()` then
   `FreeCAD.ActiveDocument.addObject("Part::FeaturePython", ...)` and
   `FreeCAD.ActiveDocument.recompute()` at module scope — e.g.
   `ControlGridNStar66_NSub_test.py:46-61`, `ControlGridNStar66_NSub_by_inheritance_test.py:309-324`,
   `CubicNStarSurface_NStar66_test.py:54-69`. They are therefore un-importable and un-testable
   by the suite; they are not run by `Tests/run_all.py`.
2. **They duplicate classes that now live in `ArachNURBS.py`.** Their bodies match the core
   later-generation class `ControlGridNStar66_NSub` (`ArachNURBS.py:8970`) — same
   `StarRow2_2Sub` / `StarDiag3_Sub` / `StarCenter` method set, same `Legs_Row2_i` index
   tables (`ControlGridNStar66_NSub_by_inheritance_test.py:45-268` vs
   `ArachNURBS.py:8986-...`). They are an earlier generation of the same code, not a
   separate finding.
3. **They carry in-code WIP notes that read as a developer's working log, not a result.**
   `ControlGridNStar66_NSub_by_inheritance_test.py:22` — *"As of now, there is a functioning
   N=3 version."*; `:26-27` — *"This is pretty horrible way to handle data access across a
   dataset of unknown size."*; `:14-18` — a design deliberation about `Matrix` vs variable
   names. The class is named `ControlGrid3Star66_3Sub` and hard-codes `N=3`
   (`:273-306`) — consistent with a prototype that had only reached 3 wedges.
4. **They leave the reader no result.** There is no assertion, no printed pass/fail, no
   recorded output — the script appends geometry to the live document and stops.

**Consequence for this review:** the `NStar` rows below are judged from the *current*
`ArachNURBS.py` class (MEASURED), not from these scripts. The scripts are useful only as
the historical hint that the N-star corner was explored and left at "N=3 works".

---

## 2. Main table

Legend — **Stab**: `OK` = builds and survives recompute; `WIP` = self-labelled work in
progress; `crash` = raises on a plain input; `dead` = superseded/unreachable.
**Cont**: continuity actually *achieved* to an arbitrary neighbouring band — `C0`/`G1` are
constructed; `G2?`/`G3?` are labels the code carries but that no oracle verifies.
**WF-compat**: `prod` = already the workflow fill; `wrapped` = reachable through an
existing workflow object; `new-contract` = wrong pole count/semantics for any current
object; `no-base` = cannot subdivide because `SilkMachinery` expects a 4×4 base.
**Effort**: `—` none (already reachable) … `XL` new object type + oracle + UI.
**Rec**: `keep` / `expose` / `hold` / `fix-then-expose` / `drop` / `investigate`.

| type | family | Stab | Cont | WF-compat | Effort | Rec |
|---|---|---|---|---|---|---|
| `ControlGrid44_4` | bicubic grid | OK (prod) | boundary C0 to its 4 edges | prod | — | keep |
| `ControlGrid44_3` | bicubic grid | OK (prod) | boundary C0; U=0 col degenerate | prod | — | keep (see #68 caveat) |
| `ControlGrid44_3_Rotate` / `_OLD` | bicubic grid | READ: variant | as 44_3 | new-contract | M | drop (superseded by rotate param) |
| `ControlGrid44_flow` | bicubic grid | OK (MEASURED) | **G1 kept at boundary; interior "flows" — NOT G2** | yes (16 poles) | S | expose behind a flag; label honestly |
| `ControlGrid64_2` / `ControlGrid64_2Grid44` | composite | OK **iff** the two grids share an edge (MEASURED); **crash** otherwise | C0 to the shared grid edge; other edges unverified | new-contract (24 poles) | L | investigate (needs seam-guard fix first) |
| `ControlGrid64_3` | bicubic grid | **dead** — *"degenerate grid. NOT IN USE ANYWHERE"* (`:5237`) | n/a | new-contract | — | drop |
| `ControlGrid64_4` | bicubic grid | READ: 2×6P + 2×4P input | C0 to a mixed 6/4 boundary | new-contract (24 poles) | L | hold |
| `ControlGrid64_normal` | composite | READ: derived normal grid | n/a (a normal field, not a patch) | new-contract | M | investigate (display only) |
| `ControlGrid64_Surf44` | composite | READ: wraps `CubicSurface_44` | inherits 44's | new-contract | M | hold |
| `ControlGrid44_EdgeSegment` | composite | READ: edge→segment helper | n/a | internal | — | keep internal |
| `ControlGrid44_2EdgeSegments` | composite | READ | n/a | internal | — | keep internal |
| `ControlGrid64_3_1Grid44` | composite | OK (MEASURED, poles=24 shape ok) | degenerates one 6×4 corner from a 4×4 grid; folding risk noted in-code (`:8300-8360`) | new-contract | L | investigate (corner-fill candidate) |
| `ControlGrid66_4` | composite | OK (prod via CornerBlend) | C0 to 4 cubic-6 rows | prod (CornerBlend) | — | keep |
| `ControlGrid66_4Sub` | composite | OK (MEASURED, 36 poles) | as `ControlGrid66_4` | new-contract | M | investigate |
| `SubGrid33_2Grid64` | composite | READ | n/a | new-contract | M | hold |
| `SubGrid63_2Surf64` | composite | READ | n/a | new-contract | M | hold |
| `ControlGridNStar66_NSub` (N=3,4,5) | N-star corner | OK on non-degenerate input (MEASURED); **crash** on a degenerate one | C0 into the star; wedge-seam continuity unverified | new-contract (N×36) | XL | investigate (the real corner prize; no oracle yet) |
| `CubicNStarSurface_NStar66` | N-star corner | OK **if** handed a built `ControlGridNStar66_NSub` | inherits the star grid | new-contract | XL | investigate |
| `StarTrim_CubicNStar` | N-star corner | READ: trim helper | n/a | new-contract | XL | hold |
| `ControlGridNStar66_StarTrim` | N-star corner | READ — *"quick and dirty test"* (`:9407`) | n/a | new-contract | XL | drop |
| `ControlGrid3Star66_3Sub` (root module) | N-star corner | WIP, N=3 only | as NStar | new-contract | XL | drop (superseded by NSub) |
| `ControlGrid5Star66_5Sub` (root module) | N-star corner | WIP, N=5 only | as NStar | new-contract | XL | drop (superseded by NSub) |
| `blend_poly_2x4_1x6` (G2) | blend primitive | OK straight + curved (MEASURED) | **C0 exact + G1 direction** (MEASURED); "G2" is a label, curvature not oracle-checked | prod (`SilkBlend.run_blend`) | — | keep |
| `blendG3_poly_2x4_1x6` | blend primitive | **WIP / crash** — `ZeroDivisionError` on a straight input (MEASURED); built on a curved one | unverified | swap-in only | L | fix-then-expose |
| `blendFair_poly_2x4_1x6` | blend primitive | **WIP / crash** — `UnboundLocalError: scale_1i` on every input tried (MEASURED) | unverified | swap-in only | L | fix-then-expose |
| `CubicSurface_44` | surface | OK (prod via `SilkChecks`/P4) | — | prod | — | keep |
| `CubicSurface_66` | surface | OK (prod via `CornerBlend`) | — | prod (CornerBlend) | — | keep |
| `CubicSurface_64` | surface | OK (prod via `Blend`) | — | prod (`SilkBlend.py:547`) | — | keep |

The `_Attributes` names in the ticket (`ControlPoly4_2N_Attributes`, …) are **methods, not
types** — each builds one class's properties (`ArachNURBS.py:1855`, `:2054`, `:2381`, …).
The user-visible *types* are the `ControlPoly4_*` / `ControlPoly6_*` classes.

**The whole sketch → Edge family is analysed separately in §2b** (it is the subject of the
follow-up question, and its modes do not behave like the fill types above: they have their
own input shapes, their own pole counts, and their own reachability story).

---

## 2b. Sketch → Edge — the "2 sketches → one edge" story

This is the process BEFORE a fill: turning sketches into the 4-pole cubic `Edge` the rest of
the workflow consumes. `ArachNURBS.py` offers two parallel families — `ControlPoly4_*`
(4-pole cubic, degree 3) and `ControlPoly6_*` (6-pole, degree 3 with two extra knots) — but
the Silk workflow only ever built a route for the first three 4-pole modes.

### 2b.1 Every edge-input mode

| mode | inputs | poles | supported by `SilkEdge`? | reachable from panel / ops? | gap? |
|---|---|---|---|---|---|
| `ControlPoly4_3L` (`:1675`) | 1 sketch, 3 connected visible lines | 4 | **yes** — `visible_line_count==3 and visible_count==3` (`SilkEdge.py:97-100`) | panel 1-sketch (`EDGE_MIN/MAX=1,2`, `SilkTaskPanel.py:122`) + `Silk_CreateEdge` command | no |
| `ControlPoly4_FirstElement` (`:2182`) | 1 sketch, first element by type | 4 | **yes** — the else branch for any single sketch (`SilkEdge.py:111-114`) | panel 1-sketch + command | no |
| `ControlPoly4_2N` (`:1853`) | 2 node sketches, each **circle + line** | 4 | **yes** — the `len(sketches) >= 2` branch (`SilkEdge.py:70-83`) | panel 2-sketch ("2N (two sketches)", `SilkTaskPanel.py:1227`) + `create_edge` op + command | no |
| `ControlPoly4_2P` (`:2053`) | 2 `Point_onCurve` objects | 4 | no | legacy `ControlPoly4` command only (registered `ControlPoly4.py:249`, retired from view — `Tests/test_initgui_commands.py:76`) | not wired |
| **`ControlPoly4_2X4P`** (`:2379`) | **2 existing `ControlPoly4` objects** — two sketch-derived planar edges | **4** | no | legacy `ControlPoly4` command only (detection `ControlPoly4.py:155-161`, creation `:220-230`; *registered* `:249` but retired from the visible menu) | **YES — the finding (§2b.2)** |
| `ControlPoly4_GridEdge` (`:2557`) | 1 `ControlGrid44` + an edge index/click | 4 | no | legacy `ControlPoly4` command only | not wired |
| `ControlPoly4_segment` (`:5998`) | a curve + 2 `Point_onCurve` | 4 | no | none (internal helper) | n/a |
| `ControlPoly6_5L` / `_2N` / `_FirstElement` / `_Bezier` / `_FilletBezier` (`:2730` / `:2882` / `:3124` / `:5583` / `:5624`) | 1 sketch (5 lines / first element / a cubic), 2 node sketches, or 2 `CubicCurve_4` | 6 | no | retired, **unregistered** command (`ControlPoly6.py:128-134`) | **out of scope (§2b.8)** |

### 2b.2 The 2-sketches → one-edge story: what is supported, and the gap

- **Supported today:** selecting **two node sketches** (each a circle + a line) and building
  an Edge routes to `ControlPoly4_2N` and yields a **4-pole cubic** (`SilkEdge.py:70-83`;
  `SilkWorkflowOps.create_edge` docstring "from one or two ControlPoly4 sketches",
  `SilkWorkflowOps.py:26-44`; panel `EDGE_MAX=2`, `SilkTaskPanel.py:122`; stage test
  `Tests/test_edge_stage.py:126-169`). Fully supported end-to-end.
- **The gap — `ControlPoly4_2X4P`** (`ArachNURBS.py:2379`, the newest sketch→edge builder,
  §2b.3). It is **not** "two sketches → one edge" in the *input-type* sense (its two inputs
  are existing `ControlPoly4` objects), but in the **modelling-intent** sense it is exactly
  that: **two sketch-derived planar edges → one 3D edge**. One input supplies the plan
  footprint, the other the elevation (§2b.4). `SilkEdge` has no branch that composes two
  edges — it only ever reads 1 or 2 *sketches* (`SilkEdge.py:62-122`) — so the capability is
  unreachable from the wizard.

### 2b.3 Is it "new"? (git provenance, READ) — the human's point

- `ControlPoly4_2X4P` is the **newest** of the whole sketch→edge family: added by upstream
  edwardvmills in `3f47384`, **2026-05-17** *"new - ControlPoly4_2X4P"* (`git log
  -S "class ControlPoly4_2X4P"`). That is why it reads as "a new feature" — **it is**.
- Our vendored `ArachNURBS.py` is **byte-identical to `upstream/master` (`4b1d713`) for every
  sketch→edge builder**; the *only* local difference in the whole file is the #41 blend guard
  in `blend_poly_2x4_1x6` (`git diff upstream/master -- ArachNURBS.py`, 8 insertions / 2
  deletions). So the "new" feature is genuine upstream work, not a local variant.
- The other recent upstream sketch→edge additions are `ControlPoly4_2P` (`a8edabd`,
  2025-05-12), `ControlPoly4_GridEdge` (`b7559e1`, 2025-11-21) and
  `ControlPoly4_FirstElement` / `ControlPoly6_FirstElement` (`a682427`, 2025-11-13) — all
  older than `2X4P`, and none of them a multi-input edge composer.
- **Reconciling the wording honestly:** an earlier draft of this document argued "none of the
  new builders is a 2-sketches→1-edge". That was true of the *input types* and wrong about
  the *capability*: `2X4P` composes two sketch-derived edges into one 3D edge, which is what
  the human means. The provenance point that matters — it is the newest builder — is the
  human's point and it stands.

### 2b.4 What `ControlPoly4_2X4P` actually does (READ + MEASURED)

MEASURED in a separate headless `freecadcmd` (live GUI / RPC 9875 untouched). Plan `Poly4_0`
on XY `[(0,0,0),(10,0,0),(20,10,0),(30,0,0)]`, elevation `Poly4_1` in the XZ plane
`[(0,0,0),(10,0,-5),(20,0,-15),(30,0,0)]`; output `Poles = [(0,0,0),(10,0,-5),(20,10,-15),
(30,0,0)]`, `Weights = [1,1,1,1]`, 3 `Legs`, `object_type = "ControlPoly4_2X4P"`, non-null
valid Shape, **recompute-stable** (`Poles` identical on a second `recompute()`), and the
`reverse` toggle mirrors the pole order.

The construction (`ArachNURBS.py:2464-2555`), line for line:

- **`Poly4_0` is the plan / XY source.** Its poles are **force-projected onto `Poly4_0`'s own
  sketch plane**: `p0_i_toPlane = (p0_i_raw - xy_origin).dot(xy_zVector)` then
  `p0_i_onPlane = p0_i_raw - xy_zVector*p0_i_toPlane` (`:2517-2529`; the normal is
  `xy_zVector = xy_mat.multiply(Base.Vector(0,0,1)) - xy_origin`, `:2512`). Any out-of-plane
  Z that Poly4_0 happens to carry is discarded.
- **`Poly4_1` is the height source.** Each composed pole is
  `p_iw = p0_i_onPlane + xy_zVector * p1_i_toPlane`, where
  `p1_i_toPlane = (p1_i_raw - xy_origin).dot(xy_zVector)` (`:2532-2541`) is Poly4_1's pole
  *distance along Poly4_0's plane normal* — only a scalar per pole is used, never Poly4_1's
  in-plane position.
- Output = 4 poles, `Legs` = 3 `Part.LineSegment`s, `Shape = Part.Shape(Legs)`
  (`:2544-2555`).

Constraints and failure modes (READ, with one MEASURED):

- **`Poly4_0` must be sketch-based.** `execute` accepts only `ControlPoly4_3L` (uses its
  `Sketch`), `ControlPoly4_2N` (uses its `Sketch0`) or `ControlPoly4_FirstElement` (uses its
  `Sketch`); anything else falls to the deliberate self-poisoning line
  `fake_name_to_trigger_error = please_read_message_above` (`:2467-2478`). MEASURED: a
  `Poly4_0` whose `object_type` is `ControlPoly4_2P` raises
  `NameError: name 'please_read_message_above' is not defined` — a deliberate, un-missable
  failure, exactly as written, and the one thing that makes E1 meaningful (below).
- **`Poly4_1` is read for its `Poles` only** — it need not be sketch-based, nor even a
  `ControlPoly4` (`:2493-2496`).
- **Two coplanar edges are silently degenerate.** MEASURED: with `Poly4_1` also in
  `Poly4_0`'s plane, every `p1_i_toPlane = 0`, so the output **equals `Poly4_0` exactly** and
  Poly4_1's shape is ignored. No error — a "flat" result, which is the honest reading of
  "Poly4_1 is an elevation".

### 2b.5 Does it fit the `Edge` workflow contract? (MEASURED — **yes**)

`Edge` is 4 poles + 4 unit weights + `Legs` + `object_type = "Edge"` (`SilkEdge.py:29-43`) and
is `Patch`'s boundary input. `2X4P` emits exactly that geometry shape, so the live question is
whether the composed *3D* poles clear the oracle.

MEASURED: a carrier presenting the composed poles/weights/legs as `object_type = "Edge"` with
`Sketches = [Poly4_0's sketch]` was run through the **real** oracle and is **green on every
check**:

| check | ok | detail |
|---|---|---|
| structural | yes | `object_type, links, 4 poles/weights, legs, shape` |
| E1 endpoint anchoring | yes | `end deltas vs sketch: 0.00e+00 / 0.00e+00 (tol 1e-06)` |
| E2 pole order | yes | consecutive steps stay shorter than diagonal skips |
| E3 polygon self-intersection | yes | no crossings |
| E4 arc/chord + valid | yes | `length/chord = 1.21 (limit 4.0), curve valid=True` |

E1 passes **because** the composed end poles are `Poly4_0`'s endpoints (projected onto
Poly4_0's own plane, so unchanged) — i.e. exactly the driving sketch's endpoints. So anchoring
against `Poly4_0`'s sketch is correct by construction, not a coincidence. (`check_edge` is
`SilkChecks.py:100-191`.)

**So yes: `2X4P` is the one sketch→edge capability that fits `Edge` cleanly and is genuinely
missing** — unlike the 6-pole family, which fits nothing (§2b.8).

### 2b.6 What would exposing it take?

1. **A compose input on `Edge`.** `Edge.Sketches` is an `App::PropertyLinkList` of *sketches*
   (`SilkEdge.py:29-30`) and E1 reads `Sketches[0]` as a 3L sketch (`SilkChecks.py:130-142`) —
   **it is not the right representation for "two existing edges"**. The clean shape is a new
   pair of link inputs (e.g. `Edge0`/`Edge1`, or `Poly4_0`/`Poly4_1`) plus a mode flag, with
   `Sketches` kept = `Poly4_0`'s driving sketch so E1 still anchors (measured green above).
2. **A user selection path.** Today only the legacy `ControlPoly4` command reaches `2X4P`
   (detection `ControlPoly4.py:155-161`, creation `:220-230`; the command is *registered* at
   `:249` but **retired from the visible toolbar/menu** — `InitGui.py:62-88`,
   `Tests/test_initgui_commands.py`). The user would select **two `Edge`s** (each already a
   planar 3L/2N/FirstElement edge) and pick a "compose" mode.
3. **The panel does not express it today.** The Edge collection is bounded to
   `EDGE_MIN, EDGE_MAX = 1, 2` *sketches* (`SilkTaskPanel.py:120-124`) and `is_sketch`
   (`:1111-1114`) filters to sketches; a compose mode must collect two **Edges**, not two
   sketches, and add a mode label beside "3L"/"2N" (`:1224-1231`).
4. **Cost:** the geometry half is nearly free (the class exists and is measured green); the
   real work is the `Edge` input representation + the panel affordance. Effort **M**.

### 2b.7 `SilkEdge` routing, and the 3+ sketches observation

`SilkEdge.Edge.execute` (`SilkEdge.py:62-143`) routes by **count and a sketch-content guess**:

- **`len(sketches) == 1`** → count *visible* (non-construction) lines: `3` and nothing else
  visible → `ControlPoly4_3L`, otherwise → `ControlPoly4_FirstElement` (`SilkEdge.py:85-122`).
- **`len(sketches) >= 2`** → **always** `ControlPoly4_2N`, using **only `sketches[0]` and
  `sketches[1]`** (`SilkEdge.py:70-83`). Two consequences:
  1. **Every sketch after the second is silently ignored.** Reachable? **Yes, through the
     command, but not the panel.** The panel caps the edge collection at `EDGE_MAX = 2`
     (`SilkTaskPanel.py:120-124`), but `SilkEdge.CreateEdge.Activated` collects **every**
     selected `Sketcher::SketchObject` with no cap (`SilkEdge.py:182-199`) and hands the whole
     list to `Edge(...)`. Selecting 3 sketches and running the toolbar/menu/context-menu
     command creates an Edge that **silently uses only the first two**. Severity: low (a valid
     2N edge, the extra ignored) but a real silent-drop worth a guard.
  2. **There is no route that composes two edges** — exactly the `2X4P` gap above.

### 2b.8 Out of scope — `ControlPoly6_*` (the human's call)

`ControlPoly6_*` (5L, FirstElement, 2N, Bezier, FilletBezier) builds **6-pole** edges. It does
not belong in the edge → patch → blend workflow and is **out of scope** for this review:
`Edge` has no 6-pole path (`SilkEdge.py:126-129`), `Patch`'s fill indexes `Poles[0..3]`
(`SilkPatch.py:452-459`) and `check_edge` structurally requires exactly 4 poles
(`SilkChecks.py:108`), and the only consumers of a 6-pole boundary are the unexposed 64/66
grid family. So it is a dead-end family, not a gap. Recorded here only so the inventory is
complete; not analysed further.

---

## 3. What the probes actually showed (evidence detail)

### 3.1 `ControlGrid44_flow` — builds, but it is **not** a G2 patch (MEASURED + READ)

- MEASURED: `ControlGrid44_flow` built 16 poles, a non-null Shape, and was
  recompute-stable (probe 1).
- READ: the class makes a *copy* of a `ControlGrid44` whose four interior points slide
  between the original position and a "flow" position along the boundary tangent lines,
  driven by `flow_11`/`flow_12`/`flow_21`/`flow_22` in `[0,1]`
  (`ArachNURBS.py:4246`, `:4261-4276`). The class comment says the interior points
  *"will 'flow' instead of providing predictable tangency."*
- **Continuity conclusion (INFERRED from the above):** a flow grid is still an independent
  bicubic patch; it interpolates its 4 boundary edges (C0, same as the quad fill) and the
  *interior* is pulled around, which can make a nicer-looking single patch but cannot by
  itself guarantee G1/G2 to a *neighbouring* patch. The name does not describe continuity
  to anything. If the human wants G2 across a patch seam, that comes from the **Blend**,
  not from the patch fill.

### 3.2 The blend primitives (MEASURED)

`blend_poly_2x4_1x6` returns `[poles(6), weights(6), scale_1, scale_2]` (`ArachNURBS.py:673`).
Measured facts on one control input:

- both endpoints reproduce the two input boundary poles **exactly** (`0.000e+00`);
- the start tangent direction is preserved (`dot = 1.000000`) — **G1 by construction**;
- the inner control leg carries a non-zero height (`h1 = 0.6468`), i.e. the blend is
  curvature-carrying.
- The oracle B2 *re-runs* `blend_poly_2x4_1x6` and compares tangent poles
  (`SilkChecks.py:861-872`), so B2 verifies the **construction**, not an independent G2
  measurement. **No test in this repo measures G2/G3 continuity.** The "G2/G3" names are
  the author's labels; `blendG3_poly_2x4_1x6` and `blendFair_poly_2x4_1x6` both carry the
  comment *"work in progress. complete mess"* (`ArachNURBS.py:761`, `:1074`).
- `blendG3_poly_2x4_1x6`: **ZeroDivisionError** on a straight (collinear) input at
  `error_0 = … / math.fabs(dCds6_0i)` (`ArachNURBS.py:936`); built 6 poles on a curved
  input. So it is input-sensitive and crashes rather than degrading.
- `blendFair_poly_2x4_1x6`: **UnboundLocalError: `scale_1i`** on both inputs tried (straight
  and curved) — it raises before returning anything on the paths exercised.

### 3.3 The 64-grid composites (MEASURED)

- `ControlGrid64_2Grid44`, **with two grids that genuinely share an edge**, built 24 poles
  and a non-null Shape (probe 2). **With grids that do not share the right corner
  structure**, it raised `UnboundLocalError: cannot access local variable 'seam_0'` at
  `ArachNURBS.py:7484` — because the guard chain only assigns `seam_0` for
  `len(dedupe)==2` or `==3` (`:7459-7483`) and the degenerate/no-seam case falls through.
  So its "refusal" path is a crash, not a clean refusal → an exposure blocker.
- `ControlGrid64_3_1Grid44` built 24 poles + non-null Shape, stable on recompute (probe 1);
  its own code comments flag folding and G1-loss risks and document several abandoned
  strategies (`ArachNURBS.py:8199`, ≈`:8300-8360`).
- `ControlGrid66_4Sub` built 36 poles + non-null Shape (probe 1).

### 3.4 The N-star corner (MEASURED, with the degenerate control)

- `ControlGridNStar66_NSub` for **N = 3, 4, 5**: built a `StarGrid` of N entries, `Legs`
  of ~25·N segments, and a **non-null Shape** on a non-degenerate 6×6-per-wedge input
  (probe 3). It is recompute-stable.
- On a *degenerate* input (probe 2), `StarCenter` raised `Part.OCCError: Both points are
  equal` at `ArachNURBS.py:9267` (`Part.LineSegment(Poles[i][29], Poles[i][35])`). This is
  a **control** confirming the probe can fail — the non-degenerate run is the result, and
  the degenerate run shows the star has **no guard** against a wedge whose centre point
  collapses.
- **Continuity (INFERRED):** the whole point of the star assembly is to make N wedge
  surfaces meet at a common centre with matched seams (`StarCenter` averages pole[29]
  across wedges, `ArachNURBS.py:~9260`). Whether the resulting seams are C0-only or higher
  is **not verified anywhere** — there is no N-star oracle. Treat any continuity claim as
  unproven.
- The three `*_test.py` modules are the historical prototype of this class and only ever
  reached N=3 (see §1).

---

## 4. Selection policy — which types should become reachable, and how a user picks

1. **Lead with `ControlPoly4_2X4P` on `Edge` (§2b).** It is the strongest candidate in the
   whole review: the **newest** sketch→edge builder, MEASURED recompute-stable, and MEASURED
   fully `check_edge`-green once carried by an `Edge`-shaped object. It is an **Edge-level**
   capability (authoring a 3D boundary from two planar sketch-derived edges), not a patch
   fill — but it is the clearest answer to "a special type the wizard cannot reach". Cost M
   (an `Edge` input representation + a panel affordance, §2b.6); no new geometry to write.
2. **Keep `Patch`'s fill choice implicit (edge count).** The wizard already has the only
   two fills that fit the `Patch` contract (16 poles, `SilkMachinery` subgrid, the P-checks):
   the quad fill and the pointed fill. Neither `ControlGrid44_flow` nor any 64/N-star type
   changes the *count*, so none of them can slot in silently.
3. **Expose `ControlGrid44_flow` only behind an explicit, clearly-labelled toggle** (e.g. a
   `Flow` boolean on `Patch`), and label it as *"tangles the interior"*, **not** as a G2
   option. It is (a) MEASURED stable, (b) already 16 poles so it clears the whole existing
   contract, and (c) genuinely different from the current quad fill. Effort is S because
   `SilkPatch._quad_fill` is the single seam (`SilkPatch.py:417-503`).
4. **Do NOT surface G3 or Fair blends** until the crashes in §3.2 are fixed *and* an oracle
   that measures the claimed continuity exists. A blend-variant picker would have to be its
   own affordance on `Blend`, not a count-driven choice, and it would be exposed to a type
   that currently raises on ordinary input.
5. **Keep the remaining `ControlPoly4_*` modes as `Edge` internals.** `SilkEdge.Edge` already
   wraps `ControlPoly4_2N`, `ControlPoly4_3L` and `ControlPoly4_FirstElement`
   (`SilkEdge.py:70-122`); `_2P` and `_GridEdge` are unreachable and should stay that way
   unless a concrete sketch shape needs them. The user-facing primitive is **Edge**, and the
   wizard already offers it. (`_2X4P` is promoted to item 1.)
6. **The corner / N-star candidates fit the `CornerBlend` contract (36 poles, 4+ inputs),
   not `Patch`.** If the contribution-corner story grows, `ControlGridNStar66_NSub`
   (general N) is the prize; but it needs (a) a degenerate-input guard, (b) a no-base-surface
   plan (it cannot subdivide through `SilkMachinery`), and (c) a new oracle. That is a
   separate build ticket, not an exposure of the current wizard.
7. **Drop the dead/superseded classes** (`ControlGrid64_3`, `ControlGridNStar66_StarTrim`,
   the two root-module N-Star subclasses, the `ControlPoly6_*` family) from the "candidate"
   set so the inventory stops implying they are reachable options.

**One-line policy:** *the first reachable capability the wizard should add is `2X4P` on
`Edge` (compose two planar edges into a 3D boundary) — it is measured stable and oracle-green
and needs only an input/affordance; the only new patch fill worth exposing is `flow`, and only
as an explicitly-labelled interior tweak; everything else is a blend variant (blocked on
bugs), an Edge internal, or a corner type that needs its own object and oracle.*

---

## 5. Confidence and open questions

**High confidence (MEASURED + READ):**
- The three `*_test.py` modules are experiments, not conclusions (§1).
- `blend_poly_2x4_1x6` gives exact C0 endpoints and preserves G1 direction; G2/G3/Fair are
  unproven labels, and G3/Fair crash on ordinary inputs (§3.2).
- `ControlGridNStar66_NSub` builds shapes for N=3,4,5 on sane input and crashes on a
  degenerate one (§3.4).
- `ControlGrid64_2Grid44` builds with a shared edge and crashes (unbound `seam_0`) without
  one (§3.3).
- **The missing Edge-level capability is `ControlPoly4_2X4P`** (`ArachNURBS.py:2379`) — the
  **newest** sketch→edge builder (2026-05-17) — which composes two sketch-derived planar edges
  into one 3D edge; our vendored `ArachNURBS.py` is byte-identical to `upstream/master` for
  every sketch→edge builder (§2b.2/§2b.3).
- **`2X4P` is MEASURED recompute-stable and MEASURED fully `check_edge`-green** once carried by
  an `Edge`-shaped object with `Sketches = [Poly4_0's sketch]`; the composed geometry is 4
  poles, unit weights, 3 legs, a valid non-null Shape, and its endpoint deltas against the
  driving sketch are `0.00e+00 / 0.00e+00` (§2b.4/§2b.5).
- **`SilkEdge` routes a 2-sketch selection to `ControlPoly4_2N` unconditionally and uses only
  the first two sketches**, so the panel is capped at two (`EDGE_MAX=2`) but the command path
  silently drops a third+; and no route composes two edges (§2b.7).
- The `ControlPoly6_*` 6-pole family is **out of scope** (the human's call): it fits no
  `Edge`/`Patch` contract and has no consumer (§2b.8).
- The exact oracle contracts each new type must satisfy (§0).

**Lower confidence / not settled by this review — with the experiment that would settle it:**

1. **True continuity of the blend and of any candidate.** No test measures G2/G3. *Experiment:*
   sample the blend's curvature against the patch boundary curvature at the seam and
   compare (a `check_blend` extension that computes both, not one that re-runs the blend).
2. **N-star wedge-seam continuity and whether the star is usable at all on real Silk
   subgrids.** The probe used synthetic 6×6 nets; the real inputs would be the corner cells
   of four silk patches. *Experiment:* build the `Tests/corner_model.py` 4-patch junction,
   feed its corner cells to `ControlGridNStar66_NSub`, and check the seams.
3. **`ControlGrid44_flow` behaviour versus the current quad fill on a real curved patch.**
   The probe confirmed it builds; it did not compare the surface to `_quad_fill` or test the
   `mirror_*` toggles. *Experiment:* build a curved `SilkPatch`, swap in the flow fill, and
   run the P-checks + a pole-diff against the default.
4. **Whether any 64-grid composite is needed by the workflow at all.** They all produce 24
   poles, which no current object consumes. *Experiment:* none — this is a design decision
   for map #1, not a measurement.
5. **`blendG3`/`blendFair` "on a curved input" fates.** `blendG3` returned 6 poles on the
   curved control but the G3 continuity it computes was not evaluated; `blendFair` has not
   been observed to return on any input. *Experiment:* call each on the exact strip rows the
   `Blend` object feeds, and run the B-checks against the result.
6. **Does a composed `2X4P` edge survive the full Edge → Patch chain?** §2b.5 MEASURED the
   composition itself and `check_edge` on the composed geometry, but there is **no compose
   branch in `Edge` today**, so I could not drive the composed edge through the real `Edge`
   object *and* through `Patch`'s P-checks end-to-end; nor did I measure a **curved** (`2N`)
   or `FirstElement` `Poly4_0` (only a planar `3L` one). *Experiment:* add a temporary
   compose branch, build four composed edges, feed them to `create_patch`, and run
   `check_patch` — confirming the composed 3D boundary survives `_quad_fill` and the P2
   boundary match, not just `check_edge`. The **how-would-the-user-pick-two-inputs** question
   (§2b.6) is a design decision for map #1, not a measurement.

**Demoted to a footnote (out of scope):** whether `ControlPoly6_2N` (a 6-pole 2-node-sketch
edge) is worth having, and whether a pair of 2-line node sketches misroutes to
`ControlPoly4_2N`'s unbound `cir0` (`ArachNURBS.py:2004`), are no longer review questions —
the human has ruled the 6-pole family out of the edge→patch→blend workflow (§2b.8). If ever
revisited, the probe is: build two 2-line sketches, select both, run `Silk_CreateEdge`, read
the console.

**The honest summary:** at the *fill* level the wizard is not missing a stable,
contract-fitting candidate — the one such candidate (`flow`) is a visual interior tweak, not a
continuity level; the rest are blend variants that currently crash (G3, Fair), composite/corner
types with no oracle and no consuming object (64-grids, N-star), or Edge internals the wizard
already wraps. **But item C ("special types unreachable from the wizard") does have a real,
ready answer at the Edge level: `ControlPoly4_2X4P`** — the newest builder, measured stable and
oracle-green, needing only an input representation and a panel affordance. So item C is not
"expose more buttons": it is **first** "expose `2X4P` on `Edge`" (§4 item 1), **then** "expose
`flow` on `Patch`, labelled honestly", plus build tickets for a corner/N-star object and for
fixing + testing the blend variants. Note the wording: item C says "special *patch* types";
`2X4P` is an Edge-level capability, so it answers the *spirit* (an unreachable special type)
rather than the letter.

**On the sketch → Edge question specifically:** the unsupported feature the human means is
**`ControlPoly4_2X4P`** (`ArachNURBS.py:2379`) — the **newest** sketch→edge builder
(2026-05-17), which composes **two sketch-derived planar edges into one 3D edge** (plan from
one, elevation from the other). It is exactly the case item C is looking for: an Edge-level
capability that is (a) genuinely missing from the wizard, (b) MEASURED stable, and (c)
MEASURED to pass the full `check_edge` oracle once carried by an `Edge`-shaped object — so
exposing it costs an input representation + panel affordance (M), not new geometry. The
`ControlPoly6_*` 6-pole family, by contrast, is **out of scope** (the human's call): it is old,
fits no `Edge`/`Patch` contract, and has no consumer. **The answer to "which special type
should the wizard reach for first" is therefore `2X4P` on `Edge`, ahead of `flow` on `Patch`.**

---

## Appendix — the measurements, inlined (the document stands alone)

The probes were run in a **separate headless `freecadcmd` process** (FreeCAD 1.1.3, Libs
1.1.3R44987); the live GUI and its XML-RPC port 9875 were not touched. `ArachNURBS.py` does
`from FreeCAD import Gui` (`ArachNURBS.py:28`), so each probe first stubs
`FreeCAD.Gui = types.ModuleType("FreeCAD.Gui")` and puts the Mod directory on `sys.path`. The
scratch scripts themselves are **not part of the record** (they lived in a temp dir that will
not survive); what follows is everything they established, so no external path is needed to
read it.

**Inputs.** A "carrier" is a `Part::FeaturePython` with `Poles` (a `PropertyVectorList`) and
`Weights` (a `PropertyFloatList`), which is the only shape the composite builders read.
Fixtures were deliberately chosen to be able to fail:

- a 4×4 grid `grid44(x0, y0) = [(x0 + i*10, y0 + j*10, (i-1.5)² + (j-1.5)²) for i,j]` (paraboloid,
  non-planar); two of them offset in `y` so one column is genuinely shared.
- a 6×6-per-wedge net `subgrid(k, N) = [(10*i·cos(2π(k + j/5)/N), 10*i·sin(2π(k + j/5)/N),
  3·sin(π i/5)) for i,j in 0..5]` — non-planar, so the N-star centre is off the seam.
- straight vs curved blend rows: `p0 = [(0,0,0),(4,0,c),(7,0,c),(10,0,0)]`,
  `p1 = [(10,0,0),(13,0,-c),(16,0,-c),(20,0,0)]` with `c = 0` (collinear) and `c = 1`.

**Results (MEASURED):**

| probe | input | result |
|---|---|---|
| `ControlGrid44_flow` | `grid44(0,0)` | 16 poles, non-null Shape, recompute-stable |
| `ControlGrid64_3_1Grid44` | `grid44` (corner 0 and 2) | 24 poles, non-null Shape, recompute-stable |
| `ControlGrid64_2Grid44` | two grids sharing an edge | 24 poles, non-null Shape |
| `ControlGrid64_2Grid44` | two grids NOT sharing an edge | `UnboundLocalError: seam_0` at `ArachNURBS.py:7484` |
| `ControlGrid66_4Sub` | 4 cubic-6 rows | 36 poles, non-null Shape |
| `ControlGridNStar66_NSub` N=3,4,5 | 3D `subgrid(k,N)` nets | `StarGrid`=N, `Legs`≈25N, **non-null Shape** |
| `ControlGridNStar66_NSub` N=3,4,5 | degenerate flat nets | `Part.OCCError: Both points are equal` at `:9267` (control) |
| `blend_poly_2x4_1x6` | straight `c=0` | OK, 6 poles |
| `blend_poly_2x4_1x6` | curved `c=1` | OK, 6 poles; endpoints exact (`|Δ|=0.000e+00`), start tangent `dot=1.000000`, inner-leg height `0.6468` |
| `blendG3_poly_2x4_1x6` | straight `c=0` | `ZeroDivisionError` at `:936` |
| `blendG3_poly_2x4_1x6` | curved `c=1` | OK, 6 poles |
| `blendFair_poly_2x4_1x6` | straight and curved | `UnboundLocalError: scale_1i` on both |
| `ControlPoly4_2X4P` | `Poly4_0` plan on XY, `Poly4_1` elevation in XZ (both `3L`) | 4 poles `[(0,0,0),(10,0,-5),(20,10,-15),(30,0,0)]`, unit weights, 3 legs, valid Shape, **recompute-stable**, `reverse` mirrors |
| `ControlPoly4_2X4P` | both polys in the **same** plane | output **equals `Poly4_0` exactly** (every elevation is 0); no error |
| `ControlPoly4_2X4P` | `Poly4_0.object_type = "ControlPoly4_2P"` | `NameError: name 'please_read_message_above' is not defined` (the deliberate self-poison) |
| `SilkChecks.check_edge` on the composed poles | in an `Edge`-shaped carrier, `Sketches=[Poly4_0's sketch]` | **all five checks green** — structural, E1 (`0.00e+00`), E2, E3, E4 |

The **control** runs are the point: `blend_poly_2x4_1x6` was re-run alongside the failing
G3/Fair calls in the same process (it built both times), and the N-star was run on a
non-degenerate *and* a degenerate net (it built on the first, raised on the second) — so "it
built" and "it crashed" are both statements the instrument could have contradicted. Likewise
the `2X4P` probe ran the composition on a genuinely-3D pair (built) *and* a coplanar pair
(collapsed to `Poly4_0`), so the "elevation is read" claim is falsifiable, not assumed.

The `2X4P` findings in §2b.4/§2b.5 are MEASURED (rows above). The sketch→Edge **provenance**
claims in §2b.3 are READ from git (`git log -S`, `git diff upstream/master`). The
`ControlPoly6_*` family is out of scope (§2b.8); §5 item 6 records what the `2X4P` probe did
**not** cover (the end-to-end `Patch` chain, and curved/`FirstElement` `Poly4_0` inputs).
