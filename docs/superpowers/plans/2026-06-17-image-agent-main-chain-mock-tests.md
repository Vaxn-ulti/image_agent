# Image Agent Main Chain Mock Tests Implementation Plan

> **For agentic workers:** Execute inline in the current session. Do not use subagents. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Finish the remaining control-plane mock, contract, and frontend integration tests for the fast-launch Image Agent main chain.

**Architecture:** Mock tests prove the control plane: API contracts, schema validation, Agent/task boundaries, workflow registry matching, preflight blocking, task state transitions, log/output registration, result-summary and artifact-manifest contracts, and frontend integration. Real script tests prove the execution plane and remain deployment acceptance evidence only when they run against actual data and registered outputs.

**Tech Stack:** FastAPI/Pydantic/pytest for backend contract tests, React/Vite/Vitest/Testing Library for frontend integration tests, OpenAI SDK-like model gateway contracts, skill-creator-style Image Agent skill docs.

---

## Scope

The remaining work is mock/control-plane only. Do not claim that DeepPrep, fMRIPrep, XCP-D, QSIPrep, QSIRecon, FSL, MRtrix, FreeSurfer, Docker, GPU, or licenses are validated by these tests.

## Git Cadence

- [x] Run `git status --short` at the start of the work block.
- [ ] Repeat git status roughly hourly, not after every small test.
- [ ] Do not stage or commit unless explicitly requested.

## Batch A: Upload And Series Control Plane

**Files:**
- Modify tests: `apps/console/src/routes/DashboardPage.test.tsx`
- Modify tests: `apps/console/src/routes/IngestPage.test.tsx`
- Modify tests if needed: `apps/api/tests/test_smoke_local_main_flow.py`

- [x] Confirm dashboard upload follows the current backend contract: zip archives use dataset ingest sessions, while direct `uploadDicom` remains scoped to the ingest page.
- [x] Add an ingest-page test that DICOM upload refreshes detected series and does not call DWI/NIfTI routes.
- [x] Add a local smoke test that upload responses with `workflow_eligibility` are preserved in safe uploaded-series evidence when present.

Run:

```bash
cd apps/api && python -m pytest tests/test_smoke_local_main_flow.py -q
cd apps/console && npm.cmd test -- DashboardPage.test.tsx IngestPage.test.tsx
```

## Batch B: Workflow Selection And Preflight Control Plane

**Files:**
- Modify tests: `apps/console/src/lib/workflows.test.ts`
- Modify tests: `apps/console/src/routes/DashboardPage.test.tsx`
- Modify tests if needed: `apps/api/tests/test_workflow_registry.py`

- [x] Add a workflow helper test that backend `blocked_workflows` reason wins over frontend fallback for every workflow lane.
- [x] Add a dashboard test that blocked workflows cannot call `api.runSeries`.
- [x] Add a dashboard test that the selected workflow stays backend-runnable when the workflow catalog contains incubation entries.

Run:

```bash
cd apps/api && python -m pytest tests/test_workflow_registry.py -q
cd apps/console && npm.cmd test -- workflows.test.ts DashboardPage.test.tsx
```

## Batch C: Task Lifecycle And Result Contracts

**Files:**
- Modify tests: `apps/api/tests/test_api_flow.py`
- Modify tests: `apps/api/tests/test_artifact_manifest_api.py`
- Modify tests: `apps/console/src/routes/TasksPage.test.tsx`
- Modify tests: `apps/console/src/routes/ResultDetailPage.test.tsx`
- Modify tests: `apps/console/src/routes/ResultsIndexPage.test.tsx`

- [ ] Add backend contract coverage for failed task status plus safe logs/outputs.
- [x] Add backend contract coverage that the complete T1 mock flow returns safe outputs, result-summary, artifact-manifest, logs, and chat state.
- [ ] Add backend contract coverage that result-summary and artifact-manifest stay safe when outputs are empty or partially missing.
- [ ] Add frontend task page coverage for failed/running/completed state display from backend data.
- [ ] Add frontend result detail coverage for missing native QC with derived report artifacts still marked derived.

Run:

```bash
cd apps/api && python -m pytest tests/test_api_flow.py tests/test_artifact_manifest_api.py -q
cd apps/console && npm.cmd test -- TasksPage.test.tsx ResultDetailPage.test.tsx ResultsIndexPage.test.tsx
```

## Batch D: Agent Boundary And RAG Source Control Plane

**Files:**
- Modify tests: `apps/api/tests/test_agent_api.py`
- Modify tests: `apps/api/tests/test_agent_graph.py`
- Modify tests: `apps/console/src/routes/AgentPage.test.tsx`
- Modify tests: `apps/console/src/components/agent/AgentEvidencePanel.test.tsx`

- [x] Add backend coverage that Agent confirmation never creates a production task before deterministic resume or `/series/{series_id}/run`.
- [ ] Add backend coverage that Chat Completions-compatible providers report no model tool loop while Responses providers report tool-loop capability when configured.
- [ ] Add frontend Agent coverage for confirmation-required workflow suggestions without treating them as launched tasks.
- [ ] Add frontend Agent evidence coverage for RAG citations and source boundaries.

Run:

```bash
cd apps/api && python -m pytest tests/test_agent_api.py tests/test_agent_graph.py -q
cd apps/console && npm.cmd test -- AgentPage.test.tsx AgentEvidencePanel.test.tsx
```

## Batch E: Fast-Launch Readiness And Documentation Guards

**Files:**
- Modify tests: `apps/api/tests/test_agent_api.py`
- Modify tests: `apps/api/tests/test_skill_and_rag_docs.py`
- Modify docs if needed: `docs/product-readiness.md`
- Modify docs if needed: `docs/skills/image-agent-developer/references/testing-matrix.md`

- [ ] Add/readiness coverage that `/deployment.fast_launch_readiness` remains blocked by missing strict deployment acceptance even when local mock smoke passes.
- [ ] Add doc guard coverage for mock/control-plane and real-script/execution-plane wording.
- [ ] Add doc guard coverage that strict deployment acceptance uses real registered workflow evidence and rejects debug-only mock workflow evidence.

Run:

```bash
cd apps/api && python -m pytest tests/test_agent_api.py tests/test_skill_and_rag_docs.py -q
```

## Final Mock Completion Verification

- [ ] Run the focused backend mock/contract suite.
- [ ] Run the focused frontend integration suite.
- [ ] Run lint/typecheck for console if frontend tests changed.
- [ ] Update `progress.md` with exact test results.

Run:

```bash
cd apps/api && python -m pytest tests/test_smoke_local_main_flow.py tests/test_api_flow.py tests/test_agent_api.py tests/test_agent_graph.py tests/test_agent_tools.py tests/test_workflow_registry.py tests/test_result_contract.py tests/test_artifact_manifest_api.py tests/test_fixed_workflow_api_contract.py tests/test_skill_and_rag_docs.py -q
cd apps/console && npm.cmd test -- DashboardPage.test.tsx IngestPage.test.tsx TasksPage.test.tsx AgentPage.test.tsx ResultDetailPage.test.tsx ResultsIndexPage.test.tsx api.test.ts workflows.test.ts resultArtifacts.test.ts AgentEvidencePanel.test.tsx
cd apps/console && npm.cmd run lint && npx tsc -b --noEmit
```
