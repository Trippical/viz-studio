# 2026-09-28/29: Vega-Lite picked, Plan 3b (skill) and Plan 4 (work-ready) built and merged

## Goal
Resume from the bake-off handoff, get the renderer decision from the user, then build the rest of v1: the publish-viz skill (Plan 3b) and everything needed to run viz-site on the user's work machine (Plan 4).

## What happened, with reasons

### Bake-off
- User was on mobile. Screenshots of the three bake-off dashboards were taken with Playwright and sent via SendUserFile; later also posted to the user's Discord through the baseball_wiggum `user` webhook (user chose it; posting used a stdlib multipart script, no URL printed).
- Vega-Lite screenshots were nearly empty: real bug. vega-embed injects `.vega-embed { position: relative }`, same specificity as `.tile-mount { position:absolute; inset:0 }` and later in the cascade, so every Vega-Lite mount collapsed to 21px. Fix: selector `.tile-body > .tile-mount` (b890ec3). The smoke test only checked `toBeVisible()`, which passes at 21px; added an assertion that each chart mount fills >60% of its tile.
- Published two artifacts for the user: renderer comparison (https://claude.ai/artifact/1v6MKjyf852LYCRFpz1n6V) and interactive network-graph/gauge examples (https://claude.ai/artifact/6wswkytAsnwangRCm1Chw5). Key finding: ECharts' extras (sankey, treemap, gauge, markLine) are blocked by our no-inline-data rule; Plotly needs more BOUND_KEYS.
- User asked about keeping all three renderers: advised against (triple security surface, three authoring guides). User picked Vega-Lite; fallback paths recorded in the scorecard (site-owned tiles like `stat`; full Vega specs, already bundled; restore from git).
- Removed Plotly/ECharts: adapters, sanitizers, tests, samples, dashboards, npm deps, Python checks, enum values (0d416aa, merged 46129e7).

### Plan 3b (publish-viz skill)
- Plan: docs/superpowers/plans/2026-09-28-plan-3b-publish-viz-skill.md. All ten Vega-Lite example specs were compiled with vega-lite before execution (no warnings).
- Found while planning: skeleton `$schema` was v5; `viz query` stamps the Databricks user but `viz validate` checked VIZ_AUTHOR (fixed properly in Plan 4).
- Executed subagent-driven on branch plan-3b: 7 tasks + a controller dry run. Findings fixed: axis format `","` prints 4.5e+4 (d3-scale tickFormat fills precision when no type letter; guide now requires a type letter, test enforces); faceted charts don't resize after late data injection (examples use `autosize: {type: pad, resize: true}`; adapter root cause parked); final review found the large-lane placeholder aggregate `SELECT * FROM data LIMIT 1000` kept by agents, a stat compare example showing orders as dollars, install-skill safety. Dry run: a fresh agent using only the skill published a chart + dashboard first try; its 5 unclear points were clarified.
- Merged 9b57d6c; main pushed to GitHub (455da6c) after a secret scan of the unpushed history (only test dummies; a handoff line naming another private project was removed).

### Scope decisions from the user
- The deliverable is the public repo Trippical/viz-studio cloned onto the user's WORK machine; real AWS/Databricks exist only there (saved to memory).
- Phone/narrow layout is out of scope (saved to memory).
- Author rule: option (b), implemented as a Databricks `current_user()` lookup during validate when DATABRICKS_HOST/TOKEN are set (stricter than blindly accepting the stamp; keeps spec 12.4).
- At work Databricks is reached with a service principal (PAT works; OAuth M2M not supported), and data will mostly be files dropped in S3 (copy down, then `viz stage --from`; `s3://` staging not supported).

### Plan 4 (work-machine ready)
- Plan: docs/superpowers/plans/2026-09-28-plan-4-work-ready.md. Executed subagent-driven on branch plan-4, 7 tasks.
- Review findings fixed: KMS key policy + break-glass notes; Helm egress guidance was wrong for S3 gateway endpoints (no IP) and STS, empty egressCidrs failed open (now `fail`s, CI proves it), AWS_STS_REGIONAL_ENDPOINTS=regional; gitleaks needs `pull-requests: read`; guide lacked AWS region, had `docker push` with no image, missed the 123456789012 placeholder, S3 test prefix join. Final review (opus): service-principal integration test asserted `@`; guide used AWS before creating it; file-staged author mismatch under assumed-role session names; egress default not a placeholder; ALB traffic dropped by NetworkPolicy (added `ingressCidrs`); prefix-conditioned ListBucket likely turns 404 into 403 (ListBucket now unconditioned on the dedicated bucket, integration test probes it); CI docker smoke run added.
- Merged into main as 8149efd (2026-09-29). Not pushed: main is 15 commits ahead of origin/main.

## Files created/changed (main ones)
- web/src/styles.css, web/e2e/smoke.spec.ts; removal of web/src/renderers/{plotly*,echarts*}.ts, sample-bucket bakeoff plotly/echarts, viz/schemas.py checks.
- skills/publish-viz/{SKILL.md,references/*.md,examples/*.json}; viz/publish/{dashboards.py,skill.py,cli.py,staging.py}; sample-bucket/generate.py + sample-bucket/viz/{charts,dashboards}/examples; tests/test_skill.py, tests/publish/test_dashboards.py, tests/publish/test_skill_install.py.
- viz/publish/{query.py,validate.py}; viz/refresh/; Dockerfile, .dockerignore, docker-compose.yml; deploy/aws/*; deploy/helm/viz-site/**; .github/workflows/ci.yml; docs/work-setup.md; tests/deploy/*, tests/refresh/*, tests/storage/test_s3_integration.py, tests/publish/test_validate_author.py, tests/test_work_setup_doc.py; pyproject.toml (viz-refresh script, pyyaml dev, skill force-include).
- docs/superpowers/specs/2026-09-22-bake-off-scorecard.md (decision), README.md, CLAUDE.md.

## Dead ends
- `docker`, `helm`, `gh` are not installed on this machine; nothing container/chart/CI was executed here.
- Guard hook blocks `$(...)`, backticks and redirects outside the project (e.g. /dev/null, the scratchpad); write scripts with the Write tool and run them.
- A dispatch that deleted by regex cut too much from viz/schemas.py once (restored from HEAD, re-applied with an anchored cut).

## Open threads / parked
- Push main and check the FIRST CI run (docker build, helm lint/template, gitleaks entropy rules are all unproven).
- Hardening list: CI duckdb smoke check passes via SPA fallback (check Content-Type/size); Vega adapter mounts empty then inserts rows (autosize workaround); OAuth M2M for service principals; `viz stage --from s3://`; skill tests are substring checks; install-skill on a dangling symlink; NodeLocal DNSCache egress; Helm fullname `viz-site-viz-site`; SA name ignores release; probes under the VPC CNI policy agent unverified; fixture chart-vegalite.json says v5; guide cross-reference to a nonexistent "Author on S3" heading; items in the 2026-09-24 log.
- User's work-machine checklist: docs/work-setup.md steps 5-7 (create AWS resources, run the two opt-in integration tests, deploy).

## Test state (main at 8149efd)
pytest 370 passed, 3 skipped (opt-in integration tests + Windows symlink); vitest 140; tsc clean; build ok; Playwright 4/4 (bake-off vega-lite, single chart page, missing dashboard, examples gallery).
