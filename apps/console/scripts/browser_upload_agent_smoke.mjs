import { createWriteStream } from 'node:fs';
import { mkdir, rm, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { spawn } from 'node:child_process';
import zlib from 'node:zlib';

const __filename = fileURLToPath(import.meta.url);
const CONSOLE_ROOT = path.resolve(path.dirname(__filename), '..');
const REPO_ROOT = path.resolve(CONSOLE_ROOT, '..', '..');
const API_ROOT = path.join(REPO_ROOT, 'apps', 'api');
const DEFAULT_AGENT_MESSAGE = '替我分析一下现在的数据';
const DEFAULT_RUNTIME_SOURCE_MESSAGE = '你现在是基于规则脚本回答，还是基于LLM在回答';
const DEFAULT_T1_METRIC_MESSAGE = '给我分析一下t1提取出来的指标，综合水平怎么样，符不符合正常水平';
const DEFAULT_WORKFLOW_CONFIRMATION_MESSAGE = ({ projectId, seriesId }) =>
  `请为项目${projectId}的序列${seriesId}准备 t1_deepprep_anat_report 工作流确认，不要创建或启动任务`;
const REQUIRED_ANSWER_FRAGMENTS = ['项目状态概览', '任务 #', '只读观察'];
const FORBIDDEN_ANSWER_FRAGMENTS = ['Tasks:', 'Model gateway is not configured'];
const RUNTIME_SOURCE_REQUIRED_FRAGMENTS = [
  '这次回答来源：后端规则和运行状态检查',
  '当前模型网关',
];
const T1_METRIC_REQUIRED_FRAGMENTS = [
  'T1 结构化结果解读',
  'BrainSegVol',
  '不能仅凭这些输出判断正常或异常',
];

export function parseArgs(argv) {
  const args = {
    agentMessage: '',
    apiPort: 0,
    consolePort: 0,
    headless: true,
    outputJson: '',
    root: '',
    runtimeSourceQuestion: false,
    t1MetricQuestion: false,
    workflowConfirmationResume: false,
  };
  for (let index = 0; index < argv.length; index += 1) {
    const arg = argv[index];
    if (arg === '--headed') {
      args.headless = false;
    } else if (arg === '--runtime-source-question') {
      args.runtimeSourceQuestion = true;
    } else if (arg === '--t1-metric-question') {
      args.t1MetricQuestion = true;
    } else if (arg === '--workflow-confirmation-resume') {
      args.workflowConfirmationResume = true;
    } else if (arg === '--root') {
      args.root = argv[++index];
    } else if (arg === '--api-port') {
      args.apiPort = Number(argv[++index]);
    } else if (arg === '--console-port') {
      args.consolePort = Number(argv[++index]);
    } else if (arg === '--agent-message') {
      args.agentMessage = argv[++index];
    } else if (arg === '--output-json') {
      args.outputJson = argv[++index];
    } else {
      throw new Error(`Unknown argument: ${arg}`);
    }
  }
  return args;
}

function freePort() {
  return new Promise((resolve, reject) => {
    import('node:net').then(({ createServer }) => {
      const server = createServer();
      server.once('error', reject);
      server.listen(0, '127.0.0.1', () => {
        const address = server.address();
        server.close(() => resolve(address.port));
      });
    }).catch(reject);
  });
}

async function requestJson(method, url, payload) {
  const response = await fetch(url, {
    body: payload === undefined ? undefined : JSON.stringify(payload),
    headers: payload === undefined ? undefined : { 'content-type': 'application/json' },
    method,
  });
  if (!response.ok) {
    throw new Error(`${method} ${url} failed: HTTP ${response.status} ${await response.text()}`);
  }
  return response.json();
}

async function waitForJson(url, predicate, label, timeoutMs = 30000) {
  const deadline = Date.now() + timeoutMs;
  let lastError = '';
  while (Date.now() < deadline) {
    try {
      const payload = await requestJson('GET', url);
      if (predicate(payload)) return payload;
      lastError = JSON.stringify(payload).slice(0, 500);
    } catch (error) {
      lastError = error instanceof Error ? error.message : String(error);
    }
    await new Promise(resolve => setTimeout(resolve, 250));
  }
  throw new Error(`${label} did not become ready: ${lastError}`);
}

async function waitForHttp(url, label, timeoutMs = 30000) {
  const deadline = Date.now() + timeoutMs;
  let lastError = '';
  while (Date.now() < deadline) {
    try {
      const response = await fetch(url);
      if (response.ok) return;
      lastError = `HTTP ${response.status}`;
    } catch (error) {
      lastError = error instanceof Error ? error.message : String(error);
    }
    await new Promise(resolve => setTimeout(resolve, 250));
  }
  throw new Error(`${label} did not become ready: ${lastError}`);
}

function spawnManaged(command, args, options) {
  const proc = spawn(command, args, {
    cwd: options.cwd,
    env: { ...process.env, ...(options.env || {}) },
    stdio: ['ignore', 'pipe', 'pipe'],
    windowsHide: true,
  });
  let stdout = '';
  let stderr = '';
  proc.stdout.on('data', chunk => {
    stdout += chunk.toString();
  });
  proc.stderr.on('data', chunk => {
    stderr += chunk.toString();
  });
  return {
    process: proc,
    async stop() {
      if (proc.exitCode !== null) return;
      proc.kill();
      await new Promise(resolve => setTimeout(resolve, 250));
      if (proc.exitCode === null) proc.kill('SIGKILL');
    },
    tail() {
      return { stderr: stderr.slice(-2000), stdout: stdout.slice(-2000) };
    },
  };
}

async function startApiServer({ corsOrigin, port, root }) {
  const effectivePort = port > 0 ? port : await freePort();
  const args = ['scripts/run_isolated_api_server.py', '--root', root, '--port', String(effectivePort)];
  if (corsOrigin) {
    args.push('--cors-origin', corsOrigin);
  }
  const proc = spawnManaged(
    'python',
    args,
    { cwd: API_ROOT },
  );
  const baseUrl = `http://127.0.0.1:${effectivePort}`;
  try {
    await waitForJson(`${baseUrl}/health`, payload => payload?.status === 'ok', 'API server');
  } catch (error) {
    const tail = proc.tail();
    await proc.stop();
    throw new Error(`${error instanceof Error ? error.message : String(error)}\n${tail.stderr || tail.stdout}`);
  }
  return { baseUrl, stop: proc.stop };
}

async function startConsoleServer({ apiBaseUrl, port }) {
  const effectivePort = port > 0 ? port : await freePort();
  const viteBin = path.join(CONSOLE_ROOT, 'node_modules', 'vite', 'bin', 'vite.js');
  const proc = spawnManaged(
    'node',
    [viteBin, '--host', '127.0.0.1', '--port', String(effectivePort)],
    {
      cwd: CONSOLE_ROOT,
      env: { VITE_API_BASE_URL: apiBaseUrl },
    },
  );
  const baseUrl = `http://127.0.0.1:${effectivePort}`;
  try {
    await waitForHttp(baseUrl, 'Console dev server');
  } catch (error) {
    const tail = proc.tail();
    await proc.stop();
    throw new Error(`${error instanceof Error ? error.message : String(error)}\n${tail.stderr || tail.stdout}`);
  }
  return { baseUrl, stop: proc.stop };
}

async function createProject({ apiBaseUrl }) {
  const project = await requestJson('POST', `${apiBaseUrl}/projects`, {
    description: 'Browser upload-to-Agent smoke',
    name: 'browser-upload-agent-smoke',
  });
  if (!Number.isInteger(project.id)) throw new Error('Project creation did not return id');
  return { project_id: project.id };
}

async function seedRunningT1Task({ projectId, root, seriesId }) {
  const script = [
    'from app.db import database',
    'database.init_db()',
    'now = database.now_iso()',
    'with database.connect() as conn:',
    '    conn.execute("INSERT INTO tasks(id, project_id, series_id, workflow_type, runtime_workflow_type, status, progress, log_path, error_message, created_at, started_at, finished_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)", (9001, PROJECT_ID, SERIES_ID, "t1_deepprep_anat_report", "t1_deepprep_anat_report", "running", 35, "logs/task-9001.log", None, now, now, None))',
    'print("seeded")',
  ].join('\n').replace('PROJECT_ID', String(projectId)).replace('SERIES_ID', String(seriesId));
  const seedPath = path.join(root, 'seed_browser_smoke.py');
  await writeFile(seedPath, script, 'utf8');
  await new Promise((resolve, reject) => {
    const proc = spawn('python', [seedPath], {
      cwd: API_ROOT,
      env: {
        ...process.env,
        IMAGE_AGENT_ENV_FILE: path.join(root, '.env'),
        IMAGE_AGENT_ROOT: root,
        PYTHONPATH: API_ROOT,
      },
      stdio: ['ignore', 'pipe', 'pipe'],
      windowsHide: true,
    });
    let stderr = '';
    proc.stderr.on('data', chunk => {
      stderr += chunk.toString();
    });
    proc.on('exit', code => {
      if (code === 0) resolve();
      else reject(new Error(stderr || `seed task exited with code ${code}`));
    });
  });
  return {
    progress: 35,
    status: 'running',
    task_id: 9001,
    workflow_type: 't1_deepprep_anat_report',
  };
}

async function seedCompletedT1ResultSummary({ projectId, root, seriesId }) {
  const script = `
import json
from pathlib import Path
from app.db import database

database.init_db()
now = database.now_iso()
task_id = 9140
root = Path(ROOT_VALUE)
out_dir = root / "projects" / str(PROJECT_ID_VALUE) / "derivatives" / str(task_id) / "output"
summary_dir = out_dir / "summary"
tables_dir = out_dir / "tables"
summary_dir.mkdir(parents=True, exist_ok=True)
tables_dir.mkdir(parents=True, exist_ok=True)
summary_path = summary_dir / "t1_result_summary.json"
brain_table = tables_dir / "t1_brain_measures.tsv"
brain_table.write_text(
    "measure\\tmetric\\tdescription\\tvalue\\tunit\\n"
    "BrainSegVol\\tbrain_segmentation_volume\\tBrain Segmentation Volume\\t1199123.4\\tmm^3\\n",
    encoding="utf-8",
)
summary_path.write_text(json.dumps({
    "contract_version": "result_summary.v1",
    "task_id": task_id,
    "workflow_type": "t1_deepprep_anat_report",
    "modality": "T1",
    "spaces": ["T1w", "MNI152"],
    "feature_groups": ["segmentation_volumes", "cortical_thickness", "regional_morphometry", "quality_control"],
    "outputs": {
        "tables": [
            {"name": "t1_brain_measures", "relative_path": "tables/t1_brain_measures.tsv", "download_url": f"/tasks/{task_id}/artifacts/tables/t1_brain_measures.tsv"},
            {"name": "t1_t1w_regions", "relative_path": "tables/t1_t1w_regions.tsv", "download_url": f"/tasks/{task_id}/artifacts/tables/t1_t1w_regions.tsv"},
        ],
        "qc": [{"name": "t1_qc_index", "relative_path": "qc/t1_qc_index.json", "download_url": f"/tasks/{task_id}/artifacts/qc/t1_qc_index.json"}],
        "reports": [{"name": "scientific_report", "relative_path": "reports/index.html", "download_url": f"/tasks/{task_id}/artifacts/reports/index.html"}],
    },
    "provenance": {
        "method": "deepprep_freesurfer_stats_parser",
        "placeholder_outputs": False,
        "extraction_status": "real_deepprep_freesurfer_stats",
        "parsed_counts": {"brain_measures": 12, "regions": 68, "maps": 4, "transforms": 2},
    },
}, ensure_ascii=False, indent=2), encoding="utf-8")
with database.connect() as conn:
    conn.execute(
        "INSERT INTO tasks(id, project_id, series_id, workflow_type, runtime_workflow_type, status, progress, log_path, error_message, created_at, started_at, finished_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
        (task_id, PROJECT_ID_VALUE, SERIES_ID_VALUE, "t1_deepprep_anat_report", "t1_deepprep", "completed", 100, str(out_dir / "task-9140.log"), None, now, now, now),
    )
    conn.execute(
        "INSERT INTO outputs(task_id, output_type, path, preview_path, metadata_json, created_at) VALUES(?,?,?,?,?,?)",
        (task_id, "json", str(summary_path), None, json.dumps({"kind": "result_summary", "modality": "T1"}), now),
    )
print("seeded-completed-t1")
`.replace('ROOT_VALUE', JSON.stringify(root).replaceAll('\\\\', '\\\\\\\\'))
    .replaceAll('PROJECT_ID_VALUE', String(projectId))
    .replaceAll('SERIES_ID_VALUE', String(seriesId));
  const seedPath = path.join(root, 'seed_completed_t1_result_summary.py');
  await writeFile(seedPath, script, 'utf8');
  await new Promise((resolve, reject) => {
    const proc = spawn('python', [seedPath], {
      cwd: API_ROOT,
      env: {
        ...process.env,
        IMAGE_AGENT_ENV_FILE: path.join(root, '.env'),
        IMAGE_AGENT_ROOT: root,
        PYTHONPATH: API_ROOT,
      },
      stdio: ['ignore', 'pipe', 'pipe'],
      windowsHide: true,
    });
    let stderr = '';
    proc.stderr.on('data', chunk => {
      stderr += chunk.toString();
    });
    proc.on('exit', code => {
      if (code === 0) resolve();
      else reject(new Error(stderr || `seed completed T1 result-summary exited with code ${code}`));
    });
  });
  return {
    task_id: 9140,
    workflow_type: 't1_deepprep_anat_report',
  };
}

async function writeMinimalNifti(filePath) {
  const header = Buffer.alloc(348);
  header.writeInt32LE(348, 0);
  [3, 64, 64, 32, 1, 1, 1, 1].forEach((value, index) => header.writeInt16LE(value, 40 + index * 2));
  header.writeInt16LE(16, 70);
  header.writeInt16LE(32, 72);
  [0, 1, 1, 1.2, 1, 0, 0, 0].forEach((value, index) => header.writeFloatLE(value, 76 + index * 4));
  header.write('n+1\0', 344, 'binary');
  await mkdir(path.dirname(filePath), { recursive: true });
  await new Promise((resolve, reject) => {
    const gzip = zlib.createGzip();
    const out = createWriteStream(filePath);
    out.on('finish', resolve);
    out.on('error', reject);
    gzip.on('error', reject);
    gzip.pipe(out);
    gzip.end(header);
  });
}

async function launchBrowser({ headless }) {
  const { chromium } = await import('playwright');
  return chromium.launch({ headless });
}

async function waitForCreatedWorkflowTask({ apiBaseUrl, projectId }, deps) {
  const url = `${apiBaseUrl}/projects/${projectId}/tasks`;
  const deadline = Date.now() + 20000;
  let tasks = [];
  while (Date.now() < deadline) {
    tasks = await deps.requestJson('GET', url);
    if (
      Array.isArray(tasks)
      && tasks.some(task => task?.workflow_type === 't1_deepprep_anat_report' && Number(task?.id) > 0)
    ) {
      break;
    }
    await new Promise(resolve => setTimeout(resolve, 250));
  }
  if (
    !Array.isArray(tasks)
    || !tasks.some(task => task?.workflow_type === 't1_deepprep_anat_report' && Number(task?.id) > 0)
  ) {
    throw new Error('created workflow task did not become ready');
  }
  return tasks.find(task => task?.workflow_type === 't1_deepprep_anat_report' && Number(task?.id) > 0);
}

async function driveBrowserFlow({
  agentMessage,
  apiBaseUrl,
  consoleBaseUrl,
  headless,
  projectId,
  runtimeSourceQuestion,
  root,
  t1MetricQuestion,
  workflowConfirmationResume,
}, deps) {
  const browser = await deps.launchBrowser({ headless });
  try {
    const page = await browser.newPage();
    const browserEvents = [];
    page.on?.('console', message => {
      browserEvents.push(`console.${message.type?.() || 'log'}: ${message.text?.() || ''}`);
    });
    page.on?.('pageerror', error => {
      browserEvents.push(`pageerror: ${error.message || String(error)}`);
    });
    await page.addInitScript((baseUrl) => {
      window.localStorage.setItem('apiBase', baseUrl);
      window.localStorage.setItem('imageAgentAuthToken', 'mvp-token');
    }, apiBaseUrl);

    const uploadPath = path.join(root, 'sub-browser-smoke_T1w.nii.gz');
    await deps.writeMinimalNifti(uploadPath);
    await page.goto(`${consoleBaseUrl}/projects/${projectId}/ingest`);
    const uploadResponsePromise = page.waitForResponse(
      response => response.url().includes(`/projects/${projectId}/upload`) && response.request().method() === 'POST',
      { timeout: 15000 },
    );
    const niftiInput = page.locator('input[aria-label="NIfTI upload"]');
    await niftiInput.setInputFiles(uploadPath);
    await niftiInput.dispatchEvent('change');
    let uploadResponse;
    try {
      uploadResponse = await uploadResponsePromise;
    } catch (error) {
      const filesCount = await niftiInput.evaluate(input => input.files?.length || 0).catch(() => -1);
      const bodyText = await page.locator('body').innerText().catch(() => '');
      throw new Error(
        [
          error instanceof Error ? error.message : String(error),
          `input_files=${filesCount}`,
          `browser_events=${browserEvents.slice(-8).join(' | ') || 'none'}`,
          `body=${bodyText.slice(0, 1200)}`,
        ].join('\n'),
      );
    }
    if (!uploadResponse.ok()) {
      throw new Error(`Browser upload failed: HTTP ${uploadResponse.status()} ${await uploadResponse.text()}`);
    }
    let uploadedSeriesId = 1;
    try {
      const uploadPayload = await uploadResponse.json();
      uploadedSeriesId = Number(uploadPayload?.series?.id || uploadPayload?.series_id || uploadedSeriesId);
    } catch {
      uploadedSeriesId = 1;
    }
    const t1SequenceText = page.getByText('T1w_MPRAGE');
    const firstT1SequenceText =
      typeof t1SequenceText.first === 'function' ? t1SequenceText.first() : t1SequenceText;
    await firstT1SequenceText.waitFor({ timeout: 15000 });

    await page.goto(`${consoleBaseUrl}/projects/${projectId}/agent`);
    if (runtimeSourceQuestion) {
      const sourceMessage = agentMessage || DEFAULT_RUNTIME_SOURCE_MESSAGE;
      await page.getByLabel('Agent query').fill(sourceMessage);
      await page.getByRole('button', { name: 'Send' }).click();
      for (const fragment of RUNTIME_SOURCE_REQUIRED_FRAGMENTS) {
        await page.getByText(fragment).waitFor({ timeout: 20000 });
      }
      await page.getByText('Database and rules').waitFor({ timeout: 10000 });
      return {
        runtimeSource: {
          message: sourceMessage,
          required_fragments: RUNTIME_SOURCE_REQUIRED_FRAGMENTS,
        },
        seed: null,
      };
    }
    if (t1MetricQuestion) {
      const seed = await deps.seedCompletedT1ResultSummary({ projectId, root, seriesId: uploadedSeriesId });
      const metricMessage = agentMessage || DEFAULT_T1_METRIC_MESSAGE;
      await page.getByLabel('Agent query').fill(metricMessage);
      await page.getByRole('button', { name: 'Send' }).click();
      for (const fragment of T1_METRIC_REQUIRED_FRAGMENTS) {
        await page.getByText(fragment).waitFor({ timeout: 20000 });
      }
      await page.getByText('Database and rules').waitFor({ timeout: 10000 });
      return {
        seed,
        t1Metric: {
          message: metricMessage,
          required_fragments: T1_METRIC_REQUIRED_FRAGMENTS,
        },
      };
    }
    if (workflowConfirmationResume) {
      const confirmationMessage = agentMessage || DEFAULT_WORKFLOW_CONFIRMATION_MESSAGE({
        projectId,
        seriesId: uploadedSeriesId,
      });
      await page.getByLabel('Agent query').fill(confirmationMessage);
      await page.getByRole('button', { name: 'Send' }).click();
      await page.getByText('Approve workflow').waitFor({ timeout: 20000 });
      await page.getByText('t1_deepprep_anat_report', { exact: true }).waitFor({ timeout: 20000 });
      await page.getByText('Task not created yet').waitFor({ timeout: 20000 });
      await page.getByRole('button', { name: 'Approve workflow' }).click();
      await page.getByText('created for t1_deepprep_anat_report').waitFor({ timeout: 20000 });
      const task = await deps.waitForCreatedWorkflowTask({ apiBaseUrl, projectId }, deps);
      return {
        seed: null,
        workflowConfirmationResume: {
          message: confirmationMessage,
          series_id: uploadedSeriesId,
          task,
        },
      };
    }

    const seed = await deps.seedRunningT1Task({ projectId, root, seriesId: uploadedSeriesId });
    await page.getByLabel('Agent query').fill(agentMessage);
    await page.getByRole('button', { name: 'Send' }).click();
    for (const fragment of REQUIRED_ANSWER_FRAGMENTS) {
      await page.getByText(fragment).waitFor({ timeout: 20000 });
    }
    for (const fragment of FORBIDDEN_ANSWER_FRAGMENTS) {
      const count = await page.getByText(fragment).count?.();
      if (count) throw new Error(`Agent answer included forbidden fragment: ${fragment}`);
    }
    await page.getByText('Database and rules').waitFor({ timeout: 10000 });
    return { seed };
  } finally {
    await browser.close();
  }
}

export async function runBrowserUploadAgentSmoke(options, injectedDeps = {}) {
  const root = path.resolve(options.root || path.join(tmpdir(), `image-agent-browser-upload-agent-${Date.now()}`));
  await mkdir(root, { recursive: true });
  const deps = {
    createProject,
    launchBrowser,
    requestJson,
    seedCompletedT1ResultSummary,
    seedRunningT1Task,
    startApiServer,
    startConsoleServer,
    waitForCreatedWorkflowTask,
    writeMinimalNifti,
    ...injectedDeps,
  };
  const consolePort = options.consolePort ?? 0;
  const effectiveConsolePort = consolePort > 0 ? consolePort : await freePort();
  const consoleOrigin = `http://127.0.0.1:${effectiveConsolePort}`;
  const apiServer = await deps.startApiServer({ corsOrigin: consoleOrigin, port: options.apiPort ?? options.port ?? 0, root });
  let consoleServer;
  try {
    const project = await deps.createProject({ apiBaseUrl: apiServer.baseUrl });
    consoleServer = await deps.startConsoleServer({ apiBaseUrl: apiServer.baseUrl, port: effectiveConsolePort });
    const flow = await driveBrowserFlow({
      agentMessage: options.workflowConfirmationResume === true || options.runtimeSourceQuestion === true
        || options.t1MetricQuestion === true
        ? options.agentMessage
        : options.agentMessage || DEFAULT_AGENT_MESSAGE,
      apiBaseUrl: apiServer.baseUrl,
      consoleBaseUrl: consoleServer.baseUrl,
      headless: options.headless !== false,
      projectId: project.project_id,
      runtimeSourceQuestion: options.runtimeSourceQuestion === true,
      root,
      t1MetricQuestion: options.t1MetricQuestion === true,
      workflowConfirmationResume: options.workflowConfirmationResume === true,
    }, deps);
    const runtimeSource = flow.runtimeSource || null;
    const t1Metric = flow.t1Metric || null;
    const workflowConfirmationResume = flow.workflowConfirmationResume || null;
    return {
      agent_answer_required_fragments: REQUIRED_ANSWER_FRAGMENTS,
      agent_interaction_status: 'passed_in_browser',
      project,
      root_scope: 'isolated',
      runtime_source: runtimeSource,
      runtime_source_status: runtimeSource ? 'passed_in_browser' : 'not_requested',
      seed_task: flow.seed,
      status: 'passed',
      t1_metric: t1Metric,
      t1_metric_status: t1Metric ? 'passed_in_browser' : 'not_requested',
      upload_status: 'passed_in_browser',
      workflow_confirmation_resume: workflowConfirmationResume,
      workflow_confirmation_resume_status: workflowConfirmationResume ? 'passed_in_browser' : 'not_requested',
    };
  } finally {
    if (consoleServer) await consoleServer.stop();
    await apiServer.stop();
    if (!options.root) await rm(root, { recursive: true, force: true });
  }
}

export function isMainModule(metaUrl, argvPath) {
  return Boolean(argvPath) && metaUrl === pathToFileURL(argvPath).href;
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  const payload = await runBrowserUploadAgentSmoke(args);
  const text = JSON.stringify(payload, null, 2);
  if (args.outputJson) {
    await mkdir(path.dirname(path.resolve(args.outputJson)), { recursive: true });
    await writeFile(args.outputJson, `${text}\n`, 'utf8');
  } else {
    console.log(text);
  }
}

if (isMainModule(import.meta.url, process.argv[1])) {
  main().catch(error => {
    console.error(error instanceof Error ? error.stack || error.message : String(error));
    process.exit(1);
  });
}
