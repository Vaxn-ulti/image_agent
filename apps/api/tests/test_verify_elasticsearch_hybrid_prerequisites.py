import importlib.util
import json
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPT_PATH = REPO_ROOT / "apps" / "api" / "scripts" / "verify_elasticsearch_hybrid_prerequisites.py"
ELASTICSEARCH_RRF_SOURCE_URL = "https://www.elastic.co/docs/reference/elasticsearch/rest-apis/reciprocal-rank-fusion"


def _load_script():
    spec = importlib.util.spec_from_file_location("verify_elasticsearch_hybrid_prerequisites", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _connected_production_status(**hybrid_overrides):
    hybrid = {
        "engine": "elasticsearch",
        "configured": True,
        "mode": "connected",
        "persisted": True,
        "index": "image_agent_rag",
        "indexed_chunk_count": 260,
        "lexical_retriever": "standard",
        "vector_retriever": "knn",
        "dense_vector_field": "embedding",
        "dense_vector_dims": 1536,
        "fusion": "rrf",
        "embedding_provider": "openai",
        "embedding_model": "text-embedding-3-small",
        "embedding_transport": "openai_compatible_http",
        "embedding_endpoint_configured": True,
        "embedding_production_ready": True,
        "official_sources": [ELASTICSEARCH_RRF_SOURCE_URL],
    }
    hybrid.update(hybrid_overrides)
    return {"index": {"engine": "elasticsearch_hybrid", "hybrid_search": hybrid}}


def _ready_runtime_probe(**elasticsearch_overrides):
    elasticsearch = {
        "configured": True,
        "endpoint_configured": True,
        "endpoint_source": "env_redacted",
        "runtime_discovery": {
            "scope": "local_docker_elasticsearch",
            "status": "available",
            "count": 1,
            "running_count": 1,
            "container_running": True,
            "candidate_endpoint": "http://127.0.0.1:9200",
            "candidate_endpoint_source": "container_port_mapping",
        },
    }
    elasticsearch.update(elasticsearch_overrides)
    return {
        "schema_version": 1,
        "portable": True,
        "machine_binding": "runtime_discovered",
        "workflow_tool_execution": "deployment_server_local",
        "docker_runtime_host": "api_server",
        "docker": {
            "accessible": True,
            "requires_sudo": False,
        },
        "elasticsearch": elasticsearch,
    }


def test_verify_elasticsearch_hybrid_prerequisites_accepts_safe_configured_env_and_connected_status(tmp_path):
    script = _load_script()
    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join(
            [
                "IMAGE_AGENT_ELASTICSEARCH_URL=https://elastic:secret@example.local:9200",
                "IMAGE_AGENT_ELASTICSEARCH_API_KEY=sk-elastic-secret",
                "IMAGE_AGENT_RAG_EMBEDDING_PROVIDER=openai_compatible",
                "IMAGE_AGENT_RAG_EMBEDDING_MODEL=text-embedding-3-small",
                "IMAGE_AGENT_RAG_EMBEDDING_BASE_URL=https://embedding.example/v1",
            ]
        ),
        encoding="utf-8",
    )

    report = script.verify_prerequisites(
        env_file=env_file,
        rag_status=_connected_production_status(),
    )

    assert report["status"] == "passed"
    assert report["checked"] == {
        "elasticsearch_url_configured": True,
        "elasticsearch_api_key_configured": True,
        "elasticsearch_index_configured": False,
        "rag_embedding_provider_configured": True,
        "rag_embedding_provider_production_configured": True,
        "rag_embedding_model_configured": True,
        "rag_embedding_api_key_configured": False,
        "rag_embedding_endpoint_configured": True,
        "rag_status_engine": "elasticsearch_hybrid",
        "rag_status_hybrid_configured": True,
        "rag_status_hybrid_engine": "elasticsearch",
        "rag_status_hybrid_index": "image_agent_rag",
        "rag_status_hybrid_index_matches_env": True,
        "rag_status_hybrid_mode": "connected",
        "rag_status_hybrid_persisted": True,
        "rag_status_hybrid_indexed_chunk_count": 260,
        "rag_status_hybrid_lexical_retriever": "standard",
        "rag_status_hybrid_vector_retriever": "knn",
        "rag_status_hybrid_dense_vector_field": "embedding",
        "rag_status_hybrid_dense_vector_dims": 1536,
        "rag_status_hybrid_fusion": "rrf",
        "rag_status_hybrid_official_rrf_source_present": True,
        "rag_status_hybrid_error_absent": True,
        "rag_status_hybrid_embedding_error_absent": True,
        "rag_status_hybrid_embedding_provider": "openai",
        "rag_status_hybrid_embedding_provider_matches_env": True,
        "rag_status_hybrid_embedding_model": "text-embedding-3-small",
        "rag_status_hybrid_embedding_model_matches_env": True,
        "rag_status_hybrid_embedding_transport": "openai_compatible_http",
        "rag_status_hybrid_embedding_endpoint_configured": True,
        "rag_status_hybrid_embedding_production_ready": True,
        "secrets_redacted": True,
    }
    serialized = json.dumps(report, sort_keys=True)
    assert "elastic-secret" not in serialized
    assert "embedding-secret" not in serialized
    assert "example.local" not in serialized
    assert "embedding.example" not in serialized
    assert "sk-" not in serialized


def test_verify_elasticsearch_hybrid_prerequisites_accepts_runtime_discovered_local_docker_es(tmp_path):
    script = _load_script()
    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join(
            [
                "IMAGE_AGENT_ELASTICSEARCH_URL=https://elastic:secret@example.local:9200",
                "IMAGE_AGENT_ELASTICSEARCH_API_KEY=sk-elastic-secret",
                "IMAGE_AGENT_RAG_EMBEDDING_PROVIDER=openai_compatible",
                "IMAGE_AGENT_RAG_EMBEDDING_MODEL=text-embedding-3-small",
                "IMAGE_AGENT_RAG_EMBEDDING_BASE_URL=https://embedding.example/v1",
            ]
        ),
        encoding="utf-8",
    )

    report = script.verify_prerequisites(
        env_file=env_file,
        rag_status=_connected_production_status(),
        runtime_probe=_ready_runtime_probe(),
    )

    assert report["status"] == "passed"
    checked = report["checked"]
    assert checked["runtime_probe_supplied"] is True
    assert checked["runtime_probe_machine_binding"] == "runtime_discovered"
    assert checked["runtime_probe_workflow_tool_execution"] == "deployment_server_local"
    assert checked["runtime_probe_docker_runtime_host"] == "api_server"
    assert checked["runtime_probe_docker_accessible"] is True
    assert checked["runtime_probe_docker_requires_sudo"] is False
    assert checked["runtime_probe_elasticsearch_configured"] is True
    assert checked["runtime_probe_elasticsearch_endpoint_source"] == "env_redacted"
    assert checked["runtime_probe_elasticsearch_discovery_scope"] == "local_docker_elasticsearch"
    assert checked["runtime_probe_elasticsearch_discovery_status"] == "available"
    assert checked["runtime_probe_elasticsearch_container_running"] is True
    assert checked["runtime_probe_elasticsearch_candidate_endpoint"] == "http://127.0.0.1:9200"
    serialized = json.dumps(report, sort_keys=True)
    assert "elastic-secret" not in serialized
    assert "example.local" not in serialized
    assert "sk-" not in serialized


def test_verify_elasticsearch_hybrid_prerequisites_rejects_runtime_probe_without_local_docker_es(tmp_path):
    script = _load_script()
    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join(
            [
                "IMAGE_AGENT_ELASTICSEARCH_URL=https://elastic:secret@example.local:9200",
                "IMAGE_AGENT_RAG_EMBEDDING_PROVIDER=openai_compatible",
                "IMAGE_AGENT_RAG_EMBEDDING_MODEL=text-embedding-3-small",
                "IMAGE_AGENT_RAG_EMBEDDING_BASE_URL=https://embedding.example/v1",
            ]
        ),
        encoding="utf-8",
    )

    with pytest.raises(SystemExit) as exc:
        script.verify_prerequisites(
            env_file=env_file,
            rag_status=_connected_production_status(),
            runtime_probe=_ready_runtime_probe(
                runtime_discovery={
                    "scope": "local_docker_elasticsearch",
                    "status": "unavailable",
                    "count": 0,
                    "running_count": 0,
                    "container_running": False,
                }
            ),
        )

    message = str(exc.value)
    assert "Runtime probe must discover a running local Docker Elasticsearch container" in message
    assert "example.local" not in message
    assert "elastic:secret" not in message


def test_verify_elasticsearch_hybrid_prerequisites_cli_emits_safe_failed_json_for_docker_access(tmp_path, monkeypatch, capsys):
    script = _load_script()
    env_file = tmp_path / ".env"
    runtime_probe_json = tmp_path / "runtime_probe.json"
    env_file.write_text(
        "\n".join(
            [
                "IMAGE_AGENT_ELASTICSEARCH_URL=https://elastic:secret@example.local:9200",
                "IMAGE_AGENT_RAG_EMBEDDING_PROVIDER=openai_compatible",
                "IMAGE_AGENT_RAG_EMBEDDING_MODEL=text-embedding-3-small",
                "IMAGE_AGENT_RAG_EMBEDDING_BASE_URL=https://embedding.example/v1",
            ]
        ),
        encoding="utf-8",
    )
    runtime_probe_json.write_text(
        json.dumps(
            _ready_runtime_probe(
                runtime_discovery={
                    "scope": "local_docker_elasticsearch",
                    "status": "unavailable",
                    "count": 0,
                    "running_count": 0,
                    "container_running": False,
                }
            )
            | {
                "docker": {
                    "accessible": False,
                    "requires_sudo": True,
                },
                "blocking_codes": ["docker_requires_sudo", "elasticsearch_not_reachable"],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(script, "_fetch_rag_status", lambda _url: _connected_production_status())

    with pytest.raises(SystemExit) as exc:
        script.main(
            [
                "--env-file",
                str(env_file),
                "--rag-status-url",
                "http://127.0.0.1:8000/agent/rag/status",
                "--runtime-probe-json",
                str(runtime_probe_json),
            ]
        )

    assert exc.value.code == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "failed"
    assert payload["checked"]["runtime_probe_docker_accessible"] is False
    assert payload["checked"]["runtime_probe_docker_requires_sudo"] is True
    assert "docker_requires_sudo" in payload["checked"]["runtime_probe_blocking_codes"]
    assert "Runtime probe Docker access must be available" in payload["failures"]
    assert "Runtime probe Docker access must not require sudo" in payload["failures"]
    assert "Runtime probe must discover a running local Docker Elasticsearch container" in payload["failures"]
    serialized = json.dumps(payload, sort_keys=True)
    assert "elastic:secret" not in serialized
    assert "example.local" not in serialized
    assert "embedding.example" not in serialized


def test_verify_elasticsearch_hybrid_prerequisites_requires_env_index_to_match_status(tmp_path):
    script = _load_script()
    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join(
            [
                "IMAGE_AGENT_ELASTICSEARCH_URL=https://elastic:secret@example.local:9200",
                "IMAGE_AGENT_ELASTICSEARCH_INDEX=image_agent_rag_release_20260619",
                "IMAGE_AGENT_RAG_EMBEDDING_PROVIDER=openai_compatible",
                "IMAGE_AGENT_RAG_EMBEDDING_MODEL=text-embedding-3-small",
                "IMAGE_AGENT_RAG_EMBEDDING_BASE_URL=https://embedding.example/v1",
            ]
        ),
        encoding="utf-8",
    )

    with pytest.raises(SystemExit) as exc:
        script.verify_prerequisites(
            env_file=env_file,
            rag_status=_connected_production_status(index="image_agent_rag_previous"),
        )

    message = str(exc.value)
    assert "Current /agent/rag/status hybrid index must match IMAGE_AGENT_ELASTICSEARCH_INDEX" in message
    assert "image_agent_rag_release_20260619" not in message
    assert "image_agent_rag_previous" not in message
    assert "example.local" not in message


def test_verify_elasticsearch_hybrid_prerequisites_rejects_missing_current_status(tmp_path):
    script = _load_script()
    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join(
            [
                "IMAGE_AGENT_ELASTICSEARCH_URL=https://elastic:secret@example.local:9200",
                "IMAGE_AGENT_RAG_EMBEDDING_PROVIDER=openai_compatible",
                "IMAGE_AGENT_RAG_EMBEDDING_MODEL=text-embedding-3-small",
                "IMAGE_AGENT_RAG_EMBEDDING_BASE_URL=https://embedding.example/v1",
            ]
        ),
        encoding="utf-8",
    )

    with pytest.raises(SystemExit) as exc:
        script.verify_prerequisites(env_file=env_file, rag_status=None)

    message = str(exc.value)
    assert "Current /agent/rag/status must be supplied" in message
    assert "example.local" not in message
    assert "embedding.example" not in message


def test_verify_elasticsearch_hybrid_prerequisites_rejects_missing_connected_config(tmp_path):
    script = _load_script()
    env_file = tmp_path / ".env"
    env_file.write_text("OPENAI_API_KEY=sk-model-secret\n", encoding="utf-8")

    with pytest.raises(SystemExit) as exc:
        script.verify_prerequisites(
            env_file=env_file,
            rag_status={"index": {"engine": "llama_index"}},
        )

    message = str(exc.value)
    assert "IMAGE_AGENT_ELASTICSEARCH_URL must be configured" in message
    assert "IMAGE_AGENT_RAG_EMBEDDING_PROVIDER must be configured" in message
    assert "IMAGE_AGENT_RAG_EMBEDDING_BASE_URL must be configured" in message
    assert "Current /agent/rag/status engine is not elasticsearch_hybrid" in message
    assert "sk-model-secret" not in message


def test_verify_elasticsearch_hybrid_prerequisites_rejects_non_connected_status(tmp_path):
    script = _load_script()
    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join(
            [
                "IMAGE_AGENT_ELASTICSEARCH_URL=https://elastic:secret@example.local:9200",
                "IMAGE_AGENT_RAG_EMBEDDING_PROVIDER=openai_compatible",
                "IMAGE_AGENT_RAG_EMBEDDING_MODEL=text-embedding-3-small",
                "IMAGE_AGENT_RAG_EMBEDDING_BASE_URL=https://embedding.example/v1",
            ]
        ),
        encoding="utf-8",
    )

    with pytest.raises(SystemExit) as exc:
        script.verify_prerequisites(
            env_file=env_file,
            rag_status={
                "index": {
                    "engine": "elasticsearch_hybrid",
                    "hybrid_search": {
                        "mode": "local_contract",
                        "persisted": False,
                    },
                }
            },
        )

    message = str(exc.value)
    assert "Current /agent/rag/status hybrid mode is not connected" in message
    assert "Current /agent/rag/status hybrid index is not persisted" in message
    assert "example.local" not in message
    assert "embedding.example" not in message


@pytest.mark.parametrize(
    ("hybrid_override", "expected_message"),
    [
        ({"configured": False}, "Current /agent/rag/status hybrid search is not configured"),
        ({"index": "C:/private/image_agent_rag"}, "Current /agent/rag/status hybrid index is not privacy-safe"),
        ({"indexed_chunk_count": 0}, "Current /agent/rag/status indexed_chunk_count must be greater than zero"),
        ({"lexical_retriever": "match"}, "Current /agent/rag/status lexical retriever is not standard"),
        ({"vector_retriever": "script_score"}, "Current /agent/rag/status vector retriever is not knn"),
        ({"dense_vector_field": "vector"}, "Current /agent/rag/status dense_vector_field is not embedding"),
        ({"dense_vector_dims": 0}, "Current /agent/rag/status dense_vector_dims must be greater than zero"),
        ({"fusion": "dbsf"}, "Current /agent/rag/status hybrid fusion is not rrf"),
        ({"official_sources": []}, "Current /agent/rag/status official_sources must include Elasticsearch RRF documentation"),
        (
            {"official_sources": ["https://docs.example.invalid/rrf"]},
            "Current /agent/rag/status official_sources must include Elasticsearch RRF documentation",
        ),
        ({"error": "[redacted-secret] connection refused"}, "Current /agent/rag/status hybrid error must be absent"),
        ({"embedding_error": "[redacted-secret]"}, "Current /agent/rag/status embedding error must be absent"),
        ({"embedding_provider": "local_hashing"}, "Current /agent/rag/status embedding provider is not production configured"),
        ({"embedding_model": ""}, "Current /agent/rag/status embedding model must be present"),
        ({"embedding_transport": "local"}, "Current /agent/rag/status embedding transport is not production-safe"),
        ({"embedding_endpoint_configured": False}, "Current /agent/rag/status embedding endpoint must be configured"),
        ({"embedding_production_ready": False}, "Current /agent/rag/status embedding production readiness must be true"),
    ],
)
def test_verify_elasticsearch_hybrid_prerequisites_rejects_weak_connected_status(
    tmp_path, hybrid_override, expected_message
):
    script = _load_script()
    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join(
            [
                "IMAGE_AGENT_ELASTICSEARCH_URL=https://elastic:secret@example.local:9200",
                "IMAGE_AGENT_RAG_EMBEDDING_PROVIDER=openai_compatible",
                "IMAGE_AGENT_RAG_EMBEDDING_MODEL=text-embedding-3-small",
                "IMAGE_AGENT_RAG_EMBEDDING_BASE_URL=https://embedding.example/v1",
            ]
        ),
        encoding="utf-8",
    )

    with pytest.raises(SystemExit) as exc:
        script.verify_prerequisites(
            env_file=env_file,
            rag_status=_connected_production_status(**hybrid_override),
        )

    message = str(exc.value)
    assert expected_message in message
    assert "example.local" not in message
    assert "embedding.example" not in message
    assert "[redacted-secret]" not in message


def test_verify_elasticsearch_hybrid_prerequisites_rejects_env_status_embedding_model_drift(tmp_path):
    script = _load_script()
    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join(
            [
                "IMAGE_AGENT_ELASTICSEARCH_URL=https://elastic:secret@example.local:9200",
                "IMAGE_AGENT_RAG_EMBEDDING_PROVIDER=openai_compatible",
                "IMAGE_AGENT_RAG_EMBEDDING_MODEL=text-embedding-3-small",
                "IMAGE_AGENT_RAG_EMBEDDING_BASE_URL=https://embedding.example/v1",
            ]
        ),
        encoding="utf-8",
    )

    with pytest.raises(SystemExit) as exc:
        script.verify_prerequisites(
            env_file=env_file,
            rag_status=_connected_production_status(embedding_model="text-embedding-3-large"),
        )

    message = str(exc.value)
    assert "Current /agent/rag/status embedding model must match IMAGE_AGENT_RAG_EMBEDDING_MODEL" in message
    assert "text-embedding-3-small" not in message
    assert "text-embedding-3-large" not in message
    assert "example.local" not in message
    assert "embedding.example" not in message


def test_verify_elasticsearch_hybrid_prerequisites_rejects_env_status_embedding_provider_drift(tmp_path):
    script = _load_script()
    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join(
            [
                "IMAGE_AGENT_ELASTICSEARCH_URL=https://elastic:secret@example.local:9200",
                "IMAGE_AGENT_RAG_EMBEDDING_PROVIDER=rawchat",
                "IMAGE_AGENT_RAG_EMBEDDING_MODEL=text-embedding-3-small",
                "IMAGE_AGENT_RAG_EMBEDDING_BASE_URL=https://embedding.example/v1",
            ]
        ),
        encoding="utf-8",
    )

    with pytest.raises(SystemExit) as exc:
        script.verify_prerequisites(
            env_file=env_file,
            rag_status=_connected_production_status(embedding_provider="openai"),
        )

    message = str(exc.value)
    assert "Current /agent/rag/status embedding provider must match IMAGE_AGENT_RAG_EMBEDDING_PROVIDER" in message
    assert "rawchat" not in message
    assert "openai" not in message
    assert "example.local" not in message
    assert "embedding.example" not in message


def test_verify_elasticsearch_hybrid_prerequisites_rejects_local_env_embedding_provider(tmp_path):
    script = _load_script()
    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join(
            [
                "IMAGE_AGENT_ELASTICSEARCH_URL=https://elastic:secret@example.local:9200",
                "IMAGE_AGENT_RAG_EMBEDDING_PROVIDER=local_hashing",
                "IMAGE_AGENT_RAG_EMBEDDING_MODEL=text-embedding-3-small",
                "IMAGE_AGENT_RAG_EMBEDDING_BASE_URL=https://embedding.example/v1",
            ]
        ),
        encoding="utf-8",
    )

    with pytest.raises(SystemExit) as exc:
        script.verify_prerequisites(
            env_file=env_file,
            rag_status=_connected_production_status(),
        )

    message = str(exc.value)
    assert "IMAGE_AGENT_RAG_EMBEDDING_PROVIDER must be production configured" in message
    assert "local_hashing" not in message
    assert "example.local" not in message
    assert "embedding.example" not in message
