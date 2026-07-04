import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { api } from '../lib/api';
import { ResultsIndexPage } from './ResultsIndexPage';

vi.mock('../lib/api', () => ({
  api: {
    listWorkflows: vi.fn(),
    listProjectTasks: vi.fn(),
  },
}));

describe('ResultsIndexPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(api.listWorkflows).mockResolvedValue({ workflows: [] });
  });

  it('uses workflow catalog display names while preserving stable workflow ids', async () => {
    vi.mocked(api.listWorkflows).mockResolvedValue({
      workflows: [
        {
          api_runnable: true,
          display_name: 'BOLD fMRIPrep + XCP-D processing, metrics, QC, and report',
          lane: 'fixed_workflow',
          requires_confirmation: true,
          runtime_workflow_type: 'bold_fmriprep_xcpd_report',
          type: 'bold_fmriprep_xcpd_report',
        },
      ],
    });
    vi.mocked(api.listProjectTasks).mockResolvedValue([
      {
        finished_at: '2026-06-18T07:00:00Z',
        id: 201,
        progress: 100,
        project_id: 13,
        status: 'completed',
        workflow_type: 'bold_fmriprep_xcpd_report',
      },
    ]);
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });

    render(
      <QueryClientProvider client={client}>
        <MemoryRouter initialEntries={['/projects/13/results']}>
          <Routes>
            <Route element={<ResultsIndexPage />} path="/projects/:projectId/results" />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>,
    );

    expect(await screen.findByText('BOLD fMRIPrep + XCP-D processing, metrics, QC, and report')).toBeInTheDocument();
    expect(screen.getByText('Stable workflow ID: bold_fmriprep_xcpd_report')).toBeInTheDocument();
    expect(screen.getByText('RUN_ID: 201')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /BOLD fMRIPrep/ })).toHaveAttribute('href', '/projects/13/results/201');
  });

  it('uses task workflow metadata when workflow catalog has not loaded', async () => {
    vi.mocked(api.listWorkflows).mockResolvedValue({ workflows: [] });
    vi.mocked(api.listProjectTasks).mockResolvedValue([
      {
        finished_at: '2026-06-18T07:00:00Z',
        id: 202,
        progress: 100,
        project_id: 13,
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
        <MemoryRouter initialEntries={['/projects/13/results']}>
          <Routes>
            <Route element={<ResultsIndexPage />} path="/projects/:projectId/results" />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>,
    );

    expect(await screen.findByText('DWI fast GPU DTI maps, atlas metrics, QC, and report')).toBeInTheDocument();
    expect(screen.getByText('Stable workflow ID: dwi_fast_gpu_dti')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /DWI fast GPU DTI/ })).toHaveAttribute('href', '/projects/13/results/202');
  });

  it('blocks the results studio when project scoped tasks cannot load', async () => {
    vi.mocked(api.listProjectTasks).mockRejectedValue(new Error('Project not found'));
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });

    render(
      <QueryClientProvider client={client}>
        <MemoryRouter initialEntries={['/projects/13/results']}>
          <Routes>
            <Route element={<ResultsIndexPage />} path="/projects/:projectId/results" />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>,
    );

    expect(await screen.findByText('Project data unavailable')).toBeInTheDocument();
    expect(screen.getByText('Project not found')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Switch project' })).toHaveAttribute('href', '/projects');
    expect(screen.queryByText('No results available')).not.toBeInTheDocument();
  });
});
