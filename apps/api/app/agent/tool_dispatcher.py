from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

from app.agent import tools
from app.agent.rag_orchestration import retrieve_reference_context
from app.agent.tool_registry import list_function_tools


RowsFn = Callable[[str, tuple[Any, ...]], list[dict[str, Any]]]


def _allowed_tool_names() -> set[str]:
    return {tool["name"] for tool in list_function_tools()}


def _tool_schema(tool_name: str) -> dict[str, Any] | None:
    for tool in list_function_tools():
        if tool["name"] == tool_name:
            return tool.get("parameters") if isinstance(tool.get("parameters"), dict) else None
    return None


def _parse_arguments(arguments: Any) -> dict[str, Any]:
    if arguments is None:
        return {}
    if isinstance(arguments, dict):
        return arguments
    if isinstance(arguments, str):
        if not arguments.strip():
            return {}
        parsed = json.loads(arguments)
        if not isinstance(parsed, dict):
            raise ValueError("Tool call arguments must decode to a JSON object")
        return parsed
    raise ValueError("Tool call arguments must be a JSON object or JSON string")


def _unknown_argument_names(tool_name: str, args: dict[str, Any]) -> list[str]:
    schema = _tool_schema(tool_name) or {}
    properties = schema.get("properties")
    if not isinstance(properties, dict):
        return []
    allowed = set(properties)
    return sorted(key for key in args if key not in allowed)


def _missing_required_argument_names(tool_name: str, args: dict[str, Any]) -> list[str]:
    schema = _tool_schema(tool_name) or {}
    required = schema.get("required")
    if not isinstance(required, list):
        return []
    return sorted(str(key) for key in required if str(key) not in args or args.get(str(key)) is None)


def _invalid_argument_type_messages(tool_name: str, args: dict[str, Any]) -> list[str]:
    schema = _tool_schema(tool_name) or {}
    properties = schema.get("properties")
    if not isinstance(properties, dict):
        return []
    messages = []
    for key, value in args.items():
        property_schema = properties.get(key)
        if isinstance(property_schema, dict) and not _value_matches_schema(value, property_schema):
            messages.append(f"{key} expected {_schema_type_label(property_schema)}")
    return sorted(messages)


def _invalid_argument_value_messages(tool_name: str, args: dict[str, Any]) -> list[str]:
    schema = _tool_schema(tool_name) or {}
    properties = schema.get("properties")
    if not isinstance(properties, dict):
        return []
    messages = []
    for key, value in args.items():
        property_schema = properties.get(key)
        if isinstance(property_schema, dict) and not _value_matches_enum(value, property_schema):
            messages.append(f"{key} expected one of {_schema_enum_label(property_schema)}")
    return sorted(messages)


def _value_matches_schema(value: Any, schema: dict[str, Any]) -> bool:
    if "oneOf" in schema:
        return any(
            isinstance(option, dict) and _value_matches_schema(value, option)
            for option in schema.get("oneOf") or []
        )
    schema_type = schema.get("type")
    if isinstance(schema_type, list):
        return any(_value_matches_type(value, item, schema) for item in schema_type)
    return _value_matches_type(value, schema_type, schema)


def _value_matches_type(value: Any, schema_type: Any, schema: dict[str, Any]) -> bool:
    if schema_type == "null":
        return value is None
    if schema_type == "integer":
        return type(value) is int
    if schema_type == "number":
        return (type(value) is int or type(value) is float) and not isinstance(value, bool)
    if schema_type == "string":
        return isinstance(value, str)
    if schema_type == "boolean":
        return type(value) is bool
    if schema_type == "object":
        return isinstance(value, dict)
    if schema_type == "array":
        if not isinstance(value, list):
            return False
        item_schema = schema.get("items")
        if not isinstance(item_schema, dict):
            return True
        return all(_value_matches_schema(item, item_schema) for item in value)
    return True


def _value_matches_enum(value: Any, schema: dict[str, Any]) -> bool:
    if "oneOf" in schema:
        return any(
            isinstance(option, dict) and _value_matches_enum(value, option)
            for option in schema.get("oneOf") or []
        )
    allowed_values = schema.get("enum")
    if isinstance(allowed_values, list):
        return value in allowed_values
    return True


def _schema_type_label(schema: dict[str, Any]) -> str:
    if "oneOf" in schema:
        labels = [
            _schema_type_label(option)
            for option in schema.get("oneOf") or []
            if isinstance(option, dict)
        ]
        return " or ".join(labels) or "valid schema value"
    schema_type = schema.get("type")
    if isinstance(schema_type, list):
        return " or ".join(str(item) for item in schema_type)
    return str(schema_type or "valid schema value")


def _schema_enum_label(schema: dict[str, Any]) -> str:
    if "oneOf" in schema:
        labels = [
            _schema_enum_label(option)
            for option in schema.get("oneOf") or []
            if isinstance(option, dict)
        ]
        return " or ".join(label for label in labels if label) or "allowed values"
    allowed_values = schema.get("enum")
    if isinstance(allowed_values, list):
        return ", ".join(repr(value) for value in allowed_values)
    return "allowed values"


def _blocked_result(tool_name: str, message: str, *, call_id: str | None = None) -> dict[str, Any]:
    return {
        "status": "blocked",
        "tool": tool_name,
        "call_id": call_id,
        "message": message,
        "production_task_created": False,
    }


def _ok_result(tool_name: str, result: Any, *, call_id: str | None = None) -> dict[str, Any]:
    return {
        "status": "ok",
        "tool": tool_name,
        "call_id": call_id,
        "result": result,
        "production_task_created": False,
    }


def dispatch_tool_call(
    tool_name: str,
    arguments: dict[str, Any] | str | None = None,
    *,
    call_id: str | None = None,
    project_context: dict[str, Any] | None = None,
    rows_fn: RowsFn | None = None,
    workflows: list[dict[str, Any]] | None = None,
    rag_root: Path | str | None = None,
    projects_root: Path | str | None = None,
    allow_production_task_creation: bool = False,
    create_task_fn: Any | None = None,
) -> dict[str, Any]:
    """Execute one OpenAI-style function tool call through backend guardrails."""

    if tool_name not in _allowed_tool_names():
        return _blocked_result(tool_name, f"Tool is not registered for image_agent: {tool_name}", call_id=call_id)
    try:
        args = _parse_arguments(arguments)
    except (json.JSONDecodeError, ValueError) as exc:
        return _blocked_result(tool_name, f"Invalid tool arguments: {exc}", call_id=call_id)
    unknown_arguments = _unknown_argument_names(tool_name, args)
    if unknown_arguments:
        return _blocked_result(
            tool_name,
            "Unknown tool argument(s): " + ", ".join(unknown_arguments),
            call_id=call_id,
        )
    missing_arguments = _missing_required_argument_names(tool_name, args)
    if missing_arguments:
        return _blocked_result(
            tool_name,
            "Missing required tool argument(s): " + ", ".join(missing_arguments),
            call_id=call_id,
        )
    invalid_type_messages = _invalid_argument_type_messages(tool_name, args)
    if invalid_type_messages:
        return _blocked_result(
            tool_name,
            "Invalid tool argument type(s): " + "; ".join(invalid_type_messages),
            call_id=call_id,
        )
    invalid_value_messages = _invalid_argument_value_messages(tool_name, args)
    if invalid_value_messages:
        return _blocked_result(
            tool_name,
            "Invalid tool argument value(s): " + "; ".join(invalid_value_messages),
            call_id=call_id,
        )

    try:
        if tool_name == "list_workflows":
            return _ok_result(
                tool_name,
                tools.list_workflows(
                    workflows=workflows,
                    lane=args.get("lane"),
                    agent_selectable=args.get("agent_selectable"),
                ),
                call_id=call_id,
            )
        if tool_name == "preflight_workflow":
            if project_context is None:
                return _blocked_result(tool_name, "project_context is required for preflight_workflow", call_id=call_id)
            return _ok_result(
                tool_name,
                tools.preflight_workflow(
                    project_context,
                    series_id=int(args["series_id"]),
                    workflow_type=str(args["workflow_type"]),
                ),
                call_id=call_id,
            )
        if tool_name == "retrieve_reference_context":
            return _ok_result(
                tool_name,
                retrieve_reference_context(
                    str(args["query"]),
                    root=rag_root,
                    filters=args.get("filters"),
                    limit=int(args.get("limit") or 5),
                ),
                call_id=call_id,
            )
        if tool_name in {"list_data_candidates", "select_incubation_dataset"} and rows_fn is None:
            return _blocked_result(tool_name, "rows_fn is required for database-backed data candidate tools", call_id=call_id)
        if tool_name == "list_data_candidates":
            return _ok_result(
                tool_name,
                tools.list_data_candidates(
                    args.get("project_id"),
                    rows_fn=rows_fn,  # type: ignore[arg-type]
                    projects_root=Path(projects_root) if projects_root is not None else None,
                    modality=args.get("modality"),
                    workflow_type=args.get("workflow_type"),
                    limit=int(args.get("limit") or 50),
                ),
                call_id=call_id,
            )
        if tool_name == "select_incubation_dataset":
            return _ok_result(
                tool_name,
                tools.select_incubation_dataset(
                    args.get("project_id"),
                    rows_fn=rows_fn,  # type: ignore[arg-type]
                    projects_root=Path(projects_root) if projects_root is not None else None,
                    modality=args.get("modality"),
                    workflow_type=args.get("workflow_type"),
                ),
                call_id=call_id,
            )
        if tool_name == "propose_toolchain":
            return _ok_result(
                tool_name,
                tools.propose_toolchain(
                    objective=str(args["objective"]),
                    input_modality=args.get("input_modality"),
                    primitives=args.get("primitives"),
                    script_paths=args.get("script_paths"),
                    script_text=args.get("script_text"),
                    known_script_roots=args.get("known_script_roots"),
                ),
                call_id=call_id,
            )
        if tool_name == "sandbox_validate_toolchain":
            return _ok_result(tool_name, tools.sandbox_validate_toolchain(args["proposal"]), call_id=call_id)
        if tool_name == "promote_toolchain_to_workflow":
            return _ok_result(
                tool_name,
                tools.promote_toolchain_to_workflow(args["proposal"], approved=bool(args.get("approved"))),
                call_id=call_id,
            )
        if tool_name in {"read_project_context", "read_task", "read_task_events", "read_result_summary", "observe_repair_task"} and rows_fn is None:
            return _blocked_result(tool_name, "rows_fn is required for database-backed read tools", call_id=call_id)
        if tool_name == "read_project_context":
            return _ok_result(
                tool_name,
                tools.read_project_context(
                    args.get("project_id"),
                    rows_fn=rows_fn,  # type: ignore[arg-type]
                    workflows=workflows if workflows is not None else tools.list_workflows(),
                    projects_root=Path(projects_root) if projects_root is not None else None,
                ),
                call_id=call_id,
            )
        if tool_name == "read_task":
            return _ok_result(tool_name, tools.read_task(int(args["task_id"]), rows_fn=rows_fn), call_id=call_id)  # type: ignore[arg-type]
        if tool_name == "read_task_events":
            return _ok_result(
                tool_name,
                tools.read_task_events(
                    int(args["task_id"]),
                    rows_fn=rows_fn,  # type: ignore[arg-type]
                    projects_root=Path(projects_root) if projects_root is not None else None,
                    tail_chars=int(args.get("tail_chars") or 12000),
                ),
                call_id=call_id,
            )
        if tool_name == "read_result_summary":
            return _ok_result(
                tool_name,
                tools.read_result_summary(
                    int(args["task_id"]),
                    rows_fn=rows_fn,  # type: ignore[arg-type]
                    projects_root=Path(projects_root) if projects_root is not None else None,
                ),
                call_id=call_id,
            )
        if tool_name == "observe_repair_task":
            return _ok_result(
                tool_name,
                tools.observe_repair_task(
                    int(args["task_id"]),
                    rows_fn=rows_fn,  # type: ignore[arg-type]
                    projects_root=Path(projects_root) if projects_root is not None else None,
                ),
                call_id=call_id,
            )
        if tool_name == "create_workflow_task":
            if not allow_production_task_creation or create_task_fn is None:
                return _blocked_result(
                    tool_name,
                    "create_workflow_task can only run from the server-side resume confirmation path.",
                    call_id=call_id,
                )
            result = tools.create_workflow_task(confirmation=args["confirmation"], create_task_fn=create_task_fn)
            return {
                "status": "ok" if result.get("status") == "task_created" else result.get("status", "blocked"),
                "tool": tool_name,
                "call_id": call_id,
                "result": result,
                "production_task_created": result.get("status") == "task_created",
            }
    except Exception as exc:
        return {
            "status": "error",
            "tool": tool_name,
            "call_id": call_id,
            "message": str(exc),
            "production_task_created": False,
        }
    return _blocked_result(tool_name, f"Tool dispatcher has no handler for: {tool_name}", call_id=call_id)


def dispatch_model_tool_calls(
    tool_calls: list[dict[str, Any]],
    **context: Any,
) -> list[dict[str, Any]]:
    trace = []
    for call in tool_calls:
        name = str(call.get("name") or call.get("function", {}).get("name") or "")
        arguments = call.get("arguments")
        if arguments is None and isinstance(call.get("function"), dict):
            arguments = call["function"].get("arguments")
        call_id = call.get("id") or call.get("call_id")
        trace.append(dispatch_tool_call(name, arguments, call_id=str(call_id) if call_id else None, **context))
    return trace


def tool_trace_message(tool_trace: list[dict[str, Any]]) -> dict[str, str]:
    return {
        "role": "user",
        "content": "Tool results JSON:\n" + json.dumps(tool_trace, ensure_ascii=False, default=str)[:30000],
    }


def tool_trace_response_items(tool_trace: list[dict[str, Any]]) -> list[dict[str, str]]:
    items = []
    for result in tool_trace:
        call_id = result.get("call_id")
        if not call_id:
            continue
        items.append(
            {
                "type": "function_call_output",
                "call_id": str(call_id),
                "output": json.dumps(result, ensure_ascii=False, default=str)[:30000],
            }
        )
    return items
