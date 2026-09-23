# viz-site

A self-hosted viewer over a folder in an object store. Agents and people publish
charts and dashboards into that folder through a paved path; the site only reads.

## Trust assumptions, read these first

- Publishing a chart or dashboard means sharing it with every person who can
  reach the site. There are no per-object permissions.
- Folders are organization, not permission.
- Dashboard filters are a view, not a restriction. Any viewer can download a
  chart's full data file.
- Everything in the bucket is treated as untrusted content: the site sanitizes
  what it renders and never runs SQL against a warehouse.

## Development

    python -m venv .venv && . .venv/Scripts/activate   # or .venv/bin/activate
    pip install -e ".[dev]"
    python -m pytest
    viz-server                                          # serves ./sample-bucket on 127.0.0.1:8000

## Publishing (the paved path)

    viz stage --from rows.csv --id sales/emea/revenue   # stage a csv, json or parquet file
    viz query --sql @q.sql --id sales/emea/revenue      # run SQL on Databricks and stage the result
    viz validate .viz-staging/charts/sales/emea/revenue # schema, data file, columns, author, id conflicts
    viz preview                                         # serve ./.viz-staging on 127.0.0.1:8000
    viz publish .viz-staging/charts/sales/emea/revenue  # validate, then upload (data first, then chart.json)
    viz publish .viz-staging/dashboards/sales/board.json
    viz move sales/emea/revenue sales/emea/revenue-monthly --yes

The staging directory `./.viz-staging` mirrors the bucket, so `viz preview` is
the real server pointed at it. `viz query` needs `pip install "viz-site[databricks]"`
and `DATABRICKS_HOST`, `DATABRICKS_TOKEN`, `DATABRICKS_WAREHOUSE_ID`; nothing
else in the package reads them. Publisher settings: `VIZ_AUTHOR` (the stamped
author when no Databricks user or AWS identity applies), `VIZ_QUERY_DENY`
(comma-separated catalogs or `catalog.schema` that `viz query` refuses),
`VIZ_PII_PATTERN`, `VIZ_STAGING_DIR`. `--force` and `--yes` are flags only.

Design: `docs/superpowers/specs/2026-09-22-viz-site-design.md`.
