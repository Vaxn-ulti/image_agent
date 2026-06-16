import { useQuery } from '@tanstack/react-query';
import {
  Activity,
  BarChart2,
  ChevronRight,
  Clock,
  FileCheck,
  Info,
  Layers,
  Search,
  Zap
} from 'lucide-react';
import { Link, useParams } from 'react-router-dom';
import { StatusBadge } from '../components/StatusBadge';
import { PageHeader } from '../components/ui/PageHeader';
import { api } from '../lib/api';
import { queryKeys } from '../lib/query';

export function ResultsIndexPage() {
  const projectId = Number(useParams().projectId);
  const tasksQuery = useQuery({
    enabled: Boolean(projectId),
    queryFn: () => api.listProjectTasks(projectId),
    queryKey: queryKeys.tasks(projectId)
  });
  const tasks = tasksQuery.data || [];
  const projectDataErrorMessage = tasksQuery.error instanceof Error
    ? tasksQuery.error.message
    : 'Project data could not be loaded.';

  const resultTasks = tasks.filter((task) =>
    task.status === 'completed' || task.status === 'completed_with_partial_failures'
  ).sort((a, b) => (b.finished_at || '').localeCompare(a.finished_at || '') || b.id - a.id);

  const getWorkflowIcon = (type: string) => {
    if (type.includes('t1')) return <Zap className="w-5 h-5" />;
    if (type.includes('dwi')) return <Layers className="w-5 h-5" />;
    if (type.includes('bold')) return <Activity className="w-5 h-5" />;
    return <BarChart2 className="w-5 h-5" />;
  };

  const formatDate = (iso: string | null | undefined) => {
    if (!iso) return 'Recent';
    return new Intl.DateTimeFormat(undefined, { dateStyle: 'medium' }).format(new Date(iso));
  };

  if (tasksQuery.isError) {
    return (
      <div className="max-w-6xl mx-auto space-y-6">
        <PageHeader
          description="Open completed task summaries, report figures, statistics, artifacts, and provenance."
          eyebrow="Scientific Review"
          title="Results Studio"
        />
        <div className="rounded-lg border border-amber-200 bg-amber-50 p-5">
          <div className="flex items-start gap-3">
            <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-white text-amber-700">
              <Info className="h-5 w-5" />
            </div>
            <div className="min-w-0 space-y-3">
              <div>
                <h2 className="text-base font-semibold text-amber-950">Project data unavailable</h2>
                <p className="mt-1 text-sm leading-6 text-amber-900">
                  {projectDataErrorMessage}
                </p>
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
        description="Open completed task summaries, report figures, statistics, artifacts, and provenance."
        eyebrow="Scientific Review"
        title="Results Studio"
      />

      {/* Stats Summary */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        <div className="bg-white p-5 rounded-xl border border-gray-200 shadow-sm flex items-center gap-4">
          <div className="w-12 h-12 rounded-lg bg-[#ECFDF5] text-[#065F46] flex items-center justify-center">
            <FileCheck className="w-6 h-6" />
          </div>
          <div>
            <div className="text-2xl font-bold text-gray-900">{resultTasks.length}</div>
            <div className="text-xs text-gray-400 font-bold uppercase tracking-wider">Completed Runs</div>
          </div>
        </div>
        <div className="bg-white p-5 rounded-xl border border-gray-200 shadow-sm flex items-center gap-4">
          <div className="w-12 h-12 rounded-lg bg-blue-50 text-blue-600 flex items-center justify-center">
            <Clock className="w-6 h-6" />
          </div>
          <div>
            <div className="text-2xl font-bold text-gray-900">
              {tasks.filter(t => t.status === 'running').length}
            </div>
            <div className="text-xs text-gray-400 font-bold uppercase tracking-wider">Active Tasks</div>
          </div>
        </div>
        <div className="bg-white p-5 rounded-xl border border-gray-200 shadow-sm flex items-center gap-4 relative overflow-hidden group">
           <div className="flex-1">
              <div className="text-xs font-bold text-gray-400 uppercase tracking-wider mb-2">Quick Search</div>
              <div className="relative">
                <Search className="w-3.5 h-3.5 absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" />
                <input
                  type="text"
                  placeholder="Find result..."
                  className="w-full pl-9 pr-3 py-1.5 bg-gray-50 border border-gray-200 rounded-md text-xs outline-none focus:border-[#065F46] transition-colors"
                />
              </div>
           </div>
        </div>
      </div>

      {/* Results Grid */}
      <div className="space-y-4">
        <div className="flex items-center justify-between px-2">
          <h2 className="text-sm font-bold text-gray-400 uppercase tracking-widest">Available Summaries</h2>
          <div className="flex items-center gap-2">
            <span className="text-[10px] font-bold text-gray-400">Sort by:</span>
            <select className="text-[10px] font-bold text-gray-600 bg-transparent outline-none cursor-pointer">
              <option>Newest First</option>
              <option>Task ID</option>
            </select>
          </div>
        </div>

        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
          {resultTasks.map((task) => (
            <Link
              key={task.id}
              to={`/projects/${projectId}/results/${task.id}`}
              className="bg-white p-5 rounded-xl border border-gray-200 shadow-sm hover:shadow-md hover:border-[#065F46]/30 transition-all group flex flex-col justify-between"
            >
              <div>
                <div className="flex items-center justify-between mb-4">
                  <div className="w-10 h-10 rounded-lg bg-gray-50 flex items-center justify-center text-gray-400 group-hover:bg-[#ECFDF5] group-hover:text-[#065F46] transition-colors">
                    {getWorkflowIcon(task.workflow_type)}
                  </div>
                  <StatusBadge status={task.status} />
                </div>
                <div className="font-bold text-gray-900 group-hover:text-[#065F46] transition-colors mb-1">
                  {task.workflow_type}
                </div>
                <div className="text-[10px] font-mono text-gray-400 mb-4">RUN_ID: {task.id}</div>
              </div>

              <div className="pt-4 border-t border-gray-100 flex items-center justify-between">
                <div className="flex items-center gap-1.5 text-xs text-gray-400 font-medium">
                  <Clock className="w-3.5 h-3.5" /> {formatDate(task.finished_at)}
                </div>
                <ChevronRight className="w-4 h-4 text-gray-300 group-hover:translate-x-1 transition-transform" />
              </div>
            </Link>
          ))}
        </div>

        {resultTasks.length === 0 && (
          <div className="bg-white rounded-xl border border-dashed border-gray-200 py-20 flex flex-col items-center justify-center text-center">
            <BarChart2 className="w-16 h-16 text-gray-200 mb-4" />
            <h3 className="text-gray-900 font-bold">No results available</h3>
            <p className="text-sm text-gray-500 max-w-xs mx-auto mt-2">
              Completed backend runs will generate result summaries here.
              Start by uploading data and running a workflow.
            </p>
            <Link
              to={`/projects/${projectId}/ingest`}
              className="mt-6 px-6 py-2 bg-[#065F46] text-white rounded-full text-xs font-bold hover:bg-[#044E3A] transition-colors shadow-sm"
            >
              Upload Data
            </Link>
          </div>
        )}
      </div>

      <div className="bg-blue-50 rounded-xl border border-blue-100 p-6 flex gap-4">
        <div className="p-2 bg-white rounded-lg border border-blue-200 text-blue-600 h-fit">
          <BarChart2 className="w-5 h-5" />
        </div>
        <div>
          <h3 className="text-sm font-bold text-blue-900 mb-1">Results Studio Overview</h3>
          <p className="text-xs text-blue-700 leading-relaxed">
            Each card represents a completed scientific workflow. Clicking a card opens the full artifact manifest,
            including T1 stats, BOLD descriptive reviews, or QSIRecon group analyses depending on the modality.
            All provenance records are cryptographically linked to the original container execution.
          </p>
        </div>
      </div>
    </div>
  );
}
