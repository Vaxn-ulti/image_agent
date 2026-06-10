from datetime import datetime, timedelta, timezone

from app.db import database


def _prepare_db(tmp_path, monkeypatch):
    from app.core import config

    monkeypatch.setattr(config, "DATA_ROOT", tmp_path)
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "app.db")
    monkeypatch.setattr(config, "PROJECTS_ROOT", tmp_path / "projects")
    monkeypatch.setattr(database, "DB_PATH", tmp_path / "app.db")
    database.init_db()
    with database.connect() as conn:
        conn.execute(
            "INSERT INTO projects(id, name, description, created_at) VALUES(?,?,?,?)",
            (1, "demo", "", database.now_iso()),
        )
        conn.execute(
            "INSERT INTO files(id, project_id, original_name, storage_path, file_type, size, sha256, created_at) VALUES(?,?,?,?,?,?,?,?)",
            (1, 1, "bold.nii.gz", str(tmp_path / "bold.nii.gz"), "NIFTI", 1, "x", database.now_iso()),
        )
        conn.execute(
            "INSERT INTO imaging_series(id, project_id, file_id, modality, format, confidence, metadata_json, status, created_at) VALUES(?,?,?,?,?,?,?,?,?)",
            (1, 1, 1, "BOLD", "NIFTI", 1.0, "{}", "ready", database.now_iso()),
        )


def test_find_stale_active_tasks_is_dry_run_only(tmp_path, monkeypatch):
    from app.workflows import stale_tasks

    _prepare_db(tmp_path, monkeypatch)
    now = datetime(2026, 6, 11, 0, 0, tzinfo=timezone.utc)
    stale_started = (now - timedelta(hours=72)).isoformat()
    fresh_started = (now - timedelta(minutes=30)).isoformat()
    stale_log = tmp_path / "stale.log"
    with database.connect() as conn:
        conn.execute(
            "INSERT INTO tasks(id, project_id, series_id, workflow_type, status, progress, log_path, created_at, started_at) VALUES(?,?,?,?,?,?,?,?,?)",
            (83, 1, 1, "dwi_qsirecon", "running", 20, str(stale_log), stale_started, stale_started),
        )
        conn.execute(
            "INSERT INTO tasks(id, project_id, series_id, workflow_type, status, progress, log_path, created_at, started_at) VALUES(?,?,?,?,?,?,?,?,?)",
            (84, 1, 1, "dwi_qsirecon", "running", 20, str(tmp_path / "fresh.log"), fresh_started, fresh_started),
        )

    report = stale_tasks.reconcile_stale_active_tasks(
        max_age_hours=24,
        apply=False,
        now=now,
        running_container_task_ids=set(),
    )

    assert report["mode"] == "dry_run"
    assert [task["id"] for task in report["stale_candidates"]] == [83]
    assert report["updated_task_ids"] == []
    with database.connect() as conn:
        row = conn.execute("SELECT status, error_message FROM tasks WHERE id=83").fetchone()
    assert row["status"] == "running"
    assert row["error_message"] is None


def test_reconcile_stale_active_tasks_refuses_running_container(tmp_path, monkeypatch):
    from app.workflows import stale_tasks

    _prepare_db(tmp_path, monkeypatch)
    now = datetime(2026, 6, 11, 0, 0, tzinfo=timezone.utc)
    started = (now - timedelta(hours=72)).isoformat()
    with database.connect() as conn:
        conn.execute(
            "INSERT INTO tasks(id, project_id, series_id, workflow_type, status, progress, log_path, created_at, started_at) VALUES(?,?,?,?,?,?,?,?,?)",
            (83, 1, 1, "dwi_qsirecon", "running", 20, str(tmp_path / "stale.log"), started, started),
        )

    report = stale_tasks.reconcile_stale_active_tasks(
        max_age_hours=24,
        apply=True,
        now=now,
        running_container_task_ids={83},
    )

    assert report["mode"] == "apply"
    assert report["blocked_task_ids"] == [83]
    assert report["updated_task_ids"] == []
    with database.connect() as conn:
        row = conn.execute("SELECT status, error_message FROM tasks WHERE id=83").fetchone()
    assert row["status"] == "running"
    assert row["error_message"] is None


def test_reconcile_stale_active_tasks_marks_old_task_failed_with_audit(tmp_path, monkeypatch):
    from app.workflows import stale_tasks

    _prepare_db(tmp_path, monkeypatch)
    now = datetime(2026, 6, 11, 0, 0, tzinfo=timezone.utc)
    started = (now - timedelta(hours=72)).isoformat()
    log_path = tmp_path / "task-83.log"
    with database.connect() as conn:
        conn.execute(
            "INSERT INTO tasks(id, project_id, series_id, workflow_type, status, progress, log_path, created_at, started_at) VALUES(?,?,?,?,?,?,?,?,?)",
            (83, 1, 1, "dwi_qsirecon", "running", 20, str(log_path), started, started),
        )

    report = stale_tasks.reconcile_stale_active_tasks(
        max_age_hours=24,
        apply=True,
        now=now,
        running_container_task_ids=set(),
        reason="operator confirmed no matching container",
    )

    assert report["updated_task_ids"] == [83]
    with database.connect() as conn:
        row = conn.execute("SELECT status, error_message, finished_at FROM tasks WHERE id=83").fetchone()
    assert row["status"] == "failed"
    assert "stale task reconciliation" in row["error_message"]
    assert "operator confirmed no matching container" in row["error_message"]
    assert row["finished_at"] == now.isoformat()
    assert "stale task reconciliation" in log_path.read_text(encoding="utf-8")
