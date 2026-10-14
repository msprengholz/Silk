# Edges are freely reusable; no "consumed" state, no claims warning

An Edge may be referenced by zero, one, or two Patches; a real seam is exactly
the edge that two adjacent patches both reference, so a second reference is
the *definition* of a shared seam, not an error. Selecting an edge for a patch
therefore never marks it "consumed" and never warns, even when that edge
already belongs to another patch (only a third reference degrades — two are
the seam itself). Adjacency is identity-based only (#44): coincident but
unlinked boundaries are never adjacent.

This is a deliberate no-op, chosen over the alternatives (a "consumed" visual
state, or a warning on re-selection). Marking edges consumed would read the
shared seam — the one case that *must* allow two references — as a mistake, so
any block would have to special-case the legitimate second pick. A warning
trades that contradiction for constant noise on the normal blending path.
Resolved in #55 Q1 (decision recorded on map #1): edges stay freely reusable,
and the only affordances for telling edges apart are #52's tree grouping and
#54's per-kind icons. The human's "every edge is taken, none free" surprise
was a *failed patch holding its links* (already fixed by #66's refuse-before-
construct), not a claims model bug — see #55 Q2.
