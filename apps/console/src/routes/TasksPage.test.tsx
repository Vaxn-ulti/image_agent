import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { api } from '../lib/api';
import { mockTasks } from '../mocks/data';
import { TasksPage } from './TasksPage';

vi.mock('../lib/api', () => ({
  api: {
    getLogs: vi.fn(),
    getOutputs: vi.fn(),
    listProjectTasks: vi.fn(),
  },
}));

describe('TasksPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders status vocabulary and result links', async () => {
    vi.mocked(api.listProjectTasks).mockResolvedValue(mockTasks);
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });

    render(
      <QueryClientProvider client={client}>
        <MemoryRouter initialEntries={['/projects/13/tasks']}>
          <Routes>
            <Route element={<TasksPage />} path="/projects/:projectId/tasks" />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>,
    );

    expect(await screen.findByText('RUN-114')).toBeInTheDocument();
    expect((await screen.findAllByText('Completed')).length).toBeGreaterThanOrEqual(3);
    expect(screen.getAllByRole('link', { name: /Open result/ }).map((link) => link.getAttribute('href'))).toContain(
      '/projects/13/results/114',
    );
  });

  it('renders running and failed backend task states without result links', async () => {
    vi.mocked(api.listProjectTasks).mockResolvedValue([
      { ...mockTasks[0], id: 201, progress: 35, status: 'running', workflow_type: 'bold_fmriprep_xcpd_report' },
      {
        ...mockTasks[0],
        error_message: 'Container image is not available.',
        id: 202,
        progress: 20,
        status: 'failed',
        workflow_type: 'dwi_fast_gpu_dti',
      },
    ]);
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });

    render(
      <QueryClientProvider client={client}>
        <MemoryRouter initialEntries={['/projects/13/tasks']}>
          <Routes>
            <Route element={<TasksPage />} path="/projects/:projectId/tasks" />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>,
    );

    expect(await screen.findByText('RUN-201')).toBeInTheDocument();
    expect(await screen.findByText('RUN-202')).toBeInTheDocument();
    expect(screen.getByText('Running')).toBeInTheDocument();
    expect(screen.getByText('Failed')).toBeInTheDocument();
    expect(screen.getByText('35%')).toBeInTheDocument();
    expect(screen.getByText('20%')).toBeInTheDocument();
    expect(screen.getByText('Container image is not available.')).toBeInTheDocument();
    expect(screen.queryByRole('link', { name: /Open result RUN-201/ })).not.toBeInTheDocument();
    expect(screen.queryByRole('link', { name: /Open result RUN-202/ })).not.toBeInTheDocument();
  });

  it('blocks the task monitor when project scoped tasks cannot load', async () => {
    vi.mocked(api.listProjectTasks).mockRejectedValue(new Error('Project not found'));
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });

    render(
      <QueryClientProvider client={client}>
        <MemoryRouter initialEntries={['/projects/13/tasks']}>
          <Routes>
            <Route element={<TasksPage />} path="/projects/:projectId/tasks" />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>,
    );

    expect(await screen.findByText('Project data unavailable')).toBeInTheDocument();
    expect(screen.getByText('Project not found')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Switch project' })).toHaveAttribute('href', '/projects');
    expect(screen.queryByText(/No backend tasks detected/)).not.toBeInTheDocument();
    expect(screen.queryByText('Recent Execution History')).not.toBeInTheDocument();
  });
});
