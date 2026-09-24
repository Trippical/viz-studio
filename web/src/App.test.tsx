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
