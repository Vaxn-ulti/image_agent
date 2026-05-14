# Workflow State

Allowed states: `queued`, `running`, `completed`, `failed`, `cancelled`.

Transitions:

- `queued -> running`
- `running -> completed`
- `running -> failed`
- `queued|running -> cancelled`

Mock T1 DeepPrep steps:

1. Create task and log file.
2. Set state `running` and progress 10.
3. Validate input series exists.
4. Write synthetic QC/report/output placeholders.
5. Register outputs.
6. Set progress 100 and state `completed`.

Real DeepPrep integration must only replace `apps/api/app/workflows/deepprep.py` execution internals and preserve task/output contracts.
