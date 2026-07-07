from __future__ import annotations

import hashlib
import json
import re
import uuid
from typing import Any

from app.agent.thread_store import confirmation_fingerprint
from app.db.database import connect, now_iso


MODEL_GATEWAY_ACCESS = "openai_sdk_gateway"
SAFE_RETRIEVED_SOURCE_PREFIXES = ("docs/rag/", "docs/skills/")


def start_agent_run(
    *,
    request_type: str,
    project_id: int | None,
    message: str | None = None,
    thread_id: str | None = None,
    approved: bool | None = None,
    confirmation: dict[str, Any] | None = None,
) -> str:
    agent_run_id = f"agent_run_{uuid.uuid4().hex}"
    now = now_iso()
    fields = _extract_confirmation_fields(confirmation or {})
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO agent_runs(
              agent_run_id, request_type, thread_id, project_id, series_id,
              workflow_type, status, approved, message_sha256,
              model_gateway_access, safe_metadata_json, retrieved_sources_json,
              tool_invocations_json, created_at, updated_at
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                agent_run_id,
                request_type,
                thread_id,
                project_id if project_id is not None else fields.get("project_id"),
                fields.get("series_id"),
                fields.get("workflow_type"),
                "running",
                _bool_int(approved),
                _sha256(message) if message else None,
                MODEL_GATEWAY_ACCESS,
                _json(
                    {
                        "schema_version": 1,
                        "trace_kind": "privacy-safe lifecycle traceability",
                        "confirmation_fingerprint": (
                            confirmation_fingerprint(confirmation) if confirmation else None
                        ),
                    }
                ),
                "[]",
                "[]",
                now,
                now,
            ),
        )
        _append_event(conn, agent_run_id, event_type="agent_run_created", status="created", metadata={})
        _append_event(conn, agent_run_id, event_type="agent_run_started", status="running", metadata={})
    return agent_run_id


def finish_agent_run(
    agent_run_id: str,
    *,
    result: dict[str, Any] | None = None,
    error: BaseException | None = None,
) -> None:
    now = now_iso()
    if error is not None:
        status = "failed"
        event_type = "agent_run_failed"
        fields: dict[str, Any] = {}
        safe_metadata = {"schema_version": 1, "error_type": type(error).__name__}
        retrieved_sources: list[dict[str, Any]] = []
        tool_invocations: list[dict[str, Any]] = []
        error_message = _safe_error_message(str(error))
    else:
        result = result or {}
        status = str(result.get("status") or "completed")
        event_type = _terminal_event_type(status)
        fields = _extract_result_fields(result)
        retrieved_sources = _safe_retrieved_sources(result.get("retrieved_context"))
        tool_invocations = _safe_tool_invocations(result)
        safe_metadata = _safe_result_metadata(result)
        error_message = _safe_error_message(str(result.get("message") or "")) if status == "failed" else None

    with connect() as conn:
        conn.execute(
            """
            UPDATE agent_runs
            SET thread_id=COALESCE(?, thread_id),
                project_id=COALESCE(?, project_id),
                series_id=COALESCE(?, series_id),
                task_id=COALESCE(?, task_id),
                workflow_type=COALESCE(?, workflow_type),
                status=?,
                intent=COALESCE(?, intent),
                action_lane=COALESCE(?, action_lane),
                selected_skill=COALESCE(?, selected_skill),
                retrieved_sources_json=?,
                tool_invocations_json=?,
                safe_metadata_json=?,
                error_message=?,
                updated_at=?,
                finished_at=?
            WHERE agent_run_id=?
            """,
            (
                fields.get("thread_id"),
                fields.get("project_id"),
                fields.get("series_id"),
                fields.get("task_id"),
                fields.get("workflow_type"),
                status,
                fields.get("intent"),
                fields.get("action_lane"),
                fields.get("selected_skill"),
                _json(retrieved_sources),
                _json(tool_invocations),
                _json(safe_metadata),
                error_message,
                now,
                now,
                agent_run_id,
            ),
        )
        _append_event(
            conn,
            agent_run_id,
            event_type=event_type,
            status=status,
            metadata={
                key: value
                for key, value in {
                    "task_id": fields.get("task_id"),
                    "thread_id": fields.get("thread_id"),
                    "workflow_type": fields.get("workflow_type"),
                }.items()
                if value is not None
            },
        )


def load_agent_run(agent_run_id: str) -> dict[str, Any] | None:
    with connect() as conn:
        row = conn.execute("SELECT * FROM agent_runs WHERE agent_run_id=?", (agent_run_id,)).fetchone()
        if row is None:
            return None
        events = conn.execute(
            """
            SELECT event_type, status, metadata_json, created_at
            FROM agent_run_events
            WHERE agent_run_id=?
            ORDER BY id
            """,
            (agent_run_id,),
        ).fetchall()

    result = dict(row)
    result["approved"] = _bool_or_none(result.get("approved"))
    result["error_message"] = _safe_error_message(str(result.get("error_message") or "")) if result.get("error_message") else None
    result["retrieved_sources"] = _sanitize_retrieved_sources(_loads_json_list(result.pop("retrieved_sources_json", "[]")))
    result["tool_invocations"] = _sanitize_tool_invocations(_loads_json_list(result.pop("tool_invocations_json", "[]")))
    result["safe_metadata"] = _sanitize_safe_metadata(_loads_json_dict(result.pop("safe_metadata_json", "{}")))
    result["events"] = [
        {
            "event_type": event["event_type"],
            "status": event["status"],
            "metadata": _sanitize_event_metadata(_loads_json_dict(event["metadata_json"])),
            "created_at": event["created_at"],
        }
        for event in events
    ]
    return result


def list_project_agent_runs(project_id: int, *, limit: int = 50) -> list[dict[str, Any]]:
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT
              agent_runs.agent_run_id,
              agent_runs.request_type,
              agent_runs.thread_id,
              agent_runs.project_id,
              agent_runs.series_id,
              agent_runs.task_id,
              agent_runs.workflow_type,
              agent_runs.status,
              agent_runs.intent,
              agent_runs.action_lane,
              agent_runs.selected_skill,
              agent_runs.approved,
              agent_runs.message_sha256,
              agent_runs.model_gateway_access,
              agent_runs.safe_metadata_json,
              agent_runs.created_at,
              agent_runs.updated_at,
              agent_runs.finished_at,
              COUNT(agent_run_events.id) AS event_count
            FROM agent_runs
            LEFT JOIN agent_run_events ON agent_run_events.agent_run_id = agent_runs.agent_run_id
            WHERE agent_runs.project_id=?
            GROUP BY agent_runs.agent_run_id
            ORDER BY agent_runs.created_at DESC
            LIMIT ?
            """,
            (project_id, limit),
        ).fetchall()

    results = []
    for row in rows:
        item = dict(row)
        item["approved"] = _bool_or_none(item.get("approved"))
        item["event_count"] = int(item.get("event_count") or 0)
        item["safe_metadata"] = _sanitize_safe_metadata(_loads_json_dict(item.pop("safe_metadata_json", "{}")))
        results.append(item)
    return results


def _append_event(conn: Any, agent_run_id: str, *, event_type: str, status: str, metadata: dict[str, Any]) -> None:
    conn.execute(
        """
        INSERT INTO agent_run_events(agent_run_id, event_type, status, metadata_json, created_at)
        VALUES(?,?,?,?,?)
        """,
        (agent_run_id, event_type, status, _json(metadata), now_iso()),
    )


def _extract_confirmation_fields(confirmation: dict[str, Any]) -> dict[str, Any]:
    return {
        "project_id": _int_or_none(confirmation.get("project_id")),
        "series_id": _int_or_none(confirmation.get("series_id")),
        "workflow_type": _str_or_none(confirmation.get("workflow_type")),
    }


def _extract_result_fields(result: dict[str, Any]) -> dict[str, Any]:
    confirmation = result.get("confirmation") if isinstance(result.get("confirmation"), dict) else {}
    decision = result.get("decision") if isinstance(result.get("decision"), dict) else {}
    task = result.get("task") if isinstance(result.get("task"), dict) else {}
    tool_input = result.get("tool_input") if isinstance(result.get("tool_input"), dict) else {}
    return {
        "thread_id": _str_or_none(result.get("thread_id")),
        "project_id": _first_int(task.get("project_id"), confirmation.get("project_id"), tool_input.get("project_id")),
        "series_id": _first_int(task.get("series_id"), confirmation.get("series_id"), tool_input.get("series_id"), decision.get("series_id")),
        "task_id": _first_int(task.get("id"), task.get("task_id"), result.get("task_id")),
        "workflow_type": _first_str(task.get("workflow_type"), confirmation.get("workflow_type"), tool_input.get("workflow_type"), decision.get("workflow_type")),
        "intent": _first_str(result.get("intent"), decision.get("intent")),
        "action_lane": _first_str(result.get("action_lane"), confirmation.get("action_lane"), decision.get("action_lane")),
        "selected_skill": _str_or_none(result.get("selected_skill")),
    }


def _safe_result_metadata(result: dict[str, Any]) -> dict[str, Any]:
    retrieved_context = result.get("retrieved_context") if isinstance(result.get("retrieved_context"), dict) else {}
    metadata = {
        "schema_version": 1,
        "trace_kind": "privacy-safe lifecycle traceability",
        "rag_mode": retrieved_context.get("mode"),
        "production_task_created": result.get("production_task_created"),
    }
    confirmation = result.get("confirmation") if isinstance(result.get("confirmation"), dict) else None
    if confirmation:
        metadata["confirmation_fingerprint"] = confirmation_fingerprint(confirmation)
    safe_metadata = result.get("safe_metadata") if isinstance(result.get("safe_metadata"), dict) else {}
    fallback_reason = _safe_symbol_value(safe_metadata.get("fallback_reason"))
    if fallback_reason:
        metadata["fallback_reason"] = fallback_reason
    normalized_from = _safe_symbol_value(safe_metadata.get("contract_status_normalized_from"))
    if normalized_from:
        metadata["contract_status_normalized_from"] = normalized_from
    for key in (
        "agent_engine",
        "graph_runtime",
        "lane",
        "confirmation_gate",
        "response_source",
        "runtime_reporter",
        "t1_metric_interpreter",
    ):
        safe_value = _safe_symbol_value(safe_metadata.get(key))
        if safe_value:
            metadata[key] = safe_value
    return {key: value for key, value in metadata.items() if value is not None}


def _safe_retrieved_sources(retrieved_context: Any) -> list[dict[str, Any]]:
    if not isinstance(retrieved_context, dict):
        return []
    sources: list[dict[str, Any]] = []
    for hit in retrieved_context.get("results") or []:
        if not isinstance(hit, dict):
            continue
        metadata = hit.get("metadata") if isinstance(hit.get("metadata"), dict) else {}
        source = _safe_source_path(hit.get("source") or hit.get("path"))
        if not source:
            continue
        item = {
            "source": source,
            "source_type": _safe_symbol_value(metadata.get("source_type")),
        }
        sources.append({key: value for key, value in item.items() if value})
    return sources[:20]


def _safe_tool_invocations(result: dict[str, Any]) -> list[dict[str, Any]]:
    combined = []
    for key in ("tool_invocations", "tool_trace"):
        value = result.get(key)
        if isinstance(value, list):
            combined.extend(value)
    return _sanitize_tool_invocations(combined)


def _terminal_event_type(status: str) -> str:
    if status == "cancelled":
        return "agent_run_cancelled"
    if status == "skipped":
        return "agent_run_skipped"
    if status == "failed":
        return "agent_run_failed"
    return "agent_run_completed"


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _safe_error_message(value: str) -> str | None:
    value = value.strip()
    if not value:
        return None
    return "redacted_error_summary"


def _sanitize_retrieved_sources(value: list[dict[str, Any]]) -> list[dict[str, str]]:
    sources: list[dict[str, str]] = []
    for hit in value:
        source = _safe_source_path(hit.get("source") or hit.get("path"))
        if not source:
            continue
        item = {
            "source": source,
            "source_type": _safe_symbol_value(hit.get("source_type")),
        }
        sources.append({key: val for key, val in item.items() if val})
    return sources[:20]


def _sanitize_tool_invocations(value: list[Any]) -> list[dict[str, str]]:
    safe = []
    allowed = {"stage", "tool", "name", "status", "mode", "type"}
    for item in value:
        if not isinstance(item, dict):
            continue
        sanitized = {
            key: parsed
            for key, raw in item.items()
            if key in allowed
            for parsed in [_safe_symbol_value(raw)]
            if parsed is not None
        }
        if sanitized:
            safe.append(sanitized)
    return safe[:50]


def _sanitize_safe_metadata(value: dict[str, Any]) -> dict[str, Any]:
    safe: dict[str, Any] = {}
    if isinstance(value.get("schema_version"), int):
        safe["schema_version"] = value["schema_version"]
    if value.get("trace_kind") == "privacy-safe lifecycle traceability":
        safe["trace_kind"] = "privacy-safe lifecycle traceability"
    rag_mode = _safe_symbol_value(value.get("rag_mode"))
    if rag_mode:
        safe["rag_mode"] = rag_mode
    if isinstance(value.get("production_task_created"), bool):
        safe["production_task_created"] = value["production_task_created"]
    fallback_reason = _safe_symbol_value(value.get("fallback_reason"))
    if fallback_reason:
        safe["fallback_reason"] = fallback_reason
    fingerprint = _str_or_none(value.get("confirmation_fingerprint"))
    if fingerprint and re.fullmatch(r"[a-f0-9]{64}", fingerprint):
        safe["confirmation_fingerprint"] = fingerprint
    error_type = _safe_symbol_value(value.get("error_type"))
    if error_type:
        safe["error_type"] = error_type
    normalized_from = _safe_symbol_value(value.get("contract_status_normalized_from"))
    if normalized_from:
        safe["contract_status_normalized_from"] = normalized_from
    for key in (
        "agent_engine",
        "graph_runtime",
        "lane",
        "confirmation_gate",
        "response_source",
        "runtime_reporter",
        "t1_metric_interpreter",
    ):
        safe_value = _safe_symbol_value(value.get(key))
        if safe_value:
            safe[key] = safe_value
    return safe


def _sanitize_event_metadata(value: dict[str, Any]) -> dict[str, Any]:
    safe: dict[str, Any] = {}
    task_id = _int_or_none(value.get("task_id"))
    if task_id is not None:
        safe["task_id"] = task_id
    thread_id = _safe_symbol_value(value.get("thread_id"), max_length=140)
    if thread_id:
        safe["thread_id"] = thread_id
    workflow_type = _safe_symbol_value(value.get("workflow_type"))
    if workflow_type:
        safe["workflow_type"] = workflow_type
    return safe


def _safe_source_path(value: Any) -> str | None:
    source = _str_or_none(value)
    if not source:
        return None
    normalized = source.replace("\\", "/")
    if re.match(r"^[A-Za-z]:/", normalized):
        return None
    if normalized.startswith("/"):
        return None
    if ".." in normalized.split("/"):
        return None
    if not re.fullmatch(r"[A-Za-z0-9_./-]+", normalized):
        return None
    if not any(normalized.startswith(prefix) for prefix in SAFE_RETRIEVED_SOURCE_PREFIXES):
        return None
    return normalized


def _safe_symbol_value(value: Any, *, max_length: int = 80) -> str | None:
    text = _str_or_none(value)
    if not text or len(text) > max_length:
        return None
    if not re.fullmatch(r"[A-Za-z0-9_.-]+", text):
        return None
    return text


def _bool_int(value: bool | None) -> int | None:
    if value is None:
        return None
    return 1 if value else 0


def _bool_or_none(value: Any) -> bool | None:
    if value is None:
        return None
    return bool(value)


def _loads_json_list(value: Any) -> list[dict[str, Any]]:
    try:
        parsed = json.loads(value or "[]")
    except (TypeError, json.JSONDecodeError):
        return []
    if not isinstance(parsed, list):
        return []
    return [item for item in parsed if isinstance(item, dict)]


def _loads_json_dict(value: Any) -> dict[str, Any]:
    try:
        parsed = json.loads(value or "{}")
    except (TypeError, json.JSONDecodeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _int_or_none(value: Any) -> int | None:
    try:
        if value is None or value == "":
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def _str_or_none(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _first_int(*values: Any) -> int | None:
    for value in values:
        parsed = _int_or_none(value)
        if parsed is not None:
            return parsed
    return None


def _first_str(*values: Any) -> str | None:
    for value in values:
        parsed = _str_or_none(value)
        if parsed:
            return parsed
    return None
