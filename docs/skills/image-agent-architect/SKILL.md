---
name: image-agent-architect
description: Use when designing or reviewing Image Agent architecture, module boundaries, LangGraph orchestration, OpenAI SDK chat gateway behavior, Responses-native agent contracts, API/result contracts, workflow integration points, frontend data flow, or changes that might blur responsibilities between FastAPI, workflow runners, RAG, and React/Vite.
---

# Image Agent Architect

Design Image Agent changes by protecting deterministic product contracts and keeping agent reasoning separate from workflow execution.

## Trigger Rules

Use this skill before architectural changes, feature slicing, cross-module refactors, agent orchestration changes, result-summary changes, workflow API design, or frontend/backend contract decisions.

Use `image-agent-workflow-runner` for execution details and `image-agent-rag-curator` for knowledge-base ingestion.

## Operating Rules

1. Keep deterministic state in backend services and database records, not in LLM memory.
2. Keep the chat/agent layer read-only for long workflows: it may inspect and recommend, but should not directly launch expensive processing from free-form chat.
3. Define contracts before UI: endpoint shape, task state, result-summary fields, artifact URLs, and error vocabulary.
4. Preserve module boundaries: ingest detects and stages data; workflow runners validate/execute; result builders summarize artifacts; RAG retrieves text; the frontend renders contracts.
5. Treat backend task/output records as the source of truth over RAG snippets and frontend assumptions.
6. Add compatibility adapters rather than silently changing old workflow names or result fields.
7. Design failure states as first-class responses with safe user messages and machine-readable details.

## Reference Loading

- Read `references/module-boundaries.md` before proposing or reviewing code ownership.
- Read `references/contracts-and-frontend.md` before changing API, task, result-summary, artifact, or UI data contracts.
- Read existing `../image-agent-developer/references/contracts.md` when exact endpoint or workflow names matter.
- Read existing `../image-agent-developer/references/repo-map.md` before mapping a plan to files.

## Output Shape

For architecture guidance, return:

1. Decision summary.
2. Affected modules and boundaries.
3. Contract changes or compatibility guarantees.
4. Frontend impact.
5. Tests and migration notes.

For reviews, lead with boundary violations, contract risks, missing tests, and stale compatibility assumptions.

## Eval Hints

Useful evals ask for a new workflow, LangGraph tool, result-summary panel, or RAG behavior under conflicting requirements. Passing answers keep execution out of chat, define typed contracts first, and identify frontend compatibility work.
