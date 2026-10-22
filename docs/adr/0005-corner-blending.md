# Corner blending is its own stage; its continuity is measured, not asserted

Corner blending is its own stage, distinct from edge-to-edge blending: the
blending step splits into **edge blending** (on seams) and **corner blending**
(where several patches meet), surfaced as **a fourth and last wizard step**
("Corner Blend") with its own toolbar button. Corner-completeness is *not* an
error and is *not* part of any "done" state, and the stage carries no continuity
language in the UI (Q3).

## Feed: the ring strips

The **shipped** construction is fed by the **four ring strips, in cyclic order**
— the `Strips` link list `CornerBlend` already holds. (The `rolling` construction,
which is the default since #119, is fed by the same ring and adds the leader
cuts: the quad is built over the four members, one of them the triangular
member's net, and the triangular patch stands beside it — see
`0006-rolled-corner-is-two-patches.md`.) This is not a matter of taste: upstream's
corner primitive takes blend grids as its input, and the original demos pair
them **consecutively** (`SubGrid_i` uses grids `i` and `i+1`, cyclically), which
is exactly what a cyclic `Strips` list gives us. Feeding boundary rows instead —
what the workbench did until now — throws away the data the corner needs.

## Mechanism: Silk's subgrid chain, not a boundary-row fit

The Silk corner fill is a three-step chain, written by edwardvmills and used by
the original demos (`Resources/Demo_files/Silk_Demo_01.FCStd`):

```
SubGrid33_2Grid64 ×4  →  ControlGrid66_4Sub  →  CubicSurface_66
```

- `SubGrid33_2Grid64` (`ArachNURBS.py:7826`) takes **two 24-pole grids**
  (each stored 4 rows × 6 poles, flat `V*6 + U`, corners at `{0, 5, 18, 23}`)
  meeting at a corner and builds a 3x3 corner partial grid by reading *two*
  rows/columns of each — the shared boundary row **and the row behind it** —
  extrapolating both into the gap and averaging them. That is where tangent
  information enters, and it is also where the construction stops: no
  curvature row is ever read, which is why it reaches G1 and not G2.
- `ControlGrid66_4Sub` (`ArachNURBS.py:8077`) is pure assembly of four such 3x3
  grids into the 6x6.
- Upstream tooltip: *"Fills four sided holes between blends (only four sided
  holes). Fairly high quality final surface ... smooth transitions across the
  four original faces."*

`ControlGrid66_4` (`ArachNURBS.py:4684`) is **not** this primitive. It is
documented as "made from 4 CubicControlPoly6" — four boundary *curves* — and
fills its interior by difference propagation. A corner fed that way is C0 by
construction, which is what this workbench's own `CornerBlend` did until now.
That defect is ours, not Silk's.

## Continuity: measured, never asserted

Upstream's intent is G1+ ("smooth transitions", "good continuity"), and the same
tooltip ranks the other family — the star/N-star tools for 3-, 5-, 6-, 7-sided
holes — as *"lower quality results"*. But the author never demonstrated even G1
in the corner subgrid: `ArachNURBS.py:7969` asks *"the $10 question here is
whether this even maintains G1? maybe ... it has been many steps since the bezier
surface was segmented."*

Therefore **no continuity is claimed for the corner stage** — in code, docs or
UI — until it is measured, and the soundness of the measurement is itself a
deliverable (#97). The N-star stays parked (#92): it measured C0 on the
raw-patch junction and is upstream's lower-quality N-sided path. FreeCAD's
`Surface::Filling` is **deferred, not rejected** — see "Reversal, and its
narrowing" below. The per-hole *opt-in* decision (Q7=c) stands withdrawn as a
feature, but the fill path stays in the tree and #96 is reopened.

## Gate

The corner rebuild joins the standing acceptance chain (`Tests/test_chain.py`),
folded into the corner stage ticket (#29 → #91).

## Measurement update (#97)

With the calibrated instrument (`Tests/continuity_calibration.py`; see the
finding in `docs/research/silk-corner-continuity-measurement.md`), the existing
Silk corner (`Silk_Demo_01`, four `ControlGrid66_4Sub` junctions) is **C0-exact**
(boundary gap <= 5.2e-13 mm) and **tangent-plane continuous to <= 0.48 deg**
against its neighbouring `CubicSurface_64` blends, but is **not G2**: the
across-seam normal-curvature gap reaches 3.1e-2 /mm against a 5e-5 tolerance
(geodesic-torsion gaps to 4.1e-2 /mm; fifteen of sixteen seams fail, one is
exactly zero).

So upstream's "smooth transitions across the four original faces" is **G1**, not
G2 -- and the port in #91 reproduces that bar. The workbench's own `CornerBlend`
before the port measures **C0** with a normal gap up to 2.1 deg: the same object,
an order of magnitude worse. **The stage's target is therefore the reference bar
(G1, <= 0.5 deg), not a G2 claim.**

## Measurement update (#100)

#100 measured what G2 would take (`docs/research/silk-corner-g2.md`), and the
result is that **the G1 wall is the construction, not the maths.** The shipped
`SubGrid33_2Grid64`/`corner_grid` reads two rows of each neighbour (position and
tangent) and averages two extrapolations; matching a corner's rows 0, 1, 2 to
its neighbours' is linear algebra on the control net. On a **synthetic junction
of compatible neighbours** -- one known smooth surface, whose exact G2
continuation is known by construction -- a control-net solve recovers that
continuation exactly (`k_gap` 6.0e-17, `|solved - T|` 2.3e-13 mm), while the
shipped averaging stops at `k_gap` 4.1e-4. On the **demo's real junctions** the
same solve reaches only `k_gap` 7.1e-3 /mm (from 3.1e-2), because the four
legacy blends' second-order data does not agree at the junction: the real-data
limit is **neighbour incompatibility**, and the neighbours' own continuity knobs
(`ControlGrid64_2Grid44.scale_tangent_*` / `scale_inner_*` / `autoG3`) are the
lever (#102). Silk's **edge blend** is the strong link -- G1-exact, `k_gap` <=
2.5e-4 /mm, ~120x below the corner's. FreeCAD's `Surface::Filling` at
`BoundaryOrder = 2` is **not** G2 here and measures *worse* than `= 1`
(`k_gap` 1.665e-1 vs 8.249e-2; `g1` 1.10 deg vs 0.155 deg), so Q7's "order-2
build" opt-in must not be read as a G2 claim. The stage target stays G1
(<= 0.5 deg); a G2 target is now supported by measurement only up to the
neighbours' compatibility.

**Instrument correction (#100), resolved by #101.** #97's `twist_gap` figures
were orientation-suspect and are not evidence: the metric took its along
tangent from each surface's natural parameter axis and lost the normal side in
alignment, so a *reversed* seam correspondence (and, as #101 found, any pair
whose natural normals oppose) read ~2|tau| on a smooth seam -- a seam with
`k_gap` 2.1e-6 read `twist_gap` 5.3e-3 in #100's raw edge-blend data, and a
smooth hyperbolic-paraboloid seam carrying 1 /mm of torsion read 2.000e+00
both ways. #101 measures it in a common frame (along = the caller's
correspondence direction, normals on one side) and pins that with a
known-answer calibration, so `twist_gap` is quotable on reversed seams too.
The G2 verdict here rests on `k_gap` alone and stands, unaffected throughout.

## Baseline

Continuity is judged against `Resources/Demo_files/Silk_Demo_01.FCStd` — the
author's own best-quality corner, four `ControlGrid66_4Sub` junctions, covering
both the four-surface corner and the three-surface hard corner
(`ControlGrid64_3_Grid44`) — recreated from its sketches by our pipeline, so the
same model can be measured (#97), automated, and clicked through in the wizard.

Resolved in corner-blending design (map #1): feed = the ring strips (Q1);
stage = fourth and last wizard step, no continuity language in the UI (Q3);
mechanism = the subgrid chain, with FreeCAD `Surface::Filling` **deferred** as an
interactive aid and a possible automated fill later (#96 reopened, #99 closed);
continuity = measured (#97), not asserted; N-star parked (#92); chain gate
folded into the build (#29).

## Reversal, and its narrowing (2026-10-17)

Q7=c kept `Surface::Filling` as a per-hole opt-in and opened #96 (a reusable
fill component) and #99 (the hole-selection UX). The owner first said *"i want
to remove the freecad surface tool integration from the tool"* — and an hour
later narrowed it: *"i want the surface fill setup to still work, but doing so
manually for now to judge the performance of that (lets say i want to fill then
entire corner with one patch). … using the surface tool in an automated way for
the 3 + 4 sided patch corner fill may still be needed, later, so dont purge
everything related to the surface tool in the silk workflow wizard yet."*

**So: deferred, not rejected.**

* **#96** is **reopened** and reframed — its first job is now *interactive
  usability*, not automation: make the corner's boundary fillable **now** so the
  owner can judge a one-patch corner by eye. If FreeCAD's Surface-workbench
  picking cannot be made to work on our objects, Silk assembles the
  `Surface::Filling` for a selection the user makes in Silk instead. The owner
  still judges the surface; they just do not fight the picker.
* **#99** stays closed: there is no *hole-selection UX* to design until the fill
  is usable at all.
* The probe (`Tests/g2_corner_fill_probe.py`) stays. Nothing is purged.

**Why it is still not a default.** A fill puts a foreign `Surface::Filling`
object in the document — outside Silk's band/split machinery and outside its
restore and regression coverage — and its order-2 build is **not** G2 and
measures *worse* than order 1 (`k_gap` 1.665e-1 vs 8.249e-2 /mm, #100). The
author's own position agrees: *"FreeCAD Surface/Filling is known to flip out on
G2. I never recommend trying to achieve G2 with this. I personally use G1 as a
final surface"* (2026).

## Measurement update (#96: the picker, measured)

The reopened ticket's first job — make the corner boundary *fillable now* — was
diagnosed on current HEAD (`docs/research/silk-fill-picking.md`): the ring
strips' `Shape` is sound (1 face / 4 edges / 4 vertices, `Selectable = True`,
`EdgeN` names stable) and `Surface::Filling` accepts
`BoundaryEdges=[(B12, "Edge4"), ...]` **directly on the strips** — 1 face, valid,
boundary residual `distToShape` `0.0` mm at order 0/1/2, no throwaway carriers.
What blocks the *manual* Surface-panel path is Silk's own deliberate
`DisplayMode = "Shaded"` for blends and corners: measured with
`View3DInventorPy.getObjectInfo` (FreeCAD's 5 px pick radius, Top view), a
2601-pixel scan around a strip's junction-end edge returns `Face1` and never
`EdgeN` while Shaded, and returns `EdgeN` (72 hits) on the same pixels at
`Flat Lines` — with the same-type control `Patch44/Edge4` (Flat Lines) reading
427 hits. The Surface panel's gate (`ShapeSelection::allow` in `SurfaceGui.so`)
accepts `Part::Feature`-derived objects with an `Edge*` subname, and the panel
records `(Blend, "EdgeN")` correctly, so nothing rejects Silk objects: the
picker simply has nothing to hit. **#96 therefore fixes the display mode** --
blends and corners are created `Flat Lines`, so their boundary edges are
drawn and selectable -- **and ships the Silk-side assembly path as well**
(select the ring strips in Silk, Silk builds the `Surface::Filling`), which is
the exact path and the checkable one.

**Consequence to keep in view.** Silk's corner ships the degenerate triangular
member that upstream calls *"not intended to produce a final surface … a
stepping stone"*, and that member's face **is** the triangular patch's face: a
`CubicSurface_64` by default (the construction the maintainer's files store) or
the FreeCAD fill as the option (`member_face="fill"`). The fill path therefore
shipped rather than stayed deferred, and the triangular patch is a surface of
the corner in its own right — `0006-rolled-corner-is-two-patches.md`.

## Measurement update (#96: the fill component, tested)

The interactive path is not the only half of #96 that shipped. The wiring is
now **one ops-level component with two collectors**, in `SilkWorkflowOps`:

* `corner_fill_boundary(strips)` — the corner's collector (the ring strips →
  the junction rows, `SilkCorner.corner_inputs`'s own ring contract).
* `create_fill(links, faces=None, order=1)` — an **explicit hole boundary**,
  `[(object, "EdgeN"), ...]` plus one support face per edge, in any order.
* `create_corner_fill(*strips, order=1)` — the command's entry (ring strips),
  unchanged for callers.

Both entry points share one build-and-validate tail (`_build_fill`): the
boundary loop is ordered **by connectivity, never click order**
(`fill_boundary_loop` reuses `SilkMachinery.loop_order`, so the #66/#68
"a loop corner meets exactly 2" proof and its named refusal are Silk's own,
not a second implementation), the order is checked against FreeCAD's 0/1/2
before anything is constructed, and the build is validated by the **C0
boundary residual** (`corner_fill_problem`, `distToShape` <= 1e-3 mm) — an
invalid or boundary-missing fill is removed again rather than parked in the
tree reading `State=Up-to-date` (#80/#83).

Pinned in `Tests/test_corner_fill.py` (`run_all.py corner_fill`, 7/7):

* the ring path still builds one valid face with residual 0.0 mm, one order
  per edge, one undo step, and refuses a non-ring selection by name;
* two scrambled explicit boundaries build the **same cyclic wire** (a
  rotation/reversal of each other) — the wiring is the geometry's, not the
  click order's;
* an open chain and an over-constrained boundary (the ring plus a surplus
  edge) are refused **by name** with nothing left in the tree;
* a **general hole** — one Patch's own four boundary edges, supported by the
  patch's own `Face1` — fills to one valid face, residual 0.0 mm. That is
  the probe's "single-patch rectangular-hole control", and it is what makes
  the component general rather than corner-shaped.

The automated 3-sided + 4-sided corner fill remains **not built** (#96's ask
item 2 is later, by the ticket's own text) and the foreign-object caveat above
is unchanged: the fill is opt-in and outside Silk's band/split machinery.
