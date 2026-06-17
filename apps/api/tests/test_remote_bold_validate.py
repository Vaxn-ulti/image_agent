from app.workflows import pipeline


def test_remote_bold_validate_uses_remote_preflight_status(monkeypatch, tmp_path):
    dirs = {"bids": tmp_path / "bids", "output": tmp_path / "output", "work": tmp_path / "work"}
    dirs["bids"].mkdir()
    monkeypatch.setattr(
        pipeline,
        "preflight_bold_fmriprep_xcpd_remote",
        lambda *, bids_dir, output_dir, work_dir, require_bids=True: {
            "ok": False,
            "blocking_errors": ["missing script"],
            "checks": [{"name": "fmriprep_script_exists", "status": "fail"}],
        },
    )

    ok, inspect = pipeline._remote_bold_preflight_status(dirs)

    assert ok is False
    assert "missing script" in inspect
    assert "fmriprep_script_exists" in inspect


def test_remote_bold_validate_uses_path_safe_remote_preflight_status(monkeypatch, tmp_path):
    dirs = {"bids": tmp_path / "bids", "output": tmp_path / "output", "work": tmp_path / "work"}
    dirs["bids"].mkdir()
    private_root = tmp_path / "private-host-root"
    fmriprep = private_root / "run_fmriprep.sh"
    xcpd = private_root / "run_xcpd.sh"
    monkeypatch.setattr(
        pipeline,
        "preflight_bold_fmriprep_xcpd_remote",
        lambda *, bids_dir, output_dir, work_dir, require_bids=True: {
            "ok": False,
            "runtime_backend": "deployment_local_script_wrapper",
            "blocking_errors": ["fmriprep_script_exists is missing or not accessible: run_fmriprep.sh"],
            "checks": [
                {"name": "fmriprep_script_exists", "status": "fail", "path": str(fmriprep)},
                {"name": "xcpd_script_exists", "status": "pass", "path": str(xcpd)},
            ],
            "config": {"fmriprep_script": str(fmriprep), "xcpd_script": str(xcpd)},
        },
    )

    ok, inspect = pipeline._remote_bold_preflight_status(dirs)

    assert ok is False
    assert "private-host-root" not in inspect
    assert "run_fmriprep.sh" in inspect
    assert "run_xcpd.sh" in inspect
