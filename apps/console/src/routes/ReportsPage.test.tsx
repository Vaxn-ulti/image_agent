import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { api } from '../lib/api';
import { mockTasks } from '../mocks/data';
import { ReportsPage } from './ReportsPage';

vi.mock('../lib/api', () => ({
  api: {
    listWorkflows: vi.fn(),
    listProjectTasks: vi.fn(),
  },
}));

describe('ReportsPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(api.listWorkflows).mockResolvedValue({ workflows: [] });
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
    expect(await screen.findByText('dwi_fast_gpu_dti')).toBeInTheDocument();
    expect(screen.queryByText('dwi fast gpu dti Report')).not.toBeInTheDocument();
  });

  it('uses workflow catalog display names while preserving stable workflow ids', async () => {
    vi.mocked(api.listWorkflows).mockResolvedValue({
      workflows: [
        {
          api_runnable: true,
          display_name: 'DWI QSIRecon reconstruction, QC, and report',
          lane: 'fixed_workflow',
          requires_confirmation: true,
          runtime_workflow_type: 'dwi_qsirecon',
          type: 'dwi_qsirecon',
        },
      ],
    });
    vi.mocked(api.listProjectTasks).mockResolvedValue([
      {
        finished_at: '2026-06-18T07:00:00Z',
        id: 301,
        progress: 100,
        project_id: 13,
        series_id: 44,
        status: 'completed',
        workflow_type: 'dwi_qsirecon',
      },
    ]);
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

    expect(await screen.findByText('DWI QSIRecon reconstruction, QC, and report')).toBeInTheDocument();
    expect(screen.getByText('Stable workflow ID: dwi_qsirecon')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /View Report/ })).toHaveAttribute('href', '/projects/13/results/301');
  });

  it('uses task workflow metadata when workflow catalog has not loaded', async () => {
    vi.mocked(api.listWorkflows).mockResolvedValue({ workflows: [] });
    vi.mocked(api.listProjectTasks).mockResolvedValue([
      {
        finished_at: '2026-06-18T07:00:00Z',
        id: 302,
        progress: 100,
        project_id: 13,
        series_id: 44,
        status: 'completed',
        workflow_metadata: {
          display_name: 'DWI fast GPU DTI maps, atlas metrics, QC, and report',
          is_report_only: false,
          runtime_workflow_type: 'dwi_fast_gpu_dti',
          workflow_type: 'dwi_fast_gpu_dti',
        },
        workflow_type: 'dwi_fast_gpu_dti',
      },
    ]);
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

    expect(await screen.findByText('DWI fast GPU DTI maps, atlas metrics, QC, and report')).toBeInTheDocument();
    expect(screen.getByText('Stable workflow ID: dwi_fast_gpu_dti')).toBeInTheDocument();
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
