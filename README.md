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

Design: `docs/superpowers/specs/2026-09-22-viz-site-design.md`.
