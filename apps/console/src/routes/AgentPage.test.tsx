import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { api } from '../lib/api';
import { queryKeys } from '../lib/query';
import { AgentPage } from './AgentPage';

vi.mock('../lib/api', () => ({
    api: {
      ragQuery: vi.fn().mockResolvedValue({
        answer: 'Task 114 completed.',
        backend_context: { tasks: [{ id: 114 }] },
        citations: [],
        intent: 'status',
        recommended_next_step: 'Read backend task/output records first.',
        tool_chain_hint: 'Read backend task/output records first.',
        tool_invocations: [{ tool: 'inspect_task_status', status: 'ok', result: { task_count: 1 } }],
        rag_mode: 'langgraph',
      }),
      runAgent: vi.fn().mockResolvedValue({
        answer: 'Task 114 completed.',
        agent_run_id: 'agent_run_123',
        citations: [],
        intent: 'status',
        recommended_next_step: 'Read backend task/output records first.',
        selected_skill: 'image-agent-operator',
        status: 'answered',
        tool_chain_hint: 'Read backend task/output records first.',
        tool_invocations: [{ tool: 'inspect_task_status', status: 'ok', result: { task_count: 1 } }],
      }),
      resumeAgent: vi.fn().mockResolvedValue({
        agent_run_id: 'agent_run_resume_123',
        answer: 'Workflow task created.',
        status: 'task_created',
        task: {
          id: 118,
          project_id: 13,
          series_id: 24,
          workflow_type: 'bold_fmriprep_xcpd_report',
          status: 'queued',
          progress: 0,
        },
      }),
      listProjectAgentRuns: vi.fn().mockResolvedValue({
        agent_runs: [],
        contract_version: 'project_agent_run_history.v1',
        project_id: 13,
      }),
      getAgentRun: vi.fn().mockResolvedValue({
        agent_run_id: 'agent_run_history_123',
        answer: 'Reviewed task evidence.',
        contract_version: 'agent_run_lookup.v1',
        events: [
          {
            event_type: 'agent_tool_invoked',
            metadata: { note: '[redacted-host-path]' },
            status: 'ok',
          },
        ],
        project_id: 13,
        selected_skill: 'image-agent-operator',
        status: 'answered',
      }),
      listSeries: vi.fn().mockResolvedValue([]),
      ragStatus: vi.fn().mockResolvedValue({
        dependencies: { llama_index: { available: true } },
        grounding_policy: { backend_records_rank: 'first' },
        index: {
          chunk_count: 240,
          document_count: 60,
          engine: 'llama_index',
          semantic_index: true,
        },
      }),
      deployment: vi.fn().mockResolvedValue({
        agent: {
          configured: false,
          model: 'gpt-4.1-mini',
          provider: 'openai',
        },
        backend_runtime_mode: 'local',
      }),
    },
  }));

describe('AgentPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('blocks project-scoped agent chat when the project is unavailable', async () => {
    vi.mocked(api.listSeries).mockRejectedValueOnce(new Error('Project not found'));
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });

    render(
      <QueryClientProvider client={client}>
        <MemoryRouter initialEntries={['/projects/13/agent']}>
          <Routes>
            <Route element={<AgentPage />} path="/projects/:projectId/agent" />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>,
    );

    expect(await screen.findByText('Project data unavailable')).toBeInTheDocument();
    expect(screen.getByText('Project not found')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Switch project' })).toHaveAttribute('href', '/projects');
    expect(screen.queryByLabelText('Agent query')).not.toBeInTheDocument();
    expect(api.runAgent).not.toHaveBeenCalled();
  });

  it('shows grounding policy and query answer', async () => {
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });

    render(
      <QueryClientProvider client={client}>
        <MemoryRouter initialEntries={['/projects/13/agent']}>
          <Routes>
            <Route element={<AgentPage />} path="/projects/:projectId/agent" />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>,
    );

    expect(await screen.findByText(/Grounding Enabled/)).toBeInTheDocument();
    await userEvent.type(screen.getByLabelText('Agent query'), 'What happened to DWI?');
    await userEvent.click(screen.getByRole('button', { name: 'Send' }));
    expect(await screen.findByText('Task 114 completed.')).toBeInTheDocument();
    expect(await screen.findByText('Evidence Review')).toBeInTheDocument();
    expect(await screen.findByText('Intent Detection')).toBeInTheDocument();
    expect(await screen.findByText('status')).toBeInTheDocument();
    expect(await screen.findByText(/Read backend task\/output records first/)).toBeInTheDocument();
    expect(await screen.findByText(/inspect_task_status/)).toBeInTheDocument();
    expect(api.runAgent).toHaveBeenCalledWith(13, 'What happened to DWI?');
    expect(api.ragQuery).not.toHaveBeenCalled();
  });

  it('keeps multi-line Agent answers readable in the chat bubble', async () => {
    vi.mocked(api.runAgent).mockResolvedValueOnce({
      agent_run_id: 'agent_run_inventory_123',
      answer: 'Uploaded files\n1. sub-01_T1w.nii.gz\n\nRunnable fixed workflows\n1. t1_deepprep_anat_report',
      intent: 'inventory_capability',
      selected_skill: 'image-agent-operator',
      status: 'answered',
    });
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });

    render(
      <QueryClientProvider client={client}>
        <MemoryRouter initialEntries={['/projects/13/agent']}>
          <Routes>
            <Route element={<AgentPage />} path="/projects/:projectId/agent" />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>,
    );

    await userEvent.type(screen.getByLabelText('Agent query'), '我上传了什么文件，可以跑什么任务');
    await userEvent.click(screen.getByRole('button', { name: 'Send' }));

    const bubble = await screen.findByText(/Uploaded files/);
    expect(bubble).toHaveClass('whitespace-pre-line');
    expect(bubble.textContent).toContain('Runnable fixed workflows');
  });

  it('shows current Agent graph progress events in the evidence panel', async () => {
    vi.mocked(api.runAgent).mockResolvedValueOnce({
      agent_run_id: 'agent_run_events_123',
      answer: 'I reviewed the project without preparing a workflow confirmation.',
      events: [
        { type: 'agent.graph.load_context', status: 'ok', message: 'Loaded project context.' },
        { type: 'agent.graph.classify_intent', status: 'ok', message: 'Classified intent as answer_question.' },
        { type: 'agent.graph.match_workflow', status: 'not_applicable', message: 'Routed agent lane to read_only.' },
      ],
      intent: 'answer_question',
      selected_skill: 'image-agent-operator',
      status: 'answered',
    });
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });

    render(
      <QueryClientProvider client={client}>
        <MemoryRouter initialEntries={['/projects/13/agent']}>
          <Routes>
            <Route element={<AgentPage />} path="/projects/:projectId/agent" />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>,
    );

    await userEvent.type(screen.getByLabelText('Agent query'), '帮我看看这个项目当前适合做什么');
    await userEvent.click(screen.getByRole('button', { name: 'Send' }));

    expect(await screen.findByText('Agent Progress')).toBeInTheDocument();
    expect(screen.getByText('agent.graph.load_context')).toBeInTheDocument();
    expect(screen.getByText('Loaded project context.')).toBeInTheDocument();
    expect(screen.getByText('agent.graph.match_workflow')).toBeInTheDocument();
    expect(screen.queryByText('Approval required')).not.toBeInTheDocument();
  });

  it('shows read-only project Agent run history from the ledger contract', async () => {
    vi.mocked(api.listProjectAgentRuns).mockResolvedValueOnce({
      agent_runs: [
        {
          agent_run_id: 'agent_run_history_123',
          created_at: '2026-06-19T10:00:00+00:00',
          event_count: 3,
          model_gateway_access: 'openai_sdk_gateway',
          project_id: 13,
          request_type: 'run',
          selected_skill: 'image-agent-operator',
          status: 'answered',
        },
      ],
      contract_version: 'project_agent_run_history.v1',
      project_id: 13,
    });
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });

    render(
      <QueryClientProvider client={client}>
        <MemoryRouter initialEntries={['/projects/13/agent']}>
          <Routes>
            <Route element={<AgentPage />} path="/projects/:projectId/agent" />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>,
    );

    expect(await screen.findByText('Run History')).toBeInTheDocument();
    expect(await screen.findByText('agent_run_history_123')).toBeInTheDocument();
    expect(screen.getByText('answered')).toBeInTheDocument();
    expect(screen.getByText('image-agent-operator')).toBeInTheDocument();
    expect(screen.getByText('3 events')).toBeInTheDocument();
    expect(api.listProjectAgentRuns).toHaveBeenCalledWith(13);
    expect(document.body.textContent).not.toContain('patient');
    expect(document.body.textContent).not.toContain('/home/yyf/project/image_agent');
  });

  it('looks up selected Agent run details from the read-only ledger contract', async () => {
    vi.mocked(api.listProjectAgentRuns).mockResolvedValueOnce({
      agent_runs: [
        {
          agent_run_id: 'agent_run_history_123',
          event_count: 1,
          project_id: 13,
          request_type: 'run',
          selected_skill: 'image-agent-operator',
          status: 'answered',
        },
      ],
      contract_version: 'project_agent_run_history.v1',
      project_id: 13,
    });
    vi.mocked(api.getAgentRun).mockResolvedValueOnce({
      agent_run_id: 'agent_run_history_123',
      answer: 'Reviewed task evidence.',
      contract_version: 'agent_run_lookup.v1',
      events: [
        {
          event_type: 'agent_tool_invoked',
          metadata: { note: '[redacted-host-path]' },
          status: 'ok',
        },
      ],
      project_id: 13,
      selected_skill: 'image-agent-operator',
      status: 'answered',
    });
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });

    render(
      <QueryClientProvider client={client}>
        <MemoryRouter initialEntries={['/projects/13/agent']}>
          <Routes>
            <Route element={<AgentPage />} path="/projects/:projectId/agent" />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>,
    );

    await userEvent.click(await screen.findByRole('button', { name: 'Inspect agent_run_history_123' }));

    expect(api.getAgentRun).toHaveBeenCalledWith('agent_run_history_123');
    expect(await screen.findByText('Run Detail')).toBeInTheDocument();
    expect(screen.getAllByText('agent_run_history_123').length).toBeGreaterThan(0);
    expect(screen.getByText('agent_tool_invoked')).toBeInTheDocument();
    expect(screen.getByText(/Reviewed task evidence/)).toBeInTheDocument();
    expect(document.body.textContent).toContain('[redacted-host-path]');
    expect(document.body.textContent).not.toContain('/home/yyf/project/image_agent');
    expect(document.body.textContent).not.toContain('sk-');
  });

  it('redacts backend paths and secrets in Agent evidence JSON', async () => {
    vi.mocked(api.runAgent).mockResolvedValueOnce({
      agent_run_id: 'agent_run_redacted_123',
      answer: 'Task evidence reviewed.',
      citations: [],
      intent: 'status',
      selected_skill: 'image-agent-operator',
      status: 'answered',
      tool_invocations: [
        {
          result: {
            linux_path: '/home/yyf/project/image_agent/data/projects/13/raw/sub-01.nii.gz',
            openai_key: 'sk-test-secret',
            windows_path: 'C:/Users/A/private/task.log',
          },
          status: 'ok',
          tool: 'inspect_task_status',
        },
      ],
    });
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });

    render(
      <QueryClientProvider client={client}>
        <MemoryRouter initialEntries={['/projects/13/agent']}>
          <Routes>
            <Route element={<AgentPage />} path="/projects/:projectId/agent" />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>,
    );

    await userEvent.type(screen.getByLabelText('Agent query'), 'Inspect backend evidence');
    await userEvent.click(screen.getByRole('button', { name: 'Send' }));

    expect(await screen.findByText('Task evidence reviewed.')).toBeInTheDocument();
    expect(document.body.textContent).toContain('[redacted-host-path]');
    expect(document.body.textContent).toContain('[redacted-secret]');
    expect(document.body.textContent).not.toContain('C:/Users/A/private/task.log');
    expect(document.body.textContent).not.toContain('/home/yyf/project/image_agent/data/projects/13/raw/sub-01.nii.gz');
    expect(document.body.textContent).not.toContain('sk-test-secret');
  });

  it('shows a chat message when the Agent run fails', async () => {
    vi.mocked(api.runAgent).mockRejectedValueOnce(new Error('Agent model gateway unavailable.'));
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });

    render(
      <QueryClientProvider client={client}>
        <MemoryRouter initialEntries={['/projects/13/agent']}>
          <Routes>
            <Route element={<AgentPage />} path="/projects/:projectId/agent" />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>,
    );

    await userEvent.type(screen.getByLabelText('Agent query'), 'Summarize this project');
    await userEvent.click(screen.getByRole('button', { name: 'Send' }));

    expect(await screen.findByText('Summarize this project')).toBeInTheDocument();
    expect(await screen.findByText('Agent model gateway unavailable.')).toBeInTheDocument();
  });

  it('shows the configured model gateway state from deployment data', async () => {
    vi.mocked(api.deployment).mockResolvedValueOnce({
      agent: {
        configured: false,
        gateway_diagnostics: {
          model_tool_loop: 'skipped',
          request_shape: 'chat_messages',
          sdk_method: 'chat.completions.create',
          structured_output: 'chat_response_format_json_object',
          workflow_task_creation: 'server_side_resume_confirmation_only',
        },
        model: 'gpt-4.1-mini',
        provider: 'openai',
      },
      backend_runtime_mode: 'local',
    });
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });

    render(
      <QueryClientProvider client={client}>
        <MemoryRouter initialEntries={['/projects/13/agent']}>
          <Routes>
            <Route element={<AgentPage />} path="/projects/:projectId/agent" />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>,
    );

    expect(await screen.findByText('Model Gateway')).toBeInTheDocument();
    expect(await screen.findByText('Not configured')).toBeInTheDocument();
    expect(screen.getByText(/openai/i)).toBeInTheDocument();
    expect(screen.getByText('SDK Route')).toBeInTheDocument();
    expect(screen.getByText('chat.completions.create')).toBeInTheDocument();
    expect(screen.getByText('Tool Loop')).toBeInTheDocument();
    expect(screen.getByText('skipped')).toBeInTheDocument();
  });

  it('shows fallback RAG status from the backend instead of hard-coded readiness', async () => {
    vi.mocked(api.ragStatus).mockResolvedValueOnce({
      dependencies: {
        langgraph: { available: false },
        llama_index: { available: false },
      },
      grounding_policy: { backend_records_rank: 'first' },
      index: {
        chunk_count: 0,
        document_count: 0,
        engine: 'local_manifest',
        semantic_index: false,
      },
    });
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });

    render(
      <QueryClientProvider client={client}>
        <MemoryRouter initialEntries={['/projects/13/agent']}>
          <Routes>
            <Route element={<AgentPage />} path="/projects/:projectId/agent" />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>,
    );

    expect(await screen.findByText('Fallback Retrieval')).toBeInTheDocument();
    expect(await screen.findByText('Local manifest')).toBeInTheDocument();
    expect(await screen.findByText('0 docs / 0 chunks')).toBeInTheDocument();
    expect(screen.queryByText('semantic-v3')).not.toBeInTheDocument();
    expect(screen.queryByText('2 min ago')).not.toBeInTheDocument();
  });

  it('requires explicit approval before resuming an Agent workflow confirmation', async () => {
    vi.mocked(api.runAgent).mockResolvedValueOnce({
      agent_run_id: 'agent_run_confirm_123',
      answer: 'I can prepare this workflow, but approval is required.',
      confirmation: {
        action_lane: 'fixed_workflow',
        project_id: 13,
        series_id: 24,
        type: 'workflow_execution',
        workflow_metadata: {
          capability_summary: 'Runs full BOLD preprocessing, XCP-D derived metrics, container-native QC, and report outputs.',
          display_name: 'BOLD fMRIPrep + XCP-D processing, metrics, QC, and report',
          runtime_workflow_type: 'bold_fmriprep_xcpd_report',
          workflow_type: 'bold_fmriprep_xcpd_report',
        },
        workflow_type: 'bold_fmriprep_xcpd_report',
      },
      intent: 'run_workflow',
      selected_skill: 'image-agent-workflow-runner',
      status: 'confirmation_required',
      thread_id: 'thread-confirm-123',
    });
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const invalidate = vi.spyOn(client, 'invalidateQueries');

    render(
      <QueryClientProvider client={client}>
        <MemoryRouter initialEntries={['/projects/13/agent']}>
          <Routes>
            <Route element={<AgentPage />} path="/projects/:projectId/agent" />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>,
    );

    await userEvent.type(screen.getByLabelText('Agent query'), 'Run BOLD preprocessing');
    await userEvent.click(screen.getByRole('button', { name: 'Send' }));

    expect(await screen.findByText('Approval required')).toBeInTheDocument();
    expect(screen.getByText('BOLD fMRIPrep + XCP-D processing, metrics, QC, and report')).toBeInTheDocument();
    expect(screen.getByText('Runs full BOLD preprocessing, XCP-D derived metrics, container-native QC, and report outputs.')).toBeInTheDocument();
    expect(screen.getByText('Stable workflow ID')).toBeInTheDocument();
    expect(screen.getByText('bold_fmriprep_xcpd_report')).toBeInTheDocument();
    expect(screen.getByText('Task not created yet')).toBeInTheDocument();
    expect(screen.getByText('Backend API creates the task after approval.')).toBeInTheDocument();
    expect(api.resumeAgent).not.toHaveBeenCalled();
    expect(invalidate).not.toHaveBeenCalledWith({ queryKey: queryKeys.tasks(13) });

    await userEvent.click(screen.getByRole('button', { name: 'Approve workflow' }));

    expect(api.resumeAgent).toHaveBeenCalledWith('thread-confirm-123', true, {
      action_lane: 'fixed_workflow',
      project_id: 13,
      series_id: 24,
      type: 'workflow_execution',
      workflow_metadata: {
        capability_summary: 'Runs full BOLD preprocessing, XCP-D derived metrics, container-native QC, and report outputs.',
        display_name: 'BOLD fMRIPrep + XCP-D processing, metrics, QC, and report',
        runtime_workflow_type: 'bold_fmriprep_xcpd_report',
        workflow_type: 'bold_fmriprep_xcpd_report',
      },
      workflow_type: 'bold_fmriprep_xcpd_report',
    });
    expect(await screen.findByText(/Task 118 created/)).toBeInTheDocument();
    expect(invalidate).toHaveBeenCalledWith({ queryKey: queryKeys.tasks(13) });
    expect(invalidate).toHaveBeenCalledWith({ queryKey: queryKeys.task(118) });
  });

  it('refreshes project tasks when an Agent run returns a created task', async () => {
    vi.mocked(api.runAgent).mockResolvedValueOnce({
      agent_run_id: 'agent_run_task_144',
      answer: 'Workflow task created.',
      status: 'task_created',
      task: {
        id: 144,
        progress: 0,
        project_id: 13,
        series_id: 24,
        status: 'queued',
        workflow_type: 'bold_fmriprep_xcpd_report',
      },
    });
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const invalidate = vi.spyOn(client, 'invalidateQueries');

    render(
      <QueryClientProvider client={client}>
        <MemoryRouter initialEntries={['/projects/13/agent']}>
          <Routes>
            <Route element={<AgentPage />} path="/projects/:projectId/agent" />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>,
    );

    await userEvent.type(screen.getByLabelText('Agent query'), 'Create the reviewed workflow task');
    await userEvent.click(screen.getByRole('button', { name: 'Send' }));

    expect(await screen.findByText('Task 144 created for bold_fmriprep_xcpd_report.')).toBeInTheDocument();
    expect(invalidate).toHaveBeenCalledWith({ queryKey: queryKeys.tasks(13) });
    expect(invalidate).toHaveBeenCalledWith({ queryKey: queryKeys.task(144) });
  });
});
