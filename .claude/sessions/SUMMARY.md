# Session handoff — viz-site

Updated: 2026-09-24
Log folder: .claude/sessions/logs/ — detailed per-session logs. Read only when a specific question isn't answered here.
Latest log: .claude/sessions/logs/2026-09-24-plans-2-and-3a-built-and-merged.md

## Current objective

The renderer bake-off decision, which only the user can make. Plans 2 (front end + bake-off) and 3a (the `viz` CLI) are DONE and merged into `main` (85205e9 and b13a249, `--no-ff`); `main` is not pushed. Suite state on `main`: pytest 295 passed, 2 skipped; `web/` vitest 163, typecheck clean, build ok, Playwright smoke 5/5.

To view: from the repo root run `VIZ_WEB_DIST=web/dist .venv/Scripts/viz-server` (PowerShell: `$env:VIZ_WEB_DIST = "web/dist"` first; `web/dist` is built) and open `http://127.0.0.1:8000/d/bakeoff/vega-lite`, `/d/bakeoff/plotly`, `/d/bakeoff/echarts`. Measured numbers are in `docs/superpowers/specs/2026-09-22-bake-off-scorecard.md` (lazy chunk vega-lite 841 KiB / plotly 4,727 KiB / echarts 1,108 KiB; sanitizer rules 10/10/12; all CSP-clean); the visual-quality column is blank for the user.

Next concrete steps, in order: (1) user picks the winner and fills the scorecard; (2) remove the two losing adapters, their sanitizers, samples and `renderer` enum values (spec 5.2), then write Plan 3b (the `publish-viz` skill + the winner's authoring guide) with `superpowers:writing-plans`, carrying the "Plan 3b must carry" list from the latest log; (3) the hardening pass the user wanted, seeded with the parked items in the log; (4) Plan 4 (Dockerfile, Helm, CI) with its carry-forwards.

Decisions already made, do not relitigate: everything in the latest log's rulings, including the spec 12.3 amendments (no `enable_external_access` in the browser; self-hosted parquet extension loaded before the lockdown; prepared inserts instead of Arrow temp tables; `datasets`, `image`/`image://`, `customdata`, `<a` and top-level `data` rules mirrored in `viz/schemas.py`), the staging layout and author-resolution order for the CLI, and that `main` is only pushed when the user says so.

## Last session summary

Wrote Plans 2 and 3a with forked plan writers, then executed both in parallel git worktrees with subagent-driven development (fresh implementer per task, review per task, fix rounds, whole-branch final reviews on the strongest model, one fix wave each). Plan 3a landed the full paved path (`viz stage/validate/publish/move/preview/query`) and was merged first; Plan 2 landed the React front end with three sanitized renderer adapters, a locked-down DuckDB-WASM large lane, the bake-off samples, a passing Playwright smoke test and the scorecard. The first real smoke run exposed two genuine defects (missing parquet extension in duckdb-wasm; Arrow builders needing code evaluation under the CSP), both fixed and now guarded by tests. Nothing is broken. A leftover `.worktrees/plan-2-front-end` directory may remain if Windows kept build binaries locked; it is git-ignored and safe to delete.

## Recent sessions

- 2026-09-24 plans-2-and-3a-built-and-merged — CLI and front end built, reviewed and merged; bake-off dashboards viewable (logs/2026-09-24-plans-2-and-3a-built-and-merged.md)
- 2026-09-22 plan-1-design-and-build — designed viz-site, security review, Plan 1 built, reviewed and merged (logs/2026-09-22-plan-1-design-and-build.md)
