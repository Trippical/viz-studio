# Session handoff — viz-site

Updated: 2026-09-29
Log folder: .claude/sessions/logs/ — detailed per-session logs. Read only when a specific question isn't answered here.
Latest log: .claude/sessions/logs/2026-09-28-vega-lite-skill-and-work-ready.md

## Current objective

v1 is built: Plans 1, 2, 3a, 3b and 4 are merged into `main`. The deliverable is the public repo Trippical/viz-studio, which the user clones onto their WORK machine; real AWS (S3, IAM, EKS) and Databricks (service principal) exist only there. `main` is ahead of `origin/main` (455da6c) and is pushed only when the user says so.

Next concrete steps: (1) with the user's OK, `git push origin main`, then check the first GitHub Actions run (`.github/workflows/ci.yml`: python, web, docker build + smoke run, helm lint/template, gitleaks) — Docker, Helm and CI have never run anywhere; fix whatever it surfaces. (2) Hardening pass, list in the latest log ("Open threads"), notably the CI duckdb check that passes via the SPA fallback and the Vega adapter's mount-empty-then-insert behaviour. (3) The user follows `docs/work-setup.md` at work (create AWS resources, run the opt-in Databricks and S3 tests, deploy with Helm).

Decisions made, do not relitigate: Vega-Lite is the only renderer; phone/narrow layout is out of scope; `viz validate` confirms the Databricks login via `current_user()` when DATABRICKS_HOST/TOKEN are set, else VIZ_AUTHOR; s3:ListBucket is unconditioned on the dedicated bucket (404 vs 403); OAuth M2M service-principal auth and `viz stage --from s3://` are not supported yet (follow-ups); Genie Code skill path is unconfirmed (`viz install-skill --dest`).

## Last session summary

Fixed a CSS collision that collapsed Vega-Lite tiles to 21px, sent bake-off screenshots to the user's phone and Discord, and published a renderer comparison. The user picked Vega-Lite; Plotly and ECharts were removed. Plan 3b built the publish-viz skill (`skills/publish-viz/`), an 11-chart example gallery (`/d/examples/gallery`), and `viz new-dashboard`/`pull-dashboard`/`install-skill`; a fresh agent dry-ran the skill successfully. Plan 4 added the Databricks author check, `viz-refresh` scaffold, Dockerfile/compose, `deploy/aws/`, `deploy/helm/viz-site`, CI, the opt-in S3 test and `docs/work-setup.md`. Reviews caught and fixed wrong egress design for S3 gateway endpoints, a fail-open empty egress list, guide gaps (region, AWS setup order, author under assumed roles) and a likely S3 403-vs-404 policy trap. Tests on main: pytest 370 passed 3 skipped, vitest 140, Playwright 4/4. Nothing is broken locally.

## Recent sessions

- 2026-09-28 vega-lite-skill-and-work-ready — Vega-Lite picked; Plan 3b skill and Plan 4 work-ready built and merged (logs/2026-09-28-vega-lite-skill-and-work-ready.md)
- 2026-09-24 plans-2-and-3a-built-and-merged — CLI and front end built, reviewed and merged; bake-off dashboards viewable (logs/2026-09-24-plans-2-and-3a-built-and-merged.md)
- 2026-09-22 plan-1-design-and-build — designed viz-site, security review, Plan 1 built, reviewed and merged (logs/2026-09-22-plan-1-design-and-build.md)
