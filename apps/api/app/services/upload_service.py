from __future__ import annotations

import json
import os
import re
import zipfile
from pathlib import Path
from typing import Any

from fastapi import HTTPException

from app.db.database import connect, now_iso
from app.db.queries import fetch_rows
from app.imaging.detect import detect_series, read_json_summary_file
from app.imaging.dwi_sidecars import dwi_json_metadata
from app.imaging.ingest import process_upload_session
from app.imaging.series_records import parse_series_row
from app.services.background import submit_background
from app.services.project_service import require_project
from app.services.runtime_overrides import main_patch_attr, main_projects_root
from app.storage.upload_files import save_project_upload, save_stream_to_path
from app.workflows.eligibility import build_workflow_eligibility


def _projects_root() -> Path:
    return main_projects_root()


def _process_upload_session():
    return main_patch_attr("process_upload_session", process_upload_session)


def _save_upload(project_id: int, upload, file_type: str | None = None) -> dict:
    return save_project_upload(
        project_id=project_id,
        filename=upload.filename,
        stream=upload.file,
        projects_root=_projects_root(),
        file_type=file_type,
    )


def _public_file(row: dict) -> dict:
    item = dict(row)
    item.pop("storage_path", None)
    return item


_INVENTORY_PATH_KEYS = {
    "source",
    "storage_path",
    "file_storage_path",
    "dicom_dir",
    "sidecars",
    "output_dir",
    "work_dir",
    "log_path",
}


def _redact_path_text(value: str) -> str:
    text = str(value)
    text = re.sub(r"[A-Za-z]:[\\/][^\s\"']+", "[redacted-host-path]", text)
    text = re.sub(r"/(?:home|Users|mnt|data|tmp|var)/[^\s\"']+", "[redacted-host-path]", text)
    return text


def _public_inventory_value(value: Any) -> Any:
    if isinstance(value, dict):
        public = {}
        for key, item in value.items():
            if key in _INVENTORY_PATH_KEYS:
                continue
            if key == "bids_dataset_root":
                public[key] = "bids/rawdata"
                continue
            public[key] = _public_inventory_value(item)
        return public
    if isinstance(value, list):
        return [_public_inventory_value(item) for item in value]
    if isinstance(value, str):
        return _redact_path_text(value)
    return value


def public_inventory(inventory: dict) -> dict:
    return _public_inventory_value(inventory)


def _is_detected_imaging_series(detection: dict) -> bool:
    return detection.get("format") != "UNKNOWN" or detection.get("modality") != "unknown"


def _attachment_item(file_row: dict) -> dict:
    return {
        "file_id": file_row["id"],
        "original_name": file_row["original_name"],
        "file_type": file_row["file_type"],
        "size": file_row["size"],
        "sha256": file_row["sha256"],
    }


def _inventory_file_item(file_row: dict, *, detected_as: str, linked_series_ids: list[int] | None = None) -> dict:
    return {
        "file_id": file_row["id"],
        "original_name": file_row["original_name"],
        "file_type": file_row["file_type"],
        "size": file_row["size"],
        "sha256": file_row["sha256"],
        "detected_as": detected_as,
        "linked_series_ids": linked_series_ids or [],
    }


def _reject_non_dwi_sidecar_upload(detection: dict) -> None:
    metadata = detection.get("metadata") or {}
    sequence_label = str(metadata.get("sequence_label") or "")
    modality = str(detection.get("modality") or "")
    if modality and modality not in {"DWI", "unknown"}:
        raise HTTPException(
            400,
            f"DWI sidecar upload received a {modality} NIfTI ({sequence_label or 'unlabeled'}). Upload it as a regular imaging file or choose the matching workflow.",
        )


def upload(project_id, file):
    require_project(project_id)
    file_row = _save_upload(project_id, file)
    detection = detect_series(file_row["storage_path"])
    metadata = detection["metadata"]
    with connect() as conn:
        session_cursor = conn.execute(
            "INSERT INTO upload_sessions(project_id, label, source_type, status, progress, inventory_json, created_at, started_at, finished_at) VALUES(?,?,?,?,?,?,?,?,?)",
            (
                project_id,
                Path(file.filename or "single-file-upload").name,
                "single_file_upload",
                "completed",
                100,
                "{}",
                now_iso(),
                now_iso(),
                now_iso(),
            ),
        )
        upload_session_id = session_cursor.lastrowid
        if not _is_detected_imaging_series(detection):
            inventory = {
                "inventory_status": "completed",
                "total_files": 1,
                "dicom": {"found_files": 0, "conversion_status": "not_applicable", "converted_series": 0, "failed_series": 0, "failures": []},
                "post_conversion_counts": {"by_modality": {}, "by_sequence": {}},
                "recognized_unsupported_sequences": [],
                "series": [],
                "attachments": [_attachment_item(file_row)],
                "files": [_inventory_file_item(file_row, detected_as="attachment")],
            }
            conn.execute(
                "UPDATE upload_sessions SET inventory_json=? WHERE id=?",
                (json.dumps(inventory), upload_session_id),
            )
            return {
                "file": _public_file(file_row),
                "series": None,
                "upload_session_id": upload_session_id,
                "status": "completed",
                "inventory": public_inventory(inventory),
            }
        cursor = conn.execute(
            "INSERT INTO imaging_series(project_id, file_id, sequence_label, supported_for_processing, unsupported_reason, modality, format, confidence, metadata_json, status, created_at, upload_session_id) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
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
                upload_session_id,
            ),
        )
        series_row = conn.execute("SELECT * FROM imaging_series WHERE id=?", (cursor.lastrowid,)).fetchone()
        inventory = {
            "inventory_status": "completed",
            "total_files": 1,
            "attachments": [],
            "files": [_inventory_file_item(file_row, detected_as=f"{detection['modality']}/{metadata.get('sequence_label')}", linked_series_ids=[cursor.lastrowid])],
            "series": [
                {
                    "series_id": cursor.lastrowid,
                    "modality": detection["modality"],
                    "format": detection["format"],
                    "sequence_label": metadata.get("sequence_label"),
                    "supported_for_processing": bool(metadata.get("supported_for_processing", True)),
                    "unsupported_reason": metadata.get("unsupported_reason", ""),
                }
            ],
        }
        conn.execute(
            "UPDATE upload_sessions SET inventory_json=? WHERE id=?",
            (json.dumps(inventory), upload_session_id),
        )
    return {"file": _public_file(file_row), "series": parse_series_row(series_row), "upload_session_id": upload_session_id}


def upload_dwi(project_id, nifti, bval, bvec, json_sidecar=None):
    require_project(project_id)
    nifti_row = _save_upload(project_id, nifti, "NIFTI")
    bval_row = _save_upload(project_id, bval, "BVAL")
    bvec_row = _save_upload(project_id, bvec, "BVEC")
    json_row = _save_upload(project_id, json_sidecar, "JSON") if json_sidecar is not None else None
    detection = detect_series(nifti_row["storage_path"])
    _reject_non_dwi_sidecar_upload(detection)
    metadata = detection["metadata"]
    metadata["sequence_label"] = metadata.get("sequence_label") if detection.get("modality") == "DWI" else "DWI_multi_shell"
    metadata.update(
        {
            "has_bval": True,
            "has_bvec": True,
            "bval_file_id": bval_row["id"],
            "bvec_file_id": bvec_row["id"],
            **dwi_json_metadata(json_row),
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
    return {"files": [_public_file(row) for row in file_rows], "series": parse_series_row(series_row)}


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
    return {"file": _public_file(archive_row), "series": parse_series_row(series_row)}


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
    save_stream_to_path(archive.file, archive_path)
    threshold = int(os.environ.get("IMAGE_AGENT_SYNC_INGEST_MAX_BYTES", str(32 * 1024 * 1024)))
    processor = _process_upload_session()
    if sync_fast_path and archive_path.stat().st_size <= threshold:
        inventory = processor(project_id, upload_session_id, archive_path)
        return {"upload_session_id": upload_session_id, "status": inventory["inventory_status"], "inventory": public_inventory(inventory)}
    submit_background(processor, project_id, upload_session_id, archive_path)
    return {"upload_session_id": upload_session_id, "status": "running"}


def get_inventory(project_id, upload_session_id):
    found = fetch_rows("SELECT * FROM upload_sessions WHERE id=? AND project_id=?", (upload_session_id, project_id))
    if not found:
        raise HTTPException(404, "Upload session not found")
    session = found[0]
    inventory = json.loads(session["inventory_json"] or "{}")
    inventory = public_inventory(enrich_inventory_workflow_eligibility(inventory))
    return {
        "upload_session_id": upload_session_id,
        "status": session["status"],
        "progress": session["progress"],
        "inventory": inventory,
        "error_message": _redact_path_text(session.get("error_message") or "") if session.get("error_message") else None,
    }


def list_project_files(project_id):
    require_project(project_id)
    files = fetch_rows(
        "SELECT id, project_id, original_name, file_type, size, sha256, created_at FROM files WHERE project_id=? ORDER BY id DESC LIMIT 200",
        (project_id,),
    )
    if not files:
        return []
    file_ids = [row["id"] for row in files]
    placeholders = ",".join("?" for _ in file_ids)
    series_rows = fetch_rows(
        "SELECT id, file_id, modality, sequence_label, format, confidence, status FROM imaging_series "
        f"WHERE file_id IN ({placeholders}) ORDER BY id DESC",
        tuple(file_ids),
    )
    by_file_id: dict[int, list[dict[str, Any]]] = {}
    for row in series_rows:
        by_file_id.setdefault(int(row["file_id"]), []).append(
            {
                "id": row["id"],
                "modality": row["modality"],
                "sequence_label": row["sequence_label"],
                "format": row["format"],
                "confidence": row["confidence"],
                "status": row["status"],
            }
        )
    public_files = []
    for row in files:
        item = dict(row)
        item["linked_series"] = by_file_id.get(int(row["id"]), [])
        if str(row.get("file_type") or "").upper() == "JSON":
            stored = fetch_rows("SELECT storage_path FROM files WHERE id=?", (row["id"],))
            item["json_summary"] = read_json_summary_file(stored[0]["storage_path"]) if stored else {}
        public_files.append(item)
    return public_files


def _referenced_sidecar_keys(metadata: dict[str, Any], file_id: int) -> set[str]:
    keys = set()
    for key in ("bval_file_id", "bvec_file_id", "json_file_id"):
        try:
            if int(metadata.get(key)) == int(file_id):
                keys.add(key)
        except (TypeError, ValueError):
            continue
    return keys


def _metadata_without_deleted_sidecar(metadata: dict[str, Any], sidecar_keys: set[str]) -> dict[str, Any]:
    updated = dict(metadata)
    if "bval_file_id" in sidecar_keys:
        updated.pop("bval_file_id", None)
        updated["has_bval"] = False
    if "bvec_file_id" in sidecar_keys:
        updated.pop("bvec_file_id", None)
        updated["has_bvec"] = False
    if "json_file_id" in sidecar_keys:
        updated.pop("json_file_id", None)
        updated["has_json"] = False
        updated["has_dwi_eddy_metadata"] = False
        updated.pop("phase_encoding_direction", None)
        updated.pop("total_readout_time", None)
    return updated


def _unlink_project_storage_file(storage_path: str) -> None:
    if not storage_path:
        return
    path = Path(storage_path)
    try:
        root = _projects_root().resolve()
        resolved = path.resolve()
    except OSError:
        return
    if root not in [resolved, *resolved.parents]:
        return
    try:
        if resolved.is_file():
            resolved.unlink()
    except OSError:
        return


def delete_project_file(project_id: int, file_id: int) -> dict:
    require_project(project_id)
    with connect() as conn:
        file_row = conn.execute(
            "SELECT * FROM files WHERE id=? AND project_id=?",
            (file_id, project_id),
        ).fetchone()
        if file_row is None:
            raise HTTPException(404, "File not found")
        series_rows = conn.execute(
            "SELECT id, file_id, metadata_json FROM imaging_series WHERE project_id=?",
            (project_id,),
        ).fetchall()
        primary_series_ids: list[int] = []
        sidecar_references: dict[int, tuple[dict[str, Any], set[str]]] = {}
        for row in series_rows:
            series_id = int(row["id"])
            if int(row["file_id"]) == int(file_id):
                primary_series_ids.append(series_id)
            try:
                metadata = json.loads(row["metadata_json"] or "{}")
            except json.JSONDecodeError:
                metadata = {}
            sidecar_keys = _referenced_sidecar_keys(metadata, file_id)
            if sidecar_keys:
                sidecar_references[series_id] = (metadata, sidecar_keys)
        affected_series_ids = sorted(set(primary_series_ids) | set(sidecar_references))
        if affected_series_ids:
            placeholders = ",".join("?" for _ in affected_series_ids)
            task_refs = conn.execute(
                f"SELECT DISTINCT series_id FROM tasks WHERE project_id=? AND series_id IN ({placeholders})",
                tuple([project_id, *affected_series_ids]),
            ).fetchall()
            if task_refs:
                raise HTTPException(409, "File is referenced by existing tasks and cannot be deleted.")

        for series_id, (metadata, sidecar_keys) in sidecar_references.items():
            if series_id in primary_series_ids:
                continue
            updated = _metadata_without_deleted_sidecar(metadata, sidecar_keys)
            conn.execute(
                "UPDATE imaging_series SET metadata_json=?, supported_for_processing=?, unsupported_reason=? WHERE id=?",
                (
                    json.dumps(updated),
                    0,
                    "Sidecar file was deleted; upload a complete sidecar set before processing.",
                    series_id,
                ),
            )
        if primary_series_ids:
            placeholders = ",".join("?" for _ in primary_series_ids)
            conn.execute(f"DELETE FROM imaging_series WHERE id IN ({placeholders})", tuple(primary_series_ids))
        conn.execute("DELETE FROM files WHERE id=? AND project_id=?", (file_id, project_id))
        deleted_file = _public_file(dict(file_row))

    _unlink_project_storage_file(str(file_row["storage_path"]))
    return {
        "deleted_file": deleted_file,
        "deleted_series_ids": primary_series_ids,
        "updated_series_ids": sorted(set(sidecar_references) - set(primary_series_ids)),
        "status": "deleted",
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
    require_project(project_id)
    return [
        parse_series_row(row)
        for row in fetch_rows("SELECT * FROM imaging_series WHERE project_id=? ORDER BY id DESC", (project_id,))
    ]
