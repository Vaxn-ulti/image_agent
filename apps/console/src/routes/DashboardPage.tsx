import { useQuery } from '@tanstack/react-query';
import { Database, FileText, ListChecks } from 'lucide-react';
import { useParams } from 'react-router-dom';
import { StatusBadge } from '../components/StatusBadge';
import { MetricBlock } from '../components/ui/MetricBlock';
import { PageHeader } from '../components/ui/PageHeader';
import { Panel, PanelBody, PanelHeader, PanelTitle } from '../components/ui/Panel';
import { api } from '../lib/api';
import { queryKeys } from '../lib/query';

export function DashboardPage() {
  const projectId = Number(useParams().projectId);
  const { data: series = [] } = useQuery({ enabled: Boolean(projectId), queryFn: () => api.listSeries(projectId), queryKey: queryKeys.series(projectId) });
  const { data: tasks = [] } = useQuery({ enabled: Boolean(projectId), queryFn: () => api.listProjectTasks(projectId), queryKey: queryKeys.tasks(projectId) });

  const active = tasks.filter((task) => task.status === 'queued' || task.status === 'running').length;
  const completed = tasks.filter((task) => task.status === 'completed' || task.status === 'completed_with_partial_failures').length;
  const modalityCounts = series.reduce<Record<string, number>>((counts, item) => {
    counts[item.modality] = (counts[item.modality] || 0) + 1;
    return counts;
  }, {});

  return (
    <div>
      <PageHeader
        description="Project health, modality readiness, active processing, and scientific result availability."
        eyebrow="Project Console"
        title="Overview"
      />
      <div className="grid gap-3 md:grid-cols-4">
        <MetricBlock detail="Registered imaging series" label="Series" value={series.length} />
        <MetricBlock detail="Queued or running" label="Active tasks" tone={active ? 'accent' : 'muted'} value={active} />
        <MetricBlock detail="Completed or partial" label="Results" tone="success" value={completed} />
        <MetricBlock detail="T1, BOLD, DWI coverage" label="Modalities" value={Object.keys(modalityCounts).length} />
      </div>
      <div className="mt-4 grid gap-4 lg:grid-cols-[1fr_1.2fr]">
        <Panel>
          <PanelHeader>
            <PanelTitle>Modality readiness</PanelTitle>
            <Database className="h-4 w-4 text-muted" />
          </PanelHeader>
          <PanelBody className="grid gap-2">
            {['T1', 'BOLD', 'DWI'].map((modality) => (
              <div className="flex items-center justify-between rounded-md border border-border bg-background px-3 py-2 text-sm" key={modality}>
                <span className="font-semibold">{modality}</span>
                <span className="text-muted">{modalityCounts[modality] || 0} series</span>
              </div>
            ))}
          </PanelBody>
        </Panel>
        <Panel>
          <PanelHeader>
            <PanelTitle>Result coverage</PanelTitle>
            <FileText className="h-4 w-4 text-muted" />
          </PanelHeader>
          <PanelBody>
            <div className="grid gap-2 md:grid-cols-3">
              <MetricBlock detail="Brain measures, cortical regions" label="T1 reports" tone={modalityCounts.T1 ? 'success' : 'muted'} value={modalityCounts.T1 ? 'Ready' : 'Missing'} />
              <MetricBlock detail="ALFF, fALFF, ReHo, tSNR" label="BOLD reports" tone={modalityCounts.BOLD ? 'success' : 'muted'} value={modalityCounts.BOLD ? 'Ready' : 'Missing'} />
              <MetricBlock detail="FA, MD, AD, RD" label="DWI reports" tone={modalityCounts.DWI ? 'success' : 'muted'} value={modalityCounts.DWI ? 'Ready' : 'Missing'} />
            </div>
          </PanelBody>
        </Panel>
      </div>
      <Panel className="mt-4">
        <PanelHeader>
          <PanelTitle>Recent tasks</PanelTitle>
          <ListChecks className="h-4 w-4 text-muted" />
        </PanelHeader>
        <PanelBody>
          <div className="divide-y divide-border">
            {tasks.slice(0, 8).map((task) => (
              <div className="flex items-center justify-between gap-3 py-2 text-sm" key={task.id}>
                <span>
                  <span className="font-mono text-xs text-muted">#{task.id}</span> {task.workflow_type}
                </span>
                <StatusBadge status={task.status} />
              </div>
            ))}
            {tasks.length === 0 ? <p className="text-sm text-muted">No tasks yet. Upload data, then run an eligible workflow.</p> : null}
          </div>
        </PanelBody>
      </Panel>
    </div>
  );
}
