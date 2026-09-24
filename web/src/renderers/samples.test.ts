// Cross-checks every chart.json in the sample bucket against the browser's
// own sanitizers. This is what stops the server-side rules in viz/schemas.py
// and the client-side rules here from drifting apart: a spec the server
// accepts as valid must also be a spec the browser will render.
import { readdirSync, readFileSync, statSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';
import { parseStatSpec } from '../components/StatTile';
import { sanitizeSpec } from './index';

const CHARTS_ROOT = join(dirname(fileURLToPath(import.meta.url)), '../../../sample-bucket/viz/charts');

const SANITIZED_RENDERERS = new Set(['vega-lite', 'plotly', 'echarts']);

function findChartFiles(dir: string, out: string[] = []): string[] {
  for (const name of readdirSync(dir)) {
    const path = join(dir, name);
    if (statSync(path).isDirectory()) findChartFiles(path, out);
    else if (name === 'chart.json') out.push(path);
  }
  return out;
}

interface ChartDoc {
  id: string;
  renderer: string;
  spec: unknown;
  data: { columns: { name: string }[] };
}

function loadChart(path: string): ChartDoc {
  return JSON.parse(readFileSync(path, 'utf8')) as ChartDoc;
}

describe('sample bucket charts pass the browser sanitizers', () => {
  const files = findChartFiles(CHARTS_ROOT);

  it('found sample chart.json files to check', () => {
    expect(files.length).toBeGreaterThan(0);
  });

  for (const path of files) {
    const doc = loadChart(path);
    it(`${doc.id} (${doc.renderer})`, () => {
      if (SANITIZED_RENDERERS.has(doc.renderer)) {
        expect(() => sanitizeSpec(doc.renderer, doc.spec)).not.toThrow();
      } else if (doc.renderer === 'stat') {
        const columnNames = doc.data.columns.map((c) => c.name);
        expect(() => parseStatSpec(doc.spec, columnNames)).not.toThrow();
      } else {
        throw new Error(`unexpected renderer in sample bucket: ${doc.renderer}`);
      }
    });
  }
});
