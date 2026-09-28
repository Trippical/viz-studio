# Session handoff — viz-site

Updated: 2026-09-28
Log folder: .claude/sessions/logs/ — detailed per-session logs. Read only when a specific question isn't answered here.
Latest log: .claude/sessions/logs/2026-09-24-plans-2-and-3a-built-and-merged.md

## Current objective

Plan 3b (the `publish-viz` skill + Vega-Lite authoring guide) is BUILT on branch `plan-3b` (tip fb5c879, 11 commits over main 2fdbf65), reviewed per task, whole-branch reviewed (opus, "with fixes"), fix wave re-reviewed clean. MERGED into `main` as 9b57d6c (branches plan-3b and vega-lite-only deleted). `main` is never pushed without the user saying so. Final verification on fb5c879: pytest 315 passed 2 skipped; vitest 140; tsc clean; build ok; Playwright 4/4 (includes the new gallery test).

What 3b added: `skills/publish-viz/` (SKILL.md, references/vega-lite.md, dashboards.md, data.md, 11 examples/*.json), published by `sample-bucket/generate.py` as `/d/examples/gallery`; `viz new-dashboard`, `viz pull-dashboard`, `viz install-skill` (default `~/.claude/skills/publish-viz`, packaged in the wheel as `viz/_skills/publish-viz`); skeleton `$schema` v6; `tests/test_skill.py` ties the skill text to the parser and files. Dry run: a fresh agent given only the skill published a chart + dashboard first try; its 5 unclear points were fixed (2e6b3bf).

Open items for the user: (a) KNOWN DEFECT, not fixed by design: `viz query` stamps the Databricks user as author but `viz validate` checks `VIZ_AUTHOR`/STS/local, so query-staged charts fail validation unless `VIZ_AUTHOR` equals the Databricks login; the skill teaches that workaround; the real fix changes the Plan 3a author ruling, so it is the user's call. (b) Genie Code skill discovery path is UNCONFIRMED; `viz install-skill --dest DIR` covers any path.

Next concrete steps, in order: (1) the user chooses between the hardening pass and Plan 4 first; origin/main is still at 919070a (Plan 1), push only when the user says; (2) hardening pass, seeded with: 2026-09-24 log parked items; phone-width grid (12 columns at 390px, stat value clips); Vega adapter mounts empty then inserts rows, forcing the `autosize` workaround on faceted charts (fix in `web/src/renderers/vegaLite.ts`); the author defect above; skill tests are substring checks; install-skill on a dangling symlink gives a generic error; `tests/fixtures/valid/chart-vegalite.json` still says v5; (3) Plan 4 (Dockerfile, Helm, CI) with its carry-forwards.

Decisions already made, do not relitigate: Vega-Lite is the only chart renderer; the 2026-09-24 log's rulings (spec 12.3 amendments, staging layout, author order); Plan 3b's three amendments (install-skill instead of a committed copy; new/pull-dashboard; Genie path unconfirmed).

## Last session summary

2026-09-28: fixed a CSS collision that collapsed Vega-Lite tiles to 21px (b890ec3), sent the bake-off screenshots to the user's phone and to Discord, published a renderer comparison (https://claude.ai/artifact/1v6MKjyf852LYCRFpz1n6V) and network-graph/gauge examples (https://claude.ai/artifact/6wswkytAsnwangRCm1Chw5). The user picked Vega-Lite; Plotly and ECharts were removed and merged (46129e7). Wrote Plan 3b and executed it subagent-driven on `plan-3b`: 7 tasks + controller dry run, one task fix round (axis format `","` printed 4.5e+4 on axes; guide now requires a type letter), one final fix wave (large-lane aggregate placeholder, stat compare formatting, install-skill safety, wording).

## Recent sessions

- 2026-09-24 plans-2-and-3a-built-and-merged — CLI and front end built, reviewed and merged; bake-off dashboards viewable (logs/2026-09-24-plans-2-and-3a-built-and-merged.md)
- 2026-09-22 plan-1-design-and-build — designed viz-site, security review, Plan 1 built, reviewed and merged (logs/2026-09-22-plan-1-design-and-build.md)
