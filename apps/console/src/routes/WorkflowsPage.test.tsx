import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { api } from '../lib/api';
import { queryKeys } from '../lib/query';
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

beforeEach(() => {
  vi.clearAllMocks();
});

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
  return client;
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

  it('passes the completed QSIPrep task id and shows the launched task handoff when launching QSIRecon', async () => {
    const user = userEvent.setup();
    vi.mocked(api.listSeries).mockResolvedValue([
      { ...mockSeries[2], modality: 'DWI', metadata: { has_bval: true, has_bvec: true, has_json: true } },
    ]);
    vi.mocked(api.listProjectTasks).mockResolvedValue([
      { ...mockTasks[0], id: 88, series_id: mockSeries[2].id, status: 'completed', workflow_type: 'dwi_qsiprep' },
    ]);
    vi.mocked(api.listWorkflows).mockResolvedValue({ workflows: ['dwi_qsirecon'] });
    vi.mocked(api.runSeries).mockResolvedValue({ ...mockTasks[0], id: 91, status: 'queued', workflow_type: 'dwi_qsirecon' });

    const client = renderPage();
    const invalidate = vi.spyOn(client, 'invalidateQueries');

    await user.click(await screen.findByRole('button', { name: /run workflow/i }));

    expect(api.runSeries).toHaveBeenCalledWith(mockSeries[2].id, 'dwi_qsirecon', 88);
    expect(await screen.findByText('Task #91 started')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /view task progress/i })).toHaveAttribute('href', '/projects/13/tasks');
    expect(invalidate).toHaveBeenCalledWith({ queryKey: queryKeys.tasks(13) });
    expect(invalidate).toHaveBeenCalledWith({ queryKey: queryKeys.task(91) });
  });

  it('shows backend workflow launch errors without claiming a task started', async () => {
    const user = userEvent.setup();
    vi.mocked(api.listSeries).mockResolvedValue([mockSeries[0]]);
    vi.mocked(api.listProjectTasks).mockResolvedValue([]);
    vi.mocked(api.listWorkflows).mockResolvedValue({ workflows: ['t1_deepprep'] });
    vi.mocked(api.runSeries).mockRejectedValue(new Error('Remote DeepPrep runtime is not configured.'));

    renderPage();

    await user.click(await screen.findByRole('button', { name: /run workflow/i }));

    expect(await screen.findByText('Remote DeepPrep runtime is not configured.')).toBeInTheDocument();
    expect(screen.queryByText(/Task #.* started/)).not.toBeInTheDocument();
  });

  it('blocks workflow launch when project scoped backend data is unavailable', async () => {
    vi.mocked(api.listSeries).mockRejectedValue(new Error('Project not found'));
    vi.mocked(api.listProjectTasks).mockResolvedValue([]);
    vi.mocked(api.listWorkflows).mockResolvedValue({ workflows: ['t1_deepprep'] });

    renderPage();

    expect(await screen.findByText('Project data unavailable')).toBeInTheDocument();
    expect(screen.getByText('Project not found')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /switch project/i })).toHaveAttribute('href', '/projects');
    expect(screen.queryByRole('button', { name: /run workflow/i })).not.toBeInTheDocument();
    expect(api.runSeries).not.toHaveBeenCalled();
  });
});
