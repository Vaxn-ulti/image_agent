import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  Activity,
  Brain,
  CheckCircle2,
  ChevronRight,
  Info,
  Layers,
  Play,
  ShieldCheck,
  Zap
} from 'lucide-react';
import { useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { Button } from '../components/ui/Button';
import { PageHeader } from '../components/ui/PageHeader';
import { api } from '../lib/api';
import { queryKeys } from '../lib/query';
import type { AgentConfirmation, AgentRunResponse, Task, WorkflowCatalogItem } from '../lib/types';
import { getWorkflowEligibility, groupWorkflows, normalizeWorkflowCatalog, selectQsiprepTaskId } from '../lib/workflows';

type PendingWorkflowApproval = {
  confirmation: AgentConfirmation;
  threadId: string;
  workflowType: string;
};

function workflowMetadataFromConfirmation(confirmation: AgentConfirmation): Partial<WorkflowCatalogItem> {
  const value = confirmation.workflow_metadata;
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    return {};
  }
  return value as Partial<WorkflowCatalogItem>;
}

function workflowOutputLabels(metadata: Partial<WorkflowCatalogItem>) {
  return [
    ...(metadata.primary_outputs || []),
    ...(metadata.qc_outputs || []),
    ...(metadata.report_outputs || []),
  ].slice(0, 4);
}

function workflowRoleLabel(value?: string) {
  return value ? value.replace(/_/g, ' ') : '';
}

function workflowCapabilityBadges(metadata: Partial<WorkflowCatalogItem>) {
  return [
    metadata.workflow_family,
    workflowRoleLabel(metadata.workflow_role),
    metadata.is_report_only === true ? 'Report only' : 'Full processing',
  ].filter(Boolean);
}

export function WorkflowsPage() {
  const projectId = Number(useParams().projectId);
  const queryClient = useQueryClient();
  const [lastStartedTask, setLastStartedTask] = useState<Task | null>(null);
  const [pendingApproval, setPendingApproval] = useState<PendingWorkflowApproval | null>(null);
  const [launchError, setLaunchError] = useState('');
  const { data: workflowPayload } = useQuery({ queryFn: api.listWorkflows, queryKey: queryKeys.workflows });
  const seriesQuery = useQuery({ enabled: Boolean(projectId), queryFn: () => api.listSeries(projectId), queryKey: queryKeys.series(projectId), retry: false });
  const tasksQuery = useQuery({ enabled: Boolean(projectId), queryFn: () => api.listProjectTasks(projectId), queryKey: queryKeys.tasks(projectId), retry: false });
  const series = seriesQuery.data || [];
  const tasks = tasksQuery.data || [];

  function taskFromAgentResponse(data: AgentRunResponse) {
    if (data.status === 'task_created' && data.task?.id) {
      return data.task;
    }
    return null;
  }

  const prepareWorkflow = useMutation({
    mutationFn: ({ qsiprepTaskId, seriesId, workflowType }: { qsiprepTaskId?: number | null; seriesId: number; workflowType: string }) => {
      const dependencyNote = qsiprepTaskId == null ? '' : ` Use completed QSIPrep task ${qsiprepTaskId} as the QSIRecon prerequisite.`;
      return api.runAgent(
        projectId,
        `Prepare workflow ${workflowType} for series ${seriesId}. Return confirmation only and do not create a task yet.${dependencyNote}`,
      );
    },
    onSuccess: (data, variables) => {
      setLaunchError('');
      setLastStartedTask(null);
      const task = taskFromAgentResponse(data);
      if (task) {
        setPendingApproval(null);
        setLastStartedTask(task);
        queryClient.invalidateQueries({ queryKey: queryKeys.tasks(projectId) });
        queryClient.invalidateQueries({ queryKey: queryKeys.task(task.id) });
        return;
      }
      if (data.status === 'confirmation_required' && data.thread_id && data.confirmation) {
        setPendingApproval({
          confirmation: data.confirmation,
          threadId: data.thread_id,
          workflowType: String(data.confirmation.workflow_type || variables.workflowType),
        });
        return;
      }
      setLaunchError(data.answer || data.message || 'Agent did not return a workflow confirmation.');
    },
    onError: (error) => {
      setPendingApproval(null);
      setLastStartedTask(null);
      setLaunchError(error instanceof Error ? error.message : 'Workflow preparation failed.');
    },
  });

  const approveWorkflow = useMutation({
    mutationFn: ({ approved, confirmation, threadId }: { approved: boolean; confirmation: AgentConfirmation; threadId: string }) =>
      api.resumeAgent(threadId, approved, confirmation),
    onSuccess: (data) => {
      setLaunchError('');
      setPendingApproval(null);
      const task = taskFromAgentResponse(data);
      if (!task) {
        setLastStartedTask(null);
        setLaunchError(data.answer || data.message || 'Workflow approval did not create a task.');
        return;
      }
      setLastStartedTask(task);
      queryClient.invalidateQueries({ queryKey: queryKeys.tasks(projectId) });
      queryClient.invalidateQueries({ queryKey: queryKeys.task(task.id) });
    },
    onError: (error) => {
      setLastStartedTask(null);
      setLaunchError(error instanceof Error ? error.message : 'Workflow approval failed.');
    },
  });

  const workflowCatalog = normalizeWorkflowCatalog(workflowPayload);
  const grouped = groupWorkflows(workflowCatalog.workflows);
  const workflowDisplayName = (workflowType: string | null | undefined) => {
    if (!workflowType) return '';
    return workflowCatalog.items[workflowType]?.display_name || workflowType;
  };
  const projectDataError = seriesQuery.error || tasksQuery.error;
  const projectDataErrorMessage = projectDataError instanceof Error ? projectDataError.message : 'Project data could not be loaded.';

  const getIcon = (group: string) => {
    switch (group) {
      case 'T1': return <Brain className="w-4 h-4" />;
      case 'DWI': return <Layers className="w-4 h-4" />;
      case 'BOLD': return <Activity className="w-4 h-4" />;
      default: return <Zap className="w-4 h-4" />;
    }
  };

  if (seriesQuery.isError || tasksQuery.isError) {
    return (
      <div className="max-w-6xl mx-auto space-y-8">
        <PageHeader
          description="Run backend-supported workflows only when prerequisites are satisfied."
          eyebrow="Execution"
          title="Workflows"
        />

        <div className="rounded-lg border border-amber-200 bg-amber-50 p-6 text-sm text-amber-800">
          <div className="flex items-center gap-2 text-base font-semibold text-amber-900">
            <Info className="w-4 h-4 shrink-0" /> Project data unavailable
          </div>
          <p className="mt-2">{projectDataErrorMessage}</p>
          <Link
            className="mt-4 inline-flex items-center gap-2 rounded-md bg-white px-3 py-2 text-xs font-semibold text-amber-800 shadow-sm ring-1 ring-amber-200 hover:bg-amber-100"
            to="/projects"
          >
            Switch project
          </Link>
        </div>
      </div>
    );
  }

  return (
    <div className="max-w-6xl mx-auto space-y-8">
      <PageHeader
        description="Run backend-supported workflows only when prerequisites are satisfied."
        eyebrow="Execution"
        title="Workflows"
      />

      {launchError ? (
        <div className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-700">
          <div className="flex items-center gap-2 font-semibold text-red-800">
            <Info className="h-4 w-4 shrink-0" /> Workflow launch failed
          </div>
          <p className="mt-1 text-xs leading-5">{launchError}</p>
        </div>
      ) : null}

      {lastStartedTask ? (
        <div className="rounded-lg border border-emerald-200 bg-emerald-50 p-4 text-sm text-emerald-800">
          <div className="flex items-center gap-2 font-semibold text-emerald-900">
            <CheckCircle2 className="h-4 w-4 shrink-0" /> Task #{lastStartedTask.id} started
          </div>
          <p className="mt-1 text-xs leading-5 text-emerald-700">
            The backend created a deterministic {workflowDisplayName(lastStartedTask.workflow_type)} task. Track queue, runtime, logs, and completion from the task page.
          </p>
          <p className="mt-1 text-[11px] font-medium text-emerald-700/80">Stable workflow ID: {lastStartedTask.workflow_type}</p>
          <Link
            className="mt-3 inline-flex items-center gap-2 rounded-md bg-white px-3 py-2 text-xs font-semibold text-emerald-800 shadow-sm ring-1 ring-emerald-200 hover:bg-emerald-100"
            to={`/projects/${projectId}/tasks`}
          >
            View task progress <ChevronRight className="h-3.5 w-3.5" />
          </Link>
        </div>
      ) : null}

      {pendingApproval ? (() => {
        const metadata = workflowMetadataFromConfirmation(pendingApproval.confirmation);
        const displayName = metadata.display_name || pendingApproval.workflowType;
        const outputs = workflowOutputLabels(metadata);
        return (
          <div className="rounded-lg border border-amber-200 bg-amber-50 p-4 text-sm text-amber-900">
            <div className="flex items-center gap-2 font-semibold">
              <ShieldCheck className="h-4 w-4 shrink-0" /> Approval required
            </div>
            <p className="mt-1 text-sm font-semibold leading-5 text-amber-950">{displayName}</p>
            <p className="mt-1 text-xs leading-5 text-amber-700">
              The Agent prepared this fixed workflow. The backend task is not created until you approve this confirmation.
            </p>
            <p className="mt-1 text-[11px] font-medium text-amber-700">Stable workflow ID: {pendingApproval.workflowType}</p>
            {metadata.capability_summary ? (
              <p className="mt-2 max-w-3xl text-xs leading-5 text-amber-800">{metadata.capability_summary}</p>
            ) : null}
            {outputs.length > 0 ? (
              <div className="mt-2 flex flex-wrap gap-1.5">
                {outputs.map((output) => (
                  <span key={output} className="rounded-full border border-amber-200 bg-white px-2 py-0.5 text-[10px] font-medium text-amber-900">
                    {output}
                  </span>
                ))}
              </div>
            ) : null}
            <div className="mt-3 flex flex-wrap gap-2">
              <button
                type="button"
                disabled={approveWorkflow.isPending}
                onClick={() => approveWorkflow.mutate({
                  approved: true,
                  confirmation: pendingApproval.confirmation,
                  threadId: pendingApproval.threadId,
                })}
                className="rounded-md bg-[#065F46] px-3 py-2 text-xs font-semibold text-white hover:bg-[#044E3A] disabled:cursor-not-allowed disabled:opacity-50"
              >
                Approve workflow
              </button>
              <button
                type="button"
                disabled={approveWorkflow.isPending}
                onClick={() => {
                  setPendingApproval(null);
                  approveWorkflow.mutate({
                    approved: false,
                    confirmation: pendingApproval.confirmation,
                    threadId: pendingApproval.threadId,
                  });
                }}
                className="rounded-md border border-amber-200 bg-white px-3 py-2 text-xs font-semibold text-amber-800 hover:bg-amber-100 disabled:cursor-not-allowed disabled:opacity-50"
              >
                Cancel
              </button>
            </div>
          </div>
        );
      })() : null}

      <div className="space-y-12">
        {Object.entries(grouped).map(([group, workflows]) => workflows.length > 0 && (
          <div key={group} className="space-y-4">
            <div className="flex items-center gap-2 px-2">
              <div className="p-1.5 rounded-lg bg-[#ECFDF5] text-[#065F46]">
                {getIcon(group)}
              </div>
              <h2 className="text-lg font-bold text-gray-900">{group} Workflows</h2>
            </div>

            <div className="grid gap-6">
              {workflows.map((workflow) => {
                const catalogItem = workflowCatalog.items[workflow];
                const displayName = catalogItem?.display_name || workflow;
                const outputs = [
                  ...(catalogItem?.primary_outputs || []),
                  ...(catalogItem?.qc_outputs || []),
                  ...(catalogItem?.report_outputs || []),
                ].slice(0, 4);
                const capabilityBadges = workflowCapabilityBadges(catalogItem || {});
                const pipelineStages = (catalogItem?.pipeline_stages || []).slice(0, 3);
                const limitations = (catalogItem?.limitations || []).slice(0, 2);
                return (
                <div key={workflow} className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden transition-all hover:shadow-md">
                  <div className="px-5 py-4 border-b border-gray-100 bg-gray-50/50 flex items-center justify-between">
                    <div className="min-w-0">
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="text-sm font-bold text-gray-800">{displayName}</span>
                        <span className="rounded border border-gray-200 bg-white px-1.5 py-0.5 text-[10px] font-semibold text-gray-500">{workflow}</span>
                      </div>
                      {catalogItem?.capability_summary ? (
                        <p className="mt-1 max-w-3xl text-xs leading-5 text-gray-500">{catalogItem.capability_summary}</p>
                      ) : null}
                      {capabilityBadges.length > 0 ? (
                        <div className="mt-2 flex flex-wrap gap-1.5">
                          {capabilityBadges.map((badge) => (
                            <span key={badge} className="rounded border border-gray-200 bg-white px-2 py-0.5 text-[10px] font-semibold text-gray-500">
                              {badge}
                            </span>
                          ))}
                        </div>
                      ) : null}
                      {outputs.length > 0 ? (
                        <div className="mt-2 flex flex-wrap gap-1.5">
                          {outputs.map((output) => (
                            <span key={output} className="rounded-full border border-emerald-100 bg-emerald-50 px-2 py-0.5 text-[10px] font-medium text-emerald-800">
                              {output}
                            </span>
                          ))}
                        </div>
                      ) : null}
                      {pipelineStages.length > 0 ? (
                        <div className="mt-3 grid gap-1.5">
                          {pipelineStages.map((stage) => (
                            <div key={`${workflow}-${stage.name}`} className="text-[11px] leading-4 text-gray-500">
                              <span className="font-semibold text-gray-700">{stage.name}</span>
                              {stage.purpose ? <span className="ml-1">{stage.purpose}</span> : null}
                            </div>
                          ))}
                        </div>
                      ) : null}
                      {limitations.length > 0 ? (
                        <div className="mt-2 text-[11px] leading-4 text-amber-700">
                          {limitations.join(' ')}
                        </div>
                      ) : null}
                    </div>
                    <button className="text-gray-400 hover:text-gray-600 transition-colors">
                      <Info className="w-4 h-4" />
                    </button>
                  </div>

                  <div className="p-5">
                    <div className="text-[10px] font-bold text-gray-400 uppercase tracking-wider mb-3 px-1">Target Series</div>
                    <div className="grid gap-3">
                      {series
                        .filter((item) => group === 'Other' || item.modality === group)
                        .map((item) => {
                          const eligibility = getWorkflowEligibility(item, workflow, tasks);
                          return (
                            <div key={`${workflow}-${item.id}`} className="flex items-center justify-between gap-4 p-3 rounded-lg border border-gray-100 bg-white hover:border-[#065F46]/30 transition-all group">
                              <div className="flex items-center gap-3">
                                <div className={`w-8 h-8 rounded-lg flex items-center justify-center text-xs font-bold ${
                                  eligibility.runnable ? 'bg-green-50 text-green-700' : 'bg-gray-50 text-gray-400'
                                }`}>
                                  #{item.id}
                                </div>
                                <div>
                                  <div className="text-sm font-semibold text-gray-800 flex items-center gap-2">
                                    {item.sequence_label || item.modality}
                                    {eligibility.runnable && (
                                      <CheckCircle2 className="w-3.5 h-3.5 text-green-500" />
                                    )}
                                  </div>
                                  {!eligibility.runnable ? (
                                    <div className="text-[10px] text-amber-600 font-medium">{eligibility.reason}</div>
                                  ) : (
                                    <div className="text-[10px] text-gray-400 uppercase tracking-tight">Ready for execution</div>
                                  )}
                                </div>
                              </div>
                              <Button
                                size="sm"
                                disabled={!eligibility.runnable || prepareWorkflow.isPending || approveWorkflow.isPending}
                                onClick={() => prepareWorkflow.mutate({
                                  qsiprepTaskId: workflow.startsWith('dwi_qsirecon') ? selectQsiprepTaskId(tasks, item.id) : null,
                                  seriesId: item.id,
                                  workflowType: workflow,
                                })}
                                className={`${
                                  eligibility.runnable
                                    ? 'bg-[#065F46] hover:bg-[#044E3A] text-white'
                                    : 'bg-gray-100 text-gray-400 cursor-not-allowed'
                                } px-4 shadow-sm group-hover:scale-105 transition-transform`}
                              >
                                {prepareWorkflow.isPending ? (
                                  <Loader2 className="w-3.5 h-3.5 animate-spin mr-1.5" />
                                ) : (
                                  <Play className="w-3.5 h-3.5 mr-1.5 fill-current" />
                                )}
                                Run Workflow
                              </Button>
                            </div>
                          );
                        })}
                      {series.filter((item) => group === 'Other' || item.modality === group).length === 0 && (
                        <div className="text-center py-6 text-gray-400 text-xs italic">
                          No {group} series found in this project.
                        </div>
                      )}
                    </div>
                  </div>
                </div>
                );
              })}
            </div>
          </div>
        ))}
      </div>

      <div className="bg-amber-50 rounded-xl border border-amber-100 p-6 flex gap-4">
        <div className="p-2 bg-white rounded-lg border border-amber-200 text-amber-600 h-fit">
          <Info className="w-5 h-5" />
        </div>
        <div>
          <h3 className="text-sm font-bold text-amber-900 mb-1">Execution Guardrails</h3>
          <p className="text-xs text-amber-700 leading-relaxed">
            Workflows are restricted to their corresponding modalities. For example, QSIRecon workflows require a completed QSIPrep task.
            The "Run" button will only be active when all prerequisite backend records are verified.
          </p>
        </div>
      </div>
    </div>
  );
}

function Loader2({ className }: { className?: string }) {
  return <div className={`w-4 h-4 border-2 border-current border-t-transparent rounded-full animate-spin ${className}`} />;
}
