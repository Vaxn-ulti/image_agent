from fastapi.testclient import TestClient
import hashlib
import json
import sys
import types

import pytest


MODEL_ENV_KEYS = [
    "IMAGE_AGENT_MODEL_PROVIDER",
    "IMAGE_AGENT_MODEL_API_KEY",
    "IMAGE_AGENT_MODEL_BASE_URL",
    "IMAGE_AGENT_MODEL_NAME",
    "IMAGE_AGENT_MODEL_REVIEW_NAME",
    "IMAGE_AGENT_MODEL_WIRE_API",
    "MODEL_PROVIDER",
    "OPENAI_API_KEY",
    "OPENAI_BASE_URL",
    "OPENAI_MODEL",
    "OPENAI_REVIEW_MODEL",
    "OPENAI_WIRE_API",
    "RAWCHAT_API_KEY",
    "RAWCHAT_BASE_URL",
    "RAWCHAT_MODEL",
    "RAWCHAT_WIRE_API",
    "KRILL_API_KEY",
    "KRILL_BASE_URL",
    "KRILL_MODEL",
    "KRILL_WIRE_API",
    "DEEPSEEK_API_KEY",
    "DEEPSEEK_BASE_URL",
    "DEEPSEEK_MODEL",
    "DEEPSEEK_WIRE_API",
    "GLM_API_KEY",
    "GLM_BASE_URL",
    "GLM_MODEL",
    "GLM_WIRE_API",
    "ZHIPU_API_KEY",
    "ZHIPU_BASE_URL",
    "ZHIPU_MODEL",
    "OPENAI_REASONING_EFFORT",
    "MODEL_REASONING_EFFORT",
    "OPENAI_DISABLE_RESPONSE_STORAGE",
    "DISABLE_RESPONSE_STORAGE",
    "OPENAI_CONTEXT_WINDOW",
    "MODEL_CONTEXT_WINDOW",
    "OPENAI_AUTO_COMPACT_TOKEN_LIMIT",
    "MODEL_AUTO_COMPACT_TOKEN_LIMIT",
    "OPENAI_DISABLE_METADATA",
    "OPENAI_RESPONSES_DISABLE_METADATA",
    "BACKEND_RUNTIME_MODE",
    "IMAGE_AGENT_MODEL_TUNNEL_PORT",
]


@pytest.fixture(autouse=True)
def isolate_agent_model_env(monkeypatch):
    for key in MODEL_ENV_KEYS:
        monkeypatch.delenv(key, raising=False)


def _insert_project(database, project_id: int, name: str | None = None) -> None:
    with database.connect() as conn:
        conn.execute(
            "INSERT INTO projects(id, name, description, created_at) VALUES(?,?,?,?)",
            (project_id, name or f"P-{project_id}", "", database.now_iso()),
        )


def _ready_elasticsearch_hybrid_status(**overrides) -> dict:
    hybrid = {
        "engine": "elasticsearch",
        "configured": True,
        "persisted": True,
        "mode": "connected",
        "index": "image_agent_rag",
        "indexed_chunk_count": 260,
        "dense_vector_dims": 1536,
        "embedding_provider": "openai",
        "embedding_model": "text-embedding-3-small",
        "embedding_transport": "openai_compatible_http",
        "embedding_endpoint_configured": True,
        "embedding_production_ready": True,
        "lexical_retriever": "standard",
        "vector_retriever": "knn",
        "dense_vector_field": "embedding",
        "fusion": "rrf",
        "official_sources": [
            "https://www.elastic.co/docs/reference/elasticsearch/rest-apis/reciprocal-rank-fusion",
        ],
    }
    hybrid.update(overrides)
    return {
        "index": {
            "engine": "elasticsearch_hybrid",
            "hybrid_search": hybrid,
        }
    }


def test_agent_model_status_uses_model_gateway(monkeypatch):
    monkeypatch.setenv("IMAGE_AGENT_MODEL_PROVIDER", "OpenAI")
    monkeypatch.setenv("IMAGE_AGENT_MODEL_API_KEY", "secret-value")
    monkeypatch.setenv("IMAGE_AGENT_MODEL_BASE_URL", "http://127.0.0.1:18080")
    monkeypatch.setenv("IMAGE_AGENT_MODEL_NAME", "gpt-5.5")
    monkeypatch.setenv("IMAGE_AGENT_MODEL_REVIEW_NAME", "gpt-5.5")
    monkeypatch.setenv("IMAGE_AGENT_MODEL_WIRE_API", "responses")
    monkeypatch.setenv("OPENAI_API_KEY", "secret-value")
    monkeypatch.setenv("OPENAI_BASE_URL", "http://127.0.0.1:18080")
    monkeypatch.setenv("OPENAI_WIRE_API", "responses")
    monkeypatch.setenv("BACKEND_RUNTIME_MODE", "remote")
    monkeypatch.setenv("IMAGE_AGENT_MODEL_TUNNEL_PORT", "18080")
    from app.main import app

    result = TestClient(app).get("/agent/model/status")

    assert result.status_code == 200
    body = result.json()
    assert body["provider"] == "OpenAI"
    assert body["provider_profile"] == "openai"
    assert body["configured"] is True
    assert body["trust_env_proxy"] is False
    assert body["capabilities"] == {
        "text": True,
        "structured_json": True,
        "model_tool_loop": True,
    }
    assert body["deployment"] == {
        "backend_runtime_mode": "remote",
        "model_gateway_access": "ssh_reverse_tunnel",
    }
    assert body["gateway_diagnostics"] == {
        "sdk_method": "responses.create",
        "request_shape": "responses_input",
        "structured_output": "responses_text_format",
        "model_tool_loop": "enabled",
        "workflow_task_creation": "server_side_resume_confirmation_only",
    }
    assert "api_key" not in body
    assert "reverse_tunnel_command" not in json.dumps(body)
    assert "ssh -N -R" not in json.dumps(body)
    assert "secret-value" not in json.dumps(body)


def test_deployment_status_uses_safe_agent_model_summary(monkeypatch):
    monkeypatch.setenv("IMAGE_AGENT_MODEL_API_KEY", "secret-value")
    monkeypatch.setenv("IMAGE_AGENT_MODEL_BASE_URL", "http://127.0.0.1:18080")
    monkeypatch.setenv("IMAGE_AGENT_MODEL_PROVIDER", "openai")
    monkeypatch.setenv("BACKEND_RUNTIME_MODE", "remote")
    monkeypatch.setenv("IMAGE_AGENT_MODEL_TUNNEL_PORT", "18080")
    from app.main import app

    result = TestClient(app).get("/deployment")

    assert result.status_code == 200
    body = result.json()
    body_json = json.dumps(body)
    assert body["agent"]["deployment"] == {
        "backend_runtime_mode": "remote",
        "model_gateway_access": "ssh_reverse_tunnel",
    }
    assert body["execution_scope"] == {
        "development_origin": "workstation",
        "deployment_target": "api_server",
        "workflow_tool_execution": "deployment_server_local",
        "docker_runtime_host": "api_server",
        "external_worker_server_required": False,
    }
    assert "reverse_tunnel_command" not in body_json
    assert "ssh -N -R" not in body_json
    assert "secret-value" not in body_json


def test_deployment_status_reports_production_readiness_blockers(monkeypatch):
    monkeypatch.setenv("IMAGE_AGENT_ENV", "production")
    monkeypatch.setenv("IMAGE_AGENT_CORS_ORIGINS", "https://console.example.com")
    monkeypatch.setenv("IMAGE_AGENT_PUBLIC_BASE_URL", "https://api.example.com")
    monkeypatch.setenv("BACKEND_RUNTIME_MODE", "remote")
    for key in MODEL_ENV_KEYS:
        monkeypatch.delenv(key, raising=False)
    from app.services import agent_service
    from app.main import app

    monkeypatch.setattr(agent_service, "public_model_status", lambda: {"configured": False})

    result = TestClient(app).get("/deployment")

    assert result.status_code == 200
    body = result.json()
    assert body["production_readiness"] == {
        "required": True,
        "ready": False,
        "status": "blocked",
        "deployment_scope": "public_internet",
        "blocking_reasons": ["Agent model gateway is not configured."],
    }


def test_deployment_status_requires_public_api_base_for_production_readiness(monkeypatch):
    monkeypatch.setenv("IMAGE_AGENT_ENV", "production")
    monkeypatch.setenv("IMAGE_AGENT_CORS_ORIGINS", "https://console.example.com")
    monkeypatch.setenv("BACKEND_RUNTIME_MODE", "remote")
    monkeypatch.setenv("OPENAI_API_KEY", "secret-value")
    monkeypatch.delenv("IMAGE_AGENT_PUBLIC_BASE_URL", raising=False)
    from app.main import app

    result = TestClient(app).get("/deployment")

    assert result.status_code == 200
    readiness = result.json()["production_readiness"]
    assert readiness["required"] is True
    assert readiness["ready"] is False
    assert readiness["status"] == "blocked"
    assert "IMAGE_AGENT_PUBLIC_BASE_URL must be set for production deployment." in readiness["blocking_reasons"]


def test_deployment_status_requires_public_https_api_base_without_path(monkeypatch):
    monkeypatch.setenv("IMAGE_AGENT_ENV", "production")
    monkeypatch.setenv("IMAGE_AGENT_CORS_ORIGINS", "https://console.example.com")
    monkeypatch.setenv("BACKEND_RUNTIME_MODE", "remote")
    monkeypatch.setenv("OPENAI_API_KEY", "secret-value")
    from app.main import app

    invalid_bases = [
        "http://api.example.com",
        "https://localhost:8000",
        "https://127.0.0.1:8000",
        "https://0.0.0.0:8000",
        "https://[::1]:8000",
        "https://api.example.com/v1",
        "https://api.example.com?debug=true",
        "https://api.example.com#fragment",
    ]

    for base_url in invalid_bases:
        monkeypatch.setenv("IMAGE_AGENT_PUBLIC_BASE_URL", base_url)
        result = TestClient(app).get("/deployment")
        readiness = result.json()["production_readiness"]
        assert readiness["required"] is True
        assert readiness["ready"] is False
        assert readiness["status"] == "blocked"
        assert "IMAGE_AGENT_PUBLIC_BASE_URL must be a public HTTPS API origin without path, query, or fragment." in readiness["blocking_reasons"]


def test_deployment_status_rejects_private_or_bare_production_origins(monkeypatch):
    monkeypatch.setenv("IMAGE_AGENT_ENV", "production")
    monkeypatch.setenv("IMAGE_AGENT_CORS_ORIGINS", "https://console.example.com")
    monkeypatch.setenv("BACKEND_RUNTIME_MODE", "remote")
    monkeypatch.setenv("OPENAI_API_KEY", "secret-value")
    from app.main import app

    for public_base_url in (
        "https://10.2.32.14",
        "https://192.168.1.20",
        "https://172.16.0.8",
        "https://api",
    ):
        monkeypatch.setenv("IMAGE_AGENT_CORS_ORIGINS", "https://console.example.com")
        monkeypatch.setenv("IMAGE_AGENT_PUBLIC_BASE_URL", public_base_url)
        readiness = TestClient(app).get("/deployment").json()["production_readiness"]
        assert "IMAGE_AGENT_PUBLIC_BASE_URL must be a public HTTPS API origin without path, query, or fragment." in readiness["blocking_reasons"]

    for cors_origin in (
        "https://10.2.32.14",
        "https://192.168.1.20",
        "https://172.16.0.8",
        "https://console",
    ):
        monkeypatch.setenv("IMAGE_AGENT_CORS_ORIGINS", cors_origin)
        monkeypatch.setenv("IMAGE_AGENT_PUBLIC_BASE_URL", "https://api.example.com")
        readiness = TestClient(app).get("/deployment").json()["production_readiness"]
        assert "Production CORS origins must include a non-localhost console origin." in readiness["blocking_reasons"]


def test_deployment_status_allows_private_network_product_readiness(monkeypatch):
    monkeypatch.setenv("IMAGE_AGENT_ENV", "production")
    monkeypatch.setenv("IMAGE_AGENT_DEPLOYMENT_SCOPE", "private_network")
    monkeypatch.setenv("IMAGE_AGENT_CORS_ORIGINS", "http://127.0.0.1:5173")
    monkeypatch.setenv("IMAGE_AGENT_PUBLIC_BASE_URL", "http://127.0.0.1:8000")
    monkeypatch.setenv("BACKEND_RUNTIME_MODE", "remote")
    monkeypatch.setenv("OPENAI_API_KEY", "secret-value")
    monkeypatch.setenv("IMAGE_AGENT_MODEL_PROVIDER", "rawchat")
    monkeypatch.setenv("IMAGE_AGENT_MODEL_API_KEY", "secret-value")
    monkeypatch.setenv("IMAGE_AGENT_MODEL_BASE_URL", "https://rawchat.cn/codex")
    monkeypatch.setenv("IMAGE_AGENT_MODEL_NAME", "gpt-5.5")
    monkeypatch.setenv("IMAGE_AGENT_MODEL_WIRE_API", "responses")
    monkeypatch.setenv("IMAGE_AGENT_MODEL_TRUST_ENV_PROXY", "0")
    monkeypatch.setenv("IMAGE_AGENT_STRICT_REMOTE_ACCEPTANCE_STATUS", "passed")
    monkeypatch.setenv("IMAGE_AGENT_STRICT_REMOTE_ACCEPTANCE_ID", "yyf-private-acceptance-20260622")
    from app.services import agent_service
    from app.main import app

    monkeypatch.setattr(agent_service, "rag_status", lambda root: _ready_elasticsearch_hybrid_status())

    result = TestClient(app).get("/deployment")

    assert result.status_code == 200
    body = result.json()
    assert body["production_readiness"] == {
        "required": True,
        "ready": True,
        "status": "ready",
        "deployment_scope": "private_network",
        "blocking_reasons": [],
    }
    assert body["fast_launch_readiness"]["ready"] is True
    assert body["fast_launch_readiness"]["checks"]["production_deployment"]["deployment_scope"] == "private_network"


def test_deployment_fast_launch_readiness_requires_production_mode(monkeypatch):
    monkeypatch.delenv("IMAGE_AGENT_ENV", raising=False)
    monkeypatch.setenv("IMAGE_AGENT_MODEL_PROVIDER", "rawchat")
    monkeypatch.setenv("IMAGE_AGENT_MODEL_API_KEY", "secret-value")
    monkeypatch.setenv("IMAGE_AGENT_MODEL_BASE_URL", "https://rawchat.cn/codex")
    monkeypatch.setenv("IMAGE_AGENT_MODEL_NAME", "gpt-5.5")
    monkeypatch.setenv("IMAGE_AGENT_MODEL_WIRE_API", "responses")
    monkeypatch.setenv("IMAGE_AGENT_STRICT_REMOTE_ACCEPTANCE_STATUS", "passed")
    monkeypatch.setenv("IMAGE_AGENT_STRICT_REMOTE_ACCEPTANCE_ID", "remote-smoke-20260616T120000Z")
    from app.services import agent_service
    from app.main import app

    monkeypatch.setattr(agent_service, "rag_status", lambda root: _ready_elasticsearch_hybrid_status())

    result = TestClient(app).get("/deployment")

    assert result.status_code == 200
    readiness = result.json()["fast_launch_readiness"]
    assert readiness["ready"] is False
    assert readiness["status"] == "blocked"
    assert readiness["checks"]["production_deployment"] == {
        "status": "blocked",
        "deployment_scope": "public_internet",
        "required": False,
        "ready": True,
        "readiness_status": "ready",
        "blocking_reasons": [],
    }
    assert (
        "Production deployment readiness has not been enabled."
        in readiness["blocking_reasons"]
    )
    assert "secret-value" not in json.dumps(readiness)


def test_deployment_fast_launch_readiness_requires_deepseek_chat_completions_and_remote_evidence(monkeypatch):
    monkeypatch.setenv("IMAGE_AGENT_MODEL_PROVIDER", "deepseek")
    monkeypatch.setenv("IMAGE_AGENT_MODEL_API_KEY", "secret-value")
    monkeypatch.setenv("IMAGE_AGENT_MODEL_BASE_URL", "https://api.deepseek.com")
    monkeypatch.setenv("IMAGE_AGENT_MODEL_NAME", "deepseek-v4-pro")
    monkeypatch.setenv("IMAGE_AGENT_MODEL_WIRE_API", "chat_completions")
    monkeypatch.delenv("IMAGE_AGENT_STRICT_REMOTE_ACCEPTANCE_STATUS", raising=False)
    monkeypatch.delenv("IMAGE_AGENT_STRICT_REMOTE_ACCEPTANCE_ID", raising=False)
    from app.main import app

    result = TestClient(app).get("/deployment")

    assert result.status_code == 200
    readiness = result.json()["fast_launch_readiness"]
    assert readiness["ready"] is False
    assert readiness["status"] == "blocked"
    assert readiness["checks"]["model_gateway_target"] == {
        "status": "passed",
        "expected_provider_profile": "deepseek",
        "actual_provider_profile": "deepseek",
        "expected_wire_api": "chat_completions",
        "actual_wire_api": "chat_completions",
        "expected_model": "deepseek-v4-pro|deepseek-v4-flash",
        "actual_model": "deepseek-v4-pro",
        "expected_base_url": "https://api.deepseek.com",
        "actual_base_url": "https://api.deepseek.com",
        "expected_trust_env_proxy": False,
        "actual_trust_env_proxy": False,
        "expected_model_gateway_access": "direct",
        "actual_model_gateway_access": "direct",
        "model_tool_loop": False,
        "direct_transport": True,
    }
    assert readiness["checks"]["agent_task_boundary"]["status"] == "passed"
    assert readiness["checks"]["strict_remote_acceptance"]["status"] == "missing"
    assert (
        "Strict remote acceptance evidence has not been verified for the upload-agent-workflow-result chain."
        in readiness["blocking_reasons"]
    )
    body_json = json.dumps(readiness)
    assert "secret-value" not in body_json
    assert "api_key" not in body_json


@pytest.mark.parametrize(
    ("trust_env_proxy", "gateway_access"),
    [
        (False, "ssh_reverse_tunnel"),
        (True, "direct"),
    ],
)
def test_deployment_fast_launch_readiness_blocks_deepseek_without_direct_transport(
    monkeypatch,
    trust_env_proxy,
    gateway_access,
):
    monkeypatch.setenv("IMAGE_AGENT_ENV", "production")
    monkeypatch.setenv("IMAGE_AGENT_CORS_ORIGINS", "https://console.example.com")
    monkeypatch.setenv("IMAGE_AGENT_PUBLIC_BASE_URL", "https://api.example.com")
    monkeypatch.setenv("IMAGE_AGENT_STRICT_REMOTE_ACCEPTANCE_STATUS", "passed")
    monkeypatch.setenv("IMAGE_AGENT_STRICT_REMOTE_ACCEPTANCE_ID", "remote-smoke-20260616T120000Z")
    from app.services import agent_service
    from app.main import app

    monkeypatch.setattr(agent_service, "rag_status", lambda root: _ready_elasticsearch_hybrid_status())
    monkeypatch.setattr(
        agent_service,
        "public_model_status",
        lambda: {
            "configured": True,
            "provider_profile": "deepseek",
            "wire_api": "chat_completions",
            "model": "deepseek-v4-pro",
            "base_url": "https://api.deepseek.com",
            "trust_env_proxy": trust_env_proxy,
            "capabilities": {"model_tool_loop": False},
            "deployment": {"model_gateway_access": gateway_access},
        },
    )

    result = TestClient(app).get("/deployment")

    assert result.status_code == 200
    readiness = result.json()["fast_launch_readiness"]
    assert readiness["ready"] is False
    assert readiness["status"] == "blocked"
    assert readiness["checks"]["model_gateway_target"] == {
        "status": "blocked",
        "expected_provider_profile": "deepseek",
        "actual_provider_profile": "deepseek",
        "expected_wire_api": "chat_completions",
        "actual_wire_api": "chat_completions",
        "expected_model": "deepseek-v4-pro|deepseek-v4-flash",
        "actual_model": "deepseek-v4-pro",
        "expected_base_url": "https://api.deepseek.com",
        "actual_base_url": "https://api.deepseek.com",
        "expected_trust_env_proxy": False,
        "actual_trust_env_proxy": trust_env_proxy,
        "expected_model_gateway_access": "direct",
        "actual_model_gateway_access": gateway_access,
        "model_tool_loop": False,
        "direct_transport": False,
    }
    assert readiness["blocking_reasons"] == [
        "Model gateway is not pinned to direct DeepSeek chat-completions production transport."
    ]


def test_deployment_fast_launch_readiness_accepts_privacy_safe_remote_acceptance_id(monkeypatch):
    monkeypatch.setenv("IMAGE_AGENT_ENV", "production")
    monkeypatch.setenv("IMAGE_AGENT_CORS_ORIGINS", "https://console.example.com")
    monkeypatch.setenv("IMAGE_AGENT_PUBLIC_BASE_URL", "https://api.example.com")
    monkeypatch.setenv("IMAGE_AGENT_MODEL_PROVIDER", "deepseek")
    monkeypatch.setenv("IMAGE_AGENT_MODEL_API_KEY", "secret-value")
    monkeypatch.setenv("IMAGE_AGENT_MODEL_BASE_URL", "https://api.deepseek.com")
    monkeypatch.setenv("IMAGE_AGENT_MODEL_NAME", "deepseek-v4-pro")
    monkeypatch.setenv("IMAGE_AGENT_MODEL_WIRE_API", "chat_completions")
    monkeypatch.setenv("IMAGE_AGENT_STRICT_REMOTE_ACCEPTANCE_STATUS", "passed")
    monkeypatch.setenv("IMAGE_AGENT_STRICT_REMOTE_ACCEPTANCE_ID", "remote-smoke-20260616T120000Z")
    from app.services import agent_service
    from app.main import app

    monkeypatch.setattr(agent_service, "rag_status", lambda root: _ready_elasticsearch_hybrid_status())

    result = TestClient(app).get("/deployment")

    assert result.status_code == 200
    readiness = result.json()["fast_launch_readiness"]
    assert readiness["ready"] is True
    assert readiness["status"] == "ready"
    assert readiness["blocking_reasons"] == []
    assert readiness["checks"]["strict_remote_acceptance"] == {
        "status": "passed",
        "evidence_id": "remote-smoke-20260616T120000Z",
        "required_evidence": "strict remote smoke JSON verified within freshness window",
    }
    assert readiness["checks"]["rag_elasticsearch_hybrid"]["status"] == "passed"
    assert readiness["checks"]["rag_elasticsearch_hybrid"]["official_rrf_source_present"] is True
    readiness_json = json.dumps(readiness)
    assert "official_sources" not in readiness_json
    assert "reciprocal-rank-fusion" not in readiness_json


def test_deployment_fast_launch_readiness_requires_elasticsearch_hybrid_components(monkeypatch):
    monkeypatch.setenv("IMAGE_AGENT_MODEL_PROVIDER", "deepseek")
    monkeypatch.setenv("IMAGE_AGENT_MODEL_API_KEY", "secret-value")
    monkeypatch.setenv("IMAGE_AGENT_MODEL_BASE_URL", "https://api.deepseek.com")
    monkeypatch.setenv("IMAGE_AGENT_MODEL_NAME", "deepseek-v4-pro")
    monkeypatch.setenv("IMAGE_AGENT_MODEL_WIRE_API", "chat_completions")
    monkeypatch.setenv("IMAGE_AGENT_STRICT_REMOTE_ACCEPTANCE_STATUS", "passed")
    monkeypatch.setenv("IMAGE_AGENT_STRICT_REMOTE_ACCEPTANCE_ID", "remote-smoke-20260616T120000Z")
    from app.services import agent_service
    from app.main import app

    monkeypatch.setattr(
        agent_service,
        "rag_status",
        lambda root: _ready_elasticsearch_hybrid_status(
            lexical_retriever="bm25_only",
            vector_retriever="script_score",
            dense_vector_field="dense",
        ),
    )

    result = TestClient(app).get("/deployment")

    assert result.status_code == 200
    readiness = result.json()["fast_launch_readiness"]
    hybrid = readiness["checks"]["rag_elasticsearch_hybrid"]
    assert readiness["ready"] is False
    assert readiness["status"] == "blocked"
    assert hybrid["status"] == "blocked"
    assert hybrid["lexical_retriever"] == "bm25_only"
    assert hybrid["vector_retriever"] == "script_score"
    assert hybrid["dense_vector_field"] == "dense"
    assert hybrid["blocking_codes"] == [
        "rag_hybrid_lexical_retriever_not_standard",
        "rag_hybrid_vector_retriever_not_knn",
        "rag_hybrid_dense_vector_field_not_embedding",
    ]
    assert "Current deployment RAG is not ready Elasticsearch hybrid with production embeddings." in readiness[
        "blocking_reasons"
    ]
    assert "secret-value" not in json.dumps(readiness)


def test_deployment_fast_launch_readiness_requires_current_elasticsearch_hybrid(monkeypatch):
    monkeypatch.setenv("IMAGE_AGENT_MODEL_PROVIDER", "deepseek")
    monkeypatch.setenv("IMAGE_AGENT_MODEL_API_KEY", "secret-value")
    monkeypatch.setenv("IMAGE_AGENT_MODEL_BASE_URL", "https://api.deepseek.com")
    monkeypatch.setenv("IMAGE_AGENT_MODEL_NAME", "deepseek-v4-pro")
    monkeypatch.setenv("IMAGE_AGENT_MODEL_WIRE_API", "chat_completions")
    monkeypatch.setenv("IMAGE_AGENT_STRICT_REMOTE_ACCEPTANCE_STATUS", "passed")
    monkeypatch.setenv("IMAGE_AGENT_STRICT_REMOTE_ACCEPTANCE_ID", "remote-smoke-20260616T120000Z")
    from app.services import agent_service
    from app.main import app

    monkeypatch.setattr(
        agent_service,
        "rag_status",
        lambda root: {
            "index": {
                "engine": "elasticsearch_hybrid",
                "hybrid_search": {
                    "engine": "elasticsearch",
                    "configured": False,
                    "persisted": False,
                    "mode": "local_contract",
                    "index": "image_agent_rag",
                    "indexed_chunk_count": 0,
                    "dense_vector_dims": 64,
                    "embedding_provider": "local_hashing",
                    "embedding_model": "local-token-hash-v1",
                    "embedding_transport": None,
                    "embedding_endpoint_configured": False,
                    "embedding_production_ready": False,
                    "fusion": "rrf",
                },
            }
        },
    )

    result = TestClient(app).get("/deployment")

    assert result.status_code == 200
    readiness = result.json()["fast_launch_readiness"]
    assert readiness["ready"] is False
    assert readiness["status"] == "blocked"
    assert readiness["checks"]["rag_elasticsearch_hybrid"] == {
        "status": "blocked",
        "engine": "elasticsearch",
        "configured": False,
        "mode": "local_contract",
        "persisted": False,
        "index": "image_agent_rag",
        "indexed_chunk_count": 0,
        "dense_vector_dims": 64,
        "embedding_provider": "local_hashing",
        "embedding_model": "local-token-hash-v1",
        "embedding_transport": None,
        "embedding_endpoint_configured": False,
        "embedding_production_ready": False,
        "lexical_retriever": None,
        "vector_retriever": None,
        "dense_vector_field": None,
        "fusion": "rrf",
        "official_rrf_source_present": False,
        "blocking_codes": [
            "rag_hybrid_not_configured",
            "rag_hybrid_not_persisted",
            "rag_hybrid_mode_not_ready",
            "rag_indexed_chunk_count_missing",
            "rag_embedding_provider_local",
            "rag_embedding_transport_missing_or_unsupported",
            "rag_embedding_endpoint_not_configured",
            "rag_embedding_not_production_ready",
            "rag_hybrid_lexical_retriever_not_standard",
            "rag_hybrid_vector_retriever_not_knn",
            "rag_hybrid_dense_vector_field_not_embedding",
            "rag_hybrid_official_rrf_source_missing",
        ],
    }
    assert "Current deployment RAG is not ready Elasticsearch hybrid with production embeddings." in readiness[
        "blocking_reasons"
    ]
    assert "secret-value" not in json.dumps(readiness)


def test_deployment_fast_launch_readiness_requires_embedding_endpoint_configured(monkeypatch):
    monkeypatch.setenv("IMAGE_AGENT_MODEL_PROVIDER", "rawchat")
    monkeypatch.setenv("IMAGE_AGENT_MODEL_API_KEY", "secret-value")
    monkeypatch.setenv("IMAGE_AGENT_MODEL_BASE_URL", "https://rawchat.cn/codex")
    monkeypatch.setenv("IMAGE_AGENT_MODEL_NAME", "gpt-5.5")
    monkeypatch.setenv("IMAGE_AGENT_MODEL_WIRE_API", "responses")
    monkeypatch.setenv("IMAGE_AGENT_STRICT_REMOTE_ACCEPTANCE_STATUS", "passed")
    monkeypatch.setenv("IMAGE_AGENT_STRICT_REMOTE_ACCEPTANCE_ID", "remote-smoke-20260616T120000Z")
    from app.services import agent_service
    from app.main import app

    monkeypatch.setattr(
        agent_service,
        "rag_status",
        lambda root: _ready_elasticsearch_hybrid_status(embedding_endpoint_configured=False),
    )

    result = TestClient(app).get("/deployment")

    assert result.status_code == 200
    readiness = result.json()["fast_launch_readiness"]
    assert readiness["ready"] is False
    assert readiness["status"] == "blocked"
    assert readiness["checks"]["rag_elasticsearch_hybrid"]["status"] == "blocked"
    assert readiness["checks"]["rag_elasticsearch_hybrid"]["embedding_endpoint_configured"] is False
    assert readiness["checks"]["rag_elasticsearch_hybrid"]["blocking_codes"] == [
        "rag_embedding_endpoint_not_configured"
    ]
    assert "Current deployment RAG is not ready Elasticsearch hybrid with production embeddings." in readiness[
        "blocking_reasons"
    ]


def test_deployment_fast_launch_readiness_requires_official_elasticsearch_rrf_source(monkeypatch):
    monkeypatch.setenv("IMAGE_AGENT_MODEL_PROVIDER", "rawchat")
    monkeypatch.setenv("IMAGE_AGENT_MODEL_API_KEY", "secret-value")
    monkeypatch.setenv("IMAGE_AGENT_MODEL_BASE_URL", "https://rawchat.cn/codex")
    monkeypatch.setenv("IMAGE_AGENT_MODEL_NAME", "gpt-5.5")
    monkeypatch.setenv("IMAGE_AGENT_MODEL_WIRE_API", "responses")
    monkeypatch.setenv("IMAGE_AGENT_STRICT_REMOTE_ACCEPTANCE_STATUS", "passed")
    monkeypatch.setenv("IMAGE_AGENT_STRICT_REMOTE_ACCEPTANCE_ID", "remote-smoke-20260616T120000Z")
    from app.services import agent_service
    from app.main import app

    monkeypatch.setattr(
        agent_service,
        "rag_status",
        lambda root: _ready_elasticsearch_hybrid_status(official_sources=["https://docs.example.invalid/rrf"]),
    )

    result = TestClient(app).get("/deployment")

    assert result.status_code == 200
    readiness = result.json()["fast_launch_readiness"]
    assert readiness["ready"] is False
    assert readiness["status"] == "blocked"
    assert readiness["checks"]["rag_elasticsearch_hybrid"]["status"] == "blocked"
    assert readiness["checks"]["rag_elasticsearch_hybrid"]["official_rrf_source_present"] is False
    assert readiness["checks"]["rag_elasticsearch_hybrid"]["blocking_codes"] == [
        "rag_hybrid_official_rrf_source_missing"
    ]
    assert "Current deployment RAG is not ready Elasticsearch hybrid with production embeddings." in readiness[
        "blocking_reasons"
    ]
    readiness_json = json.dumps(readiness)
    assert "docs.example.invalid" not in readiness_json
    assert "reciprocal-rank-fusion" not in readiness_json


def test_agent_run_returns_answer_and_persists_privacy_safe_ledger(tmp_path, monkeypatch):
    from app.core import config
    from app.db import database
    from app import main
    from app.main import app

    monkeypatch.setattr(config, "DB_PATH", tmp_path / "app.db")
    monkeypatch.setattr(database, "DB_PATH", tmp_path / "app.db")
    database.init_db()
    _insert_project(database, 7)

    class FakeRunner:
        def run(self, *, message, project_context):
            return {
                "status": "answered",
                "answer": "hello",
                "context_project_id": project_context["project_id"],
                "intent": "answer_question",
                "selected_skill": "image-agent-operator",
                "retrieved_context": {
                    "mode": "local_persistent_index",
                    "results": [
                        {
                            "source": "docs/rag/contracts/result-summary.md",
                            "snippet": "raw snippets must stay out of the ledger",
                        }
                    ],
                },
            }

    monkeypatch.setattr(main, "AgentRunner", lambda: FakeRunner())
    monkeypatch.setattr(
        main,
        "read_project_context",
        lambda project_id, *, rows_fn, workflows: {"project_id": project_id, "workflows": workflows},
    )

    result = TestClient(app).post("/agent/runs", json={"project_id": 7, "message": "hi"})

    assert result.status_code == 200
    body = result.json()
    assert body["contract_version"] == "agent_run.v1"
    assert body["status"] == "answered"
    assert body["answer"] == "hello"
    assert body["agent_run_id"]

    with database.connect() as conn:
        row = conn.execute("SELECT * FROM agent_runs WHERE agent_run_id=?", (body["agent_run_id"],)).fetchone()
        event_types = [
            item["event_type"]
            for item in conn.execute(
                "SELECT event_type FROM agent_run_events WHERE agent_run_id=? ORDER BY id",
                (body["agent_run_id"],),
            ).fetchall()
        ]

    assert row["request_type"] == "run"
    assert row["project_id"] == 7
    assert row["status"] == "answered"
    assert row["intent"] == "answer_question"
    assert row["selected_skill"] == "image-agent-operator"
    assert row["model_gateway_access"] == "openai_sdk_gateway"
    assert row["message_sha256"] == hashlib.sha256("hi".encode("utf-8")).hexdigest()
    assert "message" not in row.keys()
    assert "hi" not in json.dumps(dict(row), ensure_ascii=False)
    assert event_types == ["agent_run_created", "agent_run_started", "agent_run_completed"]


def test_agent_run_unconfigured_model_answers_inventory_without_confirmation(tmp_path, monkeypatch):
    from app.core import config
    from app.db import database
    from app import main
    from app.main import app

    monkeypatch.setattr(config, "DB_PATH", tmp_path / "app.db")
    monkeypatch.setattr(database, "DB_PATH", tmp_path / "app.db")
    database.init_db()
    _insert_project(database, 7)
    monkeypatch.setattr(
        main,
        "read_project_context",
        lambda project_id, *, rows_fn, workflows: {
            "project_id": project_id,
            "project_files": [
                {"id": 31, "original_name": "sub-01_T1w.nii.gz", "file_type": "NIFTI"},
                {"id": 32, "original_name": "sub-01_T1w.json", "file_type": "JSON"},
            ],
            "series": [
                {
                    "id": 11,
                    "modality": "T1",
                    "sequence_label": "T1w_MPRAGE",
                    "supported_for_processing": 1,
                    "workflow_eligibility": {
                        "policy_version": "workflow_eligibility_v1",
                        "production_task_created": False,
                        "runnable_workflows": [
                            {
                                "workflow_type": "t1_deepprep_anat_report",
                                "label": "T1 DeepPrep anat-only with full features and HTML report",
                                "modality": "T1",
                                "workflow_metadata": {
                                    "lane": "fixed_workflow",
                                    "agent_selectable": True,
                                    "display_name": "T1 DeepPrep anatomical processing, QC, and report",
                                    "capability_summary": "Runs anatomical T1 processing with QC and report outputs.",
                                },
                            }
                        ],
                    },
                }
            ],
            "workflows": workflows,
        },
    )

    result = TestClient(app).post(
        "/agent/runs",
        json={"project_id": 7, "message": "我上传了什么文件，可以跑什么任务"},
    )

    assert result.status_code == 200
    body = result.json()
    assert body["status"] == "answered"
    assert body["intent"] == "inventory_capability"
    assert "confirmation" not in body
    assert body["production_task_created"] is False
    assert "sub-01_T1w.nii.gz" in body["answer"]
    assert "T1w_MPRAGE" in body["answer"]
    assert "t1_deepprep_anat_report" in body["answer"]
    assert "已上传" in body["answer"]
    assert "支持处理" in body["answer"]
    assert "T1 DeepPrep 解剖处理" in body["answer"]
    assert "Uploaded files" not in body["answer"]
    assert "Detected series" not in body["answer"]
    assert " / " not in body["answer"]
    assert "supported" not in body["answer"]


def test_agent_run_unconfigured_model_returns_complete_result_analysis(tmp_path, monkeypatch):
    from app.core import config
    from app.db import database
    from app import main
    from app.main import app

    monkeypatch.setattr(config, "DB_PATH", tmp_path / "app.db")
    monkeypatch.setattr(database, "DB_PATH", tmp_path / "app.db")
    database.init_db()
    _insert_project(database, 7)
    monkeypatch.setattr(
        main,
        "read_project_context",
        lambda project_id, *, rows_fn, workflows: {
            "project_id": project_id,
            "tasks": [
                {
                    "id": 140,
                    "project_id": project_id,
                    "series_id": 11,
                    "workflow_type": "t1_deepprep_anat_report",
                    "status": "completed",
                    "progress": 100,
                    "error_message": None,
                }
            ],
            "result_summaries": [
                {
                    "task_id": 140,
                    "workflow_type": "t1_deepprep_anat_report",
                    "outputs": {
                        "reports": [{"relative_path": "reports/index.html"}],
                        "qc": [{"relative_path": "QC/sub-01/figures/sub-01_desc-surfparc_T1w.svg"}],
                    },
                }
            ],
            "workflows": workflows,
        },
    )

    result = TestClient(app).post(
        "/agent/runs",
        json={"project_id": 7, "message": "请替我完整分析结果和QC报告"},
    )

    assert result.status_code == 200
    body = result.json()
    assert body["status"] == "answered"
    assert body["production_task_created"] is False
    assert "confirmation" not in body
    assert "Observation summary" in body["answer"]
    assert "task 140" in body["answer"]
    assert "Result artifacts" in body["answer"]
    assert "reports/index.html" in body["answer"]
    assert "QC observations" in body["answer"]
    assert "sub-01_desc-surfparc_T1w.svg" in body["answer"]
    assert "No workflow was launched" in body["answer"]


def test_agent_run_confirmation_does_not_create_task_before_resume(tmp_path, monkeypatch):
    from app.core import config
    from app.db import database
    from app import main
    from app.main import app

    monkeypatch.setattr(config, "DB_PATH", tmp_path / "app.db")
    monkeypatch.setattr(database, "DB_PATH", tmp_path / "app.db")
    database.init_db()
    _insert_project(database, 7)

    class FakeRunner:
        def run(self, *, message, project_context):
            return {
                "status": "confirmation_required",
                "answer": "Confirm before launching the workflow.",
                "intent": "run_workflow",
                "selected_skill": "image-agent-workflow-runner",
                "thread_id": "thread-confirm-1",
                "production_task_created": False,
                "confirmation": {
                    "type": "workflow_execution",
                    "project_id": 7,
                    "series_id": 11,
                    "workflow_type": "t1_deepprep_anat_report",
                    "runtime_workflow_type": "t1_deepprep",
                    "fingerprint": "a" * 64,
                    "workflow_metadata": {
                        "workflow_type": "t1_deepprep_anat_report",
                        "runtime_workflow_type": "t1_deepprep",
                        "display_name": "T1 DeepPrep anatomical processing, QC, and report",
                        "agent_selectable": True,
                        "is_report_only": False,
                    },
                    "action_lane": "fixed_workflow",
                    "preflight": {"ok": True, "runtime_workflow_type": "t1_deepprep"},
                },
            }

    monkeypatch.setattr(main, "AgentRunner", lambda: FakeRunner())
    monkeypatch.setattr(
        main,
        "read_project_context",
        lambda project_id, *, rows_fn, workflows: {"project_id": project_id, "workflows": workflows},
    )

    result = TestClient(app).post("/agent/runs", json={"project_id": 7, "message": "run T1 workflow"})

    assert result.status_code == 200
    body = result.json()
    assert body["contract_version"] == "agent_run.v1"
    assert body["status"] == "confirmation_required"
    assert body["production_task_created"] is False
    assert body["confirmation"]["workflow_type"] == "t1_deepprep_anat_report"
    assert body["confirmation"]["runtime_workflow_type"] == "t1_deepprep"
    assert body["confirmation"]["fingerprint"] == "a" * 64
    assert body["confirmation"]["workflow_metadata"]["workflow_type"] == "t1_deepprep_anat_report"
    assert body["confirmation"]["workflow_metadata"]["is_report_only"] is False
    assert body["confirmation"]["preflight"]["runtime_workflow_type"] == "t1_deepprep"

    with database.connect() as conn:
        task_count = conn.execute("SELECT COUNT(*) FROM tasks").fetchone()[0]
        row = conn.execute("SELECT * FROM agent_runs WHERE agent_run_id=?", (body["agent_run_id"],)).fetchone()

    assert task_count == 0
    assert row["request_type"] == "run"
    assert row["status"] == "confirmation_required"
    assert row["task_id"] is None


def test_agent_run_prepares_workflow_confirmation_without_model_when_user_says_do_not_launch(
    tmp_path,
    monkeypatch,
):
    from app.core import config
    from app.db import database
    from app import main
    from app.main import app

    monkeypatch.setattr(config, "DATA_ROOT", tmp_path)
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "app.db")
    monkeypatch.setattr(config, "PROJECTS_ROOT", tmp_path / "projects")
    monkeypatch.setattr(database, "DB_PATH", tmp_path / "app.db")
    monkeypatch.setattr(main, "PROJECTS_ROOT", tmp_path / "projects")
    monkeypatch.setenv("IMAGE_AGENT_THREAD_ROOT", str(tmp_path / "agent_threads"))
    database.init_db()
    with database.connect() as conn:
        conn.execute("INSERT INTO projects(id, name, description, created_at) VALUES(?,?,?,?)", (1, "P", "", database.now_iso()))
        conn.execute(
            "INSERT INTO files(id, project_id, original_name, storage_path, file_type, size, sha256, created_at) VALUES(?,?,?,?,?,?,?,?)",
            (1, 1, "sub-01_T1w.nii.gz", str(tmp_path / "sub-01_T1w.nii.gz"), "NIFTI", 1, "x", database.now_iso()),
        )
        conn.execute(
            "INSERT INTO imaging_series(id, project_id, file_id, sequence_label, supported_for_processing, unsupported_reason, modality, format, confidence, metadata_json, status, created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
            (11, 1, 1, "T1w_MPRAGE", 1, "", "T1", "NIFTI", 0.9, json.dumps({}), "detected", database.now_iso()),
        )

    result = TestClient(app).post(
        "/agent/runs",
        json={
            "project_id": 1,
            "message": "请为项目1的序列11准备 t1_deepprep_anat_report 工作流确认，不要创建或启动任务",
        },
    )

    assert result.status_code == 200
    body = result.json()
    assert body["status"] == "confirmation_required"
    assert body["intent"] == "run_workflow"
    assert body["selected_skill"] == "image-agent-workflow-runner"
    assert body["production_task_created"] is False
    assert body["confirmation"]["project_id"] == 1
    assert body["confirmation"]["series_id"] == 11
    assert body["confirmation"]["workflow_type"] == "t1_deepprep_anat_report"
    assert body["confirmation"]["runtime_workflow_type"] == "t1_deepprep"
    assert body["confirmation"]["action_lane"] == "fixed_workflow"
    assert body["confirmation"]["fingerprint"]
    assert body["confirmation"]["workflow_metadata"]["is_report_only"] is False
    assert body["confirmation"]["preflight"]["ok"] is True
    assert body["safe_metadata"].get("fallback_reason") != "model_gateway_unconfigured"

    with database.connect() as conn:
        task_count = conn.execute("SELECT COUNT(*) FROM tasks").fetchone()[0]
        confirmation_row = conn.execute(
            "SELECT * FROM agent_confirmations WHERE thread_id=?",
            (body["thread_id"],),
        ).fetchone()
        run_row = conn.execute("SELECT * FROM agent_runs WHERE agent_run_id=?", (body["agent_run_id"],)).fetchone()

    assert task_count == 0
    assert confirmation_row["status"] == "pending_confirmation"
    assert confirmation_row["workflow_type"] == "t1_deepprep_anat_report"
    assert run_row["status"] == "confirmation_required"
    assert run_row["task_id"] is None


def test_agent_run_forces_unknown_fixed_workflow_into_incubation_without_production_task(tmp_path, monkeypatch):
    from app.core import config
    from app.db import database
    from app.agent.incubation import IncubationLedger
    from app.agent.langgraph_runner import LangGraphAgentRunner
    from app import main
    from app.main import app
    from app.services import task_service

    monkeypatch.setattr(config, "DATA_ROOT", tmp_path)
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "app.db")
    monkeypatch.setattr(config, "PROJECTS_ROOT", tmp_path / "projects")
    monkeypatch.setattr(database, "DB_PATH", tmp_path / "app.db")
    monkeypatch.setattr(main, "PROJECTS_ROOT", tmp_path / "projects")
    monkeypatch.setenv("IMAGE_AGENT_AGENT_ENGINE", "langgraph")

    def fail_if_called(*args, **kwargs):
        raise AssertionError("production task service must not be called for unknown fixed workflow")

    monkeypatch.setattr(task_service, "create_series_task", fail_if_called)
    monkeypatch.setattr(main, "run_pipeline_task", fail_if_called)

    class FakeGateway:
        def complete_structured_with_tools(self, messages, *, purpose, tool_context, structured_schema=None, max_tool_rounds=2):
            return {
                "decision": {
                    "intent": "run_workflow",
                    "action_lane": "fixed_workflow",
                    "lane": "fixed_workflow",
                    "workflow_type": "dwi_magic_connectome_report",
                    "series_id": 11,
                    "summary": "Run an unknown fixed workflow",
                    "objective": "Evaluate unknown workflow routing",
                    "modality": "DWI",
                    "input_modality": "DWI",
                    "toolchain": ["sandbox", "proposal"],
                    "primitives": ["proposal"],
                    "script_paths": [],
                    "script_text": "echo propose unknown workflow",
                        "risks": ["workflow_type is not registered"],
                        "recommended_next_step": "Use incubation proposal",
                        "tool_chain_hint": "incubation",
                        "requires_confirmation": True,
                        "intent_category": "unknown_workflow",
                        "intent_subcategory": "dwi_connectome",
                        "confidence": 0.9,
                        "evidence_spans": ["run unknown fixed workflow"],
                        "risk_level": "medium",
                        "ambiguities": [],
                        "route_recommendation": "toolchain_incubation",
                    },
                "tool_trace": [{"stage": "planner", "mode": "openai_function_tools_dispatched"}],
                "tool_messages": [],
            }

        def complete_text(self, messages, *, purpose):
            return "answer"

    runner = LangGraphAgentRunner(
        gateway=FakeGateway(),
        incubation_ledger=IncubationLedger(tmp_path / "incubation_ledger"),
        rag_root=tmp_path,
    )
    monkeypatch.setattr(main, "AgentRunner", lambda: runner)
    monkeypatch.setattr(
        main,
        "read_project_context",
        lambda project_id, *, rows_fn, workflows: {
            "project_id": project_id,
            "series": [{"id": 11, "modality": "DWI", "supported_for_processing": 1}],
            "workflows": workflows,
        },
    )
    database.init_db()
    _insert_project(database, 7)

    result = TestClient(app).post("/agent/runs", json={"project_id": 7, "message": "run unknown fixed workflow"})

    assert result.status_code == 200
    body = result.json()
    assert body["contract_version"] == "agent_run.v1"
    assert body["status"] == "toolchain_proposed"
    assert body["action_lane"] == "toolchain_incubation"
    assert body["production_task_created"] is False
    assert body["task_creation_allowed"] is False
    assert body["forbidden_actions"] == ["confirmation_creation", "production_task_creation", "pipeline_runner_launch"]
    assert body["safe_metadata"]["lane"] == "toolchain_incubation"
    assert body["proposed_toolchain"]["task_creation_allowed"] is False
    assert body["proposed_toolchain"]["forbidden_actions"] == [
        "confirmation_creation",
        "production_task_creation",
        "pipeline_runner_launch",
    ]
    assert body["proposed_toolchain"]["production_task_created"] is False
    assert body["proposed_toolchain"]["promotion_gate"]["production_task_created"] is False
    assert body["proposed_toolchain"]["proposal_id"].startswith("inc_")

    with database.connect() as conn:
        task_count = conn.execute("SELECT COUNT(*) FROM tasks").fetchone()[0]
        row = conn.execute("SELECT * FROM agent_runs WHERE agent_run_id=?", (body["agent_run_id"],)).fetchone()

    assert task_count == 0
    assert row["request_type"] == "run"
    assert row["status"] == "toolchain_proposed"
    assert row["task_id"] is None


def test_agent_run_uses_langgraph_runner_by_default(tmp_path, monkeypatch):
    from app.core import config
    from app.db import database
    from app import main
    from app.main import app

    monkeypatch.setattr(config, "DB_PATH", tmp_path / "app.db")
    monkeypatch.setattr(database, "DB_PATH", tmp_path / "app.db")
    monkeypatch.delenv("IMAGE_AGENT_AGENT_ENGINE", raising=False)
    monkeypatch.setenv("IMAGE_AGENT_MODEL_API_KEY", "test-key")
    monkeypatch.setenv("IMAGE_AGENT_MODEL_PROVIDER", "rawchat")
    monkeypatch.setenv("IMAGE_AGENT_MODEL_WIRE_API", "responses")
    monkeypatch.setenv("IMAGE_AGENT_MODEL_NAME", "gpt-5.5")

    class FakeGateway:
        def complete_structured(self, messages, *, purpose, structured_schema=None):
            return {"intent": "answer_question", "summary": "Explain status"}

        def complete_text(self, messages, *, purpose):
            return "langgraph answer"

    monkeypatch.setattr(main, "ModelGateway", lambda: FakeGateway())
    monkeypatch.setattr(
        main,
        "read_project_context",
        lambda project_id, *, rows_fn, workflows: {"project_id": project_id, "tasks": [], "workflows": workflows},
    )
    database.init_db()
    _insert_project(database, 7)

    result = TestClient(app).post("/agent/runs", json={"project_id": 7, "message": "hi"})

    assert result.status_code == 200
    body = result.json()
    assert body["contract_version"] == "agent_run.v1"
    assert body["status"] == "answered"
    assert body["answer"] == "langgraph answer"
    assert body["response_source"] == "model_gateway"
    assert body["production_task_created"] is False
    assert body["safe_metadata"]["agent_engine"] == "langgraph"
    assert body["safe_metadata"]["lane"] == "read_only"


def test_agent_run_falls_back_to_read_only_backend_answer_when_model_unconfigured(tmp_path, monkeypatch):
    from app.core import config
    from app.db import database
    from app import main
    from app.main import app
    from app.services import agent_service

    monkeypatch.setattr(config, "DB_PATH", tmp_path / "app.db")
    monkeypatch.setattr(database, "DB_PATH", tmp_path / "app.db")
    monkeypatch.setattr(main, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(agent_service, "public_model_status", lambda: {"configured": False})
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    database.init_db()
    _insert_project(database, 7)
    with database.connect() as conn:
        conn.execute(
            "INSERT INTO files(id, project_id, original_name, storage_path, file_type, size, sha256, created_at) VALUES(?,?,?,?,?,?,?,?)",
            (3, 7, "sub-01_T1w.nii.gz", str(tmp_path / "sub-01_T1w.nii.gz"), "nifti", 12, "abc123", database.now_iso()),
        )
        conn.execute(
            "INSERT INTO imaging_series(id, project_id, file_id, sequence_label, supported_for_processing, unsupported_reason, modality, format, confidence, metadata_json, status, created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
            (5, 7, 3, "sub-01_T1w", 1, None, "T1", "NIFTI", 0.99, "{}", "ready", database.now_iso()),
        )
        conn.execute(
            "INSERT INTO tasks(id, project_id, series_id, workflow_type, status, progress, log_path, created_at) VALUES(?,?,?,?,?,?,?,?)",
            (41, 7, 5, "t1_deepprep", "running", 35, str(tmp_path / "task-41.log"), database.now_iso()),
        )

    result = TestClient(app).post("/agent/runs", json={"project_id": 7, "message": "show task status"})

    assert result.status_code == 200
    body = result.json()
    assert body["contract_version"] == "agent_run.v1"
    assert body["status"] == "answered"
    assert body["intent"] == "status"
    assert body["selected_skill"] == "backend-status-fallback"
    assert body["response_source"] == "rag_fallback"
    assert body["safe_metadata"]["fallback_reason"] == "model_gateway_unconfigured"
    assert "Model gateway is not configured" in body["answer"]
    assert "task 41" in body["answer"]
    assert body["tool_invocations"]
    with database.connect() as conn:
        row = conn.execute("SELECT * FROM agent_runs WHERE agent_run_id=?", (body["agent_run_id"],)).fetchone()
    assert row["status"] == "answered"
    assert row["selected_skill"] == "backend-status-fallback"
    assert "model_gateway_unconfigured" in row["safe_metadata_json"]


def test_agent_run_answers_chinese_current_data_overview_readably_without_model(tmp_path, monkeypatch):
    from app.core import config
    from app.db import database
    from app import main
    from app.main import app
    from app.services import agent_service

    monkeypatch.setattr(config, "DB_PATH", tmp_path / "app.db")
    monkeypatch.setattr(database, "DB_PATH", tmp_path / "app.db")
    monkeypatch.setattr(main, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(agent_service, "public_model_status", lambda: {"configured": False})
    database.init_db()
    _insert_project(database, 7)
    with database.connect() as conn:
        conn.execute(
            "INSERT INTO files(id, project_id, original_name, storage_path, file_type, size, sha256, created_at) VALUES(?,?,?,?,?,?,?,?)",
            (3, 7, "sub-01_T1w.nii.gz", str(tmp_path / "sub-01_T1w.nii.gz"), "NIFTI", 12, "abc123", database.now_iso()),
        )
        conn.execute(
            "INSERT INTO imaging_series(id, project_id, file_id, sequence_label, supported_for_processing, unsupported_reason, modality, format, confidence, metadata_json, status, created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
            (5, 7, 3, "T1w_MPRAGE", 1, None, "T1", "NIFTI", 0.99, "{}", "ready", database.now_iso()),
        )
        conn.execute(
            "INSERT INTO tasks(id, project_id, series_id, workflow_type, status, progress, log_path, created_at) VALUES(?,?,?,?,?,?,?,?)",
            (41, 7, 5, "t1_deepprep_anat_report", "running", 35, str(tmp_path / "task-41.log"), database.now_iso()),
        )

    result = TestClient(app).post("/agent/runs", json={"project_id": 7, "message": "替我分析一下现在的数据"})

    assert result.status_code == 200
    body = result.json()
    assert body["status"] == "answered"
    assert body["intent"] == "result_analysis"
    assert body["selected_skill"] == "backend-context-fallback"
    assert body["response_source"] == "backend_context"
    assert "项目状态概览" in body["answer"]
    assert "任务 #41" in body["answer"]
    assert "进度 35%" in body["answer"]
    assert "只读观察" in body["answer"]
    assert "Tasks:" not in body["answer"]
    assert "Recommended next step" not in body["answer"]
    assert "Observation summary" not in body["answer"]
    assert "Model gateway is not configured" not in body["answer"]


def test_agent_run_answers_identity_question_without_model_call(tmp_path, monkeypatch):
    from app.core import config
    from app.db import database
    from app import main
    from app.main import app

    monkeypatch.setattr(config, "DB_PATH", tmp_path / "app.db")
    monkeypatch.setattr(database, "DB_PATH", tmp_path / "app.db")
    monkeypatch.setenv("IMAGE_AGENT_MODEL_API_KEY", "test-key")
    monkeypatch.setenv("IMAGE_AGENT_MODEL_PROVIDER", "deepseek")
    monkeypatch.setenv("IMAGE_AGENT_MODEL_NAME", "deepseek-v4-pro")

    class ForbiddenGateway:
        def complete_structured(self, messages, *, purpose, structured_schema=None):
            raise AssertionError("identity questions must not call the model gateway")

        def complete_text(self, messages, *, purpose):
            raise AssertionError("identity questions must not call the model gateway")

    monkeypatch.setattr(main, "ModelGateway", lambda: ForbiddenGateway())
    database.init_db()
    _insert_project(database, 7)

    result = TestClient(app).post("/agent/runs", json={"project_id": 7, "message": "你是谁"})

    assert result.status_code == 200
    body = result.json()
    assert body["status"] == "answered"
    assert body["intent"] == "agent_identity"
    assert body["selected_skill"] == "runtime-source-reporter"
    assert body["response_source"] == "backend_context"
    assert "Brain Image Agent" in body["answer"]
    assert "项目数据库" in body["answer"]
    assert "诊断" in body["answer"]
    assert body["safe_metadata"]["runtime_reporter"] == "deterministic"


def test_agent_run_answers_runtime_source_question_without_model_call(tmp_path, monkeypatch):
    from app.core import config
    from app.db import database
    from app import main
    from app.main import app

    monkeypatch.setattr(config, "DB_PATH", tmp_path / "app.db")
    monkeypatch.setattr(database, "DB_PATH", tmp_path / "app.db")
    monkeypatch.setenv("IMAGE_AGENT_MODEL_API_KEY", "test-key")
    monkeypatch.setenv("IMAGE_AGENT_MODEL_PROVIDER", "deepseek")
    monkeypatch.setenv("IMAGE_AGENT_MODEL_NAME", "deepseek-v4-pro")

    class ForbiddenGateway:
        def complete_structured(self, messages, *, purpose, structured_schema=None):
            raise AssertionError("runtime source questions must not call the model gateway")

        def complete_text(self, messages, *, purpose):
            raise AssertionError("runtime source questions must not call the model gateway")

    monkeypatch.setattr(main, "ModelGateway", lambda: ForbiddenGateway())
    database.init_db()
    _insert_project(database, 7)

    result = TestClient(app).post(
        "/agent/runs",
        json={"project_id": 7, "message": "你现在是基于规则脚本回答，还是基于LLM在回答"},
    )

    assert result.status_code == 200
    body = result.json()
    assert body["status"] == "answered"
    assert body["intent"] == "runtime_source"
    assert body["selected_skill"] == "runtime-source-reporter"
    assert body["response_source"] == "backend_context"
    assert "这次回答来源：后端规则和运行状态检查" in body["answer"]
    assert "deepseek-v4-pro" in body["answer"]
    assert "不会让模型自称来源" in body["answer"]
    assert body["safe_metadata"]["runtime_reporter"] == "deterministic"


def test_agent_run_explains_t1_metrics_from_result_summary_without_model_call(tmp_path, monkeypatch):
    from app.core import config
    from app.db import database
    from app import main
    from app.main import app

    monkeypatch.setattr(config, "DB_PATH", tmp_path / "app.db")
    monkeypatch.setattr(database, "DB_PATH", tmp_path / "app.db")

    class ForbiddenGateway:
        def complete_structured(self, messages, *, purpose, structured_schema=None):
            raise AssertionError("T1 metric explanations must not call the model gateway")

        def complete_text(self, messages, *, purpose):
            raise AssertionError("T1 metric explanations must not call the model gateway")

    monkeypatch.setattr(main, "ModelGateway", lambda: ForbiddenGateway())
    database.init_db()
    _insert_project(database, 7)
    out_dir = tmp_path / "project-7" / "derivatives" / "140" / "output"
    summary_dir = out_dir / "summary"
    tables_dir = out_dir / "tables"
    summary_dir.mkdir(parents=True)
    tables_dir.mkdir()
    summary_path = summary_dir / "t1_result_summary.json"
    brain_table = tables_dir / "t1_brain_measures.tsv"
    brain_table.write_text("measure\tmetric\tdescription\tvalue\tunit\nBrainSegVol\tbrain_segmentation_volume\tBrain Segmentation Volume\t1199123.4\tmm^3\n", encoding="utf-8")
    summary_path.write_text(
        json.dumps(
            {
                "contract_version": "result_summary.v1",
                "task_id": 140,
                "workflow_type": "t1_deepprep_anat_report",
                "modality": "T1",
                "spaces": ["T1w", "MNI152"],
                "feature_groups": [
                    "segmentation_volumes",
                    "cortical_thickness",
                    "regional_morphometry",
                    "quality_control",
                ],
                "outputs": {
                    "tables": [
                        {
                            "name": "t1_brain_measures",
                            "relative_path": "tables/t1_brain_measures.tsv",
                            "download_url": "/tasks/140/artifacts/tables/t1_brain_measures.tsv",
                        },
                        {
                            "name": "t1_t1w_regions",
                            "relative_path": "tables/t1_t1w_regions.tsv",
                            "download_url": "/tasks/140/artifacts/tables/t1_t1w_regions.tsv",
                        },
                    ],
                    "qc": [
                        {
                            "name": "t1_qc_index",
                            "relative_path": "qc/t1_qc_index.json",
                            "download_url": "/tasks/140/artifacts/qc/t1_qc_index.json",
                        }
                    ],
                    "reports": [
                        {
                            "name": "scientific_report",
                            "relative_path": "reports/index.html",
                            "download_url": "/tasks/140/artifacts/reports/index.html",
                        }
                    ],
                },
                "provenance": {
                    "method": "deepprep_freesurfer_stats_parser",
                    "placeholder_outputs": False,
                    "extraction_status": "real_deepprep_freesurfer_stats",
                    "parsed_counts": {"brain_measures": 12, "regions": 68, "maps": 4, "transforms": 2},
                    "note": "Parsed real DeepPrep/Freesurfer stats.",
                },
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    with database.connect() as conn:
        conn.execute(
            "INSERT INTO files(id, project_id, original_name, storage_path, file_type, size, sha256, created_at) VALUES(?,?,?,?,?,?,?,?)",
            (3, 7, "sub-01_T1w.nii.gz", str(tmp_path / "sub-01_T1w.nii.gz"), "nifti", 12, "abc123", database.now_iso()),
        )
        conn.execute(
            "INSERT INTO imaging_series(id, project_id, file_id, sequence_label, supported_for_processing, unsupported_reason, modality, format, confidence, metadata_json, status, created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
            (5, 7, 3, "sub-01_T1w", 1, None, "T1", "NIFTI", 0.99, "{}", "ready", database.now_iso()),
        )
        conn.execute(
            "INSERT INTO tasks(id, project_id, series_id, workflow_type, status, progress, log_path, created_at, finished_at) VALUES(?,?,?,?,?,?,?,?,?)",
            (140, 7, 5, "t1_deepprep_anat_report", "completed", 100, str(tmp_path / "task-140.log"), database.now_iso(), database.now_iso()),
        )
        conn.execute(
            "INSERT INTO outputs(task_id, output_type, path, preview_path, metadata_json, created_at) VALUES(?,?,?,?,?,?)",
            (
                140,
                "json",
                str(summary_path),
                None,
                json.dumps({"kind": "result_summary", "modality": "T1"}),
                database.now_iso(),
            ),
        )

    result = TestClient(app).post(
        "/agent/runs",
        json={"project_id": 7, "message": "给我分析一下t1提取出来的指标，综合水平怎么样，符不符合正常水平"},
    )

    assert result.status_code == 200
    body = result.json()
    assert body["status"] == "answered"
    assert body["intent"] == "t1_metric_interpretation"
    assert body["selected_skill"] == "t1-metric-interpreter"
    assert body["response_source"] == "backend_context"
    assert "T1 结构化结果解读" in body["answer"]
    assert "任务 #140" in body["answer"]
    assert "脑分割体积" in body["answer"]
    assert "BrainSegVol" in body["answer"]
    assert "不能仅凭这些输出判断正常或异常" in body["answer"]
    assert "没有发现 BOLD 或 DWI" in body["answer"]
    assert body["safe_metadata"]["t1_metric_interpreter"] == "deterministic"


def test_agent_run_clarifies_bold_dwi_confusion_from_t1_only_records_without_model_call(tmp_path, monkeypatch):
    from app.core import config
    from app.db import database
    from app import main
    from app.main import app

    monkeypatch.setattr(config, "DB_PATH", tmp_path / "app.db")
    monkeypatch.setattr(database, "DB_PATH", tmp_path / "app.db")
    monkeypatch.setenv("IMAGE_AGENT_MODEL_API_KEY", "test-key")
    monkeypatch.setenv("IMAGE_AGENT_MODEL_PROVIDER", "deepseek")
    monkeypatch.setenv("IMAGE_AGENT_MODEL_NAME", "deepseek-v4-pro")

    class ForbiddenGateway:
        def complete_structured(self, messages, *, purpose, structured_schema=None):
            raise AssertionError("T1-only modality confusion must not call the model gateway")

        def complete_text(self, messages, *, purpose):
            raise AssertionError("T1-only modality confusion must not call the model gateway")

    monkeypatch.setattr(main, "ModelGateway", lambda: ForbiddenGateway())
    database.init_db()
    _insert_project(database, 7)
    with database.connect() as conn:
        conn.execute(
            "INSERT INTO files(id, project_id, original_name, storage_path, file_type, size, sha256, created_at) VALUES(?,?,?,?,?,?,?,?)",
            (3, 7, "sub-01_T1w.nii.gz", str(tmp_path / "sub-01_T1w.nii.gz"), "NIFTI", 12, "abc123", database.now_iso()),
        )
        conn.execute(
            "INSERT INTO imaging_series(id, project_id, file_id, sequence_label, supported_for_processing, unsupported_reason, modality, format, confidence, metadata_json, status, created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
            (5, 7, 3, "T1w_MPRAGE", 1, None, "T1", "NIFTI", 0.99, "{}", "ready", database.now_iso()),
        )
        conn.execute(
            "INSERT INTO tasks(id, project_id, series_id, workflow_type, status, progress, log_path, created_at) VALUES(?,?,?,?,?,?,?,?)",
            (140, 7, 5, "t1_deepprep_anat_report", "completed", 100, str(tmp_path / "task-140.log"), database.now_iso()),
        )
        conn.execute(
            "INSERT INTO outputs(task_id, output_type, path, preview_path, metadata_json, created_at) VALUES(?,?,?,?,?,?)",
            (
                140,
                "connectome",
                "Recon/fsaverage/label/lh.Yeo_Brainmap_10to14Comp_TopSpecializationComp.csv",
                None,
                json.dumps({"source": "deepprep_freesurfer_label", "modality": "T1"}),
                database.now_iso(),
            ),
        )

    result = TestClient(app).post(
        "/agent/runs",
        json={"project_id": 7, "message": "我都没上传bold资料和DTI资料，为什么会跑这些步骤"},
    )

    assert result.status_code == 200
    body = result.json()
    assert body["status"] == "answered"
    assert body["intent"] == "modality_boundary_clarification"
    assert body["selected_skill"] == "modality-boundary-clarifier"
    assert body["response_source"] == "backend_context"
    assert "没有运行 BOLD 或 DWI 工作流" in body["answer"]
    assert "当前只登记到 T1 序列" in body["answer"]
    assert "任务 #140" in body["answer"]
    assert "Yeo" in body["answer"]
    assert "FreeSurfer" in body["answer"]
    assert "不是基于 BOLD 计算的功能连接" in body["answer"]
    assert "不是 DTI" in body["answer"]
    assert "不会解释功能或弥散指标" in body["answer"]
    assert "BOLD/fMRI preprocessing is handled" not in body["answer"]
    assert body["safe_metadata"]["modality_boundary_clarifier"] == "deterministic"
    assert body["safe_metadata"]["production_task_created"] is False


def test_agent_run_response_redacts_nested_backend_paths(tmp_path, monkeypatch):
    from app.core import config
    from app.db import database
    from app import main
    from app.main import app

    monkeypatch.setattr(config, "DB_PATH", tmp_path / "app.db")
    monkeypatch.setattr(database, "DB_PATH", tmp_path / "app.db")
    database.init_db()
    _insert_project(database, 7)

    class FakeRunner:
        def run(self, *, message, project_context):
            return {
                "status": "task_created",
                "task": {
                    "id": 118,
                    "project_id": 7,
                    "series_id": 11,
                    "workflow_type": "bold_fmriprep_xcpd_report",
                    "status": "queued",
                    "error_message": "patient Jane Doe at C:/Users/A/private",
                    "log_path": "C:/Users/A/private/task.log",
                },
                "tool_input": {
                    "series_id": 11,
                    "workflow_type": "bold_fmriprep_xcpd_report",
                    "output_dir": "D:/project/private-output",
                },
            }

    monkeypatch.setattr(main, "AgentRunner", lambda: FakeRunner())
    monkeypatch.setattr(
        main,
        "read_project_context",
        lambda project_id, *, rows_fn, workflows: {"project_id": project_id, "workflows": workflows},
    )

    result = TestClient(app).post("/agent/runs", json={"project_id": 7, "message": "run BOLD"})

    assert result.status_code == 200
    body = result.json()
    body_json = json.dumps(body, ensure_ascii=False)
    assert body["status"] == "task_created"
    assert body["task"]["id"] == 118
    assert body["tool_input"] == {
        "series_id": 11,
        "workflow_type": "bold_fmriprep_xcpd_report",
    }
    assert "log_path" not in body["task"]
    assert "error_message" not in body["task"]
    assert "C:/Users/A/private" not in body_json
    assert "D:/project/private-output" not in body_json
    assert "patient Jane Doe" not in body_json


def test_agent_run_response_redacts_free_text_backend_paths(tmp_path, monkeypatch):
    from app.core import config
    from app.db import database
    from app import main
    from app.main import app

    monkeypatch.setattr(config, "DB_PATH", tmp_path / "app.db")
    monkeypatch.setattr(database, "DB_PATH", tmp_path / "app.db")
    database.init_db()
    _insert_project(database, 7)

    class FakeRunner:
        def run(self, *, message, project_context):
            return {
                "status": "answered",
                "answer": (
                    "Review output at data/projects/7/derivatives/118/output/qc_report.html "
                    "with key sk-test-secret and host path /home/yyf/project/image_agent/data/projects/7/raw/sub-01.nii.gz"
                ),
                "message": "See C:/Users/A/private/task.log",
                "events": [
                    {
                        "type": "agent.final",
                        "message": "Saved under data/projects/7/derivatives/118/output/",
                        "metadata": {
                            "log_path": "D:/project/private-output/task.log",
                            "safe_doc_path": "docs/rag/vendor/fsl.md",
                        },
                    }
                ],
            }

    monkeypatch.setattr(main, "AgentRunner", lambda: FakeRunner())
    monkeypatch.setattr(
        main,
        "read_project_context",
        lambda project_id, *, rows_fn, workflows: {"project_id": project_id, "workflows": workflows},
    )

    result = TestClient(app).post("/agent/runs", json={"project_id": 7, "message": "explain task"})

    assert result.status_code == 200
    body_json = json.dumps(result.json(), ensure_ascii=False)
    assert "[redacted-host-path]" in body_json
    assert "[redacted-secret]" in body_json
    assert "docs/rag/vendor/fsl.md" in body_json
    assert "data/projects/7" not in body_json
    assert "/home/yyf/project/image_agent" not in body_json
    assert "C:/Users/A/private" not in body_json
    assert "D:/project/private-output" not in body_json
    assert "sk-test-secret" not in body_json


def test_agent_api_openapi_declares_stable_response_contracts():
    from app.main import app

    schema = TestClient(app).get("/openapi.json").json()

    assert (
        schema["paths"]["/agent/runs"]["post"]["responses"]["200"]["content"]["application/json"]["schema"]["$ref"]
        == "#/components/schemas/AgentRunResponse"
    )
    assert (
        schema["paths"]["/agent/runs/{agent_run_id}"]["get"]["responses"]["200"]["content"]["application/json"]["schema"]["$ref"]
        == "#/components/schemas/AgentRunLookupResponse"
    )
    assert (
        schema["paths"]["/agent/runs/{thread_id}/resume"]["post"]["responses"]["200"]["content"]["application/json"]["schema"]["$ref"]
        == "#/components/schemas/AgentRunResponse"
    )
    for method, path, status_code in (
        ("post", "/agent/runs", "422"),
        ("post", "/agent/runs", "502"),
        ("get", "/agent/runs/{agent_run_id}", "404"),
        ("post", "/agent/runs/{thread_id}/resume", "502"),
    ):
        assert (
            schema["paths"][path][method]["responses"][status_code]["content"]["application/json"]["schema"]["$ref"]
            == "#/components/schemas/AgentApiErrorResponse"
        )
    assert (
        schema["paths"]["/projects/{project_id}/agent-runs"]["get"]["responses"]["200"]["content"]["application/json"]["schema"]["$ref"]
        == "#/components/schemas/ProjectAgentRunHistoryResponse"
    )
    assert "/chat" not in schema["paths"]
    for name in ("AgentRunRequest", "AgentResumeRequest"):
        assert schema["components"]["schemas"][name]["additionalProperties"] is False


def test_agent_run_rejects_unknown_request_fields_with_stable_error():
    from app.main import app

    result = TestClient(app).post(
        "/agent/runs",
        json={"project_id": None, "message": "hi", "adhoc_frontend_field": "drift"},
    )

    assert result.status_code == 422
    assert result.json() == {
        "detail": {
            "contract_version": "agent_api_error.v1",
            "code": "request_contract_violation",
            "message": "Request does not match the Agent API contract.",
        }
    }


def test_agent_resume_rejects_unknown_request_fields_with_stable_error():
    from app.main import app

    result = TestClient(app).post(
        "/agent/runs/thread-1/resume",
        json={
            "approved": True,
            "confirmation": {"type": "workflow_execution"},
            "adhoc_frontend_field": "drift",
        },
    )

    assert result.status_code == 422
    assert result.json() == {
        "detail": {
            "contract_version": "agent_api_error.v1",
            "code": "request_contract_violation",
            "message": "Request does not match the Agent API contract.",
        }
    }


def test_agent_resume_rejects_unknown_confirmation_fields_with_stable_error(tmp_path, monkeypatch):
    from app.core import config
    from app.db import database
    from app.main import app

    monkeypatch.setattr(config, "DB_PATH", tmp_path / "app.db")
    monkeypatch.setattr(database, "DB_PATH", tmp_path / "app.db")
    database.init_db()

    result = TestClient(app).post(
        "/agent/runs/thread-1/resume",
        json={
            "approved": True,
            "confirmation": {
                "type": "workflow_execution",
                "project_id": 1,
                "series_id": 11,
                "workflow_type": "t1_deepprep_anat_report",
                "absolute_path_hint": "C:/Users/A/private/patient-001",
            },
        },
    )

    assert result.status_code == 422
    assert result.json() == {
        "detail": {
            "contract_version": "agent_api_error.v1",
            "code": "request_contract_violation",
            "message": "Request does not match the Agent API contract.",
        }
    }


def test_agent_request_validation_handler_preserves_default_errors_for_other_routes():
    from app.main import app

    result = TestClient(app).post("/projects", json={"description": "missing name"})

    assert result.status_code == 422
    assert isinstance(result.json()["detail"], list)
    assert result.json()["detail"][0]["loc"][-1] == "name"


def test_agent_run_contract_normalizes_unknown_runner_status(tmp_path, monkeypatch):
    from app.core import config
    from app.db import database
    from app import main
    from app.main import app

    monkeypatch.setattr(config, "DB_PATH", tmp_path / "app.db")
    monkeypatch.setattr(database, "DB_PATH", tmp_path / "app.db")
    database.init_db()
    _insert_project(database, 7)

    class FakeRunner:
        def run(self, *, message, project_context):
            return {
                "status": "surprising_new_status",
                "answer": "hello",
                "intent": "answer_question",
                "selected_skill": "image-agent-operator",
            }

    monkeypatch.setattr(main, "AgentRunner", lambda: FakeRunner())
    monkeypatch.setattr(
        main,
        "read_project_context",
        lambda project_id, *, rows_fn, workflows: {"project_id": project_id, "workflows": workflows},
    )

    result = TestClient(app).post("/agent/runs", json={"project_id": 7, "message": "hi"})

    assert result.status_code == 200
    body = result.json()
    assert body["contract_version"] == "agent_run.v1"
    assert body["status"] == "failed"
    assert body["safe_metadata"]["contract_status_normalized_from"] == "surprising_new_status"

    with database.connect() as conn:
        row = conn.execute("SELECT * FROM agent_runs WHERE agent_run_id=?", (body["agent_run_id"],)).fetchone()
    assert row["status"] == "failed"


def test_agent_rag_rebuild_endpoint_builds_persistent_index(tmp_path, monkeypatch):
    from app import main
    from app.main import app

    rag_doc = tmp_path / "docs" / "rag" / "contracts" / "result-summary.md"
    rag_doc.parent.mkdir(parents=True)
    rag_doc.write_text("# Result Summary\nbackend result contract\n", encoding="utf-8")
    monkeypatch.setattr(main, "REPO_ROOT", tmp_path)

    result = TestClient(app).post("/agent/rag/rebuild")

    assert result.status_code == 200
    body = result.json()
    assert body["semantic_index"] is True
    assert body["document_count"] == 1
    assert (tmp_path / ".rag_index" / "chunks.jsonl").exists()


def test_agent_rag_status_rebuild_query_emit_matching_connected_elasticsearch_evidence(tmp_path, monkeypatch):
    from app import main
    from app.main import app

    class FakeElasticsearchIndices:
        def __init__(self, owner):
            self.owner = owner

        def exists(self, *, index):
            self.owner.exists_calls.append(index)
            return False

        def create(self, **kwargs):
            self.owner.create_calls.append(kwargs)

    class FakeElasticsearch:
        instances = []
        search_response = {"hits": {"hits": []}}

        def __init__(self, url, api_key=None):
            self.url = url
            self.api_key = api_key
            self.exists_calls = []
            self.create_calls = []
            self.bulk_calls = []
            self.search_calls = []
            self.indices = FakeElasticsearchIndices(self)
            FakeElasticsearch.instances.append(self)

        def bulk(self, **kwargs):
            self.bulk_calls.append(kwargs)
            return {"errors": False}

        def search(self, **kwargs):
            self.search_calls.append(kwargs)
            return FakeElasticsearch.search_response

    rag_doc = tmp_path / "docs" / "rag" / "contracts" / "elasticsearch-hybrid-search.md"
    rag_doc.parent.mkdir(parents=True)
    rag_doc.write_text(
        "---\nsource_type: rag_contract\n---\n"
        "# Elasticsearch Hybrid Search\n"
        "Official BM25 dense-vector kNN RRF retrieval evidence for Image Agent.\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(main, "REPO_ROOT", tmp_path)
    monkeypatch.setenv("IMAGE_AGENT_ELASTICSEARCH_URL", "https://elastic:super-secret-password@es.local:9200")
    monkeypatch.setenv("IMAGE_AGENT_ELASTICSEARCH_API_KEY", "sk-elasticsearch-secret-token")
    monkeypatch.setitem(sys.modules, "elasticsearch", types.SimpleNamespace(Elasticsearch=FakeElasticsearch))

    rebuild = TestClient(app).post("/agent/rag/rebuild")

    assert rebuild.status_code == 200
    hybrid = rebuild.json()["hybrid_search"]
    assert hybrid["configured"] is True
    assert hybrid["persisted"] is False
    assert hybrid["mode"] == "embedding_required"
    assert hybrid["indexed_chunk_count"] == 0
    assert hybrid["embedding_provider"] == "local_hashing"
    assert hybrid["embedding_production_ready"] is False
    assert FakeElasticsearch.instances == []
    serialized = json.dumps(rebuild.json(), sort_keys=True)
    assert "super-secret-password" not in serialized
    assert "sk-elasticsearch-secret-token" not in serialized

    class FakeEmbeddings:
        def create(self, *, model, input):
            text = str(input)
            vector = [0.9, 0.8, 0.7] if "RRF evidence" in text else [0.4, 0.5, 0.6]
            return types.SimpleNamespace(data=[types.SimpleNamespace(embedding=vector)])

    class FakeOpenAI:
        def __init__(self, *, api_key, base_url, timeout, **kwargs):
            self.embeddings = FakeEmbeddings()

    monkeypatch.setitem(sys.modules, "openai", types.SimpleNamespace(OpenAI=FakeOpenAI))
    monkeypatch.setenv("IMAGE_AGENT_RAG_EMBEDDING_PROVIDER", "openai")
    monkeypatch.setenv("IMAGE_AGENT_RAG_EMBEDDING_MODEL", "text-embedding-3-small")
    monkeypatch.setenv("IMAGE_AGENT_RAG_EMBEDDING_API_KEY", "embedding-secret")
    monkeypatch.setenv("IMAGE_AGENT_RAG_EMBEDDING_BASE_URL", "https://embedding.example/v1")

    rebuild = TestClient(app).post("/agent/rag/rebuild")

    assert rebuild.status_code == 200
    hybrid = rebuild.json()["hybrid_search"]
    assert hybrid["persisted"] is True
    assert hybrid["mode"] == "connected"
    assert hybrid["indexed_chunk_count"] == 1
    assert hybrid["embedding_provider"] == "openai"
    assert hybrid["embedding_model"] == "text-embedding-3-small"
    assert hybrid["embedding_transport"] == "sdk"
    assert hybrid["embedding_endpoint_configured"] is True
    assert hybrid["embedding_production_ready"] is True
    serialized = json.dumps(rebuild.json(), sort_keys=True)
    assert "super-secret-password" not in serialized
    assert "sk-elasticsearch-secret-token" not in serialized
    assert "embedding-secret" not in serialized
    assert "https://embedding.example/v1" not in serialized
    assert FakeElasticsearch.instances[0].url == "https://elastic:super-secret-password@es.local:9200"
    assert FakeElasticsearch.instances[0].api_key == "sk-elasticsearch-secret-token"
    assert FakeElasticsearch.instances[0].bulk_calls

    status = TestClient(app).get("/agent/rag/status")

    assert status.status_code == 200
    status_hybrid = status.json()["index"]["hybrid_search"]
    assert status_hybrid["persisted"] is True
    assert status_hybrid["mode"] == "connected"
    assert status_hybrid["index"] == hybrid["index"] == "image_agent_rag"
    assert status_hybrid["indexed_chunk_count"] == hybrid["indexed_chunk_count"] == 1
    assert status_hybrid["dense_vector_dims"] == hybrid["dense_vector_dims"] == 3
    assert status_hybrid["embedding_provider"] == hybrid["embedding_provider"] == "openai"
    assert status_hybrid["embedding_model"] == hybrid["embedding_model"] == "text-embedding-3-small"
    assert status_hybrid["embedding_transport"] == hybrid["embedding_transport"] == "sdk"
    assert status_hybrid["embedding_endpoint_configured"] is True
    assert status_hybrid["embedding_production_ready"] is True

    FakeElasticsearch.search_response = {
        "hits": {
            "hits": [
                {
                    "_score": 42.0,
                    "_source": {
                        "source": "docs/rag/contracts/elasticsearch-hybrid-search.md",
                        "title": "Elasticsearch Hybrid Search",
                        "text": "Official BM25 dense-vector kNN RRF retrieval evidence for Image Agent.",
                        "metadata": {"source_type": "rag_contract"},
                    },
                }
            ]
        }
    }

    query = TestClient(app).post(
        "/agent/rag/query",
        json={"query": "Elasticsearch hybrid RRF evidence"},
    )

    assert query.status_code == 200
    body = query.json()
    assert body["retrieval_mode"] == "elasticsearch_hybrid"
    assert body["retrieval_source"] == "elasticsearch_hybrid"
    assert body["citations"][0]["path"] == "docs/rag/contracts/elasticsearch-hybrid-search.md"
    assert body["citations"][0]["source"] == "docs/rag/contracts/elasticsearch-hybrid-search.md"
    search_client = FakeElasticsearch.instances[-1]
    assert search_client.search_calls[0]["index"] == "image_agent_rag"
    assert "rrf" in search_client.search_calls[0]["body"]["retriever"]


def test_agent_rag_status_reports_persistent_index(tmp_path, monkeypatch):
    from app import main
    from app.agent.rag_index import build_local_rag_index
    from app.main import app

    rag_doc = tmp_path / "docs" / "rag" / "contracts" / "result-summary.md"
    rag_doc.parent.mkdir(parents=True)
    rag_doc.write_text("# Result Summary\nbackend result contract\n", encoding="utf-8")
    build_local_rag_index(root=tmp_path, persist_dir=tmp_path / ".rag_index")
    monkeypatch.setattr(main, "REPO_ROOT", tmp_path)

    result = TestClient(app).get("/agent/rag/status")

    assert result.status_code == 200
    body = result.json()
    assert body["index"]["manifest_exists"] is True
    assert body["index"]["chunks_exists"] is True
    assert body["index"]["document_count"] == 1
    assert body["index"]["chunk_count"] >= 1
    assert body["index"]["missing_sources"] == []
    assert body["vendor_raw_sources"]["manifest_exists"] is False


def test_agent_rag_status_reports_vendor_raw_source_traceability(tmp_path, monkeypatch):
    from app import main
    from app.agent.rag_index import build_local_rag_index
    from app.main import app

    rag_doc = tmp_path / "docs" / "rag" / "vendor" / "fmriprep_official_container_usage.md"
    raw_root = tmp_path / "docs" / "rag" / "vendor" / "raw-sources"
    raw_doc = raw_root / "fmriprep_usage.html"
    workflow_doc = tmp_path / "docs" / "rag" / "workflows" / "t1_deepprep_anat_report.md"
    rag_doc.parent.mkdir(parents=True)
    raw_root.mkdir(parents=True)
    workflow_doc.parent.mkdir(parents=True)
    rag_doc.write_text(
        "---\n"
        "source_type: rag_vendor\n"
        "source_url: https://fmriprep.org/en/stable/usage.html\n"
        "raw_source_ids: fmriprep_usage\n"
        "---\n"
        "# fMRIPrep\n"
        "Curated summary only.\n",
        encoding="utf-8",
    )
    raw_doc.write_text("<html>official raw source</html>", encoding="utf-8")
    workflow_doc.write_text(
        "# Workflow\n"
        "Grounding: docs/rag/vendor/fmriprep_official_container_usage.md.\n",
        encoding="utf-8",
    )
    raw_bytes = raw_doc.read_bytes()
    (raw_root / "manifest.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "generated_at": "2026-06-06T00:00:00Z",
                "sources": [
                    {
                        "id": "fmriprep_usage",
                        "vendor_doc": rag_doc.name,
                        "url": "https://fmriprep.org/en/stable/usage.html",
                        "file": raw_doc.name,
                        "source_type": "official_docs",
                        "retrieved_at": "2026-06-06T00:00:00Z",
                        "sha256": hashlib.sha256(raw_bytes).hexdigest(),
                        "bytes": len(raw_bytes),
                        "status": "downloaded",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    build_local_rag_index(root=tmp_path, persist_dir=tmp_path / ".rag_index")
    monkeypatch.setattr(main, "REPO_ROOT", tmp_path)

    result = TestClient(app).get("/agent/rag/status")

    assert result.status_code == 200
    raw_status = result.json()["vendor_raw_sources"]
    assert raw_status["manifest_exists"] is True
    assert raw_status["source_count"] == 1
    assert raw_status["vendor_doc_count"] == 1
    assert raw_status["missing_files"] == []
    assert raw_status["hash_mismatches"] == []
    assert raw_status["raw_sources_indexed"] is False
    assert raw_status["curated_provenance_issues"] == []
    assert raw_status["curated_provenance_ok"] is True
    assert [
        {key: value for key, value in item.items() if key != "raw_snapshots"}
        for item in raw_status["curated_sources"]
    ] == [
        {
            "vendor_doc": "fmriprep_official_container_usage.md",
            "raw_source_ids": ["fmriprep_usage"],
            "source_urls": ["https://fmriprep.org/en/stable/usage.html"],
            "raw_files": ["docs/rag/vendor/raw-sources/fmriprep_usage.html"],
            "source_types": ["official_docs"],
            "manifest_backed": True,
            "source_url_backed": True,
            "complete": True,
        }
    ]
    assert raw_status["curated_sources"][0]["raw_snapshots"] == [
        {
            "id": "fmriprep_usage",
            "file": "docs/rag/vendor/raw-sources/fmriprep_usage.html",
            "url": "https://fmriprep.org/en/stable/usage.html",
            "sha256": hashlib.sha256(raw_bytes).hexdigest(),
            "bytes": len(raw_bytes),
            "retrieved_at": "2026-06-06T00:00:00Z",
            "source_type": "official_docs",
            "status": "downloaded",
        }
    ]
    pointer_status = result.json()["vendor_pointer_integrity"]
    assert pointer_status["ok"] is True
    assert pointer_status["issue_count"] == 0
    catalog = result.json()["vendor_coverage_catalog"]
    assert catalog["status"] == "complete"
    assert catalog["policy"] == "curated summaries are indexed; raw snapshots are provenance evidence only"
    assert catalog["vendor_doc_count"] == 1
    assert catalog["complete_vendor_doc_count"] == 1
    assert catalog["raw_source_count"] == 1
    assert catalog["pointer_integrity_ok"] is True
    assert catalog["vendors"][0]["vendor_doc"] == "fmriprep_official_container_usage.md"
    assert catalog["vendors"][0]["referenced_by"] == ["docs/rag/workflows/t1_deepprep_anat_report.md"]
    assert catalog["vendors"][0]["raw_source_ids"] == ["fmriprep_usage"]
    serialized_catalog = json.dumps(catalog)
    assert "official raw source" not in serialized_catalog
    assert "manifest_path" not in serialized_catalog
    assert "persist_dir" not in serialized_catalog
    assert str(tmp_path) not in serialized_catalog
    assert "raw_snapshots" not in serialized_catalog
    assert "sha256" not in serialized_catalog
    assert "docs/rag/vendor/raw-sources" not in serialized_catalog


def test_agent_run_requires_message():
    from app.main import app

    result = TestClient(app).post("/agent/runs", json={"project_id": None, "message": ""})

    assert result.status_code == 422
    assert result.json() == {
        "detail": {
            "contract_version": "agent_api_error.v1",
            "code": "message_required",
            "message": "message is required",
        }
    }


def test_agent_project_scoped_endpoints_reject_missing_project(tmp_path, monkeypatch):
    from app.core import config
    from app.db import database
    from app import main
    from app.main import app

    monkeypatch.setattr(config, "DB_PATH", tmp_path / "app.db")
    monkeypatch.setattr(database, "DB_PATH", tmp_path / "app.db")
    monkeypatch.setattr(main, "REPO_ROOT", tmp_path)
    database.init_db()

    run = TestClient(app).post("/agent/runs", json={"project_id": 999, "message": "summarize this project"})
    rag = TestClient(app).post("/agent/rag/query", json={"project_id": 999, "query": "what data is loaded?"})
    history = TestClient(app).get("/projects/999/agent-runs")

    assert run.status_code == 404
    assert rag.status_code == 404
    assert history.status_code == 404
    assert run.json()["detail"] == "Project not found"
    assert rag.json()["detail"] == "Project not found"
    assert history.json()["detail"] == "Project not found"


def test_agent_run_failure_ledger_redacts_sensitive_error_text(tmp_path, monkeypatch):
    from app.core import config
    from app.db import database
    from app import main
    from app.main import app

    monkeypatch.setattr(config, "DB_PATH", tmp_path / "app.db")
    monkeypatch.setattr(database, "DB_PATH", tmp_path / "app.db")
    database.init_db()
    _insert_project(database, 7)

    class FakeRunner:
        def run(self, *, message, project_context):
            raise RuntimeError("OPENAI_API_KEY=sk-test-secret failed at C:/Users/A/private/patient-001")

    monkeypatch.setattr(main, "AgentRunner", lambda: FakeRunner())
    monkeypatch.setattr(
        main,
        "read_project_context",
        lambda project_id, *, rows_fn, workflows: {"project_id": project_id, "workflows": workflows},
    )

    result = TestClient(app).post("/agent/runs", json={"project_id": 7, "message": "patient John Doe"})

    assert result.status_code == 502
    assert result.json()["detail"]["contract_version"] == "agent_api_error.v1"
    assert result.json()["detail"]["code"] == "agent_model_call_failed"
    assert result.json()["detail"]["message"] == "Agent model call failed."
    detail_json = json.dumps(result.json()["detail"], ensure_ascii=False)
    assert "agent_run_id" in result.json()["detail"]
    assert "sk-test-secret" not in detail_json
    assert "patient-001" not in detail_json
    assert "C:/Users/A/private" not in detail_json
    assert "patient John Doe" not in detail_json
    with database.connect() as conn:
        row = conn.execute("SELECT * FROM agent_runs ORDER BY created_at DESC LIMIT 1").fetchone()
        event_types = [
            item["event_type"]
            for item in conn.execute(
                "SELECT event_type FROM agent_run_events WHERE agent_run_id=? ORDER BY id",
                (row["agent_run_id"],),
            ).fetchall()
        ]

    row_json = json.dumps(dict(row), ensure_ascii=False)
    assert row["status"] == "failed"
    assert row["message_sha256"] == hashlib.sha256("patient John Doe".encode("utf-8")).hexdigest()
    assert "patient John Doe" not in row_json
    assert "sk-test-secret" not in row_json
    assert "patient-001" not in row_json
    assert "C:/Users/A/private" not in row_json
    assert event_types == ["agent_run_created", "agent_run_started", "agent_run_failed"]


def test_agent_run_lookup_returns_safe_ledger_trace(tmp_path, monkeypatch):
    from app.core import config
    from app.db import database
    from app import main
    from app.main import app

    monkeypatch.setattr(config, "DB_PATH", tmp_path / "app.db")
    monkeypatch.setattr(database, "DB_PATH", tmp_path / "app.db")
    database.init_db()
    _insert_project(database, 7)

    class FakeRunner:
        def run(self, *, message, project_context):
            return {
                "status": "answered",
                "answer": "hello",
                "intent": "answer_question",
                "selected_skill": "image-agent-operator",
                "recommended_next_step": "do not echo patient Jane Doe from C:/Users/A/private",
                "tool_chain_hint": "OPENAI_API_KEY=sk-test-secret should never be shown",
                "retrieved_context": {
                    "mode": "local_persistent_index",
                    "results": [
                        {
                            "source": "docs/rag/contracts/result-summary.md",
                            "title": "Result Summary",
                            "snippet": "raw RAG snippet must not be exposed",
                            "metadata": {"source_type": "rag_contract"},
                        },
                        {
                            "source": "C:/Users/A/private/patient-001/notes.md",
                            "title": "Sensitive Source",
                            "snippet": "absolute host path must not be exposed",
                        }
                    ],
                },
                "tool_trace": [
                    {
                        "stage": "planner",
                        "tool": "retrieve_reference_context",
                        "status": "ok",
                        "secret": "sk-test-secret",
                    }
                ],
            }

    monkeypatch.setattr(main, "AgentRunner", lambda: FakeRunner())
    monkeypatch.setattr(
        main,
        "read_project_context",
        lambda project_id, *, rows_fn, workflows: {"project_id": project_id, "workflows": workflows},
    )

    run_result = TestClient(app).post("/agent/runs", json={"project_id": 7, "message": "patient John Doe"})
    lookup = TestClient(app).get(f"/agent/runs/{run_result.json()['agent_run_id']}")

    assert lookup.status_code == 200
    body = lookup.json()
    assert body["contract_version"] == "agent_run_lookup.v1"
    assert body["agent_run_id"] == run_result.json()["agent_run_id"]
    assert body["status"] == "answered"
    assert body["request_type"] == "run"
    assert body["project_id"] == 7
    assert body["intent"] == "answer_question"
    assert body["selected_skill"] == "image-agent-operator"
    assert body["model_gateway_access"] == "openai_sdk_gateway"
    assert body["message_sha256"] == hashlib.sha256("patient John Doe".encode("utf-8")).hexdigest()
    assert body["retrieved_sources"] == [
        {
            "source": "docs/rag/contracts/result-summary.md",
            "source_type": "rag_contract",
        }
    ]
    assert body["safe_metadata"] == {
        "rag_mode": "local_persistent_index",
        "schema_version": 1,
        "trace_kind": "privacy-safe lifecycle traceability",
    }
    assert body["tool_invocations"] == [
        {"stage": "planner", "status": "ok", "tool": "retrieve_reference_context"}
    ]
    assert [event["event_type"] for event in body["events"]] == [
        "agent_run_created",
        "agent_run_started",
        "agent_run_completed",
    ]
    body_json = json.dumps(body, ensure_ascii=False)
    assert "patient John Doe" not in body_json
    assert "patient Jane Doe" not in body_json
    assert "raw RAG snippet must not be exposed" not in body_json
    assert "sk-test-secret" not in body_json
    assert "C:/Users/A/private" not in body_json


def test_agent_run_lookup_returns_404_for_unknown_run(tmp_path, monkeypatch):
    from app.core import config
    from app.db import database
    from app.main import app

    monkeypatch.setattr(config, "DB_PATH", tmp_path / "app.db")
    monkeypatch.setattr(database, "DB_PATH", tmp_path / "app.db")
    database.init_db()

    result = TestClient(app).get("/agent/runs/agent_run_missing")

    assert result.status_code == 404
    assert result.json() == {
        "detail": {
            "contract_version": "agent_api_error.v1",
            "code": "agent_run_not_found",
            "message": "Agent run not found",
        }
    }


def test_agent_run_lookup_redacts_free_text_error_message(tmp_path, monkeypatch):
    from app.core import config
    from app.db import database
    from app import main
    from app.main import app

    monkeypatch.setattr(config, "DB_PATH", tmp_path / "app.db")
    monkeypatch.setattr(database, "DB_PATH", tmp_path / "app.db")
    database.init_db()
    _insert_project(database, 7)

    class FakeRunner:
        def run(self, *, message, project_context):
            raise RuntimeError("patient John Doe failed validation in C:/Users/A/private")

    monkeypatch.setattr(main, "AgentRunner", lambda: FakeRunner())
    monkeypatch.setattr(
        main,
        "read_project_context",
        lambda project_id, *, rows_fn, workflows: {"project_id": project_id, "workflows": workflows},
    )

    failed = TestClient(app).post("/agent/runs", json={"project_id": 7, "message": "patient John Doe"})
    lookup = TestClient(app).get(f"/agent/runs/{failed.json()['detail']['agent_run_id']}")

    assert lookup.status_code == 200
    body_json = json.dumps(lookup.json(), ensure_ascii=False)
    assert "patient John Doe" not in body_json
    assert "C:/Users/A/private" not in body_json
    assert lookup.json()["error_message"] == "redacted_error_summary"


def test_agent_run_lookup_resanitizes_persisted_json_fields(tmp_path, monkeypatch):
    from app.core import config
    from app.db import database
    from app.main import app

    monkeypatch.setattr(config, "DB_PATH", tmp_path / "app.db")
    monkeypatch.setattr(database, "DB_PATH", tmp_path / "app.db")
    database.init_db()
    _insert_project(database, 7)
    now = database.now_iso()
    with database.connect() as conn:
        conn.execute(
            """
            INSERT INTO agent_runs(
              agent_run_id, request_type, thread_id, project_id, status, message_sha256,
              model_gateway_access, retrieved_sources_json, tool_invocations_json,
              safe_metadata_json, error_message, created_at, updated_at, finished_at
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                "agent_run_unsafe",
                "run",
                "thread-unsafe",
                7,
                "failed",
                "hash",
                "openai_sdk_gateway",
                json.dumps(
                    [
                        {
                            "source": "docs/rag/contracts/result-summary.md",
                            "title": "Patient Jane Doe notes",
                            "source_type": "rag_contract",
                            "snippet": "raw RAG snippet",
                        },
                        {
                            "source": "data/projects/7/raw/patient-John-Doe/notes.md",
                            "title": "Sensitive relative path",
                        },
                        {"source": "C:/Users/A/private/patient-001/notes.md"},
                    ]
                ),
                json.dumps(
                    [
                        {
                            "stage": "planner sk-test-secret",
                            "tool": "retrieve_reference_context",
                            "status": "ok",
                            "secret": "sk-test-secret",
                        },
                        {"stage": "resume", "tool": "read_task", "status": "ok sk-test-secret"},
                    ]
                ),
                json.dumps(
                    {
                        "schema_version": 1,
                        "trace_kind": "privacy-safe lifecycle traceability",
                        "rag_mode": "local_persistent_index",
                        "recommended_next_step": "patient Jane Doe from C:/Users/A/private",
                        "tool_chain_hint": "OPENAI_API_KEY=sk-test-secret",
                        "confirmation_fingerprint": "a" * 64,
                    }
                ),
                "patient Jane Doe in C:/Users/A/private",
                now,
                now,
                now,
            ),
        )
        conn.execute(
            """
            INSERT INTO agent_run_events(agent_run_id, event_type, status, metadata_json, created_at)
            VALUES(?,?,?,?,?)
            """,
            (
                "agent_run_unsafe",
                "agent_run_failed",
                "failed",
                json.dumps(
                    {
                        "thread_id": "thread-unsafe",
                        "workflow_type": "t1_deepprep",
                        "task_id": 12,
                        "secret": "sk-test-secret",
                        "path": "C:/Users/A/private",
                    }
                ),
                now,
            ),
        )

    result = TestClient(app).get("/agent/runs/agent_run_unsafe")

    assert result.status_code == 200
    body = result.json()
    body_json = json.dumps(body, ensure_ascii=False)
    assert "Patient Jane Doe" not in body_json
    assert "patient-John-Doe" not in body_json
    assert "raw RAG snippet" not in body_json
    assert "sk-test-secret" not in body_json
    assert "C:/Users/A/private" not in body_json
    assert body["retrieved_sources"] == [
        {"source": "docs/rag/contracts/result-summary.md", "source_type": "rag_contract"}
    ]
    assert body["safe_metadata"] == {
        "confirmation_fingerprint": "a" * 64,
        "rag_mode": "local_persistent_index",
        "schema_version": 1,
        "trace_kind": "privacy-safe lifecycle traceability",
    }
    assert body["tool_invocations"] == [
        {"status": "ok", "tool": "retrieve_reference_context"},
        {"stage": "resume", "tool": "read_task"},
    ]
    assert body["events"][0]["metadata"] == {
        "task_id": 12,
        "thread_id": "thread-unsafe",
        "workflow_type": "t1_deepprep",
    }
    assert body["error_message"] == "redacted_error_summary"


def test_project_agent_runs_list_resanitizes_persisted_json_fields(tmp_path, monkeypatch):
    from app.core import config
    from app.db import database
    from app.main import app

    monkeypatch.setattr(config, "DB_PATH", tmp_path / "app.db")
    monkeypatch.setattr(database, "DB_PATH", tmp_path / "app.db")
    database.init_db()
    _insert_project(database, 7)
    now = database.now_iso()
    with database.connect() as conn:
        conn.execute(
            """
            INSERT INTO agent_runs(
              agent_run_id, request_type, thread_id, project_id, status, message_sha256,
              model_gateway_access, retrieved_sources_json, tool_invocations_json,
              safe_metadata_json, error_message, created_at, updated_at, finished_at
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                "agent_run_list_unsafe",
                "run",
                "thread-list",
                7,
                "surprising_history_status",
                "hash",
                "openai_sdk_gateway",
                "[]",
                "[]",
                json.dumps(
                    {
                        "schema_version": 1,
                        "trace_kind": "privacy-safe lifecycle traceability",
                        "rag_mode": "local_persistent_index",
                        "recommended_next_step": "patient Jane Doe",
                    }
                ),
                "patient Jane Doe OPENAI_API_KEY=sk-test-secret",
                now,
                now,
                now,
            ),
        )

    result = TestClient(app).get("/projects/7/agent-runs")

    assert result.status_code == 200
    body = result.json()
    body_json = json.dumps(body, ensure_ascii=False)
    assert "patient Jane Doe" not in body_json
    assert "sk-test-secret" not in body_json
    assert "error_message" not in body_json
    assert body["agent_runs"][0]["status"] == "failed"
    assert body["agent_runs"][0]["safe_metadata"] == {
        "contract_status_normalized_from": "surprising_history_status",
        "rag_mode": "local_persistent_index",
        "schema_version": 1,
        "trace_kind": "privacy-safe lifecycle traceability",
    }


def test_project_agent_runs_lists_only_safe_project_history(tmp_path, monkeypatch):
    from app.core import config
    from app.db import database
    from app import main
    from app.main import app

    monkeypatch.setattr(config, "DB_PATH", tmp_path / "app.db")
    monkeypatch.setattr(database, "DB_PATH", tmp_path / "app.db")
    database.init_db()
    _insert_project(database, 7)
    _insert_project(database, 8)

    class FakeRunner:
        def run(self, *, message, project_context):
            return {
                "status": "answered",
                "answer": f"raw answer for {message}",
                "intent": "answer_question",
                "selected_skill": "image-agent-operator",
                "retrieved_context": {
                    "mode": "local_persistent_index",
                    "results": [
                        {
                            "source": "docs/rag/contracts/agent-run-ledger.md",
                            "title": "Agent Run Ledger",
                            "snippet": f"raw snippet for {message}",
                        }
                    ],
                },
            }

    monkeypatch.setattr(main, "AgentRunner", lambda: FakeRunner())
    monkeypatch.setattr(
        main,
        "read_project_context",
        lambda project_id, *, rows_fn, workflows: {"project_id": project_id, "workflows": workflows},
    )

    client = TestClient(app)
    first = client.post("/agent/runs", json={"project_id": 7, "message": "patient one"}).json()
    second = client.post("/agent/runs", json={"project_id": 7, "message": "patient two"}).json()
    other_project = client.post("/agent/runs", json={"project_id": 8, "message": "patient other"}).json()

    result = client.get("/projects/7/agent-runs")

    assert result.status_code == 200
    body = result.json()
    assert body["contract_version"] == "project_agent_run_history.v1"
    assert body["project_id"] == 7
    ids = {item["agent_run_id"] for item in body["agent_runs"]}
    assert ids == {first["agent_run_id"], second["agent_run_id"]}
    assert other_project["agent_run_id"] not in ids
    assert all(item["status"] == "answered" for item in body["agent_runs"])
    assert all(item["project_id"] == 7 for item in body["agent_runs"])
    assert all(item["model_gateway_access"] == "openai_sdk_gateway" for item in body["agent_runs"])
    assert all(item["event_count"] == 3 for item in body["agent_runs"])
    body_json = json.dumps(body, ensure_ascii=False)
    assert "error_message" not in body_json
    assert "patient one" not in body_json
    assert "patient two" not in body_json
    assert "patient other" not in body_json
    assert "raw answer" not in body_json
    assert "raw snippet" not in body_json


def test_project_agent_runs_empty_history_returns_empty_list(tmp_path, monkeypatch):
    from app.core import config
    from app.db import database
    from app.main import app

    monkeypatch.setattr(config, "DB_PATH", tmp_path / "app.db")
    monkeypatch.setattr(database, "DB_PATH", tmp_path / "app.db")
    database.init_db()
    _insert_project(database, 7)

    result = TestClient(app).get("/projects/7/agent-runs")

    assert result.status_code == 200
    assert result.json() == {
        "contract_version": "project_agent_run_history.v1",
        "project_id": 7,
        "agent_runs": [],
    }



def test_legacy_chat_endpoint_is_removed_from_runtime():
    from app.main import app

    result = TestClient(app).post("/chat", json={"project_id": 1, "message": "hello"})

    assert result.status_code == 404

def test_agent_rag_query_launchability_uses_matrix_citations(tmp_path, monkeypatch):
    from app import main
    from app.main import app

    matrix = tmp_path / "docs" / "rag" / "workflows" / "workflow_launchability_matrix.md"
    matrix.parent.mkdir(parents=True)
    matrix.write_text(
        "---\nsource_type: rag_workflow\nworkflow_type: workflow_launchability_matrix\n---\n"
        "# Workflow Launchability Matrix\n"
        "MRIQC is `incubation_reference`, DPABI is `unsupported_external`, and QSIPrep is legacy/explicit.\n"
        "Do not create production tasks from this matrix. `workflow_eligibility` remains authoritative for launchability.\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(main, "REPO_ROOT", tmp_path)

    result = TestClient(app).post(
        "/agent/rag/query",
        json={"query": "Can Image Agent run MRIQC DPABI QSIPrep in production?"},
    )

    assert result.status_code == 200
    body = result.json()
    assert body["intent"] == "launchability"
    assert body["citations"][0]["path"].endswith("workflow_launchability_matrix.md")
    assert "workflow_eligibility remains authoritative" in body["answer"]


def test_agent_rag_query_backend_context_includes_workflow_capability_metadata(tmp_path, monkeypatch):
    from app.core import config
    from app.db import database
    from app import main
    from app.main import app

    monkeypatch.setattr(config, "DATA_ROOT", tmp_path)
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "app.db")
    monkeypatch.setattr(config, "PROJECTS_ROOT", tmp_path / "projects")
    monkeypatch.setattr(database, "DB_PATH", tmp_path / "app.db")
    monkeypatch.setattr(main, "REPO_ROOT", tmp_path)

    database.init_db()
    client = TestClient(app)
    project = client.post("/projects", json={"name": "P-rag-workflows"}).json()
    result = client.post(
        "/agent/rag/query",
        json={"project_id": project["id"], "query": "What fixed workflows can Image Agent run?"},
    )

    assert result.status_code == 200
    workflows = result.json()["backend_context"]["supported_workflows"]
    t1 = next(item for item in workflows if item["workflow_type"] == "t1_deepprep_anat_report")
    assert t1["runtime_workflow_type"] == "t1_deepprep"
    assert t1["lane"] == "fixed_workflow"
    assert t1["requires_confirmation"] is True
    assert t1["display_name"] == "T1 DeepPrep anatomical processing, QC, and report"
    assert t1["capability_summary"]
    assert t1["pipeline_stages"]
    assert t1["primary_outputs"]
    assert t1["qc_outputs"]
    assert t1["report_outputs"]
    assert t1["limitations"]
    assert t1["is_report_only"] is False

    incubation = next(item for item in workflows if item["workflow_type"] == "toolchain_proposal")
    assert incubation["lane"] == "toolchain_incubation"
    assert incubation["runtime_workflow_type"] is None
    assert incubation["requires_confirmation"] is False


def test_agent_rag_query_returns_raw_source_evidence_for_vendor_citations(tmp_path, monkeypatch):
    from app import main
    from app.agent.rag_index import build_local_rag_index
    from app.main import app

    vendor_doc = tmp_path / "docs" / "rag" / "vendor" / "fmriprep_official_outputs.md"
    raw_root = vendor_doc.parent / "raw-sources"
    raw_doc = raw_root / "fmriprep_outputs.html"
    vendor_doc.parent.mkdir(parents=True)
    raw_root.mkdir()
    vendor_doc.write_text(
        "---\n"
        "source_type: rag_vendor\n"
        "source_url: https://fmriprep.org/en/stable/outputs.html\n"
        "raw_source_ids: fmriprep_outputs\n"
        "---\n"
        "# fMRIPrep Official Outputs\n"
        "fMRIPrep writes visual reports for quality review.\n",
        encoding="utf-8",
    )
    raw_doc.write_text("<html>official fMRIPrep outputs</html>", encoding="utf-8")
    raw_bytes = raw_doc.read_bytes()
    (raw_root / "manifest.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "generated_at": "2026-06-07T00:00:00Z",
                "sources": [
                    {
                        "id": "fmriprep_outputs",
                        "vendor_doc": vendor_doc.name,
                        "url": "https://fmriprep.org/en/stable/outputs.html",
                        "file": raw_doc.name,
                        "source_type": "official_docs",
                        "retrieved_at": "2026-06-07T00:00:00Z",
                        "sha256": hashlib.sha256(raw_bytes).hexdigest(),
                        "bytes": len(raw_bytes),
                        "status": "downloaded",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    build_local_rag_index(root=tmp_path, persist_dir=tmp_path / ".rag_index")
    monkeypatch.setattr(main, "REPO_ROOT", tmp_path)

    result = TestClient(app).post(
        "/agent/rag/query",
        json={"query": "fMRIPrep visual reports"},
    )

    assert result.status_code == 200
    evidence = result.json()["raw_source_evidence"]
    assert evidence["policy"] == "raw snapshots are traceability evidence and are not indexed wholesale"
    assert evidence["sources"][0]["curated_source"] == "docs/rag/vendor/fmriprep_official_outputs.md"
    assert evidence["sources"][0]["raw_source_ids"] == ["fmriprep_outputs"]
    assert evidence["sources"][0]["raw_snapshots"][0]["sha256"] == hashlib.sha256(raw_bytes).hexdigest()
    assert evidence["raw_sources_indexed"] is False



def test_agent_resume_returns_ready_to_launch(tmp_path, monkeypatch):
    from app.core import config
    from app.db import database
    from app import main
    from app.main import app

    monkeypatch.setattr(config, "DB_PATH", tmp_path / "app.db")
    monkeypatch.setattr(database, "DB_PATH", tmp_path / "app.db")
    database.init_db()

    class FakeRunner:
        def resume(self, *, thread_id, approved, confirmation, create_task_fn=None):
            return {
                "status": "ready_to_launch",
                "thread_id": thread_id,
                "backend_tool": "create_workflow_task",
                "tool_input": {
                    "project_id": confirmation["project_id"],
                    "series_id": confirmation["series_id"],
                    "workflow_type": confirmation["workflow_type"],
                },
            }

    monkeypatch.setattr(main, "AgentRunner", lambda: FakeRunner())

    result = TestClient(app).post(
        "/agent/runs/thread-1/resume",
        json={
            "approved": True,
            "confirmation": {
                "type": "workflow_execution",
                "project_id": 1,
                "series_id": 11,
                "workflow_type": "t1_deepprep",
            },
        },
    )

    assert result.status_code == 200
    assert result.json()["contract_version"] == "agent_run.v1"
    assert result.json()["status"] == "ready_to_launch"
    assert result.json()["tool_input"]["workflow_type"] == "t1_deepprep"


def test_agent_resume_contract_normalizes_unknown_runner_status(tmp_path, monkeypatch):
    from app.core import config
    from app.db import database
    from app import main
    from app.main import app

    monkeypatch.setattr(config, "DB_PATH", tmp_path / "app.db")
    monkeypatch.setattr(database, "DB_PATH", tmp_path / "app.db")
    database.init_db()

    class FakeRunner:
        def resume(self, *, thread_id, approved, confirmation, create_task_fn=None):
            return {
                "status": "surprising_resume_status",
                "thread_id": thread_id,
                "message": "resume status drift",
            }

    monkeypatch.setattr(main, "AgentRunner", lambda: FakeRunner())

    result = TestClient(app).post(
        "/agent/runs/thread-unknown-status/resume",
        json={
            "approved": True,
            "confirmation": {
                "type": "workflow_execution",
                "project_id": 1,
                "series_id": 11,
                "workflow_type": "t1_deepprep",
            },
        },
    )

    assert result.status_code == 200
    body = result.json()
    assert body["contract_version"] == "agent_run.v1"
    assert body["status"] == "failed"
    assert body["safe_metadata"]["contract_status_normalized_from"] == "surprising_resume_status"

    with database.connect() as conn:
        row = conn.execute("SELECT * FROM agent_runs WHERE agent_run_id=?", (body["agent_run_id"],)).fetchone()
    assert row["request_type"] == "resume"
    assert row["status"] == "failed"


def test_agent_resume_failure_returns_stable_error_contract(tmp_path, monkeypatch):
    from app.core import config
    from app.db import database
    from app import main
    from app.main import app

    monkeypatch.setattr(config, "DB_PATH", tmp_path / "app.db")
    monkeypatch.setattr(database, "DB_PATH", tmp_path / "app.db")
    database.init_db()

    class FakeRunner:
        def resume(self, *, thread_id, approved, confirmation, create_task_fn=None):
            raise RuntimeError("OPENAI_API_KEY=sk-test-secret failed at C:/Users/A/private/patient-001")

    monkeypatch.setattr(main, "AgentRunner", lambda: FakeRunner())

    result = TestClient(app).post(
        "/agent/runs/thread-failure/resume",
        json={
            "approved": True,
            "confirmation": {
                "type": "workflow_execution",
                "project_id": 1,
                "series_id": 11,
                "workflow_type": "t1_deepprep",
            },
        },
    )

    assert result.status_code == 502
    detail = result.json()["detail"]
    assert detail["contract_version"] == "agent_api_error.v1"
    assert detail["code"] == "agent_resume_failed"
    assert detail["message"] == "Agent resume failed."
    assert detail["agent_run_id"]
    detail_json = json.dumps(detail, ensure_ascii=False)
    assert "sk-test-secret" not in detail_json
    assert "patient-001" not in detail_json
    assert "C:/Users/A/private" not in detail_json

    with database.connect() as conn:
        row = conn.execute("SELECT * FROM agent_runs WHERE agent_run_id=?", (detail["agent_run_id"],)).fetchone()
    assert row["request_type"] == "resume"
    assert row["status"] == "failed"
    assert row["error_message"] == "redacted_error_summary"


def test_agent_resume_approved_confirmation_creates_real_task(tmp_path, monkeypatch):
    from app.core import config
    from app.db import database
    from app.agent.thread_store import AgentThreadStore
    from app import main
    from app.main import app

    monkeypatch.setattr(config, "DATA_ROOT", tmp_path)
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "app.db")
    monkeypatch.setattr(config, "PROJECTS_ROOT", tmp_path / "projects")
    monkeypatch.setattr(database, "DB_PATH", tmp_path / "app.db")
    monkeypatch.setattr(main, "PROJECTS_ROOT", tmp_path / "projects")
    monkeypatch.setattr(main, "run_pipeline_task", lambda task_id, qsiprep_task_id=None: None)
    store = AgentThreadStore(tmp_path / "agent_threads")
    original_runner = main.AgentRunner
    monkeypatch.setattr(main, "AgentRunner", lambda: original_runner(thread_store=store))

    database.init_db()
    with database.connect() as conn:
        conn.execute("INSERT INTO projects(id, name, description, created_at) VALUES(?,?,?,?)", (1, "P", "", database.now_iso()))
        conn.execute(
            "INSERT INTO files(id, project_id, original_name, storage_path, file_type, size, sha256, created_at) VALUES(?,?,?,?,?,?,?,?)",
            (1, 1, "t1.nii.gz", str(tmp_path / "t1.nii.gz"), "NIFTI", 1, "x", database.now_iso()),
        )
        conn.execute(
            "INSERT INTO imaging_series(id, project_id, file_id, sequence_label, supported_for_processing, unsupported_reason, modality, format, confidence, metadata_json, status, created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
            (11, 1, 1, "T1_MPRAGE", 1, "", "T1", "NIFTI", 0.9, json.dumps({}), "detected", database.now_iso()),
        )

    confirmation = {
        "type": "workflow_execution",
        "project_id": 1,
        "series_id": 11,
        "workflow_type": "t1_deepprep_anat_report",
        "runtime_workflow_type": "t1_deepprep",
        "action_lane": "fixed_workflow",
        "preflight": {
            "ok": True,
            "workflow_type": "t1_deepprep_anat_report",
            "runtime_workflow_type": "t1_deepprep",
        },
        "workflow_metadata": {
            "workflow_type": "t1_deepprep_anat_report",
            "display_name": "T1 DeepPrep anatomical processing, QC, and report",
            "workflow_family": "t1",
            "workflow_role": "anat_processing",
            "is_report_only": False,
        },
    }
    thread = store.create_pending_confirmation(
        confirmation=confirmation,
        decision={"intent": "run_workflow"},
        selected_skill="image-agent-workflow-runner",
        retrieved_context={},
    )
    public_confirmation = {
        **confirmation,
        "runtime_workflow_type": "t1_deepprep",
        "fingerprint": thread["confirmation_fingerprint"],
    }

    result = TestClient(app).post(
        f"/agent/runs/{thread['thread_id']}/resume",
        json={"approved": True, "confirmation": public_confirmation},
    )

    assert result.status_code == 200
    body = result.json()
    assert body["status"] == "task_created"
    assert body["task"]["workflow_type"] == "t1_deepprep_anat_report"
    assert body["task"]["runtime_workflow_type"] == "t1_deepprep"
    assert body["task"]["status"] == "queued"
    assert body["agent_run_id"]

    with database.connect() as conn:
        row = conn.execute("SELECT * FROM agent_runs WHERE agent_run_id=?", (body["agent_run_id"],)).fetchone()
        event_types = [
            item["event_type"]
            for item in conn.execute(
                "SELECT event_type FROM agent_run_events WHERE agent_run_id=? ORDER BY id",
                (body["agent_run_id"],),
            ).fetchall()
        ]

    assert row["request_type"] == "resume"
    assert row["thread_id"] == thread["thread_id"]
    assert row["status"] == "task_created"
    assert row["project_id"] == 1
    assert row["series_id"] == 11
    assert row["workflow_type"] == "t1_deepprep_anat_report"
    assert row["task_id"] == body["task"]["id"]
    assert row["approved"] == 1
    assert event_types == ["agent_run_created", "agent_run_started", "agent_run_completed"]


def test_agent_resume_preserves_canonical_workflow_type_and_records_runtime_alias(tmp_path, monkeypatch):
    from app.core import config
    from app.db import database
    from app.agent.thread_store import AgentThreadStore
    from app import main
    from app.main import app

    monkeypatch.setattr(config, "DATA_ROOT", tmp_path)
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "app.db")
    monkeypatch.setattr(config, "PROJECTS_ROOT", tmp_path / "projects")
    monkeypatch.setattr(database, "DB_PATH", tmp_path / "app.db")
    monkeypatch.setattr(main, "PROJECTS_ROOT", tmp_path / "projects")
    monkeypatch.setattr(main, "run_pipeline_task", lambda task_id, qsiprep_task_id=None: None)
    store = AgentThreadStore(tmp_path / "agent_threads")
    original_runner = main.AgentRunner
    monkeypatch.setattr(main, "AgentRunner", lambda: original_runner(thread_store=store))

    database.init_db()
    with database.connect() as conn:
        conn.execute("INSERT INTO projects(id, name, description, created_at) VALUES(?,?,?,?)", (1, "P", "", database.now_iso()))
        conn.execute(
            "INSERT INTO files(id, project_id, original_name, storage_path, file_type, size, sha256, created_at) VALUES(?,?,?,?,?,?,?,?)",
            (1, 1, "t1.nii.gz", str(tmp_path / "t1.nii.gz"), "NIFTI", 1, "x", database.now_iso()),
        )
        conn.execute(
            "INSERT INTO imaging_series(id, project_id, file_id, sequence_label, supported_for_processing, unsupported_reason, modality, format, confidence, metadata_json, status, created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
            (11, 1, 1, "T1_MPRAGE", 1, "", "T1", "NIFTI", 0.9, json.dumps({}), "detected", database.now_iso()),
        )

    confirmation = {
        "type": "workflow_execution",
        "project_id": 1,
        "series_id": 11,
        "workflow_type": "t1_deepprep_anat_report",
        "runtime_workflow_type": "t1_deepprep",
        "action_lane": "fixed_workflow",
        "preflight": {
            "ok": True,
            "workflow_type": "t1_deepprep_anat_report",
            "runtime_workflow_type": "t1_deepprep",
        },
        "data_candidate_selection": None,
    }
    thread = store.create_pending_confirmation(
        confirmation=confirmation,
        decision={"intent": "run_workflow"},
        selected_skill="image-agent-workflow-runner",
        retrieved_context={},
    )
    public_confirmation = {
        **confirmation,
        "runtime_workflow_type": "t1_deepprep",
        "fingerprint": thread["confirmation_fingerprint"],
    }

    result = TestClient(app).post(
        f"/agent/runs/{thread['thread_id']}/resume",
        json={"approved": True, "confirmation": public_confirmation},
    )

    assert result.status_code == 200
    body = result.json()
    assert body["status"] == "task_created"
    assert body["workflow_type"] == "t1_deepprep_anat_report"
    assert body["runtime_workflow_type"] == "t1_deepprep"
    assert body["task"]["workflow_type"] == "t1_deepprep_anat_report"
    assert body["task"]["runtime_workflow_type"] == "t1_deepprep"

    with database.connect() as conn:
        task_row = conn.execute("SELECT workflow_type, runtime_workflow_type FROM tasks WHERE id=?", (body["task"]["id"],)).fetchone()
        run_row = conn.execute("SELECT workflow_type FROM agent_runs WHERE agent_run_id=?", (body["agent_run_id"],)).fetchone()

    assert task_row["workflow_type"] == "t1_deepprep_anat_report"
    assert task_row["runtime_workflow_type"] == "t1_deepprep"
    assert run_row["workflow_type"] == "t1_deepprep_anat_report"


def test_task_observe_repair_exposes_runtime_workflow_type(tmp_path, monkeypatch):
    from app.core import config
    from app.db import database
    from app import main
    from app.main import app

    monkeypatch.setattr(config, "DATA_ROOT", tmp_path)
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "app.db")
    monkeypatch.setattr(config, "PROJECTS_ROOT", tmp_path / "projects")
    monkeypatch.setattr(database, "DB_PATH", tmp_path / "app.db")
    monkeypatch.setattr(main, "PROJECTS_ROOT", tmp_path / "projects")

    database.init_db()
    with database.connect() as conn:
        conn.execute("INSERT INTO projects(id, name, description, created_at) VALUES(?,?,?,?)", (1, "P", "", database.now_iso()))
        conn.execute(
            "INSERT INTO files(id, project_id, original_name, storage_path, file_type, size, sha256, created_at) VALUES(?,?,?,?,?,?,?,?)",
            (1, 1, "t1.nii.gz", str(tmp_path / "t1.nii.gz"), "NIFTI", 1, "x", database.now_iso()),
        )
        conn.execute(
            "INSERT INTO imaging_series(id, project_id, file_id, sequence_label, supported_for_processing, unsupported_reason, modality, format, confidence, metadata_json, status, created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
            (11, 1, 1, "T1_MPRAGE", 1, "", "T1", "NIFTI", 0.9, json.dumps({}), "detected", database.now_iso()),
        )
        conn.execute(
            "INSERT INTO tasks(id, project_id, series_id, workflow_type, runtime_workflow_type, status, progress, log_path, created_at) VALUES(?,?,?,?,?,?,?,?,?)",
            (21, 1, 11, "t1_deepprep_anat_report", "t1_deepprep", "failed", 100, str(tmp_path / "task.log"), database.now_iso()),
        )

    task_result = TestClient(app).get("/tasks/21")
    observe_repair_result = TestClient(app).get("/tasks/21/observe-repair")
    task_list_result = TestClient(app).get("/projects/1/tasks")
    observe_result = TestClient(app).post("/agent/runs", json={"project_id": 1, "message": "why did task 21 fail?"})

    assert task_result.status_code == 200
    assert task_result.json()["workflow_type"] == "t1_deepprep_anat_report"
    assert task_result.json()["runtime_workflow_type"] == "t1_deepprep"
    assert task_result.json()["workflow_metadata"]["workflow_type"] == "t1_deepprep_anat_report"
    assert task_result.json()["workflow_metadata"]["runtime_workflow_type"] == "t1_deepprep"
    assert task_result.json()["workflow_metadata"]["display_name"] == "T1 DeepPrep anatomical processing, QC, and report"
    assert task_result.json()["workflow_metadata"]["is_report_only"] is False
    assert task_list_result.status_code == 200
    assert task_list_result.json()[0]["workflow_metadata"]["workflow_type"] == "t1_deepprep_anat_report"
    assert observe_repair_result.status_code == 200
    assert observe_repair_result.json()["task"]["workflow_type"] == "t1_deepprep_anat_report"
    assert observe_repair_result.json()["task"]["runtime_workflow_type"] == "t1_deepprep"
    assert observe_repair_result.json()["task"]["workflow_metadata"]["workflow_type"] == "t1_deepprep_anat_report"
    assert observe_repair_result.json()["task"]["workflow_metadata"]["is_report_only"] is False
    assert observe_result.status_code == 200


def test_langgraph_agent_resume_approved_confirmation_creates_real_task_via_task_service(tmp_path, monkeypatch):
    from app.core import config
    from app.db import database
    from app.agent.langgraph_runner import LangGraphAgentRunner
    from app.agent.thread_store import AgentThreadStore
    from app import main
    from app.main import app

    monkeypatch.setattr(config, "DATA_ROOT", tmp_path)
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "app.db")
    monkeypatch.setattr(config, "PROJECTS_ROOT", tmp_path / "projects")
    monkeypatch.setattr(database, "DB_PATH", tmp_path / "app.db")
    monkeypatch.setattr(main, "PROJECTS_ROOT", tmp_path / "projects")
    monkeypatch.setattr(main, "run_pipeline_task", lambda task_id, qsiprep_task_id=None: None)
    monkeypatch.setenv("IMAGE_AGENT_AGENT_ENGINE", "langgraph")
    store = AgentThreadStore(tmp_path / "agent_threads")
    monkeypatch.setattr(main, "AgentRunner", lambda: LangGraphAgentRunner(thread_store=store))

    database.init_db()
    with database.connect() as conn:
        conn.execute("INSERT INTO projects(id, name, description, created_at) VALUES(?,?,?,?)", (1, "P", "", database.now_iso()))
        conn.execute(
            "INSERT INTO files(id, project_id, original_name, storage_path, file_type, size, sha256, created_at) VALUES(?,?,?,?,?,?,?,?)",
            (1, 1, "t1.nii.gz", str(tmp_path / "t1.nii.gz"), "NIFTI", 1, "x", database.now_iso()),
        )
        conn.execute(
            "INSERT INTO imaging_series(id, project_id, file_id, sequence_label, supported_for_processing, unsupported_reason, modality, format, confidence, metadata_json, status, created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
            (11, 1, 1, "T1_MPRAGE", 1, "", "T1", "NIFTI", 0.9, json.dumps({}), "detected", database.now_iso()),
        )

    confirmation = {
        "type": "workflow_execution",
        "project_id": 1,
        "series_id": 11,
        "workflow_type": "t1_deepprep_anat_report",
        "action_lane": "fixed_workflow",
        "preflight": {
            "ok": True,
            "workflow_type": "t1_deepprep_anat_report",
            "runtime_workflow_type": "t1_deepprep",
        },
    }
    thread = store.create_pending_confirmation(
        confirmation=confirmation,
        decision={"intent": "run_workflow"},
        selected_skill="image-agent-workflow-runner",
        retrieved_context={},
    )

    result = TestClient(app).post(
        f"/agent/runs/{thread['thread_id']}/resume",
        json={"approved": True, "confirmation": confirmation},
    )

    assert result.status_code == 200
    body = result.json()
    assert body["status"] == "task_created"
    assert body["production_task_created"] is True
    assert body["task"]["workflow_type"] == "t1_deepprep_anat_report"
    assert body["task"]["runtime_workflow_type"] == "t1_deepprep"
    assert body["safe_metadata"]["agent_engine"] == "langgraph"
    assert body["safe_metadata"]["lane"] == "fixed_workflow"
    assert body["safe_metadata"]["confirmation_gate"] == "fingerprint_verified"

    with database.connect() as conn:
        task_count = conn.execute("SELECT COUNT(*) FROM tasks").fetchone()[0]
        row = conn.execute(
            "SELECT workflow_type, task_id, approved, safe_metadata_json FROM agent_runs WHERE agent_run_id=?",
            (body["agent_run_id"],),
        ).fetchone()

    assert task_count == 1
    assert row["workflow_type"] == "t1_deepprep_anat_report"
    assert row["task_id"] == body["task"]["id"]
    assert row["approved"] == 1
    safe_metadata = json.loads(row["safe_metadata_json"])
    assert safe_metadata["agent_engine"] == "langgraph"
    assert safe_metadata["confirmation_gate"] == "fingerprint_verified"


def test_langgraph_agent_resume_blocks_incubation_without_creating_task(tmp_path, monkeypatch):
    from app.core import config
    from app.db import database
    from app.agent.langgraph_runner import LangGraphAgentRunner
    from app.agent.thread_store import AgentThreadStore
    from app import main
    from app.main import app

    monkeypatch.setattr(config, "DATA_ROOT", tmp_path)
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "app.db")
    monkeypatch.setattr(config, "PROJECTS_ROOT", tmp_path / "projects")
    monkeypatch.setattr(database, "DB_PATH", tmp_path / "app.db")
    monkeypatch.setattr(main, "PROJECTS_ROOT", tmp_path / "projects")
    monkeypatch.setattr(main, "run_pipeline_task", lambda task_id, qsiprep_task_id=None: None)
    monkeypatch.setenv("IMAGE_AGENT_AGENT_ENGINE", "langgraph")
    store = AgentThreadStore(tmp_path / "agent_threads")
    monkeypatch.setattr(main, "AgentRunner", lambda: LangGraphAgentRunner(thread_store=store))

    database.init_db()
    with database.connect() as conn:
        conn.execute("INSERT INTO projects(id, name, description, created_at) VALUES(?,?,?,?)", (1, "P", "", database.now_iso()))
        conn.execute(
            "INSERT INTO files(id, project_id, original_name, storage_path, file_type, size, sha256, created_at) VALUES(?,?,?,?,?,?,?,?)",
            (1, 1, "dwi.nii.gz", str(tmp_path / "dwi.nii.gz"), "NIFTI", 1, "x", database.now_iso()),
        )
        conn.execute(
            "INSERT INTO imaging_series(id, project_id, file_id, sequence_label, supported_for_processing, unsupported_reason, modality, format, confidence, metadata_json, status, created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
            (24, 1, 1, "DWI", 1, "", "DWI", "NIFTI", 0.9, json.dumps({}), "detected", database.now_iso()),
        )

    confirmation = {
        "type": "workflow_execution",
        "project_id": 1,
        "series_id": 24,
        "workflow_type": "unknown_connectome",
        "action_lane": "toolchain_incubation",
    }
    thread = store.create_pending_confirmation(
        confirmation=confirmation,
        decision={"intent": "run_workflow", "action_lane": "toolchain_incubation"},
        selected_skill="image-agent-workflow-runner",
        retrieved_context={},
    )

    result = TestClient(app).post(
        f"/agent/runs/{thread['thread_id']}/resume",
        json={"approved": True, "confirmation": confirmation},
    )

    assert result.status_code == 200
    body = result.json()
    assert body["status"] == "blocked"
    assert body["production_task_created"] is False
    assert body["safe_metadata"]["agent_engine"] == "langgraph"
    assert body["safe_metadata"]["lane"] == "toolchain_incubation"
    assert body["safe_metadata"]["confirmation_gate"] == "incubation_blocked"

    with database.connect() as conn:
        task_count = conn.execute("SELECT COUNT(*) FROM tasks").fetchone()[0]
        row = conn.execute(
            "SELECT status, task_id, approved, safe_metadata_json FROM agent_runs WHERE agent_run_id=?",
            (body["agent_run_id"],),
        ).fetchone()

    assert task_count == 0
    assert row["status"] == "blocked"
    assert row["task_id"] is None
    assert row["approved"] == 1
    safe_metadata = json.loads(row["safe_metadata_json"])
    assert safe_metadata["confirmation_gate"] == "incubation_blocked"


def test_agent_resume_blocks_client_confirmation_mismatch(tmp_path, monkeypatch):
    from app.core import config
    from app.db import database
    from app.agent.thread_store import AgentThreadStore
    from app import main
    from app.main import app

    monkeypatch.setattr(config, "DATA_ROOT", tmp_path)
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "app.db")
    monkeypatch.setattr(config, "PROJECTS_ROOT", tmp_path / "projects")
    monkeypatch.setattr(database, "DB_PATH", tmp_path / "app.db")
    monkeypatch.setattr(main, "PROJECTS_ROOT", tmp_path / "projects")
    monkeypatch.setattr(main, "run_pipeline_task", lambda task_id, qsiprep_task_id=None: None)
    database.init_db()
    with database.connect() as conn:
        conn.execute("INSERT INTO projects(id, name, description, created_at) VALUES(?,?,?,?)", (1, "P", "", database.now_iso()))
        conn.execute(
            "INSERT INTO files(id, project_id, original_name, storage_path, file_type, size, sha256, created_at) VALUES(?,?,?,?,?,?,?,?)",
            (1, 1, "t1.nii.gz", str(tmp_path / "t1.nii.gz"), "NIFTI", 1, "x", database.now_iso()),
        )
        conn.execute(
            "INSERT INTO imaging_series(id, project_id, file_id, sequence_label, supported_for_processing, unsupported_reason, modality, format, confidence, metadata_json, status, created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
            (11, 1, 1, "T1_MPRAGE", 1, "", "T1", "NIFTI", 0.9, json.dumps({}), "detected", database.now_iso()),
        )

    store = AgentThreadStore(tmp_path / "agent_threads")
    original_runner = main.AgentRunner
    monkeypatch.setattr(main, "AgentRunner", lambda: original_runner(thread_store=store))
    confirmation = {
        "type": "workflow_execution",
        "project_id": 1,
        "series_id": 11,
        "workflow_type": "t1_deepprep_anat_report",
        "action_lane": "fixed_workflow",
        "preflight": {
            "ok": True,
            "workflow_type": "t1_deepprep_anat_report",
            "runtime_workflow_type": "t1_deepprep",
        },
    }
    thread = store.create_pending_confirmation(
        confirmation=confirmation,
        decision={"intent": "run_workflow"},
        selected_skill="image-agent-workflow-runner",
        retrieved_context={},
    )

    result = TestClient(app).post(
        f"/agent/runs/{thread['thread_id']}/resume",
        json={"approved": True, "confirmation": {**confirmation, "series_id": 99}},
    )

    assert result.status_code == 200
    body = result.json()
    assert body["status"] == "blocked"
    assert body["production_task_created"] is False
    assert body["message"] == "Confirmation payload does not match the server-side pending confirmation."
    with database.connect() as conn:
        task_count = conn.execute("SELECT COUNT(*) FROM tasks").fetchone()[0]
    assert task_count == 0


def test_series_run_rejects_incubation_workflow_without_creating_task(tmp_path, monkeypatch):
    from app.core import config
    from app.db import database
    from app import main
    from app.main import app

    monkeypatch.setattr(config, "DATA_ROOT", tmp_path)
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "app.db")
    monkeypatch.setattr(config, "PROJECTS_ROOT", tmp_path / "projects")
    monkeypatch.setattr(database, "DB_PATH", tmp_path / "app.db")
    monkeypatch.setattr(main, "PROJECTS_ROOT", tmp_path / "projects")

    database.init_db()
    with database.connect() as conn:
        conn.execute("INSERT INTO projects(id, name, description, created_at) VALUES(?,?,?,?)", (1, "P", "", database.now_iso()))
        conn.execute(
            "INSERT INTO files(id, project_id, original_name, storage_path, file_type, size, sha256, created_at) VALUES(?,?,?,?,?,?,?,?)",
            (1, 1, "dwi.nii.gz", str(tmp_path / "dwi.nii.gz"), "NIFTI", 1, "x", database.now_iso()),
        )
        conn.execute(
            "INSERT INTO imaging_series(id, project_id, file_id, sequence_label, supported_for_processing, unsupported_reason, modality, format, confidence, metadata_json, status, created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                11,
                1,
                1,
                "DWI",
                1,
                "",
                "DWI",
                "NIFTI",
                0.9,
                json.dumps({"has_bval": True, "has_bvec": True}),
                "detected",
                database.now_iso(),
            ),
        )

    result = TestClient(app).post("/series/11/run", json={"workflow_type": "dwi_qsiprep"})

    assert result.status_code == 400
    assert "Unknown workflow_type" in result.json()["detail"]
    with database.connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM tasks").fetchone()[0] == 0
