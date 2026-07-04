import importlib.util
import json
from pathlib import Path
from urllib.error import HTTPError, URLError

import pytest


REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPT_PATH = REPO_ROOT / "scripts" / "verify_rawchat_direct_connectivity.py"


def _load_script():
    spec = importlib.util.spec_from_file_location("verify_rawchat_direct_connectivity", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class _FakeOpener:
    def __init__(self, outcome):
        self.outcome = outcome
        self.requests = []

    def open(self, request, timeout):
        self.requests.append((request, timeout))
        if isinstance(self.outcome, BaseException):
            raise self.outcome
        return self.outcome


class _FakeResponse:
    status = 204

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False


def test_rawchat_direct_probe_accepts_endpoint_http_error_without_trusting_proxy_env(monkeypatch):
    module = _load_script()
    monkeypatch.setenv("HTTPS_PROXY", "http://proxy.invalid:8080")
    opener = _FakeOpener(HTTPError("https://rawchat.cn/codex", 404, "Not Found", hdrs=None, fp=None))

    report = module.probe_rawchat_direct_connectivity(opener_factory=lambda: opener)

    assert report["status"] == "passed"
    assert report["checked"]["host"] == "rawchat.cn"
    assert report["checked"]["http_status"] == 404
    assert report["checked"]["direct_transport"] is True
    assert report["checked"]["proxy_env_present"] is True
    assert report["checked"]["proxy_env_trusted"] is False
    assert report["checked"]["proxy_handler"] == "disabled"
    serialized = json.dumps(report, sort_keys=True)
    assert "proxy.invalid" not in serialized


def test_rawchat_direct_probe_rejects_non_rawchat_url():
    module = _load_script()

    with pytest.raises(SystemExit) as exc:
        module.probe_rawchat_direct_connectivity(url="https://example.com/codex")

    assert "rawchat direct probe URL must target rawchat.cn" in str(exc.value)


def test_rawchat_direct_probe_reports_network_failure_without_proxy_value(monkeypatch):
    module = _load_script()
    monkeypatch.setenv("HTTP_PROXY", "http://proxy.invalid:8080")

    report = module.probe_rawchat_direct_connectivity(
        opener_factory=lambda: _FakeOpener(URLError("timed out")),
    )

    assert report["status"] == "failed"
    assert report["checked"]["direct_transport"] is True
    assert report["checked"]["proxy_env_trusted"] is False
    assert report["checked"]["error_type"] == "URLError"
    assert "proxy.invalid" not in json.dumps(report, sort_keys=True)


def test_rawchat_direct_probe_cli_writes_safe_json(tmp_path, capsys, monkeypatch):
    module = _load_script()
    output_json = tmp_path / "rawchat-direct.json"
    monkeypatch.setattr(module, "probe_rawchat_direct_connectivity", lambda **_: {
        "status": "passed",
        "checked": {
            "host": "rawchat.cn",
            "direct_transport": True,
            "proxy_env_trusted": False,
            "proxy_handler": "disabled",
            "http_status": 204,
        },
        "summary": "rawchat_direct_connectivity_status=passed",
    })

    module.main(["--output-json", str(output_json)])

    stdout = capsys.readouterr().out
    saved = json.loads(output_json.read_text(encoding="utf-8"))
    assert saved["status"] == "passed"
    assert "rawchat_direct_connectivity_status=passed" in stdout
    assert "rawchat_direct_proxy_env_trusted=false" in stdout
