---
name: image-agent-developer
description: Development guide for Claude coding agents working on the Image Agent FastAPI + React/Vite repository. Use when a Claude agent is implementing, reviewing, debugging backend APIs, mixed ingest, BIDS-like conversion, workflow gating, DeepPrep T1/BOLD support, QSIPrep eddy_cuda GPU behavior, QSIRecon --recon-spec and GPU visibility, tests, skill maintenance, or documentation in /home/yyf/project/image_agent. The built-in app chat agent (DeepSeek) is not covered by this skill.
---

# Image Agent Developer

Use this skill to continue development without re-discovering product boundaries.

## Development Rules

1. Preserve deterministic backend contracts before changing UI or chat wording.
2. Keep modality detection deterministic; do not move classification into the LLM.
3. Support DeepPrep for both T1w and fMRI/BOLD preprocessing.
4. Keep ALFF/fALFF as downstream metric work unless code explicitly implements it.
5. Keep QSIPrep and QSIRecon dependency order explicit; QSIRecon requires `--recon-spec`.
6. Add tests for new workflow eligibility, BIDS naming, and status transitions.
7. Keep DWI/QSI GPU behavior aligned with the current container strategy.
8. Acceptance requires real container processing, not validate-only. DWI uses `eddy_cuda*` pattern detection; `pennlinc/qsiprep:latest` exposes `eddy_cuda11.0` at `/app/.pixi/envs/qsiprep/bin/`. Backend creates symlinks `eddy_cuda` → `eddy_cuda11.0` and fails fast if no `eddy_cuda*` exists. Real DWI tasks 61/62 are running with GPU/CUDA eddy.
9. Document behavior in `docs/workflows` when changing pipeline contracts.
10. Docker containers may outlive API restarts. Inspect mounts and task logs before assuming a container stopped. Never stop unrelated containers. Future containers are labeled with `image_agent.app=image_agent` plus `task_id`, `project_id`, `workflow_type`; existing task 65 is unlabeled and handled by the docker-wait watchdog.
11. Mount safety: writable mounts outside `PROJECTS_ROOT` are rejected. Read-only support mounts outside `PROJECTS_ROOT` (e.g., FreeSurfer license) are allowed only when at least one project mount under `PROJECTS_ROOT` exists.
12. The orphan recovery module (`apps/api/app/workflows/recovery.py`) can list/dry-run/recover labeled completed containers but never stops/kills containers and requires output files plus DB running/queued state.
13. When API port 8000 returns 404 for known task ids, verify `/health` app identity first; repeated 404/empty responses suggest port conflicts. Identify the port owner and stop only the conflicting non-image_agent process.
14. Never commit or push patient data, logs, DB files, credentials, or medical images to GitHub.

## Reference Loading

- Read `references/repo-map.md` before editing code.
- Read `references/agent-roles.md` before splitting work across orchestrator, developer, review/test, or skill agents.
- Read `references/contracts.md` before changing APIs, workflow types, or task states.
- Read `references/implementation-guidance.md` before implementing new slices.
- Read `references/gpu-workflow-strategy.md` before changing DWI/QSIPrep/QSIRecon command construction or validation.
- Read `references/testing-matrix.md` before handing work to a review/test agent or declaring validation complete.
- Read `references/skill-maintenance.md` after a failed run exposes missing or stale agent guidance.
- Read `references/operational-recovery.md` before restarting the API, troubleshooting port conflicts, or diagnosing task 404s.
- Read `references/examples-evals.md` before writing tests or review prompts.

## Handoff Output

When handing work to another coding agent, include:

- Current branch/status.
- Files changed.
- Behavior added or intentionally deferred.
- Commands run and results.
- Known risks and next test target.
