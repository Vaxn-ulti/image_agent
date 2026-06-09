# T1 DeepPrep Anatomical Report RAG

## Scope / 范围

Use this document when the user asks what a `t1_deepprep` task did, why T1 anatomy is needed, or how to read a T1 result-summary. This is workflow interpretation support, not a medical diagnosis.

## Workflow Purpose / 流程目的

`t1_deepprep` preprocesses a T1w anatomical MRI using a BIDS-like anatomical input and DeepPrep/FreeSurfer-derived outputs. The image_agent should describe it as an anatomical preprocessing and morphometry workflow: structural normalization, segmentation, cortical/subcortical summaries, and QC artifacts.

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
