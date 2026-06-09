---
name: image-agent-rag-curator
description: Use when curating Image Agent RAG or knowledge-base content, extracting workflow facts from docs/scripts/logs, resolving source conflicts, assigning metadata and priority, excluding sensitive data, or preparing retrieval snippets for the built-in agent.
---

# Image Agent RAG Curator

Curate RAG content so retrieval supports grounded product answers without becoming a hidden source of executable truth.

## Trigger Rules

Use this skill when adding, editing, auditing, or prioritizing Image Agent RAG sources; extracting facts from workflow scripts; handling conflicting docs; excluding sensitive content; or preparing metadata for retrieval.

Use `image-agent-operator` for live user replies and `image-agent-architect` for contract design.

## Operating Rules

1. Attach source metadata to every curated item: source path/URL, source type, date or commit when known, modality, workflow type, environment, evidence level, and sensitivity status.
2. Prefer current backend contracts, code, real task/result records, and verified scripts over older prose docs.
3. Store conflicts explicitly instead of blending sources into a false consensus.
4. Extract script facts carefully: commands, required inputs, output paths, env vars, runtime limits, and failure conditions. Do not copy secrets or patient data.
5. Keep RAG snippets concise, retrieval-friendly, and scoped to product behavior.
6. Exclude sensitive or unsafe material: patient identifiers, raw medical image paths intended to be private, credentials, license text, DB dumps, raw logs with PHI, and local secrets.
7. Assign RAG priority so stable contracts outrank historical notes and examples.

## Reference Loading

- Read `references/source-metadata-and-priority.md` before adding or re-ranking sources.
- Read `references/conflicts-and-script-extraction.md` before reconciling docs, code, scripts, or logs.
- Read `references/sensitive-exclusion.md` before ingesting logs, reports, screenshots, or raw output directories.
- Read `../../rag/workflows/workflow_launchability_matrix.md` when resolving workflow support, maturity, or launchability questions.
- For remote smoke proof, `/agent/rag/query` launchability answers must cite `docs/rag/workflows/workflow_launchability_matrix.md`; RAG status/index presence alone is not sufficient.
- Read existing `../image-agent-operator/references/product-context.md` for product workflow vocabulary.

## Output Shape

Return:

1. Sources reviewed.
2. Curated facts with metadata.
3. Conflicts and chosen priority.
4. Exclusions with reasons.
5. RAG update recommendation: add, revise, deprecate, or block.
6. Eval notes for retrieval behavior.

## Eval Hints

Good evals include stale QSIPrep docs conflicting with fast DTI code, scripts containing safe workflow facts plus secrets, logs with patient paths, and docs that overclaim BOLD support. Passing curation preserves metadata, ranks current backend facts first, and excludes sensitive content.
