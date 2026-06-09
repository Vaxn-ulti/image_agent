import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';
import { api } from '../lib/api';
import { mockSeries, mockTasks } from '../mocks/data';
import { DashboardPage } from './DashboardPage';

vi.mock('../lib/api', () => ({
  api: {
    listProjectTasks: vi.fn(),
    listSeries: vi.fn(),
  },
}));

describe('DashboardPage', () => {
  it('renders project overview, modality readiness, and result coverage', async () => {
    vi.mocked(api.listProjectTasks).mockResolvedValue(mockTasks);
    vi.mocked(api.listSeries).mockResolvedValue(mockSeries);
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });

    render(
      <QueryClientProvider client={client}>
        <MemoryRouter initialEntries={['/projects/13/dashboard']}>
          <Routes>
            <Route element={<DashboardPage />} path="/projects/:projectId/dashboard" />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>,
    );

    expect(await screen.findByRole('heading', { name: 'Overview' })).toBeInTheDocument();
    expect(await screen.findByText('Modality readiness')).toBeInTheDocument();
    expect(await screen.findByText('Result coverage')).toBeInTheDocument();
    expect(await screen.findAllByText('T1')).toHaveLength(1);
    expect(await screen.findAllByText('BOLD')).toHaveLength(1);
    expect(await screen.findAllByText('DWI')).toHaveLength(1);
  });
});
