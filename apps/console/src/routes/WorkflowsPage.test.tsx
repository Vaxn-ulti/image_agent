import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';
import { api } from '../lib/api';
import { mockSeries, mockTasks } from '../mocks/data';
import { WorkflowsPage } from './WorkflowsPage';

vi.mock('../lib/api', () => ({
  api: {
    listProjectTasks: vi.fn(),
    listSeries: vi.fn(),
    listWorkflows: vi.fn(),
    runSeries: vi.fn(),
  },
}));

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={['/projects/13/workflows']}>
        <Routes>
          <Route element={<WorkflowsPage />} path="/projects/:projectId/workflows" />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('WorkflowsPage', () => {
  it('shows workflow groups and disabled dependency reasons', async () => {
    vi.mocked(api.listSeries).mockResolvedValue([{ ...mockSeries[2], metadata: { has_bval: true, has_bvec: true } }]);
    vi.mocked(api.listProjectTasks).mockResolvedValue(mockTasks);
    vi.mocked(api.listWorkflows).mockResolvedValue({ workflows: ['dwi_fast_gpu_dti'] });

    renderPage();

    expect(await screen.findByRole('heading', { name: 'DWI Workflows' })).toBeInTheDocument();
    expect(await screen.findByText(/JSON sidecar/)).toBeInTheDocument();
  });

  it('passes the completed QSIPrep task id when launching QSIRecon', async () => {
    const user = userEvent.setup();
    vi.mocked(api.listSeries).mockResolvedValue([
      { ...mockSeries[2], modality: 'DWI', metadata: { has_bval: true, has_bvec: true, has_json: true } },
    ]);
    vi.mocked(api.listProjectTasks).mockResolvedValue([
      { ...mockTasks[0], id: 88, series_id: mockSeries[2].id, status: 'completed', workflow_type: 'dwi_qsiprep' },
    ]);
    vi.mocked(api.listWorkflows).mockResolvedValue({ workflows: ['dwi_qsirecon'] });
    vi.mocked(api.runSeries).mockResolvedValue({ ...mockTasks[0], workflow_type: 'dwi_qsirecon' });

    renderPage();

    await user.click(await screen.findByRole('button', { name: /run workflow/i }));

    expect(api.runSeries).toHaveBeenCalledWith(mockSeries[2].id, 'dwi_qsirecon', 88);
  });
});
