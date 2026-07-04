from __future__ import annotations

import argparse
import json
import re
import urllib.error
import urllib.request
from collections.abc import Mapping, Sequence
from pathlib import Path


REQUIRED_ENV = {
    "IMAGE_AGENT_ELASTICSEARCH_URL": "elasticsearch_url_configured",
    "IMAGE_AGENT_RAG_EMBEDDING_PROVIDER": "rag_embedding_provider_configured",
    "IMAGE_AGENT_RAG_EMBEDDING_MODEL": "rag_embedding_model_configured",
}
OPTIONAL_SYMBOL_ENV = {
    "IMAGE_AGENT_ELASTICSEARCH_INDEX": "elasticsearch_index_configured",
}
OPTIONAL_SECRET_ENV = {
    "IMAGE_AGENT_ELASTICSEARCH_API_KEY": "elasticsearch_api_key_configured",
    "IMAGE_AGENT_RAG_EMBEDDING_API_KEY": "rag_embedding_api_key_configured",
}
EMBEDDING_ENDPOINT_ENV = "IMAGE_AGENT_RAG_EMBEDDING_BASE_URL"
LOCAL_EMBEDDING_PROVIDERS = {
    "deterministic_local_hashing",
    "local_hashing",
    "local-token-hash-v1",
    "mock",
    "none",
    "",
}
PRODUCTION_EMBEDDING_TRANSPORTS = {"sdk", "openai_compatible_http"}
OPENAI_COMPATIBLE_ENV_PROVIDERS = {"openai", "openai_compatible", "custom"}
ELASTICSEARCH_RRF_SOURCE_URL = "https://www.elastic.co/docs/reference/elasticsearch/rest-apis/reciprocal-rank-fusion"


class PrerequisiteFailure(SystemExit):
    def __init__(self, report: Mapping[str, object]):
        self.report = dict(report)
        failures = report.get("failures")
        message = "; ".join(failures) if isinstance(failures, list) else "Elasticsearch hybrid prerequisites failed"
        super().__init__(message)


def _privacy_safe_symbol(value: object) -> bool:
    return isinstance(value, str) and bool(value) and len(value) <= 140 and all(
        char.isalnum() or char in "_.-" for char in value
    )


def _safe_metadata_value(value: object) -> str | None:
    if _privacy_safe_symbol(value):
        return str(value)
    return None


def _safe_loopback_endpoint(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    text = value.strip()
    if re.match(r"^https?://(?:127\.0\.0\.1|localhost):\d{2,5}$", text):
        return text
    return None


def _safe_int(value: object) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value


def _normalized_env_embedding_provider(value: str) -> str:
    provider = str(value or "").strip().lower()
    return "openai" if provider in OPENAI_COMPATIBLE_ENV_PROVIDERS else provider


def _positive_int(value: object) -> int | None:
    number = _safe_int(value)
    if number is None or number <= 0:
        return None
    return number


def _load_env_file(path: Path) -> dict[str, str]:
    if not path.exists():
        raise SystemExit(f"env file does not exist: {path}")
    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip("'\"")
        if key:
            values[key] = value
    return values


def _fetch_rag_status(url: str) -> dict | None:
    if not url:
        return None
    request = urllib.request.Request(url, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            return json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise SystemExit(f"could not read /agent/rag/status safely: {type(exc).__name__}") from exc


def _load_json_file(path: Path) -> dict:
    if not path.exists():
        raise SystemExit(f"json file does not exist: {path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SystemExit(f"could not read json file safely: {type(exc).__name__}") from exc
    if not isinstance(payload, dict):
        raise SystemExit("json file must contain an object")
    return payload


def _rag_status_summary(rag_status: Mapping[str, object] | None) -> dict[str, object | None]:
    index = rag_status.get("index") if isinstance(rag_status, Mapping) else None
    index = index if isinstance(index, Mapping) else {}
    hybrid = index.get("hybrid_search") if isinstance(index.get("hybrid_search"), Mapping) else {}
    official_sources = hybrid.get("official_sources")
    return {
        "rag_status_engine": _safe_metadata_value(index.get("engine")),
        "rag_status_hybrid_configured": hybrid.get("configured") is True,
        "rag_status_hybrid_engine": _safe_metadata_value(hybrid.get("engine")),
        "rag_status_hybrid_index": _safe_metadata_value(hybrid.get("index")),
        "rag_status_hybrid_mode": _safe_metadata_value(hybrid.get("mode")),
        "rag_status_hybrid_persisted": hybrid.get("persisted"),
        "rag_status_hybrid_indexed_chunk_count": _safe_int(hybrid.get("indexed_chunk_count")),
        "rag_status_hybrid_lexical_retriever": _safe_metadata_value(hybrid.get("lexical_retriever")),
        "rag_status_hybrid_vector_retriever": _safe_metadata_value(hybrid.get("vector_retriever")),
        "rag_status_hybrid_dense_vector_field": _safe_metadata_value(hybrid.get("dense_vector_field")),
        "rag_status_hybrid_dense_vector_dims": _safe_int(hybrid.get("dense_vector_dims")),
        "rag_status_hybrid_fusion": _safe_metadata_value(hybrid.get("fusion")),
        "rag_status_hybrid_official_rrf_source_present": (
            isinstance(official_sources, list) and ELASTICSEARCH_RRF_SOURCE_URL in official_sources
        ),
        "rag_status_hybrid_error_absent": not bool(hybrid.get("error")),
        "rag_status_hybrid_embedding_error_absent": not bool(hybrid.get("embedding_error")),
        "rag_status_hybrid_embedding_provider": _safe_metadata_value(hybrid.get("embedding_provider")),
        "rag_status_hybrid_embedding_model": _safe_metadata_value(hybrid.get("embedding_model")),
        "rag_status_hybrid_embedding_transport": _safe_metadata_value(hybrid.get("embedding_transport")),
        "rag_status_hybrid_embedding_endpoint_configured": hybrid.get("embedding_endpoint_configured") is True,
        "rag_status_hybrid_embedding_production_ready": hybrid.get("embedding_production_ready") is True,
    }


def _runtime_probe_summary(runtime_probe: Mapping[str, object] | None) -> dict[str, object | None]:
    if runtime_probe is None:
        return {}
    docker = runtime_probe.get("docker") if isinstance(runtime_probe.get("docker"), Mapping) else {}
    elasticsearch = runtime_probe.get("elasticsearch") if isinstance(runtime_probe.get("elasticsearch"), Mapping) else {}
    discovery = (
        elasticsearch.get("runtime_discovery")
        if isinstance(elasticsearch.get("runtime_discovery"), Mapping)
        else {}
    )
    blocking_codes = runtime_probe.get("blocking_codes")
    safe_blocking_codes = [
        code
        for code in blocking_codes
        if _privacy_safe_symbol(code)
    ] if isinstance(blocking_codes, list) else []
    return {
        "runtime_probe_supplied": True,
        "runtime_probe_schema_version": _safe_int(runtime_probe.get("schema_version")),
        "runtime_probe_portable": runtime_probe.get("portable") is True,
        "runtime_probe_machine_binding": _safe_metadata_value(runtime_probe.get("machine_binding")),
        "runtime_probe_workflow_tool_execution": _safe_metadata_value(runtime_probe.get("workflow_tool_execution")),
        "runtime_probe_docker_runtime_host": _safe_metadata_value(runtime_probe.get("docker_runtime_host")),
        "runtime_probe_docker_accessible": docker.get("accessible") is True,
        "runtime_probe_docker_requires_sudo": docker.get("requires_sudo") is True,
        "runtime_probe_blocking_codes": safe_blocking_codes,
        "runtime_probe_elasticsearch_configured": elasticsearch.get("configured") is True,
        "runtime_probe_elasticsearch_endpoint_configured": elasticsearch.get("endpoint_configured") is True,
        "runtime_probe_elasticsearch_endpoint_source": _safe_metadata_value(elasticsearch.get("endpoint_source")),
        "runtime_probe_elasticsearch_discovery_scope": _safe_metadata_value(discovery.get("scope")),
        "runtime_probe_elasticsearch_discovery_status": _safe_metadata_value(discovery.get("status")),
        "runtime_probe_elasticsearch_discovery_count": _safe_int(discovery.get("count")),
        "runtime_probe_elasticsearch_discovery_running_count": _safe_int(discovery.get("running_count")),
        "runtime_probe_elasticsearch_container_running": discovery.get("container_running") is True,
        "runtime_probe_elasticsearch_candidate_endpoint": _safe_loopback_endpoint(discovery.get("candidate_endpoint")),
        "runtime_probe_elasticsearch_candidate_endpoint_source": _safe_metadata_value(
            discovery.get("candidate_endpoint_source")
        ),
    }


def _failure_messages(checked: Mapping[str, object]) -> list[str]:
    failures: list[str] = []
    if checked.get("elasticsearch_url_configured") is not True:
        failures.append("IMAGE_AGENT_ELASTICSEARCH_URL must be configured")
    if checked.get("rag_embedding_provider_configured") is not True:
        failures.append("IMAGE_AGENT_RAG_EMBEDDING_PROVIDER must be configured")
    if checked.get("rag_embedding_provider_production_configured") is not True:
        failures.append("IMAGE_AGENT_RAG_EMBEDDING_PROVIDER must be production configured")
    if checked.get("rag_embedding_model_configured") is not True:
        failures.append("IMAGE_AGENT_RAG_EMBEDDING_MODEL must be configured")
    if checked.get("rag_embedding_endpoint_configured") is not True:
        failures.append("IMAGE_AGENT_RAG_EMBEDDING_BASE_URL must be configured for production embeddings")
    engine = checked.get("rag_status_engine")
    if engine != "elasticsearch_hybrid":
        failures.append("Current /agent/rag/status engine is not elasticsearch_hybrid")
    if checked.get("rag_status_hybrid_engine") != "elasticsearch":
        failures.append("Current /agent/rag/status hybrid engine is not elasticsearch")
    if checked.get("rag_status_hybrid_configured") is not True:
        failures.append("Current /agent/rag/status hybrid search is not configured")
    if checked.get("rag_status_hybrid_mode") != "connected":
        failures.append("Current /agent/rag/status hybrid mode is not connected")
    if checked.get("rag_status_hybrid_persisted") is not True:
        failures.append("Current /agent/rag/status hybrid index is not persisted")
    if checked.get("rag_status_hybrid_index") is None:
        failures.append("Current /agent/rag/status hybrid index is not privacy-safe")
    if checked.get("rag_status_hybrid_index_matches_env") is not True:
        failures.append("Current /agent/rag/status hybrid index must match IMAGE_AGENT_ELASTICSEARCH_INDEX")
    if _positive_int(checked.get("rag_status_hybrid_indexed_chunk_count")) is None:
        failures.append("Current /agent/rag/status indexed_chunk_count must be greater than zero")
    if checked.get("rag_status_hybrid_lexical_retriever") != "standard":
        failures.append("Current /agent/rag/status lexical retriever is not standard")
    if checked.get("rag_status_hybrid_vector_retriever") != "knn":
        failures.append("Current /agent/rag/status vector retriever is not knn")
    if checked.get("rag_status_hybrid_dense_vector_field") != "embedding":
        failures.append("Current /agent/rag/status dense_vector_field is not embedding")
    if _positive_int(checked.get("rag_status_hybrid_dense_vector_dims")) is None:
        failures.append("Current /agent/rag/status dense_vector_dims must be greater than zero")
    if checked.get("rag_status_hybrid_fusion") != "rrf":
        failures.append("Current /agent/rag/status hybrid fusion is not rrf")
    if checked.get("rag_status_hybrid_official_rrf_source_present") is not True:
        failures.append("Current /agent/rag/status official_sources must include Elasticsearch RRF documentation")
    if checked.get("rag_status_hybrid_error_absent") is not True:
        failures.append("Current /agent/rag/status hybrid error must be absent")
    if checked.get("rag_status_hybrid_embedding_error_absent") is not True:
        failures.append("Current /agent/rag/status embedding error must be absent")
    provider = checked.get("rag_status_hybrid_embedding_provider")
    if not isinstance(provider, str) or provider.lower() in LOCAL_EMBEDDING_PROVIDERS:
        failures.append("Current /agent/rag/status embedding provider is not production configured")
    if checked.get("rag_status_hybrid_embedding_model") is None:
        failures.append("Current /agent/rag/status embedding model must be present")
    if checked.get("rag_status_hybrid_embedding_provider_matches_env") is not True:
        failures.append("Current /agent/rag/status embedding provider must match IMAGE_AGENT_RAG_EMBEDDING_PROVIDER")
    if checked.get("rag_status_hybrid_embedding_model_matches_env") is not True:
        failures.append("Current /agent/rag/status embedding model must match IMAGE_AGENT_RAG_EMBEDDING_MODEL")
    if checked.get("rag_status_hybrid_embedding_transport") not in PRODUCTION_EMBEDDING_TRANSPORTS:
        failures.append("Current /agent/rag/status embedding transport is not production-safe")
    if checked.get("rag_status_hybrid_embedding_endpoint_configured") is not True:
        failures.append("Current /agent/rag/status embedding endpoint must be configured")
    if checked.get("rag_status_hybrid_embedding_production_ready") is not True:
        failures.append("Current /agent/rag/status embedding production readiness must be true")
    if checked.get("runtime_probe_supplied") is True:
        if checked.get("runtime_probe_schema_version") != 1:
            failures.append("Runtime probe schema_version must be 1")
        if checked.get("runtime_probe_portable") is not True:
            failures.append("Runtime probe must be portable")
        if checked.get("runtime_probe_machine_binding") != "runtime_discovered":
            failures.append("Runtime probe machine_binding must be runtime_discovered")
        if checked.get("runtime_probe_workflow_tool_execution") != "deployment_server_local":
            failures.append("Runtime probe workflow_tool_execution must be deployment_server_local")
        if checked.get("runtime_probe_docker_runtime_host") != "api_server":
            failures.append("Runtime probe docker_runtime_host must be api_server")
        if checked.get("runtime_probe_docker_accessible") is not True:
            failures.append("Runtime probe Docker access must be available")
        if checked.get("runtime_probe_docker_requires_sudo") is True:
            failures.append("Runtime probe Docker access must not require sudo")
        if checked.get("runtime_probe_elasticsearch_configured") is not True:
            failures.append("Runtime probe must report Elasticsearch configured")
        if checked.get("runtime_probe_elasticsearch_endpoint_configured") is not True:
            failures.append("Runtime probe must report Elasticsearch endpoint configured")
        if checked.get("runtime_probe_elasticsearch_endpoint_source") != "env_redacted":
            failures.append("Runtime probe Elasticsearch endpoint_source must be env_redacted")
        if checked.get("runtime_probe_elasticsearch_discovery_scope") != "local_docker_elasticsearch":
            failures.append("Runtime probe Elasticsearch discovery scope must be local_docker_elasticsearch")
        if checked.get("runtime_probe_elasticsearch_discovery_status") != "available":
            failures.append("Runtime probe Elasticsearch runtime discovery must be available")
        if checked.get("runtime_probe_elasticsearch_container_running") is not True:
            failures.append("Runtime probe must discover a running local Docker Elasticsearch container")
        if _positive_int(checked.get("runtime_probe_elasticsearch_discovery_running_count")) is None:
            failures.append("Runtime probe Elasticsearch running_count must be greater than zero")
        if checked.get("runtime_probe_elasticsearch_candidate_endpoint") is None:
            failures.append("Runtime probe Elasticsearch candidate_endpoint must be privacy-safe")
    return failures


def verify_prerequisites(
    *,
    env_file: Path,
    rag_status: Mapping[str, object] | None,
    runtime_probe: Mapping[str, object] | None = None,
) -> dict:
    env = _load_env_file(env_file)
    checked: dict[str, object | None] = {
        safe_key: bool(env.get(env_key, "").strip())
        for env_key, safe_key in REQUIRED_ENV.items()
    }
    checked.update(
        {
            safe_key: bool(env.get(env_key, "").strip())
            for env_key, safe_key in OPTIONAL_SECRET_ENV.items()
        }
    )
    checked.update(
        {
            safe_key: bool(env.get(env_key, "").strip())
            for env_key, safe_key in OPTIONAL_SYMBOL_ENV.items()
        }
    )
    env_embedding_provider = env.get("IMAGE_AGENT_RAG_EMBEDDING_PROVIDER", "").strip().lower()
    checked["rag_embedding_provider_production_configured"] = bool(env_embedding_provider) and (
        env_embedding_provider not in LOCAL_EMBEDDING_PROVIDERS
    )
    checked["rag_embedding_endpoint_configured"] = bool(env.get(EMBEDDING_ENDPOINT_ENV, "").strip())
    checked.update(_rag_status_summary(rag_status))
    env_index = env.get("IMAGE_AGENT_ELASTICSEARCH_INDEX", "").strip()
    checked["rag_status_hybrid_index_matches_env"] = (
        True if not env_index else checked.get("rag_status_hybrid_index") == env_index
    )
    checked["rag_status_hybrid_embedding_provider_matches_env"] = (
        checked.get("rag_status_hybrid_embedding_provider") == _normalized_env_embedding_provider(env_embedding_provider)
    )
    checked["rag_status_hybrid_embedding_model_matches_env"] = (
        checked.get("rag_status_hybrid_embedding_model") == env.get("IMAGE_AGENT_RAG_EMBEDDING_MODEL", "").strip()
    )
    checked.update(_runtime_probe_summary(runtime_probe))
    checked["secrets_redacted"] = True

    if rag_status is None:
        raise SystemExit("Current /agent/rag/status must be supplied for Elasticsearch hybrid prereq verification")

    failures = _failure_messages(checked)
    if failures:
        raise PrerequisiteFailure({"status": "failed", "checked": checked, "failures": failures})
    return {"status": "passed", "checked": checked}


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Verify privacy-safe Elasticsearch hybrid RAG prerequisites before mutating strict smoke."
    )
    parser.add_argument("--env-file", required=True, help="Deployment .env file to inspect without printing values.")
    parser.add_argument(
        "--rag-status-url",
        default=None,
        help="Optional deployed /agent/rag/status URL for a read-only current-engine summary.",
    )
    parser.add_argument(
        "--runtime-probe-json",
        default=None,
        help="Optional JSON from probe_runtime_environment.py --json to verify deployment-server-local ES discovery.",
    )
    args = parser.parse_args(argv)

    try:
        report = verify_prerequisites(
            env_file=Path(args.env_file),
            rag_status=_fetch_rag_status(args.rag_status_url) if args.rag_status_url else None,
            runtime_probe=_load_json_file(Path(args.runtime_probe_json)) if args.runtime_probe_json else None,
        )
    except PrerequisiteFailure as exc:
        print(json.dumps(exc.report, indent=2, sort_keys=True))
        raise SystemExit(1) from exc
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
