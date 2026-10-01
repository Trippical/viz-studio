# Plan 5b: Publisher hardening (CLI and skill) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the `viz` publisher safe for an agent to drive: it never publishes to a folder by accident, every refusal that needs a person says "ask the user", one author rule applies to every command, republishing keeps `created_at`, a pulled dashboard cannot silently overwrite a colleague's newer edit, and the small gaps the critics found (SQL files in PowerShell, PII false positives, the placeholder aggregate, preview on a public interface, the install hint, moving an id that is both a chart and a dashboard) are closed.

**Architecture:** No server changes. All code lives in `viz/publish/` plus one default in `viz/config.py`. The CLI stays a set of thin `_cmd_*` functions that call one module each. New behaviour is added as small named functions (`destination`, `publisher_author`, `keep_created_at`, `is_placeholder_aggregate`, `read_sql_file`, the `*_pulled_etag` helpers, `_pick_kind`). The skill (`skills/publish-viz/`) and `README.md` are edited with exact old and new text. This plan runs after plan 5a on the same branch and builds on 5a's storage interface (conditional `put`, `head(key).etag`) and on 5a's `_guard_overwrite` / `_commit` pair in `viz/publish/publish.py`.

**Tech Stack:** Python 3.11, pytest, argparse, pyarrow, FastAPI (unchanged), Markdown.

**Spec:** `docs/superpowers/specs/2026-09-29-hardening-decisions.md` (binding; this is plan 5b: A13-A16, A19-A26, "author is attribution" wording) and `docs/superpowers/specs/2026-09-29-hardening-findings.md` (finding texts A13, A14, A15, A16, A19, A20, A21, A22, A23, A24, A25, A26, intent item 3). Background: `docs/superpowers/specs/2026-09-22-viz-site-design.md` sections 6 and 12.4.

**Decisions taken while writing this plan (flag them in review if you disagree):**

1. A13: the check is "the `VIZ_STORAGE` environment variable is set and not blank", read with `os.environ`, not `Settings().storage` (which defaults to `local`). It applies to `viz publish` and `viz move` (including the dry run of `move`). Exit code 2, like other environment problems.
2. A19 (rule set by the lead): `publisher_author(settings, databricks_user=None, warehouse_id=None)` in `viz/publish/identity.py` is the one rule. Every command stamps the Databricks login only when `DATABRICKS_HOST`, `DATABRICKS_TOKEN` and `DATABRICKS_WAREHOUSE_ID` are all set; otherwise it uses the existing `resolve_author` (VIZ_AUTHOR, then the AWS caller identity, then `<user>@local`). No command newly requires `DATABRICKS_WAREHOUSE_ID`. `viz validate` applies the same rule. For a chart staged by `viz query`, the warehouse in its `source.warehouse_id` (what `--warehouse` or `DATABRICKS_WAREHOUSE_ID` gave the query) counts as the third variable, so `viz query --warehouse X` still validates as before. The check lives in `viz.publish.query.databricks_login_available(warehouse_id=None)`, because only `query.py` reads `DATABRICKS_*`. `viz query` passes the login it already read, so it makes no second connection.
3. A20: `publish` rewrites the staged file's `created_at` to the published value before uploading, then uploads the file's bytes. This keeps plan 5a's rule that the bytes in the bucket are exactly the staged bytes, and the staged copy shows what was published. The published value is untrusted, so it is copied only when it matches `YYYY-MM-DDTHH:MM:SSZ`. It reuses the document plan 5a's `_guard_overwrite` already read (no second read), and plan 5a's conditional PUT with the ETag of that same read still protects the commit.
4. A25: the ETag is stored in a sidecar file next to the staged dashboard, `<id>.json.pulled-etag`, because the dashboard schema forbids extra keys. `pull-dashboard` reads `head(key).etag` before `get`, so if the dashboard changes between the two calls the recorded ETag is older than the content and the later publish is refused (a false refusal, never a silent overwrite). A successful publish deletes the sidecar; `new-dashboard` deletes a stale one.
5. A21: `name` now matches only as the whole column name or after a person word (`first`, `last`, `full`, `customer`, `user`, `sur`, and others listed in Task 7).
6. A22: the placeholder check ignores case, repeated spaces and a trailing semicolon.
7. A23: `viz preview --host <non-loopback>` needs `--allowed-hosts`. Any explicit value, including `*`, is accepted, because passing it is the consent (confirmed by the lead; a test pins it).
8. `viz move` keeps unconditional PUTs in this round (decided by the lead, deferred). Task 11 adds `--kind` only.

## Global Constraints

- Python `>=3.11`. Always run the venv interpreter: `.venv/Scripts/python` (Linux/macOS: `.venv/bin/python`). Never the system `python`.
- This plan runs on the branch `hardening`, after plan 5a. Plan 5a changed `viz/publish/publish.py` (whole file), `validate.py`, `staging.py`, `preview.py`, `viz/config.py`, `tests/publish/conftest.py`, `tests/publish/test_publish.py`, `tests/publish/test_validate.py` and `tests/publish/test_preview.py`; it did not change `viz/publish/cli.py`. Every anchor below is the text as it stands after plan 5a (see the "Interfaces for later plans" section at the end of plan 5a). Where a step says "If this anchor text is not found", read the file, find the equivalent code, apply the same change, and report the difference.
- Plan 5a interfaces used here (Task 0 confirms them): `Storage.put(key, data, content_type, *, if_match: str | None = None, if_none_match: bool = False)` raising `viz.storage.PreconditionFailed`; `Storage.head(key) -> ObjectInfo` raising `NotFound`, with the ETag read as `head(key).etag` (unquoted); `viz.ids.data_key(root, chart_id, file_name)`; `data.file` in chart.json; `Settings.require_identity`; in `publish.py`, `_guard_overwrite(...) -> (existing document, etag)` and `_commit(storage, key, payload, doc_id, etag)`.
- `DATABRICKS_HOST`, `DATABRICKS_TOKEN`, `DATABRICKS_WAREHOUSE_ID` are read only inside `viz/publish/query.py`. Other modules call its functions. They never enter `viz.config.Settings` (CLAUDE.md rule 5).
- The opt-in integration tests (`VIZ_INTEGRATION=1`) are run one file at a time, never with the whole suite: with `VIZ_INTEGRATION=1` the `env` fixture keeps the real `DATABRICKS_*` variables (Task 5), so unit tests would reach a real workspace. No step in this plan sets `VIZ_INTEGRATION`.
- `viz move` keeps unconditional PUTs (deferred by the lead). Do not make them conditional.
- No new dependencies (CLAUDE.md rule 7).
- Every refusal that needs a person's consent contains the words `ask the user before passing --<flag>` (or `ask the user` for refusals without a flag). Tests pin this.
- `author` is attribution, not authentication. Nothing in code, skill or docs may describe it as an identity check or a permission.
- The skill is read by smaller models: plain words, one instruction per sentence.
- New test files go under `tests/publish/` (it already has `__init__.py`).
- Every commit message follows the "Commit messages" section of `CLAUDE.md`: subject, blank line, then two contiguous trailer lines (`Co-Authored-By` naming the model that made the commit as its harness states it, and `Claude-Session` with the session URL its harness states), produced with two `-m` flags. The commit steps below write them as placeholders; fill them from your harness.
- The whole Python suite (`.venv/Scripts/python -m pytest`) must pass before every commit.

## Review Focus

1. **The author stamped by one command disagrees with the author `viz validate` expects** (for example `viz stage` stamps `VIZ_AUTHOR` while `validate` asks Databricks), or a command newly fails because `DATABRICKS_WAREHOUSE_ID` is missing. Expected: stage, new-dashboard and pull-dashboard stamp the Databricks login only when `DATABRICKS_HOST`, `DATABRICKS_TOKEN` and `DATABRICKS_WAREHOUSE_ID` are all set, fall back to `resolve_author` otherwise, and `validate` accepts what they stamped. Pinned in Task 5 (`test_stage_stamps_and_validates_the_databricks_login`, `test_new_dashboard_stamps_and_validates_the_databricks_login`, `test_pull_dashboard_stamps_and_validates_the_databricks_login`, `test_without_a_warehouse_id_every_command_uses_viz_author`, `test_query_with_the_warehouse_flag_validates_without_the_variable`).
2. **The unit suite talks to a real Databricks workspace** on a developer machine that has `DATABRICKS_*` set, now that stage and dashboards consult Databricks. Expected: the `env` fixture removes those variables unless `VIZ_INTEGRATION=1`, and integration tests are only ever run as their own file. Pinned in Task 5 (`test_env_fixture_clears_databricks_variables`).
3. **`created_at` preservation breaks "bucket bytes equal staged bytes", or copies a hostile value from the bucket.** Expected: the staged file is rewritten before the upload and the bucket holds the same bytes; a malformed published `created_at` is ignored. Pinned in Task 6 (`test_republish_keeps_the_first_created_at`, `test_republish_ignores_a_malformed_created_at`).
4. **The pulled-ETag check is in the wrong place or not used as `if_match`**, so a colleague's edit between pull and publish is overwritten; or a stale sidecar blocks the next publish. Expected: check after the overwrite guard, pulled ETag passed as `if_match`, sidecar removed on success. Pinned in Task 10 (`test_colleague_edit_after_pull_is_refused`, `test_publish_passes_the_pulled_etag_as_if_match`, `test_sidecar_is_removed_after_a_successful_publish`).
5. **The explicit-storage check reads `Settings().storage`** (which defaults to `local`, so it never refuses) or runs after something was written. Expected: `os.environ` is checked first thing in `_cmd_publish` and `_cmd_move`, and nothing is written. Pinned in Task 1 (`test_publish_without_viz_storage_is_refused_and_writes_nothing`, `test_move_without_viz_storage_is_refused_and_moves_nothing`).

---

## How to execute a task (read this whether you are a large or a small model)

1. Read `CLAUDE.md` at the repo root first. It has the commands, the commit
   trailers, and the environment gotchas.
2. Work only on the task you were given. Do not start the next one.
3. Do the steps in order. Each step is one action. Do not skip the "run the
   test and see it fail" step; it proves the test is real.
4. Copy the code and text from the step exactly. If code in a step does not
   work as written, fix the smallest thing that makes it work, and say what
   you changed and why in your report. Do not redesign.
5. Plan 5a ran before this plan and changed some of the same files. When a
   step shows "old text" that is not in the file, read the file, find the
   code that does the same job, apply the same change there, and report the
   difference. Never skip the change.
6. If a command fails and you cannot fix it within the task's scope, stop and
   report the full error output. Do not work around it by weakening a test.
7. Before committing, run the whole Python suite:
   `.venv/Scripts/python -m pytest`. It must pass.
8. Stage only the files named in the task's commit step. Never run
   `git checkout -- .`, `git restore`, `git stash`, `git clean` or `git reset`.
9. Report back with: the commit hash, the test summary line, and any
   deviation from the plan. Nothing else is needed.

A guard hook blocks shell commands that contain backticks, `$(...)`, or
redirects to paths outside the project. Create and edit every file in this
plan with the Write and Edit tools, not a shell heredoc.

---

## File structure

| Path | Responsibility |
|---|---|
| `viz/publish/cli.py` | Explicit-storage check for publish and move; `--sql-file`; `--allowed-hosts`; `--kind`; the one author resolver; the pulled-ETag sidecar |
| `viz/publish/publish.py` | `destination()` for the success line; consent wording; `keep_created_at()`; the pulled-version check |
| `viz/publish/identity.py` | `publisher_author()`, `author_errors()`; docstring says attribution |
| `viz/publish/validate.py` | Uses `publisher_author` for charts and dashboards; refuses the placeholder aggregate; consent wording |
| `viz/publish/query.py` | `read_sql_file()`; the install hint; `databricks_login_available()` |
| `viz/publish/dashboards.py` | `pulled_dashboard` returns the ETag; sidecar helpers; consent wording |
| `viz/publish/preview.py` | Refuses a non-loopback host without `--allowed-hosts` |
| `viz/publish/move.py` | `kind` argument and `_pick_kind` |
| `viz/publish/skill.py` | Consent wording |
| `viz/publish/__init__.py` | `stage()` uses `publisher_author` |
| `viz/config.py` | Tighter default `pii_pattern` |
| `skills/publish-viz/SKILL.md`, `references/dashboards.md`, `references/data.md` | Skill text for every change above; `data.md` also names the content-addressed data files from plan 5a |
| `README.md`, `docs/work-setup.md` | The same facts for people |
| `tests/publish/conftest.py` | `env` clears `DATABRICKS_*` |
| `tests/publish/test_storage_required.py`, `test_refusal_wording.py`, `test_author_resolver.py`, `test_created_at.py`, `test_placeholder_aggregate.py`, `test_pull_etag.py`, `test_move_kind.py` | New tests |
| `tests/publish/test_publish.py`, `test_move.py`, `test_validate.py`, `test_validate_author.py`, `test_query.py`, `test_pii.py`, `test_preview.py`, `tests/test_skill.py` | Updated or appended tests |

---

### Task 0: Confirm plan 5a interfaces

**Files:** none changed. No commit.

**Interfaces:**
- Consumes: the output of plan 5a on the branch `hardening`.
- Produces: a short report the later tasks rely on.

- [ ] **Step 1: Check the branch**

Run: `git branch --show-current`
Expected: `hardening`. If it prints anything else, stop and report.

- [ ] **Step 2: Grep for the storage interface**

Run each command and keep the output:

```
grep -n "def put" viz/storage/base.py viz/storage/local.py viz/storage/s3.py
grep -n "def head" viz/storage/base.py viz/storage/local.py viz/storage/s3.py
grep -rn "class PreconditionFailed" viz/storage
grep -n "PreconditionFailed" viz/storage/__init__.py
```

Expected: every `def put` line contains `if_match` and `if_none_match` (in `base.py`, `local.py` and `s3.py` the parameters may continue on the next line; if a `def put` line does not show them, read the two lines below it); every `def head` line ends with `-> ObjectInfo:` (plan 5a kept that return type; the ETag is `head(key).etag`); `PreconditionFailed` is defined in `viz/storage/base.py` and exported from `viz/storage/__init__.py`.

- [ ] **Step 3: Grep for the contract and settings changes**

```
grep -n "def data_key" viz/ids.py
grep -n "require_identity" viz/config.py
grep -n "if_match\|if_none_match\|PreconditionFailed" viz/publish/publish.py
grep -n "_guard_overwrite(storage, key\|_commit(storage, key\|storage.put(\|print(f\"published" viz/publish/publish.py
grep -n "from .staging import" viz/publish/validate.py
grep -n "require_identity=False" viz/publish/preview.py
```

Expected:
- `def data_key(root: str, chart_id: str, file_name: str) -> str:` (the third parameter is a file name, not `fmt`).
- a `require_identity: bool = False` field.
- `publish.py` uses `if_match`, `if_none_match` and `PreconditionFailed`.
- the fourth grep prints these lines (line numbers vary): `    existing, etag = _guard_overwrite(storage, key, force, out)`, `    storage.put(data_key(root, chart_id, file_name), (chart_dir / file_name).read_bytes(), MEDIA_TYPES[fmt])`, `    _commit(storage, key, (chart_dir / "chart.json").read_bytes(), chart_id, etag)`, `    print(f"published: {chart_id}", file=out)`, `    _existing_doc, etag = _guard_overwrite(storage, key, force, out)`, `    _commit(storage, key, path.read_bytes(), dashboard_id, etag)`, `    print(f"published: {dashboard_id}", file=out)`, plus the two `storage.put(` lines inside `_commit`.
- `from .staging import LARGE_MAX_BYTES, SMALL_MAX_BYTES, SMALL_MAX_ROWS, file_sha256`.
- one `return Settings(...)` line in `preview.py` ending with `require_identity=False)`.

- [ ] **Step 4: Run the whole suite**

Run: `.venv/Scripts/python -m pytest`
Expected: all pass, 0 failed.

- [ ] **Step 5: Report**

If any expectation in Steps 1-4 is not met, stop here and report the exact output. Do not start Task 1.

Otherwise report, verbatim, the lines printed by the fourth grep of Step 3. Tasks 1, 6 and 10 anchor on them.

---

### Task 1: `viz publish` and `viz move` refuse implicit local storage and print the destination (A13)

**Files:**
- Modify: `viz/publish/cli.py`, `viz/publish/publish.py`, `tests/publish/test_publish.py`, `tests/test_skill.py`, `skills/publish-viz/SKILL.md`, `README.md`, `docs/work-setup.md`
- Create: `tests/publish/test_storage_required.py`

**Interfaces:**
- Consumes: `viz.config.Settings` (`storage`, `s3_bucket`, `local_dir`, `root_prefix`), `viz.publish.errors.CliError`.
- Produces:
  - `viz.publish.publish.destination(settings: Settings, key: str) -> str`: `s3://<bucket>/<key>` when `settings.storage == "s3"`, else the resolved local file path as a string.
  - `viz.publish.cli._require_explicit_storage() -> None`: raises `CliError(code=2)` when `VIZ_STORAGE` is unset or blank in `os.environ`.
  - Success lines: `published: <id> -> <destination of the document key>` and `moved: <old> -> <new> in <destination of the root prefix>`.

- [ ] **Step 1: Write the failing tests**

Create `tests/publish/test_storage_required.py`:

```python
"""viz publish and viz move never fall back to the default local folder (finding A13)."""
from datetime import date, datetime, timezone

import pyarrow as pa

from viz.config import Settings
from viz.publish.cli import main
from viz.publish.publish import destination
from viz.publish.staging import write_staged_chart

NOW = datetime(2026, 9, 22, 10, 0, 0, tzinfo=timezone.utc)


def _staged(staging_root, chart_id="sales/new-chart"):
    table = pa.table({"month": [date(2024, 1, 1), date(2024, 2, 1)], "revenue": [1.5, 2.5]})
    return write_staged_chart(table, chart_id, staging_root, author="tester@example.com", now=NOW)


def test_publish_without_viz_storage_is_refused_and_writes_nothing(env, bucket, staging_root, monkeypatch, capsys):
    staged = _staged(staging_root)
    monkeypatch.delenv("VIZ_STORAGE")
    assert main(["publish", str(staged.dir)]) == 2
    err = capsys.readouterr().err
    assert err.startswith("error: VIZ_STORAGE is not set")
    assert "ask the user" in err
    assert not (bucket / "viz" / "charts" / "sales" / "new-chart").exists()


def test_blank_viz_storage_is_refused(env, staging_root, monkeypatch, capsys):
    staged = _staged(staging_root)
    monkeypatch.setenv("VIZ_STORAGE", "  ")
    assert main(["publish", str(staged.dir)]) == 2
    assert "VIZ_STORAGE is not set" in capsys.readouterr().err


def test_move_without_viz_storage_is_refused_and_moves_nothing(env, bucket, monkeypatch, capsys):
    monkeypatch.delenv("VIZ_STORAGE")
    assert main(["move", "sales/revenue-by-region", "sales/renamed", "--yes"]) == 2
    assert "VIZ_STORAGE is not set" in capsys.readouterr().err
    assert (bucket / "viz" / "charts" / "sales" / "revenue-by-region" / "chart.json").is_file()
    assert not (bucket / "viz" / "charts" / "sales" / "renamed").exists()


def test_publish_prints_the_local_destination(env, bucket, staging_root, capsys):
    staged = _staged(staging_root)
    assert main(["publish", str(staged.dir)]) == 0
    expected = str((bucket / "viz" / "charts" / "sales" / "new-chart" / "chart.json").resolve())
    assert f"published: sales/new-chart -> {expected}" in capsys.readouterr().out.splitlines()


def test_move_prints_the_local_destination(env, bucket, capsys):
    assert main(["move", "sales/revenue-by-region", "sales/renamed", "--yes"]) == 0
    expected = str((bucket / "viz").resolve())
    assert f"moved: sales/revenue-by-region -> sales/renamed in {expected}" in capsys.readouterr().out


def test_destination_for_s3():
    settings = Settings(storage="s3", s3_bucket="viz-bucket", root_prefix="viz/")
    assert destination(settings, "viz/charts/a/chart.json") == "s3://viz-bucket/viz/charts/a/chart.json"
```

Append to `tests/test_skill.py`:

```python


def test_skill_says_to_ask_when_viz_storage_is_not_set():
    text = _text(SKILL / "SKILL.md")
    assert "`VIZ_STORAGE` is not set" in text
```

- [ ] **Step 2: Run them to see them fail**

Run: `.venv/Scripts/python -m pytest tests/publish/test_storage_required.py tests/test_skill.py -v`
Expected: `tests/publish/test_storage_required.py` fails to collect with `ImportError: cannot import name 'destination'`; `test_skill_says_to_ask_when_viz_storage_is_not_set` FAILS.

- [ ] **Step 3: Add `destination` to `viz/publish/publish.py` and use it in the success lines**

Add this function directly above `def publish_chart(`:

```python
def destination(settings: Settings, key: str) -> str:
    """Where a key lives, for the success line: s3://<bucket>/<key>, or a local file path."""
    if settings.storage == "s3":
        return f"s3://{settings.s3_bucket}/{key}"
    return str((Path(settings.local_dir) / key).resolve())
```

In `publish_chart`, replace

```python
    print(f"published: {chart_id}", file=out)
```

with

```python
    print(f"published: {chart_id} -> {destination(settings, key)}", file=out)
```

In `publish_dashboard`, replace

```python
    print(f"published: {dashboard_id}", file=out)
```

with

```python
    print(f"published: {dashboard_id} -> {destination(settings, key)}", file=out)
```

`key` is the variable that holds the document's bucket key (`chart_key(...)` in `publish_chart`, `dashboard_key(...)` in `publish_dashboard`). If this anchor text is not found, or 5a renamed `key`, read the file, find the equivalent code, and apply the same change; report the difference.

- [ ] **Step 4: Add the explicit-storage check to `viz/publish/cli.py`**

Replace

```python
import argparse
import sys
```

with

```python
import argparse
import os
import sys
```

Add `destination` to the names imported from `.publish`. Today the line is

```python
from .publish import PublishRefused, publish_chart, publish_dashboard
```

and it becomes

```python
from .publish import PublishRefused, destination, publish_chart, publish_dashboard
```

If that import line looks different after plan 5a, add `destination` to whatever it imports from `.publish`.

Add this function directly above `def _cmd_publish(args) -> int:`:

```python
def _require_explicit_storage() -> None:
    """publish and move write to the bucket. They never fall back to the default local
    folder: VIZ_STORAGE must be set in the environment (finding A13)."""
    if not os.environ.get("VIZ_STORAGE", "").strip():
        raise CliError(
            "VIZ_STORAGE is not set, so there is nowhere to write. Ask the user where to publish: "
            "VIZ_STORAGE=s3 with VIZ_S3_BUCKET for the shared bucket, or VIZ_STORAGE=local with "
            "VIZ_LOCAL_DIR for a folder on this machine.",
            code=2,
        )
```

Replace

```python
def _cmd_publish(args) -> int:
    settings = Settings()
```

with

```python
def _cmd_publish(args) -> int:
    _require_explicit_storage()
    settings = Settings()
```

Replace

```python
def _cmd_move(args) -> int:
    settings = Settings()
```

with

```python
def _cmd_move(args) -> int:
    _require_explicit_storage()
    settings = Settings()
```

Replace

```python
    print(f"moved: {plan.old_id} -> {plan.new_id}")
```

with

```python
    print(f"moved: {plan.old_id} -> {plan.new_id} in {destination(settings, settings.root_prefix)}")
```

If any anchor text is not found, read the file, find the equivalent code, and apply the same change; report the difference.

- [ ] **Step 5: Update the existing success-line assertions**

In `tests/publish/test_publish.py`, the line

```python
    assert capsys.readouterr().out.strip() == "published: sales/new-chart"
```

appears twice (in `test_publish_chart_puts_data_then_document` and `test_publish_command`). Replace every occurrence with

```python
    assert capsys.readouterr().out.strip().startswith("published: sales/new-chart -> ")
```

If plan 5a changed those lines, find every assertion in the file that compares the output to exactly `published: sales/new-chart` and make it a `startswith("published: sales/new-chart -> ")` check.

- [ ] **Step 6: Update the skill, README and setup guide**

In `skills/publish-viz/SKILL.md`, replace

```markdown
- `--allow-row-level`: a large-lane chart shares every row. Ask whether the
  row-level data may be shared, or rewrite the SQL to aggregate.
```

with

```markdown
- `--allow-row-level`: a large-lane chart shares every row. Ask whether the
  row-level data may be shared, or rewrite the SQL to aggregate.
- `VIZ_STORAGE` is not set: `viz publish` and `viz move` refuse to run.
  Ask the user which bucket to publish to. Do not pick one yourself.
```

In `README.md`, replace

```markdown
`VIZ_STAGING_DIR`. `--force` and `--yes` are flags only.
```

with

```markdown
`VIZ_STAGING_DIR`. `--force` and `--yes` are flags only. `viz publish` and
`viz move` refuse to run unless `VIZ_STORAGE` is set in the environment, so a
missing setting never publishes into `./sample-bucket`; on success they print
where the document went (`s3://<bucket>/<key>` or a local path).
```

In `docs/work-setup.md`, replace

```markdown
| `VIZ_STORAGE` | `local` | both | `local` (a folder) or `s3` |
```

with

```markdown
| `VIZ_STORAGE` | `local` | both | `local` (a folder) or `s3`. `viz publish` and `viz move` refuse to run unless it is set explicitly |
```

- [ ] **Step 7: Run the tests**

Run: `.venv/Scripts/python -m pytest tests/publish/test_storage_required.py tests/publish/test_publish.py tests/publish/test_move.py tests/test_skill.py tests/test_work_setup_doc.py -v`
Expected: all pass.

- [ ] **Step 8: Run the whole suite and commit**

Run: `.venv/Scripts/python -m pytest`

```bash
git add viz/publish/cli.py viz/publish/publish.py tests/publish/test_storage_required.py tests/publish/test_publish.py tests/test_skill.py skills/publish-viz/SKILL.md README.md docs/work-setup.md
git -c user.name="tripp" -c user.email="dom4domg@gmail.com" commit -m "fix: publish and move refuse implicit local storage and print the destination" -m "Co-Authored-By: <model name from your harness> <noreply@anthropic.com>
Claude-Session: <session url from your harness>"
```

---

### Task 2: Refusals that need consent say "ask the user" (A14)

**Files:**
- Modify: `viz/publish/publish.py`, `viz/publish/validate.py`, `viz/publish/cli.py`, `viz/publish/dashboards.py`, `viz/publish/skill.py`, `skills/publish-viz/SKILL.md`, `skills/publish-viz/references/dashboards.md`, `tests/publish/test_publish.py`, `tests/publish/test_move.py`, `tests/publish/test_validate.py`, `tests/test_skill.py`
- Create: `tests/publish/test_refusal_wording.py`

**Interfaces:**
- Consumes: nothing new.
- Produces: these exact refusal texts:
  - publish overwrite: `id exists: author <a>, updated_at <u>; ask the user before passing --force to overwrite`
  - large lane: `large lane publishes row-level data; ask the user before passing --allow-row-level to confirm`
  - move dry run: `dry run: ask the user before passing --yes to apply`
  - staged dashboard exists: `<path> already exists; ask the user before passing --force to replace it`
  - installed skill exists: `<path> already exists; ask the user before passing --force to replace it`

- [ ] **Step 1: Write the failing tests**

Create `tests/publish/test_refusal_wording.py`:

```python
"""Every refusal that needs a person's consent says so, so an agent stops and asks
instead of adding the flag itself (finding A14)."""
from datetime import date, datetime, timezone

import pyarrow as pa

from viz.publish import staging
from viz.publish.cli import main
from viz.publish.staging import write_staged_chart

NOW = datetime(2026, 9, 22, 10, 0, 0, tzinfo=timezone.utc)


def _staged(staging_root, chart_id):
    table = pa.table({"month": [date(2024, 1, 1), date(2024, 2, 1)], "revenue": [1.5, 2.5]})
    return write_staged_chart(table, chart_id, staging_root, author="tester@example.com", now=NOW)


def test_publish_overwrite_says_ask_the_user(env, staging_root, capsys):
    staged = _staged(staging_root, "sales/ask-first")
    assert main(["publish", str(staged.dir)]) == 0
    capsys.readouterr()
    assert main(["publish", str(staged.dir)]) == 1
    assert "ask the user before passing --force" in capsys.readouterr().err


def test_row_level_says_ask_the_user(env, staging_root, capsys, monkeypatch):
    monkeypatch.setattr(staging, "SMALL_MAX_ROWS", 0)
    staged = _staged(staging_root, "sales/ask-large")
    assert main(["validate", str(staged.dir)]) == 1
    assert "ask the user before passing --allow-row-level" in capsys.readouterr().err


def test_move_dry_run_says_ask_the_user(env, capsys):
    assert main(["move", "sales/revenue-by-region", "sales/renamed"]) == 1
    assert "ask the user before passing --yes" in capsys.readouterr().err


def test_replacing_a_staged_dashboard_says_ask_the_user(env, capsys):
    assert main(["new-dashboard", "sales/ask-board"]) == 0
    capsys.readouterr()
    assert main(["new-dashboard", "sales/ask-board"]) == 1
    assert "ask the user before passing --force" in capsys.readouterr().err


def test_replacing_an_installed_skill_says_ask_the_user(tmp_path, capsys):
    assert main(["install-skill", "--dest", str(tmp_path)]) == 0
    capsys.readouterr()
    assert main(["install-skill", "--dest", str(tmp_path)]) == 1
    assert "ask the user before passing --force" in capsys.readouterr().err
```

Append to `tests/test_skill.py`:

```python


def _step(text: str, start: str, end: str) -> str:
    return text[text.index(start):text.index(end)]


def test_skill_stops_on_errors_that_need_the_user():
    text = _text(SKILL / "SKILL.md")
    step5 = _step(text, "5. **Validate.**", "6. **Preview")
    assert "ask the user" in step5
    assert "Never add `--force`, `--yes` or `--allow-row-level` on your own." in step5
```

- [ ] **Step 2: Run them to see them fail**

Run: `.venv/Scripts/python -m pytest tests/publish/test_refusal_wording.py tests/test_skill.py -v`
Expected: all five tests in `test_refusal_wording.py` FAIL (the messages say `pass --...`), and `test_skill_stops_on_errors_that_need_the_user` FAILS.

- [ ] **Step 3: Change the messages**

In `viz/publish/publish.py`, replace the text

```
; pass --force to overwrite"
```

with

```
; ask the user before passing --force to overwrite"
```

(it is the end of the f-string in the overwrite guard that starts `f"id exists: author {author}, updated_at {updated}`).

In `viz/publish/validate.py`, replace

```python
            errors.append("large lane publishes row-level data; pass --allow-row-level to confirm")
```

with

```python
            errors.append("large lane publishes row-level data; ask the user before passing --allow-row-level to confirm")
```

In `viz/publish/cli.py`, replace

```python
        print("dry run: pass --yes to apply", file=sys.stderr)
```

with

```python
        print("dry run: ask the user before passing --yes to apply", file=sys.stderr)
```

In `viz/publish/dashboards.py`, replace

```python
        raise DashboardError(f"{path} already exists; pass --force to replace it")
```

with

```python
        raise DashboardError(f"{path} already exists; ask the user before passing --force to replace it")
```

In `viz/publish/skill.py`, replace

```python
            raise SkillExists(f"{target} already exists; pass --force to replace it")
```

with

```python
            raise SkillExists(f"{target} already exists; ask the user before passing --force to replace it")
```

If any anchor text is not found, read the file, find the equivalent code, and apply the same change; report the difference.

- [ ] **Step 4: Update the existing assertions**

In `tests/publish/test_publish.py`, replace

```python
    assert exc.value.errors == ["id exists: author tester@example.com, updated_at 2026-09-22T10:00:00Z; pass --force to overwrite"]
```

with

```python
    assert exc.value.errors == ["id exists: author tester@example.com, updated_at 2026-09-22T10:00:00Z; ask the user before passing --force to overwrite"]
```

and replace

```python
    assert "pass --allow-row-level" in capsys.readouterr().err
```

with

```python
    assert "ask the user before passing --allow-row-level" in capsys.readouterr().err
```

In `tests/publish/test_move.py`, replace

```python
    assert "pass --yes to apply" in captured.err
```

with

```python
    assert "ask the user before passing --yes to apply" in captured.err
```

In `tests/publish/test_validate.py`, replace

```python
        "large lane publishes row-level data; pass --allow-row-level to confirm"
```

with

```python
        "large lane publishes row-level data; ask the user before passing --allow-row-level to confirm"
```

- [ ] **Step 5: Carve consent refusals out of the skill's "fix every error" step**

In `skills/publish-viz/SKILL.md`, replace

```markdown
5. **Validate.** `viz validate .viz-staging/charts/<id>`. Fix every error
   it prints and run it again until it prints `ok:`.
```

with

```markdown
5. **Validate.** `viz validate .viz-staging/charts/<id>`. Fix every error
   it prints and run it again until it prints `ok:`. The exception is an
   error that says `ask the user`: it needs the user's consent, not a fix.
   Stop, show the user that line, and wait for their answer. The same goes
   for `viz publish`, `viz move` and the dashboard commands.
   Never add `--force`, `--yes` or `--allow-row-level` on your own.
```

In `skills/publish-viz/references/dashboards.md`, replace

```markdown
Both refuse to replace a staged file you may have edited. Add `--force` only
when you mean to discard the staged copy.
```

with

```markdown
Both refuse to replace a staged file you may have edited. The refusal says
`ask the user before passing --force`: do that, because `--force` discards
the staged copy.
```

- [ ] **Step 6: Run the tests**

Run: `.venv/Scripts/python -m pytest tests/publish/test_refusal_wording.py tests/publish/test_publish.py tests/publish/test_move.py tests/publish/test_validate.py tests/publish/test_dashboards.py tests/publish/test_skill_install.py tests/test_skill.py -v`
Expected: all pass.

- [ ] **Step 7: Run the whole suite and commit**

Run: `.venv/Scripts/python -m pytest`
If another test fails because it looked for `pass --force`, `pass --yes` or `pass --allow-row-level`, change only that expected text to the new wording and report it.

```bash
git add viz/publish/publish.py viz/publish/validate.py viz/publish/cli.py viz/publish/dashboards.py viz/publish/skill.py skills/publish-viz/SKILL.md skills/publish-viz/references/dashboards.md tests/publish/test_refusal_wording.py tests/publish/test_publish.py tests/publish/test_move.py tests/publish/test_validate.py tests/test_skill.py
git -c user.name="tripp" -c user.email="dom4domg@gmail.com" commit -m "fix: refusals that need consent tell the agent to ask the user" -m "Co-Authored-By: <model name from your harness> <noreply@anthropic.com>
Claude-Session: <session url from your harness>"
```

---

### Task 3: The skill allows `renderer`, and describes `author` as attribution (A15, wording)

**Files:**
- Modify: `skills/publish-viz/SKILL.md`, `skills/publish-viz/references/dashboards.md`, `tests/test_skill.py`

**Interfaces:**
- Consumes: the `_step` helper added to `tests/test_skill.py` in Task 2.
- Produces: skill text only.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_skill.py`:

```python


def test_skill_allows_editing_the_renderer():
    text = _text(SKILL / "SKILL.md")
    step4 = _step(text, "4. **Write the chart.**", "5. **Validate.**")
    assert "`renderer`" in step4


def test_dashboards_guide_calls_author_attribution():
    text = _text(SKILL / "references" / "dashboards.md")
    assert "must equal the identity" not in text
    assert "with your identity" not in text
    assert "attribution" in text
```

- [ ] **Step 2: Run them to see them fail**

Run: `.venv/Scripts/python -m pytest tests/test_skill.py -v`
Expected: `test_skill_allows_editing_the_renderer` and `test_dashboards_guide_calls_author_attribution` FAIL.

- [ ] **Step 3: Edit the skill**

In `skills/publish-viz/SKILL.md`, replace

```markdown
   example in `references/vega-lite.md`. Only edit `title`, `description`,
   `tags`, `spec`, and for a large-lane chart `aggregate`. Keep `source`.
```

with

```markdown
   example in `references/vega-lite.md`. Only edit `title`, `description`,
   `tags`, `spec`, `renderer`, and for a large-lane chart `aggregate`.
   Set `renderer` to `"stat"` only for a single headline number (see the
   stat tile in `references/vega-lite.md`). Keep `source`.
```

In `skills/publish-viz/references/dashboards.md`, replace

```markdown
Never write a dashboard file from nothing: `author` must equal the identity
the CLI resolves, and the CLI stamps it for you.
```

with

```markdown
Never write a dashboard file from nothing: the CLI stamps `author` for you.
`author` records who published the dashboard (attribution). It is not a
permission check, and `viz validate` rejects a hand-typed value.
```

and replace

```markdown
  copies it into staging with your identity and a new `updated_at`.
```

with

```markdown
  copies it into staging with you as `author` and a new `updated_at`.
```

- [ ] **Step 4: Run the tests**

Run: `.venv/Scripts/python -m pytest tests/test_skill.py -v`
Expected: all pass.

- [ ] **Step 5: Run the whole suite and commit**

Run: `.venv/Scripts/python -m pytest`

```bash
git add skills/publish-viz/SKILL.md skills/publish-viz/references/dashboards.md tests/test_skill.py
git -c user.name="tripp" -c user.email="dom4domg@gmail.com" commit -m "docs: skill allows renderer edits and calls author attribution" -m "Co-Authored-By: <model name from your harness> <noreply@anthropic.com>
Claude-Session: <session url from your harness>"
```

---

### Task 4: `viz query --sql-file` and the install hint (A16, A24)

**Files:**
- Modify: `viz/publish/query.py`, `viz/publish/cli.py`, `tests/publish/test_query.py`, `tests/test_skill.py`, `skills/publish-viz/SKILL.md`, `README.md`, `docs/work-setup.md`

**Interfaces:**
- Consumes: `viz.publish.query.QueryError`.
- Produces:
  - `viz.publish.query.read_sql_file(path: str) -> str`: reads UTF-8 (a byte order mark is dropped); raises `QueryError(code=2)` when the file is missing or not UTF-8.
  - `read_sql_argument("@path")` now calls `read_sql_file`.
  - `viz query` takes exactly one of `--sql SQL_OR_@FILE` and `--sql-file PATH` (argparse exits 2 otherwise).
  - `INSTALL_HINT` names `pip install -e ".[databricks]"` from a checkout.

- [ ] **Step 1: Write the failing tests**

In `tests/publish/test_query.py`, replace the import line

```python
from viz.publish.query import DeniedQuery, QueryError, read_sql_argument, resolve_warehouse, run_query
```

with

```python
from viz.publish.query import DeniedQuery, QueryError, read_sql_argument, read_sql_file, resolve_warehouse, run_query
```

Replace the whole function `test_missing_connector_gives_install_hint` with:

```python
def test_missing_connector_gives_install_hint(env, dbx_env, monkeypatch):
    monkeypatch.setattr(query, "_connect", None)
    monkeypatch.setitem(sys.modules, "databricks", None)
    monkeypatch.setitem(sys.modules, "databricks.sql", None)
    with pytest.raises(QueryError) as exc:
        run_query(SQL, Settings())
    assert 'pip install -e ".[databricks]"' in str(exc.value)
    assert "viz-site[databricks]" not in str(exc.value), "viz-site is not on PyPI"
```

Append to the end of `tests/publish/test_query.py`:

```python


def test_read_sql_file(tmp_path):
    path = tmp_path / "q.sql"
    path.write_bytes(b"\xef\xbb\xbfSELECT 3\n")  # a UTF-8 byte order mark, as some Windows editors write
    assert read_sql_file(str(path)) == "SELECT 3\n"
    with pytest.raises(QueryError, match="sql file not found"):
        read_sql_file(str(tmp_path / "missing.sql"))
    utf16 = tmp_path / "utf16.sql"
    utf16.write_bytes("SELECT 4".encode("utf-16"))  # what PowerShell 5 writes with >
    with pytest.raises(QueryError, match="not UTF-8"):
        read_sql_file(str(utf16))


def test_query_command_reads_sql_file(env, dbx_env, fake, staging_root, tmp_path):
    path = tmp_path / "q.sql"
    path.write_text(SQL, encoding="utf-8")
    assert main(["query", "--sql-file", str(path), "--id", "sales/from-sql-file"]) == 0
    doc = json.loads((staging_root / "charts" / "sales" / "from-sql-file" / "chart.json").read_text(encoding="utf-8"))
    assert doc["source"]["sql"] == SQL
    assert SQL in fake.log


def test_query_command_needs_exactly_one_sql_option(env, dbx_env, fake, tmp_path):
    with pytest.raises(SystemExit) as exc:
        main(["query", "--id", "sales/no-sql"])
    assert exc.value.code == 2
    path = tmp_path / "q.sql"
    path.write_text(SQL, encoding="utf-8")
    with pytest.raises(SystemExit) as exc:
        main(["query", "--sql", SQL, "--sql-file", str(path), "--id", "sales/both"])
    assert exc.value.code == 2
```

Append to `tests/test_skill.py`:

```python


def test_skill_uses_sql_file():
    text = _text(SKILL / "SKILL.md")
    assert "viz query --sql-file" in text
    assert "--sql @" not in text
```

- [ ] **Step 2: Run them to see them fail**

Run: `.venv/Scripts/python -m pytest tests/publish/test_query.py tests/test_skill.py -v`
Expected: `tests/publish/test_query.py` fails to collect with `ImportError: cannot import name 'read_sql_file'`; `test_skill_uses_sql_file` FAILS.

- [ ] **Step 3: Add `read_sql_file` and fix the hint in `viz/publish/query.py`**

Replace

```python
INSTALL_HINT = 'databricks-sql-connector is not installed; run: pip install "viz-site[databricks]"'
```

with

```python
INSTALL_HINT = (
    'databricks-sql-connector is not installed; from your viz-site checkout run: '
    'pip install -e ".[databricks]" (see docs/work-setup.md)'
)
```

Replace the whole function `read_sql_argument` with:

```python
def read_sql_file(path: str) -> str:
    """The SQL in a file. `--sql-file` exists because PowerShell treats a leading @ as an
    operator, so `--sql @query.sql` does not work there (finding A16)."""
    sql_path = Path(path)
    if not sql_path.is_file():
        raise QueryError(f"sql file not found: {sql_path}", code=2)
    try:
        return sql_path.read_text(encoding="utf-8-sig")
    except UnicodeDecodeError as err:
        raise QueryError(f"sql file {sql_path} is not UTF-8 text; save it as UTF-8 ({err})", code=2) from err


def read_sql_argument(value: str) -> str:
    if value.startswith("@"):
        return read_sql_file(value[1:])
    return value
```

- [ ] **Step 4: Add `--sql-file` to `viz/publish/cli.py`**

Replace

```python
from .query import QueryError, read_sql_argument, resolve_warehouse, run_query
```

with

```python
from .query import QueryError, read_sql_argument, read_sql_file, resolve_warehouse, run_query
```

In `_cmd_query`, replace

```python
        sql = read_sql_argument(args.sql)
```

with

```python
        sql = read_sql_file(args.sql_file) if args.sql_file else read_sql_argument(args.sql)
```

In `build_parser`, replace

```python
    query_p.add_argument("--sql", required=True, metavar="SQL_OR_@FILE")
```

with

```python
    sql_group = query_p.add_mutually_exclusive_group(required=True)
    sql_group.add_argument("--sql", default=None, metavar="SQL_OR_@FILE", help="the SQL text, or @path to read it from a file")
    sql_group.add_argument("--sql-file", default=None, metavar="PATH", help="read the SQL from this file (works in every shell)")
```

If any anchor text is not found, read the file, find the equivalent code, and apply the same change; report the difference.

- [ ] **Step 5: Use `--sql-file` in the skill, README and setup guide**

In `skills/publish-viz/SKILL.md`, replace

```markdown
3. **Stage the rows.**
   `viz query --sql @query.sql --id sales/emea/revenue-by-region` runs the
   SQL and stages the result. For a file the user already has:
```

with

```markdown
3. **Stage the rows.** Write the SQL to a file, then
   `viz query --sql-file query.sql --id sales/emea/revenue-by-region` runs
   it and stages the result. For a file the user already has:
```

In `README.md`, replace

```
    viz query --sql @q.sql --id sales/emea/revenue      # run SQL on Databricks and stage the result
    viz query --sql @q.sql --id sales/emea/revenue --drop-columns a,b --staging DIR
```

with

```
    viz query --sql-file q.sql --id sales/emea/revenue  # run SQL on Databricks and stage the result
    viz query --sql-file q.sql --id sales/emea/revenue --drop-columns a,b --staging DIR
```

In `docs/work-setup.md`, replace

```
.venv/bin/viz query --sql @first.sql --id smoke/first-chart
```

with

```
.venv/bin/viz query --sql-file first.sql --id smoke/first-chart
```

- [ ] **Step 6: Run the tests**

Run: `.venv/Scripts/python -m pytest tests/publish/test_query.py tests/publish/test_validate_author.py tests/test_skill.py tests/test_work_setup_doc.py -v`
Expected: all pass.

- [ ] **Step 7: Run the whole suite and commit**

Run: `.venv/Scripts/python -m pytest`

```bash
git add viz/publish/query.py viz/publish/cli.py tests/publish/test_query.py tests/test_skill.py skills/publish-viz/SKILL.md README.md docs/work-setup.md
git -c user.name="tripp" -c user.email="dom4domg@gmail.com" commit -m "feat: viz query --sql-file, and an install hint that works from a checkout" -m "Co-Authored-By: <model name from your harness> <noreply@anthropic.com>
Claude-Session: <session url from your harness>"
```

---

### Task 5: One author resolver for every command (A19, attribution wording)

The rule (set by the lead): the Databricks login only when `DATABRICKS_HOST`, `DATABRICKS_TOKEN` and `DATABRICKS_WAREHOUSE_ID` are all set (for a `viz query` chart, its `source.warehouse_id` counts as the third); otherwise the existing `resolve_author`. No command newly requires `DATABRICKS_WAREHOUSE_ID`, and `viz validate` follows the same rule. Never run this task's tests with `VIZ_INTEGRATION=1` set.

**Files:**
- Modify: `viz/publish/query.py`, `viz/publish/identity.py`, `viz/publish/validate.py`, `viz/publish/cli.py`, `viz/publish/__init__.py`, `tests/publish/conftest.py`, `tests/publish/test_validate_author.py`, `skills/publish-viz/SKILL.md`, `README.md`, `docs/work-setup.md`
- Create: `tests/publish/test_author_resolver.py`

**Interfaces:**
- Consumes: `viz.publish.query.databricks_configured() -> bool` (true when `DATABRICKS_HOST` and `DATABRICKS_TOKEN` are set), `viz.publish.query.current_user(warehouse_id=None) -> str` (raises `QueryError`), `resolve_author(settings, databricks_user=None)`.
- Produces:
  - `viz.publish.query.databricks_login_available(warehouse_id: str | None = None) -> bool`: true when `databricks_configured()` and a warehouse is known (`warehouse_id` when given, else `DATABRICKS_WAREHOUSE_ID`). Makes no connection.
  - `viz.publish.identity.publisher_author(settings: Settings, databricks_user: str | None = None, warehouse_id: str | None = None) -> str`: `databricks_user` if given; else the Databricks login if `databricks_login_available(warehouse_id)`; else `resolve_author(settings)`. May raise `QueryError` or AWS errors. With only `DATABRICKS_HOST` and `DATABRICKS_TOKEN` set it never contacts Databricks.
  - `viz.publish.identity.author_errors(doc: dict, expected: str) -> list[str]`: the same two messages `check_author` produced.
  - `check_author(doc, settings, databricks_user=None)` is kept (tests use it) and now calls `author_errors`.
  - `viz validate` checks charts (with the chart's `source.warehouse_id` for `databricks-sql` charts, so a `viz query --warehouse X` chart validates without `DATABRICKS_WAREHOUSE_ID`) and dashboards against `publisher_author`: the same rule the stamping commands use.
  - `stage`, `query`, `new-dashboard`, `pull-dashboard` and `viz.publish.stage()` stamp `publisher_author`. None of them newly requires `DATABRICKS_WAREHOUSE_ID`.
  - The `env` test fixture removes `DATABRICKS_HOST`, `DATABRICKS_TOKEN`, `DATABRICKS_WAREHOUSE_ID` unless `VIZ_INTEGRATION=1`. Integration tests are run one file at a time, never with the whole suite.

- [ ] **Step 1: Write the failing tests**

Create `tests/publish/test_author_resolver.py`:

```python
"""One author rule for every command that stamps a document (finding A19): the
Databricks login when DATABRICKS_HOST, DATABRICKS_TOKEN and DATABRICKS_WAREHOUSE_ID
are all set, otherwise VIZ_AUTHOR, the AWS caller identity, or <user>@local.
viz validate applies the same rule."""
import json
import os

import pytest

import viz.publish.identity as identity
from viz.config import Settings
from viz.publish import query
from viz.publish.cli import main
from viz.publish.identity import publisher_author


class FakeCursor:
    def __init__(self, calls):
        self.calls = calls

    def execute(self, sql):
        self.calls.append(sql)

    def fetchone(self):
        return ("dbx@example.com",)

    def close(self):
        pass


class FakeConnection:
    def __init__(self, calls):
        self.calls = calls

    def cursor(self):
        return FakeCursor(self.calls)

    def close(self):
        pass


@pytest.fixture
def dbx(monkeypatch):
    calls = []
    monkeypatch.setattr(query, "_connect", lambda **kwargs: FakeConnection(calls))
    monkeypatch.setenv("DATABRICKS_HOST", "https://dbc-123.cloud.databricks.com/")
    monkeypatch.setenv("DATABRICKS_TOKEN", "dapi-test")
    monkeypatch.setenv("DATABRICKS_WAREHOUSE_ID", "wh1")
    return calls


def _csv(tmp_path):
    path = tmp_path / "rows.csv"
    path.write_text("region,revenue\nEMEA,1.5\n", encoding="utf-8")
    return path


def _never_connect(**kwargs):
    raise AssertionError("must not contact Databricks")


def test_publisher_author_order(monkeypatch):
    monkeypatch.delenv("DATABRICKS_HOST", raising=False)
    monkeypatch.delenv("DATABRICKS_TOKEN", raising=False)
    monkeypatch.delenv("DATABRICKS_WAREHOUSE_ID", raising=False)
    s = Settings(storage="local", author="env@example.com")
    assert publisher_author(s) == "env@example.com"
    assert publisher_author(s, databricks_user="given@example.com") == "given@example.com"

    # Host and token without a warehouse: the login is not used, and nothing connects.
    monkeypatch.setenv("DATABRICKS_HOST", "https://dbc-123.cloud.databricks.com/")
    monkeypatch.setenv("DATABRICKS_TOKEN", "dapi-test")
    monkeypatch.setattr(query, "_connect", _never_connect)
    assert query.databricks_login_available() is False
    assert publisher_author(s) == "env@example.com"

    # A warehouse passed by the caller (the one a viz query chart ran on) completes the three.
    monkeypatch.setattr(query, "_connect", lambda **kwargs: FakeConnection([]))
    assert query.databricks_login_available("wh-from-source") is True
    assert publisher_author(s, warehouse_id="wh-from-source") == "dbx@example.com"

    # All three variables set.
    monkeypatch.setenv("DATABRICKS_WAREHOUSE_ID", "wh1")
    assert query.databricks_login_available() is True
    assert publisher_author(s) == "dbx@example.com"
    assert publisher_author(s, databricks_user="given@example.com") == "given@example.com"


def test_env_fixture_clears_databricks_variables(monkeypatch, request):
    monkeypatch.delenv("VIZ_INTEGRATION", raising=False)
    monkeypatch.setenv("DATABRICKS_HOST", "https://leak.example.com")
    monkeypatch.setenv("DATABRICKS_TOKEN", "dapi-leak")
    monkeypatch.setenv("DATABRICKS_WAREHOUSE_ID", "leak")
    request.getfixturevalue("env")
    for name in ("DATABRICKS_HOST", "DATABRICKS_TOKEN", "DATABRICKS_WAREHOUSE_ID"):
        assert name not in os.environ, f"unit tests must never see a real {name}"


def test_stage_stamps_and_validates_the_databricks_login(env, staging_root, dbx, tmp_path):
    assert main(["stage", "--from", str(_csv(tmp_path)), "--id", "sales/from-file"]) == 0
    chart_dir = staging_root / "charts" / "sales" / "from-file"
    assert json.loads((chart_dir / "chart.json").read_text(encoding="utf-8"))["author"] == "dbx@example.com"
    assert main(["validate", str(chart_dir)]) == 0


def test_new_dashboard_stamps_and_validates_the_databricks_login(env, staging_root, dbx):
    assert main(["new-dashboard", "sales/dbx-board", "--chart", "sales/revenue-by-region"]) == 0
    path = staging_root / "dashboards" / "sales" / "dbx-board.json"
    assert json.loads(path.read_text(encoding="utf-8"))["author"] == "dbx@example.com"
    assert main(["validate", str(path)]) == 0


def test_pull_dashboard_stamps_and_validates_the_databricks_login(env, staging_root, dbx):
    assert main(["pull-dashboard", "sales/overview"]) == 0
    path = staging_root / "dashboards" / "sales" / "overview.json"
    assert json.loads(path.read_text(encoding="utf-8"))["author"] == "dbx@example.com"
    assert main(["validate", str(path)]) == 0


def test_without_databricks_every_command_uses_viz_author(env, staging_root, tmp_path):
    assert main(["stage", "--from", str(_csv(tmp_path)), "--id", "sales/from-file"]) == 0
    chart = staging_root / "charts" / "sales" / "from-file" / "chart.json"
    assert json.loads(chart.read_text(encoding="utf-8"))["author"] == "tester@example.com"
    assert main(["new-dashboard", "sales/plain-board"]) == 0
    board = staging_root / "dashboards" / "sales" / "plain-board.json"
    assert json.loads(board.read_text(encoding="utf-8"))["author"] == "tester@example.com"


def test_without_a_warehouse_id_every_command_uses_viz_author(env, staging_root, dbx, monkeypatch, tmp_path):
    # DATABRICKS_HOST and DATABRICKS_TOKEN are set, DATABRICKS_WAREHOUSE_ID is not:
    # no command fails for want of a warehouse, and none contacts Databricks.
    monkeypatch.delenv("DATABRICKS_WAREHOUSE_ID")
    assert main(["stage", "--from", str(_csv(tmp_path)), "--id", "sales/from-file"]) == 0
    chart_dir = staging_root / "charts" / "sales" / "from-file"
    assert json.loads((chart_dir / "chart.json").read_text(encoding="utf-8"))["author"] == "tester@example.com"
    assert main(["validate", str(chart_dir)]) == 0
    assert main(["new-dashboard", "sales/plain-board", "--chart", "sales/revenue-by-region"]) == 0
    board = staging_root / "dashboards" / "sales" / "plain-board.json"
    assert json.loads(board.read_text(encoding="utf-8"))["author"] == "tester@example.com"
    assert main(["validate", str(board)]) == 0
    assert main(["pull-dashboard", "sales/overview"]) == 0
    assert dbx == [], "no Databricks connection without DATABRICKS_WAREHOUSE_ID"


def test_unreachable_databricks_during_stage_is_a_clean_error(env, staging_root, dbx, monkeypatch, tmp_path, capsys):
    def refuse(**kwargs):
        raise ConnectionError("warehouse unreachable")

    monkeypatch.setattr(query, "_connect", refuse)
    assert main(["stage", "--from", str(_csv(tmp_path)), "--id", "sales/from-file"]) == 2
    err = capsys.readouterr().err
    assert err.startswith("error: could not resolve the author identity:")
    assert "Traceback" not in err
    assert not (staging_root / "charts" / "sales" / "from-file").exists()


def test_identity_module_describes_author_as_attribution():
    assert "attribution" in identity.__doc__
    assert "not authentication" in identity.__doc__
```

In `tests/publish/test_validate_author.py`, replace the whole function `test_staged_file_chart_ignores_databricks` (it pinned the old rule) with:

```python
def test_staged_file_chart_is_stamped_and_confirmed_with_the_databricks_login(env, staging_root, dbx, tmp_path):
    csv = tmp_path / "rows.csv"
    csv.write_text("region,revenue\nEMEA,1.5\n", encoding="utf-8")
    assert main(["stage", "--from", str(csv), "--id", "sales/from-file"]) == 0
    chart_dir = staging_root / "charts" / "sales" / "from-file"
    assert json.loads((chart_dir / "chart.json").read_text(encoding="utf-8"))["author"] == "dbx@example.com"
    assert main(["validate", str(chart_dir)]) == 0
```

Append to the end of `tests/publish/test_validate_author.py`:

```python


def test_query_with_the_warehouse_flag_validates_without_the_variable(env, staging_root, dbx, monkeypatch, capsys):
    # The warehouse recorded in source.warehouse_id counts as the third variable.
    monkeypatch.delenv("DATABRICKS_WAREHOUSE_ID")
    assert main(["query", "--sql", SQL, "--warehouse", "wh1", "--id", "sales/by-region"]) == 0
    doc = json.loads((_chart_dir(staging_root) / "chart.json").read_text(encoding="utf-8"))
    assert doc["author"] == "dbx@example.com"
    assert doc["source"]["warehouse_id"] == "wh1"
    capsys.readouterr()
    assert main(["validate", str(_chart_dir(staging_root))]) == 0, capsys.readouterr().err


def test_databricks_login_available_needs_all_three(monkeypatch):
    monkeypatch.setenv("DATABRICKS_HOST", "https://x.example.com")
    monkeypatch.setenv("DATABRICKS_TOKEN", "dapi-test")
    monkeypatch.delenv("DATABRICKS_WAREHOUSE_ID", raising=False)
    assert query.databricks_login_available() is False
    assert query.databricks_login_available("wh1") is True
    monkeypatch.setenv("DATABRICKS_WAREHOUSE_ID", "wh1")
    assert query.databricks_login_available() is True
    monkeypatch.delenv("DATABRICKS_TOKEN")
    assert query.databricks_login_available() is False
```

- [ ] **Step 2: Run them to see them fail**

Run: `.venv/Scripts/python -m pytest tests/publish/test_author_resolver.py tests/publish/test_validate_author.py -v`
Expected: `tests/publish/test_author_resolver.py` fails to collect with `ImportError: cannot import name 'publisher_author'`; `test_staged_file_chart_is_stamped_and_confirmed_with_the_databricks_login` FAILS (the author is `tester@example.com`); `test_databricks_login_available_needs_all_three` FAILS with `AttributeError: module 'viz.publish.query' has no attribute 'databricks_login_available'`. `test_query_with_the_warehouse_flag_validates_without_the_variable` passes already (today's validate asks the chart's own warehouse); it guards the rewrite.

- [ ] **Step 3a: Add `databricks_login_available` to `viz/publish/query.py`**

In `viz/publish/query.py`, replace

```python
def databricks_configured() -> bool:
    """True when the variables `viz query` needs to reach Databricks are set."""
    return bool(os.environ.get("DATABRICKS_HOST")) and bool(os.environ.get("DATABRICKS_TOKEN"))
```

with

```python
def databricks_configured() -> bool:
    """True when the variables `viz query` needs to reach Databricks are set."""
    return bool(os.environ.get("DATABRICKS_HOST")) and bool(os.environ.get("DATABRICKS_TOKEN"))


def databricks_login_available(warehouse_id: str | None = None) -> bool:
    """True when the CLI stamps the Databricks login as `author` (finding A19):
    DATABRICKS_HOST, DATABRICKS_TOKEN and a warehouse are all set. The warehouse is
    warehouse_id when the caller has one (the warehouse a `viz query` chart ran on),
    else DATABRICKS_WAREHOUSE_ID. Makes no connection."""
    return databricks_configured() and bool(warehouse_id or os.environ.get("DATABRICKS_WAREHOUSE_ID"))
```

- [ ] **Step 3b: Rewrite `viz/publish/identity.py`**

Replace the whole file with:

```python
"""Who published a chart or dashboard, for attribution. `author` tells readers whom to
ask about a chart; it is attribution, not authentication, and it grants nothing.
The CLI stamps it, and `viz validate` checks that the stamped value equals what the
CLI would stamp now, so a hand-typed author is caught as a mistake."""
import getpass

from ..config import Settings
from .query import current_user, databricks_login_available


def resolve_author(settings: Settings, databricks_user: str | None = None) -> str:
    if databricks_user:
        return databricks_user
    if settings.author:
        return settings.author
    if settings.storage == "s3":
        import boto3  # local import keeps the local path free of AWS calls

        return boto3.client("sts").get_caller_identity()["Arn"]
    return f"{getpass.getuser()}@local"


def publisher_author(settings: Settings, databricks_user: str | None = None,
                     warehouse_id: str | None = None) -> str:
    """The one author rule for every command that stamps a document (query, stage,
    new-dashboard, pull-dashboard) and for `viz validate` (finding A19):
    1. databricks_user, when the caller already read the login (`viz query` does);
    2. the Databricks login, when DATABRICKS_HOST, DATABRICKS_TOKEN and a warehouse
       (warehouse_id, else DATABRICKS_WAREHOUSE_ID) are all set;
    3. otherwise resolve_author: VIZ_AUTHOR, then the AWS caller identity, then <user>@local.
    No command needs DATABRICKS_WAREHOUSE_ID: without it, rule 3 applies.
    Raises QueryError when Databricks is configured but cannot be reached."""
    if databricks_user:
        return databricks_user
    if databricks_login_available(warehouse_id):
        return current_user(warehouse_id)
    return resolve_author(settings)


def author_errors(doc: dict, expected: str) -> list[str]:
    actual = doc.get("author")
    if actual is None:
        return [f"author is missing; the CLI stamps it as '{expected}'"]
    if actual != expected:
        return [f"author '{actual}' does not match the resolved identity '{expected}'"]
    return []


def check_author(doc: dict, settings: Settings, databricks_user: str | None = None) -> list[str]:
    return author_errors(doc, resolve_author(settings, databricks_user))
```

- [ ] **Step 4: Use it in `viz/publish/validate.py`**

Replace

```python
from .identity import check_author
from .query import QueryError, current_user, databricks_configured
```

with

```python
from .identity import author_errors, publisher_author
from .query import QueryError
```

Replace the whole function `_check_chart_author` (from `def _check_chart_author(doc: dict, settings: Settings) -> list[str]:` to its last line `return check_author(doc, settings, databricks_user=user)`) with:

```python
def _source_warehouse(doc: dict) -> str | None:
    """The warehouse a `viz query` chart ran on, so validation asks the same warehouse."""
    source = doc.get("source") or {}
    return source.get("warehouse_id") if source.get("kind") == "databricks-sql" else None


def _check_stamped_author(doc: dict, settings: Settings, warehouse_id: str | None = None) -> list[str]:
    """The author must equal what the CLI stamps now (publisher_author). Attribution only."""
    try:
        expected = publisher_author(settings, warehouse_id=warehouse_id)
    except QueryError as err:
        return [f"author: could not confirm the Databricks user: {err}"]
    except Exception as err:  # the AWS caller identity lookup can fail too
        return [f"author: could not resolve the author: {err}"]
    return author_errors(doc, expected)
```

In `validate_staged_chart`, replace

```python
    errors += _check_chart_author(doc, settings)
```

with

```python
    errors += _check_stamped_author(doc, settings, _source_warehouse(doc))
```

In `validate_dashboard_file`, replace

```python
    errors += check_author(doc, settings)
```

with

```python
    errors += _check_stamped_author(doc, settings)
```

If any anchor text is not found, read the file, find the equivalent code, and apply the same change; report the difference.

- [ ] **Step 5: Use it in `viz/publish/cli.py` and `viz/publish/__init__.py`**

In `viz/publish/cli.py`, replace

```python
from .identity import resolve_author
```

with

```python
from .identity import publisher_author
```

Replace the whole function `_resolve_author` with:

```python
def _resolve_author(settings: Settings, databricks_user: str | None = None) -> str:
    """publisher_author() can reach Databricks, AWS or the local user database; any
    failure there is an environment problem, not a crash."""
    try:
        return publisher_author(settings, databricks_user=databricks_user)
    except Exception as err:
        raise CliError(f"could not resolve the author identity: {err}", code=2) from err
```

In `_cmd_query`, replace

```python
    return _stage_table(table, args.id, settings, args, author=user, source=source)
```

with

```python
    return _stage_table(table, args.id, settings, args, author=_resolve_author(settings, databricks_user=user),
                        source=source)
```

In `viz/publish/__init__.py`, replace

```python
    from .identity import resolve_author
```

with

```python
    from .identity import publisher_author
```

and replace

```python
        author = resolve_author(settings)
```

with

```python
        author = publisher_author(settings)
```

- [ ] **Step 6: Keep real Databricks variables away from the unit tests**

In `tests/publish/conftest.py`, replace

```python
import shutil
from pathlib import Path
```

with

```python
import os
import shutil
from pathlib import Path
```

In the `env` fixture, directly below the loop that starts `for name in ("VIZ_QUERY_DENY",` and its `monkeypatch.delenv(name, raising=False)` line, add (at the same indentation as that `for`):

```python
    if os.environ.get("VIZ_INTEGRATION") != "1":
        # A developer machine may have real Databricks variables. Unit tests must never reach Databricks.
        # With VIZ_INTEGRATION=1 they are kept, so run integration tests one file at a time
        # (docs/work-setup.md, step 6), never the whole suite.
        for name in ("DATABRICKS_HOST", "DATABRICKS_TOKEN", "DATABRICKS_WAREHOUSE_ID"):
            monkeypatch.delenv(name, raising=False)
```

- [ ] **Step 7: Run the tests**

Run: `.venv/Scripts/python -m pytest tests/publish/test_author_resolver.py tests/publish/test_validate_author.py tests/publish/test_identity.py tests/publish/test_dashboards.py tests/publish/test_query.py tests/publish/test_cli_errors.py -v`
Expected: all pass.

- [ ] **Step 8: Update the skill, README and setup guide**

In `skills/publish-viz/SKILL.md`, replace

```markdown
3. `viz query` stamps charts with the Databricks login. When
   `DATABRICKS_HOST` and `DATABRICKS_TOKEN` are set, `viz validate` asks
   Databricks for the current user and accepts that login. Without them it
   checks `VIZ_AUTHOR` instead, so ask the user to set `VIZ_AUTHOR` to their
   Databricks login email. If validation says
   `author '<a>' does not match the resolved identity '<b>'`, show the user
   both values and ask which identity is right. Never edit `author` by hand.
```

with

```markdown
3. The CLI stamps `author` on every chart and dashboard. It records who
   published (attribution); it is not a permission check. When
   `DATABRICKS_HOST`, `DATABRICKS_TOKEN` and `DATABRICKS_WAREHOUSE_ID` are
   all set, `author` is the Databricks login for every command. Otherwise
   the CLI uses `VIZ_AUTHOR`, so ask the user to set `VIZ_AUTHOR` to their
   Databricks login email. If validation says
   `author '<a>' does not match the resolved identity '<b>'`, show the user
   both values and ask which one is right. Never edit `author` by hand.
```

In `README.md`, replace

```markdown
else in the package reads them. Publisher settings: `VIZ_AUTHOR` (overrides the
AWS caller identity when set; the Databricks user from `viz query` always wins,
and `viz validate` confirms it with Databricks when the `DATABRICKS_*` variables
are set; author is attribution, not authentication), `VIZ_QUERY_DENY` (comma-separated
```

with

```markdown
else in the package reads them. Publisher settings: `VIZ_AUTHOR` (used unless
`DATABRICKS_HOST`, `DATABRICKS_TOKEN` and `DATABRICKS_WAREHOUSE_ID` are all set;
with all three, every command stamps the Databricks login and `viz validate`
confirms it; without `VIZ_AUTHOR` the AWS caller identity is the fallback;
author is attribution, not authentication), `VIZ_QUERY_DENY` (comma-separated
```

In `docs/work-setup.md`, replace

```markdown
Author: `viz query` stamps charts with your Databricks login, and
`viz validate` confirms it with Databricks. Charts staged from files use
`VIZ_AUTHOR`, then your AWS identity, then `<user>@local`.

When you publish files (not `viz query`), set `VIZ_AUTHOR` to your email, or
```

with

```markdown
Author (attribution, not a permission check): when `DATABRICKS_HOST`,
`DATABRICKS_TOKEN` and `DATABRICKS_WAREHOUSE_ID` are all set, every command
(`viz query`, `viz stage`, `viz new-dashboard`, `viz pull-dashboard`) stamps
your Databricks login and `viz validate` confirms it with Databricks. A chart
from `viz query --warehouse <id>` also counts: validation asks the warehouse
the query ran on. Otherwise the CLI uses `VIZ_AUTHOR`, then your AWS identity,
then `<user>@local`; no command requires `DATABRICKS_WAREHOUSE_ID`.

Without all three Databricks variables, set `VIZ_AUTHOR` to your email, or
```

and replace

```markdown
| `viz validate` says the author does not match (Databricks) | Without `DATABRICKS_HOST` and `DATABRICKS_TOKEN`, set `VIZ_AUTHOR` to your Databricks login |
| `viz validate` says the author does not match (file-staged charts) |
```

with

```markdown
| `viz validate` says the author does not match (Databricks) | The CLI uses the Databricks login only when `DATABRICKS_HOST`, `DATABRICKS_TOKEN` and `DATABRICKS_WAREHOUSE_ID` are all set. Set all three, or set `VIZ_AUTHOR` to your Databricks login |
| `viz validate` says the author does not match (not all Databricks variables set) |
```

(the first row is replaced whole; in the second row only the text of the first cell changes; keep the rest of that row as it is).

If any of these anchors is not found, read the file, find the paragraph that describes the same thing, and rewrite it to say the same as the new text; report the difference.

- [ ] **Step 9: Run the whole suite and commit**

Run: `.venv/Scripts/python -m pytest`

```bash
git add viz/publish/query.py viz/publish/identity.py viz/publish/validate.py viz/publish/cli.py viz/publish/__init__.py tests/publish/conftest.py tests/publish/test_author_resolver.py tests/publish/test_validate_author.py skills/publish-viz/SKILL.md README.md docs/work-setup.md
git -c user.name="tripp" -c user.email="dom4domg@gmail.com" commit -m "fix: one author rule for query, stage and the dashboard commands" -m "Co-Authored-By: <model name from your harness> <noreply@anthropic.com>
Claude-Session: <session url from your harness>"
```

---

### Task 6: Republishing keeps `created_at` (A20)

**Files:**
- Modify: `viz/publish/publish.py`
- Create: `tests/publish/test_created_at.py`

**Interfaces:**
- Consumes: plan 5a's `_guard_overwrite(storage, key, force, out) -> tuple[dict | None, str | None]` (the published document it read, or None, and its ETag). No second read of the bucket.
- Produces: `viz.publish.publish.keep_created_at(existing: dict | None, staged_file: Path) -> None`: when `existing` (the published document the overwrite guard read) has a `created_at` matching `^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$`, rewrites the staged file with that `created_at` (JSON, `indent=2`, trailing newline, LF). Called by `publish_chart` and `publish_dashboard` directly after the overwrite guard and before the document bytes are read for upload. The conditional PUT still uses the ETag of that same read, so a change between the read and the PUT is refused.

- [ ] **Step 1: Write the failing tests**

Create `tests/publish/test_created_at.py`:

```python
"""Republishing an id keeps the created_at of the first publish (finding A20)."""
import json
from datetime import date, datetime, timezone

import pyarrow as pa

from viz.publish.publish import publish_chart, publish_dashboard
from viz.publish.staging import write_staged_chart

FIRST = datetime(2026, 9, 1, 8, 0, 0, tzinfo=timezone.utc)
SECOND = datetime(2026, 9, 29, 9, 30, 0, tzinfo=timezone.utc)
KEY = "viz/charts/sales/kept/chart.json"
BOARD_KEY = "viz/dashboards/sales/kept-board.json"


def _stage(staging_root, now):
    table = pa.table({"month": [date(2024, 1, 1), date(2024, 2, 1)], "revenue": [1.5, 2.5]})
    return write_staged_chart(table, "sales/kept", staging_root, author="tester@example.com", now=now)


def _board(staging_root, stamp):
    path = staging_root / "dashboards" / "sales" / "kept-board.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({
        "schema_version": 1, "id": "sales/kept-board", "title": "Kept", "author": "tester@example.com",
        "created_at": stamp, "updated_at": stamp,
        "layout": [{"chart": "sales/revenue-by-region", "w": 12, "h": 4}],
    }), encoding="utf-8")
    return path


def test_republish_keeps_the_first_created_at(settings, storage, staging_root):
    publish_chart(_stage(staging_root, FIRST).dir, settings, storage)
    staged = _stage(staging_root, SECOND)
    publish_chart(staged.dir, settings, storage, force=True)
    doc = json.loads(storage.get(KEY))
    assert doc["created_at"] == "2026-09-01T08:00:00Z"
    assert doc["updated_at"] == "2026-09-29T09:30:00Z"
    assert storage.get(KEY) == staged.chart_path.read_bytes(), "the bucket holds exactly the staged bytes"


def test_first_publish_leaves_the_staged_file_alone(settings, storage, staging_root):
    staged = _stage(staging_root, SECOND)
    before = staged.chart_path.read_bytes()
    publish_chart(staged.dir, settings, storage)
    assert staged.chart_path.read_bytes() == before
    assert json.loads(storage.get(KEY))["created_at"] == "2026-09-29T09:30:00Z"


def test_republish_ignores_a_malformed_created_at(settings, storage, staging_root):
    publish_chart(_stage(staging_root, FIRST).dir, settings, storage)
    doc = json.loads(storage.get(KEY))
    doc["created_at"] = "<img src=x onerror=alert(1)>"
    storage.put(KEY, json.dumps(doc).encode("utf-8"), "application/json")
    publish_chart(_stage(staging_root, SECOND).dir, settings, storage, force=True)
    assert json.loads(storage.get(KEY))["created_at"] == "2026-09-29T09:30:00Z"


def test_dashboard_republish_keeps_the_first_created_at(settings, storage, staging_root):
    publish_dashboard(_board(staging_root, "2026-09-01T08:00:00Z"), settings, storage)
    path = _board(staging_root, "2026-09-29T09:30:00Z")
    publish_dashboard(path, settings, storage, force=True)
    doc = json.loads(storage.get(BOARD_KEY))
    assert doc["created_at"] == "2026-09-01T08:00:00Z"
    assert doc["updated_at"] == "2026-09-29T09:30:00Z"
    assert storage.get(BOARD_KEY) == path.read_bytes()
```

- [ ] **Step 2: Run them to see them fail**

Run: `.venv/Scripts/python -m pytest tests/publish/test_created_at.py -v`
Expected: `test_republish_keeps_the_first_created_at` and `test_dashboard_republish_keeps_the_first_created_at` FAIL (`created_at` is `2026-09-29T09:30:00Z`); the other two pass already.

- [ ] **Step 3: Add `keep_created_at` to `viz/publish/publish.py`**

Add `import re` to the imports at the top of the file (next to `import json`).

Add this block directly above `def publish_chart(`:

```python
CREATED_AT_PATTERN = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$")


def keep_created_at(existing: dict | None, staged_file: Path) -> None:
    """Republishing an id keeps the created_at of the published document (finding A20).
    `existing` is the document the overwrite guard read (None for a new id). The staged
    file is rewritten before the upload, so the bytes in the bucket still equal the staged
    file byte for byte. The published value is untrusted: it is copied only when it is a
    plain UTC timestamp such as 2026-09-29T10:00:00Z."""
    if not isinstance(existing, dict):
        return
    created = existing.get("created_at")
    if not isinstance(created, str) or not CREATED_AT_PATTERN.fullmatch(created):
        return
    staged_file = Path(staged_file)
    doc = json.loads(staged_file.read_text(encoding="utf-8"))
    if doc.get("created_at") == created:
        return
    doc["created_at"] = created
    tmp = staged_file.with_name(staged_file.name + ".tmp")
    tmp.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    tmp.replace(staged_file)
```

- [ ] **Step 4: Call it in `publish_chart` and `publish_dashboard`**

In `publish_chart`, replace

```python
    existing, etag = _guard_overwrite(storage, key, force, out)

    storage.put(data_key(root, chart_id, file_name), (chart_dir / file_name).read_bytes(), MEDIA_TYPES[fmt])
```

with

```python
    existing, etag = _guard_overwrite(storage, key, force, out)
    keep_created_at(existing, chart_dir / "chart.json")

    storage.put(data_key(root, chart_id, file_name), (chart_dir / file_name).read_bytes(), MEDIA_TYPES[fmt])
```

The chart.json bytes are read below this line, inside `_commit(storage, key, (chart_dir / "chart.json").read_bytes(), chart_id, etag)`, so the upload carries the kept `created_at`. Leave that line as it is.

In `publish_dashboard`, replace

```python
    _existing_doc, etag = _guard_overwrite(storage, key, force, out)
```

with

```python
    existing, etag = _guard_overwrite(storage, key, force, out)
    keep_created_at(existing, path)
```

The dashboard bytes are read below it, inside `_commit(storage, key, path.read_bytes(), dashboard_id, etag)`. Leave that line as it is.

If an anchor is not found (Task 0 reported the exact lines), read the file, find the overwrite-guard call, and add the `keep_created_at(...)` line directly below it; report the difference.

- [ ] **Step 5: Run the tests**

Run: `.venv/Scripts/python -m pytest tests/publish/test_created_at.py tests/publish/test_publish.py tests/publish/test_end_to_end.py -v`
Expected: all pass.

- [ ] **Step 6: Run the whole suite and commit**

Run: `.venv/Scripts/python -m pytest`

```bash
git add viz/publish/publish.py tests/publish/test_created_at.py
git -c user.name="tripp" -c user.email="dom4domg@gmail.com" commit -m "fix: republishing an id keeps its created_at" -m "Co-Authored-By: <model name from your harness> <noreply@anthropic.com>
Claude-Session: <session url from your harness>"
```

---

### Task 7: Tighter PII column pattern (A21)

**Files:**
- Modify: `viz/config.py`, `tests/publish/test_pii.py`

**Interfaces:**
- Consumes: `viz.publish.pii.pii_columns(columns, pattern)`.
- Produces: the new default `Settings.pii_pattern`. `name` matches the whole column name `name`, or a person word followed by `name` with an optional underscore (`first_name`, `customer_name`, `surname`, `username`), where the person word starts the column or follows an underscore. `product_name`, `region_name`, `campaign_name`, `report_name`, `filename`, `hostname` do not match.

- [ ] **Step 1: Write the failing test**

Append to `tests/publish/test_pii.py`:

```python


def test_name_matches_person_names_only():
    not_pii = ["product_name", "region_name", "campaign_name", "report_name", "filename", "hostname"]
    pii = ["name", "Name", "first_name", "last_name", "full_name", "firstname", "surname",
           "customer_name", "customer_first_name", "sales_rep_name", "username", "display_name",
           "email", "phone", "ssn"]
    assert pii_columns(not_pii + pii, DEFAULT) == pii
```

- [ ] **Step 2: Run it to see it fail**

Run: `.venv/Scripts/python -m pytest tests/publish/test_pii.py -v`
Expected: `test_name_matches_person_names_only` FAILS (the result starts with `product_name`, `region_name`, ...).

- [ ] **Step 3: Change the default in `viz/config.py`**

Replace

```python
    pii_pattern: str = r"(?i)(email|ssn|phone|name|address|dob|salary|\bip\b)"
```

with

```python
    # Column names that look like personal data. "name" matches alone, or after a person
    # word such as first_ or customer_; product_name and region_name do not (finding A21).
    pii_pattern: str = (
        r"(?i)(email|ssn|phone|address|dob|salary|\bip\b|^name$"
        r"|(?<![a-z0-9])(first|last|full|given|family|middle|maiden|nick|sur|user|customer|client|contact"
        r"|person|employee|manager|owner|member|patient|student|agent|rep|display)_?name(?![a-z0-9]))"
    )
```

If this anchor text is not found, read the file, find the `pii_pattern` field, and apply the same change; report the difference.

- [ ] **Step 4: Run the tests**

Run: `.venv/Scripts/python -m pytest tests/publish/test_pii.py tests/publish/test_cli_stage.py tests/publish/test_query.py tests/test_config.py -v`
Expected: all pass. The older tests in `test_pii.py` (`full_name`, `name`, `ip_address`, `ip`) still pass unchanged.

- [ ] **Step 5: Run the whole suite and commit**

Run: `.venv/Scripts/python -m pytest`

```bash
git add viz/config.py tests/publish/test_pii.py
git -c user.name="tripp" -c user.email="dom4domg@gmail.com" commit -m "fix: PII warning no longer flags product_name and region_name" -m "Co-Authored-By: <model name from your harness> <noreply@anthropic.com>
Claude-Session: <session url from your harness>"
```

---

### Task 8: Refuse the placeholder aggregate (A22); the data guide names content-addressed files

**Files:**
- Modify: `viz/publish/validate.py`, `tests/publish/test_validate.py`, `tests/publish/test_publish.py`, `skills/publish-viz/references/data.md`, `tests/test_skill.py`
- Create: `tests/publish/test_placeholder_aggregate.py`

**Interfaces:**
- Consumes: `viz.publish.staging.LARGE_DEFAULT_AGGREGATE` (`"SELECT * FROM data LIMIT 1000"`).
- Produces:
  - `viz.publish.validate.is_placeholder_aggregate(aggregate: str) -> bool`: true when the text equals the placeholder after collapsing whitespace, dropping a trailing `;` and ignoring case.
  - `viz.publish.validate.PLACEHOLDER_ERROR`: `aggregate: still the staging placeholder 'SELECT * FROM data LIMIT 1000'; replace it with a SELECT that summarizes the rows for this chart`.
  - `validate_staged_chart` adds `PLACEHOLDER_ERROR` for a large-lane chart whose aggregate is the placeholder, before the row-level error, with or without `--allow-row-level`.

- [ ] **Step 1: Write the failing tests**

Create `tests/publish/test_placeholder_aggregate.py`:

```python
"""A large-lane chart cannot be published with the placeholder aggregate (finding A22)."""
import json
from datetime import date, datetime, timezone

import pyarrow as pa
import pytest

from viz.publish import staging
from viz.publish.cli import main
from viz.publish.staging import write_staged_chart
from viz.publish.validate import PLACEHOLDER_ERROR, is_placeholder_aggregate, validate_staged_chart

NOW = datetime(2026, 9, 22, 10, 0, 0, tzinfo=timezone.utc)
REAL = "SELECT month, sum(revenue) AS revenue FROM data GROUP BY month ORDER BY month"


def _large(staging_root, monkeypatch, chart_id="sales/large"):
    monkeypatch.setattr(staging, "SMALL_MAX_ROWS", 0)
    table = pa.table({"month": [date(2024, 1, 1), date(2024, 2, 1)], "revenue": [1.5, 2.5]})
    return write_staged_chart(table, chart_id, staging_root, author="tester@example.com", now=NOW)


def _set_aggregate(staged, aggregate):
    doc = json.loads(staged.chart_path.read_text(encoding="utf-8"))
    doc["aggregate"] = aggregate
    staged.chart_path.write_text(json.dumps(doc), encoding="utf-8")


@pytest.mark.parametrize("text", [
    "SELECT * FROM data LIMIT 1000",
    "select * from data limit 1000",
    "SELECT *  FROM data\nLIMIT 1000;",
    "  SELECT * FROM data LIMIT 1000  ",
])
def test_placeholder_variants(text):
    assert is_placeholder_aggregate(text)


def test_a_real_aggregate_is_not_the_placeholder():
    assert not is_placeholder_aggregate(REAL)
    assert not is_placeholder_aggregate("SELECT * FROM data LIMIT 100")


def test_validate_refuses_the_placeholder(settings, storage, staging_root, monkeypatch):
    staged = _large(staging_root, monkeypatch)
    assert validate_staged_chart(staged.dir, settings, storage, allow_row_level=True) == [PLACEHOLDER_ERROR]
    _set_aggregate(staged, REAL)
    assert validate_staged_chart(staged.dir, settings, storage, allow_row_level=True) == []


def test_publish_command_refuses_the_placeholder(env, staging_root, monkeypatch, capsys):
    staged = _large(staging_root, monkeypatch)
    assert main(["publish", str(staged.dir), "--allow-row-level"]) == 1
    assert "still the staging placeholder" in capsys.readouterr().err
```

Append to `tests/test_skill.py` (plan 5a made data files content-addressed; the data guide still named `data.json` and `data.parquet`):

```python


def test_data_guide_names_content_addressed_data_files():
    data = _text(SKILL / "references" / "data.md")
    assert "`data.json`" not in data
    assert "`data.parquet`" not in data
    assert "data.<hash>.json" in data
    assert "Never rename or edit the data file" in data
```

- [ ] **Step 2: Run them to see them fail**

Run: `.venv/Scripts/python -m pytest tests/publish/test_placeholder_aggregate.py tests/test_skill.py -v`
Expected: `tests/publish/test_placeholder_aggregate.py` fails to collect with `ImportError: cannot import name 'PLACEHOLDER_ERROR'`; `test_data_guide_names_content_addressed_data_files` FAILS.

- [ ] **Step 3: Add the check to `viz/publish/validate.py`**

Add `LARGE_DEFAULT_AGGREGATE` to the names imported from `.staging`. After plan 5a the line is

```python
from .staging import LARGE_MAX_BYTES, SMALL_MAX_BYTES, SMALL_MAX_ROWS, file_sha256
```

and it becomes

```python
from .staging import LARGE_DEFAULT_AGGREGATE, LARGE_MAX_BYTES, SMALL_MAX_BYTES, SMALL_MAX_ROWS, file_sha256
```

Add this block directly above `def check_aggregate(`:

```python
PLACEHOLDER_ERROR = (
    f"aggregate: still the staging placeholder '{LARGE_DEFAULT_AGGREGATE}'; "
    "replace it with a SELECT that summarizes the rows for this chart"
)


def is_placeholder_aggregate(aggregate: str) -> bool:
    """True for the aggregate staging writes, ignoring case, spacing and a trailing semicolon."""
    normalized = " ".join(aggregate.split()).rstrip(";").strip().lower()
    return normalized == LARGE_DEFAULT_AGGREGATE.lower()
```

In `validate_staged_chart`, replace

```python
    if lane == "large":
        if not allow_row_level:
```

with

```python
    if lane == "large":
        if is_placeholder_aggregate(doc["aggregate"]):
            errors.append(PLACEHOLDER_ERROR)
        if not allow_row_level:
```

If this anchor text is not found, read the file, find the large-lane block at the end of `validate_staged_chart`, and add the same two lines as its first statement; report the difference.

- [ ] **Step 4: Update the tests that published the placeholder**

In `tests/publish/test_validate.py`, add `PLACEHOLDER_ERROR` to the names imported from `viz.publish.validate`. Today:

```python
from viz.publish.validate import (
    check_aggregate, conflicting_ids, validate_dashboard_file, validate_staged_chart,
)
```

becomes

```python
from viz.publish.validate import (
    PLACEHOLDER_ERROR, check_aggregate, conflicting_ids, validate_dashboard_file, validate_staged_chart,
)
```

In the same file, replace

```python
    assert validate_staged_chart(staged.dir, settings, storage) == [
        "large lane publishes row-level data; ask the user before passing --allow-row-level to confirm"
    ]
    assert validate_staged_chart(staged.dir, settings, storage, allow_row_level=True) == []
```

with

```python
    assert validate_staged_chart(staged.dir, settings, storage) == [
        PLACEHOLDER_ERROR,
        "large lane publishes row-level data; ask the user before passing --allow-row-level to confirm",
    ]
    assert validate_staged_chart(staged.dir, settings, storage, allow_row_level=True) == [PLACEHOLDER_ERROR]
```

In `tests/publish/test_publish.py`, in `test_publish_command_large_lane_needs_flag`, replace

```python
    assert main(["publish", str(staged.dir), "--allow-row-level"]) == 0
```

with

```python
    doc = json.loads(staged.chart_path.read_text(encoding="utf-8"))
    doc["aggregate"] = "SELECT month, sum(revenue) AS revenue FROM data GROUP BY month"
    staged.chart_path.write_text(json.dumps(doc), encoding="utf-8")
    assert main(["publish", str(staged.dir), "--allow-row-level"]) == 0
```

(Plan 5a replaced `test_publish_removes_stale_data_of_the_other_format` with `test_publish_removes_legacy_data_files`, which publishes a small-lane chart, so it needs no change.)

- [ ] **Step 5: Run the tests**

Run: `.venv/Scripts/python -m pytest tests/publish/test_placeholder_aggregate.py tests/publish/test_validate.py tests/publish/test_publish.py -v`
Expected: all pass.

- [ ] **Step 6: Update `references/data.md`**

In `skills/publish-viz/references/data.md`, replace

```markdown
`"aggregate"` key of `chart.json`. Staging fills it with the placeholder
`SELECT * FROM data LIMIT 1000`, which draws 1,000 arbitrary rows; always
replace it. Example:
```

with

```markdown
`"aggregate"` key of `chart.json`. Staging fills it with the placeholder
`SELECT * FROM data LIMIT 1000`, which draws 1,000 arbitrary rows.
`viz validate` refuses a chart whose `aggregate` is still this placeholder,
so always replace it. Example:
```

In the same file, replace

```markdown
| small | `data.json` | 100,000 rows and 20 MB | Almost always. Filters run in the browser. |
| large | `data.parquet` | 200 MB | Only when viewers must filter row-level data that the warehouse cannot pre-aggregate. |
```

with

```markdown
| small | `data.<hash>.json` | 100,000 rows and 20 MB | Almost always. Filters run in the browser. |
| large | `data.<hash>.parquet` | 200 MB | Only when viewers must filter row-level data that the warehouse cannot pre-aggregate. |

`<hash>` is the first 16 hex characters of the file's SHA-256, and
`chart.json` names the file in `data.file`. Never rename or edit the data file
by hand: `viz validate` refuses a file whose name does not match its bytes.
To change the data, run `viz query` or `viz stage` again.
```

Run: `.venv/Scripts/python -m pytest tests/publish/test_placeholder_aggregate.py tests/test_skill.py -v`
Expected: all pass.

- [ ] **Step 7: Run the whole suite and commit**

Run: `.venv/Scripts/python -m pytest`
If another test fails with `still the staging placeholder`, it stages a large-lane chart and expects it to validate or publish: add the three `doc["aggregate"] = ...` lines from Step 4 right after the line that stages it, and report the test name. Change nothing else in it.

```bash
git add viz/publish/validate.py tests/publish/test_placeholder_aggregate.py tests/publish/test_validate.py tests/publish/test_publish.py skills/publish-viz/references/data.md tests/test_skill.py
git -c user.name="tripp" -c user.email="dom4domg@gmail.com" commit -m "fix: validate refuses the placeholder large-lane aggregate" -m "Co-Authored-By: <model name from your harness> <noreply@anthropic.com>
Claude-Session: <session url from your harness>"
```

---

### Task 9: `viz preview` refuses a public host without `--allowed-hosts` (A23)

**Files:**
- Modify: `viz/publish/preview.py`, `viz/publish/cli.py`, `tests/publish/test_preview.py`

**Interfaces:**
- Consumes: `viz.config.Settings`, `viz.server.app.create_app`.
- Produces:
  - `viz.publish.preview.PreviewError(ValueError)`.
  - `preview_settings(staging_root, host="127.0.0.1", port=8000, allowed_hosts: str | None = None)`: `allowed_hosts` when given; else `localhost,127.0.0.1` for a loopback host; else raises `PreviewError` whose text contains `ask the user before passing --allowed-hosts`.
  - `build_preview_app(staging_root, host, port, allowed_hosts=None)`, `run_preview(staging_root, host, port, allowed_hosts=None)`.
  - `viz preview --allowed-hosts HOSTS`; a `PreviewError` becomes exit code 2.

- [ ] **Step 1: Write the failing tests**

In `tests/publish/test_preview.py`, replace

```python
from datetime import date, datetime, timezone
from pathlib import Path

import pyarrow as pa
from fastapi.testclient import TestClient

import viz.publish.cli as cli
from viz.publish.cli import main
from viz.publish.preview import build_preview_app, preview_settings
```

with

```python
from datetime import date, datetime, timezone
from pathlib import Path

import pyarrow as pa
import pytest
from fastapi.testclient import TestClient

import viz.publish.cli as cli
import viz.publish.preview as preview_mod
from viz.publish.cli import main
from viz.publish.preview import PreviewError, build_preview_app, preview_settings
```

Replace

```python
    assert preview_settings(staging_root, host="0.0.0.0").allowed_hosts_list == ["*"]
```

with

```python
    assert preview_settings(staging_root, host="0.0.0.0", allowed_hosts="a.example.com").allowed_hosts_list == ["a.example.com"]
```

Replace

```python
    monkeypatch.setattr(cli, "run_preview", lambda root, host, port: calls.append((Path(root), host, port)))
    assert main(["preview"]) == 0
    assert calls == [(staging_root, "127.0.0.1", 8000)]

    calls.clear()
    assert main(["preview", "--host", "0.0.0.0", "--port", "9000", "--staging", str(staging_root / "other")]) == 0
    assert calls == [(staging_root / "other", "0.0.0.0", 9000)]
```

with

```python
    monkeypatch.setattr(cli, "run_preview",
                        lambda root, host, port, allowed_hosts: calls.append((Path(root), host, port, allowed_hosts)))
    assert main(["preview"]) == 0
    assert calls == [(staging_root, "127.0.0.1", 8000, None)]

    calls.clear()
    assert main(["preview", "--host", "0.0.0.0", "--allowed-hosts", "a.example.com", "--port", "9000",
                 "--staging", str(staging_root / "other")]) == 0
    assert calls == [(staging_root / "other", "0.0.0.0", 9000, "a.example.com")]
```

Append to the end of the file:

```python


def test_preview_refuses_a_non_loopback_host_without_allowed_hosts(staging_root):
    with pytest.raises(PreviewError, match="ask the user before passing --allowed-hosts"):
        preview_settings(staging_root, host="0.0.0.0")
    assert preview_settings(staging_root, host="localhost").allowed_hosts_list == ["localhost", "127.0.0.1"]
    # An explicit "*" is accepted: passing --allowed-hosts is the consent.
    assert preview_settings(staging_root, host="0.0.0.0", allowed_hosts="*").allowed_hosts_list == ["*"]


def test_preview_command_refuses_a_non_loopback_host(env, staging_root, monkeypatch, capsys):
    calls = []
    monkeypatch.setattr(preview_mod.uvicorn, "run", lambda app, host, port: calls.append((host, port)))
    assert main(["preview", "--host", "0.0.0.0"]) == 2
    assert "--allowed-hosts" in capsys.readouterr().err
    assert calls == []
    assert main(["preview", "--host", "0.0.0.0", "--allowed-hosts", "viz-preview.example.com"]) == 0
    assert calls == [("0.0.0.0", 8000)]
```

Plan 5a changed only `test_preview_app_rejects_foreign_host` in this file (it now requests `/api/tree`), so the anchors above are unchanged. If one is not found, apply the same change to the equivalent line; report the difference.

- [ ] **Step 2: Run them to see them fail**

Run: `.venv/Scripts/python -m pytest tests/publish/test_preview.py -v`
Expected: the file fails to collect with `ImportError: cannot import name 'PreviewError'`.

- [ ] **Step 3: Change `viz/publish/preview.py`**

Replace

```python
LOOPBACK = ("127.0.0.1", "localhost", "::1")
```

with

```python
LOOPBACK = ("127.0.0.1", "localhost", "::1")
LOOPBACK_ALLOWED_HOSTS = "localhost,127.0.0.1"


class PreviewError(ValueError):
    pass


def _allowed_hosts(host: str, allowed_hosts: str | None) -> str:
    """A host other than loopback shows staged, unpublished data to the network, so it
    needs an explicit Host allow-list (finding A23)."""
    if allowed_hosts:
        return allowed_hosts
    if host in LOOPBACK:
        return LOOPBACK_ALLOWED_HOSTS
    raise PreviewError(
        f"--host {host} makes the preview reachable from other machines; "
        "ask the user before passing --allowed-hosts with the host names viewers will use"
    )
```

Replace

```python
def preview_settings(staging_root: Path, host: str = "127.0.0.1", port: int = 8000) -> Settings:
    allowed = "localhost,127.0.0.1" if host in LOOPBACK else "*"
```

with

```python
def preview_settings(staging_root: Path, host: str = "127.0.0.1", port: int = 8000,
                     allowed_hosts: str | None = None) -> Settings:
    allowed = _allowed_hosts(host, allowed_hosts)
```

Leave the `return Settings(...)` lines below it unchanged (they already pass `allowed_hosts=allowed`, and plan 5a added `require_identity=False`; keep it).

Replace

```python
def build_preview_app(staging_root: Path, host: str = "127.0.0.1", port: int = 8000) -> FastAPI:
    return create_app(preview_settings(staging_root, host, port))


def run_preview(staging_root: Path, host: str = "127.0.0.1", port: int = 8000) -> None:
    settings = preview_settings(staging_root, host, port)
```

with

```python
def build_preview_app(staging_root: Path, host: str = "127.0.0.1", port: int = 8000,
                      allowed_hosts: str | None = None) -> FastAPI:
    return create_app(preview_settings(staging_root, host, port, allowed_hosts))


def run_preview(staging_root: Path, host: str = "127.0.0.1", port: int = 8000,
                allowed_hosts: str | None = None) -> None:
    settings = preview_settings(staging_root, host, port, allowed_hosts)
```

If any anchor text is not found, read the file, find the equivalent code, and apply the same change; report the difference.

- [ ] **Step 4: Change `viz/publish/cli.py`**

Replace

```python
from .preview import run_preview
```

with

```python
from .preview import PreviewError, run_preview
```

Replace the whole function `_cmd_preview` with:

```python
def _cmd_preview(args) -> int:
    settings = Settings()
    try:
        run_preview(_staging_root(args, settings), args.host, args.port, args.allowed_hosts)
    except PreviewError as err:
        raise CliError(str(err), code=2) from err
    return 0
```

In `build_parser`, replace

```python
    preview_p.add_argument("--host", default="127.0.0.1")
```

with

```python
    preview_p.add_argument("--host", default="127.0.0.1")
    preview_p.add_argument("--allowed-hosts", default=None, metavar="HOSTS",
                           help="comma-separated Host names to accept; required when --host is not loopback")
```

- [ ] **Step 5: Run the tests**

Run: `.venv/Scripts/python -m pytest tests/publish/test_preview.py tests/test_skill.py -v`
Expected: all pass.

- [ ] **Step 6: Run the whole suite and commit**

Run: `.venv/Scripts/python -m pytest`

```bash
git add viz/publish/preview.py viz/publish/cli.py tests/publish/test_preview.py
git -c user.name="tripp" -c user.email="dom4domg@gmail.com" commit -m "fix: viz preview needs --allowed-hosts to listen beyond loopback" -m "Co-Authored-By: <model name from your harness> <noreply@anthropic.com>
Claude-Session: <session url from your harness>"
```

---

### Task 10: A pulled dashboard cannot overwrite a colleague's newer edit (A25)

**Files:**
- Modify: `viz/publish/dashboards.py`, `viz/publish/cli.py`, `viz/publish/publish.py`, `skills/publish-viz/references/dashboards.md`, `tests/test_skill.py`
- Create: `tests/publish/test_pull_etag.py`

**Interfaces:**
- Consumes: `Storage.head(key) -> ObjectInfo` with the ETag as `head(key).etag` (plan 5a), `Storage.put(..., if_match=...)` (plan 5a), plan 5a's `_commit(storage, key, payload, doc_id, etag)` (a non-None `etag` becomes `if_match`), and `keep_created_at(existing, path)` from Task 6.
- Produces:
  - `viz.publish.dashboards.PULLED_ETAG_SUFFIX = ".pulled-etag"`.
  - `pulled_etag_path(dashboard_file: Path) -> Path`: `<file>.pulled-etag`, for example `.viz-staging/dashboards/sales/overview.json.pulled-etag`.
  - `write_pulled_etag(dashboard_file, etag) -> None`, `read_pulled_etag(dashboard_file) -> str | None`, `clear_pulled_etag(dashboard_file) -> None`.
  - `pulled_dashboard(...)` now returns `tuple[dict, str]`: the restamped document and the ETag read before the document.
  - `viz pull-dashboard` writes the sidecar; `viz new-dashboard` removes a stale one.
  - `publish_dashboard`: when the sidecar exists, after the overwrite guard it refuses unless the published ETag (`head(key).etag`) equals the pulled one, commits through `_commit` with the pulled ETag (so the PUT carries `if_match=<pulled etag>`), and removes the sidecar after success. Refusal text contains `published again by someone else after you pulled it` and `ask the user`.

- [ ] **Step 1: Write the failing tests**

Create `tests/publish/test_pull_etag.py`:

```python
"""pull-dashboard remembers the version it pulled; publish refuses to overwrite a newer
one (finding A25)."""
import json

import viz.publish.cli as cli
from viz.publish.cli import main
from viz.publish.dashboards import pulled_etag_path, read_pulled_etag
from viz.storage.local import LocalStorage

KEY = "viz/dashboards/sales/overview.json"


def _path(staging_root):
    return staging_root / "dashboards" / "sales" / "overview.json"


class RecordingStorage(LocalStorage):
    """Records the keyword arguments of every put."""

    def __init__(self, root):
        super().__init__(root)
        self.put_kwargs = {}

    def put(self, key, data, content_type, **kwargs):
        self.put_kwargs[key] = kwargs
        super().put(key, data, content_type, **kwargs)


def test_sidecar_sits_next_to_the_staged_file(staging_root):
    assert pulled_etag_path(_path(staging_root)) == staging_root / "dashboards" / "sales" / "overview.json.pulled-etag"


def test_pull_records_the_published_etag(env, staging_root, storage):
    assert main(["pull-dashboard", "sales/overview"]) == 0
    assert read_pulled_etag(_path(staging_root)) == storage.head(KEY).etag


def test_sidecar_is_removed_after_a_successful_publish(env, staging_root, storage, capsys):
    assert main(["pull-dashboard", "sales/overview"]) == 0
    assert main(["publish", str(_path(staging_root)), "--force"]) == 0
    assert not pulled_etag_path(_path(staging_root)).exists()
    assert json.loads(storage.get(KEY))["author"] == "tester@example.com"


def test_colleague_edit_after_pull_is_refused(env, staging_root, storage, capsys):
    assert main(["pull-dashboard", "sales/overview"]) == 0
    colleague = json.loads(storage.get(KEY))
    colleague["title"] = "Colleague's title"
    storage.put(KEY, json.dumps(colleague).encode("utf-8"), "application/json")
    capsys.readouterr()
    assert main(["publish", str(_path(staging_root)), "--force"]) == 1
    err = capsys.readouterr().err
    assert "published again by someone else after you pulled it" in err
    assert "ask the user" in err
    assert json.loads(storage.get(KEY))["title"] == "Colleague's title"
    assert pulled_etag_path(_path(staging_root)).exists()


def test_dashboard_deleted_after_pull_is_refused(env, staging_root, storage, capsys):
    assert main(["pull-dashboard", "sales/overview"]) == 0
    storage.delete(KEY)
    capsys.readouterr()
    assert main(["publish", str(_path(staging_root)), "--force"]) == 1
    assert "was deleted after you pulled it" in capsys.readouterr().err


def test_publish_passes_the_pulled_etag_as_if_match(env, bucket, staging_root, monkeypatch):
    assert main(["pull-dashboard", "sales/overview"]) == 0
    pulled = read_pulled_etag(_path(staging_root))
    recording = RecordingStorage(bucket)
    monkeypatch.setattr(cli, "get_storage", lambda settings: recording)
    assert main(["publish", str(_path(staging_root)), "--force"]) == 0
    assert recording.put_kwargs[KEY].get("if_match") == pulled


def test_new_dashboard_removes_a_stale_sidecar(env, staging_root):
    assert main(["pull-dashboard", "sales/overview"]) == 0
    assert main(["new-dashboard", "sales/overview", "--force"]) == 0
    assert not pulled_etag_path(_path(staging_root)).exists()
```

Append to `tests/test_skill.py`:

```python


def test_dashboards_guide_explains_the_pulled_version_refusal():
    from viz.publish import publish

    text = _text(SKILL / "references" / "dashboards.md")
    assert "published again by someone else after you pulled it" in text
    assert "published again by someone else after you pulled it" in publish.PULLED_CHANGED
```

- [ ] **Step 2: Run them to see them fail**

Run: `.venv/Scripts/python -m pytest tests/publish/test_pull_etag.py tests/test_skill.py -v`
Expected: `tests/publish/test_pull_etag.py` fails to collect with `ImportError: cannot import name 'pulled_etag_path'`; `test_dashboards_guide_explains_the_pulled_version_refusal` FAILS.

- [ ] **Step 3: Add the sidecar to `viz/publish/dashboards.py`**

Add this block directly below `PLACEHOLDER_MARKDOWN = "Describe what this dashboard answers."`:

```python
PULLED_ETAG_SUFFIX = ".pulled-etag"


def pulled_etag_path(dashboard_file: Path) -> Path:
    """The file next to a staged dashboard that records which published version
    `viz pull-dashboard` copied: its ETag, one line (finding A25). The dashboard schema
    allows no extra keys, so the ETag cannot live inside the dashboard file."""
    dashboard_file = Path(dashboard_file)
    return dashboard_file.with_name(dashboard_file.name + PULLED_ETAG_SUFFIX)


def write_pulled_etag(dashboard_file: Path, etag: str) -> None:
    pulled_etag_path(dashboard_file).write_text(etag + "\n", encoding="utf-8", newline="\n")


def read_pulled_etag(dashboard_file: Path) -> str | None:
    path = pulled_etag_path(dashboard_file)
    if not path.is_file():
        return None
    return path.read_text(encoding="utf-8").strip() or None


def clear_pulled_etag(dashboard_file: Path) -> None:
    pulled_etag_path(dashboard_file).unlink(missing_ok=True)
```

Replace the start of `pulled_dashboard`:

```python
def pulled_dashboard(dashboard_id: str, settings: Settings, storage: Storage, author: str, now: datetime) -> dict:
    validate_id(dashboard_id)
    try:
        raw = storage.get(dashboard_key(settings.root_prefix, dashboard_id))
    except NotFound as err:
```

with

```python
def pulled_dashboard(dashboard_id: str, settings: Settings, storage: Storage, author: str,
                     now: datetime) -> tuple[dict, str]:
    """The published dashboard restamped for editing, and the ETag of the version pulled.
    The ETag is read before the body: if the dashboard changes in between, the ETag is
    older than the body and the later publish is refused, never silently applied."""
    validate_id(dashboard_id)
    key = dashboard_key(settings.root_prefix, dashboard_id)
    try:
        etag = storage.head(key).etag
        raw = storage.get(key)
    except NotFound as err:
```

and at the end of the same function replace

```python
    doc["updated_at"] = now.strftime(TIMESTAMP_FORMAT)
    return doc
```

with

```python
    doc["updated_at"] = now.strftime(TIMESTAMP_FORMAT)
    return doc, etag
```

- [ ] **Step 4: Write and clear the sidecar in `viz/publish/cli.py`**

Replace

```python
from .dashboards import DashboardError, new_dashboard, pulled_dashboard, write_staged_dashboard
```

with

```python
from .dashboards import (
    DashboardError, clear_pulled_etag, new_dashboard, pulled_dashboard, write_pulled_etag, write_staged_dashboard,
)
```

In `_cmd_new_dashboard`, replace

```python
        doc = new_dashboard(args.id, args.chart or [], args.title, author, datetime.now(timezone.utc))
        path = write_staged_dashboard(doc, _staging_root(args, settings), force=args.force)
```

with

```python
        doc = new_dashboard(args.id, args.chart or [], args.title, author, datetime.now(timezone.utc))
        path = write_staged_dashboard(doc, _staging_root(args, settings), force=args.force)
        clear_pulled_etag(path)
```

In `_cmd_pull_dashboard`, replace

```python
        doc = pulled_dashboard(args.id, settings, storage, author, datetime.now(timezone.utc))
        path = write_staged_dashboard(doc, _staging_root(args, settings), force=args.force)
```

with

```python
        doc, etag = pulled_dashboard(args.id, settings, storage, author, datetime.now(timezone.utc))
        path = write_staged_dashboard(doc, _staging_root(args, settings), force=args.force)
        write_pulled_etag(path, etag)
```

- [ ] **Step 5: Check the pulled version in `viz/publish/publish.py`**

Add this import below the existing `from .validate import ...` line:

```python
from .dashboards import clear_pulled_etag, read_pulled_etag
```

Add this block directly above `def publish_dashboard(`:

```python
PULLED_CHANGED = (
    "dashboard '{id}' was published again by someone else after you pulled it; "
    "ask the user before running viz pull-dashboard {id} --force, which replaces your staged edits "
    "with the new version"
)
PULLED_DELETED = "dashboard '{id}' was deleted after you pulled it; ask the user before publishing it again"


def _check_pulled_version(storage: Storage, key: str, dashboard_id: str, pulled: str) -> None:
    """A dashboard staged by `viz pull-dashboard` may only replace the version it was
    pulled from (finding A25). This runs after the overwrite guard; the PUT then uses the
    pulled ETag as if_match, so a change after this check is refused by storage."""
    try:
        current = storage.head(key).etag
    except NotFound as err:
        raise PublishRefused([PULLED_DELETED.format(id=dashboard_id)]) from err
    if current != pulled:
        raise PublishRefused([PULLED_CHANGED.format(id=dashboard_id)])
```

In `publish_dashboard`, replace these lines (their text after plan 5a and Tasks 1 and 6 of this plan):

```python
    existing, etag = _guard_overwrite(storage, key, force, out)
    keep_created_at(existing, path)
    _commit(storage, key, path.read_bytes(), dashboard_id, etag)
    print(f"published: {dashboard_id} -> {destination(settings, key)}", file=out)
    return dashboard_id
```

with

```python
    existing, etag = _guard_overwrite(storage, key, force, out)
    pulled = read_pulled_etag(path)
    if pulled is not None:
        _check_pulled_version(storage, key, dashboard_id, pulled)
    keep_created_at(existing, path)
    # A pulled dashboard may only replace the version it was pulled from, so the
    # commit is conditional on the pulled ETag (plan 5a's _commit passes it as if_match).
    _commit(storage, key, path.read_bytes(), dashboard_id, pulled if pulled is not None else etag)
    print(f"published: {dashboard_id} -> {destination(settings, key)}", file=out)
    clear_pulled_etag(path)
    return dashboard_id
```

If the old text is not found exactly, read `publish_dashboard`, apply the same three changes (the pulled check after the overwrite guard, the ETag passed to `_commit`, `clear_pulled_etag(path)` before `return dashboard_id`), and report the difference.

- [ ] **Step 6: Explain the refusal in `references/dashboards.md`**

In `skills/publish-viz/references/dashboards.md`, replace

```markdown
After `viz pull-dashboard`, this refusal is expected, because the dashboard
already exists. Still show the user who published it last and ask before
adding `--force`.
```

with

```markdown
After `viz pull-dashboard`, this refusal is expected, because the dashboard
already exists. Still show the user who published it last and ask before
adding `--force`.

`viz pull-dashboard` also remembers which version you pulled, in a file next
to the staged one whose name ends in `.pulled-etag`. If someone publishes the
dashboard again before you do, `viz publish --force` refuses with
`published again by someone else after you pulled it`. Show the user that
line. Never delete the `.pulled-etag` file to get past it. Ask the user
whether to pull the new version and redo the edits.
```

- [ ] **Step 7: Run the tests**

Run: `.venv/Scripts/python -m pytest tests/publish/test_pull_etag.py tests/publish/test_dashboards.py tests/publish/test_publish.py tests/publish/test_created_at.py tests/test_skill.py -v`
Expected: all pass.

- [ ] **Step 8: Run the whole suite and commit**

Run: `.venv/Scripts/python -m pytest`

```bash
git add viz/publish/dashboards.py viz/publish/cli.py viz/publish/publish.py skills/publish-viz/references/dashboards.md tests/publish/test_pull_etag.py tests/test_skill.py
git -c user.name="tripp" -c user.email="dom4domg@gmail.com" commit -m "fix: publishing a pulled dashboard refuses to overwrite a newer version" -m "Co-Authored-By: <model name from your harness> <noreply@anthropic.com>
Claude-Session: <session url from your harness>"
```

---

### Task 11: `viz move --kind chart|dashboard` (A26)

**Files:**
- Modify: `viz/publish/move.py`, `viz/publish/cli.py`, `skills/publish-viz/SKILL.md`, `tests/test_skill.py`
- Create: `tests/publish/test_move_kind.py`

**Interfaces:**
- Consumes: `viz.publish.move._exists`, `chart_key`, `dashboard_key`.
- Produces:
  - `plan_move(old_id, new_id, settings, storage, kind: str | None = None) -> MovePlan`. `kind` is `"chart"`, `"dashboard"` or `None`.
  - `_pick_kind(storage, root, old_id, kind) -> str`. With `kind=None` and both a chart and a dashboard at `old_id`: `MoveError("'<id>' is both a chart and a dashboard; pass --kind chart or --kind dashboard")`. With a kind that does not exist: `MoveError("no chart with id '<id>'")` or `MoveError("no dashboard with id '<id>'")`. Neither exists: `MoveError("no chart or dashboard with id '<id>'")` (unchanged).
  - `viz move ... --kind chart|dashboard`.
  - `apply_move` is not touched: its PUTs stay unconditional in this round (decided by the lead, deferred).

- [ ] **Step 1: Write the failing tests**

Create `tests/publish/test_move_kind.py`:

```python
"""viz move --kind picks the chart or the dashboard when an id is both (finding A26)."""
import json

import pytest

from viz.publish.cli import main
from viz.publish.move import MoveError, plan_move
from viz.storage import NotFound

BOTH = "sales/revenue-by-region"  # a chart in the sample bucket


def _add_dashboard_with_the_chart_id(storage):
    doc = json.loads(storage.get("viz/dashboards/sales/overview.json"))
    doc["id"] = BOTH
    storage.put(f"viz/dashboards/{BOTH}.json", json.dumps(doc).encode("utf-8"), "application/json")


def test_an_id_that_is_both_needs_kind(settings, storage):
    _add_dashboard_with_the_chart_id(storage)
    with pytest.raises(MoveError, match="is both a chart and a dashboard; pass --kind chart or --kind dashboard"):
        plan_move(BOTH, "sales/renamed", settings, storage)


def test_kind_dashboard_plans_only_the_dashboard(settings, storage):
    _add_dashboard_with_the_chart_id(storage)
    plan = plan_move(BOTH, "sales/renamed", settings, storage, kind="dashboard")
    assert plan.kind == "dashboard"
    assert plan.keys == [(f"viz/dashboards/{BOTH}.json", "viz/dashboards/sales/renamed.json")]


def test_kind_chart_plans_only_the_chart(settings, storage):
    _add_dashboard_with_the_chart_id(storage)
    plan = plan_move(BOTH, "sales/renamed", settings, storage, kind="chart")
    assert plan.kind == "chart"
    assert all(old.startswith(f"viz/charts/{BOTH}/") for old, _new in plan.keys)


def test_kind_that_does_not_exist(settings, storage):
    with pytest.raises(MoveError, match="no dashboard with id 'sales/revenue-by-region'"):
        plan_move(BOTH, "sales/renamed", settings, storage, kind="dashboard")
    with pytest.raises(MoveError, match="no chart with id 'sales/overview'"):
        plan_move("sales/overview", "sales/renamed", settings, storage, kind="chart")


def test_move_command_kind_flag(env, storage, capsys):
    _add_dashboard_with_the_chart_id(storage)
    assert main(["move", BOTH, "sales/renamed", "--yes"]) == 1
    assert "--kind" in capsys.readouterr().err
    assert main(["move", BOTH, "sales/renamed", "--kind", "dashboard", "--yes"]) == 0
    storage.head("viz/dashboards/sales/renamed.json")
    storage.head(f"viz/charts/{BOTH}/chart.json")  # the chart did not move
    with pytest.raises(NotFound):
        storage.head(f"viz/dashboards/{BOTH}.json")
```

Append to `tests/test_skill.py`:

```python


def test_skill_teaches_move_kind():
    assert "--kind" in _text(SKILL / "SKILL.md")
```

- [ ] **Step 2: Run them to see them fail**

Run: `.venv/Scripts/python -m pytest tests/publish/test_move_kind.py tests/test_skill.py -v`
Expected: `test_an_id_that_is_both_needs_kind` FAILS (a chart plan is returned), the three tests that pass `kind=` FAIL with `TypeError: plan_move() got an unexpected keyword argument 'kind'`, `test_move_command_kind_flag` FAILS (exit 0 without `--kind`), and `test_skill_teaches_move_kind` FAILS.

- [ ] **Step 3: Add `kind` to `viz/publish/move.py`**

Add this function directly above `def plan_move(`:

```python
def _pick_kind(storage: Storage, root: str, old_id: str, kind: str | None) -> str:
    """Which object to move. An id can be both a chart and a dashboard; then the caller
    must say which with --kind (finding A26)."""
    is_chart = _exists(storage, chart_key(root, old_id))
    is_dashboard = _exists(storage, dashboard_key(root, old_id))
    if kind == "chart":
        if not is_chart:
            raise MoveError(f"no chart with id '{old_id}'")
        return "chart"
    if kind == "dashboard":
        if not is_dashboard:
            raise MoveError(f"no dashboard with id '{old_id}'")
        return "dashboard"
    if kind is not None:
        raise MoveError(f"unknown kind '{kind}'; use chart or dashboard")
    if is_chart and is_dashboard:
        raise MoveError(f"'{old_id}' is both a chart and a dashboard; pass --kind chart or --kind dashboard")
    if is_chart:
        return "chart"
    if is_dashboard:
        return "dashboard"
    raise MoveError(f"no chart or dashboard with id '{old_id}'")
```

Replace

```python
def plan_move(old_id: str, new_id: str, settings: Settings, storage: Storage) -> MovePlan:
```

with

```python
def plan_move(old_id: str, new_id: str, settings: Settings, storage: Storage, kind: str | None = None) -> MovePlan:
```

Replace

```python
        raise MoveError("old and new id are the same")
    root = settings.root_prefix
```

with

```python
        raise MoveError("old and new id are the same")
    root = settings.root_prefix
    kind = _pick_kind(storage, root, old_id, kind)
```

Replace

```python
    if _exists(storage, chart_key(root, old_id)):
```

with

```python
    if kind == "chart":
```

Replace

```python
    if _exists(storage, dashboard_key(root, old_id)):
```

with

```python
    if kind == "dashboard":
```

Leave the final `raise MoveError(f"no chart or dashboard with id '{old_id}'")` of `plan_move` in place. If any anchor text is not found, read the file, find the equivalent code, and apply the same change; report the difference.

- [ ] **Step 4: Add `--kind` to `viz/publish/cli.py`**

In `_cmd_move`, replace

```python
        plan = plan_move(args.old_id, args.new_id, settings, storage)
```

with

```python
        plan = plan_move(args.old_id, args.new_id, settings, storage, kind=args.kind)
```

In `build_parser`, replace

```python
    move_p.add_argument("--yes", action="store_true", help="apply the move (without it, only the plan is printed)")
```

with

```python
    move_p.add_argument("--yes", action="store_true", help="apply the move (without it, only the plan is printed)")
    move_p.add_argument("--kind", choices=["chart", "dashboard"], default=None,
                        help="which one to move when the id is both a chart and a dashboard")
```

- [ ] **Step 5: Teach it in the skill**

In `skills/publish-viz/SKILL.md`, replace

```markdown
- `--yes` on `viz move`: run `viz move <old> <new>` without it first, show
  the user the printed plan (which dashboards change), and add `--yes` only
  after they agree.
```

with

```markdown
- `--yes` on `viz move`: run `viz move <old> <new>` without it first, show
  the user the printed plan (which dashboards change), and add `--yes` only
  after they agree. If `viz move` says the id is both a chart and a
  dashboard, ask the user which one they mean and add `--kind chart` or
  `--kind dashboard`.
```

- [ ] **Step 6: Run the tests**

Run: `.venv/Scripts/python -m pytest tests/publish/test_move_kind.py tests/publish/test_move.py tests/publish/test_end_to_end.py tests/test_skill.py -v`
Expected: all pass.

- [ ] **Step 7: Run the whole suite and commit**

Run: `.venv/Scripts/python -m pytest`

```bash
git add viz/publish/move.py viz/publish/cli.py skills/publish-viz/SKILL.md tests/publish/test_move_kind.py tests/test_skill.py
git -c user.name="tripp" -c user.email="dom4domg@gmail.com" commit -m "feat: viz move --kind for an id that is both a chart and a dashboard" -m "Co-Authored-By: <model name from your harness> <noreply@anthropic.com>
Claude-Session: <session url from your harness>"
```

---

## Self-review notes

- A13: Task 1. A14: Task 2 (code messages, skill step 5 carve-out, dashboards guide); Tasks 1, 9 and 10 add new refusals in the same wording. A15: Task 3. A16: Task 4. A19: Task 5. A20: Task 6. A21: Task 7. A22: Task 8. A23: Task 9. A24: Task 4. A25: Task 10. A26: Task 11.
- "Author is attribution" wording: `identity.py` docstring (Task 5, tested), `references/dashboards.md` (Task 3, tested), SKILL.md setup item 3, README and `docs/work-setup.md` (Task 5). The error text `does not match the resolved identity` is kept because `tests/test_skill.py` and the skill teach it verbatim; it names what the CLI resolved, not a permission.
- Files that plan 5a also edits (`publish.py`, `validate.py`, `staging.py`, `preview.py`, `config.py`, several test files): every edit is anchored on the text as it stands after 5a (5a's "Interfaces for later plans" lists it) and carries the "if not found" instruction. `staging.py` is not edited by this plan. `cli.py` is not edited by 5a.
- `docs/work-setup.md` is plan 5d's file, but some of its sentences would become false here (VIZ_STORAGE row, `--sql @first.sql` in step 6, the author paragraph and the two author troubleshooting rows), so Tasks 1, 4 and 5 fix exactly those. Plan 5d's Task 10 anchors on the text these tasks leave (`--sql-file first.sql`).
- `README.md` is edited here in three places (the `--force`/`--yes` sentence, the two `viz query` lines, the publisher-settings paragraph); plan 5d only adds a bullet under `## Trust assumptions, read these first`, so the edits do not overlap.
- `viz move` keeps unconditional PUTs (decided by the lead; deferred). No task here makes them conditional.
- Integration tests with `VIZ_INTEGRATION=1` are run one file at a time; no step here runs them.
- Not covered here: the S3 backend's behaviour for `if_match` on a missing key (plan 5a owns it; Task 10 refuses a deleted dashboard before the PUT, so it is not reached).

---

## Interfaces for later plans (5c, 5d)

Exact state after this plan. Plan 5c's and 5d's Task 0 check these.

- CLI: `viz query --sql-file PATH` (mutually exclusive with `--sql`); `viz preview --allowed-hosts HOSTS` (required for a non-loopback `--host`; `*` accepted); `viz move ... --kind chart|dashboard`. `viz publish` and `viz move` exit 2 unless `VIZ_STORAGE` is set in the environment, and print `published: <id> -> <destination>` / `moved: <old> -> <new> in <destination>`.
- `viz.publish.publish.destination(settings, key) -> str`; `keep_created_at(existing, staged_file)`; `PULLED_CHANGED`, `PULLED_DELETED`.
- `viz.publish.identity.publisher_author(settings, databricks_user=None, warehouse_id=None)`; `viz.publish.query.databricks_login_available(warehouse_id=None)`: the Databricks login only with `DATABRICKS_HOST`, `DATABRICKS_TOKEN` and a warehouse all set.
- `viz.publish.dashboards.PULLED_ETAG_SUFFIX = ".pulled-etag"` and the sidecar helpers.
- `docs/work-setup.md` after this plan: the `VIZ_STORAGE` row ends with "`viz publish` and `viz move` refuse to run unless it is set explicitly"; section 6 publishes with `.venv/bin/viz query --sql-file first.sql --id smoke/first-chart`; the author paragraph in section 2 names all three Databricks variables. Sections 5 and 7 and the other troubleshooting rows are unchanged.
- `README.md` after this plan: the `## Trust assumptions, read these first` heading and its bullets are unchanged.
- No server, front-end, Helm or AWS file is changed by this plan.
