import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { api } from '../lib/api';
import { mockTasks } from '../mocks/data';
import { TasksPage } from './TasksPage';

vi.mock('../lib/api', () => ({
  api: {
    getTaskEvents: vi.fn(),
    getLogs: vi.fn(),
    listWorkflows: vi.fn(),
    observeRepair: vi.fn(),
    getOutputs: vi.fn(),
    listProjectTasks: vi.fn(),
  },
}));

describe('TasksPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(api.listWorkflows).mockResolvedValue({ workflows: [] });
  });

  it('renders status vocabulary and result links', async () => {
    vi.mocked(api.listProjectTasks).mockResolvedValue(mockTasks);
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });

    render(
      <QueryClientProvider client={client}>
        <MemoryRouter initialEntries={['/projects/13/tasks']}>
          <Routes>
            <Route element={<TasksPage />} path="/projects/:projectId/tasks" />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>,
    );

    expect(await screen.findByText('RUN-114')).toBeInTheDocument();
    expect((await screen.findAllByText('Completed')).length).toBeGreaterThanOrEqual(3);
    expect(screen.getAllByRole('link', { name: /Open result/ }).map((link) => link.getAttribute('href'))).toContain(
      '/projects/13/results/114',
    );
  });

  it('renders running and failed backend task states without result links', async () => {
    vi.mocked(api.listProjectTasks).mockResolvedValue([
      { ...mockTasks[0], id: 201, progress: 35, status: 'running', workflow_type: 'bold_fmriprep_xcpd_report' },
      {
        ...mockTasks[0],
        error_message: 'Container image is not available.',
        id: 202,
        progress: 20,
        status: 'failed',
        workflow_type: 'dwi_fast_gpu_dti',
      },
    ]);
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });

    render(
      <QueryClientProvider client={client}>
        <MemoryRouter initialEntries={['/projects/13/tasks']}>
          <Routes>
            <Route element={<TasksPage />} path="/projects/:projectId/tasks" />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>,
    );

    expect(await screen.findByText('RUN-201')).toBeInTheDocument();
    expect(await screen.findByText('RUN-202')).toBeInTheDocument();
    expect(screen.getByText('Running')).toBeInTheDocument();
    expect(screen.getByText('Failed')).toBeInTheDocument();
    expect(screen.getByText('35%')).toBeInTheDocument();
    expect(screen.getByText('20%')).toBeInTheDocument();
    expect(screen.getByText('Container image is not available.')).toBeInTheDocument();
    expect(screen.queryByRole('link', { name: /Open result RUN-201/ })).not.toBeInTheDocument();
    expect(screen.queryByRole('link', { name: /Open result RUN-202/ })).not.toBeInTheDocument();
  });

  it('uses workflow catalog display names while preserving stable workflow ids', async () => {
    vi.mocked(api.listWorkflows).mockResolvedValue({
      workflows: [
        {
          api_runnable: true,
          capability_summary: 'Runs full BOLD preprocessing, XCP-D derived metrics, container-native QC, and report outputs.',
          display_name: 'BOLD fMRIPrep + XCP-D processing, metrics, QC, and report',
          lane: 'fixed_workflow',
          requires_confirmation: true,
          runtime_workflow_type: 'bold_fmriprep_xcpd_report',
          type: 'bold_fmriprep_xcpd_report',
        },
      ],
    });
    vi.mocked(api.listProjectTasks).mockResolvedValue([
      { ...mockTasks[0], id: 201, progress: 35, status: 'running', workflow_type: 'bold_fmriprep_xcpd_report' },
    ]);
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });

    render(
      <QueryClientProvider client={client}>
        <MemoryRouter initialEntries={['/projects/13/tasks']}>
          <Routes>
            <Route element={<TasksPage />} path="/projects/:projectId/tasks" />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>,
    );

    expect(await screen.findByText('BOLD fMRIPrep + XCP-D processing, metrics, QC, and report')).toBeInTheDocument();
    expect(screen.getByText('Stable workflow ID: bold_fmriprep_xcpd_report')).toBeInTheDocument();
  });

  it('uses task workflow metadata when workflow catalog has not loaded', async () => {
    vi.mocked(api.listWorkflows).mockResolvedValue({ workflows: [] });
    vi.mocked(api.listProjectTasks).mockResolvedValue([
      {
        ...mockTasks[0],
        id: 203,
        progress: 70,
        status: 'running',
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
        <MemoryRouter initialEntries={['/projects/13/tasks']}>
          <Routes>
            <Route element={<TasksPage />} path="/projects/:projectId/tasks" />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>,
    );

    expect(await screen.findByText('DWI fast GPU DTI maps, atlas metrics, QC, and report')).toBeInTheDocument();
    expect(screen.getByText('Stable workflow ID: dwi_fast_gpu_dti')).toBeInTheDocument();
  });

  it('opens read-only ObserveRepair advice for failed tasks without rerun actions', async () => {
    vi.mocked(api.listProjectTasks).mockResolvedValue([
      {
        ...mockTasks[0],
        error_message: 'Container image is not available.',
        id: 202,
        progress: 20,
        status: 'failed',
        workflow_type: 'dwi_fast_gpu_dti',
      },
    ]);
    vi.mocked(api.observeRepair).mockResolvedValue({
      auto_rerun_allowed: false,
      main_log: { tail: 'Container image pull failed after registry check.' },
      policy: 'read_only_observe_repair',
      production_task_created: false,
      remote_logs: [{ name: 'qsiprep.log', source_stage: 'qsiprep', tail: 'registry denied image pull' }],
      repair_suggestions: [
        { kind: 'failed_task_repair_plan', message: 'Inspect redacted task events and draft a repair plan.' },
      ],
      requires_human_confirmation_before_retry: true,
      requires_preflight_before_retry: true,
      status: 'ok',
      task_id: 202,
    });
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });

    render(
      <QueryClientProvider client={client}>
        <MemoryRouter initialEntries={['/projects/13/tasks']}>
          <Routes>
            <Route element={<TasksPage />} path="/projects/:projectId/tasks" />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>,
    );

    await userEvent.click(await screen.findByRole('button', { name: 'Inspect read-only repair advice for RUN-202' }));

    expect(api.observeRepair).toHaveBeenCalledWith(202);
    expect(await screen.findByText('Read-only repair advice')).toBeInTheDocument();
    expect(screen.getByText('Inspect redacted task events and draft a repair plan.')).toBeInTheDocument();
    expect(screen.getByText('Container image pull failed after registry check.')).toBeInTheDocument();
    expect(screen.getByText('registry denied image pull')).toBeInTheDocument();
    expect(screen.getByText('New preflight required')).toBeInTheDocument();
    expect(screen.getByText('Human confirmation required')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /rerun/i })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /retry/i })).not.toBeInTheDocument();
  });

  it('opens read-only structured task events for running tasks without rerun actions', async () => {
    vi.mocked(api.listProjectTasks).mockResolvedValue([
      {
        ...mockTasks[0],
        id: 204,
        progress: 45,
        status: 'running',
        workflow_type: 'bold_fmriprep_xcpd_report',
      },
    ]);
    vi.mocked(api.getTaskEvents).mockResolvedValue({
      events: [
        { progress: 45, status: 'running', type: 'task.status' },
        { name: 'fmriprep.log', source_stage: 'fmriprep', type: 'task.remote_log' },
      ],
      main_log: { tail: 'fMRIPrep running with [redacted-host-path]' },
      remote_logs: [{ name: 'fmriprep.log', source_stage: 'fmriprep', tail: 'stage reached skull-strip' }],
      status: 'ok',
      task: {
        ...mockTasks[0],
        id: 204,
        progress: 45,
        status: 'running',
        workflow_type: 'bold_fmriprep_xcpd_report',
      },
      task_id: 204,
    });
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });

    render(
      <QueryClientProvider client={client}>
        <MemoryRouter initialEntries={['/projects/13/tasks']}>
          <Routes>
            <Route element={<TasksPage />} path="/projects/:projectId/tasks" />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>,
    );

    await userEvent.click(await screen.findByRole('button', { name: 'Inspect task events for RUN-204' }));

    expect(api.getTaskEvents).toHaveBeenCalledWith(204);
    expect(await screen.findByText('Read-only task events')).toBeInTheDocument();
    expect(screen.getByText('task.status')).toBeInTheDocument();
    expect(screen.getByText('running')).toBeInTheDocument();
    expect(screen.getByText('task.remote_log')).toBeInTheDocument();
    expect(screen.getByText('fmriprep')).toBeInTheDocument();
    expect(screen.getByText('fMRIPrep running with [redacted-host-path]')).toBeInTheDocument();
    expect(screen.getByText('stage reached skull-strip')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /rerun/i })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /retry/i })).not.toBeInTheDocument();
  });

  it('blocks the task monitor when project scoped tasks cannot load', async () => {
    vi.mocked(api.listProjectTasks).mockRejectedValue(new Error('Project not found'));
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });

    render(
      <QueryClientProvider client={client}>
        <MemoryRouter initialEntries={['/projects/13/tasks']}>
          <Routes>
            <Route element={<TasksPage />} path="/projects/:projectId/tasks" />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>,
    );

    expect(await screen.findByText('Project data unavailable')).toBeInTheDocument();
    expect(screen.getByText('Project not found')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Switch project' })).toHaveAttribute('href', '/projects');
    expect(screen.queryByText(/No backend tasks detected/)).not.toBeInTheDocument();
    expect(screen.queryByText('Recent Execution History')).not.toBeInTheDocument();
  });
});
