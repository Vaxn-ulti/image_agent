import { FileText } from 'lucide-react';
import { Button } from '../ui/Button';
import { MetricBlock } from '../ui/MetricBlock';
import { PageHeader } from '../ui/PageHeader';
import type { OutputItem, ResultSummary } from '../../lib/types';

type ResultSummaryHeaderProps = {
  artifactCount: number;
  reportFigures: OutputItem[];
  summary: ResultSummary;
};

export function ResultSummaryHeader({ artifactCount, reportFigures, summary }: ResultSummaryHeaderProps) {
  return (
    <div>
      <PageHeader
        actions={
          <Button size="sm" variant="secondary">
            <FileText className="h-4 w-4" />
            Export bundle
          </Button>
        }
        description={`${summary.workflow_type} | contract ${summary.contract_version} | spaces ${summary.spaces.join(', ') || 'unknown'}`}
        eyebrow="Results Studio"
        title="Scientific Results Studio"
      />
      <div className="grid gap-3 md:grid-cols-4">
        <MetricBlock label="Task" value={`#${summary.task_id}`} />
        <MetricBlock label="Modality" tone="accent" value={summary.modality} />
        <MetricBlock label="Report figures" tone={reportFigures.length ? 'success' : 'muted'} value={reportFigures.length} />
        <MetricBlock label="Artifacts" value={artifactCount} />
      </div>
    </div>
  );
}
