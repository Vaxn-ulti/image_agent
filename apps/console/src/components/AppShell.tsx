import { useQuery } from '@tanstack/react-query';
import { Activity, Bot, Boxes, FileText, LayoutDashboard, ListChecks, Settings, UploadCloud } from 'lucide-react';
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
    <div className="grid min-h-screen grid-cols-[248px_1fr] overflow-x-hidden bg-background text-foreground max-lg:grid-cols-1">
      <aside className="min-w-0 border-r border-border bg-panel px-3 py-4 max-lg:overflow-hidden max-lg:border-b max-lg:border-r-0">
        <div className="mb-4 flex items-center gap-2 px-2 text-sm font-semibold">
          <span className="grid h-7 w-7 place-items-center rounded-md bg-accent text-xs font-bold text-paper">BI</span>
          Brain Image Agent
        </div>
        <div className="mb-4 rounded-lg border border-border bg-paper p-3">
          <div className="text-sm font-semibold">Project {projectId}</div>
          <div className="mt-1 text-xs leading-5 text-muted">Research workspace</div>
        </div>
        <nav className="space-y-1 max-lg:flex max-lg:w-full max-lg:min-w-0 max-lg:overflow-x-auto">
          {navItems.map((item) => (
            <NavLink
              className={({ isActive }) =>
                `flex items-center gap-2 rounded-md px-3 py-2 text-sm ${
                  isActive ? 'bg-background text-foreground shadow-hairline' : 'text-muted hover:bg-background hover:text-foreground'
                }`
              }
              key={item.path}
              to={`/projects/${projectId}/${item.path}`}
            >
              <item.icon className="h-4 w-4 shrink-0" />
              <span className="whitespace-nowrap">{item.label}</span>
            </NavLink>
          ))}
        </nav>
      </aside>
      <div className="min-w-0">
        <header className="flex min-h-14 items-center justify-between gap-3 border-b border-border bg-paper px-5 max-md:flex-col max-md:items-start max-md:py-3">
          <div className="flex flex-wrap items-center gap-2 text-xs font-semibold text-muted">
            <span className="rounded-full border border-success/30 bg-success/10 px-2 py-1 text-success">API connected</span>
            <span className="rounded-full border border-border bg-background px-2 py-1">{deployment?.backend_runtime_mode || 'Backend'}</span>
            <span className="rounded-full border border-border bg-background px-2 py-1">{runtime?.fs_license_exists ? 'Runtime ready' : 'Runtime unknown'}</span>
            <span className="rounded-full border border-border bg-background px-2 py-1">Agent {deployment?.agent?.configured ? 'configured' : 'fallback'}</span>
          </div>
          <NavLink className="text-sm text-muted hover:text-foreground" to="/projects">
            Switch project
          </NavLink>
        </header>
        <main className="p-5">
          <Outlet />
        </main>
        <footer className="border-t border-border px-5 py-3 text-xs text-muted">
          API base: <span className="font-mono">{getApiBase()}</span>
        </footer>
      </div>
    </div>
  );
}
