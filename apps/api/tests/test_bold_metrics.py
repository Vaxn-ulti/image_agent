import json
import sys
import types
from pathlib import Path

from app.workflows import bold_metrics


def test_bold_metrics_writes_structured_outputs(tmp_path):
    bids_dir = tmp_path / "bids"
    out_dir = tmp_path / "out"
    bids_dir.mkdir()

    summary_path = bold_metrics.run_metrics(
        bids_dir=bids_dir,
        out_dir=out_dir,
        metrics=["alff", "falff", "reho", "tsnr"],
        seed_presets=["PCC_DMN"],
        subject_id="01",
        task_label="rest",
    )

    summary = json.loads(Path(summary_path).read_text(encoding="utf-8"))
    assert summary["metrics"] == ["alff", "falff", "reho", "tsnr"]
    assert summary["seeds"][0]["preset_id"] == "PCC_DMN"
    assert (out_dir / "summary" / "bold_metrics_summary.json").exists()
    assert (out_dir / "tables" / "seed_to_roi.tsv").exists()
    assert (out_dir / "maps" / "alff.nii.gz").exists()
    assert (out_dir / "figures" / "PCC_DMN_seed_fc_stat.png").exists()


def test_bold_metrics_default_profile_writes_requested_mni_second_level_outputs(tmp_path):
    bids_dir = tmp_path / "bids"
    out_dir = tmp_path / "out"
    bids_dir.mkdir()

    summary_path = bold_metrics.run_metrics(
        bids_dir=bids_dir,
        out_dir=out_dir,
        metrics=bold_metrics.DEFAULT_METRICS,
        seed_presets=None,
        subject_id="01",
        task_label="rest",
    )

    summary = json.loads(Path(summary_path).read_text(encoding="utf-8"))
    assert {"alff", "falff", "reho", "dmn", "seed_to_roi"}.issubset(set(summary["metrics"]))
    assert summary["spaces"] == ["MNI152"]
    assert len(summary["seeds"]) == 15
    assert summary["modality"] == "BOLD"
    assert summary["contract_version"] == "1.0"
    assert (out_dir / "tables" / "network_dmn.tsv").exists()
    assert (out_dir / "tables" / "seed_to_roi.tsv").exists()
    assert (out_dir / "maps" / "dmn.nii.gz").exists()


def test_compute_bold_metrics_bundle_requires_neuroimaging_dependencies(monkeypatch, tmp_path):
    real_find_spec = bold_metrics.importlib.util.find_spec

    def fake_find_spec(name):
        if name in {"numpy", "nibabel"}:
            return None
        return real_find_spec(name)

    monkeypatch.setattr(bold_metrics.importlib.util, "find_spec", fake_find_spec)

    try:
        bold_metrics.compute_bold_metrics_bundle(
            metric="ALFF",
            preproc_bold=tmp_path / "bold.nii.gz",
            bold_json=tmp_path / "bold.json",
            brain_mask=tmp_path / "mask.nii.gz",
            confounds_tsv=tmp_path / "confounds.tsv",
            output_dir=tmp_path / "out",
        )
    except RuntimeError as exc:
        assert "numpy and nibabel" in str(exc)
    else:
        raise AssertionError("expected missing dependency failure")


def test_compute_bold_metrics_bundle_writes_real_outputs_with_stubbed_dependencies(monkeypatch, tmp_path):
    class FakeImage:
        affine = "affine"
        header = {}

        def __init__(self, data):
            self.dataobj = data

    class FakeArray(list):
        shape = (2, 2, 2, 8)
        ndim = 4

    class FakeNP(types.SimpleNamespace):
        float32 = "float32"
        float64 = "float64"

        def asarray(self, value, dtype=None):
            return value

    fake_np = FakeNP()
    fake_nib = types.SimpleNamespace(
        load=lambda path: FakeImage(FakeArray()),
        Nifti1Image=lambda data, affine, header: FakeImage(data),
        save=lambda image, path: Path(path).write_bytes(b"nifti"),
    )

    monkeypatch.setitem(sys.modules, "numpy", fake_np)
    monkeypatch.setitem(sys.modules, "nibabel", fake_nib)
    monkeypatch.setattr(bold_metrics.importlib.util, "find_spec", lambda name: object())
    monkeypatch.setattr(
        bold_metrics,
        "_compute_real_metric_maps",
        lambda np, data, mask, tr: {
            "alff": [[1.0]],
            "falff": [[0.5]],
            "reho": [[0.1]],
            "tsnr": [[2.0]],
            "rsfa": [[0.2]],
            "mean": [[10.0]],
            "std": [[1.0]],
            "mean_psd_rows": [(0.01, 1.0)],
        },
    )

    bold_json = tmp_path / "bold.json"
    confounds = tmp_path / "confounds.tsv"
    bold_json.write_text('{"RepetitionTime": 2.0}', encoding="utf-8")
    confounds.write_text("framewise_displacement\tdvars\n0.1\t1.0\n", encoding="utf-8")

    outputs = bold_metrics.compute_bold_metrics_bundle(
        metric="ALFF",
        preproc_bold=tmp_path / "sub-01_task-rest_space-MNI152_desc-preproc_bold.nii.gz",
        bold_json=bold_json,
        brain_mask=tmp_path / "mask.nii.gz",
        confounds_tsv=confounds,
        output_dir=tmp_path / "out",
    )

    assert Path(outputs["summary_json"]).exists()
    assert Path(outputs["alff_bold"]).read_bytes() == b"nifti"
    summary = json.loads(Path(outputs["summary_json"]).read_text(encoding="utf-8"))
    assert summary["method"] == "real_bold_metric_engine"
    assert summary["primary_metric"] == "ALFF"
