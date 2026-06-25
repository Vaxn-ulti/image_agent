# Dataset Ingest Workflow

## Purpose

Normalize mixed DICOM/NIfTI uploads into deterministic inventory and BIDS-like project data that downstream DeepPrep, QSIPrep, and QSIRecon workflows can validate or run.

## Inputs

- Project id.
- Upload session or uploaded files.
- DICOM archives/folders.
- NIfTI files.
- Sidecar JSON files.
- DWI `.bval` and `.bvec` files.

## Metadata Precedence

1. Sidecar JSON.
2. DICOM tags.
3. NIfTI header.
4. Filename tokens.

Do not use LLM classification for modality detection.

## Lifecycle

1. Receive upload and persist raw files.
2. Create ingest/session record.
3. Group DICOM by `SeriesInstanceUID` with patient/study guardrails.
4. Convert DICOM to NIfTI where supported.
5. Normalize NIfTI and sidecars.
6. Detect modality and sequence.
7. Build BIDS-like targets without overwrite.
8. Produce inventory.
9. Compute workflow eligibility.

Normal ingest should be asynchronous. Tiny synchronous fast path is acceptable only when the persisted inventory endpoint returns the same result.

## BIDS-like Naming

Never overwrite. Add entities deterministically:

- Use `run-<n>` for repeated acquisitions.
- Use `acq-<label>` for semantically distinct acquisitions.
- Use both when needed.

Common targets:

- T1w: `sub-<id>/anat/sub-<id>[_acq-<label>][_run-<n>]_T1w.nii.gz`
- BOLD: `sub-<id>/func/sub-<id>_task-<label>[_acq-<label>][_run-<n>]_bold.nii.gz`
- DWI: `sub-<id>/dwi/sub-<id>[_acq-<label>][_run-<n>]_dwi.nii.gz`

## Inventory Output

Inventory should include:

- Lifecycle state.
- Input file counts.
- Conversion counts.
- Detected modalities.
- BIDS-like target paths.
- Partial failures.
- Unsupported recognized sequences.
- Workflow eligibility and reasons.

## Workflow Eligibility

- T1w -> `t1_deepprep`.
- BOLD/fMRI -> `bold_deepprep`.
- DWI + `.bval` + `.bvec` -> `dwi_qsiprep` and `dwi_qsi_full`.
- Completed QSIPrep output -> `dwi_qsirecon`.

## Unsupported Handling

For recognized but unsupported processing, surface exactly:

`Current software does not support radiomics/processing for this sequence.`

## Concrete Eval Cases

1. Mixed T1/BOLD/DWI upload returns all three supported workflow families when sidecars are complete.
2. DWI without gradients is detected but QSIPrep eligibility is false with a missing-gradient reason.
3. Two BOLD runs do not overwrite; second target receives deterministic `run-*`.
4. Partial DICOM conversion returns completed-with-partial-failures inventory and preserves successful series.
