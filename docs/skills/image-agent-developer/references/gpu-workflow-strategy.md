# DWI/QSI GPU Strategy

## Current State

- Historical DWI QSIPrep tasks `46` and `47` used `eddy_cpu`, ran too long, were stopped, and are treated as `failed`.
- Backend generates `eddy_cuda_config.json` for `dwi_qsiprep`, mounts it as `/eddy_cuda_config.json`, and passes `--eddy-config /eddy_cuda_config.json`.
- The generated JSON must set `use_cuda: true`, `num_threads >= 4`, and `dont_peas: true`.
- Eddy `num_threads` defaults to `DWI_QSIPREP_OMP_NTHREADS` (4) with a floor of 2; override via `IMAGE_AGENT_EDDY_NUM_THREADS`.
- QSIPrep source (`qsiprep/workflows/dwi/fsl.py`) forces CUDA eddy to 1 thread. Single-threaded CUDA eddy is expected, not a failure.
- The `num_threads >= 4` floor in the config is a safety backstop for non-CUDA eddy or future QSIPrep versions that remove the override.
- `pennlinc/qsiprep:latest` exposes `eddy_cuda11.0` at `/app/.pixi/envs/qsiprep/bin/eddy_cuda11.0`. Detection uses `eddy_cuda*` glob to accept versioned binaries (`eddy_cuda11.0`, `eddy_cuda10.2`, etc.), not only an exact `eddy_cuda` name.
- Real DWI tasks 61 and 62 are running with GPU/CUDA eddy.
- Backend creates symlinks `eddy_cuda` → `eddy_cuda11.0` and `eddy_cuda10.2` → `eddy_cuda11.0` inside `/app/.pixi/envs/qsiprep/bin` via a bash wrapper script.
- QSIRecon documentation has no confirmed CUDA-only CLI switch. The current policy is to expose GPUs with Docker `--gpus all` and record whether the container can see them.
- `dwi_qsi_full` enforces the same GPU safety checks as standalone `dwi_qsiprep` and `dwi_qsirecon` (eddy_cuda* probe for QSIPrep, GPU visibility for QSIRecon).

## QSIPrep Policy

Use this command shape for GPU-enabled QSIPrep work:

```text
docker run --rm --gpus all -v {bids}:/data:ro -v {output}:/output -v {work}:/work -v {fs_license}:/opt/freesurfer/license.txt:ro -v {eddy_cuda_config}:/eddy_cuda_config.json:ro pennlinc/qsiprep:latest /data /output participant --eddy-config /eddy_cuda_config.json
```

Validation must:

- Check BIDS DWI, `.bval`, `.bvec`, license, output, and work mounts.
- Confirm the config file exists and contains `use_cuda: true` and `dont_peas: true`.
- Inspect image availability.
- Run a fast capability probe using `eddy_cuda*` glob across known QSIPrep/FSL paths (not exact `eddy_cuda`).
- Fail fast if no `eddy_cuda*` executable is found, naming the required CUDA-enabled QSIPrep/FSL image.
- Never fall back to `eddy_cpu` for production DWI runs under the current strategy.
- Verify CUDA eddy usage by `eddy_cuda*` binary presence and logs/GPU visibility, not by expecting a specific eddy `--nthr` value at runtime.

## QSIRecon Policy

Use Docker GPU exposure:

```text
docker run --rm --gpus all -v {qsiprep_output}:/data:ro -v {output}:/output -v {work}:/work -v {fs_license}:/opt/freesurfer/license.txt:ro pennlinc/qsirecon:latest /data /output participant --recon-spec {recon_spec}
```

`--recon-spec` selects the reconstruction pipeline. Validation must confirm a valid recon-spec value is provided and fail fast otherwise.

Validation must record:

- Completed QSIPrep task id and readable QSIPrep output path.
- QSIRecon image availability.
- Whether a GPU is visible inside the container, for example via `nvidia-smi` when present.
- The exact command and mounts, including the `--recon-spec` value.

Do not add undocumented QSIRecon CUDA CLI flags. If a future image or documentation provides one, update this reference and `docs/workflows/dwi-qsi-workflow.md` in the same change.

## 2026-05-15 Controller Finding: CUDA Eddy Forced Single-Thread

`pennlinc/qsiprep:latest` source (`qsiprep/workflows/dwi/fsl.py`) forces CUDA eddy to 1 thread:

```python
if eddy_args['use_cuda']:
    eddy_args['num_threads'] = 1
```

- Eddy `--nthr=1` is expected when CUDA is active. Do not treat it as a failure.
- Global QSIPrep resources (`--nthreads 8 --omp-nthreads 4 --mem 24000`) control non-eddy parallelism and are the correct defaults.
- Verify CUDA usage by `eddy_cuda*` binary presence, GPU-visible log lines, and Docker `--gpus all`. Do not assert a specific eddy `--nthr` value (>1) in CUDA runs.
- The `num_threads >= 4` floor in `eddy_cuda_config.json` remains as a backstop for non-CUDA eddy or future QSIPrep versions.

## 2026-05-14 DWI Stall Lesson

Do not start multiple project-owned QSIPrep real runs concurrently on this server. Tasks 61 and 62 stalled while six QSIPrep containers were active, swap was full, and task 61 had a non-fatal SynthSeg OOM crash. Future development must preserve the DWI workflow lock and reduced default resources unless a capacity check proves the host can safely run more.

Implementation guardrails:

- QSIPrep defaults: `IMAGE_AGENT_DWI_QSIPREP_NTHREADS=4`, `IMAGE_AGENT_DWI_QSIPREP_OMP_NTHREADS=2`, `IMAGE_AGENT_DWI_QSIPREP_MEM_MB=24000`.
- QSIRecon defaults: `IMAGE_AGENT_DWI_QSIRECON_NPROCS=4`, `IMAGE_AGENT_DWI_QSIRECON_OMP_NTHREADS=2`, `IMAGE_AGENT_DWI_QSIRECON_MEM_MB=24000`.
- Real `dwi_qsiprep` and `dwi_qsi_full` runs must acquire `data/projects/locks/dwi_qsiprep.lock` before launching containers.
- QSIRecon still uses Docker `--gpus all`; no undocumented CUDA-specific QSIRecon CLI flag should be added.
- If a task log is stale while Docker is still alive, inspect mounts before stopping anything and never stop containers outside `/home/yyf/project/image_agent` without explicit approval.
