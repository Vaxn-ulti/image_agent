import type {
  ArtifactManifest,
  DeploymentResponse,
  DwiUploadFiles,
  AgentRunResponse,
  AgentConfirmation,
  Inventory,
  LoginResponse,
  RagStatus,
  Project,
  RagResponse,
  ResultSummary,
  RuntimeResponse,
  Series,
  Task,
  WorkflowCatalogResponse,
} from './types';
import { redactEvidenceText } from './redaction';

const defaultApiBase = `${window.location.protocol}//${window.location.hostname}:8000`;
const apiBaseStorageKey = 'apiBase';

export function getApiBase() {
  return localStorage.getItem(apiBaseStorageKey) || defaultApiBase;
}

export function setApiBase(value: string) {
  const normalized = value.trim().replace(/\/+$/, '');
  if (!normalized) {
    resetApiBase();
    return;
  }
  localStorage.setItem(apiBaseStorageKey, normalized);
}

export function resetApiBase() {
  localStorage.removeItem(apiBaseStorageKey);
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const response = await fetch(`${getApiBase()}${path}`, options);
  if (!response.ok) {
    const text = await response.text();
    throw new Error(errorMessageFromBody(text) || `HTTP ${response.status}`);
  }
  if (response.status === 204) {
    return undefined as T;
  }
  return response.json() as Promise<T>;
}

async function requestBlob(path: string, options: RequestInit = {}): Promise<Blob> {
  const response = await fetch(`${getApiBase()}${path}`, options);
  if (!response.ok) {
    const text = await response.text();
    throw new Error(errorMessageFromBody(text) || `HTTP ${response.status}`);
  }
  return response.blob();
}

function errorMessageFromBody(text: string) {
  if (!text) return '';
  try {
    const parsed = JSON.parse(text) as unknown;
    if (parsed && typeof parsed === 'object' && 'detail' in parsed) {
      const detail = (parsed as { detail?: unknown }).detail;
      if (typeof detail === 'string') return detail;
    }
  } catch {
    return text;
  }
  return text;
}

function jsonRequest<T>(path: string, body: unknown): Promise<T> {
  return request<T>(path, {
    body: JSON.stringify(body),
    headers: { 'Content-Type': 'application/json' },
    method: 'POST',
  });
}

const unsafeBackendPathKeys = new Set(['path', 'preview_path', 'log_path', 'storage_path', 'summary_path', 'absolute_path', 'host_path', 'output_dir']);

function redactBackendPathText(value: string) {
  return redactEvidenceText(value);
}

function sanitizeObject(value: unknown, blockedKeys = unsafeBackendPathKeys): unknown {
  if (Array.isArray(value)) {
    return value.map((item) => sanitizeObject(item, blockedKeys));
  }
  if (value && typeof value === 'object') {
    return Object.fromEntries(
      Object.entries(value as Record<string, unknown>)
        .filter(([key]) => !blockedKeys.has(key))
        .map(([key, item]) => [key, sanitizeObject(item, blockedKeys)]),
    );
  }
  if (typeof value === 'string') {
    return redactBackendPathText(value);
  }
  return value;
}

function sanitizeTask(task: Task): Task {
  return sanitizeObject(task, new Set(['log_path'])) as Task;
}

function sanitizeOutputs(outputs: unknown[]): unknown[] {
  return sanitizeObject(outputs) as unknown[];
}

function sanitizeResultSummary<T>(payload: T): T {
  return sanitizeObject(payload) as T;
}

function sanitizeUploadResponse<T>(payload: T): T {
  return sanitizeObject(payload) as T;
}

function sanitizeInventoryValue(value: unknown): unknown {
  if (Array.isArray(value)) {
    return value.map(sanitizeInventoryValue);
  }
  if (value && typeof value === 'object') {
    return Object.fromEntries(
      Object.entries(value as Record<string, unknown>)
        .filter(([key]) => !['source', 'sidecars', ...unsafeBackendPathKeys].includes(key))
        .map(([key, item]) => [key, key === 'bids_dataset_root' ? 'bids/rawdata' : sanitizeInventoryValue(item)]),
    );
  }
  if (typeof value === 'string') {
    return redactBackendPathText(value);
  }
  return value;
}

function sanitizeInventoryResponse<T>(payload: T): T {
  return sanitizeInventoryValue(payload) as T;
}

function sanitizeAgentResponse<T>(payload: T): T {
  const blocked = new Set([...unsafeBackendPathKeys].filter((key) => key !== 'path'));
  return sanitizeObject(payload, blocked) as T;
}

function encodeArtifactPath(relativePath: string) {
  return relativePath.split('/').map(encodeURIComponent).join('/');
}

export const api = {
  health: () => request<{ status: string; app: string; version: string }>('/health'),
  deployment: () => request<DeploymentResponse>('/deployment'),
  runtimeContainers: () => request<RuntimeResponse>('/runtime/containers'),
  resultContract: () => request<Record<string, unknown>>('/result-contract'),
  login: (username: string, password: string) => jsonRequest<LoginResponse>('/auth/login', { username, password }),
  listWorkflows: () => request<WorkflowCatalogResponse | string[]>('/workflows'),
  listProjects: () => request<Project[]>('/projects'),
  createProject: (payload: { name: string; description?: string }) => jsonRequest<Project>('/projects', payload),
  uploadNifti: (projectId: number, file: File) => {
    const form = new FormData();
    form.append('file', file);
    return request<{ file: unknown; series: Series }>(`/projects/${projectId}/upload`, { body: form, method: 'POST' }).then(sanitizeUploadResponse);
  },
  uploadDwi: (projectId: number, files: DwiUploadFiles) => {
    const form = new FormData();
    form.append('nifti', files.nifti);
    form.append('bval', files.bval);
    form.append('bvec', files.bvec);
    form.append('json_sidecar', files.jsonSidecar);
    return request<{ files: unknown[]; series: Series }>(`/projects/${projectId}/upload-dwi`, { body: form, method: 'POST' }).then(sanitizeUploadResponse);
  },
  uploadDicom: (projectId: number, archive: File) => {
    const form = new FormData();
    form.append('archive', archive);
    return request<{ file: unknown; series: Series }>(`/projects/${projectId}/upload-dicom`, { body: form, method: 'POST' }).then(sanitizeUploadResponse);
  },
  createUploadSession: (projectId: number, payload: { label: string; source_type: string }) =>
    jsonRequest<{ id: number; project_id: number; status: string }>(`/projects/${projectId}/datasets/upload-session`, payload),
  ingestDataset: (projectId: number, uploadSessionId: number, archive: File, syncFastPath = true) => {
    const form = new FormData();
    form.append('archive', archive);
    return request<{ inventory?: Inventory }>(`/projects/${projectId}/datasets/${uploadSessionId}/ingest?sync_fast_path=${syncFastPath ? 'true' : 'false'}`, {
      body: form,
      method: 'POST',
    }).then(sanitizeInventoryResponse);
  },
  getInventory: (projectId: number, uploadSessionId: number) =>
    request<{ inventory: Inventory }>(`/projects/${projectId}/datasets/${uploadSessionId}/inventory`).then(sanitizeInventoryResponse),
  listSeries: (projectId: number) => request<Series[]>(`/projects/${projectId}/series`),
  listProjectTasks: (projectId: number) => request<Task[]>(`/projects/${projectId}/tasks`).then((tasks) => tasks.map(sanitizeTask)),
  getSeries: (seriesId: number) => request<Series>(`/series/${seriesId}`),
  runSeries: (seriesId: number, workflowType: string, qsiprepTaskId: number | null = null) =>
    jsonRequest<Task>(`/series/${seriesId}/run`, { qsiprep_task_id: qsiprepTaskId, workflow_type: workflowType }).then(sanitizeTask),
  getTask: (taskId: number) => request<Task>(`/tasks/${taskId}`).then(sanitizeTask),
  getLogs: (taskId: number) => request<{ task_id: number; text: string }>(`/tasks/${taskId}/logs`),
  getOutputs: (taskId: number) => request<unknown[]>(`/tasks/${taskId}/outputs`).then(sanitizeOutputs),
  getResultSummary: (taskId: number) => request<ResultSummary>(`/tasks/${taskId}/result-summary`).then(sanitizeResultSummary),
  getArtifactManifest: (taskId: number) => request<ArtifactManifest>(`/tasks/${taskId}/artifact-manifest`).then(sanitizeResultSummary),
  getArtifactUrl: (taskId: number, relativePath: string) => requestBlob(`/tasks/${taskId}/artifacts/${encodeArtifactPath(relativePath)}`),
  ragStatus: () => request<RagStatus>('/agent/rag/status'),
  ragQuery: (projectId: number | null, query: string) =>
    jsonRequest<RagResponse>('/agent/rag/query', { project_id: projectId, query }).then(sanitizeAgentResponse),
  runAgent: (projectId: number | null, message: string) =>
    jsonRequest<AgentRunResponse>('/agent/runs', { message, project_id: projectId }).then(sanitizeAgentResponse),
  resumeAgent: (threadId: string, approved: boolean, confirmation: AgentConfirmation) =>
    jsonRequest<AgentRunResponse>(`/agent/runs/${encodeURIComponent(threadId)}/resume`, { approved, confirmation }).then(sanitizeAgentResponse),
  chat: (
    projectId: number | null,
    message: string,
  ) =>
    jsonRequest<{
      provider?: string;
      reply: string;
      intent?: string;
      recommended_next_step?: string;
      tool_chain_hint?: string;
      tool_invocations?: Array<{ tool?: string; status?: string; result?: Record<string, unknown> }>;
      rag_mode?: string;
    }>('/chat', { message, project_id: projectId }).then(sanitizeAgentResponse),
};
