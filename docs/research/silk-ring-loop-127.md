# Which rows close the ring loop (#127)

**What this is.** The instrument first, then the rule it yields, then what the
rule costs. Every number below was produced by

```
python3 Tests/reference_corner_diff.py --rows            # his side, offline
freecad /tmp/<launcher>.py                               # ours, in FreeCAD
```

(`--rows` is #127's addition to the construction-diff instrument; the "ours"
half runs inside FreeCAD because it reads what `corner_inputs` assembles, and
`--with-ours` drives it over the RPC in the owner's GUI.)

---

## 1. The row map — his side, measured

`Silk_CopyPasta_29_Full_Blend_Solid_3X4_Clean_Up.FCStd`, corner
`CubicSurface_66_014` (the pick the instrument's rule makes: smallest
triangular net). Read offline from `Document.xml` + the stored nets; the
base-surface parameters are read by inverting each cell's own 4x4 net on the
surface's net, and **the residual of every inversion is printed as the error
floor** (1e-14 mm for a pole that lies on the surface, 2e-9 mm at the cell
corners that the fixture only approximates).

```
  the four ring PAIRS (the reader's own index map):
    0. ControlGrid64_2Grid44_035      | ControlGrid64_2Grid44_049       corners (0, 1)
    1. ControlGrid64_2Grid44_049      | ControlGrid64_2Grid44_050       corners (0, 2)
    2. ControlGrid64_2Grid44_050      | ControlGrid64_3_Grid44_001      corners (3, 1)
    3. ControlGrid64_3_Grid44_001     | ControlGrid64_2Grid44_035       corners (0, 1)

  per member: which rows its two pairs read, and what its own rows are
    035   pair 0 (g0 corner 0): rows (0, 1), across-seam columns (0, 1, 2)
          pair 3 (g1 corner 1): rows (0, 1), across-seam columns (5, 4, 3)
          RING V-END: V0 (both pairs) -> rows [0, 1] read; rows [2, 3] NEVER
          cells: 037 u 0.2500..0.7500 v 0.7500..1.0000   (6.4e-14 mm)
                 038 u 0.2500..0.7500 v 0.0000..0.0625   (2.1e-09 mm)
    049   pair 0 (g1 corner 1): rows (0, 1), columns (5, 4, 3)
          pair 1 (g0 corner 0): rows (0, 1), columns (0, 1, 2)
          RING V-END: V0 (both pairs) -> rows [0, 1] read; rows [2, 3] NEVER
          cells: 054 u 0.2500..0.7500 v 0.0000..0.2500   (2.1e-14 mm)
                 037 u 0.0000..0.2500 v 0.2500..0.7500   (2.1e-14 mm)
    050   pair 1 (g1 corner 2): rows (3, 2), columns (0, 1, 2)
          pair 2 (g0 corner 3): rows (3, 2), columns (5, 4, 3)
          RING V-END: V3 (both pairs) -> rows [2, 3] read; rows [0, 1] NEVER
          cells: 054 u 0.7500..1.0000 v 0.2500..0.7500   (2.9e-14 mm)
                 038 u 0.0000..0.0625 v 0.2500..0.7500   (1.6e-09 mm)
    TRI   pair 2 (g1 corner 1): rows (0, 1), columns (5, 4, 3)
          pair 3 (g0 corner 0): rows (0, 1), columns (0, 1, 2)
          RING V-END: V0 (both pairs) -> rows [0, 1] read; rows [2, 3] NEVER
          row V3: coincident pairs 15/15  <- the collapse, NOT read
          cell 038 u 0.0625..0.2500 v 0.0625..0.2500   (2.0e-09 mm)
          RING ROW V0 ends on 038 (0.2500, 0.0625) and (0.0625, 0.2500)
```

Three facts, all measured:

1. **Every member's two pairs agree on ONE V end**, and every member's other
   V end is read by no pair.
2. **His triangular member's collapsed row is V3 and no pair reads it.** The
   member's ring row is V0 — a real row — and its two ENDS sit on the mixed
   corners of the member's cell, `(leader, setback)` and `(setback, leader)`.
3. The two members sharing a patch meet at ONE 3-D point, which is the corner
   cell's **far corner** — the corner diagonally opposite the junction. On 037
   the junction corner is `(0, 1)` and the two cells are
   `[0, 0.25] x [0.75, 1]`, so their shared corner is `(0.25, 0.75)`.

## 1b. The row map — ours, measured (shipped default, leader 0.25)

```
  pair 0..3: corners (3, 2)   (all four, no swap)
  strip 0/1/2: RING V-END V3, rows [2, 3] read, rows [0, 1] NEVER read
  strip 3 (the member): RING V-END V3, rows [2, 3] read, row V3 = 15/15
                        coincident pairs  <- THE COLLAPSE IS ON THE LOOP
  quad: poles 36, coincident_pairs=15, collapsed 6x6 side 'v1'
  normal flips n=39/81/150: [0, 0, 0]  -- with smooth_degenerate_cap moving the
                                         6x6 poles by up to 0.1406 mm
  member interior -> quad: min 0.00003 max 0.03479 mm (0%..14% of extent)
```

**So the ROW RULE is already the same on both sides.** Every member is read on
the two rows at one V end, both pairs agreeing, the other end never read. What
differs is *which edge of the member's cell that V end is*: ours is the corner
cell's apex — the collapse — because our member is cut from the patch's corner
cell and its apex corner is the ring's shared corner.

## 2. The rule, in one sentence

> **A ring pair's shared corner is the shared patch's corner cell FAR corner;
> each member contributes ONE WHOLE ROW — the row through that corner — as one
> side of the 6x6, so both of its pairs are read on the same V end and its
> opposite V end lies inside the loop and is never read.**

For the pair to close on a patch, the two strips' ring rows must both END at
that far corner. On the axis ACROSS one strip's seam the far corner's
coordinate is that strip's **band edge** (where the band stops); on the axis
ALONG it, it is the along START (the corner cell's far edge = the leader cut
when there is one). The two strips of a pair name the two axes the other way
round, so the corner is one point exactly when

    the leader cut == the band edge, at each end of the patch's two axes.

`SilkMachinery.ring_corner_gap(p)` is that sentence as code: `None` when the
ring closes there, else the `(axis, band edge, leader)` that keep it open.
`Tests/test_leader_cut.py::test_the_ring_loop_closes_at_one_cut_and_opens_at_two`
pins it: the shipped cube corner reads `None` on all three patches; one leader
of 0.25 on `PatchA`'s two axes reads `('U', 0.1, 0.25)`; an INERT leader
(0.0625 inside a 0.1 band) reads `None` again.

## 3. Why the ring opens when the leader cut is on every patch

The two strips sharing a patch end their junction rows at, in that patch's
parameters, `(along = leader, across = band edge)` and
`(along = band edge, across = leader)` — `(0.25, 0.1)` and `(0.1, 0.25)` on the
cube corner. Two different points, so `pair_common` reports *the two grids
share no corner*, exactly as #119 measured.

His ring does not have that problem **because his member patch is the only
patch where two pairs meet**: each of those pairs takes one END of the
member's one row, and his member's row runs between those two points —
`(0.25, 0.0625)` and `(0.0625, 0.25)`, measured in §1. The member is the one
member whose cell must present TWO DIFFERENT ring corners, and its row is the
segment between them.

That is why #119's arrangement — the leader cut written as the **carrying
patch's** own cut, with the member fed so that its REAL row is the ring row —
closes the ring and produces the two-surface corner (0 coincident pairs, 66
0.0633 mm² against the member's 0.0206, no collapsed side, the two surfaces
tiling). And it is why writing the cut on **all** patches breaks it: every
other patch then has a pair whose two strips disagree about the corner.
**The third blend is not cut**: it is one full-length side of the quad
(`docs/adr/0006-rolled-corner-is-two-patches.md`).

**MEASURED, on the cube-corner fixture, through the corner stage's own
`corner_inputs`** (`Tests/test_leader_cut.py`, fast tier):

| cuts on the fixture | `ring_corner_gap` | `corner_inputs` |
|---|---|---|
| shipped (one cut per axis end, all three patches) | `None` on all three | assembles |
| two cuts on `PatchA` ONLY (the member patch) | `('U', 0.1, 0.25)` | **assembles** |
| two cuts on every patch | `('U', 0.1, 0.25)` | refuses: *could not build triangular 4th member; the ring's corner is OPEN on `PatchA`: its U axis carries a band edge of 0.1 and a leader cut of 0.25…* |

So **the loop rule needs no cell our cell model does not have**: the carrying
patch is the one patch allowed to carry two cuts, because its two ring corners
are the two ends of the member's row. What the arrangement lacks is the 6x6's
interior — see §5.

## 4. The acceptance, stated honestly

| # | criterion | status |
|---|---|---|
| 1 | the row diff exists and is readable, his side and ours, with the one-sentence rule | **MET** — `--rows`, §1/§1b/§2 |
| 2 | our 6x6 has ZERO coincident pole pairs, the member keeping its 15 | **NOT MET** — 15, collapsed side `v1` |
| 3 | fold-free at n=39/81/150 WITHOUT `smooth_degenerate_cap` | **NOT MET** — the shipped corner still needs it (it moved the 6x6 poles 0.1406 mm on this run; unsmoothed 19/23/24, `Tests/test_leader_cut.py`'s note and `silk-rolling-corner-66.md`) |
| 4 | the tri-to-quad interior distance in his 16-62 % range | **NOT MET** — 0 %..14 % of the corner extent |
| 5 | the shipped fallback byte-identical, the 4-valent corner unchanged | **MET** — `construction="shipped"` untouched; `test_corner_blend_pole_parity_with_legacy_chain` and `test_chain_corner_ground_truth` green |

2-4 are *not* a geometry claim that failed to be measured: they are the numbers
the shipped corner gives, and they move only with the two-surface arrangement.
That arrangement is reachable (the rule above says how) and #119 measured it:
2 becomes 0, 3 stays 25/53/96 flips (it FOLDS), 4 becomes 4.0 %.

## 5. What is left, and why it is not a patch

The rule needs no row our cells lack — the member's real row exists, and it is
the segment between the two points the two strips' rows end at, which is why
the member-patch-only arrangement assembles (§3, measured). What the
two-surface arrangement lacks is an **interior** for the 6x6: with no collapsed
side, `smooth_degenerate_cap` is a no-op, and the subgrid extrapolation past
the member's row folds the surface (25/53/96 flips, the fine mesh
self-intersects). #119 named it: a **member-side re-solve**. Until it exists,
the corner stage keeps writing the leader into the band edge — the shipped
corner, one cut per axis end, closed, fold-free, and with the member's apex on
the loop.

That is the decision this ticket hands back: the loop rule is settled (and
pinned as `ring_corner_gap`, and quoted by the corner stage's own refusal),
and the remaining work is the 6x6's interior re-solve, not another pairing
search.

## 6. Two measurements the ticket's gates asked for

* **The document still SETTLES (#125 intact).** After the corner stage builds
  the cube corner: `touched=[]`; three `doc.recompute()` passes leave
  `touched=[]`; a settled pass costs **0.0001 s**; and a further recompute
  moves the 6x6 poles by **0.000e+00 mm**. The `0.1406 mm` figure the
  instrument prints is NOT per-pass movement — it is the one-shot distance
  between the RAW assembly and the stage's smoothed poles.
* **The `Recursive calling of recompute` console warnings PREDATE this
  change.** Measured with a probe that builds **only** the cube-corner
  fixture (`cube_corner_model.build_cube_corner_model`, 33 objects, no corner
  stage and none of this ticket's code): **6** of those lines. They come from
  the ops layer's own `onChanged -> touch() + recompute()` nesting, which
  AGENTS.md documents.
* **The fast tier**: 227/227 green (`RESULT:{"total": 227, "passed": 227,
  "failed": 0}`, exit 0). **The manual tier could not be run here**: the RPC
  at 127.0.0.1:9875 refused (`ConnectionRefusedError`), and the offscreen
  `freecad Tests/run_all.py --manual` route — both full and filtered —
  produced no output and no exit within 500 s (the fast tier runs fine on the
  same route). It is the one gate this session did not close.

---

## 7. That 6x6 interior existed all along (#128, measured)

§4's "NOT MET" rows 2-4 and §5's "the remaining work is the 6x6's interior
re-solve" were measured against the arrangement our own stage built: the
leader written into the BAND EDGE on both patches of each rolled seam. **When
the leader is a cut of the member patch's own cell (and only of that patch),
and the member is read REAL-ROW-FIRST, the interior is fine.** Re-measured on
the cube-corner fixture through the corner stage's default construction:

| # | §4's criterion | the two-patch corner (#128) |
|---|---|---|
| 2 | 0 coincident pole pairs, the member keeping its 15 | **0 / 630** on the 6x6, 15 / 276 on the member |
| 3 | fold-free at n=39/81/150 without `smooth_degenerate_cap` | **0 / 0 / 0** on the Part surface and on the exact net; the smoothing moves 0.000e+00 mm |
| 4 | the tri-to-quad distance in his 16-62 % range | **7.5 %..53.5 %** (his 16..62 %) — the minimum is BELOW his floor, so this row is a READING, not a met criterion |
| 5 | the shipped fallback byte-identical | still met, 0.00e+00 |

The controls that make row 3 mean something, from the same run: the SHIPPED
corner's RAW assembly reads 19/23/24 flips (a known fold) and its BUILT form
reads 0/0/0 (a known good).  **Row 4 is not met and is not explained away**:
the minimum sits below his 16 % floor, and the corner's acceptance is the
construction (two surfaces, one shared curve, no overlap) plus no fold —
`docs/adr/0006-rolled-corner-is-two-patches.md`.

**What was wrong was not the 6x6, it was our choice of cut**: the two
arrangements differ in where the leader lives, and the one where it is a cut
of its own closes the loop, keeps the 66 out of the member's cell, and does
not fold. `Tests/test_two_patch_corner.py` is the instrument; the corner
stage's default construction is now that arrangement.
