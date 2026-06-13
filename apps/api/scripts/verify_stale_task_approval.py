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


def _verify_freshness(
    payload: dict,
    *,
    key: str,
    now: datetime | None,
    max_age_hours: float | None = None,
) -> tuple[datetime, float]:
    generated_at = _parse_timestamp(payload.get("generated_at"), key=f"{key}.generated_at" if key else "generated_at")
    current = now or datetime.now(timezone.utc)
    _require(current.tzinfo is not None and current.utcoffset() is not None, "now must be timezone-aware")
    age_hours = (current.astimezone(timezone.utc) - generated_at).total_seconds() / 3600
    _require(age_hours >= 0, f"{key + '.' if key else ''}generated_at must not be in the future")
    effective_max_age_hours = _max_age_hours(payload, key=key or "evidence", override=max_age_hours)
    _require(
        age_hours <= effective_max_age_hours,
        f"{key + '.' if key else ''}generated_at is older than max_age_hours",
    )
    return generated_at, effective_max_age_hours


def approval_fingerprint(payload: dict) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def verify_approval_payload(
    payload: dict,
    *,
    expected_task_ids: Sequence[int] | None = None,
    now: datetime | None = None,
    max_age_hours: float | None = None,
) -> dict:
    _require(isinstance(payload, dict), "approval payload must be a JSON object")
    _assert_no_backend_paths(payload)
    generated_at_utc, effective_max_age_hours = _verify_freshness(payload, key="", now=now, max_age_hours=max_age_hours)
    _require(payload.get("mode") == "dry_run", "mode must be dry_run")
    _require(payload.get("container_check_status") == "passed", "container_check_status must be passed")
    _require(_as_int_list(payload.get("running_container_task_ids"), key="running_container_task_ids") == [], "running_container_task_ids must be empty")
    _require(_as_int_list(payload.get("blocked_task_ids"), key="blocked_task_ids") == [], "blocked_task_ids must be empty")
    _require(_as_int_list(payload.get("updated_task_ids"), key="updated_task_ids") == [], "updated_task_ids must be empty")
    _require(_as_int_list(payload.get("out_of_scope_stale_task_ids"), key="out_of_scope_stale_task_ids") == [], "out_of_scope_stale_task_ids must be empty")

    target_task_ids = _as_int_list(payload.get("target_task_ids"), key="target_task_ids")
    if expected_task_ids is not None:
        expected = sorted(int(task_id) for task_id in expected_task_ids)
        _require(sorted(target_task_ids) == expected, "target_task_ids must match expected task ids")

    stale_candidates = payload.get("stale_candidates")
    _require(isinstance(stale_candidates, list) and stale_candidates, "stale_candidates must be non-empty")
    stale_candidate_ids = []
    for candidate in stale_candidates:
        _require(isinstance(candidate, dict), "stale_candidates entries must be objects")
        _require("log_path" not in candidate, "stale_candidates must not expose log_path")
        _require(candidate.get("is_stale") is True, "stale_candidates entries must be stale")
        _require(candidate.get("status") in {"queued", "running"}, "stale_candidates entries must be active tasks")
        task_id = candidate.get("id")
        _require(isinstance(task_id, int) and not isinstance(task_id, bool), "stale_candidates id must be an integer")
        stale_candidate_ids.append(task_id)
    _require(sorted(stale_candidate_ids) == sorted(target_task_ids), "stale_candidate ids must match target_task_ids")

    reviewed_payload = payload.get("approval_payload")
    _require(isinstance(reviewed_payload, dict), "approval_payload must be present")
    _require(
        _as_int_list(reviewed_payload.get("target_task_ids"), key="approval_payload.target_task_ids") == target_task_ids,
        "approval_payload.target_task_ids must match target_task_ids",
    )
    _require(
        _as_int_list(reviewed_payload.get("stale_candidate_ids"), key="approval_payload.stale_candidate_ids") == stale_candidate_ids,
        "approval_payload.stale_candidate_ids must match stale_candidates",
    )
    _require(
        _as_int_list(reviewed_payload.get("running_container_task_ids"), key="approval_payload.running_container_task_ids") == [],
        "approval_payload.running_container_task_ids must be empty",
    )
    _require(
        _as_int_list(reviewed_payload.get("blocked_task_ids"), key="approval_payload.blocked_task_ids") == [],
        "approval_payload.blocked_task_ids must be empty",
    )
    _require(reviewed_payload.get("container_check_status") == "passed", "approval_payload.container_check_status must be passed")

    actual_fingerprint = payload.get("approval_fingerprint")
    _require(isinstance(actual_fingerprint, str) and len(actual_fingerprint) == 64, "approval_fingerprint must be a SHA-256 hex string")
    expected_fingerprint = approval_fingerprint(reviewed_payload)
    _require(actual_fingerprint == expected_fingerprint, "approval_fingerprint mismatch")

    return {
        "status": "passed",
        "summary": "status=passed",
        "checked": {
            "target_task_ids": target_task_ids,
            "stale_candidate_ids": stale_candidate_ids,
            "approval_fingerprint": actual_fingerprint,
            "container_check_status": payload["container_check_status"],
            "max_age_hours": effective_max_age_hours,
            "generated_at_utc": generated_at_utc.isoformat(),
        },
    }


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Verify a reviewed stale-task dry-run approval JSON artifact.")
    parser.add_argument("approval_json", help="Path to JSON written by reconcile_stale_tasks.py dry-run.")
    parser.add_argument("--task-id", action="append", type=int, dest="task_ids", help="Expected target task id. Repeat for multiple ids.")
    parser.add_argument(
        "--max-age-hours",
        type=float,
        default=None,
        help="Override the payload max_age_hours freshness limit for approval evidence.",
    )
    parser.add_argument(
        "--now-utc",
        default=None,
        help="Testing hook: ISO-8601 UTC timestamp used as current time for --max-age-hours.",
    )
    args = parser.parse_args(argv)
    source_path = Path(args.approval_json)
    payload = json.loads(source_path.read_text(encoding="utf-8"))
    now = _parse_timestamp(args.now_utc, key="now_utc") if args.now_utc else None
    report = verify_approval_payload(
        payload,
        expected_task_ids=args.task_ids,
        now=now,
        max_age_hours=args.max_age_hours,
    )
    report["source_json"] = str(source_path)
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
