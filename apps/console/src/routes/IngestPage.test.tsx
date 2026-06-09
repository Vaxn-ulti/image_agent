import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';
import { api } from '../lib/api';
import { mockSeries } from '../mocks/data';
import { IngestPage } from './IngestPage';

vi.mock('../lib/api', () => ({
  api: {
    createUploadSession: vi.fn(),
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
});
