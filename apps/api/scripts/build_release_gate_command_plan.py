from __future__ import annotations

import argparse
import importlib.util
import json
from collections.abc import Sequence
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path


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


def _remote_approval_json_path(value: str | None, *, fallback: Path) -> str:
    text = value or str(fallback)
    normalized = text.replace("\\", "/")
    invalid_message = "approval_json_command_path must be a /tmp/image_agent_*.json remote path"
    if not (normalized.startswith("/tmp/image_agent_") and normalized.endswith(".json")):
        raise SystemExit(invalid_message)
    if any(part in {"", ".", ".."} for part in normalized.split("/")[1:]):
        raise SystemExit(invalid_message)
    return normalized


def build_release_gate_plan(
    *,
    plan_json: Path,
    approval_json: Path,
    expected_task_ids: Sequence[int],
    max_age_hours: float,
    now_utc: str | None = None,
    approval_json_command_path: str | None = None,
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
    plan = deepcopy(source_plan)
    plan = _replace_string_values(plan, old=PLACEHOLDER_APPROVAL_JSON, new=approval_json_text)
    if not isinstance(plan, dict):
        raise SystemExit("release gate plan must be a JSON object")
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
    parser.add_argument("--output-json", default=None, help="Optional path to save the materialized release gate plan.")
    args = parser.parse_args(argv)

    plan = build_release_gate_plan(
        plan_json=Path(args.plan_json),
        approval_json=Path(args.approval_json),
        expected_task_ids=args.task_ids,
        max_age_hours=args.max_age_hours,
        now_utc=args.now_utc,
        approval_json_command_path=args.approval_json_command_path,
    )
    if args.output_json:
        Path(args.output_json).write_text(json.dumps(plan, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(plan, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
