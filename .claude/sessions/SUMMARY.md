# Session handoff — viz-site

Updated: 2026-09-28
Log folder: .claude/sessions/logs/ — detailed per-session logs. Read only when a specific question isn't answered here.
Latest log: .claude/sessions/logs/2026-09-24-plans-2-and-3a-built-and-merged.md

## Current objective

Write Plan 3b (the `publish-viz` skill plus the Vega-Lite authoring guide) with `superpowers:writing-plans`, carrying the "Plan 3b must carry" list from the 2026-09-24 log. The bake-off is DECIDED: Vega-Lite won (2026-09-28). Plotly and ECharts are fully removed and merged into `main` (46129e7, `--no-ff` of branch `vega-lite-only`); `main` is not pushed. Suite state on `main`: pytest 282 passed, 2 skipped; `web/` vitest 129, typecheck clean, build ok, Playwright smoke 3/3.

The decision, reasons and fallback paths for chart families Vega-Lite lacks (site-owned tiles like `stat`; full Vega specs, already bundled; restoring a renderer from git) are recorded in `docs/superpowers/specs/2026-09-22-bake-off-scorecard.md`. A layout bug found this session (vega-embed's injected `.vega-embed{position:relative}` collapsed tiles to 21px) is fixed in b890ec3 and guarded by the smoke test. User-facing pages from this session: renderer comparison https://claude.ai/artifact/1v6MKjyf852LYCRFpz1n6V and network-graph/gauge examples https://claude.ai/artifact/6wswkytAsnwangRCm1Chw5. The user liked the network graph and gauge; consider them for a later tile-type or full-Vega plan.

Known cosmetic issue for the hardening pass: at phone width the dashboard grid stays 12 columns, so tiles are cramped and the stat value clips. Discord: the user's screenshots channel is the baseball_wiggum `user` webhook (`baseball_wiggum/wiggum/discord/config.json`).

Next concrete steps, in order: (1) Plan 3b; (2) the hardening pass the user wanted, seeded with the parked items in the 2026-09-24 log plus the phone-width grid; (3) Plan 4 (Dockerfile, Helm, CI) with its carry-forwards.

Decisions already made, do not relitigate: Vega-Lite is the only chart renderer; everything in the 2026-09-24 log's rulings, including the spec 12.3 amendments, the staging layout and author-resolution order for the CLI, and that `main` is only pushed when the user says so.

## Last session summary

Wrote Plans 2 and 3a with forked plan writers, then executed both in parallel git worktrees with subagent-driven development (fresh implementer per task, review per task, fix rounds, whole-branch final reviews on the strongest model, one fix wave each). Plan 3a landed the full paved path (`viz stage/validate/publish/move/preview/query`) and was merged first; Plan 2 landed the React front end with three sanitized renderer adapters, a locked-down DuckDB-WASM large lane, the bake-off samples, a passing Playwright smoke test and the scorecard. The first real smoke run exposed two genuine defects (missing parquet extension in duckdb-wasm; Arrow builders needing code evaluation under the CSP), both fixed and now guarded by tests. Nothing is broken. A leftover `.worktrees/plan-2-front-end` directory may remain if Windows kept build binaries locked; it is git-ignored and safe to delete.

## Recent sessions

- 2026-09-24 plans-2-and-3a-built-and-merged — CLI and front end built, reviewed and merged; bake-off dashboards viewable (logs/2026-09-24-plans-2-and-3a-built-and-merged.md)
- 2026-09-22 plan-1-design-and-build — designed viz-site, security review, Plan 1 built, reviewed and merged (logs/2026-09-22-plan-1-design-and-build.md)
