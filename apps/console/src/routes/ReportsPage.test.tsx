import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { api } from '../lib/api';
import { mockTasks } from '../mocks/data';
import { ReportsPage } from './ReportsPage';

vi.mock('../lib/api', () => ({
  api: {
    listProjectTasks: vi.fn(),
  },
}));

describe('ReportsPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('lists completed report tasks', async () => {
    vi.mocked(api.listProjectTasks).mockResolvedValue(mockTasks);
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });

    render(
      <QueryClientProvider client={client}>
        <MemoryRouter initialEntries={['/projects/13/reports']}>
          <Routes>
            <Route element={<ReportsPage />} path="/projects/:projectId/reports" />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>,
    );

    expect(await screen.findByRole('heading', { name: 'Scientific Reports' })).toBeInTheDocument();
    expect(await screen.findByText('3 Reports Available')).toBeInTheDocument();
    expect(await screen.findByText('dwi fast gpu dti Report')).toBeInTheDocument();
  });

  it('blocks the reports page when project scoped tasks cannot load', async () => {
    vi.mocked(api.listProjectTasks).mockRejectedValue(new Error('Project not found'));
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });

    render(
      <QueryClientProvider client={client}>
        <MemoryRouter initialEntries={['/projects/13/reports']}>
          <Routes>
            <Route element={<ReportsPage />} path="/projects/:projectId/reports" />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>,
    );

    expect(await screen.findByText('Project data unavailable')).toBeInTheDocument();
    expect(screen.getByText('Project not found')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Switch project' })).toHaveAttribute('href', '/projects');
    expect(screen.queryByText('No ready reports yet')).not.toBeInTheDocument();
    expect(screen.queryByText('0 Reports Available')).not.toBeInTheDocument();
  });
});
