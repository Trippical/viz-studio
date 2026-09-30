# Session handoff — viz-site

Updated: 2026-09-30
Log folder: .claude/sessions/logs/ — detailed per-session logs. Read only when a specific question isn't answered here.
Latest log: .claude/sessions/logs/2026-09-30-hardening-branch.md

## Current objective

Ship the hardening pass. Branch `hardening` (head 5187b41, 69 commits ahead of `main`) holds plans 5a-5d (docs/superpowers/plans/2026-09-29-plan-5*.md), a whole-branch review with fixes, and fixes from five adopter role-plays. Every task and fix round was reviewed; locally pytest 653 passed/4 skipped, vitest 190, typecheck, build, Playwright 7/7. Docker, Helm render checks and gitleaks have NOT run on this branch: CI runs only on pushes to main and on PRs.

Next concrete steps: (1) with the user's OK, `git push origin hardening` (never force), open a PR hardening→main in the GitHub web UI (no gh CLI), watch all 5 CI jobs; fix failures without weakening checks. (2) Merge on the user's word; then delete `.superpowers/sdd/*` workspaces. (3) User follows docs/work-setup.md at work.

Decisions made, do not relitigate: identity gate on in Helm (VIZ_REQUIRE_IDENTITY); atomic publish via content-addressed data files + conditional chart.json PUT; publish/move need explicit VIZ_STORAGE (and VIZ_LOCAL_DIR for local); Databricks author only when host+token+warehouse present; rate limit on by default; phone layout and dark mode out of scope; `viz move` stays non-conditional this round. Deferred minors are listed in the latest log.

## Last session summary

Pushed main (CI green on first run). Five blind critics reconstructed the design intent correctly and found ~38 issues (docs/superpowers/specs/2026-09-29-hardening-findings.md); user chose identity gate + atomic publish. Four plans were written, reconciled and executed task by task with reviews (ledgers in git-ignored .superpowers/sdd/). Final review added 3 fixes. Five adopter role-plays (operator, analyst, Haiku-follows-skill, red team, viewer) found real problems — NaN/overflow numbers killing the tree, deep keys, silent publish into ./sample-bucket, AWS_REGION vs AWS_DEFAULT_REGION, forgeable identity header without source restrictions, stat tiles clipping at 200% zoom — all fixed and reviewed. Nothing is known broken.

## Recent sessions

- 2026-09-30 hardening-branch — blind critics, plans 5a-5d executed, final review, adopter fixes (logs/2026-09-30-hardening-branch.md)
- 2026-09-28 vega-lite-skill-and-work-ready — Vega-Lite picked; Plan 3b skill and Plan 4 work-ready built and merged (logs/2026-09-28-vega-lite-skill-and-work-ready.md)
- 2026-09-24 plans-2-and-3a-built-and-merged — CLI and front end built, reviewed and merged; bake-off dashboards viewable (logs/2026-09-24-plans-2-and-3a-built-and-merged.md)
- 2026-09-22 plan-1-design-and-build — designed viz-site, security review, Plan 1 built, reviewed and merged (logs/2026-09-22-plan-1-design-and-build.md)
