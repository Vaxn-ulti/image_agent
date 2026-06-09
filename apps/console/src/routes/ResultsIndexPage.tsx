import { useQuery } from '@tanstack/react-query';
import { Link, useParams } from 'react-router-dom';
import { StatusBadge } from '../components/StatusBadge';
import { PageHeader } from '../components/ui/PageHeader';
import { Panel, PanelBody, PanelHeader, PanelTitle } from '../components/ui/Panel';
import { api } from '../lib/api';
import { queryKeys } from '../lib/query';

export function ResultsIndexPage() {
  const projectId = Number(useParams().projectId);
  const { data: tasks = [] } = useQuery({ enabled: Boolean(projectId), queryFn: () => api.listProjectTasks(projectId), queryKey: queryKeys.tasks(projectId) });
  const resultTasks = tasks.filter((task) => task.status === 'completed' || task.status === 'completed_with_partial_failures');

  return (
    <div>
      <PageHeader
        description="Open completed task summaries, report figures, statistics, artifacts, and provenance."
        eyebrow="Scientific Review"
        title="Results Studio"
      />
      <Panel>
        <PanelHeader>
          <PanelTitle>Available result summaries</PanelTitle>
          <span className="text-xs font-semibold text-muted">{resultTasks.length} completed</span>
        </PanelHeader>
        <PanelBody>
          <div className="divide-y divide-border">
            {resultTasks.map((task) => (
              <Link className="flex items-center justify-between gap-4 py-3 text-sm hover:text-accent" key={task.id} to={`/projects/${projectId}/results/${task.id}`}>
                <span>
                  <span className="font-mono text-xs text-muted">#{task.id}</span> <span className="font-semibold">{task.workflow_type}</span>
                </span>
                <StatusBadge status={task.status} />
              </Link>
            ))}
            {resultTasks.length === 0 ? <p className="text-sm text-muted">No completed result summaries yet.</p> : null}
          </div>
        </PanelBody>
      </Panel>
    </div>
  );
}
