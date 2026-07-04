# DWI/QSI GPU Strategy

## Contents

- Production DWI Lightweight Toolbox Policy
- Legacy QSIPrep/QSI Current State
- QSIPrep Policy
- QSIRecon Policy
- Controller Finding and Runtime Lessons

## Production DWI Lightweight Toolbox Policy

- `dwi_fast_gpu_dti` is the production DWI workflow.
- It is based on `/home/yyf/project/MCI_project/scripts/run_fast_gpu_dti_features.sh`, but the backend should own the steps rather than shelling to an opaque external script forever.
- Use host FSL from `/home/yyf/project/MCI_project/tools/fsl` for GPU `eddy_cuda`, `flirt`, `applywarp`, and related FSL utilities.
- Use the locked `pennlinc/qsiprep:26.0.0` image only as an MRtrix toolbox image for `dwi2mask`, `mrconvert`, `dwi2tensor`, `tensor2metric`, `mrstats`, and `mrcalc`.
- Keep execution images fixed for migration and acceptance evidence: production/default DWI toolbox `pennlinc/qsiprep:26.0.0`, legacy QSIRecon `pennlinc/qsirecon:26.0.0`, BOLD fMRIPrep `nipreps/fmriprep:25.2.5`, and BOLD XCP-D `pennlinc/xcp_d:26.0.2`. Strict acceptance rejects `:latest` or untagged images.
- Do not run full QSIPrep or full QSIRecon for production `dwi_fast_gpu_dti`.
- Require DWI NIfTI, `.bval`, `.bvec`, and JSON sidecar fields `PhaseEncodingDirection` and `TotalReadoutTime`.
- The runner should write FA/MD/AD/RD native DWI maps, MNI152 maps, QC/provenance, and atlas regional TSV tables.
- The runtime target is `2100` seconds / 35 minutes. If a real run exceeds this, record the exact step and log evidence before changing the workflow.

Validation for production DWI must verify:

- host FSL command availability under `/home/yyf/project/MCI_project/tools/fsl`;
- GPU visibility with `nvidia-smi`;
- MRtrix command availability inside the QSIPrep toolbox image;
- `full_qsiprep_run: false` and `full_qsirecon_run: false` in details/provenance where this helps prevent future confusion.

## Legacy QSIPrep/QSI Current State

- Historical DWI QSIPrep tasks `46` and `47` used `eddy_cpu`, ran too long, were stopped, and are treated as `failed`.
- Backend generates `eddy_cuda_config.json` for `dwi_qsiprep`, mounts it as `/eddy_cuda_config.json`, and passes `--eddy-config /eddy_cuda_config.json`.
- The generated JSON must set `use_cuda: true`, `num_threads >= 4`, `dont_peas: true`, `cnr_maps: true`, and `niter: 3` by default.
- Eddy `num_threads` defaults to `DWI_QSIPREP_OMP_NTHREADS` (4) with a floor of 2; override via `IMAGE_AGENT_EDDY_NUM_THREADS`.
- QSIPrep source (`qsiprep/workflows/dwi/fsl.py`) forces CUDA eddy to 1 thread. Single-threaded CUDA eddy is expected, not a failure.
- The `num_threads >= 4` floor in the config is a safety backstop for non-CUDA eddy or future QSIPrep versions that remove the override.
- The locked `pennlinc/qsiprep:26.0.0` image exposes `eddy_cuda11.0` at `/app/.pixi/envs/qsiprep/bin/eddy_cuda11.0` in the current acceptance profile. Detection uses `eddy_cuda*` glob to accept versioned binaries (`eddy_cuda11.0`, `eddy_cuda10.2`, etc.), not only an exact `eddy_cuda` name.
- Backend creates symlinks `eddy_cuda` -> `eddy_cuda11.0` and `eddy_cuda10.2` -> `eddy_cuda11.0` inside `/app/.pixi/envs/qsiprep/bin` via a bash wrapper script.
- QSIRecon documentation has no confirmed CUDA-only CLI switch. The current policy is to expose GPUs with Docker `--gpus all` and record whether the container can see them.
- `dwi_qsi_full` enforces the same GPU safety checks as standalone `dwi_qsiprep` and `dwi_qsirecon` (eddy_cuda* probe for QSIPrep, GPU visibility for QSIRecon).

## QSIPrep Policy

Use this command shape for GPU-enabled QSIPrep work:

```text
docker run --rm --gpus all -v {bids}:/data:ro -v {output}:/output -v {work}:/work -v {fs_license}:/opt/freesurfer/license.txt:ro -v {eddy_cuda_config}:/eddy_cuda_config.json:ro pennlinc/qsiprep:26.0.0 /data /output participant --eddy-config /eddy_cuda_config.json
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
docker run --rm --gpus all -v {qsiprep_output}:/data:ro -v {output}:/output -v {work}:/work -v {fs_license}:/opt/freesurfer/license.txt:ro pennlinc/qsirecon:26.0.0 /data /output participant --recon-spec {recon_spec}
```

`--recon-spec` selects the reconstruction pipeline. Validation must confirm a valid recon-spec value is provided and fail fast otherwise.

Current backend profile policy:

- `IMAGE_AGENT_QSIRECON_PROFILE=dki`
  Uses `--recon-spec dipy_dki --skip-odf-reports --notrack`
  This is the historical default and should remain the fallback for scalar-only reconstruction.

- `IMAGE_AGENT_QSIRECON_PROFILE=tractography`
  Uses `--recon-spec mrtrix_multishell_msmt_noACT`
  This is the first tractography-capable profile because it avoids T1-based ACT requirements and better matches the current project dependency chain.

Every `dwi_qsirecon` and `dwi_qsi_full` task should also save a legacy command snapshot to:

- `derivatives/<task_id>/knowledge_base/qsirecon/qsirecon_legacy_dipy_dki_command.json`

Validation must record:

- Completed QSIPrep task id and readable QSIPrep output path.
- QSIRecon image availability.
- Whether a GPU is visible inside the container, for example via `nvidia-smi` when present.
- The exact command and mounts, including the `--recon-spec` value.
- The active QSIRecon profile and whether it is tractography-capable.

Do not add undocumented QSIRecon CUDA CLI flags. If a future image or documentation provides one, update this reference and `docs/workflows/dwi-qsi-workflow.md` in the same change.

## 2026-05-15 Controller Finding: CUDA Eddy Forced Single-Thread

The locked `pennlinc/qsiprep:26.0.0` source (`qsiprep/workflows/dwi/fsl.py`) forces CUDA eddy to 1 thread:

```python
if eddy_args['use_cuda']:
    eddy_args['num_threads'] = 1
```

- Eddy `--nthr=1` is expected when CUDA is active. Do not treat it as a failure.
- Global QSIPrep resources (`--nthreads 8 --omp-nthreads 4 --mem 24000`) control non-eddy parallelism and are the correct defaults.
- Verify CUDA usage by `eddy_cuda*` binary presence, GPU-visible log lines, and Docker `--gpus all`. Do not assert a specific eddy `--nthr` value (>1) in CUDA runs.
- The `num_threads >= 4` floor in `eddy_cuda_config.json` remains as a backstop for non-CUDA eddy or future QSIPrep versions.
- Infer `is_shelled` from `.bval`. q-space/many-b-value data must use `is_shelled: false`; otherwise eddy receives `--data_is_shelled` and can spend hours in low-GPU-utilization correction.

## 2026-05-15 Long Eddy Runtime Lesson

Task 69 used the required `--nthreads 8 --omp-nthreads 4 --mem 24000` command and real `eddy_cuda10.2`, but a 129-volume DWI remained in eddy for about three hours with only low GPU utilization and no new output after the early PE translation file. An attempted `cnr_maps: false` optimization failed fast because this QSIPrep version requires `cnr_maps` to be present and true. The later task 76 showed the same long eddy behavior with `niter: 3`; bval inspection showed 16-17 rounded b-values, so the data is q-space/many-b-value rather than standard few-shell DWI. Future runs should keep CUDA, `dont_peas: true`, `repol: true`, and `cnr_maps: true`, default eddy `niter` to 3, and infer `is_shelled: false` for many-b-value data. Use `IMAGE_AGENT_DWI_QSIPREP_EDDY_NITER=5` when prioritizing default eddy convergence over speed.

## 2026-05-14 DWI Stall Lesson

Do not start multiple project-owned legacy QSIPrep real runs concurrently on this server. Tasks 61 and 62 stalled while six QSIPrep containers were active, swap was full, and task 61 had a non-fatal SynthSeg OOM crash. Future legacy QSIPrep development must preserve the QSIPrep workflow lock and reduced default resources unless a capacity check proves the host can safely run more. Production `dwi_fast_gpu_dti` should stay on the lightweight host-FSL/MRtrix-toolbox path unless code explicitly documents a resource conflict reason.

Implementation guardrails:

- QSIPrep defaults: `IMAGE_AGENT_DWI_QSIPREP_NTHREADS=8`, `IMAGE_AGENT_DWI_QSIPREP_OMP_NTHREADS=4`, `IMAGE_AGENT_DWI_QSIPREP_MEM_MB=24000`.
- QSIRecon defaults: `IMAGE_AGENT_DWI_QSIRECON_NPROCS=8`, `IMAGE_AGENT_DWI_QSIRECON_OMP_NTHREADS=4`, `IMAGE_AGENT_DWI_QSIRECON_MEM_MB=24000`.
- Real `dwi_qsiprep` and `dwi_qsi_full` runs must acquire `data/projects/locks/dwi_qsiprep.lock` before launching containers.
- QSIRecon still uses Docker `--gpus all`; no undocumented CUDA-specific QSIRecon CLI flag should be added.
- If a task log is stale while Docker is still alive, inspect mounts before stopping anything and never stop containers outside `/home/yyf/project/image_agent` without explicit approval.
