from __future__ import annotations

from enum import Enum
import re
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


AGENT_RUN_CONTRACT_VERSION = "agent_run.v1"
AGENT_RUN_LOOKUP_CONTRACT_VERSION = "agent_run_lookup.v1"
PROJECT_AGENT_RUN_HISTORY_CONTRACT_VERSION = "project_agent_run_history.v1"
AGENT_API_ERROR_CONTRACT_VERSION = "agent_api_error.v1"
SAFE_NESTED_AGENT_FIELDS = {
    "confirmation": {
        "type",
        "action_lane",
        "title",
        "project_id",
        "series_id",
        "workflow_type",
        "runtime_workflow_type",
        "fingerprint",
        "confirmation_fingerprint",
        "workflow_metadata",
        "qsiprep_task_id",
        "summary",
        "risks",
        "preflight",
        "data_candidate_selection",
    },
    "task": {
        "id",
        "task_id",
        "project_id",
        "series_id",
        "workflow_type",
        "runtime_workflow_type",
        "status",
        "progress",
        "created_at",
        "started_at",
        "finished_at",
    },
    "tool_input": {
        "project_id",
        "series_id",
        "task_id",
        "workflow_type",
        "runtime_workflow_type",
        "qsiprep_task_id",
        "approved",
        "action_lane",
    },
}
HOST_PATH_PLACEHOLDER = "[redacted-host-path]"
SECRET_PLACEHOLDER = "[redacted-secret]"
_WINDOWS_HOST_PATH_RE = re.compile(r"[A-Za-z]:[\\/][^\s`\"')\]}]+")
_UNIX_HOST_PATH_RE = re.compile(r"/(?:home|Users|mnt|data|tmp|var|srv)/[^\s`\"')\]}]+")
_RELATIVE_PROJECT_PATH_RE = re.compile(r"(^|[\s`\"'(\[{])data[\\/]+projects[\\/]+[^\s`\"')\]}]+")
_SECRET_RE = re.compile(r"sk-[A-Za-z0-9._-]+")
_ENV_SECRET_RE = re.compile(r"((?:OPENAI|DEEPSEEK|IMAGE_AGENT_SUDO)_?[A-Z_]*\s*[:=]\s*)[^\s\"',}]+", re.IGNORECASE)


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
    runtime_workflow_type: str | None = None
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
    runtime_workflow_type: str | None = None
    intent: str | None = None
    action_lane: str | None = None
    selected_skill: str | None = None
    response_source: str | None = None
    answer: str | None = None
    message: str | None = None
    confirmation: dict[str, Any] | None = None
    task: dict[str, Any] | None = None
    proposed_toolchain: dict[str, Any] | None = None
    task_observation: dict[str, Any] | None = None
    repair_plan: dict[str, Any] | None = None
    backend_tool: str | None = None
    tool_input: dict[str, Any] | None = None
    production_task_created: bool | None = None
    task_creation_allowed: bool | None = None
    forbidden_actions: list[str] = Field(default_factory=list)
    model_gateway_access: str | None = None
    safe_metadata: dict[str, Any] = Field(default_factory=dict)
    retrieved_sources: list[dict[str, Any]] = Field(default_factory=list)
    tool_invocations: list[dict[str, str]] = Field(default_factory=list)
    events: list[AgentRunEvent] = Field(default_factory=list)


class AgentRunLookupResponse(AgentRunResponse):
    contract_version: Literal["agent_run_lookup.v1"] = AGENT_RUN_LOOKUP_CONTRACT_VERSION
    message_sha256: str | None = None
    error_message: str | None = None
    created_at: str | None = None
    updated_at: str | None = None
    finished_at: str | None = None


class AgentApiErrorDetail(BaseModel):
    model_config = ConfigDict(extra="forbid")

    contract_version: Literal["agent_api_error.v1"] = AGENT_API_ERROR_CONTRACT_VERSION
    code: str
    message: str
    agent_run_id: str | None = None


class AgentApiErrorResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    detail: AgentApiErrorDetail


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
    proposed_toolchain = _optional_dict(result.get("proposed_toolchain"))
    task_creation_allowed = result.get("task_creation_allowed")
    if not isinstance(task_creation_allowed, bool) and proposed_toolchain:
        task_creation_allowed = proposed_toolchain.get("task_creation_allowed")
    forbidden_actions = result.get("forbidden_actions")
    if not isinstance(forbidden_actions, list) and proposed_toolchain:
        forbidden_actions = proposed_toolchain.get("forbidden_actions")
    response_source = _response_source(result, safe_metadata)
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
        "runtime_workflow_type": _first_value(
            result.get("runtime_workflow_type"),
            _dict_value(result.get("task")).get("runtime_workflow_type"),
            _dict_value(result.get("confirmation")).get("runtime_workflow_type"),
            _dict_value(result.get("tool_input")).get("runtime_workflow_type"),
            ledger.get("runtime_workflow_type"),
        ),
        "intent": result.get("intent") or _dict_value(result.get("decision")).get("intent") or ledger.get("intent"),
        "action_lane": result.get("action_lane") or _dict_value(result.get("confirmation")).get("action_lane") or ledger.get("action_lane"),
        "selected_skill": result.get("selected_skill") or ledger.get("selected_skill"),
        "response_source": response_source,
        "answer": result.get("answer"),
        "message": result.get("message"),
        "confirmation": _optional_safe_nested_dict("confirmation", result.get("confirmation")),
        "task": _optional_safe_nested_dict("task", result.get("task")),
        "proposed_toolchain": proposed_toolchain,
        "task_observation": _optional_dict(result.get("task_observation")),
        "repair_plan": _optional_dict(result.get("repair_plan")),
        "backend_tool": result.get("backend_tool"),
        "tool_input": _optional_safe_nested_dict("tool_input", result.get("tool_input")),
        "production_task_created": result.get("production_task_created") if isinstance(result.get("production_task_created"), bool) else safe_metadata.get("production_task_created"),
        "task_creation_allowed": task_creation_allowed if isinstance(task_creation_allowed, bool) else None,
        "forbidden_actions": forbidden_actions if isinstance(forbidden_actions, list) else [],
        "model_gateway_access": ledger.get("model_gateway_access"),
        "safe_metadata": safe_metadata,
        "retrieved_sources": _list_value(ledger.get("retrieved_sources")),
        "tool_invocations": _list_value(ledger.get("tool_invocations")),
        "events": _list_value(result.get("events")) or _list_value(ledger.get("events")),
    }
    if contract_version == AGENT_RUN_LOOKUP_CONTRACT_VERSION:
        payload.update(
            {
                "message_sha256": ledger.get("message_sha256"),
                "error_message": ledger.get("error_message"),
                "created_at": ledger.get("created_at"),
                "updated_at": ledger.get("updated_at"),
                "finished_at": ledger.get("finished_at"),
            }
        )
    return {key: _sanitize_public_value(value) for key, value in payload.items() if value is not None}


def _response_source(result: dict[str, Any], safe_metadata: dict[str, Any]) -> str | None:
    explicit = _safe_symbol(str(result.get("response_source") or safe_metadata.get("response_source") or ""))
    if explicit:
        return explicit
    selected_skill = str(result.get("selected_skill") or "")
    fallback_reason = str(safe_metadata.get("fallback_reason") or "")
    rag_mode = str(safe_metadata.get("rag_mode") or "")
    if fallback_reason == "model_gateway_unconfigured":
        if rag_mode:
            return "rag_fallback"
        if selected_skill == "backend-context-fallback":
            return "backend_context"
        return "backend_context"
    if safe_metadata.get("agent_engine") == "langgraph":
        return "model_gateway"
    if result.get("task"):
        return "workflow_engine"
    return None


def _safe_symbol(value: str) -> str | None:
    normalized = value.strip().lower().replace("-", "_")
    if normalized and len(normalized) <= 80 and all(char.isalnum() or char == "_" for char in normalized):
        return normalized
    return None


def agent_api_error_detail(code: str, message: str, *, agent_run_id: str | None = None) -> dict[str, Any]:
    return AgentApiErrorDetail(
        code=code,
        message=message,
        agent_run_id=agent_run_id,
    ).model_dump(exclude_none=True)


def build_project_agent_run_history_response(project_id: int, agent_runs: list[dict[str, Any]]) -> dict[str, Any]:
    def history_item(item: dict[str, Any]) -> dict[str, Any]:
        status, original = normalize_agent_run_status(item.get("status"))
        safe_metadata = _dict_value(item.get("safe_metadata"))
        if original:
            safe_metadata = {**safe_metadata, "contract_status_normalized_from": original}
        return {
            **item,
            "status": status,
            "safe_metadata": safe_metadata,
        }

    return {
        "contract_version": PROJECT_AGENT_RUN_HISTORY_CONTRACT_VERSION,
        "project_id": project_id,
        "agent_runs": [history_item(item) for item in agent_runs],
    }

def _dict_value(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _optional_dict(value: Any) -> dict[str, Any] | None:
    return value if isinstance(value, dict) else None


def _optional_safe_nested_dict(kind: str, value: Any) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    allowed = SAFE_NESTED_AGENT_FIELDS.get(kind, set())
    safe = {
        key: _sanitize_public_value(nested_value)
        for key, nested_value in value.items()
        if key in allowed
    }
    return safe or None


def _sanitize_public_value(value: Any) -> Any:
    if isinstance(value, str):
        return _redact_public_text(value)
    if isinstance(value, list):
        return [_sanitize_public_value(item) for item in value]
    if isinstance(value, dict):
        return {
            key: _sanitize_public_value(item)
            for key, item in value.items()
            if isinstance(key, str) and not _is_sensitive_public_key(key)
        }
    return value


def _redact_public_text(value: str) -> str:
    text = _WINDOWS_HOST_PATH_RE.sub(HOST_PATH_PLACEHOLDER, value)
    text = _UNIX_HOST_PATH_RE.sub(HOST_PATH_PLACEHOLDER, text)
    text = _RELATIVE_PROJECT_PATH_RE.sub(lambda match: f"{match.group(1)}{HOST_PATH_PLACEHOLDER}", text)
    text = _SECRET_RE.sub(SECRET_PLACEHOLDER, text)
    return _ENV_SECRET_RE.sub(lambda match: f"{match.group(1)}{SECRET_PLACEHOLDER}", text)


def _is_sensitive_public_key(key: str) -> bool:
    normalized = key.lower()
    return normalized in {"openai_key", "api_key", "secret", "token", "password"}


def _is_safe_nested_scalar(value: Any) -> bool:
    if value is None or isinstance(value, (bool, int, float)):
        return True
    if isinstance(value, str):
        return _is_safe_nested_string(value)
    if isinstance(value, list):
        return all(_is_safe_nested_string(item) for item in value)
    return False


def _is_safe_nested_string(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    normalized = value.replace("\\", "/")
    if normalized.startswith("/") or ".." in normalized.split("/"):
        return False
    if len(normalized) >= 3 and normalized[1:3] == ":/":
        return False
    if normalized.startswith("data/projects/") or "/data/projects/" in normalized:
        return False
    return True


def _list_value(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _first_value(*values: Any) -> Any:
    for value in values:
        if value is not None:
            return value
    return None
