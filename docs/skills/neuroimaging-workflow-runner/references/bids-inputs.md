# BIDS-like Inputs

## General

Construct minimal BIDS-like input under the task derivative directory:

`data/projects/{project_id}/derivatives/{task_id}/bids`

Use `dataset_description.json` with at least:

- `Name`
- `BIDSVersion`
- `DatasetType`

Use symlinks to raw/converted data where possible. Resolve symlink targets before Docker mounts.

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

Workflow:

- `dwi_qsiprep`
- `dwi_qsi_full`

QSIRecon consumes completed QSIPrep output, not this raw BIDS-like tree.
