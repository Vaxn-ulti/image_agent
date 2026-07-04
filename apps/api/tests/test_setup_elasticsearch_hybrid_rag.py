import importlib.util
import json
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPT_PATH = REPO_ROOT / "apps" / "api" / "scripts" / "setup_elasticsearch_hybrid_rag.py"


def _load_setup_script():
    spec = importlib.util.spec_from_file_location("setup_elasticsearch_hybrid_rag", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_setup_plan_scripts_local_docker_elasticsearch_and_env_without_latest_or_secrets(tmp_path):
    script = _load_setup_script()
    env_file = tmp_path / ".env"

    plan = script.build_setup_plan(
        env_file=env_file,
        index_name="image_agent_rag_release_20260620",
        embedding_provider="openai_compatible",
        embedding_model="text-embedding-3-small",
        embedding_base_url="https://embedding.example/v1",
        apply_changes=False,
    )

    serialized = json.dumps(plan, sort_keys=True)
    assert plan["plan_id"] == "elasticsearch_hybrid_rag_setup_v1"
    assert plan["mode"] == "dry_run"
    assert plan["elasticsearch_image"] == "docker.elastic.co/elasticsearch/elasticsearch:9.4.2"
    assert plan["container_name"] == "image-agent-es"
    assert plan["bind_endpoint"] == "http://127.0.0.1:9200"
    assert "latest" not in serialized
    assert "0.0.0.0:9200" not in serialized
    assert "sk-" not in serialized
    assert "OPENAI_API_KEY=" not in serialized
    assert [step["id"] for step in plan["steps"]] == [
        "inspect_docker",
        "inspect_elasticsearch_image",
        "pull_elasticsearch_image_if_missing",
        "inspect_elasticsearch_container",
        "start_elasticsearch_container_if_missing",
        "start_elasticsearch_trial_license",
        "write_elasticsearch_hybrid_env",
        "rebuild_elasticsearch_hybrid_rag",
        "verify_elasticsearch_hybrid_prerequisites",
    ]
    assert plan["env_updates"] == {
        "IMAGE_AGENT_ELASTICSEARCH_URL": "http://127.0.0.1:9200",
        "IMAGE_AGENT_ELASTICSEARCH_INDEX": "image_agent_rag_release_20260620",
        "IMAGE_AGENT_RAG_EMBEDDING_PROVIDER": "openai_compatible",
        "IMAGE_AGENT_RAG_EMBEDDING_MODEL": "text-embedding-3-small",
        "IMAGE_AGENT_RAG_EMBEDDING_BASE_URL": "https://embedding.example/v1",
    }
    run_step = next(step for step in plan["steps"] if step["id"] == "start_elasticsearch_container_if_missing")
    assert "docker run" in run_step["command_preview"]
    assert "-p 127.0.0.1:9200:9200" in run_step["command_preview"]
    assert "xpack.security.enabled=false" in run_step["command_preview"]
    assert "docker.elastic.co/elasticsearch/elasticsearch:9.4.2" in run_step["command_preview"]
    trial_step = next(step for step in plan["steps"] if step["id"] == "start_elasticsearch_trial_license")
    assert "POST http://127.0.0.1:9200/_license/start_trial?acknowledge=true" in trial_step["command_preview"]
    assert trial_step["mutates_state"] is True
    assert plan["official_runtime_sources"] == [
        "https://www.elastic.co/docs/deploy-manage/deploy/self-managed/install-elasticsearch-with-docker",
        "https://www.elastic.co/docs/deploy-manage/deploy/self-managed/install-elasticsearch-docker-basic",
        "https://www.elastic.co/docs/deploy-manage/deploy/self-managed/install-elasticsearch-docker-prod",
        "https://www.elastic.co/docs/api/doc/elasticsearch/operation/operation-license-post-start-trial",
    ]


def test_setup_apply_executes_docker_env_rebuild_and_verify_without_printing_secret(tmp_path, monkeypatch):
    script = _load_setup_script()
    env_file = tmp_path / ".env"
    calls = []
    trial_calls = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)

        class Proc:
            returncode = 0
            stdout = ""
            stderr = ""

        if cmd[:3] == ["docker", "image", "inspect"]:
            Proc.returncode = 1
            Proc.stderr = "missing"
        elif cmd[:2] == ["docker", "ps"]:
            Proc.stdout = ""
        elif cmd[:2] == ["docker", "run"]:
            Proc.stdout = "container-id"
        elif "verify_elasticsearch_hybrid_prerequisites.py" in cmd:
            Proc.stdout = '{"status": "passed"}'
        return Proc()

    monkeypatch.setattr(script.subprocess, "run", fake_run)
    monkeypatch.setattr(
        script,
        "_start_trial_license",
        lambda url: trial_calls.append(url) or {"status": "started", "trial_was_started": "true"},
        raising=False,
    )
    monkeypatch.setenv("IMAGE_AGENT_RAG_EMBEDDING_API_KEY_SOURCE", "embedding-secret-token")

    report = script.setup_elasticsearch_hybrid_rag(
        env_file=env_file,
        index_name="image_agent_rag_release_20260620",
        embedding_provider="openai_compatible",
        embedding_model="text-embedding-3-small",
        embedding_base_url="https://embedding.example/v1",
        embedding_api_key_env="IMAGE_AGENT_RAG_EMBEDDING_API_KEY_SOURCE",
        apply_changes=True,
        pull_missing_image=True,
        start_missing_container=True,
        rebuild_rag=True,
        verify_prerequisites=True,
        rag_status_url="http://127.0.0.1:8000/agent/rag/status",
        runtime_probe_json=tmp_path / "runtime_probe.json",
    )

    assert report["status"] == "completed"
    assert any(cmd[:3] == ["docker", "image", "inspect"] for cmd in calls)
    assert any(cmd[:2] == ["docker", "pull"] for cmd in calls)
    assert any(cmd[:2] == ["docker", "run"] for cmd in calls)
    assert any("verify_elasticsearch_hybrid_prerequisites.py" in cmd for cmd in calls)
    assert trial_calls == ["http://127.0.0.1:9200"]
    assert {"id": "start_elasticsearch_trial_license", "status": "started"} in report["steps"]
    env_text = env_file.read_text(encoding="utf-8")
    assert "IMAGE_AGENT_ELASTICSEARCH_URL=http://127.0.0.1:9200" in env_text
    assert "IMAGE_AGENT_ELASTICSEARCH_INDEX=image_agent_rag_release_20260620" in env_text
    assert "IMAGE_AGENT_RAG_EMBEDDING_API_KEY=embedding-secret-token" in env_text
    serialized = json.dumps(report, sort_keys=True)
    assert "embedding-secret-token" not in serialized


def test_setup_apply_report_contains_machine_checkable_handoff_evidence(tmp_path, monkeypatch):
    script = _load_setup_script()
    env_file = tmp_path / ".env"

    def fake_run(cmd, **kwargs):
        class Proc:
            returncode = 0
            stdout = ""
            stderr = ""

        if cmd[:3] == ["docker", "image", "inspect"]:
            Proc.returncode = 1
        elif cmd[:2] == ["docker", "ps"]:
            Proc.stdout = ""
        return Proc()

    monkeypatch.setattr(script.subprocess, "run", fake_run)
    monkeypatch.setattr(
        script,
        "_start_trial_license",
        lambda url: {"status": "started", "trial_was_started": "true"},
        raising=False,
    )

    report = script.setup_elasticsearch_hybrid_rag(
        env_file=env_file,
        index_name="image_agent_rag_release_20260620",
        embedding_provider="openai_compatible",
        embedding_model="text-embedding-3-small",
        embedding_base_url="https://embedding.example/v1",
        apply_changes=True,
        pull_missing_image=True,
        start_missing_container=True,
        rebuild_rag=False,
        verify_prerequisites=False,
    )

    assert report["plan_id"] == "elasticsearch_hybrid_rag_setup_v1"
    assert report["status"] == "completed"
    assert report["elastic_container_name"] == "image-agent-es"
    assert report["elastic_endpoint_bound_to_loopback"] is True
    assert report["no_latest_tags"] is True
    assert report["secret_values_not_logged"] is True
    assert report["secret_values_not_printed"] is True
    assert report["env_key_status"] == {
        "IMAGE_AGENT_ELASTICSEARCH_URL": "set",
        "IMAGE_AGENT_ELASTICSEARCH_INDEX": "set",
        "IMAGE_AGENT_RAG_EMBEDDING_PROVIDER": "set",
        "IMAGE_AGENT_RAG_EMBEDDING_MODEL": "set",
        "IMAGE_AGENT_RAG_EMBEDDING_BASE_URL": "set",
    }
    assert report["elasticsearch_trial_license_status"] in {"started", "started_or_already_started"}
    serialized = json.dumps(report, sort_keys=True)
    assert ":latest" not in serialized
    assert "sk-" not in serialized


def test_setup_plan_rejects_missing_embedding_model_or_endpoint(tmp_path):
    script = _load_setup_script()

    with pytest.raises(SystemExit) as exc:
        script.build_setup_plan(
            env_file=tmp_path / ".env",
            index_name="image_agent_rag_release_20260620",
            embedding_provider="openai_compatible",
            embedding_model="",
            embedding_base_url="",
            apply_changes=False,
        )

    assert "embedding model and embedding base URL are required" in str(exc.value)


def test_setup_apply_reuses_existing_network_and_volume_when_starting_container(tmp_path, monkeypatch):
    script = _load_setup_script()
    calls = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)

        class Proc:
            returncode = 0
            stdout = ""
            stderr = ""

        if cmd[:2] == ["docker", "ps"]:
            Proc.stdout = ""
        elif cmd[:3] == ["docker", "network", "create"]:
            Proc.returncode = 1
            Proc.stderr = "network already exists"
        return Proc()

    monkeypatch.setattr(script.subprocess, "run", fake_run)

    report = script.setup_elasticsearch_hybrid_rag(
        env_file=tmp_path / ".env",
        index_name="image_agent_rag_release_20260620",
        embedding_provider="openai_compatible",
        embedding_model="text-embedding-3-small",
        embedding_base_url="https://embedding.example/v1",
        apply_changes=True,
        pull_missing_image=True,
        start_missing_container=True,
        start_trial_license=False,
        rebuild_rag=False,
        verify_prerequisites=False,
    )

    assert report["status"] == "completed"
    assert any(cmd[:3] == ["docker", "network", "inspect"] for cmd in calls)
    assert any(cmd[:3] == ["docker", "volume", "inspect"] for cmd in calls)
    assert not any(cmd[:3] == ["docker", "network", "create"] for cmd in calls)
    assert not any(cmd[:3] == ["docker", "volume", "create"] for cmd in calls)
    assert any(cmd[:2] == ["docker", "run"] for cmd in calls)


def test_setup_apply_uses_runtime_docker_command_prefix_without_serializing_secret(tmp_path, monkeypatch):
    script = _load_setup_script()
    calls = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)

        class Proc:
            returncode = 0
            stdout = ""
            stderr = ""

        if cmd[:4] == ["sudo", "docker", "ps", "--filter"]:
            Proc.stdout = "image-agent-es"
        return Proc()

    monkeypatch.setattr(script.subprocess, "run", fake_run)
    monkeypatch.setenv("IMAGE_AGENT_DOCKER_COMMAND", "sudo docker")
    monkeypatch.setenv("IMAGE_AGENT_SUDO_PASSWORD", "sudo-secret-value")

    report = script.setup_elasticsearch_hybrid_rag(
        env_file=tmp_path / ".env",
        index_name="image_agent_rag_release_20260620",
        embedding_provider="openai_compatible",
        embedding_model="text-embedding-3-small",
        embedding_base_url="https://embedding.example/v1",
        apply_changes=True,
        pull_missing_image=True,
        start_missing_container=True,
        start_trial_license=False,
        rebuild_rag=False,
        verify_prerequisites=False,
    )

    assert report["status"] == "completed"
    assert calls[0][:2] == ["sudo", "docker"]
    assert any(cmd[:4] == ["sudo", "docker", "image", "inspect"] for cmd in calls)
    assert any(cmd[:3] == ["sudo", "docker", "ps"] for cmd in calls)
    serialized = json.dumps(report, sort_keys=True)
    assert "sudo-secret-value" not in serialized
    assert "IMAGE_AGENT_SUDO_PASSWORD" not in serialized


def test_setup_run_failure_includes_redacted_error_tail(monkeypatch):
    script = _load_setup_script()

    def fake_run(cmd, **kwargs):
        class Proc:
            returncode = 1
            stdout = "ignored stdout"
            stderr = "Authorization: Bearer embedding-secret-token failed"

        return Proc()

    monkeypatch.setattr(script.subprocess, "run", fake_run)

    with pytest.raises(SystemExit) as exc:
        script._run(["docker", "info"])

    message = str(exc.value)
    assert "command failed: docker info" in message
    assert "[redacted-secret]" in message
    assert "embedding-secret-token" not in message
    assert "Authorization" not in message


def test_setup_plan_can_derive_embedding_config_from_existing_env_file_without_secret_leak(tmp_path, monkeypatch):
    script = _load_setup_script()
    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join(
            [
                "OPENAI_API_KEY=embedding-secret-token",
                "OPENAI_BASE_URL=https://embedding.example/v1",
                "OPENAI_MODEL=gpt-5.5",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.delenv("IMAGE_AGENT_RAG_EMBEDDING_MODEL", raising=False)
    monkeypatch.delenv("IMAGE_AGENT_RAG_EMBEDDING_BASE_URL", raising=False)
    monkeypatch.delenv("IMAGE_AGENT_MODEL_BASE_URL", raising=False)
    monkeypatch.delenv("RAWCHAT_BASE_URL", raising=False)
    monkeypatch.delenv("KRILL_BASE_URL", raising=False)
    monkeypatch.delenv("OPENAI_EMBEDDING_MODEL", raising=False)

    plan = script.build_setup_plan(
        env_file=env_file,
        index_name="image_agent_rag_release_20260620",
        embedding_provider="openai_compatible",
        embedding_model="",
        embedding_base_url="",
        derive_embedding_from_env=True,
        apply_changes=False,
    )

    assert plan["env_updates"]["IMAGE_AGENT_RAG_EMBEDDING_PROVIDER"] == "openai_compatible"
    assert plan["env_updates"]["IMAGE_AGENT_RAG_EMBEDDING_MODEL"] == "text-embedding-3-small"
    assert plan["env_updates"]["IMAGE_AGENT_RAG_EMBEDDING_BASE_URL"] == "https://embedding.example/v1"
    assert plan["embedding_config_source"] == {
        "model": "default_text_embedding_3_small",
        "base_url": "OPENAI_BASE_URL",
        "api_key": "existing_runtime_fallback_present",
    }
    serialized = json.dumps(plan, sort_keys=True)
    assert "embedding-secret-token" not in serialized
    assert "OPENAI_API_KEY=embedding-secret-token" not in serialized


def test_setup_plan_derivation_overrides_local_hashing_placeholder_model(tmp_path, monkeypatch):
    script = _load_setup_script()
    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join(
            [
                "OPENAI_API_KEY=embedding-secret-token",
                "OPENAI_BASE_URL=https://embedding.example/v1",
                "IMAGE_AGENT_RAG_EMBEDDING_PROVIDER=local_hashing",
                "IMAGE_AGENT_RAG_EMBEDDING_MODEL=local-token-hash-v1",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.delenv("IMAGE_AGENT_RAG_EMBEDDING_MODEL", raising=False)
    monkeypatch.delenv("IMAGE_AGENT_RAG_EMBEDDING_BASE_URL", raising=False)
    monkeypatch.delenv("IMAGE_AGENT_MODEL_BASE_URL", raising=False)
    monkeypatch.delenv("RAWCHAT_BASE_URL", raising=False)
    monkeypatch.delenv("KRILL_BASE_URL", raising=False)
    monkeypatch.delenv("OPENAI_EMBEDDING_MODEL", raising=False)

    plan = script.build_setup_plan(
        env_file=env_file,
        index_name="image_agent_rag_release_20260620",
        embedding_provider="openai_compatible",
        embedding_model="",
        embedding_base_url="",
        derive_embedding_from_env=True,
        apply_changes=False,
    )

    assert plan["env_updates"]["IMAGE_AGENT_RAG_EMBEDDING_PROVIDER"] == "openai_compatible"
    assert plan["env_updates"]["IMAGE_AGENT_RAG_EMBEDDING_MODEL"] == "text-embedding-3-small"
    assert plan["env_updates"]["IMAGE_AGENT_RAG_EMBEDDING_BASE_URL"] == "https://embedding.example/v1"
    assert plan["embedding_config_source"]["model"] == "default_text_embedding_3_small"


def test_start_trial_license_posts_to_loopback_without_proxy(monkeypatch):
    script = _load_setup_script()
    calls = {}

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            return b'{"acknowledged": true, "trial_was_started": true}'

    class Opener:
        def open(self, request, timeout):
            calls["url"] = request.full_url
            calls["timeout"] = timeout
            return Response()

    def fake_build_opener(proxy_handler):
        calls["proxy_handler"] = proxy_handler
        return Opener()

    monkeypatch.setenv("HTTP_PROXY", "http://bad proxy value")
    monkeypatch.setattr(script.urllib.request, "build_opener", fake_build_opener)

    result = script._start_trial_license("http://127.0.0.1:9200", attempts=1, delay_seconds=0)

    assert result["status"] == "started"
    assert calls["url"] == "http://127.0.0.1:9200/_license/start_trial?acknowledge=true"
    assert calls["timeout"] == 10
    assert calls["proxy_handler"].proxies == {}
