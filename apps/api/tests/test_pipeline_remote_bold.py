import json

from app.workflows import pipeline


def _patch_bold_task(monkeypatch, tmp_path, *, remote_outputs):
    task = {
        "id": 44,
        "project_id": 7,
        "series_id": 11,
        "workflow_type": "bold_fmriprep_xcpd_report",
        "log_path": str(tmp_path / "44.log"),
    }
    series = {
        "id": 11,
        "project_id": 7,
        "file_id": 1,
        "modality": "BOLD",
        "metadata_json": "{}",
    }
    calls = []

    monkeypatch.setattr(pipeline, "_row", lambda sql, params=(): task if "FROM tasks" in sql else series)
    monkeypatch.setattr(pipeline, "_update", lambda task_id, **values: calls.append(("update", task_id, values)))
    monkeypatch.setattr(pipeline, "_build_bids", lambda task, series: {"root": tmp_path, "bids": tmp_path / "bids", "output": tmp_path / "output", "work": tmp_path / "work"})
    monkeypatch.setattr(pipeline, "_register_outputs", lambda task_id, output_dir: 3)
    monkeypatch.setattr(pipeline, "_insert_output", lambda *args, **kwargs: calls.append(("output", args, kwargs)))
    monkeypatch.setattr(
        pipeline,
        "run_bold_fmriprep_xcpd_remote",
        lambda *, task_id, bids_dir, output_dir, work_dir, log_path: {
            "ok": True,
            "outputs": remote_outputs,
            "scripts": ["run_fmriprep.sh", "run_xcpd_fmriprep.sh"],
        },
    )
    monkeypatch.setattr(pipeline, "_write_bold_fmriprep_xcpd_summary", lambda task_id, workflow_type, dirs, log_path: tmp_path / "summary.json")
    return calls


def test_pipeline_rejects_empty_remote_bold_outputs(monkeypatch, tmp_path):
    calls = _patch_bold_task(
        monkeypatch,
        tmp_path,
        remote_outputs={"reports": [], "tables": [], "metrics": [], "maps": []},
    )

    pipeline.run_pipeline_task(44)

    failed = [call for call in calls if call[0] == "update" and call[2].get("status") == "failed"]
    assert failed
    assert "completed without required artifacts" in failed[-1][2]["error_message"]


def test_pipeline_uses_remote_wrapper_for_bold_fmriprep_xcpd(monkeypatch, tmp_path):
    calls = _patch_bold_task(
        monkeypatch,
        tmp_path,
        remote_outputs={
            "reports": [{"path": str(tmp_path / "report.html")}],
            "tables": [{"path": str(tmp_path / "metrics.tsv")}],
            "metrics": [{"path": str(tmp_path / "metrics.json")}],
            "maps": [{"path": str(tmp_path / "map.nii.gz")}],
            "logs": [{"path": str(tmp_path / "fmriprep.log")}],
        },
    )

    pipeline.run_pipeline_task(44)

    assert any(call[0] == "update" and call[2].get("status") == "completed" for call in calls)


def test_bold_fmriprep_xcpd_summary_indexes_remote_logs(tmp_path):
    output = tmp_path / "output"
    (output / "logs").mkdir(parents=True)
    (output / "reports").mkdir()
    (output / "tables").mkdir()
    (output / "maps").mkdir()
    (output / "figures").mkdir()
    (output / "logs" / "fmriprep.log").write_text("fmriprep log", encoding="utf-8")
    (output / "logs" / "xcpd.log").write_text("xcpd log", encoding="utf-8")
    (output / "reports" / "index.html").write_text("<html></html>", encoding="utf-8")
    (output / "figures" / "qc.svg").write_text("<svg></svg>", encoding="utf-8")
    (output / "tables" / "metrics.tsv").write_text("metric\tvalue\n", encoding="utf-8")
    (output / "maps" / "map.nii.gz").write_bytes(b"nifti")

    summary_path = pipeline._write_bold_fmriprep_xcpd_summary(
        44,
        "bold_fmriprep_xcpd_report",
        {"output": output},
        tmp_path / "44.log",
    )

    payload = json.loads(summary_path.read_text(encoding="utf-8"))
    assert {item["name"] for item in payload["outputs"]["logs"]} == {"fmriprep.log", "xcpd.log"}
    assert all(item["relative_path"].startswith("logs/") for item in payload["outputs"]["logs"])
    assert payload["outputs"]["figures"][0]["artifact_role"] == "container_native_qc_figure"


def test_bold_fmriprep_xcpd_summary_registration_is_idempotent(monkeypatch, tmp_path):
    output = tmp_path / "output"
    (output / "logs").mkdir(parents=True)
    (output / "reports").mkdir()
    (output / "tables").mkdir()
    (output / "maps").mkdir()
    (output / "logs" / "xcpd_fmriprep.log").write_text("xcpd log", encoding="utf-8")
    (output / "reports" / "index.html").write_text("<html></html>", encoding="utf-8")
    (output / "tables" / "metrics.tsv").write_text("metric\tvalue\n", encoding="utf-8")
    (output / "maps" / "map.nii.gz").write_bytes(b"nifti")
    inserted = []
    monkeypatch.setattr(
        pipeline,
        "_rows",
        lambda sql, params=(): [
            {"id": 1}
        ]
        if "FROM outputs" in sql
        and (
            str(params[1]).endswith("bold_result_summary.json")
            or str(params[1]).endswith("bold_scientific_report_summary.json")
        )
        else [],
    )
    monkeypatch.setattr(pipeline, "_insert_output", lambda *args, **kwargs: inserted.append((args, kwargs)))

    pipeline._write_bold_fmriprep_xcpd_summary(44, "bold_fmriprep_xcpd_report", {"output": output}, tmp_path / "44.log")

    assert inserted == []


def test_pipeline_isolates_stale_workspace_before_fresh_task(monkeypatch, tmp_path):
    monkeypatch.setattr(pipeline, "PROJECTS_ROOT", tmp_path / "projects")
    task = {"id": 115, "project_id": 13}
    stale_root = pipeline.PROJECTS_ROOT / "13" / "derivatives" / "115"
    stale_file = stale_root / "output" / "old_report.html"
    stale_file.parent.mkdir(parents=True)
    stale_file.write_text("<html>old</html>", encoding="utf-8")
    monkeypatch.setattr(pipeline, "_rows", lambda sql, params=(): [])

    moved = pipeline._isolate_stale_task_workspace(task, tmp_path / "115.log")

    assert moved is not None
    assert not stale_root.exists()
    assert (moved / "output" / "old_report.html").exists()
    assert (pipeline.PROJECTS_ROOT / "13" / "derivatives" / "_stale_task_workspaces").exists()


def test_pipeline_keeps_registered_workspace(monkeypatch, tmp_path):
    monkeypatch.setattr(pipeline, "PROJECTS_ROOT", tmp_path / "projects")
    task = {"id": 115, "project_id": 13}
    root = pipeline.PROJECTS_ROOT / "13" / "derivatives" / "115"
    (root / "output").mkdir(parents=True)
    (root / "output" / "summary.json").write_text("{}", encoding="utf-8")
    monkeypatch.setattr(pipeline, "_rows", lambda sql, params=(): [{"id": 1}])

    moved = pipeline._isolate_stale_task_workspace(task, tmp_path / "115.log")

    assert moved is None
    assert root.exists()
