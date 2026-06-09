import React, { useEffect, useState } from 'react';
import { createRoot } from 'react-dom/client';
import { Activity, Brain, FileUp, MessageSquare, Play, RefreshCw, Server } from 'lucide-react';
import { api, getApiBase } from './lib/api';
import './styles.css';

function App() {
  const [user, setUser] = useState(null);
  const [projects, setProjects] = useState([]);
  const [project, setProject] = useState(null);
  const [series, setSeries] = useState([]);
  const [tasks, setTasks] = useState([]);
  const [outputs, setOutputs] = useState({});
  const [resultSummaries, setResultSummaries] = useState({});
  const [logs, setLogs] = useState({});
  const [workflows, setWorkflows] = useState([]);
  const [dwiFiles, setDwiFiles] = useState({ nifti: null, bval: null, bvec: null });
  const [deployment, setDeployment] = useState(null);
  const [runtime, setRuntime] = useState(null);
  const [inventory, setInventory] = useState(null);
  const [chatMessages, setChatMessages] = useState([{ role: 'assistant', content: 'I can query images, run DICOM conversion, DeepPrep, QSIPrep/QSIRecon, BOLD metrics, and explain task status.' }]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const runtimeModeLabel = deployment?.backend_runtime_mode === 'local' ? 'Local backend' : deployment?.backend_runtime_mode === 'remote' ? 'Remote backend' : null;

  async function loadProjects() { setProjects(await api.listProjects()); }
  async function loadWorkflows() { const res = await api.listWorkflows(); setWorkflows(res.workflows || res); }
  async function loadSeries(projectId = project?.id) { if (projectId) setSeries(await api.listSeries(projectId)); }
  async function loadTasks(projectId = project?.id) { if (projectId) setTasks(await api.listProjectTasks(projectId)); }
  async function refreshAll(projectId = project?.id) { await Promise.all([loadProjects(), loadSeries(projectId), loadTasks(projectId)]); }

  useEffect(() => {
    api.health().then(loadWorkflows).catch(() => setError(`Cannot connect API: ${getApiBase()}`));
    api.deployment().then(setDeployment).catch(() => {});
    api.runtimeContainers().then(setRuntime).catch(() => {});
  }, []);

  useEffect(() => {
    if (!project?.id) return;
    const id = setInterval(() => loadTasks(project.id), 1500);
    return () => clearInterval(id);
  }, [project?.id]);

  async function login(e) {
    e.preventDefault(); setError('');
    const form = new FormData(e.currentTarget);
    const res = await api.login(form.get('username'), form.get('password'));
    setUser(res.user);
    await loadProjects();
  }

  async function createProject(e) {
    e.preventDefault();
    const form = new FormData(e.currentTarget);
    const created = await api.createProject({ name: form.get('name'), description: form.get('description') || '' });
    setProject(created); e.currentTarget.reset(); await refreshAll(created.id);
  }

  async function selectProject(p) { setProject(p); await refreshAll(p.id); }

  async function uploadFile(e) {
    const file = e.target.files?.[0];
    if (!file || !project) return;
    setBusy(true); setError('');
    try { await api.upload(project.id, file); await loadSeries(project.id); }
    catch (err) { setError(err.message); }
    finally { setBusy(false); e.target.value = ''; }
  }

  async function uploadDwi(e) {
    e.preventDefault();
    if (!project || !dwiFiles.nifti || !dwiFiles.bval || !dwiFiles.bvec) { setError('Choose DWI NIfTI, bval, and bvec files.'); return; }
    setBusy(true); setError('');
    try { await api.uploadDwi(project.id, dwiFiles.nifti, dwiFiles.bval, dwiFiles.bvec); setDwiFiles({ nifti: null, bval: null, bvec: null }); await loadSeries(project.id); e.currentTarget.reset(); }
    catch (err) { setError(err.message); }
    finally { setBusy(false); }
  }

  async function uploadDicom(e) {
    const file = e.target.files?.[0];
    if (!file || !project) return;
    setBusy(true); setError('');
    try { await api.uploadDicom(project.id, file); await loadSeries(project.id); }
    catch (err) { setError(err.message); }
    finally { setBusy(false); e.target.value = ''; }
  }

  async function uploadDataset(e) {
    const file = e.target.files?.[0];
    if (!file || !project) return;
    setBusy(true); setError(''); setInventory(null);
    try {
      const session = await api.createUploadSession(project.id, { label: file.name, source_type: 'folder_or_archive' });
      const res = await api.ingestDataset(project.id, session.id, file, true);
      const inv = res.inventory || (await api.getInventory(project.id, session.id)).inventory;
      setInventory(inv);
      await Promise.all([loadSeries(project.id), loadTasks(project.id)]);
    } catch (err) { setError(err.message); }
    finally { setBusy(false); e.target.value = ''; }
  }

  function latestQsiprepTask({ requireCompleted }) {
    const candidates = tasks.filter((t) =>
      t.workflow_type === 'dwi_qsiprep'
      || t.workflow_type === 'dwi_qsiprep_validate'
      || t.workflow_type === 'dwi_qsi_full'
      || t.workflow_type === 'dwi_qsi_full_validate'
    );
    return candidates.find((t) => !requireCompleted || t.status === 'completed') || null;
  }

  function latestBoldPreprocTask({ requireCompleted }) {
    const candidates = tasks.filter((t) =>
      t.workflow_type === 'bold_fmriprep_xcpd_report'
      || t.workflow_type === 'bold_fmriprep_xcpd_report_validate'
      || t.workflow_type === 'bold_deepprep'
      || t.workflow_type === 'bold_deepprep_validate'
      || t.workflow_type === 't1_deepprep'
      || t.workflow_type === 't1_deepprep_validate'
    );
    return candidates.find((t) => !requireCompleted || t.status === 'completed') || null;
  }

  async function run(seriesItem, workflowType) {
    setBusy(true); setError('');
    try {
      const needsQsiprep = workflowType.startsWith('dwi_qsirecon');
      const requireCompleted = needsQsiprep && !workflowType.endsWith('_validate');
      const qsiprep = needsQsiprep ? latestQsiprepTask({ requireCompleted }) : null;
      if (needsQsiprep && !qsiprep) {
        throw new Error(requireCompleted
          ? 'Run and complete dwi_qsiprep or dwi_qsi_full before QSIRecon.'
          : 'Run dwi_qsiprep_validate, dwi_qsiprep, dwi_qsi_full_validate, or dwi_qsi_full before QSIRecon validate.');
      }
      const needsBoldPreproc = workflowType.startsWith('bold_alff') || workflowType.startsWith('bold_falff');
      const needsCompletedBoldPreproc = needsBoldPreproc && !workflowType.endsWith('_validate');
      const boldPreproc = needsBoldPreproc ? latestBoldPreprocTask({ requireCompleted: needsCompletedBoldPreproc }) : null;
      if (needsBoldPreproc && !boldPreproc) {
        throw new Error(needsCompletedBoldPreproc
          ? 'Run and complete BOLD fMRIPrep/XCP-D or legacy DeepPrep before ALFF/fALFF.'
          : 'Run BOLD fMRIPrep/XCP-D validate, BOLD fMRIPrep/XCP-D, or legacy DeepPrep before ALFF/fALFF validate.');
      }
      await api.runSeries(seriesItem.id, workflowType, qsiprep?.id || null);
      await loadTasks(project.id);
    } catch (err) { setError(err.message); }
    finally { setBusy(false); }
  }

  async function showLogs(taskId) { const res = await api.getLogs(taskId); setLogs((prev) => ({ ...prev, [taskId]: res.text })); }
  async function showOutputs(taskId) { const res = await api.getOutputs(taskId); setOutputs((prev) => ({ ...prev, [taskId]: res })); }
  async function showResultSummary(taskId) {
    try {
      const summary = await api.getResultSummary(taskId);
      setResultSummaries((prev) => ({ ...prev, [taskId]: summary }));
    } catch (err) {
      setResultSummaries((prev) => ({ ...prev, [taskId]: { error: err.message } }));
    }
  }

  async function sendChat(e) {
    e.preventDefault();
    const form = new FormData(e.currentTarget); const message = form.get('message'); if (!message) return;
    setChatMessages((prev) => [...prev, { role: 'user', content: message }]); e.currentTarget.reset();
    const res = await api.chat(project?.id || null, message);
    setChatMessages((prev) => [...prev, {
      role: 'assistant',
      content: res.reply,
      provider: res.provider,
      intent: res.intent,
      recommended_next_step: res.recommended_next_step,
      tool_chain_hint: res.tool_chain_hint,
      tool_invocations: res.tool_invocations || [],
      rag_mode: res.rag_mode,
    }]);
  }

  if (!user) return <Login error={error} onLogin={login} />;

  return <div className="app">
    <aside className="sidebar">
      <div className="brand"><Brain size={24}/><span>Brain Image Agent</span></div>
      <div className="server"><Server size={15}/> {getApiBase()} {runtimeModeLabel ? `(${runtimeModeLabel})` : ''}</div>
      <form onSubmit={createProject} className="new-project">
        <input name="name" placeholder="New project" required />
        <input name="description" placeholder="Description" />
        <button>Create</button>
      </form>
      <div className="project-list">{projects.map((p) => <button key={p.id} className={project?.id === p.id ? 'selected' : ''} onClick={() => selectProject(p)}>{p.name}</button>)}</div>
    </aside>
    <main>
      <header><h1>{project ? project.name : 'Select or create a project'}</h1><button onClick={() => refreshAll()}><RefreshCw size={16}/>Refresh</button></header>
      {error && <div className="error">{error}</div>}
      {project && <section className="workspace">
        <RuntimePanel deployment={deployment} runtime={runtime} />
        <div className="panel upload-panel">
          <div className="panel-title"><FileUp size={18}/>Upload T1/BOLD NIfTI</div>
          <input type="file" accept=".nii,.gz" onChange={uploadFile} disabled={busy}/>
        </div>
        <div className="panel upload-panel">
          <div className="panel-title"><FileUp size={18}/>Upload DICOM zip</div>
          <input type="file" accept=".zip" onChange={uploadDicom} disabled={busy}/>
        </div>
        <div className="panel upload-panel">
          <div className="panel-title"><FileUp size={18}/>Upload mixed dataset zip</div>
          <input type="file" accept=".zip" onChange={uploadDataset} disabled={busy}/>
        </div>
        {inventory && <InventoryPanel inventory={inventory} />}
        <form className="panel upload-panel dwi-upload" onSubmit={uploadDwi}>
          <div className="panel-title"><FileUp size={18}/>Upload DWI set</div>
          <label>DWI NIfTI<input type="file" accept=".nii,.gz" onChange={(e) => setDwiFiles((x) => ({ ...x, nifti: e.target.files?.[0] || null }))}/></label>
          <label>bval<input type="file" accept=".bval" onChange={(e) => setDwiFiles((x) => ({ ...x, bval: e.target.files?.[0] || null }))}/></label>
          <label>bvec<input type="file" accept=".bvec" onChange={(e) => setDwiFiles((x) => ({ ...x, bvec: e.target.files?.[0] || null }))}/></label>
          <button disabled={busy}>Upload DWI</button>
        </form>
        <div className="panel">
          <div className="panel-title"><Activity size={18}/>Series</div>
          <div className="table">{series.map((s) => <SeriesRow key={s.id} series={s} workflows={workflows} busy={busy} run={run} hasAnyQsiprep={!!latestQsiprepTask({ requireCompleted: false })} hasCompletedQsiprep={!!latestQsiprepTask({ requireCompleted: true })} hasAnyBoldPreproc={!!latestBoldPreprocTask({ requireCompleted: false })} hasCompletedBoldPreproc={!!latestBoldPreprocTask({ requireCompleted: true })} />)}{!series.length && <div className="empty">No images uploaded.</div>}</div>
        </div>
        <div className="panel">
          <div className="panel-title"><Activity size={18}/>Tasks</div>
          {tasks.map((t) => <div className="task" key={t.id}>
            <div className="task-head"><strong>#{t.id} {t.workflow_type}</strong><span className={`status ${t.status}`}>{t.status} {t.progress}%</span></div>
            <progress value={t.progress} max="100" />
            <div className="button-row"><button onClick={() => showLogs(t.id)}>Logs</button><button onClick={() => showOutputs(t.id)}>Outputs</button><button onClick={() => showResultSummary(t.id)}>Result summary</button></div>
            {logs[t.id] && <pre>{logs[t.id]}</pre>}
            {(outputs[t.id] || []).length > 0 && <ul className="outputs">{outputs[t.id].map((o) => <li key={o.id}>{o.output_type}: {o.path || JSON.stringify(o.metadata)}</li>)}</ul>}
            {resultSummaries[t.id] && <ResultSummaryPanel taskId={t.id} summary={resultSummaries[t.id]} />}
          </div>)}{!tasks.length && <div className="empty">No tasks yet.</div>}
        </div>
        <div className="panel chat">
          <div className="panel-title"><MessageSquare size={18}/>Agent Chat</div>
          <div className="messages">{chatMessages.map((m, i) => <ChatMessage key={i} message={m} />)}</div>
          <form onSubmit={sendChat}><input name="message" placeholder="task status / list series / explain qsiprep"/><button>Send</button></form>
        </div>
      </section>}
    </main>
  </div>;
}

function ChatMessage({ message }) {
  return <div className={`msg ${message.role}`}>
    <div>{message.content}</div>
    {message.role === 'assistant' && (message.intent || message.recommended_next_step || message.tool_invocations?.length > 0) && <div className="agent-meta">
      <div className="agent-meta-row">
        {message.intent && <span>Intent: {message.intent}</span>}
        {message.rag_mode && <span>RAG: {message.rag_mode}</span>}
        {message.provider && <span>Provider: {message.provider}</span>}
      </div>
      {message.recommended_next_step && <div><strong>Next step</strong><p>{message.recommended_next_step}</p></div>}
      {message.tool_chain_hint && <div><strong>Tool chain</strong><p>{message.tool_chain_hint}</p></div>}
      {message.tool_invocations?.length > 0 && <details open>
        <summary>Tool invocations ({message.tool_invocations.length})</summary>
        <ul>
          {message.tool_invocations.map((tool, index) => <li key={`${tool.tool}-${index}`}>
            <strong>{tool.tool}</strong> <span>{tool.status}</span>
            <pre>{JSON.stringify(tool.result, null, 2)}</pre>
          </li>)}
        </ul>
      </details>}
    </div>}
    {message.provider && message.role !== 'assistant' && <small>{message.provider}</small>}
  </div>;
}

function artifactUrl(taskId, artifact) {
  if (artifact.download_url?.startsWith('http')) return artifact.download_url;
  if (artifact.download_url) return `${getApiBase()}${artifact.download_url}`;
  const relativePath = artifactRelativePath(artifact);
  return `${getApiBase()}/tasks/${taskId}/artifacts/${encodeURI(relativePath)}`;
}

function artifactRelativePath(artifact, fallback = 'artifact') {
  const relativePath = String(artifact.relative_path || '').replaceAll('\\', '/');
  if (relativePath) return relativePath;
  const downloadUrl = String(artifact.download_url || '');
  const marker = '/artifacts/';
  const markerIndex = downloadUrl.indexOf(marker);
  if (markerIndex >= 0) return decodeURIComponent(downloadUrl.slice(markerIndex + marker.length));
  const absolutePath = String(artifact.path || fallback).replaceAll('\\', '/');
  return absolutePath.split('/').pop() || fallback;
}

function isHtmlReport(artifact) {
  const relativePath = String(artifact.relative_path || artifact.path || '').toLowerCase();
  const contentType = String(artifact.content_type || '').toLowerCase();
  return contentType.includes('html') || relativePath.endsWith('.html');
}

function isPreviewableFigure(artifact) {
  const relativePath = String(artifact.relative_path || artifact.path || '').toLowerCase();
  const contentType = String(artifact.content_type || '').toLowerCase();
  return contentType.startsWith('image/')
    || relativePath.endsWith('.svg')
    || relativePath.endsWith('.png')
    || relativePath.endsWith('.jpg')
    || relativePath.endsWith('.jpeg')
    || relativePath.endsWith('.webp');
}

function flattenOutputs(outputs, excluded = new Set()) {
  const result = [];
  Object.entries(outputs || {}).forEach(([key, value]) => {
    if (excluded.has(key)) return;
    if (Array.isArray(value)) result.push(...value);
    else if (value && typeof value === 'object') result.push(...flattenOutputs(value, excluded));
  });
  return result;
}

function outputSection(summary, section) {
  return Array.isArray(summary.outputs?.[section]) ? summary.outputs[section] : [];
}

function artifactLabel(artifact, fallback = 'artifact') {
  return artifactRelativePath(artifact, fallback).split('/').pop();
}

function ArtifactList({ taskId, title, artifacts, empty }) {
  if (!artifacts.length) return empty ? <div className="empty">{empty}</div> : null;
  return <div className="artifact-section">
    <strong>{title} <span>{artifacts.length}</span></strong>
    <ul className="outputs artifact-list">{artifacts.map((artifact, index) => {
      const relativePath = artifactRelativePath(artifact, `artifact-${index}`);
      return <li key={`${relativePath}-${index}`}>
        <a href={artifactUrl(taskId, artifact)} target="_blank" rel="noreferrer">{relativePath}</a>
        <span>{artifact.source_stage || artifact.artifact_role || artifact.content_type || ''}</span>
      </li>;
    })}</ul>
  </div>;
}

function ResultSummaryPanel({ taskId, summary }) {
  if (summary.error) return <div className="result-summary error">Result summary unavailable: {summary.error}</div>;
  const reportArtifacts = Array.isArray(summary.outputs?.reports) ? summary.outputs.reports : [];
  const htmlReports = reportArtifacts.filter(isHtmlReport);
  const reportFigures = reportArtifacts.filter(isPreviewableFigure);
  const nativeFigures = [...reportFigures, ...outputSection(summary, 'figures').filter(isPreviewableFigure)];
  const tables = [...outputSection(summary, 'tables'), ...outputSection(summary, 'metrics')];
  const maps = outputSection(summary, 'maps');
  const logs = outputSection(summary, 'logs');
  const sourceArtifacts = flattenOutputs(summary.outputs || {}, new Set(['reports', 'figures', 'tables', 'metrics', 'maps', 'logs']));
  return <div className="result-summary">
    <div className="summary-head">
      <strong>{summary.modality} result summary</strong>
      <span>{summary.workflow_type} / contract {summary.contract_version}</span>
    </div>
    <div className="summary-chips">
      {(summary.feature_groups || []).map((group) => <span key={group}>{group}</span>)}
      {(summary.spaces || []).map((space) => <span key={`space-${space}`}>{space}</span>)}
    </div>
    <div className="native-report">
      <strong>Container-native reports <span>{htmlReports.length}</span></strong>
      {htmlReports.length > 0
        ? <div className="report-links-grid">{htmlReports.map((artifact, index) => {
          const relativePath = artifactRelativePath(artifact, `report-${index}`);
          return <a className="report-link-card" key={`${relativePath}-html-${index}`} href={artifactUrl(taskId, artifact)} target="_blank" rel="noreferrer">
            <span>{artifactLabel(artifact, `report-${index}`)}</span>
            <em>{artifact.source_stage || artifact.artifact_role || artifact.content_type || 'native report'}</em>
          </a>;
        })}</div>
        : <div className="empty">No container-native HTML reports are registered yet.</div>}
    </div>
    <div className="scientific-report">
      <strong>Native QC figures <span>{nativeFigures.length}</span></strong>
      {nativeFigures.length > 0
        ? <div className="report-grid">{nativeFigures.map((artifact, index) => {
          const relativePath = artifactRelativePath(artifact, `report-${index}`);
          return <figure key={`${relativePath}-${index}`}>
            <figcaption><span>{artifactLabel(artifact, `figure-${index}`)}</span><em>{artifact.source_stage || artifact.space || artifact.feature_group || summary.modality}</em></figcaption>
            <a href={artifactUrl(taskId, artifact)} target="_blank" rel="noreferrer"><img src={artifactUrl(taskId, artifact)} alt={`Scientific figure ${relativePath}`} loading="lazy" /></a>
          </figure>;
        })}</div>
        : <div className="empty">No container-native QC figures are registered yet.</div>}
    </div>
    <div className="artifact-columns">
      <ArtifactList taskId={taskId} title="Tables and metrics" artifacts={tables} />
      <ArtifactList taskId={taskId} title="Maps" artifacts={maps} />
      <ArtifactList taskId={taskId} title="Logs" artifacts={logs} />
    </div>
    {sourceArtifacts.length > 0 && <details className="source-artifacts">
      <summary>Other artifacts ({sourceArtifacts.length})</summary>
      <ul className="outputs">{sourceArtifacts.map((artifact, index) => {
        const relativePath = artifactRelativePath(artifact, `artifact-${index}`);
        return <li key={`${relativePath}-${index}`}><a href={artifactUrl(taskId, artifact)} target="_blank" rel="noreferrer">{relativePath}</a> {artifact.space ? `(${artifact.space})` : ''}</li>;
      })}</ul>
    </details>}
  </div>;
}

function InventoryPanel({ inventory }) {
  const modalities = inventory.post_conversion_counts?.by_modality || {};
  const sequences = inventory.post_conversion_counts?.by_sequence || {};
  const unsupported = inventory.recognized_unsupported_sequences || [];
  return <div className="panel inventory-panel">
    <div className="panel-title"><Activity size={18}/>Dataset Inventory</div>
    <div className="inventory-grid">
      <div><strong>Total files</strong><span>{inventory.total_files ?? 0}</span></div>
      <div><strong>DICOM files</strong><span>{inventory.dicom?.found_files ?? 0}</span></div>
      <div><strong>Conversion</strong><span>{inventory.dicom?.conversion_status || 'not_applicable'}</span></div>
      <div><strong>BIDS root</strong><span>{inventory.bids_dataset_root || '-'}</span></div>
    </div>
    <div className="inventory-columns">
      <div><strong>Modalities</strong>{Object.entries(modalities).map(([k, v]) => <span key={k}>{k}: {v}</span>)}</div>
      <div><strong>Sequences</strong>{Object.entries(sequences).map(([k, v]) => <span key={k}>{k}: {v}</span>)}</div>
    </div>
    {unsupported.length > 0 && <div className="unsupported-list"><strong>Recognized but unsupported</strong>{unsupported.map((u) => <div key={u.sequence}>{u.sequence} ({u.count}): {u.message}</div>)}</div>}
  </div>;
}

function RuntimePanel({ deployment, runtime }) {
  const agent = deployment?.agent;
  const workflows = runtime?.workflows || {};
  return <div className="panel runtime-panel">
    <div className="panel-title"><Server size={18}/>Remote Runtime</div>
    <div className="runtime-grid">
      <span>Agent: {agent?.provider || 'rules'} / {agent?.model || 'not configured'} / {agent?.configured ? 'configured' : 'fallback'}</span>
      <span>FreeSurfer license: {runtime?.fs_license_exists ? 'found' : 'missing'}</span>
      {Object.entries(workflows).map(([name, check]) => <span key={name}>{name}: {check.available ? 'image ready' : 'image missing'} ({check.image})</span>)}
    </div>
  </div>;
}

const FALLBACK_WORKFLOWS = {
  T1: ['t1_deepprep_anat_report', 't1_deepprep_validate', 't1_deepprep', 't1_deepprep_mock'],
  BOLD: ['bold_fmriprep_xcpd_report', 'bold_fmriprep_xcpd_report_validate', 'bold_deepprep_validate', 'bold_deepprep', 'bold_alff_validate', 'bold_alff', 'bold_falff_validate', 'bold_falff'],
  DWI: ['dwi_fast_gpu_dti_validate', 'dwi_fast_gpu_dti'],
  DICOM: [],
};

function workflowOptionsForSeries(series, workflows) {
  const registryOptions = (workflows || []).filter((workflow) => {
    if (!workflow?.type || workflow.type === 'toolchain_proposal') return false;
    if (workflow.modality !== series.modality) return false;
    return workflow.lane === 'fixed_workflow' || workflow.api_runnable;
  });
  const options = registryOptions.length > 0
    ? registryOptions
    : (FALLBACK_WORKFLOWS[series.modality] || []).map((type) => ({ type }));
  return options.filter((workflow, index, list) => list.findIndex((item) => item.type === workflow.type) === index);
}

function SeriesRow({ series, workflows, busy, run, hasAnyQsiprep, hasCompletedQsiprep, hasAnyBoldPreproc, hasCompletedBoldPreproc }) {
  const buttons = workflowOptionsForSeries(series, workflows);
  const isDisabled = (workflowType) => {
    if (workflowType.startsWith('bold_alff') || workflowType.startsWith('bold_falff')) {
      if (workflowType.endsWith('_validate')) return busy || !hasAnyBoldPreproc;
      return busy || !hasCompletedBoldPreproc;
    }
    if (!workflowType.startsWith('dwi_qsirecon')) return busy;
    if (workflowType.endsWith('_validate')) return busy || !hasAnyQsiprep;
    return busy || !hasCompletedQsiprep;
  };
  return <div className="row">
    <div><strong>#{series.id} {series.modality}</strong><span>{series.format} / confidence {Number(series.confidence).toFixed(2)}</span></div>
    <div className="meta">shape: {(series.metadata?.shape || []).join(' x ') || 'unknown'} {series.metadata?.has_bval ? '/ bval+bvec' : ''}{series.metadata?.dicom_file_count !== undefined ? `/ ${series.metadata.dicom_file_count} DICOM files` : ''}</div>
    <div className="workflow-buttons">{buttons.map((workflow) => <button key={workflow.type} title={workflow.label || workflow.type} disabled={isDisabled(workflow.type)} onClick={() => run(series, workflow.type)}><Play size={15}/>{workflow.type}</button>)}</div>
  </div>;
}

function Login({ error, onLogin }) {
  return <div className="login-page"><form className="login" onSubmit={onLogin}>
    <div className="brand"><Brain size={28}/><span>Brain Image Agent</span></div>
    <input name="username" placeholder="Username" defaultValue="demo" />
    <input name="password" type="password" placeholder="Password" defaultValue="demo" />
    <button>Connect</button>
    <div className="server">API: {getApiBase()}</div>
    {error && <div className="error">{error}</div>}
  </form></div>;
}

createRoot(document.getElementById('root')).render(<App />);
