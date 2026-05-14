# Repository Map

Root: `/home/yyf/project/image_agent`

Known architecture:

- `apps/api`: FastAPI backend.
- `apps/api/app`: application code.
- `apps/api/tests`: backend tests.
- `apps/desktop`: React/Vite UI.
- `data/projects/{project_id}`: local/remote runtime data.
- `docs`: project architecture, API, workflow, and handoff docs.

Ownership boundaries:

- Backend API: route schemas, project/session/task endpoints, database models.
- Imaging IO: DICOM/NIfTI detection, conversion, BIDS-like construction, inventory.
- Workflow runtime: Docker command construction, validation, execution, output discovery.
- Frontend: upload, inventory, task run/status/log/output UI.
- Chat: DeepSeek prompt/tool routing grounded in backend state.

Do not move runtime data into source-controlled docs. Keep generated uploads, derivatives, logs, and caches out of hand-written documentation changes.
