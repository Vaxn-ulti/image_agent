---
name: neuroimaging-workflow-runner
description: Execute or validate Image Agent neuroimaging container workflows safely. Use when an agent must build BIDS-like inputs, validate Docker images and bind mounts, run or dry-run DeepPrep T1/BOLD preprocessing, run GPU-oriented QSIPrep preprocessing with eddy_cuda, run QSIRecon reconstruction with --recon-spec and Docker GPU exposure, inspect logs, register outputs, or report workflow status for tasks in /home/yyf/project/image_agent.
---

# Neuroimaging Workflow Runner

Use this skill for container task execution and validate-only workflow operations.

## Execution Rules

1. Resolve all host paths to absolute paths before Docker bind mounts.
2. Build minimal BIDS-like inputs using symlinks where possible; do not copy raw imaging data unnecessarily.
3. Run DeepPrep for T1w and fMRI/BOLD preprocessing.
4. Run QSIPrep before QSIRecon; never feed raw DWI directly to QSIRecon.
5. Validate Docker image, bind mounts, inputs, and command before real execution.
6. For QSIPrep, require CUDA eddy configuration and fail fast when the image lacks `eddy_cuda*`. Detection uses `eddy_cuda*` glob to accept versioned binaries like `eddy_cuda11.0` exposed at `/app/.pixi/envs/qsiprep/bin/`.
7. For QSIRecon, require `--recon-spec` with a valid pipeline spec; fail fast when missing or unsupported. Use Docker GPU exposure and record container GPU visibility; do not invent undocumented CUDA CLI flags.
8. Keep validation side-effect-light: no long-running container launch.
9. Register outputs only after verifying files exist.

## Reference Loading

- Read `references/container-contracts.md` before building Docker commands.
- Read `references/bids-inputs.md` before constructing BIDS-like trees.
- Read `references/output-discovery.md` before registering outputs.
- Read `references/examples-evals.md` before testing workflow execution behavior.

## Status Reporting

Write task logs with enough detail to reproduce command construction, mounted paths, progress milestones, failure reason, and discovered outputs. Do not include secrets or license file contents.
