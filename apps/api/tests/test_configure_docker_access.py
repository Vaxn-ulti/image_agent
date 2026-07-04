from __future__ import annotations

import importlib.util
import os
import stat
from pathlib import Path

import pytest


def _load_script():
    repo_root = Path(__file__).resolve().parents[3]
    script_path = repo_root / "scripts" / "configure_docker_access.py"
    spec = importlib.util.spec_from_file_location("configure_docker_access", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_docker_access_policy_dry_run_plans_narrow_sudoers_rule(tmp_path):
    script = _load_script()

    plan = script.build_policy_plan(
        user="yyf",
        docker_bin=Path("/usr/bin/docker"),
        sudoers_dir=tmp_path / "sudoers.d",
        rule_name="image-agent-docker",
        apply_changes=False,
    )

    assert plan["plan_id"] == "image_agent_docker_access_policy_v1"
    assert plan["mode"] == "dry_run"
    assert plan["sudoers_rule"] == "yyf ALL=(root) NOPASSWD: /usr/bin/docker\n"
    assert plan["sudoers_file"] == str(tmp_path / "sudoers.d" / "image-agent-docker")
    assert plan["verification_command"] == [
        "sudo",
        "-n",
        "docker",
        "version",
        "--format",
        "{{.Server.Version}}",
    ]
    assert [step["id"] for step in plan["steps"]] == [
        "write_sudoers_rule",
        "validate_sudoers_rule",
        "verify_operator_docker_command",
    ]
    assert plan["steps"][0]["mutates_state"] is True
    assert plan["steps"][1]["mutates_state"] is False
    assert plan["steps"][2]["mutates_state"] is False


@pytest.mark.parametrize(
    ("user", "docker_bin", "message"),
    [
        ("yyf ALL=(root) NOPASSWD:ALL", "/usr/bin/docker", "unsafe sudo user"),
        ("bad user", "/usr/bin/docker", "unsafe sudo user"),
        ("yyf", "docker", "docker binary must be an absolute path"),
        ("yyf", "/usr/bin/docker;touch /tmp/x", "unsafe docker binary path"),
    ],
)
def test_docker_access_policy_rejects_unsafe_inputs(tmp_path, user, docker_bin, message):
    script = _load_script()

    with pytest.raises(SystemExit) as exc:
        script.build_policy_plan(
            user=user,
            docker_bin=Path(docker_bin),
            sudoers_dir=tmp_path / "sudoers.d",
            rule_name="image-agent-docker",
            apply_changes=False,
        )

    assert message in str(exc.value)


def test_docker_access_policy_apply_writes_validates_and_verifies(tmp_path, monkeypatch):
    script = _load_script()
    calls = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)

        class Proc:
            returncode = 0
            stdout = "26.1.0\n"
            stderr = ""

        return Proc()

    monkeypatch.setattr(script.subprocess, "run", fake_run)

    plan = script.configure_docker_access(
        user="yyf",
        docker_bin=Path("/usr/bin/docker"),
        sudoers_dir=tmp_path / "sudoers.d",
        rule_name="image-agent-docker",
        apply_changes=True,
    )

    sudoers_file = tmp_path / "sudoers.d" / "image-agent-docker"
    assert plan["mode"] == "apply"
    assert sudoers_file.read_text(encoding="utf-8") == "yyf ALL=(root) NOPASSWD: /usr/bin/docker\n"
    expected_mode = 0o444 if os.name == "nt" else 0o440
    assert stat.S_IMODE(sudoers_file.stat().st_mode) == expected_mode
    assert calls == [
        ["visudo", "-cf", str(sudoers_file)],
        ["sudo", "-n", "docker", "version", "--format", "{{.Server.Version}}"],
    ]


def test_docker_access_policy_is_documented_in_git_managed_install_path():
    repo_root = Path(__file__).resolve().parents[3]
    readme = (repo_root / "README.md").read_text(encoding="utf-8")
    runbook = (repo_root / "docs" / "deployment" / "remote-agent-production.md").read_text(encoding="utf-8")
    combined = readme + "\n" + runbook

    assert "scripts/configure_docker_access.py" in combined
    assert "--user yyf" in combined
    assert "--apply" in combined
    assert "sudo -n docker" in combined
    assert "rawchat" in combined
    assert "direct" in combined
