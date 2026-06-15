# Main Routing Services Refactor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. The user explicitly requested no multi-subagent execution.

**Goal:** Split the oversized FastAPI `main.py` entrypoint into clear route and service boundaries while preserving existing API behavior.

**Architecture:** Keep `app.main` as the public application factory/module so existing imports and tests continue to work. Move request models and shared helpers into focused modules, then register `APIRouter` modules from `main.py`. Preserve current Agent boundaries: Agent can explain/query/recommend, while deterministic backend task creation remains behind explicit API/service calls.

**Tech Stack:** FastAPI, Pydantic, SQLite helpers in `app.db.database`, pytest/TestClient.

---

### Task 1: Add Architecture Guard

**Files:**
- Create: `apps/api/tests/test_main_architecture.py`

- [ ] **Step 1: Write the failing test**

```python
from pathlib import Path


def test_main_entrypoint_is_thin_and_routes_are_split():
    root = Path(__file__).resolve().parents[1]
    main_source = (root / "app" / "main.py").read_text(encoding="utf-8")

    assert len(main_source.splitlines()) <= 450
    for route_name in ("system", "agent", "auth", "projects", "uploads", "series", "tasks", "results", "reports", "chat"):
        assert (root / "app" / "routes" / f"{route_name}.py").exists()

    for service_name in ("project_service", "upload_service", "task_service", "result_service", "agent_service"):
        assert (root / "app" / "services" / f"{service_name}.py").exists()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd apps/api; python -m pytest tests/test_main_architecture.py -q`

Expected: FAIL because `main.py` is still over 450 lines and route/service modules do not exist.

### Task 2: Extract Shared Schemas And Dependencies

**Files:**
- Create: `apps/api/app/schemas.py`
- Create: `apps/api/app/dependencies.py`
- Modify: `apps/api/app/main.py`

- [ ] **Step 1: Move Pydantic request models into `schemas.py`**

Move `LoginRequest`, `ProjectCreate`, `UploadSessionCreate`, `RunRequest`, `ChatRequest`, `AgentRunRequest`, `AgentResumeRequest`, `AgentResumeConfirmation`, `RagQueryRequest`, `ScientificReportVerifyRequest`, `BoldGroupAnalysisRequest`, and `BoldDescriptiveReviewRequest`.

- [ ] **Step 2: Move shared constants/helpers into `dependencies.py`**

Move `REPO_ROOT`, `WORKFLOWS`, `ALLOWED_WORKFLOWS`, `rows`, `parse_series_row`, `save_upload`, DWI sidecar helpers, and `enrich_inventory_workflow_eligibility`.

- [ ] **Step 3: Keep compatibility aliases in `main.py`**

Re-export names that tests monkeypatch today, including `PROJECTS_ROOT`, `REPO_ROOT`, `AgentRunner`, `ModelGateway`, `complete_chat`, `build_rag_response`, `run_pipeline_task`, and `run_mock_deepprep`.

### Task 3: Extract Services

**Files:**
- Create: `apps/api/app/services/project_service.py`
- Create: `apps/api/app/services/upload_service.py`
- Create: `apps/api/app/services/task_service.py`
- Create: `apps/api/app/services/result_service.py`
- Create: `apps/api/app/services/agent_service.py`
- Create: `apps/api/app/services/__init__.py`

- [ ] **Step 1: Move project creation/listing logic into `project_service.py`**
- [ ] **Step 2: Move upload and ingest logic into `upload_service.py`**
- [ ] **Step 3: Move workflow validation/task creation logic into `task_service.py`**
- [ ] **Step 4: Move outputs/result/artifact logic into `result_service.py`**
- [ ] **Step 5: Move Agent/RAG/chat orchestration logic into `agent_service.py`**

### Task 4: Extract Routes

**Files:**
- Create: `apps/api/app/routes/system.py`
- Create: `apps/api/app/routes/agent.py`
- Create: `apps/api/app/routes/auth.py`
- Create: `apps/api/app/routes/projects.py`
- Create: `apps/api/app/routes/uploads.py`
- Create: `apps/api/app/routes/series.py`
- Create: `apps/api/app/routes/tasks.py`
- Create: `apps/api/app/routes/results.py`
- Create: `apps/api/app/routes/reports.py`
- Create: `apps/api/app/routes/chat.py`
- Create: `apps/api/app/routes/__init__.py`
- Modify: `apps/api/app/main.py`

- [ ] **Step 1: Register routers from `main.py`**
- [ ] **Step 2: Move each endpoint into its route module without changing paths**
- [ ] **Step 3: Keep `/chat` compatibility in `routes/chat.py`**
- [ ] **Step 4: Keep scientific report verification under `routes/reports.py`**

### Task 5: Verify Contracts

**Files:**
- Modify only if tests expose real compatibility gaps.

- [ ] **Step 1: Run architecture guard**

Run: `cd apps/api; python -m pytest tests/test_main_architecture.py -q`

Expected: PASS.

- [ ] **Step 2: Run API contract tests**

Run: `cd apps/api; python -m pytest tests/test_agent_api.py tests/test_fixed_workflow_api_contract.py tests/test_artifact_manifest_api.py -q`

Expected: PASS.

- [ ] **Step 3: Run broader API flow tests**

Run: `cd apps/api; python -m pytest tests/test_api_flow.py -q`

Expected: PASS.

### Task 6: Record Work Log And Git Backup

**Files:**
- Modify: `docs/work-log-2026-06-15.md`

- [ ] **Step 1: Add a short work log entry**

Record the route/service refactor, tests run, and any remaining remote-only acceptance boundary.

- [ ] **Step 2: Commit verified changes**

Run:

```bash
git add apps/api/app apps/api/tests docs/superpowers/plans docs/work-log-2026-06-15.md
git commit -m "refactor: split api routes and services"
```
