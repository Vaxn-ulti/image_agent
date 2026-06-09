import { ExternalLink } from 'lucide-react';
import { artifactUrl } from '../../lib/resultArtifacts';
import type { OutputItem } from '../../lib/types';
import { DataTable, TableCell, TableHead, TableHeaderCell, TableRow } from '../ui/DataTable';
import { Panel, PanelBody, PanelHeader, PanelTitle } from '../ui/Panel';

type ArtifactTableProps = {
  apiBase: string;
  artifacts: OutputItem[];
  taskId: number;
  title?: string;
};

export function ArtifactTable({ apiBase, artifacts, taskId, title = 'Artifacts' }: ArtifactTableProps) {
  return (
    <Panel>
      <PanelHeader>
        <PanelTitle>{title}</PanelTitle>
        <span className="text-xs font-semibold text-muted">{artifacts.length} files</span>
      </PanelHeader>
      <PanelBody>
        <DataTable empty="No artifacts registered." isEmpty={!artifacts.length}>
          <TableHead>
            <tr>
              <TableHeaderCell>Path</TableHeaderCell>
              <TableHeaderCell>Group</TableHeaderCell>
              <TableHeaderCell>Space</TableHeaderCell>
              <TableHeaderCell>Type</TableHeaderCell>
              <TableHeaderCell>Size</TableHeaderCell>
              <TableHeaderCell>Open</TableHeaderCell>
            </tr>
          </TableHead>
          <tbody>
            {artifacts.map((artifact, index) => {
              const relativePath = artifact.relative_path || artifact.path || `artifact-${index}`;
              const url = artifactUrl(taskId, artifact, apiBase);
              return (
                <TableRow key={`${relativePath}-${index}`}>
                  <TableCell mono>{relativePath}</TableCell>
                  <TableCell>{artifact.feature_group || '-'}</TableCell>
                  <TableCell>{artifact.space || '-'}</TableCell>
                  <TableCell>{artifact.content_type || artifact.output_type || '-'}</TableCell>
                  <TableCell>{artifact.size_bytes ? `${artifact.size_bytes} B` : '-'}</TableCell>
                  <TableCell>
                    <a className="inline-flex items-center gap-1 font-semibold text-accent hover:underline" href={url} rel="noreferrer" target="_blank">
                      Open <ExternalLink className="h-3.5 w-3.5" />
                    </a>
                  </TableCell>
                </TableRow>
              );
            })}
          </tbody>
        </DataTable>
      </PanelBody>
    </Panel>
  );
}
