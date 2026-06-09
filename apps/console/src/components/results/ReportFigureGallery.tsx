import { ExternalLink } from 'lucide-react';
import { artifactUrl, displayArtifactName } from '../../lib/resultArtifacts';
import type { OutputItem } from '../../lib/types';
import { Panel, PanelBody, PanelHeader, PanelTitle } from '../ui/Panel';

type ReportFigureGalleryProps = {
  apiBase: string;
  figures: OutputItem[];
  taskId: number;
};

export function ReportFigureGallery({ apiBase, figures, taskId }: ReportFigureGalleryProps) {
  return (
    <Panel>
      <PanelHeader>
        <PanelTitle>Scientific report figures</PanelTitle>
        <span className="text-xs font-semibold text-muted">{figures.length} figures</span>
      </PanelHeader>
      <PanelBody>
        {figures.length ? (
          <div className="grid gap-4 xl:grid-cols-2">
            {figures.map((figure, index) => {
              const relativePath = figure.relative_path || figure.path || `report-figure-${index}`;
              const url = artifactUrl(taskId, figure, apiBase);
              return (
                <figure className="overflow-hidden rounded-lg border border-border bg-paper" key={`${relativePath}-${index}`}>
                  <div className="flex items-center justify-between gap-3 border-b border-border px-3 py-2">
                    <figcaption className="min-w-0 truncate font-mono text-xs font-semibold text-foreground">
                      {displayArtifactName(figure, `figure-${index}`)}
                    </figcaption>
                    <a className="inline-flex shrink-0 items-center gap-1 text-xs font-semibold text-accent hover:underline" href={url} rel="noreferrer" target="_blank">
                      Open <ExternalLink className="h-3 w-3" />
                    </a>
                  </div>
                  <a className="block" href={url} rel="noreferrer" target="_blank">
                    <img alt={`Scientific figure ${relativePath}`} className="h-72 w-full bg-white object-contain p-3" loading="lazy" src={url} />
                  </a>
                  <div className="border-t border-border px-3 py-2 text-xs leading-5 text-muted">
                    Source: <span className="font-mono">{relativePath}</span>
                    {figure.space || figure.feature_group ? <span> | {figure.space || figure.feature_group}</span> : null}
                  </div>
                </figure>
              );
            })}
          </div>
        ) : (
          <div className="rounded-md border border-dashed border-border bg-panel p-4 text-sm text-muted">No previewable report figures are registered for this task.</div>
        )}
      </PanelBody>
    </Panel>
  );
}
