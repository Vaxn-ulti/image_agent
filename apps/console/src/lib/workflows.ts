import type { Series, Task } from './types';
import type { WorkflowCatalogItem } from './types';

export type WorkflowGroup = 'T1' | 'BOLD' | 'DWI' | 'DICOM' | 'Other';

export type WorkflowEligibility = {
  runnable: boolean;
  reason?: string;
};

export type WorkflowCatalog = {
  items: Record<string, WorkflowCatalogItem>;
  workflows: string[];
};

function workflowName(item: string | WorkflowCatalogItem): string | null {
  if (typeof item === 'string') return item;
  if (!item || typeof item !== 'object') return null;
  if (item.lane && item.lane !== 'fixed_workflow' && !item.api_runnable) return null;
  if (!item.api_runnable && (!item.requires_confirmation || !item.runtime_workflow_type)) return null;
  return item.type || item.workflow_type || item.runtime_workflow_type || null;
}

export function normalizeWorkflowCatalog(payload: Array<string | WorkflowCatalogItem> | { workflows: Array<string | WorkflowCatalogItem> } | undefined): WorkflowCatalog {
  if (!payload) return { items: {}, workflows: [] };
  const entries = Array.isArray(payload) ? payload : payload.workflows || [];
  return entries.reduce<WorkflowCatalog>(
    (catalog, item) => {
      const name = workflowName(item);
      if (!name) return catalog;
      catalog.workflows.push(name);
      if (typeof item === 'string') {
        catalog.items[name] = { type: name };
      } else {
        catalog.items[name] = { ...item, type: item.type || item.workflow_type || name };
      }
      return catalog;
    },
    { items: {}, workflows: [] },
  );
}

export function normalizeWorkflowList(payload: Array<string | WorkflowCatalogItem> | { workflows: Array<string | WorkflowCatalogItem> } | undefined): string[] {
  return normalizeWorkflowCatalog(payload).workflows;
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

function isQsiprepCompatibleTask(task: Task) {
  return task.workflow_type.startsWith('dwi_qsiprep') || task.workflow_type === 'dwi_qsi_full';
}

export function selectQsiprepTaskId(tasks: Task[], seriesId?: number | null): number | null {
  const candidates = tasks
    .filter((task) => task.status === 'completed' && isQsiprepCompatibleTask(task))
    .sort((a, b) => (b.created_at || '').localeCompare(a.created_at || '') || b.id - a.id);
  const sameSeries = candidates.find((task) => seriesId == null || task.series_id === seriesId);
  return (sameSeries || candidates[0])?.id ?? null;
}

function backendWorkflowEligibility(series: Series, workflowType: string): WorkflowEligibility | null {
  const eligibility = series.workflow_eligibility;
  if (!eligibility || eligibility.policy_version !== 'workflow_eligibility_v1') return null;

  const runnable = eligibility.runnable_workflows?.find((item) => item.workflow_type === workflowType);
  if (runnable) return { runnable: true };

  const blocked = eligibility.blocked_workflows?.find((item) => item.workflow_type === workflowType);
  if (!blocked) return null;

  return {
    reason: blocked.blocking_reasons?.filter(Boolean).join(' ') || blocked.reason || 'Backend workflow eligibility blocked this workflow.',
    runnable: false,
  };
}

export function getWorkflowEligibility(series: Series, workflowType: string, tasks: Task[]): WorkflowEligibility {
  const backendEligibility = backendWorkflowEligibility(series, workflowType);
  if (backendEligibility) return backendEligibility;

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
    if (!selectQsiprepTaskId(tasks, series.id)) {
      return { reason: 'QSIRecon requires a completed QSIPrep-compatible task.', runnable: false };
    }
  }

  return { runnable: true };
}
