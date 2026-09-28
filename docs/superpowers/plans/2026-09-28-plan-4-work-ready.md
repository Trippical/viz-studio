# Plan 4: Work-machine ready (author check, refresher scaffold, container, AWS, Helm, CI, setup guide) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Everything the user needs to clone this repo onto their work machine and run viz-site against their company's real S3 bucket and Databricks warehouse: a publish path that validates without workarounds, a container image, AWS policy documents, a Helm chart, CI that builds and tests all of it on GitHub, opt-in tests to run against real infrastructure, and one setup guide that walks through it.

**Architecture:** No new runtime behaviour on the server. The CLI gains one check (confirm the Databricks login when validating a `viz query` chart). `viz.refresh` gets the spec's scaffold only. Deployment artifacts are files: `Dockerfile`, `docker-compose.yml`, `deploy/aws/*.json`, `deploy/helm/viz-site/`, `.github/workflows/ci.yml`. Docker and Helm are not installed on the development machine, so pytest checks those files statically and CI builds, lints and renders them for real.

**Tech Stack:** Python 3.11, pytest, PyYAML (new dev-only dependency), Docker, Helm 3, GitHub Actions, AWS IAM JSON.

**Spec:** `docs/superpowers/specs/2026-09-22-viz-site-design.md` sections 7 (refresher scaffold), 8 (CI bullet), 9 (layout), 10 step 7, 12.2 (server headers, identity, allowed hosts), 12.4 (author), 12.5 (bucket and cluster), 12.6 (open source hygiene). Carry-forwards from `.claude/sessions/logs/2026-09-24-plans-2-and-3a-built-and-merged.md`: ship `web/dist/duckdb/**`; the self-hosted parquet extension is pinned to DuckDB v1.4.3; CI needs the Playwright Chromium download and a way past npm skipping esbuild's postinstall; `VIZ_ALLOWED_HOSTS` must be set in deployment.

**Decisions taken with the user on 2026-09-28:**

1. The deliverable is the public repo `Trippical/viz-studio`, cloned onto the user's work machine. Real AWS and Databricks exist only there. This plan gives them opt-in tests and a checklist rather than claiming the real integration works.
2. Author check, option (b): `viz validate` accepts the Databricks login that `viz query` stamped. This plan implements it by asking Databricks for the current user (the same `SELECT current_user()` `viz query` runs) when the Databricks variables are set, so a hand-edited author still fails (spec 12.4). Without the variables, validation falls back to `VIZ_AUTHOR` as before. The author order ruling from Plan 3a is unchanged.
3. Phone and narrow-screen layout are out of scope.

## Global Constraints

- Python `>=3.11`. Always run the venv interpreter: `.venv/Scripts/python` (Linux/macOS and CI: `.venv/bin/python`). Never the system `python`.
- `DATABRICKS_HOST`, `DATABRICKS_TOKEN`, `DATABRICKS_WAREHOUSE_ID` are read only inside `viz/publish/query.py`. They are never added to `viz.config.Settings`, and never appear in the Dockerfile, docker-compose, Helm chart or CI workflow (CLAUDE.md rule 5).
- No write routes on the server. The container runs only `viz-server`.
- One new dependency: `pyyaml>=6` in the `dev` extra only (tests parse YAML). Say so in the commit message that adds it (CLAUDE.md rule 7). No other new dependencies.
- Every placeholder in deploy files is visibly fake: `REPLACE_ME`, `example.com`, account id `123456789012`. No real bucket, role, account, host or key anywhere (spec 12.6).
- Container runs as uid `10001`, not root, and works with a read-only root filesystem plus a writable `/tmp`.
- The opt-in integration tests run only when `VIZ_INTEGRATION=1` is set. CI never sets it.
- New test packages need an empty `__init__.py` (every folder under `tests/` has one).
- Every commit message follows the "Commit messages" section of `CLAUDE.md`: subject, blank line, then two contiguous trailer lines (`Co-Authored-By` naming the model that made the commit as its harness states it, and `Claude-Session` with the session URL its harness states), produced with two `-m` flags.
- The whole Python suite (`.venv/Scripts/python -m pytest`) must pass before every commit.

## Review Focus

1. **The Databricks user lookup fails during `viz validate`** (warehouse asleep, token expired, network). Expected: validation fails with one readable `author:` error, never a traceback, and publish refuses. Pinned in Task 1 (`test_unreachable_databricks_is_a_validation_error`).
2. **Kubernetes probes rejected by the host allow-list.** Probes send `Host: <pod-ip>`, which `TrustedHostMiddleware` answers with 400, so the pod never becomes ready. Expected: probes send a `Host` header from `allowedHosts`. Pinned in Task 5 (`test_probes_send_an_allowed_host_header`).
3. **The container starts but the large lane fails** because `web/dist/duckdb/**` (the self-hosted parquet extension) did not make it into the image. Expected: the image copies the whole built `web/dist`, and CI builds the image. Pinned in Task 3 (`test_image_ships_the_whole_front_end_build`) and Task 6 (the docker job).
4. **CI's Playwright job cannot find `viz-server`**: `web/playwright.config.ts` starts `<repo>/.venv/bin/viz-server`, which only exists if CI creates `.venv` at the repo root. Expected: the web job creates `.venv` there. Pinned in Task 6 (`test_web_job_creates_the_repo_venv`).
5. **A bucket policy that locks out publishers.** Restricting the bucket to the VPC endpoint also blocks the publishers' laptops, which reach S3 over the internet or VPN. Expected: the VPC-endpoint deny exempts the publisher role. Pinned in Task 4 (`test_vpce_deny_exempts_the_publisher_role`).

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
5. If a command fails and you cannot fix it within the task's scope, stop and
   report the full error output. Do not work around it by weakening a test.
6. Before committing, run the whole Python suite:
   `.venv/Scripts/python -m pytest`. It must pass.
7. Stage only the files named in the task's commit step. Never run
   `git checkout -- .`, `git restore`, `git stash`, `git clean` or `git reset`.
8. Report back with: the commit hash, the test summary line, and any
   deviation from the plan. Nothing else is needed.

A guard hook blocks shell commands that contain backticks, `$(...)`, or
redirects to paths outside the project. Create every file in this plan with
the Write tool, not a shell heredoc.

---

## File structure

| Path | Responsibility |
|---|---|
| `viz/publish/query.py` | Adds `databricks_configured()` and `current_user(warehouse_id)`; shares connection arguments with `run_query` |
| `viz/publish/validate.py` | `validate_staged_chart` confirms the Databricks login for `databricks-sql` charts |
| `viz/refresh/__init__.py`, `viz/refresh/__main__.py` | Spec 7 scaffold: `plan(settings, storage)` and a `viz-refresh` entry point that logs the plan and exits |
| `pyproject.toml` | `viz-refresh` console script; `pyyaml>=6` in `dev` |
| `Dockerfile`, `.dockerignore`, `docker-compose.yml` | The image (front end built in a Node stage, server in a Python stage) and a local run |
| `deploy/aws/server-policy.json`, `publisher-policy.json`, `bucket-policy.json`, `README.md` | IAM and bucket policies with placeholders, and the bucket baseline |
| `deploy/helm/viz-site/**` | Helm chart with the spec 12.5 defaults |
| `.github/workflows/ci.yml` | Python, web, docker, helm and gitleaks jobs |
| `tests/storage/test_s3_integration.py` | Opt-in round trip against a real bucket |
| `docs/work-setup.md` | The work-machine guide |
| `tests/publish/test_validate_author.py`, `tests/refresh/`, `tests/deploy/`, `tests/test_work_setup_doc.py` | Tests for the above |
| `skills/publish-viz/SKILL.md`, `README.md` | Author wording, install wording, pointer to the guide |

---

### Task 1: `viz validate` confirms the Databricks login of a `viz query` chart

**Files:**
- Modify: `viz/publish/query.py`, `viz/publish/validate.py`, `skills/publish-viz/SKILL.md`, `README.md`
- Test: `tests/publish/test_validate_author.py`

**Interfaces:**
- Consumes: `viz.publish.identity.check_author(doc, settings, databricks_user=None) -> list[str]` (already accepts the Databricks user); `viz.publish.query.QueryError`, `_get_connect()`, `_env(name)`, `resolve_warehouse(warehouse_id)`; the test fixtures `env`, `staging_root` (tests/publish/conftest.py).
- Produces:
  - `viz.publish.query.databricks_configured() -> bool`: true when `DATABRICKS_HOST` and `DATABRICKS_TOKEN` are both set and non-empty.
  - `viz.publish.query.current_user(warehouse_id: str | None = None) -> str`: runs `SELECT current_user()`; raises `QueryError` on any failure.
  - `validate_staged_chart` behaviour: for a chart whose `source.kind` is `"databricks-sql"` and `databricks_configured()` is true, the expected author is the Databricks login; if the lookup fails the error list contains one line starting `author: could not confirm the Databricks user:`.

- [ ] **Step 1: Write the failing tests**

Create `tests/publish/test_validate_author.py`:

```python
"""viz validate confirms the Databricks login that viz query stamped as author."""
import json

import pyarrow as pa
import pytest

from viz.publish import query
from viz.publish.cli import main

SQL = "SELECT region, sum(revenue) AS revenue FROM sales.public.monthly GROUP BY region"


class FakeCursor:
    def __init__(self, calls):
        self.calls = calls
        self.last = None

    def execute(self, sql):
        self.calls.append(sql)
        self.last = sql

    def fetchone(self):
        return ("dbx@example.com",)

    def fetchall_arrow(self):
        return pa.table({"region": ["EMEA", "NA"], "revenue": [1.5, 2.5]})

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


def _chart_dir(staging_root):
    return staging_root / "charts" / "sales" / "by-region"


def test_query_chart_validates_with_the_databricks_login(env, staging_root, dbx, capsys):
    # env sets VIZ_AUTHOR=tester@example.com, which differs from the Databricks login.
    assert main(["query", "--sql", SQL, "--id", "sales/by-region"]) == 0
    assert json.loads((_chart_dir(staging_root) / "chart.json").read_text(encoding="utf-8"))["author"] == "dbx@example.com"
    capsys.readouterr()
    assert main(["validate", str(_chart_dir(staging_root))]) == 0, capsys.readouterr().err


def test_hand_edited_author_still_fails(env, staging_root, dbx, capsys):
    assert main(["query", "--sql", SQL, "--id", "sales/by-region"]) == 0
    path = _chart_dir(staging_root) / "chart.json"
    doc = json.loads(path.read_text(encoding="utf-8"))
    doc["author"] = "someone-else@example.com"
    path.write_text(json.dumps(doc), encoding="utf-8")
    capsys.readouterr()
    assert main(["validate", str(_chart_dir(staging_root))]) == 1
    assert "does not match the resolved identity 'dbx@example.com'" in capsys.readouterr().err


def test_without_databricks_variables_validation_falls_back_to_viz_author(env, staging_root, dbx, monkeypatch, capsys):
    assert main(["query", "--sql", SQL, "--id", "sales/by-region"]) == 0
    monkeypatch.delenv("DATABRICKS_HOST")
    monkeypatch.delenv("DATABRICKS_TOKEN")
    capsys.readouterr()
    assert main(["validate", str(_chart_dir(staging_root))]) == 1
    assert "does not match the resolved identity 'tester@example.com'" in capsys.readouterr().err


def test_unreachable_databricks_is_a_validation_error(env, staging_root, dbx, monkeypatch, capsys):
    assert main(["query", "--sql", SQL, "--id", "sales/by-region"]) == 0

    def refuse(**kwargs):
        raise ConnectionError("warehouse unreachable")

    monkeypatch.setattr(query, "_connect", refuse)
    capsys.readouterr()
    assert main(["validate", str(_chart_dir(staging_root))]) == 1
    err = capsys.readouterr().err
    assert "author: could not confirm the Databricks user:" in err
    assert "Traceback" not in err


def test_staged_file_chart_ignores_databricks(env, staging_root, dbx, tmp_path):
    csv = tmp_path / "rows.csv"
    csv.write_text("region,revenue\nEMEA,1.5\n", encoding="utf-8")
    assert main(["stage", "--from", str(csv), "--id", "sales/from-file"]) == 0
    calls_before = len(dbx)
    assert main(["validate", str(staging_root / "charts" / "sales" / "from-file")]) == 0
    assert len(dbx) == calls_before, "a chart without a databricks-sql source must not contact Databricks"


def test_databricks_configured(monkeypatch):
    monkeypatch.delenv("DATABRICKS_HOST", raising=False)
    monkeypatch.delenv("DATABRICKS_TOKEN", raising=False)
    assert query.databricks_configured() is False
    monkeypatch.setenv("DATABRICKS_HOST", "https://x.example.com")
    assert query.databricks_configured() is False
    monkeypatch.setenv("DATABRICKS_TOKEN", "dapi-test")
    assert query.databricks_configured() is True
```

- [ ] **Step 2: Run them to see them fail**

Run: `.venv/Scripts/python -m pytest tests/publish/test_validate_author.py -v`
Expected: `test_query_chart_validates_with_the_databricks_login` FAILS (validate exits 1: author mismatch against `tester@example.com`), `test_hand_edited_author_still_fails` FAILS (the message names `tester@example.com`), `test_unreachable_databricks_is_a_validation_error` FAILS, `test_databricks_configured` FAILS with `AttributeError`. The fallback and file-chart tests may pass already.

- [ ] **Step 3: Add `databricks_configured` and `current_user` to `viz/publish/query.py`**

Add these two functions directly below `def read_sql_argument(...)`:

```python
def databricks_configured() -> bool:
    """True when the variables `viz query` needs to reach Databricks are set."""
    return bool(os.environ.get("DATABRICKS_HOST")) and bool(os.environ.get("DATABRICKS_TOKEN"))


def _connection_args(warehouse_id: str | None) -> dict:
    warehouse = resolve_warehouse(warehouse_id)
    host = _env("DATABRICKS_HOST").removeprefix("https://").removeprefix("http://").rstrip("/")
    token = _env("DATABRICKS_TOKEN")
    return {"server_hostname": host, "http_path": f"/sql/1.0/warehouses/{warehouse}", "access_token": token}


def current_user(warehouse_id: str | None = None) -> str:
    """The Databricks login the configured token belongs to. `viz validate` uses it to
    confirm the author `viz query` stamped (spec 12.4)."""
    args = _connection_args(warehouse_id)
    connect = _get_connect()
    try:
        connection = connect(**args)
        try:
            cursor = connection.cursor()
            try:
                cursor.execute("SELECT current_user()")
                return cursor.fetchone()[0]
            finally:
                cursor.close()
        finally:
            connection.close()
    except QueryError:
        raise
    except Exception as err:
        raise QueryError(f"could not read the Databricks user: {err}", code=2) from err
```

In `run_query`, replace these lines:

```python
    warehouse = resolve_warehouse(warehouse_id)
    host = _env("DATABRICKS_HOST").removeprefix("https://").removeprefix("http://").rstrip("/")
    token = _env("DATABRICKS_TOKEN")
    connect = _get_connect()
    try:
        connection = connect(server_hostname=host, http_path=f"/sql/1.0/warehouses/{warehouse}", access_token=token)
```

with:

```python
    args = _connection_args(warehouse_id)
    connect = _get_connect()
    try:
        connection = connect(**args)
```

- [ ] **Step 4: Use it in `viz/publish/validate.py`**

Add below `from .identity import check_author`:

```python
from .query import QueryError, current_user, databricks_configured
```

Add this function directly above `def validate_staged_chart(`:

```python
def _check_chart_author(doc: dict, settings: Settings) -> list[str]:
    """A chart staged by `viz query` carries the Databricks login as its author. When the
    Databricks variables are set, confirm that login; otherwise check VIZ_AUTHOR as usual."""
    source = doc.get("source") or {}
    if source.get("kind") != "databricks-sql" or not databricks_configured():
        return check_author(doc, settings)
    try:
        user = current_user(source.get("warehouse_id"))
    except QueryError as err:
        return [f"author: could not confirm the Databricks user: {err}"]
    return check_author(doc, settings, databricks_user=user)
```

In `validate_staged_chart`, replace the line

```python
    errors += check_author(doc, settings)
```

with

```python
    errors += _check_chart_author(doc, settings)
```

Leave `validate_dashboard_file`'s `check_author` call unchanged.

- [ ] **Step 5: Run the tests**

Run: `.venv/Scripts/python -m pytest tests/publish/test_validate_author.py tests/publish/test_query.py tests/publish/test_validate.py -v`
Expected: all pass.

- [ ] **Step 6: Update the skill and README wording**

In `skills/publish-viz/SKILL.md`, replace setup item 3 (the paragraph that starts `3. \`viz query\` stamps charts with the Databricks login, but`) with:

```markdown
3. `viz query` stamps charts with the Databricks login. When
   `DATABRICKS_HOST` and `DATABRICKS_TOKEN` are set, `viz validate` asks
   Databricks for the current user and accepts that login. Without them it
   checks `VIZ_AUTHOR` instead, so ask the user to set `VIZ_AUTHOR` to their
   Databricks login email. If validation says
   `author '<a>' does not match the resolved identity '<b>'`, show the user
   both values and ask which identity is right. Never edit `author` by hand.
```

In the same file, replace setup item 1's second line
`` `pip install viz-site` (with `[databricks]` for `viz query`).`` with
`` to install viz-site from a checkout: `pip install -e ".[databricks]"` (see `docs/work-setup.md` in the viz-site repo).``

In `README.md`, replace the sentence fragment
`` `VIZ_AUTHOR` (overrides the
AWS caller identity when set; the Databricks user from `viz query` always wins;
author is attribution, not authentication)`` with
`` `VIZ_AUTHOR` (overrides the
AWS caller identity when set; the Databricks user from `viz query` always wins,
and `viz validate` confirms it with Databricks when the `DATABRICKS_*` variables
are set; author is attribution, not authentication)``. Match the existing line
breaks as closely as the edit allows; the wording is what matters.

Run: `.venv/Scripts/python -m pytest tests/test_skill.py -v` (must pass: it checks that SKILL.md still names `VIZ_AUTHOR` and the mismatch text).

- [ ] **Step 7: Run the whole suite and commit**

Run: `.venv/Scripts/python -m pytest`

```bash
git add viz/publish/query.py viz/publish/validate.py tests/publish/test_validate_author.py skills/publish-viz/SKILL.md README.md
git commit -m "feat: viz validate confirms the Databricks login that viz query stamped" -m "Co-Authored-By: <model> <noreply@anthropic.com>
Claude-Session: <session url>"
```

---

### Task 2: The refresher scaffold (spec 7)

**Files:**
- Create: `viz/refresh/__init__.py`, `viz/refresh/__main__.py`, `tests/refresh/__init__.py` (empty), `tests/refresh/test_plan.py`
- Modify: `pyproject.toml` (`[project.scripts]`)

**Interfaces:**
- Consumes: `viz.config.Settings`, `viz.storage.get_storage`, `Storage.list(prefix) -> list[ObjectInfo]`, `Storage.get(key) -> bytes`, `viz.schemas.validate_chart`, `SchemaError`.
- Produces: `viz.refresh.plan(settings: Settings, storage: Storage) -> list[dict]`, each item `{"id": str, "schedule": str | None, "warehouse_id": str | None}`, sorted by id; `viz.refresh.__main__.main() -> int`; console script `viz-refresh`.

- [ ] **Step 1: Write the failing tests**

Create `tests/refresh/__init__.py` (empty) and `tests/refresh/test_plan.py`:

```python
import json
import shutil
from pathlib import Path

from viz.config import Settings
from viz.refresh import plan
from viz.refresh.__main__ import main
from viz.storage import get_storage

SAMPLE = Path(__file__).resolve().parents[2] / "sample-bucket"


def _settings(root: Path) -> Settings:
    return Settings(storage="local", local_dir=root, root_prefix="viz/")


def test_plan_lists_only_charts_with_a_source(tmp_path):
    shutil.copytree(SAMPLE / "viz", tmp_path / "viz")
    settings = _settings(tmp_path)
    assert plan(settings, get_storage(settings)) == [
        {"id": "sales/revenue-by-region", "schedule": "0 6 * * *", "warehouse_id": "sample"},
    ]


def test_plan_skips_an_invalid_chart(tmp_path, caplog):
    shutil.copytree(SAMPLE / "viz", tmp_path / "viz")
    bad = tmp_path / "viz" / "charts" / "broken" / "chart.json"
    bad.parent.mkdir(parents=True)
    bad.write_text(json.dumps({"schema_version": 1, "id": "broken"}), encoding="utf-8")
    settings = _settings(tmp_path)
    ids = [item["id"] for item in plan(settings, get_storage(settings))]
    assert ids == ["sales/revenue-by-region"]
    assert "broken" in caplog.text


def test_main_logs_the_plan_and_exits_zero(tmp_path, monkeypatch, capsys):
    shutil.copytree(SAMPLE / "viz", tmp_path / "viz")
    monkeypatch.setenv("VIZ_STORAGE", "local")
    monkeypatch.setenv("VIZ_LOCAL_DIR", str(tmp_path))
    monkeypatch.setenv("VIZ_ROOT_PREFIX", "viz/")
    assert main() == 0
    out = capsys.readouterr().out
    assert "sales/revenue-by-region" in out
    assert "0 6 * * *" in out
    assert "1 refreshable chart" in out
```

- [ ] **Step 2: Run them to see them fail**

Run: `.venv/Scripts/python -m pytest tests/refresh -v`
Expected: collection ERROR, `ModuleNotFoundError: No module named 'viz.refresh'`.

- [ ] **Step 3: Write `viz/refresh/__init__.py`**

```python
"""Refresher scaffold (spec section 7). v1 only lists what a refresher would run.
The v2 spec defines execution, overwrite semantics, failure handling and concurrency;
it must honour spec section 12.7. Nothing here connects to Databricks."""
import json
import logging

from ..config import Settings
from ..schemas import SchemaError, validate_chart
from ..storage import Storage

log = logging.getLogger("viz.refresh")


def plan(settings: Settings, storage: Storage) -> list[dict]:
    """Every published chart with a `source` block, with its schedule. Invalid charts are skipped."""
    prefix = f"{settings.root_prefix}charts/"
    items = []
    for info in storage.list(prefix):
        if not info.key.endswith("/chart.json"):
            continue
        try:
            doc = validate_chart(json.loads(storage.get(info.key)))
        except (ValueError, SchemaError) as err:
            log.warning("skipping %s: %s", info.key, err)
            continue
        source = doc.get("source")
        if not source:
            continue
        items.append({"id": doc["id"], "schedule": source.get("schedule"), "warehouse_id": source.get("warehouse_id")})
    return sorted(items, key=lambda item: item["id"])
```

- [ ] **Step 4: Write `viz/refresh/__main__.py`**

```python
"""`viz-refresh` or `python -m viz.refresh`: print the refresh plan and exit. Runs nothing."""
import logging
import sys

from ..config import Settings
from ..storage import get_storage
from . import plan


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
    settings = Settings()
    items = plan(settings, get_storage(settings))
    for item in items:
        print(f"{item['id']}\tschedule={item['schedule'] or '-'}\twarehouse={item['warehouse_id'] or '-'}")
    print(f"{len(items)} refreshable chart(s); v1 does not run refreshes")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 5: Add the console script**

In `pyproject.toml`, `[project.scripts]`, add below `viz = "viz.publish.cli:main"`:

```toml
viz-refresh = "viz.refresh.__main__:main"
```

Reinstall so the script exists: `.venv/Scripts/python -m pip install -e ".[dev]"`.

- [ ] **Step 6: Run the tests and the whole suite, then commit**

Run: `.venv/Scripts/python -m pytest tests/refresh -v` then `.venv/Scripts/python -m pytest`
Then run `.venv/Scripts/viz-refresh` once from the repo root (it reads `./sample-bucket` by default) and check it prints `1 refreshable chart(s)`.

```bash
git add viz/refresh pyproject.toml tests/refresh
git commit -m "feat: refresher scaffold that lists refreshable charts and exits" -m "Co-Authored-By: <model> <noreply@anthropic.com>
Claude-Session: <session url>"
```

---

### Task 3: Container image and local compose

**Files:**
- Create: `Dockerfile`, `.dockerignore`, `docker-compose.yml`, `tests/deploy/__init__.py` (empty), `tests/deploy/test_container.py`
- Modify: `pyproject.toml` (`dev` extra gains `pyyaml>=6`)

**Interfaces:**
- Consumes: `viz-server` console script; `Settings` fields read from `VIZ_*`; the front end build `web/dist` (includes `web/dist/duckdb/**` copied from `web/public/duckdb/`).
- Produces: an image that serves on port 8000 as uid 10001 with `VIZ_WEB_DIST=/app/web/dist`. Task 5's Helm chart and Task 6's CI docker job use it.

- [ ] **Step 1: Add PyYAML to the dev extra**

In `pyproject.toml`, `[project.optional-dependencies]`, `dev`, add the line `  "pyyaml>=6",` after `"moto[s3,sts]>=5",`. Run `.venv/Scripts/python -m pip install -e ".[dev]"`.

- [ ] **Step 2: Write the failing tests**

Create `tests/deploy/__init__.py` (empty) and `tests/deploy/test_container.py`:

```python
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[2]


def _dockerfile() -> str:
    return (REPO / "Dockerfile").read_text(encoding="utf-8")


def test_image_runs_as_a_non_root_user():
    text = _dockerfile()
    assert "useradd --uid 10001" in text
    assert "\nUSER 10001\n" in text


def test_image_ships_the_whole_front_end_build():
    text = _dockerfile()
    # The whole dist, so dist/duckdb/** (the self-hosted parquet extension) comes along.
    assert "COPY --from=web /src/web/dist /app/web/dist" in text
    assert "VIZ_WEB_DIST=/app/web/dist" in text


def test_image_works_around_skipped_esbuild_postinstall():
    assert "node node_modules/esbuild/install.js" in _dockerfile()


def test_image_serves_on_all_interfaces_and_runs_only_the_server():
    text = _dockerfile()
    assert "VIZ_HOST=0.0.0.0" in text
    assert 'CMD ["viz-server"]' in text


def test_no_databricks_settings_in_container_files():
    for name in ("Dockerfile", "docker-compose.yml", ".dockerignore"):
        assert "DATABRICKS" not in (REPO / name).read_text(encoding="utf-8"), name


def test_dockerignore_keeps_local_state_out_of_the_build_context():
    lines = (REPO / ".dockerignore").read_text(encoding="utf-8").split()
    for entry in (".venv", "web/node_modules", "web/dist", ".viz-staging", ".env*", ".superpowers", ".worktrees", ".git"):
        assert entry in lines, entry


def test_compose_runs_locked_down_on_loopback():
    compose = yaml.safe_load((REPO / "docker-compose.yml").read_text(encoding="utf-8"))
    service = compose["services"]["viz-site"]
    assert service["ports"] == ["127.0.0.1:8000:8000"]
    assert service["read_only"] is True
    assert service["cap_drop"] == ["ALL"]
    assert service["environment"]["VIZ_STORAGE"] == "local"
    assert service["environment"]["VIZ_ALLOWED_HOSTS"] == "localhost,127.0.0.1"
    assert "./sample-bucket:/data:ro" in service["volumes"]
```

- [ ] **Step 3: Run them to see them fail**

Run: `.venv/Scripts/python -m pytest tests/deploy/test_container.py -v`
Expected: every test FAILS with `FileNotFoundError`.

- [ ] **Step 4: Write `Dockerfile`**

```dockerfile
# syntax=docker/dockerfile:1

# Stage 1: build the front end. Everything it needs is bundled into web/dist,
# including dist/duckdb/** (the self-hosted DuckDB parquet extension).
FROM node:24-bookworm-slim AS web
WORKDIR /src/web
COPY web/package.json web/package-lock.json ./
# npm can skip esbuild's postinstall (install-script approval); run it explicitly.
RUN npm ci && node node_modules/esbuild/install.js
COPY web/ ./
RUN npm run build

# Stage 2: the read-only server.
FROM python:3.11-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    VIZ_HOST=0.0.0.0 \
    VIZ_PORT=8000 \
    VIZ_WEB_DIST=/app/web/dist
WORKDIR /app
COPY pyproject.toml README.md LICENSE ./
COPY schemas/ schemas/
COPY skills/ skills/
COPY viz/ viz/
RUN pip install --no-cache-dir . && rm -rf /root/.cache
COPY --from=web /src/web/dist /app/web/dist
RUN useradd --uid 10001 --no-create-home --shell /usr/sbin/nologin viz
USER 10001
EXPOSE 8000
CMD ["viz-server"]
```

- [ ] **Step 5: Write `.dockerignore`**

```
.git
.venv
.viz-staging
.viz-wheel-check
.superpowers
.worktrees
.claude
.env*
**/__pycache__
web/node_modules
web/dist
web/test-results
web/playwright-report
sample-bucket
tests
docs
```

- [ ] **Step 6: Write `docker-compose.yml`**

```yaml
# Local run of the image against the synthetic sample bucket:
#   docker compose up --build   then open http://127.0.0.1:8000
services:
  viz-site:
    build: .
    ports:
      - "127.0.0.1:8000:8000"
    environment:
      VIZ_STORAGE: local
      VIZ_LOCAL_DIR: /data
      VIZ_ROOT_PREFIX: viz/
      VIZ_ALLOWED_HOSTS: localhost,127.0.0.1
    volumes:
      - ./sample-bucket:/data:ro
    read_only: true
    tmpfs:
      - /tmp
    cap_drop:
      - ALL
    security_opt:
      - no-new-privileges:true
```

- [ ] **Step 7: Run the tests and the whole suite, then commit**

Run: `.venv/Scripts/python -m pytest tests/deploy/test_container.py -v` then `.venv/Scripts/python -m pytest`
Docker is not installed on this machine; the image is built by CI (Task 6). Say so in your report.

```bash
git add Dockerfile .dockerignore docker-compose.yml pyproject.toml tests/deploy
git commit -m "feat: container image and a local compose file" -m "Adds pyyaml>=6 to the dev extra (tests parse compose, Helm values and the CI workflow).

Co-Authored-By: <model> <noreply@anthropic.com>
Claude-Session: <session url>"
```

(That is two `-m` flags: the second holds the body line, a blank line, then the two trailers adjacent. Verify with `git log -1 --format=%B` that the trailers are the last two lines and adjacent.)

---

### Task 4: AWS policies and the bucket baseline

**Files:**
- Create: `deploy/aws/server-policy.json`, `deploy/aws/publisher-policy.json`, `deploy/aws/bucket-policy.json`, `deploy/aws/README.md`, `tests/deploy/test_aws_policies.py`

**Interfaces:**
- Consumes: the S3 calls the code makes. Server (`viz/storage/s3.py` via the read-only routes): `ListObjectsV2`, `HeadObject`, `GetObject` (ranged). CLI publisher: those plus `PutObject`, `DeleteObject`, `CopyObject` (`viz move`). All under the root prefix, default `viz/`.
- Produces: policy files with placeholders `REPLACE_ME-viz-bucket`, account `123456789012`, `vpce-REPLACE_ME`, role names `viz-site-server` and `viz-site-publisher`. Task 5's `values.yaml` and Task 7's guide refer to them.

- [ ] **Step 1: Write the failing tests**

Create `tests/deploy/test_aws_policies.py`:

```python
import json
import re
from pathlib import Path

AWS = Path(__file__).resolve().parents[2] / "deploy" / "aws"


def _policy(name: str) -> dict:
    return json.loads((AWS / name).read_text(encoding="utf-8"))


def _actions(policy: dict) -> set[str]:
    out = set()
    for statement in policy["Statement"]:
        if statement["Effect"] == "Allow":
            actions = statement["Action"]
            out.update([actions] if isinstance(actions, str) else actions)
    return out


def test_server_policy_is_read_only():
    assert _actions(_policy("server-policy.json")) == {"s3:ListBucket", "s3:GetObject", "kms:Decrypt"}


def test_publisher_policy_can_write_but_not_administer():
    actions = _actions(_policy("publisher-policy.json"))
    assert actions == {"s3:ListBucket", "s3:GetObject", "s3:PutObject", "s3:DeleteObject", "kms:Decrypt", "kms:GenerateDataKey"}
    assert not any(a.endswith("*") for a in actions)


def test_object_access_is_limited_to_the_root_prefix():
    for name in ("server-policy.json", "publisher-policy.json"):
        for statement in _policy(name)["Statement"]:
            actions = statement["Action"]
            actions = [actions] if isinstance(actions, str) else actions
            if any(a in ("s3:GetObject", "s3:PutObject", "s3:DeleteObject") for a in actions):
                assert statement["Resource"] == "arn:aws:s3:::REPLACE_ME-viz-bucket/viz/*", name
            if "s3:ListBucket" in actions:
                assert statement["Condition"]["StringLike"]["s3:prefix"] == ["viz/", "viz/*"], name


def test_bucket_policy_denies_plain_http():
    statements = _policy("bucket-policy.json")["Statement"]
    deny = [s for s in statements if s["Effect"] == "Deny" and "aws:SecureTransport" in json.dumps(s)]
    assert deny and deny[0]["Condition"] == {"Bool": {"aws:SecureTransport": "false"}}


def test_vpce_deny_exempts_the_publisher_role():
    statements = _policy("bucket-policy.json")["Statement"]
    vpce = [s for s in statements if "aws:SourceVpce" in json.dumps(s)]
    assert len(vpce) == 1
    condition = vpce[0]["Condition"]
    assert condition["StringNotEquals"]["aws:SourceVpce"] == "vpce-REPLACE_ME"
    assert condition["ArnNotLike"]["aws:PrincipalArn"] == ["arn:aws:iam::123456789012:role/viz-site-publisher"]


def test_only_placeholder_accounts_and_names():
    for path in AWS.glob("*"):
        text = path.read_text(encoding="utf-8")
        for account in re.findall(r"\b\d{12}\b", text):
            assert account == "123456789012", f"{path.name}: {account}"
        assert "DATABRICKS" not in text


def test_readme_covers_the_bucket_baseline():
    text = (AWS / "README.md").read_text(encoding="utf-8")
    for phrase in ("Block Public Access", "SSE-KMS", "Versioning", "NoncurrentVersionExpiration", "CloudTrail", "IRSA", "node role"):
        assert phrase in text, phrase
```

- [ ] **Step 2: Run them to see them fail**

Run: `.venv/Scripts/python -m pytest tests/deploy/test_aws_policies.py -v`
Expected: every test FAILS with `FileNotFoundError`.

- [ ] **Step 3: Write `deploy/aws/server-policy.json`**

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "ListTheVizPrefix",
      "Effect": "Allow",
      "Action": "s3:ListBucket",
      "Resource": "arn:aws:s3:::REPLACE_ME-viz-bucket",
      "Condition": {"StringLike": {"s3:prefix": ["viz/", "viz/*"]}}
    },
    {
      "Sid": "ReadVizObjects",
      "Effect": "Allow",
      "Action": "s3:GetObject",
      "Resource": "arn:aws:s3:::REPLACE_ME-viz-bucket/viz/*"
    },
    {
      "Sid": "DecryptWithTheBucketKey",
      "Effect": "Allow",
      "Action": "kms:Decrypt",
      "Resource": "arn:aws:kms:REPLACE_ME-region:123456789012:key/REPLACE_ME-key-id"
    }
  ]
}
```

- [ ] **Step 4: Write `deploy/aws/publisher-policy.json`**

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "ListTheVizPrefix",
      "Effect": "Allow",
      "Action": "s3:ListBucket",
      "Resource": "arn:aws:s3:::REPLACE_ME-viz-bucket",
      "Condition": {"StringLike": {"s3:prefix": ["viz/", "viz/*"]}}
    },
    {
      "Sid": "ReadAndWriteVizObjects",
      "Effect": "Allow",
      "Action": ["s3:GetObject", "s3:PutObject", "s3:DeleteObject"],
      "Resource": "arn:aws:s3:::REPLACE_ME-viz-bucket/viz/*"
    },
    {
      "Sid": "EncryptAndDecryptWithTheBucketKey",
      "Effect": "Allow",
      "Action": ["kms:Decrypt", "kms:GenerateDataKey"],
      "Resource": "arn:aws:kms:REPLACE_ME-region:123456789012:key/REPLACE_ME-key-id"
    }
  ]
}
```

- [ ] **Step 5: Write `deploy/aws/bucket-policy.json`**

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "DenyPlainHttp",
      "Effect": "Deny",
      "Principal": "*",
      "Action": "s3:*",
      "Resource": ["arn:aws:s3:::REPLACE_ME-viz-bucket", "arn:aws:s3:::REPLACE_ME-viz-bucket/*"],
      "Condition": {"Bool": {"aws:SecureTransport": "false"}}
    },
    {
      "Sid": "DenyReadsOutsideTheVpcEndpointExceptPublishers",
      "Effect": "Deny",
      "Principal": "*",
      "Action": ["s3:GetObject", "s3:ListBucket"],
      "Resource": ["arn:aws:s3:::REPLACE_ME-viz-bucket", "arn:aws:s3:::REPLACE_ME-viz-bucket/*"],
      "Condition": {
        "StringNotEquals": {"aws:SourceVpce": "vpce-REPLACE_ME"},
        "ArnNotLike": {"aws:PrincipalArn": ["arn:aws:iam::123456789012:role/viz-site-publisher"]}
      }
    }
  ]
}
```

- [ ] **Step 6: Write `deploy/aws/README.md`**

````markdown
# AWS setup for viz-site

Everything here uses placeholders: replace `REPLACE_ME-viz-bucket`, the
account id `123456789012`, `REPLACE_ME-region`, `REPLACE_ME-key-id` and
`vpce-REPLACE_ME` with your own values. Never commit real ones back to the
repo.

## 1. The bucket baseline (spec 12.5)

Create one bucket for viz-site, then set:

- **Block Public Access**: all four settings on.
- **Default encryption**: SSE-KMS with a customer-managed key, Bucket Key
  enabled.
- **Versioning**: enabled, with a lifecycle rule
  `NoncurrentVersionExpiration` of 30 days, so an overwritten or deleted
  chart can be recovered for a month.
- **Logging**: S3 server access logging to a separate log bucket, or
  CloudTrail data events for this bucket.
- **Bucket policy**: `bucket-policy.json`. It denies plain HTTP, and denies
  reads that do not come through the cluster's S3 VPC endpoint, except for
  the publisher role, because publishers run `viz publish` from their own
  machines.

## 2. Roles

| Role | Policy | Who uses it |
|---|---|---|
| `viz-site-server` | `server-policy.json` (list and read under `viz/`, KMS decrypt) | The pods, through IRSA or EKS Pod Identity. Never the node role. |
| `viz-site-publisher` | `publisher-policy.json` (also put and delete under `viz/`, KMS encrypt) | People and agents running `viz publish` and `viz move`. |

If `VIZ_ROOT_PREFIX` is not `viz/`, change `viz/` in both policies.

For IRSA, the server role's trust policy allows the cluster's OIDC provider
for the service account `viz-site` in the release namespace. Put the role
ARN in the Helm value `serviceAccount.roleArn`.

## 3. What the site does with S3

The server only lists, heads and gets objects under the root prefix. The
`viz` CLI also puts, deletes and copies (`viz move`). Neither touches any
other prefix or bucket.
````

- [ ] **Step 7: Run the tests and the whole suite, then commit**

Run: `.venv/Scripts/python -m pytest tests/deploy/test_aws_policies.py -v` then `.venv/Scripts/python -m pytest`

```bash
git add deploy/aws tests/deploy/test_aws_policies.py
git commit -m "docs: AWS policies and bucket baseline with placeholders" -m "Co-Authored-By: <model> <noreply@anthropic.com>
Claude-Session: <session url>"
```

---

### Task 5: Helm chart

**Files:**
- Create: `deploy/helm/viz-site/Chart.yaml`, `values.yaml`, `templates/_helpers.tpl`, `templates/serviceaccount.yaml`, `templates/deployment.yaml`, `templates/service.yaml`, `templates/ingress.yaml`, `templates/networkpolicy.yaml`, `templates/NOTES.txt`, `tests/deploy/test_helm.py`

**Interfaces:**
- Consumes: the image from Task 3 (port 8000, uid 10001, `/api/health`); the role names from Task 4; `Settings` env vars `VIZ_STORAGE`, `VIZ_S3_BUCKET`, `VIZ_ROOT_PREFIX`, `VIZ_ALLOWED_HOSTS`, `VIZ_AUTH_HEADER`.
- Produces: a chart Task 6 lints and renders with `helm template deploy/helm/viz-site`.

- [ ] **Step 1: Write the failing tests**

Create `tests/deploy/test_helm.py`:

```python
from pathlib import Path

import yaml

CHART = Path(__file__).resolve().parents[2] / "deploy" / "helm" / "viz-site"


def _values() -> dict:
    return yaml.safe_load((CHART / "values.yaml").read_text(encoding="utf-8"))


def _template(name: str) -> str:
    return (CHART / "templates" / name).read_text(encoding="utf-8")


def test_chart_metadata():
    chart = yaml.safe_load((CHART / "Chart.yaml").read_text(encoding="utf-8"))
    assert chart["apiVersion"] == "v2"
    assert chart["name"] == "viz-site"


def test_values_hold_placeholders_only():
    values = _values()
    assert "REPLACE_ME" in values["image"]["repository"]
    assert "REPLACE_ME" in values["bucket"]["name"]
    assert values["serviceAccount"]["roleArn"].startswith("arn:aws:iam::123456789012:role/")
    assert values["allowedHosts"].endswith("example.com")


def test_pod_is_locked_down():
    text = _template("deployment.yaml")
    for fragment in (
        "automountServiceAccountToken: false",
        "runAsNonRoot: true",
        "runAsUser: 10001",
        "readOnlyRootFilesystem: true",
        "allowPrivilegeEscalation: false",
        "- ALL",
        "type: RuntimeDefault",
        "emptyDir: {}",
        "mountPath: /tmp",
        "resources:",
    ):
        assert fragment in text, fragment


def test_probes_send_an_allowed_host_header():
    text = _template("deployment.yaml")
    assert text.count("path: /api/health") == 2
    assert text.count("name: Host") == 2


def test_server_reads_s3_and_the_allow_list_from_values():
    text = _template("deployment.yaml")
    for name in ("VIZ_STORAGE", "VIZ_S3_BUCKET", "VIZ_ROOT_PREFIX", "VIZ_ALLOWED_HOSTS", "VIZ_AUTH_HEADER", "AWS_REGION"):
        assert f"name: {name}" in text, name
    assert 'value: "s3"' in text


def test_service_is_cluster_internal():
    assert "type: ClusterIP" in _template("service.yaml")


def test_service_account_uses_irsa_not_the_node_role():
    text = _template("serviceaccount.yaml")
    assert "eks.amazonaws.com/role-arn" in text
    assert "automountServiceAccountToken: false" in text


def test_ingress_is_internal_and_rate_limited():
    text = _template("ingress.yaml")
    assert "nginx.ingress.kubernetes.io/limit-rps" in text
    assert "alb.ingress.kubernetes.io/scheme: internal" in text
    assert "internal" in text.lower()


def test_network_policy_limits_ingress_and_egress():
    text = _template("networkpolicy.yaml")
    assert "- Ingress" in text and "- Egress" in text
    assert "port: 53" in text
    assert "port: 443" in text
    assert "ipBlock" in text


def test_no_databricks_anywhere_in_the_chart():
    for path in CHART.rglob("*"):
        if path.is_file():
            assert "DATABRICKS" not in path.read_text(encoding="utf-8"), path.name
```

- [ ] **Step 2: Run them to see them fail**

Run: `.venv/Scripts/python -m pytest tests/deploy/test_helm.py -v`
Expected: every test FAILS with `FileNotFoundError`.

- [ ] **Step 3: Write `deploy/helm/viz-site/Chart.yaml`**

```yaml
apiVersion: v2
name: viz-site
description: Read-only viewer over an S3 folder of charts and dashboards
type: application
version: 0.1.0
appVersion: "0.1.0"
```

- [ ] **Step 4: Write `deploy/helm/viz-site/values.yaml`**

```yaml
# Every value here is a placeholder. Copy this file, fill it in, and keep the
# filled copy out of the repo.
image:
  repository: REPLACE_ME.dkr.ecr.REPLACE_ME-region.amazonaws.com/viz-site
  tag: "0.1.0"
  pullPolicy: IfNotPresent

replicaCount: 2

bucket:
  name: REPLACE_ME-viz-bucket
  rootPrefix: viz/
  region: REPLACE_ME-region

# VIZ_ALLOWED_HOSTS: the host names the site answers to. Requests with any
# other Host header get 400. The first entry is also sent by the probes.
allowedHosts: viz.internal.example.com

# Header the company SSO proxy sets with the signed-in user (logged only).
authHeader: X-Forwarded-Email

serviceAccount:
  name: viz-site
  # IRSA: the IAM role the pods assume (deploy/aws/server-policy.json).
  # Never grant these permissions to the node role.
  roleArn: arn:aws:iam::123456789012:role/viz-site-server

ingress:
  enabled: true
  # The site must never be internet-facing: it serves company data to anyone
  # who can reach it. Use an internal load balancer.
  className: nginx
  host: viz.internal.example.com
  rateLimitPerSecond: 10
  annotations: {}

networkPolicy:
  enabled: true
  # Namespace of the ingress controller; only it may reach the pods.
  ingressControllerNamespace: ingress-nginx
  # Egress on 443: the S3 VPC endpoint (or S3 prefix-list CIDRs) and the STS
  # endpoint IRSA uses. Replace with your ranges.
  egressCidrs:
    - 10.0.0.0/8

resources:
  requests:
    cpu: 100m
    memory: 256Mi
  limits:
    cpu: "1"
    memory: 512Mi
```

- [ ] **Step 5: Write `deploy/helm/viz-site/templates/_helpers.tpl`**

```
{{- define "viz-site.name" -}}
{{- .Chart.Name -}}
{{- end -}}

{{- define "viz-site.fullname" -}}
{{- printf "%s-%s" .Release.Name .Chart.Name | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{- define "viz-site.labels" -}}
app.kubernetes.io/name: {{ include "viz-site.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
{{- end -}}

{{- define "viz-site.selectorLabels" -}}
app.kubernetes.io/name: {{ include "viz-site.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end -}}

{{- define "viz-site.probeHost" -}}
{{- index (splitList "," .Values.allowedHosts) 0 | trim -}}
{{- end -}}
```

- [ ] **Step 6: Write `deploy/helm/viz-site/templates/serviceaccount.yaml`**

```yaml
apiVersion: v1
kind: ServiceAccount
metadata:
  name: {{ .Values.serviceAccount.name }}
  labels:
    {{- include "viz-site.labels" . | nindent 4 }}
  annotations:
    # IRSA: pods assume this role; the node role gets no S3 access.
    eks.amazonaws.com/role-arn: {{ .Values.serviceAccount.roleArn | quote }}
automountServiceAccountToken: false
```

- [ ] **Step 7: Write `deploy/helm/viz-site/templates/deployment.yaml`**

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: {{ include "viz-site.fullname" . }}
  labels:
    {{- include "viz-site.labels" . | nindent 4 }}
spec:
  replicas: {{ .Values.replicaCount }}
  selector:
    matchLabels:
      {{- include "viz-site.selectorLabels" . | nindent 6 }}
  template:
    metadata:
      labels:
        {{- include "viz-site.selectorLabels" . | nindent 8 }}
    spec:
      serviceAccountName: {{ .Values.serviceAccount.name }}
      automountServiceAccountToken: false
      securityContext:
        runAsNonRoot: true
        runAsUser: 10001
        runAsGroup: 10001
        fsGroup: 10001
        seccompProfile:
          type: RuntimeDefault
      containers:
        - name: viz-site
          image: "{{ .Values.image.repository }}:{{ .Values.image.tag }}"
          imagePullPolicy: {{ .Values.image.pullPolicy }}
          ports:
            - name: http
              containerPort: 8000
          env:
            - name: VIZ_STORAGE
              value: "s3"
            - name: VIZ_S3_BUCKET
              value: {{ .Values.bucket.name | quote }}
            - name: VIZ_ROOT_PREFIX
              value: {{ .Values.bucket.rootPrefix | quote }}
            - name: VIZ_ALLOWED_HOSTS
              value: {{ .Values.allowedHosts | quote }}
            - name: VIZ_AUTH_HEADER
              value: {{ .Values.authHeader | quote }}
            - name: AWS_REGION
              value: {{ .Values.bucket.region | quote }}
          securityContext:
            allowPrivilegeEscalation: false
            readOnlyRootFilesystem: true
            capabilities:
              drop:
                - ALL
          # Probes must send an allowed Host header: the pod IP is rejected by
          # the host allow-list with 400.
          readinessProbe:
            httpGet:
              path: /api/health
              port: http
              httpHeaders:
                - name: Host
                  value: {{ include "viz-site.probeHost" . | quote }}
          livenessProbe:
            httpGet:
              path: /api/health
              port: http
              httpHeaders:
                - name: Host
                  value: {{ include "viz-site.probeHost" . | quote }}
          resources:
            {{- toYaml .Values.resources | nindent 12 }}
          volumeMounts:
            - name: tmp
              mountPath: /tmp
      volumes:
        - name: tmp
          emptyDir: {}
```

- [ ] **Step 8: Write `deploy/helm/viz-site/templates/service.yaml`**

```yaml
apiVersion: v1
kind: Service
metadata:
  name: {{ include "viz-site.fullname" . }}
  labels:
    {{- include "viz-site.labels" . | nindent 4 }}
spec:
  type: ClusterIP
  selector:
    {{- include "viz-site.selectorLabels" . | nindent 4 }}
  ports:
    - name: http
      port: 80
      targetPort: http
```

- [ ] **Step 9: Write `deploy/helm/viz-site/templates/ingress.yaml`**

```yaml
{{- if .Values.ingress.enabled }}
# Internal only: the site serves company data to anyone who can reach it, so
# it must sit behind an internal load balancer and the company SSO proxy.
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: {{ include "viz-site.fullname" . }}
  labels:
    {{- include "viz-site.labels" . | nindent 4 }}
  annotations:
    # ingress-nginx: per-client-IP request rate limit.
    nginx.ingress.kubernetes.io/limit-rps: {{ .Values.ingress.rateLimitPerSecond | quote }}
    # AWS Load Balancer Controller: never create an internet-facing ALB.
    alb.ingress.kubernetes.io/scheme: internal
    {{- with .Values.ingress.annotations }}
    {{- toYaml . | nindent 4 }}
    {{- end }}
spec:
  ingressClassName: {{ .Values.ingress.className }}
  rules:
    - host: {{ .Values.ingress.host | quote }}
      http:
        paths:
          - path: /
            pathType: Prefix
            backend:
              service:
                name: {{ include "viz-site.fullname" . }}
                port:
                  name: http
{{- end }}
```

- [ ] **Step 10: Write `deploy/helm/viz-site/templates/networkpolicy.yaml`**

```yaml
{{- if .Values.networkPolicy.enabled }}
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: {{ include "viz-site.fullname" . }}
  labels:
    {{- include "viz-site.labels" . | nindent 4 }}
spec:
  podSelector:
    matchLabels:
      {{- include "viz-site.selectorLabels" . | nindent 6 }}
  policyTypes:
    - Ingress
    - Egress
  ingress:
    # Only the ingress controller may reach the pods.
    - from:
        - namespaceSelector:
            matchLabels:
              kubernetes.io/metadata.name: {{ .Values.networkPolicy.ingressControllerNamespace }}
      ports:
        - port: 8000
          protocol: TCP
  egress:
    # DNS.
    - to:
        - namespaceSelector:
            matchLabels:
              kubernetes.io/metadata.name: kube-system
      ports:
        - port: 53
          protocol: UDP
        - port: 53
          protocol: TCP
    # S3 and STS over HTTPS only.
    - to:
        {{- range .Values.networkPolicy.egressCidrs }}
        - ipBlock:
            cidr: {{ . }}
        {{- end }}
      ports:
        - port: 443
          protocol: TCP
{{- end }}
```

- [ ] **Step 11: Write `deploy/helm/viz-site/templates/NOTES.txt`**

```
viz-site is installed as {{ include "viz-site.fullname" . }}.

It answers only to: {{ .Values.allowedHosts }}
Check it through the ingress: https://{{ .Values.ingress.host }}/api/health

If pods never become ready, check that allowedHosts includes the host the
probes send ({{ include "viz-site.probeHost" . }}) and that the IRSA role
{{ .Values.serviceAccount.roleArn }} can read s3://{{ .Values.bucket.name }}/{{ .Values.bucket.rootPrefix }}.
```

- [ ] **Step 12: Run the tests and the whole suite, then commit**

Run: `.venv/Scripts/python -m pytest tests/deploy/test_helm.py -v` then `.venv/Scripts/python -m pytest`
Helm is not installed on this machine; CI lints and renders the chart (Task 6). Say so in your report.

```bash
git add deploy/helm tests/deploy/test_helm.py
git commit -m "feat: Helm chart with the spec 12.5 security defaults" -m "Co-Authored-By: <model> <noreply@anthropic.com>
Claude-Session: <session url>"
```

---

### Task 6: GitHub Actions CI

**Files:**
- Create: `.github/workflows/ci.yml`, `tests/deploy/test_ci.py`

**Interfaces:**
- Consumes: `pyproject.toml` `dev` extra; `web/package.json` scripts `typecheck`, `test`, `build`, `e2e`; `web/playwright.config.ts`, which starts `<repo>/.venv/bin/viz-server` and runs `npm run build` in its global setup; the `Dockerfile`; the Helm chart.
- Produces: jobs `python`, `web`, `docker`, `helm`, `gitleaks` on every push to `main` and every pull request.

- [ ] **Step 1: Write the failing tests**

Create `tests/deploy/test_ci.py`:

```python
from pathlib import Path

import yaml

WORKFLOW = Path(__file__).resolve().parents[2] / ".github" / "workflows" / "ci.yml"


def _workflow() -> dict:
    return yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))


def _runs(job: dict) -> str:
    return "\n".join(step.get("run", "") for step in job["steps"])


def test_triggers():
    wf = _workflow()
    # PyYAML reads the bare key `on` as the boolean True.
    triggers = wf.get("on", wf.get(True))
    assert triggers["push"]["branches"] == ["main"]
    assert "pull_request" in triggers


def test_all_jobs_exist():
    assert set(_workflow()["jobs"]) == {"python", "web", "docker", "helm", "gitleaks"}


def test_python_job_runs_the_suite():
    assert "python -m pytest" in _runs(_workflow()["jobs"]["python"])


def test_web_job_creates_the_repo_venv():
    runs = _runs(_workflow()["jobs"]["web"])
    assert "python -m venv .venv" in runs
    assert '.venv/bin/python -m pip install -e ".[dev]"' in runs


def test_web_job_handles_esbuild_and_chromium():
    runs = _runs(_workflow()["jobs"]["web"])
    assert "node node_modules/esbuild/install.js" in runs
    assert "npx playwright install --with-deps chromium" in runs
    for script in ("npm run typecheck", "npm test", "npm run e2e"):
        assert script in runs, script


def test_docker_and_helm_jobs():
    jobs = _workflow()["jobs"]
    assert "docker build" in _runs(jobs["docker"])
    helm = _runs(jobs["helm"])
    assert "helm lint deploy/helm/viz-site" in helm
    assert "helm template" in helm


def test_gitleaks_scans_full_history():
    job = _workflow()["jobs"]["gitleaks"]
    checkout = next(step for step in job["steps"] if step.get("uses", "").startswith("actions/checkout"))
    assert checkout["with"]["fetch-depth"] == 0
    assert any(step.get("uses", "").startswith("gitleaks/gitleaks-action") for step in job["steps"])


def test_integration_tests_never_run_in_ci():
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "VIZ_INTEGRATION" not in text
    assert "DATABRICKS" not in text


def test_workflow_token_is_read_only():
    assert _workflow()["permissions"] == {"contents": "read"}
```

- [ ] **Step 2: Run them to see them fail**

Run: `.venv/Scripts/python -m pytest tests/deploy/test_ci.py -v`
Expected: every test FAILS with `FileNotFoundError`.

- [ ] **Step 3: Write `.github/workflows/ci.yml`**

```yaml
name: ci

on:
  push:
    branches: [main]
  pull_request:

permissions:
  contents: read

jobs:
  python:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
      - run: python -m pip install -e ".[dev]"
      - run: python -m pytest

  web:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
      - uses: actions/setup-node@v4
        with:
          node-version: "24"
          cache: npm
          cache-dependency-path: web/package-lock.json
      # Playwright starts <repo>/.venv/bin/viz-server, so the venv must live at the repo root.
      - run: |
          python -m venv .venv
          .venv/bin/python -m pip install -e ".[dev]"
      # npm can skip esbuild's postinstall; run it explicitly.
      - run: |
          npm ci
          node node_modules/esbuild/install.js
        working-directory: web
      - run: |
          npm run typecheck
          npm test
        working-directory: web
      - run: |
          npx playwright install --with-deps chromium
          npm run e2e
        working-directory: web

  docker:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: docker build -t viz-site:ci .

  helm:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: azure/setup-helm@v4
      - run: |
          helm lint deploy/helm/viz-site
          helm template ci deploy/helm/viz-site > /tmp/rendered.yaml
          cat /tmp/rendered.yaml

  gitleaks:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0
      - uses: gitleaks/gitleaks-action@v2
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
```

- [ ] **Step 4: Run the tests and the whole suite, then commit**

Run: `.venv/Scripts/python -m pytest tests/deploy/test_ci.py -v` then `.venv/Scripts/python -m pytest`
The workflow only runs on GitHub; the controller checks the first run after the push.

```bash
git add .github/workflows/ci.yml tests/deploy/test_ci.py
git commit -m "ci: python, web, docker, helm and gitleaks jobs" -m "Co-Authored-By: <model> <noreply@anthropic.com>
Claude-Session: <session url>"
```

---

### Task 7: Opt-in S3 test and the work-machine setup guide

**Files:**
- Create: `tests/storage/test_s3_integration.py`, `docs/work-setup.md`, `tests/test_work_setup_doc.py`
- Modify: `README.md` (one pointer paragraph)

**Interfaces:**
- Consumes: `viz.storage.s3.S3Storage(bucket, client=None)` with `put/get/head/list/copy/delete`; `viz.config.Settings.model_fields`; `viz.publish.cli.build_parser()`; files from Tasks 2 to 6.
- Produces: the guide the user follows at work.

- [ ] **Step 1: Write the failing doc test**

Create `tests/test_work_setup_doc.py`:

```python
"""docs/work-setup.md must stay true to the code: every setting, every command, every file it names."""
import argparse
import re
from pathlib import Path

from viz.config import Settings
from viz.publish.cli import build_parser

REPO = Path(__file__).resolve().parents[1]
GUIDE = REPO / "docs" / "work-setup.md"


def _text() -> str:
    return GUIDE.read_text(encoding="utf-8")


def test_every_setting_is_documented():
    text = _text()
    for field in Settings.model_fields:
        assert f"VIZ_{field.upper()}" in text, f"VIZ_{field.upper()} is not documented"


def test_databricks_variables_are_documented():
    text = _text()
    for name in ("DATABRICKS_HOST", "DATABRICKS_TOKEN", "DATABRICKS_WAREHOUSE_ID"):
        assert name in text, name


def test_every_viz_command_named_exists():
    parser = build_parser()
    commands = next(a for a in parser._actions if isinstance(a, argparse._SubParsersAction)).choices
    for name in re.findall(r"\bviz ([a-z][a-z-]*)", _text()):
        assert name in commands, f"docs/work-setup.md names `viz {name}`"


def test_every_repo_path_named_exists():
    # web/ is left out on purpose: web/dist only exists after a build.
    for path in re.findall(r"`((?:deploy|docs|skills|tests)/[A-Za-z0-9_./-]+)`", _text()):
        assert (REPO / path).exists(), path


def test_the_guide_covers_the_real_infrastructure_checks():
    text = _text()
    for phrase in ("VIZ_INTEGRATION=1", "VIZ_IT_S3_BUCKET", "tests/publish/test_query_integration.py",
                   "tests/storage/test_s3_integration.py", "viz install-skill", "helm install", "Genie Code"):
        assert phrase in text, phrase
```

- [ ] **Step 2: Run it to see it fail**

Run: `.venv/Scripts/python -m pytest tests/test_work_setup_doc.py -v`
Expected: every test FAILS with `FileNotFoundError`.

- [ ] **Step 3: Write `tests/storage/test_s3_integration.py`**

```python
"""Opt-in: a round trip against a real S3 bucket. Never runs in CI or on pull requests.
Uses a unique throwaway prefix and deletes everything it wrote."""
import os
import uuid

import pytest

from viz.storage import NotFound
from viz.storage.s3 import S3Storage

pytestmark = pytest.mark.skipif(
    os.environ.get("VIZ_INTEGRATION") != "1" or not os.environ.get("VIZ_IT_S3_BUCKET"),
    reason="set VIZ_INTEGRATION=1 and VIZ_IT_S3_BUCKET (and AWS credentials) to run",
)


def test_round_trip_against_a_real_bucket():
    storage = S3Storage(os.environ["VIZ_IT_S3_BUCKET"])
    prefix = f"{os.environ.get('VIZ_IT_S3_PREFIX', 'viz/')}integration-{uuid.uuid4().hex[:12]}/"
    first, second = f"{prefix}a.json", f"{prefix}b.json"
    try:
        storage.put(first, b'{"ok": true}', "application/json")
        assert storage.get(first) == b'{"ok": true}'
        assert storage.head(first).size == 12
        assert b"".join(storage.open(first, 1, 4)) == b'"ok"'
        storage.copy(first, second)
        assert [info.key for info in storage.list(prefix)] == [first, second]
    finally:
        for key in (first, second):
            try:
                storage.delete(key)
            except NotFound:
                pass
    assert storage.list(prefix) == []
```

Check `viz/storage/__init__.py` exports `NotFound` (`from viz.storage import NotFound` is already used by `viz/publish/validate.py`), and that `S3Storage.open(key, start, end)` treats `end` as inclusive (see the `Storage` protocol docstring). If `delete` does not raise `NotFound` for a missing key, the `try/except` is still harmless.

Run: `.venv/Scripts/python -m pytest tests/storage/test_s3_integration.py -v`
Expected: 1 skipped.

- [ ] **Step 4: Write `docs/work-setup.md`**

````markdown
# Setting up viz-site on a work machine

This guide takes a fresh clone to a working site on your company's AWS
account, with charts published from Databricks. Steps 1 to 4 need only your
laptop; steps 5 and 6 need the company's AWS account and Databricks
workspace.

## What you need

- Python 3.11 and Git.
- Node.js 24 (only to build the front end outside Docker).
- Docker, `kubectl` and Helm 3 for the deployment.
- A Databricks personal access token and a SQL warehouse id, for `viz query`.
- AWS credentials that can assume the publisher role, for `viz publish`.

## 1. Clone and install the CLI

```
git clone https://github.com/Trippical/viz-studio.git viz-site
cd viz-site
python3.11 -m venv .venv
.venv/bin/python -m pip install -e ".[databricks]"
.venv/bin/viz --version
```

On Windows use `py -3.11 -m venv .venv` and `.venv\Scripts\...`. Add
`[dev]` (`".[databricks,dev]"`) if you want to run the tests.

## 2. Settings

Everything is configured with environment variables. The server and the CLI
share the `VIZ_*` ones.

| Variable | Default | Used by | What it does |
|---|---|---|---|
| `VIZ_STORAGE` | `local` | both | `local` (a folder) or `s3` |
| `VIZ_S3_BUCKET` | none | both | Bucket name when `VIZ_STORAGE=s3` |
| `VIZ_ROOT_PREFIX` | `viz/` | both | Key prefix everything lives under |
| `VIZ_LOCAL_DIR` | `./sample-bucket` | both | Folder used when `VIZ_STORAGE=local` |
| `VIZ_TREE_TTL_SECONDS` | `60` | server | How long the folder tree is cached |
| `VIZ_ALLOWED_HOSTS` | `localhost,127.0.0.1,testserver` | server | Host names the site answers to; anything else gets 400. Must be set in deployment |
| `VIZ_AUTH_HEADER` | `X-Forwarded-Email` | server | Identity header from the SSO proxy (logged, not enforced) |
| `VIZ_MAX_DOCUMENT_BYTES` | `1048576` | server | Largest chart.json or dashboard file served |
| `VIZ_WEB_DIST` | `./web/dist` | server | Built front end |
| `VIZ_HOST` | `127.0.0.1` | server | Bind address (`0.0.0.0` in the container) |
| `VIZ_PORT` | `8000` | server | Port |
| `VIZ_AUTHOR` | none | CLI | Author when there is no Databricks login (see below) |
| `VIZ_QUERY_DENY` | empty | CLI | Comma-separated catalogs or `catalog.schema` that `viz query` refuses. A guard against accidents, not a permission boundary |
| `VIZ_PII_PATTERN` | names like email, ssn, phone | CLI | Column names that trigger a personal-data warning |
| `VIZ_STAGING_DIR` | `./.viz-staging` | CLI | Where charts are staged before publishing |
| `DATABRICKS_HOST` | none | CLI only | Workspace URL, for `viz query` |
| `DATABRICKS_TOKEN` | none | CLI only | Personal access token. Keep it in your shell or a secret store, never in a file in the repo |
| `DATABRICKS_WAREHOUSE_ID` | none | CLI only | SQL warehouse id, or pass `--warehouse` |

Author: `viz query` stamps charts with your Databricks login, and
`viz validate` confirms it with Databricks. Charts staged from files use
`VIZ_AUTHOR`, then your AWS identity, then `<user>@local`.

## 3. Try it locally

With Docker:

```
docker compose up --build
```

Then open http://127.0.0.1:8000. It serves the synthetic `sample-bucket`,
including the chart gallery at `/d/examples/gallery`.

Without Docker, build the front end once and run the server:

```
cd web
npm ci
node node_modules/esbuild/install.js
npm run build
cd ..
VIZ_WEB_DIST=web/dist .venv/bin/viz-server
```

## 4. Install the skill

```
.venv/bin/viz install-skill
```

This copies the `publish-viz` skill to `~/.claude/skills/publish-viz/`, where
Claude Code finds it. For Databricks Genie Code, the skill folder location is
not confirmed yet: find where your workspace loads skills from and run
`viz install-skill --dest <that folder>`. The skill teaches the whole path
below; its source is `skills/publish-viz/SKILL.md`.

## 5. Prove the real integrations

Run these before anyone relies on the site. Each is skipped unless you opt
in, and neither ever runs in CI.

Databricks (runs `SELECT 1` on your warehouse):

```
export VIZ_INTEGRATION=1 DATABRICKS_HOST=... DATABRICKS_TOKEN=... DATABRICKS_WAREHOUSE_ID=...
.venv/bin/python -m pytest tests/publish/test_query_integration.py -v
```

S3 (writes, reads, copies and deletes two small objects under a throwaway
prefix; needs the publisher role's credentials):

```
export VIZ_INTEGRATION=1 VIZ_IT_S3_BUCKET=your-viz-bucket
.venv/bin/python -m pytest tests/storage/test_s3_integration.py -v
```

Then publish one real chart end to end:

```
export VIZ_STORAGE=s3 VIZ_S3_BUCKET=your-viz-bucket
echo "SELECT 'a' AS label, 1 AS value" > first.sql
.venv/bin/viz query --sql @first.sql --id smoke/first-chart
.venv/bin/viz validate .viz-staging/charts/smoke/first-chart
.venv/bin/viz publish .viz-staging/charts/smoke/first-chart
```

## 6. Deploy

1. Create the bucket, roles and policies: `deploy/aws/README.md`.
2. Build and push the image to your registry:
   `docker build -t <registry>/viz-site:0.1.0 .` then `docker push`.
3. Copy `deploy/helm/viz-site/values.yaml`, fill in every `REPLACE_ME` and
   `example.com` value, and install:
   `helm install viz-site deploy/helm/viz-site -f my-values.yaml -n viz --create-namespace`.
4. Put the site behind the company SSO proxy and check
   `https://<your host>/api/health`, then open `/c/smoke/first-chart`.

## Troubleshooting

| Symptom | Cause |
|---|---|
| Every request returns 400 | The host is not in `VIZ_ALLOWED_HOSTS` (Helm: `allowedHosts`) |
| Pods never become ready | Same, for the probe's Host header; or the IRSA role cannot read the bucket |
| Large-data charts fail to load | `web/dist/duckdb/` is missing from the build; the DuckDB parquet extension is self-hosted and pinned to DuckDB v1.4.3, so re-pin it when upgrading `@duckdb/duckdb-wasm` |
| `viz validate` says the author does not match | Without `DATABRICKS_HOST` and `DATABRICKS_TOKEN`, set `VIZ_AUTHOR` to your Databricks login |
| `viz query` says the query is refused | `VIZ_QUERY_DENY` lists that catalog or schema |
````

- [ ] **Step 5: Point the README at the guide**

In `README.md`, directly below the first heading `# viz-site` and its
opening paragraph (above `## Trust assumptions, read these first`), add:

```markdown
Setting it up at work (fresh clone, AWS, Databricks, deployment):
[`docs/work-setup.md`](docs/work-setup.md).
```

- [ ] **Step 6: Run the tests and the whole suite, then commit**

Run: `.venv/Scripts/python -m pytest tests/test_work_setup_doc.py tests/storage/test_s3_integration.py -v` then `.venv/Scripts/python -m pytest`
If `test_every_setting_is_documented` fails, a `Settings` field is missing from the table: add a row, do not change the test.

```bash
git add tests/storage/test_s3_integration.py docs/work-setup.md tests/test_work_setup_doc.py README.md
git commit -m "docs: work-machine setup guide and an opt-in S3 round-trip test" -m "Co-Authored-By: <model> <noreply@anthropic.com>
Claude-Session: <session url>"
```

---

## Self-review notes

- Spec 7 (refresher scaffold): Task 2. Spec 8 CI bullet (all suites, container
  image): Task 6. Spec 9 layout (`Dockerfile`, `docker-compose.yml`,
  `deploy/helm/`): Tasks 3 and 5. Spec 10 step 7: Tasks 2, 3, 5, 6.
- Spec 12.2 (`VIZ_ALLOWED_HOSTS` in deployment, identity header): Helm values
  and env (Task 5), guide (Task 7). Spec 12.4 author: Task 1. Spec 12.5 bucket
  baseline and Helm defaults: Tasks 4 and 5. Spec 12.6: gitleaks (Task 6),
  placeholders only (Tasks 4, 5), integration tests never in CI (Task 6 test),
  sample bucket stays synthetic (already enforced by
  `tests/test_sample_bucket.py`, which the CI python job runs).
- Carry-forwards: `web/dist/duckdb/**` shipped (Task 3), extension pin noted
  (Task 7 troubleshooting), Playwright Chromium and esbuild in CI (Task 6),
  `VIZ_ALLOWED_HOSTS` set in deployment (Task 5).
- Not verifiable on this machine: `docker build`, `helm lint`, `helm template`,
  the CI run itself, and the two opt-in integration tests. The first four run
  on GitHub after the push; the last two are the user's checklist at work.
