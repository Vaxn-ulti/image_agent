# Product Context

## Scope

Image Agent is a remote-compute MVP with a React/Vite desktop UI and FastAPI backend. The backend owns storage, ingest, BIDS-like construction, workflow validation/execution, task status, logs, outputs, and DeepSeek chat grounding.

## Data Path

Uploads land under:

`data/projects/{project_id}/raw`

Workflow derivatives land under:

`data/projects/{project_id}/derivatives/{task_id}`

Logs land under:

`data/projects/{project_id}/logs/{task_id}.log`

## Supported Ingest

The MVP supports mixed uploads:

- DICOM archives or folders.
- NIfTI files.
- Sidecar JSON.
- DWI gradient files `.bval` and `.bvec`.

Ingest should produce deterministic inventory and BIDS-like placement. It should not silently overwrite BIDS artifacts; use `run-*` and/or `acq-*` entities when collisions occur.

Metadata precedence:

1. Sidecar JSON.
2. DICOM tags.
3. NIfTI header.
4. Filename tokens.

## Supported Workflows

MVP workflow family:

- `t1_deepprep`: DeepPrep T1w preprocessing.
- `bold_deepprep`: DeepPrep fMRI/BOLD preprocessing.
- `dwi_qsiprep`: QSIPrep DWI preprocessing.
- `dwi_qsirecon`: QSIRecon reconstruction from completed QSIPrep output.
- `dwi_qsi_full`: chained QSIPrep then QSIRecon.

Each workflow may have a validate-only variant that resolves Docker image availability, bind mounts, and command string without launching the container.

## DWI/QSI Runtime Position

Historical DWI QSIPrep tasks `46` and `47` used `eddy_cpu`, ran too long, were stopped, and are marked `failed`. Do not tell users to retry that CPU path as the product recommendation.

Current DWI preprocessing strategy is CUDA-oriented QSIPrep:

- Backend generates `eddy_cuda_config.json`.
- Command mounts it at `/eddy_cuda_config.json`.
- Command passes `--eddy-config /eddy_cuda_config.json`.
- Config contains `use_cuda: true`, `num_threads >= 4`, `dont_peas: true`, `cnr_maps: true`, default `niter: 3`, and an auto-inferred `is_shelled` value from b-values.

`pennlinc/qsiprep:latest` exposes `eddy_cuda11.0` at `/app/.pixi/envs/qsiprep/bin/`. Detection uses `eddy_cuda*` glob to accept versioned binaries. Real DWI tasks 61 and 62 are running with GPU/CUDA eddy.

For QSIRecon, current docs do not confirm a CUDA-only CLI flag. The product uses `docker run --gpus all` and records whether GPU is visible inside the container. QSIRecon requires `--recon-spec` to select the reconstruction pipeline.

## fMRI/BOLD Position

fMRI/BOLD must be treated as supported for DeepPrep preprocessing when BOLD input is present and passes backend eligibility checks. ALFF/fALFF are optional downstream metrics after BOLD preprocessing; they are not the primary BOLD preprocessing workflow and should not be described as performed by DeepPrep unless an implementation specifically adds that metric stage.

## Unsupported Sequences

When a recognized sequence is not supported for processing, surface this exact sentence:

`Current software does not support radiomics/processing for this sequence.`

Do not invent workaround workflows. Suggest upload correction or later feature support only when grounded in product state.
