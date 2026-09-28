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

Service principal: if the principal has a personal access token, put it in
`DATABRICKS_TOKEN` and everything works; `viz query` and `viz validate` both
see the principal's id, so charts are authored by the principal rather than
a person. OAuth machine-to-machine credentials (a client id and secret) are
not supported yet.

Files dropped in S3: `viz stage --from` reads a local file, so copy the file
down first (`aws s3 cp s3://your-drop-bucket/path/rows.parquet .`) and stage
the copy. Staging straight from an `s3://` path is not supported yet.

## 3. Try it locally

With Docker:

```
docker compose up --build
```

Then open http://127.0.0.1:8000. It serves the synthetic `sample-bucket`,
including the chart gallery at `/d/examples/gallery`.

Running the image without compose, set the storage yourself: `VIZ_STORAGE`,
`VIZ_LOCAL_DIR` (or `VIZ_S3_BUCKET`) and `VIZ_ALLOWED_HOSTS`. With none set,
the site starts but shows an empty tree.

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
