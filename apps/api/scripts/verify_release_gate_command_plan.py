from __future__ import annotations

import argparse
import json
import re
import shlex
from collections.abc import Sequence
from datetime import datetime, timezone
from pathlib import Path


PLAN_ID = "remote_release_gate_after_stale_task_approval_v1"
API_KEY_SHAPED_RE = re.compile(r"(?<![A-Za-z0-9])sk-[A-Za-z0-9_-]{10,}")
REMOTE_ENV_LOAD_SNIPPET = "set -a; . /home/yyf/project/image_agent/.env; set +a;"
FRESH_APPROVAL_JSON = "<fresh_reviewed_approval_json>"
EXPIRED_APPROVAL_JSON = "/tmp/image_agent_stale_tasks_83_84_dry_run_20260614T080202Z.json"

EXPECTED_STEP_IDS = [
    "verify_fresh_stale_task_approval",
    "apply_approved_stale_task_resolution",
    "collect_post_apply_clean_dry_run",
    "verify_post_apply_clean_resolution",
    "restart_api_preflight_only",
    "restart_api_normally",
    "run_strict_remote_smoke_acceptance",
    "verify_strict_remote_smoke_acceptance_json",
    "emit_fast_launch_acceptance_env_after_strict_verify",
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
        "scripts/build_release_gate_command_plan.py docs/deployment/remote-release-gate-command-plan.json",
        "/tmp/image_agent_stale_tasks_83_84_dry_run_<timestamp>.json",
        "--task-id 83 --task-id 84",
        "--max-age-hours 24",
        "--output-json /tmp/image_agent_remote_release_gate_plan_<timestamp>.json",
    ):
        _require(required in materialize_command, f"stale_task_approval_refresh.materialize_plan_command must include {required}")
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
    _require(
        plan.get("release_overlay") == "/home/yyf/project/image_agent_releases/codex-gate-verifiers-efca895b-20260613T165132",
        "release_overlay must point at the prepared remote verifier overlay",
    )
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
        commands_by_step["verify_post_apply_clean_resolution"],
        "verify_stale_task_resolution.py --apply-json /tmp/image_agent_stale_tasks_83_84_apply_<timestamp>.json --resolution-json /tmp/image_agent_stale_tasks_83_84_resolved_dry_run_<timestamp>.json --task-id 83 --task-id 84 --require-empty-active --max-age-hours 24",
        step_id="verify_post_apply_clean_resolution",
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
    for required_flag in (
        "--require-model",
        "--expected-model-wire-api responses",
        "--expected-model-provider-profile rawchat",
        "--require-model-tool-loop",
        "--require-project-agent-context",
        "--require-agent-workflow-confirmation",
        "--require-deployment-identity",
        "--require-production-readiness",
        "--deployment-id <accepted_release_or_commit>",
        "--expected-health-version <expected_health_version>",
        "--min-documents 60",
        "--min-chunks 200",
        "--require-raw-source-policy",
        "--require-vendor-pointer-integrity",
        "--require-real-evidence-ids",
        "--require-completed-upload",
        "--require-uploaded-series",
        "--upload-nifti-file <remote_nifti_file>",
        "--require-completed-task",
        "--require-launched-task",
        "--launch-workflow-type <real_registered_workflow_type>",
        "--wait-task-completion-timeout-seconds 21600",
        "--wait-task-completion-poll-seconds 30",
        "--require-launchability-matrix",
        "--require-container-native-qc",
        "--min-native-qc-images 1",
        "--require-scientific-report-artifacts",
        "--min-scientific-report-images 1",
        "--project-id <project_id>",
        "--upload-session-id <upload_session_id>",
        "--output-json",
    ):
        _require_command_contains(
            commands_by_step["run_strict_remote_smoke_acceptance"],
            required_flag,
            step_id="run_strict_remote_smoke_acceptance",
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
    _require_command_contains(
        commands_by_step["emit_fast_launch_acceptance_env_after_strict_verify"],
        "verify_remote_smoke_acceptance.py",
        step_id="emit_fast_launch_acceptance_env_after_strict_verify",
    )
    _require_command_contains(
        commands_by_step["emit_fast_launch_acceptance_env_after_strict_verify"],
        "--max-age-hours 24",
        step_id="emit_fast_launch_acceptance_env_after_strict_verify",
    )
    _require_command_contains(
        commands_by_step["emit_fast_launch_acceptance_env_after_strict_verify"],
        "--emit-fast-launch-env",
        step_id="emit_fast_launch_acceptance_env_after_strict_verify",
    )
    _require(
        strict_smoke_json in shlex.split(commands_by_step["emit_fast_launch_acceptance_env_after_strict_verify"]),
        "fast-launch env export command must verify the smoke output JSON",
    )

    mutating_steps = [step["id"] for step in verified_steps if step["mutates_remote_state"]]
    operator_steps = [step["id"] for step in verified_steps if step["requires_operator_authorization"]]
    _require(
        operator_steps == ["apply_approved_stale_task_resolution"],
        "only stale-task apply may require operator authorization in this plan",
    )
    _require(
        mutating_steps
        == ["apply_approved_stale_task_resolution", "restart_api_normally", "run_strict_remote_smoke_acceptance"],
        "only stale-task apply, normal restart, and strict deterministic smoke launch may mutate remote state",
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
            "approval_refresh_required_when": refresh["required_when"],
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
