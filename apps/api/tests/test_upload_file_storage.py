from __future__ import annotations

import hashlib
import io
from pathlib import Path

from app.core import config
from app.db import database


def test_save_project_upload_persists_sanitized_file_and_db_row(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_ROOT", tmp_path)
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "app.db")
    monkeypatch.setattr(config, "PROJECTS_ROOT", tmp_path / "projects")
    monkeypatch.setattr(database, "DB_PATH", tmp_path / "app.db")

    database.init_db()
    with database.connect() as conn:
        cursor = conn.execute(
            "INSERT INTO projects(name, description, created_at) VALUES(?,?,?)",
            ("Upload Storage", "", database.now_iso()),
        )
        project_id = cursor.lastrowid

    from app.storage.upload_files import save_project_upload

    payload = b"brain-image-bytes"
    row = save_project_upload(
        project_id=project_id,
        filename="../sub-01_T1w.nii.gz",
        stream=io.BytesIO(payload),
        projects_root=tmp_path / "projects",
    )

    stored = Path(row["storage_path"])
    assert stored == tmp_path / "projects" / str(project_id) / "raw" / "sub-01_T1w.nii.gz"
    assert stored.read_bytes() == payload
    assert row["original_name"] == "sub-01_T1w.nii.gz"
    assert row["file_type"] == "NIFTI"
    assert row["size"] == len(payload)
    assert row["sha256"] == hashlib.sha256(payload).hexdigest()
