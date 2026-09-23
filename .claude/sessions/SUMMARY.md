# Session handoff — viz-site

Updated: 2026-09-22
Log folder: .claude/sessions/logs/ — detailed per-session logs. Read only when a specific question isn't answered here.
Latest log: .claude/sessions/logs/2026-09-22-plan-1-design-and-build.md

## Current objective

Harden Plan 1 before building on it. The user wants a few sessions to "pick at" the merged contract, storage and server code to make sure it is strong. Plan 1 is merged to `main` (71c4362) and pushed to https://github.com/Trippical/viz-studio; suite is 169 passed, 1 Windows skip, warning-free.

Decisions already made, do not relitigate: spec `docs/superpowers/specs/2026-09-22-viz-site-design.md` with section 12 security requirements; data route is `/api/data/{id}`; SPA fallback is a 404 exception handler; SecurityHeaders middleware outermost; local ETag is size+mtime; Vega-Lite/ECharts column names are not validated against declared columns; commit trailers name the model that made the commit (see `CLAUDE.md`).

Starting points for hardening sessions: the deferred minors in the latest log's "Open threads"; a fresh adversarial pass over `viz/server/routes.py`, `viz/server/static.py`, `viz/storage/local.py` and `viz/schemas.py`; running the server against a real S3 bucket on the user's personal AWS account (only synthetic data). After hardening: write Plan 2 (front end, three renderer adapters with the section 12.3 deny-lists, controls with URL state, DuckDB-WASM large lane) with `superpowers:writing-plans`.

## Last session summary

Designed viz-site with the user from an empty folder and wrote the spec, a three-lens security review, and Plan 1. Executed Plan 1's twelve TDD tasks with subagent-driven development (small models for transcription, mid-tier for integration, most capable for the final review), fixing findings per task and in one final wave. Set up `CLAUDE.md`, the 3.11 venv, and the commit conventions so smaller models can work in the repo. Added the GitHub remote, pushed, and merged Plan 1 into `main` at the user's request. Nothing is broken. `gh` CLI is not installed; PRs go through the web UI.

## Recent sessions

- 2026-09-22 plan-1-design-and-build — designed viz-site, security review, Plan 1 built, reviewed and merged (logs/2026-09-22-plan-1-design-and-build.md)
