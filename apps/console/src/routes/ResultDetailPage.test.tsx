import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';
import { api } from '../lib/api';
import { mockDwiSummary } from '../mocks/data';
import { ResultDetailPage } from './ResultDetailPage';

vi.mock('../lib/api', () => ({
  api: {
    getResultSummary: vi.fn(),
  },
  getApiBase: () => 'http://localhost:8000',
}));

describe('ResultDetailPage', () => {
  it('renders result-summary feature groups and artifacts', async () => {
    vi.mocked(api.getResultSummary).mockResolvedValue(mockDwiSummary);
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
    expect(await screen.findByAltText(/Scientific figure reports\/dwi_tensor_metrics.png/)).toHaveAttribute(
      'src',
      'http://localhost:8000/tasks/114/artifacts/reports/dwi_tensor_metrics.png',
    );
    expect(await screen.findByRole('heading', { name: 'Scientific Results Studio' })).toBeInTheDocument();
    expect(await screen.findByText('DWI tensor map matrix')).toBeInTheDocument();
    expect(await screen.findByText('Atlas regional distribution')).toBeInTheDocument();
    expect(await screen.findByText('Evidence chain')).toBeInTheDocument();
  });
});
