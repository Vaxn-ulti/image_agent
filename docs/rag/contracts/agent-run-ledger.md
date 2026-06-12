---
source_type: rag_contract
contract: agent_run_ledger
status: current_contract
retrieved_date: 2026-06-10
---

# Agent Run Ledger Contract RAG

## Purpose

The agent-run ledger is the durable agent-run trace for Image Agent orchestration. It records privacy-safe lifecycle traceability for `/agent/runs`, the server-side resume confirmation path, and model/tool boundary decisions.

The ledger is not the source of truth for workflow outputs. Backend task rows remain the task-state source of truth; backend task rows remain authoritative. The result-summary JSON remains the output source of truth; result-summary JSON remains authoritative for completed workflow outputs.

`/agent/runs` and `/agent/runs/{thread_id}/resume` request bodies are strict
contracts: unknown request fields return `request_contract_violation` through
the `agent_api_error.v1` envelope instead of being ignored or stored in the
ledger.

Pending server-side confirmations use the SQLite `agent_confirmations` table as
their durable source of truth when the database has been initialized. The legacy
JSON thread file is only a compatibility mirror/fallback for lightweight tests
and older records. Confirmation transitions are audited in
`agent_confirmation_events`.

## Durable Identity

Each run row should include:

- `agent_run_id`
- `thread_id` when a pending confirmation exists
- `expires_at` for pending server-side confirmations
- `project_id`, `series_id`, `workflow_type`, and `task_id` when known
- `created_at`, `updated_at`, and `finished_at`
- `model_gateway_access`
- `message_sha256` or another redacted user message summary, never raw prompt text

Each confirmation row should include:

- `thread_id`
- `status`
- `project_id`, `series_id`, `workflow_type`, `qsiprep_task_id`, and `action_lane` when known
- `confirmation_fingerprint`
- `expires_at`, `created_at`, `updated_at`, and `consumed_at`
- server-side confirmation, decision, selected skill, and retrieved-context JSON for resume validation only
- safe metadata, never API keys, patient identifiers, host paths, or raw image contents

## Lifecycle Events

Use stable event names:

- `agent_run_created`
- `agent_run_started`
- `agent_run_completed`
- `agent_run_failed`
- `agent_run_cancelled`
- `agent_run_skipped`

The terminal run `status` may preserve the agent response status, such as `answered`, `confirmation_required`, `task_created`, `blocked`, `failed`, `cancelled`, or `skipped`.

## Trace Fields

The ledger may store safe trace metadata:

- `intent`
- `action_lane`
- `selected_skill`
- `rag_mode`
- retrieved document source ids, not full snippets
- `tool_invocations`
- confirmation fingerprint

Production task creation remains backend-gated; production task creation remains gated outside the planner loop. Planner function tools may read, retrieve, and preflight, but `create_workflow_task` runs only after the server-side resume confirmation path verifies a matching server-side confirmation.

Pending confirmations are single-use. A successful approved resume must move the thread out of `pending_confirmation`, even when the caller only reaches `ready_to_launch` without a task executor. Expired confirmations return blocked with `production_task_created=false` and an `agent.confirmation_expired` event.

Confirmation event names:

- `confirmation_created`
- `confirmation_marked`

Events should record `from_status`, `to_status`, redacted metadata, and
`created_at`. Consumers should use these events for auditability instead of
reading legacy JSON files directly.

## Query Endpoint

`GET /agent/runs/{agent_run_id}` returns a ledger-only envelope. It is not the original agent result and must not replay the original answer, prompt, project context, RAG snippets, or confirmation payload.

Allowed response fields include:

- `agent_run_id`
- lifecycle status and timestamps
- project, series, task, thread, and workflow ids when known
- `model_gateway_access`
- `message_sha256`
- `safe_metadata`
- `retrieved_sources`
- `tool_invocations`
- lifecycle `events`

The lookup is for operations and future frontend traceability. It should explain which agent gate was reached, but do not expose raw answer text or raw retrieval text.

`GET /projects/{project_id}/agent-runs` returns project-scoped agent-run history as a safe project run summary list. It should sort newest first and include `event_count` instead of full lifecycle events. Use the single-run lookup for full safe event history.

Each list item may include `agent_run_id`, `request_type`, `status`, safe ids, `intent`, `action_lane`, `selected_skill`, `message_sha256`, `model_gateway_access`, `safe_metadata`, and timestamps. It should not include raw answer text, raw prompt text, raw RAG snippets, full confirmation payloads, or host paths.

Additional safety rules:

- safe_metadata excludes free-form model text. Do not store `recommended_next_step`, `tool_chain_hint`, or similar model text in exposed ledger metadata.
- absolute host paths are not valid retrieved_sources. Keep only repository-relative/document-relative source ids.
- `error_message` should use the fixed value `redacted_error_summary` for exposed ledger failures; the detailed exception belongs in server logs, not the API ledger envelope.
- lookup/list responses re-sanitize stored JSON before returning it. safe_metadata uses an allowlist, retrieved_sources expose source ids only, and titles and snippets are not ledger fields.

## Privacy Boundary

The ledger is for privacy-safe lifecycle traceability. It must not become a prompt, data, or output dump.

Rules:

- do not store raw image contents
- do not expose patient identifiers
- do not expose full sensitive host paths
- do not expose API keys, bearer tokens, FreeSurfer license text, or raw DICOM contents
- do not persist full model prompts, raw RAG snippets, full project context, raw DICOM metadata, or vendor secrets

Store safe ids, hashes, redacted summaries, lifecycle statuses, and backend record links instead.

## Answering With Ledger Evidence

When answering a user question, use the agent-run ledger to explain what the agent attempted and which server-side gate it reached. Use backend task rows and result-summary JSON for actual workflow state and output claims.
