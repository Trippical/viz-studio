import { cleanup, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ApiError, DataTooLarge } from '../api/client';
import type { Chart } from '../api/types';
import type { Adapter } from '../renderers/adapter';
import { SanitizeError } from '../renderers/common';
import { ChartTile, describeError } from './ChartTile';

const mocks = vi.hoisted(() => ({
  fetchChart: vi.fn(),
  fetchRows: vi.fn(),
  adapter: {
    // Typed with explicit parameters (matching Adapter's mount/update) so
    // `.mock.calls[0][n]` below is not inferred against a zero-length tuple.
    mount: vi.fn(async (_el: HTMLElement, _spec: unknown, _rows: unknown[], _columns: unknown[]) => undefined),
    update: vi.fn(async (_rows: unknown[]) => undefined),
    destroy: vi.fn(),
  },
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

// vitest.config.ts does not set `test.globals`, so @testing-library/react's
// automatic afterEach cleanup (which checks for a global `afterEach`) never
// registers. Several cases here render more than once per file, so without
// explicit cleanup DOM nodes from earlier tests leak into later queries.
afterEach(cleanup);

function tile(id = 'sales/x') {
  return document.querySelector(`[data-tile="${id}"]`) as HTMLElement;
}

/** A fresh mock Adapter instance, so a test can tell one chart's adapter apart from another's. */
function mockAdapter(): Adapter {
  return { mount: vi.fn(async () => undefined), update: vi.fn(async () => undefined), destroy: vi.fn() };
}

/** A promise this test can resolve on its own schedule, to control when an in-flight mount settles. */
function deferred<T>(): { promise: Promise<T>; resolve: (value: T) => void } {
  let resolve: (value: T) => void = () => undefined;
  const promise = new Promise<T>((res) => {
    resolve = res;
  });
  return { promise, resolve };
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
    await waitFor(() => expect(tile('sales/bad').dataset.state).toBe('error'));
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

  it('drops a mount that finishes after the chart has already switched', async () => {
    const chartA = { ...chart, id: 'a' };
    const chartB = { ...chart, id: 'b' };
    mocks.fetchChart.mockImplementation(async (id: string) => (id === 'b' ? chartB : chartA));
    mocks.fetchRows.mockResolvedValue(rows);

    const first = mockAdapter();
    const second = mockAdapter();
    const firstMount = deferred<void>();
    (first.mount as ReturnType<typeof vi.fn>).mockReturnValue(firstMount.promise);
    mocks.getAdapter.mockReset();
    mocks.getAdapter.mockReturnValueOnce(first).mockReturnValueOnce(second);

    const { rerender } = render(<ChartTile chartId="a" filters={[]} />);
    await waitFor(() => expect(first.mount).toHaveBeenCalledTimes(1));

    // Switch charts while the first mount is still in flight. The chart doc
    // and rows for "b" load and commit (data-rows reflects them) well before
    // the stale first mount is allowed to resolve below.
    rerender(<ChartTile chartId="b" filters={[]} />);
    await waitFor(() => expect(tile('b').dataset.rows).toBe('2'));
    expect(second.mount).not.toHaveBeenCalled();

    firstMount.resolve();
    await waitFor(() => expect(first.destroy).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(second.mount).toHaveBeenCalledTimes(1));
    expect(second.mount).toHaveBeenCalledWith(expect.anything(), chartB.spec, rows, chartB.data.columns);
    expect(first.update).not.toHaveBeenCalled();
    await waitFor(() => expect(tile('b').dataset.state).toBe('ready'));
  });
});

describe('describeError', () => {
  it('maps every failure kind to a sentence', () => {
    expect(describeError(new ApiError(404, 'x'))).toBe('not found');
    expect(describeError(new ApiError(413, 'x'))).toBe('document too large');
    expect(describeError(new ApiError(500, 'x'))).toBe('request failed (500)');
    expect(describeError(new SanitizeError('k'))).toBe('spec rejected: k');
    const tooLarge = new DataTooLarge(20971521);
    expect(describeError(tooLarge)).toBe(tooLarge.message);
    expect(describeError(tooLarge)).toContain('20971521 bytes');
    const duck = new Error('boom');
    duck.name = 'DuckDbError';
    expect(describeError(duck)).toBe('query failed: boom');
    expect(describeError('?')).toBe('render failed: ?');
  });
});
