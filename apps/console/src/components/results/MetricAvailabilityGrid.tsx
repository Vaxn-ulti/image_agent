import { CheckCircle2, CircleDashed } from 'lucide-react';
import type { OutputItem } from '../../lib/types';

type MetricAvailabilityGridProps = {
  artifacts: OutputItem[];
  metrics: string[];
  spaces?: string[];
};

function artifactText(artifact: OutputItem) {
  return `${artifact.relative_path || artifact.path || ''} ${artifact.feature_group || ''} ${artifact.output_type || ''} ${artifact.space || ''}`.toLowerCase();
}

function hasMetric(artifacts: OutputItem[], metric: string, space?: string) {
  const normalizedMetric = metric.toLowerCase();
  const normalizedSpace = space?.toLowerCase();
  return artifacts.some((artifact) => {
    const text = artifactText(artifact);
    return text.includes(normalizedMetric) && (!normalizedSpace || text.includes(normalizedSpace));
  });
}

export function MetricAvailabilityGrid({ artifacts, metrics, spaces = ['native', 'mni152'] }: MetricAvailabilityGridProps) {
  return (
    <div className="overflow-hidden rounded-lg border border-border bg-background">
      <div className="grid border-b border-border bg-panel text-xs font-semibold uppercase text-muted" style={{ gridTemplateColumns: `120px repeat(${spaces.length}, minmax(0, 1fr))` }}>
        <div className="px-3 py-2">Metric</div>
        {spaces.map((space) => (
          <div className="border-l border-border px-3 py-2" key={space}>
            {space}
          </div>
        ))}
      </div>
      {metrics.map((metric) => (
        <div className="grid border-b border-border last:border-b-0" key={metric} style={{ gridTemplateColumns: `120px repeat(${spaces.length}, minmax(0, 1fr))` }}>
          <div className="px-3 py-2 font-mono text-sm font-semibold">{metric}</div>
          {spaces.map((space) => {
            const available = hasMetric(artifacts, metric, space);
            return (
              <div className="flex items-center gap-2 border-l border-border px-3 py-2 text-sm" key={space}>
                {available ? <CheckCircle2 className="h-4 w-4 text-success" /> : <CircleDashed className="h-4 w-4 text-muted" />}
                <span className={available ? 'text-foreground' : 'text-muted'}>{available ? 'Available' : 'Pending'}</span>
              </div>
            );
          })}
        </div>
      ))}
    </div>
  );
}
