import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { useEffect, useState, type ReactElement } from 'react';
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
import { GeminiStandaloneApp } from './routes/GeminiStandaloneApp';
import { authExpiredEventName, getAuthToken } from './lib/api';

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      refetchOnWindowFocus: false,
      retry: 1,
    },
  },
});

export function RequireAuth({ children }: { children: ReactElement }) {
  const [hasToken, setHasToken] = useState(() => Boolean(getAuthToken()));

  useEffect(() => {
    const handleAuthExpired = () => setHasToken(false);
    window.addEventListener(authExpiredEventName, handleAuthExpired);
    return () => window.removeEventListener(authExpiredEventName, handleAuthExpired);
  }, []);

  return hasToken ? children : <Navigate replace to="/login" />;
}

const router = createBrowserRouter([
  { element: <LoginPage />, path: '/' },
  { element: <LoginPage />, path: '/login' },
  { element: <RequireAuth><ProjectsPage /></RequireAuth>, path: '/projects' },
  { element: <GeminiStandaloneApp />, path: '/gemini' },
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
