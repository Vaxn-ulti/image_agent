from __future__ import annotations

import json
import sys
from pathlib import Path
from threading import Thread

from fastapi import HTTPException

from app.core import config
from app.db.database import connect, now_iso
from app.workflows.deepprep import run_mock_deepprep
from app.workflows.eligibility import build_workflow_eligibility
from app.workflows.registry import allowed_runtime_workflows, resolve_runtime_workflow_type

try:
    from app.workflows.pipeline import run_pipeline_task
except ImportError:

    def run_pipeline_task(task_id: int, qsiprep_task_id: int | None = None) -> None:
        with connect() as conn:
            conn.execute(
                "UPDATE tasks SET status='failed', error_message='pipeline runner missing', finished_at=? WHERE id=?",
                (now_iso(), task_id),
            )


_DEFAULT_PROJECTS_ROOT = Path(config.PROJECTS_ROOT)


def _main_attr(name: str, default):
    main = sys.modules.get("app.main")
    if main is not None and hasattr(main, name):
        return getattr(main, name)
    return default


def _projects_root() -> Path:
    main = sys.modules.get("app.main")
    if main is not None and hasattr(main, "PROJECTS_ROOT"):
        main_root = Path(getattr(main, "PROJECTS_ROOT"))
        if main_root != _DEFAULT_PROJECTS_ROOT:
            return main_root
    return Path(config.PROJECTS_ROOT)


def _rows(sql: str, params=()):
    with connect() as conn:
        return [dict(row) for row in conn.execute(sql, params).fetchall()]


def _parse_series_row(row: dict):
    item = dict(row)
    item["metadata"] = json.loads(item.pop("metadata_json"))
    item["supported_for_processing"] = bool(item.get("supported_for_processing", 1))
    file_rows = _rows("SELECT storage_path, file_type FROM files WHERE id=?", (item.get("file_id"),))
    if file_rows:
        item["file_storage_path"] = file_rows[0]["storage_path"]
        item["file_type"] = file_rows[0]["file_type"]
    item["workflow_eligibility"] = build_workflow_eligibility(item)
    item.pop("file_storage_path", None)
    item.pop("file_type", None)
    return item


def _qsiprep_output_dir(task_id: int) -> Path:
    for project_dir in _projects_root().iterdir() if _projects_root().exists() else []:
        candidate = project_dir / "derivatives" / str(task_id) / "output"
        if candidate.exists():
            return candidate
    return _projects_root() / "__missing__" / str(task_id) / "output"


def _qsiprep_output_has_anat(task_id: int) -> bool:
    anat_dir = _qsiprep_output_dir(task_id) / "sub-01" / "anat"
    return anat_dir.exists() and any(anat_dir.iterdir())


def _sidecar_base(path: Path) -> str:
    return path.name[:-7] if path.name.lower().endswith(".nii.gz") else path.stem


def _dwi_sidecar_paths(series: dict, metadata: dict) -> dict[str, Path]:
    sidecars: dict[str, Path] = {}
    for raw_path in metadata.get("sidecars") or []:
        path = Path(raw_path)
        suffix = path.suffix.lower()
        if suffix in {".json", ".bval", ".bvec"} and path.exists():
            sidecars[suffix] = path

    try:
        main_file = _rows("SELECT storage_path, file_type FROM files WHERE id=?", (series["file_id"],))[0]
    except (IndexError, KeyError):
        main_file = None
    allow_same_stem_fallback = bool(
        metadata.get("sidecars")
        or metadata.get("bids_path")
        or series.get("format") == "NIFTI_BIDS"
        or (main_file and main_file.get("file_type") == "NIFTI_BIDS")
    )
    if main_file and allow_same_stem_fallback:
        src = Path(main_file["storage_path"])
        base = _sidecar_base(src)
        for suffix in (".json", ".bval", ".bvec"):
            candidate = src.with_name(base + suffix)
            if suffix not in sidecars and candidate.exists():
                sidecars[suffix] = candidate
    return sidecars


def _dwi_has_eddy_json_metadata(series: dict, metadata: dict) -> bool:
    if metadata.get("has_json") and metadata.get("has_dwi_eddy_metadata"):
        return True
    json_path = _dwi_sidecar_paths(series, metadata).get(".json")
    if json_path is None:
        return False
    try:
        payload = json.loads(json_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    return payload.get("PhaseEncodingDirection") is not None and payload.get("TotalReadoutTime") is not None


def _dwi_has_required_sidecars(series: dict, metadata: dict) -> bool:
    sidecars = _dwi_sidecar_paths(series, metadata)
    return (
        bool(metadata.get("has_bval") or ".bval" in sidecars)
        and bool(metadata.get("has_bvec") or ".bvec" in sidecars)
        and _dwi_has_eddy_json_metadata(series, metadata)
    )


def list_project_tasks(project_id):
    return _rows("SELECT * FROM tasks WHERE project_id=? ORDER BY id DESC", (project_id,))


def get_series(series_id):
    found = _rows("SELECT * FROM imaging_series WHERE id=?", (series_id,))
    if not found:
        raise HTTPException(404, "Series not found")
    return _parse_series_row(found[0])


def validate_run_request(series, req):
    if req.workflow_type not in allowed_runtime_workflows():
        raise HTTPException(400, f"Unknown workflow_type: {req.workflow_type}")
    workflow_type = resolve_runtime_workflow_type(req.workflow_type)
    metadata = json.loads(series["metadata_json"])
    modality = series["modality"]
    if workflow_type == "t1_deepprep_mock":
        if modality != "T1":
            raise HTTPException(400, "T1 mock requires T1 series")
        return
    if workflow_type.startswith("t1_deepprep") and modality != "T1":
        raise HTTPException(400, "DeepPrep requires a T1 series")
    if workflow_type.startswith("bold_deepprep") and modality != "BOLD":
        raise HTTPException(400, "BOLD DeepPrep requires a BOLD/fMRI series")
    if workflow_type.startswith("dwi_qsiprep") or workflow_type.startswith("dwi_qsi_full"):
        if modality != "DWI" or not metadata.get("has_bval") or not metadata.get("has_bvec"):
            raise HTTPException(400, "DWI workflows require DWI series with bval and bvec")
        if workflow_type.startswith("dwi_qsi_full"):
            companion_t1 = _rows(
                "SELECT id FROM imaging_series WHERE project_id=? AND modality='T1' AND supported_for_processing=1 ORDER BY id DESC LIMIT 1",
                (series["project_id"],),
            )
            if not companion_t1:
                raise HTTPException(400, "DWI QSIPrep + QSIRecon requires T1/anat data in the same project")
    if workflow_type.startswith("dwi_fast_gpu_dti"):
        if modality != "DWI" or not _dwi_has_required_sidecars(series, metadata):
            raise HTTPException(
                400,
                "DWI fast GPU DTI requires DWI series with bval, bvec, and JSON sidecar containing PhaseEncodingDirection and TotalReadoutTime",
            )
    if workflow_type.startswith("dwi_qsirecon"):
        if not req.qsiprep_task_id:
            raise HTTPException(400, "QSIRecon requires qsiprep_task_id")
        candidates = _rows("SELECT * FROM tasks WHERE id=?", (req.qsiprep_task_id,))
        if not candidates:
            raise HTTPException(400, "qsiprep_task_id not found")
        if not candidates[0]["workflow_type"].startswith("dwi_qsiprep") and candidates[0]["workflow_type"] != "dwi_qsi_full":
            raise HTTPException(400, "qsiprep_task_id must reference QSIPrep task")
        if not req.workflow_type.endswith("_validate") and candidates[0]["status"] != "completed":
            raise HTTPException(400, "QSIRecon requires completed QSIPrep task")
        if candidates[0]["status"] == "completed" and not _qsiprep_output_has_anat(req.qsiprep_task_id):
            raise HTTPException(
                400,
                "QSIRecon requires QSIPrep output with subject anat derivatives; rerun QSIPrep in a project that includes T1/anat input",
            )
    if workflow_type.startswith("dicom_convert") and modality != "DICOM":
        raise HTTPException(400, "DICOM conversion requires a DICOM archive series")
    if workflow_type.startswith("bold_") and modality != "BOLD":
        raise HTTPException(400, "BOLD workflows require BOLD series")
    if workflow_type.startswith("bold_alff") or workflow_type.startswith("bold_falff") or workflow_type.startswith("bold_second_level"):
        prior = _rows(
            "SELECT workflow_type, status FROM tasks WHERE project_id=? AND series_id=? ORDER BY id DESC",
            (series["project_id"], series["id"]),
        )
        has_completed_preproc = any(
            task["status"] == "completed" and task["workflow_type"] == "bold_deepprep"
            for task in prior
        )
        if not has_completed_preproc:
            raise HTTPException(400, "BOLD metrics require a completed bold_deepprep task for this series")
    if series.get("supported_for_processing") == 0 and workflow_type != "t1_deepprep_mock":
        raise HTTPException(400, series.get("unsupported_reason") or "This sequence is not supported for processing")


def create_series_task(series_id, req):
    try:
        req.workflow_type = resolve_runtime_workflow_type(req.workflow_type)
    except KeyError as exc:
        raise HTTPException(400, f"Unknown workflow_type: {req.workflow_type}") from exc
    series = _rows("SELECT * FROM imaging_series WHERE id=?", (series_id,))
    if not series:
        raise HTTPException(404, "Series not found")
    series_row = series[0]
    validate_run_request(series_row, req)
    project_id = series_row["project_id"]
    log_path = _projects_root() / str(project_id) / "logs" / "pending.log"
    with connect() as conn:
        cursor = conn.execute(
            "INSERT INTO tasks(project_id, series_id, workflow_type, status, progress, log_path, qsiprep_task_id, created_at) VALUES(?,?,?,?,?,?,?,?)",
            (project_id, series_id, req.workflow_type, "queued", 0, str(log_path), req.qsiprep_task_id, now_iso()),
        )
        task_id = cursor.lastrowid
        final_log = _projects_root() / str(project_id) / "logs" / f"{task_id}.log"
        conn.execute("UPDATE tasks SET log_path=? WHERE id=?", (str(final_log), task_id))
        task = dict(conn.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone())
    if req.workflow_type == "t1_deepprep_mock":
        runner = _main_attr("run_mock_deepprep", run_mock_deepprep)
        Thread(target=runner, args=(task_id,), daemon=True).start()
    else:
        runner = _main_attr("run_pipeline_task", run_pipeline_task)
        Thread(target=runner, args=(task_id, req.qsiprep_task_id), daemon=True).start()
    return task


def run_series(series_id, req):
    return create_series_task(series_id, req)


def get_task(task_id):
    found = _rows("SELECT * FROM tasks WHERE id=?", (task_id,))
    if not found:
        raise HTTPException(404, "Task not found")
    return found[0]
