import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { api } from '../lib/api';
import { ResultsIndexPage } from './ResultsIndexPage';

vi.mock('../lib/api', () => ({
  api: {
    listProjectTasks: vi.fn(),
  },
}));

describe('ResultsIndexPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('blocks the results studio when project scoped tasks cannot load', async () => {
    vi.mocked(api.listProjectTasks).mockRejectedValue(new Error('Project not found'));
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });

    render(
      <QueryClientProvider client={client}>
        <MemoryRouter initialEntries={['/projects/13/results']}>
          <Routes>
            <Route element={<ResultsIndexPage />} path="/projects/:projectId/results" />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>,
    );

    expect(await screen.findByText('Project data unavailable')).toBeInTheDocument();
    expect(screen.getByText('Project not found')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Switch project' })).toHaveAttribute('href', '/projects');
    expect(screen.queryByText('No results available')).not.toBeInTheDocument();
  });
});
