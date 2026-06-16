# Remote Agent Production Deployment

This deployment keeps the Image Agent backend and workflow runtime on the remote compute server.
The model gateway should use the OpenAI-compatible SDK path from the deployed API server. In this document, "remote" means "the deployment server relative to the workstation"; workflow execution itself is deployment-server local. Docker containers, FSL/MRtrix/FreeSurfer tools, and wrapper scripts must run on the same server that hosts the Image Agent API, not on a second worker host. The current fast-launch target uses a Responses-capable GPT-5.5 gateway directly; SSH reverse tunnel remains a compatibility option only when the provider is reachable only from the workstation.

## Reverse Tunnel

Run this on Windows before starting or testing the deployed API only if the selected model provider is reachable from the workstation but not directly from the deployed API server:

```powershell
ssh -N -R 18081:127.0.0.1:8080 remote_server
```

On the deployed API server, configure:

```bash
export BACKEND_RUNTIME_MODE=remote
export IMAGE_AGENT_MODEL_PROVIDER=rawchat
export IMAGE_AGENT_MODEL_NAME=gpt-5.5
export IMAGE_AGENT_MODEL_REVIEW_NAME=gpt-5.5
export IMAGE_AGENT_MODEL_BASE_URL=https://rawchat.cn/codex
export IMAGE_AGENT_MODEL_WIRE_API=responses
export MODEL_REASONING_EFFORT=high
export OPENAI_DISABLE_RESPONSE_STORAGE=true
export OPENAI_DISABLE_METADATA=true
export IMAGE_AGENT_MODEL_API_KEY=<provided-by-operator>
```

Use `IMAGE_AGENT_MODEL_WIRE_API=responses` for the current rawchat GPT-5.5 gateway because local SDK and Image Agent probes returned usable Responses output and the Agent tool loop remains enabled. Keep `IMAGE_AGENT_MODEL_WIRE_API=chat_completions` only as a compatibility fallback for providers that do not return parseable Responses output. Both modes must go through `ModelGateway`; Chat Completions structured planning does not run the model tool loop, and workflow launch still requires the backend confirmation/resume path.

`ModelGateway` supports provider profiles through `IMAGE_AGENT_MODEL_PROVIDER`: `openai`, `rawchat`, `krill`, `deepseek`, `glm`, and `custom`. The generic `IMAGE_AGENT_MODEL_*` variables take priority. Provider-specific aliases are also accepted, for example `RAWCHAT_API_KEY`, `KRILL_API_KEY`, `DEEPSEEK_API_KEY`, `GLM_API_KEY` or `ZHIPU_API_KEY`. Existing `OPENAI_API_KEY`, `OPENAI_BASE_URL`, `OPENAI_MODEL`, and `OPENAI_WIRE_API` remain backward-compatible fallbacks for OpenAI-compatible gateways.

Default profile behavior is intentionally conservative: `openai`, `rawchat`, and `krill` default to `responses`; `deepseek` and `glm` default to `chat_completions`. Chat Completions mode supports text and structured JSON planning, but `/agent/model/status.capabilities.model_tool_loop` is `false`, and the Agent must still return workflow confirmation instead of creating production tasks.

`OPENAI_DISABLE_METADATA=true` is required for OpenAI-compatible gateways that reject the Responses `metadata` field but wrap the upstream validation error as a generic 502. Leave it unset for gateways that accept Responses metadata.

`/agent/model/status` reports `provider`, `provider_profile`, `wire_api`, `capabilities`, whether the key is configured, whether request metadata is enabled, and a safe gateway-access summary. It never returns the API key or reverse-tunnel command text.

## Production API Environment

Production API startup must use explicit CORS origins. Set these in the deployed server `.env` loaded by `IMAGE_AGENT_ENV_FILE` before restarting the API:

```bash
export IMAGE_AGENT_ENV=production
export IMAGE_AGENT_CORS_ORIGINS=https://<console-hostname>
export IMAGE_AGENT_PUBLIC_BASE_URL=https://<api-hostname>
```

`IMAGE_AGENT_CORS_ORIGINS` is a comma-separated allowlist. Do not use `*` in production. When `IMAGE_AGENT_ENV=production`, the API refuses to start if `IMAGE_AGENT_CORS_ORIGINS` is missing or contains a wildcard origin. Development can leave `IMAGE_AGENT_ENV` unset and use the local defaults for `http://localhost:5173` and `http://127.0.0.1:5173`.
`IMAGE_AGENT_PUBLIC_BASE_URL` must be the public HTTPS API origin that the console and deployment-server smoke evidence use. In production, `/deployment.production_readiness` stays blocked when it is missing, localhost-only, non-HTTPS, or includes a path, query, or fragment.

After restart, check `/deployment`. In production it returns
`production_readiness.required=true`; `production_readiness.ready` must be true
before the console is treated as launchable. A blocked response lists
operator-facing reasons such as `Agent model gateway is not configured.` or
`IMAGE_AGENT_PUBLIC_BASE_URL must be set for production deployment.` The
Settings page renders the same readiness status, but the remote smoke gate with
`--require-model` remains the release evidence source.

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

Deployment-local script wrappers use `IMAGE_AGENT_REMOTE_SCRIPT_TIMEOUT_SEC` as the per-script timeout. The environment variable keeps its historical name, but the scripts execute on the deployed API server's local filesystem and local Docker runtime. If a wrapper catches `TimeoutExpired`, the task log should say deployment-local script timed out and include only a redacted log tail for partial stdout retention. Script paths must be regular files, not directories, and raised wrapper errors should use path-safe script labels rather than full host paths. Success summaries use path-safe script labels for completed wrapper steps, and public preflight check summaries use path-safe labels instead of raw host paths. The child process receives a safe child environment allowlist plus task-specific `IMAGE_AGENT_TASK_*` paths; do not pass `OPENAI_API_KEY`, `DEEPSEEK_API_KEY`, or `IMAGE_AGENT_SUDO_PASSWORD` into fMRIPrep/XCP-D scripts. Any script stdout/stderr must be redacted before it is appended to task logs.

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

Set `IMAGE_AGENT_RESTART_PREFLIGHT_ONLY=1` to run the drain and port-owner
checks without stopping or starting the API. In other words, it runs the drain and port-owner checks without stopping or starting the API. A clean preflight
prints `restart_preflight:ok`; use it after stale-task resolution and before normal restart to confirm the restart wrapper will not be blocked by active
tasks or a foreign port owner.

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

For the current tasks `83` and `84` cleanup path, prefer the machine-checkable
command sequence in `docs/deployment/remote-release-gate-command-plan.json`.
Before using the plan, verify it locally or on the release overlay with:

```bash
python apps/api/scripts/verify_release_gate_command_plan.py docs/deployment/remote-release-gate-command-plan.json
```

That verifier checks the required step order, `approval_fingerprint` guard,
`--max-age-hours 24`, post-apply `--require-empty-active`, preflight-only
`restart_preflight:ok`, normal restart without
`IMAGE_AGENT_ALLOW_RESTART_WITH_ACTIVE_TASKS=1`, strict smoke flags, and the
final offline `verify_remote_smoke_acceptance.py --max-age-hours 24` check. It
does not run ssh, apply stale tasks, restart the service, or run smoke by
itself.
If the recorded approval JSON is missing or older than 24 hours, use the
plan's `stale_task_approval_refresh` command to generate a fresh read-only
`reconcile_stale_tasks.py --check-containers --task-id 83 --task-id 84` report,
then have the operator review the new `approval_fingerprint` before apply. The
refresh command must not include `--apply`. The refresh, apply, and post-apply
dry-run commands must load the remote `.env` first with
`set -a; . /home/yyf/project/image_agent/.env; set +a`, because Docker label
checks require `IMAGE_AGENT_SUDO_PASSWORD`.

After operator review of a fresh approval dry-run, materialize the next release
gate plan instead of hand-editing `<fresh_reviewed_approval_json>`:

```bash
PYTHONPATH=. /home/yyf/project/image_agent/apps/api/.venv/bin/python scripts/build_release_gate_command_plan.py docs/deployment/remote-release-gate-command-plan.json /tmp/image_agent_stale_tasks_83_84_dry_run_<timestamp>.json --task-id 83 --task-id 84 --max-age-hours 24 --approval-json-command-path /tmp/image_agent_stale_tasks_83_84_dry_run_<timestamp>.json --output-json /tmp/image_agent_remote_release_gate_plan_<timestamp>.json
PYTHONPATH=. /home/yyf/project/image_agent/apps/api/.venv/bin/python scripts/verify_release_gate_command_plan.py /tmp/image_agent_remote_release_gate_plan_<timestamp>.json
```

The materialized plan must report `status=operator_authorization_required`,
`approval_json_state.status=fresh_reviewed`, and a future
`approval_json_state.approval_expires_at_utc`. If that expiry passes before
apply, run `stale_task_approval_refresh` again and rebuild the plan. When the
builder reads a copied local approval file, keep `approval_json` as the local
read path but set `--approval-json-command-path` to the remote
`/tmp/image_agent_*.json` path that will exist on the server; non-remote command
paths are rejected so local Windows paths cannot be embedded into the release
gate commands.

To prepare the human approval handoff without mutating task rows, build a
machine-readable apply request from the verified dry-run JSON:

```bash
PYTHONPATH=. /home/yyf/project/image_agent/apps/api/.venv/bin/python scripts/build_stale_task_apply_request.py /tmp/image_agent_stale_tasks_83_84_dry_run_<timestamp>.json --task-id 83 --task-id 84 --max-age-hours 24 --output-json /tmp/image_agent_stale_tasks_83_84_apply_request_<timestamp>.json
```

The resulting `stale_task_apply_approval` JSON includes the reviewed
`approval_fingerprint`, the exact env-loading apply command, and the required
post-apply verification gates, including clean resolution verification,
preflight-only restart, normal restart, strict remote smoke, offline strict
smoke JSON verification, and the final safe fast-launch environment export from
that same verified strict smoke JSON. It also includes `approval_expires_at_utc`, which is
computed as `verified_approval.checked.generated_at_utc + freshness_hours` so
the operator can see the approval expiry without recomputing it manually. It
still requires explicit operator approval before anyone runs the apply command.
Before asking for approval, verify that request JSON:

```bash
PYTHONPATH=. /home/yyf/project/image_agent/apps/api/.venv/bin/python scripts/verify_stale_task_apply_request.py /tmp/image_agent_stale_tasks_83_84_apply_request_<timestamp>.json --task-id 83 --task-id 84 --max-age-hours 24
```

The verifier must print `status=passed`; it does not execute the embedded
apply, restart, or smoke commands.

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
PYTHONPATH=. /home/yyf/project/image_agent/apps/api/.venv/bin/python scripts/verify_stale_task_approval.py /tmp/image_agent_stale_tasks_83_84_dry_run.json --task-id 83 --task-id 84 --max-age-hours 24
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
PYTHONPATH=. /home/yyf/project/image_agent/apps/api/.venv/bin/python scripts/verify_stale_task_resolution.py --apply-json /tmp/image_agent_stale_tasks_83_84_apply.json --resolution-json /tmp/image_agent_stale_tasks_83_84_resolved_dry_run.json --task-id 83 --task-id 84 --require-empty-active --max-age-hours 24
```

`verify_stale_task_approval.py --max-age-hours 24` and
`verify_stale_task_resolution.py --max-age-hours 24` must print
`status=passed` before attempting
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
  --expected-model-wire-api responses \
  --expected-model-provider-profile rawchat \
  --require-model-tool-loop \
  --require-project-agent-context \
  --require-agent-workflow-confirmation \
  --require-deployment-identity \
  --require-production-readiness \
  --deployment-id <accepted-release-or-commit> \
  --expected-health-version <expected-health-version> \
  --min-documents 60 \
  --min-chunks 200 \
  --require-raw-source-policy \
  --require-vendor-pointer-integrity \
  --require-real-evidence-ids \
  --require-completed-upload \
  --require-uploaded-series \
  --upload-nifti-file <remote-nifti-file> \
  --require-completed-task \
  --require-launched-task \
  --launch-workflow-type <real-registered-workflow-type> \
  --wait-task-completion-timeout-seconds 21600 \
  --wait-task-completion-poll-seconds 30 \
  --require-launchability-matrix \
  --require-container-native-qc \
  --min-native-qc-images 1 \
  --require-scientific-report-artifacts \
  --min-scientific-report-images 1 \
  --project-id <project-with-series> \
  --upload-session-id <completed-upload-session-with-inventory> \
  --output-json "../../docs/deployment/remote-smoke-acceptance-$(date -u +%Y%m%dT%H%M%SZ).json"
```

The strict gate checks `/health` first and requires `app=image_agent`. It fails if `--require-model` is set and the OpenAI SDK gateway is not configured; missing model gateway is a skip only when `--require-model` is omitted. `--launch-workflow-type` must name a real registered workflow for the uploaded series; debug-only mock workflows such as `t1_deepprep_mock` are rejected by both the live smoke script and the saved JSON verifier, so strict deployment evidence must prove the deployed server can run the local Docker/toolchain path for a real workflow. When `--expected-model-wire-api responses` is supplied, live smoke and the saved JSON verifier both require `/agent/model/status.wire_api` to match that value. This protects the current rawchat Responses launch path, where local OpenAI SDK and Image Agent probes returned parseable Responses output and model tool-loop planning remained enabled. `--require-project-agent-context` posts `/agent/runs` with the supplied `--project-id` and fails unless the response reports the same `project_id`, then saves `agent_project_context_status=passed` and `agent_run_project_id`; this proves project-scoped Agent chat works, but it does not let the Agent launch workflow tasks. `--require-agent-workflow-confirmation` posts a second `/agent/runs` request for the uploaded or launched series and `--launch-workflow-type`, then fails unless the response reports `status=confirmation_required`, `intent=run_workflow`, matching project/series/workflow fields, `selected_skill=image-agent-workflow-runner`, and `production_task_created=false`. This proves the Agent can prepare a workflow choice with model-backed reasoning while deterministic `POST /series/{series_id}/run` remains the only production task-creation step. `--require-uploaded-series` uploads `--upload-nifti-file` through deterministic backend `POST /projects/{project_id}/upload`, validates the returned `workflow_eligibility`, records only safe uploaded-series metadata, and uses that returned series id for `--require-launched-task` when `--launch-series-id` is omitted. `--require-launched-task` calls deterministic backend `POST /series/{series_id}/run` with `--launch-workflow-type`, records `launched_task_status=passed`, and uses the returned backend task id for later task, QC, and report checks when `--task-id` is not supplied. With `--wait-task-completion-timeout-seconds`, smoke polls `/tasks/{task_id}` until the backend reports `completed` or the timeout expires. `--require-deployment-identity` requires a short privacy-safe `--deployment-id` such as the accepted release overlay name or commit hash; the saved JSON records `deployment_identity_status=passed` and never needs the full remote release path. `--require-production-readiness` also checks `/deployment.production_readiness` and fails unless it reports `required=true`, `ready=true`, `status=ready`, and no blocking reasons. The `/health.version` value recorded in deployment identity must also be a short privacy-safe version string, not a backend path. When `--expected-health-version` is supplied, live smoke and the saved JSON verifier both require `/health.version` to match it exactly, so an old deployment cannot satisfy new release evidence. It also fails when rebuilt RAG counts are below `--min-documents` or `--min-chunks`, when `semantic_index=true` is not reported after rebuild, when `--require-raw-source-policy` finds the official raw-source manifest missing or dirty, when raw source files are indexed, when `manifest_schema_version`, positive `source_count`, or positive `vendor_doc_count` are missing, when curated summaries do not report `curated_provenance_ok=true` with `curated_provenance_issues=[]`, when any `rag_raw_sources.curated_sources[*].complete` is not true, when any curated source lacks `manifest_backed=true`, `source_url_backed=true`, or non-empty `source_types`, or when a configured `/agent/runs` must return `status=answered` but does not. `--require-vendor-pointer-integrity` separately fails unless `/agent/rag/status` reports workflow/contract vendor pointers with `rag_vendor_pointer_integrity_status=passed`, positive `rag_vendor_pointer_integrity_pointer_count`, zero `rag_vendor_pointer_integrity_issue_count`, and non-empty `rag_vendor_pointer_integrity_referenced_vendor_docs`; this provenance pointer integrity gate proves curated vendor references in `docs/rag/workflows` and `docs/rag/contracts` remain backed by raw-source provenance. The saved JSON also carries the operator-facing `vendor_coverage_catalog` summary as `rag_vendor_coverage_catalog_status=complete`, `rag_vendor_coverage_catalog_vendor_doc_count`, and `rag_vendor_coverage_catalog_complete_vendor_doc_count`; this summary must not expose `manifest_path`, `persist_dir`, raw snapshot text, `raw_snapshots`, `raw_files`, or `sha256`. `vendor_coverage_catalog.vendors` and `rag_raw_sources.curated_sources` must exactly match by `vendor_doc`, with no missing or extra vendor docs; for each matched vendor doc, `complete`, `manifest_backed`, `source_url_backed`, `source_types`, and `raw_source_ids` must stay consistent. `raw_source_ids` are manifest ids, not artifact `official_source_ids`; artifact source ids must use curated `docs/rag/vendor/*.md` answer sources. A configured live run must also include `agent_run_id`, `intent`, and `selected_skill`; passing live model smoke reports `model_smoke_status=passed`. `--require-real-evidence-ids` fails unless `--project-id`, `--upload-session-id`, and either `--task-id` or a backend id from `--require-launched-task` are present, and the JSON evidence reports `remote_evidence_ids_status=passed`. `--require-completed-upload` fails unless `/projects/{project_id}/datasets/{upload_session_id}/inventory` reports completed upload ingestion with `upload_inventory_completion_status=passed` and `upload_inventory_status=completed`. `--require-completed-task` fetches or waits for `/tasks/{task_id}` and fails unless the task is `completed`, belongs to the supplied project, has a positive series id, and exposes a privacy-safe workflow type; when `--project-id` is supplied, it also proves the completed task workflow appears in the same series `workflow_eligibility.runnable_workflows` and records `task_workflow_selection_status=passed`. The saved JSON records only safe uploaded-series, launch, task-status, and workflow-selection summaries and omits backend paths such as `log_path`. `--require-launchability-matrix` fails unless rebuilt RAG status includes `docs/rag/workflows/workflow_launchability_matrix.md`; it also posts the launchability smoke question to `/agent/rag/query` and fails unless the response has `intent=launchability` and cites `docs/rag/workflows/workflow_launchability_matrix.md` from citation/source fields rather than answer text alone. Passing evidence reports `rag_launchability_matrix_status=passed`, `rag_launchability_matrix_source`, `rag_launchability_query_status=passed`, `rag_launchability_query_intent`, and `rag_launchability_query_source`. When real remote ids are supplied, `--project-id` validates that `/projects/{project_id}/series` exposes `workflow_eligibility` with `policy_version=workflow_eligibility_v1` and `production_task_created=false`, `--upload-session-id` validates `/projects/{project_id}/datasets/{upload_session_id}/inventory` exposes the same derived `workflow_eligibility` contract for ingested series and reports `upload_inventory_contract_status=passed`, and the resolved task id validates `/tasks/{task_id}/artifact-manifest` with at least one safe artifact, valid `preview_kind`, URL-quoted recomputed download URL, `exists=true`, positive `size_bytes`, and no backend path leakage in artifacts, nested provenance, or `omitted_artifacts`. Passing task artifact checks report `task_artifact_manifest_status=passed`. `--require-container-native-qc` turns the artifact-manifest check into served container-native QC evidence: at least one HTML or image artifact must have `native_artifact=true`, `artifact_origin=container_output`, `provenance.generated_from=container_native_qc`, identical top-level and provenance `official_source_ids` from the accepted container-QC curated vendor docs, and a successful `download_url` byte fetch whose served content type matches the manifest. `--min-native-qc-images` can require one or more served native image QC artifacts. Passing evidence reports `container_native_qc_status=passed`, `container_native_qc_served_urls`, `container_native_qc_artifacts`, and `container_native_qc_official_source_ids`; the saved JSON verifier also checks that each container-native QC artifact `relative_path` is slash-relative and safe, each container-native QC artifact `download_url` is recomputed from `task_id` and `relative_path`, and each container-native QC artifact `content_type` matches `preview_kind`. `--require-scientific-report-artifacts` is a separate derived-presentation gate: it requires the resolved completed task manifest to expose result-summary-backed report artifacts with `scientific_report_artifacts_status=passed`, `scientific_report_relative_paths` including `reports/index.html` and `reports/report_manifest.json`, `scientific_report_served_urls` from non-empty artifact route byte fetches, PNG report assets at or above `--min-scientific-report-images`, and per-artifact `scientific_report_artifacts` provenance with `source_stage=scientific_report`, `artifact_role=derived_presentation_asset`, `artifact_origin=generated_from_result_summary`, `native_artifact=false`, and `provenance.replaces_native_qc=false`; each scientific report artifact `download_url` is served with non-empty bytes and each scientific report artifact `content_type` matches `preview_kind`. These generated report artifacts are report-layer evidence and do not replace `container_native_qc_status=passed`. Use `--output-json` to save strict smoke acceptance JSON with the gate settings, deployment identity, production readiness status, health identity, model status, RAG counts, raw-source policy status, vendor pointer integrity status, safe vendor coverage catalog, per-curated-doc `rag_raw_sources.curated_sources` provenance status, evidence-id/matrix query status, project-scoped Agent chat status, Agent workflow confirmation status, completed-upload status, actual uploaded-series status, deterministic launch evidence, safe completed-task status, workflow-selection evidence, per-artifact container-native QC route evidence, derived scientific report artifact route evidence, project/upload/task contract fields, and live `agent_run_id` fields for the remote deployment evidence log.

each container-native QC artifact `relative_path` must not start with `reports/`. `reports/*` artifacts must not be auto-promoted to container-native QC. Treat them as derived scientific report evidence unless strict non-report container output provenance proves otherwise.

After saving the remote JSON, run the offline strict smoke acceptance JSON verifier `apps/api/scripts/verify_remote_smoke_acceptance.py` against that exact file:

```bash
python scripts/verify_remote_smoke_acceptance.py "../../docs/deployment/remote-smoke-acceptance-<timestamp>.json" --max-age-hours 24
```

The verifier must print `status=passed` before the JSON is attached to the handoff. `--max-age-hours 24` makes the saved `generated_at_utc` timestamp part of the release gate so stale JSON cannot be reused as fresh deployment evidence. This offline strict smoke acceptance JSON verifier does not replace running `smoke_remote_agent.py` on the deployed API server; the script name is historical, and the live run must exercise that server's local Docker/toolchain environment. It only re-checks the saved evidence for the same required fields, including `deployment_identity_status=passed`, `production_readiness_status=passed`, `production_readiness.ready=true`, an empty `production_readiness.blocking_reasons`, a privacy-safe `deployment_identity.deployment_id` matching `smoke_gate.deployment_id`, a privacy-safe `deployment_identity.health_version` matching `smoke_gate.expected_health_version` when supplied, `model_smoke_status=passed`, `smoke_gate.expected_model_wire_api`, `model_status.wire_api` matching that expected wire API, `smoke_gate.expected_model_provider_profile`, `model_status.provider_profile` matching that expected provider profile, `smoke_gate.require_model_tool_loop=true`, `model_status.capabilities.model_tool_loop=true`, `agent_project_context_status=passed`, `agent_run_project_id` matching `smoke_gate.project_id`, `agent_workflow_confirmation_status=passed`, `agent_workflow_confirmation.status=confirmation_required`, `agent_workflow_confirmation.intent=run_workflow`, `agent_workflow_confirmation.selected_skill=image-agent-workflow-runner`, `agent_workflow_confirmation.production_task_created=false`, `agent_workflow_confirmation.project_id` matching `smoke_gate.project_id`, `agent_workflow_confirmation.series_id` matching `task_status.series_id`, `agent_workflow_confirmation.workflow_type` matching `task_status.workflow_type`, `remote_evidence_ids_status=passed`, `upload_inventory_completion_status=passed`, `upload_inventory_status=completed`, `uploaded_series_status=passed`, `uploaded_series.project_id` matching `smoke_gate.project_id`, `uploaded_series.series_id` matching `task_status.series_id`, `launched_task_status=passed`, `launched_task.task_id` matching `smoke_gate.task_id`, `launched_task.project_id` matching `smoke_gate.project_id`, `launched_task.series_id` matching `task_status.series_id`, `launched_task.workflow_type` matching `task_status.workflow_type`, `task_status_status=passed`, `task_status.status=completed`, `task_status.task_id` matching `smoke_gate.task_id`, `task_workflow_selection_status=passed`, `task_workflow_selection.matched_runnable_workflow=true`, `task_workflow_selection.series_id` matching `task_status.series_id`, `task_workflow_selection.workflow_type` matching `task_status.workflow_type`, `rag_raw_sources.manifest_schema_version`, `rag_raw_sources.source_count`, `rag_raw_sources.vendor_doc_count`, `rag_vendor_pointer_integrity_status=passed`, `require_vendor_pointer_integrity`, `rag_vendor_pointer_integrity_referenced_vendor_docs`, `rag_vendor_coverage_catalog_status=complete`, `vendor_coverage_catalog`, `vendor_coverage_catalog.vendors`, `rag_raw_sources.curated_sources`, `rag_launchability_query_status=passed`, `container_native_qc_status=passed`, `container_native_qc_served_urls`, `container_native_qc_artifacts`, `container_native_qc_official_source_ids`, each container-native QC artifact `relative_path` is slash-relative and safe, each container-native QC artifact `download_url` is recomputed from `task_id` and `relative_path`, each container-native QC artifact `content_type` matches `preview_kind`, `scientific_report_artifacts_status=passed`, `scientific_report_served_urls`, and `scientific_report_artifacts`; `vendor_coverage_catalog.vendors` and `rag_raw_sources.curated_sources` must exactly match with no missing or extra vendor docs, each scientific report artifact `download_url` is served with non-empty bytes, and each scientific report artifact `content_type` matches `preview_kind`. The saved `vendor_coverage_catalog` must not expose `manifest_path`, `persist_dir`, `raw_snapshots`, `raw_files`, or `sha256`.

After the verifier passes, use the same verified JSON to emit the two safe fast-launch environment lines:

```bash
python scripts/verify_remote_smoke_acceptance.py "../../docs/deployment/remote-smoke-acceptance-<timestamp>.json" --max-age-hours 24 --emit-fast-launch-env
```

The machine-checkable release gate plan and generated `stale_task_apply_approval` handoff include this export as a final read-only step after strict JSON verification. Apply the printed `IMAGE_AGENT_STRICT_REMOTE_ACCEPTANCE_STATUS=passed` and `IMAGE_AGENT_STRICT_REMOTE_ACCEPTANCE_ID=<deployment_id>` to the remote API environment only after the strict verifier passes, then restart or reload the service so `/deployment.fast_launch_readiness` can report the accepted remote evidence. This export is only a privacy-safe summary for the operator UI; keep the saved strict remote smoke JSON and verifier output as the release evidence.

Do not put API keys, patient data, raw images, or full sensitive logs into RAG documents.

