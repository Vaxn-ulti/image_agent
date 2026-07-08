import { describe, expect, it, vi } from 'vitest';
import { isMainModule, parseArgs, runBrowserUploadAgentSmoke } from './browser_upload_agent_smoke.mjs';

function createFakePage(actions) {
  const locator = (kind, value) => ({
    async click() {
      actions.push(['click', kind, value]);
    },
    async dispatchEvent(eventName) {
      actions.push(['dispatchEvent', kind, value, eventName]);
    },
    async evaluate() {
      actions.push(['evaluate', kind, value]);
      return 1;
    },
    async fill(text) {
      actions.push(['fill', kind, value, text]);
    },
    async setInputFiles(filePath) {
      actions.push(['setInputFiles', kind, value, filePath.endsWith('sub-browser-smoke_T1w.nii.gz')]);
    },
    async waitFor() {
      actions.push(['waitFor', kind, value]);
    },
    async innerText() {
      actions.push(['innerText', kind, value]);
      return '';
    },
  });
  return {
    async addInitScript(_fn, value) {
      actions.push(['addInitScript', value]);
    },
    getByLabel: (label) => locator('label', label),
    getByRole: (role, options) => locator('role', `${role}:${options?.name || ''}`),
    getByText: (text) => locator('text', String(text)),
    locator: (selector) => locator('selector', selector),
    async goto(url) {
      actions.push(['goto', url]);
    },
    on(eventName) {
      actions.push(['page.on', eventName]);
    },
    async waitForURL(url) {
      actions.push(['waitForURL', url]);
    },
    async waitForResponse() {
      actions.push(['waitForResponse', 'upload']);
      return {
        ok: () => true,
      };
    },
  };
}

describe('browser_upload_agent_smoke', () => {
  it('detects direct CLI execution on Windows paths', () => {
    expect(
      isMainModule(
        'file:///C:/Users/A/Documents/New%20project%202/apps/console/scripts/browser_upload_agent_smoke.mjs',
        'C:\\Users\\A\\Documents\\New project 2\\apps\\console\\scripts\\browser_upload_agent_smoke.mjs',
      ),
    ).toBe(true);
  });

  it('keeps workflow confirmation CLI mode on the generated approval message', () => {
    const args = parseArgs(['--workflow-confirmation-resume']);

    expect(args.workflowConfirmationResume).toBe(true);
    expect(args.agentMessage).toBe('');
  });

  it('keeps workflow quick-action CLI mode on browser button confirmation', () => {
    const args = parseArgs(['--workflow-quick-action-resume']);

    expect(args.workflowConfirmationResume).toBe(true);
    expect(args.workflowQuickActionResume).toBe(true);
    expect(args.agentMessage).toBe('');
  });

  it('keeps workflow quick-action-after-chat CLI mode on browser button confirmation after a prior message', () => {
    const args = parseArgs(['--workflow-quick-action-after-chat-resume']);

    expect(args.workflowConfirmationResume).toBe(true);
    expect(args.workflowQuickActionResume).toBe(true);
    expect(args.workflowQuickActionAfterChat).toBe(true);
    expect(args.agentMessage).toBe('');
  });

  it('keeps runtime source CLI mode on its generated source question', () => {
    const args = parseArgs(['--runtime-source-question']);

    expect(args.runtimeSourceQuestion).toBe(true);
    expect(args.agentMessage).toBe('');
  });

  it('keeps T1 metric CLI mode on its generated metric question', () => {
    const args = parseArgs(['--t1-metric-question']);

    expect(args.t1MetricQuestion).toBe(true);
    expect(args.agentMessage).toBe('');
  });

  it('keeps modality-confusion CLI mode on its generated boundary question', () => {
    const args = parseArgs(['--modality-confusion-question']);

    expect(args.modalityConfusionQuestion).toBe(true);
    expect(args.agentMessage).toBe('');
  });

  it('drives login, NIfTI file input upload, and Agent current-data chat through the browser', async () => {
    const actions = [];
    const page = createFakePage(actions);
    const browser = {
      async close() {
        actions.push(['browser.close']);
      },
      async newPage() {
        actions.push(['browser.newPage']);
        return page;
      },
    };
    const deps = {
      async createProject() {
        actions.push(['createProject']);
        return { project_id: 1 };
      },
      async launchBrowser() {
        actions.push(['launchBrowser']);
        return browser;
      },
      async seedRunningT1Task({ projectId, root, seriesId }) {
        actions.push(['seedTask', root.endsWith('isolated-root'), projectId, seriesId]);
        return { progress: 35, status: 'running', task_id: 9001, workflow_type: 't1_deepprep_anat_report' };
      },
      async startApiServer({ root }) {
        actions.push(['startApi', root.endsWith('isolated-root')]);
        return { baseUrl: 'http://api.local', stop: vi.fn(async () => actions.push(['stopApi'])) };
      },
      async startConsoleServer({ apiBaseUrl }) {
        actions.push(['startConsole', apiBaseUrl]);
        return { baseUrl: 'http://console.local', stop: vi.fn(async () => actions.push(['stopConsole'])) };
      },
      async writeMinimalNifti(filePath) {
        actions.push(['writeNifti', filePath.endsWith('sub-browser-smoke_T1w.nii.gz')]);
      },
    };

    const result = await runBrowserUploadAgentSmoke(
      {
        agentMessage: '替我分析一下现在的数据',
        headless: true,
        port: 8123,
        root: 'C:/tmp/isolated-root',
      },
      deps,
    );

    expect(result.status).toBe('passed');
    expect(result.upload_status).toBe('passed_in_browser');
    expect(result.agent_interaction_status).toBe('passed_in_browser');
    expect(result.agent_answer_required_fragments).toEqual(['项目状态概览', '任务 #', '只读观察']);
    expect(actions).toContainEqual(['addInitScript', 'http://api.local']);
    expect(actions).toContainEqual(['waitForResponse', 'upload']);
    expect(actions).toContainEqual(['setInputFiles', 'selector', 'input[aria-label="NIfTI upload"]', true]);
    expect(actions).toContainEqual(['dispatchEvent', 'selector', 'input[aria-label="NIfTI upload"]', 'change']);
    expect(actions).toContainEqual(['waitFor', 'text', 'T1w_MPRAGE']);
    expect(actions).toContainEqual(['fill', 'label', 'Agent query', '替我分析一下现在的数据']);
    expect(actions).toContainEqual(['waitFor', 'text', 'Database and rules']);
    expect(actions).toContainEqual(['stopConsole']);
    expect(actions).toContainEqual(['stopApi']);
  });

  it('drives upload, Agent workflow confirmation, and approval resume through the browser', async () => {
    const actions = [];
    const page = createFakePage(actions);
    const browser = {
      async close() {
        actions.push(['browser.close']);
      },
      async newPage() {
        actions.push(['browser.newPage']);
        return page;
      },
    };
    const deps = {
      async createProject() {
        actions.push(['createProject']);
        return { project_id: 1 };
      },
      async launchBrowser() {
        actions.push(['launchBrowser']);
        return browser;
      },
      async requestJson(method, url) {
        actions.push(['requestJson', method, url]);
        return [
          { id: 9101, project_id: 1, series_id: 1, status: 'queued', workflow_type: 't1_deepprep_anat_report' },
        ];
      },
      async seedRunningT1Task() {
        actions.push(['seedTask']);
        throw new Error('workflow confirmation resume smoke must not seed an existing task');
      },
      async startApiServer({ root }) {
        actions.push(['startApi', root.endsWith('isolated-root')]);
        return { baseUrl: 'http://api.local', stop: vi.fn(async () => actions.push(['stopApi'])) };
      },
      async startConsoleServer({ apiBaseUrl }) {
        actions.push(['startConsole', apiBaseUrl]);
        return { baseUrl: 'http://console.local', stop: vi.fn(async () => actions.push(['stopConsole'])) };
      },
      async writeMinimalNifti(filePath) {
        actions.push(['writeNifti', filePath.endsWith('sub-browser-smoke_T1w.nii.gz')]);
      },
    };

    const result = await runBrowserUploadAgentSmoke(
      {
        headless: true,
        root: 'C:/tmp/isolated-root',
        workflowConfirmationResume: true,
      },
      deps,
    );

    expect(result.status).toBe('passed');
    expect(result.workflow_confirmation_resume_status).toBe('passed_in_browser');
    expect(result.seed_task).toBeNull();
    expect(actions).not.toContainEqual(['seedTask']);
    expect(actions).toContainEqual([
      'fill',
      'label',
      'Agent query',
      '请为项目1的序列1准备 t1_deepprep_anat_report 工作流确认，不要创建或启动任务',
    ]);
    expect(actions).toContainEqual(['waitFor', 'text', 'Approve workflow']);
    expect(actions).toContainEqual(['waitFor', 'text', 't1_deepprep_anat_report']);
    expect(actions).toContainEqual(['click', 'role', 'button:Approve workflow']);
    expect(actions).toContainEqual(['waitFor', 'text', 'created for t1_deepprep_anat_report']);
    expect(actions).toContainEqual(['requestJson', 'GET', 'http://api.local/projects/1/tasks']);
  });

  it('drives upload, Agent workflow quick action, and approval resume through the browser', async () => {
    const actions = [];
    const page = createFakePage(actions);
    const browser = {
      async close() {
        actions.push(['browser.close']);
      },
      async newPage() {
        actions.push(['browser.newPage']);
        return page;
      },
    };
    const deps = {
      async createProject() {
        actions.push(['createProject']);
        return { project_id: 1 };
      },
      async launchBrowser() {
        actions.push(['launchBrowser']);
        return browser;
      },
      async requestJson(method, url) {
        actions.push(['requestJson', method, url]);
        return [
          { id: 9102, project_id: 1, series_id: 1, status: 'queued', workflow_type: 't1_deepprep_anat_report' },
        ];
      },
      async seedRunningT1Task() {
        actions.push(['seedTask']);
        throw new Error('workflow quick-action resume smoke must not seed an existing task');
      },
      async startApiServer({ root }) {
        actions.push(['startApi', root.endsWith('isolated-root')]);
        return { baseUrl: 'http://api.local', stop: vi.fn(async () => actions.push(['stopApi'])) };
      },
      async startConsoleServer({ apiBaseUrl }) {
        actions.push(['startConsole', apiBaseUrl]);
        return { baseUrl: 'http://console.local', stop: vi.fn(async () => actions.push(['stopConsole'])) };
      },
      async writeMinimalNifti(filePath) {
        actions.push(['writeNifti', filePath.endsWith('sub-browser-smoke_T1w.nii.gz')]);
      },
    };

    const result = await runBrowserUploadAgentSmoke(
      {
        headless: true,
        root: 'C:/tmp/isolated-root',
        workflowConfirmationResume: true,
        workflowQuickActionResume: true,
      },
      deps,
    );

    expect(result.status).toBe('passed');
    expect(result.workflow_confirmation_resume_status).toBe('passed_in_browser');
    expect(result.workflow_confirmation_resume.mode).toBe('quick_action');
    expect(result.seed_task).toBeNull();
    expect(actions).not.toContainEqual(['seedTask']);
    expect(actions).not.toContainEqual([
      'fill',
      'label',
      'Agent query',
      '请为项目1的序列1准备 t1_deepprep_anat_report 工作流确认，不要创建或启动任务',
    ]);
    expect(actions).toContainEqual(['click', 'role', 'button:Prepare T1 DeepPrep confirmation for series 1']);
    expect(actions).toContainEqual(['waitFor', 'text', 'Approve workflow']);
    expect(actions).toContainEqual(['waitFor', 'text', 't1_deepprep_anat_report']);
    expect(actions).toContainEqual(['waitFor', 'text', 'Task not created yet']);
    expect(actions).toContainEqual(['click', 'role', 'button:Approve workflow']);
    expect(actions).toContainEqual(['waitFor', 'text', 'created for t1_deepprep_anat_report']);
    expect(actions).toContainEqual(['requestJson', 'GET', 'http://api.local/projects/1/tasks']);
  });

  it('drives a prior Agent message before using the workflow quick action', async () => {
    const actions = [];
    const page = createFakePage(actions);
    const browser = {
      async close() {
        actions.push(['browser.close']);
      },
      async newPage() {
        actions.push(['browser.newPage']);
        return page;
      },
    };
    const deps = {
      async createProject() {
        actions.push(['createProject']);
        return { project_id: 1 };
      },
      async launchBrowser() {
        actions.push(['launchBrowser']);
        return browser;
      },
      async requestJson(method, url) {
        actions.push(['requestJson', method, url]);
        return [
          { id: 9103, project_id: 1, series_id: 1, status: 'queued', workflow_type: 't1_deepprep_anat_report' },
        ];
      },
      async seedRunningT1Task() {
        actions.push(['seedTask']);
        throw new Error('workflow quick-action-after-chat smoke must not seed an existing task');
      },
      async startApiServer({ root }) {
        actions.push(['startApi', root.endsWith('isolated-root')]);
        return { baseUrl: 'http://api.local', stop: vi.fn(async () => actions.push(['stopApi'])) };
      },
      async startConsoleServer({ apiBaseUrl }) {
        actions.push(['startConsole', apiBaseUrl]);
        return { baseUrl: 'http://console.local', stop: vi.fn(async () => actions.push(['stopConsole'])) };
      },
      async writeMinimalNifti(filePath) {
        actions.push(['writeNifti', filePath.endsWith('sub-browser-smoke_T1w.nii.gz')]);
      },
    };

    const result = await runBrowserUploadAgentSmoke(
      {
        headless: true,
        root: 'C:/tmp/isolated-root',
        workflowConfirmationResume: true,
        workflowQuickActionAfterChat: true,
        workflowQuickActionResume: true,
      },
      deps,
    );

    expect(result.status).toBe('passed');
    expect(result.workflow_confirmation_resume_status).toBe('passed_in_browser');
    expect(result.workflow_confirmation_resume.mode).toBe('quick_action_after_chat');
    expect(result.workflow_confirmation_resume.prior_message).toBe('你现在是基于规则脚本回答，还是基于LLM在回答');
    expect(result.seed_task).toBeNull();
    expect(actions).not.toContainEqual(['seedTask']);
    expect(actions).toContainEqual([
      'fill',
      'label',
      'Agent query',
      '你现在是基于规则脚本回答，还是基于LLM在回答',
    ]);
    expect(actions).toContainEqual(['waitFor', 'text', '这次回答来源：后端规则和运行状态检查']);
    expect(actions).toContainEqual(['click', 'role', 'button:Prepare T1 DeepPrep confirmation for series 1']);
    expect(actions).toContainEqual(['click', 'role', 'button:Approve workflow']);
    expect(actions).toContainEqual(['requestJson', 'GET', 'http://api.local/projects/1/tasks']);
  });

  it('drives upload and Agent runtime-source transparency through the browser', async () => {
    const actions = [];
    const page = createFakePage(actions);
    const browser = {
      async close() {
        actions.push(['browser.close']);
      },
      async newPage() {
        actions.push(['browser.newPage']);
        return page;
      },
    };
    const deps = {
      async createProject() {
        actions.push(['createProject']);
        return { project_id: 1 };
      },
      async launchBrowser() {
        actions.push(['launchBrowser']);
        return browser;
      },
      async seedRunningT1Task() {
        actions.push(['seedTask']);
        throw new Error('runtime source smoke must not seed a task');
      },
      async startApiServer({ root }) {
        actions.push(['startApi', root.endsWith('isolated-root')]);
        return { baseUrl: 'http://api.local', stop: vi.fn(async () => actions.push(['stopApi'])) };
      },
      async startConsoleServer({ apiBaseUrl }) {
        actions.push(['startConsole', apiBaseUrl]);
        return { baseUrl: 'http://console.local', stop: vi.fn(async () => actions.push(['stopConsole'])) };
      },
      async writeMinimalNifti(filePath) {
        actions.push(['writeNifti', filePath.endsWith('sub-browser-smoke_T1w.nii.gz')]);
      },
    };

    const result = await runBrowserUploadAgentSmoke(
      {
        headless: true,
        root: 'C:/tmp/isolated-root',
        runtimeSourceQuestion: true,
      },
      deps,
    );

    expect(result.status).toBe('passed');
    expect(result.runtime_source_status).toBe('passed_in_browser');
    expect(result.seed_task).toBeNull();
    expect(actions).not.toContainEqual(['seedTask']);
    expect(actions).toContainEqual([
      'fill',
      'label',
      'Agent query',
      '你现在是基于规则脚本回答，还是基于LLM在回答',
    ]);
    expect(actions).toContainEqual(['waitFor', 'text', '这次回答来源：后端规则和运行状态检查']);
    expect(actions).toContainEqual(['waitFor', 'text', '当前模型网关']);
    expect(actions).toContainEqual(['waitFor', 'text', 'Database and rules']);
  });

  it('drives upload, completed T1 result evidence, and Agent T1 metric explanation through the browser', async () => {
    const actions = [];
    const page = createFakePage(actions);
    const browser = {
      async close() {
        actions.push(['browser.close']);
      },
      async newPage() {
        actions.push(['browser.newPage']);
        return page;
      },
    };
    const deps = {
      async createProject() {
        actions.push(['createProject']);
        return { project_id: 1 };
      },
      async launchBrowser() {
        actions.push(['launchBrowser']);
        return browser;
      },
      async seedCompletedT1ResultSummary({ projectId, root, seriesId }) {
        actions.push(['seedCompletedT1', root.endsWith('isolated-root'), projectId, seriesId]);
        return { task_id: 9140, workflow_type: 't1_deepprep_anat_report' };
      },
      async seedRunningT1Task() {
        actions.push(['seedTask']);
        throw new Error('T1 metric smoke must not seed a running task');
      },
      async startApiServer({ root }) {
        actions.push(['startApi', root.endsWith('isolated-root')]);
        return { baseUrl: 'http://api.local', stop: vi.fn(async () => actions.push(['stopApi'])) };
      },
      async startConsoleServer({ apiBaseUrl }) {
        actions.push(['startConsole', apiBaseUrl]);
        return { baseUrl: 'http://console.local', stop: vi.fn(async () => actions.push(['stopConsole'])) };
      },
      async writeMinimalNifti(filePath) {
        actions.push(['writeNifti', filePath.endsWith('sub-browser-smoke_T1w.nii.gz')]);
      },
    };

    const result = await runBrowserUploadAgentSmoke(
      {
        headless: true,
        root: 'C:/tmp/isolated-root',
        t1MetricQuestion: true,
      },
      deps,
    );

    expect(result.status).toBe('passed');
    expect(result.t1_metric_status).toBe('passed_in_browser');
    expect(result.seed_task).toEqual({ task_id: 9140, workflow_type: 't1_deepprep_anat_report' });
    expect(actions).not.toContainEqual(['seedTask']);
    expect(actions).toContainEqual(['seedCompletedT1', true, 1, 1]);
    expect(actions).toContainEqual([
      'fill',
      'label',
      'Agent query',
      '给我分析一下t1提取出来的指标，综合水平怎么样，符不符合正常水平',
    ]);
    expect(actions).toContainEqual(['waitFor', 'text', 'T1 结构化结果解读']);
    expect(actions).toContainEqual(['waitFor', 'text', 'BrainSegVol']);
    expect(actions).toContainEqual(['waitFor', 'text', '不能仅凭这些输出判断正常或异常']);
    expect(actions).toContainEqual(['waitFor', 'text', 'Database and rules']);
  });

  it('drives upload, T1-only Yeo label evidence, and Agent modality-boundary clarification through the browser', async () => {
    const actions = [];
    const page = createFakePage(actions);
    const browser = {
      async close() {
        actions.push(['browser.close']);
      },
      async newPage() {
        actions.push(['browser.newPage']);
        return page;
      },
    };
    const deps = {
      async createProject() {
        actions.push(['createProject']);
        return { project_id: 1 };
      },
      async launchBrowser() {
        actions.push(['launchBrowser']);
        return browser;
      },
      async seedCompletedT1ModalityBoundary({ projectId, root, seriesId }) {
        actions.push(['seedCompletedT1Boundary', root.endsWith('isolated-root'), projectId, seriesId]);
        return { task_id: 9141, workflow_type: 't1_deepprep_anat_report' };
      },
      async seedRunningT1Task() {
        actions.push(['seedTask']);
        throw new Error('modality-boundary smoke must not seed a running task');
      },
      async startApiServer({ root }) {
        actions.push(['startApi', root.endsWith('isolated-root')]);
        return { baseUrl: 'http://api.local', stop: vi.fn(async () => actions.push(['stopApi'])) };
      },
      async startConsoleServer({ apiBaseUrl }) {
        actions.push(['startConsole', apiBaseUrl]);
        return { baseUrl: 'http://console.local', stop: vi.fn(async () => actions.push(['stopConsole'])) };
      },
      async writeMinimalNifti(filePath) {
        actions.push(['writeNifti', filePath.endsWith('sub-browser-smoke_T1w.nii.gz')]);
      },
    };

    const result = await runBrowserUploadAgentSmoke(
      {
        headless: true,
        modalityConfusionQuestion: true,
        root: 'C:/tmp/isolated-root',
      },
      deps,
    );

    expect(result.status).toBe('passed');
    expect(result.modality_confusion_status).toBe('passed_in_browser');
    expect(result.seed_task).toEqual({ task_id: 9141, workflow_type: 't1_deepprep_anat_report' });
    expect(actions).not.toContainEqual(['seedTask']);
    expect(actions).toContainEqual(['seedCompletedT1Boundary', true, 1, 1]);
    expect(actions).toContainEqual([
      'fill',
      'label',
      'Agent query',
      '我都没上传bold资料和DTI资料，为什么会跑这些步骤',
    ]);
    expect(actions).toContainEqual(['waitFor', 'text', '没有运行 BOLD 或 DWI 工作流']);
    expect(actions).toContainEqual(['waitFor', 'text', '当前只登记到 T1 序列']);
    expect(actions).toContainEqual(['waitFor', 'text', 'Yeo']);
    expect(actions).toContainEqual(['waitFor', 'text', '不是基于 BOLD 计算的功能连接']);
    expect(actions).toContainEqual(['waitFor', 'text', '不是 DTI']);
    expect(actions).toContainEqual(['waitFor', 'text', 'Database and rules']);
  });
});
