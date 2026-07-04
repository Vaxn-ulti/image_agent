import importlib.util
import json
import urllib.error
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPT_PATH = REPO_ROOT / "apps" / "api" / "scripts" / "setup_local_embedding_service.py"


def _load_setup_script():
    spec = importlib.util.spec_from_file_location("setup_local_embedding_service", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_local_embedding_service_plan_uses_pinned_tei_container_and_loopback_env(tmp_path):
    script = _load_setup_script()

    plan = script.build_setup_plan(
        env_file=tmp_path / ".env",
        apply_changes=False,
    )

    serialized = json.dumps(plan, sort_keys=True)
    assert plan["plan_id"] == "local_embedding_service_setup_v1"
    assert plan["mode"] == "dry_run"
    assert plan["embedding_image"] == "ghcr.io/huggingface/text-embeddings-inference:cpu-1.9"
    assert plan["container_name"] == "image-agent-embeddings"
    assert plan["bind_endpoint"] == "http://127.0.0.1:18081/v1"
    assert "latest" not in serialized
    assert "0.0.0.0:18081" not in serialized
    assert "sk-" not in serialized
    assert plan["env_updates"] == {
        "IMAGE_AGENT_RAG_EMBEDDING_PROVIDER": "openai_compatible",
        "IMAGE_AGENT_RAG_EMBEDDING_MODEL": "image-agent-minilm-l6-v2",
        "IMAGE_AGENT_RAG_EMBEDDING_BASE_URL": "http://127.0.0.1:18081/v1",
    }
    start_step = next(step for step in plan["steps"] if step["id"] == "start_embedding_container_if_missing")
    assert "ghcr.io/huggingface/text-embeddings-inference:cpu-1.9" in start_step["command_preview"]
    assert "--network host" in start_step["command_preview"]
    assert "-p 127.0.0.1:18081:80" not in start_step["command_preview"]
    assert "--model-id sentence-transformers/all-MiniLM-L6-v2" in start_step["command_preview"]
    assert "--served-model-name image-agent-minilm-l6-v2" in start_step["command_preview"]


def test_local_embedding_service_apply_writes_env_and_reuses_running_container(tmp_path, monkeypatch):
    script = _load_setup_script()
    env_file = tmp_path / ".env"
    calls = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)

        class Proc:
            returncode = 0
            stdout = ""
            stderr = ""

        if cmd[:2] == ["docker", "ps"]:
            Proc.stdout = "image-agent-embeddings\n"
        return Proc()

    monkeypatch.setattr(script.subprocess, "run", fake_run)
    monkeypatch.setenv("IMAGE_AGENT_RAG_EMBEDDING_API_KEY", "embedding-secret-token")

    report = script.setup_local_embedding_service(
        env_file=env_file,
        apply_changes=True,
        verify_endpoint=False,
    )

    assert report["status"] == "completed"
    assert any(cmd[:3] == ["docker", "image", "inspect"] for cmd in calls)
    assert any(cmd[:2] == ["docker", "ps"] for cmd in calls)
    assert not any(cmd[:2] == ["docker", "run"] for cmd in calls)
    env_text = env_file.read_text(encoding="utf-8")
    assert "IMAGE_AGENT_RAG_EMBEDDING_PROVIDER=openai_compatible" in env_text
    assert "IMAGE_AGENT_RAG_EMBEDDING_MODEL=image-agent-minilm-l6-v2" in env_text
    assert "IMAGE_AGENT_RAG_EMBEDDING_BASE_URL=http://127.0.0.1:18081/v1" in env_text
    serialized = json.dumps(report, sort_keys=True)
    assert "embedding-secret-token" not in serialized


def test_local_embedding_service_apply_report_contains_machine_checkable_handoff_evidence(tmp_path, monkeypatch):
    script = _load_setup_script()
    env_file = tmp_path / ".env"
    endpoint_probes = []

    def fake_run(cmd, **kwargs):
        class Proc:
            returncode = 0
            stdout = ""
            stderr = ""

        if cmd[:2] == ["docker", "ps"]:
            Proc.stdout = "image-agent-embeddings\n"
        return Proc()

    monkeypatch.setattr(script.subprocess, "run", fake_run)
    monkeypatch.setattr(
        script,
        "_verify_embedding_endpoint",
        lambda **kwargs: endpoint_probes.append(kwargs),
        raising=False,
    )

    report = script.setup_local_embedding_service(
        env_file=env_file,
        apply_changes=True,
        verify_endpoint=True,
        verify_attempts=1,
        verify_interval_seconds=0,
    )

    assert endpoint_probes
    assert report["plan_id"] == "local_embedding_service_setup_v1"
    assert report["status"] == "completed"
    assert report["embedding_container_name"] == "image-agent-embeddings"
    assert report["embedding_endpoint_bound_to_loopback"] is True
    assert report["embedding_endpoint_probe_passed"] is True
    assert report["no_latest_tags"] is True
    assert report["secret_values_not_logged"] is True
    assert report["secret_values_not_printed"] is True
    assert report["env_key_status"] == {
        "IMAGE_AGENT_RAG_EMBEDDING_PROVIDER": "set",
        "IMAGE_AGENT_RAG_EMBEDDING_MODEL": "set",
        "IMAGE_AGENT_RAG_EMBEDDING_BASE_URL": "set",
    }
    serialized = json.dumps(report, sort_keys=True)
    assert ":latest" not in serialized
    assert "sk-" not in serialized


def test_local_embedding_service_plan_passes_runtime_proxy_names_without_values(tmp_path, monkeypatch):
    script = _load_setup_script()
    proxy_value = "https://proxy.example.invalid/temporary-token"
    monkeypatch.setenv("HTTPS_PROXY", proxy_value)

    plan = script.build_setup_plan(
        env_file=tmp_path / ".env",
        apply_changes=False,
    )

    start_step = next(step for step in plan["steps"] if step["id"] == "start_embedding_container_if_missing")
    assert "-e HTTPS_PROXY" in start_step["command_preview"]
    assert proxy_value not in json.dumps(plan, sort_keys=True)


def test_local_embedding_service_does_not_forward_all_proxy_to_container(tmp_path, monkeypatch):
    script = _load_setup_script()
    monkeypatch.setenv("HTTPS_PROXY", "http://127.0.0.1:19081")
    monkeypatch.setenv("ALL_PROXY", "socks5://127.0.0.1:7890")

    plan = script.build_setup_plan(
        env_file=tmp_path / ".env",
        apply_changes=False,
        network_mode="host",
    )

    start_step = next(step for step in plan["steps"] if step["id"] == "start_embedding_container_if_missing")
    assert "-e HTTPS_PROXY" in start_step["command_preview"]
    assert "-e ALL_PROXY" not in start_step["command_preview"]
    assert "ALL_PROXY" not in plan["container_proxy_forwarding"]["environment_names"]


def test_local_embedding_service_rewrites_loopback_proxy_for_container_without_reporting_value(tmp_path, monkeypatch):
    script = _load_setup_script()
    proxy_value = "http://127.0.0.1:19081"
    for name in script.RUNTIME_PROXY_ENV_NAMES:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("HTTP_PROXY", proxy_value)

    plan = script.build_setup_plan(
        env_file=tmp_path / ".env",
        apply_changes=False,
        network_mode="bridge",
    )

    start_step = next(step for step in plan["steps"] if step["id"] == "start_embedding_container_if_missing")
    serialized = json.dumps(plan, sort_keys=True)
    assert "--add-host host.docker.internal:host-gateway" in start_step["command_preview"]
    assert "-e HTTP_PROXY" in start_step["command_preview"]
    assert proxy_value not in serialized
    assert "host.docker.internal:19081" not in serialized
    assert plan["container_proxy_forwarding"]["enabled"] is True
    assert "HTTP_PROXY" in plan["container_proxy_forwarding"]["environment_names"]
    assert plan["container_proxy_forwarding"]["uses_host_gateway"] is True


def test_local_embedding_service_host_network_mode_serves_on_bind_port(tmp_path):
    script = _load_setup_script()

    plan = script.build_setup_plan(
        env_file=tmp_path / ".env",
        apply_changes=False,
        network_mode="host",
    )

    start_step = next(step for step in plan["steps"] if step["id"] == "start_embedding_container_if_missing")
    assert "--network host" in start_step["command_preview"]
    assert "-p 127.0.0.1:18081:80" not in start_step["command_preview"]
    assert "--port 18081" in start_step["command_preview"]
    assert plan["network_mode"] == "host"


def test_local_embedding_service_host_network_keeps_loopback_proxy(tmp_path, monkeypatch):
    script = _load_setup_script()
    for name in script.RUNTIME_PROXY_ENV_NAMES:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("HTTP_PROXY", "http://127.0.0.1:19081")

    plan = script.build_setup_plan(
        env_file=tmp_path / ".env",
        apply_changes=False,
        network_mode="host",
    )

    start_step = next(step for step in plan["steps"] if step["id"] == "start_embedding_container_if_missing")
    assert "--add-host host.docker.internal:host-gateway" not in start_step["command_preview"]
    assert plan["container_proxy_forwarding"]["uses_host_gateway"] is False
    proxy_env, uses_host_gateway = script._container_proxy_env(rewrite_loopback=False)
    assert proxy_env["HTTP_PROXY"] == "http://127.0.0.1:19081"
    assert uses_host_gateway is False


def test_local_embedding_service_recreates_exited_container(tmp_path, monkeypatch):
    script = _load_setup_script()
    env_file = tmp_path / ".env"
    calls = []

    def fake_run(cmd, **kwargs):
        calls.append((cmd, kwargs.get("env")))

        class Proc:
            returncode = 0
            stdout = ""
            stderr = ""

        if cmd[:2] == ["docker", "ps"] and "status=running" in cmd:
            Proc.stdout = ""
        if cmd[:2] == ["docker", "ps"] and "status=exited" in cmd:
            Proc.stdout = "image-agent-embeddings\n"
        return Proc()

    monkeypatch.setattr(script.subprocess, "run", fake_run)

    report = script.setup_local_embedding_service(
        env_file=env_file,
        apply_changes=True,
        verify_endpoint=False,
    )

    assert report["status"] == "completed"
    assert any(cmd[:3] == ["docker", "rm", "image-agent-embeddings"] for cmd, _env in calls)
    assert any(cmd[:2] == ["docker", "run"] for cmd, _env in calls)
    assert {"id": "remove_exited_embedding_container", "status": "removed"} in report["steps"]


def test_local_embedding_service_endpoint_probe_retries_until_ready(monkeypatch):
    script = _load_setup_script()
    attempts = []

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def read(self):
            return json.dumps({"data": [{"embedding": [0.1, 0.2]}]}).encode("utf-8")

    def fake_urlopen(_request, timeout):
        attempts.append(timeout)
        if len(attempts) < 3:
            raise urllib.error.URLError("not ready")
        return Response()

    monkeypatch.setattr(script.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(script.time, "sleep", lambda _seconds: None)

    script._verify_embedding_endpoint(
        embedding_base_url="http://127.0.0.1:18081/v1",
        served_model_name="image-agent-minilm-l6-v2",
        attempts=5,
        interval_seconds=0,
    )

    assert len(attempts) == 3


def test_local_embedding_service_rejects_floating_image(tmp_path):
    script = _load_setup_script()

    with pytest.raises(SystemExit) as exc:
        script.build_setup_plan(
            env_file=tmp_path / ".env",
            embedding_image="ghcr.io/huggingface/text-embeddings-inference:latest",
            apply_changes=False,
        )

    assert "Embedding image must be version-pinned" in str(exc.value)
