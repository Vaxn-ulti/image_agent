from __future__ import annotations

from typing import Any, TypedDict


class AgentState(TypedDict, total=False):
    messages: list[dict[str, Any]]
    project_id: int | None
    user_intent: str
    action_lane: str | None
    project_context: dict[str, Any]
    retrieved_context: list[dict[str, Any]]
    selected_skill: str | None
    selected_workflow_type: str | None
    data_candidate_selection: dict[str, Any] | None
    proposed_toolchain: dict[str, Any] | None
    composition_plan: dict[str, Any] | None
    promotion_gate: dict[str, Any] | None
    preflight: dict[str, Any] | None
    pending_confirmation: dict[str, Any] | None
    confirmation_result: dict[str, Any] | None
    task_ids: list[int]
    task_status: dict[str, Any] | None
    result_summary: dict[str, Any] | None
    final_answer: str | None
    safety_flags: list[str]


AGENT_STATE_FIELDS = list(AgentState.__annotations__.keys())
