import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

import app.workflows.remote_scripts as remote_scripts
from app.workflows.remote_scripts import (
    BOLD_REMOTE_ENV_KEYS,
    BOLD_REQUIRED_TEMPLATEFLOW_FILES,
    discover_bold_fmriprep_xcpd_outputs,
    materialize_locked_bold_remote_scripts,
    preflight_bold_fmriprep_xcpd_remote,
    resolve_templateflow_dir,
    run_bold_fmriprep_xcpd_remote,
)


def _write_required_templateflow_files(root: Path) -> None:
    for relative_path in BOLD_REQUIRED_TEMPLATEFLOW_FILES:
        path = root / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"templateflow")


def test_remote_script_preflight_reports_missing_scripts_and_license(tmp_path, monkeypatch):
    bids = tmp_path / "bids"
    bids.mkdir()
    monkeypatch.setenv("IMAGE_AGENT_FS_LICENSE", str(tmp_path / "missing-license.txt"))
    monkeypatch.setenv("IMAGE_AGENT_BOLD_FMRIPREP_SCRIPT", str(tmp_path / "missing-fmriprep.sh"))
    monkeypatch.setenv("IMAGE_AGENT_BOLD_XCPD_SCRIPT", str(tmp_path / "missing-xcpd.sh"))

    result = preflight_bold_fmriprep_xcpd_remote(bids_dir=bids, output_dir=tmp_path / "out", work_dir=tmp_path / "work")

    assert result["ok"] is False
    failed = {check["name"] for check in result["checks"] if check["status"] == "fail"}
    assert {"fmriprep_script_exists", "xcpd_script_exists", "fs_license_exists"} <= failed
    assert str(tmp_path) not in " ".join(result["blocking_errors"])
    assert "missing-fmriprep.sh" in " ".join(result["blocking_errors"])


def test_remote_script_run_preflight_error_uses_path_safe_script_labels(tmp_path, monkeypatch):
    bids = tmp_path / "bids"
    bids.mkdir()
    license_path = tmp_path / "license.txt"
    license_path.write_text("license", encoding="utf-8")
    missing_fmriprep = tmp_path / "missing-fmriprep.sh"
    missing_xcpd = tmp_path / "missing-xcpd.sh"
    monkeypatch.setenv("IMAGE_AGENT_FS_LICENSE", str(license_path))
    monkeypatch.setenv("IMAGE_AGENT_BOLD_FMRIPREP_SCRIPT", str(missing_fmriprep))
    monkeypatch.setenv("IMAGE_AGENT_BOLD_XCPD_SCRIPT", str(missing_xcpd))

    with pytest.raises(RuntimeError, match="Remote BOLD fMRIPrep/XCP-D preflight failed") as exc:
        run_bold_fmriprep_xcpd_remote(
            task_id=44,
            bids_dir=bids,
            output_dir=tmp_path / "out",
            work_dir=tmp_path / "work",
            log_path=tmp_path / "task.log",
        )

    message = str(exc.value)
    assert str(tmp_path) not in message
    assert "missing-fmriprep.sh" in message
    assert "missing-xcpd.sh" in message


def test_remote_script_preflight_rejects_directory_as_script(tmp_path, monkeypatch):
    bids = tmp_path / "bids"
    bids.mkdir()
    script_dir = tmp_path / "script-dir"
    script_dir.mkdir()
    license_path = tmp_path / "license.txt"
    license_path.write_text("license", encoding="utf-8")
    monkeypatch.setenv("IMAGE_AGENT_FS_LICENSE", str(license_path))
    monkeypatch.setenv("IMAGE_AGENT_BOLD_FMRIPREP_SCRIPT", str(script_dir))
    monkeypatch.setenv("IMAGE_AGENT_BOLD_XCPD_SCRIPT", str(script_dir))

    result = preflight_bold_fmriprep_xcpd_remote(bids_dir=bids, output_dir=tmp_path / "out", work_dir=tmp_path / "work")

    assert result["ok"] is False
    failed = {check["name"] for check in result["checks"] if check["status"] == "fail"}
    assert {"fmriprep_script_exists", "xcpd_script_exists"} <= failed


def test_remote_script_runner_passes_task_environment_and_discovers_outputs(tmp_path, monkeypatch):
    bids = tmp_path / "bids"
    output = tmp_path / "output"
    work = tmp_path / "work"
    log = tmp_path / "task.log"
    bids.mkdir()
    license_path = tmp_path / "license.txt"
    license_path.write_text("license", encoding="utf-8")
    env_capture = tmp_path / "env.json"
    fmriprep_script = tmp_path / "run_fmriprep.sh"
    xcpd_script = tmp_path / "run_xcpd.sh"
    fmriprep_script.write_text(
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        "mkdir -p \"$IMAGE_AGENT_TASK_FMRIPREP_DIR\"\n"
        "echo '<html>fmriprep</html>' > \"$IMAGE_AGENT_TASK_FMRIPREP_DIR/fmriprep_report.html\"\n",
        encoding="utf-8",
    )
    xcpd_script.write_text(
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        "mkdir -p \"$IMAGE_AGENT_TASK_XCPD_DIR/tables\" \"$IMAGE_AGENT_TASK_XCPD_DIR/reports\" \"$IMAGE_AGENT_TASK_LOG_DIR\"\n"
        "echo '<html>xcpd</html>' > \"$IMAGE_AGENT_TASK_XCPD_DIR/reports/index.html\"\n"
        "echo '<svg></svg>' > \"$IMAGE_AGENT_TASK_XCPD_DIR/reports/qc.svg\"\n"
        "echo 'metric\tvalue' > \"$IMAGE_AGENT_TASK_XCPD_DIR/tables/metrics.tsv\"\n"
        "echo 'xcpd log' > \"$IMAGE_AGENT_TASK_LOG_DIR/xcpd.log\"\n"
        f'"{sys.executable}" - <<\'PY\'\n'
        "import json, os\n"
        "keys = os.environ['IMAGE_AGENT_CAPTURE_KEYS'].split(',')\n"
        "with open(os.environ['IMAGE_AGENT_ENV_CAPTURE'], 'w', encoding='utf-8') as f:\n"
        "    json.dump({key: os.environ.get(key) for key in keys}, f)\n"
        "PY\n",
        encoding="utf-8",
    )
    fmriprep_script.chmod(0o755)
    xcpd_script.chmod(0o755)
    monkeypatch.setenv("IMAGE_AGENT_FS_LICENSE", str(license_path))
    monkeypatch.setenv("IMAGE_AGENT_BOLD_FMRIPREP_SCRIPT", str(fmriprep_script))
    monkeypatch.setenv("IMAGE_AGENT_BOLD_XCPD_SCRIPT", str(xcpd_script))
    monkeypatch.setenv("IMAGE_AGENT_ENV_CAPTURE", str(env_capture))
    monkeypatch.setenv("IMAGE_AGENT_CAPTURE_KEYS", ",".join(BOLD_REMOTE_ENV_KEYS))
    shared_templateflow = tmp_path / "shared-templateflow"
    _write_required_templateflow_files(shared_templateflow)
    monkeypatch.setenv("IMAGE_AGENT_TEMPLATEFLOW_HOME", str(shared_templateflow))

    result = run_bold_fmriprep_xcpd_remote(
        task_id=44,
        bids_dir=bids,
        output_dir=output,
        work_dir=work,
        log_path=log,
    )

    captured = json.loads(env_capture.read_text(encoding="utf-8"))
    outputs = discover_bold_fmriprep_xcpd_outputs(output)
    assert result["ok"] is True
    assert result["runtime_backend"] == "deployment_local_script_wrapper"
    assert captured["IMAGE_AGENT_TASK_BIDS_DIR"] == str(bids)
    assert captured["IMAGE_AGENT_TASK_XCPD_DIR"] == str(output / "xcpd")
    assert captured["IMAGE_AGENT_TASK_TEMPLATEFLOW_DIR"] == str(shared_templateflow)
    assert captured["IMAGE_AGENT_TASK_FS_LICENSE"] == str(license_path)
    assert captured["IMAGE_AGENT_TEMPLATEFLOW_HOME"] == str(shared_templateflow)
    assert result["scripts"] == ["run_fmriprep.sh", "run_xcpd.sh"]
    assert str(tmp_path) not in str(result["scripts"])
    assert outputs["reports"]
    assert outputs["figures"]
    assert outputs["tables"]
    assert outputs["logs"]
    assert outputs["reports"][0]["source_stage"] in {"fmriprep", "xcpd"}
    assert outputs["figures"][0]["source_stage"] == "xcpd"
    assert "START deployment-local script step 1/2" in log.read_text(encoding="utf-8")


def test_remote_script_task_environment_excludes_model_and_sudo_secrets(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-secret")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "deepseek-secret")
    monkeypatch.setenv("IMAGE_AGENT_SUDO_PASSWORD", "sudo-secret")
    monkeypatch.setenv("IMAGE_AGENT_ENV_CAPTURE", str(tmp_path / "capture.json"))
    monkeypatch.setenv("IMAGE_AGENT_CAPTURE_KEYS", ",".join(BOLD_REMOTE_ENV_KEYS))

    env = remote_scripts._task_env(
        task_id=44,
        bids_dir=tmp_path / "bids",
        output_dir=tmp_path / "output",
        work_dir=tmp_path / "work",
    )

    assert "OPENAI_API_KEY" not in env
    assert "DEEPSEEK_API_KEY" not in env
    assert "IMAGE_AGENT_SUDO_PASSWORD" not in env
    assert env["IMAGE_AGENT_ENV_CAPTURE"] == str(tmp_path / "capture.json")
    assert env["IMAGE_AGENT_CAPTURE_KEYS"] == ",".join(BOLD_REMOTE_ENV_KEYS)


def test_remote_script_timeout_uses_configured_limit_and_logs_redacted_tail(tmp_path, monkeypatch):
    script = tmp_path / "hung.sh"
    script.write_text("#!/usr/bin/env bash\nsleep 999\n", encoding="utf-8")
    script.chmod(0o755)
    log = tmp_path / "task.log"
    observed = {}
    monkeypatch.setenv("IMAGE_AGENT_REMOTE_SCRIPT_TIMEOUT_SEC", "7")

    def fake_run(command, **kwargs):
        observed["timeout"] = kwargs["timeout"]
        raise subprocess.TimeoutExpired(
            cmd=command,
            timeout=kwargs["timeout"],
            output="patient Jane Doe OPENAI_API_KEY=sk-test-secret C:/Users/A/private",
        )

    monkeypatch.setattr(remote_scripts.subprocess, "run", fake_run)

    with pytest.raises(RuntimeError, match="deployment-local script timed out after 7s") as exc:
        remote_scripts._run_script(script, env={}, log_path=log, step=1, total=1)

    text = log.read_text(encoding="utf-8")
    assert str(tmp_path) not in str(exc.value)
    assert script.name in str(exc.value)
    assert observed["timeout"] == 7
    assert "TIMEOUT deployment-local script step 1/1" in text
    assert "patient Jane Doe" not in text
    assert "sk-test-secret" not in text
    assert "C:/Users/A/private" not in text
    assert "[redacted-secret]" in text


def test_remote_script_failure_logs_redacted_stdout_tail(tmp_path, monkeypatch):
    script = tmp_path / "fail.sh"
    script.write_text("#!/usr/bin/env bash\nexit 2\n", encoding="utf-8")
    script.chmod(0o755)
    log = tmp_path / "task.log"

    class FakeProc:
        returncode = 2
        stdout = "normal line\nTOKEN=sk-test-secret\n/home/yyf/private/patient-001"

    monkeypatch.setenv("IMAGE_AGENT_REMOTE_SCRIPT_TIMEOUT_SEC", "13")
    monkeypatch.setattr(remote_scripts.subprocess, "run", lambda *args, **kwargs: FakeProc())

    with pytest.raises(RuntimeError, match="deployment-local script failed rc=2") as exc:
        remote_scripts._run_script(script, env={}, log_path=log, step=1, total=1)

    text = log.read_text(encoding="utf-8")
    assert str(tmp_path) not in str(exc.value)
    assert script.name in str(exc.value)
    assert "normal line" in text
    assert "sk-test-secret" not in text
    assert "/home/yyf/private" not in text
    assert "[redacted-secret]" in text


def test_remote_script_run_rejects_missing_script_before_subprocess(tmp_path, monkeypatch):
    missing = tmp_path / "missing.sh"
    log = tmp_path / "task.log"

    def fail_if_called(*args, **kwargs):
        raise AssertionError("subprocess.run should not be called for a missing script")

    monkeypatch.setattr(remote_scripts.subprocess, "run", fail_if_called)

    with pytest.raises(RuntimeError, match="deployment-local script is not executable") as exc:
        remote_scripts._run_script(missing, env={}, log_path=log, step=1, total=1)

    assert str(tmp_path) not in str(exc.value)
    assert missing.name in str(exc.value)


def test_remote_script_run_rejects_non_executable_file_on_posix_before_subprocess(tmp_path, monkeypatch):
    script = tmp_path / "not-executable.sh"
    script.write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
    log = tmp_path / "task.log"

    def fail_if_called(*args, **kwargs):
        raise AssertionError("subprocess.run should not be called for a non-executable script")

    monkeypatch.setattr(remote_scripts, "_script_requires_execute_bit", lambda: True, raising=False)
    monkeypatch.setattr(remote_scripts.os, "access", lambda path, mode: False)
    monkeypatch.setattr(remote_scripts.subprocess, "run", fail_if_called)

    with pytest.raises(RuntimeError, match="deployment-local script is not executable") as exc:
        remote_scripts._run_script(script, env={}, log_path=log, step=1, total=1)

    assert str(tmp_path) not in str(exc.value)
    assert script.name in str(exc.value)


def test_bold_output_discovery_classifies_container_native_qc_artifacts(tmp_path):
    output = tmp_path / "output"
    (output / "fmriprep" / "sub-01" / "figures").mkdir(parents=True)
    (output / "xcpd" / "sub-01" / "figures").mkdir(parents=True)
    (output / "xcpd" / "sub-01" / "tables").mkdir(parents=True)
    (output / "logs").mkdir()
    (output / "fmriprep" / "sub-01.html").write_text("<html>fmriprep report</html>", encoding="utf-8")
    (output / "xcpd" / "sub-01.html").write_text("<html>xcpd report</html>", encoding="utf-8")
    (output / "fmriprep" / "sub-01" / "figures" / "boldref.svg").write_text("<svg></svg>", encoding="utf-8")
    (output / "xcpd" / "sub-01" / "figures" / "carpetplot.png").write_bytes(b"png")
    (output / "xcpd" / "sub-01" / "tables" / "qc.tsv").write_text("metric\tvalue\n", encoding="utf-8")
    (output / "xcpd" / "sub-01" / "map.nii.gz").write_bytes(b"nifti")
    (output / "logs" / "xcpd.log").write_text("xcpd log", encoding="utf-8")

    outputs = discover_bold_fmriprep_xcpd_outputs(output)

    assert {item["source_stage"] for item in outputs["reports"]} == {"fmriprep", "xcpd"}
    assert {item["source_stage"] for item in outputs["figures"]} == {"fmriprep", "xcpd"}
    assert all(item["native_artifact"] is True for item in outputs["reports"])
    assert all(item["artifact_origin"] == "container_output" for item in outputs["figures"])
    assert all(item["provenance"]["replaces_native_qc"] is False for item in outputs["figures"])
    assert outputs["tables"][0]["artifact_role"] == "container_native_table"
    assert outputs["maps"][0]["artifact_role"] == "container_native_map"
    assert outputs["logs"][0]["artifact_role"] == "container_runtime_log"


def test_bold_output_discovery_classifies_wrapper_log_stages(tmp_path):
    output = tmp_path / "output"
    log_dir = output / "logs"
    log_dir.mkdir(parents=True)
    (log_dir / "fmriprep.log").write_text("fmriprep log", encoding="utf-8")
    (log_dir / "xcpd_fmriprep.log").write_text("xcp-d log", encoding="utf-8")

    outputs = discover_bold_fmriprep_xcpd_outputs(output)

    stages = {item["name"]: item["source_stage"] for item in outputs["logs"]}
    assert stages["fmriprep.log"] == "fmriprep"
    assert stages["xcpd_fmriprep.log"] == "xcpd"


def test_remote_script_preflight_checks_templateflow_cache(tmp_path, monkeypatch):
    bids = tmp_path / "bids"
    output = tmp_path / "output"
    work = tmp_path / "work"
    bids.mkdir()
    license_path = tmp_path / "license.txt"
    fmriprep_script = tmp_path / "run_fmriprep.sh"
    xcpd_script = tmp_path / "run_xcpd.sh"
    license_path.write_text("license", encoding="utf-8")
    fmriprep_script.write_text("#!/usr/bin/env bash\n", encoding="utf-8")
    xcpd_script.write_text("#!/usr/bin/env bash\n", encoding="utf-8")
    fmriprep_script.chmod(0o755)
    xcpd_script.chmod(0o755)
    shared_templateflow = tmp_path / "shared-templateflow"
    _write_required_templateflow_files(shared_templateflow)
    monkeypatch.setenv("IMAGE_AGENT_FS_LICENSE", str(license_path))
    monkeypatch.setenv("IMAGE_AGENT_BOLD_FMRIPREP_SCRIPT", str(fmriprep_script))
    monkeypatch.setenv("IMAGE_AGENT_BOLD_XCPD_SCRIPT", str(xcpd_script))
    monkeypatch.setenv("IMAGE_AGENT_TEMPLATEFLOW_HOME", str(shared_templateflow))

    result = preflight_bold_fmriprep_xcpd_remote(bids_dir=bids, output_dir=output, work_dir=work)

    checks = {check["name"]: check for check in result["checks"]}
    assert result["ok"] is True
    assert checks["templateflow_cache_writable"]["status"] == "pass"
    assert checks["templateflow_required_files_present"]["status"] == "pass"
    assert checks["templateflow_cache_writable"]["path"] == str(shared_templateflow)
    assert resolve_templateflow_dir(work) == shared_templateflow


def test_remote_script_preflight_rejects_missing_templateflow_required_files(tmp_path, monkeypatch):
    bids = tmp_path / "bids"
    output = tmp_path / "output"
    work = tmp_path / "work"
    bids.mkdir()
    license_path = tmp_path / "license.txt"
    fmriprep_script = tmp_path / "run_fmriprep.sh"
    xcpd_script = tmp_path / "run_xcpd.sh"
    license_path.write_text("license", encoding="utf-8")
    fmriprep_script.write_text("#!/usr/bin/env bash\n", encoding="utf-8")
    xcpd_script.write_text("#!/usr/bin/env bash\n", encoding="utf-8")
    fmriprep_script.chmod(0o755)
    xcpd_script.chmod(0o755)
    shared_templateflow = tmp_path / "shared-templateflow"
    shared_templateflow.mkdir()
    monkeypatch.setenv("IMAGE_AGENT_FS_LICENSE", str(license_path))
    monkeypatch.setenv("IMAGE_AGENT_BOLD_FMRIPREP_SCRIPT", str(fmriprep_script))
    monkeypatch.setenv("IMAGE_AGENT_BOLD_XCPD_SCRIPT", str(xcpd_script))
    monkeypatch.setenv("IMAGE_AGENT_TEMPLATEFLOW_HOME", str(shared_templateflow))

    result = preflight_bold_fmriprep_xcpd_remote(bids_dir=bids, output_dir=output, work_dir=work)

    checks = {check["name"]: check for check in result["checks"]}
    message = " ".join(result["blocking_errors"])
    assert result["ok"] is False
    assert checks["templateflow_required_files_present"]["status"] == "fail"
    assert "TemplateFlow cache is missing required files" in message
    assert "shared-templateflow" in message
    assert str(tmp_path) not in message


def test_remote_script_preflight_rejects_missing_oasis_templateflow_file(tmp_path, monkeypatch):
    bids = tmp_path / "bids"
    output = tmp_path / "output"
    work = tmp_path / "work"
    bids.mkdir()
    license_path = tmp_path / "license.txt"
    fmriprep_script = tmp_path / "run_fmriprep.sh"
    xcpd_script = tmp_path / "run_xcpd.sh"
    license_path.write_text("license", encoding="utf-8")
    fmriprep_script.write_text("#!/usr/bin/env bash\n", encoding="utf-8")
    xcpd_script.write_text("#!/usr/bin/env bash\n", encoding="utf-8")
    fmriprep_script.chmod(0o755)
    xcpd_script.chmod(0o755)
    shared_templateflow = tmp_path / "shared-templateflow"
    _write_required_templateflow_files(shared_templateflow)
    mni_carpet = (
        shared_templateflow
        / "tpl-MNI152NLin2009cAsym"
        / "tpl-MNI152NLin2009cAsym_res-01_desc-carpet_dseg.nii.gz"
    )
    if mni_carpet.exists():
        mni_carpet.unlink()
    monkeypatch.setenv("IMAGE_AGENT_FS_LICENSE", str(license_path))
    monkeypatch.setenv("IMAGE_AGENT_BOLD_FMRIPREP_SCRIPT", str(fmriprep_script))
    monkeypatch.setenv("IMAGE_AGENT_BOLD_XCPD_SCRIPT", str(xcpd_script))
    monkeypatch.setenv("IMAGE_AGENT_TEMPLATEFLOW_HOME", str(shared_templateflow))

    result = preflight_bold_fmriprep_xcpd_remote(bids_dir=bids, output_dir=output, work_dir=work)

    checks = {check["name"]: check for check in result["checks"]}
    assert result["ok"] is False
    assert checks["templateflow_required_files_present"]["status"] == "fail"
    assert checks["templateflow_required_files_present"]["missing_count"] == 1
    assert "TemplateFlow cache is missing required files" in " ".join(result["blocking_errors"])


def test_remote_script_preflight_rejects_unlocked_container_images(tmp_path, monkeypatch):
    bids = tmp_path / "bids"
    output = tmp_path / "output"
    work = tmp_path / "work"
    bids.mkdir()
    license_path = tmp_path / "license.txt"
    fmriprep_script = tmp_path / "run_fmriprep.sh"
    xcpd_script = tmp_path / "run_xcpd.sh"
    license_path.write_text("license", encoding="utf-8")
    fmriprep_script.write_text("#!/usr/bin/env bash\n", encoding="utf-8")
    xcpd_script.write_text("#!/usr/bin/env bash\n", encoding="utf-8")
    fmriprep_script.chmod(0o755)
    xcpd_script.chmod(0o755)
    monkeypatch.setenv("IMAGE_AGENT_FS_LICENSE", str(license_path))
    monkeypatch.setenv("IMAGE_AGENT_BOLD_FMRIPREP_SCRIPT", str(fmriprep_script))
    monkeypatch.setenv("IMAGE_AGENT_BOLD_XCPD_SCRIPT", str(xcpd_script))
    monkeypatch.setenv("IMAGE_AGENT_BOLD_FMRIPREP_IMAGE", "nipreps/fmriprep:latest")
    monkeypatch.setenv("IMAGE_AGENT_BOLD_XCPD_IMAGE", "pennlinc/xcp_d")

    result = preflight_bold_fmriprep_xcpd_remote(bids_dir=bids, output_dir=output, work_dir=work)

    assert result["ok"] is False
    failed = {check["name"]: check for check in result["checks"] if check["status"] == "fail"}
    assert failed["fmriprep_image_locked"]["image"] == "nipreps/fmriprep:latest"
    assert failed["xcpd_image_locked"]["image"] == "pennlinc/xcp_d"
    assert "fixed tag or digest" in " ".join(result["blocking_errors"])


def test_remote_script_preflight_rejects_latest_tag_inside_scripts(tmp_path, monkeypatch):
    bids = tmp_path / "bids"
    output = tmp_path / "output"
    work = tmp_path / "work"
    bids.mkdir()
    license_path = tmp_path / "license.txt"
    fmriprep_script = tmp_path / "run_fmriprep.sh"
    xcpd_script = tmp_path / "run_xcpd.sh"
    license_path.write_text("license", encoding="utf-8")
    fmriprep_script.write_text(
        "#!/usr/bin/env bash\n"
        "docker run --rm nipreps/fmriprep:latest /data /out participant\n",
        encoding="utf-8",
    )
    xcpd_script.write_text("#!/usr/bin/env bash\n", encoding="utf-8")
    fmriprep_script.chmod(0o755)
    xcpd_script.chmod(0o755)
    monkeypatch.setenv("IMAGE_AGENT_FS_LICENSE", str(license_path))
    monkeypatch.setenv("IMAGE_AGENT_BOLD_FMRIPREP_SCRIPT", str(fmriprep_script))
    monkeypatch.setenv("IMAGE_AGENT_BOLD_XCPD_SCRIPT", str(xcpd_script))
    templateflow = tmp_path / "templateflow"
    _write_required_templateflow_files(templateflow)
    monkeypatch.setenv("IMAGE_AGENT_TEMPLATEFLOW_HOME", str(templateflow))

    result = preflight_bold_fmriprep_xcpd_remote(bids_dir=bids, output_dir=output, work_dir=work)

    assert result["ok"] is False
    failed = {check["name"]: check for check in result["checks"] if check["status"] == "fail"}
    assert failed["fmriprep_script_version_lock"]["script"] == "run_fmriprep.sh"
    assert ":latest" in " ".join(result["blocking_errors"])


def test_materialize_locked_bold_scripts_rewrites_latest_sources_and_passes_preflight(tmp_path, monkeypatch):
    bids = tmp_path / "bids"
    output = tmp_path / "output"
    work = tmp_path / "work"
    source_dir = tmp_path / "source"
    wrapper_dir = tmp_path / "wrappers"
    bids.mkdir()
    source_dir.mkdir()
    license_path = tmp_path / "license.txt"
    license_path.write_text("license", encoding="utf-8")
    source_fmriprep = source_dir / "run_fmriprep.sh"
    source_xcpd = source_dir / "run_xcpd_fmriprep.sh"
    source_fmriprep.write_text(
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        "docker run --rm nipreps/fmriprep:latest \"$@\"\n",
        encoding="utf-8",
    )
    source_xcpd.write_text(
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        "docker run --rm pennlinc/xcp_d:latest \"$@\"\n",
        encoding="utf-8",
    )

    generated = materialize_locked_bold_remote_scripts(
        script_dir=wrapper_dir,
        source_fmriprep_script=source_fmriprep,
        source_xcpd_script=source_xcpd,
    )

    fmriprep_script = Path(generated["fmriprep_script"])
    xcpd_script = Path(generated["xcpd_script"])
    fmriprep_text = fmriprep_script.read_text(encoding="utf-8")
    xcpd_text = xcpd_script.read_text(encoding="utf-8")
    assert "nipreps/fmriprep:latest" not in fmriprep_text
    assert "pennlinc/xcp_d:latest" not in xcpd_text
    assert "IMAGE_AGENT_TASK_FMRIPREP_IMAGE" in fmriprep_text
    assert "IMAGE_AGENT_TASK_XCPD_IMAGE" in xcpd_text
    assert os.access(fmriprep_script, os.X_OK) is True
    assert os.access(xcpd_script, os.X_OK) is True

    monkeypatch.setenv("IMAGE_AGENT_FS_LICENSE", str(license_path))
    monkeypatch.setenv("IMAGE_AGENT_BOLD_FMRIPREP_SCRIPT", str(fmriprep_script))
    monkeypatch.setenv("IMAGE_AGENT_BOLD_XCPD_SCRIPT", str(xcpd_script))
    templateflow = tmp_path / "templateflow"
    _write_required_templateflow_files(templateflow)
    monkeypatch.setenv("IMAGE_AGENT_TEMPLATEFLOW_HOME", str(templateflow))

    result = preflight_bold_fmriprep_xcpd_remote(bids_dir=bids, output_dir=output, work_dir=work)

    assert result["ok"] is True


def test_remote_script_task_environment_exports_locked_container_images(tmp_path, monkeypatch):
    monkeypatch.setenv("IMAGE_AGENT_BOLD_FMRIPREP_IMAGE", "nipreps/fmriprep:25.2.5")
    monkeypatch.setenv("IMAGE_AGENT_BOLD_XCPD_IMAGE", "pennlinc/xcp_d:26.0.2")

    env = remote_scripts._task_env(
        task_id=44,
        bids_dir=tmp_path / "bids",
        output_dir=tmp_path / "output",
        work_dir=tmp_path / "work",
    )

    assert env["IMAGE_AGENT_TASK_FMRIPREP_IMAGE"] == "nipreps/fmriprep:25.2.5"
    assert env["IMAGE_AGENT_TASK_XCPD_IMAGE"] == "pennlinc/xcp_d:26.0.2"


def test_remote_script_preflight_templateflow_error_uses_path_safe_label(tmp_path, monkeypatch):
    bids = tmp_path / "bids"
    output = tmp_path / "output"
    work = tmp_path / "work"
    bids.mkdir()
    private_root = tmp_path / "private-host-root"
    license_path = private_root / "license.txt"
    fmriprep_script = private_root / "run_fmriprep.sh"
    xcpd_script = private_root / "run_xcpd.sh"
    templateflow = private_root / "templateflow-cache"
    private_root.mkdir()
    license_path.write_text("license", encoding="utf-8")
    fmriprep_script.write_text("#!/usr/bin/env bash\n", encoding="utf-8")
    xcpd_script.write_text("#!/usr/bin/env bash\n", encoding="utf-8")
    fmriprep_script.chmod(0o755)
    xcpd_script.chmod(0o755)
    monkeypatch.setenv("IMAGE_AGENT_FS_LICENSE", str(license_path))
    monkeypatch.setenv("IMAGE_AGENT_BOLD_FMRIPREP_SCRIPT", str(fmriprep_script))
    monkeypatch.setenv("IMAGE_AGENT_BOLD_XCPD_SCRIPT", str(xcpd_script))
    monkeypatch.setenv("IMAGE_AGENT_TEMPLATEFLOW_HOME", str(templateflow))

    def fake_access(path, mode):
        return Path(path) != templateflow

    monkeypatch.setattr(remote_scripts.os, "access", fake_access)

    result = preflight_bold_fmriprep_xcpd_remote(bids_dir=bids, output_dir=output, work_dir=work)

    message = " ".join(result["blocking_errors"])
    assert "templateflow-cache" in message
    assert "private-host-root" not in message
