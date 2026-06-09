import { flattenOutputs, getReportArtifacts, groupArtifactsByFeature, isPreviewableFigure } from '../../lib/resultArtifacts';
import type { ResultSummary } from '../../lib/types';
import { ArtifactTable } from './ArtifactTable';
import { BoldResultView } from './BoldResultView';
import { DwiResultView } from './DwiResultView';
import { ProvenancePanel } from './ProvenancePanel';
import { ReportFigureGallery } from './ReportFigureGallery';
import { ResultSummaryHeader } from './ResultSummaryHeader';
import { T1ResultView } from './T1ResultView';

type ResultStudioLayoutProps = {
  apiBase: string;
  summary: ResultSummary;
};

export function ResultStudioLayout({ apiBase, summary }: ResultStudioLayoutProps) {
  const artifacts = flattenOutputs(summary.outputs, new Set(['reports', 'figures']));
  const reportArtifacts = getReportArtifacts(summary.outputs);
  const reportFigures = reportArtifacts.filter(isPreviewableFigure);
  const artifactGroups = groupArtifactsByFeature(flattenOutputs(summary.outputs));
  const modality = summary.modality.toUpperCase();

  return (
    <div className="space-y-4">
      <ResultSummaryHeader artifactCount={artifacts.length + reportArtifacts.length} reportFigures={reportFigures} summary={summary} />
      <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_340px]">
        <div className="space-y-4">
          <ReportFigureGallery apiBase={apiBase} figures={reportFigures} taskId={summary.task_id} />
          {modality === 'T1' ? <T1ResultView artifactsByFeature={artifactGroups} summary={summary} /> : null}
          {modality === 'BOLD' ? <BoldResultView apiBase={apiBase} artifactsByFeature={artifactGroups} reportFigures={reportFigures} summary={summary} /> : null}
          {modality === 'DWI' ? <DwiResultView apiBase={apiBase} artifactsByFeature={artifactGroups} reportFigures={reportFigures} summary={summary} /> : null}
          <ArtifactTable apiBase={apiBase} artifacts={artifacts} taskId={summary.task_id} />
          <ArtifactTable apiBase={apiBase} artifacts={reportArtifacts} taskId={summary.task_id} title="Report files" />
        </div>
        <aside className="space-y-4">
          <ProvenancePanel provenance={summary.provenance} />
        </aside>
      </div>
    </div>
  );
}
