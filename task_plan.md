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
- Avoid opening new subagents by default. Preserve already-completed subagent findings as evidence, and only use a small number of new subagents when work is clearly independent and the expected efficiency gain is high.

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
| 1. Repository Goal Setup | complete | Goal files and work-log created; development branch active; prior BMAD-style findings recorded. |
| 2. Readiness Audit | in_progress | Subagent findings merged into findings.md; prioritized epics and first stories selected. |
| 3. Agent API Contract Hardening | in_progress | `/agent/runs`, run lookup, resume, project history, and legacy `/chat` boundaries have stable contract versions, response models, status enums, and tests. |
| 4. Official RAG Metadata Standardization | in_progress | Workflow docs expose machine-readable official grounding, expected artifacts, unsupported boundaries, source ids, and answer-boundary tests. |
| 5. Workflow Artifact Contract Hardening | in_progress | `/artifact-manifest` is the frontend source of truth and separates container-native QC, derived scientific reports, and preview assets. |
| 6. Skill Maintenance | in_progress | Image Agent skills follow skill-creator structure and have routing, audit, eval, and stale-name coverage. |
| 7. Remote Verification Loop | pending | Remote server install/test/run evidence is logged; local-only execution is avoided. |
| 8. Product Maturity Gate | pending | Stability/readiness checklist passes; only then notify user that frontend page design can begin. |

## Immediate Stories

1. Freeze Agent API contracts for `/agent/runs`, `/agent/runs/{agent_run_id}`, `/agent/runs/{thread_id}/resume`, and project run history before frontend integration.
2. Keep `/chat` as legacy/compatibility unless explicitly promoted; `/agent/runs` is the primary agent product surface.
3. Standardize product DWI wording: production DWI is `dwi_fast_gpu_dti`; QSIPrep/QSIRecon/QSI full are legacy/incubation unless explicitly exposed as advanced legacy.
4. Standardize workflow RAG frontmatter and answer provenance before adding more corpus content.
5. Harden artifact manifest and native-QC boundaries so frontend display depends on container-native QC evidence and not derived report PNGs.
6. Improve skills via routing and static audit, not more long prose.
7. Define strict remote acceptance as the only release gate: current deployed commit, configured model gateway, real project/upload/task/run ids, artifact manifest, native QC, scientific report provenance, and verifier `passed`.
8. Keep a scheduled commit-cadence heartbeat active so the thread periodically checks whether a checkpoint commit or scoped backup is needed.

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
- Which official vendor/container docs beyond the current T1/BOLD/DWI/launchability set need new source ingestion?
- Which agent API surfaces are mature enough to freeze for frontend consumption?

## Current RAG Metadata Progress

- First workflow frontmatter slice completed for:
  - `docs/rag/workflows/t1_deepprep_anat_report.md`
  - `docs/rag/workflows/bold_fmriprep_xcpd_report.md`
  - `docs/rag/workflows/dwi_fast_gpu_dti.md`
  - `docs/rag/workflows/workflow_launchability_matrix.md`
- Required machine fields are now tested: `source_type`, `workflow_type`, `status`, `official_grounding`, `expected_artifacts`, and `unsupported_boundaries`.
- `rag_orchestration.py` fallback retrieval now preserves YAML-list metadata when `.rag_index` is missing or stale.
- `audit_rag_metadata.py` now validates raw official-source manifest entries directly: required fields, HTTPS URL, official source type, downloaded status, safe raw-snapshot file path, existing bytes, file-size match, and SHA-256 match.

## Current Agent Gateway Progress

- Model gateway remains OpenAI SDK-style: construct the official `OpenAI` client and call `client.responses.create(...)` with Responses-native payloads.
- Responses function tools remain top-level `{"type":"function","name":...,"parameters":...}` specs, with tool results returned as typed `function_call_output` items.
- Structured planner schemas now fail before the remote model call when malformed: `structured_schema` must include a non-empty `name`, `strict=True`, an object `schema`, `schema.type=object`, and `schema.additionalProperties=False`.
- `json_object` remains only a compatibility fallback when no schema is available.

## Current Artifact Contract Progress

- `/tasks/{task_id}/artifact-manifest` now classifies artifacts with `artifact_category`, `container_native_qc`, `derived_scientific_report`, and `frontend_preview_asset`.
- Unlabeled `reports/*` preview assets default to derived scientific report metadata and cannot count as `container_native_qc`.
- Manifest envelope includes `counts_by_artifact_category`.
- RAG and skill references now state that derived scientific report assets are useful for presentation but do not replace native QC evidence.

## Current Skill Maintenance Progress

- Added `docs/skills/maintenance/routing-matrix.json` to make skill ownership, trigger families, and deferrals machine-readable.
- Added `apps/api/scripts/audit_skill_maintenance.py` and tests for routing coverage, skill sections, reference targets, eval category coverage, and secret-token patterns.
- Current audit command: `python apps/api/scripts/audit_skill_maintenance.py --json`.

## Remote Runtime Notes

- Remote server target: `yyf@10.2.32.14`.
- Remote project path from prior project notes: `/home/yyf/project/image_agent`.
- Model gateway uses OpenAI-compatible Responses-style access through `ModelGateway`.
- Required model environment shape:
  - `MODEL_PROVIDER=OpenAI`
  - `OPENAI_MODEL=gpt-5.5`
  - `OPENAI_REVIEW_MODEL=gpt-5.5`
  - `OPENAI_BASE_URL=https://rawchat.cn/codex`
  - `OPENAI_WIRE_API=responses`
  - `OPENAI_REASONING_EFFORT=high`
  - `OPENAI_DISABLE_RESPONSE_STORAGE=true`
  - `OPENAI_API_KEY` must be configured outside the repo and never written to source, docs, logs, RAG, or workflow child environments.
- Local workspace remains code/docs only. Real installation, model smoke, workflow execution, and strict acceptance must run on the remote server.

## Current Strict Acceptance Evidence Hardening

- Saved strict remote smoke evidence must now include `deployment_identity_status=passed`.
- `smoke_gate.deployment_id` and `deployment_identity.deployment_id` must match and must be a privacy-safe short release id or commit, not a full backend path.
- `deployment_identity.health_version` must also be present and privacy-safe, so `/health.version` cannot smuggle a release path into saved evidence.
- The strict acceptance command should include `--require-deployment-identity --deployment-id <accepted-release-or-commit>`.
- The freshness gate still requires `verify_remote_smoke_acceptance.py <remote-smoke-acceptance.json> --max-age-hours 24`.
- `docs/skills/image-agent-developer/references/testing-matrix.md` now mirrors these strict smoke identity and freshness requirements, guarded by `test_developer_testing_matrix_requires_deployment_identity_for_strict_smoke`.
- The same developer testing matrix now requires approved stale-task reconciliation before strict smoke when active tasks block restart: `verify_stale_task_approval.py`, apply with `--approval-json`, `verify_stale_task_resolution.py --require-empty-active`, and then normal restart without `IMAGE_AGENT_ALLOW_RESTART_WITH_ACTIVE_TASKS=1`.

## Prior BMAD-Style Explorer Findings

| Role | Agent | Scope |
| --- | --- | --- |
| Architect/API | Gauss (`019eaff1-f31b-7270-8d39-8d9b307b8187`) | Freeze `/agent/runs` contracts, run lookup, resume, docs/api.md, and `/chat` compatibility risks. |
| RAG Curator | Darwin (`019eaff2-3376-7d62-be51-86d95e5119d4`) | Standardize workflow frontmatter, official grounding, expected artifacts, unsupported boundaries, and provenance tests. |
| Product/Workflow Strategy | Linnaeus (`019eaff2-7cdb-7e00-bb0b-8acfc3140652`) | Unify production DWI wording and legacy/incubation QSI boundaries across docs, skills, tests, and frontend-adjacent labels. |
| Skill Maintainer | Anscombe (`019eaff2-c389-7b01-92f2-5ad7ecd2ac8e`) | Plan skill routing matrix, static audit, eval shape adaptation, TOCs, trigger overlap, stale workflow names, and leakage checks. |
| Operations/Remote Acceptance | Hegel (`019eaff3-0958-7f93-8d40-74a3d62a7a59`) | Plan remote env, smoke commands, acceptance JSON, verifier gaps, backup/git steps, and secret-safety boundaries. |

## Errors Encountered

| Error | Attempt | Resolution |
| --- | --- | --- |
| None yet in this planning phase. | - | - |
