# Container-Native QC Registration

Use this reference when designing or reviewing workflow output discovery.

## Runner Requirements

1. Discover native reports produced by the container before creating custom galleries.
2. Register fMRIPrep HTML reports, XCP-D HTML reports, DeepPrep QC, and FreeSurfer snapshots/stats as first-class artifacts.
3. Preserve native relative paths under the task output root.
4. Include native report assets in result-summary with content type, size, stage, provenance, and `official_source_ids`.
5. Store `official_source_ids` in top-level artifact metadata and `provenance` for each native QC/report/figure/table/map/log artifact.
6. Fail or mark incomplete when required native QC for a production workflow is missing.
7. Generated report indexes or report-builder PNGs may link to or summarize native artifacts, but must be labeled as derived presentation assets and must not replace them.

## Expected Categories

- `outputs.reports`: native HTML reports/report manifests plus explicitly labeled scientific-report presentation assets when generated.
- `outputs.figures`: native PNG/SVG/JPEG/WebP QC images.
- `outputs.tables`: TSV/CSV/JSON tables from the container.
- `outputs.maps`: NIfTI/CIFTI/GIFTI maps.
- `outputs.logs`: fMRIPrep/XCP-D/DeepPrep/FreeSurfer runtime logs.

For the BOLD fMRIPrep/XCP-D remote wrapper, XCP-D artifacts discovered below the task XCP-D output directory should carry `source_stage: xcpd`. Reports and figures produced by XCP-D itself are container-native XCP-D QC. Generated scientific report assets may summarize those artifacts, but they must not replace native XCP-D QC.

Official output summaries:

- `docs/rag/vendor/fmriprep_official_outputs.md`: fMRIPrep subject HTML reports, preprocessed derivatives, and confounds.
- `docs/rag/vendor/xcp_d_official_outputs.md`: XCP-D participant reports, executive summaries, QC, time series, connectivity, ALFF/ReHo, and confounds outputs.
- `docs/rag/vendor/deepprep_official_container_usage.md`: DeepPrep container usage and expected derivative/QC context.
- `docs/rag/vendor/freesurfer_official_container_reconall.md`: FreeSurfer recon-all outputs, stats, logs, and QC expectations.
- `docs/rag/vendor/qsiprep_official_container_usage_outputs.md`: QSIPrep container usage and preprocessing outputs.
- `docs/rag/vendor/qsirecon_official_container_usage_workflows.md`: QSIRecon container usage and reconstruction workflow outputs.
- `docs/rag/vendor/fsl_official_fast_dti_tools.md`: FSL FAST/DTI tool outputs and expected maps/tables.
- `docs/rag/vendor/mrtrix3_official_dti_toolbox.md`: MRtrix3 DTI command outputs and expected maps/tables/logs.

## Production Gate

A production workflow is not accepted until native QC/report discovery is checked and the result-summary records whether each expected native artifact exists.

`official_source_ids` are evidence pointers for RAG answers and frontend source display. They do not prove that a task succeeded; backend task status and result-summary remain authoritative.

Generated scientific report assets should carry `source_stage: scientific_report`, `artifact_role: derived_presentation_asset`, `artifact_origin: generated_from_result_summary`, `native_artifact: false`, and `provenance.replaces_native_qc: false`.
