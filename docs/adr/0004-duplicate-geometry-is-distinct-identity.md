# Coincident geometry is never identity; a copy is a distinct Edge

A translated or duplicated copy of an Edge — same poles, different placement —
is a distinct document object with its own identity, and is legitimately a
different patch's boundary. There is no "copy" marker, no special handling,
and no geometric matching that would treat near-identical edges as equivalent.
This is the #44 rule restated for the mirror/duplicate workflow: coincident
geometry is never identity, so "two edges overlap" is never a defect.

The alternative — flagging copies, or resolving adjacency geometrically —
would contradict the one robust adjacency rule Silk has (identity-based shared
edges) and would make a translated copy unusable, which is exactly the
legitimate workflow the human hit in round 1. The only real confusion is
visual: a copy looks like the original in the tree. That is addressed by #52
(group distinct Edge objects' own sketches under them) and #54 (distinct
per-kind icons), not by a copy marker. Resolved in #55 Q3.
