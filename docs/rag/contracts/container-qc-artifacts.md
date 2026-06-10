---
source_type: rag_contract
contract: container_qc_artifacts
status: current_contract
retrieved_date: 2026-06-07
---

# Container-Native QC Artifact Contract

## Purpose

Image Agent should prefer container-native QC, report, and visualization outputs when presenting workflow results. These artifacts are produced by the scientific containers or their official reporting stacks, so they carry provenance and diagnostic context that ad hoc screenshots cannot reproduce.

## Required Rule

Use container-native QC artifacts first and do not replace them with model-generated or hand-drawn substitutes.

The agent may create a lightweight index page or thumbnail gallery, but it must point back to the original artifacts in `outputs.reports`, `outputs.figures`, `outputs.tables`, `outputs.maps`, or `outputs.logs`.

Each native QC/report/figure/table/map/log artifact should carry `official_source_ids` in top-level artifact metadata and `provenance`. These ids point to curated RAG vendor documents that explain why the artifact is expected.

`/tasks/{task_id}/artifact-manifest` is the frontend display/download source of truth. It must label each item with `artifact_category`, `container_native_qc`, `derived_scientific_report`, and `frontend_preview_asset` so UI and agents can distinguish native evidence from report-layer presentation assets.

## Expected Native Artifacts

### BOLD fMRIPrep

- fMRIPrep HTML report under the fMRIPrep derivative tree.
- fMRIPrep figures such as BOLD reference, mask, registration, carpet/confounds, and normalization panels when present.
- Confounds TSV/JSON and preprocessing provenance.
- Official grounding: `docs/rag/vendor/fmriprep_official_outputs.md`.

### BOLD XCP-D

- XCP-D HTML report.
- XCP-D QC figures and plots, including motion, denoising, carpet plots, connectivity summaries, and report assets when produced by the container.
- XCP-D TSV tables for confounds, motion, QC, time series, and connectivity.
- Official grounding: `docs/rag/vendor/xcp_d_official_outputs.md`.

### T1 DeepPrep

- DeepPrep QC and HTML/report assets when produced by the container.
- FreeSurfer-compatible recon outputs, stats, surfaces, and QC images from the derivative tree.
- Official grounding: `docs/rag/vendor/deepprep_official_container_usage.md`.

### FreeSurfer

- FreeSurfer snapshots and stats such as `aseg.stats`, `aparc*.stats`, surface/segmentation QC images, and generated views when present.
- Official grounding: `docs/rag/vendor/freesurfer_official_container_reconall.md`, including `ReconAllOutputFiles`.
- Register native statistics such as `stats/aseg.stats` and `stats/lh.aparc.stats` in `outputs.tables` or `outputs.metrics` after parsing/copying.
- Register anatomical map derivatives such as `mri/orig.mgz` and `mri/aseg.mgz` in `outputs.maps` when exposed for download or converted preview.
- Register runtime records such as `scripts/recon-all.log` in `outputs.logs`.
- Use container-native FreeSurfer QC. Do not replace missing surface, segmentation, snapshot, or stats evidence with generated imagery.

## Result-Summary Requirements

Each container-native artifact must be registered with:

- `name`
- `path`
- `relative_path`
- `exists`
- `download_url`
- `content_type`
- `size_bytes`
- `source_stage`
- `container_image` or `pipeline`
- `provenance`
- `official_source_ids` in top-level artifact metadata and `provenance`

HTML reports belong in `outputs.reports`. PNG/SVG/JPEG/WebP assets belong in `outputs.figures` unless they are part of a report manifest. TSV/CSV/JSON metrics belong in `outputs.tables` or `outputs.metrics`. NIfTI/CIFTI/GIFTI maps belong in `outputs.maps`. Runtime logs belong in `outputs.logs`.

Accepted `official_source_ids` include `docs/rag/vendor/fmriprep_official_outputs.md`, `docs/rag/vendor/xcp_d_official_outputs.md`, `docs/rag/vendor/deepprep_official_container_usage.md`, `docs/rag/vendor/freesurfer_official_container_reconall.md`, `docs/rag/vendor/qsiprep_official_container_usage_outputs.md`, `docs/rag/vendor/qsirecon_official_container_usage_workflows.md`, `docs/rag/vendor/fsl_official_fast_dti_tools.md`, and `docs/rag/vendor/mrtrix3_official_dti_toolbox.md`.

`official_source_ids` are evidence pointers for RAG answers and frontend source display. They are not proof that a particular task succeeded or that an artifact was produced correctly; backend task status and result-summary remain authoritative.

Generated report assets under `reports/*` are classified as `derived_scientific_report` unless explicit metadata proves a container-native source. They should default to `source_stage=scientific_report`, `artifact_role=derived_presentation_asset`, `artifact_origin=generated_from_result_summary`, `native_artifact=false`, and `provenance.replaces_native_qc=false`. They can be previewed, but they must not satisfy `container_native_qc=true`.

## Container Decomposition Requirements

Workflow incubation must decompose Docker, Podman, Singularity, or Apptainer commands into explicit primitive contracts before any promotion suggestion. A container primitive should preserve:

- `runtime`
- `image`
- redacted `environment` and `environment_map`
- `arguments`
- `volumes`
- structured `mounts`
- `uses_gpu`
- `command_preview`

Each structured mount must include:

- `host_path`
- `container_path`
- `read_only`
- `role`
- `sandbox_scope_required`

Expected mount roles are `input_data`, `output_data`, `work_dir`, `templateflow_cache`, `license_file`, and `support`. Input data mounts must be read-only. License mounts must be read-only and must not expose license contents. Output, work, and TemplateFlow cache mounts must be scoped to the sandbox or project task root before production promotion.

## Incubation Validation Plan

Every incubating workflow proposal should include a `validation_plan` before human promotion review. The validation plan turns each primitive validation check into an evidence requirement:

- `plan_id`
- `minimum_passed_runs`
- `checks`
- `global_requirements`
- `production_enabled: false`

Each check should include `name`, `evidence_kind`, `expected_evidence`, and `source_stages`. Evidence kinds include `artifact`, `mount_audit`, `runtime`, `contract`, `parameter_audit`, and `review`.

The validation plan must require at least two passed sandbox runs, no production task side effects during incubation, redacted command/environment provenance, registered native reports and result-summary artifacts, and human approval before promotion is considered.

## Container Image Inspection Plan

Every incubating workflow with Docker, Podman, Singularity, or Apptainer primitives must include a `container_inspection_plan` before sandbox execution. The plan is executed by backend local/runtime tools only; the LLM may request or explain it, but may not run Docker or shell commands directly.

The inspection plan should record:

- image name plus digest, image id, or equivalent immutable content hash when available
- entrypoint, default command, user, working directory, labels, and environment keys without secret values
- pipeline version probes such as `fmriprep --version` or `xcp_d --version`
- native output path probes for reports, figures, tables, maps, and logs
- forbidden actions during inspection, including patient-data mounts, production task creation, license content logging, and full environment dumps

Validation checks that come from the inspection plan should use `evidence_kind: container_inspection`. Required checks include `container_image_inspected`, `container_digest_recorded`, `container_entrypoint_recorded`, `container_versions_recorded`, and `container_native_output_paths_verified`.

Backend sandbox validation may execute the inspection plan with local/runtime tools such as `docker image inspect`, `podman image inspect`, `singularity inspect --json`, or `apptainer inspect --json`. The executed inspection result is evidence for promotion review only; it must still keep `production_task_created: false` and must not start the scientific pipeline.

Official inspection grounding lives in `docs/rag/vendor/docker_official_image_inspect.md`, `docs/rag/vendor/podman_official_image_inspect.md`, and `docs/rag/vendor/singularity_apptainer_official_inspect.md`.

## Answering Rules

1. Start from backend task status, registered outputs, and result-summary.
2. Prefer container-native QC and report artifacts over generated summaries.
3. Mention missing native reports as an artifact gap, not as a scientific failure.
4. Do not claim a workflow completed if its native report or result-summary is absent.
5. If a generated gallery exists, describe it as an index over native artifacts, not a replacement.
6. Treat `official_source_ids` as source grounding only, not success evidence.
7. Do not infer clinical meaning from QC images or metric maps.

## Frontend Display

The frontend should display:

- Primary report: fMRIPrep/XCP-D/DeepPrep/FreeSurfer native HTML report when present.
- Supporting gallery: native QC figures and report assets.
- Tables: native TSV/CSV metrics with download links.
- Provenance: container image, command/script path, task id, workflow type, validation-only status, and `official_source_ids`.

If a native artifact cannot be embedded safely, show a download/open link with content type and size.

When a report-builder PNG or HTML asset exists without a matching container-native QC artifact, show it as a derived scientific report and flag the missing native QC evidence separately.
