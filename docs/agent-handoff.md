# Agent Handoff

## Backend Agent

Implement FastAPI routes, SQLite access, storage helpers, and chat tool routing. Do not alter frontend styling except API contract fixes.

## Workflow Agent

Implement NIfTI parsing and workflow runners under `imaging` and `workflows`. Keep all workflows deterministic and log every step.

## Frontend Agent

Implement React UI against documented API only. Do not assume database fields beyond API responses.

## Review/Test Agent

Run backend tests, frontend build, and a smoke flow. Fix small contract mismatches. Report remaining risks.
