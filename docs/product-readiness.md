# Image Agent Product Readiness Gate

This gate defines when Image Agent is mature enough to tell the user that frontend page design and real product use can begin.

Until every required evidence item below is current and verified, the product is still in backend/agent hardening mode. Do not start frontend page design, do not present the existing console UI as production-ready, and do not treat local-only checks as acceptance.

## Fast Launch Main Flow Goal

The current near-term product goal is to make the existing console usable as quickly as possible for the core workflow: upload imaging data, Agent interaction, select a workflow, and start processing. This is a product-smoke milestone, not a replacement for strict remote production acceptance.

Minimum backend/frontend contract for this fast launch:

- Upload imaging data through `/projects/{project_id}/upload`, `/projects/{project_id}/upload-dwi`, `/projects/{project_id}/upload-dicom`, or the upload-session ingest endpoints.
- Refresh detected series through `/projects/{project_id}/series`, including modality, sequence label, support status, and `workflow_eligibility` where available.
- List selectable workflows through `/workflows`, and show blocked/runnable state from backend contracts rather than frontend guesses.
- Start processing through `/series/{series_id}/run` only after backend validation accepts the selected workflow and series.
- Show task state through `/projects/{project_id}/tasks`, `/tasks/{task_id}`, redacted `/tasks/{task_id}/logs`, `/tasks/{task_id}/outputs`, `/tasks/{task_id}/result-summary`, and `/tasks/{task_id}/artifact-manifest`.
- Support dashboard chat with `/chat` and grounded Agent review with `/agent/rag/query`; the model may be configured later, but the UI must clearly handle fallback/rules-based status.
- Configure browser access with `IMAGE_AGENT_CORS_ORIGINS`; local development may use localhost defaults, but public deployment must not rely on wildcard CORS.
- Configure `IMAGE_AGENT_PUBLIC_BASE_URL` for production so `/deployment.production_readiness` can prove the public HTTPS API base used by the console and strict remote smoke evidence.
- Read `/deployment.fast_launch_readiness` before treating the Gemini console as launchable. It must report the rawchat GPT-5.5 Responses target, the deterministic Agent/task boundary, the upload-workflow-result contract, and strict remote acceptance evidence.

Fast-launch boundary rules:

- Agent may recommend or explain workflows, but task creation must still go through deterministic backend APIs and backend validation.
- RAG may explain official sources, but backend project/task state remains authoritative.
- Mock tests prove the control plane: API contracts, schema validation, Agent/task boundaries, workflow registry matching, preflight blocking, task state transitions, log/output registration, result-summary and artifact-manifest contracts, and frontend integration.
- Real script tests prove the execution plane: deployed-server local Docker/toolchain execution, GPU and license visibility, BIDS inputs, sidecar handling, external tool outputs, traceable logs, and result summaries derived from real outputs.
- Real processing acceptance belongs on the deployed API server. Local workstation tests prove contracts, not the deployed server's local Docker/FSL/MRtrix/FreeSurfer/container readiness.
- Container-native QC and result artifact display must rely on workflow outputs and artifact manifests, not locally invented frontend previews.
- No API keys, patient identifiers, raw source snapshots, backend absolute paths, raw task log paths, or sensitive logs may be exposed through chat, RAG status, task logs, artifact manifests, or frontend settings.

Fast local product smoke:

```bash
cd apps/api
python scripts/smoke_local_main_flow.py --api-base http://127.0.0.1:8000 --output-json ../../docs/deployment/local-main-flow-smoke.json
```

This smoke creates a temporary project, uploads a minimal generated T1 NIfTI when `--upload-nifti-file` is not supplied, verifies the uploaded series is returned by `/projects/{project_id}/series`, starts `t1_deepprep_mock` through `/series/{series_id}/run`, checks the task list, checks `/agent/model/status`, and requires `/agent/rag/status.grounding_policy`. Use `--min-rag-documents <n>` for launch rehearsal when an empty RAG index should fail. It does not call `/agent/runs` unless `--require-agent-confirmation` is set; add that flag only when the local model gateway is configured and expected to return a workflow confirmation. Add `--require-agent-resume` when the local smoke must prove the server-side confirmation path by posting `/agent/runs/{thread_id}/resume`; the output must then include `agent_workflow_resume_status=passed`, `production_task_created=true`, and `confirmation_gate=fingerprint_verified`. The smoke output is path-safe and records that it is local-only evidence; it does not prove the deployed server's local containers, real MRI processing, container-native QC artifacts, production CORS, or strict deployment acceptance.

For a stricter local launch rehearsal after docs are present, use:

```bash
python scripts/smoke_local_main_flow.py --api-base http://127.0.0.1:8000 --workflow-type t1_deepprep_mock --agent-workflow-type t1_deepprep_anat_report --expected-model-provider-profile rawchat --expected-model-wire-api responses --expected-model-name gpt-5.5 --require-model-tool-loop --rebuild-rag --min-rag-documents 60 --require-agent-confirmation --require-agent-resume --wait-task-completion-timeout-seconds 20 --wait-task-completion-poll-seconds 0.5 --require-task-outputs --require-result-summary --require-artifact-manifest
```

That stricter command keeps the quick local data path on `t1_deepprep_mock` but requires the Agent to prepare and resume a confirmation for the formal fixed workflow `t1_deepprep_anat_report`. The task used for downstream checks comes from `/agent/runs/{thread_id}/resume`, not an extra direct launch call, and the smoke records `agent_workflow_resume_status=passed`, `production_task_created=true`, and `confirmation_gate=fingerprint_verified` before it checks the task list, outputs, result summary, and artifact manifest. It also pins the local development model to rawchat GPT-5.5 Responses with model tool-loop capability, waits for the resumed task to complete, and requires safe task outputs, a unified result summary, and a non-empty artifact manifest for frontend display. It is expected to fail when the model gateway is unconfigured or not rawchat GPT-5.5 Responses, the Agent cannot produce a workflow confirmation, the server-side resume fingerprint gate fails, the local RAG index cannot be rebuilt to the required document count, task completion/output registration breaks, or the result/artifact contracts are empty. This is local-only control-plane evidence and does not prove the deployed server's local Docker/toolchain execution; strict deployment smoke must use a real registered workflow, and `t1_deepprep_mock` is rejected by the strict smoke and saved-evidence verifier.

Current model gateway finding: the rawchat GPT-5.5 OpenAI-compatible Responses path passed direct SDK, `ModelGateway`, strict local smoke, and browser dashboard checks with `OPENAI_WIRE_API=responses`, so this is the fastest-launch target for local development and remote acceptance. Krill Chat Completions remains a compatibility fallback for providers whose Responses route does not return parseable output. In Chat Completions mode, model-backed text and JSON planning work, but the Responses tool loop is intentionally reported as skipped and workflow launch must continue through deterministic backend confirmation APIs.

## Frontend Design Freeze Gate

Frontend page design may start only after all rows are marked with fresh evidence:

| Area | Required evidence | Blocking failure |
| --- | --- | --- |
| Agent architecture | OpenAI SDK Responses-style or Chat Completions-compatible gateway path is the primary model boundary, tool calls use structured function-tool contracts when the wire API supports them, Chat Completions planning is explicitly traced as no tool loop, and API tests cover planner/responder/tool-dispatch behavior. | Any direct model-call path bypasses `ModelGateway`, Chat Completions pretends to dispatch tools, tool calls are not structured on Responses-capable gateways, or durable run/thread state cannot be queried. |
| Run traceability | Durable run/thread state records safe lifecycle events, selected skill, model gateway access, retrieved sources, tool invocations, and safe metadata. | Agent work cannot be audited by `agent_run_id`, or read APIs expose prompts, secrets, local paths, or raw user content. |
| Result contracts | `/result-contract`, `/tasks/{task_id}/result-summary`, and `/tasks/{task_id}/artifact-manifest` document and serve stable result fields with safe `relative_path`, `download_url`, `content_type`, `size_bytes`, `preview_kind`, and provenance. | Frontend consumers must infer artifact cards from arbitrary text, local absolute paths leak, or legacy summaries can break current readers. |
| Workflow launchability | Project series, series detail, and ingest inventory expose `workflow_eligibility` with `policy_version=workflow_eligibility_v1`, `production_task_created=false`, runnable/blocked workflow lists, and clear reasons. | The agent or frontend has to guess whether T1, BOLD, DWI, or QSI workflows are runnable. |
| Official-source RAG | RAG uses curated official-source RAG summaries backed by `docs/rag/vendor/raw-sources/manifest.json`; raw-source manifest rows prove downloaded source URLs, hashes, source types, and raw files, but raw snapshots are not indexed as answer text. | RAG answers cite raw snapshots as answer sources, missing source ids, stale vendor pointers, or unsupported container behavior. |
| RAG answer boundaries | RAG answers state boundaries, expected outputs, non-diagnostic limits, original curated sources, and when deployed-server verification is required. | Answers imply workstation execution, diagnosis, unsupported workflow behavior, or acceptance without deployment evidence. |
| Workflow QC artifacts | Result images and reports rely on Docker/container-native QC artifacts such as fMRIPrep HTML, XCP-D HTML, DeepPrep QC, FreeSurfer snapshots, MRIQC outputs, QSIPrep/QSIRecon reports, or other container outputs. | Local code pretends to regenerate official QC, or derived scientific reports replace native QC evidence. |
| Derived report artifacts | Scientific report HTML/PNG artifacts are allowed only as generated presentation assets from result summaries, with `native_artifact=false` and `provenance.replaces_native_qc=false`. | Report-layer figures are treated as container-native QC or accepted without separate native QC evidence. |
| Runtime version lock | Production workflow registry and deployment-local scripts use fixed image tags or digests such as `pbfslab/deepprep:25.1.0`, `nipreps/fmriprep:25.2.5`, `pennlinc/xcp_d:26.0.2`, `pennlinc/qsiprep:1.0.2`, and `pennlinc/qsirecon:26.0.0`; strict acceptance rejects `:latest` or untagged execution images. | Real execution evidence omits tool/container versions, deployment scripts pull floating `latest` tags, or registry/runner contracts disagree about the image used. |
| Skills | Image Agent skills remain skill-creator-style: clear trigger rules, operating rules, reference loading, output shape, eval hints, and routing between image-agent and neuroimaging workflow skills. | Skills have stale model/provider wording, missing references, unclear routing, or no eval/backlog coverage. |
| Deployment production proof | Strict deployment acceptance runs on the deployed API server after deployment with real project/upload/task ids, local Docker/toolchain execution, and configured model gateway. The saved JSON passes `apps/api/scripts/verify_remote_smoke_acceptance.py --max-age-hours 24`; the script name is historical. | Only workstation tests pass, the deployed model gateway is unconfigured, local containers/tools on the deployed server are unproven, real evidence ids are missing, the JSON is stale, or the offline verifier fails. |

## Deployment Acceptance Minimum

The deployed API server is the authority for install, testing, running, and production acceptance. Local workstation tests can prove code and contract intent, but they cannot prove deployment readiness. All workflow scripts and Docker commands run against that server's local filesystem, local Docker daemon, local GPU visibility, local FSL/MRtrix/FreeSurfer installation, and local container image cache.

The strict remote acceptance package must include:

- Deployed package identity or commit, recorded as a privacy-safe `deployment_id`.
- `/health` returning `app=image_agent` and a privacy-safe `version` that matches the expected deployed package/version when the strict smoke gate supplies `--expected-health-version`.
- `/agent/model/status` with the OpenAI-compatible SDK gateway configured, a safe `provider_profile` such as `rawchat`, `openai`, `krill`, `deepseek`, or `glm`, a `capabilities` matrix, and `wire_api` matching the strict smoke gate's `--expected-model-wire-api` value. For the current rawchat GPT-5.5 fast-launch target this is `responses`.
- `model_smoke_status=passed` from a live `/agent/runs` smoke.
- `agent_workflow_confirmation_status=passed` showing the Agent can prepare `status=confirmation_required` for the selected workflow while `production_task_created=false`.
- RAG document/chunk thresholds, semantic index, clean raw-source policy, complete curated provenance, safe vendor coverage catalog, and vendor pointer integrity.
- Real evidence ids with `remote_evidence_ids_status=passed`.
- Deterministic launch of a real registered workflow from the uploaded series; debug-only mock workflows such as `t1_deepprep_mock` are rejected by strict deployment acceptance.
- Launchability matrix evidence from `/agent/rag/query` citation/source fields.
- `project_contract_status=passed`, `upload_inventory_contract_status=passed`, and `task_artifact_manifest_status=passed`.
- `container_native_qc_status=passed`, served container-native QC artifact URLs, accepted curated `official_source_ids`, and enough native QC images.
- `scientific_report_artifacts_status=passed`, served report HTML/PNG URLs, and derived-presentation provenance that does not replace native QC.
- Offline verifier output from `python scripts/verify_remote_smoke_acceptance.py <remote-smoke-acceptance.json> --max-age-hours 24` with `status=passed`, including `deployment_identity_status=passed`, a `deployment_identity.deployment_id` matching `smoke_gate.deployment_id`, a privacy-safe `deployment_identity.health_version` matching `smoke_gate.expected_health_version` when supplied, `model_status.wire_api` matching `smoke_gate.expected_model_wire_api`, `model_status.provider_profile` matching `smoke_gate.expected_model_provider_profile`, and `model_status.capabilities.model_tool_loop=true` when `smoke_gate.require_model_tool_loop=true`.

`skipped_missing_model_config` is not production acceptance. Health, RAG, or local pytest success without a configured remote model gateway is not enough to release the frontend gate.

`/deployment.fast_launch_readiness` is the operator-facing summary for this gate. It is `ready=true` only when:

- `checks.model_gateway_target.status=passed` for `provider_profile=rawchat`, `wire_api=responses`, `model=gpt-5.5`, and `model_tool_loop=true`.
- `checks.agent_task_boundary.status=passed`, with chat limited to read/explain/recommend and actual workflow launch still routed through `/series/{series_id}/run` or the server-side resume confirmation path.
- `checks.upload_workflow_result_contract.status=passed`, listing upload, series, workflow launch, output, result-summary, and artifact-manifest contracts.
- `checks.strict_remote_acceptance.status=passed`, backed by a privacy-safe `IMAGE_AGENT_STRICT_REMOTE_ACCEPTANCE_ID` from a strict remote smoke JSON verified inside the freshness window.

Generate the remote acceptance environment values from the already-passed verifier instead of hand-writing them:

```bash
python scripts/verify_remote_smoke_acceptance.py <remote-smoke-acceptance.json> --max-age-hours 24 --emit-fast-launch-env
```

This prints only `IMAGE_AGENT_STRICT_REMOTE_ACCEPTANCE_STATUS=passed` and a privacy-safe `IMAGE_AGENT_STRICT_REMOTE_ACCEPTANCE_ID` derived from the strict smoke `deployment_id`. This field is a summary of launch readiness, not a replacement for the saved remote smoke JSON or the offline verifier. A local rawchat pass keeps development moving, but formal release still needs the remote evidence id.
The release gate command plan and stale-task apply request both require this export step after strict JSON verification, so the fast-launch UI state is derived from the same evidence package rather than a hand-written acceptance label.

## BMAD-Inspired Operating Model

Use the BMAD Method as process guidance, not as a local installation requirement. The upstream project describes structured workflows across analysis, planning, architecture, and implementation, with specialized agents for roles such as PM, Architect, Developer, UX, and testing. For this repo, keep the split practical:

- PM/readiness: maintain this product gate, epics, and acceptance status.
- Architect: keep SDK-like module boundaries and API/result contracts stable.
- RAG curator: maintain official downloaded sources, curated summaries, source ids, and answer boundaries.
- Skill maintainer: keep Image Agent skills aligned with skill-creator-style structure.
- Workflow QC reviewer: verify container-native QC artifact provenance and derived report boundaries.
- Operations: maintain work logs, git backups, remote acceptance evidence, and no-secret/no-path-leak checks.

## Current Status

As of 2026-06-11, the live remote API is serving committed release `f57a2ea`
from release overlay
`/home/yyf/project/image_agent_releases/codex-f57a2ea-20260611T023456/apps/api`.
The dirty remote main worktree is no longer the serving path for the accepted
API process.

Strict remote acceptance passed after that release-overlay restart. The
saved evidence is
`/tmp/image_agent_task118_live8000_post_restart_f57a2ea_20260611.json`, and the
offline verifier reported `status=passed` for model smoke, real evidence ids,
RAG vendor pointer integrity, launchability query citation, project/upload
contracts, artifact manifest, container-native QC, and derived scientific report
artifacts. That evidence predates the timestamp-freshness verifier option added
later on 2026-06-11, so the frontend release gate still requires a new saved
JSON that passes `--max-age-hours 24` after normal restart.

Frontend design is still held until the final operational cleanup is resolved:
the restart used `IMAGE_AGENT_ALLOW_RESTART_WITH_ACTIVE_TASKS=1` because legacy
tasks `83` and `84` remain in `running` state even though they appear stale.
An auditable stale-task reconciliation tool now exists in
`apps/api/scripts/reconcile_stale_tasks.py`, but production task rows should be
changed only after an operator reviews the dry-run output and approves apply
mode. The tool now emits a dry-run `approval_fingerprint`; apply mode can read
the reviewed report via `--approval-json` and require that fingerprint before
mutating rows so scoped task ids and container-label evidence cannot drift
silently between review and apply. The dry-run report can be checked with
`apps/api/scripts/verify_stale_task_approval.py` before apply approval. After
approved apply, the apply JSON and a second scoped dry-run must be checked with
`apps/api/scripts/verify_stale_task_resolution.py`; that verifier must print
`status=passed`, reject `log_path`, and reject backend absolute paths anywhere
in the saved stale-task evidence. The stale-task approval/apply/resolution
artifacts must include timezone-aware `generated_at` timestamps, and the
resolution `generated_at` must be after or equal to apply `generated_at` before
a normal restart without the active-task override is accepted. In short,
stale-task evidence must pass a `max_age_hours` freshness limit through the
approval and resolution verifier scripts before it can unblock normal restart
or frontend release evidence. A remote dry-run from non-live release
`118c407` reported tasks `83` and `84` as stale candidates older than 531
hours, and a shared-env Docker label check returned no running labelled Image
Agent task ids. A fresh non-live release overlay dry-run on 2026-06-11 reported
`container_check_status=passed`, `running_container_task_ids=[]`, scoped
`stale_candidates=[83,84]`, and
`approval_fingerprint=139113571daf0137a3e34be526fd25ccaa8066aed725ab7c0b846cfc7eb3abd0`,
saved on the remote host at
`/tmp/image_agent_stale_tasks_83_84_fingerprint_dry_run_20260611T1215.json`.
As of the 2026-06-13 remote read-only dry-run, fresh approval evidence now exists
against the same scoped task ids. The dry-run JSON is saved on the remote host at
`/tmp/image_agent_stale_tasks_83_84_dry_run_20260613T1640Z.json`; the current
local verifier checked that file with `--max-age-hours 24` and reported
`status=passed`, `checked.generated_at_utc=2026-06-13T16:40:24.758668+00:00`,
`checked.container_check_status=passed`,
`checked.running_container_task_ids=[]`, and the same approval fingerprint
`139113571daf0137a3e34be526fd25ccaa8066aed725ab7c0b846cfc7eb3abd0`. This is
operator-review evidence only: approved apply has not been run, the post-apply
`verify_stale_task_resolution.py --require-empty-active --max-age-hours 24`
gate has not passed, and a normal restart plus fresh strict smoke evidence are
still required.
To avoid using stale verifier scripts during that operator-approved path, a
remote gate verifier overlay now exists at
`/home/yyf/project/image_agent_releases/codex-gate-verifiers-efca895b-20260613T165132`.
This non-live overlay was copied from the prior stale-task tooling overlay and
then updated from local commit `efca895b`; it now exposes `--max-age-hours` on
both stale-task verifier CLIs. On the remote server, the overlay verified the
fresh dry-run JSON above with `status=passed`, and its stale-task test slice
reported `40 passed`. This overlay is a prepared verifier/apply tooling base,
not production acceptance and not a service restart.
The same remote gate verifier overlay has also been refreshed with current
strict smoke gate scripts from local commit `7b12e615`. Its
`verify_remote_smoke_acceptance.py -h` output exposes `--max-age-hours` and
`--now-utc`, and the remote strict-smoke test slice
`tests/test_verify_remote_smoke_acceptance.py tests/test_smoke_remote_agent.py`
reported `179 passed`. This prepares the post-restart strict smoke acceptance
tooling but does not replace running a fresh strict remote acceptance smoke
after normal restart.
The restart wrapper now also has a non-destructive preflight mode:
`IMAGE_AGENT_RESTART_PREFLIGHT_ONLY=1`. It runs the active-task drain and
port-owner checks without stopping or starting the API; a clean preflight prints
`restart_preflight:ok`. Use it after stale-task resolution and before the normal
restart, so restart blockers are caught before any service mutation.
The non-live remote gate verifier overlay has been updated with this restart
preflight mode and its remote restart-script test slice reported `6 passed`.
Before stale-task apply, the preflight-only command still fails at the drain gate
with active tasks `83` and `84`, which confirms the current blocker without
stopping or starting the API.
The full post-authorization command sequence is now captured in
`docs/deployment/remote-release-gate-command-plan.json` and checked by
`apps/api/scripts/verify_release_gate_command_plan.py`. That machine-checkable
plan fixes the required order: fresh stale-task approval verification,
operator-approved apply, post-apply clean dry-run, resolution verification,
`IMAGE_AGENT_RESTART_PREFLIGHT_ONLY=1` reaching `restart_preflight:ok`, normal
restart without `IMAGE_AGENT_ALLOW_RESTART_WITH_ACTIVE_TASKS=1`, strict remote
smoke, and offline strict smoke JSON verification with `--max-age-hours 24`.
It is an execution plan and guardrail, not evidence that apply, restart, or
strict smoke acceptance has already happened.
The plan also includes `stale_task_approval_refresh` for
`approval_json_missing_or_older_than_24h`; that command creates a fresh
read-only `--check-containers --task-id 83 --task-id 84` dry-run and must be
operator-reviewed before it replaces the approval JSON used by apply.
The refresh/apply/post-apply dry-run commands now load the remote environment
with `set -a; . /home/yyf/project/image_agent/.env; set +a` before Docker label
checks, because `IMAGE_AGENT_SUDO_PASSWORD` is required for those checks. A
fresh read-only approval refresh on 2026-06-14 saved
`/tmp/image_agent_stale_tasks_83_84_dry_run_20260614T080202Z.json`; the remote
approval verifier reported `status=passed`,
`checked.generated_at_utc=2026-06-14T08:02:02.843606+00:00`,
`checked.container_check_status=passed`,
`checked.running_container_task_ids=[]`, and the same approval fingerprint
`139113571daf0137a3e34be526fd25ccaa8066aed725ab7c0b846cfc7eb3abd0`.
The non-live remote gate verifier overlay was refreshed with local commit
`dc5e9471`; its command-plan verifier reported `status=passed` against the new
approval JSON path, and the focused remote readiness test slice reported
`6 passed`.
Before the operator-approved mutation, use
`apps/api/scripts/build_stale_task_apply_request.py` to turn the verified
approval dry-run into a `stale_task_apply_approval` JSON handoff. That request
records the reviewed `approval_fingerprint`, exact env-loading apply command,
required post-apply clean verification, preflight-only restart, normal restart,
strict remote smoke, offline strict smoke JSON verification, and
`authorization_required=true`; generating it does not run `--apply`.
The non-live remote overlay generated an actual approval request at
`/tmp/image_agent_stale_tasks_83_84_apply_request_20260614T080202Z.json` with
`request_type=stale_task_apply_approval`,
`authorization_required=true`, `approval_expires_at_utc=2026-06-15T08:02:02.843606+00:00`,
and follow-up ids including `restart_api_normally` and
`run_strict_remote_smoke_acceptance`.
Before approval, check that request with
`apps/api/scripts/verify_stale_task_apply_request.py`; the verifier must report
`status=passed`, recompute the same approval expiry, and only statically
validate the request JSON without running the embedded apply, restart, or smoke
commands.
The non-live remote overlay verified
`/tmp/image_agent_stale_tasks_83_84_apply_request_20260614T080202Z.json` with
`verify_stale_task_apply_request.py`; it reported `status=passed`,
`checked.authorization_required=true`, and
`checked.verified_approval_generated_at_utc=2026-06-14T08:02:02.843606+00:00`,
with `checked.expires_at_utc=2026-06-15T08:02:02.843606+00:00`.
That expiry is computed from `verified_approval.checked.generated_at_utc +
freshness_hours` and is also repeated as the top-level
`approval_expires_at_utc` field in the saved apply request.
The release plan records the same rule as `approval_request_requirements` so
the approval request shape stays machine-checkable.
The non-live remote gate verifier overlay has also been refreshed with this
command plan slice from local commit `dc1bdaf9`; on the remote server,
`verify_release_gate_command_plan.py docs/deployment/remote-release-gate-command-plan.json`
reported `status=passed`, and the focused remote test slice
`tests/test_release_gate_command_plan.py` plus the product-readiness gate test
reported `4 passed`. This proves the operator command plan is present and
machine-checkable on the remote verifier overlay, but it still does not mutate
tasks, restart the service, or run strict smoke acceptance.
The same overlay was then refreshed with local commit `cd9f4a3a`, including
the stale-task approval refresh path; the remote command-plan verifier reported
`checked.approval_refresh_required_when=approval_json_missing_or_older_than_24h`
with `status=passed`, and the focused remote test slice reported `5 passed`.
As of 2026-06-16, that 2026-06-14 approval and the generated
`/tmp/image_agent_stale_tasks_83_84_apply_request_20260614T080202Z.json` are
outside the 24 hour freshness window. The current
`docs/deployment/remote-release-gate-command-plan.json` therefore has
`status=approval_refresh_required`; its verifier reports
`checked.approval_json_status=refresh_required`, preserves the expired path only
as `previous_approval_json`, and uses `<fresh_reviewed_approval_json>` in the
verify/apply commands. The previous approval JSON must not be used for apply.
Before any remote mutation, the operator must run the documented
`stale_task_approval_refresh`, review the refreshed dry-run output and
`approval_fingerprint`, then run `build_release_gate_command_plan.py` to
materialize an `operator_authorization_required` plan from the reviewed path
instead of editing `<fresh_reviewed_approval_json>` by hand. If that builder
reads a copied local approval file, `--approval-json-command-path` must still be
the server-side `/tmp/image_agent_*.json` path embedded into the apply commands;
local workstation paths are rejected from the command plan. After refresh, the
same verifier accepts only a plan whose
`approval_json_state.status=fresh_reviewed` and
`approval_json_state.approval_expires_at_utc` is still in the future; expired
reviewed approval JSON must return the plan to the refresh path. Once those
stale task records are resolved through this approved flow, normal restarts
should no longer require overriding the active-task drain gate.
The strict remote smoke step now also requires `--require-uploaded-series` with
`--upload-nifti-file <remote_nifti_file>`: the smoke runner must upload that
file through `/projects/{project_id}/upload`, validate the returned
`workflow_eligibility`, record `uploaded_series_status=passed`, and use the
returned series id for `/series/{series_id}/run`. Supplying an already-known
`--launch-series-id <uploaded_series_id>` is no longer sufficient evidence for
the fastest-launch main chain, because it proves workflow launch but not the
actual upload-to-series path.
