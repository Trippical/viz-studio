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
  queryLargeLane: vi.fn(),
  distinctValues: vi.fn(),
}));

vi.mock('../api/client', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../api/client')>()),
  fetchChart: mocks.fetchChart,
  fetchRows: mocks.fetchRows,
}));
vi.mock('../renderers', () => ({ getAdapter: mocks.getAdapter }));
vi.mock('../data/duckdb', () => ({ queryLargeLane: mocks.queryLargeLane, distinctValues: mocks.distinctValues }));

const chart: Chart = {
  schema_version: 1,
  id: 'sales/x',
  title: 'Revenue',
  renderer: 'vega-lite',
  spec: { data: { name: 'data' }, mark: 'line' },
  data: {
    format: 'json',
    file: 'data.0123456789abcdef.json',
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
  mocks.queryLargeLane.mockReset();
  mocks.distinctValues.mockReset().mockResolvedValue([]);
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

  it('mounts only the document that matches its chart id when the chart switches while idle', async () => {
    const chartY = { ...chart, id: 'sales/y', spec: { data: { name: 'data' }, mark: 'bar' } };
    mocks.fetchChart.mockImplementation(async (id: string) => (id === 'sales/y' ? chartY : chart));
    mocks.fetchRows.mockResolvedValue(rows);

    const first = mockAdapter();
    const second = mockAdapter();
    mocks.getAdapter.mockReset();
    mocks.getAdapter.mockReturnValueOnce(first).mockReturnValueOnce(second);

    // Chart "sales/x" fully mounts and goes idle before the switch, so the
    // effect that mounts it is not in flight when chartId changes below.
    const { rerender } = render(<ChartTile chartId="sales/x" filters={[]} />);
    await waitFor(() => expect(tile('sales/x').dataset.state).toBe('ready'));
    expect(first.mount).toHaveBeenCalledTimes(1);
    expect(first.mount).toHaveBeenCalledWith(expect.anything(), chart.spec, rows, chart.data.columns);

    rerender(<ChartTile chartId="sales/y" filters={[]} />);
    await waitFor(() => expect(tile('sales/y').dataset.state).toBe('ready'));

    expect(first.destroy).toHaveBeenCalledTimes(1);
    expect(mocks.getAdapter).toHaveBeenCalledTimes(2);
    expect(second.mount).toHaveBeenCalledTimes(1);
    expect(second.mount).toHaveBeenCalledWith(expect.anything(), chartY.spec, rows, chartY.data.columns);
    expect(first.update).not.toHaveBeenCalled();
  });

  it('does not flash ready with a stale stat spec when the chart switches while idle', async () => {
    // The stat branch's setRendered(true) runs synchronously inside the
    // mount/update effect (no adapter promise involved), so unlike the
    // adapter-mount branch above, a stale pass here is directly observable
    // in the very next commit rather than being corrected before any
    // microtask can see it. This exercises the same `chart.id !== chartId`
    // guard from a different, more directly observable angle.
    const statX = { ...chart, renderer: 'stat' as const, spec: { value: 'revenue', agg: 'sum' as const } };
    const statY = { ...chart, id: 'sales/y', renderer: 'stat' as const, spec: { value: 'revenue', agg: 'sum' as const } };
    mocks.fetchChart.mockImplementation(async (id: string) => (id === 'sales/y' ? statY : statX));
    mocks.fetchRows.mockResolvedValue(rows);

    const { rerender } = render(<ChartTile chartId="sales/x" filters={[]} />);
    await waitFor(() => expect(tile('sales/x').dataset.state).toBe('ready'));

    rerender(<ChartTile chartId="sales/y" filters={[]} />);
    // Assert immediately (no await): a stale-spec flash would show up in
    // this very first commit after the prop change, showing data-state
    // "ready" with no stat value actually rendered yet.
    expect(tile('sales/y').dataset.state).toBe('loading');

    await waitFor(() => expect(tile('sales/y').dataset.state).toBe('ready'));
    expect(screen.getByTestId('stat-value')).toHaveTextContent('3');
  });
});

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
