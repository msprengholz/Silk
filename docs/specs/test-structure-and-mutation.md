# Target test structure & mutation harness (Silk unified suite)

Status: **design decision** on the path to #26 (legacy prune) and #41 (mutation matrix). This is the durable reference for restructuring the test suite as the unified objects land (#38/#39/#40) — and it is the spec the mutation backfill is handed off from.

## Guiding principles

1. **External behavior via ops + oracle.** Tests assert through the ops layer (`create_edge` / `create_patch` / `create_blend`) and the oracle (`check_edge` / `check_patch` / `check_blend`) plus stored poles/shape at 1e-6. Never inspect private internals (`_subgrids`, `_base_surface`, …) — behavior only. (One recorded exception, the oracle's legacy cell reader: see below.)
2. **Mutation is first-class.** Every testable object type must demonstrate **build → mutate → revalidate** (oracle still green, geometry still valid, no stale state), not just build. "We must not only create but also change the geometry and see that it is still valid" is a stated requirement, not an afterthought.
3. **The chain gate is sacred.** The 9→7→2→1 ground-truth rebuild at 1e-6 is the acceptance gate and must survive any restructuring (and, after #40, run on unified objects).
4. **No redundant duplication.** One authoritative oracle module per object; the stage/comprehensive overlap is resolved; legacy/retired-object tests are pruned (#26), not left green-but-meaningless.
5. **Regression tests stay small and named after the bug** (#30 / #31 / #32) so history is legible.

## Recorded exception to principle 1: the oracle's legacy cell reader (#120)

Principle 1 says never to inspect private internals. There is exactly ONE place in the
code that does, and it is recorded here rather than left implicit.

**Where.** `SilkChecks._oracle_cell_net` falls back to the patch's own cell cache
(`Proxy._subgrids` / `Proxy._subgrid_weights`) when the public reader cannot answer.
`SilkChecks.check_blend` reads `p.Proxy._subgrids` once more, on the same path, as the
"does this patch have cells at all" guard. Those two sites are the whole of it -- a scan of
`SilkChecks.py` finds no other private read.

**Why the fallback exists.** The PRIMARY path is the public reader:
`Proxy.getSubgrid(u0, u1, v0, v1)` re-derives the cell from the patch's own base surface,
and both the current `Patch` (`SilkPatch.py`) and the legacy `Patch44` shim
(`SilkPatch44.py`) expose it. The fallback is reached only when that reader cannot answer:
a proxy with no `getSubgrid` at all, or one whose base surface is not built (the legacy
`Patch44` restore shim before its `execute()` has run; a test stub). It was added by #107,
which recorded that the legacy objects "keep the verdict they always had".

**Why closing it is not an improvement.** Closing the fallback would not make the oracle
stricter; it would make it SILENT. A legacy patch would stop being CHECKED and start being
SKIPPED: `check_blend` would answer "no shared edge found between the patches"
(`B1_c0_seams` / `B2_c1_tangents` red) where it used to answer a verdict, so an old
document's verdict would change. The restore contract (#93)
requires an old document to come back with the verdicts it always had. A ticket whose scope
is "none of these changes behaviour" cannot close it silently.

**What the exception does NOT cover.** The fallback is a fallback: the oracle decides nothing
else from the cache, and every other test and oracle path stays on the public surface. The
exception is bounded to the legacy path named above; a public reader that covered the legacy
objects would let it be closed, and this paragraph would be the record of why it was not.

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

**Actual disposition (2026-10-14):** the FOLD targets above never materialised — `test_edge.py`,
`test_patch.py` and `test_mutation_matrix.py` do not exist. The stage tests
(`test_edge_stage.py`, `test_patch_stage.py`, `test_blend_stage.py`) were **kept**, not folded;
`test_patch33.py` was **deleted**, not folded into `test_patch`. Unified coverage lives instead
in `test_patch_unified.py`, `test_blend_unified.py`, `test_mutation_unified.py` and the
`test_mutation_backfill.py` matrix. The table above is the original plan, kept as a record.

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
