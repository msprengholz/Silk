# Corner filling is a separate blending stage; G2 by default

Corner filling is its own stage, distinct from edge-to-edge blending (Q3): the
blending step splits into **edge blending** (on seams) and **corner filling**
(on points / where several patches meet), surfaced as **two separate taskbar
buttons** in the UI, not as extra wizard stages. This keeps two operations of
clearly different complexity apart. A corner that is not fully blended is *not*
an error and must not block any "done" condition — full blending is not always
the user's goal, so corner-completeness is deliberately excluded from the
(hidden, #73) `complete` state (Q3).

**Feed** (Q1): the corner is fed **directly from the constituent patches'
subgrid cells** (the 4-patch junction), not from the blend strips. This is the
`b` choice: the corner is derived from the same subgrid cells every other
object reads, so it stays true to the patches rather than depending on whether
strips exist.

**Continuity bar** (Q5): **G2 is the default target** for the corner stage; the
user may lower continuity afterward. Three candidate fills, in priority order:

1. **N-star corner** (`ControlGridNStar66_NSub` + `CubicNStarSurface_NStar66`):
   the Silk-native corner edwardvmills designed as a "star of blend surfaces"
   that carries the blend's curvature into the junction centre — the only
   Silk-built candidate that *intends* G2 across the boundary. Its continuity
   is **unverified** (no oracle exists; the creator himself called it "a
   gamble"), it crashes on a degenerate centre, and it is not yet wired into
   the workflow. Therefore it is **viability-gated** (Q9): it ships only if a
   new G2 oracle confirms it into a real 4-patch subgrid junction and it is
   made stable + degenerate-guarded. If not shipped, it stays its own tracked
   ticket (Q6).
2. **FreeCAD's built-in surface tool**: the **G2 default path** when the N-star
   is not viable. Continuity is set against the adjacent patches, defaulting to
   G2, and the resulting surface remains user-editable via FreeCAD's surface
   wizard afterward. A "fallback" in name only — it is the reliable way to get
   a real, verifiable G2 corner.
3. **`ControlGrid66_4` / `CubicSurface_66`** (the current `CornerBlend`): C0 at
   the boundary to its neighbours — its "G2 throughout" tooltip is internal
   to the single surface, not continuity to the surrounding patches (confirmed
   by construction: it reads four position rows, no derivative input). It is
   kept only as the explicit **low-continuity Silk-native** fallback.

**Gate** (Q7): once the corner stage ships, the corner rebuild joins the
standing acceptance chain (`Tests/test_chain.py`) — ticket #29.

Resolved in corner-blending design (map #1): Q1=b, Q3 (split stage, two
buttons, no done gate), Q5 (G2 default; N-star viability-gated, FreeCAD surface
tool as the G2 path, `66_4` as C0 fallback), Q6 (N-star separate ticket if not
shipped), Q7 (chain gate), Q9 (build N-star, keep FreeCAD fallback).
