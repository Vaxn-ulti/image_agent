import { useMutation, useQuery } from '@tanstack/react-query';
import { useState } from 'react';
import { useParams } from 'react-router-dom';
import { AgentEvidencePanel } from '../components/agent/AgentEvidencePanel';
import { Button } from '../components/ui/Button';
import { Input } from '../components/ui/Input';
import { PageHeader } from '../components/ui/PageHeader';
import { Panel, PanelBody, PanelHeader, PanelTitle } from '../components/ui/Panel';
import { api } from '../lib/api';
import { queryKeys } from '../lib/query';

export function AgentPage() {
  const projectId = Number(useParams().projectId);
  const [query, setQuery] = useState('');
  const { data: status } = useQuery({ queryFn: api.ragStatus, queryKey: queryKeys.ragStatus });
  const ask = useMutation({ mutationFn: (message: string) => api.ragQuery(projectId, message) });

  function onSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (query.trim()) ask.mutate(query.trim());
  }

  return (
    <div className="space-y-4">
      <PageHeader
        description="Ask grounded questions about project tasks, result summaries, workflow documentation, and recommended review actions."
        eyebrow="Agent Review"
        title="Agent Review"
      />
      <Panel>
        <PanelHeader>
          <PanelTitle>Grounding policy</PanelTitle>
        </PanelHeader>
        <PanelBody>
          <pre className="overflow-auto rounded-md bg-background p-3 font-mono text-xs">{JSON.stringify(status || {}, null, 2)}</pre>
        </PanelBody>
      </Panel>
      <Panel>
        <PanelHeader>
          <PanelTitle>Query</PanelTitle>
        </PanelHeader>
        <PanelBody>
          <form className="flex gap-2 max-sm:flex-col" onSubmit={onSubmit}>
            <label className="sr-only" htmlFor="agent-query">
              Agent query
            </label>
            <Input
              aria-label="Agent query"
              id="agent-query"
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Explain task status, result summaries, or workflow requirements"
              value={query}
            />
            <Button disabled={ask.isPending} variant="primary">
              Ask agent
            </Button>
          </form>
        </PanelBody>
      </Panel>
      {ask.data ? <AgentEvidencePanel response={ask.data} /> : null}
    </div>
  );
}
