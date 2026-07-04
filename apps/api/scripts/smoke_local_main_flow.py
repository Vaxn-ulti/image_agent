from __future__ import annotations

import argparse
import gzip
import json
import mimetypes
import re
import struct
import tempfile
import time
import urllib.error
import urllib.request
from collections.abc import Sequence
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4


DEFAULT_WORKFLOW_TYPE = "t1_deepprep_mock"
DEFAULT_PROJECT_NAME = "local-main-flow-smoke"


def _request(method: str, url: str, payload: dict | None = None) -> dict | list:
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


def _write_minimal_nifti(path: Path) -> None:
    header = bytearray(348)
    struct.pack_into("<i", header, 0, 348)
    struct.pack_into("<8h", header, 40, 3, 2, 2, 2, 1, 1, 1, 1)
    struct.pack_into("<h", header, 70, 16)
    struct.pack_into("<h", header, 72, 32)
    struct.pack_into("<8f", header, 76, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0)
    struct.pack_into("<f", header, 108, 352.0)
    header[344:348] = b"n+1\0"
    data = b"\0" * (2 * 2 * 2 * 4)
    with gzip.open(path, "wb") as handle:
        handle.write(bytes(header))
        handle.write(b"\0\0\0\0")
        handle.write(data)


def _int_id(payload: dict, key: str, label: str) -> int:
    value = payload.get(key)
    _require(isinstance(value, int) and not isinstance(value, bool) and value > 0, f"{label} missing positive {key}")
    return value


def _is_privacy_safe_symbol(value: object) -> bool:
    return (
        isinstance(value, str)
        and bool(value)
        and len(value) <= 140
        and all(char.isalnum() or char in "_.-" for char in value)
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


def _safe_model_status(status: dict) -> dict:
    safe: dict = {"configured": bool(status.get("configured"))}
    for key in ("provider", "provider_profile", "model", "review_model", "wire_api", "reasoning_effort"):
        value = status.get(key)
        if isinstance(value, str) and value and len(value) <= 120:
            safe[key] = value
    capabilities = status.get("capabilities")
    if isinstance(capabilities, dict):
        safe_capabilities = {}
        for key in ("text", "structured_json", "model_tool_loop"):
            if isinstance(capabilities.get(key), bool):
                safe_capabilities[key] = capabilities[key]
        if safe_capabilities:
            safe["capabilities"] = safe_capabilities
    gateway = status.get("gateway_diagnostics")
    if isinstance(gateway, dict):
        safe_gateway = {
            key: value
            for key, value in gateway.items()
            if isinstance(key, str)
            and isinstance(value, str)
            and key.replace("_", "").isalnum()
            and all(char.isalnum() or char in "_.-" for char in value)
        }
        if safe_gateway:
            safe["gateway_diagnostics"] = safe_gateway
    return safe


def _safe_series(series: dict) -> dict:
    safe = {
        "project_id": _int_id(series, "project_id", "series"),
        "series_id": _int_id(series, "id", "series"),
        "modality": str(series.get("modality") or ""),
        "sequence_label": str(series.get("sequence_label") or ""),
    }
    workflow_eligibility = _safe_workflow_eligibility(series.get("workflow_eligibility"))
    if workflow_eligibility:
        safe["workflow_eligibility"] = workflow_eligibility
    return safe


def _safe_workflow_entry(entry: object) -> dict | None:
    if not isinstance(entry, dict):
        return None
    workflow_type = entry.get("workflow_type")
    if not isinstance(workflow_type, str) or not workflow_type:
        return None
    safe = {"workflow_type": workflow_type}
    workflow_metadata = _safe_workflow_metadata(entry.get("workflow_metadata"), workflow_type=workflow_type)
    if workflow_metadata:
        safe["workflow_metadata"] = workflow_metadata
    blocking_reasons = entry.get("blocking_reasons")
    if isinstance(blocking_reasons, list):
        safe_reasons = [reason for reason in blocking_reasons if isinstance(reason, str) and reason and len(reason) <= 180]
        if safe_reasons:
            safe["blocking_reasons"] = safe_reasons
    return safe


def _safe_workflow_metadata(metadata: object, *, workflow_type: str) -> dict | None:
    if not isinstance(metadata, dict):
        return None
    metadata_workflow_type = metadata.get("workflow_type")
    if metadata_workflow_type != workflow_type or not _safe_symbol(metadata_workflow_type):
        return None
    safe: dict = {"workflow_type": metadata_workflow_type}
    runtime_workflow_type = metadata.get("runtime_workflow_type")
    if isinstance(runtime_workflow_type, str) and _safe_symbol(runtime_workflow_type):
        safe["runtime_workflow_type"] = runtime_workflow_type
    for key in ("workflow_family", "workflow_role"):
        value = metadata.get(key)
        if isinstance(value, str) and _safe_symbol(value):
            safe[key] = value
    display_name = metadata.get("display_name")
    if isinstance(display_name, str) and 0 < len(display_name) <= 160 and _safe_human_text(display_name):
        safe["display_name"] = display_name
    capability_summary = metadata.get("capability_summary")
    if isinstance(capability_summary, str) and _safe_human_text(capability_summary, max_len=320):
        safe["capability_summary"] = capability_summary
    for key in ("primary_outputs", "qc_outputs", "report_outputs", "limitations"):
        values = _safe_text_list(metadata.get(key), max_items=8, max_len=160)
        if values is not None:
            safe[key] = values
    pipeline_stages = _safe_pipeline_stages(metadata.get("pipeline_stages"))
    if pipeline_stages is not None:
        safe["pipeline_stages"] = pipeline_stages
    for key in ("agent_selectable", "is_report_only"):
        value = metadata.get(key)
        if isinstance(value, bool):
            safe[key] = value
    return safe


def _safe_symbol(value: str) -> bool:
    return bool(value) and len(value) <= 120 and all(ch.isalnum() or ch in {"_", "-", "."} for ch in value)


def _safe_human_text(value: str, *, max_len: int = 160) -> bool:
    if not value or len(value) > max_len:
        return False
    lowered = value.lower()
    return "://" not in value and "\\" not in value and not any(
        token in lowered for token in ("/home/", "/users/", "/tmp/", "/var/")
    )


def _safe_text_list(value: object, *, max_items: int, max_len: int) -> list[str] | None:
    if not isinstance(value, list):
        return None
    safe_items = [item for item in value[:max_items] if isinstance(item, str) and _safe_human_text(item, max_len=max_len)]
    return safe_items if safe_items else None


def _safe_pipeline_stages(value: object) -> list[dict] | None:
    if not isinstance(value, list):
        return None
    safe_stages: list[dict] = []
    for item in value[:8]:
        if not isinstance(item, dict):
            continue
        name = item.get("name")
        purpose = item.get("purpose")
        if not isinstance(name, str) or not _safe_human_text(name, max_len=80):
            continue
        safe_stage = {"name": name}
        if isinstance(purpose, str) and _safe_human_text(purpose, max_len=180):
            safe_stage["purpose"] = purpose
        safe_stages.append(safe_stage)
    return safe_stages if safe_stages else None


def _safe_workflow_eligibility(eligibility: object) -> dict | None:
    if not isinstance(eligibility, dict):
        return None
    safe: dict = {}
    policy_version = eligibility.get("policy_version")
    if isinstance(policy_version, str) and policy_version:
        safe["policy_version"] = policy_version
    if isinstance(eligibility.get("production_task_created"), bool):
        safe["production_task_created"] = eligibility["production_task_created"]
    primary = eligibility.get("primary_recommendation")
    if isinstance(primary, dict):
        primary_workflow = _safe_workflow_entry(primary)
        if primary_workflow:
            safe["primary_recommendation"] = primary_workflow
    for key in ("runnable_workflows", "blocked_workflows"):
        entries = eligibility.get(key)
        if isinstance(entries, list):
            safe_entries = [item for item in (_safe_workflow_entry(entry) for entry in entries) if item]
            if safe_entries:
                safe[key] = safe_entries
    return safe or None


def _safe_task(task: dict) -> dict:
    return {
        "project_id": _int_id(task, "project_id", "task"),
        "series_id": _int_id(task, "series_id", "task"),
        "task_id": _int_id(task, "id", "task"),
        "workflow_type": str(task.get("workflow_type") or ""),
        "status": str(task.get("status") or ""),
    }


def _safe_outputs(outputs: object) -> list[dict]:
    _require(isinstance(outputs, list), "task outputs response must be a list")
    safe_outputs = []
    for output in outputs:
        if not isinstance(output, dict):
            continue
        item = {}
        for key in ("id", "task_id", "size_bytes"):
            value = output.get(key)
            if isinstance(value, int) and not isinstance(value, bool):
                item[key] = value
        for key in ("output_type", "kind", "name", "relative_path", "download_url", "content_type", "preview_kind"):
            value = output.get(key)
            if isinstance(value, str) and value and len(value) <= 160:
                item[key] = value
        if item:
            item.pop("task_id", None)
            safe_outputs.append(item)
    return safe_outputs


def _safe_result_summary(summary: dict) -> dict:
    safe: dict = {}
    for key in ("contract_version", "workflow_type", "modality"):
        value = summary.get(key)
        if isinstance(value, str) and value and len(value) <= 160:
            safe[key] = value
    for key in ("task_id", "project_id"):
        value = summary.get(key)
        if isinstance(value, int) and not isinstance(value, bool):
            safe[key] = value
    return safe


def _safe_artifact_manifest(manifest: dict) -> dict:
    safe: dict = {}
    for key in ("contract_version",):
        value = manifest.get(key)
        if isinstance(value, str) and value and len(value) <= 160:
            safe[key] = value
    for key in ("task_id", "project_id"):
        value = manifest.get(key)
        if isinstance(value, int) and not isinstance(value, bool):
            safe[key] = value
    result_summary = manifest.get("result_summary")
    if isinstance(result_summary, dict):
        safe["result_summary_available"] = result_summary.get("available") is True
    artifacts = manifest.get("artifacts")
    if isinstance(artifacts, list):
        safe["artifact_count"] = len(artifacts)
    return safe


def _safe_rag_rebuild(rebuild: dict) -> dict:
    return {
        "document_count": rebuild.get("document_count") if isinstance(rebuild.get("document_count"), int) else None,
        "chunk_count": rebuild.get("chunk_count") if isinstance(rebuild.get("chunk_count"), int) else None,
        "semantic_index": rebuild.get("semantic_index") is True,
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


def _safe_agent_run(run: dict) -> dict:
    safe: dict = {}
    for key in ("agent_run_id", "thread_id", "status", "intent", "action_lane", "selected_skill", "workflow_type"):
        value = run.get(key)
        if isinstance(value, str) and value and len(value) <= 140:
            safe[key] = value
    for key in ("project_id", "series_id", "task_id"):
        value = run.get(key)
        if isinstance(value, int) and not isinstance(value, bool):
            safe[key] = value
    if isinstance(run.get("production_task_created"), bool):
        safe["production_task_created"] = run["production_task_created"]
    return safe


def _safe_agent_resume(run: dict) -> dict:
    safe = _safe_agent_run(run)
    safe_metadata = run.get("safe_metadata")
    if isinstance(safe_metadata, dict):
        confirmation_gate = safe_metadata.get("confirmation_gate")
        if isinstance(confirmation_gate, str) and confirmation_gate:
            safe["confirmation_gate"] = confirmation_gate
    return safe


def _write_payload(payload: dict, output_json: Path | None) -> None:
    text = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)
    if output_json:
        output_json.parent.mkdir(parents=True, exist_ok=True)
        output_json.write_text(text + "\n", encoding="utf-8")
    else:
        print(text)


def _find_series(series_list: object, series_id: int) -> dict:
    _require(isinstance(series_list, list), "series list response must be a list")
    for item in series_list:
        if isinstance(item, dict) and item.get("id") == series_id:
            return item
    raise SystemExit(f"uploaded series {series_id} was not returned by /projects/{{project_id}}/series")


def _validate_task_list(task_list: object, task_id: int) -> None:
    _require(isinstance(task_list, list), "task list response must be a list")
    _require(
        any(isinstance(task, dict) and task.get("id") == task_id for task in task_list),
        f"launched task {task_id} was not returned by /projects/{{project_id}}/tasks",
    )


def _prepare_agent_confirmation(base: str, project_id: int, series_id: int, workflow_type: str) -> dict:
    message = (
        f"Prepare a workflow confirmation for project {project_id}, series {series_id}, "
        f"workflow {workflow_type}. Do not create or launch the task."
    )
    run = _request("POST", f"{base}/agent/runs", {"project_id": project_id, "message": message})
    _require(isinstance(run, dict), "agent run response must be an object")
    if run.get("status") != "confirmation_required":
        raise SystemExitWithPayload("agent did not return confirmation_required", {"agent_run": _safe_agent_run(run)})
    if run.get("production_task_created") is True:
        raise SystemExitWithPayload(
            "agent created a production task before explicit approval",
            {"agent_run": _safe_agent_run(run)},
        )
    confirmation = run.get("confirmation")
    _require(isinstance(confirmation, dict), "agent confirmation is missing")
    _require(confirmation.get("project_id") == project_id, "agent confirmation project_id mismatch")
    _require(confirmation.get("series_id") == series_id, "agent confirmation series_id mismatch")
    _require(confirmation.get("workflow_type") == workflow_type, "agent confirmation workflow_type mismatch")
    thread_id = run.get("thread_id")
    _require(isinstance(thread_id, str) and thread_id, "agent confirmation thread_id is missing")
    return run


def _safe_agent_confirmation(run: dict, project_id: int, series_id: int, workflow_type: str) -> dict:
    return {
        "project_id": project_id,
        "series_id": series_id,
        "workflow_type": workflow_type,
        "production_task_created": False,
    }


def _run_agent_confirmation(base: str, project_id: int, series_id: int, workflow_type: str) -> dict:
    _prepare_agent_confirmation(base, project_id, series_id, workflow_type)
    return _safe_agent_confirmation({}, project_id, series_id, workflow_type)


def _resume_agent_confirmation(base: str, confirmation_run: dict) -> dict:
    thread_id = confirmation_run.get("thread_id")
    confirmation = confirmation_run.get("confirmation")
    _require(isinstance(thread_id, str) and thread_id, "agent resume thread_id is missing")
    _require(isinstance(confirmation, dict), "agent resume confirmation is missing")
    run = _request(
        "POST",
        f"{base}/agent/runs/{thread_id}/resume",
        {"approved": True, "confirmation": confirmation},
    )
    _require(isinstance(run, dict), "agent resume response must be an object")
    if run.get("status") != "task_created":
        raise SystemExitWithPayload("agent resume did not return task_created", {"agent_resume": _safe_agent_run(run)})
    _require(run.get("production_task_created") is True, "agent resume did not create a production task")
    safe_metadata = run.get("safe_metadata")
    _require(isinstance(safe_metadata, dict), "agent resume safe_metadata is missing")
    _require(safe_metadata.get("confirmation_gate") == "fingerprint_verified", "agent resume confirmation_gate mismatch")
    task = run.get("task")
    _require(isinstance(task, dict), "agent resume task is missing")
    _require(task.get("project_id") == confirmation.get("project_id"), "agent resume task project_id mismatch")
    _require(task.get("series_id") == confirmation.get("series_id"), "agent resume task series_id mismatch")
    _require(task.get("workflow_type") == confirmation.get("workflow_type"), "agent resume task workflow_type mismatch")
    task_id = task.get("id")
    if "task_id" in run:
        _require(run.get("task_id") == task_id, "agent resume task_id mismatch")
    return run


def _wait_for_task_completion(base: str, task_id: int, *, timeout_seconds: float, poll_seconds: float) -> dict:
    deadline = time.monotonic() + timeout_seconds
    last_task: dict | None = None
    while True:
        task = _request("GET", f"{base}/tasks/{task_id}")
        _require(isinstance(task, dict), "task status response must be an object")
        last_task = task
        status = str(task.get("status") or "")
        if status == "completed":
            return _safe_task(task)
        if status in {"failed", "cancelled"}:
            raise SystemExit(f"task {task_id} ended with status {status}")
        if time.monotonic() >= deadline:
            raise SystemExit(f"task {task_id} did not complete within {timeout_seconds:g} seconds; last status={status}")
        if poll_seconds > 0:
            time.sleep(poll_seconds)


class SystemExitWithPayload(SystemExit):
    def __init__(self, message: str, payload_update: dict) -> None:
        super().__init__(message)
        self.payload_update = payload_update


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a fast local Image Agent product main-flow smoke.")
    parser.add_argument("--api-base", required=True, help="Local API base URL, for example http://127.0.0.1:8000")
    parser.add_argument("--project-name", default=DEFAULT_PROJECT_NAME)
    parser.add_argument("--workflow-type", default=DEFAULT_WORKFLOW_TYPE)
    parser.add_argument("--agent-workflow-type")
    parser.add_argument("--upload-nifti-file", type=Path)
    parser.add_argument("--require-agent-confirmation", action="store_true")
    parser.add_argument("--require-agent-resume", action="store_true")
    parser.add_argument("--rebuild-rag", action="store_true")
    parser.add_argument("--min-rag-documents", type=int, default=0)
    parser.add_argument("--wait-task-completion-timeout-seconds", type=float, default=0)
    parser.add_argument("--wait-task-completion-poll-seconds", type=float, default=1)
    parser.add_argument("--require-task-outputs", action="store_true")
    parser.add_argument("--require-task-events", action="store_true")
    parser.add_argument("--require-result-summary", action="store_true")
    parser.add_argument("--require-artifact-manifest", action="store_true")
    parser.add_argument("--expected-model-provider-profile")
    parser.add_argument("--expected-model-wire-api")
    parser.add_argument("--expected-model-name")
    parser.add_argument("--require-model-tool-loop", action="store_true")
    parser.add_argument("--output-json", type=Path)
    return parser.parse_args(argv)


def _validate_model_expectations(model_status: dict, args: argparse.Namespace) -> None:
    if args.expected_model_provider_profile:
        actual = model_status.get("provider_profile")
        _require(
            actual == args.expected_model_provider_profile,
            f"model provider_profile {actual or 'missing'} did not match --expected-model-provider-profile {args.expected_model_provider_profile}",
        )
    if args.expected_model_wire_api:
        actual = model_status.get("wire_api")
        _require(
            actual == args.expected_model_wire_api,
            f"model wire_api {actual or 'missing'} did not match --expected-model-wire-api {args.expected_model_wire_api}",
        )
    if args.expected_model_name:
        actual = model_status.get("model")
        _require(
            actual == args.expected_model_name,
            f"model name {actual or 'missing'} did not match --expected-model-name {args.expected_model_name}",
        )
    if args.require_model_tool_loop:
        capabilities = model_status.get("capabilities")
        _require(isinstance(capabilities, dict), "model capabilities are missing")
        _require(capabilities.get("model_tool_loop") is True, "model capabilities.model_tool_loop must be true")


def main(argv: Sequence[str] | None = None) -> None:
    args = _parse_args(argv)
    if args.require_agent_resume and not args.require_agent_confirmation:
        raise SystemExit("--require-agent-resume requires --require-agent-confirmation")
    if args.require_task_events and not args.wait_task_completion_timeout_seconds:
        raise SystemExit("--require-task-events requires --wait-task-completion-timeout-seconds")
    base = args.api_base.rstrip("/")
    workflow_type = args.workflow_type
    agent_workflow_type = args.agent_workflow_type or workflow_type
    payload: dict = {
        "status": "started",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "api_base": base,
        "workflow_type": workflow_type,
        "agent_workflow_type": agent_workflow_type,
        "boundary": {
            "local_smoke_only": True,
            "remote_container_execution_required_for_release": True,
            "workflow_launch_uses_deterministic_backend_api": True,
            "agent_cannot_bypass_resume_confirmation": True,
        },
    }
    try:
        health = _request("GET", f"{base}/health")
        _require(isinstance(health, dict) and health.get("status") == "ok", "/health did not report ok")
        _require(health.get("app") in {None, "image_agent"}, "/health app identity is not image_agent")
        payload["health_status"] = "passed"
        payload["health"] = {key: health[key] for key in ("status", "app", "version") if key in health}

        project = _request("POST", f"{base}/projects", {"name": args.project_name, "description": "local product main-flow smoke"})
        _require(isinstance(project, dict), "project creation response must be an object")
        project_id = _int_id(project, "id", "project")
        payload["project"] = {"project_id": project_id}

        with tempfile.TemporaryDirectory(prefix="image-agent-local-smoke-") as temp_dir:
            upload_path = args.upload_nifti_file
            if upload_path is None:
                upload_path = Path(temp_dir) / "sub-local-smoke_T1w.nii.gz"
                _write_minimal_nifti(upload_path)
            upload = _upload_nifti(base, project_id, upload_path)
        _require(isinstance(upload, dict), "upload response must be an object")
        series = upload.get("series")
        _require(isinstance(series, dict), "upload response did not include series")
        uploaded_series = _safe_series(series)
        series_id = uploaded_series["series_id"]
        payload["upload_status"] = "passed"
        payload["uploaded_series"] = uploaded_series

        listed_series = _find_series(_request("GET", f"{base}/projects/{project_id}/series"), series_id)
        _require(listed_series.get("project_id") in {None, project_id}, "listed series project_id mismatch")
        payload["series_list_status"] = "passed"

        launched_task: dict | None = None
        if not args.require_agent_resume:
            task = _request("POST", f"{base}/series/{series_id}/run", {"workflow_type": workflow_type})
            _require(isinstance(task, dict), "workflow launch response must be an object")
            launched_task = _safe_task(task)
            _require(launched_task["project_id"] == project_id, "launched task project_id mismatch")
            _require(launched_task["series_id"] == series_id, "launched task series_id mismatch")
            _require(launched_task["workflow_type"] == workflow_type, "launched task workflow_type mismatch")
            payload["workflow_launch_status"] = "passed"
            payload["launched_task"] = launched_task

        model_status = _request("GET", f"{base}/agent/model/status")
        _require(isinstance(model_status, dict), "model status response must be an object")
        payload["model_status"] = _safe_model_status(model_status)
        _validate_model_expectations(model_status, args)
        if args.require_agent_confirmation and model_status.get("configured") is True:
            confirmation_run = _prepare_agent_confirmation(base, project_id, series_id, agent_workflow_type)
            payload["agent_workflow_confirmation"] = _safe_agent_confirmation(
                confirmation_run,
                project_id,
                series_id,
                agent_workflow_type,
            )
            if args.require_agent_resume:
                resume_run = _resume_agent_confirmation(base, confirmation_run)
                payload["agent_workflow_resume_status"] = "passed"
                payload["agent_workflow_resume"] = _safe_agent_resume(resume_run)
                launched_task = _safe_task(resume_run["task"])
                _require(launched_task["project_id"] == project_id, "agent-resumed task project_id mismatch")
                _require(launched_task["series_id"] == series_id, "agent-resumed task series_id mismatch")
                _require(launched_task["workflow_type"] == agent_workflow_type, "agent-resumed task workflow_type mismatch")
                payload["workflow_launch_status"] = "passed_via_agent_resume"
                payload["launched_task"] = launched_task
            payload["agent_boundary_status"] = "passed"
        elif args.require_agent_confirmation:
            raise SystemExit("agent confirmation required but model gateway is not configured")
        elif model_status.get("configured") is True:
            payload["agent_boundary_status"] = "model_configured_confirmation_not_required"
        else:
            payload["agent_boundary_status"] = "skipped_missing_model_config"

        _require(launched_task is not None, "workflow launch did not produce a task")
        _validate_task_list(_request("GET", f"{base}/projects/{project_id}/tasks"), launched_task["task_id"])
        payload["task_list_status"] = "passed"

        if args.wait_task_completion_timeout_seconds:
            completed_task = _wait_for_task_completion(
                base,
                launched_task["task_id"],
                timeout_seconds=args.wait_task_completion_timeout_seconds,
                poll_seconds=args.wait_task_completion_poll_seconds,
            )
            payload["task_completion_status"] = "passed"
            payload["completed_task"] = completed_task
        if args.require_task_events:
            _require(completed_task is not None, "task events require completed task evidence")
            task_events = _validate_task_events(
                _request("GET", f"{base}/tasks/{launched_task['task_id']}/events"),
                launched_task["task_id"],
                completed_task,
            )
            payload["task_events_status"] = task_events["status"]
            payload["task_events_task_id"] = task_events["task_id"]
            payload["task_events_event_types"] = task_events["event_types"]
            payload["task_events_status_event_status"] = task_events["status_event_status"]
            payload["task_events_remote_log_count"] = task_events["remote_log_count"]
            payload["task_events_remote_log_source_stages"] = task_events["remote_log_source_stages"]
            payload["task_events_main_log_tail_present"] = task_events["main_log_tail_present"]
        if args.require_task_outputs:
            outputs = _safe_outputs(_request("GET", f"{base}/tasks/{launched_task['task_id']}/outputs"))
            _require(outputs, "task outputs are required but none were returned")
            payload["task_outputs_status"] = "passed"
            payload["task_outputs"] = outputs
        if args.require_result_summary:
            result_summary = _request("GET", f"{base}/tasks/{launched_task['task_id']}/result-summary")
            _require(isinstance(result_summary, dict), "result-summary response must be an object")
            _require(result_summary.get("task_id") == launched_task["task_id"], "result-summary task_id mismatch")
            _require(result_summary.get("project_id") == project_id, "result-summary project_id mismatch")
            _require(result_summary.get("workflow_type") == launched_task["workflow_type"], "result-summary workflow_type mismatch")
            payload["result_summary_status"] = "passed"
            payload["result_summary"] = _safe_result_summary(result_summary)
        if args.require_artifact_manifest:
            manifest = _request("GET", f"{base}/tasks/{launched_task['task_id']}/artifact-manifest")
            _require(isinstance(manifest, dict), "artifact-manifest response must be an object")
            _require(manifest.get("task_id") == launched_task["task_id"], "artifact-manifest task_id mismatch")
            _require(manifest.get("project_id") in {None, project_id}, "artifact-manifest project_id mismatch")
            result_summary = manifest.get("result_summary")
            _require(isinstance(result_summary, dict) and result_summary.get("available") is True, "artifact manifest result_summary is not available")
            artifacts = manifest.get("artifacts")
            _require(isinstance(artifacts, list) and len(artifacts) > 0, "artifact manifest has no artifacts")
            payload["artifact_manifest_status"] = "passed"
            payload["artifact_manifest"] = _safe_artifact_manifest(manifest)

        if args.rebuild_rag:
            rag_rebuild = _request("POST", f"{base}/agent/rag/rebuild")
            _require(isinstance(rag_rebuild, dict), "RAG rebuild response must be an object")
            payload["rag_rebuild_status"] = "passed"
            payload["rag_rebuild"] = _safe_rag_rebuild(rag_rebuild)

        rag_status = _request("GET", f"{base}/agent/rag/status")
        _require(isinstance(rag_status, dict), "RAG status response must be an object")
        _require(isinstance(rag_status.get("grounding_policy"), dict), "RAG grounding_policy is missing")
        document_count = (rag_status.get("index") or {}).get("document_count") if isinstance(rag_status.get("index"), dict) else None
        if args.min_rag_documents:
            _require(
                isinstance(document_count, int) and document_count >= args.min_rag_documents,
                f"RAG document_count {document_count} is below required minimum {args.min_rag_documents}",
            )
        payload["rag_boundary_status"] = "passed"
        payload["rag_status"] = {
            "grounding_policy_present": True,
            "document_count": document_count,
            "min_documents_required": args.min_rag_documents,
        }
        payload["status"] = "passed"
    except SystemExitWithPayload as exc:
        payload.update(exc.payload_update)
        payload.setdefault("agent_boundary_status", "failed")
        payload["status"] = "failed"
        payload["failure_reason"] = str(exc)
        _write_payload(payload, args.output_json)
        raise SystemExit(str(exc)) from exc
    except SystemExit:
        raise

    _write_payload(payload, args.output_json)


if __name__ == "__main__":
    main()
