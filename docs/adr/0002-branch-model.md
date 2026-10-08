# Branch model

`master` is always "current upstream + accepted local work" — a clean baseline, never half-finished features.

- Development happens on **one branch per feature ticket** (e.g. `feat/gui-assisted-workflow`), merged back to `master` when done and tested.
- Upstream changes are merged into `master` directly, per ADR 0001's conflict policy.
- Contributions go out as PRs from `msprengholz/Silk` to `edwardvmills/Silk`.
- Local dev tooling (MCP test harness, `Tests/`) lives on `master`; it is additive and plausibly PR-able.

Rejected alternative: developing features directly on `master` (simpler, but `master` drifts into half-finished state and loses its value as a mergeable baseline).
