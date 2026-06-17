from __future__ import annotations

import argparse
import json
import re
import shlex
from collections.abc import Sequence
from datetime import datetime, timedelta, timezone
from pathlib import Path


EXPECTED_FOLLOWUP_STEP_IDS = [
    "collect_post_apply_clean_dry_run",
    "verify_post_apply_clean_resolution",
    "restart_api_preflight_only",
    "restart_api_normally",
    "run_strict_remote_smoke_acceptance",
    "verify_strict_remote_smoke_acceptance_json_after_normal_restart",
    "emit_fast_launch_acceptance_env_after_strict_verify",
]
REMOTE_ENV_LOAD_SNIPPET = "set -a; . /home/yyf/project/image_agent/.env; set +a;"
API_KEY_SHAPED_RE = re.compile(r"(?<![A-Za-z0-9_-])sk-[A-Za-z0-9_-]{20,}")


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(message)


def _parse_utc_timestamp(value: object, *, key: str) -> datetime:
    _require(isinstance(value, str) and value, f"{key} must be an ISO-8601 timestamp")
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise SystemExit(f"{key} must be an ISO-8601 timestamp") from exc
    _require(parsed.tzinfo is not None and parsed.utcoffset() is not None, f"{key} must be timezone-aware")
    return parsed.astimezone(timezone.utc)


def _verify_freshness(generated_at: str, *, max_age_hours: float, now_utc: datetime | None) -> datetime:
    _require(max_age_hours >= 0, "max_age_hours must be non-negative")
    parsed = _parse_utc_timestamp(generated_at, key="verified_approval.checked.generated_at_utc")
    now = now_utc or datetime.now(timezone.utc)
    _require(now.tzinfo is not None and now.utcoffset() is not None, "now_utc must be timezone-aware")
    age_hours = (now.astimezone(timezone.utc) - parsed).total_seconds() / 3600
    _require(age_hours >= 0, "verified approval generated_at_utc must not be in the future")
    _require(age_hours <= max_age_hours, "verified approval generated_at_utc is older than max_age_hours")
    return parsed


def _task_flags(task_ids: Sequence[int]) -> str:
    return " ".join(f"--task-id {int(task_id)}" for task_id in task_ids)


def _assert_safe_command(command: object, *, key: str) -> str:
    _require(isinstance(command, str) and command.strip(), f"{key} command must be non-empty")
    _require(
        "IMAGE_AGENT_ALLOW_RESTART_WITH_ACTIVE_TASKS=1" not in command,
        f"{key} command must not use active-task restart override",
    )
    _require("OPENAI_API_KEY" not in command, f"{key} command must not mention OPENAI_API_KEY")
    _require(API_KEY_SHAPED_RE.search(command) is None, f"{key} command must not contain API-key shaped strings")
    return command


def _step_by_id(steps: list[dict], step_id: str) -> dict:
    for step in steps:
        if step.get("id") == step_id:
            return step
    raise SystemExit(f"missing follow-up step {step_id}")


def _token_after(command: str, token: str, *, key: str) -> str:
    try:
        parts = shlex.split(command)
    except ValueError as exc:
        raise SystemExit(f"{key} command could not be parsed") from exc
    try:
        index = parts.index(token)
    except ValueError as exc:
        raise SystemExit(f"{key} command must include {token}") from exc
    _require(index + 1 < len(parts) and parts[index + 1], f"{key} command must include a value after {token}")
    return parts[index + 1]


def verify_apply_request(
    request: dict,
    *,
    expected_task_ids: Sequence[int] | None = None,
    max_age_hours: float = 24.0,
    now_utc: str | datetime | None = None,
) -> dict:
    _require(isinstance(request, dict), "apply request must be a JSON object")
    _require(request.get("status") == "operator_authorization_required", "status must be operator_authorization_required")
    _require(request.get("request_type") == "stale_task_apply_approval", "request_type must be stale_task_apply_approval")
    _require(request.get("authorization_required") is True, "authorization_required must be true")
    _require(
        request.get("must_not_run_until") == "operator explicitly approves stale-task apply",
        "must_not_run_until must require explicit operator approval",
    )
    target_task_ids = request.get("target_task_ids")
    _require(isinstance(target_task_ids, list) and target_task_ids, "target_task_ids must be non-empty")
    _require(all(isinstance(item, int) and not isinstance(item, bool) for item in target_task_ids), "target_task_ids entries must be integers")
    if expected_task_ids is not None:
        _require(sorted(target_task_ids) == sorted(int(item) for item in expected_task_ids), "target_task_ids must match expected task ids")
    task_flags = _task_flags(target_task_ids)

    verified = request.get("verified_approval")
    _require(isinstance(verified, dict), "verified_approval must be present")
    _require(verified.get("status") == "passed", "verified_approval.status must be passed")
    checked = verified.get("checked")
    _require(isinstance(checked, dict), "verified_approval.checked must be present")
    _require(checked.get("target_task_ids") == target_task_ids, "verified approval target_task_ids mismatch")
    approval_fingerprint = request.get("approval_fingerprint")
    _require(isinstance(approval_fingerprint, str) and len(approval_fingerprint) == 64, "approval_fingerprint must be SHA-256 hex")
    _require(checked.get("approval_fingerprint") == approval_fingerprint, "approval_fingerprint mismatch")
    now = _parse_utc_timestamp(now_utc, key="now_utc") if isinstance(now_utc, str) else now_utc
    generated_at_utc = _verify_freshness(
        checked.get("generated_at_utc"),
        max_age_hours=max_age_hours,
        now_utc=now,
    )
    expires_at_utc = generated_at_utc + timedelta(hours=max_age_hours)
    _require(
        request.get("approval_expires_at_utc") == expires_at_utc.isoformat(),
        "approval_expires_at_utc mismatch",
    )

    apply_step = request.get("apply_step")
    _require(isinstance(apply_step, dict), "apply_step must be present")
    _require(apply_step.get("id") == "apply_approved_stale_task_resolution", "apply_step.id mismatch")
    _require(apply_step.get("requires_operator_authorization") is True, "apply_step must require operator authorization")
    _require(apply_step.get("mutates_remote_state") is True, "apply_step must mutate remote state")
    apply_command = _assert_safe_command(apply_step.get("command"), key="apply_step")
    for required in (
        REMOTE_ENV_LOAD_SNIPPET,
        "reconcile_stale_tasks.py --apply",
        f"--max-age-hours {max_age_hours:g}",
        task_flags,
        f"--approval-json {request.get('approval_json')}",
        '--reason "operator confirmed no matching running Image Agent container"',
    ):
        _require(required in apply_command, f"apply_step command must include {required}")

    steps = request.get("required_followup_steps")
    _require(isinstance(steps, list), "required_followup_steps must be a list")
    _require(all(isinstance(step, dict) for step in steps), "required_followup_steps entries must be objects")
    step_ids = [step.get("id") for step in steps]
    _require(step_ids == EXPECTED_FOLLOWUP_STEP_IDS, "required follow-up step ids mismatch")
    commands = {step["id"]: _assert_safe_command(step.get("command"), key=step["id"]) for step in steps}

    _require("reconcile_stale_tasks.py --max-age-hours 24 --check-containers" in commands["collect_post_apply_clean_dry_run"], "post-apply dry-run command mismatch")
    _require(REMOTE_ENV_LOAD_SNIPPET in commands["collect_post_apply_clean_dry_run"], "post-apply dry-run must load remote env")
    _require("verify_stale_task_resolution.py" in commands["verify_post_apply_clean_resolution"], "resolution verifier command missing")
    _require("--require-empty-active --max-age-hours 24" in commands["verify_post_apply_clean_resolution"], "resolution verifier must require empty active and freshness")
    _require("IMAGE_AGENT_RESTART_PREFLIGHT_ONLY=1" in commands["restart_api_preflight_only"], "preflight command must set preflight-only mode")
    _require("restart_preflight:ok" == _step_by_id(steps, "restart_api_preflight_only").get("expected_success"), "preflight expected success mismatch")
    _require("bash tools/restart_remote_image_agent_api.sh" in commands["restart_api_normally"], "normal restart command missing")
    _require("IMAGE_AGENT_RESTART_PREFLIGHT_ONLY=1" not in commands["restart_api_normally"], "normal restart must not be preflight-only")
    strict_smoke_step = _step_by_id(steps, "run_strict_remote_smoke_acceptance")
    strict_smoke_command = commands["run_strict_remote_smoke_acceptance"]
    strict_smoke_verify_command = commands["verify_strict_remote_smoke_acceptance_json_after_normal_restart"]
    strict_smoke_env_export_command = commands["emit_fast_launch_acceptance_env_after_strict_verify"]
    for required in (
        "smoke_remote_agent.py",
        "--require-model",
        "--expected-model-wire-api responses",
        "--expected-model-provider-profile rawchat",
        "--require-model-tool-loop",
        "--require-project-agent-context",
        "--require-agent-workflow-confirmation",
        "--require-agent-workflow-resume",
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
        _require(required in strict_smoke_command, f"strict smoke command must include {required}")
    _require(
        "<completed_task_id>" not in strict_smoke_command,
        "strict smoke command must launch and resolve the task id instead of using <completed_task_id>",
    )
    _require(
        "--launch-series-id <uploaded_series_id>" not in strict_smoke_command,
        "strict smoke command must use the uploaded series returned by --require-uploaded-series",
    )
    _require(
        strict_smoke_step.get("mutates_remote_state") is True,
        "strict smoke step must be marked as mutating remote state",
    )
    strict_smoke_json = _token_after(strict_smoke_command, "--output-json", key="run_strict_remote_smoke_acceptance")
    _require(
        strict_smoke_step.get("expected_output_json") == strict_smoke_json,
        "strict smoke expected_output_json must match --output-json",
    )
    _require("verify_remote_smoke_acceptance.py" in strict_smoke_verify_command, "strict smoke verifier command missing")
    _require("--max-age-hours 24" in strict_smoke_verify_command, "strict smoke verifier must require freshness")
    _require(
        strict_smoke_json in shlex.split(strict_smoke_verify_command),
        "strict smoke verifier command must verify the smoke output JSON",
    )
    _require(
        "verify_remote_smoke_acceptance.py" in strict_smoke_env_export_command,
        "fast-launch env export command missing strict smoke verifier",
    )
    _require("--max-age-hours 24" in strict_smoke_env_export_command, "fast-launch env export must require freshness")
    _require("--emit-fast-launch-env" in strict_smoke_env_export_command, "fast-launch env export command missing")
    _require(
        strict_smoke_json in shlex.split(strict_smoke_env_export_command),
        "fast-launch env export command must verify the smoke output JSON",
    )

    return {
        "status": "passed",
        "summary": "status=passed",
        "checked": {
            "request_type": request["request_type"],
            "authorization_required": request["authorization_required"],
            "target_task_ids": target_task_ids,
            "approval_fingerprint": approval_fingerprint,
            "verified_approval_generated_at_utc": generated_at_utc.isoformat(),
            "max_age_hours": float(max_age_hours),
            "expires_at_utc": expires_at_utc.isoformat(),
            "followup_step_ids": step_ids,
        },
    }


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Verify a stale-task apply approval request JSON.")
    parser.add_argument("request_json", help="Path to JSON written by build_stale_task_apply_request.py.")
    parser.add_argument("--task-id", action="append", type=int, dest="task_ids")
    parser.add_argument("--max-age-hours", type=float, default=24.0)
    parser.add_argument("--now-utc", default=None, help="Testing hook: ISO-8601 UTC timestamp used as current time.")
    args = parser.parse_args(argv)
    source_path = Path(args.request_json)
    request = json.loads(source_path.read_text(encoding="utf-8"))
    report = verify_apply_request(
        request,
        expected_task_ids=args.task_ids,
        max_age_hours=args.max_age_hours,
        now_utc=args.now_utc,
    )
    report["source_json"] = str(source_path)
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
