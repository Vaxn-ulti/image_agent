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
const REQUIRED_ANSWER_FRAGMENTS = ['项目状态概览', '任务 #', '只读观察'];
const FORBIDDEN_ANSWER_FRAGMENTS = ['Tasks:', 'Model gateway is not configured'];

function parseArgs(argv) {
  const args = {
    agentMessage: DEFAULT_AGENT_MESSAGE,
    apiPort: 0,
    consolePort: 0,
    headless: true,
    outputJson: '',
    root: '',
  };
  for (let index = 0; index < argv.length; index += 1) {
    const arg = argv[index];
    if (arg === '--headed') {
      args.headless = false;
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

async function driveBrowserFlow({ agentMessage, apiBaseUrl, consoleBaseUrl, headless, projectId, root }, deps) {
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
    await page.getByText('T1w_MPRAGE').waitFor({ timeout: 15000 });
    const seed = await deps.seedRunningT1Task({ projectId, root, seriesId: 1 });

    await page.goto(`${consoleBaseUrl}/projects/${projectId}/agent`);
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
    seedRunningT1Task,
    startApiServer,
    startConsoleServer,
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
      agentMessage: options.agentMessage || DEFAULT_AGENT_MESSAGE,
      apiBaseUrl: apiServer.baseUrl,
      consoleBaseUrl: consoleServer.baseUrl,
      headless: options.headless !== false,
      projectId: project.project_id,
      root,
    }, deps);
    return {
      agent_answer_required_fragments: REQUIRED_ANSWER_FRAGMENTS,
      agent_interaction_status: 'passed_in_browser',
      project,
      root_scope: 'isolated',
      seed_task: flow.seed,
      status: 'passed',
      upload_status: 'passed_in_browser',
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
