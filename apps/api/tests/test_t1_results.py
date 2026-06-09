import json

from app.workflows.t1_results import write_t1_result_summary


def test_write_t1_result_summary_declares_native_and_mni_spaces(tmp_path):
    summary_path = write_t1_result_summary(
        out_dir=tmp_path,
        task_id=8,
        workflow_type="t1_deepprep",
    )

    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    assert summary["modality"] == "T1"
    assert summary["spaces"] == ["T1w", "MNI152"]
    assert {"segmentation_volumes", "cortical_thickness", "surface_area", "regional_morphometry"}.issubset(set(summary["feature_groups"]))
    tables = {item["name"] for item in summary["outputs"]["tables"]}
    assert "t1_t1w_regions" in tables
    assert "t1_mni152_regions" in tables
    assert summary["provenance"]["placeholder_outputs"] is True
    assert summary["provenance"]["extraction_status"] == "placeholder_contract_pending_real_deepprep_parser"


def test_write_t1_result_summary_parses_real_deepprep_freesurfer_stats(tmp_path):
    recon = tmp_path / "Recon" / "sub-01"
    stats = recon / "stats"
    stats.mkdir(parents=True)
    (recon / "mri").mkdir()
    (recon / "mri" / "transforms").mkdir()
    (recon / "mri" / "aparc+aseg.mgz").write_bytes(b"mgz")
    (recon / "mri" / "brain.mgz").write_bytes(b"mgz")
    (recon / "mri" / "transforms" / "talairach.xfm").write_text("xfm", encoding="utf-8")

    (stats / "brainvol.stats").write_text(
        "\n".join(
            [
                "# Measure BrainSeg, BrainSegVol, Brain Segmentation Volume, 938722.000000000000, mm^3",
                "# Measure Cortex, CortexVol, Total cortical gray matter volume, 356684.788540834677, mm^3",
                "# Measure EstimatedTotalIntraCranialVol, eTIV, Estimated Total Intracranial Volume, 1358222.452538, mm^3",
            ]
        ),
        encoding="utf-8",
    )
    aparc_text = "\n".join(
        [
            "# Table of FreeSurfer cortical parcellation anatomical statistics",
            "# ColHeaders StructName NumVert SurfArea GrayVol ThickAvg ThickStd MeanCurv GausCurv FoldInd CurvInd",
            "bankssts 1227 925 1890 2.133 0.453 0.104 0.021 5 1.1",
            "entorhinal 605 452 1654 2.656 0.844 0.127 0.029 6 0.7",
        ]
    )
    (stats / "lh.aparc.stats").write_text(aparc_text, encoding="utf-8")
    (stats / "rh.aparc.stats").write_text(aparc_text.replace("2.133", "2.222"), encoding="utf-8")
    (stats / "lh.w-g.pct.stats").write_text(
        "\n".join(
            [
                "# ColHeaders Index SegId NVertices Area_mm2 StructName Mean StdDev Min Max Range SNR",
                "1 1001 10 22.5 bankssts 48.0 3.0 42.0 53.0 11.0 16.0",
            ]
        ),
        encoding="utf-8",
    )

    summary_path = write_t1_result_summary(
        out_dir=tmp_path,
        task_id=45,
        workflow_type="t1_deepprep",
    )

    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    assert summary["provenance"]["placeholder_outputs"] is False
    assert summary["provenance"]["extraction_status"] == "real_deepprep_freesurfer_stats"
    assert summary["provenance"]["source_stats_files"]["brainvol"].endswith("brainvol.stats")
    assert summary["spaces"] == ["T1w", "MNI152"]

    table_names = {item["name"] for item in summary["outputs"]["tables"]}
    assert {"t1_brain_measures", "t1_t1w_regions", "t1_freesurfer_stats_inventory"}.issubset(table_names)
    assert "freesurfer_lh_w_g_pct" in table_names
    map_names = {item["name"] for item in summary["outputs"]["maps"]}
    assert {"t1_aparc_aseg", "t1_brain"}.issubset(map_names)
    transform_names = {item["name"] for item in summary["outputs"]["transforms"]}
    assert "talairach_xfm" in transform_names

    brain_table = tmp_path / "tables" / "t1_brain_measures.tsv"
    region_table = tmp_path / "tables" / "t1_t1w_regions.tsv"
    assert "BrainSegVol" in brain_table.read_text(encoding="utf-8")
    region_text = region_table.read_text(encoding="utf-8")
    assert "ctx-lh-bankssts" in region_text
    assert "ctx-rh-entorhinal" in region_text
    assert "2.656" in region_text
    inventory = tmp_path / "tables" / "t1_freesurfer_stats_inventory.tsv"
    assert "lh.w-g.pct.stats" in inventory.read_text(encoding="utf-8")
    copied = tmp_path / "tables" / "freesurfer_stats" / "lh.w-g.pct.tsv"
    assert copied.exists()
    assert summary["provenance"]["parsed_counts"]["stats_files"] == 4
    assert any(profile["file"] == "lh.w-g.pct.stats" and profile["data_row_count"] == 1 for profile in summary["provenance"]["stats_files"])


def test_write_t1_result_summary_registers_native_deepprep_qc_reports_and_figures(tmp_path):
    recon = tmp_path / "Recon" / "sub-01"
    stats = recon / "stats"
    stats.mkdir(parents=True)
    (stats / "brainvol.stats").write_text(
        "# Measure BrainSeg, BrainSegVol, Brain Segmentation Volume, 938722.0, mm^3\n",
        encoding="utf-8",
    )
    aparc_text = "\n".join(
        [
            "# ColHeaders StructName NumVert SurfArea GrayVol ThickAvg ThickStd MeanCurv GausCurv FoldInd CurvInd",
            "bankssts 1227 925 1890 2.133 0.453 0.104 0.021 5 1.1",
        ]
    )
    (stats / "lh.aparc.stats").write_text(aparc_text, encoding="utf-8")
    (stats / "rh.aparc.stats").write_text(aparc_text, encoding="utf-8")
    qc_dir = tmp_path / "DeepPrep" / "QC" / "sub-01"
    figures_dir = qc_dir / "figures"
    figures_dir.mkdir(parents=True)
    (qc_dir / "index.html").write_text("<html>DeepPrep QC</html>", encoding="utf-8")
    (figures_dir / "anat_preview.png").write_bytes(b"png")

    summary_path = write_t1_result_summary(
        out_dir=tmp_path,
        task_id=46,
        workflow_type="t1_deepprep",
    )

    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    reports = summary["outputs"]["reports"]
    figures = summary["outputs"]["figures"]

    assert reports[0]["relative_path"] == "DeepPrep/QC/sub-01/index.html"
    assert reports[0]["source_stage"] == "deepprep"
    assert reports[0]["artifact_role"] == "container_native_html_report"
    assert reports[0]["native_artifact"] is True
    assert reports[0]["provenance"]["replaces_native_qc"] is False
    assert figures[0]["relative_path"] == "DeepPrep/QC/sub-01/figures/anat_preview.png"
    assert figures[0]["source_stage"] == "deepprep"
    assert figures[0]["artifact_role"] == "container_native_qc_figure"
    assert figures[0]["native_artifact"] is True
    assert figures[0]["content_type"] == "image/png"
