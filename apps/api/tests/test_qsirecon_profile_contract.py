import importlib
import json

import pytest


def _reload_pipeline(monkeypatch, profile: str | None = None):
    import app.core.config as app_config
    import app.workflows.pipeline as pipeline

    if profile is None:
        monkeypatch.delenv("IMAGE_AGENT_QSIRECON_PROFILE", raising=False)
    else:
        monkeypatch.setenv("IMAGE_AGENT_QSIRECON_PROFILE", profile)
    importlib.reload(app_config)
    return importlib.reload(pipeline)


def _dirs(tmp_path):
    return {
        "root": tmp_path,
        "bids": tmp_path / "bids",
        "output": tmp_path / "output",
        "work": tmp_path / "work",
    }


def test_qsirecon_defaults_to_dipy_dki_with_notrack(monkeypatch, tmp_path):
    pipeline = _reload_pipeline(monkeypatch)
    monkeypatch.setattr(pipeline, "FS_LICENSE", tmp_path / "license.txt")

    cmd = pipeline._commands("dwi_qsirecon", _dirs(tmp_path))[0]

    assert "--recon-spec" in cmd
    assert cmd[cmd.index("--recon-spec") + 1] == "dipy_dki"
    assert "--notrack" in cmd
    assert "--skip-odf-reports" in cmd


def test_qsirecon_tractography_profile_switches_recon_spec(monkeypatch, tmp_path):
    pipeline = _reload_pipeline(monkeypatch, "tractography")
    monkeypatch.setattr(pipeline, "FS_LICENSE", tmp_path / "license.txt")

    cmd = pipeline._commands("dwi_qsirecon", _dirs(tmp_path))[0]

    assert "--recon-spec" in cmd
    assert cmd[cmd.index("--recon-spec") + 1] == "mrtrix_multishell_msmt_noACT"
    assert "--notrack" not in cmd
    assert "--skip-odf-reports" not in cmd


def test_qsirecon_invalid_profile_fails_fast(monkeypatch, tmp_path):
    pipeline = _reload_pipeline(monkeypatch, "typo_profile")
    monkeypatch.setattr(pipeline, "FS_LICENSE", tmp_path / "license.txt")

    with pytest.raises(RuntimeError, match="Unsupported IMAGE_AGENT_QSIRECON_PROFILE"):
        pipeline._commands("dwi_qsirecon", _dirs(tmp_path))


def test_qsirecon_legacy_snapshot_is_written(tmp_path):
    from app.workflows import pipeline

    snapshot = pipeline._write_qsirecon_legacy_snapshot(tmp_path)

    assert snapshot.exists()
    payload = json.loads(snapshot.read_text(encoding="utf-8"))
    assert payload["profile"] == "dki"
    assert payload["recon_spec"] == "dipy_dki"
    assert "--notrack" in payload["extra_flags"]
    assert payload["image"] == "pennlinc/qsirecon:latest"
    assert payload["input_type"] == "qsiprep"
    assert payload["command_template"][0:4] == ["docker", "run", "--rm", "--gpus"]
    assert "dipy_dki" in payload["command_template"]
