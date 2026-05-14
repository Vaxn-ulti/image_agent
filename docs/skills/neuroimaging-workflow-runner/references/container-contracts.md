# Container Contracts

## Shared Validation

Validation should:

1. Check required input files.
2. Check Docker image availability, for example with `docker image inspect`.
3. Construct the exact tokenized command.
4. Return image availability, command string/list, and bind mounts.
5. For DWI/QSI GPU workflows, run only fast capability probes.
6. Mark validation complete when command resolves, image exists, and required capability checks pass.

Validation should not launch long-running processing.

## Mount Pattern

Use resolved absolute paths:

- BIDS/input: `/data:ro`
- Output: `/output`
- Work: `/work`
- FreeSurfer license: `/opt/freesurfer/license.txt:ro` when required.

## Workflow Images

Current image contracts:

- DeepPrep: `pbfslab/deepprep:25.1.0`
- QSIPrep: `pennlinc/qsiprep:latest`
- QSIRecon: `pennlinc/qsirecon:latest`

Pin images in implementation when reproducibility matters. If `latest` remains in MVP, surface it clearly in validation output.

`pennlinc/qsiprep:latest` exposes `eddy_cuda11.0` at `/app/.pixi/envs/qsiprep/bin/eddy_cuda11.0`. Detection uses `eddy_cuda*` glob to accept versioned binaries (`eddy_cuda11.0`, `eddy_cuda10.2`, etc.), not only an exact `eddy_cuda` name. If the image changes and no `eddy_cuda*` executable exists, QSIPrep validation must fail quickly and say a CUDA-enabled QSIPrep/FSL image is required.

## Commands

T1 DeepPrep:

```text
docker run --rm -v {bids}:/data:ro -v {output}:/output -v {work}:/work -v {fs_license}:/opt/freesurfer/license.txt:ro pbfslab/deepprep:25.1.0 /data /output participant --anat_only
```

BOLD DeepPrep:

```text
docker run --rm -v {bids}:/data:ro -v {output}:/output -v {work}:/work -v {fs_license}:/opt/freesurfer/license.txt:ro pbfslab/deepprep:25.1.0 /data /output participant
```

Use implementation-specific DeepPrep BOLD flags if the repository adds them; keep the product contract that BOLD preprocessing belongs to DeepPrep.

QSIPrep:

```text
docker run --rm --gpus all -v {bids}:/data:ro -v {output}:/output -v {work}:/work -v {fs_license}:/opt/freesurfer/license.txt:ro -v {eddy_cuda_config}:/eddy_cuda_config.json:ro pennlinc/qsiprep:latest /data /output participant --eddy-config /eddy_cuda_config.json
```

QSIPrep validation must confirm `eddy_cuda_config.json` exists, is mounted at `/eddy_cuda_config.json`, and contains `use_cuda: true`, `num_threads >= 2`, and `dont_peas: true`. Single-threaded eddy starves GPU GP estimation on multi-shell DWI (task 65 stall: 3.5h+ at 100% CPU). Do not silently fall back to `eddy_cpu`.

QSIPrep detection uses `eddy_cuda*` glob (not exact `eddy_cuda`) to find versioned binaries like `eddy_cuda11.0`. The backend bash wrapper symlinks `eddy_cuda` → `eddy_cuda11.0` and `eddy_cuda10.2` → `eddy_cuda11.0` before invoking qsiprep, so the QSIPrep process sees the expected `eddy_cuda` name.

QSIRecon:

```text
docker run --rm --gpus all -v {qsiprep_output}:/data:ro -v {output}:/output -v {work}:/work -v {fs_license}:/opt/freesurfer/license.txt:ro pennlinc/qsirecon:latest /data /output participant --recon-spec {recon_spec}
```

`--recon-spec` selects the reconstruction pipeline (e.g. `dipy`, `mrtrix`, `dsi_studio`, or a custom JSON spec path). Validation must fail fast when `--recon-spec` is missing, undefined, or references an unsupported pipeline.

QSIRecon has no confirmed CUDA-specific CLI switch in current documentation. Validation should record whether the GPU is visible inside the container, for example with `nvidia-smi` when available.

## DWI Runtime Capacity Contract

Real DWI processing is serialized per project backend with `data/projects/locks/dwi_qsiprep.lock`. This prevents multiple project-owned QSIPrep containers from consuming memory simultaneously while still allowing task 2 to queue and wait. The lock is part of the runtime contract and should be visible in task logs as `Waiting for workflow lock`, `Acquired workflow lock`, and `Released workflow lock`.

Default QSIPrep command resources are intentionally conservative for this host:

```text
--nthreads 4 --omp-nthreads 2 --mem 16000
```

Default QSIRecon resources are also conservative:

```text
--nprocs 4 --omp-nthreads 2 --mem 16000
```

These defaults may be overridden with `IMAGE_AGENT_DWI_QSIPREP_*` and `IMAGE_AGENT_DWI_QSIRECON_*` environment variables, but acceptance runs should document any override in the task log or review report.
