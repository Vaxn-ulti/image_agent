from __future__ import annotations

import subprocess

from fastapi.testclient import TestClient

from app import app_factory
from app.scripts import probe_runtime_environment
from app.agent import runtime


def _runtime_status() -> dict:
    return {
        "docker_requires_sudo": True,
        "fs_license_path": "/home/yyf/license.txt",
        "fs_license_exists": True,
        "runtime_preparation": {
            "auto_pull_missing_images": True,
            "setting": "IMAGE_AGENT_AUTO_PULL_MISSING_WORKFLOW_IMAGES",
            "pull_attempted_count": 1,
            "pull_succeeded_count": 1,
            "pull_failed_count": 0,
        },
        "qsirecon_profile": "dki",
        "qsirecon_recon_spec": "dipy_dki",
        "workflows": {
            "t1_deepprep": {
                "image": "pbfslab/deepprep:25.1.0",
                "available": True,
                "pull_attempted": True,
                "pull_status": "pulled",
                "detail_tail": "sha256:abc backend path /home/yyf/project/image_agent",
            },
            "dwi_fast_gpu_dti": {
                "image": "brainlife/mrtrix3:3.0.4",
                "available": False,
                "detail_tail": "permission denied /var/run/docker.sock",
            },
        },
    }


def _agent_containers() -> list[dict]:
    return [
        {"task_id": "12", "state": "running", "name": "image-agent-task-12"},
        {"task_id": "13", "state": "exited", "name": "image-agent-task-13"},
    ]


def test_elasticsearch_container_discovery_uses_configured_docker_command(monkeypatch):
    calls = []

    def fake_check_output(command, **kwargs):
        calls.append(command)
        return (
            b'{"Image":"docker.elastic.co/elasticsearch/elasticsearch:9.4.2",'
            b'"Names":"image-agent-es",'
            b'"State":"running",'
            b'"Ports":"127.0.0.1:9200->9200/tcp"}\n'
        )

    monkeypatch.setenv("IMAGE_AGENT_DOCKER_COMMAND", "sudo -n docker")
    monkeypatch.setenv("IMAGE_AGENT_SUDO_PASSWORD", "secret-not-for-runtime-probe")
    monkeypatch.setattr(subprocess, "check_output", fake_check_output)

    containers = runtime.list_elasticsearch_containers()

    assert calls[0][:3] == ["sudo", "-n", "docker"]
    assert containers[0]["name"] == "image-agent-es"
    assert "secret-not-for-runtime-probe" not in str(calls)


def _elasticsearch_containers() -> list[dict]:
    return [
        {
            "name": "image-agent-elasticsearch",
            "image": "docker.elastic.co/elasticsearch/elasticsearch:8.15.3",
            "state": "running",
            "ports": ["127.0.0.1:9200->9200/tcp"],
            "labels": {"co.elastic.version": "8.15.3"},
            "env": {"ELASTIC_PASSWORD": "super-secret"},
        },
        {
            "name": "old-elastic",
            "image": "elasticsearch:7.17",
            "state": "exited",
            "ports": [],
        },
    ]


def test_runtime_probe_wraps_local_toolchain_status_without_machine_specific_leaks(monkeypatch):
    monkeypatch.setattr(runtime, "inspect_runtime", _runtime_status)
    monkeypatch.setattr(runtime, "list_image_agent_containers", _agent_containers)
    monkeypatch.delenv("IMAGE_AGENT_ELASTICSEARCH_URL", raising=False)

    probe = runtime.runtime_probe()

    assert probe["schema_version"] == 1
    assert probe["status"] == "blocked"
    assert probe["workflow_tool_execution"] == "deployment_server_local"
    assert probe["docker_runtime_host"] == "api_server"
    assert probe["portable"] is True
    assert probe["machine_binding"] == "runtime_discovered"
    assert probe["docker"]["requires_sudo"] is True
    assert probe["docker"]["accessible"] is False
    assert probe["resources"]["fs_license_exists"] is True
    assert probe["resources"]["fs_license_configured"] is True
    assert probe["runtime_preparation"] == {
        "auto_pull_missing_images": True,
        "setting": "IMAGE_AGENT_AUTO_PULL_MISSING_WORKFLOW_IMAGES",
        "pull_attempted_count": 1,
        "pull_succeeded_count": 1,
        "pull_failed_count": 0,
    }
    assert probe["elasticsearch"]["configured"] is False
    assert probe["elasticsearch"]["reachable"] is False
    assert probe["containers"] == {
        "scope": "image_agent_labeled",
        "count": 2,
        "running_count": 1,
        "exited_count": 1,
    }
    assert probe["workflows"]["t1_deepprep"]["available"] is True
    assert probe["workflows"]["t1_deepprep"]["pull_attempted"] is True
    assert probe["workflows"]["t1_deepprep"]["pull_status"] == "pulled"
    assert probe["workflows"]["dwi_fast_gpu_dti"]["available"] is False
    assert "detail_tail" not in probe["workflows"]["t1_deepprep"]
    assert "fs_license_path" not in probe
    assert "/home/yyf" not in str(probe)
    assert "blocking_codes" in probe
    assert "docker_requires_sudo" in probe["blocking_codes"]
    assert "workflow_dwi_fast_gpu_dti_unavailable" in probe["blocking_codes"]


def test_runtime_containers_keeps_legacy_fields_and_embeds_runtime_probe(monkeypatch):
    monkeypatch.setattr(runtime, "inspect_runtime", _runtime_status)
    monkeypatch.setattr(runtime, "list_image_agent_containers", _agent_containers)
    monkeypatch.delenv("IMAGE_AGENT_ELASTICSEARCH_URL", raising=False)

    response = runtime.runtime_containers()

    assert response["fs_license_exists"] is True
    assert response["docker_requires_sudo"] is True
    assert response["workflows"]["t1_deepprep"]["available"] is True
    assert "fs_license_path" not in response
    assert "detail_tail" not in response["workflows"]["t1_deepprep"]
    assert response["runtime_probe"]["schema_version"] == 1
    assert response["runtime_probe"]["workflows"]["t1_deepprep"]["image"] == "pbfslab/deepprep:25.1.0"
    assert "fs_license_path" not in response["runtime_probe"]
    assert "detail_tail" not in response["runtime_probe"]["workflows"]["t1_deepprep"]
    assert response["runtime_probe"]["containers"]["running_count"] == 1


def test_runtime_probe_api_route_uses_portable_contract(monkeypatch):
    monkeypatch.setattr(runtime, "inspect_runtime", _runtime_status)
    monkeypatch.setattr(runtime, "list_image_agent_containers", _agent_containers)
    monkeypatch.delenv("IMAGE_AGENT_ELASTICSEARCH_URL", raising=False)

    client = TestClient(app_factory.create_app())
    response = client.get("/runtime/probe")

    assert response.status_code == 200
    payload = response.json()
    assert payload["schema_version"] == 1
    assert payload["workflow_tool_execution"] == "deployment_server_local"
    assert payload["docker_runtime_host"] == "api_server"
    assert "fs_license_path" not in payload
    assert "detail_tail" not in str(payload)


def test_probe_runtime_environment_cli_outputs_portable_json(monkeypatch, capsys):
    monkeypatch.setattr(runtime, "inspect_runtime", _runtime_status)
    monkeypatch.setattr(runtime, "list_image_agent_containers", _agent_containers)
    monkeypatch.delenv("IMAGE_AGENT_ELASTICSEARCH_URL", raising=False)

    probe_runtime_environment.main(["--json"])

    captured = capsys.readouterr()
    assert '"schema_version": 1' in captured.out
    assert '"machine_binding": "runtime_discovered"' in captured.out
    assert "/home/yyf" not in captured.out
    assert "detail_tail" not in captured.out


def test_runtime_probe_reports_container_probe_errors_without_crashing(monkeypatch):
    monkeypatch.setattr(runtime, "inspect_runtime", _runtime_status)
    monkeypatch.delenv("IMAGE_AGENT_ELASTICSEARCH_URL", raising=False)

    def broken_container_lister():
        raise RuntimeError("IMAGE_AGENT_SUDO_PASSWORD is required for docker commands")

    monkeypatch.setattr(runtime, "list_image_agent_containers", broken_container_lister)

    probe = runtime.runtime_probe()

    assert probe["status"] == "blocked"
    assert probe["containers"] == {
        "scope": "image_agent_labeled",
        "count": 0,
        "running_count": 0,
        "exited_count": 0,
        "status": "unavailable",
    }
    assert "container_probe_unavailable" in probe["blocking_codes"]
    assert "IMAGE_AGENT_SUDO_PASSWORD" not in str(probe)


def test_runtime_probe_discovers_local_elasticsearch_container_without_leaking_values(monkeypatch):
    monkeypatch.setattr(runtime, "inspect_runtime", _runtime_status)
    monkeypatch.setattr(runtime, "list_image_agent_containers", _agent_containers)
    monkeypatch.setenv("IMAGE_AGENT_ELASTICSEARCH_URL", "http://elastic:secret@127.0.0.1:9200")
    monkeypatch.setattr(
        runtime,
        "_probe_elasticsearch_endpoint",
        lambda *, url, api_key, timeout_seconds=2.0: {
            "status": "reachable",
            "reachable": True,
            "http_status": 200,
            "proxy_env_trusted": False,
        },
    )
    monkeypatch.setattr(runtime, "list_elasticsearch_containers", _elasticsearch_containers)

    probe = runtime.runtime_probe()

    assert probe["elasticsearch"]["configured"] is True
    assert probe["elasticsearch"]["reachable"] is True
    assert probe["elasticsearch"]["endpoint_configured"] is True
    assert probe["elasticsearch"]["endpoint_source"] == "env_redacted"
    assert "elasticsearch_not_reachable" not in probe["blocking_codes"]
    assert probe["elasticsearch"]["runtime_discovery"] == {
        "scope": "local_docker_elasticsearch",
        "status": "available",
        "count": 2,
        "running_count": 1,
        "candidate_endpoint": "http://127.0.0.1:9200",
        "candidate_endpoint_source": "container_port_mapping",
        "container_running": True,
    }
    serialized = str(probe)
    assert "super-secret" not in serialized
    assert "elastic:secret" not in serialized
    assert "ELASTIC_PASSWORD" not in serialized


def test_elasticsearch_endpoint_probe_uses_direct_opener_and_api_key_without_leaking_values(monkeypatch):
    captured = {}

    class FakeResponse:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    class FakeOpener:
        def open(self, request, timeout):
            captured["url"] = request.full_url
            captured["headers"] = dict(request.header_items())
            captured["timeout"] = timeout
            return FakeResponse()

    report = runtime._probe_elasticsearch_endpoint(
        url="http://elastic:secret@127.0.0.1:9200",
        api_key="api-secret-value",
        timeout_seconds=1.5,
        opener_factory=lambda: FakeOpener(),
    )

    assert report == {
        "status": "reachable",
        "reachable": True,
        "http_status": 200,
        "proxy_env_trusted": False,
    }
    assert captured["url"] == "http://elastic:secret@127.0.0.1:9200/"
    assert captured["headers"]["Authorization"] == "ApiKey api-secret-value"
    assert captured["timeout"] == 1.5
    serialized = str(report)
    assert "api-secret-value" not in serialized
    assert "elastic:secret" not in serialized


def test_elasticsearch_endpoint_probe_reports_failure_without_leaking_error_values():
    class FakeOpener:
        def open(self, request, timeout):
            raise OSError("connection failed for api-secret-value")

    report = runtime._probe_elasticsearch_endpoint(
        url="http://elastic:secret@127.0.0.1:9200",
        api_key="api-secret-value",
        opener_factory=lambda: FakeOpener(),
    )

    assert report == {
        "status": "unreachable",
        "reachable": False,
        "error_type": "OSError",
        "proxy_env_trusted": False,
    }
    serialized = str(report)
    assert "api-secret-value" not in serialized
    assert "elastic:secret" not in serialized
    assert "connection failed" not in serialized


def test_elasticsearch_container_discovery_tolerates_non_default_encoded_docker_output(monkeypatch):
    def fake_check_output(*args, **kwargs):
        assert kwargs.get("text") is not True
        return (
            b'{"Image":"docker.elastic.co/elasticsearch/elasticsearch:8.15.3",'
            b'"Names":"'
            + "elastic-\u672c".encode("utf-8")
            + b'",'
            b'"State":"running",'
            b'"Ports":"0.0.0.0:9200->9200/tcp"}\n'
        )

    monkeypatch.setattr(subprocess, "check_output", fake_check_output)

    containers = runtime.list_elasticsearch_containers()

    assert containers == [
        {
            "name": "elastic-本",
            "image": "docker.elastic.co/elasticsearch/elasticsearch:8.15.3",
            "state": "running",
            "ports": "0.0.0.0:9200->9200/tcp",
        }
    ]
