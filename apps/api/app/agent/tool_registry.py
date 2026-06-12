from __future__ import annotations

from copy import deepcopy
from typing import Any


FUNCTION_TOOLS: list[dict[str, Any]] = [
    {
        "name": "read_project_context",
        "description": "Read backend project, series, task, output, and workflow registry context.",
        "parameters": {"type": "object", "properties": {"project_id": {"type": ["integer", "null"]}}},
    },
    {
        "name": "list_workflows",
        "description": "List workflow registry entries with optional lane and agent_selectable filters.",
        "parameters": {
            "type": "object",
            "properties": {
                "lane": {"type": ["string", "null"], "enum": ["fixed_workflow", "toolchain_incubation"]},
                "agent_selectable": {"type": ["boolean", "null"]},
            },
        },
    },
    {
        "name": "preflight_workflow",
        "description": "Run deterministic workflow eligibility checks before confirmation.",
        "parameters": {
            "type": "object",
            "required": ["series_id", "workflow_type"],
            "properties": {"series_id": {"type": "integer"}, "workflow_type": {"type": "string"}},
        },
    },
    {
        "name": "retrieve_reference_context",
        "description": "Local file_search-like RAG over docs/rag and docs/skills references.",
        "parameters": {
            "type": "object",
            "required": ["query"],
            "properties": {"query": {"type": "string"}, "filters": {"type": "object"}, "limit": {"type": "integer"}},
        },
    },
    {
        "name": "list_data_candidates",
        "description": "List registered imaging series that can be used for fixed workflow launch or sandbox incubation validation without exposing raw image contents.",
        "parameters": {
            "type": "object",
            "properties": {
                "project_id": {"type": ["integer", "null"]},
                "modality": {"type": ["string", "null"]},
                "workflow_type": {"type": ["string", "null"]},
                "limit": {"type": "integer"},
            },
        },
    },
    {
        "name": "select_incubation_dataset",
        "description": "Select the best registered sandbox candidate for incubating a toolchain proposal; never creates production tasks.",
        "parameters": {
            "type": "object",
            "properties": {
                "project_id": {"type": ["integer", "null"]},
                "modality": {"type": ["string", "null"]},
                "workflow_type": {"type": ["string", "null"]},
            },
        },
    },
    {
        "name": "create_workflow_task",
        "description": "Create a backend task for an approved fixed workflow confirmation only.",
        "parameters": {
            "type": "object",
            "required": ["confirmation"],
            "properties": {"confirmation": {"type": "object"}},
        },
    },
    {
        "name": "read_task",
        "description": "Read backend task status by task id.",
        "parameters": {"type": "object", "required": ["task_id"], "properties": {"task_id": {"type": "integer"}}},
    },
    {
        "name": "read_task_events",
        "description": "Read task events/log tail for progress and failures.",
        "parameters": {"type": "object", "required": ["task_id"], "properties": {"task_id": {"type": "integer"}}},
    },
    {
        "name": "read_result_summary",
        "description": "Read the unified result-summary contract for a completed task.",
        "parameters": {"type": "object", "required": ["task_id"], "properties": {"task_id": {"type": "integer"}}},
    },
    {
        "name": "propose_toolchain",
        "description": "Draft an incubating toolchain proposal, optionally decomposing provided container script text or approved script paths, without production execution.",
        "parameters": {
            "type": "object",
            "required": ["objective"],
            "properties": {
                "objective": {"type": "string"},
                "input_modality": {"type": ["string", "null"]},
                "primitives": {
                    "type": "array",
                    "items": {
                        "oneOf": [
                            {"type": "string"},
                            {"type": "object"},
                        ]
                    },
                },
                "script_text": {"type": ["string", "null"]},
                "script_paths": {"type": "array", "items": {"type": "string"}},
            },
        },
    },
    {
        "name": "sandbox_validate_toolchain",
        "description": "Validate an incubating toolchain in sandbox terms; never creates production tasks.",
        "parameters": {"type": "object", "required": ["proposal"], "properties": {"proposal": {"type": "object"}}},
    },
    {
        "name": "promote_toolchain_to_workflow",
        "description": "Prepare non-executing promotion suggestion artifacts after repeated sandbox validation and human approval; never enables production execution automatically.",
        "parameters": {
            "type": "object",
            "required": ["proposal", "approved"],
            "properties": {"proposal": {"type": "object"}, "approved": {"type": "boolean"}},
        },
    },
]


def list_function_tools() -> list[dict[str, Any]]:
    return deepcopy(FUNCTION_TOOLS)


def openai_tool_specs() -> list[dict[str, Any]]:
    specs = []
    for tool in list_function_tools():
        spec = {"type": "function", **tool}
        parameters = _strict_object_schema(spec.get("parameters") or {})
        spec["parameters"] = parameters
        spec["strict"] = True
        specs.append(spec)
    return specs


def _strict_object_schema(schema: dict[str, Any]) -> dict[str, Any]:
    strict_schema = deepcopy(schema)
    _mark_object_schemas_strict(strict_schema)
    return strict_schema


def _mark_object_schemas_strict(schema: Any) -> None:
    if not isinstance(schema, dict):
        return
    schema_type = schema.get("type")
    if schema_type == "object" or (isinstance(schema_type, list) and "object" in schema_type):
        schema["additionalProperties"] = False
    for value in (schema.get("properties") or {}).values():
        _mark_object_schemas_strict(value)
    _mark_object_schemas_strict(schema.get("items"))
    for key in ("oneOf", "anyOf", "allOf"):
        for value in schema.get(key) or []:
            _mark_object_schemas_strict(value)
