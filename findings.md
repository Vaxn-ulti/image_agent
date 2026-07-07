# Image Agent Findings

## 2026-07-05 Production Target Architecture Decisions

- The product target is a production-grade, single-machine private neuroimaging Agent platform with project-level isolation, not a toy demo and not an initial multi-tenant SaaS.
- The architecture must not be framed as T1/BOLD/DWI-only. T1, BOLD/fMRI, and DWI are initial validation workflows; the target routing layer should be open to all mature brain imaging sequences and processing tasks with auditable software/toolchains.
- The target graph should use `Open Neuroimaging Task Router` and `Curated Workflow Registry` language rather than modality-limited routing language.
- Checkpointing is a layered architecture:
  - LangGraph checkpointing is for graph state, interrupts, and resume.
  - Execution DB is for Celery/worker/Docker state.
  - Authorization ledger is for confirmation, fingerprint, project scope, and TTL.
  - Artifact provenance is for result files, logs, QC, checksums, and software versions.
  - Evaluation records are for paper/product metrics.
- Runtime policy is a separate layer from checkpointing. Checkpoints record what happened; policy decides whether the system may continue.
- Production policy should include built-in safety defaults, policy DB, per-run policy snapshots, effective policy resolution, TTL, loop budgets, retry budgets, repeated-failure cutoff, resource limits, and filesystem/network scope.
- The first production deployment model is single-machine/private with local operator assumptions. Do not add complex RBAC now; keep project boundary, scoped authorization, audit logs, input manifests, and project-scoped artifacts.
- Recovery should be evidence-based: attempt lineage, evidence collection, failure classification, recovery checkpoint, repair advisor, retry budget gate, and one-click safe retry only when no permissions/tools/data scope change.

## 2026-07-05 Intent Recognition Planning Scope

- The next requirements phase should focus on the intent recognition module.
- The module should be designed as a hierarchical router rather than a single LLM classification call.
- Expected production concerns include deterministic rule dispatch, structured LLM fallback, confidence scoring, clarification, refusal/blocked states, repeated-failure loop cutoff, evaluation sets, telemetry, and stable contracts for downstream graph nodes.
- Intent router decision 1: the top-level route is strictly two-way, `Answer` vs `Tool Task`, matching the target graph. Subtypes such as result explanation, system help, observe/repair, data management, exploratory tools, and unsafe/blocked requests must live inside the relevant subgraph rather than becoming first-level routes.
- Intent router decision 2: the `Answer / RAG Subgraph` uses five read-only answer subtypes: `project_status_answer`, `rag_knowledge_answer`, `result_explanation`, `system_help`, and `non_diagnostic_boundary`.
- Intent router decision 3: the `Tool Task` branch uses six task subtypes: `fixed_workflow_request`, `data_preparation_task`, `observe_repair_task`, `exploratory_tool_request`, `artifact_generation_task`, and `blocked_or_unsafe_task`.
- Intent router decision 4: intent recognition uses rule-first routing before LLM classification: `Rule Guard -> Context Grounding -> LLM Structured Intent -> Confidence Gate -> Clarification/Route`.
- Intent router decision 5: confidence gating uses `>=0.85` to proceed, `0.60-0.85` to recommend with confirmation/clarification, and `<0.60` to require clarification. Strong clarification conditions override confidence for ambiguous data scope, multiple candidate series/workflows, destructive actions, non-fixed real execution, diagnosis-like requests, and vague "process this" requests.
- Intent router decision 6: clarification uses `max_clarification_rounds=3`, option-first prompts with free-text supplementation, and a `clarification_exhausted` safe terminal state when required execution details remain missing.
- Intent router decision 7: project context may be used to recommend and preselect candidate series/workflows, but it must not auto-authorize execution. Any auto-selected candidate must be explicitly shown in confirmation with data scope, workflow, expected outputs, and risks.
- Intent router decision 8: safety/rule guard recognizes seven blocking or downgrade classes: diagnostic conclusion requests, destructive delete/overwrite/clear requests, out-of-project path access, unsandboxed new-tool real execution, network-scope expansion, secret/license/token leakage, and ambiguous long-running broad data scope. These should route to non-diagnostic answer, blocked task, sandbox/authorization, clarification, or refusal as appropriate.
- Intent router decision 9: intent recognition loop budget defaults to `max_tool_calls_per_intent_run=6`, `max_registry_queries=3`, `max_rag_queries=3`, `max_project_context_reads=2`, `same_tool_same_args_failure_limit=2`, and `same_error_signature_limit=2`. Exhaustion returns `intent_resolution_failed` with a safe clarification or manual-review next step.
- Intent router decision 10: intent recognition acceptance targets are production/paper oriented: top-level `Answer` vs `Tool Task` accuracy `>=95%`, answer subtype accuracy `>=90%`, tool-task subtype accuracy `>=88%`, clarification recall `>=95%`, high-risk block recall `>=98%`, fixed-workflow recommendation Top-1 `>=85%`, Top-3 `>=95%`, real-task misfire rate `<1%`, non-fixed real-execution misfire `0%`, and repeated-failure cutoff success `>=95%`, evaluated on at least 100-150 mostly Chinese realistic requests.

## 2026-06-09 Repository Setup

- The Image Agent Git repository is now the workspace root: `C:\Users\A\Documents\New project 2`.
- The non-project archive was moved outside the Git worktree to `C:\Users\A\Documents\New project 2_repo_archive\2026-06-09-image-agent-cleanup`.
- The active branch for this goal is `codex/image-agent-product-maturity`.
- The repository has substantial existing WIP in staged and unstaged files. Do not reset, checkout, clean, or delete it.
- Local dependency/runtime folders were moved out of the active worktree. Remote server verification remains the authoritative runtime path.

## BMAD Method Notes

- BMAD is being used here as an operating style, not as a requirement to install its full tooling locally.
- The useful mapping for this repo is: PM/Analyst for readiness, Architect for SDK-like boundaries, RAG Curator for official-source provenance, Skill Maintainer for skill-creator structure, Workflow QC for artifact contracts, and Operations for Git/remote evidence.
- The development flow should move from readiness/PRD-style criteria to epics, then small stories with implementation readiness and verification evidence.

## Pending Subagent Findings

- PM / readiness explorer: covered by local `docs/product-readiness.md` gate; dedicated PM explorer still pending.
- Architect explorer: completed.
- RAG curator explorer: completed.
- Skill maintainer explorer: completed.
- Workflow QC explorer: completed.
- Git/backup operations explorer: completed.

## Git / Backup Operations Subagent Findings

Status: read-only review completed on 2026-06-09.

Summary:

- Current branch remains `codex/image-agent-product-maturity`; last commit is `fcac5d8`.
- The tree has very large WIP: hundreds of staged/unstaged/untracked paths. A commit/backup made from only staged state would miss later acceptance hardening in `smoke_remote_agent.py`, tests, deployment docs, readiness files, and planning files.
- Cleanup archive exists at `C:\Users\A\Documents\New project 2_repo_archive\2026-06-09-image-agent-cleanup` and is about 6.14 GB, but current untracked readiness files still need scoped backup or commit coverage.
- `docs/work-log-2026-06-08.md` has strong TDD/verification/backup convention. `docs/work-log-2026-06-09.md` must be kept fresh so the huge previous log is not the only status source.

Backlog:

1. Add real remote strict smoke JSON plus verifier output after deployment.
2. Add an ops convention check covering remote-only acceptance, backup evidence, no `skipped_missing_model_config` acceptance, and no frontend readiness before remote proof.
3. Add scoped backup manifest convention: staged diff, unstaged diff, untracked file list, archive hash, and `git bundle verify`.
4. Add a latest status/handoff index for current acceptance state.
5. Track or commit `docs/product-readiness.md`, planning files, and current work log when the user chooses a checkpoint strategy.

Local backup evidence:

- Scoped backup directory: `C:\Users\A\Documents\New project 2_repo_archive\2026-06-09-product-readiness-local-slice-20260609T012914`
- Contents: scoped staged patch, scoped unstaged patch, scoped untracked list, file snapshots, `head.bundle`, `git-bundle-verify.txt`, and `sha256.txt`.
- Bundle verification exit code: `0`.

## Architect Subagent Findings

Status: read-only review completed on 2026-06-09.

Already in place:

- `apps/api/app/agent/model_gateway.py` uses an OpenAI SDK Responses-style gateway and `client.responses.create`.
- Agent graph, tool registry, tool dispatcher, durable run ledger, RAG stack, `/agent/rag/*`, and `/agent/runs/*` are present.
- Architecture contracts exist in `docs/rag/contracts/agent-run-ledger.md`, `result-summary.md`, `task-events.md`, and `docs/skills/image-agent-architect/references/contracts-and-frontend.md`.

Top frontend-freeze blockers:

1. Public `/agent/runs` and resume responses are still ad hoc runner dictionaries rather than frozen response contracts.
2. Planner tool calls are only partly usable because DB-backed tool context is not fully passed through the planning loop.
3. Durable thread state is split between SQLite run ledger and raw JSON pending confirmations; DB schema lacks an `expires_at` thread/confirmation contract.
4. Path-safe output boundaries are inconsistent in backend/RAG/chat contexts and tool reads.
5. `/chat` remains a legacy public surface outside the agent run ledger and needs deprecation or a stable compatibility contract before frontend freeze.

Backlog:

1. Add typed agent response contracts with `contract_version`, safe source/tool/event models, and response-model coverage for initial run/resume.
2. Add tool-runtime context tests proving planner tool calls can read task/events/result summaries through the model tool loop.
3. Move/sanitize pending confirmations into a durable thread contract with expiry, ownership, single-use status, and no raw RAG persistence.
4. Add leakage tests for `/agent/rag/query`, `/chat`, read-task tools, and `/agent/runs`.
5. Decide `/chat` compatibility/deprecation before product frontend freeze.

## RAG Curator Subagent Findings

Status: read-only review completed on 2026-06-09.

Strengths:

- `docs/rag/vendor/raw-sources/manifest.json` has 55 downloaded source entries with ids, vendor docs, URLs, source types, hashes, bytes, and status.
- Official coverage is broad across fMRIPrep, XCP-D, DeepPrep, FreeSurfer, FSL, MRtrix3, QSIPrep/QSIRecon, MRIQC, DPABI, BIDS/BIDS Validator, dcm2niix, Docker/Podman/Singularity/Apptainer, TemplateFlow, and OpenAI Responses docs.
- `rag_index.py` excludes raw sources from indexing and verifies curated provenance and vendor pointer integrity.
- `workflow_launchability_matrix.md` clearly states that matrix docs do not create production tasks and `workflow_eligibility` remains authoritative.

Gaps:

1. Real vendor docs generally lack `source_type: rag_vendor`; tests use it in fixtures, but corpus fallback currently classifies them as generic `rag_document`.
2. Frontmatter parsing handles only scalar `key: value`, so YAML-like lists such as `official_grounding:` are not machine-readable.
3. `t1_deepprep_anat_report.md` lacks frontmatter, `source_type`, `workflow_type`, and official vendor grounding.
4. `bold_fmriprep_xcpd_report.md` has body references but no machine-readable `official_grounding`.
5. Workflow citations do not automatically expose vendor raw-source ids for their official grounding.
6. RAG answer synthesis returns citations but does not enforce sections for source ids, boundaries, expected artifacts, and unsupported-execution caveats.

Backlog:

1. Normalize vendor docs to `source_type=rag_vendor` by path or frontmatter.
2. Parse YAML-like frontmatter lists and expose normalized `official_grounding`.
3. Add machine-readable frontmatter to workflow/safety docs, especially T1 and BOLD workflows.
4. Add RAG answer contract tests for source ids, boundaries, expected artifacts, citations, and local/remote execution caveats.
5. Propagate workflow official-grounding vendor raw evidence into RAG responses.

## Workflow QC / Result Artifact Subagent Findings

Status: read-only review completed on 2026-06-09.

Already enforced:

- `native_qc.py` centralizes container-native QC metadata with `artifact_origin=container_output`, `native_artifact=True`, `generated_from=container_native_qc`, `replaces_native_qc=False`, and curated `official_source_ids`.
- `result_contract.py` marks derived scientific report assets as `source_stage=scientific_report`, `artifact_role=derived_presentation_asset`, `artifact_origin=generated_from_result_summary`, and `native_artifact=False`.
- `artifact_manifest.py` strips backend paths, checks task output containment, rejects unsafe relative paths, and adds preview/download metadata.
- T1, DWI, and remote BOLD paths already have some native QC discovery and tests.

Risks:

1. `discover_native_qc_outputs()` scans broad HTML/image paths and could mislabel local `reports/` scientific report assets as container-native after summary regeneration.
2. BOLD metric summaries may show derived report PNGs without separately surfacing fMRIPrep/XCP-D native QC artifacts.
3. Remote BOLD validation requires reports/tables/maps/logs but not native figures/images.
4. DWI local fallback mask generation writes evidence but top-level result provenance does not clearly surface that a local fallback mask was used.
5. Console result galleries blur native QC and derived presentation images.

Backlog:

1. Exclude local `reports/` scientific-report outputs from native QC discovery or require known container dirs/stages.
2. Add BOLD native QC summary/manifest tests.
3. Require previewable image provenance fields in manifest contracts.
4. Make `/artifact-manifest` the frontend display/download source of truth.
5. Add console origin badges/columns for native versus derived assets after backend gates pass.

## Product Readiness Gate

Status: local TDD slice completed on 2026-06-09; gate is not passed.

Summary:

- Added `docs/product-readiness.md` as the explicit frontend design freeze gate.
- The gate requires evidence for OpenAI SDK Responses-style gateway usage, durable run/thread state, stable result and artifact contracts, workflow eligibility, official-source RAG provenance, answer boundaries, container-native QC artifacts, derived scientific report boundaries, skill-creator-style skills, and strict remote acceptance.
- The gate states that `skipped_missing_model_config` is not production acceptance and that local tests alone cannot release frontend page design.
- This makes the user-facing "frontend can begin" decision evidence-based rather than conversational.

Verification:

- Red: `apps/api/.venv/Scripts/python.exe -m pytest apps/api/tests/test_skill_and_rag_docs.py::test_product_readiness_gate_blocks_frontend_until_agent_contracts_are_verified -q` failed with `FileNotFoundError` for `docs/product-readiness.md`.
- Green: the same command passed after adding `docs/product-readiness.md`.
- Focused guard: `apps/api/.venv/Scripts/python.exe -m pytest apps/api/tests/test_skill_and_rag_docs.py::test_skill_creator_style_skills_have_references_and_parseable_evals apps/api/tests/test_skill_and_rag_docs.py::test_rag_corpus_contains_required_sections_and_vendor_metadata apps/api/tests/test_skill_and_rag_docs.py::test_product_readiness_gate_blocks_frontend_until_agent_contracts_are_verified -q` passed.

Remaining:

- The gate itself is only local documentation and test coverage. Product readiness remains blocked until remote strict acceptance evidence proves the deployed backend, RAG, model gateway, real evidence ids, artifact manifest, container-native QC, scientific report artifacts, and verifier output.

## Skill Maintainer Subagent Findings

Status: read-only review completed by Hume on 2026-06-09.

Summary:

- The Image Agent skill set is generally healthy. Trigger descriptions are clear, `SKILL.md` files are lean, references are separated well, and safety boundaries are strong.
- The main maintenance debt is not a hard breakage. It is eval executability, long-reference navigation, and clearer routing between `image-agent-workflow-runner` and `neuroimaging-workflow-runner`.
- `docs/skills/evals/evals.json` is valid JSON and covers seven skills with three prompts each, but it is a repo-level suite schema rather than the exact single-skill `skill-creator` eval shape.

Priority backlog:

1. Add tables of contents to references over 100 lines, starting with `docs/skills/image-agent-developer/references/contracts.md` and `testing-matrix.md`.
2. Add a skill routing matrix covering architect, developer, operator, rag-curator, result-reviewer, workflow-runner, and neuroimaging-workflow-runner.
3. Document or adapt the repo-level eval suite so it can be benchmarked in a skill-creator-style workflow.
4. Add trigger and near-miss evals for each image-agent skill.
5. Add fixture-backed evals for artifact manifests, result summaries, unsafe mounts, sensitive logs, and stale RAG docs.
6. Consider `agents/openai.yaml` for display metadata consistency.
7. Add a static skill audit script for frontmatter, reference links, long references without TOC, eval coverage, and sensitive leakage.

Suggested parallel file ownership:

- `docs/skills/image-agent-architect/**`
- `docs/skills/image-agent-operator/**`
- `docs/skills/image-agent-rag-curator/**` plus `docs/rag/workflows/workflow_launchability_matrix.md`
- `docs/skills/image-agent-result-reviewer/**`
- `docs/skills/image-agent-workflow-runner/**` plus `docs/skills/neuroimaging-workflow-runner/**`
- `docs/skills/image-agent-developer/references/contracts.md`
- `docs/skills/image-agent-developer/references/testing-matrix.md`, `gpu-workflow-strategy.md`, and `operational-recovery.md`
- `docs/skills/evals/evals.json`

## Agent API Contract Explorer Findings

Status: read-only review completed by Gauss on 2026-06-10.

Summary:

- `/agent/runs`, `/agent/runs/{agent_run_id}`, `/agent/runs/{thread_id}/resume`, and project run history exist, but they are still raw dictionaries rather than frozen response contracts.
- `docs/api.md` is stale and still centers the legacy `/chat` contract instead of the newer agent run surfaces.
- Remote smoke and acceptance verification do not yet require agent contract versions, enum membership, lookup schema, project history schema, or `/chat` deprecation fields.
- Ledger sanitization is a strength, but public API shape is not schema-owned enough to prevent accidental future unsafe fields.
- Pending confirmations are JSON-backed while run history is SQLite-backed; resume/thread authority needs a durable contract boundary.
- Legacy `/chat` remains public and frontend-visible in console/desktop clients, so it needs a stable compatibility contract or deprecation path before frontend freeze.

Recommended first implementation slice:

1. Add `apps/api/app/agent/contracts.py` with Pydantic v2 models and centralized status enums.
2. Add `contract_version` to public agent envelopes:
   - `agent_run.v1`
   - `agent_run_ledger.v1`
   - `agent_run_history.v1`
   - `legacy_chat.v1`
3. Attach `response_model=` to:
   - `POST /agent/runs`
   - `GET /agent/runs/{agent_run_id}`
   - `POST /agent/runs/{thread_id}/resume`
   - `GET /projects/{project_id}/agent-runs`
   - `POST /chat`
4. Add mapper helpers that convert existing runner and ledger dictionaries into safe public models.
5. Mark `/chat` as deprecated with `replacement_endpoint="/agent/runs"` while keeping a stable compatibility response during migration.
6. Extend local tests and remote acceptance scripts so strict remote acceptance proves the contract, not only ad hoc `status` and `agent_run_id` fields.

Suggested tests:

- `test_openapi_declares_agent_response_models`
- `test_agent_run_response_contract_filters_unexpected_fields`
- `test_agent_run_status_enum_rejects_unknown_status`
- `test_agent_lookup_contract_is_ledger_only`
- `test_project_agent_run_history_contract_version_and_exact_keys`
- `test_agent_resume_contract_for_task_created_ready_blocked_cancelled`
- `test_legacy_chat_contract_marks_deprecated`
- `test_docs_api_documents_agent_contracts`

Migration risk:

- Removing ad hoc fields too aggressively can break current console/desktop consumers. Safer path: define `v1` envelopes with only safe compatibility fields, deprecate `/chat`, then move frontend consumers after strict remote acceptance proves `/agent/runs`.

## DWI Product Wording Explorer Findings

Status: read-only review completed by Linnaeus on 2026-06-10.

Summary:

- Canonical product line is already strongest in `docs/rag/workflows/workflow_launchability_matrix.md`: production DWI is `dwi_fast_gpu_dti`; `dwi_qsiprep`, `dwi_qsirecon`, and `dwi_qsi_full` are incubation/legacy references.
- Several docs and UI/chat strings still imply QSIPrep/QSIRecon are normal DWI product paths. This can mislead the agent, RAG, frontend buttons, and remote acceptance wording.
- `apps/api/app/workflows/registry.py` marks `dwi_fast_gpu_dti` with `profile="production"` but `status="legacy_supported"`, which contradicts the matrix.
- Some workflow docs contain stale operational wording such as old running task ids and QSI-centric DWI instructions.

Canonical wording:

> Production DWI is `dwi_fast_gpu_dti`: bounded-runtime fast DTI using host FSL GPU `eddy_cuda` plus MRtrix tools from the QSIPrep image as a toolbox. It requires DWI NIfTI, `.bval`, `.bvec`, and JSON sidecar metadata with `PhaseEncodingDirection` and `TotalReadoutTime`. QSIPrep, QSIRecon, and `dwi_qsi_full` are advanced legacy/incubation workflows and must not be the default DWI recommendation or exposed as production launch options unless explicitly selected under an advanced legacy path.

Priority files to update:

- `apps/api/app/workflows/registry.py`: align `dwi_fast_gpu_dti` and validate status with production wording.
- `docs/workflows/dwi-qsi-workflow.md`: mark as advanced legacy/incubation rather than current DWI product guidance.
- `docs/workflows/dataset-ingest-workflow.md`: replace DWI mapping to `dwi_qsiprep`/`dwi_qsi_full` with production `dwi_fast_gpu_dti` requirements.
- `apps/api/app/workflows/pipeline.py`: change QSIPrep comments from "production DWI runs" to "legacy QSIPrep/QSI runs".
- `apps/api/app/main.py`: fallback chat and QSIPrep/QSIRecon explanations should include legacy/advanced boundaries.
- `apps/desktop/src/main.jsx`: initial chat and QSI prerequisite errors should not imply QSI is default production DWI.
- `docs/skills/image-agent-developer/SKILL.md`: update evidence task count wording to match current matrix/neuro runner references.
- `docs/skills/image-agent-operator/references/product-context.md`, `docs/skills/image-agent-workflow-runner/references/registry-and-preflight.md`, and `docs/skills/neuroimaging-workflow-runner/references/bids-inputs.md`: add explicit QSI legacy/incubation status labels.

Suggested tests:

- Registry assertions that `dwi_fast_gpu_dti` is production/status-aligned and QSI rows remain `toolchain_incubation` and not runtime-allowed.
- Docs tests rejecting DWI ingest guidance that maps default DWI to `dwi_qsiprep` or `dwi_qsi_full`.
- Agent/chat tests requiring QSIPrep/QSIRecon answers to say legacy/advanced/incubation, not default production DWI.
- Frontend tests ensuring DWI default/fallback buttons show `dwi_fast_gpu_dti(_validate)` unless an explicit advanced legacy flag is enabled.

Risk if unfixed:

- The frontend can expose legacy QSI as normal DWI, the agent can recommend long QSIPrep/QSI runs instead of fast DTI, and product docs can contradict `workflow_eligibility`.

## Skill Maintenance Explorer Findings

Status: read-only review completed by Anscombe on 2026-06-10.

Summary:

- Existing skill checks pass, but next value is in routing and audit rather than more long prose.
- A first slice should add a compact machine-readable routing matrix, a static maintenance audit, a pytest gate, and a short command note.
- Sensitive path/key detection needs allowlists because remote runtime paths such as `/home/yyf/project/...` can be intentional facts, while API keys/passwords must be blocking findings.

Minimal first slice:

1. Add `docs/skills/maintenance/routing-matrix.json` with runtime skills, external-only skills, negative routes, overlap keywords, and workflow-name allowlist.
2. Add `apps/api/scripts/audit_skill_maintenance.py` to check skill metadata, references, trigger overlap, eval shape, workflow names, long refs without TOCs, and sensitive path/key patterns.
3. Add `apps/api/tests/test_skill_maintenance_audit.py` asserting zero blocking findings.
4. Add a short "Maintenance Audit" command block to `docs/skills/image-agent-developer/references/skill-maintenance.md`.

Follow-up slices:

- Add compact TOCs to long references, starting with `contracts.md`, `testing-matrix.md`, `operational-recovery.md`, `gpu-workflow-strategy.md`, and `neuroimaging-workflow-runner/references/container-contracts.md`.
- Keep `docs/skills/evals/evals.json` as the repo-level suite, but add an adapter that can emit skill-creator-compatible per-skill JSON.
- Detect stale workflow names against `WORKFLOW_REGISTRY`, while explicitly allowing legacy/incubation names.

Suggested commands:

- `python apps/api/scripts/audit_skill_maintenance.py --strict`
- `python apps/api/scripts/audit_skill_maintenance.py --json`
- `python apps/api/scripts/audit_skill_maintenance.py --emit-skill-creator-evals image-agent-developer`

## Remote Acceptance Explorer Findings

Status: read-only review completed by Hegel on 2026-06-10.

Summary:

- For the current target, use direct OpenAI-compatible gateway settings rather than the older reverse-tunnel production-doc default.
- `OPENAI_API_KEY` must be entered interactively or injected by a secret manager. It must not be written to repo `.env`, source, docs, RAG, logs, command transcripts, shell history, workflow child environments, or acceptance JSON.
- Strict remote acceptance should be a saved smoke JSON plus offline verifier `passed`, with real project/upload/task/run ids and native artifact evidence.
- Current verifier is useful but should be extended to bind acceptance to model config, direct base URL, host/path/commit/package identity, freshness, and agent-run lookup.

Remote environment shape:

- `BACKEND_RUNTIME_MODE=remote`
- `MODEL_PROVIDER=OpenAI`
- `OPENAI_MODEL=gpt-5.5`
- `OPENAI_REVIEW_MODEL=gpt-5.5`
- `OPENAI_BASE_URL=https://rawchat.cn/codex`
- `OPENAI_WIRE_API=responses`
- `OPENAI_REASONING_EFFORT=high`
- `MODEL_REASONING_EFFORT=high`
- `OPENAI_DISABLE_RESPONSE_STORAGE=true`
- `DISABLE_RESPONSE_STORAGE=true`
- `OPENAI_TIMEOUT_SECONDS=120`
- `OPENAI_CONTEXT_WINDOW=1000000`
- `OPENAI_AUTO_COMPACT_TOKEN_LIMIT=900000`
- `OPENAI_API_KEY` configured out of repo/logging paths.

Remote preflight sequence:

1. SSH to `yyf@10.2.32.14`.
2. `cd /home/yyf/project/image_agent`.
3. Record `git status --short --branch` and `git rev-parse HEAD`.
4. Activate `apps/api/.venv`.
5. Run focused tests:
   - `tests/test_model_gateway.py`
   - `tests/test_agent_api.py`
   - `tests/test_remote_scripts.py`
   - `tests/test_smoke_remote_agent.py`
   - `tests/test_verify_remote_smoke_acceptance.py`
6. Run `python -m compileall -q app scripts`.
7. Check `/health`, `/agent/model/status`, and `/agent/rag/status`.

Strict smoke requirements:

- Use `scripts/smoke_remote_agent.py` with `--require-model`, RAG thresholds, raw-source policy, vendor pointer integrity, real evidence ids, launchability matrix, container-native QC, and scientific report artifacts.
- Save JSON under `docs/deployment/remote-smoke-acceptance-<timestamp>.json`.
- Run `scripts/verify_remote_smoke_acceptance.py` on the exact saved JSON.
- Accept only verifier output with `status=passed`.

Verifier gaps to close:

- Require `model_status.base_url=https://rawchat.cn/codex`, `model=gpt-5.5`, `wire_api=responses`, `reasoning_effort=high`, and `store=false`.
- Bind acceptance to remote host/path, branch, commit, package hash, and script hashes.
- Enforce freshness of `generated_at_utc`.
- Verify `agent_run_id` through `GET /agent/runs/{agent_run_id}`.
- Decide how remote smoke proves served artifact bytes beyond route checks.
- Update docs that still show reverse-tunnel `OPENAI_BASE_URL=http://127.0.0.1:18081` as the default for this deployment.
- Review `tools/restart_remote_image_agent_api.sh` because sourcing repo `.env` can clobber externally supplied OpenAI env; prefer outside-repo secret/env path or preserve-external-env mode.

Safety rules:

- `skipped_missing_model_config` is a hard fail for production acceptance.
- Do not restart while tasks are queued/running.
- Do not pass `OPENAI_API_KEY`, `DEEPSEEK_API_KEY`, or `IMAGE_AGENT_SUDO_PASSWORD` into workflow child scripts.
- Do not attach raw logs if they may contain keys, bearer tokens, patient identifiers, host paths, or license content.

## RAG Workflow Metadata Explorer Findings

Status: read-only review completed by Darwin on 2026-06-10.

Summary:

- Raw-source health is strong: manifest schema `1`, `55` raw sources, `21` curated vendor docs, and curated provenance is healthy.
- Vendor pointer integrity is green: `35` pointers, `0` issues.
- The local RAG index parser already supports simple YAML lists, but `rag_orchestration.py` fallback frontmatter parsing can still drop YAML-list metadata when `.rag_index` is absent or stale.
- Next patch should standardize workflow frontmatter and fix fallback parsing so `official_grounding` consistently propagates raw-source evidence.

Per-workflow gaps:

| Workflow doc | Current gap | Proposed status |
| --- | --- | --- |
| `docs/rag/workflows/t1_deepprep_anat_report.md` | No frontmatter; missing `source_type`, `workflow_type`, `status`, `official_grounding`, `expected_artifacts`, and `unsupported_boundaries`; absent from pointer-integrity `pointers_by_doc`. | `production_supported` |
| `docs/rag/workflows/bold_fmriprep_xcpd_report.md` | Has basic metadata, but lacks `official_grounding`, `expected_artifacts`, and `unsupported_boundaries`; current `status: current_contract` conflicts with launch matrix incubation wording. | `incubation_reference` |
| `docs/rag/workflows/dwi_fast_gpu_dti.md` | Has `official_grounding`, but lacks `expected_artifacts` and `unsupported_boundaries`; should add BIDS/BIDS-validator grounding for sidecar requirements. | `production_supported` |
| `docs/rag/workflows/workflow_launchability_matrix.md` | Has grounding, but lacks `expected_artifacts` and `unsupported_boundaries`; grounding omits some docs named in body. | `policy_matrix` or `current_contract` |

Official grounding to add:

- T1: `deepprep_official_container_usage.md`, `freesurfer_official_container_reconall.md`, `freesurfer_official_license.md`.
- BOLD: `fmriprep_official_container_usage.md`, `fmriprep_official_outputs.md`, `xcp_d_official_container_usage.md`, `xcp_d_official_outputs.md`, `templateflow_official_cache_archive_client.md`, optionally `bids_official_mri_derivatives.md`.
- DWI: keep `fsl_official_fast_dti_tools.md`, `mrtrix3_official_dti_toolbox.md`, `qsiprep_official_container_usage_outputs.md`; add `bids_official_mri_derivatives.md` and possibly `bids_validator_official_cli_docker.md`.
- Launchability matrix: add FreeSurfer recon-all, fMRIPrep usage, XCP-D usage, and optionally TemplateFlow docs to match body claims.

Expected artifact candidates:

- T1: `summary/t1_result_summary.json`, `summary/t1_scientific_report_summary.json`, DeepPrep `QC/` HTML reports, FreeSurfer `stats/*.stats`, regional TSVs, segmentation/maps, masks, transforms, preview figures, and `scripts/recon-all.log`.
- BOLD: fMRIPrep HTML report, preprocessed BOLD, masks, boldref, confounds TSV/JSON, transforms, XCP-D denoised BOLD, FD/DVARS, parcellated time series, connectivity matrices, optional ALFF/ReHo outputs, XCP-D reports, redacted logs, artifact manifest/result-summary entries.
- DWI: native FA/MD/AD/RD maps, MNI152 FA/MD/AD/RD maps, atlas regional TSVs, combined regional tables, `qc/qc_report.tsv`, `qc/dwi_fast_gpu_dti_provenance.json`, `summary/dwi_result_summary.json`, `dwi_tensor_metrics.png`, and `dwi_atlas_region_means.png`.
- Launchability matrix: policy artifacts such as `workflow_status_rows`, `launch_boundaries`, `promotion_evidence_requirements`, and `answering_rules`.

Unsupported boundaries:

- T1: do not launch on FLAIR/T2/DWI/BOLD unless backend marks T1-compatible; no diagnosis; distinguish real stats from placeholder/validation-only outputs; do not expose license contents.
- BOLD: do not call `bold_fmriprep_xcpd_report` production-ready without remote-wrapper evidence; XCP-D handoff is fMRIPrep-compatible derivatives, not raw BIDS; no diagnosis/cognition claims; no group inference.
- DWI: not full QSIPrep/QSIRecon; do not fabricate acquisition parameters, phase encoding, or readout timing; block missing sidecars; no diagnosis/prognosis/treatment claims; do not replace missing QC with generated images.
- Launchability matrix: do not create tasks from the matrix; `workflow_eligibility` and backend records remain authoritative; incubation docs do not prove production readiness; DPABI remains unsupported external.

Suggested tests:

- Add `test_workflow_docs_declare_standard_frontmatter_metadata` in `apps/api/tests/test_skill_and_rag_docs.py`.
- Update pointer tests to require `docs/rag/workflows/t1_deepprep_anat_report.md` in `pointers_by_doc`.
- Add a fallback propagation test in `apps/api/tests/test_rag_query.py` for YAML-list `official_grounding` without persistent `.rag_index`.
- Add a frontmatter-pointer test in `apps/api/tests/test_agent_state_and_rag_index.py` to ensure `rag_vendor_pointer_integrity` catches vendor paths in `official_grounding`, not just body prose.

Answer contract risk:

- Mostly additive: RAG responses will expose richer `raw_source_evidence` for workflow citations.
- The biggest care point is changing workflow `status` vocabulary. Align BOLD with launch matrix as `incubation_reference` to avoid accidental production-readiness claims.
