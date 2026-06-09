import { useQuery } from '@tanstack/react-query';
import { Link, useParams } from 'react-router-dom';
import { StatusBadge } from '../components/StatusBadge';
import { DataTable, TableCell, TableHead, TableHeaderCell, TableRow } from '../components/ui/DataTable';
import { PageHeader } from '../components/ui/PageHeader';
import { Panel, PanelBody, PanelHeader, PanelTitle } from '../components/ui/Panel';
import { api } from '../lib/api';
import { hasActiveTasks, queryKeys } from '../lib/query';

export function TasksPage() {
  const projectId = Number(useParams().projectId);
  const { data: tasks = [], error, isLoading } = useQuery({
    enabled: Boolean(projectId),
    queryFn: () => api.listProjectTasks(projectId),
    queryKey: queryKeys.tasks(projectId),
    refetchInterval: (query) => (hasActiveTasks(query.state.data) ? 1500 : false),
  });

  return (
    <div className="space-y-4">
      <PageHeader description="Monitor queued, running, completed, failed, and cancelled backend work." eyebrow="Processing" title="Tasks" />
      <Panel>
        <PanelHeader>
          <PanelTitle>Task queue</PanelTitle>
        </PanelHeader>
        <PanelBody>
          {isLoading ? <p className="text-sm text-muted">Loading tasks...</p> : null}
          {error ? <p className="text-sm text-danger">{error instanceof Error ? error.message : 'Could not load tasks'}</p> : null}
          <DataTable empty="No backend tasks yet." isEmpty={!isLoading && !tasks.length}>
            <TableHead>
              <tr>
                <TableHeaderCell>Task</TableHeaderCell>
                <TableHeaderCell>Workflow</TableHeaderCell>
                <TableHeaderCell>Status</TableHeaderCell>
                <TableHeaderCell>Progress</TableHeaderCell>
                <TableHeaderCell>Error</TableHeaderCell>
                <TableHeaderCell>Result</TableHeaderCell>
              </tr>
            </TableHead>
            <tbody>
              {tasks.map((task) => (
                <TableRow key={task.id}>
                  <TableCell>#{task.id}</TableCell>
                  <TableCell>{task.workflow_type}</TableCell>
                  <TableCell>
                    <StatusBadge status={task.status} />
                  </TableCell>
                  <TableCell>{task.progress}%</TableCell>
                  <TableCell>{task.error_message || ''}</TableCell>
                  <TableCell>
                    {task.status === 'completed' || task.status === 'completed_with_partial_failures' ? (
                      <Link className="text-accent hover:underline" to={`/projects/${projectId}/results/${task.id}`}>
                        Open result
                      </Link>
                    ) : (
                      <span className="text-muted">Pending</span>
                    )}
                  </TableCell>
                </TableRow>
              ))}
            </tbody>
          </DataTable>
        </PanelBody>
      </Panel>
    </div>
  );
}
