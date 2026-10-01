# Plan 5c: Viewer hardening (DuckDB lockdown, sanitizer, tooltips, select options, deep links, empty state, download, freshness, caching) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the viewer findings A4-A12 from the 2026-09-29 hardening review, remove the misleading "Refreshable ... schedule ..." text from the chart page, and show "Data as of <time> UTC" on every chart tile, so the browser side of viz-site is locked down, honest about freshness, usable with large-lane select controls and deep links, and cheap to load.

**Architecture:** Front-end changes stay inside the existing modules: `web/src/data/duckdb.ts` (lockdown, distinct values), `web/src/renderers/vegaLiteSanitize.ts` and a new `web/src/renderers/textTooltip.ts` (spec rules and a text-only tooltip), `web/src/state/urlState.ts` (cleared marker), `web/src/components/ChartTile.tsx` (options reporting, failure reporting, empty state, badges, download link, `aria-label`, freshness, preloaded chart), `web/src/pages/DashboardPage.tsx` (options from every lane, deep-link survival) and `web/src/pages/ChartPage.tsx` (one fetch, source text). The CLI validator `viz/schemas.py` mirrors the new sanitizer rules so the CLI refuses what the viewer refuses (spec 12.3). One new server module, `viz/server/compression.py`, adds immutable caching for `/assets` and gzip for responses over 1 KB except `/api/data/`, `.wasm` files and `/duckdb/`. A final docs task records the new sanitizer and DuckDB rules in design spec section 12.3. The server stays read-only.

**Empty-then-insert check (decisions doc, plan 5c):** `web/src/renderers/vegaLite.ts` does mount an empty view and then insert rows (vega-embed runs `view.initialize(el).runAsync()` on the empty named dataset, then the adapter calls `view.data('data', rows)` and `runAsync()` again), but both runs finish inside one browser task: vega-view 6 `evaluate()` and vega-scenegraph `renderAsync()` resolve through microtasks only (no `requestAnimationFrame` or timer on that path; checked in `node_modules/vega-view/build/vega-view.js` line 1149-1161 and `node_modules/vega-scenegraph/build/vega-scenegraph.js` line 3101), so the empty frame is never painted, and autosize is recomputed on the second run (the e2e "chart fills its tile" checks already pass). No fix task; Task 3 adds a code comment recording this.

**Tech Stack:** TypeScript 5.9, React 19, vitest 3 + jsdom + @testing-library/react, Playwright 1.63, @duckdb/duckdb-wasm 1.32 (DuckDB v1.4.3), vega-embed 7; Python 3.11, FastAPI, Starlette 1.6 (`GZipMiddleware` ships with it), pytest. No new dependencies.

**Spec:** `docs/superpowers/specs/2026-09-29-hardening-decisions.md` (binding; this is plan 5c) and `docs/superpowers/specs/2026-09-29-hardening-findings.md` (finding texts A4-A12, intent item 2 "Refreshable" text, intent item 7 download link). Background: `docs/superpowers/specs/2026-09-22-viz-site-design.md` sections 5.2 and 12.3 (Task 13 updates 12.3).

**How A4 was verified (read before Task 1).** The finding asks for `SET enable_external_access=false` "after the registered buffer and extension load". In this app the extension is loaded at startup but each chart's parquet buffer is registered later, lazily, after the configuration is locked. A scratch Node script ran the duckdb-wasm build that ships in `web/node_modules` (`dist/duckdb-node-blocking.cjs`, DuckDB v1.4.3, same C++ core as the browser build) and found:

1. `SET enable_external_access=false` then `registerFileBuffer('raw_x.csv', ...)` then `read_csv('raw_x.csv')` fails: `Permission Error: Cannot access file "raw_x.csv" - file system operations are disabled by configuration`. Registering the buffer before the SET fails the same way. So adding the SET alone would break every large-lane chart.
2. `SET allowed_directories=['/viz-data/']` before `SET enable_external_access=false`, then `SET lock_configuration=true`, then `registerFileBuffer('/viz-data/raw_x.csv', ...)` and `read_csv('/viz-data/raw_x.csv')` succeeds (2 rows), while `other.csv`, `/viz-data/../other.csv`, `/etc/passwd` and `https://example.com/x.csv` all fail with the same Permission Error, and `SET enable_external_access=true` fails with "the configuration has been locked".

So Task 1 registers every data file under `/viz-data/` and adds `allowed_directories` plus `enable_external_access=false` before the lock. Task 1 turns that script into a vitest test (`web/src/data/duckdbNode.test.ts`) so the behaviour is pinned, and Task 12's Playwright run proves the parquet path works in Chromium (the large-lane tile must reach `data-state="ready"`).

## Global Constraints

- Run on the branch `hardening`, after plans 5a and 5b (Task 0 checks). Plan 5a added the required field `file` to `ChartData` in `web/src/api/types.ts` (every `Chart` literal in a test needs it, or the typecheck fails); the URL `/api/data/<id>` is unchanged and this plan relies only on that URL. Plan 5a also added `tests/test_forbidden_keys.py`, which requires the schema's forbidden-key enum to equal `FORBIDDEN_KEYS` in `vegaLiteSanitize.ts` plus the three prototype keys: this plan never adds to `FORBIDDEN_KEYS` (new rules get their own checks). Plan 5b changed no front-end or server file.
- Anchors in `viz/server/app.py`, `viz/schemas.py` and the design spec are the text after plan 5a (see 5a's "Interfaces for later plans").
- Node.js 24 is at `C:\Program Files\nodejs`. In Git Bash run `export PATH="/c/Program Files/nodejs:$PATH"` first. All `npm` and `npx` commands run from `web/`. All Python commands use `.venv/Scripts/python` from the repo root (Linux/macOS: `.venv/bin/python`).
- Do not run `npm install` and do not add dependencies (CLAUDE.md rule 7). Everything this plan needs is already in `web/node_modules` and `.venv`.
- A guard hook blocks shell commands that contain backticks, `$(...)`, or redirects to paths outside the project. Create or rewrite files with the Write tool, and make edits with the Edit tool. Every file in this plan that contains a backtick (most TypeScript files here use template literals) must be written with the Write or Edit tool, never with a shell heredoc.
- `dangerouslySetInnerHTML`, `.innerHTML`, `.outerHTML`, `insertAdjacentHTML`, `document.write`, `srcdoc`, `new Function(` and `eval(` must not appear anywhere under `web/src`, `web/e2e` or `web/scripts`, not even in a comment (`web/src/test/noInnerHtml.test.ts` greps for them).
- The server gets no write routes. `DATABRICKS_*` never appears in server code.
- Before every commit: from `web/`, `npm test` and `npm run typecheck` must pass; when a Python file changed, `.venv/Scripts/python -m pytest` from the repo root must pass.
- Every commit message follows the "Commit messages" section of `CLAUDE.md`: subject, blank line, then two contiguous trailer lines (`Co-Authored-By` naming the model that made the commit as its harness states it, and `Claude-Session` with the session URL its harness states), produced with exactly two `-m` flags. The commit steps below show `<model name from your harness>` and `<session url from your harness>` placeholders; replace them with what your harness states.
- Stage only the files named in the task's commit step. Never run `git checkout -- .`, `git restore`, `git stash`, `git clean` or `git reset`.

## Review Focus

1. **The lockdown breaks the large lane.** `enable_external_access=false` also blocks DuckDB from reading its own registered buffers unless they sit under an allowed directory. Expected: data files are registered under `/viz-data/`, which is allowed; nothing else is. Pinned in Task 1 (`duckdbNode.test.ts`: "reads a buffer registered under the data directory after the lockdown" and "refuses every other path and cannot be unlocked") and in Task 12 (the Playwright large-lane tile reaches ready).
2. **A deep-linked select value is dropped** while some tiles are still loading, either by validation against a partial option list or by `onChange` rewriting the URL from validated filters. Expected: URL values are validated only after every chart tile reported rows, options or a failure, and `onChange` copies untouched controls' raw URL values. Pinned in Task 7 (`keeps a deep-linked select value while tiles are still loading, even when another control changes`).
3. **The new sanitizer rules reject charts that already render**, for example a gallery chart with a `layer`. Expected: every chart in `sample-bucket/` still passes the browser sanitizer and the CLI validator. Pinned in Task 2 (`web/src/renderers/samples.test.ts` is part of the run) and Task 4 (`tests/test_sample_bucket.py` and `test_valid_charts_pass`).
4. **Compression corrupts data downloads or wasm, or caching leaks onto index.html.** Gzipping `/api/data/` would break the client's `Content-Length` cap check and Range requests; gzipping `.wasm` files or anything under `/duckdb/` is ruled out by the lead; an immutable `index.html` would pin users to an old build. Expected: `/api/data/`, `*.wasm` and `/duckdb/*` are never gzipped, only `/assets/*` is immutable. Pinned in Task 11 (`test_data_files_are_never_gzipped`, `test_wasm_and_duckdb_files_are_never_gzipped`, `test_index_html_is_not_immutable`).
5. **A tooltip still renders markup.** vega-embed falls back to vega-tooltip (which renders HTML and turns an `image` key into `<img src>`) whenever the `tooltip` option is not a function. Expected: the adapter always passes the text-only handler and the handler only ever sets `textContent`. Pinned in Task 3 (`passes a text-only tooltip handler, never vega-tooltip`).

---

## How to execute a task (read this whether you are a large or a small model)

1. Read `CLAUDE.md` at the repo root first. It has the commands, the commit
   trailers, and the environment gotchas.
2. Work only on the task you were given. Do not start the next one.
3. Do the steps in order. Each step is one action. Do not skip the "run the
   test and see it fail" step; it proves the test is real.
4. Copy the code and text from the step exactly. If code in a step does not
   work as written, fix the smallest thing that makes it work, and say what
   you changed and why in your report. Do not redesign.
5. If a command fails and you cannot fix it within the task's scope, stop and
   report the full error output. Do not work around it by weakening a test.
6. Before committing, run the checks listed in Global Constraints. They must pass.
7. Stage only the files named in the task's commit step. Never run
   `git checkout -- .`, `git restore`, `git stash`, `git clean` or `git reset`.
8. Report back with: the commit hash, the test summary lines, and any
   deviation from the plan. Nothing else is needed.

When a step says "Edit", use the Edit tool with the exact old text shown
("Find") and the exact new text shown ("Replace with"). When a step says
"Write", use the Write tool with the full file content shown.

---

## File structure

| Path | Responsibility |
|---|---|
| `web/src/data/duckdb.ts` | Lockdown statements, `DATA_DIR`, `registeredFileName`, `buildDistinctAggregate`, `distinctValues` |
| `web/src/data/duckdbNode.test.ts` (new) | Runs the real duckdb-wasm Node build to pin the lockdown and the distinct SQL |
| `web/src/renderers/vegaLiteSanitize.ts` | Rejects `data` below the top level, `sequence`/`graticule`/`sphere` (own `DATA_GENERATORS` set, not `FORBIDDEN_KEYS`), `bind.element` |
| `web/src/renderers/textTooltip.ts` (new) | Text-only Vega tooltip handler |
| `web/src/renderers/vegaLite.ts` | Passes the text tooltip to vega-embed |
| `viz/schemas.py`, `tests/test_schemas.py` | CLI mirror of the new sanitizer rules |
| `web/src/state/urlState.ts` | New cleared marker `:none`, legacy `-` still read for ranges |
| `web/src/components/ChartTile.tsx` | `optionColumns`/`onOptions`, `onFailed`, `controlLabels`, `chart`, empty state, badges, footer |
| `web/src/components/freshness.ts` (new) | `formatDataAsOf` |
| `web/src/components/ControlBar.tsx` | Keeps a current select value listed |
| `web/src/pages/DashboardPage.tsx` | Options from both lanes, deep-link survival, labels |
| `web/src/pages/ChartPage.tsx` | One fetch, "Source: Databricks SQL", SQL only when `show_sql` |
| `web/src/styles.css` | Tooltip, empty state, footer styles |
| `viz/server/compression.py` (new), `viz/server/static.py`, `viz/server/app.py` | Immutable `/assets`, gzip over 1 KB except `/api/data/`, `*.wasm` and `/duckdb/` |
| `tests/server/test_compression.py` (new) | Tests for the above |
| `web/e2e/smoke.spec.ts` | Deep link, download link, freshness, cache header in a real browser |
| `docs/superpowers/specs/2026-09-22-viz-site-design.md`, `tests/test_spec_text.py` | Section 12.3 records the new sanitizer and DuckDB rules (Task 13) |

---

### Task 0: Confirm plans 5a and 5b are in

**Files:** none changed. No commit.

**Interfaces:**
- Consumes: plan 5a's and plan 5b's "Interfaces for later plans" sections.
- Produces: a short report; Task 1 starts only after it.

- [ ] **Step 1: Check the branch**

Run: `git branch --show-current`
Expected: `hardening`. If not, stop and report.

- [ ] **Step 2: Check the interfaces this plan builds on**

Run each command:

```
grep -n "file: string;" web/src/api/types.ts
grep -n "const FORBIDDEN_KEYS = new Set" web/src/renderers/vegaLiteSanitize.ts
grep -n "def _browser_forbidden_keys" tests/test_forbidden_keys.py
grep -n "from .middleware import" viz/server/app.py
grep -n "add_middleware" viz/server/app.py
grep -n "HEALTH_METHODS" viz/server/middleware.py
grep -n "def test_spec_drops_the_retired_renderers_from_the_sanitizer_rules" tests/test_spec_text.py
grep -n "Vega-Lite won the bake-off; Plotly and ECharts are removed." docs/superpowers/specs/2026-09-22-viz-site-design.md
grep -n "sql-file" viz/publish/cli.py
```

Expected, in order: one match in `ChartData`; one match; one match; `from .middleware import IdentityMiddleware, SecurityHeadersMiddleware, TrustedHostExceptHealth`; three `add_middleware` lines, the last one `app.add_middleware(SecurityHeadersMiddleware)`; at least one match; one match; one match (plan 5a's rewrite of the spec 12.3 sanitizer bullet); at least one match (plan 5b's `--sql-file`). If any is missing, stop and report the output.

- [ ] **Step 3: Run every suite**

Run: `.venv/Scripts/python -m pytest`
Then `export PATH="/c/Program Files/nodejs:$PATH"` and, from `web/`: `npm test` then `npm run typecheck`
Expected: all pass, 0 failed. If anything fails, stop and report.

- [ ] **Step 4: Report**

Report the branch and the three summary lines. Nothing is committed.

---

### Task 1: Browser DuckDB disables external access and reads only `/viz-data/` (A4)

**Files:**
- Modify: `web/src/data/duckdb.ts`, `web/src/data/duckdb.test.ts`
- Create: `web/src/data/duckdbNode.test.ts`

**Interfaces:**
- Consumes: `INIT_STATEMENTS`, `tableName(chartId)`, `ensureLoaded` (internal) in `web/src/data/duckdb.ts`; the Node build `web/node_modules/@duckdb/duckdb-wasm/dist/duckdb-node-blocking.cjs`.
- Produces:
  - `export const DATA_DIR = '/viz-data/'`
  - `INIT_STATEMENTS` becomes, in this order: `SET autoinstall_known_extensions=false`, `SET autoload_known_extensions=false`, `SET memory_limit='512MB'`, `SET allowed_directories=['/viz-data/']`, `SET enable_external_access=false`, `SET lock_configuration=true`. They still run after `buildPreloadStatements` (which loads parquet), so the extension load happens before external access is turned off.
  - `export function registeredFileName(chartId: string): string` returns `'/viz-data/' + tableName(chartId) + '.parquet'`. `ensureLoaded` registers the buffer under this name.

- [ ] **Step 1: Update the unit test for the init statements**

Edit `web/src/data/duckdb.test.ts`.

Find:
```ts
  INIT_STATEMENTS,
  ROW_LIMIT,
```
Replace with:
```ts
  DATA_DIR,
  INIT_STATEMENTS,
  ROW_LIMIT,
```

Find:
```ts
  parseSerializedSql,
  tableName,
  withTempTables,
} from './duckdb';
```
Replace with:
```ts
  parseSerializedSql,
  registeredFileName,
  tableName,
  withTempTables,
} from './duckdb';
```

Find:
```ts
describe('init statements', () => {
  it('are the spec 12.3 sequence, locked last', () => {
    expect(INIT_STATEMENTS).toEqual([
      'SET autoinstall_known_extensions=false',
      'SET autoload_known_extensions=false',
      "SET memory_limit='512MB'",
      'SET lock_configuration=true',
    ]);
  });
});
```
Replace with:
```ts
describe('init statements', () => {
  it('are the spec 12.3 sequence plus the A4 external-access lockdown, locked last', () => {
    expect(INIT_STATEMENTS).toEqual([
      'SET autoinstall_known_extensions=false',
      'SET autoload_known_extensions=false',
      "SET memory_limit='512MB'",
      "SET allowed_directories=['/viz-data/']",
      'SET enable_external_access=false',
      'SET lock_configuration=true',
    ]);
  });
});

describe('registeredFileName', () => {
  it('puts every data file inside the one directory the lockdown allows', () => {
    expect(DATA_DIR).toBe('/viz-data/');
    expect(registeredFileName('bakeoff/vega-lite/order-lines')).toBe('/viz-data/raw_bakeoff_vega_lite_order_lines.parquet');
  });
});
```

- [ ] **Step 2: Write the Node integration test**

Write `web/src/data/duckdbNode.test.ts` (Write tool: the file contains backticks):

```ts
// @vitest-environment node
//
// Runs the real duckdb-wasm build (the Node flavour of the same DuckDB
// v1.4.3 core the browser uses) to pin finding A4: after INIT_STATEMENTS,
// DuckDB can read a buffer registered under DATA_DIR and nothing else, and
// the lockdown cannot be undone. CSV is used because read_csv is built in;
// the permission check is the same for every file reader, parquet included.
import { createRequire } from 'node:module';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';
import { INIT_STATEMENTS, registeredFileName } from './duckdb';

const WEB = join(dirname(fileURLToPath(import.meta.url)), '..', '..');
const DIST = join(WEB, 'node_modules', '@duckdb', 'duckdb-wasm', 'dist');
const requireCjs = createRequire(import.meta.url);

interface NodeTable {
  toArray(): { toJSON(): Record<string, unknown> }[];
}
interface NodeConnection {
  query(sql: string): NodeTable;
  close(): void;
}
interface NodeDb {
  instantiate(progress: () => void): Promise<unknown>;
  open(config: { path: string }): void;
  connect(): NodeConnection;
  registerFileBuffer(name: string, buffer: Uint8Array): void;
}
interface NodeDuckDb {
  createDuckDB(bundles: unknown, logger: unknown, runtime: unknown): Promise<NodeDb>;
  VoidLogger: new () => unknown;
  NODE_RUNTIME: unknown;
}

const CSV = new TextEncoder().encode('a,b\n1,x\n2,y\n');

async function lockedDb(): Promise<{ db: NodeDb; conn: NodeConnection }> {
  const duckdb = requireCjs(join(DIST, 'duckdb-node-blocking.cjs')) as NodeDuckDb;
  const db = await duckdb.createDuckDB(
    {
      mvp: { mainModule: join(DIST, 'duckdb-mvp.wasm'), mainWorker: join(DIST, 'duckdb-node-mvp.worker.cjs') },
      eh: { mainModule: join(DIST, 'duckdb-eh.wasm'), mainWorker: join(DIST, 'duckdb-node-eh.worker.cjs') },
    },
    new duckdb.VoidLogger(),
    duckdb.NODE_RUNTIME,
  );
  await db.instantiate(() => undefined);
  db.open({ path: ':memory:' });
  const conn = db.connect();
  for (const statement of INIT_STATEMENTS) conn.query(statement);
  return { db, conn };
}

function csvName(chartId: string): string {
  return registeredFileName(chartId).replace(/\.parquet$/, '.csv');
}

describe('DuckDB lockdown (A4), real duckdb-wasm', () => {
  it('reads a buffer registered under the data directory after the lockdown', async () => {
    const { db, conn } = await lockedDb();
    const name = csvName('sales/x');
    db.registerFileBuffer(name, CSV);
    conn.query(`CREATE TABLE t AS SELECT * FROM read_csv('${name}')`);
    const count = conn.query('SELECT count(*)::INTEGER AS n FROM t').toArray()[0].toJSON().n;
    expect(count).toBe(2);
    conn.close();
  }, 60_000);

  it('refuses every other path and cannot be unlocked', async () => {
    const { db, conn } = await lockedDb();
    db.registerFileBuffer('other.csv', CSV);
    db.registerFileBuffer('/elsewhere/x.csv', CSV);
    for (const path of ['other.csv', '/elsewhere/x.csv', '/viz-data/../other.csv', 'https://example.com/x.csv']) {
      expect(() => conn.query(`SELECT * FROM read_csv('${path}')`), path).toThrow(/Permission Error/);
    }
    expect(() => conn.query('SET enable_external_access=true')).toThrow(/locked/);
    expect(() => conn.query("SET allowed_directories=['/']")).toThrow();
    conn.close();
  }, 60_000);
});
```

- [ ] **Step 3: Run the tests to see them fail**

Run from `web/`: `npm test -- src/data/duckdb`
Expected: `init statements` FAILS (two statements missing), `registeredFileName` FAILS (`registeredFileName is not a function`, `DATA_DIR` undefined), both `duckdbNode.test.ts` cases FAIL (the first with `registeredFileName is not a function`, the second because `read_csv('other.csv')` does not throw).

- [ ] **Step 4: Add the lockdown to `web/src/data/duckdb.ts`**

Edit `web/src/data/duckdb.ts`.

Find:
```ts
export const INIT_STATEMENTS: readonly string[] = [
  'SET autoinstall_known_extensions=false',
  'SET autoload_known_extensions=false',
  "SET memory_limit='512MB'",
  'SET lock_configuration=true',
];
```
Replace with:
```ts
/**
 * Every data file is registered inside this one directory. Finding A4: with
 * `enable_external_access=false` DuckDB refuses to read any file, registered
 * buffers included, unless it sits under `allowed_directories`. Buffers are
 * registered lazily, after the configuration is locked, so the directory is
 * allowed up front and nothing else is. Verified against duckdb-wasm 1.32
 * (DuckDB v1.4.3) by `duckdbNode.test.ts`.
 */
export const DATA_DIR = '/viz-data/';

export const INIT_STATEMENTS: readonly string[] = [
  'SET autoinstall_known_extensions=false',
  'SET autoload_known_extensions=false',
  "SET memory_limit='512MB'",
  `SET allowed_directories=['${DATA_DIR}']`,
  'SET enable_external_access=false',
  'SET lock_configuration=true',
];

/** The name a chart's data buffer is registered under, inside DATA_DIR. */
export function registeredFileName(chartId: string): string {
  return `${DATA_DIR}${tableName(chartId)}.parquet`;
}
```

Find (inside `ensureLoaded`):
```ts
  const file = `${tableName(chartId)}.parquet`;
```
Replace with:
```ts
  const file = registeredFileName(chartId);
```

- [ ] **Step 5: Run the tests to see them pass**

Run from `web/`: `npm test -- src/data/duckdb`
Expected: all pass (the Node test takes a few seconds).

- [ ] **Step 6: Run the whole front-end suite and the typecheck**

Run from `web/`: `npm test` then `npm run typecheck`
Expected: both pass.

- [ ] **Step 7: Commit**

Run from the repo root:

```bash
git add web/src/data/duckdb.ts web/src/data/duckdb.test.ts web/src/data/duckdbNode.test.ts
git -c user.name="tripp" -c user.email="dom4domg@gmail.com" commit -m "fix: browser DuckDB turns off external access and reads only /viz-data/ (A4)" -m "Co-Authored-By: <model name from your harness> <noreply@anthropic.com>
Claude-Session: <session url from your harness>"
```

---

### Task 2: Sanitizer rejects nested `data` and the `sequence`, `graticule`, `sphere` generators (A5)

**Files:**
- Modify: `web/src/renderers/vegaLiteSanitize.ts`, `web/src/renderers/vegaLiteSanitize.test.ts`

**Interfaces:**
- Consumes: `SanitizeError`, `assertPlain`, `deepClone`, `isPlainObject`, `walk` from `web/src/renderers/common.ts`. `walk` calls `visit(obj, key, value, path)` with `path` starting at `spec`, so the top-level data key has the path `spec/data`.
- Produces: `sanitize(spec)` throws `SanitizeError` with message `<path>: data is only allowed at the top level` for any `data` key whose path is not `spec/data`, and `<path>: data generator "<k>" is not allowed` for `sequence`, `graticule`, `sphere` at any depth (in addition to the existing keys). The generators live in their own set, `DATA_GENERATORS`; `FORBIDDEN_KEYS` stays exactly `'url', 'values', 'href', 'usermeta', 'datasets'`, because plan 5a's `tests/test_forbidden_keys.py` requires the schema enum to equal that set plus the prototype keys. The CLI mirror of both new rules is Task 4. `RULES` lists both rules.

- [ ] **Step 1: Write the failing tests**

Write `web/src/renderers/vegaLiteSanitize.test.ts` (Write tool) with this full content. Three existing cases change: the nested `url`, the `lookup` `values` and the layered `datasets` cases used a nested `data` key, which is now rejected first, so they now put the forbidden key somewhere else.

```ts
import { describe, expect, it } from 'vitest';
import { SanitizeError } from './common';
import { RULES, sanitize } from './vegaLiteSanitize';

const base = {
  data: { name: 'data' },
  mark: 'line',
  encoding: { x: { field: 'month', type: 'temporal' }, y: { field: 'revenue', type: 'quantitative' } },
};

describe('vega-lite sanitize', () => {
  it('returns a deep copy of a clean spec', () => {
    const out = sanitize(base);
    expect(out).toEqual(base);
    expect(out).not.toBe(base);
    expect(out.encoding).not.toBe(base.encoding);
  });

  it('requires data to be exactly the named dataset', () => {
    expect(() => sanitize({ ...base, data: { name: 'data', url: 'x' } })).toThrow(SanitizeError);
    expect(() => sanitize({ ...base, data: { name: 'other' } })).toThrow(SanitizeError);
    expect(() => sanitize({ ...base, data: undefined })).toThrow(SanitizeError);
    expect(() => sanitize({ mark: 'line' })).toThrow(SanitizeError);
  });

  it('rejects url, values, href and usermeta at any depth', () => {
    expect(() => sanitize({ ...base, layer: [{ mark: 'point', encoding: { x: { field: 'a', url: 'https://x' } } }] })).toThrow(/url/);
    expect(() => sanitize({ ...base, encoding: { ...base.encoding, href: { field: 'link' } } })).toThrow(/href/);
    expect(() => sanitize({ ...base, transform: [{ calculate: '1', as: 'x', values: [1] }] })).toThrow(/values/);
    expect(() => sanitize({ ...base, usermeta: { x: 1 } })).toThrow(/usermeta/);
  });

  it('rejects inline datasets at any depth', () => {
    expect(() =>
      sanitize({
        ...base,
        mark: 'bar',
        datasets: { mal: [{ x: 1 }] },
        layer: [{ mark: 'point' }],
      }),
    ).toThrow(SanitizeError);
    expect(() =>
      sanitize({
        ...base,
        layer: [{ mark: 'point', datasets: { mal: [{ x: 1 }] } }],
      }),
    ).toThrow(/datasets/);
  });

  it('rejects data below the top level, even the named dataset (A5)', () => {
    expect(() => sanitize({ ...base, layer: [{ data: { name: 'data' }, mark: 'point' }] })).toThrow(
      'spec/layer/0/data: data is only allowed at the top level',
    );
    expect(() => sanitize({ ...base, layer: [{ data: { sequence: { start: 0, stop: 1e9 } }, mark: 'point' }] })).toThrow(SanitizeError);
    expect(() => sanitize({ ...base, hconcat: [{ data: { name: 'data' }, mark: 'bar' }] })).toThrow(/top level/);
    expect(() => sanitize({ ...base, transform: [{ lookup: 'a', from: { data: { name: 'data' }, key: 'a' } }] })).toThrow(/top level/);
  });

  it('rejects the sequence, graticule and sphere generators anywhere (A5)', () => {
    for (const key of ['sequence', 'graticule', 'sphere']) {
      expect(() => sanitize({ ...base, transform: [{ [key]: true }] }), key).toThrow(`data generator "${key}" is not allowed`);
    }
    expect(() => sanitize({ ...base, data: { name: 'data', sequence: { start: 0, stop: 10 } } })).toThrow(SanitizeError);
  });

  it('keeps accepting a layered chart that inherits the top-level data', () => {
    const layered = { data: { name: 'data' }, layer: [{ mark: 'line', encoding: base.encoding }, { mark: 'rule', encoding: { y: { datum: 1 } } }] };
    expect(sanitize(layered)).toEqual(layered);
  });

  it('rejects image marks in both forms', () => {
    expect(() => sanitize({ ...base, mark: 'image' })).toThrow(/image/);
    expect(() => sanitize({ ...base, layer: [{ mark: { type: 'image' } }] })).toThrow(/image/);
  });

  it('rejects non-plain values', () => {
    expect(() => sanitize({ ...base, encoding: { x: { field: 'a', scale: { domain: new Date() } } } })).toThrow(SanitizeError);
    expect(() => sanitize('line')).toThrow(SanitizeError);
  });

  it('publishes its rule list', () => {
    expect(RULES.length).toBeGreaterThanOrEqual(6);
    expect(RULES).toContain('key "data" rejected below the top level');
    expect(RULES).toContain('data generators "sequence", "graticule", "sphere" rejected at any depth');
  });
});
```

- [ ] **Step 2: Run the tests to see them fail**

Run from `web/`: `npm test -- src/renderers/vegaLiteSanitize`
Expected: `rejects data below the top level` FAILS (the first spec is accepted), `rejects the sequence, graticule and sphere generators anywhere` FAILS, `publishes its rule list` FAILS. The others pass.

- [ ] **Step 3: Write the new sanitizer**

Write `web/src/renderers/vegaLiteSanitize.ts` (Write tool) with this full content:

```ts
// Spec 12.3, Vega-Lite: null loader, actions off, canvas renderer, interpreter
// instead of eval, and reject url / values / href / image marks / usermeta /
// datasets at any depth. Finding A5 adds: data only at the top level, and no
// sequence / graticule / sphere generators (they make rows out of nothing and
// can freeze the tab). Pure: no DOM, no vega import.
import { SanitizeError, assertPlain, deepClone, isPlainObject, walk } from './common';

export const RULES: readonly string[] = [
  'spec must be a plain JSON object',
  'top-level data must be exactly {"name": "data"}',
  'key "data" rejected below the top level',
  'key "url" rejected at any depth',
  'key "values" rejected at any depth',
  'key "href" rejected at any depth',
  'key "usermeta" rejected at any depth',
  'key "datasets" rejected at any depth',
  'data generators "sequence", "graticule", "sphere" rejected at any depth',
  'image marks rejected',
  'loader refuses load, sanitize, http and file',
  'actions menu off, canvas renderer, ast interpreter (no eval)',
];

// Keep this declaration in this exact form: tests/test_forbidden_keys.py parses it
// and requires schemas/chart.schema.json to forbid the same keys.
const FORBIDDEN_KEYS = new Set(['url', 'values', 'href', 'usermeta', 'datasets']);

// Finding A5. Mirrored in viz/schemas.py::_check_vegalite, not in the schema enum.
const DATA_GENERATORS = new Set(['sequence', 'graticule', 'sphere']);

const TOP_LEVEL_DATA_PATH = 'spec/data';

export function sanitize(spec: unknown): Record<string, unknown> {
  assertPlain(spec);
  if (!isPlainObject(spec)) throw new SanitizeError('vega-lite spec must be an object');
  const clean = deepClone(spec);
  const data = clean.data;
  if (!isPlainObject(data) || Object.keys(data).length !== 1 || data.name !== 'data') {
    throw new SanitizeError('vega-lite data must be exactly {"name": "data"}');
  }
  walk(clean, (_obj, key, value, path) => {
    if (key === 'data' && path !== TOP_LEVEL_DATA_PATH) throw new SanitizeError(`${path}: data is only allowed at the top level`);
    if (DATA_GENERATORS.has(key)) throw new SanitizeError(`${path}: data generator "${key}" is not allowed`);
    if (FORBIDDEN_KEYS.has(key)) throw new SanitizeError(`${path}: key "${key}" is not allowed`);
    if (key === 'mark' && (value === 'image' || (isPlainObject(value) && value.type === 'image'))) {
      throw new SanitizeError(`${path}: image marks are not allowed`);
    }
  });
  return clean;
}
```

- [ ] **Step 4: Run the tests to see them pass**

Run from `web/`: `npm test -- src/renderers`
Expected: all pass, including `samples.test.ts` (every sample-bucket chart still sanitizes). If a `samples.test.ts` case fails, stop and report the chart id and message: a sample would need changing, which is not in this plan.

- [ ] **Step 5: Run the whole front-end suite, the typecheck and the forbidden-key test**

Run from `web/`: `npm test` then `npm run typecheck`
Expected: both pass.

Run from the repo root: `.venv/Scripts/python -m pytest tests/test_forbidden_keys.py -v`
Expected: all pass (it parses `FORBIDDEN_KEYS` from the file you just wrote; the set is unchanged, so the schema needs no edit).

- [ ] **Step 6: Commit**

Run from the repo root:

```bash
git add web/src/renderers/vegaLiteSanitize.ts web/src/renderers/vegaLiteSanitize.test.ts
git -c user.name="tripp" -c user.email="dom4domg@gmail.com" commit -m "fix: Vega-Lite sanitizer rejects nested data and row generators (A5)" -m "Co-Authored-By: <model name from your harness> <noreply@anthropic.com>
Claude-Session: <session url from your harness>"
```

---

### Task 3: Text-only tooltips and no `bind.element` (A6)

**Files:**
- Create: `web/src/renderers/textTooltip.ts`, `web/src/renderers/textTooltip.test.ts`
- Modify: `web/src/renderers/vegaLite.ts`, `web/src/renderers/vegaLite.test.ts`, `web/src/renderers/vegaLiteSanitize.ts`, `web/src/renderers/vegaLiteSanitize.test.ts`, `web/src/styles.css`

**Interfaces:**
- Consumes: vega-embed 7 option `tooltip`: when it is a function, vega-embed calls `view.tooltip(fn)` and never constructs vega-tooltip's HTML `Handler` (`node_modules/vega-embed/build/embed.js` line 2848-2855). Vega calls the handler as `(handler, event, item, value)`.
- Produces:
  - `web/src/renderers/textTooltip.ts`: `export const MAX_TOOLTIP_CHARS = 2000`; `export function tooltipText(value: unknown): string` (pure; a `title` key becomes the first line, every other key becomes `key: value`, the `image` key is dropped, output capped at 2000 characters plus `…`); `export interface TextTooltip { handler(handler: unknown, event: MouseEvent, item: unknown, value: unknown): void; destroy(): void }`; `export function createTextTooltip(doc?: Document): TextTooltip` (one `div.viz-tooltip` with `role="tooltip"` appended to `document.body`, filled only through `textContent`, hidden for a null, undefined or empty value, removed by `destroy()`).
  - `vegaLite.ts` passes `tooltip: <TextTooltip>.handler` to `embed` and destroys it in `destroy()`.
  - `sanitize` throws `<path>: bind.element is not allowed` for any `bind` object that has an `element` key, at any depth.

- [ ] **Step 1: Write the failing tooltip unit tests**

Write `web/src/renderers/textTooltip.test.ts` (Write tool):

```ts
import { afterEach, describe, expect, it } from 'vitest';
import { MAX_TOOLTIP_CHARS, createTextTooltip, tooltipText } from './textTooltip';

afterEach(() => {
  for (const el of Array.from(document.querySelectorAll('.viz-tooltip'))) el.remove();
});

function move(x = 5, y = 6): MouseEvent {
  return new MouseEvent('mousemove', { clientX: x, clientY: y });
}

describe('tooltipText', () => {
  it('puts the title first, lists the other keys, and drops image', () => {
    expect(tooltipText({ revenue: 1, title: 'EMEA', image: 'https://evil.example/x.png', month: '2026-01-01' })).toBe(
      'EMEA\nrevenue: 1\nmonth: 2026-01-01',
    );
  });

  it('formats scalars, nulls, arrays and nested objects as text', () => {
    expect(tooltipText('plain')).toBe('plain');
    expect(tooltipText(42)).toBe('42');
    expect(tooltipText({ a: null, b: [1, 2], c: { d: true } })).toBe('a: null\nb: [1,2]\nc: {"d":true}');
  });

  it('keeps markup as literal text', () => {
    expect(tooltipText({ title: '<img src=x onerror=alert(1)>' })).toBe('<img src=x onerror=alert(1)>');
  });

  it('caps very long text', () => {
    const out = tooltipText('x'.repeat(MAX_TOOLTIP_CHARS + 50));
    expect(out).toHaveLength(MAX_TOOLTIP_CHARS + 1);
    expect(out.endsWith('…')).toBe(true);
  });
});

describe('createTextTooltip', () => {
  it('shows text only, never an element built from the value', () => {
    const tip = createTextTooltip();
    tip.handler(null, move(10, 20), {}, { title: '<b>bold</b>', image: 'https://evil.example/x.png' });
    const el = document.querySelector('.viz-tooltip') as HTMLElement;
    expect(el).not.toBeNull();
    expect(el.getAttribute('role')).toBe('tooltip');
    expect(el.textContent).toBe('<b>bold</b>');
    expect(el.children).toHaveLength(0);
    expect(document.querySelector('img')).toBeNull();
    expect(el.style.display).toBe('block');
    expect(el.style.left).toBe('22px');
    expect(el.style.top).toBe('32px');
  });

  it('hides on an empty value and is removed by destroy', () => {
    const tip = createTextTooltip();
    tip.handler(null, move(), {}, { a: 1 });
    tip.handler(null, move(), {}, null);
    expect((document.querySelector('.viz-tooltip') as HTMLElement).style.display).toBe('none');
    tip.destroy();
    expect(document.querySelector('.viz-tooltip')).toBeNull();
  });
});
```

- [ ] **Step 2: Add the failing adapter and sanitizer tests**

Write `web/src/renderers/vegaLite.test.ts` (Write tool) with this full content (the existing four cases are unchanged; one case is added at the end of the `vega-lite adapter` block):

```ts
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { createAdapter, rejectingLoader } from './vegaLite';

const mocks = vi.hoisted(() => {
  const view = { data: vi.fn(), runAsync: vi.fn(async () => undefined) };
  const finalize = vi.fn();
  const embed = vi.fn(async () => ({ view, finalize }));
  return { view, finalize, embed };
});

vi.mock('vega-embed', () => ({ default: mocks.embed }));
vi.mock('vega-interpreter', () => ({ expressionInterpreter: { marker: 'interpreter' } }));

const spec = {
  data: { name: 'data' },
  mark: 'line',
  encoding: { x: { field: 'month', type: 'temporal' }, y: { field: 'revenue', type: 'quantitative' } },
};
const rows = [{ month: '2026-01-01', revenue: 1 }];
const columns = [
  { name: 'month', type: 'date' as const },
  { name: 'revenue', type: 'number' as const },
];

describe('vega-lite adapter', () => {
  beforeEach(() => {
    mocks.embed.mockClear();
    mocks.view.data.mockClear();
    mocks.finalize.mockClear();
  });

  it('mounts with the locked-down options and injects rows by name', async () => {
    const el = document.createElement('div');
    const adapter = createAdapter();
    await adapter.mount(el, spec, rows, columns);
    expect(mocks.embed).toHaveBeenCalledTimes(1);
    const [target, passedSpec, opts] = mocks.embed.mock.calls[0] as unknown as [HTMLElement, Record<string, unknown>, Record<string, unknown>];
    expect(target).toBe(el);
    expect(passedSpec.data).toEqual({ name: 'data' });
    expect(passedSpec.width).toBe('container');
    expect(passedSpec.height).toBe('container');
    expect(opts).toMatchObject({ actions: false, renderer: 'canvas', ast: true, expr: { marker: 'interpreter' } });
    const loader = opts.loader as Record<string, () => Promise<unknown>>;
    for (const name of ['load', 'sanitize', 'http', 'file']) await expect(loader[name]()).rejects.toThrow();
    expect(mocks.view.data).toHaveBeenCalledWith('data', rows);
    expect(mocks.view.runAsync).toHaveBeenCalled();
    adapter.destroy();
  });

  it('update replaces the dataset and destroy finalizes', async () => {
    const adapter = createAdapter();
    await adapter.mount(document.createElement('div'), spec, rows, columns);
    const next = [{ month: '2026-02-01', revenue: 2 }];
    await adapter.update(next);
    expect(mocks.view.data).toHaveBeenLastCalledWith('data', next);
    adapter.destroy();
    expect(mocks.finalize).toHaveBeenCalledTimes(1);
  });

  it('refuses a hostile spec before touching the library', async () => {
    const adapter = createAdapter();
    await expect(adapter.mount(document.createElement('div'), { ...spec, data: { url: 'https://x' } }, rows, columns)).rejects.toThrow(/data/);
    expect(mocks.embed).not.toHaveBeenCalled();
  });

  it('rejectingLoader refuses everything', async () => {
    const loader = rejectingLoader();
    await expect(loader.load('x')).rejects.toThrow(/disabled/);
    await expect(loader.http('x')).rejects.toThrow(/disabled/);
  });

  it('passes a text-only tooltip handler, never vega-tooltip (A6)', async () => {
    const adapter = createAdapter();
    await adapter.mount(document.createElement('div'), spec, rows, columns);
    const opts = (mocks.embed.mock.calls[0] as unknown as [HTMLElement, unknown, Record<string, unknown>])[2];
    expect(typeof opts.tooltip).toBe('function');
    const handler = opts.tooltip as (h: unknown, e: MouseEvent, item: unknown, value: unknown) => void;
    handler(null, new MouseEvent('mousemove', { clientX: 5, clientY: 6 }), {}, { title: '<b>x</b>', image: 'https://evil.example/x.png', revenue: 1 });
    expect(document.querySelector('img')).toBeNull();
    const tip = document.querySelector('.viz-tooltip');
    expect(tip?.textContent).toBe('<b>x</b>\nrevenue: 1');
    expect(tip?.querySelector('b')).toBeNull();
    adapter.destroy();
    expect(document.querySelector('.viz-tooltip')).toBeNull();
  });
});
```

Edit `web/src/renderers/vegaLiteSanitize.test.ts`.

Find:
```ts
  it('rejects image marks in both forms', () => {
```
Replace with:
```ts
  it('rejects params[].bind.element at any depth (A6)', () => {
    expect(() =>
      sanitize({ ...base, params: [{ name: 'p', value: 1, bind: { input: 'range', min: 0, max: 10, element: '#elsewhere' } }] }),
    ).toThrow('spec/params/0/bind: bind.element is not allowed');
    expect(() => sanitize({ ...base, layer: [{ mark: 'point', params: [{ name: 'q', bind: { input: 'checkbox', element: 'body' } }] }] })).toThrow(
      /bind\.element/,
    );
    expect(() => sanitize({ ...base, params: [{ name: 'p', value: 1, bind: { input: 'range', min: 0, max: 10 } }] })).not.toThrow();
    expect(() => sanitize({ ...base, params: [{ name: 'sel', select: 'point', bind: 'legend' }] })).not.toThrow();
  });

  it('rejects image marks in both forms', () => {
```

- [ ] **Step 3: Run the tests to see them fail**

Run from `web/`: `npm test -- src/renderers`
Expected: `textTooltip.test.ts` FAILS (cannot resolve `./textTooltip`), `passes a text-only tooltip handler` FAILS (`opts.tooltip` is undefined), `rejects params[].bind.element at any depth` FAILS (the first spec is accepted).

- [ ] **Step 4: Write the tooltip module**

Write `web/src/renderers/textTooltip.ts` (Write tool):

```ts
// A text-only tooltip for Vega (finding A6). vega-embed's default handler,
// vega-tooltip, builds HTML and turns an `image` key into an <img src> that a
// bucket spec could point anywhere. This handler only ever sets textContent,
// so no markup from a spec or a data row is ever parsed.

export const MAX_TOOLTIP_CHARS = 2000;

function formatValue(v: unknown): string {
  if (v === null || v === undefined) return String(v);
  if (typeof v === 'string') return v;
  if (typeof v === 'number' || typeof v === 'boolean' || typeof v === 'bigint') return String(v);
  if (v instanceof Date) return v.toISOString();
  try {
    return JSON.stringify(v) ?? '';
  } catch {
    return '[unprintable]';
  }
}

/** The tooltip text for a Vega tooltip value. Pure. The `image` key is dropped. */
export function tooltipText(value: unknown): string {
  let text: string;
  if (value !== null && typeof value === 'object' && !Array.isArray(value) && !(value instanceof Date)) {
    const obj = value as Record<string, unknown>;
    const lines: string[] = [];
    if ('title' in obj) lines.push(formatValue(obj.title));
    for (const key of Object.keys(obj)) {
      if (key === 'title' || key === 'image') continue;
      lines.push(`${key}: ${formatValue(obj[key])}`);
    }
    text = lines.join('\n');
  } else {
    text = formatValue(value);
  }
  return text.length > MAX_TOOLTIP_CHARS ? `${text.slice(0, MAX_TOOLTIP_CHARS)}…` : text;
}

export interface TextTooltip {
  handler(handler: unknown, event: MouseEvent, item: unknown, value: unknown): void;
  destroy(): void;
}

/** One tooltip element per chart, appended to the body on first use. */
export function createTextTooltip(doc: Document = document): TextTooltip {
  let el: HTMLDivElement | null = null;
  return {
    handler(_handler: unknown, event: MouseEvent, _item: unknown, value: unknown): void {
      if (value === null || value === undefined || value === '') {
        if (el) el.style.display = 'none';
        return;
      }
      if (!el) {
        el = doc.createElement('div');
        el.className = 'viz-tooltip';
        el.setAttribute('role', 'tooltip');
        doc.body.appendChild(el);
      }
      el.textContent = tooltipText(value);
      el.style.display = 'block';
      el.style.left = `${event.clientX + 12}px`;
      el.style.top = `${event.clientY + 12}px`;
    },
    destroy(): void {
      el?.remove();
      el = null;
    },
  };
}
```

- [ ] **Step 5: Pass it to vega-embed**

Write `web/src/renderers/vegaLite.ts` (Write tool) with this full content:

```ts
import type { Column, Row } from '../api/types';
import type { Adapter } from './adapter';
import { createTextTooltip, type TextTooltip } from './textTooltip';
import { sanitize } from './vegaLiteSanitize';

interface EmbedView {
  data(name: string, values: unknown[]): unknown;
  runAsync(): Promise<unknown>;
}

interface EmbedResult {
  view: EmbedView;
  finalize(): void;
}

/** A Vega loader that refuses every request. Specs cannot fetch anything. */
export function rejectingLoader() {
  const refuse = async (_uri?: unknown, _options?: unknown): Promise<never> => {
    throw new Error('external loads are disabled');
  };
  return { load: refuse, sanitize: refuse, http: refuse, file: refuse };
}

export function createAdapter(): Adapter {
  let result: EmbedResult | null = null;
  let tooltip: TextTooltip | null = null;

  return {
    async mount(el: HTMLElement, spec: unknown, rows: Row[], _columns: Column[]): Promise<void> {
      const clean = sanitize(spec);
      if (clean.width === undefined) clean.width = 'container';
      if (clean.height === undefined) clean.height = 'container';
      const [{ default: embed }, { expressionInterpreter }] = await Promise.all([import('vega-embed'), import('vega-interpreter')]);
      tooltip?.destroy();
      tooltip = createTextTooltip();
      // embed() runs the view once on the empty named dataset; the rows go in
      // right after. Both runs finish inside one task (vega-view and
      // vega-scenegraph render through microtasks only), so the empty frame
      // is never painted. Checked in plan 5c; no fix needed.
      const embedded = await embed(el, clean as never, {
        actions: false,
        renderer: 'canvas',
        ast: true,
        expr: expressionInterpreter as never,
        loader: rejectingLoader() as never,
        tooltip: tooltip.handler as never,
      });
      result = embedded as unknown as EmbedResult;
      result.view.data('data', rows);
      await result.view.runAsync();
    },

    async update(rows: Row[]): Promise<void> {
      if (!result) throw new Error('adapter is not mounted');
      result.view.data('data', rows);
      await result.view.runAsync();
    },

    destroy(): void {
      result?.finalize();
      result = null;
      tooltip?.destroy();
      tooltip = null;
    },
  };
}
```

- [ ] **Step 6: Reject `bind.element` in the sanitizer**

Edit `web/src/renderers/vegaLiteSanitize.ts`.

Find:
```ts
  'data generators "sequence", "graticule", "sphere" rejected at any depth',
  'image marks rejected',
```
Replace with:
```ts
  'data generators "sequence", "graticule", "sphere" rejected at any depth',
  'params[].bind.element rejected at any depth',
  'image marks rejected',
  'tooltips are text only (no vega-tooltip HTML, no image key)',
```

Find:
```ts
    if (FORBIDDEN_KEYS.has(key)) throw new SanitizeError(`${path}: key "${key}" is not allowed`);
```
Replace with:
```ts
    if (FORBIDDEN_KEYS.has(key)) throw new SanitizeError(`${path}: key "${key}" is not allowed`);
    if (key === 'bind' && isPlainObject(value) && 'element' in value) throw new SanitizeError(`${path}: bind.element is not allowed`);
```

- [ ] **Step 7: Style the tooltip**

Append to `web/src/styles.css`:

```css

/* Text-only Vega tooltip (plan 5c, finding A6). */
.viz-tooltip { position: fixed; z-index: 1000; pointer-events: none; white-space: pre; max-width: 360px; overflow: hidden; background: var(--bg); color: var(--fg); border: 1px solid var(--border); border-radius: 4px; padding: 6px 8px; font-size: 12px; box-shadow: 0 2px 6px rgba(0, 0, 0, 0.15); }
```

- [ ] **Step 8: Run the tests to see them pass**

Run from `web/`: `npm test -- src/renderers`
Expected: all pass.

- [ ] **Step 9: Run the whole front-end suite and the typecheck**

Run from `web/`: `npm test` then `npm run typecheck`
Expected: both pass (`noInnerHtml.test.ts` included).

- [ ] **Step 10: Commit**

Run from the repo root:

```bash
git add web/src/renderers/textTooltip.ts web/src/renderers/textTooltip.test.ts web/src/renderers/vegaLite.ts web/src/renderers/vegaLite.test.ts web/src/renderers/vegaLiteSanitize.ts web/src/renderers/vegaLiteSanitize.test.ts web/src/styles.css
git -c user.name="tripp" -c user.email="dom4domg@gmail.com" commit -m "fix: text-only Vega tooltips and no bind.element (A6)" -m "Co-Authored-By: <model name from your harness> <noreply@anthropic.com>
Claude-Session: <session url from your harness>"
```

---

### Task 4: The CLI validator refuses what the viewer now refuses

**Files:**
- Modify: `viz/schemas.py`, `tests/test_schemas.py`

**Interfaces:**
- Consumes: `viz.schemas._walk(node, path="spec")`, which yields `(path, key, value)` with the top-level data key at path `spec/data`; `_check_vegalite(spec, columns) -> list[str]`.
- Produces: `validate_chart` raises `SchemaError` for a vega-lite chart with any `data` key below the top level (`<path>: data is only allowed at the top level`), any `sequence`, `graticule` or `sphere` key (`<path>: data generator "<key>" is not allowed`, the same text the browser uses), or any `bind` object with an `element` key (`<path>: bind.element is not allowed`). Spec 12.3 requires the CLI and the viewer to share these rules. The rules live in `_check_vegalite`, not in the schema's forbidden-key enum, so plan 5a's `tests/test_forbidden_keys.py` and its list stay as they are; plan 5a's nesting cap in `viz/schemas.py` (`MAX_NESTING_DEPTH`, checked before JSON Schema) is untouched and runs first.

- [ ] **Step 1: Write the failing tests**

Edit `tests/test_schemas.py`.

Find:
```python
    ("vega-lite missing top-level data", "chart-vegalite.json", _delete("spec.data"), "top-level data"),
```
Replace with:
```python
    ("vega-lite missing top-level data", "chart-vegalite.json", _delete("spec.data"), "top-level data"),
    ("vega-lite nested data", "chart-vegalite.json",
     _set("spec.layer", [{"data": {"name": "data"}, "mark": "point"}]), "only allowed at the top level"),
    ("vega-lite nested sequence", "chart-vegalite.json",
     _set("spec.layer", [{"data": {"sequence": {"start": 0, "stop": 1000000000}}, "mark": "point"}]), "sequence"),
    ("vega-lite graticule", "chart-vegalite.json", _set("spec.transform", [{"graticule": True}]), "graticule"),
    ("vega-lite sphere", "chart-vegalite.json", _set("spec.transform", [{"sphere": True}]), "sphere"),
    ("vega-lite bind element", "chart-vegalite.json",
     _set("spec.params", [{"name": "p", "value": 1, "bind": {"input": "range", "element": "#x"}}]), "bind.element"),
```

Append to the end of `tests/test_schemas.py`:

```python


def test_vegalite_bind_without_element_passes():
    doc = copy.deepcopy(load("chart-vegalite.json"))
    doc["spec"]["params"] = [{"name": "p", "value": 1, "bind": {"input": "range", "min": 0, "max": 10}}]
    assert schemas.validate_chart(doc) is doc


def test_vegalite_layer_without_its_own_data_passes():
    doc = copy.deepcopy(load("chart-vegalite.json"))
    doc["spec"]["layer"] = [{"mark": "line"}, {"mark": "rule"}]
    assert schemas.validate_chart(doc) is doc
```

- [ ] **Step 2: Run the tests to see them fail**

Run: `.venv/Scripts/python -m pytest tests/test_schemas.py -v`
Expected: the five new `test_invalid_charts_fail` cases FAIL (`vega-lite nested data` and `vega-lite bind element`, `graticule`, `sphere` raise nothing; `vega-lite nested sequence` raises a message without "sequence"). The two new pass-cases pass.

- [ ] **Step 3: Change `_check_vegalite` in `viz/schemas.py`**

Edit `viz/schemas.py`.

Find:
```python
    for path, key, value in _walk(spec):
        if key == "data" and value != {"name": "data"}:
            errors.append(f"{path}: vega-lite data must be exactly {{\"name\": \"data\"}}")
```
Replace with:
```python
    for path, key, value in _walk(spec):
        # Same rules as web/src/renderers/vegaLiteSanitize.ts (plan 5c, A5 and A6).
        if key == "data" and path != "spec/data":
            errors.append(f"{path}: data is only allowed at the top level")
        if key in ("sequence", "graticule", "sphere"):
            errors.append(f"{path}: data generator \"{key}\" is not allowed")
        if key == "bind" and isinstance(value, dict) and "element" in value:
            errors.append(f"{path}: bind.element is not allowed")
```

- [ ] **Step 4: Run the tests to see them pass**

Run: `.venv/Scripts/python -m pytest tests/test_schemas.py tests/test_sample_bucket.py -v`
Expected: all pass.

- [ ] **Step 5: Run the whole Python suite**

Run: `.venv/Scripts/python -m pytest`
Expected: all pass.

- [ ] **Step 6: Commit**

Run from the repo root:

```bash
git add viz/schemas.py tests/test_schemas.py
git -c user.name="tripp" -c user.email="dom4domg@gmail.com" commit -m "fix: CLI validator mirrors the viewer's nested-data, generator and bind.element rules" -m "Co-Authored-By: <model name from your harness> <noreply@anthropic.com>
Claude-Session: <session url from your harness>"
```

---

### Task 5: The cleared marker can no longer collide with a select value (A12, URL part)

**Files:**
- Modify: `web/src/state/urlState.ts`, `web/src/state/urlState.test.ts`

**Interfaces:**
- Consumes: `encodeFilters`, `decodeFilters` in `web/src/state/urlState.ts`. Select values are written through `encodeURIComponent`, which always escapes `:`; text values start with `~`; ranges contain `..`.
- Produces: `export const CLEARED = ':none'`. `encodeFilters` writes `:none` for an inactive value. `decodeFilters` treats `:none` as cleared for every control, and the old marker `-` as cleared only for `date-range` and `number-range` controls (where `-` can never be a value), so old links keep working. A select value `-` now round-trips.

- [ ] **Step 1: Write the failing tests**

Edit `web/src/state/urlState.test.ts`.

Find:
```ts
import { decodeFilters, encodeFilters } from './urlState';
```
Replace with:
```ts
import { CLEARED, decodeFilters, encodeFilters } from './urlState';
```

Find:
```ts
    expect(params.get('minrev')).toBe('-');
```
Replace with:
```ts
    expect(params.get('minrev')).toBe(':none');
```

Append to the end of the file:

```ts

describe('the cleared marker (A12)', () => {
  it('cannot collide with a select value, even "-"', () => {
    const withDash = { region: { options: ['-', 'EMEA'], tooMany: false } };
    const filters: Filter[] = [{ controlId: 'region', column: 'region', value: { type: 'select', values: ['-'] } }];
    const params = encodeFilters(filters);
    expect(params.get('region')).toBe('-');
    expect(decodeFilters(params, controls, withDash, today)[1].value).toEqual({ type: 'select', values: ['-'] });
  });

  it('writes and reads the new marker for every control type', () => {
    const cleared: Filter[] = [
      { controlId: 'period', column: 'month', value: { type: 'date-range', from: null, to: null } },
      { controlId: 'region', column: 'region', value: { type: 'select', values: [] } },
      { controlId: 'minrev', column: 'revenue', value: { type: 'number-range', min: null, max: null } },
    ];
    const params = encodeFilters(cleared);
    for (const id of ['period', 'region', 'minrev']) expect(params.get(id)).toBe(CLEARED);
    expect(CLEARED).toBe(':none');
    const out = decodeFilters(new URLSearchParams(params.toString()), controls, options, today);
    expect(out[0].value).toEqual({ type: 'date-range', from: null, to: null });
    expect(out[1].value).toEqual({ type: 'select', values: [] });
    expect(out[2].value).toEqual({ type: 'number-range', min: null, max: null });
  });

  it('still reads the old "-" marker on range controls', () => {
    const out = decodeFilters(new URLSearchParams('period=-&minrev=-'), controls, options, today);
    expect(out[0].value).toEqual({ type: 'date-range', from: null, to: null });
    expect(out[2].value).toEqual({ type: 'number-range', min: null, max: null });
  });
});
```

- [ ] **Step 2: Run the tests to see them fail**

Run from `web/`: `npm test -- src/state`
Expected: `writes one parameter per control` FAILS (`'-'` is not `':none'`), `cannot collide with a select value` FAILS (`-` decodes to cleared), `writes and reads the new marker` FAILS (`CLEARED` is undefined). `still reads the old "-" marker` passes already.

- [ ] **Step 3: Change the marker**

Edit `web/src/state/urlState.ts`.

Find:
```ts
const CLEARED = '-';
```
Replace with:
```ts
/**
 * Marks a control the user cleared. It contains ':', which encodeURIComponent
 * always escapes, so no encoded select value can equal it (finding A12: the
 * old marker "-" collided with a select value "-"). Text values start with
 * "~" and ranges contain "..", so they cannot equal it either.
 */
export const CLEARED = ':none';

/** The marker before plan 5c. Still read for range controls, where "-" can never be a value. */
const LEGACY_CLEARED = '-';
```

Find:
```ts
    if (raw === CLEARED) {
```
Replace with:
```ts
    if (raw === CLEARED || (raw === LEGACY_CLEARED && control.type !== 'select')) {
```

- [ ] **Step 4: Run the tests to see them pass**

Run from `web/`: `npm test -- src/state`
Expected: all pass.

- [ ] **Step 5: Run the whole front-end suite and the typecheck**

Run from `web/`: `npm test` then `npm run typecheck`
Expected: both pass.

- [ ] **Step 6: Commit**

Run from the repo root:

```bash
git add web/src/state/urlState.ts web/src/state/urlState.test.ts
git -c user.name="tripp" -c user.email="dom4domg@gmail.com" commit -m "fix: cleared-control marker no longer collides with a select value (A12)" -m "Co-Authored-By: <model name from your harness> <noreply@anthropic.com>
Claude-Session: <session url from your harness>"
```

---

### Task 6: Large-lane tiles report select options through DuckDB (A7, tile part)

**Files:**
- Modify: `web/src/data/duckdb.ts`, `web/src/data/duckdb.test.ts`, `web/src/data/duckdbNode.test.ts`, `web/src/components/ChartTile.tsx`, `web/src/components/ChartTile.test.tsx`

**Interfaces:**
- Consumes: `queryLargeLane(chartId, aggregate, columns, filters, timeoutMs?)` (wraps any aggregate as `WITH data AS (SELECT * FROM "<table>") SELECT * FROM (<aggregate>) LIMIT 50000`, checks it is a single SELECT, serializes page-wide, enforces the timeout); `MAX_SELECT_OPTIONS` (500) from `web/src/data/filters.ts`.
- Produces:
  - `export const DISTINCT_LIMIT = MAX_SELECT_OPTIONS + 1` (501).
  - `export function buildDistinctAggregate(column: string, columns: Column[]): string` returns exactly `SELECT DISTINCT CAST("<column>" AS VARCHAR) AS v FROM data WHERE "<column>" IS NOT NULL LIMIT 501`; throws `DuckDbError('unknown column: <column>')` when the column is not declared or does not match `^[A-Za-z_][A-Za-z0-9_]*$`.
  - `export function distinctValues(chartId: string, column: string, columns: Column[], timeoutMs?: number): Promise<string[]>` runs that aggregate through `queryLargeLane` with no filters over the unfiltered table and returns the `v` values as strings. The cast matches the `CAST(<col> AS VARCHAR) IN (...)` that select filters use.
  - `ChartTileProps` gains `optionColumns?: string[]` and `onOptions?: (chartId: string, values: Record<string, string[]>) => void`. For a large-lane chart, once per loaded chart, the tile calls `distinctValues` for each distinct column in `optionColumns` that the chart declares, then calls `onOptions(chartId, { <column>: values })`, with `{}` when there is nothing to list. A failure becomes the tile's error card.

- [ ] **Step 1: Write the failing pure test**

Edit `web/src/data/duckdb.test.ts`.

Find:
```ts
  DATA_DIR,
  INIT_STATEMENTS,
```
Replace with:
```ts
  DATA_DIR,
  DISTINCT_LIMIT,
  INIT_STATEMENTS,
```

Find:
```ts
  buildFilteredQuery,
  buildPreloadStatements,
```
Replace with:
```ts
  buildDistinctAggregate,
  buildFilteredQuery,
  buildPreloadStatements,
```

Append to the end of the file:

```ts

describe('buildDistinctAggregate (A7)', () => {
  it('lists one more distinct value than the option cap, cast the way select filters cast', () => {
    expect(DISTINCT_LIMIT).toBe(501);
    expect(buildDistinctAggregate('region', columns)).toBe(
      'SELECT DISTINCT CAST("region" AS VARCHAR) AS v FROM data WHERE "region" IS NOT NULL LIMIT 501',
    );
  });

  it('refuses a column the chart does not declare or an unsafe name', () => {
    expect(() => buildDistinctAggregate('nope', columns)).toThrow('unknown column: nope');
    expect(() => buildDistinctAggregate('bad"col', [...columns, { name: 'bad"col', type: 'string' }])).toThrow(DuckDbError);
  });

  it('is a single SELECT that the filtered-query wrapper accepts', () => {
    const q = buildFilteredQuery(buildDistinctAggregate('day', columns), 'raw_x', columns, []);
    expect(q.sql).toBe(
      'WITH data AS (SELECT * FROM "raw_x") SELECT * FROM (SELECT DISTINCT CAST("day" AS VARCHAR) AS v FROM data WHERE "day" IS NOT NULL LIMIT 501) LIMIT 50000',
    );
  });
});
```

Edit `web/src/data/duckdbNode.test.ts`.

Find:
```ts
import { INIT_STATEMENTS, registeredFileName } from './duckdb';
```
Replace with:
```ts
import { INIT_STATEMENTS, buildDistinctAggregate, buildFilteredQuery, registeredFileName } from './duckdb';
```

Find the last line of the file:
```ts
  }, 60_000);
});
```
Replace with:
```ts
  }, 60_000);

  it('runs the distinct-values aggregate over a locked database (A7)', async () => {
    const { db, conn } = await lockedDb();
    const name = csvName('sales/y');
    db.registerFileBuffer(name, new TextEncoder().encode('region,amount\nEMEA,1\nNA,2\nEMEA,3\n,4\n'));
    conn.query(`CREATE TABLE "raw_sales_y" AS SELECT * FROM read_csv('${name}')`);
    const cols = [
      { name: 'region', type: 'string' as const },
      { name: 'amount', type: 'number' as const },
    ];
    const q = buildFilteredQuery(buildDistinctAggregate('region', cols), 'raw_sales_y', cols, []);
    const values = conn
      .query(q.sql)
      .toArray()
      .map((r) => String(r.toJSON().v))
      .sort();
    expect(values).toEqual(['EMEA', 'NA']);
    conn.close();
  }, 60_000);
});
```

- [ ] **Step 2: Write the failing tile test**

Edit `web/src/components/ChartTile.test.tsx`.

Find:
```ts
  getAdapter: vi.fn(),
  queryLargeLane: vi.fn(),
}));
```
Replace with:
```ts
  getAdapter: vi.fn(),
  queryLargeLane: vi.fn(),
  distinctValues: vi.fn(),
}));
```

Find:
```ts
vi.mock('../data/duckdb', () => ({ queryLargeLane: mocks.queryLargeLane }));
```
Replace with:
```ts
vi.mock('../data/duckdb', () => ({ queryLargeLane: mocks.queryLargeLane, distinctValues: mocks.distinctValues }));
```

Find:
```ts
  mocks.queryLargeLane.mockReset();
});
```
Replace with:
```ts
  mocks.queryLargeLane.mockReset();
  mocks.distinctValues.mockReset().mockResolvedValue([]);
});
```

Find:
```ts
describe('describeError', () => {
```
Replace with:
```ts
describe('ChartTile select options (A7)', () => {
  const large: Chart = {
    ...chart,
    data: { ...chart.data, lane: 'large', format: 'parquet' },
    aggregate: 'SELECT region, sum(revenue) AS revenue FROM data GROUP BY region',
  };

  it('reports the distinct values of each declared select column once, for the large lane', async () => {
    mocks.fetchChart.mockResolvedValue(large);
    mocks.queryLargeLane.mockResolvedValue([{ region: 'EMEA', revenue: 1 }]);
    mocks.distinctValues.mockResolvedValue(['EMEA', 'NA']);
    const onOptions = vi.fn();
    const { rerender } = render(<ChartTile chartId="sales/x" filters={[]} optionColumns={['region', 'month', 'region']} onOptions={onOptions} />);
    await waitFor(() => expect(onOptions).toHaveBeenCalledWith('sales/x', { region: ['EMEA', 'NA'] }));
    expect(mocks.distinctValues).toHaveBeenCalledTimes(1);
    expect(mocks.distinctValues).toHaveBeenCalledWith('sales/x', 'region', large.data.columns);

    const filter = { controlId: 'r', column: 'region', value: { type: 'select' as const, values: ['NA'] } };
    rerender(<ChartTile chartId="sales/x" filters={[filter]} optionColumns={['region', 'month', 'region']} onOptions={onOptions} />);
    await waitFor(() => expect(mocks.queryLargeLane).toHaveBeenCalledTimes(2));
    expect(mocks.distinctValues).toHaveBeenCalledTimes(1);
    expect(onOptions).toHaveBeenCalledTimes(1);
  });

  it('reports an empty set when the chart declares none of the columns', async () => {
    mocks.fetchChart.mockResolvedValue(large);
    mocks.queryLargeLane.mockResolvedValue([]);
    const onOptions = vi.fn();
    render(<ChartTile chartId="sales/x" filters={[]} optionColumns={['month']} onOptions={onOptions} />);
    await waitFor(() => expect(onOptions).toHaveBeenCalledWith('sales/x', {}));
    expect(mocks.distinctValues).not.toHaveBeenCalled();
  });

  it('never lists options for the small lane (onRows covers it)', async () => {
    mocks.fetchChart.mockResolvedValue(chart);
    mocks.fetchRows.mockResolvedValue(rows);
    const onOptions = vi.fn();
    render(<ChartTile chartId="sales/x" filters={[]} optionColumns={['region']} onOptions={onOptions} />);
    await waitFor(() => expect(tile().dataset.state).toBe('ready'));
    expect(mocks.distinctValues).not.toHaveBeenCalled();
    expect(onOptions).not.toHaveBeenCalled();
  });
});

describe('describeError', () => {
```

- [ ] **Step 3: Run the tests to see them fail**

Run from `web/`: `npm test -- src/data/duckdb src/components/ChartTile`
Expected: `buildDistinctAggregate (A7)` cases FAIL (`buildDistinctAggregate is not a function`), the Node distinct case FAILS the same way, the first two `ChartTile select options (A7)` cases FAIL (`onOptions` never called; typecheck-level props are ignored by vitest), the small-lane case passes.

- [ ] **Step 4: Add the distinct-values query to `web/src/data/duckdb.ts`**

Edit `web/src/data/duckdb.ts`.

Find:
```ts
import { isActive, type Filter } from './filters';
```
Replace with:
```ts
import { MAX_SELECT_OPTIONS, isActive, type Filter } from './filters';
```

Find the end of the file:
```ts
/** Run a chart's aggregate over its parquet file with the given filters. Serialized page-wide. */
export function queryLargeLane(chartId: string, aggregate: string, columns: Column[], filters: Filter[], timeoutMs = DEFAULT_TIMEOUT_MS): Promise<Row[]> {
  const next = chain.then(() => runQuery(chartId, aggregate, columns, filters, timeoutMs));
  chain = next.catch(() => undefined);
  return next;
}
```
Replace with:
```ts
/** Run a chart's aggregate over its parquet file with the given filters. Serialized page-wide. */
export function queryLargeLane(chartId: string, aggregate: string, columns: Column[], filters: Filter[], timeoutMs = DEFAULT_TIMEOUT_MS): Promise<Row[]> {
  const next = chain.then(() => runQuery(chartId, aggregate, columns, filters, timeoutMs));
  chain = next.catch(() => undefined);
  return next;
}

/** One more than the option cap, so "too many values" is still detected (finding A7). */
export const DISTINCT_LIMIT = MAX_SELECT_OPTIONS + 1;

/**
 * The aggregate that lists a column's distinct values for a select control.
 * The column is checked against the declared columns and the identifier
 * pattern before it is quoted into the SQL; no value is ever interpolated.
 */
export function buildDistinctAggregate(column: string, columns: Column[]): string {
  if (!COLUMN_NAME.test(column) || !columns.some((c) => c.name === column)) throw new DuckDbError(`unknown column: ${column}`);
  return `SELECT DISTINCT CAST("${column}" AS VARCHAR) AS v FROM data WHERE "${column}" IS NOT NULL LIMIT ${DISTINCT_LIMIT}`;
}

/** Distinct values of one column over a large-lane chart's unfiltered data, as strings. */
export async function distinctValues(chartId: string, column: string, columns: Column[], timeoutMs = DEFAULT_TIMEOUT_MS): Promise<string[]> {
  const aggregate = buildDistinctAggregate(column, columns);
  const rows = await queryLargeLane(chartId, aggregate, [{ name: 'v', type: 'string' }], [], timeoutMs);
  return rows.map((r) => String(r.v));
}
```

- [ ] **Step 5: Report options from `ChartTile`**

Edit `web/src/components/ChartTile.tsx`.

Find:
```ts
  showTitle?: boolean;
}
```
Replace with:
```ts
  /** Columns of the dashboard's select controls; a large-lane tile lists their distinct values (A7). */
  optionColumns?: string[];
  /** Called once per loaded large-lane chart with the distinct values of each declared option column. */
  onOptions?: (chartId: string, values: Record<string, string[]>) => void;
  showTitle?: boolean;
}
```

Find:
```ts
export function ChartTile({ chartId, filters, onRows, showTitle = true }: ChartTileProps) {
```
Replace with:
```ts
export function ChartTile({ chartId, filters, onRows, optionColumns, onOptions, showTitle = true }: ChartTileProps) {
```

Find:
```ts
  onRowsRef.current = onRows;
```
Replace with:
```ts
  onRowsRef.current = onRows;
  const onOptionsRef = useRef(onOptions);
  onOptionsRef.current = onOptions;
  const optionColumnsRef = useRef(optionColumns);
  optionColumnsRef.current = optionColumns;
```

Find:
```ts
  // Mount once, then update on every filter change. Operations are serialized.
```
Replace with:
```ts
  // Large lane (finding A7): list the distinct values of every select-control
  // column this chart declares, once per loaded chart, over the unfiltered
  // data, and report them so the control bar can offer them.
  useEffect(() => {
    if (!chart || chart.id !== chartId || chart.data.lane !== 'large') return;
    let cancelled = false;
    const declared = new Set(chart.data.columns.map((c) => c.name));
    const wanted = (optionColumnsRef.current ?? []).filter((column, i, all) => declared.has(column) && all.indexOf(column) === i);
    (async () => {
      try {
        const { distinctValues } = await import('../data/duckdb');
        const out: Record<string, string[]> = {};
        for (const column of wanted) out[column] = await distinctValues(chartId, column, chart.data.columns);
        if (!cancelled) onOptionsRef.current?.(chartId, out);
      } catch (err) {
        if (!cancelled) setError(describeError(err));
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [chart, chartId]);

  // Mount once, then update on every filter change. Operations are serialized.
```

- [ ] **Step 6: Run the tests to see them pass**

Run from `web/`: `npm test -- src/data/duckdb src/components/ChartTile`
Expected: all pass.

- [ ] **Step 7: Run the whole front-end suite and the typecheck**

Run from `web/`: `npm test` then `npm run typecheck`
Expected: both pass.

- [ ] **Step 8: Commit**

Run from the repo root:

```bash
git add web/src/data/duckdb.ts web/src/data/duckdb.test.ts web/src/data/duckdbNode.test.ts web/src/components/ChartTile.tsx web/src/components/ChartTile.test.tsx
git -c user.name="tripp" -c user.email="dom4domg@gmail.com" commit -m "feat: large-lane tiles report select options from SELECT DISTINCT (A7)" -m "Co-Authored-By: <model name from your harness> <noreply@anthropic.com>
Claude-Session: <session url from your harness>"
```

---

### Task 7: Dashboards list options from both lanes and keep deep-linked values (A7, A8)

**Files:**
- Modify: `web/src/pages/DashboardPage.tsx`, `web/src/pages/DashboardPage.test.tsx`, `web/src/components/ChartTile.tsx`, `web/src/components/ChartTile.test.tsx`, `web/src/components/ControlBar.tsx`, `web/src/components/ControlBar.test.tsx`

**Interfaces:**
- Consumes: `ChartTile` props `onRows`, `optionColumns`, `onOptions` (Task 6); `selectOptions(rowSets, column)` (caps at 500, returns `tooMany: true` above); `decodeFilters(params, controls, options, today)` (validates select values only for controls whose entry in `options` is defined); `encodeFilters(filters)`.
- Produces:
  - `ChartTileProps.onFailed?: (chartId: string) => void`, called whenever the tile enters its error state.
  - `DashboardPage`: a chart tile counts as reported after `onRows`, `onOptions` or `onFailed`. Select options merge small-lane rows and large-lane value lists. URL select values are validated against the options only once every chart tile in the layout has reported. `onChange(controlId, value)` writes the changed control from the new value and copies every other control's raw URL value unchanged.
  - `ControlBar`: a select lists the union of its options and its current values, sorted, so a value restored from the URL stays visible and selected while options are still arriving.

- [ ] **Step 1: Write the failing `onFailed` tile test**

Edit `web/src/components/ChartTile.test.tsx`.

Find:
```ts
describe('describeError', () => {
```
Replace with:
```ts
describe('ChartTile failure reporting (A8)', () => {
  it('reports a failed tile through onFailed', async () => {
    mocks.fetchChart.mockRejectedValue(new ApiError(404, 'not found'));
    const onFailed = vi.fn();
    render(<ChartTile chartId="sales/nope" filters={[]} onFailed={onFailed} />);
    await waitFor(() => expect(onFailed).toHaveBeenCalledWith('sales/nope'));
  });

  it('does not call onFailed for a tile that renders', async () => {
    mocks.fetchChart.mockResolvedValue(chart);
    mocks.fetchRows.mockResolvedValue(rows);
    const onFailed = vi.fn();
    render(<ChartTile chartId="sales/x" filters={[]} onFailed={onFailed} />);
    await waitFor(() => expect(tile().dataset.state).toBe('ready'));
    expect(onFailed).not.toHaveBeenCalled();
  });
});

describe('describeError', () => {
```

- [ ] **Step 2: Write the failing `ControlBar` test**

Append to the end of `web/src/components/ControlBar.test.tsx`:

```tsx

describe('ControlBar while options are still arriving (A8)', () => {
  it('keeps a current select value listed and selected even before the options include it', () => {
    render(
      <ControlBar
        controls={[controls[1]]}
        filters={[{ controlId: 'region', column: 'region', value: { type: 'select', values: ['LATAM'] } }]}
        options={{ region: { options: ['EMEA'], tooMany: false } }}
        onChange={() => undefined}
      />,
    );
    const region = screen.getByLabelText('Region') as HTMLSelectElement;
    expect(Array.from(region.options).map((o) => o.value)).toEqual(['EMEA', 'LATAM']);
    expect(Array.from(region.selectedOptions).map((o) => o.value)).toEqual(['LATAM']);
  });
});
```

- [ ] **Step 3: Write the failing dashboard tests**

Edit `web/src/pages/DashboardPage.test.tsx`.

Find:
```ts
    update: vi.fn(async (_rows: unknown[]) => undefined),
    destroy: vi.fn(),
  },
}));
```
Replace with:
```ts
    update: vi.fn(async (_rows: unknown[]) => undefined),
    destroy: vi.fn(),
  },
  queryLargeLane: vi.fn(),
  distinctValues: vi.fn(),
}));
```

Find:
```ts
vi.mock('../renderers', () => ({ getAdapter: () => mocks.adapter }));
```
Replace with:
```ts
vi.mock('../renderers', () => ({ getAdapter: () => mocks.adapter }));
vi.mock('../data/duckdb', () => ({ queryLargeLane: mocks.queryLargeLane, distinctValues: mocks.distinctValues }));
```

Find:
```ts
  mocks.adapter.mount.mockClear();
  mocks.adapter.update.mockClear();
});
```
Replace with:
```ts
  mocks.adapter.mount.mockClear();
  mocks.adapter.update.mockClear();
  mocks.queryLargeLane.mockReset().mockResolvedValue([]);
  mocks.distinctValues.mockReset().mockResolvedValue([]);
});

/** A promise this test can resolve on its own schedule. */
function deferred<T>(): { promise: Promise<T>; resolve: (value: T) => void } {
  let resolve: (value: T) => void = () => undefined;
  const promise = new Promise<T>((res) => {
    resolve = res;
  });
  return { promise, resolve };
}

function tileState(id: string): string | null | undefined {
  return document.querySelector(`[data-tile="${id}"]`)?.getAttribute('data-state');
}
```

Append to the end of the file:

```tsx

describe('DashboardPage select options and deep links (A7, A8)', () => {
  it('keeps a deep-linked select value while tiles are still loading, even when another control changes', async () => {
    const late = deferred<typeof rows>();
    mocks.fetchRows.mockImplementation(async (id: string) => (id === 'sales/total' ? late.promise : [rows[0]]));
    renderPage('/d/sales/overview?region=NA');
    await waitFor(() => expect(tileState('sales/revenue')).toBe('ready'));

    // Only EMEA has been reported so far. Editing another control must not drop region=NA.
    fireEvent.change(screen.getByLabelText('Period from'), { target: { value: '2026-01-01' } });
    await waitFor(() => expect(screen.getByTestId('search').textContent).toContain('period=2026-01-01..'));
    expect(screen.getByTestId('search').textContent).toContain('region=NA');

    late.resolve(rows);
    await waitFor(() => expect(document.querySelectorAll('[data-tile][data-state="ready"]')).toHaveLength(2));
    const region = screen.getByLabelText('Region') as HTMLSelectElement;
    await waitFor(() => expect(Array.from(region.options).map((o) => o.value)).toEqual(['EMEA', 'NA']));
    expect(Array.from(region.selectedOptions).map((o) => o.value)).toEqual(['NA']);
    expect(screen.getByTestId('search').textContent).toContain('region=NA');
  });

  it('lists select options from a large-lane chart and keeps a deep-linked value', async () => {
    const large: Chart = {
      ...chart,
      id: 'sales/lines',
      data: { ...chart.data, lane: 'large', format: 'parquet' },
      aggregate: 'SELECT month, sum(revenue) AS revenue FROM data GROUP BY month',
    };
    mocks.fetchDashboard.mockResolvedValue({ ...dashboard, layout: [{ chart: 'sales/lines', w: 12, h: 4 }] });
    mocks.fetchChart.mockResolvedValue(large);
    mocks.queryLargeLane.mockResolvedValue([{ month: '2026-01-01', revenue: 3 }]);
    mocks.distinctValues.mockResolvedValue(['APAC', 'EMEA']);
    renderPage('/d/sales/overview?region=APAC');
    await waitFor(() => expect(tileState('sales/lines')).toBe('ready'));
    const region = screen.getByLabelText('Region') as HTMLSelectElement;
    await waitFor(() => expect(Array.from(region.options).map((o) => o.value)).toEqual(['APAC', 'EMEA']));
    expect(Array.from(region.selectedOptions).map((o) => o.value)).toEqual(['APAC']);
    expect(mocks.distinctValues).toHaveBeenCalledWith('sales/lines', 'region', columns);
    expect(mocks.fetchRows).not.toHaveBeenCalled();
  });

  it('counts a failed tile as reported, so URL values are checked once the rest have loaded', async () => {
    mocks.fetchChart.mockImplementation(async (id: string) => {
      if (id === 'sales/total') throw new ApiError(404, 'not found');
      return chart;
    });
    renderPage('/d/sales/overview?region=APAC');
    await waitFor(() => expect(tileState('sales/revenue')).toBe('ready'));
    const region = screen.getByLabelText('Region') as HTMLSelectElement;
    await waitFor(() => expect(Array.from(region.options).map((o) => o.value)).toEqual(['EMEA', 'NA']));
    await waitFor(() => expect(document.querySelector('[data-tile="sales/revenue"]')?.getAttribute('data-rows')).toBe('2'));
  });
});
```

- [ ] **Step 4: Run the tests to see them fail**

Run from `web/`: `npm test -- src/pages/DashboardPage src/components/ChartTile src/components/ControlBar`
Expected: `reports a failed tile through onFailed` FAILS (never called), `keeps a current select value listed` FAILS (options are `['EMEA']`), `keeps a deep-linked select value while tiles are still loading` FAILS (the URL has `region=%3Anone`, the cleared marker, not `region=NA`), `lists select options from a large-lane chart` FAILS (options are `['APAC']`, `distinctValues` not called). `counts a failed tile as reported` may already pass; it guards the new code.

- [ ] **Step 5: Report failures from `ChartTile`**

Edit `web/src/components/ChartTile.tsx`.

Find:
```ts
  showTitle?: boolean;
}
```
Replace with:
```ts
  /** Called when the tile shows its error card, so a dashboard stops waiting for it (A8). */
  onFailed?: (chartId: string) => void;
  showTitle?: boolean;
}
```

Find:
```ts
export function ChartTile({ chartId, filters, onRows, optionColumns, onOptions, showTitle = true }: ChartTileProps) {
```
Replace with:
```ts
export function ChartTile({ chartId, filters, onRows, optionColumns, onOptions, onFailed, showTitle = true }: ChartTileProps) {
```

Find:
```ts
  onRowsRef.current = onRows;
```
Replace with:
```ts
  onRowsRef.current = onRows;
  const onFailedRef = useRef(onFailed);
  onFailedRef.current = onFailed;
```

Find:
```ts
  // Mount once, then update on every filter change. Operations are serialized.
```
Replace with:
```ts
  // Finding A8: a failed tile will never report rows or options; say so.
  useEffect(() => {
    if (error) onFailedRef.current?.(chartId);
  }, [error, chartId]);

  // Mount once, then update on every filter change. Operations are serialized.
```

- [ ] **Step 6: Keep current values listed in `ControlBar`**

Edit `web/src/components/ControlBar.tsx`.

Find:
```ts
    const list = opts?.options ?? value.values;
```
Replace with:
```ts
    // Finding A8: a value restored from the URL stays listed (and selected)
    // while the tiles are still reporting their options.
    const list = opts ? [...new Set([...opts.options, ...value.values])].sort() : value.values;
```

- [ ] **Step 7: Rewrite `DashboardPage`**

Write `web/src/pages/DashboardPage.tsx` (Write tool) with this full content:

```tsx
import { useCallback, useEffect, useMemo, useState } from 'react';
import { useParams, useSearchParams } from 'react-router-dom';
import { fetchDashboard } from '../api/client';
import type { Dashboard, Row } from '../api/types';
import { ChartTile, describeError } from '../components/ChartTile';
import { ControlBar } from '../components/ControlBar';
import { ErrorCard } from '../components/ErrorCard';
import { Markdown } from '../components/Markdown';
import { selectOptions, type FilterValue, type SelectOptions } from '../data/filters';
import { decodeFilters, encodeFilters } from '../state/urlState';

/** Distinct values one large-lane tile reported, by column name (finding A7). */
type ValueLists = Record<string, string[]>;

export function DashboardPage() {
  const id = useParams()['*'] ?? '';
  const [dashboard, setDashboard] = useState<Dashboard | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [rowsByChart, setRowsByChart] = useState<Record<string, Row[]>>({});
  const [valuesByChart, setValuesByChart] = useState<Record<string, ValueLists>>({});
  const [reported, setReported] = useState<Record<string, boolean>>({});
  const [searchParams, setSearchParams] = useSearchParams();
  const today = useMemo(() => new Date(), []);

  useEffect(() => {
    let cancelled = false;
    setDashboard(null);
    setError(null);
    setRowsByChart({});
    setValuesByChart({});
    setReported({});
    fetchDashboard(id)
      .then((doc) => {
        if (!cancelled) setDashboard(doc);
      })
      .catch((err: unknown) => {
        if (!cancelled) setError(describeError(err));
      });
    return () => {
      cancelled = true;
    };
  }, [id]);

  const controls = useMemo(() => dashboard?.controls ?? [], [dashboard]);
  const selectColumns = useMemo(() => controls.filter((c) => c.type === 'select').map((c) => c.column), [controls]);
  const chartIds = useMemo(() => {
    const ids: string[] = [];
    for (const tile of dashboard?.layout ?? []) if ('chart' in tile && !ids.includes(tile.chart)) ids.push(tile.chart);
    return ids;
  }, [dashboard]);

  // Finding A8: until every chart tile has reported its rows, its options or
  // its failure, the option lists are incomplete, so select values restored
  // from the URL are not checked against them yet.
  const allReported = chartIds.every((chartId) => reported[chartId] === true);

  // Small-lane tiles report rows; large-lane tiles report distinct values per
  // column (finding A7). Both feed the same capped option list.
  const options = useMemo(() => {
    const out: Record<string, SelectOptions | undefined> = {};
    const rowSets = Object.values(rowsByChart);
    const valueSets = Object.values(valuesByChart);
    if (rowSets.length === 0 && valueSets.length === 0) return out;
    for (const c of controls) {
      if (c.type !== 'select') continue;
      const fromLarge: Row[][] = [];
      for (const lists of valueSets) {
        const values = lists[c.column];
        if (values) fromLarge.push(values.map((v) => ({ [c.column]: v })));
      }
      out[c.id] = selectOptions([...rowSets, ...fromLarge], c.column);
    }
    return out;
  }, [controls, rowsByChart, valuesByChart]);

  const filters = useMemo(
    () => decodeFilters(searchParams, controls, allReported ? options : {}, today),
    [searchParams, controls, options, allReported, today],
  );

  const onChange = useCallback(
    (controlId: string, value: FilterValue) => {
      const next = encodeFilters(filters.map((f) => (f.controlId === controlId ? { ...f, value } : f)));
      // Finding A8: every control the user did not touch keeps exactly the
      // value the URL has, even one not (yet) among the reported options.
      for (const control of controls) {
        if (control.id === controlId) continue;
        const raw = searchParams.get(control.id);
        if (raw !== null) next.set(control.id, raw);
      }
      setSearchParams(next, { replace: true });
    },
    [filters, controls, searchParams, setSearchParams],
  );

  const onRows = useCallback((chartId: string, rows: Row[]) => {
    setRowsByChart((prev) => ({ ...prev, [chartId]: rows }));
    setReported((prev) => ({ ...prev, [chartId]: true }));
  }, []);

  const onOptions = useCallback((chartId: string, values: ValueLists) => {
    setValuesByChart((prev) => ({ ...prev, [chartId]: values }));
    setReported((prev) => ({ ...prev, [chartId]: true }));
  }, []);

  const onFailed = useCallback((chartId: string) => {
    setReported((prev) => ({ ...prev, [chartId]: true }));
  }, []);

  if (error) return <ErrorCard id={id} reason={error} />;
  if (!dashboard) return <div className="muted">Loading…</div>;

  return (
    <div className="dashboard-page">
      <h2>{dashboard.title}</h2>
      {dashboard.description && <Markdown text={dashboard.description} />}
      {controls.length > 0 && <ControlBar controls={controls} filters={filters} options={options} onChange={onChange} />}
      <div className="grid">
        {dashboard.layout.map((tile, i) => {
          const style = { gridColumn: `span ${tile.w}`, gridRow: `span ${tile.h}` };
          if ('markdown' in tile) {
            return (
              <div key={`md-${i}`} className="grid-cell" style={style}>
                <div className="tile tile-markdown">
                  <Markdown text={tile.markdown} />
                </div>
              </div>
            );
          }
          return (
            <div key={`${tile.chart}-${i}`} className="grid-cell" style={style}>
              <ChartTile chartId={tile.chart} filters={filters} onRows={onRows} onOptions={onOptions} onFailed={onFailed} optionColumns={selectColumns} />
            </div>
          );
        })}
      </div>
    </div>
  );
}
```

- [ ] **Step 8: Run the tests to see them pass**

Run from `web/`: `npm test -- src/pages/DashboardPage src/components/ChartTile src/components/ControlBar`
Expected: all pass, including the existing `drops a region value from the URL that is not among the reported rows`.

- [ ] **Step 9: Run the whole front-end suite and the typecheck**

Run from `web/`: `npm test` then `npm run typecheck`
Expected: both pass.

- [ ] **Step 10: Commit**

Run from the repo root:

```bash
git add web/src/pages/DashboardPage.tsx web/src/pages/DashboardPage.test.tsx web/src/components/ChartTile.tsx web/src/components/ChartTile.test.tsx web/src/components/ControlBar.tsx web/src/components/ControlBar.test.tsx
git -c user.name="tripp" -c user.email="dom4domg@gmail.com" commit -m "fix: dashboards list large-lane options and keep deep-linked values until every tile reports (A7, A8)" -m "Co-Authored-By: <model name from your harness> <noreply@anthropic.com>
Claude-Session: <session url from your harness>"
```

---

### Task 8: Empty state and "not filtered by" badges (A9)

**Files:**
- Modify: `web/src/components/ChartTile.tsx`, `web/src/components/ChartTile.test.tsx`, `web/src/pages/DashboardPage.tsx`, `web/src/pages/DashboardPage.test.tsx`, `web/src/styles.css`

**Interfaces:**
- Consumes: `isActive(value)` from `web/src/data/filters.ts`; `Filter` (`controlId`, `column`, `value`); the tile's `filtered` rows and `rendered` flag.
- Produces:
  - `ChartTileProps.controlLabels?: Record<string, string>` (control id to label).
  - When the tile has rendered and its filtered rows are empty: `div.tile-empty` inside `.tile-body` with the text `No rows match the filters` when at least one active filter applies to this chart, else `No rows`.
  - A `div.tile-footer` after `.tile-body`. For every active filter whose column the chart does not declare: `span.badge.tile-badge` with the text `not filtered by <label>` (label from `controlLabels`, falling back to the control id).
  - `DashboardPage` passes `controlLabels` built from its controls.

- [ ] **Step 1: Write the failing tile tests**

Edit `web/src/components/ChartTile.test.tsx`.

Find:
```ts
describe('describeError', () => {
```
Replace with:
```ts
describe('ChartTile empty state and badges (A9)', () => {
  const periodOn = { controlId: 'period', column: 'month', value: { type: 'date-range' as const, from: '2026-01-01', to: null } };
  const daysOff = { controlId: 'days', column: 'day', value: { type: 'date-range' as const, from: null, to: null } };
  const regionNA = { controlId: 'r', column: 'region', value: { type: 'select' as const, values: ['NA'] } };
  const regionAPAC = { controlId: 'r', column: 'region', value: { type: 'select' as const, values: ['APAC'] } };

  it('says so when the filters leave no rows', async () => {
    mocks.fetchChart.mockResolvedValue(chart);
    mocks.fetchRows.mockResolvedValue(rows);
    render(<ChartTile chartId="sales/x" filters={[regionAPAC]} />);
    await waitFor(() => expect(tile().dataset.state).toBe('ready'));
    expect(tile().dataset.rows).toBe('0');
    expect(screen.getByText('No rows match the filters')).toBeInTheDocument();
  });

  it('says "No rows" when the chart has no rows and no filter applies', async () => {
    mocks.fetchChart.mockResolvedValue(chart);
    mocks.fetchRows.mockResolvedValue([]);
    render(<ChartTile chartId="sales/x" filters={[]} />);
    await waitFor(() => expect(tile().dataset.state).toBe('ready'));
    expect(screen.getByText('No rows')).toBeInTheDocument();
    expect(screen.queryByText('No rows match the filters')).toBeNull();
  });

  it('shows no empty state while rows remain', async () => {
    mocks.fetchChart.mockResolvedValue(chart);
    mocks.fetchRows.mockResolvedValue(rows);
    render(<ChartTile chartId="sales/x" filters={[regionNA]} />);
    await waitFor(() => expect(tile().dataset.state).toBe('ready'));
    expect(screen.queryByText('No rows match the filters')).toBeNull();
  });

  it('badges each active control whose column the chart does not declare', async () => {
    mocks.fetchChart.mockResolvedValue(chart);
    mocks.fetchRows.mockResolvedValue(rows);
    render(<ChartTile chartId="sales/x" filters={[periodOn, daysOff, regionNA]} controlLabels={{ period: 'Period', days: 'Days', r: 'Region' }} />);
    await waitFor(() => expect(tile().dataset.state).toBe('ready'));
    expect(screen.getByText('not filtered by Period')).toBeInTheDocument();
    expect(screen.queryByText('not filtered by Days')).toBeNull();
    expect(screen.queryByText('not filtered by Region')).toBeNull();
  });

  it('falls back to the control id without labels', async () => {
    mocks.fetchChart.mockResolvedValue(chart);
    mocks.fetchRows.mockResolvedValue(rows);
    render(<ChartTile chartId="sales/x" filters={[periodOn]} />);
    await waitFor(() => expect(tile().dataset.state).toBe('ready'));
    expect(screen.getByText('not filtered by period')).toBeInTheDocument();
  });
});

describe('describeError', () => {
```

- [ ] **Step 2: Write the failing dashboard test**

Append to the end of `web/src/pages/DashboardPage.test.tsx`:

```tsx

describe('DashboardPage badges (A9)', () => {
  it('labels the badge of a tile that ignores an active control', async () => {
    const noMonth: Chart = { ...stat, data: { ...stat.data, columns: columns.filter((c) => c.name !== 'month') } };
    mocks.fetchChart.mockImplementation(async (id: string) => (id === 'sales/total' ? noMonth : chart));
    renderPage('/d/sales/overview?period=2026-01-01..2026-12-31');
    await waitFor(() => expect(document.querySelectorAll('[data-tile][data-state="ready"]')).toHaveLength(2));
    expect(screen.getByText('not filtered by Period')).toBeInTheDocument();
    expect(screen.getAllByText(/^not filtered by/)).toHaveLength(1);
  });
});
```

- [ ] **Step 3: Run the tests to see them fail**

Run from `web/`: `npm test -- src/components/ChartTile src/pages/DashboardPage`
Expected: `says so when the filters leave no rows`, `says "No rows"`, `badges each active control`, `falls back to the control id` and `labels the badge` FAIL (no such text). `shows no empty state while rows remain` passes.

- [ ] **Step 4: Add the empty state and badges to `ChartTile`**

Edit `web/src/components/ChartTile.tsx`.

Find:
```ts
import { applyFilters, filterKey, type Filter } from '../data/filters';
```
Replace with:
```ts
import { applyFilters, filterKey, isActive, type Filter } from '../data/filters';
```

Find:
```ts
  showTitle?: boolean;
}
```
Replace with:
```ts
  /** Control labels by control id, for the "not filtered by" badges (A9). */
  controlLabels?: Record<string, string>;
  showTitle?: boolean;
}
```

Find:
```ts
export function ChartTile({ chartId, filters, onRows, optionColumns, onOptions, onFailed, showTitle = true }: ChartTileProps) {
```
Replace with:
```ts
export function ChartTile({ chartId, filters, onRows, optionColumns, onOptions, onFailed, controlLabels, showTitle = true }: ChartTileProps) {
```

Find:
```ts
  const state = error ? 'error' : rendered ? 'ready' : 'loading';
```
Replace with:
```ts
  // Finding A9: an empty result says so, and the tile names every active
  // control it ignores because it does not declare that control's column.
  const declared = new Set(chart ? chart.data.columns.map((c) => c.name) : []);
  const activeFilters = chart ? filters.filter((f) => isActive(f.value)) : [];
  const ignored = activeFilters.filter((f) => !declared.has(f.column));
  const appliedCount = activeFilters.length - ignored.length;
  const empty = !error && rendered && filtered !== null && filtered.length === 0;

  const state = error ? 'error' : rendered ? 'ready' : 'loading';
```

Find:
```tsx
        {!error && !rendered && <div className="muted tile-loading">Loading…</div>}
      </div>
    </div>
  );
```
Replace with:
```tsx
        {!error && !rendered && <div className="muted tile-loading">Loading…</div>}
        {empty && <div className="tile-empty muted">{appliedCount > 0 ? 'No rows match the filters' : 'No rows'}</div>}
      </div>
      <div className="tile-footer">
        {ignored.map((f) => (
          <span key={f.controlId} className="badge tile-badge">{`not filtered by ${controlLabels?.[f.controlId] ?? f.controlId}`}</span>
        ))}
      </div>
    </div>
  );
```

- [ ] **Step 5: Pass labels from `DashboardPage`**

Edit `web/src/pages/DashboardPage.tsx`.

Find:
```ts
  const selectColumns = useMemo(() => controls.filter((c) => c.type === 'select').map((c) => c.column), [controls]);
```
Replace with:
```ts
  const selectColumns = useMemo(() => controls.filter((c) => c.type === 'select').map((c) => c.column), [controls]);
  const controlLabels = useMemo(() => Object.fromEntries(controls.map((c) => [c.id, c.label])), [controls]);
```

Find:
```tsx
              <ChartTile chartId={tile.chart} filters={filters} onRows={onRows} onOptions={onOptions} onFailed={onFailed} optionColumns={selectColumns} />
```
Replace with:
```tsx
              <ChartTile
                chartId={tile.chart}
                filters={filters}
                onRows={onRows}
                onOptions={onOptions}
                onFailed={onFailed}
                optionColumns={selectColumns}
                controlLabels={controlLabels}
              />
```

- [ ] **Step 6: Style the empty state and footer**

Append to `web/src/styles.css`:

```css

/* Empty state and tile footer (plan 5c, findings A9 and A10). */
.tile-empty { position: absolute; inset: 0; z-index: 1; display: flex; align-items: center; justify-content: center; background: rgba(255, 255, 255, 0.85); font-size: 13px; }
.tile-footer { display: flex; align-items: center; gap: 8px; margin-top: 4px; font-size: 11px; white-space: nowrap; overflow: hidden; }
.tile-footer:empty { display: none; }
.tile-badge { margin-left: 0; }
```

- [ ] **Step 7: Run the tests to see them pass**

Run from `web/`: `npm test -- src/components/ChartTile src/pages/DashboardPage`
Expected: all pass.

- [ ] **Step 8: Run the whole front-end suite and the typecheck**

Run from `web/`: `npm test` then `npm run typecheck`
Expected: both pass.

- [ ] **Step 9: Commit**

Run from the repo root:

```bash
git add web/src/components/ChartTile.tsx web/src/components/ChartTile.test.tsx web/src/pages/DashboardPage.tsx web/src/pages/DashboardPage.test.tsx web/src/styles.css
git -c user.name="tripp" -c user.email="dom4domg@gmail.com" commit -m "feat: empty state and not-filtered-by badges on tiles (A9)" -m "Co-Authored-By: <model name from your harness> <noreply@anthropic.com>
Claude-Session: <session url from your harness>"
```

---

### Task 9: Download link, `aria-label` and "Data as of" on every tile (A10, freshness)

**Files:**
- Create: `web/src/components/freshness.ts`, `web/src/components/freshness.test.ts`
- Modify: `web/src/components/ChartTile.tsx`, `web/src/components/ChartTile.test.tsx`, `web/src/styles.css`

**Interfaces:**
- Consumes: `dataUrl(id)` from `web/src/api/client.ts` (returns `/api/data/<id>`; the server answers with `Content-Disposition: attachment`); `Chart.title`, `Chart.description`, `Chart.updated_at`.
- Produces:
  - `export function formatDataAsOf(iso: string | null | undefined): string | null` returns `YYYY-MM-DD HH:MM UTC` for a readable timestamp and `null` otherwise.
  - The tile's mount element (`div.tile-mount`, Vega-Lite charts) gets `role="img"` and `aria-label` = `<title>. <description>` (or just `<title>` without a description).
  - The tile footer gains `span.tile-asof` with `Data as of <formatted>` when `updated_at` is readable, and, once the chart document has loaded, `a.tile-download` with the text `Download data`, `href="/api/data/<id>"` and the `download` attribute. The footer sits outside the renderer branch, so stat tiles show both too (a test pins it).

- [ ] **Step 1: Write the failing tests**

Write `web/src/components/freshness.test.ts` (Write tool):

```ts
import { describe, expect, it } from 'vitest';
import { formatDataAsOf } from './freshness';

describe('formatDataAsOf', () => {
  it('formats an ISO timestamp as UTC minutes', () => {
    expect(formatDataAsOf('2026-09-22T10:00:00Z')).toBe('2026-09-22 10:00 UTC');
    expect(formatDataAsOf('2026-09-22T12:30:45+02:00')).toBe('2026-09-22 10:30 UTC');
    expect(formatDataAsOf('2026-01-05T03:04:00.123Z')).toBe('2026-01-05 03:04 UTC');
  });

  it('returns null for a missing or unreadable value', () => {
    expect(formatDataAsOf(undefined)).toBeNull();
    expect(formatDataAsOf(null)).toBeNull();
    expect(formatDataAsOf('')).toBeNull();
    expect(formatDataAsOf('yesterday')).toBeNull();
  });
});
```

Edit `web/src/components/ChartTile.test.tsx`.

Find:
```ts
describe('describeError', () => {
```
Replace with:
```ts
describe('ChartTile download, label and freshness (A10)', () => {
  const described: Chart = { ...chart, description: 'Monthly revenue.', updated_at: '2026-09-22T10:00:00Z' };

  it('links the data file, labels the chart for screen readers and shows when the data is from', async () => {
    mocks.fetchChart.mockResolvedValue(described);
    mocks.fetchRows.mockResolvedValue(rows);
    render(<ChartTile chartId="sales/x" filters={[]} />);
    await waitFor(() => expect(tile().dataset.state).toBe('ready'));
    const link = screen.getByRole('link', { name: 'Download data' });
    expect(link).toHaveAttribute('href', '/api/data/sales/x');
    expect(link).toHaveAttribute('download');
    expect(screen.getByRole('img', { name: 'Revenue. Monthly revenue.' })).toBe(tile().querySelector('.tile-mount'));
    expect(screen.getByText('Data as of 2026-09-22 10:00 UTC')).toBeInTheDocument();
  });

  it('uses the title alone without a description and skips an unreadable timestamp', async () => {
    mocks.fetchChart.mockResolvedValue({ ...chart, updated_at: 'not a date' });
    mocks.fetchRows.mockResolvedValue(rows);
    render(<ChartTile chartId="sales/x" filters={[]} />);
    await waitFor(() => expect(tile().dataset.state).toBe('ready'));
    expect(screen.getByRole('img', { name: 'Revenue' })).toBeInTheDocument();
    expect(screen.queryByText(/^Data as of/)).toBeNull();
  });

  it('has no download link when the chart document failed to load', async () => {
    mocks.fetchChart.mockRejectedValue(new ApiError(404, 'not found'));
    render(<ChartTile chartId="sales/nope" filters={[]} />);
    await screen.findByRole('alert');
    expect(screen.queryByRole('link', { name: 'Download data' })).toBeNull();
  });

  it('shows the data-as-of line and the download link on a stat tile too', async () => {
    mocks.fetchChart.mockResolvedValue({ ...described, renderer: 'stat', spec: { value: 'revenue', agg: 'sum' } });
    mocks.fetchRows.mockResolvedValue(rows);
    render(<ChartTile chartId="sales/x" filters={[]} />);
    await waitFor(() => expect(tile().dataset.state).toBe('ready'));
    expect(screen.getByTestId('stat-value')).toHaveTextContent('3');
    expect(screen.getByText('Data as of 2026-09-22 10:00 UTC')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Download data' })).toHaveAttribute('href', '/api/data/sales/x');
  });
});

describe('describeError', () => {
```

- [ ] **Step 2: Run the tests to see them fail**

Run from `web/`: `npm test -- src/components/freshness src/components/ChartTile`
Expected: `freshness.test.ts` FAILS (cannot resolve `./freshness`); the first two `ChartTile download, label and freshness (A10)` cases FAIL (no link, no `img` role); `shows the data-as-of line and the download link on a stat tile too` FAILS (no such text); the third passes.

- [ ] **Step 3: Write `freshness.ts`**

Write `web/src/components/freshness.ts` (Write tool):

```ts
// "Data as of" text for tiles and the chart page. v1 has no refresher, so the
// publish time (`updated_at`) is when the data was last loaded.

function pad(n: number): string {
  return String(n).padStart(2, '0');
}

/** `YYYY-MM-DD HH:MM UTC` for a readable ISO timestamp, otherwise null. */
export function formatDataAsOf(iso: string | null | undefined): string | null {
  if (!iso) return null;
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return null;
  return `${d.getUTCFullYear()}-${pad(d.getUTCMonth() + 1)}-${pad(d.getUTCDate())} ${pad(d.getUTCHours())}:${pad(d.getUTCMinutes())} UTC`;
}
```

- [ ] **Step 4: Add the label, the freshness line and the link to `ChartTile`**

Edit `web/src/components/ChartTile.tsx`.

Find:
```ts
import { ApiError, DataTooLarge, fetchChart, fetchRows } from '../api/client';
```
Replace with:
```ts
import { ApiError, DataTooLarge, dataUrl, fetchChart, fetchRows } from '../api/client';
```

Find:
```ts
import { ErrorCard } from './ErrorCard';
```
Replace with:
```ts
import { ErrorCard } from './ErrorCard';
import { formatDataAsOf } from './freshness';
```

Find:
```ts
  const state = error ? 'error' : rendered ? 'ready' : 'loading';
```
Replace with:
```ts
  // Finding A10: a text alternative for the canvas and a link to the data
  // file; plus when the data was published (no refresher runs in v1).
  const ariaLabel = chart ? (chart.description ? `${chart.title}. ${chart.description}` : chart.title) : chartId;
  const asOf = formatDataAsOf(chart?.updated_at);

  const state = error ? 'error' : rendered ? 'ready' : 'loading';
```

Find:
```tsx
          <div className="tile-mount" ref={mountRef} />
```
Replace with:
```tsx
          <div className="tile-mount" ref={mountRef} role="img" aria-label={ariaLabel} />
```

Find:
```tsx
          <span key={f.controlId} className="badge tile-badge">{`not filtered by ${controlLabels?.[f.controlId] ?? f.controlId}`}</span>
        ))}
      </div>
```
Replace with:
```tsx
          <span key={f.controlId} className="badge tile-badge">{`not filtered by ${controlLabels?.[f.controlId] ?? f.controlId}`}</span>
        ))}
        {asOf && <span className="muted tile-asof">{`Data as of ${asOf}`}</span>}
        {chart && (
          <a className="tile-download" href={dataUrl(chartId)} download>
            Download data
          </a>
        )}
      </div>
```

- [ ] **Step 5: Style the link**

Append to `web/src/styles.css`:

```css
.tile-download { margin-left: auto; }
```

- [ ] **Step 6: Run the tests to see them pass**

Run from `web/`: `npm test -- src/components/freshness src/components/ChartTile`
Expected: all pass.

- [ ] **Step 7: Run the whole front-end suite and the typecheck**

Run from `web/`: `npm test` then `npm run typecheck`
Expected: both pass.

- [ ] **Step 8: Commit**

Run from the repo root:

```bash
git add web/src/components/freshness.ts web/src/components/freshness.test.ts web/src/components/ChartTile.tsx web/src/components/ChartTile.test.tsx web/src/styles.css
git -c user.name="tripp" -c user.email="dom4domg@gmail.com" commit -m "feat: download link, aria-label and data-as-of line on every tile (A10)" -m "Co-Authored-By: <model name from your harness> <noreply@anthropic.com>
Claude-Session: <session url from your harness>"
```

---

### Task 10: Chart page fetches once and stops promising refreshes (A12, refresh text)

**Files:**
- Modify: `web/src/components/ChartTile.tsx`, `web/src/components/ChartTile.test.tsx`, `web/src/pages/ChartPage.tsx`, `web/src/pages/ChartPage.test.tsx`

**Interfaces:**
- Consumes: `fetchChart(id)`; the server already replaces `source` with `{kind, show_sql: false}` when `show_sql` is false (`viz/server/documents.py`); the tile footer's "Data as of" line (Task 9).
- Produces:
  - `ChartTileProps.chart?: Chart`: when given and its `id` equals `chartId`, the tile uses it instead of calling `fetchChart`.
  - `ChartPage` fetches the chart once, shows "Loading…" until then, passes the document to its tile, shows `Source: Databricks SQL` when `source` exists, shows the SQL only when `source.show_sql === true` and `source.sql` is a non-empty string, and never mentions "Refreshable" or a schedule. The data-as-of line comes from the tile footer.

- [ ] **Step 1: Write the failing tests**

Edit `web/src/components/ChartTile.test.tsx`.

Find:
```ts
describe('describeError', () => {
```
Replace with:
```ts
describe('ChartTile with a preloaded chart (A12)', () => {
  it('does not fetch the chart document again', async () => {
    mocks.fetchRows.mockResolvedValue(rows);
    render(<ChartTile chartId="sales/x" chart={chart} filters={[]} />);
    await waitFor(() => expect(tile().dataset.state).toBe('ready'));
    expect(mocks.fetchChart).not.toHaveBeenCalled();
    expect(mocks.fetchRows).toHaveBeenCalledWith('sales/x');
  });

  it('ignores a preloaded document for a different id', async () => {
    mocks.fetchChart.mockResolvedValue({ ...chart, id: 'sales/y' });
    mocks.fetchRows.mockResolvedValue(rows);
    render(<ChartTile chartId="sales/y" chart={chart} filters={[]} />);
    await waitFor(() => expect(tile('sales/y').dataset.state).toBe('ready'));
    expect(mocks.fetchChart).toHaveBeenCalledWith('sales/y');
  });
});

describe('describeError', () => {
```

Write `web/src/pages/ChartPage.test.tsx` (Write tool) with this full content:

```tsx
import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { Chart } from '../api/types';
import { ChartPage } from './ChartPage';

const mocks = vi.hoisted(() => ({
  fetchChart: vi.fn(),
  fetchRows: vi.fn(),
  adapter: { mount: vi.fn(async () => undefined), update: vi.fn(async () => undefined), destroy: vi.fn() },
}));
vi.mock('../api/client', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../api/client')>()),
  fetchChart: mocks.fetchChart,
  fetchRows: mocks.fetchRows,
}));
vi.mock('../renderers', () => ({ getAdapter: () => mocks.adapter }));

const chart: Chart = {
  schema_version: 1, id: 'sales/revenue', title: 'Revenue', description: 'Monthly *revenue*.', renderer: 'vega-lite',
  updated_at: '2026-09-22T10:00:00Z',
  spec: { data: { name: 'data' }, mark: 'line' },
  data: { format: 'json', file: 'data.0123456789abcdef.json', lane: 'small', rows: 1, bytes: 1, columns: [{ name: 'month', type: 'date' }, { name: 'revenue', type: 'number' }] },
  aggregate: null,
  source: { kind: 'databricks-sql', sql: 'SELECT month, revenue FROM t', show_sql: true, schedule: '0 6 * * *' },
};

function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/c/*" element={<ChartPage />} />
      </Routes>
    </MemoryRouter>,
  );
}

function tileState(): string | null | undefined {
  return document.querySelector('[data-tile="sales/revenue"]')?.getAttribute('data-state');
}

beforeEach(() => {
  mocks.fetchChart.mockReset().mockResolvedValue(chart);
  mocks.fetchRows.mockReset().mockResolvedValue([{ month: '2026-01-01', revenue: 1 }]);
});

describe('ChartPage', () => {
  it('shows title, description, columns, source and SQL when show_sql is true', async () => {
    renderAt('/c/sales/revenue');
    expect(await screen.findByRole('heading', { name: 'Revenue' })).toBeInTheDocument();
    expect(screen.getByText('revenue', { selector: 'em' })).toBeInTheDocument();
    expect(screen.getByRole('cell', { name: 'month' })).toBeInTheDocument();
    expect(screen.getByText('Source: Databricks SQL')).toBeInTheDocument();
    expect(screen.getByText('SELECT month, revenue FROM t').tagName).toBe('PRE');
    expect(screen.queryByText('static')).toBeNull();
    await waitFor(() => expect(tileState()).toBe('ready'));
  });

  it('fetches the chart document exactly once (A12)', async () => {
    renderAt('/c/sales/revenue');
    await waitFor(() => expect(tileState()).toBe('ready'));
    expect(mocks.fetchChart).toHaveBeenCalledTimes(1);
  });

  it('never promises a refresh or a schedule, and shows when the data is from', async () => {
    renderAt('/c/sales/revenue');
    await waitFor(() => expect(tileState()).toBe('ready'));
    expect(screen.queryByText(/Refreshable/)).toBeNull();
    expect(screen.queryByText(/schedule/)).toBeNull();
    expect(screen.queryByText(/0 6 \* \* \*/)).toBeNull();
    expect(screen.getByText('Data as of 2026-09-22 10:00 UTC')).toBeInTheDocument();
  });

  it('hides the SQL unless show_sql is true', async () => {
    mocks.fetchChart.mockResolvedValue({ ...chart, source: { kind: 'databricks-sql', sql: 'SELECT secret FROM t', show_sql: false } });
    renderAt('/c/sales/revenue');
    expect(await screen.findByText('Source: Databricks SQL')).toBeInTheDocument();
    expect(screen.queryByText('SELECT secret FROM t')).toBeNull();
    expect(document.querySelector('pre.sql')).toBeNull();
  });

  it('shows the static badge and no source line for a one-off chart', async () => {
    mocks.fetchChart.mockResolvedValue({ ...chart, source: undefined });
    renderAt('/c/sales/revenue');
    expect(await screen.findByText('static')).toBeInTheDocument();
    expect(screen.queryByText('Source: Databricks SQL')).toBeNull();
  });

  it('shows an error card when the chart is missing', async () => {
    mocks.fetchChart.mockRejectedValue(new Error('nope'));
    renderAt('/c/sales/x');
    expect((await screen.findAllByRole('alert')).length).toBeGreaterThan(0);
  });
});
```

- [ ] **Step 2: Run the tests to see them fail**

Run from `web/`: `npm test -- src/components/ChartTile src/pages/ChartPage`
Expected: `does not fetch the chart document again` FAILS (`fetchChart` called), `fetches the chart document exactly once` FAILS (called twice), `shows title, description, columns, source and SQL` FAILS (no "Source: Databricks SQL"), `hides the SQL unless show_sql is true` FAILS (no "Source: Databricks SQL", and the SQL is shown). `never promises a refresh` may already pass (the old page prints "Refreshable ..." only when the SQL is hidden, and Task 9 already added "Data as of"); it guards the new page. The rest pass.

- [ ] **Step 3: Accept a preloaded chart in `ChartTile`**

Edit `web/src/components/ChartTile.tsx`.

Find:
```ts
  showTitle?: boolean;
}
```
Replace with:
```ts
  /** A chart document the caller already fetched; the tile then skips its own fetch (A12). */
  chart?: Chart;
  showTitle?: boolean;
}
```

Find:
```ts
export function ChartTile({ chartId, filters, onRows, optionColumns, onOptions, onFailed, controlLabels, showTitle = true }: ChartTileProps) {
```
Replace with:
```ts
export function ChartTile({ chartId, chart: preloadedChart, filters, onRows, optionColumns, onOptions, onFailed, controlLabels, showTitle = true }: ChartTileProps) {
```

Find:
```ts
  onRowsRef.current = onRows;
```
Replace with:
```ts
  onRowsRef.current = onRows;
  const preloadedRef = useRef(preloadedChart);
  preloadedRef.current = preloadedChart;
```

Find:
```ts
        const doc = await fetchChart(chartId);
```
Replace with:
```ts
        const preloaded = preloadedRef.current;
        const doc = preloaded && preloaded.id === chartId ? preloaded : await fetchChart(chartId);
```

- [ ] **Step 4: Rewrite `ChartPage`**

Write `web/src/pages/ChartPage.tsx` (Write tool) with this full content:

```tsx
import { useEffect, useState } from 'react';
import { useParams } from 'react-router-dom';
import { fetchChart } from '../api/client';
import type { Chart } from '../api/types';
import { ChartTile, describeError } from '../components/ChartTile';
import { ErrorCard } from '../components/ErrorCard';
import { Markdown } from '../components/Markdown';
import type { Filter } from '../data/filters';

const NO_FILTERS: Filter[] = [];

export function ChartPage() {
  const id = useParams()['*'] ?? '';
  const [chart, setChart] = useState<Chart | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setChart(null);
    setError(null);
    fetchChart(id)
      .then((doc) => {
        if (!cancelled) setChart(doc);
      })
      .catch((err: unknown) => {
        if (!cancelled) setError(describeError(err));
      });
    return () => {
      cancelled = true;
    };
  }, [id]);

  if (error) return <ErrorCard id={id} reason={error} />;
  if (!chart) return <div className="muted">Loading…</div>;

  // No refresher runs in v1, so the page names the source and nothing more
  // (findings intent item 2). The tile footer says when the data is from.
  const sql = chart.source?.show_sql === true && typeof chart.source.sql === 'string' && chart.source.sql !== '' ? chart.source.sql : null;

  return (
    <div className="chart-page">
      <h2>
        {chart.title}
        {!chart.source && <span className="badge">static</span>}
      </h2>
      <ChartTile chartId={id} chart={chart} filters={NO_FILTERS} showTitle={false} />
      {chart.description && <Markdown text={chart.description} />}
      <table className="columns-table">
        <thead>
          <tr>
            <th>Column</th>
            <th>Type</th>
          </tr>
        </thead>
        <tbody>
          {chart.data.columns.map((c) => (
            <tr key={c.name}>
              <td>{c.name}</td>
              <td>{c.type}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {chart.source && <p className="muted">Source: Databricks SQL</p>}
      {sql && <pre className="sql">{sql}</pre>}
      <p className="muted">
        {chart.data.lane} lane, {chart.data.rows} rows, {chart.data.bytes} bytes, renderer {chart.renderer}
      </p>
    </div>
  );
}
```

- [ ] **Step 5: Run the tests to see them pass**

Run from `web/`: `npm test -- src/components/ChartTile src/pages/ChartPage`
Expected: all pass.

- [ ] **Step 6: Run the whole front-end suite and the typecheck**

Run from `web/`: `npm test` then `npm run typecheck`
Expected: both pass.

- [ ] **Step 7: Commit**

Run from the repo root:

```bash
git add web/src/components/ChartTile.tsx web/src/components/ChartTile.test.tsx web/src/pages/ChartPage.tsx web/src/pages/ChartPage.test.tsx
git -c user.name="tripp" -c user.email="dom4domg@gmail.com" commit -m "fix: chart page fetches once, names the source, no refresh promise (A12)" -m "Co-Authored-By: <model name from your harness> <noreply@anthropic.com>
Claude-Session: <session url from your harness>"
```

---

### Task 11: Immutable caching for `/assets` and gzip over 1 KB, never for `/api/data/`, `.wasm` or `/duckdb/` (A11)

**Files:**
- Create: `viz/server/compression.py`, `tests/server/test_compression.py`
- Modify: `viz/server/static.py`, `viz/server/app.py`

**Interfaces:**
- Consumes: `starlette.staticfiles.StaticFiles.file_response(self, full_path, stat_result, scope, status_code=200) -> Response` (Starlette 1.6); `starlette.middleware.gzip.GZipMiddleware(app, minimum_size=500, compresslevel=9, ...)`; `mount_spa(app, dist)` in `viz/server/static.py` (the SPA fallback serves any file under `web_dist`, for example `/duckdb/v1.4.3/wasm_eh/parquet.duckdb_extension.wasm`); `create_app(settings)` in `viz/server/app.py` after plan 5a (its middleware import line is `from .middleware import IdentityMiddleware, SecurityHeadersMiddleware, TrustedHostExceptHealth`, and `app.add_middleware(SecurityHeadersMiddleware)` is the last middleware added); the pytest fixture `settings` in `tests/server/conftest.py` (local storage over a copy of `sample-bucket/`, `allowed_hosts` includes `testserver` since plan 5a).
- Produces:
  - `viz.server.compression.IMMUTABLE = "public, max-age=31536000, immutable"`, `GZIP_MINIMUM_BYTES = 1024`, `UNCOMPRESSED_PREFIXES = ("/api/data/", "/duckdb/")`, `UNCOMPRESSED_SUFFIXES = (".wasm",)`, `is_never_compressed(path: str) -> bool`.
  - `ImmutableStaticFiles(StaticFiles)`: every response it serves carries `Cache-Control: public, max-age=31536000, immutable`. Vite names every file in `web/dist/assets` by content hash, so a changed file always has a new name. `index.html` and the `/duckdb/...` extension (served by the SPA fallback) are not affected.
  - `CompressionMiddleware(app)`: requests whose path starts with `/api/data/` or `/duckdb/`, or ends with `.wasm`, go straight to the app; everything else goes through `GZipMiddleware(app, minimum_size=1024, compresslevel=6)`. `/api/data/` is excluded because the client checks `Content-Length` against the lane caps, Range requests must keep working, and parquet is already compressed. `.wasm` files (the 34 MB DuckDB module in `/assets/`) and everything under `/duckdb/` (the self-hosted parquet extension) are served byte for byte, as the lead decided: DuckDB-WASM fetches them itself, and compressing 34 MB on every cold load costs server CPU; the immutable cache covers repeat loads.
  - `create_app` adds `CompressionMiddleware` as the outermost middleware.

- [ ] **Step 1: Write the failing tests**

Create `tests/server/test_compression.py`:

```python
"""Finding A11: hashed assets are cached for a year, responses over 1 KB are
gzipped; data files, .wasm files and everything under /duckdb/ never are."""
from fastapi.testclient import TestClient

from viz.server.app import create_app
from viz.server.compression import GZIP_MINIMUM_BYTES, IMMUTABLE, is_never_compressed

GZIP = {"Accept-Encoding": "gzip"}
BIG_JS = "console.log('viz');\n" * 200
WASM = b"\x00asm\x01\x00\x00\x00" + b"\x00" * 4096


def _dist(tmp_path):
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<!doctype html><title>viz</title>" + "<!-- pad -->" * 200, encoding="utf-8")
    (dist / "assets" / "app-3f2a1b.js").write_text(BIG_JS, encoding="utf-8")
    (dist / "assets" / "tiny-9c8d7e.js").write_text("1", encoding="utf-8")
    (dist / "assets" / "duckdb-eh-1a2b3c.wasm").write_bytes(WASM)
    extension = dist / "duckdb" / "v1.4.3" / "wasm_eh"
    extension.mkdir(parents=True)
    (extension / "parquet.duckdb_extension.wasm").write_bytes(WASM)
    (extension / "notes.txt").write_text("duckdb " * 400, encoding="utf-8")
    return dist


def _client(settings, tmp_path):
    settings.web_dist = _dist(tmp_path)
    return TestClient(create_app(settings))


def test_constants():
    assert IMMUTABLE == "public, max-age=31536000, immutable"
    assert GZIP_MINIMUM_BYTES == 1024


def test_hashed_assets_are_immutable(settings, tmp_path):
    client = _client(settings, tmp_path)
    for path in ("/assets/app-3f2a1b.js", "/assets/tiny-9c8d7e.js", "/assets/duckdb-eh-1a2b3c.wasm"):
        r = client.get(path)
        assert r.status_code == 200, path
        assert r.headers["cache-control"] == IMMUTABLE, path


def test_index_html_is_not_immutable(settings, tmp_path):
    client = _client(settings, tmp_path)
    for path in ("/", "/d/sales/overview"):
        r = client.get(path)
        assert r.status_code == 200, path
        assert "immutable" not in r.headers.get("cache-control", ""), path


def test_responses_over_one_kilobyte_are_gzipped(settings, tmp_path):
    client = _client(settings, tmp_path)
    r = client.get("/assets/app-3f2a1b.js", headers=GZIP)
    assert r.headers["content-encoding"] == "gzip"
    assert r.text == BIG_JS
    assert r.headers["cache-control"] == IMMUTABLE
    r = client.get("/api/tree", headers=GZIP)
    assert r.status_code == 200
    assert r.headers["content-encoding"] == "gzip"
    assert r.headers["content-security-policy"]


def test_never_compressed_paths():
    for path in ("/api/data/sales/x", "/duckdb/v1.4.3/wasm_eh/parquet.duckdb_extension.wasm",
                 "/duckdb/v1.4.3/wasm_eh/notes.txt", "/assets/duckdb-eh-1a2b3c.wasm"):
        assert is_never_compressed(path), path
    for path in ("/assets/app-3f2a1b.js", "/api/tree", "/", "/d/sales/overview", "/api/dataset"):
        assert not is_never_compressed(path), path


def test_wasm_and_duckdb_files_are_never_gzipped(settings, tmp_path):
    client = _client(settings, tmp_path)
    r = client.get("/assets/duckdb-eh-1a2b3c.wasm", headers=GZIP)
    assert r.status_code == 200
    assert "content-encoding" not in r.headers
    assert r.headers["content-type"] == "application/wasm"
    assert r.headers["cache-control"] == IMMUTABLE
    assert r.content == WASM
    for path in ("/duckdb/v1.4.3/wasm_eh/parquet.duckdb_extension.wasm", "/duckdb/v1.4.3/wasm_eh/notes.txt"):
        r = client.get(path, headers=GZIP)
        assert r.status_code == 200, path
        assert "content-encoding" not in r.headers, path
        assert int(r.headers["content-length"]) > GZIP_MINIMUM_BYTES, path
        assert int(r.headers["content-length"]) == len(r.content), path


def test_small_responses_are_not_gzipped(settings, tmp_path):
    client = _client(settings, tmp_path)
    r = client.get("/assets/tiny-9c8d7e.js", headers=GZIP)
    assert "content-encoding" not in r.headers
    r = client.get("/api/health", headers=GZIP)
    assert "content-encoding" not in r.headers


def test_data_files_are_never_gzipped(settings, tmp_path):
    client = _client(settings, tmp_path)
    for chart_id in ("bakeoff/vega-lite/time-series", "bakeoff/vega-lite/order-lines"):
        r = client.get(f"/api/data/{chart_id}", headers=GZIP)
        assert r.status_code == 200, chart_id
        assert "content-encoding" not in r.headers, chart_id
        assert int(r.headers["content-length"]) == len(r.content), chart_id
        assert int(r.headers["content-length"]) > GZIP_MINIMUM_BYTES, chart_id
```

- [ ] **Step 2: Run the tests to see them fail**

Run: `.venv/Scripts/python -m pytest tests/server/test_compression.py -v`
Expected: collection ERROR, `ModuleNotFoundError: No module named 'viz.server.compression'`.

- [ ] **Step 3: Write `viz/server/compression.py`**

Create `viz/server/compression.py`:

```python
"""Response compression and long-lived caching for hashed front-end assets (finding A11)."""
import os

from starlette.middleware.gzip import GZipMiddleware
from starlette.responses import Response
from starlette.staticfiles import StaticFiles
from starlette.types import ASGIApp, Receive, Scope, Send

IMMUTABLE = "public, max-age=31536000, immutable"
GZIP_MINIMUM_BYTES = 1024
GZIP_LEVEL = 6
# Served byte for byte, never gzipped (decided by the lead, plan 5c):
# /api/data/: the client checks Content-Length against the lane caps, Range
#   requests must keep working, and parquet is already compressed;
# /duckdb/ and *.wasm: the DuckDB module and its self-hosted extension, which
#   DuckDB-WASM fetches itself; compressing 34 MB per cold load costs CPU.
UNCOMPRESSED_PREFIXES = ("/api/data/", "/duckdb/")
UNCOMPRESSED_SUFFIXES = (".wasm",)


def is_never_compressed(path: str) -> bool:
    """True for paths whose responses are always sent uncompressed."""
    return path.startswith(UNCOMPRESSED_PREFIXES) or path.endswith(UNCOMPRESSED_SUFFIXES)


class ImmutableStaticFiles(StaticFiles):
    """StaticFiles for Vite's /assets. Vite names every file there by content
    hash, so a file with a given name never changes and may be cached for a year."""

    def file_response(
        self,
        full_path: str | os.PathLike[str],
        stat_result: os.stat_result,
        scope: Scope,
        status_code: int = 200,
    ) -> Response:
        response = super().file_response(full_path, stat_result, scope, status_code)
        response.headers["Cache-Control"] = IMMUTABLE
        return response


class CompressionMiddleware:
    """Gzip responses over 1 KB, except the paths is_never_compressed() names:
    data files under /api/data/, everything under /duckdb/, and any .wasm file."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app
        self.gzip = GZipMiddleware(app, minimum_size=GZIP_MINIMUM_BYTES, compresslevel=GZIP_LEVEL)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http" and is_never_compressed(scope.get("path", "")):
            await self.app(scope, receive, send)
            return
        await self.gzip(scope, receive, send)
```

- [ ] **Step 4: Use `ImmutableStaticFiles` for `/assets`**

Edit `viz/server/static.py`.

Find:
```python
from starlette.staticfiles import StaticFiles
```
Replace with:
```python

from .compression import ImmutableStaticFiles
```

Find:
```python
        app.mount("/assets", StaticFiles(directory=assets), name="assets")
```
Replace with:
```python
        app.mount("/assets", ImmutableStaticFiles(directory=assets), name="assets")
```

- [ ] **Step 5: Add the middleware in `viz/server/app.py`**

Edit `viz/server/app.py`.

Find (the line as plan 5a left it):
```python
from .middleware import IdentityMiddleware, SecurityHeadersMiddleware, TrustedHostExceptHealth
```
Replace with:
```python
from .compression import CompressionMiddleware
from .middleware import IdentityMiddleware, SecurityHeadersMiddleware, TrustedHostExceptHealth
```

Find:
```python
    app.add_middleware(SecurityHeadersMiddleware)
```
Replace with:
```python
    app.add_middleware(SecurityHeadersMiddleware)
    # Outermost: compresses whatever leaves the app, headers included, except
    # /api/data/, /duckdb/ and .wasm (finding A11). Added last so it runs first.
    app.add_middleware(CompressionMiddleware)
```

(After plan 5a, `app.add_middleware(SecurityHeadersMiddleware)` is still the last `add_middleware` line, so `CompressionMiddleware` becomes the last one added.)

- [ ] **Step 6: Run the tests to see them pass**

Run: `.venv/Scripts/python -m pytest tests/server -v`
Expected: all pass, including the existing `test_static.py` and `test_data_route.py` cases.

- [ ] **Step 7: Run the whole Python suite and the front-end checks**

Run: `.venv/Scripts/python -m pytest`
Then run from `web/`: `npm test` then `npm run typecheck`
Expected: all pass.

- [ ] **Step 8: Commit**

Run from the repo root:

```bash
git add viz/server/compression.py viz/server/static.py viz/server/app.py tests/server/test_compression.py
git -c user.name="tripp" -c user.email="dom4domg@gmail.com" commit -m "feat: immutable cache for hashed assets and gzip over 1 KB except data files (A11)" -m "Co-Authored-By: <model name from your harness> <noreply@anthropic.com>
Claude-Session: <session url from your harness>"
```

---

### Task 12: End-to-end checks, production build and the Playwright suite

**Files:**
- Modify: `web/e2e/smoke.spec.ts`

**Interfaces:**
- Consumes: `npm run build` (`vite build`, writes `web/dist`), `npm run e2e` (`playwright test`; its global setup rebuilds, then starts `<repo>/.venv/Scripts/viz-server.exe` on 127.0.0.1:8000 against `sample-bucket/`). The sample dashboard `/d/bakeoff/vega-lite` has controls Period (`month`), Days (`day`, date-range) and Region (`region`, multi-select) and four chart tiles, one of them large-lane (`bakeoff/vega-lite/order-lines`).
- Produces: two new Playwright tests that prove, in Chromium against the built bundle: a deep-linked Region survives an edit to Days; every chart tile has a "Download data" link to `/api/data/<id>`; the large-lane mount carries `role="img"` with a non-empty `aria-label`; a "Data as of" line is visible; `/assets/*.js` answers with the immutable `Cache-Control`. The existing tests prove the large lane still loads parquet after the A4 lockdown.

- [ ] **Step 1: Add the end-to-end tests**

Edit `web/e2e/smoke.spec.ts`.

Find:
```ts
test('a missing dashboard shows one error card and the header still renders', async ({ page }) => {
```
Replace with:
```ts
test('a deep-linked region survives another control change, and tiles carry download links and freshness', async ({ page }) => {
  const log = watch(page);
  await page.goto('/d/bakeoff/vega-lite?region=EMEA');
  await expect(page.locator('[data-tile][data-state="ready"]')).toHaveCount(4, { timeout: 90_000 });
  await expect(page.locator('.error-card')).toHaveCount(0);
  await expect(page.getByLabel('Region', { exact: true })).toHaveValues(['EMEA']);

  await page.getByLabel('Days from').fill('2025-01-01');
  await expect(page).toHaveURL(/days=2025-01-01/);
  await expect(page).toHaveURL(/region=EMEA/);
  await expect(page.locator('[data-tile][data-state="ready"]')).toHaveCount(4, { timeout: 60_000 });

  const links = page.getByRole('link', { name: 'Download data' });
  await expect(links).toHaveCount(4);
  await expect(page.locator('[data-tile="bakeoff/vega-lite/order-lines"] a.tile-download')).toHaveAttribute('href', '/api/data/bakeoff/vega-lite/order-lines');
  await expect(page.locator('[data-tile="bakeoff/vega-lite/order-lines"] .tile-mount')).toHaveAttribute('role', 'img');
  await expect(page.locator('[data-tile="bakeoff/vega-lite/order-lines"] .tile-mount')).toHaveAttribute('aria-label', /.+/);
  await expect(page.getByText(/^Data as of \d{4}-\d{2}-\d{2} \d{2}:\d{2} UTC$/).first()).toBeVisible();

  expect(log.foreign, 'every request stays on the site origin').toEqual([]);
  expect(log.failed, 'no request failed').toEqual([]);
  expect(log.consoleErrors, 'no console errors').toEqual([]);
});

test('hashed assets are cached for a year', async ({ request }) => {
  const html = await (await request.get('/')).text();
  const match = /\/assets\/[^"']+\.js/.exec(html);
  expect(match, 'index.html references a hashed script').not.toBeNull();
  const res = await request.get(match![0]);
  expect(res.status()).toBe(200);
  expect(res.headers()['cache-control']).toBe('public, max-age=31536000, immutable');
});

test('a missing dashboard shows one error card and the header still renders', async ({ page }) => {
```

- [ ] **Step 2: Typecheck**

Run from `web/`: `npm run typecheck`
Expected: pass.

- [ ] **Step 3: Build the production bundle**

Run from `web/`: `npm run build`
Expected: the build finishes and writes `web/dist` with no errors.

- [ ] **Step 4: Run the Playwright suite**

If Chromium for Playwright is not installed yet, run from `web/`: `npx playwright install chromium` first.
Run from `web/`: `npm run e2e`
Expected: every test passes, including `the single chart page renders a large-lane chart` and the bake-off test (the large-lane tile reaching `data-state="ready"` proves DuckDB still reads the registered parquet after the A4 lockdown in a real browser). If the large-lane tile shows `query failed: ... Permission Error`, stop and report the full message: the lockdown and the registered file name disagree.

- [ ] **Step 5: Run every suite once more**

Run from `web/`: `npm test`
Run from the repo root: `.venv/Scripts/python -m pytest`
Expected: both pass.

- [ ] **Step 6: Commit**

Run from the repo root:

```bash
git add web/e2e/smoke.spec.ts
git -c user.name="tripp" -c user.email="dom4domg@gmail.com" commit -m "test: e2e covers deep-linked selects, download links, freshness and asset caching" -m "Co-Authored-By: <model name from your harness> <noreply@anthropic.com>
Claude-Session: <session url from your harness>"
```

- [ ] **Step 7: Verify the commit message layout**

Run: `git log -1 --format=%B`
Expected: the subject on line 1, an empty line 2, and the `Co-Authored-By` and `Claude-Session` trailers as the last two non-empty lines, adjacent.

---

### Task 13: Design spec 12.3 records the new viewer rules

**Files:**
- Modify: `docs/superpowers/specs/2026-09-22-viz-site-design.md` (section 12.3 only), `tests/test_spec_text.py`

**Interfaces:**
- Consumes: plan 5a's `tests/test_spec_text.py` (helpers `_text()` and `_section(heading)`) and plan 5a's rewrite of the 12.3 sanitizer bullet (edit (r) of 5a Task 11); the rules built in Tasks 1 to 4 of this plan.
- Produces: spec 12.3 states: `data` only at the top level; `sequence`, `graticule`, `sphere` rejected; `bind.element` rejected; text-only tooltips; DuckDB `allowed_directories=['/viz-data/']` plus `enable_external_access=false` before the lock. Plan 5d does not edit 12.3.

- [ ] **Step 1: Write the failing test**

Append to the end of `tests/test_spec_text.py`:

```python


def test_spec_records_the_viewer_rules_of_plan_5c():
    front_end = " ".join(_section("### 12.3 Front end").split())
    for phrase in (
        "`data` is allowed only at the top level",
        "`sequence`, `graticule` and `sphere` are rejected at any depth",
        "`params[].bind.element`",
        "Tooltips are text only",
        "`allowed_directories=['/viz-data/']` and `enable_external_access=false`",
    ):
        assert phrase in front_end, phrase
    assert "disable the HTTP and S3 filesystems" not in front_end
```

- [ ] **Step 2: Run it to see it fail**

Run: `.venv/Scripts/python -m pytest tests/test_spec_text.py -v`
Expected: `test_spec_records_the_viewer_rules_of_plan_5c` FAILS on the first phrase; the other tests pass.

- [ ] **Step 3: Replace the sanitizer bullet in section 12.3**

Edit `docs/superpowers/specs/2026-09-22-viz-site-design.md`.

Find (the text plan 5a wrote):
```
- Renderer adapters sanitize specs before mounting, and the same rules are
  encoded in `chart.schema.json` so the CLI rejects them at publish time.
  Vega-Lite won the bake-off; Plotly and ECharts are removed. Vega-Lite: null
  loader, `actions: false`, canvas renderer, `vega-interpreter` (no
  `unsafe-eval`), reject `url`, `values`, `href`, `usermeta`, `datasets` and
  image marks at any depth. The schema's forbidden-key list is exactly the
  browser sanitizer's list plus `__proto__`, `constructor` and `prototype`;
  a test keeps the two in step.
```
Replace with:
```
- Renderer adapters sanitize specs before mounting, and the CLI enforces the
  same rules (`chart.schema.json` plus `viz/schemas.py`) so it rejects them
  at publish time. Vega-Lite won the bake-off; Plotly and ECharts are
  removed. Vega-Lite: null loader, `actions: false`, canvas renderer,
  `vega-interpreter` (no `unsafe-eval`), reject `url`, `values`, `href`,
  `usermeta`, `datasets` and image marks at any depth. The schema's
  forbidden-key list is exactly the browser sanitizer's list plus
  `__proto__`, `constructor` and `prototype`; a test keeps the two in step.
- Vega-Lite data: `data` is allowed only at the top level and must be exactly
  `{"name": "data"}`; a `data` key anywhere below it (in a layer, a concat or
  a lookup) is rejected, even the named dataset. The row generators
  `sequence`, `graticule` and `sphere` are rejected at any depth, because
  they make rows out of nothing and can freeze the tab. `params[].bind.element`
  (any `bind` object with an `element` key) is rejected at any depth, so a
  spec cannot place an input widget elsewhere on the page. The browser
  sanitizer and `viz/schemas.py` share these rules and their messages; they
  are separate checks, not entries in the forbidden-key list.
- Tooltips are text only. The adapter passes its own tooltip handler to
  vega-embed, so vega-tooltip's HTML handler is never used. The handler sets
  only `textContent`, drops an `image` key, and caps the text at 2,000
  characters.
```

- [ ] **Step 4: Replace the start of the DuckDB bullet in section 12.3**

Find:
```
- DuckDB-WASM: at connection init set `autoinstall_known_extensions=false`,
  `autoload_known_extensions=false`, `memory_limit='512MB'`, disable the HTTP
  and S3 filesystems, then `lock_configuration=true`. The `aggregate` must be
```
Replace with:
```
- DuckDB-WASM: at connection init set `autoinstall_known_extensions=false`,
  `autoload_known_extensions=false`, `memory_limit='512MB'`,
  `allowed_directories=['/viz-data/']` and `enable_external_access=false`,
  then `lock_configuration=true`. Every chart's data file is registered under
  `/viz-data/`, the only path DuckDB may read; any other file, URL or
  filesystem (HTTP and S3 included) is refused, and the lock stops a query
  from turning access back on. The `aggregate` must be
```

- [ ] **Step 5: Run the tests to see them pass**

Run: `.venv/Scripts/python -m pytest tests/test_spec_text.py -v`
Expected: all pass.

- [ ] **Step 6: Run the whole Python suite, then commit**

Run: `.venv/Scripts/python -m pytest`
Expected: all pass, 0 failed.

```bash
git add docs/superpowers/specs/2026-09-22-viz-site-design.md tests/test_spec_text.py
git -c user.name="tripp" -c user.email="dom4domg@gmail.com" commit -m "docs: spec 12.3 records nested-data, generator, bind.element, tooltip and DuckDB lockdown rules" -m "Co-Authored-By: <model name from your harness> <noreply@anthropic.com>
Claude-Session: <session url from your harness>"
```

Check with `git log -1 --format=%B`: subject on line 1, empty line 2, the two trailers as the last two lines, adjacent.

---

## Interfaces for later plans (5d)

- `viz.server.compression.CompressionMiddleware` is the outermost middleware; `/api/data/`, `/duckdb/` and `*.wasm` are never gzipped, so the docker smoke's wasm check sees the raw bytes (`00 61 73 6d`) and `application/wasm`.
- `/assets/*` responses carry `Cache-Control: public, max-age=31536000, immutable`; `index.html` does not.
- Design spec: plan 5c edited section 12.3 only. Sections 12.5 and 12.2 are as plan 5a left them.
- No Helm, AWS, CI, `README.md` or `docs/work-setup.md` file is changed by this plan.
