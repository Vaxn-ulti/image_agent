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

  it('redacts backend paths and secrets in evidence JSON blocks', () => {
    render(
      <AgentEvidencePanel
        response={{
          answer: 'Task 114 completed.',
          backend_context: {
            log_path: 'C:/Users/A/private/task.log',
            raw_path: '/home/yyf/project/image_agent/data/projects/13/raw/sub-01.nii.gz',
          },
          citations: [{ title: 'DWI docs', path: 'docs/dwi.md' }],
          intent: 'inspect_result',
          rag_mode: 'langgraph',
          tool_invocations: [{ result: { openai_key: 'sk-test-secret' }, status: 'ok', tool: 'result-summary' }],
        }}
      />,
    );

    expect(document.body.textContent).toContain('[redacted-host-path]');
    expect(document.body.textContent).toContain('[redacted-secret]');
    expect(document.body.textContent).not.toContain('C:/Users/A/private/task.log');
    expect(document.body.textContent).not.toContain('/home/yyf/project/image_agent/data/projects/13/raw/sub-01.nii.gz');
    expect(document.body.textContent).not.toContain('sk-test-secret');
  });
});
