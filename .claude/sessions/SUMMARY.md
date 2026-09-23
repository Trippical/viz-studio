# Session handoff — viz-site

Updated: 2026-09-22
Log folder: .claude/sessions/logs/ — detailed per-session logs. Read only when a specific question isn't answered here.
Latest log: .claude/sessions/logs/2026-09-22-plan-1-design-and-build.md

## Current objective

Build the paved path and get bake-off results, in parallel. The user (2026-09-22, second session) chose to skip the hardening pass for now and run two plans side by side in separate worktrees:

- Plan 2, front end and bake-off: `docs/superpowers/plans/2026-09-22-plan-2-front-end-bake-off.md` (Vite + React + TS in `web/`, three sanitized renderer adapters, controls with URL state, DuckDB-WASM large lane, bake-off samples in `sample-bucket/`, Playwright smoke test, scorecard doc `docs/superpowers/specs/2026-09-22-bake-off-scorecard.md`).
- Plan 3a, the `viz` CLI: `docs/superpowers/plans/2026-09-22-plan-3a-cli.md` (`viz/publish/`: query, stage, validate, publish, move, preview; argparse only; adds `pyarrow`, `duckdb`, optional `databricks` extra). The `publish-viz` skill (spec 6.3) is Plan 3b and waits for the bake-off winner.

State: both plans are committed on `main` and executing with `superpowers:subagent-driven-development` in git worktrees `.worktrees/plan-2-front-end` (branch `plan-2-front-end`, 17 tasks) and `.worktrees/plan-3a-cli` (branch `plan-3a-cli`, 12 tasks), each with its own `.venv`. Progress ledgers with every ruling: `<worktree>/.superpowers/sdd/<plan-basename>/progress.md` (git-ignored). If a session dies mid-plan, read the ledger and `git log` on the branch, then resume at the first task without a `complete` line. Node.js 24.19.0 was installed with winget at `C:\Program Files\nodejs` (new shells need it on PATH; in Git Bash `export PATH="/c/Program Files/nodejs:$PATH"`).

Decisions already made, do not relitigate: everything in the previous objective (spec, `/api/data/{id}`, 404-handler SPA fallback, SecurityHeaders outermost, size+mtime local ETag, commit trailers); staging root `.viz-staging/` mirrors the bucket with an empty root prefix (`.viz-staging/charts/<id>/`), so `viz preview` serves it with `root_prefix=""`; author resolution order is Databricks current user, then `VIZ_AUTHOR`, then AWS STS caller identity when storage is s3, then `<user>@local`; CLI exit codes 0/1/2; Plan 2 adds `pyarrow` to the dev extra for the parquet sample and Plan 3a adds it to main deps, so `pyproject.toml` conflicts at merge and is resolved by hand.

Next concrete step: when both plan files exist, review them, commit them, create worktrees with `superpowers:using-git-worktrees` (branches `plan-2-front-end` and `plan-3a-cli`), and execute both with `superpowers:subagent-driven-development`. After Plan 2 lands, the user reviews the three bake-off dashboards and picks a winner; then Plan 3b (skill) and the loser removal.

## Last session summary

Designed viz-site with the user from an empty folder and wrote the spec, a three-lens security review, and Plan 1. Executed Plan 1's twelve TDD tasks with subagent-driven development, fixing findings per task and in one final wave. Set up `CLAUDE.md`, the 3.11 venv, and the commit conventions so smaller models can work in the repo. Added the GitHub remote, pushed, and merged Plan 1 into `main` at the user's request. Nothing is broken; suite is 169 passed, 1 Windows skip. `gh` CLI is not installed; PRs go through the web UI.

## Recent sessions

- 2026-09-22 plan-1-design-and-build — designed viz-site, security review, Plan 1 built, reviewed and merged (logs/2026-09-22-plan-1-design-and-build.md)
