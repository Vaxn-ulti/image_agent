# Remote Agent Acceptance Log - 2026-06-07

## Current Production Task

- Remote host alias: `remote_server`
- Remote deployment: `/home/yyf/project/image_agent`
- Task under acceptance: `118`
- Workflow: `bold_fmriprep_xcpd_report`
- Project/series: project `13`, series `23`
- Status at last check: `completed`, progress `100`, no error message
- Last checked: `2026-06-07T04:05:00+08:00`
- Active stage: completed fMRIPrep + XCP-D remote wrapper
- XCP-D state: completed successfully; `output/logs/xcpd_fmriprep.log` exists
- Result summary: generated and served by `/tasks/118/result-summary`

Evidence observed:

```text
/home/yyf/project/image_agent/data/projects/13/derivatives/118/output/logs/fmriprep.log exists
/home/yyf/project/image_agent/data/projects/13/derivatives/118/output/logs/xcpd_fmriprep.log exists
/home/yyf/project/image_agent/data/projects/13/derivatives/118/output/summary/bold_result_summary.json exists
/home/yyf/project/image_agent/data/projects/13/derivatives/118/output/fmriprep exists
/home/yyf/project/image_agent/data/projects/13/derivatives/118/output/xcpd exists
Main log contains `XCP-D finished successfully!`
API `/tasks/118` returned `completed`, progress `100`, finished_at `2026-06-06T20:01:13.444172+00:00`
Regenerated result summary after deployment includes 13 reports, 28 figures, 88 tables, 132 metric JSONs, 50 maps, and 2 logs.
Live `/tasks/118/logs` labels `fmriprep.log` as `fmriprep` and `xcpd_fmriprep.log` as `xcpd`.
```

Task `118` is accepted as a completed real BOLD fMRIPrep + XCP-D workflow run with registered outputs and a regenerated unified result summary.

## Local Verification

Verified locally before remote application:

```text
110 passed: agent/incubation/RAG workflow registry/remote wrapper/RAG source traceability/fixed workflow API focused suite
22 passed: OpenAI-style function tool dispatcher/model gateway/agent graph focused suite
11 passed: dispatcher-driven script-path incubation and incubation ledger focused suite
5 passed: skill/RAG docs and vendor downloader contract suite
9 passed: remote BOLD wrapper native QC artifact discovery suite
37 passed: result-summary, fixed workflow contract, remote wrapper, and skill/RAG doc focused suite
60 passed: agent tool dispatcher/model gateway/agent graph plus result-summary, fixed workflow contract, remote wrapper, and skill/RAG doc focused suite
221 passed: full apps/api test suite after restoring direct API debug workflow runtime boundaries
7 passed: workflow registry plus agent `create_workflow_task` guardrail suite; `t1_deepprep_mock` remains API-runnable for smoke tests but blocked from agent production execution
223 passed: full apps/api test suite after container mount-role decomposition and skill/RAG policy updates
25 passed: incubation ledger, agent tool, and skill/RAG doc suite for structured container mount roles
RAG rebuild passed: 55 documents, 176 chunks, and retrieval hits `container-qc-artifacts.md` plus `security-and-containers.md` for mount-role queries
225 passed: full apps/api test suite after incubation `validation_plan` evidence requirements were added
27 passed: incubation ledger, agent tools, and skill/RAG doc suite for `validation_plan`, `evidence_kind`, `expected_evidence`, and no-production-side-effect rules
RAG rebuild passed: 55 documents, 178 chunks, and retrieval hits `container-qc-artifacts.md` plus `security-and-containers.md` for validation-plan queries
44 passed: incubation, skill/RAG docs, agent tools, dispatcher, graph, and prompt/tool registry suite after adding container image inspection plans
227 passed: full apps/api test suite in `apps/api/.venv` after adding `container_inspection_plan`
RAG rebuild passed: 55 documents, 180 chunks; retrieval ranks `security-and-containers.md` and `container-qc-artifacts.md` first for `container_inspection_plan` / digest / entrypoint / version probe queries
43 passed: incubation, skill/RAG docs, agent tools, dispatcher, and graph suite after adding backend local/runtime container inspection helper
228 passed: full apps/api test suite in `apps/api/.venv` after connecting `sandbox_validate_toolchain` to injectable container inspection
RAG rebuild passed with LlamaIndex engine: 55 documents, 180 chunks; retrieval ranks `container-qc-artifacts.md`, `security-and-containers.md`, and workflow-runner skill for `docker image inspect` / `singularity inspect` queries
32 passed: agent tools, dispatcher, function tool registry, and skill/RAG docs after adding registered data candidate selection tools
232 passed: full apps/api test suite in `apps/api/.venv` after adding `list_data_candidates` and `select_incubation_dataset`
RAG rebuild passed with LlamaIndex engine: 55 documents, 182 chunks; retrieval ranks `modalities-bids.md` and `registry-and-preflight.md` first for data candidate selection queries
33 passed: AgentRunner graph, prompt/tool registry, agent tools, and dispatcher suite after wiring data candidate selection into confirmation preparation
234 passed: full apps/api test suite in `apps/api/.venv` after AgentRunner auto-selects a series when the model omits `series_id`
RAG rebuild passed with LlamaIndex engine: 55 documents, 182 chunks; retrieval ranks workflow-runner preflight references and `modalities-bids.md` for no-series/candidate-selection confirmation queries
npm.cmd run build passed in apps/desktop for Result Summary / container-native QC display
In-app browser smoke passed for http://127.0.0.1:5174: page title `Brain Image Agent`, brand visible, no API connection error.
python -m compileall -q apps/api/app apps/api/scripts passed
13 passed: remote BOLD wrapper/result-summary/log-stage focused suite after adding wrapper-log `source_stage` and idempotent summary registration
16 passed: RAG query/reference/index focused suite after routing `build_rag_response` citations through the persistent `.rag_index`
35 passed: model/RAG/smoke focused suite after making `smoke_remote_agent.py` skip `/agent/runs` when the model gateway is unconfigured
```

## Remote Deployment

Latest package applied after task `118` completed:

```text
/tmp/image_agent_incremental_20260607T040317.tgz
sha256: see final deployment note; package hash changes if this log records the hash inside the package
remote backup: /home/yyf/project/image_agent/backups/sync_20260607T040317/pre_apply_api_docs.tgz
```

Post-apply remote checks:

```text
health: {"status":"ok","app":"image_agent","version":"0.2.0"}
task 118: completed, progress 100
13 passed: remote focused tests for wrapper discovery, live log stage labels, task-log API contract, and idempotent summary registration
python -m compileall -q app scripts passed on remote
smoke_remote_agent.py validates model status and RAG surfaces; when OPENAI_API_KEY is absent it reports `model_smoke_status=skipped_missing_model_config` and skips `/agent/runs`
task 118 result summary sections: figures, logs, maps, metrics, reports, tables
task 118 result summary counts: 13 reports, 28 figures, 88 tables, 132 metric JSONs, 50 maps, 2 logs
task 118 registered outputs: 285 rows, exactly one `kind=result_summary` row
RAG rebuild after deployment: 55 documents, 182 chunks, LlamaIndex engine
RAG query after persistent-index citation deployment: mode `langgraph`, 5 citations, first citations include `docs/skills/image-agent-workflow-runner/SKILL.md` and `docs/skills/image-agent-workflow-runner/references/security-and-containers.md`
RAG query tool invocations after deployment: `inspect_task_status`, `inspect_registered_outputs`, `inspect_scientific_reports`, `recommend_next_action`
```

Older uploaded packages kept for rollback/context:

```text
/tmp/image_agent_incremental_20260607T012542.tgz
/tmp/image_agent_incremental_20260607T013923.tgz
/tmp/image_agent_incremental_20260607T014343.tgz
/tmp/image_agent_incremental_20260607T014443.tgz
/tmp/image_agent_incremental_20260607T014500.tgz
/tmp/image_agent_incremental_20260607T015610.tgz
/tmp/image_agent_incremental_20260607T020829.tgz
/tmp/image_agent_incremental_20260607T021736.tgz
/tmp/image_agent_incremental_20260607T022900.tgz
```

The latest deployed package includes:

- Incubation primitive contracts and promotion artifact drafts.
- Agent graph returning `composition_plan` and `promotion_gate`.
- Function tool updates for proposal/promotion contracts.
- Remote wrapper support for shared `IMAGE_AGENT_TEMPLATEFLOW_HOME`.
- BOLD fMRIPrep/XCP-D result discovery now includes `output/logs/*.log` in result-summary and registered outputs.
- RAG vendor raw-source manifest with downloaded official source snapshots, byte counts, and SHA256 checks.
- `/agent/rag/status` now reports vendor raw-source traceability and whether raw HTML snapshots were accidentally indexed.
- `/agent/rag/query` response building now uses the persistent `.rag_index` retrieval path when available while preserving `path` and `excerpt` citation fields for existing callers.
- `scripts/smoke_remote_agent.py` now treats missing model gateway configuration as a skipped live-model check while still validating RAG rebuild/status surfaces.
- `/tasks/{task_id}/logs` now returns the main task log plus `output/logs/*.log` remote wrapper logs for live fMRIPrep/XCP-D monitoring.
- `/tasks/{task_id}/logs` and agent `read_task_events` now label wrapper logs with `source_stage`, including real wrapper names such as `xcpd_fmriprep.log`.
- OpenAI-style function tool dispatcher now maps model tool calls to backend allowlisted tools, records tool traces, and blocks production task creation outside the server-side resume confirmation path.
- Toolchain incubation can now read allowlisted script paths, decompose fMRIPrep/XCP-D container commands into primitive contracts, and keep the proposal in non-production incubation state.
- RAG now includes a container-native QC artifact contract; workflow/result-review skills point to it.
- BOLD fMRIPrep/XCP-D output discovery now classifies container-native HTML reports, QC figures, tables, maps, metric JSON, and logs with `source_stage` and `artifact_role`.
- BOLD fMRIPrep/XCP-D result-summary registration is idempotent when regenerating an existing summary for an already-completed task.
- `apps/api/scripts/fetch_vendor_docs.py` can refresh raw official vendor source snapshots and manifest hashes from official URLs.
- Desktop Result Summary now exposes container-native HTML reports, QC figures, tables/metrics, maps, and logs from the unified result-summary contract.
- Desktop artifact links prefer backend `download_url`, then `relative_path`, and only fall back to basename for legacy/transition summaries so remote absolute paths are not routed through artifact downloads.
- Workflow registry now separates direct API debug runtime from agent production execution: `t1_deepprep_mock` is `api_runnable` for legacy smoke tests, but remains non-agent-selectable and blocked from `create_workflow_task`.
- Workflow incubation container decomposition now emits structured `mounts`, `environment_map`, mount roles (`input_data`, `output_data`, `work_dir`, `templateflow_cache`, `license_file`, `support`), and promotion validation gates for read-only inputs, read-only license mounts, and sandbox-scoped output/work/cache mounts.
- RAG and workflow-runner skill references document the structured mount-role contract so the agent can explain and audit script-derived workflow proposals consistently.
- Workflow incubation proposals now include a `validation_plan` with `minimum_passed_runs`, per-check `evidence_kind`, `expected_evidence`, `source_stages`, no-production-side-effect requirements, and a promotion gate link back to that plan.
- RAG and workflow-runner skill references now document validation-plan expectations so agent responses can explain what evidence is required before a free-form toolchain can be promoted.
- Workflow incubation proposals now include `container_inspection_plan` for Docker/Podman/Singularity/Apptainer primitives, requiring backend-only image metadata inspection, digest/image id, entrypoint/default command, version probes, native output path probes, and explicit forbidden inspection actions.
- `validation_plan` now treats `container_image_inspected`, `container_digest_recorded`, `container_entrypoint_recorded`, `container_versions_recorded`, and `container_native_output_paths_verified` as `container_inspection` evidence, making missing container inspection a promotion blocker.
- RAG and workflow-runner skill references document container image inspection requirements so the agent can explain how it decomposes container internals without directly running Docker from the LLM.
- Backend local/runtime helper `app.agent.container_inspection` can run `docker image inspect`, `podman image inspect`, `singularity inspect --json`, or `apptainer inspect --json` through an injectable runner, normalizes image id, digests, entrypoint, cmd, env keys, labels, user, and working directory, and redacts secret-like values.
- `sandbox_validate_toolchain` now includes a `container_inspection` evidence block while still keeping `production_task_created=false`; inspection remains optional/injectable until production runtime calls it explicitly.
- OpenAI-style function tools now include `list_data_candidates` and `select_incubation_dataset` so the agent can ask the backend to enumerate registered series and choose a sandbox candidate for incubation without reading raw image contents.
- Data candidate selection scores modality match, BIDS/sidecar readiness, support status, storage existence, and project-root path scope while filtering sensitive metadata keys and preserving `production_task_created=false`.
- RAG and workflow-runner skill references document data candidate selection priorities, DICOM conversion boundaries, DWI sidecar requirements, and the rule that final production task creation still requires preflight plus explicit user confirmation.
- AgentRunner fixed-workflow confirmation preparation now auto-selects a safe matching series from backend project context when the planner omits `series_id`, records `data_candidate_selection`, marks `series_auto_selected`, and still requires preflight plus explicit confirmation.
- Planner/tool-use prompts now tell the model to use data candidate tools when the user asks for a workflow but does not name a series.
- Updated tests and deployment docs.

## RAG Official Source Expansion

Added and refreshed official downloaded source snapshots for container inspection, workflow outputs, and BIDS boundaries:

- Docker `docker image inspect`
- Podman `podman image inspect`
- SingularityCE `singularity inspect`
- Apptainer `apptainer inspect`
- fMRIPrep outputs
- XCP-D outputs
- BIDS MRI modality files
- BIDS derivatives introduction

Local evidence after refresh:

```text
fetch_vendor_docs.py downloaded 19 official raw sources into docs/rag/vendor/raw-sources
manifest now covers 12 curated vendor summaries
RAG rebuild: 61 documents, 195 chunks, LlamaIndex engine
vendor raw-source status: raw_sources_indexed=false, missing_files=[], hash_mismatches=[]
retrieval hit docs/rag/vendor/docker_official_image_inspect.md for Docker inspect/digest/labels query
retrieval hit docs/rag/vendor/singularity_apptainer_official_inspect.md for Apptainer/Singularity --json query
retrieval hit docs/rag/vendor/fmriprep_official_outputs.md for fMRIPrep visual QA/report/confounds query
retrieval hit docs/rag/vendor/xcp_d_official_outputs.md for XCP-D executive summary/ALFF/ReHo/connectivity/QC query
retrieval hit docs/rag/vendor/bids_official_mri_derivatives.md for DWI bval/bvec/JSON and raw-vs-derivative boundary query
23 passed: focused vendor/RAG index/query suite after official source expansion
python -m compileall -q apps/api/app apps/api/scripts passed
238 passed: full apps/api test suite after official source expansion
```

## Skill-Creator Style Hardening

Tightened the local Image Agent skill contract so `image-agent-developer` is held to the same skill-creator-style anatomy as the operator, architect, workflow-runner, result-reviewer, and RAG-curator skills.

Changes made:

- `image-agent-developer/SKILL.md` now uses a trigger-oriented `description: Use when ...` frontmatter.
- Added `Trigger Rules`, `Operating Rules`, `Output Shape`, and `Eval Hints` sections while preserving the existing development boundaries.
- Extended `docs/skills/evals/evals.json` with three developer evals covering normal implementation, missing result contracts, and sensitive-log/stale-QSI risk conflict.
- Strengthened `test_skill_creator_style_skills_have_references_and_parseable_evals` so every required Image Agent skill must have trigger/reference/output/eval sections and normal/missing/risk eval coverage.

Local evidence:

```text
red test first: developer skill failed the stricter skill-creator contract on missing trigger-oriented description
green targeted test: 1 passed
skill/RAG docs suite: 9 passed
RAG rebuild after skill edits: 61 documents, 197 chunks, LlamaIndex engine
developer retrieval check ranked docs/skills/image-agent-developer/SKILL.md first
238 passed: full apps/api test suite after skill-creator hardening
```

## Container-Native QC Display Hardening

Tightened the console BOLD result view so primary BOLD panels render registered native report/QC figures instead of placeholder-only visuals.

Changes made:

- `BoldResultView` now receives `reportFigures`, `task_id`, and `apiBase` from `ResultStudioLayout`.
- BOLD voxelwise, seed-connectivity, QC time-series, and mean-PSD panels render native registered figures through backend artifact URLs.
- Removed the decorative placeholder PSD SVG path from the primary BOLD result view.
- Added UI regression coverage requiring named native BOLD QC image alt text and absence of the placeholder label.

Local evidence:

```text
red frontend test first: ResultStudioLayout BOLD test failed because native BOLD QC panel images were absent
green focused frontend test: ResultStudioLayout.test.tsx 3 passed
console test suite: 25 passed across 14 files; existing React Router future warnings
console build: npm.cmd run build passed
HTTP smoke: http://127.0.0.1:5176 returned 200 and title Brain Image Agent Console
in-app browser control tool was not exposed in this turn, so visual verification used local HTTP/test/build evidence
```

## Production Hardening Notes

Set shared TemplateFlow cache before launching new production BOLD tasks:

```bash
export IMAGE_AGENT_TEMPLATEFLOW_HOME=/home/yyf/project/image_agent/cache/templateflow
mkdir -p "$IMAGE_AGENT_TEMPLATEFLOW_HOME"
```

The current task uses task-local TemplateFlow cache because it was launched before this change.

The local model gateway tunnel currently used in testing is:

```bash
ssh -N -R 18081:127.0.0.1:8080 remote_server
export OPENAI_BASE_URL=http://127.0.0.1:18081
```

Live model smoke is still blocked if the local `sub2api` gateway rejects the configured bearer key with upstream authentication failure.

## Remote API Suite Stabilization After RAG/Skill Deployment

Applied refreshed API/docs/skills/RAG package on the remote host and kept the running API service on port `8000`.

Remote package evidence:

```text
applied package sha256: 136f40c88cccd59c18dd180ab15257df47266b60f681afb5a76c9836ac039290
remote health: {"status":"ok","app":"image_agent","version":"0.2.0"}
remote RAG index: 61 documents, 197 chunks, engine=llama_index
remote vendor raw sources: 19 raw official snapshots, 12 curated vendor summaries
remote raw source policy: raw_sources_indexed=false, missing_files=[], hash_mismatches=[]
remote model status: configured=false because OPENAI_API_KEY is absent; base_url=http://127.0.0.1:18081; model_gateway_access=ssh_reverse_tunnel
```

The first broad remote API run after deployment reproduced the expected handoff state:

```text
236 passed, 2 failed, 3 warnings
failed: tests/test_agent_tools.py::test_preflight_workflow_checks_remote_runtime_when_project_root_present
failed: tests/test_model_gateway.py::test_provider_status_reports_remote_reverse_tunnel_hint
```

Systematic debugging diagnosis:

- `test_preflight_workflow_checks_remote_runtime_when_project_root_present` created fake Linux wrapper scripts without executable bits. The production preflight correctly requires executable scripts on non-Windows systems, while local Windows skipped the executable-bit check.
- `test_provider_status_reports_remote_reverse_tunnel_hint` pinned `OPENAI_BASE_URL=http://127.0.0.1:18080` but did not isolate `IMAGE_AGENT_MODEL_TUNNEL_PORT`. The remote runtime intentionally exports `IMAGE_AGENT_MODEL_TUNNEL_PORT=18081`, so the backend correctly classified port `18080` as `direct`.
- Both failures were environment-sensitive test setup issues, not regressions in remote preflight or model gateway behavior.

Narrow test-isolation fix:

- Mark fake fMRIPrep/XCP-D wrapper scripts executable in the agent preflight unit test.
- Pin `IMAGE_AGENT_MODEL_TUNNEL_PORT=18080` in the reverse-tunnel status unit test.

Verification after the fix:

```text
local focused regression tests: 2 passed
remote focused regression tests: 2 passed
remote broad API suite: 238 passed, 3 warnings
local broad API suite using apps/api/.venv: 238 passed, 25 warnings
```

## Desktop Fixed-Workflow Exposure Hardening

Audited the desktop result-summary surface after the container-native QC work. The result panel already renders:

- container-native HTML reports from `outputs.reports`
- previewable native report/QC figures from `outputs.reports` and `outputs.figures`
- tables/metrics, maps, logs, and source artifacts through backend artifact URLs

Gap fixed:

- The desktop Series row still used stale hard-coded workflow button lists, so the newer fixed production registry entries such as `bold_fmriprep_xcpd_report` and `t1_deepprep_anat_report` were not first-class launch options.
- Series rows now derive runnable workflow buttons from the backend `/workflows` registry for matching fixed workflows and API-runnable debug entries, with a fallback list while the catalog is loading.
- The BOLD downstream prerequisite check now treats `bold_fmriprep_xcpd_report` as a valid completed BOLD preproc source before ALFF/fALFF-style downstream metrics.
- Long workflow ids wrap inside their buttons so registry-derived names do not widen the task row.

Verification:

```text
desktop local build: npm.cmd run build passed
desktop local HTTP smoke: http://127.0.0.1:5177 returned 200, title Brain Image Agent
remote desktop build: npm run build passed
remote desktop HTTP smoke: http://127.0.0.1:5173 returned <title>Brain Image Agent</title>
remote Vite dev server picked up src/main.jsx and src/styles.css changes through HMR
```

## Responses-Native OpenAI Tool Wiring Hardening

Audited the model gateway against the intended OpenAI Responses-style agent architecture. The transport intentionally remains a small `urllib` adapter for the local reverse-tunnel gateway, but the payload contract now matches Responses-native tool wiring more closely.

Gap fixed:

- `openai_tool_specs()` emitted Chat-Completions-style nested tool definitions: `{"type":"function","function":{...}}`.
- Tool results after a model function call were appended as a plain user message containing `Tool results JSON`.

Changes made:

- Function tool specs are now top-level Responses function tools: `{"type":"function","name":...,"description":...,"parameters":...,"strict":false}`.
- The model gateway preserves typed `function_call_output` input items in subsequent `/responses` calls.
- Tool traces with a `call_id` now become `function_call_output` items keyed to that call id.
- The previous plain-text `Tool results JSON` message remains only as a compatibility fallback for malformed calls without a call id.
- Developer skill references now document the Responses-native tool spec and tool-output contract so future agent work does not drift back to nested Chat-Completions-shaped wiring.

Verification:

```text
red tests first: nested tool specs, collapsed function_call_output items, and missing typed output helper failed as expected
local focused gateway/dispatcher tests: 18 passed
local agent boundary suite: 40 passed, 5 warnings
local compile: python -m compileall -q app scripts passed
local docs/gateway focused suite: 30 passed
local broad API suite: 240 passed, 25 warnings
remote compile: .venv/bin/python -m compileall -q app scripts passed
remote focused gateway/dispatcher/docs suite: 30 passed
remote broad API suite: 240 passed, 3 warnings
remote API restarted cleanly; api.pid corrected to 685739
remote smoke_remote_agent.py: model_smoke_status=skipped_missing_model_config, RAG 61 documents / 197 chunks, semantic_index=true
```

## OpenAI Official Responses RAG Source Hardening

Added official OpenAI documentation snapshots and a curated RAG summary for the Responses-style function-tool boundary.

Changes made:

- `apps/api/scripts/fetch_vendor_docs.py` now includes official OpenAI function-calling and tools guide sources for Responses mode.
- Added `docs/rag/vendor/openai_official_responses_function_tools.md` with the Image Agent contract for top-level Responses function tools, `tool_choice`, typed `function_call_output`, backend allowlist dispatch, server-side resume confirmation, and secret/sensitive-output limits.
- Added raw official snapshots:
  - `docs/rag/vendor/raw-sources/openai_function_calling_responses.html`
  - `docs/rag/vendor/raw-sources/openai_tools_responses.html`
- Vendor raw-source manifest increased from 19 to 21 official snapshots, while raw HTML remains traceability-only and is not indexed.
- `tests/test_skill_and_rag_docs.py` now requires the OpenAI curated vendor doc, both OpenAI raw source ids, and the Responses/function-tool boundary phrases.

Local evidence:

```text
local RAG/doc contract suite: 10 passed
local persistent RAG rebuild: 62 documents, 200 chunks, LlamaIndex engine
local retrieval check: docs/rag/vendor/openai_official_responses_function_tools.md ranked first for Responses/function_call_output/function tools
local broad API suite: 241 passed
```

Remote verification and correction:

```text
remote file presence: OpenAI curated doc and both OpenAI raw snapshots present
remote raw-source manifest: 21 official snapshots, OpenAI ids openai_function_calling_responses and openai_tools_responses present
initial remote docs suite: 1 failed, 9 passed because two older non-OpenAI raw HTML files no longer matched the newer manifest hashes
root cause: the newer manifest had been copied to remote while stale bids_validator_docker.html and templateflow_archive.html remained from the previous raw-source set
correction: recopied the two mismatched raw source snapshots from the local authoritative raw-sources directory
remote raw-source audit after correction: mismatch_count=0
remote docs suite after correction: 10 passed
remote compile: .venv/bin/python -m compileall -q app scripts passed
remote focused RAG/API tests: 3 passed, 3 warnings
remote broad API suite: 241 passed, 3 warnings
remote smoke_remote_agent.py: model_smoke_status=skipped_missing_model_config, RAG rebuilt from 61 documents / 197 chunks to 62 documents / 200 chunks, semantic_index=true
remote health: {"status":"ok","app":"image_agent","version":"0.2.0"}
remote /agent/rag/status: 62 documents, 200 chunks, 21 raw official snapshots, 13 curated vendor summaries, raw_sources_indexed=false, missing_files=[], hash_mismatches=[]
remote retrieval check: direct Responses/function_call_output/tool_choice query ranked docs/rag/vendor/openai_official_responses_function_tools.md first
```

## QSIPrep/QSIRecon Official RAG Source Hardening

Filled the DWI/QSI vendor-doc gap with real downloaded official QSIPrep and QSIRecon sources and curated summaries for legacy QSI workflow boundaries.

Changes made:

- Added `docs/rag/vendor/qsiprep_official_container_usage_outputs.md` covering `pennlinc/qsiprep:latest`, `--eddy-config`, GPU/`eddy_cuda*` checks, native QSIPrep reports/QC tables such as `desc-image_qc.tsv`, and the boundary that `dwi_fast_gpu_dti` remains the current production DWI path.
- Added `docs/rag/vendor/qsirecon_official_container_usage_workflows.md` covering `pennlinc/qsirecon:latest`, completed-QSIPrep dependency, `--input-type qsiprep`, required `--recon-spec`, current `dipy_dki` and `mrtrix_multishell_msmt_noACT` profiles, and no invented CUDA-only QSIRecon CLI switch.
- Extended `apps/api/scripts/fetch_vendor_docs.py` with official source downloads for:
  - `https://qsiprep.readthedocs.io/en/stable/usage.html`
  - `https://qsiprep.readthedocs.io/en/stable/preprocessing.html`
  - `https://qsirecon.readthedocs.io/en/stable/quickstart.html`
  - `https://qsirecon.readthedocs.io/en/stable/builtin_workflows.html`
- Raw official snapshot count increased from 21 to 25 and curated vendor summaries from 13 to 15.
- Extended `tests/test_skill_and_rag_docs.py` to require the two QSI curated docs, four QSI raw source ids, and the DWI/QSI boundary phrases used by the workflow/skill contracts.

TDD evidence:

```text
red focused docs suite: 3 failed, 8 passed because QSI curated docs and manifest source ids were absent
green focused docs suite after source/doc additions: 11 passed
```

Local evidence:

```text
fetch_vendor_docs.py: source_count=25
local raw-source audit: 25 official snapshots, mismatch_count=0
local persistent RAG rebuild: 64 documents, 206 chunks, LlamaIndex engine
local retrieval check: QSIPrep query ranked docs/rag/vendor/qsiprep_official_container_usage_outputs.md first
local retrieval check: QSIRecon query ranked docs/rag/vendor/qsirecon_official_container_usage_workflows.md first in direct local retrieval
local broad API suite: 242 passed, 25 warnings
```

Remote evidence:

```text
remote raw-source audit: 25 official snapshots, qsi ids present, mismatch_count=0
remote docs suite: 11 passed
remote compile: .venv/bin/python -m compileall -q app scripts passed
remote smoke_remote_agent.py: model_smoke_status=skipped_missing_model_config, RAG rebuilt from 62 documents / 200 chunks to 64 documents / 206 chunks, semantic_index=true
remote /agent/rag/status: 64 documents, 206 chunks, 25 raw official snapshots, 15 curated vendor summaries, raw_sources_indexed=false, missing_files=[], hash_mismatches=[]
remote retrieval check: QSIPrep query ranked docs/rag/vendor/qsiprep_official_container_usage_outputs.md first
remote retrieval check: QSIRecon query ranked docs/rag/vendor/qsirecon_official_container_usage_workflows.md second after the existing DWI/QSI GPU strategy skill reference
remote broad API suite: 242 passed, 3 warnings
```

## FSL/MRtrix Official RAG Source Hardening for Production Fast DTI

Filled the production `dwi_fast_gpu_dti` vendor-doc gap with real downloaded official FSL and MRtrix3 sources and curated summaries for the host-FSL/MRtrix-toolbox boundary.

Changes made:

- Added `docs/rag/vendor/fsl_official_fast_dti_tools.md` covering host FSL use for `eddy_cuda`, `dtifit`, `flirt`, the `applywarp probe` boundary, MNI registration provenance, and the rule that this is not evidence of a full QSIPrep/QSIRecon run.
- Added `docs/rag/vendor/mrtrix3_official_dti_toolbox.md` covering MRtrix toolbox use inside `pennlinc/qsiprep:latest`, including `dwi2mask`, `mrconvert`, `dwi2tensor`, `tensor2metric`, FA/MD/AD/RD output boundaries, finite-map provenance, and `full_qsiprep_run: false` / `full_qsirecon_run: false`.
- Extended `apps/api/scripts/fetch_vendor_docs.py` with official source downloads for:
  - `https://fsl.fmrib.ox.ac.uk/fsl/docs/diffusion/eddy/users_guide/index.html`
  - `https://fsl.fmrib.ox.ac.uk/fsl/docs/diffusion/dtifit.html`
  - `https://fsl.fmrib.ox.ac.uk/fsl/docs/registration/flirt/user_guide.html`
  - `https://userdocs.mrtrix.org/en/latest/reference/commands/dwi2mask.html`
  - `https://userdocs.mrtrix.org/en/latest/reference/commands/mrconvert.html`
  - `https://userdocs.mrtrix.org/en/latest/reference/commands/dwi2tensor.html`
  - `https://userdocs.mrtrix.org/en/latest/reference/commands/tensor2metric.html`
- Raw official snapshot count increased from 25 to 32 and curated vendor summaries from 15 to 17.
- Extended `tests/test_skill_and_rag_docs.py` to require the two fast-DTI curated docs, seven fast-DTI raw source ids, and the production DWI boundary phrases used by the workflow/skill contracts.

TDD evidence:

```text
red focused docs suite: 3 failed, 9 passed because FSL/MRtrix curated docs and manifest source ids were absent
green focused docs suite after source/doc additions: 12 passed
```

Local evidence:

```text
fetch_vendor_docs.py: source_count=32
local raw-source audit: 32 official snapshots, mismatch_count=0
local persistent RAG rebuild: 66 documents, 212 chunks, LlamaIndex engine
local retrieval check: FSL fast-DTI query ranked docs/rag/vendor/fsl_official_fast_dti_tools.md first
local retrieval check: MRtrix fast-DTI query ranked docs/rag/vendor/mrtrix3_official_dti_toolbox.md first
local broad API suite: 243 passed, 25 warnings
```

Remote evidence:

```text
remote raw-source audit: 32 official snapshots, fsl/mrtrix ids present, mismatch_count=0
remote docs suite: 12 passed
remote compile: .venv/bin/python -m compileall -q app scripts passed
remote smoke_remote_agent.py: model_smoke_status=skipped_missing_model_config, RAG rebuilt from 64 documents / 206 chunks to 66 documents / 212 chunks, semantic_index=true
remote /agent/rag/status: 66 documents, 212 chunks, 32 raw official snapshots, 17 curated vendor summaries, raw_sources_indexed=false, missing_files=[], hash_mismatches=[]
remote retrieval check: FSL fast-DTI query ranked docs/rag/vendor/fsl_official_fast_dti_tools.md first
remote retrieval check: direct MRtrix toolbox query ranked docs/rag/vendor/mrtrix3_official_dti_toolbox.md first
remote broad API suite: 243 passed, 3 warnings
```

## Neuroimaging Workflow Runner Skill-Creator Hardening

Promoted the legacy `neuroimaging-workflow-runner` skill into the same skill-creator style contract as the Image Agent skills.

Changes made:

- Added `neuroimaging-workflow-runner` to the strict skill contract in `apps/api/tests/test_skill_and_rag_docs.py`.
- Rewrote `docs/skills/neuroimaging-workflow-runner/SKILL.md` frontmatter description to trigger with `Use when ...`.
- Added required skill-creator sections:
  - `## Trigger Rules`
  - `## Operating Rules`
  - `## Reference Loading`
  - `## Output Shape`
  - `## Eval Hints`
- Preserved the workflow-specific boundaries for DeepPrep, production `dwi_fast_gpu_dti`, legacy QSIPrep/QSIRecon, absolute bind mounts, output registration, and sensitive-data exclusion.
- Added three eval cases to `docs/skills/evals/evals.json` for `neuroimaging-workflow-runner`:
  - `neuro-runner-normal-fast-dti`
  - `neuro-runner-missing-dwi-json`
  - `neuro-runner-risk-unsafe-container-cleanup`

TDD evidence:

```text
red focused skill contract: 1 failed because neuroimaging-workflow-runner description was not trigger-oriented and the skill was missing required sections/evals
green focused skill contract: 1 passed
green skill/RAG docs suite: 12 passed
```

Local evidence:

```text
local eval audit: 3 neuroimaging-workflow-runner evals with normal_path, missing_info, and risk_conflict categories
local persistent RAG rebuild: 66 documents, 214 chunks, LlamaIndex engine
local retrieval check: neuroimaging workflow-runner query ranked docs/skills/neuroimaging-workflow-runner/SKILL.md first
local broad API suite: 243 passed, 25 warnings
```

Remote evidence:

```text
remote skill/RAG docs suite: 12 passed
remote compile: .venv/bin/python -m compileall -q app scripts passed
remote eval audit: 3 neuroimaging-workflow-runner evals with normal_path, missing_info, and risk_conflict categories
remote smoke_remote_agent.py: model_smoke_status=skipped_missing_model_config, RAG rebuilt from 66 documents / 212 chunks to 66 documents / 214 chunks, semantic_index=true
remote /agent/rag/status: 66 documents, 214 chunks, 32 raw official snapshots, 17 curated vendor summaries, raw_sources_indexed=false, missing_files=[], hash_mismatches=[]
remote retrieval check: neuroimaging workflow-runner query returned docs/skills/neuroimaging-workflow-runner/SKILL.md in top hits with the new Trigger Rules / Output Shape content
remote broad API suite: 243 passed, 3 warnings
```

## Console DWI Native Report Figure Surfacing

Surfaced DWI container/report-native QC figures inside the DWI result panels instead of relying only on the generic report gallery.

Changes made:

- Passed the existing `reportFigures` and `apiBase` values from `ResultStudioLayout` into `DwiResultView`.
- Added DWI-native figure selection for tensor metrics and atlas-region summaries from `outputs.reports`.
- Rendered the selected SVG report figures beside the matching DWI panels:
  - `dwi_tensor_metrics.svg` in `DWI tensor map matrix`
  - `dwi_atlas_region_means.svg` in `Atlas regional distribution`
- Added Testing Library cleanup to the console test setup so full-suite DOM state does not leak between route/component tests.
- Audited the desktop result summary path; it already renders `Native QC figures` from `outputs.reports` and `outputs.figures`, so DWI report SVGs are surfaced there when the backend summary provides them.

TDD evidence:

```text
red focused console test: ResultStudioLayout failed because role img "Native DWI report figure: dwi_tensor_metrics.svg" was absent even though the generic report gallery had the SVG
green focused console test: ResultStudioLayout.test.tsx 3 passed after DWI native figure rendering
```

Local evidence:

```text
console full test suite: 14 test files passed, 25 tests passed
console production build: npm run build passed; Vite transformed 1664 modules and emitted dist assets
console browser smoke: http://127.0.0.1:5180/projects loaded with title "Brain Image Agent Console", h1 "Projects", and no fetch error on the shell route
local live DWI route note: http://127.0.0.1:8000 was not serving locally, so live task-114 result-route verification was limited to the component fixture and app-shell browser smoke
remote log mirror: docs/deployment/remote-agent-acceptance-log-20260607.md copied to /home/yyf/project/image_agent
```

## DWI Fast GPU DTI Workflow RAG Page

Promoted production `dwi_fast_gpu_dti` from scattered vendor/skill facts into a first-class workflow RAG document.

Changes made:

- Added `docs/rag/workflows/dwi_fast_gpu_dti.md` with workflow metadata, expected inputs, expected outputs, result-summary reading hints, container-native DWI QC/display rules, and non-diagnostic boundaries.
- Grounded the page in the already downloaded official FSL, MRtrix3, and QSIPrep curated vendor summaries.
- Extended `apps/api/tests/test_skill_and_rag_docs.py` so the required workflow RAG corpus includes `workflows/dwi_fast_gpu_dti.md`.
- Extended the fast-DTI contract test to require the DWI workflow page to preserve:
  - host FSL `eddy_cuda` / MRtrix toolbox mode;
  - `full_qsiprep_run: false` and `full_qsirecon_run: false`;
  - `outputs.reports` display guidance;
  - `dwi_tensor_metrics.svg` and `dwi_atlas_region_means.svg`;
  - the `not full QSIPrep` production boundary.

TDD evidence:

```text
red focused docs contract: 2 failed because docs/rag/workflows/dwi_fast_gpu_dti.md was absent
green focused docs contract: 2 passed after adding the workflow RAG page
```

Local evidence:

```text
local skill/RAG docs suite: 12 passed
local persistent RAG rebuild: 67 documents, 219 chunks, LlamaIndex engine, semantic_index=true
local raw-source audit: 32 official snapshots, raw_sources_indexed=false, missing_files=[], hash_mismatches=[]
local retrieval check: dwi_fast_gpu_dti filtered query returned docs/rag/workflows/dwi_fast_gpu_dti.md as the top three hits
local RAG/index focused suite: 16 passed, 6 warnings
```

Remote evidence:

```text
remote skill/RAG docs suite: 12 passed
remote persistent RAG rebuild: 67 documents, 219 chunks, LlamaIndex engine, semantic_index=true
remote raw-source audit: 32 official snapshots, raw_sources_indexed=false, missing_files=[], hash_mismatches=[]
remote retrieval check: dwi_fast_gpu_dti filtered query returned docs/rag/workflows/dwi_fast_gpu_dti.md as the top three hits
remote RAG/index focused suite: 16 passed, 1 warning
```

## OpenAI SDK Responses Transport Migration

Replaced the remaining hand-rolled `/responses` model-gateway transport with the official OpenAI Python SDK while keeping the existing Responses-native function-tool contract.

Changes made:

- `apps/api/app/agent/model_gateway.py` now constructs `OpenAI(api_key=..., base_url=..., timeout=...)` and calls `client.responses.create(**payload)`.
- `apps/api/requirements.txt` pins `openai==1.109.1`.
- `apps/api/tests/test_model_gateway.py` asserts the gateway uses the SDK client path and preserves:
  - top-level Responses function tools;
  - typed `function_call_output` items keyed by model `call_id`;
  - existing parser/tool-loop behavior.
- `docs/rag/vendor/openai_official_responses_function_tools.md` and `docs/skills/image-agent-developer/references/contracts.md` now explicitly require official OpenAI SDK transport and say not to reintroduce hand-rolled `/responses` HTTP transport.
- This supersedes the earlier transition note in this log that described `urllib` as intentionally retained.

Local evidence:

```text
local gateway/docs/RAG focused suite: 41 passed, 6 warnings
local persistent RAG rebuild: 67 documents, 221 chunks, LlamaIndex engine, semantic_index=true
local raw-source audit: 32 official snapshots, 17 curated vendor summaries, raw_sources_indexed=false, missing_files=[], hash_mismatches=[]
local retrieval check: SDK transport query ranked docs/skills/image-agent-developer/references/contracts.md first and docs/rag/vendor/openai_official_responses_function_tools.md second, with snippets containing `OpenAI SDK`, `responses.create`, and the no hand-rolled `/responses` boundary
```

Remote evidence:

```text
remote file/code check: OpenAI SDK / responses.create contract present in docs/rag/vendor/openai_official_responses_function_tools.md, docs/skills/image-agent-developer/references/contracts.md, and apps/api/app/agent/model_gateway.py
remote persistent RAG rebuild: 67 documents, 221 chunks, LlamaIndex engine, semantic_index=true
remote raw-source audit: 32 official snapshots, 17 curated vendor summaries, raw_sources_indexed=false, missing_files=[], hash_mismatches=[]
remote retrieval check: SDK transport query ranked docs/skills/image-agent-developer/references/contracts.md first and docs/rag/vendor/openai_official_responses_function_tools.md second, with snippets containing `OpenAI SDK`, `responses.create`, and the no hand-rolled `/responses` boundary
remote gateway/docs/RAG focused suite: 41 passed, 1 warning
```

## Skill-Creator Corpus Audit

Audited the current project skill corpus after the OpenAI SDK/RAG updates.

Findings:

- Recursive skill discovery found exactly seven project `SKILL.md` files, all under `docs/skills`.
- Every project skill has:
  - trigger-oriented `description: Use when ...` frontmatter;
  - `references/*.md`;
  - `## Trigger Rules`;
  - `## Operating Rules`;
  - `## Reference Loading`;
  - `## Output Shape`;
  - `## Eval Hints`;
  - three eval cases covering `normal_path`, `missing_info`, and `risk_conflict`.
- No hidden or extra project skills were found outside the existing enforced corpus, so no skill-format rewrite was needed.

Evidence:

```text
skill corpus: image-agent-architect, image-agent-developer, image-agent-operator, image-agent-rag-curator, image-agent-result-reviewer, image-agent-workflow-runner, neuroimaging-workflow-runner
eval coverage: 7 skills x 3 evals = 21 evals; every skill has normal_path, missing_info, risk_conflict
local gateway/docs/RAG focused suite after SDK migration: 41 passed, 6 warnings
remote gateway/docs/RAG focused suite after SDK migration: 41 passed, 1 warning
```

## Fast DTI Official Tool-Surface RAG Expansion

Closed a traceability gap in the production `dwi_fast_gpu_dti` RAG corpus. The runtime preflight checks FSL `applywarp` and `fslmaths`, plus MRtrix `mrinfo`, `mrstats`, and `mrcalc`, but the raw official-source manifest previously covered only FSL eddy/dtifit/flirt and four MRtrix commands.

Changes made:

- Added official raw-source fetch entries for:
  - FSL FNIRT/applywarp user guide;
  - FSL utilities / `fslmaths`;
  - MRtrix3 `mrinfo`;
  - MRtrix3 `mrstats`;
  - MRtrix3 `mrcalc`.
- Refreshed `docs/rag/vendor/raw-sources/manifest.json` from real downloaded official pages.
- Updated `docs/rag/vendor/fsl_official_fast_dti_tools.md` to distinguish `applywarp` and `fslmaths` runtime availability checks from commands that actually produced delivered maps.
- Updated `docs/rag/vendor/mrtrix3_official_dti_toolbox.md` to distinguish `mrinfo`/`mrstats`/`mrcalc` toolbox availability checks from the current `dwi2tensor`/`tensor2metric` scalar-map path.
- Extended `apps/api/tests/test_skill_and_rag_docs.py` so these official source IDs and boundary phrases remain required.

TDD evidence:

```text
red focused docs contract: 2 failed because fsl_fnirt_user_guide was missing from the raw-source manifest and FNIRT/applywarp wording was absent from curated RAG
green focused docs contract: 2 passed after adding official source entries, refreshed raw snapshots, and curated FSL/MRtrix boundary text
```

Local evidence:

```text
local official-source download: scripts/fetch_vendor_docs.py downloaded 37 raw official snapshots
local skill/RAG docs + index/query suite: 28 passed, 6 warnings
local persistent RAG rebuild: 67 documents, 223 chunks, LlamaIndex engine, semantic_index=true
local raw-source audit: 37 official snapshots, 17 curated vendor summaries, raw_sources_indexed=false, missing_files=[], hash_mismatches=[]
local retrieval check: FSL runtime-surface query ranked docs/rag/vendor/fsl_official_fast_dti_tools.md first
local retrieval check: MRtrix runtime-surface query ranked docs/rag/vendor/mrtrix3_official_dti_toolbox.md first
```

Remote evidence:

```text
remote direct fetch note: scripts/fetch_vendor_docs.py hit an SSL handshake timeout before writing a new manifest, so the locally downloaded/hash-verified raw-source tree was mirrored to remote
remote skill/RAG docs + index/query suite: 28 passed, 1 warning
remote persistent RAG rebuild: 67 documents, 223 chunks, LlamaIndex engine, semantic_index=true
remote raw-source audit: 37 official snapshots, 17 curated vendor summaries, raw_sources_indexed=false, missing_files=[], hash_mismatches=[]
remote retrieval check: FSL runtime-surface query ranked docs/rag/vendor/fsl_official_fast_dti_tools.md first
remote retrieval check: MRtrix runtime-surface query ranked docs/rag/vendor/mrtrix3_official_dti_toolbox.md first
```

## Vendor Official-Doc Fetcher Resilience Hardening

Hardened the raw official-source fetcher after the remote host repeatedly timed out during HTTPS handshakes to official documentation sites.

Changes made:

- Added per-URL retry support to `apps/api/scripts/fetch_vendor_docs.py`.
- Added configurable fetch timeout with `--fetch-timeout-seconds`.
- Added explicit `--use-existing-on-failure` fallback that preserves an existing raw snapshot only after fetch retries fail and only when the raw file is already present.
- Manifest entries now record `download_mode`:
  - `fresh_download` for newly fetched official pages;
  - `existing_snapshot_after_fetch_error` for verified existing raw files preserved after a fetch failure.
- Fallback entries preserve the fetch error text for auditability while keeping `status=downloaded` because the raw bytes remain downloaded official snapshots with manifest hashes.
- Extended `apps/api/tests/test_skill_and_rag_docs.py` with retry, cached fallback, and fetch-timeout tests.

TDD evidence:

```text
red retry test: failed because download_vendor_sources did not accept retry_attempts
green retry tests: 3 fetcher tests passed after adding retry support and cached fallback
red timeout test: failed because download_vendor_sources did not accept fetch_timeout_seconds
green timeout/fetcher tests: 4 fetcher tests passed after wiring configurable fetch timeout
```

Local evidence:

```text
local fetch command: scripts/fetch_vendor_docs.py --fetch-timeout-seconds 20 --retry-attempts 3 --retry-delay-seconds 0 --use-existing-on-failure returned 37 sources
local manifest modes: 37 fresh_download, 0 fetch errors
local skill/RAG docs + index/query suite: 31 passed, 6 warnings
local persistent RAG rebuild: 67 documents, 223 chunks, LlamaIndex engine, semantic_index=true
local raw-source audit: 37 official snapshots, 17 curated vendor summaries, raw_sources_indexed=false, missing_files=[], hash_mismatches=[]
```

Remote evidence:

```text
remote fetch command: scripts/fetch_vendor_docs.py --fetch-timeout-seconds 3 --retry-attempts 1 --retry-delay-seconds 0 --use-existing-on-failure returned 37 sources
remote manifest modes: 37 existing_snapshot_after_fetch_error, 37 fetch errors, reflecting current remote HTTPS timeout behavior while preserving verified raw snapshots
remote skill/RAG docs + index/query suite: 31 passed, 1 warning
remote persistent RAG rebuild: 67 documents, 223 chunks, LlamaIndex engine, semantic_index=true
remote raw-source audit: 37 official snapshots, 17 curated vendor summaries, raw_sources_indexed=false, missing_files=[], hash_mismatches=[]
```

## OpenAI Python SDK Official-Source RAG Expansion

Expanded the OpenAI RAG traceability set from Responses function/tool guide pages to the official Python SDK and Responses API reference surfaces that back the current SDK transport architecture.

Changes made:

- Added official raw-source fetch entries for:
  - `openai_python_sdk_readme`: `https://raw.githubusercontent.com/openai/openai-python/main/README.md`
  - `openai_responses_api_reference`: `https://developers.openai.com/api/docs/api-reference/responses/create`
- Updated `docs/rag/vendor/openai_official_responses_function_tools.md` so the curated indexed source explicitly says:
  - use the official OpenAI Python SDK;
  - construct an `OpenAI client`;
  - call `client.responses.create(...)`;
  - do not reintroduce direct `urllib` / hand-rolled `/responses` transport.
- Extended `apps/api/tests/test_skill_and_rag_docs.py` so the new OpenAI source IDs and SDK boundary phrases are required.
- Fixed `apps/api/app/agent/rag_index.py` so raw official source snapshots under `docs/rag/vendor/raw-sources/` are never indexed, even when the raw snapshot itself is Markdown.
- Normalized indexed source paths to POSIX-style strings so raw-source detection works consistently on Windows and Linux.
- Added regression tests for raw Markdown snapshot exclusion and Windows-style raw-source path detection.

TDD/debug evidence:

```text
red OpenAI source contract: 2 failed because openai_python_sdk_readme was absent from the raw-source manifest and official OpenAI Python SDK wording was absent from curated RAG
green OpenAI source contract: 2 passed after adding official SDK/API-reference sources and curated SDK wording
raw Markdown regression found during RAG rebuild: retrieval returned docs/rag/vendor/raw-sources/openai_python_sdk_readme.md, proving raw snapshots could be indexed when the raw file extension was .md
red raw-source exclusion regression: 2 failed because raw Markdown was indexed and Windows-style raw-source paths were not detected
green raw-source exclusion regression: 2 passed after excluding docs/rag/vendor/raw-sources/ and normalizing indexed source paths
```

Local evidence:

```text
local fetch command: scripts/fetch_vendor_docs.py --fetch-timeout-seconds 20 --retry-attempts 3 --retry-delay-seconds 0 --use-existing-on-failure returned 39 sources
local manifest modes: 39 fresh_download, 0 fetch errors
local OpenAI raw snapshots: openai_function_calling_responses, openai_tools_responses, openai_python_sdk_readme, openai_responses_api_reference
local skill/RAG docs + index/query suite: 33 passed, 7 warnings
local persistent RAG rebuild: 67 documents, 223 chunks, LlamaIndex engine, semantic_index=true
local raw-source audit: 39 official snapshots, 17 curated vendor summaries, raw_sources_indexed=false, indexed_raw_sources=[], missing_files=[], hash_mismatches=[]
local retrieval check: SDK query ranked docs/rag/vendor/openai_official_responses_function_tools.md first and did not return raw-sources/openai_python_sdk_readme.md
```

Remote evidence:

```text
remote fetch command: scripts/fetch_vendor_docs.py --fetch-timeout-seconds 3 --retry-attempts 1 --retry-delay-seconds 0 --use-existing-on-failure returned 39 sources
remote manifest modes: 39 existing_snapshot_after_fetch_error, reflecting current remote HTTPS timeout behavior while preserving verified raw snapshots
remote OpenAI raw snapshots: openai_function_calling_responses, openai_tools_responses, openai_python_sdk_readme, openai_responses_api_reference
remote skill/RAG docs + index/query suite: 33 passed, 1 warning
remote persistent RAG rebuild: 67 documents, 223 chunks, LlamaIndex engine, semantic_index=true
remote raw-source audit: 39 official snapshots, 17 curated vendor summaries, raw_sources_indexed=false, indexed_raw_sources=[], missing_files=[], hash_mismatches=[]
remote retrieval check: SDK query ranked docs/rag/vendor/openai_official_responses_function_tools.md first and did not return raw-sources/openai_python_sdk_readme.md
```

## OpenAI SDK RAG Expansion Resume Verification

Freshly re-verified the OpenAI SDK official-source expansion after the interrupted/resumed work session.

Local evidence:

```text
local fetch command: scripts/fetch_vendor_docs.py --fetch-timeout-seconds 20 --retry-attempts 3 --retry-delay-seconds 0 --use-existing-on-failure returned 39 sources
local skill/RAG docs + index/query suite: 36 passed, 7 warnings
local persistent RAG rebuild: 67 documents, 223 chunks, LlamaIndex engine, semantic_index=true
local raw-source audit: 39 official snapshots, 17 curated vendor summaries, raw_sources_indexed=false, indexed_raw_sources=[], missing_files=[], hash_mismatches=[]
local retrieval check: SDK query ranked docs/rag/vendor/openai_official_responses_function_tools.md first and did not return raw-sources/openai_python_sdk_readme.md
```

Remote evidence:

```text
remote sync archive: /tmp/image_agent_openai_rag_sync_20260607T123056.tgz extracted under /home/yyf/project/image_agent
remote fetch command: scripts/fetch_vendor_docs.py --fetch-timeout-seconds 3 --retry-attempts 1 --retry-delay-seconds 0 --use-existing-on-failure returned 39 sources
remote skill/RAG docs + index/query suite: 36 passed, 1 warning
remote persistent RAG rebuild: 67 documents, 223 chunks, LlamaIndex engine, semantic_index=true
remote raw-source audit: 39 official snapshots, 17 curated vendor summaries, raw_sources_indexed=false, indexed_raw_sources=[], missing_files=[], hash_mismatches=[]
remote retrieval check: SDK query ranked docs/rag/vendor/openai_official_responses_function_tools.md first and did not return raw-sources/openai_python_sdk_readme.md
```

## Production DWI Skill Evidence Consistency

Removed stale skill text that still treated production DWI as having only one known-good real sample. The workflow-runner and developer skill references now align with the current backend/RAG evidence: task `107`, task `112`, and mixed-project task `114` all completed production `dwi_fast_gpu_dti` with real native/MNI152 DTI maps, HarvardOxford regional tables, and `validation_only=false`.

Changes made:

- Updated `docs/skills/neuroimaging-workflow-runner/SKILL.md` to cite all three production DWI real-run references.
- Updated `docs/skills/neuroimaging-workflow-runner/references/container-contracts.md` to include tasks `107`, `112`, and `114`.
- Updated `docs/skills/image-agent-developer/references/skill-maintenance.md` so it no longer says another real sample or mixed-project run is still required.
- Added a regression test in `apps/api/tests/test_skill_and_rag_docs.py` to reject the stale release-blocker phrasing and require the current task evidence.

TDD evidence:

```text
red skill evidence contract: 1 failed because workflow-runner skill text still said final release needed another real sample
green skill evidence contract: 1 passed after updating production DWI evidence in skill references
```

Local evidence:

```text
local skill/RAG docs + index/query suite: 37 passed, 7 warnings
local persistent RAG rebuild: 67 documents, 223 chunks, LlamaIndex engine, semantic_index=true
local raw-source audit: 39 official snapshots, 17 curated vendor summaries, raw_sources_indexed=false, indexed_raw_sources=[], missing_files=[], hash_mismatches=[]
local retrieval check: production DWI evidence query ranked docs/skills/neuroimaging-workflow-runner/SKILL.md first and returned output-discovery/testing/contracts/skill-maintenance references in the top hits
```

Remote evidence:

```text
remote sync archive: /tmp/image_agent_skill_evidence_sync_20260607T123827.tgz extracted under /home/yyf/project/image_agent
remote skill/RAG docs + index/query suite: 37 passed, 1 warning
remote persistent RAG rebuild: 67 documents, 223 chunks, LlamaIndex engine, semantic_index=true
remote raw-source audit: 39 official snapshots, 17 curated vendor summaries, raw_sources_indexed=false, indexed_raw_sources=[], missing_files=[], hash_mismatches=[]
remote retrieval check: production DWI evidence query ranked docs/skills/neuroimaging-workflow-runner/SKILL.md first and returned output-discovery/testing/contracts/skill-maintenance references in the top hits
```

## DeepPrep Official Outputs and QC RAG Expansion

Expanded the DeepPrep official-source RAG coverage from container usage into output/report boundaries. The curated DeepPrep vendor summary now cites the downloaded official `outputs.html` source as `deepprep_outputs` and documents the official output families:

- anatomical derivatives under `Recon/`;
- functional derivatives under `BOLD/`;
- visual reports under `QC/`, including subject/session HTML, report figures, logs, `report.html`, and `timeline.html`;
- Image Agent display rules requiring native DeepPrep HTML reports in `outputs.reports` and previewable native report figures in `outputs.figures`.

The workflow RAG now reinforces that DeepPrep report/QC artifacts are container-native evidence and that `placeholder_outputs=true` remains a validation/contract marker, not real derived measurements.

Local evidence:

```text
local fetch command: scripts/fetch_vendor_docs.py --fetch-timeout-seconds 30 --retry-attempts 2 --retry-delay-seconds 1 --use-existing-on-failure returned 40 sources
local focused skill/RAG/index/query suite: 38 passed, 7 warnings
local persistent RAG rebuild: 67 documents, 225 chunks, LlamaIndex engine, semantic_index=true
local raw-source audit: 40 official snapshots, raw_sources_indexed=false, missing_files=[], hash_mismatches=[]
local retrieval check: DeepPrep outputs/QC query ranked docs/rag/vendor/deepprep_official_container_usage.md first and did not return raw-source snapshots
```

Remote evidence:

```text
remote sync archive: /tmp/image_agent_deepprep_outputs_sync_20260607T160137.tgz extracted under /home/yyf/project/image_agent
remote fetch command: scripts/fetch_vendor_docs.py --fetch-timeout-seconds 3 --retry-attempts 1 --retry-delay-seconds 0 --use-existing-on-failure returned 40 sources
remote focused skill/RAG/index/query suite: 38 passed, 1 warning
remote persistent RAG rebuild: 67 documents, 225 chunks, LlamaIndex engine, semantic_index=true
remote raw-source audit: 40 official snapshots, raw_sources_indexed=false, missing_files=[], hash_mismatches=[]
remote retrieval check: DeepPrep outputs/QC query ranked docs/rag/vendor/deepprep_official_container_usage.md first and returned only curated RAG/skill docs in the top hits
```

## FreeSurfer Official Output Files RAG Expansion

Expanded the FreeSurfer official-source RAG coverage from `recon-all` command usage into output-file boundaries grounded in the official `ReconAllOutputFiles` wiki page. This strengthens the T1 DeepPrep/FreeSurfer answer surface for real structural maps, surfaces, labels, stats, logs, and native QC artifacts.

Changes made:

- Added official raw source id `freesurfer_recon_all_outputs` for `https://surfer.nmr.mgh.harvard.edu/fswiki/ReconAllOutputFiles`.
- Updated `docs/rag/vendor/freesurfer_official_container_reconall.md` with source-grounded output families: `mri/orig.mgz`, `mri/aseg.mgz`, `surf/lh.white`, `surf/lh.pial`, `label/lh.aparc.annot`, `stats/aseg.stats`, `stats/lh.aparc.stats`, and `scripts/recon-all.log`.
- Updated T1 DeepPrep workflow RAG so FreeSurfer stats map to `outputs.tables` or `outputs.metrics`, anatomical maps to `outputs.maps`, logs to `outputs.logs`, and snapshots/views to container-native FreeSurfer QC only when derived from native artifacts.
- Updated the container-native QC contract to prefer FreeSurfer-native maps, stats, surfaces, snapshots, and logs instead of generated substitute imagery.

TDD evidence:

```text
red FreeSurfer output contract: 1 failed because `freesurfer_recon_all_outputs` and official output-file boundaries were absent
green FreeSurfer output contract: 1 passed after adding the official source, curated boundaries, and workflow/QC notes
```

Local evidence:

```text
local fetch command: scripts/fetch_vendor_docs.py --fetch-timeout-seconds 30 --retry-attempts 2 --retry-delay-seconds 1 --use-existing-on-failure returned 41 sources
local focused skill/RAG/index/query suite: 39 passed, 7 warnings
local persistent RAG rebuild: 67 documents, 227 chunks, LlamaIndex engine, semantic_index=true
local raw-source audit: 41 official snapshots, raw_sources_indexed=false, missing_files=[], hash_mismatches=[]
local retrieval check: FreeSurfer output query returned docs/rag/vendor/freesurfer_official_container_reconall.md in the default top hits; curated-summary filtered query ranked that vendor doc first
```

Remote evidence:

```text
remote sync archive: /tmp/image_agent_freesurfer_outputs_sync_20260607T161452.tgz extracted under /home/yyf/project/image_agent
remote fetch command: scripts/fetch_vendor_docs.py --fetch-timeout-seconds 3 --retry-attempts 1 --retry-delay-seconds 0 --use-existing-on-failure returned 41 sources
remote focused skill/RAG/index/query suite: 39 passed, 1 warning
remote persistent RAG rebuild: 67 documents, 227 chunks, LlamaIndex engine, semantic_index=true
remote raw-source audit: 41 official snapshots, raw_sources_indexed=false, missing_files=[], hash_mismatches=[]
remote retrieval check: FreeSurfer output query returned docs/rag/vendor/freesurfer_official_container_reconall.md in the default top hits; curated-summary filtered query ranked that vendor doc first
```

## OpenAI SDK Chat Gateway Hardening

Moved the legacy `/chat` freeform answer path toward the same OpenAI SDK / Responses-native architecture used by the newer `/agent/*` runner. Deterministic series/status/task branches remain rules-first, but ordinary chat answers now try `ModelGateway().complete_text(..., purpose="chat_answer")` before falling back to the older DeepSeek compatibility shim.

Changes made:

- `/chat` freeform answers now use `ModelGateway`, which constructs the official OpenAI SDK client and calls `client.responses.create(...)` under the existing gateway boundary.
- The `/chat` prompt passes backend project context and retrieved RAG response JSON to the SDK gateway, preserving backend-record priority and non-diagnostic wording.
- DeepSeek remains as a legacy fallback only when the OpenAI gateway raises `ModelGatewayError`.
- Skill references were updated from "DeepSeek only" wording to "OpenAI SDK chat gateway / Responses-native primary, DeepSeek legacy fallback".

TDD evidence:

```text
red chat gateway contract: 1 failed because `app.main` did not expose/use `ModelGateway` for legacy `/chat`
green chat gateway + fallback contract: 2 passed after `/chat` preferred OpenAI SDK and the DeepSeek compatibility fallback still worked
red skill reference contract: 1 failed because skill references still said `DeepSeek only`
green skill reference contract: 1 passed after updating the OpenAI SDK chat gateway wording
```

Local evidence:

```text
local OpenAI/chat/skill focused suite: 55 passed, 5 warnings
local persistent RAG rebuild: 67 documents, 227 chunks, LlamaIndex engine, semantic_index=true
local raw-source audit: 41 official snapshots, raw_sources_indexed=false, missing_files=[], hash_mismatches=[]
local retrieval check: OpenAI SDK chat gateway query returned repo-map, agent-roles, product-context, and implementation-guidance skill references in the top hits
```

Remote evidence:

```text
remote sync archive: /tmp/image_agent_openai_chat_gateway_sync_20260607T162620.tgz extracted under /home/yyf/project/image_agent
remote OpenAI/chat/skill focused suite: 55 passed, 3 warnings
remote persistent RAG rebuild: 67 documents, 227 chunks, LlamaIndex engine, semantic_index=true
remote raw-source audit: 41 official snapshots, raw_sources_indexed=false, missing_files=[], hash_mismatches=[]
remote retrieval check: OpenAI SDK chat gateway query returned repo-map, agent-roles, product-context, and implementation-guidance skill references in the top hits
git backup: local and remote archive `image_agent_git_backup_openai_chat_gateway_20260607T162759.tgz`; remote copy stored at `/home/yyf/project/image_agent/backups/git_20260607T162759/image_agent_git_backup_openai_chat_gateway_20260607T162759.tgz`
```

## dcm2niix Official Conversion RAG Expansion

Added official-source RAG coverage for DICOM to NIfTI conversion, grounded in the `rordenlab/dcm2niix` README. This fills the ingest boundary before container workflows: raw DICOM archives are conversion candidates, not direct T1/BOLD/DWI production workflow inputs.

Changes made:

- Added official raw source id `dcm2niix_readme` for `https://raw.githubusercontent.com/rordenlab/dcm2niix/master/README.md`.
- Added `docs/rag/vendor/dcm2niix_official_conversion.md` with DICOM to NIfTI, converted NIfTI, BIDS sidecar JSON, partial conversion failures, and privacy boundaries.
- Updated `docs/rag/data-requirements/modalities-bids.md` to separate DICOM conversion/incubation candidates from direct production workflow launch.
- Updated `docs/rag/troubleshooting/common-errors.md` for `dcm2niix executable not found`, partial conversion failures, and safe next steps.

TDD evidence:

```text
red dcm2niix conversion contract: 1 failed because `docs/rag/vendor/dcm2niix_official_conversion.md` did not exist
green dcm2niix conversion contract: 1 passed after adding the official source, curated RAG, and ingest/troubleshooting boundaries
```

Local evidence:

```text
local fetch command: scripts/fetch_vendor_docs.py --fetch-timeout-seconds 30 --retry-attempts 2 --retry-delay-seconds 1 --use-existing-on-failure returned 42 sources
local focused skill/RAG/index/query suite: 41 passed, 7 warnings
local persistent RAG rebuild: 68 documents, 231 chunks, LlamaIndex engine, semantic_index=true
local raw-source audit: 42 official snapshots, raw_sources_indexed=false, missing_files=[], hash_mismatches=[]
local retrieval check: dcm2niix conversion query returned docs/rag/vendor/dcm2niix_official_conversion.md in the top hits
git backup: local archive `image_agent_git_backup_dcm2niix_rag_20260607T163348.tgz`
```

Remote evidence:

```text
remote sync archive: /tmp/image_agent_dcm2niix_rag_sync_20260607T163406.tgz extracted under /home/yyf/project/image_agent
remote fetch command: scripts/fetch_vendor_docs.py --fetch-timeout-seconds 3 --retry-attempts 1 --retry-delay-seconds 0 --use-existing-on-failure returned 42 sources
remote focused skill/RAG/index/query suite: 41 passed, 1 warning
remote persistent RAG rebuild: 68 documents, 231 chunks, LlamaIndex engine, semantic_index=true
remote raw-source audit: 42 official snapshots, raw_sources_indexed=false, missing_files=[], hash_mismatches=[]
remote retrieval check: dcm2niix conversion query returned docs/rag/vendor/dcm2niix_official_conversion.md in the top hits
git backup: remote archive stored at `/home/yyf/project/image_agent/backups/git_20260607T163348/image_agent_git_backup_dcm2niix_rag_20260607T163348.tgz`
```

## OpenAI SDK Skill Wording Cleanup

Cleaned up remaining stale skill wording after the `/chat` OpenAI SDK gateway hardening. The architect skill and operator eval references now describe the OpenAI SDK chat gateway and Responses-native behavior instead of old DeepSeek orchestration/operator wording.

Changes made:

- Updated `docs/skills/image-agent-architect/SKILL.md` to reference LangGraph orchestration, OpenAI SDK chat gateway behavior, and Responses-native agent contracts.
- Updated `docs/skills/image-agent-operator/references/examples-evals.md` to describe OpenAI SDK chat gateway operator behavior, deterministic rule fallbacks, and DeepSeek legacy fallback compatibility.
- Extended the skill/RAG regression contract so future edits reject `DeepSeek only`, `DeepSeek orchestration`, and `DeepSeek operator behavior` in current skill references.

TDD evidence:

```text
red OpenAI skill wording contract: 1 failed because architect skill still said `DeepSeek orchestration`
green OpenAI skill wording contract: 1 passed after updating architect/operator skill wording
```

Local evidence:

```text
local focused skill/RAG/index/query suite: 41 passed, 7 warnings
local persistent RAG rebuild: 68 documents, 231 chunks, LlamaIndex engine, semantic_index=true
local raw-source audit: 42 official snapshots, raw_sources_indexed=false, missing_files=[], hash_mismatches=[]
local retrieval check: OpenAI SDK chat gateway query returned updated repo-map, implementation-guidance, examples-evals, agent-roles, and product-context skill references in the top hits
git backup: local archive `image_agent_git_backup_openai_skill_wording_20260607T164120.tgz`
```

Remote evidence:

```text
remote sync archive: /tmp/image_agent_openai_skill_wording_sync_20260607T164137.tgz extracted under /home/yyf/project/image_agent
remote focused skill/RAG/index/query suite: 41 passed, 1 warning
remote persistent RAG rebuild: 68 documents, 231 chunks, LlamaIndex engine, semantic_index=true
remote raw-source audit: 42 official snapshots, raw_sources_indexed=false, missing_files=[], hash_mismatches=[]
remote retrieval check: OpenAI SDK chat gateway query returned updated repo-map, implementation-guidance, examples-evals, agent-roles, and product-context skill references in the top hits
git backup: remote archive stored at `/home/yyf/project/image_agent/backups/git_20260607T164120/image_agent_git_backup_openai_skill_wording_20260607T164120.tgz`
```

## BIDS Validator Official CLI Preflight RAG Expansion

Expanded the BIDS Validator curated RAG contract using the already downloaded official CLI and Docker raw snapshots. The new coverage keeps preflight explanations grounded in the official command-line surface while preserving the rule that raw snapshots are traceability/hash evidence only and are not indexed.

Changes made:

- Added regression coverage requiring official source ids `bids_validator_cli` and `bids_validator_docker` to remain available for the curated BIDS Validator summary.
- Updated `docs/rag/vendor/bids_validator_official_cli_docker.md` with `bids-validator <dataset>`, `--json`, `--format json`, `--format json_pp`, `--ignoreWarnings`, `--ignoreNiftiHeaders`, `--datasetTypes`, `--recursive`, `--config`, config-file influence, and `issues.errors` / `issues.warnings` / `summary` output boundaries.
- Fixed the RAG persistence test so local verification accepts the deterministic `local_manifest` fallback when optional LlamaIndex is not installed, while remote still verifies the LlamaIndex path.

TDD evidence:

```text
red BIDS Validator CLI contract: 1 failed because the curated validator doc did not name the official source ids or CLI/JSON/reporting flags
green BIDS Validator CLI contract: 1 passed after expanding the curated validator doc
red local RAG persistence fallback contract: 1 failed because local LlamaIndex is absent and the test expected docstore.json unconditionally
green local RAG persistence fallback contract: 1 passed after asserting chunks.jsonl for the local_manifest fallback
```

Local evidence:

```text
local docs/RAG/index/query suite: 42 passed
local persistent RAG rebuild: 68 documents, 233 chunks, local_manifest engine, semantic_index=true
local raw-source audit: 42 official snapshots, raw_sources_indexed=false, indexed_raw_sources=[], missing_files=[], hash_mismatches=[]
local retrieval check: BIDS Validator CLI/preflight query ranked docs/rag/vendor/bids_validator_official_cli_docker.md as the top three hits
git backup: local archive `image_agent_git_backup_bids_validator_rag_20260607T170000.tgz`
```

Remote evidence:

```text
remote sync archive: /tmp/image_agent_bids_validator_rag_sync_20260607T170000.tgz extracted under /home/yyf/project/image_agent
remote focused docs/RAG/index/query suite: 42 passed, 1 warning
remote persistent RAG rebuild: 68 documents, 233 chunks, LlamaIndex engine, semantic_index=true
remote raw-source audit: 42 official snapshots, raw_sources_indexed=false, indexed_raw_sources=[], missing_files=[], hash_mismatches=[]
remote retrieval check: BIDS Validator CLI/preflight query ranked docs/rag/vendor/bids_validator_official_cli_docker.md as the top three hits
git backup: remote archive stored at `/home/yyf/project/image_agent/backups/git_20260607T170000/image_agent_git_backup_bids_validator_rag_20260607T170000.tgz`
```

## BIDS Validator Workflow-Runner Skill Grounding

Connected the BIDS Validator official CLI preflight boundaries into workflow-runner skill references so execution-oriented agents retrieve the operational guidance before the lower-level vendor doc.

Changes made:

- Updated `docs/skills/image-agent-workflow-runner/references/registry-and-preflight.md` to point at `docs/rag/vendor/bids_validator_official_cli_docker.md` and distinguish JSON evidence, warning suppression, NIfTI-header skips, dataset-type filters, and recursive derivative validation.
- Updated `docs/skills/neuroimaging-workflow-runner/references/bids-inputs.md` with a Validator Preflight section for staged BIDS-like trees.
- Added regression coverage requiring workflow-runner skill references to include the official validator doc, `--json`, `--format json`, `--ignoreWarnings`, `--ignoreNiftiHeaders`, `--datasetTypes`, `--recursive`, and machine-readable evidence boundaries.

TDD evidence:

```text
red workflow-runner validator skill contract: 1 failed because skill references did not mention bids_validator_official_cli_docker.md or validator CLI flags
green workflow-runner validator skill contract: 1 passed after adding the skill-reference preflight sections
```

Local evidence:

```text
local focused docs/RAG/index/query suite: 43 passed
local persistent RAG rebuild: 68 documents, 234 chunks, local_manifest engine, semantic_index=true
local raw-source audit: 42 official snapshots, raw_sources_indexed=false, missing_files=[], hash_mismatches=[]
local retrieval check: workflow-runner BIDS Validator preflight query ranked neuroimaging-workflow-runner bids-inputs first, image-agent-workflow-runner registry-and-preflight second, and the official validator vendor doc third
git backup: local archive `image_agent_git_backup_bids_validator_skill_preflight_20260607T171500.tgz`
```

Remote evidence:

```text
remote sync archive: /tmp/image_agent_bids_validator_skill_preflight_sync_20260607T171500.tgz extracted under /home/yyf/project/image_agent
remote focused docs/RAG/index/query suite: 43 passed, 1 warning
remote persistent RAG rebuild: 68 documents, 234 chunks, LlamaIndex engine, semantic_index=true
remote raw-source audit: 42 official snapshots, raw_sources_indexed=false, indexed_raw_sources=[], missing_files=[], hash_mismatches=[]
remote retrieval check: workflow-runner BIDS Validator preflight query ranked neuroimaging-workflow-runner bids-inputs first, image-agent-workflow-runner registry-and-preflight second, and the official validator vendor doc third
git backup: remote archive stored at `/home/yyf/project/image_agent/backups/git_20260607T171500/image_agent_git_backup_bids_validator_skill_preflight_20260607T171500.tgz`
```

## FreeSurfer Official License RAG Expansion

Added a dedicated official FreeSurfer license boundary to the RAG corpus because the workflow registry and remote runtime repeatedly treat a FreeSurfer license as a hard preflight requirement for T1, BOLD/fMRIPrep, DeepPrep, QSIPrep, and QSIRecon-style paths.

Changes made:

- Added official raw source id `freesurfer_license_registration` for `https://surfer.nmr.mgh.harvard.edu/registration.html`.
- Added `docs/rag/vendor/freesurfer_official_license.md` covering `license.txt`, `FS_LICENSE`, `$FREESURFER_HOME/license.txt`, `--fs-license-file`, `--fs_license_file`, read-only support mounts, and no license-content exposure.
- Extended skill/RAG regression coverage so the FreeSurfer license source id, curated vendor doc, and runtime/configuration boundaries stay present.

TDD evidence:

```text
red FreeSurfer license contract: 1 failed because docs/rag/vendor/freesurfer_official_license.md did not exist
green FreeSurfer license contract: 1 passed after adding the official source, curated RAG doc, and license boundary wording
```

Local evidence:

```text
local fetch command: scripts/fetch_vendor_docs.py --fetch-timeout-seconds 30 --retry-attempts 2 --retry-delay-seconds 1 --use-existing-on-failure returned 43 sources
local focused docs/RAG/index/query suite: 44 passed
local persistent RAG rebuild: 69 documents, 237 chunks, local_manifest engine, semantic_index=true
local raw-source audit: 43 official snapshots, 19 curated vendor summaries, raw_sources_indexed=false, indexed_raw_sources=[], missing_files=[], hash_mismatches=[]
local retrieval check: FreeSurfer license query ranked docs/rag/vendor/freesurfer_official_license.md as the top three hits
git backup: local archive `image_agent_git_backup_freesurfer_license_rag_20260607T173000.tgz`
```

Remote evidence:

```text
remote sync archive: /tmp/image_agent_freesurfer_license_rag_sync_20260607T173000.tgz extracted under /home/yyf/project/image_agent
remote fetch command: scripts/fetch_vendor_docs.py --fetch-timeout-seconds 3 --retry-attempts 1 --retry-delay-seconds 0 --use-existing-on-failure returned 43 sources
remote focused docs/RAG/index/query suite: 44 passed, 1 warning
remote persistent RAG rebuild: 69 documents, 237 chunks, LlamaIndex engine, semantic_index=true
remote raw-source audit: 43 official snapshots, 19 curated vendor summaries, raw_sources_indexed=false, indexed_raw_sources=[], missing_files=[], hash_mismatches=[]
remote retrieval check: FreeSurfer license query ranked docs/rag/vendor/freesurfer_official_license.md as the top three hits
git backup: remote archive stored at `/home/yyf/project/image_agent/backups/git_20260607T173000/image_agent_git_backup_freesurfer_license_rag_20260607T173000.tgz`
```

## Scientific Report Provenance Boundary Hardening

Hardened the result-summary/scientific-report boundary so generated report-builder assets are explicitly separated from container-native QC evidence.

Changes made:

- `build_scientific_report_summary` now normalizes report assets with `source_stage: scientific_report`, `artifact_role: derived_presentation_asset`, `artifact_origin: generated_from_result_summary`, `native_artifact: false`, and `provenance.replaces_native_qc: false`.
- `verify_scientific_reports.py` now rejects generated report assets that lack derived-presentation provenance.
- Console result examples and modality panels now use current PNG report assets and label generated report figures as derived unless metadata says they are native artifacts.
- Updated workflow RAG and skill references so agents prefer container-native QC and describe report-builder PNGs as secondary presentation assets, not replacements.

TDD evidence:

```text
red backend report contract: 1 failed because scientific report artifacts lacked source_stage
green backend report contract: 1 passed after normalized derived provenance was added
red report verifier contract: 1 failed because unlabeled generated report assets were accepted
green report verifier contract: 1 passed after provenance checks were added
red console report figure contract: 1 failed because mock/report UI still expected SVG assets
green console report figure contract: 8 passed after PNG mocks and derived labels were added
```

Local evidence:

```text
local focused backend docs/RAG/report suite: 45 passed, 17 warnings
local console focused result suite: 8 passed
local console build: npm.cmd run build passed
local persistent RAG rebuild: 69 documents, 238 chunks, LlamaIndex engine
local raw-source audit: 43 official snapshots, 19 curated vendor summaries, raw_sources_indexed=false, indexed_raw_sources=[], missing_files=[], hash_mismatches=[]
local retrieval check: scientific-report provenance query ranked image-agent-developer contracts, operator product context, workflow-runner container QC, testing matrix, and DWI workflow RAG in top hits
git backup: local archive `image_agent_git_backup_report_provenance_20260607T172500.tgz`
```

Remote evidence:

```text
remote pre-sync source backup: `/home/yyf/project/image_agent/backups/git_20260607T172500/report_provenance_targets_before.tgz`
remote local backup archive copy: `/home/yyf/project/image_agent/backups/git_20260607T172500/image_agent_git_backup_report_provenance_20260607T172500.tgz`
remote sync archive: `/home/yyf/project/image_agent/image_agent_report_provenance_api_docs_sync_20260607T172500.tgz`
remote focused backend docs/RAG/report suite: 45 passed, 3 warnings
remote persistent RAG rebuild: 69 documents, 238 chunks, LlamaIndex engine
remote raw-source audit: 43 official snapshots, 19 curated vendor summaries, raw_sources_indexed=false, indexed_raw_sources=[], missing_files=[], hash_mismatches=[]
remote retrieval check: scientific-report provenance query ranked image-agent-developer contracts, operator product context, workflow-runner container QC, testing matrix, and DWI workflow RAG in top hits
remote real-output verifier before regeneration: failed for tasks 41, 111, and 114 because older report summaries lacked derived provenance
remote real-output backup before regeneration: `/home/yyf/project/image_agent/backups/git_20260607T172500/real_report_outputs_41_111_114_before_regen.tgz`
remote report regeneration: `apps/api/scripts/regenerate_scientific_reports_41_111_114.py` rewrote T1, BOLD, and DWI scientific report summaries
remote real-output verifier after regeneration: PASS for T1 task 41, BOLD task 111, and DWI task 114
```

## Sensitive Runtime Script Hygiene

Removed a hard-coded sudo password pattern from the DeepPrep-to-XCP-D helper script and added a regression guard so runtime scripts cannot pipe literal passwords into `sudo -S` or pass command-line `--password=...` values.

Changes made:

- Updated `apps/api/scripts/run_xcpd_deepprep_115.sh` to require `IMAGE_AGENT_SUDO_PASSWORD` at runtime instead of storing a literal password in the script.
- Added `test_runtime_scripts_do_not_pipe_literal_passwords_to_sudo` to scan runtime scripts under `apps/api/scripts` and `tools`.
- Updated workflow-runner security guidance to require backend-managed `IMAGE_AGENT_SUDO_PASSWORD` for unavoidable sudo use and keep the value out of command previews, logs, docs, and RAG chunks.

TDD evidence:

```text
red sensitive-script guard: 1 failed because apps/api/scripts/run_xcpd_deepprep_115.sh matched echo ... | sudo -S
green sensitive-script guard: 1 passed after the helper script switched to IMAGE_AGENT_SUDO_PASSWORD
```

Local evidence:

```text
local focused backend/skill/agent suite: 43 passed
local unsafe-pattern scan: no matches for echo ... | sudo -S, command-line --password=..., or the prior literal password
local persistent RAG rebuild: 69 documents, 239 chunks, LlamaIndex engine
local raw-source audit: 43 official snapshots, 19 curated vendor summaries, raw_sources_indexed=false, indexed_raw_sources=[], missing_files=[], hash_mismatches=[]
local retrieval check: sudo/password safety query ranked docs/skills/image-agent-workflow-runner/references/security-and-containers.md first
git backup: local archive `image_agent_git_backup_sensitive_script_hygiene_20260607T173500.tgz`
```

Remote evidence:

```text
remote pre-sync source backup: `/home/yyf/project/image_agent/backups/git_20260607T173500/sensitive_script_targets_before.tgz`
remote local backup archive copy: `/home/yyf/project/image_agent/backups/git_20260607T173500/image_agent_git_backup_sensitive_script_hygiene_20260607T173500.tgz`
remote sync archive: `/home/yyf/project/image_agent/image_agent_sensitive_script_hygiene_sync_20260607T173500.tgz`
remote focused backend/skill/agent suite: 43 passed
remote unsafe-pattern scan: no matches for echo ... | sudo -S, command-line --password=..., or the prior literal password
remote persistent RAG rebuild: 69 documents, 239 chunks, LlamaIndex engine
remote raw-source audit: 43 official snapshots, 19 curated vendor summaries, raw_sources_indexed=false, indexed_raw_sources=[], missing_files=[], hash_mismatches=[]
remote retrieval check: sudo/password safety query ranked docs/skills/image-agent-workflow-runner/references/security-and-containers.md first
```
