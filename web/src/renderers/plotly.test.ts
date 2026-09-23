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
