import type { OutputItem, ResultSummary } from '../../lib/types';
import { displayArtifactName } from '../../lib/resultArtifacts';
import { AuthenticatedArtifactImageLink, AuthenticatedArtifactOpenButton } from './AuthenticatedArtifact';
import { MetricAvailabilityGrid } from './MetricAvailabilityGrid';
import { ScientificChartPanel } from './ScientificChartPanel';
import { SourceArtifactList } from './SourceArtifactList';

type BoldResultViewProps = {
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

function BoldReportFigure({ apiBase, figure, taskId }: { apiBase: string; figure?: OutputItem; taskId: number }) {
  void apiBase;
  if (!figure) {
    return <div className="rounded-md border border-dashed border-border bg-panel p-4 text-sm text-muted">BOLD report figure is not registered for this panel.</div>;
  }

  const name = displayArtifactName(figure);
  const relativePath = figure.relative_path || figure.path || name;
  const originLabel = figure.native_artifact === false ? 'Derived BOLD report figure' : 'Native BOLD QC figure';

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

export function BoldResultView({ apiBase, artifactsByFeature, reportFigures, summary }: BoldResultViewProps) {
  const taskId = summary.task_id;
  const voxelwiseFigure = findFigure(reportFigures, ['voxelwise']);
  const connectivityFigure = findFigure(reportFigures, ['seed', 'connectivity']);
  const qcFigure = findFigure(reportFigures, ['qc']);
  const psdFigure = findFigure(reportFigures, ['psd']);

  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <ScientificChartPanel empty={!artifactsByFeature.voxelwise_metrics?.length} metric="ALFF / fALFF / ReHo / tSNR / RSFA" source="maps and reports" title="BOLD voxelwise metrics">
        <div className="space-y-3">
          <BoldReportFigure apiBase={apiBase} figure={voxelwiseFigure} taskId={taskId} />
          <MetricAvailabilityGrid artifacts={artifactsByFeature.voxelwise_metrics || []} metrics={['ALFF', 'fALFF', 'ReHo', 'tSNR', 'RSFA']} spaces={['mni152']} />
          <SourceArtifactList artifacts={artifactsByFeature.voxelwise_metrics || []} limit={3} />
        </div>
      </ScientificChartPanel>
      <ScientificChartPanel empty={!artifactsByFeature.connectivity?.length} metric="Seed-to-ROI and DMN" source="tables/seed_to_roi.tsv" title="Seed connectivity">
        <div className="space-y-3">
          <BoldReportFigure apiBase={apiBase} figure={connectivityFigure} taskId={taskId} />
          <SourceArtifactList artifacts={artifactsByFeature.connectivity || []} limit={3} />
        </div>
      </ScientificChartPanel>
      <ScientificChartPanel empty={!artifactsByFeature.qc_timeseries?.length && !artifactsByFeature.motion_confounds?.length} metric="FD / DVARS / wholebrain" source="QC tables and reports" title="QC time-series">
        <div className="space-y-3">
          <BoldReportFigure apiBase={apiBase} figure={qcFigure} taskId={taskId} />
          <SourceArtifactList artifacts={[...(artifactsByFeature.qc_timeseries || []), ...(artifactsByFeature.motion_confounds || [])]} limit={3} />
        </div>
      </ScientificChartPanel>
      <ScientificChartPanel empty={!psdFigure} metric="Power spectrum" source="bold_mean_psd.png" title="Mean PSD">
        <BoldReportFigure apiBase={apiBase} figure={psdFigure} taskId={taskId} />
      </ScientificChartPanel>
    </div>
  );
}
