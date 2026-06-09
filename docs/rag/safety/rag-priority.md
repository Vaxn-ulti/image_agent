# RAG Source Priority RAG

## Purpose / 目的

This document tells the image_agent how to rank retrieved information when answering questions about this project.

## Priority Order

1. Backend task records: current status, progress, workflow type, errors.
2. Registered outputs: artifact paths, output types, metadata.
3. Result-summary JSON: feature groups, provenance, structured outputs.
4. Scientific report summary: presentation artifacts generated from result-summary.
5. Runtime logs and task events: concrete failure/progress details.
6. Local workflow docs and curated RAG docs.
7. Vendor documentation summaries.
8. General neuroimaging knowledge.

## Non-Override Rule

RAG documents may explain concepts, but they must not override backend state for a specific project. If a doc says a workflow usually produces X but the task output registry lacks X, say X is expected but not registered for this task.

## Conflict Handling

- If backend says `failed` and a doc says the workflow is supported, answer that the workflow is supported in general but this task failed.
- If result-summary says `placeholder_outputs=true`, do not describe metrics as real.
- If vendor docs and local workflow docs differ, describe local implementation first and mention vendor behavior as reference.

## Retrieval Hint

Good answer structure:

1. "Current backend state..."
2. "Registered/summary outputs..."
3. "Relevant documentation context..."
4. "Next safe action..."

