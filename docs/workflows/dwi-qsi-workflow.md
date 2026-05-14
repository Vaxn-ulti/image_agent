# DWI QSI Workflow

## Purpose

Run or validate diffusion preprocessing and reconstruction through QSIPrep and QSIRecon.

## Workflow Types

- `dwi_qsiprep`
- `dwi_qsiprep_validate`
- `dwi_qsirecon`
- `dwi_qsirecon_validate`
- `dwi_qsi_full`
- `dwi_qsi_full_validate`

## QSIPrep Eligibility

Required:

- DWI NIfTI.
- Matching `.bval`.
- Matching `.bvec`.
- Minimal BIDS-like DWI tree.
- QSIPrep Docker image for validate or run.

## QSIPrep BIDS-like Input

Required paths:

- `sub-01/dwi/sub-01_dwi.nii.gz`
- `sub-01/dwi/sub-01_dwi.bval`
- `sub-01/dwi/sub-01_dwi.bvec`
- `dataset_description.json`

Use symlinks where possible.

## QSIPrep Docker

Image:

`pennlinc/qsiprep:latest`

This image exposes `eddy_cuda11.0` at `/app/.pixi/envs/qsiprep/bin/eddy_cuda11.0`. Detection uses `eddy_cuda*` glob to accept versioned binaries (`eddy_cuda11.0`, `eddy_cuda10.2`, etc.), not only an exact `eddy_cuda` name. If the image changes and no `eddy_cuda*` exists, validation fails fast with a clear requirement for a CUDA-enabled QSIPrep/FSL image.

Command pattern:

```text
docker run --rm --gpus all -v {bids}:/data:ro -v {output}:/output -v {work}:/work -v {fs_license}:/opt/freesurfer/license.txt:ro -v {eddy_cuda_config}:/eddy_cuda_config.json:ro pennlinc/qsiprep:latest /data /output participant --eddy-config /eddy_cuda_config.json
```

`eddy_cuda_config.json` must contain `use_cuda: true`. Do not fall back to `eddy_cpu` for production DWI runs under the current strategy.

The backend wraps QSIPrep in a bash script that symlinks `eddy_cuda` → `eddy_cuda11.0` and `eddy_cuda10.2` → `eddy_cuda11.0` inside `/app/.pixi/envs/qsiprep/bin` before invoking qsiprep, so the QSIPrep process sees the expected binary names.

Real DWI tasks 61 and 62 are running with GPU/CUDA eddy.

## QSIRecon Eligibility

Required:

- Completed QSIPrep task id.
- QSIPrep output directory readable as QSIRecon input.
- Valid `--recon-spec` value (e.g. `dipy`, `mrtrix`, `dsi_studio`, or a custom JSON spec path).
- QSIRecon Docker image for validate or run.

Do not run QSIRecon directly on raw DWI.

## QSIRecon Docker

Image:

`pennlinc/qsirecon:latest`

Command pattern:

```text
docker run --rm --gpus all -v {qsiprep_output}:/data:ro -v {output}:/output -v {work}:/work -v {fs_license}:/opt/freesurfer/license.txt:ro pennlinc/qsirecon:latest /data /output participant --recon-spec {recon_spec}
```

`--recon-spec` is the required flag that selects which reconstruction pipeline(s) to run. Common values: `dipy`, `mrtrix`, `dsi_studio`, or a path to a custom JSON spec. Validation must fail fast when `--recon-spec` is missing, undefined, or references an unsupported pipeline.

No CUDA-specific QSIRecon CLI switch is currently documented. GPU exposure is via Docker `--gpus all`. Validation should record whether GPU is visible inside the container.

## Full Chain

`dwi_qsi_full` runs:

1. QSIPrep (with eddy_cuda* detection, `--eddy-config`, symlink wrapper).
2. QSIRecon (with `--recon-spec` and Docker `--gpus all`) only if QSIPrep completes.

If QSIPrep fails, skip QSIRecon and mark the chain failed with the QSIPrep failure reason.

`dwi_qsi_full` enforces the same per-step GPU safety checks as standalone `dwi_qsiprep` and `dwi_qsirecon`.

## Outputs

QSIPrep:

- Preprocessed DWI.
- Confounds.
- QC report.
- HTML report.

QSIRecon:

- FA/MD or other scalar maps.
- Tractography.
- Connectome.
- HTML report.

## Concrete Eval Cases

1. DWI with gradients validates QSIPrep CUDA command, config mount, and eddy_cuda* detection.
2. DWI missing `.bval` or `.bvec` is ineligible with a specific reason.
3. QSIRecon without completed QSIPrep is rejected.
4. QSIRecon without `--recon-spec` or with an unsupported spec value fails validation fast.
5. Full chain skips QSIRecon after QSIPrep failure.
6. Image exposing `eddy_cuda11.0` passes eddy_cuda* detection; image with no eddy_cuda* fails validation fast.
