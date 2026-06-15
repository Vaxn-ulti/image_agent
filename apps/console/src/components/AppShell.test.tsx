import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';
import { api } from '../lib/api';
import { AppShell } from './AppShell';

vi.mock('../lib/api', () => ({
  api: {
    deployment: vi.fn(),
    runtimeContainers: vi.fn(),
  },
  getApiBase: () => 'http://localhost:8000',
}));

describe('AppShell', () => {
  it('shows a disconnected API status when deployment status cannot be loaded', async () => {
    vi.mocked(api.deployment).mockRejectedValue(new Error('Network error'));
    vi.mocked(api.runtimeContainers).mockResolvedValue({ fs_license_exists: false });
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });

    render(
      <QueryClientProvider client={client}>
        <MemoryRouter initialEntries={['/projects/13/dashboard']}>
          <Routes>
            <Route element={<AppShell />} path="/projects/:projectId/dashboard" />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>,
    );

    expect(await screen.findByText('API disconnected')).toBeInTheDocument();
    expect(screen.queryByText('API connected')).not.toBeInTheDocument();
    expect(screen.getByText('Unavailable')).toBeInTheDocument();
  });
});
