---
name: neuroimaging-workflow-runner
description: Use when an agent must validate, run, monitor, or report Image Agent neuroimaging workflows, including BIDS-like inputs, Docker bind mounts, DeepPrep T1/BOLD, production dwi_fast_gpu_dti, legacy QSIPrep/QSIRecon, task logs, output registration, or workflow status on the remote runtime.
---

# Neuroimaging Workflow Runner

Use this skill for container task execution and validate-only workflow operations.

## Trigger Rules

Use this skill when the task involves:

- building BIDS-like inputs for T1, BOLD, or DWI workflows;
- validating Docker images, bind mounts, FreeSurfer license access, or runtime preflight checks;
- running or dry-running DeepPrep, production `dwi_fast_gpu_dti`, legacy QSIPrep, QSIRecon, or QSI full-chain workflows;
- reading task logs, checking task states, registering outputs, or explaining workflow status;
- reviewing whether a workflow command is safe to execute on the remote runtime.

Do not use this skill for general user-facing chat wording without workflow execution details; use `image-agent-operator` for that surface.

## Operating Rules

1. Resolve all host paths to absolute paths before Docker bind mounts.
2. Build minimal BIDS-like inputs using symlinks where possible; do not copy raw imaging data unnecessarily.
3. Run DeepPrep for T1w and fMRI/BOLD preprocessing.
4. Use `dwi_fast_gpu_dti` as the production DWI path based on the fast GPU DTI script; require DWI NIfTI, `.bval`, `.bvec`, and JSON `PhaseEncodingDirection`/`TotalReadoutTime`; run host FSL GPU `eddy_cuda` and MRtrix toolbox commands, not full QSIPrep/QSIRecon; treat QSIPrep/QSIRecon/QSI full as legacy or experimental unless explicitly selected.
5. Validate Docker image, bind mounts, inputs, and command before real execution.
6. For QSIPrep, require CUDA eddy configuration and fail fast when the image lacks `eddy_cuda*`. Detection uses `eddy_cuda*` glob to accept versioned binaries like `eddy_cuda11.0` exposed at `/app/.pixi/envs/qsiprep/bin/`.
7. For QSIRecon, require `--recon-spec` with a valid pipeline spec; fail fast when missing or unsupported. The default profile is scalar-only `dipy_dki`, while `IMAGE_AGENT_QSIRECON_PROFILE=tractography` switches to the tractography-capable built-in workflow `mrtrix_multishell_msmt_noACT`. Use Docker GPU exposure and record container GPU visibility; do not invent undocumented CUDA CLI flags.
8. Keep validation side-effect-light: no long-running container launch.
9. Register outputs only after verifying files exist.
10. For production DWI, expect FA, MD, AD, RD, MNI152 maps, and atlas regional DTI tables within the 35 minute target; distinguish validate placeholders from real output summaries. Current real-run evidence includes task `107` on project 22 / series 38 with `runtime_sec=1156`, task `112` on project 23 / series 39 with `runtime_sec=1042`, and task `114` on mixed project 13 / series 24 with `runtime_sec=1021`; each produced real native/MNI152 DTI maps, HarvardOxford regional tables, and `validation_only=false` summaries.

## Reference Loading

- Read `references/container-contracts.md` before building Docker commands.
- Read `references/bids-inputs.md` before constructing BIDS-like trees.
- Read `references/output-discovery.md` before registering outputs.
- Read `references/examples-evals.md` before testing workflow execution behavior.
- Check `docs/knowledge-base/qsirecon/README.md` in the repo when choosing or explaining QSIRecon built-in workflows.

## Output Shape

When reporting workflow-runner work, include:

- workflow type and mode: validate-only, real run, recovery, or status review;
- required inputs checked and any missing blockers;
- container image, host tool, and bind-mount checks, with sensitive values redacted;
- task event outcome: queued, validation_started, running, output_registered, completed, failed, or skipped;
- registered outputs or expected output families, distinguishing validate placeholders from real outputs;
- next action when blocked.

Task logs must contain enough detail to reproduce command construction, mounted paths, progress milestones, failure reason, and discovered outputs. Do not include secrets, license file contents, patient identifiers, raw image contents, sudo passwords, API keys, or bearer tokens.

## Eval Hints

Good evals include:

- normal path: validate or run an eligible workflow with complete inputs and expected output registration;
- missing info: missing image, missing license, missing DWI JSON sidecar, missing gradients, or absent completed QSIPrep dependency;
- risk conflict: unsafe writable mounts, unrelated container cleanup, stale QSI docs conflicting with production fast DTI, or user pressure to fabricate QC/output evidence.

Passing behavior should preserve backend truth, keep production DWI as `dwi_fast_gpu_dti`, use container-native QC/result artifacts, and avoid launching long GPU work from a validate-only plan.
