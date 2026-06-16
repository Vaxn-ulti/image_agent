from __future__ import annotations

import argparse
import json
import mimetypes
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
    for key in ("store", "metadata_enabled"):
        if isinstance(status.get(key), bool):
            safe[key] = status[key]
    for key in ("context_window", "auto_compact_token_limit"):
        if isinstance(status.get(key), int) and not isinstance(status.get(key), bool):
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
    return {
        "agent_run_id": run["agent_run_id"],
        "status": "confirmation_required",
        "intent": "run_workflow",
        "project_id": confirmed_project_id,
        "series_id": confirmed_series_id,
        "workflow_type": confirmed_workflow_type,
        "selected_skill": run.get("selected_skill"),
        "production_task_created": False,
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
    return {
        "project_id": task_project_id,
        "series_id": series_id,
        "status": "completed",
        "task_id": task_id,
        "workflow_type": safe_workflow_type,
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
    _require(
        launched_workflow_type == workflow_type and _is_privacy_safe_symbol(launched_workflow_type),
        "launched task check failed: workflow_type mismatch",
    )
    launched_project_id = _int_metric(task.get("project_id"))
    if project_id is not None:
        _require(launched_project_id == project_id, "launched task check failed: project_id mismatch")
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
    sequence_label = series.get("sequence_label")
    if isinstance(sequence_label, str) and _is_privacy_safe_symbol(sequence_label):
        safe["sequence_label"] = sequence_label
    return safe


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


def _validate_upload_inventory_contract(response: dict, upload_session_id: int) -> dict:
    _require(int(response.get("upload_session_id") or 0) == upload_session_id, "upload inventory session id mismatch")
    inventory = response.get("inventory")
    _require(isinstance(inventory, dict), "upload inventory contract failed: inventory missing")
    series = inventory.get("series")
    _require(isinstance(series, list), "upload inventory contract failed: series missing")
    _require(bool(series), "upload inventory contract failed: no series found")
    series_ids = []
    for item in series:
        _validate_workflow_eligibility(
            item.get("workflow_eligibility"),
            "upload inventory contract failed",
        )
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
        "modality": modality,
        "feature_groups": feature_groups,
        "output_group_count": len(outputs),
        "output_item_count": output_item_count,
        "downloadable_output_count": len(downloadable_outputs),
        "downloadable_output_paths": [item["relative_path"] for item in downloadable_outputs],
        "downloadable_output_urls": [item["download_url"] for item in downloadable_outputs],
        "provenance_keys": sorted(str(key) for key in provenance),
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
        "--require-agent-workflow-confirmation",
        action="store_true",
        help="Fail unless /agent/runs can prepare a workflow confirmation without creating a production task.",
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
    if args.require_uploaded_series and (args.project_id is None or not args.upload_nifti_file):
        raise SystemExit("--require-uploaded-series requires --project-id and --upload-nifti-file")
    if args.require_project_agent_context and args.project_id is None:
        raise SystemExit("--require-project-agent-context requires --project-id")
    if args.require_agent_workflow_confirmation and args.project_id is None:
        raise SystemExit("--require-agent-workflow-confirmation requires --project-id")
    if args.require_agent_workflow_confirmation and not args.launch_workflow_type:
        raise SystemExit("--require-agent-workflow-confirmation requires --launch-workflow-type")
    if args.require_completed_upload and (args.project_id is None or args.upload_session_id is None):
        raise SystemExit("--require-completed-upload requires --project-id and --upload-session-id")
    if args.require_real_evidence_ids and (
        args.project_id is None or args.upload_session_id is None or (args.task_id is None and not args.require_launched_task)
    ):
        raise SystemExit(
            "--require-real-evidence-ids requires --project-id, --upload-session-id, and --task-id "
            "unless --require-launched-task will supply the backend task id"
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
    if args.require_launched_task and (
        (args.launch_series_id is None and not args.require_uploaded_series) or not args.launch_workflow_type
    ):
        raise SystemExit("--require-launched-task requires --launch-series-id and --launch-workflow-type")
    if args.launch_series_id is not None and args.launch_series_id <= 0:
        raise SystemExit("--launch-series-id must be a positive integer")
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
    if args.require_production_readiness:
        production_readiness = _safe_production_readiness(_request("GET", f"{base}/deployment"))
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
    upload_inventory_contract = None
    launched_task = None
    uploaded_series = None
    agent_workflow_confirmation = None
    if args.require_uploaded_series:
        uploaded_series = _validate_uploaded_series(
            _upload_nifti(base, args.project_id, Path(args.upload_nifti_file)),
            project_id=args.project_id,
        )
        if args.launch_series_id is not None and args.launch_series_id != uploaded_series["series_id"]:
            raise SystemExit("--launch-series-id must match the series returned by --require-uploaded-series")
        if args.launch_series_id is None:
            args.launch_series_id = uploaded_series["series_id"]
    if args.require_agent_workflow_confirmation:
        _require(
            args.launch_series_id is not None,
            "--require-agent-workflow-confirmation requires --launch-series-id or --require-uploaded-series",
        )
        workflow_message = (
            f"Prepare a workflow confirmation for series {args.launch_series_id} using workflow "
            f"{args.launch_workflow_type}. Do not launch it."
        )
        agent_workflow_confirmation = _validate_agent_workflow_confirmation(
            _request("POST", f"{base}/agent/runs", {"project_id": args.project_id, "message": workflow_message}),
            project_id=args.project_id,
            series_id=args.launch_series_id,
            workflow_type=args.launch_workflow_type,
        )
    if args.require_launched_task:
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
        "require_project_agent_context": bool(args.require_project_agent_context),
        "require_agent_workflow_confirmation": bool(args.require_agent_workflow_confirmation),
        "require_deployment_identity": bool(args.require_deployment_identity),
        "require_production_readiness": bool(args.require_production_readiness),
        "deployment_id": args.deployment_id,
        "min_documents": max(args.min_documents, 0),
        "min_chunks": max(args.min_chunks, 0),
        "require_raw_source_policy": bool(args.require_raw_source_policy),
        "require_vendor_pointer_integrity": bool(args.require_vendor_pointer_integrity),
        "require_real_evidence_ids": bool(args.require_real_evidence_ids),
        "require_completed_upload": bool(args.require_completed_upload),
        "require_uploaded_series": bool(args.require_uploaded_series),
        "require_completed_task": bool(args.require_completed_task),
        "require_launched_task": bool(args.require_launched_task),
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

    payload = {
        "generated_at_utc": _generated_at_utc(),
        "smoke_gate": smoke_gate,
        "health": health,
        "deployment_identity_status": "passed" if args.require_deployment_identity else "skipped",
        "deployment_identity": deployment_identity,
        "production_readiness_status": "passed" if args.require_production_readiness else "skipped",
        "production_readiness": production_readiness,
        "model_status": safe_model_status,
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
        "agent_model_gateway_status": "passed" if run else "skipped",
        "agent_model_gateway_access": run.get("model_gateway_access") if run else None,
        "agent_safe_metadata": _safe_agent_metadata(run),
        "agent_project_context_status": "passed" if args.require_project_agent_context else "skipped",
        "agent_run_project_id": run.get("project_id") if run else None,
        "agent_workflow_confirmation_status": "passed" if agent_workflow_confirmation else "skipped",
        "agent_workflow_confirmation": agent_workflow_confirmation,
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
        "upload_inventory_completion_status": "passed" if args.require_completed_upload else "skipped",
        "upload_inventory_session_id": upload_inventory_contract.get("upload_session_id") if upload_inventory_contract else None,
        "upload_inventory_status": upload_inventory_contract.get("inventory_status") if upload_inventory_contract else None,
        "upload_inventory_series_count": upload_inventory_contract.get("series_count") if upload_inventory_contract else 0,
        "upload_inventory_series_ids": upload_inventory_contract.get("series_ids") if upload_inventory_contract else [],
        "upload_inventory_series_with_workflow_eligibility": upload_inventory_contract.get("series_with_workflow_eligibility") if upload_inventory_contract else 0,
        "upload_inventory_modalities": upload_inventory_contract.get("modalities") if upload_inventory_contract else [],
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
