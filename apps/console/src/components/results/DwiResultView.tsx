import type { OutputItem, ResultSummary } from '../../lib/types';
import { displayArtifactName } from '../../lib/resultArtifacts';
import { AuthenticatedArtifactImageLink, AuthenticatedArtifactOpenButton } from './AuthenticatedArtifact';
import { MetricAvailabilityGrid } from './MetricAvailabilityGrid';
import { ScientificChartPanel } from './ScientificChartPanel';
import { SourceArtifactList } from './SourceArtifactList';

type DwiResultViewProps = {
  apiBase: string;
  artifactsByFeature: Record<string, OutputItem[]>;
  reportFigures: OutputItem[];
  summary: ResultSummary;
};

function findFigure(figures: OutputItem[], tokens: string[]) {
  return figures.find((figure) => {
    const path = `${figure.relative_path || ''} ${figure.path || ''}`.toLowerCase();
    return tokens.every((token) => path.includes(token));
  });
}

function DwiReportFigure({ apiBase, figure, taskId }: { apiBase: string; figure?: OutputItem; taskId: number }) {
  void apiBase;
  if (!figure) {
    return <div className="rounded-md border border-dashed border-border bg-panel p-4 text-sm text-muted">DWI report figure is not registered for this panel.</div>;
  }

  const name = displayArtifactName(figure);
  const relativePath = figure.relative_path || figure.path || name;
  const originLabel = figure.native_artifact === false ? 'Derived DWI report figure' : 'Native DWI report figure';

  return (
    <figure className="overflow-hidden rounded-md border border-border bg-background">
      <AuthenticatedArtifactImageLink alt={`${originLabel}: ${name}`} className="h-52 w-full bg-white object-contain p-3" relativePath={relativePath} taskId={taskId} />
      <figcaption className="flex items-center justify-between gap-3 border-t border-border px-3 py-2 text-xs">
        <span className="min-w-0 truncate font-mono text-muted">{relativePath}</span>
        <AuthenticatedArtifactOpenButton className="inline-flex shrink-0 items-center gap-1 font-semibold text-accent hover:underline" relativePath={relativePath} taskId={taskId} />
      </figcaption>
    </figure>
  );
}

export function DwiResultView({ apiBase, artifactsByFeature, reportFigures, summary }: DwiResultViewProps) {
  const mapArtifacts = [...(artifactsByFeature.native_dti_maps || []), ...(artifactsByFeature.mni152_dti_maps || [])];
  const nativeCount = artifactsByFeature.native_dti_maps?.length || 0;
  const mniCount = artifactsByFeature.mni152_dti_maps?.length || 0;
  const tensorFigure = findFigure(reportFigures, ['dwi', 'tensor']);
  const atlasFigure = findFigure(reportFigures, ['dwi', 'atlas']);

  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <ScientificChartPanel empty={!nativeCount && !mniCount} metric="FA / MD / AD / RD" source="native and MNI152 maps" title="DWI tensor map matrix">
        <div className="space-y-3">
          <DwiReportFigure apiBase={apiBase} figure={tensorFigure} taskId={summary.task_id} />
          <MetricAvailabilityGrid artifacts={mapArtifacts} metrics={['FA', 'MD', 'AD', 'RD']} spaces={['native', 'mni152']} />
          <div className="grid gap-2 text-sm text-muted md:grid-cols-2">
            <div className="rounded-md border border-border bg-background p-3">Native maps: {nativeCount}</div>
            <div className="rounded-md border border-border bg-background p-3">MNI152 maps: {mniCount}</div>
          </div>
        </div>
      </ScientificChartPanel>
      <ScientificChartPanel empty={!artifactsByFeature.regional_dti?.length} metric="Atlas regional DTI" source="combined_region_dti.tsv" title="Atlas regional distribution">
        <div className="space-y-3">
          <DwiReportFigure apiBase={apiBase} figure={atlasFigure} taskId={summary.task_id} />
          <SourceArtifactList artifacts={artifactsByFeature.regional_dti || []} />
        </div>
      </ScientificChartPanel>
      <ScientificChartPanel metric="Runtime and registration" source="provenance" title="Runtime / registration">
        <div className="grid gap-2 text-sm">
          <div className="flex items-center justify-between rounded-md border border-border bg-background px-3 py-2">
            <span className="text-muted">Runtime</span>
            <span className="font-mono font-semibold">{String(summary.provenance.runtime_sec || 'unknown')} s</span>
          </div>
          <div className="flex items-center justify-between rounded-md border border-border bg-background px-3 py-2">
            <span className="text-muted">Max runtime</span>
            <span className="font-mono font-semibold">{String(summary.provenance.max_runtime_sec || 'unknown')} s</span>
          </div>
          <div className="flex items-center justify-between rounded-md border border-border bg-background px-3 py-2">
            <span className="text-muted">Registration</span>
            <span className="font-mono font-semibold">{String(summary.provenance.mni_registration_method || 'not reported')}</span>
          </div>
        </div>
      </ScientificChartPanel>
      <ScientificChartPanel metric="Metric sanitization" source="provenance" title="Sanitization disclosure">
        <SourceArtifactList artifacts={mapArtifacts} emptyLabel="No tensor map artifacts were registered for sanitization review." />
      </ScientificChartPanel>
    </div>
  );
}
