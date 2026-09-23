# 2026-09-22 — viz-site: design, security review, Plan 1 built and merged

## Goal

Start the viz-site project from an empty folder: design it with the user, write the spec, plan and execute the first implementation slice, and get it onto GitHub.

## What happened

### Design (brainstorming, architectural path)
- User wants an open-source viewer over an S3 folder, fed by an agentic skill (Databricks Genie Code and local Claude Code) plus Python helpers, replacing Databricks dashboards. Hosted inside a VPN-gated VPC on a small k8s cluster. Viewer and refresher are the same app. Chart bake-off (Vega-Lite, Plotly, ECharts) instead of picking a library up front. Folders are v1. Viewer-side controls filter static data; no SQL runs against Databricks from the site.
- Spec: `docs/superpowers/specs/2026-09-22-viz-site-design.md`. Small lane cap doubled to 100k rows / 20 MB at the user's request. Section 11 added: seams for later optional modules (MCP server that knows all dashboards and controls, in-portal chat, real auth for an external portal), all off by default, never touching the publish path. Data route amended to `/api/data/{id}` because ids may end in `/data`.
- Security: three parallel reviewers (data exposure, injection/browser, publish path/infra) assessed the user's claim "same as Databricks, no concern". Verdict: not true as stated (VPN population is not the Databricks-grant population; the refresher is a stored-SQL-execution primitive; the large lane ships raw rows; hostile bucket content runs in every VPN browser), but closable with defaults. Merged findings: `docs/superpowers/specs/2026-09-22-security-review.md`. Spec section 12 now holds the v1 requirements. User asked "nightmare or manageable?" — manageable; mostly one-time defaults.
- User asked to future-proof everything for smaller models. `CLAUDE.md` created with commands, commit recipe, rules and Windows gotchas; plan has an execution-notes section; memory saved.

### Plan 1 (contract, storage, server): `docs/superpowers/plans/2026-09-22-plan-1-contract-storage-server.md`
12 TDD tasks executed with subagent-driven development on branch `plan-1-contract-storage-server` (in place, no worktree). Implementers: haiku for transcription tasks, sonnet for integration tasks; reviewers sonnet; final whole-branch review opus. Every task reviewed; fix rounds on Tasks 1, 3, 7, 8, 9, 11; final fix wave of 9 items; scoped re-review clean.

Key rulings (full list was in the deleted SDD ledger; a copy is in the session scratchpad only):
- Commit trailers name the model that actually made the commit; recipe is two `-m` flags with a literal newline in the second (the message-file approach and the session-model rule both failed with small models).
- Vega-Lite/ECharts specs are not checked for undeclared columns (transforms create fields); Plotly bindings and stat tiles are.
- Local backend ETag stays size+mtime (hashing 200 MB per HEAD is the DoS the security review named); S3 gives real ETags.
- SecurityHeaders middleware is outermost and converts unhandled exceptions to a JSON 500 that still carries headers; Identity logs status=500 and re-raises.
- FolderNode has an always-present `error` key; a bad `_folder.json` degrades to slug display.
- SPA fallback is a 404 exception handler (a catch-all route shadowed routes added after `create_app`, discovered when a haiku worker hit the session rate limit mid-task).
- Two Starlette 1.6 test-client deprecation warnings are filtered narrowly in pyproject (one is a `UserWarning` subclass).
- Task 12's "index.html checked before requested file" finding parked: a dist without index is a broken build.

Final review Important findings, all fixed in the wave: HEAD on the data route (405 → supported, DuckDB-WASM needs it), oversized Range digits → 500, NotFound mid-tree-build, `.gitignore` `.env` → `.env*`, vacuous static traversal test, `LocalStorage.__init__` creating the root.

### Environment facts learned
- System `python` is 3.10; `.venv/` was created with `py -3.11`. Always use `.venv/Scripts/python`.
- The project-boundary guard hook blocks backticks and redirects outside the project (`/dev/null`); use the Write tool for files with backticks.
- A subagent reverted `SUMMARY.md` mid-session (likely `git restore`); CLAUDE.md rule 8 now forbids discarding others' work; handoff edits are committed promptly.
- `gh` CLI is not installed. Remote added: https://github.com/Trippical/viz-studio.

### Merge
User said "you can merge". Merged with `--no-ff` into `main` (71c4362), suite green on merged tree (169 passed, 1 Windows symlink skip, warning-free), `main` pushed, feature branch deleted locally and remotely. PR description kept at `docs/superpowers/plans/2026-09-22-plan-1-pr-description.md` for reference.

## Files created/changed (high level)
`pyproject.toml`, `CLAUDE.md`, `README.md`, `LICENSE`, `.gitattributes`, `.gitignore`, `schemas/*.schema.json`, `viz/{ids,schemas,config}.py`, `viz/storage/{base,local,s3,__init__}.py`, `viz/server/{app,middleware,documents,tree,routes,static,__main__}.py`, `sample-bucket/generate.py` + generated `sample-bucket/viz/...`, `tests/**`, `docs/superpowers/{specs,plans}/*`.

## Dead ends
- `git commit -F` message-file convention: a small model dropped the blank line after the subject. Replaced by the two `-m` recipe.
- Catch-all SPA route: shadows later-registered routes. Replaced by the exception handler.
- `skipif(win32)` for the case-insensitive invalid-id test: wrong fix; use an id invalid on every filesystem (`bad_id`).

## Open threads / parked
- Deferred minors worth picking up: `allowed_hosts` default includes `testserver`; `If-None-Match` exact equality only; data route re-validates chart.json per ranged request; TreeCache refresh test uses a 0.2s sleep; spec 4.5 wording vs mutation-based fixtures; identity header logged unbounded; `LocalStorage.copy()` not atomic; error sort key theoretical str/int mix; id regex duplicated across schema files.
- Plan 4 must add CI (suite, synthetic-bucket check, gitleaks) and a deployment note that `VIZ_ALLOWED_HOSTS` must be set.
- User wants a few sessions to "pick at" Plan 1 for strength before moving on.

## Test/run state
`.venv/Scripts/python -m pytest` → 169 passed, 1 skipped, no warnings, on `main` at 71c4362. `viz-server` serves the sample bucket on 127.0.0.1:8000.
