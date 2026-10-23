# Silk Workbench — Agent Notes

## Agent skills

### Issue tracker

GitHub Issues on `msprengholz/Silk` (the fork), via the `gh` CLI — always pass `-R msprengholz/Silk` or the `upstream` remote is inferred. See `docs/agents/issue-tracker.md`.

### Triage labels

Default five-role vocabulary (`needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, `wontfix`), plus `wayfinder:*` labels. See `docs/agents/triage-labels.md`.

### Domain docs

Single-context: `GLOSSARY.md` + `docs/adr/` at the repo root. See `docs/agents/domain.md`.

### Discussion vs implementation (standing process)

Wayfinder discussion and the code that grows from it live in **separate contexts**. The main session is for discussion, decisions, and recording them (map #1 on the tracker). Implementation is always **handed off**: each build ticket goes to a **subagent in a fresh context** (per-ticket, TDD + oracle, returns a diff + report), reviewed before the ticket is marked done. Hand every build off to a subagent; keep code out of the discussion context.

### Measurement rule (standing)

A measurement that decides a product choice names its instrument, keeps its raw
output, publishes its error floor, and carries either a known-answer calibration
or an independent cross-check. A number quoted from a label, with no preserved
output, is not a measurement.

### Continuity instrument (corner stage)

Two instruments, one calibrated. `Tests/g2_oracle.py` samples a caller-supplied
seam and finite-differences it (`c0`, `g1_deg`, `k_gap`, `twist_gap`);
`Tests/silk_nurbs.py` + `Tests/continuity_analytic.py` evaluate the stored
control net exactly, **carrying the weights**, and add the combinatorial
`c0_controlnet`. `Tests/continuity_calibration.py` is the soundness harness:
`solve_uv`'s floor (4.5e-13 mm), every quantity's error floor, a known G1 angle,
a known curvature jump -- which is also the proof that **`g1_deg` cannot
establish G2** -- and an independent reflected-3D cross-check. **`k_gap` is the
G2 evidence.** `twist_gap` is measured in a common frame (#101): the along
tangent is the caller's correspondence direction and both normals are taken
on the same side, so the figure is invariant to a reversed seam
correspondence. Before #101 the frame leaked and a smooth seam read ~2|tau|
(visible in #100's raw edge-blend data, where a seam with `k_gap` 2.1e-6 read
`twist_gap` 5.3e-3); `Tests/continuity_calibration.seam_torsion_reversal`
pins the corrected frame on a seam that carries a known 1 /mm torsion, measured
both ways. `k_gap` is untouched by that frame (an absolute difference of
scalars). No test asserts a continuity label
(`test_no_continuity_threshold_in_suite`); the manual scripts
(`Tests/g2_demo_corner.py`, `Tests/g2_corner_measurement.py`,
`Tests/g2_corner_solve.py`, `Tests/g2_edge_blend_probe.py`,
`Tests/g2_corner_fill_continuity.py`) carry `MANUAL = True` and are asserted
reachable. Measured reference corner (`Silk_Demo_01`): C0 exact, G1 <= 0.48 deg,
**not G2** (`k_gap` <= 3.1e-2 /mm). #100 then measured what G2 would take
(`docs/research/silk-corner-g2.md`): **the maths is not the limit** -- on a
junction of compatible neighbours a control-net solve recovers the exact G2
continuation (`k_gap` 6.0e-17), where the shipped two-row average stops at
4.1e-4; on the demo's legacy neighbours the attainable `k_gap` is 7.1e-3 /mm,
set by the neighbours' mutual incompatibility (#102). FreeCAD's
`Surface::Filling` at `BoundaryOrder = 2` is **not** G2 here and measures worse
than `= 1` (`k_gap` 1.7e-1 vs 8.2e-2). #106 then measured the strips' interior
as the lever (`docs/research/silk-g2-feasibility.md`): freeing each seam strip's
second-order row (plus the corner's 4 central poles) takes the four demo
junctions from (7.117e-3, 4.999e-3, 3.375e-3, 2.303e-4) to (2.764e-4, 4.689e-5,
7.636e-5, 1.026e-5 /mm) at <= 0.52-cell motion, no fold -- but one 6-pole row
cannot match the seam pointwise, so station-zero needs 5-90 cells and folds.
Pinned in `Tests/test_g2_feasibility.py` (+ port `Tests/g2_feasibility_model.py`).
**G2 is parked in #104; corners stay G1, fold-free** (#97/#100/#102/#106).

## Core Object Architecture

Three types, one per process step (#42): `Edge` → `Patch` → `Blend`.
`Patch44` / `Patch33` / `BlendStrip` survive in their modules only
as **old-document restore shims** (class + view provider) — nothing
creates them anymore.

### Edge (`SilkEdge.py`)
- `Part::FeaturePython` (renders Shape in 3D view)
- Properties: Sketches (PropertyLinkList), Poles (4 vec), Weights, Legs, object_type="Edge"
- Display toggles: ShowCurve, ShowPolygon
- Custom view provider: `EdgeViewProvider` (custom tree icon)
- Sketches are linked via `Sketches` property (not tree children — Part::FeaturePython can't nest)

### Patch (`SilkPatch.py`)
- `Part::FeaturePython` (not group); object_type="Patch"
- One variable-length `Edges` link list (PropertyLinkList) is the single boundary input; `execute()` picks the fill from the count (4 edges → quad, 3 edges → pointed — same 16 poles as the legacy fills at 1e-6)
- **The stored `Edges` list IS the boundary cycle** (#67). You may supply it in any order — panel click order, hand-order in the data tab, an old file's saved order — and `execute()` writes the resolved cycle back with `loop_order` when, and only when, it differs. So `Edges[k]` is boundary side `k` **by construction**: `check_patch(p, list(p.Edges))` is the honest oracle call for any input order. A non-cyclic list is *not* stored (a non-closing one is refused, list untouched). Visible consequence: the data tab shows the normalized cycle, not the raw click order. An already-cyclic list takes the byte-identical no-op path (legacy pole parity `0.00e+00`, chain ground truth), and the write is a one-shot fixed point: one write per execute, then nothing.
- The 3-edge pointed fill is **not** normalized — its Patch33 parity rides on the list it is handed. Careful with the claim here: it is order-independent only in the sense that **every** ordering builds poles (6/6). Its *output* is not order-independent, and it does **not** satisfy the `Edges[k]`-is-side-`k` invariant above — on a curved corner triple (`Seam_X`/`Seam_Y`/`Seam_Z`) it builds 6/6 but is oracle-red on 6/6 (`C1_corner_order`, `C2_boundary_match`). Pre-existing, untouched by #66/#67, tracked in #68. Do not cite it as a verified invariant.
- 16 poles + 16 weights (4×4 grid)
- **Subdivision is two NAMED band edges per axis** (#82), not a split
  list: `USplit1` / `USplit2` / `VSplit1` / `VSplit2`
  (`App::PropertyFloat`). `Split1` is the parametric-0 end's band edge
  and holds `0.0` for "no band at that end"; `Split2` is the
  parametric-1 end's and holds `1.0`. So `Split1 = 0, Split2 = 1`
  reads as "no split on this axis" and the SENTINEL IS THE AXIS
  ENDPOINT. The properties' defaults are the sentinels -- a patch
  nobody has blended stays one whole surface (0 subgrids, 1 face);
  0.1 / 0.9 are the widths `ensure_band_split` writes into the ONE end
  that needs them.
- Subgrids stored internally in `_subgrids` and `_subsurfaces` (not in FreeCAD tree)
- Display toggles: ShowSurface, ShowGrid, ShowSubgrids, AutoHideBlend
- Linked Blends auto-hide the blended subgrid strip via `_HiddenSubgridIdxs`
- Subdivision / band / hidden-cell bookkeeping / compound display all delegate to the shared machinery core (`SilkMachinery`)
- Custom view provider: `PatchViewProvider` (custom tree icon)

### Blend (`SilkBlend.py`)
- `Part::FeaturePython`; object_type="Blend"
- Properties: PatchA, PatchB (PropertyLinks), Edge (optional seam pin), tolerance, Poles (24), Weights, Legs
- Auto-detects shared edge between two patches (robust against degenerate pointed corners)
- Auto-updates when a patch's band edges change
- Fed only patch subgrid cells — never a Blend
- Custom view provider: `BlendViewProvider` (custom tree icon)
- Surface built via `AN.CubicSurface_64` (NOT manual knot insertion)

### Corner Blend (`SilkCorner.py`)
- `Part::FeaturePython`; object_type="CornerBlend"; input = `Strips`, the
  ring `Blend`s around one junction — **four** at a 4-patch junction,
  **three** at a 3-patch hard corner (the triangular patch beside the quad is
  then built by the corner stage from the ring itself; the user never picks
  upstream types) — **in any order**.
- **The corner stage builds ONE OF TWO CONSTRUCTIONS, and the rolling one
  is the DEFAULT** (#119; the owner, 2026-10-21: *"the rolling corner fill
  should be the default fill!"*). The switch lives in the OPS LAYER
  (`SilkWorkflowOps.create_corner_blend(..., construction=...)`):
  `"rolling"` (the default) = the quad over the ring's four members plus the
  triangular patch beside it, the quad NOT covering the tri's cell (#128);
  `"shipped"` (the fallback) = the 66 with the spiderweb member, byte for
  byte the construction of before #119. **What those two words mean is stated
  once, in `docs/adr/0006-rolled-corner-is-two-patches.md`** — read it before
  touching the corner; the numbers below are that ADR's, not a second
  definition. No new button: the wizard's corner step and the toolbar command
  both call the ops layer, and the PANEL offers the construction as a
  selector (build-time choice; read-only once the corner exists) and SAYS
  WHICH ONE WAS BUILT — a refused rolling corner no longer falls back
  silently, the status line carries the refusal's own wording (#128).
  `CornerBlend.Construction` records what the stage built (`"rolling"` /
  `"shipped"`; empty on an older object = the shipped machinery, read by
  `SilkCorner.corner_construction`). The tri's FACE is its own net's
  `CubicSurface_64` by DEFAULT (the construction the maintainer's files
  store) and a FreeCAD `Surface::Filling` is the selectable option
  (`member_face="fill"`, the owner's replacement of that surface). The
  owner's two choices ride the ops layer and the panel: WHICH CORNER carries
  the tri (`MemberPatch` / `MemberCorner` name that corner's patch and grid
  corner, honoured on the rolling path too) and the LEADER PER SEAM
  (`leaders={seam: mm}`, one panel editor per seam of the ring).
- **THE CORNER IS TWO PATCHES** (#128/#130, stated once in
  `docs/adr/0006-rolled-corner-is-two-patches.md`): the **quad** (a 66 over
  four ring members — the two cut-back cells, the third **uncut** blend, and
  the triangular member's net read REAL-ROW-FIRST) and the **tri** (a patch
  of its own, sharing **one curve** with the quad, covering none of its area),
  plus **five preserved pieces**. The division is carried by the patch that
  carries the tri: it holds TWO cuts per axis — the SETBACK (band edge) and
  the LEADER (`ULeader1/2`, `VLeader1/2`) — so its cell is the region BETWEEN
  them, its two ring corners are that cell's two MIXED corners, and
  `ring_corner_gap` reads it OPEN while the other two read CLOSED (it is the
  one patch per corner where two different ring corners are CORRECT, #127).
  Cube-corner fixture, default build, leader 0.25 / setback 0.1: **0 of 630
  coincident pole pairs** on the 6x6, no collapsed side, **0/0/0 normal-field
  flips at n=39/81/150 without `smooth_degenerate_cap`** (a byte-identical
  no-op: the built 6x6 IS the raw assembly; the controls that make the
  reading worth something are in `Tests/test_two_patch_corner.py` — the
  SHIPPED raw assembly folds 19/23/24 and its built form reads 0), seam
  `k_gap` 7.8e-15..1.6e-14 /mm exact and 0.0067..0.0093 sampled (floor 0), the
  cut C0 1.4e-17..5.6e-17 mm, the document settles (0 Touched, 0.0001 s a
  pass, poles move 0.000e+00), areas 66 0.046713 mm² / tri 0.020609 mm². The
  tri's interior reads **7.5 %..53.5 %** of the corner's extent from the 66
  (his 16..62 %): the minimum is BELOW his floor, so that percentage is a
  READING and the acceptance is non-overlap, one shared curve and no fold —
  see the ADR.
- **The setback no longer rides along with the leader.** The rolling cut is
  the carrying patch's own property, so the band edge stays the user's
  setback and the third blend is not cut at all. `apply_corner_choices`
  writes the leader where the corner's RECORDED construction reads it (the
  leader cut for `"rolling"`, the band edge for `"shipped"`) and CLEARS a
  leader cut left on a patch that is no longer the carrying one — a second
  cut on a patch that carries a ring PAIR opens that pair's shared corner.
- **The rolling cut must clear the setback on BOTH axes of the carrying
  patch.**
  A leader resting on the band edge is INERT (`axis_cuts`), the cell on that
  axis stays the band's, and the assembly either refuses or comes out
  degenerate (measured: 4 coincident pole pairs). The stage refuses that by
  name (`the rolling leader cannot cut the member's cell: its V axis carries
  no leader cut that clears the setback`), atomically, and the fallback is the
  shipped corner. That is also why the default leader is **0.25**, the video's
  number, and not 1/16: at the default 0.1 band a 1/16 leader has nothing to
  cut. A 4-valent ring refuses the rolling construction outright — it has no
  third, uncut seam and no triangular remainder.
- A `Surface::Filling` whose boundary lives on a Silk object needs that
  object's shape to be a **COMPOUND** (the face + the boundary curves):
  a fill's boundary is a LINK to a sub-shape, and a FACE's sub-names are
  resolved through the shape's element map — a replaced face breaks them
  ("?Edge1") and the fill goes Invalid for good. A compound's children are
  named BY POSITION, so the names survive the replacement. The names are
  positions in the SHAPE'S edge list (`Edge%d` of `shape.Edges`), not in the
  list of non-degenerate edges: a renumbered survivors list hands the fill
  the collapsed edge whenever that edge is not the last one (#119).
- **The LEADER CUT is the rolling construction's own cut** (#119 added it,
  #128 shipped it). `SilkPatch` carries `ULeader1/2`, `VLeader1/2` — a SECOND
  cut per axis end, additive and default-off (sentinels per slot, so a patch
  without one reads exactly the two band edges it always read; every existing
  document is byte-identical). `SilkMachinery` reads it (`axis_cuts`,
  `build_intervals`, `axis_intervals`, `corner_cell_index`, `corner_cells`,
  `band_extent`, `band_cells`), the corner cell is then the interval BETWEEN
  the setback and the leader, a leader that does not clear its band edge is
  INERT (`axis_cuts`) and named (`leader_cut_problem`), the property name is
  one expression (`leader_cut_prop`), and `Tests/test_leader_cut.py` pins all
  of it. The ROLLING construction writes the leader here, on the member patch
  only; the SHIPPED construction still writes the band edge (that is where
  the construction of before #119 cut), and a corner that carries no recorded
  construction reads as shipped.
- **The cut is placed by LENGTH, and its sides are EQUALISED (#129).** The
  owner's rule (2026-10-22): *"ideally both segment lengths should be close
  to the same absolute length (not u or v values between 0 and 1, but the
  actual length in eg. mm). this ensures a neat, closer to even sided
  triangle"*. So `create_corner_blend` / `create_rolling_corner_66` take
  `leader` in **mm from the junction corner** (`leaders={seam: mm}` per
  seam), and the **default is `leader=None`: the two cuts that bound the
  triangular member are equalised** — `equal_cut_length` puts both cut sides
  at the GEOMETRIC MEAN of the length the parameter default (`ROLLING_LEADER`
  = 0.25) gives them, the length at which the triangle keeps its area. Both
  refusals are by name and atomic: a leader inside its setback (an inert cut)
  and a length longer than the band can carry say the number they refuse. The
  readers are `SilkMachinery.seam_length` / `seam_parameter_at_length` (a
  chord sum, and its inverse, on the patch's OWN base-surface seam curve —
  64 stations, 1.7e-6 relative floor), `SilkWorkflowOps.seam_cut_reach` (the
  seam's setback / reachable maximum), `seam_cut_length` (the tri's own side,
  mm) and `seam_cut_at_leg`; the panel's per-seam editor is in mm too
  (`CORNER_LEADER_TIP`). On a unit-axis patch mm IS the parameter, so the
  cube corner is byte-identical (worst |Δ| 0.000e+00 on all 36+24 poles and
  weights) and every caller that passes `leader=0.25` there reads the corner
  it read before. Measured on `CB_J1_FrontTopRight`
  (`Tests/corner_even_cuts.py`, MANUAL, artifact
  `Resources/Test_files/_inspect/demo_corner_even.FCStd`): the cut sides went
  9.302915 / 32.677217 mm → **17.435446 / 17.435446 mm** (residual 2.9e-13
  mm), the tri/quad areas 278.09 / 469.17 (0.5927) → 293.62 / 567.06
  (**0.5178**, his 0.2776), the tri's interior → quad 1.55..14.55 % →
  **3.51..37.08 %** of the corner's extent (his 16..62 %), the quad's
  worst/best pole pitch 32.74 → **26.93**, with 0/0/0 normal-field flips and
  0/630 coincident pairs across it.
- **The PANEL offers the equal-sided default as a value (#129's rule, made
  reachable).** Each seam's editor is a length in mm from the junction
  corner (`Leader (mm)`), and its own **0 reads `equal`**
  (`CORNER_LEADER_AUTO` / `setSpecialValueText`): that is the ask for the
  equalising rule, so a seam nothing has cut yet SEEDS at `equal`
  (`_seam_seed` returns the sentinel instead of the length the old parameter
  default landed at) and an untouched page builds the equal-sided triangle.
  `corner_choices()` hands `create_corner_blend` only the seams carrying a
  NUMBER, and no leaders IS the rule (`leaders=None`); `apply_corner_choices`
  runs the same rule on the member patch's unnamed seams (`equal_cut_legs`,
  shared with `create_rolling_corner_66`), so moving the member onto a patch
  nothing has cut yet still cuts the cell back on both axes. The status line
  names the construction built AND the tri's own sides it was placed at
  (`_built_cut_lengths`), and the refusal's own wording when the requested
  construction was refused. Measured by
  `Tests/test_corner_choices.py`
  (`test_the_panel_places_the_tri_sets_the_setback_and_defaults_to_equal_sides`,
  MANUAL, artifact
  `Resources/Test_files/_inspect/demo_corner_ui.FCStd`, LEFT OPEN): the
  placement selector `P_Top[3]` → tri 293.615537 / quad 567.064425 mm² at
  (58.0414, -66.6667, 64.6564), `P_Front[2]` → tri 57.985728 / quad
  311.440225 mm² at (16.1198, -75.8895, 45.7615); the setback editor 30/30 mm
  → tri 129.683005 mm² (cut sides 25.037835 / 5.055816), 50/50 mm →
  1233.354808 mm² (45.037835 / 25.055816); the untouched page →
  **17.435446341 / 17.435446341 mm (difference 2.949e-13 mm)**, and the
  shipped fallback's status line carries the refusal word for word.
- Builds the real subgrid chain — `SubGrid33_2Grid64` ×4 →
  `ControlGrid66_4Sub` → `CubicSurface_66` — ported into `SilkMachinery`
  (`corner_ring`, `corner_grid`, `subgrid33_2grid64`, `control_grid66_4sub`)
  from the legacy classes. Those stay **inert restore shims** and serve as
  the pole-for-pole test oracle (parity `0.000e+00`).
- A strip's `Poles` is flat `V*6 + U` — 4 rows × 6 poles, corners at flat
  `{0, 5, 18, 23}` — exactly the grid `SubGrid33_2Grid64` reads. Upstream's
  own notes call it a "6x4 grid": the same object, axes named differently.
  It is **not** a transpose, and nothing needs transposing.
- `corner_ring` fixes the ring start (earliest in the document; adjacency =
  a shared Patch) and `corner_grid` normalizes direction, so the fill does
  not depend on click order — but the direction is **not** free (the legacy
  chain's output depends on it).
- Refuses **by name and creates nothing** unless it gets four strips forming
  one ring, or three strips forming a 3-cycle (the #80/#83 lesson: never park a
  dead object). An existing corner for the same strip set is an idempotent no-op.
- **A rolled corner carries TEN ROLES, not five (#130).** Measured from
  `Silk_CopyPasta_29`: 3 ring blends + the tri + the quad + **FIVE preserved
  pieces** -- one CELL of a ring patch each, three from the patch that carries
  the tri and one from each of the other two. The cell is pinned by the file:
  the cell ONE STEP BEYOND the patch's inner cell, away from the junction
  (`SilkMachinery.preserved_piece_cells`), where the inner cell is the
  member's cell on the tri's patch and the corner cell on the others -- on the
  cube fixture that is 0.15x0.75, 0.75x0.15 and 0.75x0.75 mm² beside the
  0.15x0.15 mm² tri, plus 0.9x0.9 mm² on the two other patches. Each piece is
  a `SilkCorner.PreservedPiece` object -- the patch's OWN cell read through
  `Patch.getSubgrid` and built with the patch's base-surface construction, so
  it is a segment of the same Bezier, not a re-fit -- recorded on the corner's
  `Pieces` link list. They are C0 to everything they abut by construction
  (measured 5.6e-17..1.4e-14 mm across the cube and the demo). The **shipped**
  construction has no separate member and therefore no pieces (byte
  identical), and a 4-valent ring has no member either.
  `Tests/test_preserved_pieces.py` pins the ten roles, the cells, the nets,
  the C0 table, the settle and the shipped/4-valent pairs.
- **A rolled corner is REVERTIBLE, and more than one can live in a document
  (#131) -- measured on the demo, `Tests/test_two_rolled_corners.py`.**
  `CornerBlend` keeps a WRITE LOG (`_CutRecord`: patch|property|before|written)
  of every LEADER CUT it places -- the ops layer records it at build and at the
  panel's `apply_corner_choices` -- and `SilkCorner.release_corner`, fired by
  the corner's own one-shot `_CornerDeleteWatcher` (`onDocumentRestored`
  installs it too), removes the corner's own roles (the tri, its fill, the five
  pieces) and puts each cut back to the value it FOUND. A slot whose value has
  changed since is reported and left alone, not overwritten. Two corners on
  the demo (J1 on P_Top, J2 on P_Bottom, sharing P_Front and P_Right through
  B_FR, neither cut) both roll, both read their own cells, and the document
  settles. Delete J1: the survivor's 36 poles, weights, member and five pieces
  read `0.000e+00`, its cuts stay, P_Top's cut goes back to its sentinel
  (subgrids 12 -> 6, hidden `[0,3,5,7,10]` -> `[0,2,3,4,5]`). Delete J2 as
  well: 41 objects again and **0 differences** across every patch's cuts,
  poles, weights, subgrid count and hidden set and all 8 strips' poles. A
  shared patch keeps its piece TWICE (both corners' `beyond_both` is the same
  cell: 3368.106687 mm^2 on P_Front, 6692.122665 on P_Right twice) -- recorded,
  not deduped.
  **The limit is ONE LEADER PER AXIS END, and it is the owner's decision.** A
  corner's cut is a claim about a whole axis end of its member patch, so two
  junctions that share one end cannot both be rolled there: J1 and J3 both
  carry the tri on P_Top and want `P_Top.ULeader2` (0.643019 vs 0.641844 mm)
  -- J3 falls back to the shipped corner. Worse, one corner's cut can break
  another's ring: J2 then J4 -> J4 builds NOTHING (its ring reads the end J2
  cut), and J3 then J4 -> J4 rolls while J3's net goes EMPTY. The demo's pair
  matrix (both build orders, `Tests/two_rolled_corners.py` section 3) reads:
  J1+J2, J1+J4, J2+J3, J4+J1, J4+J2, J3+J2 two rolling; J1+J3 shipped
  fallback; J2+J4 and J3+J1 nothing; J3+J4 one empty. A LIST of cuts per axis
  instead of one property per end is what lifting this takes, and it is not
  implemented.
- **The 3-valent path builds (measured on the cube-corner fixture).** The
  member is derived from the patch's ring **corner cell** (not its full base
  net), and a multi-corner match is admitted by `pair_common` only when it is
  the member's own collapsed end row (`{0,1}` or `{2,3}` at one end) — two
  distinct shared corners, cross-column apexes and facing collapsed rows still
  refuse by name. `Tests/cube_corner_model.py` +
  `Tests/test_cube_corner_3valent.py` carry the contract (36 poles, 1+ face,
  idempotent, reversed ring identical) and the raw instrument readings. The
  member is a faithful, term-for-term port of upstream's stored members
  (ticket-foldfix; `Tests/test_triangular_member_calibration.py` pins exact
  parity on the demo's four stored members and on synthetic weights), and
  `SilkMachinery.smooth_degenerate_cap` re-solves the two member-side interior
  rows of the assembled 6x6 from the transfinite (Coons) fill of the corner's
  own boundary loop — upstream's subgrid chain extrapolates past the collapsed
  row and folded the cap. Its NON-degenerate sibling is
  `SilkMachinery.smooth_folding_interior` (#129): a 6x6 with **no** collapsed
  side that still FOLDS (`net_fold_count`, read on the exact net) gets all 16
  interior poles re-solved against the same Coons fill, boundary and weights
  held fixed. Upstream's interior is a scale-relative tangent-ratio
  extrapolation fitted to two rows per member, so on a cell whose own net is
  anisotropic the two one-sided estimates diverge and their average lands
  outside the boundary quad. **It is a SAFETY NET, not part of the rolling
  construction**: on the built rolled corner the 6x6 IS the raw
  assembly, a fold-free net is returned as the SAME lists, and the cube
  fixture is byte-identical — the step engages only on a net that unfolds
  wrong. It cannot reach a shipped corner either (a collapsed side is
  `smooth_degenerate_cap`'s case and gates it off structurally). Its one
  measured case is the demo's `CB_J1_FrontTopRight` in the arrangement of
  before the leader/length work — 0/630 coincident, no collapsed side, 30/56/86
  flips at n=39/81/150 in the two subgrids that touch the triangular member
  while the two strip-to-strip subgrids are clean — after which it reads
  0/0/0 flips and the tri's nearest interior sample moves 0.0179 → 0.30967 mm
  off the quad (`Tests/demo_corner_row_diff.py`,
  `Tests/test_fold_free_interior.py`). Read that as a dated record of the
  step, not as the thing that makes a rolled corner work. 4-valent reference on the same
  code (untouched by the smoothing; CB2 still poles-matches the legacy chain):
  g1 ≤ 2.0e-4°, `k_gap` ≤ 1.0e-2 /mm.
- Fourth wizard step and fourth toolbar command (`Silk_CreateCornerBlend`);
  the toolbar path opens its own transaction.
- Weights are carried — rational weights are possible.
- **No continuity is asserted.** The construction is pole-identical to the
  reference chain, so it inherits that chain's measured behaviour (#97):
  C0 exact, G1 ≤ 0.48°, **not G2**. #100 measured what G2 would take
  (`docs/research/silk-corner-g2.md`): the bar is a control-net **solve** of the
  corner's 4 free central poles, not the two-row average — exact on a junction
  of compatible neighbours (`k_gap` 6.0e-17), 7.1e-3 /mm on the demo's legacy
  neighbours, where the limit is the neighbours' disagreement (#102). FreeCAD's
  order-2 fill is not the route. Silk's **edge blend** is the strong link:
  G1-exact, `k_gap` ≤ 2.5e-4 /mm. Corner taxonomy/census and the G2 maths:
  `docs/research/silk-corner-type-taxonomy.md`, `silk-demo-blend-census.md`,
  `silk-g2-math-overview.md`.

## Full Workflow Pipeline
```
Sketches (9 reference sketches)
  → Edges (7, each linked to 1-2 sketches via Sketches property)
    → Patch (2 from 4 Edges each)
      → Blend (1 between the 2 Patch)
        → Corner Blend (at a junction where 3 or 4 Patch meet; fed the ring
          Blend(s) — the triangular patch beside the quad is built by the
          corner stage, not picked by the user)
```

## Module Reload Pattern
Each MCP `execute_code` call runs in the same FreeCAD process. Python caches modules:
```python
for m in list(sys.modules.keys()):
    if 'SilkPatch' in m or 'SilkPatch44' in m or 'SilkBlend' in m or 'SilkEdge' in m or 'SilkMachinery' in m:
        del sys.modules[m]
import SilkPatch, SilkBlend, SilkEdge, SilkMachinery
```

## Shared Edge Detection & Blend Algorithm

### Step 1: Find shared corners
```python
corners = [Poles[0], Poles[3], Poles[15], Poles[12]]
# = [p00, p03, p33, p30] = [U0V0, U1V0, U1V1, U0V1]
```
Compare corner[i] vs corner[j] within tolerance 0.01. Collect matching pairs.

### Step 2: Determine edge type
- (0,1) or (1,0) = U0 (V=0, U varies along row 0)
- (1,2) or (2,1) = V1 (U=1, V varies along col 3)
- (2,3) or (3,2) = U1 (V=1, U varies along row 3)
- (3,0) or (0,3) = V0 (U=0, V varies along col 0)

### Step 3: Ensure the band split on both patches (SilkBlend.ensure_band_split)
Each strip reads the perpendicular split on its two patches, additively so both
splits can coexist on a 4-patch corner patch. With no user choice the defaults
are written; a width the user already set is READ, not overridden (#64):
| Shared edge | Band axis | Band edge written (default) |
|-------------|-----------|-----------------------------|
| U0 (row 0)  | V | `VSplit1 = 0.1` |
| U1 (row 3)  | V | `VSplit2 = 0.9` |
| V0 (col 0)  | U | `USplit1 = 0.1` |
| V1 (col 3)  | U | `USplit2 = 0.9` |

**The patch owns its band edges; the blend consumes them. There is no `Blend`
property for the band width** (#64). "This seam's end" is the property's own
NAME: `SilkBlend.band_edge_prop(letter, end)` is the single naming
expression, used by the writer (`ensure_band_split`), the survivor lookup
(`_survivor_needs`) and the remover (`_drop_band_split`), so none of them can
disagree about which end owns which edge. The rule is per (patch, axis, end),
so a corner patch's two seams on one axis never collide.

**There is no third split, because there is nowhere to put one** (#76's cap
became a TYPE under #82). Each axis has exactly two properties and each names
its own end, so the two-entry limit is structural rather than enforced — and
the classify-by-value guess that made it bite (`split_at_end`, `split_end`,
`split_limit_problem`: all gone) is gone with it. `[0.2, 0.4]` used to report
"no band at the 1 end" (#81), so the blend tried to write a third value and
the cap refused it, leaving the patch `Invalid`. Every value strictly inside
(0, 1) is now an ordinary band edge at the end that names it, 0.5 included.
Two corrections remain on the property-set path
(`SilkPatch._normalize_splits_on_set`, through
`SilkMachinery.normalize_edge_pair`, so the script, panel and expression paths
all meet them): a value outside [0, 1] becomes its own slot's sentinel, and a
pair whose two edges are out of order is swapped. Both are REPORTED on the
console unless the document is restoring.

### Step 3b: Band = subgrid cells, NOT re-segmentation (ticket #33)
The strip band is taken from the patch's pre-computed subgrid cells
(`p.Proxy._subgrids`, produced by the two named edges on each axis) — never
by re-segmenting `_base_surface` with an ad-hoc trim. `band_cells(p, ea, ss)`
selects the band cell: the band interval at the seam's own end on the
seam-perpendicular axis, minus the corner cells at the seam ENDS — reserved
for the 4-subgrid corner blend object. The exclusion is keyed to the NAME,
not to a value (#82, after #61 dropped the literal 0.1 / 0.9):
`SilkMachinery.corner_cells` drops the first interval when `Split1` carries an
edge and the last when `Split2` does, so a user width of 0.2 or 0.85 excludes
its corner cell exactly as the default does. Each edge therefore drops exactly
one cell off the axis it is on, so **the band is always ONE cell** — the
multi-cell refusal is no longer expressible. The one degenerate layout left is
both ends holding the SAME edge (one split, both end cells corner cells, no
band), which `get_strip` refuses with `SilkMachinery.band_diagnosis`'s
message. Auto-hide re-derives the FULL `_HiddenSubgridIdxs` set for each patch
from ALL linked strips with the current edges (cell indices shift when a later
strip adds one).

The width IS the user's (#64): `ensure_band_split` writes 0.1 / 0.9 only when
the seam's end of that axis carries no band edge at all; otherwise it reads
the edge the patch already has and writes nothing. Because the band and
`corner_cells` read the same two properties, a user width excludes its corner
cell exactly as the default did.

### Step 4: Extract rows/columns from strips
Subgrid flat: `poles[U][V]` = `flat[U*4 + V]` (U is first dimension in FreeCAD)

**CRITICAL extraction rule:**
- If shared edge runs ALONG U (row): perpendicular is V → take COLUMNS at const U
- If shared edge runs ALONG V (col): perpendicular is U → take ROWS at const V

Row at V=i: `flat[0+i, 4+i, 8+i, 12+i]` = varying U, constant V
Col at U=j: `flat[4j+0, 4j+1, 4j+2, 4j+3]` = varying V, constant U

### Step 5: Pair rows/columns across patches
Corner matching gives the index mapping. Shared edge direction may be REVERSED.
- Example: left corners[0]=(0,0,40) matches right corners[1]=(0,0,40), left corners[3]=(0,50,0) matches right corners[0]=(0,50,0)
- Then left V=0 ↔ right U=3, left V=3 ↔ right U=0, mapping is left V=i ↔ right U=3-i (reversed)

### Step 6: Blend
For each paired row/col:
1. Reverse the LEFT row so it goes OUTER→SHARED (list(reversed(row)))
2. Keep the RIGHT column as SHARED→OUTER
3. Call `AN.blend_poly_2x4_1x6(l_row_rev, [1.0]*4, r_col, [1.0]*4, 2.0, 2.0, 2.0, 2.0)`
4. Collect 6-pole results

Stack 4 result rows into a 6×4 grid. Create blend surface via `AN.CubicSurface_64`:
```python
tmp = doc.addObject("Part::FeaturePython", "_tmp")
AN.CubicSurface_64(tmp, blend_grid_obj)
tmp.recompute()
surf_shape = tmp.Shape
doc.removeObject(tmp.Name)
```

**NEVER use `buildFromPolesMultsKnots` or manual `insertUKnot` for blend surfaces** — the knot vector is non-trivial. Always use `AN.CubicSurface_64`.

### Key gotchas
- `segment(u0, u1, v0, v1)` — first arg is U range, second is V range
- Surface `getPoles()` returns `poles[U][V]` (U is first dimension)
- `blend_poly_2x4_1x6` expects: poles_0 goes OUTER→SHARED, poles_1 goes SHARED→OUTER

## Auto-Update Chain

When a Patch's band edges change, the Blend auto-updates:

1. `Patch.onChanged("USplit1")` (or any of the four) → `fp.touch()` + `fp.recompute()` → `execute()` runs
2. `execute()` searches doc for Blend objects linked to this patch → calls `blend.touch()`
3. Next `doc.recompute()` → Blend is touched → `execute()` reads updated subgrids → blend recomputes

## Display Toggles (Patch)

- **ShowSurface**: controls surface visibility (base or subdivided)
- **ShowGrid**: controls grid line visibility
- **ShowSubgrids**: when True and splits exist, shows subdivided surfaces instead of smooth surface
- **AutoHideBlend**: when True and a Blend links to this patch, hides the blended subgrid strip (via `_HiddenSubgridIdxs` property set by Blend)

## Surface Creation for Patch (bicubic Bezier)
```python
surf = Part.BSplineSurface()
surf.increaseDegree(3, 3)
for knot, mult in [(0.0, 4), (1.0, 4)]:
    surf.insertUKnot(knot, mult, 1e-7)
    surf.insertVKnot(knot, mult, 1e-7)
for r in range(4):
    for c in range(4):
        idx = r * 4 + c
        surf.setPole(c + 1, r + 1, poles[idx], weights[idx])
```

## View Provider Pattern
Each FeaturePython object needs a custom view provider for tree icons:
```python
class MyViewProvider:
    def __init__(self, vobj):
        vobj.Proxy = self
    def getIcon(self):
        return iconPath  # path to SVG
    def attach(self, vobj):
        self.ViewObject = vobj
    def updateData(self, obj, prop):
        return True
    def __getstate__(self):
        return None
    def __setstate__(self, state):
        return None
```
Usage: `MyViewProvider(obj.ViewObject)` (NOT `obj.ViewObject.Proxy = MyViewProvider(obj.ViewObject)`)

## Test Infrastructure

### MCP Harness
- `Tests/mcp_harness.py`: `run_tests(*funcs)`, each func takes doc, returns dict
- `Tests/test_blend.py`: Blend strip tests (with `CaptureConsole`)

### Console Error Capture
```python
class CaptureConsole:
    def __enter__(self):
        self._orig_error = FreeCAD.Console.PrintError
        FreeCAD.Console.PrintError = lambda msg: (self.errors.append(msg), self._orig_error(msg))
        return self
    def __exit__(self, *args):
        FreeCAD.Console.PrintError = self._orig_error
```

### Test suite (two launchers, one suite)
- `Tests/suite.py` — auto-discovers `Tests/test_*.py` modules (uses `ALL_TESTS` if present, else top-level `test_*` functions)
- `Tests/run_all.py` — **primary launcher**: `python3 Tests/run_all.py` connects via XML-RPC to the user's already-running FreeCAD GUI (127.0.0.1:9875, no restart). Takes an optional substring filter (e.g. `python3 Tests/run_all.py chain`), `--inspect` to leave test documents open for stage-2 human inspection, and `--save` to persist the leftover geometry to `Resources/Test_files/_inspect/` (gitignored) so each test's final state can be reopened even after FreeCAD closes (implies `--inspect`). Exit codes: 0 = all pass, 1 = failures, 2 = FreeCAD unreachable.
- `freecad Tests/run_all.py` — fallback in-process mode (spawns its own FreeCAD). **Only with the offscreen environment** — see the rule below.
- **Never open a WINDOW on the owner's screen** (the owner's rule, 2026-10-20, clarified the same day): a visible FreeCAD window takes focus and interrupts the owner. Three ways to run the suite, in order of preference:
  1. **The owner's running GUI, over RPC** — no new process, nothing opens:
     `flock /tmp/silk_rpc.lock -c "python3 Tests/run_all.py"` (while iterating, a by-name filter instead of the whole tier: `flock /tmp/silk_rpc.lock -c "python3 Tests/run_all.py rolling_corner_66"`).
  2. **A spawned FreeCAD, rendered OFFSCREEN** — a real process in the background, but it draws nothing and takes no focus:
     `QT_QPA_PLATFORM=offscreen LIBGL_ALWAYS_SOFTWARE=1 freecad Tests/run_all.py`.
     Verified working (the suite runs green under it, and the owner's screen stays untouched).
  3. **A spawned FreeCAD with a visible window** — `freecad Tests/run_all.py` with no environment. **Do not do this**: it opens a window that takes focus.
  `freecadcmd` does **not** work for this suite: the runner imports `FreeCADGui`, and the console build has no such module ("cannot import name 'Gui' from 'FreeCAD'").
  If the RPC at 127.0.0.1:9875 does not answer, the offscreen route (2) is the background fallback; a run that opens a window on the owner's screen is never acceptable.
- Stage tests: `test_edge_stage.py` (E1–E4 oracle), `test_patch_stage.py` (P1–P4), `test_blend_stage.py` (B1–B4), `test_chain.py` (full 9→7→2→1 rebuild, the acceptance gate — always runs)
- **The fast tier is the inner loop, and it is TIMED**: `python3 Tests/run_all.py --timings`
  prints the per-module table, and that table is how a module earns or loses
  its tier. Measured on the owner's session (2026-10-23, `--timings`, the
  installed FreeCAD): **202 tests, 49 s of test time, ~58 s of wall** for the
  whole default run. The `[timings]` line prints test time only; the ~9 s
  wall on top of it is the run's own fixed cost, dominated by the `[leak]`
  orphan count — `gc.collect()` (2.8 s) plus one pass over the 67 M tracked
  objects of a long-lived GUI session (3.9 s, measured). A FRESHER FreeCAD
  pays less for it; that cost grows with the session, not with the suite.
  Before the slimming the same table read 243 tests / 256 s of test time /
  267 s of wall.
- **What moved out of the default tier, and why** (each carries `MANUAL = True`
  and still runs on demand: `python3 Tests/run_all.py --manual`, or by name as
  a filter). `Tests/test_manual_tier.py` pins the set in both directions and
  still asserts every manual module imports and keeps tests: `test_rolling_corner`
  (path (B), SUPERSEDED by ADR 0006), `test_corner_ring_parity` (parity sweep
  over the maintainer's 40 stored corners), `test_example_documents` (opens and
  re-derives the shipped examples), `test_inspection_toggles` and
  `test_patch_gui_command` (GUI drives), and `test_runner_generations` — the two
  tests whose answer needs a full sweep of the live heap (`ensure_fresh`'s
  no-reimport guarantee and the orphan-growth bar), which cost 12.5 s of the
  old tier for two numbers. The #72 single-generation guard, its planted-stale
  control and the purge rules stay fast (0.9 s in total).
- **Two reductions that are not deferrals**: `Tests/mcp_harness._uses_document`
  skips creating a FreeCAD document for a test whose bytecode never reads it
  (~8 s; each test that reads one still gets its OWN fresh document, nothing is
  shared), and `Tests/silk_reload.live_module_objects` is the ONE heap sweep the
  runner's orphan count, the #123 census and the growth guard share (it was
  three, and the type test is `filter(ModuleType.__instancecheck__, ...)`:
  2.4 s vs 5.7 s for the same 868 module objects). `rss_baseline_measure.collect_orphans(objects=...)`
  lets the census's fast-tier calibration hand in a synthetic pair instead of
  sweeping a real heap (123 s of the old tier).
- Ops layer: `SilkWorkflowOps.py` (`create_edge`, `create_patch`, `create_blend`) — the only construction path; oracle: `SilkChecks.py` (`check_edge`, `check_patch`, `check_blend`)
- The harness monkey-patches `popup.tipsDialog` to a console stub so unattended runs never block on modal popups
- **Self-consistency guard (#67)**: every patch the ops layer or the panel hands back is asserted oracle-green on its OWN `list(p.Edges)` — in `test_patch_stage.test_patch_stored_cycle_is_self_consistent_for_all_24_orderings` (all 24 orderings, square + curved ground truth) and `test_task_panel.test_every_patch_the_panel_hands_back_is_oracle_green` (9 click orders + the pointed fill through the real panel). Feeding the oracle a hand-computed cycle instead of `p.Edges` is the trap: it hides a stored list that disagrees with its own geometry, which is exactly how the #67 defect shipped green.
- RPC runs reload the workbench + test modules through `Tests/silk_reload.py` (#72). It purges by **file location** -- every `.py` under the Mod directory, all 57 of them, whatever they are called -- because the old `Silk*`/`Tests*`/`ArachNURBS*` name-prefix purge left ~25 helper modules (`ControlGrid44`, `ControlPoly4`, `CubicSurface_64`, ...) on an older generation of `ArachNURBS`, so a green suite validated one generation of the maths against surfaces built by another. It reloads **only when a Mod source actually changed** (mtime + size + sha256 per `.py`, fingerprint kept in `<tmp>/silk_reload_fingerprint_<pid>.json` because the FreeCAD process outlives the run), and it clears stale bindings in the persistent RPC `execute_code` namespace, which otherwise pins whole generations. Flags: `--force-reload`, `--keep-namespace`, `--rss-warn MB`. Every run prints `[reload]`, `[leak]` and `[rss]` lines.
- **Single-generation guard (#72)**: `Tests/test_module_generation.py` asserts that after a reload every Mod-directory module's `AN` is the one `sys.modules["ArachNURBS"]` object, naming offenders; that test's absence is what let a split-brain suite report 168/168. The same file keeps the old prefix-only purge executable, so the bug cannot come back silently, and the planted-stale control keeps the guard honest. The two ORPHAN tests that answer by sweeping the live heap moved to the MANUAL `Tests/test_runner_generations.py` (12.5 s of the fast tier for two numbers), so the guard module is 0.9 s.
- **Frames outlive runs**: FreeCAD prints exceptions raised inside C++ slots (e.g. `SilkBlend._DeleteWatcher.slotDeletedObject` on document close) through the excepthook, and the traceback keeps every frame. A retained `run_tests` frame pinned the whole generation it ran against, so `run_tests` drops its references (`saved`, `func`, `doc`, `outcome`, `test_funcs`) when it finishes, and the runner clears `sys.last_traceback`.
- **`Gui.addCommand` at import time was the memory leak (#72).** FreeCAD keeps one Python instance per registered command, and that instance pins the command class's `__globals__` — which is the module's dict, which holds `AN`. **30 legacy helper modules registered themselves at import**, so each reload minted a fresh `ArachNURBS` that could never be freed (~600 MB per run, measured). Those registrations are removed: the commands are retired (#50, `LEGACY_NAMES` "none may reappear"), and old documents restore from the **class**, which is untouched. Deliberately **kept**: `ControlPoly4` / `CubicCurve_4` (invoked by legacy `SilkWorkflow.runCommand`), the five visible commands, and `SilkWorkflow`'s own two registrations (a restore path — not worth an unverified change). The runner still reports `[leak] N orphaned ...` for anything left.
- **The #123 baseline instrument** (`Tests/rss_baseline_measure.py`, MANUAL): runs the fast tier N times in ONE FreeCAD and records, per run, the runner's own `rss_before`/`rss_after`, the **inter-run gap** (`rss_before(N+1) - rss_after(N)` — the quantity the runner's own delta CANNOT see, because its window opens and closes inside one run), the orphan count, the reload flag, and a second reader's RSS sample of the same process. It ends with a census of the orphan module objects and **who holds them**. Run it against a live FreeCAD: `python3 Tests/rss_baseline_measure.py --runs 5`; the raw output goes to `/tmp/silk_rss_baseline/<stamp>/` and IS the measurement. The orphan count is a **RELOAD counter, not a per-run counter**: `orphan_generations()` counts module objects a purge dropped from `sys.modules` while something still held them, and a purge happens only when the Mod sources changed — so the count grows with reloads, not with runs. `Tests/test_rss_baseline_measure.py` calibrates the analyser (known slopes, known floors) and the census. The census hands `collect_orphans(objects=...)` a synthetic orphan pair: a real census costs 123 s because it asks `gc.get_referrers` once per orphan, and each of those is a full heap scan — the instrument's `objects=None` default still means the live heap, and the fast tier asserts that it does.

## Reference Files
- `Resources/Test_files/Silk_2Boundaries.FCStd` — 9 sketches only (baseline)
- `Resources/Test_files/Silk_Workflow.FCStd` — full pipeline built on sketches
- `Resources/Test_files/Silk_2BoundariesAndControlGrids.FCStd` — old reference with groups
- `Resources/Test_files/SketchOnly_Demo01Subset_withPatches.FCStd` — **the owner's own hand-built Demo 01 model** (12 Edges → 5 Patches → 8 Blends → **0 corners**: the owner stopped at the corner stage on purpose, the panel wanted 4 ring blends and a Demo01 junction is 3-valent). It is the one artifact that **predates** the `ShowGrid` toggle (#95) and the `Flat Lines` view mode (#96), so the restore-path test needs it exactly as it is. Its inventory is stated ONCE, in `Tests/owner_model_fixture.py` (`DOCUMENTED_INVENTORY`), and `Tests/test_owner_model_fixture.py` (fast tier, offline) asserts the file on disk carries exactly that — a dirty working copy goes **red** instead of silently feeding a test (#124).
- `Resources/Test_files/examples/` — **sketch-only click-through fixtures for the human-test rounds (#56)**: `SketchOnly_Quad` (4 sketches → 1 patch), `SketchOnly_TwoPatches` (7 sketches → 2 patches + 1 blend), `SketchOnly_Corner4` (12 sketches → 4 patches + corner blends), and bonus `SketchOnly_CornerCube`. Each opens with **zero** Edge/Patch/Blend objects; a human clicks Edge → Patch → Blend to reproduce the documented target in `Resources/Test_files/examples/README.md`. Use these for the wizard-fit / tool-intuitiveness rounds (#48) and to change the tools without rebuilding geometry. `Tests/test_example_documents.py` asserts each example stays sketch-only with its documented sketch set.
