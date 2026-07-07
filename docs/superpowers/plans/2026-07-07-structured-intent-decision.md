# Structured Intent Decision Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a small structured intent layer for the Image Agent planner so read-only questions, explicit fixed-workflow launch requests, and unsafe/unknown workflow requests are normalized before LangGraph routing.

**Architecture:** Create a focused `app.agent.intent` module that owns intent enums, a Pydantic decision model, rule-first guards, and confidence-gate metadata. Keep `graph.py` as the orchestration owner by converting model planner dictionaries through the new intent module before existing confirmation/incubation/read-only branches run.

**Tech Stack:** Python, Pydantic v2, FastAPI backend test suite, pytest.

---

## File Structure

- Create: `apps/api/app/agent/intent.py`
  - Owns `IntentDecision`, constants for statuses/categories, and `normalize_intent_decision()`.
- Modify: `apps/api/app/agent/graph.py`
  - Imports the new normalizer and replaces duplicated keyword guard logic in `_plan()`.
- Create: `apps/api/tests/test_agent_intent.py`
  - Unit tests for normalization, confidence gate, and read-only/launch classification.
- Modify: `apps/api/tests/test_agent_graph.py`
  - Integration tests proving `AgentRunner._plan()` emits guard traces from the structured intent layer.
- Modify: `docs/bmad_development_log.md`
  - Records the BMAD iteration, verification, and backup commit cadence.

## Task 1: Intent Model And Rule Guards

**Files:**
- Create: `apps/api/app/agent/intent.py`
- Test: `apps/api/tests/test_agent_intent.py`

- [ ] **Step 1: Write the failing tests**

Add tests that import `normalize_intent_decision()` and assert:

```python
def test_inventory_question_forces_read_only_even_when_model_requests_run():
    decision, trace = normalize_intent_decision(
        message="我上传了什么文件，可以跑什么任务",
        model_decision={
            "intent": "run_workflow",
            "action_lane": "fixed_workflow",
            "lane": "fixed_workflow",
            "workflow_type": "t1_deepprep_anat_report",
            "requires_confirmation": True,
            "confidence": 0.92,
        },
    )

    assert decision["intent"] == "answer_question"
    assert decision["action_lane"] is None
    assert decision["lane"] is None
    assert decision["requires_confirmation"] is False
    assert decision["intent_decision"]["category"] == "inventory_capability"
    assert trace == [{
        "stage": "intent_decision",
        "status": "forced_read_only_inventory_capability_answer",
        "category": "inventory_capability",
        "confidence": 1.0,
        "production_task_created": False,
    }]
```

Also add tests for explicit launch preserving `run_workflow`, low confidence forcing read-only clarification, and unknown/non-fixed workflow preserving incubation metadata.

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest apps/api/tests/test_agent_intent.py -q`

Expected: FAIL with `ModuleNotFoundError: No module named 'app.agent.intent'`.

- [ ] **Step 3: Write minimal implementation**

Implement `intent.py` with:

```python
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.workflows.registry import FIXED_WORKFLOW, INCUBATION_LANE

IntentName = Literal["answer_question", "run_workflow"]


class IntentDecision(BaseModel):
    model_config = ConfigDict(extra="allow")

    intent: IntentName = "answer_question"
    action_lane: str | None = None
    lane: str | None = None
    workflow_type: str | None = None
    series_id: int | None = None
    summary: str | None = None
    confidence: float = Field(default=0.75, ge=0.0, le=1.0)
    requires_confirmation: bool | None = None


def normalize_intent_decision(
    *, message: str, model_decision: dict[str, Any], confidence_threshold: float = 0.55
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    ...
```

Fill the body with deterministic token checks moved from `graph.py`, plus an `intent_decision` metadata block containing `category`, `confidence`, `source`, and `gate`.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest apps/api/tests/test_agent_intent.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

Run:

```bash
git add apps/api/app/agent/intent.py apps/api/tests/test_agent_intent.py docs/superpowers/plans/2026-07-07-structured-intent-decision.md
git commit -m "feat: add structured agent intent decision"
```

## Task 2: Integrate Intent Decision Into AgentRunner

**Files:**
- Modify: `apps/api/app/agent/graph.py`
- Modify: `apps/api/tests/test_agent_graph.py`

- [ ] **Step 1: Write the failing integration tests**

Add tests that instantiate `AgentRunner` with a fake gateway returning `run_workflow` for read-only inventory questions and assert:

```python
decision, trace = runner._plan(
    message="先解释我上传了什么，可以跑什么任务，不要启动",
    project_context={"project_id": 1, "series": []},
)
assert decision["intent"] == "answer_question"
assert decision["intent_decision"]["category"] == "inventory_capability"
assert trace[-1]["stage"] == "intent_decision"
assert trace[-1]["status"] == "forced_read_only_inventory_capability_answer"
```

Add one explicit launch test asserting `message="请立即运行 T1 工作流"` keeps `run_workflow`.

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest apps/api/tests/test_agent_graph.py::test_agent_plan_uses_structured_intent_guard_for_inventory_question apps/api/tests/test_agent_graph.py::test_agent_plan_preserves_explicit_fixed_workflow_launch -q`

Expected: FAIL because `_plan()` still uses legacy `intent_guard` traces and does not attach `intent_decision`.

- [ ] **Step 3: Write minimal implementation**

In `graph.py`, import:

```python
from app.agent.intent import normalize_intent_decision
```

Then replace the legacy `_asks_for_inventory_or_capability_explanation()` / `_asks_for_fixed_workflow_confirmation()` block in `_plan()` with:

```python
decision, intent_trace = normalize_intent_decision(message=message, model_decision=decision)
tool_trace = [*tool_trace, *intent_trace]
```

Keep the old static helper methods only if tests or other modules still call them; otherwise remove them after focused tests pass.

- [ ] **Step 4: Run focused tests**

Run: `python -m pytest apps/api/tests/test_agent_intent.py apps/api/tests/test_agent_graph.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

Run:

```bash
git add apps/api/app/agent/graph.py apps/api/tests/test_agent_graph.py
git commit -m "refactor: route agent planning through intent decision"
```

## Task 3: BMAD Log And Regression

**Files:**
- Modify: `docs/bmad_development_log.md`

- [ ] **Step 1: Add BMAD log entry**

Append a new `Checkpoint 1` entry with the implemented files, scope, commands run, and the checkpoint commit hashes.

- [ ] **Step 2: Run regression**

Run:

```bash
python -m pytest apps/api/tests/test_agent_intent.py apps/api/tests/test_agent_graph.py apps/api/tests/test_agent_api.py::test_agent_run_unconfigured_model_answers_inventory_without_confirmation apps/api/tests/test_agent_api.py::test_agent_run_forces_unknown_fixed_workflow_into_incubation_without_production_task -q
git diff --check
```

Expected: all selected tests pass and diff check reports no whitespace errors.

- [ ] **Step 3: Commit**

Run:

```bash
git add docs/bmad_development_log.md
git commit -m "docs: log structured intent decision checkpoint"
```

## Self-Review

- Spec coverage: this plan covers the BMAD log's next iteration scope for `IntentDecision`, rule-first intent recognition, confidence gating, and LangGraph planner integration. It intentionally leaves full `ContextGrounder`, `StructuredIntentLLM`, policy snapshots, and loop budgets for later BMAD checkpoints.
- Placeholder scan: no `TBD`, `TODO`, or unspecified edge handling remains in the tasks.
- Type consistency: `normalize_intent_decision()` returns `(dict[str, Any], list[dict[str, Any]])`; `graph.py` consumes the same shape in `_plan()`.
