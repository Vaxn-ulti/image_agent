import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { api, getApiBase, resetApiBase, setApiBase } from './api';

describe('api client', () => {
  const fetchMock = vi.fn();

  beforeEach(() => {
    localStorage.clear();
    fetchMock.mockReset();
    vi.stubGlobal('fetch', fetchMock);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('defaults the API base to the current host on port 8000', () => {
    expect(getApiBase()).toContain(':8000');
  });

  it('stores a normalized remote API base and resets to the default host', () => {
    setApiBase('https://image-agent.example.com/');

    expect(getApiBase()).toBe('https://image-agent.example.com');
    expect(localStorage.getItem('apiBase')).toBe('https://image-agent.example.com');

    resetApiBase();

    expect(localStorage.getItem('apiBase')).toBeNull();
    expect(getApiBase()).toContain(':8000');
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
    expect(artifact).toBeInstanceOf(Blob);
    expect(artifact.size).toBe(2);
    expect(artifact.type).toBe('application/octet-stream');
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
            reply: 'Legacy evidence under C:/Users/A/private/task.log',
            tool_invocations: [{ result: { raw_path: '/home/yyf/project/image_agent/private', secret: 'sk-test-secret' }, status: 'ok', tool: 'legacy' }],
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
    const chat = await api.chat(13, 'Fallback status');
    const serialized = JSON.stringify({ chat, resumed });

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
});
