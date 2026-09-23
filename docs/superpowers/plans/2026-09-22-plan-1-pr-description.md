# Plan 1: contract, storage and server

Implements Plan 1 of the viz-site design (`docs/superpowers/specs/2026-09-22-viz-site-design.md`): the bucket contract, a storage layer with local and S3 backends, and a hardened read-only FastAPI server over a sample bucket.

## What's in this branch

- **Contract:** JSON Schemas for charts, dashboards and folders (`schemas/`) plus renderer-specific spec checks in `viz/schemas.py`. Specs cannot embed data, load URLs, carry HTML formatters, or use geo/map traces. 60 valid and invalid test cases.
- **Storage:** one `Storage` protocol, `LocalStorage` and `S3Storage` backends, the same test suite run against both (S3 via moto). Path confinement on the local backend, including symlink escapes.
- **Settings:** `VIZ_*` environment variables. No Databricks credentials anywhere in the server.
- **Sample bucket:** deterministic synthetic generator, enforced synthetic-only by tests.
- **Server:** exact Content Security Policy and four other security headers on every response including rejected hosts and crashes; identity slot with access logging; trusted hosts; no CORS; document loading with a 1 MB cap and schema validation; folder tree with single-flight cache, stale-while-revalidate, id-conflict detection and graceful error nodes; `GET /api/tree`, `/api/dashboards/{id}`, `/api/charts/{id}` (SQL stripped unless `show_sql`), `/api/data/{id}` streaming with ETag, Range and HEAD; SPA serving via a 404 exception handler; `viz-server` entry point.

## Design changes made during execution (recorded in the plan)

- Security headers middleware is outermost and converts unhandled exceptions to a JSON 500 that still carries the headers.
- SPA fallback is an exception handler, not a catch-all route, so routes registered later still resolve.
- `FolderNode` carries an always-present `error` key so a malformed `_folder.json` degrades instead of failing the tree.
- Data route is `/api/data/{id}` (ids may end in `/data`).

## Verification

- `169 passed, 1 skipped` (Windows-only symlink test), warning-free, on the exact tree at the branch tip.
- Twelve task-scoped reviews, one whole-branch review, one fix wave, one scoped re-review. All clean.
- Smoke run: `viz-server` serves the sample bucket on `127.0.0.1:8000`.

## Follow-ups (not in this PR)

Plan 2: front end and renderer bake-off. Plan 3: `viz` CLI and publish skill. Plan 4: refresher scaffold, Dockerfile, Helm, CI with the synthetic-bucket check and gitleaks. Carry-forward minors are listed in `.claude/sessions/SUMMARY.md`.

🤖 Generated with [Claude Code](https://claude.com/claude-code)

https://claude.ai/code/session_014JyBpbUMQyfxRP89X12AES
