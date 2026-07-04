import assert from "node:assert/strict";
import test from "node:test";

globalThis.window = { location: { hostname: "localhost", protocol: "http:" } };
globalThis.localStorage = {
  getItem() {
    return null;
  },
};

const { api } = await import("./api.js");

test("desktop DWI upload includes the required JSON sidecar field", async () => {
  let submittedForm;
  globalThis.fetch = async (_url, init) => {
    submittedForm = init.body;
    return new Response(JSON.stringify({ files: [], series: { id: 24, modality: "DWI" } }), { status: 200 });
  };

  await api.uploadDwi(
    13,
    new File(["n"], "sub-01_dwi.nii.gz"),
    new File(["b"], "sub-01_dwi.bval"),
    new File(["v"], "sub-01_dwi.bvec"),
    new File(['{"PhaseEncodingDirection":"j"}'], "sub-01_dwi.json", { type: "application/json" }),
  );

  assert.ok(submittedForm instanceof FormData);
  assert.ok(submittedForm.get("nifti") instanceof File);
  assert.ok(submittedForm.get("bval") instanceof File);
  assert.ok(submittedForm.get("bvec") instanceof File);
  assert.ok(submittedForm.get("json_sidecar") instanceof File);
});

test("desktop deployment response strips unsafe readiness evidence before UI code sees it", async () => {
  globalThis.fetch = async () => new Response(
    JSON.stringify({
      backend_runtime_mode: "remote",
      fast_launch_readiness: {
        checks: {
          rag_elasticsearch_hybrid: {
            blocking_codes: ["rag_hybrid_lexical_retriever_not_standard"],
            dense_vector_field: "dense",
            embedding_endpoint: "https://embeddings.example.internal/v1/embeddings",
            embedding_error: "OPENAI_API_KEY=sk-desktop-secret failed under /home/yyf/project/image_agent/private",
            official_rrf_source_present: false,
            official_sources: [
              "https://www.elastic.co/docs/reference/elasticsearch/rest-apis/reciprocal-rank-fusion",
            ],
            raw_snapshots: ["/home/yyf/project/image_agent/docs/rag/vendor/raw-sources/elastic_rrf.html"],
            status: "blocked",
          },
        },
        ready: false,
        status: "blocked",
      },
      production_readiness: {
        blocking_reasons: ["Check /home/yyf/project/image_agent/.env and sk-desktop-secret"],
        ready: false,
        status: "blocked",
      },
    }),
    { status: 200 },
  );

  const deployment = await api.deployment();
  const rag = deployment.fast_launch_readiness.checks.rag_elasticsearch_hybrid;
  const serialized = JSON.stringify(deployment);

  assert.deepEqual(rag.blocking_codes, ["rag_hybrid_lexical_retriever_not_standard"]);
  assert.equal(rag.dense_vector_field, "dense");
  assert.equal("official_sources" in rag, false);
  assert.equal("raw_snapshots" in rag, false);
  assert.equal("embedding_endpoint" in rag, false);
  assert.match(serialized, /\[redacted-host-path\]/);
  assert.match(serialized, /\[redacted-secret\]/);
  assert.doesNotMatch(serialized, /reciprocal-rank-fusion/);
  assert.doesNotMatch(serialized, /\/home\/yyf\/project\/image_agent/);
  assert.doesNotMatch(serialized, /sk-desktop-secret/);
  assert.doesNotMatch(serialized, /embeddings\.example\.internal/);
});

test("desktop result summary strips backend paths and secrets before UI code sees it", async () => {
  globalThis.fetch = async () => new Response(
    JSON.stringify({
      contract_version: "result_summary.v1",
      outputs: {
        reports: [
          {
            content_type: "image/png",
            download_url: "/tasks/118/artifacts/reports/qc.png",
            path: "/home/yyf/project/image_agent/data/projects/13/derivatives/118/reports/qc.png",
            provenance: {
              log_path: "/home/yyf/project/image_agent/data/projects/13/logs/118.log",
              note: "OPENAI_API_KEY=sk-result-secret wrote C:/Users/A/private/report",
            },
            relative_path: "reports/qc.png",
          },
        ],
      },
      project_id: 13,
      summary_path: "/home/yyf/project/image_agent/data/projects/13/derivatives/118/result-summary.json",
      task_id: 118,
      workflow_type: "t1_deepprep_anat_report",
    }),
    { status: 200 },
  );

  const summary = await api.getResultSummary(118);
  const firstReport = summary.outputs.reports[0];
  const serialized = JSON.stringify(summary);

  assert.equal(firstReport.relative_path, "reports/qc.png");
  assert.equal(firstReport.download_url, "/tasks/118/artifacts/reports/qc.png");
  assert.equal("path" in firstReport, false);
  assert.equal("summary_path" in summary, false);
  assert.match(serialized, /\[redacted-host-path\]/);
  assert.match(serialized, /\[redacted-secret\]/);
  assert.doesNotMatch(serialized, /\/home\/yyf\/project\/image_agent/);
  assert.doesNotMatch(serialized, /C:\/Users\/A\/private\/report/);
  assert.doesNotMatch(serialized, /sk-result-secret/);
  assert.doesNotMatch(serialized, /log_path/);
});

test("desktop artifact manifest strips backend paths and preserves workflow metadata for display", async () => {
  let requestedPath = "";
  globalThis.fetch = async (url) => {
    requestedPath = String(url);
    return new Response(
      JSON.stringify({
        artifacts: [
          {
            content_type: "text/html",
            download_url: "/tasks/118/artifacts/reports/report.html",
            path: "/home/yyf/project/image_agent/data/projects/13/derivatives/118/reports/report.html",
            relative_path: "reports/report.html",
          },
        ],
        runtime_workflow_type: "dwi_fast_gpu_dti",
        summary_path: "/home/yyf/project/image_agent/data/projects/13/derivatives/118/result-summary.json",
        task_id: 118,
        workflow_metadata: {
          display_name: "DWI fast GPU DTI",
          workflow_type: "dwi_fast_gpu_dti",
          limitations: ["Do not expose C:/Users/A/private/task"],
        },
        workflow_type: "dwi_fast_gpu_dti",
      }),
      { status: 200 },
    );
  };

  const manifest = await api.getArtifactManifest(118);
  const serialized = JSON.stringify(manifest);

  assert.match(requestedPath, /\/tasks\/118\/artifact-manifest$/);
  assert.equal(manifest.workflow_metadata.display_name, "DWI fast GPU DTI");
  assert.equal(manifest.artifacts[0].relative_path, "reports/report.html");
  assert.equal("path" in manifest.artifacts[0], false);
  assert.equal("summary_path" in manifest, false);
  assert.match(serialized, /\[redacted-host-path\]/);
  assert.doesNotMatch(serialized, /\/home\/yyf\/project\/image_agent/);
  assert.doesNotMatch(serialized, /C:\/Users\/A\/private\/task/);
});

test("desktop legacy outputs strip backend paths before UI code sees them", async () => {
  globalThis.fetch = async () => new Response(
    JSON.stringify([
      {
        download_url: "/tasks/118/artifacts/tables/fa.tsv",
        id: 9,
        metadata: {
          nested: { log_path: "/home/yyf/project/image_agent/data/task.log" },
          path: "/home/yyf/project/image_agent/data/private.tsv",
        },
        output_type: "table",
        path: "/home/yyf/project/image_agent/data/projects/13/derivatives/118/output/tables/fa.tsv",
        preview_path: "/home/yyf/project/image_agent/data/projects/13/derivatives/118/output/preview.png",
        relative_path: "tables/fa.tsv",
      },
    ]),
    { status: 200 },
  );

  const outputs = await api.getOutputs(118);
  const first = outputs[0];
  const serialized = JSON.stringify(outputs);

  assert.equal(first.relative_path, "tables/fa.tsv");
  assert.equal(first.download_url, "/tasks/118/artifacts/tables/fa.tsv");
  assert.equal("path" in first, false);
  assert.equal("preview_path" in first, false);
  assert.doesNotMatch(serialized, /\/home\/yyf\/project\/image_agent/);
  assert.doesNotMatch(serialized, /log_path/);
});

test("desktop task logs strip backend paths and secrets before UI code sees them", async () => {
  globalThis.fetch = async () => new Response(
    JSON.stringify({
      task_id: 118,
      text: [
        "Processing subject 01",
        "wrote /home/yyf/project/image_agent/data/projects/13/logs/118.log",
        "cache C:/Users/A/private/work/task-118",
        "artifact data/projects/13/derivatives/118/output/qc.html",
        "OPENAI_API_KEY=sk-task-log-secret",
        "TOKEN=task-log-token",
      ].join("\n"),
    }),
    { status: 200 },
  );

  const payload = await api.getLogs(118);

  assert.equal(payload.task_id, 118);
  assert.match(payload.text, /Processing subject 01/);
  assert.match(payload.text, /\[redacted-host-path\]/);
  assert.match(payload.text, /OPENAI_API_KEY=\[redacted-secret\]/);
  assert.match(payload.text, /TOKEN=\[redacted-secret\]/);
  assert.doesNotMatch(payload.text, /\/home\/yyf\/project\/image_agent/);
  assert.doesNotMatch(payload.text, /C:\/Users\/A\/private\/work/);
  assert.doesNotMatch(payload.text, /data\/projects\/13/);
  assert.doesNotMatch(payload.text, /sk-task-log-secret/);
  assert.doesNotMatch(payload.text, /task-log-token/);
});

test("desktop task events strip backend paths and secrets before UI code sees them", async () => {
  let requestedPath = "";
  globalThis.fetch = async (url) => {
    requestedPath = String(url);
    return new Response(
      JSON.stringify({
        events: [
          { progress: 45, status: "running", type: "task.status" },
          { name: "fmriprep.log", source_stage: "fmriprep", type: "task.remote_log" },
        ],
        main_log: {
          tail: "OPENAI_API_KEY=sk-task-event-secret failed at C:/Users/A/private/task-118",
        },
        remote_logs: [
          {
            name: "fmriprep.log",
            path: "/home/yyf/project/image_agent/private/logs/fmriprep.log",
            source_stage: "fmriprep",
            tail: "TOKEN=task-event-token wrote data/projects/13/derivatives/118/output",
          },
        ],
        status: "ok",
        task: {
          id: 118,
          log_path: "/home/yyf/project/image_agent/data/projects/13/logs/118.log",
          progress: 45,
          project_id: 13,
          status: "running",
          workflow_type: "bold_fmriprep_xcpd_report",
        },
      }),
      { status: 200 },
    );
  };

  const payload = await api.getTaskEvents(118);
  const serialized = JSON.stringify(payload);

  assert.match(requestedPath, /\/tasks\/118\/events$/);
  assert.equal(payload.status, "ok");
  assert.deepEqual(payload.events.map((event) => event.type), ["task.status", "task.remote_log"]);
  assert.match(payload.main_log.tail, /\[redacted-host-path\]/);
  assert.equal(payload.remote_logs[0].source_stage, "fmriprep");
  assert.match(serialized, /\[redacted-secret\]/);
  assert.doesNotMatch(serialized, /\/home\/yyf\/project\/image_agent/);
  assert.doesNotMatch(serialized, /C:\/Users\/A\/private/);
  assert.doesNotMatch(serialized, /data\/projects\/13/);
  assert.doesNotMatch(serialized, /sk-task-event-secret/);
  assert.doesNotMatch(serialized, /task-event-token/);
  assert.doesNotMatch(serialized, /log_path/);
  assert.doesNotMatch(serialized, /"path"/);
});

test("desktop Agent run strips backend paths and secrets before UI code sees it", async () => {
  globalThis.fetch = async () => new Response(
    JSON.stringify({
      agent_run_id: "agent_run_123",
      answer: "Evidence from /home/yyf/project/image_agent/data/projects/13/raw/sub-01.nii.gz and data/projects/13/derivatives/118/output/qc.html",
      citations: [{ path: "docs/rag/vendor/fsl.md", title: "FSL" }],
      status: "confirmation_required",
      tool_invocations: [
        {
          result: {
            log_path: "/home/yyf/project/image_agent/data/projects/13/logs/118.log",
            openai_key: "sk-agent-run-secret",
            safe_doc_path: "docs/rag/vendor/fsl.md",
            windows_path: "C:/Users/A/private/task.log",
          },
          status: "ok",
          tool: "inspect_task_status",
        },
      ],
    }),
    { status: 200 },
  );

  const result = await api.runAgent(13, "Inspect task evidence");
  const serialized = JSON.stringify(result);

  assert.equal(result.citations[0].path, "docs/rag/vendor/fsl.md");
  assert.match(serialized, /\[redacted-host-path\]/);
  assert.match(serialized, /\[redacted-secret\]/);
  assert.doesNotMatch(serialized, /\/home\/yyf\/project\/image_agent/);
  assert.doesNotMatch(serialized, /data\/projects\/13/);
  assert.doesNotMatch(serialized, /C:\/Users\/A\/private\/task\.log/);
  assert.doesNotMatch(serialized, /sk-agent-run-secret/);
  assert.doesNotMatch(serialized, /log_path/);
});

test("desktop Agent resume strips backend paths and secrets before UI code sees it", async () => {
  globalThis.fetch = async () => new Response(
    JSON.stringify({
      status: "task_created",
      task: {
        id: 118,
        log_path: "/home/yyf/project/image_agent/data/projects/13/logs/118.log",
        project_id: 13,
        series_id: 24,
        status: "queued",
        workflow_type: "bold_fmriprep_xcpd_report",
      },
      tool_invocations: [
        {
          result: { token: "sk-agent-resume-secret", path: "/home/yyf/project/image_agent/private/task.json" },
          status: "ok",
          tool: "create_workflow_task",
        },
      ],
    }),
    { status: 200 },
  );
  const confirmation = {
    project_id: 13,
    series_id: 24,
    type: "workflow_execution",
    workflow_type: "bold_fmriprep_xcpd_report",
  };

  const result = await api.resumeAgent("thread-abc", true, confirmation);
  const serialized = JSON.stringify(result);

  assert.equal(result.task.workflow_type, "bold_fmriprep_xcpd_report");
  assert.equal(result.task.status, "queued");
  assert.match(serialized, /\[redacted-secret\]/);
  assert.match(serialized, /\[redacted-host-path\]/);
  assert.doesNotMatch(serialized, /\/home\/yyf\/project\/image_agent/);
  assert.doesNotMatch(serialized, /sk-agent-resume-secret/);
  assert.doesNotMatch(serialized, /log_path/);
});
