import { useQuery } from '@tanstack/react-query';
import { AlertTriangle } from 'lucide-react';
import { useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { ResultStudioLayout } from '../components/results/ResultStudioLayout';
import { api, getApiBase } from '../lib/api';
import { queryKeys } from '../lib/query';
import { normalizeWorkflowCatalog } from '../lib/workflows';

export function ResultDetailPage() {
  const projectId = Number(useParams().projectId);
  const taskId = Number(useParams().taskId);
  const [exportError, setExportError] = useState('');
  const [exportReadyDownload, setExportReadyDownload] = useState<{ filename: string; url: string } | null>(null);
  const [exporting, setExporting] = useState(false);
  const { data: summary, error, isLoading } = useQuery({ enabled: Boolean(taskId), queryFn: () => api.getResultSummary(taskId), queryKey: queryKeys.resultSummary(taskId) });
  const { data: workflowPayload } = useQuery({
    queryFn: api.listWorkflows,
    queryKey: queryKeys.workflows,
  });
  const workflowCatalog = normalizeWorkflowCatalog(workflowPayload);
  const { data: artifactManifest } = useQuery({
    enabled: Boolean(taskId),
    queryFn: () => api.getArtifactManifest(taskId),
    queryKey: ['artifact-manifest', taskId],
    retry: false,
  });

  if (isLoading) return <p className="text-sm text-muted">Loading result summary...</p>;
  if (error) return <p className="text-sm text-danger">{error instanceof Error ? error.message : 'Result summary unavailable'}</p>;
  if (!summary) return null;
  if (summary.project_id !== projectId) {
    return (
      <div className="mx-auto max-w-4xl rounded-lg border border-amber-200 bg-amber-50 p-5">
        <div className="flex items-start gap-3">
          <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-white text-amber-700">
            <AlertTriangle className="h-5 w-5" />
          </div>
          <div className="min-w-0 space-y-3">
            <div>
              <h1 className="text-base font-semibold text-amber-950">Result project mismatch</h1>
              <p className="mt-1 text-sm leading-6 text-amber-900">
                This result summary belongs to project {summary.project_id}, not project {projectId}.
              </p>
            </div>
            <Link
              to={`/projects/${projectId}/results`}
              className="inline-flex items-center rounded-md bg-amber-900 px-3 py-2 text-xs font-semibold text-white hover:bg-amber-800"
            >
              Back to results
            </Link>
          </div>
        </div>
      </div>
    );
  }

  async function exportBundle() {
    if (!taskId || exporting) return;
    setExporting(true);
    setExportError('');
    if (exportReadyDownload) {
      setExportReadyDownload(null);
    }
    try {
      const ticket = await api.createTaskExportBundleTicket(taskId);
      const downloadUrl = `${getApiBase()}${ticket.download_url}`;
      const filename = `image-agent-task-${taskId}-export.zip`;
      const link = document.createElement('a');
      link.href = downloadUrl;
      link.download = filename;
      link.rel = 'noreferrer';
      link.style.display = 'none';
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
    } catch (err) {
      setExportError(err instanceof Error ? err.message : 'Unable to download export bundle.');
    } finally {
      setExporting(false);
    }
  }

  return (
    <ResultStudioLayout
      apiBase={getApiBase()}
      artifactManifest={artifactManifest}
      exportError={exportError}
      exportReadyDownload={exportReadyDownload}
      exporting={exporting}
      onExportBundle={exportBundle}
      summary={summary}
      workflowDisplayName={
        summary.workflow_metadata?.display_name ||
        artifactManifest?.workflow_metadata?.display_name ||
        workflowCatalog.items[summary.workflow_type]?.display_name
      }
    />
  );
}
