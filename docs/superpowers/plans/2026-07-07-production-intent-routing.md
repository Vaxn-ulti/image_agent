# Production Intent Routing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement production-grade layered intent routing for Image Agent using deterministic rule signals, structured LLM intent fields, a conservative fusion gate, and explicit LangGraph nodes for each stage.

**Architecture:** Extend `app.agent.intent` into the single owner of rule classification, LLM signal validation, and final fusion. Split LangGraph intent routing into `rule_intent_classifier`, `llm_intent_planner`, and `intent_fusion_gate` nodes so production traces show each decision stage.

**Tech Stack:** Python, Pydantic v2, pytest, FastAPI backend tests.

---

## File Structure

- Modify: `apps/api/app/agent/intent.py`
  - Add `RuleIntentSignal`, `LLMIntentSignal`, `IntentFusionDecision`, rule classifier, LLM signal extraction, and fusion policy.
- Modify: `apps/api/app/agent/graph.py`
  - Expand `AGENT_PLANNER_DECISION_SCHEMA` with required production intent fields.
  - Keep `_plan()` calling `normalize_intent_decision()`.
- Modify: `apps/api/app/agent/langgraph_runner.py`
  - Replace hidden `classify_intent` behavior with graph-visible rule, LLM planner, and fusion nodes.
  - Keep fallback graph node order in parity with compiled LangGraph.
- Modify: `apps/api/app/agent/state.py`
  - Add state fields for `rule_intent_signal`, `llm_intent_signal`, and `intent_decision`.
- Modify: `apps/api/tests/test_agent_intent.py`
  - Add production rule/fusion conflict tests.
- Modify: `apps/api/tests/test_agent_graph.py`
  - Add schema and trace tests.
- Modify: `docs/bmad_development_log.md`
  - Record BMAD production-intent checkpoint, test evidence, and commits.

## Task 1: Rule Signals

- [ ] Add failing tests for `classify_rule_intent()` covering read-only inventory, status, result analysis, explicit launch, negated launch, and unknown workflow wording.
- [ ] Run `python -m pytest apps/api/tests/test_agent_intent.py -q` and confirm the new tests fail because `classify_rule_intent` does not exist.
- [ ] Implement `RuleIntentSignal` and `classify_rule_intent()` in `apps/api/app/agent/intent.py`.
- [ ] Run `python -m pytest apps/api/tests/test_agent_intent.py -q` and confirm it passes.
- [ ] Commit with `feat: add production intent rule classifier`.

## Task 2: LLM Signal And Fusion Gate

- [ ] Add failing tests for missing confidence, rule/LLM launch conflict, explicit launch allowed, low-confidence launch clarification, and incubation routing.
- [ ] Run `python -m pytest apps/api/tests/test_agent_intent.py -q` and confirm expected failures.
- [ ] Implement `LLMIntentSignal`, `IntentFusionDecision`, `extract_llm_intent_signal()`, and conservative fusion inside `normalize_intent_decision()`.
- [ ] Run `python -m pytest apps/api/tests/test_agent_intent.py -q` and confirm it passes.
- [ ] Commit with `feat: fuse rule and llm intent decisions`.

## Task 3: Planner Schema

- [ ] Add failing tests in `test_agent_graph.py` proving the planner schema requires `intent_category`, `intent_subcategory`, `confidence`, `evidence_spans`, `risk_level`, `ambiguities`, and `route_recommendation`.
- [ ] Run the focused schema tests and confirm expected failures.
- [ ] Update `AGENT_PLANNER_DECISION_SCHEMA` and any fake gateway decisions needed by tests.
- [ ] Run `python -m pytest apps/api/tests/test_agent_intent.py apps/api/tests/test_agent_graph.py -q` and confirm it passes.
- [ ] Commit with `test: require production intent planner contract`.

## Task 4: Production LangGraph Nodes

- [ ] Add failing tests proving `LangGraphAgentRunner._compile_graph()` includes `rule_intent_classifier`, `llm_intent_planner`, and `intent_fusion_gate` in order before `answer_or_task_router`.
- [ ] Add fallback graph tests proving the same stage events are emitted without compiled LangGraph.
- [ ] Add public graph state tests proving `intent_decision`, `rule_intent_signal`, and `llm_intent_signal` are exposed safely.
- [ ] Run focused graph tests and confirm expected failures.
- [ ] Update `ImageAgentState` fields and `LangGraphAgentRunner` nodes/fallback path.
- [ ] Run `python -m pytest apps/api/tests/test_agent_graph.py -q` and confirm it passes.
- [ ] Commit with `feat: expose production intent stages in langgraph`.

## Task 5: Regression, BMAD Log, Final Checkpoint

- [ ] Run focused API regression:
  `python -m pytest apps/api/tests/test_agent_intent.py apps/api/tests/test_agent_graph.py apps/api/tests/test_agent_api.py::test_agent_run_unconfigured_model_answers_inventory_without_confirmation apps/api/tests/test_agent_api.py::test_agent_run_forces_unknown_fixed_workflow_into_incubation_without_production_task -q`
- [ ] Run `git diff --check`.
- [ ] Update `docs/bmad_development_log.md` with production-intent scope, tests, and commit hashes.
- [ ] Commit with `docs: log production intent routing checkpoint`.
- [ ] Run fresh final verification after the final commit.

## Self-Review

- Spec coverage: tasks cover rule classifier, LLM structured signal, fusion policy, schema contract, production LangGraph nodes, fallback graph parity, regression, BMAD log, and checkpoint commits.
- Scope control: no remote workflow run, frontend design, or production task execution changes are included.
- Type consistency: public entry point remains `normalize_intent_decision(message=..., model_decision=...) -> tuple[dict, list[dict]]`.
