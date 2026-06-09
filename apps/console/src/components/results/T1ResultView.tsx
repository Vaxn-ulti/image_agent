import type { OutputItem, ResultSummary } from '../../lib/types';
import { ScientificChartPanel } from './ScientificChartPanel';
import { SourceArtifactList } from './SourceArtifactList';

export function T1ResultView({ artifactsByFeature }: { artifactsByFeature: Record<string, OutputItem[]>; summary: ResultSummary }) {
  return (
    <div className="grid gap-4 lg:grid-cols-3">
      <ScientificChartPanel empty={!artifactsByFeature.brain_measures?.length} metric="Volumes and measures" source="tables/t1_brain_measures.tsv" title="T1 brain measures">
        <div className="space-y-3">
          <div className="grid gap-2">
            {['Intracranial volume', 'Gray matter', 'White matter'].map((label, index) => (
              <div className="rounded-md border border-border bg-background p-3" key={label}>
                <div className="mb-2 flex items-center justify-between text-xs">
                  <span className="font-semibold text-foreground">{label}</span>
                  <span className="text-muted">table source</span>
                </div>
                <div className="h-2 rounded-full bg-border">
                  <div className="h-2 rounded-full bg-accent" style={{ width: `${82 - index * 14}%` }} />
                </div>
              </div>
            ))}
          </div>
          <SourceArtifactList artifacts={artifactsByFeature.brain_measures || []} limit={2} />
        </div>
      </ScientificChartPanel>
      <ScientificChartPanel empty={!artifactsByFeature.regional_morphometry?.length} metric="Cortical thickness and regional morphometry" source="tables/t1_t1w_regions.tsv" title="Regional morphometry">
        <div className="space-y-3">
          <div className="grid grid-cols-[1fr_auto_1fr] items-center gap-2 text-xs">
            {['Frontal', 'Temporal', 'Parietal'].map((region, index) => (
              <div className="contents" key={region}>
                <div className="h-2 rounded-full bg-accent/60" style={{ width: `${76 - index * 11}%` }} />
                <div className="rounded-full border border-border bg-paper px-2 py-1 text-center font-semibold text-foreground">
                  {region}
                </div>
                <div className="h-2 rounded-full bg-success/70" style={{ width: `${70 - index * 9}%` }} />
              </div>
            ))}
          </div>
          <SourceArtifactList artifacts={artifactsByFeature.regional_morphometry || []} limit={2} />
        </div>
      </ScientificChartPanel>
      <ScientificChartPanel empty={!artifactsByFeature.freesurfer_stats?.length} metric="Stats inventory" source="freesurfer stats" title="FreeSurfer inventory">
        <SourceArtifactList artifacts={artifactsByFeature.freesurfer_stats || []} />
      </ScientificChartPanel>
    </div>
  );
}
