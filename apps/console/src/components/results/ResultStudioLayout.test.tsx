import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { mockBoldSummary, mockDwiSummary, mockT1Summary } from '../../mocks/data';
import { ResultStudioLayout } from './ResultStudioLayout';

describe('ResultStudioLayout', () => {
  it('renders research result header, reports, artifacts, and provenance', () => {
    render(<ResultStudioLayout apiBase="http://localhost:8000" summary={mockDwiSummary} />);

    expect(screen.getByRole('heading', { name: 'Scientific Results Studio' })).toBeInTheDocument();
    expect(screen.getByText('RUN-114')).toBeInTheDocument();
    expect(screen.getAllByText('DWI').length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText('Scientific report figures')).toBeInTheDocument();
    expect(screen.getByText('dwi_tensor_metrics.png')).toBeInTheDocument();
    expect(screen.getByRole('img', { name: 'Derived DWI report figure: dwi_tensor_metrics.png' })).toBeInTheDocument();
    expect(screen.getByRole('img', { name: 'Derived DWI report figure: dwi_atlas_region_means.png' })).toBeInTheDocument();
    expect(screen.getByText('Artifact Manifest')).toBeInTheDocument();
    expect(screen.getByText('Evidence chain')).toBeInTheDocument();
    expect(screen.getAllByText(/runtime_sec/).length).toBeGreaterThanOrEqual(1);
  });

  it('renders T1 scientific chart requirements', () => {
    render(<ResultStudioLayout apiBase="http://localhost:8000" summary={mockT1Summary} />);

    expect(screen.getByText('T1 brain measures')).toBeInTheDocument();
    expect(screen.getByText('Regional morphometry')).toBeInTheDocument();
    expect(screen.getByText('FreeSurfer inventory')).toBeInTheDocument();
  });

  it('renders BOLD scientific chart requirements', () => {
    render(<ResultStudioLayout apiBase="http://localhost:8000" summary={mockBoldSummary} />);

    expect(screen.getByText('BOLD voxelwise metrics')).toBeInTheDocument();
    expect(screen.getByText('Seed connectivity')).toBeInTheDocument();
    expect(screen.getByText('QC time-series')).toBeInTheDocument();
    expect(screen.getByText('Mean PSD')).toBeInTheDocument();
    expect(screen.getByRole('img', { name: 'Derived BOLD report figure: bold_voxelwise_metrics.png' })).toBeInTheDocument();
    expect(screen.getByRole('img', { name: 'Derived BOLD report figure: bold_seed_connectivity_heatmap.png' })).toBeInTheDocument();
    expect(screen.getByRole('img', { name: 'Derived BOLD report figure: bold_qc_timeseries.png' })).toBeInTheDocument();
    expect(screen.getByRole('img', { name: 'Derived BOLD report figure: bold_mean_psd.png' })).toBeInTheDocument();
    expect(screen.queryByLabelText('Mean PSD trend placeholder')).not.toBeInTheDocument();
  });
});
