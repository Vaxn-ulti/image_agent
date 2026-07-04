# Remote Agent Acceptance Evidence Template

Use this template only for real remote acceptance runs after the current local package has been deployed to `/home/yyf/project/image_agent`, the remote model gateway is configured, and no queued or running production tasks are active.

This is an evidence checklist, not a substitute for running the commands. `skipped_missing_model_config` is not production acceptance.

## Run Identity

- Date/time UTC:
- Operator:
- Remote host:
- remote git branch/status:
- deployed commit or package id:
- deployed file hashes:
  - `apps/api/scripts/smoke_remote_agent.py`:
  - `tools/restart_remote_image_agent_api.sh`:
  - `apps/api/app/workflows/remote_scripts.py`:
- Backend env notes:
  - `BACKEND_RUNTIME_MODE=remote`
  - `/agent/model/status` reports `configured=true`
  - model gateway tunnel/status:

## Pre-Restart Safety

Paste exact command output:

```text
ssh -o BatchMode=yes remote_server "curl -fsS http://127.0.0.1:8000/health"
ssh -o BatchMode=yes remote_server "curl -fsS http://127.0.0.1:8000/agent/model/status"
ssh -o BatchMode=yes remote_server "curl -fsS http://127.0.0.1:8000/agent/rag/status"
```

Required evidence:

- `/health` returns `app=image_agent`.
- `/agent/model/status` reports `configured=true`.
- RAG reports `semantic_index=true`.
- Raw source policy reports no missing files, hash mismatches, or indexed raw sources.
- Curated vendor provenance reports `curated_provenance_ok=true` and `curated_provenance_issues=[]`.

## Stale Task Resolution Evidence

Use this section only when a previous restart was blocked by stale
`queued`/`running` task rows. Attach the reviewed dry-run JSON, apply JSON, and
post-apply dry-run JSON:

```bash
cd /home/yyf/project/image_agent_releases/<accepted-release>/apps/api
PYTHONPATH=. /home/yyf/project/image_agent/apps/api/.venv/bin/python scripts/verify_stale_task_approval.py /tmp/image_agent_stale_tasks_<ids>_dry_run.json --task-id <id> --task-id <id> --max-age-hours 24
PYTHONPATH=. /home/yyf/project/image_agent/apps/api/.venv/bin/python scripts/verify_stale_task_resolution.py --apply-json /tmp/image_agent_stale_tasks_<ids>_apply.json --resolution-json /tmp/image_agent_stale_tasks_<ids>_resolved_dry_run.json --task-id <id> --task-id <id> --require-empty-active --max-age-hours 24
```

Required evidence before normal restart:

- approval verifier prints `status=passed` with `--max-age-hours 24`;
- resolution verifier prints `status=passed` with `--max-age-hours 24`;
- apply JSON has `updated_task_ids` exactly matching the approved task ids;
- post-apply dry-run has no target task ids in `active_tasks` or `stale_candidates`;
- `running_container_task_ids=[]` and `blocked_task_ids=[]`.

## Restart Drain Evidence

Run from the deployed remote repo:

```bash
cd /home/yyf/project/image_agent
bash tools/restart_remote_image_agent_api.sh
```

Paste output and confirm it contains restart drain evidence:

- `active_task_drain:ok`
- `port_owner:image_agent` or `port_owner:none` before start
- `health:ok app=image_agent`
- no foreign port owner refusal
- no active task refusal
- no post-restart health timeout

## Strict Smoke Acceptance JSON

Run from the deployed remote backend:

```bash
cd /home/yyf/project/image_agent/apps/api
source .venv/bin/activate
python scripts/smoke_remote_agent.py \
  --api-base http://127.0.0.1:8000 \
  --require-model \
  --expected-model-wire-api responses \
  --expected-model-provider-profile rawchat \
  --require-model-tool-loop \
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

Attach the strict smoke acceptance JSON and verify it contains:

- `model_smoke_status=passed`
- `smoke_gate.expected_model_wire_api=responses` and `model_status.wire_api=responses`
- `smoke_gate.expected_model_provider_profile=rawchat` and `model_status.provider_profile=rawchat`
- `smoke_gate.require_model_tool_loop=true` and `model_status.capabilities.model_tool_loop=true`
- `model_status.configured=true`, with only safe model gateway summary fields. It must not contain API keys, tokens, secrets, passwords, authorization headers, a `base_url` with embedded credentials, or nested deployment command details. `model_status.deployment`, when present, may only describe safe backend runtime mode and model gateway access.
- `deployment_identity_status=passed`
- `deployment_identity.deployment_id` matches `smoke_gate.deployment_id` and is a short release id or commit, not a full remote path
- `deployment_identity.health_version` is present, is a short privacy-safe version string, and matches `smoke_gate.expected_health_version` when supplied
- `production_readiness_status=passed`
- `production_readiness.required=true`, `production_readiness.ready=true`, `production_readiness.status=ready`, and `production_readiness.blocking_reasons=[]`
- `fast_launch_readiness_status=pre_acceptance`, `fast_launch_readiness.ready=false` only because strict acceptance env has not yet been exported, and `fast_launch_readiness.checks.rag_elasticsearch_hybrid.status=passed` with the same connected Elasticsearch hybrid index, mode, chunk count, vector dimensions, embedding provider, and embedding model as `rag_elasticsearch_hybrid`
- `--require-runtime-toolchain` was included in the strict smoke command
- `runtime_toolchain_status=passed`
- `runtime_toolchain.workflow_tool_execution=deployment_server_local`
- `runtime_toolchain.docker_runtime_host=api_server`
- `runtime_toolchain.required_workflow_available=true`
- `runtime_toolchain` does not expose `fs_license_path`, Docker inspect tails, backend paths, or secrets
- Strict launch-source guard: `--require-production-readiness --require-launched-task`, `--require-deployment-identity --require-launched-task`, and `--require-runtime-toolchain --require-launched-task` must also include `--require-agent-workflow-resume`; otherwise the live smoke CLI rejects the command. `direct_series_run` is local/diagnostic smoke only and must not be used as strict launch evidence.
- `agent_run_id`
- `agent_project_context_status=passed`
- `agent_run_project_id` matches `smoke_gate.project_id`
- `agent_workflow_confirmation_status=passed`
- `agent_workflow_confirmation.status=confirmation_required`, `intent=run_workflow`, `selected_skill=image-agent-workflow-runner`, and `production_task_created=false`
- `agent_workflow_confirmation.project_id`, `series_id`, and `workflow_type` match the strict smoke project, uploaded/launched series, and deterministic backend task workflow
- `agent_workflow_confirmation.workflow_metadata.workflow_type` matches the stable confirmation `workflow_type`; `workflow_metadata.display_name` is a descriptive display label, not the machine id; `agent_workflow_confirmation.workflow_metadata.agent_selectable=true`; `workflow_metadata.is_report_only=false`
- `smoke_gate.require_agent_workflow_resume=true`
- `smoke_gate.require_agent_workflow_fingerprint_negative=true`
- `agent_workflow_fingerprint_negative_status=passed`
- `agent_workflow_fingerprint_negative.confirmation_gate=fingerprint_mismatch`
- `agent_workflow_fingerprint_negative.production_task_created=false`
- `agent_workflow_fingerprint_negative.task_created=false`
- `--require-unknown-workflow-incubation` was included in the strict smoke command
- `smoke_gate.require_unknown_workflow_incubation=true`
- `unknown_workflow_incubation_status=passed`
- `unknown_workflow_incubation.action_lane=toolchain_incubation`
- `unknown_workflow_incubation.task_created=false`
- `unknown_workflow_incubation.confirmation_created=false`
- `unknown_workflow_incubation.task_creation_allowed=false`
- `unknown_workflow_incubation.forbidden_actions` includes `confirmation_creation`, `production_task_creation`, and `pipeline_runner_launch`
- `unknown_workflow_incubation.production_task_created=false`
- `agent_workflow_resume_status=passed`
- `agent_workflow_resume.status=task_created`, `production_task_created=true`, and `confirmation_gate=fingerprint_verified`
- `agent_workflow_resume.task_id`, `project_id`, `series_id`, and `workflow_type` match the strict smoke task, project, completed task series, and completed task workflow
- `intent`
- `selected_skill`
- `remote_evidence_ids_status=passed`
- `upload_inventory_completion_status=passed`
- `upload_inventory_status=completed`
- `uploaded_series_status=passed`
- `uploaded_series.project_id` matches `smoke_gate.project_id`
- `uploaded_series.series_id` matches `task_status.series_id`
- `launched_task_status=passed`
- `launched_task.task_id` matches `smoke_gate.task_id`
- `launched_task.project_id` matches `smoke_gate.project_id`
- `launched_task.series_id` matches `task_status.series_id`
- `launched_task.workflow_type` matches `task_status.workflow_type`
- `launched_task.launch_source=agent_workflow_resume`
- `task_status_status=passed`
- `task_status.status=completed`, `task_status.task_id` matches `smoke_gate.task_id`, `task_status.project_id` matches `smoke_gate.project_id`, and `task_status` does not expose backend paths such as `log_path`
- `--require-task-events` was included in the strict smoke command
- `smoke_gate.require_task_events=true`
- `task_events_status=passed`
- `task_events_task_id` matches `smoke_gate.task_id`
- `task_events_event_types` includes `task.status` and `task.remote_log`
- `task_events_status_event_status=completed`
- `task_events_remote_log_count` is greater than zero, `task_events_remote_log_source_stages` are privacy-safe symbols, and `task_events_main_log_tail_present=true`
- task event evidence is read-only observation from `/tasks/{task_id}/events`; it must not retry, rerun, or create production tasks
- `--require-observe-repair` was included in the strict smoke command
- `observe_repair_status=passed`
- `observe_repair_policy=read_only_observe_repair`
- `observe_repair_auto_rerun_allowed=false`
- `observe_repair_production_task_created=false`
- `observe_repair_requires_preflight_before_retry=true` and `observe_repair_requires_human_confirmation_before_retry=true`
- `task_workflow_selection_status=passed`
- `task_workflow_selection.workflow_type` matches `task_status.workflow_type`, `task_workflow_selection.series_id` matches `task_status.series_id`, and `task_workflow_selection.matched_runnable_workflow=true`
- `rag_launchability_matrix_status=passed`
- `rag_launchability_matrix_source`
- `rag_launchability_query_status=passed`
- `rag_launchability_query_intent`
- `rag_launchability_query_source`
- `rag_document_count` at or above the threshold
- `rag_chunk_count` at or above the threshold
- `rag_semantic_index=true`
- raw-source policy fields with no missing files, hash mismatches, or indexed raw sources
- `manifest_schema_version`
- `source_count`
- `vendor_doc_count`
- `curated_provenance_ok=true`
- `curated_provenance_issues=[]`
- `rag_raw_sources.curated_sources` lists each curated vendor summary with `complete=true`, `raw_source_ids`, `source_urls`, and `raw_files`
- each `curated_sources` item reports `manifest_backed=true`, `source_url_backed=true`, and non-empty `source_types`
- `raw_source_ids` are manifest ids, not artifact `official_source_ids`
- `rag_vendor_pointer_integrity_status=passed`
- `rag_vendor_pointer_integrity_pointer_count` greater than zero
- `rag_vendor_pointer_integrity_issue_count=0`
- `rag_vendor_pointer_integrity_referenced_vendor_docs` lists the curated vendor docs referenced by RAG workflows/contracts
- the vendor pointer integrity gate proves curated vendor summaries are answer sources; raw snapshots are provenance evidence only
- `smoke_gate.require_elasticsearch_hybrid_rag=true`
- `rag_elasticsearch_hybrid_status=passed`
- `rag_rebuild_elasticsearch_hybrid` is present, connected, and its `index`, `indexed_chunk_count`, `dense_vector_dims`, `embedding_provider`, `embedding_model`, `lexical_retriever`, `vector_retriever`, `dense_vector_field`, and `fusion` match `rag_elasticsearch_hybrid`; its `configured=true` and `embedding_production_ready` are also true
- `rag_elasticsearch_hybrid.engine=elasticsearch`, `configured=true`, privacy-safe `index`, `persisted=true`, `mode=connected`, positive `indexed_chunk_count`, positive `dense_vector_dims`, `lexical_retriever=standard`, `vector_retriever=knn`, `dense_vector_field=embedding`, production configured `embedding_provider`, non-empty `embedding_model`, `embedding_production_ready=true`, and `fusion=rrf`
- `rag_elasticsearch_hybrid.error`, `rag_elasticsearch_hybrid.embedding_error`, `rag_rebuild_elasticsearch_hybrid.error`, and `rag_rebuild_elasticsearch_hybrid.embedding_error` are absent
- `rag_elasticsearch_hybrid.official_rrf_source_present=true`; the live backend `/agent/rag/status.hybrid_search.official_sources` must contain the Elastic RRF documentation URL from `docs/rag/contracts/elasticsearch-hybrid-search.md`, but strict smoke and verifier evidence must not save any raw `official_sources` list
- `rag_elasticsearch_hybrid_query_status=passed`
- `rag_elasticsearch_hybrid_query_mode=elasticsearch_hybrid`
- `rag_elasticsearch_hybrid_query_retrieval_source=elasticsearch_hybrid`
- `rag_elasticsearch_hybrid_query_source=docs/rag/contracts/elasticsearch-hybrid-search.md`
- `rag_elasticsearch_hybrid_query_index`, `rag_elasticsearch_hybrid_query_lexical_retriever=standard`, `rag_elasticsearch_hybrid_query_vector_retriever=knn`, `rag_elasticsearch_hybrid_query_dense_vector_field=embedding`, `rag_elasticsearch_hybrid_query_fusion=rrf`, `dense_vector_dims`, `embedding_provider`, `embedding_model`, and `embedding_transport` match `rag_elasticsearch_hybrid`; the query-time dense-vector field matches `rag_elasticsearch_hybrid.dense_vector_field`, and query-time hybrid components match `rag_elasticsearch_hybrid`
- `rag_elasticsearch_hybrid_query_embedding_endpoint_configured=true`
- `rag_elasticsearch_hybrid_query_embedding_production_ready=true`
- local `.rag_index/elasticsearch/*` contract files are useful development evidence, but production acceptance requires the deployed API to report a persisted Elasticsearch hybrid index
- `rag_vendor_coverage_catalog_status=complete`
- `rag_vendor_coverage_catalog_vendor_doc_count` greater than zero
- `rag_vendor_coverage_catalog_complete_vendor_doc_count` equals the vendor doc count
- `vendor_coverage_catalog` is present as the operator-facing summary and does not expose `manifest_path`, `persist_dir`, `raw_snapshots`, `raw_files`, or `sha256`
- `vendor_coverage_catalog.vendors` and `rag_raw_sources.curated_sources` must exactly match by `vendor_doc`, with no missing or extra vendor docs
- for each matched vendor doc, `complete`, `manifest_backed`, `source_url_backed`, `source_types`, and `raw_source_ids` stay consistent between `vendor_coverage_catalog.vendors` and `rag_raw_sources.curated_sources`
- `project_contract_status=passed`
- `series_with_workflow_eligibility` greater than zero
- `upload_inventory_contract_status=passed`
- `upload_inventory_series_with_workflow_eligibility` greater than zero
- `task_artifact_manifest_status=passed`
- `task_result_summary_status=passed`
- `task_result_summary.task_id` matches `smoke_gate.task_id`
- `task_result_summary.workflow_type` matches `task_status.workflow_type`
- `task_result_summary.workflow_metadata.workflow_type` matches the result-summary `workflow_type`
- `task_result_summary.workflow_metadata.runtime_workflow_type` matches `task_status.runtime_workflow_type`
- `task_result_summary.workflow_metadata.display_name` is a descriptive label that does not replace the machine id
- `task_result_summary.workflow_metadata.capability_summary`, `task_result_summary.workflow_metadata.pipeline_stages`, `task_result_summary.workflow_metadata.primary_outputs`, `task_result_summary.workflow_metadata.qc_outputs`, `task_result_summary.workflow_metadata.report_outputs`, and `task_result_summary.workflow_metadata.limitations` are present
- `task_result_summary.workflow_metadata.agent_selectable=true`
- `task_result_summary.workflow_metadata.is_report_only=false`
- result-summary workflow metadata is display/interpretation evidence only and does not replace stable `workflow_type` for task creation, confirmation fingerprints, database records, or artifact routes
- `task_result_summary.contract_version`, `modality`, and `feature_groups` are present
- `task_result_summary.output_group_count` and `task_result_summary.output_item_count` are greater than zero
- `task_result_summary.downloadable_output_count` is greater than zero
- every `task_result_summary.downloadable_output_paths` entry is a safe slash-relative path
- every `task_result_summary.downloadable_output_urls` entry is recomputed from the same `task_id` and relative path
- every downloadable result-summary output is also present in the same task artifact manifest
- `task_result_summary.provenance_keys` is non-empty
- `artifact_manifest_artifact_count` greater than zero
- `artifact_manifest_preview_kinds` includes at least one preview/download class
- `artifact_manifest_relative_paths` and `artifact_manifest_download_urls` are non-empty privacy-safe artifact-route summaries used to cross-check result-summary downloadable outputs
- `container_native_qc_status=passed`
- `container_native_qc_artifact_count` greater than zero
- `container_native_qc_image_count` at or above `--min-native-qc-images`
- `container_native_qc_relative_paths` lists served container-native HTML/image QC artifacts
- `container_native_qc_served_urls` lists the manifest `download_url` routes that returned non-empty bytes
- `container_native_qc_artifacts` lists each served native QC artifact with `relative_path`, `download_url`, `content_type`, `preview_kind`, and accepted `official_source_ids`
- each container-native QC artifact `relative_path` is slash-relative and safe
- each container-native QC artifact `relative_path` must not start with `reports/`; `reports/*` artifacts must remain `scientific_report_artifacts`
- each container-native QC artifact `download_url` is recomputed from `task_id` and `relative_path`
- each container-native QC artifact `content_type` matches `preview_kind`
- `container_native_qc_official_source_ids` cites accepted container-QC curated vendor docs rather than raw sources or arbitrary `docs/rag/vendor/*.md` strings
- each accepted native QC artifact keeps identical `official_source_ids` in top-level artifact metadata and `provenance`
- `scientific_report_artifacts_status=passed`
- `scientific_report_artifact_count` greater than zero
- `scientific_report_image_count` at or above `--min-scientific-report-images`
- `scientific_report_relative_paths` includes `reports/index.html`, `reports/report_manifest.json`, and generated PNG report assets
- `scientific_report_served_urls` lists the derived report artifact `download_url` routes that returned non-empty bytes
- `scientific_report_artifacts` lists each derived report artifact with `relative_path`, `download_url`, `content_type`, `preview_kind`, `source_stage=scientific_report`, `artifact_role=derived_presentation_asset`, `artifact_origin=generated_from_result_summary`, `native_artifact=false`, and `provenance.replaces_native_qc=false`
- each scientific report artifact `download_url` is served with non-empty bytes
- each scientific report artifact `content_type` matches `preview_kind`
- derived scientific report artifacts are report-layer evidence and do not replace `container_native_qc_status=passed`
- artifact manifest items have safe slash-relative `relative_path`, recomputed URL-quoted `download_url`, `exists=true`, positive `size_bytes`, valid `preview_kind`, and no backend `path`, absolute path, Windows path, backslash, or `..` leakage in artifacts, nested provenance, or `omitted_artifacts`

Run the offline strict smoke acceptance JSON verifier `apps/api/scripts/verify_remote_smoke_acceptance.py` on the saved JSON:

```bash
python scripts/verify_remote_smoke_acceptance.py "../../docs/deployment/remote-smoke-acceptance-<timestamp>.json" --max-age-hours 24
```

Attach the verifier report only when `python scripts/verify_remote_smoke_acceptance.py` prints `status=passed` with `--max-age-hours 24`. This offline strict smoke acceptance JSON verifier does not replace running `smoke_remote_agent.py` on the deployed server; it re-checks the saved evidence freshness and the same strict fields, including `deployment_identity_status=passed`, `production_readiness_status=passed`, `production_readiness.ready=true`, empty `production_readiness.blocking_reasons`, `fast_launch_readiness_status=pre_acceptance`, the sole missing strict-acceptance blocker, `fast_launch_readiness.checks.rag_elasticsearch_hybrid.status=passed`, a privacy-safe `deployment_identity.deployment_id` matching `smoke_gate.deployment_id`, a privacy-safe `deployment_identity.health_version` matching `smoke_gate.expected_health_version` when supplied, `model_smoke_status=passed`, `smoke_gate.expected_model_wire_api`, `model_status.wire_api` matching that expected wire API, `smoke_gate.expected_model_provider_profile`, `model_status.provider_profile` matching that expected provider profile, `smoke_gate.require_model_tool_loop=true`, `model_status.capabilities.model_tool_loop=true`, `agent_project_context_status=passed`, `agent_run_project_id` matching `smoke_gate.project_id`, `agent_workflow_confirmation_status=passed`, `agent_workflow_confirmation.status=confirmation_required`, `agent_workflow_confirmation.intent=run_workflow`, `agent_workflow_confirmation.selected_skill=image-agent-workflow-runner`, `agent_workflow_confirmation.production_task_created=false`, matching Agent confirmation project/series/workflow fields, `agent_workflow_confirmation.workflow_metadata.workflow_type` matching the stable confirmation `workflow_type`, a descriptive `agent_workflow_confirmation.workflow_metadata.display_name` that does not equal the machine id, `agent_workflow_confirmation.workflow_metadata.is_report_only=false`, `smoke_gate.require_agent_workflow_resume=true`, `smoke_gate.require_agent_workflow_fingerprint_negative=true`, `agent_workflow_fingerprint_negative_status=passed`, `agent_workflow_fingerprint_negative.confirmation_gate=fingerprint_mismatch`, `agent_workflow_fingerprint_negative.production_task_created=false`, `agent_workflow_fingerprint_negative.task_created=false`, `checked.agent_workflow_fingerprint_negative_status=passed`, `checked.agent_workflow_fingerprint_negative_confirmation_gate=fingerprint_mismatch`, `checked.agent_workflow_fingerprint_negative_production_task_created=false`, `checked.agent_workflow_fingerprint_negative_task_created=false`, `agent_workflow_resume_status=passed`, `agent_workflow_resume.status=task_created`, `agent_workflow_resume.production_task_created=true`, `agent_workflow_resume.confirmation_gate=fingerprint_verified`, matching Agent resume task/project/series/workflow fields, `remote_evidence_ids_status=passed`, `upload_inventory_completion_status=passed`, `upload_inventory_status=completed`, `launched_task_status=passed`, `launched_task.task_id` matching `smoke_gate.task_id`, `launched_task.project_id` matching `smoke_gate.project_id`, `launched_task.series_id` matching `task_status.series_id`, `launched_task.workflow_type` matching `task_status.workflow_type`, `task_status_status=passed`, `task_status.status=completed`, `task_status.task_id` matching `smoke_gate.task_id`, `task_workflow_selection_status=passed`, `task_workflow_selection.matched_runnable_workflow=true`, `task_workflow_selection.series_id` matching `task_status.series_id`, `task_workflow_selection.workflow_type` matching `task_status.workflow_type`, `task_result_summary_status=passed`, `task_result_summary.task_id` matching `smoke_gate.task_id`, `task_result_summary.workflow_type` matching `task_status.workflow_type`, non-empty `task_result_summary.feature_groups`, positive result-summary output counts, positive result-summary downloadable-output counts, safe downloadable-output paths, recomputed downloadable-output URLs, matching `artifact_manifest_relative_paths`/`artifact_manifest_download_urls`, non-empty `task_result_summary.provenance_keys`, `rag_raw_sources.manifest_schema_version`, `rag_raw_sources.source_count`, `rag_raw_sources.vendor_doc_count`, `smoke_gate.require_elasticsearch_hybrid_rag=true`, `rag_elasticsearch_hybrid_status=passed`, `rag_rebuild_elasticsearch_hybrid` present with matching indexed chunk count, dense vector dimensions, embedding provider, and embedding model, `rag_elasticsearch_hybrid.persisted=true`, `rag_elasticsearch_hybrid.mode=connected`, positive `rag_elasticsearch_hybrid.indexed_chunk_count`, positive `rag_elasticsearch_hybrid.dense_vector_dims`, absent `rag_elasticsearch_hybrid.error`, absent `rag_elasticsearch_hybrid.embedding_error`, `rag_elasticsearch_hybrid.embedding_provider`, `rag_elasticsearch_hybrid.embedding_model`, `rag_elasticsearch_hybrid.embedding_production_ready=true`, `rag_elasticsearch_hybrid.fusion=rrf`, `rag_elasticsearch_hybrid.official_rrf_source_present=true`, no saved raw `rag_elasticsearch_hybrid.official_sources`, `rag_vendor_pointer_integrity_status=passed`, `require_vendor_pointer_integrity`, `rag_vendor_pointer_integrity_referenced_vendor_docs`, `rag_vendor_coverage_catalog_status=complete`, `vendor_coverage_catalog`, `vendor_coverage_catalog.vendors`, `rag_raw_sources.curated_sources`, `rag_launchability_query_status=passed`, `container_native_qc_status=passed`, `container_native_qc_served_urls`, `container_native_qc_artifacts`, `container_native_qc_official_source_ids`, each container-native QC artifact `relative_path` is slash-relative and safe, each container-native QC artifact `download_url` is recomputed from `task_id` and `relative_path`, each container-native QC artifact `content_type` matches `preview_kind`, `scientific_report_artifacts_status=passed`, `scientific_report_served_urls`, and `scientific_report_artifacts`; `vendor_coverage_catalog.vendors` and `rag_raw_sources.curated_sources` must exactly match with no missing or extra vendor docs, each scientific report artifact `download_url` is served with non-empty bytes, and each scientific report artifact `content_type` matches `preview_kind`. The verifier also checks that `vendor_coverage_catalog` must not expose `manifest_path`, `persist_dir`, `raw_snapshots`, `raw_files`, or `sha256`. For Elasticsearch hybrid RAG, it also requires `rag_elasticsearch_hybrid_query_status=passed`, `rag_elasticsearch_hybrid_query_mode=elasticsearch_hybrid`, `rag_elasticsearch_hybrid_query_retrieval_source=elasticsearch_hybrid`, `rag_elasticsearch_hybrid_query_source` pointing at `docs/rag/contracts/elasticsearch-hybrid-search.md`, and `rag_elasticsearch_hybrid_query_dense_vector_field=embedding` with the query-time dense-vector field matching `rag_elasticsearch_hybrid.dense_vector_field`.

For unknown workflow safety, the verifier must also report `checked.unknown_workflow_incubation_status=passed`, `checked.unknown_workflow_incubation_action_lane=toolchain_incubation`, `checked.unknown_workflow_incubation_task_created=false`, `checked.unknown_workflow_incubation_confirmation_created=false`, `checked.unknown_workflow_incubation_task_creation_allowed=false`, `checked.unknown_workflow_incubation_forbidden_actions`, and `checked.unknown_workflow_incubation_production_task_created=false`.

For Elasticsearch hybrid RAG, rebuild evidence must also have absent `rag_rebuild_elasticsearch_hybrid.error` and absent `rag_rebuild_elasticsearch_hybrid.embedding_error`; `rag_rebuild_elasticsearch_hybrid.lexical_retriever`, `rag_rebuild_elasticsearch_hybrid.vector_retriever`, `rag_rebuild_elasticsearch_hybrid.dense_vector_field`, and `rag_rebuild_elasticsearch_hybrid.fusion` must match `rag_elasticsearch_hybrid`. A status-only or query-only clean result is not sufficient production evidence.

Workflow metadata selection evidence must be present in both live smoke JSON and verifier checked output: `agent_workflow_confirmation.workflow_metadata.agent_selectable=true`, `task_result_summary.workflow_metadata.agent_selectable=true`, `checked.agent_workflow_confirmation_metadata_agent_selectable=true`, and `checked.task_result_summary_metadata_agent_selectable=true`. These values are display/selection evidence only and do not replace stable `workflow_type` task identity or launch gates.

## Production Acceptance Decision

Accepted only if all of the following are true:

- current package is deployed remotely;
- `/agent/model/status` reports `configured=true`;
- restart drain evidence includes `active_task_drain:ok`, `port_owner:image_agent`, and `health:ok app=image_agent`;
- strict smoke acceptance JSON reports `deployment_identity_status=passed` for the accepted release id or commit;
- strict smoke acceptance JSON reports a privacy-safe `deployment_identity.health_version` matching the supplied `--expected-health-version`;
- strict smoke acceptance JSON reports `production_readiness_status=passed`, `production_readiness.ready=true`, and no readiness blocking reasons;
- strict smoke acceptance JSON reports `model_smoke_status=passed`;
- strict smoke acceptance JSON reports `smoke_gate.expected_model_wire_api=responses`, `model_status.wire_api=responses`, `smoke_gate.expected_model_provider_profile=rawchat`, `model_status.provider_profile=rawchat`, `smoke_gate.require_model_tool_loop=true`, and `model_status.capabilities.model_tool_loop=true`;
- strict smoke acceptance JSON reports `model_status.configured=true` without secret-bearing keys, credentialed URLs, or nested deployment command details;
- strict smoke acceptance JSON includes `agent_run_id`, `intent`, and `selected_skill`;
- strict smoke acceptance JSON reports `agent_project_context_status=passed` and `agent_run_project_id` matching `smoke_gate.project_id`;
- strict smoke acceptance JSON reports `agent_workflow_confirmation_status=passed`, `status=confirmation_required`, `intent=run_workflow`, `selected_skill=image-agent-workflow-runner`, and `production_task_created=false` for the same project, series, and workflow;
- strict smoke acceptance JSON reports confirmation `workflow_metadata.workflow_type` matching the stable workflow id, a descriptive display name that does not replace the id, and `workflow_metadata.is_report_only=false`;
- strict smoke acceptance JSON reports `agent_workflow_resume_status=passed`, `status=task_created`, `production_task_created=true`, `confirmation_gate=fingerprint_verified`, and task/project/series/workflow fields matching the completed task;
- strict smoke acceptance JSON reports `agent_workflow_fingerprint_negative_status=passed`, `confirmation_gate=fingerprint_mismatch`, `production_task_created=false`, and `task_created=false` for the tampered Agent workflow confirmation before the valid resume creates the task;
- strict smoke acceptance JSON reports `remote_evidence_ids_status=passed` with real `project_id`, `upload_session_id`, and `task_id`;
- strict smoke acceptance JSON reports `upload_inventory_completion_status=passed` and `upload_inventory_status=completed`;
- strict smoke acceptance JSON reports `launched_task_status=passed` and proves the backend task-creation response came from server-side Agent resume with `--require-agent-workflow-resume`; `launched_task.launch_source` must be `agent_workflow_resume` and the task id, project id, series id, and workflow type must match the completed task;
- strict smoke acceptance JSON reports `task_status_status=passed` and `task_status.status=completed` for the same real `task_id`;
- strict smoke acceptance JSON reports `task_workflow_selection_status=passed` and proves the completed task workflow was listed in the same series `workflow_eligibility.runnable_workflows`;
- strict smoke acceptance JSON reports `rag_vendor_pointer_integrity_status=passed`, `rag_vendor_pointer_integrity_pointer_count` greater than zero, `rag_vendor_pointer_integrity_issue_count=0`, and non-empty `rag_vendor_pointer_integrity_referenced_vendor_docs`;
- strict smoke acceptance JSON reports `rag_elasticsearch_hybrid_status=passed`, `rag_elasticsearch_hybrid.configured=true`, privacy-safe `rag_elasticsearch_hybrid.index`, matching `rag_rebuild_elasticsearch_hybrid.index`, `rag_elasticsearch_hybrid.persisted=true`, `rag_elasticsearch_hybrid.mode=connected`, positive `rag_elasticsearch_hybrid.indexed_chunk_count`, positive `rag_elasticsearch_hybrid.dense_vector_dims`, checked `rag_elasticsearch_hybrid_error_absent=true`, checked `rag_elasticsearch_hybrid_embedding_error_absent=true`, checked `rag_rebuild_elasticsearch_hybrid_error_absent=true`, checked `rag_rebuild_elasticsearch_hybrid_embedding_error_absent=true`, `rag_elasticsearch_hybrid.embedding_provider`, `rag_elasticsearch_hybrid.embedding_model`, matching `rag_rebuild_elasticsearch_hybrid.embedding_model`, `rag_elasticsearch_hybrid.embedding_production_ready=true`, `rag_rebuild_elasticsearch_hybrid.embedding_production_ready=true`, `rag_elasticsearch_hybrid.fusion=rrf`, `rag_elasticsearch_hybrid_query_status=passed`, `rag_elasticsearch_hybrid_query_mode=elasticsearch_hybrid`, `rag_elasticsearch_hybrid_query_retrieval_source=elasticsearch_hybrid`, `rag_elasticsearch_hybrid_query_dense_vector_field=embedding`, and `smoke_gate.require_elasticsearch_hybrid_rag=true`;
- strict smoke acceptance JSON reports `rag_vendor_coverage_catalog_status=complete`, positive `rag_vendor_coverage_catalog_vendor_doc_count`, and a safe `vendor_coverage_catalog` summary;
- strict smoke acceptance JSON reports `rag_launchability_matrix_status=passed`, `rag_launchability_matrix_source`, and `rag_launchability_query_status=passed` from `/agent/rag/query` citation/source fields rather than answer text alone;
- strict smoke acceptance JSON satisfies RAG document/chunk thresholds, raw-source policy, curated provenance policy, and the provenance pointer integrity gate.
- strict smoke acceptance JSON reports `project_contract_status=passed`, `upload_inventory_contract_status=passed`, `task_artifact_manifest_status=passed`, and `task_result_summary_status=passed` when `--project-id`, `--upload-session-id`, and the resolved task id are supplied; downloadable result-summary outputs must be safe task artifact routes and must be present in the same artifact manifest.
- strict smoke acceptance JSON reports `container_native_qc_status=passed`, enough `container_native_qc_image_count`, non-empty `container_native_qc_served_urls`, per-artifact `container_native_qc_artifacts`, and accepted curated `container_native_qc_official_source_ids`.
- strict smoke acceptance JSON reports `scientific_report_artifacts_status=passed`, enough `scientific_report_image_count`, `scientific_report_relative_paths` for `reports/index.html`, `reports/report_manifest.json`, and PNG assets, non-empty `scientific_report_served_urls`, plus per-artifact `scientific_report_artifacts` derived provenance and matching served content types.
- offline verifier report from `python scripts/verify_remote_smoke_acceptance.py ... --max-age-hours 24` reports `status=passed` for the same saved JSON.

Do not accept a run whose strict smoke result says `skipped_missing_model_config`, even if health and RAG checks pass. Do not accept a run whose Agent smoke is unscoped to the real project; project-scoped Agent chat remains read/query/explain only, and workflow launch still goes through deterministic backend task APIs.
