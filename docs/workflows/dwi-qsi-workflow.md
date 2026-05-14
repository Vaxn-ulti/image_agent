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

`eddy_cuda_config.json` must contain `use_cuda: true`, `num_threads >= 4`, `dont_peas: true`, and `cnr_maps: false`. `dont_peas` skips post-eddy alignment QC estimation — this does not affect core eddy correction quality and is a well-established production speed optimization. `cnr_maps: false` disables non-essential CNR map generation while preserving corrected DWI and motion/eddy outputs for QSIRecon. QSIPrep source forces CUDA eddy to 1 thread regardless of the config `num_threads`; the config floor serves as a safety backstop should a future image change this behavior.

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

## 2026-05-14 Task 65 Stall: Eddy Single-Threaded GP Estimation

Task 65 (129 bvals, ~87 MB DWI) ran eddy_cuda10.2 for >3.5 hours at 100% CPU with only small eddy output files and no workdir updates after 19:35 CST. Later source inspection showed QSIPrep forces CUDA eddy to one thread internally, so `num_threads` is only a backstop for non-CUDA eddy or future images.

### Eddy Threading Rule

- `_write_qsiprep_eddy_cuda_config()` sets `num_threads` from `IMAGE_AGENT_EDDY_NUM_THREADS` env var, defaulting to `DWI_QSIPREP_OMP_NTHREADS` (4).
- Floor of 2 enforced: `DWI_QSIPREP_EDDY_NUM_THREADS = max(2, ...)`.
- `dont_peas: true` skips post-eddy alignment QC estimation for speed. This does not affect core eddy correction quality.
- `cnr_maps: false` skips non-essential CNR map generation after task 69 repeated the long eddy runtime pattern with real CUDA eddy.
- Override: `IMAGE_AGENT_EDDY_NUM_THREADS=4` for larger multi-shell datasets.
- Do not set `num_threads: 1` in any eddy config unless a documented override protocol justifies it for a specific single-shell dataset.

### Verification

- Existing test asserts `num_threads >= 4` and `dont_peas: true`.
- Existing test asserts `cnr_maps: false`.
- Env-override and floor-enforcement tests in `apps/api/tests/test_api_flow.py`.

## 2026-05-15 Controller Finding: CUDA Eddy Forced Single-Thread

- `pennlinc/qsiprep:latest` source (`qsiprep/workflows/dwi/fsl.py`) forces CUDA eddy to 1 thread:
  ```python
  if eddy_args['use_cuda']:
      eddy_args['num_threads'] = 1
  ```
- Eddy `--nthr=1` is expected when CUDA is active; do not treat it as a failure.
- Global QSIPrep resources (`--nthreads 8 --omp-nthreads 4 --mem 24000`) control non-eddy parallelism and are the correct defaults.
- Verify CUDA usage by `eddy_cuda*` binary presence, GPU-visible log lines, and Docker `--gpus all`. Do not assert a specific eddy `--nthr` value (>1) in CUDA runs.
- The `num_threads >= 4` floor in `eddy_cuda_config.json` is a backstop for non-CUDA eddy or future QSIPrep versions that remove the override.

## 2026-05-14 Recovery Policy: DWI Memory Pressure

Real QSIPrep tasks 61 and 62 stalled under memory pressure while six QSIPrep containers were active on a 91 GiB RAM host. Evidence included stale task logs, full swap, low GPU utilization, and a SynthSeg `mri_synthseg --cpu` process killed by the OS. The project-owned task containers were mapped and stopped; unrelated user containers were not touched.

Current backend policy for real DWI runs:

- Use Docker `--gpus all` and require `eddy_cuda*` inside the QSIPrep image.
- Default QSIPrep resources are `--nthreads 8 --omp-nthreads 4 --mem 24000` unless overridden by environment variables.
- Serialize project-owned real `dwi_qsiprep` and `dwi_qsi_full` runs through `data/projects/locks/dwi_qsiprep.lock`.
- Allow queued DWI tasks to wait on the lock instead of launching concurrent QSIPrep containers.
- Treat validation-only success as insufficient for acceptance.

Current recovery run:

- Task 65 reruns series 24 with the reduced resource profile and CUDA eddy.
- Task 66 reruns series 27 and waits on the DWI workflow lock until task 65 releases it.
- Watcher `scripts_watch_qsirecon_65_66.sh` submits QSIRecon only after a real QSIPrep task completes.

## Container Continuity Across API Restarts

Docker containers launched by image_agent are independent of the API process. If the API is restarted, crashed, or blocked by a port conflict, running QSIPrep/QSIRecon containers continue in Docker.

### Container Labels

Future workflow containers (task 66+, QSIRecon, and all new runs after API restart) are labeled with:

- `image_agent.app=image_agent`
- `image_agent.task_id=<task_id>`
- `image_agent.project_id=<project_id>`
- `image_agent.workflow_type=<workflow_type>`

Labels contain no patient data. Use `GET /admin/containers` (read-only, label-filtered) or `docker ps --filter "label=image_agent.app=image_agent"` to list image_agent-owned containers.

Task 65 (series 24 QSIPrep) is unlabeled because it started before the labeling patch. It remains handled by `scripts_monitor_task.sh`. Labels take effect for task 66 and all subsequent runs.

### Orphan Recovery

`apps/api/app/workflows/recovery.py` can reconcile labeled completed orphan containers after an API restart. It supports `list`, `dry-run`, and `recover` commands. The module never stops or kills containers, requires output files to exist, and only acts on containers whose DB task is in `running` or `queued` state. Unlabeled containers (task 65) are invisible to it.

### Mount Safety

- Writable mounts outside `PROJECTS_ROOT` are rejected at launch.
- Read-only support mounts outside `PROJECTS_ROOT` (e.g., FreeSurfer license) are allowed only when at least one project mount under `PROJECTS_ROOT` exists.

### Recovery Steps

1. Verify `/health` returns `app=image_agent`. Repeated 404/empty responses suggest a port conflict, not task loss.
2. Check `docker ps --filter "label=image_agent.app=image_agent"` for labeled containers; use `docker ps` for unlabeled containers (task 65).
3. Inspect container mounts to confirm which task/series a container belongs to.
4. After API recovery, reconcile task state by checking both the task output directory and Docker container status. Use the recovery module for labeled orphans.
5. Restart any watcher scripts that depend on the API (e.g. `scripts_watch_qsirecon_*.sh`).
6. Never stop unrelated containers during recovery.
