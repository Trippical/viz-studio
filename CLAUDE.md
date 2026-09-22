# viz-site: working conventions

Read this before touching anything. It is written so that any model, of any
size, can work in this repo without guessing.

## What this repo is

A viewer over a folder in an object store. Charts and dashboards are JSON files
in an S3 bucket (or a local folder in development). A Python package `viz`
serves them read-only with FastAPI. A React front end renders them. A Claude
skill plus the `viz` CLI is the only way things get published. The site never
runs SQL against a warehouse.

- Design spec: `docs/superpowers/specs/2026-09-22-viz-site-design.md`
- Security requirements (spec section 12) and the review behind them:
  `docs/superpowers/specs/2026-09-22-security-review.md`
- Implementation plans: `docs/superpowers/plans/`. Execute the plan tasks
  exactly as written. Do not improvise around a step. If a step cannot be
  done as written, stop and report the exact error.
- Session handoff: `.claude/sessions/SUMMARY.md`.

## Commands

The project virtualenv is `.venv/` at the repo root, created with Python
3.11 (`py -3.11 -m venv .venv`). The system default `python` on this machine
is 3.10 and must not be used. Always call the venv interpreter explicitly:

```
.venv/Scripts/python -m pip install -e ".[dev]"   # once
.venv/Scripts/python -m pytest                     # the whole suite, must pass before every commit
.venv/Scripts/python -m pytest tests/x -v          # one file
.venv/Scripts/viz-server                           # serve ./sample-bucket on http://127.0.0.1:8000
.venv/Scripts/python sample-bucket/generate.py     # regenerate the synthetic sample bucket
```

On Linux or macOS the paths are `.venv/bin/python` and `.venv/bin/viz-server`.
Where a plan step says `python -m pytest`, run `.venv/Scripts/python -m pytest`.

## Rules

1. **Tests first.** Every task in a plan writes the failing test, runs it to
   see it fail, writes the minimal code, runs it to see it pass, then commits.
2. **No write routes on the server.** Ever. Publishing is the CLI's job.
3. **Everything in the bucket is untrusted.** Validate on read, sanitize on
   render, never interpolate values into SQL.
4. **Sample bucket stays synthetic.** `author` is `sample@example.com`,
   `source.warehouse_id` is `sample`. Nothing real ever goes in it.
5. **No Databricks credentials in server config or Helm values.** Only the CLI
   on a publisher's machine reads `DATABRICKS_*`.
6. **Boring code.** Explicit over clever. Small files, one responsibility each.
   A future reader may be a smaller model than you.
7. **Do not add dependencies** beyond those in `pyproject.toml` without saying
   so in the commit message and the handoff summary.

## Commit messages

One line summary in the imperative, optional body, then these two trailer
lines exactly:

```
Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_014JyBpbUMQyfxRP89X12AES
```

Commit with `git -c user.name="tripp" -c user.email="dom4domg@gmail.com" commit ...`
if the global git identity is not set. Use multiple `-m` flags for multi-line
messages. Never use `git commit --amend` or force pushes.

## Environment gotchas (Windows, Git Bash)

- A guard hook blocks shell commands that contain backticks, or that redirect
  to paths outside the project (for example `/dev/null`). Use `2>&1` instead
  of `2>/dev/null`. Write files that contain backticks with the Write tool,
  not with a shell heredoc.
- Paths in shell commands use forward slashes:
  `C:/Users/tripp/Documents/Claude/visualization_site`.
- Symlink creation needs privileges on Windows; tests that need symlinks are
  skipped there and run in CI on Linux.
- Line endings: `.gitattributes` forces LF. Ignore the CRLF warnings git prints.

## Layout

```
viz/            python package: ids, schemas, config, storage/, server/, (later) publish/, refresh/
schemas/        JSON Schemas, the single source of truth for the contract
sample-bucket/  synthetic sample data; viz/ inside it mirrors the bucket
tests/          mirrors the package layout; fixtures under tests/fixtures
web/            (plan 2) Vite + React + TypeScript front end
skills/         (plan 3) the publish-viz skill
deploy/         (plan 4) Helm chart and IAM policy documents
docs/superpowers/   specs and plans
```
