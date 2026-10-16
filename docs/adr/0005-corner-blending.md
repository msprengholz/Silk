# Corner blending is its own stage; its continuity is measured, not asserted

Corner blending is its own stage, distinct from edge-to-edge blending: the
blending step splits into **edge blending** (on seams) and **corner blending**
(where several patches meet), surfaced as **a fourth and last wizard step**
("Corner Blend") with its own toolbar button. Corner-completeness is *not* an
error and is *not* part of any "done" state, and the stage carries no continuity
language in the UI (Q3).

## Feed: the ring strips

The corner is fed by the **four ring strips, in cyclic order** — the `Strips`
link list `CornerBlend` already holds. This is not a matter of taste: upstream's
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
`Surface::Filling` is kept as the **opt-in** route, for arbitrary holes and for
users who want an order-2 build (#96) — geometry first, selection UX later.

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
(G1, <= 0.5 deg), not a G2 claim.** A G2 target is not supported by measurement
for either mechanism: the FreeCAD order-2 fill's G2-ness is itself unmeasured,
because the Phase B probe read normal gaps only. Any future G2 claim has to be
read off `k_gap` / `twist_gap`.

## Baseline

Continuity is judged against `Resources/Demo_files/Silk_Demo_01.FCStd` — the
author's own best-quality corner, four `ControlGrid66_4Sub` junctions, covering
both the four-surface corner and the three-surface hard corner
(`ControlGrid64_3_Grid44`) — recreated from its sketches by our pipeline, so the
same model can be measured (#97), automated, and clicked through in the wizard.

Resolved in corner-blending design (map #1): feed = the ring strips (Q1);
stage = fourth and last wizard step, no continuity language in the UI (Q3);
mechanism = the subgrid chain by default with FreeCAD `Surface::Filling` as a
per-hole opt-in (Q7=c); continuity = measured (#97), not asserted; N-star parked
(#92); chain gate folded into the build (#29).
