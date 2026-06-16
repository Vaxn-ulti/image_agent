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
  it('surfaces production readiness blockers in the global shell', async () => {
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
    vi.mocked(api.runtimeContainers).mockResolvedValue({ fs_license_exists: true });
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

    expect(await screen.findByText('Production blocked')).toBeInTheDocument();
    expect(await screen.findByText('Agent model gateway is not configured.')).toBeInTheDocument();
  });

  it('surfaces fast-launch blockers in the global shell', async () => {
    vi.mocked(api.deployment).mockResolvedValue({
      agent: { configured: true, model: 'gpt-5.5', provider: 'rawchat' },
      backend_runtime_mode: 'remote',
      fast_launch_readiness: {
        blocking_reasons: ['Strict remote acceptance evidence has not been verified for the upload-agent-workflow-result chain.'],
        checks: {
          model_gateway_target: {
            actual_model: 'gpt-5.5',
            actual_provider_profile: 'rawchat',
            actual_wire_api: 'responses',
            expected_model: 'gpt-5.5',
            expected_provider_profile: 'rawchat',
            expected_wire_api: 'responses',
            model_tool_loop: true,
            status: 'passed',
          },
          strict_remote_acceptance: {
            required_evidence: 'strict remote smoke JSON verified within freshness window',
            status: 'missing',
          },
        },
        ready: false,
        status: 'blocked',
      },
    });
    vi.mocked(api.runtimeContainers).mockResolvedValue({ fs_license_exists: true });
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

    expect(await screen.findByText('Launch blocked')).toBeInTheDocument();
    expect(await screen.findByText('Strict remote acceptance evidence has not been verified for the upload-agent-workflow-result chain.')).toBeInTheDocument();
  });

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
