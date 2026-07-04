import json
from pathlib import Path

import nibabel as nib
import numpy as np

from app.workflows import dwi_fast_dti


def test_fast_dti_command_uses_script_runner_with_fsl_gpu_eddy_and_mrtrix_toolbox(tmp_path):
    dirs = {
        "root": tmp_path,
        "bids": tmp_path / "bids",
        "output": tmp_path / "output",
        "work": tmp_path / "work",
    }
    dwi_dir = dirs["bids"] / "sub-01" / "dwi"
    dwi_dir.mkdir(parents=True)
    (dwi_dir / "sub-01_dwi.nii.gz").write_bytes(b"nifti")
    (dwi_dir / "sub-01_dwi.bval").write_text("0 1000 1000\n", encoding="utf-8")
    (dwi_dir / "sub-01_dwi.bvec").write_text("1 0 0\n0 1 0\n0 0 1\n", encoding="utf-8")
    (dwi_dir / "sub-01_dwi.json").write_text('{"PhaseEncodingDirection":"j","TotalReadoutTime":0.05}', encoding="utf-8")

    cmd = dwi_fast_dti.build_command(dirs)
    command_text = " ".join(str(part) for part in cmd)

    assert cmd[1:4] == ["-m", "app.workflows.dwi_fast_dti", "run"]
    assert "--bids" in cmd
    assert "--out" in cmd
    assert "--work" in cmd
    assert "--resources" in cmd
    assert "--fsl-dir" in cmd
    assert str(dwi_fast_dti.FSL_DIR) in cmd
    assert "--mrtrix-image" in cmd
    assert dwi_fast_dti.MRTRIX_IMAGE in cmd
    assert "--require-gpu-eddy" in cmd
    assert "--max-runtime-sec" in cmd
    assert str(dwi_fast_dti.MAX_RUNTIME_SEC) in cmd
    assert dwi_fast_dti.MAX_RUNTIME_SEC == 2100
    assert "qsiprep /data /out participant" not in command_text
    assert "qsirecon" not in command_text.lower()
    assert "--eddy-config" not in command_text
    assert "combined_region_dti.tsv" not in command_text


def test_fast_dti_requires_dwi_json_sidecar(tmp_path):
    dirs = {
        "root": tmp_path,
        "bids": tmp_path / "bids",
        "output": tmp_path / "output",
        "work": tmp_path / "work",
    }
    dwi_dir = dirs["bids"] / "sub-01" / "dwi"
    dwi_dir.mkdir(parents=True)
    (dwi_dir / "sub-01_dwi.nii.gz").write_bytes(b"nifti")
    (dwi_dir / "sub-01_dwi.bval").write_text("0 1000 1000\n", encoding="utf-8")
    (dwi_dir / "sub-01_dwi.bvec").write_text("1 0 0\n0 1 0\n0 0 1\n", encoding="utf-8")

    try:
        dwi_fast_dti.build_command(dirs)
    except RuntimeError as exc:
        assert "sub-01_dwi.json" in str(exc)
    else:  # pragma: no cover - defensive clarity for regression failures
        raise AssertionError("build_command should require sub-01_dwi.json")


def test_select_dti_volume_indices_reduces_multishell_qspace_to_lightweight_dti_subset():
    bvals = [
        0,
        0,
        200,
        400,
        550,
        *([750, 950, 1150] * 20),
        *([1700, 2100, 3000] * 20),
    ]

    selected, metadata = dwi_fast_dti.select_dti_volume_indices(
        bvals,
        max_b0=1,
        max_directions=36,
        min_directions=12,
    )

    selected_bvals = [bvals[index] for index in selected]
    assert selected_bvals.count(0) == 1
    assert len([value for value in selected_bvals if value > 50]) == 36
    assert all(700 <= value <= 1300 for value in selected_bvals if value > 50)
    assert 1700 not in selected_bvals
    assert 2100 not in selected_bvals
    assert 3000 not in selected_bvals
    assert metadata["full_volume_count"] == len(bvals)
    assert metadata["selected_volume_count"] == 37
    assert metadata["selection_strategy"] == "target_bval_window"
    assert metadata["max_directions"] == 36


def test_run_fast_dti_uses_subset_inputs_for_mask_eddy_and_tensor(monkeypatch, tmp_path):
    bids_dir = tmp_path / "bids"
    out_dir = tmp_path / "output"
    work_dir = tmp_path / "work"
    resources_dir = tmp_path / "resources"
    dwi_dir = bids_dir / "sub-01" / "dwi"
    dwi_dir.mkdir(parents=True)
    out_dir.mkdir()
    resources_dir.mkdir()
    (dwi_dir / "sub-01_dwi.nii.gz").write_bytes(b"full-dwi")
    (dwi_dir / "sub-01_dwi.bval").write_text("0 750 950 1150 1700\n", encoding="utf-8")
    (dwi_dir / "sub-01_dwi.bvec").write_text("1 0 0 0 0\n0 1 0 0 0\n0 0 1 0 0\n", encoding="utf-8")
    (dwi_dir / "sub-01_dwi.json").write_text('{"PhaseEncodingDirection":"j-","TotalReadoutTime":0.05}', encoding="utf-8")
    (resources_dir / dwi_fast_dti.MNI_TEMPLATE_FILENAME).write_bytes(b"template")
    (resources_dir / dwi_fast_dti.MNI_ATLAS_METADATA_FILENAME).write_text("{}", encoding="utf-8")

    subset_paths = {
        "dwi": work_dir / "sub-01_dti_subset.nii.gz",
        "bval": work_dir / "sub-01_dti_subset.bval",
        "bvec": work_dir / "sub-01_dti_subset.bvec",
        "json": work_dir / "sub-01_dti_subset.json",
    }
    captured = []

    def fake_write_subset(*args, **kwargs):
        work_dir.mkdir(parents=True, exist_ok=True)
        for key, path in subset_paths.items():
            if key == "json":
                path.write_text('{"ImageAgentDtiSubset":{"selected_volume_count":4}}', encoding="utf-8")
            else:
                path.write_text("subset", encoding="utf-8")
        return subset_paths

    def fake_run_logged(cmd, *args, **kwargs):
        captured.append(" ".join(str(part) for part in cmd))

    monkeypatch.setattr(dwi_fast_dti, "validate_inputs", lambda dirs: None)
    monkeypatch.setattr(dwi_fast_dti, "prepare_mni_resources", lambda dirs: {"template": resources_dir / dwi_fast_dti.MNI_TEMPLATE_FILENAME})
    monkeypatch.setattr(dwi_fast_dti, "write_dti_subset", fake_write_subset)
    monkeypatch.setattr(dwi_fast_dti, "_write_eddy_files", lambda json_path, bval_path, target_work_dir: None)
    monkeypatch.setattr(dwi_fast_dti, "_sudo_password", lambda: "pw")
    monkeypatch.setattr(dwi_fast_dti, "_run_logged", fake_run_logged)
    monkeypatch.setattr(dwi_fast_dti, "_fsl_bin", lambda fsl_dir, name: tmp_path / name)
    monkeypatch.setattr(dwi_fast_dti, "_fsl_env", lambda fsl_dir: {})
    monkeypatch.setattr(dwi_fast_dti, "_valid_affine_matrix", lambda path: True)
    monkeypatch.setattr(dwi_fast_dti, "_mni_map_has_signal", lambda path, template_path: True)
    monkeypatch.setattr(dwi_fast_dti, "_write_region_tables", lambda *args, **kwargs: None)
    monkeypatch.setattr(dwi_fast_dti, "_sanitize_metric_maps", lambda *args, **kwargs: {})
    monkeypatch.setattr(
        dwi_fast_dti,
        "write_result_summary_from_outputs",
        lambda out_dir, task_id, workflow_type: tmp_path / "summary.json",
    )

    dwi_fast_dti.run_fast_dti(
        bids_dir=bids_dir,
        out_dir=out_dir,
        work_dir=work_dir,
        resources_dir=resources_dir,
        fsl_dir=tmp_path,
        max_runtime_sec=2100,
        task_id=99,
    )

    joined = "\n".join(captured)
    assert "/work/sub-01_dti_subset.nii.gz" in joined
    assert "/work/sub-01_dti_subset.bval" in joined
    assert "/work/sub-01_dti_subset.bvec" in joined
    assert str(subset_paths["dwi"]) in joined
    assert str(subset_paths["bval"]) in joined
    assert str(dwi_dir / "sub-01_dwi.nii.gz") not in joined


def test_run_fast_dti_applies_mni_affine_with_flirt_not_applywarp(monkeypatch, tmp_path):
    bids_dir = tmp_path / "bids"
    out_dir = tmp_path / "output"
    work_dir = tmp_path / "work"
    resources_dir = tmp_path / "resources"
    dwi_dir = bids_dir / "sub-01" / "dwi"
    dwi_dir.mkdir(parents=True)
    resources_dir.mkdir()
    (dwi_dir / "sub-01_dwi.nii.gz").write_bytes(b"full-dwi")
    (dwi_dir / "sub-01_dwi.bval").write_text("0 1000 1000 1000\n", encoding="utf-8")
    (dwi_dir / "sub-01_dwi.bvec").write_text("1 0 0 0\n0 1 0 0\n0 0 1 0\n", encoding="utf-8")
    (dwi_dir / "sub-01_dwi.json").write_text('{"PhaseEncodingDirection":"j-","TotalReadoutTime":0.05}', encoding="utf-8")

    subset_paths = {
        "dwi": work_dir / "sub-01_dti_subset.nii.gz",
        "bval": work_dir / "sub-01_dti_subset.bval",
        "bvec": work_dir / "sub-01_dti_subset.bvec",
        "json": work_dir / "sub-01_dti_subset.json",
    }
    captured = []

    def fake_write_subset(*args, **kwargs):
        work_dir.mkdir(parents=True, exist_ok=True)
        for key, path in subset_paths.items():
            if key == "json":
                path.write_text('{"ImageAgentDtiSubset":{"selected_volume_count":4}}', encoding="utf-8")
            else:
                path.write_text("subset", encoding="utf-8")
        return subset_paths

    monkeypatch.setattr(dwi_fast_dti, "validate_inputs", lambda dirs: None)
    monkeypatch.setattr(dwi_fast_dti, "prepare_mni_resources", lambda dirs: {"template": resources_dir / dwi_fast_dti.MNI_TEMPLATE_FILENAME})
    monkeypatch.setattr(dwi_fast_dti, "write_dti_subset", fake_write_subset)
    monkeypatch.setattr(dwi_fast_dti, "_write_eddy_files", lambda json_path, bval_path, target_work_dir: None)
    monkeypatch.setattr(dwi_fast_dti, "_sudo_password", lambda: "pw")
    monkeypatch.setattr(dwi_fast_dti, "_run_logged", lambda cmd, *args, **kwargs: captured.append([str(part) for part in cmd]))
    monkeypatch.setattr(dwi_fast_dti, "_fsl_bin", lambda fsl_dir, name: tmp_path / name)
    monkeypatch.setattr(dwi_fast_dti, "_fsl_env", lambda fsl_dir: {})
    monkeypatch.setattr(dwi_fast_dti, "_valid_affine_matrix", lambda path: True)
    monkeypatch.setattr(dwi_fast_dti, "_mni_map_has_signal", lambda path, template_path: True)
    monkeypatch.setattr(dwi_fast_dti, "_write_region_tables", lambda *args, **kwargs: None)
    monkeypatch.setattr(dwi_fast_dti, "_sanitize_metric_maps", lambda *args, **kwargs: {})
    monkeypatch.setattr(dwi_fast_dti, "write_result_summary_from_outputs", lambda *args, **kwargs: tmp_path / "summary.json")

    dwi_fast_dti.run_fast_dti(
        bids_dir=bids_dir,
        out_dir=out_dir,
        work_dir=work_dir,
        resources_dir=resources_dir,
        fsl_dir=tmp_path,
        max_runtime_sec=2100,
        task_id=100,
    )

    registration_commands = [cmd for cmd in captured if str(tmp_path / "flirt") in cmd[0]]
    applywarp_commands = [cmd for cmd in captured if str(tmp_path / "applywarp") in cmd[0]]
    assert not applywarp_commands
    assert registration_commands[0][-4:] == ["-dof", "6", "-cost", "normmi"]
    assert any("-applyxfm" in cmd and "-init" in cmd and "dwi_to_mni_affine.mat" in " ".join(cmd) for cmd in registration_commands)


def test_valid_affine_matrix_rejects_nan_and_singular_matrices(tmp_path):
    nan_matrix = tmp_path / "nan.mat"
    nan_matrix.write_text("-nan -nan -nan -nan\n" * 4, encoding="utf-8")
    singular_matrix = tmp_path / "singular.mat"
    singular_matrix.write_text("1 0 0 0\n0 0 0 0\n0 0 0 0\n0 0 0 1\n", encoding="utf-8")
    good_matrix = tmp_path / "good.mat"
    good_matrix.write_text("1 0 0 0\n0 1 0 0\n0 0 1 0\n0 0 0 1\n", encoding="utf-8")

    assert dwi_fast_dti._valid_affine_matrix(nan_matrix) is False
    assert dwi_fast_dti._valid_affine_matrix(singular_matrix) is False
    assert dwi_fast_dti._valid_affine_matrix(good_matrix) is True


def test_run_fast_dti_falls_back_to_header_resample_when_flirt_matrix_invalid(monkeypatch, tmp_path):
    bids_dir = tmp_path / "bids"
    out_dir = tmp_path / "output"
    work_dir = tmp_path / "work"
    resources_dir = tmp_path / "resources"
    dwi_dir = bids_dir / "sub-01" / "dwi"
    dwi_dir.mkdir(parents=True)
    resources_dir.mkdir()
    (dwi_dir / "sub-01_dwi.nii.gz").write_bytes(b"full-dwi")
    (dwi_dir / "sub-01_dwi.bval").write_text("0 1000 1000 1000\n", encoding="utf-8")
    (dwi_dir / "sub-01_dwi.bvec").write_text("1 0 0 0\n0 1 0 0\n0 0 1 0\n", encoding="utf-8")
    (dwi_dir / "sub-01_dwi.json").write_text('{"PhaseEncodingDirection":"j-","TotalReadoutTime":0.05}', encoding="utf-8")

    subset_paths = {
        "dwi": work_dir / "sub-01_dti_subset.nii.gz",
        "bval": work_dir / "sub-01_dti_subset.bval",
        "bvec": work_dir / "sub-01_dti_subset.bvec",
        "json": work_dir / "sub-01_dti_subset.json",
    }
    fallback_calls = []
    captured = []

    def fake_write_subset(*args, **kwargs):
        work_dir.mkdir(parents=True, exist_ok=True)
        for key, path in subset_paths.items():
            if key == "json":
                path.write_text('{"ImageAgentDtiSubset":{"selected_volume_count":4}}', encoding="utf-8")
            else:
                path.write_text("subset", encoding="utf-8")
        return subset_paths

    def fake_run_logged(cmd, *args, **kwargs):
        captured.append([str(part) for part in cmd])
        command_text = " ".join(str(part) for part in cmd)
        if "-omat" in command_text:
            (out_dir / "maps").mkdir(parents=True, exist_ok=True)
            (out_dir / "maps" / "dwi_to_mni_affine.mat").write_text("-nan -nan -nan -nan\n" * 4, encoding="utf-8")

    def fake_resample(metric_path, template_path, out_path):
        fallback_calls.append(out_path.name)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_bytes(b"mni")

    monkeypatch.setattr(dwi_fast_dti, "validate_inputs", lambda dirs: None)
    monkeypatch.setattr(dwi_fast_dti, "prepare_mni_resources", lambda dirs: {"template": resources_dir / dwi_fast_dti.MNI_TEMPLATE_FILENAME})
    monkeypatch.setattr(dwi_fast_dti, "write_dti_subset", fake_write_subset)
    monkeypatch.setattr(dwi_fast_dti, "_write_eddy_files", lambda json_path, bval_path, target_work_dir: None)
    monkeypatch.setattr(dwi_fast_dti, "_sudo_password", lambda: "pw")
    monkeypatch.setattr(dwi_fast_dti, "_run_logged", fake_run_logged)
    monkeypatch.setattr(dwi_fast_dti, "_fsl_bin", lambda fsl_dir, name: tmp_path / name)
    monkeypatch.setattr(dwi_fast_dti, "_fsl_env", lambda fsl_dir: {})
    monkeypatch.setattr(dwi_fast_dti, "_resample_metric_to_mni", fake_resample)
    monkeypatch.setattr(dwi_fast_dti, "_write_region_tables", lambda *args, **kwargs: None)
    monkeypatch.setattr(dwi_fast_dti, "_sanitize_metric_maps", lambda *args, **kwargs: {})
    monkeypatch.setattr(dwi_fast_dti, "write_result_summary_from_outputs", lambda *args, **kwargs: tmp_path / "summary.json")

    dwi_fast_dti.run_fast_dti(
        bids_dir=bids_dir,
        out_dir=out_dir,
        work_dir=work_dir,
        resources_dir=resources_dir,
        fsl_dir=tmp_path,
        max_runtime_sec=2100,
        task_id=101,
    )

    assert set(fallback_calls) == {
        "fa_mni152.nii.gz",
        "md_mni152.nii.gz",
        "ad_mni152.nii.gz",
        "rd_mni152.nii.gz",
    }
    affine_apply_commands = [cmd for cmd in captured if "-applyxfm" in cmd]
    assert affine_apply_commands == []


def test_fsl_env_sets_output_type_for_host_eddy_and_registration(tmp_path):
    env = dwi_fast_dti._fsl_env(tmp_path)

    assert env["FSLDIR"] == str(tmp_path)
    assert env["FSLOUTPUTTYPE"] == "NIFTI_GZ"
    assert str(tmp_path / "bin") in env["PATH"]


def test_prepare_mni_resources_writes_template_and_atlas(tmp_path):
    dirs = {"root": tmp_path}
    original_template_candidates = dwi_fast_dti.DEFAULT_TEMPLATE_CANDIDATES
    original_atlas_candidates = dwi_fast_dti.DEFAULT_ATLAS_CANDIDATES
    dwi_fast_dti.DEFAULT_TEMPLATE_CANDIDATES = []
    dwi_fast_dti.DEFAULT_ATLAS_CANDIDATES = []

    class FakeNib:
        @staticmethod
        def save(image, path):
            Path(path).write_bytes(b"template")

    class FakeAtlas:
        def __init__(self, maps):
            self.maps = maps

    fetched_atlas = tmp_path / "fetched_harvard_oxford.nii.gz"
    fetched_atlas.write_bytes(b"atlas")

    try:
        resources = dwi_fast_dti.prepare_mni_resources(
            dirs,
            template_loader=lambda resolution: {"resolution": resolution},
            atlas_fetcher=lambda name, symmetric_split: FakeAtlas(fetched_atlas),
            nib_module=FakeNib,
        )
    finally:
        dwi_fast_dti.DEFAULT_TEMPLATE_CANDIDATES = original_template_candidates
        dwi_fast_dti.DEFAULT_ATLAS_CANDIDATES = original_atlas_candidates

    assert resources["template"].read_bytes() == b"template"
    assert resources["atlas"].read_bytes() == b"atlas"
    assert resources["atlas_metadata"].exists()
    assert resources["resource_dir"].name == dwi_fast_dti.RESOURCE_SUBDIR


def test_sanitize_metric_map_replaces_nonfinite_values(tmp_path):
    metric = tmp_path / "fa.nii.gz"
    data = np.array([[[0.0, np.nan], [np.inf, -np.inf]]], dtype=np.float32)
    nib.save(nib.Nifti1Image(data, np.eye(4)), metric)

    result = dwi_fast_dti._sanitize_metric_map(metric)
    cleaned = np.asarray(nib.load(metric).dataobj)

    assert result["nonfinite_replaced"] == 3
    assert np.isfinite(cleaned).all()
    assert float(cleaned.sum()) == 0.0


def test_prepare_mni_resources_ignores_empty_candidate_files(tmp_path):
    empty_template = tmp_path / "empty_template.nii.gz"
    empty_atlas = tmp_path / "empty_atlas.nii.gz"
    real_template = tmp_path / "real_template.nii.gz"
    real_atlas = tmp_path / "real_atlas.nii.gz"
    empty_template.write_bytes(b"")
    empty_atlas.write_bytes(b"")
    real_template.write_bytes(b"real-template")
    real_atlas.write_bytes(b"real-atlas")
    original_template_candidates = dwi_fast_dti.DEFAULT_TEMPLATE_CANDIDATES
    original_atlas_candidates = dwi_fast_dti.DEFAULT_ATLAS_CANDIDATES
    dwi_fast_dti.DEFAULT_TEMPLATE_CANDIDATES = [str(empty_template), str(real_template)]
    dwi_fast_dti.DEFAULT_ATLAS_CANDIDATES = [
        ("empty", str(empty_atlas)),
        ("real", str(real_atlas)),
    ]

    try:
        resources = dwi_fast_dti.prepare_mni_resources({"root": tmp_path / "run"})
    finally:
        dwi_fast_dti.DEFAULT_TEMPLATE_CANDIDATES = original_template_candidates
        dwi_fast_dti.DEFAULT_ATLAS_CANDIDATES = original_atlas_candidates

    assert resources["template"].read_bytes() == b"real-template"
    assert resources["atlas"].read_bytes() == b"real-atlas"


def test_prepare_mni_resources_uses_offline_configured_files(tmp_path, monkeypatch):
    template = tmp_path / "template.nii.gz"
    atlas = tmp_path / "atlas.nii.gz"
    template.write_bytes(b"offline-template")
    atlas.write_bytes(b"offline-atlas")
    monkeypatch.setenv("IMAGE_AGENT_DWI_DTI_MNI_TEMPLATE", str(template))
    monkeypatch.setenv("IMAGE_AGENT_DWI_DTI_ATLAS_PATH", str(atlas))
    monkeypatch.setenv("IMAGE_AGENT_DWI_DTI_ATLAS", "MNI152_TestAtlas")

    resources = dwi_fast_dti.prepare_mni_resources({"root": tmp_path / "run"})

    assert resources["template"].read_bytes() == b"offline-template"
    assert resources["atlas"].read_bytes() == b"offline-atlas"
    metadata = json.loads(resources["atlas_metadata"].read_text(encoding="utf-8"))
    assert metadata["atlas"] == "MNI152_TestAtlas"


def test_write_validate_outputs_describes_mni_and_parcellated_deliverables(tmp_path):
    summary_path = dwi_fast_dti.write_validate_outputs(tmp_path, task_id=4, workflow_type="dwi_fast_gpu_dti_validate")

    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    assert summary["workflow_type"] == "dwi_fast_gpu_dti_validate"
    assert summary["modality"] == "DWI"
    assert summary["spaces"] == ["DWI", "MNI152"]
    assert {"tensor_metrics", "mni152_registration", "atlas_statistics"}.issubset(set(summary["feature_groups"]))
    tables = {item["name"] for item in summary["outputs"]["tables"]}
    maps = {item["name"] for item in summary["outputs"]["maps"]}
    assert "combined_region_dti" in tables
    assert "fa_mni152" in maps
    assert "rd_mni152" in maps


def test_write_validate_outputs_preserves_existing_real_metric_files(tmp_path):
    maps_dir = tmp_path / "maps"
    maps_dir.mkdir()
    real_fa = maps_dir / "fa.nii.gz"
    real_fa.write_bytes(b"real-fa")

    dwi_fast_dti.write_validate_outputs(tmp_path, task_id=5, workflow_type="dwi_fast_gpu_dti")

    assert real_fa.read_bytes() == b"real-fa"


def test_write_real_result_summary_requires_and_indexes_real_outputs(tmp_path):
    maps_dir = tmp_path / "maps"
    tables_dir = tmp_path / "tables"
    qc_dir = tmp_path / "qc"
    maps_dir.mkdir()
    tables_dir.mkdir()
    qc_dir.mkdir()
    for metric in dwi_fast_dti.DTI_METRICS:
        (maps_dir / f"{metric}.nii.gz").write_bytes(b"real")
        (maps_dir / f"{metric}_mni152.nii.gz").write_bytes(b"real")
        (tables_dir / f"{metric}_regions.tsv").write_text("region\tmean\nr\t1\n", encoding="utf-8")
    (tables_dir / "combined_region_dti.tsv").write_text("region\tfa\tmd\tad\trd\nr\t1\t2\t3\t4\n", encoding="utf-8")
    (qc_dir / "qc_report.tsv").write_text("metric\tstatus\neddy\tcompleted\n", encoding="utf-8")

    summary_path = dwi_fast_dti.write_result_summary_from_outputs(tmp_path, task_id=6, workflow_type="dwi_fast_gpu_dti")
    summary = json.loads(summary_path.read_text(encoding="utf-8"))

    assert summary["provenance"]["validation_only"] is False
    assert {item["name"] for item in summary["outputs"]["tables"]} >= {"combined_region_dti", "fa_regions"}


def test_write_real_result_summary_uses_prepared_atlas_metadata(tmp_path):
    maps_dir = tmp_path / "output" / "maps"
    tables_dir = tmp_path / "output" / "tables"
    qc_dir = tmp_path / "output" / "qc"
    resource_dir = tmp_path / dwi_fast_dti.RESOURCE_SUBDIR
    maps_dir.mkdir(parents=True)
    tables_dir.mkdir()
    qc_dir.mkdir()
    resource_dir.mkdir()
    (resource_dir / dwi_fast_dti.MNI_ATLAS_METADATA_FILENAME).write_text(
        '{"atlas":"MNI152_HarvardOxford_cort_maxprob_thr25_2mm"}',
        encoding="utf-8",
    )
    for metric in dwi_fast_dti.DTI_METRICS:
        (maps_dir / f"{metric}.nii.gz").write_bytes(b"real")
        (maps_dir / f"{metric}_mni152.nii.gz").write_bytes(b"real")
        (tables_dir / f"{metric}_regions.tsv").write_text("region\tmean\nr\t1\n", encoding="utf-8")
    (tables_dir / "combined_region_dti.tsv").write_text("region\tfa\tmd\tad\trd\nr\t1\t2\t3\t4\n", encoding="utf-8")

    summary_path = dwi_fast_dti.write_result_summary_from_outputs(
        tmp_path / "output",
        task_id=8,
        workflow_type="dwi_fast_gpu_dti",
    )
    summary = json.loads(summary_path.read_text(encoding="utf-8"))

    assert summary["provenance"]["atlas"] == "MNI152_HarvardOxford_cort_maxprob_thr25_2mm"
    assert {item["atlas"] for item in summary["outputs"]["tables"]} == {"MNI152_HarvardOxford_cort_maxprob_thr25_2mm"}


def test_write_real_result_summary_includes_metric_sanitization_provenance(tmp_path):
    maps_dir = tmp_path / "output" / "maps"
    tables_dir = tmp_path / "output" / "tables"
    qc_dir = tmp_path / "output" / "qc"
    maps_dir.mkdir(parents=True)
    tables_dir.mkdir()
    qc_dir.mkdir()
    for metric in dwi_fast_dti.DTI_METRICS:
        (maps_dir / f"{metric}.nii.gz").write_bytes(b"real")
        (maps_dir / f"{metric}_mni152.nii.gz").write_bytes(b"real")
        (tables_dir / f"{metric}_regions.tsv").write_text("region\tmean\nr\t1\n", encoding="utf-8")
    (tables_dir / "combined_region_dti.tsv").write_text("region\tfa\tmd\tad\trd\nr\t1\t2\t3\t4\n", encoding="utf-8")
    (qc_dir / "dwi_fast_gpu_dti_provenance.json").write_text(
        json.dumps(
            {
                "runtime_sec": 1042,
                "max_runtime_sec": 2100,
                "dti_subset_metadata": {"selected_volume_count": 28},
                "mni_registration_method": "flirt_normmi_dof6",
                "mni_registration_attempts": [{"method": "flirt_normmi_dof6"}],
                "metric_sanitization": {
                    "native": {"fa": {"nonfinite_replaced": 3}},
                    "mni152": {"fa": {"nonfinite_replaced": 2}},
                }
            }
        ),
        encoding="utf-8",
    )

    summary_path = dwi_fast_dti.write_result_summary_from_outputs(
        tmp_path / "output",
        task_id=9,
        workflow_type="dwi_fast_gpu_dti",
    )
    summary = json.loads(summary_path.read_text(encoding="utf-8"))

    assert summary["provenance"]["metric_sanitization"]["native"]["fa"]["nonfinite_replaced"] == 3
    assert summary["provenance"]["metric_sanitization"]["mni152"]["fa"]["nonfinite_replaced"] == 2
    assert summary["provenance"]["runtime_sec"] == 1042
    assert summary["provenance"]["max_runtime_sec"] == 2100
    assert summary["provenance"]["dti_subset_metadata"]["selected_volume_count"] == 28
    assert summary["provenance"]["mni_registration_method"] == "flirt_normmi_dof6"


def test_write_real_result_summary_reads_runtime_from_qc_report_when_needed(tmp_path):
    maps_dir = tmp_path / "output" / "maps"
    tables_dir = tmp_path / "output" / "tables"
    qc_dir = tmp_path / "output" / "qc"
    maps_dir.mkdir(parents=True)
    tables_dir.mkdir()
    qc_dir.mkdir()
    for metric in dwi_fast_dti.DTI_METRICS:
        (maps_dir / f"{metric}.nii.gz").write_bytes(b"real")
        (maps_dir / f"{metric}_mni152.nii.gz").write_bytes(b"real")
        (tables_dir / f"{metric}_regions.tsv").write_text("region\tmean\nr\t1\n", encoding="utf-8")
    (tables_dir / "combined_region_dti.tsv").write_text("region\tfa\tmd\tad\trd\nr\t1\t2\t3\t4\n", encoding="utf-8")
    (qc_dir / "dwi_fast_gpu_dti_provenance.json").write_text("{}", encoding="utf-8")
    (qc_dir / "qc_report.tsv").write_text(
        "metric\tstatus\nruntime_sec\t1058\nruntime_limit_sec\t2100\n",
        encoding="utf-8",
    )

    summary_path = dwi_fast_dti.write_result_summary_from_outputs(
        tmp_path / "output",
        task_id=10,
        workflow_type="dwi_fast_gpu_dti",
    )
    summary = json.loads(summary_path.read_text(encoding="utf-8"))

    assert summary["provenance"]["runtime_sec"] == 1058
    assert summary["provenance"]["max_runtime_sec"] == 2100


def test_write_real_result_summary_registers_native_qc_reports_and_figures(tmp_path):
    maps_dir = tmp_path / "output" / "maps"
    tables_dir = tmp_path / "output" / "tables"
    qc_dir = tmp_path / "output" / "qc"
    figures_dir = qc_dir / "figures"
    maps_dir.mkdir(parents=True)
    tables_dir.mkdir()
    figures_dir.mkdir(parents=True)
    for metric in dwi_fast_dti.DTI_METRICS:
        (maps_dir / f"{metric}.nii.gz").write_bytes(b"real")
        (maps_dir / f"{metric}_mni152.nii.gz").write_bytes(b"real")
        (tables_dir / f"{metric}_regions.tsv").write_text("region\tmean\nr\t1\n", encoding="utf-8")
    (tables_dir / "combined_region_dti.tsv").write_text("region\tfa\tmd\tad\trd\nr\t1\t2\t3\t4\n", encoding="utf-8")
    (qc_dir / "index.html").write_text("<html>DWI QC</html>", encoding="utf-8")
    (figures_dir / "fa_native_qc.png").write_bytes(b"png")

    summary_path = dwi_fast_dti.write_result_summary_from_outputs(
        tmp_path / "output",
        task_id=11,
        workflow_type="dwi_fast_gpu_dti",
    )
    summary = json.loads(summary_path.read_text(encoding="utf-8"))

    assert summary["outputs"]["reports"][0]["relative_path"] == "qc/index.html"
    assert summary["outputs"]["reports"][0]["artifact_role"] == "container_native_html_report"
    assert summary["outputs"]["reports"][0]["native_artifact"] is True
    assert summary["outputs"]["figures"][0]["relative_path"] == "qc/figures/fa_native_qc.png"
    assert summary["outputs"]["figures"][0]["artifact_role"] == "container_native_qc_figure"
    assert summary["outputs"]["figures"][0]["native_artifact"] is True
    assert summary["outputs"]["figures"][0]["provenance"]["replaces_native_qc"] is False


def test_write_real_result_summary_materializes_dwi_native_qc_when_missing(tmp_path):
    maps_dir = tmp_path / "output" / "maps"
    tables_dir = tmp_path / "output" / "tables"
    qc_dir = tmp_path / "output" / "qc"
    maps_dir.mkdir(parents=True)
    tables_dir.mkdir()
    qc_dir.mkdir()
    for metric in dwi_fast_dti.DTI_METRICS:
        (maps_dir / f"{metric}.nii.gz").write_bytes(b"real")
        (maps_dir / f"{metric}_mni152.nii.gz").write_bytes(b"real")
        (tables_dir / f"{metric}_regions.tsv").write_text("region\tmean\nr\t1\n", encoding="utf-8")
    (tables_dir / "combined_region_dti.tsv").write_text("region\tfa\tmd\tad\trd\nr\t1\t2\t3\t4\n", encoding="utf-8")
    (qc_dir / "qc_report.tsv").write_text(
        "metric\tstatus\n"
        "gpu_eddy\tcompleted\n"
        "tensor\tcompleted\n"
        "mni_registration\tcompleted\n"
        "atlas_statistics\tcompleted\n",
        encoding="utf-8",
    )
    (qc_dir / "dwi_fast_gpu_dti_provenance.json").write_text(
        json.dumps({"runtime_sec": 99, "max_runtime_sec": 2100}),
        encoding="utf-8",
    )

    summary_path = dwi_fast_dti.write_result_summary_from_outputs(
        tmp_path / "output",
        task_id=12,
        workflow_type="dwi_fast_gpu_dti",
    )
    summary = json.loads(summary_path.read_text(encoding="utf-8"))

    assert (qc_dir / "index.html").exists()
    assert (qc_dir / "figures" / "dwi_fast_gpu_dti_native_qc.svg").exists()
    native_report = summary["outputs"]["reports"][0]
    native_figure = summary["outputs"]["figures"][0]
    assert native_report["relative_path"] == "qc/index.html"
    assert native_report["artifact_role"] == "container_native_html_report"
    assert native_report["native_artifact"] is True
    assert native_figure["relative_path"] == "qc/figures/dwi_fast_gpu_dti_native_qc.svg"
    assert native_figure["artifact_role"] == "container_native_qc_figure"
    assert native_figure["native_artifact"] is True
    assert native_figure["official_source_ids"] == [
        "docs/rag/vendor/fsl_official_fast_dti_tools.md",
        "docs/rag/vendor/mrtrix3_official_dti_toolbox.md",
    ]


def test_write_real_result_summary_fails_when_real_outputs_missing(tmp_path):
    try:
        dwi_fast_dti.write_result_summary_from_outputs(tmp_path, task_id=7, workflow_type="dwi_fast_gpu_dti")
    except RuntimeError as exc:
        assert "required real outputs" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("write_result_summary_from_outputs should reject missing real outputs")
