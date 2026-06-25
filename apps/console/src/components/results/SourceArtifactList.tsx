import { displayArtifactName } from '../../lib/resultArtifacts';
import type { OutputItem } from '../../lib/types';

type SourceArtifactListProps = {
  artifacts: OutputItem[];
  emptyLabel?: string;
  limit?: number;
};

export function SourceArtifactList({ artifacts, emptyLabel = 'No artifacts registered.', limit = 4 }: SourceArtifactListProps) {
  const visible = artifacts.slice(0, limit);
  return (
    <div className="space-y-2">
      {visible.map((artifact, index) => (
        <div className="flex items-center justify-between gap-3 rounded-md border border-border bg-background px-3 py-2 text-xs" key={`${artifact.relative_path || artifact.path || index}-${index}`}>
          <span className="min-w-0 truncate font-mono text-foreground">{displayArtifactName(artifact, `artifact-${index}`)}</span>
          <span className="shrink-0 text-muted">{artifact.space || artifact.feature_group || artifact.output_type || 'source'}</span>
        </div>
      ))}
      {artifacts.length > limit ? <p className="text-xs text-muted">+{artifacts.length - limit} more artifacts</p> : null}
      {!artifacts.length ? <p className="text-sm text-muted">{emptyLabel}</p> : null}
    </div>
  );
}
