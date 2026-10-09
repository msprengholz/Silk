# Spec — Unified Edge / Patch / Blend (2-patch blend core)

Status: **Thinking-phase artifact** for wayfinder map #1. Nothing here is implemented yet. When the seams below are agreed, this feeds `/to-tickets` and each build ticket is handed off to a subagent in a fresh context (standing process rule — see AGENTS.md "Discussion vs implementation").

## Problem Statement

The workbench currently exposes a separate FreeCAD object type per ArachNURBS primitive — `Patch44`, `Patch33`, `CornerBlend`, `BlendStrip`, plus `Edge`. The shared machinery (subdivision via USplits/VSplits, band selection, hidden-cell bookkeeping, compound display) lives on only *some* of them, contradicting the end-goal wizard: the user should hand over N boundary curves and get "a surface", not pick a fill type. It also duplicates plumbing — which is why the 3-edge patch lacked the subgrid machinery the 4-edge patch had.

Separately, the current pipeline lets a blend consume other blends (the corner blend is fed 4 ring strips). That is over-complex; a blend should only ever be fed the subgrid cells of a patch.

## Solution

Unify to **three FreeCAD object types, one per process step**: `Edge`, `Patch`, `Blend` (sketch → edge → patch → blend; blends come after patches).

- **`Patch`** internally selects its fill from how many edges it is given: 3 edges → the pointed `ControlGrid44_3` fill, 4 edges → the `ControlGrid44_4` fill. No user valence knob; the count picks the fill. All fills share **one machinery core** — subdivision, band selection, hidden-cell bookkeeping, compound display.
- **`Blend`** does exactly one thing: pick a shared **Edge**, take its **two adjacent Patches**, subdivide, and blend their **two matching seam-adjacent subgrid cells** into a strip. A `Blend` is fed **only patch subgrid cells — never a Blend**.
- The 4-corner fill and FreeCAD-built-in surface fills are **deferred beyond this spec**.

## User Stories

1. As a Silk user, I want to select 3 or 4 boundary curves and get a **single `Patch` object** (not one of several types), so I never have to know or choose a fill type.
2. As a Silk user, I want a 3-boundary Patch to be a pointed fill and a 4-boundary Patch to be a quad fill **automatically**, so there is no valence knob to set.
3. As a Silk user, I want to pick the **shared edge** between two patches and get exactly **one `Blend`**, so blending is a single explicit act on an edge.
4. As a Silk user, I want the `Blend` to be a **separate object that appears after the patches**, so the tree reads sketch → edge → patch → blend.
5. As a Silk user, I want every Patch, whether 3 or 4 edges, to subdivide into u/v subgrid cells with per-cell visibility, so the machinery is uniform.
6. As a Silk user, I want the blend band to be the **correct matching subgrid cell on each side of the shared edge**, so the seam is clean without re-segmenting the base surface.
7. As a Silk user, I want edge / patch / blend each drawn in **one consistent color**, so the view and tree are readable.
8. As a Silk user, I want to edit a patch's boundaries after creation and have dependent blends update, so the model stays in sync.
9. As a Silk user, I want every object I build to pass the correctness oracle (structural + defect checks, **C0+C1 at the blend seam**, poles to 1e-6), so geometry is guaranteed.
10. As a Silk user, I want the full pipeline (sketch → edge → patch → blend) rebuildable from a blank document through the ops layer, so it is reproducible and the chain stays the acceptance gate.

## Implementation Decisions

- **One `Patch` object** with a variable-length `Edges` link list (`PropertyLinkList`) as its single boundary input (replacing the per-fill `Poly0-3` links). `execute()` picks the fill from the count and runs it; the output is `Poles`/`Weights`/`Legs` plus a B-spline surface.
- **A shared machinery core** (one module) implementing, once, for every fill: `USplits`/`VSplits` → subgrid cell pole arrays + trimmed shapes; band selection (the seam-adjacent cell); hidden-cell bookkeeping (`_HiddenSubgridIdxs`, blend + corner cells excluded automatically); compound display; and the single per-type color. Both the 3-edge and 4-edge fills delegate to it — this is the "reuse (Axis B)" payoff that gives patch33 the subgrid machinery by reusing code, not copying it.
- **One `Blend` object** consuming the two adjacent Patches + the shared Edge. The blend band is the matching seam-adjacent subgrid cell on each patch — the already-verified contract from the ring-band work (no re-segmentation). The verified strip mechanics carry over: **row pairing** (identity vs reversed, inferred from the corner matches), **row orientation per seam side** (ss), and **band split axis/side** per patch — this is exactly the existing, green, tested behavior, folded into one type.
- **Existing fills become internal implementations.** `Patch44` / `Patch33` / `BlendStrip` (and, deferred, `CornerBlend`) remain as the fills *behind* the unified shells. The ops layer (`create_edge` / `create_patch` / `create_blend`) and the oracle (`check_edge` / `check_patch` / `check_blend`) are the public contract.
- **`Edge` is unchanged** — it is already a single type.
- **Colors:** one distinct color per type (edge / patch / blend). Per-fill icon/color proliferation is retired.
- **Migration gate:** all existing tests stay green; the unified 2-patch `Blend` reproduces the current ground-truth strip exactly at 1e-6 (the chain test is the gate).

## Testing Decisions

- **Test external behavior, not internals** — drive everything through the ops layer and assert on the oracle (`check_edge` / `check_patch` / `check_blend`) plus stored geometry at 1e-6. Never assert on `execute()` machinery directly.
- **Modules tested:** unified `Patch` (both the 3-edge and 4-edge fills), unified `Blend` (the 2-patch strip), and the shared machinery across fills (subdivision, band selection, hidden-cell bookkeeping, compound display).
- **Prior art (already in the repo):** `Tests/test_patch44_comprehensive.py`, `test_patch33.py`, `test_blend.py`, `test_blend_pairing.py` (#30), `test_blend_direction.py` (#31), `test_blend_corner_splits.py` (#32), and the standing `test_chain.py` full rebuild. Same oracle-driven, ground-truth-fixture style.
- **Two-stage testing (standing rule):** stage 1 automated oracle (exit code), stage 2 human `--inspect`: visual.
- **Live-update / mutation safety (explicit requirement):** tests must not only build every object and blend from the ground up, but also **mutate the model after creation and assert nothing breaks** — edit a patch's boundary edges and change the UV splits on an existing built patch, recompute, and assert the recompute chain stays stable: surfaces stay valid, hidden-cell sets converge monotonically (no ping-pong), blend bands stay the correct seam-adjacent cells, strips orient correctly, and the chain ground truth remains at 1e-6. This is a first-class testing concern to keep in mind while restructuring and setting up the new tests, not an afterthought.

## Out of Scope

- **The 4-corner blend fill** — deferred. When built it is fed the **4 patches' corner subgrid cells**, never strips (keeps "a blend only eats patch subgrids" true).
- **FreeCAD-built-in surface fills** for valence ≥5 / leftover regions — deferred.
- N-patch stars, capping, solid construction, G2 auto-everywhere.
- **The wizard GUI** (map #1 tickets #4/#5/#6, parked) — this spec is the object layer the wizard will build on.
- Sketch creation / templating.
- Legacy `SilkWorkflow` / `BoundarySpline` command migration (separate audit, #26).

## Further Notes

- `CornerBlend` remains committed and green but is **not part of this core model** — it is superseded-in-model and deferred. Its current strip-fed wiring is not the target shape.
- **Blends never consume blends.** The guiding invariant for this whole object model.
- This spec is the foundation the end-goal wizard builds on. When the map clears past it, `/to-tickets` splits it into build tickets, each handed off to a subagent in a fresh context (TDD + oracle), reviewed before the ticket is marked done.
- **Restructuring guard:** during the unification the mutation-safety behavior (recompute on edge/split change) is a hard invariant that T1–T5 must preserve; the test suite is set up so this is verified continuously, not only in the final integration ticket.
