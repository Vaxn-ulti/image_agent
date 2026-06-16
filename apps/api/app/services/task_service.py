from __future__ import annotations

import json
from pathlib import Path

from fastapi import HTTPException

from app.core import config
from app.db.database import connect, now_iso
from app.db.queries import fetch_rows
from app.imaging.dwi_sidecars import dwi_has_required_sidecars
from app.imaging.series_records import parse_series_row
from app.services.background import submit_background
from app.services.project_service import require_project
from app.services.runtime_overrides import main_patch_attr, main_projects_root
from app.workflows.deepprep import run_mock_deepprep
from app.workflows.qsiprep_outputs import qsiprep_output_has_anat
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


def _projects_root() -> Path:
    return main_projects_root(_DEFAULT_PROJECTS_ROOT, require_override=True)


def public_task(task):
    item = dict(task)
    item.pop("log_path", None)
    return item


def list_project_tasks(project_id):
    require_project(project_id)
    return [public_task(task) for task in fetch_rows("SELECT * FROM tasks WHERE project_id=? ORDER BY id DESC", (project_id,))]


def get_series(series_id):
    found = fetch_rows("SELECT * FROM imaging_series WHERE id=?", (series_id,))
    if not found:
        raise HTTPException(404, "Series not found")
    return parse_series_row(found[0])


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
            companion_t1 = fetch_rows(
                "SELECT id FROM imaging_series WHERE project_id=? AND modality='T1' AND supported_for_processing=1 ORDER BY id DESC LIMIT 1",
                (series["project_id"],),
            )
            if not companion_t1:
                raise HTTPException(400, "DWI QSIPrep + QSIRecon requires T1/anat data in the same project")
    if workflow_type.startswith("dwi_fast_gpu_dti"):
        if modality != "DWI" or not dwi_has_required_sidecars(series, metadata):
            raise HTTPException(
                400,
                "DWI fast GPU DTI requires DWI series with bval, bvec, and JSON sidecar containing PhaseEncodingDirection and TotalReadoutTime",
            )
    if workflow_type.startswith("dwi_qsirecon"):
        if not req.qsiprep_task_id:
            raise HTTPException(400, "QSIRecon requires qsiprep_task_id")
        candidates = fetch_rows("SELECT * FROM tasks WHERE id=?", (req.qsiprep_task_id,))
        if not candidates:
            raise HTTPException(400, "qsiprep_task_id not found")
        if not candidates[0]["workflow_type"].startswith("dwi_qsiprep") and candidates[0]["workflow_type"] != "dwi_qsi_full":
            raise HTTPException(400, "qsiprep_task_id must reference QSIPrep task")
        if not req.workflow_type.endswith("_validate") and candidates[0]["status"] != "completed":
            raise HTTPException(400, "QSIRecon requires completed QSIPrep task")
        if candidates[0]["status"] == "completed" and not qsiprep_output_has_anat(req.qsiprep_task_id, projects_root=_projects_root()):
            raise HTTPException(
                400,
                "QSIRecon requires QSIPrep output with subject anat derivatives; rerun QSIPrep in a project that includes T1/anat input",
            )
    if workflow_type.startswith("dicom_convert") and modality != "DICOM":
        raise HTTPException(400, "DICOM conversion requires a DICOM archive series")
    if workflow_type.startswith("bold_") and modality != "BOLD":
        raise HTTPException(400, "BOLD workflows require BOLD series")
    if workflow_type.startswith("bold_alff") or workflow_type.startswith("bold_falff") or workflow_type.startswith("bold_second_level"):
        prior = fetch_rows(
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
    series = fetch_rows("SELECT * FROM imaging_series WHERE id=?", (series_id,))
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
        runner = main_patch_attr("run_mock_deepprep", run_mock_deepprep)
        submit_background(runner, task_id)
    else:
        runner = main_patch_attr("run_pipeline_task", run_pipeline_task)
        submit_background(runner, task_id, req.qsiprep_task_id)
    return task


def run_series(series_id, req):
    return public_task(create_series_task(series_id, req))


def get_task(task_id):
    found = fetch_rows("SELECT * FROM tasks WHERE id=?", (task_id,))
    if not found:
        raise HTTPException(404, "Task not found")
    return found[0]


def get_public_task(task_id):
    return public_task(get_task(task_id))
