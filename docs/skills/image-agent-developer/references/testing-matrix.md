# Testing Matrix

Run the smallest matrix that covers the touched surface. Record command output in handoff notes.

## Test Command

Always use the venv pytest from the repo root:

```text
apps/api/.venv/bin/pytest -q apps/api/tests
```

Do not run repo-root `pytest` or `cd apps/api && pytest`.

## Baseline

- `apps/api/.venv/bin/pytest -q apps/api/tests`
- `cd apps/desktop && npm run build`

Current known baseline:

- `apps/api pytest`: 12+ passed (check `test_api_flow.py` for latest count).
- `apps/desktop npm run build`: passed.

## DWI/QSI GPU Validation

- `dwi_qsiprep_validate` with DWI plus `.bval`/`.bvec` generates and mounts `eddy_cuda_config.json`.
- Config JSON contains `use_cuda: true`.
- QSIPrep command includes `--gpus all` and `--eddy-config /eddy_cuda_config.json`.
- Detection uses `eddy_cuda*` glob (accepts `eddy_cuda11.0`, `eddy_cuda10.2`, etc.); passes when `pennlinc/qsiprep:latest` exposes `eddy_cuda11.0` at `/app/.pixi/envs/qsiprep/bin/`.
- Backend writes a bash wrapper that symlinks `eddy_cuda` → `eddy_cuda11.0` and `eddy_cuda10.2` → `eddy_cuda11.0` before calling qsiprep.
- With an image missing all `eddy_cuda*` executables, validation fails fast with a clear GPU image requirement.
- `dwi_qsirecon_validate` requires completed QSIPrep output and records whether GPU is visible in the container.
- `dwi_qsirecon` command includes `--recon-spec` with a valid spec value; validation fails fast when `--recon-spec` is missing or unsupported.
- `dwi_qsi_full_validate` enforces the same eddy_cuda* GPU safety check as standalone `dwi_qsiprep_validate`.

## Real Acceptance

Validate-only is not sufficient for acceptance. Real acceptance requires:
- Real container processing with actual data packages.
- T1 DeepPrep real processing with registered outputs.
- BOLD DeepPrep real processing with registered outputs.
- DWI QSIPrep real processing with CUDA eddy (`--gpus all`, `--eddy-config`, `eddy_cuda*` detected, symlinks created).
- QSIRecon real processing after completed QSIPrep using Docker `--gpus all` with QSIPrep derivatives as input.
- Mixed-sample matrix: upload packages combining T1, BOLD, DWI (with gradients) in a single project.
- Unsupported sequence blocking verified with real inputs.
- Multiple sample combinations (different subjects/packages) tested.

## Contract Regression

- DWI without `.bval` or `.bvec` is ineligible with a specific reason.
- QSIRecon without a completed QSIPrep task is rejected.
- Failed/cancelled tasks remain visible through task status, logs, and outputs endpoints.
- Chat/operator responses do not recommend running CPU eddy for production DWI.

## Review/Test Acceptance

Accept a change only when:

- Focused tests for changed behavior pass.
- Baseline tests above pass or failures are unrelated and documented.
- Container validation distinguishes code defects from missing CUDA-enabled images.
- Handoff names remaining infrastructure blockers.

Final real acceptance adds:

- Real container processing completed and outputs registered.
- GPU used where supported (Docker `--gpus all` for QSIPrep and QSIRecon).
- Acceptance matrix covers T1, BOLD, DWI, QSIRecon, mixed packages, unsupported sequences, and multiple sample combinations with real data.
