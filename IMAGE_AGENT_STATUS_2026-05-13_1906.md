# Image Agent Project Status

Log time: 2026-05-13 19:06:24 CST

Project path: `/home/yyf/project/image_agent`

## 1. Current Goal

The project is building a neuroimaging GUI agent application. The intended user flow is:

1. User opens a GUI page.
2. User uploads a DICOM/NIfTI dataset or a mixed imaging folder packaged as a zip file.
3. Backend identifies all recognizable imaging sequences.
4. DICOM data is converted to NIfTI where possible.
5. DICOM and NIfTI data are normalized into a BIDS-like dataset layout.
6. The user receives an inventory summary showing file counts, DICOM count, conversion status, modality counts, sequence counts, and unsupported recognized sequences.
7. The user can ask the built-in agent questions.
8. The user can launch supported remote container workflows:
   - T1: DeepPrep
   - DWI: QSIPrep
   - DWI: QSIRecon
   - DWI: QSIPrep + QSIRecon chained workflow

The current implementation target is a lowest usable MVP, not a full clinical-grade analysis platform yet.

## 2. Deployment State

Current selected architecture: desktop/web GUI + remote compute backend.

The app is running on the remote server and exposed locally through SSH tunnel:

- Frontend: `http://127.0.0.1:5173`
- Backend health: `http://127.0.0.1:8000/health`
- Backend deployment metadata: `http://127.0.0.1:8000/deployment`
- Runtime container check: `http://127.0.0.1:8000/runtime/containers`

Remote services:

- Backend: FastAPI / Uvicorn on remote port `8000`
- Frontend: Vite React dev server on remote port `5173`
- Local access depends on SSH port forwarding from local `127.0.0.1:8000` and `127.0.0.1:5173` to remote.

Current backend deployment response:

```json
{
  "backend_runtime_mode": "remote",
  "api_base_hint": "",
  "agent": {
    "provider": "deepseek",
    "configured": true,
    "base_url": "https://api.deepseek.com",
    "model": "deepseek-v4-flash",
    "proxy_mode": "direct"
  }
}
```

## 3. Backend Implementation

Backend path:

`/home/yyf/project/image_agent/apps/api`

Main files:

- `app/main.py`
- `app/core/config.py`
- `app/db/schema.sql`
- `app/db/database.py`
- `app/imaging/detect.py`
- `app/imaging/ingest.py`
- `app/workflows/pipeline.py`
- `app/workflows/deepprep.py`
- `app/agent/deepseek.py`

Implemented backend capabilities:

1. Project management
   - Create project
   - List projects
   - Project-scoped data storage under `data/projects/{project_id}`

2. Basic upload endpoints
   - Single NIfTI upload
   - DWI upload with NIfTI + bval + bvec
   - DICOM zip upload
   - Mixed dataset zip upload through upload sessions

3. Mixed dataset ingest
   - Endpoint: `POST /projects/{project_id}/datasets/upload-session`
   - Endpoint: `POST /projects/{project_id}/datasets/{upload_session_id}/ingest`
   - Endpoint: `GET /projects/{project_id}/datasets/{upload_session_id}/inventory`
   - Zip extraction includes unsafe path protection.
   - DICOM files are counted.
   - DICOM conversion is attempted with `dcm2niix`.
   - NIfTI files are copied/linked into BIDS-like layout.
   - Inventory JSON is stored in database and under project data.

4. Imaging sequence detection
   - Detects T1, DWI, BOLD/fMRI and additional recognizable sequences.
   - Recognized unsupported examples include FLAIR and other non-MVP sequences.
   - Unsupported recognized sequences are not hidden; they are reported with:
     `Current software does not support radiomics/processing for this sequence.`

5. BIDS-like storage
   - DICOM-converted and uploaded NIfTI data are normalized under:
     `data/projects/{project_id}/bids/rawdata`
   - `dataset_description.json` is generated.
   - DWI sidecars `.bval` and `.bvec` are preserved when present.
   - Duplicate names are handled with unique BIDS path logic.

6. Task system
   - Tasks stored in SQLite.
   - Task logs stored under project logs.
   - Outputs registered in `outputs` table.
   - Task polling endpoint is available.

7. Workflow runtime
   - Real container workflow runner exists in `app/workflows/pipeline.py`.
   - Supported workflow types currently exposed:
     - `t1_deepprep`
     - `t1_deepprep_validate`
     - `dwi_qsiprep`
     - `dwi_qsiprep_validate`
     - `dwi_qsirecon`
     - `dwi_qsirecon_validate`
     - `dwi_qsi_full`
     - `dwi_qsi_full_validate`
     - `t1_deepprep_mock`
   - Validate workflows check command construction and Docker image availability without running full long jobs.

8. Runtime container inspection
   - Endpoint: `GET /runtime/containers`
   - Reports:
     - whether Docker is accessed via sudo
     - FreeSurfer license path
     - whether FreeSurfer license exists
     - availability of DeepPrep/QSIPrep/QSIRecon images

## 4. Remote Container State

Confirmed available on the remote server:

- `pbfslab/deepprep:25.1.0`
- `pennlinc/qsiprep:latest`
- `pennlinc/qsirecon:latest`

Other images visible on the server include fMRIPrep, MRIQC, FastSurfer, DPABI, RStudio and CUDA images, but the MVP currently focuses on DeepPrep and QSI-family workflows.

Docker requires sudo access. Backend uses:

- `IMAGE_AGENT_SUDO_PASSWORD`
- `IMAGE_AGENT_FS_LICENSE`

These are loaded from:

`/home/yyf/project/image_agent/.env`

The `.env` file has permission `600`.

## 5. DeepSeek Built-in Agent

Implemented file:

`/home/yyf/project/image_agent/apps/api/app/agent/deepseek.py`

Current behavior:

- The backend `/chat` endpoint first attempts DeepSeek.
- If DeepSeek fails or is not configured, it falls back to rule-based replies.
- Response includes:
  - `provider`
  - `provider_error`
  - `reply`
  - `references`

DeepSeek config:

- Base URL: `https://api.deepseek.com`
- Endpoint: `/chat/completions`
- Model: `deepseek-v4-flash`
- Proxy mode: `direct`

Important recent change:

DeepSeek is now forced to use direct connection. The client disables proxy use with two safeguards:

1. `urllib.request.ProxyHandler({})`
2. Temporarily removes `HTTP_PROXY`, `HTTPS_PROXY`, `ALL_PROXY`, `NO_PROXY` and lowercase equivalents only during the DeepSeek request, then restores them.

Latest interactive test result:

- `/chat` returned `provider: deepseek`
- `provider_error` was empty
- DeepSeek successfully produced a response

This means the built-in agent is currently interactive through the backend.

## 6. Frontend Implementation

Frontend path:

`/home/yyf/project/image_agent/apps/desktop`

Main files:

- `src/main.jsx`
- `src/lib/api.js`
- `src/styles.css`

Implemented frontend features:

1. Login screen
   - MVP login creates or returns user locally.

2. Project panel
   - Create project
   - Select project
   - Refresh project data

3. Upload panels
   - Upload T1/BOLD NIfTI
   - Upload DICOM zip
   - Upload mixed dataset zip
   - Upload DWI set with NIfTI + bval + bvec

4. Dataset inventory panel
   - Total files
   - DICOM file count
   - DICOM conversion status
   - BIDS root
   - Modalities
   - Sequences
   - Recognized but unsupported sequences

5. Remote runtime panel
   - Shows agent provider/model/config state.
   - Shows DeepSeek direct/fallback state via deployment metadata.
   - Shows FreeSurfer license availability.
   - Shows DeepPrep/QSIPrep/QSIRecon image availability.

6. Series table
   - Lists uploaded/detected series.
   - Shows modality, format, confidence, shape, DWI sidecar status, DICOM count when relevant.
   - Shows workflow buttons only for supported MVP modalities.

7. Task panel
   - Shows task id, workflow type, status, progress.
   - Allows log viewing.
   - Allows output listing.

8. Agent chat panel
   - Sends messages to `/chat`.
   - Shows reply.
   - Shows provider label when available.

## 7. Database State

SQLite schema includes:

- `users`
- `projects`
- `files`
- `imaging_series`
- `upload_sessions`
- `sequence_findings`
- `tasks`
- `outputs`
- `chat_messages`

Important columns added to `imaging_series`:

- `upload_session_id`
- `bids_path`
- `sequence_label`
- `supported_for_processing`
- `unsupported_reason`

Task table includes:

- `qsiprep_task_id`

This supports QSIRecon depending on a previous QSIPrep task.

## 8. Verification Completed

Latest backend test command:

```bash
cd /home/yyf/project/image_agent/apps/api
. .venv/bin/activate
pytest -q
```

Latest result:

```text
4 passed, 2 warnings
```

Warnings are FastAPI `on_event` deprecation warnings only.

Latest frontend build command:

```bash
cd /home/yyf/project/image_agent/apps/desktop
npm run build
```

Latest result:

```text
vite build completed successfully
```

Container smoke test:

- A temporary synthetic T1 NIfTI was created.
- It was uploaded through the backend.
- `t1_deepprep_validate` was launched.
- Task completed successfully:

```json
{
  "status": "completed",
  "progress": 100,
  "error": null
}
```

This validates that the backend can reach the DeepPrep Docker image and complete the validate-mode execution path.

DeepSeek chat smoke test:

- Request sent to `/chat`.
- Response returned from `provider: deepseek`.
- `provider_error` was empty.

This validates that the built-in agent can currently interact.

## 9. Known Limitations

1. Clinical processing validation is not complete.
   - Validate-mode confirms command/image availability.
   - Full DeepPrep/QSIPrep/QSIRecon processing on real clinical datasets still needs real sample data and long-running verification.

2. BIDS support is pragmatic MVP-level.
   - It creates a BIDS-like layout.
   - It does not yet run full `bids-validator`.
   - It does not yet expose manual correction for incorrectly inferred sequence labels.

3. DICOM conversion uses `dcm2niix`.
   - DICOM file counting and conversion attempt are implemented.
   - Real-world multi-series DICOM grouping should be tested with actual scanner exports.

4. BOLD processing is not the active MVP path.
   - BOLD/fMRI can be recognized and inventoried.
   - The current MVP workflow focus is DeepPrep for T1 and QSIPrep/QSIRecon for DWI.
   - ALFF/fALFF remains a later phase.

5. DeepSeek model name may need adjustment later.
   - Current config uses `deepseek-v4-flash`.
   - If the API later rejects this model, update `/home/yyf/project/image_agent/.env` key `DEEPSEEK_MODEL`.
   - No code change is required for model name changes.

6. Long-running tasks need better UX.
   - Current frontend polls task list.
   - It does not yet have detailed step-level progress for long jobs.
   - It does not yet support cancel/retry controls.

7. Security is MVP-level.
   - Login is placeholder.
   - Secrets are stored in `.env` with restricted permissions.
   - Production deployment should move secrets to a proper secret manager.

## 10. Important Files For Handoff

Planning and review documents:

- `/home/yyf/project/image_agent/docs/phase4-plan-and-solve.md`
- `/home/yyf/project/image_agent/docs/phase4-gemini-review-1.md`
- `/home/yyf/project/image_agent/docs/phase4-gemini-review-2.md`
- `/home/yyf/project/image_agent/docs/phase4-gemini-review-3.md`
- `/home/yyf/project/image_agent/docs/phase4-gemini-review-4.md`
- `/home/yyf/project/image_agent/docs/phase4-gemini-review-5.md`
- `/home/yyf/project/image_agent/docs/phase4-final-implementation-design.md`

Core backend:

- `/home/yyf/project/image_agent/apps/api/app/main.py`
- `/home/yyf/project/image_agent/apps/api/app/imaging/ingest.py`
- `/home/yyf/project/image_agent/apps/api/app/imaging/detect.py`
- `/home/yyf/project/image_agent/apps/api/app/workflows/pipeline.py`
- `/home/yyf/project/image_agent/apps/api/app/agent/deepseek.py`

Core frontend:

- `/home/yyf/project/image_agent/apps/desktop/src/main.jsx`
- `/home/yyf/project/image_agent/apps/desktop/src/lib/api.js`
- `/home/yyf/project/image_agent/apps/desktop/src/styles.css`

Tests:

- `/home/yyf/project/image_agent/apps/api/tests/test_api_flow.py`

Runtime config:

- `/home/yyf/project/image_agent/.env`

Logs:

- `/home/yyf/project/image_agent/logs/api.log`
- `/home/yyf/project/image_agent/logs/desktop.log`

## 11. Recommended Next Steps

Priority 1: Real sample data tests

- Test one real T1 dataset with `t1_deepprep_validate`.
- Then run full `t1_deepprep` on a small real case.
- Confirm outputs are registered and visible in frontend.

Priority 2: DWI workflow validation

- Upload real DWI NIfTI + `.bval` + `.bvec`.
- Run `dwi_qsiprep_validate`.
- Run full `dwi_qsiprep`.
- Run `dwi_qsirecon_validate` using the completed QSIPrep task id.
- Run full `dwi_qsirecon`.

Priority 3: Mixed DICOM dataset test

- Upload a real scanner-export zip containing multiple sequences.
- Confirm all recognizable sequences are listed.
- Confirm unsupported sequences are clearly marked.
- Confirm converted NIfTI data is stored under BIDS-like paths.

Priority 4: Improve task orchestration

- Add cancel/retry.
- Add queue state and worker process isolation.
- Add per-step progress parsing from Docker logs.

Priority 5: Improve BIDS correctness

- Add optional `bids-validator`.
- Add manual sequence relabel/correction UI.
- Add subject/session inference from DICOM metadata.

Priority 6: Expand BOLD/fMRI

- Re-enable or implement DeepPrep BOLD preprocessing path after T1/DWI are stable.
- Add ALFF/fALFF computation once preprocessing outputs are verified.

## 12. Current Status Summary

The software is currently a working MVP for remote-server operation:

- GUI loads locally through SSH tunnel.
- Backend is running remotely.
- Mixed upload and inventory generation are implemented.
- BIDS-like normalization is implemented.
- DeepPrep/QSIPrep/QSIRecon containers are detected on the remote server.
- DeepPrep validate path has been smoke-tested successfully.
- DeepSeek built-in agent is connected and interactive.
- Tests and frontend build pass.

The next major milestone is full processing validation on real imaging data rather than synthetic smoke data.
