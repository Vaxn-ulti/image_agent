# Architecture

Image Agent is a remote-compute first release. The console sends files and
workflow requests to a backend service; the backend owns data, workflow
execution, status, logs, and results.

## Components

- Desktop UI: React/Vite SPA. Tauri can wrap it later without changing API contracts.
- API: FastAPI service with SQLite and filesystem storage.
- Imaging detection: deterministic NIfTI header parser, not LLM guessing.
- Workflow runtime: registered workflow runners with pinned container images
  and explicit preflight checks.
- Chat: deterministic tool router for status/result explanations.

## Storage

`data/projects/{project_id}/raw` stores uploads.
`data/projects/{project_id}/derivatives/{task_id}` stores workflow outputs.
`data/projects/{project_id}/logs/{task_id}.log` stores logs.

## Boundaries

- Backend API modules expose project, upload, task, result, Agent, and runtime
  endpoints.
- Workflow modules own imaging metadata parsing, preflight, execution, and
  output registration.
- Console and desktop clients consume public API responses and avoid database
  coupling.
