import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { api } from '../lib/api';
import { mockSeries, mockT1Summary, mockTasks } from '../mocks/data';
import { DashboardPage } from './DashboardPage';

vi.mock('../lib/api', () => ({
  api: {
    getResultSummary: vi.fn(),
    listWorkflows: vi.fn(),
    listProjectTasks: vi.fn(),
    listSeries: vi.fn(),
    runSeries: vi.fn(),
    uploadDicom: vi.fn(),
    uploadDwi: vi.fn(),
    uploadNifti: vi.fn(),
    chat: vi.fn(),
  },
}));

describe('DashboardPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('updates the initial agent greeting when series load after workflows', async () => {
    vi.mocked(api.getResultSummary).mockResolvedValue(mockT1Summary);
    vi.mocked(api.listWorkflows).mockResolvedValue({ workflows: ['t1_deepprep_anat_report'] });
    vi.mocked(api.listProjectTasks).mockResolvedValue([]);
    vi.mocked(api.listSeries).mockResolvedValueOnce([]).mockResolvedValue([mockSeries[0]]);
    vi.mocked(api.chat).mockResolvedValue({ reply: 'Upload guidance.' });
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

    expect(await screen.findByText(/I haven't found any brain imaging data yet/)).toBeInTheDocument();

    await userEvent.upload(await screen.findByLabelText('Upload DICOM, NIfTI, or DWI sidecar set'), new File(['nifti'], 'sub-01_T1w.nii.gz'));

    expect((await screen.findAllByText(/I found 1 brain MRI scan/)).length).toBeGreaterThan(0);
    expect(screen.queryByText(/I haven't found any brain imaging data yet/)).not.toBeInTheDocument();
  });

  it('uses the backend upload contract and refreshes detected series after upload', async () => {
    vi.mocked(api.getResultSummary).mockResolvedValue(mockT1Summary);
    vi.mocked(api.listWorkflows).mockResolvedValue({ workflows: ['t1_deepprep'] });
    vi.mocked(api.listProjectTasks).mockResolvedValue([]);
    vi.mocked(api.listSeries).mockResolvedValueOnce([]).mockResolvedValue([mockSeries[0]]);
    vi.mocked(api.uploadNifti).mockResolvedValue({ file: {}, series: mockSeries[0] });
    vi.mocked(api.chat).mockResolvedValue({ reply: 'Upload guidance.' });
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

    const uploadInput = await screen.findByLabelText('Upload DICOM, NIfTI, or DWI sidecar set');
    expect(uploadInput).toHaveAttribute('accept', '.nii,.nii.gz,.zip,.bval,.bvec,.json');

    await userEvent.upload(uploadInput, new File(['nifti'], 'sub-01_T1w.nii.gz'));

    expect(api.uploadNifti).toHaveBeenCalledWith(13, expect.any(File));
    expect((await screen.findAllByText(/I found 1 brain MRI scan/)).length).toBeGreaterThan(0);
    expect(await screen.findByText(/Pipeline: t1_deepprep/)).toBeInTheDocument();
  });

  it('uploads a complete DWI sidecar set through the dashboard backend contract', async () => {
    vi.mocked(api.getResultSummary).mockResolvedValue(mockT1Summary);
    vi.mocked(api.listWorkflows).mockResolvedValue({ workflows: ['dwi_fast_gpu_dti'] });
    vi.mocked(api.listProjectTasks).mockResolvedValue([]);
    vi.mocked(api.listSeries).mockResolvedValueOnce([]).mockResolvedValue([mockSeries[1]]);
    vi.mocked(api.uploadDwi).mockResolvedValue({ files: [], series: mockSeries[1] });
    vi.mocked(api.chat).mockResolvedValue({ reply: 'Upload guidance.' });
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

    const uploadInput = await screen.findByLabelText('Upload DICOM, NIfTI, or DWI sidecar set');
    expect(uploadInput).toHaveAttribute('multiple');
    expect(uploadInput).toHaveAttribute('accept', '.nii,.nii.gz,.zip,.bval,.bvec,.json');

    const nifti = new File(['nifti'], 'sub-01_dwi.nii.gz');
    const bval = new File(['bval'], 'sub-01_dwi.bval');
    const bvec = new File(['bvec'], 'sub-01_dwi.bvec');
    const json = new File(['{}'], 'sub-01_dwi.json');
    await userEvent.upload(uploadInput, [nifti, bval, bvec, json]);

    expect(api.uploadDwi).toHaveBeenCalledWith(13, { nifti, bval, bvec, jsonSidecar: json });
    expect(api.uploadNifti).not.toHaveBeenCalled();
    expect((await screen.findAllByText(/I found 1 brain MRI scan/)).length).toBeGreaterThan(0);
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
    vi.mocked(api.runSeries).mockResolvedValue({
      id: 131,
      progress: 0,
      project_id: 13,
      series_id: 22,
      status: 'queued',
      workflow_type: 't1_deepprep_anat_report',
    });
    vi.mocked(api.chat).mockResolvedValue({ reply: 'Use backend recommendation.' });
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

    await userEvent.click(screen.getByRole('button', { name: 'Start recommended pipeline' }));
    expect(api.runSeries).toHaveBeenCalledWith(22, 't1_deepprep_anat_report');
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
    vi.mocked(api.runSeries).mockResolvedValue({
      id: 189,
      progress: 0,
      project_id: 13,
      qsiprep_task_id: 188,
      series_id: recommendedDwi.id,
      status: 'queued',
      workflow_type: 'dwi_qsirecon',
    });
    vi.mocked(api.chat).mockResolvedValue({ reply: 'Use QSIRecon.' });
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

    await userEvent.click(screen.getByRole('button', { name: 'Start recommended pipeline' }));

    expect(api.runSeries).toHaveBeenCalledWith(recommendedDwi.id, 'dwi_qsirecon', 188);
  });

  it('renders the processing console with backend-backed upload, workflow, run, and result sections', async () => {
    vi.mocked(api.getResultSummary).mockResolvedValue(mockT1Summary);
    vi.mocked(api.listWorkflows).mockResolvedValue({ workflows: ['t1_deepprep', 'bold_second_level', 'dwi_fast_gpu_dti'] });
    vi.mocked(api.listProjectTasks).mockResolvedValue(mockTasks);
    vi.mocked(api.listSeries).mockResolvedValue(mockSeries);
    vi.mocked(api.runSeries).mockResolvedValue({ id: 130, progress: 0, project_id: 13, series_id: 22, status: 'queued', workflow_type: 't1_deepprep' });
    vi.mocked(api.chat).mockResolvedValue({ reply: 'I can help you with that.' });
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
    expect(screen.getByLabelText('Upload DICOM, NIfTI, or DWI sidecar set')).toBeInTheDocument();
    expect(await screen.findByText('RUN-41')).toBeInTheDocument();
    expect(await screen.findByText('reports/t1_brain_measures_overview.png')).toBeInTheDocument();

    // Verify chat elements
    expect(screen.getByPlaceholderText('Ask the agent...')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Explain this step' })).toBeInTheDocument();

    // Test quick action
    await userEvent.click(screen.getByRole('button', { name: 'Explain this step' }));
    expect(api.chat).toHaveBeenCalledWith(13, 'Explain this step');

    // Test typed message
    const input = screen.getByPlaceholderText('Ask the agent...');
    await userEvent.type(input, 'Tell me more{enter}');
    expect(api.chat).toHaveBeenCalledWith(13, 'Tell me more');

    // Test original run behavior
    await userEvent.click(screen.getByRole('button', { name: 'Start recommended pipeline' }));
    expect(api.runSeries).toHaveBeenCalledWith(22, 't1_deepprep');
  });
});
