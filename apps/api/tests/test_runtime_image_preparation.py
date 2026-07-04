from app.workflows import pipeline
from app.scripts import probe_runtime_environment


def test_inspect_runtime_does_not_pull_missing_images_by_default(monkeypatch):
    calls = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)

        class Proc:
            returncode = 1
            stdout = "missing"

        return Proc()

    monkeypatch.setattr(pipeline.subprocess, "run", fake_run)
    monkeypatch.setenv("IMAGE_AGENT_SUDO_PASSWORD", "pw")
    monkeypatch.delenv("IMAGE_AGENT_AUTO_PULL_MISSING_WORKFLOW_IMAGES", raising=False)

    status = pipeline.inspect_runtime()

    assert status["runtime_preparation"]["auto_pull_missing_images"] is False
    assert status["runtime_preparation"]["pull_attempted_count"] == 0
    assert not any("pull" in cmd for cmd in calls)
    assert status["workflows"]["t1_deepprep"]["available"] is False


def test_inspect_runtime_pulls_missing_images_when_explicitly_enabled(monkeypatch):
    calls = []
    inspect_counts = {}

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        image = cmd[-1]

        class Proc:
            returncode = 0
            stdout = "ok"

        if cmd[3:5] == ["image", "inspect"]:
            inspect_counts[image] = inspect_counts.get(image, 0) + 1
            if inspect_counts[image] == 1:
                Proc.returncode = 1
                Proc.stdout = "not found"
            return Proc()
        if cmd[3] == "pull":
            return Proc()
        Proc.returncode = 2
        Proc.stdout = "unexpected command"
        return Proc()

    monkeypatch.setattr(pipeline.subprocess, "run", fake_run)
    monkeypatch.setenv("IMAGE_AGENT_SUDO_PASSWORD", "pw")
    monkeypatch.setenv("IMAGE_AGENT_AUTO_PULL_MISSING_WORKFLOW_IMAGES", "1")

    status = pipeline.inspect_runtime()

    assert status["runtime_preparation"]["auto_pull_missing_images"] is True
    assert status["runtime_preparation"]["pull_attempted_count"] >= 1
    assert status["runtime_preparation"]["pull_succeeded_count"] == status["runtime_preparation"]["pull_attempted_count"]
    assert status["workflows"]["t1_deepprep"]["available"] is True
    assert status["workflows"]["t1_deepprep"]["pull_attempted"] is True
    assert status["workflows"]["t1_deepprep"]["pull_status"] == "pulled"
    assert any(cmd[3] == "pull" and cmd[-1] == "pbfslab/deepprep:25.1.0" for cmd in calls)


def test_inspect_runtime_uses_noninteractive_configured_docker_command(monkeypatch):
    calls = []

    def fake_run(cmd, **kwargs):
        calls.append({"cmd": cmd, "input": kwargs.get("input")})

        class Proc:
            returncode = 0
            stdout = "ok"

        return Proc()

    monkeypatch.setattr(pipeline.subprocess, "run", fake_run)
    monkeypatch.setenv("IMAGE_AGENT_DOCKER_COMMAND", "sudo -n docker")
    monkeypatch.delenv("IMAGE_AGENT_SUDO_PASSWORD", raising=False)
    monkeypatch.delenv("IMAGE_AGENT_AUTO_PULL_MISSING_WORKFLOW_IMAGES", raising=False)

    status = pipeline.inspect_runtime()

    assert status["docker_requires_sudo"] is False
    assert status["workflows"]["t1_deepprep"]["available"] is True
    assert calls
    assert all(call["cmd"][:3] == ["sudo", "-n", "docker"] for call in calls)
    assert all(call["input"] is None for call in calls)


def test_inspect_runtime_keeps_legacy_sudo_password_mode(monkeypatch):
    calls = []

    def fake_run(cmd, **kwargs):
        calls.append({"cmd": cmd, "input": kwargs.get("input")})

        class Proc:
            returncode = 0
            stdout = "ok"

        return Proc()

    monkeypatch.setattr(pipeline.subprocess, "run", fake_run)
    monkeypatch.delenv("IMAGE_AGENT_DOCKER_COMMAND", raising=False)
    monkeypatch.setenv("IMAGE_AGENT_SUDO_PASSWORD", "pw")

    status = pipeline.inspect_runtime()

    assert status["docker_requires_sudo"] is True
    assert calls[0]["cmd"][:3] == ["sudo", "-S", "docker"]
    assert calls[0]["input"] == "pw\n"


def test_recovery_docker_uses_noninteractive_configured_command(monkeypatch):
    from app.workflows import recovery

    calls = []

    def fake_run(cmd, **kwargs):
        calls.append({"cmd": cmd, "input": kwargs.get("input")})

        class Proc:
            returncode = 0
            stdout = ""
            stderr = ""

        return Proc()

    monkeypatch.setattr(recovery.subprocess, "run", fake_run)
    monkeypatch.setenv("IMAGE_AGENT_DOCKER_COMMAND", "sudo -n docker")
    monkeypatch.delenv("IMAGE_AGENT_SUDO_PASSWORD", raising=False)

    recovery._docker(["ps"])

    assert calls == [{"cmd": ["sudo", "-n", "docker", "ps"], "input": None}]


def test_dwi_fast_mrtrix_command_uses_noninteractive_configured_docker(monkeypatch, tmp_path):
    from app.workflows import dwi_fast_dti

    monkeypatch.setenv("IMAGE_AGENT_DOCKER_COMMAND", "sudo -n docker")
    monkeypatch.delenv("IMAGE_AGENT_SUDO_PASSWORD", raising=False)

    cmd = dwi_fast_dti._mrtrix_command(
        "pennlinc/qsiprep:26.0.0",
        tmp_path / "bids",
        tmp_path / "out",
        tmp_path / "work",
        "mrinfo /data",
    )

    assert dwi_fast_dti._sudo_password() == ""
    assert cmd[:3] == ["sudo", "-n", "docker"]
    assert "run" in cmd


def test_probe_runtime_environment_cli_can_enable_one_shot_image_preparation(monkeypatch, capsys):
    def fake_runtime_probe():
        return {
            "runtime_preparation": {
                "auto_pull_missing_images": pipeline._truthy_env(
                    pipeline.AUTO_PULL_MISSING_WORKFLOW_IMAGES_ENV
                )
            }
        }

    monkeypatch.delenv("IMAGE_AGENT_AUTO_PULL_MISSING_WORKFLOW_IMAGES", raising=False)
    monkeypatch.setattr(probe_runtime_environment, "runtime_probe", fake_runtime_probe)

    probe_runtime_environment.main(["--json", "--prepare-missing-images"])

    payload = capsys.readouterr().out
    assert '"auto_pull_missing_images": true' in payload
    assert pipeline._truthy_env("IMAGE_AGENT_AUTO_PULL_MISSING_WORKFLOW_IMAGES") is True
