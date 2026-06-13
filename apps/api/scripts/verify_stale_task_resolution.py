from __future__ import annotations

import argparse
import hashlib
import json
from collections.abc import Sequence
from datetime import datetime, timezone
from pathlib import Path


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(message)


def _as_int_list(value: object, *, key: str) -> list[int]:
    _require(isinstance(value, list), f"{key} must be a list")
    result: list[int] = []
    for item in value:
        _require(isinstance(item, int) and not isinstance(item, bool), f"{key} entries must be integers")
        result.append(item)
    return result


def _as_task_list(value: object, *, key: str) -> list[dict]:
    _require(isinstance(value, list), f"{key} must be a list")
    result: list[dict] = []
    for item in value:
        _require(isinstance(item, dict), f"{key} entries must be objects")
        result.append(item)
    return result


def _looks_like_backend_path(value: str) -> bool:
    normalized = value.replace("\\", "/")
    return (
        normalized.startswith("/")
        or (len(normalized) >= 3 and normalized[1] == ":" and normalized[0].isalpha() and normalized[2] == "/")
        or "/home/yyf/" in normalized
        or "/project/image_agent/" in normalized
        or "/data/projects/" in normalized
    )


def _assert_no_backend_paths(value: object) -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            _require(key != "log_path", "task evidence must not expose log_path")
            _assert_no_backend_paths(item)
        return
    if isinstance(value, list):
        for item in value:
            _assert_no_backend_paths(item)
        return
    if isinstance(value, str):
        _require(not _looks_like_backend_path(value), "stale-task evidence must not expose backend paths")


def _parse_timestamp(value: object, *, key: str) -> datetime:
    _require(isinstance(value, str) and bool(value), f"{key} must be an ISO-8601 timestamp")
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise SystemExit(f"{key} must be an ISO-8601 timestamp") from exc
    _require(parsed.tzinfo is not None and parsed.utcoffset() is not None, f"{key} must be timezone-aware")
    return parsed.astimezone(timezone.utc)


def _max_age_hours(payload: dict, *, key: str, override: float | None = None) -> float:
    value = override if override is not None else payload.get("max_age_hours")
    _require(isinstance(value, (int, float)) and not isinstance(value, bool), f"{key}.max_age_hours must be a number")
    max_age_hours = float(value)
    _require(max_age_hours >= 0, f"{key}.max_age_hours must be non-negative")
    return max_age_hours


def _verify_freshness(payload: dict, *, key: str, now: datetime | None, max_age_hours: float | None = None) -> datetime:
    generated_at = _parse_timestamp(payload.get("generated_at"), key=f"{key}.generated_at")
    current = now or datetime.now(timezone.utc)
    _require(current.tzinfo is not None and current.utcoffset() is not None, "now must be timezone-aware")
    age_hours = (current.astimezone(timezone.utc) - generated_at).total_seconds() / 3600
    _require(age_hours >= 0, f"{key}.generated_at must not be in the future")
    _require(
        age_hours <= _max_age_hours(payload, key=key, override=max_age_hours),
        f"{key}.generated_at is older than max_age_hours",
    )
    return generated_at


def _approval_fingerprint(payload: dict) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _verify_fingerprint(payload: dict) -> str:
    approval_payload = payload.get("approval_payload")
    _require(isinstance(approval_payload, dict), "approval_payload must be present")
    actual = payload.get("approval_fingerprint")
    _require(isinstance(actual, str) and len(actual) == 64, "approval_fingerprint must be a SHA-256 hex string")
    _require(actual == _approval_fingerprint(approval_payload), "approval_fingerprint mismatch")
    return actual


def _expected_task_ids(expected_task_ids: Sequence[int]) -> list[int]:
    return sorted(int(task_id) for task_id in expected_task_ids)


def _task_ids(tasks: list[dict]) -> list[int]:
    ids: list[int] = []
    for task in tasks:
        _require("log_path" not in task, "task evidence must not expose log_path")
        task_id = task.get("id")
        _require(isinstance(task_id, int) and not isinstance(task_id, bool), "task id must be an integer")
        ids.append(task_id)
    return ids


def _verify_approval_payload_summary(
    payload: dict,
    *,
    key: str,
    expected_target_ids: list[int],
    expected_stale_candidate_ids: list[int],
) -> None:
    approval_payload = payload.get("approval_payload")
    _require(isinstance(approval_payload, dict), f"{key} approval_payload must be present")
    target_ids = sorted(_as_int_list(approval_payload.get("target_task_ids"), key=f"{key}.approval_payload.target_task_ids"))
    _require(target_ids == expected_target_ids, f"{key} approval_payload target_task_ids must match expected task ids")
    candidate_ids = sorted(_as_int_list(approval_payload.get("stale_candidate_ids"), key=f"{key}.approval_payload.stale_candidate_ids"))
    if expected_stale_candidate_ids:
        _require(candidate_ids == expected_stale_candidate_ids, f"{key} approval_payload stale_candidate_ids must match expected task ids")
    else:
        _require(candidate_ids == [], f"{key} approval_payload stale_candidate_ids must be empty")
    _require(
        _as_int_list(approval_payload.get("running_container_task_ids"), key=f"{key}.approval_payload.running_container_task_ids") == [],
        f"{key} approval_payload running_container_task_ids must be empty",
    )
    _require(
        _as_int_list(approval_payload.get("blocked_task_ids"), key=f"{key}.approval_payload.blocked_task_ids") == [],
        f"{key} approval_payload blocked_task_ids must be empty",
    )
    _require(
        _as_int_list(approval_payload.get("out_of_scope_stale_task_ids"), key=f"{key}.approval_payload.out_of_scope_stale_task_ids") == [],
        f"{key} approval_payload out_of_scope_stale_task_ids must be empty",
    )
    _require(approval_payload.get("container_check_status") == "passed", f"{key} approval_payload container_check_status must be passed")


def verify_resolution_evidence(
    apply_payload: dict,
    resolution_payload: dict,
    *,
    expected_task_ids: Sequence[int],
    require_empty_active: bool = False,
    now: datetime | None = None,
    max_age_hours: float | None = None,
) -> dict:
    """Verify stale-task apply evidence plus a follow-up clean dry-run report."""

    expected = _expected_task_ids(expected_task_ids)
    _require(expected, "expected task ids are required")
    _require(isinstance(apply_payload, dict), "apply payload must be a JSON object")
    _require(isinstance(resolution_payload, dict), "resolution payload must be a JSON object")
    _assert_no_backend_paths(apply_payload)
    _assert_no_backend_paths(resolution_payload)
    apply_generated_at = _verify_freshness(apply_payload, key="apply", now=now, max_age_hours=max_age_hours)
    resolution_generated_at = _verify_freshness(
        resolution_payload,
        key="resolution",
        now=now,
        max_age_hours=max_age_hours,
    )
    _require(
        resolution_generated_at >= apply_generated_at,
        "resolution generated_at must be after or equal to apply generated_at",
    )

    apply_fingerprint = _verify_fingerprint(apply_payload)
    _require(apply_payload.get("mode") == "apply", "apply mode must be apply")
    _require(apply_payload.get("container_check_status") == "passed", "apply container_check_status must be passed")
    _require(_as_int_list(apply_payload.get("running_container_task_ids"), key="apply.running_container_task_ids") == [], "apply running_container_task_ids must be empty")
    _require(_as_int_list(apply_payload.get("blocked_task_ids"), key="apply.blocked_task_ids") == [], "apply blocked_task_ids must be empty")
    _require(_as_int_list(apply_payload.get("out_of_scope_stale_task_ids"), key="apply.out_of_scope_stale_task_ids") == [], "apply out_of_scope_stale_task_ids must be empty")
    apply_targets = sorted(_as_int_list(apply_payload.get("target_task_ids"), key="apply.target_task_ids"))
    _require(apply_targets == expected, "apply target_task_ids must match expected task ids")
    updated_task_ids = sorted(_as_int_list(apply_payload.get("updated_task_ids"), key="apply.updated_task_ids"))
    _require(updated_task_ids == expected, "updated_task_ids must match expected task ids")
    apply_candidates = _as_task_list(apply_payload.get("stale_candidates"), key="apply.stale_candidates")
    _require(sorted(_task_ids(apply_candidates)) == expected, "apply stale_candidates must match expected task ids")
    for candidate in apply_candidates:
        _require(candidate.get("is_stale") is True, "apply stale_candidates entries must be stale")
        _require(candidate.get("status") in {"queued", "running"}, "apply stale_candidates entries must be active tasks")
    _verify_approval_payload_summary(
        apply_payload,
        key="apply",
        expected_target_ids=expected,
        expected_stale_candidate_ids=expected,
    )

    resolution_fingerprint = _verify_fingerprint(resolution_payload)
    _require(resolution_payload.get("mode") == "dry_run", "resolution mode must be dry_run")
    _require(resolution_payload.get("container_check_status") == "passed", "resolution container_check_status must be passed")
    _require(_as_int_list(resolution_payload.get("running_container_task_ids"), key="resolution.running_container_task_ids") == [], "resolution running_container_task_ids must be empty")
    _require(_as_int_list(resolution_payload.get("blocked_task_ids"), key="resolution.blocked_task_ids") == [], "resolution blocked_task_ids must be empty")
    _require(_as_int_list(resolution_payload.get("updated_task_ids"), key="resolution.updated_task_ids") == [], "resolution updated_task_ids must be empty")
    _require(_as_int_list(resolution_payload.get("out_of_scope_stale_task_ids"), key="resolution.out_of_scope_stale_task_ids") == [], "resolution out_of_scope_stale_task_ids must be empty")
    resolution_targets = sorted(_as_int_list(resolution_payload.get("target_task_ids"), key="resolution.target_task_ids"))
    _require(resolution_targets == expected, "resolution target_task_ids must match expected task ids")

    resolution_candidates = _as_task_list(resolution_payload.get("stale_candidates"), key="resolution.stale_candidates")
    _require(resolution_candidates == [], "resolved dry-run stale_candidates must be empty")
    active_tasks = _as_task_list(resolution_payload.get("active_tasks"), key="resolution.active_tasks")
    active_target_ids = sorted(task_id for task_id in _task_ids(active_tasks) if task_id in expected)
    _require(active_target_ids == [], "resolved dry-run must not include target task ids as active")
    _verify_approval_payload_summary(
        resolution_payload,
        key="resolution",
        expected_target_ids=expected,
        expected_stale_candidate_ids=[],
    )
    if require_empty_active:
        _require(resolution_payload.get("active_task_count") == 0, "resolved dry-run active_task_count must be 0")
        _require(active_tasks == [], "resolved dry-run active_tasks must be empty")

    return {
        "status": "passed",
        "summary": "status=passed",
        "checked": {
            "target_task_ids": expected,
            "updated_task_ids": updated_task_ids,
            "resolved_task_ids": expected,
            "apply_approval_fingerprint": apply_fingerprint,
            "resolution_approval_fingerprint": resolution_fingerprint,
            "require_empty_active": require_empty_active,
        },
    }


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Verify stale-task apply evidence and a clean follow-up dry-run JSON artifact.")
    parser.add_argument("--apply-json", required=True, help="Path to JSON written by reconcile_stale_tasks.py --apply.")
    parser.add_argument("--resolution-json", required=True, help="Path to follow-up dry-run JSON written after the apply.")
    parser.add_argument("--task-id", action="append", type=int, dest="task_ids", required=True, help="Expected reconciled task id. Repeat for multiple ids.")
    parser.add_argument("--require-empty-active", action="store_true", help="Require the follow-up dry-run to report no active tasks at all.")
    parser.add_argument(
        "--max-age-hours",
        type=float,
        default=None,
        help="Override payload max_age_hours freshness limits for apply and resolution evidence.",
    )
    parser.add_argument(
        "--now-utc",
        default=None,
        help="Testing hook: ISO-8601 UTC timestamp used as current time for --max-age-hours.",
    )
    args = parser.parse_args(argv)

    apply_path = Path(args.apply_json)
    resolution_path = Path(args.resolution_json)
    apply_payload = json.loads(apply_path.read_text(encoding="utf-8"))
    resolution_payload = json.loads(resolution_path.read_text(encoding="utf-8"))
    now = _parse_timestamp(args.now_utc, key="now_utc") if args.now_utc else None
    report = verify_resolution_evidence(
        apply_payload,
        resolution_payload,
        expected_task_ids=args.task_ids,
        require_empty_active=args.require_empty_active,
        now=now,
        max_age_hours=args.max_age_hours,
    )
    report["source_json"] = {
        "apply": str(apply_path),
        "resolution": str(resolution_path),
    }
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
