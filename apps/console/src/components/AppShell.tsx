import { useQuery } from '@tanstack/react-query';
import {
  Activity,
  Bot,
  Boxes,
  Brain,
  ChevronDown,
  ChevronLeft,
  FileText,
  LayoutDashboard,
  ListChecks,
  Settings,
  UploadCloud,
} from 'lucide-react';
import { NavLink, Outlet, useParams } from 'react-router-dom';
import { api, getApiBase } from '../lib/api';
import { queryKeys } from '../lib/query';

const navItems = [
  { icon: LayoutDashboard, label: 'Overview', path: 'dashboard' },
  { icon: UploadCloud, label: 'Data & QC', path: 'ingest' },
  { icon: Boxes, label: 'Workflows', path: 'workflows' },
  { icon: ListChecks, label: 'Tasks', path: 'tasks' },
  { icon: Activity, label: 'Results Studio', path: 'results' },
  { icon: FileText, label: 'Reports', path: 'reports' },
  { icon: Bot, label: 'Agent Review', path: 'agent' },
  { icon: Settings, label: 'Settings', path: 'settings' },
];

export function AppShell() {
  const { projectId } = useParams();
  const { data: deployment } = useQuery({ queryFn: api.deployment, queryKey: queryKeys.deployment });
  const { data: runtime } = useQuery({ queryFn: api.runtimeContainers, queryKey: queryKeys.runtime, retry: false });

  return (
    <div className="flex h-screen bg-[#F8FAFC] text-[#1E293B] font-sans antialiased overflow-hidden">
      {/* Sidebar */}
      <aside className="w-[260px] flex-shrink-0 border-r border-[#E2E8F0] bg-white flex flex-col justify-between overflow-y-auto max-lg:hidden">
        <div>
          {/* Logo */}
          <div className="flex items-center gap-3 px-6 py-6 border-b border-[#E2E8F0]">
            <div className="text-[#065F46]">
              <Brain className="w-8 h-8" />
            </div>
            <div>
              <div className="font-bold text-sm leading-tight text-gray-900">Neuro Imaging Agent</div>
              <div className="text-xs text-gray-500 text-[10px] uppercase tracking-wider font-semibold">Console v1.0</div>
            </div>
          </div>

          {/* Project Context */}
          <div className="px-4 py-4">
            <div className="bg-gray-50 rounded-lg p-3 border border-[#E2E8F0]">
              <div className="text-[10px] font-bold text-gray-400 uppercase tracking-wider mb-1">Project</div>
              <div className="flex items-center justify-between font-medium text-gray-700 text-sm">
                Project {projectId} <ChevronDown className="w-3.5 h-3.5 text-gray-400" />
              </div>
            </div>
          </div>

          {/* Navigation */}
          <div className="px-4 py-2">
            <div className="text-[10px] font-bold text-gray-400 uppercase tracking-wider mb-2 px-2">Navigation</div>
            <nav className="space-y-1">
              {navItems.map((item) => (
                <NavLink
                  key={item.path}
                  to={`/projects/${projectId}/${item.path}`}
                  className={({ isActive }) =>
                    `flex items-center gap-3 px-3 py-2 rounded-md font-medium text-sm transition-colors ${
                      isActive
                        ? 'bg-[#ECFDF5] text-[#065F46]'
                        : 'text-gray-600 hover:bg-gray-50'
                    }`
                  }
                >
                  <item.icon className="w-4 h-4" />
                  {item.label}
                </NavLink>
              ))}
            </nav>
          </div>

          {/* Runtime Status */}
          <div className="px-4 py-4">
            <div className="text-[10px] font-bold text-gray-400 uppercase tracking-wider mb-2 px-2">System Status</div>
            <div className="bg-gray-50 rounded-lg p-3 space-y-3 text-xs border border-[#E2E8F0]">
              <div className="flex items-center justify-between">
                <span className="text-gray-500">Backend</span>
                <span className="font-medium text-gray-700 capitalize">{deployment?.backend_runtime_mode || 'local'}</span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-gray-500">Runtime</span>
                <div className="flex items-center gap-1.5 font-medium text-gray-700">
                  <div className={`w-2 h-2 rounded-full ${runtime?.fs_license_exists ? 'bg-green-500' : 'bg-amber-500'}`}></div>
                  {runtime?.fs_license_exists ? 'Ready' : 'Incomplete'}
                </div>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-gray-500">Agent</span>
                <span className="font-medium text-gray-700">{deployment?.agent?.configured ? 'Enabled' : 'Fallback'}</span>
              </div>
            </div>
          </div>
        </div>

        <div className="p-4 border-t border-[#E2E8F0]">
          <NavLink to="/projects" className="flex items-center gap-2 text-gray-500 hover:text-gray-700 text-sm font-medium">
            <ChevronLeft className="w-4 h-4" /> Switch project
          </NavLink>
        </div>
      </aside>

      {/* Main Content */}
      <main className="flex-1 overflow-y-auto">
        {/* Top Header */}
        <header className="flex items-center justify-between p-6 h-16 border-b border-[#E2E8F0] bg-white">
          <div className="flex items-center gap-2 text-xs font-semibold">
            <span className="flex items-center gap-1.5 px-2 py-1 rounded-full bg-green-50 text-green-700 border border-green-100">
              <div className="w-1.5 h-1.5 rounded-full bg-green-500"></div>
              API connected
            </span>
          </div>
          <div className="flex items-center gap-3">
             <button className="flex items-center gap-2 border border-gray-200 bg-white text-gray-700 px-3 py-1.5 rounded-md text-sm font-medium hover:bg-gray-50 shadow-sm transition-colors">
              <Settings className="w-4 h-4" /> Settings
            </button>
            <div className="flex items-center gap-2 border border-gray-200 bg-white px-1.5 py-1.5 rounded-md cursor-pointer hover:bg-gray-50 shadow-sm transition-colors">
              <div className="w-6 h-6 rounded bg-[#065F46] text-white flex items-center justify-center text-xs font-bold uppercase">NR</div>
              <ChevronDown className="w-3.5 h-3.5 text-gray-500 mr-1" />
            </div>
          </div>
        </header>

        {/* Page Content Area */}
        <div className="p-8 max-w-7xl mx-auto">
          <Outlet />
        </div>

        <footer className="px-8 py-6 border-t border-[#E2E8F0] text-xs text-gray-400 flex items-center justify-between">
          <div>API base: <span className="font-mono">{getApiBase()}</span></div>
          <div>Neuro Imaging Agent &copy; 2026</div>
        </footer>
      </main>
    </div>
  );
}
