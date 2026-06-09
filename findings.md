# Image Agent Findings

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
