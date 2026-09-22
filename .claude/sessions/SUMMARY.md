# Session handoff

## Current objective

Build viz-site: an open-source, self-hosted visualization site that is a viewer over an S3 folder, fed by a Claude skill plus a Python CLI. Replaces Databricks built-in dashboards for the user's team. Developed on the user's personal AWS account, then connected on their work machine inside a VPN-gated VPC on a small k8s cluster.

## Last session summary (2026-09-22)

Brainstormed the full design with the user and wrote the spec to `docs/superpowers/specs/2026-09-22-viz-site-design.md`. Repo was empty at start; git was initialized this session.

Key decisions (all confirmed by the user):
- One Python package (`viz`: storage, server, publish, refresh) plus a Vite/React/TS front end, one container image. Viewer and refresher are the same app; refresher is a scaffold in v1, off by default.
- Contract: charts are reusable atoms under `charts/<id>/chart.json` plus a data file; dashboards under `dashboards/<id>.json` reference charts by id. Ids are slash paths, so folders are bucket prefixes. Optional `_folder.json` per folder. Folders are v1.
- Two data lanes: small (JSON, <=100k rows/20MB) and large (parquet <=200MB, DuckDB-WASM in browser with a per-chart `aggregate` SQL). Site never runs SQL against Databricks.
- Viewer-side controls (date-range, select, number-range) bind by column name and filter client-side.
- Chart renderer bake-off: Vega-Lite, Plotly, ECharts built side by side with identical samples; user picks one, losers deleted.
- Publisher: `viz` CLI (query, stage, validate, publish, move, preview) plus `skills/publish-viz/SKILL.md`, usable from Databricks Genie Code and local Claude Code. Two publish modes: refreshable (has `source` SQL) and one-off (no source, shows "static" badge).
- No app auth in v1 (VPN is the gate). Server is read-only, four GET routes, strict id validation.
- MIT license, GitHub Actions CI, Helm chart.
- Spec section 11 reserves seams for later optional modules (MCP server, in-portal chat, real auth for an external portal), all off by default and never touching the publish path.
- Three parallel security reviewers assessed the user's claim "no security concern, same as Databricks". Verdict: not true as stated, but closable with defaults. Merged findings in `docs/superpowers/specs/2026-09-22-security-review.md`; the v1 requirements are now spec section 12 (CSP, sanitized markdown, per-renderer deny-lists, locked-down DuckDB, parameterized control filters, CLI guardrails, IAM policies, Helm hardening, refresher as a separate process with no Databricks creds in v1). Contract edits: `data.path` removed, column-name regex, `source` is closed with advisory `warehouse_id` and opt-in `show_sql`.
- Renderer attack surface is a bake-off criterion: ECharts smallest once locked down, Vega-Lite close second, Plotly largest.

- Plan 1 written: `docs/superpowers/plans/2026-09-22-plan-1-contract-storage-server.md` (12 TDD tasks: scaffold, ids, schemas, local + S3 storage, settings, sample bucket, app + middleware, documents + tree cache, routes, streaming data route, SPA + entry point). Plans 2 (front end + bake-off), 3 (CLI + skill), 4 (refresher scaffold, Docker, Helm, CI, IAM files) are written after their predecessors ship. Data route amended to `GET /api/data/{id}` in the spec.

- User chose subagent-driven execution and asked that everything be future-proofed for smaller models: `CLAUDE.md` now carries commands, commit recipe, and Windows gotchas; the plan has an execution-notes section. Memory saved under the project memory dir.
- Execution is in progress on branch `plan-1-contract-storage-server` (in place, no worktree). Ledger with all rulings: `.superpowers/sdd/2026-09-22-plan-1-contract-storage-server/progress.md` (git-ignored). Tasks 1-6 complete and reviewed; Task 7 (sample bucket) implemented and under review.
- Environment: venv at `.venv/` is Python 3.11 (system default is 3.10, do not use). Commit trailers name the model that made the commit.

## Next concrete step

Continue `superpowers:subagent-driven-development` for Plan 1 from the ledger: resume at the first task without a `complete` line. After Task 12 and the final whole-branch review, use `superpowers:finishing-a-development-branch`, then write Plan 2 (front end, three renderer adapters, bake-off samples, DuckDB large lane) against the real server.
