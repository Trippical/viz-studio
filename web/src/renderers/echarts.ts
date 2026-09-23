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
