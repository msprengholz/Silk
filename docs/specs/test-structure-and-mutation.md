# Target test structure & mutation harness (Silk unified suite)

Status: **design decision** on the path to #26 (legacy prune) and #41 (mutation matrix). This is the durable reference for restructuring the test suite as the unified objects land (#38/#39/#40) — and it is the spec the mutation backfill is handed off from.

## Guiding principles

1. **External behavior via ops + oracle.** Tests assert through the ops layer (`create_edge` / `create_patch` / `create_blend`) and the oracle (`check_edge` / `check_patch` / `check_blend`) plus stored poles/shape at 1e-6. Never inspect private internals (`_subgrids`, `_base_surface`, …) — behavior only.
2. **Mutation is first-class.** Every testable object type must demonstrate **build → mutate → revalidate** (oracle still green, geometry still valid, no stale state), not just build. "We must not only create but also change the geometry and see that it is still valid" is a stated requirement, not an afterthought.
3. **The chain gate is sacred.** The 9→7→2→1 ground-truth rebuild at 1e-6 is the acceptance gate and must survive any restructuring (and, after #40, run on unified objects).
4. **No redundant duplication.** One authoritative oracle module per object; the stage/comprehensive overlap is resolved; legacy/retired-object tests are pruned (#26), not left green-but-meaningless.
5. **Regression tests stay small and named after the bug** (#30 / #31 / #32) so history is legible.

## Target module layout

Per-object oracle + mutation:

- `Tests/test_edge.py` — Edge oracle + edge mutation (move a pole on 2N and 3L edges → rebuild, oracle green).
- `Tests/test_patch.py` — unified `Patch` oracle (4-edge quad + 3-edge pointed) + pole parity vs Patch44 + mutation (edit Edges, change USplits/VSplits, reverse an edge).
- `Tests/test_blend.py` — unified 2-patch `Blend` oracle (C0+seam-C1) + mutation (change a shared edge → both patches rebuild → band re-derives → seam stays clean).
- `Tests/test_chain.py` — the gate (migrated to unified objects in #40).

Mutation infrastructure (the #41 matrix):

- `Tests/mutation_ops.py` (or harness module) — shared mutation operators + a `run_mutations(build, oracle, ops)` helper reused by per-object and matrix tests.
- `Tests/test_mutation_matrix.py` — the spanning matrix: mutation operator set × every object type × the full pipeline, plus convergence/idempotence.

Regressions (keep as-is):

- `Tests/test_blend_pairing.py` (#30), `Tests/test_blend_direction.py` (#31), `Tests/test_blend_corner_splits.py` (#32).

Deferred / non-core (keep tests, not part of the core suite's acceptance):

- `Tests/test_corner_blend.py` — the corner fill is a deferred object.

## Disposition of current modules

| Module | Disposition | Action |
|---|---|---|
| `test_chain.py` | KEEP (gate) | migrate to unified in #40 |
| `test_edge_stage.py` | FOLD → `test_edge` | oracle stays; add mutation |
| `test_patch_stage.py` | FOLD → `test_patch` | oracle stays; add mutation |
| `test_blend_stage.py` | FOLD → `test_blend` | oracle stays; add mutation |
| `test_patch_unified.py` | FOLD → `test_patch` | its pole-parity / negative / mutation grow into the unified patch module |
| `test_patch33.py` | FOLD → `test_patch` | becomes the pointed-fill section |
| `test_blend_pairing/direction/corner_splits` | KEEP | unchanged |
| `test_corner_blend.py` | KEEP (deferred) | unchanged |
| `test_patch44_comprehensive.py` | SPLIT (#26) | keep unique value (serialization, stress splits, get-subgrid API, pole-count, 2N edge); merge basics into `test_patch`; drop internal-inspection |
| `test_patch44.py` | PRUNE (#26) | GUI-command + internal-inspection path removed; no unique value left |
| `test_workflow.py`, `test_boundaryspline.py` | PRUNE (#26) | legacy BoundarySpline / ControlGridPatch commands retired |
| `test_api_smoke.py` | TRIM (#26) | keep only as an upstream AN guard if wanted; primitives now covered by object tests |

## Mutation harness spec (the part we hand off)

**Operators** — each applies a mutation, calls `doc.recompute()`, runs the object's oracle, and asserts: oracle green, geometry valid, no stale state.

1. **move_boundary_pole** — move one pole on a driving Edge; dependent patches/blends rebuild to match; oracle green; on the pipeline the seam stays C0/C1.
2. **change_splits** — set/remove/sweep USplits/VSplits on a patch; subgrid cells rebuild; the blend band stays the correct seam-adjacent cell; hidden-cell bookkeeping stays correct.
3. **reverse_edge** — reverse an Edge's pole order; `orient_a_to_b` re-orients; no fold (a Blend must show a consistent normal field after).
4. **toggle_display** — flip ShowSubgrids / ShowGrid / AutoHideBlend; the Shape never becomes invalid or wrongly empty.
5. **recompute_convergence** — recompute repeatedly; hidden-cell sets converge monotonically (no ping-pong / no stale indices); poles stable; the chain ground truth stays at 1e-6 (or moves only as the geometry dictates).

**Per-object coverage** — apply the applicable operators to Edge, Patch (quad + pointed), and (2-patch) Blend.

**Pipeline coverage** — build the full chain, mutate a shared edge and a patch's splits, recompute, and verify every descendant (both patches + the blend) revalidates and the seam stays clean; chain GT at 1e-6.

**Gate for the harness itself** — it must be green and must never weaken an existing assertion.

## Sequencing

1. **Backfill (now, unblocked):** the mutation operators land on the **current stable objects** (Edge via ops, Patch44/BlendStrip pipeline) so the technique is proven and the value is visible immediately — before the unified objects exist. This is the first handoff from this spec.
2. **As unified objects land (#38/#39/#40):** per-object mutation joins each ticket's acceptance (bake-in, not a late addition); the per-object modules fold into the target layout.
3. **#41 (T6):** `test_mutation_matrix.py` spans every object type + the pipeline, aggregating (not duplicating) the per-object mutation tests.
4. **#26 (after #40/#42):** execute the prune/merge/trim dispositions above.

Out of scope here: GUI wizard tests (#4/#5/#6), and the corner-fill matrix (deferred until that object is in core).
