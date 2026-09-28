# Session handoff — viz-site

Updated: 2026-09-28
Log folder: .claude/sessions/logs/ — detailed per-session logs. Read only when a specific question isn't answered here.
Latest log: .claude/sessions/logs/2026-09-24-plans-2-and-3a-built-and-merged.md

## Current objective

Plan 4 ("work-machine ready") is BUILT on branch `plan-4` (tip after 45dbf5c plus this handoff), reviewed per task and whole-branch (opus, "with fixes"; one fix wave, re-review clean). Merge awaits the user. `main` (99aab29 locally; origin/main at 455da6c) is pushed only when the user says so. Final verification on plan-4: pytest 370 passed 3 skipped; vitest 140; Playwright 4/4. Docker and Helm are not installed here: the Dockerfile, chart and CI workflow have never run; the first GitHub Actions run after the push is their real test (check it).

The deliverable is the public repo Trippical/viz-studio, cloned onto the user's WORK machine; real AWS and Databricks exist only there. The user's guide is `docs/work-setup.md` (install, every setting, local try, skill install, create AWS resources, opt-in real-infra tests, deploy, troubleshooting). At work Databricks is reached with a service principal (PAT works; OAuth M2M client id/secret NOT supported yet) and data will mostly be files dropped in S3 (`viz stage --from` needs a local copy; staging from `s3://` NOT supported yet). Phone/narrow layout is out of scope (user, 2026-09-28).

Plan 4 added: `viz validate` confirms the Databricks login for `viz query` charts (author option b, verified against Databricks); `viz-refresh` scaffold; Dockerfile (Node build stage + Python, uid 10001), `.dockerignore`, `docker-compose.yml`; `deploy/aws/` IAM + bucket policy + README (ListBucket unconditioned on the dedicated bucket so missing keys 404); `deploy/helm/viz-site` (IRSA, locked-down pod, probes send an allowed Host, egress fails closed, optional ingressCidrs for ALB); `.github/workflows/ci.yml` (python, web, docker build + smoke run, helm lint/template + empty-egress must fail, gitleaks); opt-in `tests/storage/test_s3_integration.py`; PyYAML in the dev extra.

Next concrete steps, in order: (1) user decides the merge of `plan-4`; then push and check the first CI run; (2) hardening pass, seeded with: CI duckdb smoke check passes via SPA fallback (check Content-Type); Vega adapter mounts empty then inserts rows (autosize workaround on faceted charts); OAuth M2M for service principals; `viz stage --from s3://`; skill tests are substring checks; install-skill on a dangling symlink; NodeLocal DNSCache; Helm fullname doubling; 2026-09-24 log parked items; (3) the user runs the work-setup checklist at work.

Decisions already made, do not relitigate: Vega-Lite only; the 2026-09-24 log rulings; Plan 3b amendments; Plan 4 decisions (author option b via Databricks lookup, phone out of scope, work machine is the target).

## Last session summary

2026-09-28: fixed the Vega-Lite 21px tile bug, the user picked Vega-Lite (Plotly/ECharts removed), Plan 3b (publish-viz skill, Vega-Lite guide, example gallery, new-dashboard/pull-dashboard/install-skill) built, reviewed, dry-run by a fresh agent and merged; main pushed to GitHub (455da6c). Plan 4 written and executed subagent-driven on `plan-4`: fix rounds caught a wrong egress design for S3 gateway endpoints, a fail-open empty egress list, gitleaks PR permissions, missing AWS region/docker push/placeholder steps in the guide, and (final review) a service-principal test assertion, AWS setup ordering, author mismatch on assumed-role ARNs, ALB ingress, and ListBucket 403-vs-404.

## Recent sessions

- 2026-09-24 plans-2-and-3a-built-and-merged — CLI and front end built, reviewed and merged; bake-off dashboards viewable (logs/2026-09-24-plans-2-and-3a-built-and-merged.md)
- 2026-09-22 plan-1-design-and-build — designed viz-site, security review, Plan 1 built, reviewed and merged (logs/2026-09-22-plan-1-design-and-build.md)
