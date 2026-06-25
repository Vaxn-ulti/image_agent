import type { ReactNode } from 'react';
import { Panel, PanelBody, PanelHeader, PanelTitle } from '../ui/Panel';

type ScientificChartPanelProps = {
  title: string;
  source?: string;
  metric?: string;
  empty?: boolean;
  emptyMessage?: string;
  children: ReactNode;
};

export function ScientificChartPanel({ children, empty, emptyMessage, metric, source, title }: ScientificChartPanelProps) {
  return (
    <Panel>
      <PanelHeader>
        <div>
          <PanelTitle>{title}</PanelTitle>
          {metric || source ? (
            <p className="mt-1 text-xs text-muted">
              {metric ? <span>{metric}</span> : null}
              {metric && source ? <span> | </span> : null}
              {source ? <span className="font-mono">{source}</span> : null}
            </p>
          ) : null}
        </div>
      </PanelHeader>
      <PanelBody>
        {empty ? (
          <div className="rounded-md border border-dashed border-border bg-panel p-4 text-sm text-muted">
            {emptyMessage || 'No source data registered for this view.'}
          </div>
        ) : (
          children
        )}
      </PanelBody>
    </Panel>
  );
}
