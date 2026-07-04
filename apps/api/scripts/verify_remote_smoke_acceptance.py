from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit
from urllib.parse import quote


LAUNCHABILITY_MATRIX_SOURCE = "docs/rag/workflows/workflow_launchability_matrix.md"
ELASTICSEARCH_HYBRID_CONTRACT_SOURCE = "docs/rag/contracts/elasticsearch-hybrid-search.md"
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
STRICT_REMOTE_ACCEPTANCE_MISSING_REASON = (
    "Strict remote acceptance evidence has not been verified for the upload-agent-workflow-result chain."
)
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


def _rrf_unavailable_reason(metadata: dict) -> str:
    return str(metadata.get("rrf_unavailable_reason") or "").strip()


def _require_elasticsearch_fusion(metadata: dict, *, context: str) -> tuple[str, str | None]:
    fusion = str(metadata.get("fusion") or "").strip()
    reason = _rrf_unavailable_reason(metadata)
    if fusion == "rrf":
        return fusion, None
    _require(
        fusion == "query_plus_knn" and reason == ELASTICSEARCH_ACCEPTED_FUSION_FALLBACK_REASON,
        f"{context}.fusion must be rrf or query_plus_knn with rrf_unavailable_reason=license_non_compliant",
    )
    return fusion, reason


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(message)


def _verify_no_saved_official_sources(value: object, *, path: str = "") -> None:
    if isinstance(value, dict):
        for key, nested in value.items():
            child_path = f"{path}.{key}" if path else str(key)
            _require(key != "official_sources", f"{child_path} must not be saved")
            _verify_no_saved_official_sources(nested, path=child_path)
    elif isinstance(value, list):
        for index, nested in enumerate(value):
            _verify_no_saved_official_sources(nested, path=f"{path}[{index}]")


def _int_metric(value: object) -> int:
    if isinstance(value, bool):
        return 0
    try:
        if value is not None:
            return int(value)
    except (TypeError, ValueError):
        return 0
    return 0


def _require_int_metric(payload: dict, key: str) -> int:
    value = payload.get(key)
    _require(isinstance(value, int) and not isinstance(value, bool), f"{key} must be an integer")
    return value


def _require_positive_int_metric(payload: dict, key: str) -> int:
    value = _require_int_metric(payload, key)
    _require(value > 0, f"{key} must be greater than zero")
    return value


def _require_positive_numeric_metric(payload: dict, key: str) -> float:
    value = payload.get(key)
    _require(isinstance(value, (int, float)) and not isinstance(value, bool), f"{key} must be numeric")
    numeric = float(value)
    _require(numeric > 0, f"{key} must be greater than zero")
    return numeric


def _require_positive_int_metric_with_prefix(payload: dict, key: str, *, prefix: str) -> int:
    value = payload.get(key)
    _require(isinstance(value, int) and not isinstance(value, bool), f"{prefix}.{key} must be an integer")
    _require(value > 0, f"{prefix}.{key} must be greater than zero")
    return value


def _require_positive_id(payload: dict, key: str, *, prefix: str) -> int:
    value = payload.get(key)
    _require(isinstance(value, int) and not isinstance(value, bool) and value > 0, f"{prefix}.{key} must be a positive integer")
    return value


def _require_status(payload: dict, key: str, expected: str = "passed") -> None:
    _require(payload.get(key) == expected, f"{key} must be {expected}")


def _require_privacy_safe_symbol(payload: dict, key: str) -> None:
    value = payload.get(key)
    _require(
        _is_privacy_safe_symbol(value),
        f"{key} must be privacy-safe",
    )


def _require_prefixed_privacy_safe_symbol(payload: dict, key: str, *, prefix: str) -> None:
    value = payload.get(key)
    _require(
        _is_privacy_safe_symbol(value),
        f"{prefix}.{key} must be privacy-safe",
    )


def _verify_no_debug_only_workflows(payload: dict) -> None:
    for section_name in (
        "task_status",
        "launched_task",
        "agent_workflow_confirmation",
        "task_workflow_selection",
        "task_result_summary",
    ):
        section = payload.get(section_name)
        if not isinstance(section, dict):
            continue
        workflow_type = section.get("workflow_type")
        if workflow_type in DEBUG_ONLY_WORKFLOWS:
            raise SystemExit(f"strict deployment acceptance cannot use debug-only workflow {workflow_type}")


def _is_privacy_safe_symbol(value: object) -> bool:
    return (
        isinstance(value, str)
        and bool(value)
        and len(value) <= 140
        and all(char.isalnum() or char in "_.-" for char in value)
    )


def _requires_direct_model_gateway(status: dict, expected_provider_profile: object) -> bool:
    provider_profile = str(status.get("provider_profile") or "").strip().lower()
    expected_profile = str(expected_provider_profile or "").strip().lower()
    if provider_profile == "rawchat" or expected_profile == "rawchat":
        return True
    base_url = status.get("base_url")
    if not isinstance(base_url, str) or not base_url:
        return False
    host = (urlsplit(base_url).hostname or "").lower()
    return host == "rawchat.cn" or host.endswith(".rawchat.cn")


def _verify_model_status(payload: dict, gate: dict) -> None:
    status = payload.get("model_status")
    _require(isinstance(status, dict), "model_status must be present")
    _require(status.get("configured") is True, "model_status.configured must be true")
    blocked_keys = {"api_key", "token", "secret", "password", "authorization"}
    for key in status:
        key_text = str(key).lower()
        _require(not any(blocked in key_text for blocked in blocked_keys), f"model_status must not expose {key}")
    base_url = status.get("base_url")
    if base_url is not None:
        _require(isinstance(base_url, str) and bool(base_url), "model_status.base_url must be a string")
        parsed = urlsplit(base_url)
        _require(not parsed.username and not parsed.password, "model_status.base_url must not contain credentials")
        _require(parsed.scheme in {"http", "https"}, "model_status.base_url must be http or https")
    for key in ("provider", "provider_profile", "model", "review_model", "wire_api", "reasoning_effort"):
        value = status.get(key)
        if value is not None:
            _require(_is_privacy_safe_symbol(value), f"model_status.{key} must be privacy-safe")
    expected_wire_api = gate.get("expected_model_wire_api")
    _require(
        status.get("wire_api") == expected_wire_api,
        "model_status.wire_api must match smoke_gate.expected_model_wire_api",
    )
    expected_provider_profile = gate.get("expected_model_provider_profile")
    _require(
        status.get("provider_profile") == expected_provider_profile,
        "model_status.provider_profile must match smoke_gate.expected_model_provider_profile",
    )
    capabilities = status.get("capabilities")
    _require(isinstance(capabilities, dict), "model_status.capabilities must be an object")
    allowed_capability_keys = {"text", "structured_json", "model_tool_loop"}
    for key, value in capabilities.items():
        key_text = str(key)
        _require(key_text in allowed_capability_keys, f"model_status.capabilities must not expose {key_text}")
        _require(isinstance(value, bool), f"model_status.capabilities.{key_text} must be boolean")
    if gate.get("require_model_tool_loop") is True:
        _require(
            capabilities.get("model_tool_loop") is True,
            "model_status.capabilities.model_tool_loop must be true",
        )
    trust_env_proxy = status.get("trust_env_proxy")
    if trust_env_proxy is not None:
        _require(isinstance(trust_env_proxy, bool), "model_status.trust_env_proxy must be boolean")
    deployment = status.get("deployment")
    if deployment is not None:
        _require(isinstance(deployment, dict), "model_status.deployment must be an object")
        allowed_deployment_keys = {"backend_runtime_mode", "model_gateway_access"}
        for key, value in deployment.items():
            key_text = str(key)
            _require(key_text in allowed_deployment_keys, f"model_status.deployment must not expose {key_text}")
            _require(_is_privacy_safe_symbol(value), f"model_status.deployment.{key_text} must be privacy-safe")
    if _requires_direct_model_gateway(status, expected_provider_profile):
        _require(
            status.get("trust_env_proxy") is False,
            "rawchat model_status.trust_env_proxy must be false",
        )
        _require(isinstance(deployment, dict), "model_status.deployment must be present for rawchat direct acceptance")
        _require(
            deployment.get("model_gateway_access") == "direct",
            "rawchat model_status.deployment.model_gateway_access must be direct",
        )
    gateway_diagnostics = status.get("gateway_diagnostics")
    if gateway_diagnostics is not None:
        _require(isinstance(gateway_diagnostics, dict), "model_status.gateway_diagnostics must be an object")
        allowed_gateway_diagnostic_keys = {
            "sdk_method",
            "request_shape",
            "structured_output",
            "model_tool_loop",
            "workflow_task_creation",
        }
        for key, value in gateway_diagnostics.items():
            key_text = str(key)
            _require(
                key_text in allowed_gateway_diagnostic_keys,
                f"model_status.gateway_diagnostics must not expose {key_text}",
            )
            _require(
                _is_privacy_safe_symbol(value),
                f"model_status.gateway_diagnostics.{key_text} must be privacy-safe",
            )


def _parse_utc_timestamp(value: object, *, key: str) -> datetime:
    _require(isinstance(value, str) and bool(value), f"{key} must be an ISO-8601 UTC timestamp")
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise SystemExit(f"{key} must be an ISO-8601 UTC timestamp") from exc
    _require(parsed.tzinfo is not None and parsed.utcoffset() is not None, f"{key} must be timezone-aware")
    return parsed.astimezone(timezone.utc)


def _verify_generated_at_utc(
    payload: dict,
    *,
    max_age_hours: float | None = None,
    now_utc: datetime | None = None,
) -> tuple[datetime, float | None]:
    generated_at = _parse_utc_timestamp(payload.get("generated_at_utc"), key="generated_at_utc")
    if max_age_hours is not None:
        _require(max_age_hours >= 0, "max_age_hours must be non-negative")
        now = now_utc or datetime.now(timezone.utc)
        _require(now.tzinfo is not None and now.utcoffset() is not None, "now_utc must be timezone-aware")
        age_hours = (now.astimezone(timezone.utc) - generated_at).total_seconds() / 3600
        _require(age_hours >= 0, "generated_at_utc must not be in the future")
        _require(age_hours <= max_age_hours, f"generated_at_utc is older than {max_age_hours:g} hours")
    return generated_at, max_age_hours


def _require_positive_int(payload: dict, key: str) -> None:
    _require_positive_int_metric(payload, key)


def _verify_gate_settings(payload: dict) -> dict:
    gate = payload.get("smoke_gate") if isinstance(payload.get("smoke_gate"), dict) else {}
    for key in (
        "require_model",
        "require_model_tool_loop",
        "require_deployment_identity",
        "require_production_readiness",
        "require_completed_task",
        "require_launched_task",
        "require_project_agent_context",
        "require_agent_workflow_confirmation",
        "require_agent_workflow_resume",
        "require_agent_workflow_fingerprint_negative",
        "require_unknown_workflow_incubation",
        "require_raw_source_policy",
        "require_vendor_pointer_integrity",
        "require_elasticsearch_hybrid_rag",
        "require_runtime_toolchain",
        "require_real_evidence_ids",
        "require_completed_upload",
        "require_uploaded_series",
        "require_launchability_matrix",
        "require_task_events",
        "require_observe_repair",
        "require_container_native_qc",
        "require_scientific_report_artifacts",
    ):
        _require(gate.get(key) is True, f"smoke_gate.{key} must be true")
    for key in ("project_id", "upload_session_id", "uploaded_series_id", "task_id"):
        _require_positive_id(gate, key, prefix="smoke_gate")
    expected_health_version = gate.get("expected_health_version")
    if expected_health_version is not None:
        _require_privacy_safe_symbol(gate, "expected_health_version")
    _require_privacy_safe_symbol(gate, "expected_model_wire_api")
    _require_privacy_safe_symbol(gate, "expected_model_provider_profile")
    _require_positive_int_metric(gate, "min_documents")
    _require_positive_int_metric(gate, "min_chunks")
    _require_positive_int_metric(gate, "min_native_qc_images")
    _require_positive_int_metric(gate, "min_scientific_report_images")
    _require_privacy_safe_symbol(gate, "deployment_id")
    return gate


def _verify_production_readiness(payload: dict) -> None:
    _require_status(payload, "production_readiness_status")
    readiness = payload.get("production_readiness")
    _require(isinstance(readiness, dict), "production_readiness must be present")
    _require(readiness.get("required") is True, "production_readiness.required must be true")
    _require(readiness.get("ready") is True, "production_readiness.ready must be true")
    _require(readiness.get("status") == "ready", "production_readiness.status must be ready")
    blocking_reasons = readiness.get("blocking_reasons")
    _require(isinstance(blocking_reasons, list), "production_readiness.blocking_reasons must be a list")
    _require(not blocking_reasons, "production_readiness.blocking_reasons must be empty")


def _verify_fast_launch_readiness(payload: dict) -> dict:
    readiness_status = payload.get("fast_launch_readiness_status")
    _require(
        readiness_status in {"passed", "pre_acceptance"},
        "fast_launch_readiness_status must be passed or pre_acceptance",
    )
    readiness = payload.get("fast_launch_readiness")
    _require(isinstance(readiness, dict), "fast_launch_readiness must be present")
    blocking_reasons = readiness.get("blocking_reasons")
    _require(isinstance(blocking_reasons, list), "fast_launch_readiness.blocking_reasons must be a list")
    checks = readiness.get("checks")
    _require(isinstance(checks, dict), "fast_launch_readiness.checks must be present")
    rag_check = checks.get("rag_elasticsearch_hybrid")
    _require(
        isinstance(rag_check, dict),
        "fast_launch_readiness.checks.rag_elasticsearch_hybrid must be present",
    )
    _require(
        rag_check.get("status") == "passed",
        "fast_launch_readiness.checks.rag_elasticsearch_hybrid.status must be passed",
    )
    production_deployment = checks.get("production_deployment")
    _require(
        isinstance(production_deployment, dict),
        "fast_launch_readiness.checks.production_deployment must be present",
    )
    _require(
        production_deployment.get("status") == "passed",
        "fast_launch_readiness.checks.production_deployment.status must be passed",
    )
    _require(
        production_deployment.get("required") is True,
        "fast_launch_readiness.checks.production_deployment.required must be true",
    )
    _require(
        production_deployment.get("ready") is True,
        "fast_launch_readiness.checks.production_deployment.ready must be true",
    )
    _require(
        production_deployment.get("readiness_status") == "ready",
        "fast_launch_readiness.checks.production_deployment.readiness_status must be ready",
    )
    production_deployment_blockers = production_deployment.get("blocking_reasons")
    _require(
        isinstance(production_deployment_blockers, list),
        "fast_launch_readiness.checks.production_deployment.blocking_reasons must be a list",
    )
    _require(
        not production_deployment_blockers,
        "fast_launch_readiness.checks.production_deployment.blocking_reasons must be empty",
    )
    for check_name in (
        "model_gateway_target",
        "agent_task_boundary",
        "upload_workflow_result_contract",
    ):
        check = checks.get(check_name)
        _require(isinstance(check, dict), f"fast_launch_readiness.checks.{check_name} must be present")
        _require(
            check.get("status") == "passed",
            f"fast_launch_readiness.checks.{check_name}.status must be passed",
        )
    strict_remote_acceptance = checks.get("strict_remote_acceptance")
    _require(
        isinstance(strict_remote_acceptance, dict),
        "fast_launch_readiness.checks.strict_remote_acceptance must be present",
    )
    strict_status = strict_remote_acceptance.get("status")
    if readiness_status == "passed":
        _require(readiness.get("ready") is True, "fast_launch_readiness.ready must be true")
        _require(readiness.get("status") == "ready", "fast_launch_readiness.status must be ready")
        _require(not blocking_reasons, "fast_launch_readiness.blocking_reasons must be empty")
        _require(
            strict_status == "passed",
            "fast_launch_readiness.checks.strict_remote_acceptance.status must be passed",
        )
    else:
        _require(readiness.get("ready") is False, "fast_launch_readiness.ready must be false before acceptance")
        _require(readiness.get("status") == "blocked", "fast_launch_readiness.status must be blocked before acceptance")
        _require(
            blocking_reasons == [STRICT_REMOTE_ACCEPTANCE_MISSING_REASON],
            "fast_launch_readiness.blocking_reasons must explain missing strict remote acceptance evidence",
        )
        _require(
            strict_status == "missing",
            "fast_launch_readiness.checks.strict_remote_acceptance.status must be missing before acceptance",
        )
    _require(rag_check.get("engine") == "elasticsearch", "fast_launch_readiness.checks.rag_elasticsearch_hybrid.engine must be elasticsearch")
    _require(rag_check.get("configured") is True, "fast_launch_readiness.checks.rag_elasticsearch_hybrid.configured must be true")
    _require(rag_check.get("persisted") is True, "fast_launch_readiness.checks.rag_elasticsearch_hybrid.persisted must be true")
    _require(rag_check.get("mode") == "connected", "fast_launch_readiness.checks.rag_elasticsearch_hybrid.mode must be connected")
    _require(_is_privacy_safe_symbol(rag_check.get("index")), "fast_launch_readiness.checks.rag_elasticsearch_hybrid.index must be privacy-safe")
    _require_positive_int_metric_with_prefix(
        rag_check,
        "indexed_chunk_count",
        prefix="fast_launch_readiness.checks.rag_elasticsearch_hybrid",
    )
    _require_positive_int_metric_with_prefix(
        rag_check,
        "dense_vector_dims",
        prefix="fast_launch_readiness.checks.rag_elasticsearch_hybrid",
    )
    embedding_provider = str(rag_check.get("embedding_provider") or "").strip()
    _require(
        embedding_provider and embedding_provider.lower() not in LOCAL_EMBEDDING_PROVIDERS,
        "fast_launch_readiness.checks.rag_elasticsearch_hybrid.embedding_provider must be production configured",
    )
    _require(
        _is_privacy_safe_symbol(rag_check.get("embedding_model")),
        "fast_launch_readiness.checks.rag_elasticsearch_hybrid.embedding_model must be present",
    )
    embedding_transport = str(rag_check.get("embedding_transport") or "").strip()
    _require(
        embedding_transport,
        "fast_launch_readiness.checks.rag_elasticsearch_hybrid.embedding_transport must be present",
    )
    _require(
        embedding_transport in {"sdk", "openai_compatible_http"},
        "fast_launch_readiness.checks.rag_elasticsearch_hybrid.embedding_transport must be production-safe",
    )
    _require(
        rag_check.get("embedding_production_ready") is True,
        "fast_launch_readiness.checks.rag_elasticsearch_hybrid.embedding_production_ready must be true",
    )
    _require(
        rag_check.get("embedding_endpoint_configured") is True,
        "fast_launch_readiness.checks.rag_elasticsearch_hybrid.embedding_endpoint_configured must be true",
    )
    _require(rag_check.get("fusion") == "rrf", "fast_launch_readiness.checks.rag_elasticsearch_hybrid.fusion must be rrf")
    rag_status = payload.get("rag_elasticsearch_hybrid") if isinstance(payload.get("rag_elasticsearch_hybrid"), dict) else {}
    for key in (
        "index",
        "mode",
        "indexed_chunk_count",
        "dense_vector_dims",
        "embedding_provider",
        "embedding_model",
        "embedding_transport",
        "embedding_endpoint_configured",
    ):
        _require(
            rag_check.get(key) == rag_status.get(key),
            f"fast_launch_readiness.checks.rag_elasticsearch_hybrid.{key} must match rag_elasticsearch_hybrid",
        )
    return rag_check


def _verify_task_status(payload: dict, gate: dict) -> None:
    _require_status(payload, "task_status_status")
    task_status = payload.get("task_status")
    _require(isinstance(task_status, dict), "task_status must be present")
    _require(task_status.get("task_id") == gate.get("task_id"), "task_status.task_id must match smoke_gate.task_id")
    _require(task_status.get("project_id") == gate.get("project_id"), "task_status.project_id must match smoke_gate.project_id")
    _require(task_status.get("status") == "completed", "task_status.status must be completed")
    _require_positive_id(task_status, "series_id", prefix="task_status")
    _require_privacy_safe_symbol(task_status, "workflow_type")


def _verify_runtime_toolchain(payload: dict) -> dict:
    _require_status(payload, "runtime_toolchain_status")
    runtime = payload.get("runtime_toolchain")
    _require(isinstance(runtime, dict), "runtime_toolchain must be present")
    allowed_keys = {
        "workflow_tool_execution",
        "docker_runtime_host",
        "docker_requires_sudo",
        "fs_license_exists",
        "workflow_count",
        "available_workflow_count",
        "required_workflow_type",
        "required_runtime_workflow_type",
        "required_workflow_available",
        "unavailable_workflows",
        "workflow_types",
    }
    for key in runtime:
        _require(key in allowed_keys, f"runtime_toolchain must not expose {key}")
    _require(
        runtime.get("workflow_tool_execution") == "deployment_server_local",
        "runtime_toolchain.workflow_tool_execution must be deployment_server_local",
    )
    _require(runtime.get("docker_runtime_host") == "api_server", "runtime_toolchain.docker_runtime_host must be api_server")
    _require(isinstance(runtime.get("docker_requires_sudo"), bool), "runtime_toolchain.docker_requires_sudo must be boolean")
    _require(runtime.get("fs_license_exists") is True, "runtime_toolchain.fs_license_exists must be true")
    _require_positive_int_metric_with_prefix(runtime, "workflow_count", prefix="runtime_toolchain")
    available_count = _require_positive_int_metric_with_prefix(
        runtime,
        "available_workflow_count",
        prefix="runtime_toolchain",
    )
    _require(
        available_count <= runtime["workflow_count"],
        "runtime_toolchain.available_workflow_count cannot exceed workflow_count",
    )
    for key in ("workflow_types", "unavailable_workflows"):
        values = runtime.get(key)
        _require(isinstance(values, list), f"runtime_toolchain.{key} must be a list")
        for value in values:
            _require(_is_privacy_safe_symbol(value), f"runtime_toolchain.{key} entries must be privacy-safe")
    required_workflow_type = runtime.get("required_workflow_type")
    _require(_is_privacy_safe_symbol(required_workflow_type), "runtime_toolchain.required_workflow_type must be privacy-safe")
    task_status = payload.get("task_status") if isinstance(payload.get("task_status"), dict) else {}
    _require(
        required_workflow_type == task_status.get("workflow_type"),
        "runtime_toolchain.required_workflow_type must match task_status.workflow_type",
    )
    has_required_runtime_workflow_type = "required_runtime_workflow_type" in runtime
    required_runtime_workflow_type = runtime.get("required_runtime_workflow_type") if has_required_runtime_workflow_type else None
    workflow_type_required_in_runtime = required_workflow_type
    if has_required_runtime_workflow_type:
        _require(
            _is_privacy_safe_symbol(required_runtime_workflow_type),
            "runtime_toolchain.required_runtime_workflow_type must be privacy-safe",
        )
        workflow_type_required_in_runtime = required_runtime_workflow_type
    task_runtime_workflow_type = task_status.get("runtime_workflow_type")
    if has_required_runtime_workflow_type and isinstance(task_runtime_workflow_type, str) and task_runtime_workflow_type:
        _require(
            required_runtime_workflow_type == task_runtime_workflow_type,
            "runtime_toolchain.required_runtime_workflow_type must match task_status.runtime_workflow_type",
        )
    _require(
        workflow_type_required_in_runtime in runtime.get("workflow_types", []),
        "runtime_toolchain.workflow_types must include required_runtime_workflow_type"
        if has_required_runtime_workflow_type
        else "runtime_toolchain.workflow_types must include required_workflow_type",
    )
    _require(runtime.get("required_workflow_available") is True, "runtime_toolchain.required_workflow_available must be true")
    _require(
        workflow_type_required_in_runtime not in runtime.get("unavailable_workflows", []),
        "runtime_toolchain.unavailable_workflows must not include required_runtime_workflow_type"
        if has_required_runtime_workflow_type
        else "runtime_toolchain.unavailable_workflows must not include required_workflow_type",
    )
    return runtime


def _verify_task_events(payload: dict, gate: dict) -> None:
    _require_status(payload, "task_events_status")
    _require(payload.get("task_events_task_id") == gate.get("task_id"), "task_events_task_id must match smoke_gate.task_id")
    event_types = payload.get("task_events_event_types")
    _require(isinstance(event_types, list) and "task.status" in event_types, "task_events_event_types must include task.status")
    _require(isinstance(event_types, list) and "task.remote_log" in event_types, "task_events_event_types must include task.remote_log")
    task_status = payload.get("task_status") if isinstance(payload.get("task_status"), dict) else {}
    _require(
        payload.get("task_events_status_event_status") == task_status.get("status") == "completed",
        "task_events_status_event_status must be completed",
    )
    _require_positive_int(payload, "task_events_remote_log_count")
    source_stages = payload.get("task_events_remote_log_source_stages")
    _require(
        isinstance(source_stages, list)
        and source_stages
        and all(_is_privacy_safe_symbol(item) for item in source_stages),
        "task_events_remote_log_source_stages must be non-empty privacy-safe symbols",
    )
    _require(payload.get("task_events_main_log_tail_present") is True, "task_events_main_log_tail_present must be true")


def _verify_observe_repair(payload: dict, gate: dict) -> None:
    _require_status(payload, "observe_repair_status")
    _require(payload.get("observe_repair_task_id") == gate.get("task_id"), "observe_repair_task_id must match smoke_gate.task_id")
    _require(
        payload.get("observe_repair_policy") == "read_only_observe_repair",
        "observe_repair_policy must be read_only_observe_repair",
    )
    _require(payload.get("observe_repair_auto_rerun_allowed") is False, "observe_repair_auto_rerun_allowed must be false")
    _require(
        payload.get("observe_repair_task_creation_allowed") is False,
        "observe_repair_task_creation_allowed must be false",
    )
    forbidden_actions = payload.get("observe_repair_forbidden_actions")
    _require(
        isinstance(forbidden_actions, list)
        and {"auto_retry", "auto_rerun", "task_creation"}.issubset(set(forbidden_actions)),
        "observe_repair_forbidden_actions must include auto_retry, auto_rerun, and task_creation",
    )
    _require(
        payload.get("observe_repair_production_task_created") is False,
        "observe_repair_production_task_created must be false",
    )
    _require(
        payload.get("observe_repair_requires_preflight_before_retry") is True,
        "observe_repair_requires_preflight_before_retry must be true",
    )
    _require(
        payload.get("observe_repair_requires_human_confirmation_before_retry") is True,
        "observe_repair_requires_human_confirmation_before_retry must be true",
    )
    _require_positive_int(payload, "observe_repair_repair_suggestion_count")


def _verify_launched_task(payload: dict, gate: dict) -> None:
    _require_status(payload, "launched_task_status")
    task_status = payload.get("task_status")
    launched_task = payload.get("launched_task")
    _require(isinstance(task_status, dict), "task_status must be present")
    _require(isinstance(launched_task, dict), "launched_task must be present")
    _require_positive_id(launched_task, "task_id", prefix="launched_task")
    _require_positive_id(launched_task, "project_id", prefix="launched_task")
    _require_positive_id(launched_task, "series_id", prefix="launched_task")
    _require(
        launched_task.get("task_id") == gate.get("task_id"),
        "launched_task.task_id must match smoke_gate.task_id",
    )
    _require(
        launched_task.get("project_id") == gate.get("project_id"),
        "launched_task.project_id must match smoke_gate.project_id",
    )
    _require(
        launched_task.get("series_id") == task_status.get("series_id"),
        "launched_task.series_id must match task_status.series_id",
    )
    _require(
        launched_task.get("workflow_type") == task_status.get("workflow_type"),
        "launched_task.workflow_type must match task_status.workflow_type",
    )
    _require(
        task_status.get("runtime_workflow_type") is not None,
        "task_status.runtime_workflow_type must be present",
    )
    _require_privacy_safe_symbol(task_status, "runtime_workflow_type")
    _require(
        launched_task.get("launch_source") == "agent_workflow_resume",
        "launched_task.launch_source must be agent_workflow_resume",
    )
    _require(
        launched_task.get("runtime_workflow_type") is not None,
        "launched_task.runtime_workflow_type must be present",
    )
    _require_privacy_safe_symbol(launched_task, "runtime_workflow_type")
    _require(
        task_status.get("runtime_workflow_type") == launched_task.get("runtime_workflow_type"),
        "task_status.runtime_workflow_type must match launched_task.runtime_workflow_type",
    )
    _require_privacy_safe_symbol(launched_task, "workflow_type")
    _require_privacy_safe_symbol(launched_task, "launch_source")
    _require_privacy_safe_symbol(launched_task, "initial_status")


def _verify_uploaded_series(payload: dict, gate: dict) -> None:
    _require_status(payload, "uploaded_series_status")
    task_status = payload.get("task_status")
    uploaded_series = payload.get("uploaded_series")
    _require(isinstance(task_status, dict), "task_status must be present")
    _require(isinstance(uploaded_series, dict), "uploaded_series must be present")
    _require_positive_id(uploaded_series, "project_id", prefix="uploaded_series")
    _require_positive_id(uploaded_series, "series_id", prefix="uploaded_series")
    _require(
        uploaded_series.get("project_id") == gate.get("project_id"),
        "uploaded_series.project_id must match smoke_gate.project_id",
    )
    _require(
        uploaded_series.get("series_id") == task_status.get("series_id"),
        "uploaded_series.series_id must match task_status.series_id",
    )
    _require(
        uploaded_series.get("series_id") == gate.get("uploaded_series_id"),
        "uploaded_series.series_id must match smoke_gate.uploaded_series_id",
    )
    _require_privacy_safe_symbol(uploaded_series, "modality")
    if uploaded_series.get("sequence_label") is not None:
        _require_privacy_safe_symbol(uploaded_series, "sequence_label")


def _verify_task_workflow_selection(payload: dict) -> None:
    _require_status(payload, "task_workflow_selection_status")
    task_status = payload.get("task_status")
    selection = payload.get("task_workflow_selection")
    _require(isinstance(task_status, dict), "task_status must be present")
    _require(isinstance(selection, dict), "task_workflow_selection must be present")
    _require(
        selection.get("matched_runnable_workflow") is True,
        "task_workflow_selection.matched_runnable_workflow must be true",
    )
    _require(
        selection.get("series_id") == task_status.get("series_id"),
        "task_workflow_selection.series_id must match task_status.series_id",
    )
    _require(
        selection.get("workflow_type") == task_status.get("workflow_type"),
        "task_workflow_selection.workflow_type must match task_status.workflow_type",
    )


def _verify_workflow_metadata(
    metadata: object,
    *,
    workflow_type: object,
    runtime_workflow_type: object,
    runtime_source: str,
    prefix: str,
) -> None:
    _require(isinstance(metadata, dict), f"{prefix}.workflow_metadata must be present")
    _require(
        metadata.get("workflow_type") == workflow_type,
        f"{prefix}.workflow_metadata.workflow_type must match workflow_type",
    )
    _require_privacy_safe_symbol(metadata, "workflow_type")
    _require_privacy_safe_symbol(metadata, "runtime_workflow_type")
    _require(
        metadata.get("runtime_workflow_type") == runtime_workflow_type,
        f"{prefix}.workflow_metadata.runtime_workflow_type must match {runtime_source}.runtime_workflow_type",
    )
    for key in ("workflow_family", "workflow_role"):
        _require_privacy_safe_symbol(metadata, key)
    display_name = metadata.get("display_name")
    _require(isinstance(display_name, str) and bool(display_name), f"{prefix}.workflow_metadata.display_name must be present")
    _require(
        display_name != workflow_type,
        f"{prefix}.workflow_metadata.display_name must not equal workflow_type",
    )
    capability_summary = metadata.get("capability_summary")
    _require(
        isinstance(capability_summary, str) and bool(capability_summary),
        f"{prefix}.workflow_metadata.capability_summary must be present",
    )
    pipeline_stages = metadata.get("pipeline_stages")
    _require(
        isinstance(pipeline_stages, list)
        and bool(pipeline_stages)
        and all(isinstance(stage, dict) and stage.get("name") and stage.get("purpose") for stage in pipeline_stages),
        f"{prefix}.workflow_metadata.pipeline_stages must be present",
    )
    for key in ("primary_outputs", "qc_outputs", "report_outputs", "limitations"):
        value = metadata.get(key)
        _require(
            isinstance(value, list) and bool(value) and all(isinstance(item, str) and bool(item) for item in value),
            f"{prefix}.workflow_metadata.{key} must be present",
        )
    _require(
        metadata.get("is_report_only") is False,
        f"{prefix}.workflow_metadata.is_report_only must be false for strict production launch evidence",
    )
    _require(
        metadata.get("agent_selectable") is True,
        f"{prefix}.workflow_metadata.agent_selectable must be true for strict production launch evidence",
    )


def _verify_task_result_summary(payload: dict, gate: dict) -> None:
    _require_status(payload, "task_result_summary_status")
    task_status = payload.get("task_status")
    summary = payload.get("task_result_summary")
    _require(isinstance(task_status, dict), "task_status must be present")
    _require(isinstance(summary, dict), "task_result_summary must be present")
    _require(
        isinstance(summary.get("contract_version"), str) and bool(summary.get("contract_version")),
        "task_result_summary.contract_version must be present",
    )
    _require(
        summary.get("task_id") == gate.get("task_id"),
        "task_result_summary.task_id must match smoke_gate.task_id",
    )
    _require(
        summary.get("workflow_type") == task_status.get("workflow_type"),
        "task_result_summary.workflow_type must match task_status.workflow_type",
    )
    _require_privacy_safe_symbol(summary, "workflow_type")
    _verify_workflow_metadata(
        summary.get("workflow_metadata"),
        workflow_type=summary.get("workflow_type"),
        runtime_workflow_type=task_status.get("runtime_workflow_type"),
        runtime_source="task_status",
        prefix="task_result_summary",
    )
    _require_privacy_safe_symbol(summary, "modality")
    feature_groups = summary.get("feature_groups")
    _require(
        isinstance(feature_groups, list)
        and feature_groups
        and all(_is_privacy_safe_symbol(item) for item in feature_groups),
        "task_result_summary.feature_groups must be non-empty",
    )
    _require_positive_int_metric_with_prefix(summary, "output_group_count", prefix="task_result_summary")
    _require_positive_int_metric_with_prefix(summary, "output_item_count", prefix="task_result_summary")
    downloadable_output_count = _require_positive_int_metric_with_prefix(
        summary,
        "downloadable_output_count",
        prefix="task_result_summary",
    )
    downloadable_output_paths = summary.get("downloadable_output_paths")
    downloadable_output_urls = summary.get("downloadable_output_urls")
    _require(
        isinstance(downloadable_output_paths, list)
        and len(downloadable_output_paths) == downloadable_output_count,
        "task_result_summary.downloadable_output_paths must match downloadable_output_count",
    )
    _require(
        isinstance(downloadable_output_urls, list)
        and len(downloadable_output_urls) == downloadable_output_count,
        "task_result_summary.downloadable_output_urls must match downloadable_output_count",
    )
    artifact_manifest_relative_paths = payload.get("artifact_manifest_relative_paths")
    artifact_manifest_download_urls = payload.get("artifact_manifest_download_urls")
    _require(
        isinstance(artifact_manifest_relative_paths, list)
        and artifact_manifest_relative_paths,
        "artifact_manifest_relative_paths must be non-empty",
    )
    _require(
        isinstance(artifact_manifest_download_urls, list)
        and artifact_manifest_download_urls,
        "artifact_manifest_download_urls must be non-empty",
    )
    for relative_path, download_url in zip(downloadable_output_paths, downloadable_output_urls, strict=True):
        _require(
            isinstance(relative_path, str) and not _is_unsafe_relative_path(relative_path),
            "task_result_summary.downloadable_output_paths entries must be safe relative paths",
        )
        expected_download_url = f"/tasks/{gate['task_id']}/artifacts/{quote(relative_path)}"
        _require(
            download_url == expected_download_url,
            "task_result_summary.downloadable_output_urls entries must match task artifact routes",
        )
        _require(
            relative_path in artifact_manifest_relative_paths and download_url in artifact_manifest_download_urls,
            "task_result_summary downloadable outputs must be present in artifact_manifest",
        )
    provenance_keys = summary.get("provenance_keys")
    _require(
        isinstance(provenance_keys, list)
        and provenance_keys
        and all(_is_privacy_safe_symbol(item) for item in provenance_keys),
        "task_result_summary.provenance_keys must be non-empty",
    )


def _verify_upload_completion(payload: dict) -> None:
    _require_status(payload, "upload_inventory_completion_status")
    _require(payload.get("upload_inventory_status") == "completed", "upload_inventory_status must be completed")
    task_status = payload.get("task_status")
    _require(isinstance(task_status, dict), "task_status must be present")
    series_id = task_status.get("series_id")
    series_ids = payload.get("upload_inventory_series_ids")
    _require(
        isinstance(series_ids, list)
        and all(isinstance(item, int) and not isinstance(item, bool) and item > 0 for item in series_ids)
        and series_id in series_ids,
        "upload_inventory_series_ids must include task_status.series_id",
    )


def _verify_workflow_eligibility_metadata_evidence(payload: dict, *, prefix: str, task_workflow_type: str) -> dict:
    status_key = f"{prefix}_workflow_eligibility_metadata_status"
    required_fields_key = f"{prefix}_workflow_eligibility_metadata_required_fields"
    workflow_types_key = f"{prefix}_workflow_eligibility_metadata_workflow_types"
    item_count_key = f"{prefix}_workflow_eligibility_metadata_item_count"
    _require_status(payload, status_key)
    required_fields = payload.get(required_fields_key)
    _require(
        isinstance(required_fields, list)
        and all(field in required_fields for field in WORKFLOW_ELIGIBILITY_METADATA_REQUIRED_FIELDS),
        f"{required_fields_key} must include workflow metadata required fields",
    )
    workflow_types = payload.get(workflow_types_key)
    _require(
        isinstance(workflow_types, list) and task_workflow_type in workflow_types,
        f"{workflow_types_key} must include task_status.workflow_type",
    )
    item_count = _require_positive_int_metric(payload, item_count_key)
    return {
        "status": payload[status_key],
        "required_field_count": len(required_fields),
        "workflow_types": workflow_types,
        "task_workflow_type_included": True,
        "item_count": item_count,
    }


def _verify_agent_project_context(payload: dict, gate: dict) -> None:
    _require_status(payload, "agent_project_context_status")
    project_id = payload.get("agent_run_project_id")
    _require(
        isinstance(project_id, int)
        and not isinstance(project_id, bool)
        and project_id == gate.get("project_id"),
        "agent_run_project_id must match smoke_gate.project_id",
    )


def _verify_agent_workflow_confirmation(payload: dict, gate: dict) -> None:
    _require_status(payload, "agent_workflow_confirmation_status")
    confirmation = payload.get("agent_workflow_confirmation")
    _require(isinstance(confirmation, dict), "agent_workflow_confirmation must be present")
    _require_privacy_safe_symbol(confirmation, "agent_run_id")
    _require_privacy_safe_symbol(confirmation, "intent")
    _require_privacy_safe_symbol(confirmation, "selected_skill")
    _require(
        confirmation.get("status") == "confirmation_required",
        "agent_workflow_confirmation.status must be confirmation_required",
    )
    _require(
        confirmation.get("intent") == "run_workflow",
        "agent_workflow_confirmation.intent must be run_workflow",
    )
    _require(
        confirmation.get("selected_skill") == "image-agent-workflow-runner",
        "agent_workflow_confirmation.selected_skill must be image-agent-workflow-runner",
    )
    _require(
        confirmation.get("production_task_created") is False,
        "agent_workflow_confirmation.production_task_created must be false",
    )
    _require(
        confirmation.get("project_id") == gate.get("project_id"),
        "agent_workflow_confirmation.project_id must match smoke_gate.project_id",
    )
    _require(
        confirmation.get("series_id") == gate.get("uploaded_series_id"),
        "agent_workflow_confirmation.series_id must match smoke_gate.uploaded_series_id",
    )
    task_status = payload.get("task_status") if isinstance(payload.get("task_status"), dict) else {}
    _require(
        confirmation.get("series_id") == task_status.get("series_id"),
        "agent_workflow_confirmation.series_id must match task_status.series_id",
    )
    _require(
        confirmation.get("workflow_type") == task_status.get("workflow_type"),
        "agent_workflow_confirmation.workflow_type must match task_status.workflow_type",
    )
    launched_task = payload.get("launched_task") if isinstance(payload.get("launched_task"), dict) else {}
    _require(
        launched_task.get("runtime_workflow_type") is not None,
        "launched_task.runtime_workflow_type must be present",
    )
    _require_privacy_safe_symbol(launched_task, "runtime_workflow_type")
    _verify_workflow_metadata(
        confirmation.get("workflow_metadata"),
        workflow_type=confirmation.get("workflow_type"),
        runtime_workflow_type=launched_task.get("runtime_workflow_type"),
        runtime_source="launched_task",
        prefix="agent_workflow_confirmation",
    )


def _verify_agent_workflow_resume(payload: dict, gate: dict) -> None:
    _require_status(payload, "agent_workflow_resume_status")
    resume = payload.get("agent_workflow_resume")
    _require(isinstance(resume, dict), "agent_workflow_resume must be present")
    _require_privacy_safe_symbol(resume, "agent_run_id")
    _require_privacy_safe_symbol(resume, "thread_id")
    _require(
        resume.get("status") == "task_created",
        "agent_workflow_resume.status must be task_created",
    )
    _require(
        resume.get("production_task_created") is True,
        "agent_workflow_resume.production_task_created must be true",
    )
    _require(
        resume.get("confirmation_gate") == "fingerprint_verified",
        "agent_workflow_resume.confirmation_gate must be fingerprint_verified",
    )
    _require(
        resume.get("project_id") == gate.get("project_id"),
        "agent_workflow_resume.project_id must match smoke_gate.project_id",
    )
    _require(
        resume.get("task_id") == gate.get("task_id"),
        "agent_workflow_resume.task_id must match smoke_gate.task_id",
    )
    task_status = payload.get("task_status") if isinstance(payload.get("task_status"), dict) else {}
    _require(
        resume.get("series_id") == task_status.get("series_id"),
        "agent_workflow_resume.series_id must match task_status.series_id",
    )
    _require(
        resume.get("workflow_type") == task_status.get("workflow_type"),
        "agent_workflow_resume.workflow_type must match task_status.workflow_type",
    )
    launched_task = payload.get("launched_task") if isinstance(payload.get("launched_task"), dict) else {}
    _require(
        resume.get("runtime_workflow_type") is not None,
        "agent_workflow_resume.runtime_workflow_type must be present",
    )
    _require_privacy_safe_symbol(resume, "runtime_workflow_type")
    _require(
        resume.get("runtime_workflow_type") == launched_task.get("runtime_workflow_type"),
        "agent_workflow_resume.runtime_workflow_type must match launched_task.runtime_workflow_type",
    )
    _require(
        resume.get("runtime_workflow_type") == task_status.get("runtime_workflow_type"),
        "agent_workflow_resume.runtime_workflow_type must match task_status.runtime_workflow_type",
    )


def _verify_agent_workflow_fingerprint_negative(payload: dict) -> dict:
    _require_status(payload, "agent_workflow_fingerprint_negative_status")
    negative = payload.get("agent_workflow_fingerprint_negative")
    _require(isinstance(negative, dict), "agent_workflow_fingerprint_negative must be present")
    _require_privacy_safe_symbol(negative, "agent_run_id")
    _require_privacy_safe_symbol(negative, "thread_id")
    _require(
        negative.get("status") == "blocked",
        "agent_workflow_fingerprint_negative.status must be blocked",
    )
    _require(
        negative.get("production_task_created") is False,
        "agent_workflow_fingerprint_negative.production_task_created must be false",
    )
    _require(
        negative.get("confirmation_gate") == "fingerprint_mismatch",
        "agent_workflow_fingerprint_negative.confirmation_gate must be fingerprint_mismatch",
    )
    _require(
        negative.get("task_created") is False,
        "agent_workflow_fingerprint_negative.task_created must be false",
    )
    return negative


def _verify_unknown_workflow_incubation(payload: dict) -> dict:
    _require_status(payload, "unknown_workflow_incubation_status")
    incubation = payload.get("unknown_workflow_incubation")
    _require(isinstance(incubation, dict), "unknown_workflow_incubation must be present")
    _require_prefixed_privacy_safe_symbol(incubation, "agent_run_id", prefix="unknown_workflow_incubation")
    if incubation.get("thread_id") is not None:
        _require_prefixed_privacy_safe_symbol(incubation, "thread_id", prefix="unknown_workflow_incubation")
    _require_prefixed_privacy_safe_symbol(incubation, "proposal_id", prefix="unknown_workflow_incubation")
    _require(
        incubation.get("status") == "toolchain_proposed",
        "unknown_workflow_incubation.status must be toolchain_proposed",
    )
    _require(
        incubation.get("action_lane") == "toolchain_incubation",
        "unknown_workflow_incubation.action_lane must be toolchain_incubation",
    )
    _require(
        incubation.get("task_created") is False,
        "unknown_workflow_incubation.task_created must be false",
    )
    _require(
        incubation.get("confirmation_created") is False,
        "unknown_workflow_incubation.confirmation_created must be false",
    )
    _require(
        incubation.get("task_creation_allowed") is False,
        "unknown_workflow_incubation.task_creation_allowed must be false",
    )
    forbidden_actions = incubation.get("forbidden_actions")
    _require(
        isinstance(forbidden_actions, list)
        and {"confirmation_creation", "production_task_creation", "pipeline_runner_launch"}.issubset(
            set(forbidden_actions)
        ),
        "unknown_workflow_incubation.forbidden_actions must include confirmation_creation, production_task_creation, and pipeline_runner_launch",
    )
    _require(
        incubation.get("production_task_created") is False,
        "unknown_workflow_incubation.production_task_created must be false",
    )
    _require(
        incubation.get("proposal_production_task_created") is False,
        "unknown_workflow_incubation.proposal_production_task_created must be false",
    )
    for key in ("proposal_status", "proposal_contract_version", "proposal_promotion_status"):
        if incubation.get(key) is not None:
            _require_prefixed_privacy_safe_symbol(incubation, key, prefix="unknown_workflow_incubation")
    return incubation


def _verify_agent_model_gateway(payload: dict, gate: dict) -> None:
    _require_status(payload, "agent_model_gateway_status")
    _require_privacy_safe_symbol(payload, "agent_model_gateway_access")
    if payload.get("agent_model_transport_access") is not None:
        _require_privacy_safe_symbol(payload, "agent_model_transport_access")
    if payload.get("agent_model_trust_env_proxy") is not None:
        _require(
            isinstance(payload.get("agent_model_trust_env_proxy"), bool),
            "agent_model_trust_env_proxy must be boolean",
        )
    if _requires_direct_model_gateway(payload.get("model_status") or {}, gate.get("expected_model_provider_profile")):
        _require(
            payload.get("agent_model_transport_access") == "direct",
            "agent_model_transport_access must be direct for rawchat direct acceptance",
        )
        _require(
            payload.get("agent_model_trust_env_proxy") is False,
            "agent_model_trust_env_proxy must be false for rawchat direct acceptance",
        )
    safe_metadata = payload.get("agent_safe_metadata")
    _require(isinstance(safe_metadata, dict), "agent_safe_metadata must be an object")
    _require(
        safe_metadata.get("fallback_reason") != "model_gateway_unconfigured",
        "agent_safe_metadata must not report model_gateway_unconfigured",
    )
    _require(
        payload.get("selected_skill") != "backend-status-fallback",
        "selected_skill must not be backend-status-fallback",
    )


def _is_unsafe_relative_path(value: object) -> bool:
    if not isinstance(value, str) or not value:
        return True
    normalized = value.replace("\\", "/")
    parts = [part for part in normalized.split("/") if part]
    return (
        "\\" in value
        or "/raw-sources/" in normalized
        or normalized.startswith("/")
        or (len(normalized) >= 2 and normalized[1] == ":" and normalized[0].isalpha())
        or ".." in parts
    )


def _is_vendor_doc_file_name(value: object) -> bool:
    return (
        isinstance(value, str)
        and value.endswith(".md")
        and "/" not in value
        and "\\" not in value
        and value not in {".md", "..md"}
        and ".." not in value
    )


def _verify_raw_source_policy(payload: dict) -> None:
    raw = payload.get("rag_raw_sources") if isinstance(payload.get("rag_raw_sources"), dict) else {}
    _require(raw.get("manifest_exists") is True, "rag_raw_sources.manifest_exists must be true")
    _require(raw.get("manifest_schema_version") is not None, "rag_raw_sources.manifest_schema_version must be present")
    _require_positive_int_metric_with_prefix(raw, "source_count", prefix="rag_raw_sources")
    _require_positive_int_metric_with_prefix(raw, "vendor_doc_count", prefix="rag_raw_sources")
    _require(not raw.get("missing_files"), "rag_raw_sources.missing_files must be empty")
    _require(not raw.get("hash_mismatches"), "rag_raw_sources.hash_mismatches must be empty")
    _require(raw.get("raw_sources_indexed") is False, "rag_raw_sources.raw_sources_indexed must be false")
    _require(not raw.get("indexed_raw_sources"), "rag_raw_sources.indexed_raw_sources must be empty")
    _require(raw.get("curated_provenance_ok") is True, "curated_provenance_ok must be true")
    _require(not raw.get("curated_provenance_issues"), "curated_provenance_issues must be empty")
    curated_sources = raw.get("curated_sources")
    _require(isinstance(curated_sources, list) and curated_sources, "curated_sources must be non-empty")
    curated_vendor_docs = []
    for item in curated_sources:
        _require(isinstance(item, dict), "curated_sources entries must be objects")
        vendor_doc = item.get("vendor_doc")
        _require(_is_vendor_doc_file_name(vendor_doc), "curated_sources vendor_doc must be a file name")
        curated_vendor_docs.append(vendor_doc)
        _require(
            item.get("complete") is True
            and bool(item.get("raw_source_ids"))
            and bool(item.get("source_urls"))
            and bool(item.get("raw_files")),
            "curated_sources entries must be complete with raw_source_ids, source_urls, and raw_files",
        )
        _require(
            item.get("manifest_backed") is True
            and item.get("source_url_backed") is True
            and isinstance(item.get("source_types"), list)
            and bool(item.get("source_types")),
            "curated_sources entries must be manifest-backed and source-url-backed",
        )
    _require(len(curated_vendor_docs) == len(set(curated_vendor_docs)), "curated_sources vendor_doc values must be unique")
    _require(raw.get("vendor_doc_count") == len(curated_sources), "rag_raw_sources.vendor_doc_count must match curated_sources")


def _verify_vendor_pointer_integrity(payload: dict) -> None:
    _require_status(payload, "rag_vendor_pointer_integrity_status")
    pointer_count = _require_positive_int_metric(payload, "rag_vendor_pointer_integrity_pointer_count")
    issue_count = _require_int_metric(payload, "rag_vendor_pointer_integrity_issue_count")
    _require(issue_count == 0, "rag_vendor_pointer_integrity_issue_count must be zero")
    referenced_vendor_docs = payload.get("rag_vendor_pointer_integrity_referenced_vendor_docs")
    _require(
        isinstance(referenced_vendor_docs, list)
        and referenced_vendor_docs
        and all(isinstance(item, str) and item.endswith(".md") and "/" not in item and "\\" not in item for item in referenced_vendor_docs),
        "rag_vendor_pointer_integrity_referenced_vendor_docs must be non-empty",
    )
    integrity = (
        payload.get("rag_vendor_pointer_integrity")
        if isinstance(payload.get("rag_vendor_pointer_integrity"), dict)
        else {}
    )
    _require(integrity.get("ok") is True, "rag_vendor_pointer_integrity.ok must be true")
    _require(integrity.get("pointer_count") == pointer_count, "rag_vendor_pointer_integrity.pointer_count must match summary")
    _require(integrity.get("issue_count") == issue_count, "rag_vendor_pointer_integrity.issue_count must match summary")
    _require(not integrity.get("issues"), "rag_vendor_pointer_integrity.issues must be empty")
    _require(
        integrity.get("referenced_vendor_docs") == referenced_vendor_docs,
        "rag_vendor_pointer_integrity.referenced_vendor_docs must match summary",
    )
    pointers_by_doc = integrity.get("pointers_by_doc")
    _require(isinstance(pointers_by_doc, dict) and pointers_by_doc, "rag_vendor_pointer_integrity.pointers_by_doc must be non-empty")
    _require(
        all(isinstance(source_doc, str) and source_doc.startswith("docs/rag/") for source_doc in pointers_by_doc),
        "rag_vendor_pointer_integrity.pointers_by_doc keys must be source docs",
    )
    flattened_vendor_paths = {
        value
        for values in pointers_by_doc.values()
        if isinstance(values, list)
        for value in values
        if isinstance(value, str)
    }
    _require(
        all(f"docs/rag/vendor/{vendor_doc}" in flattened_vendor_paths for vendor_doc in referenced_vendor_docs),
        "rag_vendor_pointer_integrity.pointers_by_doc must cover referenced vendor docs",
    )
    _require(integrity.get("raw_source_manifest_exists") is True, "rag_vendor_pointer_integrity.raw_source_manifest_exists must be true")
    _require(integrity.get("curated_provenance_ok") is True, "rag_vendor_pointer_integrity.curated_provenance_ok must be true")


def _verify_elasticsearch_hybrid_rag(payload: dict) -> None:
    _require_status(payload, "rag_elasticsearch_hybrid_status")
    hybrid = (
        payload.get("rag_elasticsearch_hybrid")
        if isinstance(payload.get("rag_elasticsearch_hybrid"), dict)
        else {}
    )
    rebuild_hybrid = (
        payload.get("rag_rebuild_elasticsearch_hybrid")
        if isinstance(payload.get("rag_rebuild_elasticsearch_hybrid"), dict)
        else {}
    )
    _require(rebuild_hybrid, "rag_rebuild_elasticsearch_hybrid must be present")
    _require(hybrid.get("engine") == "elasticsearch", "rag_elasticsearch_hybrid.engine must be elasticsearch")
    _require(hybrid.get("configured") is True, "rag_elasticsearch_hybrid.configured must be true")
    _require(hybrid.get("persisted") is True, "rag_elasticsearch_hybrid.persisted must be true")
    _require(hybrid.get("mode") == "connected", "rag_elasticsearch_hybrid.mode must be connected")
    index_name = hybrid.get("index")
    _require(_is_privacy_safe_symbol(index_name), "rag_elasticsearch_hybrid.index must be privacy-safe")
    indexed_chunk_count = hybrid.get("indexed_chunk_count")
    _require(
        isinstance(indexed_chunk_count, int) and not isinstance(indexed_chunk_count, bool) and indexed_chunk_count > 0,
        "rag_elasticsearch_hybrid.indexed_chunk_count must be greater than zero",
    )
    _require(
        rebuild_hybrid.get("engine") == "elasticsearch",
        "rag_rebuild_elasticsearch_hybrid.engine must be elasticsearch",
    )
    _require(
        rebuild_hybrid.get("configured") is True,
        "rag_rebuild_elasticsearch_hybrid.configured must be true",
    )
    _require(
        rebuild_hybrid.get("persisted") is True,
        "rag_rebuild_elasticsearch_hybrid.persisted must be true",
    )
    _require(
        rebuild_hybrid.get("mode") == "connected",
        "rag_rebuild_elasticsearch_hybrid.mode must be connected",
    )
    _require(
        rebuild_hybrid.get("index") == index_name,
        "rag_rebuild_elasticsearch_hybrid.index must match status",
    )
    _require(
        rebuild_hybrid.get("indexed_chunk_count") == indexed_chunk_count,
        "rag_rebuild_elasticsearch_hybrid.indexed_chunk_count must match status",
    )
    dense_vector_dims = hybrid.get("dense_vector_dims")
    _require(
        isinstance(dense_vector_dims, int) and not isinstance(dense_vector_dims, bool) and dense_vector_dims > 0,
        "rag_elasticsearch_hybrid.dense_vector_dims must be greater than zero",
    )
    rebuild_dense_vector_dims = rebuild_hybrid.get("dense_vector_dims")
    _require(
        isinstance(rebuild_dense_vector_dims, int)
        and not isinstance(rebuild_dense_vector_dims, bool)
        and rebuild_dense_vector_dims > 0,
        "rag_rebuild_elasticsearch_hybrid.dense_vector_dims must be greater than zero",
    )
    _require(
        rebuild_dense_vector_dims == dense_vector_dims,
        "rag_rebuild_elasticsearch_hybrid.dense_vector_dims must match status",
    )
    _require(not hybrid.get("error"), "rag_elasticsearch_hybrid.error must be absent")
    _require(not rebuild_hybrid.get("error"), "rag_rebuild_elasticsearch_hybrid.error must be absent")
    _require(not hybrid.get("embedding_error"), "rag_elasticsearch_hybrid.embedding_error must be absent")
    _require(
        not rebuild_hybrid.get("embedding_error"),
        "rag_rebuild_elasticsearch_hybrid.embedding_error must be absent",
    )
    _require(
        hybrid.get("lexical_retriever") == "standard",
        "rag_elasticsearch_hybrid.lexical_retriever must be standard",
    )
    _require(hybrid.get("vector_retriever") == "knn", "rag_elasticsearch_hybrid.vector_retriever must be knn")
    _require(
        hybrid.get("dense_vector_field") == "embedding",
        "rag_elasticsearch_hybrid.dense_vector_field must be embedding",
    )
    _require(
        rebuild_hybrid.get("lexical_retriever") == hybrid.get("lexical_retriever"),
        "rag_rebuild_elasticsearch_hybrid.lexical_retriever must match status",
    )
    _require(
        rebuild_hybrid.get("vector_retriever") == hybrid.get("vector_retriever"),
        "rag_rebuild_elasticsearch_hybrid.vector_retriever must match status",
    )
    _require(
        rebuild_hybrid.get("dense_vector_field") == hybrid.get("dense_vector_field"),
        "rag_rebuild_elasticsearch_hybrid.dense_vector_field must match status",
    )
    embedding_provider = str(hybrid.get("embedding_provider") or "").strip()
    _require(
        embedding_provider and embedding_provider.lower() not in LOCAL_EMBEDDING_PROVIDERS,
        "rag_elasticsearch_hybrid.embedding_provider must be production configured",
    )
    embedding_model = str(hybrid.get("embedding_model") or "").strip()
    _require(
        embedding_model,
        "rag_elasticsearch_hybrid.embedding_model must be present",
    )
    embedding_transport = str(hybrid.get("embedding_transport") or "").strip()
    _require(
        embedding_transport,
        "rag_elasticsearch_hybrid.embedding_transport must be present",
    )
    _require(
        embedding_transport in {"sdk", "openai_compatible_http"},
        "rag_elasticsearch_hybrid.embedding_transport must be production-safe",
    )
    _require(
        hybrid.get("embedding_endpoint_configured") is True,
        "rag_elasticsearch_hybrid.embedding_endpoint_configured must be true",
    )
    _require(
        hybrid.get("embedding_production_ready") is True,
        "rag_elasticsearch_hybrid.embedding_production_ready must be true",
    )
    _require(
        rebuild_hybrid.get("embedding_provider") == embedding_provider,
        "rag_rebuild_elasticsearch_hybrid.embedding_provider must match status",
    )
    rebuild_embedding_model = str(rebuild_hybrid.get("embedding_model") or "").strip()
    _require(
        rebuild_embedding_model,
        "rag_rebuild_elasticsearch_hybrid.embedding_model must be present",
    )
    _require(
        rebuild_embedding_model == embedding_model,
        "rag_rebuild_elasticsearch_hybrid.embedding_model must match status",
    )
    rebuild_embedding_transport = str(rebuild_hybrid.get("embedding_transport") or "").strip()
    _require(
        rebuild_embedding_transport,
        "rag_rebuild_elasticsearch_hybrid.embedding_transport must be present",
    )
    _require(
        rebuild_embedding_transport == embedding_transport,
        "rag_rebuild_elasticsearch_hybrid.embedding_transport must match status",
    )
    _require(
        rebuild_embedding_transport in {"sdk", "openai_compatible_http"},
        "rag_rebuild_elasticsearch_hybrid.embedding_transport must be production-safe",
    )
    _require(
        rebuild_hybrid.get("embedding_endpoint_configured") == hybrid.get("embedding_endpoint_configured"),
        "rag_rebuild_elasticsearch_hybrid.embedding_endpoint_configured must match status",
    )
    _require(
        rebuild_hybrid.get("embedding_endpoint_configured") is True,
        "rag_rebuild_elasticsearch_hybrid.embedding_endpoint_configured must be true",
    )
    _require(
        rebuild_hybrid.get("embedding_production_ready") is True,
        "rag_rebuild_elasticsearch_hybrid.embedding_production_ready must be true",
    )
    fusion, rrf_unavailable_reason = _require_elasticsearch_fusion(
        hybrid,
        context="rag_elasticsearch_hybrid",
    )
    _require(
        rebuild_hybrid.get("fusion") == fusion,
        "rag_rebuild_elasticsearch_hybrid.fusion must match status",
    )
    _require(
        _rrf_unavailable_reason(rebuild_hybrid) == (rrf_unavailable_reason or ""),
        "rag_rebuild_elasticsearch_hybrid.rrf_unavailable_reason must match status",
    )
    _require(
        "official_sources" not in hybrid,
        "rag_elasticsearch_hybrid.official_sources must not be saved",
    )
    _require(
        hybrid.get("official_rrf_source_present") is True,
        "rag_elasticsearch_hybrid.official_rrf_source_present must be true",
    )
    _require_status(payload, "rag_elasticsearch_hybrid_query_status")
    _require(
        payload.get("rag_elasticsearch_hybrid_query_mode") == "elasticsearch_hybrid",
        "rag_elasticsearch_hybrid_query_mode must be elasticsearch_hybrid",
    )
    _require(
        payload.get("rag_elasticsearch_hybrid_query_retrieval_source") == "elasticsearch_hybrid",
        "rag_elasticsearch_hybrid_query_retrieval_source must be elasticsearch_hybrid",
    )
    _require(
        payload.get("rag_elasticsearch_hybrid_query_source") == ELASTICSEARCH_HYBRID_CONTRACT_SOURCE,
        "rag_elasticsearch_hybrid_query_source must cite the Elasticsearch hybrid contract",
    )
    _require_positive_int_metric(payload, "rag_elasticsearch_hybrid_query_citation_count")
    _require_positive_numeric_metric(payload, "rag_elasticsearch_hybrid_query_top_score")
    _require(
        payload.get("rag_elasticsearch_hybrid_query_index") == index_name,
        "rag_elasticsearch_hybrid_query_index must match status",
    )
    _require(
        payload.get("rag_elasticsearch_hybrid_query_lexical_retriever") == hybrid.get("lexical_retriever"),
        "rag_elasticsearch_hybrid_query_lexical_retriever must match status",
    )
    _require(
        payload.get("rag_elasticsearch_hybrid_query_lexical_retriever") == "standard",
        "rag_elasticsearch_hybrid_query_lexical_retriever must be standard",
    )
    _require(
        payload.get("rag_elasticsearch_hybrid_query_vector_retriever") == hybrid.get("vector_retriever"),
        "rag_elasticsearch_hybrid_query_vector_retriever must match status",
    )
    _require(
        payload.get("rag_elasticsearch_hybrid_query_vector_retriever") == "knn",
        "rag_elasticsearch_hybrid_query_vector_retriever must be knn",
    )
    _require(
        payload.get("rag_elasticsearch_hybrid_query_dense_vector_field") == hybrid.get("dense_vector_field"),
        "rag_elasticsearch_hybrid_query_dense_vector_field must match status",
    )
    _require(
        payload.get("rag_elasticsearch_hybrid_query_dense_vector_field") == "embedding",
        "rag_elasticsearch_hybrid_query_dense_vector_field must be embedding",
    )
    _require(
        payload.get("rag_elasticsearch_hybrid_query_fusion") == fusion,
        "rag_elasticsearch_hybrid_query_fusion must match status",
    )
    _require(
        (
            payload.get("rag_elasticsearch_hybrid_query_fusion") == "rrf"
            or (
                payload.get("rag_elasticsearch_hybrid_query_fusion") == "query_plus_knn"
                and payload.get("rag_elasticsearch_hybrid_query_rrf_unavailable_reason")
                == ELASTICSEARCH_ACCEPTED_FUSION_FALLBACK_REASON
                and rrf_unavailable_reason == ELASTICSEARCH_ACCEPTED_FUSION_FALLBACK_REASON
            )
        ),
        "rag_elasticsearch_hybrid_query_fusion must be rrf or query_plus_knn with rrf_unavailable_reason=license_non_compliant",
    )
    query_dense_vector_dims = _require_positive_int_metric(
        payload,
        "rag_elasticsearch_hybrid_query_dense_vector_dims",
    )
    _require(
        query_dense_vector_dims == dense_vector_dims,
        "rag_elasticsearch_hybrid_query_dense_vector_dims must match status",
    )
    query_embedding_provider = str(payload.get("rag_elasticsearch_hybrid_query_embedding_provider") or "").strip()
    _require(
        query_embedding_provider == embedding_provider,
        "rag_elasticsearch_hybrid_query_embedding_provider must match status",
    )
    query_embedding_model = str(payload.get("rag_elasticsearch_hybrid_query_embedding_model") or "").strip()
    _require(
        query_embedding_model == embedding_model,
        "rag_elasticsearch_hybrid_query_embedding_model must match status",
    )
    query_embedding_transport = str(payload.get("rag_elasticsearch_hybrid_query_embedding_transport") or "").strip()
    _require(
        query_embedding_transport == embedding_transport,
        "rag_elasticsearch_hybrid_query_embedding_transport must match status",
    )
    _require(
        payload.get("rag_elasticsearch_hybrid_query_embedding_endpoint_configured")
        == hybrid.get("embedding_endpoint_configured"),
        "rag_elasticsearch_hybrid_query_embedding_endpoint_configured must match status",
    )
    _require(
        payload.get("rag_elasticsearch_hybrid_query_embedding_endpoint_configured") is True,
        "rag_elasticsearch_hybrid_query_embedding_endpoint_configured must be true",
    )
    _require(
        payload.get("rag_elasticsearch_hybrid_query_embedding_production_ready")
        == hybrid.get("embedding_production_ready"),
        "rag_elasticsearch_hybrid_query_embedding_production_ready must match status",
    )
    _require(
        payload.get("rag_elasticsearch_hybrid_query_embedding_production_ready") is True,
        "rag_elasticsearch_hybrid_query_embedding_production_ready must be true",
    )


def _verify_vendor_coverage_catalog(payload: dict) -> None:
    _require(payload.get("rag_vendor_coverage_catalog_status") == "complete", "rag_vendor_coverage_catalog_status must be complete")
    vendor_doc_count = _require_positive_int_metric(payload, "rag_vendor_coverage_catalog_vendor_doc_count")
    complete_count = _require_positive_int_metric(payload, "rag_vendor_coverage_catalog_complete_vendor_doc_count")
    incomplete_count = _require_int_metric(payload, "rag_vendor_coverage_catalog_incomplete_vendor_doc_count")
    _require(incomplete_count == 0, "rag_vendor_coverage_catalog_incomplete_vendor_doc_count must be zero")
    raw_source_count = _require_positive_int_metric(payload, "rag_vendor_coverage_catalog_raw_source_count")
    catalog = (
        payload.get("rag_vendor_coverage_catalog")
        if isinstance(payload.get("rag_vendor_coverage_catalog"), dict)
        else {}
    )
    _require("manifest_path" not in catalog, "rag_vendor_coverage_catalog must not expose manifest_path")
    _require("persist_dir" not in catalog, "rag_vendor_coverage_catalog must not expose persist_dir")
    _require(catalog.get("status") == "complete", "rag_vendor_coverage_catalog.status must be complete")
    _require(
        catalog.get("policy") == "curated summaries are indexed; raw snapshots are provenance evidence only",
        "rag_vendor_coverage_catalog.policy mismatch",
    )
    _require(catalog.get("vendor_doc_count") == vendor_doc_count, "rag_vendor_coverage_catalog.vendor_doc_count must match summary")
    _require(catalog.get("complete_vendor_doc_count") == complete_count, "rag_vendor_coverage_catalog.complete_vendor_doc_count must match summary")
    _require(catalog.get("incomplete_vendor_doc_count") == incomplete_count, "rag_vendor_coverage_catalog.incomplete_vendor_doc_count must match summary")
    _require(catalog.get("raw_source_count") == raw_source_count, "rag_vendor_coverage_catalog.raw_source_count must match summary")
    _require(
        catalog.get("raw_source_count") == payload.get("rag_raw_sources", {}).get("source_count"),
        "rag_vendor_coverage_catalog.raw_source_count must match rag_raw_sources.source_count",
    )
    _require(
        catalog.get("pointer_count") == payload.get("rag_vendor_pointer_integrity_pointer_count"),
        "rag_vendor_coverage_catalog.pointer_count must match pointer integrity summary",
    )
    _require(catalog.get("issue_count") == 0, "rag_vendor_coverage_catalog.issue_count must be zero")
    _require(catalog.get("raw_sources_indexed") is False, "rag_vendor_coverage_catalog.raw_sources_indexed must be false")
    _require(catalog.get("curated_provenance_ok") is True, "rag_vendor_coverage_catalog.curated_provenance_ok must be true")
    _require(catalog.get("pointer_integrity_ok") is True, "rag_vendor_coverage_catalog.pointer_integrity_ok must be true")
    vendors = catalog.get("vendors")
    _require(isinstance(vendors, list) and vendors, "rag_vendor_coverage_catalog.vendors must be non-empty")
    blocked_vendor_keys = {"raw_snapshots", "raw_files", "sha256", "manifest_path", "persist_dir", "absolute_path", "backend_path"}
    raw = payload.get("rag_raw_sources") if isinstance(payload.get("rag_raw_sources"), dict) else {}
    curated_sources = raw.get("curated_sources") if isinstance(raw.get("curated_sources"), list) else []
    curated_by_doc = {
        item.get("vendor_doc"): item
        for item in curated_sources
        if isinstance(item, dict) and _is_vendor_doc_file_name(item.get("vendor_doc"))
    }
    vendor_docs = []
    for vendor in vendors:
        _require(isinstance(vendor, dict), "rag_vendor_coverage_catalog.vendors entries must be objects")
        for blocked_key in blocked_vendor_keys:
            _require(blocked_key not in vendor, f"rag_vendor_coverage_catalog vendors must not expose {blocked_key}")
        vendor_doc = vendor.get("vendor_doc")
        vendor_path = vendor.get("vendor_path")
        _require(_is_vendor_doc_file_name(vendor_doc), "rag_vendor_coverage_catalog vendor_doc must be a file name")
        vendor_docs.append(vendor_doc)
        _require(
            isinstance(vendor_path, str)
            and vendor_path == f"docs/rag/vendor/{vendor_doc}",
            "rag_vendor_coverage_catalog vendor_path must be repo-relative",
        )
        _require(vendor.get("complete") is True, "rag_vendor_coverage_catalog vendors complete must be true")
        _require(vendor.get("manifest_backed") is True, "rag_vendor_coverage_catalog vendors manifest_backed must be true")
        _require(vendor.get("source_url_backed") is True, "rag_vendor_coverage_catalog vendors source_url_backed must be true")
        _require(_int_metric(vendor.get("raw_source_count")) > 0, "rag_vendor_coverage_catalog vendors raw_source_count must be greater than zero")
        _require(_int_metric(vendor.get("source_url_count")) > 0, "rag_vendor_coverage_catalog vendors source_url_count must be greater than zero")
        _require(isinstance(vendor.get("source_types"), list) and vendor["source_types"], "rag_vendor_coverage_catalog vendors source_types must be non-empty")
        _require(isinstance(vendor.get("raw_source_ids"), list) and vendor["raw_source_ids"], "rag_vendor_coverage_catalog vendors raw_source_ids must be non-empty")
        referenced_by = vendor.get("referenced_by")
        _require(isinstance(referenced_by, list), "rag_vendor_coverage_catalog vendors referenced_by must be a list")
        _require(
            all(
                isinstance(source_doc, str)
                and source_doc.startswith("docs/rag/")
                and "\\" not in source_doc
                and ".." not in [part for part in source_doc.split("/") if part]
                for source_doc in referenced_by
            ),
            "rag_vendor_coverage_catalog vendors referenced_by must contain repo-relative docs",
        )
        curated = curated_by_doc.get(vendor_doc)
        if curated is not None:
            _require(
                sorted(vendor["raw_source_ids"]) == sorted(curated.get("raw_source_ids") or []),
                "rag_vendor_coverage_catalog raw_source_ids must match curated_sources",
            )
            _require(
                _int_metric(vendor.get("raw_source_count")) == len(curated.get("raw_source_ids") or []),
                "rag_vendor_coverage_catalog raw_source_count must match curated_sources",
            )
            _require(
                _int_metric(vendor.get("source_url_count")) == len(curated.get("source_urls") or []),
                "rag_vendor_coverage_catalog source_url_count must match curated_sources",
            )
            _require(
                sorted(vendor["source_types"]) == sorted(curated.get("source_types") or []),
                "rag_vendor_coverage_catalog source_types must match curated_sources",
            )
            _require(
                vendor.get("complete") == curated.get("complete") is True,
                "rag_vendor_coverage_catalog complete must match curated_sources",
            )
            _require(
                vendor.get("manifest_backed") == curated.get("manifest_backed") is True,
                "rag_vendor_coverage_catalog manifest_backed must match curated_sources",
            )
            _require(
                vendor.get("source_url_backed") == curated.get("source_url_backed") is True,
                "rag_vendor_coverage_catalog source_url_backed must match curated_sources",
            )
    _require(len(vendor_docs) == len(set(vendor_docs)), "rag_vendor_coverage_catalog.vendors vendor_doc values must be unique")
    _require(
        set(vendor_docs) == set(curated_by_doc),
        "rag_vendor_coverage_catalog.vendors must match rag_raw_sources.curated_sources",
    )
    _require(len(vendors) == vendor_doc_count, "rag_vendor_coverage_catalog.vendors must match vendor_doc_count")


def _verify_launchability(payload: dict) -> None:
    _require_status(payload, "rag_launchability_matrix_status")
    _require(
        payload.get("rag_launchability_matrix_source") == LAUNCHABILITY_MATRIX_SOURCE,
        "launchability matrix source must cite workflow matrix",
    )
    _require_status(payload, "rag_launchability_query_status")
    _require(payload.get("rag_launchability_query_intent") == "launchability", "rag_launchability_query_intent must be launchability")
    _require(
        payload.get("rag_launchability_query_source") == LAUNCHABILITY_MATRIX_SOURCE,
        "launchability query source must cite workflow matrix",
    )


def _verify_real_ids(payload: dict, gate: dict) -> None:
    _require_status(payload, "remote_evidence_ids_status")
    evidence_ids = payload.get("remote_evidence_ids") if isinstance(payload.get("remote_evidence_ids"), dict) else {}
    for key in ("project_id", "upload_session_id", "task_id"):
        _require_positive_id(evidence_ids, key, prefix="remote_evidence_ids")
        _require(evidence_ids.get(key) == gate.get(key), f"remote_evidence_ids.{key} must match smoke_gate.{key}")


def _verify_deployment_identity(payload: dict, gate: dict) -> None:
    _require_status(payload, "deployment_identity_status")
    identity = payload.get("deployment_identity") if isinstance(payload.get("deployment_identity"), dict) else {}
    _require_privacy_safe_symbol(identity, "deployment_id")
    _require(
        identity.get("deployment_id") == gate.get("deployment_id"),
        "deployment_identity.deployment_id must match smoke_gate.deployment_id",
    )
    _require(
        identity.get("health_app") == "image_agent",
        "deployment_identity.health_app must be image_agent",
    )
    health_version = identity.get("health_version")
    _require(
        isinstance(health_version, str) and bool(health_version) and len(health_version) <= 80,
        "deployment_identity.health_version must be present",
    )
    _require(
        _is_privacy_safe_symbol(health_version),
        "deployment_identity.health_version must be privacy-safe",
    )
    expected_health_version = gate.get("expected_health_version")
    if expected_health_version is not None:
        _require(
            health_version == expected_health_version,
            "deployment_identity.health_version must match smoke_gate.expected_health_version",
        )


def _verify_official_source_ids(source_ids: object) -> set[str]:
    _require(isinstance(source_ids, list) and source_ids, "container_native_qc_official_source_ids must be non-empty")
    verified_ids = set()
    for source_id in source_ids:
        _require(isinstance(source_id, str), "container_native_qc_official_source_ids entries must be strings")
        _require(
            source_id in CONTAINER_NATIVE_QC_OFFICIAL_SOURCE_IDS,
            "container_native_qc_official_source_ids contains unsupported source",
        )
        verified_ids.add(source_id)
    return verified_ids


def _verify_container_native_qc(payload: dict, gate: dict) -> None:
    _require_status(payload, "container_native_qc_status")
    artifact_count = _require_positive_int_metric(payload, "container_native_qc_artifact_count")
    image_count = _require_int_metric(payload, "container_native_qc_image_count")
    _require(
        image_count >= gate["min_native_qc_images"],
        "container_native_qc_image_count below smoke gate minimum",
    )
    _require(image_count <= artifact_count, "container_native_qc_image_count cannot exceed artifact count")
    for key in ("container_native_qc_relative_paths", "container_native_qc_served_urls"):
        value = payload.get(key)
        _require(isinstance(value, list) and value, f"{key} must be non-empty")
    summary_source_ids = _verify_official_source_ids(payload.get("container_native_qc_official_source_ids"))
    artifacts = payload.get("container_native_qc_artifacts")
    _require(isinstance(artifacts, list) and artifacts, "container_native_qc_artifacts must be non-empty")
    _require(artifact_count == len(artifacts), "container_native_qc_artifact_count must match container_native_qc_artifacts")
    flattened_relative_paths = []
    flattened_served_urls = []
    flattened_source_ids = set()
    derived_image_count = 0
    for artifact in artifacts:
        _require(isinstance(artifact, dict), "container_native_qc_artifacts entries must be objects")
        for key in (
            "relative_path",
            "download_url",
            "content_type",
            "preview_kind",
            "artifact_origin",
            "native_artifact",
            "official_source_ids",
            "provenance",
        ):
            _require(key in artifact, f"container_native_qc_artifacts entries must include {key}")
        preview_kind = artifact["preview_kind"]
        _require(preview_kind in {"html", "image"}, "container_native_qc_artifacts preview_kind must be html or image")
        relative_path = artifact["relative_path"]
        download_url = artifact["download_url"]
        content_type = artifact["content_type"]
        provenance = artifact.get("provenance") if isinstance(artifact.get("provenance"), dict) else {}
        _require(
            artifact.get("artifact_origin") == "container_output",
            "container_native_qc_artifacts artifact_origin must be container_output",
        )
        _require(artifact.get("native_artifact") is True, "container_native_qc_artifacts native_artifact must be true")
        _require(
            provenance.get("generated_from") == "container_native_qc",
            "container_native_qc_artifacts provenance.generated_from must be container_native_qc",
        )
        _require(
            provenance.get("replaces_native_qc") is False,
            "container_native_qc_artifacts provenance.replaces_native_qc must be false",
        )
        _require(isinstance(relative_path, str) and relative_path, "container_native_qc_artifacts relative_path must be non-empty")
        _require(not _is_unsafe_relative_path(relative_path), "container_native_qc_artifacts relative_path is unsafe")
        _require(
            not relative_path.replace("\\", "/").lower().startswith("reports/"),
            "container_native_qc_artifacts reports paths must be scientific report artifacts",
        )
        _require(isinstance(download_url, str) and download_url, "container_native_qc_artifacts download_url must be non-empty")
        expected_download_url = f"/tasks/{gate['task_id']}/artifacts/{quote(relative_path)}"
        _require(download_url == expected_download_url, "container_native_qc_artifacts download_url mismatch")
        _require(isinstance(content_type, str) and content_type, "container_native_qc_artifacts content_type must be non-empty")
        normalized_content_type = content_type.split(";", 1)[0].strip().lower()
        if preview_kind == "html":
            _require(
                normalized_content_type == "text/html",
                "container_native_qc_artifacts html content_type must be text/html",
            )
        if preview_kind == "image":
            _require(
                normalized_content_type.startswith("image/"),
                "container_native_qc_artifacts image content_type must be image/",
            )
            derived_image_count += 1
        _require(download_url in payload["container_native_qc_served_urls"], "container_native_qc_artifacts download_url must be served")
        flattened_relative_paths.append(relative_path)
        flattened_served_urls.append(download_url)
        artifact_source_ids = _verify_official_source_ids(artifact["official_source_ids"])
        provenance_source_ids = _verify_official_source_ids(provenance.get("official_source_ids"))
        _require(
            artifact_source_ids == provenance_source_ids,
            "container_native_qc_artifacts provenance.official_source_ids must match official_source_ids",
        )
        flattened_source_ids.update(artifact_source_ids)
    _require(image_count == derived_image_count, "container_native_qc_image_count must match container_native_qc_artifacts")
    _require(payload["container_native_qc_relative_paths"] == flattened_relative_paths, "container_native_qc_relative_paths must match container_native_qc_artifacts")
    _require(payload["container_native_qc_served_urls"] == flattened_served_urls, "container_native_qc_served_urls must match container_native_qc_artifacts")
    _require(summary_source_ids == flattened_source_ids, "container_native_qc_official_source_ids must match container_native_qc_artifacts")


def _verify_scientific_report_artifacts(payload: dict, gate: dict) -> None:
    _require_status(payload, "scientific_report_artifacts_status")
    artifact_count = _require_positive_int_metric(payload, "scientific_report_artifact_count")
    image_count = _require_int_metric(payload, "scientific_report_image_count")
    html_count = _require_int_metric(payload, "scientific_report_html_count")
    json_count = _require_int_metric(payload, "scientific_report_json_count")
    _require(
        image_count >= gate["min_scientific_report_images"],
        "scientific_report_image_count below smoke gate minimum",
    )
    artifacts = payload.get("scientific_report_artifacts")
    _require(isinstance(artifacts, list) and artifacts, "scientific_report_artifacts must be non-empty")
    _require(artifact_count == len(artifacts), "scientific_report_artifact_count must match scientific_report_artifacts")
    served_urls = payload.get("scientific_report_served_urls")
    _require(isinstance(served_urls, list) and served_urls, "scientific_report_served_urls must be non-empty")
    flattened_relative_paths = []
    flattened_served_urls = []
    derived_preview_kinds = []
    derived_image_count = 0
    derived_html_count = 0
    derived_json_count = 0
    for artifact in artifacts:
        _require(isinstance(artifact, dict), "scientific_report_artifacts entries must be objects")
        for key in (
            "relative_path",
            "download_url",
            "content_type",
            "preview_kind",
            "source_stage",
            "artifact_role",
            "artifact_origin",
            "native_artifact",
            "provenance",
        ):
            _require(key in artifact, f"scientific_report_artifacts entries must include {key}")
        relative_path = artifact["relative_path"]
        download_url = artifact["download_url"]
        preview_kind = artifact["preview_kind"]
        content_type = artifact["content_type"]
        provenance = artifact.get("provenance") if isinstance(artifact.get("provenance"), dict) else {}
        _require(not _is_unsafe_relative_path(relative_path), "scientific_report_artifacts relative_path is unsafe")
        _require(isinstance(download_url, str) and download_url, "scientific_report_artifacts download_url must be non-empty")
        expected_download_url = f"/tasks/{gate['task_id']}/artifacts/{quote(relative_path)}"
        _require(download_url == expected_download_url, "scientific_report_artifacts download_url mismatch")
        _require(isinstance(content_type, str) and content_type, "scientific_report_artifacts content_type must be non-empty")
        _require(preview_kind in {"html", "image", "json"}, "scientific_report_artifacts preview_kind must be html, image, or json")
        normalized_content_type = content_type.split(";", 1)[0].strip().lower()
        if preview_kind == "html":
            _require(
                normalized_content_type == "text/html",
                "scientific_report_artifacts html content_type must be text/html",
            )
        if preview_kind == "image":
            _require(
                normalized_content_type.startswith("image/"),
                "scientific_report_artifacts image content_type must be image/",
            )
        if preview_kind == "json":
            _require(
                normalized_content_type == "application/json",
                "scientific_report_artifacts json content_type must be application/json",
            )
        _require(artifact["source_stage"] == "scientific_report", "scientific_report_artifacts source_stage must be scientific_report")
        _require(artifact["artifact_role"] == "derived_presentation_asset", "scientific_report_artifacts artifact_role must be derived_presentation_asset")
        _require(artifact["artifact_origin"] == "generated_from_result_summary", "scientific_report_artifacts artifact_origin must be generated_from_result_summary")
        _require(artifact["native_artifact"] is False, "scientific_report_artifacts native_artifact must be false")
        _require(provenance.get("generated_from") == "result_summary", "scientific_report_artifacts provenance.generated_from must be result_summary")
        _require(provenance.get("replaces_native_qc") is False, "scientific_report_artifacts provenance.replaces_native_qc must be false")
        _require(download_url in served_urls, "scientific_report_artifacts download_url must be served")
        flattened_relative_paths.append(relative_path)
        flattened_served_urls.append(download_url)
        derived_preview_kinds.append(preview_kind)
        if preview_kind == "image":
            derived_image_count += 1
        if preview_kind == "html":
            derived_html_count += 1
        if preview_kind == "json":
            derived_json_count += 1
    _require("reports/index.html" in flattened_relative_paths, "scientific_report_artifacts reports/index.html missing")
    _require("reports/report_manifest.json" in flattened_relative_paths, "scientific_report_artifacts reports/report_manifest.json missing")
    _require(image_count == derived_image_count, "scientific_report_image_count must match scientific_report_artifacts")
    _require(html_count == derived_html_count, "scientific_report_html_count must match scientific_report_artifacts")
    _require(json_count == derived_json_count, "scientific_report_json_count must match scientific_report_artifacts")
    _require(
        payload.get("scientific_report_relative_paths") == flattened_relative_paths,
        "scientific_report_relative_paths must match scientific_report_artifacts",
    )
    _require(
        payload.get("scientific_report_preview_kinds") == sorted(set(derived_preview_kinds)),
        "scientific_report_preview_kinds must match scientific_report_artifacts",
    )
    _require(
        served_urls == flattened_served_urls,
        "scientific_report_served_urls must match scientific_report_artifacts",
    )


def verify_acceptance_payload(
    payload: dict,
    *,
    max_age_hours: float | None = None,
    now_utc: datetime | None = None,
) -> dict:
    _require(isinstance(payload, dict), "acceptance payload must be a JSON object")
    _verify_no_saved_official_sources(payload)
    generated_at_utc, effective_max_age_hours = _verify_generated_at_utc(
        payload,
        max_age_hours=max_age_hours,
        now_utc=now_utc,
    )
    gate = _verify_gate_settings(payload)
    _verify_no_debug_only_workflows(payload)
    _require(isinstance(payload.get("health"), dict) and payload["health"].get("app") == "image_agent", "health.app must be image_agent")
    _verify_deployment_identity(payload, gate)
    _verify_production_readiness(payload)
    _verify_model_status(payload, gate)
    _require_status(payload, "model_smoke_status")
    _require(payload.get("agent_run_status") == "answered", "agent_run_status must be answered")
    for key in ("agent_run_id", "intent", "selected_skill"):
        _require_privacy_safe_symbol(payload, key)
    _verify_agent_model_gateway(payload, gate)
    _verify_agent_project_context(payload, gate)
    _verify_agent_workflow_confirmation(payload, gate)
    agent_workflow_fingerprint_negative = _verify_agent_workflow_fingerprint_negative(payload)
    unknown_workflow_incubation = _verify_unknown_workflow_incubation(payload)
    _require_int_metric(payload, "rag_document_count")
    _require_int_metric(payload, "rag_chunk_count")
    _require(payload["rag_document_count"] >= gate["min_documents"], "rag_document_count below smoke gate minimum")
    _require(payload["rag_chunk_count"] >= gate["min_chunks"], "rag_chunk_count below smoke gate minimum")
    _require(payload.get("rag_semantic_index") is True, "rag_semantic_index must be true")
    _verify_raw_source_policy(payload)
    _verify_vendor_pointer_integrity(payload)
    _verify_elasticsearch_hybrid_rag(payload)
    fast_launch_rag_check = _verify_fast_launch_readiness(payload)
    fast_launch_checks = payload["fast_launch_readiness"]["checks"]
    fast_launch_production_deployment = fast_launch_checks["production_deployment"]
    _verify_vendor_coverage_catalog(payload)
    _verify_real_ids(payload, gate)
    _verify_task_status(payload, gate)
    runtime_toolchain = _verify_runtime_toolchain(payload)
    _verify_task_events(payload, gate)
    _verify_observe_repair(payload, gate)
    _verify_uploaded_series(payload, gate)
    _verify_launched_task(payload, gate)
    _verify_agent_workflow_resume(payload, gate)
    _verify_task_workflow_selection(payload)
    _verify_task_result_summary(payload, gate)
    _verify_launchability(payload)
    _require_status(payload, "project_contract_status")
    _require_positive_int(payload, "series_with_workflow_eligibility")
    task_workflow_type = payload["task_status"]["workflow_type"]
    project_workflow_eligibility_metadata = _verify_workflow_eligibility_metadata_evidence(
        payload,
        prefix="project",
        task_workflow_type=task_workflow_type,
    )
    _require_status(payload, "upload_inventory_contract_status")
    _verify_upload_completion(payload)
    _require_positive_int(payload, "upload_inventory_series_with_workflow_eligibility")
    upload_inventory_workflow_eligibility_metadata = _verify_workflow_eligibility_metadata_evidence(
        payload,
        prefix="upload_inventory",
        task_workflow_type=task_workflow_type,
    )
    _require_status(payload, "task_artifact_manifest_status")
    _require_positive_int(payload, "artifact_manifest_artifact_count")
    _require(isinstance(payload.get("artifact_manifest_preview_kinds"), list) and payload["artifact_manifest_preview_kinds"], "artifact_manifest_preview_kinds must be non-empty")
    _verify_container_native_qc(payload, gate)
    _verify_scientific_report_artifacts(payload, gate)
    return {
        "status": "passed",
        "summary": "status=passed",
        "checked": {
            "model_smoke_status": payload["model_smoke_status"],
            "expected_model_wire_api": gate["expected_model_wire_api"],
            "model_wire_api": payload["model_status"].get("wire_api"),
            "expected_model_provider_profile": gate["expected_model_provider_profile"],
            "model_provider_profile": payload["model_status"].get("provider_profile"),
            "model_trust_env_proxy": payload["model_status"].get("trust_env_proxy"),
            "model_gateway_access": payload["model_status"].get("deployment", {}).get("model_gateway_access"),
            "model_tool_loop": payload["model_status"].get("capabilities", {}).get("model_tool_loop"),
            "agent_model_gateway_status": payload["agent_model_gateway_status"],
            "agent_model_gateway_access": payload["agent_model_gateway_access"],
            "agent_model_transport_access": payload.get("agent_model_transport_access"),
            "agent_model_trust_env_proxy": payload.get("agent_model_trust_env_proxy"),
            "agent_project_context_status": payload["agent_project_context_status"],
            "agent_workflow_confirmation_status": payload["agent_workflow_confirmation_status"],
            "agent_workflow_confirmation_metadata_workflow_type": payload["agent_workflow_confirmation"]["workflow_metadata"]["workflow_type"],
            "agent_workflow_confirmation_metadata_runtime_workflow_type": payload["agent_workflow_confirmation"]["workflow_metadata"].get("runtime_workflow_type"),
            "agent_workflow_confirmation_metadata_agent_selectable": payload["agent_workflow_confirmation"]["workflow_metadata"]["agent_selectable"],
            "agent_workflow_confirmation_metadata_is_report_only": payload["agent_workflow_confirmation"]["workflow_metadata"]["is_report_only"],
            "agent_workflow_resume_status": payload["agent_workflow_resume_status"],
            "agent_workflow_resume_runtime_workflow_type": payload["agent_workflow_resume"].get("runtime_workflow_type"),
            "agent_workflow_fingerprint_negative_status": payload["agent_workflow_fingerprint_negative_status"],
            "agent_workflow_fingerprint_negative_confirmation_gate": agent_workflow_fingerprint_negative.get("confirmation_gate"),
            "agent_workflow_fingerprint_negative_task_created": agent_workflow_fingerprint_negative.get("task_created"),
            "agent_workflow_fingerprint_negative_production_task_created": agent_workflow_fingerprint_negative.get(
                "production_task_created"
            ),
            "unknown_workflow_incubation_status": payload["unknown_workflow_incubation_status"],
            "unknown_workflow_incubation_action_lane": unknown_workflow_incubation.get("action_lane"),
            "unknown_workflow_incubation_task_created": unknown_workflow_incubation.get("task_created"),
            "unknown_workflow_incubation_confirmation_created": unknown_workflow_incubation.get(
                "confirmation_created"
            ),
            "unknown_workflow_incubation_task_creation_allowed": unknown_workflow_incubation.get(
                "task_creation_allowed"
            ),
            "unknown_workflow_incubation_forbidden_actions": unknown_workflow_incubation.get("forbidden_actions"),
            "unknown_workflow_incubation_production_task_created": unknown_workflow_incubation.get(
                "production_task_created"
            ),
            "unknown_workflow_incubation_proposal_production_task_created": unknown_workflow_incubation.get(
                "proposal_production_task_created"
            ),
            "deployment_identity_status": payload["deployment_identity_status"],
            "production_readiness_status": payload["production_readiness_status"],
            "fast_launch_readiness_status": payload["fast_launch_readiness_status"],
            "fast_launch_production_deployment_status": fast_launch_production_deployment.get("status"),
            "fast_launch_production_deployment_required": fast_launch_production_deployment.get("required"),
            "fast_launch_production_deployment_ready": fast_launch_production_deployment.get("ready"),
            "fast_launch_rag_elasticsearch_hybrid_status": fast_launch_rag_check.get("status"),
            "fast_launch_rag_elasticsearch_hybrid_mode": fast_launch_rag_check.get("mode"),
            "fast_launch_rag_elasticsearch_hybrid_index": fast_launch_rag_check.get("index"),
            "runtime_toolchain_status": payload["runtime_toolchain_status"],
            "runtime_toolchain_workflow_tool_execution": runtime_toolchain.get("workflow_tool_execution"),
            "runtime_toolchain_docker_runtime_host": runtime_toolchain.get("docker_runtime_host"),
            "runtime_toolchain_fs_license_exists": runtime_toolchain.get("fs_license_exists"),
            "runtime_toolchain_required_workflow_type": runtime_toolchain.get("required_workflow_type"),
            "runtime_toolchain_required_runtime_workflow_type": runtime_toolchain.get(
                "required_runtime_workflow_type"
            )
            or runtime_toolchain.get("required_workflow_type"),
            "runtime_toolchain_required_workflow_available": runtime_toolchain.get("required_workflow_available"),
            "remote_evidence_ids_status": payload["remote_evidence_ids_status"],
            "uploaded_series_status": payload["uploaded_series_status"],
            "task_status_status": payload["task_status_status"],
            "task_status_runtime_workflow_type": payload["task_status"].get("runtime_workflow_type"),
            "project_workflow_eligibility_metadata_status": project_workflow_eligibility_metadata["status"],
            "project_workflow_eligibility_metadata_item_count": project_workflow_eligibility_metadata["item_count"],
            "project_workflow_eligibility_metadata_required_field_count": project_workflow_eligibility_metadata[
                "required_field_count"
            ],
            "project_workflow_eligibility_metadata_workflow_types": project_workflow_eligibility_metadata[
                "workflow_types"
            ],
            "project_workflow_eligibility_metadata_task_workflow_type_included": project_workflow_eligibility_metadata[
                "task_workflow_type_included"
            ],
            "upload_inventory_workflow_eligibility_metadata_status": upload_inventory_workflow_eligibility_metadata[
                "status"
            ],
            "upload_inventory_workflow_eligibility_metadata_item_count": upload_inventory_workflow_eligibility_metadata[
                "item_count"
            ],
            "upload_inventory_workflow_eligibility_metadata_required_field_count": upload_inventory_workflow_eligibility_metadata[
                "required_field_count"
            ],
            "upload_inventory_workflow_eligibility_metadata_workflow_types": upload_inventory_workflow_eligibility_metadata[
                "workflow_types"
            ],
            "upload_inventory_workflow_eligibility_metadata_task_workflow_type_included": upload_inventory_workflow_eligibility_metadata[
                "task_workflow_type_included"
            ],
            "task_events_status": payload["task_events_status"],
            "task_events_remote_log_count": payload["task_events_remote_log_count"],
            "observe_repair_status": payload["observe_repair_status"],
            "observe_repair_policy": payload["observe_repair_policy"],
            "observe_repair_auto_rerun_allowed": payload["observe_repair_auto_rerun_allowed"],
            "observe_repair_task_creation_allowed": payload["observe_repair_task_creation_allowed"],
            "observe_repair_forbidden_actions": payload["observe_repair_forbidden_actions"],
            "observe_repair_production_task_created": payload["observe_repair_production_task_created"],
            "observe_repair_requires_preflight_before_retry": payload[
                "observe_repair_requires_preflight_before_retry"
            ],
            "observe_repair_requires_human_confirmation_before_retry": payload[
                "observe_repair_requires_human_confirmation_before_retry"
            ],
            "launched_task_status": payload["launched_task_status"],
            "launched_task_launch_source": payload["launched_task"].get("launch_source"),
            "launched_task_runtime_workflow_type": payload["launched_task"].get("runtime_workflow_type"),
            "task_workflow_selection_status": payload["task_workflow_selection_status"],
            "task_result_summary_status": payload["task_result_summary_status"],
            "task_result_summary_metadata_workflow_type": payload["task_result_summary"]["workflow_metadata"]["workflow_type"],
            "task_result_summary_metadata_runtime_workflow_type": payload["task_result_summary"]["workflow_metadata"].get("runtime_workflow_type"),
            "task_result_summary_metadata_agent_selectable": payload["task_result_summary"]["workflow_metadata"]["agent_selectable"],
            "task_result_summary_metadata_is_report_only": payload["task_result_summary"]["workflow_metadata"]["is_report_only"],
            "rag_vendor_pointer_integrity_status": payload["rag_vendor_pointer_integrity_status"],
            "rag_elasticsearch_hybrid_status": payload["rag_elasticsearch_hybrid_status"],
            "rag_elasticsearch_hybrid_mode": payload["rag_elasticsearch_hybrid"].get("mode"),
            "rag_elasticsearch_hybrid_configured": payload["rag_elasticsearch_hybrid"].get("configured"),
            "rag_elasticsearch_hybrid_index": payload["rag_elasticsearch_hybrid"].get("index"),
            "rag_elasticsearch_hybrid_indexed_chunk_count": payload["rag_elasticsearch_hybrid"].get(
                "indexed_chunk_count"
            ),
            "rag_elasticsearch_hybrid_dense_vector_dims": payload["rag_elasticsearch_hybrid"].get(
                "dense_vector_dims"
            ),
            "rag_elasticsearch_hybrid_error_absent": not bool(payload["rag_elasticsearch_hybrid"].get("error")),
            "rag_elasticsearch_hybrid_embedding_error_absent": not bool(
                payload["rag_elasticsearch_hybrid"].get("embedding_error")
            ),
            "rag_elasticsearch_hybrid_embedding_provider": payload["rag_elasticsearch_hybrid"].get(
                "embedding_provider"
            ),
            "rag_elasticsearch_hybrid_embedding_model": payload["rag_elasticsearch_hybrid"].get(
                "embedding_model"
            ),
            "rag_elasticsearch_hybrid_embedding_transport": payload["rag_elasticsearch_hybrid"].get(
                "embedding_transport"
            ),
            "rag_elasticsearch_hybrid_embedding_endpoint_configured": payload["rag_elasticsearch_hybrid"].get(
                "embedding_endpoint_configured"
            )
            is True,
            "rag_elasticsearch_hybrid_embedding_production_ready": payload["rag_elasticsearch_hybrid"].get(
                "embedding_production_ready"
            ),
            "rag_elasticsearch_hybrid_official_rrf_source_present": payload["rag_elasticsearch_hybrid"].get(
                "official_rrf_source_present"
            )
            is True,
            "rag_rebuild_elasticsearch_hybrid_indexed_chunk_count": payload[
                "rag_rebuild_elasticsearch_hybrid"
            ].get("indexed_chunk_count"),
            "rag_rebuild_elasticsearch_hybrid_configured": payload[
                "rag_rebuild_elasticsearch_hybrid"
            ].get("configured"),
            "rag_rebuild_elasticsearch_hybrid_index": payload[
                "rag_rebuild_elasticsearch_hybrid"
            ].get("index"),
            "rag_rebuild_elasticsearch_hybrid_dense_vector_dims": payload[
                "rag_rebuild_elasticsearch_hybrid"
            ].get("dense_vector_dims"),
            "rag_rebuild_elasticsearch_hybrid_lexical_retriever": payload[
                "rag_rebuild_elasticsearch_hybrid"
            ].get("lexical_retriever"),
            "rag_rebuild_elasticsearch_hybrid_vector_retriever": payload[
                "rag_rebuild_elasticsearch_hybrid"
            ].get("vector_retriever"),
            "rag_rebuild_elasticsearch_hybrid_dense_vector_field": payload[
                "rag_rebuild_elasticsearch_hybrid"
            ].get("dense_vector_field"),
            "rag_rebuild_elasticsearch_hybrid_error_absent": not bool(
                payload["rag_rebuild_elasticsearch_hybrid"].get("error")
            ),
            "rag_rebuild_elasticsearch_hybrid_embedding_error_absent": not bool(
                payload["rag_rebuild_elasticsearch_hybrid"].get("embedding_error")
            ),
            "rag_rebuild_elasticsearch_hybrid_embedding_provider": payload[
                "rag_rebuild_elasticsearch_hybrid"
            ].get("embedding_provider"),
            "rag_rebuild_elasticsearch_hybrid_embedding_model": payload[
                "rag_rebuild_elasticsearch_hybrid"
            ].get("embedding_model"),
            "rag_rebuild_elasticsearch_hybrid_embedding_transport": payload[
                "rag_rebuild_elasticsearch_hybrid"
            ].get("embedding_transport"),
            "rag_rebuild_elasticsearch_hybrid_embedding_endpoint_configured": payload[
                "rag_rebuild_elasticsearch_hybrid"
            ].get("embedding_endpoint_configured")
            is True,
            "rag_rebuild_elasticsearch_hybrid_embedding_production_ready": payload[
                "rag_rebuild_elasticsearch_hybrid"
            ].get("embedding_production_ready"),
            "rag_rebuild_elasticsearch_hybrid_fusion": payload["rag_rebuild_elasticsearch_hybrid"].get(
                "fusion"
            ),
            "rag_elasticsearch_hybrid_query_status": payload["rag_elasticsearch_hybrid_query_status"],
            "rag_elasticsearch_hybrid_query_mode": payload["rag_elasticsearch_hybrid_query_mode"],
            "rag_elasticsearch_hybrid_query_retrieval_source": payload[
                "rag_elasticsearch_hybrid_query_retrieval_source"
            ],
            "rag_elasticsearch_hybrid_query_source": payload["rag_elasticsearch_hybrid_query_source"],
            "rag_elasticsearch_hybrid_query_citation_count": payload[
                "rag_elasticsearch_hybrid_query_citation_count"
            ],
            "rag_elasticsearch_hybrid_query_top_score": payload[
                "rag_elasticsearch_hybrid_query_top_score"
            ],
            "rag_elasticsearch_hybrid_query_index": payload["rag_elasticsearch_hybrid_query_index"],
            "rag_elasticsearch_hybrid_query_lexical_retriever": payload[
                "rag_elasticsearch_hybrid_query_lexical_retriever"
            ],
            "rag_elasticsearch_hybrid_query_vector_retriever": payload[
                "rag_elasticsearch_hybrid_query_vector_retriever"
            ],
            "rag_elasticsearch_hybrid_query_dense_vector_field": payload[
                "rag_elasticsearch_hybrid_query_dense_vector_field"
            ],
            "rag_elasticsearch_hybrid_query_fusion": payload["rag_elasticsearch_hybrid_query_fusion"],
            "rag_elasticsearch_hybrid_query_rrf_unavailable_reason": payload.get(
                "rag_elasticsearch_hybrid_query_rrf_unavailable_reason"
            ),
            "rag_elasticsearch_hybrid_query_dense_vector_dims": payload[
                "rag_elasticsearch_hybrid_query_dense_vector_dims"
            ],
            "rag_elasticsearch_hybrid_query_embedding_provider": payload[
                "rag_elasticsearch_hybrid_query_embedding_provider"
            ],
            "rag_elasticsearch_hybrid_query_embedding_model": payload[
                "rag_elasticsearch_hybrid_query_embedding_model"
            ],
            "rag_elasticsearch_hybrid_query_embedding_transport": payload[
                "rag_elasticsearch_hybrid_query_embedding_transport"
            ],
            "rag_elasticsearch_hybrid_query_embedding_endpoint_configured": payload[
                "rag_elasticsearch_hybrid_query_embedding_endpoint_configured"
            ],
            "rag_elasticsearch_hybrid_query_embedding_production_ready": payload[
                "rag_elasticsearch_hybrid_query_embedding_production_ready"
            ],
            "rag_vendor_coverage_catalog_status": payload["rag_vendor_coverage_catalog_status"],
            "rag_launchability_query_status": payload["rag_launchability_query_status"],
            "project_contract_status": payload["project_contract_status"],
            "upload_inventory_contract_status": payload["upload_inventory_contract_status"],
            "upload_inventory_completion_status": payload["upload_inventory_completion_status"],
            "task_artifact_manifest_status": payload["task_artifact_manifest_status"],
            "container_native_qc_status": payload["container_native_qc_status"],
            "scientific_report_artifacts_status": payload["scientific_report_artifacts_status"],
            "max_age_hours": effective_max_age_hours,
            "generated_at_utc": generated_at_utc.isoformat(),
        },
    }


def fast_launch_env_lines(report: dict, payload: dict) -> list[str]:
    _require(isinstance(report, dict) and report.get("status") == "passed", "acceptance report must be passed")
    gate = payload.get("smoke_gate") if isinstance(payload.get("smoke_gate"), dict) else {}
    deployment_id = gate.get("deployment_id")
    _require(_is_privacy_safe_symbol(deployment_id), "smoke_gate.deployment_id must be privacy-safe")
    return [
        "IMAGE_AGENT_STRICT_REMOTE_ACCEPTANCE_STATUS=passed",
        f"IMAGE_AGENT_STRICT_REMOTE_ACCEPTANCE_ID={deployment_id}",
    ]


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Verify a saved strict remote smoke acceptance JSON artifact.")
    parser.add_argument("acceptance_json", help="Path to the JSON file written by smoke_remote_agent.py --output-json.")
    parser.add_argument(
        "--max-age-hours",
        type=float,
        default=None,
        help="Fail if generated_at_utc is older than this many hours.",
    )
    parser.add_argument(
        "--now-utc",
        default=None,
        help="Testing hook: ISO-8601 UTC timestamp used as the current time for --max-age-hours.",
    )
    parser.add_argument(
        "--emit-fast-launch-env",
        action="store_true",
        help="Print only safe IMAGE_AGENT_STRICT_REMOTE_ACCEPTANCE_* environment lines after verification passes.",
    )
    args = parser.parse_args(argv)
    source_path = Path(args.acceptance_json)
    payload = json.loads(source_path.read_text(encoding="utf-8"))
    now_utc = _parse_utc_timestamp(args.now_utc, key="now_utc") if args.now_utc else None
    report = verify_acceptance_payload(payload, max_age_hours=args.max_age_hours, now_utc=now_utc)
    if args.emit_fast_launch_env:
        print("\n".join(fast_launch_env_lines(report, payload)))
        return
    report["source_json"] = str(source_path)
    print(json.dumps(report, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
