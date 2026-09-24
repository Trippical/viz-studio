import { render, screen } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';
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
    mocks.fetchTree.mockReset();
    mocks.fetchTree.mockResolvedValue(tree);
    renderAt('/');
    expect(await screen.findByRole('link', { name: 'Sales overview' })).toHaveAttribute('href', '/d/sales/overview');
    expect(screen.getByText('sales')).toBeInTheDocument();
    expect(screen.getByText(/schema_version: bad/)).toBeInTheDocument();
  });

  it('renders charts with titles, markdown descriptions, static badges and item errors', async () => {
    mocks.fetchTree.mockReset();
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
    mocks.fetchTree.mockReset();
    mocks.fetchTree.mockRejectedValue(new Error('offline'));
    renderAt('/');
    expect(await screen.findByRole('alert')).toHaveTextContent('offline');
  });
});
