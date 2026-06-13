# API Contract

Base URL: `http://<server>:8000`.

## Auth

`POST /auth/login`
Request: `{ "username": "demo", "password": "demo" }`
Response: `{ "access_token": "mvp-token", "token_type": "bearer", "user": {"id": 1, "username": "demo"} }`

## Projects

`GET /projects`
Response: `[{ "id": 1, "name": "Project", "description": "", "created_at": "..." }]`

`POST /projects`
Request: `{ "name": "Project", "description": "optional" }`
Response: project object.

## Upload/Series

`POST /projects/{project_id}/upload` multipart field `file`.
Response: `{ "file": {...}, "series": {...} }`.

`GET /projects/{project_id}/series`
Response: list of series objects.

`GET /series/{series_id}`
Response: one series object.

Series fields: `id, project_id, file_id, modality, format, confidence, metadata, status, created_at`.

## Tasks

`POST /series/{series_id}/run`
Request: `{ "workflow_type": "t1_deepprep_mock" }`
Response: task object.

`GET /tasks/{task_id}` returns task.
`GET /tasks/{task_id}/logs` returns `{ "task_id": 1, "text": "..." }`.
`GET /tasks/{task_id}/outputs` returns output list.

Task states: `queued`, `running`, `completed`, `failed`, `cancelled`.

## Agent Runs

Primary product agent entrypoint. Frontend integrations should use this family
instead of legacy `/chat`.

Agent run contract version: `agent_run.v1`.
Lookup contract version: `agent_run_lookup.v1`.
Project history contract version: `project_agent_run_history.v1`.
Error contract version: `agent_api_error.v1`.

The Agent API request bodies are strict. Unknown request fields are rejected
instead of ignored, and unknown request fields return `request_contract_violation`
using the `agent_api_error.v1` envelope.
For `/agent/runs/{thread_id}/resume`, nested confirmation fields are also strict:
only the stable workflow-confirmation fields are accepted.

Stable agent run states:

- `running`
- `answered`
- `confirmation_required`
- `needs_clarification`
- `preflight_failed`
- `toolchain_proposed`
- `ready_to_launch`
- `task_created`
- `completed`
- `blocked`
- `failed`
- `cancelled`
- `skipped`

`POST /agent/runs`
Request: `{ "project_id": 1, "message": "Run T1 DeepPrep for series 11" }`
Response:

```json
{
  "contract_version": "agent_run.v1",
  "agent_run_id": "agent_run_...",
  "status": "confirmation_required",
  "request_type": "run",
  "thread_id": "thread_...",
  "project_id": 1,
  "series_id": 11,
  "workflow_type": "t1_deepprep_anat_report",
  "intent": "run_workflow",
  "action_lane": "fixed_workflow",
  "selected_skill": "image-agent-workflow-runner",
  "confirmation": { "type": "workflow_execution" },
  "safe_metadata": { "schema_version": 1 },
  "retrieved_sources": [
    { "source": "docs/rag/workflows/t1_deepprep_anat_report.md", "source_type": "rag_workflow" }
  ],
  "tool_invocations": [
    { "stage": "planner", "tool": "retrieve_reference_context", "status": "ok" }
  ],
  "events": []
}
```

The response intentionally excludes raw prompts, raw RAG snippets, absolute
host paths, API keys, and free-text patient identifiers. Runner statuses outside
the stable enum are normalized to `failed` and recorded in
`safe_metadata.contract_status_normalized_from` for audit. Nested `task`,
`tool_input`, and `confirmation` payloads use allowlisted frontend-safe scalar
fields only; runner fields such as `log_path`, `output_dir`, backend absolute
paths, free-text nested `error_message`, raw nested provenance, and arbitrary
dictionaries are not part of the Agent API response contract.

`GET /agent/runs/{agent_run_id}`
Response: same safe run fields as `agent_run_lookup.v1`, populated from the
privacy-safe run ledger. Lookup responses may include ledger-only audit fields
such as `message_sha256`, `error_message`, `created_at`, `updated_at`, and
`finished_at`; these fields are redacted and never contain the raw prompt,
patient identifiers, host paths, API keys, or raw retrieved snippets.

`POST /agent/runs/{thread_id}/resume`
Request:

```json
{
  "approved": true,
  "confirmation": {
    "type": "workflow_execution",
    "project_id": 1,
    "series_id": 11,
    "workflow_type": "t1_deepprep_anat_report"
  }
}
```

Response: `agent_run.v1`. Approved fixed-workflow confirmations may return
`status=task_created` with a backend task object. Rejected or mismatched
confirmations return stable blocked/cancelled states and never create production
tasks.

Agent run errors use the same envelope across this endpoint family:

```json
{
  "detail": {
    "contract_version": "agent_api_error.v1",
    "code": "agent_model_call_failed",
    "message": "Agent model call failed.",
    "agent_run_id": "agent_run_..."
  }
}
```

Stable error codes include `message_required`, `agent_run_not_found`,
`agent_model_call_failed`, and `agent_resume_failed`. Error details must not
echo raw prompts, backend absolute paths, API keys, patient identifiers, raw
model errors, or raw RAG snippets.

`GET /projects/{project_id}/agent-runs`
Response:

```json
{
  "contract_version": "project_agent_run_history.v1",
  "project_id": 1,
  "agent_runs": [
    {
      "agent_run_id": "agent_run_...",
      "request_type": "run",
      "project_id": 1,
      "status": "answered",
      "model_gateway_access": "openai_sdk_gateway",
      "event_count": 3,
      "safe_metadata": { "schema_version": 1 }
    }
  ]
}
```

Project history is ledger-derived and safe for UI timelines. It does not expose
raw messages, raw answers, raw snippets, or backend absolute paths.

## Chat Compatibility

`POST /chat`
Request: `{ "project_id": 1, "message": "task status 1" }`
Response:

```json
{
  "contract_version": "chat_compat.v1",
  "legacy_endpoint": true,
  "primary_endpoint": "/agent/runs",
  "reply": "...",
  "references": [{ "type": "task", "id": 1 }],
  "provider": "rules",
  "provider_error": "",
  "intent": "status",
  "recommended_next_step": "Inspect backend task state before launching a new workflow.",
  "tool_chain_hint": null,
  "tool_invocations": [],
  "rag_mode": "local_persistent_index"
}
```

`/chat` is a compatibility endpoint. New product surfaces should use
`/agent/runs` so confirmation, resume, ledger, project history, RAG provenance,
and future remote acceptance evidence share one contract family.
