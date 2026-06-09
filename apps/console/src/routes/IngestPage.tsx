import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { UploadCloud } from 'lucide-react';
import { useState } from 'react';
import { useParams } from 'react-router-dom';
import { Button } from '../components/ui/Button';
import { DataTable, TableCell, TableHead, TableHeaderCell, TableRow } from '../components/ui/DataTable';
import { PageHeader } from '../components/ui/PageHeader';
import { Panel, PanelBody, PanelHeader, PanelTitle } from '../components/ui/Panel';
import { api } from '../lib/api';
import { queryKeys } from '../lib/query';
import type { DwiUploadFiles, Inventory } from '../lib/types';

export function IngestPage() {
  const projectId = Number(useParams().projectId);
  const queryClient = useQueryClient();
  const [error, setError] = useState('');
  const [inventory, setInventory] = useState<Inventory | null>(null);
  const [dwiFiles, setDwiFiles] = useState<Partial<DwiUploadFiles>>({});
  const { data: series = [] } = useQuery({ enabled: Boolean(projectId), queryFn: () => api.listSeries(projectId), queryKey: queryKeys.series(projectId) });

  const refreshSeries = () => queryClient.invalidateQueries({ queryKey: queryKeys.series(projectId) });
  const uploadNifti = useMutation({ mutationFn: (file: File) => api.uploadNifti(projectId, file), onSuccess: refreshSeries });
  const uploadDicom = useMutation({ mutationFn: (file: File) => api.uploadDicom(projectId, file), onSuccess: refreshSeries });
  const uploadDwi = useMutation({
    mutationFn: ({ files, projectId: id }: { files: DwiUploadFiles; projectId: number }) => api.uploadDwi(id, files),
    onSuccess: refreshSeries,
  });

  async function uploadMixed(file: File) {
    setError('');
    try {
      const session = await api.createUploadSession(projectId, { label: file.name, source_type: 'folder_or_archive' });
      const response = await api.ingestDataset(projectId, session.id, file, true);
      setInventory(response.inventory || null);
      refreshSeries();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Mixed dataset ingest failed');
    }
  }

  function handleDwiUpload() {
    setError('');
    if (!dwiFiles.nifti || !dwiFiles.bval || !dwiFiles.bvec || !dwiFiles.jsonSidecar) {
      setError('DWI NIfTI, bval, bvec, and JSON sidecar are required for fast GPU DTI.');
      return;
    }
    uploadDwi.mutate({ files: dwiFiles as DwiUploadFiles, projectId });
  }

  return (
    <div className="space-y-4">
      <PageHeader
        description="Upload imaging data and verify detected series before running workflows."
        eyebrow="Data & QC"
        title="Data & QC"
      />
      {error ? <div className="rounded-md border border-danger/30 bg-danger/10 p-3 text-sm text-danger">{error}</div> : null}
      <div className="grid gap-4 lg:grid-cols-2">
        <Panel>
          <PanelHeader>
            <PanelTitle>NIfTI upload</PanelTitle>
            <UploadCloud className="h-4 w-4 text-muted" />
          </PanelHeader>
          <PanelBody>
            <input aria-label="Upload T1 or BOLD NIfTI" accept=".nii,.gz" type="file" onChange={(event) => event.target.files?.[0] && uploadNifti.mutate(event.target.files[0])} />
          </PanelBody>
        </Panel>
        <Panel>
          <PanelHeader>
            <PanelTitle>DICOM zip</PanelTitle>
            <UploadCloud className="h-4 w-4 text-muted" />
          </PanelHeader>
          <PanelBody>
            <input aria-label="Upload DICOM zip" accept=".zip" type="file" onChange={(event) => event.target.files?.[0] && uploadDicom.mutate(event.target.files[0])} />
          </PanelBody>
        </Panel>
        <Panel>
          <PanelHeader>
            <PanelTitle>Mixed dataset zip</PanelTitle>
            <UploadCloud className="h-4 w-4 text-muted" />
          </PanelHeader>
          <PanelBody>
            <input aria-label="Upload mixed dataset zip" accept=".zip" type="file" onChange={(event) => event.target.files?.[0] && uploadMixed(event.target.files[0])} />
          </PanelBody>
        </Panel>
        <Panel>
          <PanelHeader>
            <PanelTitle>DWI set</PanelTitle>
            <UploadCloud className="h-4 w-4 text-muted" />
          </PanelHeader>
          <PanelBody className="grid gap-3 text-sm">
            <label>
              DWI NIfTI
              <input className="mt-1 block" accept=".nii,.gz" type="file" onChange={(event) => setDwiFiles((prev) => ({ ...prev, nifti: event.target.files?.[0] }))} />
            </label>
            <label>
              bval
              <input className="mt-1 block" accept=".bval" type="file" onChange={(event) => setDwiFiles((prev) => ({ ...prev, bval: event.target.files?.[0] }))} />
            </label>
            <label>
              bvec
              <input className="mt-1 block" accept=".bvec" type="file" onChange={(event) => setDwiFiles((prev) => ({ ...prev, bvec: event.target.files?.[0] }))} />
            </label>
            <label>
              JSON sidecar
              <input className="mt-1 block" accept=".json" type="file" onChange={(event) => setDwiFiles((prev) => ({ ...prev, jsonSidecar: event.target.files?.[0] }))} />
            </label>
            <Button onClick={handleDwiUpload} type="button" variant="primary">
              Upload DWI set
            </Button>
          </PanelBody>
        </Panel>
      </div>
      {inventory ? (
        <Panel>
          <PanelHeader>
            <PanelTitle>Dataset inventory</PanelTitle>
          </PanelHeader>
          <PanelBody className="grid gap-2 text-sm md:grid-cols-4">
            <div>Total files: {inventory.total_files ?? 0}</div>
            <div>DICOM: {inventory.dicom?.found_files ?? 0}</div>
            <div>Conversion: {inventory.dicom?.conversion_status || 'not_applicable'}</div>
            <div>BIDS root: {inventory.bids_dataset_root || '-'}</div>
          </PanelBody>
        </Panel>
      ) : null}
      <Panel>
        <PanelHeader>
          <PanelTitle>Detected series</PanelTitle>
        </PanelHeader>
        <PanelBody>
          <DataTable empty="No detected series yet." isEmpty={!series.length}>
            <TableHead>
              <tr>
                <TableHeaderCell>ID</TableHeaderCell>
                <TableHeaderCell>Sequence</TableHeaderCell>
                <TableHeaderCell>Modality</TableHeaderCell>
                <TableHeaderCell>Format</TableHeaderCell>
                <TableHeaderCell>Confidence</TableHeaderCell>
                <TableHeaderCell>Metadata</TableHeaderCell>
              </tr>
            </TableHead>
            <tbody>
              {series.map((item) => (
                <TableRow key={item.id}>
                  <TableCell>#{item.id}</TableCell>
                  <TableCell>{item.sequence_label || '-'}</TableCell>
                  <TableCell>{item.modality}</TableCell>
                  <TableCell>{item.format}</TableCell>
                  <TableCell>{Number(item.confidence).toFixed(2)}</TableCell>
                  <TableCell>{JSON.stringify(item.metadata || {})}</TableCell>
                </TableRow>
              ))}
            </tbody>
          </DataTable>
        </PanelBody>
      </Panel>
    </div>
  );
}
