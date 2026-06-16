import type {
  DeploymentResponse,
  DwiUploadFiles,
  AgentRunResponse,
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
    throw new Error(text || `HTTP ${response.status}`);
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
    throw new Error(text || `HTTP ${response.status}`);
  }
  return response.blob();
}

function jsonRequest<T>(path: string, body: unknown): Promise<T> {
  return request<T>(path, {
    body: JSON.stringify(body),
    headers: { 'Content-Type': 'application/json' },
    method: 'POST',
  });
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
    return request<{ file: unknown; series: Series }>(`/projects/${projectId}/upload`, { body: form, method: 'POST' });
  },
  uploadDwi: (projectId: number, files: DwiUploadFiles) => {
    const form = new FormData();
    form.append('nifti', files.nifti);
    form.append('bval', files.bval);
    form.append('bvec', files.bvec);
    form.append('json_sidecar', files.jsonSidecar);
    return request<{ files: unknown[]; series: Series }>(`/projects/${projectId}/upload-dwi`, { body: form, method: 'POST' });
  },
  uploadDicom: (projectId: number, archive: File) => {
    const form = new FormData();
    form.append('archive', archive);
    return request<{ file: unknown; series: Series }>(`/projects/${projectId}/upload-dicom`, { body: form, method: 'POST' });
  },
  createUploadSession: (projectId: number, payload: { label: string; source_type: string }) =>
    jsonRequest<{ id: number; project_id: number; status: string }>(`/projects/${projectId}/datasets/upload-session`, payload),
  ingestDataset: (projectId: number, uploadSessionId: number, archive: File, syncFastPath = true) => {
    const form = new FormData();
    form.append('archive', archive);
    return request<{ inventory?: Inventory }>(`/projects/${projectId}/datasets/${uploadSessionId}/ingest?sync_fast_path=${syncFastPath ? 'true' : 'false'}`, {
      body: form,
      method: 'POST',
    });
  },
  getInventory: (projectId: number, uploadSessionId: number) =>
    request<{ inventory: Inventory }>(`/projects/${projectId}/datasets/${uploadSessionId}/inventory`),
  listSeries: (projectId: number) => request<Series[]>(`/projects/${projectId}/series`),
  listProjectTasks: (projectId: number) => request<Task[]>(`/projects/${projectId}/tasks`),
  getSeries: (seriesId: number) => request<Series>(`/series/${seriesId}`),
  runSeries: (seriesId: number, workflowType: string, qsiprepTaskId: number | null = null) =>
    jsonRequest<Task>(`/series/${seriesId}/run`, { qsiprep_task_id: qsiprepTaskId, workflow_type: workflowType }),
  getTask: (taskId: number) => request<Task>(`/tasks/${taskId}`),
  getLogs: (taskId: number) => request<{ task_id: number; text: string }>(`/tasks/${taskId}/logs`),
  getOutputs: (taskId: number) => request<unknown[]>(`/tasks/${taskId}/outputs`),
  getResultSummary: (taskId: number) => request<ResultSummary>(`/tasks/${taskId}/result-summary`),
  getArtifactUrl: (taskId: number, relativePath: string) => requestBlob(`/tasks/${taskId}/artifacts/${encodeArtifactPath(relativePath)}`),
  ragStatus: () => request<RagStatus>('/agent/rag/status'),
  ragQuery: (projectId: number | null, query: string) => jsonRequest<RagResponse>('/agent/rag/query', { project_id: projectId, query }),
  runAgent: (projectId: number | null, message: string) =>
    jsonRequest<AgentRunResponse>('/agent/runs', { message, project_id: projectId }),
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
    }>('/chat', { message, project_id: projectId }),
};
