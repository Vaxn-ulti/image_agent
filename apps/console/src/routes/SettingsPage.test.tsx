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
      api_base_hint: '',
      backend_runtime_mode: 'remote',
      production_readiness: {
        blocking_reasons: [
          'Agent model gateway is not configured.',
          'IMAGE_AGENT_PUBLIC_BASE_URL must be set for production deployment.',
        ],
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
    expect(await screen.findByText('IMAGE_AGENT_PUBLIC_BASE_URL must be set for production deployment.')).toBeInTheDocument();
    expect(await screen.findByText('Public API Base')).toBeInTheDocument();
    expect(await screen.findByText('Not reported')).toBeInTheDocument();
  });

  it('shows fast-launch readiness checks from deployment status', async () => {
    vi.mocked(api.deployment).mockResolvedValue({
      agent: { configured: true, model: 'deepseek-v4-pro', provider: 'deepseek' },
      backend_runtime_mode: 'remote',
      fast_launch_readiness: {
        blocking_reasons: [
          'Strict remote acceptance evidence has not been verified for the upload-agent-workflow-result chain.',
        ],
        checks: {
          agent_task_boundary: {
            chat_authority: 'read_explain_recommend',
            deterministic_launch_endpoint: '/series/{series_id}/run',
            status: 'passed',
            task_creation: 'server_side_resume_confirmation_only',
          },
          production_deployment: {
            blocking_reasons: [],
            readiness_status: 'ready',
            ready: true,
            required: false,
            status: 'blocked',
          },
          model_gateway_target: {
            actual_model: 'deepseek-v4-pro',
            actual_model_gateway_access: 'direct',
            actual_provider_profile: 'deepseek',
            actual_trust_env_proxy: false,
            actual_wire_api: 'chat_completions',
            expected_model: 'deepseek-v4-pro|deepseek-v4-flash',
            expected_model_gateway_access: 'direct',
            expected_provider_profile: 'deepseek',
            expected_trust_env_proxy: false,
            expected_wire_api: 'chat_completions',
            direct_transport: true,
            model_tool_loop: false,
            status: 'passed',
          },
          strict_remote_acceptance: {
            required_evidence: 'strict remote smoke JSON verified within freshness window',
            status: 'missing',
          },
          rag_elasticsearch_hybrid: {
            blocking_codes: [
              'rag_hybrid_lexical_retriever_not_standard',
              'rag_hybrid_vector_retriever_not_knn',
              'rag_hybrid_dense_vector_field_not_embedding',
            ],
            dense_vector_field: 'dense',
            embedding_endpoint_configured: false,
            official_rrf_source_present: false,
            lexical_retriever: 'bm25_only',
            status: 'blocked',
            vector_retriever: 'script_score',
          },
          upload_workflow_result_contract: {
            result_endpoints: [
              '/tasks/{task_id}/outputs',
              '/tasks/{task_id}/result-summary',
              '/tasks/{task_id}/artifact-manifest',
            ],
            series_endpoint: '/projects/{project_id}/series',
            status: 'passed',
            upload_endpoint: '/projects/{project_id}/upload',
            workflow_launch_endpoint: '/series/{series_id}/run',
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
        <SettingsPage />
      </QueryClientProvider>,
    );

    expect(await screen.findByText('Fast Launch Readiness')).toBeInTheDocument();
    expect(await screen.findByText('Launch blocked')).toBeInTheDocument();
    expect(await screen.findByText('deepseek / deepseek-v4-pro / chat_completions')).toBeInTheDocument();
    expect(await screen.findByText('Direct transport protected')).toBeInTheDocument();
    expect(await screen.findByText('Production deployment not enabled')).toBeInTheDocument();
    expect(await screen.findByText('Agent boundary protected')).toBeInTheDocument();
    expect(await screen.findByText('Strict remote acceptance missing')).toBeInTheDocument();
    expect(await screen.findByText('ES hybrid RAG blocked')).toBeInTheDocument();
    expect(await screen.findByText('bm25_only / script_score / dense')).toBeInTheDocument();
    expect(await screen.findByText('rag_hybrid_lexical_retriever_not_standard')).toBeInTheDocument();
    expect(await screen.findByText('rag_hybrid_vector_retriever_not_knn')).toBeInTheDocument();
    expect(await screen.findByText('rag_hybrid_dense_vector_field_not_embedding')).toBeInTheDocument();
    expect(
      await screen.findByText('Strict remote acceptance evidence has not been verified for the upload-agent-workflow-result chain.'),
    ).toBeInTheDocument();
    expect(screen.queryByText(/reciprocal-rank-fusion/)).not.toBeInTheDocument();
    expect(screen.queryByText(/sk-/)).not.toBeInTheDocument();
    expect(screen.queryByText(/\/home\/yyf\/project\/image_agent/)).not.toBeInTheDocument();
  });

  it('shows the backend public API base hint from deployment status', async () => {
    vi.mocked(api.deployment).mockResolvedValue({
      agent: { configured: true, provider: 'OpenAI' },
      api_base_hint: 'https://api.image-agent.example.com',
      backend_runtime_mode: 'remote',
      production_readiness: {
        blocking_reasons: [],
        ready: true,
        required: true,
        status: 'ready',
      },
    });
    vi.mocked(api.runtimeContainers).mockResolvedValue({ fs_license_exists: true });
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });

    render(
      <QueryClientProvider client={client}>
        <SettingsPage />
      </QueryClientProvider>,
    );

    expect(await screen.findByText('Public API Base')).toBeInTheDocument();
    expect(await screen.findByText('https://api.image-agent.example.com')).toBeInTheDocument();
  });

  it('shows disconnected API status when deployment cannot be loaded', async () => {
    vi.mocked(api.deployment).mockRejectedValue(new Error('backend unavailable'));
    vi.mocked(api.runtimeContainers).mockRejectedValue(new Error('runtime unavailable'));
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });

    render(
      <QueryClientProvider client={client}>
        <SettingsPage />
      </QueryClientProvider>,
    );

    expect(await screen.findByText('API disconnected')).toBeInTheDocument();
    expect(await screen.findByText('Backend status unavailable')).toBeInTheDocument();
    expect(await screen.findByText('Container status unavailable')).toBeInTheDocument();
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
