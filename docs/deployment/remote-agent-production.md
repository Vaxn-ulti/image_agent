# Remote Agent Production Deployment

This deployment keeps the Image Agent backend and workflow runtime on the remote compute server.
The model gateway stays on the Windows workstation and is exposed to the remote server by SSH reverse tunnel.

## Reverse Tunnel

Run this on Windows before starting or testing the remote API:

```powershell
ssh -N -R 18081:127.0.0.1:8080 remote_server
```

On the remote server, configure:

```bash
export BACKEND_RUNTIME_MODE=remote
export MODEL_PROVIDER=OpenAI
export OPENAI_MODEL=gpt-5.5
export OPENAI_REVIEW_MODEL=gpt-5.5
export OPENAI_BASE_URL=http://127.0.0.1:18081
export OPENAI_WIRE_API=responses
export MODEL_REASONING_EFFORT=high
export OPENAI_DISABLE_RESPONSE_STORAGE=true
export OPENAI_DISABLE_METADATA=true
export OPENAI_API_KEY=<provided-by-operator>
```

`OPENAI_DISABLE_METADATA=true` is required for OpenAI-compatible gateways that reject the Responses `metadata` field but wrap the upstream validation error as a generic 502. Leave it unset for gateways that accept Responses metadata.

`/agent/model/status` reports whether the key is configured, whether request metadata is enabled, and how the remote backend reaches the gateway. It never returns the API key.

## BOLD fMRIPrep + XCP-D Remote Scripts

Default script paths:

```bash
export IMAGE_AGENT_BOLD_FMRIPREP_SCRIPT=/home/yyf/Project/MMD_project/EVIDENCE/fmriprep_xcpd_comparison_20260602/scripts/run_fmriprep.sh
export IMAGE_AGENT_BOLD_XCPD_SCRIPT=/home/yyf/Project/MMD_project/EVIDENCE/fmriprep_xcpd_comparison_20260602/scripts/run_xcpd_fmriprep.sh
```

The backend wrapper passes task-specific paths through environment variables:

```text
IMAGE_AGENT_TASK_BIDS_DIR
IMAGE_AGENT_TASK_OUTPUT_DIR
IMAGE_AGENT_TASK_WORK_DIR
IMAGE_AGENT_TASK_FMRIPREP_DIR
IMAGE_AGENT_TASK_XCPD_DIR
IMAGE_AGENT_TASK_TEMPLATEFLOW_DIR
IMAGE_AGENT_TASK_LOG_DIR
IMAGE_AGENT_TASK_FS_LICENSE
IMAGE_AGENT_TEMPLATEFLOW_HOME
```

The scripts should prefer those task variables over hardcoded experiment paths.

For production, set a shared TemplateFlow cache before launching new tasks:

```bash
export IMAGE_AGENT_TEMPLATEFLOW_HOME=/home/yyf/project/image_agent/cache/templateflow
mkdir -p "$IMAGE_AGENT_TEMPLATEFLOW_HOME"
```

Without this setting, the backend falls back to `data/projects/<project_id>/derivatives/<task_id>/work/templateflow`.
That is isolated and safe, but it makes each fMRIPrep/XCP-D task download templates again.

Remote script wrappers use `IMAGE_AGENT_REMOTE_SCRIPT_TIMEOUT_SEC` as the per-script timeout. If a wrapper catches `TimeoutExpired`, the task log should say remote script timed out and include only a redacted log tail for partial stdout retention. Script paths must be regular files, not directories, and raised wrapper errors should use path-safe script labels rather than full host paths. Success summaries use path-safe script labels for completed wrapper steps, and public preflight check summaries use path-safe labels instead of raw host paths. The child process receives a safe child environment allowlist plus task-specific `IMAGE_AGENT_TASK_*` paths; do not pass `OPENAI_API_KEY`, `DEEPSEEK_API_KEY`, or `IMAGE_AGENT_SUDO_PASSWORD` into fMRIPrep/XCP-D scripts. Any script stdout/stderr must be redacted before it is appended to task logs.

## Applying A Prepared Incremental Package

Do not restart the remote API while a production task is running. After the task reaches `completed` or `failed`,
apply the newest package uploaded under `/tmp`:

```bash
cd /home/yyf/project/image_agent
tar -xzf /tmp/image_agent_incremental_YYYYMMDDTHHMMSS.tgz
cd apps/api
source .venv/bin/activate
python -m pytest tests/test_incubation_ledger.py tests/test_agent_tools.py tests/test_agent_graph.py tests/test_agent_api.py tests/test_workflow_registry.py tests/test_remote_scripts.py tests/test_pipeline_remote_bold.py -q
python -m compileall -q app
```

Then restart the API with the service manager used on the host and run the smoke checks below.

## Remote API Restart Safety

`tools/restart_remote_image_agent_api.sh` is a restart/drain safety gate for the remote API. It refuses to restart while tasks are `queued` or `running`, unless the operator explicitly sets `IMAGE_AGENT_ALLOW_RESTART_WITH_ACTIVE_TASKS=1` after confirming the task state. It also refuses to stop a foreign process on port 8000 unless `IMAGE_AGENT_ALLOW_FOREIGN_PORT_OWNER=1` is set, because an unexpected port owner can mean the operator is pointed at the wrong service.

The wrapper uses `IMAGE_AGENT_STOP_TIMEOUT_SECONDS` while waiting for the old Image Agent uvicorn process to exit, and `IMAGE_AGENT_START_TIMEOUT_SECONDS` while waiting for the new API to become healthy. The post-restart `/health` must return `app=image_agent`; otherwise the restart fails and the operator should inspect `apps/api/api.out`.

For accepted builds, prefer running the live API from a release overlay rather
than the dirty remote main worktree. Set `IMAGE_AGENT_RELEASE_ROOT` to the
accepted release directory, or set `IMAGE_AGENT_API_DIR` directly to that
release's `apps/api` directory. By default, the restart wrapper still reads
`IMAGE_AGENT_ENV_FILE` from the shared main repo `.env` and runs Python from
`IMAGE_AGENT_SHARED_VENV_BIN`, which defaults to the shared main repo venv. This
keeps the dirty remote main worktree out of the serving path while still reusing
the operator-managed environment and dependencies.

When active tasks block restart, the script prints a stale-task dry-run hint
using `scripts/reconcile_stale_tasks.py --check-containers`. Treat that as an
audit prompt, not as permission to override the drain gate.

Example live release-overlay restart:

```bash
export IMAGE_AGENT_ROOT=/home/yyf/project/image_agent
export IMAGE_AGENT_RELEASE_ROOT=/home/yyf/project/image_agent_releases/codex-7e7ff94-20260610
export IMAGE_AGENT_ENV_FILE=/home/yyf/project/image_agent/.env
export IMAGE_AGENT_SHARED_VENV_BIN=/home/yyf/project/image_agent/apps/api/.venv/bin
bash tools/restart_remote_image_agent_api.sh
```

If the drain gate reports old `queued` or `running` tasks that are not backed by
running Image Agent containers, audit them before using the override. The
stale-task tool defaults to read-only dry-run:

```bash
cd /home/yyf/project/image_agent_releases/<accepted-release>/apps/api
PYTHONPATH=. /home/yyf/project/image_agent/apps/api/.venv/bin/python scripts/reconcile_stale_tasks.py --max-age-hours 24
```

For approval evidence, include the read-only container label check in the
dry-run report:

```bash
set -a
. /home/yyf/project/image_agent/.env
set +a
PYTHONPATH=. /home/yyf/project/image_agent/apps/api/.venv/bin/python scripts/reconcile_stale_tasks.py --max-age-hours 24 --check-containers
```

For scoped approval, repeat `--task-id` for the exact rows the operator intends
to reconcile. The report keeps other stale rows in
`out_of_scope_stale_task_ids` and emits an `approval_fingerprint` calculated
from the scoped stale candidates, target task ids, Docker label-check result,
and running labelled task ids. Save the full dry-run JSON before applying:

```bash
PYTHONPATH=. /home/yyf/project/image_agent/apps/api/.venv/bin/python scripts/reconcile_stale_tasks.py --max-age-hours 24 --check-containers --task-id 83 --task-id 84 > /tmp/image_agent_stale_tasks_83_84_dry_run.json
```

Verify the saved approval evidence before requesting apply approval:

```bash
PYTHONPATH=. /home/yyf/project/image_agent/apps/api/.venv/bin/python scripts/verify_stale_task_approval.py /tmp/image_agent_stale_tasks_83_84_dry_run.json --task-id 83 --task-id 84
```

Only after operator review, run apply with Docker label checking enabled by
default and require the reviewed JSON. The CLI reads the reviewed
`approval_fingerprint` from that file. If the task state, scoped task ids, or
labelled running-container evidence has changed, apply refuses to mutate rows
and the operator must rerun dry-run review:

```bash
PYTHONPATH=. /home/yyf/project/image_agent/apps/api/.venv/bin/python scripts/reconcile_stale_tasks.py --apply --max-age-hours 24 --task-id 83 --task-id 84 --approval-json /tmp/image_agent_stale_tasks_83_84_dry_run.json --reason "operator confirmed no matching running Image Agent container" > /tmp/image_agent_stale_tasks_83_84_apply.json
```

The apply mode marks stale active task rows as `failed`, writes a concise audit
line to the task log, and refuses to update rows that still have a running
labelled Image Agent container.

Then run a second read-only dry-run with the same scoped task ids. The follow-up
dry-run should show that the reconciled task ids are no longer active or stale:

```bash
PYTHONPATH=. /home/yyf/project/image_agent/apps/api/.venv/bin/python scripts/reconcile_stale_tasks.py --max-age-hours 24 --check-containers --task-id 83 --task-id 84 > /tmp/image_agent_stale_tasks_83_84_resolved_dry_run.json
PYTHONPATH=. /home/yyf/project/image_agent/apps/api/.venv/bin/python scripts/verify_stale_task_resolution.py --apply-json /tmp/image_agent_stale_tasks_83_84_apply.json --resolution-json /tmp/image_agent_stale_tasks_83_84_resolved_dry_run.json --task-id 83 --task-id 84 --require-empty-active
```

`verify_stale_task_resolution.py` must print `status=passed` before attempting
a normal restart without `IMAGE_AGENT_ALLOW_RESTART_WITH_ACTIVE_TASKS=1`. If the
follow-up dry-run reports target task ids as active, stale candidates, blockers,
labelled running containers, or backend path fields such as `log_path`, stop and
review the production task/container state instead of overriding the drain gate.

## Smoke Checks

From the remote backend directory:

```bash
cd /home/yyf/project/image_agent/apps/api
source .venv/bin/activate
python -m pytest tests/test_model_gateway.py tests/test_agent_api.py tests/test_remote_scripts.py -q
curl -s http://127.0.0.1:8000/agent/model/status
curl -s http://127.0.0.1:8000/agent/rag/status
curl -s -X POST http://127.0.0.1:8000/agent/rag/rebuild
curl -s http://127.0.0.1:8000/agent/rag/status
```

Live model smoke:

```bash
curl -s -X POST http://127.0.0.1:8000/agent/runs \
  -H 'Content-Type: application/json' \
  -d '{"project_id": null, "message": "Summarize the current Image Agent runtime status."}'
```

Or run the packaged smoke script:

```bash
python scripts/smoke_remote_agent.py --api-base http://127.0.0.1:8000
```

The smoke output includes model gateway status, RAG index status before and after rebuild, and document/chunk counts.
If `/agent/model/status` reports that the model gateway is not configured, the script reports `model_smoke_status=skipped_missing_model_config` and skips `/agent/runs` while still validating the non-model deployment surfaces.
If the model gateway is configured, the script also runs the sample `/agent/runs` request and reports the selected runtime skill.

For production handoff, use the script as a strict remote acceptance gate:

```bash
python scripts/smoke_remote_agent.py \
  --api-base http://127.0.0.1:8000 \
  --require-model \
  --min-documents 60 \
  --min-chunks 200 \
  --require-raw-source-policy \
  --require-vendor-pointer-integrity \
  --require-real-evidence-ids \
  --require-launchability-matrix \
  --require-container-native-qc \
  --min-native-qc-images 1 \
  --require-scientific-report-artifacts \
  --min-scientific-report-images 1 \
  --project-id <project-with-series> \
  --upload-session-id <completed-upload-session-with-inventory> \
  --task-id <completed-task-with-result-artifacts> \
  --output-json "../../docs/deployment/remote-smoke-acceptance-$(date -u +%Y%m%dT%H%M%SZ).json"
```

The strict gate checks `/health` first and requires `app=image_agent`. It fails if `--require-model` is set and the OpenAI SDK gateway is not configured; missing model gateway is a skip only when `--require-model` is omitted. It also fails when rebuilt RAG counts are below `--min-documents` or `--min-chunks`, when `semantic_index=true` is not reported after rebuild, when `--require-raw-source-policy` finds the official raw-source manifest missing or dirty, when raw source files are indexed, when `manifest_schema_version`, positive `source_count`, or positive `vendor_doc_count` are missing, when curated summaries do not report `curated_provenance_ok=true` with `curated_provenance_issues=[]`, when any `rag_raw_sources.curated_sources[*].complete` is not true, when any curated source lacks `manifest_backed=true`, `source_url_backed=true`, or non-empty `source_types`, or when a configured `/agent/runs` must return `status=answered` but does not. `--require-vendor-pointer-integrity` separately fails unless `/agent/rag/status` reports workflow/contract vendor pointers with `rag_vendor_pointer_integrity_status=passed`, positive `rag_vendor_pointer_integrity_pointer_count`, zero `rag_vendor_pointer_integrity_issue_count`, and non-empty `rag_vendor_pointer_integrity_referenced_vendor_docs`; this provenance pointer integrity gate proves curated vendor references in `docs/rag/workflows` and `docs/rag/contracts` remain backed by raw-source provenance. The saved JSON also carries the operator-facing `vendor_coverage_catalog` summary as `rag_vendor_coverage_catalog_status=complete`, `rag_vendor_coverage_catalog_vendor_doc_count`, and `rag_vendor_coverage_catalog_complete_vendor_doc_count`; this summary must not expose `manifest_path`, `persist_dir`, raw snapshot text, `raw_snapshots`, `raw_files`, or `sha256`. `vendor_coverage_catalog.vendors` and `rag_raw_sources.curated_sources` must exactly match by `vendor_doc`, with no missing or extra vendor docs; for each matched vendor doc, `complete`, `manifest_backed`, `source_url_backed`, `source_types`, and `raw_source_ids` must stay consistent. `raw_source_ids` are manifest ids, not artifact `official_source_ids`; artifact source ids must use curated `docs/rag/vendor/*.md` answer sources. A configured live run must also include `agent_run_id`, `intent`, and `selected_skill`; passing live model smoke reports `model_smoke_status=passed`. `--require-real-evidence-ids` fails unless `--project-id`, `--upload-session-id`, and `--task-id` are all supplied and the JSON evidence reports `remote_evidence_ids_status=passed`. `--require-launchability-matrix` fails unless rebuilt RAG status includes `docs/rag/workflows/workflow_launchability_matrix.md`; it also posts the launchability smoke question to `/agent/rag/query` and fails unless the response has `intent=launchability` and cites `docs/rag/workflows/workflow_launchability_matrix.md` from citation/source fields rather than answer text alone. Passing evidence reports `rag_launchability_matrix_status=passed`, `rag_launchability_matrix_source`, `rag_launchability_query_status=passed`, `rag_launchability_query_intent`, and `rag_launchability_query_source`. When real remote ids are supplied, `--project-id` validates that `/projects/{project_id}/series` exposes `workflow_eligibility` with `policy_version=workflow_eligibility_v1` and `production_task_created=false`, `--upload-session-id` validates `/projects/{project_id}/datasets/{upload_session_id}/inventory` exposes the same derived `workflow_eligibility` contract for ingested series and reports `upload_inventory_contract_status=passed`, and `--task-id` validates `/tasks/{task_id}/artifact-manifest` with at least one safe artifact, valid `preview_kind`, URL-quoted recomputed download URL, `exists=true`, positive `size_bytes`, and no backend path leakage in artifacts, nested provenance, or `omitted_artifacts`. Passing task artifact checks report `task_artifact_manifest_status=passed`. `--require-container-native-qc` turns the artifact-manifest check into served container-native QC evidence: at least one HTML or image artifact must have `native_artifact=true`, `artifact_origin=container_output`, `provenance.generated_from=container_native_qc`, identical top-level and provenance `official_source_ids` from the accepted container-QC curated vendor docs, and a successful `download_url` byte fetch whose served content type matches the manifest. `--min-native-qc-images` can require one or more served native image QC artifacts. Passing evidence reports `container_native_qc_status=passed`, `container_native_qc_served_urls`, `container_native_qc_artifacts`, and `container_native_qc_official_source_ids`; the saved JSON verifier also checks that each container-native QC artifact `relative_path` is slash-relative and safe, each container-native QC artifact `download_url` is recomputed from `task_id` and `relative_path`, and each container-native QC artifact `content_type` matches `preview_kind`. `--require-scientific-report-artifacts` is a separate derived-presentation gate: it requires the completed `--task-id` manifest to expose result-summary-backed report artifacts with `scientific_report_artifacts_status=passed`, `scientific_report_relative_paths` including `reports/index.html` and `reports/report_manifest.json`, `scientific_report_served_urls` from non-empty artifact route byte fetches, PNG report assets at or above `--min-scientific-report-images`, and per-artifact `scientific_report_artifacts` provenance with `source_stage=scientific_report`, `artifact_role=derived_presentation_asset`, `artifact_origin=generated_from_result_summary`, `native_artifact=false`, and `provenance.replaces_native_qc=false`; each scientific report artifact `download_url` is served with non-empty bytes and each scientific report artifact `content_type` matches `preview_kind`. These generated report artifacts are report-layer evidence and do not replace `container_native_qc_status=passed`. Use `--output-json` to save strict smoke acceptance JSON with the gate settings, health identity, model status, RAG counts, raw-source policy status, vendor pointer integrity status, safe vendor coverage catalog, per-curated-doc `rag_raw_sources.curated_sources` provenance status, evidence-id/matrix query status, per-artifact container-native QC route evidence, derived scientific report artifact route evidence, project/upload/task contract fields, and live `agent_run_id` fields for the remote deployment evidence log.

After saving the remote JSON, run the offline strict smoke acceptance JSON verifier `apps/api/scripts/verify_remote_smoke_acceptance.py` against that exact file:

```bash
python scripts/verify_remote_smoke_acceptance.py "../../docs/deployment/remote-smoke-acceptance-<timestamp>.json"
```

The verifier must print `status=passed` before the JSON is attached to the handoff. This offline strict smoke acceptance JSON verifier does not replace running `smoke_remote_agent.py` on the remote server; it only re-checks the saved evidence for the same required fields, including `model_smoke_status=passed`, `remote_evidence_ids_status=passed`, `rag_raw_sources.manifest_schema_version`, `rag_raw_sources.source_count`, `rag_raw_sources.vendor_doc_count`, `rag_vendor_pointer_integrity_status=passed`, `require_vendor_pointer_integrity`, `rag_vendor_pointer_integrity_referenced_vendor_docs`, `rag_vendor_coverage_catalog_status=complete`, `vendor_coverage_catalog`, `vendor_coverage_catalog.vendors`, `rag_raw_sources.curated_sources`, `rag_launchability_query_status=passed`, `container_native_qc_status=passed`, `container_native_qc_served_urls`, `container_native_qc_artifacts`, `container_native_qc_official_source_ids`, each container-native QC artifact `relative_path` is slash-relative and safe, each container-native QC artifact `download_url` is recomputed from `task_id` and `relative_path`, each container-native QC artifact `content_type` matches `preview_kind`, `scientific_report_artifacts_status=passed`, `scientific_report_served_urls`, and `scientific_report_artifacts`; `vendor_coverage_catalog.vendors` and `rag_raw_sources.curated_sources` must exactly match with no missing or extra vendor docs, each scientific report artifact `download_url` is served with non-empty bytes, and each scientific report artifact `content_type` matches `preview_kind`. The saved `vendor_coverage_catalog` must not expose `manifest_path`, `persist_dir`, `raw_snapshots`, `raw_files`, or `sha256`.

Do not put API keys, patient data, raw images, or full sensitive logs into RAG documents.
