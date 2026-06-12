# Testing Matrix

Run the smallest matrix that covers the touched surface. Record command output in handoff notes.

## Contents

- Test Command
- Baseline
- BOLD Downstream Validation
- T1 DeepPrep Result Validation
- Production DWI Fast GPU DTI Validation
- Legacy DWI/QSI GPU Validation
- Real Acceptance
- Contract Regression
- Review/Test Acceptance

## Test Command

Always use the venv pytest from the repo root:

```text
apps/api/.venv/bin/pytest -q apps/api/tests
```

Do not run repo-root `pytest` or `cd apps/api && pytest`.

For console work, run from the console app:

```text
cd apps/console && npm test && npm run build
```

## Baseline

- `apps/api/.venv/bin/pytest -q apps/api/tests`
- `cd apps/desktop && npm run build`

Current known baseline:

- Remote `/home/yyf/project/image_agent/apps/api` full API pytest after mixed-project/legacy-sidecar hardening: `113 passed, 2 warnings`.
- `apps/desktop npm run build`: passed.

## BOLD Downstream Validation

- `bold_second_level` must use a completed `bold_deepprep` task from the same project/series.
- Real run acceptance requires MNI152 ALFF, fALFF, ReHo, tSNR, RSFA maps, 15-seed seed-to-ROI TSV, DMN summary, seed time series, and `summary/bold_result_summary.json`.
- Do not accept a BOLD run that pairs MNI BOLD with a T1w mask. If DeepPrep does not provide a matching MNI mask, derive a MNI/EPI mask from the MNI preprocessed BOLD and record it in provenance.
- Reuse a DeepPrep tSNR source only when it matches the MNI BOLD shape; otherwise recompute tSNR and record the mismatch in provenance.
- Current passing real evidence:
  - task `110`, project 14 / series 25, source DeepPrep task `45`, MNI mask fraction about `0.2209`;
  - task `111`, project 13 / series 23, source DeepPrep task `64`, MNI mask fraction about `0.2347`;
  - both produced MNI152 maps with shape `91 x 109 x 91`, 15 seeds, 226-line seed-to-ROI tables, and API result summaries with feature groups.
- Focused BOLD/contract regression after this hardening: `17 passed, 2 warnings`.

## T1 DeepPrep Result Validation

- Real T1 acceptance requires parsed `brainvol.stats`, bilateral cortical region stats, and an inventory of every available FreeSurfer `.stats` file.
- Current passing real evidence:
  - task `40`, project 14 / series 26;
  - task `41`, project 13 / series 22;
  - both expose 16 brain measures, 68 cortical regions, 9 stats files, 5 T1w maps, and 2 transform references.
- MNI152 T1 output should be represented by actual transform/map references unless a real MNI-space regional table exists. Do not invent MNI regional measurements from native FreeSurfer stats.
- Focused T1 regression after all-stats expansion: `3 passed, 2 warnings`.

## Production DWI Fast GPU DTI Validation

- `dwi_fast_gpu_dti_validate` with DWI plus `.bval`/`.bvec` plus JSON sidecar validates required input metadata before launch.
- Explicit uploaded `json_file_id`, `bval_file_id`, and `bvec_file_id` take precedence over same-stem sidecars already present near the NIfTI.
- Legacy BIDS-ingested DWI can be accepted from `metadata.sidecars` or BIDS/NIFTI_BIDS placement when `.json`, `.bval`, and `.bvec` exist and the JSON contains eddy metadata; ordinary `/upload-dwi` records without JSON must still be rejected.
- Runtime probe checks host FSL commands under `/home/yyf/project/MCI_project/tools/fsl`, GPU visibility with `nvidia-smi`, and MRtrix command availability inside `pennlinc/qsiprep:latest`.
- Production command uses the backend lightweight runner and must not include full `qsiprep /data /out participant` or full QSIRecon.
- Real run acceptance requires FA/MD/AD/RD native maps, MNI152 maps, atlas TSVs, QC/provenance, and measured runtime against the `2100` second target.
- Current passing real evidence:
  - task `107` completed on project 22 / series 38 with `runtime_sec=1156`;
  - task `112` completed on project 23 / series 39 with `runtime_sec=1042`;
  - task `114` completed on mixed project 13 / series 24 with `runtime_sec=1021`;
  - all produced native and MNI152 FA/MD/AD/RD maps, HarvardOxford regional TSVs, and `validation_only=false`.
- Registration regression tests must cover invalid FLIRT matrices. Task `106` produced an all-NaN affine; the protected path validates affine matrices and uses conservative `flirt_normmi_dof6` before fallback.
- Finite-map regression must be preserved. Real tasks `107` and `112` exposed sparse NaNs after MRtrix `tensor2metric`; production now sanitizes NaN/inf values in native and MNI metric maps and records counts in provenance. Check that delivered maps have `0` non-finite voxels.

## Legacy DWI/QSI GPU Validation

- `dwi_qsiprep_validate` with DWI plus `.bval`/`.bvec` generates and mounts `eddy_cuda_config.json`.
- Config JSON contains `use_cuda: true`, `num_threads >= 4`, `dont_peas: true`, `cnr_maps: true`, default `niter: 3`, and an `is_shelled` value inferred from b-values.
- QSIPrep command includes `--gpus all` and `--eddy-config /eddy_cuda_config.json`.
- Detection uses `eddy_cuda*` glob (accepts `eddy_cuda11.0`, `eddy_cuda10.2`, etc.); passes when `pennlinc/qsiprep:latest` exposes `eddy_cuda11.0` at `/app/.pixi/envs/qsiprep/bin/`.
- Backend writes a bash wrapper that symlinks `eddy_cuda` → `eddy_cuda11.0` and `eddy_cuda10.2` → `eddy_cuda11.0` before calling qsiprep.
- With an image missing all `eddy_cuda*` executables, validation fails fast with a clear GPU image requirement.
- `dwi_qsirecon_validate` requires completed QSIPrep output and records whether GPU is visible in the container.
- `dwi_qsirecon` command includes `--recon-spec` with a valid spec value; validation fails fast when `--recon-spec` is missing or unsupported.
- `dwi_qsi_full_validate` enforces the same eddy_cuda* GPU safety check as standalone `dwi_qsiprep_validate`.

## Real Acceptance

Validate-only is not sufficient for acceptance. Real acceptance requires:
- Real container processing with actual data packages.
- T1 DeepPrep real processing with registered outputs.
- BOLD DeepPrep real processing with registered outputs.
- Production DWI fast GPU DTI real processing with host FSL GPU `eddy_cuda`, MRtrix toolbox commands from QSIPrep image, MNI152 maps, atlas regional DTI tables, and runtime evidence.
- Legacy QSI acceptance, when explicitly selected, still requires QSIPrep real processing with CUDA eddy and QSIRecon real processing after completed QSIPrep using Docker `--gpus all` with QSIPrep derivatives as input.
- Mixed-sample matrix: upload packages combining T1, BOLD, DWI (with gradients) in a single project.
- Current mixed-project acceptance proof: project `13` has completed T1 task `41`, BOLD task `111`, and production DWI task `114`, each with `/tasks/{id}/result-summary`.
- Scientific report display acceptance for real outputs requires `outputs.reports`, `reports/index.html`, `reports/report_manifest.json`, PNG report assets for T1, BOLD, and DWI, and derived-presentation provenance (`artifact_role=derived_presentation_asset`, `native_artifact=false`, `provenance.replaces_native_qc=false`). It also requires separately registered container-native QC evidence; derived presentation reports do not replace native QC. Run by task id when possible:
  `python apps/api/scripts/verify_scientific_reports.py --projects-root data/projects --task-ids 41 111 114 --require-modalities T1 BOLD DWI --require-container-native-qc --min-native-qc-images 1`
  Required report verifier options include `--require-container-native-qc` and `--min-native-qc-images 1`.
- Operational release acceptance requires approved stale-task reconciliation before strict smoke if active tasks block restart. Dry-run approval evidence must pass `verify_stale_task_approval.py`, apply must use `--approval-json` so `approval_fingerprint` cannot drift, the post-apply dry-run must pass `verify_stale_task_resolution.py` with `--require-empty-active`, and only then may a normal restart without `IMAGE_AGENT_ALLOW_RESTART_WITH_ACTIVE_TASKS=1` count toward release evidence. Required stale-task evidence fields include `out_of_scope_stale_task_ids=[]`, `running_container_task_ids=[]`, and `blocked_task_ids=[]`.
- Unsupported sequence blocking verified with real inputs.
- Multiple sample combinations (different subjects/packages) tested.

## Contract Regression

- Model gateway tests must assert Responses-native function tool specs, preservation of typed `function_call_output` input items, and dispatcher handling for Responses tool-call arguments.
- DWI without `.bval` or `.bvec` is ineligible with a specific reason.
- QSIRecon without a completed QSIPrep task is rejected.
- Failed/cancelled tasks remain visible through task status, logs, and outputs endpoints.
- Chat/operator responses do not recommend running CPU eddy for production DWI.
- `GET /result-contract` documents frontend-required fields and modality-specific expectations.
- `GET /tasks/{task_id}/result-summary` prefers unified `kind=result_summary`, wraps legacy BOLD summaries instead of returning their raw schema, and does not crash on command metadata outputs.
- Result-summary output items include `relative_path`, `download_url`, `content_type`, and `size_bytes`.
- Scientific report summaries backfill the main result summary with `outputs.reports` and provenance `scientific_report_summary_path`.
- `GET /tasks/{task_id}/artifacts/{relative_path}` serves files only from inside the task output directory; `.nii.gz` responses return `content-type: application/gzip`, current PNG report figures return `image/png`, legacy SVG figures return `image/svg+xml`, and report HTML returns `text/html`.
- Console result detail should embed previewable scientific report figures from `outputs.reports` while preserving report-file open/download links.
- DWI validate summaries preserve `workflow_type=dwi_fast_gpu_dti_validate`.
- `workflow_eligibility` contract regressions should assert `policy_version=workflow_eligibility_v1`, `production_task_created=false`, `primary_recommendation`, `runnable_workflows`, and `blocked_workflows` on upload responses, project series listing, series detail, and `GET /projects/{project_id}/datasets/{upload_session_id}/inventory`.
- Ingest inventory eligibility checks must assert that inventory generation does not create production task rows.
- Remote strict smoke should be run on the remote server with real ids when available: `--project-id`, `--upload-session-id`, `--task-id`, `--require-real-evidence-ids`, `--require-vendor-pointer-integrity`, `--require-launchability-matrix`, `--require-container-native-qc`, `--min-native-qc-images`, `--require-scientific-report-artifacts`, `--min-scientific-report-images`, `--require-deployment-identity`, `--deployment-id`, `--output-json`, and the existing model/RAG raw-source gates. The `--deployment-id` value must be a privacy-safe accepted release id or commit symbol, not a remote backend path.
- Remote strict smoke JSON evidence should show `project_contract_status=passed`, `upload_inventory_contract_status=passed`, `task_artifact_manifest_status=passed`, `remote_evidence_ids_status=passed`, `deployment_identity_status=passed`, matching `deployment_identity.deployment_id` and `smoke_gate.deployment_id`, privacy-safe `deployment_identity.health_version`, raw-source `manifest_schema_version`, positive `source_count`, positive `vendor_doc_count`, per-curated-source `manifest_backed=true`, `source_url_backed=true`, and non-empty `source_types`, `rag_vendor_pointer_integrity_status=passed`, positive `rag_vendor_pointer_integrity_pointer_count`, zero `rag_vendor_pointer_integrity_issue_count`, non-empty `rag_vendor_pointer_integrity_referenced_vendor_docs`, `rag_vendor_coverage_catalog_status=complete`, positive `rag_vendor_coverage_catalog_vendor_doc_count`, `vendor_coverage_catalog.vendors`, `rag_raw_sources.curated_sources`, `rag_launchability_matrix_status=passed`, `rag_launchability_query_status=passed`, `rag_launchability_query_source`, `container_native_qc_status=passed`, `container_native_qc_served_urls`, `container_native_qc_artifacts`, accepted `container_native_qc_official_source_ids`, each container-native QC artifact `relative_path` is slash-relative and safe, each container-native QC artifact `download_url` is recomputed from `task_id` and `relative_path`, each container-native QC artifact `content_type` matches `preview_kind`, `scientific_report_artifacts_status=passed`, `scientific_report_relative_paths`, `scientific_report_served_urls`, and per-artifact `scientific_report_artifacts`; `vendor_coverage_catalog.vendors` and `rag_raw_sources.curated_sources` must exactly match with no missing or extra vendor docs, each scientific report artifact `download_url` is served with non-empty bytes, and each scientific report artifact `content_type` matches `preview_kind`. `raw_source_ids` are manifest ids, not `official_source_ids`; curated vendor summaries are answer sources, while raw snapshots are provenance evidence only.
- Saved remote strict smoke JSON should also pass the offline strict smoke acceptance JSON verifier `apps/api/scripts/verify_remote_smoke_acceptance.py`: run `python scripts/verify_remote_smoke_acceptance.py --max-age-hours 24 <remote-smoke-acceptance.json>` and require `status=passed`. This offline strict smoke acceptance JSON verifier does not replace running `smoke_remote_agent.py` on the remote server; it re-checks saved evidence fields such as `model_smoke_status=passed`, `remote_evidence_ids_status=passed`, `deployment_identity_status=passed`, `deployment_identity.deployment_id`, `deployment_identity.health_version`, `smoke_gate.deployment_id`, `rag_raw_sources.manifest_schema_version`, `rag_raw_sources.source_count`, `rag_raw_sources.vendor_doc_count`, `rag_vendor_pointer_integrity_status=passed`, `require_vendor_pointer_integrity`, `rag_vendor_pointer_integrity_referenced_vendor_docs`, `rag_vendor_coverage_catalog_status=complete`, `vendor_coverage_catalog`, `vendor_coverage_catalog.vendors`, `rag_raw_sources.curated_sources`, `rag_launchability_query_status=passed`, `container_native_qc_status=passed`, `container_native_qc_served_urls`, `container_native_qc_artifacts`, `container_native_qc_official_source_ids`, each container-native QC artifact `relative_path` is slash-relative and safe, each container-native QC artifact `download_url` is recomputed from `task_id` and `relative_path`, each container-native QC artifact `content_type` matches `preview_kind`, `scientific_report_artifacts_status=passed`, `scientific_report_served_urls`, and `scientific_report_artifacts`; `vendor_coverage_catalog.vendors` and `rag_raw_sources.curated_sources` must exactly match with no missing or extra vendor docs, each scientific report artifact `download_url` is served with non-empty bytes, and each scientific report artifact `content_type` matches `preview_kind`. The saved `vendor_coverage_catalog` must not expose `manifest_path`, `persist_dir`, `raw_snapshots`, `raw_files`, or `sha256`.
- Remote smoke negative cases should reject malformed `workflow_eligibility` envelopes and unsafe artifact-manifest paths, including absolute paths, `..` traversal, Windows backslashes, backend `path` leakage, missing `exists=true`, leaked paths inside nested provenance, and leaked paths inside `omitted_artifacts`. Remote smoke negative cases should reject missing `/agent/rag/query` launchability matrix citations with `RAG launchability matrix query citation missing`, including answers that mention the matrix path without citation/source metadata.
- Native QC smoke negative cases should reject arbitrary vendor Markdown, raw-source ids, provenance-only ids, top-level-only ids, and mismatched top-level/provenance `official_source_ids`.
- `GET /tasks/{task_id}/artifact-manifest` contract tests should assert `contract_version=artifact_manifest_v1`, matching `task_id`, safe `relative_path`, recomputed `download_url`, valid `preview_kind`, `content_type`, positive `size_bytes`, and no backend `path` leakage.

## Review/Test Acceptance

Accept a change only when:

- Focused tests for changed behavior pass.
- Baseline tests above pass or failures are unrelated and documented.
- Container validation distinguishes code defects from missing CUDA-enabled images.
- Handoff names remaining infrastructure blockers.

Final real acceptance adds:

- Real container processing completed and outputs registered.
- GPU used where supported: host FSL GPU `eddy_cuda` for production fast DTI; Docker `--gpus all` for legacy QSIPrep and QSIRecon.
- Acceptance matrix covers T1, BOLD, production DWI fast DTI, legacy QSI where selected, mixed packages, unsupported sequences, and multiple sample combinations with real data.
- Scientific report display artifacts pass the remote verifier against the real T1/BOLD/DWI output directories.
