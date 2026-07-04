import json

from fastapi.testclient import TestClient

from app import main
from app.core import config
from app.db import database
from app.main import app
from app.workflows.task_logs import collect_remote_task_logs

from tests.test_api_flow import make_nifti


def test_collect_remote_task_logs_discovers_native_deepprep_logs(tmp_path):
    output_dir = tmp_path / "output"
    recon_log = output_dir / "Recon" / "sub-01" / "scripts" / "recon-all.log"
    nextflow_log = output_dir / "WorkDir" / "nextflow" / ".nextflow.log"
    recon_log.parent.mkdir(parents=True)
    nextflow_log.parent.mkdir(parents=True)
    recon_log.write_text("freesurfer progress\n", encoding="utf-8")
    nextflow_log.write_text("nextflow progress\n", encoding="utf-8")

    logs = collect_remote_task_logs(output_dir)

    by_name = {item["name"]: item for item in logs}
    assert by_name["recon-all.log"]["source_stage"] == "freesurfer"
    assert "freesurfer progress" in by_name["recon-all.log"]["tail"]
    assert by_name[".nextflow.log"]["size_bytes"] > 0


def test_task_events_include_nested_native_logs_without_path_leakage(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_ROOT", tmp_path)
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "app.db")
    monkeypatch.setattr(config, "PROJECTS_ROOT", tmp_path / "projects")
    monkeypatch.setattr(database, "DB_PATH", tmp_path / "app.db")
    monkeypatch.setattr(main, "PROJECTS_ROOT", tmp_path / "projects")

    database.init_db()
    client = TestClient(app)
    project = client.post("/projects", json={"name": "P-native-logs"}).json()
    nii = tmp_path / "sub-001_T1w.nii.gz"
    make_nifti(nii)
    with nii.open("rb") as f:
        series = client.post(
            f"/projects/{project['id']}/upload",
            files={"file": (nii.name, f, "application/gzip")},
        ).json()["series"]

    log_path = tmp_path / "projects" / str(project["id"]) / "logs" / "88.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text("task wrapper continued\n", encoding="utf-8")
    remote_log = (
        tmp_path
        / "projects"
        / str(project["id"])
        / "derivatives"
        / "88"
        / "output"
        / "Recon"
        / "sub-01"
        / "scripts"
        / "recon-all.log"
    )
    remote_log.parent.mkdir(parents=True, exist_ok=True)
    remote_log.write_text(
        "container wrote /home/yyf/project/image_agent/private-output\n"
        "native freesurfer continued\n",
        encoding="utf-8",
    )
    now = database.now_iso()
    with database.connect() as conn:
        conn.execute(
            "INSERT INTO tasks(id, project_id, series_id, workflow_type, status, progress, log_path, created_at, runtime_workflow_type) "
            "VALUES(?,?,?,?,?,?,?,?,?)",
            (
                88,
                project["id"],
                series["id"],
                "t1_deepprep_anat_report",
                "completed",
                100,
                str(log_path),
                now,
                "t1_deepprep",
            ),
        )

    payload = client.get("/tasks/88/events").json()
    serialized = json.dumps(payload)
    assert any(event["type"] == "task.remote_log" and event["source_stage"] == "freesurfer" for event in payload["events"])
    assert payload["remote_logs"][0]["name"] == "recon-all.log"
    assert "native freesurfer continued" in payload["remote_logs"][0]["tail"]
    assert "path" not in payload["remote_logs"][0]
    assert "/home/yyf/project/image_agent" not in serialized


def test_task_events_fall_back_to_main_log_when_no_native_logs(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_ROOT", tmp_path)
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "app.db")
    monkeypatch.setattr(config, "PROJECTS_ROOT", tmp_path / "projects")
    monkeypatch.setattr(database, "DB_PATH", tmp_path / "app.db")
    monkeypatch.setattr(main, "PROJECTS_ROOT", tmp_path / "projects")

    database.init_db()
    client = TestClient(app)
    project = client.post("/projects", json={"name": "P-main-log-fallback"}).json()
    nii = tmp_path / "sub-001_T1w.nii.gz"
    make_nifti(nii)
    with nii.open("rb") as f:
        series = client.post(
            f"/projects/{project['id']}/upload",
            files={"file": (nii.name, f, "application/gzip")},
        ).json()["series"]

    log_path = tmp_path / "projects" / str(project["id"]) / "logs" / "89.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text(
        "pipeline runner wrote /home/yyf/project/image_agent/private-output\n"
        "task wrapper completed\n",
        encoding="utf-8",
    )
    output_dir = tmp_path / "projects" / str(project["id"]) / "derivatives" / "89" / "output"
    output_dir.mkdir(parents=True, exist_ok=True)
    now = database.now_iso()
    with database.connect() as conn:
        conn.execute(
            "INSERT INTO tasks(id, project_id, series_id, workflow_type, status, progress, log_path, created_at, runtime_workflow_type) "
            "VALUES(?,?,?,?,?,?,?,?,?)",
            (
                89,
                project["id"],
                series["id"],
                "t1_deepprep_anat_report",
                "completed",
                100,
                str(log_path),
                now,
                "t1_deepprep",
            ),
        )

    payload = client.get("/tasks/89/events").json()
    serialized = json.dumps(payload)

    assert any(
        event["type"] == "task.remote_log" and event["source_stage"] == "pipeline_runner"
        for event in payload["events"]
    )
    assert payload["remote_logs"][0]["name"] == "task.log"
    assert "task wrapper completed" in payload["remote_logs"][0]["tail"]
    assert "path" not in payload["remote_logs"][0]
    assert "/home/yyf/project/image_agent" not in serialized
