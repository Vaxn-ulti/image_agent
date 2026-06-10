---
source_type: rag_vendor
source_url: https://platform.openai.com/docs/guides/function-calling?api-mode=responses, https://platform.openai.com/docs/guides/tools?api-mode=responses, https://raw.githubusercontent.com/openai/openai-python/main/README.md, https://developers.openai.com/api/docs/api-reference/responses/create
raw_source_ids: openai_function_calling_responses, openai_tools_responses, openai_python_sdk_readme, openai_responses_api_reference
retrieved_date: 2026-06-07
status: curated_summary
---

# OpenAI Official Responses Function Tools

## Purpose / Scope

Use this source when maintaining the Image Agent model gateway, tool registry, or agent prompts that call the OpenAI Responses API through the local reverse-tunnel gateway.

This is an architecture contract for the LLM boundary. It is not a license to expose shell, Docker, raw image contents, patient metadata, API keys, or production task launch privileges directly to the model.

## Container/CLI Usage

No container or shell command should be exposed to the model for this contract.

Image Agent uses the official OpenAI Python SDK at the model boundary. The gateway should construct an `OpenAI` client with the configured API key and reverse-tunnel/base URL, then call `responses.create` with a Responses-native payload. Backend-defined function tools should be represented as top-level Responses function tools:

```json
{
  "type": "function",
  "name": "read_task_events",
  "description": "Read task events/log tail for progress and failures.",
  "parameters": {
    "type": "object",
    "required": ["task_id"],
    "properties": {
      "task_id": {"type": "integer"}
    }
  },
  "strict": false
}
```

The gateway should use `tool_choice: "auto"` when exposing the allowlisted backend tools.

The official OpenAI Python SDK source is the contract for the client shape: instantiate an `OpenAI client`, configure credentials/base URL through the backend configuration layer, and use the typed SDK resource (`client.responses.create(...)`) rather than direct `urllib` calls to `/responses`. The Responses API reference is the contract for the request/response resource boundary.

When the model returns a function call, backend code dispatches only allowlisted tools. Tool results should be returned to the model as typed Responses input items:

```json
{
  "type": "function_call_output",
  "call_id": "call_123",
  "output": "{\"status\":\"ok\"}"
}
```

## Structured Output Contract

For model decisions that must be JSON, use Responses `text.format` with `{"type":"json_schema","name":...,"schema":...,"strict":true}` when a schema is available.

Image Agent should prefer `json_schema` whenever a schema is available. `json_object` is only a compatibility fallback for older JSON mode or paths without schema support.

Use `text.format`, not Chat-Completions-style `response_format`, for Responses structured outputs. strict structured outputs must still be backend-validated before the decision is trusted.

Do not represent structured JSON decisions as fake function calls. Function tools are only for backend tool requests, and structured decisions remain model text constrained by the Responses text format contract.

OpenAI Code Interpreter container terminology is separate from Image Agent workflow container terminology. Code Interpreter containers are model/tool execution sandboxes, not Image Agent production workflow containers; do not expose Image Agent workflow containers, shell, Docker, or production task launch privileges directly to the model. Image Agent workflow containers remain backend-orchestrated and server-side gated.

## Important Inputs/Outputs

Inputs:

- `OPENAI_API_KEY`, never returned by status endpoints or RAG;
- `OPENAI_BASE_URL`, often the local reverse-tunnel URL on the remote backend;
- `OPENAI_MODEL` and `OPENAI_REVIEW_MODEL`;
- backend-generated function tool specs from `app.agent.tool_registry`.

Outputs:

- model text or structured JSON decisions;
- model-requested function calls with `call_id`, tool name, and JSON arguments;
- backend tool traces, sanitized and bounded before being returned as `function_call_output`;
- status metadata such as `model_gateway_access`, without secret values.

## Image Agent Notes

- Use the OpenAI SDK `responses.create` path with the Responses API shape. Do not reintroduce hand-rolled `/responses` HTTP transport or Chat-Completions-style nested tool specs such as `{"type":"function","function":{...}}`.
- Keep the SDK boundary explicit in reviews: the implementation should import the official OpenAI Python SDK, construct an `OpenAI client`, and call `client.responses.create(...)`.
- Keep tool execution backend-first. The model requests a registered function; backend code enforces arguments, project scope, production gating, and redaction.
- `create_workflow_task` is not a normal planner-loop action. It may execute only through the server-side resume confirmation path after explicit user approval.
- Return function call results with `function_call_output` and the original `call_id`. A plain text `Tool results JSON` message is only a compatibility fallback for malformed calls without a call id.
- do not expose API keys, bearer tokens, FreeSurfer license text, raw image contents, patient identifiers, or full sensitive host paths in prompts, tool outputs, logs, RAG documents, or status endpoints.
- RAG may document the contract and retrieved official sources, but backend records, registered outputs, and server-side confirmations remain authoritative for current runtime state.
