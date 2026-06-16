import json

import pytest

from app.agent import model_gateway


MODEL_ENV_KEYS = [
    "IMAGE_AGENT_MODEL_PROVIDER",
    "IMAGE_AGENT_MODEL_API_KEY",
    "IMAGE_AGENT_MODEL_BASE_URL",
    "IMAGE_AGENT_MODEL_NAME",
    "IMAGE_AGENT_MODEL_REVIEW_NAME",
    "IMAGE_AGENT_MODEL_WIRE_API",
    "MODEL_PROVIDER",
    "OPENAI_API_KEY",
    "OPENAI_BASE_URL",
    "OPENAI_MODEL",
    "OPENAI_REVIEW_MODEL",
    "OPENAI_WIRE_API",
    "RAWCHAT_API_KEY",
    "RAWCHAT_BASE_URL",
    "RAWCHAT_MODEL",
    "RAWCHAT_WIRE_API",
    "KRILL_API_KEY",
    "KRILL_BASE_URL",
    "KRILL_MODEL",
    "KRILL_WIRE_API",
    "DEEPSEEK_API_KEY",
    "DEEPSEEK_BASE_URL",
    "DEEPSEEK_MODEL",
    "DEEPSEEK_WIRE_API",
    "GLM_API_KEY",
    "GLM_BASE_URL",
    "GLM_MODEL",
    "GLM_WIRE_API",
    "ZHIPU_API_KEY",
    "ZHIPU_BASE_URL",
    "ZHIPU_MODEL",
    "OPENAI_REASONING_EFFORT",
    "MODEL_REASONING_EFFORT",
    "OPENAI_DISABLE_RESPONSE_STORAGE",
    "DISABLE_RESPONSE_STORAGE",
    "OPENAI_CONTEXT_WINDOW",
    "MODEL_CONTEXT_WINDOW",
    "OPENAI_AUTO_COMPACT_TOKEN_LIMIT",
    "MODEL_AUTO_COMPACT_TOKEN_LIMIT",
    "OPENAI_DISABLE_METADATA",
    "OPENAI_RESPONSES_DISABLE_METADATA",
    "BACKEND_RUNTIME_MODE",
    "IMAGE_AGENT_MODEL_TUNNEL_PORT",
]


def clear_model_env(monkeypatch):
    for key in MODEL_ENV_KEYS:
        monkeypatch.delenv(key, raising=False)


@pytest.fixture(autouse=True)
def isolate_model_gateway_env(monkeypatch):
    clear_model_env(monkeypatch)


def test_model_config_reads_openai_compatible_environment(monkeypatch):
    monkeypatch.setenv("MODEL_PROVIDER", "OpenAI")
    monkeypatch.setenv("OPENAI_API_KEY", "secret-value")
    monkeypatch.setenv("OPENAI_BASE_URL", "http://127.0.0.1:8080")
    monkeypatch.setenv("OPENAI_MODEL", "gpt-5.5")
    monkeypatch.setenv("OPENAI_REVIEW_MODEL", "gpt-5.5")
    monkeypatch.setenv("OPENAI_WIRE_API", "responses")
    monkeypatch.setenv("OPENAI_REASONING_EFFORT", "xhigh")
    monkeypatch.setenv("OPENAI_DISABLE_RESPONSE_STORAGE", "true")

    config = model_gateway.ModelConfig.from_env()

    assert config.provider == "OpenAI"
    assert config.base_url == "http://127.0.0.1:8080"
    assert config.model == "gpt-5.5"
    assert config.review_model == "gpt-5.5"
    assert config.wire_api == "responses"
    assert config.reasoning_effort == "xhigh"
    assert config.store is False


def test_model_config_prefers_image_agent_model_environment(monkeypatch):
    clear_model_env(monkeypatch)
    monkeypatch.setenv("MODEL_PROVIDER", "OpenAI")
    monkeypatch.setenv("OPENAI_API_KEY", "legacy-secret")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://legacy.example/v1")
    monkeypatch.setenv("OPENAI_MODEL", "legacy-model")
    monkeypatch.setenv("OPENAI_WIRE_API", "chat_completions")
    monkeypatch.setenv("IMAGE_AGENT_MODEL_PROVIDER", "rawchat")
    monkeypatch.setenv("IMAGE_AGENT_MODEL_API_KEY", "rawchat-secret")
    monkeypatch.setenv("IMAGE_AGENT_MODEL_BASE_URL", "https://rawchat.example/codex")
    monkeypatch.setenv("IMAGE_AGENT_MODEL_NAME", "gpt-5.5")
    monkeypatch.setenv("IMAGE_AGENT_MODEL_REVIEW_NAME", "gpt-5.5-review")
    monkeypatch.setenv("IMAGE_AGENT_MODEL_WIRE_API", "responses")

    config = model_gateway.ModelConfig.from_env()

    assert config.provider == "rawchat"
    assert config.provider_profile == "rawchat"
    assert config.api_key == "rawchat-secret"
    assert config.base_url == "https://rawchat.example/codex"
    assert config.model == "gpt-5.5"
    assert config.review_model == "gpt-5.5-review"
    assert config.wire_api == "responses"


def test_model_config_uses_deepseek_provider_specific_environment(monkeypatch):
    clear_model_env(monkeypatch)
    monkeypatch.setenv("IMAGE_AGENT_MODEL_PROVIDER", "deepseek")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "deepseek-secret")
    monkeypatch.setenv("DEEPSEEK_BASE_URL", "https://api.deepseek.example")
    monkeypatch.setenv("DEEPSEEK_MODEL", "deepseek-chat")

    config = model_gateway.ModelConfig.from_env()

    assert config.provider == "deepseek"
    assert config.provider_profile == "deepseek"
    assert config.api_key == "deepseek-secret"
    assert config.base_url == "https://api.deepseek.example"
    assert config.model == "deepseek-chat"
    assert config.wire_api == "chat_completions"


def test_provider_status_reports_glm_profile_capabilities_without_secrets(monkeypatch):
    clear_model_env(monkeypatch)
    monkeypatch.setenv("IMAGE_AGENT_MODEL_PROVIDER", "glm")
    monkeypatch.setenv("GLM_API_KEY", "glm-secret")
    monkeypatch.setenv("GLM_BASE_URL", "https://glm.example/api/paas/v4")
    monkeypatch.setenv("GLM_MODEL", "glm-4.5")

    status = model_gateway.provider_status()

    assert status["provider"] == "glm"
    assert status["provider_profile"] == "glm"
    assert status["configured"] is True
    assert status["wire_api"] == "chat_completions"
    assert status["capabilities"]["text"] is True
    assert status["capabilities"]["structured_json"] is True
    assert status["capabilities"]["model_tool_loop"] is False
    assert "api_key" not in status
    assert "glm-secret" not in json.dumps(status)


def test_model_config_accepts_codex_style_environment_names(monkeypatch):
    monkeypatch.setenv("MODEL_PROVIDER", "OpenAI")
    monkeypatch.setenv("OPENAI_API_KEY", "secret-value")
    monkeypatch.setenv("OPENAI_BASE_URL", "http://127.0.0.1:8080")
    monkeypatch.setenv("MODEL", "gpt-5.5")
    monkeypatch.setenv("REVIEW_MODEL", "gpt-5.5")
    monkeypatch.setenv("MODEL_REASONING_EFFORT", "xhigh")
    monkeypatch.setenv("DISABLE_RESPONSE_STORAGE", "true")
    monkeypatch.setenv("MODEL_CONTEXT_WINDOW", "1000000")
    monkeypatch.setenv("MODEL_AUTO_COMPACT_TOKEN_LIMIT", "900000")

    config = model_gateway.ModelConfig.from_env()

    assert config.provider == "OpenAI"
    assert config.model == "gpt-5.5"
    assert config.review_model == "gpt-5.5"
    assert config.reasoning_effort == "xhigh"
    assert config.store is False
    assert config.context_window == 1000000
    assert config.auto_compact_token_limit == 900000


def test_provider_status_does_not_expose_api_key(monkeypatch):
    monkeypatch.setenv("MODEL_PROVIDER", "OpenAI")
    monkeypatch.setenv("OPENAI_API_KEY", "secret-value")
    monkeypatch.setenv("OPENAI_BASE_URL", "http://127.0.0.1:8080")

    status = model_gateway.provider_status()

    assert status["provider"] == "OpenAI"
    assert status["configured"] is True
    assert "api_key" not in status
    assert "secret-value" not in json.dumps(status)


def test_provider_status_reports_remote_reverse_tunnel_hint(monkeypatch):
    monkeypatch.setenv("BACKEND_RUNTIME_MODE", "remote")
    monkeypatch.setenv("OPENAI_API_KEY", "secret-value")
    monkeypatch.setenv("OPENAI_BASE_URL", "http://127.0.0.1:18080")
    monkeypatch.setenv("IMAGE_AGENT_MODEL_TUNNEL_PORT", "18080")

    status = model_gateway.provider_status()

    assert status["configured"] is True
    assert status["base_url"] == "http://127.0.0.1:18080"
    assert status["deployment"]["backend_runtime_mode"] == "remote"
    assert status["deployment"]["model_gateway_access"] == "ssh_reverse_tunnel"
    assert "ssh -N -R 18080:127.0.0.1:8080" in status["deployment"]["reverse_tunnel_command"]


def test_provider_status_reports_metadata_disabled_without_secrets(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "secret-value")
    monkeypatch.setenv("OPENAI_DISABLE_METADATA", "true")

    status = model_gateway.provider_status()

    assert status["metadata_enabled"] is False
    assert "secret-value" not in json.dumps(status)


def test_provider_status_reports_responses_gateway_diagnostics(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "secret-value")
    monkeypatch.setenv("OPENAI_WIRE_API", "responses")

    status = model_gateway.provider_status()

    assert status["gateway_diagnostics"] == {
        "sdk_method": "responses.create",
        "request_shape": "responses_input",
        "structured_output": "responses_text_format",
        "model_tool_loop": "enabled",
        "workflow_task_creation": "server_side_resume_confirmation_only",
    }
    assert "secret-value" not in json.dumps(status)


def test_provider_status_reports_chat_completions_gateway_diagnostics(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "secret-value")
    monkeypatch.setenv("OPENAI_WIRE_API", "chat_completions")

    status = model_gateway.provider_status()

    assert status["gateway_diagnostics"] == {
        "sdk_method": "chat.completions.create",
        "request_shape": "chat_messages",
        "structured_output": "chat_response_format_json_object",
        "model_tool_loop": "skipped",
        "workflow_task_creation": "server_side_resume_confirmation_only",
    }
    assert "secret-value" not in json.dumps(status)


def test_responses_payload_includes_openai_style_function_tools(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "secret-value")
    config = model_gateway.ModelConfig.from_env()

    payload = model_gateway._responses_payload([{"role": "user", "content": "hi"}], config, structured=True)

    assert payload["tool_choice"] == "auto"
    assert any(tool["type"] == "function" and tool["name"] == "create_workflow_task" for tool in payload["tools"])
    assert all("function" not in tool for tool in payload["tools"])
    assert payload["text"]["format"]["type"] == "json_object"


def test_responses_payload_prefers_json_schema_when_structured_schema_is_available(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "secret-value")
    config = model_gateway.ModelConfig.from_env()
    schema = {
        "name": "agent_decision",
        "description": "Agent decision envelope.",
        "strict": True,
        "schema": {
            "type": "object",
            "additionalProperties": False,
            "required": ["intent"],
            "properties": {"intent": {"type": "string"}},
        },
    }

    payload = model_gateway._responses_payload(
        [{"role": "user", "content": "hi"}],
        config,
        structured=True,
        structured_schema=schema,
    )

    assert payload["text"]["format"] == {"type": "json_schema", **schema}


@pytest.mark.parametrize(
    ("schema", "message"),
    [
        ({"strict": True, "schema": {"type": "object", "additionalProperties": False}}, "structured_schema must include name"),
        ({"name": "agent_decision", "schema": {"type": "object", "additionalProperties": False}}, "structured_schema strict must be true"),
        (
            {"name": "agent_decision", "strict": False, "schema": {"type": "object", "additionalProperties": False}},
            "structured_schema strict must be true",
        ),
        ({"name": "agent_decision", "strict": True}, "structured_schema schema must be an object"),
        ({"name": "agent_decision", "strict": True, "schema": []}, "structured_schema schema must be an object"),
        (
            {"name": "agent_decision", "strict": True, "schema": {"type": "array", "additionalProperties": False}},
            "structured_schema schema.type must be object",
        ),
        (
            {"name": "agent_decision", "strict": True, "schema": {"type": "object"}},
            "structured_schema schema.additionalProperties must be false",
        ),
    ],
)
def test_responses_payload_rejects_non_strict_structured_schema(monkeypatch, schema, message):
    monkeypatch.setenv("OPENAI_API_KEY", "secret-value")
    config = model_gateway.ModelConfig.from_env()

    with pytest.raises(model_gateway.ModelGatewayError, match=message):
        model_gateway._responses_payload(
            [{"role": "user", "content": "hi"}],
            config,
            structured=True,
            structured_schema=schema,
        )


def test_responses_payload_preserves_function_call_output_items(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "secret-value")
    config = model_gateway.ModelConfig.from_env()
    output_item = {
        "type": "function_call_output",
        "call_id": "call_123",
        "output": '{"status":"ok"}',
    }

    payload = model_gateway._responses_payload([{"role": "user", "content": "hi"}, output_item], config)

    assert payload["input"][0] == {"role": "user", "content": "hi"}
    assert payload["input"][1] == output_item


def test_responses_payload_preserves_function_call_items(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "secret-value")
    config = model_gateway.ModelConfig.from_env()
    call_item = {
        "type": "function_call",
        "call_id": "call_123",
        "name": "list_workflows",
        "arguments": '{"lane":"fixed_workflow"}',
    }

    payload = model_gateway._responses_payload([{"role": "user", "content": "hi"}, call_item], config)

    assert payload["input"][1] == call_item


def test_parse_responses_text_output():
    body = {
        "output": [
            {
                "type": "message",
                "content": [
                    {"type": "output_text", "text": "hello from model"},
                ],
            }
        ]
    }

    assert model_gateway.parse_responses_text(body) == "hello from model"


def test_parse_structured_json_output():
    body = {
        "output": [
            {
                "type": "message",
                "content": [
                    {"type": "output_text", "text": '{"intent": "status"}'},
                ],
            }
        ]
    }

    assert model_gateway.parse_responses_json(body) == {"intent": "status"}


def test_parse_structured_json_output_allows_trailing_gateway_text():
    body = {
        "output": [
            {
                "type": "message",
                "content": [
                    {
                        "type": "output_text",
                        "text": '{"intent": "status", "summary": "ok"}\n\nThe requested JSON is above.',
                    },
                ],
            }
        ]
    }

    assert model_gateway.parse_responses_json(body) == {"intent": "status", "summary": "ok"}


def test_parse_structured_json_rejects_non_object():
    body = {
        "output": [
            {
                "type": "message",
                "content": [
                    {"type": "output_text", "text": "not-json"},
                ],
            }
        ]
    }

    with pytest.raises(model_gateway.ModelGatewayError, match="valid JSON"):
        model_gateway.parse_responses_json(body)


def test_parse_responses_tool_calls_extracts_function_call_items():
    body = {
        "output": [
            {
                "type": "function_call",
                "call_id": "call_123",
                "name": "list_workflows",
                "arguments": '{"lane": "fixed_workflow"}',
            }
        ]
    }

    calls = model_gateway.parse_responses_tool_calls(body)

    assert calls == [
        {
            "id": "call_123",
            "name": "list_workflows",
            "arguments": '{"lane": "fixed_workflow"}',
        }
    ]


def test_complete_structured_with_tools_dispatches_tool_calls_before_final_json(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "secret-value")
    monkeypatch.setenv("OPENAI_WIRE_API", "responses")

    class FakeGateway(model_gateway.ModelGateway):
        def __init__(self):
            super().__init__(model_gateway.ModelConfig.from_env())
            self.requested_messages = []

        def _request(self, messages, *, structured, purpose):
            self.requested_messages.append(messages)
            if len(self.requested_messages) == 1:
                return {
                    "output": [
                        {
                            "type": "function_call",
                            "call_id": "call_1",
                            "name": "list_workflows",
                            "arguments": '{"lane": "fixed_workflow", "agent_selectable": true}',
                        }
                    ]
                }
            return {
                "output": [
                    {
                        "type": "message",
                        "content": [
                            {"type": "output_text", "text": '{"intent": "answer_question", "summary": "read tools"}'}
                        ],
                    }
                ]
            }

    result = FakeGateway().complete_structured_with_tools(
        [{"role": "user", "content": "What workflows are available?"}],
        purpose="agent_plan",
        tool_context={},
    )

    assert result["tool_messages"][0]["type"] == "function_call"
    assert result["decision"]["intent"] == "answer_question"
    assert result["tool_trace"][0]["tool"] == "list_workflows"
    assert result["tool_messages"][-1]["type"] == "function_call_output"
    assert result["tool_messages"][-1]["call_id"] == "call_1"


def test_complete_structured_with_tools_blocks_create_workflow_task_tool_loop(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "secret-value")
    monkeypatch.setenv("OPENAI_WIRE_API", "responses")

    class FakeGateway(model_gateway.ModelGateway):
        def __init__(self):
            super().__init__(model_gateway.ModelConfig.from_env())
            self.requested_messages = []

        def _request(self, messages, *, structured, purpose, structured_schema=None):
            self.requested_messages.append(messages)
            if len(self.requested_messages) == 1:
                return {
                    "output": [
                        {
                            "type": "function_call",
                            "call_id": "call_create",
                            "name": "create_workflow_task",
                            "arguments": '{"confirmation": {"approved": true, "workflow_type": "t1_deepprep_anat_report"}}',
                        }
                    ]
                }
            return {
                "output": [
                    {
                        "type": "message",
                        "content": [
                            {
                                "type": "output_text",
                                "text": '{"intent": "answer_question", "summary": "blocked production tool"}',
                            }
                        ],
                    }
                ]
            }

    result = FakeGateway().complete_structured_with_tools(
        [{"role": "user", "content": "Launch the task directly"}],
        purpose="agent_plan",
        tool_context={},
    )

    blocked = result["tool_trace"][0]
    assert blocked["status"] == "blocked"
    assert blocked["tool"] == "create_workflow_task"
    assert blocked["production_task_created"] is False
    assert result["tool_messages"][-1]["type"] == "function_call_output"
    assert result["decision"]["intent"] == "answer_question"


def test_request_uses_openai_sdk_responses_client(monkeypatch):
    calls = {}

    class FakeResponses:
        def create(self, **payload):
            calls["payload"] = payload
            return {
                "output": [
                    {
                        "type": "message",
                        "content": [{"type": "output_text", "text": "hello"}],
                    }
                ]
            }

    class FakeOpenAI:
        def __init__(self, *, api_key, base_url, timeout):
            calls["client"] = {"api_key": api_key, "base_url": base_url, "timeout": timeout}
            self.responses = FakeResponses()

    monkeypatch.setattr(model_gateway, "OpenAI", FakeOpenAI, raising=False)
    config = model_gateway.ModelConfig(
        provider="OpenAI",
        api_key="secret-value",
        base_url="http://127.0.0.1:8080",
        model="gpt-5.5",
        review_model="gpt-5.5",
        wire_api="responses",
        reasoning_effort="xhigh",
        store=False,
        timeout_seconds=12,
        context_window=1000000,
        auto_compact_token_limit=900000,
    )

    body = model_gateway.ModelGateway(config)._request([{"role": "user", "content": "hi"}], structured=True, purpose="agent_plan")

    assert calls["client"] == {"api_key": "secret-value", "base_url": "http://127.0.0.1:8080", "timeout": 12}
    assert calls["payload"]["model"] == "gpt-5.5"
    assert calls["payload"]["input"][0] == {"role": "user", "content": "hi"}
    assert calls["payload"]["metadata"] == {"purpose": "agent_plan"}
    assert calls["payload"]["text"]["format"]["type"] == "json_object"
    assert calls["payload"]["tool_choice"] == "auto"
    assert body["output"][0]["content"][0]["text"] == "hello"


def test_request_forwards_json_schema_to_openai_sdk_responses_client(monkeypatch):
    calls = {}

    class FakeResponses:
        def create(self, **payload):
            calls["payload"] = payload
            return {
                "output": [
                    {
                        "type": "message",
                        "content": [{"type": "output_text", "text": '{"intent":"status"}'}],
                    }
                ]
            }

    class FakeOpenAI:
        def __init__(self, *, api_key, base_url, timeout):
            calls["client"] = {"api_key": api_key, "base_url": base_url, "timeout": timeout}
            self.responses = FakeResponses()

    monkeypatch.setattr(model_gateway, "OpenAI", FakeOpenAI, raising=False)
    config = model_gateway.ModelConfig(
        provider="OpenAI",
        api_key="secret-value",
        base_url="http://127.0.0.1:8080",
        model="gpt-5.5",
        review_model="gpt-5.5",
        wire_api="responses",
        reasoning_effort="xhigh",
        store=False,
        timeout_seconds=12,
        context_window=1000000,
        auto_compact_token_limit=900000,
    )
    schema = {
        "name": "agent_decision",
        "strict": True,
        "schema": {
            "type": "object",
            "additionalProperties": False,
            "required": ["intent"],
            "properties": {"intent": {"type": "string"}},
        },
    }

    body = model_gateway.ModelGateway(config)._request(
        [{"role": "user", "content": "status"}],
        structured=True,
        structured_schema=schema,
        purpose="agent_plan",
    )

    assert calls["payload"]["text"]["format"] == {"type": "json_schema", **schema}
    assert body["output"][0]["content"][0]["text"] == '{"intent":"status"}'


def test_request_retries_without_metadata_for_openai_compatible_responses(monkeypatch):
    calls = []

    class FakeResponses:
        def create(self, **payload):
            calls.append(payload)
            if "metadata" in payload:
                raise RuntimeError("Unsupported parameter: metadata")
            return {
                "output": [
                    {
                        "type": "message",
                        "content": [{"type": "output_text", "text": "hello"}],
                    }
                ]
            }

    class FakeOpenAI:
        def __init__(self, **_kwargs):
            self.responses = FakeResponses()

    monkeypatch.setattr(model_gateway, "OpenAI", FakeOpenAI, raising=False)
    config = model_gateway.ModelConfig(
        provider="OpenAI",
        api_key="secret-value",
        base_url="https://openai-compatible.example",
        model="gpt-5.5",
        review_model="gpt-5.5",
        wire_api="responses",
        reasoning_effort="high",
        store=False,
        timeout_seconds=12,
        context_window=1000000,
        auto_compact_token_limit=900000,
    )

    body = model_gateway.ModelGateway(config)._request([{"role": "user", "content": "hi"}], structured=False, purpose="agent_plan")

    assert len(calls) == 2
    assert calls[0]["metadata"] == {"purpose": "agent_plan"}
    assert "metadata" not in calls[1]
    assert body["output"][0]["content"][0]["text"] == "hello"


def test_request_can_disable_metadata_for_opaque_openai_compatible_gateways(monkeypatch):
    calls = {}

    class FakeResponses:
        def create(self, **payload):
            calls["payload"] = payload
            return {
                "output": [
                    {
                        "type": "message",
                        "content": [{"type": "output_text", "text": "hello"}],
                    }
                ]
            }

    class FakeOpenAI:
        def __init__(self, **_kwargs):
            self.responses = FakeResponses()

    monkeypatch.setattr(model_gateway, "OpenAI", FakeOpenAI, raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "secret-value")
    monkeypatch.setenv("OPENAI_BASE_URL", "http://127.0.0.1:18081")
    monkeypatch.setenv("OPENAI_WIRE_API", "responses")
    monkeypatch.setenv("OPENAI_DISABLE_METADATA", "true")

    config = model_gateway.ModelConfig.from_env()
    body = model_gateway.ModelGateway(config)._request([{"role": "user", "content": "hi"}], structured=False, purpose="agent_plan")

    assert "metadata" not in calls["payload"]
    assert body["output"][0]["content"][0]["text"] == "hello"


def test_request_accepts_openai_sdk_model_dump_response(monkeypatch):
    class FakeResponse:
        def model_dump(self):
            return {
                "output": [
                    {
                        "type": "message",
                        "content": [{"type": "output_text", "text": '{"intent":"status"}'}],
                    }
                ]
            }

    class FakeOpenAI:
        def __init__(self, **_kwargs):
            self.responses = self

        def create(self, **_payload):
            return FakeResponse()

    monkeypatch.setattr(model_gateway, "OpenAI", FakeOpenAI, raising=False)
    config = model_gateway.ModelConfig(
        provider="OpenAI",
        api_key="secret-value",
        base_url="http://127.0.0.1:8080",
        model="gpt-5.5",
        review_model="gpt-5.5",
        wire_api="responses",
        reasoning_effort="xhigh",
        store=False,
        timeout_seconds=12,
        context_window=1000000,
        auto_compact_token_limit=900000,
    )

    result = model_gateway.ModelGateway(config).complete_structured([{"role": "user", "content": "status"}])

    assert result == {"intent": "status"}


def test_complete_text_uses_openai_sdk_chat_completions_client(monkeypatch):
    calls = {}

    class FakeCompletions:
        def create(self, **payload):
            calls["payload"] = payload
            return {"choices": [{"message": {"content": "pong"}}]}

    class FakeChat:
        def __init__(self):
            self.completions = FakeCompletions()

    class FakeOpenAI:
        def __init__(self, *, api_key, base_url, timeout):
            calls["client"] = {"api_key": api_key, "base_url": base_url, "timeout": timeout}
            self.chat = FakeChat()

    monkeypatch.setattr(model_gateway, "OpenAI", FakeOpenAI, raising=False)
    config = model_gateway.ModelConfig(
        provider="OpenAI",
        api_key="secret-value",
        base_url="https://openai-compatible.example/v1",
        model="gpt-5.5",
        review_model="gpt-5.5",
        wire_api="chat_completions",
        reasoning_effort="xhigh",
        store=False,
        timeout_seconds=12,
        context_window=1000000,
        auto_compact_token_limit=900000,
    )

    result = model_gateway.ModelGateway(config).complete_text([{"role": "user", "content": "ping"}], purpose="smoke")

    assert result == "pong"
    assert calls["client"] == {
        "api_key": "secret-value",
        "base_url": "https://openai-compatible.example/v1",
        "timeout": 12,
    }
    assert calls["payload"]["model"] == "gpt-5.5"
    assert calls["payload"]["messages"] == [{"role": "user", "content": "ping"}]
    assert "metadata" not in calls["payload"]
    assert "tools" not in calls["payload"]


def test_complete_structured_uses_chat_completions_json_object(monkeypatch):
    calls = {}

    class FakeCompletions:
        def create(self, **payload):
            calls["payload"] = payload
            return {"choices": [{"message": {"content": '{"intent":"answer_question"}'}}]}

    class FakeOpenAI:
        def __init__(self, **_kwargs):
            self.chat = type("FakeChat", (), {"completions": FakeCompletions()})()

    monkeypatch.setattr(model_gateway, "OpenAI", FakeOpenAI, raising=False)
    config = model_gateway.ModelConfig(
        provider="OpenAI",
        api_key="secret-value",
        base_url="https://openai-compatible.example/v1",
        model="gpt-5.5",
        review_model="gpt-5.5",
        wire_api="chat_completions",
        reasoning_effort="xhigh",
        store=False,
        timeout_seconds=12,
        context_window=1000000,
        auto_compact_token_limit=900000,
    )
    schema = {
        "name": "agent_decision",
        "strict": True,
        "schema": {
            "type": "object",
            "additionalProperties": False,
            "required": ["intent"],
            "properties": {"intent": {"type": "string"}},
        },
    }

    result = model_gateway.ModelGateway(config).complete_structured(
        [{"role": "user", "content": "status"}],
        structured_schema=schema,
    )

    assert result == {"intent": "answer_question"}
    assert calls["payload"]["response_format"] == {"type": "json_object"}
    assert "agent_decision" in calls["payload"]["messages"][-1]["content"]


def test_complete_structured_with_tools_uses_chat_completions_without_tool_loop(monkeypatch):
    class FakeCompletions:
        def create(self, **_payload):
            return {"choices": [{"message": {"content": '{"intent":"answer_question"}'}}]}

    class FakeOpenAI:
        def __init__(self, **_kwargs):
            self.chat = type("FakeChat", (), {"completions": FakeCompletions()})()

    monkeypatch.setattr(model_gateway, "OpenAI", FakeOpenAI, raising=False)
    config = model_gateway.ModelConfig(
        provider="OpenAI",
        api_key="secret-value",
        base_url="https://openai-compatible.example/v1",
        model="gpt-5.5",
        review_model="gpt-5.5",
        wire_api="chat_completions",
        reasoning_effort="xhigh",
        store=False,
        timeout_seconds=12,
        context_window=1000000,
        auto_compact_token_limit=900000,
    )

    result = model_gateway.ModelGateway(config).complete_structured_with_tools(
        [{"role": "user", "content": "What workflows are available?"}],
        purpose="agent_plan",
        tool_context={},
    )

    assert result["decision"] == {"intent": "answer_question"}
    assert result["tool_trace"] == [
        {"status": "skipped", "reason": "chat_completions_wire_api_does_not_run_tool_loop"}
    ]
    assert result["tool_messages"] == []
