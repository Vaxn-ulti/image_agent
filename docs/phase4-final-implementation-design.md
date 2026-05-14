# Phase 4 Final Implementation Design

## 1. Purpose
This document finalizes Phase 4 implementation scope after consolidating:
- `docs/phase4-plan-and-solve.md`
- `docs/phase4-gemini-review-1.md` through `docs/phase4-gemini-review-5.md`

Primary goal: deliver a deterministic mixed-ingest (DICOM/NIfTI) to BIDS MVP that is operationally reliable in local and remote backend deployment modes.

## 2. Consolidated Gemini Recommendations Summary
Gemini reviews repeatedly recommended:
1. Make ingest asynchronous to avoid timeout in large datasets.
2. Preserve deterministic inventory/status contracts and unsupported-sequence messaging.
3. Add BIDS uniqueness handling (`run-*` / `acq-*`) to avoid filename/path collisions.
4. Clarify metadata precedence for sequence/entity inference.
5. Strengthen DICOM grouping/validation rules.
6. Keep workflow scope limited to DeepPrep + QSI family for MVP.
7. Define deployment-mode UX clearly (local vs remote backend).
8. Expand tests for partial failures, status polling, gating, and mode parity.

## 3. Accepted vs Deferred Changes

### 3.1 Accepted for Phase 4 MVP
1. **Async-first ingest contract**: `POST .../ingest` returns quickly with status handle; inventory retrieved via status endpoints.
2. **Synchronous fast path (tiny archives only)**: allowed only when status endpoints exist and remain source of truth.
3. **BIDS uniqueness policy**: enforce `run-*` and `acq-*` labels when needed to prevent overwrite/collision.
4. **Metadata precedence**: `Sidecar JSON > DICOM tags > NIfTI header > filename tokens`.
5. **DICOM grouping hardening**: primary key `SeriesInstanceUID`, with guardrails across `PatientID` + `StudyInstanceUID` boundaries.
6. **Standard unsupported message**: exact backend string required:
   - `Current software does not support radiomics/processing for this sequence.`
7. **Deployment mode UI visibility**: explicit UI mode indicator and backend endpoint mode alignment.
8. **Test expansion**: include async lifecycle, tiny-sync behavior, collisions, partial conversion failures, workflow gating, local/remote parity.

### 3.2 Deferred (Post-MVP)
1. Manual relabel/correction UI for misclassified sequences.
2. Full resumable/chunked upload protocol standardization (beyond existing multipart baseline).
3. Built-in duplicate-upload deduplication by hash/Study UID.
4. Full BIDS-validator integration (keep lightweight internal path checks only in MVP).
5. Advanced progress metrics beyond coarse ingest/conversion counters.
6. Automatic cleanup/retention policy engine for uploads temp data.

## 4. Final MVP Implementation Scope

### 4.1 In Scope
1. Mixed DICOM/NIfTI ingest.
2. DICOM->NIfTI conversion (dcm2niix) and NIfTI direct normalization.
3. Deterministic inventory report with:
   - DICOM counts and conversion status.
   - Post-conversion counts by modality and sequence.
   - Recognized unsupported sequences with exact required message.
4. BIDS rawdata placement with unique naming safety.
5. Workflow run gating to MVP-supported workflows only.
6. Local vs remote backend runtime mode support with same API contracts.

### 4.2 Out of Scope
1. Statistical dashboards/visualizations.
2. Radiomics/processing for unsupported recognized sequences.
3. Additional workflow families beyond DeepPrep and QSI family.
4. DICOMweb/PACS integration.

## 5. Agent Model (<=7)
Execution ownership remains capped at 7 agents:
1. Architecture Agent
2. Backend API Agent
3. Imaging IO Agent
4. Workflow Runtime Agent
5. Frontend Agent
6. Chat Agent
7. QA/Release Agent

## 6. Final Contracts and Behavior

### 6.1 Ingest Async Design + Tiny Sync Fast Path
1. **Default**: asynchronous ingest for all normal/large uploads.
2. `POST /projects/{project_id}/datasets/{upload_session_id}/ingest`:
   - returns accepted/running state quickly.
   - includes identifiers for status polling.
3. Status endpoints are mandatory:
   - `GET /projects/{project_id}/datasets/{upload_session_id}/inventory`
   - returns lifecycle (`queued|running|completed|completed_with_partial_failures|failed`) and final summary.
4. **Tiny synchronous-fast path (MVP exception)**:
   - only for tiny test archives under configurable threshold.
   - may return completed summary inline.
   - still must persist inventory and expose same result via status endpoint.

### 6.2 BIDS Unique Naming Rules
1. Base entities: `sub-<id>` and modality suffix (`_T1w`, `_dwi`, `_bold`, etc.).
2. If multiple acquisitions map to same target entity, add `run-<n>`.
3. If acquisitions are semantically distinct (protocol/series distinction), add `acq-<label>`.
4. If both needed, use both: `sub-01_acq-highres_run-2_T1w.nii.gz`.
5. Never overwrite an existing BIDS artifact during ingest; collision must resolve by entity augmentation, not replacement.

### 6.3 Deployment Mode UI and Runtime
1. Runtime config: `BACKEND_RUNTIME_MODE=local|remote`.
2. UI must show active mode (`Local backend` or `Remote backend`).
3. API contracts are invariant across modes.
4. Local mode supports local-host optimized ingest behavior; remote mode uses network upload path.

## 7. Exact Implementation Slices

### 7.1 Backend Slice
1. Add/finalize upload session + ingest + inventory schemas and status vocab.
2. Persist session/inventory/findings metadata.
3. Implement async job orchestration and status transitions.
4. Support tiny-archive sync fast path behind config guard.
5. Enforce exact unsupported-sequence message from backend payload.

### 7.2 Frontend Slice
1. Add upload session + ingest trigger flow with status polling.
2. Render deterministic inventory summary cards/tables.
3. Show recognized-unsupported warnings with exact sentence.
4. Expose deployment mode indicator and backend endpoint context.
5. Enforce workflow selection guardrails from backend support flags.

### 7.3 Workflow Slice
1. Enforce run validation to MVP-supported workflows only:
   - `t1_deepprep` (+ validate)
   - `dwi_qsiprep` (+ validate)
   - `dwi_qsirecon` (+ validate)
   - `dwi_qsi_full` (+ validate)
2. Reject unsupported/unknown sequences deterministically.

### 7.4 Chat Slice
1. Update response templates to consume inventory payload fields.
2. Report supported recommendations from backend matrix only.
3. Return unsupported-sequence limitation text exactly as backend contract.

### 7.5 Test Slice
1. Unit:
   - DICOM detection/grouping guards.
   - Metadata precedence resolver.
   - BIDS entity naming with `run/acq` collision handling.
   - Unsupported warning formatter exact message.
2. Integration:
   - mixed ingest (DICOM+NIfTI) inventory determinism.
   - async ingest lifecycle and status polling.
   - tiny sync fast path parity with status endpoint output.
   - partial conversion -> `completed_with_partial_failures`.
   - run endpoint gating for unsupported/unknown sequences.
3. Smoke:
   - local mode E2E ingest->run validate.
   - remote mode E2E ingest->run validate.
   - mode parity for payload schema and workflow availability.

## 8. MVP Exit Criteria
Phase 4 is complete when:
1. Mixed uploads normalize to BIDS with deterministic inventory output.
2. Async ingest + status polling are production path; tiny sync path is limited and compliant.
3. BIDS collisions are resolved with `run/acq` labels without overwrite.
4. Unsupported recognized sequences are consistently surfaced with exact required message.
5. Only DeepPrep + QSI-family workflows are runnable.
6. Local and remote backend modes pass identical core smoke scenarios.
