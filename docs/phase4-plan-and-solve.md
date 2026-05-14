# Phase 4 Plan-and-Solve Architecture Plan

## 1) Plan-and-Solve Breakdown

### Problem statement
Phase 4 must make upload/inventory clinically broader and operationally deterministic:
- Accept mixed uploads containing DICOM or NIfTI.
- Normalize all supported imaging inputs into BIDS-managed project storage.
- Detect all recognizable sequences (not only T1/DWI/BOLD).
- Return deterministic inventory/conversion summaries before processing.
- Keep MVP processing limited to DeepPrep and QSI-family workflows.
- Support two backend deployment modes: local and remote runtime.

### Solve strategy (execution order)
1. Define data contracts first: upload session, inventory report, BIDS entities, sequence taxonomy.
2. Extend ingestion pipeline: filesystem scan, DICOM detection, NIfTI detection, sidecar pairing.
3. Implement conversion/normalization pipeline:
   - DICOM -> NIfTI (dcm2niix), then BIDS placement.
   - Native NIfTI -> BIDS placement directly.
4. Implement full-sequence identification layer with supported/unsupported flags and reasons.
5. Add upload result API payload with file counts, conversion status, and post-conversion counts by modality/sequence.
6. Gate workflow execution to MVP-supported pipelines only (DeepPrep + QSI family).
7. Add deployment abstraction for local vs remote backend runtime.
8. Validate with integration/smoke tests and explicit out-of-scope boundaries.

## 2) Agent Roles and Boundaries (<=7)

1. Architecture Agent
- Owns contracts, sequence taxonomy, storage model, and phase acceptance criteria.
- No app code edits outside architecture/planning docs.

2. Backend API Agent
- Owns FastAPI endpoints, request/response schemas, upload orchestration, task-trigger entrypoints.
- Must not implement sequence heuristics directly (delegates to imaging/workflow services).

3. Imaging IO Agent
- Owns ingest scanner, DICOM grouping, DICOM->NIfTI conversion adapter, NIfTI sidecar pairing, BIDS path materialization.
- Owns deterministic sequence classification outputs consumed by API.

4. Workflow Runtime Agent
- Owns workflow registry, support matrix enforcement, task dispatch.
- MVP scope: DeepPrep + QSI family only for real processing.

5. Frontend Agent
- Owns upload UX, inventory summary UI, unsupported-sequence warnings, workflow selection guardrails.
- No statistics dashboard in this phase.

6. Chat Agent
- Owns instruction parsing and response templates for inventory/conversion/task status.
- Must report unsupported recognized sequences with explicit limitation message.

7. QA/Release Agent
- Owns automated tests, smoke scripts, local/remote deployment checks.

## 3) System Boundaries (Frontend / Backend / Workflow / Chat)

### Frontend boundary
- Sends file/folder upload session requests.
- Displays upload report:
  - DICOM file count.
  - Conversion status.
  - Counts by modality and sequence after conversion.
  - Unsupported recognized sequence notices.
- Sends selected processing command only after inventory response.
- No statistical visualization implementation in Phase 4.

### Backend boundary
- Accepts upload session.
- Runs inventory + normalization pipeline.
- Persists BIDS-organized references and inventory metadata.
- Returns deterministic summary payload.
- Authorizes only supported workflows for execution.

### Workflow boundary
- Receives normalized BIDS input handles from backend.
- Executes only:
  - `t1_deepprep` (+ validate)
  - `dwi_qsiprep` (+ validate)
  - `dwi_qsirecon` (+ validate)
  - `dwi_qsi_full` (+ validate)
- Unsupported recognized sequences are not dispatched.

### Chat boundary
- Converts user text instruction into:
  - inventory explanation,
  - supported workflow recommendation,
  - unsupported-sequence limitation statement.
- Never bypasses backend support matrix.

## 4) API Design: Dataset/Folder Upload and Inventory

## 4.1 Endpoints

### `POST /projects/{project_id}/datasets/upload-session`
Create upload session metadata.

Request (JSON):
```json
{
  "source_type": "folder_or_archive",
  "label": "subject_batch_2026_05_13"
}
```

Response:
```json
{
  "upload_session_id": 101,
  "project_id": 7,
  "status": "ready"
}
```

### `POST /projects/{project_id}/datasets/{upload_session_id}/ingest`
Multipart upload (archive or file batch). Triggers inventory + normalization.

Response (synchronous summary, asynchronous internals allowed):
```json
{
  "upload_session_id": 101,
  "inventory_status": "completed",
  "dicom": {
    "found_files": 1842,
    "conversion_status": "completed_with_partial_failures",
    "converted_series": 9,
    "failed_series": 1
  },
  "post_conversion_counts": {
    "by_modality": {"T1": 1, "T2": 1, "DWI": 2, "BOLD": 1, "FLAIR": 1},
    "by_sequence": {
      "T1w_MPRAGE": 1,
      "T2w_SPACE": 1,
      "DWI_shell_1000": 1,
      "DWI_shell_2000": 1,
      "rsfMRI_BOLD": 1,
      "T2_FLAIR": 1
    }
  },
  "recognized_unsupported_sequences": [
    {
      "sequence": "T2_FLAIR",
      "count": 1,
      "message": "Current software does not support radiomics/processing for this sequence."
    }
  ],
  "bids_dataset_root": "data/projects/7/bids/rawdata",
  "series": [
    {
      "series_id": 501,
      "source_format": "DICOM",
      "normalized_format": "NIFTI",
      "bids_path": "sub-01/anat/sub-01_T1w.nii.gz",
      "modality": "T1",
      "sequence_label": "T1w_MPRAGE",
      "supported_for_processing": true
    }
  ]
}
```

### `GET /projects/{project_id}/datasets/{upload_session_id}/inventory`
Returns latest inventory + normalization report (idempotent polling endpoint).

### `POST /series/{series_id}/run`
Reuse existing run endpoint; enforce that series is BIDS-normalized and supported.

## 4.2 Error contract
- `400`: malformed upload or unsupported container format.
- `409`: ingest already running for this session.
- `422`: no recognizable imaging content.
- `500`: internal conversion failure (include per-series failure details in payload).

## 5) BIDS Storage Design

Target project tree:
```text
data/projects/{project_id}/
  uploads/
    {upload_session_id}/
      originals/                  # untouched user payload
      extracted/                  # extracted archives
  bids/
    rawdata/
      dataset_description.json
      participants.tsv
      sub-{subject}/
        anat/
        dwi/
        func/
        fmap/                     # reserved for future
        perf/                     # reserved for future
  inventory/
    {upload_session_id}.json
  derivatives/
    {task_id}/ ...                # existing workflow outputs
```

Rules:
- Always keep original uploaded bytes.
- BIDS `rawdata` contains normalized NIfTI(+sidecars) references or copies.
- In Phase 4, either symlink or copy is acceptable; behavior must be globally configurable.
- `dataset_description.json` required at first successful normalization.

## 6) DICOM Conversion Behavior

1. Detect DICOM files by preamble/tag heuristics and extension-agnostic binary probe.
2. Group into candidate series using DICOM tags (`SeriesInstanceUID`, fallback rules when missing).
3. For each grouped series:
- Run `dcm2niix` with deterministic naming.
- Capture converter stdout/stderr and return per-series status.
- Produce NIfTI + sidecars (.json, .bval/.bvec when diffusion).
4. Move/link converted outputs into BIDS `rawdata` paths based on classified sequence.
5. Persist conversion manifest with:
- input file count,
- output artifact list,
- conversion warnings/errors.

Status vocabulary:
- `not_applicable` (no DICOM found)
- `completed`
- `completed_with_partial_failures`
- `failed`

## 7) NIfTI-to-BIDS Behavior

1. Detect `.nii` / `.nii.gz` and associate sidecars (`.json`, `.bval`, `.bvec`).
2. Classify sequence/modality from header + filename + sidecar metadata.
3. Place into canonical BIDS path:
- T1-like -> `anat/sub-XX_T1w.nii.gz`
- T2-like -> `anat/sub-XX_T2w.nii.gz`
- DWI-like -> `dwi/sub-XX_dwi.nii.gz` + sidecars
- BOLD-like -> `func/sub-XX_task-rest_bold.nii.gz` (task naming heuristic; default `rest`)
- others recognized -> best-fit BIDS folder when defined; else mark recognized-unsupported.
4. Record normalized mapping from upload source to BIDS path.

## 8) Full Sequence Identification Behavior

## 8.1 Recognition goal
Identify all recognizable sequences encountered, not only T1/DWI/BOLD.

## 8.2 Phase 4 sequence taxonomy
Supported for processing:
- `T1w_MPRAGE` -> DeepPrep
- `DWI_multi_shell` / `DWI_single_shell` -> QSIPrep/QSIRecon
- `rsfMRI_BOLD` / `task_fMRI_BOLD` -> inventory recognized; processing optional only if workflow already available

Recognized but unsupported for processing/radiomics in Phase 4:
- `T2w`, `T2_FLAIR`, `SWI`, `ASL`, `PD`, `MRA`, `DTI_ADC_MAP`, `fieldmap` family, `localizer/scout`

For every recognized unsupported sequence, backend must return:
- sequence label,
- count,
- exact message: `Current software does not support radiomics/processing for this sequence.`

Unrecognized content:
- Keep as `unknown` with reason and confidence.
- Exclude from workflow dispatch.

## 9) Deployment Mode Design: Local vs Remote Backend

## 9.1 Shared abstraction
Add runtime mode config key:
- `BACKEND_RUNTIME_MODE=local|remote`

Behavior split:
- `local`: desktop and API run on same host; filesystem paths are direct.
- `remote`: desktop calls remote API; backend owns storage and container runtime.

## 9.2 Local mode
- Quick-start single-machine install.
- Direct folder upload possible.
- Requires local `dcm2niix` and container runtime availability.

## 9.3 Remote mode
- Thin client desktop.
- Upload via HTTP multipart/chunking.
- Server-side conversion + BIDS normalization.
- Returns same API contracts as local mode.

## 9.4 Contract invariants
Regardless of mode:
- same endpoints,
- same inventory payload schema,
- same workflow support matrix,
- same status vocabulary.

## 10) MVP Acceptance Criteria (Minimal)

1. Upload containing DICOM files returns DICOM file count and conversion status.
2. Upload containing NIfTI files is normalized into BIDS rawdata.
3. Inventory response includes post-conversion counts by modality and by sequence.
4. Recognized unsupported sequences are listed with required limitation message.
5. User can trigger only DeepPrep and QSI-family workflows from normalized series.
6. Local and remote deployment modes both pass same ingestion + run smoke tests.
7. No statistical visualization is required for phase completion.

## 11) Tests and Smoke Tests

## 11.1 Backend tests
- Unit: DICOM detector, series grouper, sequence classifier, BIDS path resolver.
- Unit: unsupported-sequence response formatter message correctness.
- Integration: ingest mixed upload (DICOM + NIfTI), assert summary payload fields and counts.
- Integration: DICOM partial conversion failures produce `completed_with_partial_failures`.
- Integration: run endpoint rejects unsupported sequences.

## 11.2 Frontend smoke
- Upload dataset/folder shows inventory summary cards.
- Unsupported recognized sequence warning renders exact required sentence.
- Workflow selection list only shows runnable options per series.

## 11.3 Deployment smoke
- Local mode: end-to-end ingest -> run `t1_deepprep_validate` and `dwi_qsiprep_validate`.
- Remote mode: same scenario against remote API base URL.

## 12) Out of Scope (Phase 4)

- Statistical visualization/dashboard implementation.
- Full radiomics feature extraction for unsupported sequences.
- Advanced BIDS Apps beyond DeepPrep and QSI-family.
- Multi-site federated storage orchestration.
- Clinical reporting generation.
- DICOMweb PACS ingestion.

## 13) Execution Plan (Implementation Slices)

1. Contract slice
- Add upload-session and inventory API schemas.
- Add DB tables for `upload_sessions`, `inventory_reports`, `sequence_findings`.

2. Ingestion slice
- Implement mixed-content scanner and file manifest builder.
- Implement DICOM grouping and NIfTI sidecar matcher.

3. Normalization slice
- Implement DICOM->NIfTI conversion orchestration.
- Implement NIfTI->BIDS placement and manifest persistence.

4. Classification slice
- Extend sequence taxonomy and supported/unsupported decision engine.

5. Workflow gating slice
- Enforce MVP support matrix (DeepPrep + QSI family only) at run validation.

6. UX/chat slice
- Surface inventory summary + unsupported warnings.
- Update chat templates to reflect new inventory report fields.

7. QA slice
- Add automated tests and two-mode smoke checklist.

