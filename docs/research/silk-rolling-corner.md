# The rolling corner, built (ticket #119) -- path (B)

**What this is.** The opt-in construction the owner specified for the
rolling corner: split two of the three edge blends at a *rolling leader*
(a position on the seam curve, measured from the junction corner), give
the corner a small triangular surface of its own, and put the two
together. Everything here is assembled from what Silk and FreeCAD
already provide: the patch's own base surface (segmented), the shipped
blend algorithm, FreeCAD's own `Surface::Filling`. No new maths, no new
surface type.

**PATH (B) -- AND WHY IT IS (B).** The owner's own analysis of the
maintainer's video: *"fundamentally the corner blend is constructed of
one quad surface (created with Silk tools, so well behaved and low
order, blends nicely) and a smaller triangular surface ... edward
proposes this smaller surface to be replaced with a freecad surface
patch."*  So the rolling corner is:

* the **big quad patch** = the **0.75 piece** of each split edge blend
  (the blend surface itself -- a `CubicSurface_64`, Silk-made, low
  order), and
* the **small triangular surface** = a FreeCAD `Surface::Filling` over
  the corner region's boundary.

**NO `ControlGrid66` AND NO TRIANGULAR MEMBER ARE BUILT ON THIS PATH.**
The maintainer's 66 is a *four*-member fill; a 3-valent corner has only
three blends, so the fourth member (the "scaffolding piece" with a
collapsed row -- upstream's "stepping stone") is what makes a
Silk-native 66 possible at all.  The owner's spec does not want it: the
corner face here is FreeCAD's own filling, and a 66 plus a member would
be scaffolding nobody uses.  The **shipped default** 3-valent corner
(which DOES build the member and the 66) is untouched, and it is what
the rolling corner is measured against.

**The default path is untouched.** A blend with `Leader` = 0 (the
default) is the shipped blend, pole for pole: the same 24 poles, the
same weights, deviation `0.00e+00`
(`Tests/test_rolling_corner.py::test_a_blend_without_the_leader_is_byte_identical_to_the_shipped_one`).

---

## 1. The parameter space (one statement, used by every piece)

The **rolling leader** is a fraction of the **seam curve's own
parameter**, measured from the junction corner. A patch's base surface
is a bicubic Bezier, and one of its boundary sides is a cubic Bezier
curve whose parameter *is* that side's surface coordinate -- so "0.25 of
the way along the seam curve" is the surface coordinate 0.25 (0.75 when
the corner sits at the far end of the seam).

It is **not** the band depth (the setback) and **not** an arc-length
fraction. The maintainer's own tool places the cut by a curve position,
and a Bezier segment carries a curve position.

## 2. Stage 1 -- the split

`SilkWorkflowOps.create_split_blend(patch_a, patch_b, leader=0.25)`
returns **two** blends: the corner-side piece (the band's own extent up
to the leader) and the outer piece (the rest). Both are real surfaces
(24 poles, a face each).

They meet **exactly** at the cut: the cut is a knot line of both nets,
because the patch's base surface is *segmented* there
(`SilkMachinery.split_band_cells` -> `BSplineSurface.segment`), not
re-fitted. Measured on the cube-corner fixture by **evaluated curve
deviation** (33 samples, the two pieces' closest boundary edges):
**5.551e-17 mm**.

The patch object is **not** modified: a leader is a position on the seam
curve, and the patch's two named band edges are the band's own depth --
there is nowhere on the patch to keep a third number. The split is a
property of the blend (`Leader`, `LeaderPiece`).

## 3. Stage 2 -- the triangle

`create_rolling_triangle(patch, sides, leader)` builds a FreeCAD
`Surface::Filling` (through the shipped `create_fill`, so it carries the
same by-name refusals and the same C0 boundary oracle) over a boundary of
**three** curves:

* the corner-side piece of the **first** split seam's curve -- the seam
  curve from the junction corner to the leader point,
* the corner-side piece of the **second** split seam's curve, and
* the **chord across the corner**: the straight line joining the two
  leader points.

**The third side is the one ambiguous piece of this construction, and
the choice is named here: the chord across the corner.** The two
alternatives the owner listed are *the maintainer's collapsed triangular
member* (a degenerate surface -- it collapses to a point, so it is not a
boundary a fill can take) and *the third seam's blend end* (which closes
a different hole: the third seam's own corner). The chord is what makes
the three boundary curves meet.

## 4. Stage 3 -- the junction

`create_rolling_corner(strips, patch, leader)` puts the three stages
together: the two ring strips on the pinned patch's seams are split, and
the triangular fill is built beside them.  **No corner blend and no
triangular member are built** (path B, above).

**The junction is a GAP, and that is reported rather than papered over.**
The triangular fill's third side is the chord across the corner; the
0.75 piece of a split blend ends at the leader with a **cut edge across
the band**.  The two do not share a boundary curve: on the cube-corner
fixture the chord sits **0.2915 mm** from the 0.75 piece's surface.  This
is exactly the owner's *"part of the edge blend needs to be replaced
with a (patch66? type) surface, to allow for blending this part of the
edge to the smaller triangular corner patch"*.  **No 66 was invented to
close it** (the owner's instruction): the options are

1. build the fill over the leader rows instead of the chord, so the
   fill's boundary IS the blends' cut edges (the two leader rows do not
   close with the third seam's row, so the third side has to grow);
2. extend the 0.75 piece's end so that it meets the chord (the piece
   would have to be re-fitted -- a change to the shipped blend
   algorithm, not a new surface);
3. keep the gap and let the user decide (what this build does).

## 5. What the measurement says (and it is not what was hoped)

`Tests/rolling_corner_visual.py` (MANUAL) renders the corner and
measures it on the **cube-corner fixture** (`Tests/cube_corner_model.py`
-- three exact planar squares, never Demo 01), with the video's own
numbers: leader **0.25** on two of the three seams, rotational.

Images (`Resources/Test_files/_inspect/`, one fixed camera -- the same
one `Tests/g2_corner_roll_visual.py` uses):

| image | what it shows |
|---|---|
| `rolling_1_shaded.png` | the rolling corner: the triangular fill (blue) and the split blends (green) |
| `rolling_2_triangle.png` | the triangular surface alone |
| `rolling_3_ratio.png` | the curvature ratio k_max/k_min of the **shipped** corner (the instrument of #118), on its exact 6x6 |
| `rolling_4_gauss.png` | the Gaussian curvature k_max*k_min of the same |
| `shipped_shaded.png` | the **shipped** corner on the same fixture, for comparison |
| `rolling_legend_ratio.png`, `rolling_legend_gauss.png` | the colour legends |

Numbers (the same run):

| quantity | value |
|---|---|
| the triangular fill's own spread (its own surface) | k_max 0.0000, k_min 0.0000 -- **flat**: the cube corner's faces are planar, so the fill over three curves that lie in one plane is that plane |
| the fill's saddle samples | 0 of 441 |
| the **shipped** corner's spread at the junction | k_max 8.9014, k_min 8.5843, **ratio 1.037** |
| the shipped corner's near-junction ratio range | 1.037 .. 1.676 |
| the shipped corner's saddle cells | 52 of 1024 = 5.1 % |
| the triangle's boundary against the shipped corner's surface | **0.1522 mm** |
| the gap between the triangle's chord and the 0.75 piece's surface | **0.2915 mm** |
| the ring's seam `k_gap` (the shipped corner against its three strips; the split blends' corner-side pieces carry the same junction rows, so these are their numbers too) | **9.594e-13**, **7.808e-15**, **2.485e-13** /mm exact; sampled 2.4e-3, 4.6e-3, 2.4e-3; instrument floor 0 |

### The finding: the leader does not reach the shipped corner's shape

**The shipped corner's curvature spread is the same with and without the
leader** (1.037 both ways -- the table above).  The leader changes the
two blends, and the two blends are two real surfaces that meet exactly
at the cut -- but the shipped corner's own surface comes out the same
shape.  The mechanism is in the shipped corner chain, and it is worth
writing down because it says where the rolling has to come from:

1. **The subgrid extrapolation is scale-invariant along the seam.**
   `SilkMachinery.subgrid33_2grid64` extrapolates a corner pair's
   interior with `p11_u = p01 + (u_row0[1] - u_row1[1]) * v_tan_ratio`,
   where `u_row0[1] - u_row1[1]` is the member's **along-seam step** and
   `v_tan_ratio` divides by the **other** along-seam step. The two
   factors cancel: a member that is 3.3x shorter along its seam
   extrapolates exactly as far. So the corner's interior does not see
   how far a member runs along its seam.
2. **The corner's boundary is the member's junction row**, and that row
   sits at the band's own corner end (the corner cell's edge) -- which
   the split does not move: the corner-side piece and the outer piece
   share that row exactly.

So in Silk's corner machinery the along-seam extent of a ring member
cannot roll the corner; only the **boundary** can. The maintainer's
rolling corner gets its two zones from the boundary (his ring members
are *cuts* of the base surfaces, so their junction rows sit at the
cut), which is the step #119's Stage 1 was written for and the step
this build does not yet close.

**The triangle, meanwhile, is a flat sheet in this fixture.** The cube
corner's faces are planar, so the two seam segments and the chord all
lie in one plane and FreeCAD's fill over them is that plane (k_max =
k_min = 0).  On a curved model (the maintainer's demo) the same three
curves do not lie in a plane and the fill is a curved triangle.

### The third side, and the two alternatives that do not close

The third side is the **chord across the corner**.  The two
alternatives the owner listed were both checked against the geometry:

* **the maintainer's collapsed triangular member's edge** -- derivable
  without building the member's surface (`SilkMachinery.
  control_grid64_3_1` over the pinned patch's corner cell is pure
  arithmetic, and its junction row is that edge).  It does not close the
  loop the two leader-long seam segments open: the edge runs between the
  corner cell's own edges, which sit at the **band's own width** (0.1 on
  this fixture), not at the leader (0.25).  Closing it would need the
  corner cell to be leader-sized, i.e. the setback pushed back to the
  leader -- and a leader at the setback is a degenerate split.
* **the third seam's blend end** -- the third strip's junction row runs
  at its own band's corner end (0.1 on this fixture), so it does not
  reach the two leader points either.

The chord is the curve that does close the loop, so it is what the
triangle is built on.  This is the assumption, and it is named in the
commit message.

## 6. Reproduce

```
import Tests.rolling_corner_visual as v; v.main()
```

The script writes its PNGs under `Resources/Test_files/_inspect/` and
prints the numbers above. The fast tier pins the construction contract
(`Tests/test_rolling_corner.py`): the split's exactness, the default
path's byte-identity, the triangle's three boundary curves, the
refusal by name, and the corner's build.
