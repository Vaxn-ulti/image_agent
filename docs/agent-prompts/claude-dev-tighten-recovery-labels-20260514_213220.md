You are the Claude development agent for image_agent. Work in /home/yyf/project/image_agent.

Apply one more focused tightening to the uncommitted recovery patch. Do not touch running tasks/containers.

Required changes:
1. In apps/api/app/workflows/pipeline.py, _inject_labels must only inject labels into docker run commands. If cmd is not docker run, return cmd unchanged. For docker run with --rm, insert after --rm; for docker run without --rm, insert after run. Do not create invalid commands like docker --label ... inspect.
2. In apps/api/app/workflows/recovery.py, the mount safety predicate should allow read-only support mounts outside PROJECTS_ROOT, reject any writable outside mount, and require at least one mount source under PROJECTS_ROOT. This prevents a labeled container with no project mount from being considered safe.
3. Update tests accordingly: remove/replace the test that expects labels in docker inspect; add tests for docker inspect unchanged and no project mount rejected while mixed project+RO-support passes.
4. Run apps/api/.venv/bin/pytest -q apps/api/tests and report changed files.

Do not commit.
