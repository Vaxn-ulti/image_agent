---
name: image-agent-developer
description: Use when a coding agent is implementing, reviewing, debugging, or documenting the Image Agent FastAPI + React/Vite repository, including backend APIs, mixed ingest, BIDS-like conversion, workflow gating, OpenAI-style agent orchestration, DeepPrep T1/BOLD support, production dwi_fast_gpu_dti with host FSL GPU eddy and MRtrix toolbox mode, legacy QSIPrep/QSIRecon behavior, tests, skill maintenance, deployment logs, or repository handoffs. The built-in app chat agent behavior is covered by product code and prompts, not by this skill.
---

# Image Agent Developer

Continue Image Agent development without re-discovering product boundaries.

## Trigger Rules

Use this skill before editing backend APIs, workflow code, result contracts, agent orchestration, RAG plumbing, React/Vite frontend integration, desktop glue, tests, deployment scripts, or Image Agent documentation.

Use `image-agent-architect` first for contract or boundary design. Use `image-agent-workflow-runner` for workflow execution details. Use `image-agent-rag-curator` for knowledge-base ingestion. Use `image-agent-result-reviewer` for artifact/result acceptance.

## Operating Rules

1. Preserve deterministic backend contracts before changing UI or chat wording.
2. Keep modality detection deterministic; do not move classification into the LLM.
3. Support fixed production workflows `t1_deepprep`, `bold_deepprep` plus `bold_second_level`, and `dwi_fast_gpu_dti`.
4. Keep workflow responses aligned with the shared result contract in `references/contracts.md`.
5. Keep legacy QSIPrep and QSIRecon dependency order explicit; QSIRecon requires `--recon-spec`.
6. Add tests for new workflow eligibility, BIDS naming, and status transitions.
7. Keep production DWI behavior aligned with the lightweight toolbox strategy: host FSL GPU `eddy_cuda`, MRtrix tools from the QSIPrep image only as a toolbox, and no full QSIPrep/QSIRecon execution.
8. Acceptance requires real workflow processing, not validate-only. Production DWI has two passing real evidence tasks (`107`, project 22 / series 38; `112`, project 23 / series 39) proving host FSL at `/home/yyf/project/MCI_project/tools/fsl`, GPU `eddy_cuda`, MRtrix toolbox availability in `pennlinc/qsiprep:26.0.0`, real FA/MD/AD/RD outputs, MNI152 maps, atlas regional TSVs, and runtime under the 35 minute target.
9. BOLD downstream acceptance now has two passing real evidence tasks (`110`, project 14 / series 25; `111`, project 13 / series 23). `bold_second_level` must resolve completed DeepPrep MNI BOLD outputs, generate or use a matching MNI mask, compute ALFF/fALFF/ReHo/tSNR/RSFA plus 15-seed seed-to-ROI and DMN tables, and write `summary/bold_result_summary.json`.
10. Document behavior in `docs/workflows` when changing pipeline contracts.
11. Docker containers may outlive API restarts. Inspect mounts and task logs before assuming a container stopped. Never stop unrelated containers. Future containers are labeled with `image_agent.app=image_agent` plus `task_id`, `project_id`, `workflow_type`; existing task 65 is unlabeled and handled by the docker-wait watchdog.
12. Mount safety: writable mounts outside `PROJECTS_ROOT` are rejected. Read-only support mounts outside `PROJECTS_ROOT` (e.g., FreeSurfer license) are allowed only when at least one project mount under `PROJECTS_ROOT` exists.
13. The orphan recovery module (`apps/api/app/workflows/recovery.py`) can list/dry-run/recover labeled completed containers but never stops/kills containers and requires output files plus DB running/queued state.
14. When API port 8000 returns 404 for known task ids, verify `/health` app identity first; repeated 404/empty responses suggest port conflicts. Identify the port owner and stop only the conflicting non-image_agent process.
15. Scientific report display is part of the result contract: real T1/BOLD/DWI outputs must produce `reports/index.html`, `reports/report_manifest.json`, PNG report assets, and `outputs.reports` in `/tasks/{id}/result-summary`; generated report assets must be labeled as derived presentation, not container-native QC replacements.
16. Never commit or push patient data, logs, DB files, credentials, or medical images to GitHub.

## Reference Loading

- Read `references/repo-map.md` before editing code.
- Read `references/agent-roles.md` before splitting work across orchestrator, developer, review/test, or skill agents.
- Read `references/contracts.md` before changing APIs, workflow types, or task states.
- Read `references/implementation-guidance.md` before implementing new slices.
- Read `references/gpu-workflow-strategy.md` before changing production DWI, legacy QSIPrep/QSIRecon command construction, or validation.
- Read `references/testing-matrix.md` before handing work to a review/test agent or declaring validation complete.
- Read `references/skill-maintenance.md` after a failed run exposes missing or stale agent guidance.
- Read `references/operational-recovery.md` before restarting the API, troubleshooting port conflicts, or diagnosing task 404s.
- Read `references/examples-evals.md` before writing tests or review prompts.

## Output Shape

For implementation or review work, return:

- Current branch/status.
- Files changed.
- Behavior added or intentionally deferred.
- Commands run and results.
- Known risks and next test target.

For code-review style requests, lead with findings ordered by severity, include file/line references, and keep summaries secondary.

For handoffs to another coding agent, include the current objective slice, relevant contracts, verification evidence, and concrete next action.

## Eval Hints

Useful evals ask an agent to implement an API contract, debug a workflow/runtime issue, or maintain skills/RAG after production evidence changes. Passing answers preserve backend determinism, update tests before behavior changes, protect patient/secrets boundaries, keep work logs current, and avoid replacing production DWI with full QSIPrep/QSIRecon unless explicitly working on legacy paths.
