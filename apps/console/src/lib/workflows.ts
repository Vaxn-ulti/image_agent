import type { Series, Task } from './types';

export type WorkflowGroup = 'T1' | 'BOLD' | 'DWI' | 'DICOM' | 'Other';

export type WorkflowEligibility = {
  runnable: boolean;
  reason?: string;
};

export function normalizeWorkflowList(payload: string[] | { workflows: string[] } | undefined): string[] {
  if (!payload) return [];
  return Array.isArray(payload) ? payload : payload.workflows || [];
}

export function workflowGroup(workflowType: string): WorkflowGroup {
  if (workflowType.startsWith('t1_')) return 'T1';
  if (workflowType.startsWith('bold_')) return 'BOLD';
  if (workflowType.startsWith('dwi_')) return 'DWI';
  if (workflowType.startsWith('dicom_')) return 'DICOM';
  return 'Other';
}

export function groupWorkflows(workflows: string[]) {
  return workflows.reduce<Record<WorkflowGroup, string[]>>(
    (groups, workflow) => {
      groups[workflowGroup(workflow)].push(workflow);
      return groups;
    },
    { BOLD: [], DICOM: [], DWI: [], Other: [], T1: [] },
  );
}

function hasCompletedTask(tasks: Task[], workflowTypes: string[], seriesId?: number | null) {
  return tasks.some(
    (task) =>
      task.status === 'completed' &&
      workflowTypes.includes(task.workflow_type) &&
      (seriesId == null || task.series_id === seriesId || task.series_id == null),
  );
}

export function getWorkflowEligibility(series: Series, workflowType: string, tasks: Task[]): WorkflowEligibility {
  if (workflowType.startsWith('t1_') && series.modality !== 'T1') {
    return { reason: 'Requires a T1 series.', runnable: false };
  }

  if (workflowType.startsWith('bold_') && series.modality !== 'BOLD') {
    return { reason: 'Requires a BOLD series.', runnable: false };
  }

  if (workflowType.startsWith('dwi_') && series.modality !== 'DWI') {
    return { reason: 'Requires a DWI series.', runnable: false };
  }

  if (workflowType.startsWith('dicom_') && series.modality !== 'DICOM') {
    return { reason: 'Requires a DICOM archive series.', runnable: false };
  }

  if (workflowType === 'dwi_fast_gpu_dti' || workflowType === 'dwi_fast_gpu_dti_validate') {
    const metadata = series.metadata || {};
    if (!metadata.has_bval || !metadata.has_bvec || !metadata.has_json || !metadata.has_dwi_eddy_metadata) {
      return { reason: 'DWI fast GPU DTI requires bval, bvec, and JSON sidecar eddy metadata.', runnable: false };
    }
  }

  if (workflowType.startsWith('bold_alff') || workflowType.startsWith('bold_falff') || workflowType.startsWith('bold_second_level')) {
    const validateOnly = workflowType.endsWith('_validate');
    const hasPreproc = hasCompletedTask(tasks, ['bold_deepprep', 't1_deepprep'], validateOnly ? undefined : series.id);
    if (!hasPreproc && !validateOnly) {
      return { reason: 'Requires a completed BOLD DeepPrep-compatible preprocessing task.', runnable: false };
    }
  }

  if (workflowType.startsWith('dwi_qsirecon')) {
    const hasQsiprep = hasCompletedTask(tasks, ['dwi_qsiprep', 'dwi_qsi_full'], undefined);
    if (!hasQsiprep) {
      return { reason: 'QSIRecon requires a completed QSIPrep-compatible task.', runnable: false };
    }
  }

  return { runnable: true };
}
