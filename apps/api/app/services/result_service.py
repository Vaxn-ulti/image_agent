from __future__ import annotations

import json
import mimetypes
import sys
from pathlib import Path

from fastapi import HTTPException
from fastapi.responses import FileResponse

from app.core import config
from app.services import task_service
from app.services.compat import legacy
from app.workflows.artifact_manifest import build_artifact_manifest
from app.workflows.remote_scripts import classify_bold_fmriprep_xcpd_artifact_stage
from app.workflows.result_contract import load_result_summary


def _main_attr(name: str, default):
    main = sys.modules.get("app.main")
    if main is not None and hasattr(main, name):
        return getattr(main, name)
    return default


def _projects_root() -> Path:
    return Path(_main_attr("PROJECTS_ROOT", config.PROJECTS_ROOT))


def _rows(sql: str, params=()):
    main = sys.modules.get("app.main")
    if main is not None and hasattr(main, "rows"):
        return getattr(main, "rows")(sql, params)
    return legacy().rows(sql, params)


def get_logs(task_id):
    task = task_service.get_task(task_id)
    path = Path(task["log_path"])
    text = path.read_text(encoding="utf-8") if path.exists() else ""
    output_dir = _projects_root() / str(task["project_id"]) / "derivatives" / str(task_id) / "output"
    output_log_dir = output_dir / "logs"
    remote_logs = []
    if output_log_dir.exists():
        for log_file in sorted(output_log_dir.glob("*.log")):
            try:
                log_text = log_file.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            remote_logs.append(
                {
                    "name": log_file.name,
                    "path": str(log_file),
                    "source_stage": classify_bold_fmriprep_xcpd_artifact_stage(log_file, output_dir),
                    "size_bytes": log_file.stat().st_size,
                    "tail": log_text[-12000:],
                }
            )
    return {
        "task_id": task_id,
        "text": text,
        "remote_logs": remote_logs,
        "log_paths": [str(path), *[item["path"] for item in remote_logs]],
    }


def get_outputs(task_id):
    result = []
    for row in _rows("SELECT * FROM outputs WHERE task_id=? ORDER BY id", (task_id,)):
        item = dict(row)
        item["metadata"] = json.loads(item.pop("metadata_json"))
        result.append(item)
    return result


def get_result_summary(task_id):
    task = task_service.get_task(task_id)
    task_outputs = get_outputs(task_id)
    for output in task_outputs:
        metadata = output["metadata"]
        output_path = output.get("path") or ""
        if metadata.get("kind") == "result_summary" or output_path.endswith("_result_summary.json"):
            path = Path(output["path"])
            if path.exists():
                payload = json.loads(path.read_text(encoding="utf-8"))
                payload.setdefault("summary_path", str(path))
                return payload
    for output in task_outputs:
        metadata = output["metadata"]
        output_path = output.get("path") or ""
        if metadata.get("kind") == "bold_metrics_summary" and output_path:
            path = Path(output["path"])
            if path.exists():
                payload = json.loads(path.read_text(encoding="utf-8"))
                return {
                    "contract_version": payload.get("contract_version", "legacy-bold-metrics"),
                    "task_id": task_id,
                    "workflow_type": task["workflow_type"],
                    "modality": "BOLD",
                    "spaces": payload.get("spaces", ["MNI152"]),
                    "feature_groups": ["legacy_bold_metrics"],
                    "outputs": {},
                    "provenance": {
                        "legacy_fallback": True,
                        "legacy_summary_path": str(path),
                        "note": "Legacy BOLD metrics summary returned because no unified result_summary was registered.",
                    },
                    "legacy_summary": payload,
                }
    output_dir = _projects_root() / str(task["project_id"]) / "derivatives" / str(task_id) / "output"
    summary = load_result_summary(output_dir)
    if summary is None:
        raise HTTPException(404, "Result summary not found")
    return summary


def get_task_artifact_manifest(task_id):
    task = task_service.get_task(task_id)
    output_dir = _projects_root() / str(task["project_id"]) / "derivatives" / str(task_id) / "output"
    try:
        summary = get_result_summary(task_id)
    except HTTPException as exc:
        if exc.status_code != 404:
            raise
        summary = None
    return build_artifact_manifest(task, output_dir, summary, get_outputs(task_id))


def get_task_artifact(task_id, relative_path):
    if "\\" in relative_path:
        raise HTTPException(400, "Artifact path is outside the task output directory")
    task = task_service.get_task(task_id)
    output_dir = (_projects_root() / str(task["project_id"]) / "derivatives" / str(task_id) / "output").resolve()
    target = (output_dir / relative_path).resolve()
    if output_dir not in [target, *target.parents]:
        raise HTTPException(400, "Artifact path is outside the task output directory")
    if not target.exists() or not target.is_file():
        raise HTTPException(404, "Artifact not found")
    media_type = "application/gzip" if target.name.endswith(".nii.gz") else mimetypes.guess_type(target.name)[0]
    return FileResponse(target, media_type=media_type)


def bold_group_analysis(project_id, req):
    return legacy().bold_group_analysis(project_id, req)


def bold_descriptive_review(project_id, req):
    return legacy().bold_descriptive_review(project_id, req)
