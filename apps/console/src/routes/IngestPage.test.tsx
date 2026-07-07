import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { api } from '../lib/api';
import { mockSeries } from '../mocks/data';
import { IngestPage } from './IngestPage';

vi.mock('../lib/api', () => ({
  api: {
    createUploadSession: vi.fn(),
    getInventory: vi.fn(),
    ingestDataset: vi.fn(),
    listSeries: vi.fn().mockResolvedValue([]),
    uploadDicom: vi.fn(),
    uploadDwi: vi.fn(),
    uploadNifti: vi.fn(),
  },
}));

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={['/projects/13/ingest']}>
        <Routes>
          <Route element={<IngestPage />} path="/projects/:projectId/ingest" />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('IngestPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('shows detected sequence labels for uploaded series', async () => {
    vi.mocked(api.listSeries).mockResolvedValue(mockSeries);
    renderPage();

    expect(await screen.findByText('DWI_multi_shell')).toBeInTheDocument();
  });

  it('requires all DWI sidecar files before upload', async () => {
    vi.mocked(api.listSeries).mockResolvedValue([]);
    renderPage();

    await userEvent.click(screen.getByRole('button', { name: 'Upload DWI set' }));

    expect(await screen.findByText(/DWI NIfTI, bval, bvec, and JSON sidecar are required/)).toBeInTheDocument();
    expect(api.uploadDwi).not.toHaveBeenCalled();
  });

  it('blocks upload controls when project scoped series cannot load', async () => {
    vi.mocked(api.listSeries).mockRejectedValue(new Error('Project not found'));
    renderPage();

    expect(await screen.findByText('Project data unavailable')).toBeInTheDocument();
    expect(screen.getByText('Project not found')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Switch project' })).toHaveAttribute('href', '/projects');
    expect(screen.queryByText('Standard Uploads')).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Upload DWI set' })).not.toBeInTheDocument();
  });

  it('refreshes detected series when async mixed ingest completes', async () => {
    vi.mocked(api.listSeries)
      .mockResolvedValueOnce([])
      .mockResolvedValue(mockSeries);
    vi.mocked(api.createUploadSession).mockResolvedValue({ id: 22, project_id: 13, status: 'created' });
    vi.mocked(api.ingestDataset).mockResolvedValue({});
    vi.mocked(api.getInventory).mockResolvedValue({
      inventory: {
        inventory_status: 'completed',
        series: [{ series_id: 5, modality: 'DWI', sequence_label: 'DWI_multi_shell' }],
      },
    });
    renderPage();

    const archive = new File(['zip-bytes'], 'dataset.zip', { type: 'application/zip' });
    await userEvent.upload(await screen.findByLabelText(/Mixed dataset zip/i), archive);

    await waitFor(() => expect(api.getInventory).toHaveBeenCalledWith(13, 22));
    await waitFor(() => expect(api.listSeries).toHaveBeenCalledTimes(3));
    expect(await screen.findByText('DWI_multi_shell')).toBeInTheDocument();
  });

  it('uploads DICOM zip through the DICOM upload contract and refreshes detected series', async () => {
    vi.mocked(api.listSeries)
      .mockResolvedValueOnce([])
      .mockResolvedValue(mockSeries);
    vi.mocked(api.uploadDicom).mockResolvedValue({
      file: { id: 17, original_name: 'dicom-series.zip' },
      series: mockSeries[0],
    });
    renderPage();

    const dicomSlot = (await screen.findByText('DICOM zip')).closest('label');
    expect(dicomSlot).not.toBeNull();
    const dicomInput = dicomSlot!.querySelector('input[type="file"]') as HTMLInputElement;
    const dicomArchive = new File(['dicom-bytes'], 'dicom-series.zip', { type: 'application/zip' });
    await userEvent.upload(dicomInput, dicomArchive);

    await waitFor(() => expect(api.uploadDicom).toHaveBeenCalledWith(13, dicomArchive));
    await waitFor(() => expect(api.listSeries).toHaveBeenCalledTimes(2));
    expect(api.uploadNifti).not.toHaveBeenCalled();
    expect(api.uploadDwi).not.toHaveBeenCalled();
    expect(api.createUploadSession).not.toHaveBeenCalled();
    expect(await screen.findByText('T1w')).toBeInTheDocument();
  });

  it('shows the completed inventory after a standard NIfTI upload returns a session id', async () => {
    vi.mocked(api.listSeries)
      .mockResolvedValueOnce([])
      .mockResolvedValue(mockSeries);
    vi.mocked(api.uploadNifti).mockResolvedValue({
      file: { id: 31, original_name: 'sub-01_T1w.nii.gz' },
      inventory: { inventory_status: 'completed', total_files: 1 },
      series: mockSeries[0],
      status: 'completed',
      upload_session_id: 44,
    });
    vi.mocked(api.getInventory).mockResolvedValue({
      inventory: {
        dicom: { conversion_status: 'not_applicable', found_files: 0 },
        inventory_status: 'completed',
        post_conversion_counts: { by_modality: { T1: 1 } },
        total_files: 1,
      },
    });
    renderPage();

    const niftiInput = await screen.findByLabelText('NIfTI upload');
    const nifti = new File(['nifti-bytes'], 'sub-01_T1w.nii.gz', { type: 'application/gzip' });
    await userEvent.upload(niftiInput, nifti);

    await waitFor(() => expect(api.uploadNifti).toHaveBeenCalledWith(13, nifti));
    await waitFor(() => expect(api.getInventory).toHaveBeenCalledWith(13, 44));
    expect(await screen.findByText('Completed')).toBeInTheDocument();
    expect(await screen.findByText('T1:')).toBeInTheDocument();
    expect(await screen.findByText('T1w')).toBeInTheDocument();
  });
});
