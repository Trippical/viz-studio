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
