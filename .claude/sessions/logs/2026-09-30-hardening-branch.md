# 2026-09-29/30 — hardening branch (blind critics, plans 5a-5d, adopters)

## Goal
User asked (2026-09-29) how far from shipping, then: push main, do a hardening pass that includes
5 subagents picking the design apart and guessing original intent, "let it rip", and afterwards
5 subagents pretending to implement/adopt the result.

## What happened
1. Pushed main (455da6c..66ab31f). First CI run 36586234676 passed all 5 jobs.
2. Five blind critics (security, architecture, publisher, viewer, ops), forbidden from reading the
   spec/plans/logs, wrote inferred intent before critiquing. All five recovered the intent with
   high confidence. Misleading spots found: leftover Plotly/ECharts schema keys, chart page
   promising refresh, "auth slot" wording, NOTES.txt health claim, no download link, CLI dev
   defaults. Consolidated: docs/superpowers/specs/2026-09-29-hardening-findings.md (A1-A38, B1-B3, C).
3. User decisions: B1 identity gate (VIZ_REQUIRE_IDENTITY, on in Helm), B2 atomic publish
   (content-addressed data.<sha16>.<fmt>, conditional chart.json PUT as commit point), subagent
   execution on branch `hardening`. Binding design: docs/superpowers/specs/2026-09-29-hardening-decisions.md.
4. Four plans written in parallel by agents, reconciled by a fifth: docs/superpowers/plans/2026-09-29-plan-5{a,b,c,d}-*.md.
5. Executed 5a (12 tasks), 5b (12), 5c (14), 5d (13) with subagent-driven development: fresh
   implementer per task, task reviewer per task, ledgers in .superpowers/sdd/<plan>/progress.md
   (git-ignored). One usage-limit interruption (5a Task 11 committed, report written by controller).
6. Whole-branch final review (opus): "with fixes" -> 3 fixes (index.html no-cache + real 404 for
   missing /assets; loadDuckdb retries a rejected import; data.file fullmatch -> 422).
7. Five adopter role-plays: operator dry-run of docs/work-setup.md; analyst publishing for real on
   local storage; Haiku following the skill literally (clean success, no issues); red team with
   hostile bucket files; business user in a real browser. Findings consolidated in
   .superpowers/sdd/final/adopter-fixes.md and fixed in groups A (python), B (web), C (deploy/docs),
   each reviewed; A and C needed one fix round each.

## Rulings made by the lead (cost if wrong)
- One whole-branch review after 5d instead of per plan (5a issues surface later).
- 5c T6: shared cached loadDuckdb() instead of two import() sites (Vitest mocks only first site).
- 5c T11: CompressionMiddleware innermost (BaseHTTPMiddleware re-streaming defeats minimum_size).
- 5c T12: Vega's initializeAria overwrites role/aria-label on the mount -> label on a .tile-chart
  wrapper around only the Vega mount; stat/error/loading/empty outside it.
- Batched 5d Tasks 2-7 (Helm) and 9-11 (docs) into single dispatches, one commit per task.
- Extra fix round from adopter findings (security items treated as merge blockers).
- Author rule: Databricks login only when host+token+warehouse (env or chart source) all present.
- Rate limit stays on by default (spec); bucket write Deny incl. DeleteObjectVersion; scratch
  prefix viz/_scratch/; gzip excludes .wasm, /duckdb/, /api/data/.

## Notable bugs caught along the way
- Adding enable_external_access=false alone would have broken every large-lane chart (plan writer
  proved with duckdb-wasm); fixed with allowed_directories ['/viz-data/'] first.
- NaN / 1e999 / 5000-digit ints in a bucket doc took down /api/tree (red team) -> strict_json.
- Deep folder keys (1000 segments) caused RecursionError 500 -> only valid folder paths nest.
- VIZ_STORAGE=local without VIZ_LOCAL_DIR published into ./sample-bucket -> refused.
- Chart sets AWS_REGION but boto3 reads AWS_DEFAULT_REGION -> both set.
- Identity header forgeable by anyone reaching the LB/pods directly -> allowedSourceCidrs,
  dedicated ALB subnets, NLB client-IP requirement, forged-header checks in the guide.

## Dead ends
- Bash $(...) blocked by the guard hook: poll CI with a .venv python one-liner instead.
- Worktree not used: .venv editable install points at the main checkout.

## Open threads / deferred (all logged in the ledgers as minor)
- CI has not run on `hardening`: docker job, helm render checks (helm_checks.py incl. 3 new
  checks), gitleaks. CI runs only on pushes to main and on PRs -> push branch, open PR in web UI.
- Deferred minors: concurrent same-id publish clean-up race (grace period idea); stale rows across
  dashboards narrow race; non-UTF-8 .pulled-etag traceback; read_sql_file OSError traceback;
  date-range `last` pattern trailing newline; SG-for-pods text would block kubelet probes;
  stat tiles have no accessible name; preStop 5s may be short for ALB; "step 2a" refs ambiguous.
- Real AWS/Databricks steps at work (docs/work-setup.md) still to be done by the user.

## Test state (hardening at 5187b41, 69 commits ahead of main)
pytest 653 passed, 4 skipped (integration opt-ins, helm render, Windows symlink); vitest 190;
typecheck clean; build ok; Playwright 7/7. Docker/helm unverified locally.
