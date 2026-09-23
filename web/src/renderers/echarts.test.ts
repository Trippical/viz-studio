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
