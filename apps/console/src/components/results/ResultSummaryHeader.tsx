import { FileText, Layers, Share2, Zap } from 'lucide-react';
import { Button } from '../ui/Button';
import { PageHeader } from '../ui/PageHeader';
import type { OutputItem, ResultSummary } from '../../lib/types';

type ResultSummaryHeaderProps = {
  artifactCount: number;
  exportError?: string;
  exportReadyDownload?: { filename: string; url: string } | null;
  exporting?: boolean;
  onExportBundle?: () => void;
  reportFigures: OutputItem[];
  summary: ResultSummary;
  workflowDisplayName?: string;
};

export function ResultSummaryHeader({
  artifactCount,
  exportError,
  exportReadyDownload,
  exporting = false,
  onExportBundle,
  reportFigures,
  summary,
  workflowDisplayName,
}: ResultSummaryHeaderProps) {
  const displayName = workflowDisplayName || summary.workflow_type;
  return (
    <div className="space-y-6">
      <PageHeader
        actions={
          <div className="flex items-center gap-2">
            <Button size="sm" variant="secondary" className="bg-white border-gray-200 text-gray-700 hover:bg-gray-50">
              <Share2 className="h-3.5 w-3.5 mr-2" />
              Share Result
            </Button>
            <Button
              size="sm"
              variant="primary"
              className="bg-[#065F46] hover:bg-[#044E3A]"
              disabled={exporting}
              onClick={onExportBundle}
            >
              <FileText className="h-3.5 w-3.5 mr-2" />
              {exporting ? 'Exporting...' : 'Export bundle'}
            </Button>
          </div>
        }
        description={`${displayName} workflow execution successfully archived with full provenance and metadata tagging.`}
        eyebrow="Scientific Review"
        title="Scientific Results Studio"
      />

      <div className="text-[10px] font-medium uppercase tracking-normal text-gray-400">
        Stable workflow ID: {summary.workflow_type}
      </div>

      {exporting ? (
        <div role="status" className="rounded-md border border-emerald-100 bg-emerald-50 px-3 py-2 text-xs font-medium text-emerald-800">
          Preparing export bundle...
        </div>
      ) : null}
      {exportError ? (
        <div role="alert" className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-xs font-medium text-red-700">
          Export failed: {exportError}
        </div>
      ) : null}
      {exportReadyDownload && !exporting ? (
        <a
          className="inline-flex h-8 items-center justify-center rounded-md border border-[#065F46] bg-white px-3 text-xs font-semibold text-[#065F46] hover:bg-[#ECFDF5]"
          download={exportReadyDownload.filename}
          href={exportReadyDownload.url}
        >
          Save export bundle
        </a>
      ) : null}

      <div className="grid gap-4 grid-cols-2 md:grid-cols-4">
        <ResultMetric
          icon={<Zap className="w-4 h-4" />}
          label="Execution ID"
          value={`RUN-${summary.task_id}`}
        />
        <ResultMetric
          icon={<Layers className="w-4 h-4" />}
          label="Modality"
          value={summary.modality}
          highlight
        />
        <ResultMetric
          icon={<FileText className="w-4 h-4" />}
          label="Report Figures"
          value={reportFigures.length}
          subValue="QC assets"
        />
        <ResultMetric
          icon={<Share2 className="w-4 h-4" />}
          label="Total Artifacts"
          value={artifactCount}
          subValue="Files registered"
        />
      </div>
    </div>
  );
}

function ResultMetric({ icon, label, value, subValue, highlight }: { icon: React.ReactNode; label: string; value: string | number; subValue?: string; highlight?: boolean }) {
  return (
    <div className="bg-white p-4 rounded-xl border border-gray-200 shadow-sm flex items-start gap-3 transition-all hover:shadow-md">
      <div className={`p-2 rounded-lg ${highlight ? 'bg-[#ECFDF5] text-[#065F46]' : 'bg-gray-50 text-gray-400'} shrink-0`}>
        {icon}
      </div>
      <div className="min-w-0">
        <div className="text-[10px] font-bold text-gray-400 uppercase tracking-wider mb-0.5">{label}</div>
        <div className={`text-lg font-bold truncate ${highlight ? 'text-[#065F46]' : 'text-gray-900'}`}>{value}</div>
        {subValue && <div className="text-[10px] text-gray-400 font-medium">{subValue}</div>}
      </div>
    </div>
  );
}
