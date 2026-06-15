from __future__ import annotations

import hashlib
import json
import os
import zipfile
from pathlib import Path

from fastapi import HTTPException

from app.db.database import connect, now_iso
from app.db.queries import fetch_rows
from app.imaging.detect import detect_series
from app.imaging.ingest import process_upload_session
from app.imaging.series_records import parse_series_row
from app.services.background import submit_background
from app.services.project_service import require_project
from app.services.runtime_overrides import main_patch_attr, main_projects_root
from app.workflows.eligibility import build_workflow_eligibility


def _projects_root() -> Path:
    return main_projects_root()


def _process_upload_session():
    return main_patch_attr("process_upload_session", process_upload_session)


def _save_upload(project_id: int, upload, file_type: str | None = None) -> dict:
    raw_dir = _projects_root() / str(project_id) / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    safe_name = Path(upload.filename or "upload.bin").name
    dest = raw_dir / safe_name
    sha = hashlib.sha256()
    with dest.open("wb") as out:
        while chunk := upload.file.read(1024 * 1024):
            sha.update(chunk)
            out.write(chunk)
    inferred = file_type or (
        "NIFTI"
        if safe_name.lower().endswith((".nii", ".nii.gz"))
        else Path(safe_name).suffix.lower().lstrip(".").upper()
    )
    with connect() as conn:
        cur = conn.execute(
            "INSERT INTO files(project_id, original_name, storage_path, file_type, size, sha256, created_at) VALUES(?,?,?,?,?,?,?)",
            (project_id, safe_name, str(dest), inferred, dest.stat().st_size, sha.hexdigest(), now_iso()),
        )
        return dict(conn.execute("SELECT * FROM files WHERE id=?", (cur.lastrowid,)).fetchone())


def upload(project_id, file):
    require_project(project_id)
    file_row = _save_upload(project_id, file)
    detection = detect_series(file_row["storage_path"])
    metadata = detection["metadata"]
    with connect() as conn:
        cursor = conn.execute(
            "INSERT INTO imaging_series(project_id, file_id, sequence_label, supported_for_processing, unsupported_reason, modality, format, confidence, metadata_json, status, created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
            (
                project_id,
                file_row["id"],
                metadata.get("sequence_label"),
                1 if metadata.get("supported_for_processing", True) else 0,
                metadata.get("unsupported_reason", ""),
                detection["modality"],
                detection["format"],
                detection["confidence"],
                json.dumps(metadata),
                "detected",
                now_iso(),
            ),
        )
        series_row = conn.execute("SELECT * FROM imaging_series WHERE id=?", (cursor.lastrowid,)).fetchone()
    return {"file": file_row, "series": parse_series_row(series_row)}


def _dwi_json_metadata(json_row: dict | None) -> dict:
    if json_row is None:
        return {"has_json": False, "has_dwi_eddy_metadata": False}
    path = Path(json_row["storage_path"])
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise HTTPException(400, "DWI JSON sidecar must be valid JSON") from exc
    phase_encoding = payload.get("PhaseEncodingDirection")
    total_readout = payload.get("TotalReadoutTime")
    return {
        "has_json": True,
        "json_file_id": json_row["id"],
        "has_dwi_eddy_metadata": phase_encoding is not None and total_readout is not None,
        "phase_encoding_direction": phase_encoding,
        "total_readout_time": total_readout,
    }


def upload_dwi(project_id, nifti, bval, bvec, json_sidecar=None):
    require_project(project_id)
    nifti_row = _save_upload(project_id, nifti, "NIFTI")
    bval_row = _save_upload(project_id, bval, "BVAL")
    bvec_row = _save_upload(project_id, bvec, "BVEC")
    json_row = _save_upload(project_id, json_sidecar, "JSON") if json_sidecar is not None else None
    detection = detect_series(nifti_row["storage_path"])
    metadata = detection["metadata"]
    metadata.update(
        {
            "has_bval": True,
            "has_bvec": True,
            "bval_file_id": bval_row["id"],
            "bvec_file_id": bvec_row["id"],
            **_dwi_json_metadata(json_row),
        }
    )
    with connect() as conn:
        cursor = conn.execute(
            "INSERT INTO imaging_series(project_id, file_id, sequence_label, supported_for_processing, unsupported_reason, modality, format, confidence, metadata_json, status, created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
            (
                project_id,
                nifti_row["id"],
                metadata.get("sequence_label", "DWI_multi_shell"),
                1,
                "",
                "DWI",
                "NIFTI",
                0.95,
                json.dumps(metadata),
                "detected",
                now_iso(),
            ),
        )
        series_row = conn.execute("SELECT * FROM imaging_series WHERE id=?", (cursor.lastrowid,)).fetchone()
    file_rows = [nifti_row, bval_row, bvec_row]
    if json_row is not None:
        file_rows.append(json_row)
    return {"files": file_rows, "series": parse_series_row(series_row)}


def upload_dicom(project_id, archive):
    require_project(project_id)
    archive_row = _save_upload(project_id, archive, "DICOM_ZIP")
    extract_dir = _projects_root() / str(project_id) / "raw" / f"dicom_{archive_row['id']}"
    extract_dir.mkdir(parents=True, exist_ok=True)
    try:
        with zipfile.ZipFile(archive_row["storage_path"]) as zf:
            for member in zf.infolist():
                target = (extract_dir / member.filename).resolve()
                if extract_dir.resolve() not in [target, *target.parents]:
                    raise HTTPException(400, "Unsafe DICOM archive path")
            zf.extractall(extract_dir)
    except zipfile.BadZipFile as exc:
        raise HTTPException(400, "DICOM upload must be a zip archive") from exc
    dicom_files = [path for path in extract_dir.rglob("*") if path.is_file()]
    metadata = {
        "filename": archive_row["original_name"],
        "archive_file_id": archive_row["id"],
        "dicom_dir": str(extract_dir),
        "dicom_file_count": len(dicom_files),
    }
    with connect() as conn:
        cursor = conn.execute(
            "INSERT INTO imaging_series(project_id, file_id, sequence_label, supported_for_processing, unsupported_reason, modality, format, confidence, metadata_json, status, created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
            (
                project_id,
                archive_row["id"],
                "DICOM_ARCHIVE",
                1,
                "",
                "DICOM",
                "DICOM_ZIP",
                0.85 if dicom_files else 0.2,
                json.dumps(metadata),
                "detected",
                now_iso(),
            ),
        )
        series_row = conn.execute("SELECT * FROM imaging_series WHERE id=?", (cursor.lastrowid,)).fetchone()
    return {"file": archive_row, "series": parse_series_row(series_row)}


def create_upload_session(project_id, req):
    require_project(project_id)
    with connect() as conn:
        cursor = conn.execute(
            "INSERT INTO upload_sessions(project_id, label, source_type, status, progress, inventory_json, created_at) VALUES(?,?,?,?,?,?,?)",
            (project_id, req.label, req.source_type, "ready", 0, "{}", now_iso()),
        )
        return dict(conn.execute("SELECT * FROM upload_sessions WHERE id=?", (cursor.lastrowid,)).fetchone())


def ingest_dataset(project_id, upload_session_id, archive, sync_fast_path=True):
    sessions = fetch_rows("SELECT * FROM upload_sessions WHERE id=? AND project_id=?", (upload_session_id, project_id))
    if not sessions:
        raise HTTPException(404, "Upload session not found")
    upload_dir = _projects_root() / str(project_id) / "uploads" / str(upload_session_id) / "originals"
    upload_dir.mkdir(parents=True, exist_ok=True)
    safe_name = Path(archive.filename or "dataset.zip").name
    archive_path = upload_dir / safe_name
    with archive_path.open("wb") as out:
        while chunk := archive.file.read(1024 * 1024):
            out.write(chunk)
    threshold = int(os.environ.get("IMAGE_AGENT_SYNC_INGEST_MAX_BYTES", str(32 * 1024 * 1024)))
    processor = _process_upload_session()
    if sync_fast_path and archive_path.stat().st_size <= threshold:
        inventory = processor(project_id, upload_session_id, archive_path)
        return {"upload_session_id": upload_session_id, "status": inventory["inventory_status"], "inventory": inventory}
    submit_background(processor, project_id, upload_session_id, archive_path)
    return {"upload_session_id": upload_session_id, "status": "running"}


def get_inventory(project_id, upload_session_id):
    found = fetch_rows("SELECT * FROM upload_sessions WHERE id=? AND project_id=?", (upload_session_id, project_id))
    if not found:
        raise HTTPException(404, "Upload session not found")
    session = found[0]
    inventory = json.loads(session["inventory_json"] or "{}")
    inventory = enrich_inventory_workflow_eligibility(inventory)
    return {
        "upload_session_id": upload_session_id,
        "status": session["status"],
        "progress": session["progress"],
        "inventory": inventory,
        "error_message": session.get("error_message"),
    }


def enrich_inventory_workflow_eligibility(inventory: dict) -> dict:
    if not isinstance(inventory, dict):
        return inventory
    series = inventory.get("series")
    if not isinstance(series, list):
        return inventory
    enriched_series = []
    changed = False
    for item in series:
        if not isinstance(item, dict):
            enriched_series.append(item)
            continue
        eligibility = item.get("workflow_eligibility")
        if isinstance(eligibility, dict) and eligibility.get("policy_version") == "workflow_eligibility_v1":
            enriched_series.append(item)
            continue
        enriched_series.append({**item, "workflow_eligibility": build_workflow_eligibility(item)})
        changed = True
    if not changed:
        return inventory
    return {**inventory, "series": enriched_series}


def list_series(project_id):
    return [
        parse_series_row(row)
        for row in fetch_rows("SELECT * FROM imaging_series WHERE project_id=? ORDER BY id DESC", (project_id,))
    ]
