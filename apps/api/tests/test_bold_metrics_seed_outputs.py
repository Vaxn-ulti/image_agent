import json
from pathlib import Path

import nibabel as nib
import numpy as np

from app.workflows.bold_metrics import compute_bold_metrics_bundle


def test_real_bold_metric_bundle_writes_seed_to_roi_and_dmn_outputs(tmp_path):
    rng = np.random.default_rng(123)
    data = rng.normal(size=(5, 5, 5, 12)).astype(np.float32)
    data[1:4, 1:4, 1:4, :] += np.linspace(0, 1, 12, dtype=np.float32)
    preproc = tmp_path / "sub-01_task-rest_space-MNI152NLin6Asym_desc-preproc_bold.nii.gz"
    mask = tmp_path / "sub-01_task-rest_space-MNI152NLin6Asym_desc-brain_mask.nii.gz"
    bold_json = tmp_path / "sub-01_task-rest_space-MNI152NLin6Asym_desc-preproc_bold.json"
    confounds = tmp_path / "sub-01_task-rest_desc-confounds_timeseries.tsv"
    mask_data = np.zeros((5, 5, 5), dtype=np.uint8)
    mask_data[1:4, 1:4, 1:4] = 1
    nib.save(nib.Nifti1Image(data, np.eye(4)), preproc)
    nib.save(nib.Nifti1Image(mask_data, np.eye(4)), mask)
    bold_json.write_text('{"RepetitionTime": 2.0}', encoding="utf-8")
    confounds.write_text("framewise_displacement\tdvars\n" + "\n".join("0.01\t0.02" for _ in range(12)), encoding="utf-8")

    outputs = compute_bold_metrics_bundle(
        metric="ALFF",
        preproc_bold=preproc,
        bold_json=bold_json,
        brain_mask=mask,
        confounds_tsv=confounds,
        output_dir=tmp_path / "out",
    )

    seed_to_roi = Path(outputs["seed_to_roi_tsv"])
    network_dmn = Path(outputs["network_dmn_tsv"])
    seed_timeseries = Path(outputs["seed_timeseries_tsv"])
    assert seed_to_roi.exists()
    assert network_dmn.exists()
    assert seed_timeseries.exists()
    assert len(seed_to_roi.read_text(encoding="utf-8").strip().splitlines()) == 226
    summary = json.loads(Path(outputs["summary_json"]).read_text(encoding="utf-8"))
    assert len(summary["seeds"]) == 15
    assert "seed_to_roi" in summary["metrics"]
    assert summary["outputs"]["network_dmn"] == network_dmn.name


def test_real_bold_metric_bundle_ignores_tsnr_source_with_mismatched_shape(tmp_path):
    rng = np.random.default_rng(456)
    data = rng.normal(size=(5, 5, 5, 12)).astype(np.float32)
    mask_data = np.zeros((5, 5, 5), dtype=np.uint8)
    mask_data[1:4, 1:4, 1:4] = 1
    preproc = tmp_path / "sub-01_task-rest_space-MNI152NLin6Asym_desc-preproc_bold.nii.gz"
    mask = tmp_path / "sub-01_task-rest_space-MNI152NLin6Asym_desc-brain_mask.nii.gz"
    tsnr_source = tmp_path / "sub-01_task-rest_space-T1w_desc-tsnr_bold.nii.gz"
    bold_json = tmp_path / "sub-01_task-rest_space-MNI152NLin6Asym_desc-preproc_bold.json"
    confounds = tmp_path / "sub-01_task-rest_desc-confounds_timeseries.tsv"
    nib.save(nib.Nifti1Image(data, np.eye(4)), preproc)
    nib.save(nib.Nifti1Image(mask_data, np.eye(4)), mask)
    nib.save(nib.Nifti1Image(np.ones((3, 3, 3), dtype=np.float32), np.eye(4)), tsnr_source)
    bold_json.write_text('{"RepetitionTime": 2.0}', encoding="utf-8")
    confounds.write_text("framewise_displacement\tdvars\n" + "\n".join("0.01\t0.02" for _ in range(12)), encoding="utf-8")

    outputs = compute_bold_metrics_bundle(
        metric="ALFF",
        preproc_bold=preproc,
        bold_json=bold_json,
        brain_mask=mask,
        confounds_tsv=confounds,
        output_dir=tmp_path / "out",
        tsnr_source=tsnr_source,
    )

    tsnr_img = nib.load(outputs["tsnr_bold"])
    assert tsnr_img.shape == data.shape[:3]
    provenance = json.loads(Path(outputs["provenance_json"]).read_text(encoding="utf-8"))
    assert provenance["tsnr_source_used"] is False
    assert provenance["tsnr_source_ignored_reason"] == "shape_mismatch_or_unreadable"
