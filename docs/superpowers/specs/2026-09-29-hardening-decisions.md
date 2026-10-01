# Hardening decisions, 2026-09-29

Binding design for the hardening plans 5a-5d. Findings and their ids (A1..A38,
B1..B3) are in `2026-09-29-hardening-findings.md`. Where this file and the
2026-09-22 design spec disagree, this file wins; plan 5a updates the spec to
match.

## Plan split and order

Executed in this order, one after another, on the branch `hardening`:

- 5a `2026-09-29-plan-5a-contract-and-server.md`: B2 atomic publish end to end,
  B1 identity gate, A1, A2, A3, A17, A18, A29, A37, B3 spec text, the "auth
  slot" wording in server docstrings.
- 5b `2026-09-29-plan-5b-publisher.md`: A13-A16, A19-A26, and the "author is
  attribution" wording in CLI, skill and docs.
- 5c `2026-09-29-plan-5c-viewer.md`: A4-A12, the misleading refresh text on
  the chart page, and a check of whether the Vega adapter really mounts empty
  then inserts rows (fix only if it does).
- 5d `2026-09-29-plan-5d-deploy-ci-docs.md`: A27, A28, A30-A36, A38, Helm and
  docs for B1, README auth wording, NOTES.txt.

Out of scope everywhere: phone or narrow layout, dark mode, section C items.

## B2: atomic publish (content-addressed data file)

1. chart.json `data` gains a required field `file`: a string matching
   `^data\.[0-9a-f]{16}\.(json|parquet)$`. The 16 hex characters are the first
   16 of the SHA-256 of the data file's bytes. The extension equals
   `data.format`. `schema_version` stays `1` (nothing real is published yet).
2. Bucket key of the data file: `<root>/charts/<id>/<data.file>`.
   `viz.ids.data_key(root, chart_id, file_name)` takes the file name, not the
   format.
3. Staging: `viz stage` and `viz query` write the data file under its hashed
   name inside the staged chart directory and set `data.file`. `viz validate`
   fails when the file named by `data.file` is missing, when its SHA-256
   prefix does not match its name, or when any other `data.*` file is present
   in the staged directory.
4. Publish order: (a) PUT the data file under its hashed key (idempotent: the
   same bytes give the same key); (b) PUT chart.json conditionally, which is
   the single commit point: new chart -> `if_none_match=True`; overwrite ->
   `if_match=<etag read during the overwrite guard>`; (c) delete every
   `data.*` object under `<root>/charts/<id>/` except the new file and the
   file named by the chart.json that was just replaced (one previous
   generation is kept so a reader holding the old chart.json can still fetch
   its data).
5. A failed precondition raises `PublishRefused(["<id> changed since you
   checked it; run the command again"])`. Dashboards use the same conditional
   PUT.
6. Storage interface: `put(key, data, content_type, *, if_match: str | None =
   None, if_none_match: bool = False)` raises `viz.storage.PreconditionFailed`
   on a failed condition. `head(key)` keeps its existing return type,
   `ObjectInfo(key, size, etag, last_modified)`, because the server's size
   check and data route use it; callers read the ETag as `head(key).etag`
   (unquoted). It still raises `NotFound`. S3 backend passes `IfMatch` / `IfNoneMatch='*'` to
   `put_object` and maps HTTP 412 (and 409 ConditionalRequestConflict) to
   `PreconditionFailed`. Local backend computes the ETag as the hex MD5 of the
   file bytes and checks the condition under a process-wide lock.
7. Server `/api/data/<id>` reads chart.json and streams `data.file`. The URL
   the front end uses does not change. `viz move` copies the data file under
   the same name.
8. The sample bucket and every test fixture are regenerated or updated to the
   new layout.

## B1: identity gate

- Setting `VIZ_REQUIRE_IDENTITY` (bool, default false). When true, every
  request except `GET /api/health` and `HEAD /api/health` without a
  non-empty identity header gets 401 with body
  `{"detail": "identity header required"}`. The header name is the existing
  identity-header setting.
- Helm `values.yaml` sets it to `true`; local dev, `viz preview` and tests
  leave it false.

## A29: health check and TrustedHost

`GET /api/health` and `HEAD /api/health` are answered before the TrustedHost
check, so a load balancer that sends the pod IP as Host gets 200 with either
method. The health route accepts both methods. Every other path, and any other
method on `/api/health`, keeps the Host check.

## B3: refresher rule (spec text only)

The v2 refresher must never run bucket-supplied SQL under a shared service
principal. It may only run SQL whose hash was recorded at publish time by the
publisher, under an identity no broader than the original author's. Plan 5a
adds this to spec section 12.7.

## Clarifications by the lead (2026-09-29, after the plans were drafted)

- Storage: see B2.6. There is no `head(key) -> str`; every plan uses
  `head(key).etag`.
- Author rule (5b, A19): every command stamps the Databricks login only when
  `DATABRICKS_HOST`, `DATABRICKS_TOKEN` and `DATABRICKS_WAREHOUSE_ID` are all
  set; otherwise it uses the existing `resolve_author` (VIZ_AUTHOR, then the
  AWS caller identity, then `<user>@local`). No command newly requires
  `DATABRICKS_WAREHOUSE_ID`. `viz validate` applies the same rule. For a chart
  staged by `viz query`, the warehouse recorded in `source.warehouse_id` (the
  one `--warehouse` or `DATABRICKS_WAREHOUSE_ID` gave the query) counts as the
  third variable, so a query run with `--warehouse` still validates.
- `viz preview --allowed-hosts '*'` is accepted as explicit consent (5b, A23).
- Integration tests (`VIZ_INTEGRATION=1`) are run one file at a time, never
  with the whole suite: with that variable set, the unit-test fixtures keep
  the real `DATABRICKS_*` variables.
- Compression (5c, A11): gzip never applies to `.wasm` files, to anything
  under `/duckdb/`, or to `/api/data/`. The "Data as of" footer shows on stat
  tiles too.
- Sanitizer rules (5c, A4-A6) are recorded in design spec section 12.3 by plan
  5c: `data` only at the top level, `sequence`/`graticule`/`sphere` rejected,
  text-only tooltips, `bind.element` rejected, DuckDB `allowed_directories`
  plus `enable_external_access=false`.
- Bucket policy (5d, A38): the write Deny covers `s3:PutObject`,
  `s3:DeleteObject` and `s3:DeleteObjectVersion`.
- `viz move` keeps unconditional PUTs in this round (deferred, like the other
  section C items). No plan makes them conditional.
