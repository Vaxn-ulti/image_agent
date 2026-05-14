# Contracts

## API

Baseline endpoints:

- `POST /auth/login`
- `GET /projects`
- `POST /projects`
- `POST /projects/{project_id}/upload`
- `GET /projects/{project_id}/series`
- `GET /series/{series_id}`
- `POST /series/{series_id}/run`
- `GET /tasks/{task_id}`
- `GET /tasks/{task_id}/logs`
- `GET /tasks/{task_id}/outputs`
- `POST /chat`

Phase 4 ingest endpoints may include upload-session ingest and inventory status endpoints. Keep synchronous tiny-upload fast paths consistent with the persisted status endpoint output.

## Task States

Use only:

- `queued`
- `running`
- `completed`
- `completed_with_partial_failures` for ingest inventory lifecycle where supported.
- `failed`
- `cancelled`

If task and ingest lifecycle vocabularies diverge, document that distinction.

## Workflow Types

Supported MVP workflows:

- `t1_deepprep`
- `bold_deepprep`
- `dwi_qsiprep`
- `dwi_qsirecon`
- `dwi_qsi_full`
- `dicom_convert`
- `bold_alff`
- `bold_falff`

Validation variants may use a suffix such as `_validate` if consistent with existing code.

## BIDS-like Rules

Never overwrite an existing target artifact during ingest. Use `run-*`, `acq-*`, or both.

Suggested targets:

- T1w: `sub-<label>/anat/sub-<label>[_acq-<label>][_run-<n>]_T1w.nii.gz`
- BOLD: `sub-<label>/func/sub-<label>_task-<label>[_acq-<label>][_run-<n>]_bold.nii.gz`
- DWI: `sub-<label>/dwi/sub-<label>[_acq-<label>][_run-<n>]_dwi.nii.gz`

Metadata precedence:

1. Sidecar JSON.
2. DICOM tags.
3. NIfTI header.
4. Filename tokens.

## Workflow Dependencies

- T1w DeepPrep requires T1w input.
- BOLD DeepPrep requires BOLD input and BIDS-like func placement.
- QSIPrep requires DWI NIfTI plus `.bval` and `.bvec`.
- QSIRecon requires a completed QSIPrep task output and a valid `--recon-spec`.
- Full QSI chain runs QSIPrep before QSIRecon and skips QSIRecon if QSIPrep fails.
- DICOM conversion requires a DICOM archive series and produces NIfTI outputs before downstream modality processing.
- BOLD ALFF/fALFF are downstream metric tasks and require prior BOLD preprocessing.
