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

---

## The process, as the owner states it (2026-10-22, confirmed step by step)

This supersedes any earlier description in this repo of "how we build it". Our
implementation diverged from it at step 3, and that divergence is the reason
our quad covers the triangular patch instead of sitting beside it.

1. **Start:** three patches meet at a corner; three edge blends lie along the
   three seams.
2. **Choose the corner** where the triangular patch goes -- equivalently, the
   **two patches adjacent to it**. (It is *not* a choice of "which patch
   carries the member grid"; that was our invention.)
3. **Divide TWO of the three patches** at the leader. Two of the three blends
   are therefore cut back, and each divided patch yields a **small piece
   toward the corner** and a **large remainder**.
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

**The measurement that distinguishes a correct corner from a wrong one:** the
triangular patch's interior must lie **away** from the quad -- measured on the
maintainer's own file, its interior samples sit **4.6-35.5 mm** from the quad,
**16-62 %** of the corner's extent. A corner assembled "around" a member grid
instead measures **~1 mm** (0.5-2.6 %): the quad and the tri then describe the
same area and two objects are drawn where one surface belongs.
