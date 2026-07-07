import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  Activity,
  BarChart2,
  Brain,
  CheckCircle2,
  ChevronDown,
  Download,
  ExternalLink,
  Eye,
  Info,
  PanelRightClose,
  PanelRightOpen,
  Play,
  RotateCcw,
  Send,
  SlidersHorizontal,
  Trash2,
  UploadCloud,
  Workflow,
  X,
} from 'lucide-react';
import { useEffect, useMemo, useRef, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { StatusBadge } from '../components/StatusBadge';
import { AuthenticatedArtifactImageLink, artifactRelativePath } from '../components/results/AuthenticatedArtifact';
import { Button } from '../components/ui/Button';
import { api } from '../lib/api';
import { formatAgentText, formatResponseSourceLabel } from '../lib/agentText';
import { queryKeys } from '../lib/query';
import type { AgentConfirmation, AgentRunResponse, ArtifactManifest, DwiUploadFiles, Inventory, OutputItem, ProjectFile, ResultSummary, Series, Task, WorkflowCatalogItem } from '../lib/types';
import { getWorkflowEligibility, normalizeWorkflowCatalog, selectQsiprepTaskId, workflowGroup } from '../lib/workflows';

type DashboardAgentMessage = {
  role: 'user' | 'agent';
  content: string;
  meta?: 'initial-greeting';
  response?: AgentRunResponse;
};

function completedTask(task: Task) {
  return task.status === 'completed' || task.status === 'completed_with_partial_failures';
}

function activeTask(task: Task) {
  return task.status === 'queued' || task.status === 'running';
}

function dashboardAgentMessage(data: AgentRunResponse) {
  let message: string;
  if (data.status === 'task_created' && data.task?.id) {
    message = `Task ${data.task.id} created for ${data.task.workflow_type}.`;
  } else if (data.status === 'confirmation_required' && data.confirmation?.workflow_type) {
    message = data.answer || `Approval required for ${data.confirmation.workflow_type}. Open the Agent page to review and approve.`;
  } else {
    message = data.answer || data.message || 'Agent run completed.';
  }
  return formatAgentText(message);
}

function workflowMetadataFromConfirmation(confirmation: AgentConfirmation | undefined): Partial<WorkflowCatalogItem> {
  const value = confirmation?.workflow_metadata;
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    return {};
  }
  return value as Partial<WorkflowCatalogItem>;
}

function taskTimestamp(task: Task) {
  return task.finished_at || task.started_at || task.created_at || '';
}

type DashboardUploadResponse = {
  file?: unknown;
  files?: unknown[];
  inventory?: Inventory;
  series?: Series | null;
  status?: string;
  upload_session_id?: number;
};

function latestCompletedTask(tasks: Task[]) {
  return [...tasks].filter(completedTask).sort((a, b) => taskTimestamp(b).localeCompare(taskTimestamp(a)) || b.id - a.id)[0];
}

function defaultWorkflowForSeries(series: Series | undefined, workflows: string[]) {
  if (!series) return workflows[0] || '';
  const backendRecommendation = series.workflow_eligibility?.primary_recommendation?.workflow_type;
  if (backendRecommendation && workflows.includes(backendRecommendation)) {
    return backendRecommendation;
  }
  const sameModality = workflows.find((workflow) => workflowGroup(workflow) === series.modality);
  return sameModality || workflows[0] || '';
}

function flattenOutputs(summary: ResultSummary | undefined): OutputItem[] {
  if (!summary) return [];
  return Object.values(summary.outputs).flatMap((group) => (Array.isArray(group) ? group : Object.values(group).flat()));
}

function manifestArtifacts(manifest: ArtifactManifest | undefined): OutputItem[] {
  return manifest?.artifacts || [];
}

function formatCompleted(task: Task) {
  const raw = task.finished_at || task.started_at || task.created_at;
  if (!raw) return task.status === 'running' ? 'Running now' : '--';
  return new Intl.DateTimeFormat(undefined, { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(raw));
}

function isNiftiFile(file: File) {
  const name = file.name.toLowerCase();
  return name.endsWith('.nii') || name.endsWith('.nii.gz');
}

function selectDwiFiles(files: File[]): DwiUploadFiles | null {
  const nifti = files.find(isNiftiFile);
  const bval = files.find((file) => file.name.toLowerCase().endsWith('.bval'));
  const bvec = files.find((file) => file.name.toLowerCase().endsWith('.bvec'));
  const jsonSidecar = files.find((file) => file.name.toLowerCase().endsWith('.json'));
  if (!nifti || !bval || !bvec || !jsonSidecar) return null;
  return { nifti, bval, bvec, jsonSidecar };
}

function selectFileUpload(projectId: number, files: File[]): Promise<DashboardUploadResponse> {
  if (files.length > 1) {
    const dwiFiles = selectDwiFiles(files);
    if (dwiFiles) {
      return api.uploadDwi(projectId, dwiFiles);
    }
    return Promise.all(files.map((file) => selectFileUpload(projectId, [file]))).then((responses) => {
      const last = responses[responses.length - 1];
      const series = [...responses].reverse().find((response) => response.series?.id)?.series ?? null;
      const attachments = responses.flatMap((response) => response.inventory?.attachments || []);
      return {
        files: responses.map((response) => response.file).filter(Boolean),
        inventory: {
          attachments,
          inventory_status: 'completed',
          series: responses.flatMap((response) => response.inventory?.series || []),
          total_files: responses.length,
        },
        series,
        status: 'completed',
        upload_session_id: last?.upload_session_id,
      };
    });
  }

  const file = files[0];
  if (!file) {
    throw new Error('Select a file before uploading.');
  }
  const name = file.name.toLowerCase();
  if (name.endsWith('.zip')) {
    return api.createUploadSession(projectId, { label: file.name, source_type: 'folder_or_archive' }).then(async (session) => {
      const ingest = await api.ingestDataset(projectId, session.id, file);
      return { ...ingest, upload_session_id: session.id };
    });
  }
  return isNiftiFile(file) ? api.uploadNifti(projectId, file) : api.uploadFile(projectId, file);
}

function projectFileDetection(file: ProjectFile) {
  const linked = file.linked_series?.[0];
  if (linked) {
    return `${linked.modality || 'unknown'} / ${linked.sequence_label || 'unlabeled'}`;
  }
  if ((file.file_type || '').toUpperCase() === 'JSON') {
    return file.json_summary && Object.keys(file.json_summary).length ? 'JSON sidecar' : 'JSON attachment';
  }
  return file.file_type ? `${file.file_type} attachment` : 'Attachment';
}

export function DashboardPage() {
  const projectId = Number(useParams().projectId);
  const queryClient = useQueryClient();
  const [error, setError] = useState('');
  const [selectedSeriesId, setSelectedSeriesId] = useState<number | null>(null);
  const [selectedWorkflow, setSelectedWorkflow] = useState('');
  const [lastUploadSessionId, setLastUploadSessionId] = useState<number | null>(null);
  const [lastStartedTask, setLastStartedTask] = useState<Task | null>(null);
  const [skullStripping, setSkullStripping] = useState(true);
  const [biasCorrection, setBiasCorrection] = useState(true);
  const [chatInput, setChatInput] = useState('');
  const [messages, setMessages] = useState<DashboardAgentMessage[]>([]);
  const [agentDrawerOpen, setAgentDrawerOpen] = useState(false);
  const fileInputRef = useRef<HTMLInputElement | null>(null);

  const { data: workflowPayload } = useQuery({ queryFn: api.listWorkflows, queryKey: queryKeys.workflows });
  const seriesQuery = useQuery({ enabled: Boolean(projectId), queryFn: () => api.listSeries(projectId), queryKey: queryKeys.series(projectId) });
  const tasksQuery = useQuery({ enabled: Boolean(projectId), queryFn: () => api.listProjectTasks(projectId), queryKey: queryKeys.tasks(projectId), refetchInterval: 5000 });
  const projectFilesQuery = useQuery({ enabled: Boolean(projectId), queryFn: () => api.listProjectFiles(projectId), queryKey: queryKeys.projectFiles(projectId), retry: false });
  const series = seriesQuery.data || [];
  const tasks = tasksQuery.data || [];
  const projectFiles = projectFilesQuery.data || [];
  const { data: uploadInventoryData } = useQuery({
    enabled: Boolean(projectId && lastUploadSessionId),
    queryFn: () => api.getInventory(projectId, lastUploadSessionId!),
    queryKey: lastUploadSessionId ? queryKeys.inventory(projectId, lastUploadSessionId) : ['inventory', projectId, 'none'],
    refetchInterval: (query) => {
      const status = query.state.data?.inventory?.inventory_status;
      return status === 'running' || status === 'queued' ? 2000 : false;
    },
  });
  const { data: latestStartedTask } = useQuery({
    enabled: Boolean(lastStartedTask?.id),
    queryFn: () => api.getTask(lastStartedTask!.id),
    queryKey: lastStartedTask?.id ? queryKeys.task(lastStartedTask.id) : ['task', 'none'],
    refetchInterval: (query) => {
      const status = query.state.data?.status || lastStartedTask?.status;
      return status === 'running' || status === 'queued' ? 5000 : false;
    },
  });

  const chatMutation = useMutation({
    mutationFn: async (message: string) => {
      const agent = await api.runAgent(projectId, message);
      return { content: dashboardAgentMessage(agent), response: agent };
    },
    onSuccess: (data) => {
      setMessages((prev) => [...prev, { role: 'agent', content: data.content, response: data.response }]);
      if (data.response?.status === 'task_created') {
        queryClient.invalidateQueries({ queryKey: queryKeys.tasks(projectId) });
        if (data.response.task?.id) {
          queryClient.invalidateQueries({ queryKey: queryKeys.task(data.response.task.id) });
        }
      }
    },
    onError: (error) => {
      const message = error instanceof Error ? error.message : "Agent run unavailable.";
      setMessages((prev) => [
        ...prev,
        {
          role: 'agent',
          content: message,
        },
      ]);
    },
  });

  const resumeAgent = useMutation({
    mutationFn: ({ approved, confirmation, threadId }: { approved: boolean; confirmation: NonNullable<AgentRunResponse['confirmation']>; threadId: string }) =>
      api.resumeAgent(threadId, approved, confirmation),
    onSuccess: (data) => {
      setMessages((prev) => [...prev, { role: 'agent', content: dashboardAgentMessage(data), response: data }]);
      queryClient.invalidateQueries({ queryKey: queryKeys.tasks(projectId) });
      if (data.task?.id) {
        setLastStartedTask(data.task);
        queryClient.invalidateQueries({ queryKey: queryKeys.task(data.task.id) });
      }
    },
    onError: (err) => {
      setMessages((prev) => [
        ...prev,
        {
          role: 'agent',
          content: err instanceof Error ? err.message : 'Workflow approval failed.',
        },
      ]);
    },
  });

  const workflowCatalog = normalizeWorkflowCatalog(workflowPayload);
  const workflowOptions = workflowCatalog.workflows;
  const selectedSeries = series.find((item) => item.id === selectedSeriesId) || series[0];
  const effectiveWorkflow = selectedWorkflow || defaultWorkflowForSeries(selectedSeries, workflowOptions);
  const workflowDisplayName = (workflowType: string | null | undefined) => {
    if (!workflowType) return '';
    return workflowCatalog.items[workflowType]?.display_name || workflowType;
  };
  const effectiveWorkflowLabel = workflowDisplayName(effectiveWorkflow);
  const latestTask = latestCompletedTask(tasks);
  const displayedStartedTask = latestStartedTask || lastStartedTask;
  const resultTask = displayedStartedTask && completedTask(displayedStartedTask) ? displayedStartedTask : latestTask;

  const { data: resultSummary } = useQuery({
    enabled: Boolean(resultTask?.id),
    queryFn: () => api.getResultSummary(resultTask!.id),
    queryKey: resultTask?.id ? queryKeys.resultSummary(resultTask.id) : ['result-summary', 'none'],
    retry: false,
  });
  const { data: artifactManifest } = useQuery({
    enabled: Boolean(resultTask?.id),
    queryFn: () => api.getArtifactManifest(resultTask!.id),
    queryKey: resultTask?.id ? ['artifact-manifest', resultTask.id] : ['artifact-manifest', 'none'],
    retry: false,
  });
  const resultWorkflowType = resultSummary?.workflow_type || resultTask?.workflow_type || effectiveWorkflow;
  const resultWorkflowLabel = resultWorkflowType ? workflowDisplayName(resultWorkflowType) : '--';

  const uploadFile = useMutation<DashboardUploadResponse, Error, File[]>({
    mutationFn: (files: File[]) => selectFileUpload(projectId, files),
    onError: (err) => setError(err instanceof Error ? err.message : 'Upload failed'),
    onSuccess: (data) => {
      setError('');
      setLastUploadSessionId(data.upload_session_id ?? null);
      if (data.series?.id) {
        setSelectedSeriesId(data.series.id);
      }
      setSelectedWorkflow('');
      queryClient.invalidateQueries({ queryKey: queryKeys.series(projectId) });
      queryClient.invalidateQueries({ queryKey: queryKeys.projectFiles(projectId) });
    },
  });

  const deleteProjectFile = useMutation({
    mutationFn: (file: ProjectFile) => api.deleteProjectFile(projectId, file.id),
    onError: (err) => setError(err instanceof Error ? err.message : 'Uploaded file could not be deleted.'),
    onSuccess: (data) => {
      setError('');
      if (selectedSeriesId && data.deleted_series_ids?.includes(selectedSeriesId)) {
        setSelectedSeriesId(null);
        setSelectedWorkflow('');
      }
      queryClient.invalidateQueries({ queryKey: queryKeys.projectFiles(projectId) });
      queryClient.invalidateQueries({ queryKey: queryKeys.series(projectId) });
    },
  });

  const runPipeline = useMutation({
    mutationFn: ({ qsiprepTaskId, seriesId, workflowType }: { qsiprepTaskId?: number | null; seriesId: number; workflowType: string }) => {
      const dependencyNote = qsiprepTaskId == null ? '' : ` Use completed QSIPrep task ${qsiprepTaskId} as the QSIRecon prerequisite.`;
      return api.runAgent(
        projectId,
        `Prepare workflow ${workflowType} for series ${seriesId}. Return confirmation only and do not create a task yet.${dependencyNote}`,
      );
    },
    onError: (err) => setError(err instanceof Error ? err.message : 'Pipeline launch failed'),
    onSuccess: (data) => {
      setError('');
      setMessages((prev) => [...prev, { role: 'agent', content: dashboardAgentMessage(data), response: data }]);
      if (data.status === 'confirmation_required') {
        setAgentDrawerOpen(true);
      }
      if (data.status !== 'task_created' || !data.task?.id) {
        return;
      }
      setLastStartedTask(data.task);
      queryClient.invalidateQueries({ queryKey: queryKeys.tasks(projectId) });
      queryClient.invalidateQueries({ queryKey: queryKeys.task(data.task.id) });
    },
  });

  const active = tasks.find(activeTask);
  const completedCount = tasks.filter(completedTask).length;
  const manifestOutputs = useMemo(() => manifestArtifacts(artifactManifest), [artifactManifest]);
  const outputs = useMemo(
    () => (manifestOutputs.length > 0 ? manifestOutputs : flattenOutputs(resultSummary)).slice(0, 5),
    [manifestOutputs, resultSummary],
  );
  const previewImages = useMemo(
    () =>
      outputs
        .filter((output) => output.download_url && (output.preview_kind === 'image' || output.content_type?.startsWith('image/')))
        .slice(0, 4),
    [outputs],
  );
  const eligibility = getWorkflowEligibility(selectedSeries || ({} as Series), effectiveWorkflow, tasks);
  const canRun = Boolean(selectedSeries?.id && effectiveWorkflow && eligibility.runnable && !runPipeline.isPending);
  const uploadInventory = uploadInventoryData?.inventory;
  const uploadInventoryStatus = uploadInventory?.inventory_status;
  const uploadInventoryComplete = uploadInventoryStatus === 'completed';
  const uploadAttachmentCount = uploadInventory?.attachments?.length || 0;
  const latestMessage = messages[messages.length - 1];
  const latestAgentResponse = latestMessage?.role === 'agent' ? latestMessage.response : undefined;
  const pendingConfirmation =
    latestAgentResponse?.status === 'confirmation_required' && latestAgentResponse.thread_id && latestAgentResponse.confirmation
      ? latestAgentResponse
      : null;
  const pendingConfirmationMetadata = workflowMetadataFromConfirmation(pendingConfirmation?.confirmation);
  const pendingConfirmationWorkflowType = String(pendingConfirmation?.confirmation?.workflow_type || 'unknown');
  const pendingConfirmationDisplayName = pendingConfirmationMetadata.display_name || pendingConfirmationWorkflowType;

  function handleRun() {
    if (!selectedSeries?.id || !effectiveWorkflow) {
      setError('Select an imaging series and workflow before running the pipeline.');
      return;
    }
    if (!eligibility.runnable) {
      setError(eligibility.reason || 'Selected workflow cannot run for this series.');
      return;
    }
    runPipeline.mutate({
      qsiprepTaskId: effectiveWorkflow.startsWith('dwi_qsirecon') ? selectQsiprepTaskId(tasks, selectedSeries.id) : null,
      seriesId: selectedSeries.id,
      workflowType: effectiveWorkflow,
    });
  }

  function handleFiles(fileList: FileList | null) {
    const files = Array.from(fileList || []);
    if (!files.length) return;
    uploadFile.mutate(files);
  }

  function handleUploadInputChange(event: React.ChangeEvent<HTMLInputElement>) {
    handleFiles(event.target.files);
    event.target.value = '';
  }

  function openFilePicker() {
    fileInputRef.current?.click();
  }

  function handleDeleteProjectFile(file: ProjectFile) {
    if (deleteProjectFile.isPending) return;
    const ok = window.confirm(`Delete uploaded file "${file.original_name}"? This cannot be undone.`);
    if (!ok) return;
    deleteProjectFile.mutate(file);
  }

  function handleSeriesChange(seriesId: number) {
    setSelectedSeriesId(seriesId);
    setSelectedWorkflow('');
  }

  const seriesSummary = series.length > 0
    ? `I found ${series.length} brain MRI scan${series.length === 1 ? '' : 's'} in this project. The primary series is identified as ${selectedSeries?.modality || 'unknown modality'} (${selectedSeries?.sequence_label || 'unlabeled'}).`
    : "I haven't found any brain imaging data yet. Please upload DICOM or NIfTI files to get started.";

  const recommendation = selectedSeries
    ? `Based on the ${selectedSeries.modality} modality, the selected eligible workflow is ${effectiveWorkflow}. It will prepare the registered processing, QC, and report outputs after you explicitly start it.`
    : "Once you upload data, I can explain the detected files and the workflows that may fit them.";

  useEffect(() => {
    const canRefreshGreeting = messages.length === 0 || messages.every((message) => message.meta === 'initial-greeting');
    if (canRefreshGreeting && (series.length > 0 || workflowOptions.length > 0)) {
      setMessages([{
        role: 'agent',
        content: `Hello! I'm your neuroimaging assistant. ${seriesSummary} ${recommendation}`,
        meta: 'initial-greeting',
      }]);
    }
  }, [series.length, workflowOptions.length, seriesSummary, recommendation, messages.length]);

  useEffect(() => {
    if (uploadInventoryComplete) {
      queryClient.invalidateQueries({ queryKey: queryKeys.series(projectId) });
      queryClient.invalidateQueries({ queryKey: queryKeys.projectFiles(projectId) });
    }
  }, [projectId, queryClient, uploadInventoryComplete]);

  const handleChatSubmit = (e?: React.FormEvent) => {
    e?.preventDefault();
    if (!chatInput.trim() || chatMutation.isPending) return;
    const msg = chatInput;
    setMessages((prev) => [...prev, { role: 'user', content: msg }]);
    setChatInput('');
    chatMutation.mutate(msg);
  };

  const sendQuickChat = (msg: string) => {
    if (chatMutation.isPending) return;
    setMessages((prev) => [...prev, { role: 'user', content: msg }]);
    chatMutation.mutate(msg);
  };

  const projectDataError = seriesQuery.error || tasksQuery.error;
  const projectDataErrorMessage = projectDataError instanceof Error ? projectDataError.message : 'Project data could not be loaded.';

  if (seriesQuery.isError || tasksQuery.isError) {
    return (
      <div className="max-w-7xl mx-auto space-y-8 px-4">
        <div>
          <h1 className="text-4xl font-bold text-gray-900 mb-3 tracking-tight">Brain Imaging Processing Agent</h1>
          <p className="text-gray-500 max-w-3xl text-sm leading-relaxed">
            Upload brain MRI data and let the agent guide you through preprocessing, segmentation, and analysis.
            This tool is designed for efficient, automated neuroimaging workflows.
          </p>
        </div>

        <div className="rounded-lg border border-amber-200 bg-amber-50 p-6 text-sm text-amber-800">
          <div className="flex items-center gap-2 text-base font-semibold text-amber-900">
            <Info className="w-4 h-4 shrink-0" /> Project data unavailable
          </div>
          <p className="mt-2">{projectDataErrorMessage}</p>
          <Link
            className="mt-4 inline-flex items-center gap-2 rounded-md bg-white px-3 py-2 text-xs font-semibold text-amber-800 shadow-sm ring-1 ring-amber-200 hover:bg-amber-100"
            to="/projects"
          >
            Switch project
          </Link>
        </div>
      </div>
    );
  }

  return (
    <div>
      <div className="max-w-[1480px] mx-auto space-y-4 px-4 py-5">
        {/* Title Area */}
        <div>
          <h1 className="text-3xl font-bold text-gray-900 mb-2 tracking-tight">Brain Imaging Processing Agent</h1>
          <p className="text-gray-500 max-w-3xl text-sm leading-snug">
            Upload brain MRI data and let the agent guide you through preprocessing, segmentation, and analysis.
            This tool is designed for efficient, automated neuroimaging workflows.
          </p>
        </div>

        {error ? (
          <div className="rounded-md border border-red-200 bg-red-50 p-3 text-sm text-red-700 flex items-center gap-2">
             <Info className="w-4 h-4 shrink-0" /> {error}
          </div>
        ) : null}

        <div className="rounded-lg border border-emerald-100 bg-emerald-50/60 px-4 py-2 text-sm shadow-sm">
          <div className="flex flex-col gap-2 md:flex-row md:items-center md:justify-between">
            <div>
              <div className="font-semibold text-emerald-900">Recommended plan</div>
              <div className="mt-0.5 text-xs text-emerald-800/80">
                Pipeline: {effectiveWorkflowLabel || 'Waiting for workflow catalog'}
                {!eligibility.runnable && effectiveWorkflow ? <span className="ml-2 text-amber-700">{eligibility.reason}</span> : null}
              </div>
            </div>
            {displayedStartedTask ? (
              <div className="rounded-md border border-emerald-100 bg-white px-3 py-2 text-xs text-gray-700">
                <div className="font-semibold text-gray-900">Task #{displayedStartedTask.id} {displayedStartedTask.status}</div>
                <div className="mt-0.5">Progress: {displayedStartedTask.progress}%</div>
                <div className="mt-0.5">Workflow: {workflowDisplayName(displayedStartedTask.workflow_type)}</div>
                <div className="mt-0.5 text-[11px] text-gray-500">Stable workflow ID: {displayedStartedTask.workflow_type}</div>
                {completedTask(displayedStartedTask) ? (
                  <Link className="mt-1 inline-flex text-[#065F46] hover:underline" to={`/projects/${projectId}/results/${displayedStartedTask.id}`}>
                    View task results
                  </Link>
                ) : null}
              </div>
            ) : (
              <div className="text-xs text-emerald-800/80">{series.length ? 'Data are ready for workflow review.' : 'Upload data to review workflow eligibility.'}</div>
            )}
          </div>
        </div>

        <div className="grid grid-cols-12 gap-3 items-start">
          {/* Row 1: Upload (7) and Workflow Status (5) */}
          <div className="col-span-12 lg:col-span-7">
            <div className="bg-white rounded-lg border border-gray-200 shadow-sm overflow-hidden flex flex-col transition-all hover:shadow-md h-full">
              <div className="px-4 py-2.5 border-b border-gray-100 flex items-center gap-2 font-semibold text-gray-800 text-sm">
                <UploadCloud className="w-4 h-4 text-[#065F46]" /> Upload Data
              </div>
              <div className="p-3 flex-1 flex flex-col">
                <div
                  aria-label="Open file picker area"
                  className="min-h-[126px] border-2 border-dashed border-gray-200 rounded-lg flex flex-col items-center justify-center p-4 bg-gray-50 hover:bg-gray-100 transition-colors cursor-pointer group"
                  role="button"
                  tabIndex={0}
                  onClick={(event) => {
                    if ((event.target as HTMLElement).closest('button')) return;
                    openFilePicker();
                  }}
                  onKeyDown={(event) => {
                    if (event.key === 'Enter' || event.key === ' ') {
                      event.preventDefault();
                      openFilePicker();
                    }
                  }}
                >
                  <UploadCloud className="w-7 h-7 text-gray-400 mb-2 group-hover:text-[#065F46] transition-colors" />
                  <div className="text-sm font-medium text-gray-700 mb-1">Drag & drop files here</div>
                  <div className="text-xs text-gray-500 mb-3">or click to browse from your computer</div>
                  <button
                    className="bg-[#065F46] text-white px-4 py-1.5 rounded-md text-xs font-medium shadow-sm hover:bg-[#044E3A] transition-colors"
                    type="button"
                    onClick={openFilePicker}
                  >
                    Browse Files
                  </button>
                  <input
                    aria-label="Upload files"
                    className="sr-only"
                    ref={fileInputRef}
                    type="file"
                    multiple
                    onClick={(event) => event.stopPropagation()}
                    onChange={handleUploadInputChange}
                  />
                </div>
                <div className="mt-2 flex justify-between items-center gap-3 text-[11px]">
                  <span className="text-gray-500">Medical imaging is detected for workflows; other files are saved as project attachments.</span>
                  <Link className="text-[#065F46] hover:underline font-medium inline-flex items-center gap-1" to={`/projects/${projectId}/ingest`}>
                    Advanced Ingest <ExternalLink className="w-3 h-3" />
                  </Link>
                </div>
                {lastUploadSessionId ? (
                  <div className="mt-3 rounded-md border border-emerald-100 bg-emerald-50 px-3 py-2 text-xs font-medium text-emerald-700">
                    <div>Upload session #{lastUploadSessionId}</div>
                    {uploadInventoryStatus ? (
                      <div className="mt-1 space-y-0.5 text-[11px] text-emerald-700/80">
                        <div>Ingest {uploadInventoryComplete ? 'completed' : uploadInventoryStatus}</div>
                        {typeof uploadInventory?.total_files === 'number' ? <div>{uploadInventory.total_files} files inventoried</div> : null}
                        {uploadAttachmentCount ? <div>{uploadAttachmentCount} attachment{uploadAttachmentCount === 1 ? '' : 's'} saved</div> : null}
                      </div>
                    ) : null}
                  </div>
                ) : null}
                <div className="mt-3 rounded-md border border-gray-200 bg-white">
                  <div className="flex items-center justify-between border-b border-gray-100 px-3 py-2">
                    <div className="text-xs font-semibold text-gray-800">Uploaded files</div>
                    <div className="text-[11px] text-gray-500">{projectFiles.length} total</div>
                  </div>
                  {projectFiles.length ? (
                    <div className="max-h-40 overflow-auto divide-y divide-gray-100">
                      {projectFiles.map((file) => (
                        <div className="grid grid-cols-[minmax(0,1fr)_auto_auto] gap-2 px-3 py-2 text-xs" key={file.id}>
                          <div className="min-w-0">
                            <div className="truncate font-medium text-gray-800" title={file.original_name}>{file.original_name}</div>
                            <div className="text-[11px] text-gray-500">{file.file_type || 'unknown file'}</div>
                          </div>
                          <div className="self-center rounded bg-gray-100 px-2 py-1 text-[11px] font-medium text-gray-700">
                            {projectFileDetection(file)}
                          </div>
                          <button
                            aria-label={`Delete ${file.original_name}`}
                            className="inline-flex items-center gap-1 self-center rounded border border-red-200 bg-red-50 px-2 py-1 text-[11px] font-semibold text-red-700 transition-colors hover:bg-red-100 hover:text-red-800 disabled:cursor-not-allowed disabled:opacity-50"
                            disabled={deleteProjectFile.isPending}
                            title={`Delete ${file.original_name}`}
                            type="button"
                            onClick={() => handleDeleteProjectFile(file)}
                          >
                            <Trash2 className="h-4 w-4" />
                            <span>Delete</span>
                          </button>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <div className="px-3 py-3 text-xs text-gray-500">No uploaded files recorded yet.</div>
                  )}
                </div>
              </div>
            </div>
          </div>

          <div className="col-span-12 lg:col-span-5">
            <div className="bg-white rounded-lg border border-gray-200 shadow-sm overflow-hidden transition-all hover:shadow-md h-full">
              <div className="px-4 py-2.5 border-b border-gray-100 flex items-center gap-2 font-semibold text-gray-800 text-sm">
                <Activity className="w-4 h-4 text-[#065F46]" /> Workflow Status
              </div>
              <div className="p-3">
                <div className="relative space-y-2 before:absolute before:inset-0 before:ml-[9px] before:-translate-x-px md:before:mx-auto md:before:translate-x-0 before:h-full before:w-px before:bg-gradient-to-b before:from-transparent before:via-slate-300 before:to-transparent">
                  <WorkflowStep
                    title="Intake"
                    description="Data uploaded"
                    status={series.length ? 'completed' : 'pending'}
                    meta={series.length ? `${series.length} series` : 'Waiting'}
                  />
                  <WorkflowStep
                    title="Preprocessing"
                    description="Bias correction, skull stripping, normalization"
                    status={completedCount ? 'completed' : active ? 'active' : 'pending'}
                    meta={active?.workflow_type ? workflowDisplayName(active.workflow_type) : completedCount ? 'Completed' : 'Pending'}
                  />
                  <WorkflowStep
                    title="Segmentation"
                    description="Automated tissue & structure segmentation"
                    status={active ? 'active' : completedCount ? 'completed' : 'pending'}
                    meta={active ? `${active.progress}%` : 'Pending'}
                  />
                  <WorkflowStep
                    title="QC Review"
                    description="Quality control checks"
                    status={latestTask ? 'completed' : 'pending'}
                    meta={latestTask ? 'Ready' : 'Pending'}
                  />
                  <WorkflowStep
                    title="Report Generation"
                    description="Generate PDF report"
                    status={resultSummary ? 'completed' : 'pending'}
                    meta={resultSummary ? 'Ready' : 'Pending'}
                  />
                </div>
              </div>
            </div>
          </div>

          {/* Row 2: Pipeline Parameters (5) and Recent Runs (7) */}
          <div className="col-span-12 lg:col-span-5">
            <div className="bg-white rounded-lg border border-gray-200 shadow-sm overflow-hidden transition-all hover:shadow-md flex flex-col h-full">
              <div className="px-4 py-2.5 border-b border-gray-100 flex items-center justify-between font-semibold text-gray-800 text-sm">
                <div className="flex items-center gap-2">
                  <SlidersHorizontal className="w-4 h-4 text-[#065F46]" /> Pipeline Parameters
                  <span className="text-xs font-normal text-gray-400 ml-2">Advanced settings</span>
                </div>
              </div>
              <div className="p-3 flex-1 space-y-2.5">
                <div className="flex items-center justify-between gap-3">
                  <span className="text-xs font-medium text-gray-700 flex items-center gap-1">
                    Input Series <Info className="w-3.5 h-3.5 text-gray-400" />
                  </span>
                  <select
                    className="text-xs border border-gray-200 rounded-md px-3 py-1.5 bg-white outline-none w-[160px]"
                    value={selectedSeries?.id || ''}
                    onChange={(event) => handleSeriesChange(Number(event.target.value))}
                  >
                    {series.map((item) => (
                      <option key={item.id} value={item.id}>
                        #{item.id} {item.sequence_label || item.modality}
                      </option>
                    ))}
                    {series.length === 0 ? <option value="">No series available</option> : null}
                  </select>
                </div>
                <div className="flex items-center justify-between gap-3">
                  <span className="text-xs font-medium text-gray-700 flex items-center gap-1">
                    Preprocessing Preset <Info className="w-3.5 h-3.5 text-gray-400" />
                  </span>
                  <select
                    className="text-xs border border-gray-200 rounded-md px-3 py-1.5 bg-white outline-none w-[160px]"
                    value={effectiveWorkflow}
                    onChange={(event) => setSelectedWorkflow(event.target.value)}
                  >
                    {workflowOptions.map((workflow) => (
                      <option key={workflow} value={workflow}>
                        {workflowCatalog.items[workflow]?.display_name || workflow}
                      </option>
                    ))}
                    {workflowOptions.length === 0 ? <option value="">No workflows available</option> : null}
                  </select>
                </div>
                <div className="flex items-center justify-between gap-3">
                  <span className="text-xs font-medium text-gray-700">Skull Stripping</span>
                  <Toggle checked={skullStripping} onChange={setSkullStripping} />
                </div>
                <div className="flex items-center justify-between gap-3">
                  <span className="text-xs font-medium text-gray-700">Bias Field Correction</span>
                  <Toggle checked={biasCorrection} onChange={setBiasCorrection} />
                </div>
                <div className="flex items-center justify-between gap-3">
                  <span className="text-xs font-medium text-gray-700 flex items-center gap-1">
                    Tissue Segmentation <Info className="w-3.5 h-3.5 text-gray-400" />
                  </span>
                  <div className="text-xs font-medium text-gray-500 bg-white px-3 py-1.5 rounded-md border border-gray-100 w-[160px] truncate">
                    FastSurfer (Recommended)
                  </div>
                </div>
                <div className="flex items-center justify-between gap-3">
                  <span className="text-xs font-medium text-gray-700 flex items-center gap-1">
                    Parcellation Atlas <Info className="w-3.5 h-3.5 text-gray-400" />
                  </span>
                  <div className="text-xs font-medium text-gray-500 bg-white px-3 py-1.5 rounded-md border border-gray-100 w-[160px] truncate">
                    Desikan-Killiany (68)
                  </div>
                </div>

                {!eligibility.runnable && effectiveWorkflow && (
                  <div className="mt-2 p-2 rounded bg-amber-50 text-xs text-amber-700 border border-amber-100">
                    {eligibility.reason}
                  </div>
                )}
                
                <div className="pt-2 border-t border-gray-100">
                  <Button
                    onClick={handleRun}
                    disabled={!canRun}
                    variant="primary"
                    className="w-full justify-center gap-2 h-8 bg-[#065F46] hover:bg-[#044E3A] border-none text-white font-semibold text-sm rounded-md"
                  >
                    {runPipeline.isPending ? (
                      <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                    ) : (
                      <Play className="w-4 h-4 fill-current" />
                    )}
                    Run Workflow
                  </Button>
                </div>
              </div>
            </div>
          </div>

          <div className="col-span-12 lg:col-span-7">
            <div className="bg-white rounded-lg border border-gray-200 shadow-sm overflow-hidden flex flex-col transition-all hover:shadow-md h-full">
              <div className="px-4 py-2.5 border-b border-gray-100 flex items-center justify-between font-semibold text-gray-800 text-sm">
                <div className="flex items-center gap-2">
                  <RotateCcw className="w-4 h-4 text-[#065F46]" /> Recent Runs
                </div>
                <Link className="text-[#065F46] hover:underline font-medium text-xs" to={`/projects/${projectId}/tasks`}>
                  View all
                </Link>
              </div>
              <div className="overflow-x-auto flex-1">
                <table className="w-full text-left text-xs whitespace-nowrap">
                  <thead className="bg-gray-50 text-gray-500 border-b border-gray-100">
                    <tr>
                      <th className="px-4 py-2 font-medium">ID</th>
                      <th className="px-4 py-2 font-medium">Dataset</th>
                      <th className="px-4 py-2 font-medium">Status</th>
                      <th className="px-4 py-2 font-medium">Completed</th>
                      <th className="px-4 py-2 font-medium text-right">Actions</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-100 text-gray-700">
                    {tasks.slice(0, 3).map((task) => {
                      const taskSeries = series.find((item) => item.id === task.series_id);
                      const taskWorkflowLabel = workflowDisplayName(task.workflow_type);
                      return (
                        <tr className="hover:bg-gray-50 transition-colors" key={task.id}>
                          <td className="px-4 py-2 font-mono text-[11px] text-gray-500">RUN-{task.id}</td>
                          <td className="px-4 py-2 max-w-[220px]">
                            <div className="truncate">{taskSeries?.sequence_label || taskWorkflowLabel}</div>
                            {!taskSeries?.sequence_label ? (
                              <div className="mt-0.5 truncate text-[10px] text-gray-400">Stable workflow ID: {task.workflow_type}</div>
                            ) : null}
                          </td>
                          <td className="px-4 py-2">
                            <StatusBadge status={task.status} />
                          </td>
                          <td className="px-4 py-2 text-gray-500">{formatCompleted(task)}</td>
                          <td className="px-4 py-2 flex items-center justify-end gap-2">
                            <Link className="p-1 hover:bg-gray-200 rounded text-gray-500 transition-colors" to={`/projects/${projectId}/results/${task.id}`}>
                              <Eye className="w-4 h-4" />
                            </Link>
                            {completedTask(task) ? (
                              <Link className="p-1 hover:bg-gray-200 rounded text-gray-500 transition-colors" to={`/projects/${projectId}/reports`}>
                                <Download className="w-4 h-4" />
                              </Link>
                            ) : (
                              <button className="p-1 hover:bg-red-50 rounded text-gray-400 hover:text-red-500 transition-colors">
                                <Trash2 className="w-4 h-4" />
                              </button>
                            )}
                          </td>
                        </tr>
                      );
                    })}
                    {tasks.length === 0 && (
                      <tr>
                        <td className="px-4 py-7 text-center text-gray-400" colSpan={5}>
                          No runs yet. Upload data and start the pipeline.
                        </td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>
            </div>
          </div>

          {/* Row 3: Results Preview (12) */}
          <div className="col-span-12">
            <div
              className="bg-white rounded-lg border border-gray-200 shadow-sm overflow-hidden flex flex-col transition-all hover:shadow-md"
              data-testid="results-preview"
            >
              <div className="px-4 py-2.5 border-b border-gray-100 flex items-center gap-2 font-semibold text-gray-800 text-sm">
                <BarChart2 className="w-4 h-4 text-[#065F46]" /> Results Preview
              </div>
              <div className="p-3 flex flex-col md:flex-row gap-4">
                {/* Info Column */}
                <div className="w-full md:w-[170px] flex-shrink-0 space-y-3 text-sm border-b md:border-b-0 md:border-r border-gray-100 pb-4 md:pb-0 md:pr-5">
                  <MetaItem label="Dataset" value={selectedSeries?.sequence_label || 'No dataset'} />
                  <MetaItem label="Date" value={resultTask ? formatCompleted(resultTask) : '--'} />
                  <MetaItem label="Pipeline" value={resultWorkflowLabel} />
                  <MetaItem label="Duration" value={resultSummary?.provenance?.runtime_sec ? `${resultSummary.provenance.runtime_sec}s` : '--'} />
                  <div className="pt-2">
                    <Link
                      className="w-full flex justify-center items-center gap-2 border border-gray-300 bg-white text-gray-700 px-3 py-2 rounded-md font-medium text-xs hover:bg-gray-50 shadow-sm transition-colors"
                      to={resultTask ? `/projects/${projectId}/results/${resultTask.id}` : `/projects/${projectId}/results`}
                    >
                      View Full Results <ExternalLink className="w-3.5 h-3.5" />
                    </Link>
                  </div>
                </div>

                {/* Native artifact preview */}
                <div className="flex-1">
                  {previewImages.length > 0 ? (
                    <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 mb-4">
                      {previewImages.map((image) => (
                        <div className="flex flex-col items-center" key={image.download_url}>
                          <span className="text-[11px] font-medium text-gray-700 mb-1.5 truncate w-full text-center">
                            {image.relative_path || image.feature_group || 'QC preview'}
                          </span>
                          <div className="w-full aspect-square bg-gray-950 rounded-lg overflow-hidden relative shadow-inner group">
                            {resultTask ? (
                              <AuthenticatedArtifactImageLink
                                alt={image.relative_path || image.download_url || 'QC preview'}
                                className="w-full h-full object-contain opacity-90 transition-opacity group-hover:opacity-100"
                                relativePath={artifactRelativePath(image)}
                                taskId={resultTask.id}
                              />
                            ) : null}
                          </div>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <div className="mb-6 text-center py-6 text-gray-400 text-xs bg-gray-50 rounded-lg border border-dashed border-gray-200">
                      No native QC preview images available for this run.
                    </div>
                  )}

                  {/* Artifacts List */}
                  <div className="space-y-2">
                    <div className="text-[10px] font-bold text-gray-400 uppercase tracking-wider mb-2">Key Artifacts</div>
                    {outputs.map((output) => (
                      <div className="flex items-center justify-between gap-3 rounded-md border border-gray-100 bg-gray-50 px-3 py-2 text-xs" key={output.relative_path || output.path}>
                        <span className="truncate font-mono text-gray-600">{output.relative_path || output.path}</span>
                        <span className="shrink-0 px-2 py-0.5 rounded-full bg-white border border-gray-200 text-[#065F46] font-semibold text-[10px] uppercase">
                          {output.feature_group || 'artifact'}
                        </span>
                      </div>
                    ))}
                    {!outputs.length && (
                      <div className="text-center py-4 text-gray-400 text-xs bg-gray-50 rounded-lg border border-dashed border-gray-200">
                        No result artifacts available for this run.
                      </div>
                    )}
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Drawer Toggle Button (Visible when closed) */}
      {!agentDrawerOpen && (
        <button
          onClick={() => setAgentDrawerOpen(true)}
          className="fixed right-0 top-1/2 -translate-y-1/2 bg-[#065F46] text-white p-3 rounded-l-lg shadow-2xl z-40 hover:bg-[#044E3A] transition-all hover:pl-4 group"
          aria-label="Open Agent Copilot"
        >
          <PanelRightOpen className="w-6 h-6" />
          <span className="absolute right-full mr-2 bg-gray-800 text-white text-[10px] px-2 py-1 rounded opacity-0 group-hover:opacity-100 transition-opacity whitespace-nowrap pointer-events-none">
            Open Agent Copilot
          </span>
        </button>
      )}

      {/* Agent Copilot Floating Drawer */}
      {agentDrawerOpen ? (
      <aside className="fixed right-0 top-0 h-screen w-full bg-white border-l border-gray-200 shadow-2xl transition-all duration-300 z-50 flex flex-col sm:w-[400px]">
        <div className="bg-white flex flex-col h-full">
          <div className="px-5 py-4 border-b border-gray-100 flex items-center justify-between font-bold text-gray-800 text-sm bg-white">
            <div className="flex items-center gap-2">
              <Brain className="w-4 h-4 text-[#065F46]" /> Agent Copilot
            </div>
            <button
              onClick={() => setAgentDrawerOpen(false)}
              className="p-1.5 hover:bg-gray-100 rounded-md text-gray-500 transition-colors"
              aria-label="Collapse Agent Copilot"
            >
              <PanelRightClose className="w-5 h-5" />
            </button>
          </div>

          <div className="flex-1 overflow-y-auto p-5 space-y-4 bg-white">
            {messages.map((msg, idx) => (
              <div key={idx} className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
                <div className={`max-w-[85%] p-3 rounded-lg text-sm ${
                  msg.role === 'user'
                    ? 'bg-[#065F46] text-white rounded-br-none'
                    : 'bg-gray-100 text-gray-800 rounded-bl-none shadow-sm'
                }`}>
                  {msg.role === 'agent' && formatResponseSourceLabel(msg.response?.response_source) ? (
                    <div className="mb-1 text-[10px] font-semibold uppercase tracking-normal text-gray-500">
                      {formatResponseSourceLabel(msg.response?.response_source)}
                    </div>
                  ) : null}
                  {msg.content}
                </div>
              </div>
            ))}
            {chatMutation.isPending && (
              <div className="flex justify-start">
                <div className="bg-gray-100 text-gray-400 p-3 rounded-lg rounded-bl-none text-xs flex items-center gap-2">
                  <div className="flex gap-1">
                    <span className="w-1.5 h-1.5 bg-gray-400 rounded-full animate-bounce"></span>
                    <span className="w-1.5 h-1.5 bg-gray-400 rounded-full animate-bounce [animation-delay:0.2s]"></span>
                    <span className="w-1.5 h-1.5 bg-gray-400 rounded-full animate-bounce [animation-delay:0.4s]"></span>
                  </div>
                  Agent is thinking...
                </div>
              </div>
            )}
            {messages.length === 0 && !chatMutation.isPending && (
              <div className="h-full flex flex-col items-center justify-center text-gray-400 space-y-2">
                <Brain className="w-8 h-8 opacity-20" />
                <p className="text-xs">Initializing agent...</p>
              </div>
            )}
          </div>

          <div className="px-5 py-3 border-t border-gray-50 bg-gray-50/50 flex flex-wrap gap-2">
            <button
              onClick={() => sendQuickChat("Explain this step")}
              className="text-[10px] font-semibold bg-white border border-gray-200 px-2 py-1 rounded hover:bg-gray-50 text-gray-600 transition-colors"
            >
              Explain this step
            </button>
            <button
              onClick={() => sendQuickChat(selectedSeries ? "Review detected scan" : "How do I upload data?")}
              className="text-[10px] font-semibold bg-white border border-gray-200 px-2 py-1 rounded hover:bg-gray-50 text-gray-600 transition-colors"
            >
              Review detected scan
            </button>
            <Link
              to={`/projects/${projectId}/agent`}
              className="text-[10px] font-semibold bg-white border border-gray-200 px-2 py-1 rounded hover:bg-gray-50 text-gray-600 transition-colors"
            >
              Open full chat
            </Link>
          </div>

          {pendingConfirmation?.thread_id && pendingConfirmation.confirmation ? (
            <div className="mx-4 mt-3 rounded-lg border border-amber-200 bg-amber-50 p-3 text-xs text-amber-900">
              <div className="flex items-center gap-2 font-bold">
                <Info className="w-3.5 h-3.5 shrink-0" />
                Approval required
              </div>
              <div className="mt-2 font-semibold leading-5 text-amber-950">
                {pendingConfirmationDisplayName}
              </div>
              {pendingConfirmationMetadata.capability_summary ? (
                <div className="mt-1 leading-5 text-amber-800">
                  {pendingConfirmationMetadata.capability_summary}
                </div>
              ) : null}
              <div className="mt-2 grid grid-cols-2 gap-2">
                <span className="text-amber-700">Stable workflow ID</span>
                <span className="truncate text-right font-semibold">
                  {pendingConfirmationWorkflowType}
                </span>
                <span className="text-amber-700">Series</span>
                <span className="text-right font-semibold">
                  #{String(pendingConfirmation.confirmation.series_id || 'unknown')}
                </span>
              </div>
              <div className="mt-3 rounded-md border border-amber-200 bg-white px-3 py-2">
                <div className="font-bold text-amber-900">Task not created yet</div>
                <div className="mt-1 text-[11px] text-amber-700">
                  Backend API creates the task only after approval.
                </div>
              </div>
              <div className="mt-3 flex gap-2">
                <button
                  type="button"
                  disabled={resumeAgent.isPending}
                  onClick={() => resumeAgent.mutate({
                    approved: true,
                    confirmation: pendingConfirmation.confirmation!,
                    threadId: pendingConfirmation.thread_id!,
                  })}
                  className="flex-1 rounded-md bg-[#065F46] px-3 py-2 text-[11px] font-bold text-white shadow-sm hover:bg-[#044E3A] disabled:cursor-not-allowed disabled:opacity-50"
                >
                  Approve workflow
                </button>
                <button
                  type="button"
                  disabled={resumeAgent.isPending}
                  onClick={() => resumeAgent.mutate({
                    approved: false,
                    confirmation: pendingConfirmation.confirmation!,
                    threadId: pendingConfirmation.thread_id!,
                  })}
                  className="rounded-md border border-amber-200 bg-white px-3 py-2 text-[11px] font-bold text-amber-800 hover:bg-amber-100 disabled:cursor-not-allowed disabled:opacity-50"
                >
                  Cancel
                </button>
              </div>
            </div>
          ) : null}

          <div className="p-4 border-t border-gray-100 space-y-3 bg-white">
            <Button
              onClick={handleRun}
              disabled={!canRun}
              variant="primary"
              className="w-full justify-start gap-2 h-9 bg-[#065F46] hover:bg-[#044E3A] border-none text-white px-4 text-xs"
            >
              {runPipeline.isPending ? (
                <div className="w-3 h-3 border-2 border-white/30 border-t-white rounded-full animate-spin" />
              ) : (
                <Play className="w-3 h-3 fill-current" />
              )}
              Prepare selected workflow
            </Button>

            <form onSubmit={handleChatSubmit} className="flex gap-2">
              <input
                type="text"
                value={chatInput}
                onChange={(e) => setChatInput(e.target.value)}
                placeholder="Ask the agent..."
                className="flex-1 bg-gray-50 border border-gray-200 rounded-md px-3 py-1.5 text-xs focus:outline-none focus:ring-1 focus:ring-[#065F46]"
                disabled={chatMutation.isPending}
              />
              <button
                type="submit"
                disabled={!chatInput.trim() || chatMutation.isPending}
                className="bg-[#065F46] text-white p-1.5 rounded-md hover:bg-[#044E3A] disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                aria-label="Send message"
              >
                <Send className="w-3.5 h-3.5" />
              </button>
            </form>

            <div className="flex items-center gap-1.5 text-[10px] text-gray-400 px-1">
              <Info className="w-3 h-3 shrink-0" />
              <span>No medical diagnosis provided.</span>
            </div>
          </div>
        </div>
      </aside>
      ) : null}
    </div>
  );
}

function WorkflowStep({ title, description, status, meta }: { title: string; description: string; status: 'completed' | 'active' | 'pending'; meta: string }) {
  return (
    <div className="relative flex items-center gap-3 text-sm">
      <div className="z-10 flex-shrink-0">
        {status === 'completed' ? (
          <div className="w-5 h-5 rounded-full bg-green-500 flex items-center justify-center text-white border-2 border-white shadow-sm">
            <CheckCircle2 className="w-3.5 h-3.5" />
          </div>
        ) : status === 'active' ? (
          <div className="w-5 h-5 rounded-full bg-white border-2 border-blue-500 flex items-center justify-center shadow-sm relative">
            <div className="w-2 h-2 bg-blue-500 rounded-full animate-pulse"></div>
          </div>
        ) : (
          <div className="w-5 h-5 rounded-full bg-gray-200 border-2 border-white flex items-center justify-center text-[9px] font-bold text-gray-500 shadow-sm">
             {title === 'Intake' ? '1' : title === 'Preprocessing' ? '2' : title === 'Segmentation' ? '3' : title === 'QC Review' ? '4' : '5'}
          </div>
        )}
      </div>
      <div className="flex-1">
        <h4 className={`text-sm leading-tight font-semibold ${status === 'pending' ? 'text-gray-400' : 'text-gray-900'}`}>{title}</h4>
        <p className="text-[11px] leading-tight text-gray-500">{description}</p>
      </div>
      <div className="text-right text-[11px] leading-tight flex flex-col items-end">
        <span className={`font-medium ${status === 'active' ? 'text-blue-600' : status === 'completed' ? 'text-green-600' : 'text-gray-400'}`}>
          {status === 'active' ? 'In Progress' : status === 'completed' ? 'Completed' : 'Pending'}
        </span>
        <span className="text-gray-500 text-[10px]">{meta}</span>
      </div>
    </div>
  );
}

function Toggle({ checked, onChange }: { checked: boolean; onChange: (checked: boolean) => void }) {
  return (
    <button
      onClick={() => onChange(!checked)}
      className={`w-10 h-5 rounded-full relative transition-colors ${checked ? 'bg-[#065F46]' : 'bg-gray-300'}`}
    >
      <div className={`w-4 h-4 bg-white rounded-full absolute top-0.5 shadow-sm transition-all ${checked ? 'right-0.5' : 'left-0.5'}`} />
    </button>
  );
}

function MetaItem({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div className="text-gray-500 text-[10px] uppercase tracking-wider font-bold mb-0.5">{label}</div>
      <div className="font-medium text-gray-800 text-xs truncate">{value}</div>
    </div>
  );
}
