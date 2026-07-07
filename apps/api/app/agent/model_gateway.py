from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit

import httpx

from app.agent.tool_dispatcher import dispatch_model_tool_calls, tool_trace_message, tool_trace_response_items
from app.agent.tool_registry import openai_tool_specs


OpenAI = None
CHAT_COMPLETIONS_WIRE_APIS = {"chat", "chat_completions", "chat.completions"}
PROVIDER_PROFILES: dict[str, dict[str, Any]] = {
    "openai": {
        "base_url": "http://127.0.0.1:8080",
        "model": "gpt-5.5",
        "wire_api": "responses",
        "api_key_env": ["OPENAI_API_KEY"],
        "base_url_env": ["OPENAI_BASE_URL"],
        "model_env": ["OPENAI_MODEL", "MODEL"],
        "review_model_env": ["OPENAI_REVIEW_MODEL", "REVIEW_MODEL"],
        "wire_api_env": ["OPENAI_WIRE_API"],
    },
    "rawchat": {
        "base_url": "https://rawchat.cn/codex",
        "model": "gpt-5.5",
        "wire_api": "responses",
        "api_key_env": ["RAWCHAT_API_KEY", "OPENAI_API_KEY"],
        "base_url_env": ["RAWCHAT_BASE_URL", "OPENAI_BASE_URL"],
        "model_env": ["RAWCHAT_MODEL", "OPENAI_MODEL", "MODEL"],
        "review_model_env": ["RAWCHAT_REVIEW_MODEL", "OPENAI_REVIEW_MODEL", "REVIEW_MODEL"],
        "wire_api_env": ["RAWCHAT_WIRE_API", "OPENAI_WIRE_API"],
    },
    "krill": {
        "base_url": "https://api.krill-ai.com/codex/v1",
        "model": "gpt-5.5",
        "wire_api": "responses",
        "api_key_env": ["KRILL_API_KEY", "OPENAI_API_KEY"],
        "base_url_env": ["KRILL_BASE_URL", "OPENAI_BASE_URL"],
        "model_env": ["KRILL_MODEL", "OPENAI_MODEL", "MODEL"],
        "review_model_env": ["KRILL_REVIEW_MODEL", "OPENAI_REVIEW_MODEL", "REVIEW_MODEL"],
        "wire_api_env": ["KRILL_WIRE_API", "OPENAI_WIRE_API"],
    },
    "deepseek": {
        "base_url": "https://api.deepseek.com",
        "model": "deepseek-v4-pro",
        "wire_api": "chat_completions",
        "api_key_env": ["DEEPSEEK_API_KEY", "OPENAI_API_KEY"],
        "base_url_env": ["DEEPSEEK_BASE_URL", "OPENAI_BASE_URL"],
        "model_env": ["DEEPSEEK_MODEL", "OPENAI_MODEL", "MODEL"],
        "review_model_env": ["DEEPSEEK_REVIEW_MODEL", "OPENAI_REVIEW_MODEL", "REVIEW_MODEL"],
        "wire_api_env": ["DEEPSEEK_WIRE_API", "OPENAI_WIRE_API"],
    },
    "glm": {
        "base_url": "https://open.bigmodel.cn/api/paas/v4",
        "model": "glm-4.5",
        "wire_api": "chat_completions",
        "api_key_env": ["GLM_API_KEY", "ZHIPU_API_KEY", "OPENAI_API_KEY"],
        "base_url_env": ["GLM_BASE_URL", "ZHIPU_BASE_URL", "OPENAI_BASE_URL"],
        "model_env": ["GLM_MODEL", "ZHIPU_MODEL", "OPENAI_MODEL", "MODEL"],
        "review_model_env": ["GLM_REVIEW_MODEL", "ZHIPU_REVIEW_MODEL", "OPENAI_REVIEW_MODEL", "REVIEW_MODEL"],
        "wire_api_env": ["GLM_WIRE_API", "ZHIPU_WIRE_API", "OPENAI_WIRE_API"],
    },
    "custom": {
        "base_url": "http://127.0.0.1:8080",
        "model": "gpt-5.5",
        "wire_api": "responses",
        "api_key_env": ["OPENAI_API_KEY"],
        "base_url_env": ["OPENAI_BASE_URL"],
        "model_env": ["OPENAI_MODEL", "MODEL"],
        "review_model_env": ["OPENAI_REVIEW_MODEL", "REVIEW_MODEL"],
        "wire_api_env": ["OPENAI_WIRE_API"],
    },
}


class ModelGatewayError(RuntimeError):
    pass


def gateway_diagnostics(config: "ModelConfig") -> dict[str, str]:
    if config.wire_api == "responses":
        return {
            "sdk_method": "responses.create",
            "request_shape": "responses_input",
            "structured_output": "responses_text_format",
            "model_tool_loop": "enabled",
            "workflow_task_creation": "server_side_resume_confirmation_only",
        }
    if config.wire_api in CHAT_COMPLETIONS_WIRE_APIS:
        return {
            "sdk_method": "chat.completions.create",
            "request_shape": "chat_messages",
            "structured_output": "chat_response_format_json_object",
            "model_tool_loop": "skipped",
            "workflow_task_creation": "server_side_resume_confirmation_only",
        }
    return {
        "sdk_method": "unsupported",
        "request_shape": "unsupported",
        "structured_output": "unsupported",
        "model_tool_loop": "unsupported",
        "workflow_task_creation": "server_side_resume_confirmation_only",
    }


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _env_first(names: list[str], default: str = "") -> str:
    for name in names:
        value = os.environ.get(name)
        if value is not None and value.strip():
            return value.strip()
    return default


def _provider_profile(provider: str) -> str:
    normalized = provider.strip().lower().replace("-", "_")
    aliases = {
        "open_ai": "openai",
        "openai": "openai",
        "raw_chat": "rawchat",
        "rawchat": "rawchat",
        "krill": "krill",
        "deepseek": "deepseek",
        "deep_seek": "deepseek",
        "glm": "glm",
        "zhipu": "glm",
        "bigmodel": "glm",
        "custom": "custom",
    }
    return aliases.get(normalized, "custom")


def _is_rawchat_direct_target(profile_name: str, base_url: str) -> bool:
    if profile_name == "rawchat":
        return True
    host = (urlsplit(base_url).hostname or "").lower()
    return host == "rawchat.cn" or host.endswith(".rawchat.cn")


def _model_capabilities(wire_api: str) -> dict[str, bool]:
    return {
        "text": wire_api == "responses" or wire_api in CHAT_COMPLETIONS_WIRE_APIS,
        "structured_json": wire_api == "responses" or wire_api in CHAT_COMPLETIONS_WIRE_APIS,
        "model_tool_loop": wire_api == "responses",
    }


@dataclass(frozen=True)
class ModelConfig:
    provider: str
    api_key: str
    base_url: str
    model: str
    review_model: str
    wire_api: str
    reasoning_effort: str
    store: bool
    timeout_seconds: int
    context_window: int
    auto_compact_token_limit: int
    send_metadata: bool = True
    provider_profile: str = "openai"
    trust_env_proxy: bool = False

    @classmethod
    def from_env(cls) -> "ModelConfig":
        provider = _env_first(["IMAGE_AGENT_MODEL_PROVIDER", "MODEL_PROVIDER"], "OpenAI")
        profile_name = _provider_profile(provider)
        profile = PROVIDER_PROFILES[profile_name]
        api_key = _env_first(
            ["IMAGE_AGENT_MODEL_API_KEY", *profile["api_key_env"]],
        )
        base_url = _env_first(
            ["IMAGE_AGENT_MODEL_BASE_URL", *profile["base_url_env"]],
            profile["base_url"],
        )
        model = _env_first(
            ["IMAGE_AGENT_MODEL_NAME", *profile["model_env"]],
            profile["model"],
        )
        review_model = _env_first(
            ["IMAGE_AGENT_MODEL_REVIEW_NAME", *profile["review_model_env"]],
            model,
        )
        wire_api = _env_first(
            ["IMAGE_AGENT_MODEL_WIRE_API", *profile["wire_api_env"]],
            profile["wire_api"],
        ).lower()
        trust_env_proxy = _env_bool("IMAGE_AGENT_MODEL_TRUST_ENV_PROXY", False)
        if _is_rawchat_direct_target(profile_name, base_url):
            trust_env_proxy = False
        return cls(
            provider=provider,
            api_key=api_key,
            base_url=base_url,
            model=model,
            review_model=review_model,
            wire_api=wire_api or profile["wire_api"],
            reasoning_effort=os.environ.get("OPENAI_REASONING_EFFORT")
            or os.environ.get("MODEL_REASONING_EFFORT", "xhigh"),
            store=not (
                _env_bool("OPENAI_DISABLE_RESPONSE_STORAGE", False)
                or _env_bool("DISABLE_RESPONSE_STORAGE", True)
            ),
            timeout_seconds=int(os.environ.get("OPENAI_TIMEOUT_SECONDS", "120")),
            context_window=int(os.environ.get("OPENAI_CONTEXT_WINDOW") or os.environ.get("MODEL_CONTEXT_WINDOW", "1000000")),
            auto_compact_token_limit=int(
                os.environ.get("OPENAI_AUTO_COMPACT_TOKEN_LIMIT")
                or os.environ.get("MODEL_AUTO_COMPACT_TOKEN_LIMIT", "900000")
            ),
            send_metadata=not (
                _env_bool("OPENAI_DISABLE_METADATA", False)
                or _env_bool("OPENAI_RESPONSES_DISABLE_METADATA", False)
            ),
            provider_profile=profile_name,
            trust_env_proxy=trust_env_proxy,
        )


def provider_status(config: ModelConfig | None = None) -> dict[str, Any]:
    cfg = config or ModelConfig.from_env()
    backend_runtime_mode = os.environ.get("BACKEND_RUNTIME_MODE", "remote")
    reverse_tunnel_port = os.environ.get("IMAGE_AGENT_MODEL_TUNNEL_PORT", "18080")
    model_gateway_access = (
        "ssh_reverse_tunnel"
        if backend_runtime_mode == "remote" and cfg.base_url.startswith(f"http://127.0.0.1:{reverse_tunnel_port}")
        else "direct"
    )
    return {
        "provider": cfg.provider,
        "provider_profile": cfg.provider_profile,
        "configured": bool(cfg.api_key),
        "base_url": cfg.base_url,
        "model": cfg.model,
        "review_model": cfg.review_model,
        "wire_api": cfg.wire_api,
        "reasoning_effort": cfg.reasoning_effort,
        "store": cfg.store,
        "metadata_enabled": cfg.send_metadata,
        "context_window": cfg.context_window,
        "auto_compact_token_limit": cfg.auto_compact_token_limit,
        "trust_env_proxy": cfg.trust_env_proxy,
        "capabilities": _model_capabilities(cfg.wire_api),
        "gateway_diagnostics": gateway_diagnostics(cfg),
        "deployment": {
            "backend_runtime_mode": backend_runtime_mode,
            "model_gateway_access": model_gateway_access,
            "reverse_tunnel_command": f"ssh -N -R {reverse_tunnel_port}:127.0.0.1:8080 <remote-host>",
        },
    }


def _strict_json_schema_format(structured_schema: dict[str, Any]) -> dict[str, Any]:
    name = structured_schema.get("name")
    if not isinstance(name, str) or not name.strip():
        raise ModelGatewayError("structured_schema must include name")
    if structured_schema.get("strict") is not True:
        raise ModelGatewayError("structured_schema strict must be true")
    schema = structured_schema.get("schema")
    if not isinstance(schema, dict):
        raise ModelGatewayError("structured_schema schema must be an object")
    if schema.get("type") != "object":
        raise ModelGatewayError("structured_schema schema.type must be object")
    if schema.get("additionalProperties") is not False:
        raise ModelGatewayError("structured_schema schema.additionalProperties must be false")
    return {"type": "json_schema", **structured_schema}


def _responses_payload(
    messages: list[dict[str, Any]],
    config: ModelConfig,
    *,
    structured: bool = False,
    structured_schema: dict[str, Any] | None = None,
) -> dict[str, Any]:
    text_parts = []
    for message in messages:
        if message.get("type") in {"function_call", "tool_call"}:
            text_parts.append(
                {
                    "type": "function_call",
                    "call_id": str(message.get("call_id") or message.get("id") or ""),
                    "name": str(message.get("name") or ""),
                    "arguments": message.get("arguments") or "{}",
                }
            )
            continue
        if message.get("type") == "function_call_output":
            text_parts.append(
                {
                    "type": "function_call_output",
                    "call_id": str(message.get("call_id") or ""),
                    "output": str(message.get("output") or ""),
                }
            )
            continue
        role = message.get("role", "user")
        content = message.get("content", "")
        text_parts.append({"role": role, "content": content})
    payload: dict[str, Any] = {
        "model": config.model,
        "input": text_parts,
        "store": config.store,
        "reasoning": {"effort": config.reasoning_effort},
    }
    if structured:
        format_payload = _strict_json_schema_format(structured_schema) if structured_schema else {"type": "json_object"}
        payload["text"] = {"format": format_payload}
    tools = openai_tool_specs()
    if tools:
        payload["tools"] = tools
        payload["tool_choice"] = "auto"
    return payload


def parse_responses_text(body: dict[str, Any]) -> str:
    output = body.get("output")
    if isinstance(output, list):
        chunks: list[str] = []
        for item in output:
            if not isinstance(item, dict):
                continue
            content = item.get("content")
            if not isinstance(content, list):
                continue
            for part in content:
                if isinstance(part, dict) and isinstance(part.get("text"), str):
                    chunks.append(part["text"])
        if chunks:
            return "".join(chunks).strip()
    if isinstance(body.get("output_text"), str):
        return body["output_text"].strip()
    raise ModelGatewayError("Responses body did not include output text")


def parse_responses_tool_calls(body: dict[str, Any]) -> list[dict[str, Any]]:
    output = body.get("output")
    if not isinstance(output, list):
        return []
    calls: list[dict[str, Any]] = []
    for item in output:
        if not isinstance(item, dict):
            continue
        item_type = item.get("type")
        if item_type in {"function_call", "tool_call"} and isinstance(item.get("name"), str):
            calls.append(
                {
                    "id": item.get("call_id") or item.get("id"),
                    "name": item["name"],
                    "arguments": item.get("arguments") or "{}",
                }
            )
            continue
        if item_type == "message":
            for part in item.get("content") or []:
                if not isinstance(part, dict):
                    continue
                if part.get("type") in {"function_call", "tool_call"} and isinstance(part.get("name"), str):
                    calls.append(
                        {
                            "id": part.get("call_id") or part.get("id"),
                            "name": part["name"],
                            "arguments": part.get("arguments") or "{}",
                        }
                    )
    return calls


def parse_responses_json(body: dict[str, Any]) -> dict[str, Any]:
    text = parse_responses_text(body)
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as exc:
        extracted = _extract_first_json_object(text)
        if extracted is None:
            raise ModelGatewayError("Responses output was not valid JSON") from exc
        parsed = json.loads(extracted)
    if not isinstance(parsed, dict):
        raise ModelGatewayError("Responses output JSON must be an object")
    return parsed


def _extract_first_json_object(text: str) -> str | None:
    start = text.find("{")
    if start < 0:
        return None
    depth = 0
    in_string = False
    escaped = False
    for index in range(start, len(text)):
        char = text[index]
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
            continue
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return text[start : index + 1]
    return None


def _chat_messages(messages: list[dict[str, Any]]) -> list[dict[str, str]]:
    chat_messages: list[dict[str, str]] = []
    for message in messages:
        if message.get("type") in {"function_call", "tool_call", "function_call_output"}:
            continue
        role = str(message.get("role", "user"))
        if role not in {"system", "developer", "user", "assistant"}:
            role = "user"
        chat_messages.append({"role": role, "content": str(message.get("content", ""))})
    return chat_messages


def _schema_instruction(structured_schema: dict[str, Any] | None) -> dict[str, str]:
    if structured_schema:
        schema_text = json.dumps(structured_schema, ensure_ascii=False, separators=(",", ":"))
        return {
            "role": "system",
            "content": (
                "Return only a valid JSON object matching this response schema. "
                f"Schema: {schema_text}"
            ),
        }
    return {"role": "system", "content": "Return only a valid JSON object."}


def _chat_completion_payload(
    messages: list[dict[str, Any]],
    config: ModelConfig,
    *,
    structured: bool = False,
    structured_schema: dict[str, Any] | None = None,
) -> dict[str, Any]:
    chat_messages = _chat_messages(messages)
    payload: dict[str, Any] = {
        "model": config.model,
        "messages": chat_messages,
    }
    if structured:
        if structured_schema:
            _strict_json_schema_format(structured_schema)
        payload["messages"] = [*chat_messages, _schema_instruction(structured_schema)]
        payload["response_format"] = {"type": "json_object"}
    return payload


def parse_chat_completion_text(body: dict[str, Any]) -> str:
    choices = body.get("choices")
    if isinstance(choices, list):
        chunks: list[str] = []
        for choice in choices:
            if not isinstance(choice, dict):
                continue
            message = choice.get("message")
            if not isinstance(message, dict):
                continue
            content = message.get("content")
            if isinstance(content, str):
                chunks.append(content)
            elif isinstance(content, list):
                for part in content:
                    if isinstance(part, dict) and isinstance(part.get("text"), str):
                        chunks.append(part["text"])
        if chunks:
            return "".join(chunks).strip()
    raise ModelGatewayError("Chat completions body did not include message content")


def parse_chat_completion_json(body: dict[str, Any]) -> dict[str, Any]:
    text = parse_chat_completion_text(body)
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ModelGatewayError("Chat completions output was not valid JSON") from exc
    if not isinstance(parsed, dict):
        raise ModelGatewayError("Chat completions output JSON must be an object")
    return parsed


def _response_to_dict(response: Any) -> dict[str, Any]:
    if isinstance(response, dict):
        return response
    if hasattr(response, "model_dump"):
        dumped = response.model_dump()
        if isinstance(dumped, dict):
            return dumped
    if hasattr(response, "to_dict"):
        dumped = response.to_dict()
        if isinstance(dumped, dict):
            return dumped
    raise ModelGatewayError("Responses SDK result was not a dictionary-like object")


def _openai_client_class() -> Any:
    if OpenAI is not None:
        return OpenAI
    try:
        from openai import OpenAI as imported_openai
    except ModuleNotFoundError as exc:
        raise ModelGatewayError("openai package is not installed") from exc
    return imported_openai


class ModelGateway:
    def __init__(self, config: ModelConfig | None = None) -> None:
        self.config = config or ModelConfig.from_env()

    def _client_kwargs(self) -> dict[str, Any]:
        kwargs: dict[str, Any] = {
            "api_key": self.config.api_key,
            "base_url": self.config.base_url,
            "timeout": self.config.timeout_seconds,
        }
        if not self.config.trust_env_proxy:
            kwargs["http_client"] = httpx.Client(trust_env=False, timeout=self.config.timeout_seconds)
        return kwargs

    def complete_text(self, messages: list[dict[str, Any]], *, purpose: str = "text") -> str:
        if self.config.wire_api in CHAT_COMPLETIONS_WIRE_APIS:
            body = self._request_chat_completions(messages, structured=False, purpose=purpose)
            return parse_chat_completion_text(body)
        body = self._request(messages, structured=False, purpose=purpose)
        return parse_responses_text(body)

    def complete_structured(
        self,
        messages: list[dict[str, Any]],
        *,
        purpose: str = "structured",
        structured_schema: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if self.config.wire_api in CHAT_COMPLETIONS_WIRE_APIS:
            body = self._request_chat_completions(
                messages,
                structured=True,
                structured_schema=structured_schema,
                purpose=purpose,
            )
            return parse_chat_completion_json(body)
        if structured_schema is None:
            body = self._request(messages, structured=True, purpose=purpose)
        else:
            body = self._request(messages, structured=True, structured_schema=structured_schema, purpose=purpose)
        return parse_responses_json(body)

    def complete_structured_with_tools(
        self,
        messages: list[dict[str, Any]],
        *,
        purpose: str = "structured",
        structured_schema: dict[str, Any] | None = None,
        tool_context: dict[str, Any] | None = None,
        max_tool_rounds: int = 2,
    ) -> dict[str, Any]:
        if self.config.wire_api in CHAT_COMPLETIONS_WIRE_APIS:
            return {
                "decision": self.complete_structured(
                    messages,
                    purpose=purpose,
                    structured_schema=structured_schema,
                ),
                "tool_trace": [
                    {"status": "skipped", "reason": "chat_completions_wire_api_does_not_run_tool_loop"}
                ],
                "tool_messages": [],
                "raw_response": {},
            }
        current_messages = list(messages)
        all_trace: list[dict[str, Any]] = []
        tool_messages: list[dict[str, Any]] = []
        for _ in range(max_tool_rounds + 1):
            if structured_schema is None:
                body = self._request(current_messages, structured=True, purpose=purpose)
            else:
                body = self._request(
                    current_messages,
                    structured=True,
                    structured_schema=structured_schema,
                    purpose=purpose,
                )
            calls = parse_responses_tool_calls(body)
            if not calls:
                return {
                    "decision": parse_responses_json(body),
                    "tool_trace": all_trace,
                    "tool_messages": tool_messages,
                    "raw_response": body,
                }
            trace = dispatch_model_tool_calls(calls, **(tool_context or {}))
            all_trace.extend(trace)
            call_items = response_function_call_items(calls)
            response_items = tool_trace_response_items(trace)
            if call_items:
                tool_messages.extend(call_items)
                current_messages.extend(call_items)
            if response_items:
                tool_messages.extend(response_items)
                current_messages.extend(response_items)
            else:
                message = tool_trace_message(trace)
                tool_messages.append(message)
                current_messages.append(message)
        raise ModelGatewayError("Model requested too many tool-call rounds")

    def _request(
        self,
        messages: list[dict[str, Any]],
        *,
        structured: bool,
        purpose: str,
        structured_schema: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if not self.config.api_key:
            raise ModelGatewayError("OPENAI_API_KEY is not configured")
        if self.config.wire_api != "responses":
            raise ModelGatewayError(f"Unsupported wire_api: {self.config.wire_api}")
        payload = _responses_payload(
            messages,
            self.config,
            structured=structured,
            structured_schema=structured_schema,
        )
        if self.config.send_metadata:
            payload["metadata"] = {"purpose": purpose}
        client_class = _openai_client_class()
        client = client_class(**self._client_kwargs())
        try:
            return _response_to_dict(client.responses.create(**payload))
        except Exception as exc:
            if _is_unsupported_metadata_error(exc):
                fallback_payload = {key: value for key, value in payload.items() if key != "metadata"}
                try:
                    return _response_to_dict(client.responses.create(**fallback_payload))
                except Exception as fallback_exc:
                    raise ModelGatewayError(f"Model gateway request failed: {fallback_exc}") from fallback_exc
            raise ModelGatewayError(f"Model gateway request failed: {exc}") from exc

    def _request_chat_completions(
        self,
        messages: list[dict[str, Any]],
        *,
        structured: bool,
        purpose: str,
        structured_schema: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if not self.config.api_key:
            raise ModelGatewayError("OPENAI_API_KEY is not configured")
        payload = _chat_completion_payload(
            messages,
            self.config,
            structured=structured,
            structured_schema=structured_schema,
        )
        client_class = _openai_client_class()
        client = client_class(**self._client_kwargs())
        try:
            return _response_to_dict(client.chat.completions.create(**payload))
        except Exception as exc:
            if structured and _is_unsupported_response_format_error(exc):
                fallback_payload = {key: value for key, value in payload.items() if key != "response_format"}
                try:
                    return _response_to_dict(client.chat.completions.create(**fallback_payload))
                except Exception as fallback_exc:
                    raise ModelGatewayError(f"Model gateway request failed: {fallback_exc}") from fallback_exc
            raise ModelGatewayError(f"Model gateway request failed: {exc}") from exc


def _is_unsupported_metadata_error(exc: Exception) -> bool:
    text = str(exc).lower()
    return "metadata" in text and "unsupported parameter" in text


def _is_unsupported_response_format_error(exc: Exception) -> bool:
    text = str(exc).lower()
    return "response_format" in text and ("unsupported" in text or "unknown" in text)


def response_function_call_items(calls: list[dict[str, Any]]) -> list[dict[str, str]]:
    items: list[dict[str, str]] = []
    for call in calls:
        call_id = call.get("id") or call.get("call_id")
        name = call.get("name")
        if not call_id or not name:
            continue
        items.append(
            {
                "type": "function_call",
                "call_id": str(call_id),
                "name": str(name),
                "arguments": str(call.get("arguments") or "{}"),
            }
        )
    return items
