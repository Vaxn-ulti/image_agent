from __future__ import annotations

import hashlib
from pathlib import Path
from typing import BinaryIO

from app.db.database import connect, now_iso

CHUNK_SIZE = 1024 * 1024


def infer_file_type(filename: str, file_type: str | None = None) -> str:
    if file_type is not None:
        return file_type
    if filename.lower().endswith((".nii", ".nii.gz")):
        return "NIFTI"
    return Path(filename).suffix.lower().lstrip(".").upper()


def save_stream_to_path(stream: BinaryIO, destination: Path) -> dict:
    destination.parent.mkdir(parents=True, exist_ok=True)
    sha = hashlib.sha256()
    with destination.open("wb") as out:
        while chunk := stream.read(CHUNK_SIZE):
            sha.update(chunk)
            out.write(chunk)
    return {"size": destination.stat().st_size, "sha256": sha.hexdigest()}


def save_project_upload(
    *,
    project_id: int,
    filename: str | None,
    stream: BinaryIO,
    projects_root: Path,
    file_type: str | None = None,
) -> dict:
    safe_name = Path(filename or "upload.bin").name
    destination = projects_root / str(project_id) / "raw" / safe_name
    stored = save_stream_to_path(stream, destination)
    inferred = infer_file_type(safe_name, file_type)
    with connect() as conn:
        cursor = conn.execute(
            "INSERT INTO files(project_id, original_name, storage_path, file_type, size, sha256, created_at) VALUES(?,?,?,?,?,?,?)",
            (project_id, safe_name, str(destination), inferred, stored["size"], stored["sha256"], now_iso()),
        )
        return dict(conn.execute("SELECT * FROM files WHERE id=?", (cursor.lastrowid,)).fetchone())
