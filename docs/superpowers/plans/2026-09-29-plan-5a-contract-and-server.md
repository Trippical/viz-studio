# Plan 5a: Contract and server hardening (atomic publish, identity gate, tree isolation) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make publishing atomic (a reader never sees a chart.json whose data file is missing or belongs to another version), let the server refuse requests that did not come through the SSO proxy, stop one hostile object in the bucket from breaking the whole tree, and fix the small server and contract bugs A1, A2, A3, A17, A18, A29 and A37.

**Architecture:** Data files become content-addressed: chart.json gains `data.file` = `data.<first 16 hex of SHA-256>.<format>`, and the bucket key is `<root>/charts/<id>/<data.file>`. Publishing writes the data file, then PUTs chart.json conditionally (`If-None-Match: *` for a new chart, `If-Match: <etag>` for an overwrite), then deletes older data files except the one the replaced chart.json named. The storage layer gains conditional puts and a `PreconditionFailed` error on both backends. The server reads `data.file` to stream data, answers `GET` and `HEAD /api/health` before the Host check, and with `VIZ_REQUIRE_IDENTITY=true` returns 401 to requests without the identity header (health exempt for both methods). The tree builder catches every per-document failure, and schemas refuse documents nested deeper than 64 levels before validating them.

**Tech Stack:** Python 3.11, FastAPI/Starlette, pydantic-settings, jsonschema, boto3 (floor raised to 1.35.69 for `IfMatch`), moto, pytest; TypeScript types only on the front end (Vite/Vitest, `tsc`).

**Spec:** Binding: `docs/superpowers/specs/2026-09-29-hardening-decisions.md` (sections "B2", "B1", "A29", "B3"; this plan is "5a"). Finding texts: `docs/superpowers/specs/2026-09-29-hardening-findings.md` (A1, A2, A3, A17, A18, A37, intent item 4). Updated by Task 11: `docs/superpowers/specs/2026-09-22-viz-site-design.md` sections 1, 4.1, 4.2, 5.1, 6.2, 11, 12.2, 12.3, 12.4, 12.7.

**Interpretations of the decisions file (read these):**

1. Decision B2.6 (as amended by the lead) keeps `head(key) -> ObjectInfo(key, size, etag, last_modified)`, because the server's size check and the data route depend on it. This plan uses `head(key).etag` (unquoted) everywhere the decision says "ETag"; plans 5b to 5d do the same. It still raises `NotFound`. The local backend's ETag becomes the hex MD5 of the bytes, as the decision says, for `head` and `list` alike.
2. A37: the Plotly/ECharts keys (`link`, `sublink`, `graphic`, `extraCssText`, `appendTo`, `className`, `images`, `mapbox`, `map`) protect nothing in Vega-Lite (Vega-Lite has no such properties; `web/src/renderers/vegaLiteSanitize.ts` rejects only `url`, `values`, `href`, `usermeta`, `datasets` and image marks; `viz/schemas.py::_check_vegalite` rejects `data` other than `{"name": "data"}`, `values`, `datasets` and image marks). They are removed. To keep the lists consistent the schema list becomes exactly the browser list plus `__proto__`, `constructor`, `prototype`, which adds `values` to the schema list. A test parses the browser list so the two cannot drift.
3. A18: dashboards get no ancestor-conflict rule at all (the tree drops it; `viz validate` never had it for dashboards). Charts keep it.
4. A1 also covers the CLI's `read_document` and the publisher's `_existing` reader (a deeply nested staged or published file raised `RecursionError` there too). Both are one-line catches.
5. `docs/work-setup.md` gets two table rows (the new `VIZ_REQUIRE_IDENTITY` setting and the corrected `VIZ_ALLOWED_HOSTS` default) because `tests/test_work_setup_doc.py::test_every_setting_is_documented` fails otherwise. Everything else in that guide is plan 5d's.

## Global Constraints

- Python `>=3.11`. Always run the venv interpreter: `.venv/Scripts/python` (Linux/macOS and CI: `.venv/bin/python`). Never the system `python`.
- No new dependencies. The only `pyproject.toml` change is the boto3 floor, `boto3>=1.35` to `boto3>=1.35.69` (botocore 1.35.69 is the first release whose `PutObject` accepts `IfMatch`; checked against the published wheels). The installed boto3 is newer, so nothing needs reinstalling. The commit message of Task 1 says so (CLAUDE.md rule 7).
- No write routes on the server. The data route stays `GET/HEAD /api/data/{id}`; the URL the front end uses does not change.
- `schema_version` stays `1`.
- The sample bucket stays synthetic (`author` `sample@example.com`, `warehouse_id` `sample`). Only `sample-bucket/generate.py` writes it.
- Out of scope here, do not touch: `deploy/` and Helm (plan 5d), `README.md` (5d), `skills/` (5b), `viz/publish/cli.py` messages (5b), every file under `web/src` except `web/src/api/types.ts` and the three test files named in Task 4 (5c).
- Every commit message follows the "Commit messages" section of `CLAUDE.md`: subject, blank line, optional body, then two contiguous trailer lines (`Co-Authored-By` naming the model that made the commit as its harness states it, and `Claude-Session` with the session URL its harness states), produced with two `-m` flags. The commit steps below write them as placeholders; fill them from your harness.
- The whole Python suite (`.venv/Scripts/python -m pytest`) must pass before every commit.

## Review Focus

1. **Clean-up deletes the data file a reader still needs.** A viewer loaded chart.json a moment before a republish, then fetches its data after it. Expected: the file the replaced chart.json named survives one more publish. Pinned in Task 3 (`test_a_reader_of_the_replaced_chart_json_can_still_fetch_its_data`, `test_publish_keeps_the_new_and_one_previous_data_file`).
2. **Conditional PUT wired wrong for real S3.** Unquoted `IfMatch`, a 409 `ConditionalRequestConflict` treated as a crash, or `If-Match` on a key deleted meanwhile (S3 answers 404 `NoSuchKey`) escaping as a traceback. Expected: all three become `PreconditionFailed`. Pinned in Task 1 (`test_s3_sends_the_conditions_to_put_object`, `test_s3_maps_conditional_failures`, `test_if_match_on_a_missing_key_is_precondition_failed`).
3. **Stale data files left behind** in the regenerated sample bucket or in a staged directory, so validation or the server picks the wrong file. Expected: every chart directory holds exactly the one file its chart.json names, and `viz validate` rejects a staged directory with any other `data.*` file. Pinned in Task 2 (`test_every_chart_directory_holds_exactly_its_content_addressed_data_file`, `test_other_data_files_in_the_staged_directory_fail`).
4. **The health exemption is too wide or too narrow.** Too wide: other paths, or other methods such as POST on `/api/health`, skip the Host check or the identity gate. Too narrow: the load balancer's health check (pod IP as Host, no identity header, GET or HEAD) gets 400, 401 or 405 and the pod never becomes ready. Pinned in Task 6 (`test_health_is_answered_for_any_host`) and Task 7 (`test_health_from_a_load_balancer_needs_neither_host_nor_identity`, `test_every_path_needs_identity`).
5. **The nesting cap rejects real charts, or RecursionError still escapes.** Expected: every sample chart is under the cap, and a 300-deep or 100,000-deep chart.json becomes one error node while `/api/tree` answers 200. Pinned in Task 5 (`test_every_sample_chart_is_under_the_depth_cap`, `test_deeply_nested_chart_becomes_an_error_node`, `test_tree_route_survives_a_storage_error`).

---

## Before you start (the controller does this once, not a task)

Plans 5a, 5b, 5c and 5d run one after another on the branch `hardening`. The controller creates it with `git checkout -b hardening` from an up-to-date `main`, and commits the two hardening documents under `docs/superpowers/specs/` and the four plan files on it. A task never commits them. Task 0 then checks that this was done.

---

### Task 0: Confirm the branch and a green suite

**Files:** none changed. No commit.

**Interfaces:**
- Consumes: nothing from another plan (5a is the first of the four).
- Produces: a short report; Task 1 starts only after it.

- [ ] **Step 1: Check the branch**

Run: `git branch --show-current`
Expected: `hardening`. If it prints anything else (for example `main`), stop and report. Do not create or switch branches yourself; the controller does that.

- [ ] **Step 2: Check the hardening documents are committed**

Run: `git log --oneline -1 -- docs/superpowers/specs/2026-09-29-hardening-decisions.md docs/superpowers/plans/2026-09-29-plan-5a-contract-and-server.md`
Expected: one commit line. If it prints nothing, stop and report.

- [ ] **Step 3: Run the whole Python suite**

Run: `.venv/Scripts/python -m pytest`
Expected: all pass, 0 failed (some tests are skipped: the symlink test on Windows and the opt-in integration tests). If anything fails, stop and report the failing test names.

- [ ] **Step 4: Check the front-end toolchain**

For Task 4 and the final checks, `web/node_modules` must exist. If it does not, run once: `export PATH="/c/Program Files/nodejs:$PATH"` then, from `web/`, `npm ci` and `node node_modules/esbuild/install.js`. Then, from `web/`: `npm test`
Expected: all test files pass.

- [ ] **Step 5: Report**

Report the branch name and the pytest summary line. Nothing is committed.

---

## How to execute a task (read this whether you are a large or a small model)

1. Read `CLAUDE.md` at the repo root first. It has the commands, the commit
   trailers, and the environment gotchas.
2. Work only on the task you were given. Do not start the next one.
3. Do the steps in order. Each step is one action. Do not skip the "run the
   test and see it fail" step; it proves the test is real.
4. Copy the code and text from the step exactly. When a step says "replace",
   use the Edit tool with the old text as `old_string` and the new text as
   `new_string`. When a step says "replace the whole file", Read the file, then
   Write the full new content. If code in a step does not work as written, fix
   the smallest thing that makes it work, and say what you changed and why in
   your report. Do not redesign.
5. If a command fails and you cannot fix it within the task's scope, stop and
   report the full error output. Do not work around it by weakening a test.
6. Before committing, run the whole Python suite:
   `.venv/Scripts/python -m pytest`. It must pass.
7. Stage only the files named in the task's commit step. Never run
   `git add -A`, `git add .`, `git checkout -- .`, `git restore`, `git stash`,
   `git clean` or `git reset`.
8. Report back with: the commit hash, the test summary line, and any
   deviation from the plan. Nothing else is needed.

A guard hook blocks shell commands that contain backticks, `$(...)`, or
redirects to paths outside the project (use `2>&1`, never `2>/dev/null`).
Create and change every file in this plan with the Write and Edit tools, not a
shell heredoc.

---

## File structure

| Path | Responsibility |
|---|---|
| `viz/storage/base.py`, `viz/storage/__init__.py` | `PreconditionFailed`; `put(..., *, if_match, if_none_match)` in the protocol |
| `viz/storage/local.py` | MD5 ETags; conditional put under a process-wide lock |
| `viz/storage/s3.py` | `IfMatch` / `IfNoneMatch='*'` on `put_object`; 412, 409 and If-Match-404 become `PreconditionFailed` |
| `pyproject.toml` | `boto3>=1.35.69` |
| `schemas/chart.schema.json` | required `data.file`; extension equals `data.format`; forbidden-key list (A37) |
| `viz/ids.py` | `DATA_FILE_PATTERN`, `data_file_name(sha256_hex, fmt)`, `data_key(root, chart_id, file_name)` |
| `viz/publish/staging.py` | writes the data file under its hashed name, keeps exactly one data file; `file_sha256` |
| `viz/publish/validate.py` | `data.file` checks; id-from-path fix (A17); deep JSON (A1) |
| `viz/publish/publish.py` | data PUT, conditional commit, one-generation clean-up; conditional dashboards |
| `viz/server/routes.py` | `/api/data/{id}` streams `data.file`; `/api/health` answers GET and HEAD |
| `viz/server/documents.py`, `viz/server/tree.py`, `viz/schemas.py` | nesting cap, per-document isolation (A1); no dashboard conflict rule (A18) |
| `viz/server/middleware.py`, `viz/server/app.py`, `viz/config.py`, `viz/publish/preview.py` | `TrustedHostExceptHealth` (A29), identity gate (B1), `allowed_hosts` default (A3) |
| `viz/server/__main__.py` | `log_config()` so `viz.access` lines are written (A2) |
| `sample-bucket/generate.py`, `sample-bucket/viz/**` | regenerated with hashed data files |
| `tests/fixtures/valid/*.json` | `data.file`; Vega-Lite v6 (A37) |
| `web/src/api/types.ts` + three web test files | `ChartData.file` |
| `docs/work-setup.md` | two settings rows only |
| `docs/superpowers/specs/2026-09-22-viz-site-design.md` | spec text for everything above, and B3 in 12.7 |
| `tests/...` | new: `tests/storage/test_conditional_put.py`, `tests/server/test_tree_isolation.py`, `tests/server/test_identity_gate.py`, `tests/server/test_logging.py`, `tests/test_forbidden_keys.py`, `tests/test_spec_text.py`; many existing tests updated |

---

### Task 1: Conditional puts in the storage layer

**Files:**
- Modify: `viz/storage/base.py`, `viz/storage/__init__.py`, `viz/storage/local.py`, `viz/storage/s3.py`, `pyproject.toml`
- Test: Create `tests/storage/test_conditional_put.py`

**Interfaces:**
- Consumes: `viz.storage.base.NotFound`, `ObjectInfo`; `viz.storage.local.LocalStorage(root)`; `viz.storage.s3.S3Storage(bucket, client=None)`.
- Produces:
  - `viz.storage.PreconditionFailed(Exception)` (defined in `viz.storage.base`, re-exported by `viz.storage`).
  - `put(key: str, data: bytes, content_type: str, *, if_match: str | None = None, if_none_match: bool = False) -> None` on both backends. `if_none_match=True`: write only if the key does not exist. `if_match=<etag>`: write only if the key exists with that ETag (unquoted, as `head().etag` returns it). A failed condition raises `PreconditionFailed`; passing both raises `ValueError`.
  - `head(key).etag` / `list(prefix)[i].etag` on `LocalStorage`: hex MD5 of the file bytes (was size-mtime).

- [ ] **Step 1: Write the failing tests**

Create `tests/storage/test_conditional_put.py`:

```python
"""Conditional puts: the commit point of an atomic publish (hardening decision B2)."""
import hashlib
import threading

import boto3
import botocore.session
import pytest
from botocore.exceptions import ClientError
from moto import mock_aws

from viz.storage import PreconditionFailed
from viz.storage.base import NotFound
from viz.storage.local import LocalStorage
from viz.storage.s3 import S3Storage


@pytest.fixture(params=["local", "s3"])
def storage(request, tmp_path, monkeypatch):
    if request.param == "local":
        (tmp_path / "bucket").mkdir()
        yield LocalStorage(tmp_path / "bucket")
        return
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-east-1")
    with mock_aws():
        client = boto3.client("s3", region_name="us-east-1")
        client.create_bucket(Bucket="test-bucket")
        yield S3Storage("test-bucket", client=client)


def test_etag_is_the_md5_of_the_bytes(storage):
    storage.put("k", b"hello", "text/plain")
    expected = hashlib.md5(b"hello").hexdigest()
    assert storage.head("k").etag == expected
    assert [info.etag for info in storage.list("k")] == [expected]


def test_if_none_match_writes_only_a_new_key(storage):
    storage.put("k", b"one", "text/plain", if_none_match=True)
    with pytest.raises(PreconditionFailed):
        storage.put("k", b"two", "text/plain", if_none_match=True)
    assert storage.get("k") == b"one"


def test_if_match_needs_the_current_etag(storage):
    storage.put("k", b"one", "text/plain")
    first = storage.head("k").etag
    storage.put("k", b"two", "text/plain", if_match=first)
    assert storage.get("k") == b"two"
    with pytest.raises(PreconditionFailed):
        storage.put("k", b"three", "text/plain", if_match=first)  # stale ETag
    assert storage.get("k") == b"two"


def test_if_match_on_a_missing_key_is_precondition_failed(storage):
    with pytest.raises(PreconditionFailed):
        storage.put("gone", b"x", "text/plain", if_match=hashlib.md5(b"x").hexdigest())
    with pytest.raises(NotFound):
        storage.get("gone")


def test_both_conditions_at_once_is_a_programming_error(storage):
    with pytest.raises(ValueError):
        storage.put("k", b"x", "text/plain", if_match="abc", if_none_match=True)


def test_local_conditional_put_is_atomic_across_threads(tmp_path):
    storage = LocalStorage(tmp_path)
    results = []

    def attempt(i: int) -> None:
        try:
            storage.put("k", str(i).encode(), "text/plain", if_none_match=True)
            results.append("written")
        except PreconditionFailed:
            results.append("refused")

    threads = [threading.Thread(target=attempt, args=(i,)) for i in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert results.count("written") == 1
    assert results.count("refused") == 7


class _RecordingClient:
    def __init__(self):
        self.calls = []

    def put_object(self, **kwargs):
        self.calls.append(kwargs)
        return {}


def test_s3_sends_the_conditions_to_put_object():
    client = _RecordingClient()
    storage = S3Storage("b", client=client)
    storage.put("k", b"x", "text/plain", if_none_match=True)
    storage.put("k", b"x", "text/plain", if_match="abc123")
    storage.put("k", b"x", "text/plain")
    assert client.calls[0]["IfNoneMatch"] == "*" and "IfMatch" not in client.calls[0]
    assert client.calls[1]["IfMatch"] == '"abc123"' and "IfNoneMatch" not in client.calls[1]
    assert "IfMatch" not in client.calls[2] and "IfNoneMatch" not in client.calls[2]


class _FailingClient:
    def __init__(self, code: str, status: int):
        self.code = code
        self.status = status

    def put_object(self, **kwargs):
        raise ClientError({"Error": {"Code": self.code, "Message": "x"},
                           "ResponseMetadata": {"HTTPStatusCode": self.status}}, "PutObject")


@pytest.mark.parametrize("code,status", [("PreconditionFailed", 412), ("ConditionalRequestConflict", 409)])
def test_s3_maps_conditional_failures(code, status):
    storage = S3Storage("b", client=_FailingClient(code, status))
    with pytest.raises(PreconditionFailed):
        storage.put("k", b"x", "text/plain", if_none_match=True)


def test_s3_other_errors_are_not_precondition_failures():
    storage = S3Storage("b", client=_FailingClient("AccessDenied", 403))
    with pytest.raises(ClientError):
        storage.put("k", b"x", "text/plain", if_none_match=True)


def test_installed_botocore_knows_the_conditional_put_parameters():
    # boto3>=1.35.69 (botocore 1.35.69) is the first release with IfMatch on PutObject.
    shape = botocore.session.get_session().get_service_model("s3").operation_model("PutObject").input_shape
    assert "IfMatch" in shape.members
    assert "IfNoneMatch" in shape.members
```

- [ ] **Step 2: Run them to see them fail**

Run: `.venv/Scripts/python -m pytest tests/storage/test_conditional_put.py -v`
Expected: a collection ERROR, `ImportError: cannot import name 'PreconditionFailed' from 'viz.storage'`.

- [ ] **Step 3: Replace the whole of `viz/storage/base.py`**

```python
"""The storage protocol every backend implements."""
from dataclasses import dataclass
from datetime import datetime
from typing import Iterator, Protocol


@dataclass(frozen=True)
class ObjectInfo:
    key: str
    size: int
    etag: str
    last_modified: datetime | None


class NotFound(KeyError):
    pass


class PreconditionFailed(Exception):
    """A conditional put was refused: the key exists (if_none_match) or its ETag
    changed or it disappeared (if_match)."""


class Storage(Protocol):
    def list(self, prefix: str) -> list[ObjectInfo]:
        """All objects whose key starts with prefix, sorted by key."""

    def head(self, key: str) -> ObjectInfo:
        """Size and ETag of one object. Raises NotFound. The ETag is unquoted."""

    def get(self, key: str) -> bytes: ...

    def open(self, key: str, start: int = 0, end: int | None = None) -> Iterator[bytes]:
        """Stream bytes from start to end inclusive. end=None means to the end."""

    def put(self, key: str, data: bytes, content_type: str, *, if_match: str | None = None,
            if_none_match: bool = False) -> None:
        """Write one object. if_none_match=True: only if the key does not exist.
        if_match=<etag>: only if the key exists with that ETag (unquoted, as head() returns it).
        A failed condition raises PreconditionFailed. Passing both raises ValueError."""

    def delete(self, key: str) -> None:
        """Delete if present. Missing keys are not an error."""

    def copy(self, src: str, dst: str) -> None: ...
```

- [ ] **Step 4: Replace the whole of `viz/storage/__init__.py`**

```python
"""Pick a storage backend from settings."""
from ..config import Settings
from .base import NotFound, ObjectInfo, PreconditionFailed, Storage
from .local import LocalStorage
from .s3 import S3Storage

__all__ = ["NotFound", "ObjectInfo", "PreconditionFailed", "Storage", "get_storage"]


def get_storage(settings: Settings) -> Storage:
    if settings.storage == "local":
        return LocalStorage(settings.local_dir)
    if not settings.s3_bucket:
        raise ValueError("VIZ_S3_BUCKET is required when VIZ_STORAGE=s3")
    return S3Storage(settings.s3_bucket)
```

- [ ] **Step 5: Replace the whole of `viz/storage/local.py`**

```python
"""Filesystem backend. The root directory is the bucket."""
import hashlib
import logging
import os
import shutil
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

from .base import NotFound, ObjectInfo, PreconditionFailed

CHUNK = 1024 * 1024
_log = logging.getLogger("viz.storage")

# One lock for every LocalStorage in this process: a conditional put checks the
# current ETag and writes under it, so two threads cannot both pass the check.
# It does not protect against a second process; the local backend is for development.
_PUT_LOCK = threading.Lock()


def _md5_hex(path: Path) -> str:
    digest = hashlib.md5()
    with path.open("rb") as f:
        while True:
            chunk = f.read(CHUNK)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


class LocalStorage:
    def __init__(self, root: Path):
        self.root = Path(root)
        self._resolved_root = self.root.resolve()
        if not self.root.exists():
            _log.warning("local storage root does not exist: %s", self.root)

    def _path(self, key: str) -> Path:
        if key.startswith("/") or ".." in key.split("/"):
            raise NotFound(key)
        path = (self.root / key)
        # Refuse anything that resolves outside the root, including symlinks that escape.
        resolved = path.resolve()
        if resolved != self._resolved_root and self._resolved_root not in resolved.parents:
            raise NotFound(key)
        return path

    def _info(self, key: str, path: Path) -> ObjectInfo:
        st = path.stat()
        return ObjectInfo(
            key=key,
            size=st.st_size,
            etag=_md5_hex(path),
            last_modified=datetime.fromtimestamp(st.st_mtime, tz=timezone.utc),
        )

    def list(self, prefix: str) -> list[ObjectInfo]:
        out = []
        for dirpath, _dirnames, filenames in os.walk(self.root):
            for name in filenames:
                path = Path(dirpath) / name
                key = path.relative_to(self.root).as_posix()
                if not key.startswith(prefix):
                    continue
                try:
                    self._path(key)
                except NotFound:
                    continue
                try:
                    out.append(self._info(key, path))
                except FileNotFoundError:
                    continue
        return sorted(out, key=lambda o: o.key)

    def head(self, key: str) -> ObjectInfo:
        path = self._path(key)
        if not path.is_file():
            raise NotFound(key)
        return self._info(key, path)

    def get(self, key: str) -> bytes:
        path = self._path(key)
        if not path.is_file():
            raise NotFound(key)
        return path.read_bytes()

    def open(self, key: str, start: int = 0, end: int | None = None) -> Iterator[bytes]:
        path = self._path(key)
        if not path.is_file():
            raise NotFound(key)
        size = path.stat().st_size
        stop = size - 1 if end is None else min(end, size - 1)
        remaining = stop - start + 1
        with path.open("rb") as f:
            f.seek(start)
            while remaining > 0:
                chunk = f.read(min(CHUNK, remaining))
                if not chunk:
                    break
                remaining -= len(chunk)
                yield chunk

    def put(self, key: str, data: bytes, content_type: str, *, if_match: str | None = None,
            if_none_match: bool = False) -> None:
        if if_match is not None and if_none_match:
            raise ValueError("pass if_match or if_none_match, not both")
        path = self._path(key)
        with _PUT_LOCK:
            if if_none_match and path.is_file():
                raise PreconditionFailed(key)
            if if_match is not None and (not path.is_file() or _md5_hex(path) != if_match):
                raise PreconditionFailed(key)
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_name(path.name + ".tmp")
            tmp.write_bytes(data)
            os.replace(tmp, path)

    def delete(self, key: str) -> None:
        path = self._path(key)
        if path.is_file():
            path.unlink()

    def copy(self, src: str, dst: str) -> None:
        src_path = self._path(src)
        if not src_path.is_file():
            raise NotFound(src)
        dst_path = self._path(dst)
        dst_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src_path, dst_path)
```

- [ ] **Step 6: Replace the whole of `viz/storage/s3.py`**

```python
"""S3 backend via boto3. Credentials come from the environment or the pod role."""
from typing import Iterator

import boto3
from botocore.exceptions import ClientError

from .base import NotFound, ObjectInfo, PreconditionFailed

CHUNK = 1024 * 1024


def _is_missing(err: ClientError) -> bool:
    return err.response.get("Error", {}).get("Code") in ("404", "NoSuchKey", "NotFound")


def _is_precondition_failure(err: ClientError) -> bool:
    """412 PreconditionFailed: the condition was false. 409 ConditionalRequestConflict:
    another conditional write to the same key won the race."""
    code = err.response.get("Error", {}).get("Code")
    status = err.response.get("ResponseMetadata", {}).get("HTTPStatusCode")
    return code in ("PreconditionFailed", "ConditionalRequestConflict") or status == 412


class S3Storage:
    def __init__(self, bucket: str, client=None):
        self.bucket = bucket
        self.client = client or boto3.client("s3")

    def list(self, prefix: str) -> list[ObjectInfo]:
        out = []
        paginator = self.client.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=self.bucket, Prefix=prefix):
            for obj in page.get("Contents", []):
                out.append(ObjectInfo(
                    key=obj["Key"],
                    size=obj["Size"],
                    etag=obj["ETag"].strip('"'),
                    last_modified=obj.get("LastModified"),
                ))
        return sorted(out, key=lambda o: o.key)

    def head(self, key: str) -> ObjectInfo:
        try:
            resp = self.client.head_object(Bucket=self.bucket, Key=key)
        except ClientError as err:
            if _is_missing(err):
                raise NotFound(key) from err
            raise
        return ObjectInfo(key=key, size=resp["ContentLength"], etag=resp["ETag"].strip('"'),
                          last_modified=resp.get("LastModified"))

    def get(self, key: str) -> bytes:
        try:
            resp = self.client.get_object(Bucket=self.bucket, Key=key)
        except ClientError as err:
            if _is_missing(err):
                raise NotFound(key) from err
            raise
        return resp["Body"].read()

    def open(self, key: str, start: int = 0, end: int | None = None) -> Iterator[bytes]:
        range_header = f"bytes={start}-" if end is None else f"bytes={start}-{end}"
        try:
            resp = self.client.get_object(Bucket=self.bucket, Key=key, Range=range_header)
        except ClientError as err:
            if _is_missing(err):
                raise NotFound(key) from err
            raise
        yield from resp["Body"].iter_chunks(CHUNK)

    def put(self, key: str, data: bytes, content_type: str, *, if_match: str | None = None,
            if_none_match: bool = False) -> None:
        if if_match is not None and if_none_match:
            raise ValueError("pass if_match or if_none_match, not both")
        kwargs = {"Bucket": self.bucket, "Key": key, "Body": data, "ContentType": content_type}
        if if_none_match:
            kwargs["IfNoneMatch"] = "*"
        if if_match is not None:
            kwargs["IfMatch"] = f'"{if_match}"'
        try:
            self.client.put_object(**kwargs)
        except ClientError as err:
            if _is_precondition_failure(err):
                raise PreconditionFailed(key) from err
            if if_match is not None and _is_missing(err):
                raise PreconditionFailed(key) from err  # deleted since the caller read its ETag
            raise

    def delete(self, key: str) -> None:
        self.client.delete_object(Bucket=self.bucket, Key=key)

    def copy(self, src: str, dst: str) -> None:
        try:
            self.client.copy_object(Bucket=self.bucket, Key=dst, CopySource={"Bucket": self.bucket, "Key": src})
        except ClientError as err:
            if _is_missing(err):
                raise NotFound(src) from err
            raise
```

- [ ] **Step 7: Raise the boto3 floor in `pyproject.toml`**

Replace:

```
  "boto3>=1.35",
```

with:

```
  "boto3>=1.35.69",
```

Nothing needs reinstalling: the venv already has a newer boto3.

- [ ] **Step 8: Run the tests to see them pass**

Run: `.venv/Scripts/python -m pytest tests/storage -v`
Expected: every test passes (the new file has 16 tests); the symlink test and the opt-in S3 integration test are skipped.

- [ ] **Step 9: Run the whole suite, then commit**

Run: `.venv/Scripts/python -m pytest`
Expected: all pass.

```bash
git add viz/storage/base.py viz/storage/__init__.py viz/storage/local.py viz/storage/s3.py pyproject.toml tests/storage/test_conditional_put.py
git -c user.name="tripp" -c user.email="dom4domg@gmail.com" commit -m "feat: conditional puts and PreconditionFailed in both storage backends" -m "Raises the boto3 floor to 1.35.69, the first release whose PutObject accepts IfMatch. No new dependency.

Co-Authored-By: <model name from your harness> <noreply@anthropic.com>
Claude-Session: <session url from your harness>"
```

Check with `git log -1 --format=%B`: subject on line 1, empty line 2, the body, an empty line, then the two trailers as the last two lines, adjacent.

---

### Task 2: Content-addressed data files through the whole contract

This task changes the contract, so it changes many tests at once. Do the steps in order; the suite is only green again at Step 12.

**Files:**
- Modify: `viz/ids.py`, `schemas/chart.schema.json`, `viz/publish/staging.py`, `viz/publish/validate.py`, `viz/publish/publish.py`, `viz/server/routes.py`, `sample-bucket/generate.py`, `tests/fixtures/valid/chart-large.json`, `tests/fixtures/valid/chart-stat.json`, `tests/fixtures/valid/chart-vegalite.json`
- Regenerate: `sample-bucket/viz/**` (by running the generator; never by hand)
- Test: Modify `tests/test_ids.py`, `tests/test_schemas.py`, `tests/test_sample_bucket.py`, `tests/publish/test_staging.py`, `tests/publish/test_validate.py`, `tests/publish/test_publish.py`, `tests/publish/test_move.py`, `tests/publish/test_end_to_end.py`, `tests/publish/test_cli_stage.py`, `tests/publish/test_cli_errors.py`, `tests/server/test_data_route.py`

**Interfaces:**
- Consumes: Task 1's `put` (unconditional calls only in this task).
- Produces:
  - `viz.ids.DATA_FILE_PATTERN` = `re.compile(r"^data\.[0-9a-f]{16}\.(json|parquet)$")`.
  - `viz.ids.data_file_name(sha256_hex: str, fmt: str) -> str` returns `data.<sha256_hex[:16]>.<fmt>`; `ValueError` on an unknown format or a string that is not 64 lowercase hex characters.
  - `viz.ids.data_key(root: str, chart_id: str, file_name: str) -> str` returns `<root>charts/<chart_id>/<file_name>`; `ValueError` unless `file_name` matches `DATA_FILE_PATTERN`. (It used to take the format.)
  - chart.json `data.file`: required, pattern `^data[.][0-9a-f]{16}[.](json|parquet)$`, extension equal to `data.format`.
  - `viz.publish.staging.file_sha256(path) -> str`, `PARQUET_TMP_NAME = "parquet.tmp"`, `HASH_CHUNK = 1048576`; `skeleton(chart_id, columns, fmt, file_name, lane, rows, nbytes, author, now, source=None)`; `write_staged_chart(...)` (signature unchanged) leaves exactly one `data.*` file in the chart directory, named by `doc["data"]["file"]`; `StagedChart.data_path` points at it.
  - `validate_staged_chart` new error lines: `"<file>: not found"`, `"data.file: '<file>' does not match the file's SHA-256; it should be named '<expected>'"`, `"data: the staged directory holds other data files (<names>); keep only '<file>'"`.
  - `publish_chart` puts the data file at `data_key(root, id, data.file)`, then chart.json, then deletes every other `data.*` object of that chart (Task 3 replaces this with the conditional version).
  - `/api/data/{id}` streams `data_key(root, id, doc["data"]["file"])`. `Content-Disposition` stays `attachment; filename="data.<format>"`.

- [ ] **Step 1: Update `tests/test_ids.py`**

Replace:

```python
import pytest
from viz import ids
```

with:

```python
import hashlib

import pytest
from viz import ids
```

Replace:

```python
    assert ids.data_key("viz/", "sales/emea/rev", "json") == "viz/charts/sales/emea/rev/data.json"
    assert ids.data_key("viz/", "sales/emea/rev", "parquet") == "viz/charts/sales/emea/rev/data.parquet"
    assert ids.dashboard_key("viz/", "sales/overview") == "viz/dashboards/sales/overview.json"
    assert ids.folder_key("viz/", "charts", "sales") == "viz/charts/sales/_folder.json"
    assert ids.folder_key("viz/", "dashboards", "") == "viz/dashboards/_folder.json"


def test_data_key_rejects_unknown_format():
    with pytest.raises(ValueError):
        ids.data_key("viz/", "a", "csv")
```

with:

```python
    assert ids.data_key("viz/", "sales/emea/rev", "data.0123456789abcdef.json") == "viz/charts/sales/emea/rev/data.0123456789abcdef.json"
    assert ids.data_key("viz/", "sales/emea/rev", "data.0123456789abcdef.parquet") == "viz/charts/sales/emea/rev/data.0123456789abcdef.parquet"
    assert ids.dashboard_key("viz/", "sales/overview") == "viz/dashboards/sales/overview.json"
    assert ids.folder_key("viz/", "charts", "sales") == "viz/charts/sales/_folder.json"
    assert ids.folder_key("viz/", "dashboards", "") == "viz/dashboards/_folder.json"


@pytest.mark.parametrize("name", [
    "json", "data.json", "data.parquet", "data.0123456789ABCDEF.json", "data.0123456789abcdef.csv",
    "data.0123456789abcde.json", "../data.0123456789abcdef.json", "chart.json", "data.0123456789abcdef.json\n",
])
def test_data_key_rejects_names_that_are_not_content_addressed(name):
    with pytest.raises(ValueError):
        ids.data_key("viz/", "a", name)


def test_data_file_name_is_the_first_16_hex_of_the_sha256():
    digest = hashlib.sha256(b"[]").hexdigest()
    assert ids.data_file_name(digest, "json") == f"data.{digest[:16]}.json"
    assert ids.data_file_name(digest, "parquet") == f"data.{digest[:16]}.parquet"
    with pytest.raises(ValueError):
        ids.data_file_name(digest, "csv")
    with pytest.raises(ValueError):
        ids.data_file_name("abc", "json")
```

- [ ] **Step 2: Update the valid fixtures and `tests/test_schemas.py`**

In `tests/fixtures/valid/chart-vegalite.json` replace:

```
    "format": "json",
```

with:

```
    "format": "json",
    "file": "data.0123456789abcdef.json",
```

In `tests/fixtures/valid/chart-stat.json` replace (the line with four spaces of indent, inside `"data"`):

```
    "format": "json",
```

with:

```
    "format": "json",
    "file": "data.fedcba9876543210.json",
```

In `tests/fixtures/valid/chart-large.json` replace:

```
    "format": "parquet",
```

with:

```
    "format": "parquet",
    "file": "data.00112233445566aa.parquet",
```

In `tests/test_schemas.py` replace:

```python
    ("small lane too many bytes", "chart-vegalite.json", _set("data.bytes", 20971521), "bytes"),
```

with:

```python
    ("small lane too many bytes", "chart-vegalite.json", _set("data.bytes", 20971521), "bytes"),
    ("data file missing", "chart-vegalite.json", _delete("data.file"), "file"),
    ("data file not content-addressed", "chart-vegalite.json", _set("data.file", "data.json"), "file"),
    ("data file uppercase hex", "chart-vegalite.json", _set("data.file", "data.0123456789ABCDEF.json"), "file"),
    ("data file path traversal", "chart-vegalite.json", _set("data.file", "../data.0123456789abcdef.json"), "file"),
    ("json data in a parquet file name", "chart-vegalite.json", _set("data.file", "data.0123456789abcdef.parquet"), "file"),
    ("parquet data in a json file name", "chart-large.json", _set("data.file", "data.00112233445566aa.json"), "file"),
```

- [ ] **Step 3: Update `tests/test_sample_bucket.py`**

Replace:

```python
import json
from pathlib import Path

from viz import schemas
```

with:

```python
import hashlib
import json
from pathlib import Path

from viz import schemas
from viz.ids import data_file_name
```

Replace:

```python
        data_path = path.parent / f"data.{doc['data']['format']}"
        assert data_path.is_file()
```

with:

```python
        data_path = path.parent / doc["data"]["file"]
        assert data_path.is_file()
```

Replace:

```python
def test_parquet_sample_is_under_the_large_lane_cap():
    for renderer in RENDERERS:
        path = ROOT / "charts" / "bakeoff" / renderer / "order-lines" / "data.parquet"
        assert path.stat().st_size < 209715200
```

with:

```python
def test_parquet_sample_is_under_the_large_lane_cap():
    for renderer in RENDERERS:
        chart_dir = ROOT / "charts" / "bakeoff" / renderer / "order-lines"
        doc = json.loads((chart_dir / "chart.json").read_text(encoding="utf-8"))
        assert (chart_dir / doc["data"]["file"]).stat().st_size < 209715200


def test_every_chart_directory_holds_exactly_its_content_addressed_data_file():
    for path in _docs("charts", "chart.json"):
        doc = json.loads(path.read_text(encoding="utf-8"))
        name = doc["data"]["file"]
        digest = hashlib.sha256((path.parent / name).read_bytes()).hexdigest()
        assert name == data_file_name(digest, doc["data"]["format"]), path
        assert sorted(p.name for p in path.parent.glob("data.*")) == [name], path
```

- [ ] **Step 4: Update `tests/publish/test_staging.py`**

Replace:

```python
import json
from datetime import date, datetime, timezone

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from viz import schemas
from viz.publish import staging
```

with:

```python
import hashlib
import json
from datetime import date, datetime, timezone

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from viz import schemas
from viz.ids import data_file_name
from viz.publish import staging
```

Replace:

```python
def test_write_small_lane(tmp_path):
    staged = write_staged_chart(_table(), "sales/test-chart", tmp_path, author="tester@example.com", now=NOW)
    assert isinstance(staged, StagedChart)
    assert staged.dir == tmp_path / "charts" / "sales" / "test-chart"
    assert staged.data_path.name == "data.json"
    assert staged.chart_path.name == "chart.json"
```

with:

```python
def _data_files(directory):
    return sorted(p.name for p in directory.glob("data.*"))


def _content_name(path, fmt):
    return data_file_name(hashlib.sha256(path.read_bytes()).hexdigest(), fmt)


def test_write_small_lane(tmp_path):
    staged = write_staged_chart(_table(), "sales/test-chart", tmp_path, author="tester@example.com", now=NOW)
    assert isinstance(staged, StagedChart)
    assert staged.dir == tmp_path / "charts" / "sales" / "test-chart"
    assert staged.data_path.name == _content_name(staged.data_path, "json")
    assert _data_files(staged.dir) == [staged.data_path.name]
    assert staged.chart_path.name == "chart.json"
```

Replace:

```python
        "format": "json", "lane": "small", "rows": 3, "bytes": staged.data_path.stat().st_size,
```

with:

```python
        "format": "json", "file": staged.data_path.name, "lane": "small", "rows": 3,
        "bytes": staged.data_path.stat().st_size,
```

Replace:

```python
    staged = write_staged_chart(_table(3), "sales/big", tmp_path, author="a@b", now=NOW)
    assert staged.data_path.name == "data.parquet"
    assert staged.doc["data"]["format"] == "parquet"
```

with:

```python
    staged = write_staged_chart(_table(3), "sales/big", tmp_path, author="a@b", now=NOW)
    assert staged.data_path.name == _content_name(staged.data_path, "parquet")
    assert staged.doc["data"]["file"] == staged.data_path.name
    assert _data_files(staged.dir) == [staged.data_path.name]
    assert not (staged.dir / staging.PARQUET_TMP_NAME).exists()
    assert staged.doc["data"]["format"] == "parquet"
```

Replace:

```python
    staged = write_staged_chart(_table(), "sales/big-bytes", tmp_path, author="a@b", now=NOW)
    assert staged.data_path.name == "data.parquet"


def test_parquet_over_cap_is_refused_and_cleaned_up(tmp_path, monkeypatch):
    monkeypatch.setattr(staging, "SMALL_MAX_ROWS", 0)
    monkeypatch.setattr(staging, "LARGE_MAX_BYTES", 10)
    with pytest.raises(LaneError, match="209715200|10 bytes"):
        write_staged_chart(_table(), "sales/too-big", tmp_path, author="a@b", now=NOW)
    assert not (tmp_path / "charts" / "sales" / "too-big" / "data.parquet").exists()
    assert not (tmp_path / "charts" / "sales" / "too-big" / "chart.json").exists()


def test_restaging_removes_the_other_format(tmp_path, monkeypatch):
    monkeypatch.setattr(staging, "SMALL_MAX_ROWS", 0)
    write_staged_chart(_table(), "sales/again", tmp_path, author="a@b", now=NOW)
    monkeypatch.setattr(staging, "SMALL_MAX_ROWS", 100)
    staged = write_staged_chart(_table(), "sales/again", tmp_path, author="a@b", now=NOW)
    assert staged.data_path.name == "data.json"
    assert not (staged.dir / "data.parquet").exists()
```

with:

```python
    staged = write_staged_chart(_table(), "sales/big-bytes", tmp_path, author="a@b", now=NOW)
    assert staged.data_path.name.endswith(".parquet")


def test_parquet_over_cap_is_refused_and_cleaned_up(tmp_path, monkeypatch):
    monkeypatch.setattr(staging, "SMALL_MAX_ROWS", 0)
    monkeypatch.setattr(staging, "LARGE_MAX_BYTES", 10)
    with pytest.raises(LaneError, match="209715200|10 bytes"):
        write_staged_chart(_table(), "sales/too-big", tmp_path, author="a@b", now=NOW)
    directory = tmp_path / "charts" / "sales" / "too-big"
    assert _data_files(directory) == []
    assert not (directory / staging.PARQUET_TMP_NAME).exists()
    assert not (directory / "chart.json").exists()


def test_restaging_removes_the_other_format(tmp_path, monkeypatch):
    monkeypatch.setattr(staging, "SMALL_MAX_ROWS", 0)
    write_staged_chart(_table(), "sales/again", tmp_path, author="a@b", now=NOW)
    monkeypatch.setattr(staging, "SMALL_MAX_ROWS", 100)
    staged = write_staged_chart(_table(), "sales/again", tmp_path, author="a@b", now=NOW)
    assert staged.data_path.name.endswith(".json")
    assert _data_files(staged.dir) == [staged.data_path.name]


def test_restaging_other_rows_replaces_the_data_file(tmp_path):
    first = write_staged_chart(_table(2), "sales/again", tmp_path, author="a@b", now=NOW)
    second = write_staged_chart(_table(3), "sales/again", tmp_path, author="a@b", now=NOW)
    assert first.data_path.name != second.data_path.name
    assert _data_files(second.dir) == [second.data_path.name]
    assert json.loads(second.chart_path.read_text(encoding="utf-8"))["data"]["file"] == second.data_path.name


def test_file_sha256_matches_hashlib(tmp_path):
    path = tmp_path / "blob"
    path.write_bytes(b"x" * (staging.HASH_CHUNK + 7))
    assert staging.file_sha256(path) == hashlib.sha256(b"x" * (staging.HASH_CHUNK + 7)).hexdigest()
```

Replace:

```python
    staged = write_staged_chart(_table(), "sales/restage", tmp_path, author="tester@example.com", now=NOW)
    assert staged.data_path.name == "data.json" and staged.chart_path.is_file()
    monkeypatch.setattr(staging, "SMALL_MAX_ROWS", 0)
    monkeypatch.setattr(staging, "LARGE_MAX_BYTES", 10)
    with pytest.raises(LaneError):
        write_staged_chart(_table(), "sales/restage", tmp_path, author="tester@example.com", now=NOW)
    assert not (staged.dir / "chart.json").exists()
    assert not (staged.dir / "data.parquet").exists()
```

with:

```python
    staged = write_staged_chart(_table(), "sales/restage", tmp_path, author="tester@example.com", now=NOW)
    assert staged.data_path.name.endswith(".json") and staged.chart_path.is_file()
    monkeypatch.setattr(staging, "SMALL_MAX_ROWS", 0)
    monkeypatch.setattr(staging, "LARGE_MAX_BYTES", 10)
    with pytest.raises(LaneError):
        write_staged_chart(_table(), "sales/restage", tmp_path, author="tester@example.com", now=NOW)
    assert not (staged.dir / "chart.json").exists()
    assert not list(staged.dir.glob("data.*.parquet"))
    assert not (staged.dir / staging.PARQUET_TMP_NAME).exists()
```

- [ ] **Step 5: Update `tests/publish/test_validate.py`**

Replace:

```python
import json
from datetime import date, datetime, timezone

import pyarrow as pa
import pytest

from viz.publish import staging
```

with:

```python
import hashlib
import json
from datetime import date, datetime, timezone

import pyarrow as pa
import pytest

from viz.ids import data_file_name
from viz.publish import staging
```

Replace:

```python
    staged.data_path.unlink()
    assert validate_staged_chart(staged.dir, settings, storage) == ["data.json: not found"]


def test_integer_file_column_satisfies_declared_number(settings, storage, staging_root):
    staged = _staged(staging_root)
    rows = [{"month": "2024-01-01", "region": "EMEA", "revenue": 100}, {"month": "2024-02-01", "region": "NA", "revenue": 200}]
    payload = json.dumps(rows).encode("utf-8")
    staged.data_path.write_bytes(payload)
    doc = json.loads(json.dumps(staged.doc))
    doc["data"]["bytes"] = len(payload)
    _rewrite(staged, doc)
    assert validate_staged_chart(staged.dir, settings, storage) == []
```

with:

```python
    staged.data_path.unlink()
    assert validate_staged_chart(staged.dir, settings, storage) == [f"{staged.data_path.name}: not found"]


def _replace_data(staged, payload: bytes) -> dict:
    """Swap the staged data for new bytes under their content-addressed name; return the updated doc."""
    name = data_file_name(hashlib.sha256(payload).hexdigest(), "json")
    staged.data_path.unlink()
    (staged.dir / name).write_bytes(payload)
    doc = json.loads(json.dumps(staged.doc))
    doc["data"]["file"] = name
    doc["data"]["bytes"] = len(payload)
    _rewrite(staged, doc)
    return doc


def test_integer_file_column_satisfies_declared_number(settings, storage, staging_root):
    staged = _staged(staging_root)
    rows = [{"month": "2024-01-01", "region": "EMEA", "revenue": 100}, {"month": "2024-02-01", "region": "NA", "revenue": 200}]
    _replace_data(staged, json.dumps(rows).encode("utf-8"))
    assert validate_staged_chart(staged.dir, settings, storage) == []


def test_data_file_name_must_match_its_sha256(settings, storage, staging_root):
    staged = _staged(staging_root)
    wrong = "data.0000000000000000.json"
    staged.data_path.rename(staged.dir / wrong)
    doc = json.loads(json.dumps(staged.doc))
    doc["data"]["file"] = wrong
    _rewrite(staged, doc)
    errors = validate_staged_chart(staged.dir, settings, storage)
    assert errors == [
        f"data.file: '{wrong}' does not match the file's SHA-256; it should be named '{staged.data_path.name}'"
    ]


def test_edited_data_without_renaming_fails(settings, storage, staging_root):
    staged = _staged(staging_root)
    payload = staged.data_path.read_bytes().replace(b"100.5", b"999.5")
    staged.data_path.write_bytes(payload)
    errors = validate_staged_chart(staged.dir, settings, storage)
    assert any(e.startswith(f"data.file: '{staged.data_path.name}' does not match the file's SHA-256") for e in errors)


def test_other_data_files_in_the_staged_directory_fail(settings, storage, staging_root):
    staged = _staged(staging_root)
    (staged.dir / "data.json").write_text("[]", encoding="utf-8")
    (staged.dir / "data.0000000000000000.parquet").write_bytes(b"PAR1")
    errors = validate_staged_chart(staged.dir, settings, storage)
    assert errors == [
        "data: the staged directory holds other data files (data.0000000000000000.parquet, data.json); "
        f"keep only '{staged.data_path.name}'"
    ]
```

Replace:

```python
    staged = _staged(staging_root, chart_id="sales/large")
    assert staged.data_path.name == "data.parquet"
    assert validate_staged_chart
```

with:

```python
    staged = _staged(staging_root, chart_id="sales/large")
    assert staged.data_path.name.endswith(".parquet")
    assert validate_staged_chart
```

- [ ] **Step 6: Update the other publisher tests**

In `tests/publish/test_publish.py` replace:

```python
    assert publish_chart(staged.dir, settings, storage) == "sales/new-chart"
    assert storage.puts == ["viz/charts/sales/new-chart/data.json", "viz/charts/sales/new-chart/chart.json"]
    assert json.loads(storage.get("viz/charts/sales/new-chart/chart.json")) == staged.doc
    assert storage.get("viz/charts/sales/new-chart/data.json") == staged.data_path.read_bytes()
```

with:

```python
    assert publish_chart(staged.dir, settings, storage) == "sales/new-chart"
    data_key = f"viz/charts/sales/new-chart/{staged.doc['data']['file']}"
    assert storage.puts == [data_key, "viz/charts/sales/new-chart/chart.json"]
    assert json.loads(storage.get("viz/charts/sales/new-chart/chart.json")) == staged.doc
    assert storage.get(data_key) == staged.data_path.read_bytes()
```

and replace:

```python
def test_publish_removes_stale_data_of_the_other_format(settings, storage, staging_root, monkeypatch):
    monkeypatch.setattr(staging, "SMALL_MAX_ROWS", 0)
    big = _staged(staging_root)
    publish_chart(big.dir, settings, storage, allow_row_level=True)
    storage.head("viz/charts/sales/new-chart/data.parquet")
    monkeypatch.setattr(staging, "SMALL_MAX_ROWS", 100_000)
    small = _staged(staging_root)
    publish_chart(small.dir, settings, storage, force=True)
    storage.head("viz/charts/sales/new-chart/data.json")
    with pytest.raises(NotFound):
        storage.head("viz/charts/sales/new-chart/data.parquet")
```

with:

```python
def test_publish_removes_legacy_data_files(settings, storage, staging_root):
    storage.put("viz/charts/sales/new-chart/data.json", b"[]", "application/json")
    storage.put("viz/charts/sales/new-chart/data.parquet", b"PAR1", "application/octet-stream")
    staged = _staged(staging_root)
    publish_chart(staged.dir, settings, storage)
    storage.head(f"viz/charts/sales/new-chart/{staged.doc['data']['file']}")
    with pytest.raises(NotFound):
        storage.head("viz/charts/sales/new-chart/data.json")
    with pytest.raises(NotFound):
        storage.head("viz/charts/sales/new-chart/data.parquet")
```

In `tests/publish/test_move.py` replace:

```python
def test_plan_chart_move(settings, storage):
    plan = plan_move("sales/revenue-by-region", "sales/emea/revenue", settings, storage)
    assert isinstance(plan, MovePlan)
    assert plan.kind == "chart"
    assert plan.keys == [
        ("viz/charts/sales/revenue-by-region/data.json", "viz/charts/sales/emea/revenue/data.json"),
        ("viz/charts/sales/revenue-by-region/chart.json", "viz/charts/sales/emea/revenue/chart.json"),
    ]
```

with:

```python
def _data_file(storage, chart_id):
    return json.loads(storage.get(f"viz/charts/{chart_id}/chart.json"))["data"]["file"]


def test_plan_chart_move(settings, storage):
    name = _data_file(storage, "sales/revenue-by-region")
    plan = plan_move("sales/revenue-by-region", "sales/emea/revenue", settings, storage)
    assert isinstance(plan, MovePlan)
    assert plan.kind == "chart"
    assert plan.keys == [
        (f"viz/charts/sales/revenue-by-region/{name}", f"viz/charts/sales/emea/revenue/{name}"),
        ("viz/charts/sales/revenue-by-region/chart.json", "viz/charts/sales/emea/revenue/chart.json"),
    ]
```

and replace:

```python
    before = json.loads(storage.get("viz/dashboards/sales/overview.json"))
    plan = plan_move("sales/revenue-by-region", "sales/emea/revenue", settings, storage)
    apply_move(plan, settings, storage)

    doc = json.loads(storage.get("viz/charts/sales/emea/revenue/chart.json"))
    assert doc["id"] == "sales/emea/revenue"
    assert doc["updated_at"] != before["updated_at"]
    storage.head("viz/charts/sales/emea/revenue/data.json")
    with pytest.raises(NotFound):
        storage.head("viz/charts/sales/revenue-by-region/chart.json")
    with pytest.raises(NotFound):
        storage.head("viz/charts/sales/revenue-by-region/data.json")
```

with:

```python
    before = json.loads(storage.get("viz/dashboards/sales/overview.json"))
    name = _data_file(storage, "sales/revenue-by-region")
    plan = plan_move("sales/revenue-by-region", "sales/emea/revenue", settings, storage)
    apply_move(plan, settings, storage)

    doc = json.loads(storage.get("viz/charts/sales/emea/revenue/chart.json"))
    assert doc["id"] == "sales/emea/revenue"
    assert doc["updated_at"] != before["updated_at"]
    assert doc["data"]["file"] == name  # the data file keeps its content-addressed name
    storage.head(f"viz/charts/sales/emea/revenue/{name}")
    with pytest.raises(NotFound):
        storage.head("viz/charts/sales/revenue-by-region/chart.json")
    with pytest.raises(NotFound):
        storage.head(f"viz/charts/sales/revenue-by-region/{name}")
```

In `tests/publish/test_end_to_end.py` replace:

```python
    assert (chart_dir / "chart.json").is_file() and (chart_dir / "data.json").is_file()
```

with:

```python
    staged_doc = json.loads((chart_dir / "chart.json").read_text(encoding="utf-8"))
    assert (chart_dir / staged_doc["data"]["file"]).is_file()
```

In `tests/publish/test_cli_stage.py` replace:

```python
    assert (staging_root / "charts" / "sales" / "from-csv" / "data.json").is_file()
```

with:

```python
    assert (staging_root / "charts" / "sales" / "from-csv" / doc["data"]["file"]).is_file()
    assert doc["data"]["file"].endswith(".json")
```

In `tests/publish/test_cli_errors.py` replace:

```python
    assert staged.data_path.name == "data.parquet"
```

with:

```python
    assert staged.data_path.name.endswith(".parquet")
```

- [ ] **Step 7: Update `tests/server/test_data_route.py`**

Replace:

```python
import json

import pytest

from viz.storage import get_storage
```

with:

```python
import hashlib
import json

import pytest

from viz.ids import data_file_name
from viz.storage import get_storage
```

Replace:

```python
def test_parquet_media_type_and_missing_file(client, storage):
    doc = json.loads(storage.get("viz/charts/sales/total-revenue/chart.json"))
    doc.update({"id": "sales/big", "renderer": "vega-lite", "spec": {"data": {"name": "data"}, "mark": "bar"},
                "data": {**doc["data"], "format": "parquet", "lane": "large", "bytes": 4},
                "aggregate": "SELECT 1"})
    storage.put("viz/charts/sales/big/chart.json", json.dumps(doc).encode(), "application/json")
    assert client.get("/api/data/sales/big").status_code == 404   # chart exists, data file does not
    storage.put("viz/charts/sales/big/data.parquet", b"PAR1", "application/octet-stream")
```

with:

```python
def test_parquet_media_type_and_missing_file(client, storage):
    name = data_file_name(hashlib.sha256(b"PAR1").hexdigest(), "parquet")
    doc = json.loads(storage.get("viz/charts/sales/total-revenue/chart.json"))
    doc.update({"id": "sales/big", "renderer": "vega-lite", "spec": {"data": {"name": "data"}, "mark": "bar"},
                "data": {**doc["data"], "format": "parquet", "file": name, "lane": "large", "bytes": 4},
                "aggregate": "SELECT 1"})
    storage.put("viz/charts/sales/big/chart.json", json.dumps(doc).encode(), "application/json")
    assert client.get("/api/data/sales/big").status_code == 404   # chart exists, data file does not
    storage.put(f"viz/charts/sales/big/{name}", b"PAR1", "application/octet-stream")
```

Replace:

```python
    doc = json.loads(storage.get("viz/charts/sales/total-revenue/chart.json"))
    doc.update({"id": "sales/empty", "data": {**doc["data"], "rows": 0, "bytes": 0}})
    storage.put("viz/charts/sales/empty/chart.json", json.dumps(doc).encode(), "application/json")
    storage.put("viz/charts/sales/empty/data.json", b"", "application/json")
```

with:

```python
    name = data_file_name(hashlib.sha256(b"").hexdigest(), "json")
    doc = json.loads(storage.get("viz/charts/sales/total-revenue/chart.json"))
    doc.update({"id": "sales/empty", "data": {**doc["data"], "file": name, "rows": 0, "bytes": 0}})
    storage.put("viz/charts/sales/empty/chart.json", json.dumps(doc).encode(), "application/json")
    storage.put(f"viz/charts/sales/empty/{name}", b"", "application/json")
```

Then add these two tests at the end of the file:

```python


def test_data_route_serves_the_file_that_chart_json_names(client, storage):
    doc = json.loads(storage.get("viz/charts/sales/revenue-by-region/chart.json"))
    named = storage.get(f"viz/charts/sales/revenue-by-region/{doc['data']['file']}")
    # A stray legacy file and an older generation sit next to it; neither is served.
    storage.put("viz/charts/sales/revenue-by-region/data.json", b"[]", "application/json")
    storage.put("viz/charts/sales/revenue-by-region/data.0000000000000000.json", b"[1]", "application/json")
    r = client.get("/api/data/sales/revenue-by-region")
    assert r.status_code == 200
    assert r.content == named


def test_data_route_404_when_the_named_file_is_missing(client, storage):
    doc = json.loads(storage.get("viz/charts/sales/revenue-by-region/chart.json"))
    storage.delete(f"viz/charts/sales/revenue-by-region/{doc['data']['file']}")
    storage.put("viz/charts/sales/revenue-by-region/data.json", b"[]", "application/json")
    r = client.get("/api/data/sales/revenue-by-region")
    assert r.status_code == 404
    assert r.json() == {"detail": "data file not found"}
```

- [ ] **Step 8: Run the changed tests to see them fail**

Run: `.venv/Scripts/python -m pytest tests/test_ids.py tests/test_schemas.py tests/test_sample_bucket.py tests/publish tests/server/test_data_route.py -q`
Expected: many failures. Among them: `test_sample_bucket.py`, `test_staging.py`, `test_validate.py` and `test_data_route.py` fail to import (`ImportError: cannot import name 'data_file_name' from 'viz.ids'`); `test_ids.py` fails with `AttributeError ... data_file_name` and `ValueError: unknown data format: 'data.0123456789abcdef.json'`; `test_valid_charts_pass` fails with `Additional properties are not allowed ('file' was unexpected)`; move and publish tests fail with `KeyError: 'file'`.

- [ ] **Step 9: Change `viz/ids.py`**

Replace:

```python
DATA_FORMATS = ("json", "parquet")
KINDS = ("charts", "dashboards")
```

with:

```python
DATA_FORMATS = ("json", "parquet")
DATA_FILE_PATTERN = re.compile(r"^data\.[0-9a-f]{16}\.(json|parquet)$")
SHA256_HEX = re.compile(r"^[0-9a-f]{64}$")
KINDS = ("charts", "dashboards")
```

Replace:

```python
def data_key(root: str, chart_id: str, fmt: str) -> str:
    if fmt not in DATA_FORMATS:
        raise ValueError(f"unknown data format: {fmt!r}")
    return f"{root}charts/{chart_id}/data.{fmt}"
```

with:

```python
def data_file_name(sha256_hex: str, fmt: str) -> str:
    """The content-addressed name of a data file: data.<first 16 hex of its SHA-256>.<format>."""
    if fmt not in DATA_FORMATS:
        raise ValueError(f"unknown data format: {fmt!r}")
    if not isinstance(sha256_hex, str) or not SHA256_HEX.fullmatch(sha256_hex):
        raise ValueError(f"not a SHA-256 hex digest: {sha256_hex!r}")
    return f"data.{sha256_hex[:16]}.{fmt}"


def data_key(root: str, chart_id: str, file_name: str) -> str:
    """Bucket key of the data file that chart.json names in data.file."""
    if not isinstance(file_name, str) or not DATA_FILE_PATTERN.fullmatch(file_name):
        raise ValueError(f"invalid data file name: {file_name!r}")
    return f"{root}charts/{chart_id}/{file_name}"
```

- [ ] **Step 10: Change `schemas/chart.schema.json`**

The patterns use `[.]` instead of a backslash so nothing needs escaping in JSON.

Replace:

```
      "required": ["format", "lane", "rows", "bytes", "columns"],
      "properties": {
        "format": {"enum": ["json", "parquet"]},
```

with:

```
      "required": ["format", "file", "lane", "rows", "bytes", "columns"],
      "properties": {
        "format": {"enum": ["json", "parquet"]},
        "file": {"type": "string", "pattern": "^data[.][0-9a-f]{16}[.](json|parquet)$"},
```

Replace:

```
    {
      "if": {"properties": {"renderer": {"const": "stat"}}},
```

with:

```
    {
      "if": {"properties": {"data": {"properties": {"format": {"const": "json"}}}}},
      "then": {"properties": {"data": {"properties": {"file": {"pattern": "[.]json$"}}}}}
    },
    {
      "if": {"properties": {"data": {"properties": {"format": {"const": "parquet"}}}}},
      "then": {"properties": {"data": {"properties": {"file": {"pattern": "[.]parquet$"}}}}}
    },
    {
      "if": {"properties": {"renderer": {"const": "stat"}}},
```

- [ ] **Step 11a: Change `viz/publish/staging.py`**

Replace:

```python
"""The staging directory: a bucket with an empty root prefix, under ./.viz-staging by default.
A chart stages at charts/<id>/{chart.json,data.json|data.parquet}; a dashboard at dashboards/<id>.json."""
import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

from ..ids import validate_id
from .infer import infer_columns, rows_from_table
```

with:

```python
"""The staging directory: a bucket with an empty root prefix, under ./.viz-staging by default.
A chart stages at charts/<id>/chart.json plus exactly one data file named by chart.json's
data.file (data.<sha256-16>.json or .parquet); a dashboard at dashboards/<id>.json."""
import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

from ..ids import data_file_name, validate_id
from .infer import infer_columns, rows_from_table
```

Replace:

```python
LARGE_DEFAULT_AGGREGATE = "SELECT * FROM data LIMIT 1000"
```

with:

```python
LARGE_DEFAULT_AGGREGATE = "SELECT * FROM data LIMIT 1000"
PARQUET_TMP_NAME = "parquet.tmp"
HASH_CHUNK = 1024 * 1024
```

Replace everything from `def skeleton(` down to and including the line `    doc = skeleton(chart_id, columns, fmt, lane, len(table), data_path.stat().st_size, author, now, source)` — that is, this text:

```python
def skeleton(chart_id, columns, fmt, lane, rows, nbytes, author, now, source=None) -> dict:
    stamp = now.strftime(TIMESTAMP_FORMAT)
    doc = {
        "schema_version": 1,
        "id": chart_id,
        "title": title_from_id(chart_id),
        "author": author,
        "created_at": stamp,
        "updated_at": stamp,
        "renderer": "vega-lite",
        "spec": default_spec(columns),
        "data": {"format": fmt, "lane": lane, "rows": rows, "bytes": nbytes, "columns": columns},
        "aggregate": None if lane == "small" else LARGE_DEFAULT_AGGREGATE,
    }
    if source is not None:
        doc["source"] = source
    return doc


def _write_bytes(path: Path, payload: bytes) -> None:
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_bytes(payload)
    tmp.replace(path)


def write_staged_chart(table: pa.Table, chart_id: str, staging_root: Path, *, author: str, now: datetime,
                       source: dict | None = None) -> StagedChart:
    if table.num_columns == 0:
        raise LaneError("table has no columns")
    columns = infer_columns(table)
    directory = chart_dir(staging_root, chart_id)
    directory.mkdir(parents=True, exist_ok=True)

    payload = json.dumps(rows_from_table(table), ensure_ascii=False).encode("utf-8")
    if len(table) <= SMALL_MAX_ROWS and len(payload) <= SMALL_MAX_BYTES:
        fmt, lane = "json", "small"
        data_path = directory / "data.json"
        _write_bytes(data_path, payload)
        # Clean up old-format file after successful write
        (directory / "data.parquet").unlink(missing_ok=True)
    else:
        fmt, lane = "parquet", "large"
        data_path = directory / "data.parquet"
        pq.write_table(table, data_path)
        if data_path.stat().st_size > LARGE_MAX_BYTES:
            size = data_path.stat().st_size
            data_path.unlink()
            (directory / "chart.json").unlink(missing_ok=True)
            raise LaneError(f"parquet file is {size} bytes, over the large-lane cap of {LARGE_MAX_BYTES} bytes")
        # Clean up old-format file after successful write
        (directory / "data.json").unlink(missing_ok=True)

    doc = skeleton(chart_id, columns, fmt, lane, len(table), data_path.stat().st_size, author, now, source)
```

with:

```python
def skeleton(chart_id, columns, fmt, file_name, lane, rows, nbytes, author, now, source=None) -> dict:
    stamp = now.strftime(TIMESTAMP_FORMAT)
    doc = {
        "schema_version": 1,
        "id": chart_id,
        "title": title_from_id(chart_id),
        "author": author,
        "created_at": stamp,
        "updated_at": stamp,
        "renderer": "vega-lite",
        "spec": default_spec(columns),
        "data": {"format": fmt, "file": file_name, "lane": lane, "rows": rows, "bytes": nbytes, "columns": columns},
        "aggregate": None if lane == "small" else LARGE_DEFAULT_AGGREGATE,
    }
    if source is not None:
        doc["source"] = source
    return doc


def file_sha256(path: Path) -> str:
    """Hex SHA-256 of a file, read in chunks so a 200 MB parquet file is never held in memory."""
    digest = hashlib.sha256()
    with Path(path).open("rb") as f:
        while True:
            chunk = f.read(HASH_CHUNK)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def _write_bytes(path: Path, payload: bytes) -> None:
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_bytes(payload)
    tmp.replace(path)


def _remove_other_data_files(directory: Path, keep: str) -> None:
    """A staged chart directory holds exactly one data file: the one chart.json names."""
    for path in directory.glob("data.*"):
        if path.name != keep and path.is_file():
            path.unlink()


def write_staged_chart(table: pa.Table, chart_id: str, staging_root: Path, *, author: str, now: datetime,
                       source: dict | None = None) -> StagedChart:
    if table.num_columns == 0:
        raise LaneError("table has no columns")
    columns = infer_columns(table)
    directory = chart_dir(staging_root, chart_id)
    directory.mkdir(parents=True, exist_ok=True)

    payload = json.dumps(rows_from_table(table), ensure_ascii=False).encode("utf-8")
    if len(table) <= SMALL_MAX_ROWS and len(payload) <= SMALL_MAX_BYTES:
        fmt, lane = "json", "small"
        file_name = data_file_name(hashlib.sha256(payload).hexdigest(), fmt)
        data_path = directory / file_name
        _write_bytes(data_path, payload)
    else:
        fmt, lane = "parquet", "large"
        tmp_path = directory / PARQUET_TMP_NAME
        pq.write_table(table, tmp_path)
        size = tmp_path.stat().st_size
        if size > LARGE_MAX_BYTES:
            tmp_path.unlink()
            (directory / "chart.json").unlink(missing_ok=True)
            raise LaneError(f"parquet file is {size} bytes, over the large-lane cap of {LARGE_MAX_BYTES} bytes")
        file_name = data_file_name(file_sha256(tmp_path), fmt)
        data_path = directory / file_name
        tmp_path.replace(data_path)
    _remove_other_data_files(directory, keep=file_name)

    doc = skeleton(chart_id, columns, fmt, file_name, lane, len(table), data_path.stat().st_size, author, now, source)
```

- [ ] **Step 11b: Change `viz/publish/validate.py`**

Replace:

```python
from ..ids import chart_key, is_ancestor
```

with:

```python
from ..ids import chart_key, data_file_name, is_ancestor
```

Replace:

```python
from .staging import LARGE_MAX_BYTES, SMALL_MAX_BYTES, SMALL_MAX_ROWS
```

with:

```python
from .staging import LARGE_MAX_BYTES, SMALL_MAX_BYTES, SMALL_MAX_ROWS, file_sha256
```

Replace:

```python
    data = doc["data"]
    fmt, lane = data["format"], data["lane"]
    data_path = chart_dir / f"data.{fmt}"
    if not data_path.is_file():
        return errors + [f"data.{fmt}: not found"]
    size = data_path.stat().st_size
    if size != data["bytes"]:
        errors.append(f"data.bytes: declared {data['bytes']}, file is {size} bytes")

    if fmt == "json":
        try:
            table = table_from_file(data_path)
        except (UnsupportedColumn, ValueError) as err:
            return errors + [f"data.json: {err}"]
        rows = len(table)
    else:
        try:
            rows = pq.read_metadata(data_path).num_rows
            table = pq.read_table(data_path)
        except (pa.ArrowException, OSError, ValueError) as err:
            return errors + [f"data.parquet: {err}"]
```

with:

```python
    data = doc["data"]
    fmt, lane, file_name = data["format"], data["lane"], data["file"]
    data_path = chart_dir / file_name
    if not data_path.is_file():
        return errors + [f"{file_name}: not found"]
    expected_name = data_file_name(file_sha256(data_path), fmt)
    if expected_name != file_name:
        errors.append(f"data.file: '{file_name}' does not match the file's SHA-256; it should be named '{expected_name}'")
    others = sorted(p.name for p in chart_dir.glob("data.*") if p.name != file_name)
    if others:
        errors.append(f"data: the staged directory holds other data files ({', '.join(others)}); keep only '{file_name}'")
    size = data_path.stat().st_size
    if size != data["bytes"]:
        errors.append(f"data.bytes: declared {data['bytes']}, file is {size} bytes")

    if fmt == "json":
        try:
            table = table_from_file(data_path)
        except (UnsupportedColumn, ValueError) as err:
            return errors + [f"{file_name}: {err}"]
        rows = len(table)
    else:
        try:
            rows = pq.read_metadata(data_path).num_rows
            table = pq.read_table(data_path)
        except (pa.ArrowException, OSError, ValueError) as err:
            return errors + [f"{file_name}: {err}"]
```

Replace:

```python
    except UnsupportedColumn as err:
        errors.append(f"data.{fmt}: {err}")
```

with:

```python
    except UnsupportedColumn as err:
        errors.append(f"{file_name}: {err}")
```

- [ ] **Step 11c: Change `viz/publish/publish.py`**

Replace:

```python
def publish_chart(chart_dir: Path,
```

with:

```python
def _delete_other_data_files(storage: Storage, root: str, chart_id: str, keep: set[str]) -> None:
    """Delete every data.* object directly under charts/<id>/ whose name is not in keep.
    Keys one level deeper belong to another chart id and are never touched."""
    prefix = f"{root}charts/{chart_id}/"
    for info in storage.list(prefix):
        name = info.key[len(prefix):]
        if "/" in name or not name.startswith("data.") or name in keep:
            continue
        storage.delete(info.key)


def publish_chart(chart_dir: Path,
```

Replace:

```python
    chart_id = doc["id"]
    fmt = doc["data"]["format"]
    root = settings.root_prefix
    key = chart_key(root, chart_id)
    _guard_overwrite(storage, key, force, out)

    storage.put(data_key(root, chart_id, fmt), (chart_dir / f"data.{fmt}").read_bytes(), MEDIA_TYPES[fmt])
    storage.put(key, (chart_dir / "chart.json").read_bytes(), "application/json")
    other = "parquet" if fmt == "json" else "json"
    storage.delete(data_key(root, chart_id, other))
    print(f"published: {chart_id}", file=out)
```

with:

```python
    chart_id = doc["id"]
    fmt = doc["data"]["format"]
    file_name = doc["data"]["file"]
    root = settings.root_prefix
    key = chart_key(root, chart_id)
    _guard_overwrite(storage, key, force, out)

    storage.put(data_key(root, chart_id, file_name), (chart_dir / file_name).read_bytes(), MEDIA_TYPES[fmt])
    storage.put(key, (chart_dir / "chart.json").read_bytes(), "application/json")
    _delete_other_data_files(storage, root, chart_id, keep={file_name})
    print(f"published: {chart_id}", file=out)
```

- [ ] **Step 11d: Change `viz/server/routes.py`**

Replace:

```python
    fmt = doc["data"]["format"]
    key = data_key(settings.root_prefix, chart_id, fmt)
```

with:

```python
    fmt = doc["data"]["format"]
    key = data_key(settings.root_prefix, chart_id, doc["data"]["file"])
```

- [ ] **Step 11e: Replace the whole of `sample-bucket/generate.py`**

```python
"""Regenerate the sample bucket. Deterministic, synthetic, safe to commit.

Run from the repo root:  .venv/Scripts/python sample-bucket/generate.py
(needs the viz package installed: pip install -e ".[dev]")
"""
import hashlib
import json
import os
import random
from datetime import date, timedelta
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

from viz.ids import data_file_name

ROOT = Path(__file__).resolve().parent / "viz"
SKILL_EXAMPLES = Path(__file__).resolve().parents[1] / "skills" / "publish-viz" / "examples"
AUTHOR = "sample@example.com"
STAMP = "2026-09-22T10:00:00Z"
REGIONS = ["EMEA", "NA", "APAC", "LATAM"]
COLUMNS = [
    {"name": "month", "type": "date"},
    {"name": "region", "type": "string"},
    {"name": "revenue", "type": "number"},
    {"name": "orders", "type": "integer"},
]

RENDERERS = ["vega-lite"]
PRODUCTS = ["alpha", "bravo", "charlie", "delta", "echo", "foxtrot"]
ORDER_LINES = 200_000
QUARTER_COLUMNS = [
    {"name": "quarter", "type": "string"},
    {"name": "region", "type": "string"},
    {"name": "orders", "type": "integer"},
]
LINE_COLUMNS = [
    {"name": "day", "type": "date"},
    {"name": "region", "type": "string"},
    {"name": "product", "type": "string"},
    {"name": "amount", "type": "number"},
]
LINE_AGGREGATE = "SELECT day, sum(amount) AS amount FROM data GROUP BY day ORDER BY day"


def month_series(n: int = 36) -> list[date]:
    out = []
    year, month = 2023, 10
    for _ in range(n):
        out.append(date(year, month, 1))
        month += 1
        if month == 13:
            month, year = 1, year + 1
    return out


def rows() -> list[dict]:
    rng = random.Random(20260922)
    base = {"EMEA": 420_000, "NA": 610_000, "APAC": 300_000, "LATAM": 150_000}
    out = []
    for i, m in enumerate(month_series()):
        for region in REGIONS:
            growth = 1 + 0.012 * i
            season = 1 + 0.08 * ((m.month in (11, 12)) - (m.month in (1, 2)))
            noise = rng.uniform(0.93, 1.07)
            revenue = round(base[region] * growth * season * noise, 2)
            orders = int(revenue / rng.uniform(180, 260))
            out.append({"month": m.isoformat(), "region": region, "revenue": revenue, "orders": orders})
    return out


def write_json(path: Path, doc) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(doc, indent=2) + "\n"
    path.write_text(text, encoding="utf-8", newline="\n")
    return len(text.encode("utf-8"))


def remove_data_files(chart_dir: Path, keep: str) -> None:
    """Each chart directory holds exactly one data file: the one its chart.json names."""
    for path in chart_dir.glob("data.*"):
        if path.name != keep:
            path.unlink()


def write_data_json(chart_dir: Path, data_rows: list[dict]) -> tuple[str, int]:
    """Write the rows under their content-addressed name. Returns (file name, byte count)."""
    chart_dir.mkdir(parents=True, exist_ok=True)
    payload = (json.dumps(data_rows, indent=2) + "\n").encode("utf-8")
    name = data_file_name(hashlib.sha256(payload).hexdigest(), "json")
    (chart_dir / name).write_bytes(payload)
    remove_data_files(chart_dir, keep=name)
    return name, len(payload)


def write_data_parquet(chart_dir: Path, table: pa.Table) -> tuple[str, int]:
    """Write the table as parquet under its content-addressed name. Returns (file name, byte count)."""
    chart_dir.mkdir(parents=True, exist_ok=True)
    tmp = chart_dir / "parquet.tmp"
    pq.write_table(table, tmp, compression="snappy")
    payload = tmp.read_bytes()
    name = data_file_name(hashlib.sha256(payload).hexdigest(), "parquet")
    os.replace(tmp, chart_dir / name)
    remove_data_files(chart_dir, keep=name)
    return name, len(payload)


def chart_doc(chart_id, title, description, renderer, spec, data_file, data_rows, data_bytes, source=None,
              columns=COLUMNS, fmt="json", lane="small", aggregate=None, tags=("sales", "sample")):
    doc = {
        "schema_version": 1,
        "id": chart_id,
        "title": title,
        "description": description,
        "tags": list(tags),
        "author": AUTHOR,
        "created_at": STAMP,
        "updated_at": STAMP,
        "renderer": renderer,
        "spec": spec,
        "data": {"format": fmt, "file": data_file, "lane": lane, "rows": data_rows, "bytes": data_bytes,
                 "columns": columns},
        "aggregate": aggregate,
    }
    if source:
        doc["source"] = source
    return doc


def quarterly(data: list[dict]) -> list[dict]:
    totals: dict[tuple[str, str], int] = {}
    for r in data:
        year, month = r["month"][:4], int(r["month"][5:7])
        quarter = f"{year}-Q{(month - 1) // 3 + 1}"
        totals[(quarter, r["region"])] = totals.get((quarter, r["region"]), 0) + r["orders"]
    return [{"quarter": q, "region": region, "orders": n} for (q, region), n in sorted(totals.items())]


def order_lines() -> pa.Table:
    rng = random.Random(20260922)
    start = date(2024, 1, 1)
    lines = []
    for _ in range(ORDER_LINES):
        day = start + timedelta(days=rng.randrange(730))
        region = rng.choice(REGIONS)
        product = rng.choice(PRODUCTS)
        amount = round(rng.lognormvariate(4.5, 0.6), 2)
        lines.append((day, region, product, amount))
    lines.sort(key=lambda t: (t[0], t[1], t[2], t[3]))
    return pa.table({
        "day": pa.array([t[0] for t in lines], pa.date32()),
        "region": pa.array([t[1] for t in lines], pa.string()),
        "product": pa.array([t[2] for t in lines], pa.string()),
        "amount": pa.array([t[3] for t in lines], pa.float64()),
    })


def time_series_spec(renderer: str) -> dict:
    if renderer == "vega-lite":
        return {
            "$schema": "https://vega.github.io/schema/vega-lite/v6.json",
            "data": {"name": "data"},
            "width": "container",
            "height": "container",
            "mark": {"type": "line", "point": True},
            "encoding": {
                "x": {"field": "month", "type": "temporal", "title": "Month"},
                "y": {"field": "revenue", "type": "quantitative", "title": "Revenue"},
                "color": {"field": "region", "type": "nominal", "title": "Region"},
                "tooltip": [
                    {"field": "month", "type": "temporal", "title": "Month"},
                    {"field": "region", "type": "nominal", "title": "Region"},
                    {"field": "revenue", "type": "quantitative", "title": "Revenue", "format": ",.0f"},
                ],
            },
        }


def grouped_bar_spec(renderer: str) -> dict:
    if renderer == "vega-lite":
        return {
            "$schema": "https://vega.github.io/schema/vega-lite/v6.json",
            "data": {"name": "data"},
            "width": "container",
            "height": "container",
            "mark": "bar",
            "encoding": {
                "x": {"field": "quarter", "type": "ordinal", "title": "Quarter"},
                "xOffset": {"field": "region"},
                "y": {"field": "orders", "type": "quantitative", "title": "Orders"},
                "color": {"field": "region", "type": "nominal", "title": "Region"},
                "tooltip": [
                    {"field": "quarter", "type": "ordinal"},
                    {"field": "region", "type": "nominal"},
                    {"field": "orders", "type": "quantitative", "format": ","},
                ],
            },
        }


def order_lines_spec(renderer: str) -> dict:
    if renderer == "vega-lite":
        return {
            "$schema": "https://vega.github.io/schema/vega-lite/v6.json",
            "data": {"name": "data"},
            "width": "container",
            "height": "container",
            "mark": "bar",
            "encoding": {
                "x": {"field": "day", "type": "temporal", "title": "Day"},
                "y": {"field": "amount", "type": "quantitative", "title": "Amount"},
                "tooltip": [
                    {"field": "day", "type": "temporal"},
                    {"field": "amount", "type": "quantitative", "format": ",.0f"},
                ],
            },
        }


def renderer_title(renderer: str) -> str:
    return {"vega-lite": "Vega-Lite"}[renderer]


def write_bakeoff(data: list[dict]) -> None:
    charts = ROOT / "charts" / "bakeoff"
    dashboards = ROOT / "dashboards" / "bakeoff"
    quarters = quarterly(data)
    lines = order_lines()

    write_json(charts / "_folder.json", {"schema_version": 1, "title": "Bake-off", "description": "The same four charts written for each renderer.", "order": 20})
    write_json(dashboards / "_folder.json", {"schema_version": 1, "title": "Bake-off", "description": "One dashboard per renderer. Pick a winner.", "order": 20})

    name, n = write_data_json(charts / "total-revenue", data)
    write_json(charts / "total-revenue" / "chart.json", chart_doc(
        "bakeoff/total-revenue", "Total revenue", "Sum of revenue over the selected period, with total orders.",
        "stat", {"value": "revenue", "agg": "sum", "format": "$,.0f", "compare": {"column": "orders", "agg": "sum"}},
        name, len(data), n, tags=("bakeoff", "sample"),
    ))

    for renderer in RENDERERS:
        folder = charts / renderer
        write_json(folder / "_folder.json", {"schema_version": 1, "title": renderer_title(renderer)})

        name, n = write_data_json(folder / "time-series", data)
        write_json(folder / "time-series" / "chart.json", chart_doc(
            f"bakeoff/{renderer}/time-series", f"Revenue by region, monthly ({renderer_title(renderer)})",
            "Monthly revenue per region. Filter with the Period and Region controls.",
            renderer, time_series_spec(renderer), name, len(data), n, tags=("bakeoff", "sample"),
        ))

        name, n = write_data_json(folder / "grouped-bar", quarters)
        write_json(folder / "grouped-bar" / "chart.json", chart_doc(
            f"bakeoff/{renderer}/grouped-bar", f"Orders by region, quarterly ({renderer_title(renderer)})",
            "Quarterly orders per region. Filter with the Region control.",
            renderer, grouped_bar_spec(renderer), name, len(quarters), n, columns=QUARTER_COLUMNS,
            tags=("bakeoff", "sample"),
        ))

        name, n = write_data_parquet(folder / "order-lines", lines)
        write_json(folder / "order-lines" / "chart.json", chart_doc(
            f"bakeoff/{renderer}/order-lines", f"Order amount per day ({renderer_title(renderer)})",
            f"{ORDER_LINES:,} synthetic order lines aggregated per day in the browser with DuckDB. Filter with the Days and Region controls.",
            renderer, order_lines_spec(renderer), name, lines.num_rows, n,
            columns=LINE_COLUMNS, fmt="parquet", lane="large", aggregate=LINE_AGGREGATE, tags=("bakeoff", "sample"),
        ))

        write_json(dashboards / f"{renderer}.json", {
            "schema_version": 1,
            "id": f"bakeoff/{renderer}",
            "title": f"Bake-off: {renderer_title(renderer)}",
            "description": f"The four bake-off charts rendered with {renderer_title(renderer)}. Synthetic data.",
            "tags": ["bakeoff", "sample"],
            "author": AUTHOR,
            "created_at": STAMP,
            "updated_at": STAMP,
            "controls": [
                {"id": "period", "type": "date-range", "label": "Period", "column": "month", "default": {"last": "12m"}},
                {"id": "days", "type": "date-range", "label": "Days", "column": "day", "default": None},
                {"id": "region", "type": "select", "label": "Region", "column": "region", "multi": True, "default": None},
            ],
            "layout": [
                {"chart": f"bakeoff/{renderer}/time-series", "w": 8, "h": 4},
                {"chart": "bakeoff/total-revenue", "w": 4, "h": 2},
                {"chart": f"bakeoff/{renderer}/grouped-bar", "w": 6, "h": 4},
                {"chart": f"bakeoff/{renderer}/order-lines", "w": 6, "h": 4},
                {"markdown": f"Rendered with **{renderer_title(renderer)}**. Same data and controls on every bake-off dashboard.", "w": 12, "h": 1},
            ],
        })


def write_examples(data: list[dict]) -> None:
    """Publish every chart form from the publish-viz skill, on the monthly dataset, plus a gallery."""
    charts = ROOT / "charts" / "examples"
    dashboards = ROOT / "dashboards" / "examples"
    write_json(charts / "_folder.json", {"schema_version": 1, "title": "Examples", "description": "The chart forms taught by the publish-viz skill.", "order": 30})
    write_json(dashboards / "_folder.json", {"schema_version": 1, "title": "Examples", "description": "A gallery of every chart form the publish-viz skill teaches.", "order": 30})

    layout = []
    for path in sorted(SKILL_EXAMPLES.glob("*.json")):
        example = json.loads(path.read_text(encoding="utf-8"))
        chart_id = f"examples/{path.stem}"
        name, n = write_data_json(charts / path.stem, data)
        write_json(charts / path.stem / "chart.json", chart_doc(
            chart_id, example["title"], example["description"], example["renderer"], example["spec"],
            name, len(data), n, tags=("examples", "sample"),
        ))
        layout.append({"chart": chart_id, "w": 6, "h": 3})

    write_json(dashboards / "gallery.json", {
        "schema_version": 1,
        "id": "examples/gallery",
        "title": "Chart form gallery",
        "description": "Every example from the publish-viz skill's Vega-Lite guide, on synthetic data.",
        "tags": ["examples", "sample"],
        "author": AUTHOR,
        "created_at": STAMP,
        "updated_at": STAMP,
        "controls": [
            {"id": "period", "type": "date-range", "label": "Period", "column": "month", "default": None},
            {"id": "region", "type": "select", "label": "Region", "column": "region", "multi": True, "default": None},
        ],
        "layout": layout,
    })


def main() -> None:
    data = rows()
    charts = ROOT / "charts" / "sales"
    dashboards = ROOT / "dashboards" / "sales"

    write_json(charts / "_folder.json", {"schema_version": 1, "title": "Sales", "description": "Sample sales charts.", "order": 10})
    write_json(dashboards / "_folder.json", {"schema_version": 1, "title": "Sales", "description": "Sample sales dashboards.", "order": 10})

    name, n = write_data_json(charts / "revenue-by-region", data)
    write_json(charts / "revenue-by-region" / "chart.json", chart_doc(
        "sales/revenue-by-region",
        "Revenue by region, monthly",
        "Monthly revenue for each region over the last three years. Synthetic data.",
        "vega-lite",
        {
            "$schema": "https://vega.github.io/schema/vega-lite/v6.json",
            "data": {"name": "data"},
            "mark": {"type": "line", "point": True},
            "encoding": {
                "x": {"field": "month", "type": "temporal", "title": "Month"},
                "y": {"field": "revenue", "type": "quantitative", "title": "Revenue"},
                "color": {"field": "region", "type": "nominal", "title": "Region"},
            },
        },
        name, len(data), n,
        source={
            "kind": "databricks-sql",
            "sql": "SELECT month, region, revenue, orders FROM sample.sales.monthly_revenue ORDER BY month, region",
            "warehouse_id": "sample",
            "schedule": "0 6 * * *",
            "show_sql": True,
        },
    ))

    name, n = write_data_json(charts / "total-revenue", data)
    write_json(charts / "total-revenue" / "chart.json", chart_doc(
        "sales/total-revenue",
        "Total revenue",
        "Sum of revenue over the selected period. One-off publish, no source.",
        "stat",
        {"value": "revenue", "agg": "sum", "format": "$,.0f", "compare": {"column": "orders", "agg": "sum"}},
        name, len(data), n,
    ))

    write_json(dashboards / "overview.json", {
        "schema_version": 1,
        "id": "sales/overview",
        "title": "Sales overview",
        "description": "Revenue and orders by region. Synthetic sample data.",
        "tags": ["sales", "sample"],
        "author": AUTHOR,
        "created_at": STAMP,
        "updated_at": STAMP,
        "controls": [
            {"id": "period", "type": "date-range", "label": "Period", "column": "month", "default": {"last": "12m"}},
            {"id": "region", "type": "select", "label": "Region", "column": "region", "multi": True, "default": None},
        ],
        "layout": [
            {"chart": "sales/revenue-by-region", "w": 8, "h": 4},
            {"chart": "sales/total-revenue", "w": 4, "h": 2},
            {"markdown": "This dashboard is generated by `sample-bucket/generate.py`. Nothing here is real.", "w": 12, "h": 1},
        ],
    })

    write_bakeoff(data)
    write_examples(data)


if __name__ == "__main__":
    main()
```

- [ ] **Step 11f: Regenerate the sample bucket**

Run: `.venv/Scripts/python sample-bucket/generate.py`
Then run: `git status --short sample-bucket`
Expected: for each of the 17 chart directories, its old `data.json` (or, for `bakeoff/vega-lite/order-lines`, `data.parquet`) shows as ` D` and a new `data.<16 hex>.json` (or `.parquet`) shows as `??`; every `chart.json` shows as ` M`; `sample-bucket/generate.py` shows as ` M`. No `parquet.tmp` file anywhere. Dashboards and `_folder.json` files are unchanged.

- [ ] **Step 12: Run the tests to see them pass**

Run: `.venv/Scripts/python -m pytest tests/test_ids.py tests/test_schemas.py tests/test_sample_bucket.py tests/publish tests/server/test_data_route.py -q`
Expected: all pass.

Run: `.venv/Scripts/python -m pytest`
Expected: all pass.

Run the front-end tests too, because `web/src/renderers/samples.test.ts` reads every sample chart.json:
`export PATH="/c/Program Files/nodejs:$PATH"` then, from `web/`: `npm test`
Expected: all test files pass.

- [ ] **Step 13: Commit**

`git add` of the `sample-bucket/viz` directory stages the deleted old data files and the new hashed ones.

```bash
git add viz/ids.py schemas/chart.schema.json viz/publish/staging.py viz/publish/validate.py viz/publish/publish.py viz/server/routes.py sample-bucket/generate.py sample-bucket/viz tests/fixtures/valid/chart-large.json tests/fixtures/valid/chart-stat.json tests/fixtures/valid/chart-vegalite.json tests/test_ids.py tests/test_schemas.py tests/test_sample_bucket.py tests/publish/test_staging.py tests/publish/test_validate.py tests/publish/test_publish.py tests/publish/test_move.py tests/publish/test_end_to_end.py tests/publish/test_cli_stage.py tests/publish/test_cli_errors.py tests/server/test_data_route.py
git -c user.name="tripp" -c user.email="dom4domg@gmail.com" commit -m "feat: content-addressed data files named by data.file in chart.json" -m "Co-Authored-By: <model name from your harness> <noreply@anthropic.com>
Claude-Session: <session url from your harness>"
```

Then `git status --short sample-bucket` must print nothing.

---

### Task 3: Publish commits with a conditional PUT and keeps one previous data file

**Files:**
- Modify: `viz/publish/publish.py` (whole file)
- Test: Modify `tests/publish/test_publish.py`

**Interfaces:**
- Consumes: Task 1 `put(..., if_match=, if_none_match=)`, `PreconditionFailed`, `head(key).etag`; Task 2 `DATA_FILE_PATTERN`, `data_key(root, id, file_name)`.
- Produces (all in `viz.publish.publish`):
  - `publish_chart(chart_dir, settings, storage, force=False, allow_row_level=False, out=None) -> str` and `publish_dashboard(path, settings, storage, force=False, out=None) -> str` (signatures unchanged).
  - `_existing(storage, key) -> tuple[dict | None, str | None]`: the published document and its ETag, `(None, None)` when absent. Reads the ETag with `head` before the body with `get`. Unparseable content is `({}, etag)`.
  - `_guard_overwrite(storage, key, force, out) -> tuple[dict | None, str | None]`.
  - `_commit(storage, key, payload, doc_id, etag)`: `if_none_match=True` when `etag` is None, else `if_match=etag`; a `PreconditionFailed` becomes `PublishRefused(["<doc_id> changed since you checked it; run the command again"])`.
  - `_named_data_file(doc) -> str | None`, `_delete_other_data_files(storage, root, chart_id, keep: set[str])`.

- [ ] **Step 1: Write the failing tests**

In `tests/publish/test_publish.py` replace:

```python
class RecordingStorage(LocalStorage):
    def __init__(self, root):
        super().__init__(root)
        self.puts: list[str] = []

    def put(self, key, data, content_type):
        self.puts.append(key)
        super().put(key, data, content_type)
```

with:

```python
class RecordingStorage(LocalStorage):
    def __init__(self, root):
        super().__init__(root)
        self.puts: list[str] = []
        self.conditions: list[dict] = []

    def put(self, key, data, content_type, *, if_match=None, if_none_match=False):
        self.puts.append(key)
        self.conditions.append({"if_match": if_match, "if_none_match": if_none_match})
        super().put(key, data, content_type, if_match=if_match, if_none_match=if_none_match)


class RacingStorage(LocalStorage):
    """Another publisher writes `target` just before our conditional PUT of it lands."""

    def __init__(self, root, target):
        super().__init__(root)
        self.target = target

    def put(self, key, data, content_type, *, if_match=None, if_none_match=False):
        if key == self.target and (if_match is not None or if_none_match):
            super().put(key, b'{"author": "rival@example.com"}', "application/json")
        super().put(key, data, content_type, if_match=if_match, if_none_match=if_none_match)


def _staged_value(staging_root, revenue: float):
    table = pa.table({"month": [date(2024, 1, 1)], "revenue": [revenue]})
    return write_staged_chart(table, "sales/new-chart", staging_root, author="tester@example.com", now=NOW)


def _published_data_files(storage, chart_id="sales/new-chart"):
    prefix = f"viz/charts/{chart_id}/"
    names = [info.key[len(prefix):] for info in storage.list(prefix)]
    return sorted(name for name in names if name.startswith("data."))
```

Then add these tests at the end of the file:

```python


def test_chart_json_put_is_conditional(settings, bucket, staging_root):
    storage = RecordingStorage(bucket)
    staged = _staged(staging_root)
    publish_chart(staged.dir, settings, storage)
    assert storage.conditions[0] == {"if_match": None, "if_none_match": False}   # data file
    assert storage.conditions[1] == {"if_match": None, "if_none_match": True}    # new chart.json
    etag = storage.head("viz/charts/sales/new-chart/chart.json").etag
    publish_chart(staged.dir, settings, storage, force=True)
    assert storage.conditions[3] == {"if_match": etag, "if_none_match": False}   # overwrite


def test_new_chart_created_by_someone_else_meanwhile_is_refused(settings, bucket, staging_root):
    storage = RacingStorage(bucket, "viz/charts/sales/new-chart/chart.json")
    staged = _staged(staging_root)
    with pytest.raises(PublishRefused) as exc:
        publish_chart(staged.dir, settings, storage)
    assert exc.value.errors == ["sales/new-chart changed since you checked it; run the command again"]
    assert json.loads(storage.get("viz/charts/sales/new-chart/chart.json")) == {"author": "rival@example.com"}


def test_overwrite_of_a_chart_changed_meanwhile_is_refused(settings, bucket, staging_root):
    staged = _staged(staging_root)
    publish_chart(staged.dir, settings, LocalStorage(bucket))
    racing = RacingStorage(bucket, "viz/charts/sales/new-chart/chart.json")
    with pytest.raises(PublishRefused) as exc:
        publish_chart(staged.dir, settings, racing, force=True)
    assert exc.value.errors == ["sales/new-chart changed since you checked it; run the command again"]


def test_dashboard_changed_meanwhile_is_refused(settings, storage, bucket, staging_root):
    publish_chart(_staged(staging_root).dir, settings, storage)
    path = _dashboard_file(staging_root)
    racing = RacingStorage(bucket, "viz/dashboards/sales/board.json")
    with pytest.raises(PublishRefused) as exc:
        publish_dashboard(path, settings, racing)
    assert exc.value.errors == ["sales/board changed since you checked it; run the command again"]
    publish_dashboard(path, settings, LocalStorage(bucket), force=True)
    racing = RacingStorage(bucket, "viz/dashboards/sales/board.json")
    with pytest.raises(PublishRefused):
        publish_dashboard(path, settings, racing, force=True)


def test_publish_keeps_the_new_and_one_previous_data_file(settings, storage, staging_root):
    first = _staged_value(staging_root, 1.0)
    first_file = first.doc["data"]["file"]
    publish_chart(first.dir, settings, storage)
    assert _published_data_files(storage) == [first_file]

    second = _staged_value(staging_root, 2.0)
    second_file = second.doc["data"]["file"]
    publish_chart(second.dir, settings, storage, force=True)
    assert _published_data_files(storage) == sorted([first_file, second_file])

    third = _staged_value(staging_root, 3.0)
    third_file = third.doc["data"]["file"]
    publish_chart(third.dir, settings, storage, force=True)
    assert _published_data_files(storage) == sorted([second_file, third_file])


def test_republishing_the_same_bytes_keeps_one_data_file(settings, storage, staging_root):
    staged = _staged_value(staging_root, 1.0)
    publish_chart(staged.dir, settings, storage)
    publish_chart(staged.dir, settings, storage, force=True)
    assert _published_data_files(storage) == [staged.doc["data"]["file"]]


def test_a_reader_of_the_replaced_chart_json_can_still_fetch_its_data(settings, storage, staging_root):
    first = _staged_value(staging_root, 1.0)
    publish_chart(first.dir, settings, storage)
    old_doc = json.loads(storage.get("viz/charts/sales/new-chart/chart.json"))
    publish_chart(_staged_value(staging_root, 2.0).dir, settings, storage, force=True)
    assert json.loads(storage.get(f"viz/charts/sales/new-chart/{old_doc['data']['file']}")) == [
        {"month": "2024-01-01", "revenue": 1.0}
    ]
    r = TestClient(create_app(settings)).get("/api/data/sales/new-chart")
    assert r.json() == [{"month": "2024-01-01", "revenue": 2.0}]
```

- [ ] **Step 2: Run them to see them fail**

Run: `.venv/Scripts/python -m pytest tests/publish/test_publish.py -v`
Expected: 6 FAILED: `test_chart_json_put_is_conditional` (the chart.json put carries no condition), the three `..._meanwhile_is_refused` tests (`DID NOT RAISE PublishRefused`), `test_publish_keeps_the_new_and_one_previous_data_file` (the previous file was deleted), `test_a_reader_of_the_replaced_chart_json_can_still_fetch_its_data` (`NotFound`). `test_republishing_the_same_bytes_keeps_one_data_file` and the older tests pass.

- [ ] **Step 3: Replace the whole of `viz/publish/publish.py`**

```python
"""Copy a validated staged chart or dashboard into the bucket.

A chart publish is three steps (hardening decision B2):
1. PUT the data file under its content-addressed key. Same bytes, same key, so a retry is harmless.
2. PUT chart.json conditionally. This is the single commit point: a new chart is written only if
   no chart.json exists (if_none_match); an overwrite only if chart.json still has the ETag read
   during the overwrite guard (if_match). Readers see the old chart or the new one, never a
   chart.json whose data file is missing.
3. Delete every other data.* object of the chart except the file the replaced chart.json named,
   so a reader still holding the old chart.json can fetch its data. One generation is kept.
"""
import json
import sys
from pathlib import Path

from ..config import Settings
from ..ids import DATA_FILE_PATTERN, chart_key, dashboard_key, data_key
from ..storage import NotFound, PreconditionFailed, Storage
from .validate import read_document, validate_dashboard_file, validate_staged_chart

MEDIA_TYPES = {"json": "application/json", "parquet": "application/octet-stream"}


class PublishRefused(Exception):
    def __init__(self, errors: list[str]):
        self.errors = list(errors)
        super().__init__("; ".join(self.errors))


def _existing(storage: Storage, key: str) -> tuple[dict | None, str | None]:
    """The published document at key and the ETag it was read with, or (None, None).
    The ETag is read before the body: if the object changes in between, the later
    conditional PUT fails instead of overwriting something nobody was shown."""
    try:
        etag = storage.head(key).etag
        raw = storage.get(key)
    except NotFound:
        return None, None
    try:
        doc = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError):
        return {}, etag
    return (doc if isinstance(doc, dict) else {}), etag


def _guard_overwrite(storage: Storage, key: str, force: bool, out) -> tuple[dict | None, str | None]:
    """Refuse to overwrite without force. Returns the existing document and its ETag,
    or (None, None) when nothing is published at key."""
    existing, etag = _existing(storage, key)
    if existing is None:
        return None, None
    author = existing.get("author", "unknown")
    updated = existing.get("updated_at", "unknown")
    if not force:
        raise PublishRefused([f"id exists: author {author}, updated_at {updated}; pass --force to overwrite"])
    print(f"overwriting: author {author}, updated_at {updated}", file=out)
    return existing, etag


def _commit(storage: Storage, key: str, payload: bytes, doc_id: str, etag: str | None) -> None:
    """The conditional PUT that makes a publish visible. etag None means a new document."""
    try:
        if etag is None:
            storage.put(key, payload, "application/json", if_none_match=True)
        else:
            storage.put(key, payload, "application/json", if_match=etag)
    except PreconditionFailed as err:
        raise PublishRefused([f"{doc_id} changed since you checked it; run the command again"]) from err


def _named_data_file(doc: dict | None) -> str | None:
    """The data.file a published chart.json names, if it is a valid content-addressed name."""
    if not isinstance(doc, dict):
        return None
    data = doc.get("data")
    name = data.get("file") if isinstance(data, dict) else None
    if isinstance(name, str) and DATA_FILE_PATTERN.fullmatch(name):
        return name
    return None


def _delete_other_data_files(storage: Storage, root: str, chart_id: str, keep: set[str]) -> None:
    """Delete every data.* object directly under charts/<id>/ whose name is not in keep.
    Keys one level deeper belong to another chart id and are never touched."""
    prefix = f"{root}charts/{chart_id}/"
    for info in storage.list(prefix):
        name = info.key[len(prefix):]
        if "/" in name or not name.startswith("data.") or name in keep:
            continue
        storage.delete(info.key)


def publish_chart(chart_dir: Path, settings: Settings, storage: Storage, force: bool = False,
                  allow_row_level: bool = False, out=None) -> str:
    out = sys.stdout if out is None else out
    chart_dir = Path(chart_dir)
    errors = validate_staged_chart(chart_dir, settings, storage, allow_row_level=allow_row_level)
    if errors:
        raise PublishRefused(errors)
    doc, _ = read_document(chart_dir / "chart.json")
    chart_id = doc["id"]
    fmt = doc["data"]["format"]
    file_name = doc["data"]["file"]
    root = settings.root_prefix
    key = chart_key(root, chart_id)
    existing, etag = _guard_overwrite(storage, key, force, out)

    storage.put(data_key(root, chart_id, file_name), (chart_dir / file_name).read_bytes(), MEDIA_TYPES[fmt])
    _commit(storage, key, (chart_dir / "chart.json").read_bytes(), chart_id, etag)
    keep = {file_name}
    previous = _named_data_file(existing)
    if previous is not None:
        keep.add(previous)
    _delete_other_data_files(storage, root, chart_id, keep)
    print(f"published: {chart_id}", file=out)
    return chart_id


def publish_dashboard(path: Path, settings: Settings, storage: Storage, force: bool = False, out=None) -> str:
    out = sys.stdout if out is None else out
    path = Path(path)
    errors = validate_dashboard_file(path, settings, storage)
    if errors:
        raise PublishRefused(errors)
    doc, _ = read_document(path)
    dashboard_id = doc["id"]
    key = dashboard_key(settings.root_prefix, dashboard_id)
    _existing_doc, etag = _guard_overwrite(storage, key, force, out)
    _commit(storage, key, path.read_bytes(), dashboard_id, etag)
    print(f"published: {dashboard_id}", file=out)
    return dashboard_id
```

- [ ] **Step 4: Run the tests to see them pass**

Run: `.venv/Scripts/python -m pytest tests/publish/test_publish.py -v`
Expected: all pass, 0 failed.

- [ ] **Step 5: Run the whole suite, then commit**

Run: `.venv/Scripts/python -m pytest`
Expected: all pass.

```bash
git add viz/publish/publish.py tests/publish/test_publish.py
git -c user.name="tripp" -c user.email="dom4domg@gmail.com" commit -m "feat: publish commits chart.json with a conditional PUT and keeps one previous data file" -m "Co-Authored-By: <model name from your harness> <noreply@anthropic.com>
Claude-Session: <session url from your harness>"
```

---

### Task 4: Front-end type `ChartData.file`

**Files:**
- Modify: `web/src/api/types.ts`
- Test: Modify `web/src/components/ChartTile.test.tsx`, `web/src/pages/ChartPage.test.tsx`, `web/src/pages/DashboardPage.test.tsx`

**Interfaces:**
- Consumes: the chart.json contract from Task 2.
- Produces: `ChartData = { format: 'json' | 'parquet'; file: string; lane: 'small' | 'large'; rows: number; bytes: number; columns: Column[] }`. Nothing reads `file` yet; the front end keeps fetching `/api/data/<id>`.

- [ ] **Step 1: Add `file` to the test charts (the failing check)**

In `web/src/components/ChartTile.test.tsx` replace:

```ts
  data: {
    format: 'json',
    lane: 'small',
    rows: 2,
    bytes: 10,
```

with:

```ts
  data: {
    format: 'json',
    file: 'data.0123456789abcdef.json',
    lane: 'small',
    rows: 2,
    bytes: 10,
```

In `web/src/pages/ChartPage.test.tsx` replace:

```ts
  data: { format: 'json', lane: 'small', rows: 1, bytes: 1, columns:
```

with:

```ts
  data: { format: 'json', file: 'data.0123456789abcdef.json', lane: 'small', rows: 1, bytes: 1, columns:
```

In `web/src/pages/DashboardPage.test.tsx` replace:

```ts
  data: { format: 'json', lane: 'small', rows: 2, bytes: 1, columns }, aggregate: null,
```

with:

```ts
  data: { format: 'json', file: 'data.0123456789abcdef.json', lane: 'small', rows: 2, bytes: 1, columns }, aggregate: null,
```

- [ ] **Step 2: Run the type check to see it fail**

Run: `export PATH="/c/Program Files/nodejs:$PATH"` then, from `web/`: `npm run typecheck`
Expected: three errors `TS2353: Object literal may only specify known properties, and 'file' does not exist in type 'ChartData'`, one in each of the three test files.

- [ ] **Step 3: Add the field in `web/src/api/types.ts`**

Replace:

```ts
export interface ChartData {
  format: 'json' | 'parquet';
  lane: 'small' | 'large';
```

with:

```ts
export interface ChartData {
  format: 'json' | 'parquet';
  // Content-addressed data file name, data.<16 hex>.<format>. The server
  // resolves it; the front end always fetches /api/data/<id>.
  file: string;
  lane: 'small' | 'large';
```

- [ ] **Step 4: Run the checks to see them pass**

From `web/` (with the PATH export): `npm run typecheck` then `npm test`
Expected: no type errors; all test files pass.

- [ ] **Step 5: Run the whole Python suite, then commit**

Run: `.venv/Scripts/python -m pytest`
Expected: all pass.

```bash
git add web/src/api/types.ts web/src/components/ChartTile.test.tsx web/src/pages/ChartPage.test.tsx web/src/pages/DashboardPage.test.tsx
git -c user.name="tripp" -c user.email="dom4domg@gmail.com" commit -m "feat(web): ChartData carries the content-addressed data file name" -m "Co-Authored-By: <model name from your harness> <noreply@anthropic.com>
Claude-Session: <session url from your harness>"
```

---

### Task 5: One bad object cannot take down the tree (A1)

**Files:**
- Modify: `viz/schemas.py`, `viz/server/documents.py`, `viz/server/tree.py`, `viz/publish/validate.py`
- Test: Create `tests/server/test_tree_isolation.py`

**Interfaces:**
- Consumes: `viz.server.tree.build_tree`, the server test fixtures `settings`, `client`, `bucket` (`tests/server/conftest.py`).
- Produces:
  - `viz.schemas.MAX_NESTING_DEPTH = 64`; `viz.schemas.nesting_depth_exceeds(doc, limit=64) -> bool` (iterative; `{"a": 1}` and `[1]` are depth 1).
  - `validate_chart`, `validate_dashboard`, `validate_folder` raise `SchemaError(["$: nesting deeper than 64 levels"])` before running JSON Schema.
  - `documents._read` turns `RecursionError` from `json.loads` into `SchemaError(["$: invalid JSON (nested too deeply)"])` (so the chart route answers 422).
  - Tree nodes: any other exception while loading one chart, dashboard or folder metadata gives `"error": "could not load (<ExceptionClassName>)"` and a `viz.server` WARNING log line; the rest of the tree is built.
  - `viz.publish.validate.read_document` returns `(None, ["<name>: invalid JSON (nested too deeply)"])` on `RecursionError`.

- [ ] **Step 1: Write the failing tests**

Create `tests/server/test_tree_isolation.py`:

```python
"""A1: one hostile or unreadable object in the bucket must not take down /api/tree."""
import json

import pytest

from viz import schemas
from viz.publish.validate import read_document
from viz.server.tree import build_tree
from viz.storage import get_storage


@pytest.fixture
def storage(settings):
    return get_storage(settings)


def _find_folder(node, name):
    return next(f for f in node["folders"] if f["name"] == name)


def _item(folder, item_id):
    return next(i for i in folder["items"] if i["id"] == item_id)


def _nested_arrays(depth: int) -> str:
    return "[" * depth + "]" * depth


def _chart_with_deep_spec(storage, depth: int) -> bytes:
    doc = json.loads(storage.get("viz/charts/sales/total-revenue/chart.json"))
    doc["id"] = "sales/deep"
    text = json.dumps(doc)
    return text.replace('"spec": {', f'"spec": {{"x": {_nested_arrays(depth)}, ', 1).encode("utf-8")


def test_nesting_depth_check():
    assert schemas.nesting_depth_exceeds({"a": 1}, limit=1) is False
    assert schemas.nesting_depth_exceeds({"a": [1]}, limit=1) is True
    assert schemas.nesting_depth_exceeds(json.loads(_nested_arrays(64)), limit=64) is False
    assert schemas.nesting_depth_exceeds(json.loads(_nested_arrays(65)), limit=64) is True
    assert schemas.nesting_depth_exceeds(5) is False


def test_deep_document_is_a_schema_error_not_a_crash():
    doc = {"schema_version": 1, "spec": json.loads(_nested_arrays(300))}
    for validate in (schemas.validate_chart, schemas.validate_dashboard, schemas.validate_folder):
        with pytest.raises(schemas.SchemaError) as excinfo:
            validate(doc)
        assert excinfo.value.errors == [f"$: nesting deeper than {schemas.MAX_NESTING_DEPTH} levels"]


def test_every_sample_chart_is_under_the_depth_cap(storage, settings):
    for info in storage.list("viz/charts/"):
        if info.key.endswith("/chart.json"):
            assert not schemas.nesting_depth_exceeds(json.loads(storage.get(info.key))), info.key


@pytest.mark.parametrize("depth", [300, 100_000])
def test_deeply_nested_chart_becomes_an_error_node(storage, settings, depth):
    storage.put("viz/charts/sales/deep/chart.json", _chart_with_deep_spec(storage, depth), "application/json")
    tree = build_tree(storage, settings)
    sales = _find_folder(tree["charts"], "sales")
    node = _item(sales, "sales/deep")
    assert set(node) == {"type", "id", "error"}
    assert "nest" in node["error"]
    assert _item(sales, "sales/total-revenue")["title"] == "Total revenue"


def test_deeply_nested_chart_is_422_on_the_chart_route(client, storage):
    storage.put("viz/charts/sales/deep/chart.json", _chart_with_deep_spec(storage, 100_000), "application/json")
    assert client.get("/api/tree").status_code == 200
    r = client.get("/api/charts/sales/deep")
    assert r.status_code == 422
    assert "nested too deeply" in r.json()["detail"]["errors"][0]


def test_storage_error_on_one_chart_becomes_an_error_node(storage, settings, monkeypatch):
    real_get = storage.get

    def denied_get(key):
        if key.endswith("sales/total-revenue/chart.json"):
            raise PermissionError("AccessDenied: foreign KMS key")
        return real_get(key)

    monkeypatch.setattr(storage, "get", denied_get)
    tree = build_tree(storage, settings)
    sales = _find_folder(tree["charts"], "sales")
    assert _item(sales, "sales/total-revenue")["error"] == "could not load (PermissionError)"
    assert _item(sales, "sales/revenue-by-region")["title"] == "Revenue by region, monthly"


def test_storage_error_on_a_dashboard_and_a_folder_becomes_an_error(storage, settings, monkeypatch):
    real_get = storage.get

    def denied_get(key):
        if key.endswith("dashboards/sales/overview.json") or key.endswith("charts/sales/_folder.json"):
            raise RuntimeError("boom")
        return real_get(key)

    monkeypatch.setattr(storage, "get", denied_get)
    tree = build_tree(storage, settings)
    assert _item(_find_folder(tree["dashboards"], "sales"), "sales/overview")["error"] == "could not load (RuntimeError)"
    assert _find_folder(tree["charts"], "sales")["error"] == "could not load (RuntimeError)"


def test_tree_route_survives_a_storage_error(client, monkeypatch):
    app_storage = client.app.state.storage
    real_get = app_storage.get

    def denied_get(key):
        if key.endswith("sales/total-revenue/chart.json"):
            raise RuntimeError("AccessDenied")
        return real_get(key)

    monkeypatch.setattr(app_storage, "get", denied_get)
    r = client.get("/api/tree")
    assert r.status_code == 200


def test_cli_read_document_reports_deep_json(tmp_path):
    path = tmp_path / "chart.json"
    path.write_text(_nested_arrays(100_000), encoding="utf-8")
    doc, errors = read_document(path)
    assert doc is None
    assert errors == ["chart.json: invalid JSON (nested too deeply)"]
```

- [ ] **Step 2: Run them to see them fail**

Run: `.venv/Scripts/python -m pytest tests/server/test_tree_isolation.py -v`
Expected: all 10 tests fail, with `AttributeError: module 'viz.schemas' has no attribute 'nesting_depth_exceeds'`, `RecursionError` from jsonschema or `json.loads`, or a `PermissionError`/`RuntimeError` escaping `build_tree`.

- [ ] **Step 3: Add the nesting cap to `viz/schemas.py`**

Replace:

```python
_CANDIDATE_DIRS = (
    Path(__file__).parent / "_schemas",
    Path(__file__).resolve().parents[1] / "schemas",
)
```

with:

```python
_CANDIDATE_DIRS = (
    Path(__file__).parent / "_schemas",
    Path(__file__).resolve().parents[1] / "schemas",
)

# Deeper documents are refused before JSON Schema runs: the validator and the spec
# walks below recurse once per level, and a few hundred levels of nested arrays
# raise RecursionError. Real Vega-Lite specs stay far below this.
MAX_NESTING_DEPTH = 64
```

Replace:

```python
def _schema_errors(name: str, doc: Any) -> list[str]:
```

with:

```python
def nesting_depth_exceeds(doc: Any, limit: int = MAX_NESTING_DEPTH) -> bool:
    """True when objects and arrays nest deeper than limit. Iterative, so it cannot
    itself overflow the stack. A scalar is depth 0; {"a": 1} and [1] are depth 1."""
    stack = [(doc, 0)]
    while stack:
        node, depth = stack.pop()
        if isinstance(node, dict):
            children = list(node.values())
        elif isinstance(node, list):
            children = node
        else:
            continue
        if depth + 1 > limit:
            return True
        for child in children:
            stack.append((child, depth + 1))
    return False


def _depth_errors(doc: Any) -> list[str]:
    if nesting_depth_exceeds(doc):
        return [f"$: nesting deeper than {MAX_NESTING_DEPTH} levels"]
    return []


def _schema_errors(name: str, doc: Any) -> list[str]:
```

Replace:

```python
def validate_chart(doc: Any) -> dict:
    errors = _schema_errors("chart", doc)
```

with:

```python
def validate_chart(doc: Any) -> dict:
    depth = _depth_errors(doc)
    if depth:
        raise SchemaError(depth)
    errors = _schema_errors("chart", doc)
```

Replace:

```python
def validate_dashboard(doc: Any) -> dict:
    errors = _schema_errors("dashboard", doc)
```

with:

```python
def validate_dashboard(doc: Any) -> dict:
    depth = _depth_errors(doc)
    if depth:
        raise SchemaError(depth)
    errors = _schema_errors("dashboard", doc)
```

Replace:

```python
def validate_folder(doc: Any) -> dict:
    errors = _schema_errors("folder", doc)
```

with:

```python
def validate_folder(doc: Any) -> dict:
    depth = _depth_errors(doc)
    if depth:
        raise SchemaError(depth)
    errors = _schema_errors("folder", doc)
```

- [ ] **Step 4: Catch RecursionError in `viz/server/documents.py`**

Replace:

```python
    except (UnicodeDecodeError, json.JSONDecodeError) as err:
        raise SchemaError([f"$: invalid JSON ({err})"]) from err
```

with:

```python
    except (UnicodeDecodeError, json.JSONDecodeError) as err:
        raise SchemaError([f"$: invalid JSON ({err})"]) from err
    except RecursionError as err:
        raise SchemaError(["$: invalid JSON (nested too deeply)"]) from err
```

- [ ] **Step 5: Isolate each document in `viz/server/tree.py`**

Replace:

```python
    except (SchemaError, DocumentTooLarge) as err:
        return {"type": "chart", "id": chart_id, "error": str(err)}
```

with:

```python
    except (SchemaError, DocumentTooLarge) as err:
        return {"type": "chart", "id": chart_id, "error": str(err)}
    except Exception as err:  # noqa: BLE001 - one unreadable object must not take down the tree
        _log.warning("could not load chart %s: %r", chart_id, err)
        return {"type": "chart", "id": chart_id, "error": f"could not load ({type(err).__name__})"}
```

Replace:

```python
    except (SchemaError, DocumentTooLarge) as err:
        return {"type": "dashboard", "id": dashboard_id, "error": str(err)}
```

with:

```python
    except (SchemaError, DocumentTooLarge) as err:
        return {"type": "dashboard", "id": dashboard_id, "error": str(err)}
    except Exception as err:  # noqa: BLE001 - one unreadable object must not take down the tree
        _log.warning("could not load dashboard %s: %r", dashboard_id, err)
        return {"type": "dashboard", "id": dashboard_id, "error": f"could not load ({type(err).__name__})"}
```

Replace:

```python
        except (SchemaError, DocumentTooLarge) as err:
            node["error"] = str(err)
            continue
```

with:

```python
        except (SchemaError, DocumentTooLarge) as err:
            node["error"] = str(err)
            continue
        except Exception as err:  # noqa: BLE001 - one unreadable object must not take down the tree
            _log.warning("could not load folder metadata %s/%s: %r", kind, path, err)
            node["error"] = f"could not load ({type(err).__name__})"
            continue
```

- [ ] **Step 6: Catch RecursionError in `viz/publish/validate.py`**

Replace:

```python
    except (UnicodeDecodeError, json.JSONDecodeError) as err:
        return None, [f"{path.name}: invalid JSON ({err})"]
    return doc, []
```

with:

```python
    except (UnicodeDecodeError, json.JSONDecodeError) as err:
        return None, [f"{path.name}: invalid JSON ({err})"]
    except RecursionError:
        return None, [f"{path.name}: invalid JSON (nested too deeply)"]
    return doc, []
```

- [ ] **Step 7: Run the tests to see them pass**

Run: `.venv/Scripts/python -m pytest tests/server/test_tree_isolation.py -v`
Expected: 10 passed.

- [ ] **Step 8: Run the whole suite, then commit**

Run: `.venv/Scripts/python -m pytest`
Expected: all pass.

```bash
git add viz/schemas.py viz/server/documents.py viz/server/tree.py viz/publish/validate.py tests/server/test_tree_isolation.py
git -c user.name="tripp" -c user.email="dom4domg@gmail.com" commit -m "fix: cap document nesting and isolate each document in the tree" -m "Co-Authored-By: <model name from your harness> <noreply@anthropic.com>
Claude-Session: <session url from your harness>"
```

---

### Task 6: Health before the Host check (A29) and no testserver by default (A3)

**Files:**
- Modify: `viz/config.py`, `viz/server/middleware.py`, `viz/server/app.py`, `viz/server/routes.py`, `docs/work-setup.md`
- Test: Modify `tests/test_config.py`, `tests/server/conftest.py`, `tests/publish/conftest.py`, `tests/server/test_middleware.py`, `tests/publish/test_preview.py`

**Interfaces:**
- Consumes: `starlette.middleware.trustedhost.TrustedHostMiddleware`.
- Produces:
  - `Settings.allowed_hosts` default `"localhost,127.0.0.1"`.
  - `viz.server.middleware.HEALTH_PATH = "/api/health"`, `viz.server.middleware.HEALTH_METHODS = ("GET", "HEAD")`.
  - `viz.server.middleware.TrustedHostExceptHealth(app, allowed_hosts: list[str])`: a plain ASGI middleware. `GET /api/health` and `HEAD /api/health` skip the Host check; every other request (other paths, and any other method on `/api/health`) goes through `TrustedHostMiddleware`.
  - The health route answers both `GET` and `HEAD` (`@router.api_route("/health", methods=["GET", "HEAD"])`); before this task `HEAD /api/health` was 405.
  - Test fixtures: `tests/server/conftest.py::settings` sets `allowed_hosts="localhost,127.0.0.1,testserver"`; `tests/publish/conftest.py::env` sets `VIZ_ALLOWED_HOSTS=localhost,127.0.0.1,testserver`. Later plans' tests that build an app with other settings must allow `testserver` themselves.

- [ ] **Step 1: Write the failing tests and the fixture changes**

In `tests/test_config.py` replace:

```python
    assert s.allowed_hosts_list == ["localhost", "127.0.0.1", "testserver"]
```

with:

```python
    assert s.allowed_hosts_list == ["localhost", "127.0.0.1"]
```

In `tests/server/conftest.py` replace:

```python
    return Settings(storage="local", local_dir=bucket, root_prefix="viz/", tree_ttl_seconds=60,
                    web_dist=bucket / "no-web-dist")
```

with:

```python
    # "testserver" is the Host header FastAPI's TestClient sends. It is allowed here,
    # in tests only; the production default does not include it.
    return Settings(storage="local", local_dir=bucket, root_prefix="viz/", tree_ttl_seconds=60,
                    web_dist=bucket / "no-web-dist", allowed_hosts="localhost,127.0.0.1,testserver")
```

In `tests/publish/conftest.py` replace:

```python
    monkeypatch.setenv("VIZ_STAGING_DIR", str(staging_root))
```

with:

```python
    monkeypatch.setenv("VIZ_STAGING_DIR", str(staging_root))
    # "testserver" is the Host header FastAPI's TestClient sends; allowed in tests only.
    monkeypatch.setenv("VIZ_ALLOWED_HOSTS", "localhost,127.0.0.1,testserver")
```

In `tests/server/test_middleware.py` replace:

```python
from fastapi.testclient import TestClient

from viz.server.app import create_app
```

with:

```python
from fastapi.testclient import TestClient

from viz.config import Settings
from viz.server.app import create_app
```

Replace:

```python
def test_untrusted_host_is_rejected(settings):
    app = create_app(settings)
    with TestClient(app, base_url="http://evil.example") as c:
        r = c.get("/api/health")
    assert r.status_code == 400
```

with:

```python
def test_untrusted_host_is_rejected(settings):
    app = create_app(settings)
    with TestClient(app, base_url="http://evil.example") as c:
        r = c.get("/api/tree")
    assert r.status_code == 400


def test_health_is_answered_for_any_host(settings):
    # A load balancer health check sends the pod IP as Host (A29), with GET or HEAD.
    with TestClient(create_app(settings), base_url="http://10.1.2.3:8000") as c:
        r = c.get("/api/health")
        assert r.status_code == 200
        assert r.json() == {"status": "ok"}
        assert r.headers["content-security-policy"] == CSP
        head = c.head("/api/health")
        assert head.status_code == 200
        assert head.headers["content-security-policy"] == CSP
        assert c.get("/api/tree").status_code == 400
        assert c.get("/api/health/").status_code == 400
        assert c.get("/api/healthz").status_code == 400
        assert c.post("/api/health").status_code == 400
        assert c.get("/").status_code == 400


def test_head_health_is_answered_on_an_allowed_host(client):
    r = client.head("/api/health")
    assert r.status_code == 200
    assert r.content == b""


def test_default_allowed_hosts_do_not_include_the_test_client_host(bucket, monkeypatch):
    monkeypatch.delenv("VIZ_ALLOWED_HOSTS", raising=False)
    settings = Settings(storage="local", local_dir=bucket, web_dist=bucket / "no-web-dist")
    assert "testserver" not in settings.allowed_hosts_list
    assert TestClient(create_app(settings)).get("/api/tree").status_code == 400
    assert TestClient(create_app(settings), base_url="http://localhost").get("/api/tree").status_code == 200
```

Replace:

```python
def test_untrusted_host_response_still_has_security_headers(settings):
    app = create_app(settings)
    with TestClient(app, base_url="http://evil.example") as c:
        r = c.get("/api/health")
```

with:

```python
def test_untrusted_host_response_still_has_security_headers(settings):
    app = create_app(settings)
    with TestClient(app, base_url="http://evil.example") as c:
        r = c.get("/api/tree")
```

In `tests/publish/test_preview.py` replace:

```python
    client = TestClient(app, base_url="http://evil.example")
    assert client.get("/api/health").status_code == 400
```

with:

```python
    client = TestClient(app, base_url="http://evil.example")
    assert client.get("/api/tree").status_code == 400
```

- [ ] **Step 2: Run them to see them fail**

Run: `.venv/Scripts/python -m pytest tests/test_config.py tests/server/test_middleware.py -v`
Expected: `test_defaults` FAILS (the list still contains `testserver`), `test_health_is_answered_for_any_host` FAILS (`assert 400 == 200`), `test_head_health_is_answered_on_an_allowed_host` FAILS (`assert 405 == 200`: the route answers GET only), `test_default_allowed_hosts_do_not_include_the_test_client_host` FAILS.

- [ ] **Step 3: Change the default in `viz/config.py`**

Replace:

```python
    allowed_hosts: str = "localhost,127.0.0.1,testserver"
```

with:

```python
    allowed_hosts: str = "localhost,127.0.0.1"
```

- [ ] **Step 4: Add `TrustedHostExceptHealth` to `viz/server/middleware.py`**

Replace:

```python
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
```

with:

```python
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.requests import Request
from starlette.types import ASGIApp, Receive, Scope, Send

HEALTH_PATH = "/api/health"
# Load balancers and kubelet probes use GET; some load balancers use HEAD.
HEALTH_METHODS = ("GET", "HEAD")
```

Replace:

```python
class IdentityMiddleware(BaseHTTPMiddleware):
```

with:

```python
class TrustedHostExceptHealth:
    """The Host allow-list for every request except GET and HEAD /api/health.

    Load balancer health checks (for example an AWS ALB in IP mode) send the pod IP as
    the Host header, which is never in the allow-list. The health route returns a
    constant and reads nothing, so it is answered before the Host check. Every other
    path, including /api/health with any other method, goes through TrustedHostMiddleware.
    """

    def __init__(self, app: ASGIApp, allowed_hosts: list[str]):
        self.app = app
        self.checked = TrustedHostMiddleware(app, allowed_hosts=allowed_hosts)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if (scope["type"] == "http" and scope.get("method") in HEALTH_METHODS
                and scope.get("path") == HEALTH_PATH):
            await self.app(scope, receive, send)
            return
        await self.checked(scope, receive, send)


class IdentityMiddleware(BaseHTTPMiddleware):
```

- [ ] **Step 5: Use it in `viz/server/app.py`**

Replace:

```python
from fastapi import FastAPI
from starlette.middleware.trustedhost import TrustedHostMiddleware

from ..config import Settings
from ..storage import get_storage
from .middleware import IdentityMiddleware, SecurityHeadersMiddleware
```

with:

```python
from fastapi import FastAPI

from ..config import Settings
from ..storage import get_storage
from .middleware import IdentityMiddleware, SecurityHeadersMiddleware, TrustedHostExceptHealth
```

Replace:

```python
    # unhandled exception in the router.
    app.add_middleware(IdentityMiddleware, header=settings.auth_header)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.allowed_hosts_list)
```

with:

```python
    # unhandled exception in the router. The Host check skips GET and HEAD /api/health only.
    app.add_middleware(IdentityMiddleware, header=settings.auth_header)
    app.add_middleware(TrustedHostExceptHealth, allowed_hosts=settings.allowed_hosts_list)
```

- [ ] **Step 5b: Let the health route answer HEAD in `viz/server/routes.py`**

Replace:

```python
@router.get("/health")
def health():
```

with:

```python
@router.api_route("/health", methods=["GET", "HEAD"])
def health():
```

- [ ] **Step 6: Correct the default in `docs/work-setup.md`**

Replace:

```
| `VIZ_ALLOWED_HOSTS` | `localhost,127.0.0.1,testserver` | server | Host names the site answers to; anything else gets 400. Must be set in deployment |
```

with:

```
| `VIZ_ALLOWED_HOSTS` | `localhost,127.0.0.1` | server | Host names the site answers to; anything else gets 400, except `GET` and `HEAD /api/health` (load balancer checks send the pod IP). Must be set in deployment |
```

- [ ] **Step 7: Run the tests to see them pass**

Run: `.venv/Scripts/python -m pytest tests/test_config.py tests/server/test_middleware.py tests/publish/test_preview.py -v`
Expected: all pass.

- [ ] **Step 8: Run the whole suite, then commit**

Run: `.venv/Scripts/python -m pytest`
Expected: all pass. If a test elsewhere now gets 400, it builds an app whose settings do not allow `testserver`: allow it in that test's settings, never in `viz/config.py`.

```bash
git add viz/config.py viz/server/middleware.py viz/server/app.py viz/server/routes.py docs/work-setup.md tests/test_config.py tests/server/conftest.py tests/publish/conftest.py tests/server/test_middleware.py tests/publish/test_preview.py
git -c user.name="tripp" -c user.email="dom4domg@gmail.com" commit -m "fix: answer GET and HEAD /api/health before the Host check; drop testserver from default hosts" -m "Co-Authored-By: <model name from your harness> <noreply@anthropic.com>
Claude-Session: <session url from your harness>"
```

---

### Task 7: Identity gate, VIZ_REQUIRE_IDENTITY (B1)

**Files:**
- Modify: `viz/config.py`, `viz/server/middleware.py`, `viz/server/app.py`, `viz/publish/preview.py`, `docs/work-setup.md`
- Test: Create `tests/server/test_identity_gate.py`

**Interfaces:**
- Consumes: Task 6 `HEALTH_PATH`, `HEALTH_METHODS`; `Settings.auth_header`.
- Produces:
  - `Settings.require_identity: bool = False` (environment `VIZ_REQUIRE_IDENTITY`).
  - `viz.server.middleware.IdentityMiddleware(app, header: str, require: bool = False)`. The header value is stripped; empty counts as missing. With `require` on, every request except `GET /api/health` and `HEAD /api/health` without it gets 401 `{"detail": "identity header required"}` and an access-log line with `status=401`. `request.state.user` is the stripped value or None.
  - `viz.publish.preview.preview_settings(...)` always sets `require_identity=False`.
  - No docstring in `viz/` calls the middleware an "auth slot".

- [ ] **Step 1: Write the failing tests**

Create `tests/server/test_identity_gate.py`:

```python
"""B1: with VIZ_REQUIRE_IDENTITY on, requests without the SSO proxy's identity header get 401."""
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from viz.config import Settings
from viz.publish.preview import preview_settings
from viz.server.app import create_app
from viz.server.middleware import CSP

EMAIL = {"X-Forwarded-Email": "someone@example.com"}
VIZ_PACKAGE = Path(__file__).resolve().parents[2] / "viz"


@pytest.fixture
def gated(settings) -> TestClient:
    settings.require_identity = True
    return TestClient(create_app(settings))


def test_setting_defaults_to_off_and_reads_the_environment(monkeypatch):
    monkeypatch.delenv("VIZ_REQUIRE_IDENTITY", raising=False)
    assert Settings().require_identity is False
    monkeypatch.setenv("VIZ_REQUIRE_IDENTITY", "true")
    assert Settings().require_identity is True


def test_off_by_default_requests_without_identity_are_served(client):
    assert client.get("/api/tree").status_code == 200


def test_missing_identity_is_401(gated):
    r = gated.get("/api/tree")
    assert r.status_code == 401
    assert r.json() == {"detail": "identity header required"}
    assert r.headers["content-security-policy"] == CSP


@pytest.mark.parametrize("value", ["", "   "])
def test_empty_identity_is_401(gated, value):
    assert gated.get("/api/tree", headers={"X-Forwarded-Email": value}).status_code == 401


@pytest.mark.parametrize("path", [
    "/api/tree", "/api/charts/sales/revenue-by-region", "/api/dashboards/sales/overview",
    "/api/data/sales/revenue-by-region", "/", "/d/sales/overview", "/api/nothing",
])
def test_every_path_needs_identity(gated, path):
    assert gated.get(path).status_code == 401


def test_identity_present_is_served(gated):
    assert gated.get("/api/tree", headers=EMAIL).status_code == 200
    assert gated.get("/api/data/sales/revenue-by-region", headers=EMAIL).status_code == 200


def test_health_needs_no_identity(gated):
    r = gated.get("/api/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}
    assert gated.head("/api/health").status_code == 200


def test_other_methods_on_health_need_identity(gated):
    assert gated.post("/api/health").status_code == 401


def test_health_from_a_load_balancer_needs_neither_host_nor_identity(settings):
    settings.require_identity = True
    with TestClient(create_app(settings), base_url="http://10.1.2.3:8000") as c:
        assert c.get("/api/health").status_code == 200
        assert c.head("/api/health").status_code == 200


def test_the_header_name_is_the_auth_header_setting(settings):
    settings.require_identity = True
    settings.auth_header = "X-Auth-Request-Email"
    c = TestClient(create_app(settings))
    assert c.get("/api/tree", headers=EMAIL).status_code == 401
    assert c.get("/api/tree", headers={"X-Auth-Request-Email": "a@example.com"}).status_code == 200


def test_rejected_request_is_logged(gated, caplog):
    with caplog.at_level("INFO", logger="viz.access"):
        gated.get("/api/tree")
    assert any("user=-" in rec.getMessage() and "status=401" in rec.getMessage() for rec in caplog.records)


def test_preview_never_requires_identity(monkeypatch, tmp_path):
    monkeypatch.setenv("VIZ_REQUIRE_IDENTITY", "true")
    assert preview_settings(tmp_path).require_identity is False


def test_no_code_calls_the_identity_middleware_an_auth_slot():
    for path in sorted(VIZ_PACKAGE.rglob("*.py")):
        text = path.read_text(encoding="utf-8").lower()
        assert "auth slot" not in text, path
        assert "identity slot" not in text, path
        assert "nothing here enforces" not in text, path
```

- [ ] **Step 2: Run them to see them fail**

Run: `.venv/Scripts/python -m pytest tests/server/test_identity_gate.py -v`
Expected: most tests FAIL or ERROR (`test_other_methods_on_health_need_identity` among them): setting `settings.require_identity` raises `ValueError: "Settings" object has no field "require_identity"`, `Settings().require_identity` raises `AttributeError`, `test_preview_never_requires_identity` fails the same way, and `test_no_code_calls_the_identity_middleware_an_auth_slot` fails on `viz/server/middleware.py`. `test_off_by_default_requests_without_identity_are_served` passes.

- [ ] **Step 3: Add the setting to `viz/config.py`**

Replace:

```python
    auth_header: str = "X-Forwarded-Email"
```

with:

```python
    auth_header: str = "X-Forwarded-Email"
    # True in deployment (Helm sets it): every request except GET and HEAD /api/health
    # needs a non-empty auth_header, or gets 401. False for local development and viz preview.
    require_identity: bool = False
```

- [ ] **Step 4: Rewrite the identity middleware in `viz/server/middleware.py`**

Replace the module docstring:

```python
"""Security headers on every response, and the identity slot."""
```

with:

```python
"""Security headers on every response, the Host allow-list, and the identity header:
logged with every request and, when VIZ_REQUIRE_IDENTITY is on, required."""
```

Replace the whole `IdentityMiddleware` class, which is this text:

```python
class IdentityMiddleware(BaseHTTPMiddleware):
    """Reads the identity header set by an upstream SSO proxy. No-op without one.

    This is the auth slot: a real deployment puts the site behind a proxy that
    sets the header, and this middleware records it. Nothing here enforces.
    """

    def __init__(self, app, header: str):
        super().__init__(app)
        self.header = header

    async def dispatch(self, request: Request, call_next):
        user = request.headers.get(self.header) or None
        request.state.user = user
        started = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            elapsed_ms = (time.perf_counter() - started) * 1000
            access_log.info(
                "user=%s method=%s path=%s status=%s ms=%.1f",
                user or "-", request.method, request.url.path, 500, elapsed_ms,
            )
            raise
        elapsed_ms = (time.perf_counter() - started) * 1000
        access_log.info(
            "user=%s method=%s path=%s status=%s ms=%.1f",
            user or "-", request.method, request.url.path, response.status_code, elapsed_ms,
        )
        return response
```

with:

```python
def _log_access(user: str | None, request: Request, status: int, started: float) -> None:
    elapsed_ms = (time.perf_counter() - started) * 1000
    access_log.info(
        "user=%s method=%s path=%s status=%s ms=%.1f",
        user or "-", request.method, request.url.path, status, elapsed_ms,
    )


class IdentityMiddleware(BaseHTTPMiddleware):
    """Reads the identity header set by the SSO proxy in front of the site and logs it
    with every request (the viz.access log).

    When `require` is true (VIZ_REQUIRE_IDENTITY), a request without a non-empty identity
    header gets 401, except GET and HEAD /api/health. The header is trusted as-is: this
    only works behind a proxy that sets it and strips any value the client sent.
    """

    def __init__(self, app, header: str, require: bool = False):
        super().__init__(app)
        self.header = header
        self.require = require

    async def dispatch(self, request: Request, call_next):
        user = request.headers.get(self.header, "").strip() or None
        request.state.user = user
        started = time.perf_counter()
        is_health = request.method in HEALTH_METHODS and request.url.path == HEALTH_PATH
        if self.require and user is None and not is_health:
            _log_access(user, request, 401, started)
            return JSONResponse({"detail": "identity header required"}, status_code=401)
        try:
            response = await call_next(request)
        except Exception:
            _log_access(user, request, 500, started)
            raise
        _log_access(user, request, response.status_code, started)
        return response
```

- [ ] **Step 5: Pass the setting in `viz/server/app.py`**

Replace:

```python
    app.add_middleware(IdentityMiddleware, header=settings.auth_header)
```

with:

```python
    app.add_middleware(IdentityMiddleware, header=settings.auth_header, require=settings.require_identity)
```

- [ ] **Step 6: Keep preview open in `viz/publish/preview.py`**

Replace:

```python
    return Settings(storage="local", local_dir=Path(staging_root), root_prefix="", allowed_hosts=allowed,
                    host=host, port=port)
```

with:

```python
    return Settings(storage="local", local_dir=Path(staging_root), root_prefix="", allowed_hosts=allowed,
                    host=host, port=port, require_identity=False)
```

- [ ] **Step 7: Document the setting in `docs/work-setup.md`**

`tests/test_work_setup_doc.py::test_every_setting_is_documented` requires every `Settings` field in this table. Replace:

```
| `VIZ_AUTH_HEADER` | `X-Forwarded-Email` | server | Identity header from the SSO proxy (logged, not enforced) |
```

with:

```
| `VIZ_AUTH_HEADER` | `X-Forwarded-Email` | server | Identity header from the SSO proxy. Logged with every request; required when `VIZ_REQUIRE_IDENTITY` is true |
| `VIZ_REQUIRE_IDENTITY` | `false` | server | When `true`, every request except `GET` and `HEAD /api/health` without a non-empty `VIZ_AUTH_HEADER` gets 401. Turn it on in deployment, behind the SSO proxy |
```

- [ ] **Step 8: Run the tests to see them pass**

Run: `.venv/Scripts/python -m pytest tests/server/test_identity_gate.py tests/server/test_middleware.py tests/test_work_setup_doc.py -v`
Expected: all pass.

- [ ] **Step 9: Run the whole suite, then commit**

Run: `.venv/Scripts/python -m pytest`
Expected: all pass.

```bash
git add viz/config.py viz/server/middleware.py viz/server/app.py viz/publish/preview.py docs/work-setup.md tests/server/test_identity_gate.py
git -c user.name="tripp" -c user.email="dom4domg@gmail.com" commit -m "feat: VIZ_REQUIRE_IDENTITY rejects requests without the SSO identity header" -m "Co-Authored-By: <model name from your harness> <noreply@anthropic.com>
Claude-Session: <session url from your harness>"
```

---

### Task 8: viz-server writes the viz.access log (A2)

**Files:**
- Modify: `viz/server/__main__.py` (whole file)
- Test: Create `tests/server/test_logging.py`

**Interfaces:**
- Consumes: `uvicorn.config.LOGGING_CONFIG` (uvicorn 0.53 installed).
- Produces: `viz.server.__main__.log_config() -> dict`: a deep copy of uvicorn's config plus formatter `viz` (`%(asctime)s %(levelname)s %(name)s %(message)s`), handler `viz` (StreamHandler on stderr), logger `viz` at INFO with `propagate: False`. `main()` passes it as `uvicorn.run(..., log_config=log_config())`.

- [ ] **Step 1: Write the failing tests**

Create `tests/server/test_logging.py`:

```python
"""A2: viz-server must actually write the viz.access lines (user, method, path, status)."""
import subprocess
import sys

from viz.server import __main__ as server_main

# Runs in a fresh interpreter so the logging configuration does not leak into other tests.
SCRIPT = """
import logging.config
import sys
from fastapi.testclient import TestClient
from viz.config import Settings
from viz.server.__main__ import log_config
from viz.server.app import create_app

logging.config.dictConfig(log_config())
settings = Settings(storage="local", local_dir=sys.argv[1], web_dist=sys.argv[1], allowed_hosts="testserver")
client = TestClient(create_app(settings))
client.get("/api/health", headers={"X-Forwarded-Email": "someone@example.com"})
logging.getLogger("viz.server").debug("debug lines stay hidden")
"""


def test_log_config_sends_viz_to_stderr_at_info():
    config = server_main.log_config()
    assert config["loggers"]["viz"] == {"handlers": ["viz"], "level": "INFO", "propagate": False}
    assert config["handlers"]["viz"]["stream"] == "ext://sys.stderr"
    assert "uvicorn" in config["loggers"], "uvicorn's own loggers must stay configured"


def test_main_passes_the_log_config_to_uvicorn(monkeypatch):
    calls = []
    monkeypatch.setattr(server_main.uvicorn, "run", lambda *args, **kwargs: calls.append(kwargs))
    server_main.main()
    assert calls[0]["log_config"] == server_main.log_config()
    assert calls[0]["factory"] is True


def test_access_lines_are_written_when_configured(tmp_path):
    result = subprocess.run([sys.executable, "-c", SCRIPT, str(tmp_path)], capture_output=True, text=True,
                            timeout=120)
    assert result.returncode == 0, result.stderr
    access = [line for line in result.stderr.splitlines() if " viz.access " in line]
    assert len(access) == 1, result.stderr
    assert "INFO" in access[0]
    assert "user=someone@example.com method=GET path=/api/health status=200" in access[0]
    assert "debug lines stay hidden" not in result.stderr
```

- [ ] **Step 2: Run them to see them fail**

Run: `.venv/Scripts/python -m pytest tests/server/test_logging.py -v`
Expected: 3 FAILED: `AttributeError: module 'viz.server.__main__' has no attribute 'log_config'` (twice, the subprocess one via its stderr), and `KeyError: 'log_config'` for the `main()` test.

- [ ] **Step 3: Replace the whole of `viz/server/__main__.py`**

```python
"""Run the server: `python -m viz.server` or `viz-server`."""
import copy

import uvicorn
from uvicorn.config import LOGGING_CONFIG

from ..config import Settings

VIZ_LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s %(message)s"


def log_config() -> dict:
    """uvicorn's own logging config plus the `viz` logger at INFO on stderr.

    Without this the root logger stays at WARNING and the viz.access lines
    (user, method, path, status per request) are never written."""
    config = copy.deepcopy(LOGGING_CONFIG)
    config["formatters"]["viz"] = {"format": VIZ_LOG_FORMAT}
    config["handlers"]["viz"] = {"class": "logging.StreamHandler", "formatter": "viz", "stream": "ext://sys.stderr"}
    config["loggers"]["viz"] = {"handlers": ["viz"], "level": "INFO", "propagate": False}
    return config


def main() -> None:
    settings = Settings()
    uvicorn.run("viz.server.app:create_app", factory=True, host=settings.host, port=settings.port,
                log_config=log_config())


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run the tests to see them pass**

Run: `.venv/Scripts/python -m pytest tests/server/test_logging.py -v`
Expected: 3 passed.

- [ ] **Step 5: Run the whole suite, then commit**

Run: `.venv/Scripts/python -m pytest`
Expected: all pass.

```bash
git add viz/server/__main__.py tests/server/test_logging.py
git -c user.name="tripp" -c user.email="dom4domg@gmail.com" commit -m "fix: viz-server configures the viz logger so access lines are written" -m "Co-Authored-By: <model name from your harness> <noreply@anthropic.com>
Claude-Session: <session url from your harness>"
```

---

### Task 9: Ids with a charts/dashboards segment validate (A17); dashboards have no ancestor rule (A18)

**Files:**
- Modify: `viz/publish/validate.py`, `viz/server/tree.py`
- Test: Modify `tests/publish/test_validate.py`, `tests/server/test_tree.py`

**Interfaces:**
- Consumes: `validate_staged_chart`, `validate_dashboard_file`, `build_tree`.
- Produces:
  - `viz.publish.validate._id_from_path(path, kind, doc_id) -> str | None` (private; gained `doc_id`). When the path ends with `<kind>/<doc_id>` it returns `doc_id`; otherwise the id after the last `<kind>` directory, as before.
  - `build_tree` marks ancestor conflicts for charts only. Dashboard ids `a` and `a/b` both load normally.

- [ ] **Step 1: Write the failing tests**

Add at the end of `tests/publish/test_validate.py`:

```python


@pytest.mark.parametrize("chart_id", ["team/charts/revenue", "charts/revenue", "team/dashboards/revenue"])
def test_chart_id_with_a_charts_or_dashboards_segment_validates(settings, storage, staging_root, chart_id):
    staged = _staged(staging_root, chart_id=chart_id)
    assert validate_staged_chart(staged.dir, settings, storage) == []


@pytest.mark.parametrize("dashboard_id", ["team/dashboards/board", "dashboards/board", "team/charts/board"])
def test_dashboard_id_with_a_charts_or_dashboards_segment_validates(settings, storage, staging_root, dashboard_id):
    path = _write_dashboard(staging_root, _dashboard(dashboard_id=dashboard_id), name=dashboard_id)
    assert validate_dashboard_file(path, settings, storage) == []


def test_mismatch_under_a_charts_segment_still_reports_the_directory(settings, storage, staging_root):
    staged = _staged(staging_root, chart_id="team/charts/one")
    doc = dict(staged.doc)
    doc["id"] = "team/charts/two"
    _rewrite(staged, doc)
    errors = validate_staged_chart(staged.dir, settings, storage)
    assert "id: chart.json says 'team/charts/two' but the directory is 'one'" in errors
```

In `tests/server/test_tree.py` replace:

```python
def test_document_deleted_between_list_and_load_becomes_error_node(
```

with:

```python
def test_dashboard_ids_a_and_a_slash_b_coexist(storage, settings):
    doc = json.loads(storage.get("viz/dashboards/sales/overview.json"))
    doc["id"] = "sales"
    storage.put("viz/dashboards/sales.json", json.dumps(doc).encode(), "application/json")
    tree = build_tree(storage, settings)
    top = next(i for i in tree["dashboards"]["items"] if i["id"] == "sales")
    assert "error" not in top
    assert top["title"] == "Sales overview"
    child = next(i for i in _find_folder(tree["dashboards"], "sales")["items"] if i["id"] == "sales/overview")
    assert "error" not in child


def test_tree_accepts_ids_with_a_charts_segment(storage, settings):
    doc = json.loads(storage.get("viz/charts/sales/total-revenue/chart.json"))
    doc["id"] = "team/charts/revenue"
    storage.put("viz/charts/team/charts/revenue/chart.json", json.dumps(doc).encode(), "application/json")
    tree = build_tree(storage, settings)
    charts_folder = _find_folder(_find_folder(tree["charts"], "team"), "charts")
    node = charts_folder["items"][0]
    assert node["id"] == "team/charts/revenue"
    assert "error" not in node


def test_document_deleted_between_list_and_load_becomes_error_node(
```

- [ ] **Step 2: Run them to see them fail**

Run: `.venv/Scripts/python -m pytest tests/publish/test_validate.py tests/server/test_tree.py -v`
Expected: 5 FAILED: `test_chart_id_with_a_charts_or_dashboards_segment_validates[team/charts/revenue]` and `[charts/revenue]` (error `id: chart.json says 'team/charts/revenue' but the directory is 'revenue'`), `test_dashboard_id_with_a_charts_or_dashboards_segment_validates[team/dashboards/board]` and `[dashboards/board]`, and `test_dashboard_ids_a_and_a_slash_b_coexist` (`id conflicts with ...`). The other new tests already pass; they are regression guards.

- [ ] **Step 3: Fix `_id_from_path` in `viz/publish/validate.py`**

Replace:

```python
def _id_from_path(path: Path, kind: str) -> str | None:
    """The id implied by a path under a `charts` or `dashboards` directory, or None."""
    parts = list(Path(path).parts)
    if kind not in parts:
        return None
    tail = parts[len(parts) - parts[::-1].index(kind):]
    if kind == "dashboards" and tail and tail[-1].endswith(".json"):
        tail[-1] = tail[-1][:-5]
    return "/".join(tail) if tail else None
```

with:

```python
def _id_from_path(path: Path, kind: str, doc_id: str) -> str | None:
    """The id implied by a path under a `charts` or `dashboards` directory, or None.

    doc_id is the id the document declares. When the path ends with <kind>/<doc_id>,
    that is the answer, even if doc_id itself has a `charts` or `dashboards` segment
    (for example `team/charts/revenue`). Otherwise the id is everything after the
    last <kind> directory, which is what the error message reports."""
    parts = list(Path(path).parts)
    if kind == "dashboards" and parts and parts[-1].endswith(".json"):
        parts[-1] = parts[-1][:-5]
    id_parts = doc_id.split("/")
    n = len(id_parts)
    if len(parts) > n and parts[-n:] == id_parts and parts[-n - 1] == kind:
        return doc_id
    if kind not in parts:
        return None
    tail = parts[len(parts) - parts[::-1].index(kind):]
    return "/".join(tail) if tail else None
```

Replace:

```python
    implied = _id_from_path(chart_dir, "charts")
```

with:

```python
    implied = _id_from_path(chart_dir, "charts", doc["id"])
```

Replace:

```python
    implied = _id_from_path(path, "dashboards")
```

with:

```python
    implied = _id_from_path(path, "dashboards", doc["id"])
```

- [ ] **Step 4: Drop the dashboard conflict rule in `viz/server/tree.py`**

Replace:

```python
    charts = [_chart_node(storage, settings, cid) for cid in chart_ids]
    _mark_conflicts(charts)
    dashboards = [_dashboard_node(storage, settings, did) for did in dashboard_ids]
    _mark_conflicts(dashboards)
```

with:

```python
    charts = [_chart_node(storage, settings, cid) for cid in chart_ids]
    # Chart ids `a` and `a/b` conflict: charts/a/ would hold both a's files and the
    # folder of b. Dashboards have no such problem (dashboards/a.json and
    # dashboards/a/b.json are separate keys), so they get no conflict check.
    _mark_conflicts(charts)
    dashboards = [_dashboard_node(storage, settings, did) for did in dashboard_ids]
```

- [ ] **Step 5: Run the tests to see them pass**

Run: `.venv/Scripts/python -m pytest tests/publish/test_validate.py tests/server/test_tree.py -v`
Expected: all pass.

- [ ] **Step 6: Run the whole suite, then commit**

Run: `.venv/Scripts/python -m pytest`
Expected: all pass.

```bash
git add viz/publish/validate.py viz/server/tree.py tests/publish/test_validate.py tests/server/test_tree.py
git -c user.name="tripp" -c user.email="dom4domg@gmail.com" commit -m "fix: ids with a charts or dashboards segment validate; dashboards have no ancestor rule" -m "Co-Authored-By: <model name from your harness> <noreply@anthropic.com>
Claude-Session: <session url from your harness>"
```

---

### Task 10: One forbidden-key list for server and browser (A37)

**Files:**
- Modify: `schemas/chart.schema.json`, `tests/fixtures/valid/chart-vegalite.json`
- Test: Create `tests/test_forbidden_keys.py`

**Interfaces:**
- Consumes: `web/src/renderers/vegaLiteSanitize.ts` declares `const FORBIDDEN_KEYS = new Set([...])` with single-quoted strings (today: `'url', 'values', 'href', 'usermeta', 'datasets'`).
- Produces: the schema's `$defs.noForbiddenKeys` enum is exactly `["url", "values", "href", "usermeta", "datasets", "__proto__", "constructor", "prototype"]`. `tests/test_forbidden_keys.py` requires schema list == browser list plus the three prototype keys, and requires `viz.schemas.validate_chart` to reject every one of them nested in a spec.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_forbidden_keys.py`:

```python
"""A37: the spec keys the server rejects and the keys the browser sanitizer rejects are
one list. Plotly and ECharts are gone, so their keys are not in it."""
import copy
import json
import re
from pathlib import Path

import pytest

from viz import schemas

REPO = Path(__file__).resolve().parents[1]
SANITIZER = REPO / "web" / "src" / "renderers" / "vegaLiteSanitize.ts"
FIXTURE = REPO / "tests" / "fixtures" / "valid" / "chart-vegalite.json"
PROTOTYPE_KEYS = {"__proto__", "constructor", "prototype"}


def _browser_forbidden_keys() -> set[str]:
    text = SANITIZER.read_text(encoding="utf-8")
    match = re.search(r"const FORBIDDEN_KEYS = new Set\(\[(.*?)\]\)", text, re.DOTALL)
    assert match, "vegaLiteSanitize.ts must declare FORBIDDEN_KEYS as new Set([...])"
    return set(re.findall(r"'([^']+)'", match.group(1)))


def _schema_forbidden_keys() -> set[str]:
    schema = json.loads((REPO / "schemas" / "chart.schema.json").read_text(encoding="utf-8"))
    return set(schema["$defs"]["noForbiddenKeys"]["then"]["propertyNames"]["not"]["enum"])


def test_schema_list_is_the_browser_list_plus_prototype_keys():
    browser = _browser_forbidden_keys()
    assert browser, "no keys parsed from vegaLiteSanitize.ts"
    assert _schema_forbidden_keys() == browser | PROTOTYPE_KEYS


def test_no_plotly_or_echarts_keys_remain():
    leftovers = {"link", "sublink", "graphic", "extraCssText", "appendTo", "className", "images", "mapbox", "map"}
    assert not (_schema_forbidden_keys() & leftovers)


@pytest.mark.parametrize("key", sorted(_browser_forbidden_keys() | PROTOTYPE_KEYS))
def test_server_rejects_every_forbidden_key_at_depth(key):
    doc = json.loads(FIXTURE.read_text(encoding="utf-8"))
    doc = copy.deepcopy(doc)
    doc["spec"]["encoding"]["x"][key] = {"field": "month"}
    with pytest.raises(schemas.SchemaError) as excinfo:
        schemas.validate_chart(doc)
    assert key in str(excinfo.value)


def test_fixture_uses_the_vega_lite_v6_schema():
    doc = json.loads(FIXTURE.read_text(encoding="utf-8"))
    assert doc["spec"]["$schema"] == "https://vega.github.io/schema/vega-lite/v6.json"
```

- [ ] **Step 2: Run them to see them fail**

Run: `.venv/Scripts/python -m pytest tests/test_forbidden_keys.py -v`
Expected: 3 FAILED: `test_schema_list_is_the_browser_list_plus_prototype_keys` (the sets differ), `test_no_plotly_or_echarts_keys_remain`, `test_fixture_uses_the_vega_lite_v6_schema` (`v5.json`). The 8 parametrized `test_server_rejects_every_forbidden_key_at_depth` cases pass already.

- [ ] **Step 3: Replace the list in `schemas/chart.schema.json`**

Replace:

```
            "enum": ["url", "href", "usermeta", "datasets", "link", "sublink", "graphic", "extraCssText", "appendTo", "className", "images", "mapbox", "map", "__proto__", "constructor", "prototype"]
```

with:

```
            "enum": ["url", "values", "href", "usermeta", "datasets", "__proto__", "constructor", "prototype"]
```

- [ ] **Step 4: Fix the fixture's Vega-Lite version**

In `tests/fixtures/valid/chart-vegalite.json` replace:

```
vega-lite/v5.json
```

with:

```
vega-lite/v6.json
```

- [ ] **Step 5: Run the tests to see them pass**

Run: `.venv/Scripts/python -m pytest tests/test_forbidden_keys.py tests/test_schemas.py -v`
Expected: all pass.

- [ ] **Step 6: Run the whole suite, then commit**

Run: `.venv/Scripts/python -m pytest`
Expected: all pass.

```bash
git add schemas/chart.schema.json tests/fixtures/valid/chart-vegalite.json tests/test_forbidden_keys.py
git -c user.name="tripp" -c user.email="dom4domg@gmail.com" commit -m "fix: schema forbidden keys match the Vega-Lite sanitizer; fixture uses Vega-Lite v6" -m "Co-Authored-By: <model name from your harness> <noreply@anthropic.com>
Claude-Session: <session url from your harness>"
```

---

### Task 11: The design spec describes what 5a built, and records B3

**Files:**
- Modify: `docs/superpowers/specs/2026-09-22-viz-site-design.md`
- Test: Create `tests/test_spec_text.py`

**Interfaces:**
- Consumes: nothing in code.
- Produces: spec text for B1, B2, B3, A18, A29, A37; `tests/test_spec_text.py` pins it.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_spec_text.py`:

```python
"""The design spec must describe what plan 5a built (hardening decisions B1, B2, B3, A18, A29, A37)."""
from pathlib import Path

SPEC = Path(__file__).resolve().parents[1] / "docs" / "superpowers" / "specs" / "2026-09-22-viz-site-design.md"


def _text() -> str:
    return SPEC.read_text(encoding="utf-8")


def _section(heading: str) -> str:
    text = _text()
    start = text.index(heading)
    rest = text[start + len(heading):]
    ends = [i for i in (rest.find("\n### "), rest.find("\n## ")) if i != -1]
    return rest[: min(ends)] if ends else rest


def test_spec_describes_content_addressed_data_files():
    text = _text()
    assert "`data.file`" in text
    assert "data.<sha16>.json" in text
    assert "There is no `data.path` field" not in text
    assert "<chart-id>/data.json" not in text


def test_spec_describes_the_conditional_commit_point():
    layout = _section("### 4.1 Layout")
    assert "single commit point" in layout
    assert "If-None-Match" in layout and "If-Match" in layout


def test_spec_describes_the_identity_gate():
    text = _text()
    assert "VIZ_REQUIRE_IDENTITY" in _section("### 12.2 Server")
    assert "VIZ_REQUIRE_IDENTITY" in _section("### 5.1 Server")
    assert "auth middleware slot" not in text
    assert "middleware slot" not in text


def test_spec_exempts_health_from_the_host_check():
    assert "`GET /api/health` and `HEAD /api/health` are answered before the Host check" in _section("### 12.2 Server")


def test_spec_drops_the_dashboard_ancestor_rule():
    assert "Dashboard ids have no such rule" in _section("### 12.2 Server")


def test_spec_drops_the_retired_renderers_from_the_sanitizer_rules():
    front_end = _section("### 12.3 Front end")
    assert "ECharts:" not in front_end
    assert "Plotly:" not in front_end


def test_spec_records_the_refresher_sql_rule():
    refresher = _section("### 12.7 Constraints the v2 refresher spec must honour")
    assert "must never run bucket-supplied SQL under a shared service" in refresher
    assert "no broader than the original author's" in refresher
```

- [ ] **Step 2: Run them to see them fail**

Run: `.venv/Scripts/python -m pytest tests/test_spec_text.py -v`
Expected: 7 FAILED.

- [ ] **Step 3: Apply the spec edits**

All edits are in `docs/superpowers/specs/2026-09-22-viz-site-design.md`. Each is an Edit-tool replacement of the exact old text.

(a) Header. Replace:

```
Status: Draft for review
```

with:

```
Status: Draft for review
Amended: 2026-09-29 by `2026-09-29-hardening-decisions.md` (content-addressed
data files and conditional publish, identity gate, health check before the
Host check, the refresher SQL rule in 12.7). Where they disagree, that file wins.
```

(b) Section 1. Replace:

```
Users: a team inside a company VPC, reached only over VPN. No app-level auth in
v1. Developed and proven on a personal AWS account first.
```

with:

```
Users: a team inside a company VPC, reached only over VPN. No app-level login in
v1: the site sits behind the company SSO proxy and, with `VIZ_REQUIRE_IDENTITY`
on, refuses requests that arrive without the proxy's identity header. Developed
and proven on a personal AWS account first.
```

(c) Section 4.1 layout block. Replace:

```
    <chart-id>/data.json        small lane, or
    <chart-id>/data.parquet     large lane
```

with:

```
    <chart-id>/data.<sha16>.json      small lane, or
    <chart-id>/data.<sha16>.parquet   large lane (the name chart.json gives in data.file)
```

(d) Section 4.1 write order. Replace:

```
Writers publish the data file first, then chart.json, so a reader never sees a
spec whose data is missing.
```

with:

```
Data files are content-addressed: `<sha16>` is the first 16 hex characters of
the SHA-256 of the file's bytes, and chart.json names its file in `data.file`.
Writers publish in three steps: (1) PUT the data file under its hashed key
(the same bytes always give the same key); (2) PUT chart.json conditionally,
which is the single commit point: `If-None-Match: *` for a new chart,
`If-Match: <ETag read during the overwrite check>` for an overwrite; (3) delete
the chart's other `data.*` objects except the new file and the file the
replaced chart.json named, so a reader that already holds the old chart.json
can still fetch its data. A reader therefore sees the old chart or the new one,
never a chart.json whose data is missing or belongs to another version. A
failed condition means someone else changed the chart meanwhile; the publish
is refused and nothing the reader sees has changed. Dashboards use the same
conditional PUT.
```

(e) Section 4.2 example. Replace:

```
  "data": {
    "format": "json",
    "lane": "small",
    "rows": 1440,
```

with:

```
  "data": {
    "format": "json",
    "file": "data.3f9a0c1d2e4b5a69.json",
    "lane": "small",
    "rows": 1440,
```

(f) Section 4.2 field rules. Replace:

```
- There is no `data.path` field. The data key is derived from the id and
  `data.format`: `charts/<id>/data.json` or `charts/<id>/data.parquet`.
```

with:

```
- `data.file`: required. Matches `^data\.[0-9a-f]{16}\.(json|parquet)$`; the
  16 hex characters are the first 16 of the SHA-256 of the file's bytes and the
  extension equals `data.format`. The data key is `charts/<id>/<data.file>`.
  It is a file name, never a path. `schema_version` stays `1`.
```

(g) Section 5.1 routes table. Replace:

```
| `GET /api/data/{id}` | The data file, streamed,
```

with:

```
| `GET /api/data/{id}` | The data file that chart.json names in `data.file`, streamed,
```

(h) Section 5.1 configuration table. Replace:

```
| `VIZ_TREE_TTL_SECONDS` | tree cache TTL |
```

with:

```
| `VIZ_TREE_TTL_SECONDS` | tree cache TTL |
| `VIZ_ALLOWED_HOSTS` | host names the site answers to, default `localhost,127.0.0.1` |
| `VIZ_AUTH_HEADER` | identity header set by the SSO proxy, default `X-Forwarded-Email` |
| `VIZ_REQUIRE_IDENTITY` | `true`: every request except `GET` and `HEAD /api/health` without a non-empty identity header gets 401. Default `false`; Helm sets `true` |
```

(i) Section 6.2 staging directory. Replace:

```
Staging directory: `./.viz-staging/<chart-id>/` containing `chart.json` and the
data file, mirroring the bucket layout so publish is a copy.
```

with:

```
Staging directory: `./.viz-staging/charts/<chart-id>/` containing `chart.json`
and exactly one data file, already under its content-addressed name
(`data.<sha16>.json` or `.parquet`), mirroring the bucket layout so publish is
a copy.
```

(j) Section 6.2 validate row. Replace:

```
| `viz validate <staging dir or dashboard file>` | Schema validation, data file present, declared columns match the file,
```

with:

```
| `viz validate <staging dir or dashboard file>` | Schema validation, the file named by `data.file` present and its SHA-256 prefix matching its name, no other `data.*` file in the staged directory, declared columns match the file,
```

(k) Section 6.2 publish row. Replace:

```
| `viz publish <staging dir or dashboard file>` | Runs validate, then uploads data first and chart.json second. Refuses on any validation failure. |
```

with:

```
| `viz publish <staging dir or dashboard file>` | Runs validate, then the three steps in 4.1: data file, conditional chart.json, clean-up keeping one previous data file. Refuses on any validation failure, and when chart.json changed after the overwrite check. |
```

(l) Section 6.2 move row. Replace:

```
| `viz move <old-id> <new-id>` | Renames a chart or dashboard prefix in storage and rewrites references in every dashboard that pointed at it. |
```

with:

```
| `viz move <old-id> <new-id>` | Renames a chart or dashboard prefix in storage and rewrites references in every dashboard that pointed at it. Data files are copied under the same content-addressed name. |
```

(m) Section 11 seam. Replace:

```
- **One auth middleware slot** in front of the API routes, a no-op in v1.
```

with:

```
- **One identity middleware** in front of the API routes. It logs the SSO
  proxy's identity header with every request and, with `VIZ_REQUIRE_IDENTITY`
  on, rejects requests without it (401). It does no login and no permissions.
```

(n) Section 11 `viz.auth`. Replace:

```
  external portal, plugged into the middleware slot and the visibility rule.
```

with:

```
  external portal, plugged in next to the identity middleware and the
  visibility rule.
```

(o) Section 12.2 identity and Host bullets. Replace:

```
- The auth middleware slot reads identity headers from the company SSO proxy
  when present and logs them with every request. The deployment guide says to
  put the site behind that proxy.
- No CORS middleware. `TrustedHostMiddleware` with the internal hostnames.
```

with:

```
- The identity middleware reads the identity header (`VIZ_AUTH_HEADER`) set by
  the company SSO proxy and logs it with every request (`viz.access`, INFO,
  written to stderr by `viz-server`). With `VIZ_REQUIRE_IDENTITY=true`, the
  Helm default, every request except `GET` and `HEAD /api/health` without a
  non-empty header gets 401 `{"detail": "identity header required"}`. Local
  development, tests and `viz preview` leave it off. The header is trusted
  as-is, so the site must only be reachable through the proxy, which sets it
  and strips any client-sent value. The deployment guide says so.
- No CORS middleware. `TrustedHostMiddleware` with the internal hostnames.
  `GET /api/health` and `HEAD /api/health` are answered before the Host check,
  because load balancer health checks send the pod IP as Host; every other
  path, and any other method on `/api/health`, is checked.
```

(p) Section 12.2 data route. Replace:

```
- Data route: content type from `data.format` only, `Content-Disposition:
```

with:

```
- Data route: reads chart.json and streams `charts/<id>/<data.file>`. Content
  type from `data.format` only, `Content-Disposition:
```

(q) Section 12.2 ids. Replace:

```
- Ids: `a` and `a/b` cannot both exist; the server reports the conflict and
  `viz validate` rejects it. Ids are capped at 512 characters.
```

with:

```
- Chart ids: `a` and `a/b` cannot both exist, because `charts/a/` would hold
  both a's files and b's folder; the server reports the conflict and
  `viz validate` rejects it. Dashboard ids have no such rule:
  `dashboards/a.json` and `dashboards/a/b.json` are separate keys and coexist.
  An id may contain a `charts` or `dashboards` segment. Ids are capped at 512
  characters.
- Documents nested deeper than 64 levels are refused before schema validation.
  Any failure reading one document (bad JSON, too deep, storage error such as
  AccessDenied) turns that one node of the tree into an error node; the tree
  itself still loads.
```

(r) Section 12.3 sanitizer rules. Replace:

```
- Renderer adapters sanitize specs before mounting, and the same rules are
  encoded in `chart.schema.json` so the CLI rejects them at publish time.
  ECharts: force `renderMode: 'richText'` on every tooltip, delete `link`,
  `sublink`, `graphic`, `extraCssText`, `appendTo`, `className`, and any
  formatter containing `<`; strings are never turned into functions; canvas
  renderer. Vega-Lite: null loader, `actions: false`, canvas renderer,
  `vega-interpreter` (no `unsafe-eval`), reject `url`, `values`, `href`, image
  marks and `usermeta` at any depth. Plotly: cloud and editor buttons off,
  self-hosted topojson or geo traces rejected, `layout.images` and map layouts
  deleted, `<` escaped in data-derived text, column binding implemented as a
  strict walk that ignores `__proto__` and `constructor`.
```

with:

```
- Renderer adapters sanitize specs before mounting, and the same rules are
  encoded in `chart.schema.json` so the CLI rejects them at publish time.
  Vega-Lite won the bake-off; Plotly and ECharts are removed. Vega-Lite: null
  loader, `actions: false`, canvas renderer, `vega-interpreter` (no
  `unsafe-eval`), reject `url`, `values`, `href`, `usermeta`, `datasets` and
  image marks at any depth. The schema's forbidden-key list is exactly the
  browser sanitizer's list plus `__proto__`, `constructor` and `prototype`;
  a test keeps the two in step.
```

(s) Section 12.4 overwrite. Replace:

```
- `viz publish` refuses to overwrite an existing id without `--force`, and
  prints the existing author and `updated_at` first.
```

with:

```
- `viz publish` refuses to overwrite an existing id without `--force`, and
  prints the existing author and `updated_at` first. The check and the write
  are tied by the conditional PUT in 4.1: if the document changed after the
  check, publish refuses with "<id> changed since you checked it; run the
  command again".
```

(t) Section 12.7, decision B3. Replace:

```
whose hash it cannot verify. Tree metadata is untrusted input to any assistant
module.
```

with:

```
whose hash it cannot verify. Tree metadata is untrusted input to any assistant
module.

The refresher must never run bucket-supplied SQL under a shared service
principal. It may only run SQL whose hash was recorded at publish time by the
publisher, under an identity no broader than the original author's. (Decision
B3, 2026-09-29: anyone who can write chart.json could otherwise make a shared
principal run their SQL.) A refresh writes like a publish (section 4.1): a new
content-addressed data file, then a conditional PUT of chart.json.
```

- [ ] **Step 4: Run the tests to see them pass**

Run: `.venv/Scripts/python -m pytest tests/test_spec_text.py -v`
Expected: 7 passed.

- [ ] **Step 5: Run the whole suite, then commit**

Run: `.venv/Scripts/python -m pytest`
Expected: all pass.

```bash
git add docs/superpowers/specs/2026-09-22-viz-site-design.md tests/test_spec_text.py
git -c user.name="tripp" -c user.email="dom4domg@gmail.com" commit -m "docs: spec describes atomic publish, the identity gate and the refresher SQL rule" -m "Co-Authored-By: <model name from your harness> <noreply@anthropic.com>
Claude-Session: <session url from your harness>"
```

---

## Final checks (after Task 11, no commit)

1. `.venv/Scripts/python -m pytest` passes: all pass, 0 failed (a few tests are skipped: the Windows symlink test and the opt-in integration tests).
2. `export PATH="/c/Program Files/nodejs:$PATH"`, then from `web/`: `npm run typecheck` and `npm test` pass.
3. If Playwright's Chromium is installed, from `web/`: `npm run e2e` passes (it serves the regenerated sample bucket through the real `viz-server`). If it cannot run on this machine, say so in the report; CI runs it.
4. `git status --short` shows only files that were already modified or untracked before Task 1 (for example `.claude/sessions/SUMMARY.md`).
5. Manual smoke, optional: `.venv/Scripts/viz-server`, open http://127.0.0.1:8000/d/sales/overview, and check that the terminal prints `viz.access` lines.

---

## Interfaces for later plans (5b, 5c, 5d)

Exact final state after this plan. Later plans build on these; do not change them without updating this list.

**Storage (`viz/storage`)**
- `PreconditionFailed(Exception)`: in `viz.storage.base`, re-exported as `viz.storage.PreconditionFailed`.
- `put(key: str, data: bytes, content_type: str, *, if_match: str | None = None, if_none_match: bool = False) -> None` on `Storage`, `LocalStorage`, `S3Storage`. Failed condition: `PreconditionFailed`. Both conditions: `ValueError`. S3: `IfNoneMatch="*"`, `IfMatch='"<etag>"'`; 412, 409 `ConditionalRequestConflict`, and 404 under `if_match` all become `PreconditionFailed`.
- `head(key: str) -> ObjectInfo` (unchanged type; `.etag` unquoted; local backend: hex MD5 of the bytes). Raises `NotFound`. There is no `head(key) -> str`; use `head(key).etag` (the decisions file says the same).
- `pyproject.toml`: `boto3>=1.35.69`.

**Ids and contract (`viz/ids.py`, `schemas/chart.schema.json`)**
- `DATA_FILE_PATTERN = re.compile(r"^data\.[0-9a-f]{16}\.(json|parquet)$")`
- `data_file_name(sha256_hex: str, fmt: str) -> str` returns `data.<sha256_hex[:16]>.<fmt>`.
- `data_key(root: str, chart_id: str, file_name: str) -> str` returns `<root>charts/<chart_id>/<file_name>`; `ValueError` for any other name.
- chart.json `data.file` required; extension equals `data.format`. Schema forbidden keys: `url, values, href, usermeta, datasets, __proto__, constructor, prototype`.
- `viz.schemas.MAX_NESTING_DEPTH = 64`, `nesting_depth_exceeds(doc, limit=64) -> bool`.

**Publisher (`viz/publish`)**
- `staging.file_sha256(path) -> str`; `staging.PARQUET_TMP_NAME = "parquet.tmp"`; `staging.HASH_CHUNK = 1048576`.
- `staging.skeleton(chart_id, columns, fmt, file_name, lane, rows, nbytes, author, now, source=None) -> dict`.
- `staging.write_staged_chart(table, chart_id, staging_root, *, author, now, source=None) -> StagedChart` (unchanged signature); `StagedChart.data_path` is the hashed file; the directory holds no other `data.*` file.
- `validate.validate_staged_chart(chart_dir, settings, storage, allow_row_level=False) -> list[str]` and `validate.validate_dashboard_file(path, settings, storage) -> list[str]` (unchanged signatures). New error texts: `"<file>: not found"`, `"data.file: '<file>' does not match the file's SHA-256; it should be named '<expected>'"`, `"data: the staged directory holds other data files (<names>); keep only '<file>'"`. `validate.read_document(path)` also returns `"<name>: invalid JSON (nested too deeply)"`.
- `validate._id_from_path(path, kind, doc_id) -> str | None` (private, gained `doc_id`).
- `publish.PublishRefused(errors: list[str])`; `publish.publish_chart(chart_dir, settings, storage, force=False, allow_row_level=False, out=None) -> str`; `publish.publish_dashboard(path, settings, storage, force=False, out=None) -> str`. Still prints `published: <id>` (5b A13 changes the message).
- Private helpers 5b will touch: `_existing(storage, key) -> tuple[dict | None, str | None]` (document, ETag; `head` before `get`); `_guard_overwrite(storage, key, force, out) -> tuple[dict | None, str | None]` (refusal text still says `pass --force to overwrite`; 5b A14 rewords it); `_commit(storage, key, payload, doc_id, etag)` (refusal text `"<id> changed since you checked it; run the command again"`); `_named_data_file(doc) -> str | None`; `_delete_other_data_files(storage, root, chart_id, keep: set[str])`. For A20 (keep `created_at`) use the `existing` document `_guard_overwrite` returns; for A25 (pulled version) pass the pulled ETag into `_commit`. Keep the ETag flowing into `_commit`.
- Exact text of the two publish functions after this plan (5b anchors on it):
  - in `publish_chart`: `    existing, etag = _guard_overwrite(storage, key, force, out)`, then a blank line, then `    storage.put(data_key(root, chart_id, file_name), (chart_dir / file_name).read_bytes(), MEDIA_TYPES[fmt])`, then `    _commit(storage, key, (chart_dir / "chart.json").read_bytes(), chart_id, etag)`, ..., `    print(f"published: {chart_id}", file=out)`.
  - in `publish_dashboard`: `    _existing_doc, etag = _guard_overwrite(storage, key, force, out)`, `    _commit(storage, key, path.read_bytes(), dashboard_id, etag)`, `    print(f"published: {dashboard_id}", file=out)`, `    return dashboard_id`.
- `validate.py` imports after this plan: `from ..ids import chart_key, data_file_name, is_ancestor` and `from .staging import LARGE_MAX_BYTES, SMALL_MAX_BYTES, SMALL_MAX_ROWS, file_sha256`. The author check (`_check_chart_author`, `check_author`) is unchanged.
- `move.py` is unchanged: it copies every direct file under the old prefix, so data files keep their names. Its PUTs stay unconditional in this round (decided by the lead; deferred like the section C items). No later plan changes that.
- `preview.preview_settings(...)` sets `require_identity=False` (its `return Settings(...)` line gains `require_identity=False`; the lines above it are unchanged).
- `viz/publish/cli.py` is not changed by this plan.

**Settings (`viz/config.py`)**
- `allowed_hosts: str = "localhost,127.0.0.1"` (no `testserver`).
- `auth_header: str = "X-Forwarded-Email"` (unchanged).
- `require_identity: bool = False` (env `VIZ_REQUIRE_IDENTITY`). 5d: Helm `values.yaml` sets it `true` and `deployment.yaml` passes `VIZ_REQUIRE_IDENTITY`; `docs/work-setup.md` already has the row.

**Server (`viz/server`)**
- `middleware.HEALTH_PATH = "/api/health"`, `middleware.HEALTH_METHODS = ("GET", "HEAD")`.
- The health route answers `GET` and `HEAD` (`@router.api_route("/health", methods=["GET", "HEAD"])` in `routes.py`).
- `middleware.TrustedHostExceptHealth(app, allowed_hosts: list[str])`: only `GET` and `HEAD /api/health` skip the Host check. 5d: probes and ALB health checks may send any Host.
- `middleware.IdentityMiddleware(app, header: str, require: bool = False)`: 401 `{"detail": "identity header required"}` without a non-empty header when `require`; `GET` and `HEAD /api/health` exempt.
- Middleware order, outermost first: `SecurityHeadersMiddleware`, `TrustedHostExceptHealth`, `IdentityMiddleware`, routes. (5c adds `CompressionMiddleware` outside all of them.)
- `app.py` import line after this plan: `from .middleware import IdentityMiddleware, SecurityHeadersMiddleware, TrustedHostExceptHealth`; the last `add_middleware` call is still `app.add_middleware(SecurityHeadersMiddleware)`.
- `__main__.log_config() -> dict`; `viz-server` logs `viz.*` at INFO to stderr, format `%(asctime)s %(levelname)s %(name)s %(message)s`.
- `/api/data/{id}` streams `charts/<id>/<data.file>`; URL unchanged; `Content-Disposition: attachment; filename="data.<format>"` unchanged.
- Tree error node for an unreadable document: `{"type", "id", "error": "could not load (<ExceptionClassName>)"}`. Dashboards never get a conflict error.

**Front end (`web/src/api/types.ts`, for 5c)**
```ts
export interface ChartData {
  format: 'json' | 'parquet';
  file: string;
  lane: 'small' | 'large';
  rows: number;
  bytes: number;
  columns: Column[];
}
```
- `tests/test_forbidden_keys.py` parses `const FORBIDDEN_KEYS = new Set([...])` (single-quoted strings) from `web/src/renderers/vegaLiteSanitize.ts`. If a later plan adds a key to that set, it must add the same key to the schema enum, and the server must reject it (the test checks both). Keep the declaration in that form or update the test's regex. Plan 5c does not add to that set: it keeps the A5 generators (`sequence`, `graticule`, `sphere`) in a separate `DATA_GENERATORS` set and the nested-`data` and `bind.element` rules as their own checks, and mirrors all three in `viz/schemas.py::_check_vegalite`, so the schema enum and this test are unchanged.
- Design spec section 12.3 after this plan: the sanitizer bullet is exactly the text of edit (r) in Task 11. Plan 5c anchors on it.

**Tests**
- `tests/server/conftest.py::settings` and `tests/publish/conftest.py::env` allow `testserver`. Any new test that builds an app from other settings must allow it too.

**Left for later plans on purpose**
- 5b: `skills/publish-viz/references/data.md` still names `data.json` / `data.parquet`; the skill should say the data file is content-addressed and must never be edited or renamed by hand (restage instead) (5b Task 8 does it). CLI wording (A13, A14), `created_at` (A20), pulled version (A25, ETag sidecar), `move --kind` (A26).
- 5d: Helm env `VIZ_REQUIRE_IDENTITY=true`, README and NOTES.txt auth and health wording, IAM and bucket policy (the publisher needs `s3:DeleteObject` for the clean-up step), the rest of `docs/work-setup.md`.
