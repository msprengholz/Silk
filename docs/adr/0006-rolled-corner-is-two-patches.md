# A rolled corner is TWO patches, and "looks right" is not the acceptance

**This file is where the rolled corner is stated.** Every other file that
describes it -- `AGENTS.md`, `GLOSSARY.md`, `docs/corner-blending.md`,
`docs/research/silk-rolling-corner-66.md`,
`docs/research/silk-ring-loop-127.md`, the handover -- points here instead of
repeating it. If one of them disagrees with this section, this section wins
and that file is the defect.

## What a rolled corner is, as built

A **rolled corner** -- the maintainer's `Silk_CopyPasta_28` / `_29` structure
-- is **two surfaces meeting along one curve**, plus the pieces the division
leaves behind: **ten roles in all** (#130).

- the **quad**: a `ControlGrid66_4Sub` -> `CubicSurface_66`, built over the
  ring's **four members** -- the two cut-back cells of the divided seams, the
  **third, uncut** seam blend, and the **triangular member's net**, read
  REAL-ROW-FIRST (`SilkCorner._member_row_order`);
- the **tri**: the triangular patch, a **separate object** beside the quad.
  Its **face** is its own net's `CubicSurface_64` (the construction the
  maintainer's files store) or a FreeCAD `Surface::Filling` over the net's
  three real boundary curves (the owner's option). It shares **one curve**
  with the quad, and the two are **adjacent, never overlapping** -- they may
  not describe the same area;
- **five preserved pieces**: one CELL of a ring patch each, kept as separate
  surfaces -- **three** from the patch that carries the tri (the cells one
  step beyond its corner cell in u, in v, and the diagonal one) and **one**
  from each of the other two patches. They are the patches' **own** cells
  read through `Patch.getSubgrid`, never re-fits
  (`SilkMachinery.preserved_piece_cells`, `Tests/test_preserved_pieces.py`).

**How the division is expressed.** The patch that carries the tri carries
**two cuts per axis end**: the **setback** (its band edge, the user's) and
the **leader** (`ULeader1/2`, `VLeader1/2`, additive and default-off, #119).
That patch's corner cell is therefore the region **between** the two, the
tri's own cell, and the two strips sharing that patch end their junction rows
at two DIFFERENT points (`SilkMachinery.ring_corner_gap` reads it OPEN; it is
the one patch per corner where two different ring corners are correct,
#127). The other two patches keep one cut per axis end, and **the third blend
is not cut** -- it is one full-length side of the quad.

**The cut is a LENGTH, not a fraction (#129).** `create_corner_blend` /
`create_rolling_corner_66` take the leader as **mm from the junction corner**,
per seam (`leaders={seam: mm}`), and the **default is `leader=None`**:
`equal_cut_length` puts the tri's two cut sides at the **geometric mean** of
the length the parameter default (`ROLLING_LEADER` = 0.25) gives them, so the
triangle comes out roughly even-sided -- the owner's rule (2026-10-22):
*"ideally both segment lengths should be close to the same absolute length
(not u or v values between 0 and 1, but the actual length in eg. mm). this
ensures a neat, closer to even sided triangle"*. A leader that does not clear
its setback is INERT and is refused **by name**, atomically.

**Whose choice is what.** The owner's choice is **which corner carries the
tri** (equivalently the patch it sits on, `MemberPatch` / `MemberCorner`),
the per-seam leader lengths, and the setback. Everything else -- the ring,
the read order, the pieces, the face -- the stage decides. It is *not* a
choice of "which patch carries a member grid": there is one member net per
corner and it is the tri's.

**What is measured** (`Tests/corner_even_cuts.py`, demo junction
`CB_J1_FrontTopRight`, artifact `_inspect/demo_corner_even.FCStd`):

| reading | value |
|---|---|
| the tri's two cut sides | 9.302915 / 32.677217 mm -> **17.435446 / 17.435446 mm**, residual 2.9e-13 mm |
| tri / quad area | 278.09 / 469.17 mm2 (0.5927) -> **293.62 / 567.06 mm2 (0.5178)**; his 0.2776 |
| tri interior -> quad, % of the corner's extent | 1.55..14.55 % -> **3.51..37.08 %**; his 8.0-31.0 mm, **16-62 %** |
| quad pole pitch, worst / best | 32.74 -> **26.93** |
| normal-field flips, n = 39/81/150 | 0 / 0 / 0 |
| coincident pole pairs, 6x6 | 0 / 630 |
| the five pieces' C0 to what they abut | <= 5.9e-14 mm |
| a settled document (#125) | 0 Touched, poles move 0.000e+00 mm |

On the cube-corner fixture (`Tests/test_two_patch_corner.py`, leader 0.25,
setback 0.1): 0/630 coincident pairs, the member keeps its own 15/276, 0/0/0
flips **without** `smooth_degenerate_cap` (the smoothing is a byte-identical
no-op there: the built 6x6 IS the raw assembly), seam `k_gap`
7.8e-15..1.6e-14 /mm exact and 0.0067..0.0093 sampled, the cut's C0
1.4e-17..5.6e-17 mm, areas 0.046713 / 0.020609 mm2.

**The tri-to-quad percentage is a READING, not the acceptance.** Its minimum
sits **below** the maintainer's 16 % floor on both fixtures (3.51 % on the
demo, 7.5 % on the cube). That figure is published here so it cannot pass for
green: what makes a rolled corner is the **construction** (two surfaces, one
shared curve, no overlap, five own-cell pieces) plus no fold -- not a
percentage, and not a curvature spread.

## Why this is recorded

The term **"rolling corner" was used for four different things** in this
project, and each one was built:

| intended | what got built |
|---|---|
| the **two-patch** arrangement above | a corner whose *curvature* responds to asymmetric setbacks (#118) |
| the **tri** = a second surface, beside the quad | a fill laid *over* the member's region, inside the quad |
| the **leader** = an independent cut | the leader written into the band edge, so setback and leader were one number |
| the **cut** = a length the owner sets | a fraction of each seam's own parameter, so one number cut 14.3 mm of one seam and 57.6 mm of the other (#129) |

Each build ended in "this is not a rolling corner". The cost was days.

## The acceptance, and why prose cannot be it

**A rolled corner is not a look, it is a construction.** The acceptance is a
**construction diff against the reference files** (`Silk_CopyPasta_28`/`_29`):
same objects, same classes, same inputs, same `u` values, down to the leaves
-- `Tests/prototype_reference_corner.py` (his 20 + 20 ring corners through
`corner_grid` at 0.000e+00 poles and weights) and
`Tests/reference_corner_diff.py`. "Looks right" is not a test, and neither is
a reading of a render; that reading produced the #118 over-claim ("it rolls")
that the owner had to correct.

**Useful reference numbers** (each named to the file it came from): on
`Silk_CopyPasta_27` the tri's interior sits **8.0-31.0 mm** from the quad, on
files **28/29** **4.6-35.5 mm**; both are **16-62 %** of a 50 mm corner
extent. Upstream's own bounding boxes overlap, so a bounding-box test
**cannot** separate the surfaces; the interior distance is the only
separating instrument there is.

## Consequences

- The shipped 3-valent corner (one 66 with the member inside it) is **not** a
  rolled corner, whatever its curvature numbers say. It stays as the
  **fallback** (`construction="shipped"`), byte for byte.
- A 4-valent ring has **no** third, uncut seam and **no** triangular
  remainder, so it keeps the shipped construction and says so.
- Nothing may be declared done while the quad covers the tri, however good
  its `k_gap` looks.
- `SilkMachinery.smooth_folding_interior` / `smooth_degenerate_cap` are
  **safety nets gated on the net itself** (a collapsed side, or a folding
  interior). They are **not** part of the rolling construction: on the built
  rolled corner the 6x6 is the raw assembly and both steps return it
  unchanged.

---

## The process, as the owner states it (2026-10-22, confirmed step by step)

This supersedes any earlier description in this repo of "how we build it".

1. **Start:** three patches meet at a corner; three edge blends lie along the
   three seams.
2. **Choose the corner** where the triangular patch goes -- equivalently, the
   **two patches adjacent to it**. (It is *not* a choice of "which patch
   carries the member grid"; that was our invention.)
3. **Divide the patch that carries the triangular patch** -- and, as the
   owner clarified the same day, **one** patch is divided, **once in u and
   once in v**, not two patches once each:

   > *"one of the three base patches get divided once in both u and v dir
   > making it 3 patches and thus, making 5 pieces in total"* ... *"dividing a
   > patch once in u and v gives four parts, but the corner piece will become
   > the triangular corner fill"*

   So the divided patch's 2x2 of cells resolves as: **the corner cell is the
   triangular patch**, the **other three** are preserved pieces, and **each
   of the other two patches contributes one piece** -- 3 + 2 = **5**, which is
   exactly what the maintainer's file stores. The earlier phrasing ("divide
   two of the three patches") names the same outcome; the mechanism is one
   patch divided on both axes.
4. **The two small pieces are two sides of the triangular patch.**
5. **Roll the corner:** build the **66 quad** *across* the two divided blends
   -- the owner's words: *"we basically do another edge blend across two of
   the existing blends."* Its four sides are:
   - the cut end of divided blend **A**,
   - the cut end of divided blend **B**,
   - the **third, uncut seam blend**,
   - the **edge shared with the triangular patch**.
6. **The triangular patch** closes the remainder: two sides are the small
   pieces from step 4, the third side is **the same curve** the quad's fourth
   side runs along (one shared curve, not two coincident ones).

**Two consequences that are now normative:**

- The **third blend is not cut**; it is one full-length side of the quad.
- The quad and the tri **share one curve**. They are adjacent, never
  overlapping.

**How the shipped cell structure lands on those steps.** Steps 5 and 6 are
what the code above builds: four members including the tri's net, one shared
curve, no overlap, the third blend uncut. Step 3 is expressed differently:
the division is carried by the patch that carries the tri, which is cut at
the setback AND the leader on **both** of its axes, so the tri's cell and the
tri's two sides lie on that one patch's cuts rather than on two patches'
apiece. Steps 2 and 4 (which corner, and a small piece as one side of the
tri) therefore hold in their result, not in their mechanism. This difference
is recorded, not resolved; the separating instrument is step 5/6's
"adjacent, one curve, never overlapping", and it is now measured by
non-overlap rather than by a percentage band.
