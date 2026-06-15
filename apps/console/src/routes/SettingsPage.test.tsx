import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { api } from '../lib/api';
import { SettingsPage } from './SettingsPage';

vi.mock('../lib/api', () => ({
  api: {
    deployment: vi.fn(),
    runtimeContainers: vi.fn(),
  },
  getApiBase: () => 'http://localhost:8000',
}));

describe('SettingsPage', () => {
  it('renders runtime and agent configuration', async () => {
    vi.mocked(api.deployment).mockResolvedValue({
      agent: { configured: true, provider: 'langgraph' },
      backend_runtime_mode: 'local',
    });
    vi.mocked(api.runtimeContainers).mockResolvedValue({ fs_license_exists: true });
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });

    render(
      <QueryClientProvider client={client}>
        <SettingsPage />
      </QueryClientProvider>,
    );

    expect(await screen.findByRole('heading', { name: 'Settings' })).toBeInTheDocument();
    expect(await screen.findByText('API Connection')).toBeInTheDocument();
    expect(await screen.findByText('langgraph')).toBeInTheDocument();
  });

  it('shows production readiness blockers from deployment status', async () => {
    vi.mocked(api.deployment).mockResolvedValue({
      agent: { configured: false, provider: 'OpenAI' },
      backend_runtime_mode: 'remote',
      production_readiness: {
        blocking_reasons: ['Agent model gateway is not configured.'],
        ready: false,
        required: true,
        status: 'blocked',
      },
    });
    vi.mocked(api.runtimeContainers).mockResolvedValue({ fs_license_exists: false });
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });

    render(
      <QueryClientProvider client={client}>
        <SettingsPage />
      </QueryClientProvider>,
    );

    expect(await screen.findByText('Production Readiness')).toBeInTheDocument();
    expect(await screen.findByText('Blocked')).toBeInTheDocument();
    expect(await screen.findByText('Agent model gateway is not configured.')).toBeInTheDocument();
  });
});
