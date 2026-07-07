import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { api } from '../lib/api';
import { queryKeys } from '../lib/query';
import { mockSeries, mockT1Summary, mockTasks } from '../mocks/data';
import { DashboardPage } from './DashboardPage';

vi.mock('../lib/api', () => ({
  api: {
    getArtifactManifest: vi.fn(),
    getArtifactUrl: vi.fn(),
    getResultSummary: vi.fn(),
    listWorkflows: vi.fn(),
    listProjectTasks: vi.fn(),
    listProjectFiles: vi.fn(),
    listSeries: vi.fn(),
    getTask: vi.fn(),
    runSeries: vi.fn(),
    runAgent: vi.fn(),
    resumeAgent: vi.fn(),
    uploadDicom: vi.fn(),
    uploadDwi: vi.fn(),
    uploadFile: vi.fn(),
    uploadNifti: vi.fn(),
    createUploadSession: vi.fn(),
    getInventory: vi.fn(),
    ingestDataset: vi.fn(),
    deleteProjectFile: vi.fn(),
  },
  getApiBase: () => 'http://localhost:8000',
}));

describe('DashboardPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(api.getArtifactManifest).mockResolvedValue({ artifacts: [], contract_version: 'artifact_manifest_v1', task_id: 0 });
    vi.mocked(api.getArtifactUrl).mockResolvedValue(new Blob(['image'], { type: 'image/png' }));
    vi.mocked(api.listProjectFiles).mockResolvedValue([]);
    URL.createObjectURL = vi.fn();
    URL.revokeObjectURL = vi.fn();
    vi.spyOn(URL, 'createObjectURL').mockReturnValue('blob:http://localhost/authenticated-dashboard-artifact');
    vi.spyOn(URL, 'revokeObjectURL').mockImplementation(() => undefined);
  });

  function mockDashboardWorkflowConfirmation({
    seriesId = 22,
    taskId = 131,
    workflowType = 't1_deepprep_anat_report',
    taskWorkflowType = workflowType,
    progress = 0,
    status = 'queued',
    threadId = 'agent_dashboard_thread',
  }: {
    progress?: number;
    seriesId?: number;
    status?: 'queued' | 'running' | 'completed';
    taskId?: number;
    taskWorkflowType?: string;
    threadId?: string;
    workflowType?: string;
  } = {}) {
    const confirmation = {
      action_lane: 'fixed_workflow',
      project_id: 13,
      series_id: seriesId,
      type: 'workflow_execution',
      workflow_type: workflowType,
    };
    vi.mocked(api.runAgent).mockResolvedValue({
      answer: `Approval required for ${workflowType}.`,
      confirmation,
      status: 'confirmation_required',
      thread_id: threadId,
    });
    vi.mocked(api.resumeAgent).mockResolvedValue({
      answer: `Task ${taskId} created for ${taskWorkflowType}.`,
      status: 'task_created',
      task: { id: taskId, progress, project_id: 13, series_id: seriesId, status, workflow_type: taskWorkflowType },
    });
    return confirmation;
  }

  it('blocks the dashboard main flow when the project scoped backend data is unavailable', async () => {
    vi.mocked(api.getResultSummary).mockResolvedValue(mockT1Summary);
    vi.mocked(api.listWorkflows).mockResolvedValue({ workflows: ['t1_deepprep'] });
    vi.mocked(api.listProjectTasks).mockRejectedValue(new Error('Project not found'));
    vi.mocked(api.listSeries).mockRejectedValue(new Error('Project not found'));
    vi.mocked(api.runAgent).mockResolvedValue({ answer: 'Use a valid project.' });
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

    expect(await screen.findByText('Project data unavailable')).toBeInTheDocument();
    expect(screen.getByText('Project not found')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Switch project' })).toHaveAttribute('href', '/projects');
    expect(screen.queryByText('Upload Data')).not.toBeInTheDocument();
  });

  it('updates the initial agent greeting when series load after workflows', async () => {
    vi.mocked(api.getResultSummary).mockResolvedValue(mockT1Summary);
    vi.mocked(api.listWorkflows).mockResolvedValue({ workflows: ['t1_deepprep_anat_report'] });
    vi.mocked(api.listProjectTasks).mockResolvedValue([]);
    vi.mocked(api.listSeries).mockResolvedValueOnce([]).mockResolvedValue([mockSeries[0]]);
    vi.mocked(api.runAgent).mockResolvedValue({ answer: 'Upload guidance.' });
    vi.mocked(api.uploadNifti).mockResolvedValue({ file: {}, series: mockSeries[0] });
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

    expect(await screen.findByText('Upload data to review workflow eligibility.')).toBeInTheDocument();

    await userEvent.upload(await screen.findByLabelText('Upload files'), new File(['nifti'], 'sub-01_T1w.nii.gz'));

    expect(await screen.findByText('Data are ready for workflow review.')).toBeInTheDocument();
    expect(screen.queryByText('Upload data to review workflow eligibility.')).not.toBeInTheDocument();
  });

  it('does not phrase the initial Agent greeting as an automatic run recommendation', async () => {
    vi.mocked(api.getResultSummary).mockResolvedValue(mockT1Summary);
    vi.mocked(api.listWorkflows).mockResolvedValue({ workflows: ['t1_deepprep_anat_report'] });
    vi.mocked(api.listProjectTasks).mockResolvedValue([]);
    vi.mocked(api.listSeries).mockResolvedValue([mockSeries[0]]);
    vi.mocked(api.runAgent).mockResolvedValue({ answer: 'Upload guidance.' });
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

    await userEvent.click(await screen.findByLabelText('Open Agent Copilot'));
    expect(await screen.findByText(/the selected eligible workflow is/)).toBeInTheDocument();
    expect(screen.queryByText(/recommend running/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/Approval required/)).not.toBeInTheDocument();
    expect(api.runAgent).not.toHaveBeenCalled();
  });

  it('uses the backend upload contract and refreshes detected series after upload', async () => {
    vi.mocked(api.getResultSummary).mockResolvedValue(mockT1Summary);
    vi.mocked(api.listWorkflows).mockResolvedValue({ workflows: ['t1_deepprep'] });
    vi.mocked(api.listProjectTasks).mockResolvedValue([]);
    vi.mocked(api.listSeries).mockResolvedValueOnce([]).mockResolvedValue([mockSeries[0]]);
    vi.mocked(api.uploadNifti).mockResolvedValue({ file: {}, series: mockSeries[0] });
    vi.mocked(api.runAgent).mockResolvedValue({ answer: 'Upload guidance.' });
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

    const uploadInput = await screen.findByLabelText('Upload files');
    expect(uploadInput).not.toHaveAttribute('accept');

    await userEvent.upload(uploadInput, new File(['nifti'], 'sub-01_T1w.nii.gz'));

    expect(api.uploadNifti).toHaveBeenCalledWith(13, expect.any(File));
    expect(await screen.findByText('Data are ready for workflow review.')).toBeInTheDocument();
    expect(await screen.findByText(/Pipeline: t1_deepprep/)).toBeInTheDocument();
  });

  it('uploads arbitrary project files without requiring an imaging extension', async () => {
    vi.mocked(api.getResultSummary).mockResolvedValue(mockT1Summary);
    vi.mocked(api.listWorkflows).mockResolvedValue({ workflows: ['t1_deepprep'] });
    vi.mocked(api.listProjectTasks).mockResolvedValue([]);
    vi.mocked(api.listSeries).mockResolvedValue([]);
    vi.mocked(api.uploadFile).mockResolvedValue({
      file: { original_name: 'operator-notes.txt' },
      inventory: {
        attachments: [{ original_name: 'operator-notes.txt', file_type: 'TXT' }],
        inventory_status: 'completed',
        series: [],
        total_files: 1,
      },
      series: null,
      status: 'completed',
      upload_session_id: 91,
    });
    vi.mocked(api.getInventory).mockResolvedValue({
      inventory: {
        attachments: [{ original_name: 'operator-notes.txt', file_type: 'TXT' }],
        inventory_status: 'completed',
        series: [],
        total_files: 1,
      },
    });
    vi.mocked(api.runAgent).mockResolvedValue({ answer: 'Upload guidance.' });
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

    const uploadInput = await screen.findByLabelText('Upload files');
    expect(uploadInput).not.toHaveAttribute('accept');

    const note = new File(['notes'], 'operator-notes.txt', { type: 'text/plain' });
    await userEvent.upload(uploadInput, note);

    expect(api.uploadFile).toHaveBeenCalledWith(13, note);
    expect(api.uploadNifti).not.toHaveBeenCalled();
    expect(await screen.findByText('Upload session #91')).toBeInTheDocument();
    expect(await screen.findByText('1 attachment saved')).toBeInTheDocument();
    expect(screen.queryByText(/Supported uploads are DICOM zip/)).not.toBeInTheDocument();
  });

  it('shows uploaded files with backend-detected file roles', async () => {
    vi.mocked(api.getResultSummary).mockResolvedValue(mockT1Summary);
    vi.mocked(api.listWorkflows).mockResolvedValue({ workflows: ['t1_deepprep'] });
    vi.mocked(api.listProjectTasks).mockResolvedValue([]);
    vi.mocked(api.listSeries).mockResolvedValue([mockSeries[0]]);
    vi.mocked(api.listProjectFiles).mockResolvedValue([
      {
        file_type: 'NIFTI',
        id: 44,
        linked_series: [{ id: 55, modality: 'T1', sequence_label: 'T1w_MPRAGE' }],
        original_name: 'sub-01_T1w.nii.gz',
      },
      {
        file_type: 'TXT',
        id: 45,
        linked_series: [],
        original_name: 'operator-notes.txt',
      },
    ]);
    vi.mocked(api.runAgent).mockResolvedValue({ answer: 'Upload guidance.' });
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

    expect(await screen.findByText('Uploaded files')).toBeInTheDocument();
    expect(await screen.findByText('sub-01_T1w.nii.gz')).toBeInTheDocument();
    expect(screen.getByText('T1 / T1w_MPRAGE')).toBeInTheDocument();
    expect(screen.getByText('operator-notes.txt')).toBeInTheDocument();
    expect(screen.getByText('TXT attachment')).toBeInTheDocument();
    expect(within(screen.getByRole('button', { name: 'Delete sub-01_T1w.nii.gz' })).getByText('Delete')).toBeInTheDocument();
  });

  it('renders all uploaded files instead of hiding entries after the first eight', async () => {
    vi.mocked(api.getResultSummary).mockResolvedValue(mockT1Summary);
    vi.mocked(api.listWorkflows).mockResolvedValue({ workflows: ['t1_deepprep'] });
    vi.mocked(api.listProjectTasks).mockResolvedValue([]);
    vi.mocked(api.listSeries).mockResolvedValue([]);
    vi.mocked(api.listProjectFiles).mockResolvedValue(
      Array.from({ length: 10 }, (_, index) => ({
        file_type: 'TXT',
        id: 100 + index,
        linked_series: [],
        original_name: `uploaded-${index + 1}.txt`,
      })),
    );
    vi.mocked(api.runAgent).mockResolvedValue({ answer: 'Upload guidance.' });
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

    expect(await screen.findByText('10 total')).toBeInTheDocument();
    expect(await screen.findByText('uploaded-10.txt')).toBeInTheDocument();
    expect(screen.getAllByRole('button', { name: /^Delete uploaded-/ })).toHaveLength(10);
  });

  it('deletes an uploaded file from the Uploaded files list after confirmation', async () => {
    vi.mocked(api.getResultSummary).mockResolvedValue(mockT1Summary);
    vi.mocked(api.listWorkflows).mockResolvedValue({ workflows: ['t1_deepprep'] });
    vi.mocked(api.listProjectTasks).mockResolvedValue([]);
    vi.mocked(api.listSeries).mockResolvedValue([mockSeries[0]]);
    vi.mocked(api.listProjectFiles).mockResolvedValue([
      {
        file_type: 'NIFTI',
        id: 44,
        linked_series: [{ id: 55, modality: 'T1', sequence_label: 'T1w_MPRAGE' }],
        original_name: 'sub-01_T1w.nii.gz',
      },
    ]);
    vi.mocked(api.deleteProjectFile).mockResolvedValue({ deleted_file: { id: 44 }, deleted_series_ids: [55], status: 'deleted' });
    vi.mocked(api.runAgent).mockResolvedValue({ answer: 'Upload guidance.' });
    const confirm = vi.spyOn(window, 'confirm').mockReturnValue(true);
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

    await userEvent.click(await screen.findByRole('button', { name: 'Delete sub-01_T1w.nii.gz' }));

    expect(confirm).toHaveBeenCalled();
    expect(api.deleteProjectFile).toHaveBeenCalledWith(13, 44);
    await waitFor(() => expect(client.isFetching({ queryKey: queryKeys.projectFiles(13) })).toBe(0));
    confirm.mockRestore();
  });

  it('opens the file chooser from the visible browse button', async () => {
    vi.mocked(api.getResultSummary).mockResolvedValue(mockT1Summary);
    vi.mocked(api.listWorkflows).mockResolvedValue({ workflows: ['t1_deepprep'] });
    vi.mocked(api.listProjectTasks).mockResolvedValue([]);
    vi.mocked(api.listSeries).mockResolvedValue([]);
    vi.mocked(api.runAgent).mockResolvedValue({ answer: 'Upload guidance.' });
    const originalInputClick = HTMLInputElement.prototype.click;
    const inputClick = vi.spyOn(HTMLInputElement.prototype, 'click').mockImplementation(function click(this: HTMLInputElement) {
      return originalInputClick.call(this);
    });
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

    await userEvent.click(await screen.findByRole('button', { name: 'Browse Files' }));

    expect(inputClick).toHaveBeenCalledTimes(1);
    inputClick.mockRestore();
  });

  it('uploads a complete DWI sidecar set through the dashboard backend contract', async () => {
    vi.mocked(api.getResultSummary).mockResolvedValue(mockT1Summary);
    vi.mocked(api.listWorkflows).mockResolvedValue({ workflows: ['dwi_fast_gpu_dti'] });
    vi.mocked(api.listProjectTasks).mockResolvedValue([]);
    vi.mocked(api.listSeries).mockResolvedValueOnce([]).mockResolvedValue([mockSeries[1]]);
    vi.mocked(api.uploadDwi).mockResolvedValue({ files: [], series: mockSeries[1] });
    vi.mocked(api.runAgent).mockResolvedValue({ answer: 'Upload guidance.' });
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

    const uploadInput = await screen.findByLabelText('Upload files');
    expect(uploadInput).toHaveAttribute('multiple');
    expect(uploadInput).not.toHaveAttribute('accept');

    const nifti = new File(['nifti'], 'sub-01_dwi.nii.gz');
    const bval = new File(['bval'], 'sub-01_dwi.bval');
    const bvec = new File(['bvec'], 'sub-01_dwi.bvec');
    const json = new File(['{}'], 'sub-01_dwi.json');
    await userEvent.upload(uploadInput, [nifti, bval, bvec, json]);

    expect(api.uploadDwi).toHaveBeenCalledWith(13, { nifti, bval, bvec, jsonSidecar: json });
    expect(api.uploadNifti).not.toHaveBeenCalled();
    expect(await screen.findByText('Data are ready for workflow review.')).toBeInTheDocument();
  });

  it('uses dataset ingest for zip uploads and shows the upload session id', async () => {
    vi.mocked(api.getResultSummary).mockResolvedValue(mockT1Summary);
    vi.mocked(api.listWorkflows).mockResolvedValue({ workflows: ['t1_deepprep'] });
    vi.mocked(api.listProjectTasks).mockResolvedValue([]);
    vi.mocked(api.listSeries).mockResolvedValueOnce([]).mockResolvedValue([mockSeries[0]]);
    vi.mocked(api.createUploadSession).mockResolvedValue({ id: 77, project_id: 13, status: 'ready' });
    vi.mocked(api.ingestDataset).mockResolvedValue({ inventory: { inventory_status: 'completed' } });
    vi.mocked(api.getInventory).mockResolvedValue({ inventory: { inventory_status: 'completed', total_files: 4 } });
    vi.mocked(api.runAgent).mockResolvedValue({ answer: 'Upload guidance.' });
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

    const archive = new File(['zip'], 'scanner-export.zip', { type: 'application/zip' });
    await userEvent.upload(await screen.findByLabelText('Upload files'), archive);

    expect(api.createUploadSession).toHaveBeenCalledWith(13, { label: 'scanner-export.zip', source_type: 'folder_or_archive' });
    expect(api.ingestDataset).toHaveBeenCalledWith(13, 77, archive);
    expect(api.uploadDicom).not.toHaveBeenCalled();
    expect(await screen.findByText('Upload session #77')).toBeInTheDocument();
    expect(api.getInventory).toHaveBeenCalledWith(13, 77);
    expect(await screen.findByText('Ingest completed')).toBeInTheDocument();
    expect(screen.getByText('4 files inventoried')).toBeInTheDocument();
    expect(await screen.findByText('Data are ready for workflow review.')).toBeInTheDocument();
  });

  it('selects the newly uploaded series before recommending the next workflow', async () => {
    vi.mocked(api.getResultSummary).mockResolvedValue(mockT1Summary);
    vi.mocked(api.listWorkflows).mockResolvedValue({ workflows: ['t1_deepprep', 'dwi_fast_gpu_dti'] });
    vi.mocked(api.listProjectTasks).mockResolvedValue([]);
    vi.mocked(api.listSeries).mockResolvedValue([mockSeries[0], mockSeries[2]]);
    vi.mocked(api.uploadDwi).mockResolvedValue({ files: [], series: mockSeries[2] });
    vi.mocked(api.runAgent).mockResolvedValue({ answer: 'Upload guidance.' });
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

    expect(await screen.findByText(/Pipeline: t1_deepprep/)).toBeInTheDocument();

    await userEvent.upload(await screen.findByLabelText('Upload files'), [
      new File(['nifti'], 'sub-01_dwi.nii.gz'),
      new File(['bval'], 'sub-01_dwi.bval'),
      new File(['bvec'], 'sub-01_dwi.bvec'),
      new File(['{}'], 'sub-01_dwi.json'),
    ]);

    expect(await screen.findByText(/Pipeline: dwi_fast_gpu_dti/)).toBeInTheDocument();
  });

  it('recomputes the recommended workflow when the user changes input series', async () => {
    vi.mocked(api.getResultSummary).mockResolvedValue(mockT1Summary);
    vi.mocked(api.listWorkflows).mockResolvedValue({ workflows: ['t1_deepprep', 't1_deepprep_anat_report', 'dwi_fast_gpu_dti'] });
    vi.mocked(api.listProjectTasks).mockResolvedValue([]);
    vi.mocked(api.listSeries).mockResolvedValue([mockSeries[0], mockSeries[2]]);
    vi.mocked(api.runAgent).mockResolvedValue({ answer: 'Use the selected data.' });
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

    expect(await screen.findByText(/Pipeline: t1_deepprep/)).toBeInTheDocument();

    await userEvent.click(screen.getByText('Pipeline Parameters'));
    const workflowSelect = screen.getByDisplayValue('t1_deepprep');
    await userEvent.selectOptions(workflowSelect, 't1_deepprep_anat_report');
    expect(await screen.findByText(/Pipeline: t1_deepprep_anat_report/)).toBeInTheDocument();

    await userEvent.selectOptions(screen.getByDisplayValue('#22 T1w'), '24');

    expect(await screen.findByText(/Pipeline: dwi_fast_gpu_dti/)).toBeInTheDocument();
  });

  it('shows the workflow block reason in the recommended plan', async () => {
    vi.mocked(api.getResultSummary).mockResolvedValue(mockT1Summary);
    vi.mocked(api.listWorkflows).mockResolvedValue({ workflows: ['t1_deepprep', 'dwi_fast_gpu_dti'] });
    vi.mocked(api.listProjectTasks).mockResolvedValue([]);
    vi.mocked(api.listSeries).mockResolvedValue([mockSeries[0]]);
    vi.mocked(api.runAgent).mockResolvedValue({ answer: 'Use the selected data.' });
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

    const recommendedPlan = (await screen.findByText('Recommended plan')).parentElement;
    expect(recommendedPlan).toHaveTextContent('Pipeline: t1_deepprep');

    await userEvent.click(screen.getByText('Pipeline Parameters'));
    await userEvent.selectOptions(screen.getByDisplayValue('t1_deepprep'), 'dwi_fast_gpu_dti');

    expect(recommendedPlan).toHaveTextContent('Requires a DWI series.');
    expect(screen.getByRole('button', { name: 'Run Workflow' })).toBeDisabled();
    expect(api.runSeries).not.toHaveBeenCalled();
  });

  it('keeps dashboard workflow selection on API-runnable registry entries', async () => {
    const recommendedSeries = {
      ...mockSeries[0],
      workflow_eligibility: {
        blocked_workflows: [],
        policy_version: 'workflow_eligibility_v1',
        primary_recommendation: { workflow_type: 't1_deepprep_anat_report' },
        production_task_created: false,
        runnable_workflows: [{ workflow_type: 't1_deepprep_anat_report' }],
      },
    };
    vi.mocked(api.getResultSummary).mockResolvedValue(mockT1Summary);
    vi.mocked(api.listWorkflows).mockResolvedValue({
      workflows: [
        {
          api_runnable: true,
          lane: 'fixed_workflow',
          requires_confirmation: true,
          runtime_workflow_type: 't1_deepprep',
          type: 't1_deepprep_anat_report',
        },
        {
          api_runnable: false,
          lane: 'toolchain_incubation',
          requires_confirmation: true,
          runtime_workflow_type: 'dwi_qsiprep',
          type: 'dwi_qsiprep',
        },
      ],
    } as never);
    vi.mocked(api.listProjectTasks).mockResolvedValue([]);
    vi.mocked(api.listSeries).mockResolvedValue([recommendedSeries]);
    vi.mocked(api.getTask).mockResolvedValue({
      id: 132,
      progress: 25,
      project_id: 13,
      series_id: 22,
      status: 'running',
      workflow_type: 't1_deepprep_anat_report',
    });
    const confirmation = mockDashboardWorkflowConfirmation({ progress: 25, status: 'running', taskId: 132 });
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

    expect(await screen.findByText(/Pipeline: t1_deepprep_anat_report/)).toBeInTheDocument();
    const workflowSelect = screen.getByDisplayValue('t1_deepprep_anat_report');
    expect(within(workflowSelect).queryByRole('option', { name: 'dwi_qsiprep' })).not.toBeInTheDocument();

    await userEvent.click(screen.getByRole('button', { name: 'Run Workflow' }));

    expect(api.runAgent).toHaveBeenCalledWith(13, expect.stringContaining('t1_deepprep_anat_report'));
    expect(api.runSeries).not.toHaveBeenCalled();
    expect(await screen.findByText('Task not created yet')).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'Approve workflow' }));
    expect(api.resumeAgent).toHaveBeenCalledWith('agent_dashboard_thread', true, confirmation);
    expect(await screen.findByText('Task #132 running')).toBeInTheDocument();
  });

  it('defaults workflow selection to backend primary recommendation', async () => {
    const recommendedSeries = {
      ...mockSeries[0],
      workflow_eligibility: {
        blocked_workflows: [],
        policy_version: 'workflow_eligibility_v1',
        primary_recommendation: { workflow_type: 't1_deepprep_anat_report' },
        production_task_created: false,
        runnable_workflows: [{ workflow_type: 't1_deepprep_anat_report' }],
      },
    };
    vi.mocked(api.getResultSummary).mockResolvedValue(mockT1Summary);
    vi.mocked(api.listWorkflows).mockResolvedValue({ workflows: ['t1_deepprep', 't1_deepprep_anat_report'] });
    vi.mocked(api.listProjectTasks).mockResolvedValue([]);
    vi.mocked(api.listSeries).mockResolvedValue([recommendedSeries]);
    vi.mocked(api.getTask).mockResolvedValue({
      id: 131,
      progress: 42,
      project_id: 13,
      series_id: 22,
      status: 'running',
      workflow_type: 't1_deepprep_anat_report',
    });
    const confirmation = mockDashboardWorkflowConfirmation({ progress: 42, status: 'running' });
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

    expect(await screen.findByText(/Pipeline: t1_deepprep_anat_report/)).toBeInTheDocument();

    await userEvent.click(screen.getByRole('button', { name: 'Run Workflow' }));
    expect(api.runAgent).toHaveBeenCalledWith(13, expect.stringContaining('t1_deepprep_anat_report'));
    expect(api.runSeries).not.toHaveBeenCalled();
    await userEvent.click(await screen.findByRole('button', { name: 'Approve workflow' }));
    expect(api.resumeAgent).toHaveBeenCalledWith('agent_dashboard_thread', true, confirmation);
    expect(await screen.findByText('Task #131 running')).toBeInTheDocument();
    expect(screen.getByText('Progress: 42%')).toBeInTheDocument();
    expect(screen.getByText('Workflow: t1_deepprep_anat_report')).toBeInTheDocument();
  });

  it('links a completed launched task to its result page', async () => {
    const recommendedSeries = {
      ...mockSeries[0],
      workflow_eligibility: {
        blocked_workflows: [],
        policy_version: 'workflow_eligibility_v1',
        primary_recommendation: { workflow_type: 't1_deepprep_anat_report' },
        production_task_created: false,
        runnable_workflows: [{ workflow_type: 't1_deepprep_anat_report' }],
      },
    };
    vi.mocked(api.getResultSummary).mockResolvedValue(mockT1Summary);
    vi.mocked(api.listWorkflows).mockResolvedValue({ workflows: ['t1_deepprep', 't1_deepprep_anat_report'] });
    vi.mocked(api.listProjectTasks).mockResolvedValue([]);
    vi.mocked(api.listSeries).mockResolvedValue([recommendedSeries]);
    vi.mocked(api.getTask).mockResolvedValue({
      id: 131,
      progress: 100,
      project_id: 13,
      series_id: 22,
      status: 'completed',
      workflow_type: 't1_deepprep_anat_report',
    });
    mockDashboardWorkflowConfirmation({ progress: 100, status: 'completed' });
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

    expect(await screen.findByText(/Pipeline: t1_deepprep_anat_report/)).toBeInTheDocument();

    await userEvent.click(screen.getByRole('button', { name: 'Run Workflow' }));
    await userEvent.click(await screen.findByRole('button', { name: 'Approve workflow' }));

    expect(await screen.findByText('Task #131 completed')).toBeInTheDocument();
    expect(screen.getByText('Progress: 100%')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'View task results' })).toHaveAttribute('href', '/projects/13/results/131');
  });

  it('uses the completed launched task for the results preview before the task list refreshes', async () => {
    const recommendedSeries = {
      ...mockSeries[0],
      workflow_eligibility: {
        blocked_workflows: [],
        policy_version: 'workflow_eligibility_v1',
        primary_recommendation: { workflow_type: 't1_deepprep_anat_report' },
        production_task_created: false,
        runnable_workflows: [{ workflow_type: 't1_deepprep_anat_report' }],
      },
    };
    vi.mocked(api.getResultSummary).mockResolvedValue({ ...mockT1Summary, task_id: 131, workflow_type: 't1_deepprep_anat_report' });
    vi.mocked(api.listWorkflows).mockResolvedValue({ workflows: ['t1_deepprep_anat_report'] });
    vi.mocked(api.listProjectTasks).mockResolvedValue([]);
    vi.mocked(api.listSeries).mockResolvedValue([recommendedSeries]);
    vi.mocked(api.getTask).mockResolvedValue({
      id: 131,
      progress: 100,
      project_id: 13,
      series_id: 22,
      status: 'completed',
      workflow_type: 't1_deepprep_anat_report',
    });
    mockDashboardWorkflowConfirmation({ progress: 100, status: 'completed' });
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

    await userEvent.click(await screen.findByRole('button', { name: 'Run Workflow' }));
    await userEvent.click(await screen.findByRole('button', { name: 'Approve workflow' }));

    expect(await screen.findByText('Task #131 completed')).toBeInTheDocument();
    expect(api.getResultSummary).toHaveBeenCalledWith(131);
    expect(screen.getByRole('link', { name: /view full results/i })).toHaveAttribute('href', '/projects/13/results/131');
    expect(screen.getAllByText('t1_deepprep_anat_report').length).toBeGreaterThan(1);
  });

  it('labels the results preview with the completed task workflow while the summary is still loading', async () => {
    const recommendedSeries = {
      ...mockSeries[0],
      workflow_eligibility: {
        blocked_workflows: [],
        policy_version: 'workflow_eligibility_v1',
        primary_recommendation: { workflow_type: 't1_deepprep_anat_report' },
        production_task_created: false,
        runnable_workflows: [{ workflow_type: 't1_deepprep_anat_report' }, { workflow_type: 't1_deepprep_mock' }],
      },
    };
    vi.mocked(api.getResultSummary).mockImplementation(() => new Promise(() => {}));
    vi.mocked(api.listWorkflows).mockResolvedValue({ workflows: ['t1_deepprep_anat_report', 't1_deepprep_mock'] });
    vi.mocked(api.listProjectTasks).mockResolvedValue([
      {
        id: 131,
        progress: 100,
        project_id: 13,
        series_id: 22,
        status: 'completed',
        workflow_type: 't1_deepprep_mock',
      },
    ]);
    vi.mocked(api.listSeries).mockResolvedValue([recommendedSeries]);
    vi.mocked(api.runAgent).mockResolvedValue({ answer: 'Use backend recommendation.' });
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

    const preview = await screen.findByTestId('results-preview');

    expect(within(preview).getByText('t1_deepprep_mock')).toBeInTheDocument();
    expect(within(preview).queryByText('t1_deepprep_anat_report')).not.toBeInTheDocument();
  });

  it('uses workflow display names in dashboard observation surfaces while keeping stable ids visible', async () => {
    const displayName = 'T1 DeepPrep anatomical processing, QC, and report';
    const recommendedSeries = {
      ...mockSeries[0],
      sequence_label: '',
      workflow_eligibility: {
        blocked_workflows: [],
        policy_version: 'workflow_eligibility_v1',
        primary_recommendation: { workflow_type: 't1_deepprep_anat_report' },
        production_task_created: false,
        runnable_workflows: [{ workflow_type: 't1_deepprep_anat_report' }],
      },
    };
    vi.mocked(api.getResultSummary).mockResolvedValue({ ...mockT1Summary, task_id: 232, workflow_type: 't1_deepprep_anat_report' });
    vi.mocked(api.listWorkflows).mockResolvedValue({
      workflows: [
        {
          capability_summary: 'Runs full T1 anatomical processing, QC, and report outputs.',
          display_name: displayName,
          lane: 'fixed_workflow',
          requires_confirmation: true,
          runtime_workflow_type: 't1_deepprep',
          type: 't1_deepprep_anat_report',
        },
      ],
    });
    vi.mocked(api.listProjectTasks).mockResolvedValue([
      {
        id: 231,
        progress: 40,
        project_id: 13,
        series_id: recommendedSeries.id,
        status: 'running',
        workflow_type: 't1_deepprep_anat_report',
      },
      {
        id: 232,
        progress: 100,
        project_id: 13,
        series_id: recommendedSeries.id,
        status: 'completed',
        workflow_type: 't1_deepprep_anat_report',
      },
    ]);
    vi.mocked(api.listSeries).mockResolvedValue([recommendedSeries]);
    vi.mocked(api.runAgent).mockResolvedValue({ answer: 'Use backend recommendation.' });
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

    expect(await screen.findByText(`Pipeline: ${displayName}`)).toBeInTheDocument();
    expect(screen.getAllByText(displayName).length).toBeGreaterThanOrEqual(2);
    expect(screen.getAllByText('Stable workflow ID: t1_deepprep_anat_report').length).toBeGreaterThanOrEqual(1);
    expect(within(screen.getByTestId('results-preview')).getByText(displayName)).toBeInTheDocument();
  });

  it('renders result preview images only from backend artifact download urls', async () => {
    vi.mocked(api.getResultSummary).mockResolvedValue(mockT1Summary);
    vi.mocked(api.listWorkflows).mockResolvedValue({ workflows: ['t1_deepprep'] });
    vi.mocked(api.listProjectTasks).mockResolvedValue(mockTasks);
    vi.mocked(api.listSeries).mockResolvedValue(mockSeries);
    vi.mocked(api.runAgent).mockResolvedValue({ answer: 'Use backend artifacts.' });
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

    const preview = await screen.findByAltText('reports/t1_brain_measures_overview.png');
    expect(preview).toHaveAttribute('src', 'blob:http://localhost/authenticated-dashboard-artifact');
    expect(api.getArtifactUrl).toHaveBeenCalledWith(expect.any(Number), 'reports/t1_brain_measures_overview.png');
    expect(screen.queryByAltText('T1w axial MRI preview')).not.toBeInTheDocument();
  });

  it('does not show static T1 reference previews when backend image artifacts are unavailable', async () => {
    vi.mocked(api.getResultSummary).mockResolvedValue({ ...mockT1Summary, outputs: { tables: mockT1Summary.outputs.tables } });
    vi.mocked(api.listWorkflows).mockResolvedValue({ workflows: ['t1_deepprep'] });
    vi.mocked(api.listProjectTasks).mockResolvedValue(mockTasks);
    vi.mocked(api.listSeries).mockResolvedValue([{ ...mockSeries[0], project_id: 1 }]);
    vi.mocked(api.runAgent).mockResolvedValue({ answer: 'Native preview artifacts are unavailable.' });
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });

    render(
      <QueryClientProvider client={client}>
        <MemoryRouter initialEntries={['/projects/1/dashboard']}>
          <Routes>
            <Route element={<DashboardPage />} path="/projects/:projectId/dashboard" />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>,
    );

    expect(await screen.findByText('No native QC preview images available for this run.')).toBeInTheDocument();
    expect(screen.queryByAltText('T1w axial MRI preview')).not.toBeInTheDocument();
    expect(screen.queryByAltText('T1w sagittal MRI preview')).not.toBeInTheDocument();
    expect(screen.queryByAltText('T1w coronal MRI preview')).not.toBeInTheDocument();
    expect(screen.queryByAltText('Axial tissue segmentation preview')).not.toBeInTheDocument();
    expect(screen.queryByText('Gray Matter')).not.toBeInTheDocument();
  });

  it('prefers artifact manifest previews over generated result summary previews', async () => {
    vi.mocked(api.getArtifactManifest).mockResolvedValue({
      artifacts: [
        {
          content_type: 'image/png',
          download_url: '/tasks/41/artifacts/qc/container-native-qc.png',
          feature_group: 'container_qc',
          native_artifact: true,
          preview_kind: 'image',
          relative_path: 'qc/container-native-qc.png',
          size_bytes: 2048,
        },
        {
          content_type: 'text/html',
          download_url: '/tasks/41/artifacts/qc/index.html',
          feature_group: 'container_qc',
          native_artifact: true,
          preview_kind: 'html',
          relative_path: 'qc/index.html',
          size_bytes: 4096,
        },
      ],
      contract_version: 'artifact_manifest_v1',
      task_id: 41,
    });
    vi.mocked(api.getResultSummary).mockResolvedValue(mockT1Summary);
    vi.mocked(api.listWorkflows).mockResolvedValue({ workflows: ['t1_deepprep'] });
    vi.mocked(api.listProjectTasks).mockResolvedValue([mockTasks[0]]);
    vi.mocked(api.listSeries).mockResolvedValue(mockSeries);
    vi.mocked(api.runAgent).mockResolvedValue({ answer: 'Use backend artifacts.' });
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

    expect(await screen.findByAltText('qc/container-native-qc.png')).toHaveAttribute('src', 'blob:http://localhost/authenticated-dashboard-artifact');
    expect(api.getArtifactUrl).toHaveBeenCalledWith(41, 'qc/container-native-qc.png');
    expect(api.getArtifactManifest).toHaveBeenCalledWith(41);
    expect(screen.queryByAltText('reports/t1_brain_measures_overview.png')).not.toBeInTheDocument();
  });

  it('shows the Agent run error instead of falling back to legacy chat', async () => {
    vi.mocked(api.getResultSummary).mockResolvedValue(mockT1Summary);
    vi.mocked(api.listWorkflows).mockResolvedValue({ workflows: ['t1_deepprep'] });
    vi.mocked(api.listProjectTasks).mockResolvedValue(mockTasks);
    vi.mocked(api.listSeries).mockResolvedValue(mockSeries);
    vi.mocked(api.runAgent).mockRejectedValue(new Error('Agent run unavailable.'));
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

    await userEvent.click(await screen.findByLabelText('Open Agent Copilot'));

    await userEvent.click(await screen.findByRole('button', { name: 'Explain this step' }));

    expect(api.runAgent).toHaveBeenCalledWith(13, 'Explain this step');
    expect(await screen.findByText('Agent run unavailable.')).toBeInTheDocument();
  });

  it('clears a stale dashboard approval card when a later chat answer has no Agent confirmation response', async () => {
    const confirmation = {
      action_lane: 'fixed_workflow',
      project_id: 13,
      series_id: 22,
      type: 'workflow_execution',
      workflow_metadata: {
        display_name: 'T1 DeepPrep anatomical processing, QC, and report',
        workflow_type: 't1_deepprep_anat_report',
      },
      workflow_type: 't1_deepprep_anat_report',
    };
    vi.mocked(api.getResultSummary).mockResolvedValue(mockT1Summary);
    vi.mocked(api.listWorkflows).mockResolvedValue({ workflows: ['t1_deepprep_anat_report'] });
    vi.mocked(api.listProjectTasks).mockResolvedValue(mockTasks);
    vi.mocked(api.listSeries).mockResolvedValue(mockSeries);
    vi.mocked(api.runAgent)
      .mockResolvedValueOnce({
        answer: 'Approval required for t1_deepprep_anat_report.',
        confirmation,
        status: 'confirmation_required',
        thread_id: 'agent_thread_1',
      })
      .mockResolvedValueOnce({ answer: '这里是只读回答，不会启动任何任务。' });
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

    await userEvent.click(await screen.findByLabelText('Open Agent Copilot'));
    await userEvent.click(await screen.findByRole('button', { name: 'Prepare selected workflow' }));

    expect(await screen.findByText('Approval required')).toBeInTheDocument();

    const input = screen.getByPlaceholderText('Ask the agent...');
    await userEvent.type(input, '我上传了什么文件，可以跑什么任务{enter}');

    expect(await screen.findByText('这里是只读回答，不会启动任何任务。')).toBeInTheDocument();
    expect(screen.queryByText('Task not created yet')).not.toBeInTheDocument();
    expect(screen.queryByText('Approval required')).not.toBeInTheDocument();
  });

  it('refreshes project tasks when a dashboard Agent run creates a backend task', async () => {
    vi.mocked(api.getResultSummary).mockResolvedValue(mockT1Summary);
    vi.mocked(api.listWorkflows).mockResolvedValue({ workflows: ['t1_deepprep'] });
    vi.mocked(api.listProjectTasks).mockResolvedValue(mockTasks);
    vi.mocked(api.listSeries).mockResolvedValue(mockSeries);
    vi.mocked(api.runAgent).mockResolvedValue({
      answer: 'Task 144 created for t1_deepprep.',
      status: 'task_created',
      task: { id: 144, progress: 0, project_id: 13, series_id: 22, status: 'queued', workflow_type: 't1_deepprep' },
    });
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const invalidate = vi.spyOn(client, 'invalidateQueries');

    render(
      <QueryClientProvider client={client}>
        <MemoryRouter initialEntries={['/projects/13/dashboard']}>
          <Routes>
            <Route element={<DashboardPage />} path="/projects/:projectId/dashboard" />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>,
    );

    await userEvent.click(await screen.findByLabelText('Open Agent Copilot'));

    await userEvent.click(await screen.findByRole('button', { name: 'Explain this step' }));

    expect(await screen.findByText('Task 144 created for t1_deepprep.')).toBeInTheDocument();
    expect(invalidate).toHaveBeenCalledWith({ queryKey: queryKeys.tasks(13) });
    expect(invalidate).toHaveBeenCalledWith({ queryKey: queryKeys.task(144) });
  });

  it('approves an Agent workflow confirmation from the floating dashboard drawer', async () => {
    const confirmation = {
      action_lane: 'fixed_workflow',
      project_id: 13,
      series_id: 22,
      type: 'workflow_execution',
      workflow_metadata: {
        capability_summary: 'Runs full T1 anatomical processing, container-native QC, and report outputs.',
        display_name: 'T1 DeepPrep anatomical processing, QC, and report',
        runtime_workflow_type: 't1_deepprep',
        workflow_type: 't1_deepprep_anat_report',
      },
      workflow_type: 't1_deepprep_anat_report',
    };
    vi.mocked(api.getResultSummary).mockResolvedValue(mockT1Summary);
    vi.mocked(api.listWorkflows).mockResolvedValue({ workflows: ['t1_deepprep_anat_report'] });
    vi.mocked(api.listProjectTasks).mockResolvedValue(mockTasks);
    vi.mocked(api.listSeries).mockResolvedValue(mockSeries);
    vi.mocked(api.runAgent).mockResolvedValue({
      answer: 'Approval required for t1_deepprep_anat_report.',
      confirmation,
      status: 'confirmation_required',
      thread_id: 'agent_thread_1',
    });
    vi.mocked(api.resumeAgent).mockResolvedValue({
      answer: 'Task 155 created for t1_deepprep.',
      status: 'task_created',
      task: { id: 155, progress: 0, project_id: 13, series_id: 22, status: 'queued', workflow_type: 't1_deepprep' },
    });
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const invalidate = vi.spyOn(client, 'invalidateQueries');

    render(
      <QueryClientProvider client={client}>
        <MemoryRouter initialEntries={['/projects/13/dashboard']}>
          <Routes>
            <Route element={<DashboardPage />} path="/projects/:projectId/dashboard" />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>,
    );

    await userEvent.click(await screen.findByLabelText('Open Agent Copilot'));
    await userEvent.click(await screen.findByRole('button', { name: 'Explain this step' }));

    expect(await screen.findByText('Approval required for t1_deepprep_anat_report.')).toBeInTheDocument();
    expect(screen.getByText('T1 DeepPrep anatomical processing, QC, and report')).toBeInTheDocument();
    expect(screen.getByText('Runs full T1 anatomical processing, container-native QC, and report outputs.')).toBeInTheDocument();
    expect(screen.getByText('Stable workflow ID')).toBeInTheDocument();
    expect(screen.getByText('Task not created yet')).toBeInTheDocument();

    await userEvent.click(screen.getByRole('button', { name: 'Approve workflow' }));

    expect(api.resumeAgent).toHaveBeenCalledWith('agent_thread_1', true, confirmation);
    expect(await screen.findByText('Task 155 created for t1_deepprep.')).toBeInTheDocument();
    expect(screen.queryByText('Task not created yet')).not.toBeInTheDocument();
    expect(invalidate).toHaveBeenCalledWith({ queryKey: queryKeys.tasks(13) });
    expect(invalidate).toHaveBeenCalledWith({ queryKey: queryKeys.task(155) });
  });

  it('passes the completed QSIPrep task id when the dashboard launches recommended QSIRecon', async () => {
    const recommendedDwi = {
      ...mockSeries[2],
      workflow_eligibility: {
        blocked_workflows: [],
        policy_version: 'workflow_eligibility_v1',
        primary_recommendation: { workflow_type: 'dwi_qsirecon' },
        production_task_created: false,
        runnable_workflows: [{ workflow_type: 'dwi_qsirecon' }],
      },
    };
    vi.mocked(api.getResultSummary).mockResolvedValue(mockT1Summary);
    vi.mocked(api.listWorkflows).mockResolvedValue({ workflows: ['dwi_qsirecon'] });
    vi.mocked(api.listProjectTasks).mockResolvedValue([
      { ...mockTasks[0], id: 188, series_id: recommendedDwi.id, status: 'completed', workflow_type: 'dwi_qsiprep' },
    ]);
    vi.mocked(api.listSeries).mockResolvedValue([recommendedDwi]);
    mockDashboardWorkflowConfirmation({
      seriesId: recommendedDwi.id,
      taskId: 189,
      taskWorkflowType: 'dwi_qsirecon',
      workflowType: 'dwi_qsirecon',
    });
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

    expect(await screen.findByText(/Pipeline: dwi_qsirecon/)).toBeInTheDocument();

    await userEvent.click(screen.getByRole('button', { name: 'Run Workflow' }));

    expect(api.runAgent).toHaveBeenCalledWith(13, expect.stringContaining('dwi_qsirecon'));
    expect(api.runAgent).toHaveBeenCalledWith(13, expect.stringContaining('QSIPrep task 188'));
    expect(api.runSeries).not.toHaveBeenCalled();
  });

  it('renders the processing console with backend-backed upload, workflow, run, and result sections', async () => {
    vi.mocked(api.getResultSummary).mockResolvedValue(mockT1Summary);
    vi.mocked(api.listWorkflows).mockResolvedValue({ workflows: ['t1_deepprep', 'bold_second_level', 'dwi_fast_gpu_dti'] });
    vi.mocked(api.listProjectTasks).mockResolvedValue(mockTasks);
    vi.mocked(api.listSeries).mockResolvedValue(mockSeries);
    vi.mocked(api.runAgent).mockResolvedValue({ answer: 'Agent status: project has tasks and workflow evidence.' });
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

    expect(await screen.findByRole('heading', { name: 'Brain Imaging Processing Agent' })).toBeInTheDocument();
    expect(screen.getByText('Upload Data')).toBeInTheDocument();
    expect(screen.getByText('Workflow Status')).toBeInTheDocument();
    expect(screen.getByText('Pipeline Parameters')).toBeInTheDocument();
    expect(screen.getByText('Recent Runs')).toBeInTheDocument();
    expect(screen.getByText('Results Preview')).toBeInTheDocument();
    expect(screen.getByLabelText('Upload files')).toBeInTheDocument();
    expect(await screen.findByText('RUN-41')).toBeInTheDocument();
    expect((await screen.findAllByText('reports/t1_brain_measures_overview.png')).length).toBeGreaterThan(0);

    // Verify chat elements
    await userEvent.click(screen.getByLabelText('Open Agent Copilot'));
    expect(screen.getByPlaceholderText('Ask the agent...')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Explain this step' })).toBeInTheDocument();

    // Test quick action
    await userEvent.click(screen.getByRole('button', { name: 'Explain this step' }));
    expect(api.runAgent).toHaveBeenCalledWith(13, 'Explain this step');
    expect(await screen.findByText('Agent status: project has tasks and workflow evidence.')).toBeInTheDocument();

    // Test typed message
    const input = screen.getByPlaceholderText('Ask the agent...');
    await userEvent.type(input, 'Tell me more{enter}');
    expect(api.runAgent).toHaveBeenCalledWith(13, 'Tell me more');

    // Test dashboard workflow launch goes through Agent confirmation preparation.
    await userEvent.click(screen.getByRole('button', { name: 'Run Workflow' }));
    expect(api.runAgent).toHaveBeenCalledWith(13, expect.stringContaining('Prepare workflow'));
    expect(api.runSeries).not.toHaveBeenCalled();
  });

  it('uses workflow catalog display names while preserving workflow ids for launch', async () => {
    vi.mocked(api.listWorkflows).mockResolvedValue({
      workflows: [
        {
          capability_summary: 'Runs full BOLD preprocessing, XCP-D derived metrics, QC, and report outputs.',
          display_name: 'BOLD fMRIPrep + XCP-D processing, metrics, QC, and report',
          lane: 'fixed_workflow',
          requires_confirmation: true,
          runtime_workflow_type: 'bold_fmriprep_xcpd_report',
          type: 'bold_fmriprep_xcpd_report',
        },
      ],
    });
    vi.mocked(api.listSeries).mockResolvedValue([{ ...mockSeries[1], modality: 'BOLD' }]);
    vi.mocked(api.listProjectTasks).mockResolvedValue([]);

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

    const option = await screen.findByRole('option', { name: /BOLD fMRIPrep \+ XCP-D processing, metrics, QC, and report/ });
    expect(option).toHaveValue('bold_fmriprep_xcpd_report');
  });

  it('renders Agent Copilot as a floating drawer that can collapse and expand', async () => {
    vi.mocked(api.listWorkflows).mockResolvedValue({ workflows: ['t1_deepprep'] });
    vi.mocked(api.listProjectTasks).mockResolvedValue([]);
    vi.mocked(api.listSeries).mockResolvedValue([]);
    vi.mocked(api.runAgent).mockResolvedValue({ answer: 'Initial greeting.' });
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

    // Should be closed by default
    expect(await screen.findByLabelText('Open Agent Copilot')).toBeInTheDocument();
    expect(screen.queryByLabelText('Collapse Agent Copilot')).not.toBeInTheDocument();

    // Expand it
    await userEvent.click(screen.getByLabelText('Open Agent Copilot'));
    expect(await screen.findByLabelText('Collapse Agent Copilot')).toBeInTheDocument();
    expect(screen.queryByLabelText('Open Agent Copilot')).not.toBeInTheDocument();

    // Collapse it
    await userEvent.click(screen.getByLabelText('Collapse Agent Copilot'));
    expect(screen.queryByLabelText('Collapse Agent Copilot')).not.toBeInTheDocument();
    expect(screen.getByLabelText('Open Agent Copilot')).toBeInTheDocument();
  });
});
