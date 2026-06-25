---
source_type: rag_workflow
workflow_type: bold_fmriprep_xcpd_report
runtime_workflow_type: bold_fmriprep_xcpd_report
display_name: BOLD fMRIPrep + XCP-D processing, metrics, QC, and report
workflow_family: bold
workflow_role: complete_processing
capability_summary: Runs full BOLD preprocessing and XCP-D postprocessing, producing derived metrics, container-native QC artifacts, structured result summaries, and a scientific report.
agent_selectable: true
is_report_only: false
modality: BOLD
status: production_supported
retrieved_date: 2026-06-06
pipeline_stages:
  - BIDS preparation: Prepare supported BOLD NIfTI/BIDS input with required same-project T1/anat context.
  - fMRIPrep preprocessing: Run motion/coregistration/normalization-oriented BOLD preprocessing.
  - XCP-D postprocessing: Generate denoised derivatives and single-subject BOLD metrics.
  - result packaging: Register metrics, native QC artifacts, result summary, and report artifacts.
primary_outputs:
  - preprocessed BOLD derivatives
  - ALFF/fALFF/ReHo and connectivity metrics
  - result-summary.json
qc_outputs:
  - container-native fMRIPrep and XCP-D QC artifacts
  - HTML reports
  - QC figures
report_outputs:
  - HTML scientific report
  - report figures
  - report manifest
limitations:
  - Not report-only; requires BOLD-compatible input, same-project T1/anat data, configured scripts, containers, and FreeSurfer license.
official_grounding:
  - docs/rag/vendor/fmriprep_official_container_usage.md
  - docs/rag/vendor/fmriprep_official_outputs.md
  - docs/rag/vendor/xcp_d_official_container_usage.md
  - docs/rag/vendor/xcp_d_official_outputs.md
  - docs/rag/vendor/templateflow_official_cache_archive_client.md
  - docs/rag/vendor/bids_official_mri_derivatives.md
expected_artifacts:
  - fMRIPrep-style visual reports and derivatives when wrapper evidence proves native generation
  - XCP-D denoised BOLD outputs
  - XCP-D QC time series and reports
  - parcellated time series and connectivity matrices
  - task-scoped result-summary and artifact-manifest entries from the fixed workflow pipeline runner
unsupported_boundaries:
  - not report-only; this is a complete fixed workflow with preprocessing, postprocessing, QC, summary, and report outputs
  - do not bypass registry, preflight, human confirmation, confirmation fingerprint, task_service.create_series_task(), or the pipeline runner
  - XCP-D input is fMRIPrep-compatible derivatives, not raw BIDS
  - do not pass API keys, sudo passwords, or fixed evidence-project paths into child scripts
  - do not infer diagnosis, cognition, psychiatric status, or group effects from BOLD metrics
---

# BOLD fMRIPrep + XCP-D Report RAG

## Scope / 范围

Use this document when the user asks about the fixed workflow `bold_fmriprep_xcpd_report`, the BOLD/fMRI preprocessing and postprocessing chain, fMRIPrep, XCP-D, denoising, functional connectivity, ALFF/fALFF/ReHo, or BOLD QC.

Note: in this repo, BOLD preprocessing may also be implemented as `bold_deepprep` plus downstream metrics. Always trust the backend task record and workflow registry over this document.

Image Agent workflow identity: `bold_fmriprep_xcpd_report` is a fixed workflow and stable public `workflow_type`. Its runtime runner is also `bold_fmriprep_xcpd_report`. `workflow_metadata.is_report_only=false`; the workflow is not just a report generator. It runs preprocessing/postprocessing, registers container-native QC and structured result evidence, and may also produce report artifacts. Creating a task for this workflow must pass registry, preflight, human confirmation, confirmation fingerprint, `task_service.create_series_task()`, and the pipeline runner.

Production remote runtime: the backend launches this workflow through a remote-script wrapper. The wrapper passes task-specific BIDS/output/work/log/license paths with `IMAGE_AGENT_TASK_*` environment variables. The fMRIPrep and XCP-D scripts must prefer these variables over fixed evidence-project paths for strict production acceptance evidence.

The wrapper applies `IMAGE_AGENT_REMOTE_SCRIPT_TIMEOUT_SEC` to each script. A `TimeoutExpired` result is reported as remote script timed out, with a redacted log tail for partial stdout retention. Script paths must be regular files, not directories, raised wrapper errors should use path-safe script labels rather than full host paths, success summaries use path-safe script labels, and public preflight check summaries use path-safe labels. The child script environment is a safe child environment allowlist plus task paths; do not pass `OPENAI_API_KEY`, `DEEPSEEK_API_KEY`, or `IMAGE_AGENT_SUDO_PASSWORD`. Script stdout/stderr must be redacted before task logs or RAG-facing summaries mention it.

Current XCP-D remote-wrapper contract:

- `run_xcpd_deepprep_115.sh` is the task-115 evidence wrapper for XCP-D after DeepPrep.
- The XCP-D handoff is a DeepPrep-derived fMRIPrep-compatible input; it is not raw BIDS.
- The wrapper writes XCP-D derivatives under `IMAGE_AGENT_TASK_XCPD_DIR`.
- The fixed fMRIPrep/XCP-D production path requires a same-project T1/anat companion for the BOLD series. If no supported T1/anat series is available, task creation must be blocked before production launch instead of letting fMRIPrep fail with missing T1w inputs.
- The wrapper passes TemplateFlow through `IMAGE_AGENT_TASK_TEMPLATEFLOW_DIR`; TemplateFlow cache is a support mount, not user input data.
- Full production preflight checks the shared TemplateFlow cache before human confirmation: the cache must be writable and the fixed prewarmed `MNI152NLin2009cAsym`, `MNI152NLin6Asym`, and `OASIS30ANTs` files must exist with non-zero size. The two MNI templates require res-01/res-02 T1w and brain-mask files; `MNI152NLin2009cAsym` additionally requires the fMRIPrep BOLD-reference, brain-probseg, and carpet-dseg files used by BOLD reference skull-stripping and carpet-plot generation. XCP-D QC and atlas resampling require the TemplateFlow H5 transforms in both directions between `MNI152NLin6Asym` and `MNI152NLin2009cAsym`. `OASIS30ANTs` is limited to the official res-01 T1w, brain T1w, and brain-mask files used by fMRIPrep brain extraction. Missing TemplateFlow files are runtime setup blockers, not scan pathology.
- The expected XCP-D flags for this wrapper are `--mode linc`, `--input-type fmriprep`, `--file-format nifti`, `--linc-qc y`, and `--abcc-qc y`.

## Workflow Purpose / 流程目的

fMRIPrep prepares BOLD data and anatomical references in BIDS derivatives form. XCP-D consumes fMRIPrep-like derivatives to run BOLD postprocessing, denoising, QC, and connectivity-oriented outputs.

中文: fMRIPrep 做功能像预处理; XCP-D 在预处理结果上做去噪, 质量控制和功能连接/时间序列等后处理.

## Expected Inputs / 输入

- A BIDS-valid dataset or BIDS-like task tree with at least one BOLD run.
- T1w anatomy is normally needed by fMRIPrep unless explicitly using a restricted mode.
- BOLD JSON should include `TaskName` and `RepetitionTime` or equivalent timing fields.
- XCP-D input should be fMRIPrep-style derivatives with preprocessed BOLD, masks, confounds, boldref, and transform files in supported spaces.
- DeepPrep-derived fMRIPrep-compatible input may satisfy the XCP-D derivative boundary when the output layout contains the required fMRIPrep-like files.

## Expected Outputs / 输出

For fMRIPrep-like preprocessing:

- Preprocessed BOLD image in a standard or native space.
- Brain mask, boldref, confounds TSV/JSON, transforms, and HTML visual reports.
- Native reports, figures, tables, maps, and logs should carry `official_source_ids` such as `docs/rag/vendor/fmriprep_official_outputs.md`.

For XCP-D-like postprocessing:

- Denoised BOLD outputs.
- Motion/QC time series such as framewise displacement and DVARS.
- Parcellated time series and functional connectivity matrices.
- Optional ALFF, ReHo, or other postprocessing outputs depending on mode and flags.
- Native reports, figures, tables, maps, and logs should carry `official_source_ids` such as `docs/rag/vendor/xcp_d_official_outputs.md`.

## Result-Summary Reading Hints

- Prefer `/tasks/{task_id}/result-summary` over legacy output lists.
- Use `feature_groups`: voxelwise_metrics, connectivity, qc_timeseries, motion_confounds.
- BOLD metrics should not be described as group inference unless the workflow is explicitly a group/second-level workflow.
- If `validation_only=true`, report command readiness only; do not claim scientific results.
- Treat `official_source_ids` as evidence pointers for expected native artifacts, not proof that the task succeeded.
- Backend task status and result-summary remain authoritative for success/failure and available outputs.

## Common User Questions

- "What is FD?" Framewise displacement is a motion summary. High values can suggest motion contamination, but thresholds are study-specific.
- "What is ALFF/fALFF?" Low-frequency fluctuation metrics used in resting-state fMRI research. They are not clinical biomarkers by themselves.
- "What is connectivity?" Correlation or related association between BOLD time series from regions or seeds; interpretation depends on preprocessing and study design.

## Safety / 安全

Never infer cognition, psychiatric status, dementia, tumor, or treatment advice from BOLD metrics. Explain limitations and recommend domain expert review for clinical claims.
