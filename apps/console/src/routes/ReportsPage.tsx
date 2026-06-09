import { useQuery } from '@tanstack/react-query';
import { Link, useParams } from 'react-router-dom';
import { StatusBadge } from '../components/StatusBadge';
import { PageHeader } from '../components/ui/PageHeader';
import { Panel, PanelBody, PanelHeader, PanelTitle } from '../components/ui/Panel';
import { api } from '../lib/api';
import { queryKeys } from '../lib/query';

export function ReportsPage() {
  const projectId = Number(useParams().projectId);
  const { data: tasks = [] } = useQuery({ enabled: Boolean(projectId), queryFn: () => api.listProjectTasks(projectId), queryKey: queryKeys.tasks(projectId) });
  const reportTasks = tasks.filter((task) => task.status === 'completed' || task.status === 'completed_with_partial_failures');

  return (
    <div>
      <PageHeader
        description="Curated scientific report entry points for publication review, artifact inspection, and downloadable evidence."
        eyebrow="Research Outputs"
        title="Reports"
      />
      <Panel>
        <PanelHeader>
          <PanelTitle>Report-ready tasks</PanelTitle>
          <span className="text-xs font-semibold text-muted">{reportTasks.length} available</span>
        </PanelHeader>
        <PanelBody>
          <div className="grid gap-3">
            {reportTasks.map((task) => (
              <Link className="grid gap-3 rounded-md border border-border bg-background p-3 text-sm hover:border-accent/50 md:grid-cols-[1fr_auto]" key={task.id} to={`/projects/${projectId}/results/${task.id}`}>
                <div>
                  <div className="font-semibold">{task.workflow_type}</div>
                  <div className="mt-1 font-mono text-xs text-muted">Task #{task.id} | series {task.series_id || 'not linked'}</div>
                </div>
                <StatusBadge status={task.status} />
              </Link>
            ))}
            {!reportTasks.length ? <p className="text-sm text-muted">No completed report tasks yet.</p> : null}
          </div>
        </PanelBody>
      </Panel>
    </div>
  );
}
