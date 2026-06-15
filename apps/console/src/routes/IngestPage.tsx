import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  AlertCircle,
  CheckCircle2,
  Database,
  FileSearch,
  Info,
  Layers,
  Loader2,
  RefreshCw,
  UploadCloud,
} from 'lucide-react';
import { useState } from 'react';
import { useParams } from 'react-router-dom';
import { Button } from '../components/ui/Button';
import { DataTable, TableCell, TableHead, TableHeaderCell, TableRow } from '../components/ui/DataTable';
import { PageHeader } from '../components/ui/PageHeader';
import { api } from '../lib/api';
import { queryKeys } from '../lib/query';
import type { DwiUploadFiles, Inventory } from '../lib/types';

export function IngestPage() {
  const projectId = Number(useParams().projectId);
  const queryClient = useQueryClient();
  const [error, setError] = useState('');
  const [activeSessionId, setActiveSessionId] = useState<number | null>(null);
  const [dwiFiles, setDwiFiles] = useState<Partial<DwiUploadFiles>>({});

  const { data: series = [] } = useQuery({
    enabled: Boolean(projectId),
    queryFn: () => api.listSeries(projectId),
    queryKey: queryKeys.series(projectId),
  });

  // Polling for inventory status if a session is active
  const { data: inventoryData } = useQuery({
    enabled: Boolean(projectId && activeSessionId),
    queryFn: () => api.getInventory(projectId, activeSessionId!),
    queryKey: ['inventory', projectId, activeSessionId],
    refetchInterval: (query) => {
      const status = query.state.data?.inventory?.inventory_status;
      return status === 'running' || status === 'queued' ? 2000 : false;
    },
  });

  const inventory = inventoryData?.inventory;

  const refreshData = () => {
    queryClient.invalidateQueries({ queryKey: queryKeys.series(projectId) });
    if (activeSessionId) {
      queryClient.invalidateQueries({ queryKey: ['inventory', projectId, activeSessionId] });
    }
  };

  const uploadNifti = useMutation({
    mutationFn: (file: File) => api.uploadNifti(projectId, file),
    onSuccess: refreshData,
    onError: (err) => setError(err instanceof Error ? err.message : 'NIfTI upload failed'),
  });

  const uploadDicom = useMutation({
    mutationFn: (file: File) => api.uploadDicom(projectId, file),
    onSuccess: refreshData,
    onError: (err) => setError(err instanceof Error ? err.message : 'DICOM upload failed'),
  });

  const uploadDwi = useMutation({
    mutationFn: ({ files, projectId: id }: { files: DwiUploadFiles; projectId: number }) => api.uploadDwi(id, files),
    onSuccess: refreshData,
    onError: (err) => setError(err instanceof Error ? err.message : 'DWI upload failed'),
  });

  async function uploadMixed(file: File) {
    setError('');
    setActiveSessionId(null);
    try {
      const session = await api.createUploadSession(projectId, { label: file.name, source_type: 'folder_or_archive' });
      setActiveSessionId(session.id);
      // We set syncFastPath to false to demonstrate async polling
      await api.ingestDataset(projectId, session.id, file, false);
      refreshData();
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

  const isIngesting = inventory?.inventory_status === 'running' || inventory?.inventory_status === 'queued';

  return (
    <div className="max-w-6xl mx-auto space-y-8">
      <PageHeader
        description="Upload imaging data and verify detected series before running workflows."
        eyebrow="Data & QC"
        title="Data & QC"
      />

      {error ? (
        <div className="rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-700 flex items-center gap-3">
          <AlertCircle className="w-5 h-5 shrink-0" />
          {error}
        </div>
      ) : null}

      <div className="grid gap-6 lg:grid-cols-2">
        {/* Single/Archive Upload Paths */}
        <div className="space-y-6">
          <IngestPanel icon={<UploadCloud />} title="Standard Uploads">
            <div className="grid gap-4">
              <UploadSlot
                label="NIfTI upload"
                description="T1 or BOLD (.nii, .nii.gz)"
                accept=".nii,.gz"
                onUpload={(file) => uploadNifti.mutate(file)}
                loading={uploadNifti.isPending}
              />
              <UploadSlot
                label="DICOM zip"
                description="Complete series archive (.zip)"
                accept=".zip"
                onUpload={(file) => uploadDicom.mutate(file)}
                loading={uploadDicom.isPending}
              />
              <UploadSlot
                label="Mixed dataset zip"
                description="Mixed DICOM/NIfTI to BIDS (.zip)"
                accept=".zip"
                onUpload={uploadMixed}
                loading={isIngesting}
              />
            </div>
          </IngestPanel>

          <IngestPanel icon={<Layers />} title="Fast GPU DWI Set">
            <div className="space-y-4 text-sm">
              <p className="text-gray-500 text-xs">
                Provide all four required files for optimized GPU processing.
              </p>
              <div className="grid gap-3">
                <FileInput label="DWI NIfTI (.nii.gz)" accept=".nii,.gz" onChange={(f) => setDwiFiles((p) => ({ ...p, nifti: f }))} />
                <FileInput label="bval file (.bval)" accept=".bval" onChange={(f) => setDwiFiles((p) => ({ ...p, bval: f }))} />
                <FileInput label="bvec file (.bvec)" accept=".bvec" onChange={(f) => setDwiFiles((p) => ({ ...p, bvec: f }))} />
                <FileInput label="JSON sidecar (.json)" accept=".json" onChange={(f) => setDwiFiles((p) => ({ ...p, jsonSidecar: f }))} />
              </div>
              <Button
                onClick={handleDwiUpload}
                disabled={uploadDwi.isPending}
                className="w-full mt-2 bg-[#065F46] hover:bg-[#044E3A]"
                variant="primary"
              >
                {uploadDwi.isPending ? <Loader2 className="w-4 h-4 animate-spin mr-2" /> : <Layers className="w-4 h-4 mr-2" />}
                Upload DWI set
              </Button>
            </div>
          </IngestPanel>
        </div>

        {/* Inventory & Status */}
        <div className="space-y-6">
          <IngestPanel
            icon={<FileSearch />}
            title="Ingest Inventory"
            trailing={isIngesting && <Loader2 className="w-4 h-4 animate-spin text-[#065F46]" />}
          >
            {inventory ? (
              <div className="space-y-6">
                <div className="grid grid-cols-2 gap-4">
                  <StatBox label="Status" value={inventory.inventory_status || 'unknown'} highlight={inventory.inventory_status === 'completed'} />
                  <StatBox label="Total Files" value={inventory.total_files ?? 0} />
                  <StatBox label="DICOM Files" value={inventory.dicom?.found_files ?? 0} />
                  <StatBox label="Conversion" value={inventory.dicom?.conversion_status || '-'} />
                </div>

                {inventory.post_conversion_counts?.by_modality && (
                  <div>
                    <div className="text-[10px] font-bold text-gray-400 uppercase tracking-wider mb-2">Modality Counts</div>
                    <div className="flex flex-wrap gap-2">
                      {Object.entries(inventory.post_conversion_counts.by_modality).map(([mod, count]) => (
                        <div key={mod} className="px-2 py-1 rounded bg-gray-100 text-gray-700 text-xs font-medium border border-gray-200">
                          {mod}: <span className="text-[#065F46]">{count}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {inventory.recognized_unsupported_sequences && inventory.recognized_unsupported_sequences.length > 0 && (
                  <div className="rounded-xl border border-amber-200 bg-amber-50 p-4 space-y-3">
                    <div className="flex items-center gap-2 text-amber-800 font-bold text-sm">
                      <AlertCircle className="w-4 h-4" /> Unsupported Sequences Detected
                    </div>
                    {inventory.recognized_unsupported_sequences.map((seq, idx) => (
                      <div key={idx} className="text-xs text-amber-700 leading-relaxed border-l-2 border-amber-300 pl-3">
                        <div className="font-bold uppercase tracking-tight mb-0.5">{seq.sequence} ({seq.count} files)</div>
                        {seq.message}
                      </div>
                    ))}
                  </div>
                )}

                {inventory.bids_dataset_root && (
                  <div className="p-3 bg-gray-50 rounded-lg border border-gray-100 flex items-center justify-between gap-3 overflow-hidden">
                    <div className="min-w-0">
                      <div className="text-[10px] font-bold text-gray-400 uppercase tracking-wider">BIDS Root Path</div>
                      <div className="text-xs font-mono text-gray-600 truncate">{inventory.bids_dataset_root}</div>
                    </div>
                    <Database className="w-4 h-4 text-gray-300 shrink-0" />
                  </div>
                )}
              </div>
            ) : (
              <div className="py-12 flex flex-col items-center justify-center text-gray-400 text-center space-y-3">
                <FileSearch className="w-12 h-12 opacity-20" />
                <p className="text-sm">No active ingest session.<br/>Upload a dataset to see inventory details.</p>
              </div>
            )}
          </IngestPanel>
        </div>
      </div>

      {/* Detected Series Table */}
      <div className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden flex flex-col transition-all hover:shadow-md">
        <div className="px-5 py-4 border-b border-gray-100 flex items-center justify-between font-semibold text-gray-800 text-sm">
          <div className="flex items-center gap-2">
            <RefreshCw className="w-4 h-4 text-[#065F46]" /> Detected Series
          </div>
          <Button variant="ghost" size="sm" onClick={refreshData} className="text-xs text-gray-500 hover:text-gray-900">
            Refresh
          </Button>
        </div>
        <DataTable empty="No detected series yet. Upload data to begin." isEmpty={!series.length}>
          <TableHead>
            <tr className="bg-gray-50 border-b border-gray-100">
              <TableHeaderCell className="font-medium text-gray-500">ID</TableHeaderCell>
              <TableHeaderCell className="font-medium text-gray-500">Sequence Label</TableHeaderCell>
              <TableHeaderCell className="font-medium text-gray-500">Modality</TableHeaderCell>
              <TableHeaderCell className="font-medium text-gray-500">Format</TableHeaderCell>
              <TableHeaderCell className="font-medium text-gray-500">Confidence</TableHeaderCell>
              <TableHeaderCell className="font-medium text-gray-500 text-right">Status</TableHeaderCell>
            </tr>
          </TableHead>
          <tbody className="divide-y divide-gray-100 text-gray-700">
            {series.map((item) => (
              <TableRow key={item.id} className="hover:bg-gray-50 transition-colors">
                <TableCell className="font-mono text-xs text-gray-500">#{item.id}</TableCell>
                <TableCell className="font-medium">{item.sequence_label || '-'}</TableCell>
                <TableCell>
                  <span className={`px-2 py-0.5 rounded-full text-[10px] font-bold uppercase ${
                    item.modality === 'T1' ? 'bg-blue-100 text-blue-700' :
                    item.modality === 'BOLD' ? 'bg-purple-100 text-purple-700' :
                    item.modality === 'DWI' ? 'bg-orange-100 text-orange-700' :
                    'bg-gray-100 text-gray-700'
                  }`}>
                    {item.modality}
                  </span>
                </TableCell>
                <TableCell className="text-xs text-gray-500">{item.format}</TableCell>
                <TableCell>
                  <div className="flex items-center gap-2">
                    <div className="w-16 h-1.5 bg-gray-100 rounded-full overflow-hidden">
                      <div className="h-full bg-[#065F46]" style={{ width: `${item.confidence * 100}%` }} />
                    </div>
                    <span className="text-[10px] font-bold text-gray-500">{(item.confidence * 100).toFixed(0)}%</span>
                  </div>
                </TableCell>
                <TableCell className="text-right">
                   {item.supported_for_processing ? (
                     <CheckCircle2 className="w-4 h-4 text-green-500 ml-auto" />
                   ) : (
                     <span className="text-[10px] text-amber-600 font-medium">QC Pending</span>
                   )}
                </TableCell>
              </TableRow>
            ))}
          </tbody>
        </DataTable>
      </div>
    </div>
  );
}

function IngestPanel({ children, icon, title, trailing }: { children: React.ReactNode; icon: React.ReactNode; title: string; trailing?: React.ReactNode }) {
  return (
    <div className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden transition-all hover:shadow-md">
      <div className="px-5 py-4 border-b border-gray-100 flex items-center justify-between font-semibold text-gray-800 text-sm">
        <div className="flex items-center gap-2">
          <span className="text-[#065F46]">{icon}</span> {title}
        </div>
        {trailing}
      </div>
      <div className="p-5">{children}</div>
    </div>
  );
}

function UploadSlot({ label, description, accept, onUpload, loading }: { label: string; description: string; accept: string; onUpload: (f: File) => void; loading: boolean }) {
  return (
    <label className="flex items-center justify-between gap-4 p-3 rounded-lg border border-gray-100 bg-gray-50 hover:bg-gray-100 transition-colors cursor-pointer group relative overflow-hidden">
      <div className="flex items-center gap-3">
        <div className="w-10 h-10 rounded-lg bg-white border border-gray-100 flex items-center justify-center text-gray-400 group-hover:text-[#065F46] transition-colors">
          {loading ? <Loader2 className="w-5 h-5 animate-spin" /> : <UploadCloud className="w-5 h-5" />}
        </div>
        <div>
          <div className="text-sm font-semibold text-gray-800">{label}</div>
          <div className="text-[10px] text-gray-500 uppercase tracking-tight">{description}</div>
        </div>
      </div>
      <input type="file" className="sr-only" accept={accept} onChange={(e) => e.target.files?.[0] && onUpload(e.target.files[0])} />
      <span className="text-[10px] font-bold text-[#065F46] opacity-0 group-hover:opacity-100 transition-opacity">CHOOSE FILE</span>
      {loading && <div className="absolute bottom-0 left-0 h-0.5 bg-[#065F46] animate-pulse" style={{ width: '100%' }} />}
    </label>
  );
}

function FileInput({ label, accept, onChange }: { label: string; accept: string; onChange: (f: File) => void }) {
  return (
    <div className="space-y-1">
      <div className="text-[10px] font-bold text-gray-400 uppercase tracking-wider">{label}</div>
      <input
        type="file"
        accept={accept}
        className="block w-full text-xs text-gray-500 file:mr-3 file:py-1.5 file:px-3 file:rounded-md file:border-0 file:text-xs file:font-semibold file:bg-gray-100 file:text-gray-700 hover:file:bg-gray-200"
        onChange={(e) => e.target.files?.[0] && onChange(e.target.files[0])}
      />
    </div>
  );
}

function StatBox({ label, value, highlight }: { label: string; value: string | number; highlight?: boolean }) {
  return (
    <div className="p-3 bg-gray-50 rounded-lg border border-gray-100">
      <div className="text-[10px] font-bold text-gray-400 uppercase tracking-wider mb-1">{label}</div>
      <div className={`text-sm font-bold truncate ${highlight ? 'text-green-600' : 'text-gray-700'}`}>
        {typeof value === 'string' ? (value.charAt(0).toUpperCase() + value.slice(1)) : value}
      </div>
    </div>
  );
}
