# Common Workflow Errors RAG

## Purpose / 目的

Use for explaining failed or blocked tasks. Always prefer the actual backend `error_message`, logs, and task events first.

## Missing FreeSurfer License

Symptom:

- DeepPrep, fMRIPrep with FreeSurfer, or recon-all fails early.

Likely cause:

- License file missing, not mounted, unreadable, or path-specific to another host.

Agent response:

- "The workflow needs a valid FreeSurfer license file. Check the configured license path and container mount."

## BIDS Validation Failure

Symptom:

- Container refuses input or BIDS Validator reports errors.

Likely causes:

- Missing `dataset_description.json`.
- Missing BOLD `TaskName` or `RepetitionTime`.
- Mismatched sidecar basename.
- DWI missing `.bval` or `.bvec`.
- Unsupported labels or duplicate BIDS names.

Agent response:

- "Fix the BIDS input first; do not skip validation unless the operator intentionally accepts that risk."

## DICOM Conversion Failure

Symptom:

- Upload inventory reports DICOM files but no converted NIfTI outputs.
- `dcm2niix executable not found`.
- Some series convert while others are listed as partial conversion failures.

Likely causes:

- dcm2niix is absent from the backend runtime.
- The archive is corrupt, incomplete, or contains unsupported DICOM variants.
- Output directory permissions block converted NIfTI or BIDS sidecar JSON writing.

Agent response:

- "DICOM conversion must succeed before direct production workflow launch. Inspect the ingest inventory and conversion log summary, then install/repair dcm2niix or upload BIDS/NIfTI with required sidecars."
- Do not expose raw DICOM contents, patient identifiers, full sensitive paths, or PHI-bearing conversion logs.

## Wrong Modality For Workflow

Symptom:

- T1 workflow requested on BOLD/T2/FLAIR/DWI, or BOLD workflow requested on T1.

Agent response:

- "This workflow requires `<expected modality>` but the series is detected as `<actual modality>`."

## XCP-D Missing Derivatives

Symptom:

- XCP-D cannot find preprocessed BOLD, masks, confounds, transforms, or dataset description.

Likely cause:

- Input is raw BIDS rather than fMRIPrep-compatible derivatives, or required output spaces were not generated.
- The remote wrapper expected a DeepPrep-derived fMRIPrep-compatible input but received raw data or an incomplete derivative tree.

Agent response:

- "Run/repair BOLD preprocessing first, then pass the derivatives directory to XCP-D."
- "For the remote wrapper, check the fMRIPrep-compatible derivative path before rerunning XCP-D; the XCP-D input is not raw BIDS."

## TemplateFlow Cache Problems

Symptom:

- fMRIPrep/XCP-D cannot fetch templates, especially on offline HPC nodes.

Agent response:

- "Pre-fetch required templates and set `TEMPLATEFLOW_HOME` to a writable mounted cache."
- "For remote tasks, confirm `IMAGE_AGENT_TASK_TEMPLATEFLOW_DIR` is mounted; TemplateFlow cache is a support mount and should not be treated as the input dataset."

## Docker/GPU Runtime Problems

Symptoms:

- `--gpus all` unavailable.
- Container cannot see NVIDIA devices.
- Permission denied on output directory.

Agent response:

- "Check Docker GPU runtime, host driver/container compatibility, and writable output mounts."

## Output Discovery Missing

Symptom:

- Task completed, but frontend shows no structured result summary.

Likely cause:

- Outputs were not registered, summary JSON missing, or report generation failed after container completion.

Agent response:

- "Inspect registered outputs and the `summary/*_result_summary.json` path before rerunning the whole workflow."
