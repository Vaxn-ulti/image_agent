You are the Claude development agent for image_agent. Work in /home/yyf/project/image_agent.

The controller approves implementation of your recovery plan. Implement a minimal, safe patch now.

Current runtime facts:
- Real QSIPrep task 65 is still running in Docker container b0aaeabd76b0 and must not be stopped unless clearly failed with evidence.
- Task 66 is waiting on data/projects/locks/dwi_qsiprep.lock.
- The API was restarted after an unrelated uvicorn occupied port 8000; Docker task 65 outlived that API process, so DB state needs robust orphan recovery.
- Existing patch faf5930 already added reduced DWI resource defaults and dwi_qsiprep lock. Preserve it.
- Skill agent already documented port conflicts and container continuity. Coordinate with those docs; update docs if your implementation changes operational steps.

Implement these changes, keeping scope tight:
1. Add Docker labels to image_agent-launched containers, including task id, project id, workflow type, and app marker. Labels must not include patient data.
2. Add a safe recovery/admin script or backend helper that can list project-owned containers, map containers to task ids, recover an orphaned completed container/output into DB state, and avoid touching containers outside /home/yyf/project/image_agent/data/projects.
3. Improve watcher resilience if needed: transient 404/connection failure should not immediately imply task loss; logs should point to possible port conflict.
4. Add focused pytest coverage for label construction/recovery safety if backend code changes.
5. Run apps/api/.venv/bin/pytest -q apps/api/tests.
6. Report changed files and remaining runtime actions. Do not commit; controller will review and commit.

Safety rules:
- Never stop unrelated containers.
- Never stage/commit patient data, logs, DB files, archives, credentials, or neuroimaging files.
- Do not rerun or kill task 65/66.
