import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { ReactElement } from 'react';
import { createBrowserRouter, Navigate, RouterProvider } from 'react-router-dom';
import { AppShell } from './components/AppShell';
import { AgentPage } from './routes/AgentPage';
import { DashboardPage } from './routes/DashboardPage';
import { IngestPage } from './routes/IngestPage';
import { LoginPage } from './routes/LoginPage';
import { ProjectsPage } from './routes/ProjectsPage';
import { ResultDetailPage } from './routes/ResultDetailPage';
import { ResultsIndexPage } from './routes/ResultsIndexPage';
import { ReportsPage } from './routes/ReportsPage';
import { SettingsPage } from './routes/SettingsPage';
import { TasksPage } from './routes/TasksPage';
import { WorkflowsPage } from './routes/WorkflowsPage';
import { getAuthToken } from './lib/api';

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      refetchOnWindowFocus: false,
      retry: 1,
    },
  },
});

function RequireAuth({ children }: { children: ReactElement }) {
  return getAuthToken() ? children : <Navigate replace to="/login" />;
}

const router = createBrowserRouter([
  { element: <LoginPage />, path: '/' },
  { element: <LoginPage />, path: '/login' },
  { element: <RequireAuth><ProjectsPage /></RequireAuth>, path: '/projects' },
  {
    children: [
      { element: <Navigate replace to="dashboard" />, index: true },
      { element: <DashboardPage />, path: 'dashboard' },
      { element: <IngestPage />, path: 'ingest' },
      { element: <WorkflowsPage />, path: 'workflows' },
      { element: <TasksPage />, path: 'tasks' },
      { element: <ResultsIndexPage />, path: 'results' },
      { element: <ResultDetailPage />, path: 'results/:taskId' },
      { element: <ReportsPage />, path: 'reports' },
      { element: <AgentPage />, path: 'agent' },
      { element: <SettingsPage />, path: 'settings' },
    ],
    element: <RequireAuth><AppShell /></RequireAuth>,
    path: '/projects/:projectId',
  },
]);

export function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={router} />
    </QueryClientProvider>
  );
}
