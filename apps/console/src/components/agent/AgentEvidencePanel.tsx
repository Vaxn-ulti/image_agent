import type { RagResponse } from '../../lib/types';
import { formatAgentText } from '../../lib/agentText';
import { safeEvidenceJson } from '../../lib/redaction';
import { Panel, PanelBody, PanelHeader, PanelTitle } from '../ui/Panel';

export function AgentEvidencePanel({ response }: { response: RagResponse }) {
  return (
    <Panel>
      <PanelHeader>
        <div>
          <PanelTitle>Agent evidence review</PanelTitle>
          <p className="mt-1 text-xs text-muted">
            {response.intent || 'unknown intent'} | {response.rag_mode || 'fallback'}
          </p>
        </div>
      </PanelHeader>
      <PanelBody>
        <div className="rounded-lg border border-border bg-background p-4">
          <div className="text-xs font-semibold uppercase tracking-normal text-muted">Answer</div>
          <p className="mt-2 whitespace-pre-line text-sm leading-6 text-foreground">{formatAgentText(response.answer)}</p>
        </div>
        <div className="mt-3 rounded-lg border border-accent/30 bg-accentSoft p-3">
          <div className="text-xs font-semibold uppercase tracking-normal text-accent">Recommended next step</div>
          <p className="mt-1 text-sm font-medium text-foreground">{response.recommended_next_step || response.tool_chain_hint || 'Review backend context and citations.'}</p>
        </div>
        <div className="mt-4 grid gap-3 lg:grid-cols-3">
          <EvidenceJson title="Tool chain" value={response.tool_invocations || []} />
          <EvidenceJson title="Backend context" value={response.backend_context || {}} />
          <EvidenceJson title="Citations" value={response.citations || []} />
        </div>
      </PanelBody>
    </Panel>
  );
}

function EvidenceJson({ title, value }: { title: string; value: unknown }) {
  return (
    <div>
      <h3 className="text-xs font-semibold uppercase tracking-normal text-muted">{title}</h3>
      <pre className="scientific-scrollbar mt-2 max-h-72 overflow-auto rounded-md bg-background p-3 font-mono text-xs leading-5">{safeEvidenceJson(value)}</pre>
    </div>
  );
}
