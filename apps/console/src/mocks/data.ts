import type { Inventory, Project, ResultSummary, Series, Task } from '../lib/types';

const generatedReportMetadata = {
  source_stage: 'scientific_report',
  artifact_role: 'derived_presentation_asset',
  artifact_origin: 'generated_from_result_summary',
  native_artifact: false,
  provenance: {
    generated_from: 'result_summary',
    replaces_native_qc: false,
  },
} as const;

export const mockProject: Project = {
  created_at: '2026-05-28T10:00:00Z',
  description: 'T1, BOLD, and DWI project with completed backend evidence',
  id: 13,
  name: 'MCI mixed modality acceptance',
};

export const mockSeries: Series[] = [
  {
    confidence: 0.98,
    format: 'NIFTI',
    id: 22,
    metadata: { shape: [256, 256, 176] },
    modality: 'T1',
    project_id: 13,
    sequence_label: 'T1w',
  },
  {
    confidence: 0.96,
    format: 'NIFTI',
    id: 23,
    metadata: { shape: [91, 109, 91, 210] },
    modality: 'BOLD',
    project_id: 13,
    sequence_label: 'BOLD_rest',
  },
  {
    confidence: 0.95,
    format: 'NIFTI_BIDS',
    id: 24,
    metadata: { has_bval: true, has_bvec: true, has_dwi_eddy_metadata: true, has_json: true },
    modality: 'DWI',
    project_id: 13,
    sequence_label: 'DWI_multi_shell',
  },
];

export const mockTasks: Task[] = [
  { id: 41, progress: 100, project_id: 13, series_id: 22, status: 'completed', workflow_type: 't1_deepprep' },
  { id: 111, progress: 100, project_id: 13, series_id: 23, status: 'completed', workflow_type: 'bold_second_level' },
  { id: 114, progress: 100, project_id: 13, series_id: 24, status: 'completed', workflow_type: 'dwi_fast_gpu_dti' },
  { id: 120, progress: 45, project_id: 13, series_id: 23, status: 'running', workflow_type: 'bold_falff' },
];

export const mockInventory: Inventory = {
  bids_dataset_root: 'sub-01',
  dicom: { conversion_status: 'not_applicable', found_files: 0 },
  post_conversion_counts: {
    by_modality: { BOLD: 1, DWI: 1, T1: 1 },
    by_sequence: { BOLD_rest: 1, DWI_multi_shell: 1, T1w: 1 },
  },
  recognized_unsupported_sequences: [],
  total_files: 18,
};

export const mockDwiSummary: ResultSummary = {
  contract_version: '1.0',
  feature_groups: ['native_dti_maps', 'mni152_dti_maps', 'regional_dti', 'qc', 'scientific_report'],
  modality: 'DWI',
  outputs: {
    maps: [
      {
        content_type: 'application/gzip',
        download_url: '/tasks/114/artifacts/maps/fa.nii.gz',
        feature_group: 'native_dti_maps',
        relative_path: 'maps/fa.nii.gz',
        size_bytes: 1234,
        space: 'DWI',
      },
      {
        content_type: 'application/gzip',
        download_url: '/tasks/114/artifacts/maps/fa_mni152.nii.gz',
        feature_group: 'mni152_dti_maps',
        relative_path: 'maps/fa_mni152.nii.gz',
        size_bytes: 2345,
        space: 'MNI152',
      },
    ],
    reports: [
      {
        content_type: 'text/html',
        download_url: '/tasks/114/artifacts/reports/index.html',
        feature_group: 'scientific_report',
        relative_path: 'reports/index.html',
        size_bytes: 4567,
        ...generatedReportMetadata,
      },
      {
        content_type: 'application/json',
        download_url: '/tasks/114/artifacts/reports/report_manifest.json',
        feature_group: 'scientific_report',
        relative_path: 'reports/report_manifest.json',
        size_bytes: 789,
        ...generatedReportMetadata,
      },
      {
        content_type: 'image/png',
        download_url: '/tasks/114/artifacts/reports/dwi_tensor_metrics.png',
        feature_group: 'scientific_report',
        relative_path: 'reports/dwi_tensor_metrics.png',
        size_bytes: 3210,
        space: 'MNI152',
        ...generatedReportMetadata,
      },
      {
        content_type: 'image/png',
        download_url: '/tasks/114/artifacts/reports/dwi_atlas_region_means.png',
        feature_group: 'scientific_report',
        relative_path: 'reports/dwi_atlas_region_means.png',
        size_bytes: 2980,
        space: 'MNI152',
        ...generatedReportMetadata,
      },
    ],
    tables: [
      {
        content_type: 'text/tab-separated-values',
        download_url: '/tasks/114/artifacts/tables/combined_region_dti.tsv',
        feature_group: 'regional_dti',
        relative_path: 'tables/combined_region_dti.tsv',
        size_bytes: 3456,
        space: 'MNI152',
      },
    ],
  },
  provenance: {
    dti_subset_metadata: { selected_volumes: 28, source_volumes: 129 },
    max_runtime_sec: 2100,
    runtime_sec: 1021,
    scientific_report_report_count: 2,
    scientific_report_summary_path: '/outputs/task_114/summary/dwi_scientific_report_summary.json',
    validation_only: false,
  },
  spaces: ['DWI', 'MNI152'],
  task_id: 114,
  workflow_type: 'dwi_fast_gpu_dti',
};

export const mockT1Summary: ResultSummary = {
  contract_version: '1.0',
  feature_groups: ['brain_measures', 'regional_morphometry', 'freesurfer_stats', 'scientific_report'],
  modality: 'T1',
  outputs: {
    reports: [
      {
        content_type: 'image/png',
        download_url: '/tasks/41/artifacts/reports/t1_brain_measures_overview.png',
        feature_group: 'scientific_report',
        relative_path: 'reports/t1_brain_measures_overview.png',
        size_bytes: 2200,
        ...generatedReportMetadata,
      },
      {
        content_type: 'image/png',
        download_url: '/tasks/41/artifacts/reports/t1_region_thickness.png',
        feature_group: 'scientific_report',
        relative_path: 'reports/t1_region_thickness.png',
        size_bytes: 2400,
        ...generatedReportMetadata,
      },
    ],
    tables: [
      {
        content_type: 'text/tab-separated-values',
        download_url: '/tasks/41/artifacts/tables/t1_brain_measures.tsv',
        feature_group: 'brain_measures',
        relative_path: 'tables/t1_brain_measures.tsv',
        size_bytes: 1200,
      },
      {
        content_type: 'text/tab-separated-values',
        download_url: '/tasks/41/artifacts/tables/t1_t1w_regions.tsv',
        feature_group: 'regional_morphometry',
        relative_path: 'tables/t1_t1w_regions.tsv',
        size_bytes: 1800,
      },
      {
        content_type: 'text/tab-separated-values',
        download_url: '/tasks/41/artifacts/tables/freesurfer_stats_inventory.tsv',
        feature_group: 'freesurfer_stats',
        relative_path: 'tables/freesurfer_stats_inventory.tsv',
        size_bytes: 900,
      },
    ],
  },
  provenance: { scientific_report_report_count: 2, validation_only: false },
  spaces: ['T1w'],
  task_id: 41,
  workflow_type: 't1_deepprep',
};

export const mockBoldSummary: ResultSummary = {
  contract_version: '1.0',
  feature_groups: ['voxelwise_metrics', 'connectivity', 'qc_timeseries', 'motion_confounds', 'scientific_report'],
  modality: 'BOLD',
  outputs: {
    maps: [
      {
        content_type: 'application/gzip',
        download_url: '/tasks/111/artifacts/maps/alff.nii.gz',
        feature_group: 'voxelwise_metrics',
        relative_path: 'maps/alff.nii.gz',
        size_bytes: 1400,
        space: 'MNI152',
      },
      {
        content_type: 'application/gzip',
        download_url: '/tasks/111/artifacts/maps/falff.nii.gz',
        feature_group: 'voxelwise_metrics',
        relative_path: 'maps/falff.nii.gz',
        size_bytes: 1400,
        space: 'MNI152',
      },
    ],
    reports: [
      {
        content_type: 'image/png',
        download_url: '/tasks/111/artifacts/reports/bold_voxelwise_metrics.png',
        feature_group: 'scientific_report',
        relative_path: 'reports/bold_voxelwise_metrics.png',
        size_bytes: 3100,
        ...generatedReportMetadata,
      },
      {
        content_type: 'image/png',
        download_url: '/tasks/111/artifacts/reports/bold_qc_timeseries.png',
        feature_group: 'scientific_report',
        relative_path: 'reports/bold_qc_timeseries.png',
        size_bytes: 3000,
        ...generatedReportMetadata,
      },
      {
        content_type: 'image/png',
        download_url: '/tasks/111/artifacts/reports/bold_seed_connectivity_heatmap.png',
        feature_group: 'scientific_report',
        relative_path: 'reports/bold_seed_connectivity_heatmap.png',
        size_bytes: 3300,
        ...generatedReportMetadata,
      },
      {
        content_type: 'image/png',
        download_url: '/tasks/111/artifacts/reports/bold_mean_psd.png',
        feature_group: 'scientific_report',
        relative_path: 'reports/bold_mean_psd.png',
        size_bytes: 2600,
        ...generatedReportMetadata,
      },
    ],
    tables: [
      {
        content_type: 'text/tab-separated-values',
        download_url: '/tasks/111/artifacts/tables/seed_to_roi.tsv',
        feature_group: 'connectivity',
        relative_path: 'tables/seed_to_roi.tsv',
        size_bytes: 2100,
      },
      {
        content_type: 'text/tab-separated-values',
        download_url: '/tasks/111/artifacts/tables/dmn_summary.tsv',
        feature_group: 'connectivity',
        relative_path: 'tables/dmn_summary.tsv',
        size_bytes: 800,
      },
      {
        content_type: 'text/tab-separated-values',
        download_url: '/tasks/111/artifacts/tables/fd_dvars.tsv',
        feature_group: 'qc_timeseries',
        relative_path: 'tables/fd_dvars.tsv',
        size_bytes: 1800,
      },
    ],
  },
  provenance: { scientific_report_report_count: 4, validation_only: false },
  spaces: ['MNI152'],
  task_id: 111,
  workflow_type: 'bold_second_level',
};
