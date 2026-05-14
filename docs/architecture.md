# Architecture

Phase 1 is a remote-compute MVP. The GUI sends files and commands to a Linux backend; the backend owns data, workflow execution, status, logs, and results.

## Components

- Desktop UI: React/Vite SPA. Tauri can wrap it later without changing API contracts.
- API: FastAPI service with SQLite and filesystem storage.
- Imaging detection: deterministic NIfTI header parser, not LLM guessing.
- Workflow runtime: mock DeepPrep task first; real DeepPrep command is isolated behind workflow code.
- Chat: deterministic tool router for status/result explanations.

## Storage

`data/projects/{project_id}/raw` stores uploads.
`data/projects/{project_id}/derivatives/{task_id}` stores workflow outputs.
`data/projects/{project_id}/logs/{task_id}.log` stores logs.

## Boundaries

- Backend agent owns `apps/api/app/api`, `core`, `db`, `agent`.
- Workflow agent owns `apps/api/app/imaging` and `workflows`.
- Frontend agent owns `apps/desktop`.
- Review/Test agent can edit tests and small integration fixes.
