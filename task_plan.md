# Image Agent Product Maturity Plan

## Goal

Continue developing Image Agent until the agent product is mature and stable enough for real use. Do not tell the user to start frontend page design until the agent/API/RAG/workflow contracts are stable, remotely verified, and documented.

## Non-Negotiable Constraints

- Keep the agent architecture close to OpenAI SDK patterns: explicit gateway/client boundaries, structured Responses-style output, tool registry, durable run/thread state, and clear result contracts.
- RAG must be detailed, source-grounded, and based on real official container/vendor documentation that has been downloaded, curated, and recorded with original source metadata. Production RAG acceptance now targets Elasticsearch hybrid search: BM25 text retrieval plus dense-vector kNN, fused with RRF, with official Elastic source boundaries documented in `docs/rag/contracts/elasticsearch-hybrid-search.md`.
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
| 7. Remote Verification Loop | in_progress | Remote server install/test/run evidence is logged; local-only execution is avoided. |
| 8. Product Maturity Gate | pending | Stability/readiness checklist passes; only then notify user that frontend page design can begin. |

## Immediate Stories

1. Freeze Agent API contracts for `/agent/runs`, `/agent/runs/{agent_run_id}`, `/agent/runs/{thread_id}/resume`, and project run history before frontend integration.
2. Keep `/chat` as legacy/compatibility unless explicitly promoted; `/agent/runs` is the primary agent product surface.
3. Standardize product DWI wording: production DWI is `dwi_fast_gpu_dti`; QSIPrep/QSIRecon/QSI full are legacy/incubation unless explicitly exposed as advanced legacy.
4. Standardize workflow RAG frontmatter and answer provenance before adding more corpus content.
5. Harden artifact manifest and native-QC boundaries so frontend display depends on container-native QC evidence and not derived report PNGs.
6. Improve skills via routing and static audit, not more long prose.
7. Define strict remote acceptance as the only release gate: current deployed commit, configured model gateway, persisted Elasticsearch hybrid RAG evidence, real project/upload/task/run ids, artifact manifest, native QC, scientific report provenance, and verifier `passed`.
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

- Qdrant WIP was backed up and the active direction is Elasticsearch hybrid search, not Qdrant.
- Local RAG rebuild now writes an Elasticsearch-compatible contract under `.rag_index/elasticsearch` and reports `engine=elasticsearch_hybrid`; local fallback retrieval is not production acceptance.
- Connected Elasticsearch indexing is now supported through an injected client for tests or deployment env (`IMAGE_AGENT_ELASTICSEARCH_URL`, optional `IMAGE_AGENT_ELASTICSEARCH_API_KEY`).
- Successful connected rebuild creates the `image_agent_rag` index when missing, bulk-writes curated chunks only, and reports `hybrid_search.persisted=true`, `mode=connected`, and `indexed_chunk_count`.
- Connected retrieval now uses Elasticsearch RRF hybrid search first when the manifest is persisted; `/agent/rag/query` exposes `retrieval_mode` so strict smoke can distinguish true Elasticsearch retrieval from fallback.
- Connected retrieval only reports `elasticsearch_hybrid` when at least one safe curated citation remains after source filtering; unsafe-only Elasticsearch hits fall back locally and do not satisfy strict production query evidence.
- Strict remote acceptance must include `--require-elasticsearch-hybrid-rag` and saved JSON must show `rag_elasticsearch_hybrid_status=passed`, `rag_rebuild_elasticsearch_hybrid` matching status indexed chunks, `persisted=true`, `rag_elasticsearch_hybrid.mode=connected`, positive `rag_elasticsearch_hybrid.indexed_chunk_count`, absent `rag_elasticsearch_hybrid.error`, `dense_vector_field=embedding`, `fusion=rrf`, `rag_elasticsearch_hybrid_query_status=passed`, `rag_elasticsearch_hybrid_query_mode=elasticsearch_hybrid`, `rag_elasticsearch_hybrid_query_retrieval_source=elasticsearch_hybrid`, and the Elasticsearch hybrid contract source.
- First workflow frontmatter slice completed for:
  - `docs/rag/workflows/t1_deepprep_anat_report.md`
  - `docs/rag/workflows/bold_fmriprep_xcpd_report.md`
  - `docs/rag/workflows/dwi_fast_gpu_dti.md`
  - `docs/rag/workflows/workflow_launchability_matrix.md`
- Required machine fields are now tested: `source_type`, `workflow_type`, `status`, `official_grounding`, `expected_artifacts`, and `unsupported_boundaries`.
- `rag_orchestration.py` fallback retrieval now preserves YAML-list metadata when `.rag_index` is missing or stale.
- `audit_rag_metadata.py` now validates raw official-source manifest entries directly: required fields, HTTPS URL, official source type, downloaded status, safe raw-snapshot file path, existing bytes, file-size match, and SHA-256 match.

## Current Agent Gateway Progress

## Current Elasticsearch Hybrid RAG Progress

- Baseline remains the pre-Qdrant restore point with LangGraph main-chain progress preserved; no Qdrant implementation/contract matches should remain under `apps`, `docs/rag`, `docs/deployment`, or `docs/skills`.
- Elasticsearch hybrid RAG now has three evidence tiers:
  - local contract/mock tier: writes mapping, RRF query template, and bulk NDJSON; uses `embedding_provider=local_hashing` and `embedding_production_ready=false`;
  - connected runtime tier: can persist/query Elasticsearch through injected or env-configured clients;
  - production strict tier: requires a configured non-local embedding provider, status/rebuild `embedding_production_ready=true`, rebuild/status provider and model match, connected mode, positive indexed chunks, RRF query evidence, and citation to `docs/rag/contracts/elasticsearch-hybrid-search.md`.
- Configured embedding failure is a production-blocking state, not a connected acceptance state:
  - rebuild reports redacted `embedding_error`, `mode=embedding_error`, `persisted=false`, `indexed_chunk_count=0`, and `embedding_production_ready=false`;
  - rebuild does not bulk-write local-hash vectors into connected Elasticsearch after a configured embedding failure;
  - query falls back locally if query embedding generation fails for a persisted production-vector manifest.
- Strict production acceptance now treats any saved or live `embedding_error` as blocking, even if other fields say `mode=connected`, `persisted=true`, and `embedding_production_ready=true`.
- Strict production acceptance now also requires positive matching `dense_vector_dims` from `/agent/rag/status` and `/agent/rag/rebuild`, so production evidence proves the vector mapping dimension aligns with the configured embedding provider output.
- Strict production acceptance now requires non-empty matching `embedding_model` from `/agent/rag/status` and `/agent/rag/rebuild`, so production evidence identifies the exact embedding model used to create the dense vectors.
- `/deployment.fast_launch_readiness` now also checks the current deployment's `/agent/rag/status` Elasticsearch hybrid evidence directly. A privacy-safe strict remote acceptance id is not enough if the running API reports local-contract/fallback RAG, missing persistence, local hashing embeddings, zero chunks/dimensions, non-`rrf` fusion, or hybrid/embedding errors.
- Connected Elasticsearch runtime handling now unwraps official Python client response objects (`.body`/`.raw`) for both bulk and search responses; object bulk responses with `errors=true` are production-blocking and object search responses must parse into `elasticsearch_hybrid` retrieval results.
- Connected Elasticsearch search results must have safe repo-relative `source` values before they can become RAG citations; missing source, absolute paths, Windows drive paths, `..` traversal paths, URL strings, app/runtime paths, and raw-source paths are skipped. Accepted citation sources are Markdown under `docs/rag/` or `docs/skills/`, excluding `docs/rag/vendor/raw-sources/`.
- Embedding provider config is env-only:
  - `IMAGE_AGENT_RAG_EMBEDDING_PROVIDER`
  - `IMAGE_AGENT_RAG_EMBEDDING_MODEL`
  - `IMAGE_AGENT_RAG_EMBEDDING_API_KEY`
  - `IMAGE_AGENT_RAG_EMBEDDING_BASE_URL`
- Current focused verification:
  - `python -m pytest apps/api/tests/test_agent_state_and_rag_index.py::test_local_rag_index_writes_elasticsearch_hybrid_contract apps/api/tests/test_agent_state_and_rag_index.py::test_local_rag_index_uses_configured_embedding_provider_for_elasticsearch_vectors apps/api/tests/test_agent_state_and_rag_index.py::test_local_rag_index_uses_env_configured_openai_embedding_provider -q` -> `3 passed`.
  - `python -m pytest apps/api/tests/test_release_gate_command_plan.py apps/api/tests/test_skill_and_rag_docs.py -q` -> `82 passed`.
  - `python -m pytest apps/api/tests/test_smoke_remote_agent.py apps/api/tests/test_verify_remote_smoke_acceptance.py -q` -> `299 passed`.
  - `python -m pytest apps/api/tests -q` -> `908 passed, 9 warnings`.
  - `python -m pytest apps/api/tests -q` after embedding-failure downgrade -> `910 passed, 9 warnings`.
  - `python -m pytest apps/api/tests -q` after strict embedding-error rejection -> `913 passed, 9 warnings`.
  - `python -m pytest apps/api/tests -q` after strict dense-vector dimension evidence -> `916 passed, 9 warnings`.
  - `git diff --check` -> passed, with the existing `apps/api/requirements.txt` LF-to-CRLF warning.
  - `rg --ignore-case "qdrant" apps docs/rag docs/deployment docs/skills` -> no implementation/contract matches.
- Remaining release blocker: the deployment server still must run a real Elasticsearch rebuild/query with configured embedding provider, model gateway, upload/workflow/task/QC/report evidence, and fresh saved JSON verification.

- Model gateway remains OpenAI SDK-style: construct the official `OpenAI` client and call `client.responses.create(...)` with Responses-native payloads.
- Responses function tools remain top-level `{"type":"function","name":...,"parameters":...}` specs, with tool results returned as typed `function_call_output` items.
- Structured planner schemas now fail before the remote model call when malformed: `structured_schema` must include a non-empty `name`, `strict=True`, an object `schema`, `schema.type=object`, and `schema.additionalProperties=False`.
- `json_object` remains only a compatibility fallback when no schema is available.

## Current Workflow Metadata Progress

- Fixed workflow registry entries expose structured display/capability metadata for frontend, Agent, and RAG while preserving stable machine `workflow_type` ids for launch, fingerprints, DB rows, and runner dispatch.
- `dwi_fast_gpu_dti` is now an Agent-selectable production fixed workflow; validation and legacy QSIPrep/QSIRecon/QSI full DWI workflows remain non-production Agent choices.
- Fixed workflow confirmations include read-only `workflow_metadata` from the registry public metadata helper.
- `/agent/runs/{thread_id}/resume` accepts frontend-returned `workflow_metadata`; production task creation still uses registry/preflight `workflow_type` and `runtime_workflow_type`, not display metadata.
- Strict remote smoke JSON now preserves a safe confirmation metadata subset, and the offline verifier rejects missing or mismatched `workflow_metadata.workflow_type`, display labels reused as machine ids, and `is_report_only=true` for production launch evidence.
- Strict Elasticsearch hybrid acceptance now requires `configured=true`, a privacy-safe `index`, and matching rebuild/status index evidence in addition to connected/persisted/rebuild/query checks.
- Verified slices:
  - `python -m pytest apps/api/tests/test_agent_graph.py::test_langgraph_agent_runner_fixed_workflow_returns_confirmation_without_task_creation apps/api/tests/test_agent_api.py::test_agent_resume_approved_confirmation_creates_real_task apps/api/tests/test_fixed_workflow_api_contract.py::test_workflow_catalog_exposes_display_metadata_without_renaming_workflow_type -q` -> `3 passed`.
  - `python -m pytest apps/api/tests/test_workflow_registry.py apps/api/tests/test_fixed_workflow_api_contract.py -q` -> `31 passed`.
  - `python -m pytest apps/api/tests/test_agent_graph.py::test_langgraph_agent_runner_matches_dwi_fixed_workflow_from_capability_metadata -q` -> `1 passed`.
  - `python -m pytest apps/api/tests/test_agent_graph.py apps/api/tests/test_agent_tools.py apps/api/tests/test_agent_api.py -q` -> `86 passed`.
  - `python -m pytest apps/api/tests/test_smoke_remote_agent.py apps/api/tests/test_verify_remote_smoke_acceptance.py -q` -> `315 passed`.
  - `python -m pytest apps/api/tests/test_release_gate_command_plan.py apps/api/tests/test_skill_and_rag_docs.py -q` -> `82 passed`.
  - `python -m pytest apps/api/tests -q` -> `928 passed, 9 warnings`.
  - `python -m py_compile apps/api/app/workflows/registry.py apps/api/app/agent/graph.py apps/api/app/agent/langgraph_runner.py apps/api/app/schemas.py` -> passed.
  - `python -m py_compile apps/api/app/workflows/registry.py apps/api/app/agent/langgraph_runner.py` -> passed.
  - `python -m pytest apps/api/tests -q` -> `924 passed, 9 warnings`.
  - `git diff --check` -> passed, with the existing `apps/api/requirements.txt` LF-to-CRLF warning.
  - `rg --ignore-case "qdrant" apps docs/rag docs/deployment docs/skills` -> no implementation/contract matches.

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

- The yyf read-only probe found that the existing prepared verifier overlay is stale and lacks `verify_elasticsearch_hybrid_prerequisites.py`; no remote mutation was attempted.
- `docs/deployment/remote-release-gate-command-plan.json` now begins with a read-only `verify_release_overlay_contents` step that uses shell `test -f` checks before any stale-task apply, restart, ES prerequisite check, upload/task launch, or strict smoke.
- `verify_release_gate_command_plan.py` requires the overlay-content step, confirms it is non-mutating and operator-free, and validates the success markers `release_overlay_current=true`, `required_gate_scripts_present=true`, and `elasticsearch_hybrid_contract_present=true`.
- `apps/api/scripts/build_release_overlay_sync_plan.py` now materializes a reviewable current-worktree overlay sync plan; `docs/deployment/remote-release-overlay-sync-plan.json` targets `codex-es-hybrid-20260619T213000Z` and keeps writes limited to `/tmp` plus a new release overlay under `/home/yyf/project/image_agent_releases`, never the live `/home/yyf/project/image_agent` tree.
- The local archive for `codex-es-hybrid-20260619T213000Z` has been built at `/tmp/image_agent_release_codex-es-hybrid-20260619T213000Z.tar.gz` with SHA-256 `33499d4377a7de4e1f4c1d5fb0145e0c7157b958d717a19df2f43624cfed72a5`; archive inspection showed required ES hybrid gate files present and `.env`, dependency/cache, RAG index, and `data/projects` paths absent.
- `docs/deployment/remote-release-gate-command-plan.json` is now bound to `/home/yyf/project/image_agent_releases/codex-es-hybrid-20260619T213000Z`, and the verifier checks release overlays by safe release-root/id rules instead of hard-coding the old stale overlay.
- The reviewed local archive was uploaded to yyf `/tmp`, extracted to `.incoming`, verified, promoted, and verified as `/home/yyf/project/image_agent_releases/codex-es-hybrid-20260619T213000Z`; the promoted overlay's release-gate verifier returned `status=passed`, `step_count=11`.
- The promoted overlay is current, but ES hybrid prerequisite is still blocked: remote `.env` lacks all required ES/embedding keys and live `/agent/rag/status` remains `engine=llama_index` with no connected hybrid evidence. Next remote-facing action is ES service/config plus production embedding config, then restart/rebuild/query prerequisite verification; strict smoke must wait.
- Current yyf ES hybrid runtime evidence adds that no service is listening on `127.0.0.1:9200`; `yyf` is not in the `docker` group despite sudo membership, so Docker/Elasticsearch service checks require operator/sudo handling; existing model gateway configuration is present enough for `/agent/model/status` to report `configured=true`, `wire_api=responses`, and `model=gpt-5.5`.
- `apps/api/scripts/build_elasticsearch_hybrid_config_plan.py` and `docs/deployment/remote-elasticsearch-hybrid-config-plan.json` now provide the secret-safe next-step handoff for the operator: provision ES, apply ES/embedding env through the managed secret path, verify key presence without values, restart from the release overlay, rebuild ES hybrid RAG, run the read-only ES prerequisite, and then resume the strict release gate. This plan intentionally does not mutate remote secrets or start services by itself.
- `apps/api/scripts/verify_elasticsearch_hybrid_config_plan.py` now makes the ES config handoff machine-checkable. It verifies the accepted release overlay, missing env-key set, secret-safe placeholder env template, operator/mutating step boundaries, ES prerequisite-before-strict-smoke ordering, and detailed BM25/kNN/RRF plus production embedding expected-success coverage. Direct verifier output for `docs/deployment/remote-elasticsearch-hybrid-config-plan.json` currently reports `status=passed`, `step_count=7`.
- Current release evidence has advanced to `/home/yyf/project/image_agent_releases/codex-es-hybrid-config-gate2-20260619T231500Z`.
- The new gate2 overlay includes the ES config handoff builder, verifier, and `docs/deployment/remote-elasticsearch-hybrid-config-plan.json`; release-gate verification now rejects overlays missing those files before any mutating step.
- Remote gate2 evidence:
  - Local archive `/tmp/image_agent_release_codex-es-hybrid-config-gate2-20260619T231500Z.tar.gz`, SHA-256 `1aaee37e4c758d2e743c414837bc4bf45045d93e237003b25c63bb832c8b33ed`, size `3039329`, `member_count=519`, required files present, `.env/data/projects/node_modules/.rag_index` absent.
  - yyf promoted overlay exists, `.incoming` absent, uploaded `/tmp` archive retained for audit.
  - Promoted overlay content check returned `release_overlay_current=true`, `required_gate_scripts_present=true`, `elasticsearch_hybrid_contract_present=true`.
  - Remote release-gate verifier from overlay root returned `status=passed`, `step_count=11`.
  - Remote ES config handoff verifier from overlay root returned `status=passed`, `step_count=7`.
- Current remaining blocker is runtime configuration: yyf `.env` still lacks all ES/embedding keys, no ES hybrid live status is present, and the read-only ES prerequisite fails before any restart/rebuild/strict smoke.
- Latest time-to-start assessment: Docker is installed on yyf, but the `yyf` account cannot access `/var/run/docker.sock` and non-interactive sudo is unavailable; Elasticsearch is not listening on `127.0.0.1:9200`; live RAG remains `engine=llama_index`; all ES/embedding env keys are absent. If an operator can immediately provision ES and managed env, real closed-loop testing can likely start in about 4-6 hours; otherwise the practical estimate is 1-2 days.
- Runtime readiness must be portable: after installation, the server exposes `/runtime/probe` and `app.scripts.probe_runtime_environment --json` to discover the local Docker daemon, image-agent-labeled containers, workflow image availability, FreeSurfer license presence, resource summary, and Elasticsearch readiness. yyf is the first real acceptance environment, not a hard-coded runtime target.
- User-set execution order: finish mock/control-plane tests first, then run real online closed-loop testing on the yyf remote server.
- Current mock/control-plane gate is satisfied locally: `python -m pytest apps/api/tests -q` returned `1320 passed, 11 warnings`; focused regression for fixed validate workflow gate and RAG readiness architecture returned `5 passed`. Remote testing may proceed only through yyf runtime/ES preflight first.
- Current yyf remote preflight has started but strict smoke must not run yet: promoted overlay `/home/yyf/project/image_agent_releases/codex-es-hybrid-runtime-probe-20260619T215100Z` verifies, but live API is still old, ES hybrid prerequisites fail, restart is blocked by active tasks 83/84 pending human-reviewed stale-task reconciliation, and Docker images include unacceptable `latest` tags for strict version-lock acceptance.
- Use `/home/yyf/project/image_agent_releases/codex-es-hybrid-runtime-probe-rootfix10-20260619T154306Z` for the next remote gate continuation. It supersedes rootfix9 by preserving deployment-server-local runtime probe evidence and adding an explicit workflow-image preparation setting: by default runtime probing remains read-only with `IMAGE_AGENT_AUTO_PULL_MISSING_WORKFLOW_IMAGES=false`; the new `probe_runtime_environment --prepare-missing-images` path sets `IMAGE_AGENT_AUTO_PULL_MISSING_WORKFLOW_IMAGES=1`, pulls missing fixed-workflow Docker images, and records `runtime_preparation` evidence. The ES config handoff now has `step_count=10` and includes the mutating/operator-authorized `operator_prepare_fixed_workflow_images_if_missing` step after restart and before RAG rebuild; remote rootfix10 release-gate and ES config handoff verifiers pass. The rootfix10 read-only runtime probe evidence is `/tmp/image_agent_runtime_probe_codex-es-hybrid-runtime-probe-rootfix10-20260619T154306Z.json`; it reports `runtime_preparation.auto_pull_missing_images=false`, `pull_attempted_count=0`, no configured ES, and no local Elasticsearch runtime discovery. The current materialized operator handoff is still `/tmp/image_agent_remote_release_gate_plan_rootfix3_20260619T143210Z.json`, verified with fresh approval expiry `2026-06-20T14:21:27.328242+00:00`, no refresh/step placeholders, no API-key shaped values, and no active-task restart override. The reviewed dry-run evidence remains `/tmp/image_agent_stale_tasks_83_84_dry_run_rootfix2_20260619T221206Z.json`, with stale candidates 83/84 and approval fingerprint `139113571daf0137a3e34be526fd25ccaa8066aed725ab7c0b846cfc7eb3abd0`; human approval is still required before apply/restart.
- Current remote real-flow checkpoint: a temporary rootfix10 API is running on yyf `127.0.0.1:18082` with `IMAGE_AGENT_ROOT=/home/yyf/project/image_agent`; it is intentionally separate from the old live 8000 service. The backend startup migration has added `tasks.runtime_workflow_type` to the live DB after a `/tmp` DB backup. `task_id=119` completed the required fixed-workflow gate chain and reached the real `pbfslab/deepprep:25.1.0` container, then failed on a tiny synthetic T1 input; this is recorded as a data-quality/runtime-input failure, not an Agent/task-service gate failure. `task_id=120` is the active real-size T1 DeepPrep acceptance task created through the same registry/preflight/fingerprint/task_service/pipeline chain and has progressed past the previous FreeSurfer failure point. Do not auto-rerun failed tasks; use ObserveRepair only for read-only diagnosis, and any retry must create a new preflight/fingerprint-confirmed task. `/home/yyf/mdd_upload` is available for richer follow-up upload/series tests, especially `MDD_nii/sub-*/ses-*/anat/*t1_mprage*.nii.gz`, `func` BOLD, and `dwi` candidates; avoid recording raw subject/person-like filenames in repo logs.
- Parallel real-flow checkpoint: `task_id=121` has completed a T1 validate run through the full fixed-workflow gate chain using canonical `t1_deepprep_anat_report` plus runtime `t1_deepprep_validate`. The earlier BOLD fMRIPrep+XCP-D blocker was the deployed fMRIPrep script's hard-coded `nipreps/fmriprep:latest`; that is now fixed by managed locked wrapper generation and validated by `task_id=124`. `task_id=122` DWI validate failed because the then-configured pinned `pennlinc/qsiprep:1.0.2` image was still pulling/not ready; that version lock has since been corrected to `pennlinc/qsiprep:26.0.0` and revalidated by `task_id=123`. Read-only evidence is saved at `/tmp/image_agent_parallel_real_validate_20260620T014625+0800`, `/tmp/image_agent_dwi_validate_qsiprep260_20260620T022946+0800`, and `/tmp/image_agent_bold_validate_locked_wrapper_20260620T0247+0800`; do not rerun failed/blocked workflows automatically.
- QSIPrep/QSI fixed-image follow-up is now reflected in the current execution overlay: code, current docs, RAG/skills, and legacy acceptance script use QSIPrep `pennlinc/qsiprep:26.0.0`; QSIRecon current docs/scripts use `pennlinc/qsirecon:26.0.0`; the acceptance script now reads sudo input from runtime env rather than hard-coding it. Local regression returned `190 passed, 3 warnings`; the temporary yyf API on `127.0.0.1:18082` now runs `/home/yyf/project/image_agent_releases/codex-qsiprep260-runtime-probe-20260619T181921Z` and reports fixed DWI/QSI image contracts through `/runtime/containers`. Port 8000/live tree was not modified.
- DWI validate has now been rerun once under the corrected QSIPrep 26.0.0 contract. `task_id=123` was created through canonical `dwi_fast_gpu_dti` registry/preflight/human-confirmation fingerprint/resume/task_service/pipeline runner with validate runtime `dwi_fast_gpu_dti_validate`; it completed with `status=completed`, `progress=100`, and runtime manifest image `pennlinc/qsiprep:26.0.0` with `floating_tags_allowed=false`. Evidence is under `/tmp/image_agent_dwi_validate_qsiprep260_20260620T022946+0800`; ObserveRepair remained read-only and `auto_rerun_allowed=false`.
- BOLD fMRIPrep+XCP-D validate has now been run once after fixing the deployment-local script image lock. `task_id=124` was created through canonical `bold_fmriprep_xcpd_report` registry/preflight/human-confirmation fingerprint/resume/task_service/pipeline runner with validate runtime `bold_fmriprep_xcpd_report_validate`; it completed with `status=completed`, `progress=100`, fixed images `nipreps/fmriprep:25.2.5` and `pennlinc/xcp_d:26.0.2`, and `floating_tags_allowed=false`. Evidence is under `/tmp/image_agent_bold_validate_locked_wrapper_20260620T0247+0800`; ObserveRepair remained read-only and `auto_rerun_allowed=false`. Remaining strict online smoke blocker is ES hybrid configuration; validate-only BOLD does not replace a future full BOLD result-summary/report/QC acceptance run.
- Saved strict remote smoke evidence must now include `deployment_identity_status=passed`.
- `smoke_gate.deployment_id` and `deployment_identity.deployment_id` must match and must be a privacy-safe short release id or commit, not a full backend path.
- `deployment_identity.health_version` must also be present and privacy-safe, so `/health.version` cannot smuggle a release path into saved evidence.
- The strict acceptance command should include `--require-deployment-identity --deployment-id <accepted-release-or-commit>`.
- The freshness gate still requires `verify_remote_smoke_acceptance.py <remote-smoke-acceptance.json> --max-age-hours 24`.
- `docs/skills/image-agent-developer/references/testing-matrix.md` now mirrors these strict smoke identity and freshness requirements, guarded by `test_developer_testing_matrix_requires_deployment_identity_for_strict_smoke`.
- The same developer testing matrix now requires approved stale-task reconciliation before strict smoke when active tasks block restart: `verify_stale_task_approval.py`, apply with `--approval-json`, `verify_stale_task_resolution.py --require-empty-active`, and then normal restart without `IMAGE_AGENT_ALLOW_RESTART_WITH_ACTIVE_TASKS=1`.
- Stale-task approval and resolution evidence verifiers now reject `log_path` and backend absolute paths anywhere in nested saved JSON before the evidence can count toward normal restart or strict smoke readiness.
- Stale-task evidence verifiers now also require timezone-aware `generated_at`, with the post-apply resolution dry-run timestamp after or equal to the apply timestamp.
- Elasticsearch hybrid live strict smoke expected-success must explicitly list absent `rag_elasticsearch_hybrid.error`, absent `rag_elasticsearch_hybrid.embedding_error`, absent `rag_rebuild_elasticsearch_hybrid.error`, and absent `rag_rebuild_elasticsearch_hybrid.embedding_error`; saved verifier checks alone are not enough for deployment release evidence.
- ES hybrid configuration is now Git-scripted but not live-applied:
  - Repository setup entrypoint: `scripts/bootstrap_image_agent.py`.
  - ES setup entrypoint: `apps/api/scripts/setup_elasticsearch_hybrid_rag.py`.
  - Current ES config plan JSON requires `setup_elasticsearch_hybrid_rag_from_git_script` and no longer accepts the old prose-only operator ES configuration steps.
  - Local verification for the ES/bootstrap/runtime slice returned `41 passed, 3 warnings`; touched scripts compile; secret/proxy scan is clean.
  - yyf dry-run evidence exists at `/tmp/image_agent_git_bootstrap_verify/bootstrap_dry_run.json` and `/tmp/image_agent_git_bootstrap_verify/es_setup_dry_run.json`; both are non-mutating and contain no yyf hard-code, no `latest`, and no API-key-shaped value.
  - Next action: run the Git-managed bootstrap/setup on yyf with real local secret env, allow it to pull/start ES if missing, rebuild ES hybrid RAG, and pass `verify_elasticsearch_hybrid_prerequisites.py` before strict smoke. Do not write secrets to git, logs, or scripts.
  - Follow-up hardening is complete: bootstrap/setup now reject missing embedding model/base URL before writing `.env`, and ES setup reuses existing Docker network/volume via inspect-before-create. Current focused ES/bootstrap/runtime verification is `44 passed, 3 warnings`.
  - yyf read-only readiness now shows Docker is accessible, `127.0.0.1:9200` is not listening, all ES/embedding env keys are still missing, and temporary API `18082` is reachable but not ES hybrid configured.
  - Remote dry-run v2 evidence exists at `/tmp/image_agent_git_bootstrap_verify/bootstrap_dry_run_v2.json`, `/tmp/image_agent_git_bootstrap_verify/es_setup_dry_run_v2.json`, and `/tmp/image_agent_git_bootstrap_verify/bootstrap_skip_es_dry_run_v2.json`; all are valid dry-run JSON and contain no `latest`, no API-key-shaped value, and no yyf hard-code.
  - The updated objective permits temporary proxy use for remote pulls/external access, but proxy configuration must remain runtime-only and must not be committed or logged.
  - ES setup can now derive RAG embedding config from existing deployment env with `--derive-embedding-from-env`. yyf currently has safe source presence for `OPENAI_API_KEY`, `OPENAI_BASE_URL`, and `OPENAI_MODEL`; the derived dry-run reports `model_source=default_text_embedding_3_small`, `base_url_source=OPENAI_BASE_URL`, and `api_key_source=existing_runtime_fallback_present` without printing values.
  - ES config handoff order is corrected: setup does not run rebuild/prereq verification before API restart. The expected sequence remains setup ES/env, verify key presence, restart API, prepare workflow images, rebuild ES hybrid RAG, run `verify_elasticsearch_hybrid_prerequisites.py`, then continue strict smoke.
  - Current focused verification for this ES/bootstrap/config/runtime slice is `45 passed, 3 warnings`; touched scripts compile; secret/proxy scan is clean.
  - yyf ES setup has now been applied through the Git script: `image-agent-es` is running on loopback `9200`, `.env` contains scripted ES/RAG config, and the temporary API `18082` reads the installed root `.rag_index` after the `IMAGE_AGENT_ROOT` root-resolution fix.
  - Remaining ES blocker is not Docker/ES startup. It is the production embedding endpoint: derived base URL points to yyf loopback port `18081`, where no service is listening, so RAG rebuild records `mode=embedding_error` and does not persist vectors to ES.
  - Before strict smoke, configure or start a real OpenAI-compatible embeddings service for the scripted RAG embedding endpoint, then rebuild RAG and require `verify_elasticsearch_hybrid_prerequisites.py` to pass. Do not substitute local hashing for production acceptance.
  - ES/embedding blocker is now resolved for the temporary yyf acceptance API: pinned TEI local embeddings are running on `127.0.0.1:18081`, RAG rebuild is connected and persisted in Elasticsearch, and `/agent/rag/query` returns `retrieval_source=elasticsearch_hybrid` with official citations. ES `9.4.2` rejects RRF under the current license, so strict evidence now accepts only the audited `query_plus_knn` fallback with `rrf_unavailable_reason=license_non_compliant`; local/mock fallback remains blocked.

## Current ES Hybrid Acceptance Next Steps

- [x] Start Git-managed local TEI embeddings on yyf with pinned image/model and no committed proxy material.
- [x] Rebuild Elasticsearch hybrid RAG and verify connected/persisted `/agent/rag/status`.
- [x] Verify `/agent/rag/query` uses Elasticsearch hybrid retrieval with official citations.
- [x] Capture ES `9.4.2` RRF license boundary as audited `query_plus_knn` fallback with `rrf_unavailable_reason=license_non_compliant`.
- [x] Enable official Elasticsearch trial license on yyf and verify rebuild/status/query fusion returns to `rrf`.
- [x] Run read-only ES hybrid prerequisite gate against temporary yyf API `127.0.0.1:18082` and confirm `status=passed`.
- [ ] Run strict online smoke on yyf using the temporary accepted API/release evidence.
- [ ] Expand from validate-only fixed workflow checks into full result-summary/report/QC artifact acceptance.

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
| BMAD/subagent unavailable and no longer aligned with current goal wording. | Spawned a Workflow Gate Reviewer explorer (`019eda3f-4357-7d40-b9a8-f027f6b32387`), which returned a 503 from the local responses service. The active objective was then updated to explicitly not use BMAD-METHOD for multi-subagent coordination. | Closed the failed subagent and continued locally with TDD on the fixed-workflow task boundary. |

## 2026-07-05 Production Target Architecture Planning

Current product direction:

- Image Agent is a single-machine, private, production-grade neuroimaging Agent system, not a demo.
- The target scope is not limited to T1, BOLD, or DWI. These are first validation scenarios only. The architecture should cover all brain imaging sequences and processing tasks that have mature, documented, auditable software/toolchains.
- The target graph is registry-first, policy-gated, checkpointed, Celery-backed, and project-isolated.
- The target graph uses `Open Neuroimaging Task Router` and `Curated Workflow Registry` rather than modality-limited routing.
- Checkpointing is layered:
  - `LangGraph Checkpointer` for graph state, thread state, interrupt, and resume.
  - `Execution State DB` for execution runs, attempts, heartbeat, and events.
  - `Authorization & Audit Ledger` for confirmation, fingerprint, project scope, TTL, and local operator evidence.
  - `Artifact & Result Provenance Store` for manifest, checksum, logs, QC, and software provenance.
  - `Evaluation Records` for benchmark metrics, traces, and failure cases.
- Runtime policy is separate from checkpointing:
  - checkpoints record what happened;
  - policy decides whether the system may continue.
- Production runtime policy should include built-in safety defaults, policy DB, per-run policy snapshots, effective policy resolution, authorization TTL, loop control, retry budget, repeated-failure cutoff, resource budget, and network/filesystem scope.
- Deployment direction:
  - single-machine private deployment first;
  - no complex multi-user RBAC in the first production design;
  - keep project-level isolation, task-level authorization, execution audit, policy snapshot, data scope control, and artifact provenance;
  - use project-scoped storage and input manifests so workers do not receive unconstrained filesystem access.
- Recovery design:
  - failures should produce attempt lineage, evidence collection, failure classification, recovery checkpoint, repair advice, retry budget decision, and final failure report when needed;
  - fixed mature workflows may expose one-click safe retry, but should not silently auto-rerun long tasks;
  - non-fixed real execution should not retry silently;
  - changing tools, images, network, write scope, data scope, or core workflow parameters must re-enter authorization.

Next planning focus:

- Engineer the intent recognition module as a production-grade subsystem.
- Start with requirements elicitation before code changes.
- Resolve hierarchical intent routing, rule-first dispatch, LLM structured understanding, confidence thresholds, clarification behavior, loop limits, observability, evaluation metrics, and stable downstream contracts.
