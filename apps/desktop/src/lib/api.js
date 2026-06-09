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

export const api = {
  health: () => request('/health'),
  deployment: () => request('/deployment'),
  runtimeContainers: () => request('/runtime/containers'),
  login: (username, password) => request('/auth/login', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ username, password }) }),
  listWorkflows: () => request('/workflows'),
  listProjects: () => request('/projects'),
  createProject: (payload) => request('/projects', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) }),
  upload: (projectId, file) => {
    const form = new FormData();
    form.append('file', file);
    return request(`/projects/${projectId}/upload`, { method: 'POST', body: form });
  },
  uploadDwi: (projectId, nifti, bval, bvec) => {
    const form = new FormData();
    form.append('nifti', nifti);
    form.append('bval', bval);
    form.append('bvec', bvec);
    return request(`/projects/${projectId}/upload-dwi`, { method: 'POST', body: form });
  },
  uploadDicom: (projectId, archive) => {
    const form = new FormData();
    form.append('archive', archive);
    return request(`/projects/${projectId}/upload-dicom`, { method: 'POST', body: form });
  },
  createUploadSession: (projectId, payload) => request(`/projects/${projectId}/datasets/upload-session`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) }),
  ingestDataset: (projectId, uploadSessionId, archive, syncFastPath = true) => {
    const form = new FormData();
    form.append('archive', archive);
    return request(`/projects/${projectId}/datasets/${uploadSessionId}/ingest?sync_fast_path=${syncFastPath ? 'true' : 'false'}`, { method: 'POST', body: form });
  },
  getInventory: (projectId, uploadSessionId) => request(`/projects/${projectId}/datasets/${uploadSessionId}/inventory`),
  listSeries: (projectId) => request(`/projects/${projectId}/series`),
  listProjectTasks: (projectId) => request(`/projects/${projectId}/tasks`),
  runSeries: (seriesId, workflowType, qsiprepTaskId = null) => request(`/series/${seriesId}/run`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ workflow_type: workflowType, qsiprep_task_id: qsiprepTaskId }) }),
  getTask: (taskId) => request(`/tasks/${taskId}`),
  getLogs: (taskId) => request(`/tasks/${taskId}/logs`),
  getOutputs: (taskId) => request(`/tasks/${taskId}/outputs`),
  getResultSummary: (taskId) => request(`/tasks/${taskId}/result-summary`),
  chat: (projectId, message) => request('/chat', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ project_id: projectId, message }) }),
};
