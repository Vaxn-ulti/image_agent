import json

from app.workflows.bold_results import write_bold_result_summary_from_outputs


def test_write_bold_result_summary_indexes_real_mni_outputs(tmp_path):
    out = tmp_path
    metrics = ["alff", "falff", "reho", "tsnr", "rsfa", "mean", "std"]
    for metric in metrics:
        (out / f"sub-01_task-rest_space-MNI152NLin6Asym_res-02_desc-{metric}_bold.nii.gz").write_bytes(b"nifti")
    for name in [
        "seed_to_roi",
        "network_dmn",
        "seed_timeseries",
        "fd_timeseries",
        "dvars_timeseries",
        "wholebrain_timeseries",
        "mean_psd",
        "confounds_summary",
    ]:
        (out / f"sub-01_task-rest_desc-{name}.tsv").write_text("a\tb\n1\t2\n", encoding="utf-8")
    masks = out / "masks"
    masks.mkdir()
    (masks / "sub-01_task-rest_space-MNI152NLin6Asym_res-02_desc-brain_mask.nii.gz").write_bytes(b"mask")
    (out / "sub-01_task-rest_desc-bold_metrics_summary.json").write_text(
        json.dumps(
            {
                "metrics": ["alff", "falff", "reho", "dmn", "seed_to_roi"],
                "seeds": [{"preset_id": str(i)} for i in range(15)],
                "n_volumes": 210,
                "tr_seconds": 2.0,
                "masked_voxel_count": 199370,
            }
        ),
        encoding="utf-8",
    )
    (out / "sub-01_task-rest_desc-bold_metrics_provenance.json").write_text(
        json.dumps(
            {
                "preproc_bold": "/source/sub-01_task-rest_space-MNI152NLin6Asym_res-02_desc-preproc_bold.nii.gz",
                "brain_mask": str(masks / "sub-01_task-rest_space-MNI152NLin6Asym_res-02_desc-brain_mask.nii.gz"),
                "tsnr_source_used": False,
                "seed_registry": "app.workflows.bold_seed_registry.DEFAULT_SEED_PRESETS",
            }
        ),
        encoding="utf-8",
    )

    summary_path = write_bold_result_summary_from_outputs(out, task_id=9, workflow_type="bold_second_level")
    summary = json.loads(summary_path.read_text(encoding="utf-8"))

    assert summary_path.name == "bold_result_summary.json"
    assert summary["modality"] == "BOLD"
    assert summary["spaces"] == ["MNI152"]
    assert {"voxelwise_metrics", "connectivity"}.issubset(set(summary["feature_groups"]))
    assert {item["name"] for item in summary["outputs"]["maps"]} >= {"alff", "falff", "reho", "tsnr", "rsfa"}
    assert {item["name"] for item in summary["outputs"]["tables"]} >= {"seed_to_roi", "network_dmn", "seed_timeseries"}
    assert summary["provenance"]["validation_only"] is False
    assert summary["provenance"]["seed_count"] == 15


def test_write_bold_result_summary_requires_real_mni_outputs(tmp_path):
    (tmp_path / "sub-01_task-rest_desc-bold_metrics_summary.json").write_text("{}", encoding="utf-8")

    try:
        write_bold_result_summary_from_outputs(tmp_path, task_id=10, workflow_type="bold_second_level")
    except RuntimeError as exc:
        assert "requires real MNI outputs" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("write_bold_result_summary_from_outputs should reject missing outputs")
