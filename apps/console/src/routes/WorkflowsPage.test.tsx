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
    resumeAgent: vi.fn(),
    runAgent: vi.fn(),
    runSeries: vi.fn(),
  },
}));

beforeEach(() => {
  vi.resetAllMocks();
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

  it('shows structured workflow capability metadata instead of only the workflow id', async () => {
    vi.mocked(api.listSeries).mockResolvedValue([{ ...mockSeries[1], modality: 'BOLD' }]);
    vi.mocked(api.listProjectTasks).mockResolvedValue([]);
    vi.mocked(api.listWorkflows).mockResolvedValue({
      workflows: [
        {
          capability_summary: 'Runs full BOLD preprocessing, XCP-D derived metrics, container-native QC, and report outputs.',
          display_name: 'BOLD fMRIPrep + XCP-D processing, metrics, QC, and report',
          is_report_only: false,
          lane: 'fixed_workflow',
          limitations: ['Requires same-project T1/anat data and configured fMRIPrep/XCP-D containers.'],
          pipeline_stages: [
            { name: 'fMRIPrep preprocessing', purpose: 'Run BOLD preprocessing.' },
            { name: 'XCP-D postprocessing', purpose: 'Generate denoised metrics.' },
          ],
          primary_outputs: ['preprocessed BOLD derivatives', 'ALFF/fALFF/ReHo and connectivity metrics'],
          qc_outputs: ['container-native fMRIPrep and XCP-D QC artifacts'],
          report_outputs: ['HTML scientific report'],
          requires_confirmation: true,
          workflow_family: 'bold',
          workflow_role: 'complete_processing',
          runtime_workflow_type: 'bold_fmriprep_xcpd_report',
          type: 'bold_fmriprep_xcpd_report',
        },
      ],
    });

    renderPage();

    expect(await screen.findByText('BOLD fMRIPrep + XCP-D processing, metrics, QC, and report')).toBeInTheDocument();
    expect(screen.getByText(/full BOLD preprocessing/)).toBeInTheDocument();
    expect(screen.getByText('bold')).toBeInTheDocument();
    expect(screen.getByText('complete processing')).toBeInTheDocument();
    expect(screen.getByText('Full processing')).toBeInTheDocument();
    expect(screen.getByText('fMRIPrep preprocessing')).toBeInTheDocument();
    expect(screen.getByText(/Generate denoised metrics/)).toBeInTheDocument();
    expect(screen.getByText(/Requires same-project T1\/anat data/)).toBeInTheDocument();
    expect(screen.getByText(/preprocessed BOLD derivatives/)).toBeInTheDocument();
    expect(screen.getByText(/container-native fMRIPrep and XCP-D QC artifacts/)).toBeInTheDocument();
  });

  it('passes the completed QSIPrep task id through Agent confirmation before launching QSIRecon', async () => {
    const user = userEvent.setup();
    vi.mocked(api.listSeries).mockResolvedValue([
      { ...mockSeries[2], modality: 'DWI', metadata: { has_bval: true, has_bvec: true, has_json: true } },
    ]);
    vi.mocked(api.listProjectTasks).mockResolvedValue([
      { ...mockTasks[0], id: 88, series_id: mockSeries[2].id, status: 'completed', workflow_type: 'dwi_qsiprep' },
    ]);
    vi.mocked(api.listWorkflows).mockResolvedValue({
      workflows: [
        {
          capability_summary: 'Runs QSIRecon reconstruction derivatives and QC after QSIPrep.',
          display_name: 'DWI QSIRecon reconstruction, QC, and report',
          lane: 'fixed_workflow',
          primary_outputs: ['QSIRecon derivatives'],
          qc_outputs: ['QSIRecon QC artifacts'],
          report_outputs: ['HTML scientific report'],
          requires_confirmation: true,
          runtime_workflow_type: 'dwi_qsirecon',
          type: 'dwi_qsirecon',
        },
      ],
    });
    vi.mocked(api.runAgent).mockResolvedValue({
      answer: 'Approval required for dwi_qsirecon.',
      confirmation: {
        project_id: 13,
        series_id: mockSeries[2].id,
        type: 'workflow_execution',
        workflow_metadata: {
          capability_summary: 'Runs QSIRecon reconstruction derivatives and QC after QSIPrep.',
          display_name: 'DWI QSIRecon reconstruction, QC, and report',
          is_report_only: false,
          primary_outputs: ['QSIRecon derivatives'],
          qc_outputs: ['QSIRecon QC artifacts'],
          report_outputs: ['HTML scientific report'],
          workflow_type: 'dwi_qsirecon',
        },
        workflow_type: 'dwi_qsirecon',
      },
      intent: 'run_workflow',
      selected_skill: 'image-agent-workflow-runner',
      status: 'confirmation_required',
      thread_id: 'thread-confirm-91',
    });
    vi.mocked(api.resumeAgent).mockResolvedValue({
      answer: 'Workflow task created.',
      status: 'task_created',
      task: { ...mockTasks[0], id: 91, status: 'queued', workflow_type: 'dwi_qsirecon' },
    });

    const client = renderPage();
    const invalidate = vi.spyOn(client, 'invalidateQueries');

    await user.click(await screen.findByRole('button', { name: /run workflow/i }));

    expect(api.runAgent).toHaveBeenCalledWith(13, expect.stringContaining('dwi_qsirecon'));
    expect(api.runAgent).toHaveBeenCalledWith(13, expect.stringContaining(`series ${mockSeries[2].id}`));
    expect(api.runSeries).not.toHaveBeenCalled();
    expect(await screen.findByText('Approval required')).toBeInTheDocument();
    expect(screen.getAllByText('DWI QSIRecon reconstruction, QC, and report').length).toBeGreaterThanOrEqual(2);
    expect(screen.getAllByText(/Runs QSIRecon reconstruction derivatives/).length).toBeGreaterThanOrEqual(2);
    expect(screen.getAllByText('QSIRecon derivatives').length).toBeGreaterThanOrEqual(2);
    expect(screen.getAllByText('dwi_qsirecon').length).toBeGreaterThanOrEqual(1);
    await user.click(screen.getByRole('button', { name: /Approve workflow/ }));
    expect(api.resumeAgent).toHaveBeenCalledWith('thread-confirm-91', true, expect.objectContaining({ workflow_type: 'dwi_qsirecon' }));
    expect(await screen.findByText('Task #91 started')).toBeInTheDocument();
    expect(screen.getByText(/deterministic DWI QSIRecon reconstruction, QC, and report task/)).toBeInTheDocument();
    expect(screen.getAllByText('Stable workflow ID: dwi_qsirecon').length).toBeGreaterThanOrEqual(1);
    expect(screen.getByRole('link', { name: /view task progress/i })).toHaveAttribute('href', '/projects/13/tasks');
    expect(invalidate).toHaveBeenCalledWith({ queryKey: queryKeys.tasks(13) });
    expect(invalidate).toHaveBeenCalledWith({ queryKey: queryKeys.task(91) });
  });

  it('shows backend workflow launch errors without claiming a task started', async () => {
    const user = userEvent.setup();
    vi.mocked(api.listSeries).mockResolvedValue([mockSeries[0]]);
    vi.mocked(api.listProjectTasks).mockResolvedValue([]);
    vi.mocked(api.listWorkflows).mockResolvedValue({ workflows: ['t1_deepprep'] });
    vi.mocked(api.runAgent).mockRejectedValue(new Error('Remote DeepPrep runtime is not configured.'));

    renderPage();

    await user.click(await screen.findByRole('button', { name: /run workflow/i }));

    expect(await screen.findByText('Remote DeepPrep runtime is not configured.')).toBeInTheDocument();
    expect(screen.queryByText(/Task #.* started/)).not.toBeInTheDocument();
    expect(api.runSeries).not.toHaveBeenCalled();
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
