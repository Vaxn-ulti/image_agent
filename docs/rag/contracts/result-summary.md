---
source_type: rag_contract
contract: result_summary
status: current_contract
retrieved_date: 2026-06-10
---

# Result Summary Contract RAG

## Purpose / 目的

The result-summary JSON is the preferred structured artifact for image_agent answers about completed workflow outputs. It should outrank generic RAG documents when discussing a specific task.

Endpoint: `/tasks/{task_id}/result-summary`

Artifact manifest endpoint: `/tasks/{task_id}/artifact-manifest`

Legacy fallback: `/tasks/{task_id}/outputs`

## Required Top-Level Fields

- `contract_version`
- `task_id`
- `workflow_type`
- `modality`
- `spaces`
- `feature_groups`
- `outputs`
- `provenance`

Public API responses may also include `workflow_metadata` from the workflow registry. It can contain `display_name`, `capability_summary`, `workflow_family`, `workflow_role`, `pipeline_stages`, `primary_outputs`, `qc_outputs`, `report_outputs`, `limitations`, `is_report_only`, and `agent_selectable`.

`workflow_metadata` is for display and interpretation only. `workflow_type` remains the stable machine id for task creation, confirmation fingerprint checks, database task records, artifact routing, and audit logs. Frontend, Agent, and RAG answers may use `workflow_metadata.display_name` and capability fields to explain what the workflow did, but they must preserve the raw `workflow_type` when referring to the task record.

`workflow_metadata.agent_selectable` tells frontend, Agent, and RAG consumers whether the stable public workflow is intended for Agent-facing launch selection. `agent_selectable` does not authorize task creation by itself; production task creation still requires registry lookup, preflight, human confirmation, fingerprint verification, `task_service.create_series_task()`, and the pipeline runner.

Historical or runtime aliases may be resolved to stable public workflow metadata. For example, a historical task or result-summary with `workflow_type=t1_deepprep` and `runtime_workflow_type=t1_deepprep` can expose metadata for the stable public workflow `t1_deepprep_anat_report`. The `runtime_workflow_type` field describes the pipeline runner alias when present. This does not rewrite the result-summary's raw `workflow_type`, and it does not authorize new task creation through the alias.

`summary_path` is omitted from public result-summary responses. Use `relative_path`, `download_url`, and artifact-manifest URLs for user-facing references; never expose backend absolute paths.

## Output Item Fields

Each artifact item should include:

- `name`
- `path`
- `relative_path`
- `exists`
- `download_url`
- `content_type`
- `size_bytes`

Common optional fields:

- `space`
- `atlas`
- `feature_group`
- `description`
- `unit`
- `table_schema`

## Modality Feature Groups

T1:

- `segmentation_volumes`
- `cortical_thickness`
- `surface_area`
- `regional_morphometry`
- `quality_control`

BOLD:

- `voxelwise_metrics`
- `connectivity`
- `qc_timeseries`
- `motion_confounds`

DWI:

- `tensor_metrics`
- `mni152_registration`
- `atlas_statistics`
- `quality_control`

## Agent Rules / Agent 规则

1. Backend DB task/output records rank first.
2. Result-summary JSON ranks before planning docs and RAG summaries.
3. Display `validation_only` or `placeholder_outputs` as planned/placeholder, not real features.
4. Use `feature_groups` and `outputs` sections to organize answers, not filename guesses.
5. Use `relative_path` and `download_url` for user-facing artifact references.
6. Use `workflow_metadata` to name and explain workflow capabilities, while keeping `workflow_type` as the task id field in machine-facing statements.
7. RAG answers must not create or relaunch tasks; fixed workflow launch still requires registry, preflight, human confirmation, confirmation fingerprint, `task_service.create_series_task()`, and the pipeline runner.

## Artifact Manifest

Use `/tasks/{task_id}/artifact-manifest` as the stable preview/download list for frontend artifact panels. It flattens result-summary `outputs.*` into safe artifact items with `relative_path`, `download_url`, `content_type`, `size_bytes`, `exists`, and `preview_kind`.

The rule is: do not expose backend absolute paths through the manifest. It recomputes download URLs through `/tasks/{task_id}/artifacts/{relative_path}` and omits missing or unsafe paths. The result-summary remains authoritative for scientific/result interpretation; the manifest is only a display/download convenience.

The manifest envelope may include registry-backed `workflow_metadata` and `runtime_workflow_type` copied from the public result-summary/task record normalization path. Frontend report/QC panels can use these fields to display workflow capability context without reinterpreting raw filenames or trusting stale runner-written metadata. `workflow_metadata` remains display/interpretation evidence only; stable `workflow_type` remains the machine id for task creation, confirmation fingerprints, database rows, and artifact routes.

Manifest items also classify display provenance:

- `artifact_category`: one of `container_native_qc`, `derived_scientific_report`, `frontend_preview_asset`, or `source_artifact`.
- `container_native_qc`: true only for native workflow/container artifacts, not report-builder substitutes.
- `derived_scientific_report`: true for report-layer assets generated from result-summary evidence, including unlabeled `reports/*` PNG/HTML assets.
- `frontend_preview_asset`: true when `preview_kind` is embeddable or directly previewable (`image`, `html`, `table`, or `json`).

Generated scientific report assets should carry `source_stage=scientific_report`, `artifact_role=derived_presentation_asset`, `artifact_origin=generated_from_result_summary`, `native_artifact=false`, and `provenance.replaces_native_qc=false`. These assets are useful for presentation, but they do not satisfy container-native QC evidence by themselves.

## Suggested Answer Shape

Task `<id>` ran `<workflow_metadata.display_name|workflow_type>` for `<modality>` with stable workflow id `<workflow_type>`. Its summary reports spaces `<spaces>` and feature groups `<feature_groups>`. The most relevant artifacts are `<outputs>`. Provenance says `<provenance status>`, so these outputs are `<real|validation-only|placeholder>`.
