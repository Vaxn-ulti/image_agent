# Phase 2 API Contract

Base URL: `http://<server>:8000`. All Phase 1 endpoints remain unchanged. Phase 2 adds new upload endpoints and extends the run endpoint.

## New: Multi-file Upload for DWI

`POST /projects/{project_id}/upload-dwi`

Request: multipart form with up to 3 files:
- `nifti` (required): DWI .nii or .nii.gz
- `bval` (required): .bval sidecar
- `bvec` (required): .bvec sidecar

All files are stored in `raw/` under their original names. Detection uses the NIfTI header + bval/bvec presence to set `modality=DWI`, `confidence=0.95`.

Response:
```json
{
  "files": [
    { "id": 1, "original_name": "dwi.nii.gz", "storage_path": "...", "file_type": "NIFTI", "size": 0, "sha256": "abc", "created_at": "..." },
    { "id": 2, "original_name": "dwi.bval", "storage_path": "...", "file_type": "BVAL", "size": 0, "sha256": "def", "created_at": "..." },
    { "id": 3, "original_name": "dwi.bvec", "storage_path": "...", "file_type": "BVEC", "size": 0, "sha256": "ghi", "created_at": "..." }
  ],
  "series": {
    "id": 1, "project_id": 1, "file_id": 1,
    "modality": "DWI", "format": "NIFTI", "confidence": 0.95,
    "metadata": { "shape": [128,128,60,32], "has_bval": true, "has_bvec": true, "bval_file_id": 2, "bvec_file_id": 3 },
    "status": "detected", "created_at": "..."
  }
}
```

`metadata.bval_file_id` and `metadata.bvec_file_id` reference the sidecar `files` rows so workflows can locate them.

## Extended: Run Endpoint

`POST /series/{series_id}/run`

Request:
```json
{
  "workflow_type": "t1_deepprep" | "dwi_qsiprep" | "dwi_qsirecon" | "dwi_qsi_full"
                 | "t1_deepprep_validate" | "dwi_qsiprep_validate" | "dwi_qsirecon_validate" | "dwi_qsi_full_validate",
  "qsiprep_task_id": null
}
```

`qsiprep_task_id` is required when `workflow_type` is `dwi_qsirecon` or `dwi_qsirecon_validate`. It specifies which QSIPrep task's output to use as input.

Response: task object (same shape as Phase 1):
```json
{
  "id": 1, "project_id": 1, "series_id": 1,
  "workflow_type": "t1_deepprep",
  "status": "queued", "progress": 0,
  "log_path": "...", "error_message": null,
  "created_at": "...", "started_at": null, "finished_at": null
}
```

Validation rules at endpoint:
- `t1_deepprep*` requires series `modality == "T1"`
- `dwi_qsiprep*` and `dwi_qsi_full*` require series `modality == "DWI"` and `has_bval == true` and `has_bvec == true`
- `dwi_qsirecon*` requires `qsiprep_task_id`; referenced task must be a QSIPrep-producing task (`workflow_type` starts with `dwi_qsiprep` or equals `dwi_qsi_full`).
- `dwi_qsirecon` (real run) requires referenced QSIPrep task `status == "completed"`.
- `dwi_qsirecon_validate` does not require referenced QSIPrep task to be completed.

## New: Workflow Type Listing

`GET /workflows`

Response:
```json
{
  "workflows": [
    { "type": "t1_deepprep", "label": "T1 DeepPrep (anatomical)", "input_modality": "T1", "chained": false },
    { "type": "dwi_qsiprep", "label": "DWI QSIPrep", "input_modality": "DWI", "chained": false },
    { "type": "dwi_qsirecon", "label": "DWI QSIRecon", "input_modality": null, "chained": false },
    { "type": "dwi_qsi_full", "label": "DWI QSIPrep + QSIRecon", "input_modality": "DWI", "chained": true }
  ]
}
```

Frontend uses this to render workflow buttons dynamically instead of hardcoding `"t1_deepprep_mock"`.

## Validation Mode Contract

`_validate` workflows return a task with:
- `progress`: jumps to 100 immediately
- `outputs`: a single output of `output_type: "command"` whose content is the fully-constructed docker command string
- `status`: `"completed"` if image exists and command constructs, `"failed"` if image missing or command error
- No container is launched. Log text contains `docker image inspect` output and the resolved command.

Validation output example:
```json
{
  "output_type": "command",
  "path": null,
  "preview_path": null,
  "metadata": {
    "docker_image": "pbfslab/deepprep:25.1.0",
    "image_available": true,
    "command": "sudo -S docker run --rm -v /home/yyf/codex/license.txt:/opt/freesurfer/license.txt:ro -v /path/bids:/data -v /path/output:/output pbfslab/deepprep:25.1.0 /data /output participant --anat_only",
    "bind_mounts": {
      "bids": "/path/to/bids",
      "output": "/path/to/output",
      "license": "/home/yyf/codex/license.txt"
    }
  }
}
```

## Task State Machine (unchanged from Phase 1)

States: `queued` → `running` → `completed` | `failed`
Any non-terminal state → `cancelled` (future).

Phase 2 adds no new states. Real workflows update progress at coarse milestones (10, 30, 70, 100). Logs are appended with timestamped, structured lines: `[{timestamp}] {message}`.

## Output Types by Workflow

| workflow_type | output_types |
|---|---|
| `t1_deepprep` | `qc_report`, `segmentation`, `brain_mask`, `chart` |
| `dwi_qsiprep` | `qc_report`, `preprocessed_dwi`, `confounds`, `html_report` |
| `dwi_qsirecon` | `dti_fa`, `dti_md`, `tractography`, `connectome`, `html_report` |
| `dwi_qsi_full` | union of qsiprep + qsirecon outputs |

Exact output paths follow the container's native layout under `derivatives/{task_id}/output/`. The `outputs` table records logical types; actual paths are discovered post-run via the runner.
