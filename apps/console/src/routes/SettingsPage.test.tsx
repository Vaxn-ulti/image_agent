import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { api } from '../lib/api';
import { SettingsPage } from './SettingsPage';

vi.mock('../lib/api', () => ({
  api: {
    deployment: vi.fn(),
    runtimeContainers: vi.fn(),
  },
  getApiBase: () => localStorage.getItem('apiBase') || 'http://localhost:8000',
  resetApiBase: () => localStorage.removeItem('apiBase'),
  setApiBase: (value: string) => localStorage.setItem('apiBase', value.trim().replace(/\/+$/, '')),
}));

describe('SettingsPage', () => {
  beforeEach(() => {
    localStorage.clear();
    vi.clearAllMocks();
  });

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

  it('saves and resets the remote API base used by the console', async () => {
    vi.mocked(api.deployment).mockResolvedValue({
      agent: { configured: true, provider: 'OpenAI' },
      backend_runtime_mode: 'remote',
    });
    vi.mocked(api.runtimeContainers).mockResolvedValue({ fs_license_exists: true });
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });

    render(
      <QueryClientProvider client={client}>
        <SettingsPage />
      </QueryClientProvider>,
    );

    const input = await screen.findByLabelText('API Base Endpoint');
    await userEvent.clear(input);
    await userEvent.type(input, 'https://image-agent.example.com/');
    expect(api.deployment).toHaveBeenCalledTimes(1);
    expect(api.runtimeContainers).toHaveBeenCalledTimes(1);

    await userEvent.click(screen.getByRole('button', { name: /Save Changes/ }));

    expect(localStorage.getItem('apiBase')).toBe('https://image-agent.example.com');
    expect(await screen.findByDisplayValue('https://image-agent.example.com')).toBeInTheDocument();
    await waitFor(() => expect(api.deployment).toHaveBeenCalledTimes(2));
    await waitFor(() => expect(api.runtimeContainers).toHaveBeenCalledTimes(2));

    await userEvent.click(screen.getByRole('button', { name: 'Reset Defaults' }));

    expect(localStorage.getItem('apiBase')).toBeNull();
    expect(await screen.findByDisplayValue('http://localhost:8000')).toBeInTheDocument();
    await waitFor(() => expect(api.deployment).toHaveBeenCalledTimes(3));
    await waitFor(() => expect(api.runtimeContainers).toHaveBeenCalledTimes(3));
  });
});
