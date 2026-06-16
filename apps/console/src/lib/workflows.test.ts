import { describe, expect, it } from 'vitest';
import { mockSeries, mockTasks } from '../mocks/data';
import { getWorkflowEligibility, groupWorkflows, normalizeWorkflowList, selectQsiprepTaskId } from './workflows';

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
        { type: 't1_deepprep_anat_report', lane: 'fixed_workflow', requires_confirmation: true, runtime_workflow_type: 't1_deepprep' },
        { type: 'toolchain_proposal', requires_confirmation: false, runtime_workflow_type: null },
        { type: 'dwi_qsiprep', lane: 'toolchain_incubation', requires_confirmation: true, runtime_workflow_type: 'dwi_qsiprep' },
        { type: 't1_deepprep_mock', api_runnable: true, lane: 'toolchain_incubation', requires_confirmation: true, runtime_workflow_type: 't1_deepprep_mock' },
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

  it('uses backend workflow_eligibility before frontend fallback guesses', () => {
    const t1BlockedByBackend = {
      ...mockSeries[0],
      workflow_eligibility: {
        blocked_workflows: [
          {
            blocking_reasons: ['Remote DeepPrep runtime is not configured.'],
            workflow_type: 't1_deepprep_anat_report',
          },
        ],
        policy_version: 'workflow_eligibility_v1',
        primary_recommendation: null,
        production_task_created: false,
        runnable_workflows: [],
      },
    };

    const result = getWorkflowEligibility(t1BlockedByBackend, 't1_deepprep_anat_report', []);

    expect(result.runnable).toBe(false);
    expect(result.reason).toBe('Remote DeepPrep runtime is not configured.');
  });

  it.each([
    ['t1_deepprep_anat_report', mockSeries[0], 'Backend blocked T1 runtime.'],
    ['bold_fmriprep_xcpd_report', mockSeries[1], 'Backend blocked BOLD runtime.'],
    ['dwi_fast_gpu_dti', mockSeries[2], 'Backend blocked DWI runtime.'],
    ['dicom_convert', mockSeries[3], 'Backend blocked DICOM conversion.'],
  ])('uses backend blocked_workflows reason for %s', (workflowType, series, reason) => {
    const blockedByBackend = {
      ...series,
      workflow_eligibility: {
        blocked_workflows: [
          {
            blocking_reasons: [reason],
            workflow_type: workflowType,
          },
        ],
        policy_version: 'workflow_eligibility_v1',
        primary_recommendation: null,
        production_task_created: false,
        runnable_workflows: [],
      },
    };

    const result = getWorkflowEligibility(blockedByBackend, workflowType, []);

    expect(result).toEqual({ reason, runnable: false });
  });

  it('allows BOLD downstream workflow after completed preprocessing', () => {
    const bold = mockSeries[1];
    const tasks = [{ ...mockTasks[0], series_id: bold.id, status: 'completed' as const, workflow_type: 'bold_deepprep' }];
    const result = getWorkflowEligibility(bold, 'bold_second_level', tasks);

    expect(result.runnable).toBe(true);
  });

  it('selects a completed QSIPrep-compatible task for QSIRecon launch', () => {
    const tasks = [
      { ...mockTasks[0], id: 85, series_id: 999, status: 'completed' as const, workflow_type: 'dwi_qsiprep' },
      { ...mockTasks[1], id: 86, series_id: mockSeries[2].id, status: 'running' as const, workflow_type: 'dwi_qsiprep' },
      { ...mockTasks[2], id: 87, series_id: mockSeries[2].id, status: 'completed' as const, workflow_type: 'dwi_qsiprep_gpu' },
    ];

    expect(selectQsiprepTaskId(tasks, mockSeries[2].id)).toBe(87);
  });
});
