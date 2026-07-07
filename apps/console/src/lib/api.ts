import type {
  ArtifactManifest,
  DeploymentResponse,
  DeleteProjectFileResponse,
  DwiUploadFiles,
  AgentRunResponse,
  AgentRunLookupResponse,
  AgentConfirmation,
  Inventory,
  LoginResponse,
  RagStatus,
  Project,
  ProjectFile,
  RagResponse,
  ResultSummary,
  RuntimeResponse,
  Series,
  Task,
  TaskEventsResponse,
  ObserveRepairResponse,
  ProjectAgentRunHistoryResponse,
  WorkflowCatalogResponse,
} from './types';
import { redactEvidenceText } from './redaction';

const apiBaseStorageKey = 'apiBase';
const authTokenStorageKey = 'imageAgentAuthToken';
export const authExpiredEventName = 'image-agent-auth-expired';

function defaultApiBase() {
  return `${window.location.protocol}//${window.location.hostname}:8000`;
}

export function getApiBase() {
  const stored = localStorage.getItem(apiBaseStorageKey);
  if (stored && isStaleLoopbackApiBase(stored)) {
    localStorage.removeItem(apiBaseStorageKey);
    return defaultApiBase();
  }
  return stored || defaultApiBase();
}

function isStaleLoopbackApiBase(value: string) {
  if (['localhost', '127.0.0.1', '::1'].includes(window.location.hostname)) return false;
  try {
    const parsed = new URL(value);
    return ['localhost', '127.0.0.1', '::1'].includes(parsed.hostname);
  } catch {
    return false;
  }
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

export function getAuthToken() {
  return localStorage.getItem(authTokenStorageKey) || '';
}

export function setAuthToken(token: string) {
  const normalized = token.trim();
  if (!normalized) {
    clearAuthToken();
    return;
  }
  localStorage.setItem(authTokenStorageKey, normalized);
}

export function clearAuthToken() {
  const hadToken = Boolean(localStorage.getItem(authTokenStorageKey));
  localStorage.removeItem(authTokenStorageKey);
  if (hadToken) {
    window.dispatchEvent(new Event(authExpiredEventName));
  }
}

function withAuth(options: RequestInit): RequestInit {
  const token = getAuthToken();
  if (!token) return options;
  const headers = { ...((options.headers as Record<string, string> | undefined) || {}) };
  if (!headers.Authorization) {
    headers.Authorization = `Bearer ${token}`;
  }
  return { ...options, headers };
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const response = await fetchWithApiBaseFallback(path, options);
  if (!response.ok) {
    if (response.status === 401 && path !== '/auth/login') {
      clearAuthToken();
      throw new Error('Session expired. Please log in again.');
    }
    const text = await response.text();
    throw new Error(errorMessageFromBody(text) || `HTTP ${response.status}`);
  }
  if (response.status === 204) {
    return undefined as T;
  }
  return response.json() as Promise<T>;
}

async function requestBlob(path: string, options: RequestInit = {}): Promise<Blob> {
  const response = await fetchWithApiBaseFallback(path, options);
  if (!response.ok) {
    if (response.status === 401 && path !== '/auth/login') {
      clearAuthToken();
      throw new Error('Session expired. Please log in again.');
    }
    const text = await response.text();
    throw new Error(errorMessageFromBody(text) || `HTTP ${response.status}`);
  }
  return response.blob();
}

async function fetchWithApiBaseFallback(path: string, options: RequestInit) {
  const hadStoredApiBase = Boolean(localStorage.getItem(apiBaseStorageKey));
  try {
    return await fetch(`${getApiBase()}${path}`, withAuth(options));
  } catch (err) {
    if (!hadStoredApiBase || !isNetworkFetchFailure(err)) throw err;
    localStorage.removeItem(apiBaseStorageKey);
    return fetch(`${getApiBase()}${path}`, withAuth(options));
  }
}

function isNetworkFetchFailure(err: unknown) {
  return err instanceof TypeError && /fetch/i.test(err.message);
}

function errorMessageFromBody(text: string) {
  if (!text) return '';
  try {
    const parsed = JSON.parse(text) as unknown;
    if (parsed && typeof parsed === 'object' && 'detail' in parsed) {
      const detail = (parsed as { detail?: unknown }).detail;
      if (typeof detail === 'string') return detail;
      if (detail && typeof detail === 'object') {
        const structured = detail as { code?: unknown; message?: unknown };
        if (typeof structured.message === 'string' && structured.message.trim()) return structured.message;
        if (typeof structured.code === 'string' && structured.code.trim()) return structured.code;
      }
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
const unsafeDeploymentEvidenceKeys = new Set([
  ...unsafeBackendPathKeys,
  'api_key',
  'embedding_endpoint',
  'embedding_error',
  'elasticsearch_url',
  'error',
  'hybrid_error',
  'manifest_path',
  'password',
  'persist_dir',
  'raw_files',
  'raw_snapshots',
  'raw_sources',
  'secret',
  'token',
  'official_sources',
]);

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
  return sanitizeObject(payload, new Set([...unsafeBackendPathKeys, 'source', 'sidecars'])) as T;
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

function sanitizeDeploymentResponse<T>(payload: T): T {
  return sanitizeObject(payload, unsafeDeploymentEvidenceKeys) as T;
}

function encodeArtifactPath(relativePath: string) {
  return relativePath.split('/').map(encodeURIComponent).join('/');
}

export const api = {
  health: () => request<{ status: string; app: string; version: string }>('/health'),
  deployment: () => request<DeploymentResponse>('/deployment').then(sanitizeDeploymentResponse),
  runtimeContainers: () => request<RuntimeResponse>('/runtime/containers'),
  resultContract: () => request<Record<string, unknown>>('/result-contract'),
  login: async (username: string, password: string) => {
    const response = await jsonRequest<LoginResponse>('/auth/login', { username, password });
    setAuthToken(response.access_token);
    return response;
  },
  listWorkflows: () => request<WorkflowCatalogResponse | string[]>('/workflows'),
  listProjects: () => request<Project[]>('/projects'),
  createProject: (payload: { name: string; description?: string }) => jsonRequest<Project>('/projects', payload),
  uploadFile: (projectId: number, file: File) => {
    const form = new FormData();
    form.append('file', file);
    return request<{ file: unknown; inventory?: Inventory; series: Series | null; status?: string; upload_session_id?: number }>(
      `/projects/${projectId}/upload`,
      { body: form, method: 'POST' },
    ).then(sanitizeUploadResponse);
  },
  uploadNifti: (projectId: number, file: File) => api.uploadFile(projectId, file),
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
  listProjectFiles: (projectId: number) =>
    request<ProjectFile[]>(`/projects/${projectId}/files`).then(sanitizeInventoryResponse),
  deleteProjectFile: (projectId: number, fileId: number) =>
    request<DeleteProjectFileResponse>(`/projects/${projectId}/files/${fileId}`, { method: 'DELETE' }).then(sanitizeInventoryResponse),
  listSeries: (projectId: number) => request<Series[]>(`/projects/${projectId}/series`),
  listProjectTasks: (projectId: number) => request<Task[]>(`/projects/${projectId}/tasks`).then((tasks) => tasks.map(sanitizeTask)),
  getSeries: (seriesId: number) => request<Series>(`/series/${seriesId}`),
  runSeries: (seriesId: number, workflowType: string, qsiprepTaskId: number | null = null) =>
    jsonRequest<Task>(`/series/${seriesId}/run`, { qsiprep_task_id: qsiprepTaskId, workflow_type: workflowType }).then(sanitizeTask),
  getTask: (taskId: number) => request<Task>(`/tasks/${taskId}`).then(sanitizeTask),
  getLogs: (taskId: number) => request<{ task_id: number; text: string }>(`/tasks/${taskId}/logs`).then(sanitizeResultSummary),
  getTaskEvents: (taskId: number) => request<TaskEventsResponse>(`/tasks/${taskId}/events`).then(sanitizeResultSummary),
  getOutputs: (taskId: number) => request<unknown[]>(`/tasks/${taskId}/outputs`).then(sanitizeOutputs),
  getResultSummary: (taskId: number) => request<ResultSummary>(`/tasks/${taskId}/result-summary`).then(sanitizeResultSummary),
  getArtifactManifest: (taskId: number) => request<ArtifactManifest>(`/tasks/${taskId}/artifact-manifest`).then(sanitizeResultSummary),
  createTaskExportBundleTicket: (taskId: number) =>
    request<{ download_url: string; expires_at: number; task_id: number }>(`/tasks/${taskId}/export-bundle-ticket`, { method: 'POST' }),
  getTaskExportBundle: (taskId: number) => requestBlob(`/tasks/${taskId}/export-bundle`),
  observeRepair: (taskId: number) => request<ObserveRepairResponse>(`/tasks/${taskId}/observe-repair`).then(sanitizeResultSummary),
  getArtifactUrl: (taskId: number, relativePath: string) => requestBlob(`/tasks/${taskId}/artifacts/${encodeArtifactPath(relativePath)}`),
  ragStatus: () => request<RagStatus>('/agent/rag/status'),
  ragQuery: (projectId: number | null, query: string) =>
    jsonRequest<RagResponse>('/agent/rag/query', { project_id: projectId, query }).then(sanitizeAgentResponse),
  runAgent: (projectId: number | null, message: string) =>
    jsonRequest<AgentRunResponse>('/agent/runs', { message, project_id: projectId }).then(sanitizeAgentResponse),
  getAgentRun: (agentRunId: string) =>
    request<AgentRunLookupResponse>(`/agent/runs/${encodeURIComponent(agentRunId)}`).then(sanitizeAgentResponse),
  listProjectAgentRuns: (projectId: number) =>
    request<ProjectAgentRunHistoryResponse>(`/projects/${projectId}/agent-runs`).then(sanitizeAgentResponse),
  resumeAgent: (threadId: string, approved: boolean, confirmation: AgentConfirmation) =>
    jsonRequest<AgentRunResponse>(`/agent/runs/${encodeURIComponent(threadId)}/resume`, { approved, confirmation }).then(sanitizeAgentResponse),
};
