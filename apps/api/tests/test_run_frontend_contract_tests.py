import importlib.util
import subprocess
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPT_PATH = REPO_ROOT / "scripts" / "run_frontend_contract_tests.py"


def _load_runner():
    spec = importlib.util.spec_from_file_location("run_frontend_contract_tests", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_install_uses_dev_dependencies_with_explicit_registry_and_fetch_limits(tmp_path, monkeypatch, capsys):
    runner = _load_runner()
    console = tmp_path / "apps" / "console"
    console.mkdir(parents=True)
    (console / "package.json").write_text("{}\n", encoding="utf-8")
    (console / "package-lock.json").write_text("{}\n", encoding="utf-8")
    commands = []

    monkeypatch.setattr(runner, "_npm_executable", lambda: "npm")
    monkeypatch.setattr(
        runner,
        "_run_command",
        lambda command, *, cwd, timeout_seconds, trust_env_proxy: commands.append(
            {
                "command": command,
                "cwd": cwd,
                "timeout_seconds": timeout_seconds,
                "trust_env_proxy": trust_env_proxy,
            }
        ),
    )

    runner.run_frontend_contract_tests(
        console_dir=console,
        tests=["src/lib/api.test.ts"],
        install=True,
        timeout_seconds=120,
        registry="https://registry.npmjs.org/",
        fetch_timeout_ms=20_000,
        fetch_retries=0,
        trust_env_proxy=False,
        cache_dir=tmp_path / "npm-cache",
        offline=True,
    )

    assert commands[0] == {
        "command": [
            "npm",
            "ci",
            "--include=dev",
            "--ignore-scripts",
            "--no-audit",
            "--no-fund",
            "--registry",
            "https://registry.npmjs.org/",
            "--fetch-timeout=20000",
            "--fetch-retries=0",
            "--cache",
            str((tmp_path / "npm-cache").resolve()),
            "--offline",
        ],
        "cwd": console.resolve(),
        "timeout_seconds": 120,
        "trust_env_proxy": False,
    }
    assert commands[1]["command"] == ["npm", "test", "--", "--run", "src/lib/api.test.ts"]
    assert "frontend_api_contract_tests=passed" in capsys.readouterr().out


def test_timeout_error_redacts_registry_tokens(monkeypatch, tmp_path):
    runner = _load_runner()

    def fail_timeout(command, *, cwd, check, timeout, env):
        raise subprocess.TimeoutExpired(command, timeout)

    monkeypatch.setattr(runner.subprocess, "run", fail_timeout)

    with pytest.raises(SystemExit) as exc:
        runner._run_command(
            [
                "npm",
                "ci",
                "--registry",
                "https://example.invalid/registry?token=secret-token-value",
            ],
            cwd=tmp_path,
            timeout_seconds=3,
        )

    message = str(exc.value)
    assert "command timed out after 3s" in message
    assert "secret-token-value" not in message
    assert "token=" not in message
    assert "<redacted-url>" in message


def test_npm_failure_error_redacts_registry_tokens(monkeypatch, tmp_path):
    runner = _load_runner()

    def fail_process(command, *, cwd, check, timeout, env):
        raise subprocess.CalledProcessError(1, command)

    monkeypatch.setattr(runner.subprocess, "run", fail_process)

    with pytest.raises(SystemExit) as exc:
        runner._run_command(
            [
                "npm",
                "ci",
                "--registry",
                "https://example.invalid/registry?token=secret-token-value",
            ],
            cwd=tmp_path,
            timeout_seconds=3,
        )

    message = str(exc.value)
    assert "command failed with exit code 1" in message
    assert "CalledProcessError" not in message
    assert "secret-token-value" not in message
    assert "token=" not in message
    assert "<redacted-url>" in message


def test_run_command_does_not_inherit_proxy_environment_by_default(monkeypatch, tmp_path):
    runner = _load_runner()
    captured = {}

    monkeypatch.setenv("HTTPS_PROXY", "http://proxy.invalid:8080")
    monkeypatch.setenv("HTTP_PROXY", "http://proxy.invalid:8080")
    monkeypatch.setenv("npm_config_proxy", "http://proxy.invalid:8080")

    def capture_run(command, *, cwd, check, timeout, env):
        captured["env"] = env

    monkeypatch.setattr(runner.subprocess, "run", capture_run)

    runner._run_command(["npm", "ci"], cwd=tmp_path, timeout_seconds=3, trust_env_proxy=False)

    assert "HTTPS_PROXY" not in captured["env"]
    assert "HTTP_PROXY" not in captured["env"]
    assert "npm_config_proxy" not in captured["env"]


def test_run_command_can_explicitly_trust_proxy_environment(monkeypatch, tmp_path):
    runner = _load_runner()
    captured = {}

    monkeypatch.setenv("HTTPS_PROXY", "http://proxy.invalid:8080")

    def capture_run(command, *, cwd, check, timeout, env):
        captured["env"] = env

    monkeypatch.setattr(runner.subprocess, "run", capture_run)

    runner._run_command(["npm", "ci"], cwd=tmp_path, timeout_seconds=3, trust_env_proxy=True)

    assert captured["env"]["HTTPS_PROXY"] == "http://proxy.invalid:8080"
