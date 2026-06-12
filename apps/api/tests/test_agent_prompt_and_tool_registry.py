from pathlib import Path

from app.agent.tool_registry import list_function_tools, openai_tool_specs


PROMPT_ROOT = Path(__file__).resolve().parents[1] / "app" / "agent" / "prompts"


def test_agent_prompts_are_present_for_openai_style_brain():
    for name in ("planner.md", "responder.md", "safety.md", "tool-use.md", "rag-use.md"):
        text = (PROMPT_ROOT / name).read_text(encoding="utf-8")
        assert "image_agent" in text
        assert "backend" in text.lower() or "tool" in text.lower()


def test_agent_prompts_describe_data_candidate_tool_use():
    planner = (PROMPT_ROOT / "planner.md").read_text(encoding="utf-8")
    tool_use = (PROMPT_ROOT / "tool-use.md").read_text(encoding="utf-8")
    combined = planner + "\n" + tool_use

    assert "`list_data_candidates`" in combined
    assert "`select_incubation_dataset`" in combined
    assert "does not name a series" in planner
    assert "`production_task_created=false`" in tool_use


def test_function_tool_registry_exposes_required_tools_without_shell_access():
    tools = list_function_tools()
    names = {tool["name"] for tool in tools}

    assert {
        "read_project_context",
        "list_workflows",
        "preflight_workflow",
        "retrieve_reference_context",
        "list_data_candidates",
        "select_incubation_dataset",
        "create_workflow_task",
        "read_task",
        "read_task_events",
        "read_result_summary",
        "propose_toolchain",
        "sandbox_validate_toolchain",
        "promote_toolchain_to_workflow",
    } <= names
    assert "shell" not in names
    assert "docker_run" not in names
    assert all("parameters" in tool for tool in tools)


def test_openai_function_tool_specs_are_strict_responses_schemas():
    specs = openai_tool_specs()

    assert specs
    for spec in specs:
        assert spec["type"] == "function", spec["name"]
        assert spec["strict"] is True, spec["name"]
        parameters = spec["parameters"]
        assert parameters["type"] == "object", spec["name"]
        assert parameters["additionalProperties"] is False, spec["name"]
        for path, schema in _object_schemas(parameters):
            assert schema["additionalProperties"] is False, f"{spec['name']}:{path}"


def _object_schemas(schema, path="$"):
    if not isinstance(schema, dict):
        return
    if schema.get("type") == "object":
        yield path, schema
    for key, value in schema.get("properties", {}).items():
        yield from _object_schemas(value, f"{path}.properties.{key}")
    items = schema.get("items")
    if isinstance(items, dict):
        yield from _object_schemas(items, f"{path}.items")
    for index, value in enumerate(schema.get("oneOf", []) or []):
        yield from _object_schemas(value, f"{path}.oneOf[{index}]")
