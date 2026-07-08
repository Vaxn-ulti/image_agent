# Remote Agent Production Deployment

This deployment keeps the Image Agent backend and workflow runtime on the remote compute server.
The model gateway should use the OpenAI-compatible SDK path from the deployed API server. In this document, "remote" means "the deployment server relative to the workstation"; workflow execution itself is deployment-server local. Docker containers, FSL/MRtrix/FreeSurfer tools, and wrapper scripts must run on the same server that hosts the Image Agent API, not on a second worker host. The current fast-launch target uses DeepSeek through direct OpenAI-compatible chat completions. SSH reverse tunnel remains a compatibility option only when a provider is reachable only from the workstation, but the DeepSeek production target should be direct from the deployed API server.

## Reverse Tunnel

Run this on Windows before starting or testing the deployed API only if the selected model provider is reachable from the workstation but not directly from the deployed API server:

```powershell
ssh -N -R 18081:127.0.0.1:8080 remote_server
```

On the deployed API server, configure:

```bash
python3 scripts/bootstrap_image_agent.py \
  --skip-elasticsearch-hybrid \
  --skip-workflow-images \
  --config-only \
  --model-provider deepseek \
  --model-name deepseek-v4-pro \
  --model-review-name deepseek-v4-pro \
  --model-base-url https://api.deepseek.com \
  --model-wire-api chat_completions \
  --apply
export BACKEND_RUNTIME_MODE=remote
export MODEL_REASONING_EFFORT=high
export OPENAI_DISABLE_RESPONSE_STORAGE=true
export OPENAI_DISABLE_METADATA=true
export IMAGE_AGENT_MODEL_API_KEY=<provided-by-operator>
```

The bootstrap command writes the non-secret DeepSeek values, including `IMAGE_AGENT_MODEL_TRUST_ENV_PROXY=0`. `IMAGE_AGENT_MODEL_API_KEY` remains secret material and must be supplied through the deployment environment or secret manager, not through Git, logs, or bootstrap reports. Use `IMAGE_AGENT_MODEL_WIRE_API=chat_completions` for DeepSeek. Chat Completions structured planning does not run the Responses tool loop, so workflow launch still requires the backend confirmation/resume path.

`ModelGateway` supports provider profiles through `IMAGE_AGENT_MODEL_PROVIDER`: `openai`, `rawchat`, `krill`, `deepseek`, `glm`, and `custom`. The generic `IMAGE_AGENT_MODEL_*` variables take priority. Provider-specific aliases are also accepted, for example `RAWCHAT_API_KEY`, `KRILL_API_KEY`, `DEEPSEEK_API_KEY`, `GLM_API_KEY` or `ZHIPU_API_KEY`. Existing `OPENAI_API_KEY`, `OPENAI_BASE_URL`, `OPENAI_MODEL`, and `OPENAI_WIRE_API` remain backward-compatible fallbacks for OpenAI-compatible gateways.

Default profile behavior is intentionally conservative: `openai`, `rawchat`, and `krill` default to `responses`; `deepseek` and `glm` default to `chat_completions`. Chat Completions mode supports text and structured JSON planning, but `/agent/model/status.capabilities.model_tool_loop` is `false`, and the Agent must still return workflow confirmation instead of creating production tasks.

`OPENAI_DISABLE_METADATA=true` is required for OpenAI-compatible gateways that reject the Responses `metadata` field but wrap the upstream validation error as a generic 502. Leave it unset for gateways that accept Responses metadata.

`/agent/model/status` reports `provider`, `provider_profile`, `wire_api`, `capabilities`, whether the key is configured, whether request metadata is enabled, and a safe gateway-access summary. It never returns the API key or reverse-tunnel command text.

## Elasticsearch Hybrid RAG

Strict remote acceptance now requires the deployment server to populate and query Elasticsearch hybrid RAG, not only write local contract files. Configure the deployed API environment before rebuilding the RAG index:

```bash
export IMAGE_AGENT_ELASTICSEARCH_URL=https://<elasticsearch-host>:9200
export IMAGE_AGENT_ELASTICSEARCH_API_KEY=<provided-by-operator>
export IMAGE_AGENT_ELASTICSEARCH_INDEX=image_agent_rag_<release-or-environment>
```

`IMAGE_AGENT_ELASTICSEARCH_API_KEY` is secret material and must stay in the operator-managed environment or secret store, not in git. `IMAGE_AGENT_ELASTICSEARCH_INDEX` is optional; when omitted the backend uses `image_agent_rag`, and when set it must be a privacy-safe symbol made from letters, numbers, `_`, `.`, or `-`. If the Elasticsearch service is reachable through another authenticated boundary, the API key can be omitted, but `/agent/rag/status.index.hybrid_search.persisted` still must become `true`.

Run this on the deployed API server after docs or skill references change:

```bash
cd /home/yyf/project/image_agent/apps/api
source .venv/bin/activate
PYTHONPATH=. python - <<'PY'
from pathlib import Path
from app.agent.status import rebuild_rag_index, rag_status
root = Path("/home/yyf/project/image_agent")
print(rebuild_rag_index(root)["hybrid_search"])
print(rag_status(root)["index"]["hybrid_search"])
PY
```

The acceptance status must show `engine=elasticsearch`, `configured=true`, a privacy-safe `index`, `mode=connected`, `persisted=true`, `lexical_retriever=standard`, `vector_retriever=knn`, `dense_vector_field=embedding`, positive `rag_elasticsearch_hybrid.dense_vector_dims`, a production configured `embedding_provider`, non-empty `rag_elasticsearch_hybrid.embedding_model`, production-safe `rag_elasticsearch_hybrid.embedding_transport`, privacy-safe boolean `rag_elasticsearch_hybrid.embedding_endpoint_configured`, `embedding_production_ready=true`, `fusion=rrf`, an `indexed_chunk_count` greater than zero, no `rag_elasticsearch_hybrid.error`, and no `rag_elasticsearch_hybrid.embedding_error`. The strict smoke run also records `rag_rebuild_elasticsearch_hybrid` from `/agent/rag/rebuild`; its `index`, `indexed_chunk_count`, `dense_vector_dims`, `embedding_provider`, `embedding_model`, `embedding_transport`, and `embedding_endpoint_configured` must match the status evidence, its `configured=true` and `embedding_production_ready` must be true, and both `rag_rebuild_elasticsearch_hybrid.error` and `rag_rebuild_elasticsearch_hybrid.embedding_error` must be absent, so an old manifest or failed rebuild cannot stand in for the rebuild response. The strict smoke run also posts a dedicated Elasticsearch hybrid contract query to `/agent/rag/query`; production evidence must include `rag_elasticsearch_hybrid_query_status=passed`, `rag_elasticsearch_hybrid_query_mode=elasticsearch_hybrid`, `rag_elasticsearch_hybrid_query_retrieval_source=elasticsearch_hybrid`, `rag_elasticsearch_hybrid_query_source=docs/rag/contracts/elasticsearch-hybrid-search.md`, positive citation/score evidence, `rag_elasticsearch_hybrid_query_dense_vector_field=embedding`, and query-time `index`, `dense_vector_dims`, `embedding_provider`, `embedding_model`, `embedding_transport`, `embedding_endpoint_configured=true`, and `embedding_production_ready=true` values that match the connected status evidence; the query-time dense-vector field matches `rag_elasticsearch_hybrid.dense_vector_field`. Local `mode=local_contract`, `mode=client_unavailable`, `mode=embedding_required`, `mode=embedding_error`, `embedding_provider=local_hashing`, or `elasticsearch_hybrid_fallback` query evidence remains acceptable for mock/control-plane development only and blocks production release. `mode=embedding_required` means Elasticsearch was configured but production embeddings were not, so the backend wrote only local contract artifacts and intentionally did not create or bulk-write the connected index.

Configure the production embedding provider before rebuilding RAG:

```bash
export IMAGE_AGENT_RAG_EMBEDDING_PROVIDER=openai
export IMAGE_AGENT_RAG_EMBEDDING_MODEL=text-embedding-3-small
export IMAGE_AGENT_RAG_EMBEDDING_API_KEY=<provided-by-operator>
export IMAGE_AGENT_RAG_EMBEDDING_BASE_URL=<openai-compatible-embedding-endpoint>
```

The embedding key may reuse the model gateway credential when the provider supports both APIs, but it must stay outside git and must not be written into smoke JSON, RAG documents, or task logs. If production embedding configuration is missing, `/agent/rag/rebuild` must report `mode=embedding_required`, avoid creating or bulk-writing the connected Elasticsearch index, and keep local hash vectors confined to local contract artifacts. If embedding initialization or vector generation fails, `/agent/rag/rebuild` must report redacted `embedding_error` evidence, avoid writing local-hash vectors into connected Elasticsearch, and strict acceptance must remain blocked until a fresh rebuild/query reports production-ready embedding evidence.

The backend prefers the OpenAI SDK for configured embeddings and reports `embedding_transport=sdk`. Deployment images without the SDK can still pass production RAG acceptance through the OpenAI-compatible `/embeddings` fallback, reporting `embedding_transport=openai_compatible_http` and using the same environment variables above. `IMAGE_AGENT_RAG_EMBEDDING_BASE_URL` may be a root `/v1` endpoint or a direct `/embeddings` URL; status and smoke evidence expose only `embedding_endpoint_configured=true|false`, not the URL. The fallback only sends embedding requests and must still produce connected Elasticsearch rebuild and query evidence.

## Production API Environment

Production-style API startup must use explicit CORS origins. Set these in the deployed server `.env` loaded by `IMAGE_AGENT_ENV_FILE` before restarting the API. Public internet deployment uses `IMAGE_AGENT_DEPLOYMENT_SCOPE=public_internet` and public HTTPS origins:

```bash
export IMAGE_AGENT_ENV=production
export IMAGE_AGENT_DEPLOYMENT_SCOPE=public_internet
export IMAGE_AGENT_CORS_ORIGINS=https://<console-hostname>
export IMAGE_AGENT_PUBLIC_BASE_URL=https://<api-hostname>
```

Private usable deployment, where the product is installed and accepted inside a target server/private network rather than exposed on the public internet, uses `IMAGE_AGENT_DEPLOYMENT_SCOPE=private_network` with explicit loopback/private HTTP(S) origins:

```bash
export IMAGE_AGENT_ENV=production
export IMAGE_AGENT_DEPLOYMENT_SCOPE=private_network
export IMAGE_AGENT_CORS_ORIGINS=http://127.0.0.1:5173
export IMAGE_AGENT_PUBLIC_BASE_URL=http://127.0.0.1:8000
```

`IMAGE_AGENT_CORS_ORIGINS` is a comma-separated allowlist. Do not use `*` in production. When `IMAGE_AGENT_ENV=production`, the API refuses to start if `IMAGE_AGENT_CORS_ORIGINS` is missing or contains a wildcard origin. Development can leave `IMAGE_AGENT_ENV` unset and use the local defaults for `http://localhost:5173` and `http://127.0.0.1:5173`.
`IMAGE_AGENT_PUBLIC_BASE_URL` is the API origin that the console and deployment-server smoke evidence use. With `public_internet`, `/deployment.production_readiness` stays blocked when it is missing, localhost-only, non-HTTPS, uses a private/reserved IP address, uses a bare host name such as `https://api`, ends in `.local`, or includes a path, query, or fragment. With `private_network`, loopback/private HTTP(S) origins are allowed, but wildcard CORS, `0.0.0.0`, bare host names, paths, query strings, and fragments are still rejected. The Git-managed bootstrap and release-gate materializers apply the same scope-aware boundary before writing or accepting the deployment env.

After restart, check `/deployment`. In production it returns
`production_readiness.required=true`; `production_readiness.ready` must be true
before the console is treated as launchable. A blocked response lists
operator-facing reasons such as `Agent model gateway is not configured.` or
`IMAGE_AGENT_PUBLIC_BASE_URL must be set for production deployment.` The
Settings page renders the same readiness status, but the remote smoke gate with
`--require-model` remains the release evidence source.

## Runtime Probe Contract

After installation, `/runtime/probe` is the portable machine-discovered contract
for the deployed server. It discovers the local Docker daemon, image-agent
labeled containers, workflow image availability, FreeSurfer license presence,
resource summary, and Elasticsearch configuration/reachability on the same
machine that serves the API. `/runtime/containers` remains a compatibility fallback for older deployments, but new release evidence and strict smoke runbooks should treat `/runtime/probe` as the primary install-local runtime surface.

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
release's `apps/api` directory. When launched from the release overlay root or
its `apps/api` directory, the wrapper infers `IMAGE_AGENT_RELEASE_ROOT` from the
current directory; you can also set `IMAGE_AGENT_ENV_FILE` or pass the env file
as the first positional argument. By default, the restart wrapper still reads
the shared main repo `.env` and runs Python from `IMAGE_AGENT_SHARED_VENV_BIN`,
which defaults to the shared main repo venv. This keeps the dirty remote main
worktree out of the serving path while still reusing the operator-managed
environment and dependencies.

Operators can set `IMAGE_AGENT_ENV_FILE` or pass the env file as the first positional argument.
When launched from the release overlay root or its `apps/api` directory, the wrapper infers the release root.
This keeps the dirty remote main worktree out of the serving path.

When active tasks block restart, the script prints a stale-task dry-run hint
using `scripts/reconcile_stale_tasks.py --check-containers`. Treat that as an
audit prompt, not as permission to override the drain gate.

Example live release-overlay restart:

```bash
export IMAGE_AGENT_ROOT=/home/yyf/project/image_agent
export IMAGE_AGENT_RELEASE_ROOT=/home/yyf/project/image_agent_releases/codex-7e7ff94-20260610
export IMAGE_AGENT_ENV_FILE=/home/yyf/project/image_agent/.env
export IMAGE_AGENT_SHARED_VENV_BIN=/home/yyf/project/image_agent/apps/api/.venv/bin
bash tools/restart_remote_image_agent_api.sh /home/yyf/project/image_agent/.env
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
checks require deployment-local Docker access through the configured Docker
command. Do not put sudo passwords in `.env`, scripts, logs, or approval JSON.

After operator review of a fresh approval dry-run, materialize the next release
gate plan instead of hand-editing `<fresh_reviewed_approval_json>`:

```bash
PYTHONPATH=. /home/yyf/project/image_agent/apps/api/.venv/bin/python scripts/build_release_gate_command_plan.py docs/deployment/remote-release-gate-command-plan.json /tmp/image_agent_stale_tasks_83_84_dry_run_<timestamp>.json --task-id 83 --task-id 84 --max-age-hours 24 --approval-json-command-path /tmp/image_agent_stale_tasks_83_84_dry_run_<timestamp>.json --deployment-id <deployment_id> --expected-health-version <expected_health_version> --remote-nifti-file <remote_nifti_file> --workflow-type <real_registered_workflow_type> --project-id <project_id> --upload-session-id <upload_session_id> --evidence-timestamp <timestamp> --production-cors-origins <https_console_origin> --production-public-base-url <https_api_origin> --output-json /tmp/image_agent_remote_release_gate_plan_<timestamp>.json
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
`<https_console_origin>` and `<https_api_origin>` must be real public HTTPS
origins without path, query, or fragment. Do not pass placeholders, localhost,
private or reserved IP addresses, bare host names such as `https://api`, `.local`
names, or wildcard CORS values; the builder and verifier reject those before
the operator plan can be used.
If strict acceptance should reuse an already ingested series, replace `--remote-nifti-file <remote_nifti_file>` with `--uploaded-series-id <uploaded_series_id>`. Use this only for a series from the same project and a completed upload session; it avoids re-uploading large imaging data and must not be combined with `--remote-nifti-file`. If the fixed workflow already completed through Agent confirmation/resume and you need to avoid rerunning the same expensive container, also pass `--acceptance-task-id <completed_task_id>` and `--agent-state-db /home/yyf/project/image_agent/data/app.db`. The materialized strict smoke command will add `--reuse-persisted-agent-launch-evidence`, `--task-id <completed_task_id>`, and `--launch-series-id <uploaded_series_id>` so the verifier reuses the saved Agent confirmation, fingerprint-negative, resume, task, result-summary, QC, and report evidence. Use this reuse path only after verifying the task is completed, belongs to the same project/series/workflow, and was created by the Agent resume confirmation path; it must not be used for direct `/series/{series_id}/run` diagnostic tasks.

To prepare the human approval handoff without mutating task rows, build a
machine-readable apply request from the verified dry-run JSON:

```bash
PYTHONPATH=. /home/yyf/project/image_agent/apps/api/.venv/bin/python scripts/build_stale_task_apply_request.py /tmp/image_agent_stale_tasks_83_84_dry_run_<timestamp>.json --task-id 83 --task-id 84 --max-age-hours 24 --deployment-id <deployment_id> --expected-health-version <expected_health_version> --remote-nifti-file <remote_nifti_file> --workflow-type <real_registered_workflow_type> --project-id <project_id> --upload-session-id <upload_session_id> --production-cors-origins <https_console_origin> --production-public-base-url <https_api_origin> --output-json /tmp/image_agent_stale_tasks_83_84_apply_request_<timestamp>.json
```

The resulting `stale_task_apply_approval` JSON includes the reviewed
`approval_fingerprint`, the exact env-loading apply command, and the required
post-apply verification gates, including clean resolution verification,
preflight-only restart, normal restart, strict remote smoke, offline strict
smoke JSON verification, and the final safe fast-launch environment export from
that same verified strict smoke JSON. It also includes the concrete production
CORS/API origins that will be written by `apply_production_readiness_env`; stale
task apply requests with `https://<console-hostname>` or `https://<api-hostname>`
placeholders are invalid. It also includes `approval_expires_at_utc`, which is
computed as `verified_approval.checked.generated_at_utc + freshness_hours` so
the operator can see the approval expiry without recomputing it manually. It
still requires explicit operator approval before anyone runs the apply command.
The same existing uploaded-series shortcut is available here: replace `--remote-nifti-file <remote_nifti_file>` with `--uploaded-series-id <uploaded_series_id>` only when the completed series is in the same project and tied to a completed upload session; do not combine both upload source flags.
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
  --expected-model-wire-api chat_completions \
  --expected-model-provider-profile deepseek \
  --require-project-agent-context \
  --require-agent-workflow-confirmation \
  --require-agent-workflow-resume \
  --require-agent-workflow-fingerprint-negative \
  --require-unknown-workflow-incubation \
  --require-deployment-identity \
  --require-production-readiness \
  --require-runtime-toolchain \
  --deployment-id <accepted-release-or-commit> \
  --expected-health-version <expected-health-version> \
  --min-documents 60 \
  --min-chunks 200 \
  --require-raw-source-policy \
  --require-vendor-pointer-integrity \
  --require-elasticsearch-hybrid-rag \
  --require-real-evidence-ids \
  --require-completed-upload \
  --require-uploaded-series \
  --upload-nifti-file <remote-nifti-file> \
  --require-completed-task \
  --require-task-events \
  --require-observe-repair \
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

The strict remote acceptance gate must include `--require-model`, `--min-documents`, `--min-chunks`, `--require-raw-source-policy`, `--require-vendor-pointer-integrity`, `--require-elasticsearch-hybrid-rag`, `--require-runtime-toolchain`, `--require-real-evidence-ids`, `--require-launchability-matrix`, `--require-container-native-qc`, `--min-native-qc-images`, `--require-scientific-report-artifacts`, `--min-scientific-report-images`, `--project-id`, `--task-id`, `--upload-session-id`, and `--output-json`.

The saved strict smoke evidence must also retain the API/result contract field index used by the verifier: `workflow_eligibility`, `/projects/{project_id}/datasets/{upload_session_id}/inventory`, `/tasks/{task_id}/artifact-manifest`, `task_artifact_manifest_status=passed`, `upload_inventory_contract_status=passed`, `rag_vendor_coverage_catalog_vendor_doc_count`, `rag_vendor_coverage_catalog_complete_vendor_doc_count`, `rag_launchability_matrix_status=passed`, `rag_launchability_matrix_source`, `rag_launchability_query_source`, `scientific_report_relative_paths`, `reports/index.html`, `reports/report_manifest.json`, `source_stage=scientific_report`, `artifact_role=derived_presentation_asset`, `artifact_origin=generated_from_result_summary`, `native_artifact=false`, `provenance.replaces_native_qc=false`, `curated_provenance_ok=true`, `curated_provenance_issues=[]`, `manifest_schema_version`, `source_count`, `vendor_doc_count`, `manifest_backed=true`, `source_url_backed=true`, non-empty `source_types`, configured `/agent/runs` must return `status=answered`, `agent_run_id`, `semantic_index=true`, and missing model gateway is a skip only when `--require-model` is omitted.

To avoid re-uploading large imaging data during repeated strict-gate attempts, the same strict smoke command can replace `--upload-nifti-file <remote-nifti-file>` with `--uploaded-series-id <uploaded_series_id>`. It still requires `--require-uploaded-series`, `--project-id`, and the completed upload inventory identified by `--upload-session-id`; use it only for a series in the same project from a completed upload session, and it must not be combined with `--upload-nifti-file`. To avoid rerunning an already completed Agent-launched production task, add `--reuse-persisted-agent-launch-evidence --agent-state-db /home/yyf/project/image_agent/data/app.db --task-id <completed_task_id> --launch-series-id <uploaded_series_id>`. The saved evidence must still pass the same confirmation, fingerprint-negative, resume, launched-task, completed-task, events, ObserveRepair, result-summary, container-native QC, and scientific-report gates, and the release-gate verifier requires `--launch-series-id` to match `--uploaded-series-id`.

`--require-runtime-toolchain` calls the deployed server's `/runtime/probe`, saves only a privacy-safe runtime summary, and requires `runtime_toolchain_status=passed`, `runtime_toolchain.workflow_tool_execution=deployment_server_local`, `runtime_toolchain.docker_runtime_host=api_server`, and `runtime_toolchain.required_workflow_available=true`. It must not save `fs_license_path`, Docker inspect tails, backend paths, or secrets. `/runtime/containers` remains a compatibility fallback for older deployments only.

Strict launch-source guard: `--require-production-readiness --require-launched-task`, `--require-deployment-identity --require-launched-task`, and `--require-runtime-toolchain --require-launched-task` must also include `--require-agent-workflow-resume`; otherwise the live smoke CLI rejects the command. `direct_series_run` is local/diagnostic smoke only and must not be used as production-readiness, deployment-identity, or deployment-local runtime-toolchain launch evidence.

For Elasticsearch hybrid RAG, strict production acceptance additionally requires `rag_elasticsearch_hybrid.configured=true`, privacy-safe `rag_elasticsearch_hybrid.index`, `rag_elasticsearch_hybrid.mode=connected`, positive `rag_elasticsearch_hybrid.indexed_chunk_count`, positive `rag_elasticsearch_hybrid.dense_vector_dims`, `rag_elasticsearch_hybrid.embedding_provider` from a configured provider, non-empty `rag_elasticsearch_hybrid.embedding_model`, production-safe `rag_elasticsearch_hybrid.embedding_transport`, boolean `rag_elasticsearch_hybrid.embedding_endpoint_configured`, `rag_elasticsearch_hybrid.embedding_production_ready=true`, `rag_rebuild_elasticsearch_hybrid` with matching index, indexed chunk count, lexical retriever, vector retriever, dense-vector field, fusion mode, dense vector dimensions, embedding provider, embedding model, embedding transport, embedding endpoint configured flag, and `embedding_production_ready=true`, absent `rag_elasticsearch_hybrid.error`, absent `rag_elasticsearch_hybrid.embedding_error`, absent `rag_rebuild_elasticsearch_hybrid.error`, absent `rag_rebuild_elasticsearch_hybrid.embedding_error`, `rag_elasticsearch_hybrid_query_retrieval_source=elasticsearch_hybrid`, `rag_elasticsearch_hybrid_query_lexical_retriever=standard`, `rag_elasticsearch_hybrid_query_vector_retriever=knn`, `rag_elasticsearch_hybrid_query_dense_vector_field=embedding`, `rag_elasticsearch_hybrid_query_fusion=rrf`, and query-time index/dense-vector/embedding provider/model/transport/endpoint/production-ready evidence matching the connected status evidence. The `rag_rebuild_elasticsearch_hybrid.lexical_retriever`, `rag_rebuild_elasticsearch_hybrid.vector_retriever`, `rag_rebuild_elasticsearch_hybrid.dense_vector_field`, and `rag_rebuild_elasticsearch_hybrid.fusion` fields must match `rag_elasticsearch_hybrid`, so the release proves both `/agent/rag/rebuild` and `/agent/rag/query` use the same BM25/kNN/RRF components as connected status. `persisted=true` without connected-mode, configured/index evidence, production embedding, rebuild, and query-source evidence is local contract evidence only and must not pass release acceptance.

Task observation is a separate read-only gate. Strict production acceptance must include `--require-task-events`, and the saved JSON must show `smoke_gate.require_task_events=true`, `task_events_status=passed`, `task_events_event_types` containing both `task.status` and `task.remote_log`, `task_events_status_event_status=completed`, `task_events_remote_log_count>0`, privacy-safe `task_events_remote_log_source_stages`, and `task_events_main_log_tail_present=true`. This evidence comes from `GET /tasks/{task_id}/events`; it observes status and redacted remote-log summaries only and must not retry, rerun, or create production tasks. Strict production acceptance must also include `--require-observe-repair`; the saved JSON must show `observe_repair_status=passed`, `observe_repair_policy=read_only_observe_repair`, `observe_repair_auto_rerun_allowed=false`, `observe_repair_production_task_created=false`, `observe_repair_requires_preflight_before_retry=true`, and `observe_repair_requires_human_confirmation_before_retry=true` from `GET /tasks/{task_id}/observe-repair`.

Unknown workflow acceptance must remain proposal-only: the saved JSON and verifier report must show `unknown_workflow_incubation_status=passed`, `unknown_workflow_incubation.action_lane=toolchain_incubation`, `unknown_workflow_incubation.task_created=false`, `unknown_workflow_incubation.confirmation_created=false`, `unknown_workflow_incubation.task_creation_allowed=false`, `unknown_workflow_incubation.forbidden_actions` including `confirmation_creation`, `production_task_creation`, and `pipeline_runner_launch`, plus `unknown_workflow_incubation.production_task_created=false`.

each container-native QC artifact `relative_path` must not start with `reports/`. `reports/*` artifacts must not be auto-promoted to container-native QC. Treat them as derived scientific report evidence unless strict non-report container output provenance proves otherwise.

Before running strict smoke, run the read-only Elasticsearch hybrid prerequisite preflight from the deployment API directory:

```bash
set -a; . /home/yyf/project/image_agent/.env; set +a;
IMAGE_AGENT_ROOT=/home/yyf/project/image_agent IMAGE_AGENT_ENV_FILE=/home/yyf/project/image_agent/.env PYTHONPATH=. /home/yyf/project/image_agent/apps/api/.venv/bin/python -m app.scripts.probe_runtime_environment --json > /tmp/image_agent_runtime_probe_<timestamp>.json
PYTHONPATH=. /home/yyf/project/image_agent/apps/api/.venv/bin/python scripts/verify_elasticsearch_hybrid_prerequisites.py --env-file /home/yyf/project/image_agent/.env --rag-status-url http://127.0.0.1:8000/agent/rag/status --runtime-probe-json /tmp/image_agent_runtime_probe_<timestamp>.json
```

The read-only preflight must print `status=passed` and safe checked fields such as `elasticsearch_url_configured=true`, `rag_embedding_provider_configured=true`, `rag_embedding_provider_production_configured=true`, `rag_embedding_model_configured=true`, `rag_embedding_endpoint_configured=true`, `rag_status_engine=elasticsearch_hybrid`, `rag_status_hybrid_engine=elasticsearch`, `rag_status_hybrid_configured=true`, `rag_status_hybrid_mode=connected`, `rag_status_hybrid_persisted=true`, privacy-safe `rag_status_hybrid_index`, `rag_status_hybrid_index_matches_env=true` when `IMAGE_AGENT_ELASTICSEARCH_INDEX` is configured, positive `rag_status_hybrid_indexed_chunk_count`, positive `rag_status_hybrid_dense_vector_dims`, `rag_status_hybrid_lexical_retriever=standard`, `rag_status_hybrid_vector_retriever=knn`, `rag_status_hybrid_dense_vector_field=embedding`, `rag_status_hybrid_fusion=rrf`, `rag_status_hybrid_official_rrf_source_present=true`, `rag_status_hybrid_error_absent=true`, `rag_status_hybrid_embedding_error_absent=true`, non-local production `rag_status_hybrid_embedding_provider`, present `rag_status_hybrid_embedding_model`, `rag_status_hybrid_embedding_model_matches_env=true`, production-safe `rag_status_hybrid_embedding_transport`, `rag_status_hybrid_embedding_endpoint_configured=true`, and `rag_status_hybrid_embedding_production_ready=true`. It also requires the deployment-server-local runtime probe to discover a running local Docker Elasticsearch container through the deployment's Docker access path. If the API user is not in the Docker group, configure host permissions or use the Git-managed bootstrap with `--docker-command "sudo -n docker" --verify-docker-command` to write `IMAGE_AGENT_DOCKER_COMMAND` and verify access with non-mutating `docker version`; the bootstrap rejects `sudo -S`, password prompts, shell wrappers, and Docker socket workarounds. The `sudo -n docker` path still requires host policy. To make the narrow NOPASSWD rule reproducible from Git, review `python3 scripts/configure_docker_access.py --user yyf --docker-bin /usr/bin/docker` first, then run the same command as root with `--apply` after operator approval. The script writes `/etc/sudoers.d/image-agent-docker`, validates it with `visudo -cf`, and verifies `sudo -n docker version --format {{.Server.Version}}`; it must not store passwords, proxy URLs, API keys, or Docker socket overrides. This Docker policy only affects deployment-local container access. Rawchat traffic remains direct through `IMAGE_AGENT_MODEL_TRUST_ENV_PROXY=0` and must not inherit Docker/image-pull proxy settings. The preflight is intentionally non-mutating and must not print API keys, endpoint URLs, backend paths, patient data, raw official-source URL lists, or raw error text. Passing this preflight does not replace `/agent/rag/rebuild`, the strict smoke Elasticsearch hybrid query, or the offline saved-JSON verifier; it only prevents known-missing ES/embedding/runtime configuration from being discovered after mutating steps have already started.

For the live API readiness view, `/deployment.fast_launch_readiness.checks.rag_elasticsearch_hybrid.status=passed` also requires `fast_launch_readiness.checks.rag_elasticsearch_hybrid.lexical_retriever=standard`, `fast_launch_readiness.checks.rag_elasticsearch_hybrid.vector_retriever=knn`, `fast_launch_readiness.checks.rag_elasticsearch_hybrid.dense_vector_field=embedding`, and `fast_launch_readiness.checks.rag_elasticsearch_hybrid.official_rrf_source_present=true`, proving the running `/agent/rag/status` includes the curated Elastic RRF source without exposing the raw `official_sources` list. `/deployment.fast_launch_readiness.checks.rag_elasticsearch_hybrid.blocking_codes` gives the same class of operator-safe diagnosis when the running service is not ready. Treat codes such as `rag_index_engine_not_elasticsearch_hybrid`, `rag_hybrid_not_persisted`, `rag_hybrid_lexical_retriever_not_standard`, `rag_hybrid_vector_retriever_not_knn`, `rag_hybrid_dense_vector_field_not_embedding`, `rag_embedding_endpoint_not_configured`, `rag_hybrid_official_rrf_source_missing`, or `rag_embedding_error_present` as remediation hints only. The codes are safe to show in frontend/operator tooling, but they do not contain the missing URL/key/path values and they do not replace connected Elasticsearch rebuild, query, strict smoke, or offline verifier evidence.

After saving the remote JSON, run the offline strict smoke acceptance JSON verifier `apps/api/scripts/verify_remote_smoke_acceptance.py` against that exact file:

```bash
python scripts/verify_remote_smoke_acceptance.py "../../docs/deployment/remote-smoke-acceptance-<timestamp>.json" --max-age-hours 24
```

The verifier must print `status=passed` before the JSON is attached to the handoff. `--max-age-hours 24` makes the saved `generated_at_utc` timestamp part of the release gate so stale JSON cannot be reused as fresh deployment evidence. This offline strict smoke acceptance JSON verifier does not replace running `smoke_remote_agent.py` on the deployed API server; the script name is historical, and the live run must exercise that server's local Docker/toolchain environment. It only re-checks the saved evidence for the same required fields, including `deployment_identity_status=passed`, `production_readiness_status=passed`, `production_readiness.ready=true`, an empty `production_readiness.blocking_reasons`, `fast_launch_readiness_status=pre_acceptance`, the sole missing strict-acceptance blocker, `fast_launch_readiness.checks.rag_elasticsearch_hybrid.status=passed`, `runtime_toolchain_status=passed`, `runtime_toolchain.workflow_tool_execution=deployment_server_local`, `runtime_toolchain.docker_runtime_host=api_server`, `runtime_toolchain.required_workflow_available=true`, a privacy-safe `deployment_identity.deployment_id` matching `smoke_gate.deployment_id`, a privacy-safe `deployment_identity.health_version` matching `smoke_gate.expected_health_version` when supplied, `model_smoke_status=passed`, `smoke_gate.expected_model_wire_api`, `model_status.wire_api` matching that expected wire API, `smoke_gate.expected_model_provider_profile`, `model_status.provider_profile` matching that expected provider profile, no `smoke_gate.require_model_tool_loop`, `model_status.capabilities.model_tool_loop=false`, `agent_project_context_status=passed`, `agent_run_project_id` matching `smoke_gate.project_id`, `agent_workflow_confirmation_status=passed`, `agent_workflow_confirmation.status=confirmation_required`, `agent_workflow_confirmation.intent=run_workflow`, `agent_workflow_confirmation.selected_skill=image-agent-workflow-runner`, `agent_workflow_confirmation.production_task_created=false`, `agent_workflow_confirmation.project_id` matching `smoke_gate.project_id`, `agent_workflow_confirmation.series_id` matching `task_status.series_id`, `agent_workflow_confirmation.workflow_type` matching `task_status.workflow_type`, `smoke_gate.require_agent_workflow_resume=true`, `smoke_gate.require_agent_workflow_fingerprint_negative=true`, `agent_workflow_fingerprint_negative_status=passed`, `agent_workflow_fingerprint_negative.confirmation_gate=fingerprint_mismatch`, `agent_workflow_fingerprint_negative.production_task_created=false`, `agent_workflow_fingerprint_negative.task_created=false`, `checked.agent_workflow_fingerprint_negative_status=passed`, `checked.agent_workflow_fingerprint_negative_confirmation_gate=fingerprint_mismatch`, `checked.agent_workflow_fingerprint_negative_production_task_created=false`, `checked.agent_workflow_fingerprint_negative_task_created=false`, `agent_workflow_resume_status=passed`, `agent_workflow_resume.status=task_created`, `agent_workflow_resume.production_task_created=true`, `agent_workflow_resume.confirmation_gate=fingerprint_verified`, `agent_workflow_resume.project_id` matching `smoke_gate.project_id`, `agent_workflow_resume.series_id` matching `task_status.series_id`, `agent_workflow_resume.workflow_type` matching `task_status.workflow_type`, `agent_workflow_resume.task_id` matching `smoke_gate.task_id`, `remote_evidence_ids_status=passed`, `upload_inventory_completion_status=passed`, `upload_inventory_status=completed`, `uploaded_series_status=passed`, `uploaded_series.project_id` matching `smoke_gate.project_id`, `uploaded_series.series_id` matching `task_status.series_id`, `launched_task_status=passed`, `launched_task.task_id` matching `smoke_gate.task_id`, `launched_task.project_id` matching `smoke_gate.project_id`, `launched_task.series_id` matching `task_status.series_id`, `launched_task.workflow_type` matching `task_status.workflow_type`, `task_status_status=passed`, `task_status.status=completed`, `task_status.task_id` matching `smoke_gate.task_id`, `task_workflow_selection_status=passed`, `task_workflow_selection.matched_runnable_workflow=true`, `task_workflow_selection.series_id` matching `task_status.series_id`, `task_workflow_selection.workflow_type` matching `task_status.workflow_type`, `rag_raw_sources.manifest_schema_version`, `rag_raw_sources.source_count`, `rag_raw_sources.vendor_doc_count`, `smoke_gate.require_elasticsearch_hybrid_rag=true`, `rag_elasticsearch_hybrid_status=passed`, `rag_elasticsearch_hybrid.persisted=true`, positive `rag_elasticsearch_hybrid.dense_vector_dims` matching rebuild evidence, checked `rag_elasticsearch_hybrid_error_absent=true`, checked `rag_elasticsearch_hybrid_embedding_error_absent=true`, checked `rag_rebuild_elasticsearch_hybrid_error_absent=true`, checked `rag_rebuild_elasticsearch_hybrid_embedding_error_absent=true`, `rag_elasticsearch_hybrid.embedding_provider`, `rag_elasticsearch_hybrid.embedding_model`, `rag_elasticsearch_hybrid.embedding_production_ready=true`, matching `rag_rebuild_elasticsearch_hybrid.embedding_model`, `rag_rebuild_elasticsearch_hybrid.embedding_production_ready=true`, `rag_elasticsearch_hybrid.fusion=rrf`, `rag_elasticsearch_hybrid.official_rrf_source_present=true`, no saved raw `official_sources` key anywhere in the strict smoke JSON, `rag_vendor_pointer_integrity_status=passed`, `require_vendor_pointer_integrity`, `rag_vendor_pointer_integrity_referenced_vendor_docs`, `rag_vendor_coverage_catalog_status=complete`, `vendor_coverage_catalog`, `vendor_coverage_catalog.vendors`, `rag_raw_sources.curated_sources`, `rag_launchability_query_status=passed`, `container_native_qc_status=passed`, `container_native_qc_served_urls`, `container_native_qc_artifacts`, `container_native_qc_official_source_ids`, each container-native QC artifact `relative_path` is slash-relative and safe, each container-native QC artifact `download_url` is recomputed from `task_id` and `relative_path`, each container-native QC artifact `content_type` matches `preview_kind`, `scientific_report_artifacts_status=passed`, `scientific_report_served_urls`, and `scientific_report_artifacts`; `vendor_coverage_catalog.vendors` and `rag_raw_sources.curated_sources` must exactly match with no missing or extra vendor docs, each scientific report artifact `download_url` is served with non-empty bytes, and each scientific report artifact `content_type` matches `preview_kind`. The saved `vendor_coverage_catalog` must not expose `manifest_path`, `persist_dir`, `raw_snapshots`, `raw_files`, or `sha256`. For Elasticsearch hybrid RAG, the verifier also requires `rag_elasticsearch_hybrid_query_status=passed`, `rag_elasticsearch_hybrid_query_mode=elasticsearch_hybrid`, `rag_elasticsearch_hybrid_query_source` pointing at `docs/rag/contracts/elasticsearch-hybrid-search.md`, positive query citation/score evidence, `rag_elasticsearch_hybrid_query_lexical_retriever=standard`, `rag_elasticsearch_hybrid_query_vector_retriever=knn`, `rag_elasticsearch_hybrid_query_dense_vector_field=embedding`, `rag_elasticsearch_hybrid_query_fusion=rrf`, and query-time index/dense-vector/embedding provider/model/transport/endpoint/production-ready evidence matching the connected status evidence; the query-time dense-vector field matches `rag_elasticsearch_hybrid.dense_vector_field`, and query-time hybrid components match `rag_elasticsearch_hybrid`.

Result-summary workflow metadata is also part of the strict acceptance contract. The saved JSON must include `task_result_summary.workflow_metadata.workflow_type` matching the result-summary `workflow_type`, `task_result_summary.workflow_metadata.runtime_workflow_type` matching `task_status.runtime_workflow_type`, a descriptive `task_result_summary.workflow_metadata.display_name`, present `task_result_summary.workflow_metadata.capability_summary`, `task_result_summary.workflow_metadata.pipeline_stages`, `task_result_summary.workflow_metadata.primary_outputs`, `task_result_summary.workflow_metadata.qc_outputs`, `task_result_summary.workflow_metadata.report_outputs`, and `task_result_summary.workflow_metadata.limitations`, plus `task_result_summary.workflow_metadata.agent_selectable=true` and `task_result_summary.workflow_metadata.is_report_only=false`. This result-summary workflow metadata is display/interpretation evidence only and does not replace stable `workflow_type` for task creation, confirmation fingerprints, database records, or artifact routes.

Strict launch provenance is part of that acceptance contract. The saved JSON must include `launched_task.launch_source=agent_workflow_resume`, and the offline verifier's checked summary must include `checked.launched_task_launch_source=agent_workflow_resume`. A direct `/series/{series_id}/run` fallback can remain useful for local diagnostics, but it is not valid strict production launch evidence.

After the verifier passes, use the same verified JSON to apply the two safe fast-launch environment lines through the Git-managed bootstrap script:

```bash
python scripts/bootstrap_image_agent.py \
  --skip-elasticsearch-hybrid \
  --skip-workflow-images \
  --config-only \
  --strict-acceptance-json "../../docs/deployment/remote-smoke-acceptance-<timestamp>.json" \
  --strict-acceptance-max-age-hours 24 \
  --apply
```

The machine-checkable release gate plan and generated `stale_task_apply_approval` handoff include this as a final operator-authorized config mutation after strict JSON verification. The bootstrap script re-runs the verifier, then writes only `IMAGE_AGENT_STRICT_REMOTE_ACCEPTANCE_STATUS=passed` and `IMAGE_AGENT_STRICT_REMOTE_ACCEPTANCE_ID=<deployment_id>` to the remote API environment. Restart or reload the service so `/deployment.fast_launch_readiness` can report the accepted remote evidence. This env state is only a privacy-safe summary for the operator UI; keep the saved strict remote smoke JSON and verifier output as the release evidence.

Do not put API keys, patient data, raw images, or full sensitive logs into RAG documents.
