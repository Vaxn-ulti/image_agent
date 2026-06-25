# Concrete Examples and Evals

## Contents

- Runner Example 1: Validate BOLD DeepPrep
- Runner Example 2: Run QSI Full
- Runner Example 2b: Run Production Fast GPU DTI
- Runner Example 2c: Production Fast GPU DTI Missing JSON
- Runner Example 3: QSIPrep Image Missing CUDA Eddy
- Runner Example 4: QSIRecon Missing Recon Spec
- Runner Example 5: Missing License
- Eval Checklist

## Runner Example 1: Validate BOLD DeepPrep

Inputs:

- BOLD NIfTI exists.
- BIDS-like func path can be constructed.
- DeepPrep image is present.

Expected:

- Command includes BIDS bind, output bind, work bind, and license bind.
- Command targets DeepPrep.
- No container is launched.
- Validation task completes with command output.

## Runner Example 2: Run QSI Full

Inputs:

- DWI NIfTI, `.bval`, and `.bvec`.
- QSIPrep CUDA config can be generated.
- Valid `--recon-spec` value for QSIRecon.

Expected:

- QSIPrep runs first.
- QSIPrep command includes `--gpus all` and `--eddy-config /eddy_cuda_config.json`.
- QSIRecon starts only after QSIPrep completes, with `--recon-spec`.
- If QSIPrep fails, QSIRecon is skipped and failure is logged.

## Runner Example 2b: Run Production Fast GPU DTI

Inputs:

- DWI NIfTI, `.bval`, `.bvec`, and JSON sidecar.
- JSON sidecar contains `PhaseEncodingDirection` and `TotalReadoutTime`.
- Host FSL exists at `<REMOTE_HOME>/project/MCI_project/tools/fsl` and exposes GPU `eddy_cuda`.
- `pennlinc/qsiprep:26.0.0` exposes MRtrix toolbox commands.

Expected:

- Backend stages `sub-01_dwi.nii.gz`, `.bval`, `.bvec`, and `.json`.
- Command derives `/work/acqparams.txt` and `/work/index.txt` from JSON/b-values.
- Command runs MRtrix `dwi2mask` or fallback mask, host FSL GPU `eddy_cuda`, MRtrix `dwi2tensor`, MRtrix `tensor2metric`, FSL MNI registration, and atlas statistics.
- Command does not run full `qsiprep /data /out participant` or full QSIRecon.
- Runtime/provenance records the `2100` second target.
- Real result summary is written only after FA/MD/AD/RD native maps, MNI152 maps, and regional TSV tables exist.

## Runner Example 2c: Production Fast GPU DTI Missing JSON

Inputs:

- DWI NIfTI, `.bval`, and `.bvec`.
- JSON sidecar is absent or lacks `PhaseEncodingDirection`/`TotalReadoutTime`.

Expected:

- API validation rejects `dwi_fast_gpu_dti` and `dwi_fast_gpu_dti_validate`.
- Error names the JSON sidecar metadata requirement.
- Runner does not fabricate `acqparams.txt` or launch a container.

## Runner Example 3: QSIPrep Image Missing CUDA Eddy

Inputs:

- DWI NIfTI, `.bval`, and `.bvec`.
- Image is `pennlinc/qsiprep:26.0.0` (or another QSIPrep image).
- Container probe finds no `eddy_cuda*` executable (neither `eddy_cuda`, `eddy_cuda11.0`, nor any versioned binary).

Expected:

- Validation fails quickly.
- Failure says a CUDA-enabled QSIPrep/FSL image is required.
- No long-running QSIPrep task is launched.

Contrast: when the image exposes `eddy_cuda11.0` at `/app/.pixi/envs/qsiprep/bin/`, the `eddy_cuda*` glob matches it, validation passes, and the backend bash wrapper symlinks `eddy_cuda` → `eddy_cuda11.0` for QSIPrep compatibility.

## Runner Example 4: QSIRecon Missing Recon Spec

Inputs:

- Completed QSIPrep task.
- QSIRecon image is present.
- No `--recon-spec` or unsupported spec value.

Expected:

- Validation fails fast.
- Failure names missing or unsupported `--recon-spec`.
- No QSIRecon task is launched.

## Runner Example 5: Missing License

Inputs:

- Eligible T1 or BOLD series.
- Missing FreeSurfer license path.

Expected:

- Validation fails before launch.
- Error names missing license bind without exposing license contents.

## Eval Checklist

- Absolute host paths are used.
- BIDS-like files are symlinks or deterministic references to raw/converted data.
- BOLD uses DeepPrep preprocessing.
- ALFF/fALFF are not registered unless produced.
- `bold_second_level` is single-subject downstream metrics after completed DeepPrep, not group-level analysis.
- Production DWI fast GPU DTI stages JSON sidecar metadata and derives acquisition parameters from it.
- Production DWI fast GPU DTI uses host FSL GPU eddy and MRtrix toolbox mode, not full QSIPrep/QSIRecon.
- Validate placeholder summaries and real output summaries are distinguishable in provenance.
- QSIPrep validation uses eddy_cuda* glob, requires CUDA eddy config, and does not fall back to CPU eddy.
- QSIRecon command includes `--recon-spec` with a valid spec value.
- QSIRecon validation records GPU visibility and avoids undocumented CUDA flags.
- Logs contain command construction and failure context.

