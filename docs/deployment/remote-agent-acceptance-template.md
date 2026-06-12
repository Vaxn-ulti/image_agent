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
PYTHONPATH=. /home/yyf/project/image_agent/apps/api/.venv/bin/python scripts/verify_stale_task_approval.py /tmp/image_agent_stale_tasks_<ids>_dry_run.json --task-id <id> --task-id <id>
PYTHONPATH=. /home/yyf/project/image_agent/apps/api/.venv/bin/python scripts/verify_stale_task_resolution.py --apply-json /tmp/image_agent_stale_tasks_<ids>_apply.json --resolution-json /tmp/image_agent_stale_tasks_<ids>_resolved_dry_run.json --task-id <id> --task-id <id> --require-empty-active
```

Required evidence before normal restart:

- approval verifier prints `status=passed`;
- resolution verifier prints `status=passed`;
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
  --require-deployment-identity \
  --deployment-id <accepted-release-or-commit> \
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

Attach the strict smoke acceptance JSON and verify it contains:

- `model_smoke_status=passed`
- `deployment_identity_status=passed`
- `deployment_identity.deployment_id` matches `smoke_gate.deployment_id` and is a short release id or commit, not a full remote path
- `deployment_identity.health_version` is present and is a short privacy-safe version string, not a full remote path
- `agent_run_id`
- `intent`
- `selected_skill`
- `remote_evidence_ids_status=passed`
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
- `artifact_manifest_artifact_count` greater than zero
- `artifact_manifest_preview_kinds` includes at least one preview/download class
- `container_native_qc_status=passed`
- `container_native_qc_artifact_count` greater than zero
- `container_native_qc_image_count` at or above `--min-native-qc-images`
- `container_native_qc_relative_paths` lists served container-native HTML/image QC artifacts
- `container_native_qc_served_urls` lists the manifest `download_url` routes that returned non-empty bytes
- `container_native_qc_artifacts` lists each served native QC artifact with `relative_path`, `download_url`, `content_type`, `preview_kind`, and accepted `official_source_ids`
- each container-native QC artifact `relative_path` is slash-relative and safe
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
python scripts/verify_remote_smoke_acceptance.py "../../docs/deployment/remote-smoke-acceptance-<timestamp>.json"
```

Attach the verifier report only when it prints `status=passed`. This offline strict smoke acceptance JSON verifier does not replace running `smoke_remote_agent.py` on the remote server; it re-checks the saved evidence for the same strict fields, including `deployment_identity_status=passed`, a privacy-safe `deployment_identity.deployment_id` matching `smoke_gate.deployment_id`, a privacy-safe `deployment_identity.health_version`, `model_smoke_status=passed`, `remote_evidence_ids_status=passed`, `rag_raw_sources.manifest_schema_version`, `rag_raw_sources.source_count`, `rag_raw_sources.vendor_doc_count`, `rag_vendor_pointer_integrity_status=passed`, `require_vendor_pointer_integrity`, `rag_vendor_pointer_integrity_referenced_vendor_docs`, `rag_vendor_coverage_catalog_status=complete`, `vendor_coverage_catalog`, `vendor_coverage_catalog.vendors`, `rag_raw_sources.curated_sources`, `rag_launchability_query_status=passed`, `container_native_qc_status=passed`, `container_native_qc_served_urls`, `container_native_qc_artifacts`, `container_native_qc_official_source_ids`, each container-native QC artifact `relative_path` is slash-relative and safe, each container-native QC artifact `download_url` is recomputed from `task_id` and `relative_path`, each container-native QC artifact `content_type` matches `preview_kind`, `scientific_report_artifacts_status=passed`, `scientific_report_served_urls`, and `scientific_report_artifacts`; `vendor_coverage_catalog.vendors` and `rag_raw_sources.curated_sources` must exactly match with no missing or extra vendor docs, each scientific report artifact `download_url` is served with non-empty bytes, and each scientific report artifact `content_type` matches `preview_kind`. The verifier also checks that `vendor_coverage_catalog` must not expose `manifest_path`, `persist_dir`, `raw_snapshots`, `raw_files`, or `sha256`.

## Production Acceptance Decision

Accepted only if all of the following are true:

- current package is deployed remotely;
- `/agent/model/status` reports `configured=true`;
- restart drain evidence includes `active_task_drain:ok`, `port_owner:image_agent`, and `health:ok app=image_agent`;
- strict smoke acceptance JSON reports `deployment_identity_status=passed` for the accepted release id or commit;
- strict smoke acceptance JSON reports a privacy-safe `deployment_identity.health_version`;
- strict smoke acceptance JSON reports `model_smoke_status=passed`;
- strict smoke acceptance JSON includes `agent_run_id`, `intent`, and `selected_skill`;
- strict smoke acceptance JSON reports `remote_evidence_ids_status=passed` with real `project_id`, `upload_session_id`, and `task_id`;
- strict smoke acceptance JSON reports `rag_vendor_pointer_integrity_status=passed`, `rag_vendor_pointer_integrity_pointer_count` greater than zero, `rag_vendor_pointer_integrity_issue_count=0`, and non-empty `rag_vendor_pointer_integrity_referenced_vendor_docs`;
- strict smoke acceptance JSON reports `rag_vendor_coverage_catalog_status=complete`, positive `rag_vendor_coverage_catalog_vendor_doc_count`, and a safe `vendor_coverage_catalog` summary;
- strict smoke acceptance JSON reports `rag_launchability_matrix_status=passed`, `rag_launchability_matrix_source`, and `rag_launchability_query_status=passed` from `/agent/rag/query` citation/source fields rather than answer text alone;
- strict smoke acceptance JSON satisfies RAG document/chunk thresholds, raw-source policy, curated provenance policy, and the provenance pointer integrity gate.
- strict smoke acceptance JSON reports `project_contract_status=passed`, `upload_inventory_contract_status=passed`, and `task_artifact_manifest_status=passed` when `--project-id`, `--upload-session-id`, and `--task-id` are supplied.
- strict smoke acceptance JSON reports `container_native_qc_status=passed`, enough `container_native_qc_image_count`, non-empty `container_native_qc_served_urls`, per-artifact `container_native_qc_artifacts`, and accepted curated `container_native_qc_official_source_ids`.
- strict smoke acceptance JSON reports `scientific_report_artifacts_status=passed`, enough `scientific_report_image_count`, `scientific_report_relative_paths` for `reports/index.html`, `reports/report_manifest.json`, and PNG assets, non-empty `scientific_report_served_urls`, plus per-artifact `scientific_report_artifacts` derived provenance and matching served content types.
- offline verifier report from `python scripts/verify_remote_smoke_acceptance.py` reports `status=passed` for the same saved JSON.

Do not accept a run whose strict smoke result says `skipped_missing_model_config`, even if health and RAG checks pass.
