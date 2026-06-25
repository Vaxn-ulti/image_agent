import { useQuery } from '@tanstack/react-query';
import {
  AlertCircle,
  BookOpen,
  ChevronRight,
  Download,
  FileCheck,
  FileText,
  Search,
  Trophy
} from 'lucide-react';
import { Link, useParams } from 'react-router-dom';
import { StatusBadge } from '../components/StatusBadge';
import { PageHeader } from '../components/ui/PageHeader';
import { api } from '../lib/api';
import { queryKeys } from '../lib/query';
import { normalizeWorkflowCatalog } from '../lib/workflows';

export function ReportsPage() {
  const projectId = Number(useParams().projectId);
  const { data: tasks = [], error } = useQuery({
    enabled: Boolean(projectId),
    queryFn: () => api.listProjectTasks(projectId),
    queryKey: queryKeys.tasks(projectId)
  });
  const { data: workflowPayload } = useQuery({
    queryFn: api.listWorkflows,
    queryKey: queryKeys.workflows,
  });
  const workflowCatalog = normalizeWorkflowCatalog(workflowPayload);
  const projectDataErrorMessage = error instanceof Error ? error.message : 'Could not load reports';

  const reportTasks = tasks.filter((task) =>
    task.status === 'completed' || task.status === 'completed_with_partial_failures'
  ).sort((a, b) => (b.finished_at || '').localeCompare(a.finished_at || '') || b.id - a.id);

  if (error) {
    return (
      <div className="max-w-6xl mx-auto space-y-6">
        <PageHeader
          description="Curated scientific report entry points for publication review, artifact inspection, and downloadable evidence."
          eyebrow="Research Outputs"
          title="Scientific Reports"
        />

        <div className="rounded-lg border border-amber-200 bg-amber-50 p-5">
          <div className="flex items-start gap-3">
            <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-white text-amber-700">
              <AlertCircle className="h-5 w-5" />
            </div>
            <div className="min-w-0 space-y-3">
              <div>
                <h2 className="text-base font-semibold text-amber-950">Project data unavailable</h2>
                <p className="mt-1 text-sm leading-6 text-amber-900">{projectDataErrorMessage}</p>
              </div>
              <Link
                to="/projects"
                className="inline-flex items-center rounded-md bg-amber-900 px-3 py-2 text-xs font-semibold text-white hover:bg-amber-800"
              >
                Switch project
              </Link>
            </div>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="max-w-6xl mx-auto space-y-8">
      <PageHeader
        description="Curated scientific report entry points for publication review, artifact inspection, and downloadable evidence."
        eyebrow="Research Outputs"
        title="Scientific Reports"
      />

      {/* Header Stats */}
      <div className="flex items-center justify-between px-2">
         <div className="flex items-center gap-4">
            <div className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-[#ECFDF5] text-[#065F46] text-xs font-bold">
               <FileCheck className="w-3.5 h-3.5" /> {reportTasks.length} Reports Available
            </div>
            <div className="text-xs text-gray-400 font-medium">Updated 1 min ago</div>
         </div>
         <div className="relative">
            <Search className="w-3.5 h-3.5 absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" />
            <input
              type="text"
              placeholder="Filter reports..."
              className="pl-9 pr-3 py-1.5 bg-white border border-gray-200 rounded-md text-xs outline-none focus:border-[#065F46] transition-colors w-[220px]"
            />
         </div>
      </div>

      {/* Reports Grid */}
      <div className="grid gap-6 md:grid-cols-2">
        {reportTasks.map((task) => {
          const workflowDisplayName =
            task.workflow_metadata?.display_name ||
            workflowCatalog.items[task.workflow_type]?.display_name ||
            task.workflow_type;
          return (
          <div
            key={task.id}
            className="bg-white rounded-2xl border border-gray-200 shadow-sm overflow-hidden flex flex-col group transition-all hover:shadow-md hover:border-[#065F46]/20"
          >
            <div className="p-6 flex gap-5">
              <div className="w-16 h-16 rounded-xl bg-gray-50 flex items-center justify-center text-gray-400 group-hover:bg-[#ECFDF5] group-hover:text-[#065F46] transition-colors shrink-0">
                <FileText className="w-8 h-8" />
              </div>
              <div className="flex-1 min-w-0">
                <div className="flex items-center justify-between mb-1">
                  <span className="text-[10px] font-bold text-gray-400 uppercase tracking-widest">
                    #{task.id} | {task.workflow_type.split('_')[0].toUpperCase()}
                  </span>
                  <StatusBadge status={task.status} />
                </div>
                <h3 className="text-lg font-bold text-gray-900 group-hover:text-[#065F46] transition-colors truncate">
                  {workflowDisplayName}
                </h3>
                <div className="mt-1 text-[10px] font-medium text-gray-400">Stable workflow ID: {task.workflow_type}</div>
                <p className="text-xs text-gray-500 mt-1 leading-relaxed line-clamp-2">
                  Comprehensive review of cortical thickness, volume statistics, and automated segmentation
                  quality control images for series #{task.series_id || '0'}.
                </p>
              </div>
            </div>

            <div className="px-6 py-4 bg-gray-50 border-t border-gray-100 flex items-center justify-between">
              <div className="flex items-center gap-3">
                <Link
                  to={`/projects/${projectId}/results/${task.id}`}
                  className="flex items-center gap-1.5 text-xs font-bold text-[#065F46] hover:underline"
                >
                  <BookOpen className="w-3.5 h-3.5" /> View Report
                </Link>
                <div className="w-1 h-1 bg-gray-300 rounded-full"></div>
                <button className="flex items-center gap-1.5 text-xs font-bold text-gray-500 hover:text-gray-900">
                  <Download className="w-3.5 h-3.5" /> PDF
                </button>
              </div>
              <ChevronRight className="w-4 h-4 text-gray-300 group-hover:translate-x-1 transition-transform" />
            </div>
          </div>
          );
        })}

        {!reportTasks.length && (
          <div className="col-span-full py-24 bg-white rounded-2xl border border-dashed border-gray-200 flex flex-col items-center justify-center text-center">
            <Trophy className="w-16 h-16 text-gray-200 mb-4" />
            <h3 className="text-gray-900 font-bold text-lg">No ready reports yet</h3>
            <p className="text-sm text-gray-500 max-w-sm mx-auto mt-2">
              Complete a scientific workflow execution to generate peer-review ready reports
              and artifact manifests.
            </p>
            <Link
              to={`/projects/${projectId}/workflows`}
              className="mt-6 px-8 py-2.5 bg-[#065F46] text-white rounded-full text-xs font-bold hover:bg-[#044E3A] transition-colors shadow-lg"
            >
              Start Workflow
            </Link>
          </div>
        )}
      </div>

      <div className="bg-[#065F46]/5 rounded-2xl border border-[#065F46]/10 p-8 flex flex-col md:flex-row gap-8 items-center">
        <div className="flex-1 space-y-3 text-center md:text-left">
          <h3 className="text-lg font-bold text-[#065F46]">Publication Ready Evidence</h3>
          <p className="text-xs text-gray-600 leading-relaxed">
            All reports generated by the Neuro Imaging Agent are compliant with BIDS
            standards and include full provenance records for NIH/NSF transparency
            requirements. You can export these as PDF bundles or JSON-LD metadata for
            open-science repositories.
          </p>
        </div>
        <button className="px-6 py-3 bg-white border border-gray-200 text-gray-700 rounded-xl text-xs font-bold hover:bg-gray-50 transition-colors shadow-sm whitespace-nowrap">
          Manage Report Presets
        </button>
      </div>
    </div>
  );
}
