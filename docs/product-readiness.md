# Image Agent Product Readiness Gate

This gate defines when Image Agent is mature enough to tell the user that frontend page design and real product use can begin.

Until every required evidence item below is current and verified, the product is still in backend/agent hardening mode. Do not start frontend page design, do not present the existing console UI as production-ready, and do not treat local-only checks as acceptance.

## Fast Launch Main Flow Goal

The current near-term product goal is to make the existing console usable as quickly as possible for the core workflow: upload imaging data, Agent interaction, select a workflow, and start processing. This is a product-smoke milestone, not a replacement for strict remote production acceptance.

Minimum backend/frontend contract for this fast launch:

- Upload imaging data through `/projects/{project_id}/upload`, `/projects/{project_id}/upload-dwi`, `/projects/{project_id}/upload-dicom`, or the upload-session ingest endpoints.
- Refresh detected series through `/projects/{project_id}/series`, including modality, sequence label, support status, and `workflow_eligibility` where available.
- List selectable workflows through `/workflows`, and show blocked/runnable state from backend contracts rather than frontend guesses.
- Formal fixed-workflow launch must come from `/agent/runs/{thread_id}/resume` after human confirmation and fingerprint verification. Direct `/series/{series_id}/run` remains local diagnostic-only for debug/mock API-runnable workflows, not the production launch path for Agent-selectable fixed workflows.
- Show task state through `/projects/{project_id}/tasks`, `/tasks/{task_id}`, redacted `/tasks/{task_id}/logs`, read-only `/tasks/{task_id}/events`, `/tasks/{task_id}/outputs`, `/tasks/{task_id}/result-summary`, and `/tasks/{task_id}/artifact-manifest`.
- Support dashboard chat with `/chat` and grounded Agent review with `/agent/rag/query`; the model may be configured later, but the UI must clearly handle fallback/rules-based status.
- Configure browser access with `IMAGE_AGENT_CORS_ORIGINS`; local development may use localhost defaults, and production-style installs must use an explicit allowlist rather than wildcard CORS.
- Configure `IMAGE_AGENT_DEPLOYMENT_SCOPE` and `IMAGE_AGENT_PUBLIC_BASE_URL` for production-style readiness. Use `public_internet` with public HTTPS origins for a public deployment, or `private_network` with explicit loopback/private HTTP(S) origins when "launch" means the product is installed and usable inside the target private environment.
- Read `/deployment.fast_launch_readiness` before treating the Gemini console as launchable. It must report the rawchat GPT-5.5 Responses target, the deterministic Agent/task boundary, the upload-workflow-result contract, and strict remote acceptance evidence.

Fast-launch boundary rules:

- Agent may recommend or explain workflows, but task creation must still go through deterministic backend APIs and backend validation.
- RAG may explain official sources, but backend project/task state remains authoritative.
- Mock tests prove the control plane: API contracts, schema validation, Agent/task boundaries, workflow registry matching, preflight blocking, task state transitions, log/output registration, result-summary and artifact-manifest contracts, and frontend integration.
- Real script tests prove the execution plane: deployed-server local Docker/toolchain execution, GPU and license visibility, BIDS inputs, sidecar handling, external tool outputs, traceable logs, and result summaries derived from real outputs.
- Real processing acceptance belongs on the deployed API server. Local workstation tests prove contracts, not the deployed server's local Docker/FSL/MRtrix/FreeSurfer/container readiness.
- Container-native QC and result artifact display must rely on workflow outputs and artifact manifests, not locally invented frontend previews.
- No API keys, patient identifiers, raw source snapshots, backend absolute paths, raw task log paths, or sensitive logs may be exposed through chat, RAG status, task logs, artifact manifests, or frontend settings.

Fast local product smoke:

```bash
cd apps/api
python scripts/smoke_local_main_flow.py --api-base http://127.0.0.1:8000 --output-json ../../docs/deployment/local-main-flow-smoke.json
```

This smoke creates a temporary project, uploads a minimal generated T1 NIfTI when `--upload-nifti-file` is not supplied, verifies the uploaded series is returned by `/projects/{project_id}/series`, starts `t1_deepprep_mock` through `/series/{series_id}/run`, checks the task list, checks `/agent/model/status`, and requires `/agent/rag/status.grounding_policy`. Use `--min-rag-documents <n>` for launch rehearsal when an empty RAG index should fail. It does not call `/agent/runs` unless `--require-agent-confirmation` is set; add that flag only when the local model gateway is configured and expected to return a workflow confirmation. Add `--require-agent-resume` when the local smoke must prove the server-side confirmation path by posting `/agent/runs/{thread_id}/resume`; the output must then include `agent_workflow_resume_status=passed`, `production_task_created=true`, and `confirmation_gate=fingerprint_verified`. The smoke output is path-safe and records that it is local-only evidence; it does not prove the deployed server's local containers, real MRI processing, container-native QC artifacts, production CORS, or strict deployment acceptance.

For a stricter local launch rehearsal after docs are present, use:

```bash
python scripts/smoke_local_main_flow.py --api-base http://127.0.0.1:8000 --workflow-type t1_deepprep_mock --agent-workflow-type t1_deepprep_anat_report --expected-model-provider-profile rawchat --expected-model-wire-api responses --expected-model-name gpt-5.5 --require-model-tool-loop --rebuild-rag --min-rag-documents 60 --require-agent-confirmation --require-agent-resume --wait-task-completion-timeout-seconds 20 --wait-task-completion-poll-seconds 0.5 --require-task-outputs --require-result-summary --require-artifact-manifest
```

That stricter command keeps the quick local data path on `t1_deepprep_mock` but requires the Agent to prepare and resume a confirmation for the formal fixed workflow `t1_deepprep_anat_report`. The task used for downstream checks comes from `/agent/runs/{thread_id}/resume`, not an extra direct launch call, and the smoke records `agent_workflow_resume_status=passed`, `production_task_created=true`, and `confirmation_gate=fingerprint_verified` before it checks the task list, outputs, result summary, and artifact manifest. It also pins the local development model to rawchat GPT-5.5 Responses with model tool-loop capability, waits for the resumed task to complete, and requires safe task outputs, a unified result summary, and a non-empty artifact manifest for frontend display. It is expected to fail when the model gateway is unconfigured or not rawchat GPT-5.5 Responses, the Agent cannot produce a workflow confirmation, the server-side resume fingerprint gate fails, the local RAG index cannot be rebuilt to the required document count, task completion/output registration breaks, or the result/artifact contracts are empty. This is local-only control-plane evidence and does not prove the deployed server's local Docker/toolchain execution; strict deployment smoke must use a real registered workflow, and `t1_deepprep_mock` is rejected by the strict smoke and saved-evidence verifier.

Current model gateway finding: the rawchat GPT-5.5 OpenAI-compatible Responses path passed direct SDK, `ModelGateway`, strict local smoke, and browser dashboard checks with `OPENAI_WIRE_API=responses`, so this is the fastest-launch target for local development and remote acceptance. Krill Chat Completions remains a compatibility fallback for providers whose Responses route does not return parseable output. In Chat Completions mode, model-backed text and JSON planning work, but the Responses tool loop is intentionally reported as skipped and workflow launch must continue through deterministic backend confirmation APIs.

## Frontend Design Freeze Gate

Frontend page design may start only after all rows are marked with fresh evidence:

| Area | Required evidence | Blocking failure |
| --- | --- | --- |
| Agent architecture | OpenAI SDK Responses-style or Chat Completions-compatible gateway path is the primary model boundary, tool calls use structured function-tool contracts when the wire API supports them, Chat Completions planning is explicitly traced as no tool loop, and API tests cover planner/responder/tool-dispatch behavior. | Any direct model-call path bypasses `ModelGateway`, Chat Completions pretends to dispatch tools, tool calls are not structured on Responses-capable gateways, or durable run/thread state cannot be queried. |
| Run traceability | Durable run/thread state records safe lifecycle events, selected skill, model gateway access, retrieved sources, tool invocations, and safe metadata. | Agent work cannot be audited by `agent_run_id`, or read APIs expose prompts, secrets, local paths, or raw user content. |
| Result contracts | `/result-contract`, `/tasks/{task_id}/result-summary`, and `/tasks/{task_id}/artifact-manifest` document and serve stable result fields with safe `relative_path`, `download_url`, `content_type`, `size_bytes`, `preview_kind`, and provenance. | Frontend consumers must infer artifact cards from arbitrary text, local absolute paths leak, or legacy summaries can break current readers. |
| Workflow launchability | Project series, series detail, and ingest inventory expose `workflow_eligibility` with `policy_version=workflow_eligibility_v1`, `production_task_created=false`, runnable/blocked workflow lists, and clear reasons. | The agent or frontend has to guess whether T1, BOLD, DWI, or QSI workflows are runnable. |
| Official-source RAG | RAG uses curated official-source RAG summaries backed by `docs/rag/vendor/raw-sources/manifest.json`; raw-source manifest rows prove downloaded source URLs, hashes, source types, and raw files, but raw snapshots are not indexed as answer text. Production acceptance also requires persisted Elasticsearch hybrid search with `mode=connected`, positive `indexed_chunk_count`, positive `rag_elasticsearch_hybrid.dense_vector_dims` matching rebuild evidence, no `rag_elasticsearch_hybrid.error`, no `rag_elasticsearch_hybrid.embedding_error`, BM25, dense-vector kNN, production configured `rag_elasticsearch_hybrid.embedding_provider`, non-empty `rag_elasticsearch_hybrid.embedding_model` matching rebuild evidence, production-safe `rag_elasticsearch_hybrid.embedding_transport` matching rebuild evidence, boolean `rag_elasticsearch_hybrid.embedding_endpoint_configured` matching rebuild evidence, `rag_elasticsearch_hybrid.embedding_production_ready=true`, `rag_rebuild_elasticsearch_hybrid.lexical_retriever`, `rag_rebuild_elasticsearch_hybrid.vector_retriever`, `rag_rebuild_elasticsearch_hybrid.dense_vector_field`, and `rag_rebuild_elasticsearch_hybrid.fusion` that match `rag_elasticsearch_hybrid`, and RRF evidence from `docs/rag/contracts/elasticsearch-hybrid-search.md`. | RAG answers cite raw snapshots as answer sources, missing source ids, stale vendor pointers, unsupported container behavior, local `embedding_provider=local_hashing`, missing or mismatched `rag_elasticsearch_hybrid.dense_vector_dims`, missing or mismatched `rag_elasticsearch_hybrid.embedding_model`, missing or mismatched `rag_elasticsearch_hybrid.embedding_transport`, mismatched rebuild BM25/kNN/RRF components, `rag_elasticsearch_hybrid.embedding_error`, or only local fallback retrieval without connected persisted Elasticsearch hybrid evidence. |
| RAG answer boundaries | RAG answers state boundaries, expected outputs, non-diagnostic limits, original curated sources, and when deployed-server verification is required. | Answers imply workstation execution, diagnosis, unsupported workflow behavior, or acceptance without deployment evidence. |
| Workflow QC artifacts | Result images and reports rely on Docker/container-native QC artifacts such as fMRIPrep HTML, XCP-D HTML, DeepPrep QC, FreeSurfer snapshots, MRIQC outputs, QSIPrep/QSIRecon reports, or other container outputs. | Local code pretends to regenerate official QC, or derived scientific reports replace native QC evidence. |
| Derived report artifacts | Scientific report HTML/PNG artifacts are allowed only as generated presentation assets from result summaries, with `native_artifact=false` and `provenance.replaces_native_qc=false`. | Report-layer figures are treated as container-native QC or accepted without separate native QC evidence. |
| Runtime version lock | Production workflow registry and deployment-local scripts use fixed image tags or digests such as `pbfslab/deepprep:25.1.0`, `nipreps/fmriprep:25.2.5`, `pennlinc/xcp_d:26.0.2`, `pennlinc/qsiprep:26.0.0`, and `pennlinc/qsirecon:26.0.0`; strict acceptance rejects `:latest` or untagged execution images. | Real execution evidence omits tool/container versions, deployment scripts pull floating `latest` tags, or registry/runner contracts disagree about the image used. |
| Skills | Image Agent skills remain skill-creator-style: clear trigger rules, operating rules, reference loading, output shape, eval hints, and routing between image-agent and neuroimaging workflow skills. | Skills have stale model/provider wording, missing references, unclear routing, or no eval/backlog coverage. |
| Deployment production proof | Strict deployment acceptance runs on the deployed API server after deployment with real project/upload/task ids, local Docker/toolchain execution, and configured model gateway. The saved JSON passes `apps/api/scripts/verify_remote_smoke_acceptance.py --max-age-hours 24`; the script name is historical. It must include `--require-runtime-toolchain` evidence from the install-local runtime probe showing `runtime_toolchain_status=passed`, `runtime_toolchain.workflow_tool_execution=deployment_server_local`, `runtime_toolchain.docker_runtime_host=api_server`, and `runtime_toolchain.required_workflow_available=true` without exposing `fs_license_path`, Docker inspect tails, backend paths, or secrets. | Only workstation tests pass, the deployed model gateway is unconfigured, local containers/tools on the deployed server are unproven, real evidence ids are missing, runtime toolchain JSON is missing or leaks paths/secrets, the JSON is stale, or the offline verifier fails. |

## Deployment Acceptance Minimum

The deployed API server is the authority for install, testing, running, and production acceptance. Local workstation tests can prove code and contract intent, but they cannot prove deployment readiness. After installation, `/runtime/probe` is the portable machine-discovered contract for the server's local Docker daemon, image-agent-labeled containers, workflow image availability, FreeSurfer license presence, resource summary, and Elasticsearch configuration/reachability. All workflow scripts and Docker commands run against that server's local filesystem, local Docker daemon, local GPU visibility, local FSL/MRtrix/FreeSurfer installation, and local container image cache.

The strict remote acceptance package must include:

- Deployed package identity or commit, recorded as a privacy-safe `deployment_id`.
- `/health` returning `app=image_agent` and a privacy-safe `version` that matches the expected deployed package/version when the strict smoke gate supplies `--expected-health-version`.
- `/agent/model/status` with the OpenAI-compatible SDK gateway configured, a safe `provider_profile` such as `rawchat`, `openai`, `krill`, `deepseek`, or `glm`, a `capabilities` matrix, and `wire_api` matching the strict smoke gate's `--expected-model-wire-api` value. For the current rawchat GPT-5.5 fast-launch target this is `responses`.
- `model_smoke_status=passed` from a live `/agent/runs` smoke.
- `agent_workflow_confirmation_status=passed` showing the Agent can prepare `status=confirmation_required` for the selected workflow while `production_task_created=false`.
- `--require-agent-workflow-fingerprint-negative` evidence showing a tampered Agent workflow confirmation is blocked before task creation, with `smoke_gate.require_agent_workflow_fingerprint_negative=true`, `agent_workflow_fingerprint_negative_status=passed`, `agent_workflow_fingerprint_negative.confirmation_gate=fingerprint_mismatch`, `agent_workflow_fingerprint_negative.production_task_created=false`, and `agent_workflow_fingerprint_negative.task_created=false`.
- `--require-unknown-workflow-incubation` evidence showing an unregistered workflow request stays proposal-only, with `smoke_gate.require_unknown_workflow_incubation=true`, `unknown_workflow_incubation_status=passed`, `unknown_workflow_incubation.action_lane=toolchain_incubation`, `unknown_workflow_incubation.task_created=false`, and `unknown_workflow_incubation.production_task_created=false`.
- `--require-runtime-toolchain` evidence from the deployed API server's `/runtime/probe`; `/runtime/containers` remains a compatibility fallback for old deployments. The evidence must show `runtime_toolchain_status=passed`, `runtime_toolchain.workflow_tool_execution=deployment_server_local`, `runtime_toolchain.docker_runtime_host=api_server`, and `runtime_toolchain.required_workflow_available=true`; this evidence must be a safe summary and must not expose `fs_license_path`, Docker inspect tails, backend paths, or secrets.
- Strict launch-source guard: `--require-production-readiness --require-launched-task`, `--require-deployment-identity --require-launched-task`, and `--require-runtime-toolchain --require-launched-task` must also include `--require-agent-workflow-resume`; otherwise the live smoke CLI rejects the command. `direct_series_run` is local/diagnostic smoke only and must not be used as strict deployment launch evidence.
- RAG document/chunk thresholds, semantic index, clean raw-source policy, complete curated provenance, connected persisted Elasticsearch hybrid search evidence with positive indexed chunks and no hybrid error, safe vendor coverage catalog, and vendor pointer integrity.
- Real evidence ids with `remote_evidence_ids_status=passed`.
- Read-only task observation evidence with `smoke_gate.require_task_events=true`, `task_events_status=passed`, `task_events_event_types` including `task.status` and `task.remote_log`, `task_events_status_event_status=completed`, and `task_events_remote_log_count>0`; `/tasks/{task_id}/events` must not retry, rerun, or create production tasks.
- ObserveRepair read-only evidence from `--require-observe-repair`, with `observe_repair_status=passed`, `observe_repair_policy=read_only_observe_repair`, `observe_repair_auto_rerun_allowed=false`, `observe_repair_production_task_created=false`, `observe_repair_requires_preflight_before_retry=true`, and `observe_repair_requires_human_confirmation_before_retry=true`; `/tasks/{task_id}/observe-repair` may draft repair suggestions but must not retry, rerun, or create production tasks.
- Deterministic launch of a real registered workflow from the uploaded series through Agent resume confirmation evidence; debug-only mock workflows such as `t1_deepprep_mock` are rejected by strict deployment acceptance.
- Launchability matrix evidence from `/agent/rag/query` citation/source fields.
- `project_contract_status=passed`, `upload_inventory_contract_status=passed`, and `task_artifact_manifest_status=passed`.
- `task_result_summary.workflow_metadata.workflow_type`, `task_result_summary.workflow_metadata.runtime_workflow_type`, `task_result_summary.workflow_metadata.display_name`, `task_result_summary.workflow_metadata.capability_summary`, `task_result_summary.workflow_metadata.pipeline_stages`, `task_result_summary.workflow_metadata.primary_outputs`, `task_result_summary.workflow_metadata.qc_outputs`, `task_result_summary.workflow_metadata.report_outputs`, `task_result_summary.workflow_metadata.limitations`, `task_result_summary.workflow_metadata.agent_selectable=true`, and `task_result_summary.workflow_metadata.is_report_only=false`; result-summary workflow metadata is display/interpretation evidence only and does not replace stable `workflow_type` for task creation, confirmation fingerprints, database records, or artifact routes.
- `container_native_qc_status=passed`, served container-native QC artifact URLs, accepted curated `official_source_ids`, and enough native QC images.
- `scientific_report_artifacts_status=passed`, served report HTML/PNG URLs, and derived-presentation provenance that does not replace native QC.
- Offline verifier output from `python scripts/verify_remote_smoke_acceptance.py <remote-smoke-acceptance.json> --max-age-hours 24` with `status=passed`, including `deployment_identity_status=passed`, a `deployment_identity.deployment_id` matching `smoke_gate.deployment_id`, a privacy-safe `deployment_identity.health_version` matching `smoke_gate.expected_health_version` when supplied, `runtime_toolchain_status=passed`, `runtime_toolchain.workflow_tool_execution=deployment_server_local`, `runtime_toolchain.docker_runtime_host=api_server`, `runtime_toolchain.required_workflow_available=true`, `model_status.wire_api` matching `smoke_gate.expected_model_wire_api`, `model_status.provider_profile` matching `smoke_gate.expected_model_provider_profile`, `model_status.capabilities.model_tool_loop=true` when `smoke_gate.require_model_tool_loop=true`, `agent_workflow_confirmation.workflow_metadata.workflow_type` matching the stable confirmation workflow id, confirmation metadata display name that does not replace that id, `agent_workflow_confirmation.workflow_metadata.agent_selectable=true`, `checked.agent_workflow_confirmation_metadata_agent_selectable=true`, `task_result_summary.workflow_metadata.agent_selectable=true`, `checked.task_result_summary_metadata_agent_selectable=true`, `agent_workflow_confirmation.workflow_metadata.is_report_only=false`, `checked.agent_workflow_fingerprint_negative_status=passed`, `checked.agent_workflow_fingerprint_negative_confirmation_gate=fingerprint_mismatch`, `checked.agent_workflow_fingerprint_negative_production_task_created=false`, `checked.agent_workflow_fingerprint_negative_task_created=false`, `smoke_gate.require_elasticsearch_hybrid_rag=true`, `rag_elasticsearch_hybrid_status=passed` with `configured=true`, privacy-safe `index`, `persisted=true`, `rag_elasticsearch_hybrid.mode=connected`, positive `rag_elasticsearch_hybrid.indexed_chunk_count`, positive `rag_elasticsearch_hybrid.dense_vector_dims`, `rag_rebuild_elasticsearch_hybrid` matching the status index, indexed chunk count, dense vector dimensions, embedding provider, embedding model, embedding transport, embedding endpoint configured flag, and `rag_rebuild_elasticsearch_hybrid.lexical_retriever`, `rag_rebuild_elasticsearch_hybrid.vector_retriever`, `rag_rebuild_elasticsearch_hybrid.dense_vector_field`, and `rag_rebuild_elasticsearch_hybrid.fusion` that match `rag_elasticsearch_hybrid`, checked `rag_elasticsearch_hybrid_error_absent=true`, checked `rag_elasticsearch_hybrid_embedding_error_absent=true`, checked `rag_rebuild_elasticsearch_hybrid_error_absent=true`, checked `rag_rebuild_elasticsearch_hybrid_embedding_error_absent=true`, `rag_elasticsearch_hybrid.embedding_provider`, `rag_elasticsearch_hybrid.embedding_model`, `rag_elasticsearch_hybrid.embedding_transport`, `rag_elasticsearch_hybrid.embedding_endpoint_configured`, `rag_elasticsearch_hybrid.embedding_production_ready=true`, `rag_rebuild_elasticsearch_hybrid.embedding_production_ready=true`, and `fusion=rrf`, and `rag_elasticsearch_hybrid_query_status=passed` with `rag_elasticsearch_hybrid_query_mode=elasticsearch_hybrid`, `rag_elasticsearch_hybrid_query_retrieval_source=elasticsearch_hybrid`, `rag_elasticsearch_hybrid_query_source=docs/rag/contracts/elasticsearch-hybrid-search.md`, `rag_elasticsearch_hybrid_query_dense_vector_field=embedding`, positive query citation/score evidence, and query-time index/dense-vector/embedding provider/model/transport/endpoint/production-ready evidence matching the connected status evidence; the query-time dense-vector field matches `rag_elasticsearch_hybrid.dense_vector_field`.

`skipped_missing_model_config` is not production acceptance. Health, RAG, or local pytest success without a configured remote model gateway is not enough to release the frontend gate.

`/deployment.fast_launch_readiness` is the operator-facing summary for this gate. It is `ready=true` only when:

- `checks.model_gateway_target.status=passed` for `provider_profile=rawchat`, `wire_api=responses`, `model=gpt-5.5`, and `model_tool_loop=true`.
- `checks.agent_task_boundary.status=passed`, with chat limited to read/explain/recommend and actual Agent-selectable fixed workflow launch routed through the server-side resume confirmation path rather than direct `/series/{series_id}/run`.
- `checks.upload_workflow_result_contract.status=passed`, listing upload, series, workflow launch, output, result-summary, and artifact-manifest contracts.
- `checks.production_deployment.status=passed`, with `/deployment.production_readiness.required=true`, `.ready=true`, and `deployment_scope` set to either `public_internet` or `private_network` according to the intended install target.
- `checks.strict_remote_acceptance.status=passed`, backed by a privacy-safe `IMAGE_AGENT_STRICT_REMOTE_ACCEPTANCE_ID` from a strict remote smoke JSON verified inside the freshness window.
- `checks.rag_elasticsearch_hybrid.status=passed`, based on the current deployment's `/agent/rag/status` evidence: Elasticsearch hybrid search is configured, persisted, `mode=connected`, uses a privacy-safe index, has positive indexed chunks and dense-vector dimensions, uses production-ready non-local embeddings with a non-empty model, exposes a production-safe `embedding_transport`, exposes only the boolean `embedding_endpoint_configured` rather than the endpoint URL, has `fusion=rrf`, has `fast_launch_readiness.checks.rag_elasticsearch_hybrid.lexical_retriever=standard`, `fast_launch_readiness.checks.rag_elasticsearch_hybrid.vector_retriever=knn`, and `fast_launch_readiness.checks.rag_elasticsearch_hybrid.dense_vector_field=embedding`, and exposes no hybrid or embedding error. The fast-launch UI must not infer RAG readiness from the remote acceptance id alone.

When that RAG check is blocked, `/deployment.fast_launch_readiness.checks.rag_elasticsearch_hybrid.blocking_codes` exposes only stable, privacy-safe reason codes such as `rag_index_engine_not_elasticsearch_hybrid`, `rag_hybrid_mode_not_ready`, `rag_hybrid_lexical_retriever_not_standard`, `rag_hybrid_vector_retriever_not_knn`, `rag_hybrid_dense_vector_field_not_embedding`, `rag_embedding_endpoint_not_configured`, or `rag_embedding_error_present`. These codes are intended for operator diagnostics and frontend disable states. They must not include endpoint URLs, API keys, backend paths, patient data, raw log text, or raw vendor snapshot paths.

Before strict smoke mutates remote state, the release gate and stale-task apply handoff must run `verify_elasticsearch_hybrid_prerequisites.py` as a read-only preflight. It checks whether the deployment env has explicit Elasticsearch URL, optional privacy-safe `IMAGE_AGENT_ELASTICSEARCH_INDEX`, and production RAG embedding provider/model/base URL, then requires the current `/agent/rag/status` to show Elasticsearch hybrid search configured, persisted, `mode=connected`, a privacy-safe index, `rag_status_hybrid_index_matches_env=true` when an explicit index is configured, positive indexed chunk count and dense-vector dimensions, `rag_status_hybrid_lexical_retriever=standard`, `rag_status_hybrid_vector_retriever=knn`, `rag_status_hybrid_dense_vector_field=embedding`, `fusion=rrf`, `rag_status_hybrid_official_rrf_source_present=true`, non-local production embedding provider/model/transport, `embedding_endpoint_configured=true`, `embedding_production_ready=true`, and no hybrid or embedding error. The preflight output is limited to booleans, safe symbols, and counts; it must not print API keys, endpoint URLs, patient data, backend paths, raw official-source URL lists, or raw error text. Passing this preflight is still not release acceptance because it does not replace `/agent/rag/query`, strict remote smoke, or the saved-JSON verifier.

Strict remote smoke and the saved-JSON verifier must also prove query-time hybrid components: `rag_elasticsearch_hybrid_query_lexical_retriever=standard`, `rag_elasticsearch_hybrid_query_vector_retriever=knn`, `rag_elasticsearch_hybrid_query_dense_vector_field=embedding`, and `rag_elasticsearch_hybrid_query_fusion=rrf`. The query-time hybrid components match `rag_elasticsearch_hybrid` so a release cannot pass by proving only connected status while the actual `/agent/rag/query` path omits BM25/kNN/RRF evidence.

Strict remote smoke and the saved-JSON verifier must also prove rebuild hybrid components: `rag_rebuild_elasticsearch_hybrid.lexical_retriever`, `rag_rebuild_elasticsearch_hybrid.vector_retriever`, `rag_rebuild_elasticsearch_hybrid.dense_vector_field`, and `rag_rebuild_elasticsearch_hybrid.fusion` match `rag_elasticsearch_hybrid`; status-only or query-only BM25/kNN/RRF evidence is not enough for release acceptance.

Strict remote smoke now saves `fast_launch_readiness_status=pre_acceptance` while the only allowed blocker is the not-yet-applied strict remote acceptance evidence. The offline verifier re-checks `fast_launch_readiness.checks.rag_elasticsearch_hybrid.status=passed` against the same Elasticsearch hybrid status evidence. The Git-managed bootstrap script then re-runs that verifier in `--config-only` mode and writes the `IMAGE_AGENT_STRICT_REMOTE_ACCEPTANCE_*` env lines that let `/deployment.fast_launch_readiness` become final `ready` after restart. This keeps the frontend/operator gate tied to the deployment evidence package instead of a separate hand-written readiness label.

Apply the remote acceptance environment values from the already-passed verifier instead of hand-writing them:

```bash
python scripts/bootstrap_image_agent.py \
  --skip-elasticsearch-hybrid \
  --skip-workflow-images \
  --config-only \
  --strict-acceptance-json <remote-smoke-acceptance.json> \
  --strict-acceptance-max-age-hours 24 \
  --apply
```

This writes only `IMAGE_AGENT_STRICT_REMOTE_ACCEPTANCE_STATUS=passed` and a privacy-safe `IMAGE_AGENT_STRICT_REMOTE_ACCEPTANCE_ID` derived from the strict smoke `deployment_id`. These fields are a summary of launch readiness, not a replacement for the saved remote smoke JSON or the offline verifier. A local rawchat pass keeps development moving, but formal release still needs the remote evidence id.
The release gate command plan and stale-task apply request both require the Elasticsearch hybrid prerequisite preflight before strict smoke and this bootstrap config-only apply step after strict JSON verification, so the fast-launch UI state is derived from the same evidence package rather than a hand-written acceptance label.

## BMAD-Inspired Operating Model

Use the BMAD Method as process guidance, not as a local installation requirement. The upstream project describes structured workflows across analysis, planning, architecture, and implementation, with specialized agents for roles such as PM, Architect, Developer, UX, and testing. For this repo, keep the split practical:

- PM/readiness: maintain this product gate, epics, and acceptance status.
- Architect: keep SDK-like module boundaries and API/result contracts stable.
- RAG curator: maintain official downloaded sources, curated summaries, source ids, and answer boundaries.
- Skill maintainer: keep Image Agent skills aligned with skill-creator-style structure.
- Workflow gate reviewer: verify fixed workflow launch still flows through registry, preflight, human confirmation, fingerprint, `task_service.create_series_task()`, and the pipeline runner.
- Workflow QC reviewer: verify container-native QC artifact provenance and derived report boundaries.
- QA/release evidence reviewer: verify local mock/control-plane tests separately from deployed-server strict smoke, runtime toolchain, task-events, and freshness evidence.
- Operations: maintain work logs, git backups, remote acceptance evidence, and no-secret/no-path-leak checks.

## Current Status

As of 2026-06-22, the private product-usable launch gate has passed on yyf.
This is not public internet exposure; it is the target/private installation
being complete and usable. The live API is running from
`/home/yyf/project/image_agent_releases/codex-es-hybrid-runtime-probe-rootfix10-20260619T154306Z`
with shared root `/home/yyf/project/image_agent`. Strict smoke evidence is
`/tmp/image_agent_private_launch_acceptance_task137_final_20260622.json`, and
offline verifier evidence is
`/tmp/image_agent_private_launch_acceptance_task137_final_verify_20260622.json`
with `status=passed`. The evidence id is
`codex-private-launch-task137-20260622`, reusing the completed real chain for
project `28`, upload session `11`, uploaded series `50`, and fixed workflow
task `137` (`workflow_type=t1_deepprep_anat_report`) without rerunning the
workflow. After Git-managed strict-acceptance env emission and active-task
drain, the API restarted from PID `3528840` to PID `3538435`. `/deployment`
now reports `production_readiness.status=ready`,
`production_readiness.deployment_scope=private_network`,
`fast_launch_readiness.status=ready`, no blocking reasons,
`fast_launch_readiness.checks.strict_remote_acceptance.status=passed`,
`fast_launch_readiness.checks.rag_elasticsearch_hybrid.status=passed`, and
`fast_launch_readiness.checks.model_gateway_target.status=passed` with rawchat
GPT-5.5 Responses and `trust_env_proxy=false`. The deployment readiness
snapshot is saved at
`/tmp/image_agent_private_launch_deployment_ready_20260622.json`.

As of 2026-06-11, the live remote API is serving committed release `f57a2ea`
from release overlay
`/home/yyf/project/image_agent_releases/codex-f57a2ea-20260611T023456/apps/api`.
The dirty remote main worktree is no longer the serving path for the accepted
API process.

Strict remote acceptance passed after that release-overlay restart. The
saved evidence is
`/tmp/image_agent_task118_live8000_post_restart_f57a2ea_20260611.json`, and the
offline verifier reported `status=passed` for model smoke, real evidence ids,
RAG vendor pointer integrity, launchability query citation, project/upload
contracts, artifact manifest, container-native QC, and derived scientific report
artifacts. That evidence predates the timestamp-freshness verifier option added
later on 2026-06-11, so the frontend release gate still requires a new saved
JSON that passes `--max-age-hours 24` after normal restart.

Frontend design is still held until the final operational cleanup is resolved:
the restart used `IMAGE_AGENT_ALLOW_RESTART_WITH_ACTIVE_TASKS=1` because legacy
tasks `83` and `84` remain in `running` state even though they appear stale.
An auditable stale-task reconciliation tool now exists in
`apps/api/scripts/reconcile_stale_tasks.py`, but production task rows should be
changed only after an operator reviews the dry-run output and approves apply
mode. The tool now emits a dry-run `approval_fingerprint`; apply mode can read
the reviewed report via `--approval-json` and require that fingerprint before
mutating rows so scoped task ids and container-label evidence cannot drift
silently between review and apply. The dry-run report can be checked with
`apps/api/scripts/verify_stale_task_approval.py` before apply approval. After
approved apply, the apply JSON and a second scoped dry-run must be checked with
`apps/api/scripts/verify_stale_task_resolution.py`; that verifier must print
`status=passed`, reject `log_path`, and reject backend absolute paths anywhere
in the saved stale-task evidence. The stale-task approval/apply/resolution
artifacts must include timezone-aware `generated_at` timestamps, and the
resolution `generated_at` must be after or equal to apply `generated_at` before
a normal restart without the active-task override is accepted. In short,
stale-task evidence must pass a `max_age_hours` freshness limit through the
approval and resolution verifier scripts before it can unblock normal restart
or frontend release evidence. A remote dry-run from non-live release
`118c407` reported tasks `83` and `84` as stale candidates older than 531
hours, and a shared-env Docker label check returned no running labelled Image
Agent task ids. A fresh non-live release overlay dry-run on 2026-06-11 reported
`container_check_status=passed`, `running_container_task_ids=[]`, scoped
`stale_candidates=[83,84]`, and
`approval_fingerprint=139113571daf0137a3e34be526fd25ccaa8066aed725ab7c0b846cfc7eb3abd0`,
saved on the remote host at
`/tmp/image_agent_stale_tasks_83_84_fingerprint_dry_run_20260611T1215.json`.
As of the 2026-06-13 remote read-only dry-run, fresh approval evidence now exists
against the same scoped task ids. The dry-run JSON is saved on the remote host at
`/tmp/image_agent_stale_tasks_83_84_dry_run_20260613T1640Z.json`; the current
local verifier checked that file with `--max-age-hours 24` and reported
`status=passed`, `checked.generated_at_utc=2026-06-13T16:40:24.758668+00:00`,
`checked.container_check_status=passed`,
`checked.running_container_task_ids=[]`, and the same approval fingerprint
`139113571daf0137a3e34be526fd25ccaa8066aed725ab7c0b846cfc7eb3abd0`. This is
operator-review evidence only: approved apply has not been run, the post-apply
`verify_stale_task_resolution.py --require-empty-active --max-age-hours 24`
gate has not passed, and a normal restart plus fresh strict smoke evidence are
still required.
To avoid using stale verifier scripts during that operator-approved path, a
remote gate verifier overlay now exists at
`/home/yyf/project/image_agent_releases/codex-gate-verifiers-efca895b-20260613T165132`.
This non-live overlay was copied from the prior stale-task tooling overlay and
then updated from local commit `efca895b`; it now exposes `--max-age-hours` on
both stale-task verifier CLIs. On the remote server, the overlay verified the
fresh dry-run JSON above with `status=passed`, and its stale-task test slice
reported `40 passed`. This overlay is a prepared verifier/apply tooling base,
not production acceptance and not a service restart.
The same remote gate verifier overlay has also been refreshed with current
strict smoke gate scripts from local commit `7b12e615`. Its
`verify_remote_smoke_acceptance.py -h` output exposes `--max-age-hours` and
`--now-utc`, and the remote strict-smoke test slice
`tests/test_verify_remote_smoke_acceptance.py tests/test_smoke_remote_agent.py`
reported `179 passed`. This prepares the post-restart strict smoke acceptance
tooling but does not replace running a fresh strict remote acceptance smoke
after normal restart.
The restart wrapper now also has a non-destructive preflight mode:
`IMAGE_AGENT_RESTART_PREFLIGHT_ONLY=1`. It runs the active-task drain and
port-owner checks without stopping or starting the API; a clean preflight prints
`restart_preflight:ok`. Use it after stale-task resolution and before the normal
restart, so restart blockers are caught before any service mutation.
The non-live remote gate verifier overlay has been updated with this restart
preflight mode and its remote restart-script test slice reported `6 passed`.
Before stale-task apply, the preflight-only command still fails at the drain gate
with active tasks `83` and `84`, which confirms the current blocker without
stopping or starting the API.
The full post-authorization command sequence is now captured in
`docs/deployment/remote-release-gate-command-plan.json` and checked by
`apps/api/scripts/verify_release_gate_command_plan.py`. That machine-checkable
plan fixes the required order: fresh stale-task approval verification,
operator-approved apply, post-apply clean dry-run, resolution verification,
`IMAGE_AGENT_RESTART_PREFLIGHT_ONLY=1` reaching `restart_preflight:ok`, normal
restart without `IMAGE_AGENT_ALLOW_RESTART_WITH_ACTIVE_TASKS=1`, strict remote
smoke, and offline strict smoke JSON verification with `--max-age-hours 24`.
It is an execution plan and guardrail, not evidence that apply, restart, or
strict smoke acceptance has already happened.
The plan also includes `stale_task_approval_refresh` for
`approval_json_missing_or_older_than_24h`; that command creates a fresh
read-only `--check-containers --task-id 83 --task-id 84` dry-run and must be
operator-reviewed before it replaces the approval JSON used by apply.
The refresh/apply/post-apply dry-run commands now load the remote environment
with `set -a; . /home/yyf/project/image_agent/.env; set +a` before Docker label
checks, because `IMAGE_AGENT_SUDO_PASSWORD` is required for those checks. A
fresh read-only approval refresh on 2026-06-14 saved
`/tmp/image_agent_stale_tasks_83_84_dry_run_20260614T080202Z.json`; the remote
approval verifier reported `status=passed`,
`checked.generated_at_utc=2026-06-14T08:02:02.843606+00:00`,
`checked.container_check_status=passed`,
`checked.running_container_task_ids=[]`, and the same approval fingerprint
`139113571daf0137a3e34be526fd25ccaa8066aed725ab7c0b846cfc7eb3abd0`.
The non-live remote gate verifier overlay was refreshed with local commit
`dc5e9471`; its command-plan verifier reported `status=passed` against the new
approval JSON path, and the focused remote readiness test slice reported
`6 passed`.
Before the operator-approved mutation, use
`apps/api/scripts/build_stale_task_apply_request.py` to turn the verified
approval dry-run into a `stale_task_apply_approval` JSON handoff. That request
records the reviewed `approval_fingerprint`, exact env-loading apply command,
required post-apply clean verification, preflight-only restart, normal restart,
strict remote smoke, offline strict smoke JSON verification, and
`authorization_required=true`; generating it does not run `--apply`.
The non-live remote overlay generated an actual approval request at
`/tmp/image_agent_stale_tasks_83_84_apply_request_20260614T080202Z.json` with
`request_type=stale_task_apply_approval`,
`authorization_required=true`, `approval_expires_at_utc=2026-06-15T08:02:02.843606+00:00`,
and follow-up ids including `restart_api_normally` and
`run_strict_remote_smoke_acceptance`.
Before approval, check that request with
`apps/api/scripts/verify_stale_task_apply_request.py`; the verifier must report
`status=passed`, recompute the same approval expiry, and only statically
validate the request JSON without running the embedded apply, restart, or smoke
commands.
The non-live remote overlay verified
`/tmp/image_agent_stale_tasks_83_84_apply_request_20260614T080202Z.json` with
`verify_stale_task_apply_request.py`; it reported `status=passed`,
`checked.authorization_required=true`, and
`checked.verified_approval_generated_at_utc=2026-06-14T08:02:02.843606+00:00`,
with `checked.expires_at_utc=2026-06-15T08:02:02.843606+00:00`.
That expiry is computed from `verified_approval.checked.generated_at_utc +
freshness_hours` and is also repeated as the top-level
`approval_expires_at_utc` field in the saved apply request.
The release plan records the same rule as `approval_request_requirements` so
the approval request shape stays machine-checkable.
The non-live remote gate verifier overlay has also been refreshed with this
command plan slice from local commit `dc1bdaf9`; on the remote server,
`verify_release_gate_command_plan.py docs/deployment/remote-release-gate-command-plan.json`
reported `status=passed`, and the focused remote test slice
`tests/test_release_gate_command_plan.py` plus the product-readiness gate test
reported `4 passed`. This proves the operator command plan is present and
machine-checkable on the remote verifier overlay, but it still does not mutate
tasks, restart the service, or run strict smoke acceptance.
The same overlay was then refreshed with local commit `cd9f4a3a`, including
the stale-task approval refresh path; the remote command-plan verifier reported
`checked.approval_refresh_required_when=approval_json_missing_or_older_than_24h`
with `status=passed`, and the focused remote test slice reported `5 passed`.
As of 2026-06-16, that 2026-06-14 approval and the generated
`/tmp/image_agent_stale_tasks_83_84_apply_request_20260614T080202Z.json` are
outside the 24 hour freshness window. The current
`docs/deployment/remote-release-gate-command-plan.json` therefore has
`status=approval_refresh_required`; its verifier reports
`checked.approval_json_status=refresh_required`, preserves the expired path only
as `previous_approval_json`, and uses `<fresh_reviewed_approval_json>` in the
verify/apply commands. The previous approval JSON must not be used for apply.
Before any remote mutation, the operator must run the documented
`stale_task_approval_refresh`, review the refreshed dry-run output and
`approval_fingerprint`, then run `build_release_gate_command_plan.py` to
materialize an `operator_authorization_required` plan from the reviewed path
instead of editing `<fresh_reviewed_approval_json>` by hand. If that builder
reads a copied local approval file, `--approval-json-command-path` must still be
the server-side `/tmp/image_agent_*.json` path embedded into the apply commands;
local workstation paths are rejected from the command plan. After refresh, the
same verifier accepts only a plan whose
`approval_json_state.status=fresh_reviewed` and
`approval_json_state.approval_expires_at_utc` is still in the future; expired
reviewed approval JSON must return the plan to the refresh path. Once those
stale task records are resolved through this approved flow, normal restarts
should no longer require overriding the active-task drain gate.
The strict remote smoke step now also requires `--require-uploaded-series` with
`--upload-nifti-file <remote_nifti_file>`: the smoke runner must upload that
file through `/projects/{project_id}/upload`, validate the returned
`workflow_eligibility`, record `uploaded_series_status=passed`, and use the
returned series id for Agent workflow confirmation/resume launch evidence.
Supplying an already-known
`--launch-series-id <uploaded_series_id>` is no longer sufficient evidence for
the fastest-launch main chain, because it proves workflow launch but not the
actual upload-to-series path.
