import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';
import { api } from '../lib/api';
import { mockTasks } from '../mocks/data';
import { ReportsPage } from './ReportsPage';

vi.mock('../lib/api', () => ({
  api: {
    listProjectTasks: vi.fn(),
  },
}));

describe('ReportsPage', () => {
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

    expect(await screen.findByRole('heading', { name: 'Reports' })).toBeInTheDocument();
    expect(await screen.findByText('Report-ready tasks')).toBeInTheDocument();
    expect(await screen.findByText('dwi_fast_gpu_dti')).toBeInTheDocument();
  });
});
