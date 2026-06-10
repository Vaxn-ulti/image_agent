# Container Contracts

## Contents

- Shared Validation
- Mount Pattern
- Workflow Images
- Commands
- DWI Runtime Capacity Contract

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
- QSIPrep toolbox / legacy QSIPrep: `pennlinc/qsiprep:latest`
- QSIRecon: `pennlinc/qsirecon:latest`

Pin images in implementation when reproducibility matters. If `latest` remains in MVP, surface it clearly in validation output.

`pennlinc/qsiprep:latest` exposes `eddy_cuda11.0` at `/app/.pixi/envs/qsiprep/bin/eddy_cuda11.0`. Detection uses `eddy_cuda*` glob to accept versioned binaries (`eddy_cuda11.0`, `eddy_cuda10.2`, etc.), not only an exact `eddy_cuda` name. If the image changes and no `eddy_cuda*` executable exists, QSIPrep validation must fail quickly and say a CUDA-enabled QSIPrep/FSL image is required.

Production `dwi_fast_gpu_dti` does not use that image as a full QSIPrep workflow. It uses host FSL at `/home/yyf/project/MCI_project/tools/fsl` for GPU `eddy_cuda` and FSL registration commands, and uses `pennlinc/qsiprep:latest` only to access MRtrix commands.

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

Production fast GPU DTI:

```text
python -m app.workflows.dwi_fast_dti run --bids {bids} --out {output} --work {work} --resources {resources} --fsl-dir /home/yyf/project/MCI_project/tools/fsl --mrtrix-image pennlinc/qsiprep:latest --max-runtime-sec 2100 --require-gpu-eddy
```

Runtime must validate host FSL commands, GPU visibility, and MRtrix toolbox commands. The production fast DTI path must not execute:

```text
qsiprep /data /out participant
qsirecon /data /out participant
```

Expected production steps are lightweight staging/QC, `dwi2mask` or fallback mask, host FSL `eddy_cuda`, MRtrix tensor fitting/metrics, MNI152 registration, atlas regional statistics, and provenance/QC output.

Known-good production evidence: task `107` on project 22 / series 38 completed in about 19 minutes 52 seconds (`runtime_sec=1156`), task `112` on project 23 / series 39 completed in about 18 minutes 2 seconds (`runtime_sec=1042`), and task `114` on mixed project 13 / series 24 completed with `runtime_sec=1021`. These runs used host FSL GPU `eddy_cuda`, MRtrix toolbox tensor metrics, conservative `flirt_normmi_dof6` MNI registration, native and MNI152 FA/MD/AD/RD maps, HarvardOxford regional TSVs, and `validation_only=false` summaries. Treat task `106` as the protected regression for invalid NaN FLIRT matrices.

QSIPrep:

```text
docker run --rm --gpus all -v {bids}:/data:ro -v {output}:/output -v {work}:/work -v {fs_license}:/opt/freesurfer/license.txt:ro -v {eddy_cuda_config}:/eddy_cuda_config.json:ro pennlinc/qsiprep:latest /data /output participant --eddy-config /eddy_cuda_config.json
```

QSIPrep validation must confirm `eddy_cuda_config.json` exists, is mounted at `/eddy_cuda_config.json`, and contains `use_cuda: true`, `num_threads >= 4`, `dont_peas: true`, `cnr_maps: true`, and `niter: 3` by default. Do not silently fall back to `eddy_cpu`. QSIPrep source forces CUDA eddy to 1 thread; verify CUDA usage by `eddy_cuda*` binary and logs/GPU visibility, not by requiring a specific eddy `--nthr` value at runtime. This QSIPrep version rejects `cnr_maps: false`, so speed tuning uses `dont_peas: true` and the configurable `IMAGE_AGENT_DWI_QSIPREP_EDDY_NITER` instead. The backend must infer `is_shelled` from b-values and set it false for q-space/many-b-value DWI.

QSIPrep detection uses `eddy_cuda*` glob (not exact `eddy_cuda`) to find versioned binaries like `eddy_cuda11.0`. The backend bash wrapper symlinks `eddy_cuda` → `eddy_cuda11.0` and `eddy_cuda10.2` → `eddy_cuda11.0` before invoking qsiprep, so the QSIPrep process sees the expected `eddy_cuda` name.

QSIRecon:

```text
docker run --rm --gpus all -v {qsiprep_output}:/data:ro -v {output}:/output -v {work}:/work -v {fs_license}:/opt/freesurfer/license.txt:ro pennlinc/qsirecon:latest /data /output participant --recon-spec {recon_spec}
```

`--recon-spec` selects the reconstruction pipeline. Official built-in values include QSIRecon workflow names such as `dipy_dki` and `mrtrix_multishell_msmt_noACT`; official custom workflow specs are YAML authoring references. Current Image Agent production is policy-limited to backend-approved profiles, not arbitrary user-supplied custom specs in production. Validation must fail fast when `--recon-spec` is missing, undefined, or references an unsupported pipeline.

QSIRecon has no confirmed CUDA-specific CLI switch in current documentation. Validation should record whether the GPU is visible inside the container, for example with `nvidia-smi` when available.

## DWI Runtime Capacity Contract

Legacy QSIPrep processing is serialized per project backend with `data/projects/locks/dwi_qsiprep.lock`. This prevents multiple project-owned QSIPrep containers from consuming memory simultaneously while still allowing task 2 to queue and wait. The lock is part of the legacy runtime contract and should be visible in task logs as `Waiting for workflow lock`, `Acquired workflow lock`, and `Released workflow lock`.

Production `dwi_fast_gpu_dti` has a separate 35 minute target and should be monitored by task logs and runner timeout/provenance. Do not route it into the legacy QSIPrep lock path unless code explicitly documents a resource conflict reason.

Default QSIPrep command resources are intentionally conservative for this host:

```text
--nthreads 8 --omp-nthreads 4 --mem 24000
```

Default QSIRecon resources follow the same user-approved resource profile:

```text
--nprocs 8 --omp-nthreads 4 --mem 24000
```

These defaults may be overridden with `IMAGE_AGENT_DWI_QSIPREP_*` and `IMAGE_AGENT_DWI_QSIRECON_*` environment variables, but acceptance runs should document any override in the task log or review report.
