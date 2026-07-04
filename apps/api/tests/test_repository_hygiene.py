from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


def _load_script():
    repo_root = Path(__file__).resolve().parents[3]
    script_path = repo_root / "scripts" / "check_repository_hygiene.py"
    spec = importlib.util.spec_from_file_location("check_repository_hygiene", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_repository_hygiene_rejects_conflict_proxy_and_key_markers(tmp_path):
    script = _load_script()
    forbidden_proxy = "https://proxy.invalid/" + ("O" + "wO=") + "runtime-only"
    secret_like = "sk-" + ("A" * 24)
    bad_file = tmp_path / "bad.py"
    bad_file.write_text(
        "\n".join(
            [
                "<<<<<<< HEAD",
                f"PROXY = {forbidden_proxy!r}",
                f"API_KEY = {secret_like!r}",
            ]
        ),
        encoding="utf-8",
    )

    with pytest.raises(SystemExit) as exc:
        script.run_hygiene_check(paths=[bad_file], repo_root=tmp_path)

    message = str(exc.value)
    assert "repository hygiene check failed" in message
    assert "conflict_marker" in message
    assert "forbidden_proxy_marker" in message
    assert "api_key_shaped_secret" in message
    assert forbidden_proxy not in message
    assert secret_like not in message


def test_repository_hygiene_reports_safe_summary(tmp_path):
    script = _load_script()
    safe_file = tmp_path / "safe.md"
    safe_file.write_text("IMAGE_AGENT_MODEL_TRUST_ENV_PROXY=0\nno secrets here\n", encoding="utf-8")

    report = script.run_hygiene_check(paths=[safe_file], repo_root=tmp_path)

    assert report["status"] == "passed"
    assert report["checked"]["file_count"] == 1
    assert report["checked"]["finding_count"] == 0
    assert report["summary"] == "repository_hygiene_status=passed"
