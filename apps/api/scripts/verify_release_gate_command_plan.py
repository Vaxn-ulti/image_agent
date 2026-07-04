from __future__ import annotations

import argparse
import ipaddress
import json
import re
import shlex
from collections.abc import Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable
from urllib.parse import urlsplit


PLAN_ID = "remote_release_gate_after_stale_task_approval_v1"
API_KEY_SHAPED_RE = re.compile(r"(?<![A-Za-z0-9])sk-[A-Za-z0-9_-]{10,}")
PLACEHOLDER_RE = re.compile(r"<[^>\s]+>")
REMOTE_RELEASE_ROOT = "/home/yyf/project/image_agent_releases"
REMOTE_ENV_LOAD_SNIPPET = "set -a; . /home/yyf/project/image_agent/.env; set +a;"
REMOTE_LIVE_ROOT_SNIPPET = "IMAGE_AGENT_ROOT=/home/yyf/project/image_agent"
FRESH_APPROVAL_JSON = "<fresh_reviewed_approval_json>"
EXPIRED_APPROVAL_JSON = "/tmp/image_agent_stale_tasks_83_84_dry_run_20260614T080202Z.json"

EXPECTED_STEP_IDS = [
    "verify_release_overlay_contents",
    "verify_frontend_api_contract_tests",
    "verify_fresh_stale_task_approval",
    "apply_approved_stale_task_resolution",
    "collect_post_apply_clean_dry_run",
    "verify_post_apply_clean_resolution",
    "verify_docker_host_policy_dry_run",
    "verify_rawchat_direct_connectivity",
    "apply_production_readiness_env",
    "restart_api_preflight_only",
    "restart_api_normally",
    "verify_elasticsearch_hybrid_prerequisites",
    "run_strict_remote_smoke_acceptance",
    "verify_strict_remote_smoke_acceptance_json",
    "emit_fast_launch_acceptance_env_after_strict_verify",
    "restart_api_after_fast_launch_acceptance_env",
    "verify_final_fast_launch_readiness",
]

FRONTEND_API_CONTRACT_TESTS = [
    "src/lib/api.test.ts",
    "src/lib/workflows.test.ts",
    "src/routes/AgentPage.test.tsx",
    "src/routes/WorkflowsPage.test.tsx",
    "src/routes/ResultDetailPage.test.tsx",
]

REQUIRED_PRIVACY_AND_SAFETY_INVARIANTS = [
    "do_not_store_or_print_api_keys_or_secrets",
    "do_not_store_raw_patient_data",
    "do_not_store_backend_absolute_paths_in_acceptance_json",
    "do_not_use_IMAGE_AGENT_ALLOW_RESTART_WITH_ACTIVE_TASKS",
    "do_not_count_skipped_missing_model_config_as_passed",
]


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(message)


def load_plan(path: str | Path) -> dict:
    source_path = Path(path)
    payload = json.loads(source_path.read_text(encoding="utf-8"))
    _require(isinstance(payload, dict), "command plan must be a JSON object")
    return payload


def _require_command_contains(command: str, needle: str, *, step_id: str) -> None:
    _require(needle in command, f"{step_id}.command must include {needle}")


def _require_expected_success_contains(expected_success: list[str], needle: str, *, step_id: str) -> None:
    _require(
        needle in expected_success,
        f"{step_id}.expected_success must include {needle}",
    )


def _token_after(command: str, token: str, *, step_id: str) -> str:
    try:
        parts = shlex.split(command)
    except ValueError as exc:
        raise SystemExit(f"{step_id}.command could not be parsed") from exc
    try:
        index = parts.index(token)
    except ValueError as exc:
        raise SystemExit(f"{step_id}.command must include {token}") from exc
    _require(index + 1 < len(parts) and parts[index + 1], f"{step_id}.command must include a value after {token}")
    return parts[index + 1]


def _command_parts(command: str, *, step_id: str) -> list[str]:
    try:
        return shlex.split(command)
    except ValueError as exc:
        raise SystemExit(f"{step_id}.command could not be parsed") from exc


def _require_no_command_placeholders(verified_steps: Sequence[dict]) -> None:
    for step in verified_steps:
        command = step["command"]
        _require(
            PLACEHOLDER_RE.search(command) is None,
            "operator_authorization_required commands must be materialized without placeholders",
        )


def _require_placeholder_or_materialized_value(
    command: str,
    token: str,
    *,
    step_id: str,
    placeholder: str,
    materialized: bool,
    validator: Callable[[str], bool] | None = None,
    message: str | None = None,
) -> str:
    value = _token_after(command, token, step_id=step_id)
    if materialized:
        _require(value != placeholder and PLACEHOLDER_RE.search(value) is None, message or f"{step_id}.command must materialize {token}")
        if validator is not None:
            _require(validator(value), message or f"{step_id}.command has invalid value for {token}")
    else:
        _require(value == placeholder, f"{step_id}.command must include {token} {placeholder}")
    return value


def _command_has_token(command: str, token: str, *, step_id: str) -> bool:
    return token in _command_parts(command, step_id=step_id)


def _is_positive_int_text(value: str) -> bool:
    try:
        return int(value) > 0
    except (TypeError, ValueError):
        return False


def _is_privacy_safe_release_symbol(value: str) -> bool:
    return bool(re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{2,80}", value or ""))


def _require_release_overlay(value: object) -> str:
    _require(
        isinstance(value, str) and value.startswith(f"{REMOTE_RELEASE_ROOT}/"),
        "release_overlay must be under the remote release root",
    )
    release_id = value.removeprefix(f"{REMOTE_RELEASE_ROOT}/")
    _require("/" not in release_id, "release_overlay must not contain nested path segments")
    _require(_is_privacy_safe_release_symbol(release_id), "release_overlay must end with a privacy-safe release id")
    _require(not release_id.endswith(".incoming"), "release_overlay must not point at an incoming overlay")
    return value


def _is_remote_nifti_path(value: str) -> bool:
    normalized = value.replace("\\", "/")
    return normalized.startswith("/") and (normalized.endswith(".nii") or normalized.endswith(".nii.gz"))


def _is_remote_db_path(value: str) -> bool:
    normalized = (value or "").replace("\\", "/")
    return (
        normalized.startswith("/")
        and normalized.endswith(".db")
        and all(part not in {"", ".", ".."} for part in normalized.split("/")[1:])
    )


def _is_workflow_type_symbol(value: str) -> bool:
    return bool(re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{2,80}", value or "")) and not value.endswith("_mock")


def _is_public_https_origin(value: str) -> bool:
    if not re.fullmatch(r"https://[A-Za-z0-9.-]+(?::[0-9]{1,5})?", value or ""):
        return False
    host = value.removeprefix("https://").split(":", 1)[0].lower()
    return _is_public_deployment_host(host)


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


def _is_private_network_origin(value: str) -> bool:
    parsed = urlsplit(value or "")
    return (
        parsed.scheme in {"http", "https"}
        and bool(parsed.hostname)
        and _is_private_network_host(parsed.hostname)
        and not parsed.path
        and not parsed.query
        and not parsed.fragment
    )


def _is_deployment_origin_for_scope(value: str, *, deployment_scope: str) -> bool:
    if deployment_scope == "private_network":
        return _is_private_network_origin(value)
    return _is_public_https_origin(value)


def _is_public_deployment_host(host: str) -> bool:
    normalized = (host or "").strip().lower().rstrip(".")
    if normalized in {"localhost", "127.0.0.1", "0.0.0.0", "::1"}:
        return False
    try:
        return ipaddress.ip_address(normalized).is_global
    except ValueError:
        return "." in normalized and not normalized.endswith(".local")


def _parse_utc_timestamp(value: object, *, key: str) -> datetime:
    _require(isinstance(value, str) and value, f"{key} must be an ISO-8601 timestamp")
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise SystemExit(f"{key} must be an ISO-8601 timestamp") from exc
    _require(parsed.tzinfo is not None and parsed.utcoffset() is not None, f"{key} must be timezone-aware")
    return parsed.astimezone(timezone.utc)


def _resolve_now_utc(value: str | datetime | None) -> datetime:
    if isinstance(value, datetime):
        _require(value.tzinfo is not None and value.utcoffset() is not None, "now_utc must be timezone-aware")
        return value.astimezone(timezone.utc)
    if isinstance(value, str):
        return _parse_utc_timestamp(value, key="now_utc")
    return datetime.now(timezone.utc)


def _verify_step_shape(step: object, *, expected_id: str, index: int) -> dict:
    _require(isinstance(step, dict), f"steps[{index}] must be an object")
    _require(step.get("id") == expected_id, f"steps[{index}].id must be {expected_id}")
    command = step.get("command")
    _require(isinstance(command, str) and command.strip(), f"{expected_id}.command must be non-empty")
    _require("\n" not in command, f"{expected_id}.command must be single-line")
    _require("OPENAI_API_KEY" not in command, f"{expected_id}.command must not mention OPENAI_API_KEY")
    _require(
        API_KEY_SHAPED_RE.search(command) is None,
        f"{expected_id}.command must not contain API-key shaped strings",
    )
    _require(
        "IMAGE_AGENT_ALLOW_RESTART_WITH_ACTIVE_TASKS=1" not in command,
        f"{expected_id}.command must not use active-task restart override",
    )
    _require(isinstance(step.get("mutates_remote_state"), bool), f"{expected_id}.mutates_remote_state must be boolean")
    _require(
        isinstance(step.get("requires_operator_authorization"), bool),
        f"{expected_id}.requires_operator_authorization must be boolean",
    )
    expected_success = step.get("expected_success")
    _require(isinstance(expected_success, list) and expected_success, f"{expected_id}.expected_success must be non-empty")
    _require(all(isinstance(item, str) and item for item in expected_success), f"{expected_id}.expected_success entries must be strings")
    return step


def _verify_approval_refresh(plan: dict) -> dict:
    refresh = plan.get("stale_task_approval_refresh")
    _require(isinstance(refresh, dict), "stale_task_approval_refresh must be present")
    if plan.get("status") == "operator_authorization_required":
        approval_state = plan.get("approval_json_state")
        _require(isinstance(approval_state, dict), "approval_json_state must describe the approval JSON state")
        expected_keys = {
            "status",
            "source_approval_json",
            "approval_expires_at_utc",
            "next_required_step",
            "mutates_remote_state",
            "requires_operator_authorization",
        }
        _require(
            set(refresh) == expected_keys,
            "stale_task_approval_refresh must be superseded by fresh reviewed approval",
        )
        _require(
            refresh.get("status") == "superseded_by_fresh_reviewed_approval",
            "stale_task_approval_refresh must be superseded by fresh reviewed approval",
        )
        _require(
            refresh.get("source_approval_json") == plan.get("approval_json"),
            "stale_task_approval_refresh.source_approval_json must match approval_json",
        )
        _require(
            refresh.get("approval_expires_at_utc") == approval_state.get("approval_expires_at_utc"),
            "stale_task_approval_refresh.approval_expires_at_utc must match approval_json_state",
        )
        _require(
            refresh.get("next_required_step") == "apply_approved_stale_task_resolution",
            "stale_task_approval_refresh.next_required_step mismatch",
        )
        _require(
            refresh.get("mutates_remote_state") is False,
            "stale_task_approval_refresh must be read-only",
        )
        _require(
            refresh.get("requires_operator_authorization") is False,
            "stale_task_approval_refresh superseded marker must not require operator authorization",
        )
        serialized_refresh = json.dumps(refresh, sort_keys=True)
        _require(
            PLACEHOLDER_RE.search(serialized_refresh) is None,
            "stale_task_approval_refresh must not contain placeholders after materialization",
        )
        _require(
            API_KEY_SHAPED_RE.search(serialized_refresh) is None and "OPENAI_API_KEY" not in serialized_refresh,
            "stale_task_approval_refresh must not expose secrets",
        )
        _require(
            "IMAGE_AGENT_ALLOW_RESTART_WITH_ACTIVE_TASKS=1" not in serialized_refresh,
            "stale_task_approval_refresh must not use active-task restart override",
        )
        return refresh

    _require(
        refresh.get("required_when") == "approval_json_missing_or_older_than_24h",
        "stale_task_approval_refresh.required_when mismatch",
    )
    _require(
        refresh.get("must_be_operator_reviewed_before_apply") is True,
        "stale_task_approval_refresh must require operator review before apply",
    )
    _require(
        refresh.get("mutates_remote_state") is False,
        "stale_task_approval_refresh must be read-only",
    )
    _require(
        refresh.get("output_json_pattern") == "/tmp/image_agent_stale_tasks_83_84_dry_run_<timestamp>.json",
        "stale_task_approval_refresh.output_json_pattern mismatch",
    )
    command = refresh.get("command")
    _require(isinstance(command, str) and command.strip(), "stale_task_approval_refresh.command must be non-empty")
    _require("\n" not in command, "stale_task_approval_refresh.command must be single-line")
    _require("--apply" not in command, "stale_task_approval_refresh.command must not apply")
    _require(
        "IMAGE_AGENT_ALLOW_RESTART_WITH_ACTIVE_TASKS=1" not in command,
        "stale_task_approval_refresh.command must not use active-task restart override",
    )
    _require(
        API_KEY_SHAPED_RE.search(command) is None and "OPENAI_API_KEY" not in command,
        "stale_task_approval_refresh.command must not expose secrets",
    )
    for required in (
        REMOTE_ENV_LOAD_SNIPPET,
        REMOTE_LIVE_ROOT_SNIPPET,
        "reconcile_stale_tasks.py --max-age-hours 24 --check-containers",
        "--task-id 83 --task-id 84",
        "> /tmp/image_agent_stale_tasks_83_84_dry_run_<timestamp>.json",
    ):
        _require(required in command, f"stale_task_approval_refresh.command must include {required}")
    _require(
        refresh.get("next_steps_after_refresh")
        == [
            "operator reviews refreshed dry-run JSON and approval_fingerprint",
            "run build_release_gate_command_plan.py to materialize an operator_authorization_required plan",
            "verify the materialized plan with verify_release_gate_command_plan.py before apply",
        ],
        "stale_task_approval_refresh.next_steps_after_refresh mismatch",
    )
    materialize_command = refresh.get("materialize_plan_command")
    _require(
        isinstance(materialize_command, str) and materialize_command.strip(),
        "stale_task_approval_refresh.materialize_plan_command must be non-empty",
    )
    _require("\n" not in materialize_command, "stale_task_approval_refresh.materialize_plan_command must be single-line")
    _require(
        API_KEY_SHAPED_RE.search(materialize_command) is None and "OPENAI_API_KEY" not in materialize_command,
        "stale_task_approval_refresh.materialize_plan_command must not expose secrets",
    )
    _require(
        "IMAGE_AGENT_ALLOW_RESTART_WITH_ACTIVE_TASKS=1" not in materialize_command,
        "stale_task_approval_refresh.materialize_plan_command must not use active-task restart override",
    )
    for required in (
        "apps/api/scripts/build_release_gate_command_plan.py docs/deployment/remote-release-gate-command-plan.json",
        "/tmp/image_agent_stale_tasks_83_84_dry_run_<timestamp>.json",
        "--task-id 83 --task-id 84",
        "--max-age-hours 24",
        "--deployment-scope public_internet",
        "--production-cors-origins <https_console_origin>",
        "--production-public-base-url <https_api_origin>",
        "--output-json /tmp/image_agent_remote_release_gate_plan_<timestamp>.json",
    ):
        _require(required in materialize_command, f"stale_task_approval_refresh.materialize_plan_command must include {required}")
    _require(
        refresh.get("production_origin_materialization")
        == {
            "required_arguments": [
                "--deployment-scope public_internet",
                "--production-cors-origins <https_console_origin>",
                "--production-public-base-url <https_api_origin>",
            ],
            "boundary": (
                "Use public_internet for real public HTTPS origins without path, query, or fragment, or replace "
                "with private_network plus explicit loopback/private HTTP(S) origins for private usable deployment; "
                "do not use placeholders, 0.0.0.0, bare host names, wildcard CORS values, paths, query, or fragments."
            ),
        },
        "stale_task_approval_refresh.production_origin_materialization mismatch",
    )
    return refresh


def _verify_approval_json_state(plan: dict, *, now_utc: str | datetime | None) -> dict:
    status = plan.get("status")
    approval_json = plan.get("approval_json")
    approval_json_state = plan.get("approval_json_state")
    _require(isinstance(approval_json_state, dict), "approval_json_state must describe the approval JSON state")

    if status == "approval_refresh_required":
        _require(
            approval_json == FRESH_APPROVAL_JSON,
            "approval_json must be a fresh reviewed approval placeholder when refresh is required",
        )
        _require(
            approval_json_state.get("status") == "refresh_required",
            "approval_json_state.status must be refresh_required",
        )
        _require(
            approval_json_state.get("previous_approval_json") == EXPIRED_APPROVAL_JSON,
            "approval_json_state.previous_approval_json must preserve the expired evidence path",
        )
        _require(
            approval_json_state.get("next_required_step") == "stale_task_approval_refresh",
            "approval_json_state.next_required_step must point at stale_task_approval_refresh",
        )
        _require(
            isinstance(approval_json_state.get("reason"), str) and approval_json_state["reason"],
            "approval_json_state.reason must be non-empty",
        )
        return {
            "approval_json": FRESH_APPROVAL_JSON,
            "approval_json_status": "refresh_required",
            "approval_expires_at_utc": None,
        }

    if status == "operator_authorization_required":
        _require(
            isinstance(approval_json, str)
            and approval_json
            and approval_json != FRESH_APPROVAL_JSON
            and approval_json != EXPIRED_APPROVAL_JSON
            and "<" not in approval_json
            and ">" not in approval_json,
            "approval_json must be a fresh reviewed approval JSON path before operator authorization",
        )
        _require(
            approval_json_state.get("status") == "fresh_reviewed",
            "approval_json_state.status must be fresh_reviewed",
        )
        _require(
            approval_json_state.get("previous_approval_json") == EXPIRED_APPROVAL_JSON,
            "approval_json_state.previous_approval_json must preserve the expired evidence path",
        )
        _require(
            approval_json_state.get("next_required_step") == "apply_approved_stale_task_resolution",
            "approval_json_state.next_required_step must point at apply_approved_stale_task_resolution",
        )
        generated_at = _parse_utc_timestamp(
            approval_json_state.get("verified_approval_generated_at_utc"),
            key="approval_json_state.verified_approval_generated_at_utc",
        )
        expires_at = _parse_utc_timestamp(
            approval_json_state.get("approval_expires_at_utc"),
            key="approval_json_state.approval_expires_at_utc",
        )
        now = _resolve_now_utc(now_utc)
        _require(generated_at <= now, "approval_json_state.verified_approval_generated_at_utc must not be in the future")
        _require(expires_at > now, "approval_json_state.approval_expires_at_utc is older than now_utc")
        return {
            "approval_json": approval_json,
            "approval_json_status": "fresh_reviewed",
            "approval_expires_at_utc": expires_at.isoformat(),
        }

    raise SystemExit("status must be approval_refresh_required or operator_authorization_required")


def verify_plan(plan: dict, *, now_utc: str | datetime | None = None) -> dict:
    _require(plan.get("plan_id") == PLAN_ID, f"plan_id must be {PLAN_ID}")
    _require(plan.get("schema_version") == 1, "schema_version must be 1")
    _require(plan.get("remote_host") == "yyf@10.2.32.14", "remote_host must identify the accepted remote server")
    _require(plan.get("remote_project_root") == "/home/yyf/project/image_agent", "remote_project_root mismatch")
    release_overlay = _require_release_overlay(plan.get("release_overlay"))
    approval_state = _verify_approval_json_state(plan, now_utc=now_utc)
    approval_json = approval_state["approval_json"]
    _require(plan.get("target_task_ids") == [83, 84], "target_task_ids must be [83, 84]")
    _require(plan.get("freshness_hours") == 24, "freshness_hours must be 24")
    _require(
        plan.get("approval_request_requirements")
        == {
            "must_include_fields": [
                "approval_fingerprint",
                "approval_expires_at_utc",
            ],
            "approval_expires_at_utc_source": "verified_approval.checked.generated_at_utc + freshness_hours",
        },
        "approval_request_requirements mismatch",
    )
    _require(
        plan.get("privacy_and_safety_invariants") == REQUIRED_PRIVACY_AND_SAFETY_INVARIANTS,
        "privacy_and_safety_invariants mismatch",
    )
    _require(
        plan.get("frontend_gate")
        == {
            "status_until_all_steps_pass": "blocked",
            "required_final_evidence": "fresh_strict_remote_smoke_acceptance_verified_within_24h",
        },
        "frontend_gate mismatch",
    )
    refresh = _verify_approval_refresh(plan)

    steps = plan.get("steps")
    _require(isinstance(steps, list), "steps must be a list")
    _require(len(steps) == len(EXPECTED_STEP_IDS), "steps must contain the expected release gate sequence")
    verified_steps = [
        _verify_step_shape(step, expected_id=expected_id, index=index)
        for index, (step, expected_id) in enumerate(zip(steps, EXPECTED_STEP_IDS, strict=True))
    ]
    commands_by_step = {step["id"]: step["command"] for step in verified_steps}
    materialized_operator_plan = plan.get("status") == "operator_authorization_required"
    if materialized_operator_plan:
        _require_no_command_placeholders(verified_steps)

    _require_command_contains(
        commands_by_step["verify_release_overlay_contents"],
        f"cd {release_overlay}",
        step_id="verify_release_overlay_contents",
    )
    for required_file in (
        "apps/api/app/scripts/probe_runtime_environment.py",
        "apps/api/scripts/build_stale_task_apply_request.py",
        "apps/api/scripts/verify_stale_task_apply_request.py",
        "apps/api/scripts/build_elasticsearch_hybrid_config_plan.py",
        "apps/api/scripts/verify_elasticsearch_hybrid_config_plan.py",
        "apps/api/scripts/setup_elasticsearch_hybrid_rag.py",
        "apps/api/scripts/setup_local_embedding_service.py",
        "apps/api/scripts/verify_elasticsearch_hybrid_prerequisites.py",
        "apps/api/scripts/smoke_remote_agent.py",
        "apps/api/scripts/verify_remote_smoke_acceptance.py",
        "apps/api/scripts/verify_release_gate_command_plan.py",
        "scripts/configure_docker_access.py",
        "scripts/check_repository_hygiene.py",
        "scripts/run_frontend_contract_tests.py",
        "scripts/verify_rawchat_direct_connectivity.py",
        "docs/deployment/remote-elasticsearch-hybrid-config-plan.json",
        "docs/rag/contracts/elasticsearch-hybrid-search.md",
        "apps/console/package.json",
        "apps/console/package-lock.json",
        *[f"apps/console/{test_path}" for test_path in FRONTEND_API_CONTRACT_TESTS],
        "tools/restart_remote_image_agent_api.sh",
    ):
        _require_command_contains(
            commands_by_step["verify_release_overlay_contents"],
            f"test -f {required_file}",
            step_id="verify_release_overlay_contents",
        )
    _require_command_contains(
        commands_by_step["verify_release_overlay_contents"],
        "apps/api/scripts/verify_elasticsearch_hybrid_config_plan.py docs/deployment/remote-elasticsearch-hybrid-config-plan.json",
        step_id="verify_release_overlay_contents",
    )
    overlay_expected_success = verified_steps[0]["expected_success"]
    for required_success in (
        "release_overlay_current=true",
        "required_gate_scripts_present=true",
        "elasticsearch_hybrid_contract_present=true",
        "repository_hygiene_status=passed",
        "elasticsearch_hybrid_config_plan_status=passed",
    ):
        _require_expected_success_contains(
            overlay_expected_success,
            required_success,
            step_id="verify_release_overlay_contents",
        )
    _require_command_contains(
        commands_by_step["verify_release_overlay_contents"],
        "scripts/check_repository_hygiene.py --paths README.md scripts apps/api/scripts docs/deployment docs/rag docs/skills",
        step_id="verify_release_overlay_contents",
    )

    frontend_command = commands_by_step["verify_frontend_api_contract_tests"]
    _require_command_contains(
        frontend_command,
        f"cd {release_overlay}",
        step_id="verify_frontend_api_contract_tests",
    )
    _require_command_contains(
        frontend_command,
        "scripts/run_frontend_contract_tests.py",
        step_id="verify_frontend_api_contract_tests",
    )
    _require_command_contains(
        frontend_command,
        "--console-dir apps/console",
        step_id="verify_frontend_api_contract_tests",
    )
    _require_command_contains(
        frontend_command,
        "--install",
        step_id="verify_frontend_api_contract_tests",
    )
    for required_frontend_flag in (
        "--registry https://registry.npmjs.org/",
        "--fetch-timeout-ms 20000",
        "--fetch-retries 0",
        "--timeout-seconds 120",
        "--cache-dir /tmp/image_agent_console_npm_cache_",
        "--offline",
    ):
        _require_command_contains(
            frontend_command,
            required_frontend_flag,
            step_id="verify_frontend_api_contract_tests",
        )
    for test_path in FRONTEND_API_CONTRACT_TESTS:
        _require_command_contains(
            frontend_command,
            test_path,
            step_id="verify_frontend_api_contract_tests",
        )
    frontend_expected_success = next(
        step["expected_success"] for step in verified_steps if step["id"] == "verify_frontend_api_contract_tests"
    )
    _require_expected_success_contains(
        frontend_expected_success,
        "frontend_api_contract_tests=passed",
        step_id="verify_frontend_api_contract_tests",
    )

    _require_command_contains(
        commands_by_step["verify_fresh_stale_task_approval"],
        f"verify_stale_task_approval.py {approval_json} --task-id 83 --task-id 84 --max-age-hours 24",
        step_id="verify_fresh_stale_task_approval",
    )
    _require_command_contains(
        commands_by_step["apply_approved_stale_task_resolution"],
        f"reconcile_stale_tasks.py --apply --max-age-hours 24 --task-id 83 --task-id 84 --approval-json {approval_json}",
        step_id="apply_approved_stale_task_resolution",
    )
    _require_command_contains(
        commands_by_step["apply_approved_stale_task_resolution"],
        REMOTE_ENV_LOAD_SNIPPET,
        step_id="apply_approved_stale_task_resolution",
    )
    _require_command_contains(
        commands_by_step["apply_approved_stale_task_resolution"],
        REMOTE_LIVE_ROOT_SNIPPET,
        step_id="apply_approved_stale_task_resolution",
    )
    _require_command_contains(
        commands_by_step["collect_post_apply_clean_dry_run"],
        "reconcile_stale_tasks.py --max-age-hours 24 --check-containers --task-id 83 --task-id 84",
        step_id="collect_post_apply_clean_dry_run",
    )
    _require_command_contains(
        commands_by_step["collect_post_apply_clean_dry_run"],
        REMOTE_ENV_LOAD_SNIPPET,
        step_id="collect_post_apply_clean_dry_run",
    )
    _require_command_contains(
        commands_by_step["collect_post_apply_clean_dry_run"],
        REMOTE_LIVE_ROOT_SNIPPET,
        step_id="collect_post_apply_clean_dry_run",
    )
    _require_command_contains(
        commands_by_step["verify_post_apply_clean_resolution"],
        "verify_stale_task_resolution.py",
        step_id="verify_post_apply_clean_resolution",
    )
    for required_flag in (
        "--apply-json",
        "--resolution-json",
        "--task-id 83 --task-id 84",
        "--require-empty-active",
        "--max-age-hours 24",
    ):
        _require_command_contains(
            commands_by_step["verify_post_apply_clean_resolution"],
            required_flag,
            step_id="verify_post_apply_clean_resolution",
        )
    for json_flag in ("--apply-json", "--resolution-json"):
        json_path = _token_after(
            commands_by_step["verify_post_apply_clean_resolution"],
            json_flag,
            step_id="verify_post_apply_clean_resolution",
        )
        _require(
            (not materialized_operator_plan) or PLACEHOLDER_RE.search(json_path) is None,
            "operator_authorization_required commands must be materialized without placeholders",
        )
        _require(json_path.startswith("/tmp/image_agent_stale_tasks_83_84_"), f"verify_post_apply_clean_resolution.command {json_flag} must use the expected /tmp evidence path")
    _require_command_contains(
        commands_by_step["verify_post_apply_clean_resolution"],
        "--task-id 83 --task-id 84",
        step_id="verify_post_apply_clean_resolution",
    )
    docker_policy_command = commands_by_step["verify_docker_host_policy_dry_run"]
    for required in (
        "scripts/configure_docker_access.py",
        "--user yyf",
        "--docker-bin /usr/bin/docker",
        "--output-json /tmp/image_agent_docker_access_policy_dry_run_",
        "plan_id=image_agent_docker_access_policy_v1",
        "mode=dry_run",
        "sudoers_file=/etc/sudoers.d/image-agent-docker",
        "verification_command=sudo -n docker version",
    ):
        _require_command_contains(
            docker_policy_command,
            required,
            step_id="verify_docker_host_policy_dry_run",
        )
    _require(
        "--apply" not in _command_parts(docker_policy_command, step_id="verify_docker_host_policy_dry_run"),
        "verify_docker_host_policy_dry_run.command must not include --apply",
    )
    docker_policy_expected_success = next(
        step["expected_success"] for step in verified_steps if step["id"] == "verify_docker_host_policy_dry_run"
    )
    for required_success in (
        "plan_id=image_agent_docker_access_policy_v1",
        "mode=dry_run",
        "sudoers_file=/etc/sudoers.d/image-agent-docker",
        "verification_command=sudo -n docker version",
    ):
        _require_expected_success_contains(
            docker_policy_expected_success,
            required_success,
            step_id="verify_docker_host_policy_dry_run",
        )
    rawchat_direct_command = commands_by_step["verify_rawchat_direct_connectivity"]
    for required in (
        "scripts/verify_rawchat_direct_connectivity.py",
        "--url https://rawchat.cn/codex",
        "--output-json /tmp/image_agent_rawchat_direct_connectivity_",
    ):
        _require_command_contains(
            rawchat_direct_command,
            required,
            step_id="verify_rawchat_direct_connectivity",
        )
    rawchat_direct_expected_success = next(
        step["expected_success"] for step in verified_steps if step["id"] == "verify_rawchat_direct_connectivity"
    )
    for required_success in (
        "rawchat_direct_connectivity_status=passed",
        "rawchat_direct_proxy_env_trusted=false",
        "rawchat_direct_transport=direct",
    ):
        _require_expected_success_contains(
            rawchat_direct_expected_success,
            required_success,
            step_id="verify_rawchat_direct_connectivity",
        )
    production_env_command = commands_by_step["apply_production_readiness_env"]
    for required in (
        "scripts/bootstrap_image_agent.py",
        "--repo-root",
        "--image-agent-root /home/yyf/project/image_agent",
        "--env-file /home/yyf/project/image_agent/.env",
        "--production",
        "--deployment-scope",
        "--model-provider rawchat",
        "--model-name gpt-5.5",
        "--model-review-name gpt-5.5",
        "--model-base-url https://rawchat.cn/codex",
        "--model-wire-api responses",
        "--verify-docker-command",
        "--skip-elasticsearch-hybrid",
        "--skip-workflow-images",
        "--config-only",
        "--apply",
    ):
        _require_command_contains(
            production_env_command,
            required,
            step_id="apply_production_readiness_env",
        )
    deployment_scope = _token_after(
        production_env_command,
        "--deployment-scope",
        step_id="apply_production_readiness_env",
    )
    _require(
        deployment_scope in {"public_internet", "private_network"},
        "apply_production_readiness_env.command must include --deployment-scope public_internet or private_network",
    )
    console_origin_message = (
        "apply_production_readiness_env.command must include a concrete private-network console origin"
        if deployment_scope == "private_network"
        else "apply_production_readiness_env.command must include a concrete public HTTPS console origin"
    )
    api_origin_message = (
        "apply_production_readiness_env.command must include a concrete private-network API origin"
        if deployment_scope == "private_network"
        else "apply_production_readiness_env.command must include a concrete public HTTPS API origin"
    )
    cors_origin = _require_placeholder_or_materialized_value(
        production_env_command,
        "--production-cors-origins",
        step_id="apply_production_readiness_env",
        placeholder="https://<console-hostname>",
        materialized=materialized_operator_plan,
        validator=lambda value: _is_deployment_origin_for_scope(value, deployment_scope=deployment_scope),
        message=console_origin_message,
    )
    public_api_origin = _require_placeholder_or_materialized_value(
        production_env_command,
        "--production-public-base-url",
        step_id="apply_production_readiness_env",
        placeholder="https://<api-hostname>",
        materialized=materialized_operator_plan,
        validator=lambda value: _is_deployment_origin_for_scope(value, deployment_scope=deployment_scope),
        message=api_origin_message,
    )
    docker_command = _token_after(
        production_env_command,
        "--docker-command",
        step_id="apply_production_readiness_env",
    )
    _require(
        docker_command in {"docker", "sudo -n docker"},
        "apply_production_readiness_env.command must include --docker-command docker or --docker-command 'sudo -n docker'",
    )
    production_expected_success = next(
        step["expected_success"] for step in verified_steps if step["id"] == "apply_production_readiness_env"
    )
    for required_success in (
        "IMAGE_AGENT_ENV=production",
        f"IMAGE_AGENT_DEPLOYMENT_SCOPE={deployment_scope}",
        f"IMAGE_AGENT_CORS_ORIGINS={cors_origin}",
        f"IMAGE_AGENT_PUBLIC_BASE_URL={public_api_origin}",
        "IMAGE_AGENT_MODEL_PROVIDER=rawchat",
        "IMAGE_AGENT_MODEL_NAME=gpt-5.5",
        "IMAGE_AGENT_MODEL_REVIEW_NAME=gpt-5.5",
        "IMAGE_AGENT_MODEL_BASE_URL=https://rawchat.cn/codex",
        "IMAGE_AGENT_MODEL_WIRE_API=responses",
        "IMAGE_AGENT_MODEL_TRUST_ENV_PROXY=0",
        f"IMAGE_AGENT_DOCKER_COMMAND={docker_command}",
        "verify_docker_command completed",
    ):
        _require_expected_success_contains(
            production_expected_success,
            required_success,
            step_id="apply_production_readiness_env",
        )
    _require_command_contains(
        commands_by_step["restart_api_preflight_only"],
        "IMAGE_AGENT_RESTART_PREFLIGHT_ONLY=1",
        step_id="restart_api_preflight_only",
    )
    _require_command_contains(
        commands_by_step["restart_api_preflight_only"],
        "bash tools/restart_remote_image_agent_api.sh",
        step_id="restart_api_preflight_only",
    )
    _require_command_contains(
        commands_by_step["restart_api_normally"],
        "bash tools/restart_remote_image_agent_api.sh",
        step_id="restart_api_normally",
    )
    _require(
        "IMAGE_AGENT_RESTART_PREFLIGHT_ONLY=1" not in commands_by_step["restart_api_normally"],
        "restart_api_normally must not run in preflight-only mode",
    )
    _require_command_contains(
        commands_by_step["verify_elasticsearch_hybrid_prerequisites"],
        "verify_elasticsearch_hybrid_prerequisites.py",
        step_id="verify_elasticsearch_hybrid_prerequisites",
    )
    for required_flag in (
        "--env-file /home/yyf/project/image_agent/.env",
        "--rag-status-url http://127.0.0.1:8000/agent/rag/status",
    ):
        _require_command_contains(
            commands_by_step["verify_elasticsearch_hybrid_prerequisites"],
            required_flag,
            step_id="verify_elasticsearch_hybrid_prerequisites",
        )
    es_prereq_command = commands_by_step["verify_elasticsearch_hybrid_prerequisites"]
    _require(
        "set -a; . /home/yyf/project/image_agent/.env; set +a;" in es_prereq_command
        and "IMAGE_AGENT_ROOT=/home/yyf/project/image_agent" in es_prereq_command
        and "IMAGE_AGENT_ENV_FILE=/home/yyf/project/image_agent/.env" in es_prereq_command,
        "ES prerequisite runtime probe must load deployment env",
    )
    runtime_probe_json = _token_after(
        es_prereq_command,
        "--runtime-probe-json",
        step_id="verify_elasticsearch_hybrid_prerequisites",
    )
    _require(
        runtime_probe_json.startswith("/tmp/image_agent_runtime_probe_") and runtime_probe_json.endswith(".json"),
        "verify_elasticsearch_hybrid_prerequisites.command --runtime-probe-json must use the expected /tmp runtime probe path",
    )
    _require(
        (not materialized_operator_plan) or PLACEHOLDER_RE.search(runtime_probe_json) is None,
        "operator_authorization_required runtime probe JSON path must be materialized without placeholders",
    )
    _require_command_contains(
        es_prereq_command,
        f"-m app.scripts.probe_runtime_environment --json > {runtime_probe_json}",
        step_id="verify_elasticsearch_hybrid_prerequisites",
    )
    es_prereq_expected_success = next(
        step["expected_success"] for step in verified_steps if step["id"] == "verify_elasticsearch_hybrid_prerequisites"
    )
    for required_success in (
        "status=passed",
        "elasticsearch_url_configured=true",
        "rag_embedding_provider_configured=true",
        "rag_embedding_provider_production_configured=true",
        "rag_embedding_model_configured=true",
        "rag_embedding_endpoint_configured=true",
        "secrets_redacted=true",
        "rag_status_engine=elasticsearch_hybrid",
        "rag_status_hybrid_engine=elasticsearch",
        "rag_status_hybrid_configured=true",
        "rag_status_hybrid_mode=connected",
        "rag_status_hybrid_persisted=true",
        "rag_status_hybrid_index privacy-safe",
        "rag_status_hybrid_index_matches_env=true",
        "rag_status_hybrid_indexed_chunk_count>0",
        "rag_status_hybrid_lexical_retriever=standard",
        "rag_status_hybrid_vector_retriever=knn",
        "rag_status_hybrid_dense_vector_field=embedding",
        "rag_status_hybrid_dense_vector_dims>0",
        "rag_status_hybrid_fusion=rrf",
        "rag_status_hybrid_official_rrf_source_present=true",
        "rag_status_hybrid_error_absent=true",
        "rag_status_hybrid_embedding_error_absent=true",
        "rag_status_hybrid_embedding_provider production configured",
        "rag_status_hybrid_embedding_provider_matches_env=true",
        "rag_status_hybrid_embedding_model present",
        "rag_status_hybrid_embedding_model_matches_env=true",
        "rag_status_hybrid_embedding_transport production-safe",
        "rag_status_hybrid_embedding_endpoint_configured=true",
        "rag_status_hybrid_embedding_production_ready=true",
        "runtime_probe_machine_binding=runtime_discovered",
        "runtime_probe_workflow_tool_execution=deployment_server_local",
        "runtime_probe_docker_runtime_host=api_server",
        "runtime_probe_docker_accessible=true",
        "runtime_probe_docker_requires_sudo=false",
        "runtime_probe_elasticsearch_discovery_status=available",
        "runtime_probe_elasticsearch_container_running=true",
        "runtime_probe_elasticsearch_candidate_endpoint loopback",
    ):
        _require_expected_success_contains(
            es_prereq_expected_success,
            required_success,
            step_id="verify_elasticsearch_hybrid_prerequisites",
        )
    static_strict_smoke_flags = (
        "--require-model",
        "--expected-model-wire-api responses",
        "--expected-model-provider-profile rawchat",
        "--require-model-tool-loop",
        "--require-project-agent-context",
        "--require-agent-workflow-confirmation",
        "--require-agent-workflow-resume",
        "--require-agent-workflow-fingerprint-negative",
        "--require-unknown-workflow-incubation",
        "--require-deployment-identity",
        "--require-production-readiness",
        "--require-runtime-toolchain",
        "--min-documents 60",
        "--min-chunks 200",
        "--require-raw-source-policy",
        "--require-vendor-pointer-integrity",
        "--require-elasticsearch-hybrid-rag",
        "--require-real-evidence-ids",
        "--require-completed-upload",
        "--require-uploaded-series",
        "--require-completed-task",
        "--require-task-events",
        "--require-observe-repair",
        "--require-launched-task",
        "--wait-task-completion-timeout-seconds 21600",
        "--wait-task-completion-poll-seconds 30",
        "--require-launchability-matrix",
        "--require-container-native-qc",
        "--min-native-qc-images 1",
        "--require-scientific-report-artifacts",
        "--min-scientific-report-images 1",
        "--output-json",
    )
    for required_flag in static_strict_smoke_flags:
        _require_command_contains(
            commands_by_step["run_strict_remote_smoke_acceptance"],
            required_flag,
            step_id="run_strict_remote_smoke_acceptance",
        )
    _require_placeholder_or_materialized_value(
        commands_by_step["run_strict_remote_smoke_acceptance"],
        "--deployment-id",
        step_id="run_strict_remote_smoke_acceptance",
        placeholder="<accepted_release_or_commit>",
        materialized=materialized_operator_plan,
        validator=_is_privacy_safe_release_symbol,
        message="run_strict_remote_smoke_acceptance.command must include a concrete privacy-safe deployment id",
    )
    _require_placeholder_or_materialized_value(
        commands_by_step["run_strict_remote_smoke_acceptance"],
        "--expected-health-version",
        step_id="run_strict_remote_smoke_acceptance",
        placeholder="<expected_health_version>",
        materialized=materialized_operator_plan,
        validator=_is_privacy_safe_release_symbol,
        message="run_strict_remote_smoke_acceptance.command must include a concrete privacy-safe expected health version",
    )
    strict_smoke_command = commands_by_step["run_strict_remote_smoke_acceptance"]
    if materialized_operator_plan and _command_has_token(
        strict_smoke_command,
        "--uploaded-series-id",
        step_id="run_strict_remote_smoke_acceptance",
    ):
        uploaded_series_id = _token_after(
            strict_smoke_command,
            "--uploaded-series-id",
            step_id="run_strict_remote_smoke_acceptance",
        )
        _require(
            _is_positive_int_text(uploaded_series_id),
            "run_strict_remote_smoke_acceptance.command must include a positive uploaded series id",
        )
        _require(
            "--upload-nifti-file" not in _command_parts(strict_smoke_command, step_id="run_strict_remote_smoke_acceptance"),
            "run_strict_remote_smoke_acceptance.command must choose either --uploaded-series-id or --upload-nifti-file",
        )
    else:
        uploaded_series_id = None
        _require_placeholder_or_materialized_value(
            strict_smoke_command,
            "--upload-nifti-file",
            step_id="run_strict_remote_smoke_acceptance",
            placeholder="<remote_nifti_file>",
            materialized=materialized_operator_plan,
            validator=_is_remote_nifti_path,
            message="run_strict_remote_smoke_acceptance.command must include a concrete remote NIfTI file path",
        )
    if _command_has_token(
        strict_smoke_command,
        "--reuse-persisted-agent-launch-evidence",
        step_id="run_strict_remote_smoke_acceptance",
    ):
        _require(
            materialized_operator_plan,
            "run_strict_remote_smoke_acceptance.command can reuse persisted launch evidence only in materialized plans",
        )
        _require(
            uploaded_series_id is not None,
            "run_strict_remote_smoke_acceptance.command can reuse persisted launch evidence only with --uploaded-series-id",
        )
        acceptance_task_id = _token_after(
            strict_smoke_command,
            "--task-id",
            step_id="run_strict_remote_smoke_acceptance",
        )
        _require(
            _is_positive_int_text(acceptance_task_id),
            "run_strict_remote_smoke_acceptance.command must include a positive acceptance task id",
        )
        launch_series_id = _token_after(
            strict_smoke_command,
            "--launch-series-id",
            step_id="run_strict_remote_smoke_acceptance",
        )
        _require(
            _is_positive_int_text(launch_series_id) and launch_series_id == uploaded_series_id,
            "run_strict_remote_smoke_acceptance.command launch-series-id must match uploaded-series-id",
        )
        agent_state_db = _token_after(
            strict_smoke_command,
            "--agent-state-db",
            step_id="run_strict_remote_smoke_acceptance",
        )
        _require(
            _is_remote_db_path(agent_state_db),
            "run_strict_remote_smoke_acceptance.command must include an absolute remote agent state .db path",
        )
    _require_placeholder_or_materialized_value(
        commands_by_step["run_strict_remote_smoke_acceptance"],
        "--launch-workflow-type",
        step_id="run_strict_remote_smoke_acceptance",
        placeholder="<real_registered_workflow_type>",
        materialized=materialized_operator_plan,
        validator=_is_workflow_type_symbol,
        message="run_strict_remote_smoke_acceptance.command must include a concrete registered workflow type",
    )
    _require_placeholder_or_materialized_value(
        commands_by_step["run_strict_remote_smoke_acceptance"],
        "--project-id",
        step_id="run_strict_remote_smoke_acceptance",
        placeholder="<project_id>",
        materialized=materialized_operator_plan,
        validator=_is_positive_int_text,
        message="run_strict_remote_smoke_acceptance.command must include a positive project id",
    )
    _require_placeholder_or_materialized_value(
        commands_by_step["run_strict_remote_smoke_acceptance"],
        "--upload-session-id",
        step_id="run_strict_remote_smoke_acceptance",
        placeholder="<upload_session_id>",
        materialized=materialized_operator_plan,
        validator=_is_positive_int_text,
        message="run_strict_remote_smoke_acceptance.command must include a positive upload session id",
    )
    _require(
        "--launch-series-id <uploaded_series_id>" not in commands_by_step["run_strict_remote_smoke_acceptance"],
        "run_strict_remote_smoke_acceptance must use the uploaded series returned by --require-uploaded-series",
    )
    _require_command_contains(
        commands_by_step["verify_strict_remote_smoke_acceptance_json"],
        "verify_remote_smoke_acceptance.py",
        step_id="verify_strict_remote_smoke_acceptance_json",
    )
    _require_command_contains(
        commands_by_step["verify_strict_remote_smoke_acceptance_json"],
        "--max-age-hours 24",
        step_id="verify_strict_remote_smoke_acceptance_json",
    )
    strict_smoke_json = _token_after(
        commands_by_step["run_strict_remote_smoke_acceptance"],
        "--output-json",
        step_id="run_strict_remote_smoke_acceptance",
    )
    _require(
        strict_smoke_json in shlex.split(commands_by_step["verify_strict_remote_smoke_acceptance_json"]),
        "strict smoke verifier command must verify the smoke output JSON",
    )
    strict_smoke_expected_success = next(
        step["expected_success"] for step in verified_steps if step["id"] == "run_strict_remote_smoke_acceptance"
    )
    verify_expected_success = next(
        step["expected_success"] for step in verified_steps if step["id"] == "verify_strict_remote_smoke_acceptance_json"
    )
    required_model_direct_expected_success = {
        "model_status.trust_env_proxy=false": "checked.model_trust_env_proxy=false",
        "model_status.deployment.model_gateway_access=direct": "checked.model_gateway_access=direct",
    }
    required_fast_launch_production_expected_success = {
        "fast_launch_readiness.checks.production_deployment.status=passed": (
            "checked.fast_launch_production_deployment_status=passed"
        ),
        "fast_launch_readiness.checks.production_deployment.required=true": (
            "checked.fast_launch_production_deployment_required=true"
        ),
        "fast_launch_readiness.checks.production_deployment.ready=true": (
            "checked.fast_launch_production_deployment_ready=true"
        ),
    }
    required_rag_transport_expected_success = {
        "rag_elasticsearch_hybrid.embedding_transport production-safe": (
            "checked.rag_elasticsearch_hybrid_embedding_transport production-safe"
        ),
        "rag_elasticsearch_hybrid.embedding_endpoint_configured boolean": (
            "checked.rag_elasticsearch_hybrid_embedding_endpoint_configured boolean"
        ),
        "rag_elasticsearch_hybrid.official_rrf_source_present=true": (
            "checked.rag_elasticsearch_hybrid_official_rrf_source_present=true"
        ),
        "rag_rebuild_elasticsearch_hybrid.lexical_retriever matches status": (
            "checked.rag_rebuild_elasticsearch_hybrid_lexical_retriever matches status"
        ),
        "rag_rebuild_elasticsearch_hybrid.vector_retriever matches status": (
            "checked.rag_rebuild_elasticsearch_hybrid_vector_retriever matches status"
        ),
        "rag_rebuild_elasticsearch_hybrid.dense_vector_field matches status": (
            "checked.rag_rebuild_elasticsearch_hybrid_dense_vector_field matches status"
        ),
        "rag_rebuild_elasticsearch_hybrid.fusion matches status": (
            "checked.rag_rebuild_elasticsearch_hybrid_fusion matches status"
        ),
        "rag_rebuild_elasticsearch_hybrid.embedding_transport matches status": (
            "checked.rag_rebuild_elasticsearch_hybrid_embedding_transport matches status"
        ),
        "rag_rebuild_elasticsearch_hybrid.embedding_endpoint_configured matches status": (
            "checked.rag_rebuild_elasticsearch_hybrid_embedding_endpoint_configured matches status"
        ),
    }
    required_rag_query_evidence_expected_success = {
        "rag_elasticsearch_hybrid_query_index matches status": (
            "checked.rag_elasticsearch_hybrid_query_index matches status"
        ),
        "rag_elasticsearch_hybrid_query_lexical_retriever=standard": (
            "checked.rag_elasticsearch_hybrid_query_lexical_retriever=standard"
        ),
        "rag_elasticsearch_hybrid_query_vector_retriever=knn": (
            "checked.rag_elasticsearch_hybrid_query_vector_retriever=knn"
        ),
        "rag_elasticsearch_hybrid_query_dense_vector_field=embedding": (
            "checked.rag_elasticsearch_hybrid_query_dense_vector_field=embedding"
        ),
        "rag_elasticsearch_hybrid_query_fusion=rrf": (
            "checked.rag_elasticsearch_hybrid_query_fusion=rrf"
        ),
        "rag_elasticsearch_hybrid_query_dense_vector_dims matches status": (
            "checked.rag_elasticsearch_hybrid_query_dense_vector_dims matches status"
        ),
        "rag_elasticsearch_hybrid_query_embedding_provider matches status": (
            "checked.rag_elasticsearch_hybrid_query_embedding_provider matches status"
        ),
        "rag_elasticsearch_hybrid_query_embedding_model matches status": (
            "checked.rag_elasticsearch_hybrid_query_embedding_model matches status"
        ),
        "rag_elasticsearch_hybrid_query_embedding_transport matches status": (
            "checked.rag_elasticsearch_hybrid_query_embedding_transport matches status"
        ),
        "rag_elasticsearch_hybrid_query_embedding_endpoint_configured matches status": (
            "checked.rag_elasticsearch_hybrid_query_embedding_endpoint_configured matches status"
        ),
        "rag_elasticsearch_hybrid_query_embedding_endpoint_configured=true": (
            "checked.rag_elasticsearch_hybrid_query_embedding_endpoint_configured=true"
        ),
        "rag_elasticsearch_hybrid_query_embedding_production_ready matches status": (
            "checked.rag_elasticsearch_hybrid_query_embedding_production_ready matches status"
        ),
        "rag_elasticsearch_hybrid_query_embedding_production_ready=true": (
            "checked.rag_elasticsearch_hybrid_query_embedding_production_ready=true"
        ),
    }
    required_agent_resume_launch_expected_success = {
        "launched_task.launch_source=agent_workflow_resume": (
            "checked.launched_task_launch_source=agent_workflow_resume"
        ),
    }
    required_runtime_workflow_alias_expected_success = {
        "agent_workflow_confirmation.workflow_metadata.runtime_workflow_type matches launched_task.runtime_workflow_type": (
            "checked.agent_workflow_confirmation_metadata_runtime_workflow_type matches launched_task_runtime_workflow_type"
        ),
        "agent_workflow_confirmation.workflow_metadata.agent_selectable=true": (
            "checked.agent_workflow_confirmation_metadata_agent_selectable=true"
        ),
        "launched_task.runtime_workflow_type present": (
            "checked.launched_task_runtime_workflow_type present"
        ),
        "agent_workflow_resume.runtime_workflow_type matches launched_task.runtime_workflow_type": (
            "checked.agent_workflow_resume_runtime_workflow_type matches launched_task_runtime_workflow_type"
        ),
        "task_status.runtime_workflow_type matches launched_task.runtime_workflow_type": (
            "checked.task_status_runtime_workflow_type matches launched_task_runtime_workflow_type"
        ),
    }
    required_result_summary_metadata_expected_success = {
        "task_result_summary.workflow_metadata.workflow_type matches task workflow_type": (
            "checked.task_result_summary_metadata_workflow_type matches task workflow_type"
        ),
        "task_result_summary.workflow_metadata.runtime_workflow_type matches task_status.runtime_workflow_type": (
            "checked.task_result_summary_metadata_runtime_workflow_type matches task_status_runtime_workflow_type"
        ),
        "task_result_summary.workflow_metadata.agent_selectable=true": (
            "checked.task_result_summary_metadata_agent_selectable=true"
        ),
        "task_result_summary.workflow_metadata.is_report_only=false": (
            "checked.task_result_summary_metadata_is_report_only=false"
        ),
    }
    required_workflow_eligibility_metadata_expected_success = [
        (
            "project_workflow_eligibility_metadata_status=passed",
            "checked.project_workflow_eligibility_metadata_status=passed",
        ),
        (
            "project_workflow_eligibility_metadata_workflow_types include task workflow_type",
            "checked.project_workflow_eligibility_metadata_workflow_types include task workflow_type",
        ),
        (
            "project_workflow_eligibility_metadata_workflow_types include task workflow_type",
            "checked.project_workflow_eligibility_metadata_task_workflow_type_included=true",
        ),
        (
            "project_workflow_eligibility_metadata_item_count>0",
            "checked.project_workflow_eligibility_metadata_item_count>0",
        ),
        (
            "upload_inventory_workflow_eligibility_metadata_status=passed",
            "checked.upload_inventory_workflow_eligibility_metadata_status=passed",
        ),
        (
            "upload_inventory_workflow_eligibility_metadata_workflow_types include task workflow_type",
            "checked.upload_inventory_workflow_eligibility_metadata_workflow_types include task workflow_type",
        ),
        (
            "upload_inventory_workflow_eligibility_metadata_workflow_types include task workflow_type",
            "checked.upload_inventory_workflow_eligibility_metadata_task_workflow_type_included=true",
        ),
        (
            "upload_inventory_workflow_eligibility_metadata_item_count>0",
            "checked.upload_inventory_workflow_eligibility_metadata_item_count>0",
        ),
    ]
    required_fingerprint_negative_expected_success = {
        "agent_workflow_fingerprint_negative_status=passed": (
            "checked.agent_workflow_fingerprint_negative_status=passed"
        ),
        "agent_workflow_fingerprint_negative.confirmation_gate=fingerprint_mismatch": (
            "checked.agent_workflow_fingerprint_negative_confirmation_gate=fingerprint_mismatch"
        ),
        "agent_workflow_fingerprint_negative.production_task_created=false": (
            "checked.agent_workflow_fingerprint_negative_production_task_created=false"
        ),
        "agent_workflow_fingerprint_negative.task_created=false": (
            "checked.agent_workflow_fingerprint_negative_task_created=false"
        ),
    }
    required_unknown_workflow_incubation_expected_success = {
        "unknown_workflow_incubation_status=passed": "checked.unknown_workflow_incubation_status=passed",
        "unknown_workflow_incubation.action_lane=toolchain_incubation": (
            "checked.unknown_workflow_incubation_action_lane=toolchain_incubation"
        ),
        "unknown_workflow_incubation.task_created=false": (
            "checked.unknown_workflow_incubation_task_created=false"
        ),
        "unknown_workflow_incubation.confirmation_created=false": (
            "checked.unknown_workflow_incubation_confirmation_created=false"
        ),
        "unknown_workflow_incubation.task_creation_allowed=false": (
            "checked.unknown_workflow_incubation_task_creation_allowed=false"
        ),
        "unknown_workflow_incubation.forbidden_actions include confirmation_creation,production_task_creation,pipeline_runner_launch": (
            "checked.unknown_workflow_incubation_forbidden_actions include confirmation_creation,production_task_creation,pipeline_runner_launch"
        ),
        "unknown_workflow_incubation.production_task_created=false": (
            "checked.unknown_workflow_incubation_production_task_created=false"
        ),
        "unknown_workflow_incubation.proposal_production_task_created=false": (
            "checked.unknown_workflow_incubation_proposal_production_task_created=false"
        ),
    }
    required_observe_repair_expected_success = {
        "observe_repair_status=passed": "checked.observe_repair_status=passed",
        "observe_repair.policy=read_only_observe_repair": "checked.observe_repair_policy=read_only_observe_repair",
        "observe_repair.auto_rerun_allowed=false": "checked.observe_repair_auto_rerun_allowed=false",
        "observe_repair.task_creation_allowed=false": "checked.observe_repair_task_creation_allowed=false",
        "observe_repair.forbidden_actions include auto_retry,auto_rerun,task_creation": (
            "checked.observe_repair_forbidden_actions include auto_retry,auto_rerun,task_creation"
        ),
        "observe_repair.production_task_created=false": "checked.observe_repair_production_task_created=false",
        "observe_repair.requires_preflight_before_retry=true": (
            "checked.observe_repair_requires_preflight_before_retry=true"
        ),
        "observe_repair.requires_human_confirmation_before_retry=true": (
            "checked.observe_repair_requires_human_confirmation_before_retry=true"
        ),
    }
    for smoke_item, verifier_item in required_model_direct_expected_success.items():
        _require_expected_success_contains(
            strict_smoke_expected_success,
            smoke_item,
            step_id="run_strict_remote_smoke_acceptance",
        )
        _require_expected_success_contains(
            verify_expected_success,
            verifier_item,
            step_id="verify_strict_remote_smoke_acceptance_json",
        )
    for smoke_item, verifier_item in required_fast_launch_production_expected_success.items():
        _require_expected_success_contains(
            strict_smoke_expected_success,
            smoke_item,
            step_id="run_strict_remote_smoke_acceptance",
        )
        _require_expected_success_contains(
            verify_expected_success,
            verifier_item,
            step_id="verify_strict_remote_smoke_acceptance_json",
        )
    for smoke_item, verifier_item in required_rag_transport_expected_success.items():
        _require_expected_success_contains(
            strict_smoke_expected_success,
            smoke_item,
            step_id="run_strict_remote_smoke_acceptance",
        )
        _require_expected_success_contains(
            verify_expected_success,
            verifier_item,
            step_id="verify_strict_remote_smoke_acceptance_json",
        )
    for smoke_item, verifier_item in required_rag_query_evidence_expected_success.items():
        _require_expected_success_contains(
            strict_smoke_expected_success,
            smoke_item,
            step_id="run_strict_remote_smoke_acceptance",
        )
        _require_expected_success_contains(
            verify_expected_success,
            verifier_item,
            step_id="verify_strict_remote_smoke_acceptance_json",
        )
    for smoke_item, verifier_item in required_agent_resume_launch_expected_success.items():
        _require_expected_success_contains(
            strict_smoke_expected_success,
            smoke_item,
            step_id="run_strict_remote_smoke_acceptance",
        )
        _require_expected_success_contains(
            verify_expected_success,
            verifier_item,
            step_id="verify_strict_remote_smoke_acceptance_json",
        )
    for smoke_item, verifier_item in required_runtime_workflow_alias_expected_success.items():
        _require_expected_success_contains(
            strict_smoke_expected_success,
            smoke_item,
            step_id="run_strict_remote_smoke_acceptance",
        )
        _require_expected_success_contains(
            verify_expected_success,
            verifier_item,
            step_id="verify_strict_remote_smoke_acceptance_json",
        )
    for smoke_item, verifier_item in required_result_summary_metadata_expected_success.items():
        _require_expected_success_contains(
            strict_smoke_expected_success,
            smoke_item,
            step_id="run_strict_remote_smoke_acceptance",
        )
        _require_expected_success_contains(
            verify_expected_success,
            verifier_item,
            step_id="verify_strict_remote_smoke_acceptance_json",
        )
    for smoke_item, verifier_item in required_workflow_eligibility_metadata_expected_success:
        _require_expected_success_contains(
            strict_smoke_expected_success,
            smoke_item,
            step_id="run_strict_remote_smoke_acceptance",
        )
        _require_expected_success_contains(
            verify_expected_success,
            verifier_item,
            step_id="verify_strict_remote_smoke_acceptance_json",
        )
    for smoke_item, verifier_item in required_fingerprint_negative_expected_success.items():
        _require_expected_success_contains(
            strict_smoke_expected_success,
            smoke_item,
            step_id="run_strict_remote_smoke_acceptance",
        )
        _require_expected_success_contains(
            verify_expected_success,
            verifier_item,
            step_id="verify_strict_remote_smoke_acceptance_json",
        )
    for smoke_item, verifier_item in required_unknown_workflow_incubation_expected_success.items():
        _require_expected_success_contains(
            strict_smoke_expected_success,
            smoke_item,
            step_id="run_strict_remote_smoke_acceptance",
        )
        _require_expected_success_contains(
            verify_expected_success,
            verifier_item,
            step_id="verify_strict_remote_smoke_acceptance_json",
        )
    for smoke_item, verifier_item in required_observe_repair_expected_success.items():
        _require_expected_success_contains(
            strict_smoke_expected_success,
            smoke_item,
            step_id="run_strict_remote_smoke_acceptance",
        )
        _require_expected_success_contains(
            verify_expected_success,
            verifier_item,
            step_id="verify_strict_remote_smoke_acceptance_json",
        )
    fast_launch_env_command = commands_by_step["emit_fast_launch_acceptance_env_after_strict_verify"]
    for required in (
        "scripts/bootstrap_image_agent.py",
        "--env-file /home/yyf/project/image_agent/.env",
        "--skip-elasticsearch-hybrid",
        "--skip-workflow-images",
        "--config-only",
        "--strict-acceptance-max-age-hours 24",
        "--apply",
    ):
        _require_command_contains(
            fast_launch_env_command,
            required,
            step_id="emit_fast_launch_acceptance_env_after_strict_verify",
        )
    _require(
        "--emit-fast-launch-env" not in fast_launch_env_command,
        "fast-launch env apply command must use bootstrap instead of printing env lines",
    )
    _require(
        strict_smoke_json in shlex.split(fast_launch_env_command),
        "fast-launch env apply command must verify the smoke output JSON",
    )
    restart_after_fast_launch_command = commands_by_step["restart_api_after_fast_launch_acceptance_env"]
    for required in (
        "IMAGE_AGENT_ENV_FILE=/home/yyf/project/image_agent/.env",
        "bash tools/restart_remote_image_agent_api.sh",
    ):
        _require_command_contains(
            restart_after_fast_launch_command,
            required,
            step_id="restart_api_after_fast_launch_acceptance_env",
        )
    final_fast_launch_command = commands_by_step["verify_final_fast_launch_readiness"]
    _require_command_contains(
        final_fast_launch_command,
        "http://127.0.0.1:8000/deployment",
        step_id="verify_final_fast_launch_readiness",
    )
    final_fast_launch_expected = next(
        step["expected_success"] for step in verified_steps if step["id"] == "verify_final_fast_launch_readiness"
    )
    _require_expected_success_contains(
        final_fast_launch_expected,
        "fast_launch_readiness.status=ready",
        step_id="verify_final_fast_launch_readiness",
    )
    _require_expected_success_contains(
        final_fast_launch_expected,
        "fast_launch_readiness.checks.strict_remote_acceptance.status=passed",
        step_id="verify_final_fast_launch_readiness",
    )
    _require_expected_success_contains(
        final_fast_launch_expected,
        "fast_launch_readiness.checks.production_deployment.status=passed",
        step_id="verify_final_fast_launch_readiness",
    )
    _require_expected_success_contains(
        final_fast_launch_expected,
        "fast_launch_readiness.checks.production_deployment.required=true",
        step_id="verify_final_fast_launch_readiness",
    )
    _require_expected_success_contains(
        final_fast_launch_expected,
        "fast_launch_readiness.checks.production_deployment.ready=true",
        step_id="verify_final_fast_launch_readiness",
    )
    for required in (
        "p.get(\"required\") is True",
        "p.get(\"ready\") is True",
    ):
        _require_command_contains(
            final_fast_launch_command,
            required,
            step_id="verify_final_fast_launch_readiness",
        )

    mutating_steps = [step["id"] for step in verified_steps if step["mutates_remote_state"]]
    operator_steps = [step["id"] for step in verified_steps if step["requires_operator_authorization"]]
    _require(
        operator_steps == [
            "apply_approved_stale_task_resolution",
            "apply_production_readiness_env",
            "restart_api_normally",
            "run_strict_remote_smoke_acceptance",
            "emit_fast_launch_acceptance_env_after_strict_verify",
            "restart_api_after_fast_launch_acceptance_env",
        ],
        "stale-task apply, production readiness env apply, normal restart, strict deterministic smoke launch, strict acceptance env apply, and post-acceptance restart must require operator authorization in this plan",
    )
    _require(
        mutating_steps
        == [
            "apply_approved_stale_task_resolution",
            "apply_production_readiness_env",
            "restart_api_normally",
            "run_strict_remote_smoke_acceptance",
            "emit_fast_launch_acceptance_env_after_strict_verify",
            "restart_api_after_fast_launch_acceptance_env",
        ],
        "only stale-task apply, production readiness env apply, normal restart, strict deterministic smoke launch, strict acceptance env apply, and post-acceptance restart may mutate remote state",
    )

    serialized = json.dumps(plan, sort_keys=True)
    _require("approval_fingerprint" in serialized, "plan must preserve approval_fingerprint evidence requirement")
    _require("approval_expires_at_utc" in serialized, "plan must preserve approval_expires_at_utc evidence requirement")
    _require("restart_preflight:ok" in serialized, "plan must require restart_preflight:ok")
    _require("skipped_missing_model_config" in serialized, "plan must reject skipped_missing_model_config")

    return {
        "status": "passed",
        "summary": "status=passed",
        "checked": {
            "plan_id": plan["plan_id"],
            "step_count": len(verified_steps),
            "target_task_ids": plan["target_task_ids"],
            "freshness_hours": plan["freshness_hours"],
            "approval_json": approval_json,
            "approval_json_status": approval_state["approval_json_status"],
            "approval_expires_at_utc": approval_state["approval_expires_at_utc"],
            "approval_request_required_fields": plan["approval_request_requirements"]["must_include_fields"],
            "operator_authorization_required_steps": operator_steps,
            "mutating_steps": mutating_steps,
            "frontend_gate_status": plan["frontend_gate"]["status_until_all_steps_pass"],
            "approval_refresh_required_when": refresh.get("required_when") or refresh.get("status"),
        },
    }


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Verify the remote release gate command plan JSON.")
    parser.add_argument("plan_json", help="Path to docs/deployment/remote-release-gate-command-plan.json")
    parser.add_argument("--now-utc", default=None, help="Testing hook: ISO-8601 UTC timestamp used for approval expiry checks.")
    args = parser.parse_args(argv)
    plan = load_plan(args.plan_json)
    report = verify_plan(plan, now_utc=args.now_utc)
    report["source_json"] = str(Path(args.plan_json))
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
