# Skill Maintenance

Update skills when execution or review exposes a repeatable failure point that another agent could avoid.

## Failure Update Flow

1. Capture the failing task id, command, image tag, logs, and observed status transition.
2. Classify the failure as code defect, container/runtime capability, data/input eligibility, documentation gap, or orchestration gap.
3. Update the narrowest skill reference that would have prevented the repeated mistake.
4. Keep `SKILL.md` concise; add only a pointer when a new reference is needed.
5. Update workflow docs when the product contract changed.
6. Re-run skill validation if available, then run a Markdown sanity check and the relevant test matrix.
7. Hand off with changed skill files, why the guidance changed, and which agent must act next.

## Current Recorded Failures

- DWI QSIPrep tasks `46` and `47` used `eddy_cpu`, ran too long, were stopped, and are marked `failed`.
- The production remediation is not to retry CPU eddy and not to run full QSIPrep. Use the lightweight `dwi_fast_gpu_dti` path with host FSL GPU `eddy_cuda`, MRtrix tools from the QSIPrep image as a toolbox, and the 35 minute runtime target.
- Legacy/experimental QSIPrep still requires CUDA eddy config plus a CUDA-enabled QSIPrep/FSL image when explicitly selected.
- The locked `pennlinc/qsiprep:1.0.2` image exposes `eddy_cuda11.0` at `/app/.pixi/envs/qsiprep/bin/` for legacy QSIPrep probing, but production fast DTI now probes host FSL under `/home/yyf/project/MCI_project/tools/fsl`.

### API Port 8000 Conflict (2026-05-14)

- Unrelated uvicorn service bound port 8000, causing image_agent watcher to return 404 from `/tasks/{id}` for valid task ids.
- The 404 came from the wrong application, not from missing data. Recovery required identifying the port owner, stopping only the conflicting non-image_agent process, and restarting the image_agent API from the repo root with `.env`.
- See `references/operational-recovery.md` for the step-by-step procedure.

### Container Lifecycle Assumption (2026-05-14)

- Real QSIPrep task 65 continued running in Docker during an API restart. Do not assume an API restart means containers stopped.
- Always inspect `docker ps`, container mounts, and task logs before declaring a task state.
- Watcher scripts (e.g. `scripts_watch_qsirecon_*.sh`) depend on the API and may also need restart after API recovery.

### Orphan Recovery and Labeling (2026-05-14)

- Containers that complete while the API is down leave DB task state stuck in `running`/`queued`. The recovery module (`apps/api/app/workflows/recovery.py`) reconciles these orphans via `list`/`dry-run`/`recover` commands.
- Recovery only acts on labeled, already-completed containers and requires output files plus valid DB state. It never stops or kills containers.
- Future containers are labeled with `image_agent.app=image_agent` plus `task_id`, `project_id`, `workflow_type`. Labels contain no patient data.
- Task 65 is unlabeled (started pre-patch) and handled by `scripts_monitor_task.sh`.

### Mount Safety Enforcement (2026-05-14)

- Writable mounts outside `PROJECTS_ROOT` are rejected. Read-only support mounts outside `PROJECTS_ROOT` (e.g., FreeSurfer license) require at least one project mount under `PROJECTS_ROOT`.

### Watcher /health Verification (2026-05-14)

- Watcher scripts now verify `/health` returns `app=image_agent` before trusting task data. Repeated 404/empty responses are treated as possible port conflicts, not immediate task loss.

## Acceptance Checklist

- Agent role boundaries are clear.
- Skill routing is machine-readable in `docs/skills/maintenance/routing-matrix.json`.
- Static skill maintenance audit passes: `python apps/api/scripts/audit_skill_maintenance.py --json`.
- DWI/QSI GPU policy names both command behavior and the eddy_cuda* versioned binary strategy.
- Review/test matrix includes backend, desktop, and container validation checks.
- Remaining blockers are assigned to the orchestrator rather than hidden in skill text.
- Final acceptance requires real container processing (not validate-only) with real data and registered outputs.
- Production DWI acceptance now has multiple known-good real tasks: task `107` on project 22 / series 38 completed in about 19 minutes 52 seconds (`runtime_sec=1156`), task `112` on project 23 / series 39 completed in about 18 minutes 2 seconds (`runtime_sec=1042`), and task `114` on mixed project 13 / series 24 completed with `runtime_sec=1021`. Keep this evidence in skills/planning with host FSL GPU `eddy_cuda`, MRtrix toolbox mode, native and MNI152 FA/MD/AD/RD maps, HarvardOxford regional DTI tables, and `validation_only=false`.
- Scientific report display acceptance requires the remote verifier script against real outputs, preferably by task id: `python apps/api/scripts/verify_scientific_reports.py --projects-root data/projects --task-ids 41 111 114 --require-modalities T1 BOLD DWI --require-container-native-qc --min-native-qc-images 1`. This keeps derived presentation report assets separate from container-native QC and prevents generated PNG reports from being treated as native evidence.
- QSIPrep commands include `--eddy-config /eddy_cuda_config.json` with `use_cuda: true`, `num_threads >= 2`, and `dont_peas: true`.
- QSIRecon commands include `--recon-spec`.
- Tests run with `apps/api/.venv/bin/pytest -q apps/api/tests` (currently 37 passed).
- Operational recovery procedures cover API port conflicts, container continuity, orphan recovery, and mount safety.
- Container labels (`image_agent.app=image_agent` + `task_id`, `project_id`, `workflow_type`) are documented and contain no patient data.
- Mount safety rejects writable mounts outside `PROJECTS_ROOT`; read-only support mounts outside `PROJECTS_ROOT` require a project mount.
- Watcher scripts verify `/health` app identity and treat repeated 404/empty responses as port conflicts.
- No patient data, logs, DB files, credentials, or medical images are staged for commit.
