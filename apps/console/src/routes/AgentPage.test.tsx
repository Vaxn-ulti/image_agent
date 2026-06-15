import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';
import { api } from '../lib/api';
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
    },
  }));

describe('AgentPage', () => {
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
});
