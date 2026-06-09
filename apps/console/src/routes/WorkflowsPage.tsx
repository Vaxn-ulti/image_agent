import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Play } from 'lucide-react';
import { useParams } from 'react-router-dom';
import { Button } from '../components/ui/Button';
import { PageHeader } from '../components/ui/PageHeader';
import { Panel, PanelBody, PanelHeader, PanelTitle } from '../components/ui/Panel';
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
    onSuccess: () => queryClient.invalidateQueries({ queryKey: queryKeys.tasks(projectId) }),
  });

  const grouped = groupWorkflows(normalizeWorkflowList(workflowPayload));

  return (
    <div className="space-y-4">
      <PageHeader description="Run backend-supported workflows only when prerequisites are satisfied." eyebrow="Execution" title="Workflows" />
      {Object.entries(grouped).map(
        ([group, workflows]) =>
          workflows.length > 0 && (
            <Panel key={group}>
              <PanelHeader>
                <PanelTitle>{group}</PanelTitle>
              </PanelHeader>
              <PanelBody className="space-y-3">
                {workflows.map((workflow) => (
                  <div className="rounded-md border border-border bg-background p-3" key={workflow}>
                    <div className="mb-2 text-sm font-medium">{workflow}</div>
                    <div className="grid gap-2">
                      {series
                        .filter((item) => group === 'Other' || item.modality === group)
                        .map((item) => {
                          const eligibility = getWorkflowEligibility(item, workflow, tasks);
                          return (
                            <div className="flex items-center justify-between gap-3 text-sm" key={`${workflow}-${item.id}`}>
                              <div>
                                <div>
                                  Series #{item.id} {item.sequence_label || item.modality}
                                </div>
                                {!eligibility.runnable ? <div className="text-xs text-warning">{eligibility.reason}</div> : null}
                              </div>
                              <Button disabled={!eligibility.runnable || runWorkflow.isPending} onClick={() => runWorkflow.mutate({ seriesId: item.id, workflowType: workflow })}>
                                <Play className="h-4 w-4" />
                                Run
                              </Button>
                            </div>
                          );
                        })}
                    </div>
                  </div>
                ))}
              </PanelBody>
            </Panel>
          ),
      )}
    </div>
  );
}
