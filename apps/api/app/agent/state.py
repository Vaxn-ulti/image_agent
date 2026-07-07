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


class ImageAgentState(TypedDict, total=False):
    thread_id: str
    project_id: int | None
    message: str
    intent: str
    lane: str | None
    router_lane: str | None
    risk_assessment: dict[str, Any]
    task_planning: dict[str, Any]
    requirement_completeness: dict[str, Any]
    neuroimaging_intake: dict[str, Any]
    sequence_normalization: dict[str, Any]
    curated_workflow_registry: dict[str, Any]
    capability_matcher: dict[str, Any]
    fixed_workflow_recommendation: dict[str, Any]
    execution_plan_candidate: dict[str, Any]
    plan_policy_gate: dict[str, Any]
    project_context: dict[str, Any]
    workflow_registry: list[dict[str, Any]]
    deployment_status: dict[str, Any]
    decision: dict[str, Any]
    rule_intent_signal: dict[str, Any]
    llm_intent_signal: dict[str, Any]
    intent_decision: dict[str, Any]
    planner_tool_trace: list[dict[str, Any]]
    skill_context: dict[str, Any]
    retrieved_context: dict[str, Any]
    selected_skill: str | None
    workflow_match: dict[str, Any] | None
    preflight: dict[str, Any] | None
    confirmation: dict[str, Any] | None
    confirmation_fingerprint: str | None
    approved: bool | None
    proposal: dict[str, Any] | None
    promotion_review: dict[str, Any] | None
    task: dict[str, Any] | None
    task_observation: dict[str, Any] | None
    result_summary: dict[str, Any] | None
    repair_plan: dict[str, Any] | None
    answer: str | None
    result: dict[str, Any]
    events: list[dict[str, Any]]
    production_task_created: bool


IMAGE_AGENT_STATE_FIELDS = list(ImageAgentState.__annotations__.keys())
