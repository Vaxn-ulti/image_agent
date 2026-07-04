import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { api } from '../lib/api';
import { mockDwiSummary } from '../mocks/data';
import { ResultDetailPage } from './ResultDetailPage';

vi.mock('../lib/api', () => ({
  api: {
    getArtifactManifest: vi.fn(),
    getArtifactUrl: vi.fn(),
    getResultSummary: vi.fn(),
    getTaskExportBundle: vi.fn(),
    createTaskExportBundleTicket: vi.fn(),
    listWorkflows: vi.fn(),
  },
  getApiBase: () => 'http://localhost:8000',
}));

describe('ResultDetailPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(api.getArtifactManifest).mockResolvedValue({ artifacts: [], contract_version: 'artifact_manifest_v1', task_id: 0 });
    vi.mocked(api.getArtifactUrl).mockResolvedValue(new Blob(['image'], { type: 'image/png' }));
    vi.mocked(api.getTaskExportBundle).mockResolvedValue(new Blob(['zip'], { type: 'application/zip' }));
    vi.mocked(api.createTaskExportBundleTicket).mockResolvedValue({ download_url: '/tasks/114/export-bundle-download?ticket=abc', expires_at: 1780000000, task_id: 114 });
    vi.mocked(api.listWorkflows).mockResolvedValue({ workflows: [] });
    URL.createObjectURL = vi.fn();
    URL.revokeObjectURL = vi.fn();
    vi.spyOn(URL, 'createObjectURL').mockReturnValue('blob:http://localhost/authenticated-artifact');
    vi.spyOn(URL, 'revokeObjectURL').mockImplementation(() => undefined);
  });

  it('renders result-summary feature groups and artifacts', async () => {
    vi.mocked(api.getResultSummary).mockResolvedValue({ ...mockDwiSummary, project_id: 13 });
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });

    render(
      <QueryClientProvider client={client}>
        <MemoryRouter initialEntries={['/projects/13/results/114']}>
          <Routes>
            <Route element={<ResultDetailPage />} path="/projects/:projectId/results/:taskId" />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>,
    );

    expect(await screen.findByText('Modality')).toBeInTheDocument();
    expect((await screen.findAllByText('native_dti_maps')).length).toBeGreaterThanOrEqual(1);
    expect(await screen.findByText('maps/fa.nii.gz')).toBeInTheDocument();
    expect((await screen.findAllByText(/runtime_sec/)).length).toBeGreaterThanOrEqual(1);
    expect(await screen.findByText(/Scientific report/)).toBeInTheDocument();
    expect(await screen.findByText(/reports\/index.html/)).toBeInTheDocument();
    expect(await screen.findByText('dwi_tensor_metrics.png')).toBeInTheDocument();
    expect(await screen.findByAltText(/Scientific figure reports\/dwi_tensor_metrics.png/)).toHaveAttribute('src', 'blob:http://localhost/authenticated-artifact');
    expect(api.getArtifactUrl).toHaveBeenCalledWith(114, 'reports/dwi_tensor_metrics.png');
    expect(await screen.findByRole('heading', { name: 'Scientific Results Studio' })).toBeInTheDocument();
    expect(await screen.findByText('DWI tensor map matrix')).toBeInTheDocument();
    expect(await screen.findByText('Atlas regional distribution')).toBeInTheDocument();
    expect(await screen.findByText('Evidence chain')).toBeInTheDocument();
  });

  it('uses workflow catalog display names in the result header while preserving stable workflow ids', async () => {
    vi.mocked(api.getResultSummary).mockResolvedValue({ ...mockDwiSummary, project_id: 13 });
    vi.mocked(api.listWorkflows).mockResolvedValue({
      workflows: [
        {
          api_runnable: true,
          display_name: 'DWI fast GPU tensor processing, QC, and report',
          lane: 'fixed_workflow',
          requires_confirmation: true,
          runtime_workflow_type: 'dwi_fast_gpu_dti',
          type: 'dwi_fast_gpu_dti',
        },
      ],
    });
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });

    render(
      <QueryClientProvider client={client}>
        <MemoryRouter initialEntries={['/projects/13/results/114']}>
          <Routes>
            <Route element={<ResultDetailPage />} path="/projects/:projectId/results/:taskId" />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>,
    );

    expect(
      await screen.findByText('DWI fast GPU tensor processing, QC, and report workflow execution successfully archived with full provenance and metadata tagging.'),
    ).toBeInTheDocument();
    expect(screen.getByText('Stable workflow ID: dwi_fast_gpu_dti')).toBeInTheDocument();
  });

  it('downloads the full task export bundle from the result header', async () => {
    vi.mocked(api.getResultSummary).mockResolvedValue({ ...mockDwiSummary, project_id: 13 });
    const click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => undefined);
    const appendChild = vi.spyOn(document.body, 'appendChild');
    const removeChild = vi.spyOn(document.body, 'removeChild');
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });

    render(
      <QueryClientProvider client={client}>
        <MemoryRouter initialEntries={['/projects/13/results/114']}>
          <Routes>
            <Route element={<ResultDetailPage />} path="/projects/:projectId/results/:taskId" />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>,
    );
    await userEvent.click(await screen.findByRole('button', { name: /Export bundle/ }));

    await waitFor(() => expect(api.createTaskExportBundleTicket).toHaveBeenCalledWith(114));
    expect(api.getTaskExportBundle).not.toHaveBeenCalled();
    expect(appendChild).toHaveBeenCalledWith(expect.any(HTMLAnchorElement));
    expect(click).toHaveBeenCalled();
    expect(removeChild).toHaveBeenCalledWith(expect.any(HTMLAnchorElement));
  });

  it('shows visible export progress while the bundle is being prepared', async () => {
    vi.mocked(api.getResultSummary).mockResolvedValue({ ...mockDwiSummary, project_id: 13 });
    let resolveBundle: (blob: Blob) => void = () => undefined;
    vi.mocked(api.createTaskExportBundleTicket).mockReturnValue(
      new Promise((resolve) => {
        resolveBundle = () => resolve({ download_url: '/tasks/114/export-bundle-download?ticket=abc', expires_at: 1780000000, task_id: 114 });
      }),
    );
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });

    render(
      <QueryClientProvider client={client}>
        <MemoryRouter initialEntries={['/projects/13/results/114']}>
          <Routes>
            <Route element={<ResultDetailPage />} path="/projects/:projectId/results/:taskId" />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>,
    );
    await userEvent.click(await screen.findByRole('button', { name: /Export bundle/ }));

    expect(await screen.findByText('Preparing export bundle...')).toBeInTheDocument();

    resolveBundle(new Blob(['zip'], { type: 'application/zip' }));
    await waitFor(() => expect(screen.queryByText('Preparing export bundle...')).not.toBeInTheDocument());
  });

  it('shows a visible export error when the bundle download fails', async () => {
    vi.mocked(api.getResultSummary).mockResolvedValue({ ...mockDwiSummary, project_id: 13 });
    vi.mocked(api.createTaskExportBundleTicket).mockRejectedValue(new Error('Session expired. Please log in again.'));
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });

    render(
      <QueryClientProvider client={client}>
        <MemoryRouter initialEntries={['/projects/13/results/114']}>
          <Routes>
            <Route element={<ResultDetailPage />} path="/projects/:projectId/results/:taskId" />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>,
    );
    await userEvent.click(await screen.findByRole('button', { name: /Export bundle/ }));

    expect(await screen.findByRole('alert')).toHaveTextContent('Export failed: Session expired. Please log in again.');
  });

  it('uses result-summary workflow metadata when workflow catalog has not loaded', async () => {
    vi.mocked(api.getResultSummary).mockResolvedValue({
      ...mockDwiSummary,
      project_id: 13,
      workflow_metadata: {
        display_name: 'DWI fast GPU DTI maps, atlas metrics, QC, and report',
        is_report_only: false,
        runtime_workflow_type: 'dwi_fast_gpu_dti',
        workflow_type: 'dwi_fast_gpu_dti',
      },
    });
    vi.mocked(api.listWorkflows).mockResolvedValue({ workflows: [] });
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });

    render(
      <QueryClientProvider client={client}>
        <MemoryRouter initialEntries={['/projects/13/results/114']}>
          <Routes>
            <Route element={<ResultDetailPage />} path="/projects/:projectId/results/:taskId" />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>,
    );

    expect(
      await screen.findByText('DWI fast GPU DTI maps, atlas metrics, QC, and report workflow execution successfully archived with full provenance and metadata tagging.'),
    ).toBeInTheDocument();
    expect(screen.getByText('Stable workflow ID: dwi_fast_gpu_dti')).toBeInTheDocument();
  });

  it('uses artifact-manifest workflow metadata when summary metadata and catalog are unavailable', async () => {
    vi.mocked(api.getResultSummary).mockResolvedValue({ ...mockDwiSummary, project_id: 13, workflow_metadata: undefined });
    vi.mocked(api.getArtifactManifest).mockResolvedValue({
      artifacts: [],
      contract_version: 'artifact_manifest_v1',
      runtime_workflow_type: 'dwi_fast_gpu_dti',
      task_id: 114,
      workflow_metadata: {
        display_name: 'DWI fast GPU DTI maps, atlas metrics, QC, and report',
        is_report_only: false,
        runtime_workflow_type: 'dwi_fast_gpu_dti',
        workflow_type: 'dwi_fast_gpu_dti',
      },
      workflow_type: 'dwi_fast_gpu_dti',
    });
    vi.mocked(api.listWorkflows).mockResolvedValue({ workflows: [] });
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });

    render(
      <QueryClientProvider client={client}>
        <MemoryRouter initialEntries={['/projects/13/results/114']}>
          <Routes>
            <Route element={<ResultDetailPage />} path="/projects/:projectId/results/:taskId" />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>,
    );

    expect(
      await screen.findByText('DWI fast GPU DTI maps, atlas metrics, QC, and report workflow execution successfully archived with full provenance and metadata tagging.'),
    ).toBeInTheDocument();
    expect(screen.getByText('Stable workflow ID: dwi_fast_gpu_dti')).toBeInTheDocument();
  });

  it('prefers artifact manifest files for native QC previews and artifact tables', async () => {
    vi.mocked(api.getResultSummary).mockResolvedValue({ ...mockDwiSummary, project_id: 13 });
    vi.mocked(api.getArtifactManifest).mockResolvedValue({
      artifacts: [
        {
          content_type: 'image/png',
          download_url: '/tasks/114/artifacts/qc/native-dwi-qc.png',
          feature_group: 'scientific_report',
          native_artifact: true,
          preview_kind: 'image',
          relative_path: 'qc/native-dwi-qc.png',
          size_bytes: 4096,
        },
        {
          content_type: 'application/gzip',
          download_url: '/tasks/114/artifacts/maps/fa_native.nii.gz',
          feature_group: 'native_dti_maps',
          native_artifact: true,
          relative_path: 'maps/fa_native.nii.gz',
          size_bytes: 8192,
          space: 'DWI',
        },
      ],
      contract_version: 'artifact_manifest_v1',
      task_id: 114,
    });
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });

    render(
      <QueryClientProvider client={client}>
        <MemoryRouter initialEntries={['/projects/13/results/114']}>
          <Routes>
            <Route element={<ResultDetailPage />} path="/projects/:projectId/results/:taskId" />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>,
    );

    expect(await screen.findByRole('img', { name: 'Scientific figure qc/native-dwi-qc.png' })).toHaveAttribute('src', 'blob:http://localhost/authenticated-artifact');
    expect(api.getArtifactUrl).toHaveBeenCalledWith(114, 'qc/native-dwi-qc.png');
    expect(await screen.findByText('maps/fa_native.nii.gz')).toBeInTheDocument();
    expect(api.getArtifactManifest).toHaveBeenCalledWith(114);
    expect(screen.queryByText('reports/dwi_tensor_metrics.png')).not.toBeInTheDocument();
  });

  it('shows derived report artifact origin when native QC is missing', async () => {
    vi.mocked(api.getResultSummary).mockResolvedValue({ ...mockDwiSummary, project_id: 13 });
    vi.mocked(api.getArtifactManifest).mockResolvedValue({
      artifacts: [
        {
          artifact_category: 'derived_scientific_report',
          artifact_origin: 'generated_from_result_summary',
          artifact_role: 'derived_presentation_asset',
          content_type: 'image/png',
          derived_scientific_report: true,
          download_url: '/tasks/114/artifacts/reports/dwi_tensor_metrics.png',
          feature_group: 'scientific_report',
          native_artifact: false,
          preview_kind: 'image',
          relative_path: 'reports/dwi_tensor_metrics.png',
          size_bytes: 4096,
        },
      ],
      contract_version: 'artifact_manifest_v1',
      task_id: 114,
    });
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });

    render(
      <QueryClientProvider client={client}>
        <MemoryRouter initialEntries={['/projects/13/results/114']}>
          <Routes>
            <Route element={<ResultDetailPage />} path="/projects/:projectId/results/:taskId" />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>,
    );

    expect((await screen.findAllByText('reports/dwi_tensor_metrics.png')).length).toBeGreaterThanOrEqual(1);
    expect(await screen.findByText('No container-native QC artifacts registered')).toBeInTheDocument();
    expect(
      await screen.findByText('Derived report files are available, but they do not replace native container QC evidence.'),
    ).toBeInTheDocument();
    expect(await screen.findByText('generated_from_result_summary')).toBeInTheDocument();
    expect(await screen.findByAltText('Scientific figure reports/dwi_tensor_metrics.png')).toHaveAttribute('src', 'blob:http://localhost/authenticated-artifact');
    expect(api.getArtifactUrl).toHaveBeenCalledWith(114, 'reports/dwi_tensor_metrics.png');
  });

  it('blocks result rendering when the task summary belongs to another project', async () => {
    vi.mocked(api.getResultSummary).mockResolvedValue({ ...mockDwiSummary, project_id: 99 });
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });

    render(
      <QueryClientProvider client={client}>
        <MemoryRouter initialEntries={['/projects/13/results/114']}>
          <Routes>
            <Route element={<ResultDetailPage />} path="/projects/:projectId/results/:taskId" />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>,
    );

    expect(await screen.findByText('Result project mismatch')).toBeInTheDocument();
    expect(screen.getByText('This result summary belongs to project 99, not project 13.')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Back to results' })).toHaveAttribute('href', '/projects/13/results');
    expect(screen.queryByRole('heading', { name: 'Scientific Results Studio' })).not.toBeInTheDocument();
  });
});
