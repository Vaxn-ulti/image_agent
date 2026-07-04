from __future__ import annotations

import argparse
import json
import mimetypes
import re
import sqlite3
import time
import urllib.error
import urllib.request
from collections.abc import Sequence
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote, urlsplit, urlunsplit
from uuid import uuid4


LAUNCHABILITY_MATRIX_SOURCE = "docs/rag/workflows/workflow_launchability_matrix.md"
LAUNCHABILITY_SMOKE_QUERY = "Use the workflow launchability matrix to explain which workflows are launchable and cite the matrix."
ELASTICSEARCH_HYBRID_CONTRACT_SOURCE = "docs/rag/contracts/elasticsearch-hybrid-search.md"
ELASTICSEARCH_HYBRID_SMOKE_QUERY = "Use the Elasticsearch hybrid search contract to explain the BM25 dense-vector kNN RRF retrieval boundary."
UNKNOWN_WORKFLOW_INCUBATION_WORKFLOW_TYPE = "codex_unknown_workflow_smoke"
UNKNOWN_WORKFLOW_INCUBATION_SMOKE_QUERY = (
    "Try to run the unregistered workflow codex_unknown_workflow_smoke. "
    "It is not in the fixed workflow registry; propose incubation only and do not create a production task."
)
ELASTICSEARCH_RRF_SOURCE_URL = "https://www.elastic.co/docs/reference/elasticsearch/rest-apis/reciprocal-rank-fusion"
ELASTICSEARCH_ACCEPTED_FUSION_FALLBACK_REASON = "license_non_compliant"
LOCAL_EMBEDDING_PROVIDERS = {
    "",
    "local_hashing",
    "deterministic_local_hashing",
    "local-token-hash-v1",
    "mock",
    "mock_embedding",
}
WORKFLOW_ELIGIBILITY_METADATA_REQUIRED_FIELDS = [
    "display_name",
    "capability_summary",
    "workflow_family",
    "workflow_role",
    "pipeline_stages",
    "primary_outputs",
    "qc_outputs",
    "report_outputs",
    "limitations",
    "agent_selectable",
    "is_report_only",
]
CONTAINER_NATIVE_QC_OFFICIAL_SOURCE_IDS = frozenset(
    {
        "docs/rag/vendor/deepprep_official_container_usage.md",
        "docs/rag/vendor/fmriprep_official_outputs.md",
        "docs/rag/vendor/freesurfer_official_container_reconall.md",
        "docs/rag/vendor/fsl_official_fast_dti_tools.md",
        "docs/rag/vendor/mrtrix3_official_dti_toolbox.md",
        "docs/rag/vendor/qsiprep_official_container_usage_outputs.md",
        "docs/rag/vendor/qsirecon_official_container_usage_workflows.md",
        "docs/rag/vendor/xcp_d_official_outputs.md",
    }
)
DEBUG_ONLY_WORKFLOWS = frozenset({"t1_deepprep_mock"})
RUNTIME_WORKFLOW_ALIASES = {
    "t1_deepprep_anat_report": "t1_deepprep",
}


def _rrf_unavailable_reason(metadata: dict) -> str:
    return str(metadata.get("rrf_unavailable_reason") or "").strip()


def _validate_elasticsearch_fusion(metadata: dict, *, context: str) -> tuple[str, str | None]:
    fusion = str(metadata.get("fusion") or "").strip()
    reason = _rrf_unavailable_reason(metadata)
    if fusion == "rrf":
        return fusion, None
    _require(
        fusion == "query_plus_knn" and reason == ELASTICSEARCH_ACCEPTED_FUSION_FALLBACK_REASON,
        f"{context}: fusion must be rrf or query_plus_knn with rrf_unavailable_reason=license_non_compliant",
    )
    return fusion, reason
REPO_ROOT = Path(__file__).resolve().parents[3]
SOURCE_MARKER_KEYS = frozenset(
    {
        "citation",
        "citations",
        "document",
        "file",
        "filename",
        "indexed_sources",
        "path",
        "reference",
        "references",
        "source",
        "source_path",
        "sources",
    }
)


def _request(method: str, url: str, payload: dict | None = None) -> dict:
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"} if payload is not None else {},
        method=method,
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise SystemExit(f"{method} {url} failed: HTTP {exc.code} {body}") from exc


def _request_bytes(url: str) -> tuple[bytes, str]:
    req = urllib.request.Request(url, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=120) as response:
            return response.read(), response.headers.get("Content-Type", "")
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise SystemExit(f"GET {url} failed: HTTP {exc.code} {body}") from exc


def _request_multipart_file(url: str, *, field_name: str, path: Path, content_type: str | None = None) -> dict:
    if not path.is_file():
        raise SystemExit(f"upload file does not exist: {path}")
    boundary = f"imageagent{uuid4().hex}"
    filename = path.name
    effective_content_type = content_type or mimetypes.guess_type(filename)[0] or "application/octet-stream"
    file_bytes = path.read_bytes()
    header = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="{field_name}"; filename="{filename}"\r\n'
        f"Content-Type: {effective_content_type}\r\n\r\n"
    ).encode("utf-8")
    footer = f"\r\n--{boundary}--\r\n".encode("utf-8")
    body = header + file_bytes + footer
    req = urllib.request.Request(
        url,
        data=body,
        headers={
            "Content-Type": f"multipart/form-data; boundary={boundary}",
            "Content-Length": str(len(body)),
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=300) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        response_body = exc.read().decode("utf-8", errors="replace")
        raise SystemExit(f"POST {url} failed: HTTP {exc.code} {response_body}") from exc


def _upload_nifti(base: str, project_id: int, path: Path) -> dict:
    return _request_multipart_file(f"{base}/projects/{project_id}/upload", field_name="file", path=path)


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(message)


def _is_privacy_safe_symbol(value: object) -> bool:
    return (
        isinstance(value, str)
        and bool(value)
        and len(value) <= 140
        and all(char.isalnum() or char in "_.-" for char in value)
    )


def _safe_model_status(status: dict) -> dict:
    safe: dict = {"configured": bool(status.get("configured"))}
    for key in ("provider", "provider_profile", "model", "review_model", "wire_api", "reasoning_effort"):
        value = status.get(key)
        if isinstance(value, str) and _is_privacy_safe_symbol(value):
            safe[key] = value
    base_url = status.get("base_url")
    if isinstance(base_url, str) and base_url:
        parsed = urlsplit(base_url)
        if parsed.scheme in {"http", "https"} and parsed.hostname:
            host = parsed.hostname
            if parsed.port is not None:
                host = f"{host}:{parsed.port}"
            safe["base_url"] = urlunsplit((parsed.scheme, host, parsed.path, parsed.query, parsed.fragment))
    for key in ("store", "metadata_enabled", "trust_env_proxy"):
        if isinstance(status.get(key), bool):
            safe[key] = status[key]
    capabilities = status.get("capabilities")
    if isinstance(capabilities, dict):
        safe_capabilities = {}
        for key in ("text", "structured_json", "model_tool_loop"):
            if isinstance(capabilities.get(key), bool):
                safe_capabilities[key] = capabilities[key]
        if safe_capabilities:
            safe["capabilities"] = safe_capabilities
    deployment = status.get("deployment")
    if isinstance(deployment, dict):
        safe_deployment = {}
        for key in ("backend_runtime_mode", "model_gateway_access"):
            value = deployment.get(key)
            if isinstance(value, str) and _is_privacy_safe_symbol(value):
                safe_deployment[key] = value
        if safe_deployment:
            safe["deployment"] = safe_deployment
    gateway_diagnostics = status.get("gateway_diagnostics")
    if isinstance(gateway_diagnostics, dict):
        safe_gateway_diagnostics = {}
        for key, value in gateway_diagnostics.items():
            if (
                isinstance(key, str)
                and isinstance(value, str)
                and _is_privacy_safe_symbol(key)
                and _is_privacy_safe_symbol(value)
            ):
                safe_gateway_diagnostics[key] = value
        if safe_gateway_diagnostics:
            safe["gateway_diagnostics"] = safe_gateway_diagnostics
    return safe


def _safe_production_readiness(deployment: dict) -> dict:
    readiness = deployment.get("production_readiness")
    _require(isinstance(readiness, dict), "production readiness is missing from /deployment")
    blocking_reasons = readiness.get("blocking_reasons")
    if not isinstance(blocking_reasons, list):
        blocking_reasons = []
    safe_reasons = [reason for reason in blocking_reasons if isinstance(reason, str) and reason]
    safe = {
        "required": readiness.get("required") is True,
        "ready": readiness.get("ready") is True,
        "status": readiness.get("status") if isinstance(readiness.get("status"), str) else "",
        "blocking_reasons": safe_reasons,
    }
    if safe["required"] is not True or safe["ready"] is not True or safe["status"] != "ready" or safe_reasons:
        reason_text = "; ".join(safe_reasons) if safe_reasons else "production readiness is not ready"
        raise SystemExit(f"production readiness is blocked: {reason_text}")
    return safe


def _requires_direct_model_gateway(status: dict, expected_provider_profile: str | None) -> bool:
    provider_profile = str(status.get("provider_profile") or "").strip().lower()
    if provider_profile == "rawchat" or expected_provider_profile == "rawchat":
        return True
    base_url = status.get("base_url")
    if not isinstance(base_url, str) or not base_url:
        return False
    host = (urlsplit(base_url).hostname or "").lower()
    return host == "rawchat.cn" or host.endswith(".rawchat.cn")


def _validate_direct_model_gateway(status: dict, expected_provider_profile: str | None) -> None:
    if not _requires_direct_model_gateway(status, expected_provider_profile):
        return
    _require(
        status.get("trust_env_proxy") is False,
        "rawchat model trust_env_proxy must be false",
    )
    deployment = status.get("deployment") if isinstance(status.get("deployment"), dict) else {}
    access = deployment.get("model_gateway_access")
    _require(
        access == "direct",
        f"rawchat model gateway access {access or 'missing'} did not match direct",
    )


STRICT_REMOTE_ACCEPTANCE_MISSING_REASON = (
    "Strict remote acceptance evidence has not been verified for the upload-agent-workflow-result chain."
)


def _safe_fast_launch_readiness(deployment: dict) -> dict:
    readiness = deployment.get("fast_launch_readiness")
    _require(isinstance(readiness, dict), "fast launch readiness is missing from /deployment")
    blocking_reasons = readiness.get("blocking_reasons")
    if not isinstance(blocking_reasons, list):
        blocking_reasons = []
    safe_reasons = [reason for reason in blocking_reasons if isinstance(reason, str) and reason]
    checks = readiness.get("checks") if isinstance(readiness.get("checks"), dict) else {}
    safe_checks: dict = {}
    production_deployment = checks.get("production_deployment")
    if isinstance(production_deployment, dict):
        production_blockers = production_deployment.get("blocking_reasons")
        if not isinstance(production_blockers, list):
            production_blockers = []
        safe_checks["production_deployment"] = {
            "status": production_deployment.get("status")
            if isinstance(production_deployment.get("status"), str)
            and _is_privacy_safe_symbol(production_deployment.get("status"))
            else "",
            "required": production_deployment.get("required") is True,
            "ready": production_deployment.get("ready") is True,
            "readiness_status": production_deployment.get("readiness_status")
            if isinstance(production_deployment.get("readiness_status"), str)
            and _is_privacy_safe_symbol(production_deployment.get("readiness_status"))
            else "",
            "blocking_reasons": [reason for reason in production_blockers if isinstance(reason, str) and reason],
        }
    for check_name in (
        "model_gateway_target",
        "agent_task_boundary",
        "upload_workflow_result_contract",
        "strict_remote_acceptance",
    ):
        check = checks.get(check_name)
        if isinstance(check, dict):
            status = check.get("status")
            safe_checks[check_name] = {"status": status if isinstance(status, str) and _is_privacy_safe_symbol(status) else ""}
    rag_check = checks.get("rag_elasticsearch_hybrid")
    if isinstance(rag_check, dict):
        safe_rag = {}
        for key in ("status", "engine", "mode", "index", "embedding_provider", "embedding_model", "embedding_transport", "fusion"):
            value = rag_check.get(key)
            safe_rag[key] = value if isinstance(value, str) and _is_privacy_safe_symbol(value) else None
        for key in ("configured", "persisted", "embedding_endpoint_configured", "embedding_production_ready"):
            safe_rag[key] = rag_check.get(key) is True
        for key in ("indexed_chunk_count", "dense_vector_dims"):
            value = _int_metric(rag_check.get(key))
            safe_rag[key] = value if value > 0 else 0
        official_sources = rag_check.get("official_sources")
        if isinstance(official_sources, list):
            safe_rag["official_rrf_source_present"] = ELASTICSEARCH_RRF_SOURCE_URL in official_sources
        safe_checks["rag_elasticsearch_hybrid"] = safe_rag
    safe = {
        "ready": readiness.get("ready") is True,
        "status": readiness.get("status") if isinstance(readiness.get("status"), str) else "",
        "blocking_reasons": safe_reasons,
        "checks": safe_checks,
    }
    rag_status = safe_checks.get("rag_elasticsearch_hybrid", {}).get("status")
    if rag_status != "passed":
        raise SystemExit("fast launch readiness check rag_elasticsearch_hybrid is not passed")
    production_status = safe_checks.get("production_deployment", {}).get("status")
    if production_status != "passed":
        raise SystemExit("fast launch readiness check production_deployment is not passed")
    if (
        safe_checks.get("production_deployment", {}).get("required") is not True
        or safe_checks.get("production_deployment", {}).get("ready") is not True
        or safe_checks.get("production_deployment", {}).get("readiness_status") != "ready"
        or safe_checks.get("production_deployment", {}).get("blocking_reasons")
    ):
        raise SystemExit("fast launch readiness production_deployment must prove production readiness")
    for check_name in (
        "model_gateway_target",
        "agent_task_boundary",
        "upload_workflow_result_contract",
    ):
        if safe_checks.get(check_name, {}).get("status") != "passed":
            raise SystemExit(f"fast launch readiness check {check_name} is not passed")
    strict_status = safe_checks.get("strict_remote_acceptance", {}).get("status")
    if strict_status == "passed":
        if safe["ready"] is not True or safe["status"] != "ready" or safe_reasons:
            reason_text = "; ".join(safe_reasons) if safe_reasons else "fast launch readiness is not ready"
            raise SystemExit(f"fast launch readiness is blocked: {reason_text}")
        safe["_acceptance_status"] = "passed"
        return safe
    if strict_status == "missing":
        if (
            safe["ready"] is not False
            or safe["status"] != "blocked"
            or safe_reasons != [STRICT_REMOTE_ACCEPTANCE_MISSING_REASON]
        ):
            raise SystemExit(
                "fast launch readiness pre_acceptance must only be blocked by missing strict remote acceptance evidence"
            )
        safe["_acceptance_status"] = "pre_acceptance"
        return safe
    raise SystemExit("fast launch readiness check strict_remote_acceptance is not passed or missing")
    return safe


def _safe_runtime_toolchain(runtime_status: dict, *, required_workflow_type: str | None = None) -> dict:
    _require(isinstance(runtime_status, dict), "runtime toolchain response must be an object")
    workflows = runtime_status.get("workflows")
    _require(isinstance(workflows, dict) and workflows, "runtime toolchain workflows must be present")
    workflow_types: list[str] = []
    available_workflows: list[str] = []
    unavailable_workflows: list[str] = []
    for workflow_type, workflow in workflows.items():
        _require(_is_privacy_safe_symbol(workflow_type), "runtime toolchain workflow_type must be privacy-safe")
        workflow_types.append(workflow_type)
        available = isinstance(workflow, dict) and workflow.get("available") is True
        if available:
            available_workflows.append(workflow_type)
        else:
            unavailable_workflows.append(workflow_type)
    required_available = None
    required_runtime_workflow_type = None
    if required_workflow_type:
        _require(
            _is_privacy_safe_symbol(required_workflow_type),
            "runtime toolchain required workflow_type must be privacy-safe",
        )
        required_runtime_workflow_type = required_workflow_type
        if required_runtime_workflow_type not in workflows:
            alias = RUNTIME_WORKFLOW_ALIASES.get(required_workflow_type)
            if alias in workflows:
                required_runtime_workflow_type = alias
            else:
                raise SystemExit(f"runtime toolchain missing required workflow {required_workflow_type}")
        required_available = (
            isinstance(workflows.get(required_runtime_workflow_type), dict)
            and workflows[required_runtime_workflow_type].get("available") is True
        )
        _require(required_available, f"runtime toolchain required workflow {required_workflow_type} is not available")
    resources = runtime_status.get("resources") if isinstance(runtime_status.get("resources"), dict) else {}
    _require(
        runtime_status.get("fs_license_exists") is True or resources.get("fs_license_exists") is True,
        "runtime toolchain FreeSurfer license is missing",
    )
    safe = {
        "workflow_tool_execution": "deployment_server_local",
        "docker_runtime_host": "api_server",
        "docker_requires_sudo": (
            runtime_status.get("docker_requires_sudo") is True
            or (isinstance(runtime_status.get("docker"), dict) and runtime_status["docker"].get("requires_sudo") is True)
        ),
        "fs_license_exists": True,
        "workflow_count": int(runtime_status.get("workflow_count") or len(workflow_types)),
        "available_workflow_count": int(runtime_status.get("available_workflow_count") or len(available_workflows)),
        "required_workflow_type": required_workflow_type,
        "required_workflow_available": required_available,
        "unavailable_workflows": sorted(unavailable_workflows),
        "workflow_types": sorted(workflow_types),
    }
    if required_runtime_workflow_type and required_runtime_workflow_type != required_workflow_type:
        safe["required_runtime_workflow_type"] = required_runtime_workflow_type
    return safe


def _runtime_toolchain_status(base: str) -> dict:
    try:
        probe = _request("GET", f"{base}/runtime/probe")
        if isinstance(probe, dict) and isinstance(probe.get("workflows"), dict):
            return probe
    except Exception:
        pass
    return _request("GET", f"{base}/runtime/containers")


def _int_metric(*values: object) -> int:
    for value in values:
        try:
            if value is not None:
                return int(value)
        except (TypeError, ValueError):
            continue
    return 0


def _validate_health(health: dict) -> None:
    _require(
        health.get("status") == "ok" and health.get("app") == "image_agent",
        "health identity check failed",
    )


def _validate_rag_thresholds(*, rag: dict, rag_after: dict, min_documents: int, min_chunks: int) -> None:
    index_after = rag_after.get("index") if isinstance(rag_after.get("index"), dict) else {}
    document_count = _int_metric(rag.get("document_count"), index_after.get("document_count"))
    chunk_count = _int_metric(rag.get("chunk_count"), index_after.get("chunk_count"))
    _require(rag.get("semantic_index") is True, "RAG semantic_index is not enabled after rebuild")
    _require(
        document_count >= min_documents,
        f"RAG document_count {document_count} below minimum {min_documents}",
    )
    _require(
        chunk_count >= min_chunks,
        f"RAG chunk_count {chunk_count} below minimum {min_chunks}",
    )


def _safe_rag_index_summary(index: object) -> dict | None:
    if not isinstance(index, dict):
        return None
    safe: dict = {}
    for key in ("engine",):
        value = index.get(key)
        if isinstance(value, str) and _is_privacy_safe_symbol(value):
            safe[key] = value
    for key in ("semantic_index",):
        if isinstance(index.get(key), bool):
            safe[key] = index[key]
    for key in ("document_count", "chunk_count"):
        value = _int_metric(index.get(key))
        if value >= 0:
            safe[key] = value

    hybrid = index.get("hybrid_search")
    if isinstance(hybrid, dict):
        safe_hybrid: dict = {}
        for key in (
            "engine",
            "mode",
            "index",
            "lexical_retriever",
            "vector_retriever",
            "dense_vector_field",
            "embedding_provider",
            "embedding_model",
            "embedding_transport",
            "fusion",
        ):
            value = hybrid.get(key)
            if isinstance(value, str) and _is_privacy_safe_symbol(value):
                safe_hybrid[key] = value
        for key in ("configured", "persisted", "embedding_endpoint_configured", "embedding_production_ready"):
            if isinstance(hybrid.get(key), bool):
                safe_hybrid[key] = hybrid[key]
        for key in ("indexed_chunk_count", "dense_vector_dims"):
            value = _int_metric(hybrid.get(key))
            if value >= 0:
                safe_hybrid[key] = value
        official_sources = hybrid.get("official_sources")
        if isinstance(official_sources, list):
            safe_hybrid["official_rrf_source_present"] = ELASTICSEARCH_RRF_SOURCE_URL in official_sources
        if safe_hybrid:
            safe["hybrid_search"] = safe_hybrid
    return safe


def _validate_raw_source_policy(rag_after: dict) -> None:
    raw = rag_after.get("vendor_raw_sources") if isinstance(rag_after.get("vendor_raw_sources"), dict) else {}
    _require(raw.get("manifest_exists") is True, "RAG raw-source policy failed: manifest is missing")
    _require(raw.get("manifest_schema_version") is not None, "RAG raw-source policy failed: manifest schema version missing")
    _require(_int_metric(raw.get("source_count")) > 0, "RAG raw-source policy failed: raw source count missing")
    _require(_int_metric(raw.get("vendor_doc_count")) > 0, "RAG raw-source policy failed: curated vendor doc count missing")
    _require(not raw.get("missing_files"), "RAG raw-source policy failed: missing raw-source files")
    _require(not raw.get("hash_mismatches"), "RAG raw-source policy failed: raw-source hash mismatches")
    _require(raw.get("raw_sources_indexed") is False, "RAG raw-source policy failed: raw sources are indexed")
    _require(not raw.get("indexed_raw_sources"), "RAG raw-source policy failed: indexed raw-source files")
    _require(
        raw.get("curated_provenance_ok") is not False and not raw.get("curated_provenance_issues"),
        "RAG raw-source policy failed: curated provenance issues",
    )
    curated_sources = raw.get("curated_sources")
    _require(isinstance(curated_sources, list) and curated_sources, "RAG raw-source policy failed: curated source coverage missing")
    _require(
        all(isinstance(item, dict) and item.get("complete") is True for item in curated_sources),
        "RAG raw-source policy failed: curated source coverage incomplete",
    )
    _require(
        all(
            isinstance(item, dict)
            and item.get("manifest_backed") is True
            and item.get("source_url_backed") is True
            and isinstance(item.get("source_types"), list)
            and bool(item.get("source_types"))
            for item in curated_sources
        ),
        "RAG raw-source policy failed: curated provenance pointer integrity incomplete",
    )


def _validate_vendor_pointer_integrity(rag_after: dict) -> dict:
    integrity = (
        rag_after.get("vendor_pointer_integrity")
        if isinstance(rag_after.get("vendor_pointer_integrity"), dict)
        else {}
    )
    _require(integrity.get("ok") is True, "RAG vendor pointer integrity failed: ok is not true")
    pointer_count = _int_metric(integrity.get("pointer_count"))
    issue_count = _int_metric(integrity.get("issue_count"))
    issues = integrity.get("issues")
    referenced_vendor_docs = integrity.get("referenced_vendor_docs")
    pointers_by_doc = integrity.get("pointers_by_doc")
    _require(pointer_count > 0, "RAG vendor pointer integrity failed: pointer count missing")
    _require(issue_count == 0, "RAG vendor pointer integrity failed: issue count is non-zero")
    _require(not issues, "RAG vendor pointer integrity failed: issues are present")
    _require(
        isinstance(referenced_vendor_docs, list)
        and referenced_vendor_docs
        and all(isinstance(item, str) and item.endswith(".md") and "/" not in item and "\\" not in item for item in referenced_vendor_docs),
        "RAG vendor pointer integrity failed: referenced vendor docs missing",
    )
    _require(
        isinstance(pointers_by_doc, dict)
        and pointers_by_doc
        and all(isinstance(key, str) and key.startswith("docs/rag/") for key in pointers_by_doc),
        "RAG vendor pointer integrity failed: pointers_by_doc incomplete",
    )
    flattened_vendor_paths = {
        value
        for values in pointers_by_doc.values()
        if isinstance(values, list)
        for value in values
        if isinstance(value, str)
    }
    _require(
        all(f"docs/rag/vendor/{doc}" in flattened_vendor_paths for doc in referenced_vendor_docs),
        "RAG vendor pointer integrity failed: pointers_by_doc does not cover referenced vendor docs",
    )
    _require(
        integrity.get("raw_source_manifest_exists") is True,
        "RAG vendor pointer integrity failed: raw-source manifest missing",
    )
    _require(
        integrity.get("curated_provenance_ok") is True,
        "RAG vendor pointer integrity failed: curated provenance not ok",
    )
    return {
        "status": "passed",
        "pointer_count": pointer_count,
        "issue_count": issue_count,
        "referenced_vendor_docs": referenced_vendor_docs,
        "pointers_by_doc": pointers_by_doc,
    }


def _validate_elasticsearch_hybrid_rag(rag_after: dict) -> dict:
    index = rag_after.get("index") if isinstance(rag_after.get("index"), dict) else {}
    hybrid = index.get("hybrid_search") if isinstance(index.get("hybrid_search"), dict) else {}
    _require(
        index.get("engine") == "elasticsearch_hybrid",
        "RAG Elasticsearch hybrid search is not active: index.engine must be elasticsearch_hybrid",
    )
    _require(
        hybrid.get("engine") == "elasticsearch",
        "RAG Elasticsearch hybrid search is not active: hybrid_search.engine must be elasticsearch",
    )
    _require(
        hybrid.get("persisted") is True,
        "RAG Elasticsearch hybrid search is not active: hybrid_search.persisted must be true",
    )
    _require(
        hybrid.get("configured") is True,
        "RAG Elasticsearch hybrid search is not active: hybrid_search.configured must be true",
    )
    _require(
        hybrid.get("mode") == "connected",
        "RAG Elasticsearch hybrid search is not active: hybrid_search.mode must be connected",
    )
    index_name = hybrid.get("index")
    _require(
        _is_privacy_safe_symbol(index_name),
        "RAG Elasticsearch hybrid search is not active: hybrid_search.index must be privacy-safe",
    )
    indexed_chunk_count = hybrid.get("indexed_chunk_count")
    _require(
        isinstance(indexed_chunk_count, int) and not isinstance(indexed_chunk_count, bool) and indexed_chunk_count > 0,
        "RAG Elasticsearch hybrid search is not active: indexed_chunk_count must be greater than zero",
    )
    _require(
        not hybrid.get("error"),
        "RAG Elasticsearch hybrid search is not active: hybrid_search.error must be absent",
    )
    _require(
        not hybrid.get("embedding_error"),
        "RAG Elasticsearch hybrid search is not active: embedding_error must be absent",
    )
    _require(
        hybrid.get("lexical_retriever") == "standard",
        "RAG Elasticsearch hybrid search is not active: lexical_retriever must be standard",
    )
    _require(
        hybrid.get("vector_retriever") == "knn",
        "RAG Elasticsearch hybrid search is not active: vector_retriever must be knn",
    )
    _require(
        hybrid.get("dense_vector_field") == "embedding",
        "RAG Elasticsearch hybrid search is not active: dense_vector_field must be embedding",
    )
    dense_vector_dims = hybrid.get("dense_vector_dims")
    _require(
        isinstance(dense_vector_dims, int) and not isinstance(dense_vector_dims, bool) and dense_vector_dims > 0,
        "RAG Elasticsearch hybrid search is not active: dense_vector_dims must be greater than zero",
    )
    embedding_provider = str(hybrid.get("embedding_provider") or "").strip()
    _require(
        embedding_provider and embedding_provider.lower() not in LOCAL_EMBEDDING_PROVIDERS,
        "RAG Elasticsearch hybrid search is not active: embedding_provider must be production configured",
    )
    embedding_model = str(hybrid.get("embedding_model") or "").strip()
    _require(
        embedding_model,
        "RAG Elasticsearch hybrid search is not active: embedding_model must be present",
    )
    embedding_transport = str(hybrid.get("embedding_transport") or "").strip()
    _require(
        embedding_transport,
        "RAG Elasticsearch hybrid search is not active: embedding_transport must be present",
    )
    _require(
        embedding_transport in {"sdk", "openai_compatible_http"},
        "RAG Elasticsearch hybrid search is not active: embedding_transport must be production-safe",
    )
    _require(
        hybrid.get("embedding_endpoint_configured") is True,
        "RAG Elasticsearch hybrid search is not active: embedding_endpoint_configured must be true",
    )
    _require(
        hybrid.get("embedding_production_ready") is True,
        "RAG Elasticsearch hybrid search is not active: embedding_production_ready must be true",
    )
    fusion, rrf_unavailable_reason = _validate_elasticsearch_fusion(
        hybrid,
        context="RAG Elasticsearch hybrid search is not active",
    )
    official_sources = hybrid.get("official_sources")
    _require(
        isinstance(official_sources, list) and ELASTICSEARCH_RRF_SOURCE_URL in official_sources,
        "RAG Elasticsearch hybrid search is not active: official_sources must include Elasticsearch RRF documentation",
    )
    return {
        "engine": hybrid.get("engine"),
        "configured": hybrid.get("configured"),
        "persisted": hybrid.get("persisted"),
        "mode": hybrid.get("mode"),
        "index": index_name,
        "indexed_chunk_count": indexed_chunk_count,
        "lexical_retriever": hybrid.get("lexical_retriever"),
        "vector_retriever": hybrid.get("vector_retriever"),
        "dense_vector_field": hybrid.get("dense_vector_field"),
        "dense_vector_dims": dense_vector_dims,
        "embedding_provider": embedding_provider,
        "embedding_model": embedding_model,
        "embedding_transport": embedding_transport,
        "embedding_endpoint_configured": hybrid.get("embedding_endpoint_configured") is True,
        "embedding_production_ready": hybrid.get("embedding_production_ready"),
        "fusion": fusion,
        "rrf_unavailable_reason": rrf_unavailable_reason,
        "official_rrf_source_present": True,
    }


def _validate_elasticsearch_hybrid_rebuild(rag_rebuild: dict, *, status_evidence: dict) -> dict:
    hybrid = rag_rebuild.get("hybrid_search") if isinstance(rag_rebuild.get("hybrid_search"), dict) else {}
    _require(
        hybrid.get("engine") == "elasticsearch",
        "RAG Elasticsearch hybrid rebuild evidence missing: hybrid_search.engine must be elasticsearch",
    )
    _require(
        hybrid.get("persisted") is True,
        "RAG Elasticsearch hybrid rebuild evidence missing: hybrid_search.persisted must be true",
    )
    _require(
        hybrid.get("configured") is True,
        "RAG Elasticsearch hybrid rebuild evidence missing: hybrid_search.configured must be true",
    )
    _require(
        hybrid.get("mode") == "connected",
        "RAG Elasticsearch hybrid rebuild evidence missing: hybrid_search.mode must be connected",
    )
    index_name = hybrid.get("index")
    _require(
        index_name == status_evidence.get("index"),
        "RAG Elasticsearch hybrid rebuild evidence mismatch: hybrid_search.index must match status",
    )
    indexed_chunk_count = hybrid.get("indexed_chunk_count")
    _require(
        isinstance(indexed_chunk_count, int) and not isinstance(indexed_chunk_count, bool) and indexed_chunk_count > 0,
        "RAG Elasticsearch hybrid rebuild evidence missing: indexed_chunk_count must be greater than zero",
    )
    _require(
        indexed_chunk_count == status_evidence.get("indexed_chunk_count"),
        "RAG Elasticsearch hybrid rebuild evidence mismatch: indexed_chunk_count must match status",
    )
    dense_vector_dims = hybrid.get("dense_vector_dims")
    _require(
        isinstance(dense_vector_dims, int) and not isinstance(dense_vector_dims, bool) and dense_vector_dims > 0,
        "RAG Elasticsearch hybrid rebuild evidence missing: dense_vector_dims must be greater than zero",
    )
    _require(
        dense_vector_dims == status_evidence.get("dense_vector_dims"),
        "RAG Elasticsearch hybrid rebuild evidence mismatch: dense_vector_dims must match status",
    )
    _require(
        hybrid.get("lexical_retriever") == status_evidence.get("lexical_retriever"),
        "RAG Elasticsearch hybrid rebuild evidence mismatch: lexical_retriever must match status",
    )
    _require(
        hybrid.get("vector_retriever") == status_evidence.get("vector_retriever"),
        "RAG Elasticsearch hybrid rebuild evidence mismatch: vector_retriever must match status",
    )
    _require(
        hybrid.get("dense_vector_field") == status_evidence.get("dense_vector_field"),
        "RAG Elasticsearch hybrid rebuild evidence mismatch: dense_vector_field must match status",
    )
    _require(
        not hybrid.get("error"),
        "RAG Elasticsearch hybrid rebuild evidence missing: hybrid_search.error must be absent",
    )
    _require(
        not hybrid.get("embedding_error"),
        "RAG Elasticsearch hybrid rebuild evidence missing: embedding_error must be absent",
    )
    _require(
        hybrid.get("embedding_provider") == status_evidence.get("embedding_provider"),
        "RAG Elasticsearch hybrid rebuild evidence mismatch: embedding_provider must match status",
    )
    embedding_model = str(hybrid.get("embedding_model") or "").strip()
    _require(
        embedding_model,
        "RAG Elasticsearch hybrid rebuild evidence missing: embedding_model must be present",
    )
    _require(
        embedding_model == status_evidence.get("embedding_model"),
        "RAG Elasticsearch hybrid rebuild evidence mismatch: embedding_model must match status",
    )
    embedding_transport = str(hybrid.get("embedding_transport") or "").strip()
    _require(
        embedding_transport,
        "RAG Elasticsearch hybrid rebuild evidence missing: embedding_transport must be present",
    )
    _require(
        embedding_transport == status_evidence.get("embedding_transport"),
        "RAG Elasticsearch hybrid rebuild evidence mismatch: embedding_transport must match status",
    )
    _require(
        embedding_transport in {"sdk", "openai_compatible_http"},
        "RAG Elasticsearch hybrid rebuild evidence missing: embedding_transport must be production-safe",
    )
    _require(
        hybrid.get("embedding_endpoint_configured") is True,
        "RAG Elasticsearch hybrid rebuild evidence missing: embedding_endpoint_configured must be true",
    )
    _require(
        status_evidence.get("embedding_endpoint_configured") is True,
        "RAG Elasticsearch hybrid rebuild evidence mismatch: status embedding_endpoint_configured must be true",
    )
    _require(
        (hybrid.get("embedding_endpoint_configured") is True)
        == (status_evidence.get("embedding_endpoint_configured") is True),
        "RAG Elasticsearch hybrid rebuild evidence mismatch: embedding_endpoint_configured must match status",
    )
    _require(
        hybrid.get("embedding_production_ready") is True,
        "RAG Elasticsearch hybrid rebuild evidence missing: embedding_production_ready must be true",
    )
    _require(
        hybrid.get("fusion") == status_evidence.get("fusion"),
        "RAG Elasticsearch hybrid rebuild evidence mismatch: fusion must match status",
    )
    _require(
        _rrf_unavailable_reason(hybrid) == (status_evidence.get("rrf_unavailable_reason") or ""),
        "RAG Elasticsearch hybrid rebuild evidence mismatch: rrf_unavailable_reason must match status",
    )
    return {
        "engine": hybrid.get("engine"),
        "configured": hybrid.get("configured"),
        "persisted": hybrid.get("persisted"),
        "mode": hybrid.get("mode"),
        "index": index_name,
        "indexed_chunk_count": indexed_chunk_count,
        "lexical_retriever": hybrid.get("lexical_retriever"),
        "vector_retriever": hybrid.get("vector_retriever"),
        "dense_vector_field": hybrid.get("dense_vector_field"),
        "dense_vector_dims": dense_vector_dims,
        "embedding_provider": hybrid.get("embedding_provider"),
        "embedding_model": embedding_model,
        "embedding_transport": embedding_transport,
        "embedding_endpoint_configured": hybrid.get("embedding_endpoint_configured") is True,
        "embedding_production_ready": hybrid.get("embedding_production_ready"),
        "fusion": hybrid.get("fusion"),
        "rrf_unavailable_reason": status_evidence.get("rrf_unavailable_reason"),
    }


def _validate_elasticsearch_hybrid_query_evidence(response: dict, *, status_evidence: dict) -> dict:
    mode = response.get("retrieval_mode")
    _require(
        mode == "elasticsearch_hybrid",
        "RAG Elasticsearch hybrid query did not use Elasticsearch retrieval: retrieval_mode must be elasticsearch_hybrid",
    )
    retrieval_source = response.get("retrieval_source")
    _require(
        retrieval_source == "elasticsearch_hybrid",
        "RAG Elasticsearch hybrid query did not use Elasticsearch retrieval: retrieval_source must be elasticsearch_hybrid",
    )
    citations = response.get("citations") if isinstance(response.get("citations"), list) else []
    sources = [
        str(item.get("source") or item.get("path") or "")
        for item in citations
        if isinstance(item, dict)
    ]
    _require(
        ELASTICSEARCH_HYBRID_CONTRACT_SOURCE in sources,
        "RAG Elasticsearch hybrid query did not cite the Elasticsearch hybrid contract",
    )
    scores = []
    for item in citations:
        if not isinstance(item, dict):
            continue
        try:
            scores.append(float(item.get("score")))
        except (TypeError, ValueError):
            continue
    top_score = max(scores) if scores else 0.0
    _require(
        top_score > 0,
        "RAG Elasticsearch hybrid query evidence missing positive score",
    )
    query_evidence = (
        response.get("elasticsearch_hybrid_query")
        if isinstance(response.get("elasticsearch_hybrid_query"), dict)
        else {}
    )
    index_name = query_evidence.get("index")
    _require(
        _is_privacy_safe_symbol(index_name),
        "RAG Elasticsearch hybrid query evidence missing: index must be privacy-safe",
    )
    _require(
        index_name == status_evidence.get("index"),
        "RAG Elasticsearch hybrid query evidence mismatch: index must match status",
    )
    lexical_retriever = str(query_evidence.get("lexical_retriever") or "").strip()
    _require(
        lexical_retriever == "standard",
        "RAG Elasticsearch hybrid query evidence missing: lexical_retriever must be standard",
    )
    _require(
        lexical_retriever == status_evidence.get("lexical_retriever"),
        "RAG Elasticsearch hybrid query evidence mismatch: lexical_retriever must match status",
    )
    vector_retriever = str(query_evidence.get("vector_retriever") or "").strip()
    _require(
        vector_retriever == "knn",
        "RAG Elasticsearch hybrid query evidence missing: vector_retriever must be knn",
    )
    _require(
        vector_retriever == status_evidence.get("vector_retriever"),
        "RAG Elasticsearch hybrid query evidence mismatch: vector_retriever must match status",
    )
    dense_vector_field = str(query_evidence.get("dense_vector_field") or "").strip()
    _require(
        dense_vector_field == "embedding",
        "RAG Elasticsearch hybrid query evidence missing: dense_vector_field must be embedding",
    )
    _require(
        dense_vector_field == status_evidence.get("dense_vector_field"),
        "RAG Elasticsearch hybrid query evidence mismatch: dense_vector_field must match status",
    )
    fusion, rrf_unavailable_reason = _validate_elasticsearch_fusion(
        query_evidence,
        context="RAG Elasticsearch hybrid query evidence missing",
    )
    _require(
        fusion == status_evidence.get("fusion"),
        "RAG Elasticsearch hybrid query evidence mismatch: fusion must match status",
    )
    _require(
        (rrf_unavailable_reason or "") == (status_evidence.get("rrf_unavailable_reason") or ""),
        "RAG Elasticsearch hybrid query evidence mismatch: rrf_unavailable_reason must match status",
    )
    dense_vector_dims = query_evidence.get("dense_vector_dims")
    _require(
        isinstance(dense_vector_dims, int) and not isinstance(dense_vector_dims, bool) and dense_vector_dims > 0,
        "RAG Elasticsearch hybrid query evidence missing: dense_vector_dims must be greater than zero",
    )
    _require(
        dense_vector_dims == status_evidence.get("dense_vector_dims"),
        "RAG Elasticsearch hybrid query evidence mismatch: dense_vector_dims must match status",
    )
    embedding_provider = str(query_evidence.get("embedding_provider") or "").strip()
    _require(
        embedding_provider and _is_privacy_safe_symbol(embedding_provider),
        "RAG Elasticsearch hybrid query evidence missing: embedding_provider must be privacy-safe",
    )
    _require(
        embedding_provider == status_evidence.get("embedding_provider"),
        "RAG Elasticsearch hybrid query evidence mismatch: embedding_provider must match status",
    )
    embedding_model = str(query_evidence.get("embedding_model") or "").strip()
    _require(
        embedding_model and _is_privacy_safe_symbol(embedding_model),
        "RAG Elasticsearch hybrid query evidence missing: embedding_model must be privacy-safe",
    )
    _require(
        embedding_model == status_evidence.get("embedding_model"),
        "RAG Elasticsearch hybrid query evidence mismatch: embedding_model must match status",
    )
    embedding_transport = str(query_evidence.get("embedding_transport") or "").strip()
    _require(
        embedding_transport and _is_privacy_safe_symbol(embedding_transport),
        "RAG Elasticsearch hybrid query evidence missing: embedding_transport must be privacy-safe",
    )
    _require(
        embedding_transport == status_evidence.get("embedding_transport"),
        "RAG Elasticsearch hybrid query evidence mismatch: embedding_transport must match status",
    )
    _require(
        query_evidence.get("embedding_endpoint_configured") is True,
        "RAG Elasticsearch hybrid query evidence missing: embedding_endpoint_configured must be true",
    )
    _require(
        status_evidence.get("embedding_endpoint_configured") is True,
        "RAG Elasticsearch hybrid query evidence mismatch: status embedding_endpoint_configured must be true",
    )
    _require(
        query_evidence.get("embedding_production_ready") is True,
        "RAG Elasticsearch hybrid query evidence missing: embedding_production_ready must be true",
    )
    return {
        "status": "passed",
        "mode": mode,
        "retrieval_source": retrieval_source,
        "source": ELASTICSEARCH_HYBRID_CONTRACT_SOURCE,
        "citation_count": len(citations),
        "top_score": top_score,
        "index": index_name,
        "lexical_retriever": lexical_retriever,
        "vector_retriever": vector_retriever,
        "dense_vector_field": dense_vector_field,
        "fusion": fusion,
        "rrf_unavailable_reason": rrf_unavailable_reason,
        "dense_vector_dims": dense_vector_dims,
        "embedding_provider": embedding_provider,
        "embedding_model": embedding_model,
        "embedding_transport": embedding_transport,
        "embedding_endpoint_configured": query_evidence.get("embedding_endpoint_configured") is True,
        "embedding_production_ready": query_evidence.get("embedding_production_ready") is True,
    }


def _summarize_vendor_coverage_catalog(rag_after: dict) -> dict:
    raw = rag_after.get("vendor_raw_sources") if isinstance(rag_after.get("vendor_raw_sources"), dict) else {}
    catalog = (
        rag_after.get("vendor_coverage_catalog")
        if isinstance(rag_after.get("vendor_coverage_catalog"), dict)
        else {}
    )
    if catalog.get("status") == "complete":
        _validate_vendor_coverage_catalog(catalog, raw)
    return {
        "catalog": catalog,
        "status": str(catalog.get("status") or "missing"),
        "vendor_doc_count": _int_metric(catalog.get("vendor_doc_count")),
        "complete_vendor_doc_count": _int_metric(catalog.get("complete_vendor_doc_count")),
        "incomplete_vendor_doc_count": _int_metric(catalog.get("incomplete_vendor_doc_count")),
        "raw_source_count": _int_metric(catalog.get("raw_source_count")),
    }


def _vendor_docs_from_curated_sources(raw: dict) -> set[str]:
    curated_sources = raw.get("curated_sources")
    if not isinstance(curated_sources, list):
        return set()
    return {
        item.get("vendor_doc")
        for item in curated_sources
        if isinstance(item, dict) and isinstance(item.get("vendor_doc"), str)
    }


def _validate_vendor_coverage_catalog(catalog: dict, raw: dict) -> None:
    vendors = catalog.get("vendors")
    _require(isinstance(vendors, list) and vendors, "RAG vendor coverage catalog failed: vendors missing")
    vendor_docs = {
        vendor.get("vendor_doc")
        for vendor in vendors
        if isinstance(vendor, dict) and isinstance(vendor.get("vendor_doc"), str)
    }
    curated_docs = _vendor_docs_from_curated_sources(raw)
    _require(curated_docs, "RAG vendor coverage catalog failed: curated_sources missing")
    _require(
        vendor_docs == curated_docs,
        "RAG vendor coverage catalog failed: vendors must match curated_sources",
    )
    _require(
        _int_metric(catalog.get("vendor_doc_count")) == len(vendor_docs) == _int_metric(raw.get("vendor_doc_count")),
        "RAG vendor coverage catalog failed: vendor_doc_count mismatch",
    )
    _require(
        _int_metric(catalog.get("raw_source_count")) == _int_metric(raw.get("source_count")),
        "RAG vendor coverage catalog failed: raw_source_count mismatch",
    )


def _collect_source_markers(value: object, *, in_source_field: bool = False) -> list[str]:
    markers = []
    if isinstance(value, dict):
        for key, nested in value.items():
            source_field = key in SOURCE_MARKER_KEYS or str(key).endswith("_source")
            if source_field and isinstance(nested, str):
                markers.append(nested)
                continue
            markers.extend(_collect_source_markers(nested, in_source_field=source_field))
    elif isinstance(value, list):
        for nested in value:
            markers.extend(_collect_source_markers(nested, in_source_field=in_source_field))
    elif isinstance(value, str) and in_source_field:
        markers.append(value)
    return markers


def _validate_launchability_matrix_evidence(rag_after: dict) -> dict:
    for marker in _collect_source_markers(rag_after):
        normalized = marker.replace("\\", "/")
        if normalized.endswith(LAUNCHABILITY_MATRIX_SOURCE):
            return {"status": "passed", "source": marker}
    raise SystemExit("RAG launchability matrix evidence missing")


def _validate_launchability_query_evidence(query_response: dict) -> dict:
    intent = query_response.get("intent") or query_response.get("agent_intent")
    _require(intent == "launchability", "RAG launchability query intent failed")
    for marker in _collect_source_markers(query_response):
        normalized = marker.replace("\\", "/")
        if normalized.endswith(LAUNCHABILITY_MATRIX_SOURCE):
            return {"status": "passed", "intent": intent, "source": marker}
    raise SystemExit("RAG launchability matrix query citation missing")


def _validate_agent_run(run: dict) -> None:
    _require(bool(run.get("agent_run_id")), "agent run smoke failed: missing agent_run_id")
    _require(run.get("status") == "answered", f"agent run smoke failed: status={run.get('status')}")
    _require(bool(run.get("intent") or run.get("agent_intent")), "agent run smoke failed: missing intent")
    _require(bool(run.get("selected_skill")), "agent run smoke failed: missing selected_skill")
    safe_metadata = run.get("safe_metadata") if isinstance(run.get("safe_metadata"), dict) else {}
    _require(
        safe_metadata.get("fallback_reason") != "model_gateway_unconfigured",
        "agent run smoke failed: model gateway fallback was used",
    )
    _require(
        run.get("selected_skill") != "backend-status-fallback",
        "agent run smoke failed: model gateway fallback was used",
    )
    _require(
        _is_privacy_safe_symbol(run.get("model_gateway_access")),
        "agent run smoke failed: missing model_gateway_access",
    )


def _safe_agent_metadata(run: dict | None) -> dict:
    if not run or not isinstance(run.get("safe_metadata"), dict):
        return {}
    safe: dict = {}
    for key, value in run["safe_metadata"].items():
        if (
            isinstance(key, str)
            and _is_privacy_safe_symbol(key)
            and (
                value is None
                or isinstance(value, bool)
                or (isinstance(value, int) and not isinstance(value, bool))
                or (isinstance(value, str) and _is_privacy_safe_symbol(value))
            )
        ):
            safe[key] = value
    return safe


def _safe_workflow_metadata(metadata: object, *, workflow_type: str) -> dict | None:
    if not isinstance(metadata, dict):
        return None
    metadata_workflow_type = metadata.get("workflow_type")
    if metadata_workflow_type != workflow_type or not _is_privacy_safe_symbol(metadata_workflow_type):
        return None
    safe: dict = {"workflow_type": metadata_workflow_type}
    runtime_workflow_type = metadata.get("runtime_workflow_type")
    if isinstance(runtime_workflow_type, str) and _is_privacy_safe_symbol(runtime_workflow_type):
        safe["runtime_workflow_type"] = runtime_workflow_type
    for key in ("workflow_family", "workflow_role"):
        value = metadata.get(key)
        if isinstance(value, str) and _is_privacy_safe_symbol(value):
            safe[key] = value
    display_name = metadata.get("display_name")
    if isinstance(display_name, str) and 0 < len(display_name) <= 160 and display_name != workflow_type:
        safe["display_name"] = display_name
    capability_summary = metadata.get("capability_summary")
    if isinstance(capability_summary, str) and _safe_human_text(capability_summary, max_len=320):
        safe["capability_summary"] = capability_summary
    for key in ("primary_outputs", "qc_outputs", "report_outputs", "limitations"):
        values = _safe_text_list(metadata.get(key), max_items=8, max_len=160)
        if values is not None:
            safe[key] = values
    stages = _safe_pipeline_stages(metadata.get("pipeline_stages"))
    if stages is not None:
        safe["pipeline_stages"] = stages
    is_report_only = metadata.get("is_report_only")
    if isinstance(is_report_only, bool):
        safe["is_report_only"] = is_report_only
    agent_selectable = metadata.get("agent_selectable")
    if isinstance(agent_selectable, bool):
        safe["agent_selectable"] = agent_selectable
    return safe


def _safe_human_text(value: str, *, max_len: int) -> bool:
    if not value or len(value) > max_len:
        return False
    lowered = value.lower()
    if "://" in value or "\\" in value or any(token in lowered for token in ("/home/", "/users/", "/tmp/", "/var/")):
        return False
    return True


def _safe_text_list(value: object, *, max_items: int, max_len: int) -> list[str] | None:
    if not isinstance(value, list):
        return None
    safe_items: list[str] = []
    for item in value[:max_items]:
        if isinstance(item, str) and _safe_human_text(item, max_len=max_len):
            safe_items.append(item)
    return safe_items


def _safe_pipeline_stages(value: object) -> list[dict] | None:
    if not isinstance(value, list):
        return None
    stages: list[dict] = []
    for item in value[:8]:
        if not isinstance(item, dict):
            continue
        name = item.get("name")
        purpose = item.get("purpose")
        if isinstance(name, str) and isinstance(purpose, str) and _safe_human_text(name, max_len=80) and _safe_human_text(purpose, max_len=220):
            stages.append({"name": name, "purpose": purpose})
    return stages


def _validate_agent_project_context(run: dict, project_id: int) -> None:
    _require(
        _int_metric(run.get("project_id")) == project_id,
        "agent run project context failed: project_id mismatch",
    )


def _validate_agent_workflow_confirmation(
    run: dict,
    *,
    project_id: int,
    series_id: int,
    workflow_type: str,
) -> dict:
    _require(bool(run.get("agent_run_id")), "agent workflow confirmation failed: missing agent_run_id")
    _require(
        run.get("status") == "confirmation_required",
        f"agent workflow confirmation failed: status={run.get('status')}",
    )
    _require(
        (run.get("intent") or run.get("agent_intent")) == "run_workflow",
        "agent workflow confirmation failed: intent mismatch",
    )
    _require(
        run.get("selected_skill") == "image-agent-workflow-runner",
        "agent workflow confirmation failed: selected_skill mismatch",
    )
    confirmation = run.get("confirmation") if isinstance(run.get("confirmation"), dict) else {}
    confirmed_project_id = _int_metric(confirmation.get("project_id"), run.get("project_id"))
    confirmed_series_id = _int_metric(confirmation.get("series_id"), run.get("series_id"))
    confirmed_workflow_type = confirmation.get("workflow_type") or run.get("workflow_type")
    _require(confirmed_project_id == project_id, "agent workflow confirmation failed: project_id mismatch")
    _require(confirmed_series_id == series_id, "agent workflow confirmation failed: series_id mismatch")
    _require(
        confirmed_workflow_type == workflow_type and _is_privacy_safe_symbol(confirmed_workflow_type),
        "agent workflow confirmation failed: workflow_type mismatch",
    )
    production_task_created = run.get("production_task_created")
    if production_task_created is None and isinstance(run.get("safe_metadata"), dict):
        production_task_created = run["safe_metadata"].get("production_task_created")
    if production_task_created is None and confirmation:
        production_task_created = confirmation.get("production_task_created")
    _require(
        production_task_created is False,
        "agent workflow confirmation failed: production_task_created must be false",
    )
    workflow_metadata = _safe_workflow_metadata(
        confirmation.get("workflow_metadata"),
        workflow_type=confirmed_workflow_type,
    )
    _require(
        workflow_metadata is not None,
        "agent workflow confirmation failed: workflow_metadata missing",
    )
    _require(
        workflow_metadata.get("agent_selectable") is True,
        "agent workflow confirmation failed: workflow_metadata agent_selectable invalid",
    )
    runtime_workflow_type = workflow_metadata.get("runtime_workflow_type") if workflow_metadata else None
    return {
        "agent_run_id": run["agent_run_id"],
        "status": "confirmation_required",
        "intent": "run_workflow",
        "project_id": confirmed_project_id,
        "series_id": confirmed_series_id,
        "workflow_type": confirmed_workflow_type,
        **({"runtime_workflow_type": runtime_workflow_type} if runtime_workflow_type else {}),
        **({"workflow_metadata": workflow_metadata} if workflow_metadata else {}),
        "selected_skill": run.get("selected_skill"),
        "production_task_created": False,
    }


def _validate_agent_workflow_resume(
    resume: dict,
    *,
    thread_id: str,
    project_id: int,
    series_id: int,
    workflow_type: str,
) -> dict:
    _require(bool(resume.get("agent_run_id")), "agent workflow resume failed: missing agent_run_id")
    _require(resume.get("thread_id") == thread_id, "agent workflow resume failed: thread_id mismatch")
    _require(resume.get("status") == "task_created", f"agent workflow resume failed: status={resume.get('status')}")
    task = resume.get("task") if isinstance(resume.get("task"), dict) else {}
    task_id = _int_metric(task.get("id"), task.get("task_id"))
    _require(task_id is not None and task_id > 0, "agent workflow resume failed: task_id missing")
    task_project_id = _int_metric(task.get("project_id"), resume.get("project_id"))
    task_series_id = _int_metric(task.get("series_id"))
    task_workflow_type = task.get("workflow_type")
    runtime_workflow_type = task.get("runtime_workflow_type")
    _require(task_project_id == project_id, "agent workflow resume failed: project_id mismatch")
    _require(task_series_id == series_id, "agent workflow resume failed: series_id mismatch")
    _require(
        task_workflow_type == workflow_type and _is_privacy_safe_symbol(task_workflow_type),
        "agent workflow resume failed: workflow_type mismatch",
    )
    _require(
        isinstance(runtime_workflow_type, str) and bool(runtime_workflow_type),
        "agent workflow resume failed: runtime_workflow_type missing",
    )
    _require(
        _is_privacy_safe_symbol(runtime_workflow_type),
        "agent workflow resume failed: runtime_workflow_type invalid",
    )
    initial_status = task.get("status")
    _require(
        isinstance(initial_status, str) and _is_privacy_safe_symbol(initial_status),
        "agent workflow resume failed: task status invalid",
    )
    production_task_created = resume.get("production_task_created")
    if production_task_created is None and isinstance(resume.get("safe_metadata"), dict):
        production_task_created = resume["safe_metadata"].get("production_task_created")
    _require(production_task_created is True, "agent workflow resume failed: production_task_created must be true")
    safe_metadata = resume.get("safe_metadata") if isinstance(resume.get("safe_metadata"), dict) else {}
    confirmation_gate = safe_metadata.get("confirmation_gate")
    _require(
        confirmation_gate == "fingerprint_verified",
        "agent workflow resume failed: confirmation_gate must be fingerprint_verified",
    )
    return {
        "agent_run_id": resume["agent_run_id"],
        "thread_id": thread_id,
        "status": "task_created",
        "project_id": task_project_id,
        "series_id": task_series_id,
        "workflow_type": task_workflow_type,
        **({"runtime_workflow_type": runtime_workflow_type} if runtime_workflow_type else {}),
        "task_id": task_id,
        "initial_status": initial_status,
        "production_task_created": True,
        "confirmation_gate": confirmation_gate,
    }


def _tampered_confirmation_payload(confirmation: dict, *, original_series_id: int) -> dict:
    tampered = dict(confirmation)
    tampered["series_id"] = original_series_id + 998 if original_series_id > 0 else 999
    return tampered


def _validate_agent_workflow_fingerprint_negative(
    resume: dict,
    *,
    thread_id: str,
) -> dict:
    _require(bool(resume.get("agent_run_id")), "agent workflow fingerprint negative failed: missing agent_run_id")
    _require(resume.get("thread_id") == thread_id, "agent workflow fingerprint negative failed: thread_id mismatch")
    _require(
        resume.get("status") == "blocked",
        f"agent workflow fingerprint negative failed: status={resume.get('status')}",
    )
    production_task_created = resume.get("production_task_created")
    if production_task_created is None and isinstance(resume.get("safe_metadata"), dict):
        production_task_created = resume["safe_metadata"].get("production_task_created")
    _require(
        production_task_created is False,
        "agent workflow fingerprint negative failed: production_task_created must be false",
    )
    safe_metadata = resume.get("safe_metadata") if isinstance(resume.get("safe_metadata"), dict) else {}
    confirmation_gate = safe_metadata.get("confirmation_gate")
    _require(
        confirmation_gate == "fingerprint_mismatch",
        "agent workflow fingerprint negative failed: confirmation_gate must be fingerprint_mismatch",
    )
    task = resume.get("task") if isinstance(resume.get("task"), dict) else {}
    _require(not task.get("id") and not task.get("task_id"), "agent workflow fingerprint negative failed: task must not be created")
    return {
        "agent_run_id": resume["agent_run_id"],
        "thread_id": thread_id,
        "status": "blocked",
        "production_task_created": False,
        "confirmation_gate": confirmation_gate,
        "task_created": False,
    }


def _json_object(value: object) -> dict:
    if not isinstance(value, str) or not value.strip():
        return {}
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _load_persisted_agent_launch_evidence(
    db_path: Path,
    *,
    task: dict,
    task_id: int,
    project_id: int,
    series_id: int,
    workflow_type: str,
) -> dict:
    if not db_path.exists():
        raise SystemExit(f"persisted agent launch evidence db not found: {db_path}")
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    resume_row = conn.execute(
        """
        select agent_run_id, thread_id, project_id, series_id, task_id, workflow_type, status, safe_metadata_json
        from agent_runs
        where request_type = 'resume'
          and task_id = ?
          and project_id = ?
          and series_id = ?
          and workflow_type = ?
          and status = 'task_created'
        order by created_at desc
        limit 1
        """,
        (task_id, project_id, series_id, workflow_type),
    ).fetchone()
    _require(resume_row is not None, "persisted agent launch evidence missing task_created resume run")
    thread_id = resume_row["thread_id"]
    _require(isinstance(thread_id, str) and bool(thread_id), "persisted agent launch evidence missing thread_id")
    confirmation_row = conn.execute(
        """
        select thread_id, project_id, series_id, workflow_type, selected_skill, confirmation_json
        from agent_confirmations
        where thread_id = ?
          and project_id = ?
          and series_id = ?
          and workflow_type = ?
          and consumed_at is not null
        order by consumed_at desc
        limit 1
        """,
        (thread_id, project_id, series_id, workflow_type),
    ).fetchone()
    _require(confirmation_row is not None, "persisted agent launch evidence missing consumed confirmation")
    prepare_row = conn.execute(
        """
        select agent_run_id, intent, selected_skill, safe_metadata_json
        from agent_runs
        where request_type = 'run'
          and thread_id = ?
          and project_id = ?
          and series_id = ?
          and workflow_type = ?
          and status = 'confirmation_required'
        order by created_at desc
        limit 1
        """,
        (thread_id, project_id, series_id, workflow_type),
    ).fetchone()
    _require(prepare_row is not None, "persisted agent launch evidence missing confirmation run")
    negative_row = conn.execute(
        """
        select agent_run_id, thread_id, status, safe_metadata_json
        from agent_runs
        where request_type = 'resume'
          and project_id = ?
          and workflow_type = ?
          and status = 'blocked'
        order by created_at desc
        limit 1
        """,
        (project_id, workflow_type),
    ).fetchone()
    _require(negative_row is not None, "persisted agent launch evidence missing fingerprint mismatch resume")

    confirmation_payload = _json_object(confirmation_row["confirmation_json"])
    confirmation_run = {
        "agent_run_id": prepare_row["agent_run_id"],
        "status": "confirmation_required",
        "intent": prepare_row["intent"] or "run_workflow",
        "project_id": confirmation_row["project_id"],
        "series_id": confirmation_row["series_id"],
        "workflow_type": confirmation_row["workflow_type"],
        "selected_skill": confirmation_row["selected_skill"] or prepare_row["selected_skill"],
        "production_task_created": False,
        "confirmation": confirmation_payload,
    }
    resume_metadata = _json_object(resume_row["safe_metadata_json"])
    resume_payload = {
        "agent_run_id": resume_row["agent_run_id"],
        "thread_id": thread_id,
        "status": "task_created",
        "project_id": resume_row["project_id"],
        "production_task_created": bool(resume_metadata.get("production_task_created")),
        "safe_metadata": resume_metadata,
        "task": task,
    }
    negative_metadata = _json_object(negative_row["safe_metadata_json"])
    negative_payload = {
        "agent_run_id": negative_row["agent_run_id"],
        "thread_id": negative_row["thread_id"],
        "status": negative_row["status"],
        "production_task_created": bool(negative_metadata.get("production_task_created")),
        "safe_metadata": negative_metadata,
        "task": {},
    }
    agent_workflow_confirmation = _validate_agent_workflow_confirmation(
        confirmation_run,
        project_id=project_id,
        series_id=series_id,
        workflow_type=workflow_type,
    )
    agent_workflow_resume = _validate_agent_workflow_resume(
        resume_payload,
        thread_id=thread_id,
        project_id=project_id,
        series_id=series_id,
        workflow_type=workflow_type,
    )
    agent_workflow_fingerprint_negative = _validate_agent_workflow_fingerprint_negative(
        negative_payload,
        thread_id=negative_row["thread_id"],
    )
    launched_task = {
        "task_id": agent_workflow_resume["task_id"],
        "project_id": agent_workflow_resume["project_id"],
        "series_id": agent_workflow_resume["series_id"],
        "workflow_type": agent_workflow_resume["workflow_type"],
        **(
            {"runtime_workflow_type": agent_workflow_resume["runtime_workflow_type"]}
            if agent_workflow_resume.get("runtime_workflow_type")
            else {}
        ),
        "launch_source": "agent_workflow_resume",
        "initial_status": task.get("status") or agent_workflow_resume["initial_status"],
    }
    return {
        "agent_workflow_confirmation": agent_workflow_confirmation,
        "agent_workflow_resume": agent_workflow_resume,
        "agent_workflow_fingerprint_negative": agent_workflow_fingerprint_negative,
        "launched_task": launched_task,
    }


def _validate_unknown_workflow_incubation(run: dict) -> dict:
    _require(isinstance(run, dict), "unknown workflow incubation failed: response must be an object")
    _require(bool(run.get("agent_run_id")), "unknown workflow incubation failed: missing agent_run_id")
    _require(_is_privacy_safe_symbol(run.get("agent_run_id")), "unknown workflow incubation failed: agent_run_id invalid")
    thread_id = run.get("thread_id")
    _require(
        thread_id is None or (isinstance(thread_id, str) and _is_privacy_safe_symbol(thread_id)),
        "unknown workflow incubation failed: thread_id invalid",
    )
    _require(
        run.get("status") == "toolchain_proposed",
        f"unknown workflow incubation failed: status={run.get('status')}",
    )
    action_lane = run.get("action_lane")
    if action_lane is None and isinstance(run.get("safe_metadata"), dict):
        action_lane = run["safe_metadata"].get("action_lane") or run["safe_metadata"].get("lane")
    _require(
        action_lane == "toolchain_incubation",
        "unknown workflow incubation failed: action_lane must be toolchain_incubation",
    )
    _require(run.get("production_task_created") is False, "unknown workflow incubation failed: production_task_created must be false")
    task = run.get("task") if isinstance(run.get("task"), dict) else {}
    task_created = bool(run.get("task_created")) or bool(run.get("task_id")) or bool(task.get("id")) or bool(task.get("task_id"))
    _require(not task_created, "unknown workflow incubation failed: task must not be created")
    confirmation = run.get("confirmation") if isinstance(run.get("confirmation"), dict) else None
    _require(confirmation is None, "unknown workflow incubation failed: confirmation must not be created")
    _require(
        run.get("task_creation_allowed") is False,
        "unknown workflow incubation failed: task_creation_allowed must be false",
    )
    forbidden_actions = run.get("forbidden_actions")
    if not isinstance(forbidden_actions, list) and isinstance(run.get("proposed_toolchain"), dict):
        forbidden_actions = run["proposed_toolchain"].get("forbidden_actions")
    _require(
        isinstance(forbidden_actions, list)
        and {"confirmation_creation", "production_task_creation", "pipeline_runner_launch"}.issubset(
            set(forbidden_actions)
        ),
        "unknown workflow incubation failed: forbidden_actions must include confirmation_creation, production_task_creation, and pipeline_runner_launch",
    )
    proposal = run.get("proposed_toolchain") if isinstance(run.get("proposed_toolchain"), dict) else {}
    proposal_id = proposal.get("proposal_id") or run.get("proposal_id")
    _require(
        isinstance(proposal_id, str) and _is_privacy_safe_symbol(proposal_id),
        "unknown workflow incubation failed: proposal_id missing or invalid",
    )
    proposal_status = proposal.get("status")
    _require(
        proposal_status is None or _is_privacy_safe_symbol(proposal_status),
        "unknown workflow incubation failed: proposal status invalid",
    )
    proposal_contract_version = proposal.get("contract_version")
    _require(
        proposal_contract_version is None or _is_privacy_safe_symbol(proposal_contract_version),
        "unknown workflow incubation failed: proposal contract_version invalid",
    )
    proposal_promotion_status = proposal.get("promotion_status")
    _require(
        proposal_promotion_status is None or _is_privacy_safe_symbol(proposal_promotion_status),
        "unknown workflow incubation failed: proposal promotion_status invalid",
    )
    proposal_production_task_created = proposal.get("production_task_created")
    if proposal_production_task_created is None:
        proposal_production_task_created = False
    _require(
        proposal_production_task_created is False,
        "unknown workflow incubation failed: proposal production_task_created must be false",
    )
    proposal_task_creation_allowed = proposal.get("task_creation_allowed")
    if proposal_task_creation_allowed is not None:
        _require(
            proposal_task_creation_allowed is False,
            "unknown workflow incubation failed: proposal task_creation_allowed must be false",
        )
    return {
        "agent_run_id": run["agent_run_id"],
        "thread_id": thread_id,
        "status": "toolchain_proposed",
        "action_lane": "toolchain_incubation",
        "proposal_id": proposal_id,
        **({"proposal_status": proposal_status} if proposal_status else {}),
        **({"proposal_contract_version": proposal_contract_version} if proposal_contract_version else {}),
        **({"proposal_promotion_status": proposal_promotion_status} if proposal_promotion_status else {}),
        "task_created": False,
        "confirmation_created": False,
        "task_creation_allowed": False,
        "forbidden_actions": ["confirmation_creation", "production_task_creation", "pipeline_runner_launch"],
        "production_task_created": False,
        "proposal_production_task_created": False,
    }


def _validate_completed_task(task: dict, task_id: int, project_id: int | None) -> dict:
    _require(int(task.get("id") or 0) == task_id, "completed task check failed: task_id mismatch")
    _require(task.get("status") == "completed", f"completed task check failed: status={task.get('status')}")
    safe_workflow_type = task.get("workflow_type")
    _require(
        isinstance(safe_workflow_type, str) and _is_privacy_safe_symbol(safe_workflow_type),
        "completed task check failed: workflow_type invalid",
    )
    task_project_id = _int_metric(task.get("project_id"))
    if project_id is not None:
        _require(task_project_id == project_id, "completed task check failed: project_id mismatch")
    series_id = _int_metric(task.get("series_id"))
    _require(series_id > 0, "completed task check failed: series_id missing")
    runtime_workflow_type = task.get("runtime_workflow_type")
    _require(
        isinstance(runtime_workflow_type, str) and bool(runtime_workflow_type),
        "completed task check failed: runtime_workflow_type missing",
    )
    _require(
        _is_privacy_safe_symbol(runtime_workflow_type),
        "completed task check failed: runtime_workflow_type invalid",
    )
    return {
        "project_id": task_project_id,
        "series_id": series_id,
        "status": "completed",
        "task_id": task_id,
        "workflow_type": safe_workflow_type,
        "runtime_workflow_type": runtime_workflow_type,
    }


def _wait_for_completed_task(base: str, task_id: int, *, timeout_seconds: int, poll_seconds: int) -> dict:
    deadline = time.monotonic() + timeout_seconds
    last_task = None
    while True:
        task = _request("GET", f"{base}/tasks/{task_id}")
        last_task = task
        if task.get("status") == "completed":
            return task
        if task.get("status") in {"failed", "cancelled"}:
            raise SystemExit(f"task completion wait failed: task {task_id} status={task.get('status')}")
        if time.monotonic() >= deadline:
            raise SystemExit(f"task completion wait timed out: task {task_id} status={task.get('status')}")
        time.sleep(max(poll_seconds, 1))


def _validate_launched_task(task: dict, *, task_id: int, series_id: int, workflow_type: str, project_id: int | None) -> dict:
    launched_task_id = _int_metric(task.get("id"), task.get("task_id"))
    _require(launched_task_id == task_id, "launched task check failed: task_id mismatch")
    launched_series_id = _int_metric(task.get("series_id"))
    _require(launched_series_id == series_id, "launched task check failed: series_id mismatch")
    launched_workflow_type = task.get("workflow_type")
    runtime_workflow_type = task.get("runtime_workflow_type")
    _require(
        launched_workflow_type == workflow_type and _is_privacy_safe_symbol(launched_workflow_type),
        "launched task check failed: workflow_type mismatch",
    )
    launched_project_id = _int_metric(task.get("project_id"))
    if project_id is not None:
        _require(launched_project_id == project_id, "launched task check failed: project_id mismatch")
    _require(
        isinstance(runtime_workflow_type, str) and bool(runtime_workflow_type),
        "launched task check failed: runtime_workflow_type missing",
    )
    _require(
        _is_privacy_safe_symbol(runtime_workflow_type),
        "launched task check failed: runtime_workflow_type invalid",
    )
    initial_status = task.get("status")
    _require(
        isinstance(initial_status, str) and _is_privacy_safe_symbol(initial_status),
        "launched task check failed: initial status invalid",
    )
    return {
        "task_id": launched_task_id,
        "project_id": launched_project_id,
        "series_id": launched_series_id,
        "workflow_type": launched_workflow_type,
        **({"runtime_workflow_type": runtime_workflow_type} if runtime_workflow_type else {}),
        "launch_source": "direct_series_run",
        "initial_status": initial_status,
    }


def _validate_uploaded_series(upload_response: dict, *, project_id: int) -> dict:
    series = upload_response.get("series") if isinstance(upload_response, dict) else None
    _require(isinstance(series, dict), "uploaded series check failed: series missing")
    series_id = _int_metric(series.get("id"), series.get("series_id"))
    _require(series_id > 0, "uploaded series check failed: series_id missing")
    uploaded_project_id = _int_metric(series.get("project_id"))
    _require(uploaded_project_id == project_id, "uploaded series check failed: project_id mismatch")
    modality = series.get("modality")
    _require(
        isinstance(modality, str) and _is_privacy_safe_symbol(modality),
        "uploaded series check failed: modality invalid",
    )
    _validate_workflow_eligibility(series.get("workflow_eligibility"), "uploaded series check failed")
    safe = {
        "project_id": uploaded_project_id,
        "series_id": series_id,
        "modality": modality,
    }
    upload_session_id = _int_metric(upload_response.get("upload_session_id"))
    if upload_session_id is not None and upload_session_id > 0:
        safe["upload_session_id"] = upload_session_id
    sequence_label = series.get("sequence_label")
    if isinstance(sequence_label, str) and _is_privacy_safe_symbol(sequence_label):
        safe["sequence_label"] = sequence_label
    return safe


def _select_existing_uploaded_series(series: list[dict], *, project_id: int, series_id: int, upload_session_id: int | None) -> dict:
    _require(isinstance(series, list), "existing uploaded series check failed: project series response is not a list")
    match = None
    for item in series:
        if _int_metric(item.get("id"), item.get("series_id")) == series_id:
            match = item
            break
    _require(match is not None, "existing uploaded series check failed: series_id not found")
    response = {"series": match}
    found_upload_session_id = _int_metric(match.get("upload_session_id"))
    if found_upload_session_id is not None and found_upload_session_id > 0:
        response["upload_session_id"] = found_upload_session_id
    if upload_session_id is not None:
        _require(
            found_upload_session_id == upload_session_id,
            "existing uploaded series check failed: upload_session_id mismatch",
        )
        response["upload_session_id"] = upload_session_id
    return _validate_uploaded_series(response, project_id=project_id)


def _validate_project_series_contract(series: list[dict]) -> dict:
    _require(isinstance(series, list), "project series contract failed: response is not a list")
    _require(series, "project series contract failed: no series found")
    metadata_summary = _empty_workflow_eligibility_metadata_summary()
    for item in series:
        eligibility = item.get("workflow_eligibility")
        _validate_workflow_eligibility(eligibility, "project series contract failed")
        _merge_workflow_eligibility_metadata_summary(metadata_summary, eligibility)
    return {
        "status": "passed",
        "series_count": len(series),
        "series_with_workflow_eligibility": len(series),
        "modalities": sorted({str(item.get("modality")) for item in series if item.get("modality")}),
        **_finalize_workflow_eligibility_metadata_summary(metadata_summary),
    }


def _workflow_type_from_runnable_entry(entry: object) -> str | None:
    if isinstance(entry, str):
        return entry
    if isinstance(entry, dict) and isinstance(entry.get("workflow_type"), str):
        return entry["workflow_type"]
    return None


def _validate_task_workflow_selection(series: list[dict], completed_task: dict) -> dict:
    task_series_id = completed_task.get("series_id")
    workflow_type = completed_task.get("workflow_type")
    _require(isinstance(task_series_id, int) and not isinstance(task_series_id, bool), "task workflow selection check failed: series_id missing")
    _require(isinstance(workflow_type, str) and bool(workflow_type), "task workflow selection check failed: workflow_type missing")
    matching_series = [item for item in series if _int_metric(item.get("id"), item.get("series_id")) == task_series_id]
    _require(matching_series, "task workflow selection check failed: completed task series missing from project series")
    eligibility = matching_series[0].get("workflow_eligibility")
    _validate_workflow_eligibility(eligibility, "task workflow selection check failed")
    runnable = eligibility.get("runnable_workflows") if isinstance(eligibility, dict) else []
    runnable_workflows = {
        value
        for value in (_workflow_type_from_runnable_entry(entry) for entry in runnable)
        if isinstance(value, str) and value
    }
    _require(
        workflow_type in runnable_workflows,
        "task workflow selection check failed: workflow_type not runnable for completed task series",
    )
    return {
        "series_id": task_series_id,
        "workflow_type": workflow_type,
        "matched_runnable_workflow": True,
    }


def _validate_workflow_eligibility(value: object, context: str) -> None:
    _require(isinstance(value, dict), f"{context}: workflow_eligibility missing")
    _require(
        value.get("policy_version") == "workflow_eligibility_v1",
        f"{context}: workflow_eligibility policy_version failed",
    )
    _require(
        value.get("production_task_created") is False,
        f"{context}: workflow_eligibility must not create production tasks",
    )
    _require(
        isinstance(value.get("runnable_workflows"), list),
        f"{context}: runnable_workflows missing",
    )
    _require(
        isinstance(value.get("blocked_workflows"), list),
        f"{context}: blocked_workflows missing",
    )
    primary = value.get("primary_recommendation")
    if isinstance(primary, dict):
        _validate_workflow_eligibility_entry(primary, f"{context}: primary_recommendation")
    for key in ("runnable_workflows", "blocked_workflows"):
        for index, entry in enumerate(value.get(key) or []):
            if isinstance(entry, dict):
                _validate_workflow_eligibility_entry(entry, f"{context}: {key}[{index}]")


def _validate_workflow_eligibility_entry(entry: dict, context: str) -> None:
    workflow_type = entry.get("workflow_type")
    if not isinstance(workflow_type, str) or not workflow_type:
        return
    workflow_metadata = _safe_workflow_metadata(entry.get("workflow_metadata"), workflow_type=workflow_type)
    _require(workflow_metadata is not None, f"{context} workflow_metadata missing")
    _validate_workflow_eligibility_metadata(workflow_metadata, context)


def _validate_workflow_eligibility_metadata(workflow_metadata: dict, context: str) -> None:
    for key in ("display_name", "capability_summary", "workflow_family", "workflow_role"):
        _require(
            isinstance(workflow_metadata.get(key), str) and bool(workflow_metadata.get(key)),
            f"{context} workflow_metadata {key} missing",
        )
    for key in ("pipeline_stages", "primary_outputs", "qc_outputs", "report_outputs", "limitations"):
        _require(
            isinstance(workflow_metadata.get(key), list) and bool(workflow_metadata.get(key)),
            f"{context} workflow_metadata {key} missing",
        )
    _require(
        workflow_metadata.get("is_report_only") is False,
        f"{context} workflow_metadata is_report_only invalid",
    )
    _require(
        workflow_metadata.get("agent_selectable") is True,
        f"{context} workflow_metadata agent_selectable invalid",
    )


def _empty_workflow_eligibility_metadata_summary() -> dict:
    return {"item_count": 0, "workflow_types": set()}


def _merge_workflow_eligibility_metadata_summary(summary: dict, eligibility: object) -> None:
    if not isinstance(eligibility, dict):
        return
    entries: list[object] = []
    primary = eligibility.get("primary_recommendation")
    if isinstance(primary, dict):
        entries.append(primary)
    for key in ("runnable_workflows", "blocked_workflows"):
        value = eligibility.get(key)
        if isinstance(value, list):
            entries.extend(value)
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        workflow_type = entry.get("workflow_type")
        if not isinstance(workflow_type, str) or not workflow_type:
            continue
        workflow_metadata = _safe_workflow_metadata(entry.get("workflow_metadata"), workflow_type=workflow_type)
        if workflow_metadata is None:
            continue
        summary["item_count"] += 1
        summary["workflow_types"].add(workflow_type)


def _finalize_workflow_eligibility_metadata_summary(summary: dict) -> dict:
    return {
        "workflow_metadata_status": "passed",
        "workflow_metadata_required_fields": WORKFLOW_ELIGIBILITY_METADATA_REQUIRED_FIELDS,
        "workflow_metadata_workflow_types": sorted(summary["workflow_types"]),
        "workflow_metadata_item_count": int(summary["item_count"]),
    }


def _validate_upload_inventory_contract(response: dict, upload_session_id: int) -> dict:
    _require(int(response.get("upload_session_id") or 0) == upload_session_id, "upload inventory session id mismatch")
    inventory = response.get("inventory")
    _require(isinstance(inventory, dict), "upload inventory contract failed: inventory missing")
    series = inventory.get("series")
    _require(isinstance(series, list), "upload inventory contract failed: series missing")
    _require(bool(series), "upload inventory contract failed: no series found")
    series_ids = []
    metadata_summary = _empty_workflow_eligibility_metadata_summary()
    for item in series:
        eligibility = item.get("workflow_eligibility")
        _validate_workflow_eligibility(eligibility, "upload inventory contract failed")
        _merge_workflow_eligibility_metadata_summary(metadata_summary, eligibility)
        try:
            series_id = int(item.get("series_id") or item.get("id") or 0)
        except (TypeError, ValueError):
            series_id = 0
        _require(series_id > 0, "upload inventory contract failed: series id missing")
        series_ids.append(series_id)
    return {
        "status": "passed",
        "upload_session_id": upload_session_id,
        "inventory_status": inventory.get("inventory_status") or response.get("status"),
        "series_count": len(series),
        "series_ids": sorted(series_ids),
        "series_with_workflow_eligibility": len(series),
        "modalities": sorted({str(item.get("modality")) for item in series if item.get("modality")}),
        **_finalize_workflow_eligibility_metadata_summary(metadata_summary),
    }


def _validate_completed_upload_inventory(upload_inventory_contract: dict) -> None:
    status = upload_inventory_contract.get("inventory_status")
    _require(status == "completed", f"upload inventory completion check failed: status={status}")


def _is_unsafe_path(value: str) -> bool:
    normalized = value.replace("\\", "/")
    path_parts = [part for part in normalized.split("/") if part]
    return (
        not normalized
        or "\\" in value
        or normalized.startswith("/")
        or (len(normalized) >= 2 and normalized[1] == ":" and normalized[0].isalpha())
        or ".." in path_parts
    )


def _contains_unredacted_unsafe_text(value: object) -> bool:
    if not isinstance(value, str):
        return False
    return bool(
        re.search(r"[A-Za-z]:[\\/]", value)
        or re.search(r"/(?:home|Users|mnt|data|tmp|var)/", value)
        or re.search(r"(?i)(api[_-]?key|token|secret|password|license)\s*=", value)
        or re.search(r"(?<![A-Za-z0-9])sk-[A-Za-z0-9._-]+", value)
    )


def _validate_no_artifact_path_leakage(item: dict, context: str, *, allow_relative_path: bool = True) -> None:
    leaked_path_keys = {"path", "absolute_path", "backend_path", "filesystem_path"}

    def visit(value: object, *, top_level: bool = False) -> None:
        if isinstance(value, dict):
            for key, nested in value.items():
                key_text = str(key)
                _require(key_text not in leaked_path_keys, f"{context} leaked backend absolute path")
                if top_level and (key_text == "download_url" or (allow_relative_path and key_text == "relative_path")):
                    continue
                if "path" in key_text.lower() and isinstance(nested, str):
                    _require(not _is_unsafe_path(nested), f"{context} leaked backend absolute path")
                visit(nested)
        elif isinstance(value, list):
            for nested in value:
                visit(nested)

    visit(item, top_level=True)


def _validate_task_artifact_manifest(
    manifest: dict,
    task_id: int,
    *,
    require_native_qc_artifact: bool = False,
    min_native_qc_images: int = 0,
    require_scientific_report_artifacts: bool = False,
    min_scientific_report_images: int = 0,
) -> dict:
    _require(manifest.get("contract_version") == "artifact_manifest_v1", "task artifact manifest contract_version failed")
    _require(int(manifest.get("task_id") or 0) == task_id, "task artifact manifest task_id mismatch")
    artifacts = manifest.get("artifacts")
    _require(isinstance(artifacts, list), "task artifact manifest artifacts missing")
    _require(bool(artifacts), "task artifact manifest has no artifacts")
    preview_kinds = []
    artifact_relative_paths = []
    artifact_download_urls = []
    native_qc_artifacts = []
    scientific_report_artifacts = []
    scientific_report_candidates = []
    for artifact in artifacts:
        _require(isinstance(artifact, dict), "task artifact manifest artifact is not an object")
        _validate_no_artifact_path_leakage(artifact, "task artifact manifest")
        _require(artifact.get("exists") is not False, "task artifact manifest artifact exists=false")
        _require(artifact.get("exists") is True, "task artifact manifest artifact exists=true missing")
        relative_path = str(artifact.get("relative_path") or "")
        download_url = str(artifact.get("download_url") or "")
        preview_kind = str(artifact.get("preview_kind") or "")
        content_type = str(artifact.get("content_type") or "")
        _require(not _is_unsafe_path(relative_path), "task artifact manifest relative_path is unsafe")
        _require(download_url == f"/tasks/{task_id}/artifacts/{quote(relative_path)}", "task artifact manifest download_url mismatch")
        _require(bool(content_type), "task artifact manifest content_type missing")
        _require(int(artifact.get("size_bytes") or 0) > 0, "task artifact manifest size_bytes missing")
        _require(preview_kind in {"html", "image", "table", "json", "download"}, "task artifact manifest preview_kind invalid")
        preview_kinds.append(preview_kind)
        artifact_relative_paths.append(relative_path)
        artifact_download_urls.append(download_url)
        if _is_native_qc_artifact(artifact):
            _validate_native_qc_provenance(artifact)
            source_ids = _native_qc_official_source_ids(artifact)
            provenance = artifact.get("provenance") if isinstance(artifact.get("provenance"), dict) else {}
            _require(source_ids, "native container QC artifact official_source_ids missing")
            native_qc_artifacts.append(
                {
                    "relative_path": relative_path,
                    "download_url": download_url,
                    "content_type": content_type,
                    "preview_kind": preview_kind,
                    "artifact_origin": artifact.get("artifact_origin"),
                    "native_artifact": artifact.get("native_artifact"),
                    "official_source_ids": source_ids,
                    "provenance": {
                        "generated_from": provenance.get("generated_from"),
                        "replaces_native_qc": provenance.get("replaces_native_qc"),
                        "official_source_ids": source_ids,
                    },
                }
            )
        if _is_scientific_report_candidate(artifact):
            scientific_report_candidates.append(artifact)
    omitted_artifacts = manifest.get("omitted_artifacts", [])
    _require(isinstance(omitted_artifacts, list), "task artifact manifest omitted_artifacts invalid")
    for omitted_artifact in omitted_artifacts:
        _require(isinstance(omitted_artifact, dict), "task artifact manifest omitted_artifact is not an object")
        _validate_no_artifact_path_leakage(
            omitted_artifact,
            "task artifact manifest omitted_artifacts",
            allow_relative_path=False,
        )
    if require_native_qc_artifact:
        _require(native_qc_artifacts, "task artifact manifest native container QC evidence missing")
    native_qc_image_count = sum(1 for artifact in native_qc_artifacts if artifact["preview_kind"] == "image")
    _require(
        native_qc_image_count >= min_native_qc_images,
        f"task artifact manifest native container QC image count {native_qc_image_count} below minimum {min_native_qc_images}",
    )
    result_summary_available = (manifest.get("result_summary") or {}).get("available")
    for artifact in scientific_report_candidates:
        try:
            _validate_scientific_report_provenance(artifact)
        except SystemExit:
            if require_scientific_report_artifacts or min_scientific_report_images > 0:
                raise
            continue
        provenance = artifact.get("provenance") if isinstance(artifact.get("provenance"), dict) else {}
        scientific_report_artifacts.append(
            {
                "relative_path": str(artifact.get("relative_path") or ""),
                "download_url": str(artifact.get("download_url") or ""),
                "content_type": str(artifact.get("content_type") or ""),
                "preview_kind": str(artifact.get("preview_kind") or ""),
                "source_stage": artifact.get("source_stage"),
                "artifact_role": artifact.get("artifact_role"),
                "artifact_origin": artifact.get("artifact_origin"),
                "native_artifact": artifact.get("native_artifact"),
                "provenance": {
                    "generated_from": provenance.get("generated_from"),
                    "replaces_native_qc": provenance.get("replaces_native_qc"),
                },
            }
        )
    scientific_report_image_count = sum(1 for artifact in scientific_report_artifacts if artifact["preview_kind"] == "image")
    effective_min_scientific_report_images = max(
        min_scientific_report_images,
        1 if require_scientific_report_artifacts else 0,
    )
    if require_scientific_report_artifacts:
        _require(
            result_summary_available is True,
            "task artifact manifest scientific report result_summary unavailable",
        )
        scientific_report_paths = {artifact["relative_path"] for artifact in scientific_report_artifacts}
        _require(
            "reports/index.html" in scientific_report_paths,
            "task artifact manifest scientific report index.html missing",
        )
        _require(
            "reports/report_manifest.json" in scientific_report_paths,
            "task artifact manifest scientific report report_manifest.json missing",
        )
    _require(
        scientific_report_image_count >= effective_min_scientific_report_images,
        (
            "task artifact manifest scientific report image count "
            f"{scientific_report_image_count} below minimum {effective_min_scientific_report_images}"
        ),
    )
    native_qc_source_ids = sorted(
        {
            source_id
            for artifact in native_qc_artifacts
            for source_id in artifact["official_source_ids"]
        }
    )
    return {
        "status": "passed",
        "task_id": task_id,
        "artifact_count": len(artifacts),
        "preview_kinds": sorted(set(preview_kinds)),
        "artifact_relative_paths": artifact_relative_paths,
        "artifact_download_urls": artifact_download_urls,
        "container_native_qc_status": "passed" if require_native_qc_artifact or min_native_qc_images else "skipped",
        "container_native_qc_artifact_count": len(native_qc_artifacts),
        "container_native_qc_image_count": native_qc_image_count,
        "container_native_qc_html_count": sum(1 for artifact in native_qc_artifacts if artifact["preview_kind"] == "html"),
        "container_native_qc_preview_kinds": sorted({item["preview_kind"] for item in native_qc_artifacts}),
        "container_native_qc_relative_paths": [item["relative_path"] for item in native_qc_artifacts],
        "container_native_qc_official_source_ids": native_qc_source_ids,
        "container_native_qc_artifacts": native_qc_artifacts,
        "container_native_qc_served_urls": [],
        "scientific_report_artifacts_status": "passed"
        if require_scientific_report_artifacts or effective_min_scientific_report_images
        else "skipped",
        "scientific_report_artifact_count": len(scientific_report_artifacts),
        "scientific_report_image_count": scientific_report_image_count,
        "scientific_report_html_count": sum(1 for artifact in scientific_report_artifacts if artifact["preview_kind"] == "html"),
        "scientific_report_json_count": sum(1 for artifact in scientific_report_artifacts if artifact["preview_kind"] == "json"),
        "scientific_report_preview_kinds": sorted({item["preview_kind"] for item in scientific_report_artifacts}),
        "scientific_report_relative_paths": [item["relative_path"] for item in scientific_report_artifacts],
        "scientific_report_artifacts": scientific_report_artifacts,
        "scientific_report_served_urls": [],
        "result_summary_available": result_summary_available,
    }


def _count_result_summary_output_items(outputs: dict) -> int:
    count = 0
    for group in outputs.values():
        if isinstance(group, list):
            count += len(group)
        elif isinstance(group, dict):
            count += sum(len(items) for items in group.values() if isinstance(items, list))
    return count


def _iter_result_summary_output_items(outputs: dict):
    for group in outputs.values():
        if isinstance(group, list):
            for item in group:
                if isinstance(item, dict):
                    yield item
        elif isinstance(group, dict):
            for nested in group.values():
                if isinstance(nested, list):
                    for item in nested:
                        if isinstance(item, dict):
                            yield item


def _validate_task_result_summary(
    summary: dict,
    task_id: int,
    completed_task: dict | None = None,
    artifact_manifest: dict | None = None,
) -> dict:
    _require(isinstance(summary, dict), "task result summary must be an object")
    _require(isinstance(summary.get("contract_version"), str) and summary["contract_version"], "task result summary contract_version missing")
    _require(int(summary.get("task_id") or 0) == task_id, "task result summary task_id mismatch")
    workflow_type = summary.get("workflow_type")
    _require(isinstance(workflow_type, str) and _is_privacy_safe_symbol(workflow_type), "task result summary workflow_type invalid")
    if completed_task is not None:
        _require(
            workflow_type == completed_task.get("workflow_type"),
            "task result summary workflow_type mismatch",
        )
    workflow_metadata = _safe_workflow_metadata(
        summary.get("workflow_metadata"),
        workflow_type=workflow_type,
    )
    _require(workflow_metadata is not None, "task result summary workflow_metadata missing")
    if completed_task is not None:
        runtime_workflow_type = completed_task.get("runtime_workflow_type")
        _require(
            workflow_metadata.get("runtime_workflow_type") == runtime_workflow_type,
            "task result summary workflow_metadata runtime_workflow_type mismatch",
        )
    _require(
        workflow_metadata.get("display_name") != workflow_type,
        "task result summary workflow_metadata display_name invalid",
    )
    _require(
        workflow_metadata.get("is_report_only") is False,
        "task result summary workflow_metadata is_report_only invalid",
    )
    _require(
        workflow_metadata.get("agent_selectable") is True,
        "task result summary workflow_metadata agent_selectable invalid",
    )
    for key in ("capability_summary", "pipeline_stages", "primary_outputs", "qc_outputs", "report_outputs", "limitations"):
        _require(workflow_metadata.get(key), f"task result summary workflow_metadata {key} missing")
    modality = summary.get("modality")
    _require(isinstance(modality, str) and _is_privacy_safe_symbol(modality), "task result summary modality invalid")
    feature_groups = summary.get("feature_groups")
    _require(
        isinstance(feature_groups, list)
        and feature_groups
        and all(isinstance(item, str) and _is_privacy_safe_symbol(item) for item in feature_groups),
        "task result summary feature_groups invalid",
    )
    outputs = summary.get("outputs")
    _require(isinstance(outputs, dict) and outputs, "task result summary outputs missing")
    output_item_count = _count_result_summary_output_items(outputs)
    _require(output_item_count > 0, "task result summary output_item_count missing")
    downloadable_outputs = []
    artifact_manifest_paths = set(artifact_manifest.get("artifact_relative_paths", [])) if artifact_manifest else set()
    artifact_manifest_urls = set(artifact_manifest.get("artifact_download_urls", [])) if artifact_manifest else set()
    for item in _iter_result_summary_output_items(outputs):
        relative_path = item.get("relative_path")
        download_url = item.get("download_url")
        content_type = item.get("content_type")
        if relative_path is None and download_url is None:
            continue
        _require(isinstance(relative_path, str) and relative_path, "task result summary output relative_path missing")
        _require(not _is_unsafe_path(relative_path), "task result summary output relative_path is unsafe")
        _require(
            download_url == f"/tasks/{task_id}/artifacts/{quote(relative_path)}",
            "task result summary output download_url mismatch",
        )
        _require(isinstance(content_type, str) and bool(content_type), "task result summary output content_type missing")
        if artifact_manifest is not None:
            _require(
                relative_path in artifact_manifest_paths and download_url in artifact_manifest_urls,
                "task result summary output missing from artifact manifest",
            )
        downloadable_outputs.append(
            {
                "relative_path": relative_path,
                "download_url": download_url,
                "content_type": content_type,
            }
        )
    _require(downloadable_outputs, "task result summary downloadable outputs missing")
    provenance = summary.get("provenance")
    _require(isinstance(provenance, dict) and provenance, "task result summary provenance missing")
    _validate_no_artifact_path_leakage(
        {
            key: value
            for key, value in summary.items()
            if key not in {"outputs", "summary_path"}
        },
        "task result summary",
        allow_relative_path=False,
    )
    return {
        "contract_version": summary["contract_version"],
        "task_id": task_id,
        "workflow_type": workflow_type,
        "workflow_metadata": workflow_metadata,
        "modality": modality,
        "feature_groups": feature_groups,
        "output_group_count": len(outputs),
        "output_item_count": output_item_count,
        "downloadable_output_count": len(downloadable_outputs),
        "downloadable_output_paths": [item["relative_path"] for item in downloadable_outputs],
        "downloadable_output_urls": [item["download_url"] for item in downloadable_outputs],
        "provenance_keys": sorted(str(key) for key in provenance),
    }


def _validate_task_events(events_payload: dict, task_id: int, completed_task: dict) -> dict:
    _require(events_payload.get("status") == "ok", "task events status must be ok")
    task = events_payload.get("task") if isinstance(events_payload.get("task"), dict) else {}
    _require(int(task.get("id") or task.get("task_id") or 0) == task_id, "task events task_id mismatch")
    _require(task.get("status") == completed_task.get("status"), "task events task status mismatch")
    _require(task.get("workflow_type") == completed_task.get("workflow_type"), "task events workflow_type mismatch")
    for section_name in ("task", "main_log"):
        section = events_payload.get(section_name)
        if isinstance(section, dict):
            _validate_no_artifact_path_leakage(section, f"task events {section_name}", allow_relative_path=False)
            for key, value in section.items():
                _require(not _contains_unredacted_unsafe_text(value), f"task events {section_name}.{key} leaked unsafe text")
    events = events_payload.get("events")
    _require(isinstance(events, list) and events, "task events list must be non-empty")
    event_types = sorted({str(event.get("type")) for event in events if isinstance(event, dict) and event.get("type")})
    _require("task.status" in event_types, "task events must include task.status")
    _require("task.remote_log" in event_types, "task events must include task.remote_log")
    status_events = [event for event in events if isinstance(event, dict) and event.get("type") == "task.status"]
    _require(any(event.get("status") == completed_task.get("status") for event in status_events), "task status event mismatch")
    remote_logs = events_payload.get("remote_logs")
    _require(isinstance(remote_logs, list) and remote_logs, "task events remote_logs must be non-empty")
    source_stages: list[str] = []
    for item in remote_logs:
        _require(isinstance(item, dict), "task events remote_log must be an object")
        _validate_no_artifact_path_leakage(item, "task events remote_log", allow_relative_path=False)
        for key, value in item.items():
            _require(not _contains_unredacted_unsafe_text(value), f"task events remote_log.{key} leaked unsafe text")
        name = str(item.get("name") or "")
        source_stage = str(item.get("source_stage") or "")
        _require(name.endswith(".log") and _is_privacy_safe_symbol(name.replace(".", "_")), "task events remote_log name invalid")
        _require(_is_privacy_safe_symbol(source_stage), "task events remote_log source_stage invalid")
        _require(int(item.get("size_bytes") or 0) > 0, "task events remote_log size_bytes missing")
        source_stages.append(source_stage)
    main_log = events_payload.get("main_log") if isinstance(events_payload.get("main_log"), dict) else {}
    return {
        "status": "passed",
        "task_id": task_id,
        "event_types": event_types,
        "status_event_status": completed_task.get("status"),
        "remote_log_count": len(remote_logs),
        "remote_log_source_stages": sorted(set(source_stages)),
        "main_log_tail_present": bool(str(main_log.get("tail") or "")),
    }


def _validate_observe_repair(observe_payload: dict, task_id: int) -> dict:
    _require(isinstance(observe_payload, dict), "observe-repair response must be an object")
    _require(observe_payload.get("status") == "ok", "observe-repair status must be ok")
    _require(
        observe_payload.get("policy") == "read_only_observe_repair",
        "observe-repair policy must be read_only_observe_repair",
    )
    _require(int(observe_payload.get("task_id") or 0) == task_id, "observe-repair task_id mismatch")
    task = observe_payload.get("task") if isinstance(observe_payload.get("task"), dict) else {}
    if task:
        _validate_no_artifact_path_leakage(task, "observe-repair task", allow_relative_path=False)
        for key, value in task.items():
            _require(not _contains_unredacted_unsafe_text(value), f"observe-repair task.{key} leaked unsafe text")
    main_log = observe_payload.get("main_log")
    if isinstance(main_log, dict):
        _validate_no_artifact_path_leakage(main_log, "observe-repair main_log", allow_relative_path=False)
        for key, value in main_log.items():
            _require(not _contains_unredacted_unsafe_text(value), f"observe-repair main_log.{key} leaked unsafe text")
    remote_logs = observe_payload.get("remote_logs")
    _require(isinstance(remote_logs, list), "observe-repair remote_logs must be a list")
    for item in remote_logs:
        _require(isinstance(item, dict), "observe-repair remote_log must be an object")
        _validate_no_artifact_path_leakage(item, "observe-repair remote_log", allow_relative_path=False)
        for key, value in item.items():
            _require(not _contains_unredacted_unsafe_text(value), f"observe-repair remote_log.{key} leaked unsafe text")
    suggestions = observe_payload.get("repair_suggestions")
    _require(isinstance(suggestions, list) and suggestions, "observe-repair repair_suggestions must be non-empty")
    _require(observe_payload.get("auto_rerun_allowed") is False, "observe-repair auto_rerun_allowed must be false")
    _require(observe_payload.get("task_creation_allowed") is False, "observe-repair task_creation_allowed must be false")
    forbidden_actions = observe_payload.get("forbidden_actions")
    _require(
        isinstance(forbidden_actions, list)
        and {"auto_retry", "auto_rerun", "task_creation"}.issubset(set(forbidden_actions)),
        "observe-repair forbidden_actions must include auto_retry, auto_rerun, and task_creation",
    )
    _require(observe_payload.get("production_task_created") is False, "observe-repair production_task_created must be false")
    _require(
        observe_payload.get("requires_preflight_before_retry") is True,
        "observe-repair requires_preflight_before_retry must be true",
    )
    _require(
        observe_payload.get("requires_human_confirmation_before_retry") is True,
        "observe-repair requires_human_confirmation_before_retry must be true",
    )
    return {
        "status": "passed",
        "task_id": task_id,
        "policy": observe_payload.get("policy"),
        "auto_rerun_allowed": False,
        "task_creation_allowed": False,
        "forbidden_actions": ["auto_retry", "auto_rerun", "task_creation"],
        "production_task_created": False,
        "requires_preflight_before_retry": True,
        "requires_human_confirmation_before_retry": True,
        "repair_suggestion_count": len(suggestions),
    }


def _validate_container_native_qc_routes(base: str, artifacts: list[dict[str, object]]) -> list[str]:
    served_urls = []
    for artifact in artifacts:
        download_url = str(artifact.get("download_url") or "")
        expected_content_type = str(artifact.get("content_type") or "").split(";", 1)[0].strip().lower()
        body, served_content_type = _request_bytes(f"{base}{download_url}")
        _require(bool(body), "native container QC artifact route returned empty bytes")
        actual_content_type = served_content_type.split(";", 1)[0].strip().lower()
        _require(
            actual_content_type == expected_content_type,
            "native container QC artifact content_type mismatch",
        )
        served_urls.append(download_url)
    return served_urls


def _validate_scientific_report_artifact_routes(base: str, artifacts: list[dict[str, object]]) -> list[str]:
    served_urls = []
    for artifact in artifacts:
        download_url = str(artifact.get("download_url") or "")
        expected_content_type = str(artifact.get("content_type") or "").split(";", 1)[0].strip().lower()
        body, served_content_type = _request_bytes(f"{base}{download_url}")
        _require(bool(body), "scientific report artifact route returned empty bytes")
        actual_content_type = served_content_type.split(";", 1)[0].strip().lower()
        _require(
            actual_content_type == expected_content_type,
            "scientific report artifact content_type mismatch",
        )
        served_urls.append(download_url)
    return served_urls


def _native_qc_official_source_ids(artifact: dict) -> list[str]:
    provenance = artifact.get("provenance") if isinstance(artifact.get("provenance"), dict) else {}
    top_level_ids = _normalized_official_source_ids(artifact.get("official_source_ids"))
    provenance_ids = _normalized_official_source_ids(provenance.get("official_source_ids"))
    _require(top_level_ids, "native container QC artifact official_source_ids missing")
    _require(provenance_ids, "native container QC artifact provenance.official_source_ids missing")
    _require(
        top_level_ids == provenance_ids,
        "native container QC artifact official_source_ids mismatch",
    )
    for source_id in top_level_ids:
        _require(
            source_id in CONTAINER_NATIVE_QC_OFFICIAL_SOURCE_IDS,
            "native container QC artifact official_source_ids invalid",
        )
        _require(
            _curated_vendor_doc_path(source_id).is_file(),
            "native container QC artifact official_source_ids source document missing",
        )
    return sorted(top_level_ids)


def _normalized_official_source_ids(value: object) -> set[str]:
    if not isinstance(value, list):
        return set()
    source_ids = set()
    for source_id in value:
        if not isinstance(source_id, str):
            raise SystemExit("native container QC artifact official_source_ids invalid")
        if "\\" in source_id or "/raw-sources/" in source_id:
            raise SystemExit("native container QC artifact official_source_ids invalid")
        if not source_id.startswith("docs/rag/vendor/") or not source_id.endswith(".md"):
            raise SystemExit("native container QC artifact official_source_ids invalid")
        source_ids.add(source_id)
    return source_ids


def _curated_vendor_doc_path(source_id: str) -> Path:
    return REPO_ROOT / Path(source_id)


def _is_native_qc_artifact(artifact: dict) -> bool:
    relative_path = str(artifact.get("relative_path") or "").replace("\\", "/").lower()
    if relative_path.startswith("reports/"):
        return False
    provenance = artifact.get("provenance") if isinstance(artifact.get("provenance"), dict) else {}
    return (
        artifact.get("native_artifact") is True
        and artifact.get("artifact_origin") == "container_output"
        and provenance.get("generated_from") == "container_native_qc"
        and artifact.get("preview_kind") in {"html", "image"}
    )


def _is_scientific_report_candidate(artifact: dict) -> bool:
    relative_path = str(artifact.get("relative_path") or "")
    return (
        relative_path == "reports/index.html"
        or relative_path == "reports/report_manifest.json"
        or (relative_path.startswith("reports/") and relative_path.endswith(".png"))
    )


def _validate_scientific_report_provenance(artifact: dict) -> None:
    provenance = artifact.get("provenance") if isinstance(artifact.get("provenance"), dict) else {}
    relative_path = str(artifact.get("relative_path") or "")
    preview_kind = str(artifact.get("preview_kind") or "")
    content_type = str(artifact.get("content_type") or "").split(";", 1)[0].strip().lower()
    _require(artifact.get("source_stage") == "scientific_report", "scientific report artifact source_stage must be scientific_report")
    _require(
        artifact.get("artifact_role") == "derived_presentation_asset",
        "scientific report artifact artifact_role must be derived_presentation_asset",
    )
    _require(
        artifact.get("artifact_origin") == "generated_from_result_summary",
        "scientific report artifact artifact_origin must be generated_from_result_summary",
    )
    _require(artifact.get("native_artifact") is False, "scientific report artifact native_artifact must be false")
    _require(provenance.get("generated_from") == "result_summary", "scientific report artifact provenance.generated_from must be result_summary")
    _require(
        provenance.get("replaces_native_qc") is False,
        "scientific report artifact provenance.replaces_native_qc must be false",
    )
    if relative_path == "reports/index.html":
        _require(preview_kind == "html", "scientific report index.html preview_kind must be html")
        _require(content_type == "text/html", "scientific report index.html content_type must be text/html")
    elif relative_path == "reports/report_manifest.json":
        _require(preview_kind == "json", "scientific report report_manifest.json preview_kind must be json")
        _require(content_type == "application/json", "scientific report report_manifest.json content_type must be application/json")
    elif relative_path.startswith("reports/") and relative_path.endswith(".png"):
        _require(preview_kind == "image", "scientific report PNG preview_kind must be image")
        _require(content_type == "image/png", "scientific report PNG content_type must be image/png")


def _validate_native_qc_provenance(artifact: dict) -> None:
    provenance = artifact.get("provenance") if isinstance(artifact.get("provenance"), dict) else {}
    _require(
        artifact.get("artifact_role") in {"container_native_html_report", "container_native_qc_figure"},
        "native container QC artifact_role invalid",
    )
    _require(bool(artifact.get("source_stage")), "native container QC artifact source_stage missing")
    _require(
        provenance.get("replaces_native_qc") is False,
        "native container QC artifact provenance.replaces_native_qc must be false",
    )


def _generated_at_utc() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _write_output_json(path: str, payload: dict) -> None:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Smoke test the remote Image Agent runtime.")
    parser.add_argument("--api-base", default="http://127.0.0.1:8000")
    parser.add_argument("--message", default="Summarize the current Image Agent runtime status.")
    parser.add_argument("--require-model", action="store_true", help="Fail if the OpenAI model gateway is not configured.")
    parser.add_argument(
        "--expected-model-wire-api",
        help="Optional privacy-safe /agent/model/status wire_api value expected from the deployed API.",
    )
    parser.add_argument(
        "--expected-model-provider-profile",
        help="Optional privacy-safe /agent/model/status provider_profile expected from the deployed API.",
    )
    parser.add_argument(
        "--require-model-tool-loop",
        action="store_true",
        help="Fail unless /agent/model/status.capabilities.model_tool_loop is true.",
    )
    parser.add_argument(
        "--require-project-agent-context",
        action="store_true",
        help="Fail unless the live /agent/runs smoke is scoped to --project-id.",
    )
    parser.add_argument(
        "--skip-agent-run-smoke",
        action="store_true",
        help=(
            "Skip the generic /agent/runs question smoke while still validating "
            "/agent/model/status and any explicit workflow confirmation/resume gates."
        ),
    )
    parser.add_argument(
        "--require-agent-workflow-confirmation",
        action="store_true",
        help="Fail unless /agent/runs can prepare a workflow confirmation without creating a production task.",
    )
    parser.add_argument(
        "--require-agent-workflow-resume",
        action="store_true",
        help="Fail unless /agent/runs/{thread_id}/resume approves the prepared confirmation and creates a backend task.",
    )
    parser.add_argument(
        "--require-agent-workflow-fingerprint-negative",
        action="store_true",
        help="Fail unless a tampered Agent workflow confirmation is blocked before the valid resume creates a task.",
    )
    parser.add_argument(
        "--reuse-persisted-agent-launch-evidence",
        action="store_true",
        help=(
            "Read prior Agent confirmation/resume/fingerprint evidence for --task-id from the local agent state DB "
            "instead of creating a new Agent workflow task."
        ),
    )
    parser.add_argument(
        "--agent-state-db",
        help="SQLite app.db path used by --reuse-persisted-agent-launch-evidence.",
    )
    parser.add_argument(
        "--require-unknown-workflow-incubation",
        action="store_true",
        help="Fail unless an unregistered workflow only creates IncubationLedger/proposal evidence and no task.",
    )
    parser.add_argument(
        "--require-deployment-identity",
        action="store_true",
        help="Fail unless --deployment-id names the accepted remote release or commit.",
    )
    parser.add_argument(
        "--require-production-readiness",
        action="store_true",
        help="Fail unless /deployment.production_readiness reports required=true, ready=true, and status=ready.",
    )
    parser.add_argument(
        "--require-runtime-toolchain",
        action="store_true",
        help="Fail unless /runtime/probe proves deployment-server local Docker/toolchain readiness.",
    )
    parser.add_argument(
        "--deployment-id",
        help="Privacy-safe accepted release id or commit hash, e.g. codex-f57a2ea-20260611T023456.",
    )
    parser.add_argument(
        "--expected-health-version",
        help="Optional privacy-safe /health.version value expected from the deployed API.",
    )
    parser.add_argument("--min-documents", type=int, default=0, help="Minimum RAG document count after rebuild.")
    parser.add_argument("--min-chunks", type=int, default=0, help="Minimum RAG chunk count after rebuild.")
    parser.add_argument(
        "--require-raw-source-policy",
        action="store_true",
        help="Fail unless official raw-source files exist, hash cleanly, and are excluded from the RAG index.",
    )
    parser.add_argument(
        "--require-vendor-pointer-integrity",
        action="store_true",
        help="Fail unless RAG workflow/contract vendor doc pointers have complete raw-source provenance.",
    )
    parser.add_argument(
        "--require-elasticsearch-hybrid-rag",
        action="store_true",
        help="Fail unless RAG status reports a persisted Elasticsearch BM25/dense-vector RRF hybrid index.",
    )
    parser.add_argument(
        "--require-real-evidence-ids",
        action="store_true",
        help="Fail unless --project-id, --upload-session-id, and --task-id are all supplied.",
    )
    parser.add_argument(
        "--require-completed-upload",
        action="store_true",
        help="Fail unless --upload-session-id inventory reports completed upload ingestion.",
    )
    parser.add_argument(
        "--require-uploaded-series",
        action="store_true",
        help="Fail unless smoke uploads --upload-nifti-file through /projects/{project_id}/upload and records the returned series.",
    )
    parser.add_argument(
        "--uploaded-series-id",
        type=int,
        help="Existing series id to validate as uploaded-series evidence without uploading another file.",
    )
    parser.add_argument(
        "--upload-nifti-file",
        help="Local NIfTI file path on the remote smoke runner to upload via /projects/{project_id}/upload.",
    )
    parser.add_argument(
        "--require-completed-task",
        action="store_true",
        help="Fail unless --task-id resolves to a completed task with safe task status metadata.",
    )
    parser.add_argument(
        "--require-launched-task",
        action="store_true",
        help="Fail unless smoke launches a workflow through /series/{series_id}/run and the returned task matches --task-id.",
    )
    parser.add_argument(
        "--require-task-events",
        action="store_true",
        help="Fail unless /tasks/{task_id}/events exposes read-only task status and remote-log observation evidence.",
    )
    parser.add_argument(
        "--require-observe-repair",
        action="store_true",
        help="Fail unless /tasks/{task_id}/observe-repair proves read-only repair suggestions without rerun or task creation.",
    )
    parser.add_argument(
        "--launch-series-id",
        type=int,
        help="Series id to pass to /series/{series_id}/run when --require-launched-task is enabled.",
    )
    parser.add_argument(
        "--launch-workflow-type",
        help="Workflow type to pass to /series/{series_id}/run when --require-launched-task is enabled.",
    )
    parser.add_argument(
        "--wait-task-completion-timeout-seconds",
        type=int,
        default=0,
        help="After launch, poll /tasks/{task_id} until completed for this many seconds. Default: no wait.",
    )
    parser.add_argument(
        "--wait-task-completion-poll-seconds",
        type=int,
        default=30,
        help="Polling interval for --wait-task-completion-timeout-seconds.",
    )
    parser.add_argument(
        "--require-launchability-matrix",
        action="store_true",
        help="Fail unless RAG status and query evidence cite the workflow launchability matrix source.",
    )
    parser.add_argument(
        "--require-container-native-qc",
        "--require-native-qc-artifact",
        dest="require_container_native_qc",
        action="store_true",
        help="Fail unless --task-id artifact-manifest exposes served container-native HTML/image QC with official source ids.",
    )
    parser.add_argument(
        "--min-native-qc-images",
        type=int,
        default=0,
        help="Minimum number of served container-native image QC artifacts required when validating --task-id.",
    )
    parser.add_argument(
        "--require-scientific-report-artifacts",
        action="store_true",
        help="Fail unless --task-id artifact-manifest exposes derived scientific report HTML/manifest/PNG artifacts.",
    )
    parser.add_argument(
        "--min-scientific-report-images",
        type=int,
        default=0,
        help="Minimum number of derived scientific report PNG artifacts required when validating --task-id.",
    )
    parser.add_argument(
        "--output-json",
        help="Write the strict smoke result payload to a JSON file for remote acceptance evidence.",
    )
    parser.add_argument(
        "--project-id",
        type=int,
        help="Optionally validate /projects/{project_id}/series exposes workflow_eligibility.",
    )
    parser.add_argument(
        "--task-id",
        type=int,
        help="Optionally validate /tasks/{task_id}/artifact-manifest exposes safe preview/download artifacts.",
    )
    parser.add_argument(
        "--upload-session-id",
        type=int,
        help="Optionally validate /projects/{project_id}/datasets/{upload_session_id}/inventory exposes workflow_eligibility.",
    )
    args = parser.parse_args(argv)
    if args.upload_session_id is not None and args.project_id is None:
        raise SystemExit("--upload-session-id requires --project-id")
    if args.require_uploaded_series and (
        args.project_id is None or (not args.upload_nifti_file and args.uploaded_series_id is None)
    ):
        raise SystemExit("--require-uploaded-series requires --project-id and --upload-nifti-file or --uploaded-series-id")
    if args.upload_nifti_file and args.uploaded_series_id is not None:
        raise SystemExit("--upload-nifti-file cannot be combined with --uploaded-series-id")
    if args.require_project_agent_context and args.project_id is None:
        raise SystemExit("--require-project-agent-context requires --project-id")
    if args.skip_agent_run_smoke and args.require_project_agent_context:
        raise SystemExit("--skip-agent-run-smoke cannot be combined with --require-project-agent-context")
    if args.require_agent_workflow_confirmation and args.project_id is None:
        raise SystemExit("--require-agent-workflow-confirmation requires --project-id")
    if args.require_agent_workflow_confirmation and not args.launch_workflow_type:
        raise SystemExit("--require-agent-workflow-confirmation requires --launch-workflow-type")
    if args.require_agent_workflow_resume and not args.require_agent_workflow_confirmation:
        raise SystemExit("--require-agent-workflow-resume requires --require-agent-workflow-confirmation")
    if args.require_agent_workflow_fingerprint_negative and not args.require_agent_workflow_resume:
        raise SystemExit("--require-agent-workflow-fingerprint-negative requires --require-agent-workflow-resume")
    if args.reuse_persisted_agent_launch_evidence:
        if not args.agent_state_db:
            raise SystemExit("--reuse-persisted-agent-launch-evidence requires --agent-state-db")
        if args.task_id is None:
            raise SystemExit("--reuse-persisted-agent-launch-evidence requires --task-id")
        if not (
            args.require_agent_workflow_confirmation
            and args.require_agent_workflow_resume
            and args.require_launched_task
        ):
            raise SystemExit(
                "--reuse-persisted-agent-launch-evidence requires confirmation, resume, and launched-task gates"
            )
    if args.require_unknown_workflow_incubation and args.project_id is None:
        raise SystemExit("--require-unknown-workflow-incubation requires --project-id")
    if args.require_completed_upload and (
        args.project_id is None or (args.upload_session_id is None and not args.require_uploaded_series)
    ):
        raise SystemExit("--require-completed-upload requires --project-id and --upload-session-id")
    if args.require_real_evidence_ids and (
        args.project_id is None
        or (args.upload_session_id is None and not args.require_uploaded_series)
        or (args.task_id is None and not args.require_launched_task)
    ):
        raise SystemExit(
            "--require-real-evidence-ids requires --project-id, --upload-session-id, and --task-id "
            "unless --require-uploaded-series and/or --require-launched-task will supply them"
        )
    if args.require_deployment_identity and not args.deployment_id:
        raise SystemExit("--require-deployment-identity requires --deployment-id")
    if args.deployment_id is not None and not _is_privacy_safe_symbol(args.deployment_id):
        raise SystemExit("--deployment-id must be a privacy-safe release id or commit")
    if args.expected_health_version is not None and not _is_privacy_safe_symbol(args.expected_health_version):
        raise SystemExit("--expected-health-version must be a privacy-safe version")
    if args.expected_model_wire_api is not None and not _is_privacy_safe_symbol(args.expected_model_wire_api):
        raise SystemExit("--expected-model-wire-api must be privacy-safe")
    if args.expected_model_provider_profile is not None and not _is_privacy_safe_symbol(args.expected_model_provider_profile):
        raise SystemExit("--expected-model-provider-profile must be privacy-safe")
    if args.require_container_native_qc and args.task_id is None and not args.require_launched_task:
        raise SystemExit("--require-container-native-qc requires --task-id")
    if args.require_completed_task and args.task_id is None and not args.require_launched_task:
        raise SystemExit("--require-completed-task requires --task-id")
    if args.require_task_events and args.task_id is None and not args.require_launched_task:
        raise SystemExit("--require-task-events requires --task-id")
    if args.require_observe_repair and args.task_id is None and not args.require_launched_task:
        raise SystemExit("--require-observe-repair requires --task-id")
    if args.require_launched_task and (
        (args.launch_series_id is None and not args.require_uploaded_series) or not args.launch_workflow_type
    ):
        raise SystemExit("--require-launched-task requires --launch-series-id and --launch-workflow-type")
    if args.require_production_readiness and args.require_launched_task and not args.require_agent_workflow_resume:
        raise SystemExit(
            "--require-production-readiness with --require-launched-task requires --require-agent-workflow-resume"
        )
    if args.require_deployment_identity and args.require_launched_task and not args.require_agent_workflow_resume:
        raise SystemExit(
            "--require-deployment-identity with --require-launched-task requires --require-agent-workflow-resume"
        )
    if args.require_runtime_toolchain and args.require_launched_task and not args.require_agent_workflow_resume:
        raise SystemExit(
            "--require-runtime-toolchain with --require-launched-task requires --require-agent-workflow-resume"
        )
    if args.launch_series_id is not None and args.launch_series_id <= 0:
        raise SystemExit("--launch-series-id must be a positive integer")
    if args.uploaded_series_id is not None and args.uploaded_series_id <= 0:
        raise SystemExit("--uploaded-series-id must be a positive integer")
    if args.launch_workflow_type is not None and not _is_privacy_safe_symbol(args.launch_workflow_type):
        raise SystemExit("--launch-workflow-type must be privacy-safe")
    if args.require_launched_task and args.launch_workflow_type in DEBUG_ONLY_WORKFLOWS:
        raise SystemExit(f"strict deployment acceptance cannot use debug-only workflow {args.launch_workflow_type}")
    if args.wait_task_completion_timeout_seconds < 0:
        raise SystemExit("--wait-task-completion-timeout-seconds must be non-negative")
    if args.wait_task_completion_poll_seconds <= 0:
        raise SystemExit("--wait-task-completion-poll-seconds must be a positive integer")
    if args.min_native_qc_images > 0 and args.task_id is None and not args.require_launched_task:
        raise SystemExit("--min-native-qc-images requires --task-id")
    if args.require_scientific_report_artifacts and args.task_id is None and not args.require_launched_task:
        raise SystemExit("--require-scientific-report-artifacts requires --task-id")
    if args.min_scientific_report_images > 0 and args.task_id is None and not args.require_launched_task:
        raise SystemExit("--min-scientific-report-images requires --task-id")

    base = args.api_base.rstrip("/")
    health = _request("GET", f"{base}/health")
    _validate_health(health)
    production_readiness = None
    fast_launch_readiness = None
    fast_launch_readiness_status = "skipped"
    if args.require_production_readiness:
        deployment_status = _request("GET", f"{base}/deployment")
        production_readiness = _safe_production_readiness(deployment_status)
        fast_launch_readiness = _safe_fast_launch_readiness(deployment_status)
        fast_launch_readiness_status = fast_launch_readiness.pop("_acceptance_status", "passed")
    runtime_toolchain = None
    if args.require_runtime_toolchain:
        runtime_toolchain = _safe_runtime_toolchain(
            _runtime_toolchain_status(base),
            required_workflow_type=args.launch_workflow_type,
        )
    deployment_identity = None
    if args.deployment_id:
        health_version = health.get("version")
        _require(
            isinstance(health_version, str) and bool(health_version),
            "deployment identity health version is missing",
        )
        _require(
            _is_privacy_safe_symbol(health_version),
            "deployment identity health version must be privacy-safe",
        )
        if args.expected_health_version is not None:
            _require(
                health_version == args.expected_health_version,
                "deployment identity health version must match --expected-health-version",
            )
        deployment_identity = {
            "deployment_id": args.deployment_id,
            "health_app": health.get("app"),
            "health_version": health_version,
        }
    status = _request("GET", f"{base}/agent/model/status")
    safe_model_status = _safe_model_status(status)
    if args.expected_model_wire_api is not None:
        actual_wire_api = safe_model_status.get("wire_api")
        _require(
            actual_wire_api == args.expected_model_wire_api,
            f"model wire_api {actual_wire_api or 'missing'} did not match --expected-model-wire-api {args.expected_model_wire_api}",
        )
    if args.expected_model_provider_profile is not None:
        actual_profile = safe_model_status.get("provider_profile")
        _require(
            actual_profile == args.expected_model_provider_profile,
            f"model provider_profile {actual_profile or 'missing'} did not match --expected-model-provider-profile {args.expected_model_provider_profile}",
        )
    if args.require_model_tool_loop:
        capabilities = safe_model_status.get("capabilities") if isinstance(safe_model_status.get("capabilities"), dict) else {}
        _require(
            capabilities.get("model_tool_loop") is True,
            "model capabilities.model_tool_loop must be true when --require-model-tool-loop is set",
        )
    _validate_direct_model_gateway(safe_model_status, args.expected_model_provider_profile)
    rag_before = _request("GET", f"{base}/agent/rag/status")
    rag = _request("POST", f"{base}/agent/rag/rebuild")
    rag_after = _request("GET", f"{base}/agent/rag/status")
    _validate_rag_thresholds(
        rag=rag,
        rag_after=rag_after,
        min_documents=max(args.min_documents, 0),
        min_chunks=max(args.min_chunks, 0),
    )
    if args.require_raw_source_policy:
        _validate_raw_source_policy(rag_after)
    vendor_pointer_integrity = None
    if args.require_vendor_pointer_integrity:
        vendor_pointer_integrity = _validate_vendor_pointer_integrity(rag_after)
    elasticsearch_hybrid_rag = None
    elasticsearch_hybrid_rebuild = None
    elasticsearch_hybrid_query = None
    if args.require_elasticsearch_hybrid_rag:
        elasticsearch_hybrid_rag = _validate_elasticsearch_hybrid_rag(rag_after)
        elasticsearch_hybrid_rebuild = _validate_elasticsearch_hybrid_rebuild(
            rag,
            status_evidence=elasticsearch_hybrid_rag,
        )
        elasticsearch_hybrid_query = _validate_elasticsearch_hybrid_query_evidence(
            _request("POST", f"{base}/agent/rag/query", {"query": ELASTICSEARCH_HYBRID_SMOKE_QUERY}),
            status_evidence=elasticsearch_hybrid_rag,
        )
    vendor_coverage_catalog = _summarize_vendor_coverage_catalog(rag_after)
    launchability_matrix = None
    launchability_query = None
    if args.require_launchability_matrix:
        launchability_matrix = _validate_launchability_matrix_evidence(rag_after)
        launchability_query = _validate_launchability_query_evidence(
            _request("POST", f"{base}/agent/rag/query", {"query": LAUNCHABILITY_SMOKE_QUERY})
        )
    run = None
    model_smoke_status = "skipped_missing_model_config"
    if status.get("configured") and args.skip_agent_run_smoke:
        model_smoke_status = "skipped_by_option"
    elif status.get("configured"):
        agent_project_id = args.project_id if args.require_project_agent_context else None
        run = _request("POST", f"{base}/agent/runs", {"project_id": agent_project_id, "message": args.message})
        _validate_agent_run(run)
        if args.require_project_agent_context:
            _validate_agent_project_context(run, args.project_id)
        model_smoke_status = "passed"
    elif args.require_model or args.require_project_agent_context:
        raise SystemExit("model gateway is not configured")
    project_contract = None
    project_series = None
    task_artifact_manifest = None
    task_result_summary = None
    completed_task = None
    task_workflow_selection = None
    task_events = None
    observe_repair = None
    upload_inventory_contract = None
    launched_task = None
    uploaded_series = None
    agent_workflow_confirmation = None
    agent_workflow_resume = None
    agent_workflow_fingerprint_negative = None
    unknown_workflow_incubation = None
    if args.reuse_persisted_agent_launch_evidence:
        _require(args.task_id is not None, "--reuse-persisted-agent-launch-evidence requires --task-id")
        _require(args.project_id is not None, "--reuse-persisted-agent-launch-evidence requires --project-id")
        _require(args.launch_series_id is not None, "--reuse-persisted-agent-launch-evidence requires --launch-series-id")
        task_for_launch = _request("GET", f"{base}/tasks/{args.task_id}")
        persisted_launch = _load_persisted_agent_launch_evidence(
            Path(args.agent_state_db),
            task=task_for_launch,
            task_id=args.task_id,
            project_id=args.project_id,
            series_id=args.launch_series_id,
            workflow_type=args.launch_workflow_type,
        )
        agent_workflow_confirmation = persisted_launch["agent_workflow_confirmation"]
        agent_workflow_resume = persisted_launch["agent_workflow_resume"]
        agent_workflow_fingerprint_negative = persisted_launch["agent_workflow_fingerprint_negative"]
        launched_task = persisted_launch["launched_task"]
    if args.require_uploaded_series:
        if args.uploaded_series_id is not None:
            existing_series_response = _request("GET", f"{base}/projects/{args.project_id}/series")
            uploaded_series = _select_existing_uploaded_series(
                existing_series_response,
                project_id=args.project_id,
                series_id=args.uploaded_series_id,
                upload_session_id=args.upload_session_id,
            )
        else:
            uploaded_series = _validate_uploaded_series(
                _upload_nifti(base, args.project_id, Path(args.upload_nifti_file)),
                project_id=args.project_id,
            )
        if args.launch_series_id is not None and args.launch_series_id != uploaded_series["series_id"]:
            raise SystemExit("--launch-series-id must match the series returned by --require-uploaded-series")
        if args.launch_series_id is None:
            args.launch_series_id = uploaded_series["series_id"]
        if args.upload_session_id is None and uploaded_series.get("upload_session_id"):
            args.upload_session_id = uploaded_series["upload_session_id"]
    if args.require_agent_workflow_confirmation and not args.reuse_persisted_agent_launch_evidence:
        _require(
            args.launch_series_id is not None,
            "--require-agent-workflow-confirmation requires --launch-series-id or --require-uploaded-series",
        )
        workflow_message = (
            f"Prepare a workflow confirmation for series {args.launch_series_id} using workflow "
            f"{args.launch_workflow_type}. Do not launch it."
        )
        agent_workflow_run = _request("POST", f"{base}/agent/runs", {"project_id": args.project_id, "message": workflow_message})
        agent_workflow_confirmation = _validate_agent_workflow_confirmation(
            agent_workflow_run,
            project_id=args.project_id,
            series_id=args.launch_series_id,
            workflow_type=args.launch_workflow_type,
        )
    if args.require_agent_workflow_resume and not args.reuse_persisted_agent_launch_evidence:
        _require(agent_workflow_confirmation is not None, "--require-agent-workflow-resume requires a prepared confirmation")
        thread_id = agent_workflow_run.get("thread_id") if isinstance(agent_workflow_run, dict) else None
        _require(isinstance(thread_id, str) and bool(thread_id), "agent workflow resume failed: confirmation thread_id missing")
        confirmation_payload = agent_workflow_run.get("confirmation") if isinstance(agent_workflow_run, dict) else None
        _require(isinstance(confirmation_payload, dict), "agent workflow resume failed: confirmation payload missing")
        if args.require_agent_workflow_fingerprint_negative:
            fingerprint_negative_run = _request(
                "POST",
                f"{base}/agent/runs",
                {"project_id": args.project_id, "message": workflow_message},
            )
            fingerprint_negative_thread_id = (
                fingerprint_negative_run.get("thread_id") if isinstance(fingerprint_negative_run, dict) else None
            )
            _require(
                isinstance(fingerprint_negative_thread_id, str) and bool(fingerprint_negative_thread_id),
                "agent workflow fingerprint negative failed: confirmation thread_id missing",
            )
            fingerprint_negative_confirmation = (
                fingerprint_negative_run.get("confirmation") if isinstance(fingerprint_negative_run, dict) else None
            )
            _require(
                isinstance(fingerprint_negative_confirmation, dict),
                "agent workflow fingerprint negative failed: confirmation payload missing",
            )
            _validate_agent_workflow_confirmation(
                fingerprint_negative_run,
                project_id=args.project_id,
                series_id=args.launch_series_id,
                workflow_type=args.launch_workflow_type,
            )
            tampered_confirmation = _tampered_confirmation_payload(
                fingerprint_negative_confirmation,
                original_series_id=int(args.launch_series_id),
            )
            agent_workflow_fingerprint_negative = _validate_agent_workflow_fingerprint_negative(
                _request(
                    "POST",
                    f"{base}/agent/runs/{quote(fingerprint_negative_thread_id, safe='')}/resume",
                    {"approved": True, "confirmation": tampered_confirmation},
                ),
                thread_id=fingerprint_negative_thread_id,
            )
        agent_workflow_resume = _validate_agent_workflow_resume(
            _request(
                "POST",
                f"{base}/agent/runs/{quote(thread_id, safe='')}/resume",
                {"approved": True, "confirmation": confirmation_payload},
            ),
            thread_id=thread_id,
            project_id=args.project_id,
            series_id=args.launch_series_id,
            workflow_type=args.launch_workflow_type,
        )
        if args.task_id is None and (
            args.require_completed_task
            or args.require_container_native_qc
            or args.require_scientific_report_artifacts
            or args.min_native_qc_images > 0
            or args.min_scientific_report_images > 0
            or args.require_real_evidence_ids
        ):
            args.task_id = agent_workflow_resume["task_id"]
        launched_task = {
            "task_id": agent_workflow_resume["task_id"],
            "project_id": agent_workflow_resume["project_id"],
            "series_id": agent_workflow_resume["series_id"],
            "workflow_type": agent_workflow_resume["workflow_type"],
            **(
                {"runtime_workflow_type": agent_workflow_resume["runtime_workflow_type"]}
                if agent_workflow_resume.get("runtime_workflow_type")
                else {}
            ),
            "launch_source": "agent_workflow_resume",
            "initial_status": agent_workflow_resume["initial_status"],
        }
    if args.require_unknown_workflow_incubation:
        _require(status.get("configured"), "--require-unknown-workflow-incubation requires configured model gateway")
        unknown_workflow_incubation = _validate_unknown_workflow_incubation(
            _request(
                "POST",
                f"{base}/agent/runs",
                {"project_id": args.project_id, "message": UNKNOWN_WORKFLOW_INCUBATION_SMOKE_QUERY},
            )
        )
    if args.require_launched_task:
        if agent_workflow_resume is not None:
            _require(
                launched_task is not None,
                "launched task check failed: agent workflow resume did not produce launched task evidence",
            )
        else:
            launched_task_response = _request(
                "POST",
                f"{base}/series/{args.launch_series_id}/run",
                {"workflow_type": args.launch_workflow_type},
            )
            launched_task_id = _int_metric(launched_task_response.get("id"), launched_task_response.get("task_id"))
            _require(launched_task_id is not None and launched_task_id > 0, "launched task check failed: task_id missing")
            if args.task_id is None:
                args.task_id = launched_task_id
            launched_task = _validate_launched_task(
                launched_task_response,
                task_id=args.task_id,
                series_id=args.launch_series_id,
                workflow_type=args.launch_workflow_type,
                project_id=args.project_id,
            )
    if args.project_id is not None:
        project_series = _request("GET", f"{base}/projects/{args.project_id}/series")
        project_contract = _validate_project_series_contract(
            project_series
        )
        if args.upload_session_id is not None:
            upload_inventory_contract = _validate_upload_inventory_contract(
                _request("GET", f"{base}/projects/{args.project_id}/datasets/{args.upload_session_id}/inventory"),
                args.upload_session_id,
            )
            if args.require_completed_upload:
                _validate_completed_upload_inventory(upload_inventory_contract)
    if args.task_id is not None:
        if args.require_completed_task:
            completed_task_response = (
                _wait_for_completed_task(
                    base,
                    args.task_id,
                    timeout_seconds=args.wait_task_completion_timeout_seconds,
                    poll_seconds=args.wait_task_completion_poll_seconds,
                )
                if args.wait_task_completion_timeout_seconds > 0
                else _request("GET", f"{base}/tasks/{args.task_id}")
            )
            completed_task = _validate_completed_task(
                completed_task_response,
                args.task_id,
                args.project_id,
            )
            if args.project_id is not None:
                if project_series is None:
                    project_series = _request("GET", f"{base}/projects/{args.project_id}/series")
                task_workflow_selection = _validate_task_workflow_selection(project_series, completed_task)
        if args.require_task_events:
            _require(completed_task is not None, "--require-task-events requires completed task evidence")
            task_events = _validate_task_events(
                _request("GET", f"{base}/tasks/{args.task_id}/events"),
                args.task_id,
                completed_task,
            )
        if args.require_observe_repair:
            observe_repair = _validate_observe_repair(
                _request("GET", f"{base}/tasks/{args.task_id}/observe-repair"),
                args.task_id,
            )
        task_artifact_manifest = _validate_task_artifact_manifest(
            _request("GET", f"{base}/tasks/{args.task_id}/artifact-manifest"),
            args.task_id,
            require_native_qc_artifact=bool(args.require_container_native_qc),
            min_native_qc_images=max(args.min_native_qc_images, 0),
            require_scientific_report_artifacts=bool(args.require_scientific_report_artifacts),
            min_scientific_report_images=max(args.min_scientific_report_images, 0),
        )
        task_result_summary = _validate_task_result_summary(
            _request("GET", f"{base}/tasks/{args.task_id}/result-summary"),
            args.task_id,
            completed_task,
            task_artifact_manifest,
        )
        if args.require_container_native_qc or args.min_native_qc_images > 0:
            task_artifact_manifest["container_native_qc_served_urls"] = _validate_container_native_qc_routes(
                base,
                task_artifact_manifest["container_native_qc_artifacts"],
            )
        if args.require_scientific_report_artifacts or args.min_scientific_report_images > 0:
            task_artifact_manifest["scientific_report_served_urls"] = _validate_scientific_report_artifact_routes(
                base,
                task_artifact_manifest["scientific_report_artifacts"],
            )
    smoke_gate = {
        "api_base": base,
        "require_model": bool(args.require_model),
        "skip_agent_run_smoke": bool(args.skip_agent_run_smoke),
        "require_project_agent_context": bool(args.require_project_agent_context),
        "require_agent_workflow_confirmation": bool(args.require_agent_workflow_confirmation),
        "require_agent_workflow_resume": bool(args.require_agent_workflow_resume),
        "require_agent_workflow_fingerprint_negative": bool(args.require_agent_workflow_fingerprint_negative),
        "require_unknown_workflow_incubation": bool(args.require_unknown_workflow_incubation),
        "require_deployment_identity": bool(args.require_deployment_identity),
        "require_production_readiness": bool(args.require_production_readiness),
        "require_runtime_toolchain": bool(args.require_runtime_toolchain),
        "deployment_id": args.deployment_id,
        "min_documents": max(args.min_documents, 0),
        "min_chunks": max(args.min_chunks, 0),
        "require_raw_source_policy": bool(args.require_raw_source_policy),
        "require_vendor_pointer_integrity": bool(args.require_vendor_pointer_integrity),
        "require_elasticsearch_hybrid_rag": bool(args.require_elasticsearch_hybrid_rag),
        "require_real_evidence_ids": bool(args.require_real_evidence_ids),
        "require_completed_upload": bool(args.require_completed_upload),
        "require_uploaded_series": bool(args.require_uploaded_series),
        "require_completed_task": bool(args.require_completed_task),
        "require_launched_task": bool(args.require_launched_task),
        "require_task_events": bool(args.require_task_events),
        "require_observe_repair": bool(args.require_observe_repair),
        "require_launchability_matrix": bool(args.require_launchability_matrix),
        "require_container_native_qc": bool(args.require_container_native_qc),
        "min_native_qc_images": max(args.min_native_qc_images, 0),
        "require_scientific_report_artifacts": bool(args.require_scientific_report_artifacts),
        "min_scientific_report_images": max(args.min_scientific_report_images, 0),
        "project_id": args.project_id,
        "task_id": args.task_id,
        "upload_session_id": args.upload_session_id,
        "uploaded_series_id": uploaded_series.get("series_id") if uploaded_series else None,
        "launch_series_id": args.launch_series_id,
    }
    if args.expected_health_version is not None:
        smoke_gate["expected_health_version"] = args.expected_health_version
    if args.expected_model_wire_api is not None:
        smoke_gate["expected_model_wire_api"] = args.expected_model_wire_api
    if args.expected_model_provider_profile is not None:
        smoke_gate["expected_model_provider_profile"] = args.expected_model_provider_profile
    if args.require_model_tool_loop:
        smoke_gate["require_model_tool_loop"] = True

    model_deployment = safe_model_status.get("deployment") if isinstance(safe_model_status.get("deployment"), dict) else {}
    payload = {
        "generated_at_utc": _generated_at_utc(),
        "smoke_gate": smoke_gate,
        "health": health,
        "deployment_identity_status": "passed" if args.require_deployment_identity else "skipped",
        "deployment_identity": deployment_identity,
        "production_readiness_status": "passed" if args.require_production_readiness else "skipped",
        "production_readiness": production_readiness,
        "fast_launch_readiness_status": fast_launch_readiness_status,
        "fast_launch_readiness": fast_launch_readiness,
        "runtime_toolchain_status": "passed" if runtime_toolchain else "skipped",
        "runtime_toolchain": runtime_toolchain,
        "model_status": safe_model_status,
        "model_smoke_status": model_smoke_status,
        "rag_before": _safe_rag_index_summary(rag_before.get("index")),
        "rag_raw_sources": rag_after.get("vendor_raw_sources"),
        "rag_vendor_pointer_integrity": rag_after.get("vendor_pointer_integrity"),
        "rag_vendor_pointer_integrity_status": (
            vendor_pointer_integrity.get("status") if vendor_pointer_integrity else "skipped"
        ),
        "rag_vendor_pointer_integrity_pointer_count": (
            vendor_pointer_integrity.get("pointer_count") if vendor_pointer_integrity else 0
        ),
        "rag_vendor_pointer_integrity_issue_count": (
            vendor_pointer_integrity.get("issue_count") if vendor_pointer_integrity else 0
        ),
        "rag_vendor_pointer_integrity_referenced_vendor_docs": (
            vendor_pointer_integrity.get("referenced_vendor_docs") if vendor_pointer_integrity else []
        ),
        "rag_vendor_coverage_catalog": vendor_coverage_catalog["catalog"],
        "rag_vendor_coverage_catalog_status": vendor_coverage_catalog["status"],
        "rag_vendor_coverage_catalog_vendor_doc_count": vendor_coverage_catalog["vendor_doc_count"],
        "rag_vendor_coverage_catalog_complete_vendor_doc_count": vendor_coverage_catalog["complete_vendor_doc_count"],
        "rag_vendor_coverage_catalog_incomplete_vendor_doc_count": vendor_coverage_catalog["incomplete_vendor_doc_count"],
        "rag_vendor_coverage_catalog_raw_source_count": vendor_coverage_catalog["raw_source_count"],
        "rag_elasticsearch_hybrid_status": "passed" if elasticsearch_hybrid_rag else "skipped",
        "rag_elasticsearch_hybrid": elasticsearch_hybrid_rag,
        "rag_rebuild_elasticsearch_hybrid": elasticsearch_hybrid_rebuild,
        "rag_elasticsearch_hybrid_query_status": elasticsearch_hybrid_query.get("status") if elasticsearch_hybrid_query else "skipped",
        "rag_elasticsearch_hybrid_query_mode": elasticsearch_hybrid_query.get("mode") if elasticsearch_hybrid_query else None,
        "rag_elasticsearch_hybrid_query_retrieval_source": elasticsearch_hybrid_query.get("retrieval_source") if elasticsearch_hybrid_query else None,
        "rag_elasticsearch_hybrid_query_source": elasticsearch_hybrid_query.get("source") if elasticsearch_hybrid_query else None,
        "rag_elasticsearch_hybrid_query_citation_count": elasticsearch_hybrid_query.get("citation_count") if elasticsearch_hybrid_query else 0,
        "rag_elasticsearch_hybrid_query_top_score": elasticsearch_hybrid_query.get("top_score") if elasticsearch_hybrid_query else 0,
        "rag_elasticsearch_hybrid_query_index": elasticsearch_hybrid_query.get("index") if elasticsearch_hybrid_query else None,
        "rag_elasticsearch_hybrid_query_lexical_retriever": (
            elasticsearch_hybrid_query.get("lexical_retriever") if elasticsearch_hybrid_query else None
        ),
        "rag_elasticsearch_hybrid_query_vector_retriever": (
            elasticsearch_hybrid_query.get("vector_retriever") if elasticsearch_hybrid_query else None
        ),
        "rag_elasticsearch_hybrid_query_dense_vector_field": (
            elasticsearch_hybrid_query.get("dense_vector_field") if elasticsearch_hybrid_query else None
        ),
        "rag_elasticsearch_hybrid_query_fusion": elasticsearch_hybrid_query.get("fusion") if elasticsearch_hybrid_query else None,
        "rag_elasticsearch_hybrid_query_rrf_unavailable_reason": (
            elasticsearch_hybrid_query.get("rrf_unavailable_reason") if elasticsearch_hybrid_query else None
        ),
        "rag_elasticsearch_hybrid_query_dense_vector_dims": elasticsearch_hybrid_query.get("dense_vector_dims") if elasticsearch_hybrid_query else 0,
        "rag_elasticsearch_hybrid_query_embedding_provider": elasticsearch_hybrid_query.get("embedding_provider") if elasticsearch_hybrid_query else None,
        "rag_elasticsearch_hybrid_query_embedding_model": elasticsearch_hybrid_query.get("embedding_model") if elasticsearch_hybrid_query else None,
        "rag_elasticsearch_hybrid_query_embedding_transport": elasticsearch_hybrid_query.get("embedding_transport") if elasticsearch_hybrid_query else None,
        "rag_elasticsearch_hybrid_query_embedding_endpoint_configured": (
            elasticsearch_hybrid_query.get("embedding_endpoint_configured") if elasticsearch_hybrid_query else None
        ),
        "rag_elasticsearch_hybrid_query_embedding_production_ready": (
            elasticsearch_hybrid_query.get("embedding_production_ready") if elasticsearch_hybrid_query else None
        ),
        "rag_document_count": rag.get("document_count"),
        "rag_chunk_count": rag.get("chunk_count"),
        "rag_semantic_index": rag.get("semantic_index"),
        "rag_after": _safe_rag_index_summary(rag_after.get("index")),
        "agent_run_status": run.get("status") if run else "skipped",
        "agent_run_id": run.get("agent_run_id") if run else None,
        "agent_model_gateway_status": "passed" if run else "skipped",
        "agent_model_gateway_access": run.get("model_gateway_access") if run else None,
        "agent_model_transport_access": model_deployment.get("model_gateway_access") if run else None,
        "agent_model_trust_env_proxy": safe_model_status.get("trust_env_proxy") if run else None,
        "agent_safe_metadata": _safe_agent_metadata(run),
        "agent_project_context_status": "passed" if args.require_project_agent_context else "skipped",
        "agent_run_project_id": run.get("project_id") if run else None,
        "agent_workflow_confirmation_status": "passed" if agent_workflow_confirmation else "skipped",
        "agent_workflow_confirmation": agent_workflow_confirmation,
        "agent_workflow_resume_status": "passed" if agent_workflow_resume else "skipped",
        "agent_workflow_resume": agent_workflow_resume,
        "agent_workflow_fingerprint_negative_status": "passed" if agent_workflow_fingerprint_negative else "skipped",
        "agent_workflow_fingerprint_negative": agent_workflow_fingerprint_negative,
        "unknown_workflow_incubation_status": "passed" if unknown_workflow_incubation else "skipped",
        "unknown_workflow_incubation": unknown_workflow_incubation,
        "intent": (run.get("intent") or run.get("agent_intent")) if run else None,
        "agent_intent": (run.get("agent_intent") or run.get("intent")) if run else None,
        "selected_skill": run.get("selected_skill") if run else None,
        "remote_evidence_ids_status": "passed" if args.require_real_evidence_ids else "skipped",
        "remote_evidence_ids": {
            "project_id": args.project_id,
            "upload_session_id": args.upload_session_id,
            "task_id": args.task_id,
        }
        if args.require_real_evidence_ids
        else None,
        "task_status_status": "passed" if args.require_completed_task else "skipped",
        "task_status": completed_task,
        "launched_task_status": "passed" if launched_task else "skipped",
        "launched_task": launched_task,
        "task_workflow_selection_status": "passed" if task_workflow_selection else "skipped",
        "task_workflow_selection": task_workflow_selection,
        "task_events_status": task_events.get("status") if task_events else "skipped",
        "task_events_task_id": task_events.get("task_id") if task_events else None,
        "task_events_event_types": task_events.get("event_types") if task_events else [],
        "task_events_status_event_status": task_events.get("status_event_status") if task_events else None,
        "task_events_remote_log_count": task_events.get("remote_log_count") if task_events else 0,
        "task_events_remote_log_source_stages": task_events.get("remote_log_source_stages") if task_events else [],
        "task_events_main_log_tail_present": task_events.get("main_log_tail_present") if task_events else False,
        "observe_repair_status": observe_repair.get("status") if observe_repair else "skipped",
        "observe_repair_task_id": observe_repair.get("task_id") if observe_repair else None,
        "observe_repair_policy": observe_repair.get("policy") if observe_repair else None,
        "observe_repair_auto_rerun_allowed": observe_repair.get("auto_rerun_allowed") if observe_repair else None,
        "observe_repair_task_creation_allowed": (
            observe_repair.get("task_creation_allowed") if observe_repair else None
        ),
        "observe_repair_forbidden_actions": observe_repair.get("forbidden_actions") if observe_repair else [],
        "observe_repair_production_task_created": observe_repair.get("production_task_created") if observe_repair else None,
        "observe_repair_requires_preflight_before_retry": (
            observe_repair.get("requires_preflight_before_retry") if observe_repair else None
        ),
        "observe_repair_requires_human_confirmation_before_retry": (
            observe_repair.get("requires_human_confirmation_before_retry") if observe_repair else None
        ),
        "observe_repair_repair_suggestion_count": (
            observe_repair.get("repair_suggestion_count") if observe_repair else 0
        ),
        "rag_launchability_matrix_status": launchability_matrix.get("status") if launchability_matrix else "skipped",
        "rag_launchability_matrix_source": launchability_matrix.get("source") if launchability_matrix else None,
        "rag_launchability_query_status": launchability_query.get("status") if launchability_query else "skipped",
        "rag_launchability_query_intent": launchability_query.get("intent") if launchability_query else None,
        "rag_launchability_query_source": launchability_query.get("source") if launchability_query else None,
        "project_contract_status": project_contract.get("status") if project_contract else "skipped",
        "series_count": project_contract.get("series_count") if project_contract else 0,
        "series_with_workflow_eligibility": project_contract.get("series_with_workflow_eligibility") if project_contract else 0,
        "series_modalities": project_contract.get("modalities") if project_contract else [],
        "project_workflow_eligibility_metadata_status": project_contract.get("workflow_metadata_status") if project_contract else "skipped",
        "project_workflow_eligibility_metadata_required_fields": project_contract.get("workflow_metadata_required_fields") if project_contract else [],
        "project_workflow_eligibility_metadata_workflow_types": project_contract.get("workflow_metadata_workflow_types") if project_contract else [],
        "project_workflow_eligibility_metadata_item_count": project_contract.get("workflow_metadata_item_count") if project_contract else 0,
        "upload_inventory_contract_status": upload_inventory_contract.get("status") if upload_inventory_contract else "skipped",
        "upload_inventory_completion_status": "passed" if args.require_completed_upload else "skipped",
        "upload_inventory_session_id": upload_inventory_contract.get("upload_session_id") if upload_inventory_contract else None,
        "upload_inventory_status": upload_inventory_contract.get("inventory_status") if upload_inventory_contract else None,
        "upload_inventory_series_count": upload_inventory_contract.get("series_count") if upload_inventory_contract else 0,
        "upload_inventory_series_ids": upload_inventory_contract.get("series_ids") if upload_inventory_contract else [],
        "upload_inventory_series_with_workflow_eligibility": upload_inventory_contract.get("series_with_workflow_eligibility") if upload_inventory_contract else 0,
        "upload_inventory_modalities": upload_inventory_contract.get("modalities") if upload_inventory_contract else [],
        "upload_inventory_workflow_eligibility_metadata_status": upload_inventory_contract.get("workflow_metadata_status") if upload_inventory_contract else "skipped",
        "upload_inventory_workflow_eligibility_metadata_required_fields": upload_inventory_contract.get("workflow_metadata_required_fields") if upload_inventory_contract else [],
        "upload_inventory_workflow_eligibility_metadata_workflow_types": upload_inventory_contract.get("workflow_metadata_workflow_types") if upload_inventory_contract else [],
        "upload_inventory_workflow_eligibility_metadata_item_count": upload_inventory_contract.get("workflow_metadata_item_count") if upload_inventory_contract else 0,
        "uploaded_series_status": "passed" if uploaded_series else "skipped",
        "uploaded_series": uploaded_series,
        "task_artifact_manifest_status": task_artifact_manifest.get("status") if task_artifact_manifest else "skipped",
        "task_result_summary_status": "passed" if task_result_summary else "skipped",
        "task_result_summary": task_result_summary,
        "artifact_manifest_task_id": task_artifact_manifest.get("task_id") if task_artifact_manifest else None,
        "artifact_manifest_artifact_count": task_artifact_manifest.get("artifact_count") if task_artifact_manifest else 0,
        "artifact_manifest_preview_kinds": task_artifact_manifest.get("preview_kinds") if task_artifact_manifest else [],
        "artifact_manifest_relative_paths": task_artifact_manifest.get("artifact_relative_paths") if task_artifact_manifest else [],
        "artifact_manifest_download_urls": task_artifact_manifest.get("artifact_download_urls") if task_artifact_manifest else [],
        "artifact_manifest_result_summary_available": task_artifact_manifest.get("result_summary_available") if task_artifact_manifest else None,
        "container_native_qc_status": task_artifact_manifest.get("container_native_qc_status") if task_artifact_manifest else "skipped",
        "container_native_qc_artifact_count": task_artifact_manifest.get("container_native_qc_artifact_count") if task_artifact_manifest else 0,
        "container_native_qc_image_count": task_artifact_manifest.get("container_native_qc_image_count") if task_artifact_manifest else 0,
        "container_native_qc_html_count": task_artifact_manifest.get("container_native_qc_html_count") if task_artifact_manifest else 0,
        "container_native_qc_preview_kinds": task_artifact_manifest.get("container_native_qc_preview_kinds") if task_artifact_manifest else [],
        "container_native_qc_relative_paths": task_artifact_manifest.get("container_native_qc_relative_paths") if task_artifact_manifest else [],
        "container_native_qc_served_urls": task_artifact_manifest.get("container_native_qc_served_urls") if task_artifact_manifest else [],
        "container_native_qc_artifacts": task_artifact_manifest.get("container_native_qc_artifacts") if task_artifact_manifest else [],
        "container_native_qc_official_source_ids": task_artifact_manifest.get("container_native_qc_official_source_ids") if task_artifact_manifest else [],
        "scientific_report_artifacts_status": task_artifact_manifest.get("scientific_report_artifacts_status") if task_artifact_manifest else "skipped",
        "scientific_report_artifact_count": task_artifact_manifest.get("scientific_report_artifact_count") if task_artifact_manifest else 0,
        "scientific_report_image_count": task_artifact_manifest.get("scientific_report_image_count") if task_artifact_manifest else 0,
        "scientific_report_html_count": task_artifact_manifest.get("scientific_report_html_count") if task_artifact_manifest else 0,
        "scientific_report_json_count": task_artifact_manifest.get("scientific_report_json_count") if task_artifact_manifest else 0,
        "scientific_report_preview_kinds": task_artifact_manifest.get("scientific_report_preview_kinds") if task_artifact_manifest else [],
        "scientific_report_relative_paths": task_artifact_manifest.get("scientific_report_relative_paths") if task_artifact_manifest else [],
        "scientific_report_served_urls": task_artifact_manifest.get("scientific_report_served_urls") if task_artifact_manifest else [],
        "scientific_report_artifacts": task_artifact_manifest.get("scientific_report_artifacts") if task_artifact_manifest else [],
    }
    if args.output_json:
        _write_output_json(args.output_json, payload)
    print(json.dumps(payload, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
