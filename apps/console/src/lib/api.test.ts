import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { api, getApiBase, getAuthToken, resetApiBase, setApiBase, setAuthToken } from './api';

describe('api client', () => {
  const fetchMock = vi.fn();

  beforeEach(() => {
    localStorage.clear();
    fetchMock.mockReset();
    vi.stubGlobal('fetch', fetchMock);
  });

  afterEach(() => {
    vi.unstubAllEnvs();
    vi.unstubAllGlobals();
  });

  it('defaults the API base to the current host on port 8000', () => {
    expect(getApiBase()).toContain(':8000');
  });

  it('uses the configured Vite API base before falling back to the current host', async () => {
    vi.stubEnv('VITE_API_BASE_URL', 'http://127.0.0.1:8011/');
    vi.resetModules();
    const { getApiBase: getConfiguredApiBase } = await import('./api');

    expect(getConfiguredApiBase()).toBe('http://127.0.0.1:8011');
  });

  it('stores a normalized remote API base and resets to the default host', () => {
    setApiBase('https://image-agent.example.com/');

    expect(getApiBase()).toBe('https://image-agent.example.com');
    expect(localStorage.getItem('apiBase')).toBe('https://image-agent.example.com');

    resetApiBase();

    expect(localStorage.getItem('apiBase')).toBeNull();
    expect(getApiBase()).toContain(':8000');
  });

  it('ignores stale localhost API base when the console is opened from a remote host', () => {
    vi.stubGlobal('location', new URL('http://10.2.32.14:5180/projects/13/results/140'));
    localStorage.setItem('apiBase', 'http://localhost:8000');

    expect(getApiBase()).toBe('http://10.2.32.14:8000');
    expect(localStorage.getItem('apiBase')).toBeNull();
  });

  it('stores login bearer token and sends it on later API requests', async () => {
    fetchMock
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            access_token: 'operator-token',
            token_type: 'bearer',
            user: { id: 1, username: 'operator' },
          }),
          { status: 200 },
        ),
      )
      .mockResolvedValueOnce(new Response(JSON.stringify([]), { status: 200 }));

    await api.login('operator', 'correct-password');
    expect(getAuthToken()).toBe('operator-token');

    await api.listProjects();
    const [, init] = fetchMock.mock.calls[1];
    expect(init.headers).toMatchObject({ Authorization: 'Bearer operator-token' });
  });

  it('clears stale bearer token and asks the operator to log in again on authenticated API 401', async () => {
    setAuthToken('stale-token');
    const authExpired = vi.fn();
    window.addEventListener('image-agent-auth-expired', authExpired);
    fetchMock.mockResolvedValueOnce(
      new Response(JSON.stringify({ detail: 'Authentication required' }), { status: 401 }),
    );

    await expect(api.listProjectTasks(13)).rejects.toThrow('Session expired. Please log in again.');

    expect(getAuthToken()).toBe('');
    expect(authExpired).toHaveBeenCalledTimes(1);
    window.removeEventListener('image-agent-auth-expired', authExpired);
  });

  it('uploads DWI with a JSON sidecar field', async () => {
    fetchMock.mockResolvedValueOnce(new Response(JSON.stringify({ ok: true }), { status: 200 }));
    await api.uploadDwi(7, {
      nifti: new File(['n'], 'sub-01_dwi.nii.gz'),
      bval: new File(['bval'], 'sub-01_dwi.bval'),
      bvec: new File(['bvec'], 'sub-01_dwi.bvec'),
      jsonSidecar: new File(['{}'], 'sub-01_dwi.json'),
    });

    const [, init] = fetchMock.mock.calls[0];
    const form = init.body as FormData;
    expect(form.get('nifti')).toBeInstanceOf(File);
    expect(form.get('bval')).toBeInstanceOf(File);
    expect(form.get('bvec')).toBeInstanceOf(File);
    expect(form.get('json_sidecar')).toBeInstanceOf(File);
  });

  it('strips backend storage paths from upload responses before UI code sees them', async () => {
    const leakedFile = {
      id: 1,
      original_name: 'sub-01_T1w.nii.gz',
      storage_path: '/home/yyf/project/image_agent/data/projects/13/raw/sub-01_T1w.nii.gz',
      file_type: 'NIFTI',
    };
    fetchMock
      .mockResolvedValueOnce(new Response(JSON.stringify({ file: leakedFile, series: { id: 11, project_id: 13 } }), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ files: [leakedFile], series: { id: 12, project_id: 13 } }), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ file: leakedFile, series: { id: 13, project_id: 13 } }), { status: 200 }));

    const standard = await api.uploadNifti(13, new File(['n'], 'sub-01_T1w.nii.gz'));
    const dwi = await api.uploadDwi(13, {
      nifti: new File(['n'], 'sub-01_dwi.nii.gz'),
      bval: new File(['b'], 'sub-01_dwi.bval'),
      bvec: new File(['v'], 'sub-01_dwi.bvec'),
      jsonSidecar: new File(['{}'], 'sub-01_dwi.json'),
    });
    const dicom = await api.uploadDicom(13, new File(['z'], 'dicom.zip'));

    const standardFile = standard.file as Record<string, unknown>;
    const dwiFile = dwi.files[0] as Record<string, unknown>;
    const dicomFile = dicom.file as Record<string, unknown>;
    expect('storage_path' in standardFile).toBe(false);
    expect('storage_path' in dwiFile).toBe(false);
    expect('storage_path' in dicomFile).toBe(false);
    expect(JSON.stringify({ standard, dwi, dicom })).not.toContain('/home/yyf/project/image_agent');
  });

  it('uploads arbitrary files through the generic upload endpoint', async () => {
    fetchMock.mockResolvedValueOnce(
      new Response(
        JSON.stringify({
          file: {
            id: 9,
            original_name: 'operator-notes.txt',
            storage_path: '/home/yyf/project/image_agent/data/projects/13/raw/operator-notes.txt',
          },
          inventory: {
            attachments: [
              {
                original_name: 'operator-notes.txt',
                source: '/home/yyf/project/image_agent/data/projects/13/raw/operator-notes.txt',
              },
            ],
            inventory_status: 'completed',
            series: [],
          },
          series: null,
          status: 'completed',
          upload_session_id: 91,
        }),
        { status: 200 },
      ),
    );

    const uploaded = await api.uploadFile(13, new File(['notes'], 'operator-notes.txt'));

    expect(fetchMock.mock.calls[0][0]).toContain('/projects/13/upload');
    expect((fetchMock.mock.calls[0][1].body as FormData).get('file')).toBeInstanceOf(File);
    expect(uploaded.series).toBeNull();
    expect('storage_path' in (uploaded.file as Record<string, unknown>)).toBe(false);
    expect('source' in (uploaded.inventory?.attachments?.[0] as Record<string, unknown>)).toBe(false);
    expect(JSON.stringify(uploaded)).not.toContain('/home/yyf/project/image_agent');
  });

  it('lists uploaded project files without leaking backend paths', async () => {
    fetchMock.mockResolvedValueOnce(
      new Response(
        JSON.stringify([
          {
            id: 4,
            original_name: 'sub-01_T1w.nii.gz',
            storage_path: '/home/yyf/project/image_agent/data/projects/13/raw/sub-01_T1w.nii.gz',
            file_type: 'NIFTI',
            linked_series: [{ id: 8, modality: 'T1', sequence_label: 'T1w_MPRAGE' }],
          },
        ]),
        { status: 200 },
      ),
    );

    const files = await api.listProjectFiles(13);

    expect(fetchMock.mock.calls[0][0]).toContain('/projects/13/files');
    expect(files[0].linked_series?.[0].modality).toBe('T1');
    expect('storage_path' in (files[0] as Record<string, unknown>)).toBe(false);
    expect(JSON.stringify(files)).not.toContain('/home/yyf/project/image_agent');
  });

  it('deletes uploaded project files through the project scoped endpoint', async () => {
    fetchMock.mockResolvedValueOnce(new Response(JSON.stringify({ deleted_file: { id: 4 }, status: 'deleted' }), { status: 200 }));

    const result = await api.deleteProjectFile(13, 4);

    expect(fetchMock.mock.calls[0][0]).toContain('/projects/13/files/4');
    expect(fetchMock.mock.calls[0][1].method).toBe('DELETE');
    expect(result.status).toBe('deleted');
  });

  it('strips backend paths from ingest inventory responses before UI code sees them', async () => {
    const inventory = {
      inventory_status: 'completed',
      bids_dataset_root: '/home/yyf/project/image_agent/data/projects/13/bids/rawdata',
      dicom: {
        failures: [
          {
            source: '/home/yyf/project/image_agent/data/projects/13/uploads/22/extracted',
            log_tail: 'dcm2niix executable not found',
          },
        ],
      },
      series: [
        {
          series_id: 5,
          bids_path: 'bids/rawdata/sub-01/anat/sub-01_T1w.nii.gz',
          sidecars: ['/home/yyf/project/image_agent/data/projects/13/bids/rawdata/sub-01/anat/sub-01_T1w.json'],
        },
      ],
    };
    fetchMock
      .mockResolvedValueOnce(new Response(JSON.stringify({ inventory }), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ inventory }), { status: 200 }));

    const ingest = await api.ingestDataset(13, 22, new File(['z'], 'dataset.zip'));
    const polled = await api.getInventory(13, 22);

    expect(ingest.inventory?.bids_dataset_root).toBe('bids/rawdata');
    expect(polled.inventory.bids_dataset_root).toBe('bids/rawdata');
    expect('source' in (ingest.inventory?.dicom?.failures?.[0] as Record<string, unknown>)).toBe(false);
    expect('sidecars' in (ingest.inventory?.series?.[0] as Record<string, unknown>)).toBe(false);
    expect(JSON.stringify({ ingest, polled })).not.toContain('/home/yyf/project/image_agent');
  });

  it('requests result summaries and artifacts with backend route paths', async () => {
    fetchMock
      .mockResolvedValueOnce(new Response(JSON.stringify({ task_id: 4 }), { status: 200 }))
      .mockResolvedValueOnce(new Response('FA', { headers: { 'Content-Type': 'application/octet-stream' }, status: 200 }));
    await api.getResultSummary(4);
    const artifact = await api.getArtifactUrl(4, 'maps/fa.nii.gz');

    expect(fetchMock.mock.calls[0][0]).toContain('/tasks/4/result-summary');
    expect(fetchMock.mock.calls[1][0]).toContain('/tasks/4/artifacts/maps/fa.nii.gz');
    expect(artifact).toBeTruthy();
    expect(artifact.size).toBe(2);
    expect(artifact.type).toBe('application/octet-stream');
  });

  it('downloads a completed task export bundle from the backend zip endpoint', async () => {
    fetchMock.mockResolvedValueOnce(new Response('zip', { headers: { 'Content-Type': 'application/zip' }, status: 200 }));

    const bundle = await api.getTaskExportBundle(140);

    expect(fetchMock.mock.calls[0][0]).toContain('/tasks/140/export-bundle');
    expect(bundle.size).toBe(3);
    expect(bundle.type).toBe('application/zip');
  });

  it('creates a native browser export download ticket for large result bundles', async () => {
    fetchMock.mockResolvedValueOnce(
      new Response(
        JSON.stringify({
          download_url: '/tasks/140/export-bundle-download?ticket=abc',
          expires_at: 1780000000,
          task_id: 140,
        }),
        { status: 200 },
      ),
    );

    const ticket = await api.createTaskExportBundleTicket(140);

    expect(fetchMock.mock.calls[0][0]).toContain('/tasks/140/export-bundle-ticket');
    expect(fetchMock.mock.calls[0][1].method).toBe('POST');
    expect(ticket.download_url).toBe('/tasks/140/export-bundle-download?ticket=abc');
  });

  it('clears stale bearer token and asks the operator to log in again on authenticated blob 401', async () => {
    setAuthToken('stale-token');
    fetchMock.mockResolvedValueOnce(
      new Response(JSON.stringify({ detail: 'Authentication required' }), { status: 401 }),
    );

    await expect(api.getTaskExportBundle(140)).rejects.toThrow('Session expired. Please log in again.');

    expect(getAuthToken()).toBe('');
  });

  it('retries blob downloads with the default host API base after a stored API base network failure', async () => {
    window.history.pushState({}, '', '/projects/33/results/140');
    setApiBase('http://stale-api.example.invalid:8000');
    fetchMock
      .mockRejectedValueOnce(new TypeError('Failed to fetch'))
      .mockResolvedValueOnce(new Response('zip', { headers: { 'Content-Type': 'application/zip' }, status: 200 }));

    const bundle = await api.getTaskExportBundle(140);

    expect(fetchMock.mock.calls[0][0]).toBe('http://stale-api.example.invalid:8000/tasks/140/export-bundle');
    expect(fetchMock.mock.calls[1][0]).toContain(':8000/tasks/140/export-bundle');
    expect(localStorage.getItem('apiBase')).toBeNull();
    expect(bundle.size).toBe(3);
  });

  it('strips backend paths from result summaries before UI code sees them', async () => {
    fetchMock.mockResolvedValueOnce(
      new Response(
        JSON.stringify({
          contract_version: 'result_summary.v1',
          feature_groups: ['qc'],
          modality: 'T1',
          outputs: {
            reports: [
              {
                content_type: 'image/png',
                download_url: '/tasks/118/artifacts/reports/qc.png',
                path: '/home/yyf/project/image_agent/data/projects/13/derivatives/118/reports/qc.png',
                provenance: {
                  log_path: '/home/yyf/project/image_agent/data/projects/13/logs/118.log',
                  source_note: 'generated under C:/Users/A/private/work',
                },
                relative_path: 'reports/qc.png',
              },
            ],
          },
          project_id: 13,
          provenance: {
            output_dir: '/home/yyf/project/image_agent/data/projects/13/derivatives/118',
            runtime_note: 'saved under /home/yyf/project/image_agent/private',
          },
          spaces: [],
          summary_path: '/home/yyf/project/image_agent/data/projects/13/derivatives/118/result-summary.json',
          task_id: 118,
          workflow_type: 't1_deepprep_anat_report',
        }),
        { status: 200 },
      ),
    );

    const summary = await api.getResultSummary(118);
    const reports = summary.outputs.reports;
    expect(Array.isArray(reports)).toBe(true);
    const firstOutput = (reports as unknown[])[0] as Record<string, unknown>;
    const serialized = JSON.stringify(summary);

    expect(firstOutput.relative_path).toBe('reports/qc.png');
    expect(firstOutput.download_url).toBe('/tasks/118/artifacts/reports/qc.png');
    expect(firstOutput.content_type).toBe('image/png');
    expect('path' in firstOutput).toBe(false);
    expect('summary_path' in summary).toBe(false);
    expect(serialized).toContain('[redacted-host-path]');
    expect(serialized).not.toContain('/home/yyf/project/image_agent');
    expect(serialized).not.toContain('C:/Users/A/private/work');
    expect(serialized).not.toContain('log_path');
    expect(serialized).not.toContain('output_dir');
  });

  it('requests and sanitizes task artifact manifests before UI code sees them', async () => {
    fetchMock.mockResolvedValueOnce(
      new Response(
        JSON.stringify({
          artifacts: [
            {
              content_type: 'image/png',
              download_url: '/tasks/118/artifacts/qc/native.png',
              native_artifact: true,
              path: '/home/yyf/project/image_agent/data/projects/13/derivatives/118/output/qc/native.png',
              preview_kind: 'image',
              provenance: {
                log_path: '/home/yyf/project/image_agent/data/projects/13/logs/118.log',
                source_note: 'generated under C:/Users/A/private/work',
              },
              relative_path: 'qc/native.png',
              size_bytes: 2048,
            },
          ],
          contract_version: 'artifact_manifest_v1',
          omitted_artifacts: [
            {
              reason: 'unsafe path under /home/yyf/project/image_agent/private',
              path: '/home/yyf/project/image_agent/private/hidden.png',
            },
          ],
          task_id: 118,
        }),
        { status: 200 },
      ),
    );

    const manifest = await api.getArtifactManifest(118);
    const firstArtifact = manifest.artifacts[0];
    const serialized = JSON.stringify(manifest);

    expect(fetchMock.mock.calls[0][0]).toContain('/tasks/118/artifact-manifest');
    expect(manifest.contract_version).toBe('artifact_manifest_v1');
    expect(firstArtifact.relative_path).toBe('qc/native.png');
    expect(firstArtifact.download_url).toBe('/tasks/118/artifacts/qc/native.png');
    expect(firstArtifact.preview_kind).toBe('image');
    expect(firstArtifact.native_artifact).toBe(true);
    expect('path' in firstArtifact).toBe(false);
    expect(serialized).toContain('[redacted-host-path]');
    expect(serialized).not.toContain('/home/yyf/project/image_agent');
    expect(serialized).not.toContain('C:/Users/A/private/work');
    expect(serialized).not.toContain('log_path');
  });

  it('requests and sanitizes read-only ObserveRepair task advice', async () => {
    fetchMock.mockResolvedValueOnce(
      new Response(
        JSON.stringify({
          auto_rerun_allowed: false,
          main_log: {
            tail: 'OPENAI_API_KEY=sk-observe-secret failed at C:/Users/A/private/patient-118',
          },
          policy: 'read_only_observe_repair',
          production_task_created: false,
          remote_logs: [
            {
              name: 'fmriprep.log',
              path: '/home/yyf/project/image_agent/private/logs/fmriprep.log',
              tail: 'remote TOKEN=repair-secret wrote /home/yyf/project/image_agent/private',
            },
          ],
          repair_suggestions: [
            { kind: 'failed_task_repair_plan', message: 'Inspect logs and draft a repair plan.' },
          ],
          requires_human_confirmation_before_retry: true,
          requires_preflight_before_retry: true,
          status: 'ok',
          task: {
            id: 118,
            log_path: '/home/yyf/project/image_agent/data/projects/13/logs/118.log',
            progress: 20,
            project_id: 13,
            status: 'failed',
            workflow_type: 't1_deepprep_anat_report',
          },
          task_id: 118,
        }),
        { status: 200 },
      ),
    );

    const payload = await api.observeRepair(118);
    const serialized = JSON.stringify(payload);

    expect(fetchMock.mock.calls[0][0]).toContain('/tasks/118/observe-repair');
    expect(payload.policy).toBe('read_only_observe_repair');
    expect(payload.auto_rerun_allowed).toBe(false);
    expect(payload.production_task_created).toBe(false);
    expect(payload.requires_preflight_before_retry).toBe(true);
    expect(payload.requires_human_confirmation_before_retry).toBe(true);
    expect(serialized).toContain('[redacted-secret]');
    expect(serialized).toContain('[redacted-host-path]');
    expect(serialized).not.toContain('sk-observe-secret');
    expect(serialized).not.toContain('repair-secret');
    expect(serialized).not.toContain('/home/yyf/project/image_agent');
    expect(serialized).not.toContain('C:/Users/A/private');
    expect(serialized).not.toContain('log_path');
    expect(serialized).not.toContain('"path"');
  });

  it('runs project-scoped Agent chat through the Agent run endpoint', async () => {
    fetchMock.mockResolvedValueOnce(new Response(JSON.stringify({ agent_run_id: 'agent_run_123', answer: 'ok' }), { status: 200 }));

    await api.runAgent(13, 'Summarize this project');

    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toContain('/agent/runs');
    expect(init.method).toBe('POST');
    expect(init.headers).toEqual({ 'Content-Type': 'application/json' });
    expect(JSON.parse(init.body as string)).toEqual({
      message: 'Summarize this project',
      project_id: 13,
    });
  });

  it('redacts backend paths and secrets from Agent run responses before UI code sees them', async () => {
    fetchMock.mockResolvedValueOnce(
      new Response(
        JSON.stringify({
          agent_run_id: 'agent_run_123',
          answer:
            'Evidence reviewed from /home/yyf/project/image_agent/data/projects/13/raw/sub-01.nii.gz and data/projects/13/derivatives/118/output/qc.html',
          citations: [{ path: 'docs/rag/vendor/fsl.md', title: 'FSL' }],
          tool_invocations: [
            {
              result: {
                log_path: '/home/yyf/project/image_agent/data/projects/13/logs/118.log',
                openai_key: 'sk-test-secret',
                safe_doc_path: 'docs/rag/vendor/fsl.md',
                windows_path: 'C:/Users/A/private/task.log',
              },
              status: 'ok',
              tool: 'inspect_task_status',
            },
          ],
        }),
        { status: 200 },
      ),
    );

    const result = await api.runAgent(13, 'Inspect task evidence');
    const serialized = JSON.stringify(result);

    expect(result.citations?.[0].path).toBe('docs/rag/vendor/fsl.md');
    expect(serialized).toContain('[redacted-host-path]');
    expect(serialized).toContain('[redacted-secret]');
    expect(serialized).not.toContain('/home/yyf/project/image_agent');
    expect(serialized).not.toContain('data/projects/13');
    expect(serialized).not.toContain('C:/Users/A/private/task.log');
    expect(serialized).not.toContain('sk-test-secret');
    expect(serialized).not.toContain('log_path');
  });

  it('lists project Agent run history through the safe ledger endpoint', async () => {
    fetchMock.mockResolvedValueOnce(
      new Response(
        JSON.stringify({
          agent_runs: [
            {
              agent_run_id: 'agent_run_history_123',
              created_at: '2026-06-19T10:00:00+00:00',
              event_count: 3,
              model_gateway_access: 'openai_sdk_gateway',
              project_id: 13,
              request_type: 'run',
              safe_metadata: {
                note: 'inspected /home/yyf/project/image_agent/data/projects/13/raw/sub-01.nii.gz with sk-history-secret',
              },
              selected_skill: 'image-agent-operator',
              status: 'answered',
            },
          ],
          contract_version: 'project_agent_run_history.v1',
          project_id: 13,
        }),
        { status: 200 },
      ),
    );

    const history = await api.listProjectAgentRuns(13);
    const serialized = JSON.stringify(history);

    expect(fetchMock.mock.calls[0][0]).toContain('/projects/13/agent-runs');
    expect(history.agent_runs[0].agent_run_id).toBe('agent_run_history_123');
    expect(history.agent_runs[0].selected_skill).toBe('image-agent-operator');
    expect(serialized).toContain('[redacted-host-path]');
    expect(serialized).toContain('[redacted-secret]');
    expect(serialized).not.toContain('/home/yyf/project/image_agent');
    expect(serialized).not.toContain('sk-history-secret');
  });

  it('looks up a single Agent run through the safe ledger endpoint', async () => {
    fetchMock.mockResolvedValueOnce(
      new Response(
        JSON.stringify({
          agent_run_id: 'agent_run_lookup_123',
          answer: 'Reviewed task evidence.',
          contract_version: 'agent_run_lookup.v1',
          created_at: '2026-06-19T10:00:00+00:00',
          events: [
            {
              event_type: 'agent_tool_invoked',
              metadata: {
                note: 'read /home/yyf/project/image_agent/data/projects/13/logs/118.log using sk-lookup-secret',
              },
              status: 'ok',
            },
          ],
          message_sha256: 'abc123',
          project_id: 13,
          selected_skill: 'image-agent-operator',
          status: 'answered',
        }),
        { status: 200 },
      ),
    );

    const lookup = await api.getAgentRun('agent_run_lookup_123');
    const serialized = JSON.stringify(lookup);

    expect(fetchMock.mock.calls[0][0]).toContain('/agent/runs/agent_run_lookup_123');
    expect(lookup.contract_version).toBe('agent_run_lookup.v1');
    expect(lookup.agent_run_id).toBe('agent_run_lookup_123');
    expect(lookup.events?.[0]?.event_type).toBe('agent_tool_invoked');
    expect(serialized).toContain('[redacted-host-path]');
    expect(serialized).toContain('[redacted-secret]');
    expect(serialized).not.toContain('/home/yyf/project/image_agent');
    expect(serialized).not.toContain('sk-lookup-secret');
  });

  it('resumes an Agent workflow confirmation through the explicit resume endpoint', async () => {
    fetchMock.mockResolvedValueOnce(new Response(JSON.stringify({ status: 'task_created', task: { id: 118 } }), { status: 200 }));
    const confirmation = {
      project_id: 13,
      series_id: 24,
      type: 'workflow_execution',
      workflow_type: 'bold_fmriprep_xcpd_report',
    };

    await api.resumeAgent('thread-abc', true, confirmation);

    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toContain('/agent/runs/thread-abc/resume');
    expect(init.method).toBe('POST');
    expect(init.headers).toEqual({ 'Content-Type': 'application/json' });
    expect(JSON.parse(init.body as string)).toEqual({
      approved: true,
      confirmation,
    });
  });

  it('redacts backend paths and secrets from Agent resume and legacy chat responses', async () => {
    fetchMock
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            status: 'task_created',
            task: {
              id: 118,
              log_path: '/home/yyf/project/image_agent/data/projects/13/logs/118.log',
              project_id: 13,
              series_id: 24,
              status: 'queued',
              workflow_type: 'bold_fmriprep_xcpd_report',
            },
            tool_invocations: [{ result: { token: 'sk-test-secret' }, status: 'ok', tool: 'create_workflow_task' }],
          }),
          { status: 200 },
        ),
      )
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            agent_run_id: 'agent_run_redaction',
            answer: 'Agent evidence under C:/Users/A/private/task.log',
            contract_version: 'agent_run_lookup.v1',
            events: [],
            retrieved_sources: [],
            safe_metadata: { secret: 'sk-test-secret' },
            status: 'answered',
            tool_invocations: [{ result: { raw_path: '/home/yyf/project/image_agent/private', secret: 'sk-test-secret' }, status: 'ok', tool: 'agent' }],
          }),
          { status: 200 },
        ),
      );
    const confirmation = {
      project_id: 13,
      series_id: 24,
      type: 'workflow_execution',
      workflow_type: 'bold_fmriprep_xcpd_report',
    };

    const resumed = await api.resumeAgent('thread-abc', true, confirmation);
    const inspected = await api.getAgentRun('agent_run_redaction');
    const serialized = JSON.stringify({ inspected, resumed });

    expect(serialized).toContain('[redacted-host-path]');
    expect(serialized).toContain('[redacted-secret]');
    expect(serialized).not.toContain('/home/yyf/project/image_agent');
    expect(serialized).not.toContain('C:/Users/A/private/task.log');
    expect(serialized).not.toContain('sk-test-secret');
    expect(serialized).not.toContain('log_path');
  });

  it('preserves backend error text', async () => {
    fetchMock.mockResolvedValueOnce(new Response('DWI JSON sidecar is required', { status: 400 }));
    await expect(api.getTask(99)).rejects.toThrow('DWI JSON sidecar is required');
  });

  it('uses backend JSON detail as the user-facing error message', async () => {
    fetchMock.mockResolvedValueOnce(new Response(JSON.stringify({ detail: 'Project not found' }), { status: 404 }));

    await expect(api.listSeries(13)).rejects.toMatchObject({ message: 'Project not found' });
  });

  it('uses structured backend detail.message as the user-facing error message', async () => {
    fetchMock.mockResolvedValueOnce(
      new Response(
        JSON.stringify({
          detail: {
            agent_run_id: 'agent_run_f69242d2a72445aba937ffb73569fd2b',
            code: 'agent_model_call_failed',
            contract_version: 'agent_api_error.v1',
            message: 'Agent model call failed.',
          },
        }),
        { status: 502 },
      ),
    );

    await expect(api.runAgent(13, 'prepare workflow')).rejects.toMatchObject({ message: 'Agent model call failed.' });
  });

  it('strips backend log paths from task responses before UI code sees them', async () => {
    const task = {
      id: 118,
      project_id: 13,
      series_id: 24,
      workflow_type: 'dwi_qsiprep',
      status: 'running',
      progress: 20,
      error_message: 'failed under /home/yyf/project/image_agent/private',
      log_path: '/home/yyf/project/image_agent/data/projects/13/logs/118.log',
    };
    fetchMock
      .mockResolvedValueOnce(new Response(JSON.stringify(task), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify([task]), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify(task), { status: 200 }));

    const created = await api.runSeries(24, 'dwi_qsiprep');
    const list = await api.listProjectTasks(13);
    const detail = await api.getTask(118);

    expect('log_path' in created).toBe(false);
    expect('log_path' in list[0]).toBe(false);
    expect('log_path' in detail).toBe(false);
    expect(JSON.stringify({ created, list, detail })).not.toContain('/home/yyf/project/image_agent');
    expect(JSON.stringify({ created, list, detail })).toContain('[redacted-host-path]');
  });

  it('sanitizes task logs before UI code sees them', async () => {
    fetchMock.mockResolvedValueOnce(
      new Response(
        JSON.stringify({
          task_id: 118,
          text: [
            'Processing subject 01',
            'wrote /home/yyf/project/image_agent/data/projects/13/logs/118.log',
            'cache C:/Users/A/private/work/task-118',
            'artifact data/projects/13/derivatives/118/output/qc.html',
            'OPENAI_API_KEY=sk-task-log-secret',
            'TOKEN=task-log-token',
          ].join('\n'),
        }),
        { status: 200 },
      ),
    );

    const payload = await api.getLogs(118);

    expect(payload.task_id).toBe(118);
    expect(payload.text).toContain('Processing subject 01');
    expect(payload.text).toContain('[redacted-host-path]');
    expect(payload.text).toContain('OPENAI_API_KEY=[redacted-secret]');
    expect(payload.text).toContain('TOKEN=[redacted-secret]');
    expect(payload.text).not.toContain('/home/yyf/project/image_agent');
    expect(payload.text).not.toContain('C:/Users/A/private/work');
    expect(payload.text).not.toContain('data/projects/13');
    expect(payload.text).not.toContain('sk-task-log-secret');
    expect(payload.text).not.toContain('task-log-token');
  });

  it('sanitizes task events before UI code sees them', async () => {
    fetchMock.mockResolvedValueOnce(
      new Response(
        JSON.stringify({
          events: [
            { progress: 20, status: 'running', type: 'task.status' },
            { name: 'fmriprep.log', source_stage: 'fmriprep', type: 'task.remote_log' },
          ],
          main_log: {
            tail: 'OPENAI_API_KEY=sk-task-event-secret failed at C:/Users/A/private/task-118',
          },
          remote_logs: [
            {
              name: 'fmriprep.log',
              path: '/home/yyf/project/image_agent/private/logs/fmriprep.log',
              source_stage: 'fmriprep',
              tail: 'TOKEN=task-event-token wrote data/projects/13/derivatives/118/output',
            },
          ],
          status: 'ok',
          task: {
            id: 118,
            log_path: '/home/yyf/project/image_agent/data/projects/13/logs/118.log',
            progress: 20,
            project_id: 13,
            status: 'running',
            workflow_type: 'bold_fmriprep_xcpd_report',
          },
        }),
        { status: 200 },
      ),
    );

    const payload = await api.getTaskEvents(118);
    const serialized = JSON.stringify(payload);

    expect(fetchMock.mock.calls[0][0]).toContain('/tasks/118/events');
    expect(payload.status).toBe('ok');
    expect(payload.events?.map((event) => event.type)).toEqual(['task.status', 'task.remote_log']);
    expect(payload.main_log?.tail).toContain('[redacted-host-path]');
    expect(payload.remote_logs?.[0]?.source_stage).toBe('fmriprep');
    expect(serialized).toContain('[redacted-secret]');
    expect(serialized).not.toContain('/home/yyf/project/image_agent');
    expect(serialized).not.toContain('C:/Users/A/private');
    expect(serialized).not.toContain('data/projects/13');
    expect(serialized).not.toContain('sk-task-event-secret');
    expect(serialized).not.toContain('task-event-token');
    expect(serialized).not.toContain('log_path');
    expect(serialized).not.toContain('"path"');
  });

  it('strips backend paths from legacy output responses before UI code sees them', async () => {
    fetchMock.mockResolvedValueOnce(
      new Response(
        JSON.stringify([
          {
            id: 9,
            task_id: 118,
            output_type: 'table',
            path: '/home/yyf/project/image_agent/data/projects/13/derivatives/118/output/tables/fa.tsv',
            preview_path: '/home/yyf/project/image_agent/data/projects/13/derivatives/118/output/preview.png',
            relative_path: 'tables/fa.tsv',
            download_url: '/tasks/118/artifacts/tables/fa.tsv',
            metadata: {
              kind: 'qc_table',
              path: '/home/yyf/project/image_agent/data/private.tsv',
              preview_path: '/home/yyf/project/image_agent/data/private.png',
              nested: { log_path: '/home/yyf/project/image_agent/data/task.log' },
            },
          },
        ]),
        { status: 200 },
      ),
    );

    const outputs = await api.getOutputs(118);
    const first = outputs[0] as Record<string, unknown>;
    const serialized = JSON.stringify(outputs);

    expect(first.relative_path).toBe('tables/fa.tsv');
    expect(first.download_url).toBe('/tasks/118/artifacts/tables/fa.tsv');
    expect('path' in first).toBe(false);
    expect('preview_path' in first).toBe(false);
    expect(serialized).not.toContain('/home/yyf/project/image_agent');
  });

  it('sanitizes deployment readiness evidence before UI code sees it', async () => {
    fetchMock.mockResolvedValueOnce(
      new Response(
        JSON.stringify({
          backend_runtime_mode: 'remote',
          fast_launch_readiness: {
            checks: {
              rag_elasticsearch_hybrid: {
                blocking_codes: ['rag_hybrid_lexical_retriever_not_standard'],
                dense_vector_field: 'dense',
                embedding_endpoint: 'https://embeddings.example.internal/v1/embeddings',
                embedding_endpoint_configured: false,
                embedding_error: 'OPENAI_API_KEY=sk-deployment-secret failed under /home/yyf/project/image_agent/private',
                official_rrf_source_present: false,
                official_sources: [
                  'https://www.elastic.co/docs/reference/elasticsearch/rest-apis/reciprocal-rank-fusion',
                ],
                raw_snapshots: ['/home/yyf/project/image_agent/docs/rag/vendor/raw-sources/elastic_rrf.html'],
                status: 'blocked',
              },
            },
            ready: false,
            status: 'blocked',
          },
          production_readiness: {
            blocking_reasons: ['Check /home/yyf/project/image_agent/.env and sk-deployment-secret'],
            ready: false,
            status: 'blocked',
          },
        }),
        { status: 200 },
      ),
    );

    const deployment = await api.deployment();
    const rag = deployment.fast_launch_readiness?.checks?.rag_elasticsearch_hybrid as Record<string, unknown>;
    const serialized = JSON.stringify(deployment);

    expect(rag.blocking_codes).toEqual(['rag_hybrid_lexical_retriever_not_standard']);
    expect(rag.dense_vector_field).toBe('dense');
    expect('official_sources' in rag).toBe(false);
    expect('raw_snapshots' in rag).toBe(false);
    expect('embedding_endpoint' in rag).toBe(false);
    expect(serialized).toContain('[redacted-host-path]');
    expect(serialized).toContain('[redacted-secret]');
    expect(serialized).not.toContain('reciprocal-rank-fusion');
    expect(serialized).not.toContain('/home/yyf/project/image_agent');
    expect(serialized).not.toContain('sk-deployment-secret');
    expect(serialized).not.toContain('embeddings.example.internal');
  });
});
