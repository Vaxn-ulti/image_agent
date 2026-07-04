import json
from pathlib import Path

from app.workflows.native_qc import discover_native_qc_outputs, native_qc_artifact
from app.workflows.result_contract import build_result_summary, build_scientific_report_summary, discover_result_summary, result_contract_spec


def test_build_result_summary_has_frontend_sections_and_spaces(tmp_path):
    table = tmp_path / "tables" / "regions.tsv"
    table.parent.mkdir()
    table.write_text("region\tvalue\nctx-lh\t1.0\n", encoding="utf-8")
    nifti = tmp_path / "maps" / "fa_mni152.nii.gz"
    nifti.parent.mkdir()
    nifti.write_bytes(b"nifti")

    summary_path = build_result_summary(
        out_dir=tmp_path,
        task_id=12,
        workflow_type="dwi_fast_gpu_dti",
        modality="DWI",
        spaces=["DWI", "MNI152"],
        feature_groups=["tensor_metrics", "atlas_statistics"],
        outputs={
            "tables": [{"name": "combined_region_dti", "path": table}],
            "maps": [{"name": "fa_mni152", "path": nifti, "space": "MNI152"}],
        },
        provenance={"source": "unit-test"},
    )

    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    assert summary["contract_version"] == "1.0"
    assert summary["task_id"] == 12
    assert summary["workflow_type"] == "dwi_fast_gpu_dti"
    assert summary["modality"] == "DWI"
    assert summary["spaces"] == ["DWI", "MNI152"]
    assert summary["feature_groups"] == ["tensor_metrics", "atlas_statistics"]
    assert summary["outputs"]["tables"][0]["relative_path"] == "tables/regions.tsv"
    assert summary["outputs"]["maps"][0]["space"] == "MNI152"
    assert summary["outputs"]["maps"][0]["size_bytes"] == 5
    assert summary["outputs"]["maps"][0]["content_type"] == "application/gzip"
    assert summary["outputs"]["maps"][0]["download_url"] == "/tasks/12/artifacts/maps/fa_mni152.nii.gz"
    assert Path(summary["summary_path"]).name == "dwi_result_summary.json"
    assert Path(summary["summary_path"]).parent.name == "summary"


def test_build_result_summary_omits_empty_downloadable_outputs(tmp_path):
    valid = tmp_path / "reports" / "sub-01.html"
    empty = tmp_path / "reports" / "sub-01_task-rest_desc-validation_bold.html"
    valid.parent.mkdir()
    valid.write_text("<html>valid</html>", encoding="utf-8")
    empty.write_text("", encoding="utf-8")

    summary_path = build_result_summary(
        out_dir=tmp_path,
        task_id=135,
        workflow_type="bold_fmriprep_xcpd_report",
        modality="BOLD",
        spaces=["MNI152NLin6Asym"],
        feature_groups=["reports"],
        outputs={
            "reports": [
                {"name": valid.name, "path": valid},
                {"name": empty.name, "path": empty},
            ]
        },
        provenance={"source": "unit-test"},
    )

    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    report_paths = [item["relative_path"] for item in summary["outputs"]["reports"]]

    assert report_paths == ["reports/sub-01.html"]


def test_discover_result_summary_prefers_summary_json(tmp_path):
    summary = tmp_path / "summary" / "dwi_result_summary.json"
    summary.parent.mkdir()
    summary.write_text('{"ok": true}', encoding="utf-8")

    assert discover_result_summary(tmp_path) == summary


def test_result_contract_spec_documents_frontend_required_fields():
    spec = result_contract_spec()

    assert spec["summary_endpoint"] == "/tasks/{task_id}/result-summary"
    assert spec["outputs_endpoint"] == "/tasks/{task_id}/outputs"
    for field in ("contract_version", "task_id", "workflow_type", "modality", "spaces", "feature_groups", "outputs", "provenance"):
        assert field in spec["required_top_level_fields"]
    for field in ("relative_path", "download_url", "content_type", "size_bytes"):
        assert field in spec["output_item_fields"]["required"]
    for field in (
        "source_stage",
        "artifact_role",
        "artifact_origin",
        "native_artifact",
        "provenance",
        "official_source_ids",
        "official_source_scope",
    ):
        assert field in spec["output_item_fields"]["common_optional"]
    for modality in ("T1", "BOLD", "DWI"):
        assert "reports" in spec["modalities"][modality]["output_sections"]
        assert "figures" in spec["modalities"][modality]["output_sections"]
    assert spec["modalities"]["BOLD"]["spaces"] == ["MNI152"]
    assert spec["modalities"]["DWI"]["spaces"] == ["DWI", "MNI152"]


def test_native_qc_artifacts_include_curated_official_source_ids(tmp_path):
    cases = [
        ("fmriprep/sub-01.html", "docs/rag/vendor/fmriprep_official_outputs.md"),
        ("xcpd/sub-01/figures/carpetplot.png", "docs/rag/vendor/xcp_d_official_outputs.md"),
        ("deepprep/qc/sub-01.html", "docs/rag/vendor/deepprep_official_container_usage.md"),
        ("freesurfer/sub-01/scripts/recon-all.log", "docs/rag/vendor/freesurfer_official_container_reconall.md"),
        ("qsiprep/sub-01.html", "docs/rag/vendor/qsiprep_official_container_usage_outputs.md"),
        ("qsirecon/sub-01.html", "docs/rag/vendor/qsirecon_official_container_usage_workflows.md"),
        ("mrtrix/dwi2tensor_qc.png", "docs/rag/vendor/mrtrix3_official_dti_toolbox.md"),
        ("fsl/dtifit.log", "docs/rag/vendor/fsl_official_fast_dti_tools.md"),
    ]
    for relative_path, expected_source_id in cases:
        path = tmp_path / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("artifact", encoding="utf-8")

        artifact = native_qc_artifact(path, tmp_path, "container_native_qc_figure", pipeline="unit-test")

        assert expected_source_id in artifact["official_source_ids"]
        assert expected_source_id in artifact["provenance"]["official_source_ids"]
        assert all("/raw-sources/" not in source_id for source_id in artifact["official_source_ids"])


def test_discover_native_qc_outputs_preserves_official_source_ids(tmp_path):
    report = tmp_path / "xcpd" / "sub-01.html"
    figure = tmp_path / "fmriprep" / "sub-01" / "figures" / "boldref.svg"
    report.parent.mkdir(parents=True)
    figure.parent.mkdir(parents=True)
    report.write_text("<html>xcpd report</html>", encoding="utf-8")
    figure.write_text("<svg></svg>", encoding="utf-8")

    outputs = discover_native_qc_outputs(tmp_path, pipeline="bold_fmriprep_xcpd_report")

    report_artifact = outputs["reports"][0]
    figure_artifact = outputs["figures"][0]
    assert "docs/rag/vendor/xcp_d_official_outputs.md" in report_artifact["official_source_ids"]
    assert "docs/rag/vendor/fmriprep_official_outputs.md" in figure_artifact["official_source_ids"]
    assert report_artifact["provenance"]["official_source_ids"] == report_artifact["official_source_ids"]


def test_dwi_pipeline_generic_qc_artifacts_use_dwi_tool_grounding(tmp_path):
    qc_report = tmp_path / "qc" / "index.html"
    qc_report.parent.mkdir(parents=True)
    qc_report.write_text("<html>DWI QC</html>", encoding="utf-8")

    artifact = native_qc_artifact(qc_report, tmp_path, "container_native_html_report", pipeline="dwi_fast_gpu_dti")

    assert artifact["source_stage"] != "deepprep"
    assert "docs/rag/vendor/deepprep_official_container_usage.md" not in artifact["official_source_ids"]
    assert set(artifact["official_source_ids"]) == {
        "docs/rag/vendor/fsl_official_fast_dti_tools.md",
        "docs/rag/vendor/mrtrix3_official_dti_toolbox.md",
    }


def test_build_scientific_report_summary_indexes_report_artifacts(tmp_path):
    html = tmp_path / "reports" / "index.html"
    png = tmp_path / "reports" / "figure.png"
    html.parent.mkdir(parents=True)
    html.write_text("<html></html>", encoding="utf-8")
    png.write_bytes(b"\x89PNG\r\n\x1a\n")

    summary_path = build_scientific_report_summary(
        out_dir=tmp_path,
        task_id=13,
        workflow_type="t1_deepprep",
        modality="T1",
        spaces=["T1w", "MNI152"],
        feature_groups=["segmentation_volumes"],
        report_items=[
            {"name": "scientific_report_index", "path": html},
            {"name": "scientific_report_figure", "path": png},
        ],
        provenance={"source_summary": "summary/t1_result_summary.json"},
    )

    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    assert summary["feature_groups"] == ["segmentation_volumes", "scientific_report"]
    assert "reports" in summary["outputs"]
    assert summary["outputs"]["reports"][0]["content_type"] == "text/html"
    assert summary["outputs"]["reports"][1]["content_type"] == "image/png"
    assert summary["outputs"]["reports"][0]["download_url"] == "/tasks/13/artifacts/reports/index.html"
    assert summary["spaces"] == ["T1w", "MNI152"]
    for report in summary["outputs"]["reports"]:
        assert report["source_stage"] == "scientific_report"
        assert report["artifact_role"] == "derived_presentation_asset"
        assert report["artifact_origin"] == "generated_from_result_summary"
        assert report["native_artifact"] is False
        assert report["provenance"]["replaces_native_qc"] is False
        assert report["provenance"]["generated_from"] == "result_summary"


def test_scientific_report_summary_backfills_main_result_summary(tmp_path):
    summary = tmp_path / "summary" / "t1_result_summary.json"
    summary.parent.mkdir(parents=True)
    summary.write_text(
        json.dumps(
            {
                "contract_version": "1.0",
                "task_id": 21,
                "workflow_type": "t1_deepprep",
                "modality": "T1",
                "spaces": ["T1w", "MNI152"],
                "feature_groups": ["segmentation_volumes"],
                "outputs": {},
                "provenance": {},
                "summary_path": str(summary),
            }
        ),
        encoding="utf-8",
    )
    reports_dir = tmp_path / "reports"
    reports_dir.mkdir()
    (reports_dir / "index.html").write_text("<html></html>", encoding="utf-8")
    (reports_dir / "manifest.json").write_text("{}", encoding="utf-8")

    from app.workflows.scientific_reports import build_scientific_report_summary as build_report

    report_summary_path = build_report(
        out_dir=tmp_path,
        task_id=21,
        workflow_type="t1_deepprep",
        summary=json.loads(summary.read_text(encoding="utf-8")),
    )

    report_summary = json.loads(report_summary_path.read_text(encoding="utf-8"))
    main_summary = json.loads(summary.read_text(encoding="utf-8"))
    assert report_summary["outputs"]["reports"]
    assert "reports" in main_summary["outputs"]
    assert main_summary["provenance"]["scientific_report_summary_path"] == str(report_summary_path)


def test_scientific_report_backfill_preserves_existing_native_reports(tmp_path):
    summary = tmp_path / "summary" / "bold_result_summary.json"
    native_report = tmp_path / "fmriprep" / "sub-01.html"
    native_report.parent.mkdir(parents=True)
    native_report.write_text("<html>native report</html>", encoding="utf-8")
    summary.parent.mkdir(parents=True)
    summary.write_text(
        json.dumps(
            {
                "contract_version": "1.0",
                "task_id": 118,
                "workflow_type": "bold_fmriprep_xcpd_report",
                "modality": "BOLD",
                "spaces": ["MNI152"],
                "feature_groups": ["preprocessing", "reports"],
                "outputs": {
                    "reports": [
                        {
                            "name": "sub-01.html",
                            "path": str(native_report),
                            "relative_path": "fmriprep/sub-01.html",
                            "content_type": "text/html",
                            "native_artifact": True,
                            "source_stage": "fmriprep",
                            "artifact_role": "container_native_html_report",
                        }
                    ]
                },
                "provenance": {},
                "summary_path": str(summary),
            }
        ),
        encoding="utf-8",
    )

    from app.workflows.scientific_reports import build_scientific_report_summary as build_report

    for _ in range(2):
        build_report(
            out_dir=tmp_path,
            task_id=118,
            workflow_type="bold_fmriprep_xcpd_report",
            summary=json.loads(summary.read_text(encoding="utf-8")),
        )

    main_summary = json.loads(summary.read_text(encoding="utf-8"))
    reports = main_summary["outputs"]["reports"]
    by_relative_path = {item["relative_path"]: item for item in reports}
    assert by_relative_path["fmriprep/sub-01.html"]["native_artifact"] is True
    assert by_relative_path["reports/index.html"]["artifact_role"] == "derived_presentation_asset"
    assert by_relative_path["reports/report_manifest.json"]["artifact_origin"] == "generated_from_result_summary"
    assert [item["relative_path"] for item in reports].count("reports/index.html") == 1
    assert [item["relative_path"] for item in reports].count("fmriprep/sub-01.html") == 1


def test_scientific_report_bundle_uses_png_figures_for_all_indicator_modalities(tmp_path):
    from app.workflows.scientific_reports import build_scientific_report_summary as build_report

    def write_tsv(path: Path, rows: str) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(rows, encoding="utf-8")
        return path

    cases = [
        (
            "T1",
            "t1_deepprep",
            {
                "tables": [
                    {
                        "name": "t1_brain_measures",
                        "path": write_tsv(
                            tmp_path / "t1" / "tables" / "brain.tsv",
                            "measure\tvalue\tunit\nBrainSegVol\t1200\tmm3\nCortexVol\t860\tmm3\n",
                        ),
                    },
                    {
                        "name": "t1_t1w_regions",
                        "path": write_tsv(
                            tmp_path / "t1" / "tables" / "regions.tsv",
                            "region\tcortical_thickness_mm\nctx-lh-a\t2.3\nctx-lh-b\t2.7\n",
                        ),
                    },
                ]
            },
        ),
        (
            "BOLD",
            "bold_second_level",
            {
                "tables": [
                    {
                        "name": "seed_to_roi",
                        "path": write_tsv(
                            tmp_path / "bold" / "tables" / "seed.tsv",
                            "seed_id\troi_id\tcorrelation_r\ns1\ts1\t1\ns1\ts2\t0.2\ns2\ts1\t0.1\ns2\ts2\t1\n",
                        ),
                    },
                    {
                        "name": "fd_timeseries",
                        "path": write_tsv(
                            tmp_path / "bold" / "tables" / "fd.tsv",
                            "volume_index\tframewise_displacement\n0\t0.01\n1\t0.03\n2\t0.02\n",
                        ),
                    },
                ],
                "summaries": [
                    {
                        "name": "bold_metrics_summary",
                        "path": tmp_path / "bold" / "summary" / "metrics.json",
                    }
                ],
            },
        ),
        (
            "DWI",
            "dwi_fast_gpu_dti",
            {
                "tables": [
                    {
                        "name": "combined_region_dti",
                        "path": write_tsv(
                            tmp_path / "dwi" / "tables" / "combined.tsv",
                            "region\tfa\tmd\tad\trd\tatlas\nA\t0.41\t0.001\t0.002\t0.0007\tJHU\nB\t0.52\t0.0011\t0.0022\t0.0008\tJHU\n",
                        ),
                    }
                ]
            },
        ),
    ]
    (tmp_path / "bold" / "summary").mkdir(parents=True, exist_ok=True)
    (tmp_path / "bold" / "summary" / "metrics.json").write_text(
        json.dumps({"voxelwise_means": {"ALFF": 0.7, "fALFF": 0.31, "tSNR": 54.2}}),
        encoding="utf-8",
    )

    for idx, (modality, workflow_type, outputs) in enumerate(cases, start=1):
        out_dir = tmp_path / modality.lower()
        summary_path = out_dir / "summary" / f"{modality.lower()}_result_summary.json"
        summary_path.parent.mkdir(parents=True, exist_ok=True)
        summary = {
            "contract_version": "1.0",
            "task_id": idx,
            "workflow_type": workflow_type,
            "modality": modality,
            "spaces": ["MNI152"],
            "feature_groups": ["indicator_display"],
            "outputs": outputs,
            "provenance": {"runtime_sec": 12, "atlas": "JHU"},
            "summary_path": str(summary_path),
        }
        summary_path.write_text(json.dumps(summary, default=str), encoding="utf-8")

        report_summary_path = build_report(out_dir, idx, workflow_type, summary)

        report_summary = json.loads(report_summary_path.read_text(encoding="utf-8"))
        report_items = report_summary["outputs"]["reports"]
        png_items = [item for item in report_items if item["relative_path"].endswith(".png")]
        assert png_items, modality
        assert all(item["content_type"] == "image/png" for item in png_items)
        manifest = json.loads((out_dir / "reports" / "report_manifest.json").read_text(encoding="utf-8"))
        assert all(not asset.endswith(".svg") for asset in manifest["assets"])
        assert any(asset.endswith(".png") for asset in manifest["assets"])
        html = (out_dir / "reports" / "index.html").read_text(encoding="utf-8")
        assert ".png" in html
