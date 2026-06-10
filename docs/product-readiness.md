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
| Remote production proof | Strict remote acceptance runs on the remote server after deployment with real project/upload/task ids and configured model gateway. The saved JSON passes `apps/api/scripts/verify_remote_smoke_acceptance.py`. | Only local tests pass, remote model is unconfigured, real evidence ids are missing, or the offline verifier fails. |

## Remote Acceptance Minimum

The remote server is the authority for install, testing, running, and production acceptance. Local tests can prove code and contract intent, but they cannot prove deployment readiness.

The strict remote acceptance package must include:

- Deployed package identity or commit.
- `/health` returning `app=image_agent`.
- `/agent/model/status` with the OpenAI SDK gateway configured.
- `model_smoke_status=passed` from a live `/agent/runs` smoke.
- RAG document/chunk thresholds, semantic index, clean raw-source policy, complete curated provenance, safe vendor coverage catalog, and vendor pointer integrity.
- Real evidence ids with `remote_evidence_ids_status=passed`.
- Launchability matrix evidence from `/agent/rag/query` citation/source fields.
- `project_contract_status=passed`, `upload_inventory_contract_status=passed`, and `task_artifact_manifest_status=passed`.
- `container_native_qc_status=passed`, served container-native QC artifact URLs, accepted curated `official_source_ids`, and enough native QC images.
- `scientific_report_artifacts_status=passed`, served report HTML/PNG URLs, and derived-presentation provenance that does not replace native QC.
- Offline verifier output from `python scripts/verify_remote_smoke_acceptance.py <remote-smoke-acceptance.json>` with `status=passed`.

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

As of 2026-06-11, the first formal live-port strict remote acceptance evidence
has passed for committed release `7e7ff94` on the remote API surface at port
`8000`. The saved evidence cited in `docs/work-log-2026-06-10.md` includes real
project/upload/task ids, configured OpenAI-compatible Responses gateway smoke,
RAG provenance and launchability citation, safe artifact manifest,
container-native QC, derived scientific report provenance, route-served
artifacts, and an offline verifier result of `status=passed`.

The product is still in final operational hardening mode before frontend page
design is released. The remaining readiness condition is to make the accepted
release overlay the durable normal restart/service path, keep the dirty remote
main worktree out of the serving path, and refresh or explicitly preserve the
strict remote acceptance evidence after that operational path is used.
