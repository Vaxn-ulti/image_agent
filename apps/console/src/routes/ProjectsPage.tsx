import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  FolderPlus,
  FolderRoot,
  Layout,
  Plus,
  Search,
  Settings2
} from 'lucide-react';
import { Link, useNavigate } from 'react-router-dom';
import { Button } from '../components/ui/Button';
import { Input } from '../components/ui/Input';
import { PageHeader } from '../components/ui/PageHeader';
import { api } from '../lib/api';
import { queryKeys } from '../lib/query';

export function ProjectsPage() {
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const { data: projects = [], error, isLoading } = useQuery({
    queryFn: api.listProjects,
    queryKey: queryKeys.projects
  });

  const createProject = useMutation({
    mutationFn: api.createProject,
    onSuccess: (project) => {
      queryClient.invalidateQueries({ queryKey: queryKeys.projects });
      navigate(`/projects/${project.id}/dashboard`);
    },
  });

  function onSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    createProject.mutate({
      description: String(form.get('description') || ''),
      name: String(form.get('name') || '')
    });
    event.currentTarget.reset();
  }

  return (
    <div className="min-h-screen bg-[#F8FAFC] font-sans antialiased text-[#1E293B]">
      <main className="mx-auto max-w-6xl p-8 space-y-12">
        <PageHeader
          description="Select a research project or create a new workspace for an imaging dataset."
          eyebrow="Workspace Management"
          title="Research Projects"
        />

        <div className="grid gap-8 lg:grid-cols-[340px_1fr]">
          {/* Create Project Panel */}
          <aside className="space-y-6">
            <div className="bg-white rounded-2xl border border-gray-200 shadow-sm overflow-hidden p-6 space-y-6 transition-all hover:shadow-md">
              <div className="flex items-center gap-2 font-bold text-gray-800 text-sm">
                <FolderPlus className="w-4 h-4 text-[#065F46]" /> New Project
              </div>
              <form className="space-y-4" onSubmit={onSubmit}>
                <div className="space-y-1.5">
                  <label className="text-[10px] font-bold text-gray-400 uppercase tracking-widest px-1" htmlFor="project-name">
                    Project Name
                  </label>
                  <Input
                    className="rounded-xl border-gray-200 bg-gray-50 focus:bg-white transition-all text-sm px-4 py-2.5"
                    id="project-name"
                    name="name"
                    required
                    placeholder="e.g. ADNI_3T_Cohort"
                  />
                </div>
                <div className="space-y-1.5">
                  <label className="text-[10px] font-bold text-gray-400 uppercase tracking-widest px-1" htmlFor="project-description">
                    Description
                  </label>
                  <Input
                    className="rounded-xl border-gray-200 bg-gray-50 focus:bg-white transition-all text-sm px-4 py-2.5"
                    id="project-description"
                    name="description"
                    placeholder="Brief objective..."
                  />
                </div>
                <Button
                  disabled={createProject.isPending}
                  variant="primary"
                  className="w-full bg-[#065F46] hover:bg-[#044E3A] rounded-xl py-2.5 font-bold shadow-md shadow-[#065F46]/10"
                >
                  {createProject.isPending ? 'Creating...' : 'Create Workspace'}
                </Button>
              </form>
            </div>

            <div className="p-5 bg-[#065F46]/5 rounded-2xl border border-[#065F46]/10">
               <h4 className="text-xs font-bold text-[#065F46] mb-2 flex items-center gap-2">
                 <Settings2 className="w-3.5 h-3.5" /> Workspace Tips
               </h4>
               <p className="text-[11px] text-gray-500 leading-relaxed">
                 Each project represents a unique scientific context. Workflows,
                 BIDS datasets, and Agent memory are isolated at the project level.
               </p>
            </div>
          </aside>

          {/* Projects List */}
          <div className="space-y-6">
            <div className="flex items-center justify-between px-2">
               <h2 className="text-sm font-bold text-gray-400 uppercase tracking-widest flex items-center gap-2">
                 <FolderRoot className="w-4 h-4" /> Active Workspaces
               </h2>
               <div className="relative">
                  <Search className="w-3.5 h-3.5 absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" />
                  <input
                    type="text"
                    placeholder="Search projects..."
                    className="pl-9 pr-3 py-1.5 bg-white border border-gray-200 rounded-lg text-xs outline-none focus:border-[#065F46] transition-colors w-[240px] shadow-sm"
                  />
               </div>
            </div>

            {isLoading && (
              <div className="py-20 flex flex-col items-center gap-4">
                 <div className="w-10 h-10 border-4 border-gray-100 border-t-[#065F46] rounded-full animate-spin"></div>
                 <span className="text-sm text-gray-400 font-medium">Loading workspaces...</span>
              </div>
            )}

            {error && (
              <div className="p-4 bg-red-50 border border-red-100 rounded-xl text-red-600 text-sm flex items-center gap-3">
                 <Plus className="w-4 h-4 rotate-45" /> {error instanceof Error ? error.message : 'Could not load projects'}
              </div>
            )}

            <div className="grid gap-4 sm:grid-cols-2">
              {projects.map((project) => (
                <Link
                  key={project.id}
                  to={`/projects/${project.id}/dashboard`}
                  className="bg-white p-6 rounded-2xl border border-gray-200 shadow-sm hover:shadow-md hover:border-[#065F46]/30 transition-all group flex flex-col justify-between h-40"
                >
                  <div>
                    <div className="flex items-center justify-between mb-3">
                       <div className="w-10 h-10 rounded-xl bg-gray-50 text-gray-400 flex items-center justify-center group-hover:bg-[#ECFDF5] group-hover:text-[#065F46] transition-colors">
                         <Layout className="w-5 h-5" />
                       </div>
                       <span className="text-[10px] font-mono font-bold text-gray-300">ID: {project.id}</span>
                    </div>
                    <div className="text-base font-bold text-gray-900 group-hover:text-[#065F46] transition-colors truncate">
                      {project.name}
                    </div>
                    <div className="mt-1 text-xs text-gray-500 line-clamp-2 leading-relaxed">
                      {project.description || 'No description provided for this project.'}
                    </div>
                  </div>
                </Link>
              ))}

              {!isLoading && projects.length === 0 && (
                <div className="col-span-full py-24 bg-white rounded-2xl border border-dashed border-gray-200 flex flex-col items-center justify-center text-center">
                  <FolderPlus className="w-16 h-16 text-gray-100 mb-4" />
                  <h3 className="text-gray-900 font-bold">No Projects Found</h3>
                  <p className="text-sm text-gray-500 mt-2">Create your first research workspace to begin processing data.</p>
                </div>
              )}
            </div>
          </div>
        </div>
      </main>

      <footer className="max-w-6xl mx-auto px-8 py-12 border-t border-gray-100 flex items-center justify-between text-[10px] font-bold text-gray-300 uppercase tracking-widest">
         <div>Neuro Imaging Agent &copy; 2026</div>
         <div className="flex gap-6">
            <a href="#" className="hover:text-gray-500">Documentation</a>
            <a href="#" className="hover:text-gray-500">Privacy Policy</a>
            <a href="#" className="hover:text-gray-500">Terms of Service</a>
         </div>
      </footer>
    </div>
  );
}
