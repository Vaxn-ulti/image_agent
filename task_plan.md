# Image Agent Product Maturity Plan

## Goal

Continue developing Image Agent until the agent product is mature and stable enough for real use. Do not tell the user to start frontend page design until the agent/API/RAG/workflow contracts are stable, remotely verified, and documented.

## Non-Negotiable Constraints

- Keep the agent architecture close to OpenAI SDK patterns: explicit gateway/client boundaries, structured Responses-style output, tool registry, durable run/thread state, and clear result contracts.
- RAG must be detailed, source-grounded, and based on real official container/vendor documentation that has been downloaded, curated, and recorded with original source metadata.
- RAG answers must state boundaries, expected outputs, and original sources. They must not imply local execution, diagnosis, or unsupported container behavior.
- Skills are maintained in a skill-creator style: clear trigger descriptions, progressive disclosure, references, test/eval prompts where useful, and explicit safety/edge-case boundaries.
- Workflow result images must rely on Docker/container-native QC and visualization artifacts. Local code may index, serve, validate, and display those artifacts, but must not pretend to regenerate official QC locally.
- Local workspace is for code and documentation only. Installation, smoke testing, runtime verification, and workflow execution belong on the remote server.
- Maintain work logs and Git backups throughout. Do not reset, clean, or delete user/WIP changes.
- Check commit/backup cadence regularly. A checkpoint commit or scoped backup should be recommended when the tree has large WIP, critical untracked planning/readiness files, more than about one hour of active work since the last checkpoint, or new remote-acceptance evidence.
- Use parallel subagents where work is independent. Route delegated tasks through subagents rather than duplicating them locally.

## BMAD-Inspired Operating Model

- Analyst/PM: product maturity criteria, readiness gaps, PRD/epic/story decomposition.
- Architect: SDK-like API shape, module boundaries, contracts, integration risks.
- RAG Curator: official source map, provenance, answer contracts, missing vendor docs.
- Skill Maintainer: skill-creator compliance, references, evals, trigger boundaries.
- Workflow QC: result artifact contracts, container-native QC provenance, remote-only verification.
- Operations: Git backup cadence, work-log discipline, remote test evidence.

## Phases

| Phase | Status | Exit Criteria |
| --- | --- | --- |
| 1. Repository Goal Setup | complete | Goal files and work-log created; development branch active; BMAD subagents dispatched. |
| 2. Readiness Audit | in_progress | Subagent findings merged into findings.md; prioritized epics and first stories selected. |
| 3. Contract Hardening | pending | Agent run, RAG answer, tool, workflow result, and artifact contracts are stable and covered by tests. |
| 4. Official RAG Expansion | pending | Missing official docs are downloaded/curated, source metadata recorded, and answer boundaries tested. |
| 5. Skill Maintenance | pending | Image Agent skills follow skill-creator structure and have eval prompts/backlog coverage. |
| 6. Remote Verification Loop | pending | Remote server install/test/run evidence is logged; local-only execution is avoided. |
| 7. Product Maturity Gate | pending | Stability/readiness checklist passes; only then notify user that frontend page design can begin. |

## Immediate Stories

1. Integrate BMAD-style read-only subagent findings into a product maturity backlog.
2. Add a stable `docs/product-readiness.md` gate that defines when frontend design is allowed. Status: complete locally, pending remote evidence before gate can pass.
3. Add/extend RAG answer contract tests for source provenance, boundaries, and official-doc source ids.
4. Add/extend workflow artifact contract tests for container-native QC image provenance.
5. Add/extend skill maintenance docs/evals for image-agent skills.
6. Establish a repeatable Git backup and remote verification log convention.
7. Keep a scheduled commit-cadence heartbeat active so the thread periodically checks whether a checkpoint commit or scoped backup is needed.

## Commit And Backup Cadence

- A thread heartbeat named `image-agent-commit-cadence-check` checks every 60 minutes.
- The heartbeat may inspect git status and recent history, but must not stage, commit, reset, clean, push, or delete anything unless the user explicitly asks.
- Recommend a checkpoint commit when WIP is large, critical readiness/planning files are untracked, or more than about one hour of active development has passed since the last checkpoint.
- Recommend a scoped backup before risky integration, before remote deployment packaging, and whenever strict remote acceptance JSON/verifier evidence is added.
- Keep frontend page design blocked regardless of commit status until `docs/product-readiness.md` has strict remote acceptance evidence.

## Current Branch

`codex/image-agent-product-maturity`

## Open Questions To Resolve From Evidence

- Which existing WIP changes are already intended for the current product-maturity goal?
- Which remote server commands and paths are authoritative for smoke testing?
- Which official vendor/container docs are already complete enough, and which need new source ingestion?
- Which agent API surfaces are mature enough to freeze for frontend consumption?

## Errors Encountered

| Error | Attempt | Resolution |
| --- | --- | --- |
| None yet in this planning phase. | - | - |
