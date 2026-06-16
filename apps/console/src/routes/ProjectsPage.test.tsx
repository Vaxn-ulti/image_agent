import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';
import { api } from '../lib/api';
import { mockProject } from '../mocks/data';
import { ProjectsPage } from './ProjectsPage';

vi.mock('../lib/api', () => ({
  api: {
    createProject: vi.fn(),
    listProjects: vi.fn(),
  },
}));

function LocationProbe() {
  const location = useLocation();
  return <div data-testid="location">{location.pathname}</div>;
}

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <Routes>
          <Route element={<ProjectsPage />} path="/" />
          <Route element={<LocationProbe />} path="/projects/:projectId/dashboard" />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('ProjectsPage', () => {
  it('lists projects and creates a new project', async () => {
    vi.mocked(api.listProjects).mockResolvedValue([mockProject]);
    vi.mocked(api.createProject).mockResolvedValue({ ...mockProject, id: 14, name: 'New cohort' });

    renderPage();

    expect(await screen.findByText('MCI mixed modality acceptance')).toBeInTheDocument();

    await userEvent.type(screen.getByLabelText('Project Name'), 'New cohort');
    await userEvent.click(screen.getByRole('button', { name: 'Create Workspace' }));

    await waitFor(() => expect(api.createProject).toHaveBeenCalledWith({ description: '', name: 'New cohort' }));
    expect(await screen.findByTestId('location')).toHaveTextContent('/projects/14/dashboard');
  });
});
