import { useQuery } from '@tanstack/react-query';
import { PageHeader } from '../components/ui/PageHeader';
import { Panel, PanelBody, PanelHeader, PanelTitle } from '../components/ui/Panel';
import { api, getApiBase } from '../lib/api';
import { queryKeys } from '../lib/query';

export function SettingsPage() {
  const { data: deployment } = useQuery({ queryFn: api.deployment, queryKey: queryKeys.deployment });
  const { data: runtime } = useQuery({ queryFn: api.runtimeContainers, queryKey: queryKeys.runtime, retry: false });

  return (
    <div>
      <PageHeader
        description="Runtime, API, and agent configuration signals used by the scientific console."
        eyebrow="Environment"
        title="Settings"
      />
      <div className="grid gap-4 lg:grid-cols-2">
        <Panel>
          <PanelHeader>
            <PanelTitle>API connection</PanelTitle>
          </PanelHeader>
          <PanelBody className="space-y-3 text-sm">
            <div className="rounded-md border border-border bg-background p-3">
              <div className="text-xs font-semibold uppercase text-muted">API base</div>
              <div className="mt-1 break-all font-mono">{getApiBase()}</div>
            </div>
            <div className="rounded-md border border-border bg-background p-3">
              <div className="text-xs font-semibold uppercase text-muted">Backend mode</div>
              <div className="mt-1 font-mono">{deployment?.backend_runtime_mode || 'unknown'}</div>
            </div>
          </PanelBody>
        </Panel>
        <Panel>
          <PanelHeader>
            <PanelTitle>Runtime and agent</PanelTitle>
          </PanelHeader>
          <PanelBody className="space-y-3 text-sm">
            <div className="rounded-md border border-border bg-background p-3">
              <div className="text-xs font-semibold uppercase text-muted">FreeSurfer license</div>
              <div className="mt-1 font-mono">{runtime?.fs_license_exists ? 'available' : 'not reported'}</div>
            </div>
            <div className="rounded-md border border-border bg-background p-3">
              <div className="text-xs font-semibold uppercase text-muted">Agent provider</div>
              <div className="mt-1 font-mono">{deployment?.agent?.provider || 'fallback'}</div>
            </div>
          </PanelBody>
        </Panel>
      </div>
    </div>
  );
}
