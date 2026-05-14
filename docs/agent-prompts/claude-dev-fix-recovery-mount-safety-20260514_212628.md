You are the Claude development agent for image_agent. Work in /home/yyf/project/image_agent.

Apply a focused fix to the uncommitted orphan recovery patch based on review findings. Do not touch running containers/tasks.

Required fix:
- In apps/api/app/workflows/recovery.py, update _container_in_project_tree so real containers with read-only support mounts outside PROJECTS_ROOT (for example FreeSurfer license) are allowed, but any writable mount outside PROJECTS_ROOT is rejected.
- Keep the requirement that the recovery only acts on containers with image_agent labels and project ids. Do not make it less safe.
- Add/adjust tests in apps/api/tests/test_api_flow.py so the normal Docker inspect case is covered: project mounts inside PROJECTS_ROOT with RW true, read-only license/support mount outside PROJECTS_ROOT with RW false should pass; writable outside mount should fail.
- Optionally make _inject_labels defensive if --rm is missing and add a small test, but keep scope tight.
- Run apps/api/.venv/bin/pytest -q apps/api/tests and report changed files.

Do not commit. Do not stop/rerun task 65 or 66.
