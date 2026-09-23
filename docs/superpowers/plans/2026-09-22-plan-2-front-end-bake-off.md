# Plan 2: Front End and Bake-off Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A Vite + React + TypeScript front end in `web/` that renders the sample bucket through three sanitized renderer adapters (Vega-Lite, Plotly, ECharts) plus a stat tile, with dashboard controls held in the URL, a lazily loaded DuckDB-WASM large lane, bake-off sample charts and dashboards for each renderer, one Playwright smoke test, and a scorecard the user fills in to pick the winning renderer.

**Architecture:** The front end is a static bundle served by the existing FastAPI server (`viz/server/static.py` mounts `web/dist/assets` and falls back to `index.html`). It talks only to `/api/*` on the same origin. Every chart spec from the bucket is treated as hostile: a pure `sanitize()` per renderer rewrites or rejects it before an adapter mounts it, and the adapters are configured so nothing in a spec can load a URL, run code, or inject HTML. Small-lane data is fetched as JSON rows and filtered in TypeScript. Large-lane data is a parquet file loaded into an in-browser DuckDB whose configuration is locked before any chart's `aggregate` runs; control values reach DuckDB only as prepared-statement parameters and Arrow temp tables. Dashboard control state lives in the URL query string so a filtered view is a shareable link.

**Tech Stack:** Node 24, npm, Vite 7, React 19, TypeScript 5.9, react-router-dom 7, vitest 3 + jsdom + @testing-library/react, Playwright 1.63 (chromium), vega 6 / vega-lite 6 / vega-embed 7 / vega-interpreter 2, plotly.js-dist-min 3, echarts 6, @duckdb/duckdb-wasm 1.32 + apache-arrow 17, react-markdown 10 + remark-gfm 4, d3-format 3. Python side: pyarrow (dev extra) for the parquet sample.

**Spec:** `docs/superpowers/specs/2026-09-22-viz-site-design.md` sections 4.2, 4.3, 5.2, 8 (front-end bullet), 12.3, and the bake-off sample requirement in 5.2. Security rationale: `docs/superpowers/specs/2026-09-22-security-review.md`. The server contract this plan consumes is Plan 1: `docs/superpowers/plans/2026-09-22-plan-1-contract-storage-server.md`.

## Global Constraints

- Everything is bundled by Vite and served from the site. Nothing loads from a CDN at runtime. No `<script src>` to another origin, no `import()` of a URL, no `registerFileURL` in DuckDB.
- Content Security Policy sent by the server on every response, verbatim: `default-src 'self'; script-src 'self' 'wasm-unsafe-eval'; worker-src 'self' blob:; connect-src 'self'; img-src 'self' data: blob:; style-src 'self' 'unsafe-inline'; object-src 'none'; base-uri 'self'; form-action 'self'; frame-ancestors 'none'`. There is no `'unsafe-eval'`, so Vega must run with `ast: true` and the `vega-interpreter` expression interpreter, and no renderer may turn a string into a function.
- Renderer adapter interface, exact: `interface Adapter { mount(el: HTMLElement, spec: unknown, rows: Row[], columns: Column[]): Promise<void>; update(rows: Row[]): Promise<void>; destroy(): void }` with `type Row = Record<string, unknown>` and `type Column = { name: string; type: 'string' | 'number' | 'integer' | 'boolean' | 'date' | 'timestamp' }`.
- Every renderer has a pure `sanitize(spec: unknown): unknown` in its own file that throws `SanitizeError` on rejection and never touches the DOM. Sanitizers accept plain objects and arrays only.
- `dangerouslySetInnerHTML` appears nowhere under `web/src` except `web/src/components/Markdown.tsx`, and it does not appear there either (react-markdown does not need it). A test greps for it.
- Small lane: JSON rows, at most `20971520` bytes; the client refuses larger bodies. Large lane: parquet, at most `209715200` bytes. Large-lane results are capped at `50000` rows by wrapping the aggregate as `SELECT * FROM (<aggregate>) LIMIT 50000`.
- DuckDB-WASM connection init runs, in this order: `SET autoinstall_known_extensions=false`, `SET autoload_known_extensions=false`, `SET memory_limit='512MB'`, `SET lock_configuration=true`. The parquet extension is statically linked into duckdb-wasm, so no extension is ever fetched. HTTP and S3 access from the worker is prevented by the CSP (`connect-src 'self'`, which the worker inherits from the response that served it) and by never registering URLs; the only file DuckDB ever sees is a buffer registered from `/api/data/<id>`, which is materialized into a table and then dropped.
- Control values are never interpolated into SQL. Ranges are prepared-statement parameters; select values go in as Arrow temp tables. Column identifiers are double-quoted and must appear in the chart's declared columns, whose names match `^[A-Za-z_][A-Za-z0-9_]*$`.
- `select` controls cap at `500` options and fall back to a text filter above that.
- Id pattern, verbatim from the spec: `^[a-z0-9]+(-[a-z0-9]+)*(/[a-z0-9]+(-[a-z0-9]+)*)*$`.
- Sample bucket content is synthetic: `author` is always `sample@example.com`, any `source.warehouse_id` is `sample`. The generator is deterministic (`random.Random(20260922)`).
- Plotly specs use the column-binding convention from `viz/schemas.py`: `{ "traces": [...], "layout": {...} }`, where each of `x, y, z, text, hovertext, labels, values, customdata` on a trace is `{ "column": "<name>" }`. This plan adds one optional trace key, `split: "<column>"`, that the adapter expands into one trace per distinct value. ECharts series get the same optional `split` key, expanded into one series per distinct value backed by a `filter` dataset transform. Vega-Lite needs no convention; it uses `color`/`detail` encodings.
- Node.js 24 is installed at `C:\Program Files\nodejs`. New Git Bash shells need `export PATH="/c/Program Files/nodejs:$PATH"`; PowerShell needs `$env:PATH = "C:\Program Files\nodejs;" + $env:PATH`. All `npm` commands run from `web/`. All Python commands use the venv interpreter `.venv/Scripts/python` (Linux/macOS: `.venv/bin/python`) from the repo root.
- Every commit message follows the "Commit messages" section of `CLAUDE.md`: subject, blank line, then two contiguous trailer lines (`Co-Authored-By` naming the model that made the commit as its harness states it, and `Claude-Session` with the session URL its harness states). Use the two `-m` recipe from `CLAUDE.md`.
- Before every commit: `npm test` in `web/` must pass, `npm run typecheck` in `web/` must pass, and when a Python file changed, `.venv/Scripts/python -m pytest` from the repo root must pass.
- Commit `web/package-lock.json`. Never commit `web/node_modules` or `web/dist` (both are already in `.gitignore`).

## How to execute a task (read this whether you are a large or a small model)

1. Read `CLAUDE.md` at the repo root first. It has the commands, the commit
   trailers, and the environment gotchas (a guard hook blocks backticks in
   shell commands: write files with the Write tool, not heredocs).
2. Work only on the task you were given. Do not start the next one.
3. Do the steps in order. Each step is one action. Do not skip the "run the
   test and see it fail" step; it proves the test is real.
4. Copy the code from the step exactly. If the code in a step does not work as
   written, fix the smallest thing that makes it work, and say what you
   changed and why in your report. Do not redesign.
5. If a command fails and you cannot fix it within the task's scope, stop and
   report the full error output. Do not work around it by weakening a test.
6. Before committing, run the checks listed in Global Constraints. They must pass.
7. Report back with: the commit hash, the test summary lines, and any deviation
   from the plan. Nothing else is needed.

---

## File structure

| Path | Responsibility |
|---|---|
| `web/package.json`, `web/package-lock.json` | Dependencies and scripts (`dev`, `build`, `test`, `typecheck`, `e2e`) |
| `web/vite.config.ts` | Vite build (manual chunks per renderer), dev proxy, vitest config |
| `web/tsconfig.json` | TypeScript strict config |
| `web/index.html` | Entry page |
| `web/src/main.tsx` | Mounts `<App/>` inside `BrowserRouter` |
| `web/src/App.tsx` | Header nav and routes |
| `web/src/styles.css` | The only stylesheet |
| `web/src/vite-env.d.ts` | Vite client types (`?url` imports) |
| `web/src/types/plotly.d.ts` | Module declaration for `plotly.js-dist-min` |
| `web/src/api/types.ts` | TypeScript shapes for chart, dashboard, tree |
| `web/src/api/client.ts` | `fetchTree`, `fetchDashboard`, `fetchChart`, `fetchRows`, `dataUrl`, `ApiError`, `DataTooLarge` |
| `web/src/components/Markdown.tsx` | The one Markdown component, URL policy included |
| `web/src/data/filters.ts` | `FilterValue`, `Filter`, `applyFilters`, `selectOptions`, `resolveLast`, `defaultFilterValue` |
| `web/src/state/urlState.ts` | `encodeFilters`, `decodeFilters` |
| `web/src/renderers/common.ts` | `SanitizeError`, `assertPlain`, `deepClone`, `walk`, `FORBIDDEN_KEYS` |
| `web/src/components/StatTile.tsx` | Stat renderer (React component) plus `parseStatSpec`, `aggregate`, `formatValue` |
| `web/src/renderers/vegaLiteSanitize.ts`, `vegaLite.ts` | Vega-Lite rules and adapter |
| `web/src/renderers/echartsSanitize.ts`, `echarts.ts` | ECharts rules and adapter |
| `web/src/renderers/plotlyBind.ts`, `plotlySanitize.ts`, `plotly.ts` | Plotly column binding, rules and adapter |
| `web/src/renderers/index.ts` | `getAdapter(renderer)`, `sanitizeSpec(renderer, spec)` |
| `web/src/components/ErrorCard.tsx` | Tile-level error card |
| `web/src/components/ChartTile.tsx` | Loads a chart, its data, sanitizes, mounts, updates, isolates failures |
| `web/src/pages/TreePage.tsx` | Dashboards tree (`/`) and charts library (`/charts`) |
| `web/src/pages/DashboardPage.tsx`, `web/src/components/ControlBar.tsx` | Dashboard page with controls and the 12-column grid |
| `web/src/pages/ChartPage.tsx` | Single chart page |
| `web/src/data/duckdb.ts` | DuckDB-WASM lazy runtime, locked config, parquet load, safe filtered query |
| `web/src/test/setup.ts`, `web/src/test/noInnerHtml.test.ts` | Test setup and the `dangerouslySetInnerHTML` guard |
| `web/e2e/smoke.spec.ts`, `web/playwright.config.ts` | Playwright smoke test |
| `web/scripts/chunk-sizes.mjs`, `web/scripts/spec-lines.mjs` | Bake-off measurements |
| `sample-bucket/generate.py` | Extended with bake-off charts, parquet, and three dashboards |
| `tests/test_sample_bucket.py`, `tests/server/test_static.py` | Python tests touched by this plan |
| `docs/superpowers/specs/2026-09-22-bake-off-scorecard.md` | The scorecard the user fills in |

---

### Task 1: Web scaffold, test runner, production build, wasm content type

**Files:**
- Create: `web/package.json`, `web/tsconfig.json`, `web/vite.config.ts`, `web/index.html`, `web/src/main.tsx`, `web/src/App.tsx`, `web/src/App.test.tsx`, `web/src/styles.css`, `web/src/vite-env.d.ts`, `web/src/test/setup.ts`
- Modify: `tests/server/test_static.py` (append one test), possibly `viz/server/static.py`

**Interfaces:**
- Produces: `npm run dev` (Vite on 5173 proxying `/api` to 127.0.0.1:8000), `npm run build` (writes `web/dist`), `npm test` (vitest, jsdom), `npm run typecheck`, `npm run e2e` (Playwright, used from Task 16). Manual chunk names `renderer-vega`, `renderer-plotly`, `renderer-echarts`, `duckdb` that Task 17 measures. The server serves `/assets/*.wasm` as `application/wasm`.

- [ ] **Step 1: Write the Python test for the wasm content type**

Append to `tests/server/test_static.py`:

```python


def test_wasm_asset_has_wasm_content_type(settings, tmp_path):
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<html></html>", encoding="utf-8")
    (dist / "assets" / "duckdb-eh.wasm").write_bytes(b"\x00asm\x01\x00\x00\x00")
    settings.web_dist = dist
    client = TestClient(create_app(settings))
    r = client.get("/assets/duckdb-eh.wasm")
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/wasm"
```

- [ ] **Step 2: Run it**

Run from the repo root: `.venv/Scripts/python -m pytest tests/server/test_static.py -v`

Expected: either PASS (Python's `mimetypes` already knows `.wasm`) or FAIL with a content type such as `application/octet-stream`. If it FAILS, add these two lines to `viz/server/static.py` directly under the existing imports, then re-run until PASS:

```python
import mimetypes

mimetypes.add_type("application/wasm", ".wasm")
```

- [ ] **Step 3: Create the web package files**

`web/package.json`:

```json
{
  "name": "viz-site-web",
  "private": true,
  "version": "0.1.0",
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "vite build",
    "typecheck": "tsc --noEmit -p tsconfig.json",
    "test": "vitest run",
    "e2e": "playwright test"
  },
  "dependencies": {
    "@duckdb/duckdb-wasm": "1.32.0",
    "apache-arrow": "^17.0.0",
    "d3-format": "^3.1.0",
    "echarts": "^6.1.0",
    "plotly.js-dist-min": "^3.7.0",
    "react": "^19.3.0",
    "react-dom": "^19.3.0",
    "react-markdown": "^10.1.0",
    "react-router-dom": "^7.18.0",
    "remark-gfm": "^4.0.1",
    "vega": "^6.4.0",
    "vega-embed": "^7.2.0",
    "vega-interpreter": "^2.3.0",
    "vega-lite": "^6.4.0"
  },
  "devDependencies": {
    "@playwright/test": "^1.63.0",
    "@testing-library/jest-dom": "^6.10.0",
    "@testing-library/react": "^16.3.0",
    "@types/d3-format": "^3.0.4",
    "@types/node": "^22.0.0",
    "@types/react": "^19.3.0",
    "@types/react-dom": "^19.3.0",
    "@vitejs/plugin-react": "^5.2.0",
    "jsdom": "^27.4.0",
    "typescript": "~5.9.0",
    "vite": "^7.3.0",
    "vitest": "^3.2.0"
  }
}
```

These versions were checked against the npm registry on 2026-09-22 (latest per major: react 19.3.0, react-router-dom 7.18.4, vega 6.4.0, vega-lite 6.4.3, vega-embed 7.2.0, vega-interpreter 2.3.2, plotly.js-dist-min 3.7.0, echarts 6.1.0, @duckdb/duckdb-wasm 1.32.0 stable with an `apache-arrow ^17` dependency, react-markdown 10.1.0, remark-gfm 4.0.1, d3-format 3.1.2, vite 7.3.6, @vitejs/plugin-react 5.2.0, vitest 3.2.7, jsdom 27.4.0, @testing-library/react 16.3.3, @testing-library/jest-dom 6.10.0, @playwright/test 1.63.0, typescript 5.9.3). Newer majors exist for vite, vitest, plotly, jsdom and typescript; they are deliberately not used.

`web/tsconfig.json`:

```json
{
  "compilerOptions": {
    "target": "ES2022",
    "lib": ["ES2022", "DOM", "DOM.Iterable"],
    "module": "ESNext",
    "moduleResolution": "bundler",
    "jsx": "react-jsx",
    "strict": true,
    "noUnusedLocals": true,
    "noUnusedParameters": true,
    "noFallthroughCasesInSwitch": true,
    "noEmit": true,
    "skipLibCheck": true,
    "esModuleInterop": true,
    "resolveJsonModule": true,
    "isolatedModules": true,
    "types": ["vite/client", "node"]
  },
  "include": ["src", "e2e", "scripts", "vite.config.ts", "playwright.config.ts"]
}
```

`web/vite.config.ts`:

```ts
import { defineConfig } from 'vitest/config';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: { '/api': 'http://127.0.0.1:8000' },
  },
  build: {
    assetsInlineLimit: 0,
    chunkSizeWarningLimit: 6000,
    rollupOptions: {
      output: {
        manualChunks: {
          'renderer-vega': ['vega', 'vega-lite', 'vega-embed', 'vega-interpreter'],
          'renderer-plotly': ['plotly.js-dist-min'],
          'renderer-echarts': ['echarts'],
          duckdb: ['@duckdb/duckdb-wasm', 'apache-arrow'],
        },
      },
    },
  },
  test: {
    environment: 'jsdom',
    setupFiles: ['src/test/setup.ts'],
    exclude: ['e2e/**', 'node_modules/**', 'dist/**'],
    css: false,
  },
});
```

`web/index.html`:

```html
<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>viz-site</title>
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/main.tsx"></script>
  </body>
</html>
```

`web/src/main.tsx`:

```tsx
import React from 'react';
import ReactDOM from 'react-dom/client';
import { BrowserRouter } from 'react-router-dom';
import App from './App';
import './styles.css';

ReactDOM.createRoot(document.getElementById('root') as HTMLElement).render(
  <React.StrictMode>
    <BrowserRouter>
      <App />
    </BrowserRouter>
  </React.StrictMode>,
);
```

`web/src/App.tsx` (a placeholder body; Task 11 replaces it with the router):

```tsx
export default function App() {
  return (
    <div className="app">
      <header className="app-header">
        <h1>viz-site</h1>
      </header>
    </div>
  );
}
```

`web/src/styles.css`:

```css
:root {
  --bg: #ffffff;
  --fg: #1c1c1c;
  --muted: #666666;
  --border: #dddddd;
  --error-bg: #fff3f3;
  --error-border: #d33;
  --accent: #2b5fd9;
  font-family: system-ui, -apple-system, "Segoe UI", Roboto, sans-serif;
  color: var(--fg);
  background: var(--bg);
}

* { box-sizing: border-box; }
body { margin: 0; }
a { color: var(--accent); }

.app-header { display: flex; align-items: baseline; gap: 24px; padding: 12px 20px; border-bottom: 1px solid var(--border); }
.app-header h1 { font-size: 18px; margin: 0; }
.app-header nav a { margin-right: 16px; }
.app-main { padding: 20px; }

.tree ul { list-style: none; padding-left: 18px; margin: 4px 0; }
.tree .folder-title { font-weight: 600; margin-top: 8px; }
.tree .item-error { color: var(--error-border); }
.muted { color: var(--muted); }

.control-bar { display: flex; flex-wrap: wrap; gap: 16px; align-items: flex-end; padding: 12px 0 20px; }
.control { display: flex; flex-direction: column; gap: 4px; font-size: 13px; }
.control .range { display: flex; gap: 6px; align-items: center; }

.grid { display: grid; grid-template-columns: repeat(12, minmax(0, 1fr)); grid-auto-rows: 120px; gap: 12px; }
.tile { border: 1px solid var(--border); border-radius: 6px; padding: 10px; min-width: 0; overflow: hidden; display: flex; flex-direction: column; }
.tile-title { font-size: 14px; font-weight: 600; margin: 0 0 6px; }
.tile-body { flex: 1; min-height: 0; position: relative; }
.tile-mount { position: absolute; inset: 0; }
.tile-markdown { overflow: auto; }

.error-card { background: var(--error-bg); border: 1px solid var(--error-border); border-radius: 6px; padding: 10px; font-size: 13px; overflow: auto; }
.error-card .error-id { font-family: ui-monospace, Menlo, Consolas, monospace; font-size: 12px; }

.stat { display: flex; flex-direction: column; justify-content: center; height: 100%; }
.stat-value { font-size: 36px; font-weight: 700; }
.stat-compare { font-size: 13px; color: var(--muted); }

.chart-page .tile { height: 480px; }
.badge { display: inline-block; font-size: 11px; padding: 2px 6px; border: 1px solid var(--border); border-radius: 10px; color: var(--muted); margin-left: 8px; }
.columns-table { border-collapse: collapse; font-size: 13px; }
.columns-table td, .columns-table th { border: 1px solid var(--border); padding: 4px 8px; text-align: left; }
pre.sql { background: #f6f6f6; padding: 10px; overflow: auto; font-size: 12px; }
```

`web/src/vite-env.d.ts`:

```ts
/// <reference types="vite/client" />
```

`web/src/test/setup.ts`:

```ts
import '@testing-library/jest-dom/vitest';
```

- [ ] **Step 4: Write the first failing front-end test**

`web/src/App.test.tsx`:

```tsx
import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import App from './App';

describe('App', () => {
  it('renders the site name', () => {
    render(<App />);
    expect(screen.getByRole('heading', { name: 'viz-site' })).toBeInTheDocument();
  });
});
```

- [ ] **Step 5: Install and run the test**

Run from `web/`: `npm install` then `npm test`

Expected: `npm install` completes (it may print peer warnings; errors are not acceptable). `npm test` prints `1 passed`.

If `npm install` fails on a version that does not resolve, report the exact package and error; do not change majors.

- [ ] **Step 6: Typecheck and build**

Run from `web/`: `npm run typecheck` then `npm run build`

Expected: typecheck prints nothing (exit 0). Build writes `web/dist/index.html` and `web/dist/assets/index-<hash>.js`. The renderer chunks do not exist yet because nothing imports the libraries; that is expected.

- [ ] **Step 7: Prove the server serves the build**

Run from the repo root in the background: `VIZ_WEB_DIST=web/dist .venv/Scripts/viz-server`
Then: `curl -s http://127.0.0.1:8000/ | head -c 200`
Expected: the built `index.html` (contains `<div id="root">` and a `/assets/index-` script). Stop the server.

- [ ] **Step 8: Run the Python suite and commit**

Run from the repo root: `.venv/Scripts/python -m pytest`
Expected: all pass (170 or more passed, 1 skipped on Windows).

```bash
git add web/package.json web/package-lock.json web/tsconfig.json web/vite.config.ts web/index.html web/src/main.tsx web/src/App.tsx web/src/App.test.tsx web/src/styles.css web/src/vite-env.d.ts web/src/test/setup.ts tests/server/test_static.py
git add viz/server/static.py   # only if Step 2 changed it
git commit -m "feat(web): Vite + React + TypeScript scaffold with vitest and production build" -m "Co-Authored-By: <model> <noreply@anthropic.com>
Claude-Session: <session url>"
```

---

### Task 2: API types and client

**Files:**
- Create: `web/src/api/types.ts`, `web/src/api/client.ts`, `web/src/api/client.test.ts`

**Interfaces:**
- Produces: the types `Column`, `ColumnType`, `Row`, `Chart`, `ChartData`, `ChartSource`, `Control`, `DateRangeControl`, `SelectControl`, `NumberRangeControl`, `Tile`, `Dashboard`, `Tree`, `TreeFolder`, `TreeItem`; the functions `fetchTree(): Promise<Tree>`, `fetchDashboard(id: string): Promise<Dashboard>`, `fetchChart(id: string): Promise<Chart>`, `fetchRows(id: string): Promise<Row[]>`, `dataUrl(id: string): string`; the errors `ApiError` (`status: number`, `detail: unknown`) and `DataTooLarge` (`bytes: number`); the constant `SMALL_LANE_MAX_BYTES = 20971520`.

- [ ] **Step 1: Write the failing tests**

`web/src/api/client.test.ts`:

```ts
import { afterEach, describe, expect, it, vi } from 'vitest';
import { ApiError, DataTooLarge, SMALL_LANE_MAX_BYTES, dataUrl, fetchChart, fetchRows, fetchTree } from './client';

function jsonResponse(body: unknown, status = 200, headers: Record<string, string> = {}) {
  const text = JSON.stringify(body);
  return new Response(text, {
    status,
    headers: { 'content-type': 'application/json', 'content-length': String(text.length), ...headers },
  });
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('client', () => {
  it('dataUrl keeps the id as a path', () => {
    expect(dataUrl('sales/emea/revenue')).toBe('/api/data/sales/emea/revenue');
  });

  it('fetchTree returns the parsed body', async () => {
    const fetchMock = vi.fn(async () => jsonResponse({ charts: {}, dashboards: {}, built_at: 'x' }));
    vi.stubGlobal('fetch', fetchMock);
    const tree = await fetchTree();
    expect(tree.built_at).toBe('x');
    expect(fetchMock).toHaveBeenCalledWith('/api/tree', expect.objectContaining({ headers: { Accept: 'application/json' } }));
  });

  it('non-2xx becomes ApiError with the detail', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => jsonResponse({ detail: { errors: ['id: bad'] } }, 422)));
    await expect(fetchChart('sales/x')).rejects.toMatchObject({ status: 422, detail: { errors: ['id: bad'] } });
    await expect(fetchChart('sales/x')).rejects.toBeInstanceOf(ApiError);
  });

  it('non-JSON error bodies keep the text', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => new Response('gateway down', { status: 502 })));
    await expect(fetchChart('sales/x')).rejects.toMatchObject({ status: 502, detail: 'gateway down' });
  });

  it('fetchRows returns row objects', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => jsonResponse([{ a: 1 }, { a: 2 }])));
    expect(await fetchRows('sales/x')).toEqual([{ a: 1 }, { a: 2 }]);
  });

  it('fetchRows refuses oversized bodies by Content-Length', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => jsonResponse([], 200, { 'content-length': String(SMALL_LANE_MAX_BYTES + 1) })),
    );
    await expect(fetchRows('sales/x')).rejects.toBeInstanceOf(DataTooLarge);
  });

  it('fetchRows rejects a body that is not an array of objects', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => jsonResponse({ rows: [] })));
    await expect(fetchRows('sales/x')).rejects.toMatchObject({ status: 422 });
    vi.stubGlobal('fetch', vi.fn(async () => new Response('not json', { status: 200 })));
    await expect(fetchRows('sales/x')).rejects.toMatchObject({ status: 422 });
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run from `web/`: `npm test -- src/api`
Expected: FAIL, `Failed to resolve import "./client"`.

- [ ] **Step 3: Write the types**

`web/src/api/types.ts`:

```ts
// Shapes of the documents the server returns. They mirror
// schemas/chart.schema.json, schemas/dashboard.schema.json and the tree built
// by viz/server/tree.py. Everything here is untrusted input.

export type ColumnType = 'string' | 'number' | 'integer' | 'boolean' | 'date' | 'timestamp';

export interface Column {
  name: string;
  type: ColumnType;
}

export type Row = Record<string, unknown>;

export type Renderer = 'vega-lite' | 'plotly' | 'echarts' | 'stat';

export interface ChartData {
  format: 'json' | 'parquet';
  lane: 'small' | 'large';
  rows: number;
  bytes: number;
  columns: Column[];
}

export interface ChartSource {
  kind: 'databricks-sql';
  sql?: string;
  warehouse_id?: string;
  schedule?: string;
  show_sql?: boolean;
}

export interface Chart {
  schema_version: 1;
  id: string;
  title: string;
  description?: string;
  tags?: string[];
  author?: string;
  created_at?: string;
  updated_at?: string;
  renderer: Renderer;
  spec: unknown;
  data: ChartData;
  aggregate?: string | null;
  source?: ChartSource;
}

export interface DateRangeControl {
  id: string;
  type: 'date-range';
  label: string;
  column: string;
  default?: null | { last: string } | { from: string; to: string };
}

export interface SelectControl {
  id: string;
  type: 'select';
  label: string;
  column: string;
  multi?: boolean;
  default?: null | string | string[];
}

export interface NumberRangeControl {
  id: string;
  type: 'number-range';
  label: string;
  column: string;
  default?: null | { min?: number; max?: number };
}

export type Control = DateRangeControl | SelectControl | NumberRangeControl;

export interface ChartTileSpec {
  chart: string;
  w: number;
  h: number;
}

export interface MarkdownTileSpec {
  markdown: string;
  w: number;
  h: number;
}

export type Tile = ChartTileSpec | MarkdownTileSpec;

export interface Dashboard {
  schema_version: 1;
  id: string;
  title: string;
  description?: string;
  tags?: string[];
  author?: string;
  created_at?: string;
  updated_at?: string;
  controls?: Control[];
  layout: Tile[];
}

export interface TreeChartItem {
  type: 'chart';
  id: string;
  title?: string;
  description?: string | null;
  tags?: string[];
  renderer?: string;
  lane?: string;
  static?: boolean;
  updated_at?: string | null;
  error?: string;
}

export interface TreeDashboardItem {
  type: 'dashboard';
  id: string;
  title?: string;
  description?: string | null;
  tags?: string[];
  controls?: Control[];
  updated_at?: string | null;
  error?: string;
}

export type TreeItem = TreeChartItem | TreeDashboardItem;

export interface TreeFolder {
  type: 'folder';
  path: string;
  name: string;
  title: string | null;
  description: string | null;
  order: number | null;
  error: string | null;
  folders: TreeFolder[];
  items: TreeItem[];
}

export interface Tree {
  charts: TreeFolder;
  dashboards: TreeFolder;
  built_at: string;
}
```

- [ ] **Step 4: Write the client**

`web/src/api/client.ts`:

```ts
import type { Chart, Dashboard, Row, Tree } from './types';

export const SMALL_LANE_MAX_BYTES = 20971520;

export class ApiError extends Error {
  status: number;
  detail: unknown;
  constructor(status: number, detail: unknown) {
    super(typeof detail === 'string' ? detail : `request failed with status ${status}`);
    this.name = 'ApiError';
    this.status = status;
    this.detail = detail;
  }
}

export class DataTooLarge extends Error {
  bytes: number;
  constructor(bytes: number) {
    super(`data file is ${bytes} bytes, above the small-lane cap of ${SMALL_LANE_MAX_BYTES}`);
    this.name = 'DataTooLarge';
    this.bytes = bytes;
  }
}

export function dataUrl(id: string): string {
  return `/api/data/${id}`;
}

function isPlainObject(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

async function readError(res: Response): Promise<unknown> {
  const text = await res.text();
  try {
    const body: unknown = JSON.parse(text);
    if (isPlainObject(body) && 'detail' in body) return body.detail;
    return body;
  } catch {
    return text;
  }
}

async function getJson<T>(url: string): Promise<T> {
  const res = await fetch(url, { headers: { Accept: 'application/json' } });
  if (!res.ok) throw new ApiError(res.status, await readError(res));
  return (await res.json()) as T;
}

export function fetchTree(): Promise<Tree> {
  return getJson<Tree>('/api/tree');
}

export function fetchDashboard(id: string): Promise<Dashboard> {
  return getJson<Dashboard>(`/api/dashboards/${id}`);
}

export function fetchChart(id: string): Promise<Chart> {
  return getJson<Chart>(`/api/charts/${id}`);
}

export async function fetchRows(id: string): Promise<Row[]> {
  const res = await fetch(dataUrl(id));
  if (!res.ok) throw new ApiError(res.status, await readError(res));
  const declared = Number(res.headers.get('content-length'));
  if (Number.isFinite(declared) && declared > SMALL_LANE_MAX_BYTES) throw new DataTooLarge(declared);
  const text = await res.text();
  if (text.length > SMALL_LANE_MAX_BYTES) throw new DataTooLarge(text.length);
  let parsed: unknown;
  try {
    parsed = JSON.parse(text);
  } catch {
    throw new ApiError(422, 'data file is not valid JSON');
  }
  if (!Array.isArray(parsed) || !parsed.every(isPlainObject)) {
    throw new ApiError(422, 'data file is not an array of row objects');
  }
  return parsed as Row[];
}
```

- [ ] **Step 5: Run tests to verify they pass**

Run from `web/`: `npm test -- src/api` then `npm run typecheck`
Expected: PASS (7 tests), typecheck clean.

- [ ] **Step 6: Commit**

```bash
git add web/src/api/types.ts web/src/api/client.ts web/src/api/client.test.ts
git commit -m "feat(web): API types and client with size cap and typed errors" -m "Co-Authored-By: <model> <noreply@anthropic.com>
Claude-Session: <session url>"
```

---

### Task 3: The one Markdown component

**Files:**
- Create: `web/src/components/Markdown.tsx`, `web/src/components/Markdown.test.tsx`, `web/src/test/noInnerHtml.test.ts`

**Interfaces:**
- Produces: `Markdown({ text }: { text: string })` React component; `safeUrl(url: string): string` (pure; returns `''` for anything not `http:`, `https:`, `mailto:` or a same-origin relative URL); `isSameOrigin(url: string): boolean`.

- [ ] **Step 1: Write the failing tests**

`web/src/components/Markdown.test.tsx`:

```tsx
import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { Markdown, safeUrl } from './Markdown';

describe('safeUrl', () => {
  it('allows http, https, mailto and relative', () => {
    expect(safeUrl('https://example.com/x')).toBe('https://example.com/x');
    expect(safeUrl('http://example.com')).toBe('http://example.com');
    expect(safeUrl('mailto:a@b.c')).toBe('mailto:a@b.c');
    expect(safeUrl('/d/sales/overview')).toBe('/d/sales/overview');
    expect(safeUrl('sales/overview')).toBe('sales/overview');
  });

  it('blocks other schemes and protocol-relative URLs', () => {
    expect(safeUrl('javascript:alert(1)')).toBe('');
    expect(safeUrl('JAVASCRIPT:alert(1)')).toBe('');
    expect(safeUrl('data:text/html,hi')).toBe('');
    expect(safeUrl('vbscript:x')).toBe('');
    expect(safeUrl('//evil.example/x')).toBe('');
    expect(safeUrl('  javascript:1')).toBe('');
  });
});

describe('Markdown', () => {
  it('renders emphasis and GFM tables, never raw HTML', () => {
    const { container } = render(<Markdown text={'**bold** <script>alert(1)</script> <b>raw</b>\n\n| a | b |\n|---|---|\n| 1 | 2 |'} />);
    expect(screen.getByText('bold').tagName).toBe('STRONG');
    expect(container.querySelector('script')).toBeNull();
    expect(container.querySelector('b')).toBeNull();
    expect(container.querySelector('table')).not.toBeNull();
  });

  it('links open in a new tab with the safe rel and unsafe hrefs are dropped', () => {
    render(<Markdown text={'[ok](https://example.com) [bad](javascript:alert(1))'} />);
    const ok = screen.getByText('ok');
    expect(ok.tagName).toBe('A');
    expect(ok).toHaveAttribute('href', 'https://example.com');
    expect(ok).toHaveAttribute('target', '_blank');
    expect(ok).toHaveAttribute('rel', 'noopener noreferrer nofollow');
    const bad = screen.getByText('bad');
    expect(bad.tagName).not.toBe('A');
  });

  it('renders same-origin images only', () => {
    const { container } = render(<Markdown text={'![a](/assets/a.png) ![b](https://evil.example/b.png)'} />);
    const imgs = container.querySelectorAll('img');
    expect(imgs).toHaveLength(1);
    expect(imgs[0]).toHaveAttribute('src', '/assets/a.png');
    expect(container.textContent).toContain('[image blocked]');
  });
});
```

`web/src/test/noInnerHtml.test.ts`:

```ts
import { readdirSync, readFileSync, statSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';

function walk(dir: string, out: string[] = []): string[] {
  for (const name of readdirSync(dir)) {
    const path = join(dir, name);
    if (statSync(path).isDirectory()) walk(path, out);
    else if (/\.(ts|tsx)$/.test(name) && !name.endsWith('.test.ts') && !name.endsWith('.test.tsx')) out.push(path);
  }
  return out;
}

describe('no raw HTML injection anywhere in the app', () => {
  it('dangerouslySetInnerHTML is not used', () => {
    const src = join(__dirname, '..');
    const offenders = walk(src).filter((path) => readFileSync(path, 'utf8').includes('dangerouslySetInnerHTML'));
    expect(offenders).toEqual([]);
  });

  it('innerHTML assignment is not used', () => {
    const src = join(__dirname, '..');
    const offenders = walk(src).filter((path) => /\.innerHTML\s*=/.test(readFileSync(path, 'utf8')));
    expect(offenders).toEqual([]);
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run from `web/`: `npm test -- src/components src/test`
Expected: the Markdown file fails with `Failed to resolve import "./Markdown"`; the noInnerHtml test passes already (nothing offends yet). That is fine: it is a guard that must keep passing.

- [ ] **Step 3: Implement**

`web/src/components/Markdown.tsx`:

```tsx
import type { ComponentProps } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

const ALLOWED_SCHEMES = new Set(['http', 'https', 'mailto']);

/** Returns the URL if it may be rendered, otherwise an empty string. */
export function safeUrl(url: string): string {
  const trimmed = url.trim();
  if (trimmed === '') return '';
  if (trimmed.startsWith('//')) return '';
  const colon = trimmed.indexOf(':');
  if (colon > 0 && /^[a-z][a-z0-9+.-]*$/i.test(trimmed.slice(0, colon))) {
    return ALLOWED_SCHEMES.has(trimmed.slice(0, colon).toLowerCase()) ? trimmed : '';
  }
  return trimmed;
}

export function isSameOrigin(url: string): boolean {
  try {
    return new URL(url, window.location.origin).origin === window.location.origin;
  } catch {
    return false;
  }
}

function Link({ href, children }: ComponentProps<'a'>) {
  if (!href) return <span>{children}</span>;
  return (
    <a href={href} target="_blank" rel="noopener noreferrer nofollow">
      {children}
    </a>
  );
}

function Image({ src, alt }: ComponentProps<'img'>) {
  if (typeof src !== 'string' || src === '' || !isSameOrigin(src)) return <span className="muted">[image blocked]</span>;
  return <img src={src} alt={alt ?? ''} />;
}

export function Markdown({ text }: { text: string }) {
  return (
    <ReactMarkdown
      skipHtml
      remarkPlugins={[remarkGfm]}
      urlTransform={(url) => safeUrl(url)}
      components={{ a: Link, img: Image }}
    >
      {text}
    </ReactMarkdown>
  );
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run from `web/`: `npm test` then `npm run typecheck`
Expected: PASS (all). If the `components` typing complains about the `node` prop, change the two component signatures to `({ href, children }: ComponentProps<'a'> & { node?: unknown })` and `({ src, alt }: ComponentProps<'img'> & { node?: unknown })` and report the change.

- [ ] **Step 5: Commit**

```bash
git add web/src/components/Markdown.tsx web/src/components/Markdown.test.tsx web/src/test/noInnerHtml.test.ts
git commit -m "feat(web): shared Markdown component with URL policy and no-innerHTML guard" -m "Co-Authored-By: <model> <noreply@anthropic.com>
Claude-Session: <session url>"
```

---

### Task 4: Filters, select options and date-range defaults

**Files:**
- Create: `web/src/data/filters.ts`, `web/src/data/filters.test.ts`

**Interfaces:**
- Consumes: `Row`, `Column`, `Control` from `web/src/api/types.ts`.
- Produces:
  - `type FilterValue = { type: 'date-range'; from: string | null; to: string | null } | { type: 'select'; values: string[] } | { type: 'number-range'; min: number | null; max: number | null } | { type: 'text'; text: string }`
  - `interface Filter { controlId: string; column: string; value: FilterValue }`
  - `applyFilters(rows: Row[], columns: Column[], filters: Filter[]): Row[]` (a filter whose column is not declared on the chart is skipped)
  - `isActive(value: FilterValue): boolean`
  - `MAX_SELECT_OPTIONS = 500`, `interface SelectOptions { options: string[]; tooMany: boolean }`, `selectOptions(rowSets: Row[][], column: string): SelectOptions`
  - `resolveLast(last: string, today: Date): { from: string; to: string }`, `isoDate(d: Date): string`
  - `defaultFilterValue(control: Control, today: Date, tooMany?: boolean): FilterValue`
  - `filterKey(filters: Filter[]): string` (stable string for effect dependencies)

- [ ] **Step 1: Write the failing tests**

`web/src/data/filters.test.ts`:

```ts
import { describe, expect, it } from 'vitest';
import type { Column, Control, Row } from '../api/types';
import {
  MAX_SELECT_OPTIONS,
  applyFilters,
  defaultFilterValue,
  filterKey,
  isActive,
  resolveLast,
  selectOptions,
} from './filters';

const columns: Column[] = [
  { name: 'month', type: 'date' },
  { name: 'region', type: 'string' },
  { name: 'revenue', type: 'number' },
];

const rows: Row[] = [
  { month: '2026-01-01', region: 'EMEA', revenue: 10 },
  { month: '2026-02-01', region: 'NA', revenue: 20 },
  { month: '2026-03-01', region: 'APAC', revenue: 30 },
  { month: '2026-03-01T12:00:00Z', region: 'EMEA', revenue: 40 },
];

describe('applyFilters', () => {
  it('filters dates by ISO prefix, inclusive', () => {
    const out = applyFilters(rows, columns, [
      { controlId: 'p', column: 'month', value: { type: 'date-range', from: '2026-02-01', to: '2026-03-01' } },
    ]);
    expect(out.map((r) => r.revenue)).toEqual([20, 30, 40]);
  });

  it('filters select by string equality and skips empty selections', () => {
    expect(
      applyFilters(rows, columns, [{ controlId: 'r', column: 'region', value: { type: 'select', values: ['EMEA'] } }]).length,
    ).toBe(2);
    expect(applyFilters(rows, columns, [{ controlId: 'r', column: 'region', value: { type: 'select', values: [] } }]).length).toBe(4);
  });

  it('filters number ranges and open ends', () => {
    expect(
      applyFilters(rows, columns, [{ controlId: 'n', column: 'revenue', value: { type: 'number-range', min: 20, max: null } }]).length,
    ).toBe(3);
    expect(
      applyFilters(rows, columns, [{ controlId: 'n', column: 'revenue', value: { type: 'number-range', min: null, max: 20 } }]).length,
    ).toBe(2);
  });

  it('text filter is a case-insensitive substring match', () => {
    expect(applyFilters(rows, columns, [{ controlId: 'r', column: 'region', value: { type: 'text', text: 'em' } }]).length).toBe(2);
  });

  it('skips filters whose column the chart does not declare', () => {
    expect(applyFilters(rows, columns, [{ controlId: 'x', column: 'nope', value: { type: 'select', values: ['a'] } }]).length).toBe(4);
  });
});

describe('selectOptions', () => {
  it('unions distinct values across charts, sorted', () => {
    const out = selectOptions([rows, [{ region: 'LATAM' }, { region: null }]], 'region');
    expect(out).toEqual({ options: ['APAC', 'EMEA', 'LATAM', 'NA'], tooMany: false });
  });

  it('flags too many options', () => {
    const many: Row[] = Array.from({ length: MAX_SELECT_OPTIONS + 1 }, (_, i) => ({ region: `r${i}` }));
    expect(selectOptions([many], 'region')).toEqual({ options: [], tooMany: true });
  });
});

describe('resolveLast', () => {
  const today = new Date(2026, 8, 22); // 2026-09-22 local
  it('handles d, w, m, y', () => {
    expect(resolveLast('10d', today)).toEqual({ from: '2026-09-12', to: '2026-09-22' });
    expect(resolveLast('2w', today)).toEqual({ from: '2026-09-08', to: '2026-09-22' });
    expect(resolveLast('12m', today)).toEqual({ from: '2025-09-22', to: '2026-09-22' });
    expect(resolveLast('1y', today)).toEqual({ from: '2025-09-22', to: '2026-09-22' });
  });
  it('rejects malformed input', () => {
    expect(() => resolveLast('12', today)).toThrow();
  });
});

describe('defaultFilterValue', () => {
  const today = new Date(2026, 8, 22);
  it('resolves control defaults', () => {
    const period: Control = { id: 'p', type: 'date-range', label: 'P', column: 'month', default: { last: '1y' } };
    expect(defaultFilterValue(period, today)).toEqual({ type: 'date-range', from: '2025-09-22', to: '2026-09-22' });
    const region: Control = { id: 'r', type: 'select', label: 'R', column: 'region', multi: true, default: ['EMEA', 'NA'] };
    expect(defaultFilterValue(region, today)).toEqual({ type: 'select', values: ['EMEA', 'NA'] });
    const single: Control = { id: 'r', type: 'select', label: 'R', column: 'region', default: 'EMEA' };
    expect(defaultFilterValue(single, today)).toEqual({ type: 'select', values: ['EMEA'] });
    const none: Control = { id: 'r', type: 'select', label: 'R', column: 'region', default: null };
    expect(defaultFilterValue(none, today)).toEqual({ type: 'select', values: [] });
    expect(defaultFilterValue(none, today, true)).toEqual({ type: 'text', text: '' });
    const n: Control = { id: 'n', type: 'number-range', label: 'N', column: 'revenue', default: { min: 5 } };
    expect(defaultFilterValue(n, today)).toEqual({ type: 'number-range', min: 5, max: null });
  });
});

describe('isActive and filterKey', () => {
  it('detects inactive values', () => {
    expect(isActive({ type: 'select', values: [] })).toBe(false);
    expect(isActive({ type: 'date-range', from: null, to: null })).toBe(false);
    expect(isActive({ type: 'number-range', min: null, max: null })).toBe(false);
    expect(isActive({ type: 'text', text: '' })).toBe(false);
    expect(isActive({ type: 'text', text: 'a' })).toBe(true);
  });
  it('filterKey is stable', () => {
    const f = [{ controlId: 'r', column: 'region', value: { type: 'select', values: ['a'] } as const }];
    expect(filterKey(f)).toBe(filterKey([...f]));
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run from `web/`: `npm test -- src/data`
Expected: FAIL, `Failed to resolve import "./filters"`.

- [ ] **Step 3: Implement**

`web/src/data/filters.ts`:

```ts
import type { Column, Control, Row } from '../api/types';

export type FilterValue =
  | { type: 'date-range'; from: string | null; to: string | null }
  | { type: 'select'; values: string[] }
  | { type: 'number-range'; min: number | null; max: number | null }
  | { type: 'text'; text: string };

export interface Filter {
  controlId: string;
  column: string;
  value: FilterValue;
}

export const MAX_SELECT_OPTIONS = 500;

export interface SelectOptions {
  options: string[];
  tooMany: boolean;
}

export function isActive(value: FilterValue): boolean {
  switch (value.type) {
    case 'date-range':
      return value.from !== null || value.to !== null;
    case 'select':
      return value.values.length > 0;
    case 'number-range':
      return value.min !== null || value.max !== null;
    case 'text':
      return value.text !== '';
  }
}

function dateKey(v: unknown): string | null {
  if (v === null || v === undefined) return null;
  if (v instanceof Date) return isoDate(v);
  return String(v).slice(0, 10);
}

function matches(v: unknown, value: FilterValue): boolean {
  switch (value.type) {
    case 'date-range': {
      const key = dateKey(v);
      if (key === null) return false;
      if (value.from !== null && key < value.from) return false;
      if (value.to !== null && key > value.to) return false;
      return true;
    }
    case 'select':
      return v !== null && v !== undefined && value.values.includes(String(v));
    case 'number-range': {
      const n = typeof v === 'number' ? v : Number(v);
      if (!Number.isFinite(n)) return false;
      if (value.min !== null && n < value.min) return false;
      if (value.max !== null && n > value.max) return false;
      return true;
    }
    case 'text':
      return v !== null && v !== undefined && String(v).toLowerCase().includes(value.text.toLowerCase());
  }
}

export function applyFilters(rows: Row[], columns: Column[], filters: Filter[]): Row[] {
  const declared = new Set(columns.map((c) => c.name));
  const active = filters.filter((f) => declared.has(f.column) && isActive(f.value));
  if (active.length === 0) return rows;
  return rows.filter((row) => active.every((f) => matches(row[f.column], f.value)));
}

export function selectOptions(rowSets: Row[][], column: string): SelectOptions {
  const seen = new Set<string>();
  for (const rows of rowSets) {
    for (const row of rows) {
      const v = row[column];
      if (v === null || v === undefined) continue;
      seen.add(String(v));
      if (seen.size > MAX_SELECT_OPTIONS) return { options: [], tooMany: true };
    }
  }
  return { options: [...seen].sort(), tooMany: false };
}

export function isoDate(d: Date): string {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, '0');
  const day = String(d.getDate()).padStart(2, '0');
  return `${y}-${m}-${day}`;
}

export function resolveLast(last: string, today: Date): { from: string; to: string } {
  const m = /^(\d{1,3})([dwmy])$/.exec(last);
  if (!m) throw new Error(`invalid date-range default: ${last}`);
  const n = Number(m[1]);
  const from = new Date(today.getTime());
  switch (m[2]) {
    case 'd':
      from.setDate(from.getDate() - n);
      break;
    case 'w':
      from.setDate(from.getDate() - 7 * n);
      break;
    case 'm':
      from.setMonth(from.getMonth() - n);
      break;
    case 'y':
      from.setFullYear(from.getFullYear() - n);
      break;
  }
  return { from: isoDate(from), to: isoDate(today) };
}

export function defaultFilterValue(control: Control, today: Date, tooMany = false): FilterValue {
  switch (control.type) {
    case 'date-range': {
      const d = control.default;
      if (!d) return { type: 'date-range', from: null, to: null };
      if ('last' in d) {
        const r = resolveLast(d.last, today);
        return { type: 'date-range', from: r.from, to: r.to };
      }
      return { type: 'date-range', from: d.from, to: d.to };
    }
    case 'select': {
      if (tooMany) return { type: 'text', text: '' };
      const d = control.default;
      if (d === null || d === undefined) return { type: 'select', values: [] };
      return { type: 'select', values: Array.isArray(d) ? d : [d] };
    }
    case 'number-range': {
      const d = control.default;
      return { type: 'number-range', min: d?.min ?? null, max: d?.max ?? null };
    }
  }
}

export function filterKey(filters: Filter[]): string {
  return JSON.stringify(filters.map((f) => [f.controlId, f.column, f.value]));
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run from `web/`: `npm test -- src/data` then `npm run typecheck`
Expected: PASS (13 tests), typecheck clean.

- [ ] **Step 5: Commit**

```bash
git add web/src/data/filters.ts web/src/data/filters.test.ts
git commit -m "feat(web): small-lane filters, select options and date-range defaults" -m "Co-Authored-By: <model> <noreply@anthropic.com>
Claude-Session: <session url>"
```

---

### Task 5: Filter state in the URL

**Files:**
- Create: `web/src/state/urlState.ts`, `web/src/state/urlState.test.ts`

**Interfaces:**
- Consumes: `Filter`, `FilterValue`, `SelectOptions`, `defaultFilterValue`, `isActive` from `web/src/data/filters.ts`; `Control` from `web/src/api/types.ts`.
- Produces: `encodeFilters(filters: Filter[]): URLSearchParams` and `decodeFilters(params: URLSearchParams, controls: Control[], options: Record<string, SelectOptions | undefined>, today: Date): Filter[]`.
- Encoding, one query parameter per control keyed by control id: date-range `from..to` (either side may be empty); number-range `min..max`; select `v1,v2` with each value passed through `encodeURIComponent` before joining; text `~text`; an inactive value is written as `-` so that clearing a control that has a default is representable. A missing parameter means "use the control default". Unknown parameters are ignored.
- Decoding validates: dates must match `YYYY-MM-DD` and be real dates; numbers must be finite; select values must be in `options[control.id].options` when that entry exists and `tooMany` is false (unknown values are dropped); when `options[control.id]` is undefined (rows not loaded yet) the values pass through unvalidated and are re-validated on the next render; when `tooMany` is true the control decodes as a text filter.

- [ ] **Step 1: Write the failing tests**

`web/src/state/urlState.test.ts`:

```ts
import { describe, expect, it } from 'vitest';
import type { Control } from '../api/types';
import type { Filter } from '../data/filters';
import { decodeFilters, encodeFilters } from './urlState';

const controls: Control[] = [
  { id: 'period', type: 'date-range', label: 'Period', column: 'month', default: { last: '1y' } },
  { id: 'region', type: 'select', label: 'Region', column: 'region', multi: true, default: null },
  { id: 'minrev', type: 'number-range', label: 'Revenue', column: 'revenue', default: null },
];
const today = new Date(2026, 8, 22);
const options = { region: { options: ['APAC', 'EMEA', 'NA'], tooMany: false } };

describe('encodeFilters', () => {
  it('writes one parameter per control and marks inactive values', () => {
    const filters: Filter[] = [
      { controlId: 'period', column: 'month', value: { type: 'date-range', from: '2026-01-01', to: null } },
      { controlId: 'region', column: 'region', value: { type: 'select', values: ['EMEA', 'N,A'] } },
      { controlId: 'minrev', column: 'revenue', value: { type: 'number-range', min: null, max: null } },
    ];
    const params = encodeFilters(filters);
    expect(params.get('period')).toBe('2026-01-01..');
    expect(params.get('region')).toBe('EMEA,N%2CA');
    expect(params.get('minrev')).toBe('-');
  });
});

describe('decodeFilters', () => {
  it('uses defaults when a parameter is absent', () => {
    const out = decodeFilters(new URLSearchParams(''), controls, options, today);
    expect(out).toEqual([
      { controlId: 'period', column: 'month', value: { type: 'date-range', from: '2025-09-22', to: '2026-09-22' } },
      { controlId: 'region', column: 'region', value: { type: 'select', values: [] } },
      { controlId: 'minrev', column: 'revenue', value: { type: 'number-range', min: null, max: null } },
    ]);
  });

  it('round-trips values and honours the cleared marker', () => {
    const params = new URLSearchParams('period=-&region=EMEA,N%2CA,NA&minrev=10..20.5&junk=1');
    const out = decodeFilters(params, controls, options, today);
    expect(out[0].value).toEqual({ type: 'date-range', from: null, to: null });
    expect(out[1].value).toEqual({ type: 'select', values: ['EMEA', 'NA'] }); // "N,A" is not an option
    expect(out[2].value).toEqual({ type: 'number-range', min: 10, max: 20.5 });
  });

  it('rejects malformed dates and numbers by falling back to the default', () => {
    const params = new URLSearchParams('period=2026-13-45..x&minrev=abc..1e999');
    const out = decodeFilters(params, controls, options, today);
    expect(out[0].value).toEqual({ type: 'date-range', from: '2025-09-22', to: '2026-09-22' });
    expect(out[2].value).toEqual({ type: 'number-range', min: null, max: null });
  });

  it('passes select values through while options are unknown', () => {
    const out = decodeFilters(new URLSearchParams('region=ZZ'), controls, {}, today);
    expect(out[1].value).toEqual({ type: 'select', values: ['ZZ'] });
  });

  it('decodes a text filter when the option set is too large', () => {
    const tooMany = { region: { options: [], tooMany: true } };
    expect(decodeFilters(new URLSearchParams('region=~em'), controls, tooMany, today)[1].value).toEqual({ type: 'text', text: 'em' });
    expect(decodeFilters(new URLSearchParams(''), controls, tooMany, today)[1].value).toEqual({ type: 'text', text: '' });
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run from `web/`: `npm test -- src/state`
Expected: FAIL, `Failed to resolve import "./urlState"`.

- [ ] **Step 3: Implement**

`web/src/state/urlState.ts`:

```ts
import type { Control } from '../api/types';
import { defaultFilterValue, isActive, type Filter, type FilterValue, type SelectOptions } from '../data/filters';

const CLEARED = '-';

function encodeValue(value: FilterValue): string {
  if (!isActive(value)) return CLEARED;
  switch (value.type) {
    case 'date-range':
      return `${value.from ?? ''}..${value.to ?? ''}`;
    case 'number-range':
      return `${value.min ?? ''}..${value.max ?? ''}`;
    case 'select':
      return value.values.map(encodeURIComponent).join(',');
    case 'text':
      return `~${value.text}`;
  }
}

export function encodeFilters(filters: Filter[]): URLSearchParams {
  const params = new URLSearchParams();
  for (const f of filters) params.set(f.controlId, encodeValue(f.value));
  return params;
}

function parseDate(s: string): string | null | undefined {
  // undefined: malformed. null: open end. string: valid ISO date.
  if (s === '') return null;
  if (!/^\d{4}-\d{2}-\d{2}$/.test(s)) return undefined;
  const d = new Date(`${s}T00:00:00Z`);
  if (Number.isNaN(d.getTime()) || d.toISOString().slice(0, 10) !== s) return undefined;
  return s;
}

function parseNumber(s: string): number | null | undefined {
  if (s === '') return null;
  const n = Number(s);
  return Number.isFinite(n) ? n : undefined;
}

function decodeValue(raw: string, control: Control, opts: SelectOptions | undefined): FilterValue | undefined {
  switch (control.type) {
    case 'date-range': {
      const parts = raw.split('..');
      if (parts.length !== 2) return undefined;
      const from = parseDate(parts[0]);
      const to = parseDate(parts[1]);
      if (from === undefined || to === undefined) return undefined;
      return { type: 'date-range', from, to };
    }
    case 'number-range': {
      const parts = raw.split('..');
      if (parts.length !== 2) return undefined;
      const min = parseNumber(parts[0]);
      const max = parseNumber(parts[1]);
      if (min === undefined || max === undefined) return undefined;
      return { type: 'number-range', min, max };
    }
    case 'select': {
      if (opts?.tooMany) {
        return { type: 'text', text: raw.startsWith('~') ? raw.slice(1) : raw };
      }
      let values: string[];
      try {
        values = raw.split(',').map(decodeURIComponent).filter((v) => v !== '');
      } catch {
        return undefined;
      }
      if (opts) values = values.filter((v) => opts.options.includes(v));
      if (!control.multi && values.length > 1) values = values.slice(0, 1);
      return { type: 'select', values };
    }
  }
}

export function decodeFilters(
  params: URLSearchParams,
  controls: Control[],
  options: Record<string, SelectOptions | undefined>,
  today: Date,
): Filter[] {
  return controls.map((control) => {
    const opts = options[control.id];
    const tooMany = control.type === 'select' && opts?.tooMany === true;
    const fallback = defaultFilterValue(control, today, tooMany);
    const raw = params.get(control.id);
    let value: FilterValue = fallback;
    if (raw === CLEARED) {
      value = tooMany ? { type: 'text', text: '' } : clearedValue(control);
    } else if (raw !== null) {
      value = decodeValue(raw, control, opts) ?? fallback;
    }
    return { controlId: control.id, column: control.column, value };
  });
}

function clearedValue(control: Control): FilterValue {
  switch (control.type) {
    case 'date-range':
      return { type: 'date-range', from: null, to: null };
    case 'number-range':
      return { type: 'number-range', min: null, max: null };
    case 'select':
      return { type: 'select', values: [] };
  }
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run from `web/`: `npm test -- src/state` then `npm run typecheck`
Expected: PASS (6 tests), typecheck clean.

- [ ] **Step 5: Commit**

```bash
git add web/src/state/urlState.ts web/src/state/urlState.test.ts
git commit -m "feat(web): filter state encoded in and validated from the URL" -m "Co-Authored-By: <model> <noreply@anthropic.com>
Claude-Session: <session url>"
```

---

### Task 6: Renderer common helpers and the stat tile

**Files:**
- Create: `web/src/renderers/common.ts`, `web/src/renderers/common.test.ts`, `web/src/components/StatTile.tsx`, `web/src/components/StatTile.test.tsx`

**Interfaces:**
- Consumes: `Row` from `web/src/api/types.ts`.
- Produces in `common.ts`: `class SanitizeError extends Error`; `assertPlain(value: unknown, path?: string): void` (throws `SanitizeError` unless every nested value is a primitive, an Array, or an object whose prototype is `Object.prototype` or `null`; functions, class instances, Maps, Dates all rejected); `deepClone<T>(value: T): T` (structured copy into fresh plain objects, keys `__proto__`, `constructor`, `prototype` dropped); `walk(node: unknown, visit: (obj: Record<string, unknown>, key: string, value: unknown, path: string) => void, path?: string): void` (calls `visit` for every own key of every nested plain object, depth first, parents before children; `visit` may `delete obj[key]` or reassign `obj[key]`); `type Agg = 'sum' | 'avg' | 'min' | 'max' | 'count' | 'last'`; `AGGS: readonly Agg[]`; `isPlainObject(v: unknown): v is Record<string, unknown>`; `UNSAFE_KEYS = ['__proto__', 'constructor', 'prototype']`.
- Produces in `StatTile.tsx`: `interface StatSpec { value: string; agg: Agg; format?: string; compare?: { column: string; agg: Agg } }`; `parseStatSpec(spec: unknown, columns: string[]): StatSpec` (throws `SanitizeError`); `aggregate(rows: Row[], column: string, agg: Agg): number | null`; `formatValue(value: number | null, format?: string): string`; component `StatTile({ spec, rows, columns }: { spec: unknown; rows: Row[]; columns: string[] })`.

- [ ] **Step 1: Write the failing tests**

`web/src/renderers/common.test.ts`:

```ts
import { describe, expect, it } from 'vitest';
import { SanitizeError, assertPlain, deepClone, walk } from './common';

describe('assertPlain', () => {
  it('accepts JSON-shaped values', () => {
    expect(() => assertPlain({ a: [1, 'x', null, { b: true }] })).not.toThrow();
    expect(() => assertPlain(Object.create(null))).not.toThrow();
  });
  it('rejects functions, class instances, Dates and Maps at any depth', () => {
    expect(() => assertPlain({ a: () => 1 })).toThrow(SanitizeError);
    expect(() => assertPlain({ a: [new Date()] })).toThrow(SanitizeError);
    expect(() => assertPlain(new Map())).toThrow(SanitizeError);
    class X {}
    expect(() => assertPlain({ x: new X() })).toThrow(SanitizeError);
  });
});

describe('deepClone', () => {
  it('copies and drops prototype-polluting keys', () => {
    const src = JSON.parse('{"a":{"b":1},"__proto__":{"polluted":true},"constructor":1}');
    const out = deepClone(src) as Record<string, unknown>;
    expect(out).toEqual({ a: { b: 1 } });
    expect(out.a).not.toBe(src.a);
    expect(Object.keys(out)).toEqual(['a']);
    expect(({} as Record<string, unknown>).polluted).toBeUndefined();
  });
});

describe('walk', () => {
  it('visits every key with its path and allows deletion', () => {
    const spec = { a: 1, b: { c: [{ d: 2 }], e: 3 } };
    const seen: string[] = [];
    walk(spec, (obj, key, _value, path) => {
      seen.push(path);
      if (key === 'e') delete obj[key];
    });
    expect(seen).toEqual(['spec/a', 'spec/b', 'spec/b/c', 'spec/b/c/0/d', 'spec/b/e']);
    expect(spec.b).toEqual({ c: [{ d: 2 }] });
  });
});
```

`web/src/components/StatTile.test.tsx`:

```tsx
import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { SanitizeError } from '../renderers/common';
import { StatTile, aggregate, formatValue, parseStatSpec } from './StatTile';

const rows = [
  { revenue: 10, orders: 1 },
  { revenue: 20, orders: 2 },
  { revenue: 30, orders: 3 },
];

describe('aggregate', () => {
  it('computes every agg and ignores non-numeric values', () => {
    expect(aggregate(rows, 'revenue', 'sum')).toBe(60);
    expect(aggregate(rows, 'revenue', 'avg')).toBe(20);
    expect(aggregate(rows, 'revenue', 'min')).toBe(10);
    expect(aggregate(rows, 'revenue', 'max')).toBe(30);
    expect(aggregate(rows, 'revenue', 'count')).toBe(3);
    expect(aggregate(rows, 'revenue', 'last')).toBe(30);
    expect(aggregate([{ revenue: 'x' }, { revenue: 5 }], 'revenue', 'sum')).toBe(5);
    expect(aggregate([], 'revenue', 'sum')).toBeNull();
  });
});

describe('formatValue', () => {
  it('uses d3-format and falls back on a bad format', () => {
    expect(formatValue(1234.5, '$,.0f')).toBe('$1,235');
    expect(formatValue(1234.5)).toBe('1,234.5');
    expect(formatValue(1234.5, '%%%%q')).toBe('1234.5');
    expect(formatValue(null, '$,.0f')).toBe('–');
  });
});

describe('parseStatSpec', () => {
  it('accepts a valid spec and rejects unknown columns, aggs and shapes', () => {
    expect(parseStatSpec({ value: 'revenue', agg: 'sum' }, ['revenue'])).toEqual({ value: 'revenue', agg: 'sum' });
    expect(() => parseStatSpec({ value: 'nope', agg: 'sum' }, ['revenue'])).toThrow(SanitizeError);
    expect(() => parseStatSpec({ value: 'revenue', agg: 'median' }, ['revenue'])).toThrow(SanitizeError);
    expect(() => parseStatSpec({ value: 'revenue', agg: 'sum', compare: { column: 'x', agg: 'sum' } }, ['revenue'])).toThrow(SanitizeError);
    expect(() => parseStatSpec('sum', ['revenue'])).toThrow(SanitizeError);
    expect(() => parseStatSpec({ value: 'revenue', agg: 'sum', format: 123 }, ['revenue'])).toThrow(SanitizeError);
  });
});

describe('StatTile', () => {
  it('renders the value and the comparison line', () => {
    render(
      <StatTile
        spec={{ value: 'revenue', agg: 'sum', format: ',.0f', compare: { column: 'orders', agg: 'sum' } }}
        rows={rows}
        columns={['revenue', 'orders']}
      />,
    );
    expect(screen.getByTestId('stat-value')).toHaveTextContent('60');
    expect(screen.getByTestId('stat-compare')).toHaveTextContent('orders (sum): 6');
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run from `web/`: `npm test -- src/renderers src/components/StatTile`
Expected: FAIL, unresolved imports `./common` and `./StatTile`.

- [ ] **Step 3: Implement common helpers**

`web/src/renderers/common.ts`:

```ts
// Helpers shared by every renderer sanitizer. Pure: no DOM, no library imports.

export class SanitizeError extends Error {
  constructor(message: string) {
    super(message);
    this.name = 'SanitizeError';
  }
}

export type Agg = 'sum' | 'avg' | 'min' | 'max' | 'count' | 'last';
export const AGGS: readonly Agg[] = ['sum', 'avg', 'min', 'max', 'count', 'last'];

export const UNSAFE_KEYS = ['__proto__', 'constructor', 'prototype'];

export function isPlainObject(v: unknown): v is Record<string, unknown> {
  if (typeof v !== 'object' || v === null || Array.isArray(v)) return false;
  const proto = Object.getPrototypeOf(v);
  return proto === Object.prototype || proto === null;
}

export function assertPlain(value: unknown, path = 'spec'): void {
  if (value === null) return;
  const t = typeof value;
  if (t === 'string' || t === 'number' || t === 'boolean' || t === 'undefined') return;
  if (Array.isArray(value)) {
    value.forEach((v, i) => assertPlain(v, `${path}/${i}`));
    return;
  }
  if (isPlainObject(value)) {
    for (const key of Object.keys(value)) assertPlain(value[key], `${path}/${key}`);
    return;
  }
  throw new SanitizeError(`${path}: only plain JSON values are allowed`);
}

export function deepClone<T>(value: T): T {
  if (Array.isArray(value)) return value.map((v) => deepClone(v)) as unknown as T;
  if (isPlainObject(value)) {
    const out: Record<string, unknown> = {};
    for (const key of Object.keys(value)) {
      if (UNSAFE_KEYS.includes(key)) continue;
      out[key] = deepClone(value[key]);
    }
    return out as T;
  }
  return value;
}

export function walk(
  node: unknown,
  visit: (obj: Record<string, unknown>, key: string, value: unknown, path: string) => void,
  path = 'spec',
): void {
  if (Array.isArray(node)) {
    node.forEach((v, i) => walk(v, visit, `${path}/${i}`));
    return;
  }
  if (!isPlainObject(node)) return;
  for (const key of Object.keys(node)) {
    const here = `${path}/${key}`;
    visit(node, key, node[key], here);
    if (key in node) walk(node[key], visit, here);
  }
}
```

- [ ] **Step 4: Implement the stat tile**

`web/src/components/StatTile.tsx`:

```tsx
import { format as d3format } from 'd3-format';
import type { Row } from '../api/types';
import { AGGS, SanitizeError, isPlainObject, type Agg } from '../renderers/common';

export interface StatSpec {
  value: string;
  agg: Agg;
  format?: string;
  compare?: { column: string; agg: Agg };
}

function isAgg(v: unknown): v is Agg {
  return typeof v === 'string' && (AGGS as readonly string[]).includes(v);
}

export function parseStatSpec(spec: unknown, columns: string[]): StatSpec {
  if (!isPlainObject(spec)) throw new SanitizeError('stat spec must be an object');
  const { value, agg, format, compare } = spec;
  if (typeof value !== 'string' || !columns.includes(value)) throw new SanitizeError(`stat value column unknown: ${String(value)}`);
  if (!isAgg(agg)) throw new SanitizeError(`stat agg unknown: ${String(agg)}`);
  const out: StatSpec = { value, agg };
  if (format !== undefined) {
    if (typeof format !== 'string' || format.length > 32) throw new SanitizeError('stat format must be a short string');
    out.format = format;
  }
  if (compare !== undefined) {
    if (!isPlainObject(compare)) throw new SanitizeError('stat compare must be an object');
    if (typeof compare.column !== 'string' || !columns.includes(compare.column)) {
      throw new SanitizeError(`stat compare column unknown: ${String(compare.column)}`);
    }
    if (!isAgg(compare.agg)) throw new SanitizeError(`stat compare agg unknown: ${String(compare.agg)}`);
    out.compare = { column: compare.column, agg: compare.agg };
  }
  return out;
}

export function aggregate(rows: Row[], column: string, agg: Agg): number | null {
  const values = rows.map((r) => r[column]).filter((v): v is number => typeof v === 'number' && Number.isFinite(v));
  if (agg === 'count') return rows.length === 0 ? null : values.length;
  if (values.length === 0) return null;
  switch (agg) {
    case 'sum':
      return values.reduce((a, b) => a + b, 0);
    case 'avg':
      return values.reduce((a, b) => a + b, 0) / values.length;
    case 'min':
      return Math.min(...values);
    case 'max':
      return Math.max(...values);
    case 'last':
      return values[values.length - 1];
  }
}

export function formatValue(value: number | null, format?: string): string {
  if (value === null) return '–';
  try {
    return d3format(format ?? ',')(value);
  } catch {
    return String(value);
  }
}

export function StatTile({ spec, rows, columns }: { spec: unknown; rows: Row[]; columns: string[] }) {
  const parsed = parseStatSpec(spec, columns);
  const main = aggregate(rows, parsed.value, parsed.agg);
  return (
    <div className="stat">
      <div className="stat-value" data-testid="stat-value">
        {formatValue(main, parsed.format)}
      </div>
      {parsed.compare && (
        <div className="stat-compare" data-testid="stat-compare">
          {parsed.compare.column} ({parsed.compare.agg}): {formatValue(aggregate(rows, parsed.compare.column, parsed.compare.agg), parsed.format)}
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 5: Run tests to verify they pass**

Run from `web/`: `npm test` then `npm run typecheck`
Expected: PASS (all), typecheck clean.

- [ ] **Step 6: Commit**

```bash
git add web/src/renderers/common.ts web/src/renderers/common.test.ts web/src/components/StatTile.tsx web/src/components/StatTile.test.tsx
git commit -m "feat(web): sanitizer helpers and stat tile" -m "Co-Authored-By: <model> <noreply@anthropic.com>
Claude-Session: <session url>"
```

---

### Task 7: Vega-Lite sanitizer and adapter

**Files:**
- Create: `web/src/renderers/adapter.ts`, `web/src/renderers/vegaLiteSanitize.ts`, `web/src/renderers/vegaLiteSanitize.test.ts`, `web/src/renderers/vegaLite.ts`, `web/src/renderers/vegaLite.test.ts`

**Interfaces:**
- Consumes: `SanitizeError`, `assertPlain`, `deepClone`, `isPlainObject`, `walk` from `web/src/renderers/common.ts`; `Row`, `Column` from `web/src/api/types.ts`.
- Produces: `interface Adapter { mount(el: HTMLElement, spec: unknown, rows: Row[], columns: Column[]): Promise<void>; update(rows: Row[]): Promise<void>; destroy(): void }` in `adapter.ts`; `sanitize(spec: unknown): Record<string, unknown>` and `RULES: readonly string[]` in `vegaLiteSanitize.ts`; `createAdapter(): Adapter` and `rejectingLoader()` in `vegaLite.ts`. The adapter calls `sanitize` itself inside `mount`, so callers may pass the raw spec.

- [ ] **Step 1: Write the failing tests**

`web/src/renderers/vegaLiteSanitize.test.ts`:

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
    expect(() => sanitize({ ...base, layer: [{ data: { url: 'https://x' }, mark: 'point' }] })).toThrow(/url/);
    expect(() => sanitize({ ...base, encoding: { ...base.encoding, href: { field: 'link' } } })).toThrow(/href/);
    expect(() => sanitize({ ...base, transform: [{ lookup: 'a', from: { data: { values: [1] }, key: 'a' } }] })).toThrow(/values/);
    expect(() => sanitize({ ...base, usermeta: { x: 1 } })).toThrow(/usermeta/);
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
  });
});
```

`web/src/renderers/vegaLite.test.ts`:

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
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run from `web/`: `npm test -- src/renderers/vegaLite`
Expected: FAIL, unresolved imports `./vegaLiteSanitize` and `./vegaLite`.

- [ ] **Step 3: Implement**

`web/src/renderers/adapter.ts`:

```ts
import type { Column, Row } from '../api/types';

/** One renderer. mount() sanitizes the spec itself; callers pass the raw spec from the bucket. */
export interface Adapter {
  mount(el: HTMLElement, spec: unknown, rows: Row[], columns: Column[]): Promise<void>;
  update(rows: Row[]): Promise<void>;
  destroy(): void;
}
```

`web/src/renderers/vegaLiteSanitize.ts`:

```ts
// Spec 12.3, Vega-Lite: null loader, actions off, canvas renderer, interpreter
// instead of eval, and reject url / values / href / image marks / usermeta at
// any depth. Pure: no DOM, no vega import.
import { SanitizeError, assertPlain, deepClone, isPlainObject, walk } from './common';

export const RULES: readonly string[] = [
  'spec must be a plain JSON object',
  'top-level data must be exactly {"name": "data"}',
  'key "url" rejected at any depth',
  'key "values" rejected at any depth',
  'key "href" rejected at any depth',
  'key "usermeta" rejected at any depth',
  'image marks rejected',
  'loader refuses load, sanitize, http and file',
  'actions menu off, canvas renderer, ast interpreter (no eval)',
];

const FORBIDDEN_KEYS = new Set(['url', 'values', 'href', 'usermeta']);

export function sanitize(spec: unknown): Record<string, unknown> {
  assertPlain(spec);
  if (!isPlainObject(spec)) throw new SanitizeError('vega-lite spec must be an object');
  const clean = deepClone(spec);
  const data = clean.data;
  if (!isPlainObject(data) || Object.keys(data).length !== 1 || data.name !== 'data') {
    throw new SanitizeError('vega-lite data must be exactly {"name": "data"}');
  }
  walk(clean, (_obj, key, value, path) => {
    if (FORBIDDEN_KEYS.has(key)) throw new SanitizeError(`${path}: key "${key}" is not allowed`);
    if (key === 'mark' && (value === 'image' || (isPlainObject(value) && value.type === 'image'))) {
      throw new SanitizeError(`${path}: image marks are not allowed`);
    }
  });
  return clean;
}
```

`web/src/renderers/vegaLite.ts`:

```ts
import type { Column, Row } from '../api/types';
import type { Adapter } from './adapter';
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

  return {
    async mount(el: HTMLElement, spec: unknown, rows: Row[], _columns: Column[]): Promise<void> {
      const clean = sanitize(spec);
      if (clean.width === undefined) clean.width = 'container';
      if (clean.height === undefined) clean.height = 'container';
      const [{ default: embed }, { expressionInterpreter }] = await Promise.all([import('vega-embed'), import('vega-interpreter')]);
      const embedded = await embed(el, clean as never, {
        actions: false,
        renderer: 'canvas',
        ast: true,
        expr: expressionInterpreter as never,
        loader: rejectingLoader() as never,
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
    },
  };
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run from `web/`: `npm test -- src/renderers` then `npm run typecheck`
Expected: PASS. If typecheck rejects the `embed(...)` option types, keep the `as never` casts and report which option needed it; do not loosen `strict`.

- [ ] **Step 5: Commit**

```bash
git add web/src/renderers/adapter.ts web/src/renderers/vegaLiteSanitize.ts web/src/renderers/vegaLiteSanitize.test.ts web/src/renderers/vegaLite.ts web/src/renderers/vegaLite.test.ts
git commit -m "feat(web): Vega-Lite sanitizer and adapter with rejecting loader and interpreter" -m "Co-Authored-By: <model> <noreply@anthropic.com>
Claude-Session: <session url>"
```

---

### Task 8: ECharts sanitizer and adapter

**Files:**
- Create: `web/src/renderers/echartsSanitize.ts`, `web/src/renderers/echartsSanitize.test.ts`, `web/src/renderers/echarts.ts`, `web/src/renderers/echarts.test.ts`

**Interfaces:**
- Consumes: `Adapter` from `adapter.ts`; helpers from `common.ts`.
- Produces: `sanitize(spec: unknown): Record<string, unknown>` and `RULES` in `echartsSanitize.ts`; `createAdapter(): Adapter` and `buildOption(clean: Record<string, unknown>, rows: Row[], columns: Column[]): Record<string, unknown>` in `echarts.ts`. `buildOption` injects `dataset` and expands any series carrying `split: "<column>"` into one series per distinct value, each backed by a `filter` dataset transform (`{ dimension, '=': value }`).

- [ ] **Step 1: Write the failing tests**

`web/src/renderers/echartsSanitize.test.ts`:

```ts
import { describe, expect, it } from 'vitest';
import { SanitizeError } from './common';
import { RULES, sanitize } from './echartsSanitize';

const base = {
  xAxis: { type: 'category' },
  yAxis: { type: 'value' },
  tooltip: { trigger: 'axis' },
  series: [{ type: 'bar', encode: { x: 'region', y: 'orders' } }],
};

describe('echarts sanitize', () => {
  it('forces richText tooltips everywhere', () => {
    const out = sanitize({ ...base, series: [{ ...base.series[0], tooltip: { formatter: '{b}' } }] });
    expect((out.tooltip as Record<string, unknown>).renderMode).toBe('richText');
    const series = out.series as Record<string, unknown>[];
    expect((series[0].tooltip as Record<string, unknown>).renderMode).toBe('richText');
    expect(sanitize({ ...base, tooltip: true }).tooltip).toEqual({ renderMode: 'richText' });
    expect(sanitize({ ...base, tooltip: { renderMode: 'html' } }).tooltip).toEqual({ renderMode: 'richText' });
  });

  it('deletes the DOM-reaching keys at any depth', () => {
    const out = sanitize({
      ...base,
      graphic: [{ type: 'text' }],
      title: { text: 't', link: 'https://x', sublink: 'https://y' },
      tooltip: { extraCssText: 'x', appendTo: 'body', className: 'c' },
    });
    expect(out.graphic).toBeUndefined();
    expect(out.title).toEqual({ text: 't' });
    expect(out.tooltip).toEqual({ renderMode: 'richText' });
  });

  it('rejects HTML and non-string formatters', () => {
    expect(() => sanitize({ ...base, tooltip: { formatter: '<b>{b}</b>' } })).toThrow(SanitizeError);
    expect(() => sanitize({ ...base, xAxis: { axisLabel: { formatter: '<img>' } } })).toThrow(/formatter/);
    expect(() => sanitize({ ...base, tooltip: { formatter: ['{a}'] } })).toThrow(/formatter/);
    expect(sanitize({ ...base, tooltip: { formatter: '{b}: {c}' } })).toBeTruthy();
  });

  it('rejects dataset and inline data', () => {
    expect(() => sanitize({ ...base, dataset: { source: [] } })).toThrow(/dataset/);
    expect(() => sanitize({ ...base, series: [{ type: 'bar', data: [1, 2] }] })).toThrow(/data/);
  });

  it('requires series to be objects and the spec to be plain', () => {
    expect(() => sanitize({ ...base, series: ['bar'] })).toThrow(SanitizeError);
    expect(() => sanitize({ ...base, series: { type: 'bar' } })).not.toThrow();
    expect(() => sanitize({ ...base, series: [{ type: 'bar', itemStyle: { color: () => 'red' } }] })).toThrow(SanitizeError);
    expect(() => sanitize([])).toThrow(SanitizeError);
  });

  it('publishes its rule list', () => {
    expect(RULES.length).toBeGreaterThanOrEqual(6);
  });
});
```

`web/src/renderers/echarts.test.ts`:

```ts
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { buildOption, createAdapter } from './echarts';

const mocks = vi.hoisted(() => {
  const chart = { setOption: vi.fn(), resize: vi.fn(), dispose: vi.fn() };
  const init = vi.fn(() => chart);
  return { chart, init };
});

vi.mock('echarts', () => ({ init: mocks.init }));

const spec = {
  xAxis: { type: 'time' },
  yAxis: { type: 'value' },
  series: [{ type: 'line', split: 'region', encode: { x: 'month', y: 'revenue' } }],
};
const rows = [
  { month: '2026-01-01', region: 'EMEA', revenue: 1 },
  { month: '2026-01-01', region: 'NA', revenue: 2 },
  { month: '2026-02-01', region: 'EMEA', revenue: 3 },
];
const columns = [
  { name: 'month', type: 'date' as const },
  { name: 'region', type: 'string' as const },
  { name: 'revenue', type: 'number' as const },
];

describe('buildOption', () => {
  it('injects the dataset and expands split series with filter transforms', () => {
    const out = buildOption(spec, rows, columns);
    expect(out.dataset).toEqual([
      { source: rows },
      { transform: { type: 'filter', config: { dimension: 'region', '=': 'EMEA' } } },
      { transform: { type: 'filter', config: { dimension: 'region', '=': 'NA' } } },
    ]);
    expect(out.series).toEqual([
      { type: 'line', encode: { x: 'month', y: 'revenue' }, name: 'EMEA', datasetIndex: 1 },
      { type: 'line', encode: { x: 'month', y: 'revenue' }, name: 'NA', datasetIndex: 2 },
    ]);
  });

  it('binds unsplit series to the raw dataset and rejects unknown split columns', () => {
    const out = buildOption({ series: { type: 'bar', encode: { x: 'region', y: 'revenue' } } }, rows, columns);
    expect(out.series).toEqual([{ type: 'bar', encode: { x: 'region', y: 'revenue' }, datasetIndex: 0 }]);
    expect(() => buildOption({ series: [{ type: 'bar', split: 'nope' }] }, rows, columns)).toThrow(/split/);
  });
});

describe('echarts adapter', () => {
  beforeEach(() => {
    mocks.init.mockClear();
    mocks.chart.setOption.mockClear();
    mocks.chart.dispose.mockClear();
  });

  it('inits on canvas, sets the sanitized option with data, updates and disposes', async () => {
    const el = document.createElement('div');
    const adapter = createAdapter();
    await adapter.mount(el, { ...spec, tooltip: { trigger: 'axis' } }, rows, columns);
    expect(mocks.init).toHaveBeenCalledWith(el, null, { renderer: 'canvas' });
    const first = mocks.chart.setOption.mock.calls[0][0] as Record<string, unknown>;
    expect((first.tooltip as Record<string, unknown>).renderMode).toBe('richText');
    expect((first.dataset as unknown[]).length).toBe(3);
    await adapter.update(rows.slice(0, 1));
    const second = mocks.chart.setOption.mock.calls[1][0] as Record<string, unknown>;
    expect((second.dataset as unknown[]).length).toBe(2);
    adapter.destroy();
    expect(mocks.chart.dispose).toHaveBeenCalledTimes(1);
  });

  it('refuses a hostile spec before init', async () => {
    const adapter = createAdapter();
    await expect(adapter.mount(document.createElement('div'), { ...spec, dataset: [] }, rows, columns)).rejects.toThrow(/dataset/);
    expect(mocks.init).not.toHaveBeenCalled();
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run from `web/`: `npm test -- src/renderers/echarts`
Expected: FAIL, unresolved imports.

- [ ] **Step 3: Implement**

`web/src/renderers/echartsSanitize.ts`:

```ts
// Spec 12.3, ECharts: richText tooltips everywhere, DOM-reaching keys removed,
// formatters must be HTML-free strings (never functions), no inline data,
// dataset injected by the adapter, canvas renderer. Pure.
import { SanitizeError, assertPlain, deepClone, isPlainObject, walk } from './common';

export const RULES: readonly string[] = [
  'spec must be a plain JSON object',
  'key "dataset" rejected at any depth (the adapter injects it)',
  'key "data" rejected at any depth (no inline data)',
  'keys link, sublink, graphic, extraCssText, appendTo, className deleted at any depth',
  'formatter must be a string (never a function)',
  'formatter must not contain "<"',
  'every tooltip gets renderMode richText; any other renderMode is overwritten',
  'series must be an object or an array of objects',
  'canvas renderer',
];

const DELETE_KEYS = new Set(['link', 'sublink', 'graphic', 'extraCssText', 'appendTo', 'className']);
const REJECT_KEYS = new Set(['dataset', 'data']);

export function sanitize(spec: unknown): Record<string, unknown> {
  assertPlain(spec);
  if (!isPlainObject(spec)) throw new SanitizeError('echarts spec must be an object');
  const clean = deepClone(spec);
  walk(clean, (obj, key, value, path) => {
    if (REJECT_KEYS.has(key)) throw new SanitizeError(`${path}: key "${key}" is not allowed`);
    if (DELETE_KEYS.has(key)) {
      delete obj[key];
      return;
    }
    if (key === 'formatter') {
      if (typeof value !== 'string') throw new SanitizeError(`${path}: formatter must be a string`);
      if (value.includes('<')) throw new SanitizeError(`${path}: formatter must not contain HTML`);
    }
    if (key === 'tooltip') {
      if (isPlainObject(value)) value.renderMode = 'richText';
      else obj[key] = { renderMode: 'richText' };
    }
    if (key === 'renderMode' && value !== 'richText') obj[key] = 'richText';
  });
  const series = clean.series;
  if (series !== undefined) {
    const list = Array.isArray(series) ? series : [series];
    list.forEach((s, i) => {
      if (!isPlainObject(s)) throw new SanitizeError(`spec/series/${i}: series must be an object`);
    });
    clean.series = list;
  }
  return clean;
}
```

`web/src/renderers/echarts.ts`:

```ts
import type { Column, Row } from '../api/types';
import type { Adapter } from './adapter';
import { SanitizeError, isPlainObject } from './common';
import { sanitize } from './echartsSanitize';

interface EChartsInstance {
  setOption(option: unknown, opts?: unknown): void;
  resize(): void;
  dispose(): void;
}

function distinct(rows: Row[], column: string): unknown[] {
  const seen = new Set<unknown>();
  const out: unknown[] = [];
  for (const row of rows) {
    const v = row[column];
    if (v === null || v === undefined || seen.has(v)) continue;
    seen.add(v);
    out.push(v);
  }
  return out;
}

/** Inject the dataset and expand `split` series. `clean` must come from sanitize(). */
export function buildOption(clean: Record<string, unknown>, rows: Row[], columns: Column[]): Record<string, unknown> {
  const declared = new Set(columns.map((c) => c.name));
  const dataset: unknown[] = [{ source: rows }];
  const input = Array.isArray(clean.series) ? clean.series : clean.series === undefined ? [] : [clean.series];
  const series: unknown[] = [];
  input.forEach((s, i) => {
    if (!isPlainObject(s)) throw new SanitizeError(`spec/series/${i}: series must be an object`);
    const { split, ...rest } = s;
    if (split === undefined) {
      series.push({ ...rest, datasetIndex: 0 });
      return;
    }
    if (typeof split !== 'string' || !declared.has(split)) {
      throw new SanitizeError(`spec/series/${i}/split: must name a declared column`);
    }
    for (const value of distinct(rows, split)) {
      dataset.push({ transform: { type: 'filter', config: { dimension: split, '=': value } } });
      series.push({ ...rest, name: String(value), datasetIndex: dataset.length - 1 });
    }
  });
  return { ...clean, dataset, series };
}

export function createAdapter(): Adapter {
  let chart: EChartsInstance | null = null;
  let clean: Record<string, unknown> | null = null;
  let columns: Column[] = [];
  let observer: ResizeObserver | null = null;

  return {
    async mount(el: HTMLElement, spec: unknown, rows: Row[], cols: Column[]): Promise<void> {
      clean = sanitize(spec);
      columns = cols;
      const echarts = await import('echarts');
      chart = echarts.init(el, null, { renderer: 'canvas' }) as unknown as EChartsInstance;
      chart.setOption(buildOption(clean, rows, columns), { notMerge: true });
      if (typeof ResizeObserver !== 'undefined') {
        observer = new ResizeObserver(() => chart?.resize());
        observer.observe(el);
      }
    },

    async update(rows: Row[]): Promise<void> {
      if (!chart || !clean) throw new Error('adapter is not mounted');
      chart.setOption(buildOption(clean, rows, columns), { notMerge: true });
    },

    destroy(): void {
      observer?.disconnect();
      observer = null;
      chart?.dispose();
      chart = null;
      clean = null;
    },
  };
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run from `web/`: `npm test -- src/renderers` then `npm run typecheck`
Expected: PASS, typecheck clean.

- [ ] **Step 5: Commit**

```bash
git add web/src/renderers/echartsSanitize.ts web/src/renderers/echartsSanitize.test.ts web/src/renderers/echarts.ts web/src/renderers/echarts.test.ts
git commit -m "feat(web): ECharts sanitizer and adapter with richText tooltips and split series" -m "Co-Authored-By: <model> <noreply@anthropic.com>
Claude-Session: <session url>"
```

---

### Task 9: Plotly column binding, sanitizer and adapter

**Files:**
- Create: `web/src/types/plotly.d.ts`, `web/src/renderers/plotlySanitize.ts`, `web/src/renderers/plotlySanitize.test.ts`, `web/src/renderers/plotlyBind.ts`, `web/src/renderers/plotlyBind.test.ts`, `web/src/renderers/plotly.ts`, `web/src/renderers/plotly.test.ts`

**Interfaces:**
- Consumes: `Adapter`; helpers from `common.ts`.
- Produces: `interface PlotlySpec { traces: Record<string, unknown>[]; layout: Record<string, unknown> }`, `sanitize(spec: unknown): PlotlySpec`, `RULES`, `BOUND_KEYS`, `FORBIDDEN_TRACE_TYPES` in `plotlySanitize.ts`; `bindTraces(traces: Record<string, unknown>[], rows: Row[], columns: Column[]): Record<string, unknown>[]` and `escapeLt(v: unknown): unknown` in `plotlyBind.ts`; `createAdapter(): Adapter` and `PLOTLY_CONFIG` in `plotly.ts`.

- [ ] **Step 1: Write the failing tests**

`web/src/renderers/plotlySanitize.test.ts`:

```ts
import { describe, expect, it } from 'vitest';
import { SanitizeError } from './common';
import { RULES, sanitize } from './plotlySanitize';

const base = {
  traces: [{ type: 'bar', x: { column: 'region' }, y: { column: 'orders' }, name: 'Orders' }],
  layout: { title: { text: 'Orders' }, barmode: 'group' },
};

describe('plotly sanitize', () => {
  it('accepts the binding shape and copies it', () => {
    const out = sanitize(base);
    expect(out).toEqual(base);
    expect(out.traces).not.toBe(base.traces);
    expect(sanitize({ traces: base.traces }).layout).toEqual({});
  });

  it('allows only traces and layout at the top level', () => {
    expect(() => sanitize({ ...base, frames: [] })).toThrow(/frames/);
    expect(() => sanitize({ layout: {} })).toThrow(/traces/);
    expect(() => sanitize({ traces: [] })).toThrow(/traces/);
    expect(() => sanitize({ traces: ['bar'] })).toThrow(/traces\/0/);
  });

  it('rejects geo and map trace types', () => {
    for (const type of ['scattergeo', 'choropleth', 'scattermapbox', 'choroplethmapbox', 'densitymapbox', 'scattermap', 'choroplethmap', 'densitymap']) {
      expect(() => sanitize({ traces: [{ type }] })).toThrow(/geo|map/);
    }
  });

  it('requires bound keys to be column bindings', () => {
    expect(() => sanitize({ traces: [{ type: 'bar', x: [1, 2] }] })).toThrow(/x/);
    expect(() => sanitize({ traces: [{ type: 'bar', x: { column: 'a', extra: 1 } }] })).toThrow(/x/);
    expect(() => sanitize({ traces: [{ type: 'bar', text: { column: 5 } }] })).toThrow(/text/);
    expect(() => sanitize({ traces: [{ type: 'bar', split: 3 }] })).toThrow(/split/);
  });

  it('strips images, mapbox, map and geo from the layout at any depth', () => {
    const out = sanitize({
      traces: base.traces,
      layout: { images: [{ source: 'https://x' }], mapbox: {}, map: {}, geo: {}, xaxis: { images: [] }, title: { text: 'ok' } },
    });
    expect(out.layout).toEqual({ xaxis: {}, title: { text: 'ok' } });
  });

  it('rejects non-plain values and prototype keys', () => {
    expect(() => sanitize({ traces: [{ type: 'bar', marker: { color: () => 1 } }] })).toThrow(SanitizeError);
    expect(sanitize(JSON.parse('{"traces":[{"type":"bar","__proto__":{"x":1}}]}')).traces[0]).toEqual({ type: 'bar' });
  });

  it('publishes its rule list', () => {
    expect(RULES.length).toBeGreaterThanOrEqual(6);
  });
});
```

`web/src/renderers/plotlyBind.test.ts`:

```ts
import { describe, expect, it } from 'vitest';
import { SanitizeError } from './common';
import { bindTraces, escapeLt } from './plotlyBind';

const rows = [
  { region: 'EMEA', orders: 1, label: '<b>x</b>' },
  { region: 'NA', orders: 2, label: 'y' },
  { region: 'EMEA', orders: 3, label: 'z' },
];
const columns = [
  { name: 'region', type: 'string' as const },
  { name: 'orders', type: 'integer' as const },
  { name: 'label', type: 'string' as const },
];

describe('bindTraces', () => {
  it('replaces bindings with column arrays and escapes text', () => {
    const out = bindTraces([{ type: 'bar', x: { column: 'region' }, y: { column: 'orders' }, text: { column: 'label' } }], rows, columns);
    expect(out).toEqual([{ type: 'bar', x: ['EMEA', 'NA', 'EMEA'], y: [1, 2, 3], text: ['&lt;b>x&lt;/b>', 'y', 'z'] }]);
  });

  it('expands split into one trace per value', () => {
    const out = bindTraces([{ type: 'scatter', split: 'region', x: { column: 'orders' }, y: { column: 'orders' } }], rows, columns);
    expect(out).toEqual([
      { type: 'scatter', name: 'EMEA', x: [1, 3], y: [1, 3] },
      { type: 'scatter', name: 'NA', x: [2], y: [2] },
    ]);
  });

  it('rejects undeclared columns for bindings and split', () => {
    expect(() => bindTraces([{ type: 'bar', x: { column: 'nope' } }], rows, columns)).toThrow(SanitizeError);
    expect(() => bindTraces([{ type: 'bar', split: 'nope' }], rows, columns)).toThrow(SanitizeError);
  });

  it('escapeLt only touches strings', () => {
    expect(escapeLt('<a>')).toBe('&lt;a>');
    expect(escapeLt(5)).toBe(5);
    expect(escapeLt(null)).toBeNull();
  });
});
```

`web/src/renderers/plotly.test.ts`:

```ts
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { PLOTLY_CONFIG, createAdapter } from './plotly';

const mocks = vi.hoisted(() => ({
  newPlot: vi.fn(async () => undefined),
  react: vi.fn(async () => undefined),
  purge: vi.fn(),
}));

vi.mock('plotly.js-dist-min', () => ({ default: { newPlot: mocks.newPlot, react: mocks.react, purge: mocks.purge } }));

const spec = { traces: [{ type: 'bar', x: { column: 'region' }, y: { column: 'orders' } }], layout: { barmode: 'group' } };
const rows = [
  { region: 'EMEA', orders: 1 },
  { region: 'NA', orders: 2 },
];
const columns = [
  { name: 'region', type: 'string' as const },
  { name: 'orders', type: 'integer' as const },
];

describe('plotly adapter', () => {
  beforeEach(() => {
    mocks.newPlot.mockClear();
    mocks.react.mockClear();
    mocks.purge.mockClear();
  });

  it('config keeps the cloud and editor off', () => {
    expect(PLOTLY_CONFIG).toMatchObject({
      displaylogo: false,
      showSendToCloud: false,
      showEditInChartStudio: false,
      responsive: true,
    });
    expect(PLOTLY_CONFIG.modeBarButtonsToRemove).toEqual(expect.arrayContaining(['sendDataToCloud', 'editInChartStudio']));
  });

  it('mounts with bound traces, updates with react, purges on destroy', async () => {
    const el = document.createElement('div');
    const adapter = createAdapter();
    await adapter.mount(el, spec, rows, columns);
    expect(mocks.newPlot).toHaveBeenCalledTimes(1);
    const [target, traces, layout, config] = mocks.newPlot.mock.calls[0] as unknown as [HTMLElement, unknown[], Record<string, unknown>, unknown];
    expect(target).toBe(el);
    expect(traces).toEqual([{ type: 'bar', x: ['EMEA', 'NA'], y: [1, 2] }]);
    expect(layout).toMatchObject({ barmode: 'group', autosize: true });
    expect(config).toBe(PLOTLY_CONFIG);
    await adapter.update(rows.slice(1));
    expect(mocks.react).toHaveBeenCalledTimes(1);
    expect((mocks.react.mock.calls[0] as unknown as [HTMLElement, unknown[]])[1]).toEqual([{ type: 'bar', x: ['NA'], y: [2] }]);
    adapter.destroy();
    expect(mocks.purge).toHaveBeenCalledWith(el);
  });

  it('refuses a hostile spec before loading the library', async () => {
    const adapter = createAdapter();
    await expect(adapter.mount(document.createElement('div'), { traces: [{ type: 'choropleth' }] }, rows, columns)).rejects.toThrow(/geo|map/);
    expect(mocks.newPlot).not.toHaveBeenCalled();
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run from `web/`: `npm test -- src/renderers/plotly`
Expected: FAIL, unresolved imports.

- [ ] **Step 3: Implement**

`web/src/types/plotly.d.ts`:

```ts
declare module 'plotly.js-dist-min' {
  interface PlotlyStatic {
    newPlot(el: HTMLElement, data: unknown[], layout?: unknown, config?: unknown): Promise<unknown>;
    react(el: HTMLElement, data: unknown[], layout?: unknown, config?: unknown): Promise<unknown>;
    purge(el: HTMLElement): void;
  }
  const Plotly: PlotlyStatic;
  export default Plotly;
}
```

`web/src/renderers/plotlySanitize.ts`:

```ts
// Spec 12.3, Plotly: cloud/editor off (adapter config), geo and map traces
// rejected, layout.images and map layouts deleted, "<" escaped in bound text,
// column binding as a strict walk. Mirrors _check_plotly in viz/schemas.py.
import { SanitizeError, assertPlain, deepClone, isPlainObject, walk } from './common';

export const RULES: readonly string[] = [
  'spec must be a plain object with only "traces" and "layout"',
  'traces must be a non-empty array of plain objects',
  'trace types scattergeo, choropleth, scattermapbox, choroplethmapbox, densitymapbox, scattermap, choroplethmap, densitymap rejected',
  'x, y, z, text, hovertext, labels, values, customdata must be {"column": name} bindings',
  'split, when present, must be a string',
  'layout keys images, mapbox, map, geo deleted at any depth',
  'keys __proto__, constructor, prototype dropped',
  '"<" escaped in every string bound to text or hovertext',
  'cloud export, chart studio and the Plotly logo disabled in config',
];

export const BOUND_KEYS = ['x', 'y', 'z', 'text', 'hovertext', 'labels', 'values', 'customdata'] as const;

export const FORBIDDEN_TRACE_TYPES = new Set([
  'scattergeo',
  'choropleth',
  'scattermapbox',
  'choroplethmapbox',
  'densitymapbox',
  'scattermap',
  'choroplethmap',
  'densitymap',
]);

const LAYOUT_DELETE_KEYS = new Set(['images', 'mapbox', 'map', 'geo']);

export interface PlotlySpec {
  traces: Record<string, unknown>[];
  layout: Record<string, unknown>;
}

export function sanitize(spec: unknown): PlotlySpec {
  assertPlain(spec);
  if (!isPlainObject(spec)) throw new SanitizeError('plotly spec must be an object');
  for (const key of Object.keys(spec)) {
    if (key !== 'traces' && key !== 'layout') throw new SanitizeError(`spec/${key}: plotly spec allows only traces and layout`);
  }
  const clean = deepClone(spec);
  const traces = clean.traces;
  if (!Array.isArray(traces) || traces.length === 0) throw new SanitizeError('spec/traces: must be a non-empty array');
  traces.forEach((trace, i) => {
    if (!isPlainObject(trace)) throw new SanitizeError(`spec/traces/${i}: must be an object`);
    if (typeof trace.type === 'string' && FORBIDDEN_TRACE_TYPES.has(trace.type)) {
      throw new SanitizeError(`spec/traces/${i}/type: geo and map traces are not allowed`);
    }
    for (const key of BOUND_KEYS) {
      if (!(key in trace)) continue;
      const binding = trace[key];
      if (!isPlainObject(binding) || Object.keys(binding).length !== 1 || typeof binding.column !== 'string') {
        throw new SanitizeError(`spec/traces/${i}/${key}: must be a column binding {"column": name}`);
      }
    }
    if ('split' in trace && typeof trace.split !== 'string') throw new SanitizeError(`spec/traces/${i}/split: must be a column name`);
  });
  let layout: Record<string, unknown> = {};
  if (clean.layout !== undefined) {
    if (!isPlainObject(clean.layout)) throw new SanitizeError('spec/layout: must be an object');
    layout = clean.layout;
    walk(layout, (obj, key) => {
      if (LAYOUT_DELETE_KEYS.has(key)) delete obj[key];
    }, 'spec/layout');
  }
  return { traces: traces as Record<string, unknown>[], layout };
}
```

`web/src/renderers/plotlyBind.ts`:

```ts
import type { Column, Row } from '../api/types';
import { SanitizeError, UNSAFE_KEYS, isPlainObject } from './common';
import { BOUND_KEYS } from './plotlySanitize';

const ESCAPED_KEYS = new Set(['text', 'hovertext']);

export function escapeLt(v: unknown): unknown {
  return typeof v === 'string' ? v.replace(/</g, '&lt;') : v;
}

function columnArray(rows: Row[], column: string, escape: boolean): unknown[] {
  return rows.map((row) => (escape ? escapeLt(row[column]) : row[column]));
}

function bindOne(trace: Record<string, unknown>, rows: Row[], declared: Set<string>, index: number): Record<string, unknown> {
  const out: Record<string, unknown> = {};
  for (const key of Object.keys(trace)) {
    if (UNSAFE_KEYS.includes(key) || key === 'split') continue;
    const value = trace[key];
    if ((BOUND_KEYS as readonly string[]).includes(key)) {
      if (!isPlainObject(value) || typeof value.column !== 'string') {
        throw new SanitizeError(`spec/traces/${index}/${key}: must be a column binding`);
      }
      if (!declared.has(value.column)) throw new SanitizeError(`spec/traces/${index}/${key}: unknown column "${value.column}"`);
      out[key] = columnArray(rows, value.column, ESCAPED_KEYS.has(key));
    } else {
      out[key] = value;
    }
  }
  return out;
}

/** Replace {column} bindings with arrays from rows and expand `split` traces. */
export function bindTraces(traces: Record<string, unknown>[], rows: Row[], columns: Column[]): Record<string, unknown>[] {
  const declared = new Set(columns.map((c) => c.name));
  const out: Record<string, unknown>[] = [];
  traces.forEach((trace, i) => {
    const split = trace.split;
    if (split === undefined) {
      out.push(bindOne(trace, rows, declared, i));
      return;
    }
    if (typeof split !== 'string' || !declared.has(split)) throw new SanitizeError(`spec/traces/${i}/split: must name a declared column`);
    const groups = new Map<string, Row[]>();
    for (const row of rows) {
      const v = row[split];
      if (v === null || v === undefined) continue;
      const key = String(v);
      const group = groups.get(key);
      if (group) group.push(row);
      else groups.set(key, [row]);
    }
    for (const [name, group] of groups) {
      const bound = bindOne(trace, group, declared, i);
      out.push({ ...bound, name });
    }
  });
  return out;
}
```

`web/src/renderers/plotly.ts`:

```ts
import type { Column, Row } from '../api/types';
import type { Adapter } from './adapter';
import { bindTraces } from './plotlyBind';
import { sanitize, type PlotlySpec } from './plotlySanitize';

export const PLOTLY_CONFIG = {
  displaylogo: false,
  showSendToCloud: false,
  showEditInChartStudio: false,
  modeBarButtonsToRemove: ['sendDataToCloud', 'editInChartStudio'],
  responsive: true,
};

type PlotlyModule = typeof import('plotly.js-dist-min').default;

export function createAdapter(): Adapter {
  let el: HTMLElement | null = null;
  let plotly: PlotlyModule | null = null;
  let clean: PlotlySpec | null = null;
  let columns: Column[] = [];

  function layoutFor(spec: PlotlySpec): Record<string, unknown> {
    return { autosize: true, margin: { l: 48, r: 16, t: 32, b: 40 }, ...spec.layout };
  }

  return {
    async mount(target: HTMLElement, spec: unknown, rows: Row[], cols: Column[]): Promise<void> {
      clean = sanitize(spec);
      columns = cols;
      const traces = bindTraces(clean.traces, rows, columns);
      plotly = (await import('plotly.js-dist-min')).default;
      el = target;
      await plotly.newPlot(el, traces, layoutFor(clean), PLOTLY_CONFIG);
    },

    async update(rows: Row[]): Promise<void> {
      if (!el || !clean || !plotly) throw new Error('adapter is not mounted');
      const traces = bindTraces(clean.traces, rows, columns);
      await plotly.react(el, traces, layoutFor(clean), PLOTLY_CONFIG);
    },

    destroy(): void {
      if (el && plotly) plotly.purge(el);
      el = null;
      plotly = null;
      clean = null;
    },
  };
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run from `web/`: `npm test -- src/renderers` then `npm run typecheck`
Expected: PASS, typecheck clean.

- [ ] **Step 5: Commit**

```bash
git add web/src/types/plotly.d.ts web/src/renderers/plotlySanitize.ts web/src/renderers/plotlySanitize.test.ts web/src/renderers/plotlyBind.ts web/src/renderers/plotlyBind.test.ts web/src/renderers/plotly.ts web/src/renderers/plotly.test.ts
git commit -m "feat(web): Plotly column binding, sanitizer and adapter with cloud features off" -m "Co-Authored-By: <model> <noreply@anthropic.com>
Claude-Session: <session url>"
```

---

### Task 10: Renderer registry, error card and the chart tile

**Files:**
- Create: `web/src/renderers/index.ts`, `web/src/renderers/index.test.ts`, `web/src/components/ErrorCard.tsx`, `web/src/components/ChartTile.tsx`, `web/src/components/ChartTile.test.tsx`

**Interfaces:**
- Consumes: `createAdapter` from the three adapter files; `sanitize` and `RULES` from the three sanitizer files; `fetchChart`, `fetchRows`, `ApiError`, `DataTooLarge` from `web/src/api/client.ts`; `applyFilters`, `filterKey`, `Filter` from `web/src/data/filters.ts`; `StatTile`.
- Produces in `renderers/index.ts`: `getAdapter(renderer: string): Adapter` (throws `SanitizeError` for unknown renderers, including `stat`), `sanitizeSpec(renderer: string, spec: unknown): unknown`, `RULE_COUNTS: Record<'vega-lite' | 'echarts' | 'plotly', number>`.
- Produces in `ErrorCard.tsx`: `ErrorCard({ id, reason }: { id: string; reason: string })` rendering `role="alert"`, the id in `.error-id`, the reason text.
- Produces in `ChartTile.tsx`: `ChartTile({ chartId, filters, onRows?, showTitle? }: ChartTileProps)` and `describeError(err: unknown): string`. The tile root has `data-tile="<id>"`, `data-state="loading" | "ready" | "error"` (`ready` only after the adapter's `mount`/`update` resolved, or the stat tile rendered) and `data-rows="<filtered row count>"`. `onRows(chartId, rows)` is called once with the unfiltered small-lane rows so the dashboard can derive select options. Large-lane charts show an error card in this task; Task 14 wires DuckDB in.

- [ ] **Step 1: Write the failing tests**

`web/src/renderers/index.test.ts`:

```ts
import { describe, expect, it } from 'vitest';
import { SanitizeError } from './common';
import { RULE_COUNTS, getAdapter, sanitizeSpec } from './index';

describe('registry', () => {
  it('returns a fresh adapter per call for each renderer', () => {
    for (const r of ['vega-lite', 'plotly', 'echarts']) {
      const a = getAdapter(r);
      expect(typeof a.mount).toBe('function');
      expect(getAdapter(r)).not.toBe(a);
    }
  });
  it('rejects unknown renderers and stat', () => {
    expect(() => getAdapter('stat')).toThrow(SanitizeError);
    expect(() => getAdapter('d3')).toThrow(SanitizeError);
    expect(() => getAdapter('__proto__')).toThrow(SanitizeError);
    expect(() => sanitizeSpec('toString', {})).toThrow(SanitizeError);
  });
  it('sanitizes per renderer and counts rules', () => {
    expect(sanitizeSpec('vega-lite', { data: { name: 'data' }, mark: 'bar' })).toEqual({ data: { name: 'data' }, mark: 'bar' });
    expect(RULE_COUNTS['vega-lite']).toBeGreaterThan(0);
    expect(RULE_COUNTS.plotly).toBeGreaterThan(0);
    expect(RULE_COUNTS.echarts).toBeGreaterThan(0);
  });
});
```

`web/src/components/ChartTile.test.tsx`:

```tsx
import { render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { ApiError } from '../api/client';
import type { Chart } from '../api/types';
import { SanitizeError } from '../renderers/common';
import { ChartTile, describeError } from './ChartTile';

const mocks = vi.hoisted(() => ({
  fetchChart: vi.fn(),
  fetchRows: vi.fn(),
  adapter: { mount: vi.fn(async () => undefined), update: vi.fn(async () => undefined), destroy: vi.fn() },
  getAdapter: vi.fn(),
}));

vi.mock('../api/client', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../api/client')>()),
  fetchChart: mocks.fetchChart,
  fetchRows: mocks.fetchRows,
}));
vi.mock('../renderers', () => ({ getAdapter: mocks.getAdapter }));

const chart: Chart = {
  schema_version: 1,
  id: 'sales/x',
  title: 'Revenue',
  renderer: 'vega-lite',
  spec: { data: { name: 'data' }, mark: 'line' },
  data: {
    format: 'json',
    lane: 'small',
    rows: 2,
    bytes: 10,
    columns: [
      { name: 'region', type: 'string' },
      { name: 'revenue', type: 'number' },
    ],
  },
  aggregate: null,
};
const rows = [
  { region: 'EMEA', revenue: 1 },
  { region: 'NA', revenue: 2 },
];

beforeEach(() => {
  mocks.fetchChart.mockReset();
  mocks.fetchRows.mockReset();
  mocks.adapter.mount.mockClear();
  mocks.adapter.update.mockClear();
  mocks.adapter.destroy.mockClear();
  mocks.getAdapter.mockReset().mockReturnValue(mocks.adapter);
});

function tile(id = 'sales/x') {
  return document.querySelector(`[data-tile="${id}"]`) as HTMLElement;
}

describe('ChartTile', () => {
  it('loads, mounts with filtered rows, reports rows, and updates on filter change', async () => {
    mocks.fetchChart.mockResolvedValue(chart);
    mocks.fetchRows.mockResolvedValue(rows);
    const onRows = vi.fn();
    const { rerender } = render(<ChartTile chartId="sales/x" filters={[]} onRows={onRows} />);
    await waitFor(() => expect(tile().dataset.state).toBe('ready'));
    expect(screen.getByRole('heading', { name: 'Revenue' })).toBeInTheDocument();
    expect(mocks.adapter.mount).toHaveBeenCalledTimes(1);
    expect(mocks.adapter.mount.mock.calls[0][2]).toEqual(rows);
    expect(onRows).toHaveBeenCalledWith('sales/x', rows);
    expect(tile().dataset.rows).toBe('2');

    rerender(<ChartTile chartId="sales/x" filters={[{ controlId: 'r', column: 'region', value: { type: 'select', values: ['NA'] } }]} onRows={onRows} />);
    await waitFor(() => expect(mocks.adapter.update).toHaveBeenCalledTimes(1));
    expect(mocks.adapter.update.mock.calls[0][0]).toEqual([rows[1]]);
    await waitFor(() => expect(tile().dataset.rows).toBe('1'));
    expect(mocks.adapter.mount).toHaveBeenCalledTimes(1);
  });

  it('shows an error card with the id for a missing chart', async () => {
    mocks.fetchChart.mockRejectedValue(new ApiError(404, 'not found'));
    render(<ChartTile chartId="sales/nope" filters={[]} />);
    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent('sales/nope');
    expect(alert).toHaveTextContent('not found');
    expect(tile('sales/nope').dataset.state).toBe('error');
  });

  it('lists schema errors for an invalid chart', async () => {
    mocks.fetchChart.mockRejectedValue(new ApiError(422, { errors: ['title: required', 'spec/x: bad'] }));
    render(<ChartTile chartId="sales/x" filters={[]} />);
    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent('title: required');
    expect(alert).toHaveTextContent('spec/x: bad');
  });

  it('turns a sanitizer rejection into an error card', async () => {
    mocks.fetchChart.mockResolvedValue(chart);
    mocks.fetchRows.mockResolvedValue(rows);
    mocks.adapter.mount.mockRejectedValueOnce(new SanitizeError('spec/data: bad'));
    render(<ChartTile chartId="sales/x" filters={[]} />);
    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent('spec rejected: spec/data: bad');
  });

  it('renders stat tiles without an adapter and isolates a bad stat spec', async () => {
    mocks.fetchChart.mockResolvedValue({ ...chart, renderer: 'stat', spec: { value: 'revenue', agg: 'sum' } });
    mocks.fetchRows.mockResolvedValue(rows);
    render(<ChartTile chartId="sales/x" filters={[]} />);
    await waitFor(() => expect(tile().dataset.state).toBe('ready'));
    expect(screen.getByTestId('stat-value')).toHaveTextContent('3');
    expect(mocks.getAdapter).not.toHaveBeenCalled();

    mocks.fetchChart.mockResolvedValue({ ...chart, id: 'sales/bad', renderer: 'stat', spec: { value: 'nope', agg: 'sum' } });
    render(<ChartTile chartId="sales/bad" filters={[]} />);
    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent('sales/bad');
    expect(alert).toHaveTextContent('spec rejected');
  });

  it('shows an error card for the large lane until Task 14', async () => {
    mocks.fetchChart.mockResolvedValue({ ...chart, data: { ...chart.data, lane: 'large', format: 'parquet' }, aggregate: 'SELECT 1' });
    render(<ChartTile chartId="sales/x" filters={[]} />);
    expect(await screen.findByRole('alert')).toHaveTextContent('large lane');
  });

  it('destroys the adapter on unmount', async () => {
    mocks.fetchChart.mockResolvedValue(chart);
    mocks.fetchRows.mockResolvedValue(rows);
    const { unmount } = render(<ChartTile chartId="sales/x" filters={[]} />);
    await waitFor(() => expect(tile().dataset.state).toBe('ready'));
    unmount();
    expect(mocks.adapter.destroy).toHaveBeenCalled();
  });
});

describe('describeError', () => {
  it('maps every failure kind to a sentence', () => {
    expect(describeError(new ApiError(404, 'x'))).toBe('not found');
    expect(describeError(new ApiError(413, 'x'))).toBe('document too large');
    expect(describeError(new ApiError(500, 'x'))).toBe('request failed (500)');
    expect(describeError(new SanitizeError('k'))).toBe('spec rejected: k');
    const duck = new Error('boom');
    duck.name = 'DuckDbError';
    expect(describeError(duck)).toBe('query failed: boom');
    expect(describeError('?')).toBe('render failed: ?');
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run from `web/`: `npm test -- src/renderers/index src/components/ChartTile`
Expected: FAIL, unresolved imports.

- [ ] **Step 3: Implement the registry**

`web/src/renderers/index.ts`:

```ts
import type { Adapter } from './adapter';
import { SanitizeError } from './common';
import { createAdapter as createEcharts } from './echarts';
import { RULES as ECHARTS_RULES, sanitize as sanitizeEcharts } from './echartsSanitize';
import { createAdapter as createPlotly } from './plotly';
import { RULES as PLOTLY_RULES, sanitize as sanitizePlotly } from './plotlySanitize';
import { createAdapter as createVegaLite } from './vegaLite';
import { RULES as VEGA_RULES, sanitize as sanitizeVegaLite } from './vegaLiteSanitize';

const ADAPTERS: Record<string, () => Adapter> = {
  'vega-lite': createVegaLite,
  plotly: createPlotly,
  echarts: createEcharts,
};

const SANITIZERS: Record<string, (spec: unknown) => unknown> = {
  'vega-lite': sanitizeVegaLite,
  plotly: sanitizePlotly,
  echarts: sanitizeEcharts,
};

export const RULE_COUNTS = {
  'vega-lite': VEGA_RULES.length,
  plotly: PLOTLY_RULES.length,
  echarts: ECHARTS_RULES.length,
};

function own<T>(table: Record<string, T>, key: string): T | undefined {
  return Object.prototype.hasOwnProperty.call(table, key) ? table[key] : undefined;
}

export function getAdapter(renderer: string): Adapter {
  const factory = own(ADAPTERS, renderer);
  if (!factory) throw new SanitizeError(`unknown renderer: ${renderer}`);
  return factory();
}

export function sanitizeSpec(renderer: string, spec: unknown): unknown {
  const sanitize = own(SANITIZERS, renderer);
  if (!sanitize) throw new SanitizeError(`unknown renderer: ${renderer}`);
  return sanitize(spec);
}
```

- [ ] **Step 4: Implement the error card and the tile**

`web/src/components/ErrorCard.tsx`:

```tsx
export function ErrorCard({ id, reason }: { id: string; reason: string }) {
  return (
    <div className="error-card" role="alert">
      <div className="error-id">{id}</div>
      <div>{reason}</div>
    </div>
  );
}
```

`web/src/components/ChartTile.tsx`:

```tsx
import { Component, useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import { ApiError, DataTooLarge, fetchChart, fetchRows } from '../api/client';
import type { Chart, Row } from '../api/types';
import { applyFilters, filterKey, type Filter } from '../data/filters';
import { getAdapter } from '../renderers';
import type { Adapter } from '../renderers/adapter';
import { SanitizeError, isPlainObject } from '../renderers/common';
import { ErrorCard } from './ErrorCard';
import { StatTile } from './StatTile';

export interface ChartTileProps {
  chartId: string;
  filters: Filter[];
  onRows?: (chartId: string, rows: Row[]) => void;
  showTitle?: boolean;
}

export function describeError(err: unknown): string {
  if (err instanceof ApiError) {
    if (err.status === 404) return 'not found';
    if (err.status === 413) return 'document too large';
    if (err.status === 422) {
      const detail = err.detail;
      const errors = isPlainObject(detail) && Array.isArray(detail.errors) ? detail.errors : [detail];
      return `invalid document: ${errors.map((e) => (typeof e === 'string' ? e : JSON.stringify(e))).join('; ')}`;
    }
    return `request failed (${err.status})`;
  }
  if (err instanceof DataTooLarge) return err.message;
  if (err instanceof SanitizeError) return `spec rejected: ${err.message}`;
  if (err instanceof Error && err.name === 'DuckDbError') return `query failed: ${err.message}`;
  if (err instanceof Error) return `render failed: ${err.message}`;
  return `render failed: ${String(err)}`;
}

class TileErrorBoundary extends Component<{ id: string; children: ReactNode }, { error: string | null }> {
  state = { error: null as string | null };

  static getDerivedStateFromError(err: unknown) {
    return { error: describeError(err) };
  }

  render() {
    if (this.state.error) return <ErrorCard id={this.props.id} reason={this.state.error} />;
    return this.props.children;
  }
}

export function ChartTile({ chartId, filters, onRows, showTitle = true }: ChartTileProps) {
  const [chart, setChart] = useState<Chart | null>(null);
  const [rows, setRows] = useState<Row[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [rendered, setRendered] = useState(false);
  const mountRef = useRef<HTMLDivElement>(null);
  const adapterRef = useRef<Adapter | null>(null);
  const queueRef = useRef<Promise<void>>(Promise.resolve());
  const onRowsRef = useRef(onRows);
  onRowsRef.current = onRows;
  const key = filterKey(filters);

  // Load the chart document and its small-lane rows.
  useEffect(() => {
    let cancelled = false;
    setChart(null);
    setRows(null);
    setError(null);
    setRendered(false);
    (async () => {
      try {
        const doc = await fetchChart(chartId);
        if (doc.data.lane === 'large') throw new Error('large lane is not supported yet');
        const data = await fetchRows(chartId);
        if (cancelled) return;
        setChart(doc);
        setRows(data);
        onRowsRef.current?.(chartId, data);
      } catch (err) {
        if (!cancelled) setError(describeError(err));
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [chartId]);

  // eslint-disable-next-line react-hooks/exhaustive-deps -- `key` stands in for `filters`
  const filtered = useMemo(() => (chart && rows ? applyFilters(rows, chart.data.columns, filters) : null), [chart, rows, key]);

  // Mount once, then update on every filter change. Operations are serialized.
  useEffect(() => {
    if (!chart || !filtered || error) return;
    if (chart.renderer === 'stat') {
      setRendered(true);
      return;
    }
    const el = mountRef.current;
    if (!el) return;
    let cancelled = false;
    queueRef.current = queueRef.current
      .then(async () => {
        if (cancelled) return;
        if (!adapterRef.current) {
          const adapter = getAdapter(chart.renderer);
          await adapter.mount(el, chart.spec, filtered, chart.data.columns);
          adapterRef.current = adapter;
        } else {
          await adapterRef.current.update(filtered);
        }
        if (!cancelled) setRendered(true);
      })
      .catch((err) => {
        if (!cancelled) setError(describeError(err));
      });
    return () => {
      cancelled = true;
    };
  }, [chart, filtered, error]);

  // Tear the adapter down when the tile goes away or changes chart.
  useEffect(
    () => () => {
      adapterRef.current?.destroy();
      adapterRef.current = null;
    },
    [chartId],
  );

  const state = error ? 'error' : rendered ? 'ready' : 'loading';
  const columnNames = chart ? chart.data.columns.map((c) => c.name) : [];

  return (
    <div className="tile" data-tile={chartId} data-state={state} data-rows={filtered ? filtered.length : 0}>
      {showTitle && <h3 className="tile-title">{chart?.title ?? chartId}</h3>}
      <div className="tile-body">
        {error ? (
          <ErrorCard id={chartId} reason={error} />
        ) : chart && filtered && chart.renderer === 'stat' ? (
          <TileErrorBoundary id={chartId}>
            <StatTile spec={chart.spec} rows={filtered} columns={columnNames} />
          </TileErrorBoundary>
        ) : (
          <div className="tile-mount" ref={mountRef} />
        )}
        {!error && !rendered && <div className="muted tile-loading">Loading…</div>}
      </div>
    </div>
  );
}
```

- [ ] **Step 5: Run tests to verify they pass**

Run from `web/`: `npm test` then `npm run typecheck`
Expected: PASS (all), typecheck clean. React logs the boundary-caught error to the console in the stat test; that is expected output, not a failure.

- [ ] **Step 6: Commit**

```bash
git add web/src/renderers/index.ts web/src/renderers/index.test.ts web/src/components/ErrorCard.tsx web/src/components/ChartTile.tsx web/src/components/ChartTile.test.tsx
git commit -m "feat(web): renderer registry, error card and isolated chart tile" -m "Co-Authored-By: <model> <noreply@anthropic.com>
Claude-Session: <session url>"
```

---

### Task 11: Routing and the two tree pages

**Files:**
- Create: `web/src/pages/TreePage.tsx`, `web/src/pages/TreePage.test.tsx`
- Modify: `web/src/App.tsx`, `web/src/App.test.tsx`

**Interfaces:**
- Consumes: `fetchTree`, `Tree`, `TreeFolder`, `TreeItem`; `Markdown`; `ErrorCard`.
- Produces: `TreePage({ kind }: { kind: 'charts' | 'dashboards' })`; routes `/` (dashboards tree) and `/charts` (charts library) in `App`. Items link to `/d/<id>` and `/c/<id>`. Folders show `title ?? name`, their description through `Markdown`, and their `error` when present. Items with `error` render as text with the error, not as links. Static charts get a `static` badge.

- [ ] **Step 1: Write the failing tests**

Replace `web/src/App.test.tsx`:

```tsx
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';
import App from './App';

vi.mock('./api/client', async (importOriginal) => ({
  ...(await importOriginal<typeof import('./api/client')>()),
  fetchTree: vi.fn(async () => ({
    charts: { type: 'folder', path: '', name: '', title: null, description: null, order: null, error: null, folders: [], items: [] },
    dashboards: { type: 'folder', path: '', name: '', title: null, description: null, order: null, error: null, folders: [], items: [] },
    built_at: 'x',
  })),
}));

describe('App', () => {
  it('renders the site name and the navigation', () => {
    render(
      <MemoryRouter initialEntries={['/']}>
        <App />
      </MemoryRouter>,
    );
    expect(screen.getByRole('heading', { name: 'viz-site' })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Dashboards' })).toHaveAttribute('href', '/');
    expect(screen.getByRole('link', { name: 'Charts' })).toHaveAttribute('href', '/charts');
  });
});
```

`web/src/pages/TreePage.test.tsx`:

```tsx
import { render, screen } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { Tree } from '../api/types';
import { TreePage } from './TreePage';

const mocks = vi.hoisted(() => ({ fetchTree: vi.fn() }));
vi.mock('../api/client', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../api/client')>()),
  fetchTree: mocks.fetchTree,
}));

const tree: Tree = {
  built_at: 'x',
  charts: {
    type: 'folder', path: '', name: '', title: null, description: null, order: null, error: null,
    folders: [
      {
        type: 'folder', path: 'sales', name: 'sales', title: 'Sales', description: 'Sample **sales** charts.', order: 10, error: null, folders: [],
        items: [
          { type: 'chart', id: 'sales/revenue', title: 'Revenue', renderer: 'vega-lite', lane: 'small', static: false },
          { type: 'chart', id: 'sales/total', title: 'Total', renderer: 'stat', lane: 'small', static: true },
          { type: 'chart', id: 'sales/broken', error: 'title: required' },
        ],
      },
    ],
    items: [],
  },
  dashboards: {
    type: 'folder', path: '', name: '', title: null, description: null, order: null, error: null,
    folders: [
      {
        type: 'folder', path: 'sales', name: 'sales', title: null, description: null, order: null, error: 'schema_version: bad', folders: [],
        items: [{ type: 'dashboard', id: 'sales/overview', title: 'Sales overview' }],
      },
    ],
    items: [],
  },
};

beforeEach(() => mocks.fetchTree.mockReset());

function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/" element={<TreePage kind="dashboards" />} />
        <Route path="/charts" element={<TreePage kind="charts" />} />
      </Routes>
    </MemoryRouter>,
  );
}

describe('TreePage', () => {
  it('renders dashboards with folder slug fallback and folder errors', async () => {
    mocks.fetchTree.mockResolvedValue(tree);
    renderAt('/');
    expect(await screen.findByRole('link', { name: 'Sales overview' })).toHaveAttribute('href', '/d/sales/overview');
    expect(screen.getByText('sales')).toBeInTheDocument();
    expect(screen.getByText(/schema_version: bad/)).toBeInTheDocument();
  });

  it('renders charts with titles, markdown descriptions, static badges and item errors', async () => {
    mocks.fetchTree.mockResolvedValue(tree);
    renderAt('/charts');
    expect(await screen.findByRole('link', { name: 'Revenue' })).toHaveAttribute('href', '/c/sales/revenue');
    expect(screen.getByText('Sales')).toBeInTheDocument();
    expect(screen.getByText('sales').tagName).toBe('STRONG');
    expect(screen.getByText('static')).toBeInTheDocument();
    expect(screen.getByText(/sales\/broken/)).toHaveTextContent('title: required');
    expect(screen.queryByRole('link', { name: /broken/ })).toBeNull();
  });

  it('shows an error card when the tree fails', async () => {
    mocks.fetchTree.mockRejectedValue(new Error('offline'));
    renderAt('/');
    expect(await screen.findByRole('alert')).toHaveTextContent('offline');
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run from `web/`: `npm test -- src/App src/pages`
Expected: FAIL (`./pages/TreePage` unresolved; App has no links).

- [ ] **Step 3: Implement**

`web/src/pages/TreePage.tsx`:

```tsx
import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { fetchTree } from '../api/client';
import type { Tree, TreeFolder, TreeItem } from '../api/types';
import { ErrorCard } from '../components/ErrorCard';
import { Markdown } from '../components/Markdown';

type Kind = 'charts' | 'dashboards';

function itemHref(kind: Kind, item: TreeItem): string {
  return kind === 'charts' ? `/c/${item.id}` : `/d/${item.id}`;
}

function Item({ kind, item }: { kind: Kind; item: TreeItem }) {
  if (item.error) {
    return (
      <span className="item-error">
        {item.id}: {item.error}
      </span>
    );
  }
  return (
    <>
      <Link to={itemHref(kind, item)}>{item.title ?? item.id}</Link>
      {item.type === 'chart' && item.static && <span className="badge">static</span>}
    </>
  );
}

function Folder({ kind, folder, root }: { kind: Kind; folder: TreeFolder; root: boolean }) {
  return (
    <div>
      {!root && (
        <div className="folder-title">
          {folder.title ?? folder.name}
          {folder.error && <span className="item-error"> ({folder.error})</span>}
        </div>
      )}
      {!root && folder.description && <Markdown text={folder.description} />}
      <ul>
        {folder.items.map((item) => (
          <li key={item.id}>
            <Item kind={kind} item={item} />
          </li>
        ))}
        {folder.folders.map((child) => (
          <li key={child.path}>
            <Folder kind={kind} folder={child} root={false} />
          </li>
        ))}
      </ul>
    </div>
  );
}

export function TreePage({ kind }: { kind: Kind }) {
  const [tree, setTree] = useState<Tree | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setTree(null);
    setError(null);
    fetchTree()
      .then((t) => {
        if (!cancelled) setTree(t);
      })
      .catch((err: unknown) => {
        if (!cancelled) setError(err instanceof Error ? err.message : String(err));
      });
    return () => {
      cancelled = true;
    };
  }, [kind]);

  return (
    <div className="tree">
      <h2>{kind === 'charts' ? 'Charts' : 'Dashboards'}</h2>
      {error && <ErrorCard id={kind} reason={error} />}
      {!error && !tree && <div className="muted">Loading…</div>}
      {tree && <Folder kind={kind} folder={tree[kind]} root />}
    </div>
  );
}
```

Replace `web/src/App.tsx`:

```tsx
import { Link, Route, Routes } from 'react-router-dom';
import { TreePage } from './pages/TreePage';

export default function App() {
  return (
    <div className="app">
      <header className="app-header">
        <h1>viz-site</h1>
        <nav>
          <Link to="/">Dashboards</Link>
          <Link to="/charts">Charts</Link>
        </nav>
      </header>
      <main className="app-main">
        <Routes>
          <Route path="/" element={<TreePage kind="dashboards" />} />
          <Route path="/charts" element={<TreePage kind="charts" />} />
        </Routes>
      </main>
    </div>
  );
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run from `web/`: `npm test` then `npm run typecheck`
Expected: PASS (all), typecheck clean.

- [ ] **Step 5: Look at it**

Run from the repo root in the background: `.venv/Scripts/viz-server`. Run from `web/`: `npm run dev`. Open `http://127.0.0.1:5173/` and `http://127.0.0.1:5173/charts` in a browser (or `curl -s http://127.0.0.1:5173/ | head -c 300` to confirm the dev server answers). Expected: the sales folder with its dashboard and charts. Stop both servers.

- [ ] **Step 6: Commit**

```bash
git add web/src/App.tsx web/src/App.test.tsx web/src/pages/TreePage.tsx web/src/pages/TreePage.test.tsx
git commit -m "feat(web): router, dashboards tree and charts library pages" -m "Co-Authored-By: <model> <noreply@anthropic.com>
Claude-Session: <session url>"
```

---

### Task 12: Dashboard page with control bar and grid

**Files:**
- Create: `web/src/components/ControlBar.tsx`, `web/src/components/ControlBar.test.tsx`, `web/src/pages/DashboardPage.tsx`, `web/src/pages/DashboardPage.test.tsx`
- Modify: `web/src/App.tsx` (add the `/d/*` route), `web/src/styles.css` (append grid cell rules)

**Interfaces:**
- Consumes: `fetchDashboard`, `Dashboard`, `Control`, `Row`; `Filter`, `FilterValue`, `SelectOptions`, `selectOptions`; `encodeFilters`, `decodeFilters`; `ChartTile`, `describeError`; `Markdown`; `ErrorCard`.
- Produces: `ControlBar({ controls, filters, options, onChange }: ControlBarProps)` where `onChange(controlId: string, value: FilterValue)`; every widget is labelled with the control's `label` (date and number ranges use `<label> from` and `<label> to`), so tests and Playwright can use `getByLabel`. `DashboardPage()` reads the id from the `/d/*` splat, holds filter state in the URL (`useSearchParams`, `replace: true`), derives select options from the union of the rows every small-lane tile reported, and renders the 12-column grid (`gridColumn: span w`, `gridRow: span h`, 120px rows).

- [ ] **Step 1: Write the failing tests**

`web/src/components/ControlBar.test.tsx`:

```tsx
import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import type { Control } from '../api/types';
import type { Filter } from '../data/filters';
import { ControlBar } from './ControlBar';

const controls: Control[] = [
  { id: 'period', type: 'date-range', label: 'Period', column: 'month', default: null },
  { id: 'region', type: 'select', label: 'Region', column: 'region', multi: true, default: null },
  { id: 'one', type: 'select', label: 'One region', column: 'region', default: null },
  { id: 'minrev', type: 'number-range', label: 'Revenue', column: 'revenue', default: null },
];
const filters: Filter[] = [
  { controlId: 'period', column: 'month', value: { type: 'date-range', from: '2026-01-01', to: null } },
  { controlId: 'region', column: 'region', value: { type: 'select', values: ['EMEA'] } },
  { controlId: 'one', column: 'region', value: { type: 'select', values: [] } },
  { controlId: 'minrev', column: 'revenue', value: { type: 'number-range', min: null, max: 5 } },
];
const options = { region: { options: ['APAC', 'EMEA', 'NA'], tooMany: false }, one: { options: ['APAC', 'EMEA', 'NA'], tooMany: false } };

describe('ControlBar', () => {
  it('renders labelled widgets with current values', () => {
    render(<ControlBar controls={controls} filters={filters} options={options} onChange={() => undefined} />);
    expect(screen.getByLabelText('Period from')).toHaveValue('2026-01-01');
    expect(screen.getByLabelText('Period to')).toHaveValue('');
    const region = screen.getByLabelText('Region') as HTMLSelectElement;
    expect(region.multiple).toBe(true);
    expect(Array.from(region.selectedOptions).map((o) => o.value)).toEqual(['EMEA']);
    expect(screen.getByLabelText('One region')).toHaveValue('');
    expect(screen.getByLabelText('Revenue to')).toHaveValue(5);
  });

  it('emits typed values on change', () => {
    const onChange = vi.fn();
    render(<ControlBar controls={controls} filters={filters} options={options} onChange={onChange} />);
    fireEvent.change(screen.getByLabelText('Period to'), { target: { value: '2026-03-01' } });
    expect(onChange).toHaveBeenLastCalledWith('period', { type: 'date-range', from: '2026-01-01', to: '2026-03-01' });

    const region = screen.getByLabelText('Region') as HTMLSelectElement;
    for (const o of Array.from(region.options)) o.selected = o.value === 'APAC' || o.value === 'NA';
    fireEvent.change(region);
    expect(onChange).toHaveBeenLastCalledWith('region', { type: 'select', values: ['APAC', 'NA'] });

    fireEvent.change(screen.getByLabelText('One region'), { target: { value: 'NA' } });
    expect(onChange).toHaveBeenLastCalledWith('one', { type: 'select', values: ['NA'] });

    fireEvent.change(screen.getByLabelText('Revenue from'), { target: { value: '2.5' } });
    expect(onChange).toHaveBeenLastCalledWith('minrev', { type: 'number-range', min: 2.5, max: 5 });
    fireEvent.change(screen.getByLabelText('Revenue to'), { target: { value: '' } });
    expect(onChange).toHaveBeenLastCalledWith('minrev', { type: 'number-range', min: null, max: null });
  });

  it('falls back to a text box when there are too many options', () => {
    const onChange = vi.fn();
    render(
      <ControlBar
        controls={[controls[1]]}
        filters={[{ controlId: 'region', column: 'region', value: { type: 'text', text: 'em' } }]}
        options={{ region: { options: [], tooMany: true } }}
        onChange={onChange}
      />,
    );
    const box = screen.getByLabelText('Region');
    expect(box.tagName).toBe('INPUT');
    expect(box).toHaveValue('em');
    fireEvent.change(box, { target: { value: 'na' } });
    expect(onChange).toHaveBeenLastCalledWith('region', { type: 'text', text: 'na' });
  });
});
```

`web/src/pages/DashboardPage.test.tsx`:

```tsx
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { ApiError } from '../api/client';
import type { Chart, Dashboard } from '../api/types';
import { DashboardPage } from './DashboardPage';

const mocks = vi.hoisted(() => ({
  fetchDashboard: vi.fn(),
  fetchChart: vi.fn(),
  fetchRows: vi.fn(),
  adapter: { mount: vi.fn(async () => undefined), update: vi.fn(async () => undefined), destroy: vi.fn() },
}));
vi.mock('../api/client', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../api/client')>()),
  fetchDashboard: mocks.fetchDashboard,
  fetchChart: mocks.fetchChart,
  fetchRows: mocks.fetchRows,
}));
vi.mock('../renderers', () => ({ getAdapter: () => mocks.adapter }));

const columns = [
  { name: 'month', type: 'date' as const },
  { name: 'region', type: 'string' as const },
  { name: 'revenue', type: 'number' as const },
];
const chart: Chart = {
  schema_version: 1, id: 'sales/revenue', title: 'Revenue', renderer: 'vega-lite',
  spec: { data: { name: 'data' }, mark: 'line' },
  data: { format: 'json', lane: 'small', rows: 2, bytes: 1, columns }, aggregate: null,
};
const stat: Chart = { ...chart, id: 'sales/total', title: 'Total', renderer: 'stat', spec: { value: 'revenue', agg: 'sum' } };
const rows = [
  { month: '2026-01-01', region: 'EMEA', revenue: 1 },
  { month: '2026-02-01', region: 'NA', revenue: 2 },
];
const dashboard: Dashboard = {
  schema_version: 1, id: 'sales/overview', title: 'Sales overview', description: 'Synthetic **data**.',
  controls: [
    { id: 'period', type: 'date-range', label: 'Period', column: 'month', default: null },
    { id: 'region', type: 'select', label: 'Region', column: 'region', multi: true, default: null },
  ],
  layout: [
    { chart: 'sales/revenue', w: 8, h: 4 },
    { chart: 'sales/total', w: 4, h: 2 },
    { markdown: 'Notes here.', w: 12, h: 1 },
  ],
};

function Probe() {
  return <div data-testid="search">{useLocation().search}</div>;
}

function renderPage(path = '/d/sales/overview') {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/d/*" element={<DashboardPage />} />
      </Routes>
      <Probe />
    </MemoryRouter>,
  );
}

beforeEach(() => {
  mocks.fetchDashboard.mockReset().mockResolvedValue(dashboard);
  mocks.fetchChart.mockReset().mockImplementation(async (id: string) => (id === 'sales/total' ? stat : chart));
  mocks.fetchRows.mockReset().mockResolvedValue(rows);
  mocks.adapter.mount.mockClear();
  mocks.adapter.update.mockClear();
});

describe('DashboardPage', () => {
  it('renders title, description, controls, tiles and markdown', async () => {
    renderPage();
    expect(await screen.findByRole('heading', { name: 'Sales overview' })).toBeInTheDocument();
    expect(screen.getByText('data').tagName).toBe('STRONG');
    expect(screen.getByText('Notes here.')).toBeInTheDocument();
    await waitFor(() => expect(document.querySelectorAll('[data-tile][data-state="ready"]')).toHaveLength(2));
    const cell = document.querySelector('[data-tile="sales/revenue"]')?.parentElement as HTMLElement;
    expect(cell.style.gridColumn).toBe('span 8');
    expect(cell.style.gridRow).toBe('span 4');
    const region = screen.getByLabelText('Region') as HTMLSelectElement;
    await waitFor(() => expect(Array.from(region.options).map((o) => o.value)).toEqual(['EMEA', 'NA']));
  });

  it('writes filter changes to the URL and pushes them into every tile', async () => {
    renderPage();
    await waitFor(() => expect(document.querySelectorAll('[data-tile][data-state="ready"]')).toHaveLength(2));
    const region = screen.getByLabelText('Region') as HTMLSelectElement;
    await waitFor(() => expect(region.options.length).toBe(2));
    for (const o of Array.from(region.options)) o.selected = o.value === 'NA';
    fireEvent.change(region);
    await waitFor(() => expect(screen.getByTestId('search').textContent).toContain('region=NA'));
    await waitFor(() => expect(mocks.adapter.update).toHaveBeenCalled());
    expect(mocks.adapter.update.mock.calls.at(-1)?.[0]).toEqual([rows[1]]);
    await waitFor(() => expect(document.querySelector('[data-tile="sales/revenue"]')?.getAttribute('data-rows')).toBe('1'));
    expect(screen.getByTestId('stat-value')).toHaveTextContent('2');
  });

  it('applies filters from the URL on first render', async () => {
    renderPage('/d/sales/overview?region=EMEA&period=2026-01-01..2026-01-31');
    await waitFor(() => expect(document.querySelectorAll('[data-tile][data-state="ready"]')).toHaveLength(2));
    expect(mocks.adapter.mount.mock.calls[0][2]).toEqual([rows[0]]);
    expect(screen.getByLabelText('Period from')).toHaveValue('2026-01-01');
  });

  it('shows one error card for a missing dashboard', async () => {
    mocks.fetchDashboard.mockRejectedValue(new ApiError(404, 'not found'));
    renderPage('/d/sales/nope');
    expect(await screen.findByRole('alert')).toHaveTextContent('sales/nope');
  });

  it('keeps the page up when one tile fails', async () => {
    mocks.fetchChart.mockImplementation(async (id: string) => {
      if (id === 'sales/total') throw new ApiError(422, { errors: ['spec/value: unknown column'] });
      return chart;
    });
    renderPage();
    expect(await screen.findByRole('alert')).toHaveTextContent('spec/value: unknown column');
    await waitFor(() => expect(document.querySelector('[data-tile="sales/revenue"]')?.getAttribute('data-state')).toBe('ready'));
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run from `web/`: `npm test -- src/components/ControlBar src/pages/DashboardPage`
Expected: FAIL, unresolved imports.

- [ ] **Step 3: Implement the control bar**

`web/src/components/ControlBar.tsx`:

```tsx
import type { Control } from '../api/types';
import type { Filter, FilterValue, SelectOptions } from '../data/filters';

export interface ControlBarProps {
  controls: Control[];
  filters: Filter[];
  options: Record<string, SelectOptions | undefined>;
  onChange: (controlId: string, value: FilterValue) => void;
}

function num(s: string): number | null {
  if (s.trim() === '') return null;
  const n = Number(s);
  return Number.isFinite(n) ? n : null;
}

function Widget({ control, value, opts, onChange }: { control: Control; value: FilterValue; opts: SelectOptions | undefined; onChange: (v: FilterValue) => void }) {
  const id = `ctl-${control.id}`;
  if (control.type === 'date-range' && value.type === 'date-range') {
    return (
      <div className="control">
        <span>{control.label}</span>
        <div className="range">
          <label htmlFor={`${id}-from`} className="muted">from</label>
          <input id={`${id}-from`} type="date" aria-label={`${control.label} from`} value={value.from ?? ''} onChange={(e) => onChange({ ...value, from: e.target.value || null })} />
          <label htmlFor={`${id}-to`} className="muted">to</label>
          <input id={`${id}-to`} type="date" aria-label={`${control.label} to`} value={value.to ?? ''} onChange={(e) => onChange({ ...value, to: e.target.value || null })} />
        </div>
      </div>
    );
  }
  if (control.type === 'number-range' && value.type === 'number-range') {
    return (
      <div className="control">
        <span>{control.label}</span>
        <div className="range">
          <label htmlFor={`${id}-from`} className="muted">from</label>
          <input id={`${id}-from`} type="number" aria-label={`${control.label} from`} value={value.min ?? ''} onChange={(e) => onChange({ ...value, min: num(e.target.value) })} />
          <label htmlFor={`${id}-to`} className="muted">to</label>
          <input id={`${id}-to`} type="number" aria-label={`${control.label} to`} value={value.max ?? ''} onChange={(e) => onChange({ ...value, max: num(e.target.value) })} />
        </div>
      </div>
    );
  }
  if (control.type === 'select' && value.type === 'text') {
    return (
      <div className="control">
        <label htmlFor={id}>{control.label}</label>
        <input id={id} type="text" placeholder="contains…" value={value.text} onChange={(e) => onChange({ type: 'text', text: e.target.value })} />
        {opts?.tooMany && <span className="muted">too many values to list</span>}
      </div>
    );
  }
  if (control.type === 'select' && value.type === 'select') {
    const list = opts?.options ?? value.values;
    const multi = control.multi === true;
    return (
      <div className="control">
        <label htmlFor={id}>{control.label}</label>
        <select
          id={id}
          multiple={multi}
          value={multi ? value.values : (value.values[0] ?? '')}
          onChange={(e) => {
            const picked = Array.from(e.target.selectedOptions).map((o) => o.value).filter((v) => v !== '');
            onChange({ type: 'select', values: multi ? picked : picked.slice(0, 1) });
          }}
        >
          {!multi && <option value="">(all)</option>}
          {list.map((o) => (
            <option key={o} value={o}>
              {o}
            </option>
          ))}
        </select>
      </div>
    );
  }
  return null;
}

export function ControlBar({ controls, filters, options, onChange }: ControlBarProps) {
  return (
    <div className="control-bar">
      {controls.map((control) => {
        const filter = filters.find((f) => f.controlId === control.id);
        if (!filter) return null;
        return <Widget key={control.id} control={control} value={filter.value} opts={options[control.id]} onChange={(v) => onChange(control.id, v)} />;
      })}
    </div>
  );
}
```

- [ ] **Step 4: Implement the dashboard page and wire the route**

`web/src/pages/DashboardPage.tsx`:

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

export function DashboardPage() {
  const id = useParams()['*'] ?? '';
  const [dashboard, setDashboard] = useState<Dashboard | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [rowsByChart, setRowsByChart] = useState<Record<string, Row[]>>({});
  const [searchParams, setSearchParams] = useSearchParams();
  const today = useMemo(() => new Date(), []);

  useEffect(() => {
    let cancelled = false;
    setDashboard(null);
    setError(null);
    setRowsByChart({});
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

  const options = useMemo(() => {
    const out: Record<string, SelectOptions | undefined> = {};
    const sets = Object.values(rowsByChart);
    if (sets.length === 0) return out;
    for (const c of controls) if (c.type === 'select') out[c.id] = selectOptions(sets, c.column);
    return out;
  }, [controls, rowsByChart]);

  const filters = useMemo(() => decodeFilters(searchParams, controls, options, today), [searchParams, controls, options, today]);

  const onChange = useCallback(
    (controlId: string, value: FilterValue) => {
      const next = filters.map((f) => (f.controlId === controlId ? { ...f, value } : f));
      setSearchParams(encodeFilters(next), { replace: true });
    },
    [filters, setSearchParams],
  );

  const onRows = useCallback((chartId: string, rows: Row[]) => {
    setRowsByChart((prev) => ({ ...prev, [chartId]: rows }));
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
              <ChartTile chartId={tile.chart} filters={filters} onRows={onRows} />
            </div>
          );
        })}
      </div>
    </div>
  );
}
```

In `web/src/App.tsx` add the import and the route:

```tsx
import { DashboardPage } from './pages/DashboardPage';
```

```tsx
          <Route path="/d/*" element={<DashboardPage />} />
```

Append to `web/src/styles.css`:

```css

.grid-cell { min-width: 0; min-height: 0; }
.grid-cell > .tile { height: 100%; }
```

- [ ] **Step 5: Run tests to verify they pass**

Run from `web/`: `npm test` then `npm run typecheck`
Expected: PASS (all), typecheck clean.

- [ ] **Step 6: Look at it**

Run the API server and `npm run dev` as in Task 11 and open `http://127.0.0.1:5173/d/sales/overview`. Expected: control bar with Period and Region, the Vega-Lite line chart, the stat tile and the markdown tile; changing Region rewrites the URL and the chart. Stop both servers.

- [ ] **Step 7: Commit**

```bash
git add web/src/components/ControlBar.tsx web/src/components/ControlBar.test.tsx web/src/pages/DashboardPage.tsx web/src/pages/DashboardPage.test.tsx web/src/App.tsx web/src/styles.css
git commit -m "feat(web): dashboard page with URL-backed controls and 12-column grid" -m "Co-Authored-By: <model> <noreply@anthropic.com>
Claude-Session: <session url>"
```

---

### Task 13: Single chart page

**Files:**
- Create: `web/src/pages/ChartPage.tsx`, `web/src/pages/ChartPage.test.tsx`
- Modify: `web/src/App.tsx` (add the `/c/*` route)

**Interfaces:**
- Consumes: `fetchChart`, `Chart`; `ChartTile`, `describeError`; `Markdown`; `ErrorCard`.
- Produces: `ChartPage()` at `/c/*`: title with a `static` badge when there is no `source`, the chart at full width (`ChartTile` with `showTitle={false}` and no filters), the description through `Markdown`, a columns table, the SQL in `<pre class="sql">` when `source.sql` is present, and a one-line note when the chart is refreshable but the SQL is hidden.

- [ ] **Step 1: Write the failing test**

`web/src/pages/ChartPage.test.tsx`:

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
  spec: { data: { name: 'data' }, mark: 'line' },
  data: { format: 'json', lane: 'small', rows: 1, bytes: 1, columns: [{ name: 'month', type: 'date' }, { name: 'revenue', type: 'number' }] },
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

beforeEach(() => {
  mocks.fetchChart.mockReset().mockResolvedValue(chart);
  mocks.fetchRows.mockReset().mockResolvedValue([{ month: '2026-01-01', revenue: 1 }]);
});

describe('ChartPage', () => {
  it('shows title, description, columns and SQL for a refreshable chart', async () => {
    renderAt('/c/sales/revenue');
    expect(await screen.findByRole('heading', { name: 'Revenue' })).toBeInTheDocument();
    expect(screen.getByText('revenue', { selector: 'em' })).toBeInTheDocument();
    expect(screen.getByRole('cell', { name: 'month' })).toBeInTheDocument();
    expect(screen.getByText('SELECT month, revenue FROM t').tagName).toBe('PRE');
    expect(screen.queryByText('static')).toBeNull();
    await waitFor(() => expect(document.querySelector('[data-tile="sales/revenue"]')?.getAttribute('data-state')).toBe('ready'));
  });

  it('shows the static badge for a one-off chart and the hidden-SQL note otherwise', async () => {
    mocks.fetchChart.mockResolvedValue({ ...chart, source: undefined });
    renderAt('/c/sales/revenue');
    expect(await screen.findByText('static')).toBeInTheDocument();

    mocks.fetchChart.mockResolvedValue({ ...chart, source: { kind: 'databricks-sql', show_sql: false, schedule: '0 6 * * *' } });
    renderAt('/c/sales/revenue');
    expect(await screen.findByText(/SQL hidden/)).toBeInTheDocument();
  });

  it('shows an error card when the chart is missing', async () => {
    mocks.fetchChart.mockRejectedValue(new Error('nope'));
    renderAt('/c/sales/x');
    expect((await screen.findAllByRole('alert')).length).toBeGreaterThan(0);
  });
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run from `web/`: `npm test -- src/pages/ChartPage`
Expected: FAIL, `./ChartPage` unresolved.

- [ ] **Step 3: Implement**

`web/src/pages/ChartPage.tsx`:

```tsx
import { useEffect, useState } from 'react';
import { useParams } from 'react-router-dom';
import { fetchChart } from '../api/client';
import type { Chart } from '../api/types';
import { ChartTile, describeError } from '../components/ChartTile';
import { ErrorCard } from '../components/ErrorCard';
import { Markdown } from '../components/Markdown';

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

  return (
    <div className="chart-page">
      <h2>
        {chart?.title ?? id}
        {chart && !chart.source && <span className="badge">static</span>}
      </h2>
      <ChartTile chartId={id} filters={[]} showTitle={false} />
      {chart?.description && <Markdown text={chart.description} />}
      {chart && (
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
      )}
      {chart?.source?.sql && <pre className="sql">{chart.source.sql}</pre>}
      {chart?.source && !chart.source.sql && (
        <p className="muted">Refreshable from Databricks SQL (SQL hidden by the publisher){chart.source.schedule ? `, schedule ${chart.source.schedule}` : ''}.</p>
      )}
      {chart && (
        <p className="muted">
          {chart.data.lane} lane, {chart.data.rows} rows, {chart.data.bytes} bytes, renderer {chart.renderer}
          {chart.updated_at ? `, updated ${chart.updated_at}` : ''}
        </p>
      )}
    </div>
  );
}
```

In `web/src/App.tsx` add the import and the route:

```tsx
import { ChartPage } from './pages/ChartPage';
```

```tsx
          <Route path="/c/*" element={<ChartPage />} />
```

- [ ] **Step 4: Run tests to verify they pass**

Run from `web/`: `npm test` then `npm run typecheck`
Expected: PASS (all), typecheck clean.

- [ ] **Step 5: Commit**

```bash
git add web/src/pages/ChartPage.tsx web/src/pages/ChartPage.test.tsx web/src/App.tsx
git commit -m "feat(web): single chart page with columns, SQL and static badge" -m "Co-Authored-By: <model> <noreply@anthropic.com>
Claude-Session: <session url>"
```

---

### Task 14: DuckDB-WASM large lane

**Files:**
- Create: `web/src/data/duckdb.ts`, `web/src/data/duckdb.test.ts`
- Modify: `web/src/components/ChartTile.tsx`, `web/src/components/ChartTile.test.tsx`

**Interfaces:**
- Consumes: `dataUrl` from `web/src/api/client.ts`; `Column`, `Row`; `Filter`, `isActive`.
- Produces in `duckdb.ts`: `class DuckDbError extends Error` (name `DuckDbError`); constants `ROW_LIMIT = 50000`, `DEFAULT_TIMEOUT_MS = 15000`, `LARGE_LANE_MAX_BYTES = 209715200`, `INIT_STATEMENTS` (the four `SET`s in order); pure functions `tableName(chartId: string): string`, `checkSingleSelectSyntax(aggregate: string): string` (strips comments, rejects `;` and anything not starting with `SELECT` or `WITH`), `parseSerializedSql(json: string): void` (validates the output of `json_serialize_sql`: `error` false, exactly one statement, node type `SELECT_NODE`), `buildFilteredQuery(aggregate: string, table: string, columns: Column[], filters: Filter[]): BuiltQuery` with `interface BuiltQuery { sql: string; params: unknown[]; tempTables: { name: string; values: string[] }[] }`, `arrowRowsToRows(rows: Record<string, unknown>[], columns: Column[]): Row[]`; and the async entry point `queryLargeLane(chartId: string, aggregate: string, columns: Column[], filters: Filter[], timeoutMs?: number): Promise<Row[]>`. The module imports `@duckdb/duckdb-wasm` and `apache-arrow` only inside functions, so it stays out of the main chunk; `ChartTile` imports the module itself lazily.
- Runtime behavior of `queryLargeLane`: one shared DuckDB per page, created on first use (worker + wasm from bundled `?url` assets, `VoidLogger`, `open` with `castBigIntToDouble`, `castDecimalToDouble`, `castTimestampToDate`), then `INIT_STATEMENTS` in order, then a probe of `json_serialize_sql` (if it throws, the runtime records `jsonCheck = false` and logs one warning; the pure syntax check and the subquery wrapper still apply). Per chart: fetch `dataUrl(id)`, refuse bodies over `LARGE_LANE_MAX_BYTES`, `registerFileBuffer`, `CREATE TABLE "<tableName>" AS SELECT * FROM read_parquet('<file>')`, `dropFile`. Per query: all work is serialized through one promise chain; select values are inserted as Arrow temp tables named `f_<controlId>_<n>` and dropped afterwards; the statement is prepared and run with the range/text parameters; a timeout terminates the worker and clears the shared runtime so the next call rebuilds it.

- [ ] **Step 1: Write the failing unit tests**

`web/src/data/duckdb.test.ts`:

```ts
import { describe, expect, it } from 'vitest';
import type { Column } from '../api/types';
import type { Filter } from './filters';
import {
  DuckDbError,
  INIT_STATEMENTS,
  ROW_LIMIT,
  arrowRowsToRows,
  buildFilteredQuery,
  checkSingleSelectSyntax,
  parseSerializedSql,
  tableName,
} from './duckdb';

const columns: Column[] = [
  { name: 'day', type: 'date' },
  { name: 'region', type: 'string' },
  { name: 'amount', type: 'number' },
];

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

describe('tableName', () => {
  it('derives a safe identifier from the id', () => {
    expect(tableName('bakeoff/vega-lite/order-lines')).toBe('raw_bakeoff_vega_lite_order_lines');
  });
});

describe('checkSingleSelectSyntax', () => {
  it('accepts SELECT and WITH, strips comments', () => {
    expect(checkSingleSelectSyntax('  SELECT 1')).toBe('SELECT 1');
    expect(checkSingleSelectSyntax('-- note\nWITH x AS (SELECT 1) SELECT * FROM x')).toMatch(/^WITH/);
    expect(checkSingleSelectSyntax('/* c */ select day from data')).toBe('select day from data');
  });
  it('rejects multiple statements and non-selects', () => {
    expect(() => checkSingleSelectSyntax('SELECT 1; DROP TABLE x')).toThrow(DuckDbError);
    expect(() => checkSingleSelectSyntax('INSTALL httpfs')).toThrow(DuckDbError);
    expect(() => checkSingleSelectSyntax('COPY data TO \'x\'')).toThrow(DuckDbError);
    expect(() => checkSingleSelectSyntax('')).toThrow(DuckDbError);
  });
});

describe('parseSerializedSql', () => {
  it('accepts one SELECT node and rejects everything else', () => {
    expect(() => parseSerializedSql('{"error":false,"statements":[{"node":{"type":"SELECT_NODE"}}]}')).not.toThrow();
    expect(() => parseSerializedSql('{"error":true,"error_type":"parser","error_message":"syntax error"}')).toThrow(/syntax error/);
    expect(() => parseSerializedSql('{"error":false,"statements":[{"node":{"type":"SELECT_NODE"}},{"node":{"type":"SELECT_NODE"}}]}')).toThrow(/single/);
    expect(() => parseSerializedSql('{"error":false,"statements":[{"node":{"type":"COPY_STATEMENT"}}]}')).toThrow(/SELECT/);
    expect(() => parseSerializedSql('not json')).toThrow(DuckDbError);
  });
});

describe('buildFilteredQuery', () => {
  const aggregate = 'SELECT day, sum(amount) AS amount FROM data GROUP BY day ORDER BY day';

  it('wraps the aggregate in a data CTE with a row limit and no filters', () => {
    const q = buildFilteredQuery(aggregate, 'raw_x', columns, []);
    expect(q.sql).toBe(`WITH data AS (SELECT * FROM "raw_x") SELECT * FROM (${aggregate}) LIMIT ${ROW_LIMIT}`);
    expect(q.params).toEqual([]);
    expect(q.tempTables).toEqual([]);
  });

  it('binds ranges as parameters and selects as temp tables, in filter order', () => {
    const filters: Filter[] = [
      { controlId: 'days', column: 'day', value: { type: 'date-range', from: '2025-01-01', to: '2025-06-30' } },
      { controlId: 'region', column: 'region', value: { type: 'select', values: ['EMEA', "x'; DROP TABLE t; --"] } },
      { controlId: 'amt', column: 'amount', value: { type: 'number-range', min: 10, max: null } },
      { controlId: 'prod', column: 'region', value: { type: 'text', text: 'em' } },
    ];
    const q = buildFilteredQuery(aggregate, 'raw_x', columns, filters);
    expect(q.sql).toContain('WHERE CAST("day" AS DATE) >= CAST(? AS DATE) AND CAST("day" AS DATE) <= CAST(? AS DATE)');
    expect(q.sql).toMatch(/CAST\("region" AS VARCHAR\) IN \(SELECT v FROM "f_region_\d+"\)/);
    expect(q.sql).toContain('"amount" >= ?');
    expect(q.sql).toContain('contains(lower(CAST("region" AS VARCHAR)), lower(?))');
    expect(q.params).toEqual(['2025-01-01', '2025-06-30', 10, 'em']);
    expect(q.tempTables).toHaveLength(1);
    expect(q.tempTables[0].values).toEqual(['EMEA', "x'; DROP TABLE t; --"]);
    expect(q.sql).not.toContain('DROP');
  });

  it('skips inactive filters, undeclared columns and unsafe column names', () => {
    const filters: Filter[] = [
      { controlId: 'a', column: 'region', value: { type: 'select', values: [] } },
      { controlId: 'b', column: 'nope', value: { type: 'number-range', min: 1, max: 2 } },
      { controlId: 'c', column: 'bad"col', value: { type: 'number-range', min: 1, max: 2 } },
    ];
    const q = buildFilteredQuery(aggregate, 'raw_x', [...columns, { name: 'bad"col', type: 'number' }], filters);
    expect(q.sql).not.toContain('WHERE');
    expect(q.params).toEqual([]);
  });

  it('rejects a hostile aggregate before building', () => {
    expect(() => buildFilteredQuery('SELECT 1; SELECT 2', 'raw_x', columns, [])).toThrow(DuckDbError);
  });
});

describe('arrowRowsToRows', () => {
  it('normalizes bigint, Date and epoch numbers by declared column type', () => {
    const out = arrowRowsToRows(
      [
        { day: new Date(Date.UTC(2025, 0, 2)), region: 'EMEA', amount: 10n, total: 5 },
        { day: Date.UTC(2025, 0, 3), region: 'NA', amount: 2.5, total: 7n },
      ],
      columns,
    );
    expect(out).toEqual([
      { day: '2025-01-02', region: 'EMEA', amount: 10, total: 5 },
      { day: '2025-01-03', region: 'NA', amount: 2.5, total: 7 },
    ]);
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run from `web/`: `npm test -- src/data/duckdb`
Expected: FAIL, `./duckdb` unresolved.

- [ ] **Step 3: Implement**

`web/src/data/duckdb.ts`:

```ts
// DuckDB-WASM large lane. Spec 12.3: locked configuration before any chart
// SQL runs, no extension fetches, no external access, control values only as
// parameters and temp tables, a 50k row cap and a wall-clock budget.
import { dataUrl } from '../api/client';
import type { Column, Row } from '../api/types';
import { isActive, type Filter } from './filters';

export const ROW_LIMIT = 50000;
export const DEFAULT_TIMEOUT_MS = 15000;
export const LARGE_LANE_MAX_BYTES = 209715200;

export const INIT_STATEMENTS: readonly string[] = [
  'SET autoinstall_known_extensions=false',
  'SET autoload_known_extensions=false',
  "SET memory_limit='512MB'",
  'SET lock_configuration=true',
];

const COLUMN_NAME = /^[A-Za-z_][A-Za-z0-9_]*$/;

export class DuckDbError extends Error {
  constructor(message: string) {
    super(message);
    this.name = 'DuckDbError';
  }
}

export function tableName(chartId: string): string {
  return `raw_${chartId.replace(/[^a-z0-9]/g, '_')}`;
}

export function checkSingleSelectSyntax(aggregate: string): string {
  const stripped = aggregate
    .replace(/\/\*[\s\S]*?\*\//g, ' ')
    .replace(/--[^\n]*/g, ' ')
    .trim();
  if (stripped === '') throw new DuckDbError('aggregate is empty');
  if (stripped.includes(';')) throw new DuckDbError('aggregate must be a single statement');
  if (!/^(select|with)\b/i.test(stripped)) throw new DuckDbError('aggregate must be a SELECT');
  return stripped;
}

export function parseSerializedSql(json: string): void {
  let parsed: unknown;
  try {
    parsed = JSON.parse(json);
  } catch {
    throw new DuckDbError('could not parse the serialized aggregate');
  }
  const doc = parsed as { error?: boolean; error_message?: string; statements?: { node?: { type?: string } }[] };
  if (doc.error) throw new DuckDbError(`aggregate does not parse: ${doc.error_message ?? 'unknown error'}`);
  if (!Array.isArray(doc.statements) || doc.statements.length !== 1) throw new DuckDbError('aggregate must be a single statement');
  if (doc.statements[0]?.node?.type !== 'SELECT_NODE') throw new DuckDbError('aggregate must be a SELECT');
}

export interface BuiltQuery {
  sql: string;
  params: unknown[];
  tempTables: { name: string; values: string[] }[];
}

let tempCounter = 0;

export function buildFilteredQuery(aggregate: string, table: string, columns: Column[], filters: Filter[]): BuiltQuery {
  const clean = checkSingleSelectSyntax(aggregate);
  const types = new Map(columns.map((c) => [c.name, c.type]));
  const conds: string[] = [];
  const params: unknown[] = [];
  const tempTables: BuiltQuery['tempTables'] = [];
  for (const f of filters) {
    const type = types.get(f.column);
    if (!type || !COLUMN_NAME.test(f.column) || !isActive(f.value)) continue;
    const col = `"${f.column}"`;
    const value = f.value;
    switch (value.type) {
      case 'date-range': {
        const expr = type === 'date' || type === 'timestamp' ? `CAST(${col} AS DATE)` : col;
        if (value.from !== null) {
          conds.push(`${expr} >= CAST(? AS DATE)`);
          params.push(value.from);
        }
        if (value.to !== null) {
          conds.push(`${expr} <= CAST(? AS DATE)`);
          params.push(value.to);
        }
        break;
      }
      case 'number-range': {
        if (value.min !== null) {
          conds.push(`${col} >= ?`);
          params.push(value.min);
        }
        if (value.max !== null) {
          conds.push(`${col} <= ?`);
          params.push(value.max);
        }
        break;
      }
      case 'select': {
        tempCounter += 1;
        const name = `f_${f.controlId.replace(/[^a-z0-9]/g, '_')}_${tempCounter}`;
        tempTables.push({ name, values: value.values });
        conds.push(`CAST(${col} AS VARCHAR) IN (SELECT v FROM "${name}")`);
        break;
      }
      case 'text': {
        conds.push(`contains(lower(CAST(${col} AS VARCHAR)), lower(?))`);
        params.push(value.text);
        break;
      }
    }
  }
  const where = conds.length > 0 ? ` WHERE ${conds.join(' AND ')}` : '';
  const sql = `WITH data AS (SELECT * FROM "${table}"${where}) SELECT * FROM (${clean}) LIMIT ${ROW_LIMIT}`;
  return { sql, params, tempTables };
}

function normalize(v: unknown, type: Column['type'] | undefined): unknown {
  if (typeof v === 'bigint') return Number(v);
  if (v instanceof Date) return type === 'date' ? v.toISOString().slice(0, 10) : v.toISOString();
  if (typeof v === 'number' && type === 'date') return new Date(v).toISOString().slice(0, 10);
  if (typeof v === 'number' && type === 'timestamp') return new Date(v).toISOString();
  return v;
}

export function arrowRowsToRows(rows: Record<string, unknown>[], columns: Column[]): Row[] {
  const types = new Map(columns.map((c) => [c.name, c.type]));
  return rows.map((r) => {
    const out: Row = {};
    for (const key of Object.keys(r)) out[key] = normalize(r[key], types.get(key));
    return out;
  });
}

// ---- runtime -------------------------------------------------------------

type DuckDbModule = typeof import('@duckdb/duckdb-wasm');
type AsyncDuckDB = InstanceType<DuckDbModule['AsyncDuckDB']>;
type Connection = Awaited<ReturnType<AsyncDuckDB['connect']>>;

interface Runtime {
  db: AsyncDuckDB;
  conn: Connection;
  loaded: Set<string>;
  jsonCheck: boolean;
}

let runtime: Promise<Runtime> | null = null;
let chain: Promise<unknown> = Promise.resolve();

async function createRuntime(): Promise<Runtime> {
  const duckdb = await import('@duckdb/duckdb-wasm');
  const [{ default: wasmUrl }, { default: workerUrl }] = await Promise.all([
    import('@duckdb/duckdb-wasm/dist/duckdb-eh.wasm?url'),
    import('@duckdb/duckdb-wasm/dist/duckdb-browser-eh.worker.js?url'),
  ]);
  const worker = new Worker(workerUrl);
  const db = new duckdb.AsyncDuckDB(new duckdb.VoidLogger(), worker);
  await db.instantiate(wasmUrl);
  await db.open({ path: ':memory:', query: { castBigIntToDouble: true, castDecimalToDouble: true, castTimestampToDate: true } });
  const conn = await db.connect();
  for (const statement of INIT_STATEMENTS) await conn.query(statement);
  let jsonCheck = true;
  try {
    await conn.query("SELECT json_serialize_sql('SELECT 1')");
  } catch {
    jsonCheck = false;
    console.warn('duckdb: json_serialize_sql is unavailable in this build; relying on the syntax check and subquery wrapping');
  }
  return { db, conn, loaded: new Set(), jsonCheck };
}

function getRuntime(): Promise<Runtime> {
  if (!runtime) {
    runtime = createRuntime().catch((err: unknown) => {
      runtime = null;
      throw new DuckDbError(`could not start DuckDB: ${err instanceof Error ? err.message : String(err)}`);
    });
  }
  return runtime;
}

async function terminateRuntime(): Promise<void> {
  const current = runtime;
  runtime = null;
  if (!current) return;
  try {
    const rt = await current;
    await rt.db.terminate();
  } catch {
    // already gone
  }
}

async function ensureLoaded(rt: Runtime, chartId: string): Promise<void> {
  if (rt.loaded.has(chartId)) return;
  const res = await fetch(dataUrl(chartId));
  if (!res.ok) throw new DuckDbError(`data file request failed (${res.status})`);
  const declared = Number(res.headers.get('content-length'));
  if (Number.isFinite(declared) && declared > LARGE_LANE_MAX_BYTES) throw new DuckDbError(`data file is ${declared} bytes, above the large-lane cap`);
  const buffer = new Uint8Array(await res.arrayBuffer());
  if (buffer.byteLength > LARGE_LANE_MAX_BYTES) throw new DuckDbError(`data file is ${buffer.byteLength} bytes, above the large-lane cap`);
  const file = `${tableName(chartId)}.parquet`;
  await rt.db.registerFileBuffer(file, buffer);
  try {
    await rt.conn.query(`CREATE TABLE "${tableName(chartId)}" AS SELECT * FROM read_parquet('${file}')`);
  } finally {
    await rt.db.dropFile(file).catch(() => undefined);
  }
  rt.loaded.add(chartId);
}

async function assertSingleSelect(conn: Connection, aggregate: string): Promise<void> {
  const stmt = await conn.prepare('SELECT json_serialize_sql(?) AS j');
  try {
    const table = await stmt.query(aggregate);
    const first = table.toArray()[0] as { toJSON(): { j: unknown } } | undefined;
    parseSerializedSql(String(first?.toJSON().j ?? ''));
  } finally {
    await stmt.close().catch(() => undefined);
  }
}

function withTimeout<T>(promise: Promise<T>, ms: number): Promise<T> {
  return new Promise<T>((resolve, reject) => {
    const timer = setTimeout(() => reject(new DuckDbError(`query timed out after ${ms} ms`)), ms);
    promise.then(
      (v) => {
        clearTimeout(timer);
        resolve(v);
      },
      (e: unknown) => {
        clearTimeout(timer);
        reject(e);
      },
    );
  });
}

async function runQuery(chartId: string, aggregate: string, columns: Column[], filters: Filter[], timeoutMs: number): Promise<Row[]> {
  const built = buildFilteredQuery(aggregate, tableName(chartId), columns, filters);
  const rt = await getRuntime();
  await ensureLoaded(rt, chartId);
  if (rt.jsonCheck) await assertSingleSelect(rt.conn, aggregate);
  const arrow = await import('apache-arrow');
  for (const t of built.tempTables) {
    await rt.conn.insertArrowTable(arrow.tableFromArrays({ v: t.values }), { name: t.name, create: true });
  }
  try {
    const stmt = await rt.conn.prepare(built.sql);
    try {
      const table = await withTimeout(stmt.query(...built.params), timeoutMs);
      const rows = table.toArray().map((r) => (r as { toJSON(): Record<string, unknown> }).toJSON());
      return arrowRowsToRows(rows, columns);
    } finally {
      await stmt.close().catch(() => undefined);
    }
  } catch (err) {
    if (err instanceof DuckDbError && /timed out/.test(err.message)) {
      await terminateRuntime();
      throw err;
    }
    throw err instanceof DuckDbError ? err : new DuckDbError(err instanceof Error ? err.message : String(err));
  } finally {
    if (runtime) {
      for (const t of built.tempTables) await rt.conn.query(`DROP TABLE IF EXISTS "${t.name}"`).catch(() => undefined);
    }
  }
}

/** Run a chart's aggregate over its parquet file with the given filters. Serialized page-wide. */
export function queryLargeLane(chartId: string, aggregate: string, columns: Column[], filters: Filter[], timeoutMs = DEFAULT_TIMEOUT_MS): Promise<Row[]> {
  const next = chain.then(() => runQuery(chartId, aggregate, columns, filters, timeoutMs));
  chain = next.catch(() => undefined);
  return next;
}
```

- [ ] **Step 4: Run the unit tests and typecheck**

Run from `web/`: `npm test -- src/data/duckdb` then `npm run typecheck`
Expected: PASS (10 tests). If typecheck cannot resolve the two `?url` imports, add these two lines to `web/src/vite-env.d.ts` and re-run:

```ts
declare module '@duckdb/duckdb-wasm/dist/duckdb-eh.wasm?url' { const url: string; export default url; }
declare module '@duckdb/duckdb-wasm/dist/duckdb-browser-eh.worker.js?url' { const url: string; export default url; }
```

- [ ] **Step 5: Wire the large lane into the tile**

In `web/src/components/ChartTile.tsx`:

Add a state line after `const [rows, setRows] = useState<Row[] | null>(null);`:

```tsx
  const [largeRows, setLargeRows] = useState<Row[] | null>(null);
```

In the load effect, replace the line

```tsx
        if (doc.data.lane === 'large') throw new Error('large lane is not supported yet');
```

with

```tsx
        if (doc.data.lane === 'large') {
          if (!cancelled) setChart(doc);
          return;
        }
```

and add `setLargeRows(null);` next to the other resets at the top of that effect.

Replace the `filtered` memo with:

```tsx
  // eslint-disable-next-line react-hooks/exhaustive-deps -- `key` stands in for `filters`
  const filtered = useMemo(() => {
    if (!chart) return null;
    if (chart.data.lane === 'large') return largeRows;
    return rows ? applyFilters(rows, chart.data.columns, filters) : null;
  }, [chart, rows, largeRows, key]);
```

Add this effect directly after the `filtered` memo:

```tsx
  // Large lane: every filter change is a new DuckDB query over the parquet table.
  useEffect(() => {
    if (!chart || chart.data.lane !== 'large' || error) return;
    let cancelled = false;
    (async () => {
      try {
        const { queryLargeLane } = await import('../data/duckdb');
        const result = await queryLargeLane(chartId, chart.aggregate ?? '', chart.data.columns, filters);
        if (!cancelled) setLargeRows(result);
      } catch (err) {
        if (!cancelled) setError(describeError(err));
      }
    })();
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- `key` stands in for `filters`
  }, [chart, chartId, key, error]);
```

- [ ] **Step 6: Replace the placeholder tile test**

In `web/src/components/ChartTile.test.tsx`, add to the `mocks` object:

```ts
  queryLargeLane: vi.fn(),
```

add after the other `vi.mock` calls:

```ts
vi.mock('../data/duckdb', () => ({ queryLargeLane: mocks.queryLargeLane }));
```

add `mocks.queryLargeLane.mockReset();` inside `beforeEach`, and replace the test `shows an error card for the large lane until Task 14` with:

```tsx
  it('runs the aggregate through DuckDB for the large lane and re-runs on filter change', async () => {
    const large: Chart = { ...chart, data: { ...chart.data, lane: 'large', format: 'parquet' }, aggregate: 'SELECT region, sum(revenue) AS revenue FROM data GROUP BY region' };
    mocks.fetchChart.mockResolvedValue(large);
    mocks.queryLargeLane.mockResolvedValueOnce([{ region: 'EMEA', revenue: 1 }, { region: 'NA', revenue: 2 }]).mockResolvedValueOnce([{ region: 'NA', revenue: 2 }]);
    const filter = { controlId: 'r', column: 'region', value: { type: 'select' as const, values: ['NA'] } };
    const { rerender } = render(<ChartTile chartId="sales/x" filters={[]} />);
    await waitFor(() => expect(tile().dataset.state).toBe('ready'));
    expect(mocks.fetchRows).not.toHaveBeenCalled();
    expect(mocks.queryLargeLane).toHaveBeenCalledWith('sales/x', large.aggregate, large.data.columns, []);
    expect(tile().dataset.rows).toBe('2');
    rerender(<ChartTile chartId="sales/x" filters={[filter]} />);
    await waitFor(() => expect(mocks.queryLargeLane).toHaveBeenCalledTimes(2));
    expect(mocks.queryLargeLane.mock.calls[1][3]).toEqual([filter]);
    await waitFor(() => expect(tile().dataset.rows).toBe('1'));
    expect(mocks.adapter.update).toHaveBeenCalledWith([{ region: 'NA', revenue: 2 }]);
  });

  it('shows a query failure as an error card', async () => {
    mocks.fetchChart.mockResolvedValue({ ...chart, data: { ...chart.data, lane: 'large', format: 'parquet' }, aggregate: 'SELECT 1' });
    const err = new Error('query timed out after 15000 ms');
    err.name = 'DuckDbError';
    mocks.queryLargeLane.mockRejectedValue(err);
    render(<ChartTile chartId="sales/x" filters={[]} />);
    expect(await screen.findByRole('alert')).toHaveTextContent('query failed: query timed out');
  });
```

- [ ] **Step 7: Run everything**

Run from `web/`: `npm test`, `npm run typecheck`, then `npm run build`
Expected: PASS (all); build output lists `assets/duckdb-<hash>.js`, `assets/duckdb-browser-eh.worker-<hash>.js` and `assets/duckdb-eh-<hash>.wasm` next to the three `renderer-*` chunks. If the build reports the worker or wasm as missing, report the exact message; do not switch to a CDN bundle.

- [ ] **Step 8: Commit**

```bash
git add web/src/data/duckdb.ts web/src/data/duckdb.test.ts web/src/components/ChartTile.tsx web/src/components/ChartTile.test.tsx web/src/vite-env.d.ts
git commit -m "feat(web): DuckDB-WASM large lane with locked config and parameterized filters" -m "Co-Authored-By: <model> <noreply@anthropic.com>
Claude-Session: <session url>"
```

---

### Task 15: Bake-off samples in the sample bucket

**Files:**
- Modify: `sample-bucket/generate.py`, `tests/test_sample_bucket.py`, `pyproject.toml` (add `pyarrow>=17` to the `dev` extra), `.gitattributes` (mark parquet binary)
- Generated: `sample-bucket/viz/charts/bakeoff/**`, `sample-bucket/viz/dashboards/bakeoff/**`

**Interfaces:**
- Produces, for each renderer `r` in `vega-lite`, `plotly`, `echarts`: charts `bakeoff/<r>/time-series` (small lane, monthly revenue by region), `bakeoff/<r>/grouped-bar` (small lane, quarterly orders by region), `bakeoff/<r>/order-lines` (large lane, parquet, 200000 synthetic order lines with columns `day` date, `region` string, `product` string, `amount` number, aggregate `SELECT day, sum(amount) AS amount FROM data GROUP BY day ORDER BY day`); one shared stat chart `bakeoff/total-revenue`; one dashboard `bakeoff/<r>` with controls `period` (date-range on `month`, default last 12 months), `days` (date-range on `day`), `region` (multi select); folders `charts/bakeoff`, `charts/bakeoff/<r>`, `dashboards/bakeoff`. The aggregate's output column is named `amount` so every renderer's spec binds only declared column names (the server's Plotly check requires it).

- [ ] **Step 1: Write the failing tests**

In `tests/test_sample_bucket.py`, inside `test_every_chart_validates_and_matches_its_data`, replace

```python
        if doc["data"]["format"] == "json":
            rows = json.loads(data_path.read_text(encoding="utf-8"))
            assert len(rows) == doc["data"]["rows"]
            declared = {c["name"] for c in doc["data"]["columns"]}
            assert set(rows[0]) == declared
```

with

```python
        declared = {c["name"] for c in doc["data"]["columns"]}
        if doc["data"]["format"] == "json":
            rows = json.loads(data_path.read_text(encoding="utf-8"))
            assert len(rows) == doc["data"]["rows"]
            assert set(rows[0]) == declared
        else:
            import pyarrow.parquet as pq

            meta = pq.read_metadata(data_path)
            assert meta.num_rows == doc["data"]["rows"]
            assert set(pq.read_schema(data_path).names) == declared
```

and append:

```python


RENDERERS = ("vega-lite", "plotly", "echarts")


def test_bakeoff_samples_exist_for_every_renderer():
    for renderer in RENDERERS:
        for chart in ("time-series", "grouped-bar", "order-lines"):
            path = ROOT / "charts" / "bakeoff" / renderer / chart / "chart.json"
            assert path.is_file(), path
            doc = json.loads(path.read_text(encoding="utf-8"))
            assert doc["renderer"] == renderer
            if chart == "order-lines":
                assert doc["data"]["lane"] == "large" and doc["data"]["format"] == "parquet"
                assert doc["aggregate"].startswith("SELECT day, sum(amount) AS amount")
            else:
                assert doc["data"]["lane"] == "small"
        dashboard = json.loads((ROOT / "dashboards" / "bakeoff" / f"{renderer}.json").read_text(encoding="utf-8"))
        chart_ids = [t["chart"] for t in dashboard["layout"] if "chart" in t]
        assert chart_ids == [
            f"bakeoff/{renderer}/time-series",
            "bakeoff/total-revenue",
            f"bakeoff/{renderer}/grouped-bar",
            f"bakeoff/{renderer}/order-lines",
        ]
        assert [c["id"] for c in dashboard["controls"]] == ["period", "days", "region"]
    stat = json.loads((ROOT / "charts" / "bakeoff" / "total-revenue" / "chart.json").read_text(encoding="utf-8"))
    assert stat["renderer"] == "stat"


def test_parquet_sample_is_under_the_large_lane_cap():
    for renderer in RENDERERS:
        path = ROOT / "charts" / "bakeoff" / renderer / "order-lines" / "data.parquet"
        assert path.stat().st_size < 209715200
```

- [ ] **Step 2: Add pyarrow and run the tests to see them fail**

In `pyproject.toml`, change the `dev` extra to:

```toml
dev = [
  "pytest>=8",
  "pytest-asyncio>=0.24",
  "httpx>=0.27",
  "moto[s3]>=5",
  "pyarrow>=17",
]
```

Append to `.gitattributes`:

```
*.parquet binary
```

Run from the repo root: `.venv/Scripts/python -m pip install -e ".[dev]"` then `.venv/Scripts/python -m pytest tests/test_sample_bucket.py -v`
Expected: `test_bakeoff_samples_exist_for_every_renderer` and `test_parquet_sample_is_under_the_large_lane_cap` FAIL (files missing). The others pass.

- [ ] **Step 3: Extend the generator**

In `sample-bucket/generate.py`, replace the imports at the top with:

```python
import json
import random
from datetime import date, timedelta
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
```

Add after the `COLUMNS` list:

```python
RENDERERS = ["vega-lite", "plotly", "echarts"]
PRODUCTS = ["alpha", "bravo", "charlie", "delta", "echo", "foxtrot"]
ORDER_LINES = 200_000
QUARTER_COLUMNS = [
    {"name": "quarter", "type": "string"},
    {"name": "region", "type": "string"},
    {"name": "orders", "type": "integer"},
]
LINE_COLUMNS = [
    {"name": "day", "type": "date"},
    {"name": "region", "type": "string"},
    {"name": "product", "type": "string"},
    {"name": "amount", "type": "number"},
]
LINE_AGGREGATE = "SELECT day, sum(amount) AS amount FROM data GROUP BY day ORDER BY day"
```

Replace the `chart_doc` function with this generalized version (existing callers keep working):

```python
def chart_doc(chart_id, title, description, renderer, spec, data_rows, data_bytes, source=None,
              columns=COLUMNS, fmt="json", lane="small", aggregate=None, tags=("sales", "sample")):
    doc = {
        "schema_version": 1,
        "id": chart_id,
        "title": title,
        "description": description,
        "tags": list(tags),
        "author": AUTHOR,
        "created_at": STAMP,
        "updated_at": STAMP,
        "renderer": renderer,
        "spec": spec,
        "data": {"format": fmt, "lane": lane, "rows": data_rows, "bytes": data_bytes, "columns": columns},
        "aggregate": aggregate,
    }
    if source:
        doc["source"] = source
    return doc
```

Add these functions before `main()`:

```python
def quarterly(data: list[dict]) -> list[dict]:
    totals: dict[tuple[str, str], int] = {}
    for r in data:
        year, month = r["month"][:4], int(r["month"][5:7])
        quarter = f"{year}-Q{(month - 1) // 3 + 1}"
        totals[(quarter, r["region"])] = totals.get((quarter, r["region"]), 0) + r["orders"]
    return [{"quarter": q, "region": region, "orders": n} for (q, region), n in sorted(totals.items())]


def order_lines() -> pa.Table:
    rng = random.Random(20260922)
    start = date(2024, 1, 1)
    lines = []
    for _ in range(ORDER_LINES):
        day = start + timedelta(days=rng.randrange(730))
        region = rng.choice(REGIONS)
        product = rng.choice(PRODUCTS)
        amount = round(rng.lognormvariate(4.5, 0.6), 2)
        lines.append((day, region, product, amount))
    lines.sort(key=lambda t: (t[0], t[1], t[2], t[3]))
    return pa.table({
        "day": pa.array([t[0] for t in lines], pa.date32()),
        "region": pa.array([t[1] for t in lines], pa.string()),
        "product": pa.array([t[2] for t in lines], pa.string()),
        "amount": pa.array([t[3] for t in lines], pa.float64()),
    })


def write_parquet(path: Path, table: pa.Table) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(table, path, compression="snappy")
    return path.stat().st_size


def time_series_spec(renderer: str) -> dict:
    if renderer == "vega-lite":
        return {
            "$schema": "https://vega.github.io/schema/vega-lite/v5.json",
            "data": {"name": "data"},
            "width": "container",
            "height": "container",
            "mark": {"type": "line", "point": True},
            "encoding": {
                "x": {"field": "month", "type": "temporal", "title": "Month"},
                "y": {"field": "revenue", "type": "quantitative", "title": "Revenue"},
                "color": {"field": "region", "type": "nominal", "title": "Region"},
                "tooltip": [
                    {"field": "month", "type": "temporal", "title": "Month"},
                    {"field": "region", "type": "nominal", "title": "Region"},
                    {"field": "revenue", "type": "quantitative", "title": "Revenue", "format": ",.0f"},
                ],
            },
        }
    if renderer == "plotly":
        return {
            "traces": [{"type": "scatter", "mode": "lines+markers", "split": "region",
                        "x": {"column": "month"}, "y": {"column": "revenue"}}],
            "layout": {"xaxis": {"title": {"text": "Month"}}, "yaxis": {"title": {"text": "Revenue"}},
                       "legend": {"title": {"text": "Region"}}, "hovermode": "x unified"},
        }
    return {
        "xAxis": {"type": "time", "name": "Month"},
        "yAxis": {"type": "value", "name": "Revenue"},
        "legend": {},
        "tooltip": {"trigger": "axis", "renderMode": "richText"},
        "series": [{"type": "line", "split": "region", "showSymbol": True, "encode": {"x": "month", "y": "revenue"}}],
    }


def grouped_bar_spec(renderer: str) -> dict:
    if renderer == "vega-lite":
        return {
            "$schema": "https://vega.github.io/schema/vega-lite/v5.json",
            "data": {"name": "data"},
            "width": "container",
            "height": "container",
            "mark": "bar",
            "encoding": {
                "x": {"field": "quarter", "type": "ordinal", "title": "Quarter"},
                "xOffset": {"field": "region"},
                "y": {"field": "orders", "type": "quantitative", "title": "Orders"},
                "color": {"field": "region", "type": "nominal", "title": "Region"},
                "tooltip": [
                    {"field": "quarter", "type": "ordinal"},
                    {"field": "region", "type": "nominal"},
                    {"field": "orders", "type": "quantitative", "format": ","},
                ],
            },
        }
    if renderer == "plotly":
        return {
            "traces": [{"type": "bar", "split": "region", "x": {"column": "quarter"}, "y": {"column": "orders"}}],
            "layout": {"barmode": "group", "xaxis": {"title": {"text": "Quarter"}}, "yaxis": {"title": {"text": "Orders"}}},
        }
    return {
        "xAxis": {"type": "category", "name": "Quarter"},
        "yAxis": {"type": "value", "name": "Orders"},
        "legend": {},
        "tooltip": {"trigger": "axis", "renderMode": "richText"},
        "series": [{"type": "bar", "split": "region", "encode": {"x": "quarter", "y": "orders"}}],
    }


def order_lines_spec(renderer: str) -> dict:
    if renderer == "vega-lite":
        return {
            "$schema": "https://vega.github.io/schema/vega-lite/v5.json",
            "data": {"name": "data"},
            "width": "container",
            "height": "container",
            "mark": "bar",
            "encoding": {
                "x": {"field": "day", "type": "temporal", "title": "Day"},
                "y": {"field": "amount", "type": "quantitative", "title": "Amount"},
                "tooltip": [
                    {"field": "day", "type": "temporal"},
                    {"field": "amount", "type": "quantitative", "format": ",.0f"},
                ],
            },
        }
    if renderer == "plotly":
        return {
            "traces": [{"type": "bar", "x": {"column": "day"}, "y": {"column": "amount"}}],
            "layout": {"xaxis": {"title": {"text": "Day"}}, "yaxis": {"title": {"text": "Amount"}}},
        }
    return {
        "xAxis": {"type": "time", "name": "Day"},
        "yAxis": {"type": "value", "name": "Amount"},
        "tooltip": {"trigger": "axis", "renderMode": "richText"},
        "series": [{"type": "bar", "encode": {"x": "day", "y": "amount"}}],
    }


def renderer_title(renderer: str) -> str:
    return {"vega-lite": "Vega-Lite", "plotly": "Plotly", "echarts": "ECharts"}[renderer]


def write_bakeoff(data: list[dict]) -> None:
    charts = ROOT / "charts" / "bakeoff"
    dashboards = ROOT / "dashboards" / "bakeoff"
    quarters = quarterly(data)
    lines = order_lines()

    write_json(charts / "_folder.json", {"schema_version": 1, "title": "Bake-off", "description": "The same four charts written for each renderer.", "order": 20})
    write_json(dashboards / "_folder.json", {"schema_version": 1, "title": "Bake-off", "description": "One dashboard per renderer. Pick a winner.", "order": 20})

    n = write_json(charts / "total-revenue" / "data.json", data)
    write_json(charts / "total-revenue" / "chart.json", chart_doc(
        "bakeoff/total-revenue", "Total revenue", "Sum of revenue over the selected period, with total orders.",
        "stat", {"value": "revenue", "agg": "sum", "format": "$,.0f", "compare": {"column": "orders", "agg": "sum"}},
        len(data), n, tags=("bakeoff", "sample"),
    ))

    for renderer in RENDERERS:
        folder = charts / renderer
        write_json(folder / "_folder.json", {"schema_version": 1, "title": renderer_title(renderer)})

        n = write_json(folder / "time-series" / "data.json", data)
        write_json(folder / "time-series" / "chart.json", chart_doc(
            f"bakeoff/{renderer}/time-series", f"Revenue by region, monthly ({renderer_title(renderer)})",
            "Monthly revenue per region. Filter with the Period and Region controls.",
            renderer, time_series_spec(renderer), len(data), n, tags=("bakeoff", "sample"),
        ))

        n = write_json(folder / "grouped-bar" / "data.json", quarters)
        write_json(folder / "grouped-bar" / "chart.json", chart_doc(
            f"bakeoff/{renderer}/grouped-bar", f"Orders by region, quarterly ({renderer_title(renderer)})",
            "Quarterly orders per region. Filter with the Region control.",
            renderer, grouped_bar_spec(renderer), len(quarters), n, columns=QUARTER_COLUMNS, tags=("bakeoff", "sample"),
        ))

        n = write_parquet(folder / "order-lines" / "data.parquet", lines)
        write_json(folder / "order-lines" / "chart.json", chart_doc(
            f"bakeoff/{renderer}/order-lines", f"Order amount per day ({renderer_title(renderer)})",
            f"{ORDER_LINES:,} synthetic order lines aggregated per day in the browser with DuckDB. Filter with the Days and Region controls.",
            renderer, order_lines_spec(renderer), lines.num_rows, n,
            columns=LINE_COLUMNS, fmt="parquet", lane="large", aggregate=LINE_AGGREGATE, tags=("bakeoff", "sample"),
        ))

        write_json(dashboards / f"{renderer}.json", {
            "schema_version": 1,
            "id": f"bakeoff/{renderer}",
            "title": f"Bake-off: {renderer_title(renderer)}",
            "description": f"The four bake-off charts rendered with {renderer_title(renderer)}. Synthetic data.",
            "tags": ["bakeoff", "sample"],
            "author": AUTHOR,
            "created_at": STAMP,
            "updated_at": STAMP,
            "controls": [
                {"id": "period", "type": "date-range", "label": "Period", "column": "month", "default": {"last": "12m"}},
                {"id": "days", "type": "date-range", "label": "Days", "column": "day", "default": None},
                {"id": "region", "type": "select", "label": "Region", "column": "region", "multi": True, "default": None},
            ],
            "layout": [
                {"chart": f"bakeoff/{renderer}/time-series", "w": 8, "h": 4},
                {"chart": "bakeoff/total-revenue", "w": 4, "h": 2},
                {"chart": f"bakeoff/{renderer}/grouped-bar", "w": 6, "h": 4},
                {"chart": f"bakeoff/{renderer}/order-lines", "w": 6, "h": 4},
                {"markdown": f"Rendered with **{renderer_title(renderer)}**. Same data and controls on every bake-off dashboard.", "w": 12, "h": 1},
            ],
        })
```

At the end of `main()`, after the existing `write_json(dashboards / "overview.json", {...})` call, add:

```python
    write_bakeoff(data)
```

- [ ] **Step 4: Generate and test**

Run from the repo root: `.venv/Scripts/python sample-bucket/generate.py` then `.venv/Scripts/python -m pytest -v`
Expected: the bake-off folders appear; all tests pass. Check the parquet size: `ls -la sample-bucket/viz/charts/bakeoff/vega-lite/order-lines/` should show `data.parquet` of a few MB. Run the generator a second time and `git status`: no files change on the second run (determinism).

- [ ] **Step 5: See it in the browser**

Run from the repo root in the background: `.venv/Scripts/viz-server`; from `web/`: `npm run dev`. Open `http://127.0.0.1:5173/d/bakeoff/vega-lite`, `/d/bakeoff/plotly`, `/d/bakeoff/echarts`. Expected: four tiles each, the large-lane tile renders after a short DuckDB load, no error cards. If a tile shows an error card, fix the sample spec (not the sanitizer) and report what changed. Stop both servers.

- [ ] **Step 6: Commit**

```bash
git add sample-bucket/generate.py sample-bucket/viz tests/test_sample_bucket.py pyproject.toml .gitattributes
git commit -m "feat(sample): bake-off charts and dashboards per renderer, parquet large-lane sample" -m "Adds pyarrow>=17 to the dev extra for writing the parquet sample.

Co-Authored-By: <model> <noreply@anthropic.com>
Claude-Session: <session url>"
```

(The body line about pyarrow satisfies `CLAUDE.md` rule 7. Keep the blank line between the body and the trailers exactly as shown.)

---

### Task 16: Playwright smoke test

**Files:**
- Create: `web/playwright.config.ts`, `web/e2e/global-setup.ts`, `web/e2e/smoke.spec.ts`
- Modify: `.gitignore` (append `web/test-results/` and `web/playwright-report/`)

**Interfaces:**
- Produces: `npm run e2e` from `web/`, which builds the bundle, starts `viz-server` against `sample-bucket/` with `VIZ_WEB_DIST` pointing at `web/dist`, and runs the smoke test in headless Chromium. The test proves, per renderer: four tiles reach `data-state="ready"`, no error card, the Region control filters the time-series tile (its `data-rows` drops) and rewrites the URL, every network request stays on `http://127.0.0.1:8000/`, no request fails, and no console error or CSP violation appears.

- [ ] **Step 1: Install the browser**

Run from `web/`: `npx playwright install chromium`
Expected: Chromium downloads once.

- [ ] **Step 2: Write the config, setup and test**

`web/playwright.config.ts`:

```ts
import { defineConfig } from '@playwright/test';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const here = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(here, '..');
const venvBin = path.join(root, '.venv', process.platform === 'win32' ? 'Scripts' : 'bin');
const server = path.join(venvBin, process.platform === 'win32' ? 'viz-server.exe' : 'viz-server');

export default defineConfig({
  testDir: './e2e',
  timeout: 120_000,
  retries: 0,
  workers: 1,
  reporter: 'list',
  globalSetup: './e2e/global-setup.ts',
  use: { baseURL: 'http://127.0.0.1:8000', headless: true },
  webServer: {
    command: `"${server}"`,
    url: 'http://127.0.0.1:8000/api/health',
    cwd: root,
    reuseExistingServer: false,
    timeout: 60_000,
    env: {
      ...(process.env as Record<string, string>),
      VIZ_STORAGE: 'local',
      VIZ_LOCAL_DIR: path.join(root, 'sample-bucket'),
      VIZ_WEB_DIST: path.join(root, 'web', 'dist'),
      VIZ_ALLOWED_HOSTS: '127.0.0.1,localhost',
    },
  },
  projects: [{ name: 'chromium', use: { browserName: 'chromium' } }],
});
```

`web/e2e/global-setup.ts`:

```ts
import { execSync } from 'node:child_process';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

export default function globalSetup(): void {
  const web = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
  execSync('npm run build', { cwd: web, stdio: 'inherit', shell: process.platform === 'win32' ? 'cmd.exe' : '/bin/sh' });
}
```

`web/e2e/smoke.spec.ts`:

```ts
import { expect, test, type Page } from '@playwright/test';

const RENDERERS = ['vega-lite', 'plotly', 'echarts'] as const;
const ORIGIN = 'http://127.0.0.1:8000/';

function watch(page: Page) {
  const consoleErrors: string[] = [];
  const foreign: string[] = [];
  const failed: string[] = [];
  page.on('console', (m) => {
    if (m.type() === 'error') consoleErrors.push(m.text());
  });
  page.on('pageerror', (e) => consoleErrors.push(String(e)));
  page.on('request', (r) => {
    if (!r.url().startsWith(ORIGIN)) foreign.push(r.url());
  });
  page.on('requestfailed', (r) => failed.push(`${r.url()} ${r.failure()?.errorText ?? ''}`));
  return { consoleErrors, foreign, failed };
}

for (const renderer of RENDERERS) {
  test(`bake-off dashboard renders with ${renderer} and the Region control filters it`, async ({ page }) => {
    const log = watch(page);
    await page.goto(`/d/bakeoff/${renderer}`);

    await expect(page.locator('[data-tile]')).toHaveCount(4);
    await expect(page.locator('[data-tile][data-state="ready"]')).toHaveCount(4, { timeout: 90_000 });
    await expect(page.locator('.error-card')).toHaveCount(0);

    const timeSeries = page.locator(`[data-tile="bakeoff/${renderer}/time-series"]`);
    const before = Number(await timeSeries.getAttribute('data-rows'));
    expect(before).toBeGreaterThan(0);
    const largeBefore = Number(await page.locator(`[data-tile="bakeoff/${renderer}/order-lines"]`).getAttribute('data-rows'));
    expect(largeBefore).toBeGreaterThan(0);

    await page.getByLabel('Region', { exact: true }).selectOption(['EMEA']);
    await expect(page).toHaveURL(/region=EMEA/);
    await expect.poll(async () => Number(await timeSeries.getAttribute('data-rows'))).toBeLessThan(before);
    await expect(page.locator('[data-tile][data-state="ready"]')).toHaveCount(4, { timeout: 60_000 });
    await expect(page.locator('.error-card')).toHaveCount(0);
    await expect(page.locator(`[data-tile="bakeoff/${renderer}/time-series"] canvas, [data-tile="bakeoff/${renderer}/time-series"] svg`).first()).toBeVisible();

    expect(log.foreign, 'every request stays on the site origin').toEqual([]);
    expect(log.failed, 'no request failed').toEqual([]);
    expect(log.consoleErrors.filter((m) => /Content Security Policy|Refused to/i.test(m)), 'no CSP violations').toEqual([]);
    expect(log.consoleErrors, 'no console errors').toEqual([]);
  });
}

test('the single chart page renders a large-lane chart and shows its columns', async ({ page }) => {
  const log = watch(page);
  await page.goto('/c/bakeoff/vega-lite/order-lines');
  await expect(page.locator('[data-tile][data-state="ready"]')).toHaveCount(1, { timeout: 90_000 });
  await expect(page.locator('.error-card')).toHaveCount(0);
  await expect(page.getByRole('cell', { name: 'amount' })).toBeVisible();
  expect(log.foreign).toEqual([]);
  expect(log.consoleErrors).toEqual([]);
});

test('a missing dashboard shows one error card and the header still renders', async ({ page }) => {
  await page.goto('/d/bakeoff/nope');
  await expect(page.locator('.error-card')).toHaveCount(1);
  await expect(page.getByRole('heading', { name: 'viz-site' })).toBeVisible();
});
```

Append to `.gitignore`:

```
web/test-results/
web/playwright-report/
```

- [ ] **Step 3: Run it**

Run from `web/`: `npm run typecheck` then `npm run e2e`
Expected: typecheck clean; 5 tests pass. Common failures and what they mean:
- `[data-state="ready"]` count stays at 3 and the `order-lines` tile shows `query failed`: read the error text. `could not start DuckDB` means the worker or wasm asset did not load (check the `/assets` names in `web/dist`). A `json_serialize_sql` error means the probe did not catch it; report the exact message.
- A console error mentioning `Content Security Policy`: some library tried to inline a script, load a URL or `eval`. Report the message verbatim; do not relax the CSP.
- Plotly logging `WebGL` warnings is fine (warnings are not errors).

- [ ] **Step 4: Run the unit suites once more and commit**

Run from `web/`: `npm test`. Run from the repo root: `.venv/Scripts/python -m pytest`.
Expected: all pass.

```bash
git add web/playwright.config.ts web/e2e/global-setup.ts web/e2e/smoke.spec.ts .gitignore
git commit -m "test(web): Playwright smoke test over the three bake-off dashboards" -m "Co-Authored-By: <model> <noreply@anthropic.com>
Claude-Session: <session url>"
```

---

### Task 17: Bake-off scorecard and README

**Files:**
- Create: `web/scripts/chunk-sizes.mjs`, `web/scripts/spec-lines.mjs`, `docs/superpowers/specs/2026-09-22-bake-off-scorecard.md`
- Modify: `README.md` (append a "Front end" section)

**Interfaces:**
- Produces: two measurement scripts and the scorecard. The scorecard holds the measured numbers and leaves the user's columns blank. The user reviews the three dashboards, fills in the blanks, and picks a winner; that decision drives Plan 3b (the skill's authoring guide) and the removal of the two losing adapters, their samples and their enum values.

- [ ] **Step 1: Write the scripts**

`web/scripts/chunk-sizes.mjs`:

```js
// Prints the size of each renderer's lazy chunk and of the DuckDB assets in web/dist.
import { readdirSync, statSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const assets = join(dirname(fileURLToPath(import.meta.url)), '..', 'dist', 'assets');
const files = readdirSync(assets)
  .map((name) => ({ name, bytes: statSync(join(assets, name)).size }))
  .sort((a, b) => b.bytes - a.bytes);

const groups = {
  'vega-lite': /^renderer-vega-/,
  plotly: /^renderer-plotly-/,
  echarts: /^renderer-echarts-/,
  duckdb: /^duckdb-.*\.js$|worker.*\.js$|\.wasm$/,
  main: /^index-/,
};

const kib = (n) => `${Math.round(n / 1024).toLocaleString('en-US')} KiB`;
console.log('group\tsize');
for (const [label, re] of Object.entries(groups)) {
  const total = files.filter((f) => re.test(f.name)).reduce((s, f) => s + f.bytes, 0);
  console.log(`${label}\t${kib(total)}`);
}
console.log('\nfile\tsize');
for (const f of files) console.log(`${f.name}\t${kib(f.bytes)}`);
```

`web/scripts/spec-lines.mjs`:

```js
// Prints, per renderer, the pretty-printed line count of the bake-off specs and
// the number of sanitizer rules, for the scorecard.
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const web = join(dirname(fileURLToPath(import.meta.url)), '..');
const bucket = join(web, '..', 'sample-bucket', 'viz', 'charts', 'bakeoff');
const renderers = { 'vega-lite': 'vegaLiteSanitize.ts', plotly: 'plotlySanitize.ts', echarts: 'echartsSanitize.ts' };

function specLines(renderer, chart) {
  const doc = JSON.parse(readFileSync(join(bucket, renderer, chart, 'chart.json'), 'utf8'));
  return JSON.stringify(doc.spec, null, 2).split('\n').length;
}

function ruleCount(file) {
  const src = readFileSync(join(web, 'src', 'renderers', file), 'utf8');
  const block = src.slice(src.indexOf('RULES: readonly string[] = ['), src.indexOf('];'));
  return block.split('\n').filter((line) => /^\s*'/.test(line)).length;
}

console.log('renderer\ttime-series lines\tgrouped-bar lines\torder-lines lines\tsanitizer rules');
for (const [renderer, file] of Object.entries(renderers)) {
  console.log(`${renderer}\t${specLines(renderer, 'time-series')}\t${specLines(renderer, 'grouped-bar')}\t${specLines(renderer, 'order-lines')}\t${ruleCount(file)}`);
}
```

- [ ] **Step 2: Measure**

Run from `web/`: `npm run build`, then `node scripts/chunk-sizes.mjs`, then `node scripts/spec-lines.mjs`, then `npm run e2e`.
Expected: three tables of numbers and 5 passing e2e tests. Copy the numbers into the scorecard in the next step; do not type them from memory.

- [ ] **Step 3: Write the scorecard**

`docs/superpowers/specs/2026-09-22-bake-off-scorecard.md` (replace every `<n>` with the measured value and `<pass/fail>` with the e2e result):

```markdown
# Renderer bake-off scorecard

Spec: `2026-09-22-viz-site-design.md` section 5.2 (bake-off) and 12.3 (renderer
attack surface is a scored criterion). Measured on 2026-09-22 from the Plan 2
build. Blank columns are for the reviewer.

## How to review

1. From the repo root: `cd web && npm run build && cd ..` then
   `VIZ_WEB_DIST=web/dist .venv/Scripts/viz-server`.
2. Open `http://127.0.0.1:8000/d/bakeoff/vega-lite`, `/d/bakeoff/plotly` and
   `/d/bakeoff/echarts`. Each has the same four tiles: a monthly time series,
   a stat tile, a quarterly grouped bar, and a 200,000-row parquet chart
   aggregated in the browser.
3. Use the Period, Days and Region controls on each. Hover for tooltips.
   Resize the window.
4. Open one chart from each dashboard on its own page (`/c/bakeoff/<renderer>/time-series`).
5. Score 1 (poor) to 5 (excellent) in the blank columns, then write the
   decision at the bottom.

## Measured

| Renderer | Lazy chunk (KiB) | Sanitizer rules | time-series spec lines | grouped-bar spec lines | order-lines spec lines | Smoke test |
|---|---|---|---|---|---|---|
| vega-lite | <n> | <n> | <n> | <n> | <n> | <pass/fail> |
| plotly | <n> | <n> | <n> | <n> | <n> | <pass/fail> |
| echarts | <n> | <n> | <n> | <n> | <n> | <pass/fail> |

Shared: DuckDB assets <n> KiB (wasm + worker + glue), main bundle <n> KiB.

Notes on the measurements:

- "Lazy chunk" is the renderer library plus its adapter as Vite emitted it; it
  loads only when a page contains a chart with that renderer.
- "Sanitizer rules" counts the entries in each sanitizer's `RULES` list, which
  is the list of things the adapter has to refuse or rewrite to be safe under
  the site CSP. Fewer rules with the same guarantees means a smaller attack
  surface to maintain.
- "Spec lines" is the pretty-printed size of the same chart written for each
  renderer: a rough proxy for authoring ergonomics for the publishing skill.
- Grouping: Vega-Lite groups by an encoding (`color`); Plotly and ECharts need
  the `split` convention this plan added to their adapters.

## Reviewer

| Renderer | Visual quality (1-5) | Tooltips and hover (1-5) | Controls feel responsive (1-5) | Resize behaviour (1-5) | Notes |
|---|---|---|---|---|---|
| vega-lite | | | | | |
| plotly | | | | | |
| echarts | | | | | |

## Decision

Winner: _(fill in)_

Reason: _(fill in)_

Follow-ups after the decision: Plan 3b writes the skill's authoring guide for
the winner; a cleanup task removes the two losing adapters, their sanitizers,
their sample folders, their dashboards, their manual chunks in
`web/vite.config.ts`, and their values from the `renderer` enum in
`schemas/chart.schema.json` and `viz/schemas.py`.
```

- [ ] **Step 4: Document the front end in the README**

Append to `README.md`:

```markdown

## Front end

The viewer is a Vite + React + TypeScript app in `web/`. Node 24 and npm are
required. From `web/`:

    npm install
    npm run dev          # Vite on http://127.0.0.1:5173, proxies /api to the server on :8000
    npm run build        # writes web/dist; serve it with VIZ_WEB_DIST=web/dist viz-server
    npm test             # vitest unit tests
    npm run typecheck
    npm run e2e          # Playwright smoke test: builds, starts viz-server, drives Chromium

Every renderer library, the DuckDB-WASM worker and its wasm are bundled and
served from the site. Nothing loads from a CDN. Chart specs from the bucket are
sanitized before they are mounted; see `web/src/renderers/*Sanitize.ts` and
spec section 12.3. The bake-off between Vega-Lite, Plotly and ECharts is scored
in `docs/superpowers/specs/2026-09-22-bake-off-scorecard.md`.
```

- [ ] **Step 5: Commit**

```bash
git add web/scripts/chunk-sizes.mjs web/scripts/spec-lines.mjs docs/superpowers/specs/2026-09-22-bake-off-scorecard.md README.md
git commit -m "docs: bake-off scorecard with measured bundle, rule and spec sizes; front-end README" -m "Co-Authored-By: <model> <noreply@anthropic.com>
Claude-Session: <session url>"
```

---

## Self-review

**Spec coverage (sections this plan owns):**

| Spec item | Task |
|---|---|
| 5.2 Vite + React + TypeScript built to `web/dist`, served by FastAPI | 1 |
| 5.2 screens: dashboards tree, dashboard page, charts library, single chart page | 11, 12, 13 |
| 5.2 data flow: dashboard then charts in parallel; small lane JSON in memory; large lane parquet in DuckDB loaded lazily | 10, 12, 14 |
| 5.2 controls: filter set; small lane in TypeScript; large lane as a WHERE on `data` before the aggregate | 4, 14 |
| 5.2 adapter interface `mount`/`update`; three bake-off adapters; `stat` as a React component; Plotly column-binding convention | 6, 7, 8, 9 |
| 5.2 bake-off samples: four charts per renderer (time series + date-range, grouped bar + multi-select, stat + compare, large-lane parquet + aggregate) and one dashboard per renderer | 15 |
| 5.2 error handling: missing chart, malformed JSON, schema failure, oversized data, renderer exception, DuckDB failure, each a tile-level card, page survives | 2, 10, 14 |
| 4.2 `renderer` enum, `spec` refers to dataset `data`, `data.columns` types drive widgets, `aggregate` over `data` | 2, 4, 12, 14 |
| 4.3 controls bind by column, unfiltered when a chart lacks the column, select options are the union across charts, 12-column flow grid, markdown tiles, error cards for bad tiles | 4, 12 |
| 8 component tests for filter logic and each adapter; one Playwright smoke test that changes a control and asserts a chart changes | 4, 7, 8, 9, 16 |
| 12.3 one Markdown component, raw HTML off, http/https/mailto only, `rel="noopener noreferrer nofollow"`, same-origin images | 3 |
| 12.3 everything bundled by Vite, nothing from a CDN | 1, 14, 16 |
| 12.3 ECharts rules (richText, deleted keys, no `<` in formatters, strings never functions, canvas) | 8 |
| 12.3 Vega-Lite rules (null loader, actions off, canvas, interpreter, reject url/values/href/image/usermeta) | 7 |
| 12.3 Plotly rules (cloud/editor off, geo/map rejected, images and map layouts deleted, `<` escaped, strict walk ignoring `__proto__`/`constructor`) | 9 |
| 12.3 renderer attack surface as a scored criterion | 17 |
| 12.3 DuckDB init settings and `lock_configuration`, single SELECT check with `json_serialize_sql`, `LIMIT 50000`, wall-clock budget, worker recreated on timeout | 14 |
| 12.3 control values never interpolated: Arrow temp tables, parameterized bounds, `data` as a CTE, control columns must be declared, URL values validated and typed | 5, 14 |
| 12.3 select cap 500 with text fallback | 4, 5, 12 |
| 12.3 no `dangerouslySetInnerHTML` outside Markdown (none at all here) | 3 |
| 12.6 sample bucket synthetic | 15 |

Deliberate deviations, recorded so no executor "fixes" them:

- Spec 12.3 says "disable the HTTP and S3 filesystems". DuckDB-WASM implements
  those natively rather than through the `httpfs` extension, and the safe
  handle is the CSP (`connect-src 'self'`, inherited by the worker) plus never
  registering a URL. The plan also materializes the parquet buffer into a table
  and drops the file, so no file is reachable when a chart's SQL runs.
  `enable_external_access=false` is not set in the browser because it would
  block reading the registered buffer for the next chart on the same page; it
  stays a CLI-side setting (spec 12.4, Plan 3a).
- `json_serialize_sql` is probed at init. The parquet extension is statically
  linked into duckdb-wasm; the json extension is linked only in some builds.
  If it is missing, the pure syntax check and the `SELECT * FROM (...)`
  wrapper remain, and Plan 3a's `viz validate` runs the same `json_serialize_sql`
  check in native DuckDB at publish time. Task 16 surfaces which case applies.
- Vega-Lite `values` is rejected at any depth as the spec says, which also
  forbids `axis.values`; sample specs avoid it.

Gaps deliberately left for later plans: `viz publish` and `viz validate`
(Plan 3a), the skill (Plan 3b), CI, Dockerfile and Helm (Plan 4). Removal of
the losing renderers happens after the user fills in the scorecard.

**Placeholder scan:** none. Task 10's large-lane error is a real behavior with
a real test that Task 14 replaces with the real path and a real test.

**Type consistency:** `Adapter` (Task 7) is used with the same three methods in
Tasks 8, 9, 10. `Filter`/`FilterValue` (Task 4) are consumed unchanged in Tasks
5, 10, 12, 14. `SelectOptions` shape `{ options, tooMany }` matches between
Tasks 4, 5, 12. `describeError` (Task 10) handles `DuckDbError` by name so Task
14 needs no import into the tile. `queryLargeLane(chartId, aggregate, columns,
filters)` in Task 14 matches the call and mock in the Task 14 tile test. The
`data-tile`/`data-state`/`data-rows` attributes set in Task 10 are the ones the
Task 12 tests and the Task 16 smoke test read. The chart ids and control ids the
Task 16 smoke test uses are the ones Task 15 generates. `RULES` is exported by
every sanitizer (Tasks 7, 8, 9) and read by `RULE_COUNTS` (Task 10) and
`spec-lines.mjs` (Task 17).
