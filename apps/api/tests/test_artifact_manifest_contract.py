import json

from app.workflows.artifact_manifest import build_artifact_manifest


def test_artifact_manifest_classifies_native_qc_scientific_reports_and_preview_assets(tmp_path):
    output_dir = tmp_path / "output"
    native_report = output_dir / "fmriprep" / "sub-01.html"
    report_png = output_dir / "reports" / "t1_qc.png"
    table = output_dir / "tables" / "regions.tsv"
    map_file = output_dir / "maps" / "fa.nii.gz"
    for path, content in (
        (native_report, "<html>native</html>"),
        (report_png, b"\x89PNG\r\n\x1a\nreport"),
        (table, "region\tvalue\nA\t1\n"),
        (map_file, b"nifti"),
    ):
        path.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(content, bytes):
            path.write_bytes(content)
        else:
            path.write_text(content, encoding="utf-8")

    result_summary = {
        "contract_version": "1.0",
        "summary_path": str(output_dir / "summary" / "t1_result_summary.json"),
        "modality": "T1",
        "outputs": {
            "reports": [
                {
                    "name": "sub-01.html",
                    "path": str(native_report),
                    "relative_path": "fmriprep/sub-01.html",
                    "content_type": "text/html",
                    "native_artifact": True,
                    "artifact_origin": "container_output",
                    "source_stage": "fmriprep",
                    "artifact_role": "container_native_html_report",
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
                },
            ],
            "tables": [
                {
                    "name": "regions.tsv",
                    "path": str(table),
                    "relative_path": "tables/regions.tsv",
                    "content_type": "text/tab-separated-values",
                }
            ],
            "maps": [
                {
                    "name": "fa.nii.gz",
                    "path": str(map_file),
                    "relative_path": "maps/fa.nii.gz",
                    "content_type": "application/gzip",
                }
            ],
        },
    }

    manifest = build_artifact_manifest(
        {"id": 7, "project_id": 1, "workflow_type": "t1_deepprep", "status": "completed"},
        output_dir,
        result_summary,
        registered_outputs=[],
    )

    artifacts = {item["relative_path"]: item for item in manifest["artifacts"]}
    assert artifacts["fmriprep/sub-01.html"]["artifact_category"] == "container_native_qc"
    assert artifacts["fmriprep/sub-01.html"]["container_native_qc"] is True
    assert artifacts["fmriprep/sub-01.html"]["derived_scientific_report"] is False

    report = artifacts["reports/t1_qc.png"]
    assert report["artifact_category"] == "derived_scientific_report"
    assert report["container_native_qc"] is False
    assert report["derived_scientific_report"] is True
    assert report["frontend_preview_asset"] is True
    assert report["source_stage"] == "scientific_report"
    assert report["artifact_role"] == "derived_presentation_asset"
    assert report["artifact_origin"] == "generated_from_result_summary"
    assert report["native_artifact"] is False
    assert report["provenance"]["replaces_native_qc"] is False

    assert artifacts["tables/regions.tsv"]["artifact_category"] == "frontend_preview_asset"
    assert artifacts["tables/regions.tsv"]["frontend_preview_asset"] is True
    assert artifacts["maps/fa.nii.gz"]["artifact_category"] == "source_artifact"
    assert artifacts["maps/fa.nii.gz"]["frontend_preview_asset"] is False
    assert manifest["counts_by_artifact_category"] == {
        "container_native_qc": 1,
        "derived_scientific_report": 1,
        "frontend_preview_asset": 1,
        "source_artifact": 1,
    }
    assert '"path":' not in json.dumps(manifest)


def test_artifact_manifest_demotes_native_qc_without_strict_container_provenance(tmp_path):
    output_dir = tmp_path / "output"
    native_like_report = output_dir / "fmriprep" / "sub-01.html"
    native_like_report.parent.mkdir(parents=True)
    native_like_report.write_text("<html>native-looking</html>", encoding="utf-8")

    result_summary = {
        "contract_version": "1.0",
        "modality": "T1",
        "outputs": {
            "reports": [
                {
                    "name": "sub-01.html",
                    "path": str(native_like_report),
                    "relative_path": "fmriprep/sub-01.html",
                    "content_type": "text/html",
                    "native_artifact": True,
                    "source_stage": "fmriprep",
                    "artifact_role": "container_native_html_report",
                    "official_source_ids": ["docs/rag/vendor/fmriprep_official_outputs.md"],
                },
            ],
        },
    }

    manifest = build_artifact_manifest(
        {"id": 8, "project_id": 1, "workflow_type": "t1_deepprep", "status": "completed"},
        output_dir,
        result_summary,
        registered_outputs=[],
    )

    artifact = manifest["artifacts"][0]
    assert artifact["artifact_category"] == "frontend_preview_asset"
    assert artifact["container_native_qc"] is False
    assert artifact["native_artifact"] is False
    assert artifact["frontend_preview_asset"] is True
    assert manifest["counts_by_artifact_category"] == {"frontend_preview_asset": 1}
