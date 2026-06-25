import { AlertTriangle } from 'lucide-react';
import { flattenOutputs, getReportArtifacts, groupArtifactsByFeature, isPreviewableFigure } from '../../lib/resultArtifacts';
import type { ArtifactManifest, OutputItem, ResultSummary } from '../../lib/types';
import { ArtifactTable } from './ArtifactTable';
import { BoldResultView } from './BoldResultView';
import { DwiResultView } from './DwiResultView';
import { ProvenancePanel } from './ProvenancePanel';
import { ReportFigureGallery } from './ReportFigureGallery';
import { ResultSummaryHeader } from './ResultSummaryHeader';
import { T1ResultView } from './T1ResultView';

type ResultStudioLayoutProps = {
  apiBase: string;
  artifactManifest?: ArtifactManifest;
  exportError?: string;
  exportReadyDownload?: { filename: string; url: string } | null;
  exporting?: boolean;
  onExportBundle?: () => void;
  summary: ResultSummary;
  workflowDisplayName?: string;
};

function isReportArtifact(artifact: OutputItem) {
  const featureGroup = (artifact.feature_group || '').toLowerCase();
  const outputType = (artifact.output_type || '').toLowerCase();
  const role = (artifact.artifact_role || '').toLowerCase();
  const contentType = (artifact.content_type || '').toLowerCase();
  return (
    featureGroup.includes('report') ||
    featureGroup.includes('qc') ||
    outputType.includes('report') ||
    role.includes('report') ||
    artifact.preview_kind === 'html' ||
    artifact.preview_kind === 'image' ||
    contentType === 'text/html' ||
    contentType.startsWith('image/')
  );
}

export function ResultStudioLayout({
  apiBase,
  artifactManifest,
  exportError,
  exportReadyDownload,
  exporting,
  onExportBundle,
  summary,
  workflowDisplayName,
}: ResultStudioLayoutProps) {
  const manifestArtifacts = artifactManifest?.artifacts || [];
  const usesManifest = manifestArtifacts.length > 0;
  const allArtifacts = usesManifest ? manifestArtifacts : flattenOutputs(summary.outputs);
  const reportArtifacts = usesManifest ? allArtifacts.filter(isReportArtifact) : getReportArtifacts(summary.outputs);
  const artifacts = usesManifest ? allArtifacts.filter((artifact) => !isReportArtifact(artifact)) : flattenOutputs(summary.outputs, new Set(['reports', 'figures']));
  const reportFigures = reportArtifacts.filter(isPreviewableFigure);
  const artifactGroups = groupArtifactsByFeature(allArtifacts);
  const modality = summary.modality.toUpperCase();
  const hasContainerNativeQc = allArtifacts.some(
    (artifact) => artifact.container_native_qc === true || artifact.artifact_category === 'container_native_qc',
  );
  const hasDerivedReportArtifacts = allArtifacts.some(
    (artifact) => artifact.derived_scientific_report === true || artifact.artifact_category === 'derived_scientific_report',
  );
  const showNativeQcBoundary = usesManifest && hasDerivedReportArtifacts && !hasContainerNativeQc;

  return (
    <div className="max-w-7xl mx-auto space-y-8 animate-in fade-in duration-500">
      <ResultSummaryHeader
        artifactCount={artifacts.length + reportArtifacts.length}
        exportError={exportError}
        exportReadyDownload={exportReadyDownload}
        exporting={exporting}
        onExportBundle={onExportBundle}
        reportFigures={reportFigures}
        summary={summary}
        workflowDisplayName={workflowDisplayName}
      />

      <div className="grid gap-8 xl:grid-cols-[1fr_320px]">
        <div className="space-y-8 min-w-0">
          {/* Scientific Visualization Area */}
          <div className="space-y-6">
            <ReportFigureGallery apiBase={apiBase} figures={reportFigures} taskId={summary.task_id} />
            {showNativeQcBoundary ? (
              <div className="rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-950">
                <div className="flex items-start gap-3">
                  <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-amber-700" />
                  <div className="min-w-0">
                    <div className="font-semibold">No container-native QC artifacts registered</div>
                    <p className="mt-1 text-xs leading-5 text-amber-900">
                      Derived report files are available, but they do not replace native container QC evidence.
                    </p>
                  </div>
                </div>
              </div>
            ) : null}

            <div className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden p-6">
              {modality === 'T1' ? <T1ResultView artifactsByFeature={artifactGroups} summary={summary} /> : null}
              {modality === 'BOLD' ? <BoldResultView apiBase={apiBase} artifactsByFeature={artifactGroups} reportFigures={reportFigures} summary={summary} /> : null}
              {modality === 'DWI' ? <DwiResultView apiBase={apiBase} artifactsByFeature={artifactGroups} reportFigures={reportFigures} summary={summary} /> : null}
            </div>
          </div>

          {/* Artifact Manifest Tables */}
          <div className="space-y-6">
             <div className="flex items-center gap-2 px-2">
                <div className="w-1.5 h-6 bg-[#065F46] rounded-full"></div>
                <h2 className="text-lg font-bold text-gray-900">Artifact Manifest</h2>
             </div>

             <div className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden">
                <ArtifactTable apiBase={apiBase} artifacts={artifacts} taskId={summary.task_id} />
             </div>

             <div className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden">
                <ArtifactTable apiBase={apiBase} artifacts={reportArtifacts} taskId={summary.task_id} title="Report files" />
             </div>
          </div>
        </div>

        {/* Sidebar Context */}
        <aside className="space-y-6">
          <div className="sticky top-8">
             <div className="text-[10px] font-bold text-gray-400 uppercase tracking-wider mb-4 px-1">Execution Metadata</div>
             <div className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden">
                <ProvenancePanel provenance={summary.provenance} />
             </div>

             <div className="mt-6 p-5 bg-[#065F46]/5 rounded-xl border border-[#065F46]/10">
                <h4 className="text-xs font-bold text-gray-900 mb-2">Scientific Integrity</h4>
                <p className="text-[11px] text-gray-500 leading-relaxed">
                  All outputs in this studio are generated using containerized OCI images.
                  The provenance hash ensures that the results are reproducible across any
                  compatible infrastructure.
                </p>
             </div>
          </div>
        </aside>
      </div>
    </div>
  );
}
