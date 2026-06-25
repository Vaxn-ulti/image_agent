# BIDS-like Inputs

## General

Construct minimal BIDS-like input under the task derivative directory:

`data/projects/{project_id}/derivatives/{task_id}/bids`

Use `dataset_description.json` with at least:

- `Name`
- `BIDSVersion`
- `DatasetType`

Use symlinks to raw/converted data where possible. Resolve symlink targets before Docker mounts.

## Validator Preflight

Use the official BIDS Validator boundary in `docs/rag/vendor/bids_validator_official_cli_docker.md` when explaining whether a staged BIDS-like tree is ready for production workflow launch.

- `bids-validator <dataset> --json`, `--format json`, or `--format json_pp` can provide machine-readable preflight evidence.
- `--ignoreWarnings` means warnings remain reportable unless explicitly ignored.
- `--ignoreNiftiHeaders` skips NIfTI-header-dependent checks; mention that limitation if it was used.
- `--datasetTypes` limits validation to raw, derivative, or study dataset types.
- `--recursive` includes derivative datasets found under `derivatives/` recursively.

## T1w

Path:

`sub-01/anat/sub-01_T1w.nii.gz`

Required:

- T1w NIfTI.

Workflow:

- `t1_deepprep`

## fMRI/BOLD

Path:

`sub-01/func/sub-01_task-rest_bold.nii.gz`

Recommended sidecars when available:

- JSON sidecar with task, repetition time, phase encoding, slice timing, and related metadata.

Workflow:

- `bold_deepprep`

Notes:

- Use DeepPrep for BOLD preprocessing.
- ALFF/fALFF are downstream metrics after preprocessing.

## DWI

Paths:

- `sub-01/dwi/sub-01_dwi.nii.gz`
- `sub-01/dwi/sub-01_dwi.bval`
- `sub-01/dwi/sub-01_dwi.bvec`
- `sub-01/dwi/sub-01_dwi.json` for production fast GPU DTI.

Workflow:

- `dwi_fast_gpu_dti`
- `dwi_qsiprep`
- `dwi_qsi_full`

Notes:

- `dwi_fast_gpu_dti` requires JSON metadata fields `PhaseEncodingDirection` and `TotalReadoutTime` so the backend can derive `acqparams.txt` instead of using a hard-coded phase-encoding row.
- QSIPrep/QSI full require `.bval` and `.bvec`; QSIRecon consumes completed QSIPrep output, not this raw BIDS-like tree.
