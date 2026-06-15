import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  Activity,
  Brain,
  CheckCircle2,
  ChevronRight,
  Info,
  Layers,
  Play,
  Zap
} from 'lucide-react';
import { useParams } from 'react-router-dom';
import { Button } from '../components/ui/Button';
import { PageHeader } from '../components/ui/PageHeader';
import { api } from '../lib/api';
import { queryKeys } from '../lib/query';
import { getWorkflowEligibility, groupWorkflows, normalizeWorkflowList } from '../lib/workflows';

export function WorkflowsPage() {
  const projectId = Number(useParams().projectId);
  const queryClient = useQueryClient();
  const { data: workflowPayload } = useQuery({ queryFn: api.listWorkflows, queryKey: queryKeys.workflows });
  const { data: series = [] } = useQuery({ enabled: Boolean(projectId), queryFn: () => api.listSeries(projectId), queryKey: queryKeys.series(projectId) });
  const { data: tasks = [] } = useQuery({ enabled: Boolean(projectId), queryFn: () => api.listProjectTasks(projectId), queryKey: queryKeys.tasks(projectId) });

  const runWorkflow = useMutation({
    mutationFn: ({ seriesId, workflowType }: { seriesId: number; workflowType: string }) => api.runSeries(seriesId, workflowType),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.tasks(projectId) });
    },
  });

  const grouped = groupWorkflows(normalizeWorkflowList(workflowPayload));

  const getIcon = (group: string) => {
    switch (group) {
      case 'T1': return <Brain className="w-4 h-4" />;
      case 'DWI': return <Layers className="w-4 h-4" />;
      case 'BOLD': return <Activity className="w-4 h-4" />;
      default: return <Zap className="w-4 h-4" />;
    }
  };

  return (
    <div className="max-w-6xl mx-auto space-y-8">
      <PageHeader
        description="Run backend-supported workflows only when prerequisites are satisfied."
        eyebrow="Execution"
        title="Workflows"
      />

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
              {workflows.map((workflow) => (
                <div key={workflow} className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden transition-all hover:shadow-md">
                  <div className="px-5 py-4 border-b border-gray-100 bg-gray-50/50 flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <span className="text-sm font-bold text-gray-800">{workflow}</span>
                      <span className="px-2 py-0.5 rounded-full bg-white border border-gray-200 text-gray-400 text-[10px] font-bold uppercase">
                        Standard Pipeline
                      </span>
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
                                disabled={!eligibility.runnable || runWorkflow.isPending}
                                onClick={() => runWorkflow.mutate({ seriesId: item.id, workflowType: workflow })}
                                className={`${
                                  eligibility.runnable
                                    ? 'bg-[#065F46] hover:bg-[#044E3A] text-white'
                                    : 'bg-gray-100 text-gray-400 cursor-not-allowed'
                                } px-4 shadow-sm group-hover:scale-105 transition-transform`}
                              >
                                {runWorkflow.isPending ? (
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
              ))}
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
