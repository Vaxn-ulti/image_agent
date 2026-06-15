import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';
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
});
