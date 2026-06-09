import { Panel, PanelBody, PanelHeader, PanelTitle } from '../ui/Panel';

type ProvenancePanelProps = {
  provenance: Record<string, unknown>;
};

export function ProvenancePanel({ provenance }: ProvenancePanelProps) {
  const highlights = ['runtime_sec', 'max_runtime_sec', 'mni_registration_method', 'scientific_report_report_count', 'validation_only'];

  return (
    <Panel>
      <PanelHeader>
        <PanelTitle>Evidence chain</PanelTitle>
      </PanelHeader>
      <PanelBody>
        <div className="mb-3 grid gap-2">
          {highlights.map((key) =>
            key in provenance ? (
              <div className="flex items-center justify-between gap-3 rounded-md border border-border bg-background px-3 py-2 text-xs" key={key}>
                <span className="font-mono text-muted">{key}</span>
                <strong className="text-right text-foreground">{String(provenance[key])}</strong>
              </div>
            ) : null,
          )}
        </div>
        <pre className="scientific-scrollbar max-h-96 overflow-auto rounded-md bg-background p-3 font-mono text-xs leading-5 text-foreground">
          {JSON.stringify(provenance, null, 2)}
        </pre>
      </PanelBody>
    </Panel>
  );
}
