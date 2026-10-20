# Session handover — 2026-10-19 (the rolling corner)

**State at pause.** Branch `unified-workflow-wizard`, pushed to `origin`. The
default test run is the **fast tier** (~60 s, 195 tests). Heavy end-to-end
modules carry `MANUAL = True` and need `--manual`.

**Read this first:** `docs/corner-blending.md` (the corner page: vocabulary,
supported valences, the honest answer on the rolling fillet) and
`docs/research/silk-rolling-corner.md` (the rolling build's own finding).

---

## 1. The owner's decisions in this session (all closed on the tracker)

| decision | where it lives |
|---|---|
| **D1** — both corner constructions, **rolling stays the default**, the maintainer's recipe is the opt-in | [#114](https://github.com/msprengholz/Silk/issues/114) closed; the recipe is [#119](https://github.com/msprengholz/Silk/issues/119) |
| **D3** — `Silk_CornerFill` joins the visible set | [#96](https://github.com/msprengholz/Silk/issues/96) item 1 shipped (`2282a3e`) |
| **D8** — nothing beyond what FreeCAD or Silk already provides; the G2 findings are **kept as docs**, the implementation is dropped | [#104](https://github.com/msprengholz/Silk/issues/104) closed with `docs/research/silk-g2-*.md` intact |
| **D9** — for 5- and 6-valent corners, **FreeCAD's fill directly, even if it is not pretty** | [#92](https://github.com/msprengholz/Silk/issues/92) closed; the sentence is on the corner page |
| **no degree-1 raise**, **no Y-split** (the owner's own reason: the Y-split's edges run along the highest-curvature centre) | in [#119](https://github.com/msprengholz/Silk/issues/119)'s scope |
| **#12 deferred** — "no features that silk currently does not support" | [#12](https://github.com/msprengholz/Silk/issues/12) closed |
| **the rolling corner is NOT what we ship** — the owner's ruling on the render | `docs/corner-blending.md` |

**The vocabulary is settled and lives in `GLOSSARY.md`:** *rolling* is the
maintainer's own word for **two zones of different fillet size** (two convex
fillets) and is reserved for it; *setback* is the video's word for our **band
width**; *anisotropy* and *saddle* are our measured quantities. The shipped
corner is **one 6×6 with a rounded outline** — the owner ruled on the render:
*"the patch has weirdly rounded edges … I only see one surface, but it should
be two!"*

---

## 2. The rolling corner — the ground truth, and where we are

### 2.1 The primary sources (read them, do not re-derive)

- **The video**: <https://www.youtube.com/watch?v=Lqg4Uwt_zyw> (episode 51).
- **The finished model** (the definitive one):
  `upstream/master:Resources/Tutorial_Files/Silk CopyPasta/Silk_CopyPasta_27_First_Corner_Rolled.FCStd`
  — extract with `git show "upstream/master:…" > /tmp/cp/27.FCStd`. Its
  predecessors `25_Rolling_Corner_blend_start` and
  `26_Rolling_Corner_blend_stopping_point` are in the same series. **There are
  29 files in that series; the corner is 25→26→27.** Read them offline (a zip:
  `Document.xml` holds the object classes and links) — never open them in
  FreeCAD.
- **The demo**: `Silk_Demo_01.FCStd` (also `upstream/master:Resources/Demo_files/`).

### 2.2 What the maintainer's finished corner IS (from the file)

```
ControlGrid66_4Sub_012  ->  4 x SubGrid33_2Grid64_048..051
   ring members: ControlGrid64_2Grid44_048 (cells 137,142)
                  ControlGrid64_2Grid44_033 (cells 108,141)  <- one cell REPLACED by a cut cell
                  ControlGrid64_2Grid44_051 (cells 138,101)
                  ControlGrid64_3_Grid44_000  (cell 140)     <- the TRIANGULAR MEMBER (4th side)
   -> CubicSurface_66_013
```

The 26→27 delta **is** the recipe:

| | objects | meaning |
|---|---|---|
| 25→26 | +16 `Point_onCurve`, in **pairs** on each seam curve (u = 0.1875 / 0.8125 here; four labelled `rolling_leader`) | the stopping points |
| 26→27 | +4 `ControlPoly4_segment` +4 `CubicCurve_4` | pieces of the **original curves** |
| | +5 `ControlGrid44_2EdgeSegments` | **2-edge cuts of the base surfaces** |
| | blend 033's `Grid_1`: 108 → **141** | the blend **cut back** at the leader; it stays a 64 |
| | +2 `CubicSurface_44` | the **backfill** — "re-create the portions of the original surface that are to be preserved and not blended" |
| | +1 `ControlGrid64_3_Grid44_000` | the **member** (the scaffolding 4th side) |
| | +4 `SubGrid33_2Grid64` → +1 `ControlGrid66_4Sub` → +1 `CubicSurface_66` | the corner |

**Hard facts from the demo file (D01):** the 64 is **one cell per side** (the
4-pole direction is **along the seam**); every seam curve carries a **major and
a minor setback** per end (`CubicCurve_4012`: minor_front 0.075, major_front
0.100, major_back 0.800, minor_back 0.950); the preserved remainder is
**11 extra `CubicSurface_44`**; and **there is no 3-sided 66** —
`ControlGrid66_4Sub` is a four-member fill, which is exactly why the
fourth "scaffolding piece" exists.

### 2.3 What we built (Path B) and why it is not enough

`6f9d2f3` + `60d50dd`. **The split is exact**: the patch's base surface is
segmented at the leader (`SilkMachinery.split_band_cells` → `BSplineSurface.segment`),
so the cut is a knot line of both nets and the two pieces meet at
**5.551e-17 mm**; the default path (`Leader` = 0) is byte-identical
(0.00e+00 poles and weights). The triangle is a real FreeCAD
`Surface::Filling` through the shipped `create_fill`.

**Two failures, both reported rather than papered over:**

1. **The junction is a gap.** The fill's third side (the chord) sits
   **0.2915 mm** from the 0.75 piece's surface; the triangle's boundary sits
   **0.1522 mm** from the shipped corner's surface. This is precisely the
   owner's *"part of the edge blend needs to be replaced with a (patch66? type)
   surface"*. **No 66 was invented to close it.**
2. **The leader does not change the corner's shape.** The shipped corner's
   curvature spread is **1.037 with and without the leader, identical to
   thirteen digits** — the subgrid extrapolation is scale-invariant along the
   seam, and the corner's boundary sits at the **band's own corner end**,
   which the split does not move. *The rolling has to come from the boundary.*

### 2.4 The next build: **Path A** — the maintainer's structure

**There IS a Path A checkpoint now: `4e21833` ("wip(#119): PATH A -- the
rolling corner built from CUT cells").** It was interrupted at the session pause
while writing its test file, and it is **committed but UNGATED at the time of
writing**. It contains: a `CornerBlend` variant in `SilkCorner.py` that takes
the ring members' **cut** cells (plus a `member_grid()` helper and the leader
carried on the corner); `create_rolling_corner_66(strips, patch, leader=…,
seams=…)` in `SilkWorkflowOps.py`; `Tests/test_rolling_corner_66.py` (the
fast-tier contract, **written but never run**); and
`Tests/rolling_corner_66_visual.py` (the render + numbers script, never run).

**Its own acceptance test was RED when the session paused** — see §5 for the
gate. So the state is: the cut cells are written, but **the leader still does
not move the corner**, and the WIP was interrupted before its author could say
why.

**The acceptance test, and it is the whole thing:**

> the corner's curvature spread (`k_max/k_min`) and saddle fraction **must MOVE
> with the leader**. Every configuration so far reads **1.037**. If the numbers
> do not move, the build has not succeeded, whatever else it achieves.

**How:** our ring members are the patch's *parametric* cells; the maintainer's
are **cuts of the base surfaces**, so their junction rows sit **at the cut**.
Our equivalent: feed the corner machinery the **cut** cells — the corner-side
piece of each split seam (a band cell cut at the leader), the third unsplit
strip, and the member derived from the **cut** corner cell — then build the
corner as the 66 we already have, and finally replace the member's face with
the FreeCAD fill (the owner's *"smaller triangular surface … replaced with a
freecad surface patch"*).

**If it turns out impossible in our machinery, say so with the evidence and
what it would take.** Do not fake it, and do not fall back to Path B silently.

**Where Path A was interrupted:** it had just written the test module, and its
own test names are the acceptance — `test_the_leader_moves_the_corner_s_shape`,
`test_the_junction_at_the_cut_is_closed`,
`test_the_rolling_corner_builds_the_66_the_member_and_the_fill`, plus
`test_a_corner_without_the_rolling_construction_is_the_shipped_one` (the
default path must stay byte-identical) and
`test_a_leader_outside_the_seam_is_refused_by_name`. **The first thing to do
is read those tests and make them pass, not to write more code.**

---

## 3. The tracker, and what is merged

| ticket | state |
|---|---|
| [#119](https://github.com/msprengholz/Silk/issues/119) the rolling recipe | **in build** — Path A (see above) |
| [#121](https://github.com/msprengholz/Silk/issues/121) #96's evidence | **committed, merge held** — it rewrites `SilkWorkflowOps.py`, the file Path A was editing. `git merge ticket/work-121` (its merge is conflict-free against the pre-Path-A HEAD) |
| [#123](https://github.com/msprengholz/Silk/issues/123) the RSS measurement | **merged** (`f4cf192`) — the instrument (`Tests/rss_baseline_measure.py`, N runs in one FreeCAD process, RSS + orphan count per run) is written and desk-checked, **not yet run** |
| [#124](https://github.com/msprengholz/Silk/issues/124) the fixture vs the test | **merged and green** — the committed fixture is 12/5/8/**0** corners; the 1-corner variant was a dirty artifact and the test that wanted it was written 15 min after that save. The new guard goes red on a drifted copy; `save_fixture` now refuses to write inside the repo |
| [#120](https://github.com/msprengholz/Silk/issues/120) the four review items | **in its worktree** (`/tmp/wt-120`, branch `ticket/work-120`) — see §5 |
| [#96](https://github.com/msprengholz/Silk/issues/96) | item 1 shipped; item 2 deferred into #119 |

**Also landed earlier in the session:** the corner page + glossary vocabulary
(`0175a7a`, `e28c835`), the tracker-config fix (`60234b9`), the fill in the
toolbar (`2282a3e`), the oracle no longer imports the code under test
(`9dc7f2f`, verified with a mutation control), the CornerCube fixture and its
click script (`be27f61`, `69864af`), and the **suite tier split** (`d9b17bc`,
`1c71bc0`, `804978f`): the default run is now ~60 s.

---

## 4. The process lessons (they cost time; do not relearn them)

- **One writer per tree.** Two children in one checkout produced a confusing
  recovery summary and nearly a lost commit. The rolling build and the ticket
  children must not share a tree.
- **A worktree child cannot gate.** FreeCAD loads the workbench from a fixed
  path, so a run from a worktree exercises the **main** tree and hands back a
  false green. The ticket children wrote code and tests; the gate was bunched
  to the end. That is the cost, and it is why three merges wait for one gate.
- **The fork's `gh` resolves the BASE repo.** Always `-R msprengholz/Silk`
  (`docs/agents/issue-tracker.md` now says so).
- **The gate is ~60 s, not 14 min** — the tier split made short runs possible,
  and a child with a 2-hour budget can now afford to gate itself.

---

## 5. The gate at the pause, and the two failures

The owner's GUI FreeCAD was **down** at the pause, so the gate ran in the
documented **in-process fallback** (`freecad Tests/run_all.py` — it spawns its
own FreeCAD; use it only when no GUI is running, never alongside one):

```
IN-PROCESS GATE: total 211  passed 209  failed 2
FAIL: test_a_corner_without_the_rolling_construction_is_the_shipped_one
      ['First arg must be Vector']
FAIL: test_the_leader_moves_the_corner_s_shape
      ['the rolling corner is the shipped corner, pole for pole']
```

**Both failures are the Path A WIP's own tests** — everything else, including
all of #121's new tests (#96's normal-gap instrument, the order judgement, the
selectable C0 fallback, #11's datas-level link) and #123's instrument tests,
is green.

**What the two failures mean:**

1. `test_a_corner_without_the_rolling_construction_is_the_shipped_one` —
   *"First arg must be Vector"* — a **test bug**, the same Vector/tuple
   mismatch class as the CornerCube one: the test subtracts a tuple from a
   Vector. Cheap to fix.
2. `test_the_leader_moves_the_corner_s_shape` — *"the rolling corner is the
   shipped corner, pole for pole"* — **the acceptance test is red**: with the
   leader set, the corner comes out pole-identical to the shipped corner.
   **This is THE thing to chase.** Either Path A was interrupted before the cut
   cells reached the corner's boundary (most likely: it was interrupted while
   writing the test module), or the cut cells do not carry the cut into the
   corner's junction row. The maintainer's file says they do: his ring
   members' junction rows sit at the cut.

**The last fully-green state** was `195/195` (fast tier) at `5b66d85`, before
the Path A WIP and the #121 merge. Treat that as the known-good baseline.

```bash
cd /home/mo/.local/share/FreeCAD/v1-1/Mod/Silk
git checkout unified-workflow-wizard && git pull --ff-only
# 1. the rolling build's state (Path A):
git log --oneline -8
git status                      # must be clean before merging anything
# 2. merge the held work, then ONE gate for all of it:
git merge --no-edit ticket/work-121
git merge --no-edit ticket/work-120        # if it has landed
flock /tmp/silk_rpc.lock -c "python3 Tests/run_all.py"      # fast tier
flock /tmp/silk_rpc.lock -c "python3 Tests/run_all.py --manual test_blend_grid_toggle"
flock /tmp/silk_rpc.lock -c "python3 Tests/run_all.py --manual test_corner_orientation"
# 3. the RSS measurement (#123) - it needs the live FreeCAD:
python3 Tests/rss_baseline_measure.py --runs 5      # keep the raw output it prints
# 4. the rolling corner, by hand, for the owner's eye:
#    Resources/Test_files/_inspect/rolling_*.png and shipped_shaded.png
```

**Do not** re-run the whole `--manual` tier as a habit: it is ~12 min and the
192-test fast tier now carries the load-bearing guards (the chain gate, the
#67 stored-cycle guard, the #72 single-generation guard, the continuity
calibration). A tier split needs **its own machinery in the tier it protects** —
that is why `test_runner_timeout` was pulled back into the fast tier.
