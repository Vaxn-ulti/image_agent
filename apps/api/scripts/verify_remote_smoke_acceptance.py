from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote


LAUNCHABILITY_MATRIX_SOURCE = "docs/rag/workflows/workflow_launchability_matrix.md"
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


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(message)


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


def _is_privacy_safe_symbol(value: object) -> bool:
    return (
        isinstance(value, str)
        and bool(value)
        and len(value) <= 140
        and all(char.isalnum() or char in "_.-" for char in value)
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
) -> datetime:
    generated_at = _parse_utc_timestamp(payload.get("generated_at_utc"), key="generated_at_utc")
    if max_age_hours is not None:
        _require(max_age_hours >= 0, "max_age_hours must be non-negative")
        now = now_utc or datetime.now(timezone.utc)
        _require(now.tzinfo is not None and now.utcoffset() is not None, "now_utc must be timezone-aware")
        age_hours = (now.astimezone(timezone.utc) - generated_at).total_seconds() / 3600
        _require(age_hours >= 0, "generated_at_utc must not be in the future")
        _require(age_hours <= max_age_hours, f"generated_at_utc is older than {max_age_hours:g} hours")
    return generated_at


def _require_positive_int(payload: dict, key: str) -> None:
    _require_positive_int_metric(payload, key)


def _verify_gate_settings(payload: dict) -> dict:
    gate = payload.get("smoke_gate") if isinstance(payload.get("smoke_gate"), dict) else {}
    for key in (
        "require_model",
        "require_deployment_identity",
        "require_raw_source_policy",
        "require_vendor_pointer_integrity",
        "require_real_evidence_ids",
        "require_launchability_matrix",
        "require_container_native_qc",
        "require_scientific_report_artifacts",
    ):
        _require(gate.get(key) is True, f"smoke_gate.{key} must be true")
    for key in ("project_id", "upload_session_id", "task_id"):
        _require_positive_id(gate, key, prefix="smoke_gate")
    _require_positive_int_metric(gate, "min_documents")
    _require_positive_int_metric(gate, "min_chunks")
    _require_positive_int_metric(gate, "min_native_qc_images")
    _require_positive_int_metric(gate, "min_scientific_report_images")
    _require_privacy_safe_symbol(gate, "deployment_id")
    return gate


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
        for key in ("relative_path", "download_url", "content_type", "preview_kind", "official_source_ids"):
            _require(key in artifact, f"container_native_qc_artifacts entries must include {key}")
        preview_kind = artifact["preview_kind"]
        _require(preview_kind in {"html", "image"}, "container_native_qc_artifacts preview_kind must be html or image")
        relative_path = artifact["relative_path"]
        download_url = artifact["download_url"]
        content_type = artifact["content_type"]
        _require(isinstance(relative_path, str) and relative_path, "container_native_qc_artifacts relative_path must be non-empty")
        _require(not _is_unsafe_relative_path(relative_path), "container_native_qc_artifacts relative_path is unsafe")
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
        flattened_source_ids.update(_verify_official_source_ids(artifact["official_source_ids"]))
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
    _verify_generated_at_utc(payload, max_age_hours=max_age_hours, now_utc=now_utc)
    gate = _verify_gate_settings(payload)
    _require(isinstance(payload.get("health"), dict) and payload["health"].get("app") == "image_agent", "health.app must be image_agent")
    _verify_deployment_identity(payload, gate)
    _require(isinstance(payload.get("model_status"), dict) and payload["model_status"].get("configured") is True, "model_status.configured must be true")
    _require_status(payload, "model_smoke_status")
    _require(payload.get("agent_run_status") == "answered", "agent_run_status must be answered")
    for key in ("agent_run_id", "intent", "selected_skill"):
        _require_privacy_safe_symbol(payload, key)
    _require_int_metric(payload, "rag_document_count")
    _require_int_metric(payload, "rag_chunk_count")
    _require(payload["rag_document_count"] >= gate["min_documents"], "rag_document_count below smoke gate minimum")
    _require(payload["rag_chunk_count"] >= gate["min_chunks"], "rag_chunk_count below smoke gate minimum")
    _require(payload.get("rag_semantic_index") is True, "rag_semantic_index must be true")
    _verify_raw_source_policy(payload)
    _verify_vendor_pointer_integrity(payload)
    _verify_vendor_coverage_catalog(payload)
    _verify_real_ids(payload, gate)
    _verify_launchability(payload)
    _require_status(payload, "project_contract_status")
    _require_positive_int(payload, "series_with_workflow_eligibility")
    _require_status(payload, "upload_inventory_contract_status")
    _require_positive_int(payload, "upload_inventory_series_with_workflow_eligibility")
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
            "deployment_identity_status": payload["deployment_identity_status"],
            "remote_evidence_ids_status": payload["remote_evidence_ids_status"],
            "rag_vendor_pointer_integrity_status": payload["rag_vendor_pointer_integrity_status"],
            "rag_vendor_coverage_catalog_status": payload["rag_vendor_coverage_catalog_status"],
            "rag_launchability_query_status": payload["rag_launchability_query_status"],
            "project_contract_status": payload["project_contract_status"],
            "upload_inventory_contract_status": payload["upload_inventory_contract_status"],
            "task_artifact_manifest_status": payload["task_artifact_manifest_status"],
            "container_native_qc_status": payload["container_native_qc_status"],
            "scientific_report_artifacts_status": payload["scientific_report_artifacts_status"],
        },
    }


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
    args = parser.parse_args(argv)
    source_path = Path(args.acceptance_json)
    payload = json.loads(source_path.read_text(encoding="utf-8"))
    now_utc = _parse_utc_timestamp(args.now_utc, key="now_utc") if args.now_utc else None
    report = verify_acceptance_payload(payload, max_age_hours=args.max_age_hours, now_utc=now_utc)
    report["source_json"] = str(source_path)
    print(json.dumps(report, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
