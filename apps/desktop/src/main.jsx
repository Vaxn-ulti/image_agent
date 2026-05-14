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
      t.workflow_type === 'bold_deepprep'
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
          ? 'Run and complete bold_deepprep or t1_deepprep before ALFF/fALFF.'
          : 'Run bold_deepprep_validate, bold_deepprep, t1_deepprep_validate, or t1_deepprep before ALFF/fALFF validate.');
      }
      await api.runSeries(seriesItem.id, workflowType, qsiprep?.id || null);
      await loadTasks(project.id);
    } catch (err) { setError(err.message); }
    finally { setBusy(false); }
  }

  async function showLogs(taskId) { const res = await api.getLogs(taskId); setLogs((prev) => ({ ...prev, [taskId]: res.text })); }
  async function showOutputs(taskId) { const res = await api.getOutputs(taskId); setOutputs((prev) => ({ ...prev, [taskId]: res })); }

  async function sendChat(e) {
    e.preventDefault();
    const form = new FormData(e.currentTarget); const message = form.get('message'); if (!message) return;
    setChatMessages((prev) => [...prev, { role: 'user', content: message }]); e.currentTarget.reset();
    const res = await api.chat(project?.id || null, message);
    setChatMessages((prev) => [...prev, { role: 'assistant', content: res.reply, provider: res.provider }]);
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
          <div className="table">{series.map((s) => <SeriesRow key={s.id} series={s} busy={busy} run={run} hasAnyQsiprep={!!latestQsiprepTask({ requireCompleted: false })} hasCompletedQsiprep={!!latestQsiprepTask({ requireCompleted: true })} hasAnyBoldPreproc={!!latestBoldPreprocTask({ requireCompleted: false })} hasCompletedBoldPreproc={!!latestBoldPreprocTask({ requireCompleted: true })} />)}{!series.length && <div className="empty">No images uploaded.</div>}</div>
        </div>
        <div className="panel">
          <div className="panel-title"><Activity size={18}/>Tasks</div>
          {tasks.map((t) => <div className="task" key={t.id}>
            <div className="task-head"><strong>#{t.id} {t.workflow_type}</strong><span className={`status ${t.status}`}>{t.status} {t.progress}%</span></div>
            <progress value={t.progress} max="100" />
            <div className="button-row"><button onClick={() => showLogs(t.id)}>Logs</button><button onClick={() => showOutputs(t.id)}>Outputs</button></div>
            {logs[t.id] && <pre>{logs[t.id]}</pre>}
            {(outputs[t.id] || []).length > 0 && <ul className="outputs">{outputs[t.id].map((o) => <li key={o.id}>{o.output_type}: {o.path || JSON.stringify(o.metadata)}</li>)}</ul>}
          </div>)}{!tasks.length && <div className="empty">No tasks yet.</div>}
        </div>
        <div className="panel chat">
          <div className="panel-title"><MessageSquare size={18}/>Agent Chat</div>
          <div className="messages">{chatMessages.map((m, i) => <div key={i} className={`msg ${m.role}`}>{m.content}{m.provider && <small>{m.provider}</small>}</div>)}</div>
          <form onSubmit={sendChat}><input name="message" placeholder="task status / list series / explain qsiprep"/><button>Send</button></form>
        </div>
      </section>}
    </main>
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

function SeriesRow({ series, busy, run, hasAnyQsiprep, hasCompletedQsiprep, hasAnyBoldPreproc, hasCompletedBoldPreproc }) {
  const buttons = series.modality === 'T1'
    ? ['t1_deepprep_validate', 't1_deepprep', 't1_deepprep_mock']
    : series.modality === 'BOLD'
      ? ['bold_deepprep_validate', 'bold_deepprep', 'bold_alff_validate', 'bold_alff', 'bold_falff_validate', 'bold_falff']
    : series.modality === 'DWI'
      ? ['dwi_qsiprep_validate', 'dwi_qsiprep', 'dwi_qsi_full_validate', 'dwi_qsi_full', 'dwi_qsirecon_validate', 'dwi_qsirecon']
    : series.modality === 'DICOM'
      ? ['dicom_convert_validate', 'dicom_convert']
      : [];
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
    <div className="workflow-buttons">{buttons.map((w) => <button key={w} disabled={isDisabled(w)} onClick={() => run(series, w)}><Play size={15}/>{w}</button>)}</div>
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
