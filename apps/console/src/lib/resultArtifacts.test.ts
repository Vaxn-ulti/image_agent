import { describe, expect, it } from 'vitest';
import { artifactUrl, flattenOutputs, getReportArtifacts, groupArtifactsByFeature, isPreviewableFigure } from './resultArtifacts';
import { mockDwiSummary } from '../mocks/data';

describe('result artifact helpers', () => {
  it('flattens outputs while excluding report artifacts', () => {
    const artifacts = flattenOutputs(mockDwiSummary.outputs, new Set(['reports']));

    expect(artifacts.map((artifact) => artifact.relative_path)).toEqual([
      'maps/fa.nii.gz',
      'maps/fa_mni152.nii.gz',
      'tables/combined_region_dti.tsv',
    ]);
  });

  it('extracts previewable report figures', () => {
    const reports = getReportArtifacts(mockDwiSummary.outputs);

    expect(reports.filter(isPreviewableFigure).map((artifact) => artifact.relative_path)).toEqual([
      'reports/dwi_tensor_metrics.png',
      'reports/dwi_atlas_region_means.png',
    ]);
    expect(reports.filter(isPreviewableFigure).every((artifact) => artifact.artifact_role === 'derived_presentation_asset')).toBe(true);
  });

  it('includes native output figures with report artifacts for preview galleries', () => {
    const artifacts = getReportArtifacts({
      reports: [
        {
          content_type: 'text/html',
          relative_path: 'reports/index.html',
        },
      ],
      figures: [
        {
          content_type: 'image/png',
          native_artifact: true,
          relative_path: 'figures/native_deepprep_qc.png',
        },
      ],
    });

    expect(artifacts.filter(isPreviewableFigure).map((artifact) => artifact.relative_path)).toEqual([
      'figures/native_deepprep_qc.png',
    ]);
  });

  it('groups artifacts by feature group', () => {
    const groups = groupArtifactsByFeature(flattenOutputs(mockDwiSummary.outputs));

    expect(groups.native_dti_maps).toHaveLength(1);
    expect(groups.mni152_dti_maps).toHaveLength(1);
    expect(groups.regional_dti).toHaveLength(1);
    expect(groups.scientific_report).toHaveLength(4);
  });

  it('builds backend artifact URLs without hiding relative paths', () => {
    const artifact = flattenOutputs(mockDwiSummary.outputs).find((item) => item.relative_path === 'maps/fa.nii.gz');

    expect(artifact).toBeDefined();
    expect(artifactUrl(114, artifact!, 'http://localhost:8000')).toBe('http://localhost:8000/tasks/114/artifacts/maps/fa.nii.gz');
  });
});
