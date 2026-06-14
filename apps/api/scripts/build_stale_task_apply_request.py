from __future__ import annotations

import argparse
import importlib.util
import json
from collections.abc import Sequence
from datetime import datetime, timezone
from pathlib import Path


REMOTE_OVERLAY_ROOT = "/home/yyf/project/image_agent_releases/codex-gate-verifiers-efca895b-20260613T165132"
REMOTE_API_DIR = f"{REMOTE_OVERLAY_ROOT}/apps/api"
REMOTE_SHARED_PYTHON = "/home/yyf/project/image_agent/apps/api/.venv/bin/python"
REMOTE_ENV_LOAD_SNIPPET = "set -a; . /home/yyf/project/image_agent/.env; set +a;"
APPLY_REASON = "operator confirmed no matching running Image Agent container"


def _load_approval_verifier():
    script = Path(__file__).resolve().with_name("verify_stale_task_approval.py")
    spec = importlib.util.spec_from_file_location("verify_stale_task_approval", script)
    module = importlib.util.module_from_spec(spec)
    if spec.loader is None:
        raise RuntimeError("could not load verify_stale_task_approval.py")
    spec.loader.exec_module(module)
    return module


def _parse_utc_timestamp(value: str | None) -> datetime | None:
    if value is None:
        return None
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise SystemExit("now_utc must be timezone-aware")
    return parsed.astimezone(timezone.utc)


def _timestamp_for_paths(value: str | None) -> str:
    if value:
        return value
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _task_flags(task_ids: Sequence[int]) -> str:
    return " ".join(f"--task-id {int(task_id)}" for task_id in task_ids)


def _api_command(command: str, *, load_env: bool = False) -> str:
    env = f"{REMOTE_ENV_LOAD_SNIPPET} " if load_env else ""
    return f"cd {REMOTE_API_DIR} && {env}PYTHONPATH=. {REMOTE_SHARED_PYTHON} {command}"


def build_apply_request(
    *,
    approval_json: Path,
    expected_task_ids: Sequence[int],
    max_age_hours: float,
    now_utc: str | None = None,
    output_timestamp: str | None = None,
) -> dict:
    verifier = _load_approval_verifier()
    payload = json.loads(approval_json.read_text(encoding="utf-8"))
    now = _parse_utc_timestamp(now_utc)
    verified = verifier.verify_approval_payload(
        payload,
        expected_task_ids=expected_task_ids,
        now=now,
        max_age_hours=max_age_hours,
    )
    task_ids = verified["checked"]["target_task_ids"]
    task_flags = _task_flags(task_ids)
    stamp = _timestamp_for_paths(output_timestamp)
    apply_json = f"/tmp/image_agent_stale_tasks_83_84_apply_{stamp}.json"
    resolution_json = f"/tmp/image_agent_stale_tasks_83_84_resolved_dry_run_{stamp}.json"
    strict_smoke_json = f"/tmp/image_agent_remote_smoke_acceptance_{stamp}.json"
    approval_json_text = str(approval_json)

    apply_command = _api_command(
        (
            f"scripts/reconcile_stale_tasks.py --apply --max-age-hours {max_age_hours:g} "
            f"{task_flags} --approval-json {approval_json_text} "
            f"--reason \"{APPLY_REASON}\" > {apply_json}"
        ),
        load_env=True,
    )
    post_apply_dry_run = _api_command(
        (
            f"scripts/reconcile_stale_tasks.py --max-age-hours {max_age_hours:g} "
            f"--check-containers {task_flags} > {resolution_json}"
        ),
        load_env=True,
    )
    verify_resolution = _api_command(
        (
            f"scripts/verify_stale_task_resolution.py --apply-json {apply_json} "
            f"--resolution-json {resolution_json} {task_flags} "
            f"--require-empty-active --max-age-hours {max_age_hours:g}"
        )
    )
    restart_preflight = (
        f"cd {REMOTE_OVERLAY_ROOT} && "
        "IMAGE_AGENT_ROOT=/home/yyf/project/image_agent "
        f"IMAGE_AGENT_RELEASE_ROOT={REMOTE_OVERLAY_ROOT} "
        "IMAGE_AGENT_ENV_FILE=/home/yyf/project/image_agent/.env "
        "IMAGE_AGENT_SHARED_VENV_BIN=/home/yyf/project/image_agent/apps/api/.venv/bin "
        "IMAGE_AGENT_RESTART_PREFLIGHT_ONLY=1 "
        "bash tools/restart_remote_image_agent_api.sh"
    )
    strict_smoke_verify = _api_command(
        f"scripts/verify_remote_smoke_acceptance.py {strict_smoke_json} --max-age-hours {max_age_hours:g}"
    )

    return {
        "status": "operator_authorization_required",
        "request_type": "stale_task_apply_approval",
        "authorization_required": True,
        "must_not_run_until": "operator explicitly approves stale-task apply",
        "approval_json": approval_json_text,
        "approval_fingerprint": verified["checked"]["approval_fingerprint"],
        "target_task_ids": task_ids,
        "verified_approval": verified,
        "apply_step": {
            "id": "apply_approved_stale_task_resolution",
            "requires_operator_authorization": True,
            "mutates_remote_state": True,
            "command": apply_command,
            "expected_output_json": apply_json,
        },
        "required_followup_steps": [
            {
                "id": "collect_post_apply_clean_dry_run",
                "mutates_remote_state": False,
                "command": post_apply_dry_run,
                "expected_output_json": resolution_json,
            },
            {
                "id": "verify_post_apply_clean_resolution",
                "mutates_remote_state": False,
                "command": verify_resolution,
                "expected_success": "status=passed",
            },
            {
                "id": "restart_api_preflight_only",
                "mutates_remote_state": False,
                "command": restart_preflight,
                "expected_success": "restart_preflight:ok",
            },
            {
                "id": "verify_strict_remote_smoke_acceptance_json_after_normal_restart",
                "mutates_remote_state": False,
                "command": strict_smoke_verify,
                "expected_success": "status=passed",
            },
        ],
        "safety_invariants": [
            "do_not_run_without_explicit_operator_authorization",
            "do_not_use_IMAGE_AGENT_ALLOW_RESTART_WITH_ACTIVE_TASKS",
            "do_not_count_skipped_missing_model_config_as_passed",
            "do_not_store_or_print_api_keys_or_secrets",
        ],
    }


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Build a reviewed stale-task apply approval request JSON.")
    parser.add_argument("approval_json", help="Path to verified stale-task approval dry-run JSON.")
    parser.add_argument("--task-id", action="append", type=int, dest="task_ids", required=True)
    parser.add_argument("--max-age-hours", type=float, default=24.0)
    parser.add_argument("--now-utc", default=None, help="Testing hook: ISO-8601 UTC timestamp used as current time.")
    parser.add_argument("--output-timestamp", default=None, help="Timestamp suffix for generated /tmp output paths.")
    parser.add_argument("--output-json", default=None, help="Optional path to save the approval request JSON.")
    args = parser.parse_args(argv)

    request = build_apply_request(
        approval_json=Path(args.approval_json),
        expected_task_ids=args.task_ids,
        max_age_hours=args.max_age_hours,
        now_utc=args.now_utc,
        output_timestamp=args.output_timestamp,
    )
    if args.output_json:
        request["output_json"] = str(Path(args.output_json))
        Path(args.output_json).write_text(json.dumps(request, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(request, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
