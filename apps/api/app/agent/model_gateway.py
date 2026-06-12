from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any

from app.agent.tool_dispatcher import dispatch_model_tool_calls, tool_trace_message, tool_trace_response_items
from app.agent.tool_registry import openai_tool_specs


OpenAI = None


class ModelGatewayError(RuntimeError):
    pass


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


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

    @classmethod
    def from_env(cls) -> "ModelConfig":
        provider = os.environ.get("MODEL_PROVIDER", "OpenAI")
        model = os.environ.get("OPENAI_MODEL") or os.environ.get("MODEL", "gpt-5.5")
        return cls(
            provider=provider,
            api_key=os.environ.get("OPENAI_API_KEY", ""),
            base_url=os.environ.get("OPENAI_BASE_URL", "http://127.0.0.1:8080"),
            model=model,
            review_model=os.environ.get("OPENAI_REVIEW_MODEL") or os.environ.get("REVIEW_MODEL", model),
            wire_api=os.environ.get("OPENAI_WIRE_API", "responses").strip().lower() or "responses",
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
        raise ModelGatewayError("Responses output was not valid JSON") from exc
    if not isinstance(parsed, dict):
        raise ModelGatewayError("Responses output JSON must be an object")
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

    def complete_text(self, messages: list[dict[str, Any]], *, purpose: str = "text") -> str:
        body = self._request(messages, structured=False, purpose=purpose)
        return parse_responses_text(body)

    def complete_structured(
        self,
        messages: list[dict[str, Any]],
        *,
        purpose: str = "structured",
        structured_schema: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
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
        client = client_class(api_key=self.config.api_key, base_url=self.config.base_url, timeout=self.config.timeout_seconds)
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


def _is_unsupported_metadata_error(exc: Exception) -> bool:
    text = str(exc).lower()
    return "metadata" in text and "unsupported parameter" in text


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
