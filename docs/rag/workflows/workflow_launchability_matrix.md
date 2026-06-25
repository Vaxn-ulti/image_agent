---
source_type: rag_workflow
workflow_type: workflow_launchability_matrix
status: current_contract
retrieved_date: 2026-06-08
official_grounding:
  - docs/rag/vendor/deepprep_official_container_usage.md
  - docs/rag/vendor/fmriprep_official_outputs.md
  - docs/rag/vendor/xcp_d_official_outputs.md
  - docs/rag/vendor/fsl_official_fast_dti_tools.md
  - docs/rag/vendor/mrtrix3_official_dti_toolbox.md
  - docs/rag/vendor/qsiprep_official_container_usage_outputs.md
  - docs/rag/vendor/qsirecon_official_container_usage_workflows.md
  - docs/rag/vendor/mriqc_official_container_usage_outputs.md
  - docs/rag/vendor/dpabi_official_container_boundary.md
expected_artifacts:
  - backend workflow_eligibility envelope for runnable and blocked workflow lists
  - real task ids and task states for any success claim
  - /tasks/{task_id}/result-summary for completed outputs
  - /tasks/{task_id}/artifact-manifest for frontend preview and download surfaces
  - strict remote smoke acceptance JSON and verifier passed evidence before release readiness
unsupported_boundaries:
  - do not create production tasks from this matrix alone
  - do not present incubation_reference rows as production-supported launch options
  - do not treat official container documentation as proof of Image Agent runtime support
  - do not count skipped_missing_model_config or local-only checks as release acceptance
  - do not expose backend absolute paths, secrets, or patient identifiers in readiness evidence
---

# Workflow Launchability Matrix

## Scope

Use this matrix when a user or agent asks whether a workflow is currently launchable, production-supported, legacy/explicit, incubation-only, or unsupported in Image Agent.

Do not create production tasks from this matrix. `workflow_eligibility` remains authoritative for launchability on a specific uploaded series, and `/tasks/{task_id}/result-summary` remains authoritative for completed outputs. Backend task records, registered outputs, and remote strict smoke evidence outrank this RAG document.

Status vocabulary:

- `production_supported`: backend-supported lane with current eligibility/result-summary expectations and real remote evidence requirements.
- `incubation_reference`: official container or workflow documentation exists, but Image Agent needs backend workflow code, output discovery, result-summary/artifact contract coverage, and remote promotion evidence before production task creation.
- `external_reference_only`: useful official ecosystem context, not a current Image Agent launch lane.
- `unsupported_external`: do not present as a supported Image Agent workflow; answer with boundary wording and supported alternatives.

## Matrix

| Workflow or family | Status | Current launch boundary | Required evidence before user-facing success claims | Source and QC boundary |
| --- | --- | --- | --- | --- |
| `t1_deepprep_anat_report` | `production_supported` | `t1_deepprep_anat_report` is the stable public workflow_type; `t1_deepprep` is the runtime_workflow_type. Launch only for T1-compatible series after registry preflight, human confirmation, confirmation fingerprint, `task_service.create_series_task()`, and the pipeline runner. It is not report-only: `workflow_metadata.is_report_only=false`. | Real completed task, parsed DeepPrep/FreeSurfer stats, registered maps/tables/reports, and `/tasks/{task_id}/result-summary`. Current evidence includes real task ids 40 and 41. | DeepPrep and FreeSurfer official docs ground expected outputs. Container-native QC source ids may include `docs/rag/vendor/deepprep_official_container_usage.md` and `docs/rag/vendor/freesurfer_official_container_reconall.md`. |
| `t1_deepprep` | `production_supported` | Runtime alias for the T1 pipeline runner, not the preferred public launch id. Frontend, Agent confirmation, fingerprints, and task records should use `t1_deepprep_anat_report` unless reading historical tasks. | Use backend task records to distinguish historical/runtime alias records from current fixed workflow launches. | Same DeepPrep and FreeSurfer grounding as `t1_deepprep_anat_report`; do not let the alias replace the stable public workflow_type in new launch flows. |
| `bold_deepprep` | `production_supported` | Launch only for BOLD-compatible series with BIDS-like func placement and required metadata. | Completed DeepPrep task with registered outputs before downstream metrics or XCP-D handoff. Backend records decide whether BOLD preprocessing succeeded. | DeepPrep official docs ground expected preprocessing outputs. Do not infer XCP-D outputs from BOLD DeepPrep alone. |
| `bold_second_level` | `production_supported` | Single-subject downstream BOLD metrics after a completed `bold_deepprep` task from the same project/series; not group inference. | Real completed task, MNI152 maps/tables/connectivity/QC outputs, `summary/bold_result_summary.json`, and result-summary feature groups. Current evidence includes real task ids 110 and 111. | Result-summary output and registered report artifacts are authoritative. Container-native QC source ids may include fMRIPrep/XCP-D only when the underlying artifacts actually come from those native outputs or remote-wrapper evidence. |
| `bold_fmriprep_xcpd_report` | `production_supported` | fixed workflow that must pass registry, preflight, human confirmation, confirmation fingerprint, task_service.create_series_task(), and the pipeline runner. It is not report-only: `workflow_metadata.is_report_only=false`. The wrapper must use task-scoped `IMAGE_AGENT_TASK_*` env paths, redact logs, avoid fixed evidence-project paths, and treat XCP-D input as fMRIPrep-compatible derivatives rather than raw BIDS. | Strict launch evidence requires Agent confirmation/resume, runtime toolchain evidence, completed task status, fMRIPrep/XCP-D native QC/report artifacts, result-summary, artifact manifest, task-events, ObserveRepair read-only evidence, and strict smoke without leaked paths. | docs/rag/workflows/bold_fmriprep_xcpd_report.md plus fMRIPrep/XCP-D vendor docs ground expected native outputs. Do not describe it as a simple report generator; backend task/result evidence remains authoritative for success claims. |
| `dwi_fast_gpu_dti` | `production_supported` | Launch only when DWI NIfTI, `.bval`, `.bvec`, and JSON sidecar with `PhaseEncodingDirection` and `TotalReadoutTime` are present or accepted by legacy BIDS sidecar logic. | Real completed task with FA/MD/AD/RD native maps, MNI152 maps, regional TSVs, QC/provenance, finite-map evidence, and `validation_only=false`. Current evidence includes real task ids 107, 112, and 114. | Uses host FSL GPU `eddy_cuda` and MRtrix commands from the QSIPrep image as a toolbox. It is not full QSIPrep or QSIRecon. Container-native QC source ids include FSL, MRtrix3, and QSIPrep toolbox grounding. |
| `dwi_qsiprep` | `incubation_reference` | Legacy/explicit DWI lane only. Do not make it the default DWI recommendation while `dwi_fast_gpu_dti` is the production lane. | Promotion requires full backend launch policy, CUDA eddy validation, result-summary/artifact coverage, remote completed tasks, and strict smoke evidence with real task ids. | docs/rag/vendor/qsiprep_official_container_usage_outputs.md grounds official QSIPrep usage and visual reports. Official docs do not prove current Image Agent production readiness. |
| `dwi_qsirecon` | `incubation_reference` | Requires completed QSIPrep output; never launch directly against raw DWI files. Backend-approved profiles only. | Promotion requires completed QSIPrep dependency evidence, approved `--recon-spec`, output discovery for selected profiles, result-summary schema, artifact manifest, and remote completed task evidence. | docs/rag/vendor/qsirecon_official_container_usage_workflows.md grounds QSIRecon usage, built-in workflows, and custom YAML boundaries. Do not imply arbitrary user YAML is production-runnable. |
| `dwi_qsi_full` | `incubation_reference` | Legacy/explicit chain that runs QSIPrep before QSIRecon and must skip QSIRecon if QSIPrep fails. | Promotion requires both QSIPrep and QSIRecon acceptance evidence, dependency-aware task state, registered native QC/report artifacts, and strict remote smoke. | Cite both QSIPrep and QSIRecon curated vendor documents; do not describe fast DTI outputs as coming from this chain. |
| `mriqc` | `incubation_reference` | Official external QC workflow, not registered in current Image Agent workflow registry. Keep `production_task_created=false` unless a future backend workflow is added. | Promotion requires backend workflow code, BIDS-app mount contract, output discovery for reports/IQMs, result-summary/artifact-manifest coverage, privacy review for MRIQC IQM submission behavior, and real remote task ids. | docs/rag/vendor/mriqc_official_container_usage_outputs.md grounds official MRIQC usage and reports. It does not authorize current Image Agent MRIQC launch. |
| `dpabi` | `unsupported_external` | External ecosystem reference only. Not a supported Image Agent workflow and not a current task lane. | Do not promise promotion without a new backend design, validated container command, output discovery, result-summary contract, and remote acceptance. | docs/rag/vendor/dpabi_official_container_boundary.md grounds the unsupported boundary. Do not add DPABI to container-native QC source ids. |

## Answering Rules

- Start from backend records for live projects and series. If a series has `workflow_eligibility`, use that envelope for runnable and blocked workflow lists.
- Use this matrix to explain product maturity, not to bypass server-side confirmation or preflight.
- For production-supported rows, still avoid success claims until the task is completed and result-summary/artifact evidence exists.
- For incubation rows, say that official container documentation exists and list the missing Image Agent promotion evidence.
- For `unsupported_external`, say it is not a supported Image Agent workflow and name the currently supported alternatives.
- Container-native QC source ids are provenance pointers for expected artifact families; they are not proof that a particular task succeeded.
- Remote promotion requires real task ids, upload/project ids where relevant, strict smoke evidence, result-summary output, artifact-manifest evidence, and no leaked backend paths.
