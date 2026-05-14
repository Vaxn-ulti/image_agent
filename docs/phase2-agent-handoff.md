# Phase 2 Agent Handoff Protocol

Four agents share ownership of the Phase 2 codebase. Each owns specific directories and concerns. Cross-boundary changes require a handoff entry in this document.

## Ownership Map

### Backend Agent

**Owns:**
- `apps/backend/api/` — all FastAPI routes, request/response schemas, validation
- `apps/backend/db/` — SQLAlchemy models, migrations, alembic
- `apps/backend/config.py` — env vars, constants, Docker image tags
- `apps/backend/storage/` — file storage, directory layout, path resolution

**Must not touch:**
- `apps/backend/workflows/` — workflow runner internals
- `apps/desktop/` — frontend code
- `apps/backend/detection/` — modality detection logic

**Handoff needed when:** a new API endpoint requires a new detection step or workflow type.

### Workflow Agent

**Owns:**
- `apps/backend/workflows/` — all workflow modules (deepprep, qsiprep, qsirecon, qsi_full)
- `apps/backend/detection/` — NIfTI header parsing, modality/format detection
- `apps/backend/bids.py` — minimal BIDS construction, symlink farm

**Must not touch:**
- `apps/backend/api/` — route definitions, HTTP schemas
- `apps/backend/db/` — ORM models, migrations
- `apps/desktop/` — frontend code

**Handoff needed when:** a workflow needs a new DB column, a new API parameter, or a new output type that the API must expose.

### Frontend Agent

**Owns:**
- `apps/desktop/` — all UI code, API client, workflow selection, task display
- `apps/desktop/src/api/` — typed API client matching backend schemas

**Must not touch:**
- `apps/backend/` — any server-side code

**Handoff needed when:** the UI needs a new API endpoint or a change to an existing response shape. The Backend agent must implement the endpoint first, then the Frontend agent consumes it.

### Review/Test Agent

**Owns:**
- `apps/backend/tests/` — pytest suite, fixtures, mocks
- `docs/` — architecture and contract docs (this file)
- Smoke scripts (`scripts/smoke-*.py`) — end-to-end validation scripts

**Must not touch:**
- `apps/backend/api/`, `apps/backend/workflows/`, `apps/desktop/` — production code

**Handoff needed when:** tests reveal a contract violation — the owning agent must fix the code, not the test.

## Handoff Format

Each cross-agent change must be recorded with:

```
## Handoff YYYY-MM-DD: <title>
- **From:** <source agent>
- **To:** <target agent>
- **What:** <concrete change needed>
- **Why:** <reason / context>
- **Contract reference:** <file:line or endpoint>
```

## Shared Contracts (no handoff needed)

These are read by all agents and can be updated by any agent with a note in git:
- `docs/phase2-architecture.md` — overall design
- `docs/phase2-api.md` — API shapes
- `docs/phase2-workflows.md` — workflow command contracts
- `docs/phase2-agent-handoff.md` — this file

## Cross-Cutting Rules

1. **Sudo password:** handled by `config.py` only. No other module reads `IMAGE_AGENT_SUDO_PASSWORD`. Workflows call a shared `run_docker(cmd: list[str])` helper that injects `sudo -S` via stdin.
2. **File paths:** Backend storage module resolves all paths. Workflows receive absolute paths only — never construct paths from raw input.
3. **DB writes:** Backend owns the `tasks` and `outputs` tables. Workflows call a Backend-provided callback (`on_progress`, `on_output`, `on_complete`) — never write to DB directly.
4. **Error handling:** Workflows raise typed exceptions (`WorkflowError`, `ImageNotFoundError`). Backend API layer catches them and maps to HTTP status codes.
5. **Logging:** One log file per task at `logs/{task_id}.log`. Workflows append structured lines. Backend reads logs for the status endpoint.

## Initial Handoffs (Phase 2 setup)

### Handoff 2026-05-13: Workflow runner interface
- **From:** Backend Agent
- **To:** Workflow Agent
- **What:** Backend provides `run_docker(cmd, task_id)`, `on_progress(task_id, pct)`, `on_output(task_id, type, path)`, `on_complete(task_id)`, `on_fail(task_id, error)` callbacks. Workflow modules import and call them.
- **Why:** DB and subprocess ownership stays with Backend.
- **Contract reference:** `docs/phase2-architecture.md` line 50-55.

### Handoff 2026-05-13: API response shapes for workflow outputs
- **From:** Workflow Agent
- **To:** Backend Agent
- **What:** Workflow defines `OUTPUT_PATTERNS` dict mapping filename globs to `output_type` strings. Backend reads this to implement output discovery in the API layer.
- **Why:** Output type definitions are workflow knowledge but the API serves them.
- **Contract reference:** `docs/phase2-api.md` line 120-126.
