---
source_type: rag_workflow
workflow_type: t1_deepprep_anat_report
runtime_workflow_type: t1_deepprep
display_name: T1 DeepPrep anatomical processing, QC, and report
workflow_family: t1
workflow_role: anat_processing
capability_summary: Runs anatomical T1 processing with DeepPrep/FreeSurfer-derived measurements, QC artifacts, structured result summary, tables, figures, and an HTML report.
agent_selectable: true
is_report_only: false
modality: T1
status: production_supported
retrieved_date: 2026-06-10
pipeline_stages:
  - BIDS preparation: Prepare supported T1 NIfTI input for anatomical processing.
  - DeepPrep anatomical processing: Generate anatomical derivatives and FreeSurfer-compatible statistics.
  - result packaging: Register summaries, tables, figures, QC, and report artifacts for frontend review.
primary_outputs:
  - anatomical derivatives
  - FreeSurfer/DeepPrep statistics
  - regional tables
  - result-summary.json
qc_outputs:
  - DeepPrep/FreeSurfer QC artifacts when available
report_outputs:
  - HTML scientific report
  - report figures
limitations:
  - Requires supported T1 input and configured FreeSurfer license/container runtime.
official_grounding:
  - docs/rag/vendor/deepprep_official_container_usage.md
  - docs/rag/vendor/freesurfer_official_container_reconall.md
  - docs/rag/vendor/freesurfer_official_license.md
  - docs/rag/vendor/bids_official_mri_derivatives.md
expected_artifacts:
  - summary/t1_result_summary.json
  - summary/t1_scientific_report_summary.json
  - DeepPrep QC HTML reports
  - FreeSurfer stats tables
  - registered maps, figures, reports, tables, and logs
unsupported_boundaries:
  - no diagnosis, prognosis, dementia, tumor, or treatment advice
  - do not launch on FLAIR, T2, DWI, or BOLD unless backend marks the series T1-compatible
  - do not treat placeholder contracts as real DeepPrep/FreeSurfer measurements
  - do not replace missing container-native QC with generated images
  - do not replace the stable workflow_type with the runtime_workflow_type in confirmations, fingerprints, task records, or user-facing launch controls
  - not a report-only workflow; it includes anatomical processing, QC, structured summaries, and report artifacts
---

# T1 DeepPrep Anatomical Report RAG

## Scope / 范围

Use this document when the user asks what a `t1_deepprep_anat_report` task did, why T1 anatomy is needed, or how to read a T1 result-summary. This is workflow interpretation support, not a medical diagnosis.

Image Agent workflow identity: `t1_deepprep_anat_report` is the stable public workflow_type for Agent confirmation, fingerprints, database task records, frontend launch controls, and RAG explanations. `t1_deepprep` is the runtime_workflow_type used by the pipeline runner. `workflow_metadata.is_report_only=false`; this is not a report-only workflow even though the stable id contains `report`.

## Workflow Purpose / 流程目的

`t1_deepprep_anat_report` launches the T1 DeepPrep anatomical processing lane; the runtime runner `t1_deepprep` preprocesses a T1w anatomical MRI using a BIDS-like anatomical input and DeepPrep/FreeSurfer-derived outputs. The image_agent should describe it as an anatomical preprocessing and morphometry workflow: structural normalization, segmentation, cortical/subcortical summaries, QC artifacts, structured results, and report artifacts.

In Chinese: T1 DeepPrep 主要用于结构像预处理和形态学摘要, 包括分割, 皮层厚度/表面积等 FreeSurfer 统计, 以及质量控制报告.

## Expected Inputs / 输入

- A detected T1/T1w/MPRAGE-like series.
- BIDS path like `sub-<label>/anat/sub-<label>_T1w.nii.gz` with JSON sidecar when available.
- FreeSurfer license mounted for real DeepPrep/FreeSurfer processing.
- Do not launch on FLAIR, T2, DWI, or BOLD unless the backend explicitly marks the series as T1-compatible.

## Expected Outputs / 输出

- `summary/t1_result_summary.json`: primary structured result contract.
- `summary/t1_scientific_report_summary.json`: optional presentation-layer report bundle.
- FreeSurfer stats inventory and regional TSV tables when real stats are parsed.
- Segmentation, masks, transforms, QC report files, and preview/report figures when registered.
- FreeSurfer official outputs include `mri/orig.mgz`, `mri/aseg.mgz`, `surf/lh.white`, `surf/lh.pial`, `label/lh.aparc.annot`, `stats/aseg.stats`, `stats/lh.aparc.stats`, and `scripts/recon-all.log` when the corresponding files exist.
- FreeSurfer stats parsed from native `stats/*.stats` files should be registered in `outputs.tables` or `outputs.metrics`; anatomical maps belong in `outputs.maps`; runtime logs belong in `outputs.logs`.
- DeepPrep `QC/` HTML report artifacts should appear in `outputs.reports` when present.
- DeepPrep previewable report figures should appear in `outputs.figures` and be displayed as container-native DeepPrep QC, not as generated substitute imagery.
- FreeSurfer snapshots or derived views should be displayed as container-native FreeSurfer QC only when generated from the native derivative tree.

## Result-Summary Reading Hints

- Trust `provenance.extraction_status`.
- `real_deepprep_freesurfer_stats` means the summary parsed real FreeSurfer statistics.
- `placeholder_contract_pending_real_deepprep_parser` or `placeholder_outputs=true` means planned/contract data, not real derived measurements.
- Use `feature_groups` to organize the response: segmentation volumes, cortical thickness, surface area, regional morphometry, quality control.

## Interpretation Boundaries / 解释边界

Do say: "The workflow produced FreeSurfer-derived morphometry summaries and QC artifacts."

Do not say: "This subject has atrophy/dementia/tumor" unless a qualified clinician-provided report is present. The agent may explain what a feature type usually represents, but must not diagnose.

## Good Agent Answer Pattern

1. Start with task state from backend records.
2. Cite the result-summary path and report artifacts if present.
3. Summarize what was computed.
4. Note whether outputs are real, validation-only, or placeholder.
5. Add non-diagnostic safety language.
