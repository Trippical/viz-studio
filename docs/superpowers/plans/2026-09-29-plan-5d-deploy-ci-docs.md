# Plan 5d: Deploy, CI and docs hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the deploy, CI and documentation findings of the 2026-09-29 hardening review: a CI docker smoke that cannot pass on the SPA fallback, a helm negative check that asserts its message, a Helm chart with correct names, ALB settings, extra DNS egress, graceful shutdown, a PodDisruptionBudget, honest NOTES, a switchable rate limit and the identity gate on by default, a bucket policy that denies writes to everyone but the publisher, and a setup guide in the right order.

**Architecture:** No server or CLI code changes. Changes are to `deploy/helm/viz-site/**`, `deploy/aws/**`, `.github/workflows/ci.yml`, two new stdlib-plus-PyYAML scripts under `.github/scripts/`, `docs/work-setup.md`, `README.md` and one paragraph of the design spec. Helm and Docker are not installed on the development machine, so pytest checks the template text, the parsed `values.yaml`, the JSON policies and the parsed workflow. The two CI scripts do the real rendering and container checks on GitHub; the docker smoke script is also run locally against the real FastAPI app through `TestClient`.

**Tech Stack:** Python 3.11, pytest, PyYAML (already in the `dev` extra), FastAPI `TestClient`, Helm 3 templates, GitHub Actions, AWS IAM JSON. No new dependencies.

**Spec:** `docs/superpowers/specs/2026-09-29-hardening-decisions.md` (binding; this plan is "5d") and `docs/superpowers/specs/2026-09-29-hardening-findings.md` (findings A27, A28, A30, A31, A32, A33, A34, A35, A36, A38, and B1's Helm and docs part). Design spec `docs/superpowers/specs/2026-09-22-viz-site-design.md` section 12.5.

**Depends on plans 5a, 5b, 5c**, which run before this one on the same branch `hardening` (Task 0 checks). From 5a this plan uses: the setting `require_identity` (env `VIZ_REQUIRE_IDENTITY`, bool, default false) in `viz/config.py`; `GET` and `HEAD /api/health` answered before the TrustedHost check and exempt from the identity gate; data files stored as `charts/<id>/data.<16 hex>.<json|parquet>`; the `docs/work-setup.md` table rows 5a wrote (`VIZ_ALLOWED_HOSTS`, `VIZ_AUTH_HEADER`, `VIZ_REQUIRE_IDENTITY`). From 5b: `viz query --sql-file` (5b already changed the guide's `--sql @first.sql` line to `--sql-file first.sql`), `viz publish` refusing to run without `VIZ_STORAGE`, and 5b's edits of the README (outside the trust section) and of the guide's author text. From 5c: `/duckdb/` and `*.wasm` are never gzipped, so the docker smoke sees raw wasm. No IAM policy or doc in the files this plan changes names `data.json` or `data.parquet` literally (checked while writing this plan), so nothing needs renaming for that.

## Global Constraints

- Python `>=3.11`. Always run the venv interpreter: `.venv/Scripts/python` (Linux/macOS: `.venv/bin/python`). Never the system `python`.
- No server, CLI, front end or schema code changes in this plan. Do not do any item that belongs to 5a, 5b or 5c.
- No `DATABRICKS_*` anywhere in Helm, Docker, CI or AWS files (CLAUDE.md rule 5). Existing tests enforce this.
- Every placeholder in deploy files is visibly fake: `REPLACE_ME`, `example.com`, account id `123456789012`, `vpce-REPLACE_ME`. No real bucket, role, account, host, certificate or key anywhere.
- No new dependencies. The CI helm job installs PyYAML into its own runner Python; that is CI setup, not a project dependency.
- Every file is created or edited with the Write or Edit tool, never a shell heredoc (the guard hook blocks backticks and `$(...)` in shell commands; several files below contain both).
- New files under `tests/deploy/` need no `__init__.py` change: `tests/deploy/__init__.py` already exists.
- Every commit message follows the "Commit messages" section of `CLAUDE.md`: subject, blank line, then two adjacent trailer lines (`Co-Authored-By` naming the model that made the commit as its harness states it, and `Claude-Session` with the session URL its harness states), produced with exactly two `-m` flags.
- The whole Python suite (`.venv/Scripts/python -m pytest`) must pass before every commit.

## Review Focus

1. **The docker smoke passes on the SPA fallback again.** Any unknown path returns `index.html` with 200, so a smoke that only checks the status proves nothing. Expected: the smoke fails unless the extension response is `application/wasm` or starts with the bytes `00 61 73 6d`. Pinned in Task 1 (`test_main_fails_when_the_wasm_falls_back_to_index_html`).
2. **The docker smoke runs against an empty bucket** because an environment variable name is misspelled (for example `VIZ_DATA_DIR` instead of `VIZ_LOCAL_DIR`) and the server silently falls back to its default folder, which does not exist in the image. Expected: the smoke fails when the tree has no dashboards, and every `-e VIZ_*` name in the docker job is a real `Settings` field. Pinned in Task 1 (`test_main_fails_on_an_empty_bucket`, `test_docker_job_env_names_are_real_settings`).
3. **The identity gate is silently off in production** because the Helm env var name does not match 5a's setting, or the value renders as something pydantic does not parse as true. Expected: the deployment sets `VIZ_REQUIRE_IDENTITY` to `"true"` and the name maps to a `Settings` field. Pinned in Task 3 (`test_require_identity_env_matches_a_setting`) and Task 8 (`check_identity_gate` in CI).
4. **IRSA stops working after the rename.** The ServiceAccount name now follows the release; if the docs or the trust policy example name a different account, pods cannot assume the role and every page is empty. Expected: `helm install viz-site ... -n viz` gives service account `viz-site`, and both docs name `system:serviceaccount:viz:viz-site`. Pinned in Task 2 (`test_service_account_name_defaults_to_the_fullname`), Task 8 (`check_names`), Task 9 (`test_readme_shows_the_irsa_trust_policy`) and Task 10 (`test_the_guide_covers_the_hardening_steps`).
5. **The new write Deny locks out the publisher** (a different ARN or condition key from the read exemption), so every `viz publish` gets AccessDenied. Expected: the write Deny exempts exactly the same principal list as the read Deny, using `ArnNotLike` on `aws:PrincipalArn`. Pinned in Task 9 (`test_write_deny_exempts_the_same_publisher_as_the_read_deny`).

---

## How to execute a task (read this whether you are a large or a small model)

1. Read `CLAUDE.md` at the repo root first. It has the commands, the commit
   trailers, and the environment gotchas.
2. Work only on the task you were given. Do not start the next one.
3. Do the steps in order. Each step is one action. Do not skip the "run the
   test and see it fail" step; it proves the test is real.
4. Copy the code and text from the step exactly. An "Edit" step gives the
   exact old text and the exact new text: use the Edit tool with them. If the
   old text is not found exactly, read the file, find the passage the step
   describes, and if an earlier plan (5a, 5b, 5c) reworded it, apply the same
   change to the reworded passage and say so in your report. If you cannot
   find the passage at all, stop and report.
5. If a command fails and you cannot fix it within the task's scope, stop and
   report the full error output. Do not work around it by weakening a test.
6. Before committing, run the whole Python suite:
   `.venv/Scripts/python -m pytest`. It must pass.
7. Stage only the files named in the task's commit step. Never run
   `git checkout -- .`, `git restore`, `git stash`, `git clean` or `git reset`.
8. Report back with: the commit hash, the test summary line, and any
   deviation from the plan. Nothing else is needed.

A guard hook blocks shell commands that contain backticks, `$(...)`, or
redirects to paths outside the project. Create and edit every file in this
plan with the Write or Edit tool, not a shell heredoc.

### Task 0: Confirm plans 5a, 5b and 5c are in

**Files:** none changed. No commit.

**Interfaces:**
- Consumes: the "Interfaces for later plans" sections at the end of plans 5a, 5b and 5c.
- Produces: a short report; Task 1 starts only after it.

- [ ] **Step 1: Check the branch**

Run: `git branch --show-current`
Expected: `hardening`. If not, stop and report.

- [ ] **Step 2: Check plan 5a's setting and health exemption**

Run: `.venv/Scripts/python -c "from viz.config import Settings; print('require_identity' in Settings.model_fields)"`
Expected: `True`. If it prints `False`, stop and report: this plan needs 5a's setting.

Run: `grep -n "HEALTH_METHODS = " viz/server/middleware.py`
Expected: one line, `HEALTH_METHODS = ("GET", "HEAD")`.

- [ ] **Step 3: Check the texts this plan anchors on**

Use the Grep tool (or `grep -n`) for each:
- `docs/work-setup.md`: a row starting `` | `VIZ_AUTH_HEADER` | `` that contains `required when`, and a row starting `` | `VIZ_REQUIRE_IDENTITY` | `` (both from plan 5a).
- `docs/work-setup.md`: `viz query --sql-file first.sql --id smoke/first-chart` (from plan 5b).
- `viz/publish/cli.py`: `_require_explicit_storage` (from plan 5b).
- `viz/server/compression.py`: `UNCOMPRESSED_PREFIXES = ("/api/data/", "/duckdb/")` (from plan 5c).
- `README.md`: `## Trust assumptions, read these first`.
- `deploy/aws/bucket-policy.json`: `DenyReadsOutsideTheVpcEndpointExceptPublishers`.

Expected: every one is found. If one is missing, stop and report which.

- [ ] **Step 4: Run the whole suite**

Run: `.venv/Scripts/python -m pytest`
Expected: all pass, 0 failed.

- [ ] **Step 5: Confirm the tools**

Run: `command -v helm docker 2>&1`
Expected: nothing is printed on this machine. That is expected; CI renders the chart and builds the image.

- [ ] **Step 6: Report**

Report the branch, the pytest summary line and that helm and docker are absent. Nothing is committed.

---

## File structure

| Path | Responsibility |
|---|---|
| `.github/scripts/docker_smoke.py` (new) | Stdlib-only smoke checks against the running container: health, real wasm, tree with dashboards |
| `.github/scripts/helm_checks.py` (new) | Renders the chart in several configurations with `helm template` and checks the parsed manifests |
| `.github/workflows/ci.yml` | Docker job mounts the sample bucket and runs `docker_smoke.py`; helm job runs `helm_checks.py` |
| `deploy/helm/viz-site/templates/_helpers.tpl` | Standard fullname; `viz-site.serviceAccountName` |
| `deploy/helm/viz-site/templates/serviceaccount.yaml`, `deployment.yaml` | Use the ServiceAccount helper; identity gate env; probes, preStop, grace period |
| `deploy/helm/viz-site/templates/pdb.yaml` (new) | PodDisruptionBudget when `replicaCount > 1` |
| `deploy/helm/viz-site/templates/ingress.yaml` | ALB block only for `className: alb`; nginx rate limit behind a flag |
| `deploy/helm/viz-site/templates/networkpolicy.yaml` | `dnsCidrs` egress rule |
| `deploy/helm/viz-site/templates/NOTES.txt` | Honest post-install checks |
| `deploy/helm/viz-site/values.yaml` | New values: `serviceAccount.name: ""`, `requireIdentity`, `ingress.rateLimit`, `ingress.alb`, `networkPolicy.dnsCidrs` |
| `deploy/aws/bucket-policy.json`, `deploy/aws/README.md` | Write Deny except the publisher; trust policy example; VPC endpoint order |
| `docs/work-setup.md` | Order of namespace, VPC endpoint and IRSA; scratch prefix smoke with cleanup; identity gate; rate limit; troubleshooting |
| `README.md`, `docs/superpowers/specs/2026-09-22-viz-site-design.md` | "No login of its own" wording; spec 12.5 matches the chart |
| `tests/deploy/test_docker_smoke.py`, `tests/deploy/test_helm_checks.py`, `tests/test_readme.py` (new); `tests/deploy/test_ci.py`, `test_helm.py`, `test_aws_policies.py`, `tests/test_work_setup_doc.py` | Tests for the above |

---

### Task 1: CI docker smoke checks real wasm and a mounted sample bucket (A27)

**Files:**
- Create: `.github/scripts/docker_smoke.py`, `tests/deploy/test_docker_smoke.py`
- Modify: `.github/workflows/ci.yml` (docker job), `tests/deploy/test_ci.py`

**Interfaces:**
- Consumes: `viz.config.Settings` fields `storage`, `local_dir`, `root_prefix`, `web_dist`, `allowed_hosts`; `viz.server.app.create_app(settings)`; the SPA fallback in `viz/server/static.py` (serves a file under `web_dist` if it exists, otherwise `index.html` with 200); `/api/tree` returns `{"charts": <folder>, "dashboards": <folder>, "built_at": ...}` where a folder is `{"items": [...], "folders": [...], ...}` and a dashboard item has `"type": "dashboard"` and, when broken, a non-empty `"error"`; the shipped file `web/public/duckdb/v1.4.3/wasm_eh/parquet.duckdb_extension.wasm` (starts with bytes `00 61 73 6d`).
- Produces: `.github/scripts/docker_smoke.py` with `EXTENSION_PATH: str`, `WASM_MAGIC: bytes`, `fetch(url) -> tuple[int, str, bytes]`, `is_wasm(content_type, body) -> bool`, `count_dashboards(folder) -> int`, `wait_for_health(base, attempts=30) -> bool`, `main(argv) -> int` (0 ok, 1 failed).

- [ ] **Step 1: Write the failing tests for the script**

Create `tests/deploy/test_docker_smoke.py`:

```python
"""The CI docker smoke script. It must fail when the wasm request falls back to
index.html and when the folder tree has no dashboards (finding A27)."""
import importlib.util
import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from viz.config import Settings
from viz.server.app import create_app

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / ".github" / "scripts" / "docker_smoke.py"
SAMPLE = REPO / "sample-bucket"
WASM = REPO / "web" / "public" / "duckdb" / "v1.4.3" / "wasm_eh" / "parquet.duckdb_extension.wasm"
BASE = "http://localhost:8000"


@pytest.fixture
def smoke():
    spec = importlib.util.spec_from_file_location("docker_smoke", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _dist(tmp_path: Path, with_wasm: bool) -> Path:
    """A minimal built front end: index.html, and optionally the self-hosted extension."""
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("<!doctype html><title>viz</title>", encoding="utf-8")
    if with_wasm:
        target = dist / "duckdb" / "v1.4.3" / "wasm_eh" / "parquet.duckdb_extension.wasm"
        target.parent.mkdir(parents=True)
        shutil.copyfile(WASM, target)
    return dist


def _fetch_via(dist: Path, bucket: Path):
    """A stand-in for docker_smoke.fetch that asks the real app through TestClient."""
    settings = Settings(storage="local", local_dir=bucket, root_prefix="viz/", web_dist=dist,
                        allowed_hosts="testserver")
    client = TestClient(create_app(settings))

    def fetch(url: str):
        response = client.get(url.removeprefix(BASE))
        return response.status_code, response.headers.get("content-type", ""), response.content

    return fetch


def test_extension_path_matches_the_shipped_file(smoke):
    assert (REPO / "web" / "public" / smoke.EXTENSION_PATH.lstrip("/")).is_file()


def test_is_wasm_accepts_the_real_extension(smoke):
    assert smoke.is_wasm("application/octet-stream", WASM.read_bytes()[:64])
    assert smoke.is_wasm("application/wasm", b"\x00asm\x01\x00\x00\x00")


def test_is_wasm_rejects_the_spa_fallback(smoke):
    assert not smoke.is_wasm("text/html; charset=utf-8", b"<!doctype html><title>viz</title>")


def test_count_dashboards_walks_nested_folders_and_skips_errors(smoke):
    tree = {
        "items": [{"type": "dashboard", "id": "a", "error": None}],
        "folders": [{
            "items": [
                {"type": "dashboard", "id": "b/c"},
                {"type": "dashboard", "id": "b/d", "error": "not found"},
                {"type": "chart", "id": "b/e"},
            ],
            "folders": [],
        }],
    }
    assert smoke.count_dashboards(tree) == 2


def test_main_passes_against_the_real_app_and_sample_bucket(smoke, tmp_path, monkeypatch):
    monkeypatch.setattr(smoke, "fetch", _fetch_via(_dist(tmp_path, with_wasm=True), SAMPLE))
    assert smoke.main(["docker_smoke.py", BASE]) == 0


def test_main_fails_when_the_wasm_falls_back_to_index_html(smoke, tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(smoke, "fetch", _fetch_via(_dist(tmp_path, with_wasm=False), SAMPLE))
    assert smoke.main(["docker_smoke.py", BASE]) == 1
    assert "is not WebAssembly" in capsys.readouterr().out


def test_main_fails_on_an_empty_bucket(smoke, tmp_path, monkeypatch, capsys):
    empty = tmp_path / "empty"
    (empty / "viz" / "charts").mkdir(parents=True)
    (empty / "viz" / "dashboards").mkdir(parents=True)
    monkeypatch.setattr(smoke, "fetch", _fetch_via(_dist(tmp_path, with_wasm=True), empty))
    assert smoke.main(["docker_smoke.py", BASE]) == 1
    assert "lists no dashboards" in capsys.readouterr().out
```

- [ ] **Step 2: Run them to see them fail**

Run: `.venv/Scripts/python -m pytest tests/deploy/test_docker_smoke.py -v`
Expected: every test FAILS or ERRORS with `FileNotFoundError` (the script does not exist yet).

- [ ] **Step 3: Write `.github/scripts/docker_smoke.py`**

```python
"""CI smoke test for the container image. Standard library only: the docker job
has no project virtualenv.

Usage, from the repo root, with the container listening on port 8000:
    python3 .github/scripts/docker_smoke.py http://localhost:8000

Checks, in order:
1. /api/health answers 200 (retried for up to 30 seconds while the container starts).
2. The self-hosted DuckDB parquet extension is served as WebAssembly. An unknown
   path falls back to index.html with status 200, so a 200 alone proves nothing.
3. /api/tree is JSON and lists at least one dashboard without an error, which
   proves the mounted sample bucket is being read.
"""
import json
import sys
import time
import urllib.error
import urllib.request

EXTENSION_PATH = "/duckdb/v1.4.3/wasm_eh/parquet.duckdb_extension.wasm"
WASM_MAGIC = b"\x00asm"


def fetch(url: str) -> tuple[int, str, bytes]:
    """GET url. Returns (status, content type, body). HTTP error statuses are returned, not raised."""
    try:
        with urllib.request.urlopen(url, timeout=10) as response:
            return response.status, response.headers.get("Content-Type", ""), response.read()
    except urllib.error.HTTPError as err:
        return err.code, err.headers.get("Content-Type", ""), err.read()


def is_wasm(content_type: str, body: bytes) -> bool:
    """True when the response is WebAssembly: the application/wasm type or the wasm magic bytes."""
    media_type = content_type.split(";")[0].strip().lower()
    return media_type == "application/wasm" or body[:4] == WASM_MAGIC


def count_dashboards(folder: dict) -> int:
    """Dashboards without an error in a /api/tree folder node and all of its sub-folders."""
    count = 0
    for item in folder.get("items", []):
        if item.get("type") == "dashboard" and not item.get("error"):
            count += 1
    for child in folder.get("folders", []):
        count += count_dashboards(child)
    return count


def wait_for_health(base: str, attempts: int = 30) -> bool:
    for _ in range(attempts):
        try:
            status, _, _ = fetch(base + "/api/health")
        except OSError:
            status = 0
        if status == 200:
            return True
        time.sleep(1)
    return False


def main(argv: list[str]) -> int:
    base = argv[1].rstrip("/")
    if not wait_for_health(base):
        print("FAIL: /api/health never answered 200")
        return 1
    print("ok   /api/health")

    status, content_type, body = fetch(base + EXTENSION_PATH)
    if status != 200 or not is_wasm(content_type, body):
        print(f"FAIL: {EXTENSION_PATH} is not WebAssembly "
              f"(status {status}, Content-Type {content_type!r}, first bytes {body[:16]!r})")
        return 1
    print(f"ok   {EXTENSION_PATH}: {len(body)} bytes, Content-Type {content_type!r}")

    status, content_type, body = fetch(base + "/api/tree")
    if status != 200 or not content_type.startswith("application/json"):
        print(f"FAIL: /api/tree answered status {status} with Content-Type {content_type!r}")
        return 1
    dashboards = count_dashboards(json.loads(body)["dashboards"])
    if dashboards < 1:
        print("FAIL: /api/tree lists no dashboards; is the sample bucket mounted at VIZ_LOCAL_DIR?")
        return 1
    print(f"ok   /api/tree lists {dashboards} dashboards")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
```

- [ ] **Step 4: Run the script tests**

Run: `.venv/Scripts/python -m pytest tests/deploy/test_docker_smoke.py -v`
Expected: all 7 pass. If `test_main_passes_against_the_real_app_and_sample_bucket` fails on `/api/tree` with status 400, the app rejected the Host header: check that `allowed_hosts="testserver"` is passed exactly as written. If it fails with 401, plan 5a's identity gate is on by default in `Settings`, which contradicts the decisions file: stop and report.

- [ ] **Step 5: Write the failing workflow tests**

In `tests/deploy/test_ci.py`, add `import re` directly below `from pathlib import Path`, and add `from viz.config import Settings` directly below `import yaml`. Then replace the function

```python
def test_docker_job_smoke_tests_the_image():
    docker = _runs(_workflow()["jobs"]["docker"])
    for fragment in ("docker run", "--read-only", "/api/health"):
        assert fragment in docker, fragment
```

with

```python
def test_docker_job_smoke_tests_the_image():
    docker = _runs(_workflow()["jobs"]["docker"])
    for fragment in (
        "docker run",
        "--read-only",
        '-v "$PWD/sample-bucket:/data:ro"',
        "-e VIZ_STORAGE=local",
        "-e VIZ_LOCAL_DIR=/data",
        "-e VIZ_ROOT_PREFIX=viz/",
        "python3 .github/scripts/docker_smoke.py http://localhost:8000",
        'test "$(docker exec viz id -u)" = "10001"',
    ):
        assert fragment in docker, fragment
    # The old check fetched the wasm with curl -o /dev/null and passed on the index.html fallback.
    assert "curl -fsS -o /dev/null" not in docker


def test_docker_job_env_names_are_real_settings():
    docker = _runs(_workflow()["jobs"]["docker"])
    names = re.findall(r"-e (VIZ_[A-Z_]+)=", docker)
    assert {"VIZ_STORAGE", "VIZ_LOCAL_DIR", "VIZ_ROOT_PREFIX", "VIZ_ALLOWED_HOSTS"} <= set(names)
    for name in names:
        assert name.removeprefix("VIZ_").lower() in Settings.model_fields, name


def test_docker_job_always_removes_the_container():
    steps = _workflow()["jobs"]["docker"]["steps"]
    cleanup = [step for step in steps if step.get("if") == "always()"]
    assert cleanup and "docker rm -f viz" in cleanup[0]["run"]
```

- [ ] **Step 6: Run them to see them fail**

Run: `.venv/Scripts/python -m pytest tests/deploy/test_ci.py -v`
Expected: `test_docker_job_smoke_tests_the_image`, `test_docker_job_env_names_are_real_settings` and `test_docker_job_always_removes_the_container` FAIL; the rest pass.

- [ ] **Step 7: Change the docker job in `.github/workflows/ci.yml`**

Edit. Old text:

```yaml
      - run: docker build -t viz-site:ci .
      - run: |
          docker run -d --name viz --read-only --tmpfs /tmp -p 8000:8000 -e VIZ_ALLOWED_HOSTS=localhost viz-site:ci
          for i in $(seq 1 30); do curl -fsS -H 'Host: localhost' http://127.0.0.1:8000/api/health && break; sleep 1; done
          curl -fsS -H 'Host: localhost' http://127.0.0.1:8000/api/health
          curl -fsS -o /dev/null -H 'Host: localhost' http://127.0.0.1:8000/duckdb/v1.4.3/wasm_eh/parquet.duckdb_extension.wasm
          test "$(docker exec viz id -u)" = "10001"
          docker rm -f viz
```

New text:

```yaml
      - run: docker build -t viz-site:ci .
      # Smoke: run the image locked down, with the synthetic sample bucket
      # mounted read-only, and check that it serves real WebAssembly (not the
      # index.html fallback) and a folder tree with dashboards.
      - run: |
          docker run -d --name viz --read-only --tmpfs /tmp -p 8000:8000 \
            -v "$PWD/sample-bucket:/data:ro" \
            -e VIZ_STORAGE=local -e VIZ_LOCAL_DIR=/data -e VIZ_ROOT_PREFIX=viz/ \
            -e VIZ_ALLOWED_HOSTS=localhost \
            viz-site:ci
          python3 .github/scripts/docker_smoke.py http://localhost:8000
          test "$(docker exec viz id -u)" = "10001"
      - if: failure()
        run: docker logs viz || true
      - if: always()
        run: docker rm -f viz || true
```

(`http://localhost:8000` sends `Host: localhost:8000`; the host allow-list compares the name without the port, so `VIZ_ALLOWED_HOSTS=localhost` accepts it.)

- [ ] **Step 8: Run the tests and the whole suite, then commit**

Run: `.venv/Scripts/python -m pytest tests/deploy/test_ci.py tests/deploy/test_docker_smoke.py -v` then `.venv/Scripts/python -m pytest`
Docker is not installed on this machine; the docker job itself runs only on GitHub. Say so in your report.

```bash
git add .github/scripts/docker_smoke.py .github/workflows/ci.yml tests/deploy/test_docker_smoke.py tests/deploy/test_ci.py
git -c user.name="tripp" -c user.email="dom4domg@gmail.com" commit -m "ci: docker smoke checks real wasm and a mounted sample bucket" -m "Co-Authored-By: <model name from your harness> <noreply@anthropic.com>
Claude-Session: <session url from your harness>"
```

Verify with `git log -1 --format=%B` that the subject is line 1, line 2 is empty, and the two trailers are the last two lines and adjacent.

---

### Task 2: Helm names: standard fullname and ServiceAccount name (A31)

**Files:**
- Modify: `deploy/helm/viz-site/templates/_helpers.tpl`, `templates/serviceaccount.yaml`, `templates/deployment.yaml`, `values.yaml`, `tests/deploy/test_helm.py`

**Interfaces:**
- Consumes: `.Release.Name`, `.Chart.Name` (`viz-site`), `.Values.serviceAccount.name`.
- Produces: `include "viz-site.fullname" .` gives the release name when it contains `viz-site`, otherwise `<release>-viz-site`; new helper `include "viz-site.serviceAccountName" .` gives `serviceAccount.name` when non-empty, otherwise the fullname. Task 7 (NOTES) and Task 8 (CI checks) use both.

- [ ] **Step 1: Write the failing tests**

Append to `tests/deploy/test_helm.py`:

```python
def test_fullname_is_the_release_name_when_it_contains_the_chart_name():
    text = _template("_helpers.tpl")
    assert "contains .Chart.Name .Release.Name" in text
    assert '{{- .Release.Name | trunc 63 | trimSuffix "-" -}}' in text
    assert '{{- printf "%s-%s" .Release.Name .Chart.Name | trunc 63 | trimSuffix "-" -}}' in text


def test_service_account_name_defaults_to_the_fullname():
    helpers = _template("_helpers.tpl")
    assert 'define "viz-site.serviceAccountName"' in helpers
    assert 'default (include "viz-site.fullname" .) .Values.serviceAccount.name' in helpers
    assert _values()["serviceAccount"]["name"] == ""
    assert 'name: {{ include "viz-site.serviceAccountName" . }}' in _template("serviceaccount.yaml")
    assert 'serviceAccountName: {{ include "viz-site.serviceAccountName" . }}' in _template("deployment.yaml")
    for name in ("serviceaccount.yaml", "deployment.yaml"):
        assert ".Values.serviceAccount.name" not in _template(name), name
```

- [ ] **Step 2: Run them to see them fail**

Run: `.venv/Scripts/python -m pytest tests/deploy/test_helm.py -v`
Expected: the two new tests FAIL; the rest pass.

- [ ] **Step 3: Replace the fullname helper and add the ServiceAccount helper**

Edit `deploy/helm/viz-site/templates/_helpers.tpl`. Old text:

```
{{- define "viz-site.fullname" -}}
{{- printf "%s-%s" .Release.Name .Chart.Name | trunc 63 | trimSuffix "-" -}}
{{- end -}}
```

New text:

```
{{/*
Standard fullname: the release name alone when it already contains the chart
name ("helm install viz-site ..." gives "viz-site", not "viz-site-viz-site"),
otherwise "<release>-viz-site". Kubernetes names are capped at 63 characters.
*/}}
{{- define "viz-site.fullname" -}}
{{- if contains .Chart.Name .Release.Name -}}
{{- .Release.Name | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- printf "%s-%s" .Release.Name .Chart.Name | trunc 63 | trimSuffix "-" -}}
{{- end -}}
{{- end -}}

{{/*
ServiceAccount name: serviceAccount.name when set, otherwise the fullname.
The IRSA trust policy must name exactly this service account.
*/}}
{{- define "viz-site.serviceAccountName" -}}
{{- default (include "viz-site.fullname" .) .Values.serviceAccount.name -}}
{{- end -}}
```

- [ ] **Step 4: Use the helper in the ServiceAccount and the Deployment**

Edit `deploy/helm/viz-site/templates/serviceaccount.yaml`. Old text: `  name: {{ .Values.serviceAccount.name }}` New text: `  name: {{ include "viz-site.serviceAccountName" . }}`

Edit `deploy/helm/viz-site/templates/deployment.yaml`. Old text: `      serviceAccountName: {{ .Values.serviceAccount.name }}` New text: `      serviceAccountName: {{ include "viz-site.serviceAccountName" . }}`

- [ ] **Step 5: Default the value to empty**

Edit `deploy/helm/viz-site/values.yaml`. Old text:

```yaml
serviceAccount:
  name: viz-site
```

New text:

```yaml
serviceAccount:
  # Empty: use the release's full name, which is the release name itself when
  # it contains "viz-site" (helm install viz-site ... gives viz-site) and
  # "<release>-viz-site" otherwise. The IRSA trust policy must name this
  # service account: system:serviceaccount:<namespace>:<name>.
  name: ""
```

- [ ] **Step 6: Run the tests and the whole suite, then commit**

Run: `.venv/Scripts/python -m pytest tests/deploy/test_helm.py -v` then `.venv/Scripts/python -m pytest`
Helm is not installed on this machine; Task 8 adds CI checks that render the names. Say so in your report.

```bash
git add deploy/helm/viz-site/templates/_helpers.tpl deploy/helm/viz-site/templates/serviceaccount.yaml deploy/helm/viz-site/templates/deployment.yaml deploy/helm/viz-site/values.yaml tests/deploy/test_helm.py
git -c user.name="tripp" -c user.email="dom4domg@gmail.com" commit -m "fix(helm): standard fullname; ServiceAccount named after the release" -m "Co-Authored-By: <model name from your harness> <noreply@anthropic.com>
Claude-Session: <session url from your harness>"
```

---

### Task 3: Helm turns the identity gate on by default (B1)

**Files:**
- Modify: `deploy/helm/viz-site/values.yaml`, `templates/deployment.yaml`, `tests/deploy/test_helm.py`

**Interfaces:**
- Consumes: plan 5a's setting `require_identity` (env `VIZ_REQUIRE_IDENTITY`; pydantic parses the string `"true"` as true); the existing `authHeader` value (env `VIZ_AUTH_HEADER`).
- Produces: value `requireIdentity: true`; the Deployment env `VIZ_REQUIRE_IDENTITY` rendered as the quoted string `"true"` or `"false"`. Task 7 and Task 10 describe it.

- [ ] **Step 1: Write the failing tests**

In `tests/deploy/test_helm.py`, add `from viz.config import Settings` directly below `import yaml`, then append:

```python
def test_identity_gate_is_on_by_default():
    assert _values()["requireIdentity"] is True
    text = _template("deployment.yaml")
    assert "- name: VIZ_REQUIRE_IDENTITY\n              value: {{ .Values.requireIdentity | quote }}" in text


def test_require_identity_env_matches_a_setting():
    # The env var only works if it maps to a real field (plan 5a adds require_identity).
    assert "require_identity" in Settings.model_fields
    assert Settings(require_identity="true").require_identity is True
```

- [ ] **Step 2: Run them to see them fail**

Run: `.venv/Scripts/python -m pytest tests/deploy/test_helm.py -v`
Expected: `test_identity_gate_is_on_by_default` FAILS with `KeyError: 'requireIdentity'`. `test_require_identity_env_matches_a_setting` passes already (5a added the field); if it fails, stop and report.

- [ ] **Step 3: Add the value**

Edit `deploy/helm/viz-site/values.yaml`. Old text:

```yaml
# Header the company SSO proxy sets with the signed-in user (logged only).
authHeader: X-Forwarded-Email
```

New text:

```yaml
# Header the company SSO proxy sets with the signed-in user. Logged with every
# request, and required on every request when requireIdentity is true.
authHeader: X-Forwarded-Email

# VIZ_REQUIRE_IDENTITY. The site has no login of its own. When true, every
# request except /api/health that does not carry the authHeader header gets
# 401, so the site refuses traffic that did not come through the SSO proxy.
# Set it to false only for a first smoke test before the proxy is in place
# (docs/work-setup.md, step 7), and turn it back on afterwards.
requireIdentity: true
```

- [ ] **Step 4: Pass it to the container**

Edit `deploy/helm/viz-site/templates/deployment.yaml`. Old text:

```yaml
            - name: VIZ_AUTH_HEADER
              value: {{ .Values.authHeader | quote }}
```

New text:

```yaml
            - name: VIZ_AUTH_HEADER
              value: {{ .Values.authHeader | quote }}
            - name: VIZ_REQUIRE_IDENTITY
              value: {{ .Values.requireIdentity | quote }}
```

- [ ] **Step 5: Run the tests and the whole suite, then commit**

Run: `.venv/Scripts/python -m pytest tests/deploy/test_helm.py -v` then `.venv/Scripts/python -m pytest`

```bash
git add deploy/helm/viz-site/values.yaml deploy/helm/viz-site/templates/deployment.yaml tests/deploy/test_helm.py
git -c user.name="tripp" -c user.email="dom4domg@gmail.com" commit -m "feat(helm): identity gate on by default (VIZ_REQUIRE_IDENTITY)" -m "Co-Authored-By: <model name from your harness> <noreply@anthropic.com>
Claude-Session: <session url from your harness>"
```

---

### Task 4: Probes, graceful shutdown and a PodDisruptionBudget (A33)

**Files:**
- Create: `deploy/helm/viz-site/templates/pdb.yaml`
- Modify: `deploy/helm/viz-site/templates/deployment.yaml`, `tests/deploy/test_helm.py`

**Interfaces:**
- Consumes: `.Values.replicaCount` (default 2); helpers `viz-site.fullname`, `viz-site.labels`, `viz-site.selectorLabels`, `viz-site.probeHost`; `/api/health` (answers without touching S3 and, after 5a, before the host allow-list).
- Produces: pod `terminationGracePeriodSeconds: 30`; container `lifecycle.preStop.exec.command: ["sleep", "5"]`; readiness probe period 5 s, timeout 2 s, failure threshold 3; liveness probe initial delay 10 s, period 20 s, timeout 5 s, failure threshold 6; a `policy/v1` PodDisruptionBudget with `minAvailable: 1` only when `replicaCount > 1`. Task 8 checks the render.

- [ ] **Step 1: Write the failing tests**

In `tests/deploy/test_helm.py`, add `import re` directly above `from pathlib import Path`, then append:

```python
def _probe(text: str, start: str, end: str) -> dict[str, int]:
    block = text.split(start, 1)[1].split(end, 1)[0]
    return {key: int(value) for key, value in re.findall(r"(\w+Seconds|failureThreshold): (\d+)", block)}


def test_readiness_and_liveness_differ_and_liveness_is_more_lenient():
    text = _template("deployment.yaml")
    ready = _probe(text, "readinessProbe:", "livenessProbe:")
    live = _probe(text, "livenessProbe:", "lifecycle:")
    assert ready == {"periodSeconds": 5, "timeoutSeconds": 2, "failureThreshold": 3}
    assert live == {"initialDelaySeconds": 10, "periodSeconds": 20, "timeoutSeconds": 5, "failureThreshold": 6}
    assert live["periodSeconds"] * live["failureThreshold"] > ready["periodSeconds"] * ready["failureThreshold"]
    assert live["timeoutSeconds"] > ready["timeoutSeconds"]


def test_pods_shut_down_gracefully():
    text = _template("deployment.yaml")
    assert "      terminationGracePeriodSeconds: 30\n" in text
    assert 'preStop:\n              exec:\n                command: ["sleep", "5"]' in text


def test_disruption_budget_only_with_more_than_one_replica():
    text = _template("pdb.yaml")
    assert text.startswith("{{- if gt (int .Values.replicaCount) 1 }}")
    assert "apiVersion: policy/v1" in text
    assert "kind: PodDisruptionBudget" in text
    assert "  minAvailable: 1" in text
    assert 'include "viz-site.selectorLabels" .' in text
    assert text.rstrip().endswith("{{- end }}")
```

- [ ] **Step 2: Run them to see them fail**

Run: `.venv/Scripts/python -m pytest tests/deploy/test_helm.py -v`
Expected: the three new tests FAIL (`IndexError` on `lifecycle:`, missing text, `FileNotFoundError` for `pdb.yaml`).

- [ ] **Step 3: Add the grace period**

Edit `deploy/helm/viz-site/templates/deployment.yaml`. Old text:

```yaml
      automountServiceAccountToken: false
      securityContext:
```

New text:

```yaml
      automountServiceAccountToken: false
      terminationGracePeriodSeconds: 30
      securityContext:
```

- [ ] **Step 4: Replace the probes and add the preStop hook**

Edit `deploy/helm/viz-site/templates/deployment.yaml`. Old text:

```yaml
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
```

New text:

```yaml
          # /api/health does not touch S3 and is answered before the host
          # allow-list; the Host header is sent anyway so the probes never
          # depend on that ordering.
          # Readiness is quick to react: a slow pod leaves the Service after
          # about 15 seconds.
          readinessProbe:
            httpGet:
              path: /api/health
              port: http
              httpHeaders:
                - name: Host
                  value: {{ include "viz-site.probeHost" . | quote }}
            periodSeconds: 5
            timeoutSeconds: 2
            failureThreshold: 3
          # Liveness is more lenient: a pod is restarted only after about two
          # minutes without an answer, so a busy pod is not killed while it is
          # merely out of the Service.
          livenessProbe:
            httpGet:
              path: /api/health
              port: http
              httpHeaders:
                - name: Host
                  value: {{ include "viz-site.probeHost" . | quote }}
            initialDelaySeconds: 10
            periodSeconds: 20
            timeoutSeconds: 5
            failureThreshold: 6
          # Keep serving for 5 seconds after the pod is marked for deletion, so
          # the load balancer stops sending new requests before SIGTERM.
          lifecycle:
            preStop:
              exec:
                command: ["sleep", "5"]
```

(`sleep` is `/bin/sleep` from coreutils in the `python:3.11-slim-bookworm` base image; it needs no write access.)

- [ ] **Step 5: Create `deploy/helm/viz-site/templates/pdb.yaml`**

```yaml
{{- if gt (int .Values.replicaCount) 1 }}
# Keep at least one pod running during node drains and cluster upgrades.
# Not rendered for a single replica: minAvailable 1 would block every drain.
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: {{ include "viz-site.fullname" . }}
  labels:
    {{- include "viz-site.labels" . | nindent 4 }}
spec:
  minAvailable: 1
  selector:
    matchLabels:
      {{- include "viz-site.selectorLabels" . | nindent 6 }}
{{- end }}
```

- [ ] **Step 6: Run the tests and the whole suite, then commit**

Run: `.venv/Scripts/python -m pytest tests/deploy/test_helm.py -v` then `.venv/Scripts/python -m pytest`
`test_probes_send_an_allowed_host_header` must still pass (two `/api/health` paths, two `Host` headers).

```bash
git add deploy/helm/viz-site/templates/pdb.yaml deploy/helm/viz-site/templates/deployment.yaml tests/deploy/test_helm.py
git -c user.name="tripp" -c user.email="dom4domg@gmail.com" commit -m "feat(helm): separate probes, preStop delay, grace period and a PodDisruptionBudget" -m "Co-Authored-By: <model name from your harness> <noreply@anthropic.com>
Claude-Session: <session url from your harness>"
```

---

### Task 5: Ingress: ALB settings and a switchable rate limit (A30, A36)

**Files:**
- Modify: `deploy/helm/viz-site/templates/ingress.yaml` (rewritten), `deploy/helm/viz-site/values.yaml`, `tests/deploy/test_helm.py`

**Interfaces:**
- Consumes: `.Values.ingress.className`, `.Values.ingress.host`, `.Values.ingress.annotations`.
- Produces: values `ingress.rateLimit.enabled` (default `true`), `ingress.rateLimit.perSecond` (default `10`), `ingress.alb.certificateArn` (placeholder). The old value `ingress.rateLimitPerSecond` is removed. When `className` is `alb`, the Ingress carries exactly these ALB annotations: `scheme: internal`, `target-type: ip`, `listen-ports: '[{"HTTPS":443}]'`, `certificate-arn`, `healthcheck-path: /api/health`, and no nginx annotation. Otherwise it carries `nginx.ingress.kubernetes.io/limit-rps` only when `rateLimit.enabled`, and no ALB annotation. Task 8 checks the render; Task 10 documents it.

- [ ] **Step 1: Write the failing tests**

Append to `tests/deploy/test_helm.py`:

```python
def test_alb_annotations_render_only_for_the_alb_class():
    text = _template("ingress.yaml")
    start = text.index('{{- if eq .Values.ingress.className "alb" }}')
    middle = text.index("{{- else }}", start)
    alb_block, nginx_block = text[start:middle], text[middle:]
    for line in (
        "alb.ingress.kubernetes.io/scheme: internal",
        "alb.ingress.kubernetes.io/target-type: ip",
        """alb.ingress.kubernetes.io/listen-ports: '[{"HTTPS":443}]'""",
        "alb.ingress.kubernetes.io/certificate-arn: {{ .Values.ingress.alb.certificateArn | quote }}",
        "alb.ingress.kubernetes.io/healthcheck-path: /api/health",
    ):
        assert line in alb_block, line
    assert "nginx.ingress.kubernetes.io" not in alb_block
    assert "alb.ingress.kubernetes.io" not in nginx_block.split("{{- with .Values.ingress.annotations }}")[0]


def test_nginx_rate_limit_can_be_switched_off():
    text = _template("ingress.yaml")
    nginx_block = text[text.index("{{- else }}"):]
    assert "{{- if .Values.ingress.rateLimit.enabled }}" in nginx_block
    assert "nginx.ingress.kubernetes.io/limit-rps: {{ .Values.ingress.rateLimit.perSecond | quote }}" in nginx_block
    ingress = _values()["ingress"]
    assert ingress["rateLimit"] == {"enabled": True, "perSecond": 10}
    assert "rateLimitPerSecond" not in ingress
    values_text = (CHART / "values.yaml").read_text(encoding="utf-8")
    assert "SSO proxy" in values_text.split("rateLimit:")[0].rsplit("host:", 1)[1]


def test_alb_certificate_is_a_placeholder():
    arn = _values()["ingress"]["alb"]["certificateArn"]
    assert arn.startswith("arn:aws:acm:REPLACE_ME-region:123456789012:certificate/")
    assert "REPLACE_ME" in arn.rsplit("/", 1)[1]
```

- [ ] **Step 2: Run them to see them fail**

Run: `.venv/Scripts/python -m pytest tests/deploy/test_helm.py -v`
Expected: the three new tests FAIL (`ValueError: substring not found`, `KeyError`); the rest pass.

- [ ] **Step 3: Rewrite `deploy/helm/viz-site/templates/ingress.yaml`**

Replace the whole file with:

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
    {{- if eq .Values.ingress.className "alb" }}
    # AWS Load Balancer Controller: an internal ALB with an HTTPS listener,
    # targets registered by pod IP, health checked on /api/health (which does
    # not touch S3 and is answered before the host allow-list). The nginx
    # rate limit does not apply here; use a WAF rate-based rule instead.
    alb.ingress.kubernetes.io/scheme: internal
    alb.ingress.kubernetes.io/target-type: ip
    alb.ingress.kubernetes.io/listen-ports: '[{"HTTPS":443}]'
    alb.ingress.kubernetes.io/certificate-arn: {{ .Values.ingress.alb.certificateArn | quote }}
    alb.ingress.kubernetes.io/healthcheck-path: /api/health
    {{- else }}
    # ingress-nginx: make the controller's own Service internal
    # (service.beta.kubernetes.io/aws-load-balancer-scheme: internal).
    {{- if .Values.ingress.rateLimit.enabled }}
    # Counted per client IP. Behind an SSO proxy every request comes from the
    # proxy's IP, so all users share one limit: set ingress.rateLimit.enabled
    # to false there.
    nginx.ingress.kubernetes.io/limit-rps: {{ .Values.ingress.rateLimit.perSecond | quote }}
    {{- end }}
    {{- end }}
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

- [ ] **Step 4: Change the ingress values**

Edit `deploy/helm/viz-site/values.yaml`. Old text:

```yaml
  className: nginx
  host: viz.internal.example.com
  rateLimitPerSecond: 10
  annotations: {}
```

New text:

```yaml
  # "nginx" (ingress-nginx) or "alb" (AWS Load Balancer Controller). The
  # ingress.alb values are used only when className is "alb".
  className: nginx
  host: viz.internal.example.com
  # ingress-nginx only. nginx counts requests per client IP. With the company
  # SSO proxy in front of the ingress, every request arrives from the proxy's
  # IP, so all users share one limit and the site starts refusing everyone:
  # set enabled to false when a proxy sits in front. Leave it on only when
  # users reach the ingress directly.
  rateLimit:
    enabled: true
    perSecond: 10
  alb:
    # ACM certificate for ingress.host, used by the HTTPS listener on 443.
    certificateArn: arn:aws:acm:REPLACE_ME-region:123456789012:certificate/REPLACE_ME
  annotations: {}
```

- [ ] **Step 5: Run the tests and the whole suite, then commit**

Run: `.venv/Scripts/python -m pytest tests/deploy/test_helm.py -v` then `.venv/Scripts/python -m pytest`
`test_ingress_is_internal_and_rate_limited` must still pass (the template text still names both annotations).

```bash
git add deploy/helm/viz-site/templates/ingress.yaml deploy/helm/viz-site/values.yaml tests/deploy/test_helm.py
git -c user.name="tripp" -c user.email="dom4domg@gmail.com" commit -m "feat(helm): ALB annotations for className alb; switchable nginx rate limit" -m "Co-Authored-By: <model name from your harness> <noreply@anthropic.com>
Claude-Session: <session url from your harness>"
```

---

### Task 6: NetworkPolicy `dnsCidrs` (A32)

**Files:**
- Modify: `deploy/helm/viz-site/templates/networkpolicy.yaml`, `deploy/helm/viz-site/values.yaml`, `tests/deploy/test_helm.py`

**Interfaces:**
- Consumes: `.Values.networkPolicy.dnsCidrs` (list of CIDR strings).
- Produces: value `networkPolicy.dnsCidrs: []`. When non-empty, one extra egress rule with an `ipBlock` per CIDR on UDP 53 and TCP 53. The existing kube-system DNS rule stays. Task 8 checks the render.

- [ ] **Step 1: Write the failing test**

Append to `tests/deploy/test_helm.py`:

```python
def test_extra_dns_resolvers_are_allowed_on_udp_and_tcp_53():
    assert _values()["networkPolicy"]["dnsCidrs"] == []
    text = _template("networkpolicy.yaml")
    # The block runs from the `with` to the S3 rule's comment (its first `{{- end }}` closes the inner range).
    block = text.split("{{- with .Values.networkPolicy.dnsCidrs }}", 1)[1].split("# S3 and STS over HTTPS only.", 1)[0]
    assert "- ipBlock:\n            cidr: {{ . }}" in block
    assert "- port: 53\n          protocol: UDP\n        - port: 53\n          protocol: TCP" in block
    # The kube-dns rule is still there.
    assert "kubernetes.io/metadata.name: kube-system" in text
    assert text.count("port: 53") == 4
    values_text = (CHART / "values.yaml").read_text(encoding="utf-8")
    assert "NodeLocal DNSCache" in values_text.split("dnsCidrs:")[0].rsplit("egressCidrs:", 1)[1]
```

- [ ] **Step 2: Run it to see it fail**

Run: `.venv/Scripts/python -m pytest tests/deploy/test_helm.py -v`
Expected: `test_extra_dns_resolvers_are_allowed_on_udp_and_tcp_53` FAILS with `KeyError: 'dnsCidrs'`.

- [ ] **Step 3: Add the rule to the template**

Edit `deploy/helm/viz-site/templates/networkpolicy.yaml`. Old text:

```yaml
    # S3 and STS over HTTPS only.
```

New text:

```yaml
    {{- with .Values.networkPolicy.dnsCidrs }}
    # DNS to resolvers outside kube-system, for example NodeLocal DNSCache.
    - to:
        {{- range . }}
        - ipBlock:
            cidr: {{ . }}
        {{- end }}
      ports:
        - port: 53
          protocol: UDP
        - port: 53
          protocol: TCP
    {{- end }}
    # S3 and STS over HTTPS only.
```

- [ ] **Step 4: Add the value**

Edit `deploy/helm/viz-site/values.yaml`. Old text:

```yaml
  # NodeLocal DNSCache (169.254.20.10) is not allowed by the DNS rule; add it
  # if your cluster uses it.
  egressCidrs:
    - 192.0.2.0/24  # REPLACE_ME: see the comment above
```

New text:

```yaml
  egressCidrs:
    - 192.0.2.0/24  # REPLACE_ME: see the comment above
  # Extra DNS resolvers outside kube-system, allowed on UDP and TCP 53. With
  # NodeLocal DNSCache add its address, for example ["169.254.20.10/32"].
  # The rule for kube-dns in kube-system stays in place either way.
  dnsCidrs: []
```

- [ ] **Step 5: Run the tests and the whole suite, then commit**

Run: `.venv/Scripts/python -m pytest tests/deploy/test_helm.py -v` then `.venv/Scripts/python -m pytest`

```bash
git add deploy/helm/viz-site/templates/networkpolicy.yaml deploy/helm/viz-site/values.yaml tests/deploy/test_helm.py
git -c user.name="tripp" -c user.email="dom4domg@gmail.com" commit -m "feat(helm): networkPolicy.dnsCidrs for resolvers outside kube-system" -m "Co-Authored-By: <model name from your harness> <noreply@anthropic.com>
Claude-Session: <session url from your harness>"
```

---

### Task 7: NOTES.txt tells the truth about health (A34)

**Files:**
- Modify: `deploy/helm/viz-site/templates/NOTES.txt` (rewritten), `tests/deploy/test_helm.py`

**Interfaces:**
- Consumes: helpers `viz-site.fullname`, `viz-site.serviceAccountName` (Task 2); values `allowedHosts`, `requireIdentity` (Task 3), `authHeader`, `ingress.host`, `bucket.name`, `bucket.rootPrefix`, `serviceAccount.roleArn`.
- Produces: post-install text. `helm lint` renders it in CI (Task 8).

- [ ] **Step 1: Write the failing test**

Append to `tests/deploy/test_helm.py`:

```python
def test_notes_say_health_does_not_touch_s3_and_to_open_the_tree():
    text = _template("NOTES.txt")
    flat = " ".join(text.split())
    assert "It does not touch S3" in flat
    assert "Open https://{{ .Values.ingress.host }}/ and check that the folder tree loads" in flat
    assert "{{- if .Values.requireIdentity }}" in text
    assert 'system:serviceaccount:{{ .Release.Namespace }}:{{ include "viz-site.serviceAccountName" . }}' in flat
    # The old text claimed an S3 or IRSA failure keeps pods unready; /api/health never reads S3.
    assert "never become ready" not in flat
```

- [ ] **Step 2: Run it to see it fail**

Run: `.venv/Scripts/python -m pytest tests/deploy/test_helm.py -v`
Expected: `test_notes_say_health_does_not_touch_s3_and_to_open_the_tree` FAILS.

- [ ] **Step 3: Rewrite `deploy/helm/viz-site/templates/NOTES.txt`**

Replace the whole file with:

```
viz-site is installed as {{ include "viz-site.fullname" . }} in namespace {{ .Release.Namespace }}.
Its service account is {{ include "viz-site.serviceAccountName" . }}; the IRSA trust policy of
{{ .Values.serviceAccount.roleArn }} must name
system:serviceaccount:{{ .Release.Namespace }}:{{ include "viz-site.serviceAccountName" . }}.

It answers only to: {{ .Values.allowedHosts }}
{{- if .Values.requireIdentity }}

requireIdentity is on: every request except /api/health that does not carry
the {{ .Values.authHeader }} header gets 401. Open the site through the
company SSO proxy, which sets that header.
{{- end }}

Check the install in two steps:

1. https://{{ .Values.ingress.host }}/api/health returns {"status": "ok"}.
   This only says the pods are running. It does not touch S3, so it stays
   green when the bucket, the IRSA role or the KMS key policy is wrong.

2. Open https://{{ .Values.ingress.host }}/ and check that the folder tree loads.
   An empty tree or error markers mean the pods cannot read
   s3://{{ .Values.bucket.name }}/{{ .Values.bucket.rootPrefix }}: check the IRSA role above,
   networkPolicy.egressCidrs (S3 and STS) and the KMS key policy.
```

- [ ] **Step 4: Run the tests and the whole suite, then commit**

Run: `.venv/Scripts/python -m pytest tests/deploy/test_helm.py -v` then `.venv/Scripts/python -m pytest`

```bash
git add deploy/helm/viz-site/templates/NOTES.txt tests/deploy/test_helm.py
git -c user.name="tripp" -c user.email="dom4domg@gmail.com" commit -m "docs(helm): NOTES say health does not touch S3; check the folder tree" -m "Co-Authored-By: <model name from your harness> <noreply@anthropic.com>
Claude-Session: <session url from your harness>"
```

---

### Task 8: CI renders the chart and checks it, including the negative check's message (A28)

**Files:**
- Create: `.github/scripts/helm_checks.py`, `tests/deploy/test_helm_checks.py`
- Modify: `.github/workflows/ci.yml` (helm job), `tests/deploy/test_ci.py`

**Interfaces:**
- Consumes: the `helm` binary (CI only); PyYAML; the chart after Tasks 2 to 7; the fail message in `templates/networkpolicy.yaml`: `networkPolicy.egressCidrs must list at least one CIDR (an empty list would allow egress anywhere)`.
- Produces: `.github/scripts/helm_checks.py` with `CHART`, `EGRESS_ERROR`, `render(release, *args) -> list[dict]`, `render_error(*args) -> str`, `one(docs, kind) -> dict`, `dns_ports_ok(rule) -> bool`, six `check_*()` functions, `CHECKS` (list of them), `main() -> int`. Run from the repo root.

- [ ] **Step 1: Write the failing tests**

Create `tests/deploy/test_helm_checks.py`:

```python
"""The CI helm render checks. The checks themselves need helm and run in the CI
helm job; here we test the pieces that do not need helm."""
import importlib.util
import shutil
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / ".github" / "scripts" / "helm_checks.py"
NETWORKPOLICY = REPO / "deploy" / "helm" / "viz-site" / "templates" / "networkpolicy.yaml"


@pytest.fixture
def checks():
    spec = importlib.util.spec_from_file_location("helm_checks", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_negative_check_expects_the_templates_own_message(checks):
    # A28: the CI check must fail on any other error, so it looks for this exact text.
    assert checks.EGRESS_ERROR in NETWORKPOLICY.read_text(encoding="utf-8")


def test_every_check_is_registered(checks):
    assert [check.__name__ for check in checks.CHECKS] == [
        "check_empty_egress_fails_with_its_message",
        "check_names",
        "check_identity_gate",
        "check_probes_and_shutdown",
        "check_ingress",
        "check_dns",
    ]


def test_dns_ports_ok(checks):
    assert checks.dns_ports_ok({"ports": [{"port": 53, "protocol": "UDP"}, {"port": 53, "protocol": "TCP"}]})
    assert not checks.dns_ports_ok({"ports": [{"port": 53, "protocol": "UDP"}]})
    assert not checks.dns_ports_ok({"ports": [{"port": 443, "protocol": "TCP"}]})


def test_one_refuses_zero_or_two_matches(checks):
    with pytest.raises(AssertionError):
        checks.one([], "Deployment")
    with pytest.raises(AssertionError):
        checks.one([{"kind": "Deployment"}, {"kind": "Deployment"}], "Deployment")
    assert checks.one([{"kind": "Service"}, {"kind": "Deployment", "x": 1}], "Deployment") == {"kind": "Deployment", "x": 1}


@pytest.mark.skipif(shutil.which("helm") is None, reason="helm is not installed; the CI helm job runs these checks")
def test_chart_passes_every_check(checks, monkeypatch):
    monkeypatch.chdir(REPO)
    assert checks.main() == 0
```

In `tests/deploy/test_ci.py`, replace the function

```python
def test_helm_job_proves_an_empty_egress_list_fails():
    helm = _runs(_workflow()["jobs"]["helm"])
    assert "networkPolicy.egressCidrs=[]" in helm
```

with

```python
def test_helm_job_runs_the_render_checks():
    job = _workflow()["jobs"]["helm"]
    helm = _runs(job)
    assert 'python -m pip install "pyyaml>=6"' in helm
    assert "python .github/scripts/helm_checks.py" in helm
    assert any(step.get("uses", "").startswith("actions/setup-python") for step in job["steps"])
    # A28: the old inline check passed on any failure; the script checks the message.
    assert "> /dev/null 2>&1" not in helm
```

- [ ] **Step 2: Run them to see them fail**

Run: `.venv/Scripts/python -m pytest tests/deploy/test_helm_checks.py tests/deploy/test_ci.py -v`
Expected: every test in `test_helm_checks.py` FAILS or ERRORS with `FileNotFoundError` (the last one is SKIPPED because helm is not installed), and `test_helm_job_runs_the_render_checks` FAILS.

- [ ] **Step 3: Write `.github/scripts/helm_checks.py`**

```python
"""Render the Helm chart in several configurations and check what comes out.

Runs in the CI helm job, which has the helm binary and PyYAML. Each check
renders the chart with `helm template`, parses the manifests and raises
AssertionError with a readable message when the chart is wrong.

Usage, from the repo root:
    python .github/scripts/helm_checks.py
"""
import subprocess
import sys

import yaml

CHART = "deploy/helm/viz-site"
EGRESS_ERROR = "networkPolicy.egressCidrs must list at least one CIDR"


def render(release: str, *args: str) -> list[dict]:
    """The manifests `helm template <release> <chart> <args>` prints, empty documents dropped."""
    result = subprocess.run(["helm", "template", release, CHART, *args], capture_output=True, text=True)
    if result.returncode != 0:
        raise AssertionError(f"helm template {release} {' '.join(args)} failed:\n{result.stderr}")
    return [doc for doc in yaml.safe_load_all(result.stdout) if doc]


def render_error(*args: str) -> str:
    """The error output of a `helm template` run that must fail."""
    result = subprocess.run(["helm", "template", "ci", CHART, *args], capture_output=True, text=True)
    if result.returncode == 0:
        raise AssertionError(f"helm template {' '.join(args)} succeeded but must fail")
    return result.stderr


def one(docs: list[dict], kind: str) -> dict:
    found = [doc for doc in docs if doc.get("kind") == kind]
    if len(found) != 1:
        raise AssertionError(f"expected exactly one {kind}, found {len(found)}")
    return found[0]


def pod_spec(docs: list[dict]) -> dict:
    return one(docs, "Deployment")["spec"]["template"]["spec"]


def env_of(docs: list[dict]) -> dict:
    return {item["name"]: item.get("value") for item in pod_spec(docs)["containers"][0]["env"]}


def annotations_of(docs: list[dict]) -> dict:
    return one(docs, "Ingress")["metadata"].get("annotations") or {}


def dns_ports_ok(rule: dict) -> bool:
    ports = sorted((port["protocol"], port["port"]) for port in rule.get("ports", []))
    return ports == [("TCP", 53), ("UDP", 53)]


def check_empty_egress_fails_with_its_message() -> None:
    """A28: an empty egress list must fail the render with the chart's own message."""
    stderr = render_error("--set-json", "networkPolicy.egressCidrs=[]")
    if EGRESS_ERROR not in stderr:
        raise AssertionError(f"the render failed, but not with {EGRESS_ERROR!r}:\n{stderr}")


def check_names() -> None:
    """A31: fullname and ServiceAccount name follow the release; serviceAccount.name overrides."""
    cases = [
        (("viz-site",), "viz-site", "viz-site"),
        (("prod",), "prod-viz-site", "prod-viz-site"),
        (("viz-site", "--set", "serviceAccount.name=custom-sa"), "viz-site", "custom-sa"),
    ]
    for args, fullname, account in cases:
        docs = render(*args)
        name = one(docs, "Deployment")["metadata"]["name"]
        if name != fullname:
            raise AssertionError(f"{args}: Deployment is named {name!r}, expected {fullname!r}")
        sa = one(docs, "ServiceAccount")["metadata"]["name"]
        if sa != account:
            raise AssertionError(f"{args}: ServiceAccount is named {sa!r}, expected {account!r}")
        used = pod_spec(docs)["serviceAccountName"]
        if used != account:
            raise AssertionError(f"{args}: pods use service account {used!r}, expected {account!r}")


def check_identity_gate() -> None:
    """B1: VIZ_REQUIRE_IDENTITY is "true" by default and can be turned off."""
    value = env_of(render("ci")).get("VIZ_REQUIRE_IDENTITY")
    if value != "true":
        raise AssertionError(f"VIZ_REQUIRE_IDENTITY is {value!r} by default, expected 'true'")
    value = env_of(render("ci", "--set", "requireIdentity=false")).get("VIZ_REQUIRE_IDENTITY")
    if value != "false":
        raise AssertionError(f"VIZ_REQUIRE_IDENTITY is {value!r} with requireIdentity=false, expected 'false'")


def check_probes_and_shutdown() -> None:
    """A33: grace period, preStop, separate probes with timeouts, PDB only above one replica."""
    docs = render("ci")
    spec = pod_spec(docs)
    container = spec["containers"][0]
    if spec.get("terminationGracePeriodSeconds") != 30:
        raise AssertionError(f"terminationGracePeriodSeconds is {spec.get('terminationGracePeriodSeconds')!r}")
    command = container.get("lifecycle", {}).get("preStop", {}).get("exec", {}).get("command")
    if command != ["sleep", "5"]:
        raise AssertionError(f"preStop command is {command!r}")
    ready, live = container["readinessProbe"], container["livenessProbe"]
    if ready == live:
        raise AssertionError("readiness and liveness probes are identical")
    for label, probe in (("readiness", ready), ("liveness", live)):
        if "timeoutSeconds" not in probe:
            raise AssertionError(f"the {label} probe has no timeoutSeconds")
    if live["periodSeconds"] * live["failureThreshold"] <= ready["periodSeconds"] * ready["failureThreshold"]:
        raise AssertionError("the liveness probe is not more lenient than the readiness probe")
    pdb = one(docs, "PodDisruptionBudget")
    if pdb["spec"].get("minAvailable") != 1:
        raise AssertionError(f"PodDisruptionBudget minAvailable is {pdb['spec'].get('minAvailable')!r}")
    if pdb["spec"]["selector"]["matchLabels"] != one(docs, "Deployment")["spec"]["selector"]["matchLabels"]:
        raise AssertionError("the PodDisruptionBudget does not select the Deployment's pods")
    single = render("ci", "--set", "replicaCount=1")
    if [doc for doc in single if doc.get("kind") == "PodDisruptionBudget"]:
        raise AssertionError("a PodDisruptionBudget is rendered for a single replica")


def check_ingress() -> None:
    """A30 and A36: ALB annotations only for className alb; nginx rate limit behind a flag."""
    nginx = annotations_of(render("ci"))
    if nginx.get("nginx.ingress.kubernetes.io/limit-rps") != "10":
        raise AssertionError(f"default nginx annotations lack limit-rps 10: {nginx}")
    if any(key.startswith("alb.ingress.kubernetes.io/") for key in nginx):
        raise AssertionError(f"ALB annotations rendered for className nginx: {nginx}")
    off = annotations_of(render("ci", "--set", "ingress.rateLimit.enabled=false"))
    if "nginx.ingress.kubernetes.io/limit-rps" in off:
        raise AssertionError("limit-rps rendered with ingress.rateLimit.enabled=false")
    alb = annotations_of(render("ci", "--set", "ingress.className=alb"))
    expected = {
        "alb.ingress.kubernetes.io/scheme": "internal",
        "alb.ingress.kubernetes.io/target-type": "ip",
        "alb.ingress.kubernetes.io/listen-ports": '[{"HTTPS":443}]',
        "alb.ingress.kubernetes.io/healthcheck-path": "/api/health",
    }
    for key, value in expected.items():
        if alb.get(key) != value:
            raise AssertionError(f"className alb: {key} is {alb.get(key)!r}, expected {value!r}")
    if not str(alb.get("alb.ingress.kubernetes.io/certificate-arn", "")).startswith("arn:aws:acm:"):
        raise AssertionError(f"className alb: no certificate-arn annotation: {alb}")
    if "nginx.ingress.kubernetes.io/limit-rps" in alb:
        raise AssertionError("className alb: the nginx limit-rps annotation is rendered")


def check_dns() -> None:
    """A32: dnsCidrs adds an ipBlock rule on UDP and TCP 53; the kube-dns rule stays."""
    rules = one(render("ci"), "NetworkPolicy")["spec"]["egress"]
    if len(rules) != 2:
        raise AssertionError(f"expected 2 egress rules by default (kube-dns, 443), found {len(rules)}")
    kube_dns = rules[0]
    if "namespaceSelector" not in kube_dns["to"][0] or not dns_ports_ok(kube_dns):
        raise AssertionError(f"the first egress rule is not the kube-dns rule: {kube_dns}")
    rules = one(render("ci", "--set-json", 'networkPolicy.dnsCidrs=["169.254.20.10/32"]'), "NetworkPolicy")["spec"]["egress"]
    if len(rules) != 3:
        raise AssertionError(f"expected 3 egress rules with one dnsCidr, found {len(rules)}")
    extra = [rule for rule in rules if any(peer.get("ipBlock", {}).get("cidr") == "169.254.20.10/32" for peer in rule["to"])]
    if len(extra) != 1 or not dns_ports_ok(extra[0]):
        raise AssertionError(f"no egress rule for 169.254.20.10/32 on UDP and TCP 53: {rules}")
    if rules[0] != kube_dns:
        raise AssertionError("the kube-dns rule changed when dnsCidrs was set")


CHECKS = [
    check_empty_egress_fails_with_its_message,
    check_names,
    check_identity_gate,
    check_probes_and_shutdown,
    check_ingress,
    check_dns,
]


def main() -> int:
    failed = 0
    for check in CHECKS:
        try:
            check()
        except AssertionError as err:
            failed += 1
            print(f"FAIL {check.__name__}: {err}")
        else:
            print(f"ok   {check.__name__}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Change the helm job in `.github/workflows/ci.yml`**

Edit. Old text:

```yaml
      - uses: azure/setup-helm@v4
      - run: |
          helm lint deploy/helm/viz-site
          helm template ci deploy/helm/viz-site > /tmp/rendered.yaml
          cat /tmp/rendered.yaml
          if helm template ci deploy/helm/viz-site --set-json 'networkPolicy.egressCidrs=[]' > /dev/null 2>&1; then
            echo "an empty networkPolicy.egressCidrs must fail the render"; exit 1
          fi
```

New text:

```yaml
      - uses: azure/setup-helm@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
      - run: python -m pip install "pyyaml>=6"
      # helm lint renders every template, NOTES.txt included. helm_checks.py
      # renders the chart in several configurations and checks names, the
      # identity gate, probes and the PodDisruptionBudget, the ingress
      # annotations, the DNS egress rules, and that an empty egressCidrs fails
      # with the chart's own message.
      - run: |
          helm lint deploy/helm/viz-site
          helm template ci deploy/helm/viz-site
          python .github/scripts/helm_checks.py
```

- [ ] **Step 5: Run the tests and the whole suite, then commit**

Run: `.venv/Scripts/python -m pytest tests/deploy/test_helm_checks.py tests/deploy/test_ci.py -v` then `.venv/Scripts/python -m pytest`
Expected: all pass except `test_chart_passes_every_check`, which is SKIPPED on this machine. Also run `.venv/Scripts/python -m py_compile .github/scripts/helm_checks.py` (no output means it compiles). The checks themselves run only in the CI helm job; say so in your report.

```bash
git add .github/scripts/helm_checks.py .github/workflows/ci.yml tests/deploy/test_helm_checks.py tests/deploy/test_ci.py
git -c user.name="tripp" -c user.email="dom4domg@gmail.com" commit -m "ci: render the Helm chart in several configurations and check it" -m "Co-Authored-By: <model name from your harness> <noreply@anthropic.com>
Claude-Session: <session url from your harness>"
```

---

### Task 9: Bucket policy denies writes except the publisher; AWS README (A38, A35)

**Files:**
- Modify: `deploy/aws/bucket-policy.json`, `deploy/aws/README.md`, `tests/deploy/test_aws_policies.py`

**Interfaces:**
- Consumes: the existing placeholders `REPLACE_ME-viz-bucket`, `123456789012`, `viz-site-publisher`, `vpce-REPLACE_ME`; the ServiceAccount naming from Task 2.
- Produces: a third bucket policy statement `DenyWritesExceptThePublisherRole` denying `s3:PutObject`, `s3:DeleteObject` and `s3:DeleteObjectVersion` (decided by the lead) to every principal except the publisher role; a README with the VPC endpoint ordering, the write Deny and an IRSA trust policy example for namespace `viz` and service account `viz-site`. Task 10 points at them. The publisher role's own policy (`publisher-policy.json`) is unchanged: it allows `s3:DeleteObject`, which plan 5a's clean-up step needs, and never needed `s3:DeleteObjectVersion`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/deploy/test_aws_policies.py`:

```python
def _statement(sid: str) -> dict:
    found = [s for s in _policy("bucket-policy.json")["Statement"] if s.get("Sid") == sid]
    assert len(found) == 1, sid
    return found[0]


def test_writes_are_denied_to_everyone_but_the_publisher_role():
    deny = _statement("DenyWritesExceptThePublisherRole")
    assert deny["Effect"] == "Deny"
    assert deny["Principal"] == "*"
    # DeleteObjectVersion too: the bucket is versioned, and deleting a version is a write.
    assert sorted(deny["Action"]) == ["s3:DeleteObject", "s3:DeleteObjectVersion", "s3:PutObject"]
    assert deny["Resource"] == "arn:aws:s3:::REPLACE_ME-viz-bucket/*"
    assert deny["Condition"] == {
        "ArnNotLike": {"aws:PrincipalArn": ["arn:aws:iam::123456789012:role/viz-site-publisher"]}
    }


def test_write_deny_exempts_the_same_publisher_as_the_read_deny():
    write = _statement("DenyWritesExceptThePublisherRole")["Condition"]["ArnNotLike"]
    read = _statement("DenyReadsOutsideTheVpcEndpointExceptPublishers")["Condition"]["ArnNotLike"]
    assert write == read


def test_readme_explains_the_write_deny_and_endpoint_order():
    text = " ".join((AWS / "README.md").read_text(encoding="utf-8").split())
    assert ("denies `s3:PutObject`, `s3:DeleteObject` and `s3:DeleteObjectVersion` to every principal "
            "except the publisher role") in text
    assert text.index("S3 gateway VPC endpoint") < text.index("**Bucket policy**")


def test_readme_shows_the_irsa_trust_policy():
    text = (AWS / "README.md").read_text(encoding="utf-8")
    assert "system:serviceaccount:viz:viz-site" in text
    assert "sts:AssumeRoleWithWebIdentity" in text
    assert "choose the namespace and the\nHelm release name before you create the role" in text
```

- [ ] **Step 2: Run them to see them fail**

Run: `.venv/Scripts/python -m pytest tests/deploy/test_aws_policies.py -v`
Expected: the four new tests FAIL; the rest pass.

- [ ] **Step 3: Add the write Deny to `deploy/aws/bucket-policy.json`**

Edit. Old text:

```json
        "ArnNotLike": {"aws:PrincipalArn": ["arn:aws:iam::123456789012:role/viz-site-publisher"]}
      }
    }
  ]
}
```

New text:

```json
        "ArnNotLike": {"aws:PrincipalArn": ["arn:aws:iam::123456789012:role/viz-site-publisher"]}
      }
    },
    {
      "Sid": "DenyWritesExceptThePublisherRole",
      "Effect": "Deny",
      "Principal": "*",
      "Action": ["s3:PutObject", "s3:DeleteObject", "s3:DeleteObjectVersion"],
      "Resource": "arn:aws:s3:::REPLACE_ME-viz-bucket/*",
      "Condition": {
        "ArnNotLike": {"aws:PrincipalArn": ["arn:aws:iam::123456789012:role/viz-site-publisher"]}
      }
    }
  ]
}
```

Then run `.venv/Scripts/python -c "import json; json.load(open('deploy/aws/bucket-policy.json'))"` (no output means the JSON is valid).

- [ ] **Step 4: Update the bucket policy bullet in `deploy/aws/README.md`**

Edit. Old text:

```markdown
- **Bucket policy**: `bucket-policy.json`. It denies plain HTTP, and denies
  reads that do not come through the cluster's S3 VPC endpoint, except for
  the publisher role, because publishers run `viz publish` from their own
  machines. Nobody else, including administrators, can read objects from outside the VPC endpoint; for break-glass access, edit the bucket policy first.
```

New text:

```markdown
- **S3 gateway VPC endpoint**: the bucket policy needs its id. Create the
  endpoint in the cluster's VPC before you apply the policy, and record its
  `vpce-...` id (`docs/work-setup.md`, step 5, has the command).
- **Bucket policy**: `bucket-policy.json`. It denies plain HTTP; denies
  reads that do not come through the cluster's S3 VPC endpoint, except for
  the publisher role, because publishers run `viz publish` from their own
  machines; and denies `s3:PutObject`, `s3:DeleteObject` and
  `s3:DeleteObjectVersion` to every principal except the publisher role, so
  no other role in the account can change what the site shows or erase an
  object's history, whatever its own IAM policy allows. Nobody
  else, including administrators, can read objects from outside the VPC
  endpoint, or write or delete objects at all; for break-glass access, edit
  the bucket policy first. If publishers sign in with a different role (for
  example an AWS SSO role), add its ARN to both exemptions.
```

- [ ] **Step 5: Replace the IRSA paragraph in `deploy/aws/README.md`**

Edit. Old text:

```markdown
For IRSA, the server role's trust policy allows the cluster's OIDC provider
for the service account `viz-site` in the release namespace. Put the role
ARN in the Helm value `serviceAccount.roleArn`.
```

New text:

````markdown
For IRSA, the server role's trust policy allows the cluster's OIDC provider
for one service account in one namespace, so choose the namespace and the
Helm release name before you create the role. The chart names the service
account after the release (`helm install viz-site ...` gives `viz-site`;
another release name `x` gives `x-viz-site`), or uses the Helm value
`serviceAccount.name` when you set it. With namespace `viz` and release
`viz-site` the trust policy is:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {"Federated": "arn:aws:iam::123456789012:oidc-provider/oidc.eks.REPLACE_ME-region.amazonaws.com/id/REPLACE_ME"},
      "Action": "sts:AssumeRoleWithWebIdentity",
      "Condition": {
        "StringEquals": {
          "oidc.eks.REPLACE_ME-region.amazonaws.com/id/REPLACE_ME:sub": "system:serviceaccount:viz:viz-site",
          "oidc.eks.REPLACE_ME-region.amazonaws.com/id/REPLACE_ME:aud": "sts.amazonaws.com"
        }
      }
    }
  ]
}
```

Put the role ARN in the Helm value `serviceAccount.roleArn`.
````

- [ ] **Step 6: Run the tests and the whole suite, then commit**

Run: `.venv/Scripts/python -m pytest tests/deploy/test_aws_policies.py -v` then `.venv/Scripts/python -m pytest`
`test_only_placeholder_accounts_and_names` must still pass (the only 12-digit number is `123456789012`).

```bash
git add deploy/aws/bucket-policy.json deploy/aws/README.md tests/deploy/test_aws_policies.py
git -c user.name="tripp" -c user.email="dom4domg@gmail.com" commit -m "fix(aws): bucket policy denies writes except the publisher role; IRSA trust example" -m "Co-Authored-By: <model name from your harness> <noreply@anthropic.com>
Claude-Session: <session url from your harness>"
```

---

### Task 10: The work-machine guide in the right order (A35, A36, B1)

**Files:**
- Modify: `docs/work-setup.md`, `tests/test_work_setup_doc.py`

**Interfaces:**
- Consumes: everything from Tasks 2 to 9; `VIZ_IT_S3_PREFIX` in `tests/storage/test_s3_integration.py` (a key prefix; the test appends `integration-<hex>/`); `VIZ_ROOT_PREFIX`; the publisher policy covers `viz/*`, so the scratch prefix `viz/_scratch/` is writable by the publisher and never listed by the site (the tree reads only `<root>charts/` and `<root>dashboards/`).
- Produces: the guide.

Note on `test_every_viz_command_named_exists`: it treats any `viz <lowercase word>` in the guide as a CLI command. Never write `-n viz <word>` or `namespace viz <word>` with a word after `viz`; the text below always ends those commands with `viz`.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_work_setup_doc.py`:

```python
def test_the_guide_covers_the_hardening_steps():
    text = _text()
    for phrase in (
        "kubectl create namespace viz",
        "create-vpc-endpoint",
        "system:serviceaccount:",
        "VIZ_IT_S3_PREFIX=viz/_scratch/",
        "VIZ_ROOT_PREFIX=viz/_scratch/",
        "aws s3 rm s3://your-viz-bucket/viz/_scratch/ --recursive",
        "VIZ_REQUIRE_IDENTITY",
        "requireIdentity",
        "401",
        "ingress.rateLimit.enabled",
        "Pods never call KMS",
        "helm install viz-site deploy/helm/viz-site -f my-values.yaml -n viz",
        "check that the folder tree loads",
    ):
        assert phrase in text, phrase
    # A35: the dead cross-reference is gone, and the steps are in dependency order.
    assert "Author on S3" not in text
    assert text.index("kubectl create namespace viz") < text.index("create-vpc-endpoint") < text.index("vpce-REPLACE_ME")
    assert text.index("viz publish .viz-staging/charts/smoke/first-chart") < text.index("aws s3 rm")
    # The smoke chart lives under the scratch prefix now, never on the real site.
    assert "/c/smoke/first-chart" not in text
```

- [ ] **Step 2: Run it to see it fail**

Run: `.venv/Scripts/python -m pytest tests/test_work_setup_doc.py -v`
Expected: `test_the_guide_covers_the_hardening_steps` FAILS; the rest pass.

- [ ] **Step 3: Settings table rows for the identity header and the gate**

Plan 5a wrote these two rows. Replace them (both lines together, exactly as 5a left them):

```markdown
| `VIZ_AUTH_HEADER` | `X-Forwarded-Email` | server | Identity header from the SSO proxy. Logged with every request; required when `VIZ_REQUIRE_IDENTITY` is true |
| `VIZ_REQUIRE_IDENTITY` | `false` | server | When `true`, every request except `GET` and `HEAD /api/health` without a non-empty `VIZ_AUTH_HEADER` gets 401. Turn it on in deployment, behind the SSO proxy |
```

with:

```markdown
| `VIZ_AUTH_HEADER` | `X-Forwarded-Email` | server | Identity header set by the SSO proxy. Logged with every request; required on every request when `VIZ_REQUIRE_IDENTITY` is true |
| `VIZ_REQUIRE_IDENTITY` | `false` | server | When true, every request except `GET` and `HEAD /api/health` without the `VIZ_AUTH_HEADER` header gets 401. The Helm chart sets it to true (value `requireIdentity`); local runs and `viz preview` leave it off |
```

If the old text is not found exactly, replace each of the two rows (found by its first cell) with its new row, and report the difference.

- [ ] **Step 4: Rewrite step 5**

Replace everything from the line `## 5. Create the AWS resources` up to, but not including, the line `## 6. Prove the real integrations` with the text below. No earlier plan (5a, 5b, 5c) edits this section, so it should match the original quoted after the new text. If it does not, keep any sentence an earlier plan added by putting it at the end of the matching numbered item below, and say so in your report.

New text:

````markdown
## 5. Create the AWS resources

Do these in order: later items need values from earlier ones.

1. **Choose the namespace and the Helm release name.** The IRSA trust policy
   names the pods' service account as
   `system:serviceaccount:<namespace>:<service account>`, so both must be
   fixed before you create the server role. This guide uses the namespace
   `viz` and the release `viz-site`, which gives the service account
   `viz-site` (another release name `x` gives `x-viz-site`; the Helm value
   `serviceAccount.name` overrides it). Create the namespace now:
   `kubectl create namespace viz`
2. **Create the S3 gateway VPC endpoint** in the cluster's VPC, attached to
   the route tables of the subnets the nodes run in, and write down its id
   (`vpce-...`). The pods reach S3 through it, and the bucket policy in the
   next item needs the id.

   ```
   aws ec2 create-vpc-endpoint --vpc-endpoint-type Gateway \
     --vpc-id <cluster vpc id> --service-name com.amazonaws.<region>.s3 \
     --route-table-ids <route table ids of the node subnets> \
     --query VpcEndpoint.VpcEndpointId --output text
   ```

   If the VPC already has an S3 gateway endpoint, use its id instead:
   `aws ec2 describe-vpc-endpoints --filters Name=service-name,Values=com.amazonaws.<region>.s3`
3. **Create the bucket, roles and policies**: `deploy/aws/README.md`. That
   covers the bucket baseline, the bucket policy (put the id from item 2 in
   place of `vpce-REPLACE_ME`), the KMS key policy, the `viz-site-server`
   role with its IRSA trust policy (use the namespace and service account
   from item 1), and the `viz-site-publisher` role.
4. **Act as the publisher role on your laptop.** To run `viz publish` and
   `viz move`, add a profile that assumes `viz-site-publisher`, with a fixed
   `role_session_name`. A fixed session name keeps your AWS identity, and so
   the author stamped on charts you stage from files, the same from one
   command to the next.

   ```
   # ~/.aws/config
   [profile viz-publisher]
   role_arn = arn:aws:iam::123456789012:role/viz-site-publisher
   source_profile = default
   role_session_name = viz-publisher
   region = your-region
   ```

   Then `export AWS_PROFILE=viz-publisher` before running publisher commands.

   If your company signs in with AWS SSO, the SSO role is not
   `viz-site-publisher`; either assume the publisher role from it as above,
   or add your SSO role's ARN to both publisher exemptions in
   `deploy/aws/bucket-policy.json` (the read Deny and the write Deny). Only
   the publisher role can write to the bucket.
````

Original section 5 (for comparison only; do not paste it):

````markdown
## 5. Create the AWS resources

Create the bucket, roles and policies: `deploy/aws/README.md`. That covers
the bucket baseline, the KMS key policy, and the `viz-site-server` and
`viz-site-publisher` IAM roles. Do this before the next step, which proves
the real integrations against those resources.

To run `viz publish` and `viz move` from your laptop, act as the
`viz-site-publisher` role. Add a profile that assumes it, with a fixed
`role_session_name` (see "Author on S3" in step 2 for why a fixed session
name matters):

```
# ~/.aws/config
[profile viz-publisher]
role_arn = arn:aws:iam::123456789012:role/viz-site-publisher
source_profile = default
role_session_name = viz-publisher
region = your-region
```

Then `export AWS_PROFILE=viz-publisher` before running publisher commands.

If your company signs in with AWS SSO, the SSO role is not
`viz-site-publisher`; either assume the publisher role from it as above, or
add your SSO role's ARN to the publisher exemption in
`deploy/aws/bucket-policy.json`.
````

- [ ] **Step 5: Step 6 writes under a scratch prefix and cleans up**

In section `## 6. Prove the real integrations`, replace everything from the line that starts `S3 (writes, reads, copies and deletes two small objects under a throwaway` up to, but not including, the line `## 7. Deploy` with the text below. Plan 5b (finding A16) already changed the `viz query` line of the publish block to `--sql-file first.sql`; the text below keeps that form. The Databricks paragraph above this range (with `tests/publish/test_query_integration.py`) is not touched. Each integration test file is run on its own, as the guide shows; never set `VIZ_INTEGRATION=1` for the whole suite.

````markdown
S3 (writes, reads, copies and deletes two small objects under a throwaway
prefix; needs the publisher role's credentials). Point it at the scratch
prefix `viz/_scratch/`. The publisher policy covers it, and the site never
lists it: the site reads only `viz/charts/` and `viz/dashboards/`.

```
export VIZ_INTEGRATION=1 VIZ_IT_S3_BUCKET=your-viz-bucket VIZ_IT_S3_PREFIX=viz/_scratch/ AWS_REGION=your-region
.venv/bin/python -m pytest tests/storage/test_s3_integration.py -v
```

Then publish one real chart end to end, also under the scratch prefix, so
nothing appears on the real site:

```
export VIZ_STORAGE=s3 VIZ_S3_BUCKET=your-viz-bucket VIZ_ROOT_PREFIX=viz/_scratch/ AWS_REGION=your-region
echo "SELECT 'a' AS label, 1 AS value" > first.sql
.venv/bin/viz query --sql-file first.sql --id smoke/first-chart
.venv/bin/viz validate .viz-staging/charts/smoke/first-chart
.venv/bin/viz publish .viz-staging/charts/smoke/first-chart
aws s3 ls s3://your-viz-bucket/viz/_scratch/charts/smoke/first-chart/
```

The listing shows `chart.json` and one data file named
`data.<16 hex characters>.<format>`. Publishing the same id again is
refused with the current author and date; add `--force` to `viz publish`
only when you mean to replace it.

Clean up when you are done, and clear the scratch prefix before you publish
anything real:

```
aws s3 rm s3://your-viz-bucket/viz/_scratch/ --recursive
rm -rf .viz-staging/charts/smoke first.sql
unset VIZ_ROOT_PREFIX VIZ_IT_S3_PREFIX
```

Versioning keeps the deleted objects as noncurrent versions for 30 days (see
`deploy/aws/README.md`); that is expected. On PowerShell, clear a variable
with `Remove-Item Env:VIZ_ROOT_PREFIX`.

````

- [ ] **Step 6: Step 7 names the namespace, the rate limit and the identity gate**

In section `## 7. Deploy`, keep item 1 (the `docker build` item) as it is. Replace everything from the line that begins with `2. Copy` (item 2) up to, but not including, the line `## Troubleshooting` with:

````markdown
2. Copy `deploy/helm/viz-site/values.yaml`, fill in every `REPLACE_ME`,
   `example.com` and `123456789012` value (including
   `networkPolicy.egressCidrs`, and `ingress.alb.certificateArn` if you set
   `ingress.className: alb`), and install into the namespace from step 5:
   `helm install viz-site deploy/helm/viz-site -f my-values.yaml -n viz`
3. Rate limit. With ingress-nginx the chart limits each client IP to
   `ingress.rateLimit.perSecond` requests per second. Behind the company SSO
   proxy every request arrives from the proxy's IP, so all users share that
   one limit and the site starts refusing everyone under normal use. Set
   `ingress.rateLimit.enabled: false` when a proxy sits in front of the
   ingress. On ALB the value does nothing; use a WAF rate-based rule there.
4. Identity. The site has no login of its own. With `requireIdentity: true`
   (the default), every request except `/api/health` that lacks the
   `authHeader` header (`X-Forwarded-Email` by default) gets 401, so until
   the SSO proxy is in front of the site every page returns 401. For a first
   smoke test before the proxy exists, send the header yourself through a
   port forward (use a host from your `allowedHosts`):

   ```
   kubectl port-forward svc/viz-site 8080:80 -n viz
   curl -H "Host: viz.internal.example.com" -H "X-Forwarded-Email: you@example.com" http://127.0.0.1:8080/api/tree
   ```

   Or install once with `--set requireIdentity=false` added to the
   `helm install` line, check, and run
   `helm upgrade viz-site deploy/helm/viz-site -f my-values.yaml -n viz`
   as soon as the proxy is in place to turn the gate back on. Never leave it
   off: without it anyone who can reach the load balancer sees every chart.
5. Put the site behind the company SSO proxy. Check
   `https://<your host>/api/health`; it returns `{"status": "ok"}` but does
   not touch S3, so it only says the pods are running. Then open
   `https://<your host>/` and check that the folder tree loads.

````

- [ ] **Step 7: Troubleshooting rows**

Find the row that starts `| Pods never become ready |` and the row directly below it that starts `| Pods are Ready but pages show errors or an empty tree |`. Replace those two rows with these three:

```markdown
| Every page returns 401 | `requireIdentity` is on and the request did not come through the SSO proxy (no `X-Forwarded-Email` header). See step 7 |
| Pods never become ready | The container exits at start (`kubectl logs`), or the cluster's NetworkPolicy engine blocks the kubelet's probes. `/api/health` needs neither S3 nor an allowed Host header |
| Pods are Ready but pages show errors or an empty tree | The pods cannot read the bucket: check `networkPolicy.egressCidrs` (S3 and STS), the IRSA role and its trust policy, and the KMS key policy. Pods never call KMS themselves; S3 calls KMS on their behalf, so no egress rule for KMS is needed, but the key policy must allow the `viz-site-server` role `kms:Decrypt` |
```

- [ ] **Step 8: Run the tests and the whole suite, then commit**

Run: `.venv/Scripts/python -m pytest tests/test_work_setup_doc.py -v` then `.venv/Scripts/python -m pytest`
If `test_every_viz_command_named_exists` fails, some line has `viz ` followed by a word that is not a CLI command (see the note at the top of this task): reword that line so `viz` ends the command, do not change the test.

```bash
git add docs/work-setup.md tests/test_work_setup_doc.py
git -c user.name="tripp" -c user.email="dom4domg@gmail.com" commit -m "docs: work-setup in dependency order, scratch-prefix smoke, identity gate and rate limit" -m "Co-Authored-By: <model name from your harness> <noreply@anthropic.com>
Claude-Session: <session url from your harness>"
```

---

### Task 11: README says there is no login; spec 12.5 matches the chart

**Files:**
- Create: `tests/test_readme.py`
- Modify: `README.md`, `docs/superpowers/specs/2026-09-22-viz-site-design.md` (section 12.5 only)

**Interfaces:**
- Consumes: the README section `## Trust assumptions, read these first`; spec 12.5's Helm defaults paragraph.
- Produces: user-facing wording only.

- [ ] **Step 1: Write the failing test**

Create `tests/test_readme.py`:

```python
"""README states the trust assumptions in plain words (spec 12.1, hardening B1)."""
from pathlib import Path

README = Path(__file__).resolve().parents[1] / "README.md"


def _trust_section() -> str:
    text = README.read_text(encoding="utf-8")
    section = text.split("## Trust assumptions, read these first", 1)[1].split("\n## ", 1)[0]
    return " ".join(section.split())


def test_readme_says_the_site_has_no_login_of_its_own():
    section = _trust_section()
    for phrase in ("no login of its own", "SSO proxy", "`requireIdentity: true`", "401", "publishing is sharing"):
        assert phrase in section, phrase
```

- [ ] **Step 2: Run it to see it fail**

Run: `.venv/Scripts/python -m pytest tests/test_readme.py -v`
Expected: FAILS on `no login of its own`.

- [ ] **Step 3: Add the bullet to `README.md`**

Edit. Old text:

```markdown
## Trust assumptions, read these first

```

New text:

```markdown
## Trust assumptions, read these first

- The site has no login of its own. It relies on the company SSO proxy in
  front of it and, by default in the Helm chart (`requireIdentity: true`),
  refuses with 401 every request that did not come through that proxy.
  Anyone the proxy lets in can see every chart and dashboard: publishing is
  sharing.
```

(The old text is the heading line followed by one empty line. The new bullet goes directly above the existing first bullet, `- Publishing a chart or dashboard means sharing it ...`, which stays.)

- [ ] **Step 4: Update spec 12.5**

Edit `docs/superpowers/specs/2026-09-22-viz-site-design.md`. Old text:

```markdown
  for streaming; IRSA or pod identity, never the node role. Per-IP rate limit
  at the ingress.
```

New text:

```markdown
  for streaming; IRSA or pod identity, never the node role. Per-IP rate limit
  at the ingress, switchable off (`ingress.rateLimit.enabled`) because behind
  an SSO proxy every request shares the proxy's IP. The identity gate
  (`requireIdentity`, env `VIZ_REQUIRE_IDENTITY`) is on by default. Separate
  readiness and liveness probes, a preStop delay, and a PodDisruptionBudget
  when there is more than one replica. With the AWS Load Balancer Controller:
  internal scheme, target type ip, HTTPS listener, health check on
  `/api/health`.
```

- [ ] **Step 5: Run the tests and the whole suite, then commit**

Run: `.venv/Scripts/python -m pytest tests/test_readme.py -v` then `.venv/Scripts/python -m pytest`

```bash
git add README.md tests/test_readme.py docs/superpowers/specs/2026-09-22-viz-site-design.md
git -c user.name="tripp" -c user.email="dom4domg@gmail.com" commit -m "docs: README says the site has no login of its own; spec 12.5 matches the chart" -m "Co-Authored-By: <model name from your harness> <noreply@anthropic.com>
Claude-Session: <session url from your harness>"
```

---

### Task 12: Final verification

**Files:** none changed unless a check fails.

- [ ] **Step 1: Run the whole suite**

Run: `.venv/Scripts/python -m pytest`
Expected: all pass; skipped tests include `test_chart_passes_every_check` (no helm) and the opt-in integration tests. Record the summary line.

- [ ] **Step 2: Compile the CI scripts**

Run: `.venv/Scripts/python -m py_compile .github/scripts/docker_smoke.py .github/scripts/helm_checks.py`
Expected: no output.

- [ ] **Step 3: Look for leftovers**

Use the Grep tool (not the shell) for each pattern over the repo, excluding `docs/superpowers/`:
- `rateLimitPerSecond`: expected no matches.
- `\.Values\.serviceAccount\.name`: expected matches only in `deploy/helm/viz-site/templates/_helpers.tpl`.
- `viz-site-viz-site`: expected no matches.
- `/c/smoke/first-chart`: expected no matches.

If any check fails, fix the file in the smallest way, rerun the suite, and commit that file alone with subject `fix: <what was left over>` and the two trailers.

- [ ] **Step 4: Report what only CI can prove**

These cannot run on this machine (no helm, no docker). Say so explicitly in the report:
1. The docker job: the image builds; with the sample bucket mounted read-only, `docker_smoke.py` prints `ok` for `/api/health`, for the wasm extension and for `/api/tree lists N dashboards`; the container runs as uid 10001.
2. The helm job: `helm lint` (which renders NOTES.txt), `helm template`, and `helm_checks.py` printing `ok` for all six checks.
3. The web, python and gitleaks jobs as before.
4. Nothing proves the ALB, IRSA, VPC endpoint, bucket policy or identity gate against real AWS; that is the user's checklist in `docs/work-setup.md` at work.

- [ ] **Step 5: Push only with the user's approval, then check the Actions run**

Do not push on your own. Report to the controller that the branch `hardening` is ready. Only after the user approves: push the branch (`git push origin hardening`; never force). CI runs on pushes to `main` and on pull requests, so the controller opens a pull request from `hardening` to `main` in the GitHub web UI (there is no `gh` CLI on this machine). Then open the Actions run for that pull request and confirm all five jobs pass. In the docker and helm job logs, confirm the `ok` lines listed in Step 4. If a job fails, report the failing step's log; do not change the checks to make them pass.

---

## Self-review notes

- A27: Task 1 (script, local tests through the real app, CI docker job with the sample bucket mounted read-only and `VIZ_STORAGE=local`, `VIZ_LOCAL_DIR=/data`, which are the `Settings` names in `viz/config.py`).
- A28: Task 8 (`check_empty_egress_fails_with_its_message` asserts the chart's own message; a pytest ties the script's text to `networkpolicy.yaml`).
- A30: Task 5 (ALB annotations only for `className: alb`) and Task 8 (`check_ingress`).
- A31: Task 2 and Task 8 (`check_names`); docs in Tasks 7, 9, 10.
- A32: Task 6 and Task 8 (`check_dns`).
- A33: Task 4 and Task 8 (`check_probes_and_shutdown`).
- A34: Task 7; also the guide (Task 10 step 6 item 5) and troubleshooting.
- A35: Task 9 (README order and trust policy) and Task 10 (namespace first, VPC endpoint before the bucket policy, dead cross-reference removed, scratch prefix and cleanup, KMS line corrected).
- A36: Task 5 (flag and comment) and Task 10 (sentence in the guide).
- A38: Task 9 (write Deny on `s3:PutObject`, `s3:DeleteObject` and `s3:DeleteObjectVersion`, as the lead decided).
- Cross-plan anchors: Task 10 anchors on the `docs/work-setup.md` rows plan 5a wrote and the `--sql-file first.sql` line plan 5b wrote; Task 11 touches only the README trust section (5b edited other README lines) and spec 12.5 (5a and 5c edited other sections).
- B1 (Helm and docs): Task 3, Task 7, Task 10, Task 11.
- README auth wording: Task 11.
- Data file rename from 5a: no deploy policy or doc in scope names `data.json` or `data.parquet`; the guide's listing text uses the new `data.<16 hex>.<format>` form.
