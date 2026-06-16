import { useQuery } from '@tanstack/react-query';
import {
  AlertCircle,
  ExternalLink,
  Eye,
  History,
  Loader2,
  Search,
  Trash2
} from 'lucide-react';
import { Link, useParams } from 'react-router-dom';
import { StatusBadge } from '../components/StatusBadge';
import { PageHeader } from '../components/ui/PageHeader';
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
  const projectDataErrorMessage = error instanceof Error ? error.message : 'Could not load tasks';

  if (error) {
    return (
      <div className="max-w-6xl mx-auto space-y-6">
        <PageHeader
          description="Monitor queued, running, completed, failed, and cancelled backend work."
          eyebrow="Processing"
          title="Task Monitor"
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
        description="Monitor queued, running, completed, failed, and cancelled backend work."
        eyebrow="Processing"
        title="Task Monitor"
      />

      <div className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden flex flex-col transition-all hover:shadow-md">
        <div className="px-5 py-4 border-b border-gray-100 flex items-center justify-between font-semibold text-gray-800 text-sm">
          <div className="flex items-center gap-2">
            <History className="w-4 h-4 text-[#065F46]" /> Recent Execution History
          </div>
          <div className="flex items-center gap-3">
             <div className="relative">
                <Search className="w-3.5 h-3.5 absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" />
                <input
                  type="text"
                  placeholder="Filter tasks..."
                  className="pl-9 pr-3 py-1.5 bg-gray-50 border border-gray-200 rounded-md text-xs outline-none focus:border-[#065F46] transition-colors w-[200px]"
                />
             </div>
          </div>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm whitespace-nowrap">
            <thead className="bg-gray-50 text-gray-500 border-b border-gray-100">
              <tr>
                <th className="px-5 py-3 font-medium">ID</th>
                <th className="px-5 py-3 font-medium">Workflow</th>
                <th className="px-5 py-3 font-medium">Status</th>
                <th className="px-5 py-3 font-medium">Progress</th>
                <th className="px-5 py-3 font-medium">Details</th>
                <th className="px-5 py-3 font-medium text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100 text-gray-700">
              {tasks.map((task) => (
                <tr key={task.id} className="hover:bg-gray-50 transition-colors group">
                  <td className="px-5 py-4 font-mono text-xs text-gray-400">RUN-{task.id}</td>
                  <td className="px-5 py-4">
                    <div className="font-semibold text-gray-800">{task.workflow_type}</div>
                    <div className="text-[10px] text-gray-400 uppercase tracking-tighter">Backend Process</div>
                  </td>
                  <td className="px-5 py-4">
                    <StatusBadge status={task.status} />
                  </td>
                  <td className="px-5 py-4">
                    <div className="flex items-center gap-3">
                      <div className="w-24 h-1.5 bg-gray-100 rounded-full overflow-hidden">
                        <div
                          className={`h-full transition-all duration-500 ${
                            task.status === 'failed' ? 'bg-red-500' :
                            task.status === 'completed' ? 'bg-green-500' :
                            'bg-[#065F46]'
                          }`}
                          style={{ width: `${task.progress}%` }}
                        />
                      </div>
                      <span className="text-[10px] font-bold text-gray-500">{task.progress}%</span>
                    </div>
                  </td>
                  <td className="px-5 py-4">
                    {task.error_message ? (
                      <div className="flex items-center gap-1.5 text-red-500 text-xs truncate max-w-[200px]">
                        <AlertCircle className="w-3.5 h-3.5 shrink-0" />
                        {task.error_message}
                      </div>
                    ) : (
                      <div className="text-gray-400 text-xs italic">No issues reported</div>
                    )}
                  </td>
                  <td className="px-5 py-4 text-right">
                    <div className="flex items-center justify-end gap-2 opacity-0 group-hover:opacity-100 transition-opacity">
                      {(task.status === 'completed' || task.status === 'completed_with_partial_failures') ? (
                        <Link
                          aria-label={`Open result RUN-${task.id}`}
                          className="p-1.5 rounded-lg border border-gray-200 text-gray-500 hover:text-[#065F46] hover:border-[#065F46] bg-white transition-all shadow-sm"
                          to={`/projects/${projectId}/results/${task.id}`}
                          title="View Results"
                        >
                          <Eye className="w-4 h-4" />
                        </Link>
                      ) : null}
                      <button
                        className="p-1.5 rounded-lg border border-gray-200 text-gray-500 hover:text-red-500 hover:border-red-200 bg-white transition-all shadow-sm"
                        title="Delete Record"
                      >
                        <Trash2 className="w-4 h-4" />
                      </button>
                    </div>
                    {!(task.status === 'completed' || task.status === 'completed_with_partial_failures') && task.status !== 'failed' && (
                       <span className="text-[10px] font-bold text-gray-400 uppercase tracking-widest group-hover:hidden">Running...</span>
                    )}
                  </td>
                </tr>
              ))}
              {isLoading && (
                <tr>
                  <td className="px-5 py-12 text-center" colSpan={6}>
                    <div className="flex flex-col items-center gap-3">
                      <Loader2 className="w-8 h-8 animate-spin text-[#065F46] opacity-40" />
                      <span className="text-sm text-gray-400">Synchronizing with backend worker...</span>
                    </div>
                  </td>
                </tr>
              )}
              {!isLoading && tasks.length === 0 && (
                <tr>
                  <td className="px-5 py-16 text-center" colSpan={6}>
                    <div className="flex flex-col items-center gap-4 opacity-30">
                      <History className="w-16 h-16 text-gray-300" />
                      <p className="text-gray-500 text-sm">No backend tasks detected.<br/>Launch a workflow to see its execution lifecycle here.</p>
                    </div>
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      <div className="rounded-xl border border-[#065F46]/10 bg-[#065F46]/5 p-6 flex gap-5">
         <div className="w-12 h-12 rounded-full bg-white border border-[#065F46]/20 flex items-center justify-center text-[#065F46] shadow-sm shrink-0">
           <ExternalLink className="w-5 h-5" />
         </div>
         <div className="space-y-1">
           <h3 className="text-sm font-bold text-gray-900">Task Lifecycle Management</h3>
           <p className="text-xs text-gray-500 leading-relaxed">
             This monitor polls the backend API every 1.5 seconds when active tasks are detected.
             If a task enters an error state, click the details to see the sanitized execution log.
             Completed tasks will automatically unlock artifact manifests in the Results Studio.
           </p>
         </div>
      </div>
    </div>
  );
}
