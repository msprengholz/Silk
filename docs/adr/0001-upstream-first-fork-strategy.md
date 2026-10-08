# Upstream-first fork strategy

The main goal of this repo is to keep building on `edwardvmills/Silk` master, and the long-term goal is to contribute work back upstream. The fork (`msprengholz/Silk`) must therefore stay mergeable with upstream at all times.

Consequences:

- Local history was rebased onto the real upstream commit (`e8a287f`, v0.2.2) it was originally built on, so the fork has one clean linear history with upstream.
- When merging upstream changes, conflicts in upstream-derived files (e.g. `ArachNURBS.py`, `ControlPoly4.py`) are resolved **in upstream's favor** wherever upstream's behaviour covers the same need. Local duplicates of upstream fixes are dropped, not merged alongside.
- `package.xml` keeps upstream's version number (no local bump) so the fork never claims to be a different addon version.
- New Silk objects (Patch44, Edge, BlendStrip, ...) are purely additive and written PR-shape.
