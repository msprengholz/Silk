# FreeCAD's surface tool as the corner G2 fill — measured (ticket #91 Phase B)

**Question.** ADR 0005 asks the corner stage to default to G2, with
FreeCAD's built-in surface tool (`Surface::Filling`, a
`BRepFill_Filling` with per-edge support faces and a continuity order) as
the G2 path, fed from the four constituent patches' subgrid cells
(Q1=b). Does that tool actually reach G2 across the 4-patch junction, and
what feed does it need?

**Answer (measured).** It cannot reach G1, let alone G2, on the Q1=b
feed: the raw patches ridge at 60–88° along their shared seams (#92), so
at every vertex of the junction hole two consecutive boundary edges are
supported by *different* patches that disagree — the fill is
over-constrained. `Surface::Filling` then returns an **invalid** face
whose surface does not even contain its own boundary. Fed the
*already-blended* boundary instead (the ring strips' inner ends), the
same tool builds a valid fill that is G1 to ≤0.16° and near-G2 to ≤0.49°
of residual normal gap. **The corner stage can only honour its G2 default
if Q1 moves from `b` (raw patches) to `a` (blended strips).**

## Method

`Tests/g2_corner_fill_probe.py` (measurement only — throwaway carriers in
a scratch document; the corner fixture is `Tests/corner_model.py`). Both
feeds are built with the identical `Surface::Filling` wiring:

```python
fill = doc.addObject("Surface::Filling", name)
fill.BoundaryEdges   = [(support_obj, ["EdgeN"]), ...]  # consecutive wire order
fill.BoundaryFaces   = ["Face1", ...]                   # one support face name per edge
fill.BoundaryOrder   = [order, ...]                     # 0=C0, 1=G1, 2=G2
```

Continuity order is read as 0 = C0, 1 = G1, 2 = G2: this FreeCAD build
(1.1.3 / OCCT 7.9) rejects ≥ 3 with `BRepFill : The continuity is not G0
G1 or G2`, and the GUI's own G2 entry maps to 2.

The seam is the same geometric curve on the fill and on the reference
surface. Because the fill's surface is a general trim, `S.parameter()`
is **not** accurate enough for boundary points (it lands up to 1.3 mm
away), so the probe solves each boundary point's (u, v) with a coarse
grid plus Newton (`solve_uv`) and reports the solve residual alongside
the normal gap.

## Measured (FreeCAD 1.1.3, OCCT 7.9, `Tests/corner_model.py` fixture)

| feed | order | valid | boundary residual | max boundary normal gap |
|------|-------|-------|-------------------|--------------------------|
| raw patches (Q1=b) | 0 (C0) | yes | ≤ 5.0e-3 mm | 45.3 – 88.6° (C0, by design) |
| raw patches (Q1=b) | 1 (G1) | **no** | 0.59 – 7.3 mm | not measurable |
| raw patches (Q1=b) | 2 (G2) | **no** | 0.75 – 3.2 mm | not measurable |
| ring strips (Q1=a) | 0 (C0) | yes | ≤ 2.3e-4 mm | 1.86 – 4.29° (C0, by design) |
| ring strips (Q1=a) | 1 (G1) | yes | ≤ 2.2e-4 mm | **0.087 – 0.155°** |
| ring strips (Q1=a) | 2 (G2) | yes | ≤ 9.0e-3 mm | **0.164 – 0.483°** |

`boundary residual` = max distance from a boundary point to the fill
surface. For a sound fill it is the parameter-solve floor; for the
over-constrained raw feed it is 0.6–7 mm — the fill does not pass through
its own boundary at all, which is why no normal gap can be read there.

## Control

A rectangular hole cut out of ONE smooth patch surface, with the four
surrounding strips as supports, reaches C0 = 0.17°, G1 = 0.009°,
G2 = 0.38° normal gap — the API, the support wiring and the measurement
all work when the four supports are mutually consistent. That is the
control the raw-patch negative is read against.

## What this means for the ticket

* The N-star was already parked (#92) as C0 on the raw-patch feed. This
  measurement says the FreeCAD surface tool is **also** C0-or-worse on
  exactly that feed — the failure is in the feed, not in either fill.
* On the blended feed the tool reaches G1 and near-G2. The residual
  ~0.2–0.5° at G2 is the fill algorithm's own approximation (tunables —
  `TolCurvature`, `Tolerance3d`, `MaximumDegree`, `Iterations` — are not
  yet swept).
* Building the corner object itself is therefore blocked on the Q1
  decision: with Q1=b the default G2 corner cannot be built by any
  candidate; the only honest default would be the C0 `ControlGrid66_4`
  fallback, and that is a product decision for the ticket owner.
