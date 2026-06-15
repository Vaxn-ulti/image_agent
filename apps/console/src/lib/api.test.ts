import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { api, getApiBase } from './api';

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

  it('requests result summaries and artifacts with backend paths', async () => {
    fetchMock
      .mockResolvedValueOnce(new Response(JSON.stringify({ task_id: 4 }), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ artifact: true }), { status: 200 }));
    await api.getResultSummary(4);
    await api.getArtifactUrl(4, 'maps/fa.nii.gz');

    expect(fetchMock.mock.calls[0][0]).toContain('/tasks/4/result-summary');
    expect(fetchMock.mock.calls[1][0]).toContain('/tasks/4/artifacts/maps%2Ffa.nii.gz');
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

  it('preserves backend error text', async () => {
    fetchMock.mockResolvedValueOnce(new Response('DWI JSON sidecar is required', { status: 400 }));
    await expect(api.getTask(99)).rejects.toThrow('DWI JSON sidecar is required');
  });
});
