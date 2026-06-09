# Module Boundaries

## Ownership Map

Keep responsibilities narrow:

- Ingest: upload handling, inventory, modality metadata, BIDS-like placement, collision-safe naming.
- Workflow eligibility: deterministic checks from series metadata, sidecars, prior tasks, and configured workflow registry.
- Workflow runners: validate-only checks, command construction, container/task execution, logs, output discovery.
- Result builders: parse real artifacts into result summaries, scientific reports, tables, and safe artifact metadata.
- Agent orchestration: classify user intent, inspect backend state, retrieve relevant docs, recommend next actions.
- RAG: store curated product knowledge and return cited snippets, not executable truth.
- Frontend: render project, series, task, result-summary, artifact, and report contracts without reconstructing workflow logic.

## LangGraph and Tool Boundary

Agent graph nodes may call read-only tools such as:

- inspect project/series inventory;
- inspect task status and logs;
- inspect registered outputs and result summaries;
- verify scientific report artifacts;
- retrieve RAG snippets;
- recommend the next safe action.

The graph should not directly run long workflows from open-ended chat. If the product later supports chat-launched workflows, require explicit confirmation and route through the same deterministic API used by the UI.

## Boundary Smells

- The frontend infers modality from filenames instead of backend metadata.
- RAG text decides workflow eligibility without backend checks.
- A chat response promises outputs that no result-summary records show.
- A workflow runner returns ad hoc payloads instead of the shared task/result contract.
- Container logs or local absolute paths leak directly into user-facing UI.
- New features require editing several unrelated modules because contracts were implicit.
