You are the Claude skill agent for image_agent. Work in /home/yyf/project/image_agent.

Update skill/workflow docs to reflect the finalized orphan recovery implementation. Do not edit code. Do not touch data or containers.

Facts to document:
- Future Docker workflow containers are labeled with image_agent.app=image_agent plus task_id, project_id, workflow_type. Labels contain no patient data.
- /health includes app=image_agent identity and /admin/containers is read-only, label-filtered.
- Recovery module apps/api/app/workflows/recovery.py can list/dry-run/recover labeled completed orphan containers, never stops/kills containers, and requires output files plus DB running/queued state.
- Mount safety: writable mounts outside PROJECTS_ROOT are rejected; read-only support mounts outside PROJECTS_ROOT such as FreeSurfer license are allowed only when at least one project mount under PROJECTS_ROOT exists.
- Existing task 65 is unlabeled because it started before the patch, so it remains handled by the temporary docker-wait watchdog; labels apply to future task 66/QSIRecon/new runs after API restart.
- Watcher scripts verify /health app identity and treat repeated 404/empty responses as possible port conflicts, not immediate task loss.
- Tests: apps/api/.venv/bin/pytest -q apps/api/tests => 37 passed.

Update the most relevant docs under docs/skills and docs/workflows. Keep concise but actionable. Do not commit.
