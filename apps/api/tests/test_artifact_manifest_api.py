import json
import zipfile
from io import BytesIO

from fastapi.testclient import TestClient

from app.core import config
from app.main import app
from app.services import result_service


def _seed_completed_task(tmp_path, monkeypatch, *, task_id=221):
    monkeypatch.setattr(config, "DATA_ROOT", tmp_path)
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "app.db")
    monkeypatch.setattr(config, "PROJECTS_ROOT", tmp_path / "projects")

    from app.db import database
    import app.main as main

    monkeypatch.setattr(database, "DB_PATH", tmp_path / "app.db")
    monkeypatch.setattr(main, "PROJECTS_ROOT", tmp_path / "projects")

    database.init_db()
    output_dir = tmp_path / "projects" / "1" / "derivatives" / str(task_id) / "output"
    native_html = output_dir / "fmriprep" / "sub-01.html"
    native_png = output_dir / "xcpd" / "sub-01" / "figures" / "carpetplot.png"
    report_png = output_dir / "reports" / "t1_qc.png"
    pipeline_log = output_dir / "logs" / "pipeline.log"
    windows_style = output_dir / "reports" / "windows-style.png"
    summary = output_dir / "summary" / "t1_result_summary.json"

    native_html.parent.mkdir(parents=True, exist_ok=True)
    native_html.write_text("<html><body>native qc</body></html>", encoding="utf-8")
    native_png.parent.mkdir(parents=True, exist_ok=True)
    native_png.write_bytes(b"\x89PNG\r\n\x1a\nnative")
    report_png.parent.mkdir(parents=True, exist_ok=True)
    report_png.write_bytes(b"\x89PNG\r\n\x1a\nreport")
    pipeline_log.parent.mkdir(parents=True, exist_ok=True)
    pipeline_log.write_text("container command completed\n", encoding="utf-8")
    windows_style.write_bytes(b"\x89PNG\r\n\x1a\nunsafe")

    summary.parent.mkdir(parents=True)
    summary.write_text(
        json.dumps(
            {
                "contract_version": "1.0",
                "summary_path": str(summary),
                "task_id": task_id,
                "workflow_type": "t1_deepprep",
                "modality": "T1",
                "outputs": {
                    "reports": [
                        {
                            "name": "sub-01.html",
                            "path": str(native_html),
                            "relative_path": "fmriprep/sub-01.html",
                            "content_type": "text/html",
                            "native_artifact": True,
                            "artifact_origin": "container_output",
                            "source_stage": "fmriprep",
                            "official_source_ids": ["docs/rag/vendor/fmriprep_official_outputs.md"],
                            "provenance": {
                                "generated_from": "container_native_qc",
                                "replaces_native_qc": False,
                                "official_source_ids": ["docs/rag/vendor/fmriprep_official_outputs.md"],
                            },
                        },
                        {
                            "name": "t1_qc.png",
                            "path": str(report_png),
                            "relative_path": "reports/t1_qc.png",
                            "content_type": "image/png",
                            "native_artifact": False,
                            "artifact_origin": "generated_from_result_summary",
                            "source_stage": "scientific_report",
                            "provenance": {
                                "generated_from": "result_summary",
                                "replaces_native_qc": False,
                            },
                        },
                        {
                            "name": "windows-style.png",
                            "path": str(windows_style),
                            "relative_path": r"reports\windows-style.png",
                            "content_type": "image/png",
                        },
                    ],
                    "figures": [
                        {
                            "name": "carpetplot.png",
                            "path": str(native_png),
                            "relative_path": "xcpd/sub-01/figures/carpetplot.png",
                            "content_type": "image/png",
                            "native_artifact": True,
                            "artifact_origin": "container_output",
                            "source_stage": "xcpd",
                            "official_source_ids": ["docs/rag/vendor/xcp_d_official_outputs.md"],
                            "provenance": {
                                "generated_from": "container_native_qc",
                                "replaces_native_qc": False,
                                "official_source_ids": ["docs/rag/vendor/xcp_d_official_outputs.md"],
                            },
                        }
                    ],
                },
                "provenance": {"placeholder_outputs": False},
            }
        ),
        encoding="utf-8",
    )
    with database.connect() as conn:
        now = database.now_iso()
        conn.execute("INSERT INTO projects(id, name, description, created_at) VALUES(?,?,?,?)", (1, "P", "", now))
        conn.execute(
            "INSERT INTO files(id, project_id, original_name, storage_path, file_type, size, sha256, created_at) VALUES(?,?,?,?,?,?,?,?)",
            (1, 1, "t1.nii.gz", str(tmp_path / "t1.nii.gz"), "NIFTI", 1, "x", now),
        )
        conn.execute(
            "INSERT INTO imaging_series(id, project_id, file_id, sequence_label, supported_for_processing, unsupported_reason, modality, format, confidence, metadata_json, status, created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
            (1, 1, 1, "T1", 1, "", "T1", "NIFTI", 0.9, "{}", "detected", now),
        )
        conn.execute(
            "INSERT INTO tasks(id, project_id, series_id, workflow_type, status, progress, log_path, created_at) VALUES(?,?,?,?,?,?,?,?)",
            (task_id, 1, 1, "t1_deepprep", "completed", 100, str(tmp_path / f"{task_id}.log"), now),
        )
        conn.execute(
            "INSERT INTO outputs(task_id, output_type, path, preview_path, metadata_json, created_at) VALUES(?,?,?,?,?,?)",
            (task_id, "json", str(summary), None, json.dumps({"kind": "result_summary"}), now),
        )
    return task_id


def test_artifact_manifest_and_artifact_route_are_frontend_safe_contract_pair(tmp_path, monkeypatch):
    task_id = _seed_completed_task(tmp_path, monkeypatch)
    client = TestClient(app)

    manifest_response = client.get(f"/tasks/{task_id}/artifact-manifest")

    assert manifest_response.status_code == 200
    manifest = manifest_response.json()
    assert manifest["contract_version"] == "artifact_manifest_v1"
    assert manifest["artifact_endpoint"] == f"/tasks/{task_id}/artifacts/{{relative_path}}"
    artifacts = {item["relative_path"]: item for item in manifest["artifacts"]}
    assert set(artifacts) == {
        "fmriprep/sub-01.html",
        "reports/t1_qc.png",
        "xcpd/sub-01/figures/carpetplot.png",
    }
    assert all("path" not in item for item in artifacts.values())
    assert all(not item["download_url"].startswith("file:") for item in artifacts.values())
    assert artifacts["fmriprep/sub-01.html"]["preview_kind"] == "html"
    assert artifacts["xcpd/sub-01/figures/carpetplot.png"]["preview_kind"] == "image"
    assert artifacts["reports/t1_qc.png"]["source_stage"] == "scientific_report"
    assert artifacts["reports/t1_qc.png"]["provenance"]["replaces_native_qc"] is False
    assert {
        "relative_path": r"reports\windows-style.png",
        "reason": "unsafe_relative_path",
    } in manifest["omitted_artifacts"]

    html_response = client.get(artifacts["fmriprep/sub-01.html"]["download_url"])
    png_response = client.get(artifacts["xcpd/sub-01/figures/carpetplot.png"]["download_url"])
    generated_response = client.get(artifacts["reports/t1_qc.png"]["download_url"])

    assert html_response.status_code == 200
    assert html_response.headers["content-type"].startswith("text/html")
    assert "native qc" in html_response.text
    assert png_response.status_code == 200
    assert png_response.headers["content-type"].startswith("image/png")
    assert png_response.content.startswith(b"\x89PNG")
    assert generated_response.status_code == 200
    assert generated_response.content.startswith(b"\x89PNG")

    assert client.get(f"/tasks/{task_id}/artifacts/../secret.txt").status_code in {400, 404}
    assert client.get(f"/tasks/{task_id}/artifacts/reports%5Cwindows-style.png").status_code == 400


def test_task_export_bundle_downloads_all_safe_result_data(tmp_path, monkeypatch):
    task_id = _seed_completed_task(tmp_path, monkeypatch, task_id=222)
    client = TestClient(app)

    response = client.get(f"/tasks/{task_id}/export-bundle")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/zip")
    assert f"image-agent-task-{task_id}-export.zip" in response.headers["content-disposition"]
    with zipfile.ZipFile(BytesIO(response.content)) as bundle:
        names = set(bundle.namelist())
        assert "artifact_manifest.json" in names
        assert "result_summary.json" in names
        assert "fmriprep/sub-01.html" in names
        assert "logs/pipeline.log" in names
        assert "reports/t1_qc.png" in names
        assert "summary/t1_result_summary.json" in names
        assert "xcpd/sub-01/figures/carpetplot.png" in names
        assert r"reports\windows-style.png" not in names
        assert "../secret.txt" not in names
        manifest = json.loads(bundle.read("artifact_manifest.json").decode("utf-8"))
        assert manifest["task_id"] == task_id
        assert all("path" not in item for item in manifest["artifacts"])


def test_task_export_bundle_native_download_ticket_is_one_time_and_safe(tmp_path, monkeypatch):
    task_id = _seed_completed_task(tmp_path, monkeypatch, task_id=223)
    client = TestClient(app)

    ticket_response = client.post(f"/tasks/{task_id}/export-bundle-ticket")

    assert ticket_response.status_code == 200
    ticket = ticket_response.json()
    assert ticket["download_url"].startswith(f"/tasks/{task_id}/export-bundle-download?ticket=")
    assert "expires_at" in ticket

    first_download = client.get(ticket["download_url"])
    second_download = client.get(ticket["download_url"])

    assert first_download.status_code == 200
    assert first_download.headers["content-type"].startswith("application/zip")
    assert f"image-agent-task-{task_id}-export.zip" in first_download.headers["content-disposition"]
    assert second_download.status_code == 403
    assert client.get(f"/tasks/{task_id}/export-bundle-download?ticket=bad-ticket").status_code == 403


def test_task_export_bundle_ticket_download_bypasses_bearer_auth_but_requires_ticket(tmp_path, monkeypatch):
    task_id = _seed_completed_task(tmp_path, monkeypatch, task_id=224)
    monkeypatch.setenv("IMAGE_AGENT_REQUIRE_AUTH", "true")
    client = TestClient(app)
    ticket = result_service.create_task_export_ticket(task_id)

    valid_download = client.get(ticket["download_url"])
    invalid_download = client.get(f"/tasks/{task_id}/export-bundle-download?ticket=bad-ticket")

    assert valid_download.status_code == 200
    assert valid_download.headers["content-type"].startswith("application/zip")
    assert invalid_download.status_code == 403
