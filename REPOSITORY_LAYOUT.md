# Repository Layout

This document summarizes the public repository structure for Image Agent.

## Included

- `apps/api`: FastAPI backend, LangGraph agent orchestration, workflow
  registry, task services, upload/result APIs, and runtime helpers.
- `apps/console`: React/Vite console for project upload, agent interaction,
  workflow launch, task observation, results, reports, QC, and export.
- `apps/desktop`: lightweight desktop-oriented client assets.
- `scripts`: portable bootstrap, hygiene, and Docker access helpers.
- `docs/rag`: curated official-source RAG material and workflow capability
  documents.
- `docs/skills`: Image Agent operator and workflow-runner references.
- `docs/workflows` and selected architecture/deployment docs: portable product
  documentation.

## Excluded

Local run logs, server-specific acceptance evidence, private deployment paths,
generated build outputs, virtual environments, `.env` files, local databases,
patient data, and tokens are intentionally excluded from the public repository.

## Configuration

Provide deployment-specific values through environment variables, secret
managers, or untracked local files. Do not commit API keys, model gateway
tokens, proxy URLs, server IPs, operator-specific absolute paths, or generated
runtime evidence.
