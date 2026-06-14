# Image Agent Product Readiness Gate

This gate defines when Image Agent is mature enough to tell the user that frontend page design and real product use can begin.

Until every required evidence item below is current and verified, the product is still in backend/agent hardening mode. Do not start frontend page design, do not present the existing console UI as production-ready, and do not treat local-only checks as acceptance.

## Frontend Design Freeze Gate

Frontend page design may start only after all rows are marked with fresh evidence:

| Area | Required evidence | Blocking failure |
| --- | --- | --- |
| Agent architecture | OpenAI SDK Responses-style gateway path is the primary model boundary, tool calls use structured function-tool contracts, and API tests cover planner/responder/tool-dispatch behavior. | Any direct model-call path bypasses `ModelGateway`, tool calls are not structured, or durable run/thread state cannot be queried. |
| Run traceability | Durable run/thread state records safe lifecycle events, selected skill, model gateway access, retrieved sources, tool invocations, and safe metadata. | Agent work cannot be audited by `agent_run_id`, or read APIs expose prompts, secrets, local paths, or raw user content. |
| Result contracts | `/result-contract`, `/tasks/{task_id}/result-summary`, and `/tasks/{task_id}/artifact-manifest` document and serve stable result fields with safe `relative_path`, `download_url`, `content_type`, `size_bytes`, `preview_kind`, and provenance. | Frontend consumers must infer artifact cards from arbitrary text, local absolute paths leak, or legacy summaries can break current readers. |
| Workflow launchability | Project series, series detail, and ingest inventory expose `workflow_eligibility` with `policy_version=workflow_eligibility_v1`, `production_task_created=false`, runnable/blocked workflow lists, and clear reasons. | The agent or frontend has to guess whether T1, BOLD, DWI, or QSI workflows are runnable. |
| Official-source RAG | RAG uses curated official-source RAG summaries backed by `docs/rag/vendor/raw-sources/manifest.json`; raw-source manifest rows prove downloaded source URLs, hashes, source types, and raw files, but raw snapshots are not indexed as answer text. | RAG answers cite raw snapshots as answer sources, missing source ids, stale vendor pointers, or unsupported container behavior. |
| RAG answer boundaries | RAG answers state boundaries, expected outputs, non-diagnostic limits, original curated sources, and when remote verification is required. | Answers imply local execution, diagnosis, unsupported workflow behavior, or acceptance without remote evidence. |
| Workflow QC artifacts | Result images and reports rely on Docker/container-native QC artifacts such as fMRIPrep HTML, XCP-D HTML, DeepPrep QC, FreeSurfer snapshots, MRIQC outputs, QSIPrep/QSIRecon reports, or other container outputs. | Local code pretends to regenerate official QC, or derived scientific reports replace native QC evidence. |
| Derived report artifacts | Scientific report HTML/PNG artifacts are allowed only as generated presentation assets from result summaries, with `native_artifact=false` and `provenance.replaces_native_qc=false`. | Report-layer figures are treated as container-native QC or accepted without separate native QC evidence. |
| Skills | Image Agent skills remain skill-creator-style: clear trigger rules, operating rules, reference loading, output shape, eval hints, and routing between image-agent and neuroimaging workflow skills. | Skills have stale model/provider wording, missing references, unclear routing, or no eval/backlog coverage. |
| Remote production proof | Strict remote acceptance runs on the remote server after deployment with real project/upload/task ids and configured model gateway. The saved JSON passes `apps/api/scripts/verify_remote_smoke_acceptance.py --max-age-hours 24`. | Only local tests pass, remote model is unconfigured, real evidence ids are missing, the JSON is stale, or the offline verifier fails. |

## Remote Acceptance Minimum

The remote server is the authority for install, testing, running, and production acceptance. Local tests can prove code and contract intent, but they cannot prove deployment readiness.

The strict remote acceptance package must include:

- Deployed package identity or commit, recorded as a privacy-safe `deployment_id`.
- `/health` returning `app=image_agent`.
- `/agent/model/status` with the OpenAI SDK gateway configured.
- `model_smoke_status=passed` from a live `/agent/runs` smoke.
- RAG document/chunk thresholds, semantic index, clean raw-source policy, complete curated provenance, safe vendor coverage catalog, and vendor pointer integrity.
- Real evidence ids with `remote_evidence_ids_status=passed`.
- Launchability matrix evidence from `/agent/rag/query` citation/source fields.
- `project_contract_status=passed`, `upload_inventory_contract_status=passed`, and `task_artifact_manifest_status=passed`.
- `container_native_qc_status=passed`, served container-native QC artifact URLs, accepted curated `official_source_ids`, and enough native QC images.
- `scientific_report_artifacts_status=passed`, served report HTML/PNG URLs, and derived-presentation provenance that does not replace native QC.
- Offline verifier output from `python scripts/verify_remote_smoke_acceptance.py <remote-smoke-acceptance.json> --max-age-hours 24` with `status=passed`, including `deployment_identity_status=passed`, a `deployment_identity.deployment_id` matching `smoke_gate.deployment_id`, and a privacy-safe `deployment_identity.health_version`.

`skipped_missing_model_config` is not production acceptance. Health, RAG, or local pytest success without a configured remote model gateway is not enough to release the frontend gate.

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
Once those stale task records are resolved through this approved flow, normal
restarts should no longer require overriding the active-task drain gate.
