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
  // Typed with explicit parameters (matching Adapter's mount/update) so
  // `.mock.calls[0][n]` below is not inferred against a zero-length tuple.
  adapter: {
    mount: vi.fn(async (_el: HTMLElement, _spec: unknown, _rows: unknown[], _columns: unknown[]) => undefined),
    update: vi.fn(async (_rows: unknown[]) => undefined),
    destroy: vi.fn(),
  },
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
  data: { format: 'json', file: 'data.0123456789abcdef.json', lane: 'small', rows: 2, bytes: 1, columns }, aggregate: null,
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

  it('drops a region value from the URL that is not among the reported rows', async () => {
    renderPage('/d/sales/overview?region=APAC');
    await waitFor(() => expect(document.querySelectorAll('[data-tile][data-state="ready"]')).toHaveLength(2));
    const region = screen.getByLabelText('Region') as HTMLSelectElement;
    await waitFor(() => expect(region.options.length).toBe(2));
    // APAC is not among the rows the tiles reported, so once the select
    // options are derived from those rows the restored value is dropped:
    // nothing stays selected and the tile falls back to its unfiltered rows.
    expect(Array.from(region.selectedOptions).map((o) => o.value)).toEqual([]);
    await waitFor(() => expect(document.querySelector('[data-tile="sales/revenue"]')?.getAttribute('data-rows')).toBe('2'));
  });
});
