# Target Graph Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move Image Agent from the current first-version LangGraph skeleton toward the full production target graph by implementing the next safety-critical graph nodes and contracts.

**Architecture:** Keep `LangGraphAgentRunner` as the graph orchestration owner. Add small deterministic graph nodes with typed state fields, safe event metadata, compiled/fallback parity tests, and no production task creation before policy and authorization gates.

**Tech Stack:** Python, Pydantic v2, LangGraph-compatible fallback, pytest, FastAPI backend tests.

---

## File Structure

- Modify: `apps/api/app/agent/langgraph_runner.py`
  - Add target graph nodes in slices.
  - Preserve deterministic fallback parity.
- Modify: `apps/api/app/agent/state.py`
  - Add state fields for completeness, clarification, neuroimaging intake, sequence normalization, preflight-lite, capability matching, plan policy, authorization.
- Create/modify: `apps/api/app/agent/requirements.py`
  - Own requirement completeness and clarification contracts.
- Create/modify: `apps/api/app/agent/neuro_router.py`
  - Own neuroimaging data intake validation, sequence normalization, and capability matching.
- Create/modify: `apps/api/app/agent/policy.py`
  - Own ExecutionPlan policy gate and permission scope classifier.
- Modify tests:
  - `apps/api/tests/test_agent_graph.py`
  - `apps/api/tests/test_execution_plan_contract.py`
  - new focused tests as modules grow.
- Modify docs:
  - `docs/bmad_development_log.md`
  - target graph decision docs under `docs/superpowers/specs/`.

## Slice 1: Requirement Completeness And Clarification Interrupt

- [ ] Add failing tests for graph nodes:
  - `requirement_completeness`
  - `clarification_interrupt`
  - checkpoint-like resumable state for missing series/workflow/authorization facts.
- [ ] Implement `RequirementCompleteness` contract:
  - `status=complete|needs_clarification`
  - `missing_fields`
  - `clarifying_question`
  - `safe_context`
  - `production_task_created=false`
- [ ] Wire graph:
  - tool-task route enters `requirement_completeness`;
  - incomplete requirements route to `clarification_interrupt`;
  - complete requirements continue to neuroimaging intake.
- [ ] Verify:
  - ambiguous “处理一下这个数据” stops before confirmation;
  - explicit run with series/workflow proceeds to later graph lane;
  - compiled and fallback graph event order match.
- [ ] Commit checkpoint.

## Slice 2: Neuroimaging Intake And Sequence Normalization

- [ ] Add tests for `neuroimaging_data_intake_validation` and `sequence_metadata_normalization`.
- [ ] Implement deterministic intake summary from project context:
  - files;
  - imaging series;
  - format;
  - modality;
  - sidecars;
  - unsupported reasons.
- [ ] Implement metadata precedence:
  - sidecar JSON;
  - DICOM tags;
  - NIfTI header;
  - filename tokens.
- [ ] Verify unsupported recognized sequences receive the exact limitation boundary.
- [ ] Commit checkpoint.

## Slice 3: Capability Matcher And Registry Recommendation

- [ ] Add tests for:
  - registry-backed fixed workflow match;
  - non-agent-selectable workflow exclusion;
  - unknown workflow incubation;
  - capability evidence in graph state.
- [ ] Implement `capability_matcher`, `curated_workflow_registry`, and `fixed_workflow_recommendation` graph nodes.
- [ ] Ensure LLM cannot promote an unregistered workflow to production.
- [ ] Commit checkpoint.

## Slice 4: ExecutionPlan Candidate And Policy Gate

- [ ] Add tests for `execution_plan_candidate` schema and `plan_policy_gate`.
- [ ] Build candidate plan from fixed mature workflow or sandbox recipe.
- [ ] Gate invalid plans before authorization:
  - missing workflow id;
  - unpinned container;
  - missing input manifest;
  - unsafe mounts;
  - missing QC/artifact expectations.
- [ ] Commit checkpoint.

## Slice 5: Authorization And Execution Control Plane Boundary

- [ ] Add tests that no production task can be created before authorization.
- [ ] Implement permission scope classifier:
  - fixed mature workflow;
  - sandbox/new tool;
  - retry/replan;
  - sensitive export/delete/cross-project action.
- [ ] Implement task-bound authorization TTL contract.
- [ ] Connect approved plan to the existing execution control plane adapter without creating new remote workflow behavior locally.
- [ ] Commit checkpoint.

## Verification Cadence

After each slice:

```bash
python -m pytest apps/api/tests/test_agent_graph.py -q
python -m pytest apps/api/tests/test_agent_intent.py apps/api/tests/test_agent_api.py::test_agent_run_unconfigured_model_answers_inventory_without_confirmation apps/api/tests/test_agent_api.py::test_agent_run_forces_unknown_fixed_workflow_into_incubation_without_production_task -q
git diff --check
```

For larger execution-control-plane slices, add:

```bash
python -m pytest apps/api/tests/test_execution_plan_contract.py apps/api/tests/test_execution_task_service.py apps/api/tests/test_task_executor.py -q
```

## Scope Guard

This plan does not run remote workflows, restart remote APIs, create production tasks, change deployment secrets, or perform public-internet deployment. Those actions require a separate BMAD remote-verification checkpoint and explicit operator evidence.

## Self-Review

- This plan aligns directly to target graph lines 539-640 in `docs/image_agent_production_implementation_spec.md`.
- It prioritizes graph safety gates before execution-system expansion.
- It turns section 9 engineering questions into enforceable graph contracts instead of prose only.
