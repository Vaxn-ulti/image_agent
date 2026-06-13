import json
import importlib.util
import subprocess
import sys
from pathlib import Path

from app.scripts.verify_scientific_reports import check_output, main, resolve_task_output_dirs


def _load_packaged_script_module():
    script = Path(__file__).resolve().parents[1] / "scripts" / "verify_scientific_reports.py"
    spec = importlib.util.spec_from_file_location("packaged_verify_scientific_reports", script)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _report_metadata() -> dict:
    return {
        "source_stage": "scientific_report",
        "artifact_role": "derived_presentation_asset",
        "artifact_origin": "generated_from_result_summary",
        "native_artifact": False,
        "provenance": {
            "generated_from": "result_summary",
            "replaces_native_qc": False,
        },
    }


def _write_report_output(root: Path, modality: str = "DWI", *, include_provenance: bool = True) -> None:
    summary_dir = root / "summary"
    reports_dir = root / "reports"
    summary_dir.mkdir(parents=True)
    reports_dir.mkdir()
    reports = [
        {
            "relative_path": "reports/index.html",
            "download_url": "/tasks/1/artifacts/reports/index.html",
            "content_type": "text/html",
            "size_bytes": 1200,
            **(_report_metadata() if include_provenance else {}),
        },
        {
            "relative_path": "reports/report_manifest.json",
            "download_url": "/tasks/1/artifacts/reports/report_manifest.json",
            "content_type": "application/json",
            "size_bytes": 300,
            **(_report_metadata() if include_provenance else {}),
        },
    ]
    main_summary_path = summary_dir / f"{modality.lower()}_result_summary.json"
    report_summary_path = summary_dir / f"{modality.lower()}_scientific_report_summary.json"
    main_summary_path.write_text(
        json.dumps(
            {
                "modality": modality,
                "outputs": {"reports": reports},
                "provenance": {"scientific_report_summary_path": str(report_summary_path)},
            }
        ),
        encoding="utf-8",
    )
    report_summary_path.write_text(json.dumps({"outputs": {"reports": reports}}), encoding="utf-8")
    reports_dir.joinpath("index.html").write_text(
        f"<html><body><h1>{modality} Scientific Report</h1>{'real readable content ' * 80}</body></html>",
        encoding="utf-8",
    )
    reports_dir.joinpath("report_manifest.json").write_text(
        json.dumps({"modality": modality, "assets": ["index.html", "report_manifest.json", "a.png", "b.png", "c.png", "d.png"]}),
        encoding="utf-8",
    )
    for name in ("a.png", "b.png", "c.png", "d.png"):
        reports_dir.joinpath(name).write_bytes(b"\x89PNG\r\n\x1a\n" + (name.encode("utf-8") * 80))


def _native_qc_metadata(source_id: str, *, preview_kind: str = "image") -> dict:
    return {
        "download_url": "/tasks/1/artifacts/native-qc/qc.png" if preview_kind == "image" else "/tasks/1/artifacts/native-qc/report.html",
        "content_type": "image/png" if preview_kind == "image" else "text/html",
        "size_bytes": 500,
        "source_stage": "fmriprep",
        "artifact_role": "container_native_qc_figure" if preview_kind == "image" else "container_native_html_report",
        "artifact_origin": "container_output",
        "native_artifact": True,
        "official_source_ids": [source_id],
        "provenance": {
            "generated_from": "container_native_qc",
            "replaces_native_qc": False,
            "official_source_ids": [source_id],
        },
    }


def _add_native_qc_outputs(root: Path, *, source_id: str = "docs/rag/vendor/fmriprep_official_outputs.md") -> None:
    summary_path = root / "summary" / "dwi_result_summary.json"
    payload = json.loads(summary_path.read_text(encoding="utf-8"))
    native_qc_dir = root / "native-qc"
    native_qc_dir.mkdir()
    native_qc_dir.joinpath("report.html").write_text("<html><body>native qc report</body></html>", encoding="utf-8")
    native_qc_dir.joinpath("qc.png").write_bytes(b"\x89PNG\r\n\x1a\n" + (b"native-qc" * 80))
    payload["outputs"]["reports"].append(
        {
            "relative_path": "native-qc/report.html",
            **_native_qc_metadata(source_id, preview_kind="html"),
        }
    )
    payload["outputs"]["figures"] = [
        {
            "relative_path": "native-qc/qc.png",
            **_native_qc_metadata(source_id, preview_kind="image"),
        }
    ]
    summary_path.write_text(json.dumps(payload), encoding="utf-8")


def test_check_output_accepts_complete_scientific_report_bundle(tmp_path):
    _write_report_output(tmp_path, "DWI")

    result = check_output(tmp_path)

    assert result.ok
    assert result.modality == "DWI"
    assert result.errors == []


def test_check_output_rejects_missing_reports_contract(tmp_path):
    (tmp_path / "summary").mkdir()
    (tmp_path / "summary" / "t1_result_summary.json").write_text(json.dumps({"modality": "T1", "outputs": {}, "provenance": {}}), encoding="utf-8")

    result = check_output(tmp_path)

    assert not result.ok
    assert any("missing scientific report summary" in error for error in result.errors)


def test_check_output_rejects_unlabeled_generated_report_assets(tmp_path):
    _write_report_output(tmp_path, "DWI", include_provenance=False)

    result = check_output(tmp_path)

    assert not result.ok
    assert any("generated report artifact missing derived provenance" in error for error in result.errors)


def test_packaged_script_uses_current_png_report_contract(tmp_path):
    packaged = _load_packaged_script_module()
    _write_report_output(tmp_path, "DWI")

    result = packaged.check_output(tmp_path)

    assert result.ok
    assert result.modality == "DWI"
    assert result.errors == []


def test_packaged_script_rejects_unlabeled_generated_report_assets(tmp_path):
    packaged = _load_packaged_script_module()
    _write_report_output(tmp_path, "DWI", include_provenance=False)

    result = packaged.check_output(tmp_path)

    assert not result.ok
    assert any("generated report artifact missing derived provenance" in error for error in result.errors)


def test_packaged_script_cli_accepts_png_report_contract(tmp_path):
    _write_report_output(tmp_path, "DWI")
    script = Path(__file__).resolve().parents[1] / "scripts" / "verify_scientific_reports.py"

    result = subprocess.run(
        [sys.executable, str(script), str(tmp_path), "--require-modalities", "DWI", "--json"],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["ok"] is True
    assert payload["results"][0]["modality"] == "DWI"


def test_check_output_rejects_derived_only_reports_when_native_qc_required(tmp_path):
    _write_report_output(tmp_path, "DWI")

    result = check_output(tmp_path, require_container_native_qc=True, min_native_qc_images=1)

    assert not result.ok
    assert any("container-native QC evidence missing" in error for error in result.errors)


def test_check_output_rejects_reports_path_native_qc_impersonation(tmp_path):
    _write_report_output(tmp_path, "DWI")
    fake_native = tmp_path / "reports" / "fake_native.png"
    fake_native.write_bytes(b"\x89PNG\r\n\x1a\n" + (b"fake-native" * 80))
    summary_path = tmp_path / "summary" / "dwi_result_summary.json"
    payload = json.loads(summary_path.read_text(encoding="utf-8"))
    payload["outputs"]["figures"] = [
        {
            "relative_path": "reports/fake_native.png",
            **_native_qc_metadata("docs/rag/vendor/fmriprep_official_outputs.md", preview_kind="image"),
        }
    ]
    summary_path.write_text(json.dumps(payload), encoding="utf-8")

    result = check_output(tmp_path, require_container_native_qc=True, min_native_qc_images=1)

    assert not result.ok
    assert any("container-native QC evidence missing" in error for error in result.errors)


def test_check_output_accepts_separate_native_qc_when_required(tmp_path):
    _write_report_output(tmp_path, "DWI")
    _add_native_qc_outputs(tmp_path)

    result = check_output(tmp_path, require_container_native_qc=True, min_native_qc_images=1)

    assert result.ok
    assert result.errors == []


def test_check_output_rejects_native_qc_missing_output_file(tmp_path):
    _write_report_output(tmp_path, "DWI")
    _add_native_qc_outputs(tmp_path)
    (tmp_path / "native-qc" / "qc.png").unlink()

    result = check_output(tmp_path, require_container_native_qc=True, min_native_qc_images=1)

    assert not result.ok
    assert any("container-native QC artifact file missing" in error for error in result.errors)


def test_check_output_rejects_native_qc_unsupported_official_source(tmp_path):
    _write_report_output(tmp_path, "DWI")
    _add_native_qc_outputs(tmp_path, source_id="docs/rag/vendor/fake.md")

    result = check_output(tmp_path, require_container_native_qc=True, min_native_qc_images=1)

    assert not result.ok
    assert any("official_source_ids unsupported" in error for error in result.errors)


def test_main_enforces_required_modalities(tmp_path):
    dwi = tmp_path / "dwi"
    _write_report_output(dwi, "DWI")

    assert main([str(dwi), "--require-modalities", "T1", "BOLD", "DWI"]) == 1


def test_resolve_task_output_dirs_finds_project_derivative_output(tmp_path):
    output = tmp_path / "projects" / "13" / "derivatives" / "114" / "output"
    _write_report_output(output, "DWI")

    paths, errors = resolve_task_output_dirs(tmp_path / "projects", [114])

    assert errors == []
    assert paths == [output]


def test_main_accepts_task_ids_with_projects_root(tmp_path):
    output = tmp_path / "projects" / "13" / "derivatives" / "114" / "output"
    _write_report_output(output, "DWI")

    assert main(["--projects-root", str(tmp_path / "projects"), "--task-ids", "114", "--require-modalities", "DWI"]) == 0


def test_agent_verify_scientific_reports_endpoint_accepts_task_ids(tmp_path, monkeypatch):
    from app.core import config
    from app.db import database
    import app.main as main_app
    from fastapi.testclient import TestClient

    projects_root = tmp_path / "projects"
    output = projects_root / "13" / "derivatives" / "114" / "output"
    _write_report_output(output, "DWI")
    monkeypatch.setattr(config, "DATA_ROOT", tmp_path)
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "app.db")
    monkeypatch.setattr(config, "PROJECTS_ROOT", projects_root)
    monkeypatch.setattr(database, "DB_PATH", tmp_path / "app.db")
    monkeypatch.setattr(main_app, "PROJECTS_ROOT", projects_root)
    database.init_db()

    payload = TestClient(main_app.app).post(
        "/agent/tools/verify-scientific-reports",
        json={"projects_root": str(projects_root), "task_ids": [114], "require_modalities": ["DWI"]},
    ).json()

    assert payload["ok"] is True
    assert payload["read_only"] is True
    assert payload["results"][0]["modality"] == "DWI"


def test_agent_verify_scientific_reports_endpoint_reports_missing_required_modality(tmp_path, monkeypatch):
    from app.core import config
    from app.db import database
    import app.main as main_app
    from fastapi.testclient import TestClient

    projects_root = tmp_path / "projects"
    output = projects_root / "13" / "derivatives" / "114" / "output"
    _write_report_output(output, "DWI")
    monkeypatch.setattr(config, "DATA_ROOT", tmp_path)
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "app.db")
    monkeypatch.setattr(config, "PROJECTS_ROOT", projects_root)
    monkeypatch.setattr(database, "DB_PATH", tmp_path / "app.db")
    monkeypatch.setattr(main_app, "PROJECTS_ROOT", projects_root)
    database.init_db()

    payload = TestClient(main_app.app).post(
        "/agent/tools/verify-scientific-reports",
        json={"projects_root": str(projects_root), "task_ids": [114], "require_modalities": ["T1", "DWI"]},
    ).json()

    assert payload["ok"] is False
    assert payload["missing_modalities"] == ["T1"]


def test_agent_verify_scientific_reports_endpoint_enforces_native_qc_requirement(tmp_path, monkeypatch):
    from app.core import config
    from app.db import database
    import app.main as main_app
    from fastapi.testclient import TestClient

    projects_root = tmp_path / "projects"
    output = projects_root / "13" / "derivatives" / "114" / "output"
    _write_report_output(output, "DWI")
    monkeypatch.setattr(config, "DATA_ROOT", tmp_path)
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "app.db")
    monkeypatch.setattr(config, "PROJECTS_ROOT", projects_root)
    monkeypatch.setattr(database, "DB_PATH", tmp_path / "app.db")
    monkeypatch.setattr(main_app, "PROJECTS_ROOT", projects_root)
    database.init_db()

    payload = TestClient(main_app.app).post(
        "/agent/tools/verify-scientific-reports",
        json={
            "projects_root": str(projects_root),
            "task_ids": [114],
            "require_modalities": ["DWI"],
            "require_container_native_qc": True,
            "min_native_qc_images": 1,
        },
    ).json()

    assert payload["ok"] is False
    assert payload["require_container_native_qc"] is True
    assert payload["min_native_qc_images"] == 1
    assert any("container-native QC evidence missing" in error for error in payload["results"][0]["errors"])


def test_agent_verify_scientific_reports_endpoint_accepts_native_qc_requirement(tmp_path, monkeypatch):
    from app.core import config
    from app.db import database
    import app.main as main_app
    from fastapi.testclient import TestClient

    projects_root = tmp_path / "projects"
    output = projects_root / "13" / "derivatives" / "114" / "output"
    _write_report_output(output, "DWI")
    _add_native_qc_outputs(output)
    monkeypatch.setattr(config, "DATA_ROOT", tmp_path)
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "app.db")
    monkeypatch.setattr(config, "PROJECTS_ROOT", projects_root)
    monkeypatch.setattr(database, "DB_PATH", tmp_path / "app.db")
    monkeypatch.setattr(main_app, "PROJECTS_ROOT", projects_root)
    database.init_db()

    payload = TestClient(main_app.app).post(
        "/agent/tools/verify-scientific-reports",
        json={
            "projects_root": str(projects_root),
            "task_ids": [114],
            "require_modalities": ["DWI"],
            "require_container_native_qc": True,
            "min_native_qc_images": 1,
        },
    ).json()

    assert payload["ok"] is True
    assert payload["require_container_native_qc"] is True
    assert payload["min_native_qc_images"] == 1
    assert payload["results"][0]["errors"] == []
