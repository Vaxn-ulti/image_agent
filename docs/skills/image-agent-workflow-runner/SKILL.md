---
name: image-agent-workflow-runner
description: Use when validating, launching, monitoring, or summarizing Image Agent workflows, including workflow registry entries, preflight checks, container commands, task events, output registration, result summaries, security boundaries, or compatibility with the existing neuroimaging-workflow-runner skill.
---

# Image Agent Workflow Runner

Run Image Agent workflows through deterministic registry, preflight, execution, event, and result-summary contracts.

## Trigger Rules

Use this skill for workflow execution plans, validate-only behavior, container command review, task lifecycle events, output discovery, result summaries, runtime security, or handoff to an execution agent.

If deep legacy QSIPrep/QSIRecon command details are needed, also read `../neuroimaging-workflow-runner/SKILL.md`; do not replace or rename that existing skill.

## Operating Rules

1. Start from the workflow registry: workflow type, modality, required inputs, validation variant, runner, expected outputs, and compatibility aliases.
2. Run preflight before real execution: inputs, sidecars, resolved paths, Docker image/tool availability, GPU/runtime capability, output/work directories, and license/support mounts.
3. Keep validate-only side-effect-light: no long-running container launch and no fake real outputs.
4. Use task events to make state transitions auditable: queued, validation_started, running, progress/log, output_registered, completed, failed, cancelled.
5. Register outputs only after files exist. If metadata must be registered, write a real metadata JSON file first.
6. Result summaries must distinguish real execution from validation placeholders and expose frontend-safe artifact metadata.
7. Enforce mount and data safety: no writable mounts outside the project root, no secrets or patient data in logs, and no stopping unrelated containers.
8. Treat production DWI as `dwi_fast_gpu_dti`: host FSL GPU `eddy_cuda`, MRtrix toolbox mode, no full QSIPrep/QSIRecon run unless explicitly using legacy workflows.

## Reference Loading

- Read `references/registry-and-preflight.md` before adding or validating workflow registry entries.
- Read `references/ta<REDACTED_API_KEY>.md` before reporting events, registering outputs, or building summaries.
- Read `references/container-qc-artifacts.md` before designing report discovery or frontend visualization for container workflows.
- Read `references/security-and-containers.md` before reviewing mounts, Docker commands, logs, or recovery behavior.
- Read existing `../neuroimaging-workflow-runner/references/container-contracts.md` for detailed legacy container command contracts.
- Read existing `../neuroimaging-workflow-runner/references/output-discovery.md` for modality-specific output expectations.

## Output Shape

For workflow execution guidance, return:

1. Workflow type and registry match.
2. Preflight result: pass/fail plus exact blockers.
3. Execution mode: validate-only or real.
4. Container/tool command summary with safe paths.
5. Task events to emit or inspect.
6. Outputs/result-summary expected or discovered.
7. Container-native QC/HTML/image artifacts discovered or missing.
8. Security notes.

## Eval Hints

Good evals include missing JSON DWI sidecars, unavailable Docker images, stale validate placeholders, unlabeled containers, unsafe mounts, and frontend artifact summary mismatches. Passing answers fail fast, avoid fake outputs, and preserve the existing `neuroimaging-workflow-runner` compatibility path.

