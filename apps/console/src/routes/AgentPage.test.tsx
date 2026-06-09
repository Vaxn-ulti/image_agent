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
      ragStatus: vi.fn().mockResolvedValue({ dependencies: { llama_index: false }, grounding_policy: { backend_records_rank: 'first' } }),
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

    expect(await screen.findByText(/Grounding policy/)).toBeInTheDocument();
    await userEvent.type(screen.getByLabelText('Agent query'), 'What happened to DWI?');
    await userEvent.click(screen.getByRole('button', { name: 'Ask agent' }));
    expect(await screen.findByText('Task 114 completed.')).toBeInTheDocument();
    expect(await screen.findByText('Agent evidence review')).toBeInTheDocument();
    expect(await screen.findByText('Backend context')).toBeInTheDocument();
    expect(await screen.findByText(/status\s*\|\s*langgraph/)).toBeInTheDocument();
    expect(await screen.findByText(/Read backend task\/output records first/)).toBeInTheDocument();
    expect(await screen.findByText(/inspect_task_status/)).toBeInTheDocument();
  });
});
