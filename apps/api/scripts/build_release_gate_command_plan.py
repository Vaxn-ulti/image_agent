from __future__ import annotations

import argparse
import ipaddress
import importlib.util
import json
import re
from collections.abc import Sequence
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlsplit


PLACEHOLDER_APPROVAL_JSON = "<fresh_reviewed_approval_json>"
EXPIRED_APPROVAL_JSON = "/tmp/image_agent_stale_tasks_83_84_dry_run_20260614T080202Z.json"


def _load_script(name: str):
    script = Path(__file__).resolve().with_name(name)
    spec = importlib.util.spec_from_file_location(name.removesuffix(".py"), script)
    module = importlib.util.module_from_spec(spec)
    if spec.loader is None:
        raise RuntimeError(f"could not load {name}")
    spec.loader.exec_module(module)
    return module


def _parse_utc_timestamp(value: str | None, *, key: str) -> datetime | None:
    if value is None:
        return None
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise SystemExit(f"{key} must be an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise SystemExit(f"{key} must be timezone-aware")
    return parsed.astimezone(timezone.utc)


def _replace_string_values(value: object, *, old: str, new: str) -> object:
    if isinstance(value, dict):
        return {key: _replace_string_values(item, old=old, new=new) for key, item in value.items()}
    if isinstance(value, list):
        return [_replace_string_values(item, old=old, new=new) for item in value]
    if isinstance(value, str):
        return value.replace(old, new)
    return value


def _replace_step_string_values(step: dict, *, old: str, new: str) -> None:
    command = step.get("command")
    if isinstance(command, str):
        step["command"] = command.replace(old, new)
    expected_success = step.get("expected_success")
    if isinstance(expected_success, list):
        step["expected_success"] = [item.replace(old, new) if isinstance(item, str) else item for item in expected_success]


def _remote_approval_json_path(value: str | None, *, fallback: Path) -> str:
    text = value or str(fallback)
    normalized = text.replace("\\", "/")
    invalid_message = "approval_json_command_path must be a /tmp/image_agent_*.json remote path"
    if not (normalized.startswith("/tmp/image_agent_") and normalized.endswith(".json")):
        raise SystemExit(invalid_message)
    if any(part in {"", ".", ".."} for part in normalized.split("/")[1:]):
        raise SystemExit(invalid_message)
    return normalized


def _required_text(value: str | None, *, key: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise SystemExit(f"{key} is required")
    return value.strip()


def _required_privacy_safe_release_symbol(value: str | None, *, key: str) -> str:
    text = _required_text(value, key=key)
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{2,80}", text):
        raise SystemExit(f"{key} must be a privacy-safe release symbol")
    return text


def _required_remote_nifti_file(value: str | None) -> str:
    text = _required_text(value, key="remote_nifti_file").replace("\\", "/")
    if not (text.startswith("/") and (text.endswith(".nii") or text.endswith(".nii.gz"))):
        raise SystemExit("remote_nifti_file must be a remote .nii or .nii.gz path")
    return text


def _required_workflow_type(value: str | None) -> str:
    text = _required_text(value, key="workflow_type")
    if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{2,80}", text) or text.endswith("_mock"):
        raise SystemExit("workflow_type must be a concrete registered workflow type")
    return text


def _required_production_https_origin(value: str | None, *, key: str) -> str:
    text = _required_text(value, key=key)
    if not re.fullmatch(r"https://[A-Za-z0-9.-]+(?::[0-9]{1,5})?", text):
        raise SystemExit(f"{key} must be a public HTTPS origin")
    host = text.removeprefix("https://").split(":", 1)[0].lower()
    if not _is_public_deployment_host(host):
        raise SystemExit(f"{key} must be a public HTTPS origin")
    return text


def _deployment_scope_value(value: str | None) -> str:
    text = (value or "public_internet").strip().lower()
    if text not in {"public_internet", "private_network"}:
        raise SystemExit("deployment_scope must be public_internet or private_network")
    return text


def _is_private_network_host(host: str) -> bool:
    normalized = (host or "").strip().lower().rstrip(".")
    if normalized in {"localhost", "127.0.0.1", "::1"}:
        return True
    if normalized == "0.0.0.0":
        return False
    try:
        address = ipaddress.ip_address(normalized)
    except ValueError:
        return normalized.endswith(".local")
    return not address.is_global and not address.is_unspecified


def _required_private_network_origin(value: str | None, *, key: str) -> str:
    text = _required_text(value, key=key)
    parsed = urlsplit(text)
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or not _is_private_network_host(parsed.hostname)
        or parsed.path
        or parsed.query
        or parsed.fragment
    ):
        raise SystemExit(f"{key} must be a private-network HTTP(S) origin")
    return text


def _required_deployment_origin(value: str | None, *, key: str, deployment_scope: str) -> str:
    if deployment_scope == "private_network":
        return _required_private_network_origin(value, key=key)
    return _required_production_https_origin(value, key=key)


def _is_public_deployment_host(host: str) -> bool:
    normalized = (host or "").strip().lower().rstrip(".")
    if normalized in {"localhost", "127.0.0.1", "0.0.0.0", "::1"}:
        return False
    try:
        return ipaddress.ip_address(normalized).is_global
    except ValueError:
        return "." in normalized and not normalized.endswith(".local")


def _required_int(value: int | None, *, key: str) -> int:
    if isinstance(value, bool) or value is None or int(value) <= 0:
        raise SystemExit(f"{key} must be a positive integer")
    return int(value)


def _replace_strict_smoke_upload_source(plan: dict, *, uploaded_series_id: int | None) -> None:
    if uploaded_series_id is None:
        return
    uploaded_series_id_text = str(_required_int(uploaded_series_id, key="uploaded_series_id"))
    for step in plan.get("steps") or []:
        if not isinstance(step, dict) or step.get("id") != "run_strict_remote_smoke_acceptance":
            continue
        command = step.get("command")
        if not isinstance(command, str):
            continue
        step["command"] = command.replace(
            "--upload-nifti-file <remote_nifti_file>",
            f"--uploaded-series-id {uploaded_series_id_text}",
        )


def _required_remote_db_path(value: str | None, *, key: str) -> str:
    text = _required_text(value, key=key).replace("\\", "/")
    if not (text.startswith("/") and text.endswith(".db")):
        raise SystemExit(f"{key} must be an absolute remote .db path")
    if any(part in {"", ".", ".."} for part in text.split("/")[1:]):
        raise SystemExit(f"{key} must be an absolute remote .db path")
    return text


def _reuse_persisted_agent_launch_evidence(
    plan: dict,
    *,
    acceptance_task_id: int | None,
    uploaded_series_id: int | None,
    agent_state_db: str | None,
) -> None:
    if acceptance_task_id is None:
        return
    if uploaded_series_id is None:
        raise SystemExit("acceptance_task_id requires uploaded_series_id")
    task_id_text = str(_required_int(acceptance_task_id, key="acceptance_task_id"))
    series_id_text = str(_required_int(uploaded_series_id, key="uploaded_series_id"))
    agent_state_db_text = _required_remote_db_path(agent_state_db, key="agent_state_db")
    for step in plan.get("steps") or []:
        if not isinstance(step, dict) or step.get("id") != "run_strict_remote_smoke_acceptance":
            continue
        command = step.get("command")
        if not isinstance(command, str):
            continue
        marker = "--require-agent-workflow-confirmation "
        insertion = (
            "--reuse-persisted-agent-launch-evidence "
            f"--agent-state-db {agent_state_db_text} "
            f"--task-id {task_id_text} "
            f"--launch-series-id {series_id_text} "
        )
        if "--reuse-persisted-agent-launch-evidence" not in command:
            command = command.replace(marker, marker + insertion)
        step["command"] = command


def build_release_gate_plan(
    *,
    plan_json: Path,
    approval_json: Path,
    expected_task_ids: Sequence[int],
    max_age_hours: float,
    now_utc: str | None = None,
    approval_json_command_path: str | None = None,
    deployment_id: str | None = None,
    expected_health_version: str | None = None,
    remote_nifti_file: str | None = None,
    uploaded_series_id: int | None = None,
    acceptance_task_id: int | None = None,
    agent_state_db: str | None = None,
    workflow_type: str | None = None,
    project_id: int | None = None,
    upload_session_id: int | None = None,
    evidence_timestamp: str | None = None,
    deployment_scope: str | None = None,
    production_cors_origins: str | None = None,
    production_public_base_url: str | None = None,
) -> dict:
    approval_verifier = _load_script("verify_stale_task_approval.py")
    plan_verifier = _load_script("verify_release_gate_command_plan.py")

    source_plan = json.loads(plan_json.read_text(encoding="utf-8"))
    if source_plan.get("status") != "approval_refresh_required":
        raise SystemExit("source plan status must be approval_refresh_required")
    if source_plan.get("approval_json") != PLACEHOLDER_APPROVAL_JSON:
        raise SystemExit("source plan approval_json must be <fresh_reviewed_approval_json>")

    approval_payload = json.loads(approval_json.read_text(encoding="utf-8"))
    now = _parse_utc_timestamp(now_utc, key="now_utc")
    verified = approval_verifier.verify_approval_payload(
        approval_payload,
        expected_task_ids=expected_task_ids,
        now=now,
        max_age_hours=max_age_hours,
    )
    generated_at = _parse_utc_timestamp(
        verified["checked"]["generated_at_utc"],
        key="verified_approval.checked.generated_at_utc",
    )
    if generated_at is None:
        raise SystemExit("verified approval generated_at_utc is required")
    expires_at = generated_at + timedelta(hours=max_age_hours)

    approval_json_text = _remote_approval_json_path(approval_json_command_path, fallback=approval_json)
    deployment_id_text = _required_privacy_safe_release_symbol(deployment_id, key="deployment_id")
    expected_health_version_text = _required_privacy_safe_release_symbol(
        expected_health_version,
        key="expected_health_version",
    )
    remote_nifti_file_text = None if uploaded_series_id is not None else _required_remote_nifti_file(remote_nifti_file)
    workflow_type_text = _required_workflow_type(workflow_type)
    project_id_text = str(_required_int(project_id, key="project_id"))
    upload_session_id_text = str(_required_int(upload_session_id, key="upload_session_id"))
    evidence_timestamp_text = _required_text(evidence_timestamp, key="evidence_timestamp")
    deployment_scope_text = _deployment_scope_value(deployment_scope)
    production_cors_origins_text = _required_deployment_origin(
        production_cors_origins,
        key="production_cors_origins",
        deployment_scope=deployment_scope_text,
    )
    production_public_base_url_text = _required_deployment_origin(
        production_public_base_url,
        key="production_public_base_url",
        deployment_scope=deployment_scope_text,
    )
    plan = deepcopy(source_plan)
    plan = _replace_string_values(plan, old=PLACEHOLDER_APPROVAL_JSON, new=approval_json_text)
    if not isinstance(plan, dict):
        raise SystemExit("release gate plan must be a JSON object")
    _replace_strict_smoke_upload_source(plan, uploaded_series_id=uploaded_series_id)
    _reuse_persisted_agent_launch_evidence(
        plan,
        acceptance_task_id=acceptance_task_id,
        uploaded_series_id=uploaded_series_id,
        agent_state_db=agent_state_db,
    )
    replacements = {
        "<accepted_release_or_commit>": deployment_id_text,
        "<expected_health_version>": expected_health_version_text,
        "<remote_nifti_file>": remote_nifti_file_text,
        "<real_registered_workflow_type>": workflow_type_text,
        "<project_id>": project_id_text,
        "<upload_session_id>": upload_session_id_text,
        "<timestamp>": evidence_timestamp_text,
        "--deployment-scope public_internet": f"--deployment-scope {deployment_scope_text}",
        "IMAGE_AGENT_DEPLOYMENT_SCOPE=public_internet": f"IMAGE_AGENT_DEPLOYMENT_SCOPE={deployment_scope_text}",
        "https://<console-hostname>": production_cors_origins_text,
        "https://<api-hostname>": production_public_base_url_text,
    }
    for step in plan.get("steps") or []:
        if not isinstance(step, dict):
            continue
        for placeholder, value in replacements.items():
            if value is not None:
                _replace_step_string_values(step, old=placeholder, new=value)
    previous_state = source_plan.get("approval_json_state") if isinstance(source_plan.get("approval_json_state"), dict) else {}
    plan["status"] = "operator_authorization_required"
    plan["approval_json"] = approval_json_text
    plan["approval_json_state"] = {
        "status": "fresh_reviewed",
        "previous_approval_json": previous_state.get("previous_approval_json") or EXPIRED_APPROVAL_JSON,
        "verified_approval_generated_at_utc": generated_at.isoformat(),
        "approval_expires_at_utc": expires_at.isoformat(),
        "next_required_step": "apply_approved_stale_task_resolution",
    }
    plan["stale_task_approval_refresh"] = {
        "status": "superseded_by_fresh_reviewed_approval",
        "source_approval_json": approval_json_text,
        "approval_expires_at_utc": expires_at.isoformat(),
        "next_required_step": "apply_approved_stale_task_resolution",
        "mutates_remote_state": False,
        "requires_operator_authorization": False,
    }

    plan_verifier.verify_plan(plan, now_utc=now or datetime.now(timezone.utc))
    return plan


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Materialize a release-gate command plan from a fresh reviewed approval JSON.")
    parser.add_argument("plan_json", help="Path to the refresh-required release gate command plan JSON.")
    parser.add_argument("approval_json", help="Path to the refreshed reviewed stale-task approval dry-run JSON.")
    parser.add_argument("--task-id", action="append", type=int, dest="task_ids", required=True)
    parser.add_argument("--max-age-hours", type=float, default=24.0)
    parser.add_argument("--now-utc", default=None, help="Testing hook: ISO-8601 UTC timestamp used for freshness checks.")
    parser.add_argument(
        "--approval-json-command-path",
        default=None,
        help=(
            "Remote /tmp/image_agent_*.json approval path to embed in commands "
            "when the readable approval_json path differs from the server path."
        ),
    )
    parser.add_argument("--deployment-id", default=None)
    parser.add_argument("--expected-health-version", default=None)
    parser.add_argument("--remote-nifti-file", default=None)
    parser.add_argument("--uploaded-series-id", type=int, default=None)
    parser.add_argument("--acceptance-task-id", type=int, default=None)
    parser.add_argument("--agent-state-db", default=None)
    parser.add_argument("--workflow-type", default=None)
    parser.add_argument("--project-id", type=int, default=None)
    parser.add_argument("--upload-session-id", type=int, default=None)
    parser.add_argument("--evidence-timestamp", default=None)
    parser.add_argument("--deployment-scope", choices=["public_internet", "private_network"], default=None)
    parser.add_argument("--production-cors-origins", default=None)
    parser.add_argument("--production-public-base-url", default=None)
    parser.add_argument("--output-json", default=None, help="Optional path to save the materialized release gate plan.")
    args = parser.parse_args(argv)

    plan = build_release_gate_plan(
        plan_json=Path(args.plan_json),
        approval_json=Path(args.approval_json),
        expected_task_ids=args.task_ids,
        max_age_hours=args.max_age_hours,
        now_utc=args.now_utc,
        approval_json_command_path=args.approval_json_command_path,
        deployment_id=args.deployment_id,
        expected_health_version=args.expected_health_version,
        remote_nifti_file=args.remote_nifti_file,
        uploaded_series_id=args.uploaded_series_id,
        acceptance_task_id=args.acceptance_task_id,
        agent_state_db=args.agent_state_db,
        workflow_type=args.workflow_type,
        project_id=args.project_id,
        upload_session_id=args.upload_session_id,
        evidence_timestamp=args.evidence_timestamp,
        deployment_scope=args.deployment_scope,
        production_cors_origins=args.production_cors_origins,
        production_public_base_url=args.production_public_base_url,
    )
    if args.output_json:
        Path(args.output_json).write_text(json.dumps(plan, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(plan, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
