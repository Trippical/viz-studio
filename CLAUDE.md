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
8. **Never discard work you did not create.** Do not run `git checkout -- .`,
   `git restore`, `git stash`, `git clean`, or `git reset` on files you did
   not change in your task. Other work may be in progress in the same
   checkout. Stage only your own files by name, and leave everything else in
   the working tree exactly as you found it.

## Commit messages

A commit message is a subject line, a blank line, an optional body, a blank
line, and then a block of two trailer lines that sit together at the very end
with no blank line between them:

```
Co-Authored-By: <the model name your harness gave you> <noreply@anthropic.com>
Claude-Session: <the session URL your harness gave you>
```

`Co-Authored-By` names the model that actually made the commit, exactly as
your harness states it (for example `Claude Fable 5.1`, `Claude Haiku 4.5`).
`Claude-Session` is the session URL your harness states. If your harness
gives you no such lines, use `Co-Authored-By: Claude <noreply@anthropic.com>`
alone.

The reliable way to produce that layout is two `-m` flags, where the second
one contains a real line break between the two trailers:

```
git -c user.name="tripp" -c user.email="dom4domg@gmail.com" commit -m "<subject>" -m "Co-Authored-By: <model> <noreply@anthropic.com>
Claude-Session: <session url>"
```

Git puts exactly one blank line between the two `-m` values, which is the
blank line after the subject. Do not use three or more `-m` flags for the
trailers; that splits them with a blank line. Verify with
`git log -1 --format=%B`: the subject on line 1, an empty line 2, and the two
trailers as the last two non-empty lines, adjacent.

Amending is allowed only to fix the message of a commit that has not been
pushed, and only when a reviewer asks for it. Never rewrite pushed history.
No force pushes.

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
