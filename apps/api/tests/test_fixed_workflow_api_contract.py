import json
import gzip
import struct
from pathlib import Path

import nibabel as nib
import numpy as np
from fastapi.testclient import TestClient

from app.core import config
from app.main import app


def _write_minimal_nifti(path: Path, shape=(8, 8, 8, 3)) -> None:
    header = bytearray(348)
    struct.pack_into("<i", header, 0, 348)
    dims = [len(shape), *shape, *([1] * (7 - len(shape)))]
    struct.pack_into("<8h", header, 40, *dims)
    struct.pack_into("<h", header, 70, 16)
    struct.pack_into("<h", header, 72, 32)
    struct.pack_into("<8f", header, 76, 0.0, 1.0, 1.0, 1.2, 1.0, 0.0, 0.0, 0.0)
    header[344:348] = b"n+1\0"
    if path.name.endswith(".gz"):
        with gzip.open(path, "wb") as f:
            f.write(header)
    else:
        path.write_bytes(header)


def test_workflow_catalog_exposes_fixed_production_entries():
    client = TestClient(app)
    workflows = client.get("/workflows").json()["workflows"]
    workflow_types = {item["type"] for item in workflows}
    workflow_labels = {item["type"]: item["label"] for item in workflows}

    assert "bold_second_level" in workflow_types
    assert "bold_second_level_validate" in workflow_types
    assert "dwi_fast_gpu_dti" in workflow_types
    assert "dwi_fast_gpu_dti_validate" in workflow_types
    assert workflow_labels["bold_second_level"] == "BOLD downstream metrics (single subject)"


def test_workflow_catalog_exposes_display_metadata_without_renaming_workflow_type():
    client = TestClient(app)
    workflows = client.get("/workflows").json()["workflows"]
    workflow = next(item for item in workflows if item["type"] == "bold_fmriprep_xcpd_report")

    assert workflow["type"] == "bold_fmriprep_xcpd_report"
    assert workflow["type"] != workflow["display_name"]
    assert workflow["display_name"] == "BOLD fMRIPrep + XCP-D processing, metrics, QC, and report"
    assert workflow["workflow_family"] == "bold"
    assert workflow["workflow_role"] == "complete_processing"
    assert workflow["capability_summary"]
    assert [stage["name"] for stage in workflow["pipeline_stages"]] == [
        "BIDS preparation",
        "fMRIPrep preprocessing",
        "XCP-D postprocessing",
        "result packaging",
    ]
    assert "preprocessed BOLD derivatives" in workflow["primary_outputs"]
    assert "container-native fMRIPrep and XCP-D QC artifacts" in workflow["qc_outputs"]
    assert "HTML scientific report" in workflow["report_outputs"]
    assert workflow["limitations"]
    assert workflow["is_report_only"] is False


def test_user_facing_frontends_launch_workflows_through_agent_confirmation():
    repo_root = Path(__file__).resolve().parents[3]
    checked_sources = {
        "apps/console/src/routes/DashboardPage.tsx": repo_root / "apps" / "console" / "src" / "routes" / "DashboardPage.tsx",
        "apps/console/src/routes/WorkflowsPage.tsx": repo_root / "apps" / "console" / "src" / "routes" / "WorkflowsPage.tsx",
        "apps/desktop/src/main.jsx": repo_root / "apps" / "desktop" / "src" / "main.jsx",
        "apps/desktop/src/lib/api.js": repo_root / "apps" / "desktop" / "src" / "lib" / "api.js",
    }
    for label, path in checked_sources.items():
        source = path.read_text(encoding="utf-8")
        assert "/series/${" not in source, f"{label} must not call the direct /series/{{series_id}}/run endpoint"
        assert "api.runSeries" not in source, f"{label} must not bypass Agent confirmation through api.runSeries"

    assert "api.runAgent" in checked_sources["apps/console/src/routes/DashboardPage.tsx"].read_text(encoding="utf-8")
    assert "api.resumeAgent" in checked_sources["apps/console/src/routes/DashboardPage.tsx"].read_text(encoding="utf-8")
    assert "api.runAgent" in checked_sources["apps/console/src/routes/WorkflowsPage.tsx"].read_text(encoding="utf-8")
    assert "api.resumeAgent" in checked_sources["apps/console/src/routes/WorkflowsPage.tsx"].read_text(encoding="utf-8")
    assert "runAgent" in checked_sources["apps/desktop/src/lib/api.js"].read_text(encoding="utf-8")
    assert "resumeAgent" in checked_sources["apps/desktop/src/lib/api.js"].read_text(encoding="utf-8")


def test_result_summary_endpoint_loads_registered_summary(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_ROOT", tmp_path)
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "app.db")
    monkeypatch.setattr(config, "PROJECTS_ROOT", tmp_path / "projects")
    from app.db import database
    import app.main as main

    monkeypatch.setattr(database, "DB_PATH", tmp_path / "app.db")
    monkeypatch.setattr(main, "PROJECTS_ROOT", tmp_path / "projects")

    database.init_db()
    summary = tmp_path / "projects" / "1" / "derivatives" / "4" / "output" / "summary" / "t1_result_summary.json"
    summary.parent.mkdir(parents=True)
    summary.write_text(
        json.dumps(
            {
                "contract_version": "1.0",
                "task_id": 4,
                "workflow_type": "t1_deepprep",
                "modality": "T1",
                "spaces": ["T1w", "MNI152"],
                "feature_groups": [],
                "outputs": {},
                "provenance": {},
            }
        ),
        encoding="utf-8",
    )
    with database.connect() as conn:
        conn.execute("INSERT INTO projects(id, name, description, created_at) VALUES(?,?,?,?)", (1, "P", "", database.now_iso()))
        conn.execute(
            "INSERT INTO files(id, project_id, original_name, storage_path, file_type, size, sha256, created_at) VALUES(?,?,?,?,?,?,?,?)",
            (1, 1, "t1.nii.gz", str(tmp_path / "t1.nii.gz"), "NIFTI", 1, "x", database.now_iso()),
        )
        conn.execute(
            "INSERT INTO imaging_series(id, project_id, file_id, sequence_label, supported_for_processing, unsupported_reason, modality, format, confidence, metadata_json, status, created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
            (1, 1, 1, "T1_MPRAGE", 1, "", "T1", "NIFTI", 0.9, "{}", "detected", database.now_iso()),
        )
        conn.execute(
            "INSERT INTO tasks(id, project_id, series_id, workflow_type, status, progress, log_path, created_at) VALUES(?,?,?,?,?,?,?,?)",
            (4, 1, 1, "t1_deepprep", "completed", 100, str(tmp_path / "4.log"), database.now_iso()),
        )
        conn.execute(
            "INSERT INTO outputs(task_id, output_type, path, preview_path, metadata_json, created_at) VALUES(?,?,?,?,?,?)",
            (4, "json", str(summary), None, json.dumps({"kind": "result_summary"}), database.now_iso()),
        )

    result = TestClient(app).get("/tasks/4/result-summary")

    assert result.status_code == 200
    assert result.json()["spaces"] == ["T1w", "MNI152"]


def test_result_summary_endpoint_overrides_stale_workflow_metadata_with_registry(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_ROOT", tmp_path)
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "app.db")
    monkeypatch.setattr(config, "PROJECTS_ROOT", tmp_path / "projects")
    from app.db import database
    import app.main as main

    monkeypatch.setattr(database, "DB_PATH", tmp_path / "app.db")
    monkeypatch.setattr(main, "PROJECTS_ROOT", tmp_path / "projects")

    database.init_db()
    summary = tmp_path / "projects" / "1" / "derivatives" / "44" / "output" / "summary" / "t1_result_summary.json"
    summary.parent.mkdir(parents=True)
    summary.write_text(
        json.dumps(
            {
                "contract_version": "1.0",
                "task_id": 44,
                "workflow_type": "t1_deepprep",
                "modality": "T1",
                "spaces": ["T1w"],
                "feature_groups": [],
                "outputs": {},
                "provenance": {},
                "workflow_metadata": {
                    "workflow_type": "t1_deepprep",
                    "runtime_workflow_type": "t1_deepprep",
                    "display_name": "t1_deepprep",
                    "is_report_only": True,
                },
            }
        ),
        encoding="utf-8",
    )
    with database.connect() as conn:
        conn.execute("INSERT INTO projects(id, name, description, created_at) VALUES(?,?,?,?)", (1, "P", "", database.now_iso()))
        conn.execute(
            "INSERT INTO files(id, project_id, original_name, storage_path, file_type, size, sha256, created_at) VALUES(?,?,?,?,?,?,?,?)",
            (1, 1, "t1.nii.gz", str(tmp_path / "t1.nii.gz"), "NIFTI", 1, "x", database.now_iso()),
        )
        conn.execute(
            "INSERT INTO imaging_series(id, project_id, file_id, sequence_label, supported_for_processing, unsupported_reason, modality, format, confidence, metadata_json, status, created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
            (1, 1, 1, "T1_MPRAGE", 1, "", "T1", "NIFTI", 0.9, "{}", "detected", database.now_iso()),
        )
        conn.execute(
            "INSERT INTO tasks(id, project_id, series_id, workflow_type, runtime_workflow_type, status, progress, log_path, created_at) VALUES(?,?,?,?,?,?,?,?,?)",
            (44, 1, 1, "t1_deepprep_anat_report", "t1_deepprep", "completed", 100, str(tmp_path / "44.log"), database.now_iso()),
        )
        conn.execute(
            "INSERT INTO outputs(task_id, output_type, path, preview_path, metadata_json, created_at) VALUES(?,?,?,?,?,?)",
            (44, "json", str(summary), None, json.dumps({"kind": "result_summary"}), database.now_iso()),
        )

    result = TestClient(app).get("/tasks/44/result-summary")

    assert result.status_code == 200
    metadata = result.json()["workflow_metadata"]
    assert metadata["workflow_type"] == "t1_deepprep_anat_report"
    assert metadata["runtime_workflow_type"] == "t1_deepprep"
    assert metadata["display_name"] == "T1 DeepPrep anatomical processing, QC, and report"
    assert metadata["workflow_type"] != metadata["display_name"]
    assert metadata["is_report_only"] is False
    assert metadata["primary_outputs"]
    assert metadata["qc_outputs"]
    assert metadata["report_outputs"]


def test_result_summary_endpoint_prefers_unified_summary_over_bold_metrics_legacy(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_ROOT", tmp_path)
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "app.db")
    monkeypatch.setattr(config, "PROJECTS_ROOT", tmp_path / "projects")
    from app.db import database
    import app.main as main

    monkeypatch.setattr(database, "DB_PATH", tmp_path / "app.db")
    monkeypatch.setattr(main, "PROJECTS_ROOT", tmp_path / "projects")

    database.init_db()
    output_dir = tmp_path / "projects" / "1" / "derivatives" / "5" / "output"
    legacy = output_dir / "sub-01_task-rest_desc-bold_metrics_summary.json"
    unified = output_dir / "summary" / "bold_result_summary.json"
    unified.parent.mkdir(parents=True)
    legacy.write_text(json.dumps({"modality": "BOLD", "spaces": ["MNI152"], "legacy": True}), encoding="utf-8")
    unified.write_text(
        json.dumps(
            {
                "contract_version": "1.0",
                "task_id": 5,
                "workflow_type": "bold_second_level",
                "modality": "BOLD",
                "spaces": ["MNI152"],
                "feature_groups": ["voxelwise_metrics", "connectivity"],
                "outputs": {},
                "provenance": {"seed_count": 15},
            }
        ),
        encoding="utf-8",
    )
    with database.connect() as conn:
        conn.execute("INSERT INTO projects(id, name, description, created_at) VALUES(?,?,?,?)", (1, "P", "", database.now_iso()))
        conn.execute(
            "INSERT INTO files(id, project_id, original_name, storage_path, file_type, size, sha256, created_at) VALUES(?,?,?,?,?,?,?,?)",
            (1, 1, "bold.nii.gz", str(tmp_path / "bold.nii.gz"), "NIFTI", 1, "x", database.now_iso()),
        )
        conn.execute(
            "INSERT INTO imaging_series(id, project_id, file_id, sequence_label, supported_for_processing, unsupported_reason, modality, format, confidence, metadata_json, status, created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
            (1, 1, 1, "BOLD", 1, "", "BOLD", "NIFTI", 0.9, "{}", "detected", database.now_iso()),
        )
        conn.execute(
            "INSERT INTO tasks(id, project_id, series_id, workflow_type, status, progress, log_path, created_at) VALUES(?,?,?,?,?,?,?,?)",
            (5, 1, 1, "bold_second_level", "completed", 100, str(tmp_path / "5.log"), database.now_iso()),
        )
        conn.execute(
            "INSERT INTO outputs(task_id, output_type, path, preview_path, metadata_json, created_at) VALUES(?,?,?,?,?,?)",
            (5, "json", str(legacy), None, json.dumps({"kind": "bold_metrics_summary"}), database.now_iso()),
        )
        conn.execute(
            "INSERT INTO outputs(task_id, output_type, path, preview_path, metadata_json, created_at) VALUES(?,?,?,?,?,?)",
            (5, "json", str(unified), None, json.dumps({"kind": "result_summary", "modality": "BOLD"}), database.now_iso()),
        )

    result = TestClient(app).get("/tasks/5/result-summary")

    assert result.status_code == 200
    payload = result.json()
    assert payload["feature_groups"] == ["voxelwise_metrics", "connectivity"]
    assert payload["provenance"]["seed_count"] == 15
    assert "legacy" not in payload


def test_agent_rag_status_endpoint_reports_grounding_policy():
    result = TestClient(app).get("/agent/rag/status")

    assert result.status_code == 200
    payload = result.json()
    assert payload["grounding_policy"]["source_priority"][0] == "backend_task_records"
    assert "langgraph" in payload["dependencies"]


def test_result_contract_endpoint_documents_frontend_contract():
    result = TestClient(app).get("/result-contract")

    assert result.status_code == 200
    payload = result.json()
    assert payload["contract_version"] == "1.0"
    assert payload["summary_endpoint"] == "/tasks/{task_id}/result-summary"
    assert payload["artifact_manifest_endpoint"] == "/tasks/{task_id}/artifact-manifest"
    assert "download_url" in payload["output_item_fields"]["required"]
    assert payload["modalities"]["T1"]["spaces"] == ["T1w", "MNI152"]


def test_task_logs_endpoint_includes_remote_wrapper_logs(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_ROOT", tmp_path)
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "app.db")
    monkeypatch.setattr(config, "PROJECTS_ROOT", tmp_path / "projects")
    from app.db import database
    import app.main as main

    monkeypatch.setattr(database, "DB_PATH", tmp_path / "app.db")
    monkeypatch.setattr(main, "PROJECTS_ROOT", tmp_path / "projects")

    database.init_db()
    main_log = tmp_path / "projects" / "1" / "logs" / "118.log"
    remote_log_dir = tmp_path / "projects" / "1" / "derivatives" / "118" / "output" / "logs"
    main_log.parent.mkdir(parents=True)
    remote_log_dir.mkdir(parents=True)
    main_log.write_text("main task log\n", encoding="utf-8")
    (remote_log_dir / "fmriprep.log").write_text("fmriprep progress\n" * 3, encoding="utf-8")
    (remote_log_dir / "xcpd_fmriprep.log").write_text("xcp-d progress\n", encoding="utf-8")
    with database.connect() as conn:
        conn.execute("INSERT INTO projects(id, name, description, created_at) VALUES(?,?,?,?)", (1, "P", "", database.now_iso()))
        conn.execute(
            "INSERT INTO files(id, project_id, original_name, storage_path, file_type, size, sha256, created_at) VALUES(?,?,?,?,?,?,?,?)",
            (1, 1, "bold.nii.gz", str(tmp_path / "bold.nii.gz"), "NIFTI", 1, "x", database.now_iso()),
        )
        conn.execute(
            "INSERT INTO imaging_series(id, project_id, file_id, sequence_label, supported_for_processing, unsupported_reason, modality, format, confidence, metadata_json, status, created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
            (1, 1, 1, "BOLD", 1, "", "BOLD", "NIFTI", 0.9, "{}", "detected", database.now_iso()),
        )
        conn.execute(
            "INSERT INTO tasks(id, project_id, series_id, workflow_type, status, progress, log_path, created_at) VALUES(?,?,?,?,?,?,?,?)",
            (118, 1, 1, "bold_fmriprep_xcpd_report", "running", 20, str(main_log), database.now_iso()),
        )

    payload = TestClient(app).get("/tasks/118/logs").json()

    assert payload["text"] == "main task log\n"
    assert payload["remote_logs"][0]["name"] == "fmriprep.log"
    assert "fmriprep progress" in payload["remote_logs"][0]["tail"]
    stages = {item["name"]: item["source_stage"] for item in payload["remote_logs"]}
    assert stages["fmriprep.log"] == "fmriprep"
    assert stages["xcpd_fmriprep.log"] == "xcpd"
    assert "log_paths" not in payload
    assert all("path" not in item for item in payload["remote_logs"])


def test_pipeline_command_outputs_get_metadata_file_path(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_ROOT", tmp_path)
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "app.db")
    monkeypatch.setattr(config, "PROJECTS_ROOT", tmp_path / "projects")
    from app.db import database
    from app.workflows import pipeline
    import app.main as main

    monkeypatch.setattr(database, "DB_PATH", tmp_path / "app.db")
    monkeypatch.setattr(main, "PROJECTS_ROOT", tmp_path / "projects")
    monkeypatch.setattr(pipeline, "PROJECTS_ROOT", tmp_path / "projects")

    database.init_db()
    with database.connect() as conn:
        conn.execute("INSERT INTO projects(id, name, description, created_at) VALUES(?,?,?,?)", (1, "P", "", database.now_iso()))
        conn.execute(
            "INSERT INTO files(id, project_id, original_name, storage_path, file_type, size, sha256, created_at) VALUES(?,?,?,?,?,?,?,?)",
            (1, 1, "dwi.nii.gz", str(tmp_path / "dwi.nii.gz"), "NIFTI", 1, "x", database.now_iso()),
        )
        conn.execute(
            "INSERT INTO imaging_series(id, project_id, file_id, sequence_label, supported_for_processing, unsupported_reason, modality, format, confidence, metadata_json, status, created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
            (1, 1, 1, "DWI", 1, "", "DWI", "NIFTI", 0.9, "{}", "detected", database.now_iso()),
        )
        conn.execute(
            "INSERT INTO tasks(id, project_id, series_id, workflow_type, status, progress, log_path, created_at) VALUES(?,?,?,?,?,?,?,?)",
            (6, 1, 1, "dwi_fast_gpu_dti_validate", "completed", 100, str(tmp_path / "6.log"), database.now_iso()),
        )

    pipeline._insert_output(6, "command", None, {"commands": []})
    with database.connect() as conn:
        output = conn.execute("SELECT * FROM outputs WHERE task_id=6").fetchone()
    output_path = Path(output["path"])

    assert output_path.name == "command_output.json"
    assert output_path.exists()
    assert json.loads(output_path.read_text(encoding="utf-8"))["commands"] == []


def test_result_summary_endpoint_wraps_legacy_bold_summary(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_ROOT", tmp_path)
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "app.db")
    monkeypatch.setattr(config, "PROJECTS_ROOT", tmp_path / "projects")
    from app.db import database
    import app.main as main

    monkeypatch.setattr(database, "DB_PATH", tmp_path / "app.db")
    monkeypatch.setattr(main, "PROJECTS_ROOT", tmp_path / "projects")

    database.init_db()
    output_dir = tmp_path / "projects" / "1" / "derivatives" / "7" / "output"
    output_dir.mkdir(parents=True)
    legacy = output_dir / "sub-01_task-rest_desc-bold_metrics_summary.json"
    legacy.write_text(
        json.dumps({"modality": "BOLD", "spaces": ["MNI152"], "metrics": ["alff"], "outputs": {"alff": "file.nii.gz"}}),
        encoding="utf-8",
    )
    with database.connect() as conn:
        conn.execute("INSERT INTO projects(id, name, description, created_at) VALUES(?,?,?,?)", (1, "P", "", database.now_iso()))
        conn.execute(
            "INSERT INTO files(id, project_id, original_name, storage_path, file_type, size, sha256, created_at) VALUES(?,?,?,?,?,?,?,?)",
            (1, 1, "bold.nii.gz", str(tmp_path / "bold.nii.gz"), "NIFTI", 1, "x", database.now_iso()),
        )
        conn.execute(
            "INSERT INTO imaging_series(id, project_id, file_id, sequence_label, supported_for_processing, unsupported_reason, modality, format, confidence, metadata_json, status, created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
            (1, 1, 1, "BOLD", 1, "", "BOLD", "NIFTI", 0.9, "{}", "detected", database.now_iso()),
        )
        conn.execute(
            "INSERT INTO tasks(id, project_id, series_id, workflow_type, status, progress, log_path, created_at) VALUES(?,?,?,?,?,?,?,?)",
            (7, 1, 1, "bold_second_level", "completed", 100, str(tmp_path / "7.log"), database.now_iso()),
        )
        conn.execute(
            "INSERT INTO outputs(task_id, output_type, path, preview_path, metadata_json, created_at) VALUES(?,?,?,?,?,?)",
            (7, "json", str(legacy), None, json.dumps({"kind": "bold_metrics_summary"}), database.now_iso()),
        )

    result = TestClient(app).get("/tasks/7/result-summary")

    assert result.status_code == 200
    payload = result.json()
    assert payload["feature_groups"] == ["legacy_bold_metrics"]
    assert payload["provenance"]["legacy_fallback"] is True
    assert payload["legacy_summary"]["metrics"] == ["alff"]


def test_task_artifact_endpoint_serves_files_inside_output_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_ROOT", tmp_path)
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "app.db")
    monkeypatch.setattr(config, "PROJECTS_ROOT", tmp_path / "projects")
    from app.db import database
    import app.main as main

    monkeypatch.setattr(database, "DB_PATH", tmp_path / "app.db")
    monkeypatch.setattr(main, "PROJECTS_ROOT", tmp_path / "projects")

    database.init_db()
    artifact = tmp_path / "projects" / "1" / "derivatives" / "8" / "output" / "tables" / "regions.tsv"
    artifact.parent.mkdir(parents=True)
    artifact.write_text("region\tvalue\nr\t1\n", encoding="utf-8")
    nifti_artifact = artifact.parents[1] / "maps" / "fa.nii.gz"
    nifti_artifact.parent.mkdir()
    nifti_artifact.write_bytes(b"fake-gzip-nifti")
    report_png = artifact.parents[1] / "reports" / "figure.png"
    report_png.parent.mkdir()
    report_png.write_bytes(b"\x89PNG\r\n\x1a\n")
    report_html = report_png.parent / "index.html"
    report_html.write_text("<html></html>", encoding="utf-8")
    with database.connect() as conn:
        conn.execute("INSERT INTO projects(id, name, description, created_at) VALUES(?,?,?,?)", (1, "P", "", database.now_iso()))
        conn.execute(
            "INSERT INTO files(id, project_id, original_name, storage_path, file_type, size, sha256, created_at) VALUES(?,?,?,?,?,?,?,?)",
            (1, 1, "t1.nii.gz", str(tmp_path / "t1.nii.gz"), "NIFTI", 1, "x", database.now_iso()),
        )
        conn.execute(
            "INSERT INTO imaging_series(id, project_id, file_id, sequence_label, supported_for_processing, unsupported_reason, modality, format, confidence, metadata_json, status, created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
            (1, 1, 1, "T1", 1, "", "T1", "NIFTI", 0.9, "{}", "detected", database.now_iso()),
        )
        conn.execute(
            "INSERT INTO tasks(id, project_id, series_id, workflow_type, status, progress, log_path, created_at) VALUES(?,?,?,?,?,?,?,?)",
            (8, 1, 1, "t1_deepprep", "completed", 100, str(tmp_path / "8.log"), database.now_iso()),
        )

    client = TestClient(app)
    result = client.get("/tasks/8/artifacts/tables/regions.tsv")
    nifti_result = client.get("/tasks/8/artifacts/maps/fa.nii.gz")
    png_result = client.get("/tasks/8/artifacts/reports/figure.png")
    html_result = client.get("/tasks/8/artifacts/reports/index.html")
    outside = client.get("/tasks/8/artifacts/../secret.txt")

    assert result.status_code == 200
    assert "region\tvalue" in result.text
    assert nifti_result.status_code == 200
    assert nifti_result.headers["content-type"] == "application/gzip"
    assert png_result.status_code == 200
    assert png_result.headers["content-type"].startswith("image/png")
    assert html_result.status_code == 200
    assert html_result.headers["content-type"].startswith("text/html")
    assert outside.status_code in {400, 404}


def test_task_artifact_manifest_lists_previewable_result_summary_artifacts(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_ROOT", tmp_path)
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "app.db")
    monkeypatch.setattr(config, "PROJECTS_ROOT", tmp_path / "projects")
    from app.db import database
    import app.main as main

    monkeypatch.setattr(database, "DB_PATH", tmp_path / "app.db")
    monkeypatch.setattr(main, "PROJECTS_ROOT", tmp_path / "projects")

    database.init_db()
    output_dir = tmp_path / "projects" / "1" / "derivatives" / "9" / "output"
    report = output_dir / "reports" / "index.html"
    figure = output_dir / "qc" / "figures" / "fa_native_qc.png"
    table = output_dir / "tables" / "regions.tsv"
    nifti = output_dir / "maps" / "fa.nii.gz"
    summary = output_dir / "summary" / "dwi_result_summary.json"
    for path, content in (
        (report, "<html></html>"),
        (figure, "png"),
        (table, "region\tvalue\n"),
        (nifti, "nifti"),
    ):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    summary.parent.mkdir(parents=True)
    summary.write_text(
        json.dumps(
            {
                "contract_version": "1.0",
                "task_id": 9,
                "workflow_type": "dwi_fast_gpu_dti",
                "modality": "DWI",
                "spaces": ["DWI", "MNI152"],
                "feature_groups": ["quality_control"],
                "workflow_metadata": {
                    "workflow_type": "dwi_report_only",
                    "runtime_workflow_type": "dwi_report_only",
                    "display_name": "dwi_report_only",
                    "is_report_only": True,
                },
                "outputs": {
                    "reports": [
                        {
                            "name": "index.html",
                            "path": str(report),
                            "relative_path": "reports/index.html",
                            "download_url": "/tasks/9/artifacts/reports/index.html",
                            "content_type": "text/html",
                            "size_bytes": report.stat().st_size,
                            "exists": True,
                            "artifact_role": "container_native_html_report",
                            "native_artifact": True,
                            "source_stage": "dwi_fast_dti",
                            "official_source_ids": ["docs/rag/vendor/fsl_official_fast_dti_tools.md"],
                        }
                    ],
                    "figures": [
                        {
                            "name": "fa_native_qc.png",
                            "path": str(figure),
                            "relative_path": "qc/figures/fa_native_qc.png",
                            "download_url": "/tasks/9/artifacts/qc/figures/fa_native_qc.png",
                            "content_type": "image/png",
                            "size_bytes": figure.stat().st_size,
                            "exists": True,
                            "artifact_role": "container_native_qc_figure",
                            "native_artifact": True,
                            "source_stage": "dwi_fast_dti",
                        }
                    ],
                    "tables": [
                        {
                            "name": "regions.tsv",
                            "path": str(table),
                            "relative_path": "tables/regions.tsv",
                            "download_url": "/tasks/9/artifacts/tables/regions.tsv",
                            "content_type": "text/tab-separated-values",
                            "size_bytes": table.stat().st_size,
                            "exists": True,
                        }
                    ],
                    "maps": [
                        {
                            "name": "fa.nii.gz",
                            "path": str(nifti),
                            "relative_path": "maps/fa.nii.gz",
                            "download_url": "/tasks/9/artifacts/maps/fa.nii.gz",
                            "content_type": "application/gzip",
                            "size_bytes": nifti.stat().st_size,
                            "exists": True,
                        }
                    ],
                },
                "provenance": {"placeholder_outputs": False},
            }
        ),
        encoding="utf-8",
    )
    with database.connect() as conn:
        conn.execute("INSERT INTO projects(id, name, description, created_at) VALUES(?,?,?,?)", (1, "P", "", database.now_iso()))
        conn.execute(
            "INSERT INTO files(id, project_id, original_name, storage_path, file_type, size, sha256, created_at) VALUES(?,?,?,?,?,?,?,?)",
            (1, 1, "dwi.nii.gz", str(tmp_path / "dwi.nii.gz"), "NIFTI", 1, "x", database.now_iso()),
        )
        conn.execute(
            "INSERT INTO imaging_series(id, project_id, file_id, sequence_label, supported_for_processing, unsupported_reason, modality, format, confidence, metadata_json, status, created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
            (1, 1, 1, "DWI", 1, "", "DWI", "NIFTI", 0.9, "{}", "detected", database.now_iso()),
        )
        conn.execute(
            "INSERT INTO tasks(id, project_id, series_id, workflow_type, status, progress, log_path, created_at) VALUES(?,?,?,?,?,?,?,?)",
            (9, 1, 1, "dwi_fast_gpu_dti", "completed", 100, str(tmp_path / "9.log"), database.now_iso()),
        )
        conn.execute(
            "INSERT INTO outputs(task_id, output_type, path, preview_path, metadata_json, created_at) VALUES(?,?,?,?,?,?)",
            (9, "json", str(summary), None, json.dumps({"kind": "result_summary"}), database.now_iso()),
        )

    payload = TestClient(app).get("/tasks/9/artifact-manifest").json()

    assert payload["contract_version"] == "artifact_manifest_v1"
    assert payload["task_id"] == 9
    assert payload["workflow_type"] == "dwi_fast_gpu_dti"
    assert payload["runtime_workflow_type"] == "dwi_fast_gpu_dti"
    assert payload["workflow_metadata"]["workflow_type"] == "dwi_fast_gpu_dti"
    assert payload["workflow_metadata"]["display_name"] == "DWI fast GPU DTI maps, atlas metrics, QC, and report"
    assert payload["workflow_metadata"]["workflow_type"] != payload["workflow_metadata"]["display_name"]
    assert payload["workflow_metadata"]["is_report_only"] is False
    assert payload["workflow_metadata"]["primary_outputs"]
    assert payload["workflow_metadata"]["qc_outputs"]
    assert payload["workflow_metadata"]["report_outputs"]
    assert payload["modality"] == "DWI"
    assert payload["result_summary"]["available"] is True
    assert payload["result_summary"]["summary_path"] == "summary/dwi_result_summary.json"
    assert payload["counts_by_section"] == {"reports": 1, "figures": 1, "tables": 1, "maps": 1}
    items = {item["relative_path"]: item for item in payload["artifacts"]}
    assert items["reports/index.html"]["preview_kind"] == "html"
    assert items["qc/figures/fa_native_qc.png"]["preview_kind"] == "image"
    assert items["tables/regions.tsv"]["preview_kind"] == "table"
    assert items["maps/fa.nii.gz"]["preview_kind"] == "download"
    assert items["reports/index.html"]["download_url"] == "/tasks/9/artifacts/reports/index.html"
    assert "path" not in items["reports/index.html"]
    assert items["reports/index.html"]["official_source_ids"] == ["docs/rag/vendor/fsl_official_fast_dti_tools.md"]


def test_task_artifact_manifest_omits_unsafe_or_missing_artifacts(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_ROOT", tmp_path)
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "app.db")
    monkeypatch.setattr(config, "PROJECTS_ROOT", tmp_path / "projects")
    from app.db import database
    import app.main as main

    monkeypatch.setattr(database, "DB_PATH", tmp_path / "app.db")
    monkeypatch.setattr(main, "PROJECTS_ROOT", tmp_path / "projects")

    database.init_db()
    output_dir = tmp_path / "projects" / "1" / "derivatives" / "10" / "output"
    valid = output_dir / "reports" / "index.html"
    missing = output_dir / "reports" / "missing.html"
    outside = tmp_path / "secret.html"
    summary = output_dir / "summary" / "t1_result_summary.json"
    valid.parent.mkdir(parents=True, exist_ok=True)
    valid.write_text("<html></html>", encoding="utf-8")
    outside.write_text("<html>secret</html>", encoding="utf-8")
    summary.parent.mkdir(parents=True)
    summary.write_text(
        json.dumps(
            {
                "contract_version": "1.0",
                "task_id": 10,
                "workflow_type": "t1_deepprep",
                "modality": "T1",
                "spaces": ["T1w"],
                "feature_groups": ["quality_control"],
                "outputs": {
                    "reports": [
                        {"name": "index.html", "path": str(valid), "relative_path": "reports/index.html"},
                        {"name": "missing.html", "path": str(missing), "relative_path": "reports/missing.html"},
                        {"name": "secret.html", "path": str(outside), "relative_path": "../secret.html"},
                    ]
                },
                "provenance": {},
            }
        ),
        encoding="utf-8",
    )
    with database.connect() as conn:
        conn.execute("INSERT INTO projects(id, name, description, created_at) VALUES(?,?,?,?)", (1, "P", "", database.now_iso()))
        conn.execute(
            "INSERT INTO files(id, project_id, original_name, storage_path, file_type, size, sha256, created_at) VALUES(?,?,?,?,?,?,?,?)",
            (1, 1, "t1.nii.gz", str(tmp_path / "t1.nii.gz"), "NIFTI", 1, "x", database.now_iso()),
        )
        conn.execute(
            "INSERT INTO imaging_series(id, project_id, file_id, sequence_label, supported_for_processing, unsupported_reason, modality, format, confidence, metadata_json, status, created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
            (1, 1, 1, "T1", 1, "", "T1", "NIFTI", 0.9, "{}", "detected", database.now_iso()),
        )
        conn.execute(
            "INSERT INTO tasks(id, project_id, series_id, workflow_type, status, progress, log_path, created_at) VALUES(?,?,?,?,?,?,?,?)",
            (10, 1, 1, "t1_deepprep", "completed", 100, str(tmp_path / "10.log"), database.now_iso()),
        )
        conn.execute(
            "INSERT INTO outputs(task_id, output_type, path, preview_path, metadata_json, created_at) VALUES(?,?,?,?,?,?)",
            (10, "json", str(summary), None, json.dumps({"kind": "result_summary"}), database.now_iso()),
        )

    payload = TestClient(app).get("/tasks/10/artifact-manifest").json()

    assert [item["relative_path"] for item in payload["artifacts"]] == ["reports/index.html"]
    assert payload["omitted_artifacts"] == [
        {"relative_path": "reports/missing.html", "reason": "missing_or_not_file"},
        {"relative_path": "../secret.html", "reason": "outside_task_output_dir"},
    ]


def test_dwi_fast_gpu_dti_requires_json_sidecar_metadata(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_ROOT", tmp_path)
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "app.db")
    monkeypatch.setattr(config, "PROJECTS_ROOT", tmp_path / "projects")
    from app.db import database
    import app.main as main

    monkeypatch.setattr(database, "DB_PATH", tmp_path / "app.db")
    monkeypatch.setattr(main, "PROJECTS_ROOT", tmp_path / "projects")
    monkeypatch.setattr(main, "run_pipeline_task", lambda task_id, qsiprep_task_id=None: None)

    database.init_db()
    client = TestClient(app)
    project = client.post("/projects", json={"name": "P-fast-dti-json"}).json()
    nifti = tmp_path / "sub-001_dwi.nii.gz"
    bval = tmp_path / "sub-001_dwi.bval"
    bvec = tmp_path / "sub-001_dwi.bvec"
    _write_minimal_nifti(nifti)
    bval.write_text("0 1000 1000\n", encoding="utf-8")
    bvec.write_text("1 0 0\n0 1 0\n0 0 1\n", encoding="utf-8")

    with nifti.open("rb") as nifti_f, bval.open("rb") as bval_f, bvec.open("rb") as bvec_f:
        uploaded = client.post(
            f"/projects/{project['id']}/upload-dwi",
            files={
                "nifti": (nifti.name, nifti_f, "application/gzip"),
                "bval": (bval.name, bval_f, "text/plain"),
                "bvec": (bvec.name, bvec_f, "text/plain"),
            },
        ).json()

    eligibility = uploaded["series"]["workflow_eligibility"]
    assert eligibility["production_task_created"] is False
    assert "dwi_fast_gpu_dti" in {item["workflow_type"] for item in eligibility["blocked_workflows"]}
    assert not any(item["workflow_type"] == "dwi_fast_gpu_dti" for item in eligibility["runnable_workflows"])

    rejected = client.post(
        f"/series/{uploaded['series']['id']}/run",
        json={"workflow_type": "dwi_fast_gpu_dti_validate"},
    )
    assert rejected.status_code == 403
    assert "/agent/runs" in rejected.json()["detail"]

    json_sidecar = tmp_path / "sub-001_dwi.json"
    json_sidecar.write_text('{"PhaseEncodingDirection": "j", "TotalReadoutTime": 0.05}', encoding="utf-8")
    with nifti.open("rb") as nifti_f, bval.open("rb") as bval_f, bvec.open("rb") as bvec_f, json_sidecar.open("rb") as json_f:
        accepted_upload = client.post(
            f"/projects/{project['id']}/upload-dwi",
            files={
                "nifti": (nifti.name, nifti_f, "application/gzip"),
                "bval": (bval.name, bval_f, "text/plain"),
                "bvec": (bvec.name, bvec_f, "text/plain"),
                "json_sidecar": (json_sidecar.name, json_f, "application/json"),
            },
        ).json()
    assert accepted_upload["series"]["metadata"]["has_json"] is True
    assert accepted_upload["series"]["metadata"]["has_dwi_eddy_metadata"] is True
    accepted_eligibility = accepted_upload["series"]["workflow_eligibility"]
    assert accepted_eligibility["primary_recommendation"]["workflow_type"] == "dwi_fast_gpu_dti"
    assert "dwi_fast_gpu_dti" in {item["workflow_type"] for item in accepted_eligibility["runnable_workflows"]}
    series_detail = client.get(f"/series/{accepted_upload['series']['id']}").json()
    assert series_detail["workflow_eligibility"]["primary_recommendation"]["workflow_type"] == "dwi_fast_gpu_dti"
    project_series = client.get(f"/projects/{project['id']}/series").json()
    accepted_from_list = next(item for item in project_series if item["id"] == accepted_upload["series"]["id"])
    assert accepted_from_list["workflow_eligibility"]["primary_recommendation"]["workflow_type"] == "dwi_fast_gpu_dti"
    assert client.get(f"/projects/{project['id']}/tasks").json() == []

    accepted = client.post(
        f"/series/{accepted_upload['series']['id']}/run",
        json={"workflow_type": "dwi_fast_gpu_dti_validate"},
    )
    assert accepted.status_code == 403
    assert "/agent/runs" in accepted.json()["detail"]
    with database.connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM tasks WHERE workflow_type='dwi_fast_gpu_dti_validate'").fetchone()[0] == 0


def test_dwi_fast_gpu_dti_accepts_legacy_bids_sidecar_metadata(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_ROOT", tmp_path)
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "app.db")
    monkeypatch.setattr(config, "PROJECTS_ROOT", tmp_path / "projects")
    from app.db import database
    import app.main as main

    monkeypatch.setattr(database, "DB_PATH", tmp_path / "app.db")
    monkeypatch.setattr(main, "PROJECTS_ROOT", tmp_path / "projects")
    monkeypatch.setattr(main, "run_pipeline_task", lambda task_id, qsiprep_task_id=None: None)

    database.init_db()
    client = TestClient(app)
    project = client.post("/projects", json={"name": "P-legacy-bids-dwi"}).json()
    bids_dwi = tmp_path / "projects" / str(project["id"]) / "bids" / "rawdata" / "sub-01" / "dwi" / "sub-01_dwi.nii"
    bids_dwi.parent.mkdir(parents=True)
    _write_minimal_nifti(bids_dwi)
    bids_dwi.with_suffix(".bval").write_text("0 1000 1000\n", encoding="utf-8")
    bids_dwi.with_suffix(".bvec").write_text("1 0 0\n0 1 0\n0 0 1\n", encoding="utf-8")
    bids_dwi.with_suffix(".json").write_text(
        '{"PhaseEncodingDirection": "j-", "TotalReadoutTime": 0.0321546}',
        encoding="utf-8",
    )
    legacy_metadata = {}
    with database.connect() as conn:
        conn.execute(
            "INSERT INTO files(id, project_id, original_name, storage_path, file_type, size, sha256, created_at) VALUES(?,?,?,?,?,?,?,?)",
            (1, project["id"], "sub-01_dwi.nii", str(bids_dwi), "NIFTI_BIDS", bids_dwi.stat().st_size, "x", database.now_iso()),
        )
        conn.execute(
            "INSERT INTO imaging_series(id, project_id, file_id, sequence_label, supported_for_processing, unsupported_reason, modality, format, confidence, metadata_json, status, created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
            (1, project["id"], 1, "DWI_multi_shell", 1, "", "DWI", "NIFTI_BIDS", 0.95, json.dumps(legacy_metadata), "detected", database.now_iso()),
        )

    accepted = client.post(
        "/series/1/run",
        json={"workflow_type": "dwi_fast_gpu_dti_validate"},
    )
    series_detail = client.get("/series/1").json()

    assert accepted.status_code == 403
    assert "/agent/runs" in accepted.json()["detail"]
    assert series_detail["workflow_eligibility"]["primary_recommendation"]["workflow_type"] == "dwi_fast_gpu_dti"
    with database.connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM tasks WHERE workflow_type='dwi_fast_gpu_dti_validate'").fetchone()[0] == 0


def test_dwi_eligibility_ignores_stale_sidecar_paths(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_ROOT", tmp_path)
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "app.db")
    monkeypatch.setattr(config, "PROJECTS_ROOT", tmp_path / "projects")
    from app.db import database
    import app.main as main

    monkeypatch.setattr(database, "DB_PATH", tmp_path / "app.db")
    monkeypatch.setattr(main, "PROJECTS_ROOT", tmp_path / "projects")

    database.init_db()
    client = TestClient(app)
    project = client.post("/projects", json={"name": "P-stale-sidecars"}).json()
    dwi = tmp_path / "projects" / str(project["id"]) / "bids" / "rawdata" / "sub-01" / "dwi" / "sub-01_dwi.nii"
    dwi.parent.mkdir(parents=True)
    _write_minimal_nifti(dwi)
    stale_metadata = {
        "sidecars": [
            str(dwi.with_suffix(".json")),
            str(dwi.with_suffix(".bval")),
            str(dwi.with_suffix(".bvec")),
        ],
        "PhaseEncodingDirection": "j-",
        "TotalReadoutTime": 0.0321546,
    }
    with database.connect() as conn:
        conn.execute(
            "INSERT INTO files(id, project_id, original_name, storage_path, file_type, size, sha256, created_at) VALUES(?,?,?,?,?,?,?,?)",
            (1, project["id"], "sub-01_dwi.nii", str(dwi), "NIFTI_BIDS", dwi.stat().st_size, "x", database.now_iso()),
        )
        conn.execute(
            "INSERT INTO imaging_series(id, project_id, file_id, sequence_label, supported_for_processing, unsupported_reason, modality, format, confidence, metadata_json, status, created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
            (1, project["id"], 1, "DWI_multi_shell", 1, "", "DWI", "NIFTI_BIDS", 0.95, json.dumps(stale_metadata), "detected", database.now_iso()),
        )

    series_detail = client.get("/series/1").json()
    eligibility = series_detail["workflow_eligibility"]

    assert eligibility["primary_recommendation"] is None
    assert not any(item["workflow_type"] == "dwi_fast_gpu_dti" for item in eligibility["runnable_workflows"])
    assert "dwi_fast_gpu_dti" in {item["workflow_type"] for item in eligibility["blocked_workflows"]}


def test_dwi_stage_copies_uploaded_json_sidecar_by_file_id(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_ROOT", tmp_path)
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "app.db")
    monkeypatch.setattr(config, "PROJECTS_ROOT", tmp_path / "projects")
    from app.db import database
    from app.workflows import pipeline
    import app.main as main

    monkeypatch.setattr(database, "DB_PATH", tmp_path / "app.db")
    monkeypatch.setattr(main, "PROJECTS_ROOT", tmp_path / "projects")
    monkeypatch.setattr(pipeline, "PROJECTS_ROOT", tmp_path / "projects")

    database.init_db()
    client = TestClient(app)
    project = client.post("/projects", json={"name": "P-dwi-json-stage"}).json()
    nifti = tmp_path / "sub-001_dwi.nii.gz"
    bval = tmp_path / "sub-001_dwi.bval"
    bvec = tmp_path / "sub-001_dwi.bvec"
    sidecar = tmp_path / "sub-001_dwi.json"
    _write_minimal_nifti(nifti)
    bval.write_text("0 1000 1000\n", encoding="utf-8")
    bvec.write_text("1 0 0\n0 1 0\n0 0 1\n", encoding="utf-8")
    sidecar.write_text('{"PhaseEncodingDirection": "j-", "TotalReadoutTime": 0.07}', encoding="utf-8")

    with nifti.open("rb") as nifti_f, bval.open("rb") as bval_f, bvec.open("rb") as bvec_f, sidecar.open("rb") as json_f:
        uploaded = client.post(
            f"/projects/{project['id']}/upload-dwi",
            files={
                "nifti": (nifti.name, nifti_f, "application/gzip"),
                "bval": (bval.name, bval_f, "text/plain"),
                "bvec": (bvec.name, bvec_f, "text/plain"),
                "json_sidecar": (sidecar.name, json_f, "application/json"),
            },
        ).json()

    task = {
        "id": 12,
        "project_id": project["id"],
        "series_id": uploaded["series"]["id"],
        "workflow_type": "dwi_fast_gpu_dti_validate",
        "log_path": str(tmp_path / "task.log"),
    }
    dirs = pipeline._build_bids(task, {"metadata_json": json.dumps(uploaded["series"]["metadata"]), **uploaded["series"]})
    staged = dirs["bids"] / "sub-01" / "dwi" / "sub-01_dwi.json"

    assert json.loads(staged.read_text(encoding="utf-8"))["PhaseEncodingDirection"] == "j-"


def test_bold_metric_resolver_prefers_mni_deepprep_outputs(tmp_path, monkeypatch):
    from app.workflows import pipeline

    monkeypatch.setattr(pipeline, "PROJECTS_ROOT", tmp_path / "projects")
    project_id = 7
    source_task = 41
    func = tmp_path / "projects" / str(project_id) / "derivatives" / str(source_task) / "output" / "BOLD" / "sub-01" / "func"
    qc = tmp_path / "projects" / str(project_id) / "derivatives" / str(source_task) / "output" / "QC" / "sub-01" / "figures"
    func.mkdir(parents=True)
    qc.mkdir(parents=True)
    mni = func / "sub-01_task-rest_space-MNI152NLin6Asym_desc-preproc_bold.nii.gz"
    t1w = func / "sub-01_task-rest_space-T1w_desc-preproc_bold.nii.gz"
    mask = func / "sub-01_task-rest_space-MNI152NLin6Asym_desc-brain_mask.nii.gz"
    confounds = func / "sub-01_task-rest_desc-confounds_timeseries.tsv"
    for path in (mni, t1w, mask, confounds):
        path.write_text("x", encoding="utf-8")
    mni.with_name(mni.name.replace(".nii.gz", ".json")).write_text('{"RepetitionTime": 2.0}', encoding="utf-8")

    monkeypatch.setattr(
        pipeline,
        "_row",
        lambda sql, params=(): {"id": source_task, "project_id": project_id} if "FROM tasks" in sql else None,
    )

    inputs = pipeline._resolve_bold_metric_inputs(
        {"project_id": project_id, "series_id": 3},
        {"project_id": project_id, "id": 3},
    )

    assert inputs["preproc_bold"] == mni
    assert inputs["brain_mask"] == mask


def test_bold_metric_resolver_does_not_pair_mni_bold_with_t1w_mask(tmp_path, monkeypatch):
    from app.workflows import pipeline

    monkeypatch.setattr(pipeline, "PROJECTS_ROOT", tmp_path / "projects")
    project_id = 7
    source_task = 42
    func = tmp_path / "projects" / str(project_id) / "derivatives" / str(source_task) / "output" / "BOLD" / "sub-01" / "func"
    func.mkdir(parents=True)
    mni = func / "sub-01_task-rest_space-MNI152NLin6Asym_res-02_desc-preproc_bold.nii.gz"
    t1w_mask = func / "sub-01_task-rest_space-T1w_desc-brain_mask.nii.gz"
    confounds = func / "sub-01_task-rest_desc-confounds_timeseries.tsv"
    for path in (mni, t1w_mask, confounds):
        path.write_text("x", encoding="utf-8")
    mni.with_name(mni.name.replace(".nii.gz", ".json")).write_text('{"RepetitionTime": 2.0}', encoding="utf-8")

    monkeypatch.setattr(
        pipeline,
        "_row",
        lambda sql, params=(): {"id": source_task, "project_id": project_id} if "FROM tasks" in sql else None,
    )

    inputs = pipeline._resolve_bold_metric_inputs(
        {"project_id": project_id, "series_id": 3},
        {"project_id": project_id, "id": 3},
    )

    assert inputs["preproc_bold"] == mni
    assert inputs["brain_mask"] is None


def test_generated_bold_brain_mask_uses_epi_mask_when_available(tmp_path, monkeypatch):
    from app.workflows import pipeline

    data = np.zeros((5, 5, 5, 10), dtype=np.float32)
    data[1:4, 1:4, 1:4, :] = np.linspace(1.0, 2.0, 10, dtype=np.float32)
    preproc = tmp_path / "sub-01_task-rest_space-MNI152NLin6Asym_desc-preproc_bold.nii.gz"
    mask_path = tmp_path / "sub-01_task-rest_space-MNI152NLin6Asym_desc-brain_mask.nii.gz"
    nib.save(nib.Nifti1Image(data, np.eye(4)), preproc)

    class FakeMask:
        dataobj = np.pad(np.ones((1, 1, 1), dtype=np.uint8), ((2, 2), (2, 2), (2, 2)))

    monkeypatch.setitem(__import__("sys").modules, "nilearn.masking", type("Masking", (), {"compute_epi_mask": lambda path: FakeMask}))

    pipeline._generate_bold_brain_mask(preproc, mask_path)

    generated = np.asarray(nib.load(mask_path).dataobj) > 0
    assert int(generated.sum()) == 1
    assert generated[2, 2, 2]


def test_bold_second_level_uses_real_mni_metric_command(tmp_path, monkeypatch):
    from app.workflows import pipeline

    monkeypatch.setattr(pipeline, "PROJECTS_ROOT", tmp_path / "projects")
    project_id = 7
    source_task = 41
    func = tmp_path / "projects" / str(project_id) / "derivatives" / str(source_task) / "output" / "BOLD" / "sub-01" / "func"
    func.mkdir(parents=True)
    preproc = func / "sub-01_task-rest_space-MNI152NLin6Asym_desc-preproc_bold.nii.gz"
    mask = func / "sub-01_task-rest_space-MNI152NLin6Asym_desc-brain_mask.nii.gz"
    confounds = func / "sub-01_task-rest_desc-confounds_timeseries.tsv"
    for path in (preproc, mask, confounds):
        path.write_text("x", encoding="utf-8")
    bold_json = preproc.with_name(preproc.name.replace(".nii.gz", ".json"))
    bold_json.write_text('{"RepetitionTime": 2.0}', encoding="utf-8")

    monkeypatch.setattr(
        pipeline,
        "_row",
        lambda sql, params=(): {"id": source_task, "project_id": project_id} if "FROM tasks" in sql else None,
    )

    inputs = pipeline._resolve_bold_metric_inputs(
        {"project_id": project_id, "series_id": 3},
        {"project_id": project_id, "id": 3},
    )
    cmd = pipeline._commands(
        "bold_second_level",
        {"bids": tmp_path / "bids", "output": tmp_path / "out", "work": tmp_path / "work", "root": tmp_path},
        metric_inputs=inputs,
    )[0]

    assert "-m" in cmd
    assert "app.workflows.bold_metrics" in cmd
    assert "--preproc-bold" in cmd
    assert str(preproc) in cmd
    assert "--brain-mask" in cmd
    assert str(mask) in cmd
    assert "--confounds" in cmd
    assert str(confounds) in cmd
    assert "--metrics" not in cmd


def test_bold_pipeline_executes_real_metric_command_and_registers_outputs(tmp_path, monkeypatch):
    from app.workflows import pipeline

    monkeypatch.setattr(pipeline, "PROJECTS_ROOT", tmp_path / "projects")
    task_id = 12
    task = {
        "id": task_id,
        "project_id": 7,
        "series_id": 3,
        "workflow_type": "bold_second_level",
        "log_path": str(tmp_path / "task.log"),
    }
    series = {
        "id": 3,
        "project_id": 7,
        "file_id": 99,
        "metadata_json": "{}",
    }
    dirs = {
        "root": tmp_path / "task",
        "bids": tmp_path / "task" / "bids",
        "output": tmp_path / "task" / "output",
        "work": tmp_path / "task" / "work",
    }
    dirs["output"].mkdir(parents=True)
    summary = dirs["output"] / "sub-01_task-rest_desc-bold_metrics_summary.json"
    provenance = dirs["output"] / "sub-01_task-rest_desc-bold_metrics_provenance.json"
    seed_to_roi = dirs["output"] / "sub-01_task-rest_desc-seed_to_roi.tsv"
    network_dmn = dirs["output"] / "sub-01_task-rest_desc-network_dmn.tsv"
    seed_timeseries = dirs["output"] / "sub-01_task-rest_desc-seed_timeseries.tsv"
    result_summary = dirs["output"] / "summary" / "bold_result_summary.json"

    updates = []
    inserted = []
    commands = []

    monkeypatch.setattr(pipeline, "_row", lambda sql, params=(): task if "FROM tasks WHERE id" in sql else series)
    monkeypatch.setattr(pipeline, "_build_bids", lambda task_arg, series_arg: dirs)
    monkeypatch.setattr(
        pipeline,
        "_resolve_bold_metric_inputs",
        lambda task_arg, series_arg, log_path=None: {
            "preproc_bold": tmp_path / "source" / "sub-01_task-rest_space-MNI152NLin6Asym_desc-preproc_bold.nii.gz",
            "bold_json": tmp_path / "source" / "sub-01_task-rest_space-MNI152NLin6Asym_desc-preproc_bold.json",
            "brain_mask": tmp_path / "source" / "sub-01_task-rest_space-MNI152NLin6Asym_desc-brain_mask.nii.gz",
            "confounds_tsv": tmp_path / "source" / "sub-01_task-rest_desc-confounds_timeseries.tsv",
            "tsnr_source": None,
        },
    )
    monkeypatch.setattr(
        pipeline,
        "_prepare_bold_metric_inputs",
        lambda metric_inputs, dirs_arg, log_path=None: metric_inputs,
    )
    monkeypatch.setattr(pipeline, "_update", lambda task_id_arg, **values: updates.append((task_id_arg, values)))
    monkeypatch.setattr(
        pipeline,
        "_run_local_command",
        lambda cmd, log_path: (
            commands.append(cmd),
            summary.write_text(
                '{"spaces":["MNI152"],"metrics":["alff","falff","reho","dmn","seed_to_roi"],"seeds":[{"preset_id":"PCC_DMN"}]}',
                encoding="utf-8",
            ),
            provenance.write_text('{"preproc_bold":"/source/mni.nii.gz","brain_mask":"/output/masks/mask.nii.gz"}', encoding="utf-8"),
            *[
                (dirs["output"] / f"sub-01_task-rest_space-MNI152NLin6Asym_res-02_desc-{metric}_bold.nii.gz").write_bytes(b"nifti")
                for metric in ("alff", "falff", "reho", "tsnr", "rsfa")
            ],
            seed_to_roi.write_text("seed_id\troi_id\tcorrelation_r\n", encoding="utf-8"),
            network_dmn.write_text("network\tmean_fc\nDMN\t0.0\n", encoding="utf-8"),
            seed_timeseries.write_text("volume_index\tPCC_DMN\n0\t0.0\n", encoding="utf-8"),
        ),
    )
    monkeypatch.setattr(pipeline, "_register_outputs", lambda task_id_arg, output_dir: 3)
    monkeypatch.setattr(
        pipeline,
        "_insert_output",
        lambda task_id_arg, output_type, path=None, metadata=None: inserted.append((task_id_arg, output_type, Path(path) if path else None, metadata)),
    )

    pipeline.run_pipeline_task(task_id)

    assert commands
    assert "--preproc-bold" in commands[0]
    assert any(item[2] == summary and item[3]["kind"] == "bold_metrics_summary" for item in inserted)
    assert any(item[2] == seed_to_roi and item[3]["kind"] == "seed_to_roi" for item in inserted)
    assert any(item[2] == network_dmn and item[3]["kind"] == "network_summary" for item in inserted)
    assert any(item[2] == result_summary and item[3]["kind"] == "result_summary" for item in inserted)
    assert updates[-1][1]["status"] == "completed"


def test_bold_fmriprep_xcpd_pipeline_writes_scientific_report_summary(tmp_path, monkeypatch):
    from app.workflows import pipeline

    task_id = 135
    task = {
        "id": task_id,
        "project_id": 24,
        "series_id": 45,
        "workflow_type": "bold_fmriprep_xcpd_report",
        "log_path": str(tmp_path / "task.log"),
    }
    series = {
        "id": 45,
        "project_id": 24,
        "file_id": 99,
        "metadata_json": "{}",
    }
    dirs = {
        "root": tmp_path / "task",
        "bids": tmp_path / "task" / "bids",
        "output": tmp_path / "task" / "output",
        "work": tmp_path / "task" / "work",
    }
    for directory in dirs.values():
        directory.mkdir(parents=True, exist_ok=True)

    def write_minimal_container_outputs(**kwargs):
        output_dir = Path(kwargs["output_dir"])
        (output_dir / "fmriprep").mkdir(parents=True, exist_ok=True)
        (output_dir / "xcpd").mkdir(parents=True, exist_ok=True)
        (output_dir / "tables").mkdir(parents=True, exist_ok=True)
        (output_dir / "maps").mkdir(parents=True, exist_ok=True)
        (output_dir / "logs").mkdir(parents=True, exist_ok=True)
        (output_dir / "fmriprep" / "sub-01.html").write_text("<html>fmriprep</html>", encoding="utf-8")
        (output_dir / "xcpd" / "sub-01.html").write_text("<html>xcpd</html>", encoding="utf-8")
        (output_dir / "tables" / "connectivity.tsv").write_text("seed\troi\tcorrelation\nA\tB\t0.1\n", encoding="utf-8")
        (output_dir / "maps" / "sub-01_space-MNI152NLin6Asym_desc-preproc_bold.nii.gz").write_bytes(b"nifti")
        (output_dir / "logs" / "xcpd.log").write_text("XCP-D finished successfully\n", encoding="utf-8")
        outputs = pipeline.discover_bold_fmriprep_xcpd_outputs(output_dir)
        return {"ok": True, "scripts": ["run_fmriprep.sh", "run_xcpd_fmriprep.sh"], "outputs": outputs}

    updates = []
    inserted = []
    monkeypatch.setattr(pipeline, "_row", lambda sql, params=(): task if "FROM tasks WHERE id" in sql else series)
    monkeypatch.setattr(pipeline, "_rows", lambda sql, params=(): [])
    monkeypatch.setattr(pipeline, "_build_bids", lambda task_arg, series_arg: dirs)
    monkeypatch.setattr(pipeline, "_commands", lambda workflow, dirs_arg, **kwargs: [["docker", "run", "bold"]])
    monkeypatch.setattr(pipeline, "_isolate_stale_task_workspace", lambda task_arg, log_path: None)
    monkeypatch.setattr(pipeline, "_update", lambda task_id_arg, **values: updates.append((task_id_arg, values)))
    monkeypatch.setattr(pipeline, "_register_outputs", lambda task_id_arg, output_dir: 5)
    monkeypatch.setattr(
        pipeline,
        "_insert_output",
        lambda task_id_arg, output_type, path=None, metadata=None: inserted.append((task_id_arg, output_type, Path(path) if path else None, metadata)),
    )
    monkeypatch.setattr(pipeline, "run_bold_fmriprep_xcpd_remote", write_minimal_container_outputs)

    pipeline.run_pipeline_task(task_id)

    result_summary = dirs["output"] / "summary" / "bold_result_summary.json"
    scientific_summary = dirs["output"] / "summary" / "bold_scientific_report_summary.json"
    main_summary = json.loads(result_summary.read_text(encoding="utf-8"))
    report_paths = [item["relative_path"] for item in main_summary["outputs"]["reports"]]

    assert scientific_summary.exists()
    assert "reports/index.html" in report_paths
    assert "reports/report_manifest.json" in report_paths
    assert any(item[2] == scientific_summary and item[3]["kind"] == "scientific_report_summary" for item in inserted)
    assert updates[-1][1]["status"] == "completed"
