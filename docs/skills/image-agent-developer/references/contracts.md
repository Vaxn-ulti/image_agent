# Contracts

## Contents

- API
- Task States
- Workflow Types
- Shared Result Contract
- Agent Orchestration Contract
- BIDS-like Rules
- Workflow Dependencies
- Result Summary Semantics
- BOLD Descriptive Review Boundary

## API

Baseline endpoints:

- `POST /auth/login`
- `GET /projects`
- `POST /projects`
- `POST /projects/{project_id}/upload`
- `GET /projects/{project_id}/series`
- `GET /series/{series_id}`
- `POST /series/{series_id}/run`
- `GET /tasks/{task_id}`
- `GET /tasks/{task_id}/logs`
- `GET /tasks/{task_id}/outputs`
- `GET /tasks/{task_id}/result-summary`
- `GET /tasks/{task_id}/artifacts/{relative_path}`
- `GET /result-contract`
- `GET /agent/rag/status`
- `POST /agent/rag/query`
- `POST /agent/tools/verify-scientific-reports`
- `POST /agent/runs`
- `GET /agent/runs/{agent_run_id}`
- `POST /agent/runs/{thread_id}/resume`
- `GET /projects/{project_id}/agent-runs`
- `POST /chat` compatibility only; new product surfaces should use the `/agent/runs` contract family.

Phase 4 ingest endpoints include upload-session ingest and inventory status endpoints. Keep synchronous tiny-upload fast paths consistent with the persisted status endpoint output.

## Task States

Use only:

- `queued`
- `running`
- `completed`
- `completed_with_partial_failures` for ingest inventory lifecycle where supported.
- `failed`
- `cancelled`

If task and ingest lifecycle vocabularies diverge, document that distinction.

## Workflow Types

Fixed production workflows:

- `t1_deepprep`
- `bold_deepprep`
- `bold_second_level`
- `dwi_fast_gpu_dti`

Legacy or experimental workflows:

- `dwi_qsiprep`
- `dwi_qsirecon`
- `dwi_qsi_full`
- `dicom_convert`
- `bold_alff`
- `bold_falff`

Validation variants may use a suffix such as `_validate` if consistent with existing code.

## Shared Result Contract

Workflow handlers should return the shared result shape used by the backend task runner: state, message or error detail, output records, and task metadata sufficient for DB/task/output registration. Keep new workflow implementations compatible with that contract instead of returning ad hoc payloads.

Frontend consumers should use:

- `GET /result-contract` to discover the current machine-readable contract.
- `GET /tasks/{task_id}/result-summary` for structured T1/BOLD/DWI result views.
- `GET /tasks/{task_id}/artifact-manifest` for a stable preview/download list with `preview_kind`, sanitized `relative_path`, recomputed `download_url`, `content_type`, and `size_bytes`.
- `GET /tasks/{task_id}/artifacts/{relative_path}` for safe artifact download/preview from inside that task output directory.
- `GET /tasks/{task_id}/outputs` only as the legacy artifact listing.

Scientific report display layer:

- Real T1/BOLD/DWI result summaries should include `outputs.reports` with `reports/index.html`, `reports/report_manifest.json`, and modality-specific PNG report-builder assets.
- A companion `summary/<modality>_scientific_report_summary.json` may also be registered as an output with metadata `kind=scientific_report_summary`.
- The report layer is presentation over the result-summary source of truth; do not replace raw tables/maps or invent measurements only for a chart.
- The frontend should surface reports as a readable `Scientific report` panel and keep machine outputs in the generic artifact table. Image report artifacts (`image/*`, `.svg`, `.png`, `.jpg`, `.jpeg`, `.webp`) should render as embedded figure previews; `reports/index.html` should remain the full report entry point.
- Generated scientific report assets must be labeled with `source_stage: scientific_report`, `artifact_role: derived_presentation_asset`, `artifact_origin: generated_from_result_summary`, `native_artifact: false`, and `provenance.replaces_native_qc: false` so agents and UI can distinguish them from container-native QC artifacts.

Every result-summary output item should include:

- `name`
- `path`
- `relative_path`
- `exists`
- `download_url`
- `content_type`
- `size_bytes`

Common optional output-item fields include `space`, `atlas`, `feature_group`, `description`, `unit`, `table_schema`, `source_stage`, `artifact_role`, `artifact_origin`, `native_artifact`, and `provenance`.

Artifact serving rules:

- `/tasks/{task_id}/artifacts/{relative_path}` must resolve only inside `data/projects/{project_id}/derivatives/{task_id}/output`.
- `.nii.gz` artifacts should be served with `content-type: application/gzip`, matching result-summary `content_type`.
- Browser-preview report artifacts should be served with useful media types, including `image/png` for current report-builder figures, `image/svg+xml` for legacy SVG figures, and `text/html` for report indexes.
- `/tasks/{task_id}/artifact-manifest` should be the frontend's stable preview/download list and should not expose backend absolute paths. The result-summary remains authoritative for scientific/result interpretation.
- Do not expose backend absolute paths to frontend users. Keep any host-path debugging evidence server-side, redacted, and out of frontend/API artifact contracts.

Workflow eligibility contract:

- Upload, series, and ingest-inventory responses should expose derived `workflow_eligibility` without creating production tasks.
- Covered surfaces include `POST /projects/{project_id}/upload`, DWI/DICOM upload variants, `GET /projects/{project_id}/series`, `GET /series/{series_id}`, and `GET /projects/{project_id}/datasets/{upload_session_id}/inventory` (`/projects/{project_id}/datasets/{upload_session_id}/inventory`).
- Every `workflow_eligibility` envelope should include `policy_version=workflow_eligibility_v1`, `production_task_created=false`, `primary_recommendation`, `runnable_workflows`, and `blocked_workflows`.
- `runnable_workflows` names workflows that satisfy current backend launch requirements from persisted files and metadata. `blocked_workflows` must carry concrete missing requirements instead of vague not-ready text.
- Eligibility is advisory launchability, not a successful run claim. Real acceptance still requires a completed task, registered outputs, result-summary evidence, and remote strict smoke evidence.
- Ingest inventory must remain side-effect-free: do not create production task rows while deriving eligibility for uploaded files.

## Agent Orchestration Contract

- `POST /agent/runs` is the primary product agent entrypoint. `POST /agent/rag/query` and compatibility `POST /chat` should expose `intent`, `recommended_next_step`, `tool_chain_hint`, `tool_invocations`, and `rag_mode` where applicable.
- `/agent/runs` and `/agent/runs/{thread_id}/resume` request bodies are strict API contracts: unknown request fields return `request_contract_violation` in the `agent_api_error.v1` envelope rather than being ignored.
- For resume calls, nested confirmation fields are also strict: accept only the stable workflow-confirmation fields before calling the runner, ledger, or task-creation path.
- `tool_invocations` is a read-only trace of internal agent tools, such as `inspect_task_status`, `inspect_registered_outputs`, `inspect_scientific_reports`, and `recommend_next_action`.
- The built-in agent may inspect state and suggest next actions from backend records, but it must not launch long-running workflows directly from chat.
- `POST /agent/tools/verify-scientific-reports` is a read-only Agent tool endpoint for report-layer acceptance. It accepts `task_ids`, optional `projects_root`, optional explicit `output_dirs`, and `require_modalities`, then returns `ok`, `read_only`, resolution errors, missing modalities, and per-output checks.
- Backend records and registered outputs remain authoritative over local RAG documents.
- The OpenAI Responses gateway should use the official OpenAI SDK transport: construct `OpenAI(api_key=..., base_url=..., timeout=...)` and call `responses.create(...)` with Responses-native payloads.
- The OpenAI Responses gateway should expose backend tools as Responses-native function specs: `{"type":"function","name":...,"parameters":...}`. Do not reintroduce hand-rolled `/responses` HTTP transport or the nested Chat-Completions-style `{"type":"function","function":{...}}` wrapper for Responses payloads.
- OpenAI function tool specs are strict at the model boundary: set `strict=true`, ensure every object schema in `parameters` has `additionalProperties=false`, and still validate/dispatch only allowlisted tools on the backend.
- The backend dispatcher rejects unknown tool arguments before execution; do not silently ignore ad hoc model, frontend, or compatibility-layer parameters.
- The backend dispatcher rejects missing required tool arguments before execution; missing required inputs should produce a stable blocked tool result rather than a handler-level exception.
- Model-requested function calls must be answered with typed `function_call_output` input items keyed by the original `call_id`. Plain text `Tool results JSON` messages are only a compatibility fallback when a malformed tool call has no call id.
- Structured planner decisions should use Responses `text.format` with `json_schema` and `strict: true` when the backend has a schema; prefer `json_schema` whenever a schema is available. `json_object` is only a compatibility fallback.
- The gateway must reject malformed `structured_schema` before calling `responses.create`: require a non-empty `name`, `strict=true`, and an object `schema` with `type=object` plus `additionalProperties=false`.
- Backend code validates strict structured outputs before treating them as `intent`, `recommended_next_step`, `tool_chain_hint`, or tool-planning decisions.
- Do not use Chat-Completions-style `response_format`, nested tool wrappers, or fake function calls for normal structured decisions.
- OpenAI Code Interpreter container terminology is not Image Agent workflow container terminology. Code Interpreter containers are model/tool execution sandboxes, not Image Agent production workflow containers; do not expose Image Agent workflow containers, shell, Docker, or production task launch privileges directly to the model. Image Agent workflow containers remain backend-orchestrated and server-side gated.
- Production task creation remains gated outside the planner loop: function tools may prepare/read/preflight, but `create_workflow_task` can execute only through the server-side resume confirmation path.

Agent-run ledger:

- The backend should maintain an `agent-run ledger` as a durable agent-run trace for `/agent/runs` and resume calls.
- Use `agent_run_id` as the durable run identity and emit lifecycle events named `agent_run_created`, `agent_run_started`, `agent_run_completed`, `agent_run_failed`, `agent_run_cancelled`, and `agent_run_skipped`.
- Ledger rows may include `model_gateway_access`, `tool_invocations`, `intent`, `action_lane`, `selected_skill`, safe retrieved document source ids, confirmation fingerprint, `project_id`, `series_id`, `workflow_type`, and `task_id` when known.
- Use privacy-safe lifecycle traceability only: store `message_sha256` or another redacted user message summary, not raw prompt text or retrieved snippets.
- Do not store raw image contents, do not expose patient identifiers, do not expose full sensitive host paths, and do not expose API keys, bearer tokens, FreeSurfer license text, or raw DICOM contents.
- Backend task rows remain authoritative for task state. Result-summary JSON remains authoritative for completed workflow outputs. The ledger explains agent orchestration, not clinical meaning or workflow output truth.
- `GET /agent/runs/{agent_run_id}` should return a ledger-only envelope with `safe_metadata`, `retrieved_sources`, `tool_invocations`, lifecycle `events`, and safe ids. It is not the original agent result; do not expose raw answer text, raw prompts, raw RAG snippets, full confirmation payloads, or host paths.
- `GET /projects/{project_id}/agent-runs` should return project-scoped agent-run history as a safe project run summary list, sorted newest first, with `event_count` instead of full event payloads.
- safe_metadata excludes free-form model text; do not expose model-generated `recommended_next_step`, `tool_chain_hint`, or similar text through the ledger envelope. Absolute host paths are not valid retrieved_sources. Exposed failure summaries should use `redacted_error_summary`.
- Pending confirmation records should include `expires_at`; pending confirmations are single-use. A successful approved resume must consume the pending thread, and expired confirmations return blocked with `production_task_created=false`.
- Lookup/list responses re-sanitize stored JSON before returning it. safe_metadata uses an allowlist, retrieved_sources expose source ids only, and titles and snippets are not ledger fields.

## BIDS-like Rules

Never overwrite an existing target artifact during ingest. Use `run-*`, `acq-*`, or both.

Suggested targets:

- T1w: `sub-<label>/anat/sub-<label>[_acq-<label>][_run-<n>]_T1w.nii.gz`
- BOLD: `sub-<label>/func/sub-<label>_task-<label>[_acq-<label>][_run-<n>]_bold.nii.gz`
- DWI: `sub-<label>/dwi/sub-<label>[_acq-<label>][_run-<n>]_dwi.nii.gz`

Metadata precedence:

1. Sidecar JSON.
2. DICOM tags.
3. NIfTI header.
4. Filename tokens.

## Workflow Dependencies

- T1w DeepPrep requires T1w input.
- BOLD DeepPrep requires BOLD input and BIDS-like func placement.
- `bold_second_level` is a single-subject downstream metrics package after BOLD DeepPrep, not the group-level analysis endpoint.
- BOLD downstream metrics require completed BOLD DeepPrep outputs for the same series.
- Fast GPU DTI requires DWI NIfTI plus `.bval`, `.bvec`, and a JSON sidecar containing `PhaseEncodingDirection` and `TotalReadoutTime`; it is the production DWI workflow.
- Legacy BIDS-ingested DWI records may lack newer `has_json` / `json_file_id` metadata. They may be accepted only when real `.json`, `.bval`, and `.bvec` sidecars are present in `metadata.sidecars` or BIDS/NIFTI_BIDS placement, and the JSON contains `PhaseEncodingDirection` plus `TotalReadoutTime`. Ordinary `/upload-dwi` records without JSON must still be rejected.
- Production `dwi_fast_gpu_dti` must use host FSL from `/home/yyf/project/MCI_project/tools/fsl` for GPU `eddy_cuda` and FSL registration utilities. It uses `pennlinc/qsiprep:latest` only as an MRtrix toolbox image for commands such as `dwi2mask`, `mrconvert`, `dwi2tensor`, `tensor2metric`, `mrstats`, and `mrcalc`.
- Production `dwi_fast_gpu_dti` must not execute full `qsiprep /data /out participant` or full QSIRecon. The expected max runtime target is `2100` seconds / 35 minutes.
- QSIPrep requires DWI NIfTI plus `.bval` and `.bvec`.
- QSIRecon requires a completed QSIPrep task output and a valid `--recon-spec`.
- Full QSI chain runs QSIPrep before QSIRecon and skips QSIRecon if QSIPrep fails.
- DICOM conversion requires a DICOM archive series and produces NIfTI outputs before downstream modality processing.
- BOLD ALFF/fALFF are legacy split metric tasks; production single-subject downstream BOLD outputs are registered through `bold_second_level`.

## Result Summary Semantics

- Validate-only result summaries may contain placeholder outputs and must set `placeholder_outputs: true` or `validation_only: true` in provenance.
- Real DWI fast GPU DTI summaries must be created from existing FA/MD/AD/RD maps, MNI152 maps, and atlas regional tables; do not reuse validate placeholder summaries after a real run.
- Current real DWI evidence:
  - task `107` on project 22 / series 38 completed in about 19 minutes 52 seconds wall time (`runtime_sec=1156` in QC);
  - task `112` on project 23 / series 39 completed in about 18 minutes 2 seconds wall time (`runtime_sec=1042` in QC);
  - task `114` on mixed project 13 / series 24 completed with `runtime_sec=1021`, accepted legacy BIDS sidecar metadata, and proves T1/BOLD/DWI can coexist in one project;
  - all three used 28-volume DTI subsets from 129-volume sources and produced native FA/MD/AD/RD maps, MNI152 FA/MD/AD/RD maps, HarvardOxford regional TSVs, and `validation_only=false` result summaries.
- DWI metric maps must be finite for frontend delivery. MRtrix `tensor2metric` may emit sparse NaNs; production code sanitizes native and MNI maps by replacing NaN/inf with `0.0` and records replacement counts in provenance. Task `112` records `114` native and `142` MNI replacements per metric after this hardening.
- DWI result summaries must read the prepared atlas metadata from `mni152_resources/dwi_dti_mni_atlas.json`; do not report the default Schaefer atlas when the actual regional TSVs used HarvardOxford or another selected atlas.
- Real BOLD downstream summaries must be created from existing MNI152 maps and connectivity/QC tables, then written to `summary/bold_result_summary.json`.
- Current real BOLD evidence:
  - task `110` on project 14 / series 25 used DeepPrep task `45`;
  - task `111` on project 13 / series 23 used DeepPrep task `64`;
  - both returned `modality=BOLD`, `spaces=["MNI152"]`, feature groups `voxelwise_metrics`, `connectivity`, `qc_timeseries`, and `motion_confounds` from `/tasks/{id}/result-summary`.
- BOLD MNI outputs must include ALFF, fALFF, ReHo, tSNR, RSFA maps, 15-seed seed-to-ROI TSV, DMN summary, and seed time series. Do not pair MNI BOLD with a T1w mask; generate or require a matching MNI/EPI mask.
- `/tasks/{task_id}/result-summary` must prefer `kind=result_summary` over legacy `kind=bold_metrics_summary`; legacy metric summaries are compatibility artifacts, not the frontend contract.
- If only a legacy BOLD metric summary is present, `/tasks/{task_id}/result-summary` must wrap it in a unified shell with `feature_groups=["legacy_bold_metrics"]`, `provenance.legacy_fallback=true`, and the raw payload under `legacy_summary`; do not return the raw old schema directly.
- Command/validate metadata outputs must not register empty DB paths. If a pipeline registers an output with no source path, write `metadata/<output_type>_output.json` under the task output directory and register that file.
- DWI validate summaries should preserve the actual workflow type, e.g. `dwi_fast_gpu_dti_validate`, so task records and summaries agree.
- T1 result summaries parse real DeepPrep/Freesurfer stats when `Recon/sub-*/stats` exists. Real parsed summaries use `extraction_status=real_deepprep_freesurfer_stats` and `placeholder_outputs: false`.
- Real T1 summaries should expose all available FreeSurfer `.stats` files, not just `brainvol` and `aparc`. The current writer adds `t1_freesurfer_stats_inventory.tsv`, copies every `.stats` file under `tables/freesurfer_stats/`, and records per-file counts in provenance.
- Current real T1 evidence: tasks `40` and `41` each expose 16 brain measures, 68 cortical regions, 9 stats files, 5 T1w maps, and 2 transform references.
- T1 summaries fall back to the explicit contract placeholder only when real stats are missing. Treat provenance `extraction_status=placeholder_contract_pending_real_deepprep_parser` as not-yet-real regional feature extraction.
- Final report-layer acceptance should run `python apps/api/scripts/verify_scientific_reports.py` with `--projects-root data/projects --task-ids 41 111 114 --require-modalities T1 BOLD DWI --require-container-native-qc --min-native-qc-images 1` on the remote server against real task outputs, or pass explicit output directories if different task ids are selected. This gate checks derived presentation reports and separately requires container-native QC; generated report PNGs are useful presentation assets but do not replace native QC. Remote strict smoke may also enforce report-layer manifest evidence with `--require-scientific-report-artifacts`, but that gate must stay separate from `--require-container-native-qc`: `scientific_report_artifacts_status=passed` proves `reports/index.html`, `reports/report_manifest.json`, PNG assets, and derived provenance, while `container_native_qc_status=passed` proves served container-native QC.

## BOLD Descriptive Review Boundary

- Historical outputs under `D:\Project\image_agent\bold_descriptive_review_20260521` are useful as descriptive reporting examples, not as second-level statistical inference.
- Preserve the distinction between:
  - `bold_second_level`: single-subject downstream metrics after DeepPrep;
  - `/projects/{project_id}/bold/descriptive-review`: descriptive review/report package;
  - `/projects/{project_id}/bold/group-analysis`: group-level analysis route.
- Do not overwrite remote real BOLD scripts (`bold_descriptive_review.py`, `bold_group_analysis.py`, or remote real `bold_metrics.py`) with local placeholders.
