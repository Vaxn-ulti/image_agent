from pathlib import Path

from app.core import config
from app.db import database
from app.schemas import RunRequest
from app.services import task_service


class RecordingExecutor:
    def __init__(self):
        self.plans = []

    def submit(self, plan):
        self.plans.append(plan)
        return {"executor": "celery", "celery_task_id": "celery-1", "queue": "image_agent_long", "task_id": plan.task_id}


def _seed_t1_series(projects_root: Path):
    projects_root.mkdir(parents=True, exist_ok=True)
    with database.connect() as conn:
        conn.execute("INSERT INTO projects(id, name, description, created_at) VALUES(?,?,?,?)", (7, "P", "", database.now_iso()))
        conn.execute(
            "INSERT INTO files(id, project_id, original_name, storage_path, file_type, size, sha256, created_at) "
            "VALUES(?,?,?,?,?,?,?,?)",
            (31, 7, "sub-01_T1w.nii.gz", str(projects_root / "7" / "sub-01_T1w.nii.gz"), "NIFTI", 100, "abc", database.now_iso()),
        )
        conn.execute(
            "INSERT INTO imaging_series(id, project_id, file_id, modality, format, confidence, metadata_json, status, created_at) "
            "VALUES(?,?,?,?,?,?,?,?,?)",
            (11, 7, 31, "T1", "NIFTI", 0.99, "{}", "ready", database.now_iso()),
        )


def test_create_series_task_submits_approved_execution_plan_instead_of_thread(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "app.db")
    monkeypatch.setattr(database, "DB_PATH", tmp_path / "app.db")
    monkeypatch.setattr(config, "PROJECTS_ROOT", tmp_path / "projects")
    import app.main as main

    monkeypatch.setattr(main, "PROJECTS_ROOT", tmp_path / "projects")
    database.init_db()
    _seed_t1_series(tmp_path / "projects")
    executor = RecordingExecutor()
    monkeypatch.setattr(task_service, "get_task_executor", lambda: executor, raising=False)

    def fail_if_threaded(*args, **kwargs):
        raise AssertionError("create_series_task must submit through TaskExecutor, not submit_background")

    monkeypatch.setattr(task_service, "submit_background", fail_if_threaded, raising=False)

    task = task_service.create_series_task(
        11,
        RunRequest(workflow_type="t1_deepprep_anat_report", runtime_workflow_type="t1_deepprep"),
        confirmed_agent_gate=True,
    )

    assert task["status"] == "queued"
    assert len(executor.plans) == 1
    plan = executor.plans[0]
    assert plan.project_id == 7
    assert plan.series_id == 11
    assert plan.task_id == task["id"]
    assert plan.workflow_type == "t1_deepprep_anat_report"
    assert plan.runtime_workflow_type == "t1_deepprep"
    assert plan.confirmation_id == "agent_confirmed_gate"
    with database.connect() as conn:
        run = conn.execute("SELECT task_id, status, queue, celery_task_id FROM execution_runs WHERE task_id=?", (task["id"],)).fetchone()
        events = conn.execute(
            "SELECT event_type, status FROM execution_events WHERE task_id=? ORDER BY id",
            (task["id"],),
        ).fetchall()

    assert dict(run) == {"task_id": task["id"], "status": "queued", "queue": "image_agent_long", "celery_task_id": "celery-1"}
    assert [dict(event) for event in events] == [
        {"event_type": "execution.plan_approved", "status": "approved"},
        {"event_type": "execution.queued", "status": "queued"},
    ]
