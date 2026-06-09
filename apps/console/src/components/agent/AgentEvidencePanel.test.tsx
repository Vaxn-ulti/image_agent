import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { AgentEvidencePanel } from './AgentEvidencePanel';

describe('AgentEvidencePanel', () => {
  it('renders answer, next step, tool chain, backend context, and citations', () => {
    render(
      <AgentEvidencePanel
        response={{
          answer: 'Task 114 completed.',
          backend_context: { tasks: [{ id: 114 }] },
          citations: [{ title: 'DWI docs', path: 'docs/dwi.md' }],
          intent: 'inspect_result',
          rag_mode: 'langgraph',
          recommended_next_step: 'Open DWI tensor map matrix.',
          tool_invocations: [{ tool: 'result-summary', status: 'ok' }],
        }}
      />,
    );

    expect(screen.getByText('Task 114 completed.')).toBeInTheDocument();
    expect(screen.getByText('Open DWI tensor map matrix.')).toBeInTheDocument();
    expect(screen.getByText('Tool chain')).toBeInTheDocument();
    expect(screen.getByText('Backend context')).toBeInTheDocument();
    expect(screen.getByText('Citations')).toBeInTheDocument();
  });
});
