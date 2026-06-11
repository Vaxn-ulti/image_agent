from datetime import datetime, timedelta, timezone
import importlib.util
import json
from pathlib import Path

from app.db import database

REPO_ROOT = Path(__file__).resolve().parents[3]


def _load_reconcile_cli():
    module_path = REPO_ROOT / "apps" / "api" / "scripts" / "reconcile_stale_tasks.py"
    spec = importlib.util.spec_from_file_location("reconcile_stale_tasks_cli", module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


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


def test_dry_run_can_report_running_container_blockers(tmp_path, monkeypatch):
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
        apply=False,
        now=now,
        running_container_task_ids={83},
        container_check_status="passed",
    )

    assert report["mode"] == "dry_run"
    assert report["container_check_status"] == "passed"
    assert report["running_container_task_ids"] == [83]
    assert report["blocked_task_ids"] == [83]
    assert report["stale_candidates"] == []


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


def test_reconcile_stale_active_tasks_can_scope_apply_to_task_ids(tmp_path, monkeypatch):
    from app.workflows import stale_tasks

    _prepare_db(tmp_path, monkeypatch)
    now = datetime(2026, 6, 11, 0, 0, tzinfo=timezone.utc)
    started = (now - timedelta(hours=72)).isoformat()
    with database.connect() as conn:
        for task_id in (83, 84):
            conn.execute(
                "INSERT INTO tasks(id, project_id, series_id, workflow_type, status, progress, log_path, created_at, started_at) VALUES(?,?,?,?,?,?,?,?,?)",
                (task_id, 1, 1, "dwi_qsirecon", "running", 20, str(tmp_path / f"task-{task_id}.log"), started, started),
            )

    report = stale_tasks.reconcile_stale_active_tasks(
        max_age_hours=24,
        apply=True,
        now=now,
        running_container_task_ids=set(),
        task_ids={83},
        reason="operator approved task 83 only",
    )

    assert report["updated_task_ids"] == [83]
    assert report["out_of_scope_stale_task_ids"] == [84]
    with database.connect() as conn:
        rows = conn.execute("SELECT id, status FROM tasks ORDER BY id").fetchall()
    assert [(row["id"], row["status"]) for row in rows] == [(83, "failed"), (84, "running")]


def test_cli_check_containers_keeps_dry_run_read_only(tmp_path, monkeypatch, capsys):
    _prepare_db(tmp_path, monkeypatch)
    now = datetime.now(timezone.utc)
    started = (now - timedelta(hours=72)).isoformat()
    with database.connect() as conn:
        conn.execute(
            "INSERT INTO tasks(id, project_id, series_id, workflow_type, status, progress, log_path, created_at, started_at) VALUES(?,?,?,?,?,?,?,?,?)",
            (83, 1, 1, "dwi_qsirecon", "running", 20, str(tmp_path / "stale.log"), started, started),
        )

    cli = _load_reconcile_cli()
    monkeypatch.setattr(cli, "running_container_task_ids_from_docker", lambda: {83})

    cli.main(["--max-age-hours", "24", "--check-containers"])

    report = json.loads(capsys.readouterr().out)
    assert report["mode"] == "dry_run"
    assert report["container_check_status"] == "passed"
    assert report["running_container_task_ids"] == [83]
    assert report["blocked_task_ids"] == [83]
    assert report["updated_task_ids"] == []
    with database.connect() as conn:
        row = conn.execute("SELECT status FROM tasks WHERE id=83").fetchone()
    assert row["status"] == "running"


def test_cli_task_id_scopes_dry_run_candidates(tmp_path, monkeypatch, capsys):
    _prepare_db(tmp_path, monkeypatch)
    now = datetime.now(timezone.utc)
    started = (now - timedelta(hours=72)).isoformat()
    with database.connect() as conn:
        for task_id in (83, 84):
            conn.execute(
                "INSERT INTO tasks(id, project_id, series_id, workflow_type, status, progress, log_path, created_at, started_at) VALUES(?,?,?,?,?,?,?,?,?)",
                (task_id, 1, 1, "dwi_qsirecon", "running", 20, str(tmp_path / f"task-{task_id}.log"), started, started),
            )

    cli = _load_reconcile_cli()
    monkeypatch.setattr(cli, "running_container_task_ids_from_docker", lambda: set())

    cli.main(["--max-age-hours", "24", "--check-containers", "--task-id", "83"])

    report = json.loads(capsys.readouterr().out)
    assert [task["id"] for task in report["stale_candidates"]] == [83]
    assert report["out_of_scope_stale_task_ids"] == [84]
    assert report["target_task_ids"] == [83]
    assert report["updated_task_ids"] == []


def test_dry_run_report_includes_stable_approval_fingerprint(tmp_path, monkeypatch):
    from app.workflows import stale_tasks

    _prepare_db(tmp_path, monkeypatch)
    now = datetime(2026, 6, 11, 0, 0, tzinfo=timezone.utc)
    started = (now - timedelta(hours=72)).isoformat()
    with database.connect() as conn:
        conn.execute(
            "INSERT INTO tasks(id, project_id, series_id, workflow_type, status, progress, log_path, created_at, started_at) VALUES(?,?,?,?,?,?,?,?,?)",
            (83, 1, 1, "dwi_qsirecon", "running", 20, str(tmp_path / "task-83.log"), started, started),
        )

    first = stale_tasks.reconcile_stale_active_tasks(
        max_age_hours=24,
        apply=False,
        now=now,
        running_container_task_ids=set(),
        task_ids={83},
    )
    later = stale_tasks.reconcile_stale_active_tasks(
        max_age_hours=24,
        apply=False,
        now=now + timedelta(minutes=5),
        running_container_task_ids=set(),
        task_ids={83},
    )

    assert len(first["approval_fingerprint"]) == 64
    assert first["approval_fingerprint"] == later["approval_fingerprint"]
    assert first["approval_payload"]["stale_candidate_ids"] == [83]
    assert first["approval_payload"]["running_container_task_ids"] == []


def test_apply_refuses_mismatched_approval_fingerprint_before_updates(tmp_path, monkeypatch):
    from app.workflows import stale_tasks

    _prepare_db(tmp_path, monkeypatch)
    now = datetime(2026, 6, 11, 0, 0, tzinfo=timezone.utc)
    started = (now - timedelta(hours=72)).isoformat()
    with database.connect() as conn:
        conn.execute(
            "INSERT INTO tasks(id, project_id, series_id, workflow_type, status, progress, log_path, created_at, started_at) VALUES(?,?,?,?,?,?,?,?,?)",
            (83, 1, 1, "dwi_qsirecon", "running", 20, str(tmp_path / "task-83.log"), started, started),
        )

    try:
        stale_tasks.reconcile_stale_active_tasks(
            max_age_hours=24,
            apply=True,
            now=now,
            running_container_task_ids=set(),
            task_ids={83},
            expected_approval_fingerprint="not-the-reviewed-fingerprint",
        )
    except ValueError as exc:
        assert "approval fingerprint mismatch" in str(exc)
    else:
        raise AssertionError("expected mismatched approval fingerprint to fail")

    with database.connect() as conn:
        row = conn.execute("SELECT status, error_message FROM tasks WHERE id=83").fetchone()
    assert row["status"] == "running"
    assert row["error_message"] is None
