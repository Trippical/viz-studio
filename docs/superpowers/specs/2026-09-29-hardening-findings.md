# Hardening findings, 2026-09-29

Source: five independent critics (security, architecture/contract, publisher
workflow, viewer, operations). Each read the code and user-facing docs only,
never the spec, plans or session logs, and wrote down the intent it inferred
before critiquing. "Confirmed" means the lead re-checked the code; "critic"
means the critic verified it; "suspected" means nobody ran it.

## Intent reconstruction

All five recovered the core intent with high confidence: replace Databricks
dashboards; bucket is the database; read-only server with no warehouse
credentials; publishing only through the CLI and skill; everything in the
bucket is hostile; folders and filters are not permissions; `author` is
attribution; refresher deferred to v2.

Where the repo misled them (these are clarity bugs, fix them):

1. Schema forbidden-key list still names Plotly/ECharts keys
   (`chart.schema.json:108`), so readers infer a multi-renderer design.
2. `ChartPage` prints "Refreshable from Databricks SQL, schedule ..." although
   nothing refreshes; readers assume data is current.
3. `author` wording (`identity.py:1`, `dashboards.md:110`) reads like an
   identity check; `VIZ_AUTHOR` makes it free text.
4. IdentityMiddleware is called "the auth slot" and Helm assumes an SSO proxy
   it neither deploys nor checks for; readers assume auth exists.
5. Helm `NOTES.txt` says S3/IRSA failure keeps pods unready; `/api/health`
   never touches S3.
6. `index.html` has a mobile viewport meta while phone layout is out of scope.
7. README promises "any viewer can download the data file"; the UI has no link.
8. CLI defaults (local storage in `./sample-bucket`) say "dev tool" while the
   skill presents it as the production publisher.

Note: the known item "Vega adapter mounts empty then inserts rows" was not
found by the viewer critic; re-check before working on it.

## A. Bugs and gaps to fix (no design decision needed)

Server
- A1 (confirmed, critic reproduced) One chart.json of deeply nested arrays
  raises RecursionError in `documents._read`; `tree._chart_node` does not
  catch it; `/api/tree` 500s until the object is deleted. Same for any S3
  ClientError (e.g. AccessDenied from a foreign KMS key). Catch per document,
  mark the node errored, cap nesting depth.
- A2 (confirmed) Access/identity log `viz.access` is never emitted in
  production: no logging config in `viz/server/__main__.py`, uvicorn leaves
  root at WARNING.
- A3 (critic) `allowed_hosts` default includes `testserver`; move it to tests.

Front end
- A4 (confirmed) Browser DuckDB lockdown lacks `SET enable_external_access=false`
  (`web/src/data/duckdb.ts:12-17`); Python lockdown has it.
- A5 (confirmed top-level-only check; runtime suspected) Nested
  `layer[i].data: {"sequence": ...}` bypasses the sanitizer and can freeze the
  tab. Reject `data` below top level and `sequence`/`graticule`/`sphere`.
- A6 (suspected) Vega tooltip `image` key renders an `<img src>` from an
  expression; use a text-only tooltip formatter. Reject `params[].bind.element`.
- A7 (confirmed) Select controls get no options from large-lane charts
  (`ChartTile.tsx:77` never calls `onRows`); deep-linked values dropped.
- A8 (critic) Deep-linked select values lost if the user edits a control before
  all tiles load.
- A9 (critic) No empty state when filters leave 0 rows; no badge on tiles that
  ignore an active control.
- A10 (critic) No data download link or `aria-label` on tiles.
- A11 (critic) No compression or immutable cache on static assets (34 MB wasm).
- A12 (critic) `ChartPage` fetches the chart twice; `-` select value collides
  with CLEARED marker.

CLI and skill
- A13 (critic reproduced) `viz publish` with `VIZ_STORAGE` unset writes to
  `./sample-bucket` and exits 0. Refuse implicit local storage for
  publish/move; print bucket and key on success.
- A14 (critic) Refusal messages say "pass --force / --allow-row-level / --yes";
  skill step 5 says fix every error and rerun. Messages must say "ask the user".
- A15 (critic) Skill forbids editing `renderer`, which stat tiles need.
- A16 (critic) `--sql @query.sql` fails in PowerShell; add `--sql-file`.
- A17 (critic) Ids containing a `charts`/`dashboards` segment stage but never
  validate.
- A18 (critic) Dashboard ancestor-conflict rule differs between validate and
  tree.
- A19 (critic) Charts stamp the Databricks login, dashboards use
  `resolve_author`; unify.
- A20 (critic) `created_at` resets on republish; keep it.
- A21 (critic) PII regex `name` matches `product_name`; tighten.
- A22 (critic) Placeholder aggregate `SELECT * FROM data LIMIT 1000` passes.
- A23 (critic) `viz preview --host 0.0.0.0` sets allowed hosts to `*`.
- A24 (critic) Install hint says `pip install viz-site[databricks]`; not on PyPI.
- A25 (critic) `pull-dashboard` then `publish --force` can clobber a
  colleague's edit; record the pulled `updated_at` and refuse on mismatch.
- A26 (critic) `move` cannot target a dashboard whose id is also a chart id;
  add `--kind`.

Deploy, CI, docs
- A27 (confirmed) CI docker smoke passes via SPA fallback; assert
  `application/wasm` and smoke against a mounted sample bucket.
- A28 (critic) CI helm negative check passes on any failure; grep the message.
- A29 (suspected) ALB health checks send the IP as Host and get 400; exempt
  `/api/health` from TrustedHost or document the annotation.
- A30 (critic) ALB path lacks `target-type: ip`, HTTPS listener, certificate.
- A31 (critic) Helm fullname `viz-site-viz-site`; ServiceAccount name ignores
  release.
- A32 (critic) NodeLocal DNSCache needs a template edit; add `dnsCidrs`.
- A33 (critic) No PDB, preStop, grace period; liveness equals readiness.
- A34 (critic) NOTES.txt health claim (see intent item 5).
- A35 (critic) work-setup: namespace chosen after IRSA trust needs it; no
  S3 VPC endpoint step; dead "Author on S3" cross-reference; smoke test writes
  into the production prefix.
- A36 (critic) nginx rate limit keyed on client IP collapses behind the SSO
  proxy.
- A37 Leftover Plotly/ECharts keys in schema; fixture says Vega-Lite v5.
- A38 (critic) Bucket policy restricts reads only; add Deny on Put/Delete for
  principals other than the publisher role.

## B. Decisions (user, 2026-09-29)

B1 yes (default on in Helm, off in local dev). B2 yes (change the contract
now). B3 record in the spec. Execution: a plan in docs/superpowers/plans,
executed by subagents on a `hardening` branch, reviewed, merged on the user's
word.

- B1 Fail-closed identity: `VIZ_REQUIRE_IDENTITY` returning 401 without the
  proxy header, default on in Helm. Consistent with spec (no app auth, proxy
  in front) but changes behaviour.
- B2 Atomic publish: data under a content-addressed key named in chart.json,
  chart.json PUT as the commit point, S3 conditional PUTs for the overwrite
  guard. Contract change; cheapest before real data exists.
- B3 Refresher v2 must not run bucket-supplied SQL under a shared service
  principal. Record the rule in the spec now; no code.

## C. Deferred (team scale makes these acceptable for v1)

- Tree rebuild GETs every document every 60 s per pod; ETag cache later.
- Path-as-id with no stable opaque id; `move` has no rollback or lock.
- Schema evolution: validator dispatch by `schema_version`, CLI/server
  version handshake.
- Hand-written TS types; generate from schemas later.
- Shared publisher role; per-team roles later.
- Dark mode, colour-blind palette, SVG renderer for accessibility.
- Pinned image digests and a Python lock file.
