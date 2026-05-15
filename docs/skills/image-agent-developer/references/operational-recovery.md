# Operational Recovery

## API Port 8000 Conflict

Port 8000 is the image_agent API default. An unrelated uvicorn service can bind it first, causing the image_agent watcher to return HTTP 404 from `/tasks/{id}` for task ids that exist in the image_agent database. The 404 comes from the wrong application serving the request, not from missing data.

### Detection

- `curl http://localhost:8000/tasks/{active_id}` returns 404 when the task is known to exist.
- `curl http://localhost:8000/health` returns an unexpected response or 404.
- The image_agent watcher or desktop app shows stale/missing task status.

### Recovery

1. Identify the process on port 8000:
   ```text
   ss -tlnp 'sport = :8000'
   ```
   or
   ```text
   lsof -i :8000
   ```

2. If the process is not the image_agent API, note its command and working directory. Stop only the conflicting non-image_agent process:
   ```text
   kill <pid>
   ```
   Never stop image_agent-owned containers or unrelated user services.

3. Restart the image_agent API from the repo root with its `.env`:
   ```text
   cd /home/yyf/project/image_agent && source .env && uvicorn apps.api.main:app --host 0.0.0.0 --port 8000 &
   ```

4. Verify recovery:
   ```text
   curl http://localhost:8000/health
   curl http://localhost:8000/tasks/{active_id}
   ```
   Both should return valid JSON with correct task data.

## Container Lifecycle vs API Lifecycle

Docker containers launched by the image_agent API are independent processes. An API restart, crash, or port conflict does not stop running containers.

### Rules

- Never assume an API restart means containers stopped. Check `docker ps` and inspect mounts before acting.
- Task logs may be stale (no new writes) while the container is still alive. Inspect `docker top <container>` and `docker logs <container>` to confirm liveness.
- Real QSIPrep tasks (e.g. task 65) may continue producing outputs in Docker while the API is down. After API recovery, check task output directories and Docker container status to reconcile task state.
- When a watcher script manages task submission (e.g. `scripts_watch_qsirecon_*.sh`), the watcher may also need restart if it depended on the API.

## Data Security

- Never commit or push patient data, DICOM files, NIfTI images, logs containing PHI, database dumps, or credentials to GitHub.
- Never stop unrelated containers or services on the host. If a port conflict or resource pressure occurs, isolate the conflict to image_agent-owned processes only.
- The `.env` file contains secrets. Ensure it is in `.gitignore` and never staged.

## DWI Lock and Resource Policy

Preserve DWI workflow serialization and the current user-approved resource profile:

- Real `dwi_qsiprep` and `dwi_qsi_full` runs acquire `data/projects/locks/dwi_qsiprep.lock` before launching containers.
- Default QSIPrep resources: `--nthreads 8 --omp-nthreads 4 --mem 24000`.
- Default QSIRecon resources: `--nprocs 8 --omp-nthreads 4 --mem 24000`.
- Do not increase concurrency without a host capacity check; keep these resource defaults unless the user explicitly changes them.

See `references/gpu-workflow-strategy.md` and `docs/workflows/dwi-qsi-workflow.md` for full policy.

## Docker Container Labels

Future workflow containers are labeled at launch with:

- `image_agent.app=image_agent`
- `image_agent.task_id=<task_id>`
- `image_agent.project_id=<project_id>`
- `image_agent.workflow_type=<workflow_type>`

Labels contain no patient data, PHI, or file paths. Labels enable the recovery module to identify orphaned containers without inspecting mounts or logs.

Task 65 (series 24 QSIPrep) is **unlabeled** because it started before the labeling patch was deployed. It remains handled by the temporary `scripts_monitor_task.sh` docker-wait watchdog. Labels apply to future task 66 / QSIRecon runs and all new containers after API restart.

## Health and Admin Endpoints

`GET /health` includes `app=image_agent` as an identity field. Watcher scripts and external monitors must verify this field to confirm they are talking to the correct application, not an unrelated service on port 8000.

`GET /admin/containers` is read-only and returns only containers matching the `image_agent.app=image_agent` label filter. It does not expose unrelated containers. Use it to list image_agent-owned containers without `docker ps` filtering.

## Orphan Recovery Module

`apps/api/app/workflows/recovery.py` handles labeled completed orphan containers — containers that finished (exit code 0 or non-zero) but whose task state was lost due to an API restart while the container was running.

### Commands

- `list` — enumerate labeled completed containers whose task_id is not found in the DB or whose DB state is inconsistent.
- `dry-run` — show what recovery would do without applying changes.
- `recover` — reconcile container exit codes and output directories back into DB task state.

### Safety Constraints

- **Never stops or kills containers.** Recovery only operates on already-completed containers.
- **Requires output files.** A container is only recoverable if output files exist at the expected output directory.
- **Requires DB state check.** Only reconciles when the DB task is in `running` or `queued` state (i.e., the task was in-flight when the API went down).
- **Label-gated.** Unlabeled containers (e.g., task 65) are invisible to the recovery module and must be handled manually or by the docker-wait watchdog.

## Mount Safety

The API validates container mounts before launching:

- **Writable mounts** (`:rw` or default) outside `PROJECTS_ROOT` are **rejected**. This prevents workflow containers from writing to host system directories.
- **Read-only support mounts** outside `PROJECTS_ROOT` (e.g., FreeSurfer license at `/opt/freesurfer/license.txt`) are **allowed only when at least one project mount under `PROJECTS_ROOT` exists**. This ensures every container has a clear project context.
- If no project mount exists, the container launch is rejected regardless of other mounts.

## Watcher /health Verification

Watcher scripts (`scripts_watch_qsirecon_*.sh`, `scripts_monitor_task.sh`) verify `/health` app identity before trusting task data:

- A non-matching or absent `app=image_agent` field means the response came from the wrong service.
- Repeated 404 or empty responses are treated as **possible port conflicts**, not immediate task loss. The watcher will retry with backoff and may alert rather than assume the task disappeared.
- After confirming API identity, the watcher proceeds with normal task polling.
