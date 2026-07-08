const defaultApiBase = `${window.location.protocol}//${window.location.hostname}:8000`;
const API_BASE = localStorage.getItem('apiBase') || defaultApiBase;

export function getApiBase() {
  return API_BASE;
}

async function request(path, options = {}) {
  const res = await fetch(`${API_BASE}${path}`, options);
  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || `HTTP ${res.status}`);
  }
  return res.json();
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

function redactEvidenceText(value) {
  return value
    .replace(/[A-Za-z]:[\\/][^\s"']+/g, '[redacted-host-path]')
    .replace(/\/(?:home|Users|mnt|data|tmp|var)\/[^\s"']+/g, '[redacted-host-path]')
    .replace(/(^|[\s`"'([{])data[\\/]+projects[\\/]+[^\s`"',)\]}]+/g, '$1[redacted-host-path]')
    .replace(/sk-[A-Za-z0-9._-]+/g, '[redacted-secret]')
    .replace(/([A-Z0-9_]*(?:API[_-]?KEY|TOKEN|SECRET|PASSWORD|LICENSE)[A-Z0-9_]*\s*[:=]\s*)[^\s"',}]+/gi, '$1[redacted-secret]')
    .replace(/((?:OPENAI|DEEPSEEK|IMAGE_AGENT_SUDO)_?[A-Z_]*\s*[:=]\s*)[^\s"',}]+/gi, '$1[redacted-secret]');
}

function sanitizeObject(value, blockedKeys) {
  if (Array.isArray(value)) {
    return value.map((item) => sanitizeObject(item, blockedKeys));
  }
  if (value && typeof value === 'object') {
    return Object.fromEntries(
      Object.entries(value)
        .filter(([key]) => !blockedKeys.has(key))
        .map(([key, item]) => [key, sanitizeObject(item, blockedKeys)]),
    );
  }
  if (typeof value === 'string') {
    return redactEvidenceText(value);
  }
  return value;
}

function sanitizeDeploymentResponse(payload) {
  return sanitizeObject(payload, unsafeDeploymentEvidenceKeys);
}

function sanitizeBackendResponse(payload) {
  return sanitizeObject(payload, unsafeBackendPathKeys);
}

function sanitizeAgentResponse(payload) {
  const blocked = new Set([...unsafeBackendPathKeys].filter((key) => key !== 'path'));
  return sanitizeObject(payload, blocked);
}

export const api = {
  health: () => request('/health'),
  deployment: () => request('/deployment').then(sanitizeDeploymentResponse),
  runtimeContainers: () => request('/runtime/containers'),
  login: (username, password) => request('/auth/login', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ username, password }) }),
  listWorkflows: () => request('/workflows'),
  listProjects: () => request('/projects'),
  createProject: (payload) => request('/projects', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) }),
  upload: (projectId, file) => {
    const form = new FormData();
    form.append('file', file);
    return request(`/projects/${projectId}/upload`, { method: 'POST', body: form }).then(sanitizeBackendResponse);
  },
  uploadDwi: (projectId, nifti, bval, bvec, jsonSidecar) => {
    const form = new FormData();
    form.append('nifti', nifti);
    form.append('bval', bval);
    form.append('bvec', bvec);
    form.append('json_sidecar', jsonSidecar);
    return request(`/projects/${projectId}/upload-dwi`, { method: 'POST', body: form }).then(sanitizeBackendResponse);
  },
  uploadDicom: (projectId, archive) => {
    const form = new FormData();
    form.append('archive', archive);
    return request(`/projects/${projectId}/upload-dicom`, { method: 'POST', body: form }).then(sanitizeBackendResponse);
  },
  createUploadSession: (projectId, payload) => request(`/projects/${projectId}/datasets/upload-session`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) }),
  ingestDataset: (projectId, uploadSessionId, archive, syncFastPath = true) => {
    const form = new FormData();
    form.append('archive', archive);
    return request(`/projects/${projectId}/datasets/${uploadSessionId}/ingest?sync_fast_path=${syncFastPath ? 'true' : 'false'}`, { method: 'POST', body: form });
  },
  getInventory: (projectId, uploadSessionId) => request(`/projects/${projectId}/datasets/${uploadSessionId}/inventory`),
  listSeries: (projectId) => request(`/projects/${projectId}/series`),
  listProjectTasks: (projectId) => request(`/projects/${projectId}/tasks`).then(sanitizeBackendResponse),
  runAgent: (projectId, message) => request('/agent/runs', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ project_id: projectId, message }) }).then(sanitizeAgentResponse),
  resumeAgent: (threadId, approved, confirmation) => request(`/agent/runs/${encodeURIComponent(threadId)}/resume`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ approved, confirmation }) }).then(sanitizeAgentResponse),
  getTask: (taskId) => request(`/tasks/${taskId}`).then(sanitizeBackendResponse),
  getLogs: (taskId) => request(`/tasks/${taskId}/logs`).then(sanitizeBackendResponse),
  getTaskEvents: (taskId) => request(`/tasks/${taskId}/events`).then(sanitizeBackendResponse),
  getOutputs: (taskId) => request(`/tasks/${taskId}/outputs`).then(sanitizeBackendResponse),
  getResultSummary: (taskId) => request(`/tasks/${taskId}/result-summary`).then(sanitizeBackendResponse),
  getArtifactManifest: (taskId) => request(`/tasks/${taskId}/artifact-manifest`).then(sanitizeBackendResponse),
};
