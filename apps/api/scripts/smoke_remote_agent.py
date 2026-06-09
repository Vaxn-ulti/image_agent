from __future__ import annotations

import argparse
import json
import urllib.error
import urllib.request
from collections.abc import Sequence
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote


LAUNCHABILITY_MATRIX_SOURCE = "docs/rag/workflows/workflow_launchability_matrix.md"
LAUNCHABILITY_SMOKE_QUERY = "Use the workflow launchability matrix to explain which workflows are launchable and cite the matrix."
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


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(message)


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


def _summarize_vendor_coverage_catalog(rag_after: dict) -> dict:
    catalog = (
        rag_after.get("vendor_coverage_catalog")
        if isinstance(rag_after.get("vendor_coverage_catalog"), dict)
        else {}
    )
    return {
        "catalog": catalog,
        "status": str(catalog.get("status") or "missing"),
        "vendor_doc_count": _int_metric(catalog.get("vendor_doc_count")),
        "complete_vendor_doc_count": _int_metric(catalog.get("complete_vendor_doc_count")),
        "incomplete_vendor_doc_count": _int_metric(catalog.get("incomplete_vendor_doc_count")),
        "raw_source_count": _int_metric(catalog.get("raw_source_count")),
    }


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


def _validate_project_series_contract(series: list[dict]) -> dict:
    _require(isinstance(series, list), "project series contract failed: response is not a list")
    _require(series, "project series contract failed: no series found")
    for item in series:
        _validate_workflow_eligibility(item.get("workflow_eligibility"), "project series contract failed")
    return {
        "status": "passed",
        "series_count": len(series),
        "series_with_workflow_eligibility": len(series),
        "modalities": sorted({str(item.get("modality")) for item in series if item.get("modality")}),
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


def _validate_upload_inventory_contract(response: dict, upload_session_id: int) -> dict:
    _require(int(response.get("upload_session_id") or 0) == upload_session_id, "upload inventory session id mismatch")
    inventory = response.get("inventory")
    _require(isinstance(inventory, dict), "upload inventory contract failed: inventory missing")
    series = inventory.get("series")
    _require(isinstance(series, list), "upload inventory contract failed: series missing")
    _require(bool(series), "upload inventory contract failed: no series found")
    for item in series:
        _validate_workflow_eligibility(
            item.get("workflow_eligibility"),
            "upload inventory contract failed",
        )
    return {
        "status": "passed",
        "upload_session_id": upload_session_id,
        "inventory_status": inventory.get("inventory_status") or response.get("status"),
        "series_count": len(series),
        "series_with_workflow_eligibility": len(series),
        "modalities": sorted({str(item.get("modality")) for item in series if item.get("modality")}),
    }


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
        if _is_native_qc_artifact(artifact):
            _validate_native_qc_provenance(artifact)
            source_ids = _native_qc_official_source_ids(artifact)
            _require(source_ids, "native container QC artifact official_source_ids missing")
            native_qc_artifacts.append(
                {
                    "relative_path": relative_path,
                    "download_url": download_url,
                    "content_type": content_type,
                    "preview_kind": preview_kind,
                    "official_source_ids": source_ids,
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
        "--require-real-evidence-ids",
        action="store_true",
        help="Fail unless --project-id, --upload-session-id, and --task-id are all supplied.",
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
    if args.require_real_evidence_ids and (
        args.project_id is None or args.upload_session_id is None or args.task_id is None
    ):
        raise SystemExit("--require-real-evidence-ids requires --project-id, --upload-session-id, and --task-id")
    if args.require_container_native_qc and args.task_id is None:
        raise SystemExit("--require-container-native-qc requires --task-id")
    if args.min_native_qc_images > 0 and args.task_id is None:
        raise SystemExit("--min-native-qc-images requires --task-id")
    if args.require_scientific_report_artifacts and args.task_id is None:
        raise SystemExit("--require-scientific-report-artifacts requires --task-id")
    if args.min_scientific_report_images > 0 and args.task_id is None:
        raise SystemExit("--min-scientific-report-images requires --task-id")

    base = args.api_base.rstrip("/")
    health = _request("GET", f"{base}/health")
    _validate_health(health)
    status = _request("GET", f"{base}/agent/model/status")
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
    if status.get("configured"):
        run = _request("POST", f"{base}/agent/runs", {"project_id": None, "message": args.message})
        _validate_agent_run(run)
        model_smoke_status = "passed"
    elif args.require_model:
        raise SystemExit("model gateway is not configured")
    project_contract = None
    task_artifact_manifest = None
    upload_inventory_contract = None
    if args.project_id is not None:
        project_contract = _validate_project_series_contract(
            _request("GET", f"{base}/projects/{args.project_id}/series")
        )
        if args.upload_session_id is not None:
            upload_inventory_contract = _validate_upload_inventory_contract(
                _request("GET", f"{base}/projects/{args.project_id}/datasets/{args.upload_session_id}/inventory"),
                args.upload_session_id,
            )
    if args.task_id is not None:
        task_artifact_manifest = _validate_task_artifact_manifest(
            _request("GET", f"{base}/tasks/{args.task_id}/artifact-manifest"),
            args.task_id,
            require_native_qc_artifact=bool(args.require_container_native_qc),
            min_native_qc_images=max(args.min_native_qc_images, 0),
            require_scientific_report_artifacts=bool(args.require_scientific_report_artifacts),
            min_scientific_report_images=max(args.min_scientific_report_images, 0),
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
    payload = {
        "generated_at_utc": _generated_at_utc(),
        "smoke_gate": {
            "api_base": base,
            "require_model": bool(args.require_model),
            "min_documents": max(args.min_documents, 0),
            "min_chunks": max(args.min_chunks, 0),
            "require_raw_source_policy": bool(args.require_raw_source_policy),
            "require_vendor_pointer_integrity": bool(args.require_vendor_pointer_integrity),
            "require_real_evidence_ids": bool(args.require_real_evidence_ids),
            "require_launchability_matrix": bool(args.require_launchability_matrix),
            "require_container_native_qc": bool(args.require_container_native_qc),
            "min_native_qc_images": max(args.min_native_qc_images, 0),
            "require_scientific_report_artifacts": bool(args.require_scientific_report_artifacts),
            "min_scientific_report_images": max(args.min_scientific_report_images, 0),
            "project_id": args.project_id,
            "task_id": args.task_id,
            "upload_session_id": args.upload_session_id,
        },
        "health": health,
        "model_status": status,
        "model_smoke_status": model_smoke_status,
        "rag_before": rag_before.get("index"),
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
        "rag_document_count": rag.get("document_count"),
        "rag_chunk_count": rag.get("chunk_count"),
        "rag_semantic_index": rag.get("semantic_index"),
        "rag_after": rag_after.get("index"),
        "agent_run_status": run.get("status") if run else "skipped",
        "agent_run_id": run.get("agent_run_id") if run else None,
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
        "rag_launchability_matrix_status": launchability_matrix.get("status") if launchability_matrix else "skipped",
        "rag_launchability_matrix_source": launchability_matrix.get("source") if launchability_matrix else None,
        "rag_launchability_query_status": launchability_query.get("status") if launchability_query else "skipped",
        "rag_launchability_query_intent": launchability_query.get("intent") if launchability_query else None,
        "rag_launchability_query_source": launchability_query.get("source") if launchability_query else None,
        "project_contract_status": project_contract.get("status") if project_contract else "skipped",
        "series_count": project_contract.get("series_count") if project_contract else 0,
        "series_with_workflow_eligibility": project_contract.get("series_with_workflow_eligibility") if project_contract else 0,
        "series_modalities": project_contract.get("modalities") if project_contract else [],
        "upload_inventory_contract_status": upload_inventory_contract.get("status") if upload_inventory_contract else "skipped",
        "upload_inventory_session_id": upload_inventory_contract.get("upload_session_id") if upload_inventory_contract else None,
        "upload_inventory_status": upload_inventory_contract.get("inventory_status") if upload_inventory_contract else None,
        "upload_inventory_series_count": upload_inventory_contract.get("series_count") if upload_inventory_contract else 0,
        "upload_inventory_series_with_workflow_eligibility": upload_inventory_contract.get("series_with_workflow_eligibility") if upload_inventory_contract else 0,
        "upload_inventory_modalities": upload_inventory_contract.get("modalities") if upload_inventory_contract else [],
        "task_artifact_manifest_status": task_artifact_manifest.get("status") if task_artifact_manifest else "skipped",
        "artifact_manifest_task_id": task_artifact_manifest.get("task_id") if task_artifact_manifest else None,
        "artifact_manifest_artifact_count": task_artifact_manifest.get("artifact_count") if task_artifact_manifest else 0,
        "artifact_manifest_preview_kinds": task_artifact_manifest.get("preview_kinds") if task_artifact_manifest else [],
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
