from __future__ import annotations

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


AGENT_RUN_CONTRACT_VERSION = "agent_run.v1"
AGENT_RUN_LOOKUP_CONTRACT_VERSION = "agent_run_lookup.v1"
PROJECT_AGENT_RUN_HISTORY_CONTRACT_VERSION = "project_agent_run_history.v1"
CHAT_COMPATIBILITY_CONTRACT_VERSION = "chat_compat.v1"


class AgentRunStatus(str, Enum):
    running = "running"
    answered = "answered"
    confirmation_required = "confirmation_required"
    needs_clarification = "needs_clarification"
    preflight_failed = "preflight_failed"
    toolchain_proposed = "toolchain_proposed"
    ready_to_launch = "ready_to_launch"
    task_created = "task_created"
    completed = "completed"
    blocked = "blocked"
    failed = "failed"
    cancelled = "cancelled"
    skipped = "skipped"


class AgentRunEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_type: str | None = None
    type: str | None = None
    status: str | None = None
    message: str | None = None
    task_id: int | None = None
    workflow_type: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: str | None = None


class AgentRunResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    contract_version: Literal["agent_run.v1"] = AGENT_RUN_CONTRACT_VERSION
    agent_run_id: str
    status: AgentRunStatus
    request_type: str | None = None
    thread_id: str | None = None
    project_id: int | None = None
    series_id: int | None = None
    task_id: int | None = None
    workflow_type: str | None = None
    intent: str | None = None
    action_lane: str | None = None
    selected_skill: str | None = None
    answer: str | None = None
    message: str | None = None
    confirmation: dict[str, Any] | None = None
    task: dict[str, Any] | None = None
    backend_tool: str | None = None
    tool_input: dict[str, Any] | None = None
    production_task_created: bool | None = None
    model_gateway_access: str | None = None
    safe_metadata: dict[str, Any] = Field(default_factory=dict)
    retrieved_sources: list[dict[str, Any]] = Field(default_factory=list)
    tool_invocations: list[dict[str, str]] = Field(default_factory=list)
    events: list[AgentRunEvent] = Field(default_factory=list)


class AgentRunLookupResponse(AgentRunResponse):
    contract_version: Literal["agent_run_lookup.v1"] = AGENT_RUN_LOOKUP_CONTRACT_VERSION


class ProjectAgentRunHistoryItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    agent_run_id: str
    request_type: str | None = None
    thread_id: str | None = None
    project_id: int | None = None
    series_id: int | None = None
    task_id: int | None = None
    workflow_type: str | None = None
    status: AgentRunStatus
    intent: str | None = None
    action_lane: str | None = None
    selected_skill: str | None = None
    approved: bool | None = None
    message_sha256: str | None = None
    model_gateway_access: str | None = None
    safe_metadata: dict[str, Any] = Field(default_factory=dict)
    event_count: int = 0
    created_at: str | None = None
    updated_at: str | None = None
    finished_at: str | None = None


class ProjectAgentRunHistoryResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    contract_version: Literal["project_agent_run_history.v1"] = PROJECT_AGENT_RUN_HISTORY_CONTRACT_VERSION
    project_id: int
    agent_runs: list[ProjectAgentRunHistoryItem] = Field(default_factory=list)


class ChatCompatibilityResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    contract_version: Literal["chat_compat.v1"] = CHAT_COMPATIBILITY_CONTRACT_VERSION
    legacy_endpoint: bool = True
    primary_endpoint: Literal["/agent/runs"] = "/agent/runs"
    reply: str
    references: list[dict[str, Any]] = Field(default_factory=list)
    provider: str
    provider_error: str = ""
    intent: str | None = None
    recommended_next_step: str | None = None
    tool_chain_hint: str | None = None
    tool_invocations: list[dict[str, Any]] = Field(default_factory=list)
    rag_mode: str | None = None


def normalize_agent_run_status(value: Any) -> tuple[str, str | None]:
    raw = str(value or "failed").strip() or "failed"
    allowed = {item.value for item in AgentRunStatus}
    if raw in allowed:
        return raw, None
    return AgentRunStatus.failed.value, raw


def normalize_agent_run_result(result: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(result)
    status, original = normalize_agent_run_status(normalized.get("status"))
    normalized["status"] = status
    if original:
        safe_metadata = normalized.get("safe_metadata") if isinstance(normalized.get("safe_metadata"), dict) else {}
        normalized["safe_metadata"] = {
            **safe_metadata,
            "contract_status_normalized_from": original,
        }
    return normalized


def build_agent_run_response_payload(
    result: dict[str, Any],
    *,
    ledger: dict[str, Any] | None = None,
    request_type: str | None = None,
    project_id: int | None = None,
    contract_version: str = AGENT_RUN_CONTRACT_VERSION,
) -> dict[str, Any]:
    ledger = ledger or {}
    status, original = normalize_agent_run_status(result.get("status") or ledger.get("status"))
    safe_metadata = _dict_value(ledger.get("safe_metadata")) or _dict_value(result.get("safe_metadata"))
    if original:
        safe_metadata = {**safe_metadata, "contract_status_normalized_from": original}
    payload = {
        "contract_version": contract_version,
        "agent_run_id": result.get("agent_run_id") or ledger.get("agent_run_id"),
        "status": status,
        "request_type": ledger.get("request_type") or request_type,
        "thread_id": result.get("thread_id") or ledger.get("thread_id"),
        "project_id": _first_value(
            result.get("project_id"),
            _dict_value(result.get("task")).get("project_id"),
            _dict_value(result.get("confirmation")).get("project_id"),
            ledger.get("project_id"),
            project_id,
        ),
        "series_id": _first_value(
            result.get("series_id"),
            _dict_value(result.get("task")).get("series_id"),
            _dict_value(result.get("confirmation")).get("series_id"),
            _dict_value(result.get("tool_input")).get("series_id"),
            ledger.get("series_id"),
        ),
        "task_id": _first_value(
            result.get("task_id"),
            _dict_value(result.get("task")).get("task_id"),
            _dict_value(result.get("task")).get("id"),
            ledger.get("task_id"),
        ),
        "workflow_type": _first_value(
            result.get("workflow_type"),
            _dict_value(result.get("task")).get("workflow_type"),
            _dict_value(result.get("confirmation")).get("workflow_type"),
            _dict_value(result.get("tool_input")).get("workflow_type"),
            ledger.get("workflow_type"),
        ),
        "intent": result.get("intent") or _dict_value(result.get("decision")).get("intent") or ledger.get("intent"),
        "action_lane": result.get("action_lane") or _dict_value(result.get("confirmation")).get("action_lane") or ledger.get("action_lane"),
        "selected_skill": result.get("selected_skill") or ledger.get("selected_skill"),
        "answer": result.get("answer"),
        "message": result.get("message"),
        "confirmation": _optional_dict(result.get("confirmation")),
        "task": _optional_dict(result.get("task")),
        "backend_tool": result.get("backend_tool"),
        "tool_input": _optional_dict(result.get("tool_input")),
        "production_task_created": result.get("production_task_created") if isinstance(result.get("production_task_created"), bool) else safe_metadata.get("production_task_created"),
        "model_gateway_access": ledger.get("model_gateway_access"),
        "safe_metadata": safe_metadata,
        "retrieved_sources": _list_value(ledger.get("retrieved_sources")),
        "tool_invocations": _list_value(ledger.get("tool_invocations")),
        "events": _list_value(result.get("events")) or _list_value(ledger.get("events")),
    }
    return {key: value for key, value in payload.items() if value is not None}


def build_project_agent_run_history_response(project_id: int, agent_runs: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "contract_version": PROJECT_AGENT_RUN_HISTORY_CONTRACT_VERSION,
        "project_id": project_id,
        "agent_runs": [
            {
                **item,
                "status": normalize_agent_run_status(item.get("status"))[0],
                "safe_metadata": _dict_value(item.get("safe_metadata")),
            }
            for item in agent_runs
        ],
    }


def build_chat_compatibility_response(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "contract_version": CHAT_COMPATIBILITY_CONTRACT_VERSION,
        "legacy_endpoint": True,
        "primary_endpoint": "/agent/runs",
        **payload,
    }


def _dict_value(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _optional_dict(value: Any) -> dict[str, Any] | None:
    return value if isinstance(value, dict) else None


def _list_value(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _first_value(*values: Any) -> Any:
    for value in values:
        if value is not None:
            return value
    return None
