# A rolled corner is TWO patches, and "looks right" is not the acceptance

A **rolled corner** — the maintainer's `Silk_CopyPasta_28` / `_29` structure — is
**two surfaces meeting along the rolling leader**:

- the **quad**: a `ControlGrid66_4Sub` → `CubicSurface_66`, built from the four
  subgrids between **consecutive ring members**, with the triangular member
  **one of those four** (so its interior is the *ring hole*, not the corner);
- the **tri**: the member's **own surface** (a `CubicSurface_64` over the member
  grid, or a FreeCAD fill over the member's three real boundary curves), sitting
  **beside** the quad and sharing the leader boundary.

Measured on the maintainer's own files: each member is read by **three**
consumers — its own `CubicSurface_64` (the tri) **and two** `SubGrid33_2Grid64`
(which feed the quad). That is the structural signature of the two-patch
corner, and it is what a single 66 cannot produce.

## Why this is recorded

The term **"rolling corner" was used for three different things** in this
project, and each one was built:

| intended | what got built |
|---|---|
| the **two-patch** arrangement above | a corner whose *curvature* responds to asymmetric setbacks (#118) |
| the **tri** = the member's own surface | a fill laid *over* the member's region, inside the quad |
| the **leader** = an independent cut | the leader written into the band edge, so setback and leader were one number |

Three builds died on the ambiguity, each ending in "this is not a rolling
corner". The cost was days.

## The acceptance, and why prose cannot be it

**A rolled corner is not a look, it is a construction.** The acceptance is a
**construction diff against the reference files** (`Silk_CopyPasta_28`/`_29`):
same objects, same classes, same inputs, same `u` values, down to the leaves.
"Looks right" is not a test, and neither is my reading of a render — that
reading produced the #118 over-claim ("it rolls") that the owner had to correct.

**Useful reference numbers** (file 27, measured from its stored `.brp`): the tri
interior sits **8.0–31.0 mm** from the quad, **16–62 %** of a 50 mm corner
extent. A single patch wrapping the corner measures **0.1–10 %**. A bounding-box
test **cannot** separate the two — upstream's own boxes overlap — so the
**interior-distance ratio** is the separating instrument.

## Consequences

- The shipped 3-valent corner (one 66 with the member inside it) is **not** a
  rolled corner, whatever its curvature numbers say. It stays as the **fallback**
  (`construction="shipped"`).
- The rolling construction may not be declared done while its quad wraps the
  corner, however good its `k_gap` looks.
- Anything that needs a **second cut per axis end** to reproduce the reference
  (the leader independent of the setback) is part of this decision, not a
  detail to be improvised per build.
