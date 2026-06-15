import { describe, expect, it } from 'vitest';
import { mockSeries, mockTasks } from '../mocks/data';
import { getWorkflowEligibility, groupWorkflows, normalizeWorkflowList } from './workflows';

describe('workflow helpers', () => {
  it('groups backend workflow names by modality', () => {
    const grouped = groupWorkflows(['t1_deepprep', 'bold_second_level', 'dwi_fast_gpu_dti', 'dicom_convert']);

    expect(grouped.T1).toContain('t1_deepprep');
    expect(grouped.BOLD).toContain('bold_second_level');
    expect(grouped.DWI).toContain('dwi_fast_gpu_dti');
    expect(grouped.DICOM).toContain('dicom_convert');
  });

  it('normalizes backend workflow registry objects to API-runnable workflow types', () => {
    const workflows = normalizeWorkflowList({
      workflows: [
        { type: 't1_deepprep_anat_report', requires_confirmation: true, runtime_workflow_type: 't1_deepprep' },
        { type: 'toolchain_proposal', requires_confirmation: false, runtime_workflow_type: null },
        { type: 't1_deepprep_mock', api_runnable: true, requires_confirmation: true, runtime_workflow_type: 't1_deepprep_mock' },
      ],
    });

    expect(workflows).toEqual(['t1_deepprep_anat_report', 't1_deepprep_mock']);
  });

  it('requires JSON eddy metadata for DWI fast GPU DTI', () => {
    const dwi = { ...mockSeries[2], metadata: { has_bval: true, has_bvec: true, has_json: false } };
    const result = getWorkflowEligibility(dwi, 'dwi_fast_gpu_dti', mockTasks);

    expect(result.runnable).toBe(false);
    expect(result.reason).toContain('JSON sidecar');
  });

  it('allows BOLD downstream workflow after completed preprocessing', () => {
    const bold = mockSeries[1];
    const tasks = [{ ...mockTasks[0], series_id: bold.id, status: 'completed' as const, workflow_type: 'bold_deepprep' }];
    const result = getWorkflowEligibility(bold, 'bold_second_level', tasks);

    expect(result.runnable).toBe(true);
  });
});
