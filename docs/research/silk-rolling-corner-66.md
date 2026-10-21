# The rolling corner, path (A): the 66 over the cut cells (#119)

**What this is.** The ground truth for the rolling corner, read OFFLINE
from the maintainer's own finished model, and what Silk's cell structure
can and cannot say with it.  Every number here was measured with the
shipped instruments (`Tests/g2_corner_roll_measure.py`,
`Tests/g2_corner_roll_visual.py`, `Tests/continuity_calibration.py`) on
the cube-corner fixture (`Tests/cube_corner_model.py`), and the raw
output is the console log of

```
freecad Tests/rolling_corner_66_visual.py     # the numbers + the render
```

(the same in-process launcher the gate uses; it needs a GUI for the
pictures, not for the numbers).

---

## 1. The maintainer's file, read offline

`upstream/master:Resources/Tutorial_Files/Silk CopyPasta/
Silk_CopyPasta_27_First_Corner_Rolled.FCStd` (and its 25/26
predecessors) is a zip.  `Document.xml` holds the object classes, the
links and the stored nets; the pole lists live in separate `Poles*` /
`Weights*` files.  It is read offline, never opened in FreeCAD.

The corner's object chain:

```
ControlGrid66_4Sub_012  ->  4 x SubGrid33_2Grid64
   SubGrid33_2Grid64_048: ControlGrid64_2Grid44_048 + ControlGrid64_3_Grid44_000
   SubGrid33_2Grid64_049: ControlGrid64_3_Grid44_000 + ControlGrid64_2Grid44_033
   SubGrid33_2Grid64_050: ControlGrid64_2Grid44_033 + ControlGrid64_2Grid44_051
   SubGrid33_2Grid64_051: ControlGrid64_2Grid44_051 + ControlGrid64_2Grid44_048
      -> CubicSurface_66_013
```

So the corner is **four** members -- three blends
(`ControlGrid64_2Grid44`, each over two `ControlGrid44_2EdgeSegments`)
and one **triangular member** (`ControlGrid64_3_Grid44_000`, over one
cell).  There is no separate triangle beside the 66: the "smaller
triangular surface" of the owner's reading IS the member's own face.

### 1.1 The ring members are CUTS of the base surfaces

Every member's cell is a `ControlGrid44_2EdgeSegments` -- a two-edge cut
of a base surface, bounded by two curves that are SEGMENTS of the
surface's own edges (`ControlPoly4_segment` + `CubicCurve_4`).  Read
off the stored cells (their parametric spans against the corner patch's
own net, and the segment objects' `Point_onCurve` pairs), with the
corner patch's surface `CubicSurface_44_036` parameterised (su, sv):

| cell | surface | span (su) | span (sv) | what it is |
|---|---|---|---|---|
| 142 | 036 (the corner patch) | 0 .. 1/16 | 0.25 .. 0.75 | the band of seam curve200 |
| 141 | 036 | 0.25 .. 0.75 | 0 .. 1/16 | the band of seam curve248 |
| 140 | 036 | 1/16 .. 0.25 | 1/16 .. 0.25 | the MEMBER's cell |
| 137 | 054 | -- | 0.25 .. 0.75 | the other side of the curve200 band |
| 138 | 054 | -- | 0 .. 0.25 | the other side of the curve248 band |
| 101 | 039 | 0 .. 0.25 | -- | the other side of the curve248 band |
| 108 | 039 | 0.25 .. 0.75 | -- | the other side of the curve200 band |

The numbers behind them: the seam curves are cut at **1/16 = 0.0625**
(the setback -- the band's width across the seam) and at **0.25** (the
leader -- where the band's along-seam extent starts); the `Point_onCurve`
objects labelled `..._leader` carry u = 0.0625 and 0.8125, and the
`..._leader005` points carry u = 0.25 and 0.75.

**So the maintainer's corner patch is cut at TWO positions per axis:**
the setback (1/16) and the leader (0.25).  The corner fill's boundary
against each blend is that blend's CUT EDGE, i.e. it sits AT THE
LEADER; the member's cell is the region BETWEEN the setback and the
leader.

### 1.2 Where the junction is, and where the member pinches

The junction is the surface's corner (su, sv) = (0, 0) = (-100, -100, 0)
in the file's own coordinates -- the point where seam curve200 (the
su = 0 edge) and seam curve248 (the sv = 0 edge) meet.

The member's grid (`ControlGrid64_3_Grid44_000`, 24 poles, one row
collapsed) pinches at (0.25, 0.25) -- the LEADER/leader corner, NOT at
the junction.  The junction square (0 .. 1/16)^2 is not in any of the
seven cells: it is preserved original surface (the file's "backfill"
surfaces).

### 1.3 The structure to aim for, in Silk's words

Silk's shipped 3-valent corner is the same OBJECTS (a 66 over four
members, one of them the triangular member, plus the member's own face
as a separate surface) with a different REGION: Silk's member is the
patch's corner CELL, and its collapsed row -- the apex the 66 pinches
at -- is AT THE JUNCTION.  The maintainer's is the cell between the
setback and the leader, and its apex is at the leader/leader corner.

---

## 2. Which quantity sets Silk's 66's boundary, and the coupling

In Silk's machinery the corner fill's boundary against a blend is that
blend's JUNCTION ROW: the end row of the band's cell that faces the
junction.  The band's cell is a rectangular cell of the patch's
subgrid net, so that row sits at the patch's named band edge on the
seam-parallel axis, at the junction end.  **That one split value is
what the leader moves.**

The consequence, stated plainly and not hidden: Silk's patch carries ONE
named band edge per axis end (#82), and that edge is at once

  * the setback of the PERPENDICULAR seam (the band's width across it),
    and
  * the leader of THIS seam (the band's along-seam extent).

Moving the leader therefore moves that setback with it.  The
maintainer's model has the two as separate cuts (1/16 and 0.25) and does
not have this coupling; Silk's cell structure cannot hold both numbers
at one axis end, and this build keeps one number.

**A uniform leader is a pure scaling.**  Measured (cube-corner fixture,
all three seams at the same setback, no rolling construction at all):
the curvature spread is **1.03694 at setbacks 0.1, 0.25 and 0.5** -- the
same to thirteen digits, because the corner is a scaled copy of itself.
The leader moves the SHAPE only when it is moved on SOME of the ring's
seams.

---

## 3. The numbers (the acceptance instrument)

Fixture: `Tests/cube_corner_model.py` (three exact planar squares).  The
rolling corner is `create_rolling_corner_66` with the leader on the two
seams the pinned patch `PatchA` carries.

| configuration | k_max | k_min | ratio | saddle cells | foot ratio |
|---|---|---|---|---|---|
| shipped corner | 8.90142 | 8.58433 | **1.03694** | 52/1024 = 5.08 % | 1.1772 |
| rolling, leader 0.125 | -- | -- | **1.14972** | 52/1024 | 1.6263 |
| rolling, leader 0.25 (the maintainer's) | 2.10333 | 1.56412 | **1.34474** | 52/1024 | 3.1715 |
| rolling, leader 0.50 | 0.561144 | 0.399593 | **1.40429** | 52/1024 | 7.3289 |

(the spread is measured at the corner's centre; the "foot ratio" is the
spread at the point nearest the junction -- `junction_probe`'s foot.)

**The spread MOVES with the leader** -- 1.03694 -> 1.34474 at the
maintainer's own 0.25, and the junction foot's anisotropy moves from
1.18 to 3.17 (7.33 at 0.5).  The curvature MAGNITUDES move too, but
they are scale, not shape: k_max falls as 1/size^2 (8.90 -> 2.10 ->
0.561).

**The saddle-cell fraction does NOT move**: 52/1024 = 5.08 % in every
configuration, and the 52 cells are the SAME cells (checked: the sets
are equal).  They are the degenerate apex region -- the member's
collapsed row -- which is a parametric invariant of the construction.

The saddle count is not blind to the shape, though: #118's rotational
asymmetric setback (every patch one large and one small setback) reads
**320/1024 = 31.3 %** with a ratio of 2.288, against the symmetric
config's 52/1024 and 1.037.  So the instrument works; the rolling
corner's leader simply does not reach that pattern:

* the leader is ONE number per seam, written on both patches of the
  seam, so the seam's two sides get their setback from the leader of
  the NEIGHBOURING seam;
* the rotational LARGE/SMALL pattern needs one seam's two patches to
  carry DIFFERENT setback values (E_BC's pair is {B.V = small,
  C.V = large}), which one leader per seam cannot write.  It is a
  parity obstruction of the coupling, not a tuning problem.

Measured over every reachable subset of the ring (leader 0.25), the
spread moves for every non-uniform subset and the saddle count stays
52/1024:

| rolled seams | ratio | saddle |
|---|---|---|
| none (shipped) | 1.03694 | 52/1024 |
| B_AB | 5.56728 | 52/1024 |
| B_BC | 2.34400 | 52/1024 |
| B_CA | 5.56728 | 52/1024 |
| B_AB + B_BC | 3.62434 | 52/1024 |
| B_AB + B_CA (the default: PatchA's two seams) | 1.34474 | 52/1024 |
| B_BC + B_CA | 3.62434 | 52/1024 |
| all three | 1.03694 | 52/1024 |

(all three = a uniform setback = a scaled copy = the shipped shape.)

---

## 4. The junction, the seams and the default path

**The junction at the cut is CLOSED.**  The corner fill's boundary IS
each blend's junction row, so the C0 residual between the 66's own
surface and each blend's cut edge is at the instrument's floor:

| configuration | B_AB | B_BC | B_CA |
|---|---|---|---|
| shipped corner | 1.55e-17 mm | 1.388e-17 mm | 1.389e-17 mm |
| leader 0.25 | 2.86e-17 mm | 2.781e-17 mm | 1.394e-17 mm |
| leader 0.50 | 5.598e-17 mm | 5.562e-17 mm | 1.412e-17 mm |

Path (B) left **0.2915 mm** there (and 0.1522 mm at the triangle); both
are gone.

**The small triangular surface against the 66**: worst 0.04855 mm at
leader 0.25 (0.05846 mm at 0.5), 0 mm at the apex.  The member's face
and the 66 share only the collapsed (degenerate) row, so the member's
base edge is not on the 66's boundary -- in the maintainer's file it is
(his 66 takes the member's setback edges, because his member's cell is
the region between the setback and the leader).  The owner's FreeCAD
replacement of that face matches the face it replaces to **2.781e-17 mm**
and stands the same 0.04855 mm from the 66.

**The seam k_gap** (corner against the strip it feeds; exact from the
control net, sampled along the seam; the instrument's floor is 0
k_gap/mm and 0 mm c0, `Tests/continuity_calibration.error_floor`):

| configuration | B_AB exact / sampled | B_BC exact / sampled | B_CA exact / sampled |
|---|---|---|---|
| shipped corner | 9.594e-13 / 0.00238 | 7.808e-15 / 0.004563 | 2.485e-13 / 0.00238 |
| leader 0.25 | 3.412e-13 / 0.0009015 | 1.604e-14 / 0.01141 | 4.441e-14 / 0.0009015 |
| leader 0.50 | 8.956e-14 / 0.00045 | 2.479e-14 / 0.02281 | 1.136e-14 / 0.00045 |

**The default path is unchanged.**  A blend with `Leader` = 0 is the
shipped blend, pole for pole: max pole deviation **0.00e+00 mm**, max
weight deviation **0.00e+00** (`Tests/test_rolling_corner.py`).  This
build touches no shipped code path: the rolling corner is opt-in, and
the corner without it is the shipped corner.

---

## 5. What is left

1. **The setback rides along with the leader** (one cut per axis end).
   To hold them apart, Silk's cell structure would need a second cut at
   the junction end of an axis -- a new concept in the patch's data
   model, and #82 closed the "third split" question deliberately.
2. **The member's cell is the corner cell, not the region between the
   setback and the leader**, so the 66 pinches at the junction and the
   member's face stands 0.0486 mm off it.  The maintainer's 66 does not
   cover the junction at all (his junction square is preserved original
   surface).
3. **The saddle-cell fraction cannot serve as the leader's acceptance
   instrument in this construction**: it is the degenerate apex's, and
   it is the same 52 cells in every configuration.
4. The rotational LARGE/SMALL pattern of the video is unreachable through
   one leader per seam (parity, section 3).

---

## 6. The rolling corner is the DEFAULT, and the member's face is a fill (#119)

**The switch.**  The owner, 2026-10-21: *"the rolling corner fill should
be the default fill!"*  The switch lives in the OPS LAYER
(`SilkWorkflowOps.create_corner_blend(..., construction=...)`), because
the ops layer is the only construction path (AGENTS.md):

| `construction` | what it builds |
|---|---|
| `"rolling"` (THE DEFAULT) | the 66 over the ring's CUT cells, plus the small triangular member whose FACE is a FreeCAD `Surface::Filling` |
| `"shipped"` (THE FALLBACK) | the 66 with the spiderweb member -- the construction of before #119, byte for byte |

The wizard's corner step and the toolbar command both call the ops
layer, so both build the rolling corner, and the visible set stays
Edge -> Patch -> Blend -> Corner Blend (no new button).

**WHERE THE ROLLING CONSTRUCTION CANNOT BE BUILT, THE FALLBACK IS USED.**
The rolling leader is a CUT in the band, and Silk carries ONE band edge
per axis end (#82).  A patch that carries TWO junctions on the
seam-parallel axis cannot carry that cut -- the band edge is shared --
and the rolling construction refuses by name ("the band on Patch has 2
corner cells on its U axis, so it does not reach exactly one junction
corner").  That is the case in the demo-01 model and in the 2x2 corner
model: their patches carry several junctions, so their corners keep the
shipped construction.  The refusal is ATOMIC (the cut is planned before
it is written, and undone if the corner does not build), so the fallback
is the shipped corner, byte for byte.

**THE MEMBER'S FACE IS A FILL.**  The spiderweb member is kept -- it
carries the fill's boundary -- but hidden; the FreeCAD filling IS the
member's face.  The fill is built through the shipped component
(`create_fill`, #96) with #121's SELECTABLE C0 fallback, and its
continuity is measured with the shipped instrument (`fill_normal_gap`).

| | leader 0.25 | leader 0.50 |
|---|---|---|
| the fill's order (requested 1 = G1) | 0 (C0) | 0 (C0) |
| the tangent-plane gap against the silk face | 0 deg | 0 deg |
| the fill's own residual against the boundary | 3.0e-06 mm | 2.7e-06 .. 3.9e-06 mm |
| the fill against the silk member | 2.781e-17 mm | 5.562e-17 mm |
| the fill against the 66 | **0.04855 mm** | 0.05847 mm |

The G1 order is REFUSED by FreeCAD on this boundary (measured: the fill
is `Invalid` at orders 1 and 2), so the C0 fallback is what builds.  The
tangent-plane gap reads 0 deg because the fixture is PLANAR (both
surfaces are planes); on a curved corner it is the figure that says
whether the fill reached the order.

**CAN THE FILL TAKE THE MEMBER BOUNDARY AS IT IS?**  No: the member's
collapsed row is a DEGENERATE edge (its two ends are the apex), and a
degenerate edge is not a curve a fill can take.  The fill takes the
member's three REAL edges, which do close a loop.

**THE SHAPE, RE-MEASURED** (the baseline did not move: #125 fixed the
settling, not the geometry):

| configuration | k_max | k_min | spread | saddle cells |
|---|---|---|---|---|
| shipped corner (the fallback) | 8.90142 | 8.58433 | **1.03694** | 52/1024 = 5.08 % |
| default (rolling), leader 0.25 | 2.10333 | 1.56412 | **1.34474** | 52/1024 |
| default (rolling), leader 0.50 | 0.561144 | 0.399593 | **1.40429** | 52/1024 |

The seam `k_gap` (exact / sampled), the cut's C0 and the fallback's
byte-identity (0.00e+00 on poles and weights) are in the console log of

```
python3 Tests/run_all.py --manual     # and
import Tests.rolling_corner_default_visual as v; v.main()
```

(the renders: `Resources/Test_files/_inspect/rollingdef_*.png`).

**THE TWO GAPS ARE UNCHANGED AND STILL STRUCTURAL.**  The saddle
fraction does not move (52/1024 in every configuration: it is the
degenerate apex's), and the setback still rides along with the leader
(one band edge per axis end).  Neither is fixed here.

---

## The leader becomes its own cut: the corner is TWO patches (#119, session 2)

**WHAT WAS WRONG.**  The 66 was built from the ring's cells, as upstream
does — the wiring was never the problem.  The problem was that the leader
was written into the BAND EDGE, so on the member's patch the leader and
the setback were ONE number.  Both blends adjacent to the member then
terminated their junction rows at the SAME point (the patch's far cell
corner), the ring's 4th corner coincided with the 3rd, the 66 came out with a
whole collapsed side — and its surface swept over the member's own cell
instead of stopping at it.  Measured: the member's interior lay
0.0002–0.017 mm from the 66 (0.1–10 % of the corner extent) = inside it.

**THE REFERENCE, MEASURED** (upstream's own finished corner, file 27, the
classes read from the FCStd's stored `.brp` shapes with `Part.Shape().read`):
his 66 has **36 distinct poles**, its v=0 side IS the triangle's flowing row,
and his triangle's interior sits **8.0–31.0 mm from the quad = 16–62 %** of
the corner's 50 mm diagonal.  NOTE: his quad's bounding box CONTAINS his
tri's bounding box too (the tri pokes out by only 0.79 mm in y, 0.07 mm in
z), so a bbox test cannot separate the two cases — the distance instrument is
the one that can.

**WHAT LANDED.**

1. `SilkPatch` gains `ULeader1/2`, `VLeader1/2` — a cut of its own, ADDITIVE
   and default-off (sentinels per slot, so a patch without one reads exactly
   the two band edges it always read; the shipped construction stays
   **0.00e+00** on poles and weights).
2. `SilkMachinery` reads it: `axis_cuts`, `build_intervals`, `axis_intervals`,
   `axis_has_cuts`, `corner_cell_index`, `corner_cells`, `band_extent`,
   `band_cells`, plus `leader_cut_problem`.  The CORNER CELL is the interval
   BETWEEN the setback and the leader; a leader that does not clear its band
   edge is INERT and named.  `Tests/test_leader_cut.py` pins the identity,
   the new cell, the one-cell band invariant and the refusal.
3. `RollingMemberFace` names its boundary edges by position in the SHAPE's
   edge list, not in the list of non-degenerate edges: the old numbering
   handed the fill the collapsed edge as its second side whenever that edge
   was not the last one (`Edge1 meets both of its loop neighbours at the SAME
   end`).

**THE TWO-SURFACE ARRANGEMENT WAS BUILT AND MEASURED — AND IT FOLDS, so it is
NOT shipped.**  What was tried: write the leader cut on the MEMBER patch (not
both patches of a seam — cutting both breaks the ring at the other patch,
where its own two blends stop meeting: `corner_grid` refuses with "the two
grids share no corner"), and feed the member to the ring REVERSED, so its
real row is the ring row at V = 3 like every strip's.

| cube corner, leader 0.25 | before (leader in the band edge) | the two-surface arrangement |
|---|---|---|
| 66 area | 0.011007 | **0.063310** |
| 66 collapsed side | **yes** (a whole row on one point) | **no** |
| tri (member) area | 0.003578 | 0.020609 |
| tri bbox | (0,0,0)→(0.0625,0.0625,0) | (0.1,0.1,0)→(0.25,0.25,0) |
| tri interior → quad | 0.0002–0.017 mm (0.1–10 %) | **0.01478 mm max = 4.02 %** |
| seam k_gap (exact) | 9.6e-13 /mm | **56.65 /mm** |
| the cut's C0 | 5.6e-17 mm | 5.6e-17 mm |
| **normal-field flips** (n=39/81/150) | **0** | **25 / 53 / 96** |
| fine mesh self-intersects | no | **yes** |
| shipped fallback | 0.00e+00 | 0.00e+00 |

The two surfaces DO tile (overlap `0.00000000`, `distToShape` 0.0, the tri is
the far cell and the quad the ring around it — renders
`Resources/Test_files/_inspect/after_*.png`, produced from the experimental
wiring named above: the leader cut written on the member patch, and
`SilkCorner._MEMBER_ROW_ORDER_LEADER` used for that patch.  They are NOT
reachable from the committed tree; re-apply those two switches to
reproduce), but the member-side interior rows are extrapolated from the
member's own rows and the cap folds.
`SilkMachinery.smooth_degenerate_cap` re-solves rows on a COLLAPSED side, and
this arrangement has none there — the fix is a member-side re-solve, which is
the next piece of work, not a knob.

**THEREFORE, TODAY.**  The corner stage still writes the leader into the BAND
EDGE: byte-identical to before this session on every existing path, the cube
corner's cap still fold-free, the pins unchanged.  The leader CUT and its cell
rule are in place, tested, and waiting for that re-solve; the seam `k_gap` the
two-surface arrangement leaves (56.65 /mm) and the tri → quad distance (4.0 %
against the maintainer's 16–62 %) are the other two numbers to close.

**ALSO MEASURED, leader 0.9375** (the symmetric partner of 1/16 from the far
end): tri → quad 0.03078 mm = 2.32 %, k_gap 492.9 /mm, saddle 39.6 %,
tri bbox (0.1,0.1,0)→(0.9375,0.9375,0).

**WHAT IS STILL OPEN.**

* The member-side re-solve (the fold above) — the one thing between the
  machinery and the owner's two-patch corner.
* The seam `k_gap`: the cut is on the member patch only, so the strips'
  corner-side boundary is skewed.  Matching the leader on both patches needs
  two cuts per axis end on the OTHER patches as well.
* The saddle fraction (5.1 % → 32 % with the cut, still the degenerate
  apex's cells): the rotational LARGE/SMALL pattern the video shows is still
  out of reach with one leader per seam.
* #126 (the corner-cell refusal on the owner's own model) is untouched.

---

# The corner STAGE against the reference's ring: what landed, and the blocker

The primitives were never the limit: `Tests/prototype_reference_corner.py`
feeds the maintainer's own ring grids to `subgrid33_2grid64` +
`control_grid66_4sub` and reproduces all 20 quad corners of episode 28 (and
29) at **0.000e+00** on poles and weights.  What failed was the stage AROUND
them.  This session closed two of the four named defects and measured the
other two to a stopping point.

## Defect 1 — the ring normalizer was stricter than the algebra. FIXED.

`SilkMachinery.corner_grid` accepted only rings whose every adjacent pair
shared the corner slots `CORNER_COMMON` = (3, 2) or all of their mirror, and
refused **all 40** of the reference's rings ("the four strips are not a
consistently oriented ring").  His rings share (0,1), (0,2) and (3,1) as well,
mixed freely round one ring — seven distinct patterns over the two files —
and `subgrid33_2grid64` takes each pair on whatever corners it finds.

**The fix.** `corner_grid` now resolves the ring through `_oriented_ring`: the
ring AS STORED is used whenever its four pairs are all read without a grid
swap (the byte-identical path every ring this workbench builds takes); a ring
handed over mirrored is reversed and the reversed reading is used when THAT is
all one way.  No corner pattern is demanded.  A ring that MIXES the two
readings is still refused, BY NAME and with both patterns quoted — one of its
four subgrids would land transposed against its neighbours, so the 6x6's
interior rows would not line up, and a silent wrong surface is worse than a
refusal.

**The proof, through `corner_grid` itself** (`Tests/test_corner_ring_parity.py`,
fast tier): episode 28 **20/20** and episode 29 **20/20** quad corners
reproduced from the ring grids the files store, worst pole deviation
**0.000e+00 mm** and worst weight deviation **0.000e+00** over all 36 poles.
The same module pins the as-stored no-op (the ring is handed back as the same
list), the mirrored ring giving the identical 6x6 (0.000e+00 mm), and the
mixed ring's refusal by name.

## Defect 4 — the tri is a `CubicSurface_64` again, the fill selectable. FIXED.

The maintainer's tri face is `CubicSurface_64` over the member net.  Ours was
a FreeCAD `Surface::Filling`.  `SilkWorkflowOps.create_corner_blend(...
member_face=...)` now selects the face and **"cubicsurface64" is the
default**: the member's own 64 is the tri, the member is VISIBLE, and no fill
is built.  **"fill"** is the option — the owner's replacement surface, built
through the shipped `create_fill` (#96, #121's selectable C0 fallback) with
the silk member kept hidden behind it, exactly as before.  An unknown value is
refused BY NAME before anything is built (so it cannot fall through to the
shipped corner).  Measured on the cube corner: default → 1 face on the member,
**0** `Surface::Filling` in the document; `member_face="fill"` → 1 fill, the
64 hidden.

## The owner's two choices, and where they reach

* **Which patch carries the tri** (`MemberPatch` / `MemberCorner`, #117) now
  works on the ROLLING path.  The rolling construction resolved the pin for
  its cutting step and never wrote it onto the corner it built, so the
  corner's own `execute()` re-ran the AUTOMATIC search while the member
  followed the cut — the two surfaces could disagree.  Now: a USER's pin is
  written onto the built corner, and `SilkCorner._member_pin_of` makes the
  member read it (the member used to ignore the pin entirely: with the member
  pinned to PatchB its face did not move when PatchB's cut moved).  An
  UNPINNED corner still stores no pin — that is #117's opt-in contract, and
  the corner and the member then agree because both run the same search on the
  same ring.
* **How small the tri is** — the leader PER SEAM:
  `create_corner_blend(leaders={"B_AB": 0.5, ...})`, and the panel's corner
  page mounts **one editor per seam of the ring**, so the choice reaches every
  patch rather than only the member's.  `apply_corner_choices(strips,
  pin=..., leaders=...)` writes both onto a corner that already exists (the
  panel's Apply); it refuses by name when the ring has no corner yet, so it
  cannot become a second creation path.

Measured (cube-corner fixture; the tri's own face area; the check lines of
`Tests/test_corner_choices.py`):

| member on | one leader 0.25 | one leader 0.50 | member bbox max (0.25) |
|---|---|---|---|
| PatchA[0] | 0.057246 | 0.228984 | (0.25, 0.25, 0) |
| PatchB[0] | 0.057246 | 0.228984 | (0, 0.25, 0.25) |
| PatchC[0] | 0.057246 | 0.228984 | (0.25, 0, 0.25) |

At ONE leader the three areas are EQUAL and the three PLACEMENTS differ: the
three member cells are the same square on three planes, which is the
fixture's symmetry.  With a leader PER SEAM the cells become three different
rectangles and the area follows the member patch too:

| member on | {B_AB:.5, B_BC:.25, B_CA:.1} | {B_AB:.9, B_BC:.5, B_CA:.2} |
|---|---|---|
| PatchA[0] | 0.045797 | 0.164868 |
| PatchB[0] | 0.114492 | 0.412170 |
| PatchC[0] | 0.022898 | 0.091593 |

## Defect 2 — the member's collapsed row is still consumed on our ring. NOT FIXED.

**The finding, in the terms the next attempt needs.**  On our cell layout the
member's **collapse corner IS the ring's shared corner**, so **no pairing or
orientation avoids it**.  The ring's shared corners on the cube fixture are
the three patch corner cells' FAR corners — A = (0.1, 0.1, 0), B = (0, 0.1,
0.1), C = (0.1, 0, 0.1) — and the triangular member's collapsed row is the
whole row through A, so A sits at member slots 2 **and** 3.  Measured over all
**24** (patch, corner 0..3, reversed) member candidates: every one either
refuses ("the two grids share no corner" / "more than one corner") or
assembles WITH the collapsed side — 15 of the 6x6's coincident pairs are that
row (17 counting the apex's two extra hits).

**The reference's zero-coincident 6x6 needs a different LOOP.**  His member's
cell is the region **between the setback (1/16) and the leader (0.25)**, so
his strips' junction rows terminate at the member's MIXED corners, and the
member's real row (the L around its near corner) — not its collapsed row — is
the 6x6's fourth side.  In our machinery that arrangement is the leader cut on
**every** patch, and **that arrangement opens our ring today**: with
`ULeader1 = VLeader1 = 0.25` on all three patches (intervals [0,.1],
[.1,.25], [.25,1], the corner cell correctly (1,1)) the strips stop sharing
corners with each other AND with the member — "the two grids share no corner"
on pairs 0→1 and 3→0 — and `corner_inputs` refuses "could not build
triangular 4th member".  So the remaining work is **which rows form the ring
loop** (the member-side re-solve #119 names), not the assembler's pairing
rule.

## Defect 3 — the cap smoothing could not be removed. BLOCKED BY DEFECT 2.

Measured directly on the fixture, same instrument (`SilkChecks.
_normal_field_flips`, n = 39/81/150), from the assembled net with the
smoothing removed and with it:

| | flips n=39 / 81 / 150 | net moved by the smoothing |
|---|---|---|
| RAW (smoothing removed) | **19 / 23 / 24** | 0.0000e+00 mm |
| smoothed (shipped) | 0 / 0 / 0 | 5.6256e-02 mm |

So the smoothing stays, by the ticket's own rule ("if a fold appears without
the smoothing, stop and report").

## The acceptance, stated honestly

1. **Met** — the parity table THROUGH `corner_grid`: 20/20 quad corners of
   episode 28 and of episode 29 at 0.000e+00 (poles and weights).
2. **NOT MET** — our 6x6 still has 15 coincident pole pairs (the member's
   collapsed row is still a boundary side); the member net keeps its 15.
3. **NOT MET** — the cap smoothing cannot be removed; unsmoothed 19/23/24
   flips against the smoothed 0/0/0.
4. **Met** — the tri is a `CubicSurface_64` by default, the fill selectable,
   and the tri's area changes with the leader and (under a per-seam leader)
   with the member patch.
5. **Met** — the shipped fallback is untouched: `construction="shipped"`
   builds no cut, writes no pin and is pinned byte-identical by
   `Tests/test_corner_blend.py::test_corner_blend_pole_parity_with_legacy_chain`
   and `Tests/test_chain.py::test_chain_corner_ground_truth` (max pole dev
   5.55e-14 against the fixture's stored poles).

**The sentence this ticket may not lose:** the primitives reproduce all 20 of
his corners at 0.000e+00; the stage now accepts his rings (defect 1) and
builds the tri as his 64 (defect 4); **the ring LOOP is still ours**, so the
assembly still consumes the member's collapsed row and still needs the cap
smoothing.  Our corner stage does NOT yet reproduce his corner.

Renders (`Tests/rolling_corner_reference_visual.py`, MANUAL, one camera RULE
scaled per subject — our fixture is 0.1 mm at the origin and his geometry is
tens of millimetres elsewhere, so one literal camera cannot frame both):
`Resources/Test_files/_inspect/ringref_1_ours.png` (66 + tri at leader 0.25),
`ringref_2_ours_leader050.png`, `ringref_3_tri_leader025.png`,
`ringref_4_tri_leader050.png`, `ringref_5_reference.png` (his 66 and 64 drawn
from the nets his file stores, read offline).  Measured on the same run: our
66 0.078693 mm² at leader 0.25 and 0.262572 mm² at 0.5; our tri 0.057246 /
0.228984; the reference's 66 5187.829202 mm² and its tri 1439.902924 mm² —
all with 0 normal-field flips at n = 39/81/150.
