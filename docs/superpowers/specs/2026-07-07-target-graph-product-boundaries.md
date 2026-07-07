# Target Graph Product Boundaries And Engineering Decisions

## Purpose

This document turns the target graph in `docs/image_agent_production_implementation_spec.md` into product boundaries and engineering decisions. It answers the implementation questions behind section 9 at decision level, so future BMAD checkpoints can build toward the full graph rather than adding isolated features.

Primary target graph source:

- `docs/image_agent_production_implementation_spec.md`, section 8, "LangGraph Target Graph".
- Engineering question source: section 9, "100 个落地问题清单".

## Product Boundary

Image Agent is a research neuroimaging workflow control plane for local or private-network deployment. It is not a clinical diagnosis product, not a general remote-code execution assistant, and not a free-form workflow executor.

The product must:

- accept DICOM, NIfTI, and BIDS-oriented neuroimaging inputs;
- explain data, eligibility, workflow boundaries, and results without diagnosis;
- recommend and launch fixed mature workflows only through registry, preflight, policy gate, and human authorization;
- keep exploratory or unregistered toolchains in sandbox/incubation until promoted;
- execute containers through an auditable execution control plane;
- preserve provenance for decisions, inputs, containers, outputs, artifacts, and retries;
- use official-source RAG and registry facts as grounding, not as execution authority.

## Deployment Decisions

Recommended product target:

- primary: single lab workstation or private lab server;
- secondary: private-network departmental server;
- deferred: public internet multi-tenant SaaS.

Deployment boundaries:

- public internet readiness is not required for the next production milestone;
- private HTTP(S) and loopback API/console origins are acceptable only when `IMAGE_AGENT_DEPLOYMENT_SCOPE=private_network`;
- production evidence must still prove model gateway, Elasticsearch hybrid RAG, Docker access, workflow execution, artifact manifest, native QC, report provenance, and verifier pass.

Offline mode:

- fully offline operation is a deployment profile, not the baseline;
- online model/RAG provider settings must be explicit and privacy-safe;
- offline mode later requires local model, local embedding provider, locally mirrored docs, and offline container image/digest management.

## Data And Privacy Decisions

Input support:

- DICOM, NIfTI, and BIDS are first-class inputs;
- NRRD/MHA/PET/QSM/ASL/MRA/CTA are registry-driven extensions, not core hard-coded paths.

PHI/PII:

- assume uploaded imaging metadata may contain sensitive identifiers;
- do not serialize raw paths, patient identifiers, server secrets, API keys, or full DICOM metadata into public API responses, graph state, logs, or RAG answers;
- anonymization is required before production workflow execution when DICOM metadata is in scope;
- PHI audit export is deferred but the event model must preserve enough safe evidence to add it.

Project isolation:

- minimum: `project_id` database boundary plus per-project storage roots;
- production target: database project id, per-project filesystem roots, and container mount isolation;
- task containers never receive Docker socket mounts.

## Intent And LangGraph Decisions

The graph must evolve from the current front-half skeleton to the full target graph in bounded slices.

Already implemented:

- `run_intake`;
- `safety_risk_router`;
- production intent stages: `rule_intent_classifier`, `llm_intent_planner`, `intent_fusion_gate`;
- coarse answer/task routing;
- RAG retrieval and skill selection;
- coarse lanes: read-only, fixed workflow, incubation, observe/repair.

Next graph nodes to implement:

1. `requirement_completeness`
2. `clarification_interrupt`
3. `neuroimaging_data_intake_validation`
4. `sequence_metadata_normalization`
5. `preflight_lite`
6. `open_neuroimaging_task_router`
7. `capability_matcher`
8. `fixed_workflow_recommendation`
9. `execution_plan_candidate`
10. `plan_policy_gate`
11. `authorization_verification`
12. `execution_control_plane`

Intent taxonomy:

- Answer categories should be fixed for now: inventory/capability, status, result analysis, RAG explanation, general read-only answer.
- Tool-task categories should be fixed for now: fixed workflow launch, workflow recommendation, incubation proposal, observe/repair, sandbox validation, execution retry/replan.
- All model classification must include confidence, evidence spans, risk level, ambiguities, and route recommendation.

Clinical boundary:

- outputs must not provide diagnosis, prognosis, treatment recommendation, or patient-specific clinical interpretation;
- result analysis may describe workflow artifacts, QC status, processing failures, and research-oriented measurements.

Authorization:

- long-running workflows, production task creation, retry with changed inputs/resources, deletion, overwrite, export of sensitive bundles, and cross-project copy require human authorization;
- authorization TTL should be task-bound for v1, not session-global.

## RAG, Registry, And KG Decisions

RAG source policy:

- official vendor/container docs, local curated contracts, and reviewed internal runbooks are accepted;
- raw scraped pages are not directly citable unless curated into safe Markdown under `docs/rag/` or `docs/skills/`;
- GitHub issues/forums can enter troubleshooting only after review and source labeling.

Registry-first policy:

- LLM cannot invent production workflows;
- every production workflow requires a registry entry, maturity level, supported sequence scope, fixed container image, expected inputs/outputs, QC artifacts, and citations;
- unknown workflow requests route to incubation/sandbox.

Elasticsearch hybrid:

- production RAG uses Elasticsearch hybrid retrieval with BM25, dense-vector kNN, metadata filters, and RRF;
- local fallback retrieval is development evidence only, not strict production acceptance;
- production evidence must include configured non-local embedding provider, positive indexed chunks, matching vector dimensions/model, connected query mode, and safe citations.

KG direction:

- property graph is planned after registry schema stabilizes;
- initial entities: Software, SoftwareVersion, ContainerImage, Command, Parameter, InputArtifact, OutputArtifact, Workflow, WorkflowStep, QCRule, ErrorSignature, Fix, Citation, License, SequenceFamily.

## Neuroimaging Workflow Decisions

Sequence handling:

- core should not hard-code all sequence support;
- sequence/task routing must consume registry, BIDS metadata, file inventory, workflow contracts, and capability metadata;
- unsupported recognized sequences must receive deterministic limitation messages rather than fake processing paths.

Metadata precedence:

1. sidecar JSON;
2. DICOM tags;
3. NIfTI header;
4. filename tokens.

DICOM grouping:

- primary grouping key is `SeriesInstanceUID`;
- guard against cross-patient and cross-study mixing with `PatientID` and `StudyInstanceUID` boundaries;
- conversion provenance must record source series ids and generated BIDS entities.

BIDS:

- BIDS rawdata placement should use deterministic unique naming;
- collisions resolve with `run-*` and `acq-*`, never overwrite;
- BIDS Validator integration is required for production but lightweight internal path checks can precede it.

Workflow coverage:

- fixed mature v1 workflows should prioritize T1 anatomical, BOLD/fMRIPrep-XCPD, DWI fast GPU DTI, and carefully selected validation profiles;
- QSIPrep/QSIRecon full routes remain legacy/advanced/incubation unless explicitly promoted.

QC:

- UI and result APIs must prefer container-native QC artifacts;
- derived scientific report figures can supplement but must not masquerade as official native QC;
- QC thresholds are workflow defaults first, then project template overrides, then manual review.

## Execution System Decisions

Execution plan:

- `ExecutionPlan` and `ApprovedExecutionPlan` must be versioned;
- plan hash must include workflow id, container digest, inputs, normalized parameters, policy version, and authorization scope;
- dynamic DAG expansion is deferred until static plan execution is reliable.

State machine:

- business execution state belongs in the database, not in Celery delivery state;
- required entities: `execution_runs`, `execution_attempts`, `execution_events`;
- every retry creates a new attempt.

Queues:

- minimum queues: `image_agent_cpu`, `image_agent_gpu`, `image_agent_sandbox`, `image_agent_long`;
- IO-heavy tasks may later get `image_agent_io`;
- GPU resource expression must include GPU kind/class, VRAM, CUDA compatibility, and optional MIG profile when available.

Lease and heartbeat:

- worker lease and heartbeat are mandatory;
- recommended first defaults: heartbeat every 30 seconds, stale lease after 3 missed heartbeats, task-specific timeout ceilings;
- stale/timeout/cancel flows go through reaper/cleanup and write execution events.

Container policy:

- default network disabled;
- read-only input mounts;
- isolated output/workdir;
- drop capabilities and use no-new-privileges where runtime supports it;
- no Docker socket mount;
- image allowlist and digest pinning required for production;
- secrets never appear in command logs.

Retry policy:

- automatic retry is limited to known transient infrastructure errors;
- same error signature repeated twice stops automatic retry;
- one-click retry is allowed only for mature fixed workflows and unchanged authorization scope;
- any changed data, container, network, resource, or permission scope requires new authorization.

Artifact policy:

- artifact manifest is the frontend and API source of truth;
- production artifacts should have hashes and provenance;
- manifest signing is deferred but schema should leave room for signatures.

SQLite boundary:

- SQLite is development/local-only for production-control-plane features;
- PostgreSQL or equivalent production DB is required for multi-worker execution state, durable leases, and reconciliation.

## Target Graph Gap Map

| Target Graph Area | Current State | Decision | Next Slice |
| --- | --- | --- | --- |
| Intake/checkpoint/safety | Partial | Keep deterministic and audit-safe | Add checkpoint state object |
| Intent answer/task routing | Production first slice | Keep rule + LLM + fusion | Add taxonomy eval set |
| Requirement completeness | Missing | Must block ambiguous tool tasks | Implement before neuroimaging router |
| Clarification interrupt | Missing | Required before any uncertain execution | Add resumable checkpoint |
| Neuroimaging intake/normalization | Partial outside graph | Must become graph nodes | Wrap inventory/BIDS rules |
| Capability matcher/registry | Partial | Registry is source of truth | Add matcher node and tests |
| Fixed workflow plan builder | Coarse confirmation path | Must emit ExecutionPlan candidate | Implement plan schema adapter |
| Exploratory tool path | Incubation proposal exists | Needs official source and verifier gates | Add trust/verifier nodes |
| Plan policy gate | Partial contracts | Must be central gate before auth | Implement policy snapshot |
| Authorization | Confirmation exists | Must become scoped auth node | Add task-bound TTL and scope |
| Execution control plane | Partial services | Must use DB run/attempt state | Extend execution service |
| Worker/reaper/QC | Partial | Must be event/provenance driven | Implement after plan/auth |

## Recommended Implementation Order

1. Requirement completeness and clarification interrupt.
2. Neuroimaging data intake validation and sequence metadata normalization.
3. Capability matcher and registry-backed fixed workflow recommendation.
4. ExecutionPlan candidate and plan policy gate.
5. Authorization verification with task-bound scope.
6. Execution control plane DB state and scheduler admission.
7. Worker lease, heartbeat, reaper, and DLQ.
8. Artifact manifest/result summary/QC gate integration.
9. Observe/repair retry/replan loop.
10. Evaluation logger and benchmark suite.

## Acceptance Gate For Next Code Slice

The next code slice should be accepted only when:

- new graph nodes are visible in compiled and fallback graph tests;
- each node writes safe graph state and events;
- ambiguous tool-task requests stop at clarification;
- no production task is created before policy and authorization gates;
- target graph gap map and BMAD log are updated with evidence;
- focused tests and `git diff --check` pass.
